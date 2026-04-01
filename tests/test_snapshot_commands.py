"""Tests for snapshot creation, comparison, and name resolution commands.

Covers:
- handle_snapshot_command (lines 12593-12678)
- handle_diff_snapshot_command (lines 12991-13373)
- handle_compare_snapshots_command (lines 13376-13605)
- Snapshot dispatch and name resolution in main() (lines 14263-14786)
"""

from __future__ import annotations

import json
import os
from unittest.mock import MagicMock, patch

import pytest

import cja_auto_sdr.core.json_io as json_io
from cja_auto_sdr.diff.models import (
    DataViewSnapshot,
    DiffResult,
    DiffSummary,
    MetadataDiff,
)
from cja_auto_sdr.generator import (
    _known_long_options,
    handle_compare_snapshots_command,
    handle_diff_snapshot_command,
    handle_snapshot_command,
    resolve_data_view_names,
)
from cja_auto_sdr.generator import (
    parse_arguments as _real_parse_arguments,
)

# _known_long_options() internally calls parse_arguments(return_parser=True).
# When tests @patch parse_arguments, that internal call would return a MagicMock
# instead of a real parser, breaking _cli_option_value / _cli_option_specified.
# Pre-populating the lru_cache here avoids that — the real frozenset is cached
# once and reused across all tests regardless of patches.
_known_long_options()

# ==================== Helpers ====================


def _make_snapshot(**overrides) -> DataViewSnapshot:
    """Build a minimal DataViewSnapshot with sensible defaults."""
    defaults = {
        "data_view_id": "dv_test",
        "data_view_name": "Test DV",
        "owner": "owner@test.com",
        "description": "desc",
        "metrics": [{"id": "m1", "name": "Metric A"}],
        "dimensions": [{"id": "d1", "name": "Dim A"}],
        "created_at": "2025-06-01T00:00:00+00:00",
    }
    defaults.update(overrides)
    return DataViewSnapshot(**defaults)


def _make_diff_result(has_changes: bool = False, change_pct: float = 0.0) -> DiffResult:
    """Build a minimal DiffResult for mocking."""
    summary = DiffSummary(
        source_metrics_count=10,
        target_metrics_count=10,
        source_dimensions_count=5,
        target_dimensions_count=5,
        metrics_added=1 if has_changes else 0,
    )
    metadata = MetadataDiff(
        source_name="Source DV",
        target_name="Target DV",
        source_id="dv_src",
        target_id="dv_tgt",
    )
    return DiffResult(
        summary=summary,
        metadata_diff=metadata,
        metric_diffs=[],
        dimension_diffs=[],
    )


def _write_snapshot_file(path, snapshot: DataViewSnapshot | None = None):
    """Write a snapshot JSON to disk."""
    if snapshot is None:
        snapshot = _make_snapshot()
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot.to_dict(), f)


# ==================== handle_snapshot_command ====================


