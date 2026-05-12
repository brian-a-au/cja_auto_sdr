"""Watch-mode cycle orchestrator.

`WatchCycleRunner.run_cycle()` is a pure generator over event objects — the
caller is responsible for serializing them to stdout and for inter-cycle sleep.
This separation makes the loop trivial to test and keeps signal handling in the
CLI layer.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from cja_auto_sdr.diff.comparator import DataViewComparator
from cja_auto_sdr.diff.snapshot import SnapshotManager
from cja_auto_sdr.output.watch_event import (
    BaselineEvent,
    ChangeEvent,
    ErrorEvent,
    iso8601_utc_now,
)


def _watch_total_changes(summary: Any) -> int:
    """Watch-specific total: includes calc-metric + segment changes.

    `DiffSummary.total_changes` (diff/models.py:111) only sums metrics + dimensions.
    For watch threshold semantics we want the full picture.
    """
    return (
        summary.total_changes
        + summary.calc_metrics_added
        + summary.calc_metrics_removed
        + summary.calc_metrics_modified
        + summary.segments_added
        + summary.segments_removed
        + summary.segments_modified
    )


def _changes_by_category(summary: Any) -> dict[str, dict[str, int]]:
    return {
        "dimensions": {
            "added": summary.dimensions_added,
            "removed": summary.dimensions_removed,
            "modified": summary.dimensions_modified,
        },
        "metrics": {
            "added": summary.metrics_added,
            "removed": summary.metrics_removed,
            "modified": summary.metrics_modified,
        },
        "calculated_metrics": {
            "added": summary.calc_metrics_added,
            "removed": summary.calc_metrics_removed,
            "modified": summary.calc_metrics_modified,
        },
        "segments": {
            "added": summary.segments_added,
            "removed": summary.segments_removed,
            "modified": summary.segments_modified,
        },
    }


def _snapshot_id(snap: Any) -> str:
    # Stable per-snapshot identifier for the event stream. Falls back to id() if
    # the snapshot has no `created_at` (legacy snapshots) — never raises.
    created = getattr(snap, "created_at", None) or ""
    return f"{snap.data_view_id}@{created}" if created else f"{snap.data_view_id}@{id(snap):x}"


class WatchCycleRunner:
    """One instance per watch invocation; holds prior snapshots in memory."""

    def __init__(
        self,
        *,
        snapshot_manager: SnapshotManager,
        comparator: DataViewComparator,
        threshold: int,
    ) -> None:
        self._snapshot_manager = snapshot_manager
        self._comparator = comparator
        self._threshold = threshold
        self._prior: dict[str, Any] = {}

    def run_cycle(
        self,
        *,
        cja: Any,
        data_view_ids: list[str],
        cycle: int,
    ) -> Iterator[BaselineEvent | ChangeEvent | ErrorEvent]:
        for dv_id in data_view_ids:
            try:
                current = self._snapshot_manager.create_snapshot(
                    cja,
                    dv_id,
                    quiet=True,
                    include_calculated_metrics=True,
                    include_segments=True,
                )
            except Exception as exc:  # surfaced as error event, loop continues.
                yield ErrorEvent(
                    ts=iso8601_utc_now(),
                    cycle=cycle,
                    data_view_id=dv_id,
                    stage="fetch",
                    error_class=type(exc).__name__,
                    error_message=str(exc),
                )
                continue

            prior = self._prior.get(dv_id)
            if prior is None:
                self._prior[dv_id] = current
                yield BaselineEvent(
                    ts=iso8601_utc_now(),
                    cycle=cycle,
                    data_view_id=dv_id,
                    snapshot_id=_snapshot_id(current),
                    component_counts={
                        "dimensions": len(getattr(current, "dimensions", []) or []),
                        "metrics": len(getattr(current, "metrics", []) or []),
                        "calculated_metrics": len(getattr(current, "calculated_metrics_inventory", []) or []),
                        "segments": len(getattr(current, "segments_inventory", []) or []),
                    },
                )
                continue

            try:
                diff = self._comparator.compare(prior, current)
            except Exception as exc:
                yield ErrorEvent(
                    ts=iso8601_utc_now(),
                    cycle=cycle,
                    data_view_id=dv_id,
                    stage="diff",
                    error_class=type(exc).__name__,
                    error_message=str(exc),
                )
                continue

            total = _watch_total_changes(diff.summary)
            if total >= self._threshold:
                yield ChangeEvent(
                    ts=iso8601_utc_now(),
                    cycle=cycle,
                    data_view_id=dv_id,
                    previous_snapshot_id=_snapshot_id(prior),
                    current_snapshot_id=_snapshot_id(current),
                    total_changes=total,
                    changes_by_category=_changes_by_category(diff.summary),
                )
            self._prior[dv_id] = current
