"""Adversarial and stress tests for org-report trending feature.

Tests cover malformed snapshot files, corrupted cache directories, timestamp
edge cases, org ID edge cases, drift score robustness, and pipeline stress.
"""

from __future__ import annotations

import json
from pathlib import Path

from cja_auto_sdr.org.models import TrendingSnapshot
from cja_auto_sdr.org.snapshot_utils import (
    is_org_report_snapshot_payload,
    org_report_snapshot_content_hash,
    org_report_snapshot_history_eligible,
)
from cja_auto_sdr.org.trending import (
    _extract_snapshot_from_json,
    _load_snapshot_from_file,
    build_trending,
    compute_deltas,
    compute_drift_scores,
    discover_snapshots,
)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def _make_valid_snapshot(
    timestamp: str = "2026-01-01T00:00:00Z",
    org_id: str = "adv_org",
    dv_count: int = 3,
) -> dict:
    return {
        "generated_at": timestamp,
        "org_id": org_id,
        "report_type": "org_analysis",
        "parameters": {"skip_similarity": False, "org_stats_only": False},
        "summary": {
            "data_views_total": dv_count,
            "total_unique_components": 50,
            "similarity_analysis_complete": True,
            "similarity_analysis_mode": "complete",
        },
        "distribution": {
            "core": {
                "total": 20,
                "metrics_count": 10,
                "dimensions_count": 10,
                "metrics": [],
                "dimensions": [],
            },
            "isolated": {"total": 5, "metrics_count": 3, "dimensions_count": 2},
        },
        "data_views": [
            {
                "data_view_id": f"dv{i}",
                "data_view_name": f"DV {i}",
                "metrics_count": 10,
                "dimensions_count": 5,
            }
            for i in range(dv_count)
        ],
        "component_index": {},
        "similarity_pairs": [],
    }


def _write_snapshot(directory: Path, filename: str, payload: dict) -> Path:
    path = directory / filename
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Class 1: Malformed snapshot files
# ---------------------------------------------------------------------------


class TestMalformedSnapshotFiles:
    def test_truncated_json_is_skipped(self, tmp_path: Path):
        bad = tmp_path / "truncated.json"
        bad.write_bytes(b'{"generated_at": "2026-01-01T00:00:00Z", "org_id": "x"')
        result = _load_snapshot_from_file(bad)
        assert result is None

    def test_array_root_json_is_skipped(self, tmp_path: Path):
        bad = tmp_path / "array.json"
        bad.write_text(json.dumps([{"generated_at": "2026-01-01T00:00:00Z"}]), encoding="utf-8")
        result = _load_snapshot_from_file(bad)
        assert result is None

    def test_valid_json_missing_required_keys_is_skipped(self, tmp_path: Path):
        bad = tmp_path / "missing_keys.json"
        bad.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
        result = _load_snapshot_from_file(bad)
        assert result is None

    def test_empty_file_is_skipped(self, tmp_path: Path):
        empty = tmp_path / "empty.json"
        empty.write_bytes(b"")
        result = _load_snapshot_from_file(empty)
        assert result is None

    def test_binary_garbage_is_skipped(self, tmp_path: Path):
        binary = tmp_path / "garbage.json"
        binary.write_bytes(bytes(range(256)))
        result = _load_snapshot_from_file(binary)
        assert result is None

    def test_snapshot_with_all_zero_metrics_loads_gracefully(self, tmp_path: Path):
        payload = _make_valid_snapshot()
        payload["summary"]["total_unique_components"] = 0
        payload["summary"]["data_views_total"] = 0
        payload["data_views"] = []
        f = _write_snapshot(tmp_path, "zero_metrics.json", payload)
        # Should either load or return None — must not raise
        result = _load_snapshot_from_file(f)
        # it's still a valid structure; may load with zero counts
        if result is not None:
            assert result.component_count == 0
            assert result.data_view_count == 0

    def test_snapshot_with_negative_metric_values_loads_gracefully(self, tmp_path: Path):
        payload = _make_valid_snapshot()
        payload["summary"]["total_unique_components"] = -5
        payload["summary"]["data_views_total"] = -1
        f = _write_snapshot(tmp_path, "negative.json", payload)
        # No crash expected
        result = _load_snapshot_from_file(f)
        # Negative counts may be coerced to 0 or loaded as-is depending on policy
        assert result is None or isinstance(result, TrendingSnapshot)

    def test_mixed_valid_and_invalid_files_only_loads_valid(self, tmp_path: Path):
        good = _write_snapshot(tmp_path, "good.json", _make_valid_snapshot(timestamp="2026-01-01T00:00:00Z"))
        (tmp_path / "bad1.json").write_bytes(b"not json at all")
        (tmp_path / "bad2.json").write_text("null", encoding="utf-8")
        (tmp_path / "bad3.json").write_bytes(b"")

        snapshots = discover_snapshots(tmp_path, window_size=10, org_id="adv_org")
        assert len(snapshots) >= 1
        paths = [s.source_path for s in snapshots]
        assert any(str(good) in (p or "") for p in paths)


