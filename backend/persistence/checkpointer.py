"""
persistence/checkpointer.py
────────────────────────────────────────────────────────────────────────────
LangGraph AsyncPostgresSaver lifecycle.

Public surface:
  open_checkpointer()  — async context manager used in FastAPI lifespan.
                         Opens the pool, sets the module-level holder,
                         closes on exit.
  get_checkpointer()   — returns the live saver (None when persistence is
                         disabled) for use in build_agent().

Design invariants (MUST NOT be violated):
  • Do NOT call checkpointer.setup() here. Schema creation belongs in the
    standalone migration script (poetry run init-checkpoints). Runtime code
    assumes tables exist.
  • DataFrames must never enter the checkpoint. Graph state is text-only;
    the DF cache is ephemeral and lives outside LangGraph state. Adding a
    DataFrame to graph state would cause the encrypted bytes for the entire
    frame to be rewritten to Postgres on every graph step — a documented
    bloat anti-pattern.
"""

from __future__ import annotations

import base64
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg.rows import dict_row
from psycopg_pool import AsyncConnectionPool

from config.settings import settings
from persistence.crypto import EncryptedSerializer  # re-exported for callers

__all__ = ["EncryptedSerializer", "get_checkpointer", "open_checkpointer"]


# ── Module-level holder ───────────────────────────────────────────────────────

_checkpointer: AsyncPostgresSaver | None = None


def get_checkpointer() -> AsyncPostgresSaver | None:
    """
    Return the live AsyncPostgresSaver, or None when persistence is disabled.

    None is the valid no-op value — callers (build_agent, /health) must
    handle it without raising.
    """
    return _checkpointer


# ── Lifecycle context manager ─────────────────────────────────────────────────

@asynccontextmanager
async def open_checkpointer():
    """
    Async context manager for the checkpointer lifecycle. Intended for use
    in FastAPI's lifespan handler — call once at app startup, not per-request.

    On enter:
      1. Decode the AES-256 key from settings.
      2. Build an EncryptedSerializer.
      3. Open a psycopg AsyncConnectionPool (autocommit + dict_row required
         by AsyncPostgresSaver — omitting either raises at runtime).
      4. Instantiate AsyncPostgresSaver and set the module-level holder.

    On exit: clear the holder, then close the pool (psycopg drains in-flight
    queries before closing).

    Only call this when settings.checkpoint_enabled is True. Calling it when
    disabled is a programming error, not a configuration error.
    """
    global _checkpointer

    key = base64.b64decode(settings.checkpoint_encryption_key)
    serde = EncryptedSerializer.from_pycryptodome_aes(key)

    async with AsyncConnectionPool(
        conninfo=settings.checkpoint_db_uri,
        min_size=settings.checkpoint_pool_min,
        max_size=settings.checkpoint_pool_max,
        kwargs={"autocommit": True, "row_factory": dict_row},
    ) as pool:
        _checkpointer = AsyncPostgresSaver(pool, serde=serde)
        try:
            yield _checkpointer
        finally:
            _checkpointer = None
