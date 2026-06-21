"""CLI wiring for --notion-repair-database and --notion-print-database-schema (v3.10.0)."""

from __future__ import annotations

import sys

import pytest

from cja_auto_sdr.cli.parser import parse_arguments
from cja_auto_sdr.cli.standalone_policy import standalone_prevalidation_policy
from cja_auto_sdr.generator import (
    RunMode,
    _infer_run_mode_enum,
    _main_impl,
    _validate_semantic_flag_relationships,
)


def test_flags_parse() -> None:
    assert parse_arguments(["--notion-repair-database"]).notion_repair_database is True
    assert parse_arguments(["--notion-print-database-schema"]).notion_print_database_schema is True
    assert parse_arguments(["dv1"]).notion_repair_database is False


def test_modes_inferred() -> None:
    assert _infer_run_mode_enum(parse_arguments(["--notion-repair-database"])) is RunMode.NOTION_REPAIR_DATABASE
    assert _infer_run_mode_enum(parse_arguments(["--notion-print-database-schema"])) is RunMode.NOTION_PRINT_SCHEMA


def test_print_schema_wins_over_other_modes() -> None:
    # Informational; must take precedence so it is never silently dropped.
    args = parse_arguments(["--notion-print-database-schema", "--list-dataviews"])
    assert _infer_run_mode_enum(args) is RunMode.NOTION_PRINT_SCHEMA


def test_standalone_policies_registered() -> None:
    assert standalone_prevalidation_policy("notion_repair_database") is not None
    assert standalone_prevalidation_policy("notion_print_schema") is not None


def test_print_schema_outputs_schema_no_creds(capsys, monkeypatch) -> None:
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.setattr(sys, "argv", ["cja_auto_sdr", "--notion-print-database-schema"])
    with pytest.raises(SystemExit) as exc:
        _main_impl()
    assert exc.value.code == 0
    assert "CJA SDR Registry — database schema" in capsys.readouterr().out


def test_repair_requires_database_id(capsys, monkeypatch) -> None:
    monkeypatch.delenv("NOTION_DATABASE_ID", raising=False)
    monkeypatch.setattr(sys, "argv", ["cja_auto_sdr", "--notion-repair-database"])
    with pytest.raises(SystemExit) as exc:
        _main_impl()
    assert exc.value.code == 1
    err = capsys.readouterr().err
    assert "--notion-database-id" in err or "NOTION_DATABASE_ID" in err


@pytest.mark.parametrize(
    "argv",
    [
        ["--notion-repair-database", "--org-report"],
        ["--notion-repair-database", "--list-dataviews"],
        ["--notion-repair-database", "--batch", "dv1", "dv2"],
        ["--notion-repair-database", "dv_123"],
        ["--notion-repair-database", "--notion-prune-orphans"],
        ["--notion-repair-database", "--notion-create-database"],
    ],
)
def test_repair_rejects_other_commands(argv, capsys) -> None:
    args = parse_arguments(argv)
    inferred = _infer_run_mode_enum(args)
    with pytest.raises(SystemExit) as exc:
        _validate_semantic_flag_relationships(args, inferred_mode=inferred)
    assert exc.value.code == 1
    assert "--notion-repair-database" in capsys.readouterr().err


@pytest.mark.parametrize("argv", [["--notion-repair-database"], ["--notion-repair-database", "--dry-run"]])
def test_repair_alone_passes_validation(argv) -> None:
    args = parse_arguments(argv)
    assert _infer_run_mode_enum(args) is RunMode.NOTION_REPAIR_DATABASE
    _validate_semantic_flag_relationships(args, inferred_mode=RunMode.NOTION_REPAIR_DATABASE)
