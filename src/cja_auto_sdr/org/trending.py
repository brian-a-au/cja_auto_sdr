"""Org-report trending: snapshot discovery, delta computation, and drift scoring."""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path
from typing import Any

from cja_auto_sdr.org.models import (
    OrgReportTrending,
    TrendingDelta,
    TrendingSnapshot,
)
from cja_auto_sdr.org.snapshot_utils import (
    chronological_snapshot_sort_fields,
    org_report_snapshot_history_eligible,
    snapshot_identity_tokens,
)

logger = logging.getLogger(__name__)


def _coerce_int(value: Any) -> int | None:
    """Best-effort integer coercion for serialized snapshot counts."""
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


def _coerce_float(value: Any) -> float | None:
    """Best-effort float coercion for serialized snapshot metrics."""
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


def _mapping_int(mapping: dict[str, Any], *keys: str) -> int | None:
    """Return the first available integer-like value from a mapping."""
    for key in keys:
        if key not in mapping:
            continue
        coerced = _coerce_int(mapping.get(key))
        if coerced is not None:
            return coerced
    return None


def _mapping_dict(value: Any) -> dict[str, Any]:
    """Return a dict value or a safe empty mapping."""
    if isinstance(value, dict):
        return value
    return {}


def _mapping_list(value: Any) -> list[Any]:
    """Return a list value or a safe empty list."""
    if isinstance(value, list):
        return value
    return []


def _canonical_snapshot_payload(data: dict[str, Any]) -> dict[str, Any]:
    """Return the stable subset of a snapshot payload used for hashing."""
    return {key: value for key, value in data.items() if key != "_snapshot_meta"}


