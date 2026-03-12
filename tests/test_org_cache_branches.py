"""Focused branch coverage for org cache and lock helper logic."""

from __future__ import annotations

import errno
import json
import os
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from cja_auto_sdr.org.cache import OrgReportCache, OrgReportLock
from cja_auto_sdr.org.models import DataViewSummary


def _summary(dv_id: str) -> DataViewSummary:
    return DataViewSummary(
        data_view_id=dv_id,
        data_view_name=f"Data View {dv_id}",
        metric_ids={"metric/1"},
        dimension_ids={"dimension/1"},
        metric_count=1,
        dimension_count=1,
    )


def _full_fidelity_snapshot(payload: dict[str, object]) -> dict[str, object]:
    summary = payload.setdefault("summary", {})
    if isinstance(summary, dict):
        summary.setdefault("similarity_analysis_complete", True)
        summary.setdefault("similarity_analysis_mode", "complete")
        data_views_total = summary.get("data_views_total") or summary.get("total_data_views")
        if isinstance(data_views_total, int) and data_views_total >= 0 and "data_views" not in payload:
            payload["data_views"] = [
                {"id": f"dv_{index:03d}", "name": f"DV {index}", "metrics_count": 0, "dimensions_count": 0}
                for index in range(1, data_views_total + 1)
            ]

    parameters = payload.setdefault("parameters", {})
    if isinstance(parameters, dict):
        parameters.setdefault("skip_similarity", False)
        parameters.setdefault("org_stats_only", False)

    payload.setdefault("similarity_pairs", [])
    return payload


def test_cache_default_dir_uses_home(tmp_path: Path):
    with patch("cja_auto_sdr.org.cache.Path.home", return_value=tmp_path):
        cache = OrgReportCache()
    assert cache.cache_dir == tmp_path / ".cja_auto_sdr" / "cache"


def test_load_cache_invalid_json_logs_warning(tmp_path: Path):
    cache_file = tmp_path / "org_report_cache.json"
    cache_file.write_text("{not valid json")
    logger = Mock()

    cache = OrgReportCache(cache_dir=tmp_path, logger=logger)

    assert cache._cache == {}
    logger.warning.assert_called_once()
    assert "Failed to load org report cache" in logger.warning.call_args[0][0]


