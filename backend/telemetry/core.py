"""
telemetry/core.py
─────────────────────────────────────────────────────────────────────────────
Single telemetry spine. Emits one JSON line per event to stdout.

Design principles:
  • Crash-proof: the emitter never raises to its caller. A logging failure
    emits a fallback error event rather than propagating.
  • Session/turn correlation: every event carries session_id + turn_id +
    a per-turn monotonic sequence number so async stdout interleave is
    reconstructable.
  • Secret exclusion: a denylist redacts credentials/tokens at all levels.
  • Volume control: large DataFrames are summarised, long strings truncated.
  • LangSmith stays off: forced by settings.__init__; documented here too.

The two ContextVars (current_session_id, current_turn_id) are set by
server.py and main.py at turn boundaries. current_session_id is imported
from tools.bigquery_tools (single source of truth); current_turn_id is
owned here.

Usage:
    from telemetry.core import log_event, turn_span, turn_span_async
    from telemetry.core import truncate_value, summarize_payload
"""

from __future__ import annotations

import json
import logging
import sys
import time
import traceback
import uuid
from contextlib import asynccontextmanager, contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any

# Import the canonical ContextVars from bigquery_tools (single source of truth).
# current_session_id — ephemeral per-connection; telemetry correlation.
# current_thread_id  — durable LangGraph conversation identity; bridges the
#                      Phase 1 telemetry work and Phase 3 persistence (TICKET-4.3).
from tools.bigquery_tools import current_session_id, current_thread_id  # noqa: E402  (circular-safe at runtime)

from config.settings import settings

# ── Turn correlation ──────────────────────────────────────────────────────────

current_turn_id: ContextVar[str | None] = ContextVar("current_turn_id", default=None)
current_turn_seq: ContextVar[int] = ContextVar("current_turn_seq", default=0)

# ── Logger ────────────────────────────────────────────────────────────────────
# Dedicated logger → stdout only, raw JSON message, no double-propagation.

_handler = logging.StreamHandler(sys.stdout)
_handler.setFormatter(logging.Formatter("%(message)s"))

_logger = logging.getLogger("eda.telemetry")
_logger.setLevel(logging.DEBUG)
_logger.addHandler(_handler)
_logger.propagate = False

# ── Secret denylist ───────────────────────────────────────────────────────────

_SECRET_KEYS = {
    "token", "access_token", "refresh_token", "credentials",
    "client_secret", "api_key", "authorization", "password",
    "private_key", "secret", "auth",
    # DB connection strings contain embedded passwords — must never appear in logs.
    "checkpoint_db_uri", "dsn", "conn_string",
    # Encryption key — raw bytes/base64 of the AES-256 key; never log.
    "checkpoint_encryption_key", "encryption_key",
}


def _redact(fields: dict) -> dict:
    """Replace any secret-named keys with [REDACTED]. Case-insensitive match."""
    out = {}
    for k, v in fields.items():
        if k.lower() in _SECRET_KEYS:
            out[k] = "[REDACTED]"
        elif isinstance(v, dict):
            out[k] = _redact(v)
        else:
            out[k] = v
    return out


# ── Value utilities ───────────────────────────────────────────────────────────

def truncate_value(v: Any) -> Any:
    """
    Truncate a string value to TELEMETRY_MAX_VALUE_CHARS.
    Non-string values are returned as-is for the JSON serializer to handle.
    """
    if isinstance(v, str) and len(v) > settings.telemetry_max_value_chars:
        excess = len(v) - settings.telemetry_max_value_chars
        return v[: settings.telemetry_max_value_chars] + f"…[truncated {excess} chars]"
    return v


def summarize_payload(obj: Any) -> Any:
    """
    Summarise large objects so they are loggable without blowing up stdout.

    - pandas.DataFrame → shape, columns, dtypes, sample rows
    - Long str          → preview with truncation marker
    - Large list/dict   → size + first few items
    - Anything else     → returned as-is (JSON serializer handles it)
    """
    # Lazy pandas import so telemetry has no hard dependency on pandas.
    try:
        import pandas as pd  # type: ignore
        if isinstance(obj, pd.DataFrame):
            return {
                "type": "dataframe",
                "rows": len(obj),
                "cols": list(obj.columns),
                "dtypes": {col: str(dtype) for col, dtype in obj.dtypes.items()},
                "sample": obj.head(settings.telemetry_sample_rows).to_dict("records"),
            }
    except ImportError:
        pass

    if isinstance(obj, str):
        return truncate_value(obj)

    if isinstance(obj, (list, tuple)):
        if len(obj) > 20:
            return {
                "type": "list",
                "size": len(obj),
                "preview": list(obj[:5]),
            }
        return obj

    if isinstance(obj, dict):
        try:
            serialized = json.dumps(obj, default=str)
            if len(serialized) > 4096:
                items = list(obj.items())[:5]
                return {
                    "type": "dict",
                    "size": len(obj),
                    "preview": dict(items),
                }
        except Exception:
            pass
        return obj

    return obj


