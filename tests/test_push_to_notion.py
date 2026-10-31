"""Tests for --push-to-notion command path."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _make_sdr_json(tmp_path: Path) -> Path:
    """Write a minimal valid SDR JSON artifact."""
    payload = {
        "metadata": {
            "Data View Name": "Web Analytics",
            "Data View ID": "dv_001",
            "Generated Date & timestamp and timezone": "2026-05-14 10:00 UTC",
        },
        "metrics": [{"Name": "Visits", "Type": "metric"}],
        "dimensions": [{"Name": "Page", "Type": "dimension"}],
        "data_quality": [],
        "data_view": {"Data View ID": "dv_001"},
        "derived_fields": {},
        "calculated_metrics": {},
        "segments": {},
    }
    path = tmp_path / "dv_001_sdr.json"
    path.write_text(json.dumps(payload))
    return path


def test_push_to_notion_reads_json_and_calls_writer(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "test-token")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent-id")
    json_path = _make_sdr_json(tmp_path)

    from cja_auto_sdr.generator import _push_to_notion_from_json

    mock_client_instance = MagicMock()
    mock_client_instance.pages.create.return_value = {"id": "new-page"}
    mock_client_instance.blocks.children.append.return_value = {}

    with patch(
        "cja_auto_sdr.output.writers.notion._require_notion_client",
    ) as mock_cls:
        mock_cls.return_value = MagicMock(return_value=mock_client_instance)
        result = _push_to_notion_from_json(
            str(json_path),
            output_dir=str(tmp_path),
            force_new=False,
        )

    assert result.startswith("notion://pages/")


def test_push_to_notion_file_not_found_exits(tmp_path):
    from cja_auto_sdr.generator import _push_to_notion_from_json

    with pytest.raises(SystemExit) as exc_info:
        _push_to_notion_from_json(
            str(tmp_path / "nonexistent.json"),
            output_dir=str(tmp_path),
        )
    assert exc_info.value.code == 1


def test_push_to_notion_invalid_json_exits(tmp_path):
    from cja_auto_sdr.generator import _push_to_notion_from_json

    bad_json = tmp_path / "bad.json"
    bad_json.write_text("{ not valid json }")
    with pytest.raises(SystemExit) as exc_info:
        _push_to_notion_from_json(str(bad_json), output_dir=str(tmp_path))
    assert exc_info.value.code == 1


def test_push_to_notion_os_error_exits(tmp_path, monkeypatch):
    """OSError from JSON read (permission denied, IO error) surfaces as exit 1."""
    import cja_auto_sdr.generator as gen_mod

    fake = tmp_path / "exists_but_unreadable.json"
    fake.write_text("{}")

    def boom(self, *args, **kwargs):
        raise PermissionError("simulated permission denied")

    monkeypatch.setattr(Path, "read_text", boom)
    with pytest.raises(SystemExit) as exc_info:
        gen_mod._push_to_notion_from_json(str(fake), output_dir=str(tmp_path))
    assert exc_info.value.code == 1


def test_push_to_notion_takes_precedence_over_watch():
    """RunMode inference must resolve PUSH_TO_NOTION before WATCH so dispatch is consistent."""
    import argparse

    from cja_auto_sdr.generator import RunMode, _infer_run_mode_enum

    args = argparse.Namespace(
        push_to_notion="./sdr.json",
        watch_data_views=["dv_123"],
    )
    assert _infer_run_mode_enum(args) == RunMode.PUSH_TO_NOTION


class TestPushToNotionUnsearchableParent:
    def test_json_under_unsearchable_dir_reports_not_found(self, unsearchable_dir, capsys):
        from cja_auto_sdr.generator import _push_to_notion_from_json

        with pytest.raises(SystemExit):
            _push_to_notion_from_json(str(unsearchable_dir / "report.json"))
        assert "file not found" in capsys.readouterr().err


@pytest.mark.parametrize("content", ["[1, 2]", '"text"', "null"])
def test_push_non_object_json_exits_1_without_traceback(tmp_path, capsys, content):
    from cja_auto_sdr.generator import _push_to_notion_from_json

    path = tmp_path / "bad_shape.json"
    path.write_text(content)
    with pytest.raises(SystemExit) as exc_info:
        _push_to_notion_from_json(str(path), output_dir=str(tmp_path))
    assert exc_info.value.code == 1
    assert "must contain a JSON object" in capsys.readouterr().err


@pytest.mark.parametrize("section", ["derived_fields", "calculated_metrics", "segments"])
def test_push_null_inventory_section_is_skipped(tmp_path, section):
    from cja_auto_sdr.generator import _push_to_notion_from_json

    payload = {"metadata": {}, "metrics": [{"Name": "Visits"}], section: None}
    path = tmp_path / "null_section.json"
    path.write_text(json.dumps(payload))
    with patch(
        "cja_auto_sdr.output.writers.notion.write_notion_output",
        return_value="notion://pages/x",
    ) as mock_write:
        result = _push_to_notion_from_json(str(path), output_dir=str(tmp_path))

    assert result == "notion://pages/x"
    assert list(mock_write.call_args.kwargs["data_dict"]) == ["Metrics"]


@pytest.mark.parametrize(
    ("payload", "path"),
    [
        ({"metrics": 5}, "metrics"),
        ({"dimensions": "Page"}, "dimensions"),
        ({"data_quality": {"Issue": "x"}}, "data_quality"),
        ({"metrics": [1, 2]}, "metrics"),
        ({"derived_fields": {"fields": "abc"}}, "derived_fields.fields"),
        ({"calculated_metrics": {"metrics": {"id": "cm1"}}}, "calculated_metrics.metrics"),
        ({"segments": {"segments": [{"id": "s1"}, "s2"]}}, "segments.segments"),
    ],
)
def test_push_malformed_section_exits_1_without_traceback(tmp_path, capsys, payload, path):
    from cja_auto_sdr.generator import _push_to_notion_from_json

    json_path = tmp_path / "bad_section.json"
    json_path.write_text(json.dumps(payload))
    with (
        patch("cja_auto_sdr.output.writers.notion.write_notion_output") as mock_write,
        pytest.raises(SystemExit) as exc_info,
    ):
        _push_to_notion_from_json(str(json_path), output_dir=str(tmp_path))

    assert exc_info.value.code == 1
    err = capsys.readouterr().err
    assert f"'{path}'" in err
    assert "must be a list of objects" in err
    assert "Traceback" not in err
    mock_write.assert_not_called()


def test_push_all_sections_build_sheets_in_order(tmp_path):
    from cja_auto_sdr.generator import _push_to_notion_from_json

    payload = {
        "metadata": {},
        "metrics": [{"Name": "Visits"}],
        "dimensions": [{"Name": "Page"}],
        "data_quality": [{"Issue": "x"}],
        "derived_fields": {"fields": [{"id": "df1"}]},
        "calculated_metrics": {"metrics": [{"id": "cm1"}]},
        "segments": {"segments": [{"id": "s1"}]},
    }
    json_path = tmp_path / "full.json"
    json_path.write_text(json.dumps(payload))
    with patch(
        "cja_auto_sdr.output.writers.notion.write_notion_output",
        return_value="notion://pages/x",
    ) as mock_write:
        _push_to_notion_from_json(str(json_path), output_dir=str(tmp_path))

    assert list(mock_write.call_args.kwargs["data_dict"]) == [
        "Metrics",
        "Dimensions",
        "Data Quality",
        "Derived Fields",
        "Calculated Metrics",
        "Segments",
    ]