def test_get_returns_none_without_fetched_at(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    cache._cache["dv_missing_fetched"] = {"data_view_id": "dv_missing_fetched"}
    assert cache.get("dv_missing_fetched") is None


def test_get_returns_none_for_stale_or_invalid_timestamp(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)

    stale_time = (datetime.now(UTC) - timedelta(hours=25)).isoformat()
    cache._cache["dv_stale"] = {"fetched_at": stale_time}
    assert cache.get("dv_stale", max_age_hours=24) is None

    cache._cache["dv_bad_ts"] = {"fetched_at": "definitely-not-iso"}
    assert cache.get("dv_bad_ts", max_age_hours=24) is None


@pytest.mark.parametrize(
    "required_flags",
    [
        {"include_names": True},
        {"include_metadata": True},
        {"include_component_types": True},
    ],
)
def test_get_rejects_when_required_flags_missing(tmp_path: Path, required_flags: dict[str, bool]):
    cache = OrgReportCache(cache_dir=tmp_path)
    cache._cache["dv_flags"] = {
        "data_view_id": "dv_flags",
        "data_view_name": "Flags DV",
        "fetched_at": datetime.now(UTC).isoformat(),
    }

    assert cache.get("dv_flags", required_flags=required_flags) is None


def test_get_logs_debug_on_deserialization_failure(tmp_path: Path):
    logger = Mock()
    cache = OrgReportCache(cache_dir=tmp_path, logger=logger)
    cache._cache["dv_broken"] = {
        "data_view_id": "dv_broken",
        "data_view_name": "Broken DV",
        "metric_ids": 123,  # not iterable -> set(123) raises
        "fetched_at": datetime.now(UTC).isoformat(),
    }

    assert cache.get("dv_broken") is None
    logger.debug.assert_called_once()


def test_put_many_empty_skips_save(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    with patch.object(cache, "_save_cache") as save:
        cache.put_many([])
    save.assert_not_called()


def test_put_many_saves_once_for_multiple_entries(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    with patch.object(cache, "_save_cache") as save:
        cache.put_many(
            [_summary("dv_one"), _summary("dv_two")],
            include_names=True,
            include_metadata=True,
            include_component_types=True,
        )

    save.assert_called_once()
    assert set(cache._cache) == {"dv_one", "dv_two"}
    assert cache._cache["dv_one"]["include_names"] is True
    assert cache._cache["dv_one"]["include_metadata"] is True
    assert cache._cache["dv_one"]["include_component_types"] is True


def test_has_valid_entry_handles_missing_and_invalid_timestamps(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)

    cache._cache["dv_missing_fetched"] = {}
    assert cache.has_valid_entry("dv_missing_fetched") is False

    cache._cache["dv_invalid_fetched"] = {"fetched_at": "invalid"}
    assert cache.has_valid_entry("dv_invalid_fetched") is False

    stale_time = (datetime.now(UTC) - timedelta(hours=48)).isoformat()
    cache._cache["dv_stale"] = {"fetched_at": stale_time}
    assert cache.has_valid_entry("dv_stale", max_age_hours=24) is False


def test_get_stats_reports_file_size(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)

    stats_before = cache.get_stats()
    assert stats_before["entries"] == 0
    assert stats_before["cache_size_bytes"] == 0

    cache.put(_summary("dv_stats"))

    stats_after = cache.get_stats()
    assert stats_after["entries"] == 1
    assert stats_after["cache_size_bytes"] > 0
    assert stats_after["cache_file"].endswith("org_report_cache.json")


def test_get_org_report_snapshot_dir_uses_collision_resistant_org_key(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    snapshot_dir = cache.get_org_report_snapshot_dir("org@test.example")
    assert snapshot_dir.parent == tmp_path / "org_report_snapshots"
    assert snapshot_dir.name.startswith("org_test_example__")


def test_iter_org_report_snapshot_dirs_returns_current_and_legacy_dirs(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)

    snapshot_dirs = cache._iter_org_report_snapshot_dirs("org@test.example")

    assert [path.name for path in snapshot_dirs] == [
        cache.get_org_report_snapshot_dir("org@test.example").name,
        "org_test_example",
    ]


def test_org_report_snapshot_dirs_do_not_collide_for_distinct_org_ids(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)

    report_a = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "a.b@AdobeOrg",
        "summary": {"data_views_total": 1, "total_unique_components": 1},
    }
    report_b = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "a_b@AdobeOrg",
        "summary": {"data_views_total": 1, "total_unique_components": 1},
    }

    path_a = cache.save_org_report_snapshot(report_a)
    path_b = cache.save_org_report_snapshot(report_b)

    assert path_a.parent != path_b.parent
    assert [snapshot["org_id"] for snapshot in cache.list_org_report_snapshots("a.b@AdobeOrg")] == ["a.b@AdobeOrg"]
    assert [snapshot["org_id"] for snapshot in cache.list_org_report_snapshots("a_b@AdobeOrg")] == ["a_b@AdobeOrg"]


def test_list_org_report_snapshots_reads_legacy_dir_and_filters_mismatched_org_metadata(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    legacy_dir = cache.get_org_report_snapshot_root_dir() / "org_test_example"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    (legacy_dir / "match.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-03-01T00:00:00Z",
                "org_id": "org@test.example",
                "summary": {"data_views_total": 1, "total_unique_components": 1},
            }
        ),
        encoding="utf-8",
    )
    (legacy_dir / "mismatch.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-03-02T00:00:00Z",
                "org_id": "other-org",
                "summary": {"data_views_total": 1, "total_unique_components": 1},
            }
        ),
        encoding="utf-8",
    )

    snapshots = cache.list_org_report_snapshots("org@test.example")

    assert [Path(snapshot["filepath"]).name for snapshot in snapshots] == ["match.json"]