def _snapshot_content_hash(data: dict[str, Any]) -> str:
    """Return a deterministic content hash for an org-report JSON payload."""
    serialized = json.dumps(
        _canonical_snapshot_payload(data),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _snapshot_identity_tokens(snapshot: TrendingSnapshot) -> tuple[tuple[str, ...], ...]:
    """Return all stable identities available for one snapshot."""
    return snapshot_identity_tokens(
        snapshot_id=snapshot.snapshot_id,
        content_hash=snapshot.content_hash,
        source_path=snapshot.source_path,
        fallback_parts=(snapshot.org_id or "", snapshot.timestamp),
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
    if not isinstance(data_view, dict):
        return True
    return data_view.get("error") not in (None, "")


def _successful_data_view_rows(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Return only successfully analyzed data-view rows from a snapshot payload."""
    data_views = _mapping_list(data.get("data_views", []))
    return [
        data_view for data_view in data_views if isinstance(data_view, dict) and not _data_view_row_has_error(data_view)
    ]


def _extract_snapshot_from_json(
    data: dict[str, Any],
    *,
    source_path: str | Path | None = None,
) -> TrendingSnapshot | None:
    """Build a TrendingSnapshot from a parsed org-report JSON dict.

    Returns None if the payload is missing required top-level keys.
    """
    timestamp = data.get("generated_at") or data.get("timestamp")
    if not timestamp:
        return None
    if not org_report_snapshot_history_eligible(data):
        return None

    summary = _mapping_dict(data.get("summary", {}))
    distribution = _mapping_dict(data.get("distribution", {}))
    org_id = data.get("org_id")
    snapshot_meta = data.get("_snapshot_meta", {})
    if not isinstance(snapshot_meta, dict):
        snapshot_meta = {}
    successful_data_views = _successful_data_view_rows(data)
    raw_data_views = _mapping_list(data.get("data_views", []))

    # Prefer explicit analyzed counts, including legitimate zero-analyzed outage snapshots.
    dv_count = _mapping_int(summary, "data_views_analyzed")
    if dv_count is None:
        dv_count = _mapping_int(summary, "data_views_total", "total_data_views")
        if dv_count == 0:
            dv_count = None
    if dv_count is None:
        dv_count = len(successful_data_views) if successful_data_views else len(raw_data_views)

    # Component count
    comp_count = _mapping_int(summary, "total_unique_components") or 0

    # Core / isolated from distribution
    core_section = _mapping_dict(distribution.get("core", {}))
    isolated_section = _mapping_dict(distribution.get("isolated", {}))

    core_count = _mapping_int(core_section, "total")
    if core_count is None:
        core_count = (_mapping_int(core_section, "metrics_count") or 0) + (
            _mapping_int(core_section, "dimensions_count") or 0
        )

    isolated_count = _mapping_int(isolated_section, "total")
    if isolated_count is None:
        isolated_count = (_mapping_int(isolated_section, "metrics_count") or 0) + (
            _mapping_int(isolated_section, "dimensions_count") or 0
        )

    # High-similarity pairs
    sim_pairs = _mapping_list(data.get("similarity_pairs", []))
    high_sim_count = sum(
        1
        for pair in sim_pairs
        if isinstance(pair, dict) and (_coerce_float(pair.get("jaccard_similarity")) or 0.0) >= 0.9
    )

    # Per-DV metrics for drift scoring (single pass over data_views)
    dv_component_counts: dict[str, int] = {}
    dv_core_ratios: dict[str, float] = {}
    dv_max_similarity: dict[str, float] = {}
    dv_ids: set[str] = set()
    dv_names: dict[str, str] = {}

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
        dv_id = str(dv.get("data_view_id") or dv.get("id") or "")
        if not dv_id:
            continue
        dv_ids.add(dv_id)
        metrics = _mapping_int(dv, "metrics_count", "metric_count") or 0
        dims = _mapping_int(dv, "dimensions_count", "dimension_count") or 0
        dv_component_counts[dv_id] = metrics + dims
        dv_names[dv_id] = str(dv.get("data_view_name") or dv.get("name") or dv_id)
        dv_core_component_counts[dv_id] = 0
        dv_max_similarity[dv_id] = 0.0

    component_index = _mapping_dict(data.get("component_index", {}))
    if component_index and core_ids:
        for comp_id in core_ids:
            comp_info = component_index.get(comp_id)
            if not isinstance(comp_info, dict):
                continue
            for dv_id in _mapping_list(comp_info.get("data_views", [])):
                if dv_id in dv_core_component_counts:
                    dv_core_component_counts[dv_id] += 1

    for dv_id, total_components in dv_component_counts.items():
        if total_components > 0 and core_ids:
            dv_core_ratios[dv_id] = dv_core_component_counts.get(dv_id, 0) / total_components
        else:
            dv_core_ratios[dv_id] = 0.0

    # Max similarity per DV
    for pair in sim_pairs:
        if not isinstance(pair, dict):
            continue
        dv1 = str(pair.get("dv1_id") or _mapping_dict(pair.get("data_view_1", {})).get("id") or "")
        dv2 = str(pair.get("dv2_id") or _mapping_dict(pair.get("data_view_2", {})).get("id") or "")
        sim = _coerce_float(pair.get("jaccard_similarity")) or 0.0
        if dv1 in dv_ids and dv2 in dv_ids:
            dv_max_similarity[dv1] = max(dv_max_similarity.get(dv1, 0.0), sim)
            dv_max_similarity[dv2] = max(dv_max_similarity.get(dv2, 0.0), sim)

    return TrendingSnapshot(
        timestamp=str(timestamp),
        org_id=str(org_id) if org_id is not None else None,
        data_view_count=dv_count,
        component_count=comp_count,
        core_count=core_count,
        isolated_count=isolated_count,
        high_sim_pair_count=high_sim_count,
        snapshot_id=str(snapshot_meta["snapshot_id"]) if snapshot_meta.get("snapshot_id") is not None else None,
        content_hash=str(snapshot_meta.get("content_hash") or _snapshot_content_hash(data)),
        source_path=str(source_path) if source_path is not None else None,
        dv_component_counts=dv_component_counts,
        dv_core_ratios=dv_core_ratios,
        dv_max_similarity=dv_max_similarity,
        dv_ids=dv_ids,
        dv_names=dv_names,
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
    cache_path = Path(cache_dir)
    snapshots: list[TrendingSnapshot] = []
    seen_snapshot_identities: set[tuple[str, ...]] = set()
    pinned_snapshot_identities = _resolve_explicit_snapshot_identities(explicit_file, org_id=org_id)
    explicit_path = Path(explicit_file) if explicit_file is not None else None

    # Collect JSON files from the directory
    json_files: list[Path] = []
    if cache_path.is_dir():
        json_files = sorted(cache_path.glob("*.json"))

    # Include explicit file if provided
    if explicit_path is not None and explicit_path.is_file() and explicit_path not in json_files:
        json_files.append(explicit_path)

    for json_file in json_files:
        snapshot = _load_snapshot_from_file(json_file)
        if snapshot is None:
            continue
        if org_id is not None and snapshot.org_id != org_id:
            continue
        snapshot_identities = set(_snapshot_identity_tokens(snapshot))
        if snapshot_identities.isdisjoint(seen_snapshot_identities):
            snapshots.append(snapshot)
            seen_snapshot_identities.update(snapshot_identities)

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

    # Basic heuristic: org-report JSONs have a "summary" or "data_views" key
    if "summary" not in data and "data_views" not in data:
        return None

    return _extract_snapshot_from_json(data, source_path=json_file)


# ---------------------------------------------------------------------------
# Delta computation
# ---------------------------------------------------------------------------


def compute_deltas(snapshots: list[TrendingSnapshot]) -> list[TrendingDelta]:
    """Compute deltas between consecutive snapshots."""
    deltas: list[TrendingDelta] = []
    for i in range(1, len(snapshots)):
        prev = snapshots[i - 1]
        curr = snapshots[i]
        deltas.append(
            TrendingDelta(
                from_timestamp=prev.timestamp,
                to_timestamp=curr.timestamp,
                data_view_delta=curr.data_view_count - prev.data_view_count,
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


def compute_drift_scores(snapshots: list[TrendingSnapshot]) -> dict[str, float]:
    """Compute per-data-view drift scores across the snapshot window.

    Each score is a float 0.0-1.0 indicating how much the DV changed
    relative to others.  Uses weighted normalization across four dimensions:
    component count change (0.4), core/isolated ratio shift (0.2),
    similarity shift (0.2), and presence change (0.2).

    Returns an empty dict if fewer than 2 snapshots.
    """
    if len(snapshots) < 2:
        return {}

    first = snapshots[0]
    last = snapshots[-1]

    # All DVs seen across the window
    all_dv_ids: set[str] = set()
    for snap in snapshots:
        all_dv_ids.update(snap.dv_ids)

    if not all_dv_ids:
        return {}

    # Raw deltas per DV per dimension
    raw_component: dict[str, float] = {}
    raw_core_ratio: dict[str, float] = {}
    raw_similarity: dict[str, float] = {}
    raw_presence: dict[str, float] = {}

    for dv_id in all_dv_ids:
        in_first = dv_id in first.dv_ids
        in_last = dv_id in last.dv_ids

        # Presence change: 1.0 if added or removed, 0.0 if present throughout
        if in_first and in_last:
            raw_presence[dv_id] = 0.0
        else:
            raw_presence[dv_id] = 1.0

        # Component count change (absolute delta)
        comp_first = first.dv_component_counts.get(dv_id, 0)
        comp_last = last.dv_component_counts.get(dv_id, 0)
        raw_component[dv_id] = abs(comp_last - comp_first)

        # Core ratio shift
        ratio_first = first.dv_core_ratios.get(dv_id, 0.0)
        ratio_last = last.dv_core_ratios.get(dv_id, 0.0)
        raw_core_ratio[dv_id] = abs(ratio_last - ratio_first)

        # Similarity shift
        sim_first = first.dv_max_similarity.get(dv_id, 0.0)
        sim_last = last.dv_max_similarity.get(dv_id, 0.0)
        raw_similarity[dv_id] = abs(sim_last - sim_first)

    # Normalize each dimension to 0-1
    def _normalize(values: dict[str, float]) -> dict[str, float]:
        if not values:
            return {}
        max_val = max(values.values())
        if max_val == 0:
            return dict.fromkeys(values, 0.0)
        return {k: v / max_val for k, v in values.items()}

    norm_component = _normalize(raw_component)
    norm_core_ratio = _normalize(raw_core_ratio)
    norm_similarity = _normalize(raw_similarity)
    norm_presence = _normalize(raw_presence)

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
