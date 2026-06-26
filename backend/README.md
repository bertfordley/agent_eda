# EDA Agent — Backend

FastAPI server running a Gemini 2.0 Flash agent (via Vertex AI and the Deep Agents / LangGraph runtime). Connects to BigQuery and optionally Google Drive / Sheets. Exposes a REST + WebSocket API consumed by the [eda-agent-frontend](https://github.com/your-org/eda-agent-frontend).

---

## Prerequisites

| Tool | Minimum version | Notes |
|------|----------------|-------|
| Python | 3.11 | 3.12+ also works |
| Poetry | 1.8+ | `pip install poetry` or [official installer](https://python-poetry.org/docs/) |
| Google Cloud SDK | any recent | For `gcloud auth` — [install guide](https://cloud.google.com/sdk/docs/install) |
| A GCP project | — | With Vertex AI API enabled |
| Docker Engine | 24+ | For local Postgres (optional — required for conversation persistence) |

---

## Project layout

```
eda-agent-backend/
├── agents/
│   └── orchestrator.py   # Deep Agents executor, subagent specs, system prompt
├── config/
│   └── settings.py       # Typed env-var settings + GCP credential factory
├── tools/
│   ├── bigquery_tools.py # bq_list_datasets, bq_list_tables, bq_run_query …
│   ├── drive_tools.py    # sheet_from_url, drive_search_files …
│   ├── analysis_tools.py # df_describe, df_correlations, df_group_by …
│   ├── viz_tools.py      # chart_bar, chart_line, chart_interactive …
│   └── report_tools.py   # report_start, report_add_section, report_generate_html …
├── server.py             # FastAPI app — REST endpoints + WebSocket /chat/stream
├── main.py               # CLI REPL (poetry run eda)
├── pyproject.toml
└── .env.example
```

---

## Setup

### 1. Install dependencies

```bash
poetry install
```

Creates a `.venv/` and installs all Python dependencies including FastAPI, Deep Agents, LangChain, the BigQuery client, Matplotlib, Plotly, and Pandas.

> **WeasyPrint (PDF export) is a heavy optional dependency.** If the install fails on WeasyPrint, comment it out of `pyproject.toml` — HTML reports still work; only PDF export is affected. On Ubuntu/Debian you may need: `sudo apt install libpango-1.0-0 libpangocairo-1.0-0`. On macOS: `brew install pango`.

### 2. Configure environment

```bash
cp .env.example .env
```

Open `.env` and set the required values:

```dotenv
# ── Required ───────────────────────────────────────────────────────────────────
GCP_PROJECT_ID=your-gcp-project-id       # e.g. my-analytics-project

# ── Recommended ────────────────────────────────────────────────────────────────
BQ_DEFAULT_DATASET=your_dataset          # shorthand for unqualified table refs
GCP_REGION=us-central1                   # Vertex AI endpoint region

# ── Optional (defaults shown) ──────────────────────────────────────────────────
VERTEX_AI_MODEL=gemini-2.0-flash         # or gemini-1.5-pro, gemini-2.0-pro
VERTEX_AI_TEMPERATURE=0.0
BQ_MAX_BYTES_BILLED=10000000000          # 10 GB cost guard
AGENT_FS_BACKEND=state                   # "state" (ephemeral) or "local" (persistent)
CHARTS_DIR=./charts                      # where chart images are written
REPORTS_DIR=./reports                    # where HTML/PDF reports are written
```

### 3. Authenticate with Google Cloud

```bash
gcloud auth application-default login
```

This caches credentials at `~/.config/gcloud/application_default_credentials.json`. The server reads them automatically via Application Default Credentials — no extra config needed.

**Using a service account instead?** Place the JSON key at `./service_account.json` and set:
```dotenv
GOOGLE_APPLICATION_CREDENTIALS=./service_account.json
```

**Required IAM roles for the credential:**

| Role | Purpose |
|------|---------|
| `roles/bigquery.user` | Run queries |
| `roles/bigquery.dataViewer` | Read table data |
| `roles/aiplatform.user` | Call Vertex AI / Gemini |
| `roles/drive.readonly` | *(optional)* Google Drive tool |

### 4. Google Drive / Sheets OAuth (optional)

The Drive tools use OAuth 2.0 so the agent can read Sheets and files on the user's behalf. Skip this if you only need BigQuery.

1. In the [Google Cloud Console](https://console.cloud.google.com/apis/credentials), create an **OAuth 2.0 Client ID** (Desktop app type).
2. Download the JSON and save it as `./oauth_client_secrets.json`.
3. On the first Drive tool call, a browser window opens for consent. The token is then cached at `./oauth_token.json`.

### 5. Checkpoint database (optional — enables conversation persistence)

Conversation memory is stored in Postgres via LangGraph's checkpointer. Without it, each WebSocket connection is single-turn (the current default). To enable:

```bash
# Start the local Postgres container (data persists across restarts via Docker volume)
docker compose up -d

# Verify it's healthy
docker compose ps

# Run the migration once (creates checkpoint tables — idempotent)
poetry run init-checkpoints
```

Set these variables in `.env` (matching the defaults in `docker-compose.yml`):

```dotenv
POSTGRES_USER=eda
POSTGRES_PASSWORD=eda
POSTGRES_DB=eda_checkpoints
CHECKPOINT_DB_URI=postgresql://eda:eda@localhost:5432/eda_checkpoints
CHECKPOINT_ENCRYPTION_KEY=<output of: openssl rand -base64 32>
```

**Encryption is mandatory when `CHECKPOINT_DB_URI` is set** — the server refuses to start without a valid key (conversation history can contain discussion of regulated data).

```bash
# Stop the container (data preserved in the Docker volume)
docker compose down

# Stop and wipe all checkpoint data
docker compose down -v
```

**GCP deployment:** set `CHECKPOINT_DB_URI` to your Cloud SQL connection string — the same variable, no code change needed. The Postgres major version in `docker-compose.yml` is pinned to 16 to match the intended Cloud SQL version; keep them in lockstep when upgrading.

#### Checkpoint pruning (required before sustained traffic)

LangGraph writes one row per graph step (~15–30 rows per multi-step turn). Without pruning, the checkpoint table grows unboundedly. Run the pruning script as a scheduled job:

```bash
# Preview — shows how many rows would be deleted, no changes made
poetry run prune-checkpoints --dry-run

# Prune (keeps the most recent 20 checkpoints per thread — the default)
poetry run prune-checkpoints

# Stricter retention
poetry run prune-checkpoints --keep-last 10
```

**Scheduling:**

- **Locally (cron):** add to crontab — e.g. daily at 2 AM:
  ```
  0 2 * * * cd /path/to/backend && poetry run prune-checkpoints
  ```
- **GCP (Cloud Scheduler):** create a Cloud Run Job that runs the Docker image with `CMD ["poetry", "run", "prune-checkpoints"]`, then trigger it daily with Cloud Scheduler.

---

## Running

### API server (used by the frontend)

```bash
poetry run uvicorn server:app --reload --port 8000
```

Verify it's running:
```bash
curl http://localhost:8000/health
# {"status": "ok", "model": "gemini-2.0-flash", "fs_backend": "state"}
```

### CLI REPL (useful for testing without the frontend)

```bash
poetry run eda
```

---

## API reference

All endpoints are on `http://localhost:8000`.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Returns `{status, model, fs_backend}` |
| `POST` | `/chat` | Single-turn, non-streaming. Body: `{message: string}`. Returns `{reply: string}` |
| `WS` | `/chat/stream` | Streaming chat. Send `{message: string}`, receive text tokens then `{done: true}` or `{error: "..."}` |
| `GET` | `/charts` | List generated chart files: `[{name, url}]` |
| `GET` | `/charts/{filename}` | Download a chart image |
| `GET` | `/reports` | List generated report files: `[{name, url}]` |
| `GET` | `/reports/{filename}` | Download a report (HTML or PDF) |

**WebSocket protocol detail:** the server sends raw text tokens via `send_text()` and JSON control frames via `send_json()` on the same socket. Clients must attempt `JSON.parse()` on every message and fall back to treating the payload as a literal text token if parsing fails.

---

## Architecture

```
FastAPI server (server.py)
│
└─ Deep Agents executor (agents/orchestrator.py)
   │  LangGraph runtime
   │  Gemini 2.0 Flash via Vertex AI
   │
   ├─ Tools (all registered in tools/__init__.py → ALL_TOOLS)
   │   ├─ bigquery_tools    bq_list_datasets, bq_list_tables,
   │   │                    bq_describe_table, bq_run_query, bq_profile_dataset
   │   ├─ drive_tools       sheet_from_url, drive_search_files,
   │   │                    drive_read_file, doc_to_text
   │   ├─ analysis_tools    df_describe, df_correlations, df_group_by,
   │   │                    df_time_series, df_compare, df_value_counts
   │   ├─ viz_tools         chart_bar, chart_line, chart_scatter,
   │   │                    chart_histogram, chart_heatmap, chart_interactive
   │   └─ report_tools      report_start, report_add_section, report_add_chart,
   │                        report_generate_html, report_generate_pdf, report_to_drive
   │
   └─ Subagents (spawned on demand via Deep Agents' built-in `task` tool)
       ├─ bq_explorer    Deep multi-step BigQuery schema discovery + SQL
       └─ viz_analyst    Chart generation + report assembly
```

The server is stateless — there is no session store or conversation history. Each WebSocket message is a single-turn request to the agent. Chat history persistence is handled by the frontend (IndexedDB).

---

## Production deployment

```bash
# Multi-worker with Uvicorn
poetry run uvicorn server:app --host 0.0.0.0 --port 8000 --workers 2

# Or with Gunicorn + Uvicorn worker
poetry run gunicorn server:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

To serve the compiled frontend from the same process, add to `server.py`:
```python
from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory="../eda-agent-frontend/dist", html=True), name="frontend")
```

---

## Development

```bash
# Run tests
poetry run pytest

# Lint + format
poetry run ruff check .
poetry run ruff format .
```

### Adding a new tool

1. Add your function to the appropriate file in `tools/`, decorated with `@tool`.
2. Import and append it to `ALL_TOOLS` in `tools/__init__.py`.
3. If it belongs to a subagent, add it to the relevant `tools` list in `agents/orchestrator.py`.
4. Restart the server — tools register at startup.

---

## Troubleshooting

**"Required environment variable GCP_PROJECT_ID is not set"**
Run `cp .env.example .env` from this directory and set `GCP_PROJECT_ID`.

**"403 Access denied" from BigQuery**
Check `gcloud auth list` to confirm which account is active, then ensure it has `bigquery.user` and `bigquery.dataViewer` on the project.

**Gemini returns empty responses or "model not found"**
Confirm the Vertex AI API is enabled: [console.cloud.google.com/apis/library/aiplatform.googleapis.com](https://console.cloud.google.com/apis/library/aiplatform.googleapis.com). Also confirm `GCP_REGION` is a region where Gemini is available (`us-central1` has the broadest coverage).

**WeasyPrint install fails**
See the note in the Setup section above. Comment it out of `pyproject.toml` if you don't need PDF export.
