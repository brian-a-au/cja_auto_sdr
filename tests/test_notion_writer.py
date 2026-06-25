"""Tests for Notion block builder and writer."""

from __future__ import annotations

import builtins
import logging
import sys
import types
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from cja_auto_sdr.output.notion_database import DATABASE_SCHEMA
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


@pytest.mark.parametrize(
    ("severity", "expected_emoji"),
    [
        # CJA quality engine vocabulary (core.constants.QUALITY_SEVERITY_ORDER).
        ("CRITICAL", "🔴"),
        ("HIGH", "🔴"),
        ("MEDIUM", "⚠️"),
        ("LOW", "ℹ️"),
        ("INFO", "ℹ️"),
        # Generic logging vocabulary kept for safety.
        ("ERROR", "🔴"),
        ("WARN", "⚠️"),
        ("WARNING", "⚠️"),
        # Severity strings are upper-cased before lookup.
        ("high", "🔴"),
        ("medium", "⚠️"),
        # Unknown severities fall back to the info icon.
        ("BOGUS", "ℹ️"),
    ],
)
def test_dq_callout_blocks_severity_icon_mapping(severity, expected_emoji):
    """Severity icons must cover the CJA engine's CRITICAL/HIGH/MEDIUM/LOW/INFO vocabulary.

    Regression: HIGH and MEDIUM previously fell through to the info icon because
    the mapper only knew the ERROR/WARN/INFO vocabulary.
    """
    dq_df = pd.DataFrame(
        {
            "Severity": [severity],
            "Component": ["item_x"],
            "Issue": ["some issue"],
        }
    )
    blocks = _dq_callout_blocks(dq_df)
    assert blocks[0]["callout"]["icon"]["emoji"] == expected_emoji


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


def _neutralize_dotenv(monkeypatch):
    """Install a no-op ``dotenv`` so a developer's local .env can't leak into
    these resolver tests. ``resolve_notion_credentials`` calls
    ``from dotenv import load_dotenv; load_dotenv()``, and python-dotenv's
    ``find_dotenv`` searches upward from the source file (not the cwd), so
    chdir is not enough — we replace the module with a no-op loader. Works
    whether or not python-dotenv is installed."""
    fake = types.ModuleType("dotenv")
    fake.load_dotenv = lambda *args, **kwargs: False
    monkeypatch.setitem(sys.modules, "dotenv", fake)


def test_resolve_notion_credentials_reads_env(monkeypatch):
    _neutralize_dotenv(monkeypatch)
    monkeypatch.setenv("NOTION_TOKEN", "secret-token")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent-page-id")
    from cja_auto_sdr.output.writers.notion import resolve_notion_credentials

    token, parent_id = resolve_notion_credentials()
    assert token == "secret-token"
    assert parent_id == "parent-page-id"


def test_resolve_notion_credentials_missing_token_raises(monkeypatch):
    _neutralize_dotenv(monkeypatch)
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
    _neutralize_dotenv(monkeypatch)
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


# ---------------------------------------------------------------------------
# write_notion_output — database upsert path
# ---------------------------------------------------------------------------


def test_writer_skips_db_upsert_when_database_id_is_none(tmp_path, monkeypatch):
    """v3.7.0 callers that don't pass a database_id are unaffected."""
    from cja_auto_sdr.output.writers.notion import write_notion_output

    monkeypatch.setenv("NOTION_TOKEN", "fake-token")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent-page")

    fake_client_class = MagicMock()
    fake_client = fake_client_class.return_value
    fake_client.pages.create.return_value = {"id": "new-page-id"}
    fake_client.blocks.children.append.return_value = {}

    with patch("cja_auto_sdr.output.writers.notion._require_notion_client", return_value=fake_client_class):
        result = write_notion_output(
            {"Metrics": pd.DataFrame()},
            {"Data View ID": "dv1", "Data View Name": "X"},
            "X",
            tmp_path,
            MagicMock(),
        )

    assert result == "notion://pages/new-page-id"
    fake_client.databases.retrieve.assert_not_called()
    fake_client.databases.create.assert_not_called()


