"""Tests for CLI command handlers and dispatch functions in generator.py.

Targets uncovered lines in:
- process_inventory_summary (lines 5049-5117)
- handle_diff_command config unpacking (lines 12755-12988)
- handle_diff_snapshot_command (lines 13068-13373)
- _main_impl: --stats handler (lines 13811-13978)
- _main_impl: --org-report routing (lines 13893-14055)
- _main_impl: --list-snapshots (lines 14103-14171)
- _main_impl: --prune-snapshots & more CLI dispatch (lines 14065-14249)
"""

from __future__ import annotations

import json
import logging
import os
from unittest.mock import MagicMock, patch

import pytest

from cja_auto_sdr.core.exceptions import APIError, CJASDRError
from cja_auto_sdr.generator import (
    DiffConfig,
    DiffSnapshotConfig,
    NameResolutionDiagnostics,
    _main_impl,
    handle_diff_command,
    handle_diff_snapshot_command,
    parse_arguments,
    process_inventory_summary,
)


def _mock_cli_option_specified(option_name, argv=None):
    """Stub that always returns False — prevents _known_long_options() from
    calling parse_arguments(return_parser=True) while it is mocked."""
    return False


def _mock_cli_option_specified_for(*option_names):
    """Return a stub that reports only the selected long options as explicit."""
    specified = set(option_names)
    return lambda option_name, argv=None: option_name in specified


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_snapshot(data_view_id="dv_test123", data_view_name="Test DV"):
    """Build a lightweight mock DataViewSnapshot."""
    snap = MagicMock()
    snap.data_view_id = data_view_id
    snap.data_view_name = data_view_name
    snap.created_at = "2025-01-15T10:00:00+00:00"
    snap.metrics = [{"id": "m1", "name": "Metric1"}]
    snap.dimensions = [{"id": "d1", "name": "Dim1"}]
    snap.has_calculated_metrics_inventory = False
    snap.has_segments_inventory = False
    snap.calculated_metrics_inventory = None
    snap.segments_inventory = None
    snap.get_inventory_summary.return_value = {
        "calculated_metrics": {"present": False, "count": 0},
        "segments": {"present": False, "count": 0},
    }
    return snap


def _make_mock_diff_result(has_changes=False):
    """Build a mock DiffResult with summary."""
    result = MagicMock()
    result.summary.has_changes = has_changes
    result.summary.metrics_change_percent = 0.0
    result.summary.dimensions_change_percent = 0.0
    result.metrics_diffs = []
    result.dimensions_diffs = []
    return result


# ==================== process_inventory_summary ====================


class TestProcessInventorySummary:
    """Tests for process_inventory_summary() covering lines 5049-5127."""

    @patch("cja_auto_sdr.generator.display_inventory_summary")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.with_log_context")
    @patch("cja_auto_sdr.generator.setup_logging")
    def test_cja_init_failure_returns_error(self, mock_setup, mock_ctx, mock_init, mock_display):
        """When initialize_cja returns None, function should return error dict."""
        mock_setup.return_value = logging.getLogger("test")
        mock_ctx.return_value = logging.getLogger("test")
        mock_init.return_value = None

        result = process_inventory_summary("dv_test123", config_file="config.json")

        assert "error" in result
        assert result["error"] == "CJA initialization failed"
        mock_display.assert_not_called()

    @patch("cja_auto_sdr.generator.display_inventory_summary")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.with_log_context")
    @patch("cja_auto_sdr.generator.setup_logging")
    def test_data_view_fetch_failure_returns_error(self, mock_setup, mock_ctx, mock_init, mock_display):
        """When cja.dataviews.get_single raises, function should return error dict."""
        mock_setup.return_value = logging.getLogger("test")
        mock_ctx.return_value = logging.getLogger("test")

        mock_cja = MagicMock()
        mock_cja.dataviews.get_single.side_effect = APIError("API Error 404")
        mock_init.return_value = mock_cja

        result = process_inventory_summary("dv_bad_id", config_file="config.json")

        assert "error" in result
        assert "API Error 404" in result["error"]

    @patch("cja_auto_sdr.generator.display_inventory_summary")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.with_log_context")
    @patch("cja_auto_sdr.generator.setup_logging")
    def test_data_view_fetch_transport_failure_returns_error(self, mock_setup, mock_ctx, mock_init, mock_display):
        """Transport failures during data view lookup should return error dict."""
        mock_setup.return_value = logging.getLogger("test")
        mock_ctx.return_value = logging.getLogger("test")

        mock_cja = MagicMock()
        mock_cja.dataviews.get_single.side_effect = ConnectionError("network timeout")
        mock_init.return_value = mock_cja

        result = process_inventory_summary("dv_bad_id", config_file="config.json")

        assert "error" in result
        assert "network timeout" in result["error"]

    @patch("cja_auto_sdr.generator.display_inventory_summary")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.with_log_context")
    @patch("cja_auto_sdr.generator.setup_logging")
    def test_data_view_fetch_unexpected_exception_returns_error(self, mock_setup, mock_ctx, mock_init, mock_display):
        """RuntimeError during data view fetch should return error dict, not traceback."""
        mock_setup.return_value = logging.getLogger("test")
        mock_ctx.return_value = logging.getLogger("test")

        mock_cja = MagicMock()
        mock_cja.dataviews.get_single.side_effect = RuntimeError("unexpected client crash")
        mock_init.return_value = mock_cja

        result = process_inventory_summary("dv_bad_id", config_file="config.json")

        assert "error" in result
        assert "unexpected client crash" in result["error"]

    @patch("cja_auto_sdr.generator.display_inventory_summary")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.with_log_context")
    @patch("cja_auto_sdr.generator.setup_logging")
    def test_successful_fetch_no_inventory(self, mock_setup, mock_ctx, mock_init, mock_display):
        """Successful fetch with no inventory flags returns display_inventory_summary result."""
        mock_setup.return_value = logging.getLogger("test")
        mock_ctx.return_value = logging.getLogger("test")

        mock_cja = MagicMock()
        mock_cja.dataviews.get_single.return_value = {"name": "My DV"}
        mock_init.return_value = mock_cja
        mock_display.return_value = {"total": 0}

        result = process_inventory_summary("dv_test123", config_file="config.json")

        assert result == {"total": 0}
        mock_display.assert_called_once()

    @patch("cja_auto_sdr.generator.display_inventory_summary")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.with_log_context")
    @patch("cja_auto_sdr.generator.setup_logging")
    def test_successful_with_quiet_mode(self, mock_setup, mock_ctx, mock_init, mock_display):
        """Quiet mode should suppress progress output but still return results."""
        mock_setup.return_value = logging.getLogger("test")
        mock_ctx.return_value = logging.getLogger("test")

        mock_cja = MagicMock()
        mock_cja.dataviews.get_single.return_value = {"name": "Quiet DV"}
        mock_init.return_value = mock_cja
        mock_display.return_value = {"status": "ok"}

        result = process_inventory_summary("dv_test123", quiet=True)

        assert result == {"status": "ok"}

    @patch("cja_auto_sdr.generator.display_inventory_summary")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.with_log_context")
    @patch("cja_auto_sdr.generator.setup_logging")
    def test_include_derived_success(self, mock_setup, mock_ctx, mock_init, mock_display):
        """Test include_derived path when import and build succeed."""
        mock_setup.return_value = logging.getLogger("test")
        mock_ctx.return_value = logging.getLogger("test")

        mock_cja = MagicMock()
        mock_cja.dataviews.get_single.return_value = {"name": "DV1"}
        mock_cja.dataviews.get_metrics.return_value = [{"id": "m1"}]
        mock_cja.dataviews.get_dimensions.return_value = [{"id": "d1"}]
        mock_init.return_value = mock_cja
        mock_display.return_value = {"derived": 5}

        mock_builder_cls = MagicMock()
        mock_inventory = MagicMock()
        mock_inventory.total_derived_fields = 5
        mock_builder_cls.return_value.build.return_value = mock_inventory

        with patch.dict(
            "sys.modules",
            {"cja_auto_sdr.inventory.derived_fields": MagicMock(DerivedFieldInventoryBuilder=mock_builder_cls)},
        ):
            result = process_inventory_summary("dv_test123", include_derived=True)

        assert result == {"derived": 5}

    @patch("cja_auto_sdr.generator.display_inventory_summary")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.with_log_context")
    @patch("cja_auto_sdr.generator.setup_logging")
    def test_include_derived_import_failure_logs_warning(self, mock_setup, mock_ctx, mock_init, mock_display):
        """When derived fields import fails, should log warning and continue."""
        logger = logging.getLogger("test")
        mock_setup.return_value = logger
        mock_ctx.return_value = logger

        mock_cja = MagicMock()
        mock_cja.dataviews.get_single.return_value = {"name": "DV1"}
        mock_cja.dataviews.get_metrics.side_effect = APIError("metrics API error")
        mock_init.return_value = mock_cja
        mock_display.return_value = {"ok": True}

        result = process_inventory_summary("dv_test123", include_derived=True)

        # Should still succeed; derived failure is non-fatal
        assert result == {"ok": True}

    @patch("cja_auto_sdr.generator.display_inventory_summary")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.with_log_context")
    @patch("cja_auto_sdr.generator.setup_logging")
    def test_include_calculated_import_failure(self, mock_setup, mock_ctx, mock_init, mock_display):
        """When calculated metrics import fails, should continue gracefully."""
        mock_setup.return_value = logging.getLogger("test")
        mock_ctx.return_value = logging.getLogger("test")

        mock_cja = MagicMock()
        mock_cja.dataviews.get_single.return_value = {"name": "DV1"}
        mock_init.return_value = mock_cja
        mock_display.return_value = {"ok": True}

        # Force import to fail
        with patch.dict(
            "sys.modules",
            {"cja_auto_sdr.inventory.calculated_metrics": None},
        ):
            result = process_inventory_summary("dv_test123", include_calculated=True)

        assert result == {"ok": True}

    @patch("cja_auto_sdr.generator.display_inventory_summary")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.with_log_context")
    @patch("cja_auto_sdr.generator.setup_logging")
    def test_include_calculated_transport_failure(self, mock_setup, mock_ctx, mock_init, mock_display):
        """Transport errors in calculated inventory should be non-fatal."""
        mock_setup.return_value = logging.getLogger("test")
        mock_ctx.return_value = logging.getLogger("test")

        mock_cja = MagicMock()
        mock_cja.dataviews.get_single.return_value = {"name": "DV1"}
        mock_init.return_value = mock_cja
        mock_display.return_value = {"ok": True}

        mock_builder_cls = MagicMock()
        mock_builder_cls.return_value.build.side_effect = ConnectionError("calc transport down")
        with patch.dict(
            "sys.modules",
            {
                "cja_auto_sdr.inventory.calculated_metrics": MagicMock(
                    CalculatedMetricsInventoryBuilder=mock_builder_cls
                )
            },
        ):
            result = process_inventory_summary("dv_test123", include_calculated=True)

        assert result == {"ok": True}
        call_kwargs = mock_display.call_args.kwargs
        assert call_kwargs["calculated_inventory"] is None

    @patch("cja_auto_sdr.generator.display_inventory_summary")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.with_log_context")
    @patch("cja_auto_sdr.generator.setup_logging")
    def test_include_segments_import_failure(self, mock_setup, mock_ctx, mock_init, mock_display):
        """When segments import fails, should continue gracefully."""
        mock_setup.return_value = logging.getLogger("test")
        mock_ctx.return_value = logging.getLogger("test")

        mock_cja = MagicMock()
        mock_cja.dataviews.get_single.return_value = {"name": "DV1"}
        mock_init.return_value = mock_cja
        mock_display.return_value = {"ok": True}

        # Force import to fail
        with patch.dict(
            "sys.modules",
            {"cja_auto_sdr.inventory.segments": None},
        ):
            result = process_inventory_summary("dv_test123", include_segments=True)

        assert result == {"ok": True}

    @patch("cja_auto_sdr.generator.display_inventory_summary")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.with_log_context")
    @patch("cja_auto_sdr.generator.setup_logging")
    def test_include_segments_transport_failure(self, mock_setup, mock_ctx, mock_init, mock_display):
        """Transport errors in segments inventory should be non-fatal."""
        mock_setup.return_value = logging.getLogger("test")
        mock_ctx.return_value = logging.getLogger("test")

        mock_cja = MagicMock()
        mock_cja.dataviews.get_single.return_value = {"name": "DV1"}
        mock_init.return_value = mock_cja
        mock_display.return_value = {"ok": True}

        mock_builder_cls = MagicMock()
        mock_builder_cls.return_value.build.side_effect = ConnectionError("segments transport down")
        with patch.dict(
            "sys.modules",
            {"cja_auto_sdr.inventory.segments": MagicMock(SegmentsInventoryBuilder=mock_builder_cls)},
        ):
            result = process_inventory_summary("dv_test123", include_segments=True)

        assert result == {"ok": True}
        call_kwargs = mock_display.call_args.kwargs
        assert call_kwargs["segments_inventory"] is None

    @pytest.mark.parametrize(
        ("module_name", "builder_attr", "include_kwargs", "summary_key"),
        [
            (
                "cja_auto_sdr.inventory.derived_fields",
                "DerivedFieldInventoryBuilder",
                {"include_derived": True},
                "derived_inventory",
            ),
            (
                "cja_auto_sdr.inventory.calculated_metrics",
                "CalculatedMetricsInventoryBuilder",
                {"include_calculated": True},
                "calculated_inventory",
            ),
            (
                "cja_auto_sdr.inventory.segments",
                "SegmentsInventoryBuilder",
                {"include_segments": True},
                "segments_inventory",
            ),
        ],
    )
    @patch("cja_auto_sdr.generator.display_inventory_summary")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.with_log_context")
    @patch("cja_auto_sdr.generator.setup_logging")
    def test_include_optional_inventory_runtime_failure_non_fatal(
        self,
        mock_setup,
        mock_ctx,
        mock_init,
        mock_display,
        module_name,
        builder_attr,
        include_kwargs,
        summary_key,
    ):
        """Unexpected RuntimeError in optional inventory builders should not abort summary mode."""
        mock_setup.return_value = logging.getLogger("test")
        mock_ctx.return_value = logging.getLogger("test")

        mock_cja = MagicMock()
        mock_cja.dataviews.get_single.return_value = {"name": "DV1"}
        mock_cja.dataviews.get_metrics.return_value = [{"id": "m1"}]
        mock_cja.dataviews.get_dimensions.return_value = [{"id": "d1"}]
        mock_init.return_value = mock_cja
        mock_display.return_value = {"ok": True}

        mock_builder_cls = MagicMock()
        mock_builder_cls.return_value.build.side_effect = RuntimeError("unexpected builder runtime failure")

        with patch.dict(
            "sys.modules",
            {module_name: MagicMock(**{builder_attr: mock_builder_cls})},
        ):
            result = process_inventory_summary("dv_test123", quiet=True, **include_kwargs)

        assert result == {"ok": True}
        call_kwargs = mock_display.call_args.kwargs
        assert call_kwargs[summary_key] is None

    @patch("cja_auto_sdr.generator.display_inventory_summary")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.with_log_context")
    @patch("cja_auto_sdr.generator.setup_logging")
    def test_data_view_lookup_returns_non_dict(self, mock_setup, mock_ctx, mock_init, mock_display):
        """When lookup_data is not a dict, should use data_view_id as name."""
        mock_setup.return_value = logging.getLogger("test")
        mock_ctx.return_value = logging.getLogger("test")

        mock_cja = MagicMock()
        mock_cja.dataviews.get_single.return_value = "not_a_dict"
        mock_init.return_value = mock_cja
        mock_display.return_value = {}

        process_inventory_summary("dv_test123")

        # Should use data_view_id as the name fallback
        call_kwargs = mock_display.call_args
        assert call_kwargs[1]["data_view_name"] == "dv_test123"