def test_list_org_report_snapshots_deduplicates_migrated_copies_and_prefers_current_dir(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    current_path = cache.save_org_report_snapshot(
        {
            "generated_at": "2026-03-01T00:00:00Z",
            "org_id": "org@test.example",
            "summary": {"data_views_total": 1, "total_unique_components": 1},
        }
    )
    legacy_dir = cache.get_org_report_snapshot_root_dir() / "org_test_example"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy_copy = legacy_dir / current_path.name
    legacy_copy.write_text(current_path.read_text(encoding="utf-8"), encoding="utf-8")

    snapshots = cache.list_org_report_snapshots()

    assert len(snapshots) == 1
    assert snapshots[0]["filepath"] == str(current_path.resolve(strict=False))


def test_save_org_report_snapshot_writes_json_file(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    report = _full_fidelity_snapshot(
        {
            "generated_at": "2026-03-01T00:00:00Z",
            "org_id": "org@test.example",
            "summary": {"data_views_total": 2, "total_unique_components": 5},
        }
    )

    path = cache.save_org_report_snapshot(report)

    assert path.exists()
    assert path.parent == cache.get_org_report_snapshot_dir("org@test.example")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["org_id"] == "org@test.example"
    assert payload["_snapshot_meta"]["snapshot_id"]
    assert payload["_snapshot_meta"]["content_hash"]
    assert payload["_snapshot_meta"]["history_eligible"] is True
    assert payload["_snapshot_meta"]["history_exclusion_reason"] is None


def test_save_org_report_snapshot_failed_write_does_not_leave_partial_json(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    report = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "org@test.example",
        "summary": {"data_views_total": 2, "total_unique_components": 5},
    }
    snapshot_dir = cache.get_org_report_snapshot_dir("org@test.example")

    with patch("cja_auto_sdr.org.cache.json.dump", side_effect=OSError("disk full")):
        with pytest.raises(OSError, match="disk full"):
            cache.save_org_report_snapshot(report)

    assert snapshot_dir.exists()
    assert list(snapshot_dir.iterdir()) == []


def test_save_org_report_snapshot_persists_history_eligibility_metadata(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    report = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "org@test.example",
        "summary": {
            "data_views_total": 2,
            "total_unique_components": 5,
            "similarity_analysis_complete": False,
            "similarity_analysis_mode": "org_stats_only",
        },
        "distribution": {"core": {"total": 2}, "isolated": {"total": 3}},
        "similarity_pairs": [],
    }

    path = cache.save_org_report_snapshot(report)

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["_snapshot_meta"]["history_eligible"] is False
    assert payload["_snapshot_meta"]["history_exclusion_reason"] == "org_stats_only"

    listed = cache.list_org_report_snapshots("org@test.example")
    assert listed[0]["history_eligible"] is False
    assert listed[0]["history_exclusion_reason"] == "org_stats_only"

    inspected = cache.inspect_org_report_snapshot(path)
    assert inspected["history_eligible"] is False
    assert inspected["history_exclusion_reason"] == "org_stats_only"


def test_save_org_report_snapshot_skips_heavy_history_extractors(tmp_path: Path, monkeypatch):
    import cja_auto_sdr.org.snapshot_utils as snapshot_utils

    cache = OrgReportCache(cache_dir=tmp_path)
    report = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "org@test.example",
        "report_type": "org_analysis",
        "summary": {
            "data_views_total": 2,
            "total_unique_components": 5,
            "similarity_analysis_complete": False,
            "similarity_analysis_mode": "org_stats_only",
        },
        "distribution": {"core": {"total": 2}, "isolated": {"total": 3}},
        "component_index": {
            "comp_a": {"data_views": ["dv1"]},
            "comp_b": {"data_views": ["dv2"]},
        },
        "similarity_pairs": [
            {"dv1_id": "dv1", "dv2_id": "dv2", "jaccard_similarity": 0.99},
        ],
    }

    def fail_component_ids(_raw_component_index):
        raise AssertionError("save_org_report_snapshot extracted component ids")

    def fail_similarity_pairs(_rows, *, threshold=0.9):
        raise AssertionError(f"save_org_report_snapshot extracted similarity pairs at threshold {threshold}")

    monkeypatch.setattr(snapshot_utils, "_snapshot_component_ids", fail_component_ids)
    monkeypatch.setattr(snapshot_utils, "_org_report_high_similarity_pairs_from_rows", fail_similarity_pairs)

    path = cache.save_org_report_snapshot(report)

    assert path.exists()


def test_save_org_report_snapshot_rejects_non_snapshot_payload(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)

    with pytest.raises(ValueError, match="Invalid org-report snapshot payload"):
        cache.save_org_report_snapshot({"generated_at": "2026-03-01T00:00:00Z", "note": "not a snapshot"})


def test_save_org_report_snapshot_same_timestamp_creates_unique_files(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    report_a = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "org@test.example",
        "summary": {"data_views_total": 2, "total_unique_components": 5},
    }
    report_b = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "org@test.example",
        "summary": {"data_views_total": 3, "total_unique_components": 7},
    }

    path_a = cache.save_org_report_snapshot(report_a)
    path_b = cache.save_org_report_snapshot(report_b)

    assert path_a != path_b
    assert path_a.exists()
    assert path_b.exists()
    assert len(list(cache.get_org_report_snapshot_dir("org@test.example").glob("*.json"))) == 2


def test_list_org_report_snapshots_returns_newest_first(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    root = cache.get_org_report_snapshot_dir("org@test.example")
    root.mkdir(parents=True, exist_ok=True)
    (root / "older.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-02-01T00:00:00Z",
                "org_id": "org@test.example",
                "summary": {"data_views_total": 1, "total_unique_components": 2},
                "distribution": {"core": {"total": 1}, "isolated": {"total": 1}},
            }
        ),
        encoding="utf-8",
    )
    (root / "newer.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-03-01T00:00:00Z",
                "org_id": "org@test.example",
                "summary": {"data_views_total": 3, "total_unique_components": 9},
                "distribution": {"core": {"total": 5}, "isolated": {"total": 4}},
            }
        ),
        encoding="utf-8",
    )

    snapshots = cache.list_org_report_snapshots("org@test.example")

    assert [Path(snapshot["filepath"]).name for snapshot in snapshots] == ["newer.json", "older.json"]
    assert snapshots[0]["data_views_total"] == 3


