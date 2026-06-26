"""
server.py
─────────────────────────────────────────────────────────────────────────────
FastAPI server with full telemetry instrumentation.

STREAMING MIGRATION (TICKETS 002-003):
  The WebSocket event loop has been migrated from the legacy astream_events()
  API to the LangGraph v2 astream() API with stream_mode and subgraphs=True.

  Why this matters:
    astream_events() → hands back raw .content (str OR list) → crashed with
      "TypeError: data must be str or bytes-like" on conversational turns.
    astream(stream_mode=["messages","updates"], subgraphs=True) → hands back
      StreamPart dicts; the "messages" projection yields (token, metadata)
      pairs where token.text is always a plain string (framework-normalised).
      subgraphs=True surfaces events from bq_explorer and viz_analyst so
      the UI is no longer silent during delegation.

  StreamPart shape (version="v2"):
    {"type": "messages"|"updates", "ns": (...), "data": ...}
    ns == ()                      → main agent
    ns contains "tools:<id>"      → a spawned subagent

  Telemetry continuity:
    tool_start / tool_end / model_request / model_response events are
    re-derived from the "updates" StreamPart (node-level updates) so the
    audit trail and debug diagnostics are preserved without the event-kind
    string parsing that was tied to astream_events.

Run:
    poetry run uvicorn server:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from langgraph.errors import GraphRecursionError
from pydantic import BaseModel

from agents.orchestrator import get_agent, chat as agent_chat, AGENT_RECURSION_LIMIT
from config.settings import settings
from persistence.checkpointer import open_checkpointer
from telemetry.core import (
    log_event,
    turn_span,
    turn_span_async,
    truncate_value,
    summarize_payload,
)
from tools.bigquery_tools import current_session_id, current_thread_id

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan: manages the checkpointer pool and the agent singleton.

    Startup order (when persistence is enabled):
      1. open_checkpointer() — opens the psycopg pool and sets the module-level
         holder so get_checkpointer() returns the live saver.
         AsyncConnectionPool establishes min_size connections on open, which
         serves as the connectivity check — an unreachable DB raises here, not
         at first request.
      2. get_agent() — builds the LangGraph agent with the checkpointer attached.
         After this point all get_agent() calls return the cached singleton.
      3. yield — app serves requests.

    Shutdown: the `async with open_checkpointer()` context manager closes the
    pool (draining in-flight queries) when the outer `async with` exits.
    """
    if settings.checkpoint_enabled:
        async with open_checkpointer():
            log_event("startup", checkpoint="enabled")
            get_agent()
            yield
            log_event("shutdown", checkpoint="enabled")
    else:
        # Persistence disabled — single-turn mode.
        # settings.__init__ already emitted the WARNING about this state.
        log_event("startup", checkpoint="disabled")
        get_agent()
        yield
        log_event("shutdown", checkpoint="disabled")


