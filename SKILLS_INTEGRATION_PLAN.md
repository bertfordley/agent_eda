# Skills Integration Plan

**Purpose:** Integrate seven uploaded skill files into the agent_eda backend. This plan covers prompt changes, new SKILL.md playbooks, and one potential new tool. Read before touching any file under `agents/definitions/` or `skills/`.

**Read first:**
- `CLAUDE.md` — repo conventions and architecture overview
- `backend/agents/orchestrator.py` — agent construction, subagent definitions, skill injection
- `backend/skills/loader.py` — how SKILL.md files are discovered and injected into the system prompt
- `backend/agents/definitions/` — the three externalized agent prompts

**Golden rule for this plan:** Do not touch `server.py`, `orchestrator.py`, or any telemetry code unless a ticket explicitly says to. The active streaming migration (`IMPLEMENTATION_PLAN.md`, Phases 1–4) owns those files.

---

## How skills work in this repo (read before any ticket)

The skill system has two layers that are easy to conflate:

1. **SKILL.md playbooks** (`backend/skills/<name>/SKILL.md`) — markdown files with YAML frontmatter. The `skills/loader.py` discovers them at startup, builds a compact index (name + description + when_to_use), and appends it to the main agent's system prompt. When the agent encounters a matching request, it calls `load_skill("<name>")` to get the full step-by-step body. **Playbooks are not tools** — they are text instructions that guide the agent to use the tools it already has.

2. **Agent definition files** (`backend/agents/definitions/*.md`) — the externalized system prompts for the main agent and the two subagents. These load via `agents/loader.py`. Edits here change what the agent *knows and does by default*, not what it can load on demand.

The frontmatter schema for SKILL.md:

```yaml
---
name: <slug>              # must match the directory name
description: <one line>   # shown in the skill index in the system prompt
when_to_use: <trigger>    # the agent reads this to decide when to call load_skill()
---
```

`load_skill_index()` builds one bullet per skill from `name + description + when_to_use`. If `when_to_use` is vague, the agent will either over-trigger (load the skill for everything) or never trigger (miss the right moment). Write it as a concrete trigger condition, not a capability description.

---

## Phase 1 — Agent Prompt Enhancements

These tickets edit existing markdown files only. No new files, no Python changes. Do these first because they unblock all subsequent phases (a stronger main agent makes the new skills more useful).

---

### TICKET-101 · Absorb `analyze.md` validation + output-format guidance into `main_agent.md`

**File to edit:** `backend/agents/definitions/main_agent.md`

**What to add:** Three new sections drawn from the uploaded `analyze.md`. Do not copy the entire file — the main agent already does data retrieval and SQL; what it lacks is (a) complexity classification logic, (b) an explicit validation gate before presenting results, and (c) differentiated output format by complexity level.

**Exact additions:**

Add the following block immediately after the `━━ ANALYSIS FLOW ━━` section (after the four existing numbered steps):

```
━━ COMPLEXITY CLASSIFICATION ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Before starting any analysis, classify the request:

• QUICK — single metric, simple filter, factual lookup.
  Output: answer directly + query in a code block. Skip charts unless obvious.
• FULL — multi-dimensional, trend, comparison, or root-cause question.
  Output: lead with the key finding, then supporting tables/charts, then caveats
  and 2-3 suggested follow-up questions.
• FORMAL — comprehensive investigation ("prepare a review", "assess quality",
  "produce a report"). Output: executive summary → methodology → findings →
  caveats → recommendations. Use report_start / report_add_section.

When in doubt between QUICK and FULL, default to FULL.

━━ VALIDATE BEFORE PRESENTING ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Before returning any result to the user, run these checks mentally:
• Row count sanity — does the number of records make sense for the question?
• Null impact — could unexpected nulls be skewing the result?
• Magnitude check — are the numbers in a plausible range for this domain?
• Trend continuity — does a time series have unexpected gaps or jumps?
• Aggregation logic — do subtotals sum to totals (no double-counting)?
If any check raises a concern, investigate and flag the caveat explicitly.
Do NOT silently return suspect numbers.
```

**Gotchas:**
- The `━━` divider style must match exactly — the loader reads the file as plain text. Copy an existing divider character, do not retype it.
- Do not remove or reorder the existing `━━ ANALYSIS FLOW ━━` steps — the numbered list there is referenced in the subagent definitions and tests.
- `main_agent.md` is loaded by `agents/loader.py` at agent construction time, which is wrapped in `@lru_cache(maxsize=1)`. In development, restart the server (or call `get_agent.cache_clear()`) after editing this file to pick up changes.

**Verification:**
```bash
poetry run eda
# Enter: "how many rows are in the orders table"
# Expect: QUICK classification behavior — direct answer + SQL, no unprompted chart
# Enter: "what is driving the drop in revenue last month"
# Expect: FULL classification — leading insight, supporting data, follow-up suggestions
```

---

### TICKET-102 · Absorb BigQuery nuances + common SQL patterns into `bq_explorer.md`

**File to edit:** `backend/agents/definitions/bq_explorer.md`

**What to add:** Two new sections from the uploaded `sql-queries.md`. Drop all Snowflake, Redshift, Databricks, and PostgreSQL content — this subagent is BigQuery-only. Only bring in:
1. BigQuery-specific syntax nuances that are not already in the prompt.
2. Reusable SQL pattern templates for window functions, CTEs, funnel analysis, cohort retention, and deduplication.

**Exact additions:**

After the existing `Rules:` block, add:

