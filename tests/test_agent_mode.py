# tests/test_agent_mode.py
"""Tests for --agent-mode CLI preset flag."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

from cja_auto_sdr.cli.parser import parse_arguments
from cja_auto_sdr.cli.standalone_policy import (
    _STANDALONE_FAST_PATH_METADATA_DESTS,
    standalone_prevalidation_policy,
)
from cja_auto_sdr.diff.cli import _diff_output_to_stdout_requested


def _run_main_impl(argv_tail: list[str]) -> int:
    """Execute _main_impl with argv and return the exit code."""
    from cja_auto_sdr.generator import _main_impl

    with patch.object(sys, "argv", ["cja_auto_sdr", *argv_tail]):
        with pytest.raises(SystemExit) as exc_info:
            _main_impl()
    return int(exc_info.value.code)


class TestAgentModeRegistration:
    """Verify --agent-mode is registered correctly."""

    def test_agent_mode_defaults_to_false(self):
        args = parse_arguments(["dv_123"])
        assert args.agent_mode is False

    def test_agent_mode_flag_sets_true(self):
        args = parse_arguments(["dv_123", "--agent-mode"])
        assert args.agent_mode is True

    def test_agent_mode_appears_in_agent_integration_group(self):
        parser = parse_arguments([], return_parser=True)
        group_titles = [g.title for g in parser._action_groups]
        assert "Agent Integration" in group_titles


class TestAgentModeResolution:
    """Verify --agent-mode applies preset defaults and respects explicit overrides."""

    def test_agent_mode_sets_format_json(self):
        args = parse_arguments(["dv_123", "--agent-mode"])
        assert args.format == "json"

    def test_agent_mode_sets_output_stdout(self):
        args = parse_arguments(["dv_123", "--agent-mode"])
        assert args.output == "-"

    def test_agent_mode_sets_log_format_json(self):
        args = parse_arguments(["dv_123", "--agent-mode"])
        assert args.log_format == "json"

    def test_explicit_format_overrides_agent_mode(self):
        args = parse_arguments(["dv_123", "--agent-mode", "--format", "csv"])
        assert args.format == "csv"

    def test_inline_format_overrides_agent_mode(self):
        args = parse_arguments(["dv_123", "--agent-mode", "--format=csv"])
        assert args.format == "csv"

    def test_explicit_output_overrides_agent_mode(self):
        args = parse_arguments(["dv_123", "--agent-mode", "--output", "report.json"])
        assert args.output == "report.json"

    def test_inline_output_overrides_agent_mode(self):
        args = parse_arguments(["dv_123", "--agent-mode", "--output=report.json"])
        assert args.output == "report.json"

    def test_explicit_log_format_overrides_agent_mode(self):
        args = parse_arguments(["dv_123", "--agent-mode", "--log-format", "text"])
        assert args.log_format == "text"

    def test_agent_mode_before_explicit_flags(self):
        """Explicit flags win regardless of order."""
        args = parse_arguments(["--agent-mode", "dv_123", "--format", "csv"])
        assert args.format == "csv"
        assert args.output == "-"

    def test_no_flag_behavior_unchanged(self):
        """Without --agent-mode, defaults remain as before."""
        args = parse_arguments(["dv_123"])
        assert args.format is None
        assert args.output is None
        assert args.log_format == "text"

    def test_agent_mode_on_discovery_command(self):
        args = parse_arguments(["--list-dataviews", "--agent-mode"])
        assert args.format == "json"
        assert args.output == "-"

    def test_stdout_compatible_discovery_format_override_keeps_stdout(self):
        args = parse_arguments(["--list-dataviews", "--agent-mode", "--format", "csv"])
        assert args.format == "csv"
        assert args.output == "-"

    def test_agent_mode_on_org_report(self):
        args = parse_arguments(["--org-report", "--agent-mode"])
        assert args.format == "json"
        assert args.output == "-"

    def test_file_only_org_report_format_override_keeps_agent_mode_stdout_default(self):
        args = parse_arguments(["--org-report", "--agent-mode", "--format", "markdown"])
        assert args.format == "markdown"
        assert args.output == "-"

    def test_agent_mode_on_diff(self):
        args = parse_arguments(["--diff", "dv_a", "dv_b", "--agent-mode"])
        assert args.format == "json"
        assert args.output == "-"

    def test_agent_mode_on_batch(self):
        args = parse_arguments(["--batch", "dv_a", "dv_b", "--agent-mode"])
        assert args.format == "json"
        assert args.output == "-"

    def test_agent_mode_honors_real_sys_argv_when_argv_is_none(self):
        with patch("sys.argv", ["cja_auto_sdr", "dv_123", "--agent-mode", "--output", "report.json"]):
            args = parse_arguments()
        assert args.output == "report.json"


class TestAgentModeFastPath:
    """Verify --agent-mode is tolerated on fast-path modes."""

    def test_agent_mode_in_metadata_dests(self):
        assert "agent_mode" in _STANDALONE_FAST_PATH_METADATA_DESTS

    def test_completion_fast_path_tolerates_agent_mode(self):
        policy = standalone_prevalidation_policy("completion")
        assert policy is not None
        tolerated = policy.tolerated_fast_path_dests()
        assert "agent_mode" in tolerated

    def test_exit_codes_fast_path_tolerates_agent_mode(self):
        policy = standalone_prevalidation_policy("exit_codes")
        assert policy is not None
        tolerated = policy.tolerated_fast_path_dests()
        assert "agent_mode" in tolerated


class TestAgentModeConstraints:
    """Verify --agent-mode does not soften existing validation rules."""

    def test_agent_mode_run_summary_json_stdout_conflict(self):
        """--agent-mode --run-summary-json - should still fail when paired with stdout output."""
        args = parse_arguments(["dv_123", "--agent-mode", "--run-summary-json", "-"])
        assert args.output == "-"
        assert args.run_summary_json == "-"

    def test_agent_mode_help_text_under_agent_integration(self):
        """--agent-mode help appears under Agent Integration group."""
        parser = parse_arguments([], return_parser=True)
        for group in parser._action_groups:
            if group.title == "Agent Integration":
                action_dests = [a.dest for a in group._group_actions]
                assert "agent_mode" in action_dests
                return
        pytest.fail("Agent Integration group not found")


class TestAgentModeDiffStdout:
    """Verify --agent-mode diff stdout JSON behavior."""

    def test_agent_mode_diff_sets_json_stdout(self):
        """--agent-mode with --diff should set json format and stdout output."""
        args = parse_arguments(["--diff", "dv_a", "dv_b", "--agent-mode"])
        assert args.format == "json"
        assert args.output == "-"

    def test_diff_stdout_detection_logic_honors_dash_alias(self):
        """The diff dispatch helper should treat '-' as stdout for JSON output."""
        args = parse_arguments(["--diff", "dv_a", "dv_b", "--agent-mode"])
        assert _diff_output_to_stdout_requested(args, output_format=args.format) is True

    def test_diff_stdout_detection_logic_honors_stdout_alias(self):
        """The diff dispatch helper should treat 'stdout' as stdout for JSON output."""
        args = parse_arguments(["--diff", "dv_a", "dv_b", "--format", "json", "--output", "stdout"])
        assert _diff_output_to_stdout_requested(args, output_format=args.format) is True

    def test_diff_stdout_detection_false_for_csv(self):
        """Non-json format should not trigger stdout JSON path."""
        args = parse_arguments(["--diff", "dv_a", "dv_b", "--agent-mode", "--format", "csv"])
        assert _diff_output_to_stdout_requested(args, output_format=args.format) is False

    def test_compare_snapshots_agent_mode_sets_json_stdout(self):
        """--agent-mode with --compare-snapshots should set json format and stdout output."""
        args = parse_arguments(["--compare-snapshots", "a.json", "b.json", "--agent-mode"])
        assert args.format == "json"
        assert args.output == "-"

    def test_diff_snapshot_agent_mode_sets_json_stdout(self):
        """--agent-mode with --diff-snapshot should set json format and stdout output."""
        args = parse_arguments(["dv_123", "--diff-snapshot", "baseline.json", "--agent-mode"])
        assert args.format == "json"
        assert args.output == "-"


class TestDiffStdoutAliasRuntime:
    """Verify the documented 'stdout' alias reaches diff-family runtime handlers."""

    def test_diff_stdout_alias_reaches_live_diff_handler(self):
        with (
            patch(
                "cja_auto_sdr.generator.resolve_data_view_names",
                side_effect=[(["dv_source"], {}), (["dv_target"], {})],
            ),
            patch("cja_auto_sdr.generator.handle_diff_command", return_value=(True, False, None)) as mock_diff,
        ):
            exit_code = _run_main_impl(["--diff", "dv_source", "dv_target", "--format", "json", "--output", "stdout"])

        assert exit_code == 0
        assert mock_diff.call_args.kwargs["output_to_stdout"] is True

    def test_diff_snapshot_stdout_alias_reaches_handler(self):
        with (
            patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {})),
            patch("cja_auto_sdr.generator.handle_diff_snapshot_command", return_value=(True, False, None)) as mock_diff,
        ):
            exit_code = _run_main_impl(
                ["dv_123", "--diff-snapshot", "baseline.json", "--format", "json", "--output", "stdout"]
            )

        assert exit_code == 0
        assert mock_diff.call_args.kwargs["output_to_stdout"] is True

    def test_compare_with_prev_stdout_alias_reaches_handler(self):
        with (
            patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {})),
            patch("cja_auto_sdr.generator.SnapshotManager") as mock_snapshot_manager,
            patch("cja_auto_sdr.generator.handle_diff_snapshot_command", return_value=(True, False, None)) as mock_diff,
        ):
            mock_snapshot_manager.return_value.get_most_recent_snapshot.return_value = "./snapshots/prev.json"
            exit_code = _run_main_impl(["dv_123", "--compare-with-prev", "--format", "json", "--output", "stdout"])

        assert exit_code == 0
        assert mock_diff.call_args.kwargs["snapshot_file"] == "./snapshots/prev.json"
        assert mock_diff.call_args.kwargs["output_to_stdout"] is True

    def test_compare_snapshots_stdout_alias_reaches_handler(self):
        with patch(
            "cja_auto_sdr.generator.handle_compare_snapshots_command",
            return_value=(True, False, None),
        ) as mock_compare:
            exit_code = _run_main_impl(
                ["--compare-snapshots", "source.json", "target.json", "--format", "json", "--output", "stdout"]
            )

        assert exit_code == 0
        assert mock_compare.call_args.kwargs["output_to_stdout"] is True


class TestAgentModeOrgReportRuntime:
    """Verify org-report agent-mode overrides reach runtime without self-invalid stdout wiring."""

    def test_file_only_org_report_format_override_does_not_pass_stdout_output(self):
        with patch("cja_auto_sdr.generator.run_org_report", return_value=(True, False)) as mock_run:
            exit_code = _run_main_impl(["--org-report", "--agent-mode", "--format", "markdown"])

        assert exit_code == 0
        assert mock_run.call_args.kwargs["output_path"] is None

    def test_file_only_org_report_format_override_recomputes_quiet_after_stdout_suppression(self):
        with patch("cja_auto_sdr.generator.run_org_report", return_value=(True, False)) as mock_run:
            exit_code = _run_main_impl(["--org-report", "--agent-mode", "--format", "all"])

        assert exit_code == 0
        assert mock_run.call_args.kwargs["output_path"] is None
        assert mock_run.call_args.kwargs["quiet"] is False

    def test_org_stats_file_only_format_override_recomputes_quiet_after_stdout_suppression(self):
        with patch("cja_auto_sdr.generator.run_org_report", return_value=(True, False)) as mock_run:
            exit_code = _run_main_impl(["--org-report", "--org-stats", "--agent-mode", "--format", "markdown"])

        assert exit_code == 0
        assert mock_run.call_args.kwargs["output_path"] is None
        assert mock_run.call_args.kwargs["quiet"] is False

    def test_explicit_quiet_still_wins_when_org_report_suppresses_inherited_stdout(self):
        with patch("cja_auto_sdr.generator.run_org_report", return_value=(True, False)) as mock_run:
            exit_code = _run_main_impl(["--org-report", "--agent-mode", "--format", "markdown", "--quiet"])

        assert exit_code == 0
        assert mock_run.call_args.kwargs["output_path"] is None
        assert mock_run.call_args.kwargs["quiet"] is True
