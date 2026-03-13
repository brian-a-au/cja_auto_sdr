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

from cja_auto_sdr.org.identifiers import normalize_org_report_data_view_id
from cja_auto_sdr.org.models import OrgReportComparisonInput

_EARLIEST_UTC = datetime.min.replace(tzinfo=UTC)
ORG_REPORT_SNAPSHOT_ROOT_DIRNAME = "org_report_snapshots"
_VOLATILE_ORG_REPORT_SNAPSHOT_KEYS = frozenset({"_snapshot_meta", "trending"})
LEGACY_MISSING_FIDELITY_MARKERS_REASON = "legacy_missing_fidelity_markers"
INVALID_ORG_REPORT_SNAPSHOT_PAYLOAD_REASON = "invalid_snapshot_payload"


@dataclass(frozen=True)
class OrgReportSnapshotDataViewStats:
    """Normalized data-view population counts for one org-report snapshot."""

    reported_total: int
    analyzed_total: int
    failed_total: int
    raw_total: int
    successful_row_total: int


@dataclass(frozen=True)
class OrgReportSnapshotDataViewAssessment:
    """Normalized DV counts plus consistency checks for one snapshot payload."""

    stats: OrgReportSnapshotDataViewStats
    explicit_reported_total: int | None
    explicit_analyzed_total: int | None
    explicit_failed_total: int | None
    has_error_rows: bool
    rows_match_reported_total: bool
    successful_rows_match_analyzed_total: bool
    identified_row_total: int
    unique_id_total: int
    missing_id_rows: int
    duplicate_id_rows: int
    duplicate_successful_raw_id_rows: int
    ids_complete: bool
    coverage_complete: bool
    comparison_complete: bool
    history_complete: bool


@dataclass(frozen=True)
class OrgReportSnapshotComparisonAssessment:
    """Normalized comparison-fidelity decision for one org-report payload."""

    eligible: bool
    exclusion_reason: str | None
    complete_high_similarity_pairs: bool


@dataclass(frozen=True)
class OrgReportSnapshotHistoryAssessment:
    """Normalized history-fidelity decision for one org-report payload."""

    eligible: bool
    exclusion_reason: str | None
    fidelity_known: bool


@dataclass(frozen=True)
class OrgReportSnapshotDataViewInventory:
    """Normalized DV identities collected from serialized snapshot rows."""

    ids: frozenset[str]
    names: dict[str, str]
    normalized_ids: tuple[str, ...]
    missing_id_rows: int


@dataclass(frozen=True)
class _OrgReportSnapshotState:
    """Centralized normalized snapshot state shared across helpers."""

    timestamp: str | None
    org_id: str
    summary: dict[str, Any]
    distribution: dict[str, Any]
    snapshot_meta: dict[str, Any]
    raw_data_views: tuple[Any, ...]
    successful_data_views: tuple[dict[str, Any], ...]
    data_view_inventory: OrgReportSnapshotDataViewInventory
    raw_component_index: Any
    raw_similarity_rows: Any
    component_ids: frozenset[str] | None
    component_ids_loaded: bool
    high_similarity_pairs: frozenset[tuple[str, str]]
    high_similarity_pairs_loaded: bool
    reported_data_view_total: int | None
    component_count: int
    core_count: int
    isolated_count: int
    data_view_assessment: OrgReportSnapshotDataViewAssessment
    history_assessment: OrgReportSnapshotHistoryAssessment
    comparison_assessment: OrgReportSnapshotComparisonAssessment


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


def org_report_snapshot_history_exclusion_reason(data: Any) -> str | None:
    """Return the reason an org-report payload should stay out of trending history."""
    return org_report_snapshot_history_assessment(data).exclusion_reason


def _invalid_org_report_snapshot_history_assessment() -> OrgReportSnapshotHistoryAssessment:
    """Return the fail-closed history assessment for non-object JSON roots."""
    return OrgReportSnapshotHistoryAssessment(
        eligible=False,
        exclusion_reason=INVALID_ORG_REPORT_SNAPSHOT_PAYLOAD_REASON,
        fidelity_known=False,
    )


def _invalid_org_report_snapshot_comparison_assessment() -> OrgReportSnapshotComparisonAssessment:
    """Return the fail-closed comparison assessment for non-object JSON roots."""
    return OrgReportSnapshotComparisonAssessment(
        eligible=False,
        exclusion_reason=INVALID_ORG_REPORT_SNAPSHOT_PAYLOAD_REASON,
        complete_high_similarity_pairs=False,
    )