# ==================== handle_diff_command ====================


class TestHandleDiffCommand:
    """Tests for handle_diff_command() covering lines 12755-12988."""

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_diff_step_summary")
    @patch("cja_auto_sdr.generator.write_diff_output")
    @patch("cja_auto_sdr.generator.DataViewComparator")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_basic_diff_no_changes(
        self, mock_conf, mock_cjapy, mock_sm_cls, mock_comp_cls, mock_write, mock_build, mock_append
    ):
        """Basic diff with no changes returns (True, False, None)."""
        mock_conf.return_value = (True, "config_path", {})
        mock_cjapy.CJA.return_value = MagicMock()

        mock_sm = MagicMock()
        mock_sm.create_snapshot.return_value = _make_mock_snapshot()
        mock_sm_cls.return_value = mock_sm

        diff_result = _make_mock_diff_result(has_changes=False)
        mock_comp = MagicMock()
        mock_comp.compare.return_value = diff_result
        mock_comp_cls.return_value = mock_comp

        mock_write.return_value = "output text"

        success, has_changes, exit_override = handle_diff_command(
            source_id="dv_source",
            target_id="dv_target",
            quiet=True,
        )

        assert success is True
        assert has_changes is False
        assert exit_override is None

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_diff_step_summary")
    @patch("cja_auto_sdr.generator.write_diff_output")
    @patch("cja_auto_sdr.generator.DataViewComparator")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_with_changes(
        self, mock_conf, mock_cjapy, mock_sm_cls, mock_comp_cls, mock_write, mock_build, mock_append
    ):
        """Diff that finds changes returns has_changes=True."""
        mock_conf.return_value = (True, "config_path", {})
        mock_cjapy.CJA.return_value = MagicMock()

        mock_sm = MagicMock()
        mock_sm.create_snapshot.return_value = _make_mock_snapshot()
        mock_sm_cls.return_value = mock_sm

        diff_result = _make_mock_diff_result(has_changes=True)
        mock_comp = MagicMock()
        mock_comp.compare.return_value = diff_result
        mock_comp_cls.return_value = mock_comp
        mock_write.return_value = "changes output"

        success, has_changes, _ = handle_diff_command(
            source_id="dv_a",
            target_id="dv_b",
            quiet=True,
        )

        assert success is True
        assert has_changes is True

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_diff_step_summary")
    @patch("cja_auto_sdr.generator.write_diff_output")
    @patch("cja_auto_sdr.generator.DataViewComparator")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_config_failure(
        self, mock_conf, mock_cjapy, mock_sm_cls, mock_comp_cls, mock_write, mock_build, mock_append
    ):
        """Configuration failure returns (False, False, None)."""
        mock_conf.return_value = (False, "Bad creds", {})

        success, _has_changes, _exit_override = handle_diff_command(
            source_id="dv_a",
            target_id="dv_b",
            quiet=True,
        )

        assert success is False
        assert _has_changes is False

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_diff_step_summary")
    @patch("cja_auto_sdr.generator.write_diff_output")
    @patch("cja_auto_sdr.generator.DataViewComparator")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_warn_threshold_exceeded(
        self, mock_conf, mock_cjapy, mock_sm_cls, mock_comp_cls, mock_write, mock_build, mock_append
    ):
        """When warn_threshold is exceeded, exit_code_override should be 3."""
        mock_conf.return_value = (True, "config_path", {})
        mock_cjapy.CJA.return_value = MagicMock()

        mock_sm = MagicMock()
        mock_sm.create_snapshot.return_value = _make_mock_snapshot()
        mock_sm_cls.return_value = mock_sm

        diff_result = _make_mock_diff_result(has_changes=True)
        diff_result.summary.metrics_change_percent = 25.0
        diff_result.summary.dimensions_change_percent = 5.0
        mock_comp = MagicMock()
        mock_comp.compare.return_value = diff_result
        mock_comp_cls.return_value = mock_comp
        mock_write.return_value = "output"

        _, _, exit_override = handle_diff_command(
            source_id="dv_a",
            target_id="dv_b",
            warn_threshold=10.0,
            quiet=True,
        )

        assert exit_override == 3

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_diff_step_summary")
    @patch("cja_auto_sdr.generator.write_diff_output")
    @patch("cja_auto_sdr.generator.DataViewComparator")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_reverse_swaps_ids(
        self, mock_conf, mock_cjapy, mock_sm_cls, mock_comp_cls, mock_write, mock_build, mock_append
    ):
        """Reverse diff should swap source and target."""
        mock_conf.return_value = (True, "config_path", {})
        mock_cjapy.CJA.return_value = MagicMock()

        source_snap = _make_mock_snapshot("dv_source", "Source")
        target_snap = _make_mock_snapshot("dv_target", "Target")

        mock_sm = MagicMock()
        # First call -> source snapshot, second -> target snapshot
        mock_sm.create_snapshot.side_effect = [source_snap, target_snap]
        mock_sm_cls.return_value = mock_sm

        diff_result = _make_mock_diff_result()
        mock_comp = MagicMock()
        mock_comp.compare.return_value = diff_result
        mock_comp_cls.return_value = mock_comp
        mock_write.return_value = ""

        handle_diff_command(
            source_id="dv_source",
            target_id="dv_target",
            reverse_diff=True,
            quiet=True,
        )

        # Verify compare was called (reverse should have swapped the IDs before snapshot creation)
        mock_comp.compare.assert_called_once()

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_diff_step_summary")
    @patch("cja_auto_sdr.generator.write_diff_output")
    @patch("cja_auto_sdr.generator.DataViewComparator")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_quiet_diff_suppresses_output(
        self, mock_conf, mock_cjapy, mock_sm_cls, mock_comp_cls, mock_write, mock_build, mock_append
    ):
        """quiet_diff=True should skip write_diff_output."""
        mock_conf.return_value = (True, "config_path", {})
        mock_cjapy.CJA.return_value = MagicMock()

        mock_sm = MagicMock()
        mock_sm.create_snapshot.return_value = _make_mock_snapshot()
        mock_sm_cls.return_value = mock_sm

        diff_result = _make_mock_diff_result()
        mock_comp = MagicMock()
        mock_comp.compare.return_value = diff_result
        mock_comp_cls.return_value = mock_comp

        handle_diff_command(
            source_id="dv_a",
            target_id="dv_b",
            quiet_diff=True,
            quiet=True,
        )

        mock_write.assert_not_called()

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_diff_step_summary")
    @patch("cja_auto_sdr.generator.write_diff_output")
    @patch("cja_auto_sdr.generator.DataViewComparator")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_with_diff_output_writes_to_file(
        self, mock_conf, mock_cjapy, mock_sm_cls, mock_comp_cls, mock_write, mock_build, mock_append, tmp_path
    ):
        """--diff-output should write content to specified file."""
        mock_conf.return_value = (True, "config_path", {})
        mock_cjapy.CJA.return_value = MagicMock()

        mock_sm = MagicMock()
        mock_sm.create_snapshot.return_value = _make_mock_snapshot()
        mock_sm_cls.return_value = mock_sm

        diff_result = _make_mock_diff_result()
        mock_comp = MagicMock()
        mock_comp.compare.return_value = diff_result
        mock_comp_cls.return_value = mock_comp
        mock_write.return_value = "diff content here"

        diff_file = str(tmp_path / "out.txt")

        handle_diff_command(
            source_id="dv_a",
            target_id="dv_b",
            diff_output=diff_file,
            quiet=True,
        )

        assert os.path.isfile(diff_file)
        with open(diff_file) as f:
            assert f.read() == "diff content here"

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_diff_step_summary")
    @patch("cja_auto_sdr.generator.write_diff_output")
    @patch("cja_auto_sdr.generator.DataViewComparator")
    @patch("cja_auto_sdr.generator.resolve_auto_prune_retention")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_auto_snapshot_saves(
        self,
        mock_conf,
        mock_cjapy,
        mock_sm_cls,
        mock_retention,
        mock_comp_cls,
        mock_write,
        mock_build,
        mock_append,
        tmp_path,
    ):
        """auto_snapshot=True should save snapshots to snapshot_dir."""
        mock_conf.return_value = (True, "config_path", {})
        mock_cjapy.CJA.return_value = MagicMock()

        mock_sm = MagicMock()
        mock_sm.create_snapshot.return_value = _make_mock_snapshot()
        mock_sm.generate_snapshot_filename.return_value = "snap_file.json"
        mock_sm_cls.return_value = mock_sm

        mock_retention.return_value = (0, None)

        diff_result = _make_mock_diff_result()
        mock_comp = MagicMock()
        mock_comp.compare.return_value = diff_result
        mock_comp_cls.return_value = mock_comp
        mock_write.return_value = ""

        snap_dir = str(tmp_path / "snaps")

        handle_diff_command(
            source_id="dv_a",
            target_id="dv_b",
            auto_snapshot=True,
            snapshot_dir=snap_dir,
            quiet=True,
        )

        assert mock_sm.save_snapshot.call_count == 2  # Source + target

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_exception_returns_false(self, mock_conf, mock_cjapy):
        """General exception during diff returns (False, False, None)."""
        mock_conf.return_value = (True, "config_path", {})
        mock_cjapy.CJA.side_effect = CJASDRError("Unexpected boom")

        success, has_changes, exit_override = handle_diff_command(
            source_id="dv_a",
            target_id="dv_b",
            quiet=True,
        )

        assert success is False
        assert has_changes is False
        assert exit_override is None

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_plain_exception_returns_false(self, mock_conf, mock_cjapy):
        """Bare dependency exceptions should be converted to controlled diff failures."""
        mock_conf.return_value = (True, "config_path", {})
        mock_cjapy.CJA.side_effect = Exception("auth bootstrap failed")

        success, has_changes, exit_override = handle_diff_command(
            source_id="dv_a",
            target_id="dv_b",
            quiet=True,
        )

        assert success is False
        assert has_changes is False
        assert exit_override is None

    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_snapshot_value_error_returns_false(self, mock_conf, mock_cjapy, mock_sm_cls, capsys):
        """ValueError during snapshot fetch should be handled as a diff failure."""
        mock_conf.return_value = (True, "config_path", {})
        mock_cjapy.CJA.return_value = MagicMock()

        mock_sm = MagicMock()
        mock_sm.create_snapshot.side_effect = ValueError("data view not found")
        mock_sm_cls.return_value = mock_sm

        success, has_changes, exit_override = handle_diff_command(
            source_id="dv_missing",
            target_id="dv_target",
            quiet=True,
        )

        assert success is False
        assert has_changes is False
        assert exit_override is None
        assert "Failed to compare data views" in capsys.readouterr().err

    def test_diff_config_dataclass_unpacking(self):
        """DiffConfig is correctly unpacked into local vars in handle_diff_command."""
        config = DiffConfig(
            source_id="dv_src",
            target_id="dv_tgt",
            quiet=True,
            quiet_diff=True,
            labels=("Before", "After"),
        )

        with patch("cja_auto_sdr.generator.configure_cjapy") as mock_conf:
            mock_conf.return_value = (False, "fail", {})

            success, _, _ = handle_diff_command(
                source_id="ignored",
                target_id="ignored",
                diff_config=config,
            )

        assert success is False

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_diff_step_summary")
    @patch("cja_auto_sdr.generator.write_diff_output")
    @patch("cja_auto_sdr.generator.DataViewComparator")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_format_pr_comment(
        self, mock_conf, mock_cjapy, mock_sm_cls, mock_comp_cls, mock_write, mock_build, mock_append
    ):
        """format_pr_comment=True should set effective format to 'pr-comment'."""
        mock_conf.return_value = (True, "config_path", {})
        mock_cjapy.CJA.return_value = MagicMock()

        mock_sm = MagicMock()
        mock_sm.create_snapshot.return_value = _make_mock_snapshot()
        mock_sm_cls.return_value = mock_sm

        diff_result = _make_mock_diff_result()
        mock_comp = MagicMock()
        mock_comp.compare.return_value = diff_result
        mock_comp_cls.return_value = mock_comp
        mock_write.return_value = "pr output"

        handle_diff_command(
            source_id="dv_a",
            target_id="dv_b",
            format_pr_comment=True,
            quiet=True,
        )

        # write_diff_output should receive "pr-comment" as format
        call_args = mock_write.call_args
        assert call_args[0][1] == "pr-comment"

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_diff_step_summary")
    @patch("cja_auto_sdr.generator.write_diff_output")
    @patch("cja_auto_sdr.generator.DataViewComparator")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_with_labels(
        self, mock_conf, mock_cjapy, mock_sm_cls, mock_comp_cls, mock_write, mock_build, mock_append
    ):
        """Custom labels are passed through to comparator."""
        mock_conf.return_value = (True, "config_path", {})
        mock_cjapy.CJA.return_value = MagicMock()

        mock_sm = MagicMock()
        mock_sm.create_snapshot.return_value = _make_mock_snapshot()
        mock_sm_cls.return_value = mock_sm

        diff_result = _make_mock_diff_result()
        mock_comp = MagicMock()
        mock_comp.compare.return_value = diff_result
        mock_comp_cls.return_value = mock_comp
        mock_write.return_value = ""

        handle_diff_command(
            source_id="dv_a",
            target_id="dv_b",
            labels=("Prod", "Staging"),
            quiet=True,
        )

        compare_call = mock_comp.compare.call_args
        assert compare_call[0][2] == "Prod"
        assert compare_call[0][3] == "Staging"

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_diff_step_summary")
    @patch("cja_auto_sdr.generator.write_diff_output")
    @patch("cja_auto_sdr.generator.DataViewComparator")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_diff_non_console_format_prints_success(
        self, mock_conf, mock_cjapy, mock_sm_cls, mock_comp_cls, mock_write, mock_build, mock_append, capsys
    ):
        """Non-console output format should print success message when not quiet."""
        mock_conf.return_value = (True, "config_path", {})
        mock_cjapy.CJA.return_value = MagicMock()

        mock_sm = MagicMock()
        mock_sm.create_snapshot.return_value = _make_mock_snapshot()
        mock_sm_cls.return_value = mock_sm

        diff_result = _make_mock_diff_result()
        mock_comp = MagicMock()
        mock_comp.compare.return_value = diff_result
        mock_comp_cls.return_value = mock_comp
        mock_write.return_value = ""

        handle_diff_command(
            source_id="dv_a",
            target_id="dv_b",
            output_format="json",
            quiet=False,
        )

        captured = capsys.readouterr()
        assert "Diff report generated successfully" in captured.out


