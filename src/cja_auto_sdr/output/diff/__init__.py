"""Diff output renderers and file writers.

This package contains the diff output renderers and file writers extracted
from generator.py:

- console: Color-coded terminal output with side-by-side tables
- grouped: Field-grouped diff output for console
- pr_comment: GitHub/GitLab PR comment markdown format
- markdown: Full markdown diff report written to file
- common: Shared helpers (value formatting, change symbols, breaking change detection)
- json: JSON diff file output
- html: HTML diff file output with professional styling
- excel: Excel diff file output with color-coded rows
- csv: CSV diff file output
- write_diff_output: Dispatcher that routes to the correct writer(s)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from cja_auto_sdr.output.diff.common import (
    ANSIColors,
    _format_diff_value,
    _get_change_detail,
    _get_change_emoji,
    _get_change_symbol,
    _get_colored_symbol,
    _get_inventory_change_detail,
    detect_breaking_changes,
)
from cja_auto_sdr.output.diff.console import (
    _format_side_by_side,
    write_diff_console_output,
)
from cja_auto_sdr.output.diff.csv import write_diff_csv_output
from cja_auto_sdr.output.diff.excel import write_diff_excel_output
from cja_auto_sdr.output.diff.grouped import write_diff_grouped_by_field_output
from cja_auto_sdr.output.diff.html import write_diff_html_output
from cja_auto_sdr.output.diff.json import write_diff_json_output
from cja_auto_sdr.output.diff.markdown import (
    _format_markdown_side_by_side,
    write_diff_markdown_output,
)
from cja_auto_sdr.output.diff.pr_comment import write_diff_pr_comment_output

if TYPE_CHECKING:
    import logging

    from cja_auto_sdr.diff.models import DiffResult


def write_diff_output(
    diff_result: DiffResult,
    output_format: str,
    base_filename: str,
    output_dir: str | Path,
    logger: logging.Logger,
    changes_only: bool = False,
    summary_only: bool = False,
    side_by_side: bool = False,
    use_color: bool = True,
    group_by_field: bool = False,
    group_by_field_limit: int = 10,
) -> str | None:
    """
    Write diff comparison output in specified format(s).

    Args:
        diff_result: The DiffResult to output
        output_format: Output format ('console', 'json', 'markdown', 'html', 'excel', 'csv', 'all', 'pr-comment')
        base_filename: Base filename without extension
        output_dir: Output directory path
        logger: Logger instance
        changes_only: Only include changed items
        summary_only: Only show summary (console only)
        side_by_side: Show side-by-side comparison for modified items
        use_color: Use ANSI color codes in console output
        group_by_field: Group changes by field name instead of component
        group_by_field_limit: Max items per section in group-by-field output (0 = unlimited)

    Returns:
        Console output string (for console/pr-comment format) or None
    """
    from cja_auto_sdr.core.constants import should_generate_format

    os.makedirs(output_dir, exist_ok=True)
    console_output = None

    # Handle group-by-field output mode
    if group_by_field and should_generate_format(output_format, "console"):
        console_output = write_diff_grouped_by_field_output(diff_result, use_color, group_by_field_limit)
        print(console_output)  # noqa: T201
        if output_format == "console":
            return console_output

    # Handle PR comment format
    if output_format == "pr-comment":
        console_output = write_diff_pr_comment_output(diff_result, changes_only)
        print(console_output)  # noqa: T201
        return console_output

    if should_generate_format(output_format, "console") and not group_by_field:
        console_output = write_diff_console_output(diff_result, changes_only, summary_only, side_by_side, use_color)
        print(console_output)  # noqa: T201

    if output_format == "console":
        return console_output

    if should_generate_format(output_format, "json"):
        write_diff_json_output(diff_result, base_filename, output_dir, logger, changes_only)

    if should_generate_format(output_format, "markdown"):
        write_diff_markdown_output(diff_result, base_filename, output_dir, logger, changes_only, side_by_side)

    if should_generate_format(output_format, "html"):
        write_diff_html_output(diff_result, base_filename, output_dir, logger, changes_only)

    if should_generate_format(output_format, "excel"):
        write_diff_excel_output(diff_result, base_filename, output_dir, logger, changes_only)

    if should_generate_format(output_format, "csv"):
        write_diff_csv_output(diff_result, base_filename, output_dir, logger, changes_only)

    return console_output


__all__ = [
    "ANSIColors",
    "_format_diff_value",
    "_format_markdown_side_by_side",
    "_format_side_by_side",
    "_get_change_detail",
    "_get_change_emoji",
    "_get_change_symbol",
    "_get_colored_symbol",
    "_get_inventory_change_detail",
    "detect_breaking_changes",
    "write_diff_console_output",
    "write_diff_csv_output",
    "write_diff_excel_output",
    "write_diff_grouped_by_field_output",
    "write_diff_html_output",
    "write_diff_json_output",
    "write_diff_markdown_output",
    "write_diff_output",
    "write_diff_pr_comment_output",
]