# ── Core emitter ─────────────────────────────────────────────────────────────

def _next_seq() -> int:
    """Increment and return the per-turn sequence counter."""
    seq = current_turn_seq.get(0)
    current_turn_seq.set(seq + 1)
    return seq


def log_event(event_type: str, **fields: Any) -> None:
    """
    Emit one JSON line to stdout. Never raises to the caller.

    Standard fields added automatically:
      ts          — UTC ISO-8601 with milliseconds
      event       — event_type argument
      session_id  — from current_session_id ContextVar
      turn_id     — from current_turn_id ContextVar (None outside a turn span)
      seq         — monotonic per-turn sequence counter

    Secrets are redacted before serialization regardless of TELEMETRY_LEVEL.
    Non-serializable values fall back to repr() via json's default=str.
    """
    if not settings.telemetry_enabled:
        return

    record: dict[str, Any] = {
        "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
        "event": event_type,
        "session_id": current_session_id.get("__default__"),
        "thread_id": current_thread_id.get("__default__"),
        "turn_id": current_turn_id.get(None),
        "seq": _next_seq(),
        **fields,
    }

    record = _redact(record)

    try:
        line = json.dumps(record, default=str, ensure_ascii=False)
    except Exception as e:
        # Serialization itself failed — emit a minimal fallback so the event
        # is never silently lost.
        try:
            fallback = json.dumps({
                "ts": record.get("ts", ""),
                "event": "telemetry_serialization_error",
                "session_id": record.get("session_id"),
                "turn_id": record.get("turn_id"),
                "seq": record.get("seq"),
                "original_event": event_type,
                "error": repr(e),
            })
            _logger.info(fallback)
        except Exception:
            pass  # If even the fallback fails, stay silent — never raise.
        return

    _logger.info(line)


# ── Turn lifecycle span ───────────────────────────────────────────────────────

@contextmanager
def turn_span(message: str, channel: str):
    """
    Synchronous context manager for one agent turn.

    Sets turn_id + resets seq counter → emits turn_started →
    yields → emits turn_completed (success) or turn_failed (exception).
    Always re-raises on exception so the caller's error handling is unaffected.

    Args:
        message: The user's raw input (truncated in the log).
        channel: One of "cli" | "rest" | "ws".

    Usage:
        with turn_span(user_input, channel="cli"):
            reply = agent_chat(user_input)
    """
    turn_id = uuid.uuid4().hex
    turn_id_token = current_turn_id.set(turn_id)
    seq_token = current_turn_seq.set(0)
    start = time.monotonic()

    log_event(
        "turn_started",
        channel=channel,
        user_message=truncate_value(message),
    )

    try:
        yield
    except BaseException as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        log_event(
            "turn_failed",
            channel=channel,
            duration_ms=duration_ms,
            error_type=type(exc).__name__,
            error=truncate_value(str(exc)),
            traceback=traceback.format_exc(),
        )
        raise
    else:
        duration_ms = int((time.monotonic() - start) * 1000)
        log_event(
            "turn_completed",
            channel=channel,
            duration_ms=duration_ms,
        )
    finally:
        current_turn_id.reset(turn_id_token)
        current_turn_seq.reset(seq_token)


@asynccontextmanager
async def turn_span_async(message: str, channel: str):
    """
    Async context manager for one agent turn. Identical semantics to
    turn_span but usable with `async with` in the WebSocket handler.

    Usage:
        async with turn_span_async(message, channel="ws"):
            async for event in agent.astream_events(...):
                ...
    """
    turn_id = uuid.uuid4().hex
    turn_id_token = current_turn_id.set(turn_id)
    seq_token = current_turn_seq.set(0)
    start = time.monotonic()

    log_event(
        "turn_started",
        channel=channel,
        user_message=truncate_value(message),
    )

    try:
        yield
    except BaseException as exc:
        duration_ms = int((time.monotonic() - start) * 1000)
        log_event(
            "turn_failed",
            channel=channel,
            duration_ms=duration_ms,
            error_type=type(exc).__name__,
            error=truncate_value(str(exc)),
            traceback=traceback.format_exc(),
        )
        raise
    else:
        duration_ms = int((time.monotonic() - start) * 1000)
        log_event(
            "turn_completed",
            channel=channel,
            duration_ms=duration_ms,
        )
    finally:
        current_turn_id.reset(turn_id_token)
        current_turn_seq.reset(seq_token)
