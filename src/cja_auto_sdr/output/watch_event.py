"""NDJSON event serializer for `cja-watch-event/v1` (watch mode stdout schema)."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime

from cja_auto_sdr.core.logging import redact_text

SCHEMA_VERSION = "cja-watch-event/v1"


def iso8601_utc_now() -> str:
    """Return current UTC time as Z-suffixed ISO-8601 (no microseconds)."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass(frozen=True)
class BaselineEvent:
    ts: str
    cycle: int
    data_view_id: str
    snapshot_id: str
    component_counts: dict[str, int] = field(default_factory=dict)


@dataclass(frozen=True)
class ChangeEvent:
    ts: str
    cycle: int
    data_view_id: str
    previous_snapshot_id: str
    current_snapshot_id: str
    total_changes: int
    changes_by_category: dict[str, dict[str, int]] = field(default_factory=dict)


@dataclass(frozen=True)
class ErrorEvent:
    ts: str
    cycle: int
    data_view_id: str
    stage: str  # "fetch" | "snapshot" | "diff"
    error_class: str
    error_message: str


def _envelope(event_type: str, ts: str, cycle: int, data_view_id: str) -> dict[str, object]:
    # Field order matters: schema, type, ts, cycle, data_view_id are the human-scannable prefix.
    return {
        "schema": SCHEMA_VERSION,
        "type": event_type,
        "ts": ts,
        "cycle": cycle,
        "data_view_id": data_view_id,
    }


def serialize_event(event: BaselineEvent | ChangeEvent | ErrorEvent) -> str:
    if isinstance(event, BaselineEvent):
        payload = _envelope("baseline", event.ts, event.cycle, event.data_view_id)
        payload["snapshot_id"] = event.snapshot_id
        payload["component_counts"] = event.component_counts
    elif isinstance(event, ChangeEvent):
        payload = _envelope("change", event.ts, event.cycle, event.data_view_id)
        payload["previous_snapshot_id"] = event.previous_snapshot_id
        payload["current_snapshot_id"] = event.current_snapshot_id
        payload["total_changes"] = event.total_changes
        payload["changes_by_category"] = event.changes_by_category
    elif isinstance(event, ErrorEvent):
        payload = _envelope("error", event.ts, event.cycle, event.data_view_id)
        payload["stage"] = event.stage
        payload["error_class"] = event.error_class
        payload["error_message"] = redact_text(event.error_message)
    else:  # pragma: no cover — defensive; unreachable if callers honor the union.
        raise TypeError(f"unknown watch event type: {type(event).__name__}")
    return json.dumps(payload, separators=(",", ":")) + "\n"
