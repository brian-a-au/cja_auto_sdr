"""Shared helpers for org-report snapshot identity, retention, and ordering."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

_EARLIEST_UTC = datetime.min.replace(tzinfo=UTC)
ORG_REPORT_SNAPSHOT_ROOT_DIRNAME = "org_report_snapshots"


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


def snapshot_path_text(path: str | Path | None) -> str:
    """Return a normalized absolute path string for snapshot identity checks."""
    if path in (None, ""):
        return ""
    return str(Path(path).resolve(strict=False))


def snapshot_slug(value: Any, *, fallback: str = "unknown") -> str:
    """Return a filesystem-safe slug for snapshot file and directory labels."""
    if value in (None, ""):
        return fallback
    normalized = re.sub(r"[^0-9A-Za-z_-]+", "_", str(value)).strip("_")
    return normalized or fallback


def org_report_snapshot_dir_key(org_id: Any) -> str:
    """Return a collision-resistant directory key for one org-report history."""
    normalized_org_id = str(org_id or "unknown")
    digest = hashlib.sha256(normalized_org_id.encode("utf-8")).hexdigest()[:16]
    return f"{snapshot_slug(normalized_org_id)}__{digest}"


def org_report_snapshot_dir_candidates(org_id: Any) -> tuple[str, ...]:
    """Return directory keys to scan for an org, newest scheme first."""
    preferred = org_report_snapshot_dir_key(org_id)
    legacy = snapshot_slug(org_id)
    if legacy == preferred:
        return (preferred,)
    return (preferred, legacy)


def _dedupe_paths(paths: Iterable[Path]) -> tuple[Path, ...]:
    """Return paths de-duplicated by normalized absolute path, preserving order."""
    deduped: list[Path] = []
    seen_paths: set[str] = set()
    for path in paths:
        normalized = snapshot_path_text(path)
        if normalized in seen_paths:
            continue
        seen_paths.add(normalized)
        deduped.append(Path(normalized))
    return tuple(deduped)


def org_report_snapshot_dir_paths(snapshot_root: str | Path, org_id: Any = None) -> tuple[Path, ...]:
    """Return per-org snapshot directories beneath the persistent snapshot root."""
    root = Path(snapshot_root)
    if org_id is not None:
        return tuple(root / dir_key for dir_key in org_report_snapshot_dir_candidates(org_id))

    if not root.exists() or not root.is_dir():
        return ()
    return tuple(sorted(path for path in root.iterdir() if path.is_dir()))


def org_report_snapshot_search_dirs(cache_dir: str | Path, org_id: Any = None) -> tuple[Path, ...]:
    """Return directories that may contain org-report snapshots for one discovery request.

    Supports callers passing either:
    - the persistent snapshot root directory,
    - a specific per-org snapshot directory, or
    - a generic directory of JSON reports used in tests/manual workflows.
    """
    cache_path = Path(cache_dir)
    if org_id is None:
        if cache_path.name == ORG_REPORT_SNAPSHOT_ROOT_DIRNAME:
            return org_report_snapshot_dir_paths(cache_path)
        return (cache_path,)

    candidate_names = set(org_report_snapshot_dir_candidates(org_id))
    if cache_path.name == ORG_REPORT_SNAPSHOT_ROOT_DIRNAME:
        return org_report_snapshot_dir_paths(cache_path, org_id=org_id)
    if cache_path.name in candidate_names:
        return _dedupe_paths(cache_path.parent / dir_key for dir_key in org_report_snapshot_dir_candidates(org_id))
    return (cache_path,)


def iter_org_report_snapshot_files(cache_dir: str | Path, org_id: Any = None) -> tuple[Path, ...]:
    """Return JSON snapshot files for a discovery request, de-duplicated by path."""
    snapshot_files: list[Path] = []
    seen_paths: set[str] = set()

    for snapshot_dir in org_report_snapshot_search_dirs(cache_dir, org_id=org_id):
        if not snapshot_dir.exists() or not snapshot_dir.is_dir():
            continue
        for snapshot_file in sorted(snapshot_dir.glob("*.json")):
            normalized = snapshot_path_text(snapshot_file)
            if normalized in seen_paths:
                continue
            seen_paths.add(normalized)
            snapshot_files.append(Path(normalized))

    return tuple(snapshot_files)


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
        identities.append(("source_path", snapshot_path_text(source_path)))

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