```
━━ BIGQUERY SYNTAX REFERENCE ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Date/time:
  CURRENT_DATE(), CURRENT_TIMESTAMP()
  DATE_ADD(date_col, INTERVAL 7 DAY) / DATE_SUB / DATE_DIFF / TIMESTAMP_DIFF
  DATE_TRUNC(col, MONTH) / TIMESTAMP_TRUNC(col, HOUR)
  EXTRACT(YEAR FROM col) / EXTRACT(DAYOFWEEK FROM col)  -- 1=Sunday
  FORMAT_DATE('%Y-%m-%d', date_col)

Cost + performance:
  - Always filter on the partition column (usually a date) to minimise bytes scanned.
  - Use APPROX_COUNT_DISTINCT() for cardinality estimates on 100M+ row tables.
  - Never SELECT * on large tables — billing is per-byte scanned.
  - Prefer DATE_TRUNC over FORMAT_DATE in GROUP BY — it is indexable.
  - For expensive queries, add a dry-run comment explaining why the full scan
    is necessary; the cost-cap check in bq_run_query will warn first.

String matching (no ILIKE in BQ):
  LOWER(col) LIKE '%pattern%'
  REGEXP_CONTAINS(col, r'pattern')

Arrays:
  UNNEST(array_col) / ARRAY_AGG(col) / ARRAY_LENGTH(col)
  value IN UNNEST(array_col)

━━ REUSABLE SQL PATTERNS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Always use CTEs for multi-step queries — they make retry easier when a step fails:

```sql
WITH
base AS (
    SELECT ...
    FROM project.dataset.table
    WHERE partition_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
),
aggregated AS (
    SELECT dimension, SUM(metric) AS total
    FROM base
    GROUP BY dimension
)
SELECT * FROM aggregated ORDER BY total DESC LIMIT 100;
```

Window functions:
```sql
ROW_NUMBER() OVER (PARTITION BY user_id ORDER BY created_at DESC)   -- dedup / latest
RANK() OVER (PARTITION BY category ORDER BY revenue DESC)
SUM(revenue) OVER (ORDER BY date ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)  -- running total
AVG(revenue) OVER (ORDER BY date ROWS BETWEEN 6 PRECEDING AND CURRENT ROW)          -- 7-day moving avg
LAG(value, 1) OVER (PARTITION BY entity ORDER BY date)              -- prior period value
revenue / SUM(revenue) OVER () AS pct_of_total
revenue / SUM(revenue) OVER (PARTITION BY category) AS pct_of_category
```

Deduplication (keep latest record per key):
```sql
WITH ranked AS (
    SELECT *, ROW_NUMBER() OVER (PARTITION BY entity_id ORDER BY updated_at DESC) AS rn
    FROM project.dataset.table
)
SELECT * EXCEPT(rn) FROM ranked WHERE rn = 1;
```

Funnel analysis:
```sql
WITH funnel AS (
    SELECT
        user_id,
        MAX(IF(event = 'page_view',        1, 0)) AS step_1,
        MAX(IF(event = 'signup_start',     1, 0)) AS step_2,
        MAX(IF(event = 'signup_complete',  1, 0)) AS step_3,
        MAX(IF(event = 'first_purchase',   1, 0)) AS step_4
    FROM project.dataset.events
    WHERE event_date >= DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY)
    GROUP BY user_id
)
SELECT
    SUM(step_1) AS viewed,
    SUM(step_2) AS started,
    SUM(step_3) AS completed,
    SUM(step_4) AS purchased,
    ROUND(100.0 * SUM(step_2) / NULLIF(SUM(step_1), 0), 1) AS view_to_start_pct,
    ROUND(100.0 * SUM(step_3) / NULLIF(SUM(step_2), 0), 1) AS start_to_complete_pct,
    ROUND(100.0 * SUM(step_4) / NULLIF(SUM(step_3), 0), 1) AS complete_to_purchase_pct
FROM funnel;
```

Cohort retention:
```sql
WITH cohorts AS (
    SELECT user_id, DATE_TRUNC(first_activity_date, MONTH) AS cohort_month
    FROM project.dataset.users
),
activity AS (
    SELECT user_id, DATE_TRUNC(activity_date, MONTH) AS activity_month
    FROM project.dataset.user_activity
)
SELECT
    c.cohort_month,
    COUNT(DISTINCT c.user_id) AS cohort_size,
    COUNT(DISTINCT IF(a.activity_month = c.cohort_month,                               a.user_id, NULL)) AS month_0,
    COUNT(DISTINCT IF(a.activity_month = DATE_ADD(c.cohort_month, INTERVAL 1 MONTH),   a.user_id, NULL)) AS month_1,
    COUNT(DISTINCT IF(a.activity_month = DATE_ADD(c.cohort_month, INTERVAL 3 MONTH),   a.user_id, NULL)) AS month_3
FROM cohorts c
LEFT JOIN activity a USING (user_id)
GROUP BY c.cohort_month
ORDER BY c.cohort_month;
```
```

