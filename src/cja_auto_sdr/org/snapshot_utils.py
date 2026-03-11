"""Shared helpers for org-report snapshot identity, parsing, retention, and ordering."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cja_auto_sdr.org.models import OrgReportComparisonInput

_EARLIEST_UTC = datetime.min.replace(tzinfo=UTC)
ORG_REPORT_SNAPSHOT_ROOT_DIRNAME = "org_report_snapshots"
_VOLATILE_ORG_REPORT_SNAPSHOT_KEYS = frozenset({"_snapshot_meta", "trending"})
LEGACY_MISSING_FIDELITY_MARKERS_REASON = "legacy_missing_fidelity_markers"


@dataclass(frozen=True)
class OrgReportSnapshotDataViewStats:
    """Normalized data-view population counts for one org-report snapshot."""

    reported_total: int
    analyzed_total: int
    failed_total: int
    raw_total: int
    successful_row_total: int


@dataclass(frozen=True)
class OrgReportSnapshotHistoryAssessment:
    """Normalized history-fidelity decision for one org-report payload."""

    eligible: bool
    exclusion_reason: str | None
    fidelity_known: bool


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


def sorted_snapshot_strings(values: Iterable[Any], *, limit: int | None = None) -> list[str]:
    """Return normalized string values in deterministic lexical order."""
    normalized = sorted(str(value) for value in values if value not in (None, ""))
    if limit is not None:
        return normalized[:limit]
    return normalized


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


def is_org_report_snapshot_root_dir(path: str | Path) -> bool:
    """Return True when a path is the persistent org-report snapshot root."""
    return Path(path).name == ORG_REPORT_SNAPSHOT_ROOT_DIRNAME


def org_report_snapshot_dedupe_key(
    *,
    org_id: Any = None,
    content_hash: Any = None,
    snapshot_id: Any = None,
    generated_at: Any = None,
    source_path: str | Path | None = None,
) -> tuple[str, ...]:
    """Return a stable key for de-duplicating equivalent org-report snapshots."""
    normalized_org_id = str(org_id or "unknown")
    if content_hash not in (None, ""):
        return ("content_hash", normalized_org_id, str(content_hash))
    if snapshot_id not in (None, ""):
        return ("snapshot_id", normalized_org_id, str(snapshot_id))
    return ("fallback", normalized_org_id, str(generated_at or ""), snapshot_path_text(source_path))


def org_report_snapshot_source_rank(source_path: str | Path | None, org_id: Any = None) -> int:
    """Return how strongly a snapshot path matches the preferred per-org layout."""
    normalized_path = snapshot_path_text(source_path)
    if not normalized_path:
        return 0

    parent_name = Path(normalized_path).parent.name
    candidate_names = org_report_snapshot_dir_candidates(org_id)
    for index, candidate_name in enumerate(candidate_names):
        if parent_name == candidate_name:
            return len(candidate_names) - index
    return 0


def org_report_snapshot_preference_key(
    *,
    org_id: Any = None,
    source_path: str | Path | None = None,
    snapshot_id: Any = None,
) -> tuple[int, int]:
    """Return a deterministic preference key for equivalent snapshot copies."""
    return (
        org_report_snapshot_source_rank(source_path, org_id),
        int(snapshot_id not in (None, "")),
    )


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


def coerce_snapshot_bool(value: Any) -> bool | None:
    """Best-effort boolean coercion for serialized org-report flags."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    if isinstance(value, str):
        stripped = value.strip().lower()
        if stripped in {"1", "true", "yes", "y", "on", "complete", "full"}:
            return True
        if stripped in {"0", "false", "no", "n", "off", "skipped", "partial", "incomplete"}:
            return False
    return None


def org_report_snapshot_history_exclusion_reason(data: Mapping[str, Any]) -> str | None:
    """Return the reason an org-report payload should stay out of trending history."""
    return org_report_snapshot_history_assessment(data).exclusion_reason


