"""Direct unit tests for org snapshot helper utilities."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path

from cja_auto_sdr.org.snapshot_utils import (
    chronological_snapshot_sort_fields,
    newest_first_snapshot_sort_fields,
    org_report_snapshot_dir_candidates,
    org_report_snapshot_dir_key,
    org_report_snapshot_history_eligible,
    parse_snapshot_timestamp,
    snapshot_epoch,
    snapshot_identity_tokens,
    snapshot_path_text,
    snapshot_slug,
)


def test_parse_snapshot_timestamp_normalizes_common_cases():
    assert parse_snapshot_timestamp(None) is None
    assert parse_snapshot_timestamp("   ") is None
    assert parse_snapshot_timestamp("not-a-date") is None
    assert parse_snapshot_timestamp("2026-03-01T00:00:00Z").tzinfo is UTC
    assert parse_snapshot_timestamp("2026-03-01T00:00:00").tzinfo is UTC


def test_snapshot_epoch_and_sort_fields_handle_missing_timestamps():
    assert snapshot_epoch("invalid") is None
    assert chronological_snapshot_sort_fields("invalid")[0] is True
    assert newest_first_snapshot_sort_fields("invalid")[0] is True


def test_snapshot_path_text_and_slug_normalize_values(tmp_path: Path):
    relative = Path("tests") / ".." / "README.md"

    assert snapshot_path_text(None) == ""
    assert snapshot_path_text(relative) == str(relative.resolve(strict=False))
    assert snapshot_slug(None) == "unknown"
    assert snapshot_slug(":::") == "unknown"
    assert snapshot_slug("org@test.example") == "org_test_example"
    assert snapshot_slug(tmp_path.name, fallback="fallback") == tmp_path.name


def test_org_report_snapshot_dir_helpers_include_legacy_alias():
    key = org_report_snapshot_dir_key("org@test.example")
    candidates = org_report_snapshot_dir_candidates("org@test.example")

    assert key.startswith("org_test_example__")
    assert candidates == (key, "org_test_example")


def test_snapshot_identity_tokens_fall_back_when_no_primary_identity():
    assert snapshot_identity_tokens(snapshot_id="abc", content_hash="def") == (
        ("snapshot_id", "abc"),
        ("content_hash", "def"),
    )
    assert snapshot_identity_tokens(source_path="README.md")[0][0] == "source_path"
    assert snapshot_identity_tokens(fallback_parts=("org_a", 123)) == (("fallback", "org_a", "123"),)


def test_org_report_snapshot_history_eligible_accepts_non_mapping_summary():
    assert org_report_snapshot_history_eligible({"summary": []}) is True
    assert org_report_snapshot_history_eligible({"summary": {"is_sampled": True}}) is False
