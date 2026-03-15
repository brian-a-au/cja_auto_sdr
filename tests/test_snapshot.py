"""Tests for diff/snapshot.py — SnapshotManager and parse_retention_period.

Targets uncovered lines: 31-32, 41, 45-48, 59, 65-66, 79-85, 105, 116, 123,
147-154, 168-175, 237-238, 271-272, 286, 295, 301, 310-311, 339, 344, 349-356.
"""

import json
import logging
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch
from zoneinfo import ZoneInfo

import pytest

import cja_auto_sdr.core.json_io as json_io

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cja_auto_sdr.diff.models import DataViewSnapshot
from cja_auto_sdr.diff.snapshot import SnapshotManager, parse_retention_period

# ==================== Fixtures ====================


@pytest.fixture
def logger():
    return logging.getLogger("test_snapshot")


@pytest.fixture
def manager(logger):
    return SnapshotManager(logger)


@pytest.fixture
def sample_snapshot():
    return DataViewSnapshot(
        data_view_id="dv_abc",
        data_view_name="Test View",
        owner="owner@test.com",
        description="desc",
        metrics=[{"id": "m1", "name": "Metric 1"}],
        dimensions=[{"id": "d1", "name": "Dim 1"}],
    )


def _write_snapshot_json(filepath, data_view_id="dv_abc", created_at=None, extra=None):
    """Helper to write a snapshot JSON file."""
    data = {
        "snapshot_version": "1.0",
        "data_view_id": data_view_id,
        "data_view_name": "Test",
        "created_at": created_at or datetime.now(UTC).isoformat(),
        "metrics": [],
        "dimensions": [],
    }
    if extra:
        data.update(extra)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(data, f)
    return filepath


# ==================== _default_snapshot_timezone Tests ====================


class TestDefaultSnapshotTimezone:
    """Tests for _default_snapshot_timezone (lines 27-48)."""

    def test_tz_env_valid_returns_zoneinfo(self, manager):
        """Line 30: TZ env has a valid IANA zone name."""
        with patch.dict(os.environ, {"TZ": "US/Eastern"}):
            tz = manager._default_snapshot_timezone()
            assert tz is not None

    def test_tz_env_invalid_falls_through(self, manager):
        """Lines 31-32: TZ env has an invalid zone name — ZoneInfoNotFoundError caught."""
        with patch.dict(os.environ, {"TZ": "Invalid/NotARealZone"}):
            tz = manager._default_snapshot_timezone()
            # Should still return *something* (falls through to later branches)
            assert tz is not None

    def test_localtime_path_does_not_exist(self, manager):
        """Line 41: localtime paths don't exist — continue."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("cja_auto_sdr.diff.snapshot.ZoneInfo") as mock_zi,
        ):
            # Make ZoneInfo("localtime") raise, forcing fallback to file paths
            from zoneinfo import ZoneInfoNotFoundError

            mock_zi.side_effect = ZoneInfoNotFoundError("localtime")
            mock_zi.from_file = MagicMock(return_value=ZoneInfo("UTC"))

            with patch("os.path.exists", return_value=False):
                tz = manager._default_snapshot_timezone()
                assert tz is not None

    def test_localtime_file_oserror(self, manager):
        """Lines 45-46: Reading /etc/localtime raises OSError — continue."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("cja_auto_sdr.diff.snapshot.ZoneInfo") as mock_zi,
        ):
            from zoneinfo import ZoneInfoNotFoundError

            mock_zi.side_effect = ZoneInfoNotFoundError("fail")

            with (
                patch("os.path.exists", return_value=True),
                patch("builtins.open", side_effect=OSError("disk error")),
            ):
                tz = manager._default_snapshot_timezone()
                # Falls through to line 48 — datetime.now().astimezone().tzinfo
                assert tz is not None

    def test_final_fallback_returns_local_tz(self, manager):
        """Line 48: All branches fail — returns datetime.now().astimezone().tzinfo."""
        with (
            patch.dict(os.environ, {}, clear=True),
            patch("cja_auto_sdr.diff.snapshot.ZoneInfo") as mock_zi,
        ):
            from zoneinfo import ZoneInfoNotFoundError

            mock_zi.side_effect = ZoneInfoNotFoundError("fail")

            with patch("os.path.exists", return_value=False):
                tz = manager._default_snapshot_timezone()
                assert tz is not None


