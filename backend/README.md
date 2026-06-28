# EDA Agent — Backend

FastAPI server running a Gemini 2.0 Flash agent (via Vertex AI and the Deep Agents / LangGraph runtime). Connects to BigQuery and optionally Google Drive / Sheets. Exposes a REST + WebSocket API consumed by the React frontend.

---

## Quick answer: how do I run this without Postgres?

**Just don't set `CHECKPOINT_DB_URI`.** The server detects its absence at startup and enters **dev fallback mode** automatically — conversation memory is provided by the frontend (history is sent with each message, stored in the browser). No Docker, no database, no migration scripts needed.

The only required env var is `GCP_PROJECT_ID`.

---

## Two operating modes

### Dev fallback mode (default — no database required)

The default. Works on a laptop with no infrastructure dependencies beyond GCP access.

- `CHECKPOINT_DB_URI` is **not set**
- Conversation history is sent by the frontend on every turn and passed directly to the agent
- No server-side audit trail — suitable for local development only
- `/health` reports `"checkpoint": "disabled (dev fallback — client history, no server audit)"`

### Production mode (requires Postgres)

Activated by setting `CHECKPOINT_DB_URI`. History is stored server-side in Postgres via LangGraph's `AsyncPostgresSaver` checkpointer. Client-sent history is ignored entirely when this mode is active.

- Provides a durable, server-authoritative audit trail
- Conversation survives server restarts and frontend refreshes
- Required for regulated or production workloads
- `/health` reports `"checkpoint": "enabled"`

Switching between modes is a single env-var change — no code change, no frontend change.

---

## Prerequisites

