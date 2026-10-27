"""Output writers (current implementations live in generator for compatibility)."""

from __future__ import annotations

from cja_auto_sdr.output.writers.csv import write_csv_output
from cja_auto_sdr.output.writers.excel import write_excel_output
from cja_auto_sdr.output.writers.html import write_html_output
from cja_auto_sdr.output.writers.json import write_json_output
from cja_auto_sdr.output.writers.markdown import write_markdown_output

__all__ = [
    "write_csv_output",
    "write_excel_output",
    "write_html_output",
    "write_json_output",
    "write_markdown_output",
]