def _persisted_org_report_snapshot_history_assessment(
    snapshot_meta: Mapping[str, Any],
) -> OrgReportSnapshotHistoryAssessment | None:
    """Return any persisted history-fidelity decision stored in snapshot metadata."""
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


def _derived_org_report_snapshot_history_assessment(
    data: Mapping[str, Any],
    *,
    summary: Mapping[str, Any] | None = None,
    data_view_assessment: OrgReportSnapshotDataViewAssessment | None = None,
) -> OrgReportSnapshotHistoryAssessment:
    """Derive history fidelity from the snapshot payload itself."""
    summary = snapshot_mapping_dict(summary if summary is not None else data.get("summary", {}))
    data_view_assessment = (
        data_view_assessment if data_view_assessment is not None else org_report_snapshot_data_view_assessment(data)
    )

    def _incomplete_data_views() -> OrgReportSnapshotHistoryAssessment:
        return OrgReportSnapshotHistoryAssessment(
            eligible=False,
            exclusion_reason="incomplete_data_views",
            fidelity_known=True,
        )

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
        if not data_view_assessment.history_complete:
            return _incomplete_data_views()
        return OrgReportSnapshotHistoryAssessment(eligible=True, exclusion_reason=None, fidelity_known=True)
    if similarity_analysis_mode:
        if similarity_analysis_mode == "complete" and not data_view_assessment.history_complete:
            return _incomplete_data_views()
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


def org_report_snapshot_history_assessment(data: Any) -> OrgReportSnapshotHistoryAssessment:
    """Return the normalized history-fidelity assessment for one snapshot payload."""
    return _org_report_snapshot_state(data).history_assessment


def org_report_snapshot_history_eligible(data: Any) -> bool:
    """Return True when an org-report payload should participate in trending history."""
    return org_report_snapshot_history_assessment(data).eligible


def _derived_org_report_snapshot_comparison_assessment(
    data: Mapping[str, Any],
    *,
    summary: Mapping[str, Any] | None = None,
    data_view_assessment: OrgReportSnapshotDataViewAssessment | None = None,
    derived_history: OrgReportSnapshotHistoryAssessment | None = None,
) -> OrgReportSnapshotComparisonAssessment:
    """Derive point-in-time comparison fidelity from the snapshot payload itself.

    Direct comparison requires complete row coverage plus analyzer-safe raw DV
    identities. Exact DV identity deltas and high-similarity pair deltas are
    gated separately by the completeness flags carried into
    OrgReportComparisonInput.
    """
    summary = snapshot_mapping_dict(summary if summary is not None else data.get("summary", {}))
    if coerce_snapshot_bool(summary.get("is_sampled")) is True:
        return OrgReportSnapshotComparisonAssessment(
            eligible=False,
            exclusion_reason="sampled",
            complete_high_similarity_pairs=False,
        )

    data_view_assessment = (
        data_view_assessment if data_view_assessment is not None else org_report_snapshot_data_view_assessment(data)
    )
    if not data_view_assessment.comparison_complete:
        return OrgReportSnapshotComparisonAssessment(
            eligible=False,
            exclusion_reason="incomplete_data_views",
            complete_high_similarity_pairs=False,
        )

    derived_history = (
        derived_history if derived_history is not None else _derived_org_report_snapshot_history_assessment(data)
    )
    if derived_history.exclusion_reason == LEGACY_MISSING_FIDELITY_MARKERS_REASON:
        return OrgReportSnapshotComparisonAssessment(
            eligible=False,
            exclusion_reason=LEGACY_MISSING_FIDELITY_MARKERS_REASON,
            complete_high_similarity_pairs=False,
        )

    return OrgReportSnapshotComparisonAssessment(
        eligible=True,
        exclusion_reason=None,
        complete_high_similarity_pairs=derived_history.eligible,
    )


