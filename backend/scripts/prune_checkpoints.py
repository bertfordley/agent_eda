"""
scripts/prune_checkpoints.py
────────────────────────────────────────────────────────────────────────────
Standalone pruning script for LangGraph checkpoint tables.

Problem addressed: LangGraph writes one row per graph step, so a multi-step
turn with tool calls generates ~15–30 rows. Without pruning, documented
production experience shows ~93 rows per average conversation and tens of MB
per week of modest traffic — degrading latency and storage cost over time.

Pruning strategy:
  Per (thread_id, checkpoint_ns) partition, retain the most recent KEEP_LAST
  checkpoints (ordered by checkpoint_id DESC — UUIDv7 encodes the timestamp
  in the high bits, making this a time-ordered sort) and delete older rows
  from all three checkpoint tables.

Tables pruned (in dependency order):
  1. checkpoint_writes  — pending write entries (references checkpoints)
  2. checkpoint_blobs   — serialized node state blobs (references checkpoints)
  3. checkpoints        — one row per step (primary)

Security note (MANDATORY):
  KEEP_LAST is passed via parameterized query — never concatenated into SQL.
  Table names are hardcoded constants, not user input.  This design follows
  the guideline from the checkpointer CVE class: parameterized SQL only.

Usage:
  poetry run prune-checkpoints                     # keep last 20 per thread
  poetry run prune-checkpoints --keep-last 10      # stricter retention
  poetry run prune-checkpoints --dry-run           # preview, no deletes

Run as a scheduled job:
  Locally:   add to crontab — e.g. daily at 2 AM:
               0 2 * * * cd /path/to/backend && poetry run prune-checkpoints
  GCP:       Cloud Scheduler → Cloud Run Job / Cloud Functions trigger
               (see README.md)

NEVER call this from app-boot code.
"""

from __future__ import annotations

import argparse
import asyncio
import sys

from dotenv import load_dotenv

load_dotenv()

from config.settings import settings  # noqa: E402

DEFAULT_KEEP_LAST = 20


def _positive_int(value: str) -> int:
    ivalue = int(value)
    if ivalue < 1:
        raise argparse.ArgumentTypeError(
            f"--keep-last must be a positive integer >= 1, got {ivalue!r}"
        )
    return ivalue

# ── SQL constants (all parameterized — %s for keep_last, no concatenation) ───

_COUNT_EXCESS_SQL = """
    SELECT COUNT(*)
    FROM (
        SELECT 1
        FROM (
            SELECT ROW_NUMBER() OVER (
                PARTITION BY thread_id, checkpoint_ns
                ORDER BY checkpoint_id DESC
            ) AS rn
            FROM checkpoints
        ) ranked
        WHERE rn > %s
    ) excess
"""

_DELETE_WRITES_SQL = """
    DELETE FROM checkpoint_writes
    WHERE (thread_id, checkpoint_ns, checkpoint_id) IN (
        SELECT thread_id, checkpoint_ns, checkpoint_id
        FROM (
            SELECT thread_id, checkpoint_ns, checkpoint_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY thread_id, checkpoint_ns
                       ORDER BY checkpoint_id DESC
                   ) AS rn
            FROM checkpoints
        ) ranked
        WHERE rn > %s
    )
"""

_DELETE_BLOBS_SQL = """
    DELETE FROM checkpoint_blobs
    WHERE (thread_id, checkpoint_ns, checkpoint_id) IN (
        SELECT thread_id, checkpoint_ns, checkpoint_id
        FROM (
            SELECT thread_id, checkpoint_ns, checkpoint_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY thread_id, checkpoint_ns
                       ORDER BY checkpoint_id DESC
                   ) AS rn
            FROM checkpoints
        ) ranked
        WHERE rn > %s
    )
"""

_DELETE_CHECKPOINTS_SQL = """
    DELETE FROM checkpoints
    WHERE (thread_id, checkpoint_ns, checkpoint_id) IN (
        SELECT thread_id, checkpoint_ns, checkpoint_id
        FROM (
            SELECT thread_id, checkpoint_ns, checkpoint_id,
                   ROW_NUMBER() OVER (
                       PARTITION BY thread_id, checkpoint_ns
                       ORDER BY checkpoint_id DESC
                   ) AS rn
            FROM checkpoints
        ) ranked
        WHERE rn > %s
    )
"""


async def _run(keep_last: int, dry_run: bool) -> None:
    if not settings.checkpoint_enabled:
        print(
            "ERROR: CHECKPOINT_DB_URI is not set. "
            "Set CHECKPOINT_DB_URI and CHECKPOINT_ENCRYPTION_KEY in .env before running.",
            file=sys.stderr,
        )
        sys.exit(1)

    import psycopg  # noqa: PLC0415

    print(f"Retention policy: keep last {keep_last} checkpoints per (thread_id, checkpoint_ns).")
    if dry_run:
        print("[dry-run] No rows will be deleted.")

    # autocommit=False so all three DELETEs are atomic — partial prune never
    # leaves orphan blobs or writes behind.
    async with await psycopg.AsyncConnection.connect(
        settings.checkpoint_db_uri, autocommit=False
    ) as conn:
        async with conn.cursor() as cur:
            await cur.execute("SELECT COUNT(*) FROM checkpoints")
            row = await cur.fetchone()
            total_before = row[0] if row else 0

            await cur.execute(_COUNT_EXCESS_SQL, (keep_last,))
            row = await cur.fetchone()
            rows_to_prune = row[0] if row else 0

            print(f"Checkpoint rows before: {total_before:,}")
            print(f"Rows eligible for pruning (rank > {keep_last}): {rows_to_prune:,}")

            if rows_to_prune == 0:
                print("Nothing to prune — retention policy already satisfied.")
                return

            if dry_run:
                print(f"[dry-run] Would delete up to {rows_to_prune:,} checkpoint rows.")
                return

            # Delete in dependency order: writes → blobs → checkpoints.
            await cur.execute(_DELETE_WRITES_SQL, (keep_last,))
            deleted_writes = cur.rowcount
            print(f"  Deleted {deleted_writes:,} rows from checkpoint_writes")

            await cur.execute(_DELETE_BLOBS_SQL, (keep_last,))
            deleted_blobs = cur.rowcount
            print(f"  Deleted {deleted_blobs:,} rows from checkpoint_blobs")

            await cur.execute(_DELETE_CHECKPOINTS_SQL, (keep_last,))
            deleted_checkpoints = cur.rowcount
            print(f"  Deleted {deleted_checkpoints:,} rows from checkpoints")

            await conn.commit()

            await cur.execute("SELECT COUNT(*) FROM checkpoints")
            row = await cur.fetchone()
            total_after = row[0] if row else 0
            print(f"Checkpoint rows after:  {total_after:,}")
            print(f"Done. Freed {total_before - total_after:,} checkpoint rows.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Prune old LangGraph checkpoint rows, keeping the most recent N per thread. "
            "Run as a scheduled job — daily is typical."
        )
    )
    parser.add_argument(
        "--keep-last",
        type=_positive_int,
        default=DEFAULT_KEEP_LAST,
        metavar="N",
        help=(
            f"Checkpoints to retain per (thread_id, checkpoint_ns) partition "
            f"(default: {DEFAULT_KEEP_LAST}, minimum: 1)"
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview what would be deleted without making any changes",
    )
    args = parser.parse_args()
    asyncio.run(_run(keep_last=args.keep_last, dry_run=args.dry_run))


if __name__ == "__main__":
    main()