class TestHandleSnapshotCommand:
    """Tests for handle_snapshot_command — snapshot creation flow."""

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_successful_snapshot_creation(self, mock_configure, mock_cjapy, tmp_path, capsys):
        """Snapshot creation succeeds and writes file."""
        mock_configure.return_value = (True, "config", None)
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataView.return_value = {
            "name": "My Data View",
            "owner": {"name": "admin"},
            "description": "A test data view",
        }
        mock_cja.getMetrics.return_value = MagicMock(
            empty=False, to_dict=MagicMock(return_value=[{"id": "m1", "name": "M1"}])
        )
        mock_cja.getDimensions.return_value = MagicMock(
            empty=False, to_dict=MagicMock(return_value=[{"id": "d1", "name": "D1"}])
        )

        out_file = str(tmp_path / "snap.json")
        result = handle_snapshot_command(
            data_view_id="dv_123",
            snapshot_file=out_file,
            config_file="config.json",
            quiet=False,
        )

        assert result is True
        assert os.path.exists(out_file)

        with open(out_file, encoding="utf-8") as f:
            data = json.load(f)
        assert data["data_view_id"] == "dv_123"
        assert data["data_view_name"] == "My Data View"

        captured = capsys.readouterr()
        assert "SNAPSHOT CREATED SUCCESSFULLY" in captured.out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_snapshot_quiet_mode(self, mock_configure, mock_cjapy, tmp_path, capsys):
        """Quiet mode suppresses progress output."""
        mock_configure.return_value = (True, "config", None)
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataView.return_value = {"name": "DV", "owner": "o", "description": ""}
        mock_cja.getMetrics.return_value = MagicMock(empty=False, to_dict=MagicMock(return_value=[]))
        mock_cja.getDimensions.return_value = MagicMock(empty=False, to_dict=MagicMock(return_value=[]))

        out_file = str(tmp_path / "snap.json")
        result = handle_snapshot_command(
            data_view_id="dv_123",
            snapshot_file=out_file,
            quiet=True,
        )

        assert result is True
        captured = capsys.readouterr()
        assert "SNAPSHOT CREATED SUCCESSFULLY" not in captured.out
        assert "CREATING DATA VIEW SNAPSHOT" not in captured.out

    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_configuration_failure(self, mock_configure, tmp_path, capsys):
        """Returns False when CJA configuration fails."""
        mock_configure.return_value = (False, "Missing credentials", None)

        out_file = str(tmp_path / "snap.json")
        result = handle_snapshot_command(
            data_view_id="dv_123",
            snapshot_file=out_file,
            quiet=True,
        )

        assert result is False
        captured = capsys.readouterr()
        assert "Configuration failed" in captured.err

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_snapshot_with_inventory_flags(self, mock_configure, mock_cjapy, tmp_path, capsys):
        """Snapshot creation includes inventory info in banner."""
        mock_configure.return_value = (True, "config", None)
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataView.return_value = {"name": "DV", "owner": "o", "description": ""}
        mock_cja.getMetrics.return_value = MagicMock(
            empty=False, to_dict=MagicMock(return_value=[{"id": "m1", "name": "M1"}])
        )
        mock_cja.getDimensions.return_value = MagicMock(empty=False, to_dict=MagicMock(return_value=[]))

        out_file = str(tmp_path / "snap.json")
        result = handle_snapshot_command(
            data_view_id="dv_123",
            snapshot_file=out_file,
            include_calculated_metrics=True,
            include_segments=True,
        )

        assert result is True
        captured = capsys.readouterr()
        assert "calculated metrics" in captured.out
        assert "segments" in captured.out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_snapshot_general_exception(self, mock_configure, mock_cjapy, tmp_path, capsys):
        """Returns False on unexpected exception."""
        from cja_auto_sdr.core.exceptions import APIError

        mock_configure.return_value = (True, "config", None)
        mock_cjapy.CJA.side_effect = APIError("API down")

        out_file = str(tmp_path / "snap.json")
        result = handle_snapshot_command(
            data_view_id="dv_123",
            snapshot_file=out_file,
            quiet=True,
        )

        assert result is False
        captured = capsys.readouterr()
        assert "Failed to create snapshot" in captured.err

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_snapshot_constructor_exception(self, mock_configure, mock_cjapy, tmp_path, capsys):
        """Bare constructor failures from cjapy should return False with CLI error output."""
        mock_configure.return_value = (True, "config", None)
        mock_cjapy.CJA.side_effect = Exception("auth bootstrap failed")

        out_file = str(tmp_path / "snap.json")
        result = handle_snapshot_command(
            data_view_id="dv_123",
            snapshot_file=out_file,
        )

        assert result is False
        captured = capsys.readouterr()
        assert "Failed to create snapshot: auth bootstrap failed" in captured.err

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_snapshot_constructor_hint_stays_on_stderr(self, mock_configure, mock_cjapy, tmp_path, capsys):
        """Hint-bearing snapshot failures should keep the error and hint together on stderr."""
        mock_configure.return_value = (True, "config", None)
        mock_cjapy.CJA.side_effect = KeyError("content")

        out_file = str(tmp_path / "snap.json")
        result = handle_snapshot_command(
            data_view_id="dv_123",
            snapshot_file=out_file,
            quiet=True,
        )

        assert result is False
        captured = capsys.readouterr()
        assert "Failed to create snapshot: 'content'" in captured.err
        assert "AEP API" in captured.err
        assert captured.out == ""

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_snapshot_with_profile(self, mock_configure, mock_cjapy, tmp_path):
        """Profile parameter is passed to configure_cjapy."""
        mock_configure.return_value = (True, "config", None)
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataView.return_value = {"name": "DV", "owner": "o", "description": ""}
        mock_cja.getMetrics.return_value = MagicMock(empty=False, to_dict=MagicMock(return_value=[]))
        mock_cja.getDimensions.return_value = MagicMock(empty=False, to_dict=MagicMock(return_value=[]))

        out_file = str(tmp_path / "snap.json")
        handle_snapshot_command(
            data_view_id="dv_123",
            snapshot_file=out_file,
            profile="staging",
        )

        mock_configure.assert_called_once_with(
            profile="staging", config_file="config.json", logger=mock_configure.call_args[1]["logger"]
        )

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_snapshot_write_failure_preserves_existing_file(self, mock_configure, mock_cjapy, tmp_path, monkeypatch):
        """Atomic snapshot writes keep the prior baseline intact on write failure."""
        mock_configure.return_value = (True, "config", None)
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataView.return_value = {"name": "DV", "owner": "o", "description": ""}
        mock_cja.getMetrics.return_value = MagicMock(empty=False, to_dict=MagicMock(return_value=[]))
        mock_cja.getDimensions.return_value = MagicMock(empty=False, to_dict=MagicMock(return_value=[]))

        out_file = tmp_path / "snap.json"
        out_file.write_text(
            json.dumps(
                {
                    "snapshot_version": "1.0",
                    "data_view_id": "dv_existing",
                    "data_view_name": "Existing",
                    "created_at": "2024-01-01T00:00:00+00:00",
                    "metrics": [],
                    "dimensions": [],
                },
            ),
            encoding="utf-8",
        )
        original_contents = out_file.read_text(encoding="utf-8")

        def _failing_dump(payload, file_obj, *args, **kwargs):
            file_obj.write('{"partial": ')
            raise OSError("disk full")

        monkeypatch.setattr(json_io.json, "dump", _failing_dump)

        result = handle_snapshot_command(
            data_view_id="dv_123",
            snapshot_file=str(out_file),
            quiet=True,
        )

        assert result is False
        assert out_file.read_text(encoding="utf-8") == original_contents
        assert list(tmp_path.glob(f".{out_file.name}.*.tmp")) == []


# ==================== handle_compare_snapshots_command ====================