def _persisted_org_report_snapshot_comparison_assessment(
    *,
    snapshot_meta: Mapping[str, Any],
    derived_history: OrgReportSnapshotHistoryAssessment,
    persisted_history: OrgReportSnapshotHistoryAssessment | None = None,
) -> OrgReportSnapshotComparisonAssessment | None:
    """Return any persisted comparison-tightening decision stored in snapshot metadata."""
    persisted = (
        persisted_history
        if persisted_history is not None
        else _persisted_org_report_snapshot_history_assessment(snapshot_meta)
    )
    if persisted is None or persisted.eligible:
        return None

    explicit_reason = str(snapshot_meta.get("history_exclusion_reason") or "").strip()

    # History metadata should not block point-in-time comparison when it merely
    # restates a payload-derived history-only exclusion such as skip-similarity.
    if not derived_history.eligible and (not explicit_reason or explicit_reason == derived_history.exclusion_reason):
        return None

    return OrgReportSnapshotComparisonAssessment(
        eligible=False,
        exclusion_reason=persisted.exclusion_reason,
        complete_high_similarity_pairs=False,
    )


def _merged_org_report_snapshot_comparison_assessment(
    *,
    derived: OrgReportSnapshotComparisonAssessment,
    persisted: OrgReportSnapshotComparisonAssessment | None,
) -> OrgReportSnapshotComparisonAssessment:
    """Merge derived and persisted comparison-fidelity decisions with fail-closed semantics."""
    if not derived.eligible:
        return derived

    # Persisted metadata may tighten direct-comparison eligibility, but it must
    # not widen it because older cached snapshots can carry stale positive flags.
    if persisted is not None and not persisted.eligible:
        return persisted

    return derived


def org_report_snapshot_comparison_assessment(data: Any) -> OrgReportSnapshotComparisonAssessment:
    """Return the normalized comparison-fidelity assessment for one snapshot payload."""
    return _org_report_snapshot_state(data).comparison_assessment


def org_report_snapshot_comparison_eligible(data: Any) -> bool:
    """Return True when an org-report payload supports point-in-time comparison."""
    return org_report_snapshot_comparison_assessment(data).eligible


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


def _non_negative_snapshot_mapping_int(mapping: Mapping[str, Any], *keys: str) -> int | None:
    """Return the first integer-like mapping value, clamped to zero or higher."""
    value = snapshot_mapping_int(mapping, *keys)
    if value is None:
        return None
    return max(0, value)


def org_report_snapshot_timestamp(data: Any) -> str | None:
    """Return the normalized timestamp string for one org-report payload."""
    payload = snapshot_mapping_dict(data)
    raw_timestamp = payload.get("generated_at") or payload.get("timestamp")
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


@dataclass(frozen=True)
class _SnapshotIdAliasResolution:
    """Resolved serialized snapshot ID alias after defensive validation."""

    raw: str | None
    normalized: str


def _resolve_snapshot_id_alias(*candidates: tuple[bool, Any]) -> _SnapshotIdAliasResolution:
    """Resolve one snapshot ID across a prioritized alias list.

    Only string aliases are considered valid snapshot identifiers. Blank-string
    aliases fall through to later populated aliases so mixed legacy/current
    payloads can still recover a stable ID, but if every present string alias is
    blank-like we preserve one explicit blank marker so raw-ID collision checks
    still fail closed on repeated blank identifiers.
    """
    blank_alias_seen = False
    for present, value in candidates:
        if not present or not isinstance(value, str):
            continue
        normalized = normalize_org_report_data_view_id(value)
        if normalized:
            return _SnapshotIdAliasResolution(raw=value, normalized=normalized)
        blank_alias_seen = True
    if blank_alias_seen:
        return _SnapshotIdAliasResolution(raw="", normalized="")
    return _SnapshotIdAliasResolution(raw=None, normalized="")


def org_report_data_view_row_id(data_view: Mapping[str, Any]) -> str:
    """Extract one normalized data-view identifier from a serialized row."""
    return _resolve_snapshot_id_alias(
        ("data_view_id" in data_view, data_view.get("data_view_id")),
        ("id" in data_view, data_view.get("id")),
    ).normalized


def org_report_data_view_row_raw_id(data_view: Mapping[str, Any]) -> str | None:
    """Extract the analyzer-facing raw DV ID token from a serialized row.

    Returns None only when the row has no DV ID field at all. Blank aliases
    fall through to later populated aliases, but if every explicit alias is
    blank-like we preserve an empty-string token so collision checks can still
    fail closed on repeated blank IDs.
    """
    return _resolve_snapshot_id_alias(
        ("data_view_id" in data_view, data_view.get("data_view_id")),
        ("id" in data_view, data_view.get("id")),
    ).raw


def org_report_data_view_row_has_error(data_view: Any) -> bool:
    """Return True when a serialized data-view row represents a failed fetch."""
    if not isinstance(data_view, dict):
        return True
    if "error" not in data_view:
        return False
    return data_view.get("error") is not None


