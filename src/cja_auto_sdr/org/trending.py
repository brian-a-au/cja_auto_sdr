"""Org-report trending: snapshot discovery, delta computation, and drift scoring."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from cja_auto_sdr.org.models import (
    OrgReportTrending,
    TrendingDelta,
    TrendingSnapshot,
    _snapshot_effective_data_view_count,
)
from cja_auto_sdr.org.snapshot_utils import (
    _org_report_snapshot_state,
    chronological_snapshot_sort_fields,
    coerce_snapshot_float,
    is_org_report_snapshot_payload,
    is_org_report_snapshot_root_dir,
    iter_org_report_snapshot_files,
    normalize_org_report_data_view_id,
    normalized_similarity_pair_ids,
    org_report_data_view_row_has_error,
    org_report_data_view_row_id,
    org_report_snapshot_content_hash,
    org_report_snapshot_dedupe_key,
    org_report_snapshot_metadata,
    org_report_snapshot_preference_key,
    snapshot_identity_tokens,
    snapshot_mapping_dict,
    snapshot_mapping_int,
    snapshot_mapping_list,
)

logger = logging.getLogger(__name__)

_mapping_dict = snapshot_mapping_dict
_mapping_int = snapshot_mapping_int
_mapping_list = snapshot_mapping_list


def _snapshot_identity_tokens(snapshot: TrendingSnapshot) -> tuple[tuple[str, ...], ...]:
    """Return all stable identities available for one snapshot."""
    return snapshot_identity_tokens(
        snapshot_id=snapshot.snapshot_id,
        content_hash=snapshot.content_hash,
        source_path=snapshot.source_path,
        fallback_parts=(snapshot.org_id or "", snapshot.timestamp),
    )


def _snapshot_identity_key(snapshot: TrendingSnapshot) -> tuple[str, ...]:
    """Return the logical identity for one trending snapshot."""
    return org_report_snapshot_dedupe_key(
        org_id=snapshot.org_id,
        content_hash=snapshot.content_hash,
        snapshot_id=snapshot.snapshot_id,
        generated_at=snapshot.timestamp,
        source_path=snapshot.source_path,
    )


def _snapshot_preference(snapshot: TrendingSnapshot) -> tuple[int, int]:
    """Return how strongly one snapshot copy should be preferred."""
    return org_report_snapshot_preference_key(
        org_id=snapshot.org_id,
        source_path=snapshot.source_path,
        snapshot_id=snapshot.snapshot_id,
    )


def _snapshot_sort_key(snapshot: TrendingSnapshot) -> tuple[bool, object, str, str]:
    """Return the sort key for oldest-to-newest snapshot ordering."""
    tie_breaker = snapshot.source_path or snapshot.snapshot_id or snapshot.content_hash or ""
    return chronological_snapshot_sort_fields(snapshot.timestamp, tie_breaker=tie_breaker)


def _snapshots_equivalent(left: TrendingSnapshot, right: TrendingSnapshot) -> bool:
    """Return True when two snapshot objects describe the same persisted state."""
    if left.org_id != right.org_id or left.timestamp != right.timestamp:
        return False
    if left.snapshot_id and right.snapshot_id:
        return left.snapshot_id == right.snapshot_id
    if left.content_hash and right.content_hash:
        return left.content_hash == right.content_hash
    return (
        left.data_view_count == right.data_view_count
        and left.analyzed_data_view_count == right.analyzed_data_view_count
        and left.component_count == right.component_count
        and left.core_count == right.core_count
        and left.isolated_count == right.isolated_count
        and left.high_sim_pair_count == right.high_sim_pair_count
        and left.dv_component_counts == right.dv_component_counts
        and left.dv_core_ratios == right.dv_core_ratios
        and left.dv_max_similarity == right.dv_max_similarity
        and left.dv_ids == right.dv_ids
        and left.dv_names == right.dv_names
    )


def _resolve_explicit_snapshot_identities(
    explicit_file: str | Path | None,
    *,
    org_id: str | None = None,
) -> set[tuple[str, ...]]:
    """Return identity aliases for explicitly requested comparison snapshots."""
    if explicit_file is None:
        return set()

    snapshot = _load_snapshot_from_file(Path(explicit_file))
    if snapshot is None:
        return set()
    if org_id is not None and snapshot.org_id != org_id:
        return set()
    return set(_snapshot_identity_tokens(snapshot))


def _trim_snapshot_window(
    snapshots: list[TrendingSnapshot],
    *,
    window_size: int,
    pinned_snapshot_identities: set[tuple[str, ...]] | None = None,
) -> list[TrendingSnapshot]:
    """Return an oldest-to-newest window while retaining explicitly pinned snapshots."""
    if window_size <= 0:
        return []

    ordered_snapshots = sorted(snapshots, key=_snapshot_sort_key)
    if len(ordered_snapshots) <= window_size:
        return ordered_snapshots

    pinned_snapshot_identities = pinned_snapshot_identities or set()
    selected: list[TrendingSnapshot] = []
    selected_identities: set[tuple[str, ...]] = set()

    for snapshot in ordered_snapshots:
        snapshot_identities = set(_snapshot_identity_tokens(snapshot))
        if snapshot_identities & pinned_snapshot_identities and snapshot_identities.isdisjoint(selected_identities):
            selected.append(snapshot)
            selected_identities.update(snapshot_identities)

    if len(selected) >= window_size:
        return selected[-window_size:]

    for snapshot in reversed(ordered_snapshots):
        snapshot_identities = set(_snapshot_identity_tokens(snapshot))
        if not snapshot_identities.isdisjoint(selected_identities):
            continue
        selected.append(snapshot)
        selected_identities.update(snapshot_identities)
        if len(selected) >= window_size:
            break

    selected.sort(key=_snapshot_sort_key)
    return selected


# ---------------------------------------------------------------------------
# Snapshot extraction
# ---------------------------------------------------------------------------


def _data_view_row_has_error(data_view: Any) -> bool:
    """Return True when a serialized data-view row represents a failed fetch."""
    return org_report_data_view_row_has_error(data_view)


def _successful_data_view_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only successfully analyzed data-view rows from a snapshot payload."""
    state = _org_report_snapshot_state(data)
    return list(state.successful_data_views)


