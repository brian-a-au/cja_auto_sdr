"""SDR output writers — extracted from generator.py for modularity.

This module contains the core SDR output format writers:
- apply_excel_formatting: Excel sheet formatting with severity colors
- write_excel_output: Excel workbook generation
- write_csv_output: CSV file generation (one file per sheet)
- write_json_output: Hierarchical JSON generation
- write_html_output: Styled HTML report generation
- write_markdown_output: GitHub-flavored Markdown generation

Also contains the ExcelFormatCache helper class.
"""

from __future__ import annotations

import html
import json
import logging
import math
import os
import re
from collections.abc import Mapping
from datetime import date, datetime
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from cja_auto_sdr.api.quality import DataQualityChecker
from cja_auto_sdr.core.colors import _format_error_msg
from cja_auto_sdr.core.exceptions import OutputError
from cja_auto_sdr.core.json_io import write_json_atomic_compatible, write_text_atomic_compatible
from cja_auto_sdr.core.version import __version__
from cja_auto_sdr.output.csv_staging import csv_member_name, publish_csv_bundle
from cja_auto_sdr.output.excel_staging import staged_excel_writer
from cja_auto_sdr.output.sdr.coverage import SdrCoverage, coverage_section_labels

__all__ = [
    "TYPED_SDR_SCHEMA_VERSION",
    "ExcelFormatCache",
    "apply_excel_formatting",
    "build_json_payload",
    "build_typed_json_payload",
    "serialize_typed_json",
    "to_native_json",
    "write_csv_output",
    "write_excel_output",
    "write_html_output",
    "write_json_output",
    "write_markdown_output",
    "write_typed_json_output",
]


class ExcelFormatCache:
    """Cache for Excel format objects to avoid recreating identical formats.

    xlsxwriter creates a new format object for each add_format() call, even if
    the properties are identical. This class caches formats by their properties
    to reuse them across multiple sheets, improving performance by 15-25% for
    workbooks with multiple sheets.

    Usage:
        cache = ExcelFormatCache(workbook)
        header_fmt = cache.get_format({'bold': True, 'bg_color': '#366092'})
    """

    def __init__(self, workbook):
        self.workbook = workbook
        self._cache: dict[tuple, Any] = {}

    def get_format(self, properties: dict[str, Any]) -> Any:
        """Get or create a format with the given properties.

        Args:
            properties: Dictionary of format properties (e.g., {'bold': True})

        Returns:
            xlsxwriter Format object
        """
        # Convert dict to a hashable key (sorted tuple of items)
        # Use repr() for nested values to avoid collisions (e.g. [1,2] vs '[1, 2]')
        cache_key = tuple(sorted((k, repr(v)) for k, v in properties.items()))

        if cache_key not in self._cache:
            self._cache[cache_key] = self.workbook.add_format(properties)

        return self._cache[cache_key]


def _is_scalar_cell(value: object) -> bool:
    return value is None or isinstance(value, (str, int, float, bool, np.generic, pd.Timestamp))


def _display_cell(value: object) -> object:
    if isinstance(value, (list, tuple)):
        if all(_is_scalar_cell(item) for item in value):
            return ", ".join(str(item) for item in value)
        return json.dumps(list(value), indent=2, default=str)
    if isinstance(value, dict):
        return json.dumps(value, indent=2, default=str)
    return value