def _successful_snapshot_data_view_rows(raw_data_views: Iterable[Any]) -> list[dict[str, Any]]:
    """Return successful DV rows from already-normalized raw snapshot rows."""
    return [
        data_view
        for data_view in raw_data_views
        if isinstance(data_view, dict) and not org_report_data_view_row_has_error(data_view)
    ]


def successful_org_report_data_view_rows(data: Any) -> list[dict[str, Any]]:
    """Return only successfully analyzed data-view rows from an org-report payload."""
    payload = snapshot_mapping_dict(data)
    data_views = snapshot_mapping_list(payload.get("data_views", []))
    return _successful_snapshot_data_view_rows(data_views)


def _collect_snapshot_data_view_inventory(raw_data_views: Iterable[Any]) -> OrgReportSnapshotDataViewInventory:
    """Collect normalized DV identifiers and names from serialized snapshot rows."""
    data_view_ids: set[str] = set()
    data_view_names: dict[str, str] = {}
    normalized_ids: list[str] = []
    missing_id_rows = 0

    for data_view in raw_data_views:
        if not isinstance(data_view, Mapping):
            missing_id_rows += 1
            continue
        data_view_id = org_report_data_view_row_id(data_view)
        if not data_view_id:
            missing_id_rows += 1
            continue
        normalized_ids.append(data_view_id)
        data_view_ids.add(data_view_id)
        data_view_names[data_view_id] = str(data_view.get("data_view_name") or data_view.get("name") or data_view_id)

    return OrgReportSnapshotDataViewInventory(
        ids=frozenset(data_view_ids),
        names=data_view_names,
        normalized_ids=tuple(normalized_ids),
        missing_id_rows=missing_id_rows,
    )


def _build_org_report_snapshot_data_view_assessment(
    *,
    payload_is_mapping: bool,
    summary: Mapping[str, Any],
    raw_data_views: tuple[Any, ...],
    successful_data_views: tuple[dict[str, Any], ...],
    data_view_inventory: OrgReportSnapshotDataViewInventory,
) -> OrgReportSnapshotDataViewAssessment:
    """Build the DV assessment from normalized snapshot row state."""
    raw_total = len(raw_data_views)
    successful_row_total = len(successful_data_views)
    has_error_rows = raw_total != successful_row_total

    explicit_analyzed_total = _non_negative_snapshot_mapping_int(summary, "data_views_analyzed")
    analyzed_total = successful_row_total if explicit_analyzed_total is None else explicit_analyzed_total

    explicit_reported_total = _non_negative_snapshot_mapping_int(summary, "data_views_total", "total_data_views")
    reported_candidates = [successful_row_total, analyzed_total]
    if raw_total > 0:
        reported_candidates.append(raw_total)
    if explicit_reported_total is not None:
        reported_candidates.append(explicit_reported_total)
    reported_total = max(reported_candidates, default=0)

    explicit_failed_total = _non_negative_snapshot_mapping_int(summary, "data_views_failed")
    failed_total = max(
        explicit_failed_total or 0,
        raw_total - successful_row_total,
        reported_total - analyzed_total,
        0,
    )

    stats = OrgReportSnapshotDataViewStats(
        reported_total=reported_total,
        analyzed_total=analyzed_total,
        failed_total=failed_total,
        raw_total=raw_total,
        successful_row_total=successful_row_total,
    )
    rows_match_reported_total = payload_is_mapping and (
        explicit_reported_total is None or raw_total == explicit_reported_total
    )
    successful_rows_match_analyzed_total = payload_is_mapping and (
        explicit_analyzed_total is None or successful_row_total == explicit_analyzed_total
    )

    identified_row_total = len(data_view_inventory.normalized_ids)
    unique_id_total = len(data_view_inventory.ids)
    duplicate_id_rows = identified_row_total - unique_id_total
    successful_raw_id_tokens = [
        raw_id
        for data_view in successful_data_views
        if (raw_id := org_report_data_view_row_raw_id(data_view)) is not None
    ]
    duplicate_successful_raw_id_rows = len(successful_raw_id_tokens) - len(set(successful_raw_id_tokens))
    ids_complete = payload_is_mapping and (
        data_view_inventory.missing_id_rows == 0 and duplicate_id_rows == 0 and unique_id_total == stats.reported_total
    )

    coverage_complete = payload_is_mapping and (
        not has_error_rows
        and (explicit_failed_total is None or explicit_failed_total == 0)
        and rows_match_reported_total
        and successful_rows_match_analyzed_total
    )
    # Direct comparison can tolerate incomplete stable IDs, but not evidence that
    # analyzer-facing raw IDs collided across successful rows because that can
    # already skew component and distribution counts in serialized org reports.
    comparison_complete = coverage_complete and duplicate_successful_raw_id_rows == 0
    history_complete = comparison_complete and ids_complete

    return OrgReportSnapshotDataViewAssessment(
        stats=stats,
        explicit_reported_total=explicit_reported_total,
        explicit_analyzed_total=explicit_analyzed_total,
        explicit_failed_total=explicit_failed_total,
        has_error_rows=has_error_rows,
        rows_match_reported_total=rows_match_reported_total,
        successful_rows_match_analyzed_total=successful_rows_match_analyzed_total,
        identified_row_total=identified_row_total,
        unique_id_total=unique_id_total,
        missing_id_rows=data_view_inventory.missing_id_rows,
        duplicate_id_rows=duplicate_id_rows,
        duplicate_successful_raw_id_rows=duplicate_successful_raw_id_rows,
        ids_complete=ids_complete,
        coverage_complete=coverage_complete,
        comparison_complete=comparison_complete,
        history_complete=history_complete,
    )


