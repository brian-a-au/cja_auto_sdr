"""Tests for Notion-related CLI flag wiring."""
from __future__ import annotations

import sys
from unittest.mock import patch

from cja_auto_sdr.cli.parser import parse_arguments


def _parse(args):
    with patch.object(sys, "argv", ["cja_auto_sdr", *args]):
        return parse_arguments()


def test_format_notion_is_accepted():
    args = _parse(["dv_12345", "--format", "notion"])
    assert args.format == "notion"


def test_notion_force_new_flag_false_by_default():
    args = _parse(["dv_12345", "--format", "notion"])
    assert args.notion_force_new is False


def test_notion_force_new_flag_sets_true():
    args = _parse(["dv_12345", "--format", "notion", "--notion-force-new"])
    assert args.notion_force_new is True


def test_push_to_notion_accepts_file_path():
    args = _parse(["--push-to-notion", "./reports/sdr.json"])
    assert args.push_to_notion == "./reports/sdr.json"


def test_push_to_notion_with_force_new():
    args = _parse(["--push-to-notion", "./reports/sdr.json", "--notion-force-new"])
    assert args.push_to_notion == "./reports/sdr.json"
    assert args.notion_force_new is True
