"""Shared helpers for org-report snapshot identity, retention, and ordering."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_EARLIEST_UTC = datetime.min.replace(tzinfo=UTC)


def parse_snapshot_timestamp(raw_timestamp: Any) -> datetime | None:
    """Normalize snapshot timestamps to UTC for stable ordering."""
    if raw_timestamp in (None, ""):
        return None

    timestamp_text = str(raw_timestamp).strip()
    if not timestamp_text:
        return None
    if timestamp_text.endswith("Z"):
        timestamp_text = f"{timestamp_text[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(timestamp_text)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def snapshot_epoch(raw_timestamp: Any) -> float | None:
    """Return a normalized UTC epoch for a persisted snapshot timestamp."""
    parsed = parse_snapshot_timestamp(raw_timestamp)
    if parsed is None:
        return None
    return parsed.timestamp()


def chronological_snapshot_sort_fields(
    raw_timestamp: Any,
    *,
    tie_breaker: str = "",
) -> tuple[bool, datetime, str, str]:
    """Return oldest-to-newest sort fields, placing undated snapshots last."""
    parsed = parse_snapshot_timestamp(raw_timestamp)
    return (
        parsed is None,
        parsed or _EARLIEST_UTC,
        str(raw_timestamp or ""),
        tie_breaker,
    )


def newest_first_snapshot_sort_fields(
    raw_timestamp: Any,
    *,
    tie_breaker: str = "",
) -> tuple[bool, float, str, str]:
    """Return newest-to-oldest sort fields, placing undated snapshots last."""
    epoch = snapshot_epoch(raw_timestamp)
    return (
        epoch is None,
        -epoch if epoch is not None else 0.0,
        str(raw_timestamp or ""),
        tie_breaker,
    )


def snapshot_identity_tokens(
    *,
    snapshot_id: Any = None,
    content_hash: Any = None,
    source_path: str | Path | None = None,
    fallback_parts: Iterable[Any] = (),
) -> tuple[tuple[str, ...], ...]:
    """Return all stable identity aliases available for one snapshot."""
    identities: list[tuple[str, ...]] = []

    if snapshot_id not in (None, ""):
        identities.append(("snapshot_id", str(snapshot_id)))
    if content_hash not in (None, ""):
        identities.append(("content_hash", str(content_hash)))
    if source_path not in (None, ""):
        identities.append(("source_path", str(Path(source_path).resolve(strict=False))))

    if identities:
        return tuple(identities)

    normalized_fallback = tuple(str(part) for part in fallback_parts)
    return (("fallback", *normalized_fallback),)


def org_report_snapshot_history_eligible(data: Mapping[str, Any]) -> bool:
    """Return True when an org-report payload should participate in trending history."""
    summary = data.get("summary", {})
    if not isinstance(summary, Mapping):
        return True
    return not bool(summary.get("is_sampled"))