**Gotchas:**
- BigQuery uses `IF()` not `CASE WHEN ... END` for inline conditionals in MAX(IF(...)) funnel patterns — cleaner and the optimizer handles it well. Do not switch to `CASE WHEN`.
- BigQuery cohort retention uses `DATE_ADD(date, INTERVAL N MONTH)`, not `date + INTERVAL '1 month'` (that's PostgreSQL syntax). This is a common LLM mistake.
- The code block fence inside the markdown will need to use triple backticks. Make sure the outer markdown file uses fenced code blocks correctly — the loader reads the raw markdown and the agent receives it as plain text.
- `bq_explorer.md` is also loaded from `agents/loader.py` with the same `@lru_cache`. Restart the server after editing.

**Verification:**
```bash
poetry run eda
# Enter: "build a 30-day user funnel from the events table"
# Expect: bq_explorer generates SQL using the MAX(IF(...)) funnel pattern
# Enter: "show me cohort retention by signup month"
# Expect: SQL uses DATE_ADD(..., INTERVAL N MONTH) not PostgreSQL interval syntax
```

---

## Phase 2 — Replace `data-quality-audit` Skill

The existing `data-quality-audit` skill is a 5-step tool-sequencing playbook. The uploaded `explore-data.md` is a full superset: it adds column classification, completeness scoring, consistency checks, distribution pattern detection, and temporal analysis. Replace the existing skill rather than adding a second one — two "quality check" skills would confuse the agent's routing.

---

### TICKET-201 · Rename existing skill directory

```bash
cd backend/skills
mv data-quality-audit explore-data
```

The loader discovers skills by globbing `skills/*/SKILL.md`. The directory name becomes the fallback skill name if the frontmatter `name` field is absent, but the frontmatter field is authoritative. Rename the directory anyway for consistency.

**Gotcha:** If there are any test files that hardcode the string `"data-quality-audit"` (e.g., `tests/test_skills.py`), update them to `"explore-data"` in the same commit.

```bash
grep -r "data-quality-audit" backend/tests/
```

---

### TICKET-202 · Rewrite `skills/explore-data/SKILL.md`

**File to write:** `backend/skills/explore-data/SKILL.md`

This replaces the current content entirely. The source material is the uploaded `explore-data.md`, adapted for this repo. Key adaptations:

1. Replace all "if a data warehouse MCP server is connected" language with direct tool calls.
2. Remove the `CONNECTORS.md` reference.
3. Replace PostgreSQL `information_schema` schema exploration queries with BigQuery equivalents.
4. Reference the repo's actual tool names throughout.
5. Add a `when_to_use` frontmatter field.

**Full file content:**

```markdown
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
```

**Gotchas (for the developer writing this file):**
- The triple backtick fences inside the SKILL.md will be rendered as plain text by the skill loader and sent to the model as-is. The model handles nested code blocks correctly. No special escaping is needed.
- Do not add a `user-invocable: false` frontmatter field. This skill should be loadable via `load_skill("explore-data")` from the main agent.
- The `name` field must be `explore-data` (matching the directory). If they diverge, `_name_of()` in `loader.py` uses the frontmatter `name` preferentially — but keeping them consistent avoids confusion.

**Verification:**
```bash
poetry run python -c "
from skills.loader import list_skill_names, get_skill_body
print(list_skill_names())
body = get_skill_body('explore-data')
print(body[:200])
"
# Expect: ['explore-data', 'key-comparison'] (or similar — order may vary)
# Expect: first 200 chars of the new skill body
```

---

### TICKET-203 · Update `main_agent.md` skill index reference

The existing `main_agent.md` ANALYSIS FLOW section references `data-quality-audit` by name in step 3. Find and update it.

**File to edit:** `backend/agents/definitions/main_agent.md`

Find the line:
```
   its steps (e.g. comparing two datasets on a key, or auditing data quality).
```

Update the parenthetical to:
```
   its steps (e.g. explore-data for profiling a new table, key-comparison for
   reconciling two datasets, statistical-analysis for trend or distribution work).
```

This seeds the agent with concrete skill names so it learns the routing faster during a session.

**Gotcha:** Do not hardcode a specific list of all skills in the prompt — the `load_skill_index()` function already injects the full index at runtime. The parenthetical is just a few concrete examples to prime the agent.

---

## Phase 3 — Add `statistical-analysis` Skill

This is a net-new skill. The repo has the underlying tools (`df_correlations`, `df_detect_outliers`, `df_time_series`, `df_describe`) but no guidance on *when* to use them or *how to interpret the output*. This skill provides that methodology layer.

---

### TICKET-301 · Create `skills/statistical-analysis/SKILL.md`

**File to create:** `backend/skills/statistical-analysis/SKILL.md`

The source is the uploaded `statistical-analysis.md`. Adaptations needed:
1. Add YAML frontmatter with `name`, `description`, `when_to_use`.
2. Replace generic "run Python" instructions with references to the repo's actual tools.
3. Keep all statistical methodology content verbatim — it is the value here.

**Full file content:**

```markdown
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
```

**Gotchas:**
- `APPROX_QUANTILES` is BigQuery-specific. If the user is running SQL in a different warehouse (unlikely given the repo setup, but possible via a connected sheet), note the dialect limitation.
- The skill body references `df_correlations`, `df_detect_outliers`, `df_describe`, `df_time_series`, and `df_group_by` — all of these are in `ALL_TOOLS` and available to the main agent. No new tools needed.
- Do not add Python scipy/statsmodels code. The agent doesn't have a Python execution tool — it generates SQL and uses the df_* tools. Statistical methodology is applied by interpreting the df_* outputs correctly.

**Verification:**
```bash
poetry run python -c "
from skills.loader import list_skill_names, get_skill_body
names = list_skill_names()
assert 'statistical-analysis' in names, f'skill not found in {names}'
print('OK — statistical-analysis skill registered')
"
```

---

## Phase 4 — Merge Viz Skills + Update `viz_analyst`

Two uploaded files cover visualization: `data-visualization.md` (internal reference with chart selection guide, Python code patterns, design principles, accessibility checklist) and `create-viz.md` (user-facing workflow). They cover identical ground. In this repo, skills are agent-loaded playbooks — not user slash commands. Merge them into one authoritative SKILL.md and upgrade `viz_analyst.md` to use it.

---

### TICKET-401 · Create `skills/data-visualization/SKILL.md`

**File to create:** `backend/skills/data-visualization/SKILL.md`

Merge both uploaded files. Preserve the chart selection table and "when NOT to use" section from `data-visualization.md` (more complete), the code pattern section (adapted to reference `chart_*` tools, not raw matplotlib), and the design + accessibility sections. Take the step-by-step generation workflow from `create-viz.md` as the structural backbone.

**Full file content:**

```markdown
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
```

**Gotchas:**
- The repo's chart tools produce PNG files (matplotlib) or HTML files (plotly). They do NOT accept matplotlib `rcParams` or seaborn style arguments — those are baked into `viz_tools.py`. Do not instruct the agent to set `plt.style` or `sns.set_theme` in the skill body; those calls happen in the tool code.
- `chart_heatmap` does not take `x_column`/`y_column` args — it computes the correlation matrix across all numeric columns automatically. The skill body must not suggest passing those arguments.
- `chart_line` takes `y_columns` (plural, comma-separated string) — not `y_column`. This is a footgun: the agent will sometimes call it with `y_column` (singular) by analogy with the other tools. The skill body reinforces the correct parameter name.

**Verification:**
```bash
poetry run python -c "
from skills.loader import get_skill_body
body = get_skill_body('data-visualization')
assert 'chart_interactive' in body
assert 'chart_heatmap' in body
assert 'y_columns' in body  # plural — the important one
print('data-visualization skill OK')
"
```

---

### TICKET-402 · Update `viz_analyst.md` with chart selection guidance and design standards

**File to edit:** `backend/agents/definitions/viz_analyst.md`

The current viz_analyst system prompt is 5 lines with zero chart-selection guidance. The agent is told to "choose the right chart type for the data shape" but given no criteria. This produces inconsistent chart choices and missing titles.

**Replace the current content with:**

```markdown
---
name: viz_analyst
description: Specialist visualisation + report sub-agent. Use when you want charts and reports built in a separate context, or in parallel.
tools:
  - df_describe
  - chart_bar
  - chart_line
  - chart_scatter
  - chart_histogram
  - chart_heatmap
  - chart_interactive
  - report_start
  - report_add_section
  - report_add_chart
  - report_generate_html
  - report_generate_pdf
  - report_to_drive
---
You create charts and compile reports.

## Workflow

1. Call `df_describe(cache_key=...)` to confirm what data is available and
   what the column names are before calling any chart tool.
2. Choose the right chart type using the guide below.
3. Generate charts with `chart_*` tools.
4. Assemble into a report with `report_*` tools if requested.
5. Return file paths of all outputs.

Prefer `chart_interactive` for final deliverables — it produces a self-contained
HTML file that stakeholders can open without any software.

## Chart Type Selection

| What to show | Tool |
|---|---|
| Trend over time | `chart_line` |
| Category comparison or ranking | `chart_bar` (sorts descending by default) |
| Distribution | `chart_histogram` |
| Correlation between two metrics | `chart_scatter` |
| Correlation across all numeric columns | `chart_heatmap` |
| Final shareable deliverable | `chart_interactive` |

Never use pie or donut charts. Use `chart_bar` for part-to-whole comparisons.

## Parameter Rules

- `chart_line`: `y_columns` is a **comma-separated string** (not a list). For multiple
  lines: `y_columns="revenue,cost"`.
- `chart_heatmap`: does **not** take `x_column` or `y_column` — it auto-selects all
  numeric columns. Just pass `cache_key` and optionally `method` and `title`.
- `chart_bar`: `top_n` defaults to 20. Set lower for cleaner charts with few categories.
- All tools: `cache_key` defaults to `"latest"`. Always specify explicitly when
  multiple DataFrames are in use.

## Design Standards

- **Title**: Always set a descriptive `title` that states the insight:
  "Revenue grew 23% YoY" not "Revenue by Month".
- **Sorting**: `chart_bar` sorts by value descending automatically. For natural
  ordering (months, funnel stages), pre-sort in the SQL before charting.
- **Color grouping**: Only use `color_column` in `chart_scatter` when the
  grouping adds information. Keep to 3–8 distinct values max.

## Error Handling

If a `chart_*` tool returns a string starting with "Columns not found:", check
the column names against `df_describe` output and retry with the corrected name.
The tools return error strings (not exceptions) on bad input.

If `df_describe` returns `[CACHE_MISS cache_key='...']`, the DataFrame is no
longer in memory. Report this to the main agent — the main agent must re-run
the originating `bq_run_query` before re-delegating the visualization task.
```

**Gotchas:**
- The `tools:` frontmatter list in the agent definition files is parsed by `agents/loader.py` to determine which tool objects to bind to the subagent. The format must match exactly (one tool name per list item). Do not add tools to the frontmatter that are not in the existing list without also updating `agents/loader.py`'s tool binding logic.
- The `viz_analyst` gets its own isolated context window. It cannot see the main agent's conversation history or cached DataFrames. If the main agent loaded data under `cache_key="orders"`, the viz_analyst can use that key — the DataFrame cache is process-level, not agent-level — but it does not know the schema. Always instruct the main agent to pass the `cache_key` explicitly when delegating.

**Verification:**
```bash
poetry run eda
# Enter: "chart the monthly revenue trend from the orders table for the past year"
# Expect: viz_analyst is delegated to; produces a chart_line or chart_interactive
# Expect: returned title is descriptive ("Monthly Revenue Jan–Dec 2025") not auto-generated
```

---

## Phase 5 — Add `build-dashboard` Skill

This is genuinely new capability. The repo can produce individual chart PNGs and HTML reports via `report_*` tools, but has no multi-panel dashboard with KPI cards, interactive filters, and a sortable table in a single file. This skill instructs the agent to generate that HTML directly and write it to the `reports/` directory.

---

### TICKET-501 · Create `skills/build-dashboard/SKILL.md`

**File to create:** `backend/skills/build-dashboard/SKILL.md`

**Design decision — SKILL.md vs new tool:**
This plan uses the SKILL.md approach (the agent generates the HTML directly) rather than building a `dashboard_build` Python tool. Reason: the dashboard HTML template is data-driven and context-sensitive (KPI definitions vary per dataset), so generated HTML from an LLM is more flexible than a rigid Python code path. A dedicated tool can be added in a later phase if the SKILL.md approach proves brittle.

**Key adaptation from the uploaded `build-dashboard.md`:**
- Replace "Step 2: gather data from warehouse" with instructions using the repo's cached DataFrame + `df_describe`.
- Replace "save and open in browser" with writing to `backend/reports/dashboard_<uuid>.html`.
- Remove CONNECTORS.md references.
- Keep the full HTML template, CSS, Chart.js patterns, KPI card, filter, and table patterns verbatim — these are the value.

**Full file content:**

````markdown
---
name: build-dashboard
description: Generate a self-contained interactive HTML dashboard with KPI cards, Chart.js charts, dropdown filters, and a sortable data table. Opens directly in a browser.
when_to_use: User asks for a dashboard, executive overview, interactive report, or wants multiple charts with filters in one shareable file.
---

# Build Interactive Dashboard

Produce a single self-contained HTML file with KPI cards, interactive charts,
filters, and a sortable table. No server or dependencies required — send the
file to anyone.

## Step 1 — Clarify Requirements

Before building, determine:
- **Key metrics (KPIs)**: What 2–4 headline numbers go at the top?
- **Charts**: What trends or comparisons need to be visualised? (1–3 charts)
- **Filter dimensions**: What should users be able to slice by? (region, category, date range)
- **Detail table**: What row-level data should appear at the bottom?
- **Data source**: Which cache_key holds the data?

If the user didn't specify these, propose sensible defaults based on the
DataFrame schema from `df_describe(cache_key=...)` and confirm before building.

## Step 2 — Prepare the Data

Run `df_describe(cache_key=...)` to understand the DataFrame structure.

For large DataFrames (>10K rows), pre-aggregate in SQL before building the
dashboard. Embed only the aggregated data. Guidelines:

| Raw data size | Approach |
|---|---|
| <1,000 rows | Embed raw data directly |
| 1,000–10,000 rows | Embed directly; pre-aggregate for charts |
| >10,000 rows | Pre-aggregate server-side; embed only summary |
| >100,000 rows | Do not use a client-side dashboard — use `report_generate_html` instead |

## Step 3 — Generate the Dashboard HTML

Write a single self-contained HTML file to `backend/reports/dashboard_<descriptive_name>.html`.

Use this base template. Populate the `/* DATA */` section with the actual data
from the DataFrame as a JavaScript array of objects.

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>DASHBOARD_TITLE</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js@4.5.1" integrity="sha384-jb8JQMbMoBUzgWatfe6COACi2ljcDdZQ2OxczGA3bGNeWe+6DChMTBJemed7ZnvJ" crossorigin="anonymous"></script>
    <style>
        :root {
            --bg-primary: #f8f9fa; --bg-card: #ffffff; --bg-header: #1a1a2e;
            --text-primary: #212529; --text-secondary: #6c757d; --text-on-dark: #ffffff;
            --color-1: #4C72B0; --color-2: #DD8452; --color-3: #55A868;
            --color-4: #C44E52; --color-5: #8172B3; --color-6: #937860;
            --positive: #28a745; --negative: #dc3545; --gap: 16px; --radius: 8px;
        }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               background: var(--bg-primary); color: var(--text-primary); line-height: 1.5; }
        .dashboard-container { max-width: 1400px; margin: 0 auto; padding: var(--gap); }
        .dashboard-header { background: var(--bg-header); color: var(--text-on-dark);
            padding: 20px 24px; border-radius: var(--radius); margin-bottom: var(--gap);
            display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
        .dashboard-header h1 { font-size: 20px; font-weight: 600; }
        .filters { display: flex; gap: 12px; align-items: center; flex-wrap: wrap; }
        .filter-group { display: flex; align-items: center; gap: 6px; }
        .filter-group label { font-size: 12px; color: rgba(255,255,255,0.7); }
        .filter-group select, .filter-group input[type="date"] {
            padding: 6px 10px; border: 1px solid rgba(255,255,255,0.2); border-radius: 4px;
            background: rgba(255,255,255,0.1); color: var(--text-on-dark); font-size: 13px; }
        .filter-group select option { background: var(--bg-header); }
        .kpi-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: var(--gap); margin-bottom: var(--gap); }
        .kpi-card { background: var(--bg-card); border-radius: var(--radius); padding: 20px 24px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
        .kpi-label { font-size: 13px; color: var(--text-secondary); text-transform: uppercase;
            letter-spacing: 0.5px; margin-bottom: 4px; }
        .kpi-value { font-size: 28px; font-weight: 700; margin-bottom: 4px; }
        .kpi-change { font-size: 13px; font-weight: 500; }
        .kpi-change.positive { color: var(--positive); } .kpi-change.negative { color: var(--negative); }
        .chart-row { display: grid; grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
            gap: var(--gap); margin-bottom: var(--gap); }
        .chart-container { background: var(--bg-card); border-radius: var(--radius);
            padding: 20px 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }
        .chart-container h3 { font-size: 14px; font-weight: 600; margin-bottom: 16px; }
        .chart-container canvas { max-height: 300px; }
        .table-section { background: var(--bg-card); border-radius: var(--radius);
            padding: 20px 24px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); overflow-x: auto; }
        .data-table { width: 100%; border-collapse: collapse; font-size: 13px; }
        .data-table thead th { text-align: left; padding: 10px 12px; border-bottom: 2px solid #dee2e6;
            color: var(--text-secondary); font-weight: 600; font-size: 12px; text-transform: uppercase;
            letter-spacing: 0.5px; cursor: pointer; user-select: none; }
        .data-table thead th:hover { color: var(--text-primary); background: #f8f9fa; }
        .data-table tbody td { padding: 10px 12px; border-bottom: 1px solid #f0f0f0; }
        .data-table tbody tr:hover { background: #f8f9fa; }
        .dashboard-footer { text-align: right; padding: 8px 0;
            font-size: 12px; color: var(--text-secondary); }
        @media (max-width: 768px) {
            .dashboard-header { flex-direction: column; align-items: flex-start; }
            .kpi-row { grid-template-columns: repeat(2, 1fr); }
            .chart-row { grid-template-columns: 1fr; }
        }
    </style>
</head>
<body>
<div class="dashboard-container">
    <header class="dashboard-header">
        <h1>DASHBOARD_TITLE</h1>
        <div class="filters">
            <!-- Add filter-group divs here, one per filterable dimension -->
        </div>
    </header>
    <section class="kpi-row">
        <!-- Add kpi-card divs here -->
    </section>
    <section class="chart-row">
        <!-- Add chart-container divs here -->
    </section>
    <section class="table-section">
        <h3>Detail</h3>
        <div id="detail-table"></div>
    </section>
    <footer class="dashboard-footer">Data as of: DATA_DATE</footer>
</div>
<script>
    // ── DATA ──────────────────────────────────────────────────────────────────
    const RAW_DATA = [/* paste rows here as JSON objects */];

    const COLORS = ['#4C72B0','#DD8452','#55A868','#C44E52','#8172B3','#937860'];

    // ── FORMATTING ────────────────────────────────────────────────────────────
    function fmt(val, type) {
        if (val == null) return '—';
        if (type === 'currency') {
            if (Math.abs(val) >= 1e6) return '$' + (val/1e6).toFixed(1) + 'M';
            if (Math.abs(val) >= 1e3) return '$' + (val/1e3).toFixed(1) + 'K';
            return '$' + val.toFixed(0);
        }
        if (type === 'percent') return val.toFixed(1) + '%';
        if (Math.abs(val) >= 1e6) return (val/1e6).toFixed(1) + 'M';
        if (Math.abs(val) >= 1e3) return (val/1e3).toFixed(1) + 'K';
        return val.toLocaleString();
    }

    // ── DASHBOARD CLASS ───────────────────────────────────────────────────────
    class Dashboard {
        constructor(data) {
            this.raw = data;
            this.filtered = data;
            this.charts = {};
            this.sortCol = null;
            this.sortDir = 'desc';
            this.init();
        }
        init() { this.populateFilters(); this.applyFilters(); }

        populateFilters() {
            // For each filter, populate unique values from RAW_DATA:
            // this.populateSelect('filter-region', 'region');
        }
        populateSelect(id, field) {
            const sel = document.getElementById(id);
            if (!sel) return;
            [...new Set(this.raw.map(d => d[field]))].sort().forEach(v => {
                const o = document.createElement('option'); o.value = v; o.textContent = v;
                sel.appendChild(o);
            });
        }
        getFilter(id) { const el = document.getElementById(id); return el && el.value !== 'all' ? el.value : null; }

        applyFilters() {
            // Add filter predicates here, e.g.:
            // const region = this.getFilter('filter-region');
            this.filtered = this.raw.filter(row => {
                // if (region && row.region !== region) return false;
                return true;
            });
            this.renderKPIs();
            this.renderCharts();
            this.renderTable();
        }

        renderKPIs() {
            // Example: document.getElementById('kpi-total').textContent = fmt(total, 'currency');
        }

        renderCharts() {
            // Build labels + datasets from this.filtered, then call createLineChart / createBarChart
        }

        createLineChart(id, labels, datasets) {
            const ctx = document.getElementById(id).getContext('2d');
            if (this.charts[id]) this.charts[id].destroy();
            this.charts[id] = new Chart(ctx, {
                type: 'line',
                data: { labels, datasets: datasets.map((ds, i) => ({
                    label: ds.label, data: ds.data,
                    borderColor: COLORS[i % COLORS.length],
                    backgroundColor: COLORS[i % COLORS.length] + '20',
                    borderWidth: 2, tension: 0.3, pointRadius: 3
                }))},
                options: { responsive: true, maintainAspectRatio: false,
                    interaction: { mode: 'index', intersect: false },
                    plugins: { legend: { position: 'top' } },
                    scales: { x: { grid: { display: false } }, y: { beginAtZero: true } } }
            });
        }

        createBarChart(id, labels, data, opts = {}) {
            const ctx = document.getElementById(id).getContext('2d');
            if (this.charts[id]) this.charts[id].destroy();
            const horiz = opts.horizontal || labels.length > 8;
            this.charts[id] = new Chart(ctx, {
                type: 'bar',
                data: { labels, datasets: [{ label: opts.label || 'Value', data,
                    backgroundColor: COLORS.map(c => c + 'CC'), borderRadius: 4 }] },
                options: { responsive: true, maintainAspectRatio: false, indexAxis: horiz ? 'y' : 'x',
                    plugins: { legend: { display: false } },
                    scales: { x: { beginAtZero: true }, y: { beginAtZero: !horiz } } }
            });
        }

        renderTable() {
            const cols = [
                // { field: 'name', label: 'Name' },
                // { field: 'revenue', label: 'Revenue', format: 'currency' },
            ];
            if (!cols.length) return;
            const sorted = [...this.filtered].sort((a, b) => {
                if (!this.sortCol) return 0;
                const av = a[this.sortCol], bv = b[this.sortCol];
                const cmp = av < bv ? -1 : av > bv ? 1 : 0;
                return this.sortDir === 'asc' ? cmp : -cmp;
            });
            let html = '<table class="data-table"><thead><tr>';
            cols.forEach(c => {
                const arrow = this.sortCol === c.field ? (this.sortDir === 'asc' ? ' ▲' : ' ▼') : '';
                html += `<th onclick="dash.sort('${c.field}')">${c.label}${arrow}</th>`;
            });
            html += '</tr></thead><tbody>';
            sorted.slice(0, 100).forEach(row => {
                html += '<tr>' + cols.map(c => `<td>${fmt(row[c.field], c.format)}</td>`).join('') + '</tr>';
            });
            html += '</tbody></table>';
            document.getElementById('detail-table').innerHTML = html;
        }

        sort(field) {
            this.sortDir = this.sortCol === field && this.sortDir === 'desc' ? 'asc' : 'desc';
            this.sortCol = field;
            this.renderTable();
        }
    }

    const dash = new Dashboard(RAW_DATA);
    // Wire filter change handlers after construction:
    // document.getElementById('filter-region').addEventListener('change', () => dash.applyFilters());
</script>
</body>
</html>
```

## Step 4 — Populate the Template

For each part of the template, fill in:

1. **`DASHBOARD_TITLE`**: A descriptive title (e.g., "Monthly Sales Dashboard — Jan 2025")
2. **`DATA_DATE`**: `MAX(date_column)` from the data or today's date
3. **`RAW_DATA`**: The DataFrame rows as a JSON array of objects. For DataFrames
   from `bq_run_query`, serialise the result rows directly. Date values should be
   ISO strings ("2025-01-15").
4. **Filter controls**: Add one `<div class="filter-group">` per filterable dimension.
   Wire each to `dash.applyFilters()` on change and call `dash.populateSelect()` in
   `populateFilters()`.
5. **KPI cards**: Add one `<div class="kpi-card">` per headline metric.
   Compute values in `renderKPIs()` from `this.filtered`.
6. **Chart containers**: Add one `<div class="chart-container">` per chart,
   with a `<canvas id="...">`. Call `createLineChart` or `createBarChart` in
   `renderCharts()`.
7. **Table columns**: Define `cols` array in `renderTable()` matching the DataFrame fields.

## Step 5 — Save the File

Write the completed HTML to:
```
backend/reports/dashboard_<descriptive_slug>.html
```

Use the `report_to_drive` tool if the user wants to upload it to Google Drive.
Otherwise, return the local file path.

## Performance Limits

| Raw rows | Action |
|---|---|
| <1,000 | Embed directly |
| 1,000–10,000 | Embed, but aggregate for charts (only embed chart-level rollups) |
| >10,000 | Pre-aggregate in SQL; embed summary only. Note this in the dashboard footer. |
| >100,000 | Do not use this skill. Use `report_generate_html` for paginated reports. |

## Gotchas

- The Chart.js CDN link uses an SRI integrity hash. Do not change the URL or hash —
  mismatches cause the chart library to be blocked by the browser.
- `chart.destroy()` must be called before recreating a chart on the same canvas ID.
  The template's `createLineChart`/`createBarChart` methods do this automatically.
- Limit the `renderTable()` to `slice(0, 100)` rows for DOM performance. Add a
  "Showing N of M rows" count if the dataset is larger.
- JavaScript `Date` parsing from strings is timezone-ambiguous. For date-only strings
  ("2025-01-15"), parse with `new Date(str + 'T00:00:00')` to force local time zone
  and avoid off-by-one day errors.
- Do not use `localStorage` or `sessionStorage` in the dashboard — write all state
  into the `Dashboard` class instance.
````

**Verification:**
```bash
poetry run python -c "
from skills.loader import list_skill_names
names = list_skill_names()
assert 'build-dashboard' in names, f'Not found in {names}'
print('build-dashboard skill registered:', names)
"
# Then manually test:
poetry run eda
# Enter: "build me an executive dashboard of monthly revenue by region"
# Expect: agent loads build-dashboard skill, produces backend/reports/dashboard_*.html
# Open the HTML file in a browser and verify KPI cards, charts, and filter work
```

---

## Phase 6 — Regression and Integration Testing

Run these after all previous phases are complete. Do not skip — the skill loader uses `@lru_cache` and the agent construction uses `@lru_cache`, so stale state between test runs is a real risk.

---

### TICKET-601 · Verify skill loader picks up all new skills

```bash
cd backend
poetry run python -c "
from skills.loader import list_skill_names, load_skill_index
names = list_skill_names()
print('Registered skills:', names)
expected = {'explore-data', 'key-comparison', 'statistical-analysis', 'data-visualization', 'build-dashboard'}
missing = expected - set(names)
assert not missing, f'Missing skills: {missing}'
print()
print('=== Skill index (as injected into system prompt) ===')
print(load_skill_index())
"
```

**What to check in the output:**
- All five skill names appear
- Each entry in the index has a non-empty `description` and `when_to_use`
- No YAML parse errors (a frontmatter error produces a skill with empty `meta` dict)

---

### TICKET-602 · Run the existing test suite

```bash
cd backend
poetry run pytest -x -v
```

The `-x` flag stops on first failure. All tests should pass — this plan made no Python code changes. If any test references the string `"data-quality-audit"`, update it to `"explore-data"` (see TICKET-201).

---

### TICKET-603 · Smoke test via CLI REPL (manual)

```bash
cd backend
poetry run eda
```

Run these prompts in sequence and verify the expected behavior:

| Prompt | Expected behavior |
|---|---|
| "how many rows in the users table" | QUICK response — direct number + SQL, no unprompted chart |
| "explore the orders table" | Loads `explore-data` skill via `load_skill()`, runs full profiling sequence |
| "what is the correlation between spend and revenue" | Loads `statistical-analysis` skill, calls `df_correlations`, interprets result with mean/median framing |
| "chart the weekly signup trend for the past 6 months" | Calls `chart_line` or delegates to `viz_analyst`, returns file path with insight-driven title |
| "build me a sales dashboard for the board" | Loads `build-dashboard` skill, clarifies KPIs/charts/filters, generates HTML to reports/ |
| "compare this month's orders against the targets sheet [URL]" | Loads `key-comparison` skill (existing), calls `df_check_key` before `df_compare` |

---

### TICKET-604 · Verify agent definitions load without errors

```bash
cd backend
poetry run python -c "
from agents.loader import definitions_available, load_subagents, main_prompt_base
print('definitions_available:', definitions_available())
base = main_prompt_base()
assert '━━ COMPLEXITY CLASSIFICATION ━━' in base, 'TICKET-101 change missing from main_agent'
assert '━━ VALIDATE BEFORE PRESENTING ━━' in base, 'TICKET-101 validation section missing'
print('main_agent: OK')
subs = load_subagents()
bq = next(s for s in subs if s['name'] == 'bq_explorer')
assert 'APPROX_COUNT_DISTINCT' in bq['system_prompt'], 'TICKET-102 BQ nuances missing from bq_explorer'
assert 'cohort_month' in bq['system_prompt'], 'TICKET-102 cohort pattern missing from bq_explorer'
print('bq_explorer: OK')
viz = next(s for s in subs if s['name'] == 'viz_analyst')
assert 'y_columns' in viz['system_prompt'], 'TICKET-402 y_columns rule missing from viz_analyst'
print('viz_analyst: OK')
"
```

---

## Appendix — Common Pitfalls

**Cache invalidation.** Both `agents/loader.py` and `orchestrator.py` use `@lru_cache`. In development, edits to `.md` files in `agents/definitions/` or `skills/` are not picked up until the server restarts. If changes don't appear to take effect, restart the Uvicorn process.

**Frontmatter format.** The `skills/loader.py` uses `frontmatter.split_frontmatter()` (from the `python-frontmatter` or equivalent package). YAML values that contain colons (`:`) must be quoted. Test any new frontmatter with:
```bash
poetry run python -c "
from frontmatter import split_frontmatter
from pathlib import Path
meta, body = split_frontmatter(Path('backend/skills/<name>/SKILL.md').read_text())
print(meta)
"
```

**Skill name / directory mismatch.** `load_skill("<name>")` matches on the `name` frontmatter field (falling back to directory name if absent). Keep them identical. If they diverge, the agent may call `load_skill("explore-data")` and get back `None` because the frontmatter says `name: explore_data` (underscore vs hyphen).

**The `when_to_use` field drives routing.** The agent reads the compact index (one line per skill) and decides whether to call `load_skill()`. If `when_to_use` is too broad ("use for any data question"), the agent loads it for everything and wastes context. If too narrow ("use only when user says the word 'explore'"), it misses obvious cases. Test by saying the request in several natural ways and checking whether the skill gets loaded.

**BigQuery SQL in SKILL.md code blocks.** When the skill body includes SQL code blocks that will be sent to the agent as part of `load_skill()` output, make sure the SQL syntax is BigQuery-correct. The agent will copy-paste from the skill — if the template has PostgreSQL syntax, the bq_run_query call will fail. Key differences: `IF()` not `IIF()`, `DATE_ADD(date, INTERVAL N UNIT)` not `date + INTERVAL 'N unit'`, no `ILIKE` (use `LOWER(col) LIKE`).

**viz_analyst cannot access `load_skill()`.** The `load_skill` tool is in `ALL_TOOLS` which is bound to the **main agent**, not to subagents. The viz_analyst does not have `load_skill` in its tool list. Design guidance for the viz_analyst system prompt should be baked directly into `viz_analyst.md` (as done in TICKET-402), not referenced as a skill to load.
