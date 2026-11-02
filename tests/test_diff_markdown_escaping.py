"""Diff Markdown and PR comment tables escape pipes, backticks, backslashes and newlines."""

from __future__ import annotations

import logging
import re

from cja_auto_sdr.diff.comparator import DataViewComparator
from cja_auto_sdr.diff.models import DataViewSnapshot
from cja_auto_sdr.output.diff.markdown import write_diff_markdown_output
from cja_auto_sdr.output.diff.pr_comment import write_diff_pr_comment_output

log = logging.getLogger("test_diff_markdown_escaping")


def _result():
    src = DataViewSnapshot(
        data_view_id="dv_1",
        data_view_name="Prod | EU",
        metrics=[
            {"id": "metrics/a", "name": "Orders | Net", "type": "int", "description": "Line one\nLine two"},
            {"id": "metrics/b", "name": "Plain", "type": "int", "description": "old"},
        ],
        dimensions=[],
    )
    tgt = DataViewSnapshot(
        data_view_id="dv_2",
        data_view_name="Prod | US",
        metrics=[
            {"id": "metrics/a", "name": "Orders | Net", "type": "int", "description": "Line one\nLine 2"},
            {"id": "metrics/b", "name": "Plain", "type": "int", "description": "new"},
            {"id": "metrics/c", "name": "Added | pipe", "type": "int", "description": ""},
        ],
        dimensions=[],
    )
    return DataViewComparator(log).compare(src, tgt, source_label="EU | prod", target_label="US")


def _cells(line: str) -> int:
    """Count unescaped pipes (GFM: a backslash escapes the next character)."""
    count = 0
    i = 0
    while i < len(line):
        if line[i] == "\\":
            i += 2
            continue
        if line[i] == "|":
            count += 1
        i += 1
    return count


def _assert_tables_consistent(text: str) -> int:
    header = None
    tables = 0
    for line in text.split("\n"):
        if line.startswith("|"):
            if header is None:
                header = _cells(line)
                tables += 1
            else:
                assert _cells(line) == header, line
        elif header is not None:
            assert line.strip() == "", f"stray line inside table: {line!r}"
            header = None
    return tables


def test_diff_markdown_tables_escape_pipes_and_newlines(tmp_path):
    path = write_diff_markdown_output(_result(), "d", str(tmp_path), log, side_by_side=True)
    text = open(path, encoding="utf-8").read()
    assert _assert_tables_consistent(text) >= 3
    assert "Orders \\| Net" in text
    assert "Line one<br>Line two" in text
    assert "\\\\|" not in text  # no double escaping


def test_pr_comment_rows_escape_names():
    text = write_diff_pr_comment_output(_result())
    assert _assert_tables_consistent(text) >= 2
    assert "Orders \\| Net" in text


def test_cell_helper_is_shared_with_org_trending():
    from cja_auto_sdr.org.writers.trending import _escape_markdown_table_cell
    from cja_auto_sdr.output.markdown_escape import escape_markdown_table_cell

    value = "a\\b|c`d\r\ne\nf"
    assert _escape_markdown_table_cell(value) == escape_markdown_table_cell(value)
    assert escape_markdown_table_cell(value) == "a\\\\b\\|c\\`d<br>e<br>f"
    assert re.fullmatch(r"plain text", escape_markdown_table_cell("plain text"))


def _nan_name_result():
    from cja_auto_sdr.diff.models import (
        ChangeType,
        ComponentDiff,
        DiffResult,
        DiffSummary,
        InventoryItemDiff,
        MetadataDiff,
    )

    nan = float("nan")
    comp = ComponentDiff(id="m1", name=nan, change_type=ChangeType.MODIFIED, changed_fields={"description": ("x", "y")})
    added = ComponentDiff(id="m2", name=None, change_type=ChangeType.ADDED)
    inv = InventoryItemDiff(id="s1", inventory_type="segment", name=nan, change_type=ChangeType.ADDED)
    return DiffResult(
        summary=DiffSummary(metrics_added=1, metrics_modified=1, segments_added=1),
        metadata_diff=MetadataDiff(source_name=None, target_name=nan, source_id="a", target_id="b"),
        metric_diffs=[comp, added],
        dimension_diffs=[],
        segments_diffs=[inv],
    )


def test_nan_name_blank_in_text_writers(tmp_path):
    """DIFF-26: a NaN or None component name is blank, never the text 'nan' or 'None'."""
    from cja_auto_sdr.output.diff.console import write_diff_console_output
    from cja_auto_sdr.output.diff.grouped import write_diff_grouped_by_field_output
    from cja_auto_sdr.output.diff.html import write_diff_html_output

    result = _nan_name_result()
    md = open(write_diff_markdown_output(result, "d", str(tmp_path), log), encoding="utf-8").read()
    html_text = open(write_diff_html_output(result, "d", str(tmp_path), log), encoding="utf-8").read()
    outputs = {
        "markdown": md,
        "pr_comment": write_diff_pr_comment_output(result),
        "html": html_text,
        "console": write_diff_console_output(result, use_color=False),
        "grouped": write_diff_grouped_by_field_output(result, use_color=False),
    }
    for fmt, text in outputs.items():
        assert not re.search(r"\bnan\b", text, re.IGNORECASE), fmt
        assert not re.search(r"\bNone\b", text), fmt
