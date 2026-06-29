"""
agents/mcp_client.py
──────────────────────────────────────────────────────────────────────────────
MCP CLIENT wiring — load tools from remote MCP servers (e.g. a knowledge base)
and expose them as LangChain tools the Deep Agent can call alongside its
in-process tools.

Why a client, not a server: the stateful in-process tools (bq_run_query → df_* →
chart_*) share a live DataFrame cache and must stay in-process. The high-value
MCP direction is consuming STATELESS external context servers — a knowledge base
that returns small text chunks. See the plan's Part E.

Design contract:
  • No servers configured (settings.mcp_servers == []) → returns [] (no-op).
  • langchain-mcp-adapters not installed → logs a warning, returns [] (never
    breaks startup). Add the dependency to enable remote tools.
  • Connection spec per server: {"name", "url", "transport"?} (default transport
    "streamable_http"). Auth headers may be supplied via "headers".
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from typing import Any

from config.settings import settings

logger = logging.getLogger(__name__)

_DEFAULT_TRANSPORT = "streamable_http"


def _to_connections(servers: list[dict]) -> dict[str, dict]:
    """Map our config list → MultiServerMCPClient connections mapping."""
    connections: dict[str, dict] = {}
    for s in servers:
        conn: dict[str, Any] = {
            "url": s["url"],
            "transport": s.get("transport", _DEFAULT_TRANSPORT),
        }
        if s.get("headers"):
            conn["headers"] = s["headers"]
        connections[s["name"]] = conn
    return connections


def _run_coro_blocking(coro: Coroutine[Any, Any, Any]) -> Any:
    """Run an async coroutine to completion from a sync caller, whether or not an
    event loop is already running (build_agent may be invoked inside FastAPI's
    async lifespan)."""
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)  # no loop running — safe to drive one

    # A loop is already running on this thread → execute in a separate thread.
    # Timeout prevents a hung MCP server from stalling FastAPI lifespan startup.
    import concurrent.futures

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(coro)).result(timeout=30)


def load_mcp_tools() -> list:
    """Return LangChain tools discovered from the configured MCP servers.

    Always safe to call: returns [] when nothing is configured or the optional
    dependency is missing. Never raises into the agent build path.
    """
    servers = settings.mcp_servers
    if not servers:
        return []

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError:
        logger.warning(
            "MCP_SERVERS is configured but 'langchain-mcp-adapters' is not "
            "installed — remote MCP tools are disabled. Add the dependency to "
            "enable the knowledge base."
        )
        return []

    try:
        client = MultiServerMCPClient(_to_connections(servers))
        tools = _run_coro_blocking(client.get_tools())
        logger.info(
            "Loaded %d MCP tool(s) from %d server(s): %s",
            len(tools),
            len(servers),
            ", ".join(s["name"] for s in servers),
        )
        return list(tools)
    except Exception as exc:  # never break agent startup on a remote failure
        logger.warning(
            "Failed to load MCP tools (%s: %s) — continuing without them.",
            type(exc).__name__,
            exc,
        )
        return []
