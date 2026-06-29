"""
Unit tests for tools/bigquery_tools.py — pure functions and scope enforcement.

GCP credentials and a real BigQuery client are never needed: BQ client calls
are mocked at the function level via unittest.mock.patch. The pure helpers
(_assert_read_only, _qualify_table, _qualify_dataset) are tested directly.

Env vars (GCP_PROJECT_ID, BQ_DEFAULT_DATASET) are set by tests/conftest.py
before this module is imported, satisfying config/settings.py's import-time
_require_env("GCP_PROJECT_ID") call.
"""

from __future__ import annotations

# Stub out the tools package before any import to prevent tools/__init__.py
# from running. __init__.py eagerly imports ALL tools (drive_tools, report_tools,
# etc.) which require googleapiclient, jinja2, matplotlib, and more. By
# pre-registering a lightweight stub, Python will still find and load
# tools/bigquery_tools.py as a submodule without the __init__.py side effects.
import sys
import types
from pathlib import Path

if 'tools' not in sys.modules:
    _tools_stub = types.ModuleType('tools')
    _tools_stub.__path__ = [str(Path(__file__).parent.parent / 'tools')]
    _tools_stub.__package__ = 'tools'
    sys.modules['tools'] = _tools_stub

import pytest
from unittest.mock import MagicMock, patch

from config.catalog import parse_catalog
from config.settings import settings
from tools.bigquery_tools import (
    _assert_read_only,
    _qualify_dataset,
    _qualify_table,
    bq_describe_table,
    bq_list_tables,
)


# ── _assert_read_only ─────────────────────────────────────────────────────────


def test_assert_read_only_simple_select_passes():
    _assert_read_only("SELECT * FROM `test-project-id.ds.orders`")


def test_assert_read_only_with_cte_passes():
    _assert_read_only(
        "WITH cte AS (SELECT id, amount FROM `proj.ds.orders`) "
        "SELECT id, SUM(amount) FROM cte GROUP BY id"
    )


def test_assert_read_only_union_all_passes():
    _assert_read_only(
        "SELECT a, b FROM `proj.ds.t1` UNION ALL SELECT a, b FROM `proj.ds.t2`"
    )


def test_assert_read_only_empty_raises():
    with pytest.raises(ValueError, match="Empty SQL"):
        _assert_read_only("")


def test_assert_read_only_multiple_statements_raises():
    with pytest.raises(ValueError, match="Stacked queries"):
        _assert_read_only("SELECT 1; SELECT 2")


def test_assert_read_only_insert_raises():
    with pytest.raises(ValueError, match="Mutating SQL"):
        _assert_read_only("INSERT INTO `proj.ds.t` VALUES (1, 'x')")


def test_assert_read_only_update_raises():
    with pytest.raises(ValueError, match="Mutating SQL"):
        _assert_read_only("UPDATE `proj.ds.t` SET a = 1 WHERE b = 2")


def test_assert_read_only_delete_raises():
    with pytest.raises(ValueError, match="Mutating SQL"):
        _assert_read_only("DELETE FROM `proj.ds.t` WHERE a = 1")


def test_assert_read_only_drop_table_raises():
    with pytest.raises(ValueError, match="Mutating SQL"):
        _assert_read_only("DROP TABLE `proj.ds.t`")


def test_assert_read_only_create_table_raises():
    with pytest.raises(ValueError, match="Mutating SQL"):
        _assert_read_only("CREATE TABLE `proj.ds.t` AS SELECT 1")


def test_assert_read_only_merge_raises():
    with pytest.raises(ValueError, match="Mutating SQL"):
        _assert_read_only(
            "MERGE `proj.ds.target` AS T "
            "USING (SELECT id FROM `proj.ds.src`) AS S ON T.id = S.id "
            "WHEN MATCHED THEN UPDATE SET T.val = S.val"
        )


def test_assert_read_only_truncate_raises():
    with pytest.raises(ValueError, match="Mutating SQL"):
        _assert_read_only("TRUNCATE TABLE `proj.ds.t`")


# ── _qualify_table ─────────────────────────────────────────────────────────────


def test_qualify_table_already_fq():
    # Three-part: project.dataset.table — returned as-is
    assert _qualify_table("myproj.myds.orders") == "myproj.myds.orders"


def test_qualify_table_dataset_dot_table():
    # Two-part: dataset.table — project prepended from settings
    assert _qualify_table("myds.orders") == "test-project-id.myds.orders"


def test_qualify_table_bare_with_default_dataset():
    # One-part: bare table name with BQ_DEFAULT_DATASET configured
    # conftest sets BQ_DEFAULT_DATASET="test_dataset"
    assert _qualify_table("orders") == "test-project-id.test_dataset.orders"