# ==================== _parse_snapshot_created_at Tests ====================


class TestParseSnapshotCreatedAt:
    """Tests for _parse_snapshot_created_at (lines 50-71)."""

    def test_none_returns_none(self, manager):
        """Line 59: None input."""
        assert manager._parse_snapshot_created_at(None) is None

    def test_empty_string_returns_none(self, manager):
        """Line 59: Empty string input."""
        assert manager._parse_snapshot_created_at("") is None

    def test_whitespace_only_returns_none(self, manager):
        """Line 59: Whitespace-only string."""
        assert manager._parse_snapshot_created_at("   ") is None

    def test_invalid_date_returns_none(self, manager):
        """Lines 65-66: Unparseable date string."""
        assert manager._parse_snapshot_created_at("not-a-date") is None

    def test_z_suffix_parsed_as_utc(self, manager):
        """Line 61: 'Z' suffix gets converted to +00:00."""
        result = manager._parse_snapshot_created_at("2024-06-15T12:00:00Z")
        assert result is not None
        assert result.tzinfo is not None
        assert result == datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_aware_timestamp_normalized_to_utc(self, manager):
        """Timezone-aware timestamp gets converted to UTC."""
        result = manager._parse_snapshot_created_at("2024-06-15T12:00:00+05:00")
        assert result is not None
        assert result == datetime(2024, 6, 15, 7, 0, 0, tzinfo=UTC)

    def test_naive_timestamp_gets_local_tz_then_utc(self, manager):
        """Lines 68-69: Naive timestamp is assumed local, then converted to UTC."""
        result = manager._parse_snapshot_created_at("2024-06-15T12:00:00")
        assert result is not None
        assert result.tzinfo is not None  # Should be UTC after conversion


# ==================== _snapshot_created_at_utc Tests ====================


class TestSnapshotCreatedAtUtc:
    """Tests for _snapshot_created_at_utc (lines 73-85)."""

    def test_uses_created_at_when_present(self, manager):
        """Normal case — created_at field is parseable."""
        snapshot = {"created_at": "2024-06-15T12:00:00+00:00"}
        result = manager._snapshot_created_at_utc(snapshot)
        assert result == datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_falls_back_to_mtime_when_created_at_empty(self, manager, tmp_path):
        """Lines 79-82: created_at is empty, falls back to file mtime."""
        filepath = str(tmp_path / "snap.json")
        with open(filepath, "w") as f:
            f.write("{}")

        snapshot = {"created_at": "", "filepath": filepath}
        result = manager._snapshot_created_at_utc(snapshot)
        assert result is not None
        assert result.tzinfo is not None

    def test_falls_back_to_mtime_when_created_at_invalid(self, manager, tmp_path):
        """Lines 79-82: created_at is unparseable, falls back to mtime."""
        filepath = str(tmp_path / "snap.json")
        with open(filepath, "w") as f:
            f.write("{}")

        snapshot = {"created_at": "garbage", "filepath": filepath}
        result = manager._snapshot_created_at_utc(snapshot)
        assert result is not None

    def test_mtime_fallback_file_not_exists(self, manager):
        """Lines 80, 85: filepath provided but does not exist → None."""
        snapshot = {"created_at": "", "filepath": "/nonexistent/path.json"}
        result = manager._snapshot_created_at_utc(snapshot)
        assert result is None

    def test_mtime_fallback_no_filepath(self, manager):
        """Line 85: No filepath key → None."""
        snapshot = {"created_at": ""}
        result = manager._snapshot_created_at_utc(snapshot)
        assert result is None

    def test_mtime_fallback_oserror(self, manager, tmp_path):
        """Lines 83-84: os.path.getmtime raises OSError → None."""
        filepath = str(tmp_path / "snap.json")
        with open(filepath, "w") as f:
            f.write("{}")

        snapshot = {"created_at": "", "filepath": filepath}
        with patch("os.path.getmtime", side_effect=OSError("permission denied")):
            result = manager._snapshot_created_at_utc(snapshot)
            assert result is None


# ==================== create_snapshot Tests ====================