def org_report_snapshot_data_view_assessment(data: Any) -> OrgReportSnapshotDataViewAssessment:
    """Return normalized DV counts plus consistency checks for one snapshot payload."""
    payload_is_mapping = isinstance(data, Mapping)
    payload = snapshot_mapping_dict(data)
    summary = snapshot_mapping_dict(payload.get("summary", {}))
    raw_data_views = tuple(snapshot_mapping_list(payload.get("data_views", [])))
    successful_data_views = tuple(_successful_snapshot_data_view_rows(raw_data_views))
    data_view_inventory = _collect_snapshot_data_view_inventory(raw_data_views)

    return _build_org_report_snapshot_data_view_assessment(
        payload_is_mapping=payload_is_mapping,
        summary=summary,
        raw_data_views=raw_data_views,
        successful_data_views=successful_data_views,
        data_view_inventory=data_view_inventory,
    )


def org_report_snapshot_data_view_stats(data: Mapping[str, Any]) -> OrgReportSnapshotDataViewStats:
    """Return normalized reported/analyzed/failed counts for one snapshot payload."""
    return org_report_snapshot_data_view_assessment(data).stats


def org_report_snapshot_has_complete_data_view_coverage(data: Mapping[str, Any]) -> bool:
    """Return True when DV rows and summary counts agree on full snapshot coverage."""
    return org_report_snapshot_data_view_assessment(data).coverage_complete


def org_report_snapshot_has_complete_data_view_ids(data: Mapping[str, Any]) -> bool:
    """Return True when every reported data view has a unique, normalized stable ID."""
    return org_report_snapshot_data_view_assessment(data).ids_complete


def normalized_similarity_pair_ids(pair: Mapping[str, Any]) -> tuple[str, str] | None:
    """Extract a stable high-similarity pair identity from serialized report data."""
    data_view_1 = snapshot_mapping_dict(pair.get("data_view_1", {}))
    data_view_2 = snapshot_mapping_dict(pair.get("data_view_2", {}))
    dv1 = _resolve_snapshot_id_alias(
        ("dv1_id" in pair, pair.get("dv1_id")),
        ("id" in data_view_1, data_view_1.get("id")),
    ).normalized
    dv2 = _resolve_snapshot_id_alias(
        ("dv2_id" in pair, pair.get("dv2_id")),
        ("id" in data_view_2, data_view_2.get("id")),
    ).normalized
    if not dv1 or not dv2 or dv1 == dv2:
        return None
    return tuple(sorted((dv1, dv2)))


def _org_report_high_similarity_pairs_from_rows(
    similarity_rows: Iterable[Any],
    *,
    threshold: float = 0.9,
) -> set[tuple[str, str]]:
    """Return stable high-similarity pairs from pre-normalized snapshot rows."""
    similarity_pairs: set[tuple[str, str]] = set()
    for pair in similarity_rows:
        if not isinstance(pair, Mapping):
            continue
        if (coerce_snapshot_float(pair.get("jaccard_similarity")) or 0.0) < threshold:
            continue
        normalized_pair = normalized_similarity_pair_ids(pair)
        if normalized_pair is not None:
            similarity_pairs.add(normalized_pair)
    return similarity_pairs