| Tool | Minimum version | Notes |
|------|----------------|-------|
| Python | 3.11 | 3.12+ also works |
| Poetry | 1.8+ | `pip install poetry` or [official installer](https://python-poetry.org/docs/) |
| Google Cloud SDK | any recent | For `gcloud auth` — [install guide](https://cloud.google.com/sdk/docs/install) |
| A GCP project | — | With Vertex AI API enabled |
| Docker Engine | 24+ | **Production mode only** — not needed for dev fallback |

---

## Project layout

```
backend/
├── agents/
│   ├── orchestrator.py       # Deep Agents executor; loads definitions + catalog + skills + MCP tools
│   ├── loader.py             # agents/definitions/*.md → subagent specs (tool-name → callable)
│   ├── mcp_client.py         # MCP CLIENT — load remote MCP server tools (e.g. knowledge base)
│   └── definitions/          # Externalized agent specs (markdown + frontmatter)
│       ├── main_agent.md     #   main system prompt (catalog + skills appended at build)
│       ├── bq_explorer.md    #   BigQuery specialist subagent
│       └── viz_analyst.md    #   charts + reports subagent
├── config/
│   ├── settings.py           # Typed env-var settings + GCP credential factory
│   └── catalog.py            # Per-deployment data catalog: domain scope + NL schema, scope enforcement
├── skills/                   # Reusable analysis playbooks (progressive disclosure)
│   ├── loader.py             #   build the skills index; fetch a skill body
│   ├── key-comparison/SKILL.md
│   └── data-quality-audit/SKILL.md
├── persistence/
│   └── checkpointer.py       # AsyncPostgresSaver pool (production mode only)
├── telemetry/
│   ├── core.py               # Structured JSON telemetry emitter
│   └── governance.py         # Audit events (query_executed, thread_resumed, …)
├── tools/
│   ├── bigquery_tools.py     # bq_* + catalog scope enforcement (dataset allow-listing)
│   ├── drive_tools.py        # sheet_from_url, drive_search_files …
│   ├── analysis_tools.py     # df_describe, df_correlations, df_group_by …
│   ├── viz_tools.py          # chart_bar, chart_line, chart_interactive …
│   ├── report_tools.py       # report_start → report_generate_html/pdf
│   └── skill_tools.py        # load_skill — fetch a skill's full instructions on demand
├── scripts/
│   ├── init_checkpoint_db.py # One-time migration (production mode only)
│   └── prune_checkpoints.py  # Scheduled pruning (production mode only)
├── tests/
│   ├── test_sanitize_client_history.py
│   ├── test_catalog.py        # catalog parsing, scope, SQL allow-listing
│   └── test_agent_loader.py   # frontmatter, agent loader, skills loader
├── frontmatter.py            # Pure YAML-frontmatter parser (agent + skill files)
├── history.py                # Pure sanitization utility for client history
├── data_catalog.example.yaml # Template — copy to data_catalog.yaml per deployment
├── server.py                 # FastAPI app — REST + WebSocket /chat/stream
├── main.py                   # CLI REPL (poetry run eda)
├── pyproject.toml
└── .env.example
```

---

## Setup

### 1. Install dependencies

```bash
poetry install
```

> **WeasyPrint (PDF export) is a heavy optional dependency.** If the install fails, comment it out of `pyproject.toml` — HTML reports still work. On macOS: `brew install pango`. On Ubuntu/Debian: `sudo apt install libpango-1.0-0 libpangocairo-1.0-0`.

### 2. Configure environment

```bash
cp .env.example .env
```

Open `.env` and fill in the values for your target mode:

#### Dev fallback mode (minimum config)

```dotenv
# ── Required ─────────────────────────────────────────────────────────────────
GCP_PROJECT_ID=your-gcp-project-id

# ── Recommended ──────────────────────────────────────────────────────────────
BQ_DEFAULT_DATASET=your_dataset   # shorthand for unqualified table refs
GCP_REGION=us-central1            # Vertex AI endpoint region

# ── Optional (defaults shown) ─────────────────────────────────────────────────
VERTEX_AI_MODEL=gemini-2.0-flash
VERTEX_AI_TEMPERATURE=0.0
BQ_MAX_BYTES_BILLED=10000000000   # 10 GB cost guard
AGENT_FS_BACKEND=state            # "state" (ephemeral) or "local" (persistent charts/reports)
CHARTS_DIR=./charts
REPORTS_DIR=./reports

# CHECKPOINT_DB_URI is intentionally absent → dev fallback mode
```

#### Production mode (add these on top of the above)

```dotenv
CHECKPOINT_DB_URI=postgresql://eda:yourpassword@localhost:5432/eda_checkpoints
CHECKPOINT_ENCRYPTION_KEY=<output of: openssl rand -base64 32>
```

Encryption is mandatory when `CHECKPOINT_DB_URI` is set — the server refuses to start without a valid 32-byte AES-256 key. Conversation history may contain regulated data and must never be stored in plaintext.

### 3. Authenticate with Google Cloud

```bash
gcloud auth application-default login
```

Credentials are cached at `~/.config/gcloud/application_default_credentials.json` and picked up automatically via Application Default Credentials.

**Using a service account instead?**
```dotenv
GOOGLE_APPLICATION_CREDENTIALS=./service_account.json
```

**Required IAM roles:**

| Role | Purpose |
|------|---------|
| `roles/bigquery.user` | Run queries |
| `roles/bigquery.dataViewer` | Read table data |
| `roles/aiplatform.user` | Call Vertex AI / Gemini |
| `roles/drive.readonly` | *(optional)* Google Drive tool |

### 4. Google Drive / Sheets OAuth (optional)

Skip if you only need BigQuery.

1. In [Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials), create an **OAuth 2.0 Client ID** (Desktop app type).
2. Download the JSON and save it as `./oauth_client_secrets.json`.
3. On the first Drive tool call the server opens a browser for consent. Token is cached at `./oauth_token.json`.

### 5. Checkpoint database (production mode only)

Skip this section entirely for dev fallback mode.

```bash
# Start local Postgres (data persists across restarts via Docker volume)
docker compose up -d

# Verify it's healthy
docker compose ps

# Run the migration once (creates checkpoint tables — idempotent)
poetry run init-checkpoints
```

```bash
# Stop the container (data preserved)
docker compose down

# Stop and wipe all checkpoint data
docker compose down -v
```

**GCP deployment:** set `CHECKPOINT_DB_URI` to your Cloud SQL connection string — same variable, no code change.

#### Checkpoint pruning

LangGraph writes ~15–30 rows per agent turn. Run the pruning script as a scheduled job to prevent unbounded growth:

```bash
# Preview — no changes made
poetry run prune-checkpoints --dry-run

# Prune (keeps the most recent 20 checkpoints per thread — default)
poetry run prune-checkpoints

# Stricter retention
poetry run prune-checkpoints --keep-last 10
```

Scheduling (e.g. daily at 2 AM via cron):
```
0 2 * * * cd /path/to/backend && poetry run prune-checkpoints
```

---

## Running

### API server

```bash
poetry run uvicorn server:app --reload --port 8000
```

Verify startup mode:
```bash
curl http://localhost:8000/health
```

Dev fallback mode response:
```json
{
  "status": "ok",
  "model": "gemini-2.0-flash",
  "fs_backend": "state",
  "telemetry": "standard",
  "checkpoint": "disabled (dev fallback — client history, no server audit)"
}
```

Production mode response:
```json
{
  "status": "ok",
  "model": "gemini-2.0-flash",
  "fs_backend": "state",
  "telemetry": "standard",
  "checkpoint": "enabled"
}
```

### CLI REPL (quick testing without the frontend)

```bash
poetry run eda
```

Note: the CLI REPL is single-turn — it does not send a history array. For multi-turn conversations, use the frontend or the WebSocket endpoint directly.

### Tests

```bash
poetry run pytest
```

---

## API reference

All endpoints on `http://localhost:8000`.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Mode, model, telemetry level, checkpoint status |
| `POST` | `/chat` | Non-streaming. Body: `{message, thread_id?, messages?}`. Returns `{reply}` |
| `WS` | `/chat/stream` | Streaming chat (see protocol below) |
| `GET` | `/charts` | List generated chart files: `[{name, url, mtime}]` |
| `GET` | `/charts/{filename}` | Download a chart image |
| `GET` | `/reports` | List generated report files: `[{name, url, mtime}]` |
| `GET` | `/reports/{filename}` | Download a report (HTML or PDF) |

### WebSocket protocol — `/chat/stream`

**Client → server** (JSON, every turn):
```json
{
  "message": "what tables are in the sales dataset?",
  "thread_id": "abc123",
  "messages": [
    {"role": "user",      "content": "hello"},
    {"role": "assistant", "content": "Hi! What would you like to analyse?"},
    {"role": "user",      "content": "what tables are in the sales dataset?"}
  ]
}
```

| Field | Required | Description |
|-------|----------|-------------|
| `message` | Yes | The new user turn |
| `thread_id` | No | Durable conversation identity. Omit on the first turn; the server generates one and echoes it back |
| `messages` | No | Full conversation history with the new user turn as the final element. Used in dev fallback mode; silently ignored in production mode |

**Server → client** (in order):

| Frame | When |
|-------|------|
| `{"type": "thread", "thread_id": "…"}` | First turn only, when server generated the id — store it and send it back on every subsequent turn |
| `{"type": "tool_start", "tool": "…", "input": "…"}` | Before a tool call |
| `{"type": "tool_end", "tool": "…"}` | After a tool call |
| `{"type": "subagent_start", "name": "…"}` | When a subagent is spawned |
| `{"type": "subagent_end", "name": "…"}` | When a subagent completes |
| `{"type": "subagent_token", "ns": "…", "text": "…"}` | Streaming tokens from a subagent |
| `<raw string>` | Main-agent streaming text token (not JSON) |
| `{"done": true}` | Turn complete |
| `{"error": "…"}` | Turn failed |

**Parsing rule:** attempt `JSON.parse()` on every message. If the result is a plain object, inspect `frame.type` or check for `done`/`error`. If parsing fails (or the value is not an object), the payload is a raw text token. Never forward an unrecognised object frame as a token.

---

## Domain deployment — scope the agent to your data

The agent is **domain-agnostic**: each department runs its own instance pointed at
its own data. One deployment = one domain, configured by files (no code changes).

### 1. Data catalog (`data_catalog.yaml`)

Copy the template and describe your datasets in natural language:

```bash
cp data_catalog.example.yaml data_catalog.yaml
```

```yaml
domain:
  name: Sales Analytics
  description: Orders, revenue, and customers for the Sales team.
datasets:
  - id: my-project.sales            # fully-qualified project.dataset
    description: Core transactional sales data.
    tables:
      - id: my-project.sales.orders # fully-qualified project.dataset.table
        description: One row per order line.
        fields:
          - { name: order_id,   type: STRING,    description: Unique order id. }
          - { name: amount_usd, type: NUMERIC,   description: Line total in USD. }
```

The catalog does two things:

- **Scoping (security).** Only the listed datasets may be queried. Enforced
  server-side in `tools/bigquery_tools.py` — `bq_run_query` parses every table
  reference (via `sqlglot`) and rejects anything outside the catalog with a
  `[SCOPE_DENIED …]` marker. The model is never trusted to stay in bounds.
- **Context.** The descriptions are injected into the agent's system prompt so it
  understands your data without blind schema exploration.

**No catalog file → unscoped:** all datasets visible, no domain context (fine for
local poking, logged as a warning, not for real deployments). Path override:
`DATA_CATALOG_PATH`.

### 2. Agent definitions (`agents/definitions/*.md`)

The main agent and subagents are markdown files with YAML frontmatter
(`name`, `description`, `tools`) plus a prompt body. Edit them to customize a
deployment's behaviour without touching code. If the directory is removed, the
orchestrator falls back to built-in defaults. The data catalog and skills index
are appended to the main prompt automatically at build time.

### 3. Skills (`skills/<name>/SKILL.md`)

Reusable analysis playbooks (e.g. `key-comparison`, `data-quality-audit`). Only a
compact **index** sits in the prompt; when a request matches, the agent calls the
`load_skill(name)` tool to pull that skill's full step-by-step instructions on
demand (progressive disclosure). Add a skill by dropping a new `SKILL.md` in its
own folder — no code change.

### 4. Knowledge base / remote MCP tools (`MCP_SERVERS`)

The app is an **MCP client**: set `MCP_SERVERS` (a JSON list of stateless MCP
servers) and their tools are added to the agent alongside the in-process tools.
The intended first use is a knowledge base the agent queries for extra context
during analysis. Empty by default (no-op); requires the `langchain-mcp-adapters`
dependency.

```dotenv
MCP_SERVERS=[{"name":"knowledge_base","url":"https://kb.internal/mcp","transport":"streamable_http"}]
```

> **Why only the knowledge base, and not the data tools, over MCP?** The
> `bq_run_query → df_* → chart_*` pipeline shares a live in-process DataFrame
> cache that cannot cross a process boundary cheaply, so those tools stay
> in-process. Stateless context servers (like a KB) are the right fit for MCP.

---

## Architecture

```
FastAPI (server.py)
│
├─ Dev fallback (CHECKPOINT_DB_URI not set):
│    Frontend sends history → sanitize_client_history() → agent input
│    No server-side audit trail. LOCAL DEVELOPMENT ONLY.
│
└─ Production (CHECKPOINT_DB_URI set):
     AsyncPostgresSaver reads history from Postgres
     Client-sent history is ignored entirely
     AES-256-GCM encryption at rest (mandatory)

Both paths converge at:
  │
  └─ Deep Agents executor (agents/orchestrator.py)
       LangGraph runtime · Gemini 2.0 Flash via Vertex AI
       │
       ├─ Tools (tools/__init__.py → ALL_TOOLS)
       │   ├─ bigquery_tools    bq_list_datasets, bq_list_tables,
       │   │                    bq_describe_table, bq_run_query, bq_profile_dataset
       │   ├─ drive_tools       sheet_from_url, drive_search_files, drive_read_file
       │   ├─ analysis_tools    df_describe, df_correlations, df_group_by,
       │   │                    df_time_series, df_compare, df_value_counts
       │   ├─ viz_tools         chart_bar, chart_line, chart_scatter,
       │   │                    chart_histogram, chart_heatmap, chart_interactive
       │   └─ report_tools      report_start → report_add_section → report_generate_html/pdf
       │
       └─ Subagents (spawned on demand via Deep Agents' built-in `task` tool)
           ├─ bq_explorer    Deep multi-step BigQuery schema discovery + SQL
           └─ viz_analyst    Chart generation + report assembly
```

### Key identifiers

| Identifier | Scope | Keys |
|------------|-------|------|
| `session_id` | Per WebSocket connection (ephemeral, dies with the process) | In-process DataFrame cache (dev fallback); telemetry events |
| `thread_id` | Per conversation (durable, survives restarts) | LangGraph checkpointer (production); DataFrame cache (production) |

These must never be conflated.

### DataFrame cache

BigQuery results are cached in-process as Pandas DataFrames, keyed by `(cache_key, thread_id)`. In dev fallback mode the key uses `session_id` so the cache remains stable within a single WebSocket connection. DataFrames are never written to LangGraph state or checkpoints — only the string `cache_key` lives in graph state.

### Telemetry

Every significant event (turn start/end, tool calls, model requests, governance events) is emitted as one JSON line to stdout. Each line carries `session_id`, `thread_id`, `turn_id`, and a monotonic sequence number for reconstructing async interleave.

```bash
# Standard telemetry (metadata + governance events)
TELEMETRY_LEVEL=standard   # default

# Debug telemetry (also includes full model message payloads)
TELEMETRY_LEVEL=debug
```

---

## Development

```bash
# Run tests
poetry run pytest

# Lint
poetry run ruff check .

# Format
poetry run ruff format .
```

### Adding a new tool

1. Add your function to the appropriate file in `tools/`, decorated with `@tool`.
2. Import and append it to `ALL_TOOLS` in `tools/__init__.py`.
3. If it belongs to a subagent, also add it to the relevant `tools` list in `agents/orchestrator.py`.
4. Restart the server — tools register at startup.

---

## Production deployment

```bash
# Multi-worker with Uvicorn
poetry run uvicorn server:app --host 0.0.0.0 --port 8000 --workers 2

# Or with Gunicorn + Uvicorn worker
poetry run gunicorn server:app -w 2 -k uvicorn.workers.UvicornWorker --bind 0.0.0.0:8000
```

To serve the compiled frontend from the same process:
```python
# server.py
from fastapi.staticfiles import StaticFiles
app.mount("/", StaticFiles(directory="../frontend/dist", html=True), name="frontend")
```

---

## Troubleshooting

**"Required environment variable GCP_PROJECT_ID is not set"**
Run `cp .env.example .env` and fill in `GCP_PROJECT_ID`.

**"403 Access denied" from BigQuery**
Run `gcloud auth list` to confirm the active account, then check it has `roles/bigquery.user` and `roles/bigquery.dataViewer` on the project.

**Gemini returns empty responses or "model not found"**
Confirm the Vertex AI API is enabled in your project. Confirm `GCP_REGION` is a region where Gemini is available (`us-central1` has the broadest coverage).

**"CHECKPOINT_ENCRYPTION_KEY is not valid base64" at startup**
Generate a fresh key: `openssl rand -base64 32`. Paste the full output (including any trailing `=`) into `.env` as `CHECKPOINT_ENCRYPTION_KEY`.

**Agent answers ignore previous messages in dev fallback mode**
The CLI REPL and the REST `/chat` endpoint are single-turn by design. Multi-turn memory in dev fallback mode requires the frontend, which sends the history array on every turn. Using the WebSocket endpoint directly also works if you build and send the `messages` array yourself.

**DataFrame cache miss ("re-run the query") after reconnect**
Expected — DataFrames live in the server process and are lost on restart or reconnect. The agent is instructed to transparently re-run the original query; let it proceed.

**WeasyPrint install fails**
Comment out `weasyprint` in `pyproject.toml` if you don't need PDF export. HTML reports still work.
