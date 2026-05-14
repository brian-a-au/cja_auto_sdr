"""Output writer registry (thin wrapper around generator implementations)."""

from cja_auto_sdr.output.writers import (
    write_csv_output,
    write_excel_output,
    write_html_output,
    write_json_output,
    write_markdown_output,
)
from cja_auto_sdr.output.writers.notion import write_notion_output

WRITER_REGISTRY = {
    "csv": write_csv_output,
    "excel": write_excel_output,
    "xlsx": write_excel_output,
    "html": write_html_output,
    "json": write_json_output,
    "markdown": write_markdown_output,
    "md": write_markdown_output,
    "notion": write_notion_output,
}


def get_writer(format_name: str):
    """Return a writer function for the given format name."""
    return WRITER_REGISTRY.get(format_name)


__all__ = ["WRITER_REGISTRY", "get_writer"]
