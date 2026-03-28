# tests/test_agent_mode.py
"""Tests for --agent-mode CLI preset flag."""

from __future__ import annotations

import pytest
from unittest.mock import patch

from cja_auto_sdr.cli.parser import parse_arguments


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
        assert args.output == "-"  # agent-mode still fills non-overridden

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

    def test_agent_mode_on_org_report(self):
        args = parse_arguments(["--org-report", "--agent-mode"])
        assert args.format == "json"
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


from cja_auto_sdr.cli.standalone_policy import (
    StandalonePrevalidationPolicy,
    standalone_prevalidation_policy,
    _STANDALONE_FAST_PATH_METADATA_DESTS,
)


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