def effective_org_report_data_view_count(data: Mapping[str, Any]) -> int:
    """Return the snapshot headline data-view count."""
    return org_report_snapshot_data_view_stats(data).reported_total


def reported_org_report_data_view_count(data: Any) -> int | None:
    """Return the raw total-data-view count reported by the snapshot, if any."""
    payload = snapshot_mapping_dict(data)
    summary = snapshot_mapping_dict(payload.get("summary", {}))
    raw_data_views = tuple(snapshot_mapping_list(payload.get("data_views", [])))
    return _reported_org_report_data_view_count(summary, raw_data_views)


def _reported_org_report_data_view_count(
    summary: Mapping[str, Any],
    raw_data_views: tuple[Any, ...],
) -> int | None:
    """Return the raw total-data-view count from normalized snapshot state."""
    data_view_count = snapshot_mapping_int(summary, "data_views_total", "total_data_views")
    if data_view_count is not None:
        return data_view_count

    if raw_data_views:
        return len(raw_data_views)
    return None


def org_report_component_count(data: Any) -> int:
    """Return the total unique component count recorded in an org-report snapshot."""
    payload = snapshot_mapping_dict(data)
    return _org_report_component_count(snapshot_mapping_dict(payload.get("summary", {})))


def _org_report_component_count(summary: Mapping[str, Any]) -> int:
    """Return the total unique component count from normalized snapshot summary."""
    return snapshot_mapping_int(summary, "total_unique_components") or 0


def org_report_core_count(data: Any) -> int:
    """Return the normalized core-component count recorded in an org-report snapshot."""
    payload = snapshot_mapping_dict(data)
    return _org_report_core_count(snapshot_mapping_dict(payload.get("distribution", {})))


def _org_report_core_count(distribution: Mapping[str, Any]) -> int:
    """Return the normalized core-component count from normalized distribution data."""
    core_section = snapshot_mapping_dict(distribution.get("core", {}))
    core_count = snapshot_mapping_int(core_section, "total")
    if core_count is None:
        core_count = (snapshot_mapping_int(core_section, "metrics_count") or 0) + (
            snapshot_mapping_int(core_section, "dimensions_count") or 0
        )
    return core_count


def org_report_isolated_count(data: Any) -> int:
    """Return the normalized isolated-component count recorded in an org-report snapshot."""
    payload = snapshot_mapping_dict(data)
    return _org_report_isolated_count(snapshot_mapping_dict(payload.get("distribution", {})))


def _org_report_isolated_count(distribution: Mapping[str, Any]) -> int:
    """Return the normalized isolated-component count from normalized distribution data."""
    isolated_section = snapshot_mapping_dict(distribution.get("isolated", {}))
    isolated_count = snapshot_mapping_int(isolated_section, "total")
    if isolated_count is None:
        isolated_count = (snapshot_mapping_int(isolated_section, "metrics_count") or 0) + (
            snapshot_mapping_int(isolated_section, "dimensions_count") or 0
        )
    return isolated_count


def org_report_high_similarity_pairs(
    data: Any,
    *,
    threshold: float = 0.9,
) -> set[tuple[str, str]]:
    """Return stable data-view pair identities meeting the similarity threshold."""
    payload = snapshot_mapping_dict(data)
    return _org_report_high_similarity_pairs_from_rows(
        snapshot_mapping_list(payload.get("similarity_pairs", [])),
        threshold=threshold,
    )


def _snapshot_component_ids(raw_component_index: Any) -> frozenset[str] | None:
    """Return normalized component IDs from a serialized component index."""
    if not isinstance(raw_component_index, dict):
        return None
    return frozenset(str(component_id) for component_id in raw_component_index if str(component_id))


def _state_component_ids(state: _OrgReportSnapshotState) -> frozenset[str] | None:
    """Return component IDs, using precomputed state when available."""
    if state.component_ids_loaded:
        return state.component_ids
    return _snapshot_component_ids(state.raw_component_index)


def _state_high_similarity_pairs(
    state: _OrgReportSnapshotState,
    *,
    threshold: float = 0.9,
) -> frozenset[tuple[str, str]]:
    """Return high-similarity pairs, using precomputed state at the default threshold."""
    if threshold == 0.9 and state.high_similarity_pairs_loaded:
        return state.high_similarity_pairs
    return frozenset(
        _org_report_high_similarity_pairs_from_rows(
            snapshot_mapping_list(state.raw_similarity_rows),
            threshold=threshold,
        )
    )


