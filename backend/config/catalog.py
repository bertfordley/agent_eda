"""
config/catalog.py
─────────────────────────────────────────────────────────────────────────────
Per-deployment data catalog.

A deployment is scoped to ONE domain (e.g. "Sales Analytics"). The catalog is a
YAML file describing the BigQuery datasets/tables/fields that domain may touch,
in natural language. It serves two purposes:

1. SCOPING (security) — only the datasets listed here may be queried. Enforced
   server-side in tools/bigquery_tools.py; the model is never trusted to stay
   in bounds.
2. CONTEXT — render_catalog_prompt() turns the catalog into an NL block injected
   into the agent's system prompt so it understands the data without blind
   schema exploration.

This module is dependency-light (stdlib + pyyaml) and the core functions are
pure (they take a Catalog argument) so they are importable and testable in
isolation — mirroring history.py. Runtime callers use the cached get_catalog().

Backward compatibility: if no catalog file exists, load_catalog() returns an
EMPTY catalog. An empty catalog disables scoping (all datasets visible) and
renders no context block — the agent behaves exactly as it did before this
feature. A warning is logged so unscoped operation is never silent.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

_log = logging.getLogger(__name__)

# Marker returned to the agent when a ref is outside the configured scope.
# Mirrors the existing [CACHE_MISS ...] string-marker convention so the agent
# treats it as a tool-level signal rather than a crash.
SCOPE_DENIED = "SCOPE_DENIED"


# ── Model (frozen — immutable per coding-style.md) ────────────────────────────


@dataclass(frozen=True)
class FieldSpec:
    name: str
    type: str
    description: str = ""


@dataclass(frozen=True)
class TableSpec:
    id: str  # fully-qualified: project.dataset.table
    description: str = ""
    fields: tuple[FieldSpec, ...] = ()


@dataclass(frozen=True)
class DatasetSpec:
    id: str  # fully-qualified: project.dataset
    description: str = ""
    tables: tuple[TableSpec, ...] = ()


@dataclass(frozen=True)
class Catalog:
    domain_name: str = ""
    domain_description: str = ""
    datasets: tuple[DatasetSpec, ...] = ()

    @property
    def is_empty(self) -> bool:
        """True when no datasets are configured → scoping disabled (unscoped)."""
        return not self.datasets

    @property
    def allowed_dataset_ids(self) -> frozenset[str]:
        """Fully-qualified `project.dataset` ids that may be queried."""
        return frozenset(d.id for d in self.datasets)

    @property
    def allowed_table_ids(self) -> frozenset[str]:
        """Fully-qualified `project.dataset.table` ids enumerated in the catalog.

        Enumerated tables are a (possibly partial) subset used for NL context.
        Scoping is enforced at DATASET granularity (allowed_dataset_ids); a
        dataset being allowed permits every table within it, enumerated or not.
        """
        return frozenset(t.id for d in self.datasets for t in d.tables)


# ── Loading + validation (fail-fast at the boundary) ──────────────────────────


class CatalogError(ValueError):
    """Raised when a catalog file is present but malformed."""


def _require_qualified(ref: str, parts_expected: int, kind: str) -> None:
    parts = ref.split(".")
    if len(parts) != parts_expected or any(not p.strip() for p in parts):
        example = "project.dataset" if parts_expected == 2 else "project.dataset.table"
        raise CatalogError(
            f"{kind} id '{ref}' must be fully-qualified as '{example}' "
            f"({parts_expected} dot-separated parts)."
        )


def parse_catalog(raw: dict) -> Catalog:
    """Build a Catalog from an already-parsed YAML mapping. Pure + testable."""
    if not isinstance(raw, dict):
        raise CatalogError("Catalog root must be a mapping.")

    domain = raw.get("domain") or {}
    if not isinstance(domain, dict):
        raise CatalogError("`domain` must be a mapping with name/description.")

    datasets_raw = raw.get("datasets") or []
    if not isinstance(datasets_raw, list):
        raise CatalogError("`datasets` must be a list.")

    seen_datasets: set[str] = set()
    seen_tables: set[str] = set()
    datasets: list[DatasetSpec] = []

    for d in datasets_raw:
        if not isinstance(d, dict) or "id" not in d:
            raise CatalogError("Each dataset needs an `id`.")
        ds_id = str(d["id"]).strip()
        _require_qualified(ds_id, 2, "Dataset")
        if ds_id in seen_datasets:
            raise CatalogError(f"Duplicate dataset id '{ds_id}'.")
        seen_datasets.add(ds_id)

        tables: list[TableSpec] = []
        for t in d.get("tables") or []:
            if not isinstance(t, dict) or "id" not in t:
                raise CatalogError(f"Each table in dataset '{ds_id}' needs an `id`.")
            tbl_id = str(t["id"]).strip()
            _require_qualified(tbl_id, 3, "Table")
            if not tbl_id.startswith(ds_id + "."):
                raise CatalogError(
                    f"Table '{tbl_id}' is not inside its dataset '{ds_id}'."
                )
            if tbl_id in seen_tables:
                raise CatalogError(f"Duplicate table id '{tbl_id}'.")
            seen_tables.add(tbl_id)

            fields = tuple(
                FieldSpec(
                    name=str(f.get("name", "")).strip(),
                    type=str(f.get("type", "")).strip(),
                    description=str(f.get("description", "")).strip(),
                )
                for f in (t.get("fields") or [])
                if isinstance(f, dict)
            )
            tables.append(
                TableSpec(
                    id=tbl_id,
                    description=str(t.get("description", "")).strip(),
                    fields=fields,
                )
            )

        datasets.append(
            DatasetSpec(
                id=ds_id,
                description=str(d.get("description", "")).strip(),
                tables=tuple(tables),
            )
        )

    return Catalog(
        domain_name=str(domain.get("name", "")).strip(),
        domain_description=str(domain.get("description", "")).strip(),
        datasets=tuple(datasets),
    )


def load_catalog(path: str | Path) -> Catalog:
    """Load + validate the catalog YAML. Absent file → empty (unscoped) catalog."""
    p = Path(path)
    if not p.exists():
        _log.warning(
            "Data catalog '%s' not found — running UNSCOPED (all datasets "
            "visible, no domain context). Set DATA_CATALOG_PATH and provide a "
            "catalog file for domain-scoped deployment.",
            p,
        )
        return Catalog()

    try:
        raw = yaml.safe_load(p.read_text()) or {}
    except yaml.YAMLError as exc:  # malformed YAML — fail fast, don't run unscoped
        raise CatalogError(f"Could not parse catalog '{p}': {exc}") from exc

    return parse_catalog(raw)


@lru_cache(maxsize=1)
def get_catalog() -> Catalog:
    """Cached runtime accessor — parses the catalog once per process.

    settings is imported lazily (deferred) so this module stays import-safe for
    the pure unit tests, which must not trigger settings' required-env checks.
    """
    from config.settings import settings

    return load_catalog(settings.data_catalog_path)


# ── Scope enforcement (pure) ──────────────────────────────────────────────────


def is_dataset_allowed(catalog: Catalog, dataset_id: str) -> bool:
    """Empty catalog → everything allowed (unscoped). Else strict membership."""
    if catalog.is_empty:
        return True
    return dataset_id in catalog.allowed_dataset_ids


def dataset_of(table_id: str) -> str:
    """`project.dataset.table` → `project.dataset`. Caller must pass a fully
    qualified 3-part id (resolve defaults before calling)."""
    parts = table_id.split(".")
    return ".".join(parts[:2])


def is_table_allowed(catalog: Catalog, table_id: str) -> bool:
    """A fully-qualified table is allowed iff its dataset is allowed."""
    if catalog.is_empty:
        return True
    return dataset_of(table_id) in catalog.allowed_dataset_ids


def tables_out_of_scope(
    catalog: Catalog,
    sql: str,
    *,
    project: str,
    default_dataset: str = "",
) -> list[str]:
    """Return the table refs in `sql` that fall outside the catalog's scope.

    Pure + testable: the caller passes the deployment's default `project` and
    optional `default_dataset` rather than reading settings. Returns an empty
    list when the query is fully in scope OR when the catalog is empty. CTE names
    are excluded so common table expressions are never treated as real tables.

    sqlglot is imported lazily so this module stays import-clean (yaml-only) for
    the catalog tests that don't exercise SQL parsing.
    """
    if catalog.is_empty:
        return []

    import sqlglot
    import sqlglot.expressions as exp

    statement = sqlglot.parse_one(sql, dialect="bigquery")
    cte_names = {c.alias for c in statement.find_all(exp.CTE)}

    denied: list[str] = []
    for tnode in statement.find_all(exp.Table):
        name, db, proj = tnode.name, tnode.db, tnode.catalog

        # Bare name with no dataset that matches a CTE → not a real table.
        if not db and not proj and name in cte_names:
            continue

        if db and proj:
            fq = f"{proj}.{db}.{name}"
        elif db:
            fq = f"{project}.{db}.{name}"
        elif default_dataset:
            fq = f"{project}.{default_dataset}.{name}"
        else:
            # Unqualified, not a CTE, no default dataset — cannot resolve safely.
            denied.append(name)
            continue

        if not is_table_allowed(catalog, fq):
            denied.append(fq)

    return denied


# ── Prompt rendering ──────────────────────────────────────────────────────────


def render_catalog_prompt(catalog: Catalog) -> str:
    """NL block for the system prompt. Empty catalog → empty string."""
    if catalog.is_empty:
        return ""

    lines: list[str] = []
    header = catalog.domain_name or "this deployment"
    lines.append(f"━━ AVAILABLE DATA — {header} ━━")
    if catalog.domain_description:
        lines.append(catalog.domain_description)
    lines.append(
        "You are scoped to ONLY the datasets below. Queries against any other "
        "dataset are rejected automatically. Use this catalog to answer "
        "structural questions without exploratory schema calls."
    )

    for d in catalog.datasets:
        lines.append("")
        desc = f" — {d.description}" if d.description else ""
        lines.append(f"• Dataset `{d.id}`{desc}")
        for t in d.tables:
            tdesc = f" — {t.description}" if t.description else ""
            lines.append(f"  • Table `{t.id}`{tdesc}")
            for f in t.fields:
                ftype = f" ({f.type})" if f.type else ""
                fdesc = f" — {f.description}" if f.description else ""
                lines.append(f"      - {f.name}{ftype}{fdesc}")

    return "\n".join(lines)
