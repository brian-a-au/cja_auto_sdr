"""CLI flag wiring + dispatch validation for the v3.8.0 database flags."""

from __future__ import annotations

from cja_auto_sdr.cli.parser import parse_arguments


def test_notion_database_id_flag_parses() -> None:
    args = parse_arguments(["dv1", "--format", "notion", "--notion-database-id", "abc-123"])
    assert args.notion_database_id == "abc-123"


def test_notion_create_database_flag_parses() -> None:
    args = parse_arguments(["dv1", "--format", "notion", "--notion-create-database"])
    assert args.notion_create_database is True


def test_notion_database_id_default_is_none() -> None:
    args = parse_arguments(["dv1", "--format", "notion"])
    assert args.notion_database_id is None
    assert args.notion_create_database is False


def test_org_report_accepts_notion_format() -> None:
    args = parse_arguments(["--org-report", "--format", "notion"])
    assert args.org_report is True
    assert args.format == "notion"