def test_writer_upserts_db_row_when_database_id_provided(tmp_path, monkeypatch):
    from cja_auto_sdr.output.writers.notion import write_notion_output

    monkeypatch.setenv("NOTION_TOKEN", "fake-token")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent-page")

    fake_client_class = MagicMock()
    fake_client = fake_client_class.return_value
    fake_client.pages.create.side_effect = [
        {"id": "new-page-id"},  # detail page
        {"id": "new-row-id"},  # DB row
    ]
    fake_client.databases.retrieve.return_value = {
        "id": "db-given",
        "data_sources": [{"id": "ds-given"}],
    }
    fake_client.data_sources.retrieve.return_value = {
        "id": "ds-given",
        "properties": {name: {"id": "x"} for name in DATABASE_SCHEMA},
    }
    # No existing row in the database for this data view (registry is also empty).
    fake_client.data_sources.query.return_value = {"results": []}

    with patch("cja_auto_sdr.output.writers.notion._require_notion_client", return_value=fake_client_class):
        result = write_notion_output(
            {"Metrics": pd.DataFrame([{"a": 1}])},
            {"Data View ID": "dv1", "Data View Name": "X"},
            "X",
            tmp_path,
            MagicMock(),
            database_id="db-given",
        )

    assert result == "notion://pages/new-page-id"
    fake_client.databases.retrieve.assert_called_once_with(database_id="db-given")
    # one page.create for the SDR page, one for the DB row
    assert fake_client.pages.create.call_count == 2
    # DB row must use data_source_id parent
    db_row_call = fake_client.pages.create.call_args_list[1]
    assert db_row_call.kwargs["parent"] == {"type": "data_source_id", "data_source_id": "ds-given"}


def test_writer_client_built_with_notion_version(tmp_path, monkeypatch):
    """write_notion_output must build the Notion client with notion_version='2025-09-03'."""
    from cja_auto_sdr.output.writers.notion import write_notion_output

    monkeypatch.setenv("NOTION_TOKEN", "fake-token")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent-page")

    fake_client_class = MagicMock()
    fake_client = fake_client_class.return_value
    fake_client.pages.create.return_value = {"id": "new-page-id"}
    fake_client.blocks.children.append.return_value = {}

    with patch("cja_auto_sdr.output.writers.notion._require_notion_client", return_value=fake_client_class):
        write_notion_output(
            {"Metrics": pd.DataFrame()},
            {"Data View ID": "dv1", "Data View Name": "X"},
            "X",
            tmp_path,
            MagicMock(),
        )

    # The client class must be called with notion_version="2025-09-03" and the SDK
    # log level raised so per-request-fail warnings don't duplicate our friendly errors.
    call_kwargs = fake_client_class.call_args.kwargs
    assert call_kwargs.get("notion_version") == "2025-09-03"
    assert call_kwargs.get("log_level") == logging.ERROR


def test_writer_converts_ensure_database_value_error_to_notion_config_error(tmp_path, monkeypatch):
    """Schema-mismatched database_id surfaces as NotionConfigurationError, not raw ValueError.

    Acceptance criterion AC#3: when ensure_database raises ValueError (missing required
    properties), write_notion_output must re-raise it as NotionConfigurationError so the
    CLI dispatcher can convert it to a clean exit 1 rather than a raw traceback.
    """
    from cja_auto_sdr.output.writers.notion import NotionConfigurationError, write_notion_output

    monkeypatch.setenv("NOTION_TOKEN", "fake-token")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent-page")

    fake_client_class = MagicMock()
    fake_client = fake_client_class.return_value
    fake_client.pages.create.return_value = {"id": "new-page-id"}
    fake_client.blocks.children.append.return_value = {}

    err_msg = "Database bad-db is missing required properties: ['Data Quality']"

    with (
        patch("cja_auto_sdr.output.writers.notion._require_notion_client", return_value=fake_client_class),
        patch(
            "cja_auto_sdr.output.notion_database.ensure_database",
            side_effect=ValueError(err_msg),
        ),
        pytest.raises(NotionConfigurationError) as exc_info,
    ):
        write_notion_output(
            data_dict={"Metrics": pd.DataFrame({"Name": ["m1"], "Type": ["metric"]})},
            metadata_dict={"Data View ID": "dv_bad", "Data View Name": "Bad DV"},
            base_filename="bad_sdr",
            output_dir=str(tmp_path),
            logger=logging.getLogger("test"),
            database_id="bad-db",
        )

    assert "Data Quality" in str(exc_info.value)
    assert "bad-db" in str(exc_info.value)