# ---------------------------------------------------------------------------
# Class 2: Corrupted cache directories
# ---------------------------------------------------------------------------


class TestCorruptedCacheDirectories:
    def test_cache_dir_is_a_file_returns_empty(self, tmp_path: Path):
        not_a_dir = tmp_path / "notadir"
        not_a_dir.write_text("I am a file", encoding="utf-8")
        result = discover_snapshots(not_a_dir, window_size=10)
        assert result == []

    def test_empty_subdirectories_return_empty(self, tmp_path: Path):
        subdir = tmp_path / "empty_subdir"
        subdir.mkdir()
        result = discover_snapshots(subdir, window_size=10)
        assert result == []

    def test_nonexistent_cache_dir_returns_empty(self, tmp_path: Path):
        missing = tmp_path / "does_not_exist"
        result = discover_snapshots(missing, window_size=10)
        assert result == []

    def test_build_trending_with_nonexistent_cache_dir_returns_none(self, tmp_path: Path):
        missing = tmp_path / "does_not_exist"
        result = build_trending(missing, window_size=10)
        assert result is None

    def test_explicit_history_file_nonexistent_is_skipped_gracefully(self, tmp_path: Path):
        _write_snapshot(tmp_path, "snap1.json", _make_valid_snapshot(timestamp="2026-01-01T00:00:00Z"))
        missing_explicit = tmp_path / "nonexistent_history.json"
        # Should not crash; explicit file that doesn't exist is silently ignored
        result = discover_snapshots(tmp_path, window_size=10, explicit_file=missing_explicit, org_id="adv_org")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# Class 3: Timestamp edge cases
# ---------------------------------------------------------------------------


class TestTimestampEdgeCases:
    def test_future_timestamp_year_2099_sorts_after_present(self, tmp_path: Path):
        snap_present = _make_valid_snapshot(timestamp="2026-01-01T00:00:00Z")
        snap_future = _make_valid_snapshot(timestamp="2099-12-31T23:59:59Z")
        _write_snapshot(tmp_path, "present.json", snap_present)
        _write_snapshot(tmp_path, "future.json", snap_future)
        snapshots = discover_snapshots(tmp_path, window_size=10, org_id="adv_org")
        assert len(snapshots) == 2
        assert snapshots[0].timestamp < snapshots[1].timestamp

    def test_epoch_zero_timestamp_is_handled(self, tmp_path: Path):
        payload = _make_valid_snapshot(timestamp="1970-01-01T00:00:00Z")
        _write_snapshot(tmp_path, "epoch_zero.json", payload)
        snapshots = discover_snapshots(tmp_path, window_size=10, org_id="adv_org")
        assert len(snapshots) >= 1
        assert snapshots[0].timestamp == "1970-01-01T00:00:00Z"

    def test_invalid_timestamp_format_snapshot_is_skipped_or_placed_last(self, tmp_path: Path):
        payload = _make_valid_snapshot()
        payload["generated_at"] = "not-a-timestamp"
        _write_snapshot(tmp_path, "bad_ts.json", payload)
        # Undated snapshots should be placed last or skipped — no crash
        result = discover_snapshots(tmp_path, window_size=10, org_id="adv_org")
        assert isinstance(result, list)

    def test_duplicate_timestamps_across_snapshots_deduped_by_content(self, tmp_path: Path):
        snap_a = _make_valid_snapshot(timestamp="2026-06-01T00:00:00Z")
        snap_b = _make_valid_snapshot(timestamp="2026-06-01T00:00:00Z")
        snap_b["data_views"][0]["metrics_count"] = 99  # different content
        _write_snapshot(tmp_path, "dup_a.json", snap_a)
        _write_snapshot(tmp_path, "dup_b.json", snap_b)
        result = discover_snapshots(tmp_path, window_size=10, org_id="adv_org")
        # Both have different content hashes → both should survive deduplication
        assert len(result) == 2


