"""Tests for quality policy functions and run summary/status inference.

Covers: normalize_quality_severity, count_quality_issues_by_severity,
has_quality_issues_at_or_above, aggregate_quality_issues, load_quality_policy,
apply_quality_policy_defaults, _normalize_exit_code, _infer_run_status,
_merge_run_details, and _coerce_run_mode.
"""

import argparse
import importlib.metadata
import json
import os
import re
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from cja_auto_sdr.generator import (
    FAILURE_CODE_REGISTRY,
    RUN_SUMMARY_SCHEMA_VERSION,
    ProcessingResult,
    RunMode,
    _build_org_report_lock_run_summary_block,
    _coerce_run_mode,
    _collect_environment_info,
    _infer_run_status,
    _merge_run_details,
    _normalize_exit_code,
    _normalize_failure_identity,
    _normalize_output_artifact_state,
    _processing_result_to_summary,
    _result_output_paths,
    aggregate_quality_issues,
    apply_quality_policy_defaults,
    count_quality_issues_by_severity,
    has_quality_issues_at_or_above,
    load_quality_policy,
    normalize_quality_severity,
)

# ==================== run-summary details helpers ====================


class TestRunSummarySchemaVersion:
    def test_schema_version_matches_current_contract(self):
        assert RUN_SUMMARY_SCHEMA_VERSION == "1.1"