def test_writer_falls_back_to_query_when_registry_missing(tmp_path, monkeypatch):
    """When the registry has no row id, query the DB by Data View ID rather than create a duplicate."""
    from cja_auto_sdr.output.writers.notion import write_notion_output

    monkeypatch.setenv("NOTION_TOKEN", "fake-token")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent-page")

    fake_client_class = MagicMock()
    fake_client = fake_client_class.return_value
    fake_client.pages.create.return_value = {"id": "new-page-id"}  # detail page only
    fake_client.databases.retrieve.return_value = {"id": "db-given", "data_sources": [{"id": "ds-given"}]}
    fake_client.data_sources.retrieve.return_value = {
        "id": "ds-given",
        "properties": {name: {"id": "x"} for name in DATABASE_SCHEMA},
    }
    # Registry is empty (tmp_path) but the DB already has a row for this data view.
    fake_client.data_sources.query.return_value = {"results": [{"id": "existing-row-id"}]}
    fake_client.pages.update.return_value = {"id": "existing-row-id"}

    with patch("cja_auto_sdr.output.writers.notion._require_notion_client", return_value=fake_client_class):
        write_notion_output(
            {"Metrics": pd.DataFrame([{"a": 1}])},
            {"Data View ID": "dv1", "Data View Name": "X"},
            "X",
            tmp_path,
            MagicMock(),
            database_id="db-given",
        )

    # The existing row is updated, not duplicated: pages.create only for the detail page.
    assert fake_client.pages.create.call_count == 1
    fake_client.pages.update.assert_called_once()
    assert fake_client.pages.update.call_args.kwargs["page_id"] == "existing-row-id"


def test_writer_logs_created_database_id(tmp_path, monkeypatch):
    """--notion-create-database surfaces the newly created database id via the logger."""
    from cja_auto_sdr.output.writers.notion import write_notion_output

    monkeypatch.setenv("NOTION_TOKEN", "fake-token")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "parent-page")

    fake_client_class = MagicMock()
    fake_client = fake_client_class.return_value
    fake_client.pages.create.side_effect = [{"id": "new-page-id"}, {"id": "new-row-id"}]
    fake_client.databases.create.return_value = {"id": "new-db-id", "data_sources": [{"id": "new-ds-id"}]}
    fake_client.data_sources.query.return_value = {"results": []}
    mock_logger = MagicMock()

    with patch("cja_auto_sdr.output.writers.notion._require_notion_client", return_value=fake_client_class):
        write_notion_output(
            {"Metrics": pd.DataFrame([{"a": 1}])},
            {"Data View ID": "dv1", "Data View Name": "X"},
            "X",
            tmp_path,
            mock_logger,
            create_database=True,
        )

    logged = " ".join(str(c.args) for c in mock_logger.info.call_args_list)
    assert "new-db-id" in logged


def test_resolve_notion_credentials_parent_optional_when_not_required(monkeypatch):
    """require_parent=False returns the token without requiring NOTION_PARENT_PAGE_ID."""
    _neutralize_dotenv(monkeypatch)
    monkeypatch.setenv("NOTION_TOKEN", "tok")
    monkeypatch.delenv("NOTION_PARENT_PAGE_ID", raising=False)
    from cja_auto_sdr.output.writers.notion import resolve_notion_credentials

    token, parent = resolve_notion_credentials(require_parent=False)
    assert token == "tok"
    assert parent is None