class TestCreateSnapshot:
    """Tests for create_snapshot (lines 92-178)."""

    def _mock_cja(self, metrics_df=None, dimensions_df=None, dv_info=None):
        """Build a mock CJA object."""
        cja = MagicMock()
        cja.getDataView.return_value = dv_info or {
            "name": "My View",
            "owner": {"name": "admin"},
            "description": "desc",
        }
        cja.getMetrics.return_value = metrics_df
        cja.getDimensions.return_value = dimensions_df
        return cja

    def test_getdataview_returns_falsy_raises(self, manager):
        """Line 105: getDataView returns None/empty — ValueError raised."""
        cja = MagicMock()
        cja.getDataView.return_value = None
        with pytest.raises(ValueError, match="Failed to fetch data view info"):
            manager.create_snapshot(cja, "dv_missing")

    def test_metrics_nonempty_converted(self, manager):
        """Line 116: Non-empty metrics DataFrame → to_dict('records')."""
        metrics_df = MagicMock()
        metrics_df.empty = False
        metrics_df.to_dict.return_value = [{"id": "m1", "name": "M1"}]

        dims_df = MagicMock()
        dims_df.empty = True

        cja = self._mock_cja(metrics_df=metrics_df, dimensions_df=dims_df)
        snap = manager.create_snapshot(cja, "dv_test", quiet=True)
        assert len(snap.metrics) == 1
        metrics_df.to_dict.assert_called_once_with("records")

    def test_dimensions_nonempty_converted(self, manager):
        """Line 123: Non-empty dimensions DataFrame → to_dict('records')."""
        metrics_df = MagicMock()
        metrics_df.empty = True

        dims_df = MagicMock()
        dims_df.empty = False
        dims_df.to_dict.return_value = [{"id": "d1", "name": "D1"}]

        cja = self._mock_cja(metrics_df=metrics_df, dimensions_df=dims_df)
        snap = manager.create_snapshot(cja, "dv_test", quiet=True)
        assert len(snap.dimensions) == 1
        dims_df.to_dict.assert_called_once_with("records")

    def test_none_dataframes_give_empty_lists(self, manager):
        """metrics_df and dimensions_df are None — lists stay empty."""
        cja = self._mock_cja(metrics_df=None, dimensions_df=None)
        snap = manager.create_snapshot(cja, "dv_test", quiet=True)
        assert snap.metrics == []
        assert snap.dimensions == []

    def test_calc_metrics_import_error(self, manager, capsys):
        """Lines 147-150: ImportError when loading calc metrics module."""
        import builtins

        cja = self._mock_cja(metrics_df=None, dimensions_df=None)

        original_import = builtins.__import__

        def fail_calc_import(name, *args, **kwargs):
            if name == "cja_auto_sdr.inventory.calculated_metrics":
                raise ImportError("test: module not available")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fail_calc_import):
            snap = manager.create_snapshot(cja, "dv_test", quiet=False, include_calculated_metrics=True)
            captured = capsys.readouterr()
            assert snap.calculated_metrics_inventory is None
            assert "Warning" in captured.out

    def test_calc_metrics_generic_exception(self, manager, capsys):
        """Lines 151-154: Generic exception when fetching calc metrics."""
        cja = self._mock_cja(metrics_df=None, dimensions_df=None)

        with patch("cja_auto_sdr.inventory.calculated_metrics.CalculatedMetricsInventoryBuilder") as mock_builder_cls:
            mock_builder_cls.return_value.build.side_effect = RuntimeError("API failure")
            manager.create_snapshot(cja, "dv_test", quiet=False, include_calculated_metrics=True)
            captured = capsys.readouterr()
            assert "Warning" in captured.out
            assert "API failure" in captured.out

    def test_calc_metrics_transport_exception_non_fatal(self, manager, capsys):
        """Optional calculated metrics transport errors should not abort snapshot creation."""
        cja = self._mock_cja(metrics_df=None, dimensions_df=None)

        with patch("cja_auto_sdr.inventory.calculated_metrics.CalculatedMetricsInventoryBuilder") as mock_builder_cls:
            mock_builder_cls.return_value.build.side_effect = OSError("connection reset by peer")
            snapshot = manager.create_snapshot(cja, "dv_test", quiet=False, include_calculated_metrics=True)
            captured = capsys.readouterr()

        assert snapshot.calculated_metrics_inventory is None
        assert "Warning" in captured.out
        assert "connection reset by peer" in captured.out

    def test_segments_import_error(self, manager, capsys):
        """Lines 168-170: ImportError when loading segments module."""
        import builtins

        cja = self._mock_cja(metrics_df=None, dimensions_df=None)

        original_import = builtins.__import__

        def fail_seg_import(name, *args, **kwargs):
            if name == "cja_auto_sdr.inventory.segments":
                raise ImportError("test: segments module not available")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fail_seg_import):
            snap = manager.create_snapshot(cja, "dv_test", quiet=False, include_segments=True)
            captured = capsys.readouterr()
            assert snap.segments_inventory is None
            assert "Warning" in captured.out

    def test_segments_generic_exception(self, manager, capsys):
        """Lines 172-175: Generic exception when fetching segments."""
        cja = self._mock_cja(metrics_df=None, dimensions_df=None)

        with patch("cja_auto_sdr.inventory.segments.SegmentsInventoryBuilder") as mock_builder_cls:
            mock_builder_cls.return_value.build.side_effect = RuntimeError("Segment fail")
            manager.create_snapshot(cja, "dv_test", quiet=False, include_segments=True)
            captured = capsys.readouterr()
            assert "Warning" in captured.out
            assert "Segment fail" in captured.out

    def test_segments_transport_exception_non_fatal(self, manager, capsys):
        """Optional segments transport errors should not abort snapshot creation."""
        cja = self._mock_cja(metrics_df=None, dimensions_df=None)

        with patch("cja_auto_sdr.inventory.segments.SegmentsInventoryBuilder") as mock_builder_cls:
            mock_builder_cls.return_value.build.side_effect = OSError("segments api timeout")
            snapshot = manager.create_snapshot(cja, "dv_test", quiet=False, include_segments=True)
            captured = capsys.readouterr()

        assert snapshot.segments_inventory is None
        assert "Warning" in captured.out
        assert "segments api timeout" in captured.out

    def test_calc_metrics_quiet_suppresses_output(self, manager, capsys):
        """Lines 147-154 with quiet=True: warnings still print but success messages don't."""
        cja = self._mock_cja(metrics_df=None, dimensions_df=None)

        with patch("cja_auto_sdr.inventory.calculated_metrics.CalculatedMetricsInventoryBuilder") as mock_builder_cls:
            mock_builder_cls.return_value.build.side_effect = RuntimeError("quiet test")
            manager.create_snapshot(cja, "dv_test", quiet=True, include_calculated_metrics=True)
            captured = capsys.readouterr()
            # quiet=True means no warning is printed to stdout
            assert "quiet test" not in captured.out

    def test_segments_quiet_suppresses_output(self, manager, capsys):
        """Lines 168-175 with quiet=True: warnings suppressed."""
        cja = self._mock_cja(metrics_df=None, dimensions_df=None)

        with patch("cja_auto_sdr.inventory.segments.SegmentsInventoryBuilder") as mock_builder_cls:
            mock_builder_cls.return_value.build.side_effect = RuntimeError("quiet seg")
            manager.create_snapshot(cja, "dv_test", quiet=True, include_segments=True)
            captured = capsys.readouterr()
            assert "quiet seg" not in captured.out