# ==================== handle_diff_snapshot_command ====================


class TestHandleDiffSnapshotCommand:
    """Tests for handle_diff_snapshot_command() covering lines 13068-13373."""

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_diff_step_summary")
    @patch("cja_auto_sdr.generator.write_diff_output")
    @patch("cja_auto_sdr.generator.DataViewComparator")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_basic_snapshot_diff(
        self, mock_conf, mock_cjapy, mock_sm_cls, mock_comp_cls, mock_write, mock_build, mock_append
    ):
        """Basic diff against snapshot succeeds."""
        mock_conf.return_value = (True, "config_path", {})
        mock_cjapy.CJA.return_value = MagicMock()

        source_snap = _make_mock_snapshot()
        target_snap = _make_mock_snapshot("dv_live", "Live")

        mock_sm = MagicMock()
        mock_sm.load_snapshot.return_value = source_snap
        mock_sm.create_snapshot.return_value = target_snap
        mock_sm_cls.return_value = mock_sm

        diff_result = _make_mock_diff_result()
        mock_comp = MagicMock()
        mock_comp.compare.return_value = diff_result
        mock_comp_cls.return_value = mock_comp
        mock_write.return_value = ""

        success, has_changes, exit_code = handle_diff_snapshot_command(
            data_view_id="dv_live",
            snapshot_file="snapshot.json",
            quiet=True,
        )

        assert success is True
        assert has_changes is False
        assert exit_code is None

    @patch("cja_auto_sdr.generator.SnapshotManager")
    def test_snapshot_file_not_found(self, mock_sm_cls):
        """Missing snapshot file returns (False, False, None)."""
        mock_sm = MagicMock()
        mock_sm.load_snapshot.side_effect = FileNotFoundError("not found")
        mock_sm_cls.return_value = mock_sm

        success, _has_changes, _exit_code = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file="missing.json",
            quiet=True,
        )

        assert success is False

    @patch("cja_auto_sdr.generator.SnapshotManager")
    def test_invalid_snapshot_file(self, mock_sm_cls):
        """Invalid snapshot file (ValueError) returns (False, False, None)."""
        mock_sm = MagicMock()
        mock_sm.load_snapshot.side_effect = ValueError("corrupt snapshot")
        mock_sm_cls.return_value = mock_sm

        success, _, _ = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file="bad.json",
            quiet=True,
        )

        assert success is False

    @patch("cja_auto_sdr.generator.SnapshotManager")
    def test_missing_inventory_blocks_diff(self, mock_sm_cls, capsys):
        """Requesting calc metrics from snapshot that lacks them returns failure."""
        snap = _make_mock_snapshot()
        snap.has_calculated_metrics_inventory = False
        snap.has_segments_inventory = False

        mock_sm = MagicMock()
        mock_sm.load_snapshot.return_value = snap
        mock_sm_cls.return_value = mock_sm

        success, _, _ = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file="snap.json",
            include_calc_metrics=True,
            quiet=True,
        )

        assert success is False
        captured = capsys.readouterr()
        assert "snapshot missing requested data" in captured.err

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_diff_step_summary")
    @patch("cja_auto_sdr.generator.write_diff_output")
    @patch("cja_auto_sdr.generator.DataViewComparator")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_snapshot_diff_config_failure(
        self, mock_conf, mock_cjapy, mock_sm_cls, mock_comp_cls, mock_write, mock_build, mock_append
    ):
        """Config failure in snapshot diff returns (False, False, None)."""
        source_snap = _make_mock_snapshot()

        mock_sm = MagicMock()
        mock_sm.load_snapshot.return_value = source_snap
        mock_sm_cls.return_value = mock_sm

        mock_conf.return_value = (False, "Bad config", {})

        success, _, _ = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file="snap.json",
            quiet=True,
        )

        assert success is False

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_diff_step_summary")
    @patch("cja_auto_sdr.generator.write_diff_output")
    @patch("cja_auto_sdr.generator.DataViewComparator")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_snapshot_diff_with_warn_threshold(
        self, mock_conf, mock_cjapy, mock_sm_cls, mock_comp_cls, mock_write, mock_build, mock_append
    ):
        """Warn threshold exceeded returns exit_code=3."""
        mock_conf.return_value = (True, "config_path", {})
        mock_cjapy.CJA.return_value = MagicMock()

        source_snap = _make_mock_snapshot()
        target_snap = _make_mock_snapshot("dv_live", "Live")

        mock_sm = MagicMock()
        mock_sm.load_snapshot.return_value = source_snap
        mock_sm.create_snapshot.return_value = target_snap
        mock_sm_cls.return_value = mock_sm

        diff_result = _make_mock_diff_result(has_changes=True)
        diff_result.summary.metrics_change_percent = 50.0
        mock_comp = MagicMock()
        mock_comp.compare.return_value = diff_result
        mock_comp_cls.return_value = mock_comp
        mock_write.return_value = ""

        _, _, exit_code = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file="snap.json",
            warn_threshold=10.0,
            quiet=True,
        )

        assert exit_code == 3

    def test_diff_snapshot_config_dataclass_unpacking(self):
        """DiffSnapshotConfig is correctly unpacked in handle_diff_snapshot_command."""
        config = DiffSnapshotConfig(
            data_view_id="dv_test",
            snapshot_file="snap.json",
            quiet=True,
            quiet_diff=True,
        )

        with patch("cja_auto_sdr.generator.SnapshotManager") as mock_sm_cls:
            mock_sm = MagicMock()
            mock_sm.load_snapshot.side_effect = FileNotFoundError("nope")
            mock_sm_cls.return_value = mock_sm

            success, _, _ = handle_diff_snapshot_command(
                data_view_id="ignored",
                snapshot_file="ignored",
                diff_snapshot_config=config,
            )

        assert success is False

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_diff_step_summary")
    @patch("cja_auto_sdr.generator.write_diff_output")
    @patch("cja_auto_sdr.generator.DataViewComparator")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_snapshot_diff_reverse(
        self, mock_conf, mock_cjapy, mock_sm_cls, mock_comp_cls, mock_write, mock_build, mock_append
    ):
        """reverse_diff=True should swap source and target snapshots."""
        mock_conf.return_value = (True, "config_path", {})
        mock_cjapy.CJA.return_value = MagicMock()

        source_snap = _make_mock_snapshot("dv_snap", "Snap")
        target_snap = _make_mock_snapshot("dv_live", "Live")

        mock_sm = MagicMock()
        mock_sm.load_snapshot.return_value = source_snap
        mock_sm.create_snapshot.return_value = target_snap
        mock_sm_cls.return_value = mock_sm

        diff_result = _make_mock_diff_result()
        mock_comp = MagicMock()
        mock_comp.compare.return_value = diff_result
        mock_comp_cls.return_value = mock_comp
        mock_write.return_value = ""

        handle_diff_snapshot_command(
            data_view_id="dv_live",
            snapshot_file="snap.json",
            reverse_diff=True,
            quiet=True,
        )

        # After reverse, target_snap becomes source and source_snap becomes target
        compare_call = mock_comp.compare.call_args
        assert compare_call[0][0] == target_snap
        assert compare_call[0][1] == source_snap

    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_snapshot_diff_general_exception(self, mock_conf, mock_cjapy, mock_sm_cls):
        """General exception returns (False, False, None)."""
        source_snap = _make_mock_snapshot()

        mock_sm = MagicMock()
        mock_sm.load_snapshot.return_value = source_snap
        mock_sm_cls.return_value = mock_sm

        mock_conf.return_value = (True, "config_path", {})
        mock_cjapy.CJA.side_effect = CJASDRError("unexpected")

        success, _has_changes, _ = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file="snap.json",
            quiet=True,
        )

        assert success is False


