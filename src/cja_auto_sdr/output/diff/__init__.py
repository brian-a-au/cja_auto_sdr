"""Diff output renderers — text-oriented diff comparison formatters.

This package contains the diff output renderers extracted from generator.py:

- console: Color-coded terminal output with side-by-side tables
- grouped: Field-grouped diff output for console
- pr_comment: GitHub/GitLab PR comment markdown format
- markdown: Full markdown diff report written to file
- common: Shared helpers (value formatting, change symbols, breaking change detection)
"""

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
from cja_auto_sdr.output.diff.grouped import write_diff_grouped_by_field_output
from cja_auto_sdr.output.diff.markdown import (
    _format_markdown_side_by_side,
    write_diff_markdown_output,
)
from cja_auto_sdr.output.diff.pr_comment import write_diff_pr_comment_output

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
    "write_diff_grouped_by_field_output",
    "write_diff_markdown_output",
    "write_diff_pr_comment_output",
]
