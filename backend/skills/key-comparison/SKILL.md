---
name: key-comparison
description: Safely compare two datasets on a shared join key, cardinality-aware.
when_to_use: User asks to compare, diff, reconcile, or find mismatches between two tables/sheets on a shared key.
---
# Key Comparison

Use this whenever two datasets must be matched on a shared key (e.g. comparing
this month's orders against a target sheet, or reconciling two source systems).

## Steps

1. **Load both sides** into the cache with distinct, descriptive cache_keys
   (e.g. `bq_run_query(sql, cache_key="orders")` and
   `sheet_from_url(url, cache_key="targets")`).

2. **Validate the key on BOTH sides first.** Call `df_check_key(key_columns, cache_key=...)`
   on the join column in *each* cached DataFrame. Confirm the key is unique and
   non-null. Never skip this — a silent many-to-many join explodes row counts.

3. **Compare.** Only after both keys check out, call
   `df_compare(key_column, cache_key_a=..., cache_key_b=..., value_columns=...)`.
   It reports join cardinality and per-column deltas.

4. **Handle non-unique keys.** If `df_check_key` shows the key is non-unique on
   both sides, the join is many-to-many and `df_compare` will refuse it above the
   row guardrail. Aggregate one side to a unique grain (GROUP BY in SQL) first.

5. **Report clearly:** rows matched, rows only in A, rows only in B, and which
   value columns changed (with magnitudes). Offer a chart of the largest deltas.
