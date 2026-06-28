"""
tests/test_catalog.py
──────────────────────────────────────────────────────────────────────────────
Unit tests for config/catalog.py.

The module is dependency-light (stdlib + pyyaml) and its core functions are
pure, so no GCP or settings env is required — same isolation contract as
test_sanitize_client_history.py.
"""

import pytest

from config.catalog import (
    Catalog,
    CatalogError,
    is_dataset_allowed,
    is_table_allowed,
    load_catalog,
    parse_catalog,
    render_catalog_prompt,
    tables_out_of_scope,
)


def _sales_raw() -> dict:
    return {
        "domain": {"name": "Sales", "description": "Sales data."},
        "datasets": [
            {
                "id": "proj.sales",
                "description": "Core sales.",
                "tables": [
                    {
                        "id": "proj.sales.orders",
                        "description": "One row per order.",
                        "fields": [
                            {"name": "order_id", "type": "STRING", "description": "PK."},
                            {"name": "amount_usd", "type": "NUMERIC"},
                        ],
                    }
                ],
            }
        ],
    }


# ── parsing: happy path ───────────────────────────────────────────────────────


def test_parse_builds_full_hierarchy():
    cat = parse_catalog(_sales_raw())
    assert cat.domain_name == "Sales"
    assert len(cat.datasets) == 1
    ds = cat.datasets[0]
    assert ds.id == "proj.sales"
    assert ds.tables[0].id == "proj.sales.orders"
    assert ds.tables[0].fields[0].name == "order_id"


def test_allowed_id_sets():
    cat = parse_catalog(_sales_raw())
    assert cat.allowed_dataset_ids == frozenset({"proj.sales"})
    assert cat.allowed_table_ids == frozenset({"proj.sales.orders"})


# ── parsing: validation failures (fail-fast at the boundary) ──────────────────


def test_unqualified_dataset_id_rejected():
    raw = {"datasets": [{"id": "sales"}]}  # missing project
    with pytest.raises(CatalogError):
        parse_catalog(raw)


def test_unqualified_table_id_rejected():
    raw = {"datasets": [{"id": "proj.sales", "tables": [{"id": "sales.orders"}]}]}
    with pytest.raises(CatalogError):
        parse_catalog(raw)


def test_table_outside_its_dataset_rejected():
    raw = {
        "datasets": [
            {"id": "proj.sales", "tables": [{"id": "proj.other.orders"}]}
        ]
    }
    with pytest.raises(CatalogError):
        parse_catalog(raw)


def test_duplicate_dataset_rejected():
    raw = {"datasets": [{"id": "proj.sales"}, {"id": "proj.sales"}]}
    with pytest.raises(CatalogError):
        parse_catalog(raw)


def test_duplicate_table_rejected():
    raw = {
        "datasets": [
            {
                "id": "proj.sales",
                "tables": [{"id": "proj.sales.orders"}, {"id": "proj.sales.orders"}],
            }
        ]
    }
    with pytest.raises(CatalogError):
        parse_catalog(raw)


def test_dataset_missing_id_rejected():
    with pytest.raises(CatalogError):
        parse_catalog({"datasets": [{"description": "no id"}]})


# ── empty / unscoped catalog ──────────────────────────────────────────────────


def test_empty_catalog_is_empty():
    assert Catalog().is_empty is True
    assert parse_catalog({}).is_empty is True


def test_load_missing_file_returns_empty(tmp_path):
    cat = load_catalog(tmp_path / "does_not_exist.yaml")
    assert cat.is_empty is True


def test_load_malformed_yaml_raises(tmp_path):
    bad = tmp_path / "bad.yaml"
    bad.write_text("domain: [unterminated\n")
    with pytest.raises(CatalogError):
        load_catalog(bad)


def test_load_valid_yaml_roundtrip(tmp_path):
    import yaml

    f = tmp_path / "catalog.yaml"
    f.write_text(yaml.safe_dump(_sales_raw()))
    cat = load_catalog(f)
    assert cat.domain_name == "Sales"
    assert cat.allowed_dataset_ids == frozenset({"proj.sales"})


# ── scope enforcement ─────────────────────────────────────────────────────────


def test_in_scope_dataset_and_table_allowed():
    cat = parse_catalog(_sales_raw())
    assert is_dataset_allowed(cat, "proj.sales") is True
    assert is_table_allowed(cat, "proj.sales.orders") is True
    # dataset-granularity: a non-enumerated table in an allowed dataset is allowed
    assert is_table_allowed(cat, "proj.sales.returns") is True


def test_out_of_scope_dataset_and_table_denied():
    cat = parse_catalog(_sales_raw())
    assert is_dataset_allowed(cat, "proj.finance") is False
    assert is_table_allowed(cat, "proj.finance.ledger") is False


def test_empty_catalog_allows_everything():
    cat = Catalog()
    assert is_dataset_allowed(cat, "anything.at.all") is True
    assert is_table_allowed(cat, "any.thing.here") is True


# ── prompt rendering ──────────────────────────────────────────────────────────


def test_render_includes_domain_datasets_and_fields():
    out = render_catalog_prompt(parse_catalog(_sales_raw()))
    assert "Sales" in out
    assert "proj.sales" in out
    assert "proj.sales.orders" in out
    assert "order_id" in out


def test_render_empty_catalog_is_blank():
    assert render_catalog_prompt(Catalog()) == ""


# ── SQL scope enforcement (tables_out_of_scope) ───────────────────────────────


def _sales_catalog() -> Catalog:
    return parse_catalog(_sales_raw())  # allows dataset proj.sales


def test_in_scope_query_has_no_denials():
    cat = _sales_catalog()
    sql = "SELECT order_id FROM `proj.sales.orders` WHERE amount_usd > 10"
    assert tables_out_of_scope(cat, sql, project="proj") == []


def test_out_of_scope_query_is_flagged():
    cat = _sales_catalog()
    sql = "SELECT * FROM `proj.finance.ledger`"
    assert tables_out_of_scope(cat, sql, project="proj") == ["proj.finance.ledger"]


def test_dataset_qualified_ref_uses_default_project():
    cat = _sales_catalog()
    # `sales.orders` (no project) resolves against the deployment project.
    sql = "SELECT * FROM sales.orders"
    assert tables_out_of_scope(cat, sql, project="proj") == []


def test_join_with_one_out_of_scope_table_is_flagged():
    cat = _sales_catalog()
    sql = (
        "SELECT o.order_id FROM `proj.sales.orders` o "
        "JOIN `proj.finance.ledger` l ON o.order_id = l.order_id"
    )
    assert tables_out_of_scope(cat, sql, project="proj") == ["proj.finance.ledger"]


def test_cte_name_is_not_treated_as_table():
    cat = _sales_catalog()
    sql = (
        "WITH recent AS (SELECT * FROM `proj.sales.orders`) "
        "SELECT * FROM recent"
    )
    assert tables_out_of_scope(cat, sql, project="proj") == []


def test_bare_table_with_default_dataset_resolves():
    cat = _sales_catalog()
    sql = "SELECT * FROM orders"  # default dataset = sales
    assert tables_out_of_scope(cat, sql, project="proj", default_dataset="sales") == []


def test_bare_unresolvable_table_is_flagged():
    cat = _sales_catalog()
    sql = "SELECT * FROM orders"  # no default dataset → cannot resolve safely
    assert tables_out_of_scope(cat, sql, project="proj") == ["orders"]


def test_empty_catalog_never_flags():
    sql = "SELECT * FROM `anything.at.all`"
    assert tables_out_of_scope(Catalog(), sql, project="proj") == []