# ---------------------------------------------------------------------------
# Class 4: Org ID edge cases
# ---------------------------------------------------------------------------


class TestOrgIdEdgeCases:
    def test_unicode_org_id_cjk_characters_handled(self, tmp_path: Path):
        org_id = "组织テスト한국어"
        payload = _make_valid_snapshot(org_id=org_id)
        _write_snapshot(tmp_path, "unicode_org.json", payload)
        result = discover_snapshots(tmp_path, window_size=10, org_id=org_id)
        assert len(result) == 1
        assert result[0].org_id == org_id

    def test_org_id_with_path_separators_is_handled_safely(self, tmp_path: Path):
        """Path-traversal attempt in org_id should not cause filesystem errors."""
        traversal_org_id = "../../../etc/passwd"
        payload = _make_valid_snapshot(org_id=traversal_org_id)
        _write_snapshot(tmp_path, "traversal.json", payload)
        # Should not crash; org filtering may or may not match
        try:
            result = discover_snapshots(tmp_path, window_size=10, org_id=traversal_org_id)
            assert isinstance(result, list)
        except ValueError:
            pass  # Raising is also acceptable

    def test_empty_string_org_id_handled(self, tmp_path: Path):
        payload = _make_valid_snapshot(org_id="")
        payload["org_id"] = ""
        _write_snapshot(tmp_path, "empty_org.json", payload)
        # Should not crash
        result = discover_snapshots(tmp_path, window_size=10)
        assert isinstance(result, list)

    def test_very_long_org_id_handled(self, tmp_path: Path):
        long_org_id = "x" * 1200
        payload = _make_valid_snapshot(org_id=long_org_id)
        _write_snapshot(tmp_path, "long_org.json", payload)
        result = discover_snapshots(tmp_path, window_size=10, org_id=long_org_id)
        assert isinstance(result, list)
        if result:
            assert result[0].org_id == long_org_id

    def test_org_id_filter_excludes_wrong_org(self, tmp_path: Path):
        snap_a = _make_valid_snapshot(org_id="org_alpha")
        snap_b = _make_valid_snapshot(org_id="org_beta")
        _write_snapshot(tmp_path, "alpha.json", snap_a)
        _write_snapshot(tmp_path, "beta.json", snap_b)
        result = discover_snapshots(tmp_path, window_size=10, org_id="org_alpha")
        assert all(s.org_id == "org_alpha" for s in result)


# ---------------------------------------------------------------------------
# Class 5: Drift score robustness
# ---------------------------------------------------------------------------