class TestHandleCompareSnapshotsCommand:
    """Tests for handle_compare_snapshots_command — offline snapshot comparison."""

    def test_compare_identical_snapshots(self, tmp_path, capsys):
        """Comparing identical snapshots reports no changes."""
        source = _make_snapshot(data_view_id="dv_A", data_view_name="DV A")
        target = _make_snapshot(data_view_id="dv_B", data_view_name="DV B")

        src_file = str(tmp_path / "source.json")
        tgt_file = str(tmp_path / "target.json")
        _write_snapshot_file(src_file, source)
        _write_snapshot_file(tgt_file, target)

        success, _has_changes, _exit_code = handle_compare_snapshots_command(
            source_file=src_file,
            target_file=tgt_file,
            quiet=True,
            quiet_diff=True,
        )

        assert success is True

    def test_compare_snapshots_file_not_found(self, tmp_path, capsys):
        """Returns failure when snapshot file is missing."""
        src_file = str(tmp_path / "source.json")
        _write_snapshot_file(src_file)

        success, _has_changes, _exit_code = handle_compare_snapshots_command(
            source_file=src_file,
            target_file=str(tmp_path / "nonexistent.json"),
            quiet=True,
        )

        assert success is False
        captured = capsys.readouterr()
        assert "Snapshot file not found" in captured.err

    def test_compare_snapshots_invalid_file(self, tmp_path, capsys):
        """Returns failure for invalid snapshot file (missing snapshot_version)."""
        src_file = str(tmp_path / "source.json")
        _write_snapshot_file(src_file)

        invalid_file = str(tmp_path / "invalid.json")
        with open(invalid_file, "w", encoding="utf-8") as f:
            json.dump({"not_a_snapshot": True}, f)

        success, _has_changes, _exit_code = handle_compare_snapshots_command(
            source_file=src_file,
            target_file=invalid_file,
            quiet=True,
        )

        assert success is False
        captured = capsys.readouterr()
        assert "Invalid snapshot file" in captured.err

    def test_compare_snapshots_unexpected_exception(self, tmp_path, capsys):
        """Plain Exception during comparison should return controlled failure, not traceback."""
        src_file = str(tmp_path / "source.json")
        tgt_file = str(tmp_path / "target.json")
        _write_snapshot_file(src_file)
        _write_snapshot_file(tgt_file)

        mock_manager = MagicMock()
        mock_manager.load_snapshot.side_effect = RuntimeError("unexpected comparator crash")
        with patch("cja_auto_sdr.generator.SnapshotManager", return_value=mock_manager):
            success, has_changes, exit_code = handle_compare_snapshots_command(
                source_file=src_file,
                target_file=tgt_file,
                quiet=True,
            )

        assert success is False
        assert has_changes is False
        assert exit_code is None
        captured = capsys.readouterr()
        assert "unexpected" in captured.err.lower()

    def test_compare_snapshots_with_banner(self, tmp_path, capsys):
        """Non-quiet mode prints comparison banner."""
        source = _make_snapshot(data_view_id="dv_A", data_view_name="DV A")
        target = _make_snapshot(data_view_id="dv_B", data_view_name="DV B")

        src_file = str(tmp_path / "source.json")
        tgt_file = str(tmp_path / "target.json")
        _write_snapshot_file(src_file, source)
        _write_snapshot_file(tgt_file, target)

        success, _has_changes, _exit_code = handle_compare_snapshots_command(
            source_file=src_file,
            target_file=tgt_file,
            quiet=False,
            quiet_diff=False,
            output_format="console",
            no_color=True,
        )

        assert success is True
        captured = capsys.readouterr()
        assert "COMPARING TWO SNAPSHOTS" in captured.out
        assert "Source:" in captured.out
        assert "Target:" in captured.out

    def test_compare_snapshots_reverse_diff(self, tmp_path, capsys):
        """Reverse diff swaps source and target."""
        source = _make_snapshot(
            data_view_id="dv_A",
            data_view_name="DV A",
            metrics=[{"id": "m1", "name": "Metric A"}],
        )
        target = _make_snapshot(
            data_view_id="dv_B",
            data_view_name="DV B",
            metrics=[{"id": "m1", "name": "Metric A"}, {"id": "m2", "name": "Metric B"}],
        )

        src_file = str(tmp_path / "source.json")
        tgt_file = str(tmp_path / "target.json")
        _write_snapshot_file(src_file, source)
        _write_snapshot_file(tgt_file, target)

        success, _has_changes, _exit_code = handle_compare_snapshots_command(
            source_file=src_file,
            target_file=tgt_file,
            reverse_diff=True,
            quiet=False,
            quiet_diff=False,
            output_format="console",
            no_color=True,
        )

        assert success is True
        captured = capsys.readouterr()
        assert "(Reversed comparison)" in captured.out

    def test_compare_snapshots_custom_labels(self, tmp_path, capsys):
        """Custom labels appear in comparison output."""
        source = _make_snapshot(data_view_id="dv_A", data_view_name="DV A")
        target = _make_snapshot(data_view_id="dv_B", data_view_name="DV B")

        src_file = str(tmp_path / "source.json")
        tgt_file = str(tmp_path / "target.json")
        _write_snapshot_file(src_file, source)
        _write_snapshot_file(tgt_file, target)

        success, _, _ = handle_compare_snapshots_command(
            source_file=src_file,
            target_file=tgt_file,
            labels=("Baseline", "Current"),
            quiet=False,
            quiet_diff=False,
            output_format="console",
            no_color=True,
        )

        assert success is True
        captured = capsys.readouterr()
        assert "Baseline" in captured.out
        assert "Current" in captured.out

    def test_compare_snapshots_warn_threshold_exceeded(self, tmp_path, capsys):
        """Exit code 3 when change percentage exceeds warn threshold."""
        source = _make_snapshot(
            data_view_id="dv_A",
            data_view_name="DV A",
            metrics=[{"id": f"m{i}", "name": f"M{i}"} for i in range(10)],
        )
        # Target is missing all metrics -> 100% change
        target = _make_snapshot(
            data_view_id="dv_B",
            data_view_name="DV B",
            metrics=[],
        )

        src_file = str(tmp_path / "source.json")
        tgt_file = str(tmp_path / "target.json")
        _write_snapshot_file(src_file, source)
        _write_snapshot_file(tgt_file, target)

        success, has_changes, exit_code = handle_compare_snapshots_command(
            source_file=src_file,
            target_file=tgt_file,
            warn_threshold=5.0,
            quiet=True,
            quiet_diff=False,
            output_format="console",
            no_color=True,
        )

        assert success is True
        assert has_changes is True
        assert exit_code == 3

    def test_compare_snapshots_diff_output_to_file(self, tmp_path, capsys):
        """--diff-output writes content to a file."""
        source = _make_snapshot(data_view_id="dv_A", data_view_name="DV A")
        target = _make_snapshot(data_view_id="dv_B", data_view_name="DV B")

        src_file = str(tmp_path / "source.json")
        tgt_file = str(tmp_path / "target.json")
        diff_out = str(tmp_path / "diff_output.txt")
        _write_snapshot_file(src_file, source)
        _write_snapshot_file(tgt_file, target)

        success, _, _ = handle_compare_snapshots_command(
            source_file=src_file,
            target_file=tgt_file,
            diff_output=diff_out,
            quiet=False,
            quiet_diff=False,
            output_format="console",
            no_color=True,
        )

        assert success is True
        assert os.path.exists(diff_out)

    def test_compare_snapshots_general_exception(self, tmp_path, capsys):
        """General exception returns failure tuple."""
        src_file = str(tmp_path / "source.json")
        # Write a valid JSON that will cause a downstream error
        with open(src_file, "w", encoding="utf-8") as f:
            json.dump({"snapshot_version": "1.0", "data_view_id": "dv_A", "data_view_name": "A"}, f)

        tgt_file = str(tmp_path / "target.json")
        with open(tgt_file, "w", encoding="utf-8") as f:
            f.write("this is not json")

        success, _has_changes, _exit_code = handle_compare_snapshots_command(
            source_file=src_file,
            target_file=tgt_file,
            quiet=True,
        )

        assert success is False

    def test_compare_snapshots_inventory_cross_dv_error(self, tmp_path, capsys):
        """Inventory comparison fails when snapshots are from different data views."""
        source = _make_snapshot(
            data_view_id="dv_A",
            data_view_name="DV A",
            calculated_metrics_inventory=[],
        )
        target = _make_snapshot(
            data_view_id="dv_B",
            data_view_name="DV B",
            calculated_metrics_inventory=[],
        )

        src_file = str(tmp_path / "source.json")
        tgt_file = str(tmp_path / "target.json")
        _write_snapshot_file(src_file, source)
        _write_snapshot_file(tgt_file, target)

        success, _has_changes, _exit_code = handle_compare_snapshots_command(
            source_file=src_file,
            target_file=tgt_file,
            include_calc_metrics=True,
            quiet=True,
        )

        assert success is False
        captured = capsys.readouterr()
        assert "Inventory comparison requires snapshots from the same data view" in captured.err

    def test_compare_snapshots_quiet_diff_suppresses_output(self, tmp_path, capsys):
        """quiet_diff suppresses comparison output but still returns results."""
        source = _make_snapshot(data_view_id="dv_A", data_view_name="DV A")
        target = _make_snapshot(data_view_id="dv_B", data_view_name="DV B")

        src_file = str(tmp_path / "source.json")
        tgt_file = str(tmp_path / "target.json")
        _write_snapshot_file(src_file, source)
        _write_snapshot_file(tgt_file, target)

        success, _, _ = handle_compare_snapshots_command(
            source_file=src_file,
            target_file=tgt_file,
            quiet=True,
            quiet_diff=True,
        )

        assert success is True
        captured = capsys.readouterr()
        # quiet_diff means no diff output, and quiet means no banner
        assert "COMPARING TWO SNAPSHOTS" not in captured.out

    def test_compare_snapshots_same_dv_with_inventory(self, tmp_path, capsys):
        """Inventory comparison works when snapshots are from the same data view."""
        source = _make_snapshot(
            data_view_id="dv_A",
            data_view_name="DV A",
            calculated_metrics_inventory=[
                {"metric_id": "cm1", "metric_name": "Calc A"},
            ],
        )
        target = _make_snapshot(
            data_view_id="dv_A",
            data_view_name="DV A",
            calculated_metrics_inventory=[
                {"metric_id": "cm1", "metric_name": "Calc A Modified"},
                {"metric_id": "cm2", "metric_name": "Calc B"},
            ],
        )

        src_file = str(tmp_path / "source.json")
        tgt_file = str(tmp_path / "target.json")
        _write_snapshot_file(src_file, source)
        _write_snapshot_file(tgt_file, target)

        success, _has_changes, _exit_code = handle_compare_snapshots_command(
            source_file=src_file,
            target_file=tgt_file,
            include_calc_metrics=True,
            quiet=True,
            quiet_diff=True,
        )

        assert success is True

    def test_compare_snapshots_non_console_format(self, tmp_path, capsys):
        """Non-console output format shows 'Diff report generated successfully'."""
        source = _make_snapshot(data_view_id="dv_A", data_view_name="DV A")
        target = _make_snapshot(data_view_id="dv_B", data_view_name="DV B")

        src_file = str(tmp_path / "source.json")
        tgt_file = str(tmp_path / "target.json")
        _write_snapshot_file(src_file, source)
        _write_snapshot_file(tgt_file, target)

        success, _, _ = handle_compare_snapshots_command(
            source_file=src_file,
            target_file=tgt_file,
            quiet=False,
            quiet_diff=False,
            output_format="json",
            output_dir=str(tmp_path),
            no_color=True,
        )

        assert success is True
        captured = capsys.readouterr()
        assert "Diff report generated successfully" in captured.out