def test_force_new_records_superseded_page_as_orphan(tmp_path, monkeypatch):
    """--notion-force-new over an existing page records the old page id as an orphan."""
    from cja_auto_sdr.output.notion_registry import (
        get_registry_path,
        lookup_orphaned_page_ids,
        lookup_page_id,
        store_page_id,
    )
    from cja_auto_sdr.output.writers.notion import create_or_update_page

    reg = get_registry_path(tmp_path)
    store_page_id(reg, "dv1", "page-old")  # pretend a prior publish

    client = MagicMock()
    client.pages.create.return_value = {"id": "page-new"}

    new_id = create_or_update_page(
        client,
        "parent",
        "DV — SDR",
        "dv1",
        [],
        reg,
        force_new=True,
    )

    assert new_id == "page-new"
    assert lookup_page_id(reg, "dv1") == "page-new"
    assert lookup_orphaned_page_ids(reg, "dv1") == ["page-old"]


def test_force_new_with_no_prior_page_records_no_orphan(tmp_path):
    from cja_auto_sdr.output.notion_registry import get_registry_path, lookup_orphaned_page_ids
    from cja_auto_sdr.output.writers.notion import create_or_update_page

    reg = get_registry_path(tmp_path)
    client = MagicMock()
    client.pages.create.return_value = {"id": "page-new"}

    create_or_update_page(client, "parent", "DV — SDR", "dv1", [], reg, force_new=True)
    assert lookup_orphaned_page_ids(reg, "dv1") == []


# ---------------------------------------------------------------------------
# Task 3: prune_notion_orphans tests
# ---------------------------------------------------------------------------


def test_prune_orphans_archives_and_clears(tmp_path, monkeypatch):
    from cja_auto_sdr.output.notion_registry import (
        add_orphaned_page_id,
        get_registry_path,
        lookup_orphaned_page_ids,
        store_page_id,
    )
    from cja_auto_sdr.output.writers.notion import prune_notion_orphans

    monkeypatch.setenv("NOTION_TOKEN", "tok")
    monkeypatch.delenv("NOTION_PARENT_PAGE_ID", raising=False)  # not required for prune

    reg = get_registry_path(tmp_path)
    store_page_id(reg, "dv1", "page-current")
    add_orphaned_page_id(reg, "dv1", "orphan-1")
    add_orphaned_page_id(reg, "dv1", "orphan-2")

    fake_cls = MagicMock()
    fake_client = fake_cls.return_value
    fake_client.pages.update.return_value = {"id": "x"}
    with patch("cja_auto_sdr.output.writers.notion._require_notion_client", return_value=fake_cls):
        archived, gone = prune_notion_orphans(tmp_path, MagicMock())

    assert (archived, gone) == (2, 0)
    assert fake_client.pages.update.call_count == 2
    # archive == archived=True, by page id
    assert {c.kwargs["page_id"] for c in fake_client.pages.update.call_args_list} == {"orphan-1", "orphan-2"}
    assert all(c.kwargs.get("archived") is True for c in fake_client.pages.update.call_args_list)
    assert lookup_orphaned_page_ids(reg, "dv1") == []  # cleared


def test_prune_orphans_dry_run_makes_no_calls(tmp_path, monkeypatch):
    from cja_auto_sdr.output.notion_registry import add_orphaned_page_id, get_registry_path, lookup_orphaned_page_ids
    from cja_auto_sdr.output.writers.notion import prune_notion_orphans

    monkeypatch.setenv("NOTION_TOKEN", "tok")

    reg = get_registry_path(tmp_path)
    add_orphaned_page_id(reg, "dv1", "orphan-1")

    with patch("cja_auto_sdr.output.writers.notion._require_notion_client") as req:
        archived, gone = prune_notion_orphans(tmp_path, MagicMock(), dry_run=True)

    assert (archived, gone) == (0, 0)
    req.assert_not_called()  # no client built, no API calls
    assert lookup_orphaned_page_ids(reg, "dv1") == ["orphan-1"]  # registry untouched


def test_prune_orphans_nothing_to_do(tmp_path, monkeypatch):
    from cja_auto_sdr.output.writers.notion import prune_notion_orphans

    monkeypatch.setenv("NOTION_TOKEN", "tok")
    with patch("cja_auto_sdr.output.writers.notion._require_notion_client") as req:
        assert prune_notion_orphans(tmp_path, MagicMock()) == (0, 0)
    req.assert_not_called()