app = FastAPI(title="EDA Agent", version="1.0.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

_CHART_EXTENSIONS = {".png", ".html"}
_REPORT_EXTENSIONS = {".html", ".pdf"}

# Maximum client history messages accepted in dev fallback mode.
# Bounds context window usage and cost when checkpoint_enabled is False.
MAX_HISTORY_MESSAGES = 50


class ChatRequest(BaseModel):
    message: str
    thread_id: str | None = None
    messages: list | None = None


class ChatResponse(BaseModel):
    reply: str


def sanitize_client_history(raw: list[dict]) -> list[dict]:
    """
    Sanitize client-sent conversation history for use as agent input.

    DEV FALLBACK ONLY — no server-side audit trail; history lives client-side.
    Regulated traffic MUST run with checkpoint_enabled=true.

    Transformations applied:
    - Strips every field except role and content (no ids, status, artifactIds)
    - Drops turns with empty/whitespace-only content (prevents the Gemini
      empty-content error class fixed in the streaming migration)
    """
    result = []
    for msg in raw:
        role = msg.get("role", "")
        content = (msg.get("content") or "").strip()
        if not content:
            continue
        result.append({"role": role, "content": content})
    return result


def _safe_path(base_dir: Path, filename: str) -> Path:
    candidate = (base_dir / filename).resolve()
    base_resolved = base_dir.resolve()
    if not candidate.is_relative_to(base_resolved):
        raise HTTPException(400, "Invalid filename")
    return candidate


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "model": settings.vertex_model,
        "fs_backend": settings.agent_fs_backend,
        "telemetry": settings.telemetry_level if settings.telemetry_enabled else "disabled",
        "checkpoint": (
            "enabled"
            if settings.checkpoint_enabled
            else "disabled (dev fallback — client history, no server audit)"
        ),
    }


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    session_id = uuid.uuid4().hex
    thread_id = (req.thread_id or "").strip() or uuid.uuid4().hex
    sid_token = current_session_id.set(session_id)
    # Cache keying (TICKET-7): production uses thread_id (survives reconnects);
    # dev fallback uses session_id (scoped to this request only).
    cache_thread_id = thread_id if settings.checkpoint_enabled else session_id
    tid_token = current_thread_id.set(cache_thread_id)

    # Prepare sanitized history for fallback mode (TICKET-4).
    # DEV FALLBACK ONLY — ignored entirely when checkpoint_enabled is True.
    sanitized_history: list[dict] | None = None
    if not settings.checkpoint_enabled and isinstance(req.messages, list) and req.messages:
        sanitized_history = sanitize_client_history(req.messages)

    try:
        with turn_span(req.message, channel="rest"):
            reply = await asyncio.to_thread(
                agent_chat, req.message, thread_id, sanitized_history
            )
        return ChatResponse(reply=reply)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        current_session_id.reset(sid_token)
        current_thread_id.reset(tid_token)