# ==================== _main_impl: --profile-add / --profile-test / --profile-show ====================


class TestMainImplProfileCommands:
    """Tests for profile commands in _main_impl (lines 13810-13828)."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.add_profile_interactive")
    def test_profile_add_dispatches_and_tracks_run_state(self, mock_add):
        mock_add.return_value = True
        run_state = {"mode": "unknown", "details": {}}

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--profile-add", "new_profile"])
                _main_impl(run_state=run_state)

        assert exc_info.value.code == 0
        mock_add.assert_called_once_with("new_profile")
        assert run_state["details"]["operation_success"] is True

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.add_profile_interactive")
    def test_profile_add_failure_exits_one(self, mock_add):
        mock_add.return_value = False

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--profile-add", "bad_profile"])
                _main_impl()

        assert exc_info.value.code == 1

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.test_profile")
    def test_profile_test_tracks_run_state(self, mock_test):
        mock_test.return_value = True
        run_state = {"mode": "unknown", "details": {}}

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--profile-test", "myprof"])
                _main_impl(run_state=run_state)

        assert exc_info.value.code == 0
        assert run_state["details"]["operation_success"] is True

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.show_profile")
    def test_profile_show_tracks_run_state(self, mock_show):
        mock_show.return_value = True
        run_state = {"mode": "unknown", "details": {}}

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--profile-show", "myprof"])
                _main_impl(run_state=run_state)

        assert exc_info.value.code == 0
        assert run_state["details"]["operation_success"] is True


# ==================== _main_impl: --git-init ====================


class TestMainImplGitInit:
    """Tests for --git-init dispatch in _main_impl (lines 13831-13847)."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.git_init_snapshot_repo")
    def test_git_init_success(self, mock_git_init, capsys):
        mock_git_init.return_value = (True, "Repository initialized")
        run_state = {"mode": "unknown", "details": {}}

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--git-init"])
                _main_impl(run_state=run_state)

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "SUCCESS: Repository initialized" in captured.out

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.git_init_snapshot_repo")
    def test_git_init_failure(self, mock_git_init, capsys):
        mock_git_init.return_value = (False, "Directory not empty")
        run_state = {"mode": "unknown", "details": {}}

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--git-init"])
                _main_impl(run_state=run_state)

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "FAILED" in captured.out


# ==================== _main_impl: --git-push without --git-commit ====================


class TestMainImplGitPushValidation:
    """Tests for git argument validation (lines 13850-13852)."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_git_push_without_commit_errors(self):
        """--git-push without --git-commit should exit 1."""
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["dv_test123"])
                args.git_push = True
                args.git_commit = False
                mock_pa.return_value = args
                _main_impl()

        assert exc_info.value.code == 1


# ==================== _main_impl: discovery format routing (line 13874) ====================


class TestMainImplDiscoveryFormatRouting:
    """Tests for discovery command output format logic (lines 13868-13888)."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_dataviews")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_discovery_stdout_forces_json(self, _mock_conf, mock_list_dv):
        """When output is stdout, discovery format should default to json."""
        mock_list_dv.return_value = True
        run_state = {"mode": "unknown", "details": {}}

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--list-dataviews", "--output", "-"])
                mock_pa.return_value = args
                _main_impl(run_state=run_state)

        assert exc_info.value.code == 0
        assert run_state["output_format"] == "json"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_dataviews")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_discovery_stdout_preserves_explicit_csv(self, _mock_conf, mock_list_dv):
        """Explicit csv format should be preserved for stdout discovery commands."""
        mock_list_dv.return_value = True
        run_state = {"mode": "unknown", "details": {}}

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--list-dataviews", "--format", "csv", "--output", "-"])
                _main_impl(run_state=run_state)

        assert exc_info.value.code == 0
        assert run_state["output_format"] == "csv"
        assert mock_list_dv.call_args.kwargs["output_format"] == "csv"
        assert mock_list_dv.call_args.kwargs["output_file"] == "-"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_dataviews")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_discovery_stdout_unsupported_format_warns_and_defaults_to_json(
        self, _mock_conf, mock_list_dv, caplog: pytest.LogCaptureFixture
    ):
        """Unsupported stdout format should warn and fall back to json."""
        mock_list_dv.return_value = True
        run_state = {"mode": "unknown", "details": {}}

        with caplog.at_level(logging.WARNING, logger="cja_auto_sdr.generator"):
            with pytest.raises(SystemExit) as exc_info:
                with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                    mock_pa.return_value = parse_arguments(["--list-dataviews", "--format", "excel", "--output", "-"])
                    _main_impl(run_state=run_state)

        assert exc_info.value.code == 0
        assert run_state["output_format"] == "json"
        assert mock_list_dv.call_args.kwargs["output_format"] == "json"
        assert "using json" in caplog.text


# ==================== _main_impl: --config-status / --validate-config ====================


class TestMainImplConfigCommands:
    """Tests for --config-status and --validate-config (lines 13892-13904)."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.show_config_status")
    def test_config_status_dispatches(self, mock_show):
        mock_show.return_value = True
        run_state = {"mode": "unknown", "details": {}}

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--config-status"])
                _main_impl(run_state=run_state)

        assert exc_info.value.code == 0
        mock_show.assert_called_once()

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.validate_config_only")
    def test_validate_config_dispatches(self, mock_validate):
        mock_validate.return_value = True

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--validate-config"])
                _main_impl()

        assert exc_info.value.code == 0

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.validate_config_only")
    def test_validate_config_failure_exits_one(self, mock_validate):
        mock_validate.return_value = False

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--validate-config"])
                _main_impl()

        assert exc_info.value.code == 1


# ==================== _main_impl: --stats ====================


class TestMainImplStats:
    """Tests for --stats handler in _main_impl (lines 13937-13978)."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.show_stats")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_stats_success(self, mock_resolve, mock_stats):
        mock_resolve.return_value = (["dv_resolved"], {})
        mock_stats.return_value = True
        run_state = {"mode": "unknown", "details": {}}

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--stats", "dv_test123"])
                _main_impl(run_state=run_state)

        assert exc_info.value.code == 0
        assert run_state["details"]["operation_success"] is True
        assert run_state["output_format"] == "table"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.show_stats")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_stats_failure_exits_one(self, mock_resolve, mock_stats):
        mock_resolve.return_value = (["dv_resolved"], {})
        mock_stats.return_value = False

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--stats", "dv_test123"])
                _main_impl()

        assert exc_info.value.code == 1

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_stats_no_resolved_ids_exits_one(self, mock_resolve):
        """When name resolution finds nothing, should exit 1."""
        mock_resolve.return_value = ([], {})

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--stats", "nonexistent_dv"])
                _main_impl()

        assert exc_info.value.code == 1

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_stats_no_data_views_exits_one(self):
        """--stats without data views should exit 1."""
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--stats"])
                _main_impl()

        assert exc_info.value.code == 1

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.show_stats")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_stats_json_format(self, mock_resolve, mock_stats):
        mock_resolve.return_value = (["dv_test"], {})
        mock_stats.return_value = True
        run_state = {"mode": "unknown", "details": {}}

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--stats", "--format", "json", "dv_test"])
                _main_impl(run_state=run_state)

        assert exc_info.value.code == 0
        assert run_state["output_format"] == "json"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.show_stats")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_stats_stdout_forces_json(self, mock_resolve, mock_stats):
        """--output stdout should force json format for stats."""
        mock_resolve.return_value = (["dv_test"], {})
        mock_stats.return_value = True
        run_state = {"mode": "unknown", "details": {}}

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--stats", "--output", "-", "dv_test"])
                _main_impl(run_state=run_state)

        assert exc_info.value.code == 0
        assert run_state["output_format"] == "json"


# ==================== _main_impl: --org-report ====================


