"""CLI wiring for --notion-prune-orphans (v3.9.0)."""

from __future__ import annotations

import argparse

import pytest

from cja_auto_sdr.cli.parser import parse_arguments
from cja_auto_sdr.cli.standalone_policy import standalone_prevalidation_policy
from cja_auto_sdr.generator import RunMode, _infer_run_mode_enum, _validate_semantic_flag_relationships


def test_flag_parses_default_false() -> None:
    assert parse_arguments(["dv1"]).notion_prune_orphans is False


def test_flag_parses_true() -> None:
    assert parse_arguments(["--notion-prune-orphans"]).notion_prune_orphans is True


def test_infers_prune_mode() -> None:
    args = parse_arguments(["--notion-prune-orphans"])
    assert _infer_run_mode_enum(args) is RunMode.NOTION_PRUNE_ORPHANS


def test_prune_with_dry_run_still_infers_prune_mode() -> None:
    """--dry-run is a preview sub-flag of prune; it must NOT shadow it as RunMode.DRY_RUN."""
    args = parse_arguments(["--notion-prune-orphans", "--dry-run"])
    assert _infer_run_mode_enum(args) is RunMode.NOTION_PRUNE_ORPHANS


def test_standalone_policy_registered() -> None:
    assert standalone_prevalidation_policy("notion_prune_orphans") is not None


@pytest.mark.parametrize("conflict", ["org_report", "diff", "batch"])
def test_prune_rejects_conflicting_modes(conflict, capsys) -> None:
    args = argparse.Namespace(
        notion_prune_orphans=True,
        push_to_notion=None,
        org_report=False,
        diff=False,
        batch=False,
        watch_data_views=None,
        skip_validation=False,
        format=None,
    )
    setattr(args, conflict, True)
    with pytest.raises(SystemExit) as exc:
        _validate_semantic_flag_relationships(args, inferred_mode=RunMode.NOTION_PRUNE_ORPHANS)
    assert exc.value.code == 1
    assert "--notion-prune-orphans" in capsys.readouterr().err
