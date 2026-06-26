"""
scripts/init_checkpoint_db.py
────────────────────────────────────────────────────────────────────────────
Standalone migration: creates the LangGraph checkpoint tables in Postgres.

Run ONCE after `docker compose up -d` (local) or before app start (Cloud SQL):

    poetry run init-checkpoints

Idempotent — AsyncPostgresSaver.setup() uses versioned migrations so a
second run is a no-op without error.

Tables created:
  checkpoints          — one row per (thread_id, checkpoint_ns, checkpoint_id)
  checkpoint_blobs     — serialized node state blobs
  checkpoint_writes    — pending write entries between steps
  checkpoint_migrations — migration version tracking

NEVER call this from app-boot code. It must run as a deliberate deploy step,
not on every uvicorn start — that risks permission failures and "table already
exists" races in multi-worker deployments.
"""

from __future__ import annotations

import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()

from config.settings import settings  # noqa: E402 — load_dotenv must run first


async def _run() -> None:
    if not settings.checkpoint_enabled:
        print(
            "ERROR: CHECKPOINT_DB_URI is not set. "
            "Set CHECKPOINT_DB_URI and CHECKPOINT_ENCRYPTION_KEY in .env before running.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Import here so the module is importable even when persistence deps are
    # absent (e.g. in a slim test environment without langgraph-checkpoint-postgres).
    from persistence.checkpointer import open_checkpointer

    print(f"Connecting to checkpoint DB…")
    print("Running migrations…")

    async with open_checkpointer() as checkpointer:
        await checkpointer.setup()

    print("Done. Tables created or already exist:")
    print("  checkpoints")
    print("  checkpoint_blobs")
    print("  checkpoint_writes")
    print("  checkpoint_migrations")


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