# ==================== handle_diff_snapshot_command ====================


class TestHandleDiffSnapshotCommand:
    """Tests for handle_diff_snapshot_command — compare live DV against snapshot."""

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_successful_diff_snapshot(self, mock_configure, mock_cjapy, tmp_path, capsys):
        """Diff against snapshot succeeds end-to-end."""
        mock_configure.return_value = (True, "config", None)
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataView.return_value = {
            "name": "Test DV",
            "owner": {"name": "admin"},
            "description": "desc",
        }
        mock_cja.getMetrics.return_value = MagicMock(
            empty=False, to_dict=MagicMock(return_value=[{"id": "m1", "name": "Metric A"}])
        )
        mock_cja.getDimensions.return_value = MagicMock(
            empty=False, to_dict=MagicMock(return_value=[{"id": "d1", "name": "Dim A"}])
        )

        snap_file = str(tmp_path / "baseline.json")
        _write_snapshot_file(snap_file)

        success, _has_changes, _exit_code = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file=snap_file,
            quiet=True,
            quiet_diff=True,
        )

        assert success is True

    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_snapshot_config_failure(self, mock_configure, tmp_path, capsys):
        """Returns failure when CJA configuration fails."""
        mock_configure.return_value = (False, "No credentials", None)

        snap_file = str(tmp_path / "baseline.json")
        _write_snapshot_file(snap_file)

        success, _has_changes, _exit_code = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file=snap_file,
            quiet=False,
            quiet_diff=False,
        )

        assert success is False
        captured = capsys.readouterr()
        assert "Configuration failed" in captured.err

    def test_diff_snapshot_file_not_found(self, tmp_path, capsys):
        """Returns failure when snapshot file does not exist."""
        success, _has_changes, _exit_code = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file=str(tmp_path / "nonexistent.json"),
            quiet=True,
        )

        assert success is False
        captured = capsys.readouterr()
        assert "Snapshot file not found" in captured.err

    def test_diff_snapshot_invalid_file(self, tmp_path, capsys):
        """Returns failure for invalid snapshot file."""
        invalid_file = str(tmp_path / "bad.json")
        with open(invalid_file, "w", encoding="utf-8") as f:
            json.dump({"no_version": True}, f)

        success, _has_changes, _exit_code = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file=invalid_file,
            quiet=True,
        )

        assert success is False
        captured = capsys.readouterr()
        assert "Invalid snapshot file" in captured.err

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_snapshot_with_banner(self, mock_configure, mock_cjapy, tmp_path, capsys):
        """Non-quiet mode prints comparison banner."""
        mock_configure.return_value = (True, "config", None)
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataView.return_value = {
            "name": "DV",
            "owner": "o",
            "description": "",
        }
        mock_cja.getMetrics.return_value = MagicMock(empty=False, to_dict=MagicMock(return_value=[]))
        mock_cja.getDimensions.return_value = MagicMock(empty=False, to_dict=MagicMock(return_value=[]))

        snap_file = str(tmp_path / "baseline.json")
        _write_snapshot_file(snap_file)

        success, _, _ = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file=snap_file,
            quiet=False,
            quiet_diff=False,
            output_format="console",
            no_color=True,
        )

        assert success is True
        captured = capsys.readouterr()
        assert "COMPARING DATA VIEW AGAINST SNAPSHOT" in captured.out
        assert "dv_test" in captured.out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_snapshot_reverse_diff(self, mock_configure, mock_cjapy, tmp_path, capsys):
        """Reverse diff prints indicator and swaps source/target."""
        mock_configure.return_value = (True, "config", None)
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataView.return_value = {
            "name": "DV",
            "owner": "o",
            "description": "",
        }
        mock_cja.getMetrics.return_value = MagicMock(empty=False, to_dict=MagicMock(return_value=[]))
        mock_cja.getDimensions.return_value = MagicMock(empty=False, to_dict=MagicMock(return_value=[]))

        snap_file = str(tmp_path / "baseline.json")
        _write_snapshot_file(snap_file)

        success, _, _ = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file=snap_file,
            reverse_diff=True,
            quiet=False,
            quiet_diff=False,
            output_format="console",
            no_color=True,
        )

        assert success is True
        captured = capsys.readouterr()
        assert "(Reversed comparison)" in captured.out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_snapshot_missing_inventory(self, mock_configure, mock_cjapy, tmp_path, capsys):
        """Returns failure when requesting inventory diff but snapshot lacks inventory data."""
        mock_configure.return_value = (True, "config", None)

        # Snapshot without inventory data
        snap = _make_snapshot(data_view_id="dv_test")
        snap_file = str(tmp_path / "baseline.json")
        _write_snapshot_file(snap_file, snap)

        success, _, _ = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file=snap_file,
            include_calc_metrics=True,
            quiet=True,
        )

        assert success is False
        captured = capsys.readouterr()
        assert "snapshot missing requested data" in captured.err

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_snapshot_auto_snapshot(self, mock_configure, mock_cjapy, tmp_path, capsys):
        """Auto-snapshot saves current state to snapshot directory."""
        mock_configure.return_value = (True, "config", None)
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataView.return_value = {
            "name": "Test DV",
            "owner": "o",
            "description": "",
        }
        mock_cja.getMetrics.return_value = MagicMock(
            empty=False, to_dict=MagicMock(return_value=[{"id": "m1", "name": "M1"}])
        )
        mock_cja.getDimensions.return_value = MagicMock(empty=False, to_dict=MagicMock(return_value=[]))

        snap_file = str(tmp_path / "baseline.json")
        _write_snapshot_file(snap_file)
        snapshot_dir = str(tmp_path / "auto_snapshots")

        success, _, _ = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file=snap_file,
            auto_snapshot=True,
            snapshot_dir=snapshot_dir,
            quiet=False,
            quiet_diff=False,
            output_format="console",
            no_color=True,
        )

        assert success is True
        assert os.path.isdir(snapshot_dir)

        # Check auto-saved snapshot exists
        files = os.listdir(snapshot_dir)
        assert len(files) >= 1
        assert any(f.endswith(".json") for f in files)

        captured = capsys.readouterr()
        assert "Auto-saved current state" in captured.out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_snapshot_auto_prune(self, mock_configure, mock_cjapy, tmp_path, capsys):
        """Auto-prune with retention deletes old snapshots."""
        mock_configure.return_value = (True, "config", None)
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataView.return_value = {
            "name": "Test DV",
            "owner": "o",
            "description": "",
        }
        mock_cja.getMetrics.return_value = MagicMock(empty=False, to_dict=MagicMock(return_value=[]))
        mock_cja.getDimensions.return_value = MagicMock(empty=False, to_dict=MagicMock(return_value=[]))

        snap_file = str(tmp_path / "baseline.json")
        _write_snapshot_file(snap_file)
        snapshot_dir = str(tmp_path / "auto_snapshots")
        os.makedirs(snapshot_dir)

        # Pre-populate with old snapshots for the same data view
        for i in range(5):
            old_snap = _make_snapshot(
                data_view_id="dv_test",
                created_at=f"2025-01-{10 + i:02d}T00:00:00+00:00",
            )
            old_file = os.path.join(snapshot_dir, f"dv_test_2025010{i}_000000.json")
            _write_snapshot_file(old_file, old_snap)

        success, _, _ = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file=snap_file,
            auto_snapshot=True,
            snapshot_dir=snapshot_dir,
            keep_last=2,
            keep_last_specified=True,
            quiet=False,
            quiet_diff=False,
            output_format="console",
            no_color=True,
        )

        assert success is True
        captured = capsys.readouterr()
        assert "Retention policy" in captured.out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_snapshot_warn_threshold(self, mock_configure, mock_cjapy, tmp_path, capsys):
        """Warn threshold triggers exit code 3."""
        mock_configure.return_value = (True, "config", None)
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataView.return_value = {
            "name": "Test DV",
            "owner": "o",
            "description": "",
        }
        # Return no metrics from live view, but snapshot has many
        mock_cja.getMetrics.return_value = MagicMock(empty=True, to_dict=MagicMock(return_value=[]))
        mock_cja.getDimensions.return_value = MagicMock(empty=True, to_dict=MagicMock(return_value=[]))

        snap = _make_snapshot(
            data_view_id="dv_test",
            metrics=[{"id": f"m{i}", "name": f"M{i}"} for i in range(10)],
            dimensions=[{"id": f"d{i}", "name": f"D{i}"} for i in range(5)],
        )
        snap_file = str(tmp_path / "baseline.json")
        _write_snapshot_file(snap_file, snap)

        success, has_changes, exit_code = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file=snap_file,
            warn_threshold=5.0,
            quiet=True,
            quiet_diff=False,
            output_format="console",
            no_color=True,
        )

        assert success is True
        assert has_changes is True
        assert exit_code == 3

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_snapshot_diff_output_to_file(self, mock_configure, mock_cjapy, tmp_path, capsys):
        """--diff-output writes output to specified file."""
        mock_configure.return_value = (True, "config", None)
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataView.return_value = {
            "name": "Test DV",
            "owner": "o",
            "description": "",
        }
        mock_cja.getMetrics.return_value = MagicMock(
            empty=False, to_dict=MagicMock(return_value=[{"id": "m1", "name": "M1"}])
        )
        mock_cja.getDimensions.return_value = MagicMock(
            empty=False, to_dict=MagicMock(return_value=[{"id": "d1", "name": "D1"}])
        )

        snap_file = str(tmp_path / "baseline.json")
        _write_snapshot_file(snap_file)
        diff_out = str(tmp_path / "diff.txt")

        success, _, _ = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file=snap_file,
            diff_output=diff_out,
            quiet=False,
            quiet_diff=False,
            output_format="console",
            no_color=True,
        )

        assert success is True
        assert os.path.exists(diff_out)
        captured = capsys.readouterr()
        assert "Diff output written to" in captured.out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_snapshot_non_console_format(self, mock_configure, mock_cjapy, tmp_path, capsys):
        """Non-console format shows success message."""
        mock_configure.return_value = (True, "config", None)
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataView.return_value = {
            "name": "DV",
            "owner": "o",
            "description": "",
        }
        mock_cja.getMetrics.return_value = MagicMock(empty=False, to_dict=MagicMock(return_value=[]))
        mock_cja.getDimensions.return_value = MagicMock(empty=False, to_dict=MagicMock(return_value=[]))

        snap_file = str(tmp_path / "baseline.json")
        _write_snapshot_file(snap_file)

        success, _, _ = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file=snap_file,
            quiet=False,
            quiet_diff=False,
            output_format="json",
            output_dir=str(tmp_path),
            no_color=True,
        )

        assert success is True
        captured = capsys.readouterr()
        assert "Diff report generated successfully" in captured.out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_snapshot_inventory_included_in_banner(self, mock_configure, mock_cjapy, tmp_path, capsys):
        """Inventory flags appear in the banner."""
        mock_configure.return_value = (True, "config", None)
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataView.return_value = {
            "name": "DV",
            "owner": "o",
            "description": "",
        }
        mock_cja.getMetrics.return_value = MagicMock(empty=False, to_dict=MagicMock(return_value=[]))
        mock_cja.getDimensions.return_value = MagicMock(empty=False, to_dict=MagicMock(return_value=[]))

        snap = _make_snapshot(
            data_view_id="dv_test",
            calculated_metrics_inventory=[],
            segments_inventory=[],
        )
        snap_file = str(tmp_path / "baseline.json")
        _write_snapshot_file(snap_file, snap)

        success, _, _ = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file=snap_file,
            include_calc_metrics=True,
            include_segments=True,
            quiet=False,
            quiet_diff=False,
            output_format="console",
            no_color=True,
        )

        assert success is True
        captured = capsys.readouterr()
        assert "calculated metrics" in captured.out
        assert "segments" in captured.out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_snapshot_general_exception(self, mock_configure, mock_cjapy, tmp_path, capsys):
        """General exception returns failure tuple."""
        from cja_auto_sdr.core.exceptions import CJASDRError

        mock_configure.return_value = (True, "config", None)
        mock_cjapy.CJA.side_effect = CJASDRError("Unexpected failure")

        snap_file = str(tmp_path / "baseline.json")
        _write_snapshot_file(snap_file)

        success, _has_changes, _exit_code = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file=snap_file,
            quiet=True,
        )

        assert success is False
        captured = capsys.readouterr()
        assert "Failed to compare against snapshot" in captured.err

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_snapshot_constructor_hint_stays_on_stderr(self, mock_configure, mock_cjapy, tmp_path, capsys):
        """Hint-bearing diff-snapshot failures should keep stderr together."""
        mock_configure.return_value = (True, "config", None)
        mock_cjapy.CJA.side_effect = RuntimeError("HTTP 403 Forbidden")

        snap_file = str(tmp_path / "baseline.json")
        _write_snapshot_file(snap_file)

        success, _has_changes, _exit_code = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file=snap_file,
            quiet=True,
        )

        assert success is False
        captured = capsys.readouterr()
        assert "Failed to compare against snapshot: HTTP 403 Forbidden" in captured.err
        assert "authentication or authorization failed" in captured.err

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_snapshot_auto_snapshot_with_date_retention(self, mock_configure, mock_cjapy, tmp_path, capsys):
        """Auto-snapshot with date-based retention (keep_since)."""
        mock_configure.return_value = (True, "config", None)
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataView.return_value = {
            "name": "Test DV",
            "owner": "o",
            "description": "",
        }
        mock_cja.getMetrics.return_value = MagicMock(empty=False, to_dict=MagicMock(return_value=[]))
        mock_cja.getDimensions.return_value = MagicMock(empty=False, to_dict=MagicMock(return_value=[]))

        snap_file = str(tmp_path / "baseline.json")
        _write_snapshot_file(snap_file)
        snapshot_dir = str(tmp_path / "auto_snapshots")

        success, _, _ = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file=snap_file,
            auto_snapshot=True,
            snapshot_dir=snapshot_dir,
            keep_since="7d",
            keep_since_specified=True,
            quiet=True,
            quiet_diff=True,
        )

        assert success is True
        assert os.path.isdir(snapshot_dir)