def test_prune_orphans_object_not_found_is_cleared(tmp_path, monkeypatch):
    from cja_auto_sdr.output.notion_registry import add_orphaned_page_id, get_registry_path, lookup_orphaned_page_ids
    from cja_auto_sdr.output.writers.notion import prune_notion_orphans

    monkeypatch.setenv("NOTION_TOKEN", "tok")

    reg = get_registry_path(tmp_path)
    add_orphaned_page_id(reg, "dv1", "gone-page")

    class _NotFound(Exception):
        code = "object_not_found"

    _NotFound.__name__ = "APIResponseError"

    fake_cls = MagicMock()
    fake_cls.return_value.pages.update.side_effect = _NotFound()
    with patch("cja_auto_sdr.output.writers.notion._require_notion_client", return_value=fake_cls):
        archived, gone = prune_notion_orphans(tmp_path, MagicMock())

    assert (archived, gone) == (0, 1)
    assert lookup_orphaned_page_ids(reg, "dv1") == []  # dead id removed anyway


# ---------------------------------------------------------------------------
# Task 3: repair_notion_database tests
# ---------------------------------------------------------------------------


def test_repair_notion_database_applies(tmp_path, monkeypatch):
    from cja_auto_sdr.output.writers.notion import repair_notion_database

    monkeypatch.setenv("NOTION_TOKEN", "tok")
    monkeypatch.delenv("NOTION_PARENT_PAGE_ID", raising=False)  # not required

    fake_cls = MagicMock()
    fake_client = fake_cls.return_value
    fake_client.databases.retrieve.return_value = {"id": "db1", "data_sources": [{"id": "ds1"}]}
    fake_client.data_sources.retrieve.return_value = {"properties": {"Name": {"type": "title"}}}
    fake_client.data_sources.update.return_value = {"id": "ds1"}

    with patch("cja_auto_sdr.output.writers.notion._require_notion_client", return_value=fake_cls):
        result = repair_notion_database("db1", MagicMock())

    assert result.applied is True
    assert fake_client.data_sources.update.call_count == 1


def test_repair_notion_database_dry_run_no_update(tmp_path, monkeypatch):
    from cja_auto_sdr.output.writers.notion import repair_notion_database

    monkeypatch.setenv("NOTION_TOKEN", "tok")

    fake_cls = MagicMock()
    fake_client = fake_cls.return_value
    fake_client.databases.retrieve.return_value = {"id": "db1", "data_sources": [{"id": "ds1"}]}
    fake_client.data_sources.retrieve.return_value = {"properties": {"Name": {"type": "title"}}}

    with patch("cja_auto_sdr.output.writers.notion._require_notion_client", return_value=fake_cls):
        result = repair_notion_database("db1", MagicMock(), dry_run=True)

    assert result.applied is False
    fake_client.data_sources.update.assert_not_called()


def test_repair_notion_database_maps_value_error(monkeypatch):
    from cja_auto_sdr.output.writers.notion import NotionConfigurationError, repair_notion_database

    monkeypatch.setenv("NOTION_TOKEN", "tok")

    fake_cls = MagicMock()
    fake_cls.return_value.databases.retrieve.return_value = {"id": "db1", "data_sources": []}
    with patch("cja_auto_sdr.output.writers.notion._require_notion_client", return_value=fake_cls):
        with pytest.raises(NotionConfigurationError, match="no data source"):
            repair_notion_database("db1", MagicMock())


def test_repair_notion_database_maps_api_error(monkeypatch):
    """databases.retrieve raising an API error surfaces as NotionAPIError."""
    from cja_auto_sdr.output.writers.notion import NotionAPIError, repair_notion_database

    monkeypatch.setenv("NOTION_TOKEN", "tok")

    class FakeAPIError(Exception):
        code = "object_not_found"

    FakeAPIError.__name__ = "APIResponseError"

    fake_cls = MagicMock()
    fake_cls.return_value.databases.retrieve.side_effect = FakeAPIError("not found")

    with patch("cja_auto_sdr.output.writers.notion._require_notion_client", return_value=fake_cls):
        with pytest.raises(NotionAPIError):
            repair_notion_database("db1", MagicMock())


