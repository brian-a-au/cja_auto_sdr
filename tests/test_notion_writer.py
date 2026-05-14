"""Tests for Notion block builder and writer."""
from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from cja_auto_sdr.output.writers.notion import (
    _callout_block,
    _dq_callout_blocks,
    _heading2_block,
    _metadata_callout_block,
    _rich_text,
    _section_blocks,
    _table_block,
    _table_row_block,
    build_sdr_blocks,
)


def test_rich_text_returns_list_with_text_object():
    result = _rich_text("hello")
    assert isinstance(result, list)
    assert result[0]["type"] == "text"
    assert result[0]["text"]["content"] == "hello"


def test_heading2_block_type():
    block = _heading2_block("Metrics")
    assert block["type"] == "heading_2"
    assert block["heading_2"]["rich_text"][0]["text"]["content"] == "Metrics"


def test_callout_block_defaults():
    block = _callout_block("Some info")
    assert block["type"] == "callout"
    assert block["callout"]["icon"]["emoji"] == "📋"
    assert block["callout"]["rich_text"][0]["text"]["content"] == "Some info"


def test_callout_block_custom_emoji():
    block = _callout_block("Warning", emoji="⚠️")
    assert block["callout"]["icon"]["emoji"] == "⚠️"


def test_table_row_block_structure():
    row = _table_row_block(["col1", "col2"])
    assert row["type"] == "table_row"
    assert len(row["table_row"]["cells"]) == 2
    assert row["table_row"]["cells"][0][0]["text"]["content"] == "col1"


def test_table_block_has_header_row_plus_data_rows():
    df = pd.DataFrame({"Name": ["metric_a", "metric_b"], "Type": ["dim", "metric"]})
    block = _table_block(df)
    assert block["type"] == "table"
    assert block["table"]["has_column_header"] is True
    children = block["table"]["children"]
    assert len(children) == 3
    assert children[0]["table_row"]["cells"][0][0]["text"]["content"] == "Name"
    assert children[1]["table_row"]["cells"][0][0]["text"]["content"] == "metric_a"


def test_table_block_empty_df():
    df = pd.DataFrame({"Name": [], "Type": []})
    block = _table_block(df)
    children = block["table"]["children"]
    assert len(children) == 1


def test_section_blocks_returns_heading_plus_table():
    df = pd.DataFrame({"Name": ["a"], "Type": ["metric"]})
    blocks = _section_blocks("Metrics", df)
    assert blocks[0]["type"] == "heading_2"
    assert blocks[1]["type"] == "table"


def test_section_blocks_empty_df_returns_empty_list():
    df = pd.DataFrame()
    blocks = _section_blocks("Metrics", df)
    assert blocks == []


def test_dq_callout_blocks_warn_severity():
    dq_df = pd.DataFrame({
        "Severity": ["WARN"],
        "Component": ["metric_a"],
        "Issue": ["Missing description"],
    })
    blocks = _dq_callout_blocks(dq_df)
    assert len(blocks) == 1
    assert blocks[0]["callout"]["icon"]["emoji"] == "⚠️"


def test_dq_callout_blocks_error_severity():
    dq_df = pd.DataFrame({
        "Severity": ["ERROR"],
        "Component": ["dim_b"],
        "Issue": ["Null values"],
    })
    blocks = _dq_callout_blocks(dq_df)
    assert blocks[0]["callout"]["icon"]["emoji"] == "🔴"


def test_dq_callout_blocks_empty_df_returns_empty():
    blocks = _dq_callout_blocks(pd.DataFrame())
    assert blocks == []


def test_metadata_callout_block_content():
    metadata = {
        "Data View Name": "Web Analytics",
        "Data View ID": "dv_123",
        "Generated Date & timestamp and timezone": "2026-05-14 10:00:00 UTC",
    }
    block = _metadata_callout_block(metadata)
    assert block["type"] == "callout"
    content = block["callout"]["rich_text"][0]["text"]["content"]
    assert "Web Analytics" in content
    assert "dv_123" in content


