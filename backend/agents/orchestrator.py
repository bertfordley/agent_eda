"""
agents/orchestrator.py
─────────────────────────────────────────────────────────────────────────────
EDA Agent built on Deep Agents (LangGraph runtime).

TICKET-005 (prior): recursion_limit=40 caps the ReAct retry loop.
TICKET-008 (prior): model_content_error diagnostic in chat().

STREAMING MIGRATION (TICKETS 001-003):
  chat() now uses BaseMessage.text (langchain-core built-in) rather than the
  hand-rolled content_to_text() helper, which was a reimplementation of the
  same logic. server.py's streaming loop uses astream() + subgraphs=True
  (see server.py) and reads chunk.text so the str-vs-list content problem
  is handled by the framework, not by us.
"""

from __future__ import annotations

import traceback as tb

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend, StateBackend
from langchain.chat_models import init_chat_model
from langgraph.errors import GraphRecursionError

from config.settings import settings
from telemetry.core import log_event, truncate_value
from tools import ALL_TOOLS
from tools.analysis_tools import df_check_key, df_describe
from tools.bigquery_tools import (
    bq_describe_table,
    bq_list_datasets,
    bq_list_tables,
    bq_profile_dataset,
    bq_run_query,
)
from tools.report_tools import (
    report_add_chart,
    report_add_section,
    report_generate_html,
    report_generate_pdf,
    report_start,
    report_to_drive,
)
from tools.viz_tools import (
    chart_bar,
    chart_heatmap,
    chart_histogram,
    chart_interactive,
    chart_line,
    chart_scatter,
)

AGENT_RECURSION_LIMIT = 40

# Keywords that identify model-layer content/empty-payload errors from Gemini.
_CONTENT_ERROR_PATTERNS = ("must be", "empty", "Content", "parts", "contents")


def _llm():
    # The correct provider token for Vertex AI is "google_vertexai".
    # model_provider is passed explicitly (not as a "provider:model" prefix)
    # because the init_chat_model reference warns that bare "gemini..." prefix
    # inference defaults to google_vertexai *today* but "default changes in
    # next major" — the explicit kwarg locks the binding against that drift.
    return init_chat_model(
        model=settings.vertex_model,
        model_provider="google_vertexai",
        temperature=settings.vertex_temperature,
        project=settings.gcp_project_id,
        location=settings.gcp_region,
    )


def _backend():
    if settings.agent_fs_backend == "local":
        return FilesystemBackend(root_dir=str(settings.agent_workspace_dir))
    return StateBackend()


BQ_EXPLORER_SUBAGENT = {
    "name": "bq_explorer",
    "description": (
        "Specialist BigQuery sub-agent. Use for complex multi-step schema "
        "discovery and SQL work — runs in its own isolated context window."
    ),
    "system_prompt": (
        "You are a BigQuery expert. Your only job is schema discovery and SQL.\n\n"
        "Workflow:\n"
        "1. bq_list_datasets → orient yourself\n"
        "2. bq_list_tables / bq_describe_table → understand structure\n"
        "3. bq_run_query → fetch results with precise Standard SQL\n"
        "4. Return a structured summary — never raw dumps\n\n"
        "Rules:\n"
        "- Fully-qualify table refs: project.dataset.table\n"
        "- LIMIT to ≤ 1 000 rows unless told otherwise\n"
        "- No mutating SQL (INSERT/UPDATE/DELETE/DROP) — these are rejected automatically\n"
        "- Flag any columns that look like PII\n"
        "- For tables with > 1 000 000 rows, aggregate in SQL before pulling results\n"
        "- Before joining two datasets, call df_check_key first\n"
        "- If a query fails, retry at most 3 times then report failure"
    ),
    "tools": [
        bq_list_datasets, bq_list_tables,
        bq_describe_table, bq_run_query, bq_profile_dataset,
        df_check_key,
    ],
}

VIZ_ANALYST_SUBAGENT = {
    "name": "viz_analyst",
    "description": (
        "Specialist visualisation + report sub-agent. Use when you want "
        "charts and reports built in a separate context, or in parallel."
    ),
    "system_prompt": (
        "You create charts and compile reports.\n\n"
        "Workflow:\n"
        "1. Call df_describe to confirm what data is available\n"
        "2. Choose the right chart type for the data shape\n"
        "3. Generate charts with chart_* tools\n"
        "4. Assemble into a report with report_* tools\n"
        "5. Return file paths of all outputs\n\n"
        "Prefer chart_interactive for final deliverables (self-contained HTML)."
    ),
    "tools": [
        df_describe,
        chart_bar, chart_line, chart_scatter,
        chart_histogram, chart_heatmap, chart_interactive,
        report_start, report_add_section, report_add_chart,
        report_generate_html, report_generate_pdf, report_to_drive,
    ],
}

