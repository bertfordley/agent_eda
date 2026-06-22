"""
agents/orchestrator.py
─────────────────────────────────────────────────────────────────────────────
EDA Agent built on Deep Agents (LangGraph runtime).

Deep Agents ships these capabilities out of the box:
  • Planning     — `write_todos` decomposes multi-step requests.
  • Filesystem   — Large BQ results offloaded to the virtual FS.
  • Subagents    — `task` tool spawns isolated sub-agents.
  • Context mgmt — Summarisation middleware auto-compresses long sessions.

TICKET-005: recursion_limit=40 is applied to every agent.invoke /
astream_events call to cap the ReAct retry loop. GraphRecursionError is
caught at both call sites and surfaced as a clean message.

Backend options (AGENT_FS_BACKEND in .env):
  "state"  — ephemeral in LangGraph state (default)
  "local"  — persists to AGENT_WORKSPACE_DIR

Subagents:
  • bq_explorer  — BigQuery schema discovery + SQL
  • viz_analyst  — chart generation + report assembly
"""

from __future__ import annotations

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend, StateBackend
from langchain.chat_models import init_chat_model
from langgraph.errors import GraphRecursionError

from config.settings import settings
from tools import ALL_TOOLS

from tools.bigquery_tools import (
    bq_list_datasets, bq_list_tables,
    bq_describe_table, bq_run_query, bq_profile_dataset,
)
from tools.analysis_tools import df_describe, df_check_key
from tools.viz_tools import (
    chart_bar, chart_line, chart_scatter,
    chart_histogram, chart_heatmap, chart_interactive,
)
from tools.report_tools import (
    report_start, report_add_section, report_add_chart,
    report_generate_html, report_generate_pdf, report_to_drive,
)

# ── Agent step limit ──────────────────────────────────────────────────────────
# TICKET-005: cap ReAct retry loop to prevent unbounded LLM/BQ consumption.
AGENT_RECURSION_LIMIT = 40


# ── LLM ───────────────────────────────────────────────────────────────────────

def _llm():
    """Gemini 2.0 Flash via Vertex AI, using LangChain's init_chat_model."""
    return init_chat_model(
        model=f"vertex_ai/{settings.vertex_model}",
        temperature=settings.vertex_temperature,
        project=settings.gcp_project_id,
        location=settings.gcp_region,
    )


# ── Filesystem backend ────────────────────────────────────────────────────────

def _backend():
    if settings.agent_fs_backend == "local":
        return FilesystemBackend(root_dir=str(settings.agent_workspace_dir))
    return StateBackend()


# ── Subagent specs ────────────────────────────────────────────────────────────

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
        "- For tables with > 1 000 000 rows, aggregate in SQL (GROUP BY / "
        "date_trunc) before pulling results; do not request raw rows\n"
        "- Before joining two datasets, call df_check_key to verify the "
        "join column is unique in both frames\n"
        "- If a query fails, retry at most 3 times with a different approach "
        "before reporting failure to the orchestrator"
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


# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are an expert data analyst with access to BigQuery, Google Sheets,
Google Drive, and a full suite of analysis and visualisation tools.

Your job is to help users explore and understand their data through natural conversation.
Be proactive: suggest next steps, flag anomalies, and offer to generate charts or reports.

━━ DATA INGESTION ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• BigQuery: start with bq_list_datasets → bq_list_tables → bq_describe_table
  before writing SQL. Use bq_run_query with a descriptive cache_key.
• Google Sheets: if the user shares a URL, call sheet_from_url immediately.
  Ask for the tab name if the URL doesn't make it obvious.
• Drive files: use drive_search_files first to confirm the right file.

━━ ANALYSIS FLOW ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
1. After loading any data, always run df_describe to ground your understanding.
2. Use df_correlations, df_group_by, df_time_series to build findings.
3. BEFORE calling df_compare: always call df_check_key on the join column in
   BOTH DataFrames first. Only proceed with df_compare if df_check_key confirms
   the key is unique or warns of a one-to-many relationship you can explain.
4. Use df_compare when the user wants to join BQ data with a Sheet.
5. Generate charts to support key findings — tell the user the file path.

━━ LARGE TABLES ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
For tables with more than 1 000 000 rows, aggregate in SQL before pulling data.
Write GROUP BY / SUM / COUNT / date_trunc queries to produce summary results.
Do not request raw rows from large tables.

━━ REPORTS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
report_start → report_add_section (repeat) → report_add_chart (repeat)
→ report_generate_html → report_generate_pdf (optional)
→ report_to_drive (optional)

━━ SUBAGENTS ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Delegate to bq_explorer for deep multi-step schema work.
Delegate to viz_analyst when you want charts and reports built in parallel.

━━ SAFETY ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
• Never write mutating SQL — bq_run_query will reject it automatically.
• Respect the 10 GB BQ cost cap — the tool will warn before executing.
• Do not expose raw PII in responses; summarise or mask sensitive values.
• Use cache_key names that reflect the data (e.g. 'q2_revenue', 'sheet_targets').
• If a tool call fails, retry at most 3 times with a modified approach, then
  report the failure clearly rather than looping indefinitely.
"""


# ── Agent factory ─────────────────────────────────────────────────────────────

def build_agent():
    return create_deep_agent(
        model=_llm(),
        tools=ALL_TOOLS,
        system_prompt=SYSTEM_PROMPT,
        backend=_backend(),
        subagents=[BQ_EXPLORER_SUBAGENT, VIZ_ANALYST_SUBAGENT],
    )


_agent = None


def get_agent():
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent


def chat(message: str) -> str:
    """Send a message and return the agent's text reply."""
    agent = get_agent()
    # TICKET-005: enforce recursion limit; catch and surface step-limit errors.
    try:
        result = agent.invoke(
            {"messages": [{"role": "user", "content": message}]},
            config={"recursion_limit": AGENT_RECURSION_LIMIT},
        )
    except GraphRecursionError:
        return (
            "I was unable to complete the task within the allowed number of steps. "
            "Please rephrase or narrow the request — for example, ask about one "
            "specific table or metric at a time."
        )

    messages = result.get("messages", [])
    if not messages:
        return ""
    content = messages[-1].content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, str):
                parts.append(block)
            elif isinstance(block, dict) and block.get("type") == "text":
                parts.append(block.get("text", ""))
        return "".join(parts)
    return str(content)