def test_list_org_report_snapshots_places_undated_entries_last(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    root = cache.get_org_report_snapshot_dir("org@test.example")
    root.mkdir(parents=True, exist_ok=True)
    (root / "dated.json").write_text(
        json.dumps(
            {
                "generated_at": "2026-03-01T00:00:00Z",
                "org_id": "org@test.example",
                "summary": {"data_views_total": 3, "total_unique_components": 9},
                "distribution": {"core": {"total": 5}, "isolated": {"total": 4}},
            }
        ),
        encoding="utf-8",
    )
    (root / "undated.json").write_text(
        json.dumps(
            {
                "generated_at": "not-a-timestamp",
                "org_id": "org@test.example",
                "summary": {"data_views_total": 1, "total_unique_components": 2},
                "distribution": {"core": {"total": 1}, "isolated": {"total": 1}},
            }
        ),
        encoding="utf-8",
    )

    snapshots = cache.list_org_report_snapshots("org@test.example")

    assert [Path(snapshot["filepath"]).name for snapshot in snapshots] == ["dated.json", "undated.json"]


def test_inspect_org_report_snapshot_includes_data_view_preview(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    snapshot_path = cache.get_org_report_snapshot_dir("org@test.example") / "report.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-03-01T00:00:00Z",
                "org_id": "org@test.example",
                "summary": {"data_views_total": 2, "total_unique_components": 4},
                "distribution": {"core": {"total": 2}, "isolated": {"total": 2}},
                "data_views": [
                    {"data_view_id": "dv_1", "data_view_name": "Orders"},
                    {"data_view_id": "dv_2", "data_view_name": "Visitors"},
                ],
            }
        ),
        encoding="utf-8",
    )

    snapshot = cache.inspect_org_report_snapshot(snapshot_path)

    assert snapshot["data_view_names_preview"] == ["Orders", "Visitors"]
    assert snapshot["data_view_names_total"] == 2


def test_inspect_org_report_snapshot_marks_legacy_payload_without_fidelity_as_ineligible(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    snapshot_path = cache.get_org_report_snapshot_dir("org@test.example") / "legacy.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-03-01T00:00:00Z",
                "org_id": "org@test.example",
                "summary": {"data_views_total": 2, "total_unique_components": 4},
                "distribution": {"core": {"total": 2}, "isolated": {"total": 2}},
                "similarity_pairs": [],
            }
        ),
        encoding="utf-8",
    )

    snapshot = cache.inspect_org_report_snapshot(snapshot_path)

    assert snapshot["history_eligible"] is False
    assert snapshot["history_exclusion_reason"] == "legacy_missing_fidelity_markers"


def test_snapshot_maintenance_skips_non_snapshot_json_objects(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    snapshot_dir = cache.get_org_report_snapshot_dir("org@test.example")
    snapshot_dir.mkdir(parents=True, exist_ok=True)

    bogus_path = snapshot_dir / "bogus.json"
    bogus_path.write_text(
        json.dumps({"generated_at": "2026-02-01T00:00:00Z", "note": "not an org-report snapshot"}),
        encoding="utf-8",
    )
    valid_path = snapshot_dir / "valid.json"
    valid_path.write_text(
        json.dumps(
            _full_fidelity_snapshot(
                {
                    "generated_at": "2026-03-01T00:00:00Z",
                    "org_id": "org@test.example",
                    "summary": {"data_views_total": 1, "total_unique_components": 2},
                    "distribution": {"core": {"total": 1}, "isolated": {"total": 1}},
                }
            )
        ),
        encoding="utf-8",
    )

    snapshots = cache.list_org_report_snapshots("org@test.example")

    assert [Path(snapshot["filepath"]).name for snapshot in snapshots] == ["valid.json"]
    with pytest.raises(ValueError, match="Invalid org-report snapshot"):
        cache.inspect_org_report_snapshot(bogus_path)

    deleted = cache.prune_org_report_snapshots(org_id="org@test.example", keep_last=1)

    assert deleted == []
    assert bogus_path.exists()
    assert valid_path.exists()


def test_load_org_report_snapshot_metadata_normalizes_malformed_sections(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    snapshot_path = cache.get_org_report_snapshot_dir("org@test.example") / "report.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-03-01T00:00:00Z",
                "org_id": "org@test.example",
                "summary": [],
                "distribution": {"core": [], "isolated": []},
                "_snapshot_meta": "bad-meta",
                "data_views": [{"name": f"DV {index}"} for index in range(12)],
            }
        ),
        encoding="utf-8",
    )

    metadata = cache._load_org_report_snapshot_metadata(snapshot_path, include_data_views=True)

    assert metadata is not None
    assert metadata["data_views_total"] == 12
    assert metadata["core_count"] == 0
    assert metadata["isolated_count"] == 0
    assert metadata["snapshot_id"] is None
    assert metadata["data_view_names_total"] == 12
    assert metadata["data_view_names_truncated"] is True


