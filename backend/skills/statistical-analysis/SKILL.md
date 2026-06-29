---
name: statistical-analysis
description: Methodology for descriptive statistics, trend analysis, outlier detection, and hypothesis testing. Guides correct interpretation and communication of statistical results.
when_to_use: User asks about distributions, correlations, trends, seasonality, anomalies, whether a difference is significant, or wants a statistical summary of a metric.
---

# Statistical Analysis

Use this skill to apply the right statistical method and communicate results
correctly. The repo tools (`df_describe`, `df_correlations`, `df_time_series`,
`df_detect_outliers`) produce the numbers — this skill tells you what they mean
and how to present them.

## Descriptive Statistics

### Choosing the Right Measure of Center

| Situation | Use | Why |
|---|---|---|
| Symmetric distribution, no outliers | Mean | Most efficient estimator |
| Skewed distribution | Median | Robust to outliers |
| Business metrics (revenue, session length) | **Both mean and median** | The gap between them shows skew |
| Categorical data | Mode | Only option for non-numeric |

**Rule:** Always report mean and median together for any business metric. If they
diverge by more than 20%, the distribution is skewed and the mean alone is
misleading. Call this out explicitly.

### Percentiles to Report

When `df_describe` returns statistics, augment with these percentiles via SQL:

```sql
SELECT
    APPROX_QUANTILES(metric, 100)[OFFSET(1)]  AS p1,
    APPROX_QUANTILES(metric, 100)[OFFSET(5)]  AS p5,
    APPROX_QUANTILES(metric, 100)[OFFSET(25)] AS p25,
    APPROX_QUANTILES(metric, 100)[OFFSET(50)] AS p50,
    APPROX_QUANTILES(metric, 100)[OFFSET(75)] AS p75,
    APPROX_QUANTILES(metric, 100)[OFFSET(90)] AS p90,
    APPROX_QUANTILES(metric, 100)[OFFSET(95)] AS p95,
    APPROX_QUANTILES(metric, 100)[OFFSET(99)] AS p99
FROM `project.dataset.table`;
```

Example narrative: "The median session duration is 4.2 minutes, but the top 10%
of users spend over 22 minutes — pulling the mean up to 7.8 minutes."

### Characterising Distributions

From `df_describe` output, identify the distribution shape:
- **Normal**: mean ≈ median, IQR roughly symmetric around median
- **Right-skewed**: mean > median, large gap between p75 and p99 (common for revenue)
- **Left-skewed**: mean < median (uncommon; rare in business data)
- **Bimodal**: two separate clusters visible in `chart_histogram` output — segment
  and analyze each population separately
- **Power law**: p50 is very low, p99 is very high — use median, not mean

## Trend Analysis

### Step-by-step

1. Run `df_time_series(date_column, value_column, freq="W")` or `"ME"` for monthly.
2. Look for sustained directional movement (trend), repeating patterns (seasonality),
   and sudden level shifts (change points).
3. For period-over-period comparison, write SQL directly:

```sql
WITH weekly AS (
    SELECT
        DATE_TRUNC(event_date, WEEK) AS week,
        SUM(metric) AS value
    FROM `project.dataset.table`
    GROUP BY week
)
SELECT
    week,
    value,
    LAG(value, 1) OVER (ORDER BY week) AS prior_week,
    ROUND(100.0 * (value - LAG(value, 1) OVER (ORDER BY week))
          / NULLIF(LAG(value, 1) OVER (ORDER BY week), 0), 1) AS wow_pct
FROM weekly
ORDER BY week DESC;
```

4. Visualise with `chart_line` (PNG) or `chart_interactive(chart_type="line")` for
   final deliverables.

### Seasonality

When comparing periods, always account for seasonality:
- Use year-over-year (YoY) for seasonal businesses
- Use same-day-last-week for daily data with weekly cycles
- Never compare December to November and call it a trend

### Communicating Uncertainty

Never give a point forecast. Always give a range:
- Good: "We expect 10K–12K signups next month based on the 3-month trend"
- Bad: "We will get 11,234 signups next month"

## Outlier Detection

The repo has `df_detect_outliers` (IQR method). Use it as the first pass. Then:

1. **Investigate** every flagged outlier before removing it. Ask: data error,
   genuine extreme value, or a different population?
2. **Data errors** (negative ages, 1970 timestamps, 999999 placeholders): fix or
   remove and document what was done.
3. **Genuine extremes** (a $1M enterprise order in a $50-avg consumer dataset):
   keep but use median for aggregation; analyze separately if they dominate results.
4. **Different population** (enterprise vs. SMB): segment and analyze separately.

**Always document outlier decisions:**
"We excluded 47 records (0.3%) with transaction amounts >$50K, which represent
bulk enterprise orders analyzed separately."

For time-series anomaly detection, the IQR method works poorly. Instead:
```sql
-- Flag days where value deviates >2 stdev from 28-day rolling average
WITH stats AS (
    SELECT
        date,
        value,
        AVG(value) OVER (ORDER BY date ROWS BETWEEN 27 PRECEDING AND CURRENT ROW) AS rolling_avg,
        STDDEV(value) OVER (ORDER BY date ROWS BETWEEN 27 PRECEDING AND CURRENT ROW) AS rolling_std
    FROM `project.dataset.daily_metrics`
)
SELECT *, ABS(value - rolling_avg) / NULLIF(rolling_std, 0) AS z_score
FROM stats
WHERE ABS(value - rolling_avg) / NULLIF(rolling_std, 0) > 2
ORDER BY z_score DESC;
```

## Correlation Analysis

Run `df_correlations(cache_key=..., method="pearson")`.

**Interpreting results:**
- |r| > 0.7: strong correlation — worth highlighting, but investigate direction
- 0.4 < |r| < 0.7: moderate — noteworthy but don't over-claim
- |r| < 0.4: weak — mention only if the user specifically asked

**Critical rule — always state explicitly:**
"Correlation does not imply causation. X and Y move together; this could mean
X causes Y, Y causes X, or both are driven by a third variable."

**Spurious correlations are inevitable** when you run `df_correlations` across
many columns. If you tested 20 pairs and found one strong correlation, note that
multiple comparisons were run.

## Statistical Cautions

Apply these checks before presenting any statistical result:

**Simpson's Paradox:** An overall trend can reverse when you segment the data.
Always run `df_group_by` on key dimensions to confirm the aggregate finding
holds within segments.

**Survivorship Bias:** You can only analyze entities that appear in the dataset.
If analyzing active users, the churned users are missing. Ask: "Who is absent from
this data, and would their inclusion change the conclusion?"

**Ecological Fallacy:** A trend at the group level may not apply to individuals.
"Tables with higher X have higher Y" does not mean "individual rows with higher X
have higher Y."

**Small Sample Warning:** With fewer than 30 observations per group, flag results
as indicative only: "With N=12 in this segment, treat this as directional — we
lack the sample size to be confident in the exact magnitude."

**False Precision:** Round appropriately. "About 5% churn" is more honest than
"4.73% churn" if the underlying data has noise. Prefer ranges for forecasts.