# ==================== save_snapshot Tests ====================


class TestSaveSnapshot:
    """Tests for SnapshotManager.save_snapshot."""

    def test_save_snapshot_writes_json(self, manager, sample_snapshot, tmp_path):
        filepath = tmp_path / "snapshot.json"

        saved = manager.save_snapshot(sample_snapshot, str(filepath))

        assert saved == str(filepath.resolve())
        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)
        assert data["data_view_id"] == sample_snapshot.data_view_id
        assert data["snapshot_version"] == sample_snapshot.snapshot_version

    def test_save_snapshot_fsyncs_parent_directory(self, manager, sample_snapshot, tmp_path, monkeypatch):
        filepath = tmp_path / "snapshot.json"
        fsync_calls: list[Path] = []

        monkeypatch.setattr(json_io, "_fsync_directory", lambda directory: fsync_calls.append(Path(directory)))

        manager.save_snapshot(sample_snapshot, str(filepath))

        assert fsync_calls == [tmp_path.resolve()]

    def test_save_snapshot_rejects_symlink_destination(self, manager, sample_snapshot, tmp_path):
        target_file = tmp_path / "real-snapshot.json"
        target_file.write_text('{"snapshot_version": "1.0", "data_view_id": "dv_original"}', encoding="utf-8")
        link_path = tmp_path / "snapshot.json"
        link_path.symlink_to(target_file)

        with pytest.raises(OSError, match="symlink"):
            manager.save_snapshot(sample_snapshot, str(link_path))

        assert link_path.is_symlink()
        assert json.loads(target_file.read_text(encoding="utf-8"))["data_view_id"] == "dv_original"

    def test_save_snapshot_failure_preserves_existing_file_and_cleans_temp(
        self,
        manager,
        sample_snapshot,
        tmp_path,
        monkeypatch,
    ):
        filepath = tmp_path / "snapshot.json"
        filepath.write_text(
            json.dumps(
                {
                    "snapshot_version": "1.0",
                    "data_view_id": "dv_original",
                    "data_view_name": "Original",
                    "created_at": "2024-01-01T00:00:00+00:00",
                    "metrics": [],
                    "dimensions": [],
                },
            ),
            encoding="utf-8",
        )
        original_contents = filepath.read_text(encoding="utf-8")

        def _failing_dump(payload, file_obj, *args, **kwargs):
            file_obj.write('{"partial": ')
            raise OSError("disk full")

        monkeypatch.setattr(json_io.json, "dump", _failing_dump)

        with pytest.raises(OSError, match="disk full"):
            manager.save_snapshot(sample_snapshot, str(filepath))

        assert filepath.read_text(encoding="utf-8") == original_contents
        assert list(tmp_path.glob(f".{filepath.name}.*.tmp")) == []


