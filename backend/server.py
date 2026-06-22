"""
server.py
─────────────────────────────────────────────────────────────────────────────
FastAPI server. Deep Agents' LangGraph runtime supports streaming natively,
so the WebSocket endpoint gets real token-by-token streaming with no hacks.

Run:
    poetry run uvicorn server:app --reload --port 8000
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from langgraph.errors import GraphRecursionError
from pydantic import BaseModel

from agents.orchestrator import get_agent, chat as agent_chat, AGENT_RECURSION_LIMIT
from config.settings import settings
from tools.bigquery_tools import current_session_id

app = FastAPI(title="EDA Agent", version="1.0.0")

# TICKET-009: restrict CORS to configured origins instead of wildcard "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allow_origins,
    allow_methods=["*"],
    allow_headers=["*"],
)

# TICKET-014: allowed file extensions for chart and report endpoints.
_CHART_EXTENSIONS = {".png", ".html"}
_REPORT_EXTENSIONS = {".html", ".pdf"}


class ChatRequest(BaseModel):
    message: str


class ChatResponse(BaseModel):
    reply: str


def _safe_path(base_dir: Path, filename: str) -> Path:
    """Resolve filename inside base_dir and reject path traversal attempts."""
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
    }


@app.post("/chat", response_model=ChatResponse)
async def chat_endpoint(req: ChatRequest):
    # TICKET-001: set a per-request session_id so the DataFrame cache is isolated.
    session_id = uuid.uuid4().hex
    token = current_session_id.set(session_id)
    try:
        reply = await asyncio.to_thread(agent_chat, req.message)
        return ChatResponse(reply=reply)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))
    finally:
        current_session_id.reset(token)


@app.websocket("/chat/stream")
async def chat_stream(websocket: WebSocket):
    """
    Streaming chat via WebSocket.

    Client sends: {"message": "..."}
    Server sends:
      - {"type": "tool_start", "tool": "<name>", "input": "<summary>"}
        when the agent begins a tool call (TICKET-011)
      - {"type": "tool_end", "tool": "<name>"}
        when a tool call completes (TICKET-011)
      - raw text token string for each streamed content chunk
      - {"done": true} when the agent turn is complete
      - {"error": "..."} on any per-message failure
    """
    await websocket.accept()
    agent = get_agent()

    # TICKET-001: generate a stable session_id for this WebSocket connection
    # so all tool calls within the session share the same DataFrame cache.
    session_id = uuid.uuid4().hex

    try:
        while True:
            # TICKET-008: receive raw text and parse manually so a
            # JSONDecodeError never escapes to the outer loop.
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

            input_state = {"messages": [{"role": "user", "content": message}]}

            # TICKET-001: bind the session_id ContextVar for this agent turn.
            token = current_session_id.set(session_id)
            try:
                async for event in agent.astream_events(
                    input_state,
                    version="v2",
                    config={"recursion_limit": AGENT_RECURSION_LIMIT},
                ):
                    kind = event.get("event")

                    # TICKET-011: forward tool-start events so the frontend
                    # can show which tool is running instead of a blank gap.
                    if kind == "on_tool_start":
                        tool_name = event.get("name", "unknown_tool")
                        tool_input = event.get("data", {}).get("input", {})
                        # Truncate input summary to avoid sending large payloads.
                        input_summary = str(tool_input)[:200]
                        await websocket.send_json({
                            "type": "tool_start",
                            "tool": tool_name,
                            "input": input_summary,
                        })

                    # TICKET-011: forward tool-end completion signal only —
                    # not the full tool output which may contain sensitive data.
                    elif kind == "on_tool_end":
                        tool_name = event.get("name", "unknown_tool")
                        await websocket.send_json({
                            "type": "tool_end",
                            "tool": tool_name,
                        })

                    elif kind == "on_chat_model_stream":
                        chunk = event.get("data", {}).get("chunk")
                        if chunk and hasattr(chunk, "content") and chunk.content:
                            await websocket.send_text(chunk.content)

                await websocket.send_json({"done": True})

            except WebSocketDisconnect:
                raise
            except GraphRecursionError:
                await websocket.send_json({
                    "error": (
                        "Agent exceeded the step limit. Please rephrase or narrow "
                        "the request — ask about one table or metric at a time."
                    )
                })
            except Exception as e:
                await websocket.send_json({"error": str(e)})
            finally:
                current_session_id.reset(token)

    except WebSocketDisconnect:
        pass


@app.get("/charts")
async def list_charts():
    # TICKET-014: filter to allowed extensions, sort newest-first, cap at 100.
    files = [
        f for f in settings.charts_dir.iterdir()
        if f.is_file() and f.suffix.lower() in _CHART_EXTENSIONS
    ]
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    files = files[:100]
    return [
        {
            "name": f.name,
            "url": f"/charts/{f.name}",
            "mtime": int(f.stat().st_mtime),
        }
        for f in files
    ]


@app.get("/reports")
async def list_reports():
    # TICKET-014: filter to allowed extensions, sort newest-first, cap at 100.
    files = [
        f for f in settings.reports_dir.iterdir()
        if f.is_file() and f.suffix.lower() in _REPORT_EXTENSIONS
    ]
    files.sort(key=lambda f: f.stat().st_mtime, reverse=True)
    files = files[:100]
    return [
        {
            "name": f.name,
            "url": f"/reports/{f.name}",
            "mtime": int(f.stat().st_mtime),
        }
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
