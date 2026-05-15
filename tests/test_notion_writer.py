"""Tests for Notion block builder and writer."""

from __future__ import annotations

import builtins
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


def test_table_block_zero_column_df_returns_none():
    """A DataFrame with no columns has nothing to render — Notion rejects table_width=0."""
    df = pd.DataFrame()
    assert _table_block(df) is None


def test_section_blocks_zero_column_df_returns_empty():
    """No columns means no table; the section should not emit an orphan heading."""
    df = pd.DataFrame({}, index=[0, 1, 2])
    assert _section_blocks("Metrics", df) == []


def test_section_blocks_returns_heading_plus_table():
    df = pd.DataFrame({"Name": ["a"], "Type": ["metric"]})
    blocks = _section_blocks("Metrics", df)
    assert blocks[0]["type"] == "heading_2"
    assert blocks[1]["type"] == "table"


def test_section_blocks_empty_df_returns_empty_list():
    df = pd.DataFrame()
    blocks = _section_blocks("Metrics", df)
    assert blocks == []


def test_section_blocks_small_df_emits_single_table():
    df = pd.DataFrame({"Name": [f"m{i}" for i in range(50)], "Type": ["metric"] * 50})
    blocks = _section_blocks("Metrics", df)
    # heading + one table
    assert len(blocks) == 2
    assert blocks[0]["type"] == "heading_2"
    assert blocks[1]["type"] == "table"
    # header row + 50 data rows = 51 children, well within 100
    assert len(blocks[1]["table"]["children"]) == 51


def test_section_blocks_splits_large_df_into_sibling_tables():
    """A section with > 99 data rows must split into sibling tables under one heading.

    Notion caps a single block's children at 100 (including a table's
    table_row children). Each emitted table must contain at most 1 header
    row + 99 data rows, and the union must preserve every input row.
    """
    n = 250
    df = pd.DataFrame({"Name": [f"m{i:03d}" for i in range(n)], "Type": ["metric"] * n})
    blocks = _section_blocks("Metrics", df)

    # 1 heading + ceil(250 / 99) = 3 tables = 4 blocks
    assert len(blocks) == 4
    assert blocks[0]["type"] == "heading_2"
    assert all(b["type"] == "table" for b in blocks[1:])

    # Every table must respect the 100-children Notion API cap.
    for table in blocks[1:]:
        assert len(table["table"]["children"]) <= 100

    # All data rows preserved across the sibling tables, in original order.
    recovered: list[str] = []
    for table in blocks[1:]:
        # children[0] is the header row; skip it.
        for row in table["table"]["children"][1:]:
            recovered.append(row["table_row"]["cells"][0][0]["text"]["content"])
    assert recovered == [f"m{i:03d}" for i in range(n)]


def test_section_blocks_chunks_at_99_data_rows():
    """Each split table holds at most 99 data rows + 1 header = 100 children."""
    df = pd.DataFrame({"Name": [f"d{i:03d}" for i in range(99)], "Type": ["dim"] * 99})
    blocks = _section_blocks("Dimensions", df)
    # 99 rows == single chunk (heading + one table, 100 children total).
    assert len(blocks) == 2
    assert len(blocks[1]["table"]["children"]) == 100

    df_overflow = pd.DataFrame({"Name": [f"d{i:03d}" for i in range(100)], "Type": ["dim"] * 100})
    blocks_overflow = _section_blocks("Dimensions", df_overflow)
    # 100 rows must split: heading + two tables (99 + 1).
    assert len(blocks_overflow) == 3
    assert len(blocks_overflow[1]["table"]["children"]) == 100  # header + 99
    assert len(blocks_overflow[2]["table"]["children"]) == 2  # header + 1


def test_dq_callout_blocks_warn_severity():
    dq_df = pd.DataFrame(
        {
            "Severity": ["WARN"],
            "Component": ["metric_a"],
            "Issue": ["Missing description"],
        }
    )
    blocks = _dq_callout_blocks(dq_df)
    assert len(blocks) == 1
    assert blocks[0]["callout"]["icon"]["emoji"] == "⚠️"


def test_dq_callout_blocks_error_severity():
    dq_df = pd.DataFrame(
        {
            "Severity": ["ERROR"],
            "Component": ["dim_b"],
            "Issue": ["Null values"],
        }
    )
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
    headings = [b["heading_2"]["rich_text"][0]["text"]["content"] for b in blocks if b["type"] == "heading_2"]
    assert any("Metrics" in h for h in headings)
    assert not any("Dimensions" in h for h in headings)


def test_build_sdr_blocks_dq_section_omitted_when_empty():
    data_dict = {
        "Metrics": pd.DataFrame({"Name": ["m1"], "Type": ["metric"]}),
        "Data Quality": pd.DataFrame(),
    }
    metadata = {"Data View Name": "Test", "Data View ID": "dv_001"}
    blocks = build_sdr_blocks(data_dict, metadata)
    headings = [b["heading_2"]["rich_text"][0]["text"]["content"] for b in blocks if b["type"] == "heading_2"]
    assert not any("Data Quality" in h for h in headings)