def test_build_sdr_blocks_structure():
    data_dict = {
        "Metrics": pd.DataFrame({"Name": ["m1"], "Type": ["metric"]}),
        "Dimensions": pd.DataFrame({"Name": ["d1"], "Type": ["dim"]}),
        "Data Quality": pd.DataFrame(),
    }
    metadata = {"Data View Name": "Test", "Data View ID": "dv_001"}
    blocks = build_sdr_blocks(data_dict, metadata)
    types = [b["type"] for b in blocks]
    assert "callout" in types
    assert "heading_2" in types
    assert "table" in types
    assert "divider" in types
    assert "paragraph" in types


def test_build_sdr_blocks_omits_empty_sections():
    data_dict = {
        "Metrics": pd.DataFrame({"Name": ["m1"], "Type": ["metric"]}),
        "Dimensions": pd.DataFrame(),
    }
    metadata = {"Data View Name": "Test", "Data View ID": "dv_001"}
    blocks = build_sdr_blocks(data_dict, metadata)
    headings = [
        b["heading_2"]["rich_text"][0]["text"]["content"]
        for b in blocks
        if b["type"] == "heading_2"
    ]
    assert any("Metrics" in h for h in headings)
    assert not any("Dimensions" in h for h in headings)


def test_build_sdr_blocks_dq_section_omitted_when_empty():
    data_dict = {
        "Metrics": pd.DataFrame({"Name": ["m1"], "Type": ["metric"]}),
        "Data Quality": pd.DataFrame(),
    }
    metadata = {"Data View Name": "Test", "Data View ID": "dv_001"}
    blocks = build_sdr_blocks(data_dict, metadata)
    headings = [
        b["heading_2"]["rich_text"][0]["text"]["content"]
        for b in blocks
        if b["type"] == "heading_2"
    ]
    assert not any("Data Quality" in h for h in headings)


# ---- API layer tests (mocked Client) ----


def test_resolve_notion_credentials_reads_env(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "secret-token")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent-page-id")
    from cja_auto_sdr.output.writers.notion import resolve_notion_credentials
    token, parent_id = resolve_notion_credentials()
    assert token == "secret-token"
    assert parent_id == "parent-page-id"