class TestDriftScoreRobustness:
    def _snapshot_from_payload(self, payload: dict, source_path: str | None = None) -> TrendingSnapshot | None:
        return _extract_snapshot_from_json(payload, source_path=source_path)

    def test_two_identical_snapshots_drift_is_zero(self):
        payload = _make_valid_snapshot(timestamp="2026-01-01T00:00:00Z")
        snap1 = self._snapshot_from_payload(payload, source_path="snap1.json")
        # Same content, different timestamp for sequencing
        payload2 = dict(payload)
        payload2 = {**payload, "generated_at": "2026-02-01T00:00:00Z"}
        snap2 = self._snapshot_from_payload(payload2, source_path="snap2.json")
        assert snap1 is not None and snap2 is not None
        scores = compute_drift_scores([snap1, snap2])
        assert all(v == 0.0 for v in scores.values()), f"Expected all-zero drift: {scores}"

    def test_all_data_views_replaced_gives_maximum_presence_drift(self):
        snap1 = TrendingSnapshot(
            timestamp="2026-01-01T00:00:00Z",
            org_id="test_org",
            dv_ids={"dv_old_1", "dv_old_2"},
            dv_component_counts={"dv_old_1": 10, "dv_old_2": 10},
            dv_core_ratios={"dv_old_1": 0.5, "dv_old_2": 0.5},
            dv_max_similarity={"dv_old_1": 0.0, "dv_old_2": 0.0},
        )
        snap2 = TrendingSnapshot(
            timestamp="2026-02-01T00:00:00Z",
            org_id="test_org",
            dv_ids={"dv_new_1", "dv_new_2"},
            dv_component_counts={"dv_new_1": 10, "dv_new_2": 10},
            dv_core_ratios={"dv_new_1": 0.5, "dv_new_2": 0.5},
            dv_max_similarity={"dv_new_1": 0.0, "dv_new_2": 0.0},
        )
        scores = compute_drift_scores([snap1, snap2])
        # All DVs should have non-zero drift (presence change)
        assert len(scores) == 4
        assert all(v > 0.0 for v in scores.values()), f"Expected non-zero drift: {scores}"

    def test_drift_scores_all_zero_metrics_no_div_by_zero(self):
        snap1 = TrendingSnapshot(
            timestamp="2026-01-01T00:00:00Z",
            org_id="test_org",
            dv_ids={"dv1"},
            dv_component_counts={"dv1": 0},
            dv_core_ratios={"dv1": 0.0},
            dv_max_similarity={"dv1": 0.0},
        )
        snap2 = TrendingSnapshot(
            timestamp="2026-02-01T00:00:00Z",
            org_id="test_org",
            dv_ids={"dv1"},
            dv_component_counts={"dv1": 0},
            dv_core_ratios={"dv1": 0.0},
            dv_max_similarity={"dv1": 0.0},
        )
        # Must not raise ZeroDivisionError
        scores = compute_drift_scores([snap1, snap2])
        assert isinstance(scores, dict)
        assert scores.get("dv1", 0.0) == 0.0

    def test_dv_appears_disappears_reappears_across_three_snapshots(self):
        snap1 = TrendingSnapshot(
            timestamp="2026-01-01T00:00:00Z",
            org_id="test_org",
            dv_ids={"dv_stable", "dv_volatile"},
            dv_component_counts={"dv_stable": 10, "dv_volatile": 5},
            dv_core_ratios={"dv_stable": 0.5, "dv_volatile": 0.0},
            dv_max_similarity={"dv_stable": 0.0, "dv_volatile": 0.0},
        )
        snap2 = TrendingSnapshot(
            timestamp="2026-02-01T00:00:00Z",
            org_id="test_org",
            dv_ids={"dv_stable"},
            dv_component_counts={"dv_stable": 10},
            dv_core_ratios={"dv_stable": 0.5},
            dv_max_similarity={"dv_stable": 0.0},
        )
        snap3 = TrendingSnapshot(
            timestamp="2026-03-01T00:00:00Z",
            org_id="test_org",
            dv_ids={"dv_stable", "dv_volatile"},
            dv_component_counts={"dv_stable": 10, "dv_volatile": 5},
            dv_core_ratios={"dv_stable": 0.5, "dv_volatile": 0.0},
            dv_max_similarity={"dv_stable": 0.0, "dv_volatile": 0.0},
        )
        scores = compute_drift_scores([snap1, snap2, snap3])
        assert isinstance(scores, dict)
        # dv_volatile changed presence twice; dv_stable did not
        volatile_score = scores.get("dv_volatile", 0.0)
        stable_score = scores.get("dv_stable", 0.0)
        assert volatile_score >= stable_score, f"volatile ({volatile_score}) should score >= stable ({stable_score})"

    def test_single_snapshot_drift_returns_empty_dict(self):
        snap = TrendingSnapshot(
            timestamp="2026-01-01T00:00:00Z",
            dv_ids={"dv1"},
            dv_component_counts={"dv1": 10},
            dv_core_ratios={"dv1": 0.5},
            dv_max_similarity={"dv1": 0.0},
        )
        scores = compute_drift_scores([snap])
        assert scores == {}

    def test_no_snapshots_drift_returns_empty_dict(self):
        scores = compute_drift_scores([])
        assert scores == {}

    def test_snapshots_with_no_dv_ids_drift_returns_empty_dict(self):
        snap1 = TrendingSnapshot(timestamp="2026-01-01T00:00:00Z", dv_ids=set())
        snap2 = TrendingSnapshot(timestamp="2026-02-01T00:00:00Z", dv_ids=set())
        scores = compute_drift_scores([snap1, snap2])
        assert scores == {}


