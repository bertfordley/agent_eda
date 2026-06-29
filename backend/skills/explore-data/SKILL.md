---
name: explore-data
description: Comprehensive data profile — shape, quality, distributions, and patterns. Run before drawing conclusions from any unfamiliar dataset.
when_to_use: User loads a new table or file, asks "is this data clean?", wants to understand a dataset, or requests a quality check before analysis.
---

# Data Exploration and Profile

Run this before any analysis on an unfamiliar dataset. It surfaces data quality
issues before they corrupt conclusions.

## Step 1 — Understand Structure

Before querying any data, understand its structure from the schema:

```
bq_describe_table(table_id)
```

From the schema output, classify each column:
- **Identifier**: unique keys, foreign keys, entity IDs
- **Dimension**: categorical attributes for grouping/filtering (status, type, region)
- **Metric**: quantitative values (revenue, count, duration, score)
- **Temporal**: dates and timestamps (created_at, updated_at, event_date)
- **Text**: free-form text (description, notes, name)
- **Boolean**: true/false flags
- **Structural**: JSON, arrays, nested fields (RECORD type in BigQuery)

Document the grain: "one row per ___" — this is the most important question
about any table and the one most often skipped.

## Step 2 — Profile the Data

Load a representative sample and run the full profiling suite:

```
bq_run_query(sql, cache_key="profile_sample")  -- use LIMIT 100000 for large tables
df_describe(cache_key="profile_sample")
```

For each important categorical column:
```
df_value_counts(column="<col>", cache_key="profile_sample")
```

For numeric columns, check outliers:
```
df_detect_outliers(cache_key="profile_sample")
```

For large tables where sampling isn't sufficient, use:
```
bq_profile_dataset(dataset_id)
```
This runs server-side aggregations and avoids pulling raw rows.

## Step 3 — Quality Assessment

Rate each column using this framework:

**Completeness:**
- ≥99% non-null → Complete (no action)
- 95–99% non-null → Mostly complete (investigate the nulls — are they structural or a bug?)
- 80–95% non-null → Incomplete (understand why before using this column in aggregations)
- <80% non-null → Sparse (may need imputation or exclusion — flag clearly)

**Consistency red flags to look for in `df_value_counts` output:**
- Same concept represented differently: "USA", "US", "United States", "us"
- Numbers stored as strings ("1,234" instead of 1234)
- Dates in mixed formats ("2024-01-15" and "Jan 15 2024" in the same column)
- Foreign keys that have no matching parent (check with `df_check_key` + a join query)

**Accuracy red flags (look in `df_detect_outliers` and `df_describe` output):**
- Placeholder values: 0, -1, 999999, "N/A", "TBD", "test", "xxx"
- Suspiciously high frequency of a single value (the modal value dominates > 80%)
- Impossible values: ages > 150, future timestamps in historical data, negative quantities
- Round-number bias: all values ending in 0 or 5 (suggests estimation)

**Timeliness:**
- What is the `MAX(updated_at)` or equivalent? Is it recent for an active table?
- Are there gaps in the time series? (Run `df_time_series` on the date column to check)

## Step 4 — Key and Duplicate Check

If the table has a natural identifier, verify it:
```
df_check_key(key_columns="<id_column>", cache_key="profile_sample")
```

For composite keys:
```
df_check_key(key_columns="col_a,col_b", cache_key="profile_sample")
```

A non-unique key on a table you intend to join against is a silent data corruption
risk. Never skip this check.

## Step 5 — Pattern Discovery

Look for relationships and patterns:

**Distribution shapes** (visible from `df_describe` percentiles):
- Normal: mean ≈ median, p25 and p75 roughly symmetric around p50
- Right-skewed: mean > median, long tail of high values (common for revenue, session duration)
- Bimodal: two distinct peaks (suggests two populations — segment and analyze separately)
- Power law: very few large values, very many small ones (common for user activity)

**Temporal patterns** (run `df_time_series` on date columns):
- Trend: sustained upward or downward movement
- Seasonality: repeating weekly, monthly, or annual pattern
- Change point: sudden level shift (often corresponds to a product launch or data pipeline change)
- Gaps: missing periods that shouldn't be missing

**Correlations** (run `df_correlations` on numeric columns):
- Flag strong correlations (|r| > 0.7) for follow-up
- Always note: correlation does not imply causation

## Step 6 — BigQuery Schema Queries

When you need schema information directly from BigQuery:

```sql
-- List columns and types for a table
SELECT column_name, data_type, is_nullable
FROM `project.dataset.INFORMATION_SCHEMA.COLUMNS`
WHERE table_name = 'my_table'
ORDER BY ordinal_position;

-- Count rows in all tables in a dataset
SELECT table_id, row_count, size_bytes, last_modified_time
FROM `project.dataset.__TABLES__`
ORDER BY row_count DESC;

-- Check for recent activity (timeliness)
SELECT MAX(created_at) AS latest_record, COUNT(*) AS total_rows
FROM `project.dataset.my_table`;
```

## Step 7 — Output Format

Produce a structured summary:

```
## Data Profile: <table_name>

### Overview
- Rows: <N> (sampled from <M> total if large table)
- Columns: <N> (<breakdown: X dimensions, Y metrics, Z dates, W IDs>)
- Grain: one row per ___
- Date range: <min> to <max>

### Column Quality
| Column | Type | Null % | Issues |
|--------|------|--------|--------|
| ...    | ...  | ...    | ...    |

### Data Quality Issues
[flagged issues with severity: INFO / WARN / ALERT]

### Recommended Explorations
1. ...
2. ...
3. ...
```

## Gotchas Specific to This Repo

- `df_describe` and `df_detect_outliers` operate on the **cached in-memory DataFrame**,
  not BigQuery directly. You must run `bq_run_query` first to populate the cache.
- For tables > 1M rows, never pull raw rows. Use `bq_profile_dataset` or write
  aggregation SQL that produces a summary DataFrame ≤ 100K rows.
- The in-memory cache is ephemeral. If you get a `[CACHE_MISS]` error, re-run the
  original `bq_run_query` with the same `cache_key` before retrying the df_* tool.
- BigQuery `__TABLES__` metadata is eventually consistent — `row_count` may lag
  a few minutes behind recent inserts. For exact counts, run `SELECT COUNT(*)`.