def test_resolve_notion_credentials_missing_token_exits(monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_PARENT_PAGE_ID", raising=False)
    from cja_auto_sdr.output.writers.notion import resolve_notion_credentials
    with pytest.raises(SystemExit) as exc_info:
        resolve_notion_credentials()
    assert exc_info.value.code == 1


def test_resolve_notion_credentials_missing_parent_page_exits(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "secret-token")
    monkeypatch.delenv("NOTION_PARENT_PAGE_ID", raising=False)
    from cja_auto_sdr.output.writers.notion import resolve_notion_credentials
    with pytest.raises(SystemExit) as exc_info:
        resolve_notion_credentials()
    assert exc_info.value.code == 1


def test_clear_page_blocks_deletes_all_children():
    from cja_auto_sdr.output.writers.notion import _clear_page_blocks
    client = MagicMock()
    client.blocks.children.list.return_value = {
        "results": [{"id": "block-1"}, {"id": "block-2"}],
        "has_more": False,
    }
    _clear_page_blocks(client, "page-abc")
    assert client.blocks.delete.call_count == 2
    client.blocks.delete.assert_any_call(block_id="block-1")
    client.blocks.delete.assert_any_call(block_id="block-2")


def test_clear_page_blocks_handles_pagination():
    from cja_auto_sdr.output.writers.notion import _clear_page_blocks
    client = MagicMock()
    client.blocks.children.list.side_effect = [
        {"results": [{"id": "block-1"}], "has_more": True, "next_cursor": "cursor-x"},
        {"results": [{"id": "block-2"}], "has_more": False},
    ]
    _clear_page_blocks(client, "page-abc")
    assert client.blocks.delete.call_count == 2


def test_append_blocks_batches_at_100():
    from cja_auto_sdr.output.writers.notion import _append_blocks
    client = MagicMock()
    blocks = [
        {"type": "paragraph", "paragraph": {"rich_text": []}} for _ in range(150)
    ]
    _append_blocks(client, "page-abc", blocks)
    assert client.blocks.children.append.call_count == 2
    first_call_blocks = client.blocks.children.append.call_args_list[0][1]["children"]
    assert len(first_call_blocks) == 100


def test_create_or_update_page_creates_new_when_not_in_registry(tmp_path):
    from cja_auto_sdr.output.writers.notion import create_or_update_page
    client = MagicMock()
    client.pages.create.return_value = {"id": "new-page-id"}
    registry_path = tmp_path / ".notion_pages.json"
    page_id = create_or_update_page(
        client,
        "parent-id",
        "Web Analytics — SDR",
        "dv_123",
        [{"type": "paragraph", "paragraph": {"rich_text": []}}],
        registry_path,
        force_new=False,
    )
    assert page_id == "new-page-id"
    client.pages.create.assert_called_once()


def test_create_or_update_page_updates_existing_when_in_registry(tmp_path):
    import json
    from cja_auto_sdr.output.writers.notion import create_or_update_page
    registry_path = tmp_path / ".notion_pages.json"
    registry_path.write_text(json.dumps({"dv_123": "existing-page-id"}))
    client = MagicMock()
    client.blocks.children.list.return_value = {"results": [], "has_more": False}
    page_id = create_or_update_page(
        client,
        "parent-id",
        "Web Analytics — SDR",
        "dv_123",
        [],
        registry_path,
        force_new=False,
    )
    assert page_id == "existing-page-id"
    client.pages.create.assert_not_called()


def test_create_or_update_page_force_new_ignores_registry(tmp_path):
    import json
    from cja_auto_sdr.output.writers.notion import create_or_update_page
    registry_path = tmp_path / ".notion_pages.json"
    registry_path.write_text(json.dumps({"dv_123": "old-page-id"}))
    client = MagicMock()
    client.pages.create.return_value = {"id": "fresh-page-id"}
    page_id = create_or_update_page(
        client,
        "parent-id",
        "Web Analytics — SDR",
        "dv_123",
        [],
        registry_path,
        force_new=True,
    )
    assert page_id == "fresh-page-id"
    client.pages.create.assert_called_once()


# ---- write_notion_output integration tests ----


def test_write_notion_output_returns_notion_url(tmp_path, monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "test-token")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent-id")
    from cja_auto_sdr.output.writers.notion import write_notion_output
    mock_client_instance = MagicMock()
    mock_client_instance.pages.create.return_value = {"id": "new-page-abc"}
    mock_client_instance.blocks.children.append.return_value = {}
    with patch(
        "cja_auto_sdr.output.writers.notion._require_notion_client",
    ) as mock_cls:
        mock_cls.return_value = MagicMock(return_value=mock_client_instance)
        result = write_notion_output(
            data_dict={
                "Metrics": pd.DataFrame({"Name": ["m1"], "Type": ["metric"]}),
            },
            metadata_dict={"Data View Name": "Test DV", "Data View ID": "dv_001"},
            base_filename="test_sdr",
            output_dir=str(tmp_path),
            logger=logging.getLogger("test"),
        )
    assert result.startswith("notion://pages/")


def test_write_notion_output_with_force_new(tmp_path, monkeypatch):
    import json
    monkeypatch.setenv("NOTION_TOKEN", "test-token")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent-id")
    (tmp_path / ".notion_pages.json").write_text(json.dumps({"dv_001": "old-page"}))
    from cja_auto_sdr.output.writers.notion import write_notion_output
    mock_client_instance = MagicMock()
    mock_client_instance.pages.create.return_value = {"id": "fresh-page"}
    mock_client_instance.blocks.children.append.return_value = {}
    with patch(
        "cja_auto_sdr.output.writers.notion._require_notion_client",
    ) as mock_cls:
        mock_cls.return_value = MagicMock(return_value=mock_client_instance)
        write_notion_output(
            data_dict={
                "Metrics": pd.DataFrame({"Name": ["m1"], "Type": ["metric"]}),
            },
            metadata_dict={"Data View Name": "Test DV", "Data View ID": "dv_001"},
            base_filename="test_sdr",
            output_dir=str(tmp_path),
            logger=logging.getLogger("test"),
            force_new=True,
        )
    mock_client_instance.pages.create.assert_called_once()


def test_notion_registered_in_writer_registry():
    from cja_auto_sdr.output.registry import WRITER_REGISTRY
    assert "notion" in WRITER_REGISTRY