def _persisted_org_report_snapshot_history_assessment(
    data: Mapping[str, Any],
) -> OrgReportSnapshotHistoryAssessment | None:
    """Return any persisted history-fidelity decision stored in snapshot metadata."""
    snapshot_meta = snapshot_mapping_dict(data.get("_snapshot_meta", {}))
    explicit_history_eligible = coerce_snapshot_bool(snapshot_meta.get("history_eligible"))
    if explicit_history_eligible is None:
        return None
    if explicit_history_eligible:
        return OrgReportSnapshotHistoryAssessment(eligible=True, exclusion_reason=None, fidelity_known=True)
    explicit_reason = str(snapshot_meta.get("history_exclusion_reason") or "").strip()
    return OrgReportSnapshotHistoryAssessment(
        eligible=False,
        exclusion_reason=explicit_reason or "history_ineligible",
        fidelity_known=True,
    )


def _derived_org_report_snapshot_history_assessment(data: Mapping[str, Any]) -> OrgReportSnapshotHistoryAssessment:
    """Derive history fidelity from the snapshot payload itself."""
    summary = snapshot_mapping_dict(data.get("summary", {}))
    if coerce_snapshot_bool(summary.get("is_sampled")) is True:
        return OrgReportSnapshotHistoryAssessment(
            eligible=False,
            exclusion_reason="sampled",
            fidelity_known=True,
        )

    similarity_analysis_complete = coerce_snapshot_bool(summary.get("similarity_analysis_complete"))
    similarity_analysis_mode = str(summary.get("similarity_analysis_mode") or "").strip()
    if similarity_analysis_complete is False:
        return OrgReportSnapshotHistoryAssessment(
            eligible=False,
            exclusion_reason=similarity_analysis_mode or "similarity_incomplete",
            fidelity_known=True,
        )
    if similarity_analysis_complete is True:
        return OrgReportSnapshotHistoryAssessment(eligible=True, exclusion_reason=None, fidelity_known=True)
    if similarity_analysis_mode:
        return OrgReportSnapshotHistoryAssessment(
            eligible=similarity_analysis_mode == "complete",
            exclusion_reason=None if similarity_analysis_mode == "complete" else similarity_analysis_mode,
            fidelity_known=True,
        )

    parameters = snapshot_mapping_dict(data.get("parameters", {}))
    if coerce_snapshot_bool(parameters.get("org_stats_only")) is True:
        return OrgReportSnapshotHistoryAssessment(
            eligible=False,
            exclusion_reason="org_stats_only",
            fidelity_known=True,
        )
    if coerce_snapshot_bool(parameters.get("skip_similarity")) is True:
        return OrgReportSnapshotHistoryAssessment(
            eligible=False,
            exclusion_reason="skip_similarity",
            fidelity_known=True,
        )

    if "similarity_pairs" in data and data.get("similarity_pairs") is None:
        return OrgReportSnapshotHistoryAssessment(
            eligible=False,
            exclusion_reason="similarity_incomplete",
            fidelity_known=True,
        )

    if is_org_report_snapshot_payload(data):
        return OrgReportSnapshotHistoryAssessment(
            eligible=False,
            exclusion_reason=LEGACY_MISSING_FIDELITY_MARKERS_REASON,
            fidelity_known=False,
        )

    return OrgReportSnapshotHistoryAssessment(eligible=True, exclusion_reason=None, fidelity_known=False)


def _merged_org_report_snapshot_history_assessment(
    *,
    derived: OrgReportSnapshotHistoryAssessment,
    persisted: OrgReportSnapshotHistoryAssessment | None,
) -> OrgReportSnapshotHistoryAssessment:
    """Merge derived and persisted history-fidelity decisions with fail-closed semantics."""
    if not derived.eligible:
        return derived

    # Persisted metadata is advisory only: it may tighten eligibility, but it must
    # never widen eligibility because older cached snapshots can carry stale
    # `_snapshot_meta.history_eligible` values from earlier releases.
    if persisted is not None and not persisted.eligible:
        return persisted

    return derived


def org_report_snapshot_history_assessment(data: Mapping[str, Any]) -> OrgReportSnapshotHistoryAssessment:
    """Return the normalized history-fidelity assessment for one snapshot payload."""
    return _merged_org_report_snapshot_history_assessment(
        derived=_derived_org_report_snapshot_history_assessment(data),
        persisted=_persisted_org_report_snapshot_history_assessment(data),
    )


def org_report_snapshot_history_eligible(data: Mapping[str, Any]) -> bool:
    """Return True when an org-report payload should participate in trending history."""
    return org_report_snapshot_history_assessment(data).eligible