def test_load_org_report_snapshot_metadata_preserves_reported_and_analyzed_counts(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    snapshot_path = cache.get_org_report_snapshot_dir("org@test.example") / "report.json"
    snapshot_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-03-01T00:00:00Z",
                "org_id": "org@test.example",
                "summary": {
                    "data_views_total": 5,
                    "data_views_analyzed": 3,
                    "data_views_failed": 2,
                    "total_unique_components": 8,
                },
                "distribution": {"core": {"total": 5}, "isolated": {"total": 3}},
                "data_views": [
                    {"data_view_id": "dv_1", "data_view_name": "One"},
                    {"data_view_id": "dv_2", "data_view_name": "Two"},
                    {"data_view_id": "dv_3", "data_view_name": "Three"},
                    {"data_view_id": "dv_4", "data_view_name": "Four", "error": "timeout"},
                    {"data_view_id": "dv_5", "data_view_name": "Five", "error": "forbidden"},
                ],
            }
        ),
        encoding="utf-8",
    )

    metadata = cache._load_org_report_snapshot_metadata(snapshot_path, include_data_views=True)

    assert metadata is not None
    assert metadata["data_views_total"] == 5
    assert metadata["data_views_analyzed"] == 3
    assert metadata["data_views_failed"] == 2
    assert metadata["data_views_total_reported"] == 5
    assert metadata["data_view_names_total"] == 5


def test_should_retain_snapshot_uses_normalized_preserved_paths_and_cutoff(tmp_path: Path):
    preserved_path = tmp_path / "snap.json"
    preserved_path.write_text("{}", encoding="utf-8")
    snapshot = {
        "filepath": os.path.relpath(preserved_path, Path.cwd()),
        "generated_at_epoch": datetime.now(UTC).timestamp(),
    }

    assert OrgReportCache._should_retain_snapshot(
        snapshot,
        retained_paths={str(preserved_path.resolve(strict=False))},
        cutoff=None,
    )
    assert OrgReportCache._should_retain_snapshot(
        snapshot,
        retained_paths=set(),
        cutoff=datetime.now(UTC) - timedelta(days=1),
    )