# ---------------------------------------------------------------------------
# Class 6: Trending pipeline stress tests
# ---------------------------------------------------------------------------


class TestTrendingPipelineStress:
    def test_fifty_plus_snapshot_window_computes_correctly(self, tmp_path: Path):
        """Verify correctness with 55 snapshot files written to disk."""
        for i in range(55):
            ts = f"2026-01-{i + 1:02d}T00:00:00Z" if i < 31 else f"2026-02-{i - 30:02d}T00:00:00Z"
            payload = _make_valid_snapshot(timestamp=ts, dv_count=3)
            _write_snapshot(tmp_path, f"snap_{i:03d}.json", payload)

        result = build_trending(tmp_path, window_size=50, org_id="adv_org")
        assert result is not None
        assert result.window_size <= 50
        assert len(result.snapshots) == result.window_size
        assert len(result.deltas) == result.window_size - 1

    def test_window_size_zero_returns_none(self, tmp_path: Path):
        _write_snapshot(tmp_path, "snap1.json", _make_valid_snapshot(timestamp="2026-01-01T00:00:00Z"))
        _write_snapshot(tmp_path, "snap2.json", _make_valid_snapshot(timestamp="2026-02-01T00:00:00Z"))
        result = build_trending(tmp_path, window_size=0, org_id="adv_org")
        assert result is None

    def test_window_size_one_returns_none(self, tmp_path: Path):
        _write_snapshot(tmp_path, "snap1.json", _make_valid_snapshot(timestamp="2026-01-01T00:00:00Z"))
        _write_snapshot(tmp_path, "snap2.json", _make_valid_snapshot(timestamp="2026-02-01T00:00:00Z"))
        result = build_trending(tmp_path, window_size=1, org_id="adv_org")
        assert result is None  # requires >= 2 snapshots in window

    def test_current_snapshot_duplicate_is_not_added_twice(self, tmp_path: Path):
        payload1 = _make_valid_snapshot(timestamp="2026-01-01T00:00:00Z")
        payload2 = _make_valid_snapshot(timestamp="2026-02-01T00:00:00Z")
        _write_snapshot(tmp_path, "snap1.json", payload1)
        _write_snapshot(tmp_path, "snap2.json", payload2)

        # Build the "current" snapshot from the same payload as snap2
        current = _extract_snapshot_from_json(payload2, source_path=str(tmp_path / "snap2.json"))
        assert current is not None

        result = build_trending(tmp_path, window_size=10, current_snapshot=current, org_id="adv_org")
        assert result is not None
        # The duplicate current snapshot should not be counted twice
        timestamps = [s.timestamp for s in result.snapshots]
        assert timestamps.count("2026-02-01T00:00:00Z") == 1

    def test_content_hash_determinism(self):
        """Same payload → same hash on repeated calls."""
        payload = _make_valid_snapshot()
        h1 = org_report_snapshot_content_hash(payload)
        h2 = org_report_snapshot_content_hash(payload)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex digest

    def test_content_hash_different_for_different_payloads(self):
        p1 = _make_valid_snapshot(timestamp="2026-01-01T00:00:00Z")
        p2 = _make_valid_snapshot(timestamp="2026-02-01T00:00:00Z")
        assert org_report_snapshot_content_hash(p1) != org_report_snapshot_content_hash(p2)

    def test_build_trending_only_one_snapshot_returns_none(self, tmp_path: Path):
        _write_snapshot(tmp_path, "snap1.json", _make_valid_snapshot(timestamp="2026-01-01T00:00:00Z"))
        result = build_trending(tmp_path, window_size=10, org_id="adv_org")
        assert result is None

    def test_build_trending_two_snapshots_produces_one_delta(self, tmp_path: Path):
        _write_snapshot(tmp_path, "snap1.json", _make_valid_snapshot(timestamp="2026-01-01T00:00:00Z"))
        _write_snapshot(tmp_path, "snap2.json", _make_valid_snapshot(timestamp="2026-02-01T00:00:00Z"))
        result = build_trending(tmp_path, window_size=10, org_id="adv_org")
        assert result is not None
        assert len(result.deltas) == 1
        assert result.deltas[0].from_timestamp == "2026-01-01T00:00:00Z"
        assert result.deltas[0].to_timestamp == "2026-02-01T00:00:00Z"

    def test_compute_deltas_empty_list_returns_empty(self):
        assert compute_deltas([]) == []

    def test_compute_deltas_single_snapshot_returns_empty(self):
        snap = TrendingSnapshot(timestamp="2026-01-01T00:00:00Z", data_view_count=3)
        assert compute_deltas([snap]) == []

    def test_compute_deltas_captures_component_growth(self):
        snap1 = TrendingSnapshot(timestamp="2026-01-01T00:00:00Z", data_view_count=3, component_count=50)
        snap2 = TrendingSnapshot(timestamp="2026-02-01T00:00:00Z", data_view_count=4, component_count=65)
        deltas = compute_deltas([snap1, snap2])
        assert len(deltas) == 1
        assert deltas[0].data_view_delta == 1
        assert deltas[0].component_delta == 15