def test_repair_notion_database_conflict_only_not_called_up_to_date(monkeypatch):
    """Conflicts but nothing to add must NOT log 'up to date' (Codex P2): the schema is not clean."""
    from cja_auto_sdr.output.notion_database import DATABASE_SCHEMA, _schema_property_type
    from cja_auto_sdr.output.writers.notion import repair_notion_database

    monkeypatch.setenv("NOTION_TOKEN", "tok")

    live = {n: {"type": _schema_property_type(e)} for n, e in DATABASE_SCHEMA.items()}
    live["Metrics Count"] = {"type": "rich_text"}  # conflict; nothing missing

    fake_cls = MagicMock()
    fc = fake_cls.return_value
    fc.databases.retrieve.return_value = {"id": "db1", "data_sources": [{"id": "ds1"}]}
    fc.data_sources.retrieve.return_value = {"properties": live}
    logger = MagicMock()

    with patch("cja_auto_sdr.output.writers.notion._require_notion_client", return_value=fake_cls):
        result = repair_notion_database("db1", logger)

    assert result.to_add == [] and result.conflicts
    fc.data_sources.update.assert_not_called()
    info_msgs = " ".join(str(c.args[0]) for c in logger.info.call_args_list)
    assert "up to date" not in info_msgs
    assert "manual resolution" in info_msgs


def test_repair_notion_database_resolves_db_id_from_env(monkeypatch):
    """With no explicit id, repair falls back to NOTION_DATABASE_ID from the env/.env (Codex P2)."""
    from cja_auto_sdr.output.writers.notion import repair_notion_database

    monkeypatch.setenv("NOTION_TOKEN", "tok")
    monkeypatch.setenv("NOTION_DATABASE_ID", "db-from-env")

    fake_cls = MagicMock()
    fc = fake_cls.return_value
    fc.databases.retrieve.return_value = {"id": "db-from-env", "data_sources": [{"id": "ds1"}]}
    fc.data_sources.retrieve.return_value = {"properties": {"Name": {"type": "title"}}}

    with patch("cja_auto_sdr.output.writers.notion._require_notion_client", return_value=fake_cls):
        repair_notion_database(None, MagicMock())  # no explicit id → resolved from env

    fc.databases.retrieve.assert_called_once()
    assert fc.databases.retrieve.call_args.kwargs["database_id"] == "db-from-env"


# ---------------------------------------------------------------------------
# Coverage hardening (v3.11.1): error-mapping helpers, pagination/delete edge
# cases, prune/repair error branches, and the dotenv-absent fallbacks.
# ---------------------------------------------------------------------------


def test_build_sdr_blocks_includes_dq_section_when_present():
    """A non-empty Data Quality frame renders the DQ heading plus per-row callouts."""
    data_dict = {
        "Data Quality": pd.DataFrame([{"Severity": "WARN", "Message": "check this"}]),
        "Metrics": pd.DataFrame({"Name": ["m1"], "Type": ["metric"]}),
    }
    metadata = {"Data View Name": "Test", "Data View ID": "dv_001"}
    blocks = build_sdr_blocks(data_dict, metadata)
    headings = [b["heading_2"]["rich_text"][0]["text"]["content"] for b in blocks if b["type"] == "heading_2"]
    assert any("Data Quality" in h for h in headings)
    assert any(b["type"] == "callout" for b in blocks)


def test_extract_api_error_code_stringifies_non_str_code():
    """A non-string, non-None ``code`` (e.g. an enum/int) is coerced via str()."""
    from cja_auto_sdr.output.writers import notion as _notion_mod

    class FakeErr(Exception):
        code = 123

    assert _notion_mod._extract_api_error_code(FakeErr()) == "123"


def test_extract_api_error_code_returns_none_when_code_absent():
    """No ``code`` attribute (or an explicit None) yields None."""
    from cja_auto_sdr.output.writers import notion as _notion_mod

    class FakeErr(Exception):
        code = None

    assert _notion_mod._extract_api_error_code(FakeErr()) is None
    assert _notion_mod._extract_api_error_code(Exception("plain")) is None


def test_extract_retry_after_seconds_parses_numeric_header():
    from cja_auto_sdr.output.writers import notion as _notion_mod

    class FakeErr(Exception):
        headers = {"Retry-After": "2.5"}

    assert _notion_mod._extract_retry_after_seconds(FakeErr()) == 2.5


