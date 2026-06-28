---
name: data-quality-audit
description: Systematic first-pass data-quality assessment of a loaded dataset.
when_to_use: User asks "is this data clean?", wants a quality check, or has just loaded unfamiliar data.
---
# Data-Quality Audit

Run this right after loading any unfamiliar dataset, before drawing conclusions.

## Steps

1. **Profile.** Call `df_describe(cache_key=...)` for shape, dtypes, null counts,
   and basic statistics. Note any column that is entirely null or constant.

2. **Categoricals.** For each important string/category column, call
   `df_value_counts(column, cache_key=...)`. Flag unexpected categories, casing
   inconsistencies, and high-cardinality columns that should be keys.

3. **Numerics.** Call `df_detect_outliers(cache_key=...)` (IQR method). Flag
   columns with implausible outliers or out-of-range values (e.g. negative
   amounts, future dates).

4. **Keys & duplicates.** If the data has a natural identifier, run
   `df_check_key(key_columns, cache_key=...)` to confirm uniqueness and surface
   duplicate rows.

5. **Summarize** a short data-quality report: % null per column, suspect columns,
   outlier counts, and duplicate findings. Offer to chart key distributions.