@app.websocket("/chat/stream")
async def chat_stream(websocket: WebSocket):
    """
    Streaming chat via WebSocket.

    Client sends:  {"message": "...", "thread_id": "<optional conversation id>"}
    Server sends (in order):
      {"type": "thread",         "thread_id": "..."}  ← only if server generated it
      {"type": "tool_start",     "tool": "<name>", "input": "<summary>"}
      {"type": "tool_end",       "tool": "<name>"}
      {"type": "subagent_start", "name": "<subagent>"}
      {"type": "subagent_end",   "name": "<subagent>"}
      {"type": "subagent_token", "ns": "<tools:id>", "text": "<token>"}
      <raw text token>   (main agent tokens only, via send_text)
      {"done": true}
      {"error": "..."}

    Identity contract (MUST NOT conflate):
      session_id  — ephemeral, per-WebSocket-connection. Scopes the in-process
                    DataFrame cache and all telemetry events. Dies with the process.
      thread_id   — durable conversation identity for the LangGraph checkpointer.
                    Survives server restarts; passed to the agent via
                    config["configurable"]["thread_id"]. When persistence is
                    disabled, thread_id is still tracked but has no effect on state.

    Telemetry events emitted per turn:
      turn_started, model_request (with has_empty_content), tool_start,
      tool_end, model_response, subagent_start, subagent_end,
      turn_completed / turn_failed
    """
    await websocket.accept()
    agent = get_agent()

    # Stable session_id for this connection so all turns and the DataFrame
    # cache share the same identity in telemetry and the session-scoped store.
    session_id = uuid.uuid4().hex

    try:
        while True:
            # ── Receive and validate the incoming message ──────────────────
            try:
                raw = await websocket.receive_text()
            except WebSocketDisconnect:
                raise

            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                await websocket.send_json({
                    "error": 'Malformed request; expected {"message": "..."}'
                })
                continue

            if not isinstance(data, dict):
                await websocket.send_json({
                    "error": 'Malformed request; expected {"message": "..."}'
                })
                continue

            message = data.get("message", "")
            if not message or not isinstance(message, str) or not message.strip():
                await websocket.send_json({"error": "Empty message"})
                continue

            # thread_id scopes the durable conversation in the LangGraph checkpointer.
            # session_id (per-connection, above) scopes the ephemeral DataFrame cache
            # and telemetry. They MUST NOT be conflated: thread_id persists across
            # reconnects and server restarts; session_id dies with this process.
            thread_id = data.get("thread_id", "")
            if not isinstance(thread_id, str):
                thread_id = ""
            thread_id = thread_id.strip()
            # generated_thread_id=True means this is the first turn — skip the
            # DB resume-detection query (a thread we just minted can't have prior
            # state). generated_thread_id=False means the client sent an existing
            # id — it may be a resumed conversation, so we check the DB below.
            generated_thread_id = not thread_id
            if generated_thread_id:
                thread_id = uuid.uuid4().hex
                # Echo the generated id so the client can store it and include it
                # with every subsequent turn in this conversation.
                await websocket.send_json({"type": "thread", "thread_id": thread_id})

            # ── Parse optional client history (TICKET-2) ──────────────────
            # Always validated; used below only when checkpoint_enabled=False.
            # When checkpoint_enabled=True the field is accepted but ignored.
            client_messages_raw: list[dict] | None = None
            raw_msgs = data.get("messages")
            if raw_msgs is not None:
                msgs_valid = (
                    isinstance(raw_msgs, list)
                    and all(
                        isinstance(m, dict)
                        and m.get("role") in ("user", "assistant")
                        and isinstance(m.get("content"), str)
                        for m in raw_msgs
                    )
                    and (not raw_msgs or raw_msgs[-1].get("role") == "user")
                )
                if not msgs_valid:
                    await websocket.send_json({"error": "Malformed messages payload"})
                    continue
                # Apply cap to bound context window usage and cost.
                client_messages_raw = list(raw_msgs[-MAX_HISTORY_MESSAGES:])

            # ── Build agent input (TICKET-4) ───────────────────────────────
            # Production path (checkpoint_enabled=True): single new user message;
            # checkpointer supplies history. Client history intentionally ignored —
            # the server (checkpointer) is the authoritative source for audit.
            #
            # DEV FALLBACK (checkpoint_enabled=False): sanitized client history
            # is the full context. No server-side audit trail — DEV ONLY.
            # Regulated traffic MUST run with checkpoint_enabled=true.
            if settings.checkpoint_enabled or not client_messages_raw:
                input_state = {"messages": [{"role": "user", "content": message}]}
            else:
                input_state = {"messages": sanitize_client_history(client_messages_raw)}

            sid_token = current_session_id.set(session_id)
            # Cache keying (TICKET-7): production keys by thread_id (survives reconnects);
            # dev fallback keys by session_id (stable for this WebSocket connection only).
            cache_thread_id = thread_id if settings.checkpoint_enabled else session_id
            tid_token = current_thread_id.set(cache_thread_id)

            # Per-turn context: maps task tool_call_id -> subagent_type so that
            # subagent_end frames carry the correct subagent name.  Populated at
            # subagent spawn (model_request node), consumed at completion (tools
            # node).  Reset each turn so stale ids never bleed across turns.
            turn_ctx: dict[str, str] = {}
            # Fire at most once per turn to avoid flooding logs.
            _subagent_ns_logged = False

            try:
                # TICKET-4.3: detect whether this turn resumes an existing thread.
                # Only check the DB when the client provided a thread_id (if we
                # generated it, the thread is definitionally fresh — skip the query).
                if not generated_thread_id and settings.checkpoint_enabled:
                    from persistence.checkpointer import get_checkpointer
                    from telemetry.governance import log_thread_resumed
                    _cp = get_checkpointer()
                    if _cp is not None:
                        _prior = await _cp.aget_tuple(
                            {"configurable": {"thread_id": thread_id}}
                        )
                        if _prior is not None:
                            log_thread_resumed(thread_id=thread_id)

                async with turn_span_async(message, channel="ws"):
                    # TICKET-002: migrate from astream_events() to astream()
                    # with stream_mode=["messages","updates"] and subgraphs=True.
                    #
                    # stream_mode="messages" → (token, metadata) pairs;
                    #   token.text is always a plain string (framework-normalized
                    #   from str OR list[block] content — the exact crash was
                    #   passing a list to send_text; .text prevents that).
                    # stream_mode="updates"  → {node_name: output} dicts;
                    #   used for tool events and model-request telemetry.
                    # subgraphs=True         → surfaces events from bq_explorer
                    #   and viz_analyst so the UI sees activity during delegation
                    #   instead of going silent.
                    async for part in agent.astream(
                        input_state,
                        stream_mode=["messages", "updates"],
                        subgraphs=True,
                        version="v2",
                        config={
                            "configurable": {"thread_id": thread_id},
                            "recursion_limit": AGENT_RECURSION_LIMIT,
                        },
                    ):
                        part_type = part.get("type")
                        part_ns   = part.get("ns", ())
                        part_data = part.get("data", {})

                        # Is this event from a subagent (tools:<id> in the namespace)?
                        # Deep Agents spawns subagents via the built-in `task` tool;
                        # LangGraph places them in a "tools:<uuid>" subgraph namespace.
                        # If this assumption is wrong for the installed version, enable
                        # TELEMETRY_LEVEL=debug and look for "subagent_ns_debug" events
                        # in stdout — they show the real part_ns tuple so you can
                        # adjust the startswith() prefix below accordingly.
                        is_subagent = any(
                            s.startswith("tools:") for s in part_ns
                        )

                        # Debug: emit the raw namespace once per turn on first subagent
                        # event so the "tools:" prefix assumption can be verified.
                        if (
                            is_subagent
                            and not _subagent_ns_logged
                            and settings.telemetry_level == "debug"
                        ):
                            _subagent_ns_logged = True
                            log_event(
                                "subagent_ns_debug",
                                part_type=part_type,
                                part_ns=list(part_ns),
                            )

                        # ── TICKET-003: streaming tokens ───────────────────
                        if part_type == "messages":
                            # StreamPart["data"] for "messages" mode is a
                            # (token, metadata) tuple.
                            token, _metadata = part_data

                            # token.text is the framework's own str-vs-list
                            # normalizer — always returns a plain string.
                            # Never use token.content here; that is the raw
                            # value that crashed the old loop.
                            text = token.text if hasattr(token, "text") else ""

                            if not text:
                                continue

                            if is_subagent:
                                # Subagent tokens: send a structured frame so
                                # the frontend can show progress during the
                                # previously-silent delegation window.
                                # TICKET-1.3 adds frontend rendering.
                                #
                                # Safe fallback if "tools:" prefix doesn't match:
                                # use the last ns segment rather than raising
                                # StopIteration.
                                sub_ns = next(
                                    (s for s in part_ns if s.startswith("tools:")),
                                    part_ns[-1] if part_ns else "subagent",
                                )
                                await websocket.send_json({
                                    "type": "subagent_token",
                                    "ns": sub_ns,
                                    "text": text,
                                })
                            else:
                                # Main-agent token: raw text string so the
                                # frontend's existing streaming logic works
                                # without any client-side changes.
                                await websocket.send_text(text)

                        # ── Updates: tools, model calls, subagent lifecycle ─
                        elif part_type == "updates":
                            # part_data is {node_name: node_output}
                            for node_name, node_output in part_data.items():
                                await _handle_update_node(
                                    websocket=websocket,
                                    node_name=node_name,
                                    node_output=node_output,
                                    is_subagent=is_subagent,
                                    part_ns=part_ns,
                                    turn_ctx=turn_ctx,
                                )

                    await websocket.send_json({"done": True})

            except WebSocketDisconnect:
                raise
            except GraphRecursionError:
                # turn_span_async already emitted turn_failed.
                await websocket.send_json({
                    "error": (
                        "Agent exceeded the step limit. Please rephrase or narrow "
                        "the request — ask about one table or metric at a time."
                    )
                })
            except Exception as e:
                # turn_span_async already emitted turn_failed with traceback.
                await websocket.send_json({"error": str(e)})
            finally:
                current_session_id.reset(sid_token)
                current_thread_id.reset(tid_token)

    except WebSocketDisconnect:
        log_event("ws_disconnected")


