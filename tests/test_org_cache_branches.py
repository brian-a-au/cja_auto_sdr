"""Focused branch coverage for org cache and lock helper logic."""

from __future__ import annotations

import errno
import json
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


def test_save_org_report_snapshot_writes_json_file(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    report = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "org@test.example",
        "summary": {"data_views_total": 2, "total_unique_components": 5},
    }

    path = cache.save_org_report_snapshot(report)

    assert path.exists()
    assert path.parent == cache.get_org_report_snapshot_dir("org@test.example")
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["org_id"] == "org@test.example"
    assert payload["_snapshot_meta"]["snapshot_id"]
    assert payload["_snapshot_meta"]["content_hash"]


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


def test_prune_org_report_snapshots_keeps_latest_per_org(tmp_path: Path):
    cache = OrgReportCache(cache_dir=tmp_path)
    for month in ("01", "02", "03"):
        cache.save_org_report_snapshot(
            {
                "generated_at": f"2026-{month}-01T00:00:00Z",
                "org_id": "org@test.example",
                "summary": {"data_views_total": 1, "total_unique_components": 1},
            }
        )

    deleted = cache.prune_org_report_snapshots(org_id="org@test.example", keep_last=2)
    remaining = cache.list_org_report_snapshots("org@test.example")

    assert len(deleted) == 1
    assert len(remaining) == 2
    assert [snapshot["generated_at"] for snapshot in remaining] == ["2026-03-01T00:00:00Z", "2026-02-01T00:00:00Z"]


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
                {
                    "generated_at": timestamp,
                    "org_id": "org@test.example",
                    "summary": {"data_views_total": 1, "total_unique_components": 1},
                    "distribution": {"core": {"total": 1}, "isolated": {"total": 0}},
                }
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
                {
                    "generated_at": timestamp,
                    "org_id": "org@test.example",
                    "summary": {"data_views_total": 1, "total_unique_components": 1},
                    "distribution": {"core": {"total": 1}, "isolated": {"total": 0}},
                }
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
        {
            "generated_at": "2026-01-01T00:00:00Z",
            "org_id": "org@test.example",
            "summary": {"data_views_total": 1, "total_unique_components": 1},
        }
    )
    middle = cache.save_org_report_snapshot(
        {
            "generated_at": "2026-02-01T00:00:00Z",
            "org_id": "org@test.example",
            "summary": {"data_views_total": 1, "total_unique_components": 1},
        }
    )
    newest = cache.save_org_report_snapshot(
        {
            "generated_at": "2026-03-01T00:00:00Z",
            "org_id": "org@test.example",
            "summary": {"data_views_total": 1, "total_unique_components": 1},
        }
    )

    deleted = cache.prune_org_report_snapshots(
        org_id="org@test.example",
        keep_last=1,
        preserved_snapshot_paths=[retained],
    )
    remaining = cache.list_org_report_snapshots("org@test.example")

    assert [Path(path).name for path in deleted] == [middle.name]
    assert [Path(snapshot["filepath"]).name for snapshot in remaining] == [newest.name, retained.name]


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
