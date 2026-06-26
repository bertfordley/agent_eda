"""
tools/bigquery_tools.py
─────────────────────────────────────────────────────────────────────────────
BigQuery tools as plain Python callables.

DataFrame cache (TICKET-4.2):
  _df_cache is keyed by (thread_id, cache_key) via a contextvars.ContextVar
  so concurrent conversations never overwrite each other's DataFrames.
  thread_id aligns the cache with the durable LangGraph conversation identity —
  within a process, DataFrames survive WebSocket reconnects on the same thread.

  INVARIANT — DataFrames must NEVER be stored in the LangGraph graph state or
  checkpoint. A DataFrame in graph state would be serialized to Postgres at
  every graph step, causing unbounded storage bloat. The cache (this module)
  is the ONLY correct place to hold DataFrame objects. Graph state holds
  cache_key strings only. Do not remove this guardrail.

Read-only SQL enforcement (TICKET-002):
  bq_run_query calls _assert_read_only() which uses sqlglot to parse and
  reject any non-SELECT statement or stacked queries before hitting BigQuery.

Dialect validation (TICKET-004):
  sqlglot.parse uses dialect="bigquery"; a ParseError surfaces immediately
  to the agent as a correction message.

Cost circuit-breaker (TICKET-003):
  A dry-run estimate is checked against bq_max_bytes_billed before the real
  query is submitted.

Materialize row cap (TICKET-010):
  Results exceeding MATERIALIZE_ROW_CAP rows are not pulled into pandas memory.

Governance telemetry (TELEMETRY):
  log_query_executed is called at every exit path of bq_run_query so the
  audit trail captures every SQL attempt, accepted or rejected.

Tools:
  bq_list_datasets       – list datasets in the project
  bq_list_tables         – list tables in a dataset
  bq_describe_table      – schema, row count, sample rows
  bq_run_query           – run SQL, return text summary + cache DataFrame
  bq_profile_dataset     – quick size/row-count overview of a whole dataset
"""

from __future__ import annotations

import io
import logging
import threading
import time
from contextvars import ContextVar
from typing import Optional

import pandas as pd
from google.api_core.exceptions import GoogleAPIError
from google.cloud import bigquery

from config.settings import get_bq_client, safe_query_config, dry_run_query_config, settings

logger = logging.getLogger(__name__)

# ── Thread-scoped DataFrame cache ─────────────────────────────────────────────
# Key: (thread_id, cache_key) → DataFrame
#
# current_session_id — ephemeral per-WebSocket-connection; used for telemetry.
# current_thread_id  — durable LangGraph conversation identity; keys the cache
#                      so DataFrames survive reconnects within the same process.
# Both are set per-turn by server.py. Do NOT conflate them.

current_session_id: ContextVar[str] = ContextVar("current_session_id", default="__default__")
current_thread_id: ContextVar[str] = ContextVar("current_thread_id", default="__default__")

_df_cache: dict[tuple[str, str], pd.DataFrame] = {}
_df_cache_lock = threading.Lock()
_thread_last_access: dict[str, float] = {}
MAX_THREADS = 32

MATERIALIZE_ROW_CAP = 1_000_000


def _evict_lru_thread() -> None:
    """Remove the least-recently-used thread's entries when cap is exceeded."""
    if len(_thread_last_access) <= MAX_THREADS:
        return
    oldest = min(_thread_last_access, key=lambda t: _thread_last_access[t])
    keys_to_remove = [k for k in _df_cache if k[0] == oldest]
    for k in keys_to_remove:
        del _df_cache[k]
    del _thread_last_access[oldest]
    logger.debug("Evicted DataFrame cache for thread_id=%s", oldest)


def get_cached_df(key: str = "latest") -> Optional[pd.DataFrame]:
    thread_id = current_thread_id.get()
    with _df_cache_lock:
        _thread_last_access[thread_id] = time.monotonic()
        return _df_cache.get((thread_id, key))


def set_cached_df(df: pd.DataFrame, key: str = "latest") -> None:
    thread_id = current_thread_id.get()
    with _df_cache_lock:
        _thread_last_access[thread_id] = time.monotonic()
        _df_cache[(thread_id, key)] = df
        _evict_lru_thread()


# ── SQL safety ────────────────────────────────────────────────────────────────

