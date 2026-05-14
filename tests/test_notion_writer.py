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