SYSTEM_PROMPT = """You are an expert data analyst with access to BigQuery, Google Sheets,
Google Drive, and a full suite of analysis and visualisation tools.

Your job is to help users explore and understand their data through natural conversation.
Be proactive: suggest next steps, flag anomalies, and offer to generate charts or reports.
You can also discuss analytical approaches, methodology, or data concepts without
retrieving data — not every question requires a tool call.

━━ DATA INGESTION ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• BigQuery: start with bq_list_datasets → bq_list_tables → bq_describe_table
  before writing SQL. Use bq_run_query with a descriptive cache_key.
• Google Sheets: if the user shares a URL, call sheet_from_url immediately.
• Drive files: use drive_search_files first to confirm the right file.

━━ ANALYSIS FLOW ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. After loading any data, always run df_describe to ground your understanding.
2. Use df_correlations, df_group_by, df_time_series to build findings.
3. BEFORE calling df_compare: always call df_check_key on the join column in
   BOTH DataFrames first.
4. Generate charts to support key findings — tell the user the file path.

━━ LARGE TABLES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
For tables with more than 1 000 000 rows, aggregate in SQL before pulling data.

━━ REPORTS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
report_start → report_add_section → report_add_chart → report_generate_html

━━ SUBAGENTS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Delegate to bq_explorer for deep multi-step schema work.
Delegate to viz_analyst when you want charts and reports built in parallel.

━━ CACHE MISSES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
If a df_* tool returns [CACHE_MISS cache_key='...'], the DataFrame is no
longer in memory (the server restarted). Transparently re-run the original
bq_run_query with the same cache_key and LIMIT, then retry the analysis —
do not tell the user the data is unavailable; just reload it silently.

━━ SAFETY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Never write mutating SQL — bq_run_query will reject it automatically.
• Respect the BQ cost cap — the tool will warn before executing.
• Do not expose raw PII in responses; summarise or mask sensitive values.
• If a tool call fails, retry at most 3 times then report failure clearly.
"""


def _compose_system_prompt(base: str) -> str:
    """Append the per-deployment data-catalog context and the skills index to a
    base prompt. Both are no-ops when unconfigured (empty catalog / no skills),
    so an undeployed/unscoped instance behaves exactly as before."""
    from config.catalog import get_catalog, render_catalog_prompt
    from skills.loader import load_skill_index

    parts = [base]
    catalog_block = render_catalog_prompt(get_catalog())
    if catalog_block:
        parts.append(catalog_block)
    skills_block = load_skill_index()
    if skills_block:
        parts.append(skills_block)
    return "\n\n".join(parts)


def build_agent(checkpointer=None):
    # checkpointer=None → single-turn mode (current default).
    # checkpointer=<AsyncPostgresSaver> → durable memory; LangGraph propagates
    # it to subgraphs automatically so bq_explorer and viz_analyst inherit it.
    #
    # Agent definition: prefer externalized markdown (agents/definitions/*.md) so
    # each deployment can customize prompts/subagents without code edits. Fall
    # back to the in-module constants below when the definitions dir is absent.
    from agents.loader import definitions_available, load_subagents, main_prompt_base
    from agents.mcp_client import load_mcp_tools

    if definitions_available():
        base_prompt = main_prompt_base()
        subagents = load_subagents()
    else:
        base_prompt = SYSTEM_PROMPT
        subagents = [BQ_EXPLORER_SUBAGENT, VIZ_ANALYST_SUBAGENT]

    # In-process tools + any remote MCP tools (e.g. a knowledge base). The latter
    # is [] unless MCP_SERVERS is configured, so this is a no-op by default.
    tools = [*ALL_TOOLS, *load_mcp_tools()]

    return create_deep_agent(
        model=_llm(),
        tools=tools,
        system_prompt=_compose_system_prompt(base_prompt),
        backend=_backend(),
        subagents=subagents,
        checkpointer=checkpointer,
    )


_agent = None


def get_agent():
    global _agent
    if _agent is None:
        # Deferred import avoids a circular import at module level and ensures
        # we read the checkpointer holder only after the lifespan has set it.
        # If called before startup (e.g. in tests), get_checkpointer() returns
        # None and the agent runs without persistence — correct for both cases.
        from persistence.checkpointer import get_checkpointer
        _agent = build_agent(checkpointer=get_checkpointer())
    return _agent


def chat(
    message: str,
    thread_id: str | None = None,
    messages: list[dict] | None = None,
) -> str:
    """Send a message and return the agent's text reply (non-streaming)."""
    agent = get_agent()
    config: dict = {"recursion_limit": AGENT_RECURSION_LIMIT}
    if thread_id:
        config["configurable"] = {"thread_id": thread_id}

    # Production path (checkpoint_enabled=True): single new user message;
    # checkpointer supplies history. Client messages ignored — server is authoritative.
    # DEV FALLBACK (checkpoint_enabled=False): pre-sanitized client history is
    # the full context. No server-side audit trail — DEV ONLY.
    # Regulated traffic MUST run with checkpoint_enabled=true.
    if settings.checkpoint_enabled or not messages:
        input_state: dict = {"messages": [{"role": "user", "content": message}]}
    else:
        input_state = {"messages": messages}  # already sanitized by server.py

    try:
        result = agent.invoke(input_state, config=config)
    except GraphRecursionError:
        return (
            "I was unable to complete the task within the allowed number of steps. "
            "Please rephrase or narrow the request — for example, ask about one "
            "specific table or metric at a time."
        )
    except Exception as exc:
        # Detect model-layer content/empty-payload errors from Gemini and emit
        # a diagnostic telemetry event so the issue is visible in logs with a
        # full traceback and the exact raising module.
        err_str = str(exc)
        if any(pat in err_str for pat in _CONTENT_ERROR_PATTERNS):
            log_event(
                "model_content_error",
                error_type=type(exc).__name__,
                error=truncate_value(err_str),
                traceback=tb.format_exc(),
                hint=(
                    "Check the preceding model_request events for "
                    "has_empty_content=true, which identifies the malformed turn."
                ),
            )
        raise

    messages = result.get("messages", [])
    if not messages:
        return ""

    # TICKET-001: use the framework's built-in .text accessor rather than the
    # hand-rolled content_to_text() helper (which was a duplicate of this logic).
    # BaseMessage.text (langchain-core >= 1.0) handles both str and list[block]
    # content and always returns a plain string.
    return messages[-1].text