def test_extract_retry_after_seconds_returns_none_for_unparseable_header():
    from cja_auto_sdr.output.writers import notion as _notion_mod

    class FakeErr(Exception):
        headers = {"Retry-After": "soon-ish"}

    assert _notion_mod._extract_retry_after_seconds(FakeErr()) is None


def test_friendly_notion_error_message_for_validation_error():
    from cja_auto_sdr.output.writers import notion as _notion_mod

    class FakeErr(Exception):
        code = "validation_error"

    msg = _notion_mod._friendly_notion_error_message(FakeErr("bad payload"))
    assert "rejected the payload" in msg


def test_friendly_notion_error_message_falls_back_for_unknown_code():
    from cja_auto_sdr.output.writers import notion as _notion_mod

    class FakeErr(Exception):
        code = "some_unknown_code"

    msg = _notion_mod._friendly_notion_error_message(FakeErr("boom"))
    assert "some_unknown_code" in msg


def test_list_all_child_block_ids_breaks_when_next_cursor_missing():
    """has_more=True but a missing next_cursor must break, not loop forever."""
    from cja_auto_sdr.output.writers.notion import _list_all_child_block_ids

    client = MagicMock()
    client.blocks.children.list.return_value = {
        "results": [{"id": "b1"}],
        "has_more": True,
        "next_cursor": None,
    }
    ids = _list_all_child_block_ids(client, "page-x")
    assert ids == ["b1"]
    client.blocks.children.list.assert_called_once()


def test_clear_page_blocks_single_block_uses_direct_delete():
    """A single child block is deleted directly without spinning up a thread pool."""
    from cja_auto_sdr.output.writers.notion import _clear_page_blocks

    client = MagicMock()
    client.blocks.children.list.return_value = {"results": [{"id": "only-block"}], "has_more": False}
    _clear_page_blocks(client, "page-x")
    client.blocks.delete.assert_called_once_with(block_id="only-block")


def test_resolve_notion_credentials_handles_missing_dotenv(monkeypatch):
    """When python-dotenv is unavailable, resolution falls back to the raw env."""
    monkeypatch.setitem(sys.modules, "dotenv", None)  # `from dotenv import load_dotenv` -> ImportError
    monkeypatch.setenv("NOTION_TOKEN", "tok")
    monkeypatch.setenv("NOTION_PARENT_PAGE_ID", "pid")
    from cja_auto_sdr.output.writers.notion import resolve_notion_credentials

    token, parent = resolve_notion_credentials()
    assert token == "tok"
    assert parent == "pid"


def test_prune_orphans_api_error_other_than_not_found_raises(tmp_path, monkeypatch):
    """A non-404 API error while archiving an orphan surfaces as NotionAPIError."""
    from cja_auto_sdr.output.notion_registry import add_orphaned_page_id, get_registry_path
    from cja_auto_sdr.output.writers.notion import NotionAPIError, prune_notion_orphans

    monkeypatch.setenv("NOTION_TOKEN", "tok")
    reg = get_registry_path(tmp_path)
    add_orphaned_page_id(reg, "dv1", "orphan-1")

    class _Forbidden(Exception):
        code = "restricted_resource"

    _Forbidden.__name__ = "APIResponseError"

    fake_cls = MagicMock()
    fake_cls.return_value.pages.update.side_effect = _Forbidden()
    with patch("cja_auto_sdr.output.writers.notion._require_notion_client", return_value=fake_cls):
        with pytest.raises(NotionAPIError):
            prune_notion_orphans(tmp_path, MagicMock())


def test_prune_orphans_non_api_error_reraises(tmp_path, monkeypatch):
    """A non-API error while archiving an orphan propagates unchanged."""
    from cja_auto_sdr.output.notion_registry import add_orphaned_page_id, get_registry_path
    from cja_auto_sdr.output.writers.notion import prune_notion_orphans

    monkeypatch.setenv("NOTION_TOKEN", "tok")
    reg = get_registry_path(tmp_path)
    add_orphaned_page_id(reg, "dv1", "orphan-1")

    fake_cls = MagicMock()
    fake_cls.return_value.pages.update.side_effect = RuntimeError("disk error")
    with patch("cja_auto_sdr.output.writers.notion._require_notion_client", return_value=fake_cls):
        with pytest.raises(RuntimeError, match="disk error"):
            prune_notion_orphans(tmp_path, MagicMock())


