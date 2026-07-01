# EDA Agent — Backend

FastAPI server running a Gemini 2.0 Flash agent (via Vertex AI and the LangGraph / Deep Agents runtime). Connects to BigQuery and optionally Google Drive / Sheets. Exposes a REST + WebSocket API consumed by the React frontend.

---

## Quickstart (dev)

The minimum to get a working server on a laptop — no Docker, no database.

```bash
# 1. Install dependencies
cd backend
poetry install

# 2. Copy env template and fill in your GCP project
cp .env.example .env
# Edit .env — set GCP_PROJECT_ID at minimum

# 3. Authenticate with GCP
gcloud auth application-default login

# 4. (Optional) scope the agent to specific datasets
cp data_catalog.example.yaml data_catalog.yaml
# Edit data_catalog.yaml — describe your domain, datasets, tables, and fields

# 5. Start the server
poetry run uvicorn server:app --reload --port 8000
```

Verify it's running:
```bash
curl http://localhost:8000/health
```

Expected response:
```json
{
  "status": "ok",
  "model": "gemini-2.0-flash",
  "checkpoint": "disabled (dev fallback — client history, no server audit)"
}
```

Then start the frontend in a separate terminal:
```bash
cd ../frontend
npm install
npm run dev   # http://localhost:5173
```

> **No data catalog?** The agent runs unscoped — all your BigQuery datasets are visible. Fine for local exploration, but always configure a catalog before pointing at real or sensitive data.

---

## How do I run tests?

```bash
# From backend/
eval "$(pyenv init -)" && PYENV_VERSION=3.11.9 python -m pytest

# Single file
eval "$(pyenv init -)" && PYENV_VERSION=3.11.9 python -m pytest tests/test_catalog.py
```

> **Why not `poetry run pytest`?** The `pyproject.toml` includes a `[[tool.poetry.source]]` entry with `priority = "primary"` (a corporate PyPI mirror). Poetry 1.2.2 doesn't support this field and aborts when resolving dependencies. `poetry install` and the server itself are fine because they only read the lock file. Tests must use the pyenv-managed Python directly.

---

## Two operating modes

### Dev fallback (default — no database)

The default. Works with no infrastructure beyond GCP access.

- `CHECKPOINT_DB_URI` is **not set**
- Conversation history is sent by the frontend on every turn and passed straight to the agent
- No server-side audit trail — local development only

### Production mode (requires Postgres)

Activated by setting `CHECKPOINT_DB_URI`. History is stored server-side in Postgres via LangGraph's `AsyncPostgresSaver`. Client-sent history is ignored entirely.

- Durable, server-authoritative audit trail
- Conversations survive server restarts and browser refreshes
- Required for regulated or production workloads
- AES-256-GCM encryption at rest is **mandatory** (server refuses to start without it)

Switching between modes is one env-var change — no code changes, no frontend changes.

---

## Prerequisites

