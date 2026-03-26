"""Excel diff file output writer.

Extracted from generator.py. Provides:
- write_diff_excel_output: Write diff comparison to Excel format with color-coded rows
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import pandas as pd

from cja_auto_sdr.core.colors import _format_error_msg
from cja_auto_sdr.diff.models import (
    ChangeType,
    ComponentDiff,
    DiffResult,
    InventoryItemDiff,
)
from cja_auto_sdr.output.diff.common import (
    _get_change_detail,
    _get_inventory_change_detail,
)

__all__ = [
    "write_diff_excel_output",
]


def write_diff_excel_output(
    diff_result: DiffResult,
    base_filename: str,
    output_dir: str | Path,
    logger: logging.Logger,
    changes_only: bool = False,
) -> str:
    """
    Write diff comparison to Excel format with color-coded rows.

    Args:
        diff_result: The DiffResult to output
        base_filename: Base filename without extension
        output_dir: Output directory path
        logger: Logger instance
        changes_only: Only include changed items

    Returns:
        Path to Excel output file
    """
    try:
        logger.info("Generating diff Excel output...")

        summary = diff_result.summary
        meta = diff_result.metadata_diff
        excel_file = os.path.join(output_dir, f"{base_filename}.xlsx")

        with pd.ExcelWriter(excel_file, engine="xlsxwriter") as writer:
            workbook = writer.book

            # Define formats
            added_format = workbook.add_format({"bg_color": "#d4edda", "border": 1})
            removed_format = workbook.add_format({"bg_color": "#f8d7da", "border": 1})
            modified_format = workbook.add_format({"bg_color": "#fff3cd", "border": 1})
            normal_format = workbook.add_format({"border": 1})

            # Summary sheet - build rows dynamically
            summary_rows = [
                {
                    "Component": "Metrics",
                    diff_result.source_label: summary.source_metrics_count,
                    diff_result.target_label: summary.target_metrics_count,
                    "Added": summary.metrics_added,
                    "Removed": summary.metrics_removed,
                    "Modified": summary.metrics_modified,
                    "Unchanged": summary.metrics_unchanged,
                    "Changed %": f"{summary.metrics_change_percent:.1f}%",
                },
                {
                    "Component": "Dimensions",
                    diff_result.source_label: summary.source_dimensions_count,
                    diff_result.target_label: summary.target_dimensions_count,
                    "Added": summary.dimensions_added,
                    "Removed": summary.dimensions_removed,
                    "Modified": summary.dimensions_modified,
                    "Unchanged": summary.dimensions_unchanged,
                    "Changed %": f"{summary.dimensions_change_percent:.1f}%",
                },
            ]

            # Add inventory rows if present (check for actual inventory diffs)
            if diff_result.calc_metrics_diffs is not None:
                summary_rows.append(
                    {
                        "Component": "Calc Metrics",
                        diff_result.source_label: summary.source_calc_metrics_count,
                        diff_result.target_label: summary.target_calc_metrics_count,
                        "Added": summary.calc_metrics_added,
                        "Removed": summary.calc_metrics_removed,
                        "Modified": summary.calc_metrics_modified,
                        "Unchanged": summary.calc_metrics_unchanged,
                        "Changed %": f"{summary.calc_metrics_change_percent:.1f}%",
                    },
                )
            if diff_result.segments_diffs is not None:
                summary_rows.append(
                    {
                        "Component": "Segments",
                        diff_result.source_label: summary.source_segments_count,
                        diff_result.target_label: summary.target_segments_count,
                        "Added": summary.segments_added,
                        "Removed": summary.segments_removed,
                        "Modified": summary.segments_modified,
                        "Unchanged": summary.segments_unchanged,
                        "Changed %": f"{summary.segments_change_percent:.1f}%",
                    },
                )

            summary_df = pd.DataFrame(summary_rows)
            summary_df.to_excel(writer, sheet_name="Summary", index=False)

            # Metadata sheet
            metadata_data = {
                "Property": [
                    "Source ID",
                    "Source Name",
                    "Target ID",
                    "Target Name",
                    "Generated At",
                    "Has Changes",
                    "Total Changes",
                ],
                "Value": [
                    meta.source_id,
                    meta.source_name,
                    meta.target_id,
                    meta.target_name,
                    diff_result.generated_at,
                    str(summary.has_changes),
                    summary.total_changes,
                ],
            }
            metadata_df = pd.DataFrame(metadata_data)
            metadata_df.to_excel(writer, sheet_name="Metadata", index=False)

            # Helper function to write diff sheet
            def write_diff_sheet(diffs: list[ComponentDiff], sheet_name: str):
                if changes_only:
                    diffs = [d for d in diffs if d.change_type != ChangeType.UNCHANGED]

                if not diffs:
                    df = pd.DataFrame({"Message": ["No changes"]})
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                    return

                rows = [
                    {
                        "Status": diff.change_type.value.upper(),
                        "ID": diff.id,
                        "Name": diff.name,
                        "Details": _get_change_detail(diff),
                    }
                    for diff in diffs
                ]

                df = pd.DataFrame(rows)
                df.to_excel(writer, sheet_name=sheet_name, index=False)

                # Apply color formatting
                worksheet = writer.sheets[sheet_name]
                for row_idx, diff in enumerate(diffs, start=1):
                    if diff.change_type == ChangeType.ADDED:
                        fmt = added_format
                    elif diff.change_type == ChangeType.REMOVED:
                        fmt = removed_format
                    elif diff.change_type == ChangeType.MODIFIED:
                        fmt = modified_format
                    else:
                        fmt = normal_format

                    for col_idx in range(len(df.columns)):
                        worksheet.write(row_idx, col_idx, df.iloc[row_idx - 1, col_idx], fmt)

            write_diff_sheet(diff_result.metric_diffs, "Metrics Diff")
            write_diff_sheet(diff_result.dimension_diffs, "Dimensions Diff")

            # Helper function to write inventory diff sheet
            def write_inventory_diff_sheet(diffs: list[InventoryItemDiff] | None, sheet_name: str):
                if diffs is None:
                    return

                if changes_only:
                    diffs = [d for d in diffs if d.change_type != ChangeType.UNCHANGED]

                if not diffs:
                    df = pd.DataFrame({"Message": ["No changes"]})
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                    return

                rows = [
                    {
                        "Status": diff.change_type.value.upper(),
                        "ID": diff.id,
                        "Name": diff.name,
                        "Details": _get_inventory_change_detail(diff),
                    }
                    for diff in diffs
                ]

                df = pd.DataFrame(rows)
                df.to_excel(writer, sheet_name=sheet_name, index=False)

                # Apply color formatting
                worksheet = writer.sheets[sheet_name]
                for row_idx, diff in enumerate(diffs, start=1):
                    if diff.change_type == ChangeType.ADDED:
                        fmt = added_format
                    elif diff.change_type == ChangeType.REMOVED:
                        fmt = removed_format
                    elif diff.change_type == ChangeType.MODIFIED:
                        fmt = modified_format
                    else:
                        fmt = normal_format

                    for col_idx in range(len(df.columns)):
                        worksheet.write(row_idx, col_idx, df.iloc[row_idx - 1, col_idx], fmt)

            # Write inventory diff sheets if present
            if diff_result.calc_metrics_diffs is not None:
                write_inventory_diff_sheet(diff_result.calc_metrics_diffs, "Calc Metrics Diff")
            if diff_result.segments_diffs is not None:
                write_inventory_diff_sheet(diff_result.segments_diffs, "Segments Diff")

        logger.info(f"Diff Excel file created: {excel_file}")
        return excel_file

    except (OSError, KeyError, TypeError, ValueError) as e:
        logger.error(_format_error_msg("creating diff Excel file", error=e))
        raise
