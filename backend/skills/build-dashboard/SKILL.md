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
