"""Tests for Notion-related CLI flag wiring."""

from __future__ import annotations

import argparse
import sys
from unittest.mock import patch

import pytest

from cja_auto_sdr.cli.parser import parse_arguments
from cja_auto_sdr.generator import RunMode, _validate_semantic_flag_relationships


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


def test_push_to_notion_standalone_policy_tolerates_database_flags():
    """notion_database_id and notion_create_database must be tolerated by the standalone policy."""
    from cja_auto_sdr.cli.standalone_policy import standalone_prevalidation_policy

    policy = standalone_prevalidation_policy("push_to_notion")
    assert policy is not None
    assert "notion_database_id" in policy.ignored_semantic_dests
    assert "notion_create_database" in policy.ignored_semantic_dests


def test_format_notion_rejected_for_diff_mode():
    """--format notion in diff mode must exit 1 with actionable error (Notion is SDR-only)."""
    args = argparse.Namespace(
        format="notion",
        diff=True,
        skip_validation=False,
    )
    with pytest.raises(SystemExit) as exc_info:
        _validate_semantic_flag_relationships(args, inferred_mode=RunMode.DIFF)
    assert exc_info.value.code == 1


def test_format_notion_allowed_in_org_report_mode():
    """--format notion in org-report mode must be allowed (Task 6: org-report is now a valid notion target)."""
    args = argparse.Namespace(
        format="notion",
        skip_validation=False,
        push_to_notion=None,
        workers=1,
        watch_data_views=None,
    )
    _validate_semantic_flag_relationships(args, inferred_mode=RunMode.ORG_REPORT)


def test_format_notion_allowed_in_push_to_notion_mode():
    """--push-to-notion + --format notion must not error — push handler ignores --format."""
    args = argparse.Namespace(
        format="notion",
        push_to_notion="./sdr.json",
        skip_validation=False,
    )
    _validate_semantic_flag_relationships(args, inferred_mode=RunMode.PUSH_TO_NOTION)


def test_format_notion_allowed_in_sdr_mode():
    """--format notion in SDR mode must validate cleanly."""
    args = argparse.Namespace(
        format="notion",
        skip_validation=False,
    )
    _validate_semantic_flag_relationships(args, inferred_mode=RunMode.SDR)


# Mode flags that --push-to-notion must reject. _run_mode_checks dispatches by
# precedence — every flag below would otherwise win and silently drop the
# publish. Parametrized to mirror the table-driven impl
# (_PUSH_TO_NOTION_INCOMPATIBLE_FLAGS) so a future addition there gets
# coverage by adding one line here.
_PUSH_TO_NOTION_MUTEX_CASES: tuple[tuple[str, object], ...] = (
    ("org_report", True),
    ("diff", True),
    ("snapshot", "./snap.json"),
    ("diff_snapshot", ["./a.json", "./b.json"]),
    ("compare_snapshots", ["./a.json", "./b.json"]),
    ("list_snapshots", True),
    ("prune_snapshots", True),
    ("list_org_report_snapshots", True),
    ("inspect_org_report_snapshot", "./snap.json"),
    ("prune_org_report_snapshots", True),
    ("batch", True),
    ("watch_data_views", ["dv_123"]),
    ("inventory_summary", True),
    ("dry_run", True),
    ("data_views", ["dv_123"]),
    ("profile_list", True),
    ("profile_add", "name"),
    ("profile_import", ["name", "./profile.json"]),
    ("profile_show", "name"),
    ("profile_test", "name"),
    ("sample_config", True),
    ("config_status", True),
    ("config_json", True),
    ("validate_config", True),
    ("git_init", True),
    ("list_dataviews", True),
    ("list_connections", True),
    ("list_datasets", True),
    ("list_metrics", "dv_123"),
    ("list_dimensions", "dv_123"),
    ("list_segments", "dv_123"),
    ("list_calculated_metrics", "dv_123"),
    ("describe_dataview", "dv_123"),
    ("stats", True),
    ("notion_print_database_schema", True),
)


@pytest.mark.parametrize(("dest", "value"), _PUSH_TO_NOTION_MUTEX_CASES)
def test_push_to_notion_rejects_incompatible_mode_flag(dest, value):
    """Each mode flag in the mutex table must cause --push-to-notion to exit 1."""
    args = argparse.Namespace(
        push_to_notion="./sdr.json",
        skip_validation=False,
        **{dest: value},
    )
    with pytest.raises(SystemExit) as exc_info:
        _validate_semantic_flag_relationships(args, inferred_mode=RunMode.PUSH_TO_NOTION)
    assert exc_info.value.code == 1


@pytest.mark.parametrize("argv_tail", [["--profile-list"], ["--sample-config"], ["--stats", "dv_1"]])
@patch("cja_auto_sdr.generator.configure_cjapy")
@patch("cja_auto_sdr.generator.cjapy")
def test_main_push_to_notion_with_early_mode_exits_1(
    mock_cjapy, mock_configure, tmp_path, monkeypatch, capsys, argv_tail
):
    """Early-dispatching modes must not silently drop --push-to-notion."""
    from cja_auto_sdr.generator import main

    monkeypatch.chdir(tmp_path)
    (tmp_path / "sdr.json").write_text("{}")
    monkeypatch.setattr(sys, "argv", ["cja_auto_sdr", "--push-to-notion", "sdr.json", *argv_tail])
    with pytest.raises(SystemExit) as exc:
        main()
    assert exc.value.code == 1
    assert "--push-to-notion is incompatible with" in capsys.readouterr().err
    assert not (tmp_path / "config.sample.json").exists()
    mock_cjapy.CJA.assert_not_called()
    mock_configure.assert_not_called()