def _assert_read_only(sql: str) -> None:
    """
    Parse sql with sqlglot (BigQuery dialect) and raise ValueError if:
      - The SQL does not parse as valid BigQuery Standard SQL.
      - More than one statement is present (semicolon injection).
      - Any statement is not a SELECT / UNION / WITH…SELECT.
    """
    import sqlglot
    import sqlglot.errors
    import sqlglot.expressions as exp

    try:
        statements = sqlglot.parse(sql, dialect="bigquery")
    except sqlglot.errors.ParseError as e:
        raise ValueError(
            f"SQL does not parse as BigQuery Standard SQL: {e}. "
            "Please rewrite using BigQuery Standard SQL syntax "
            "(e.g. backtick identifiers, LIMIT instead of TOP, "
            "DATE_TRUNC(date, MONTH) not DATE_TRUNC('month', date))."
        )

    if not statements:
        raise ValueError("Empty SQL statement.")

    if len(statements) > 1:
        raise ValueError(
            f"Stacked queries are not allowed ({len(statements)} statements detected). "
            "Submit one SELECT statement at a time."
        )

    stmt = statements[0]

    MUTATING_TYPES = (
        exp.Insert, exp.Update, exp.Delete, exp.Drop,
        exp.Create, exp.Alter, exp.Merge, exp.TruncateTable,
    )
    for node in stmt.walk():
        if isinstance(node, MUTATING_TYPES):
            raise ValueError(
                f"Mutating SQL ({type(node).__name__}) is not permitted. "
                "Only read-only SELECT queries are allowed."
            )

    ALLOWED_ROOT_TYPES = (exp.Select, exp.Union, exp.With, exp.Subquery)
    if not isinstance(stmt, ALLOWED_ROOT_TYPES):
        raise ValueError(
            f"Only SELECT queries are permitted. Got: {type(stmt).__name__}. "
            "Rewrite as a SELECT statement."
        )


def _df_summary(df: pd.DataFrame, max_rows: int = 20) -> str:
    buf = io.StringIO()
    buf.write(f"Shape: {df.shape[0]:,} rows × {df.shape[1]} cols\n\n")
    buf.write("Columns (name → dtype):\n")
    for col, dtype in df.dtypes.items():
        buf.write(f"  {col}: {dtype}\n")
    buf.write(f"\nFirst {min(max_rows, len(df))} rows:\n")
    buf.write(df.head(max_rows).to_string(index=False))
    return buf.getvalue()


# ── Tools ─────────────────────────────────────────────────────────────────────

def bq_list_datasets() -> str:
    """List all BigQuery datasets in the configured GCP project."""
    try:
        client = get_bq_client()
        datasets = list(client.list_datasets())
        if not datasets:
            return f"No datasets found in project '{settings.gcp_project_id}'."
        return "Datasets:\n" + "\n".join(f"  • {ds.dataset_id}" for ds in datasets)
    except GoogleAPIError as e:
        return f"BigQuery error listing datasets: {e}"


def bq_list_tables(dataset_id: str) -> str:
    """
    List all tables and views in a BigQuery dataset.

    Args:
        dataset_id: Dataset name, e.g. 'analytics'
    """
    try:
        client = get_bq_client()
        tables = list(client.list_tables(dataset_id))
        if not tables:
            return f"No tables in '{dataset_id}'."
        lines = [f"  • {t.table_id} ({t.table_type})" for t in tables]
        return f"Tables in `{dataset_id}`:\n" + "\n".join(lines)
    except GoogleAPIError as e:
        return f"BigQuery error listing tables in '{dataset_id}': {e}"


def bq_describe_table(table_ref: str) -> str:
    """
    Return the schema, approximate row count, and 5 sample rows for a table.

    Args:
        table_ref: Fully-qualified ref like 'project.dataset.table'
                   or 'dataset.table' (uses configured project).
    """
    try:
        client = get_bq_client()
        if table_ref.count(".") == 1:
            table_ref = f"{settings.gcp_project_id}.{table_ref}"

        table = client.get_table(table_ref)
        buf = io.StringIO()
        buf.write(f"Table: `{table_ref}`\n")
        buf.write(f"Rows (approx): {table.num_rows:,}\n")
        buf.write(f"Size: {(table.num_bytes or 0) / 1e6:.1f} MB\n\n")
        buf.write("Schema:\n")
        for f in table.schema:
            mode = f" [{f.mode}]" if f.mode != "NULLABLE" else ""
            desc = f"  — {f.description}" if f.description else ""
            buf.write(f"  {f.name}: {f.field_type}{mode}{desc}\n")

        sample = client.query(
            f"SELECT * FROM `{table_ref}` LIMIT 5", job_config=safe_query_config()
        ).to_dataframe()
        buf.write("\nSample rows:\n")
        buf.write(sample.to_string(index=False))
        return buf.getvalue()
    except GoogleAPIError as e:
        return f"BigQuery error describing table '{table_ref}': {e}"