# ==================== list_snapshots edge cases ====================


class TestListSnapshotsEdgeCases:
    """Tests for list_snapshots error handling (lines 237-238)."""

    def test_corrupt_json_skipped(self, manager, tmp_path):
        """Line 237-238: json.JSONDecodeError — file is skipped."""
        # Write a valid snapshot
        _write_snapshot_json(str(tmp_path / "good.json"))
        # Write corrupt JSON
        with open(tmp_path / "corrupt.json", "w") as f:
            f.write("{invalid json content!!!")

        snapshots = manager.list_snapshots(str(tmp_path))
        assert len(snapshots) == 1
        assert snapshots[0]["filename"] == "good.json"

    def test_oserror_reading_json_skipped(self, manager, tmp_path):
        """Lines 237-238: OSError reading a JSON file — file is skipped."""
        _write_snapshot_json(str(tmp_path / "good.json"))
        # Create a file that will fail to open
        bad_path = tmp_path / "bad.json"
        bad_path.write_text("{}")

        original_open = open

        def patched_open(path, *args, **kwargs):
            if str(path).endswith("bad.json"):
                raise OSError("permission denied")
            return original_open(path, *args, **kwargs)

        with patch("builtins.open", side_effect=patched_open):
            snapshots = manager.list_snapshots(str(tmp_path))
            assert len(snapshots) == 1

    def test_nonexistent_directory_returns_empty(self, manager, tmp_path):
        """Line 216-217: Directory does not exist."""
        snapshots = manager.list_snapshots(str(tmp_path / "nope"))
        assert snapshots == []

    def test_non_json_files_ignored(self, manager, tmp_path):
        """Line 220: Only .json files are considered."""
        (tmp_path / "readme.txt").write_text("hello")
        (tmp_path / "data.csv").write_text("a,b,c")
        snapshots = manager.list_snapshots(str(tmp_path))
        assert snapshots == []


# ==================== apply_retention_policy edge cases ====================


