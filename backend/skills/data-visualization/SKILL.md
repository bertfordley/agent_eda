---
name: data-visualization
description: Chart type selection, design principles, and step-by-step chart generation. Use when creating any visualization from query results or a DataFrame.
when_to_use: User asks for a chart, graph, plot, or visual. User wants to visualize query results, a trend, a distribution, or a comparison.
---

# Data Visualization

## Step 1 — Identify What You're Showing

Before choosing a chart type, determine the data relationship:

| What You're Showing | Best Chart Tool | Notes |
|---|---|---|
| Trend over time | `chart_line` | Default for time series |
| Comparison across categories | `chart_bar` | Horizontal preferred when >8 categories |
| Ranking | `chart_bar` | Sort descending; use `top_n` parameter |
| Distribution of values | `chart_histogram` | Reveals skew, bimodal patterns |
| Correlation between two variables | `chart_scatter` | Add `color_column` for a third dimension |
| Multiple metrics over time | `chart_line` (multi-series via `y_columns`) | Comma-separate column names |
| Correlation matrix | `chart_heatmap` | Requires ≥2 numeric columns |
| Final shareable deliverable | `chart_interactive` | Self-contained HTML; opens in any browser |

**When NOT to use certain charts:**
- **Pie/donut charts**: Not available in the tool suite — use `chart_bar` instead.
  Humans are poor at comparing angles; bar charts are always clearer.
- **3D charts**: Never. They distort perception and add no information.
- **Dual-axis**: Use with caution. If you need one, use `chart_interactive`
  with `chart_type="line"` and annotate both axes clearly in the title.

## Step 2 — Get the Data

Confirm the DataFrame is in cache:
```
df_describe(cache_key="<your_key>")
```

If you get a `[CACHE_MISS]` error, re-run the originating `bq_run_query` with the
same `cache_key` first.

Check column names in the `df_describe` output before calling any `chart_*` tool.
Column names are case-sensitive. A misspelled column name returns an error message
from the tool — not an exception — so check the output string.

## Step 3 — Generate the Chart

Call the appropriate tool. Common patterns:

**Time series (line):**
```
chart_line(x_column="date", y_columns="revenue,cost", title="Revenue vs Cost (Monthly)", cache_key="monthly")
```

**Category comparison (bar):**
```
chart_bar(x_column="product_name", y_column="total_revenue", title="Revenue by Product", top_n=15, cache_key="products")
```

**Distribution (histogram):**
```
chart_histogram(column="session_duration_seconds", bins=40, title="Distribution of Session Duration", cache_key="sessions")
```

**Correlation (scatter):**
```
chart_scatter(x_column="spend", y_column="revenue", color_column="channel", title="Revenue vs Spend by Channel", cache_key="campaigns")
```

**Correlation matrix (heatmap):**
```
chart_heatmap(cache_key="numeric_summary", method="pearson", title="Metric Correlation Heatmap")
```

**Interactive final deliverable:**
```
chart_interactive(chart_type="line", x_column="week", y_column="signups", color_column="plan_type", title="Weekly Signups by Plan Type", cache_key="signups")
```

`chart_interactive` is preferred for anything shared with stakeholders — recipients
can hover, zoom, and filter without any software installs.

## Step 4 — Apply Design Standards

**Titles — state the insight, not just the metric:**
- Good: "Revenue grew 23% YoY in Q4" (tells the reader what to see)
- Bad: "Revenue by Month" (makes the reader figure it out)

The `chart_*` tools accept a `title` parameter. Always set it. Never leave the
auto-generated `"{y_column} vs {x_column}"` as the final title.

**Sorting:**
- Bar charts: `chart_bar` already sorts by `y_column` descending. If you need
  a different sort (e.g., chronological), pre-sort in your SQL.
- Categorical dimensions with a natural order (months, funnel stages) should be
  ordered in the SQL with `ORDER BY` before plotting — the tool preserves DataFrame row order.

**Color:**
- `chart_scatter` uses `color_column` to group points — use a low-cardinality
  categorical column (3–8 groups max). More than 8 colors becomes illegible.
- `chart_heatmap` uses `coolwarm` diverging palette centered at 0 — correct for
  correlation matrices. Do not change this.

**Data labels and annotations:**
- For bar charts where the exact value matters, note the top values in your
  narrative — the PNG tools do not support annotations. For annotation support,
  use `chart_interactive`.

## Step 5 — Accessibility Checklist

Before presenting any chart:
- [ ] Title describes the insight, not just the data
- [ ] Both axes are labeled (auto-set by the tools from column names — verify they're human-readable)
- [ ] Color is not the *only* differentiator (for scatter with `color_column`, also mention the groups in text)
- [ ] Date range or data source is noted in the narrative, even if not on the chart
- [ ] Chart works in grayscale (test mentally — if it would be meaningless printed in B&W, add labels)

## Step 6 — Return Paths to the User

All `chart_*` tools return a file path string. Always surface this to the user:
"Bar chart saved to: `charts/bar_a3f2c1.png`"

For `chart_interactive`, the HTML file path is returned. Note that it is
self-contained and can be sent to anyone — it does not require the server to be running.

## Multiple Charts in One Response

When the analysis needs several charts:
1. Generate them in sequence (or delegate to `viz_analyst` for parallel generation)
2. Return all file paths in a numbered list
3. Use `report_start` → `report_add_chart` → `report_generate_html` to bundle them
   into a single shareable HTML report

## When to Delegate to viz_analyst

Delegate to `viz_analyst` when:
- The user wants 3+ charts (parallel generation is faster)
- The final output should be a compiled report rather than individual chart files
- The chart selection requires more than one iteration (viz_analyst has its own
  context window and won't pollute the main agent's working memory)

Main agent always decides WHAT to chart; viz_analyst handles HOW to generate and
assemble it.
