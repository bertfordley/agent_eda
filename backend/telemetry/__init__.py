"""
telemetry — structured JSON telemetry spine for EDA Agent.

Public API:
    from telemetry.core import log_event, turn_span, turn_span_async
    from telemetry.core import truncate_value, summarize_payload
    from telemetry.governance import log_query_executed, log_entity_resolution
"""

from telemetry.core import (
    log_event,
    turn_span,
    turn_span_async,
    truncate_value,
    summarize_payload,
    current_turn_id,
)
from telemetry.governance import log_query_executed, log_entity_resolution

__all__ = [
    "log_event",
    "turn_span",
    "turn_span_async",
    "truncate_value",
    "summarize_payload",
    "current_turn_id",
    "log_query_executed",
    "log_entity_resolution",
]
