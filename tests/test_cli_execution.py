"""Tests for CLI execution preflight helpers."""

import argparse
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from cja_auto_sdr.cli.execution import prepare_sdr_execution_context


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