# ==================== Snapshot name resolution ====================


class TestSnapshotNameResolution:
    """Tests for name resolution in snapshot dispatch paths."""

    @patch("cja_auto_sdr.generator.get_cached_data_views")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_resolve_data_view_id_passthrough(self, mock_configure, mock_cjapy, mock_cache):
        """Data view IDs (starting with dv_) pass through unchanged."""
        mock_configure.return_value = (True, "config", None)
        mock_cjapy.CJA.return_value = MagicMock()
        mock_cache.return_value = [{"id": "dv_12345", "name": "Test DV"}]

        resolved, name_map = resolve_data_view_names(
            ["dv_12345"],
            config_file="config.json",
        )

        assert resolved == ["dv_12345"]
        assert name_map == {}

    @patch("cja_auto_sdr.generator.get_cached_data_views")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_resolve_name_to_id(self, mock_configure, mock_cjapy, mock_cache):
        """Data view name resolves to ID via API lookup."""
        mock_configure.return_value = (True, "config", None)
        mock_cjapy.CJA.return_value = MagicMock()
        mock_cache.return_value = [
            {"id": "dv_found", "name": "Production Analytics"},
            {"id": "dv_other", "name": "Staging Analytics"},
        ]

        resolved, name_map = resolve_data_view_names(
            ["Production Analytics"],
            config_file="config.json",
        )

        assert "dv_found" in resolved
        assert "Production Analytics" in name_map

    @patch("cja_auto_sdr.generator.get_cached_data_views")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_resolve_name_not_found(self, mock_configure, mock_cjapy, mock_cache):
        """Unresolvable name results in empty list."""
        mock_configure.return_value = (True, "config", None)
        mock_cjapy.CJA.return_value = MagicMock()
        mock_cache.return_value = [
            {"id": "dv_1", "name": "Other DV"},
        ]

        resolved, _name_map = resolve_data_view_names(
            ["NonexistentDV"],
            config_file="config.json",
            suggest_similar=False,
        )

        assert "NonexistentDV" not in list(resolved)

    @patch("cja_auto_sdr.generator.get_cached_data_views")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_resolve_multiple_identifiers_mixed(self, mock_configure, mock_cjapy, mock_cache):
        """Mix of IDs and names resolves correctly."""
        mock_configure.return_value = (True, "config", None)
        mock_cjapy.CJA.return_value = MagicMock()
        mock_cache.return_value = [
            {"id": "dv_direct_id", "name": "Direct DV"},
            {"id": "dv_name_resolved", "name": "My DV"},
        ]

        resolved, _name_map = resolve_data_view_names(
            ["dv_direct_id", "My DV"],
            config_file="config.json",
        )

        assert "dv_direct_id" in resolved
        assert "dv_name_resolved" in resolved

    def test_resolve_with_invalid_match_mode(self):
        """Invalid match_mode raises ValueError."""
        with pytest.raises(ValueError, match="Invalid match_mode"):
            resolve_data_view_names(
                ["dv_123"],
                config_file="config.json",
                match_mode="invalid_mode",
            )