def _org_report_snapshot_state(
    data: Any,
    *,
    include_component_ids: bool = False,
    include_high_similarity_pairs: bool = False,
) -> _OrgReportSnapshotState:
    """Build the centralized normalized snapshot state used across helpers."""
    payload_is_mapping = isinstance(data, Mapping)
    payload = snapshot_mapping_dict(data)
    summary = snapshot_mapping_dict(payload.get("summary", {}))
    distribution = snapshot_mapping_dict(payload.get("distribution", {}))
    snapshot_meta = snapshot_mapping_dict(payload.get("_snapshot_meta", {}))
    raw_component_index = payload.get("component_index")
    raw_similarity_rows = payload.get("similarity_pairs")
    raw_data_views = tuple(snapshot_mapping_list(payload.get("data_views", [])))
    successful_data_views = tuple(_successful_snapshot_data_view_rows(raw_data_views))
    data_view_inventory = _collect_snapshot_data_view_inventory(raw_data_views)
    data_view_assessment = _build_org_report_snapshot_data_view_assessment(
        payload_is_mapping=payload_is_mapping,
        summary=summary,
        raw_data_views=raw_data_views,
        successful_data_views=successful_data_views,
        data_view_inventory=data_view_inventory,
    )

    if payload_is_mapping:
        derived_history = _derived_org_report_snapshot_history_assessment(
            payload,
            summary=summary,
            data_view_assessment=data_view_assessment,
        )
        persisted_history = _persisted_org_report_snapshot_history_assessment(snapshot_meta)
        history_assessment = _merged_org_report_snapshot_history_assessment(
            derived=derived_history,
            persisted=persisted_history,
        )
        comparison_assessment = _merged_org_report_snapshot_comparison_assessment(
            derived=_derived_org_report_snapshot_comparison_assessment(
                payload,
                summary=summary,
                data_view_assessment=data_view_assessment,
                derived_history=derived_history,
            ),
            persisted=_persisted_org_report_snapshot_comparison_assessment(
                snapshot_meta=snapshot_meta,
                derived_history=derived_history,
                persisted_history=persisted_history,
            ),
        )
    else:
        history_assessment = _invalid_org_report_snapshot_history_assessment()
        comparison_assessment = _invalid_org_report_snapshot_comparison_assessment()

    return _OrgReportSnapshotState(
        timestamp=org_report_snapshot_timestamp(payload),
        org_id=str(payload.get("org_id") or "unknown"),
        summary=summary,
        distribution=distribution,
        snapshot_meta=snapshot_meta,
        raw_data_views=raw_data_views,
        successful_data_views=successful_data_views,
        data_view_inventory=data_view_inventory,
        raw_component_index=raw_component_index,
        raw_similarity_rows=raw_similarity_rows,
        component_ids=_snapshot_component_ids(raw_component_index) if include_component_ids else None,
        component_ids_loaded=include_component_ids,
        high_similarity_pairs=(
            frozenset(_org_report_high_similarity_pairs_from_rows(snapshot_mapping_list(raw_similarity_rows)))
            if include_high_similarity_pairs
            else frozenset()
        ),
        high_similarity_pairs_loaded=include_high_similarity_pairs,
        reported_data_view_total=_reported_org_report_data_view_count(summary, raw_data_views),
        component_count=_org_report_component_count(summary),
        core_count=_org_report_core_count(distribution),
        isolated_count=_org_report_isolated_count(distribution),
        data_view_assessment=data_view_assessment,
        history_assessment=history_assessment,
        comparison_assessment=comparison_assessment,
    )