def to_display_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``df`` that is safe for tabular rendering (xlsx, CSV, HTML, Markdown).

    List-of-scalar cells become ``", "``-joined strings; other dict/list cells become
    indented JSON text. Other cells are untouched. The input is never mutated, and
    JSON output must not use this helper.
    """
    out = df.copy()
    for col in out.columns:
        series = out[col]
        if series.dtype != object:
            continue
        if series.map(lambda v: isinstance(v, (list, tuple, dict))).any():
            out[col] = series.map(_display_cell)
    return out


def apply_excel_formatting(
    writer,
    df,
    sheet_name,
    logger: logging.Logger,
    format_cache: ExcelFormatCache | None = None,
):
    """Apply formatting to Excel sheets with error handling.

    Args:
        writer: pandas ExcelWriter object
        df: DataFrame to format
        sheet_name: Name of the sheet
        logger: Logger instance
        format_cache: Optional ExcelFormatCache for format reuse across sheets
    """
    try:
        logger.info("Formatting sheet: %s", sheet_name)
        df = to_display_frame(df)

        # Calculate row offset for Data Quality sheet (summary section at top)
        summary_rows = 0
        if sheet_name == "Data Quality" and "Severity" in df.columns:
            summary_rows = 7  # Title + header + 5 severity levels + blank row

        # Reorder columns for component sheets (name first for readability)
        if sheet_name in ("Metrics", "Dimensions", "Derived Fields", "Calculated Metrics") and "name" in df.columns:
            preferred_order = ["name", "type", "id", "description", "title"]
            existing_cols = [col for col in preferred_order if col in df.columns]
            other_cols = [col for col in df.columns if col not in preferred_order]
            df = df[existing_cols + other_cols]

        # Write dataframe to sheet with offset for summary
        df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=summary_rows)

        workbook = writer.book
        worksheet = writer.sheets[sheet_name]

        # Use format cache if provided, otherwise create formats directly
        # Format cache improves performance by 15-25% when formatting multiple sheets
        cache = format_cache or ExcelFormatCache(workbook)

        # Add summary section for Data Quality sheet
        if sheet_name == "Data Quality" and "Severity" in df.columns:
            # Calculate severity counts
            severity_counts = df["Severity"].value_counts()

            # Summary formats (using cache for reuse)
            title_format = cache.get_format({"bold": True, "font_size": 14, "font_color": "#366092", "bottom": 2})
            summary_header = cache.get_format({"bold": True, "bg_color": "#D9E1F2", "border": 1, "align": "center"})
            summary_cell = cache.get_format({"border": 1, "align": "center"})

            # Write summary title
            worksheet.write(0, 0, "Issue Summary", title_format)
            worksheet.merge_range(0, 0, 0, 1, "Issue Summary", title_format)

            # Write summary headers
            worksheet.write(1, 0, "Severity", summary_header)
            worksheet.write(1, 1, "Count", summary_header)

            # Write severity counts in order
            row = 2
            total_count = 0
            for sev in DataQualityChecker.SEVERITY_ORDER:
                count = severity_counts.get(sev, 0)
                if count > 0 or sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:  # Always show main levels
                    worksheet.write(row, 0, sev, summary_cell)
                    worksheet.write(row, 1, int(count), summary_cell)
                    total_count += count
                    row += 1

            # Set column widths for summary
            worksheet.set_column(0, 0, 12)
            worksheet.set_column(1, 1, 8)

        # Common format definitions (cached for reuse across sheets)
        header_format = cache.get_format(
            {
                "bold": True,
                "bg_color": "#366092",
                "font_color": "white",
                "border": 1,
                "align": "center",
                "text_wrap": True,
            },
        )

        grey_format = cache.get_format(
            {"bg_color": "#F2F2F2", "border": 1, "text_wrap": True, "align": "top", "valign": "top"},
        )

        white_format = cache.get_format(
            {"bg_color": "#FFFFFF", "border": 1, "text_wrap": True, "align": "top", "valign": "top"},
        )

        # Bold formats for Name column in Metrics/Dimensions sheets
        name_bold_grey = cache.get_format(
            {"bg_color": "#F2F2F2", "border": 1, "text_wrap": True, "align": "top", "valign": "top", "bold": True},
        )

        name_bold_white = cache.get_format(
            {"bg_color": "#FFFFFF", "border": 1, "text_wrap": True, "align": "top", "valign": "top", "bold": True},
        )

        # Special formats for Data Quality sheet
        if sheet_name == "Data Quality":
            # Severity icons for visual indicators (Excel only)
            severity_icons = {
                "CRITICAL": "\u25cf",  # filled circle
                "HIGH": "\u25b2",  # triangle up
                "MEDIUM": "\u25a0",  # filled square
                "LOW": "\u25cb",  # empty circle
                "INFO": "\u2139",  # info symbol
            }

            # Row formats (for non-severity columns) - using cache
            critical_format = cache.get_format(
                {
                    "bg_color": "#FFC7CE",
                    "font_color": "#9C0006",
                    "border": 1,
                    "text_wrap": True,
                    "align": "top",
                    "valign": "top",
                },
            )

            high_format = cache.get_format(
                {
                    "bg_color": "#FFEB9C",
                    "font_color": "#9C6500",
                    "border": 1,
                    "text_wrap": True,
                    "align": "top",
                    "valign": "top",
                },
            )

            medium_format = cache.get_format(
                {
                    "bg_color": "#C6EFCE",
                    "font_color": "#006100",
                    "border": 1,
                    "text_wrap": True,
                    "align": "top",
                    "valign": "top",
                },
            )

            low_format = cache.get_format(
                {
                    "bg_color": "#DDEBF7",
                    "font_color": "#1F4E78",
                    "border": 1,
                    "text_wrap": True,
                    "align": "top",
                    "valign": "top",
                },
            )

            info_format = cache.get_format(
                {
                    "bg_color": "#E2EFDA",
                    "font_color": "#375623",
                    "border": 1,
                    "text_wrap": True,
                    "align": "top",
                    "valign": "top",
                },
            )

            # Bold formats for Severity column (emphasize priority) - using cache
            critical_bold = cache.get_format(
                {
                    "bg_color": "#FFC7CE",
                    "font_color": "#9C0006",
                    "bold": True,
                    "border": 1,
                    "align": "center",
                    "valign": "vcenter",
                },
            )

            high_bold = cache.get_format(
                {
                    "bg_color": "#FFEB9C",
                    "font_color": "#9C6500",
                    "bold": True,
                    "border": 1,
                    "align": "center",
                    "valign": "vcenter",
                },
            )

            medium_bold = cache.get_format(
                {
                    "bg_color": "#C6EFCE",
                    "font_color": "#006100",
                    "bold": True,
                    "border": 1,
                    "align": "center",
                    "valign": "vcenter",
                },
            )

            low_bold = cache.get_format(
                {
                    "bg_color": "#DDEBF7",
                    "font_color": "#1F4E78",
                    "bold": True,
                    "border": 1,
                    "align": "center",
                    "valign": "vcenter",
                },
            )

            info_bold = cache.get_format(
                {
                    "bg_color": "#E2EFDA",
                    "font_color": "#375623",
                    "bold": True,
                    "border": 1,
                    "align": "center",
                    "valign": "vcenter",
                },
            )

            # Map severity to formats
            severity_formats = {
                "CRITICAL": (critical_format, critical_bold),
                "HIGH": (high_format, high_bold),
                "MEDIUM": (medium_format, medium_bold),
                "LOW": (low_format, low_bold),
                "INFO": (info_format, info_bold),
            }

        # Format header row (offset by summary rows if present)
        header_row = summary_rows
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(header_row, col_num, value, header_format)

        # Column width caps - tighter limits for Metrics/Dimensions sheets
        if sheet_name in ("Metrics", "Dimensions"):
            # Specific column width limits for better readability
            column_width_caps = {
                "name": 40,
                "type": 20,
                "id": 35,
                "title": 40,
                "description": 55,  # Narrower than default, relies on text wrap
            }
            default_cap = 50  # Narrower default for other columns
        else:
            column_width_caps = {}
            default_cap = 100

        # String form of the frame computed once and reused for column widths,
        # row heights, and Severity values below (avoids re-converting per column/row).
        # Use pandas' nullable string dtype so missing values become empty
        # strings instead of floating NaN values that reject the .str accessor.
        df_str = df.astype("string").fillna("")

        # Set column widths with appropriate caps (vectorized)
        for idx, col in enumerate(df.columns):
            col_lower = col.lower()
            max_cap = column_width_caps.get(col_lower, default_cap)
            if len(df) > 0:
                # Only the first line matters for width; n=1 avoids splitting
                # the remainder of multi-line cells.
                content_max = int(df_str[col].str.split("\n", n=1).str[0].str.len().max())
            else:
                content_max = 0
            max_len = min(max(content_max, len(str(col))) + 2, max_cap)
            worksheet.set_column(idx, idx, max_len)

        # Apply row formatting (offset by summary rows)
        data_start_row = summary_rows + 1  # +1 for header row

        # Cache column indices outside the loop for performance (avoids repeated hash lookups)
        severity_col_idx = df.columns.get_loc("Severity") if "Severity" in df.columns else -1
        name_col_idx = df.columns.get_loc("name") if "name" in df.columns else -1
        is_data_quality_sheet = sheet_name == "Data Quality" and severity_col_idx >= 0
        is_component_sheet = sheet_name in ("Metrics", "Dimensions") and name_col_idx >= 0

        # Row line counts computed once (vectorized) instead of per-row string scans
        if len(df) > 0:
            row_line_counts = df_str.apply(lambda s: s.str.count("\n")).max(axis=1).astype(int).tolist()
        else:
            row_line_counts = []
        severity_values = df_str["Severity"].tolist() if is_data_quality_sheet else None
        # name_values comes from the original df (not df_str) since xlsxwriter writes
        # row_data["name"] verbatim, which may be a non-str object.
        name_values = df["name"].tolist() if is_component_sheet else None

        for idx in range(len(df)):
            max_lines = row_line_counts[idx] + 1
            row_height = min(max_lines * 15, 400)
            excel_row = data_start_row + idx

            # Apply severity-based formatting for Data Quality sheet
            if is_data_quality_sheet:
                severity = severity_values[idx]
                row_format, bold_format = severity_formats.get(severity, (low_format, low_bold))

                # Set row height and default format
                worksheet.set_row(excel_row, row_height, row_format)

                # Write Severity column with icon and bold format
                icon = severity_icons.get(severity, "")
                worksheet.write(excel_row, severity_col_idx, f"{icon} {severity}", bold_format)
            else:
                row_format = grey_format if idx % 2 == 0 else white_format
                worksheet.set_row(excel_row, row_height, row_format)

                # Apply bold Name column for Metrics/Dimensions sheets
                if is_component_sheet:
                    name_format = name_bold_grey if idx % 2 == 0 else name_bold_white
                    name_value = name_values[idx]
                    if pd.isna(name_value):
                        worksheet.write_blank(excel_row, name_col_idx, None, name_format)
                    else:
                        worksheet.write(excel_row, name_col_idx, name_value, name_format)

        # Add autofilter to data table (offset by summary rows)
        worksheet.autofilter(summary_rows, 0, summary_rows + len(df), len(df.columns) - 1)

        # Freeze header row (summary + data header visible when scrolling)
        worksheet.freeze_panes(summary_rows + 1, 0)

        logger.info("Successfully formatted sheet: %s", sheet_name)

    except (OutputError, OSError, KeyError, TypeError, ValueError) as e:
        logger.error(_format_error_msg(f"formatting sheet {sheet_name}", error=e))
        raise


# ==================== OUTPUT FORMAT WRITERS ====================


def empty_section_note(sheet_name: str, section_labels: Mapping[str, str]) -> str:
    """Text shown for an empty section: its coverage state when known, else generic."""
    return section_labels.get(sheet_name) or f"No data available for {sheet_name}"


def empty_section_placeholder(sheet_name: str, section_labels: Mapping[str, str]) -> pd.DataFrame:
    """One-cell placeholder frame for an empty Excel sheet."""
    return pd.DataFrame({"Note": [empty_section_note(sheet_name, section_labels)]})


def write_excel_output(
    data_dict: dict[str, pd.DataFrame],
    base_filename: str,
    output_dir: str | Path,
    logger: logging.Logger,
) -> str:
    """
    Write data to a formatted Excel workbook.

    Args:
        data_dict: Dictionary mapping sheet names to DataFrames
        base_filename: Base filename without extension
        output_dir: Output directory path
        logger: Logger instance

    Returns:
        Path to Excel output file
    """
    try:
        logger.info("Generating Excel output...")

        excel_file = os.path.join(output_dir, f"{base_filename}.xlsx")
        section_labels = coverage_section_labels(data_dict)
        with staged_excel_writer(excel_file) as writer:
            format_cache = ExcelFormatCache(writer.book)
            for sheet_name, df in data_dict.items():
                if df.empty:
                    placeholder_df = empty_section_placeholder(sheet_name, section_labels)
                    apply_excel_formatting(writer, placeholder_df, sheet_name, logger, format_cache)
                else:
                    apply_excel_formatting(writer, df, sheet_name, logger, format_cache)

        logger.info("Excel file created: %s", excel_file)
        return excel_file

    except PermissionError as e:
        logger.error("Permission denied creating Excel file: %s", e)
        logger.error("Check write permissions for the output directory")
        raise
    except OSError as e:
        logger.error("OS error creating Excel file: %s", e)
        logger.error("Check disk space and path validity")
        raise
    except (KeyError, TypeError, ValueError) as e:
        logger.error(_format_error_msg("creating Excel file", error=e))
        raise


def write_csv_output(
    data_dict: dict[str, pd.DataFrame],
    base_filename: str,
    output_dir: str | Path,
    logger: logging.Logger,
) -> str:
    """
    Write data to CSV files (one per sheet)

    Args:
        data_dict: Dictionary mapping sheet names to DataFrames
        base_filename: Base filename without extension
        output_dir: Output directory path
        logger: Logger instance

    Returns:
        Path to output directory containing CSV files
    """
    try:
        logger.info("Generating CSV output...")

        csv_dir = os.path.join(output_dir, f"{base_filename}_csv")

        # Stage every section, then publish members and the completion manifest together
        display_frames = {sheet_name: to_display_frame(sheet_df) for sheet_name, sheet_df in data_dict.items()}
        publish_csv_bundle(display_frames, csv_dir)
        for sheet_name in display_frames:
            logger.info("  \u2713 Created CSV: %s", csv_member_name(sheet_name))

        logger.info("CSV files created in: %s", csv_dir)
        return csv_dir

    except PermissionError as e:
        logger.error("Permission denied creating CSV files: %s", e)
        logger.error("Check write permissions for the output directory")
        raise
    except OSError as e:
        logger.error("OS error creating CSV files: %s", e)
        logger.error("Check disk space and path validity")
        raise
    except (KeyError, TypeError, ValueError) as e:
        logger.error(_format_error_msg("creating CSV files", error=e))
        raise


TYPED_SDR_SCHEMA_VERSION: Final = "cja-auto-sdr.sdr-typed/1"

# Sheets whose JSON section is identical in the legacy and typed payloads.
_INVENTORY_SECTIONS: Final = {
    "Derived Fields": ("derived_fields", "derived", "fields"),
    "Calculated Metrics": ("calculated_metrics", "calculated", "metrics"),
    "Segments": ("segments", "segments", "segments"),
}


def _empty_json_payload(metadata_dict: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "metadata": metadata_dict,
        "data_view": {},
        "metrics": [],
        "dimensions": [],
        "data_quality": [],
        "derived_fields": {},
        "calculated_metrics": {},
        "segments": {},
    }


def _frame_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    """Convert a frame to records, normalizing pandas missing scalars to ``None``.

    Pandas 3 preserves nullable string columns as NaN in ``to_dict()``, which
    would otherwise leak non-standard NaN values into JSON.
    """
    return df.astype(object).where(df.notna(), None).to_dict(orient="records")


def _shared_json_section(
    sheet_name: str,
    records: list[dict[str, Any]],
    inventory_objects: Mapping[str, Any],
) -> tuple[str, Any] | None:
    """Return ``(section, value)`` for sheets that legacy and typed SDR JSON build the same way.

    These are ``data_quality`` and the three inventory sections. Inventory
    sections use the inventory object's ``to_json()`` for detailed output when
    one is available, and the sheet records otherwise. Other sheets return ``None``.
    """
    if sheet_name == "Data Quality":
        return "data_quality", records
    if sheet_name in _INVENTORY_SECTIONS:
        section, inventory_key, records_key = _INVENTORY_SECTIONS[sheet_name]
        inventory = inventory_objects.get(inventory_key)
        return section, inventory.to_json() if inventory else {records_key: records}
    return None


def _add_coverage_sections(json_data: dict[str, Any], coverage: SdrCoverage | None) -> None:
    """Append the additive ``collected_components`` and ``coverage`` keys when known."""
    if coverage is None:
        return
    json_data["collected_components"] = list(coverage.collected_components)
    json_data["coverage"] = coverage.to_json()


def build_json_payload(
    data_dict: dict[str, pd.DataFrame],
    metadata_dict: dict[str, Any],
    inventory_objects: dict[str, Any] | None = None,
    coverage: SdrCoverage | None = None,
) -> dict[str, Any]:
    """Build the hierarchical JSON payload for SDR output.

    Shared by :func:`write_json_output` (file output) and stdout streaming so
    both paths serialize identical structures.

    Args:
        data_dict: Dictionary mapping sheet names to DataFrames
        metadata_dict: Metadata information
        inventory_objects: Optional dict with 'derived'/'calculated'/'segments'
            inventory objects for detailed output using ``to_json()``
        coverage: Optional run coverage; adds ``collected_components`` and
            ``coverage``. An excluded family keeps its key as an empty list,
            so ``collected_components`` tells excluded apart from empty.

    Returns:
        JSON-serializable dictionary
    """
    json_data = _empty_json_payload(metadata_dict)
    inventory_objects = inventory_objects or {}

    for sheet_name, df in data_dict.items():
        records = _frame_records(df)
        shared = _shared_json_section(sheet_name, records, inventory_objects)
        if shared is not None:
            json_data[shared[0]] = shared[1]
        elif sheet_name == "Metrics":
            json_data["metrics"] = records
        elif sheet_name == "Dimensions":
            json_data["dimensions"] = records
        elif sheet_name == "DataView Details":
            # For single-record sheets, store as object not array
            json_data["data_view"] = records[0] if records else {}

    _add_coverage_sections(json_data, coverage)
    return json_data


def to_native_json(value: Any) -> Any:
    """Recursively convert a value into strict, native JSON-compatible Python data.

    * ``None``, ``pd.NA``, ``pd.NaT``, NaN, and infinite floats become ``None``.
    * numpy scalars become their Python equivalents (``.item()``); numpy arrays become lists.
    * dict keys are kept and values converted; lists and tuples become lists.
    * timestamps become ISO 8601 strings.
    * strings are returned unchanged and are never parsed.
    """
    if value is None or value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, Mapping):
        return {key: to_native_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [to_native_json(item) for item in value]
    if isinstance(value, np.ndarray):
        return [to_native_json(item) for item in value.tolist()]
    if isinstance(value, np.datetime64):
        return None if np.isnat(value) else pd.Timestamp(value).isoformat()
    if isinstance(value, np.generic):
        return to_native_json(value.item())
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _native_frame_records(df: pd.DataFrame | None) -> list[Any]:
    if df is None or df.empty:
        return []
    return to_native_json(df.to_dict(orient="records"))


def build_typed_json_payload(
    *,
    data_dict: Mapping[str, pd.DataFrame],
    native_frames: Mapping[str, pd.DataFrame],
    data_view: Mapping[str, Any],
    metadata_dict: Mapping[str, Any],
    inventory_objects: Mapping[str, Any] | None = None,
    coverage: SdrCoverage | None = None,
) -> dict[str, Any]:
    """Build the versioned typed SDR JSON payload (``--json-typed``).

    The payload has the same top-level keys as :func:`build_json_payload`, with
    ``schema_version`` first. A section is filled only when the legacy builder
    would fill it (its sheet is present in ``data_dict``), but its values come
    from native sources:

    * ``data_view`` is the whole raw data view lookup, not a first-row expansion.
    * ``metrics`` and ``dimensions`` come from ``native_frames`` captured before
      display formatting, so nested objects, lists, booleans, and numbers stay native.
    * ``metadata``, ``data_quality``, and the inventory sections are built the
      same way as the legacy payload.

    The result passes through :func:`to_native_json`, so it is strict JSON.
    """
    json_data = _empty_json_payload(metadata_dict)

    if "DataView Details" in data_dict:
        json_data["data_view"] = dict(data_view or {})
    if "Metrics" in data_dict:
        json_data["metrics"] = _native_frame_records(native_frames.get("Metrics"))
    if "Dimensions" in data_dict:
        json_data["dimensions"] = _native_frame_records(native_frames.get("Dimensions"))

    inventory_objects = inventory_objects or {}
    for sheet_name, df in data_dict.items():
        if sheet_name == "Data Quality" or sheet_name in _INVENTORY_SECTIONS:
            section, value = _shared_json_section(sheet_name, _frame_records(df), inventory_objects)
            json_data[section] = value

    _add_coverage_sections(json_data, coverage)
    return {"schema_version": TYPED_SDR_SCHEMA_VERSION, **to_native_json(json_data)}


def _log_json_write_error(logger: logging.Logger, error: BaseException) -> None:
    if isinstance(error, PermissionError):
        logger.error("Permission denied creating JSON file: %s", error)
        logger.error("Check write permissions for the output directory")
    elif isinstance(error, OSError):
        logger.error("OS error creating JSON file: %s", error)
        logger.error("Check disk space and path validity")
    elif isinstance(error, (TypeError, ValueError)):
        logger.error("JSON serialization error: %s", error)
        logger.error("Data contains non-serializable values")
    else:
        logger.error(_format_error_msg("creating JSON file", error=error))


def write_json_output(
    data_dict: dict[str, pd.DataFrame],
    metadata_dict: dict[str, Any],
    base_filename: str,
    output_dir: str | Path,
    logger: logging.Logger,
    inventory_objects: dict[str, Any] | None = None,
    output_path: str | None = None,
    coverage: SdrCoverage | None = None,
) -> str:
    """
    Write data to JSON format with hierarchical structure

    Args:
        data_dict: Dictionary mapping sheet names to DataFrames
        metadata_dict: Metadata information
        base_filename: Base filename without extension
        output_dir: Output directory path
        logger: Logger instance
        inventory_objects: Optional dict with 'derived' and 'calculated' inventory objects
                          for detailed JSON output using to_json()

    Returns:
        Path to JSON output file
    """
    try:
        logger.info("Generating JSON output...")

        json_data = build_json_payload(data_dict, metadata_dict, inventory_objects, coverage=coverage)

        # Write JSON file
        json_file = str(output_path) if output_path else os.path.join(output_dir, f"{base_filename}.json")
        write_json_atomic_compatible(json_file, json_data, indent=2, ensure_ascii=False, trailing_newline=False)

        logger.info("\u2713 JSON file created: %s", json_file)
        return json_file

    except (PermissionError, OSError, TypeError, ValueError, KeyError, AttributeError) as e:
        _log_json_write_error(logger, e)
        raise


def serialize_typed_json(payload: Mapping[str, Any]) -> str:
    """Serialize a typed SDR payload as strict JSON (NaN and infinity are rejected)."""
    return json.dumps(payload, indent=2, ensure_ascii=False, allow_nan=False)


def write_typed_json_output(
    payload: Mapping[str, Any],
    base_filename: str,
    output_dir: str | Path,
    logger: logging.Logger,
    output_path: str | None = None,
) -> str:
    """Write a payload from :func:`build_typed_json_payload` to a JSON file.

    The text is serialized with ``allow_nan=False`` before anything is written,
    so a non-strict payload raises ``ValueError`` and leaves no file behind.
    """
    try:
        logger.info("Generating typed JSON output...")
        text = serialize_typed_json(payload)
        json_file = str(output_path) if output_path else os.path.join(output_dir, f"{base_filename}.json")
        write_text_atomic_compatible(json_file, text)
        logger.info("\u2713 Typed JSON file created: %s", json_file)
        return json_file
    except (PermissionError, OSError, TypeError, ValueError) as e:
        _log_json_write_error(logger, e)
        raise


def write_html_output(
    data_dict: dict[str, pd.DataFrame],
    metadata_dict: dict[str, Any],
    base_filename: str,
    output_dir: str | Path,
    logger: logging.Logger,
    output_path: str | None = None,
) -> str:
    """
    Write data to HTML format with professional styling

    Args:
        data_dict: Dictionary mapping sheet names to DataFrames
        metadata_dict: Metadata information
        base_filename: Base filename without extension
        output_dir: Output directory path
        logger: Logger instance

    Returns:
        Path to HTML output file
    """
    try:
        logger.info("Generating HTML output...")

        # Build HTML content
        html_parts = []

        # HTML header with CSS
        html_parts.append("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CJA Solution Design Reference</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            color: #333;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
            border-radius: 8px;
        }
        h1 {
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
            margin-bottom: 30px;
        }
        h2 {
            color: #34495e;
            margin-top: 40px;
            margin-bottom: 20px;
            border-left: 4px solid #3498db;
            padding-left: 15px;
        }
        .metadata {
            background-color: #ecf0f1;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 30px;
        }
        .metadata-item {
            margin: 8px 0;
            display: flex;
            align-items: baseline;
        }
        .metadata-label {
            font-weight: bold;
            min-width: 200px;
            color: #2c3e50;
        }
        .metadata-value {
            color: #555;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 14px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        thead {
            background-color: #3498db;
            color: white;
        }
        th {
            padding: 12px;
            text-align: left;
            font-weight: 600;
            position: sticky;
            top: 0;
        }
        td {
            padding: 10px 12px;
            border-bottom: 1px solid #ddd;
        }
        tbody tr:nth-child(even) {
            background-color: #f8f9fa;
        }
        tbody tr:hover {
            background-color: #e8f4f8;
        }
        .severity-CRITICAL {
            background-color: #e74c3c !important;
            color: white;
            font-weight: bold;
        }
        .severity-HIGH {
            background-color: #e67e22 !important;
            color: white;
        }
        .severity-MEDIUM {
            background-color: #f39c12 !important;
            color: white;
        }
        .severity-LOW {
            background-color: #95a5a6 !important;
            color: white;
        }
        .severity-INFO {
            background-color: #3498db !important;
            color: white;
        }
        .section {
            margin-bottom: 50px;
        }
        .footer {
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            text-align: center;
            color: #7f8c8d;
            font-size: 12px;
        }
        @media print {
            body {
                background-color: white;
            }
            .container {
                box-shadow: none;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>\U0001f4ca CJA Solution Design Reference</h1>
        """)

        # Metadata section
        html_parts.append('<div class="metadata">')
        html_parts.append("<h2>\U0001f4cb Metadata</h2>")
        for key, value in metadata_dict.items():
            safe_value = html.escape(str(value))
            html_parts.append(f"""
            <div class="metadata-item">
                <span class="metadata-label">{key}:</span>
                <span class="metadata-value">{safe_value}</span>
            </div>
            """)
        html_parts.append("</div>")

        # Data sections
        section_icons = {
            "Coverage": "\U0001f9ed",
            "Data Quality": "\U0001f50d",
            "DataView Details": "\U0001f4ca",
            "Metrics": "\U0001f4c8",
            "Dimensions": "\U0001f4d0",
            "Derived Fields": "\U0001f527",
            "Calculated Metrics": "\U0001f9ee",
            "Segments": "\U0001f3af",
        }

        section_labels = coverage_section_labels(data_dict)
        for sheet_name, sheet_df in data_dict.items():
            icon = section_icons.get(sheet_name, "\U0001f4c4")
            if sheet_df.empty:
                # Keep empty sections visible, labelled with their coverage state.
                note = html.escape(empty_section_note(sheet_name, section_labels))
                html_parts.append('<div class="section">')
                html_parts.append(f"<h2>{icon} {html.escape(sheet_name)}</h2>")
                html_parts.append(f'<p class="section-state"><em>{note}</em></p>')
                html_parts.append("</div>")
                continue
            df = to_display_frame(sheet_df)

            html_parts.append('<div class="section">')
            html_parts.append(f"<h2>{icon} {html.escape(sheet_name)}</h2>")

            # Convert DataFrame to HTML with custom styling
            df_html = df.to_html(index=False, escape=True, classes="data-table")

            # Add severity-based row classes for Data Quality sheet
            if sheet_name == "Data Quality" and "Severity" in df.columns:
                valid_severities = {"CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"}
                # Convert through pandas StringDtype first so categorical Severity columns
                # can be normalized without fillna() category-assignment errors.
                severities = df["Severity"].astype("string").fillna("").str.upper().tolist()

                # Apply classes only to tbody rows so header <tr ...> formatting does not shift alignment.
                tbody_match = re.search(r"(<tbody>)(.*?)(</tbody>)", df_html, flags=re.DOTALL)
                if tbody_match:
                    row_idx = 0

                    def _add_severity_class(
                        match: re.Match[str],
                        _severities: list[str] = severities,
                        _valid_severities: set[str] = valid_severities,
                    ) -> str:
                        nonlocal row_idx
                        row_open = match.group(0)
                        if row_idx >= len(_severities):
                            return row_open

                        severity = _severities[row_idx]
                        row_idx += 1
                        if severity not in _valid_severities:
                            return row_open

                        if 'class="' in row_open:
                            return re.sub(
                                r'class="([^"]*)"',
                                f'class="\\1 severity-{severity}"',
                                row_open,
                                count=1,
                            )
                        return row_open.replace("<tr", f'<tr class="severity-{severity}"', 1)

                    styled_tbody = re.sub(r"<tr(?:\s[^>]*)?>", _add_severity_class, tbody_match.group(2))
                    df_html = df_html[: tbody_match.start(2)] + styled_tbody + df_html[tbody_match.end(2) :]

            html_parts.append(df_html)
            html_parts.append("</div>")

        # Footer
        html_parts.append(f"""
        <div class="footer">
            <p>Generated by CJA SDR Generator v{__version__}</p>
            <p>Generated at {html.escape(str(metadata_dict.get("Generated At", "N/A")))}</p>
        </div>
    </div>
</body>
</html>
        """)

        # Write HTML file
        html_file = str(output_path) if output_path else os.path.join(output_dir, f"{base_filename}.html")
        write_text_atomic_compatible(html_file, "\n".join(html_parts))

        logger.info("\u2713 HTML file created: %s", html_file)
        return html_file

    except PermissionError as e:
        logger.error("Permission denied creating HTML file: %s", e)
        logger.error("Check write permissions for the output directory")
        raise
    except OSError as e:
        logger.error("OS error creating HTML file: %s", e)
        logger.error("Check disk space and path validity")
        raise
    except (KeyError, TypeError, ValueError) as e:
        logger.error(_format_error_msg("creating HTML file", error=e))
        raise