def _extract_snapshot_from_json(
    data: dict[str, Any],
    *,
    source_path: str | Path | None = None,
) -> TrendingSnapshot | None:
    """Build a TrendingSnapshot from a parsed org-report JSON dict.

    Returns None if the payload is missing required top-level keys.
    """
    state = _org_report_snapshot_state(
        data,
        include_component_ids=True,
        include_high_similarity_pairs=True,
    )
    metadata = org_report_snapshot_metadata(data, state=state, source_path=source_path)
    if metadata is None:
        return None
    if not state.history_assessment.eligible:
        return None

    timestamp = metadata["generated_at"]
    distribution = state.distribution
    data_view_stats = state.data_view_assessment.stats
    successful_data_views = list(state.successful_data_views)
    high_similarity_pairs = set(state.high_similarity_pairs)
    sim_pairs = _mapping_list(data.get("similarity_pairs", []))

    # Per-DV metrics for drift scoring (single pass over data_views)
    dv_component_counts: dict[str, int] = {}
    dv_core_ratios: dict[str, float] = {}
    dv_max_similarity: dict[str, float] = {}
    dv_ids = set(state.data_view_inventory.ids)
    dv_names = dict(state.data_view_inventory.names)
    has_data_view_ids = bool(dv_ids)

    # Core ratio per DV: fraction of DV's components that are "core"
    # (shared across >= threshold% of DVs).  Approximated from the global
    # core component list — a DV's core ratio is len(its_components ∩ core) / total.
    core_ids: set[str] = set()
    core_section = _mapping_dict(distribution.get("core", {}))
    for comp_id_list_key in (("metrics", "core_metrics"), ("dimensions", "core_dimensions")):
        for key in comp_id_list_key:
            values = _mapping_list(core_section.get(key, []))
            if values:
                core_ids.update(str(value) for value in values)
                break

    dv_core_component_counts: dict[str, int] = {}

    for dv in successful_data_views:
        dv_id = org_report_data_view_row_id(dv)
        if not dv_id:
            continue
        metrics = _mapping_int(dv, "metrics_count", "metric_count") or 0
        dims = _mapping_int(dv, "dimensions_count", "dimension_count") or 0
        dv_component_counts[dv_id] = metrics + dims
        dv_core_component_counts[dv_id] = 0
        dv_max_similarity[dv_id] = 0.0

    raw_component_index = data.get("component_index")
    component_index = _mapping_dict(raw_component_index)
    component_ids: set[str] | None = None if state.component_ids is None else set(state.component_ids)
    if component_index and core_ids:
        for comp_id in core_ids:
            comp_info = component_index.get(comp_id)
            if not isinstance(comp_info, dict):
                continue
            for dv_id in _mapping_list(comp_info.get("data_views", [])):
                normalized_dv_id = normalize_org_report_data_view_id(dv_id)
                if normalized_dv_id in dv_core_component_counts:
                    dv_core_component_counts[normalized_dv_id] += 1

    for dv_id, total_components in dv_component_counts.items():
        if total_components > 0 and core_ids:
            dv_core_ratios[dv_id] = dv_core_component_counts.get(dv_id, 0) / total_components
        else:
            dv_core_ratios[dv_id] = 0.0

    # Max similarity per DV
    for pair in sim_pairs:
        if not isinstance(pair, dict):
            continue
        normalized_pair = normalized_similarity_pair_ids(pair)
        if normalized_pair is None:
            continue
        dv1, dv2 = normalized_pair
        sim = coerce_snapshot_float(pair.get("jaccard_similarity")) or 0.0
        if dv1 in dv_ids and dv2 in dv_ids:
            dv_max_similarity[dv1] = max(dv_max_similarity.get(dv1, 0.0), sim)
            dv_max_similarity[dv2] = max(dv_max_similarity.get(dv2, 0.0), sim)

    return TrendingSnapshot(
        timestamp=str(timestamp),
        org_id=str(metadata["org_id"]) if metadata.get("org_id") is not None else None,
        data_view_count=data_view_stats.reported_total,
        analyzed_data_view_count=data_view_stats.analyzed_total,
        component_count=int(metadata["total_unique_components"]),
        core_count=int(metadata["core_count"]),
        isolated_count=int(metadata["isolated_count"]),
        high_sim_pair_count=int(metadata["high_similarity_pairs"]),
        snapshot_id=str(metadata["snapshot_id"]) if metadata.get("snapshot_id") is not None else None,
        content_hash=str(metadata.get("content_hash") or org_report_snapshot_content_hash(data)),
        source_path=str(source_path) if source_path is not None else None,
        component_ids=component_ids,
        high_similarity_pairs=high_similarity_pairs,
        dv_component_counts=dv_component_counts,
        dv_core_ratios=dv_core_ratios,
        dv_max_similarity=dv_max_similarity,
        dv_ids=dv_ids,
        dv_names=dv_names,
        has_data_view_ids=has_data_view_ids,
        complete_data_view_ids=state.data_view_assessment.ids_complete,
        complete_high_similarity_pairs=state.comparison_assessment.complete_high_similarity_pairs,
    )