def test_qualify_table_bare_no_default_dataset(monkeypatch):
    # One-part: bare table name without a default dataset → returned as-is
    monkeypatch.setattr(settings, "bq_default_dataset", "")
    assert _qualify_table("orders") == "orders"


def test_qualify_table_strips_backticks():
    assert _qualify_table("`myproj.myds.orders`") == "myproj.myds.orders"


def test_qualify_table_strips_whitespace():
    assert _qualify_table("  myds.orders  ") == "test-project-id.myds.orders"


# ── _qualify_dataset ──────────────────────────────────────────────────────────


def test_qualify_dataset_already_fq():
    assert _qualify_dataset("myproj.myds") == "myproj.myds"


def test_qualify_dataset_bare():
    assert _qualify_dataset("myds") == "test-project-id.myds"


def test_qualify_dataset_strips_whitespace():
    assert _qualify_dataset("  myds  ") == "test-project-id.myds"


def test_qualify_dataset_strips_backticks():
    assert _qualify_dataset("`myproj.myds`") == "myproj.myds"


# ── bq_list_tables — scope enforcement ────────────────────────────────────────


def _make_scoped_catalog():
    """Catalog allowing only test-project-id.allowed_ds."""
    return parse_catalog({
        "domain": {"name": "Test", "description": "Test domain"},
        "datasets": [{"id": "test-project-id.allowed_ds", "description": "Allowed dataset"}],
    })


def test_bq_list_tables_denied_returns_scope_denied_marker():
    # Arrange
    catalog = _make_scoped_catalog()
    with patch("tools.bigquery_tools.get_catalog", return_value=catalog), \
         patch("tools.bigquery_tools.get_bq_client") as mock_get_client:

        # Act
        result = bq_list_tables("denied_ds")

    # Assert — marker returned, BQ client never instantiated
    assert "SCOPE_DENIED" in result
    mock_get_client.assert_not_called()


def test_bq_list_tables_allowed_calls_bq_client():
    # Arrange
    catalog = _make_scoped_catalog()
    mock_bq = MagicMock()
    mock_table = MagicMock()
    mock_table.table_id = "orders"
    mock_table.table_type = "TABLE"
    mock_bq.list_tables.return_value = [mock_table]

    with patch("tools.bigquery_tools.get_catalog", return_value=catalog), \
         patch("tools.bigquery_tools.get_bq_client", return_value=mock_bq):

        # Act
        result = bq_list_tables("allowed_ds")

    # Assert
    assert "SCOPE_DENIED" not in result
    assert "orders" in result
    mock_bq.list_tables.assert_called_once_with("test-project-id.allowed_ds")


def test_bq_list_tables_unscoped_calls_bq_client():
    # Arrange — empty catalog means unscoped (all datasets allowed)
    empty_catalog = parse_catalog({"domain": {"name": "Test"}, "datasets": []})
    mock_bq = MagicMock()
    mock_bq.list_tables.return_value = []

    with patch("tools.bigquery_tools.get_catalog", return_value=empty_catalog), \
         patch("tools.bigquery_tools.get_bq_client", return_value=mock_bq):

        # Act
        result = bq_list_tables("some_ds")

    # Assert
    assert "SCOPE_DENIED" not in result
    mock_bq.list_tables.assert_called_once()


# ── bq_describe_table — scope enforcement ─────────────────────────────────────


def test_bq_describe_table_denied_returns_scope_denied_marker():
    catalog = _make_scoped_catalog()
    with patch("tools.bigquery_tools.get_catalog", return_value=catalog), \
         patch("tools.bigquery_tools.get_bq_client") as mock_get_client:

        result = bq_describe_table("denied_ds.orders")

    assert "SCOPE_DENIED" in result
    mock_get_client.assert_not_called()


def test_bq_describe_table_allowed_calls_bq_client():
    catalog = _make_scoped_catalog()
    mock_bq = MagicMock()
    mock_table_meta = MagicMock()
    mock_table_meta.num_rows = 1000
    mock_table_meta.num_bytes = 50000
    mock_table_meta.schema = []
    mock_bq.get_table.return_value = mock_table_meta
    mock_bq.query.return_value.to_dataframe.return_value = MagicMock(
        to_string=MagicMock(return_value="col1 col2\n1    2")
    )

    with patch("tools.bigquery_tools.get_catalog", return_value=catalog), \
         patch("tools.bigquery_tools.get_bq_client", return_value=mock_bq):

        result = bq_describe_table("allowed_ds.orders")

    assert "SCOPE_DENIED" not in result
    mock_bq.get_table.assert_called_once_with("test-project-id.allowed_ds.orders")