# ==================== Main dispatch snapshot paths ====================


class TestMainSnapshotDispatch:
    """Tests for main() dispatch paths for snapshot-related commands."""

    @pytest.fixture(autouse=True)
    def _no_cli_option_scan(self, monkeypatch):
        monkeypatch.setattr("cja_auto_sdr.generator._cli_option_value", lambda *_a, **_kw: None)

    @staticmethod
    def _make_compare_args(**overrides):
        """Build a Namespace with all args main() expects for --compare-snapshots."""
        args = _real_parse_arguments(["--compare-snapshots", "source.json", "target.json", "--quiet"])
        for k, v in overrides.items():
            setattr(args, k, v)
        return args

    @patch("cja_auto_sdr.generator.handle_compare_snapshots_command")
    @patch("cja_auto_sdr.generator.parse_arguments")
    def test_main_compare_snapshots_success_no_changes(self, mock_parse, mock_compare):
        """main() dispatches --compare-snapshots and exits 0 on no changes."""
        from cja_auto_sdr.generator import main

        mock_parse.return_value = self._make_compare_args()
        mock_compare.return_value = (True, False, None)

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0

    @patch("cja_auto_sdr.generator.handle_compare_snapshots_command")
    @patch("cja_auto_sdr.generator.parse_arguments")
    def test_main_compare_snapshots_with_changes(self, mock_parse, mock_compare):
        """main() exits 2 when compare-snapshots detects changes."""
        from cja_auto_sdr.generator import main

        mock_parse.return_value = self._make_compare_args()
        mock_compare.return_value = (True, True, None)

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 2

    @patch("cja_auto_sdr.generator.handle_compare_snapshots_command")
    @patch("cja_auto_sdr.generator.parse_arguments")
    def test_main_compare_snapshots_threshold_exit_3(self, mock_parse, mock_compare):
        """main() exits 3 when warn threshold exceeded."""
        from cja_auto_sdr.generator import main

        mock_parse.return_value = self._make_compare_args(warn_threshold=5.0)
        mock_compare.return_value = (True, True, 3)

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 3

    @patch("cja_auto_sdr.generator.handle_compare_snapshots_command")
    @patch("cja_auto_sdr.generator.parse_arguments")
    def test_main_compare_snapshots_failure_exit_1(self, mock_parse, mock_compare):
        """main() exits 1 when compare-snapshots fails."""
        from cja_auto_sdr.generator import main

        mock_parse.return_value = self._make_compare_args()
        mock_compare.return_value = (False, False, None)

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1

    @patch("cja_auto_sdr.generator.parse_arguments")
    def test_main_compare_snapshots_metrics_dimensions_conflict(self, mock_parse, capsys):
        """main() rejects --metrics-only + --dimensions-only with --compare-snapshots."""
        from cja_auto_sdr.generator import main

        mock_parse.return_value = self._make_compare_args(metrics_only=True, dimensions_only=True)

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Cannot use both --metrics-only and --dimensions-only" in captured.err

    @patch("cja_auto_sdr.generator.parse_arguments")
    def test_main_compare_snapshots_inventory_only_rejected(self, mock_parse, capsys):
        """main() rejects --inventory-only with --compare-snapshots."""
        from cja_auto_sdr.generator import main

        mock_parse.return_value = self._make_compare_args(inventory_only=True)

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "--inventory-only is only available in SDR mode" in captured.err