class TestMainImplOrgReport:
    """Tests for --org-report routing in _main_impl (lines 13981-14055)."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.run_org_report")
    def test_org_report_success(self, mock_org):
        mock_org.return_value = (True, False)
        run_state = {"mode": "unknown", "details": {}}

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--org-report"])
                _main_impl(run_state=run_state)

        assert exc_info.value.code == 0
        assert run_state["details"]["operation_success"] is True
        assert run_state["details"]["thresholds_exceeded"] is False

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.run_org_report")
    def test_org_report_failure_exits_one(self, mock_org):
        mock_org.return_value = (False, False)

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--org-report"])
                _main_impl()

        assert exc_info.value.code == 1

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.run_org_report")
    def test_org_report_thresholds_exceeded_without_fail(self, mock_org):
        """Thresholds exceeded without --fail-on-threshold should exit 0."""
        mock_org.return_value = (True, True)

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--org-report"])
                _main_impl()

        assert exc_info.value.code == 0

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.run_org_report")
    def test_org_report_thresholds_exceeded_with_fail(self, mock_org):
        """Thresholds exceeded with --fail-on-threshold should exit 2."""
        mock_org.return_value = (True, True)

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--org-report", "--fail-on-threshold"])
                _main_impl()

        assert exc_info.value.code == 2

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.run_org_report")
    def test_org_report_with_json_format(self, mock_org):
        mock_org.return_value = (True, False)
        run_state = {"mode": "unknown", "details": {}}

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--org-report", "--format", "json"])
                _main_impl(run_state=run_state)

        assert exc_info.value.code == 0
        assert run_state["output_format"] == "json"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.run_org_report")
    def test_org_report_builds_config_with_filter(self, mock_org):
        """OrgReportConfig should receive filter_pattern from args."""
        mock_org.return_value = (True, False)

        with pytest.raises(SystemExit):
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--org-report", "--filter", "prod.*"])
                _main_impl()

        # Verify org_config passed to run_org_report
        call_kwargs = mock_org.call_args[1]
        assert call_kwargs["org_config"].filter_pattern == "prod.*"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_dataviews")
    def test_trending_window_requires_org_report_mode(self, mock_list_dataviews, capsys):
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--list-dataviews", "--trending-window", "5"])
                _main_impl(run_state={})

        assert exc_info.value.code == 1
        assert "--trending-window is only supported with --org-report" in capsys.readouterr().err
        mock_list_dataviews.assert_not_called()


class TestMainImplOrgReportSnapshots:
    """Tests for dedicated org-report snapshot inspection/listing/pruning commands."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.OrgReportCache")
    def test_list_org_report_snapshots_json_output(self, mock_cache_cls):
        mock_cache = MagicMock()
        mock_cache.list_org_report_snapshots.return_value = [
            {
                "org_id": "test_org@AdobeOrg",
                "generated_at": "2026-03-01T00:00:00Z",
                "data_views_total": 4,
                "total_unique_components": 12,
                "core_count": 8,
                "isolated_count": 4,
                "high_similarity_pairs": 1,
                "filepath": "/tmp/report.json",
            }
        ]
        mock_cache.get_org_report_snapshot_root_dir.return_value = "/tmp/org_report_snapshots"
        mock_cache_cls.return_value = mock_cache

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--list-org-report-snapshots", "--format", "json"])
                _main_impl()

        assert exc_info.value.code == 0

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator._emit_output")
    @patch("cja_auto_sdr.generator.OrgReportCache")
    def test_list_org_report_snapshots_table_output_preserves_snapshot_path(self, mock_cache_cls, mock_emit):
        mock_cache = MagicMock()
        nested_snapshot = "/tmp/org_report_snapshots/3a/9f/org_report_test_org_20260301_abcd1234.json"
        mock_cache.list_org_report_snapshots.return_value = [
            {
                "org_id": "test_org@AdobeOrg",
                "generated_at": "2026-03-01T00:00:00Z",
                "data_views_total": 4,
                "total_unique_components": 12,
                "core_count": 8,
                "isolated_count": 4,
                "high_similarity_pairs": 1,
                "filepath": nested_snapshot,
            }
        ]
        mock_cache.get_org_report_snapshot_root_dir.return_value = "/tmp/org_report_snapshots"
        mock_cache_cls.return_value = mock_cache

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--list-org-report-snapshots"])
                _main_impl()

        assert exc_info.value.code == 0
        emitted = mock_emit.call_args[0][0]
        assert "Snapshot Path" in emitted
        assert nested_snapshot in emitted.replace("\n", "").replace(" ", "")

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator._emit_output")
    @patch("cja_auto_sdr.generator.OrgReportCache")
    def test_list_org_report_snapshots_csv_output_includes_history_metadata(self, mock_cache_cls, mock_emit):
        mock_cache = MagicMock()
        mock_cache.list_org_report_snapshots.return_value = [
            {
                "org_id": "test_org@AdobeOrg",
                "generated_at": "2026-03-01T00:00:00Z",
                "data_views_total": 4,
                "total_unique_components": 12,
                "core_count": 8,
                "isolated_count": 4,
                "high_similarity_pairs": 1,
                "history_eligible": False,
                "history_exclusion_reason": "org_stats_only",
                "filepath": "/tmp/report.json",
            }
        ]
        mock_cache_cls.return_value = mock_cache

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--list-org-report-snapshots", "--format", "csv"])
                _main_impl()

        assert exc_info.value.code == 0
        emitted = mock_emit.call_args[0][0]
        assert "history_eligible" in emitted
        assert "history_exclusion_reason" in emitted
        assert "org_stats_only" in emitted

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator._emit_output")
    @patch("cja_auto_sdr.generator.OrgReportCache")
    def test_inspect_org_report_snapshot_table_output(self, mock_cache_cls, mock_emit):
        mock_cache = MagicMock()
        mock_cache.inspect_org_report_snapshot.return_value = {
            "org_id": "test_org@AdobeOrg",
            "generated_at": "2026-03-01T00:00:00Z",
            "data_views_total": 4,
            "total_unique_components": 12,
            "core_count": 8,
            "isolated_count": 4,
            "high_similarity_pairs": 1,
            "history_eligible": False,
            "history_exclusion_reason": "org_stats_only",
            "filepath": "/tmp/report.json",
            "data_view_names_preview": ["Orders", "Visitors"],
            "data_view_names_total": 2,
            "data_view_names_truncated": False,
        }
        mock_cache_cls.return_value = mock_cache

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--inspect-org-report-snapshot", "/tmp/report.json"])
                _main_impl()

        assert exc_info.value.code == 0
        emitted = mock_emit.call_args[0][0]
        assert "Org-Report Snapshot" in emitted
        assert "History eligible:     False" in emitted
        assert "History exclusion:    org_stats_only" in emitted
        assert "Orders" in emitted

    @patch("cja_auto_sdr.generator.OrgReportCache")
    def test_prune_org_report_snapshots_json_output(self, mock_cache_cls):
        mock_cache = MagicMock()
        mock_cache.prune_org_report_snapshots.return_value = ["/tmp/old.json"]
        mock_cache.get_org_report_snapshot_root_dir.return_value = "/tmp/org_report_snapshots"
        mock_cache_cls.return_value = mock_cache

        with pytest.raises(SystemExit) as exc_info:
            with (
                patch("cja_auto_sdr.generator._cli_option_specified") as mock_cli_spec,
                patch("cja_auto_sdr.generator.parse_arguments") as mock_pa,
            ):
                mock_cli_spec.side_effect = _mock_cli_option_specified_for("--org-report-keep-last")
                mock_pa.return_value = parse_arguments(
                    ["--prune-org-report-snapshots", "--org-report-keep-last", "5", "--format", "json"]
                )
                _main_impl()

        assert exc_info.value.code == 0
        mock_cache.prune_org_report_snapshots.assert_called_once_with(
            org_id=None,
            keep_last=5,
            keep_since_days=None,
        )

    @patch("cja_auto_sdr.generator.OrgReportCache")
    def test_prune_org_report_snapshots_keep_last_zero_is_allowed(self, mock_cache_cls):
        mock_cache = MagicMock()
        mock_cache.prune_org_report_snapshots.return_value = []
        mock_cache.get_org_report_snapshot_root_dir.return_value = "/tmp/org_report_snapshots"
        mock_cache_cls.return_value = mock_cache

        with pytest.raises(SystemExit) as exc_info:
            with (
                patch("cja_auto_sdr.generator._cli_option_specified") as mock_cli_spec,
                patch("cja_auto_sdr.generator.parse_arguments") as mock_pa,
            ):
                mock_cli_spec.side_effect = _mock_cli_option_specified_for("--org-report-keep-last")
                mock_pa.return_value = parse_arguments(
                    ["--prune-org-report-snapshots", "--org-report-keep-last", "0", "--format", "json"]
                )
                _main_impl()

        assert exc_info.value.code == 0
        mock_cache.prune_org_report_snapshots.assert_called_once_with(
            org_id=None,
            keep_last=0,
            keep_since_days=None,
        )

    def test_org_report_snapshot_keep_last_zero_requires_prune_mode(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            with (
                patch("cja_auto_sdr.generator._cli_option_specified") as mock_cli_spec,
                patch("cja_auto_sdr.generator.parse_arguments") as mock_pa,
            ):
                mock_cli_spec.side_effect = _mock_cli_option_specified_for("--org-report-keep-last")
                mock_pa.return_value = parse_arguments(["--list-org-report-snapshots", "--org-report-keep-last", "0"])
                _main_impl()

        assert exc_info.value.code == 1
        assert "--org-report-keep-last and --org-report-keep-since are only supported" in capsys.readouterr().err

    def test_prune_org_report_snapshots_reject_negative_keep_last(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            with (
                patch("cja_auto_sdr.generator._cli_option_specified") as mock_cli_spec,
                patch("cja_auto_sdr.generator.parse_arguments") as mock_pa,
            ):
                mock_cli_spec.side_effect = _mock_cli_option_specified_for("--org-report-keep-last")
                mock_pa.return_value = parse_arguments(["--prune-org-report-snapshots", "--org-report-keep-last", "-1"])
                _main_impl()

        assert exc_info.value.code == 1
        assert "--org-report-keep-last cannot be negative" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_org_report_snapshot_commands_conflict(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(
                    ["--list-org-report-snapshots", "--inspect-org-report-snapshot", "cached.json"]
                )
                _main_impl()

        assert exc_info.value.code == 1
        assert "Use only one of --list-org-report-snapshots" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_dataviews")
    def test_org_report_snapshot_commands_reject_other_primary_modes(self, mock_list_dataviews, capsys):
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--list-dataviews", "--list-org-report-snapshots"])
                _main_impl()

        assert exc_info.value.code == 1
        assert "cannot be combined with other command modes" in capsys.readouterr().err
        mock_list_dataviews.assert_not_called()

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator._handle_completion_prevalidation")
    def test_org_report_snapshot_commands_reject_completion_mode(self, mock_completion, capsys):
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--completion", "bash", "--list-org-report-snapshots"])
                _main_impl()

        assert exc_info.value.code == 1
        assert "cannot be combined with other command modes" in capsys.readouterr().err
        mock_completion.assert_not_called()

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_org_report_snapshot_commands_reject_positional_data_views(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["dv_123", "--list-org-report-snapshots"])
                _main_impl()

        assert exc_info.value.code == 1
        assert "do not accept positional data view arguments" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_inspect_org_report_snapshot_rejects_org_filter(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(
                    [
                        "--inspect-org-report-snapshot",
                        "cached.json",
                        "--org-report-snapshot-org",
                        "test_org@AdobeOrg",
                    ]
                )
                _main_impl()

        assert exc_info.value.code == 1
        assert "--org-report-snapshot-org can only be used" in capsys.readouterr().err


# ==================== _main_impl: --list-snapshots ====================


class TestMainImplListSnapshots:
    """Tests for --list-snapshots mode (lines 14103-14171)."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator._emit_output")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    def test_list_snapshots_table_output(self, mock_sm_cls, mock_emit):
        mock_sm = MagicMock()
        mock_sm.list_snapshots.return_value = [
            {
                "data_view_id": "dv_test",
                "data_view_name": "Test",
                "created_at": "2025-01-01",
                "metrics_count": 10,
                "dimensions_count": 5,
                "filepath": "/path/to/snap.json",
            }
        ]
        mock_sm_cls.return_value = mock_sm
        run_state = {"mode": "unknown", "details": {}}

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--list-snapshots"])
                _main_impl(run_state=run_state)

        assert exc_info.value.code == 0
        assert run_state["details"]["snapshot_count"] == 1
        mock_emit.assert_called_once()

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator._emit_output")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    def test_list_snapshots_json_output(self, mock_sm_cls, mock_emit):
        mock_sm = MagicMock()
        mock_sm.list_snapshots.return_value = []
        mock_sm_cls.return_value = mock_sm

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--list-snapshots", "--format", "json"])
                _main_impl()

        assert exc_info.value.code == 0
        emitted = mock_emit.call_args[0][0]
        parsed = json.loads(emitted)
        assert parsed["count"] == 0

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator._emit_output")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    def test_list_snapshots_csv_output(self, mock_sm_cls, mock_emit):
        mock_sm = MagicMock()
        mock_sm.list_snapshots.return_value = [
            {
                "data_view_id": "dv_csv",
                "data_view_name": "CSV Test",
                "created_at": "2025-02-01",
                "metrics_count": 3,
                "dimensions_count": 2,
                "filepath": "/snap.json",
            }
        ]
        mock_sm_cls.return_value = mock_sm

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--list-snapshots", "--format", "csv"])
                _main_impl()

        assert exc_info.value.code == 0
        emitted = mock_emit.call_args[0][0]
        assert "dv_csv" in emitted

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator._emit_output")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    def test_list_snapshots_filter_by_dv_id(self, mock_sm_cls, mock_emit):
        """When data view IDs provided, only matching snapshots shown."""
        mock_sm = MagicMock()
        mock_sm.list_snapshots.return_value = [
            {
                "data_view_id": "dv_match",
                "data_view_name": "Match",
                "created_at": "2025-01-01",
                "metrics_count": 1,
                "dimensions_count": 1,
                "filepath": "/snap1.json",
            },
            {
                "data_view_id": "dv_other",
                "data_view_name": "Other",
                "created_at": "2025-01-01",
                "metrics_count": 1,
                "dimensions_count": 1,
                "filepath": "/snap2.json",
            },
        ]
        mock_sm_cls.return_value = mock_sm
        run_state = {"mode": "unknown", "details": {}}

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--list-snapshots", "--format", "json", "dv_match"])
                _main_impl(run_state=run_state)

        assert exc_info.value.code == 0
        emitted = mock_emit.call_args[0][0]
        parsed = json.loads(emitted)
        assert parsed["count"] == 1
        assert parsed["snapshots"][0]["data_view_id"] == "dv_match"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator._emit_output")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    def test_list_snapshots_empty_table(self, mock_sm_cls, mock_emit):
        """Empty snapshot list should show 'No snapshots found' message."""
        mock_sm = MagicMock()
        mock_sm.list_snapshots.return_value = []
        mock_sm_cls.return_value = mock_sm

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--list-snapshots"])
                _main_impl()

        assert exc_info.value.code == 0
        emitted = mock_emit.call_args[0][0]
        assert "No snapshots found" in emitted

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.SnapshotManager")
    def test_list_snapshots_json_output_contract_error_is_controlled(self, mock_sm_cls, capsys):
        """Non-finite JSON values should fail with a structured output_contract error."""
        mock_sm = MagicMock()
        mock_sm.list_snapshots.return_value = [{"data_view_id": "dv_nan", "metrics_count": float("nan")}]
        mock_sm_cls.return_value = mock_sm

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--list-snapshots", "--format", "json"])
                _main_impl()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        payload = json.loads(captured.err)
        assert payload["error_type"] == "output_contract"
        assert "Snapshot listing output contains non-JSON-compliant values" in payload["error"]


# ==================== _main_impl: --show-only / --include-all-inventory ====================


class TestMainImplShowOnlyAndInventory:
    """Tests for --show-only parsing and --include-all-inventory (lines 14065-14101)."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_show_only_invalid_types_exits_one(self):
        """Invalid --show-only types should exit 1."""
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["dv_test123"])
                # Simulate diff mode with invalid show_only
                args.diff = ["dv_a", "dv_b"]
                args.show_only = "added,invalid_type"
                mock_pa.return_value = args
                _main_impl()

        assert exc_info.value.code == 1

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator._emit_output")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    def test_include_all_inventory_snapshot_mode(self, mock_sm_cls, mock_emit):
        """--include-all-inventory in snapshot-like mode should not enable derived."""
        mock_sm = MagicMock()
        mock_sm.list_snapshots.return_value = []
        mock_sm_cls.return_value = mock_sm

        with pytest.raises(SystemExit):
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--list-snapshots"])
                args.include_all_inventory = True
                args.snapshot = "dv_test123"  # snapshot-like mode
                mock_pa.return_value = args
                _main_impl()

        # In snapshot-like mode, include_derived_inventory should remain unset


# ==================== _main_impl: --prune-snapshots ====================


class TestMainImplPruneSnapshots:
    """Tests for --prune-snapshots mode (lines 14173-14261)."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_auto_prune_retention")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator._emit_output")
    def test_prune_json_output(self, mock_emit, mock_sm_cls, mock_retention):
        mock_retention.return_value = (5, None)

        mock_sm = MagicMock()
        mock_sm.list_snapshots.return_value = [
            {"data_view_id": "dv_test", "filepath": "/snap1.json"},
        ]
        mock_sm.apply_retention_policy.return_value = ["/snap_old.json"]
        mock_sm_cls.return_value = mock_sm

        run_state = {"mode": "unknown", "details": {}}

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--prune-snapshots", "--keep-last", "5", "--format", "json"])
                mock_pa.return_value = args
                _main_impl(run_state=run_state)

        assert exc_info.value.code == 0
        emitted = mock_emit.call_args[0][0]
        parsed = json.loads(emitted)
        assert parsed["deleted_count"] >= 0

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_auto_prune_retention")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator._emit_output")
    def test_prune_csv_output(self, mock_emit, mock_sm_cls, mock_retention):
        mock_retention.return_value = (3, None)

        mock_sm = MagicMock()
        mock_sm.list_snapshots.return_value = [
            {"data_view_id": "dv_test", "filepath": "/snap1.json"},
        ]
        mock_sm.apply_retention_policy.return_value = ["/deleted.json"]
        mock_sm_cls.return_value = mock_sm

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--prune-snapshots", "--keep-last", "3", "--format", "csv"])
                mock_pa.return_value = args
                _main_impl()

        assert exc_info.value.code == 0
        emitted = mock_emit.call_args[0][0]
        assert "filepath" in emitted

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_auto_prune_retention")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator._emit_output")
    def test_prune_table_output(self, mock_emit, mock_sm_cls, mock_retention):
        mock_retention.return_value = (2, None)

        mock_sm = MagicMock()
        mock_sm.list_snapshots.return_value = [
            {"data_view_id": "dv_test", "filepath": "/snap.json"},
        ]
        mock_sm.apply_retention_policy.return_value = ["/old1.json", "/old2.json"]
        mock_sm_cls.return_value = mock_sm

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--prune-snapshots", "--keep-last", "2"])
                mock_pa.return_value = args
                _main_impl()

        assert exc_info.value.code == 0
        emitted = mock_emit.call_args[0][0]
        assert "Deleted files" in emitted

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_auto_prune_retention")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    def test_prune_no_retention_policy_exits_error(self, mock_sm_cls, mock_retention):
        """--prune-snapshots without retention flags should exit 1."""
        mock_retention.return_value = (0, None)

        mock_sm = MagicMock()
        mock_sm.list_snapshots.return_value = []
        mock_sm_cls.return_value = mock_sm

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--prune-snapshots"])
                mock_pa.return_value = args
                _main_impl()

        assert exc_info.value.code == 1

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.parse_retention_period")
    @patch("cja_auto_sdr.generator.resolve_auto_prune_retention")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator._emit_output")
    def test_prune_with_keep_since(self, mock_emit, mock_sm_cls, mock_retention, mock_parse_period):
        mock_retention.return_value = (0, "7d")
        mock_parse_period.return_value = 7

        mock_sm = MagicMock()
        mock_sm.list_snapshots.return_value = [
            {"data_view_id": "dv_test", "filepath": "/snap.json"},
        ]
        mock_sm.apply_date_retention_policy.return_value = ["/old.json"]
        mock_sm_cls.return_value = mock_sm

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--prune-snapshots", "--keep-since", "7d", "--format", "json"])
                mock_pa.return_value = args
                _main_impl()

        assert exc_info.value.code == 0

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_auto_prune_retention")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator._emit_output")
    def test_prune_with_dv_filter(self, mock_emit, mock_sm_cls, mock_retention):
        """Prune with specific data view IDs should only prune those."""
        mock_retention.return_value = (3, None)

        mock_sm = MagicMock()
        mock_sm.list_snapshots.return_value = [
            {"data_view_id": "dv_keep", "filepath": "/snap_keep.json"},
            {"data_view_id": "dv_prune", "filepath": "/snap_prune.json"},
        ]
        mock_sm.apply_retention_policy.return_value = []
        mock_sm_cls.return_value = mock_sm

        run_state = {"mode": "unknown", "details": {}}

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--prune-snapshots", "--keep-last", "3", "--format", "json", "dv_prune"])
                mock_pa.return_value = args
                _main_impl(run_state=run_state)

        assert exc_info.value.code == 0
        # Should have pruned for dv_prune only
        mock_sm.apply_retention_policy.assert_called_once()

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_auto_prune_retention")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    def test_prune_json_output_contract_error_is_controlled(self, mock_sm_cls, mock_retention, capsys):
        """Non-finite JSON values should fail with a structured output_contract error."""
        mock_retention.return_value = (1, None)

        mock_sm = MagicMock()
        mock_sm.list_snapshots.return_value = [{"data_view_id": "dv_test", "filepath": "/snap1.json"}]
        mock_sm.apply_retention_policy.return_value = [float("nan")]
        mock_sm_cls.return_value = mock_sm

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--prune-snapshots", "--keep-last", "1", "--format", "json"])
                mock_pa.return_value = args
                _main_impl()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        payload = json.loads(captured.err)
        assert payload["error_type"] == "output_contract"
        assert "Snapshot prune output contains non-JSON-compliant values" in payload["error"]


# ==================== _main_impl: --diff-labels ====================


class TestMainImplDiffLabels:
    """Tests for --diff-labels parsing (lines 14073-14076)."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.handle_diff_command")
    def test_diff_labels_parsed_as_tuple(self, mock_diff, mock_resolve):
        """--diff-labels should be parsed and passed as tuple."""
        mock_diff.return_value = (True, False, None)
        mock_resolve.side_effect = [(["dv_a"], {}), (["dv_b"], {})]

        with pytest.raises(SystemExit):
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--diff", "dv_a", "dv_b", "--diff-labels", "Before", "After"])
                mock_pa.return_value = args
                _main_impl()

        # Labels should have been parsed as a tuple and passed through
        mock_diff.assert_called_once()
        assert mock_diff.call_args[1]["labels"] == ("Before", "After")


# ==================== _main_impl: ID-bearing discovery inspection dispatch ====================


class TestDiscoveryInspectionDispatch:
    """Tests for dispatch of new ID-bearing discovery commands."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.describe_dataview")
    def test_describe_dataview_dispatch(self, mock_fn):
        mock_fn.return_value = True
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--describe-dataview", "dv_1"])
                mock_pa.return_value = args
                _main_impl(run_state={})
        assert exc_info.value.code == 0
        mock_fn.assert_called_once()
        assert mock_fn.call_args[0][0] == "dv_1"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.describe_dataview")
    def test_describe_dataview_sets_discovery_mode_in_run_state(self, mock_fn):
        """ID-bearing discovery inspection commands should infer discovery mode."""
        mock_fn.return_value = True
        run_state = {}
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--describe-dataview", "dv_1"])
                mock_pa.return_value = args
                _main_impl(run_state=run_state)

        assert exc_info.value.code == 0
        assert run_state["mode"] == "discovery"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.describe_dataview")
    def test_describe_dataview_rejects_fail_on_quality(self, mock_fn, capsys):
        """Discovery inspection commands should reject SDR-only --fail-on-quality."""
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--describe-dataview", "dv_1", "--fail-on-quality", "HIGH"])
                mock_pa.return_value = args
                _main_impl(run_state={})

        assert exc_info.value.code == 1
        assert "--fail-on-quality is only supported in SDR generation mode" in capsys.readouterr().err
        mock_fn.assert_not_called()

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_metrics")
    def test_list_metrics_dispatch(self, mock_fn):
        mock_fn.return_value = True
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--list-metrics", "dv_1"])
                mock_pa.return_value = args
                _main_impl(run_state={})
        assert exc_info.value.code == 0
        mock_fn.assert_called_once()
        assert mock_fn.call_args[0][0] == "dv_1"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_dimensions")
    def test_list_dimensions_dispatch(self, mock_fn):
        mock_fn.return_value = True
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--list-dimensions", "dv_1"])
                mock_pa.return_value = args
                _main_impl(run_state={})
        assert exc_info.value.code == 0
        mock_fn.assert_called_once()

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_segments")
    def test_list_segments_dispatch(self, mock_fn):
        mock_fn.return_value = True
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--list-segments", "dv_1"])
                mock_pa.return_value = args
                _main_impl(run_state={})
        assert exc_info.value.code == 0
        mock_fn.assert_called_once()

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_calculated_metrics")
    def test_list_calculated_metrics_dispatch(self, mock_fn):
        mock_fn.return_value = True
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--list-calculated-metrics", "dv_1"])
                mock_pa.return_value = args
                _main_impl(run_state={})
        assert exc_info.value.code == 0
        mock_fn.assert_called_once()

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.describe_dataview")
    def test_describe_dataview_stdout_forces_json(self, mock_fn):
        """When output is stdout, format should default to json."""
        mock_fn.return_value = True
        run_state = {}
        with pytest.raises(SystemExit):
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--describe-dataview", "dv_1", "--output", "-"])
                mock_pa.return_value = args
                _main_impl(run_state=run_state)
        assert run_state["output_format"] == "json"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_metrics")
    def test_list_metrics_csv_format_preserved(self, mock_fn):
        """Explicit csv format should be preserved for ID-bearing discovery commands."""
        mock_fn.return_value = True
        run_state = {}
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--list-metrics", "dv_1", "--format", "csv"])
                mock_pa.return_value = args
                _main_impl(run_state=run_state)
        assert exc_info.value.code == 0
        assert run_state["output_format"] == "csv"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_dimensions")
    def test_list_dimensions_failure_exits_one(self, mock_fn):
        """When the command function returns False, should exit 1."""
        mock_fn.return_value = False
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--list-dimensions", "dv_1"])
                mock_pa.return_value = args
                _main_impl()
        assert exc_info.value.code == 1

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_segments")
    def test_list_segments_passes_filter_and_sort(self, mock_fn):
        """Filter and sort options should be forwarded to the command function."""
        mock_fn.return_value = True
        with pytest.raises(SystemExit):
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(
                    [
                        "--list-segments",
                        "dv_1",
                        "--filter",
                        "active.*",
                        "--sort",
                        "name",
                        "--limit",
                        "10",
                    ]
                )
                mock_pa.return_value = args
                _main_impl()
        call_kwargs = mock_fn.call_args
        assert call_kwargs[1]["filter_pattern"] == "active.*"
        assert call_kwargs[1]["sort_expression"] == "name"
        assert call_kwargs[1]["limit"] == 10


class TestDiscoveryInspectionNameResolution:
    """Tests for data view name resolution in ID-bearing discovery commands."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.describe_dataview")
    def test_id_passthrough_skips_resolution(self, mock_fn, mock_resolve):
        """Data view IDs (dv_...) should pass through without calling resolve_data_view_names."""
        mock_fn.return_value = True
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--describe-dataview", "dv_123"])
                mock_pa.return_value = args
                _main_impl(run_state={})
        assert exc_info.value.code == 0
        mock_resolve.assert_not_called()
        assert mock_fn.call_args[0][0] == "dv_123"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.describe_dataview")
    def test_name_resolves_to_single_id(self, mock_fn, mock_resolve):
        """A name that resolves to a single data view ID should be passed to the command."""
        mock_resolve.return_value = (["dv_resolved"], {"My View": ["dv_resolved"]})
        mock_fn.return_value = True
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--describe-dataview", "My View"])
                mock_pa.return_value = args
                _main_impl(run_state={})
        assert exc_info.value.code == 0
        mock_resolve.assert_called_once()
        assert mock_fn.call_args[0][0] == "dv_resolved"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.describe_dataview")
    def test_name_no_match_exits_one(self, mock_fn, mock_resolve, capsys):
        """A name with no matches should exit 1 with an error."""
        mock_resolve.return_value = ([], {})
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--describe-dataview", "Nonexistent View"])
                mock_pa.return_value = args
                _main_impl(run_state={})
        assert exc_info.value.code == 1
        mock_fn.assert_not_called()
        captured = capsys.readouterr()
        assert "Could not resolve data view" in captured.err

    @pytest.mark.parametrize(
        "argv",
        [
            ["--describe-dataview", "Nonexistent View", "--format", "json"],
            ["--describe-dataview", "Nonexistent View", "--format", "csv"],
            ["--describe-dataview", "Nonexistent View", "--output", "-"],
        ],
    )
    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.describe_dataview")
    def test_name_no_match_machine_readable_emits_structured_error(self, mock_fn, mock_resolve, capsys, argv):
        """Machine-readable inspection modes should emit a structured JSON error for unresolved names."""
        mock_resolve.return_value = ([], {})
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(argv)
                _main_impl(run_state={})
        assert exc_info.value.code == 1
        mock_fn.assert_not_called()
        payload = json.loads(capsys.readouterr().err)
        assert payload["error_type"] == "not_found"
        assert "Could not resolve data view" in payload["error"]
        assert "--list-dataviews" in payload["error"]

    @pytest.mark.parametrize(
        "argv",
        [
            ["--describe-dataview", "Broken View", "--format", "json"],
            ["--describe-dataview", "Broken View", "--format", "csv"],
            ["--describe-dataview", "Broken View", "--output", "-"],
        ],
    )
    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.describe_dataview")
    def test_machine_readable_resolution_setup_failure_reports_configuration_error(
        self,
        mock_fn,
        mock_resolve,
        capsys,
        argv,
    ):
        """Setup/configuration failures should not be mislabeled as not_found."""

        def _mock_resolver(_identifiers, _config_file, _logger, **_kwargs):
            return (
                [],
                {},
                NameResolutionDiagnostics(
                    error_type="configuration_error",
                    error_message="Failed to configure credentials: Missing credentials",
                ),
            )

        mock_resolve.side_effect = _mock_resolver

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(argv)
                _main_impl(run_state={})

        assert exc_info.value.code == 1
        mock_fn.assert_not_called()
        payload = json.loads(capsys.readouterr().err)
        assert payload["error_type"] == "configuration_error"
        assert "Failed to configure credentials" in payload["error"]

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.describe_dataview")
    def test_machine_readable_resolution_connectivity_failure_reports_connectivity_error(
        self,
        mock_fn,
        mock_resolve,
        capsys,
    ):
        """Connectivity/API failures should surface as connectivity_error."""

        def _mock_resolver(_identifiers, _config_file, _logger, **_kwargs):
            return (
                [],
                {},
                NameResolutionDiagnostics(
                    error_type="connectivity_error",
                    error_message="Failed to resolve data view names: network timeout",
                ),
            )

        mock_resolve.side_effect = _mock_resolver

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--describe-dataview", "Timeout View", "--format", "json"])
                _main_impl(run_state={})

        assert exc_info.value.code == 1
        mock_fn.assert_not_called()
        payload = json.loads(capsys.readouterr().err)
        assert payload["error_type"] == "connectivity_error"
        assert "network timeout" in payload["error"]

    @pytest.mark.parametrize(
        "argv",
        [
            ["--describe-dataview", "Noisy View", "--format", "json"],
            ["--describe-dataview", "Noisy View", "--format", "csv"],
            ["--describe-dataview", "Noisy View", "--output", "-"],
        ],
    )
    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.describe_dataview")
    def test_machine_readable_resolution_logs_do_not_pollute_json_error(
        self,
        mock_fn,
        mock_resolve,
        capsys,
        argv,
    ):
        """Resolver logger output must not precede machine-readable JSON errors."""

        def _mock_resolver(_identifiers, _config_file, logger, **_kwargs):
            logger.error("resolver plain log line")
            return (
                [],
                {},
                NameResolutionDiagnostics(
                    error_type="configuration_error",
                    error_message="Failed to configure credentials: bad profile",
                ),
            )

        mock_resolve.side_effect = _mock_resolver

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(argv)
                _main_impl(run_state={})

        assert exc_info.value.code == 1
        mock_fn.assert_not_called()
        stderr_output = capsys.readouterr().err
        payload = json.loads(stderr_output)
        assert payload["error_type"] == "configuration_error"
        assert "resolver plain log line" not in stderr_output

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.prompt_for_selection")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.describe_dataview")
    def test_ambiguous_name_interactive_select(self, mock_fn, mock_resolve, mock_prompt):
        """An ambiguous name in interactive mode should call prompt_for_selection."""
        mock_resolve.return_value = (["dv_a", "dv_b"], {"Shared": ["dv_a", "dv_b"]})
        mock_prompt.return_value = "dv_b"
        mock_fn.return_value = True
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--describe-dataview", "Shared"])
                mock_pa.return_value = args
                _main_impl(run_state={})
        assert exc_info.value.code == 0
        mock_prompt.assert_called_once()
        assert mock_fn.call_args[0][0] == "dv_b"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.prompt_for_selection")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.describe_dataview")
    def test_ambiguous_name_non_interactive_exits_one(self, mock_fn, mock_resolve, mock_prompt, capsys):
        """An ambiguous name in non-interactive mode should exit 1 with disambiguation list."""
        mock_resolve.return_value = (["dv_a", "dv_b"], {"Shared": ["dv_a", "dv_b"]})
        mock_prompt.return_value = None  # non-interactive
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--describe-dataview", "Shared"])
                mock_pa.return_value = args
                _main_impl(run_state={})
        assert exc_info.value.code == 1
        mock_fn.assert_not_called()
        captured = capsys.readouterr()
        assert "ambiguous" in captured.err.lower()
        assert "dv_a" in captured.err
        assert "dv_b" in captured.err

    @pytest.mark.parametrize(
        "argv",
        [
            ["--describe-dataview", "Shared", "--format", "json"],
            ["--describe-dataview", "Shared", "--format", "csv"],
            ["--describe-dataview", "Shared", "--output", "-"],
        ],
    )
    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.prompt_for_selection")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.describe_dataview")
    def test_ambiguous_name_machine_readable_emits_structured_error(
        self,
        mock_fn,
        mock_resolve,
        mock_prompt,
        capsys,
        argv,
    ):
        """Machine-readable inspection modes should fail with structured ambiguity details."""
        mock_resolve.return_value = (["dv_a", "dv_b"], {"Shared": ["dv_a", "dv_b"]})
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(argv)
                _main_impl(run_state={})
        assert exc_info.value.code == 1
        mock_fn.assert_not_called()
        mock_prompt.assert_not_called()
        payload = json.loads(capsys.readouterr().err)
        assert payload["error_type"] == "ambiguous_name"
        assert payload["data_view_name"] == "Shared"
        assert payload["matches"] == ["dv_a", "dv_b"]
        assert "Specify an exact data view ID" in payload["error"]

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.describe_dataview")
    def test_name_match_option_forwarded(self, mock_fn, mock_resolve):
        """--name-match should be forwarded to resolve_data_view_names as match_mode."""
        mock_resolve.return_value = (["dv_found"], {"View": ["dv_found"]})
        mock_fn.return_value = True
        with pytest.raises(SystemExit):
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--describe-dataview", "View", "--name-match", "fuzzy"])
                mock_pa.return_value = args
                _main_impl(run_state={})
        assert mock_resolve.call_args[1]["match_mode"] == "fuzzy"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.list_metrics")
    def test_list_metrics_name_resolution(self, mock_fn, mock_resolve):
        """--list-metrics should forward the canonical resolved data view name."""
        mock_resolve.return_value = (
            ["dv_m1"],
            {"Metrics View": ["dv_m1"]},
            NameResolutionDiagnostics(resolved_name_by_id={"dv_m1": "Metrics Canonical"}),
        )
        mock_fn.return_value = True
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--list-metrics", "Metrics View"])
                mock_pa.return_value = args
                _main_impl(run_state={})
        assert exc_info.value.code == 0
        assert mock_fn.call_args[0][0] == "dv_m1"
        assert mock_fn.call_args[1]["data_view_name"] == "Metrics Canonical"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.list_dimensions")
    def test_list_dimensions_name_resolution(self, mock_fn, mock_resolve):
        """--list-dimensions should forward the canonical resolved data view name."""
        mock_resolve.return_value = (
            ["dv_d1"],
            {"Dims View": ["dv_d1"]},
            NameResolutionDiagnostics(resolved_name_by_id={"dv_d1": "Dimensions Canonical"}),
        )
        mock_fn.return_value = True
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--list-dimensions", "Dims View"])
                mock_pa.return_value = args
                _main_impl(run_state={})
        assert exc_info.value.code == 0
        assert mock_fn.call_args[0][0] == "dv_d1"
        assert mock_fn.call_args[1]["data_view_name"] == "Dimensions Canonical"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.list_segments")
    def test_list_segments_name_resolution(self, mock_fn, mock_resolve):
        """--list-segments should forward the canonical resolved data view name."""
        mock_resolve.return_value = (
            ["dv_s1"],
            {"Segs View": ["dv_s1"]},
            NameResolutionDiagnostics(resolved_name_by_id={"dv_s1": "Segments Canonical"}),
        )
        mock_fn.return_value = True
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--list-segments", "Segs View"])
                mock_pa.return_value = args
                _main_impl(run_state={})
        assert exc_info.value.code == 0
        assert mock_fn.call_args[0][0] == "dv_s1"
        assert mock_fn.call_args[1]["data_view_name"] == "Segments Canonical"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.list_calculated_metrics")
    def test_list_calculated_metrics_name_resolution(self, mock_fn, mock_resolve):
        """--list-calculated-metrics should forward the canonical resolved data view name."""
        mock_resolve.return_value = (
            ["dv_cm1"],
            {"Calc View": ["dv_cm1"]},
            NameResolutionDiagnostics(resolved_name_by_id={"dv_cm1": "Calculated Canonical"}),
        )
        mock_fn.return_value = True
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--list-calculated-metrics", "Calc View"])
                mock_pa.return_value = args
                _main_impl(run_state={})
        assert exc_info.value.code == 0
        assert mock_fn.call_args[0][0] == "dv_cm1"
        assert mock_fn.call_args[1]["data_view_name"] == "Calculated Canonical"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.list_metrics")
    def test_list_metrics_name_resolution_legacy_tuple_omits_preferred_name(self, mock_fn, mock_resolve):
        """Legacy resolver tuples should not inject raw query text as data_view_name."""
        mock_resolve.return_value = (["dv_m1"], {"Prod Web": ["dv_m1"]})
        mock_fn.return_value = True
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--list-metrics", "Prod Web", "--name-match", "fuzzy"])
                mock_pa.return_value = args
                _main_impl(run_state={})
        assert exc_info.value.code == 0
        assert mock_fn.call_args[0][0] == "dv_m1"
        assert "data_view_name" not in mock_fn.call_args[1]

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.list_metrics")
    def test_list_metrics_name_resolution_fuzzy_uses_canonical_name(self, mock_fn, mock_resolve):
        """Fuzzy inspection name matches should use canonical names in downstream output."""
        mock_resolve.return_value = (
            ["dv_prod_web"],
            {"Prod Web": ["dv_prod_web"]},
            NameResolutionDiagnostics(resolved_name_by_id={"dv_prod_web": "Production Web"}),
        )
        mock_fn.return_value = True
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--list-metrics", "Prod Web", "--name-match", "fuzzy"])
                mock_pa.return_value = args
                _main_impl(run_state={})
        assert exc_info.value.code == 0
        assert mock_fn.call_args[0][0] == "dv_prod_web"
        assert mock_fn.call_args[1]["data_view_name"] == "Production Web"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.list_metrics")
    def test_id_passthrough_list_metrics(self, mock_fn, mock_resolve):
        """--list-metrics with a dv_ ID should skip resolution."""
        mock_fn.return_value = True
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--list-metrics", "dv_456"])
                mock_pa.return_value = args
                _main_impl(run_state={})
        assert exc_info.value.code == 0
        mock_resolve.assert_not_called()
        assert mock_fn.call_args[0][0] == "dv_456"
        assert "data_view_name" not in mock_fn.call_args[1]

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.describe_dataview")
    def test_name_no_match_error_suggests_list_dataviews(self, mock_fn, mock_resolve, capsys):
        """Unresolved name error should suggest running --list-dataviews."""
        mock_resolve.return_value = ([], {})
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--describe-dataview", "No Such View"])
                mock_pa.return_value = args
                _main_impl(run_state={})
        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "--list-dataviews" in captured.err


