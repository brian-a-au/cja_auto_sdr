"""JSON diff file output writer.

Extracted from generator.py. Provides:
- write_diff_json_output: Write diff comparison to JSON format
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path

from cja_auto_sdr.core.colors import _format_error_msg
from cja_auto_sdr.diff.models import (
    ChangeType,
    ComponentDiff,
    DiffResult,
    InventoryItemDiff,
)


def write_diff_json_output(
    diff_result: DiffResult,
    base_filename: str,
    output_dir: str | Path,
    logger: logging.Logger,
    changes_only: bool = False,
) -> str:
    """
    Write diff comparison to JSON format.

    Args:
        diff_result: The DiffResult to output
        base_filename: Base filename without extension
        output_dir: Output directory path
        logger: Logger instance
        changes_only: Only include changed items

    Returns:
        Path to JSON output file
    """
    try:
        logger.info("Generating diff JSON output...")

        summary = diff_result.summary
        meta = diff_result.metadata_diff

        def serialize_component_diff(d: ComponentDiff) -> dict:
            return {
                "id": d.id,
                "name": d.name,
                "change_type": d.change_type.value,
                "changed_fields": {k: {"source": v[0], "target": v[1]} for k, v in (d.changed_fields or {}).items()},
                "source_data": d.source_data,
                "target_data": d.target_data,
            }

        def serialize_inventory_diff(d: InventoryItemDiff) -> dict:
            return {
                "id": d.id,
                "name": d.name,
                "change_type": d.change_type.value,
                "inventory_type": d.inventory_type,
                "changed_fields": {k: {"source": v[0], "target": v[1]} for k, v in (d.changed_fields or {}).items()},
                "source_data": d.source_data,
                "target_data": d.target_data,
            }

        # Filter diffs if changes_only
        metric_diffs = diff_result.metric_diffs
        dimension_diffs = diff_result.dimension_diffs
        if changes_only:
            metric_diffs = [d for d in metric_diffs if d.change_type != ChangeType.UNCHANGED]
            dimension_diffs = [d for d in dimension_diffs if d.change_type != ChangeType.UNCHANGED]

        json_data = {
            "metadata": {
                "generated_at": diff_result.generated_at,
                "tool_version": diff_result.tool_version,
                "source_label": diff_result.source_label,
                "target_label": diff_result.target_label,
            },
            "source": {
                "id": meta.source_id,
                "name": meta.source_name,
                "owner": meta.source_owner,
                "description": meta.source_description,
            },
            "target": {
                "id": meta.target_id,
                "name": meta.target_name,
                "owner": meta.target_owner,
                "description": meta.target_description,
            },
            "summary": {
                "source_metrics_count": summary.source_metrics_count,
                "target_metrics_count": summary.target_metrics_count,
                "source_dimensions_count": summary.source_dimensions_count,
                "target_dimensions_count": summary.target_dimensions_count,
                "metrics_added": summary.metrics_added,
                "metrics_removed": summary.metrics_removed,
                "metrics_modified": summary.metrics_modified,
                "metrics_unchanged": summary.metrics_unchanged,
                "metrics_change_percent": summary.metrics_change_percent,
                "dimensions_added": summary.dimensions_added,
                "dimensions_removed": summary.dimensions_removed,
                "dimensions_modified": summary.dimensions_modified,
                "dimensions_unchanged": summary.dimensions_unchanged,
                "dimensions_change_percent": summary.dimensions_change_percent,
                "has_changes": summary.has_changes,
                "total_changes": summary.total_changes,
                "total_added": summary.total_added,
                "total_removed": summary.total_removed,
                "total_modified": summary.total_modified,
                "total_summary": summary.total_summary,
            },
            "metric_diffs": [serialize_component_diff(d) for d in metric_diffs],
            "dimension_diffs": [serialize_component_diff(d) for d in dimension_diffs],
        }

        # Add inventory diffs if present
        if diff_result.has_inventory_diffs:
            inventory_summary = {}
            if summary.source_calc_metrics_count > 0 or summary.target_calc_metrics_count > 0:
                inventory_summary["calculated_metrics"] = {
                    "source_count": summary.source_calc_metrics_count,
                    "target_count": summary.target_calc_metrics_count,
                    "added": summary.calc_metrics_added,
                    "removed": summary.calc_metrics_removed,
                    "modified": summary.calc_metrics_modified,
                    "unchanged": summary.calc_metrics_unchanged,
                }
            if summary.source_segments_count > 0 or summary.target_segments_count > 0:
                inventory_summary["segments"] = {
                    "source_count": summary.source_segments_count,
                    "target_count": summary.target_segments_count,
                    "added": summary.segments_added,
                    "removed": summary.segments_removed,
                    "modified": summary.segments_modified,
                    "unchanged": summary.segments_unchanged,
                }
            json_data["inventory_summary"] = inventory_summary

            if diff_result.calc_metrics_diffs is not None:
                calc_diffs = diff_result.calc_metrics_diffs
                if changes_only:
                    calc_diffs = [d for d in calc_diffs if d.change_type != ChangeType.UNCHANGED]
                json_data["calculated_metrics_diffs"] = [serialize_inventory_diff(d) for d in calc_diffs]

            if diff_result.segments_diffs is not None:
                seg_diffs = diff_result.segments_diffs
                if changes_only:
                    seg_diffs = [d for d in seg_diffs if d.change_type != ChangeType.UNCHANGED]
                json_data["segments_diffs"] = [serialize_inventory_diff(d) for d in seg_diffs]

        json_file = os.path.join(output_dir, f"{base_filename}.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Diff JSON file created: {json_file}")
        return json_file

    except (OSError, TypeError, ValueError) as e:
        logger.error(_format_error_msg("creating diff JSON file", error=e))
        raise
