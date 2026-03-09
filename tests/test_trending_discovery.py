"""Tests for org-report trending: snapshot discovery, deltas, and drift scoring."""

import json

import pytest

from cja_auto_sdr.org.models import OrgReportTrending, TrendingSnapshot
from cja_auto_sdr.org.trending import (
    _extract_snapshot_from_json,
    build_trending,
    compute_deltas,
    compute_drift_scores,
    discover_snapshots,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_org_report_json(
    timestamp="2026-01-01T00:00:00Z",
    org_id="test_org",
    dv_count=10,
    comp_count=100,
    core_metrics=None,
    core_dimensions=None,
    isolated_metrics=None,
    isolated_dimensions=None,
    data_views=None,
    component_index=None,
    similarity_pairs=None,
):
    """Build a minimal org-report JSON dict."""
    return {
        "generated_at": timestamp,
        "org_id": org_id,
        "summary": {
            "data_views_total": dv_count,
            "total_unique_components": comp_count,
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
        "data_views": data_views or [],
        "component_index": component_index or {},
        "similarity_pairs": similarity_pairs or [],
    }


def _write_report(tmp_path, filename, data):
    path = tmp_path / filename
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Snapshot extraction
# ---------------------------------------------------------------------------


class TestExtractSnapshotFromJson:
    def test_basic_extraction(self):
        data = _make_org_report_json(dv_count=12, comp_count=200)
        snap = _extract_snapshot_from_json(data)
        assert snap is not None
        assert snap.timestamp == "2026-01-01T00:00:00Z"
        assert snap.data_view_count == 12
        assert snap.component_count == 200

    def test_missing_timestamp_returns_none(self):
        data = {"summary": {"data_views_total": 5}}
        assert _extract_snapshot_from_json(data) is None

    def test_fallback_timestamp_key(self):
        data = {"timestamp": "2026-06-01", "summary": {"data_views_total": 5}, "org_id": "test_org"}
        snap = _extract_snapshot_from_json(data)
        assert snap is not None
        assert snap.timestamp == "2026-06-01"

    def test_core_and_isolated_from_totals(self):
        data = _make_org_report_json(
            core_metrics=["m1", "m2"],
            core_dimensions=["d1"],
            isolated_metrics=["m3"],
            isolated_dimensions=[],
        )
        snap = _extract_snapshot_from_json(data)
        assert snap.core_count == 3
        assert snap.isolated_count == 1

    def test_core_fallback_to_counts(self):
        """When 'total' is missing, fall back to metrics_count + dimensions_count."""
        data = _make_org_report_json()
        del data["distribution"]["core"]["total"]
        data["distribution"]["core"]["metrics_count"] = 5
        data["distribution"]["core"]["dimensions_count"] = 3
        snap = _extract_snapshot_from_json(data)
        assert snap.core_count == 8

    def test_high_sim_pair_count(self):
        data = _make_org_report_json(
            similarity_pairs=[
                {"dv1_id": "a", "dv2_id": "b", "jaccard_similarity": 0.95},
                {"dv1_id": "c", "dv2_id": "d", "jaccard_similarity": 0.5},
                {"dv1_id": "e", "dv2_id": "f", "jaccard_similarity": 0.91},
            ],
        )
        snap = _extract_snapshot_from_json(data)
        assert snap.high_sim_pair_count == 2

    def test_per_dv_component_counts(self):
        data = _make_org_report_json(
            data_views=[
                {"id": "dv1", "name": "DV 1", "metrics_count": 50, "dimensions_count": 30},
                {"id": "dv2", "name": "DV 2", "metrics_count": 20, "dimensions_count": 10},
            ],
        )
        snap = _extract_snapshot_from_json(data)
        assert snap.dv_component_counts == {"dv1": 80, "dv2": 30}
        assert snap.dv_ids == {"dv1", "dv2"}
        assert snap.dv_names == {"dv1": "DV 1", "dv2": "DV 2"}

    def test_core_ratios_are_derived_from_component_index(self):
        data = _make_org_report_json(
            core_metrics=["m1"],
            core_dimensions=["d1"],
            data_views=[
                {"id": "dv1", "metrics_count": 2, "dimensions_count": 1},
                {"id": "dv2", "metrics_count": 1, "dimensions_count": 1},
            ],
            component_index={
                "m1": {"type": "metric", "data_views": ["dv1", "dv2"]},
                "d1": {"type": "dimension", "data_views": ["dv1"]},
            },
        )
        snap = _extract_snapshot_from_json(data)
        assert snap.dv_core_ratios["dv1"] == pytest.approx(2 / 3, abs=0.0001)
        assert snap.dv_core_ratios["dv2"] == pytest.approx(1 / 2, abs=0.0001)

    def test_dv_max_similarity(self):
        data = _make_org_report_json(
            similarity_pairs=[
                {"dv1_id": "a", "dv2_id": "b", "jaccard_similarity": 0.8},
                {"dv1_id": "a", "dv2_id": "c", "jaccard_similarity": 0.9},
            ],
        )
        snap = _extract_snapshot_from_json(data)
        assert snap.dv_max_similarity["a"] == 0.9
        assert snap.dv_max_similarity["b"] == 0.8
        assert snap.dv_max_similarity["c"] == 0.9

    def test_dv_count_fallback_to_data_views_length(self):
        data = _make_org_report_json(
            dv_count=0,
            data_views=[
                {"id": "dv1", "metrics_count": 10, "dimensions_count": 5},
                {"id": "dv2", "metrics_count": 10, "dimensions_count": 5},
            ],
        )
        snap = _extract_snapshot_from_json(data)
        assert snap.data_view_count == 2

    def test_legacy_summary_and_distribution_keys_still_supported(self):
        data = {
            "generated_at": "2026-01-01T00:00:00Z",
            "org_id": "test_org",
            "summary": {"total_data_views": 4, "total_unique_components": 10},
            "distribution": {
                "core": {"core_metrics": ["m1"], "core_dimensions": ["d1"], "metrics_count": 1, "dimensions_count": 1},
                "isolated": {"metrics_count": 1, "dimensions_count": 0},
            },
            "data_views": [{"data_view_id": "dv1", "metric_count": 2, "dimension_count": 1}],
            "component_index": {
                "m1": {"data_views": ["dv1"]},
                "d1": {"data_views": ["dv1"]},
            },
        }
        snap = _extract_snapshot_from_json(data)
        assert snap is not None
        assert snap.data_view_count == 4
        assert snap.core_count == 2


# ---------------------------------------------------------------------------
# Cache discovery
# ---------------------------------------------------------------------------


class TestDiscoverSnapshots:
    def test_empty_directory(self, tmp_path):
        result = discover_snapshots(tmp_path, window_size=10)
        assert result == []

    def test_nonexistent_directory(self, tmp_path):
        result = discover_snapshots(tmp_path / "nonexistent", window_size=10)
        assert result == []

    def test_discovers_json_files(self, tmp_path):
        for i in range(3):
            ts = f"2026-0{i + 1}-01T00:00:00Z"
            _write_report(tmp_path, f"report_{i}.json", _make_org_report_json(timestamp=ts))
        result = discover_snapshots(tmp_path, window_size=10)
        assert len(result) == 3
        assert result[0].timestamp == "2026-01-01T00:00:00Z"
        assert result[2].timestamp == "2026-03-01T00:00:00Z"

    def test_window_trims_to_most_recent(self, tmp_path):
        for i in range(5):
            ts = f"2026-0{i + 1}-01T00:00:00Z"
            _write_report(tmp_path, f"report_{i}.json", _make_org_report_json(timestamp=ts))
        result = discover_snapshots(tmp_path, window_size=3)
        assert len(result) == 3
        assert result[0].timestamp == "2026-03-01T00:00:00Z"
        assert result[2].timestamp == "2026-05-01T00:00:00Z"

    def test_skips_corrupt_json(self, tmp_path):
        (tmp_path / "good.json").write_text(
            json.dumps(_make_org_report_json(timestamp="2026-01-01")),
            encoding="utf-8",
        )
        (tmp_path / "bad.json").write_text("not json{{{", encoding="utf-8")
        result = discover_snapshots(tmp_path, window_size=10)
        assert len(result) == 1

    def test_skips_non_org_report_json(self, tmp_path):
        (tmp_path / "org.json").write_text(
            json.dumps(_make_org_report_json(timestamp="2026-01-01")),
            encoding="utf-8",
        )
        (tmp_path / "other.json").write_text(
            json.dumps({"type": "sdr", "format": "excel"}),
            encoding="utf-8",
        )
        result = discover_snapshots(tmp_path, window_size=10)
        assert len(result) == 1

    def test_explicit_file_included(self, tmp_path):
        _write_report(tmp_path, "cached.json", _make_org_report_json(timestamp="2026-01-01"))
        explicit = tmp_path / "subdir"
        explicit.mkdir()
        _write_report(explicit, "baseline.json", _make_org_report_json(timestamp="2025-12-01"))
        result = discover_snapshots(tmp_path, window_size=10, explicit_file=explicit / "baseline.json")
        assert len(result) == 2
        assert result[0].timestamp == "2025-12-01"

    def test_explicit_file_is_retained_when_window_is_trimmed(self, tmp_path):
        for month in range(1, 5):
            _write_report(tmp_path, f"cached_{month}.json", _make_org_report_json(timestamp=f"2026-0{month}-01"))
        explicit = tmp_path / "subdir"
        explicit.mkdir()
        _write_report(explicit, "baseline.json", _make_org_report_json(timestamp="2025-12-01"))

        result = discover_snapshots(tmp_path, window_size=3, explicit_file=explicit / "baseline.json")

        assert [snapshot.timestamp for snapshot in result] == ["2025-12-01", "2026-03-01", "2026-04-01"]

    def test_same_timestamp_distinct_snapshots_are_preserved(self, tmp_path):
        _write_report(tmp_path, "a.json", _make_org_report_json(timestamp="2026-01-01", comp_count=100))
        _write_report(tmp_path, "b.json", _make_org_report_json(timestamp="2026-01-01", comp_count=200))
        result = discover_snapshots(tmp_path, window_size=10)
        assert len(result) == 2
        assert sorted(snapshot.component_count for snapshot in result) == [100, 200]

    def test_explicit_file_deduplicates(self, tmp_path):
        _write_report(tmp_path, "report.json", _make_org_report_json(timestamp="2026-01-01"))
        result = discover_snapshots(tmp_path, window_size=10, explicit_file=tmp_path / "report.json")
        assert len(result) == 1

    def test_explicit_file_nonexistent(self, tmp_path):
        _write_report(tmp_path, "report.json", _make_org_report_json(timestamp="2026-01-01"))
        result = discover_snapshots(tmp_path, window_size=10, explicit_file=tmp_path / "gone.json")
        assert len(result) == 1

    def test_filters_discovered_snapshots_to_org_id(self, tmp_path):
        _write_report(tmp_path, "a.json", _make_org_report_json(timestamp="2026-01-01", org_id="org_a"))
        _write_report(tmp_path, "b.json", _make_org_report_json(timestamp="2026-02-01", org_id="org_b"))
        result = discover_snapshots(tmp_path, window_size=10, org_id="org_a")
        assert len(result) == 1
        assert result[0].org_id == "org_a"

    def test_orders_snapshots_by_normalized_utc_timestamp(self, tmp_path):
        _write_report(tmp_path, "late_local.json", _make_org_report_json(timestamp="2026-03-01T00:15:00-02:00"))
        _write_report(tmp_path, "early_utc.json", _make_org_report_json(timestamp="2026-03-01T01:30:00+02:00"))

        result = discover_snapshots(tmp_path, window_size=10)

        assert [snapshot.timestamp for snapshot in result] == [
            "2026-03-01T01:30:00+02:00",
            "2026-03-01T00:15:00-02:00",
        ]


# ---------------------------------------------------------------------------
# Delta computation
# ---------------------------------------------------------------------------


class TestComputeDeltas:
    def test_empty_list(self):
        assert compute_deltas([]) == []

    def test_single_snapshot(self):
        snap = TrendingSnapshot(timestamp="2026-01-01")
        assert compute_deltas([snap]) == []

    def test_two_snapshots(self):
        snaps = [
            TrendingSnapshot(
                timestamp="2026-01-01",
                data_view_count=10,
                component_count=100,
                core_count=80,
                isolated_count=20,
                high_sim_pair_count=2,
            ),
            TrendingSnapshot(
                timestamp="2026-02-01",
                data_view_count=12,
                component_count=130,
                core_count=95,
                isolated_count=35,
                high_sim_pair_count=3,
            ),
        ]
        deltas = compute_deltas(snaps)
        assert len(deltas) == 1
        assert deltas[0].data_view_delta == 2
        assert deltas[0].component_delta == 30
        assert deltas[0].core_delta == 15
        assert deltas[0].isolated_delta == 15
        assert deltas[0].high_sim_pair_delta == 1

    def test_three_snapshots(self):
        snaps = [
            TrendingSnapshot(timestamp="2026-01-01", component_count=100),
            TrendingSnapshot(timestamp="2026-02-01", component_count=120),
            TrendingSnapshot(timestamp="2026-03-01", component_count=110),
        ]
        deltas = compute_deltas(snaps)
        assert len(deltas) == 2
        assert deltas[0].component_delta == 20
        assert deltas[1].component_delta == -10

    def test_identical_snapshots(self):
        snaps = [
            TrendingSnapshot(timestamp="2026-01-01", data_view_count=5, component_count=50),
            TrendingSnapshot(timestamp="2026-02-01", data_view_count=5, component_count=50),
        ]
        deltas = compute_deltas(snaps)
        assert deltas[0].data_view_delta == 0
        assert deltas[0].component_delta == 0


# ---------------------------------------------------------------------------
# Drift scoring
# ---------------------------------------------------------------------------


class TestComputeDriftScores:
    def test_empty_snapshots(self):
        assert compute_drift_scores([]) == {}

    def test_single_snapshot(self):
        snap = TrendingSnapshot(timestamp="2026-01-01", dv_ids={"a"})
        assert compute_drift_scores([snap]) == {}

    def test_all_static_scores_zero(self):
        snaps = [
            TrendingSnapshot(
                timestamp="2026-01-01",
                dv_ids={"a", "b"},
                dv_component_counts={"a": 100, "b": 50},
                dv_core_ratios={"a": 0.8, "b": 0.6},
                dv_max_similarity={"a": 0.9, "b": 0.7},
            ),
            TrendingSnapshot(
                timestamp="2026-02-01",
                dv_ids={"a", "b"},
                dv_component_counts={"a": 100, "b": 50},
                dv_core_ratios={"a": 0.8, "b": 0.6},
                dv_max_similarity={"a": 0.9, "b": 0.7},
            ),
        ]
        scores = compute_drift_scores(snaps)
        assert scores["a"] == 0.0
        assert scores["b"] == 0.0

    def test_added_dv_scores_high(self):
        snaps = [
            TrendingSnapshot(
                timestamp="2026-01-01",
                dv_ids={"a"},
                dv_component_counts={"a": 100},
                dv_core_ratios={"a": 0.8},
                dv_max_similarity={"a": 0.0},
            ),
            TrendingSnapshot(
                timestamp="2026-02-01",
                dv_ids={"a", "b"},
                dv_component_counts={"a": 100, "b": 50},
                dv_core_ratios={"a": 0.8, "b": 0.6},
                dv_max_similarity={"a": 0.0, "b": 0.0},
            ),
        ]
        scores = compute_drift_scores(snaps)
        # 'b' was added, 'a' was static — b should score higher
        assert scores["b"] > scores["a"]
        assert scores["a"] == 0.0

    def test_component_change_drives_score(self):
        snaps = [
            TrendingSnapshot(
                timestamp="2026-01-01",
                dv_ids={"a", "b"},
                dv_component_counts={"a": 100, "b": 50},
                dv_core_ratios={"a": 0.5, "b": 0.5},
                dv_max_similarity={"a": 0.5, "b": 0.5},
            ),
            TrendingSnapshot(
                timestamp="2026-02-01",
                dv_ids={"a", "b"},
                dv_component_counts={"a": 200, "b": 50},
                dv_core_ratios={"a": 0.5, "b": 0.5},
                dv_max_similarity={"a": 0.5, "b": 0.5},
            ),
        ]
        scores = compute_drift_scores(snaps)
        assert scores["a"] > scores["b"]
        assert scores["b"] == 0.0
        assert scores["a"] == pytest.approx(0.4, abs=0.01)  # 0.4 weight * 1.0 normalized

    def test_scores_are_deterministic(self):
        snaps = [
            TrendingSnapshot(
                timestamp="2026-01-01",
                dv_ids={"a", "b", "c"},
                dv_component_counts={"a": 100, "b": 50, "c": 75},
                dv_core_ratios={"a": 0.8, "b": 0.4, "c": 0.6},
                dv_max_similarity={"a": 0.9, "b": 0.3, "c": 0.6},
            ),
            TrendingSnapshot(
                timestamp="2026-02-01",
                dv_ids={"a", "b", "c"},
                dv_component_counts={"a": 120, "b": 80, "c": 75},
                dv_core_ratios={"a": 0.7, "b": 0.5, "c": 0.6},
                dv_max_similarity={"a": 0.8, "b": 0.5, "c": 0.6},
            ),
        ]
        scores1 = compute_drift_scores(snaps)
        scores2 = compute_drift_scores(snaps)
        assert scores1 == scores2

    def test_removed_dv_scores_high(self):
        snaps = [
            TrendingSnapshot(
                timestamp="2026-01-01",
                dv_ids={"a", "b"},
                dv_component_counts={"a": 100, "b": 50},
                dv_core_ratios={"a": 0.8, "b": 0.6},
                dv_max_similarity={"a": 0.5, "b": 0.5},
            ),
            TrendingSnapshot(
                timestamp="2026-02-01",
                dv_ids={"a"},
                dv_component_counts={"a": 100},
                dv_core_ratios={"a": 0.8},
                dv_max_similarity={"a": 0.5},
            ),
        ]
        scores = compute_drift_scores(snaps)
        assert scores["b"] > scores["a"]
        assert scores["a"] == 0.0


# ---------------------------------------------------------------------------
# build_trending integration
# ---------------------------------------------------------------------------


class TestBuildTrending:
    def test_returns_none_with_zero_snapshots(self, tmp_path):
        result = build_trending(tmp_path)
        assert result is None

    def test_returns_none_with_one_snapshot(self, tmp_path):
        _write_report(tmp_path, "r.json", _make_org_report_json(timestamp="2026-01-01"))
        result = build_trending(tmp_path)
        assert result is None

    def test_builds_trending_with_two_snapshots(self, tmp_path):
        _write_report(tmp_path, "a.json", _make_org_report_json(timestamp="2026-01-01", dv_count=10, comp_count=100))
        _write_report(tmp_path, "b.json", _make_org_report_json(timestamp="2026-02-01", dv_count=12, comp_count=120))
        result = build_trending(tmp_path)
        assert isinstance(result, OrgReportTrending)
        assert result.window_size == 2
        assert len(result.snapshots) == 2
        assert len(result.deltas) == 1

    def test_current_snapshot_appended(self, tmp_path):
        _write_report(tmp_path, "a.json", _make_org_report_json(timestamp="2026-01-01"))
        current = TrendingSnapshot(timestamp="2026-02-01", data_view_count=15, component_count=200)
        result = build_trending(tmp_path, current_snapshot=current)
        assert result is not None
        assert result.window_size == 2
        assert result.snapshots[-1].timestamp == "2026-02-01"

    def test_current_snapshot_deduplicates(self, tmp_path):
        _write_report(tmp_path, "a.json", _make_org_report_json(timestamp="2026-01-01"))
        _write_report(tmp_path, "b.json", _make_org_report_json(timestamp="2026-02-01"))
        current = _extract_snapshot_from_json(_make_org_report_json(timestamp="2026-02-01"))
        result = build_trending(tmp_path, current_snapshot=current)
        assert result.window_size == 2

    def test_window_size_respected(self, tmp_path):
        for i in range(10):
            ts = f"2026-{i + 1:02d}-01T00:00:00Z"
            _write_report(tmp_path, f"r{i}.json", _make_org_report_json(timestamp=ts))
        result = build_trending(tmp_path, window_size=3)
        assert result.window_size == 3

    def test_explicit_file_folded_in(self, tmp_path):
        _write_report(tmp_path, "cached.json", _make_org_report_json(timestamp="2026-02-01"))
        subdir = tmp_path / "sub"
        subdir.mkdir()
        _write_report(subdir, "baseline.json", _make_org_report_json(timestamp="2026-01-01"))
        result = build_trending(tmp_path, explicit_file=subdir / "baseline.json")
        assert result is not None
        assert result.window_size == 2
        assert result.snapshots[0].timestamp == "2026-01-01"

    def test_explicit_file_remains_in_window_after_current_snapshot_is_added(self, tmp_path):
        for month in range(2, 5):
            _write_report(tmp_path, f"cached_{month}.json", _make_org_report_json(timestamp=f"2026-0{month}-01"))
        subdir = tmp_path / "sub"
        subdir.mkdir()
        _write_report(subdir, "baseline.json", _make_org_report_json(timestamp="2026-01-01"))

        current = TrendingSnapshot(timestamp="2026-05-01", data_view_count=20, component_count=200)
        result = build_trending(tmp_path, window_size=3, explicit_file=subdir / "baseline.json", current_snapshot=current)

        assert result is not None
        assert [snapshot.timestamp for snapshot in result.snapshots] == ["2026-01-01", "2026-04-01", "2026-05-01"]

    def test_org_id_scoping_excludes_other_org_snapshots(self, tmp_path):
        _write_report(tmp_path, "a.json", _make_org_report_json(timestamp="2026-01-01", org_id="org_a"))
        _write_report(tmp_path, "b.json", _make_org_report_json(timestamp="2026-02-01", org_id="org_b"))
        current = TrendingSnapshot(timestamp="2026-03-01", org_id="org_a")
        result = build_trending(tmp_path, current_snapshot=current, org_id="org_a")
        assert result is not None
        assert [snapshot.org_id for snapshot in result.snapshots] == ["org_a", "org_a"]