class TestDiscoveryInspectionOutputFile:
    """Tests for --output FILE with inspection commands."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_metrics")
    def test_output_file_forwarded_to_command(self, mock_fn, tmp_path):
        """--output FILE should be forwarded to the command function."""
        mock_fn.return_value = True
        out_file = str(tmp_path / "metrics.json")
        with pytest.raises(SystemExit):
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--list-metrics", "dv_1", "--format", "json", "--output", out_file])
                mock_pa.return_value = args
                _main_impl(run_state={})
        assert mock_fn.call_args[1]["output_file"] == out_file

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_dimensions")
    def test_output_file_forwarded_to_list_dimensions(self, mock_fn, tmp_path):
        """--output FILE should be forwarded to list_dimensions."""
        mock_fn.return_value = True
        out_file = str(tmp_path / "dims.csv")
        with pytest.raises(SystemExit):
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--list-dimensions", "dv_1", "--format", "csv", "--output", out_file])
                mock_pa.return_value = args
                _main_impl(run_state={})
        assert mock_fn.call_args[1]["output_file"] == out_file

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.describe_dataview")
    def test_output_file_forwarded_to_describe_dataview(self, mock_fn, tmp_path):
        """--output FILE should be forwarded to describe_dataview."""
        mock_fn.return_value = True
        out_file = str(tmp_path / "desc.json")
        with pytest.raises(SystemExit):
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--describe-dataview", "dv_1", "--format", "json", "--output", out_file])
                mock_pa.return_value = args
                _main_impl(run_state={})
        assert mock_fn.call_args[1]["output_file"] == out_file


class TestDiscoveryInspectionExcludePattern:
    """Tests for --exclude pattern forwarding in inspection commands."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_metrics")
    def test_exclude_pattern_forwarded_to_list_metrics(self, mock_fn):
        """--exclude pattern should be forwarded as exclude_pattern kwarg."""
        mock_fn.return_value = True
        with pytest.raises(SystemExit):
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--list-metrics", "dv_1", "--exclude", "internal.*"])
                mock_pa.return_value = args
                _main_impl()
        assert mock_fn.call_args[1]["exclude_pattern"] == "internal.*"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_dimensions")
    def test_exclude_pattern_forwarded_to_list_dimensions(self, mock_fn):
        """--exclude pattern should be forwarded to list_dimensions."""
        mock_fn.return_value = True
        with pytest.raises(SystemExit):
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--list-dimensions", "dv_1", "--exclude", "test.*"])
                mock_pa.return_value = args
                _main_impl()
        assert mock_fn.call_args[1]["exclude_pattern"] == "test.*"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_calculated_metrics")
    def test_filter_and_exclude_combined(self, mock_fn):
        """--filter and --exclude should both be forwarded together."""
        mock_fn.return_value = True
        with pytest.raises(SystemExit):
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(
                    ["--list-calculated-metrics", "dv_1", "--filter", "revenue.*", "--exclude", "test.*"]
                )
                mock_pa.return_value = args
                _main_impl()
        assert mock_fn.call_args[1]["filter_pattern"] == "revenue.*"
        assert mock_fn.call_args[1]["exclude_pattern"] == "test.*"