def org_report_snapshot_comparison_input(
    data: Any,
    *,
    require_history_eligible: bool = True,
    require_comparison_eligible: bool = False,
) -> OrgReportComparisonInput:
    """Normalize one snapshot payload into comparison input fields.

    Data-view identities include failed rows when those rows still expose a
    stable ID. This preserves the full known snapshot population for identity
    deltas even when point-in-time analysis coverage was partial. Direct
    comparison requires full row coverage and no raw-ID collisions that could
    skew serialized component/distribution totals, but exact DV add/remove
    lists still degrade gracefully via complete_data_view_ids=False when some
    rows lack a stable unique ID.
    """
    state = _org_report_snapshot_state(
        data,
        include_component_ids=True,
        include_high_similarity_pairs=True,
    )
    if not is_org_report_snapshot_payload(data) or state.timestamp is None:
        raise ValueError("expected org-report snapshot payload")

    history_exclusion_reason = str(state.history_assessment.exclusion_reason or "").strip()
    if require_history_eligible and history_exclusion_reason:
        raise ValueError(f"snapshot is not eligible for comparison: {history_exclusion_reason}")
    if require_comparison_eligible and not state.comparison_assessment.eligible:
        raise ValueError(
            "snapshot is not eligible for comparison: "
            f"{state.comparison_assessment.exclusion_reason or 'comparison_ineligible'}"
        )

    component_ids = _state_component_ids(state)
    high_similarity_pairs = _state_high_similarity_pairs(state)

    return OrgReportComparisonInput(
        timestamp=state.timestamp,
        data_view_ids=set(state.data_view_inventory.ids),
        has_data_view_ids=bool(state.data_view_inventory.ids),
        complete_data_view_ids=state.data_view_assessment.ids_complete,
        data_view_names=dict(state.data_view_inventory.names),
        data_view_count=state.data_view_assessment.stats.reported_total,
        comparison_data_view_count=state.data_view_assessment.stats.analyzed_total,
        component_count=state.component_count,
        component_ids=None if component_ids is None else set(component_ids),
        core_count=state.core_count,
        isolated_count=state.isolated_count,
        high_similarity_pairs=set(high_similarity_pairs),
        complete_high_similarity_pairs=state.comparison_assessment.complete_high_similarity_pairs,
    )


def _org_report_snapshot_metadata_from_state(
    data: Any,
    *,
    state: _OrgReportSnapshotState,
    source_path: str | Path | None = None,
    include_data_views: bool = False,
) -> dict[str, Any] | None:
    """Render snapshot metadata from centralized normalized snapshot state."""
    if not is_org_report_snapshot_payload(data) or state.timestamp is None:
        return None

    source = Path(source_path) if source_path is not None else None
    data_view_stats = state.data_view_assessment.stats
    high_similarity_pairs = _state_high_similarity_pairs(state)
    metadata: dict[str, Any] = {
        "org_id": state.org_id,
        "generated_at": state.timestamp,
        "generated_at_epoch": snapshot_epoch(state.timestamp),
        "filepath": snapshot_path_text(source),
        "filename": source.name if source is not None else "",
        "data_views_total": data_view_stats.reported_total,
        "data_views_analyzed": data_view_stats.analyzed_total,
        "data_views_failed": data_view_stats.failed_total,
        "data_views_total_reported": state.reported_data_view_total,
        "total_unique_components": state.component_count,
        "core_count": state.core_count,
        "isolated_count": state.isolated_count,
        "high_similarity_pairs": len(high_similarity_pairs),
        "snapshot_id": state.snapshot_meta.get("snapshot_id"),
        "content_hash": state.snapshot_meta.get("content_hash") or org_report_snapshot_content_hash(data),
        "history_eligible": state.history_assessment.exclusion_reason is None,
        "history_exclusion_reason": state.history_assessment.exclusion_reason,
    }

    if include_data_views:
        data_view_names = [
            str(dv.get("data_view_name") or dv.get("name") or dv.get("data_view_id") or dv.get("id") or "")
            for dv in state.raw_data_views
            if isinstance(dv, Mapping)
        ]
        data_view_names = [name for name in data_view_names if name]
        metadata["data_view_names_preview"] = data_view_names[:10]
        metadata["data_view_names_total"] = len(data_view_names)
        metadata["data_view_names_truncated"] = len(data_view_names) > 10

    return metadata


def _resolve_org_report_snapshot_state(
    data: Any,
    *,
    state: _OrgReportSnapshotState | None = None,
) -> _OrgReportSnapshotState:
    """Return a caller-provided snapshot state or build it on demand."""
    if state is not None:
        return state
    return _org_report_snapshot_state(data)


def org_report_snapshot_metadata(
    data: Any,
    *,
    state: _OrgReportSnapshotState | None = None,
    source_path: str | Path | None = None,
    include_data_views: bool = False,
) -> dict[str, Any] | None:
    """Return normalized metadata for one org-report snapshot payload."""
    return _org_report_snapshot_metadata_from_state(
        data,
        state=_resolve_org_report_snapshot_state(data, state=state),
        source_path=source_path,
        include_data_views=include_data_views,
    )
