"""
tools/analysis_tools.py
─────────────────────────────────────────────────────────────────────────────
Statistical analysis tools operating on cached DataFrames.

All tools accept a cache_key so the agent can work with multiple datasets
in the same session (e.g. 'bq_orders' and 'sheet_targets' side-by-side).

Tools:
  df_describe        – descriptive stats, null rates, type overview
  df_correlations    – correlation matrix + top pairs
  df_value_counts    – frequency distribution for a column
  df_group_by        – group-by aggregation
  df_time_series     – resample + trend over time
  df_detect_outliers – IQR-based outlier flagging
  df_compare         – compare two cached DataFrames on a shared key column
  df_check_key       – verify key uniqueness and dtype before joining (TICKET-007)
"""

from __future__ import annotations

import io

import numpy as np
import pandas as pd

from tools.bigquery_tools import get_cached_df

# TICKET-006: hard ceiling on projected merged row count to prevent Cartesian
# explosions when the agent picks a non-unique join key.
MAX_MERGE_ROWS = 5_000_000


def _require(key: str) -> pd.DataFrame:
    df = get_cached_df(key)
    if df is None:
        raise ValueError(
            f"No DataFrame under key '{key}'. "
            "Run bq_run_query or sheet_from_url first."
        )
    return df


def df_describe(cache_key: str = "latest") -> str:
    """
    Descriptive statistics for a cached DataFrame.
    Covers shape, null rates, numeric stats, and categorical overviews.

    Args:
        cache_key: Name of the cached DataFrame (default 'latest').
    """
    df = _require(cache_key)
    buf = io.StringIO()
    buf.write(f"=== '{cache_key}' — {df.shape[0]:,} rows × {df.shape[1]} cols ===\n\n")

    null_pct = (df.isnull().mean() * 100).round(1)
    buf.write("Null % per column:\n")
    for col, pct in null_pct.items():
        buf.write(f"  {col}: {pct:.1f}%{'  ⚠' if pct > 20 else ''}\n")

    num = df.select_dtypes(include="number")
    if not num.empty:
        buf.write("\nNumeric stats:\n")
        buf.write(num.describe().round(3).to_string())
        buf.write("\n")

    cat = df.select_dtypes(include=["object", "category"])
    if not cat.empty:
        buf.write("\nCategorical columns:\n")
        for col in cat.columns:
            n = df[col].nunique()
            vc = df[col].value_counts()
            top = vc.index[0] if len(vc) > 0 else "—"
            buf.write(f"  {col}: {n} unique  (top: '{top}')\n")

    return buf.getvalue()


def df_correlations(cache_key: str = "latest", method: str = "pearson") -> str:
    """
    Correlation matrix for all numeric columns.

    Args:
        cache_key: DataFrame name (default 'latest').
        method:    'pearson', 'spearman', or 'kendall'.
    """
    df = _require(cache_key)
    num = df.select_dtypes(include="number")
    if num.shape[1] < 2:
        return "Need ≥ 2 numeric columns."

    corr = num.corr(method=method)
    pairs = (
        corr.where(pd.DataFrame(np.tril(np.ones(corr.shape), k=-1).astype(bool),
                                index=corr.index, columns=corr.columns))
        .stack().abs().sort_values(ascending=False).head(5)
    )
    buf = io.StringIO()
    buf.write(f"Correlation matrix ({method}):\n{corr.round(3).to_string()}\n\n")
    buf.write("Top 5 strongest pairs:\n")
    for (c1, c2), v in pairs.items():
        buf.write(f"  {c1} ↔ {c2}: {v:.3f}\n")
    return buf.getvalue()


def df_value_counts(column: str, cache_key: str = "latest", top_n: int = 20) -> str:
    """
    Frequency distribution for a categorical column.

    Args:
        column:    Column to analyse.
        cache_key: DataFrame name (default 'latest').
        top_n:     Show top N values (default 20).
    """
    df = _require(cache_key)
    if column not in df.columns:
        return f"Column '{column}' not found. Available: {list(df.columns)}"

    if len(df) == 0:
        return f"DataFrame '{cache_key}' is empty — no values to count."

    vc = df[column].value_counts(dropna=False).head(top_n)
    total = len(df)
    buf = io.StringIO()
    buf.write(f"Value counts — '{column}' (top {top_n}):\n")
    for val, cnt in vc.items():
        buf.write(f"  {str(val):<35} {cnt:>8,}  {cnt/total*100:>5.1f}%\n")
    return buf.getvalue()


def df_group_by(
    group_columns: str,
    agg_column: str,
    agg_func: str = "sum",
    cache_key: str = "latest",
) -> str:
    """
    Group-by aggregation on a cached DataFrame.

    Args:
        group_columns: Comma-separated column(s) to group by, e.g. 'region,product'.
        agg_column:    Numeric column to aggregate.
        agg_func:      'sum', 'mean', 'count', 'min', 'max', 'median'.
        cache_key:     DataFrame name (default 'latest').
    """
    df = _require(cache_key)
    groups = [c.strip() for c in group_columns.split(",")]
    missing = [c for c in groups + [agg_column] if c not in df.columns]
    if missing:
        return f"Columns not found: {missing}. Available: {list(df.columns)}"

    result = (
        df.groupby(groups)[agg_column]
        .agg(agg_func)
        .reset_index()
        .sort_values(agg_column, ascending=False)
    )
    return result.head(30).to_string(index=False)