class TestDiscoveryInspectionSortDescending:
    """Tests for --sort with descending prefix in inspection commands."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_metrics")
    def test_sort_descending_forwarded(self, mock_fn):
        """--sort=-name should be forwarded as-is to the command function."""
        mock_fn.return_value = True
        with pytest.raises(SystemExit):
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--list-metrics", "dv_1", "--sort=-name"])
                mock_pa.return_value = args
                _main_impl()
        assert mock_fn.call_args[1]["sort_expression"] == "-name"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_segments")
    def test_sort_ascending_forwarded(self, mock_fn):
        """--sort name (ascending) should be forwarded to the command function."""
        mock_fn.return_value = True
        with pytest.raises(SystemExit):
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--list-segments", "dv_1", "--sort", "id"])
                mock_pa.return_value = args
                _main_impl()
        assert mock_fn.call_args[1]["sort_expression"] == "id"


class TestDiscoveryInspectionLimitDispatch:
    """Tests for --limit forwarding through inspection dispatch."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_dimensions")
    def test_limit_forwarded_to_list_dimensions(self, mock_fn):
        """--limit should be forwarded as integer to the command function."""
        mock_fn.return_value = True
        with pytest.raises(SystemExit):
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--list-dimensions", "dv_1", "--limit", "5"])
                mock_pa.return_value = args
                _main_impl()
        assert mock_fn.call_args[1]["limit"] == 5

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_calculated_metrics")
    def test_limit_forwarded_to_list_calculated_metrics(self, mock_fn):
        """--limit should be forwarded to list_calculated_metrics."""
        mock_fn.return_value = True
        with pytest.raises(SystemExit):
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(["--list-calculated-metrics", "dv_1", "--limit", "20"])
                mock_pa.return_value = args
                _main_impl()
        assert mock_fn.call_args[1]["limit"] == 20