def test_repair_notion_database_handles_missing_dotenv(monkeypatch):
    """repair_notion_database tolerates python-dotenv being absent."""
    monkeypatch.setitem(sys.modules, "dotenv", None)  # force ImportError on the dotenv import
    monkeypatch.setenv("NOTION_TOKEN", "tok")
    from cja_auto_sdr.output.writers.notion import repair_notion_database

    fake_cls = MagicMock()
    fc = fake_cls.return_value
    fc.databases.retrieve.return_value = {"id": "db1", "data_sources": [{"id": "ds1"}]}
    fc.data_sources.retrieve.return_value = {"properties": {"Name": {"type": "title"}}}
    fc.data_sources.update.return_value = {"id": "ds1"}
    with patch("cja_auto_sdr.output.writers.notion._require_notion_client", return_value=fake_cls):
        result = repair_notion_database("db1", MagicMock())
    assert result.applied is True


def test_repair_notion_database_reraises_non_api_error(monkeypatch):
    """A non-API error from repair_database_schema propagates unchanged."""
    from cja_auto_sdr.output.writers.notion import repair_notion_database

    monkeypatch.setenv("NOTION_TOKEN", "tok")
    fake_cls = MagicMock()
    fake_cls.return_value.databases.retrieve.side_effect = RuntimeError("kaboom")
    with patch("cja_auto_sdr.output.writers.notion._require_notion_client", return_value=fake_cls):
        with pytest.raises(RuntimeError, match="kaboom"):
            repair_notion_database("db1", MagicMock())


def test_repair_notion_database_warns_on_missing_title(monkeypatch):
    """A registry whose title column was renamed yields a 'missing' conflict warning."""
    from cja_auto_sdr.output.notion_database import DATABASE_SCHEMA, _schema_property_type
    from cja_auto_sdr.output.writers.notion import repair_notion_database

    monkeypatch.setenv("NOTION_TOKEN", "tok")
    # Full schema except the canonical title "Name" is absent -> ("Name", "title", "missing").
    live = {n: {"type": _schema_property_type(e)} for n, e in DATABASE_SCHEMA.items() if n != "Name"}
    fake_cls = MagicMock()
    fc = fake_cls.return_value
    fc.databases.retrieve.return_value = {"id": "db1", "data_sources": [{"id": "ds1"}]}
    fc.data_sources.retrieve.return_value = {"properties": live}
    logger = MagicMock()
    with patch("cja_auto_sdr.output.writers.notion._require_notion_client", return_value=fake_cls):
        result = repair_notion_database("db1", logger)
    assert ("Name", "title", "missing") in result.conflicts
    warn_msgs = " ".join(str(c.args[0]) for c in logger.warning.call_args_list)
    assert "absent" in warn_msgs


def test_repair_notion_database_logs_up_to_date_when_clean(monkeypatch):
    """A schema that needs nothing logs the up-to-date confirmation."""
    from cja_auto_sdr.output.notion_database import DATABASE_SCHEMA, _schema_property_type
    from cja_auto_sdr.output.writers.notion import repair_notion_database

    monkeypatch.setenv("NOTION_TOKEN", "tok")
    live = {n: {"type": _schema_property_type(e)} for n, e in DATABASE_SCHEMA.items()}
    fake_cls = MagicMock()
    fc = fake_cls.return_value
    fc.databases.retrieve.return_value = {"id": "db1", "data_sources": [{"id": "ds1"}]}
    fc.data_sources.retrieve.return_value = {"properties": live}
    logger = MagicMock()
    with patch("cja_auto_sdr.output.writers.notion._require_notion_client", return_value=fake_cls):
        result = repair_notion_database("db1", logger)
    assert result.to_add == [] and result.conflicts == []
    info_msgs = " ".join(str(c.args[0]) for c in logger.info.call_args_list)
    assert "up to date" in info_msgs
