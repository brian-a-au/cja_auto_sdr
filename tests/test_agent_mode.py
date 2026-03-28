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