# ---- API layer tests (mocked Client) ----


def test_resolve_notion_credentials_reads_env(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "secret-token")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent-page-id")
    from cja_auto_sdr.output.writers.notion import resolve_notion_credentials

    token, parent_id = resolve_notion_credentials()
    assert token == "secret-token"
    assert parent_id == "parent-page-id"


def test_resolve_notion_credentials_missing_token_raises(monkeypatch):
    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_PARENT_PAGE_ID", raising=False)
    from cja_auto_sdr.output.writers.notion import (
        NotionConfigurationError,
        resolve_notion_credentials,
    )

    with pytest.raises(NotionConfigurationError) as exc_info:
        resolve_notion_credentials()
    assert "NOTION_TOKEN" in str(exc_info.value)


def test_resolve_notion_credentials_missing_parent_page_raises(monkeypatch):
    monkeypatch.setenv("NOTION_TOKEN", "secret-token")
    monkeypatch.delenv("NOTION_PARENT_PAGE_ID", raising=False)
    from cja_auto_sdr.output.writers.notion import (
        NotionConfigurationError,
        resolve_notion_credentials,
    )

    with pytest.raises(NotionConfigurationError) as exc_info:
        resolve_notion_credentials()
    assert "NOTION_PARENT_PAGE_ID" in str(exc_info.value)


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
    blocks = [{"type": "paragraph", "paragraph": {"rich_text": []}} for _ in range(150)]
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


def test_no_top_level_notion_client_imports_in_package():
    """Static guard: the optional `notion-client` extra must never be imported at module-load time.

    The package is published with `notion-client` as an opt-in extra. If a top-level
    `import notion_client` slips in (e.g. via an autoformat or refactor), the
    package will fail to import for any user who hasn't installed the extra —
    which is the entire point of marking it optional. Catch that statically here
    instead of relying on the no-extras CI job alone.
    """
    import ast
    from pathlib import Path

    pkg_root = Path(__file__).resolve().parent.parent / "src" / "cja_auto_sdr"
    offenders: list[tuple[str, int]] = []
    for py_file in pkg_root.rglob("*.py"):
        source = py_file.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(py_file))
        # Only scan module-level imports (tree.body) — function-local imports
        # are how this codebase keeps the optional dep optional.
        for node in tree.body:
            if isinstance(node, ast.Import):
                if any(
                    alias.name == "notion_client" or alias.name.startswith("notion_client.") for alias in node.names
                ):
                    offenders.append((str(py_file.relative_to(pkg_root)), node.lineno))
            elif isinstance(node, ast.ImportFrom):
                if node.module and (node.module == "notion_client" or node.module.startswith("notion_client.")):
                    offenders.append((str(py_file.relative_to(pkg_root)), node.lineno))

    assert offenders == [], (
        "Top-level `import notion_client` found — the optional extra must only be "
        f"imported lazily inside a function. Offenders: {offenders}"
    )


def test_require_notion_client_raises_when_sdk_missing(monkeypatch):
    """Missing notion-client extra raises NotionDependencyError with install instructions."""
    import sys as _sys

    from cja_auto_sdr.output.writers import notion as _notion_mod
    from cja_auto_sdr.output.writers.notion import NotionDependencyError

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "notion_client":
            raise ImportError("No module named 'notion_client'")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    monkeypatch.setitem(_sys.modules, "notion_client", None)

    with pytest.raises(NotionDependencyError) as exc_info:
        _notion_mod._require_notion_client()
    msg = str(exc_info.value)
    assert "notion extra" in msg
    assert "cja-auto-sdr[notion]" in msg


def test_push_to_notion_cli_converts_config_error_to_exit(monkeypatch, tmp_path):
    """The CLI dispatcher must convert NotionConfigurationError to exit code 1."""
    import json as _json

    monkeypatch.delenv("NOTION_TOKEN", raising=False)
    monkeypatch.delenv("NOTION_PARENT_PAGE_ID", raising=False)
    artifact = tmp_path / "sdr.json"
    artifact.write_text(_json.dumps({"metadata": {"Data View ID": "dv_1"}, "metrics": []}))

    from cja_auto_sdr.generator import _push_to_notion_from_json

    with pytest.raises(SystemExit) as exc_info:
        _push_to_notion_from_json(str(artifact))
    assert exc_info.value.code == 1