def df_time_series(
    date_column: str,
    value_column: str,
    freq: str = "ME",
    agg_func: str = "sum",
    cache_key: str = "latest",
) -> str:
    """
    Resample a time-series column to identify trends.

    Args:
        date_column:  Date / timestamp column.
        value_column: Numeric column to aggregate.
        freq:         Pandas offset alias — 'D', 'W', 'ME' (month-end),
                      'QE' (quarter-end), 'YE' (year-end).
        agg_func:     Aggregation function (default 'sum').
        cache_key:    DataFrame name (default 'latest').
    """
    df = _require(cache_key)
    for col in [date_column, value_column]:
        if col not in df.columns:
            return f"Column '{col}' not found. Available: {list(df.columns)}"

    ts = df.copy()
    ts[date_column] = pd.to_datetime(ts[date_column], errors="coerce")
    ts = ts.dropna(subset=[date_column]).set_index(date_column)
    freq_map = {"M": "ME", "Q": "QE", "Y": "YE"}
    resolved_freq = freq_map.get(freq, freq)
    result = ts[value_column].resample(resolved_freq).agg(agg_func).dropna()
    return result.to_string()


def df_detect_outliers(cache_key: str = "latest", iqr_multiplier: float = 1.5) -> str:
    """
    Flag outliers in numeric columns using IQR method.

    Args:
        cache_key:      DataFrame name (default 'latest').
        iqr_multiplier: Whisker width multiplier (default 1.5 = standard boxplot).
    """
    df = _require(cache_key)
    num = df.select_dtypes(include="number")
    if num.empty:
        return "No numeric columns found."

    buf = io.StringIO()
    buf.write(f"Outlier detection (IQR × {iqr_multiplier}):\n\n")
    for col in num.columns:
        q1, q3 = num[col].quantile([0.25, 0.75])
        iqr = q3 - q1
        lo, hi = q1 - iqr_multiplier * iqr, q3 + iqr_multiplier * iqr
        mask = (num[col] < lo) | (num[col] > hi)
        n_out = int(mask.sum())
        examples = num.loc[mask, col].sort_values().head(3).tolist() if n_out else []
        flag = f"examples: {examples}" if examples else "none"
        buf.write(
            f"  {col}: {n_out} outliers  "
            f"(bounds [{lo:.2f}, {hi:.2f}])  {flag}\n"
        )
    return buf.getvalue()


def df_check_key(key_columns: str, cache_key: str = "latest") -> str:
    """
    Verify whether one or more columns form a unique, non-null key.
    Call this before df_compare to confirm the join key is valid.

    Args:
        key_columns: Comma-separated column name(s), e.g. 'order_id'
                     or 'region,product' for a composite key.
        cache_key:   DataFrame name (default 'latest').

    Returns:
        Structured report: row count, distinct count, null count, uniqueness
        verdict, per-column dtype. If a single column is not unique but the
        composite of all named columns is, that is stated explicitly.
    """
    df = _require(cache_key)
    cols = [c.strip() for c in key_columns.split(",")]
    missing = [c for c in cols if c not in df.columns]
    if missing:
        return f"Columns not found: {missing}. Available: {list(df.columns)}"

    total_rows = len(df)
    buf = io.StringIO()
    buf.write(f"Key check on '{cache_key}' — columns: {cols}\n\n")
    buf.write(f"  Total rows:      {total_rows:,}\n")

    # Per-column dtype and null report
    buf.write("\n  Per-column dtype and null count:\n")
    for col in cols:
        null_count = int(df[col].isnull().sum())
        buf.write(f"    {col}: dtype={df[col].dtype}  nulls={null_count:,}\n")

    # Composite key uniqueness
    composite_null_rows = int(df[cols].isnull().any(axis=1).sum())
    composite_distinct = int(df[cols].drop_duplicates().shape[0])
    composite_unique = (composite_distinct == total_rows) and (composite_null_rows == 0)

    buf.write(f"\n  Composite key ({' + '.join(cols)}):\n")
    buf.write(f"    Distinct tuples: {composite_distinct:,}\n")
    buf.write(f"    Rows with any null in key: {composite_null_rows:,}\n")
    buf.write(f"    Is unique key: {'✓ YES' if composite_unique else '✗ NO'}\n")

    # If composite is unique but individual columns are not, say so explicitly
    if len(cols) > 1:
        for col in cols:
            single_distinct = int(df[col].nunique(dropna=True))
            single_unique = (single_distinct == total_rows) and (int(df[col].isnull().sum()) == 0)
            buf.write(
                f"    '{col}' alone is {'✓ unique' if single_unique else '✗ NOT unique'} "
                f"({single_distinct:,} distinct values)\n"
            )

    if not composite_unique:
        dups = df[df.duplicated(subset=cols, keep=False)]
        example_keys = dups[cols].head(3).to_string(index=False)
        buf.write(f"\n  Example duplicate key values (first 3):\n{example_keys}\n")
        buf.write(
            "\n  ⚠ This column set is NOT a valid join key. "
            "Use df_check_key to find a unique alternative before calling df_compare.\n"
        )
    else:
        buf.write("\n  ✓ Safe to use as a join key in df_compare.\n")

    return buf.getvalue()


