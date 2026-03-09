"""Org-report trending: snapshot discovery, delta computation, and drift scoring."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from cja_auto_sdr.org.models import (
    OrgReportTrending,
    TrendingDelta,
    TrendingSnapshot,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Snapshot extraction
# ---------------------------------------------------------------------------


def _extract_snapshot_from_json(data: dict[str, Any]) -> TrendingSnapshot | None:
    """Build a TrendingSnapshot from a parsed org-report JSON dict.

    Returns None if the payload is missing required top-level keys.
    """
    timestamp = data.get("generated_at") or data.get("timestamp")
    if not timestamp:
        return None

    summary = data.get("summary", {})
    distribution = data.get("distribution", {})

    # Data view count
    dv_count = summary.get("total_data_views", 0)
    if not dv_count:
        dv_count = len(data.get("data_views", []))

    # Component count
    comp_count = summary.get("total_unique_components", 0)

    # Core / isolated from distribution
    core_section = distribution.get("core", {})
    isolated_section = distribution.get("isolated", {})

    core_count = core_section.get("total")
    if core_count is None:
        core_count = core_section.get("metrics_count", 0) + core_section.get("dimensions_count", 0)

    isolated_count = isolated_section.get("total")
    if isolated_count is None:
        isolated_count = isolated_section.get("metrics_count", 0) + isolated_section.get("dimensions_count", 0)

    # High-similarity pairs
    sim_pairs = data.get("similarity_pairs", [])
    high_sim_count = sum(1 for p in sim_pairs if p.get("jaccard_similarity", 0) >= 0.9)

    # Per-DV metrics for drift scoring (single pass over data_views)
    dv_component_counts: dict[str, int] = {}
    dv_core_ratios: dict[str, float] = {}
    dv_max_similarity: dict[str, float] = {}
    dv_ids: set[str] = set()

    # Core ratio per DV: fraction of DV's components that are "core"
    # (shared across >= threshold% of DVs).  Approximated from the global
    # core component list — a DV's core ratio is len(its_components ∩ core) / total.
    core_ids: set[str] = set()
    for comp_id_list_key in ("core_metrics", "core_dimensions"):
        core_ids.update(distribution.get("core", {}).get(comp_id_list_key, []))

    for dv in data.get("data_views", []):
        dv_id = dv.get("data_view_id") or dv.get("id", "")
        if not dv_id:
            continue
        dv_ids.add(dv_id)
        metrics = dv.get("metric_count", 0)
        dims = dv.get("dimension_count", 0)
        dv_component_counts[dv_id] = metrics + dims

        metric_ids = set(dv.get("metric_ids", []))
        dimension_ids = set(dv.get("dimension_ids", []))
        all_ids = metric_ids | dimension_ids
        total = len(all_ids)
        if total > 0 and core_ids:
            dv_core_ratios[dv_id] = len(all_ids & core_ids) / total
        else:
            dv_core_ratios[dv_id] = 0.0

    # Max similarity per DV
    for pair in sim_pairs:
        dv1 = pair.get("dv1_id") or pair.get("data_view_1", {}).get("id", "")
        dv2 = pair.get("dv2_id") or pair.get("data_view_2", {}).get("id", "")
        sim = pair.get("jaccard_similarity", 0.0)
        if dv1:
            dv_max_similarity[dv1] = max(dv_max_similarity.get(dv1, 0.0), sim)
        if dv2:
            dv_max_similarity[dv2] = max(dv_max_similarity.get(dv2, 0.0), sim)

    return TrendingSnapshot(
        timestamp=str(timestamp),
        data_view_count=dv_count,
        component_count=comp_count,
        core_count=core_count,
        isolated_count=isolated_count,
        high_sim_pair_count=high_sim_count,
        dv_component_counts=dv_component_counts,
        dv_core_ratios=dv_core_ratios,
        dv_max_similarity=dv_max_similarity,
        dv_ids=dv_ids,
    )


# ---------------------------------------------------------------------------
# Cache discovery
# ---------------------------------------------------------------------------


def discover_snapshots(
    cache_dir: str | Path,
    window_size: int = 10,
    explicit_file: str | Path | None = None,
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
    seen_timestamps: set[str] = set()

    # Collect JSON files from the directory
    json_files: list[Path] = []
    if cache_path.is_dir():
        json_files = sorted(cache_path.glob("*.json"))

    # Include explicit file if provided
    if explicit_file:
        explicit_path = Path(explicit_file)
        if explicit_path.is_file() and explicit_path not in json_files:
            json_files.append(explicit_path)

    for json_file in json_files:
        snapshot = _load_snapshot_from_file(json_file)
        if snapshot is not None and snapshot.timestamp not in seen_timestamps:
            snapshots.append(snapshot)
            seen_timestamps.add(snapshot.timestamp)

    # Sort by timestamp (oldest first) and trim to window
    snapshots.sort(key=lambda s: s.timestamp)
    if len(snapshots) > window_size:
        snapshots = snapshots[-window_size:]

    return snapshots


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

    return _extract_snapshot_from_json(data)


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
    snapshots = discover_snapshots(cache_dir, window_size=window_size, explicit_file=explicit_file)

    # Append current run snapshot if provided and not a duplicate
    if current_snapshot is not None:
        existing_timestamps = {s.timestamp for s in snapshots}
        if current_snapshot.timestamp not in existing_timestamps:
            snapshots.append(current_snapshot)
            # Re-trim if over window
            if len(snapshots) > window_size:
                snapshots = snapshots[-window_size:]

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