def bq_run_query(sql: str, cache_key: str = "latest") -> str:
    """
    Execute a BigQuery Standard SQL query.

    Results are cached so downstream analysis and chart tools can reuse
    them without re-running BigQuery.

    Args:
        sql:       Standard SQL. Use fully-qualified table refs.
        cache_key: Name for this result set (default 'latest').

    Returns:
        Text summary (shape + first 20 rows). Full DataFrame is in cache.
    """
    # Import here to avoid a circular import at module load time.
    # telemetry imports bigquery_tools (for current_session_id), so
    # bigquery_tools must not import telemetry at the top level.
    from telemetry.governance import log_query_executed

    # TICKET-002 + TICKET-004: validate SQL before touching BigQuery.
    try:
        _assert_read_only(sql)
    except ValueError as e:
        log_query_executed(
            sql=sql,
            row_count=None,
            bytes_processed=None,
            rejected=True,
            rejection_reason=str(e),
            cache_key=cache_key,
        )
        return f"SQL rejected: {e}"

    try:
        client = get_bq_client()

        # TICKET-003: dry-run cost estimate.
        dry_run_bytes: int | None = None
        try:
            dry_job = client.query(sql, job_config=dry_run_query_config())
            dry_run_bytes = dry_job.total_bytes_processed or 0
            if dry_run_bytes > settings.bq_max_bytes_billed:
                estimated_gb = dry_run_bytes / 1e9
                budget_gb = settings.bq_max_bytes_billed / 1e9
                msg = (
                    f"Query would scan ~{estimated_gb:.2f} GB, which exceeds the "
                    f"{budget_gb:.1f} GB budget cap. Add WHERE filters or a LIMIT "
                    "clause to reduce the scan size before resubmitting."
                )
                log_query_executed(
                    sql=sql,
                    row_count=None,
                    bytes_processed=None,
                    rejected=True,
                    rejection_reason=msg,
                    cache_key=cache_key,
                    dry_run_bytes=dry_run_bytes,
                )
                return msg
        except GoogleAPIError as e:
            err_msg = f"BigQuery query dry-run failed: {e}"
            log_query_executed(
                sql=sql,
                row_count=None,
                bytes_processed=None,
                rejected=True,
                rejection_reason=err_msg,
                cache_key=cache_key,
            )
            return err_msg

        # TICKET-010: row count check before materializing.
        query_job = client.query(sql, job_config=safe_query_config())
        result = query_job.result()
        total_rows = result.total_rows

        if total_rows is not None and total_rows > MATERIALIZE_ROW_CAP:
            msg = (
                f"Query would return {total_rows:,} rows, which exceeds the "
                f"{MATERIALIZE_ROW_CAP:,}-row materialization cap. "
                "Add GROUP BY / aggregation in SQL to reduce the result set, "
                "then resubmit."
            )
            log_query_executed(
                sql=sql,
                row_count=total_rows,
                bytes_processed=None,
                rejected=True,
                rejection_reason=msg,
                cache_key=cache_key,
                dry_run_bytes=dry_run_bytes,
            )
            return msg

        df = result.to_dataframe()
        bytes_processed = getattr(query_job, "total_bytes_processed", None)

        if df.empty:
            set_cached_df(df, key=cache_key)
            log_query_executed(
                sql=sql,
                row_count=0,
                bytes_processed=bytes_processed,
                rejected=False,
                rejection_reason=None,
                cache_key=cache_key,
                dry_run_bytes=dry_run_bytes,
            )
            return (
                f"[cache_key='{cache_key}'] Query succeeded but returned 0 rows. "
                "No data to analyze."
            )

        set_cached_df(df, key=cache_key)
        log_query_executed(
            sql=sql,
            row_count=len(df),
            bytes_processed=bytes_processed,
            rejected=False,
            rejection_reason=None,
            cache_key=cache_key,
            dry_run_bytes=dry_run_bytes,
        )
        return f"[cache_key='{cache_key}']\n" + _df_summary(df)

    except GoogleAPIError as e:
        err_msg = f"BigQuery query failed: {e}"
        log_query_executed(
            sql=sql,
            row_count=None,
            bytes_processed=None,
            rejected=True,
            rejection_reason=err_msg,
            cache_key=cache_key,
        )
        return err_msg


def bq_profile_dataset(dataset_id: str) -> str:
    """
    Quick profile of an entire dataset: table names, row counts, sizes.

    Args:
        dataset_id: BigQuery dataset name.
    """
    try:
        client = get_bq_client()
        tables = list(client.list_tables(dataset_id))
        if not tables:
            return f"Dataset '{dataset_id}' is empty."

        lines = []
        for t in tables[:40]:
            ref = f"{settings.gcp_project_id}.{dataset_id}.{t.table_id}"
            try:
                meta = client.get_table(ref)
                lines.append(
                    f"  {t.table_id:<45} {(meta.num_rows or 0):>12,} rows  "
                    f"{(meta.num_bytes or 0)/1e6:>8.1f} MB"
                )
            except Exception as e:
                logger.warning("Metadata fetch failed for %s: %s", t.table_id, e)
                lines.append(
                    f"  {t.table_id} (metadata unavailable: {type(e).__name__})"
                )

        header = f"  {'Table':<45} {'Rows':>12}  {'Size':>8}"
        return f"Dataset: {dataset_id}\n{header}\n" + "\n".join(lines)
    except GoogleAPIError as e:
        return f"BigQuery error profiling dataset '{dataset_id}': {e}"