# ---------------------------------------------------------------------------
# Cache discovery
# ---------------------------------------------------------------------------


def discover_snapshots(
    cache_dir: str | Path,
    window_size: int = 10,
    explicit_file: str | Path | None = None,
    org_id: str | None = None,
) -> list[TrendingSnapshot]:
    """Walk a directory for org-report JSON files and return snapshots.

    Args:
        cache_dir: Directory to scan for ``*.json`` org-report files.
        window_size: Maximum number of snapshots to return.
        explicit_file: Optional explicit file path (from ``--compare-org-report``)
            to include in the snapshot list.

    Returns:
        List of TrendingSnapshot ordered oldest-to-newest, trimmed to
        *window_size*.  May be empty if no valid snapshots are found.
    """
    snapshots_by_identity: dict[tuple[str, ...], TrendingSnapshot] = {}
    ordered_identities: list[tuple[str, ...]] = []
    pinned_snapshot_identities = _resolve_explicit_snapshot_identities(explicit_file, org_id=org_id)
    explicit_path = Path(explicit_file) if explicit_file is not None else None

    # Collect JSON files from the resolved snapshot search scope.
    json_files = list(iter_org_report_snapshot_files(cache_dir, org_id=org_id))

    # Include explicit file if provided
    if explicit_path is not None and explicit_path.is_file() and explicit_path not in json_files:
        json_files.append(explicit_path)

    for json_file in json_files:
        snapshot = _load_snapshot_from_file(json_file)
        if snapshot is None:
            continue
        if org_id is not None and snapshot.org_id != org_id:
            continue
        snapshot_identity = _snapshot_identity_key(snapshot)
        existing_snapshot = snapshots_by_identity.get(snapshot_identity)
        if existing_snapshot is None:
            snapshots_by_identity[snapshot_identity] = snapshot
            ordered_identities.append(snapshot_identity)
        elif _snapshot_preference(snapshot) > _snapshot_preference(existing_snapshot):
            snapshots_by_identity[snapshot_identity] = snapshot

    snapshots = [snapshots_by_identity[snapshot_identity] for snapshot_identity in ordered_identities]
    if org_id is None and is_org_report_snapshot_root_dir(cache_dir):
        snapshot_org_ids = {snapshot.org_id or "unknown" for snapshot in snapshots}
        if len(snapshot_org_ids) > 1:
            raise ValueError(
                f"Multiple org snapshot histories found under {Path(cache_dir)}; pass org_id to scope discovery."
            )

    return _trim_snapshot_window(
        snapshots,
        window_size=window_size,
        pinned_snapshot_identities=pinned_snapshot_identities,
    )


