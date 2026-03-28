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