def escape_markdown(text: Any) -> str:
    """Escape special markdown characters in table cells"""
    if text is None:
        return ""
    try:
        if pd.isna(text):
            return ""
    except (TypeError, ValueError):
        # pd.isna returns an array for list-like input; truth-testing it raises.
        pass
    text = str(text)
    # Escape backslashes first so a literal backslash before a pipe cannot
    # swallow the pipe escape, then escape pipes that would break tables
    text = text.replace("\\", "\\\\")
    text = text.replace("|", "\\|")
    # Escape backticks
    text = text.replace("`", "\\`")
    # Replace newlines with spaces in table cells
    text = text.replace("\n", " ")
    text = text.replace("\r", " ")
    return text.strip()


def df_to_markdown_table(df: pd.DataFrame, sheet_name: str, empty_message: str | None = None) -> str:
    """Convert DataFrame to markdown table format.

    Escaping is column-vectorized via `str.replace()` rather than a per-cell
    `apply(axis=1)` call, for better performance on large DataFrames.
    """
    if df.empty:
        if empty_message:
            return f"\n*{escape_markdown(empty_message)}*\n"
        return f"\n*No {sheet_name.lower()} found.*\n"

    # Header row
    headers = [escape_markdown(col) for col in df.columns]
    header_row = "| " + " | ".join(headers) + " |"

    # Separator row with left alignment
    separator_row = "| " + " | ".join(["---"] * len(headers)) + " |"

    # Data rows - column-wise vectorized escaping instead of per-row apply()
    # `astype(object)` first: pandas nullable extension dtypes (Int64, Float64,
    # boolean, category) reject writing the "" fill value in-place via `.where()`
    # and raise TypeError, so upcast to plain object dtype before filling blanks.
    # NA sentinels (pd.NA / np.nan / NaT) survive the object cast, so `.notna()`
    # on the object-cast frame still agrees with `.notna()` on the original.
    df_obj = df.astype(object)
    df_esc = df_obj.where(df_obj.notna(), "").astype(str)
    for col in df_esc.columns:
        df_esc[col] = (
            df_esc[col]
            .str.replace("\\", "\\\\", regex=False)
            .str.replace("|", "\\|", regex=False)
            .str.replace("`", "\\`", regex=False)
            .str.replace("\n", " ", regex=False)
            .str.replace("\r", " ", regex=False)
            .str.strip()
        )
    data_rows = ["| " + " | ".join(row) + " |" for row in df_esc.itertuples(index=False)]

    return "\n".join([header_row, separator_row, *data_rows])