class TestApplyRetentionPolicy:
    """Tests for apply_retention_policy (lines 252-274)."""

    def test_keep_last_zero_returns_empty(self, manager, tmp_path):
        """Line 254-255: keep_last <= 0 → return []."""
        assert manager.apply_retention_policy(str(tmp_path), "dv_abc", 0) == []

    def test_keep_last_negative_returns_empty(self, manager, tmp_path):
        """Line 254-255: keep_last negative → return []."""
        assert manager.apply_retention_policy(str(tmp_path), "dv_abc", -5) == []

    def test_fewer_snapshots_than_keep_last(self, manager, tmp_path):
        """Line 260-261: Only 2 snapshots, keep_last=5 → nothing deleted."""
        _write_snapshot_json(str(tmp_path / "s1.json"), created_at="2024-01-01T10:00:00+00:00")
        _write_snapshot_json(str(tmp_path / "s2.json"), created_at="2024-01-02T10:00:00+00:00")
        deleted = manager.apply_retention_policy(str(tmp_path), "dv_abc", 5)
        assert deleted == []

    def test_deletes_excess_snapshots(self, manager, tmp_path):
        """Lines 263-270: Deletes oldest snapshots beyond keep_last."""
        _write_snapshot_json(str(tmp_path / "old.json"), created_at="2024-01-01T10:00:00+00:00")
        _write_snapshot_json(str(tmp_path / "mid.json"), created_at="2024-01-02T10:00:00+00:00")
        _write_snapshot_json(str(tmp_path / "new.json"), created_at="2024-01-03T10:00:00+00:00")

        deleted = manager.apply_retention_policy(str(tmp_path), "dv_abc", 1)
        assert len(deleted) == 2
        # Only the newest should remain
        remaining = manager.list_snapshots(str(tmp_path))
        assert len(remaining) == 1
        assert remaining[0]["filename"] == "new.json"

    def test_oserror_on_delete_logged(self, manager, tmp_path):
        """Lines 271-272: OSError when removing a file — logged, not raised."""
        _write_snapshot_json(str(tmp_path / "old.json"), created_at="2024-01-01T10:00:00+00:00")
        _write_snapshot_json(str(tmp_path / "new.json"), created_at="2024-01-02T10:00:00+00:00")

        with patch("os.remove", side_effect=OSError("permission denied")):
            deleted = manager.apply_retention_policy(str(tmp_path), "dv_abc", 1)
            # os.remove failed, so nothing was actually deleted
            assert deleted == []

    def test_only_deletes_matching_data_view_id(self, manager, tmp_path):
        """Retention only applies to the specified data_view_id."""
        _write_snapshot_json(str(tmp_path / "a1.json"), data_view_id="dv_a", created_at="2024-01-01T10:00:00+00:00")
        _write_snapshot_json(str(tmp_path / "a2.json"), data_view_id="dv_a", created_at="2024-01-02T10:00:00+00:00")
        _write_snapshot_json(str(tmp_path / "b1.json"), data_view_id="dv_b", created_at="2024-01-01T10:00:00+00:00")

        deleted = manager.apply_retention_policy(str(tmp_path), "dv_a", 1)
        assert len(deleted) == 1
        # dv_b's snapshot should be untouched
        remaining = manager.list_snapshots(str(tmp_path))
        dv_b_remaining = [s for s in remaining if s["data_view_id"] == "dv_b"]
        assert len(dv_b_remaining) == 1


# ==================== apply_date_retention_policy Tests ====================