| Tool | Minimum version | Notes |
|------|----------------|-------|
| Python | 3.11 | via pyenv recommended |
| Poetry | 1.8+ | `pip install poetry` or [official installer](https://python-poetry.org/docs/) |
| Google Cloud SDK | any recent | For `gcloud auth` — [install guide](https://cloud.google.com/sdk/docs/install) |
| GCP project | — | With Vertex AI API enabled |
| Docker Engine | 24+ | **Production mode only** |

---

## Project layout

```
backend/
├── agents/
│   ├── orchestrator.py        # Deep Agents executor; @lru_cache(maxsize=1) — restart to pick up .md changes
│   ├── loader.py              # agents/definitions/*.md → subagent specs
│   ├── mcp_client.py          # Load tools from remote MCP servers (MCP_SERVERS env var)
│   └── definitions/           # Single source of truth for agent behavior
│       ├── main_agent.md      #   Main system prompt (catalog + skills index appended at build)
│       ├── bq_explorer.md     #   BigQuery specialist subagent: BQ syntax reference, SQL patterns
│       └── viz_analyst.md     #   Charts + reports subagent: chart type selection, design rules
├── config/
│   ├── settings.py            # Typed env-var settings + GCP credential factory
│   └── catalog.py             # Data catalog: scope enforcement (sqlglot AST) + NL schema injection
├── skills/                    # Reusable analysis playbooks (progressive disclosure)
│   ├── loader.py              #   Build skills index; fetch a skill body on demand
│   ├── explore-data/          #   7-step data profile: shape, quality, distributions, patterns
│   ├── key-comparison/        #   Reconcile two datasets on a join key
│   ├── statistical-analysis/  #   Descriptive stats, trends, outliers, correlations
│   ├── data-visualization/    #   Chart type selection, design standards, generation steps
│   └── build-dashboard/       #   Self-contained interactive HTML dashboard template (Chart.js)
├── persistence/
│   ├── checkpointer.py        # AsyncPostgresSaver lifecycle (production mode only)
│   └── crypto.py              # AES-256-GCM EncryptedSerializer for checkpoint encryption
├── telemetry/
│   ├── core.py                # Structured JSON telemetry — one line per event to stdout
│   └── governance.py          # Audit events (query_executed, thread_resumed, …)
├── tools/
│   ├── __init__.py            # ALL_TOOLS list — the single registration point
│   ├── bigquery_tools.py      # bq_* tools + catalog scope enforcement
│   ├── drive_tools.py         # sheet_from_url, drive_search_files, drive_read_file
│   ├── analysis_tools.py      # df_describe, df_correlations, df_group_by, df_time_series, …
│   ├── viz_tools.py           # chart_bar, chart_line, chart_scatter, chart_heatmap, chart_interactive
│   ├── report_tools.py        # report_start → report_add_section → report_generate_html/pdf
│   └── skill_tools.py         # load_skill — fetch a skill's full instructions on demand
├── scripts/
│   ├── init_checkpoint_db.py  # One-time migration (production mode only)
│   └── prune_checkpoints.py   # Scheduled pruning (production mode only)
├── tests/
│   ├── conftest.py
│   ├── test_agent_loader.py          # frontmatter parser, loader, skills discovery
│   ├── test_bigquery_tools.py        # read-only SQL enforcement, table/dataset qualification
│   ├── test_catalog.py               # catalog parsing, scope enforcement, SQL allow-listing
│   ├── test_encrypted_serializer.py  # AES-256-GCM encrypt/decrypt, tamper detection
│   ├── test_sanitize_client_history.py
│   └── test_settings.py              # env-var parsing (bool, int, float, MCP_SERVERS JSON)
├── frontmatter.py             # Pure YAML-frontmatter parser (agent + skill files share this)
├── history.py                 # Sanitize client-supplied message history (dev fallback mode)
├── data_catalog.example.yaml  # Template — copy to data_catalog.yaml per deployment
├── server.py                  # FastAPI app — REST + WebSocket /chat/stream
├── main.py                    # CLI REPL (poetry run eda)
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
DATA_CATALOG_PATH=./data_catalog.yaml   # omit to run unscoped
MCP_SERVERS=[]                          # JSON list of {name, url} remote MCP servers
SKILL_EXEC_ENABLED=false                # allow run_skill_script to execute skill-owned scripts
SKILL_SCRIPT_TIMEOUT_SEC=30             # per-script wall-clock limit
SKILL_SCRIPT_MAX_OUTPUT_CHARS=10000     # cap on captured stdout+stderr returned to the agent

# CHECKPOINT_DB_URI intentionally absent → dev fallback mode
```

#### Production mode (add to the above)

```dotenv
CHECKPOINT_DB_URI=postgresql://eda:yourpassword@localhost:5432/eda_checkpoints
CHECKPOINT_ENCRYPTION_KEY=<output of: openssl rand -base64 32>
```

### 3. Authenticate with Google Cloud

```bash
gcloud auth application-default login
```

**Required IAM roles:**

| Role | Purpose |
|------|---------|
| `roles/bigquery.user` | Run queries |
| `roles/bigquery.dataViewer` | Read table data |
| `roles/aiplatform.user` | Call Vertex AI / Gemini |
| `roles/drive.readonly` | *(optional)* Google Drive tools |

**Using a service account instead:**
```dotenv
GOOGLE_APPLICATION_CREDENTIALS=./service_account.json
```

### 4. Data catalog (recommended)

```bash
cp data_catalog.example.yaml data_catalog.yaml
```

Describe your domain in natural language. The catalog enforces dataset scope server-side and injects field descriptions into the agent's system prompt:

```yaml
domain:
  name: Sales Analytics
  description: Orders, revenue, and customers for the Sales team.
datasets:
  - id: my-project.sales
    description: Core transactional sales data.
    tables:
      - id: my-project.sales.orders
        description: One row per order line.
        fields:
          - { name: order_id,   type: STRING,  description: Unique order id. }
          - { name: amount_usd, type: NUMERIC, description: Line total in USD. }
```

See [Domain deployment](#domain-deployment) for the full model.

### 5. Google Drive / Sheets OAuth (optional)

1. In [Cloud Console → Credentials](https://console.cloud.google.com/apis/credentials), create an **OAuth 2.0 Client ID** (Desktop app type).
2. Download the JSON and save it as `./oauth_client_secrets.json`.
3. On the first Drive tool call the server opens a browser for consent. Token is cached at `./oauth_token.json`.

### 6. Checkpoint database (production mode only)

```bash
# Start local Postgres
docker compose up -d

# Run the migration once (idempotent)
poetry run init-checkpoints
```

**GCP:** point `CHECKPOINT_DB_URI` at your Cloud SQL connection string — no other change needed.

**Pruning** (LangGraph writes ~15–30 rows per turn):
```bash
poetry run prune-checkpoints --dry-run   # preview
poetry run prune-checkpoints             # keep last 20 per thread
poetry run prune-checkpoints --keep-last 10
```

---

## Running

### API server

```bash
poetry run uvicorn server:app --reload --port 8000
```

### CLI REPL

```bash
poetry run eda
```

Single-turn only — no history array. For multi-turn testing use the WebSocket endpoint or the frontend.

---

## Development

```bash
# Tests
eval "$(pyenv init -)" && PYENV_VERSION=3.11.9 python -m pytest

# Lint / format
poetry run ruff check .
poetry run ruff format .
```

### Adding a new tool

1. Add a plain Python function to the appropriate file in `tools/` — no `@tool` decorator needed. Give every argument and the return type a type hint, and write a docstring with an `Args:` section; deepagents derives the tool's name, schema, and description from these, and they become what the model sees.
2. Import and append it to `ALL_TOOLS` in `tools/__init__.py`.
3. If it belongs to a subagent, add the tool name to that subagent's `tools:` list in `agents/definitions/<subagent>.md` — **not** in any Python file.
4. Restart the server (`get_agent()` is `@lru_cache(maxsize=1)` — call `get_agent.cache_clear()` to reload without restarting).

### Adding a new skill

1. Create `skills/<name>/SKILL.md` with YAML frontmatter (`name`, `description`,
   `when_to_use`, and optional `kind`) and a step-by-step body.
   - `kind: playbook` (default, may be omitted) — the skill needs BigQuery/Sheets/
     Drive data; the main agent loads data first, then follows the playbook.
   - `kind: script` — the skill is self-contained and runs via
     `run_skill_script`; the main agent does NOT load data first. Use this for
     skills that ship a `scripts/` folder (see below) and don't touch the data
     warehouse.
2. Restart the server — the skills index is rebuilt automatically, grouped by `kind`.

No code changes required.

#### Skills that run a script

A skill may ship executable helpers next to its `SKILL.md`:

```
skills/<name>/
├── SKILL.md
├── assets/     # config/profile/data files the script reads
└── scripts/    # runnable scripts, e.g. evaluate_match_score.py
```

The agent runs one via the `run_skill_script(skill_name, script, args)` tool,
which is **disabled by default** — set `SKILL_EXEC_ENABLED=true` to allow it. Only
`.py` files under the skill's own `scripts/` folder may run (a resolved
path-traversal guard blocks anything else), execution is bounded by
`SKILL_SCRIPT_TIMEOUT_SEC` / `SKILL_SCRIPT_MAX_OUTPUT_CHARS`, secrets are withheld
from the child process, and every attempt is audited via the
`governance.script_executed` event.

The script runs as a **separate process**, so it **cannot read the in-process
DataFrame cache**. Pass any data it needs through `args` — e.g. the match-scoring
skill takes `--config`/`--profile` (filenames it reads from its own `assets/`,
since `cwd` is the skill folder) and `--matches` (an inline JSON string the agent
builds from the user's input per the skill's `SKILL.md`).

### Editing agent behavior

Agent prompts and subagent tool lists live entirely in `agents/definitions/*.md`. Edit the markdown, restart (or call `get_agent.cache_clear()`), and the change takes effect. Never hardcode prompts in Python.

---

## API reference

All endpoints on `http://localhost:8000`.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/health` | Mode, model, telemetry level, checkpoint status |
| `POST` | `/chat` | Non-streaming. Body: `{message, thread_id?, messages?}`. Returns `{reply}` |
| `WS` | `/chat/stream` | Streaming chat (see protocol below) |
| `GET` | `/charts` | List generated chart files |
| `GET` | `/charts/{filename}` | Download a chart image |
| `GET` | `/reports` | List generated report files |
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

| Field | Required | Notes |
|-------|----------|-------|
| `message` | Yes | The new user turn |
| `thread_id` | No | Omit on the first turn; server generates one and echoes it back |
| `messages` | No | Full history with the new turn as the last element. Used in dev fallback; ignored in production |

**Server → client:**

| Frame | When |
|-------|------|
| `{"type": "thread", "thread_id": "…"}` | First turn only |
| `{"type": "tool_start", "tool": "…", "input": "…"}` | Before each tool call |
| `{"type": "tool_end", "tool": "…"}` | After each tool call |
| `{"type": "subagent_start", "name": "…"}` | Subagent spawned |
| `{"type": "subagent_end", "name": "…"}` | Subagent complete |
| `{"type": "subagent_token", "ns": "…", "text": "…"}` | Subagent streaming token |
| `<raw string>` | Main-agent text token (not JSON) |
| `{"done": true}` | Turn complete |
| `{"error": "…"}` | Turn failed |

**Parsing rule:** `JSON.parse()` every message. If it's a plain object, inspect `frame.type` or check for `done`/`error`. If parsing fails, it's a raw text token. Never forward an unrecognised object frame as a token.

---

## Domain deployment

The agent is **domain-agnostic**: each department deploys its own instance pointed at its own data. One deployment = one domain, configured entirely by files — no code changes.

### 1. Data catalog

Controls what the agent can see and query. Two functions:

- **Scoping (security):** `bq_run_query` parses every SQL table reference (via `sqlglot` AST) and rejects anything outside the catalog with a `[SCOPE_DENIED …]` marker before the query reaches BigQuery. The model is never trusted to stay in bounds.
- **Context:** descriptions are injected into the system prompt so the agent understands your data without blind schema exploration.

Without a catalog file the agent is unscoped. This is logged as a warning and is not suitable for real deployments.

### 2. Agent definitions

`agents/definitions/*.md` — YAML frontmatter (`name`, `description`, `tools`) plus a prompt body. The catalog and skills index are appended to `main_agent.md` automatically at build time. Edit these files to customize behavior for a domain without touching Python.

### 3. Skills

`skills/<name>/SKILL.md` — analysis playbooks loaded on demand. Only a compact index sits in the system prompt; when a request matches, the agent calls `load_skill(name)` to pull the full step-by-step instructions.

| Skill | Kind | Purpose |
|-------|------|---------|
| `explore-data` | playbook | 7-step data profile: shape, quality, distributions, patterns |
| `key-comparison` | playbook | Reconcile two tables on a shared key |
| `statistical-analysis` | playbook | Descriptive stats, trends, outliers, correlations, cautions |
| `data-visualization` | playbook | Chart type selection, design standards, generation steps |
| `build-dashboard` | playbook | Self-contained interactive HTML dashboard (Chart.js template) |

### 4. Remote MCP tools

Set `MCP_SERVERS` to a JSON list of stateless MCP servers and their tools are added alongside the in-process tools. Intended use: a knowledge base the agent queries for domain context during analysis.

```dotenv
MCP_SERVERS=[{"name":"knowledge_base","url":"https://kb.internal/mcp","transport":"streamable_http"}]
```

The `bq_run_query → df_* → chart_*` pipeline shares a live in-process DataFrame cache that can't cross a process boundary, so data tools stay in-process. Stateless context servers are the right fit for MCP.

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
     AES-256-GCM encryption at rest (mandatory — persistence/crypto.py)

Both paths converge at:
  │
  └─ Deep Agents executor (agents/orchestrator.py)
       LangGraph runtime · Gemini 2.0 Flash via Vertex AI
       │
       ├─ Tools (tools/__init__.py → ALL_TOOLS)
       │   ├─ bigquery_tools    bq_list_datasets, bq_list_tables, bq_describe_table,
       │   │                    bq_run_query (+ scope enforcement), bq_profile_dataset
       │   ├─ drive_tools       sheet_from_url, drive_search_files, drive_read_file
       │   ├─ analysis_tools    df_describe, df_correlations, df_group_by,
       │   │                    df_time_series, df_detect_outliers, df_value_counts, …
       │   ├─ viz_tools         chart_bar, chart_line, chart_scatter,
       │   │                    chart_histogram, chart_heatmap, chart_interactive
       │   ├─ report_tools      report_start → report_add_section → report_generate_html/pdf
       │   └─ skill_tools       load_skill
       │
       └─ Subagents (via Deep Agents' built-in `task` tool)
           ├─ bq_explorer    Multi-step BigQuery schema discovery + SQL
           └─ viz_analyst    Chart generation + report assembly
```

### Key invariants

**`session_id` vs `thread_id`:** `session_id` is ephemeral (per WebSocket connection). `thread_id` is durable (per conversation, keys the checkpointer). Never conflate them — both appear on every telemetry event.

**DataFrame cache:** results live in-process in `tools/bigquery_tools.py:_df_cache`, keyed by `(thread_id, cache_key)`. They never enter LangGraph state or the checkpoint. Graph state holds only the `cache_key` string.

**Streaming tokens:** always use `token.text` (never `token.content`) from LangGraph's `astream()`. `.content` can be a `list[block]` on Gemini conversational turns and will crash `send_text()`.

---

## Production deployment

```bash
poetry run uvicorn server:app --host 0.0.0.0 --port 8000 --workers 2
```

---

## Troubleshooting

**"Required environment variable GCP_PROJECT_ID is not set"**
Run `cp .env.example .env` and fill in `GCP_PROJECT_ID`.

**"403 Access denied" from BigQuery**
`gcloud auth list` to confirm the active account has `roles/bigquery.user` and `roles/bigquery.dataViewer`.

**Gemini returns empty responses or "model not found"**
Confirm the Vertex AI API is enabled. Confirm `GCP_REGION` is a region where Gemini is available (`us-central1` has the broadest coverage).

**"CHECKPOINT_ENCRYPTION_KEY is not valid base64" at startup**
Generate a fresh key: `openssl rand -base64 32`. Paste the full output (including trailing `=`) into `.env`.

**Agent answers ignore previous messages in dev fallback mode**
The CLI REPL and REST `/chat` endpoint are single-turn by design. Multi-turn memory in dev fallback mode requires the frontend (which sends the full history array on every turn) or a WebSocket client that builds the `messages` array manually.

**DataFrame cache miss after server restart**
Expected — DataFrames live in the process and are lost on restart. The agent re-runs the original query transparently; let it proceed.

**`poetry run pytest` hangs or errors on dep resolution**
Use `eval "$(pyenv init -)" && PYENV_VERSION=3.11.9 python -m pytest` instead. See [How do I run tests?](#how-do-i-run-tests) above.

**WeasyPrint install fails**
Comment out `weasyprint` in `pyproject.toml`. HTML reports still work.