@pytest.mark.run_summary_contract
class TestRunSummaryOutput:
    """Tests for --run-summary-json output."""

    @staticmethod
    def _assert_run_summary_schema(payload):
        """Validate run summary payload contract used by automation."""
        required_keys = {
            "summary_version",
            "tool_version",
            "started_at",
            "ended_at",
            "duration_seconds",
            "exit_code",
            "status",
            "mode",
            "profile",
            "config_file",
            "output_format",
            "allow_partial",
            "command",
            "inputs",
            "results",
            "result_counts",
            "failure_rollups",
            "quality_gate_failed",
            "quality_policy",
            "details",
        }
        assert required_keys.issubset(payload)
        assert payload["summary_version"] == "1.1"
        assert isinstance(payload["tool_version"], str)
        assert isinstance(payload["started_at"], str)
        assert isinstance(payload["ended_at"], str)
        assert isinstance(payload["duration_seconds"], (int, float))
        assert isinstance(payload["exit_code"], int)
        assert payload["status"] in {"success", "error", "policy_exit"}
        assert isinstance(payload["mode"], str)
        assert payload["profile"] is None or isinstance(payload["profile"], str)
        assert payload["config_file"] is None or isinstance(payload["config_file"], str)
        assert payload["output_format"] is None or isinstance(payload["output_format"], str)
        assert isinstance(payload["allow_partial"], bool)

        command = payload["command"]
        assert isinstance(command, dict)
        assert isinstance(command.get("argv"), list)
        assert all(isinstance(arg, str) for arg in command["argv"])
        assert isinstance(command.get("cwd"), str)

        inputs = payload["inputs"]
        assert isinstance(inputs, dict)
        assert isinstance(inputs.get("data_view_inputs"), list)
        assert isinstance(inputs.get("resolved_data_views"), list)

        result_counts = payload["result_counts"]
        assert isinstance(result_counts, dict)
        assert isinstance(result_counts.get("total"), int)
        assert isinstance(result_counts.get("successful"), int)
        assert isinstance(result_counts.get("failed"), int)
        assert isinstance(result_counts.get("quality_issues"), int)
        assert result_counts["total"] == result_counts["successful"] + result_counts["failed"]

        assert isinstance(payload["results"], list)
        result_required_keys = {
            "data_view_id",
            "data_view_name",
            "success",
            "duration_seconds",
            "metrics_count",
            "dimensions_count",
            "dq_issues_count",
            "dq_severity_counts",
            "output_file",
            "output_files",
            "error_message",
            "failure_code",
            "failure_reason",
            "partial_output",
            "partial_reasons",
            "file_size_bytes",
            "segments_count",
            "segments_high_complexity",
            "calculated_metrics_count",
            "calculated_metrics_high_complexity",
            "derived_fields_count",
            "derived_fields_high_complexity",
        }
        for result in payload["results"]:
            assert isinstance(result, dict)
            assert result_required_keys.issubset(result)
            assert isinstance(result["data_view_id"], str)
            assert isinstance(result["data_view_name"], str)
            assert isinstance(result["success"], bool)
            assert isinstance(result["duration_seconds"], (int, float))
            assert isinstance(result["dq_severity_counts"], dict)
            assert isinstance(result["output_file"], str)
            assert isinstance(result["output_files"], list)
            assert all(isinstance(path, str) for path in result["output_files"])
            assert isinstance(result["failure_code"], str)
            assert isinstance(result["failure_reason"], str)
            assert isinstance(result["partial_output"], bool)
            assert isinstance(result["partial_reasons"], list)
            assert all(isinstance(reason, str) for reason in result["partial_reasons"])

        failure_rollups = payload["failure_rollups"]
        assert isinstance(failure_rollups, dict)
        assert isinstance(failure_rollups.get("by_code"), dict)
        assert isinstance(failure_rollups.get("by_reason"), dict)

        assert isinstance(payload["quality_gate_failed"], bool)

        quality_policy = payload["quality_policy"]
        if quality_policy is not None:
            assert isinstance(quality_policy, dict)
            assert isinstance(quality_policy.get("path"), str)
            assert isinstance(quality_policy.get("applied"), dict)

        assert isinstance(payload["details"], dict)

    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_run_summary_written_for_sdr_success(self, mock_resolve, mock_process, tmp_path):
        """Successful SDR run should write run summary with result details."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_test"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=True,
            duration=0.25,
            metrics_count=10,
            dimensions_count=12,
            dq_issues_count=0,
            dq_issues=[],
            dq_severity_counts={},
            output_file="report.xlsx",
            file_size_bytes=2048,
        )

        summary_file = tmp_path / "run_summary.json"
        with patch.object(sys, "argv", ["cja_auto_sdr", "dv_test", "--run-summary-json", str(summary_file)]):
            main()

        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "sdr"
        assert payload["exit_code"] == 0
        assert payload["output_format"] == "excel"
        assert payload["result_counts"]["total"] == 1
        assert payload["result_counts"]["successful"] == 1
        assert payload["results"][0]["data_view_id"] == "dv_test"
        assert payload["results"][0]["output_file"] == "report.xlsx"
        assert payload["results"][0]["output_files"] == ["report.xlsx"]

    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_run_summary_serializes_additive_output_files(self, mock_resolve, mock_process, tmp_path):
        """Run summary should carry additive multi-artifact output data."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_test"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=True,
            duration=0.25,
            metrics_count=10,
            dimensions_count=12,
            dq_issues_count=0,
            dq_issues=[],
            dq_severity_counts={},
            output_file="report.xlsx",
            output_files=["report.xlsx", "report.json", "report.html"],
            file_size_bytes=2048,
        )

        summary_file = tmp_path / "run_summary_outputs.json"
        with patch.object(sys, "argv", ["cja_auto_sdr", "dv_test", "--run-summary-json", str(summary_file)]):
            main()

        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["results"][0]["output_file"] == "report.xlsx"
        assert payload["results"][0]["output_files"] == ["report.xlsx", "report.json", "report.html"]

    def test_run_summary_all_format_subprocess_preserves_output_files(self, tmp_path):
        """E2E: subprocess run-summary contract should preserve additive output_files for --format all."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        summary_file = tmp_path / "run_summary_all_subprocess.json"
        script = textwrap.dedent(
            f"""
            import sys
            from unittest.mock import patch

            from cja_auto_sdr.generator import ProcessingResult, main

            summary_file = {str(summary_file)!r}
            result = ProcessingResult(
                data_view_id="dv_test",
                data_view_name="Test View",
                success=True,
                duration=0.25,
                metrics_count=10,
                dimensions_count=12,
                dq_issues_count=0,
                dq_issues=[],
                dq_severity_counts={{}},
                output_file="report.xlsx",
                output_files=["report.xlsx", "report.json", "report.html"],
                file_size_bytes=2048,
            )

            with (
                patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_test"], {{}})),
                patch("cja_auto_sdr.generator.process_single_dataview", return_value=result),
                patch.object(
                    sys,
                    "argv",
                    ["cja_auto_sdr", "dv_test", "--format", "all", "--run-summary-json", summary_file],
                ),
            ):
                main()
            """,
        )

        result = subprocess.run(
            ["uv", "run", "python", "-c", script],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["output_format"] == "all"
        assert payload["results"][0]["output_file"] == "report.xlsx"
        assert payload["results"][0]["output_files"] == ["report.xlsx", "report.json", "report.html"]


@pytest.mark.run_summary_contract
class TestOpenOutputArtifacts(TestRunSummaryOutput):
    """Tests for opening normalized emitted artifact paths."""

    @patch("cja_auto_sdr.generator.open_file_in_default_app")
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_single_mode_open_uses_all_emitted_output_files(self, mock_resolve, mock_process, mock_open):
        """Single-mode --open should consume additive output_files when present."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_test"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=True,
            duration=0.25,
            metrics_count=10,
            dimensions_count=12,
            dq_issues_count=0,
            dq_issues=[],
            dq_severity_counts={},
            output_file="report.xlsx",
            output_files=["report.xlsx", "report.json", "report.html"],
            file_size_bytes=2048,
        )
        mock_open.return_value = True

        with patch.object(sys, "argv", ["cja_auto_sdr", "dv_test", "--open", "--format", "all"]):
            main()

        assert mock_open.call_count == 3
        assert [call.args[0] for call in mock_open.call_args_list] == ["report.xlsx", "report.json", "report.html"]

    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_run_summary_written_for_policy_exit(self, mock_resolve, mock_process, tmp_path):
        """Policy exits should still write run summary with quality gate status."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_test"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=True,
            duration=0.1,
            dq_issues_count=1,
            dq_issues=[{"Severity": "HIGH", "Issue": "Duplicate component"}],
            dq_severity_counts={"HIGH": 1},
        )

        summary_file = tmp_path / "run_summary_policy.json"
        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "dv_test", "--fail-on-quality", "HIGH", "--run-summary-json", str(summary_file)],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 2
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["exit_code"] == 2
        assert payload["status"] == "policy_exit"
        assert payload["quality_gate_failed"] is True

    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_run_summary_includes_stable_failure_identity(self, mock_resolve, mock_process, tmp_path):
        """Failed SDR results should expose stable failure code/reason and rollups."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_test"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=False,
            duration=0.2,
            error_message="Component fetch failed: metrics: timeout",
            failure_code="COMPONENT_FETCH_FAILED",
            failure_reason="required_endpoints_failed:metrics",
        )

        summary_file = tmp_path / "run_summary_failure_identity.json"
        with patch.object(sys, "argv", ["cja_auto_sdr", "dv_test", "--run-summary-json", str(summary_file)]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["status"] == "error"
        assert payload["result_counts"]["failed"] == 1
        assert payload["results"][0]["failure_code"] == "COMPONENT_FETCH_FAILED"
        assert payload["results"][0]["failure_reason"] == "required_endpoints_failed:metrics"
        assert payload["failure_rollups"]["by_code"] == {"COMPONENT_FETCH_FAILED": 1}
        assert payload["failure_rollups"]["by_reason"] == {"required_endpoints_failed:metrics": 1}

    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_run_summary_includes_partial_output_fields(self, mock_resolve, mock_process, tmp_path):
        """Allow-partial SDR outputs should surface partial_output and partial_reasons per result."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_test"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=True,
            duration=0.2,
            partial_output=True,
            partial_reasons=[
                "required_endpoints_failed:metrics",
                "data_quality_validation_runtime_failed",
            ],
        )

        summary_file = tmp_path / "run_summary_partial_output.json"
        with patch.object(
            sys,
            "argv",
            [
                "cja_auto_sdr",
                "dv_test",
                "--allow-partial",
                "--run-summary-json",
                str(summary_file),
            ],
        ):
            main()

        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["allow_partial"] is True
        assert payload["results"][0]["partial_output"] is True
        assert payload["results"][0]["partial_reasons"] == [
            "required_endpoints_failed:metrics",
            "data_quality_validation_runtime_failed",
        ]

    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.BatchProcessor.print_summary")
    @patch("cja_auto_sdr.generator.ProcessPoolExecutor")
    @patch("cja_auto_sdr.generator.tqdm")
    def test_run_summary_batch_failure_rollups_mixed_results_under_concurrent_completion(
        self,
        mock_tqdm,
        mock_executor_cls,
        _mock_print_summary,
        mock_resolve,
        tmp_path,
    ):
        """Batch-mode run summary should aggregate failure_rollups with mixed out-of-order future completion."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_ok", "dv_fetch_fail", "dv_validation_fail"], {})

        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        future_ok = Mock()
        future_fetch_fail = Mock()
        future_validation_fail = Mock()

        future_ok.result.return_value = ProcessingResult(
            data_view_id="dv_ok",
            data_view_name="Healthy View",
            success=True,
            duration=0.2,
            dq_issues_count=1,
            dq_issues=[{"Severity": "HIGH", "Issue": "threshold"}],
            dq_severity_counts={"HIGH": 1},
        )
        future_fetch_fail.result.return_value = ProcessingResult(
            data_view_id="dv_fetch_fail",
            data_view_name="Fetch Fail View",
            success=False,
            duration=0.3,
            error_message="Component fetch failed: metrics: timeout",
            failure_code="COMPONENT_FETCH_FAILED",
            failure_reason="required_endpoints_failed:metrics",
        )
        future_validation_fail.result.return_value = ProcessingResult(
            data_view_id="dv_validation_fail",
            data_view_name="Validation Fail View",
            success=False,
            duration=0.3,
            error_message="Data quality validation failed: threadpool failure",
            failure_code="DQ_VALIDATION_RUNTIME_FAILED",
            failure_reason="data_quality_validation_runtime_failed",
        )

        mock_executor = MagicMock()
        mock_executor.__enter__ = Mock(return_value=mock_executor)
        mock_executor.__exit__ = Mock(return_value=False)
        mock_executor.submit.side_effect = [future_ok, future_fetch_fail, future_validation_fail]
        mock_executor_cls.return_value = mock_executor

        summary_file = tmp_path / "run_summary_batch_rollups.json"
        with (
            patch(
                "cja_auto_sdr.generator.as_completed",
                return_value=[future_validation_fail, future_ok, future_fetch_fail],
            ),
            patch("cja_auto_sdr.generator.setup_logging", return_value=Mock()),
            patch.object(
                sys,
                "argv",
                [
                    "cja_auto_sdr",
                    "dv_ok",
                    "dv_fetch_fail",
                    "dv_validation_fail",
                    "--batch",
                    "--workers",
                    "2",
                    "--continue-on-error",
                    "--fail-on-quality",
                    "HIGH",
                    "--run-summary-json",
                    str(summary_file),
                ],
            ),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["result_counts"]["failed"] == 2
        assert payload["failure_rollups"]["by_code"] == {
            "COMPONENT_FETCH_FAILED": 1,
            "DQ_VALIDATION_RUNTIME_FAILED": 1,
        }
        assert payload["failure_rollups"]["by_reason"] == {
            "data_quality_validation_runtime_failed": 1,
            "required_endpoints_failed:metrics": 1,
        }

    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.BatchProcessor.print_summary")
    @patch("cja_auto_sdr.generator.ProcessPoolExecutor")
    @patch("cja_auto_sdr.generator.tqdm")
    def test_run_summary_batch_mixed_results_preserves_success_output_files(
        self,
        mock_tqdm,
        mock_executor_cls,
        _mock_print_summary,
        mock_resolve,
        tmp_path,
    ):
        """Batch-mode run summary should preserve additive output_files for successful entries even when failures exist."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_ok", "dv_fail"], {})

        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        future_ok = Mock()
        future_fail = Mock()

        future_ok.result.return_value = ProcessingResult(
            data_view_id="dv_ok",
            data_view_name="Healthy View",
            success=True,
            duration=0.2,
            metrics_count=10,
            dimensions_count=12,
            dq_issues_count=0,
            dq_issues=[],
            dq_severity_counts={},
            output_file="ok.xlsx",
            output_files=["ok.json", "ok.xlsx", "ok.html", "ok.json"],
            file_size_bytes=2048,
        )
        future_fail.result.return_value = ProcessingResult(
            data_view_id="dv_fail",
            data_view_name="Fail View",
            success=False,
            duration=0.3,
            error_message="Component fetch failed: metrics: timeout",
            failure_code="COMPONENT_FETCH_FAILED",
            failure_reason="required_endpoints_failed:metrics",
        )

        mock_executor = MagicMock()
        mock_executor.__enter__ = Mock(return_value=mock_executor)
        mock_executor.__exit__ = Mock(return_value=False)
        mock_executor.submit.side_effect = [future_ok, future_fail]
        mock_executor_cls.return_value = mock_executor

        summary_file = tmp_path / "run_summary_batch_outputs.json"
        with (
            patch("cja_auto_sdr.generator.as_completed", return_value=[future_fail, future_ok]),
            patch("cja_auto_sdr.generator.setup_logging", return_value=Mock()),
            patch.object(
                sys,
                "argv",
                [
                    "cja_auto_sdr",
                    "dv_ok",
                    "dv_fail",
                    "--batch",
                    "--workers",
                    "2",
                    "--continue-on-error",
                    "--run-summary-json",
                    str(summary_file),
                ],
            ),
        ):
            main()

        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        results_by_id = {result["data_view_id"]: result for result in payload["results"]}
        assert results_by_id["dv_ok"]["output_file"] == "ok.xlsx"
        assert results_by_id["dv_ok"]["output_files"] == ["ok.xlsx", "ok.json", "ok.html"]
        assert results_by_id["dv_fail"]["output_files"] == []

    @patch("cja_auto_sdr.generator.list_dataviews")
    def test_run_summary_written_for_discovery_mode(self, mock_list_dataviews, tmp_path):
        """Discovery mode should write summary even when exiting via SystemExit."""
        from cja_auto_sdr.generator import main

        mock_list_dataviews.return_value = True
        summary_file = tmp_path / "run_summary_discovery.json"

        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "--list-dataviews", "--run-summary-json", str(summary_file)],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "discovery"
        assert payload["exit_code"] == 0
        assert payload["details"]["discovery_command"] == "list_dataviews"

    @patch("cja_auto_sdr.generator.list_dataviews")
    def test_run_summary_non_sdr_quality_policy_is_not_applied(self, mock_list_dataviews, tmp_path):
        """Run summary should record quality policy path but keep applied defaults empty in non-SDR modes."""
        from cja_auto_sdr.generator import main

        policy_path = tmp_path / "quality_policy.json"
        policy_path.write_text(
            json.dumps({"fail_on_quality": "HIGH", "quality_report": "csv", "max_issues": 5}),
            encoding="utf-8",
        )
        mock_list_dataviews.return_value = True
        summary_file = tmp_path / "run_summary_discovery_quality_policy.json"

        with patch.object(
            sys,
            "argv",
            [
                "cja_auto_sdr",
                "--list-dataviews",
                "--quality-policy",
                str(policy_path),
                "--run-summary-json",
                str(summary_file),
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "discovery"
        assert payload["quality_policy"]["path"] == str(policy_path)
        assert payload["quality_policy"]["applied"] == {}

    @patch("cja_auto_sdr.generator.run_org_report")
    @patch("cja_auto_sdr.generator.list_dataviews")
    def test_run_summary_mode_precedence_matches_dispatch_order(
        self,
        mock_list_dataviews,
        mock_run_org_report,
        tmp_path,
    ):
        """When multiple mode flags are present, summary mode should match the first dispatch branch."""
        from cja_auto_sdr.generator import main

        mock_list_dataviews.return_value = True
        summary_file = tmp_path / "run_summary_mode_precedence.json"

        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "--list-dataviews", "--org-report", "--run-summary-json", str(summary_file)],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "discovery"
        assert payload["details"]["discovery_command"] == "list_dataviews"
        mock_list_dataviews.assert_called_once()
        mock_run_org_report.assert_not_called()

    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_run_summary_stdout_is_json_only(self, mock_resolve, mock_process, capsys):
        """--run-summary-json stdout should emit parseable JSON on stdout."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_test"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=True,
            duration=0.1,
            metrics_count=1,
            dimensions_count=1,
            dq_issues_count=0,
            dq_issues=[],
            dq_severity_counts={},
        )

        with patch.object(sys, "argv", ["cja_auto_sdr", "dv_test", "--run-summary-json", "stdout"]):
            main()

        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "sdr"
        assert payload["exit_code"] == 0

    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.interactive_wizard")
    def test_run_summary_interactive_refreshes_data_view_inputs(
        self,
        mock_wizard,
        mock_resolve,
        mock_process,
        tmp_path,
    ):
        """Interactive runs should record wizard-selected data view inputs in run summary."""
        from cja_auto_sdr.generator import ProcessingResult, WizardConfig, main

        mock_wizard.return_value = WizardConfig(
            data_view_ids=["dv_wizard_selected"],
            output_format="excel",
            include_segments=False,
            include_calculated=False,
            include_derived=False,
            inventory_only=False,
        )
        mock_resolve.return_value = (["dv_wizard_selected"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_wizard_selected",
            data_view_name="Wizard Selected",
            success=True,
            duration=0.1,
            metrics_count=1,
            dimensions_count=1,
            dq_issues_count=0,
            dq_issues=[],
            dq_severity_counts={},
        )

        summary_file = tmp_path / "run_summary_interactive_inputs.json"
        with patch.object(sys, "argv", ["cja_auto_sdr", "--interactive", "--run-summary-json", str(summary_file)]):
            main()

        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "sdr"
        assert payload["inputs"]["data_view_inputs"] == ["dv_wizard_selected"]

    @patch("cja_auto_sdr.generator.list_dataviews")
    def test_run_summary_stdout_with_abbreviated_flag_is_json_only(self, mock_list_dataviews, capsys):
        """Abbreviated --run-summary-json should still redirect normal stdout chatter."""
        from cja_auto_sdr.generator import main

        def _mock_list_dataviews(*args, **kwargs):
            print("discovery table output")
            return True

        mock_list_dataviews.side_effect = _mock_list_dataviews

        with patch.object(sys, "argv", ["cja_auto_sdr", "--list-dataviews", "--run-summary-j", "stdout"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "discovery"
        assert payload["exit_code"] == 0
        assert "discovery table output" not in captured.out
        assert "discovery table output" in captured.err

    def test_run_summary_stdout_json_only_subprocess_exit_codes_full_flag(self):
        """E2E: full flag should keep stdout as JSON-only in chatty exit-codes mode."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        result = subprocess.run(
            ["uv", "run", "cja_auto_sdr", "--exit-codes", "--run-summary-json", "stdout"],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "exit_codes"
        assert "EXIT CODE REFERENCE" not in result.stdout
        assert "EXIT CODE REFERENCE" in result.stderr

    def test_run_summary_stdout_json_only_subprocess_exit_codes_abbreviated_flag(self):
        """E2E: abbreviated flag should keep stdout as JSON-only in chatty exit-codes mode."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        result = subprocess.run(
            ["uv", "run", "cja_auto_sdr", "--exit-codes", "--run-summary-j", "stdout"],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "exit_codes"
        assert "EXIT CODE REFERENCE" not in result.stdout
        assert "EXIT CODE REFERENCE" in result.stderr

    def test_run_summary_exit_codes_ignored_allow_partial_reports_false(self, tmp_path):
        """Ignored standalone flags should not survive into run-summary telemetry."""
        from cja_auto_sdr.generator import main

        summary_file = tmp_path / "run_summary_exit_codes_allow_partial_ignored.json"
        with patch.object(
            sys,
            "argv",
            [
                "cja_auto_sdr",
                "--exit-codes",
                "--allow-partial",
                "--run-summary-json",
                str(summary_file),
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "exit_codes"
        assert payload["status"] == "success"
        assert payload["allow_partial"] is False

    def test_run_summary_completion_mode_classification(self, tmp_path):
        """Completion runs should emit run summary mode=completion."""
        from cja_auto_sdr.generator import main

        summary_file = tmp_path / "run_summary_completion.json"
        fake_argcomplete = type(sys)("argcomplete")

        with (
            patch.object(
                sys,
                "argv",
                ["cja_auto_sdr", "--completion", "bash", "--run-summary-json", str(summary_file)],
            ),
            patch.dict("sys.modules", {"argcomplete": fake_argcomplete}),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "completion"
        assert payload["exit_code"] == 0
        assert payload["status"] == "success"

    def test_run_summary_exit_codes_precedes_completion_mode_classification(self, tmp_path):
        """Mixed --exit-codes/--completion should preserve exit-codes summary mode."""
        from cja_auto_sdr.generator import main

        summary_file = tmp_path / "run_summary_exit_codes_precedes_completion.json"
        with (
            patch.object(
                sys,
                "argv",
                [
                    "cja_auto_sdr",
                    "--exit-codes",
                    "--completion",
                    "bash",
                    "--run-summary-json",
                    str(summary_file),
                ],
            ),
            patch("cja_auto_sdr.core.exit_codes.print_exit_codes") as mock_print_exit_codes,
            patch("cja_auto_sdr.generator._handle_completion_prevalidation") as mock_completion_prevalidation,
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "exit_codes"
        assert payload["exit_code"] == 0
        assert payload["status"] == "success"
        mock_print_exit_codes.assert_called_once()
        mock_completion_prevalidation.assert_not_called()

    def test_run_summary_stdout_subprocess_version_is_order_independent(self):
        """E2E: --version should still emit run summary JSON regardless of flag order."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        commands = [
            ["uv", "run", "cja_auto_sdr", "--version", "--run-summary-json", "stdout"],
            ["uv", "run", "cja_auto_sdr", "--run-summary-json", "stdout", "--version"],
            ["uv", "run", "cja_auto_sdr", "-V", "--run-summary-json", "stdout"],
            ["uv", "run", "cja_auto_sdr", "--run-summary-json", "stdout", "-V"],
            ["uv", "run", "cja_auto_sdr", "--version", "--profile", "--run-summary-json", "stdout"],
        ]

        for cmd in commands:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=repo_root,
            )
            assert result.returncode == 0
            payload = json.loads(result.stdout)
            self._assert_run_summary_schema(payload)
            assert payload["exit_code"] == 0
            assert payload["mode"] == "unknown"
            assert "cja_auto_sdr " not in result.stdout
            assert "cja_auto_sdr " in result.stderr

    def test_module_invocation_version_banner_consistent_with_and_without_run_summary(self):
        """`python -m cja_auto_sdr --version` should keep the same banner prefix across paths."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        fast_path = subprocess.run(
            ["uv", "run", "python", "-m", "cja_auto_sdr", "--version"],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        assert fast_path.returncode == 0
        assert " -m cja_auto_sdr " in fast_path.stdout
        fast_prefix = fast_path.stdout.strip().split(" -m cja_auto_sdr ")[0]

        fallback = subprocess.run(
            ["uv", "run", "python", "-m", "cja_auto_sdr", "--version", "--run-summary-json", "stdout"],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        assert fallback.returncode == 0
        payload = json.loads(fallback.stdout)
        self._assert_run_summary_schema(payload)
        assert payload["exit_code"] == 0
        assert f"{fast_prefix} -m cja_auto_sdr " in fallback.stderr

    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_run_summary_records_inferred_output_format(self, mock_resolve, mock_process, tmp_path):
        """Run summary should capture format inferred from --output extension."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_test"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=True,
            duration=0.1,
            metrics_count=1,
            dimensions_count=1,
            dq_issues_count=0,
            dq_issues=[],
            dq_severity_counts={},
            output_file="report.csv",
        )

        summary_file = tmp_path / "run_summary_inferred.json"
        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "dv_test", "--output", "report.csv", "--run-summary-json", str(summary_file)],
        ):
            main()

        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["output_format"] == "csv"

    @patch("cja_auto_sdr.generator.write_quality_report_output")
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_run_summary_quality_report_uses_quality_report_format(
        self,
        mock_resolve,
        mock_process,
        mock_write_report,
        tmp_path,
    ):
        """Run summary output_format should reflect --quality-report format, not internal SDR writer format."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_test"], {})
        mock_write_report.return_value = "stdout"
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=True,
            duration=0.1,
            dq_issues_count=1,
            dq_issues=[{"Severity": "LOW", "Issue": "Minor"}],
            dq_severity_counts={"LOW": 1},
        )

        summary_file = tmp_path / "run_summary_quality_report_format.json"
        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "dv_test", "--quality-report", "csv", "--run-summary-json", str(summary_file)],
        ):
            main()

        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "sdr"
        assert payload["output_format"] == "csv"

    @patch("cja_auto_sdr.generator.process_inventory_summary")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_run_summary_inventory_summary_mode_and_output_format(self, mock_resolve, mock_inventory_summary, tmp_path):
        """Inventory summary runs should report mode=inventory_summary with effective summary output format."""
        from cja_auto_sdr.generator import main

        mock_resolve.return_value = (["dv_test"], {})
        mock_inventory_summary.return_value = {}
        summary_file = tmp_path / "run_summary_inventory_summary.json"

        with patch.object(
            sys,
            "argv",
            [
                "cja_auto_sdr",
                "dv_test",
                "--include-segments",
                "--inventory-summary",
                "--run-summary-json",
                str(summary_file),
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "inventory_summary"
        assert payload["output_format"] == "console"

    @patch("cja_auto_sdr.generator.process_inventory_summary")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_inventory_summary_propagates_log_format(self, mock_resolve, mock_inventory_summary):
        """Inventory summary mode should pass --log-format to process_inventory_summary."""
        from cja_auto_sdr.generator import main

        mock_resolve.return_value = (["dv_test"], {})
        mock_inventory_summary.return_value = {}

        with patch.object(
            sys,
            "argv",
            [
                "cja_auto_sdr",
                "dv_test",
                "--include-segments",
                "--inventory-summary",
                "--log-format",
                "json",
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        assert mock_inventory_summary.call_count == 1
        assert mock_inventory_summary.call_args.kwargs["log_format"] == "json"

    @patch("cja_auto_sdr.generator.git_init_snapshot_repo")
    def test_run_summary_git_init_mode(self, mock_git_init, tmp_path):
        """Run summary should classify --git-init runs with git_init mode."""
        from cja_auto_sdr.generator import main

        mock_git_init.return_value = (True, "initialized")
        summary_file = tmp_path / "run_summary_git_init.json"

        with patch.object(
            sys,
            "argv",
            [
                "cja_auto_sdr",
                "--git-init",
                "--git-dir",
                str(tmp_path / "repo"),
                "--run-summary-json",
                str(summary_file),
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "git_init"
        assert payload["status"] == "success"

    def test_run_summary_invalid_cli_status_is_error(self, tmp_path):
        """Argparse usage errors (exit 2) should be reported as status=error, not policy_exit."""
        from cja_auto_sdr.generator import main

        summary_file = tmp_path / "run_summary_cli_error.json"
        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "--definitely-invalid-flag", "--run-summary-json", str(summary_file)],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 2
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["status"] == "error"
        assert payload["exit_code"] == 2

    def test_run_summary_invalid_quality_policy_preserves_inferred_mode(self, tmp_path):
        """Policy-load failures should still emit run summary with inferred mode metadata."""
        from cja_auto_sdr.generator import main

        summary_file = tmp_path / "run_summary_quality_policy_error.json"
        missing_policy = tmp_path / "missing_quality_policy.json"

        with patch.object(
            sys,
            "argv",
            [
                "cja_auto_sdr",
                "--list-dataviews",
                "--quality-policy",
                str(missing_policy),
                "--run-summary-json",
                str(summary_file),
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "discovery"
        assert payload["status"] == "error"
        assert payload["quality_policy"]["path"] == str(missing_policy)
        assert payload["quality_policy"]["applied"] == {}

    def test_run_summary_policy_applied_allow_partial_survives_early_validation_exit(self, tmp_path):
        """Policy-mutated allow_partial should be synced before later CLI validation exits."""
        from cja_auto_sdr.generator import main

        summary_file = tmp_path / "run_summary_policy_allow_partial_validation_error.json"
        policy_file = tmp_path / "quality_policy.json"
        policy_file.write_text(json.dumps({"allow_partial": True}), encoding="utf-8")

        with patch.object(
            sys,
            "argv",
            [
                "cja_auto_sdr",
                "dv_test",
                "--quality-policy",
                str(policy_file),
                "--workers",
                "0",
                "--run-summary-json",
                str(summary_file),
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "sdr"
        assert payload["status"] == "error"
        assert payload["allow_partial"] is True
        assert payload["quality_policy"]["path"] == str(policy_file)
        assert payload["quality_policy"]["applied"] == {"allow_partial": True}

    def test_run_summary_profile_overwrite_validation_error_mode(self, tmp_path):
        """Profile overwrite validation failures should still be classified as profile_management mode."""
        from cja_auto_sdr.generator import main

        summary_file = tmp_path / "run_summary_profile_overwrite_error.json"
        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "--profile-overwrite", "--run-summary-json", str(summary_file)],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "profile_management"
        assert payload["status"] == "error"

    def test_run_summary_non_sdr_allow_partial_validation_preserves_flag(self, tmp_path):
        """Early non-SDR validation errors should preserve allow_partial telemetry."""
        from cja_auto_sdr.generator import main

        summary_file = tmp_path / "run_summary_non_sdr_allow_partial_error.json"
        with patch.object(
            sys,
            "argv",
            [
                "cja_auto_sdr",
                "--list-dataviews",
                "--allow-partial",
                "--run-summary-json",
                str(summary_file),
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "discovery"
        assert payload["status"] == "error"
        assert payload["allow_partial"] is True

    def test_run_summary_argparse_error_preserves_allow_partial_flag(self, tmp_path):
        """Argparse failures should still preserve allow_partial telemetry from argv."""
        from cja_auto_sdr.generator import main

        summary_file = tmp_path / "run_summary_argparse_allow_partial_error.json"
        with patch.object(
            sys,
            "argv",
            [
                "cja_auto_sdr",
                "--allow-partial",
                "--definitely-invalid-flag",
                "--run-summary-json",
                str(summary_file),
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 2
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "unknown"
        assert payload["status"] == "error"
        assert payload["allow_partial"] is True

    def test_run_summary_missing_value_does_not_write_flag_named_file(self, tmp_path, monkeypatch):
        """Malformed --run-summary-json should not treat the next flag as an output path."""
        from cja_auto_sdr.generator import main

        bad_output_name = "--list-dataviews"
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["cja_auto_sdr", "--run-summary-json", "--list-dataviews"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 2
        assert not (tmp_path / bad_output_name).exists()

    def test_cli_option_value_uses_last_valid_occurrence(self):
        """Raw option helper should align with argparse 'last value wins' behavior."""
        from cja_auto_sdr.generator import _cli_option_value

        value = _cli_option_value(
            "--run-summary-json",
            [
                "--run-summary-json",
                "stdout",
                "--run-summary-json",
                "summary.json",
            ],
        )
        assert value == "summary.json"

    def test_cli_option_value_accepts_unambiguous_long_option_abbreviation(self):
        """Raw option helper should resolve argparse-accepted long-option abbreviations."""
        from cja_auto_sdr.generator import _cli_option_value

        value = _cli_option_value("--run-summary-json", ["--run-summary-j", "stdout"])
        assert value == "stdout"

    @pytest.mark.parametrize(
        ("argv", "expected"),
        [
            (["--run-summary-json", "stdout"], "stdout"),
            (["--run-summary-j", "stdout"], "stdout"),
            (["--run-summary-j=stdout"], "stdout"),
            (["--run-summary-json", "--list-dataviews"], None),
            (["--run-summary-j", "--list-dataviews"], None),
            (["--run-summary-json", "stdout", "--run-summary-j", "summary.json"], "summary.json"),
            (["--run-summary-json=stdout", "--run-summary-j=summary.json"], "summary.json"),
            (["--run-summary-json", "stdout", "--run-summary-json"], "stdout"),
        ],
    )
    def test_cli_option_value_permutations(self, argv, expected):
        """Raw option helper should stay aligned with argparse-style option permutations."""
        from cja_auto_sdr.generator import _cli_option_value

        assert _cli_option_value("--run-summary-json", argv) == expected

    @pytest.mark.parametrize(
        ("option_name", "argv", "expected"),
        [
            ("--run-summary-json", ["--run-summary-j", "stdout"], True),
            ("--max-issues", ["--max-i=10"], True),
            ("--fail-on-quality", ["--fail-on-q", "HIGH"], True),
            ("--profile", ["--pro"], False),
            ("--run-summary-json", ["-q"], False),
        ],
    )
    def test_cli_option_specified_permutations(self, option_name, argv, expected):
        """Explicit option detection should follow argparse abbreviation semantics."""
        from cja_auto_sdr.generator import _cli_option_specified

        assert _cli_option_specified(option_name, argv) is expected


class TestMergeRunDetails:
    def test_adds_new_key(self):
        run_state = {"details": {}}
        _merge_run_details(run_state, execution_settings={"a": 1})
        assert run_state["details"]["execution_settings"] == {"a": 1}

    def test_does_not_overwrite_existing_key(self):
        run_state = {"details": {"execution_settings": {"original": True}}}
        _merge_run_details(run_state, execution_settings={"replaced": True})
        assert run_state["details"]["execution_settings"] == {"original": True}

    def test_preserves_existing_operation_success(self):
        run_state = {"details": {"operation_success": True}}
        _merge_run_details(run_state, execution_settings={"a": 1})
        assert run_state["details"]["operation_success"] is True
        assert run_state["details"]["execution_settings"] == {"a": 1}

    def test_creates_details_if_missing(self):
        run_state = {}
        _merge_run_details(run_state, lock={"acquired": True})
        assert run_state["details"]["lock"] == {"acquired": True}

    def test_none_run_state_is_noop(self):
        _merge_run_details(None, execution_settings={"a": 1})

    def test_merges_multiple_new_keys(self):
        run_state = {"details": {}}
        _merge_run_details(run_state, execution_settings={"a": 1}, lock={"b": 2})
        assert run_state["details"]["execution_settings"] == {"a": 1}
        assert run_state["details"]["lock"] == {"b": 2}

    def test_only_adds_missing_keys(self):
        run_state = {"details": {"lock": {"existing": True}}}
        _merge_run_details(run_state, lock={"new": True}, execution_settings={"x": 1})
        assert run_state["details"]["lock"] == {"existing": True}
        assert run_state["details"]["execution_settings"] == {"x": 1}


# ==================== normalize_quality_severity ====================


class TestNormalizeQualitySeverity:
    def test_valid_lowercase(self):
        assert normalize_quality_severity("critical") == "CRITICAL"

    def test_valid_uppercase(self):
        assert normalize_quality_severity("HIGH") == "HIGH"

    def test_valid_mixed_case(self):
        assert normalize_quality_severity("Medium") == "MEDIUM"

    def test_all_valid_levels(self):
        for level in ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"):
            assert normalize_quality_severity(level) == level

    def test_invalid_raises(self):
        with pytest.raises(ValueError, match="Invalid quality severity"):
            normalize_quality_severity("UNKNOWN")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="Invalid quality severity"):
            normalize_quality_severity("")


# ==================== count_quality_issues_by_severity ====================


class TestCountQualityIssuesBySeverity:
    def test_empty_list(self):
        assert count_quality_issues_by_severity([]) == {}

    def test_mixed_severities(self):
        issues = [
            {"Severity": "HIGH"},
            {"Severity": "HIGH"},
            {"Severity": "LOW"},
            {"Severity": "CRITICAL"},
        ]
        result = count_quality_issues_by_severity(issues)
        assert result == {"CRITICAL": 1, "HIGH": 2, "LOW": 1}

    def test_unknown_severity_ignored(self):
        issues = [
            {"Severity": "HIGH"},
            {"Severity": "BOGUS"},
        ]
        result = count_quality_issues_by_severity(issues)
        assert result == {"HIGH": 1}

    def test_missing_severity_key(self):
        issues = [{"other_field": "value"}]
        result = count_quality_issues_by_severity(issues)
        assert result == {}

    def test_lowercase_severity_treated_as_unknown(self):
        """count_quality_issues_by_severity upper-cases internally."""
        issues = [{"Severity": "high"}]
        result = count_quality_issues_by_severity(issues)
        assert result == {"HIGH": 1}


# ==================== has_quality_issues_at_or_above ====================


class TestHasQualityIssuesAtOrAbove:
    def test_critical_above_info(self):
        issues = [{"Severity": "CRITICAL"}]
        assert has_quality_issues_at_or_above(issues, "INFO") is True

    def test_info_not_above_critical(self):
        issues = [{"Severity": "INFO"}]
        assert has_quality_issues_at_or_above(issues, "CRITICAL") is False

    def test_exact_threshold_match(self):
        issues = [{"Severity": "MEDIUM"}]
        assert has_quality_issues_at_or_above(issues, "MEDIUM") is True

    def test_empty_issues(self):
        assert has_quality_issues_at_or_above([], "LOW") is False

    def test_high_above_medium(self):
        issues = [{"Severity": "HIGH"}]
        assert has_quality_issues_at_or_above(issues, "MEDIUM") is True

    def test_low_not_above_high(self):
        issues = [{"Severity": "LOW"}]
        assert has_quality_issues_at_or_above(issues, "HIGH") is False

    def test_invalid_threshold_raises(self):
        with pytest.raises(ValueError, match="Invalid quality severity"):
            has_quality_issues_at_or_above([], "BOGUS")

    def test_case_insensitive_threshold(self):
        issues = [{"Severity": "HIGH"}]
        assert has_quality_issues_at_or_above(issues, "high") is True

    def test_all_severity_boundaries(self):
        """Verify rank ordering: CRITICAL < HIGH < MEDIUM < LOW < INFO."""
        ordered = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
        for i, severity in enumerate(ordered):
            issues = [{"Severity": severity}]
            # Should match at own level and all levels below (higher index)
            for j, threshold in enumerate(ordered):
                expected = i <= j
                assert has_quality_issues_at_or_above(issues, threshold) is expected, (
                    f"severity={severity}, threshold={threshold}"
                )


# ==================== aggregate_quality_issues ====================


class TestAggregateQualityIssues:
    def _make_result(self, dv_id, dv_name, issues):
        return ProcessingResult(
            data_view_id=dv_id,
            data_view_name=dv_name,
            success=True,
            duration=1.0,
            dq_issues=issues,
        )

    def test_empty_results(self):
        assert aggregate_quality_issues([]) == []

    def test_single_result_no_issues(self):
        result = self._make_result("dv1", "Test View", [])
        assert aggregate_quality_issues([result]) == []

    def test_adds_data_view_context(self):
        issues = [{"Severity": "HIGH", "Message": "test"}]
        result = self._make_result("dv1", "Test View", issues)
        aggregated = aggregate_quality_issues([result])
        assert len(aggregated) == 1
        assert aggregated[0]["Data View ID"] == "dv1"
        assert aggregated[0]["Data View Name"] == "Test View"
        assert aggregated[0]["Severity"] == "HIGH"

    def test_multiple_results_flattened(self):
        r1 = self._make_result("dv1", "View 1", [{"Severity": "HIGH"}])
        r2 = self._make_result("dv2", "View 2", [{"Severity": "LOW"}, {"Severity": "MEDIUM"}])
        aggregated = aggregate_quality_issues([r1, r2])
        assert len(aggregated) == 3

    def test_preserves_existing_context(self):
        """If issue already has Data View ID, it should NOT be overwritten."""
        issues = [{"Severity": "HIGH", "Data View ID": "original"}]
        result = self._make_result("dv1", "View 1", issues)
        aggregated = aggregate_quality_issues([result])
        assert aggregated[0]["Data View ID"] == "original"


class TestBuildQualityStepSummary:
    def _make_result(
        self,
        dv_id,
        dv_name,
        *,
        success=True,
        dq_issues=None,
        dq_severity_counts=None,
        dq_issues_count=None,
    ):
        issues = dq_issues or []
        return ProcessingResult(
            data_view_id=dv_id,
            data_view_name=dv_name,
            success=success,
            duration=1.0,
            dq_issues=issues,
            dq_issues_count=len(issues) if dq_issues_count is None else dq_issues_count,
            dq_severity_counts=dq_severity_counts or {},
        )

    def test_renders_severity_counts_in_contract_order_and_highest_severity_per_view(self):
        from cja_auto_sdr.output.run_summary import build_quality_step_summary

        primary = self._make_result(
            "dv_primary",
            "Primary View",
            dq_issues=[{"Severity": "LOW"}, {"Severity": "HIGH"}],
            dq_severity_counts={"HIGH": 1, "LOW": 1},
        )
        secondary = self._make_result(
            "dv_secondary",
            "Secondary View",
            dq_issues=[{"Severity": "CRITICAL"}, {"Severity": "MEDIUM"}],
            dq_severity_counts={"CRITICAL": 1, "MEDIUM": 1},
        )
        failed = self._make_result("dv_failed", "", success=False, dq_issues=[], dq_severity_counts={})

        summary = build_quality_step_summary([primary, secondary, failed])

        assert "### Data Quality Summary" in summary
        assert "- Data views processed: 2/3" in summary
        assert "- Total quality issues: 4" in summary
        assert summary.index("| CRITICAL | 1 |") < summary.index("| HIGH | 1 |")
        assert summary.index("| HIGH | 1 |") < summary.index("| MEDIUM | 1 |")
        assert summary.index("| MEDIUM | 1 |") < summary.index("| LOW | 1 |")
        assert "| Primary View | `dv_primary` | 2 | HIGH |" in summary
        assert "| Secondary View | `dv_secondary` | 2 | CRITICAL |" in summary
        assert "| - | `dv_failed` | 0 | NONE |" in summary

    def test_omits_severity_rollup_table_when_no_issues_exist(self):
        from cja_auto_sdr.output.run_summary import build_quality_step_summary

        summary = build_quality_step_summary([self._make_result("dv_clean", "Clean View", dq_issues=[])])

        assert "- Data views processed: 1/1" in summary
        assert "- Total quality issues: 0" in summary
        assert "| Severity | Count |" not in summary
        assert "| Clean View | `dv_clean` | 0 | NONE |" in summary

    def test_generator_wrapper_respects_generator_level_aggregate_patch(self):
        from cja_auto_sdr import generator

        clean = self._make_result("dv_clean", "Clean View", dq_issues=[])

        with patch(
            "cja_auto_sdr.generator.aggregate_quality_issues",
            return_value=[{"Severity": "HIGH", "Message": "patched"}],
        ) as aggregate_mock:
            summary = generator.build_quality_step_summary([clean])

        aggregate_mock.assert_called_once_with([clean])
        assert "- Total quality issues: 1" in summary
        assert "| HIGH | 1 |" in summary


# ==================== load_quality_policy ====================


class TestLoadQualityPolicy:
    def test_valid_policy_file(self, tmp_path):
        policy = {"fail_on_quality": "HIGH", "quality_report": "json"}
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(json.dumps(policy))
        result = load_quality_policy(policy_file)
        assert result["fail_on_quality"] == "HIGH"
        assert result["quality_report"] == "json"

    def test_nested_quality_policy_key(self, tmp_path):
        payload = {"quality_policy": {"fail_on_quality": "MEDIUM"}}
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(json.dumps(payload))
        result = load_quality_policy(policy_file)
        assert result["fail_on_quality"] == "MEDIUM"

    def test_nested_quality_key(self, tmp_path):
        payload = {"quality": {"fail_on_quality": "LOW"}}
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(json.dumps(payload))
        result = load_quality_policy(policy_file)
        assert result["fail_on_quality"] == "LOW"

    def test_file_not_found(self):
        with pytest.raises(FileNotFoundError, match="Policy file not found"):
            load_quality_policy("/nonexistent/policy.json")

    def test_invalid_json(self, tmp_path):
        policy_file = tmp_path / "bad.json"
        policy_file.write_text("not json")
        with pytest.raises(json.JSONDecodeError):
            load_quality_policy(policy_file)

    def test_non_dict_payload(self, tmp_path):
        policy_file = tmp_path / "array.json"
        policy_file.write_text('["not", "a", "dict"]')
        with pytest.raises(ValueError, match="must be a JSON object"):
            load_quality_policy(policy_file)

    def test_unknown_keys_rejected(self, tmp_path):
        policy = {"fail_on_quality": "HIGH", "unknown_key": True}
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(json.dumps(policy))
        with pytest.raises(ValueError, match="Unsupported quality policy key"):
            load_quality_policy(policy_file)

    def test_max_issues_non_negative_int(self, tmp_path):
        policy = {"max_issues": 10}
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(json.dumps(policy))
        result = load_quality_policy(policy_file)
        assert result["max_issues"] == 10

    def test_max_issues_negative_rejected(self, tmp_path):
        policy = {"max_issues": -1}
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(json.dumps(policy))
        with pytest.raises(ValueError, match="must be >= 0"):
            load_quality_policy(policy_file)

    def test_allow_partial_boolean(self, tmp_path):
        policy = {"allow_partial": True}
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(json.dumps(policy))
        result = load_quality_policy(policy_file)
        assert result["allow_partial"] is True

    @pytest.mark.parametrize("invalid_allow_partial", [1, "true", None])
    def test_allow_partial_invalid_type_rejected(self, invalid_allow_partial, tmp_path):
        policy = {"allow_partial": invalid_allow_partial}
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(json.dumps(policy))
        with pytest.raises(ValueError, match="must be a boolean"):
            load_quality_policy(policy_file)

    def test_allow_partial_incompatible_with_quality_gate_keys_rejected(self, tmp_path):
        policy = {"allow_partial": True, "fail_on_quality": "HIGH"}
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(json.dumps(policy))
        with pytest.raises(ValueError, match="cannot be combined with fail_on_quality or quality_report"):
            load_quality_policy(policy_file)

    def test_empty_fail_on_quality_rejected(self, tmp_path):
        policy = {"fail_on_quality": ""}
        policy_file = tmp_path / "policy.json"
        policy_file.write_text(json.dumps(policy))
        with pytest.raises(ValueError, match="cannot be empty"):
            load_quality_policy(policy_file)


# ==================== apply_quality_policy_defaults ====================


class TestApplyQualityPolicyDefaults:
    def test_applies_defaults_when_not_specified(self):
        args = argparse.Namespace(fail_on_quality=None, quality_report=None, max_issues=None, allow_partial=False)
        policy = {"fail_on_quality": "MEDIUM", "quality_report": "csv", "max_issues": 50, "allow_partial": False}
        applied = apply_quality_policy_defaults(args, policy, argv=["cja_auto_sdr", "dv_123"])
        assert args.fail_on_quality == "MEDIUM"
        assert args.quality_report == "csv"
        assert args.max_issues == 50
        assert args.allow_partial is False
        assert applied == {
            "fail_on_quality": "MEDIUM",
            "quality_report": "csv",
            "max_issues": 50,
            "allow_partial": False,
        }

    def test_cli_flag_overrides_policy(self):
        args = argparse.Namespace(fail_on_quality="HIGH", quality_report=None, allow_partial=False)
        policy = {"fail_on_quality": "LOW"}
        applied = apply_quality_policy_defaults(
            args,
            policy,
            argv=["cja_auto_sdr", "--fail-on-quality", "HIGH", "dv_123"],
        )
        # CLI flag was specified so policy should NOT override
        assert args.fail_on_quality == "HIGH"
        assert "fail_on_quality" not in applied

    def test_empty_policy(self):
        args = argparse.Namespace(fail_on_quality=None)
        applied = apply_quality_policy_defaults(args, {}, argv=[])
        assert applied == {}

    def test_allow_partial_applied_when_not_specified(self):
        args = argparse.Namespace(fail_on_quality=None, quality_report=None, max_issues=0, allow_partial=False)
        policy = {"allow_partial": True}
        applied = apply_quality_policy_defaults(args, policy, argv=["cja_auto_sdr", "dv_123"])
        assert args.allow_partial is True
        assert applied == {"allow_partial": True}

    def test_allow_partial_policy_not_applied_when_cli_fail_on_quality_specified(self):
        args = argparse.Namespace(fail_on_quality="HIGH", quality_report=None, max_issues=0, allow_partial=False)
        policy = {"allow_partial": True}
        applied = apply_quality_policy_defaults(
            args,
            policy,
            argv=["cja_auto_sdr", "--fail-on-quality", "HIGH", "dv_123"],
        )
        assert args.allow_partial is False
        assert applied == {}

    def test_quality_defaults_not_applied_when_allow_partial_cli_specified(self):
        args = argparse.Namespace(fail_on_quality=None, quality_report=None, max_issues=0, allow_partial=True)
        policy = {"fail_on_quality": "MEDIUM", "quality_report": "csv"}
        applied = apply_quality_policy_defaults(
            args,
            policy,
            argv=["cja_auto_sdr", "--allow-partial", "dv_123"],
        )
        assert args.fail_on_quality is None
        assert args.quality_report is None
        assert applied == {}


# ==================== _normalize_exit_code ====================


class TestNormalizeExitCode:
    def test_none_returns_zero(self):
        assert _normalize_exit_code(None) == 0

    def test_int_passthrough(self):
        assert _normalize_exit_code(0) == 0
        assert _normalize_exit_code(1) == 1
        assert _normalize_exit_code(42) == 42

    def test_bool_true(self):
        # bool is subclass of int; True -> 1
        assert _normalize_exit_code(True) == 1

    def test_bool_false(self):
        assert _normalize_exit_code(False) == 0

    def test_string_returns_one(self):
        assert _normalize_exit_code("error message") == 1

    def test_negative_int(self):
        assert _normalize_exit_code(-1) == -1


# ==================== _infer_run_status ====================


class TestInferRunStatus:
    def test_exit_code_zero_is_success(self):
        assert _infer_run_status(0, {}) == "success"

    def test_quality_gate_exit_2(self):
        run_state = {"quality_gate_failed": True}
        assert _infer_run_status(2, run_state) == "policy_exit"

    def test_org_report_threshold_exit(self):
        run_state = {
            "mode": RunMode.ORG_REPORT,
            "details": {
                "thresholds_exceeded": True,
                "fail_on_threshold": True,
            },
        }
        assert _infer_run_status(2, run_state) == "policy_exit"

    def test_diff_changes_found_exit_2(self):
        run_state = {
            "mode": RunMode.DIFF,
            "details": {"operation_success": True},
        }
        assert _infer_run_status(2, run_state) == "policy_exit"

    def test_diff_warn_threshold_exit_3(self):
        run_state = {
            "mode": RunMode.DIFF_SNAPSHOT,
            "details": {"operation_success": True},
        }
        assert _infer_run_status(3, run_state) == "policy_exit"

    def test_generic_error(self):
        assert _infer_run_status(1, {}) == "error"

    def test_exit_2_without_quality_gate_is_error(self):
        assert _infer_run_status(2, {}) == "error"

    def test_diff_failure_not_policy_exit(self):
        """If operation_success is False, exit 2 should be error, not policy_exit."""
        run_state = {
            "mode": RunMode.DIFF,
            "details": {"operation_success": False},
        }
        assert _infer_run_status(2, run_state) == "error"

    def test_explain_exit_code_mode_with_zero_exit_is_success(self):
        run_state = {"mode": RunMode.EXPLAIN_EXIT_CODE, "details": {"explained_code": 2}}
        assert _infer_run_status(0, run_state) == "success"

    def test_explain_exit_code_mode_with_nonzero_exit_is_error(self):
        run_state = {"mode": RunMode.EXPLAIN_EXIT_CODE, "details": {}}
        assert _infer_run_status(1, run_state) == "error"


class TestFailureCodeRegistry:
    def test_registry_is_unique_and_stable_shape(self):
        assert isinstance(FAILURE_CODE_REGISTRY, tuple)
        assert all(isinstance(code, str) and code for code in FAILURE_CODE_REGISTRY)
        assert len(set(FAILURE_CODE_REGISTRY)) == len(FAILURE_CODE_REGISTRY)

    def test_failure_code_docs_cover_registry(self):
        docs_path = Path(__file__).resolve().parents[1] / "docs" / "FAILURE_CODES.md"
        content = docs_path.read_text(encoding="utf-8")
        documented_codes = set(re.findall(r"`([A-Z_]+)`", content))
        undocumented = sorted(set(FAILURE_CODE_REGISTRY) - documented_codes)
        assert undocumented == []


class TestFailureIdentityNormalization:
    @pytest.mark.parametrize(
        ("error_message", "expected_code"),
        [
            ("Component fetch failed: metrics: timeout", "COMPONENT_FETCH_FAILED"),
            ("Data quality validation failed: worker exception", "DQ_VALIDATION_RUNTIME_FAILED"),
            ("Data view validation failed", "DATAVIEW_LOOKUP_INVALID"),
            ("No metrics or dimensions found - data view may be empty or inaccessible", "REQUIRED_COMPONENTS_EMPTY"),
            ("CJA initialization failed", "CJA_INIT_FAILED"),
            ("Permission denied: /tmp/report.xlsx", "OUTPUT_PERMISSION_DENIED"),
            ("Completely unknown legacy failure", "UNCLASSIFIED_FAILURE"),
        ],
    )
    def test_legacy_messages_map_to_stable_codes(self, error_message, expected_code):
        result = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=False,
            duration=0.0,
            error_message=error_message,
        )

        failure_code, failure_reason = _normalize_failure_identity(result)

        assert failure_code == expected_code
        assert failure_reason == expected_code.lower()


class TestPartialRunSummaryNormalization:
    def test_failed_partial_result_preserves_partial_output_signal(self):
        result = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=False,
            duration=0.0,
            partial_output=True,
            partial_reasons=["required_endpoints_failed:metrics"],
            error_message="Permission denied: /tmp/report.xlsx",
        )

        summary = _processing_result_to_summary(result)

        assert summary["success"] is False
        assert summary["partial_output"] is True
        assert summary["partial_reasons"] == ["required_endpoints_failed:metrics"]
        assert summary["failure_code"] == "OUTPUT_PERMISSION_DENIED"


class TestOutputArtifactNormalization:
    def test_normalize_output_artifact_state_dedupes_and_orders_primary_first(self):
        primary_output, output_files = _normalize_output_artifact_state(
            "report.html",
            ["report.json", "report.html", "report.json", "  ", "report.xlsx"],
        )

        assert primary_output == "report.html"
        assert output_files == ["report.html", "report.json", "report.xlsx"]

    def test_result_output_paths_preserves_primary_artifact_order(self):
        result_paths = _result_output_paths(
            {
                "output_file": "report.xlsx",
                "output_files": ["report.json", "report.xlsx", "report.html", "report.json"],
            },
        )

        assert result_paths == ["report.xlsx", "report.json", "report.html"]


# ==================== _coerce_run_mode ====================


class TestCoerceRunMode:
    def test_passthrough_enum(self):
        assert _coerce_run_mode(RunMode.SDR) is RunMode.SDR

    def test_valid_string(self):
        assert _coerce_run_mode("sdr") is RunMode.SDR
        assert _coerce_run_mode("diff") is RunMode.DIFF

    def test_invalid_string(self):
        assert _coerce_run_mode("nonexistent") is None

    def test_none_input(self):
        assert _coerce_run_mode(None) is None

    def test_int_input(self):
        assert _coerce_run_mode(42) is None


# ==================== _collect_environment_info ====================


class TestCollectEnvironmentInfo:
    def test_returns_expected_keys(self):
        info = _collect_environment_info()
        assert "python_version" in info
        assert "platform" in info
        assert "platform_version" in info
        assert "dependencies" in info

    def test_python_version_format(self):
        import sys

        info = _collect_environment_info()
        vi = sys.version_info
        assert info["python_version"] == f"{vi.major}.{vi.minor}.{vi.micro}"

    def test_platform_matches_sys(self):
        import sys

        info = _collect_environment_info()
        assert info["platform"] == sys.platform

    def test_platform_version_is_string(self):
        info = _collect_environment_info()
        assert isinstance(info["platform_version"], str)
        assert len(info["platform_version"]) > 0

    def test_dependencies_contains_core_packages(self):
        info = _collect_environment_info()
        expected = {"cjapy", "pandas", "numpy", "xlsxwriter", "tqdm"}
        assert set(info["dependencies"].keys()) == expected

    def test_dependency_versions_are_strings(self):
        info = _collect_environment_info()
        for pkg, ver in info["dependencies"].items():
            assert isinstance(ver, str), f"{pkg} version is not a string"

    def test_graceful_fallback_on_missing_package(self):
        with patch(
            "cja_auto_sdr.core.logging.importlib.metadata.version",
            side_effect=importlib.metadata.PackageNotFoundError("not found"),
        ):
            info = _collect_environment_info()
            for ver in info["dependencies"].values():
                assert ver == "unknown"

    def test_partial_failure_returns_unknown_for_failing_only(self):
        real_version = importlib.metadata.version

        def selective_fail(pkg):
            if pkg == "numpy":
                raise importlib.metadata.PackageNotFoundError("not found")
            return real_version(pkg)

        with patch(
            "cja_auto_sdr.core.logging.importlib.metadata.version",
            side_effect=selective_fail,
        ):
            info = _collect_environment_info()
            assert info["dependencies"]["numpy"] == "unknown"
            # Other packages should still have real versions
            assert info["dependencies"]["pandas"] != "unknown"

    def test_non_package_not_found_error_returns_unknown(self):
        """Non-PackageNotFoundError metadata exceptions should map to 'unknown', not crash."""

        def metadata_bomb(pkg):
            raise ValueError(f"malformed metadata for {pkg}")

        with patch(
            "cja_auto_sdr.core.logging.importlib.metadata.version",
            side_effect=metadata_bomb,
        ):
            info = _collect_environment_info()
            for ver in info["dependencies"].values():
                assert ver == "unknown"
            # Rest of the payload should still be intact
            assert "python_version" in info
            assert "platform" in info

    def test_oserror_during_metadata_does_not_crash_environment_info(self):
        """OSError from corrupt dist-info should not prevent environment collection."""
        real_version = importlib.metadata.version

        def corrupt_one(pkg):
            if pkg == "pandas":
                raise OSError("cannot read dist-info")
            return real_version(pkg)

        with patch(
            "cja_auto_sdr.core.logging.importlib.metadata.version",
            side_effect=corrupt_one,
        ):
            info = _collect_environment_info()
            assert info["dependencies"]["pandas"] == "unknown"
            assert info["dependencies"]["numpy"] != "unknown"


# ==================== lock run-summary block builder ====================


class TestBuildOrgReportLockRunSummaryBlock:
    """Tests for _build_org_report_lock_run_summary_block reshaping contract."""

    def test_happy_path_all_fields(self):
        block = _build_org_report_lock_run_summary_block(
            {
                "lock_acquired": True,
                "lock_stale_threshold_seconds": 3600,
                "lock_contention": False,
                "lock_ownership_lost": False,
                "lock_backend": "lease",
            }
        )
        assert block["acquired"] is True
        assert block["stale_threshold_seconds"] == 3600
        assert block["contention_observed"] is False
        assert block["lost_during_run"] is False
        assert block["backend"] == "lease"
        assert "loss_reason" not in block

    def test_acquired_then_lost(self):
        block = _build_org_report_lock_run_summary_block(
            {
                "lock_acquired": True,
                "lock_ownership_lost": True,
                "lock_backend": "lease",
            }
        )
        assert block["acquired"] is True
        assert block["lost_during_run"] is True
        assert block["loss_reason"] == "ownership_lost_during_execution"

    def test_contention_at_startup_not_acquired(self):
        block = _build_org_report_lock_run_summary_block(
            {
                "lock_acquired": False,
                "lock_contention": True,
            }
        )
        assert block["acquired"] is False
        assert block["contention_observed"] is True
        assert block["lost_during_run"] is False  # default when acquired present

    def test_empty_details_returns_empty_block(self):
        block = _build_org_report_lock_run_summary_block({})
        assert block == {}

    def test_missing_ownership_lost_defaults_false_when_acquired(self):
        """When lock_acquired is present but lock_ownership_lost is not, lost_during_run defaults to False."""
        block = _build_org_report_lock_run_summary_block({"lock_acquired": True})
        assert block["lost_during_run"] is False

    def test_missing_ownership_lost_absent_when_not_acquired_key(self):
        """When lock_acquired key is missing entirely, lost_during_run is not set."""
        block = _build_org_report_lock_run_summary_block({"lock_contention": True})
        assert "lost_during_run" not in block

    def test_backend_whitespace_stripped(self):
        block = _build_org_report_lock_run_summary_block({"lock_backend": "  lease  "})
        assert block["backend"] == "lease"

    def test_empty_backend_omitted(self):
        block = _build_org_report_lock_run_summary_block({"lock_backend": ""})
        assert "backend" not in block

    def test_none_backend_omitted(self):
        block = _build_org_report_lock_run_summary_block({"lock_backend": None})
        assert "backend" not in block

    def test_stale_threshold_normalized(self):
        """Non-positive thresholds should be clamped by normalize_lock_stale_threshold_seconds."""
        block = _build_org_report_lock_run_summary_block({"lock_stale_threshold_seconds": -1})
        assert block["stale_threshold_seconds"] > 0  # clamped to minimum

    def test_loss_reason_not_set_when_ownership_not_lost(self):
        block = _build_org_report_lock_run_summary_block(
            {
                "lock_acquired": True,
                "lock_ownership_lost": False,
            }
        )
        assert "loss_reason" not in block


# ==================== advisory rollup in run-summary contract ====================


class TestOrgReportAdvisoryRollupRunSummaryContract:
    """Verify the advisory rollup integration with run-summary details."""

    def test_summary_version_unchanged_with_advisory_rollup(self):
        """Adding advisory_rollup must not alter the run-summary schema version."""
        assert RUN_SUMMARY_SCHEMA_VERSION == "1.1"

    def test_advisory_rollup_merged_via_details_key(self):
        """Advisory rollup appears under details.advisories."""
        from cja_auto_sdr.generator import _merge_org_report_run_summary_details
        from cja_auto_sdr.org.models import OrgReportConfig

        rollup = {
            "advisories_version": "1.0",
            "severity": "info",
            "summary": {},
            "types": [],
            "recommended_actions": [],
        }
        run_state: dict = {"details": {}}
        _merge_org_report_run_summary_details(
            run_state,
            success=True,
            thresholds_exceeded=False,
            fail_on_threshold=False,
            lock_details={},
            org_config=OrgReportConfig(),
            advisory_rollup=rollup,
        )
        assert run_state["details"]["advisories"] is rollup

    def test_existing_envelope_fields_survive_advisory_merge(self):
        """Core run-summary envelope fields must not be lost when advisories are merged."""
        from cja_auto_sdr.generator import _merge_org_report_run_summary_details
        from cja_auto_sdr.org.models import OrgReportConfig

        rollup = {
            "advisories_version": "1.0",
            "severity": "info",
            "summary": {},
            "types": [],
            "recommended_actions": [],
        }
        run_state: dict = {"details": {}}
        _merge_org_report_run_summary_details(
            run_state,
            success=True,
            thresholds_exceeded=False,
            fail_on_threshold=False,
            lock_details={},
            org_config=OrgReportConfig(),
            advisory_rollup=rollup,
        )
        # Core fields must be present
        assert "operation_success" in run_state["details"]
        assert "execution_settings" in run_state["details"]


class TestDiffAdvisoryRollupRunSummaryContract:
    """Verify diff advisory rollup integration with run-summary details."""

    def test_diff_advisory_rollup_merged_into_run_state(self):
        """Advisory rollup from diff handler is merged under details.advisories."""
        from cja_auto_sdr.diff.commands import _populate_diff_advisory_rollup
        from cja_auto_sdr.diff.models import DiffResult, DiffSummary, MetadataDiff

        diff_result = DiffResult(
            summary=DiffSummary(),
            metadata_diff=MetadataDiff(
                source_name="A",
                target_name="B",
                source_id="dv-a",
                target_id="dv-b",
            ),
            metric_diffs=[],
            dimension_diffs=[],
        )
        runtime_details: dict = {}
        _populate_diff_advisory_rollup(runtime_details, diff_result, changes_only=False)

        run_state: dict = {
            "details": {
                "operation_success": True,
                "has_changes": False,
                "warn_threshold_exit_code": None,
            },
        }
        advisory_rollup = runtime_details.get("advisory_rollup")
        if advisory_rollup is not None:
            run_state["details"]["advisories"] = advisory_rollup

        assert "advisories" in run_state["details"]
        assert run_state["details"]["advisories"]["advisories_version"] == "1.0"
        # Core fields preserved
        assert run_state["details"]["operation_success"] is True
        assert run_state["details"]["has_changes"] is False

    def test_diff_advisory_rollup_not_merged_on_failure(self):
        """When handler fails, runtime_details is empty and no advisories key appears."""
        runtime_details: dict = {}
        run_state: dict = {"details": {"operation_success": False}}

        advisory_rollup = runtime_details.get("advisory_rollup")
        if advisory_rollup is not None:
            run_state["details"]["advisories"] = advisory_rollup

        assert "advisories" not in run_state["details"]

    def test_diff_advisory_rollup_severity_reflects_content(self):
        """Breaking changes in diff should produce critical severity in rollup."""
        from cja_auto_sdr.diff.commands import _populate_diff_advisory_rollup
        from cja_auto_sdr.diff.models import (
            ChangeType,
            ComponentDiff,
            DiffResult,
            DiffSummary,
            MetadataDiff,
        )

        removed = ComponentDiff(id="m1", name="Revenue", change_type=ChangeType.REMOVED)
        diff_result = DiffResult(
            summary=DiffSummary(metrics_removed=1),
            metadata_diff=MetadataDiff(
                source_name="A",
                target_name="B",
                source_id="dv-a",
                target_id="dv-b",
            ),
            metric_diffs=[removed],
            dimension_diffs=[],
        )
        runtime_details: dict = {}
        _populate_diff_advisory_rollup(runtime_details, diff_result, changes_only=False)
        rollup = runtime_details["advisory_rollup"]
        assert rollup["severity"] == "critical"
        assert "breaking_changes" in rollup["types"]


# ---------------------------------------------------------------------------
# Run-summary elapsed-duration timing hardening (v3.5.6)
# ---------------------------------------------------------------------------


class TestRunSummaryTimingHardening:
    """Verify run-summary uses perf_counter for duration while keeping wall-clock timestamps."""

    def test_duration_seconds_uses_perf_counter(self) -> None:
        """_build_run_summary_payload derives duration_seconds from perf_counter, not wall-clock."""
        from cja_auto_sdr.generator import _build_run_summary_payload

        run_state: dict = {
            "mode": "single",
            "processed_results": [],
            "data_view_inputs": [],
            "resolved_data_views": [],
        }
        # Simulate perf_counter start at 1000.0; current perf_counter returns 1005.25
        import time
        from unittest.mock import MagicMock, patch

        mock_time = MagicMock(wraps=time)
        mock_time.perf_counter.return_value = 1005.25

        with patch("cja_auto_sdr.generator.time", mock_time):
            payload = _build_run_summary_payload(
                run_state=run_state,
                exit_code=0,
                summary_start="2026-04-01T12:00:00+00:00",
                summary_start_perf=1000.0,
            )

        assert payload["duration_seconds"] == 5.25
        assert payload["started_at"] == "2026-04-01T12:00:00+00:00"
        assert isinstance(payload["ended_at"], str)
        assert "T" in payload["ended_at"]  # ISO 8601

    def test_started_at_ended_at_are_wall_clock(self) -> None:
        """started_at and ended_at remain wall-clock UTC timestamps, not elapsed clocks."""
        import time as real_time
        from datetime import UTC, datetime
        from unittest.mock import MagicMock, patch

        from cja_auto_sdr.generator import _build_run_summary_payload

        run_state: dict = {
            "mode": "single",
            "processed_results": [],
            "data_view_inputs": [],
            "resolved_data_views": [],
        }

        fixed_now = datetime(2026, 4, 1, 15, 30, 0, tzinfo=UTC)
        mock_time = MagicMock(wraps=real_time)
        mock_time.perf_counter.return_value = 2000.0

        with (
            patch("cja_auto_sdr.generator.time", mock_time),
            patch("cja_auto_sdr.generator.datetime") as mock_dt,
        ):
            mock_dt.now.return_value = fixed_now
            mock_dt.side_effect = datetime
            payload = _build_run_summary_payload(
                run_state=run_state,
                exit_code=0,
                summary_start="2026-04-01T15:29:55+00:00",
                summary_start_perf=1995.0,
            )

        assert payload["started_at"] == "2026-04-01T15:29:55+00:00"
        assert payload["ended_at"] == fixed_now.isoformat()
        assert payload["duration_seconds"] == 5.0