# ---------------------------------------------------------------------------
# Class 7: History eligibility edge cases
# ---------------------------------------------------------------------------


class TestHistoryEligibilityEdgeCases:
    def test_skip_similarity_true_excludes_snapshot_from_history(self, tmp_path: Path):
        payload = _make_valid_snapshot()
        payload["parameters"]["skip_similarity"] = True
        del payload["summary"]["similarity_analysis_complete"]
        del payload["summary"]["similarity_analysis_mode"]
        assert not org_report_snapshot_history_eligible(payload)

    def test_org_stats_only_true_excludes_snapshot_from_history(self, tmp_path: Path):
        payload = _make_valid_snapshot()
        payload["parameters"]["org_stats_only"] = True
        del payload["summary"]["similarity_analysis_complete"]
        del payload["summary"]["similarity_analysis_mode"]
        assert not org_report_snapshot_history_eligible(payload)

    def test_similarity_analysis_complete_true_includes_in_history(self):
        payload = _make_valid_snapshot()
        assert org_report_snapshot_history_eligible(payload)

    def test_snapshot_with_similarity_pairs_null_excluded(self):
        payload = _make_valid_snapshot()
        payload["similarity_pairs"] = None
        del payload["summary"]["similarity_analysis_complete"]
        del payload["summary"]["similarity_analysis_mode"]
        assert not org_report_snapshot_history_eligible(payload)

    def test_history_ineligible_snapshots_skipped_by_load(self, tmp_path: Path):
        payload = _make_valid_snapshot()
        payload["parameters"]["skip_similarity"] = True
        del payload["summary"]["similarity_analysis_complete"]
        del payload["summary"]["similarity_analysis_mode"]
        f = _write_snapshot(tmp_path, "ineligible.json", payload)
        result = _load_snapshot_from_file(f)
        assert result is None


# ---------------------------------------------------------------------------
# Class 8: is_org_report_snapshot_payload robustness
# ---------------------------------------------------------------------------


class TestIsOrgReportSnapshotPayloadRobustness:
    def test_non_mapping_types_return_false(self):
        for value in (None, [], 42, "string", True):
            assert not is_org_report_snapshot_payload(value)

    def test_missing_timestamp_returns_false(self):
        payload = {"org_id": "test", "report_type": "org_analysis"}
        assert not is_org_report_snapshot_payload(payload)

    def test_report_type_org_analysis_with_timestamp_returns_true(self):
        payload = {"generated_at": "2026-01-01T00:00:00Z", "report_type": "org_analysis"}
        assert is_org_report_snapshot_payload(payload)

    def test_summary_mapping_with_timestamp_returns_true(self):
        payload = {"generated_at": "2026-01-01T00:00:00Z", "summary": {}}
        assert is_org_report_snapshot_payload(payload)

    def test_distribution_mapping_with_timestamp_returns_true(self):
        payload = {"generated_at": "2026-01-01T00:00:00Z", "distribution": {}}
        assert is_org_report_snapshot_payload(payload)

    def test_data_views_list_with_timestamp_returns_true(self):
        payload = {"generated_at": "2026-01-01T00:00:00Z", "data_views": []}
        assert is_org_report_snapshot_payload(payload)