# ==================== Snapshot dispatch for --snapshot mode ====================


class TestMainSnapshotMode:
    """Tests for main() --snapshot dispatch with name resolution."""

    @pytest.fixture(autouse=True)
    def _no_cli_option_scan(self, monkeypatch):
        monkeypatch.setattr("cja_auto_sdr.generator._cli_option_value", lambda *_a, **_kw: None)

    @staticmethod
    def _make_snapshot_args(**overrides):
        args = _real_parse_arguments(["--snapshot", "./snap.json", "dv_1"])
        for k, v in overrides.items():
            setattr(args, k, v)
        return args

    @patch("cja_auto_sdr.generator.handle_snapshot_command")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.parse_arguments")
    def test_snapshot_requires_one_data_view(self, mock_parse, mock_resolve, mock_handle, capsys):
        """--snapshot with multiple data views exits with error."""
        from cja_auto_sdr.generator import main

        mock_parse.return_value = self._make_snapshot_args(data_views=["dv_1", "dv_2"])

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "--snapshot requires exactly 1 data view" in captured.err

    @patch("cja_auto_sdr.generator.handle_snapshot_command")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.parse_arguments")
    def test_snapshot_include_derived_rejected(self, mock_parse, mock_resolve, mock_handle, capsys):
        """--include-derived with --snapshot is rejected."""
        from cja_auto_sdr.generator import main

        mock_parse.return_value = self._make_snapshot_args(include_derived_inventory=True)

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "--include-derived cannot be used with --snapshot" in captured.err