def test_call_with_rate_limit_retry_succeeds_after_one_429(monkeypatch):
    """A single 429 should retry-and-succeed without raising."""
    from cja_auto_sdr.output.writers import notion as _notion_mod

    class FakeRateLimited(Exception):
        code = "rate_limited"

    # Make _is_notion_api_error recognize our fake class.
    FakeRateLimited.__name__ = "APIResponseError"

    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] == 1:
            raise FakeRateLimited("rate limited")
        return "ok"

    # Skip the sleep so the test is fast.
    monkeypatch.setattr(_notion_mod.time, "sleep", lambda _s: None)
    assert _notion_mod._call_with_rate_limit_retry(flaky) == "ok"
    assert calls["n"] == 2


def test_call_with_rate_limit_retry_gives_up_after_max_attempts(monkeypatch):
    from cja_auto_sdr.output.writers import notion as _notion_mod

    class FakeRateLimited(Exception):
        code = "rate_limited"

    FakeRateLimited.__name__ = "APIResponseError"

    calls = {"n": 0}

    def always_429():
        calls["n"] += 1
        raise FakeRateLimited("rate limited")

    monkeypatch.setattr(_notion_mod.time, "sleep", lambda _s: None)
    with pytest.raises(FakeRateLimited):
        _notion_mod._call_with_rate_limit_retry(always_429)
    assert calls["n"] == _notion_mod._RATE_LIMIT_MAX_ATTEMPTS


def test_call_with_rate_limit_retry_passes_non_rate_limit_errors_through(monkeypatch):
    """Non-429 API errors must not be retried — they propagate immediately."""
    from cja_auto_sdr.output.writers import notion as _notion_mod

    class FakeUnauthorized(Exception):
        code = "unauthorized"

    FakeUnauthorized.__name__ = "APIResponseError"

    calls = {"n": 0}

    def auth_fail():
        calls["n"] += 1
        raise FakeUnauthorized("bad token")

    with pytest.raises(FakeUnauthorized):
        _notion_mod._call_with_rate_limit_retry(auth_fail)
    assert calls["n"] == 1


def test_friendly_notion_error_message_for_unauthorized():
    from cja_auto_sdr.output.writers import notion as _notion_mod

    class FakeErr(Exception):
        code = "unauthorized"

    msg = _notion_mod._friendly_notion_error_message(FakeErr("nope"))
    assert "NOTION_TOKEN" in msg
    assert "NOTION_PARENT_PAGE_ID" in msg


def test_friendly_notion_error_message_for_rate_limit():
    from cja_auto_sdr.output.writers import notion as _notion_mod

    class FakeErr(Exception):
        code = "rate_limited"

    assert "rate limit" in _notion_mod._friendly_notion_error_message(FakeErr("x")).lower()


def test_write_notion_output_wraps_api_error_as_notion_api_error(tmp_path, monkeypatch):
    """API errors from create_or_update_page surface as NotionAPIError with friendly text."""
    import logging as _logging

    monkeypatch.setenv("NOTION_TOKEN", "tok")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "pid")
    from cja_auto_sdr.output.writers.notion import NotionAPIError, write_notion_output

    class FakeUnauthorized(Exception):
        code = "unauthorized"

    FakeUnauthorized.__name__ = "APIResponseError"

    mock_client_instance = MagicMock()
    mock_client_instance.pages.create.side_effect = FakeUnauthorized("nope")
    with patch(
        "cja_auto_sdr.output.writers.notion._require_notion_client",
    ) as mock_cls:
        mock_cls.return_value = MagicMock(return_value=mock_client_instance)
        with pytest.raises(NotionAPIError) as exc_info:
            write_notion_output(
                data_dict={"Metrics": pd.DataFrame({"Name": ["m"], "Type": ["x"]})},
                metadata_dict={"Data View Name": "T", "Data View ID": "dv_1"},
                base_filename="t",
                output_dir=str(tmp_path),
                logger=_logging.getLogger("test"),
            )
    assert "NOTION_TOKEN" in str(exc_info.value)


def test_clear_page_blocks_lists_all_before_deleting():
    """Listing and deleting must be split into two phases — no in-loop delete during list."""
    from cja_auto_sdr.output.writers.notion import _clear_page_blocks

    client = MagicMock()
    list_calls: list[str] = []
    delete_calls: list[str] = []

    def fake_list(**kwargs):
        list_calls.append("list")
        cursor = kwargs.get("start_cursor")
        if cursor is None:
            return {"results": [{"id": "b1"}, {"id": "b2"}], "has_more": True, "next_cursor": "c1"}
        return {"results": [{"id": "b3"}], "has_more": False}

    def fake_delete(**kwargs):
        delete_calls.append(kwargs["block_id"])

    client.blocks.children.list.side_effect = fake_list
    client.blocks.delete.side_effect = fake_delete

    _clear_page_blocks(client, "page-abc")
    assert sorted(delete_calls) == ["b1", "b2", "b3"]
    # All listing must complete before any deletion runs.
    assert len(list_calls) == 2
