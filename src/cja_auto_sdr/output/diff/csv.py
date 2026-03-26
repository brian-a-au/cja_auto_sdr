"""CSV diff file output writer.

Extracted from generator.py. Provides:
- write_diff_csv_output: Write diff comparison to CSV files
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
    "write_diff_csv_output",
]


def write_diff_csv_output(
    diff_result: DiffResult,
    base_filename: str,
    output_dir: str | Path,
    logger: logging.Logger,
    changes_only: bool = False,
) -> str:
    """
    Write diff comparison to CSV files.

    Args:
        diff_result: The DiffResult to output
        base_filename: Base filename without extension
        output_dir: Output directory path
        logger: Logger instance
        changes_only: Only include changed items

    Returns:
        Path to output directory containing CSV files
    """
    try:
        logger.info("Generating diff CSV output...")

        summary = diff_result.summary
        meta = diff_result.metadata_diff

        # Create subdirectory for CSV files
        csv_dir = os.path.join(output_dir, f"{base_filename}_csv")
        os.makedirs(csv_dir, exist_ok=True)

        # Summary CSV - build rows dynamically
        summary_rows = [
            {
                "Component": "Metrics",
                "Source_Count": summary.source_metrics_count,
                "Target_Count": summary.target_metrics_count,
                "Added": summary.metrics_added,
                "Removed": summary.metrics_removed,
                "Modified": summary.metrics_modified,
                "Unchanged": summary.metrics_unchanged,
                "Changed_Percent": summary.metrics_change_percent,
            },
            {
                "Component": "Dimensions",
                "Source_Count": summary.source_dimensions_count,
                "Target_Count": summary.target_dimensions_count,
                "Added": summary.dimensions_added,
                "Removed": summary.dimensions_removed,
                "Modified": summary.dimensions_modified,
                "Unchanged": summary.dimensions_unchanged,
                "Changed_Percent": summary.dimensions_change_percent,
            },
        ]

        # Add inventory rows if present (check for actual inventory diffs)
        if diff_result.calc_metrics_diffs is not None:
            summary_rows.append(
                {
                    "Component": "Calc_Metrics",
                    "Source_Count": summary.source_calc_metrics_count,
                    "Target_Count": summary.target_calc_metrics_count,
                    "Added": summary.calc_metrics_added,
                    "Removed": summary.calc_metrics_removed,
                    "Modified": summary.calc_metrics_modified,
                    "Unchanged": summary.calc_metrics_unchanged,
                    "Changed_Percent": summary.calc_metrics_change_percent,
                },
            )
        if diff_result.segments_diffs is not None:
            summary_rows.append(
                {
                    "Component": "Segments",
                    "Source_Count": summary.source_segments_count,
                    "Target_Count": summary.target_segments_count,
                    "Added": summary.segments_added,
                    "Removed": summary.segments_removed,
                    "Modified": summary.segments_modified,
                    "Unchanged": summary.segments_unchanged,
                    "Changed_Percent": summary.segments_change_percent,
                },
            )

        pd.DataFrame(summary_rows).to_csv(os.path.join(csv_dir, "summary.csv"), index=False, encoding="utf-8")
        logger.info("  Created: summary.csv")

        # Metadata CSV
        metadata_data = {
            "Property": [
                "source_id",
                "source_name",
                "target_id",
                "target_name",
                "generated_at",
                "has_changes",
                "total_changes",
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
        pd.DataFrame(metadata_data).to_csv(os.path.join(csv_dir, "metadata.csv"), index=False, encoding="utf-8")
        logger.info("  Created: metadata.csv")

        # Helper function to write diff CSV
        def write_diff_csv(diffs: list[ComponentDiff], filename: str):
            if changes_only:
                diffs = [d for d in diffs if d.change_type != ChangeType.UNCHANGED]

            rows = [
                {
                    "status": diff.change_type.value,
                    "id": diff.id,
                    "name": diff.name,
                    "details": _get_change_detail(diff),
                }
                for diff in diffs
            ]

            pd.DataFrame(rows).to_csv(os.path.join(csv_dir, filename), index=False, encoding="utf-8")
            logger.info(f"  Created: {filename}")

        write_diff_csv(diff_result.metric_diffs, "metrics_diff.csv")
        write_diff_csv(diff_result.dimension_diffs, "dimensions_diff.csv")

        # Helper function to write inventory diff CSV
        def write_inventory_diff_csv(diffs: list[InventoryItemDiff] | None, filename: str):
            if diffs is None:
                return

            if changes_only:
                diffs = [d for d in diffs if d.change_type != ChangeType.UNCHANGED]

            rows = [
                {
                    "status": diff.change_type.value,
                    "id": diff.id,
                    "name": diff.name,
                    "details": _get_inventory_change_detail(diff),
                }
                for diff in diffs
            ]

            pd.DataFrame(rows).to_csv(os.path.join(csv_dir, filename), index=False, encoding="utf-8")
            logger.info(f"  Created: {filename}")

        # Write inventory diff CSVs if present
        if diff_result.calc_metrics_diffs is not None:
            write_inventory_diff_csv(diff_result.calc_metrics_diffs, "calc_metrics_diff.csv")
        if diff_result.segments_diffs is not None:
            write_inventory_diff_csv(diff_result.segments_diffs, "segments_diff.csv")

        logger.info(f"Diff CSV files created in: {csv_dir}")
        return csv_dir

    except (OSError, KeyError, TypeError, ValueError) as e:
        logger.error(_format_error_msg("creating diff CSV files", error=e))
        raise