class TestApplyDateRetentionPolicy:
    """Tests for apply_date_retention_policy (lines 276-316)."""

    def test_none_days_returns_empty(self, manager, tmp_path):
        """Line 285-286: days is None → return []."""
        result = manager.apply_date_retention_policy(str(tmp_path), "dv_abc")
        assert result == []

    def test_zero_days_returns_empty(self, manager, tmp_path):
        """Line 286: days=0 → return []."""
        result = manager.apply_date_retention_policy(str(tmp_path), "dv_abc", keep_since_days=0)
        assert result == []

    def test_negative_days_returns_empty(self, manager, tmp_path):
        """Line 286: negative days → return []."""
        result = manager.apply_date_retention_policy(str(tmp_path), "dv_abc", keep_since_days=-10)
        assert result == []

    def test_wildcard_data_view_id(self, manager, tmp_path):
        """Line 295: data_view_id='*' applies to all snapshots."""
        old_time = (datetime.now(UTC) - timedelta(days=100)).isoformat()
        _write_snapshot_json(str(tmp_path / "a.json"), data_view_id="dv_a", created_at=old_time)
        _write_snapshot_json(str(tmp_path / "b.json"), data_view_id="dv_b", created_at=old_time)

        deleted = manager.apply_date_retention_policy(str(tmp_path), "*", keep_since_days=30)
        assert len(deleted) == 2

    def test_empty_data_view_id_applies_to_all(self, manager, tmp_path):
        """Line 295: empty string data_view_id applies to all snapshots."""
        old_time = (datetime.now(UTC) - timedelta(days=100)).isoformat()
        _write_snapshot_json(str(tmp_path / "a.json"), data_view_id="dv_a", created_at=old_time)
        _write_snapshot_json(str(tmp_path / "b.json"), data_view_id="dv_b", created_at=old_time)

        deleted = manager.apply_date_retention_policy(str(tmp_path), "", keep_since_days=30)
        assert len(deleted) == 2

    def test_snapshot_with_no_created_at_skipped(self, manager, tmp_path):
        """Line 301: snapshot_created_at is None → continue (not deleted)."""
        # Write a snapshot with no created_at
        data = {
            "snapshot_version": "1.0",
            "data_view_id": "dv_abc",
            "data_view_name": "Test",
            "created_at": "",
            "metrics": [],
            "dimensions": [],
        }
        filepath = str(tmp_path / "no_date.json")
        with open(filepath, "w") as f:
            json.dump(data, f)

        # Patch getmtime so the mtime fallback also returns None
        with patch("os.path.getmtime", side_effect=OSError("no mtime")):
            deleted = manager.apply_date_retention_policy(str(tmp_path), "dv_abc", keep_since_days=1)
            # Should skip (not delete) because created_at couldn't be resolved
            assert deleted == []
            # File should still exist (not deleted)
            assert os.path.exists(filepath)

    def test_deletes_old_snapshots_within_window(self, manager, tmp_path):
        """Deletes snapshots older than keep_since_days."""
        old_time = (datetime.now(UTC) - timedelta(days=60)).isoformat()
        recent_time = (datetime.now(UTC) - timedelta(days=1)).isoformat()

        _write_snapshot_json(str(tmp_path / "old.json"), created_at=old_time)
        _write_snapshot_json(str(tmp_path / "recent.json"), created_at=recent_time)

        deleted = manager.apply_date_retention_policy(str(tmp_path), "dv_abc", keep_since_days=30)
        assert len(deleted) == 1
        assert "old.json" in deleted[0]
        remaining = manager.list_snapshots(str(tmp_path))
        assert len(remaining) == 1

    def test_oserror_on_delete_logged_not_raised(self, manager, tmp_path):
        """Lines 310-311: OSError during file removal — logged, not raised."""
        old_time = (datetime.now(UTC) - timedelta(days=100)).isoformat()
        _write_snapshot_json(str(tmp_path / "old.json"), created_at=old_time)

        with patch("os.remove", side_effect=OSError("read-only filesystem")):
            deleted = manager.apply_date_retention_policy(str(tmp_path), "dv_abc", keep_since_days=30)
            assert deleted == []

    def test_delete_older_than_days_alias(self, manager, tmp_path):
        """delete_older_than_days is an alias for keep_since_days."""
        old_time = (datetime.now(UTC) - timedelta(days=60)).isoformat()
        _write_snapshot_json(str(tmp_path / "old.json"), created_at=old_time)

        deleted = manager.apply_date_retention_policy(str(tmp_path), "dv_abc", delete_older_than_days=30)
        assert len(deleted) == 1


# ==================== generate_snapshot_filename Tests ====================


class TestGenerateSnapshotFilename:
    """Tests for generate_snapshot_filename."""

    def test_without_name(self, manager):
        """Filename has just data_view_id and timestamp."""
        name = manager.generate_snapshot_filename("dv_abc123")
        assert name.startswith("dv_abc123_")
        assert name.endswith(".json")

    def test_with_name(self, manager):
        """Filename includes sanitised data view name."""
        name = manager.generate_snapshot_filename("dv_abc123", "My View!")
        assert "My_View_" in name
        assert name.endswith(".json")

    def test_long_name_truncated(self, manager):
        """Long data view names are truncated to 50 chars."""
        long_name = "A" * 100
        name = manager.generate_snapshot_filename("dv_abc123", long_name)
        # The safe_name portion should be at most 50 chars
        parts_before_id = name.split("dv_abc123")[0]
        safe_name_part = parts_before_id.rstrip("_")
        assert len(safe_name_part) <= 50

    def test_special_chars_sanitised(self, manager):
        """Special characters replaced with underscores."""
        name = manager.generate_snapshot_filename("dv_x", "Hello World! @#$")
        assert " " not in name
        assert "!" not in name
        assert "@" not in name


# ==================== get_most_recent_snapshot Tests ====================


