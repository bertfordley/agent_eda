"""
telemetry/governance.py
─────────────────────────────────────────────────────────────────────────────
Governance audit event helpers.

SCHEMA CONTRACT
───────────────
These events constitute the regulatory audit trail for this application.
Their schema is contractually stable: only additive changes (new nullable
fields) are permitted without a migration plan. Renaming or removing fields
is a breaking change that requires version coordination with any downstream
log consumers (dashboards, compliance queries, SIEM rules).

Current governance events:
  governance.query            — every SQL execution attempt (accepted or rejected)
  governance.thread_resumed   — a turn loaded existing checkpoint state (vs. fresh)
  governance.entity_resolution — entity mention resolved to a stored value
                                 (DORMANT — schema seam for the planned NER/ER
                                  layer; no callers yet, fires when that layer lands)

The entity_resolution event is defined now so that:
  1. Log parsers and dashboards can be built against a stable schema before
     the feature exists.
  2. The first ER implementation inherits the correct field names without a
     log-format migration.
"""

from __future__ import annotations

import logging
from typing import Any

from telemetry.core import log_event, truncate_value

logger = logging.getLogger(__name__)


def log_thread_resumed(thread_id: str) -> None:
    """
    Emit a governance audit event when a turn resumes an existing conversation.

    Fires once per turn when the LangGraph checkpointer has prior state for
    the given thread_id — i.e., this is not the first turn in the thread.
    Distinguishing resumed threads from fresh ones is part of the audit story:
    the prior conversation context materially shapes the response.
    """
    try:
        log_event("governance.thread_resumed", thread_id=thread_id)
    except Exception as exc:
        logger.warning("governance emit failed: %s", exc)


def log_query_executed(
    sql: str,
    row_count: int | None,
    bytes_processed: int | None,
    rejected: bool,
    rejection_reason: str | None,
    cache_key: str | None = None,
    dry_run_bytes: int | None = None,
) -> None:
    """
    Emit a governance audit event for every SQL execution attempt.

    Called at every exit path of bq_run_query:
      - SQL rejected by _assert_read_only (rejected=True, row_count=None)
      - Dry-run over-budget rejection  (rejected=True, row_count=None)
      - Materialization-cap exceeded   (rejected=True, row_count=None)
      - Successful execution           (rejected=False, row_count=N)

    The two forward-looking nullable fields (resolved_entities,
    applied_definitions) are present but empty until the NER/ER layer lands.
    Do not remove them — downstream parsers depend on their presence.
    """
    try:
        log_event(
            "governance.query",
            sql=truncate_value(sql),
            cache_key=cache_key,
            rejected=rejected,
            rejection_reason=truncate_value(rejection_reason) if rejection_reason else None,
            row_count=row_count,
            bytes_processed=bytes_processed,
            dry_run_bytes=dry_run_bytes,
            # ── NER/ER seam fields (nullable until that layer exists) ──────
            resolved_entities=[],   # will be list[dict] when ER layer is live
            applied_definitions=[], # will be list[str] when governance rules exist
        )
    except Exception as exc:
        logger.warning("governance emit failed: %s", exc)


def log_script_executed(
    skill_name: str,
    script: str,
    args: list[str] | None,
    accepted: bool,
    rejection_reason: str | None = None,
    exit_code: int | None = None,
    duration_ms: int | None = None,
) -> None:
    """
    Emit a governance audit event for every skill-script execution attempt.

    Called at every exit path of run_skill_script:
      - execution disabled / skill unknown / path denied / not found
                                       (accepted=False, exit_code=None)
      - timed out or errored           (accepted=False, exit_code=None)
      - ran to completion              (accepted=True, exit_code=N)

    accepted=True means the script was actually launched (regardless of its exit
    code); accepted=False means it was blocked before launch.
    """
    try:
        log_event(
            "governance.script_executed",
            skill_name=skill_name,
            script=script,
            args=[truncate_value(a) for a in (args or [])],
            accepted=accepted,
            rejection_reason=truncate_value(rejection_reason) if rejection_reason else None,
            exit_code=exit_code,
            duration_ms=duration_ms,
        )
    except Exception as exc:
        logger.warning("governance emit failed: %s", exc)


def log_entity_resolution(
    mention: str,
    resolved_to: Any,
    confidence: float | None,
    candidates: list[dict],
    column: str | None,
    table: str | None,
    auto_applied: bool,
    resolution_method: str | None = None,
) -> None:
    """
    Emit a governance audit event when a user entity mention is resolved
    to one or more stored values.

    DORMANT — no callers exist yet. This function is the seam for the
    planned NER/ER pipeline. When that layer is built:
      - mention:          the raw span extracted from the user query
                          e.g. "chevy atlanta"
      - resolved_to:      the canonical stored value(s) chosen
                          e.g. "Chevrolet of Atlanta LLC"
                          or a list when resolved to a variant cluster
      - confidence:       float 0–1 from the matcher, None if rule-based
      - candidates:       list of all candidates considered with scores
                          e.g. [{"value":"Chevrolet of Atlanta LLC","score":0.91}, ...]
      - column:           which entity column this resolved against
                          e.g. "dealer_name"
      - table:            source table of the entity column
                          e.g. "sales.orders"
      - auto_applied:     True if the resolution was applied to the SQL
                          without user confirmation; False if the user was
                          shown candidates and chose
      - resolution_method: "lexical" | "embedding" | "llm" | "alias_table"
                           | "user_confirmed" — how the match was made
    """
    try:
        log_event(
            "governance.entity_resolution",
            mention=truncate_value(str(mention)),
            resolved_to=resolved_to,
            confidence=confidence,
            candidates=candidates[:10],  # cap candidates list in the log
            column=column,
            table=table,
            auto_applied=auto_applied,
            resolution_method=resolution_method,
        )
    except Exception:
        # Governance logging must never block the resolution pipeline.
        pass
