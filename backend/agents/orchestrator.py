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
from functools import lru_cache

from deepagents import create_deep_agent
from deepagents.backends import FilesystemBackend, StateBackend
from langchain.chat_models import init_chat_model
from langgraph.errors import GraphRecursionError

from config.settings import settings
from telemetry.core import log_event, truncate_value
from tools import ALL_TOOLS

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


def build_agent(checkpointer: object = None) -> object:
    # checkpointer=None → stateless mode (default). Pass an AsyncPostgresSaver
    # for durable conversation memory; LangGraph propagates it to subgraphs.
    # Agent prompts and subagent specs live in agents/definitions/*.md — edit
    # those files to customize the agent for a deployment without touching code.
    from agents.loader import load_subagents, main_prompt_base
    from agents.mcp_client import load_mcp_tools

    # In-process tools + any remote MCP tools (e.g. a knowledge base). The latter
    # is [] unless MCP_SERVERS is configured, so this is a no-op by default.
    tools = [*ALL_TOOLS, *load_mcp_tools()]

    return create_deep_agent(
        model=_llm(),
        tools=tools,
        system_prompt=_compose_system_prompt(main_prompt_base()),
        backend=_backend(),
        subagents=load_subagents(),
        checkpointer=checkpointer,
    )


@lru_cache(maxsize=1)
def get_agent() -> object:
    # Deferred import avoids circular import at module level and ensures we read
    # the checkpointer holder only after the lifespan has set it. If called
    # before startup (e.g. in tests), get_checkpointer() returns None and the
    # agent runs without persistence — correct for both cases.
    # Call get_agent.cache_clear() to force rebuild (e.g. after new checkpointer).
    from persistence.checkpointer import get_checkpointer
    return build_agent(checkpointer=get_checkpointer())


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