async def _handle_update_node(
    websocket: WebSocket,
    node_name: str,
    node_output: dict,
    is_subagent: bool,
    part_ns: tuple,
    turn_ctx: dict[str, str],
) -> None:
    """
    Process one node-level update from the "updates" StreamPart.

    Derives tool_start / tool_end / model_request / model_response telemetry
    and subagent_start / subagent_end WS frames from the graph node structure,
    replacing the astream_events kind-string parsing used in the legacy loop.

    Node names emitted by Deep Agents / LangGraph:
      model_request  → the LLM was called (main agent or subagent)
      tools          → one or more tools executed
    Subagent lifecycle is tracked via task tool_calls inside model_request
    (spawn) and task ToolMessage returns inside tools (completion).

    turn_ctx maps task tool_call_id -> subagent_type so subagent_end carries
    the correct name (populated here at spawn, consumed here at completion).
    """
    messages = node_output.get("messages", []) if isinstance(node_output, dict) else []

    # ── model_request node ─────────────────────────────────────────────────
    if node_name == "model_request":
        # messages = node_output.get("messages", []) (set at top of function).
        # With astream(updates, version="v2"), the updates StreamPart carries
        # the AIMessage(s) output by this node — unlike the legacy astream_events
        # "on_chat_model_start" event, which had no messages attached and caused
        # message_count: 0.
        #
        # If message_count is still 0 after this migration, enable
        # TELEMETRY_LEVEL=debug and look for "model_request_payload_debug" events
        # to see the actual keys present in node_output for the installed
        # langgraph version. Adjust the key lookup (node_output.get("messages"))
        # to match what the debug event shows.
        if settings.telemetry_level == "debug" and not messages:
            log_event(
                "model_request_payload_debug",
                is_subagent=is_subagent,
                node_output_type=type(node_output).__name__,
                node_output_keys=(
                    list(node_output.keys()) if isinstance(node_output, dict) else None
                ),
            )

        # Track subagent spawning: a task tool_call in the main agent's
        # model_request means a subagent is about to be delegated to.
        # Store tool_call_id -> subagent_type in turn_ctx so the matching
        # ToolMessage completion can emit the correct name in subagent_end.
        if not is_subagent:
            for msg in messages:
                for tc in getattr(msg, "tool_calls", []):
                    if tc.get("name") == "task":
                        subagent_type = tc.get("args", {}).get("subagent_type", "unknown")
                        tc_id = tc.get("id", "")
                        if tc_id:
                            turn_ctx[tc_id] = subagent_type
                        await websocket.send_json({
                            "type": "subagent_start",
                            "name": subagent_type,
                        })
                        log_event("subagent_start", subagent=subagent_type)

        # Telemetry: model_request with has_empty_content diagnostic.
        # This is the key signal for diagnosing Gemini content-shape errors.
        has_empty = any(
            getattr(m, "content", None) in (None, "", [])
            for m in messages
        )

        if settings.telemetry_level == "debug":
            msg_list = []
            for m in messages:
                content = getattr(m, "content", None)
                msg_list.append({
                    "role": getattr(m, "type", "unknown"),
                    # Use .text for safety; fall back to str(content)
                    "content": truncate_value(
                        m.text if hasattr(m, "text") else str(content or "")
                    ),
                    "has_tool_calls": bool(getattr(m, "tool_calls", None)),
                })
            log_event(
                "model_request",
                is_subagent=is_subagent,
                message_count=len(messages),
                has_empty_content=has_empty,
                messages=msg_list,
            )
        else:
            log_event(
                "model_request",
                is_subagent=is_subagent,
                message_count=len(messages),
                has_empty_content=has_empty,
            )

        # model_response: emit finish_reason and token usage from the complete
        # AIMessage that appears in the updates stream.  Individual tokens arrive
        # via the "messages" StreamPart; the full message with metadata arrives
        # here via "updates" once the node completes.
        for msg in messages:
            response_metadata = getattr(msg, "response_metadata", None) or {}
            usage = getattr(msg, "usage_metadata", None)
            finish_reason = response_metadata.get("finish_reason")
            if finish_reason is not None or usage is not None:
                log_event(
                    "model_response",
                    is_subagent=is_subagent,
                    finish_reason=finish_reason,
                    input_tokens=(
                        getattr(usage, "input_tokens", None) if usage else None
                    ),
                    output_tokens=(
                        getattr(usage, "output_tokens", None) if usage else None
                    ),
                    total_tokens=(
                        getattr(usage, "total_tokens", None) if usage else None
                    ),
                )

    # ── tools node ─────────────────────────────────────────────────────────
    elif node_name == "tools":
        for msg in messages:
            msg_type = getattr(msg, "type", "")

            if msg_type == "tool":
                tool_name = getattr(msg, "name", "unknown_tool")
                tool_output = getattr(msg, "content", None)

                # Emit WS tool_end frame for main-agent tools so the existing
                # frontend "Running <tool>…" affordance in useChatStream.ts
                # sees a completion signal. Subagent tool completions are
                # visible via subagent_token frames (TICKET-004 will render them).
                if not is_subagent:
                    await websocket.send_json({
                        "type": "tool_end",
                        "tool": tool_name,
                    })

                log_event(
                    "tool_end",
                    tool=tool_name,
                    is_subagent=is_subagent,
                    output_summary=summarize_payload(tool_output),
                )

                # Subagent completion: a ToolMessage for "task" in the main
                # agent's tools node means a delegated subagent has returned.
                # Resolve the subagent name by looking up the matching
                # tool_call_id recorded in turn_ctx at spawn time.
                if not is_subagent and tool_name == "task":
                    tc_id = getattr(msg, "tool_call_id", "")
                    subagent_name = turn_ctx.get(tc_id, "unknown")
                    await websocket.send_json({
                        "type": "subagent_end",
                        "name": subagent_name,
                    })
                    log_event("subagent_end", subagent=subagent_name)

            elif msg_type == "ai":
                # AI message in the tools node = the model emitted tool calls.
                # Emit tool_start frames for each call.
                for tc in getattr(msg, "tool_calls", []):
                    tc_name = tc.get("name", "unknown_tool")
                    tc_input = tc.get("args", {})
                    input_summary = str(tc_input)[:200]

                    if not is_subagent:
                        await websocket.send_json({
                            "type": "tool_start",
                            "tool": tc_name,
                            "input": input_summary,
                        })

                    log_event(
                        "tool_start",
                        tool=tc_name,
                        is_subagent=is_subagent,
                        tool_input=truncate_value(str(tc_input)),
                    )