def write_markdown_output(
    data_dict: dict[str, pd.DataFrame],
    metadata_dict: dict[str, Any],
    base_filename: str,
    output_dir: str | Path,
    logger: logging.Logger,
    output_path: str | None = None,
) -> str:
    """
    Write data to Markdown format for GitHub, Confluence, and other platforms

    Features:
    - GitHub-flavored markdown tables
    - Table of contents with section links
    - Collapsible sections for large tables
    - Proper escaping of special characters
    - Issue summary for Data Quality

    Args:
        data_dict: Dictionary mapping sheet names to DataFrames
        metadata_dict: Metadata information
        base_filename: Base filename without extension
        output_dir: Output directory path
        logger: Logger instance

    Returns:
        Path to Markdown output file
    """
    try:
        logger.info("Generating Markdown output...")

        md_parts = []

        # Title
        md_parts.append("# \U0001f4ca CJA Solution Design Reference\n")

        # Metadata section
        md_parts.append("## \U0001f4cb Metadata\n")
        if metadata_dict:
            for key, value in metadata_dict.items():
                md_parts.append(f"**{key}:** {escape_markdown(str(value))}")
            md_parts.append("")

        # Table of contents
        md_parts.append("## \U0001f4d1 Table of Contents\n")
        toc_items = []
        for sheet_name in data_dict:
            # Create anchor-safe links
            anchor = sheet_name.lower().replace(" ", "-").replace("_", "-")
            toc_items.append(f"- [{sheet_name}](#{anchor})")
        md_parts.append("\n".join(toc_items))
        md_parts.append("\n---\n")

        # Process each sheet
        section_labels = coverage_section_labels(data_dict)
        for sheet_name, sheet_df in data_dict.items():
            df = to_display_frame(sheet_df)
            md_parts.append(f"## {sheet_name}\n")

            # Add special handling for Data Quality sheet
            if sheet_name == "Data Quality" and not df.empty and "Severity" in df.columns:
                # Add issue summary
                severity_counts = df["Severity"].value_counts()
                md_parts.append("### Issue Summary\n")
                md_parts.append("| Severity | Count |")
                md_parts.append("| --- | --- |")

                severity_emojis = {
                    "CRITICAL": "\U0001f534",
                    "HIGH": "\U0001f7e0",
                    "MEDIUM": "\U0001f7e1",
                    "LOW": "\u26aa",
                    "INFO": "\U0001f535",
                }
                for sev in DataQualityChecker.SEVERITY_ORDER:
                    count = severity_counts.get(sev, 0)
                    if count > 0 or sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW"]:
                        emoji = severity_emojis.get(sev, "")
                        md_parts.append(f"| {emoji} {sev} | {count} |")
                md_parts.append("")

            # For large tables (>50 rows), use collapsible sections
            if len(df) > 50:
                md_parts.append("<details>")
                md_parts.append(f"<summary>View {len(df)} rows (click to expand)</summary>\n")
                md_parts.append(df_to_markdown_table(df, sheet_name))
                md_parts.append("\n</details>\n")
            else:
                # For smaller tables, show directly
                md_parts.append(df_to_markdown_table(df, sheet_name, section_labels.get(sheet_name)))
                md_parts.append("")

            # Add counts
            md_parts.append(f"*Total {sheet_name}: {len(df)} items*\n")
            md_parts.append("---\n")

        # Footer
        md_parts.append("---")
        md_parts.append("*Generated by CJA Auto SDR Generator*")

        # Write to file
        markdown_file = str(output_path) if output_path else os.path.join(output_dir, f"{base_filename}.md")
        write_text_atomic_compatible(markdown_file, "\n".join(md_parts))

        logger.info("\u2713 Markdown file created: %s", markdown_file)
        return markdown_file

    except PermissionError as e:
        logger.error("Permission denied creating Markdown file: %s", e)
        logger.error("Check write permissions for the output directory")
        raise
    except OSError as e:
        logger.error("OS error creating Markdown file: %s", e)
        logger.error("Check disk space and path validity")
        raise
    except (KeyError, TypeError, ValueError) as e:
        logger.error(_format_error_msg("creating Markdown file", error=e))
        raise