def coerce_snapshot_int(value: Any) -> int | None:
    """Best-effort integer coercion for serialized org-report counts."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return int(stripped)
        except ValueError:
            return None
    return None


def coerce_snapshot_float(value: Any) -> float | None:
    """Best-effort float coercion for serialized org-report metrics."""
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return None
        try:
            return float(stripped)
        except ValueError:
            return None
    return None


def snapshot_mapping_int(mapping: Mapping[str, Any], *keys: str) -> int | None:
    """Return the first integer-like value found in a mapping."""
    for key in keys:
        if key not in mapping:
            continue
        coerced = coerce_snapshot_int(mapping.get(key))
        if coerced is not None:
            return coerced
    return None


def snapshot_mapping_dict(value: Any) -> dict[str, Any]:
    """Return a dict-like value or a safe empty mapping."""
    if isinstance(value, Mapping):
        return dict(value)
    return {}


def snapshot_mapping_list(value: Any) -> list[Any]:
    """Return a list value or a safe empty list."""
    if isinstance(value, list):
        return value
    return []


def org_report_snapshot_timestamp(data: Mapping[str, Any]) -> str | None:
    """Return the normalized timestamp string for one org-report payload."""
    raw_timestamp = data.get("generated_at") or data.get("timestamp")
    if raw_timestamp in (None, ""):
        return None
    timestamp_text = str(raw_timestamp).strip()
    return timestamp_text or None


def is_org_report_snapshot_payload(data: Any) -> bool:
    """Return True when parsed JSON looks like an org-report snapshot payload."""
    if not isinstance(data, Mapping):
        return False
    if org_report_snapshot_timestamp(data) is None:
        return False
    if data.get("report_type") == "org_analysis":
        return True
    return any(
        (
            isinstance(data.get("summary"), Mapping),
            isinstance(data.get("distribution"), Mapping),
            isinstance(data.get("data_views"), list),
        ),
    )


def _canonical_snapshot_sort_key(value: Any) -> str:
    """Return a stable sort key for order-insensitive snapshot collections."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _canonicalize_snapshot_value(value: Any) -> Any:
    """Recursively normalize snapshot values for deterministic content hashing.

    Org-report snapshot hashing treats collection order as non-semantic so
    equivalent payloads remain stable across set iteration and differing input
    ordering from separate CLI processes.
    """
    if isinstance(value, Mapping):
        return {key: _canonicalize_snapshot_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set, frozenset)):
        normalized_items = [_canonicalize_snapshot_value(item) for item in value]
        return sorted(normalized_items, key=_canonical_snapshot_sort_key)
    return value


def canonical_org_report_snapshot_payload(report_data: Mapping[str, Any]) -> dict[str, Any]:
    """Return the stable payload used for org-report snapshot hashing."""
    return {
        key: _canonicalize_snapshot_value(value)
        for key, value in report_data.items()
        if key not in _VOLATILE_ORG_REPORT_SNAPSHOT_KEYS
    }