# ==================== Snapshot dispatch for --diff-snapshot mode ====================


class TestMainDiffSnapshotMode:
    """Tests for main() --diff-snapshot dispatch with name resolution."""

    @pytest.fixture(autouse=True)
    def _no_cli_option_scan(self, monkeypatch):
        monkeypatch.setattr("cja_auto_sdr.generator._cli_option_value", lambda *_a, **_kw: None)

    @staticmethod
    def _make_diff_snap_args(**overrides):
        args = _real_parse_arguments(["--diff-snapshot", "./baseline.json", "dv_1"])
        for k, v in overrides.items():
            setattr(args, k, v)
        return args

    @patch("cja_auto_sdr.generator.handle_diff_snapshot_command")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.parse_arguments")
    def test_diff_snapshot_requires_one_data_view(self, mock_parse, mock_resolve, mock_handle, capsys):
        """--diff-snapshot with multiple data views exits with error."""
        from cja_auto_sdr.generator import main

        mock_parse.return_value = self._make_diff_snap_args(data_views=["dv_1", "dv_2"])

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "--diff-snapshot requires exactly 1 data view" in captured.err

    @patch("cja_auto_sdr.generator.handle_diff_snapshot_command")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.parse_arguments")
    def test_diff_snapshot_metrics_dimensions_conflict(self, mock_parse, mock_resolve, mock_handle, capsys):
        """--metrics-only + --dimensions-only with --diff-snapshot is rejected."""
        from cja_auto_sdr.generator import main

        mock_parse.return_value = self._make_diff_snap_args(metrics_only=True, dimensions_only=True)

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Cannot use both --metrics-only and --dimensions-only" in captured.err

    @patch("cja_auto_sdr.generator.handle_diff_snapshot_command")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.parse_arguments")
    def test_diff_snapshot_inventory_only_rejected(self, mock_parse, mock_resolve, mock_handle, capsys):
        """--inventory-only with --diff-snapshot is rejected."""
        from cja_auto_sdr.generator import main

        mock_parse.return_value = self._make_diff_snap_args(inventory_only=True)

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "--inventory-only is only available in SDR mode" in captured.err

    @patch("cja_auto_sdr.generator.handle_diff_snapshot_command")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.parse_arguments")
    def test_diff_snapshot_name_resolution_failure(self, mock_parse, mock_resolve, mock_handle, capsys):
        """Unresolvable data view name exits with error."""
        from cja_auto_sdr.generator import main

        mock_parse.return_value = self._make_diff_snap_args(data_views=["My DV"])
        mock_resolve.return_value = ([], {})

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Could not resolve data view" in captured.err

    @patch("cja_auto_sdr.generator.prompt_for_selection")
    @patch("cja_auto_sdr.generator.handle_diff_snapshot_command")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.parse_arguments")
    def test_diff_snapshot_ambiguous_name_no_selection(
        self, mock_parse, mock_resolve, mock_handle, mock_prompt, capsys
    ):
        """Ambiguous name resolution with no interactive selection exits with error."""
        from cja_auto_sdr.generator import main

        mock_parse.return_value = self._make_diff_snap_args(data_views=["My DV"])
        mock_resolve.return_value = (["dv_1", "dv_2"], {"My DV": ["dv_1", "dv_2"]})
        mock_prompt.return_value = None

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "ambiguous" in captured.err.lower()

    @patch("cja_auto_sdr.generator.prompt_for_selection")
    @patch("cja_auto_sdr.generator.handle_diff_snapshot_command")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.parse_arguments")
    def test_diff_snapshot_ambiguous_name_selection_succeeds(
        self,
        mock_parse,
        mock_resolve,
        mock_handle,
        mock_prompt,
    ):
        """Ambiguous name resolved via interactive selection."""
        from cja_auto_sdr.generator import main

        mock_parse.return_value = self._make_diff_snap_args(data_views=["My DV"], quiet=True)
        mock_resolve.return_value = (["dv_1", "dv_2"], {"My DV": ["dv_1", "dv_2"]})
        mock_prompt.return_value = "dv_1"
        mock_handle.return_value = (True, False, None)

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 0
        mock_handle.assert_called_once()


# ==================== Compare-with-prev dispatch ====================


class TestMainCompareWithPrevMode:
    """Tests for main() --compare-with-prev dispatch."""

    @pytest.fixture(autouse=True)
    def _no_cli_option_scan(self, monkeypatch):
        monkeypatch.setattr("cja_auto_sdr.generator._cli_option_value", lambda *_a, **_kw: None)

    @staticmethod
    def _make_cwp_args(**overrides):
        args = _real_parse_arguments(["--compare-with-prev", "dv_1"])
        for k, v in overrides.items():
            setattr(args, k, v)
        return args

    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.parse_arguments")
    def test_compare_with_prev_requires_one_data_view(self, mock_parse, mock_resolve, capsys):
        """--compare-with-prev with multiple data views exits with error."""
        from cja_auto_sdr.generator import main

        mock_parse.return_value = self._make_cwp_args(data_views=["dv_1", "dv_2"])

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "--compare-with-prev requires exactly 1 data view" in captured.err

    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.parse_arguments")
    def test_compare_with_prev_inventory_only_rejected(self, mock_parse, mock_resolve, capsys):
        """--inventory-only with --compare-with-prev is rejected."""
        from cja_auto_sdr.generator import main

        mock_parse.return_value = self._make_cwp_args(inventory_only=True)

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "--inventory-only is only available in SDR mode" in captured.err

    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.parse_arguments")
    def test_compare_with_prev_no_previous_snapshot(self, mock_parse, mock_resolve, mock_sm, capsys):
        """No previous snapshot exits with guidance message."""
        from cja_auto_sdr.generator import main

        mock_parse.return_value = self._make_cwp_args()
        mock_resolve.return_value = (["dv_1"], {})
        mock_sm_instance = MagicMock()
        mock_sm.return_value = mock_sm_instance
        mock_sm_instance.get_most_recent_snapshot.return_value = None

        with pytest.raises(SystemExit) as exc_info:
            main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "No previous snapshots found" in captured.err
