"""Output module - Output format writers and registries."""

from __future__ import annotations

from cja_auto_sdr.output.excel import ExcelFormatCache, apply_excel_formatting
from cja_auto_sdr.output.protocols import OutputWriter
from cja_auto_sdr.output.registry import WRITER_REGISTRY, get_writer
from cja_auto_sdr.output.writers import (
    write_csv_output,
    write_excel_output,
    write_html_output,
    write_json_output,
    write_markdown_output,
)

__all__ = [
    "WRITER_REGISTRY",
    "ExcelFormatCache",
    "OutputWriter",
    "apply_excel_formatting",
    "get_writer",
    "write_csv_output",
    "write_excel_output",
    "write_html_output",
    "write_json_output",
    "write_markdown_output",
]
