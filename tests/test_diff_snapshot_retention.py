"""Parse-cache coverage for SnapshotManager.list_snapshots (diff retention passes).

Verifies list_snapshots routes per-file JSON parsing through the shared
core.json_io.load_json_cached helper, so repeated retention passes over the
same snapshot directory (e.g. apply_retention_policy -> list_snapshots,
apply_date_retention_policy -> list_snapshots) do not re-parse unchanged
files from disk.
"""

from __future__ import annotations

from cja_auto_sdr.core import json_io
from cja_auto_sdr.diff.models import DataViewSnapshot
from cja_auto_sdr.diff.snapshot import SnapshotManager


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