def test_prune_org_report_snapshots_keeps_latest_per_org(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    for month in ("01", "02", "03"):
        cache.save_org_report_snapshot(
            _full_fidelity_snapshot(
                {
                    "generated_at": f"2026-{month}-01T00:00:00Z",
                    "org_id": "org@test.example",
                    "summary": {"data_views_total": 1, "total_unique_components": 1},
                }
            )
        )

    deleted = cache.prune_org_report_snapshots(org_id="org@test.example", keep_last=2)
    remaining = cache.list_org_report_snapshots("org@test.example")

    assert len(deleted) == 1
    assert len(remaining) == 2
    assert [snapshot["generated_at"] for snapshot in remaining] == ["2026-03-01T00:00:00Z", "2026-02-01T00:00:00Z"]


def test_prune_org_report_snapshots_removes_redundant_legacy_duplicates_and_keeps_preferred_copy(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    older_path = cache.save_org_report_snapshot(
        _full_fidelity_snapshot(
            {
                "generated_at": "2026-01-01T00:00:00Z",
                "org_id": "org@test.example",
                "summary": {"data_views_total": 1, "total_unique_components": 1},
            }
        )
    )
    current_path = cache.save_org_report_snapshot(
        _full_fidelity_snapshot(
            {
                "generated_at": "2026-02-01T00:00:00Z",
                "org_id": "org@test.example",
                "summary": {"data_views_total": 1, "total_unique_components": 1},
            }
        )
    )
    legacy_dir = cache.get_org_report_snapshot_root_dir() / "org_test_example"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy_copy = legacy_dir / current_path.name
    legacy_copy.write_text(current_path.read_text(encoding="utf-8"), encoding="utf-8")

    deleted = cache.prune_org_report_snapshots(org_id="org@test.example", keep_last=1)
    remaining = cache.list_org_report_snapshots("org@test.example")

    assert set(deleted) == {
        str(older_path.resolve(strict=False)),
        str(legacy_copy.resolve(strict=False)),
    }
    assert current_path.exists()
    assert not legacy_copy.exists()
    assert [snapshot["filepath"] for snapshot in remaining] == [str(current_path.resolve(strict=False))]


def test_prune_org_report_snapshots_prefers_dated_entries_over_undated_ones(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    root = cache.get_org_report_snapshot_dir("org@test.example")
    root.mkdir(parents=True, exist_ok=True)
    for name, timestamp in (
        ("older.json", "2026-02-01T00:00:00Z"),
        ("newer.json", "2026-03-01T00:00:00Z"),
        ("undated.json", "not-a-timestamp"),
    ):
        (root / name).write_text(
            json.dumps(
                _full_fidelity_snapshot(
                    {
                        "generated_at": timestamp,
                        "org_id": "org@test.example",
                        "summary": {"data_views_total": 1, "total_unique_components": 1},
                        "distribution": {"core": {"total": 1}, "isolated": {"total": 0}},
                    }
                )
            ),
            encoding="utf-8",
        )

    deleted = cache.prune_org_report_snapshots(org_id="org@test.example", keep_last=2)
    remaining = cache.list_org_report_snapshots("org@test.example")

    assert [Path(path).name for path in deleted] == ["undated.json"]
    assert [Path(snapshot["filepath"]).name for snapshot in remaining] == ["newer.json", "older.json"]


def test_prune_org_report_snapshots_keeps_entries_matching_either_retention_rule(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    root = cache.get_org_report_snapshot_dir("org@test.example")
    root.mkdir(parents=True, exist_ok=True)

    now = datetime.now(UTC)
    for name, timestamp in (
        ("newest.json", now.isoformat()),
        ("recent.json", (now - timedelta(days=5)).isoformat()),
        ("old.json", (now - timedelta(days=45)).isoformat()),
    ):
        (root / name).write_text(
            json.dumps(
                _full_fidelity_snapshot(
                    {
                        "generated_at": timestamp,
                        "org_id": "org@test.example",
                        "summary": {"data_views_total": 1, "total_unique_components": 1},
                        "distribution": {"core": {"total": 1}, "isolated": {"total": 0}},
                    }
                )
            ),
            encoding="utf-8",
        )

    deleted = cache.prune_org_report_snapshots(org_id="org@test.example", keep_last=1, keep_since_days=30)
    remaining = cache.list_org_report_snapshots("org@test.example")

    assert [Path(path).name for path in deleted] == ["old.json"]
    assert [Path(snapshot["filepath"]).name for snapshot in remaining] == ["newest.json", "recent.json"]


def test_prune_org_report_snapshots_preserves_explicit_paths(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    retained = cache.save_org_report_snapshot(
        _full_fidelity_snapshot(
            {
                "generated_at": "2026-01-01T00:00:00Z",
                "org_id": "org@test.example",
                "summary": {"data_views_total": 1, "total_unique_components": 1},
            }
        )
    )
    middle = cache.save_org_report_snapshot(
        _full_fidelity_snapshot(
            {
                "generated_at": "2026-02-01T00:00:00Z",
                "org_id": "org@test.example",
                "summary": {"data_views_total": 1, "total_unique_components": 1},
            }
        )
    )
    newest = cache.save_org_report_snapshot(
        _full_fidelity_snapshot(
            {
                "generated_at": "2026-03-01T00:00:00Z",
                "org_id": "org@test.example",
                "summary": {"data_views_total": 1, "total_unique_components": 1},
            }
        )
    )

    deleted = cache.prune_org_report_snapshots(
        org_id="org@test.example",
        keep_last=1,
        preserved_snapshot_paths=[retained],
    )
    remaining = cache.list_org_report_snapshots("org@test.example")

    assert [Path(path).name for path in deleted] == [middle.name]
    assert [Path(snapshot["filepath"]).name for snapshot in remaining] == [newest.name, retained.name]


def test_prune_org_report_snapshots_keep_last_keeps_newest_by_recency_even_when_ineligible(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    eligible_old = cache.save_org_report_snapshot(
        {
            "generated_at": "2026-01-01T00:00:00Z",
            "org_id": "org@test.example",
            "summary": {
                "data_views_total": 2,
                "data_views_analyzed": 2,
                "similarity_analysis_complete": True,
                "total_unique_components": 5,
            },
            "distribution": {"core": {"total": 2}, "isolated": {"total": 3}},
            "similarity_pairs": [],
        }
    )
    ineligible_new = cache.save_org_report_snapshot(
        {
            "generated_at": "2026-02-01T00:00:00Z",
            "org_id": "org@test.example",
            "summary": {
                "data_views_total": 2,
                "data_views_analyzed": 2,
                "similarity_analysis_complete": False,
                "similarity_analysis_mode": "org_stats_only",
                "total_unique_components": 5,
            },
            "distribution": {"core": {"total": 2}, "isolated": {"total": 3}},
            "similarity_pairs": [],
        }
    )
    eligible_new = cache.save_org_report_snapshot(
        {
            "generated_at": "2026-03-01T00:00:00Z",
            "org_id": "org@test.example",
            "summary": {
                "data_views_total": 2,
                "data_views_analyzed": 2,
                "similarity_analysis_complete": True,
                "total_unique_components": 5,
            },
            "distribution": {"core": {"total": 2}, "isolated": {"total": 3}},
            "similarity_pairs": [],
        }
    )

    deleted = cache.prune_org_report_snapshots(org_id="org@test.example", keep_last=2)
    remaining = cache.list_org_report_snapshots("org@test.example")

    assert deleted == [str(eligible_old.resolve(strict=False))]
    assert [Path(snapshot["filepath"]).name for snapshot in remaining] == [eligible_new.name, ineligible_new.name]


def test_prune_org_report_snapshots_keep_last_keeps_recent_markerless_cached_snapshots(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    eligible_old = cache.save_org_report_snapshot(
        _full_fidelity_snapshot(
            {
                "generated_at": "2026-01-01T00:00:00Z",
                "org_id": "org@test.example",
                "summary": {"data_views_total": 2, "total_unique_components": 5},
                "distribution": {"core": {"total": 2}, "isolated": {"total": 3}},
            }
        )
    )

    legacy_cached = cache.get_org_report_snapshot_dir("org@test.example") / "legacy_cached.json"
    legacy_cached.write_text(
        json.dumps(
            {
                "generated_at": "2026-02-01T00:00:00Z",
                "org_id": "org@test.example",
                "_snapshot_meta": {
                    "snapshot_id": "persisted-123",
                    "history_eligible": True,
                    "history_exclusion_reason": None,
                },
                "summary": {"data_views_total": 2, "total_unique_components": 5},
                "distribution": {"core": {"total": 2}, "isolated": {"total": 3}},
                "data_views": [],
                "component_index": {},
                "similarity_pairs": [],
            }
        ),
        encoding="utf-8",
    )

    eligible_new = cache.save_org_report_snapshot(
        _full_fidelity_snapshot(
            {
                "generated_at": "2026-03-01T00:00:00Z",
                "org_id": "org@test.example",
                "summary": {"data_views_total": 2, "total_unique_components": 5},
                "distribution": {"core": {"total": 2}, "isolated": {"total": 3}},
            }
        )
    )

    deleted = cache.prune_org_report_snapshots(org_id="org@test.example", keep_last=2)
    remaining = cache.list_org_report_snapshots("org@test.example")

    assert deleted == [str(eligible_old.resolve(strict=False))]
    assert [Path(snapshot["filepath"]).name for snapshot in remaining] == [eligible_new.name, legacy_cached.name]
    assert remaining[1]["history_eligible"] is False
    assert remaining[1]["history_exclusion_reason"] == "legacy_missing_fidelity_markers"


def test_lock_property_and_health_delegate_to_manager(tmp_path: Path):
    lock = OrgReportLock("org@test", lock_dir=tmp_path)
    manager = Mock()
    manager.lock_lost = True
    manager.read_info.return_value = {"pid": 1234}
    lock._manager = manager

    assert lock.lock_lost is True
    assert lock.get_lock_info() == {"pid": 1234}
    lock.ensure_healthy()
    manager.ensure_held.assert_called_once()


def test_is_process_running_covers_os_kill_branches():
    with patch("cja_auto_sdr.org.cache.os.kill", return_value=None):
        assert OrgReportLock._is_process_running(123) is True

    with patch("cja_auto_sdr.org.cache.os.kill", side_effect=ProcessLookupError):
        assert OrgReportLock._is_process_running(123) is False

    with patch("cja_auto_sdr.org.cache.os.kill", side_effect=OSError(errno.EPERM, "permission")):
        assert OrgReportLock._is_process_running(123) is True

    with patch("cja_auto_sdr.org.cache.os.kill", side_effect=OSError(errno.ESRCH, "missing")):
        assert OrgReportLock._is_process_running(123) is False


def test_is_process_running_handles_int_conversion_failures():
    class OverflowInt:
        def __int__(self):
            raise OverflowError

    assert OrgReportLock._is_process_running("not-a-pid") is False
    assert OrgReportLock._is_process_running(OverflowInt()) is False


# ---------------------------------------------------------------------------
# Edge-case coverage for previously uncovered lines
# ---------------------------------------------------------------------------


def test_retained_keep_last_paths_returns_empty_set_when_keep_last_is_zero(tmp_path: Path):
    """L268: _retained_keep_last_paths returns set() when keep_last <= 0."""
    cache = OrgReportCache(cache_dir=tmp_path)
    result = cache._retained_keep_last_paths(
        [{"filepath": str(tmp_path / "snap.json"), "generated_at_epoch": 1000}],
        keep_last=0,
    )
    assert result == set()


def test_retained_keep_last_paths_returns_empty_set_when_keep_last_is_negative(tmp_path: Path):
    """L268: _retained_keep_last_paths returns set() when keep_last < 0."""
    cache = OrgReportCache(cache_dir=tmp_path)
    result = cache._retained_keep_last_paths(
        [{"filepath": str(tmp_path / "snap.json"), "generated_at_epoch": 1000}],
        keep_last=-1,
    )
    assert result == set()


def test_should_retain_snapshot_returns_false_when_generated_at_epoch_missing():
    """L292-293: _should_retain_snapshot returns False when snapshot has no generated_at_epoch."""
    snapshot = {"filepath": "/some/path.json"}  # no generated_at_epoch key
    cutoff = datetime.now(UTC) - timedelta(days=1)
    result = OrgReportCache._should_retain_snapshot(
        snapshot,
        retained_paths=set(),
        cutoff=cutoff,
    )
    assert result is False


def test_load_org_report_snapshot_metadata_returns_none_on_os_error(tmp_path: Path):
    """L307-309: OSError during file open → log warning, return None."""
    cache = OrgReportCache(cache_dir=tmp_path)
    logger = Mock()
    cache.logger = logger

    missing_path = tmp_path / "nonexistent.json"

    result = cache._load_org_report_snapshot_metadata(missing_path)

    assert result is None
    logger.warning.assert_called_once()
    warning_msg = logger.warning.call_args[0][0]
    assert "Skipping org-report snapshot" in warning_msg


def test_load_org_report_snapshot_metadata_returns_none_on_json_decode_error(tmp_path: Path):
    """L307-309: JSONDecodeError during parse → log warning, return None."""
    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{not valid json", encoding="utf-8")

    logger = Mock()
    cache = OrgReportCache(cache_dir=tmp_path, logger=logger)
    # Reset call count from __init__ load
    logger.reset_mock()

    result = cache._load_org_report_snapshot_metadata(bad_json)

    assert result is None
    logger.warning.assert_called_once()


def test_load_org_report_snapshot_metadata_returns_none_for_non_dict_payload(tmp_path: Path):
    """L311-313: JSON array (not dict) → log warning, return None."""
    array_json = tmp_path / "array.json"
    array_json.write_text("[1, 2, 3]", encoding="utf-8")

    logger = Mock()
    cache = OrgReportCache(cache_dir=tmp_path, logger=logger)
    logger.reset_mock()

    result = cache._load_org_report_snapshot_metadata(array_json)

    assert result is None
    logger.warning.assert_called_once()
    # call_args[0] is (fmt, path, ...) — "expected JSON object" appears in the format string
    assert "expected JSON object" in logger.warning.call_args[0][0]


def test_prune_org_report_snapshots_returns_empty_list_when_no_retention_policy(tmp_path: Path):
    """L401: keep_last <= 0 AND keep_since_days is None → return [] immediately."""
    cache = OrgReportCache(cache_dir=tmp_path)
    cache.save_org_report_snapshot(
        _full_fidelity_snapshot(
            {
                "generated_at": "2026-03-01T00:00:00Z",
                "org_id": "org@test.example",
                "summary": {"data_views_total": 1, "total_unique_components": 1},
            }
        )
    )

    # Both default (keep_last=0, keep_since_days=None) → early return
    result = cache.prune_org_report_snapshots()
    assert result == []


def test_prune_org_report_snapshots_skips_empty_duplicate_paths_group(tmp_path: Path):
    """L440: duplicate_paths is empty → continue (snapshot without filepath is skipped)."""
    cache = OrgReportCache(cache_dir=tmp_path)

    # Save a real snapshot so pruning has something to work with
    cache.save_org_report_snapshot(
        _full_fidelity_snapshot(
            {
                "generated_at": "2026-01-01T00:00:00Z",
                "org_id": "org@test.example",
                "summary": {"data_views_total": 1, "total_unique_components": 1},
            }
        )
    )
    cache.save_org_report_snapshot(
        _full_fidelity_snapshot(
            {
                "generated_at": "2026-02-01T00:00:00Z",
                "org_id": "org@test.example",
                "summary": {"data_views_total": 1, "total_unique_components": 1},
            }
        )
    )

    snapshots = cache._load_org_report_snapshots(org_id="org@test.example")

    # Inject a snapshot entry with no filepath so duplicate_paths becomes empty
    snapshots.append(
        {
            "org_id": "org@test.example",
            "generated_at": "2026-03-01T00:00:00Z",
            "generated_at_epoch": 1_000_000,
            # intentionally no 'filepath' key
        }
    )

    with patch.object(cache, "_load_org_report_snapshots", return_value=snapshots):
        deleted = cache.prune_org_report_snapshots(org_id="org@test.example", keep_last=1)

    # The filepath-less snapshot is silently skipped; only real snapshots are pruned
    assert isinstance(deleted, list)
