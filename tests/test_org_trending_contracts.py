"""Contract tests for org/trending public APIs.

These tests verify public API signatures, return types, and semantic guarantees.
They are NOT coverage tests — they protect against API regressions.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from cja_auto_sdr.org.cache import OrgReportCache
from cja_auto_sdr.org.models import (
    OrgReportComparison,
    OrgReportTrending,
    TrendingDelta,
    TrendingSnapshot,
)
from cja_auto_sdr.org.snapshot_utils import (
    OrgReportSnapshotDataViewStats,
    chronological_snapshot_sort_fields,
    org_report_snapshot_data_view_stats,
    org_report_snapshot_metadata,
    parse_snapshot_timestamp,
    snapshot_epoch,
)
from cja_auto_sdr.org.trending import (
    build_trending,
    compute_deltas,
    compute_drift_scores,
    discover_snapshots,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_org_report_json(
    timestamp: str = "2026-01-01T00:00:00Z",
    org_id: str = "test_org",
    dv_count: int = 10,
    comp_count: int = 100,
    core_metrics: list | None = None,
    core_dimensions: list | None = None,
    isolated_metrics: list | None = None,
    isolated_dimensions: list | None = None,
    data_views: list | None = None,
    component_index: dict | None = None,
    similarity_pairs: list | None = None,
) -> dict:
    """Build a minimal, history-eligible org-report JSON dict."""
    if data_views is None:
        data_views = [
            {"id": f"dv{index}", "name": f"DV {index}", "metrics_count": 0, "dimensions_count": 0}
            for index in range(1, dv_count + 1)
        ]
    return {
        "generated_at": timestamp,
        "org_id": org_id,
        "parameters": {
            "skip_similarity": False,
            "org_stats_only": False,
        },
        "summary": {
            "data_views_total": dv_count,
            "total_unique_components": comp_count,
            "similarity_analysis_complete": True,
            "similarity_analysis_mode": "complete",
        },
        "distribution": {
            "core": {
                "total": len(core_metrics or []) + len(core_dimensions or []),
                "metrics_count": len(core_metrics or []),
                "dimensions_count": len(core_dimensions or []),
                "metrics": core_metrics or [],
                "dimensions": core_dimensions or [],
            },
            "isolated": {
                "total": len(isolated_metrics or []) + len(isolated_dimensions or []),
                "metrics_count": len(isolated_metrics or []),
                "dimensions_count": len(isolated_dimensions or []),
            },
        },
        "data_views": data_views,
        "component_index": component_index or {},
        "similarity_pairs": similarity_pairs or [],
    }


def _write_report(tmp_path: Path, filename: str, data: dict) -> Path:
    path = tmp_path / filename
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Dataclass Contracts: TrendingSnapshot
# ---------------------------------------------------------------------------


class TestTrendingSnapshotContract:
    """Contract tests for TrendingSnapshot dataclass."""

    def test_construction_with_required_field_only(self):
        snap = TrendingSnapshot(timestamp="2026-01-01T00:00:00Z")
        assert snap.timestamp == "2026-01-01T00:00:00Z"

    def test_optional_fields_default_to_zero_or_none(self):
        snap = TrendingSnapshot(timestamp="2026-01-01T00:00:00Z")
        assert snap.org_id is None
        assert snap.data_view_count == 0
        assert snap.analyzed_data_view_count is None
        assert snap.component_count == 0
        assert snap.core_count == 0
        assert snap.isolated_count == 0
        assert snap.high_sim_pair_count == 0
        assert snap.snapshot_id is None
        assert snap.content_hash is None
        assert snap.source_path is None
        assert snap.component_ids is None
        assert snap.complete_high_similarity_pairs is False

    def test_collection_fields_default_to_empty(self):
        snap = TrendingSnapshot(timestamp="2026-01-01T00:00:00Z")
        assert snap.high_similarity_pairs == set()
        assert snap.dv_component_counts == {}
        assert snap.dv_core_ratios == {}
        assert snap.dv_max_similarity == {}
        assert snap.dv_ids == set()
        assert snap.dv_names == {}

    def test_construction_with_all_fields(self):
        snap = TrendingSnapshot(
            timestamp="2026-03-01T12:00:00Z",
            org_id="my_org",
            data_view_count=20,
            analyzed_data_view_count=18,
            component_count=500,
            core_count=300,
            isolated_count=100,
            high_sim_pair_count=3,
            snapshot_id="snap-abc-123",
            content_hash="deadbeef" * 8,
            source_path="/tmp/report.json",
            component_ids={"c1", "c2"},
            high_similarity_pairs={("dv1", "dv2")},
            dv_component_counts={"dv1": 50, "dv2": 60},
            dv_core_ratios={"dv1": 0.8, "dv2": 0.6},
            dv_max_similarity={"dv1": 0.95, "dv2": 0.88},
            dv_ids={"dv1", "dv2"},
            dv_names={"dv1": "Data View One", "dv2": "Data View Two"},
            has_data_view_ids=True,
            complete_high_similarity_pairs=True,
        )
        assert snap.org_id == "my_org"
        assert snap.data_view_count == 20
        assert snap.analyzed_data_view_count == 18
        assert snap.component_count == 500
        assert snap.core_count == 300
        assert snap.isolated_count == 100
        assert snap.high_sim_pair_count == 3
        assert snap.snapshot_id == "snap-abc-123"
        assert snap.dv_ids == {"dv1", "dv2"}
        assert snap.dv_names == {"dv1": "Data View One", "dv2": "Data View Two"}
        assert snap.complete_high_similarity_pairs is True

    def test_has_data_view_ids_inferred_from_dv_ids(self):
        """__post_init__ sets has_data_view_ids=True when dv_ids is non-empty."""
        snap = TrendingSnapshot(timestamp="2026-01-01T00:00:00Z", dv_ids={"dv1"})
        assert snap.has_data_view_ids is True

    def test_has_data_view_ids_inferred_from_dv_names(self):
        """__post_init__ sets has_data_view_ids=True when dv_names is non-empty."""
        snap = TrendingSnapshot(timestamp="2026-01-01T00:00:00Z", dv_names={"dv1": "Name"})
        assert snap.has_data_view_ids is True

    def test_id_only_manual_snapshots_normalize_effective_data_view_count(self):
        snap = TrendingSnapshot(
            timestamp="2026-01-01T00:00:00Z",
            dv_ids={"dv1", "dv2"},
            dv_names={"dv1": "DV One", "dv2": "DV Two"},
        )
        assert snap.data_view_count == 2
        assert snap.complete_data_view_ids is True

    def test_has_data_view_ids_false_when_no_dv_data(self):
        snap = TrendingSnapshot(timestamp="2026-01-01T00:00:00Z")
        assert snap.has_data_view_ids is False

    def test_field_types(self):
        snap = TrendingSnapshot(
            timestamp="2026-01-01T00:00:00Z",
            data_view_count=5,
            component_count=100,
            dv_ids={"a"},
            dv_component_counts={"a": 10},
            dv_core_ratios={"a": 0.5},
            dv_max_similarity={"a": 0.7},
        )
        assert isinstance(snap.timestamp, str)
        assert isinstance(snap.data_view_count, int)
        assert isinstance(snap.component_count, int)
        assert isinstance(snap.dv_ids, set)
        assert isinstance(snap.dv_component_counts, dict)
        assert isinstance(snap.dv_core_ratios, dict)
        assert isinstance(snap.dv_max_similarity, dict)


# ---------------------------------------------------------------------------
# Dataclass Contracts: TrendingDelta
# ---------------------------------------------------------------------------


class TestTrendingDeltaContract:
    """Contract tests for TrendingDelta dataclass."""

    def test_construction_with_required_fields(self):
        delta = TrendingDelta(
            from_timestamp="2026-01-01T00:00:00Z",
            to_timestamp="2026-02-01T00:00:00Z",
        )
        assert delta.from_timestamp == "2026-01-01T00:00:00Z"
        assert delta.to_timestamp == "2026-02-01T00:00:00Z"

    def test_numeric_fields_default_to_zero(self):
        delta = TrendingDelta(
            from_timestamp="2026-01-01T00:00:00Z",
            to_timestamp="2026-02-01T00:00:00Z",
        )
        assert delta.data_view_delta == 0
        assert delta.component_delta == 0
        assert delta.core_delta == 0
        assert delta.isolated_delta == 0
        assert delta.high_sim_pair_delta == 0

    def test_signed_integer_semantics_positive(self):
        """Positive deltas represent growth."""
        delta = TrendingDelta(
            from_timestamp="2026-01-01T00:00:00Z",
            to_timestamp="2026-02-01T00:00:00Z",
            data_view_delta=5,
            component_delta=50,
            core_delta=30,
            isolated_delta=20,
            high_sim_pair_delta=2,
        )
        assert delta.data_view_delta > 0
        assert delta.component_delta > 0

    def test_signed_integer_semantics_negative(self):
        """Negative deltas represent shrinkage."""
        delta = TrendingDelta(
            from_timestamp="2026-02-01T00:00:00Z",
            to_timestamp="2026-03-01T00:00:00Z",
            data_view_delta=-3,
            component_delta=-25,
            core_delta=-10,
            isolated_delta=-15,
            high_sim_pair_delta=-1,
        )
        assert delta.data_view_delta < 0
        assert delta.component_delta < 0

    def test_field_types_are_int(self):
        delta = TrendingDelta(
            from_timestamp="2026-01-01T00:00:00Z",
            to_timestamp="2026-02-01T00:00:00Z",
            data_view_delta=1,
            component_delta=2,
            core_delta=3,
            isolated_delta=4,
            high_sim_pair_delta=5,
        )
        assert isinstance(delta.data_view_delta, int)
        assert isinstance(delta.component_delta, int)
        assert isinstance(delta.core_delta, int)
        assert isinstance(delta.isolated_delta, int)
        assert isinstance(delta.high_sim_pair_delta, int)


# ---------------------------------------------------------------------------
# Dataclass Contracts: OrgReportTrending
# ---------------------------------------------------------------------------


class TestOrgReportTrendingContract:
    """Contract tests for OrgReportTrending dataclass and to_comparison()."""

    def _make_snapshot(self, timestamp: str, comp_count: int = 100) -> TrendingSnapshot:
        return TrendingSnapshot(
            timestamp=timestamp,
            data_view_count=10,
            component_count=comp_count,
            core_count=80,
            isolated_count=20,
            dv_ids={"dv1"},
            dv_names={"dv1": "Test DV"},
        )

    def test_default_construction(self):
        trending = OrgReportTrending()
        assert trending.snapshots == []
        assert trending.deltas == []
        assert trending.drift_scores == {}
        assert trending.window_size == 0

    def test_to_comparison_returns_none_with_fewer_than_two_snapshots(self):
        trending = OrgReportTrending(snapshots=[], window_size=0)
        assert trending.to_comparison() is None

    def test_to_comparison_returns_none_with_one_snapshot(self):
        trending = OrgReportTrending(
            snapshots=[self._make_snapshot("2026-01-01T00:00:00Z")],
            window_size=1,
        )
        assert trending.to_comparison() is None

    def test_to_comparison_returns_org_report_comparison_type(self):
        trending = OrgReportTrending(
            snapshots=[
                self._make_snapshot("2026-01-01T00:00:00Z", comp_count=100),
                self._make_snapshot("2026-02-01T00:00:00Z", comp_count=120),
            ],
            window_size=2,
        )
        result = trending.to_comparison()
        assert isinstance(result, OrgReportComparison)

    def test_to_comparison_uses_last_two_snapshots(self):
        """to_comparison() uses snapshots[-2] and snapshots[-1]."""
        snaps = [
            self._make_snapshot("2026-01-01T00:00:00Z", comp_count=100),
            self._make_snapshot("2026-02-01T00:00:00Z", comp_count=120),
            self._make_snapshot("2026-03-01T00:00:00Z", comp_count=140),
        ]
        trending = OrgReportTrending(snapshots=snaps, window_size=3)
        result = trending.to_comparison()
        assert result is not None
        assert result.previous_timestamp == "2026-02-01T00:00:00Z"
        assert result.current_timestamp == "2026-03-01T00:00:00Z"

    def test_to_comparison_reflects_delta_in_summary(self):
        """Summary deltas in the comparison reflect the actual snapshot difference."""
        trending = OrgReportTrending(
            snapshots=[
                self._make_snapshot("2026-01-01T00:00:00Z", comp_count=100),
                self._make_snapshot("2026-02-01T00:00:00Z", comp_count=150),
            ],
            window_size=2,
        )
        result = trending.to_comparison()
        assert result is not None
        assert result.summary["components_delta"] == 50

    def test_to_comparison_supports_manual_id_only_snapshots_without_reported_totals(self):
        trending = OrgReportTrending(
            snapshots=[
                TrendingSnapshot(
                    timestamp="2026-01-01T00:00:00Z",
                    dv_ids={"dv1"},
                    dv_names={"dv1": "Legacy DV"},
                ),
                TrendingSnapshot(
                    timestamp="2026-02-01T00:00:00Z",
                    dv_ids={"dv1", "dv2"},
                    dv_names={"dv1": "Legacy DV", "dv2": "New DV"},
                ),
            ],
            window_size=2,
        )

        result = trending.to_comparison()

        assert result is not None
        assert result.data_views_added == ["dv2"]
        assert result.data_views_added_names == ["New DV"]
        assert result.summary["data_views_delta"] == 1

    def test_to_comparison_treats_explicit_dv_ids_as_authoritative_over_auxiliary_name_keys(self):
        trending = OrgReportTrending(
            snapshots=[
                TrendingSnapshot(
                    timestamp="2026-01-01T00:00:00Z",
                    dv_ids={"dv1"},
                    dv_names={"dv1": "Legacy DV", " dv1 ": "Duplicate metadata"},
                ),
                TrendingSnapshot(
                    timestamp="2026-02-01T00:00:00Z",
                    dv_ids={"dv1", "dv2"},
                    dv_names={"dv1": "Legacy DV", "dv2": "New DV", " dv1 ": "Duplicate metadata"},
                ),
            ],
            window_size=2,
        )

        result = trending.to_comparison()

        assert result is not None
        assert result.data_views_added == ["dv2"]
        assert result.data_views_removed == []
        assert result.summary["data_views_delta"] == 1


# ---------------------------------------------------------------------------
# Function Contracts: discover_snapshots()
# ---------------------------------------------------------------------------


class TestDiscoverSnapshotsContract:
    """Contract tests for discover_snapshots() public API."""

    def test_empty_directory_returns_empty_list(self, tmp_path):
        result = discover_snapshots(tmp_path)
        assert isinstance(result, list)
        assert result == []

    def test_nonexistent_directory_returns_empty_list(self, tmp_path):
        result = discover_snapshots(tmp_path / "does_not_exist")
        assert isinstance(result, list)
        assert result == []

    def test_returns_list_of_trending_snapshots(self, tmp_path):
        data = _make_org_report_json(timestamp="2026-01-01T00:00:00Z")
        _write_report(tmp_path, "report1.json", data)
        result = discover_snapshots(tmp_path)
        assert isinstance(result, list)
        assert all(isinstance(s, TrendingSnapshot) for s in result)

    def test_single_snapshot_returned(self, tmp_path):
        data = _make_org_report_json(timestamp="2026-01-15T00:00:00Z")
        _write_report(tmp_path, "report.json", data)
        result = discover_snapshots(tmp_path)
        assert len(result) == 1

    def test_ordered_oldest_to_newest(self, tmp_path):
        _write_report(tmp_path, "r2.json", _make_org_report_json(timestamp="2026-02-01T00:00:00Z"))
        _write_report(tmp_path, "r1.json", _make_org_report_json(timestamp="2026-01-01T00:00:00Z"))
        _write_report(tmp_path, "r3.json", _make_org_report_json(timestamp="2026-03-01T00:00:00Z"))
        result = discover_snapshots(tmp_path)
        assert len(result) == 3
        timestamps = [s.timestamp for s in result]
        assert timestamps == sorted(timestamps)

    def test_respects_window_size(self, tmp_path):
        for i in range(1, 8):
            _write_report(
                tmp_path,
                f"r{i}.json",
                _make_org_report_json(timestamp=f"2026-0{i}-01T00:00:00Z"),
            )
        result = discover_snapshots(tmp_path, window_size=3)
        assert len(result) <= 3

    def test_window_size_zero_returns_empty(self, tmp_path):
        _write_report(tmp_path, "r.json", _make_org_report_json(timestamp="2026-01-01T00:00:00Z"))
        result = discover_snapshots(tmp_path, window_size=0)
        assert result == []

    def test_non_org_report_json_files_are_ignored(self, tmp_path):
        (tmp_path / "random.json").write_text('{"foo": "bar"}', encoding="utf-8")
        result = discover_snapshots(tmp_path)
        assert result == []

    def test_invalid_json_files_are_ignored(self, tmp_path):
        (tmp_path / "bad.json").write_text("not json {{{", encoding="utf-8")
        result = discover_snapshots(tmp_path)
        assert result == []

    def test_returns_newest_n_when_window_smaller_than_total(self, tmp_path):
        for month in range(1, 6):
            _write_report(
                tmp_path,
                f"r{month}.json",
                _make_org_report_json(timestamp=f"2026-0{month}-01T00:00:00Z"),
            )
        result = discover_snapshots(tmp_path, window_size=2)
        assert len(result) == 2
        # Should be the two newest (months 4 and 5)
        assert result[-1].timestamp == "2026-05-01T00:00:00Z"
        assert result[0].timestamp == "2026-04-01T00:00:00Z"


# ---------------------------------------------------------------------------
# Function Contracts: compute_deltas()
# ---------------------------------------------------------------------------


class TestComputeDeltasContract:
    """Contract tests for compute_deltas() public API."""

    def _snap(
        self, ts: str, dv: int = 10, comp: int = 100, core: int = 80, iso: int = 20, sim: int = 2
    ) -> TrendingSnapshot:
        return TrendingSnapshot(
            timestamp=ts,
            data_view_count=dv,
            component_count=comp,
            core_count=core,
            isolated_count=iso,
            high_sim_pair_count=sim,
        )

    def test_returns_list(self):
        result = compute_deltas([])
        assert isinstance(result, list)

    def test_empty_list_returns_empty(self):
        assert compute_deltas([]) == []

    def test_single_snapshot_returns_empty(self):
        assert compute_deltas([self._snap("2026-01-01T00:00:00Z")]) == []

    def test_len_equals_snapshots_minus_one(self):
        snaps = [self._snap(f"2026-0{i}-01T00:00:00Z") for i in range(1, 5)]
        result = compute_deltas(snaps)
        assert len(result) == len(snaps) - 1

    def test_all_elements_are_trending_delta(self):
        snaps = [self._snap(f"2026-0{i}-01T00:00:00Z") for i in range(1, 4)]
        result = compute_deltas(snaps)
        assert all(isinstance(d, TrendingDelta) for d in result)

    def test_delta_signs_correct_for_growth(self):
        snaps = [
            self._snap("2026-01-01T00:00:00Z", dv=10, comp=100, core=80, iso=20, sim=2),
            self._snap("2026-02-01T00:00:00Z", dv=15, comp=150, core=100, iso=40, sim=5),
        ]
        deltas = compute_deltas(snaps)
        assert len(deltas) == 1
        d = deltas[0]
        assert d.data_view_delta == 5
        assert d.component_delta == 50
        assert d.core_delta == 20
        assert d.isolated_delta == 20
        assert d.high_sim_pair_delta == 3

    def test_delta_signs_correct_for_shrinkage(self):
        snaps = [
            self._snap("2026-01-01T00:00:00Z", dv=15, comp=150),
            self._snap("2026-02-01T00:00:00Z", dv=10, comp=100),
        ]
        deltas = compute_deltas(snaps)
        assert deltas[0].data_view_delta == -5
        assert deltas[0].component_delta == -50

    def test_timestamps_reference_correct_snapshots(self):
        snaps = [
            self._snap("2026-01-01T00:00:00Z"),
            self._snap("2026-02-01T00:00:00Z"),
            self._snap("2026-03-01T00:00:00Z"),
        ]
        deltas = compute_deltas(snaps)
        assert deltas[0].from_timestamp == "2026-01-01T00:00:00Z"
        assert deltas[0].to_timestamp == "2026-02-01T00:00:00Z"
        assert deltas[1].from_timestamp == "2026-02-01T00:00:00Z"
        assert deltas[1].to_timestamp == "2026-03-01T00:00:00Z"

    def test_id_only_manual_snapshots_use_effective_totals_for_deltas(self):
        snaps = [
            TrendingSnapshot(timestamp="2026-01-01T00:00:00Z", dv_ids={"dv1"}),
            TrendingSnapshot(timestamp="2026-02-01T00:00:00Z", dv_ids={"dv1", "dv2"}),
        ]

        deltas = compute_deltas(snaps)

        assert len(deltas) == 1
        assert deltas[0].data_view_delta == 1


# ---------------------------------------------------------------------------
# Function Contracts: compute_drift_scores()
# ---------------------------------------------------------------------------


class TestComputeDriftScoresContract:
    """Contract tests for compute_drift_scores() public API."""

    def _snap_with_dvs(self, ts: str, dv_ids: set, counts: dict | None = None) -> TrendingSnapshot:
        return TrendingSnapshot(
            timestamp=ts,
            dv_ids=set(dv_ids),
            dv_component_counts=counts or dict.fromkeys(dv_ids, 100),
            dv_core_ratios=dict.fromkeys(dv_ids, 0.5),
            dv_max_similarity=dict.fromkeys(dv_ids, 0.0),
        )

    def test_returns_dict(self):
        result = compute_drift_scores([])
        assert isinstance(result, dict)

    def test_empty_list_returns_empty_dict(self):
        assert compute_drift_scores([]) == {}

    def test_single_snapshot_returns_empty_dict(self):
        snap = self._snap_with_dvs("2026-01-01T00:00:00Z", {"dv1"})
        assert compute_drift_scores([snap]) == {}

    def test_fewer_than_two_snapshots_returns_empty_dict(self):
        snap = TrendingSnapshot(timestamp="2026-01-01T00:00:00Z")
        result = compute_drift_scores([snap])
        assert result == {}

    def test_values_in_range_zero_to_one(self):
        snaps = [
            self._snap_with_dvs("2026-01-01T00:00:00Z", {"dv1", "dv2"}, {"dv1": 100, "dv2": 200}),
            self._snap_with_dvs("2026-02-01T00:00:00Z", {"dv1", "dv2"}, {"dv1": 150, "dv2": 200}),
        ]
        result = compute_drift_scores(snaps)
        assert isinstance(result, dict)
        for value in result.values():
            assert 0.0 <= value <= 1.0, f"score {value} out of [0.0, 1.0]"

    def test_dict_keys_are_dv_id_strings(self):
        snaps = [
            self._snap_with_dvs("2026-01-01T00:00:00Z", {"dv-a", "dv-b"}),
            self._snap_with_dvs("2026-02-01T00:00:00Z", {"dv-a", "dv-b"}, {"dv-a": 50, "dv-b": 100}),
        ]
        result = compute_drift_scores(snaps)
        assert all(isinstance(k, str) for k in result)

    def test_no_change_across_snapshots_yields_zero_scores(self):
        """When nothing changes, all drift scores should be zero."""
        identical_snaps = [
            self._snap_with_dvs("2026-01-01T00:00:00Z", {"dv1"}, {"dv1": 100}),
            self._snap_with_dvs("2026-02-01T00:00:00Z", {"dv1"}, {"dv1": 100}),
        ]
        result = compute_drift_scores(identical_snaps)
        for v in result.values():
            assert v == 0.0

    def test_dv_union_across_window_is_captured(self):
        """DVs appearing in any snapshot are included in drift scores."""
        snaps = [
            self._snap_with_dvs("2026-01-01T00:00:00Z", {"dv1"}),
            self._snap_with_dvs("2026-02-01T00:00:00Z", {"dv1", "dv2"}),
        ]
        result = compute_drift_scores(snaps)
        assert "dv1" in result
        assert "dv2" in result

    def test_snapshots_with_no_dv_ids_returns_empty(self):
        snaps = [
            TrendingSnapshot(timestamp="2026-01-01T00:00:00Z"),
            TrendingSnapshot(timestamp="2026-02-01T00:00:00Z"),
        ]
        result = compute_drift_scores(snaps)
        assert result == {}


# ---------------------------------------------------------------------------
# Function Contracts: build_trending()
# ---------------------------------------------------------------------------


class TestBuildTrendingContract:
    """Contract tests for build_trending() public API."""

    def test_returns_none_for_empty_directory(self, tmp_path):
        result = build_trending(tmp_path)
        assert result is None

    def test_returns_none_for_single_snapshot(self, tmp_path):
        _write_report(tmp_path, "r.json", _make_org_report_json(timestamp="2026-01-01T00:00:00Z"))
        result = build_trending(tmp_path)
        assert result is None

    def test_returns_org_report_trending_for_two_or_more_snapshots(self, tmp_path):
        _write_report(tmp_path, "r1.json", _make_org_report_json(timestamp="2026-01-01T00:00:00Z"))
        _write_report(tmp_path, "r2.json", _make_org_report_json(timestamp="2026-02-01T00:00:00Z"))
        result = build_trending(tmp_path)
        assert isinstance(result, OrgReportTrending)

    def test_returned_trending_has_correct_snapshot_count(self, tmp_path):
        for month in range(1, 4):
            _write_report(
                tmp_path,
                f"r{month}.json",
                _make_org_report_json(timestamp=f"2026-0{month}-01T00:00:00Z"),
            )
        result = build_trending(tmp_path)
        assert result is not None
        assert result.window_size == 3
        assert len(result.snapshots) == 3

    def test_returned_trending_has_deltas(self, tmp_path):
        _write_report(tmp_path, "r1.json", _make_org_report_json(timestamp="2026-01-01T00:00:00Z"))
        _write_report(tmp_path, "r2.json", _make_org_report_json(timestamp="2026-02-01T00:00:00Z"))
        result = build_trending(tmp_path)
        assert result is not None
        assert len(result.deltas) == 1

    def test_returned_trending_has_drift_scores_dict(self, tmp_path):
        _write_report(tmp_path, "r1.json", _make_org_report_json(timestamp="2026-01-01T00:00:00Z"))
        _write_report(tmp_path, "r2.json", _make_org_report_json(timestamp="2026-02-01T00:00:00Z"))
        result = build_trending(tmp_path)
        assert result is not None
        assert isinstance(result.drift_scores, dict)

    def test_window_size_limits_snapshots(self, tmp_path):
        for i in range(1, 6):
            _write_report(
                tmp_path,
                f"r{i}.json",
                _make_org_report_json(timestamp=f"2026-0{i}-01T00:00:00Z"),
            )
        result = build_trending(tmp_path, window_size=2)
        assert result is not None
        assert result.window_size == 2

    def test_current_snapshot_is_appended(self, tmp_path):
        _write_report(tmp_path, "r1.json", _make_org_report_json(timestamp="2026-01-01T00:00:00Z"))
        current = TrendingSnapshot(
            timestamp="2026-02-15T00:00:00Z",
            data_view_count=12,
            component_count=110,
            core_count=85,
            isolated_count=25,
        )
        result = build_trending(tmp_path, current_snapshot=current)
        assert result is not None
        assert result.snapshots[-1].timestamp == "2026-02-15T00:00:00Z"

    def test_returns_none_when_nonexistent_directory(self, tmp_path):
        result = build_trending(tmp_path / "does_not_exist")
        assert result is None


# ---------------------------------------------------------------------------
# Snapshot Utils Contracts: parse_snapshot_timestamp()
# ---------------------------------------------------------------------------


class TestParseSnapshotTimestampContract:
    """Contract tests for parse_snapshot_timestamp()."""

    def test_returns_datetime_for_valid_iso_timestamp(self):
        result = parse_snapshot_timestamp("2026-01-01T00:00:00Z")
        assert isinstance(result, datetime)

    def test_returns_none_for_none(self):
        assert parse_snapshot_timestamp(None) is None

    def test_returns_none_for_empty_string(self):
        assert parse_snapshot_timestamp("") is None

    def test_returns_none_for_invalid_timestamp(self):
        assert parse_snapshot_timestamp("not-a-date") is None

    def test_returned_datetime_is_utc(self):
        result = parse_snapshot_timestamp("2026-06-15T12:00:00Z")
        assert result is not None
        assert result.tzinfo is not None
        assert result.tzinfo == UTC

    def test_z_suffix_is_treated_as_utc(self):
        result = parse_snapshot_timestamp("2026-06-15T12:00:00Z")
        assert result is not None
        assert result.hour == 12

    def test_naive_datetime_is_treated_as_utc(self):
        result = parse_snapshot_timestamp("2026-06-15T12:00:00")
        assert result is not None
        assert result.tzinfo == UTC


# ---------------------------------------------------------------------------
# Snapshot Utils Contracts: snapshot_epoch()
# ---------------------------------------------------------------------------


class TestSnapshotEpochContract:
    """Contract tests for snapshot_epoch()."""

    def test_returns_float_for_valid_timestamp(self):
        result = snapshot_epoch("2026-01-01T00:00:00Z")
        assert isinstance(result, float)

    def test_returns_none_for_none(self):
        assert snapshot_epoch(None) is None

    def test_returns_none_for_invalid_string(self):
        assert snapshot_epoch("garbage") is None

    def test_epoch_is_positive(self):
        result = snapshot_epoch("2026-01-01T00:00:00Z")
        assert result is not None
        assert result > 0.0

    def test_later_timestamp_has_greater_epoch(self):
        early = snapshot_epoch("2026-01-01T00:00:00Z")
        late = snapshot_epoch("2026-12-31T00:00:00Z")
        assert early is not None
        assert late is not None
        assert late > early


# ---------------------------------------------------------------------------
# Snapshot Utils Contracts: chronological_snapshot_sort_fields()
# ---------------------------------------------------------------------------


class TestChronologicalSnapshotSortFieldsContract:
    """Contract tests for chronological_snapshot_sort_fields()."""

    def test_returns_four_tuple(self):
        result = chronological_snapshot_sort_fields("2026-01-01T00:00:00Z")
        assert isinstance(result, tuple)
        assert len(result) == 4

    def test_first_field_is_bool_none_indicator(self):
        valid_result = chronological_snapshot_sort_fields("2026-01-01T00:00:00Z")
        none_result = chronological_snapshot_sort_fields(None)
        # Valid timestamps sort before invalid/None
        assert valid_result[0] is False
        assert none_result[0] is True

    def test_valid_timestamps_sort_older_before_newer(self):
        older = chronological_snapshot_sort_fields("2026-01-01T00:00:00Z")
        newer = chronological_snapshot_sort_fields("2026-06-01T00:00:00Z")
        assert older < newer

    def test_none_timestamps_sort_last(self):
        valid = chronological_snapshot_sort_fields("2026-01-01T00:00:00Z")
        none_ts = chronological_snapshot_sort_fields(None)
        assert valid < none_ts

    def test_tie_breaker_is_fourth_element(self):
        result = chronological_snapshot_sort_fields("2026-01-01T00:00:00Z", tie_breaker="tiebreak_value")
        assert result[3] == "tiebreak_value"


# ---------------------------------------------------------------------------
# Snapshot Utils Contracts: org_report_snapshot_metadata()
# ---------------------------------------------------------------------------


class TestOrgReportSnapshotMetadataContract:
    """Contract tests for org_report_snapshot_metadata()."""

    def test_returns_none_for_non_snapshot_payload(self):
        result = org_report_snapshot_metadata({"foo": "bar"})
        assert result is None

    @pytest.mark.parametrize("value", [([],), ("not-a-snapshot",), (42,), (None,)])
    def test_returns_none_for_non_mapping_json_root(self, value):
        assert org_report_snapshot_metadata(value) is None

    def test_returns_dict_for_valid_snapshot(self):
        data = _make_org_report_json()
        result = org_report_snapshot_metadata(data)
        assert isinstance(result, dict)

    def test_contains_expected_keys(self):
        data = _make_org_report_json(timestamp="2026-01-01T00:00:00Z", org_id="org123")
        result = org_report_snapshot_metadata(data)
        assert result is not None
        expected_keys = {
            "org_id",
            "generated_at",
            "generated_at_epoch",
            "filepath",
            "filename",
            "data_views_total",
            "data_views_analyzed",
            "data_views_failed",
            "total_unique_components",
            "core_count",
            "isolated_count",
            "high_similarity_pairs",
            "snapshot_id",
            "content_hash",
            "history_eligible",
            "history_exclusion_reason",
        }
        for key in expected_keys:
            assert key in result, f"Expected key '{key}' missing from metadata"

    def test_org_id_field_is_populated(self):
        data = _make_org_report_json(org_id="my_org_id")
        result = org_report_snapshot_metadata(data)
        assert result is not None
        assert result["org_id"] == "my_org_id"

    def test_generated_at_epoch_is_float_or_none(self):
        data = _make_org_report_json(timestamp="2026-01-01T00:00:00Z")
        result = org_report_snapshot_metadata(data)
        assert result is not None
        epoch = result["generated_at_epoch"]
        assert epoch is None or isinstance(epoch, float)

    def test_history_eligible_is_bool(self):
        data = _make_org_report_json()
        result = org_report_snapshot_metadata(data)
        assert result is not None
        assert isinstance(result["history_eligible"], bool)

    def test_source_path_is_used_for_filepath(self, tmp_path):
        data = _make_org_report_json()
        path = tmp_path / "my_report.json"
        result = org_report_snapshot_metadata(data, source_path=path)
        assert result is not None
        assert result["filename"] == "my_report.json"


# ---------------------------------------------------------------------------
# Snapshot Utils Contracts: org_report_snapshot_data_view_stats()
# ---------------------------------------------------------------------------


class TestOrgReportSnapshotDataViewStatsContract:
    """Contract tests for org_report_snapshot_data_view_stats()."""

    def test_returns_org_report_snapshot_data_view_stats(self):
        data = _make_org_report_json(dv_count=5)
        result = org_report_snapshot_data_view_stats(data)
        assert isinstance(result, OrgReportSnapshotDataViewStats)

    def test_result_fields_are_ints(self):
        data = _make_org_report_json(dv_count=5)
        result = org_report_snapshot_data_view_stats(data)
        assert isinstance(result.reported_total, int)
        assert isinstance(result.analyzed_total, int)
        assert isinstance(result.failed_total, int)
        assert isinstance(result.raw_total, int)
        assert isinstance(result.successful_row_total, int)

    def test_all_counts_are_non_negative(self):
        data = _make_org_report_json(dv_count=10)
        result = org_report_snapshot_data_view_stats(data)
        assert result.reported_total >= 0
        assert result.analyzed_total >= 0
        assert result.failed_total >= 0
        assert result.raw_total >= 0
        assert result.successful_row_total >= 0

    def test_empty_data_views_list_gives_zero_counts(self):
        data = _make_org_report_json(dv_count=0, data_views=[])
        result = org_report_snapshot_data_view_stats(data)
        assert result.raw_total == 0
        assert result.successful_row_total == 0

    def test_with_successful_data_views(self):
        data_views = [
            {"data_view_id": "dv1", "data_view_name": "DV One", "metrics_count": 5, "dimensions_count": 10},
            {"data_view_id": "dv2", "data_view_name": "DV Two", "metrics_count": 3, "dimensions_count": 7},
        ]
        data = _make_org_report_json(dv_count=2, data_views=data_views)
        result = org_report_snapshot_data_view_stats(data)
        assert result.raw_total == 2
        assert result.successful_row_total == 2

    def test_with_failed_data_view(self):
        data_views = [
            {"data_view_id": "dv1", "data_view_name": "DV One"},
            {"data_view_id": "dv2", "error": "timeout"},
        ]
        data = _make_org_report_json(dv_count=2, data_views=data_views)
        result = org_report_snapshot_data_view_stats(data)
        assert result.raw_total == 2
        assert result.successful_row_total == 1

    def test_frozen_dataclass_is_immutable(self):
        data = _make_org_report_json()
        result = org_report_snapshot_data_view_stats(data)
        with pytest.raises((AttributeError, TypeError)):
            result.reported_total = 999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Cache Contracts: OrgReportCache.save_org_report_snapshot()
# ---------------------------------------------------------------------------


class TestOrgReportCacheSaveSnapshotContract:
    """Contract tests for OrgReportCache.save_org_report_snapshot()."""

    def test_creates_file_on_disk(self, tmp_path):
        cache = OrgReportCache(cache_dir=tmp_path)
        data = _make_org_report_json(timestamp="2026-01-01T00:00:00Z", org_id="org1")
        result_path = cache.save_org_report_snapshot(data, org_id="org1")
        assert result_path.exists()
        assert result_path.is_file()

    def test_returns_path_object(self, tmp_path):
        cache = OrgReportCache(cache_dir=tmp_path)
        data = _make_org_report_json(timestamp="2026-01-01T00:00:00Z", org_id="org1")
        result_path = cache.save_org_report_snapshot(data, org_id="org1")
        assert isinstance(result_path, Path)

    def test_saved_file_is_valid_json(self, tmp_path):
        cache = OrgReportCache(cache_dir=tmp_path)
        data = _make_org_report_json(timestamp="2026-01-01T00:00:00Z", org_id="org1")
        result_path = cache.save_org_report_snapshot(data, org_id="org1")
        content = json.loads(result_path.read_text(encoding="utf-8"))
        assert isinstance(content, dict)

    def test_saved_file_contains_snapshot_meta(self, tmp_path):
        cache = OrgReportCache(cache_dir=tmp_path)
        data = _make_org_report_json(timestamp="2026-01-01T00:00:00Z", org_id="org1")
        result_path = cache.save_org_report_snapshot(data, org_id="org1")
        content = json.loads(result_path.read_text(encoding="utf-8"))
        assert "_snapshot_meta" in content
        meta = content["_snapshot_meta"]
        assert "snapshot_id" in meta
        assert "content_hash" in meta
        assert "history_eligible" in meta

    def test_raises_for_invalid_payload(self, tmp_path):
        cache = OrgReportCache(cache_dir=tmp_path)
        with pytest.raises(ValueError):
            cache.save_org_report_snapshot({"foo": "bar"}, org_id="org1")

    def test_file_saved_under_org_subdir(self, tmp_path):
        cache = OrgReportCache(cache_dir=tmp_path)
        data = _make_org_report_json(timestamp="2026-01-01T00:00:00Z", org_id="myorg")
        result_path = cache.save_org_report_snapshot(data, org_id="myorg")
        # The saved file should be inside the snapshot root directory
        snapshot_root = cache.get_org_report_snapshot_root_dir()
        assert str(result_path).startswith(str(snapshot_root))

    def test_infers_org_id_from_payload(self, tmp_path):
        cache = OrgReportCache(cache_dir=tmp_path)
        data = _make_org_report_json(timestamp="2026-01-01T00:00:00Z", org_id="inferred_org")
        # No explicit org_id passed
        result_path = cache.save_org_report_snapshot(data)
        assert result_path.exists()


# ---------------------------------------------------------------------------
# Cache Contracts: OrgReportCache.prune_org_report_snapshots()
# ---------------------------------------------------------------------------


class TestOrgReportCachePruneSnapshotsContract:
    """Contract tests for OrgReportCache.prune_org_report_snapshots()."""

    def _save_snapshots(self, cache: OrgReportCache, count: int, org_id: str = "org1") -> list[Path]:
        paths = []
        for i in range(1, count + 1):
            data = _make_org_report_json(
                timestamp=f"2026-{i:02d}-01T00:00:00Z" if i <= 12 else f"2027-{i - 12:02d}-01T00:00:00Z",
                org_id=org_id,
            )
            path = cache.save_org_report_snapshot(data, org_id=org_id)
            paths.append(path)
        return paths

    def test_returns_list(self, tmp_path):
        cache = OrgReportCache(cache_dir=tmp_path)
        result = cache.prune_org_report_snapshots(keep_last=5)
        assert isinstance(result, list)

    def test_no_retention_criteria_returns_empty(self, tmp_path):
        cache = OrgReportCache(cache_dir=tmp_path)
        self._save_snapshots(cache, 3)
        result = cache.prune_org_report_snapshots()
        assert result == []

    def test_keep_last_removes_old_files(self, tmp_path):
        cache = OrgReportCache(cache_dir=tmp_path)
        self._save_snapshots(cache, 5)
        deleted = cache.prune_org_report_snapshots(keep_last=2)
        # Some files should have been deleted
        assert len(deleted) > 0
        # The deleted files should not exist on disk
        for p in deleted:
            assert not Path(p).exists()

    def test_keep_last_preserves_most_recent_snapshots(self, tmp_path):
        cache = OrgReportCache(cache_dir=tmp_path)
        self._save_snapshots(cache, 5)
        cache.prune_org_report_snapshots(keep_last=2)
        # Count remaining snapshots
        remaining = list(cache.get_org_report_snapshot_root_dir().rglob("*.json"))
        assert len(remaining) == 2

    def test_deleted_paths_are_strings(self, tmp_path):
        cache = OrgReportCache(cache_dir=tmp_path)
        self._save_snapshots(cache, 4)
        deleted = cache.prune_org_report_snapshots(keep_last=1)
        assert all(isinstance(p, str) for p in deleted)

    def test_idempotent_second_prune_deletes_nothing(self, tmp_path):
        cache = OrgReportCache(cache_dir=tmp_path)
        self._save_snapshots(cache, 5)
        cache.prune_org_report_snapshots(keep_last=2)
        deleted_second = cache.prune_org_report_snapshots(keep_last=2)
        assert deleted_second == []
