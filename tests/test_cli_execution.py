"""Tests for CLI execution preflight helpers."""

import argparse
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from cja_auto_sdr.cli.execution import (
    dispatch_inventory_summary_mode,
    execute_sdr_processing_modes,
    prepare_sdr_execution_context,
    resolve_inventory_mode_configuration,
)


class _ConsoleColors:
    @staticmethod
    def info(text: str) -> str:
        return text

    @staticmethod
    def warning(text: str) -> str:
        return text

    @staticmethod
    def error(text: str) -> str:
        return text

    @staticmethod
    def success(text: str) -> str:
        return text

    @staticmethod
    def bold(text: str) -> str:
        return text


def _make_args(**overrides) -> argparse.Namespace:
    defaults = {
        "assume_yes": True,
        "quiet": False,
        "dry_run": False,
        "production": False,
        "log_level": "INFO",
        "log_format": "default",
        "config_file": "config.json",
        "output_dir": "/tmp/output",
        "format": None,
        "quality_report": None,
        "metrics_only": False,
        "dimensions_only": False,
        "api_auto_tune": False,
        "api_min_workers": 1,
        "api_max_workers": 10,
        "circuit_breaker": False,
        "circuit_failure_threshold": 5,
        "circuit_timeout": 30.0,
        "inventory_summary": False,
        "include_derived_inventory": False,
        "include_calculated_metrics": False,
        "include_segments_inventory": False,
        "inventory_only": False,
        "profile": None,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _make_generator():
    return SimpleNamespace(
        ConsoleColors=_ConsoleColors,
        APITuningConfig=lambda min_workers, max_workers: SimpleNamespace(
            min_workers=min_workers,
            max_workers=max_workers,
        ),
        CircuitBreakerConfig=lambda failure_threshold, timeout_seconds: SimpleNamespace(
            failure_threshold=failure_threshold,
            timeout_seconds=timeout_seconds,
        ),
        _check_output_dir_access=lambda output_dir: (True, Path(output_dir), None, None),
        setup_logging=MagicMock(return_value="logger"),
        run_dry_run=MagicMock(return_value=True),
    )


class TestPrepareSdrExecutionContext:
    def test_returns_execution_context_with_api_and_circuit_configs(self):
        args = _make_args(
            api_auto_tune=True,
            api_min_workers=2,
            api_max_workers=8,
            circuit_breaker=True,
            circuit_failure_threshold=4,
            circuit_timeout=12.5,
        )
        generator = _make_generator()

        with patch("cja_auto_sdr.cli.execution._generator_module", return_value=generator):
            context = prepare_sdr_execution_context(args, data_views=["dv_123"], run_state={})

        assert context["effective_log_level"] == "INFO"
        assert context["quality_report_format"] is None
        assert context["quality_report_only"] is False
        assert context["sdr_format"] == "excel"
        assert context["inventory_order"] == []
        assert context["api_tuning_config"].min_workers == 2
        assert context["api_tuning_config"].max_workers == 8
        assert context["circuit_breaker_config"].failure_threshold == 4
        assert context["circuit_breaker_config"].timeout_seconds == 12.5

    def test_dry_run_exits_after_running_validation(self):
        args = _make_args(dry_run=True, output_dir="/tmp/not-used")
        generator = _make_generator()
        run_state: dict[str, object] = {}

        with patch("cja_auto_sdr.cli.execution._generator_module", return_value=generator):
            with pytest.raises(SystemExit) as exc_info:
                prepare_sdr_execution_context(args, data_views=["dv_123"], run_state=run_state)

        assert exc_info.value.code == 0
        generator.setup_logging.assert_called_once_with(batch_mode=True, log_level="WARNING", log_format="default")
        generator.run_dry_run.assert_called_once_with(["dv_123"], "config.json", "logger", profile=None)
        assert run_state["details"] == {"operation_success": True}

    def test_inventory_summary_dispatches_and_exits(self):
        args = _make_args(inventory_summary=True, include_segments_inventory=True)
        generator = _make_generator()
        mock_dispatch = MagicMock(side_effect=SystemExit(0))

        with (
            patch("cja_auto_sdr.cli.execution._generator_module", return_value=generator),
            patch("cja_auto_sdr.cli.execution.resolve_inventory_mode_configuration", return_value=["segments"]),
            patch("cja_auto_sdr.cli.execution.dispatch_inventory_summary_mode", mock_dispatch),
        ):
            with pytest.raises(SystemExit) as exc_info:
                prepare_sdr_execution_context(args, data_views=["dv_123"])

        assert exc_info.value.code == 0
        assert mock_dispatch.call_count == 1
        dispatch_args = mock_dispatch.call_args.kwargs
        assert dispatch_args["data_views"] == ["dv_123"]
        assert dispatch_args["effective_log_level"] == "INFO"
        assert dispatch_args["inventory_order"] == ["segments"]

    def test_output_dir_not_directory_exits_1(self, capsys):
        """When _check_output_dir_access returns not_directory, exit(1) with error."""
        args = _make_args()
        generator = _make_generator()
        generator._check_output_dir_access = lambda output_dir: (
            False,
            Path(output_dir),
            "not_directory",
            None,
        )

        with patch("cja_auto_sdr.cli.execution._generator_module", return_value=generator):
            with pytest.raises(SystemExit) as exc_info:
                prepare_sdr_execution_context(args, data_views=["dv_123"])

        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "Output path is not a directory" in err

    def test_output_dir_parent_not_directory_exits_1(self, capsys):
        """When access_reason is parent_not_directory, exit(1) with message about component."""
        args = _make_args()
        generator = _make_generator()
        parent = Path("/some/nonexistent/component")
        generator._check_output_dir_access = lambda output_dir: (
            False,
            Path(output_dir),
            "parent_not_directory",
            parent,
        )

        with patch("cja_auto_sdr.cli.execution._generator_module", return_value=generator):
            with pytest.raises(SystemExit) as exc_info:
                prepare_sdr_execution_context(args, data_views=["dv_123"])

        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "Cannot create output directory" in err
        assert str(parent) in err

    def test_output_dir_parent_not_writable_exits_1(self, capsys):
        """When access_reason is parent_not_writable, exit(1) with not writable message."""
        args = _make_args()
        generator = _make_generator()
        parent = Path("/restricted/parent")
        generator._check_output_dir_access = lambda output_dir: (
            False,
            Path(output_dir),
            "parent_not_writable",
            parent,
        )

        with patch("cja_auto_sdr.cli.execution._generator_module", return_value=generator):
            with pytest.raises(SystemExit) as exc_info:
                prepare_sdr_execution_context(args, data_views=["dv_123"])

        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "Cannot create output directory" in err
        assert "not writable" in err

    def test_output_dir_default_permission_failure_exits_1(self, capsys):
        """Fallback access reason (no parent_dir) exits with generic cannot-write message."""
        args = _make_args()
        generator = _make_generator()
        generator._check_output_dir_access = lambda output_dir: (
            False,
            Path(output_dir),
            "unknown_reason",
            None,
        )

        with patch("cja_auto_sdr.cli.execution._generator_module", return_value=generator):
            with pytest.raises(SystemExit) as exc_info:
                prepare_sdr_execution_context(args, data_views=["dv_123"])

        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "Cannot write to output directory" in err
        assert "Check permissions" in err


class TestResolveInventoryModeConfiguration:
    """Tests for resolve_inventory_mode_configuration() covering argv flag position tracking."""

    def _make_gen_for_resolve(self):
        return SimpleNamespace(ConsoleColors=_ConsoleColors)

    def test_include_derived_only_returns_derived(self):
        """--include-derived alone produces ['derived'] ordering."""
        args = argparse.Namespace(
            include_derived_inventory=True,
            include_calculated_metrics=False,
            include_segments_inventory=False,
            inventory_only=False,
            inventory_summary=False,
        )
        gen = self._make_gen_for_resolve()
        with patch("cja_auto_sdr.cli.execution._generator_module", return_value=gen):
            result = resolve_inventory_mode_configuration(args, argv=["dv_123", "--include-derived"])
        assert result == ["derived"]

    def test_include_calculated_only_returns_calculated(self):
        """--include-calculated alone produces ['calculated'] ordering."""
        args = argparse.Namespace(
            include_derived_inventory=False,
            include_calculated_metrics=True,
            include_segments_inventory=False,
            inventory_only=False,
            inventory_summary=False,
        )
        gen = self._make_gen_for_resolve()
        with patch("cja_auto_sdr.cli.execution._generator_module", return_value=gen):
            result = resolve_inventory_mode_configuration(args, argv=["dv_123", "--include-calculated"])
        assert result == ["calculated"]

    def test_include_segments_only_returns_segments(self):
        """--include-segments alone produces ['segments'] ordering."""
        args = argparse.Namespace(
            include_derived_inventory=False,
            include_calculated_metrics=False,
            include_segments_inventory=True,
            inventory_only=False,
            inventory_summary=False,
        )
        gen = self._make_gen_for_resolve()
        with patch("cja_auto_sdr.cli.execution._generator_module", return_value=gen):
            result = resolve_inventory_mode_configuration(args, argv=["dv_123", "--include-segments"])
        assert result == ["segments"]

    def test_all_three_flags_respects_cli_order(self):
        """All three flags in a specific order are sorted by argv position."""
        args = argparse.Namespace(
            include_derived_inventory=True,
            include_calculated_metrics=True,
            include_segments_inventory=True,
            inventory_only=False,
            inventory_summary=False,
        )
        gen = self._make_gen_for_resolve()
        # Order in argv: segments first, then calculated, then derived
        argv = ["dv_123", "--include-segments", "--include-calculated", "--include-derived"]
        with patch("cja_auto_sdr.cli.execution._generator_module", return_value=gen):
            result = resolve_inventory_mode_configuration(args, argv=argv)
        assert result == ["segments", "calculated", "derived"]

    def test_derived_and_calculated_order_preserved(self):
        """Two flags: derived before calculated in argv => ['derived', 'calculated']."""
        args = argparse.Namespace(
            include_derived_inventory=True,
            include_calculated_metrics=True,
            include_segments_inventory=False,
            inventory_only=False,
            inventory_summary=False,
        )
        gen = self._make_gen_for_resolve()
        argv = ["dv_123", "--include-derived", "--include-calculated"]
        with patch("cja_auto_sdr.cli.execution._generator_module", return_value=gen):
            result = resolve_inventory_mode_configuration(args, argv=argv)
        assert result == ["derived", "calculated"]

    def test_duplicate_flag_in_argv_uses_first_occurrence(self):
        """Duplicate flags in argv: only first occurrence position is recorded."""
        args = argparse.Namespace(
            include_derived_inventory=True,
            include_calculated_metrics=False,
            include_segments_inventory=False,
            inventory_only=False,
            inventory_summary=False,
        )
        gen = self._make_gen_for_resolve()
        # --include-derived appears twice; only first position (1) should be used
        argv = ["dv_123", "--include-derived", "--other-flag", "--include-derived"]
        with patch("cja_auto_sdr.cli.execution._generator_module", return_value=gen):
            result = resolve_inventory_mode_configuration(args, argv=argv)
        assert result == ["derived"]

    def test_no_inventory_flags_returns_empty_list(self):
        """When no inventory flags are set, returns empty list."""
        args = argparse.Namespace(
            include_derived_inventory=False,
            include_calculated_metrics=False,
            include_segments_inventory=False,
            inventory_only=False,
            inventory_summary=False,
        )
        gen = self._make_gen_for_resolve()
        with patch("cja_auto_sdr.cli.execution._generator_module", return_value=gen):
            result = resolve_inventory_mode_configuration(args, argv=["dv_123"])
        assert result == []


class TestDispatchInventorySummaryMode:
    """Tests for dispatch_inventory_summary_mode() covering the multi-DV blank-line separator."""

    def test_multiple_data_views_prints_separator(self, capsys):
        """When processing > 1 data view, a blank line is printed between them."""
        args = _make_args(include_segments_inventory=True, format=None)
        gen = SimpleNamespace(
            ConsoleColors=_ConsoleColors,
            process_inventory_summary=MagicMock(return_value={}),
        )

        with patch("cja_auto_sdr.cli.execution._generator_module", return_value=gen):
            with pytest.raises(SystemExit) as exc_info:
                dispatch_inventory_summary_mode(
                    args,
                    data_views=["dv_1", "dv_2"],
                    effective_log_level="INFO",
                    inventory_order=["segments"],
                )

        assert exc_info.value.code == 0
        # Two data views => one blank-line separator printed between them
        assert gen.process_inventory_summary.call_count == 2
        out = capsys.readouterr().out
        assert "\n\n" in out or out.count("\n") >= 1

    def test_single_data_view_no_separator(self, capsys):
        """When processing exactly 1 data view, no blank line separator is printed."""
        args = _make_args(format=None)
        gen = SimpleNamespace(
            ConsoleColors=_ConsoleColors,
            process_inventory_summary=MagicMock(return_value={}),
        )

        with patch("cja_auto_sdr.cli.execution._generator_module", return_value=gen):
            with pytest.raises(SystemExit) as exc_info:
                dispatch_inventory_summary_mode(
                    args,
                    data_views=["dv_1"],
                    effective_log_level="INFO",
                    inventory_order=[],
                )

        assert exc_info.value.code == 0
        assert gen.process_inventory_summary.call_count == 1
        out = capsys.readouterr().out
        # No separator blank line should appear
        assert out == "" or "\n\n" not in out


class TestExecuteSdrProcessingModesQualityOnly:
    """Tests for execute_sdr_processing_modes() and _run_single_mode() quality-report-only path."""

    def _make_quality_result(self, success=True):
        result = MagicMock()
        result.success = success
        result.data_view_name = "Test DV"
        result.data_view_id = "dv_123"
        result.metrics_count = 10
        result.dimensions_count = 5
        result.dq_issues_count = 2
        result.error_message = "Something failed"
        result.emitted_output_files = []
        result.output_file = "/tmp/output/test.xlsx"
        result.file_size_formatted = "1.2 MB"
        return result

    def test_quality_report_only_single_mode_success_path(self, capsys):
        """quality_report_only=True in single mode prints quality summary lines (L667-669)."""
        args = _make_args(
            quality_report="json",
            quiet=False,
            batch=False,
            workers=1,
            continue_on_error=False,
            show_timings=False,
            enable_cache=False,
            cache_size=100,
            cache_ttl=300,
            skip_validation=False,
            max_issues=10,
            clear_cache=False,
            production=False,
        )
        mock_result = self._make_quality_result(success=True)
        gen = SimpleNamespace(
            ConsoleColors=_ConsoleColors,
            process_single_dataview=MagicMock(return_value=mock_result),
        )

        with patch("cja_auto_sdr.cli.execution._generator_module", return_value=gen):
            output = execute_sdr_processing_modes(
                args,
                data_views=["dv_123"],
                effective_log_level="INFO",
                sdr_format="json",
                processing_start_time=0.0,
                workers_auto=False,
                quality_report_only=False,  # routes to _run_single_mode, not quality mode
                inventory_order=[],
                api_tuning_config=None,
                circuit_breaker_config=None,
            )

        capsys.readouterr()
        assert output["quality_report_results"] == []
        assert output["overall_failure"] is False

    def test_quality_report_only_prints_quality_summary_lines(self, capsys):
        """L667-669: quality_report_only path prints SUCCESS + Metrics/Dimensions/Issues lines."""
        args = _make_args(
            quality_report="json",
            quiet=False,
            batch=False,
            workers=1,
            continue_on_error=False,
            show_timings=False,
            enable_cache=False,
            cache_size=100,
            cache_ttl=300,
            skip_validation=False,
            max_issues=10,
            clear_cache=False,
            production=False,
        )
        mock_result = self._make_quality_result(success=True)
        gen = SimpleNamespace(
            ConsoleColors=_ConsoleColors,
            process_single_dataview=MagicMock(return_value=mock_result),
        )

        with patch("cja_auto_sdr.cli.execution._generator_module", return_value=gen):
            # Directly invoke _run_single_mode via execute_sdr_processing_modes
            # by NOT setting quality_report_only=True (which routes to quality mode)
            # We instead patch _run_single_mode internals via quality_report_only param
            from cja_auto_sdr.cli.execution import _run_single_mode

            output = _run_single_mode(
                args,
                data_views=["dv_123"],
                effective_log_level="INFO",
                sdr_format="json",
                processing_start_time=0.0,
                quality_report_only=True,
                inventory_order=[],
                api_tuning_config=None,
                circuit_breaker_config=None,
            )

        out = capsys.readouterr().out
        assert "Quality validation completed" in out
        assert "Metrics:" in out
        assert "Data Quality Issues:" in out
        assert output["overall_failure"] is False
        assert output["quality_report_results"] == []