def org_report_snapshot_content_hash(report_data: Mapping[str, Any]) -> str:
    """Return a deterministic content hash for an org-report snapshot payload."""
    serialized = json.dumps(
        canonical_org_report_snapshot_payload(report_data),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def org_report_data_view_row_has_error(data_view: Any) -> bool:
    """Return True when a serialized data-view row represents a failed fetch."""
    if not isinstance(data_view, dict):
        return True
    if "error" not in data_view:
        return False
    return data_view.get("error") is not None


def successful_org_report_data_view_rows(data: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Return only successfully analyzed data-view rows from an org-report payload."""
    data_views = snapshot_mapping_list(data.get("data_views", []))
    return [
        data_view
        for data_view in data_views
        if isinstance(data_view, dict) and not org_report_data_view_row_has_error(data_view)
    ]


def org_report_snapshot_data_view_stats(data: Mapping[str, Any]) -> OrgReportSnapshotDataViewStats:
    """Return normalized reported/analyzed/failed counts for one snapshot payload."""
    summary = snapshot_mapping_dict(data.get("summary", {}))
    raw_data_views = snapshot_mapping_list(data.get("data_views", []))
    successful_data_views = successful_org_report_data_view_rows(data)

    raw_total = len(raw_data_views)
    successful_row_total = len(successful_data_views)

    analyzed_total = snapshot_mapping_int(summary, "data_views_analyzed")
    if analyzed_total is None:
        analyzed_total = successful_row_total
    analyzed_total = max(0, analyzed_total)

    explicit_reported_total = snapshot_mapping_int(summary, "data_views_total", "total_data_views")
    reported_candidates = [successful_row_total, analyzed_total]
    if raw_total > 0:
        reported_candidates.append(raw_total)
    if explicit_reported_total is not None:
        reported_candidates.append(max(0, explicit_reported_total))
    reported_total = max(reported_candidates, default=0)

    explicit_failed_total = snapshot_mapping_int(summary, "data_views_failed")
    if explicit_failed_total is None:
        explicit_failed_total = 0
    explicit_failed_total = max(0, explicit_failed_total)
    failed_total = max(
        explicit_failed_total,
        raw_total - successful_row_total,
        reported_total - analyzed_total,
        0,
    )

    return OrgReportSnapshotDataViewStats(
        reported_total=reported_total,
        analyzed_total=analyzed_total,
        failed_total=failed_total,
        raw_total=raw_total,
        successful_row_total=successful_row_total,
    )


def normalized_similarity_pair_ids(pair: Mapping[str, Any]) -> tuple[str, str] | None:
    """Extract a stable high-similarity pair identity from serialized report data."""
    dv1 = str(pair.get("dv1_id") or snapshot_mapping_dict(pair.get("data_view_1", {})).get("id") or "").strip()
    dv2 = str(pair.get("dv2_id") or snapshot_mapping_dict(pair.get("data_view_2", {})).get("id") or "").strip()
    if not dv1 or not dv2:
        return None
    return tuple(sorted((dv1, dv2)))


def effective_org_report_data_view_count(data: Mapping[str, Any]) -> int:
    """Return the snapshot headline data-view count."""
    return org_report_snapshot_data_view_stats(data).reported_total


def reported_org_report_data_view_count(data: Mapping[str, Any]) -> int | None:
    """Return the raw total-data-view count reported by the snapshot, if any."""
    summary = snapshot_mapping_dict(data.get("summary", {}))
    data_view_count = snapshot_mapping_int(summary, "data_views_total", "total_data_views")
    if data_view_count is not None:
        return data_view_count

    raw_data_views = snapshot_mapping_list(data.get("data_views", []))
    if raw_data_views:
        return len(raw_data_views)
    return None


def org_report_component_count(data: Mapping[str, Any]) -> int:
    """Return the total unique component count recorded in an org-report snapshot."""
    summary = snapshot_mapping_dict(data.get("summary", {}))
    return snapshot_mapping_int(summary, "total_unique_components") or 0


def org_report_core_count(data: Mapping[str, Any]) -> int:
    """Return the normalized core-component count recorded in an org-report snapshot."""
    distribution = snapshot_mapping_dict(data.get("distribution", {}))
    core_section = snapshot_mapping_dict(distribution.get("core", {}))
    core_count = snapshot_mapping_int(core_section, "total")
    if core_count is None:
        core_count = (snapshot_mapping_int(core_section, "metrics_count") or 0) + (
            snapshot_mapping_int(core_section, "dimensions_count") or 0
        )
    return core_count


def org_report_isolated_count(data: Mapping[str, Any]) -> int:
    """Return the normalized isolated-component count recorded in an org-report snapshot."""
    distribution = snapshot_mapping_dict(data.get("distribution", {}))
    isolated_section = snapshot_mapping_dict(distribution.get("isolated", {}))
    isolated_count = snapshot_mapping_int(isolated_section, "total")
    if isolated_count is None:
        isolated_count = (snapshot_mapping_int(isolated_section, "metrics_count") or 0) + (
            snapshot_mapping_int(isolated_section, "dimensions_count") or 0
        )
    return isolated_count


def org_report_high_similarity_pairs(
    data: Mapping[str, Any],
    *,
    threshold: float = 0.9,
) -> set[tuple[str, str]]:
    """Return stable data-view pair identities meeting the similarity threshold."""
    similarity_pairs: set[tuple[str, str]] = set()
    for pair in snapshot_mapping_list(data.get("similarity_pairs", [])):
        if not isinstance(pair, Mapping):
            continue
        if (coerce_snapshot_float(pair.get("jaccard_similarity")) or 0.0) < threshold:
            continue
        normalized_pair = normalized_similarity_pair_ids(pair)
        if normalized_pair is not None:
            similarity_pairs.add(normalized_pair)
    return similarity_pairs


def org_report_snapshot_comparison_input(
    data: Mapping[str, Any],
    *,
    require_history_eligible: bool = True,
) -> OrgReportComparisonInput:
    """Normalize one snapshot payload into comparison input fields."""
    metadata = org_report_snapshot_metadata(data)
    if metadata is None:
        raise ValueError("expected org-report snapshot payload")

    history_exclusion_reason = str(metadata.get("history_exclusion_reason") or "").strip()
    if require_history_eligible and history_exclusion_reason:
        raise ValueError(f"snapshot is not eligible for comparison: {history_exclusion_reason}")

    prev_dv_ids: set[str] = set()
    prev_dv_names: dict[str, str] = {}
    for dv in successful_org_report_data_view_rows(data):
        dv_id = str(dv.get("data_view_id") or dv.get("id") or "")
        if not dv_id:
            continue
        prev_dv_ids.add(dv_id)
        prev_dv_names[dv_id] = str(dv.get("data_view_name") or dv.get("name") or "Unknown")

    prev_component_ids = None
    prev_component_index = data.get("component_index")
    if isinstance(prev_component_index, dict):
        prev_component_ids = {str(component_id) for component_id in prev_component_index if str(component_id)}

    return OrgReportComparisonInput(
        timestamp=str(metadata["generated_at"]),
        data_view_ids=prev_dv_ids,
        has_data_view_ids=isinstance(data.get("data_views"), list),
        data_view_names=prev_dv_names,
        data_view_count=int(metadata["data_views_total"]),
        comparison_data_view_count=int(metadata["data_views_analyzed"]),
        component_count=int(metadata["total_unique_components"]),
        component_ids=prev_component_ids,
        core_count=int(metadata["core_count"]),
        isolated_count=int(metadata["isolated_count"]),
        high_similarity_pairs=org_report_high_similarity_pairs(data),
    )


def org_report_snapshot_metadata(
    data: Mapping[str, Any],
    *,
    source_path: str | Path | None = None,
    include_data_views: bool = False,
) -> dict[str, Any] | None:
    """Return normalized metadata for one org-report snapshot payload."""
    if not is_org_report_snapshot_payload(data):
        return None

    timestamp = org_report_snapshot_timestamp(data)
    assert timestamp is not None

    snapshot_meta = snapshot_mapping_dict(data.get("_snapshot_meta", {}))
    data_views = snapshot_mapping_list(data.get("data_views", []))
    source = Path(source_path) if source_path is not None else None
    data_view_stats = org_report_snapshot_data_view_stats(data)

    history_exclusion_reason = org_report_snapshot_history_exclusion_reason(data)

    metadata: dict[str, Any] = {
        "org_id": str(data.get("org_id") or "unknown"),
        "generated_at": timestamp,
        "generated_at_epoch": snapshot_epoch(timestamp),
        "filepath": snapshot_path_text(source),
        "filename": source.name if source is not None else "",
        "data_views_total": data_view_stats.reported_total,
        "data_views_analyzed": data_view_stats.analyzed_total,
        "data_views_failed": data_view_stats.failed_total,
        "data_views_total_reported": reported_org_report_data_view_count(data),
        "total_unique_components": org_report_component_count(data),
        "core_count": org_report_core_count(data),
        "isolated_count": org_report_isolated_count(data),
        "high_similarity_pairs": len(org_report_high_similarity_pairs(data)),
        "snapshot_id": snapshot_meta.get("snapshot_id"),
        "content_hash": snapshot_meta.get("content_hash") or org_report_snapshot_content_hash(data),
        "history_eligible": history_exclusion_reason is None,
        "history_exclusion_reason": history_exclusion_reason,
    }

    if include_data_views:
        data_view_names = [
            str(dv.get("data_view_name") or dv.get("name") or dv.get("data_view_id") or dv.get("id") or "")
            for dv in data_views
            if isinstance(dv, Mapping)
        ]
        data_view_names = [name for name in data_view_names if name]
        metadata["data_view_names_preview"] = data_view_names[:10]
        metadata["data_view_names_total"] = len(data_view_names)
        metadata["data_view_names_truncated"] = len(data_view_names) > 10

    return metadata
