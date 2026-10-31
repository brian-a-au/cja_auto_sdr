"""Shared Markdown table cell escaping (dependency-free)."""

from __future__ import annotations


def escape_markdown_table_cell(value: object) -> str:
    """Escape Markdown table cell content without changing readable text."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace("|", "\\|")
        .replace("`", "\\`")
        .replace("\r\n", "<br>")
        .replace("\n", "<br>")
        .replace("\r", "<br>")
    )
