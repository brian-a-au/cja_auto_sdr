"""Parse-cache coverage for SnapshotManager.list_snapshots (diff retention passes).

Verifies list_snapshots routes per-file JSON parsing through the shared
core.json_io.load_json_cached helper, so repeated retention passes over the
same snapshot directory (e.g. apply_retention_policy -> list_snapshots,
apply_date_retention_policy -> list_snapshots) do not re-parse unchanged
files from disk.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta

import pytest

from cja_auto_sdr.core import json_io
from cja_auto_sdr.diff.models import DataViewSnapshot
from cja_auto_sdr.diff.snapshot import SnapshotManager


def test_snapshot_discovery_refreshes_identity_after_timestamp_preserving_replacement(tmp_path):
    mgr = SnapshotManager()
    path = tmp_path / "snapshot.json"
    replacement = tmp_path / "replacement.json"
    snapshot = DataViewSnapshot(data_view_id="dv_old", data_view_name="View")
    mgr.save_snapshot(snapshot, str(path))
    assert mgr.get_most_recent_snapshot(str(tmp_path), "dv_old") == str(path)
    before = path.stat()

    snapshot.data_view_id = "dv_new"
    mgr.save_snapshot(snapshot, str(replacement))
    os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
    os.replace(replacement, path)
    assert path.stat().st_size == before.st_size

    assert mgr.get_most_recent_snapshot(str(tmp_path), "dv_old") is None
    assert mgr.get_most_recent_snapshot(str(tmp_path), "dv_new") == str(path)


def test_list_snapshots_parse_is_cached(tmp_path, monkeypatch):
    """Each snapshot file is parsed at most once across two list_snapshots calls."""
    mgr = SnapshotManager()  # constructor takes only an optional logger

    # Write 2 valid snapshot files via the real snapshot-writing helper for
    # schema fidelity (matches what create_snapshot/save_snapshot produce).
    snapshot_a = DataViewSnapshot(
        data_view_id="dv_a",
        data_view_name="View A",
        owner="owner@test.com",
        description="desc a",
        metrics=[{"id": "m1", "name": "Metric 1"}],
        dimensions=[{"id": "d1", "name": "Dim 1"}],
    )
    snapshot_b = DataViewSnapshot(
        data_view_id="dv_b",
        data_view_name="View B",
        owner="owner@test.com",
        description="desc b",
        metrics=[{"id": "m2", "name": "Metric 2"}],
        dimensions=[{"id": "d2", "name": "Dim 2"}],
    )
    mgr.save_snapshot(snapshot_a, str(tmp_path / "a.json"))
    mgr.save_snapshot(snapshot_b, str(tmp_path / "b.json"))

    json_io.load_json_cached.cache_clear()
    calls = {}
    real_open = open

    def counting_open(file, *a, **k):
        calls[str(file)] = calls.get(str(file), 0) + 1
        return real_open(file, *a, **k)

    monkeypatch.setattr("builtins.open", counting_open)

    mgr.list_snapshots(str(tmp_path))
    mgr.list_snapshots(str(tmp_path))

    assert calls, "expected the counting_open shim to observe at least one open() call"
    assert all(v == 1 for k, v in calls.items() if k.endswith(".json"))


@pytest.fixture(params=["invalid_utf8", "integer_limit"])
def malformed_snapshot_bytes(request):
    if request.param == "invalid_utf8":
        yield b'{"snapshot_version": "1.0", "bad": "\xff"}'
        return

    previous_limit = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(4300)
    try:
        yield b'{"snapshot_version": "1.0", "bad": ' + b"9" * 5000 + b"}"
    finally:
        sys.set_int_max_str_digits(previous_limit)


def _write_healthy_diff_history(manager, tmp_path):
    now = datetime.now(UTC)
    for name, age in [("old", 60), ("new", 1)]:
        manager.save_snapshot(
            DataViewSnapshot(
                data_view_id="dv_test",
                data_view_name="View",
                created_at=(now - timedelta(days=age)).isoformat(),
            ),
            str(tmp_path / f"{name}.json"),
        )


def test_snapshot_discovery_skips_decoding_failures(tmp_path, malformed_snapshot_bytes):
    manager = SnapshotManager()
    _write_healthy_diff_history(manager, tmp_path)
    (tmp_path / "bad.json").write_bytes(malformed_snapshot_bytes)

    assert [item["filename"] for item in manager.list_snapshots(str(tmp_path))] == ["new.json", "old.json"]
    assert manager.get_most_recent_snapshot(str(tmp_path), "dv_test") == str(tmp_path / "new.json")


@pytest.mark.parametrize("policy", ["count", "date"])
def test_snapshot_retention_preserves_undecodable_files(tmp_path, malformed_snapshot_bytes, policy):
    manager = SnapshotManager()
    _write_healthy_diff_history(manager, tmp_path)
    malformed_path = tmp_path / "bad.json"
    malformed_path.write_bytes(malformed_snapshot_bytes)

    if policy == "count":
        deleted = manager.apply_retention_policy(str(tmp_path), "dv_test", keep_last=1)
    else:
        deleted = manager.apply_date_retention_policy(str(tmp_path), "dv_test", keep_since_days=30)

    assert deleted == [str(tmp_path / "old.json")]
    assert not (tmp_path / "old.json").exists()
    assert (tmp_path / "new.json").exists()
    assert malformed_path.read_bytes() == malformed_snapshot_bytes


def test_snapshot_discovery_with_only_decoding_failures_returns_empty(tmp_path, malformed_snapshot_bytes):
    manager = SnapshotManager()
    (tmp_path / "bad.json").write_bytes(malformed_snapshot_bytes)

    assert manager.list_snapshots(str(tmp_path)) == []
    assert manager.get_most_recent_snapshot(str(tmp_path), "dv_test") is None


def test_explicit_snapshot_and_shared_loader_keep_decoding_errors(tmp_path, malformed_snapshot_bytes):
    path = tmp_path / "bad.json"
    path.write_bytes(malformed_snapshot_bytes)

    with pytest.raises(ValueError):
        SnapshotManager().load_snapshot(str(path))
    with pytest.raises(ValueError):
        json_io.load_json_cached(path)


@pytest.mark.parametrize("field", ["metrics", "dimensions", "calculated_metrics_inventory", "segments_inventory"])
@pytest.mark.parametrize("rows", [[None], [{"id": 1}], [{"id": -1}], [{"id": 1.5}], [{"id": True}]])
def test_malformed_newer_snapshot_cannot_replace_or_delete_healthy_baseline(tmp_path, field, rows):
    import json

    if field in ("calculated_metrics_inventory", "segments_inventory"):
        id_field = "metric_id" if field == "calculated_metrics_inventory" else "segment_id"
        rows = [{id_field: row["id"]} if isinstance(row, dict) else row for row in rows]
    manager = SnapshotManager()
    healthy = tmp_path / "healthy.json"
    bad = tmp_path / "bad.json"
    manager.save_snapshot(
        DataViewSnapshot(data_view_id="dv_test", data_view_name="View", created_at="2026-01-01T00:00:00Z"), str(healthy)
    )
    payload = {
        "snapshot_version": "1.0",
        "data_view_id": "dv_test",
        "created_at": "2026-02-01T00:00:00Z",
        field: rows,
    }
    bad_content = json.dumps(payload)
    bad.write_text(bad_content)
    assert manager.apply_retention_policy(str(tmp_path), "dv_test", keep_last=1) == []
    assert manager.get_most_recent_snapshot(str(tmp_path), "dv_test") == str(healthy)
    assert healthy.exists() and bad.read_text() == bad_content


@pytest.mark.parametrize("timestamp", ["0001-01-01T00:00:00+01:00", "9999-12-31T23:59:59-01:00"])
def test_timestamp_conversion_overflow_is_ineligible_for_diff_history(tmp_path, timestamp):
    import json

    manager = SnapshotManager()
    _write_healthy_diff_history(manager, tmp_path)
    bad = tmp_path / "overflow.json"
    bad.write_text(json.dumps({"snapshot_version": "1.0", "data_view_id": "dv_test", "created_at": timestamp}))
    assert [item["filename"] for item in manager.list_snapshots(str(tmp_path))] == ["new.json", "old.json"]
    assert manager.apply_retention_policy(str(tmp_path), "dv_test", keep_last=1) == [str(tmp_path / "old.json")]
    assert manager.apply_date_retention_policy(str(tmp_path), "dv_test", keep_since_days=30) == []
    assert bad.exists()
    with pytest.raises(ValueError, match="timestamp"):
        manager.load_snapshot(str(bad))


@pytest.mark.parametrize("field", ["metrics", "dimensions", "calculated_metrics_inventory", "segments_inventory"])
@pytest.mark.parametrize(
    "rows",
    [
        42,
        [None],
        ["row"],
        [{"id": [1]}],
        [{"id": {"key": 1}}],
        [{"id": "m"}, {"id": 1}],
        [{"id": 1}],
        [{"id": -1}],
        [{"id": 1.5}],
        [{"id": True}],
    ],
)
def test_unusable_consumed_rows_are_excluded_from_history(tmp_path, field, rows):
    import json

    if field in ("calculated_metrics_inventory", "segments_inventory") and isinstance(rows, list):
        id_field = "metric_id" if field == "calculated_metrics_inventory" else "segment_id"
        rows = [{id_field: row["id"]} if isinstance(row, dict) and "id" in row else row for row in rows]
    manager = SnapshotManager()
    _write_healthy_diff_history(manager, tmp_path)
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps(
            {"snapshot_version": "1.0", "data_view_id": "dv_test", "created_at": "2000-01-01T00:00:00Z", field: rows}
        )
    )
    with pytest.raises(ValueError, match=field):
        manager.load_snapshot(str(bad))
    assert [s["filename"] for s in manager.list_snapshots(str(tmp_path))] == ["new.json", "old.json"]
    assert manager.get_most_recent_snapshot(str(tmp_path), "dv_test") == str(tmp_path / "new.json")
    assert manager.apply_date_retention_policy(str(tmp_path), "dv_test", keep_since_days=30) == [
        str(tmp_path / "old.json")
    ]
    assert bad.exists()


@pytest.mark.parametrize("timestamp", [None, "", "   ", "not-an-iso-time"])
def test_ordinary_missing_or_malformed_diff_timestamp_keeps_mtime_policy(tmp_path, timestamp):
    import json

    manager = SnapshotManager()
    path = tmp_path / "legacy.json"
    path.write_text(json.dumps({"snapshot_version": "1.0", "data_view_id": "dv_test", "created_at": timestamp}))
    old_epoch = (datetime.now(UTC) - timedelta(days=60)).timestamp()
    os.utime(path, (old_epoch, old_epoch))
    assert manager.get_most_recent_snapshot(str(tmp_path), "dv_test") == str(path)
    assert manager.apply_date_retention_policy(str(tmp_path), "dv_test", keep_since_days=30) == [str(path)]


def test_validation_preserves_legacy_rows_and_cached_payload(tmp_path):
    import json

    manager = SnapshotManager()
    path = tmp_path / "legacy.json"
    rows = [
        {},
        {"id": None},
        {"id": False},
        {"id": 0},
        {"id": 0.0},
        {"id": ""},
        {"id": []},
        {"id": {}},
        {"id": "m", "name": "first"},
        {"id": "m", "name": "last"},
    ]
    payload = {
        "snapshot_version": "1.0",
        "data_view_id": "dv_test",
        "metrics": rows,
        "metadata": ["unused"],
        "additive": {"any": [1]},
        "segments_inventory": [{"id": "s", "definition_json": "not JSON"}],
    }
    path.write_text(json.dumps(payload))
    cached = json_io.load_json_cached(path)
    assert manager.get_most_recent_snapshot(str(tmp_path), "dv_test") == str(path)
    snapshot = manager.load_snapshot(str(path))
    assert snapshot.metrics == rows and snapshot.dimensions == []
    assert snapshot.calculated_metrics_inventory is None
    assert snapshot.metadata == ["unused"]
    from cja_auto_sdr.diff.comparator import DataViewComparator

    result = DataViewComparator().compare(
        snapshot, DataViewSnapshot(data_view_id="dv_test", metrics=[{"id": "m", "name": "last"}])
    )
    assert result.summary.metrics_modified == 0
    assert cached == payload and json_io.load_json_cached(path) is cached


def test_snapshot_eligibility_refreshes_after_same_size_mtime_replacement(tmp_path):
    import json

    manager = SnapshotManager()
    path = tmp_path / "snapshot.json"
    replacement = tmp_path / "replacement.json"
    valid = {"snapshot_version": "1.0", "data_view_id": "dv_test", "metrics": [{}]}
    invalid = {**valid, "metrics": [None]}
    path.write_text(json.dumps(valid) + "  ")
    cached = json_io.load_json_cached(path)
    assert manager.get_most_recent_snapshot(str(tmp_path), "dv_test") == str(path)
    before = path.stat()
    replacement.write_text(json.dumps(invalid))
    os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
    os.replace(replacement, path)
    assert path.stat().st_size == before.st_size
    assert manager.list_snapshots(str(tmp_path)) == []
    assert cached == valid


def test_from_dict_preserves_missing_version_default():
    snapshot = DataViewSnapshot.from_dict({"data_view_id": "legacy"})
    assert snapshot.snapshot_version == "1.0" and snapshot.metrics == [] and snapshot.dimensions == []
