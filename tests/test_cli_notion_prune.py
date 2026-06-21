"""CLI wiring for --notion-prune-orphans (v3.9.0)."""

from __future__ import annotations

import argparse
import sys

import pytest

from cja_auto_sdr.cli.parser import parse_arguments
from cja_auto_sdr.cli.standalone_policy import standalone_prevalidation_policy
from cja_auto_sdr.generator import (
    RunMode,
    _infer_run_mode_enum,
    _main_impl,
    _resolve_semantic_validation_args,
    _validate_semantic_flag_relationships,
)


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


@pytest.mark.parametrize(
    "conflict", ["org_report", "diff", "batch", "push_to_notion", "watch_data_views", "inventory_summary", "data_views"]
)
def test_prune_rejects_conflicting_modes(conflict, capsys) -> None:
    args = argparse.Namespace(
        notion_prune_orphans=True,
        push_to_notion=None,
        org_report=False,
        diff=False,
        batch=False,
        watch_data_views=None,
        inventory_summary=False,
        data_views=[],
        skip_validation=False,
        format=None,
    )
    setattr(args, conflict, True)
    with pytest.raises(SystemExit) as exc:
        _validate_semantic_flag_relationships(args, inferred_mode=RunMode.NOTION_PRUNE_ORPHANS)
    assert exc.value.code == 1
    assert "--notion-prune-orphans" in capsys.readouterr().err


@pytest.mark.parametrize(
    ("argv", "label"),
    [
        (["--notion-prune-orphans", "--push-to-notion", "saved.json"], "--push-to-notion"),
        (["--notion-prune-orphans", "dv_123"], "positional data view arguments"),
    ],
)
def test_prune_conflict_rejected_through_effective_args(argv, label, capsys) -> None:
    """Regression for the standalone-policy bug: the conflict block must survive arg sanitization.

    The CLI validates ``_resolve_semantic_validation_args(...)`` output, not the raw args. That
    helper clears every dest in the mode's ``ignored_semantic_dests``. If the prune policy cleared
    ``notion_prune_orphans``, the whole conflict block would be skipped and these combinations would
    silently prune. Both argv keep prune as the inferred mode, so the prune policy is the one used.
    """
    args = parse_arguments(argv)
    assert _infer_run_mode_enum(args) is RunMode.NOTION_PRUNE_ORPHANS
    effective = _resolve_semantic_validation_args(args, inferred_mode=RunMode.NOTION_PRUNE_ORPHANS)
    assert effective.notion_prune_orphans is True  # policy must NOT clear the mode flag
    with pytest.raises(SystemExit) as exc:
        _validate_semantic_flag_relationships(effective, inferred_mode=RunMode.NOTION_PRUNE_ORPHANS)
    assert exc.value.code == 1
    assert "--notion-prune-orphans" in capsys.readouterr().err


@pytest.mark.parametrize(
    "argv",
    [
        ["--notion-prune-orphans", "--list-dataviews"],
        ["--notion-prune-orphans", "--stats"],
        ["--notion-prune-orphans", "--list-snapshots"],
    ],
)
def test_prune_rejects_higher_precedence_modes(argv, capsys) -> None:
    """A mode that outranks prune in _run_mode_checks must not silently drop the prune request."""
    args = parse_arguments(argv)
    inferred = _infer_run_mode_enum(args)
    assert inferred is not RunMode.NOTION_PRUNE_ORPHANS  # another mode won the dispatch
    with pytest.raises(SystemExit) as exc:
        _validate_semantic_flag_relationships(args, inferred_mode=inferred)
    assert exc.value.code == 1
    assert "--notion-prune-orphans" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [["--notion-prune-orphans"], ["--notion-prune-orphans", "--dry-run"]])
def test_prune_alone_or_with_dry_run_passes_validation(argv) -> None:
    """Prune by itself (and with the --dry-run sub-flag) must NOT be rejected as a conflict."""
    args = parse_arguments(argv)
    assert _infer_run_mode_enum(args) is RunMode.NOTION_PRUNE_ORPHANS
    # Should not raise SystemExit.
    _validate_semantic_flag_relationships(args, inferred_mode=RunMode.NOTION_PRUNE_ORPHANS)


def test_prune_output_is_visible(tmp_path, capsys, monkeypatch) -> None:
    """Regression: the prune dispatch configures a console logger so its output is visible.

    With no registry in the output dir there are no orphans, so this exercises the
    'nothing to prune' message end-to-end without needing a Notion token.
    """
    monkeypatch.setattr(sys, "argv", ["cja_auto_sdr", "--notion-prune-orphans", "--output-dir", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        _main_impl()
    assert exc.value.code == 0
    assert "No orphan Notion pages to prune." in capsys.readouterr().out
