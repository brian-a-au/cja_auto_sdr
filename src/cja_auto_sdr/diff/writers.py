"""Diff output writers (canonical implementation in output.diff; this module forwards for compatibility)."""

__all__ = [
    "write_diff_console_output",
    "write_diff_csv_output",
    "write_diff_excel_output",
    "write_diff_html_output",
    "write_diff_json_output",
    "write_diff_markdown_output",
    "write_diff_output",
    "write_diff_pr_comment_output",
]

from cja_auto_sdr.core.lazy import make_getattr

__getattr__ = make_getattr(__name__, __all__, target_module="cja_auto_sdr.output.diff")
