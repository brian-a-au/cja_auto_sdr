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