def _load_snapshot_from_file(json_file: Path) -> TrendingSnapshot | None:
    """Load a single org-report JSON file and extract a snapshot.

    Returns None if the file is unreadable, malformed, or not an org-report.
    """
    try:
        with open(json_file, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
        logger.warning("Skipping %s: %s", json_file, exc)
        return None

    if not isinstance(data, dict):
        logger.warning("Skipping %s: not a JSON object", json_file)
        return None

    if not is_org_report_snapshot_payload(data):
        return None

    return _extract_snapshot_from_json(data, source_path=json_file)


# ---------------------------------------------------------------------------
# Delta computation
# ---------------------------------------------------------------------------


def compute_deltas(snapshots: list[TrendingSnapshot]) -> list[TrendingDelta]:
    """Compute deltas between consecutive snapshots."""
    deltas: list[TrendingDelta] = []
    for prev, curr in _iter_consecutive_snapshot_pairs(snapshots):
        deltas.append(
            TrendingDelta(
                from_timestamp=prev.timestamp,
                to_timestamp=curr.timestamp,
                data_view_delta=_snapshot_effective_data_view_count(curr) - _snapshot_effective_data_view_count(prev),
                component_delta=curr.component_count - prev.component_count,
                core_delta=curr.core_count - prev.core_count,
                isolated_delta=curr.isolated_count - prev.isolated_count,
                high_sim_pair_delta=curr.high_sim_pair_count - prev.high_sim_pair_count,
            )
        )
    return deltas


# ---------------------------------------------------------------------------
# Drift scoring
# ---------------------------------------------------------------------------

# Weights for drift score dimensions (sum to 1.0)
_WEIGHT_COMPONENT = 0.4
_WEIGHT_CORE_RATIO = 0.2
_WEIGHT_SIMILARITY = 0.2
_WEIGHT_PRESENCE = 0.2


def _iter_consecutive_snapshot_pairs(
    snapshots: list[TrendingSnapshot],
) -> Iterator[tuple[TrendingSnapshot, TrendingSnapshot]]:
    """Yield consecutive oldest-to-newest snapshot pairs."""
    for index in range(1, len(snapshots)):
        yield snapshots[index - 1], snapshots[index]


def _normalize_drift_dimension(values: dict[str, float]) -> dict[str, float]:
    """Scale one raw drift dimension to 0.0-1.0 by the largest DV value."""
    if not values:
        return {}
    max_value = max(values.values())
    if max_value == 0:
        return dict.fromkeys(values, 0.0)
    return {dv_id: value / max_value for dv_id, value in values.items()}


def _accumulate_pairwise_drift(
    previous: TrendingSnapshot,
    current: TrendingSnapshot,
    *,
    dv_ids: set[str],
    raw_component: dict[str, float],
    raw_core_ratio: dict[str, float],
    raw_similarity: dict[str, float],
    raw_presence: dict[str, float],
) -> None:
    """Accumulate absolute period-over-period drift contributions for one pair."""
    for dv_id in dv_ids:
        previous_present = dv_id in previous.dv_ids
        current_present = dv_id in current.dv_ids
        raw_presence[dv_id] += 1.0 if previous_present != current_present else 0.0
        raw_component[dv_id] += abs(
            current.dv_component_counts.get(dv_id, 0) - previous.dv_component_counts.get(dv_id, 0)
        )
        raw_core_ratio[dv_id] += abs(current.dv_core_ratios.get(dv_id, 0.0) - previous.dv_core_ratios.get(dv_id, 0.0))
        raw_similarity[dv_id] += abs(
            current.dv_max_similarity.get(dv_id, 0.0) - previous.dv_max_similarity.get(dv_id, 0.0)
        )


def compute_drift_scores(snapshots: list[TrendingSnapshot]) -> dict[str, float]:
    """Compute per-data-view drift scores across the snapshot window.

    Each score is a float 0.0-1.0 indicating how much the DV changed
    relative to others. Uses weighted normalization across four dimensions,
    with each raw dimension accumulated from consecutive snapshot deltas
    across the full window: component count change (0.4),
    core/isolated ratio shift (0.2), similarity shift (0.2),
    and presence change (0.2).

    Returns an empty dict if fewer than 2 snapshots.
    """
    if len(snapshots) < 2:
        return {}

    # All DVs seen across the window
    all_dv_ids: set[str] = set()
    for snap in snapshots:
        all_dv_ids.update(snap.dv_ids)

    if not all_dv_ids:
        return {}

    # Raw deltas per DV per dimension, aggregated across every period.
    raw_component = dict.fromkeys(all_dv_ids, 0.0)
    raw_core_ratio = dict.fromkeys(all_dv_ids, 0.0)
    raw_similarity = dict.fromkeys(all_dv_ids, 0.0)
    raw_presence = dict.fromkeys(all_dv_ids, 0.0)

    for previous, current in _iter_consecutive_snapshot_pairs(snapshots):
        _accumulate_pairwise_drift(
            previous,
            current,
            dv_ids=all_dv_ids,
            raw_component=raw_component,
            raw_core_ratio=raw_core_ratio,
            raw_similarity=raw_similarity,
            raw_presence=raw_presence,
        )

    norm_component = _normalize_drift_dimension(raw_component)
    norm_core_ratio = _normalize_drift_dimension(raw_core_ratio)
    norm_similarity = _normalize_drift_dimension(raw_similarity)
    norm_presence = _normalize_drift_dimension(raw_presence)

    # Weighted average
    scores: dict[str, float] = {}
    for dv_id in all_dv_ids:
        score = (
            _WEIGHT_COMPONENT * norm_component.get(dv_id, 0.0)
            + _WEIGHT_CORE_RATIO * norm_core_ratio.get(dv_id, 0.0)
            + _WEIGHT_SIMILARITY * norm_similarity.get(dv_id, 0.0)
            + _WEIGHT_PRESENCE * norm_presence.get(dv_id, 0.0)
        )
        scores[dv_id] = round(score, 4)

    return scores


# ---------------------------------------------------------------------------
# High-level builder
# ---------------------------------------------------------------------------


def build_trending(
    cache_dir: str | Path,
    window_size: int = 10,
    explicit_file: str | Path | None = None,
    current_snapshot: TrendingSnapshot | None = None,
    org_id: str | None = None,
) -> OrgReportTrending | None:
    """Build a complete OrgReportTrending from cached org-report JSONs.

    Args:
        cache_dir: Directory containing org-report JSON outputs.
        window_size: Maximum number of snapshots in the window.
        explicit_file: Optional explicit file to fold into the window.
        current_snapshot: Snapshot for the current run (appended to window).

    Returns:
        OrgReportTrending if >= 2 snapshots available, else None.
    """
    effective_org_id = org_id or (current_snapshot.org_id if current_snapshot is not None else None)
    pinned_snapshot_identities = _resolve_explicit_snapshot_identities(explicit_file, org_id=effective_org_id)
    snapshots = discover_snapshots(
        cache_dir,
        window_size=window_size,
        explicit_file=explicit_file,
        org_id=effective_org_id,
    )

    # Append current run snapshot if provided and not a duplicate
    if current_snapshot is not None:
        current_snapshot_org_id = current_snapshot.org_id or effective_org_id
        if current_snapshot.org_id is None and current_snapshot_org_id is not None:
            current_snapshot.org_id = current_snapshot_org_id

        if effective_org_id is None or current_snapshot_org_id == effective_org_id:
            if current_snapshot_org_id is None:
                is_duplicate = any(_snapshots_equivalent(snapshot, current_snapshot) for snapshot in snapshots)
            else:
                is_duplicate = any(
                    _snapshots_equivalent(snapshot, current_snapshot)
                    for snapshot in snapshots
                    if snapshot.org_id == current_snapshot_org_id
                )

            if not is_duplicate:
                snapshots.append(current_snapshot)
                pinned_snapshot_identities.update(_snapshot_identity_tokens(current_snapshot))

    snapshots = _trim_snapshot_window(
        snapshots,
        window_size=window_size,
        pinned_snapshot_identities=pinned_snapshot_identities,
    )

    if len(snapshots) < 2:
        return None

    deltas = compute_deltas(snapshots)
    drift_scores = compute_drift_scores(snapshots)

    return OrgReportTrending(
        snapshots=snapshots,
        deltas=deltas,
        drift_scores=drift_scores,
        window_size=len(snapshots),
    )