def df_compare(
    key_column: str,
    cache_key_a: str = "latest",
    cache_key_b: str = "",
    value_columns: str = "",
) -> str:
    """
    Compare two cached DataFrames on a shared key column.
    Useful for joining BigQuery data with a Google Sheet target/benchmark.

    TICKET-006: Cardinality guardrail — rejects non-unique keys on both sides
    that would produce a Cartesian explosion. Warns on one-to-many relationships.
    TICKET-006: Dtype compatibility check before merge.

    Args:
        key_column:    Column to join on (must exist in both DataFrames).
        cache_key_a:   First DataFrame (default 'latest').
        cache_key_b:   Second DataFrame name.
        value_columns: Comma-separated numeric columns to diff (optional).
    """
    if not cache_key_b:
        return "Provide cache_key_b — the name of the second DataFrame to compare against."

    df_a = _require(cache_key_a)
    df_b = _require(cache_key_b)

    if key_column not in df_a.columns or key_column not in df_b.columns:
        return (
            f"Key column '{key_column}' not in both DataFrames. "
            f"A has: {list(df_a.columns)}. B has: {list(df_b.columns)}"
        )

    # TICKET-006: dtype compatibility check.
    dtype_a = df_a[key_column].dtype
    dtype_b = df_b[key_column].dtype
    if dtype_a != dtype_b:
        return (
            f"Key column '{key_column}' has mismatched dtypes: "
            f"'{cache_key_a}' has {dtype_a}, '{cache_key_b}' has {dtype_b}. "
            "Cast both to the same type before comparing (e.g. .astype(str)). "
            "A dtype mismatch will silently produce zero matched rows."
        )

    # TICKET-006: cardinality guardrail.
    dup_a = bool(df_a[key_column].duplicated().any())
    dup_b = bool(df_b[key_column].duplicated().any())

    if dup_a and dup_b:
        # Estimate the Cartesian explosion: sum of (count_A_k * count_B_k) for shared keys.
        counts_a = df_a[key_column].value_counts()
        counts_b = df_b[key_column].value_counts()
        shared_keys = counts_a.index.intersection(counts_b.index)
        est_rows = int((counts_a[shared_keys] * counts_b[shared_keys]).sum())
        if est_rows > MAX_MERGE_ROWS:
            return (
                f"BLOCKED: Key column '{key_column}' has duplicate values in BOTH DataFrames. "
                f"Estimated merged row count: {est_rows:,} (cap: {MAX_MERGE_ROWS:,}). "
                "This would produce a many-to-many Cartesian explosion. "
                "Run df_check_key to identify a unique join key, then resubmit."
            )

    warning_prefix = ""
    if dup_a and not dup_b:
        warning_prefix = (
            f"⚠ One-to-many join: '{key_column}' has duplicates in '{cache_key_a}' "
            f"but is unique in '{cache_key_b}'.\n\n"
        )
    elif dup_b and not dup_a:
        warning_prefix = (
            f"⚠ One-to-many join: '{key_column}' has duplicates in '{cache_key_b}' "
            f"but is unique in '{cache_key_a}'.\n\n"
        )

    merged = df_a.merge(df_b, on=key_column, suffixes=("_A", "_B"), how="outer", indicator=True)
    counts = merged["_merge"].value_counts()

    buf = io.StringIO()
    buf.write(warning_prefix)
    buf.write(f"Comparison: '{cache_key_a}' vs '{cache_key_b}' on key '{key_column}'\n\n")
    buf.write(f"  Rows only in A: {counts.get('left_only', 0):,}\n")
    buf.write(f"  Rows only in B: {counts.get('right_only', 0):,}\n")
    buf.write(f"  Matching rows:  {counts.get('both', 0):,}\n")

    if value_columns:
        cols = [c.strip() for c in value_columns.split(",")]
        buf.write("\nDelta (A − B) for matched rows:\n")
        matched = merged[merged["_merge"] == "both"]
        for col in cols:
            a_col, b_col = f"{col}_A", f"{col}_B"
            if a_col in matched.columns and b_col in matched.columns:
                delta = (matched[a_col] - matched[b_col]).dropna()
                buf.write(
                    f"  {col}: mean delta = {delta.mean():.2f}, "
                    f"max = {delta.max():.2f}, min = {delta.min():.2f}\n"
                )
            else:
                buf.write(
                    f"  {col}: skipped — column not present in both DataFrames "
                    f"(needs '{a_col}' and '{b_col}').\n"
                )

    return buf.getvalue()