@app.get("/charts")
async def list_charts():
    files = [
        f for f in settings.charts_dir.iterdir()
        if f.is_file() and f.suffix.lower() in _CHART_EXTENSIONS
    ]
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    files = files[:100]
    return [
        {"name": f.name, "url": f"/charts/{f.name}", "mtime": int(f.stat().st_mtime)}
        for f in files
    ]


@app.get("/reports")
async def list_reports():
    files = [
        f for f in settings.reports_dir.iterdir()
        if f.is_file() and f.suffix.lower() in _REPORT_EXTENSIONS
    ]
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    files = files[:100]
    return [
        {"name": f.name, "url": f"/reports/{f.name}", "mtime": int(f.stat().st_mtime)}
        for f in files
    ]


@app.get("/charts/{filename}")
async def get_chart(filename: str):
    p = _safe_path(settings.charts_dir, filename)
    if not p.exists():
        raise HTTPException(404, "Chart not found")
    if p.suffix.lower() not in _CHART_EXTENSIONS:
        raise HTTPException(400, "File type not permitted")
    return FileResponse(p)


@app.get("/reports/{filename}")
async def get_report(filename: str):
    p = _safe_path(settings.reports_dir, filename)
    if not p.exists():
        raise HTTPException(404, "Report not found")
    if p.suffix.lower() not in _REPORT_EXTENSIONS:
        raise HTTPException(400, "File type not permitted")
    return FileResponse(p)