class TestDescribeDataviewIgnoresFilterSortLimit:
    """Tests that describe_dataview ignores filter/sort/limit kwargs with a warning."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.describe_dataview")
    def test_filter_sort_limit_do_not_cause_error(self, mock_fn, capsys):
        """--filter, --sort, --limit with --describe-dataview should not error."""
        mock_fn.return_value = True
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(
                    ["--describe-dataview", "dv_1", "--filter", "something", "--sort", "name", "--limit", "10"]
                )
                mock_pa.return_value = args
                _main_impl(run_state={})
        assert exc_info.value.code == 0
        mock_fn.assert_called_once()
        assert "--filter, --sort, --limit options are ignored with --describe-dataview" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.describe_dataview")
    def test_filter_sort_limit_warning_suppressed_for_machine_readable_mode(self, mock_fn, capsys):
        """Machine-readable describe mode should avoid warning text on stderr."""
        mock_fn.return_value = True
        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                args = parse_arguments(
                    [
                        "--describe-dataview",
                        "dv_1",
                        "--format",
                        "json",
                        "--filter",
                        "something",
                        "--sort",
                        "name",
                        "--limit",
                        "10",
                    ]
                )
                mock_pa.return_value = args
                _main_impl(run_state={})
        assert exc_info.value.code == 0
        mock_fn.assert_called_once()
        assert "ignored with --describe-dataview" not in capsys.readouterr().err

    def test_describe_dataview_rejects_unexpected_kwargs(self):
        """describe_dataview() should fail fast on unsupported kwargs."""
        from cja_auto_sdr.generator import describe_dataview

        with pytest.raises(TypeError):
            describe_dataview(
                "dv_1",
                output_format="json",
                filter_pattern="anything",
                exclude_pattern="something",
                limit=10,
                sort_expression="-name",
            )
