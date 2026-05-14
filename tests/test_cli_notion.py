"""Tests for Notion-related CLI flag wiring."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest

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


def test_push_to_notion_default_is_none():
    args = _parse(["dv_12345"])
    assert args.push_to_notion is None


def test_push_to_notion_and_format_both_set_no_argparse_conflict():
    args = _parse(["--push-to-notion", "./sdr.json", "--format", "notion"])
    assert args.push_to_notion == "./sdr.json"
    assert args.format == "notion"


def test_push_to_notion_standalone_policy_registered():
    from cja_auto_sdr.cli.standalone_policy import standalone_prevalidation_policy

    policy = standalone_prevalidation_policy("push_to_notion")
    assert policy is not None
    assert "notion_force_new" in policy.ignored_semantic_dests


def test_format_notion_rejected_for_diff_mode():
    """--format notion in diff mode must exit 1 with actionable error (Notion is SDR-only)."""
    import argparse

    from cja_auto_sdr.generator import (
        RunMode,
        _validate_semantic_flag_relationships,
    )

    args = argparse.Namespace(
        format="notion",
        diff=True,
        skip_validation=False,
    )
    with pytest.raises(SystemExit) as exc_info:
        _validate_semantic_flag_relationships(args, inferred_mode=RunMode.DIFF)
    assert exc_info.value.code == 1


def test_format_notion_rejected_for_org_report_mode():
    """--format notion in org-report mode must exit 1 (Notion is SDR-only)."""
    import argparse

    from cja_auto_sdr.generator import (
        RunMode,
        _validate_semantic_flag_relationships,
    )

    args = argparse.Namespace(
        format="notion",
        skip_validation=False,
    )
    with pytest.raises(SystemExit) as exc_info:
        _validate_semantic_flag_relationships(args, inferred_mode=RunMode.ORG_REPORT)
    assert exc_info.value.code == 1


def test_format_notion_allowed_in_push_to_notion_mode():
    """--push-to-notion + --format notion must not error — push handler ignores --format."""
    import argparse

    from cja_auto_sdr.generator import (
        RunMode,
        _validate_semantic_flag_relationships,
    )

    args = argparse.Namespace(
        format="notion",
        push_to_notion="./sdr.json",
        skip_validation=False,
    )
    _validate_semantic_flag_relationships(args, inferred_mode=RunMode.PUSH_TO_NOTION)


def test_format_notion_allowed_in_sdr_mode():
    """--format notion in SDR mode must validate cleanly."""
    import argparse

    from cja_auto_sdr.generator import (
        RunMode,
        _validate_semantic_flag_relationships,
    )

    args = argparse.Namespace(
        format="notion",
        skip_validation=False,
    )
    _validate_semantic_flag_relationships(args, inferred_mode=RunMode.SDR)