class TestGetMostRecentSnapshot:
    """Tests for get_most_recent_snapshot."""

    def test_returns_none_when_no_match(self, manager, tmp_path):
        """No snapshots for the data_view_id → None."""
        _write_snapshot_json(str(tmp_path / "other.json"), data_view_id="dv_other")
        result = manager.get_most_recent_snapshot(str(tmp_path), "dv_abc")
        assert result is None

    def test_returns_most_recent(self, manager, tmp_path):
        """Returns the most recent snapshot filepath."""
        _write_snapshot_json(
            str(tmp_path / "old.json"),
            data_view_id="dv_abc",
            created_at="2024-01-01T10:00:00+00:00",
        )
        _write_snapshot_json(
            str(tmp_path / "new.json"),
            data_view_id="dv_abc",
            created_at="2024-06-15T10:00:00+00:00",
        )
        result = manager.get_most_recent_snapshot(str(tmp_path), "dv_abc")
        assert result is not None
        assert result.endswith("new.json")


# ==================== parse_retention_period Tests ====================


class TestParseRetentionPeriod:
    """Tests for parse_retention_period (lines 328-356)."""

    def test_empty_string_returns_none(self):
        """Line 339: empty string → None."""
        assert parse_retention_period("") is None

    def test_none_returns_none(self):
        """Line 339: None-ish — though the function expects str, empty is the guard."""
        assert parse_retention_period("") is None

    def test_plain_digits(self):
        """Line 344: '30' → 30 days."""
        assert parse_retention_period("30") == 30

    def test_plain_digits_with_whitespace(self):
        """Whitespace stripped before parsing."""
        assert parse_retention_period("  7  ") == 7

    def test_days_suffix_lowercase(self):
        """Line 348: '7d' → 7."""
        assert parse_retention_period("7d") == 7

    def test_days_suffix_uppercase(self):
        """Line 348: '14D' → 14."""
        assert parse_retention_period("14D") == 14

    def test_weeks_suffix(self):
        """Line 349-350: '2w' → 14."""
        assert parse_retention_period("2w") == 14

    def test_weeks_suffix_uppercase(self):
        """'3W' → 21."""
        assert parse_retention_period("3W") == 21

    def test_months_suffix(self):
        """Lines 351-352: '1m' → 30."""
        assert parse_retention_period("1m") == 30

    def test_months_suffix_uppercase(self):
        """'2M' → 60."""
        assert parse_retention_period("2M") == 60

    def test_invalid_suffix_returns_none(self):
        """Line 356: Unrecognized suffix → None."""
        assert parse_retention_period("10y") is None

    def test_non_numeric_prefix_returns_none(self):
        """Lines 353-354: ValueError from int() → None."""
        assert parse_retention_period("abcd") is None

    def test_non_numeric_with_valid_suffix_returns_none(self):
        """Lines 353-354: 'xyzd' → int('xyz') fails → None."""
        assert parse_retention_period("xyzd") is None

    def test_zero_days(self):
        """'0d' → 0."""
        assert parse_retention_period("0d") == 0

    def test_zero_plain(self):
        """'0' → 0."""
        assert parse_retention_period("0") == 0


# ==================== _snapshot_sort_key Tests ====================


class TestSnapshotSortKey:
    """Tests for _snapshot_sort_key."""

    def test_valid_timestamp(self, manager):
        """Returns the UTC datetime."""
        snapshot = {"created_at": "2024-06-15T12:00:00+00:00"}
        key = manager._snapshot_sort_key(snapshot)
        assert key == datetime(2024, 6, 15, 12, 0, 0, tzinfo=UTC)

    def test_no_timestamp_returns_datetime_min(self, manager):
        """No parseable timestamp → datetime.min with UTC tz."""
        snapshot = {"created_at": ""}
        key = manager._snapshot_sort_key(snapshot)
        assert key == datetime.min.replace(tzinfo=UTC)


# ==================== SnapshotManager.__init__ Tests ====================


class TestSnapshotManagerInit:
    """Tests for SnapshotManager constructor."""

    def test_default_logger(self):
        """No logger provided → creates one."""
        manager = SnapshotManager()
        assert manager.logger is not None

    def test_custom_logger(self, logger):
        """Custom logger is stored."""
        manager = SnapshotManager(logger)
        assert manager.logger is logger
