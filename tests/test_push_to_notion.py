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
