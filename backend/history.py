"""
history.py
──────────────────────────────────────────────────────────────────────────────
Pure utilities for client-sent conversation history.

No external dependencies — importable in isolation (test-friendly).
"""

from __future__ import annotations


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
