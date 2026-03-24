"""Markdown diff file output renderer.

Extracted from generator.py. Provides:
- write_diff_markdown_output: Full markdown diff report written to file
- _format_markdown_side_by_side: Side-by-side markdown table for modified items
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from cja_auto_sdr.core.colors import _format_error_msg
from cja_auto_sdr.diff.models import ChangeType, ComponentDiff, DiffResult
from cja_auto_sdr.output.diff.common import (
    _format_diff_value,
    _get_change_detail,
    _get_change_emoji,
    _get_inventory_change_detail,
)


def _format_markdown_side_by_side(diff: ComponentDiff, source_label: str, target_label: str) -> list[str]:
    """
    Format a component diff as a side-by-side markdown table.

    Args:
        diff: The ComponentDiff to format
        source_label: Label for source side
        target_label: Label for target side

    Returns:
        List of markdown lines for the side-by-side view
    """
    lines: list[str] = []
    if diff.change_type != ChangeType.MODIFIED or not diff.changed_fields:
        return lines

    # Component header
    lines.append(f"\n**`{diff.id}`** - {diff.name}\n")

    # Side-by-side table
    lines.append(f"| Field | {source_label} | {target_label} |")
    lines.append("| --- | --- | --- |")

    for field_name, (old_val, new_val) in diff.changed_fields.items():
        old_formatted = _format_diff_value(old_val, truncate=False)
        new_formatted = _format_diff_value(new_val, truncate=False)
        # Use italic for empty values in markdown
        old_str = "*(empty)*" if old_formatted == "(empty)" else old_formatted.replace("|", "\\|")
        new_str = "*(empty)*" if new_formatted == "(empty)" else new_formatted.replace("|", "\\|")

        # Truncate very long values
        if len(old_str) > 50:
            old_str = old_str[:47] + "..."
        if len(new_str) > 50:
            new_str = new_str[:47] + "..."

        lines.append(f"| `{field_name}` | {old_str} | {new_str} |")

    lines.append("")
    return lines


def write_diff_markdown_output(
    diff_result: DiffResult,
    base_filename: str,
    output_dir: str | Path,
    logger: logging.Logger,
    changes_only: bool = False,
    side_by_side: bool = False,
) -> str:
    """
    Write diff comparison to Markdown format.

    Args:
        diff_result: The DiffResult to output
        base_filename: Base filename without extension
        output_dir: Output directory path
        logger: Logger instance
        changes_only: Only include changed items
        side_by_side: Show side-by-side comparison for modified items

    Returns:
        Path to Markdown output file
    """
    try:
        logger.info("Generating diff Markdown output...")

        summary = diff_result.summary
        meta = diff_result.metadata_diff
        md_parts: list[str] = []

        # Title
        md_parts.append("# Data View Comparison Report\n")

        # Metadata
        md_parts.append("## Comparison Details\n")
        md_parts.append(f"**{diff_result.source_label}:** {meta.source_name} (`{meta.source_id}`)")
        md_parts.append(f"**{diff_result.target_label}:** {meta.target_name} (`{meta.target_id}`)")
        md_parts.append(f"**Generated:** {diff_result.generated_at}")
        md_parts.append(f"**Tool Version:** {diff_result.tool_version}\n")

        # Summary table
        md_parts.append("## Summary\n")
        md_parts.append(
            f"| Component | {diff_result.source_label} | {diff_result.target_label} | Added | Removed | Modified | Unchanged | Changed |",
        )
        md_parts.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        md_parts.append(
            f"| Metrics | {summary.source_metrics_count} | {summary.target_metrics_count} | "
            f"+{summary.metrics_added} | -{summary.metrics_removed} | ~{summary.metrics_modified} | "
            f"{summary.metrics_unchanged} | {summary.metrics_change_percent:.1f}% |",
        )
        md_parts.append(
            f"| Dimensions | {summary.source_dimensions_count} | {summary.target_dimensions_count} | "
            f"+{summary.dimensions_added} | -{summary.dimensions_removed} | ~{summary.dimensions_modified} | "
            f"{summary.dimensions_unchanged} | {summary.dimensions_change_percent:.1f}% |",
        )

        # Add inventory rows to summary if present
        if diff_result.has_inventory_diffs:
            if summary.source_calc_metrics_count > 0 or summary.target_calc_metrics_count > 0:
                md_parts.append(
                    f"| **Calc Metrics** | {summary.source_calc_metrics_count} | {summary.target_calc_metrics_count} | "
                    f"+{summary.calc_metrics_added} | -{summary.calc_metrics_removed} | ~{summary.calc_metrics_modified} | "
                    f"{summary.calc_metrics_unchanged} | - |",
                )
            if summary.source_segments_count > 0 or summary.target_segments_count > 0:
                md_parts.append(
                    f"| **Segments** | {summary.source_segments_count} | {summary.target_segments_count} | "
                    f"+{summary.segments_added} | -{summary.segments_removed} | ~{summary.segments_modified} | "
                    f"{summary.segments_unchanged} | - |",
                )
        md_parts.append("")

        if not summary.has_changes:
            md_parts.append("**✓ No differences found.**\n")
        else:
            md_parts.append(f"**Total: {summary.total_summary}**\n")

        # Metrics changes
        metric_changes = [d for d in diff_result.metric_diffs if d.change_type != ChangeType.UNCHANGED]
        if metric_changes or not changes_only:
            md_parts.append("## Metrics Changes\n")
            if metric_changes:
                md_parts.append("| Status | ID | Name | Details |")
                md_parts.append("| --- | --- | --- | --- |")
                for diff in metric_changes:
                    symbol = _get_change_emoji(diff.change_type)
                    detail = _get_change_detail(diff).replace("|", "\\|")
                    md_parts.append(f"| {symbol} | `{diff.id}` | {diff.name} | {detail} |")

                # Add side-by-side detail for modified items
                if side_by_side:
                    modified = [d for d in metric_changes if d.change_type == ChangeType.MODIFIED]
                    if modified:
                        md_parts.append("\n### Modified Metrics - Side by Side\n")
                        for diff in modified:
                            md_parts.extend(
                                _format_markdown_side_by_side(diff, diff_result.source_label, diff_result.target_label),
                            )
            else:
                md_parts.append("*No changes*")
            md_parts.append("")

        # Dimensions changes
        dim_changes = [d for d in diff_result.dimension_diffs if d.change_type != ChangeType.UNCHANGED]
        if dim_changes or not changes_only:
            md_parts.append("## Dimensions Changes\n")
            if dim_changes:
                md_parts.append("| Status | ID | Name | Details |")
                md_parts.append("| --- | --- | --- | --- |")
                for diff in dim_changes:
                    symbol = _get_change_emoji(diff.change_type)
                    detail = _get_change_detail(diff).replace("|", "\\|")
                    md_parts.append(f"| {symbol} | `{diff.id}` | {diff.name} | {detail} |")

                # Add side-by-side detail for modified items
                if side_by_side:
                    modified = [d for d in dim_changes if d.change_type == ChangeType.MODIFIED]
                    if modified:
                        md_parts.append("\n### Modified Dimensions - Side by Side\n")
                        for diff in modified:
                            md_parts.extend(
                                _format_markdown_side_by_side(diff, diff_result.source_label, diff_result.target_label),
                            )
            else:
                md_parts.append("*No changes*")
            md_parts.append("")

        # Inventory changes (if present)
        if diff_result.has_inventory_diffs:
            md_parts.append("---\n")
            md_parts.append("# Inventory Changes\n")

            # Calculated metrics inventory changes
            if diff_result.calc_metrics_diffs is not None:
                calc_changes = [d for d in diff_result.calc_metrics_diffs if d.change_type != ChangeType.UNCHANGED]
                md_parts.append(f"## Calculated Metrics Changes ({len(calc_changes)})\n")
                if calc_changes:
                    md_parts.append("| Status | ID | Name | Details |")
                    md_parts.append("| --- | --- | --- | --- |")
                    for diff in calc_changes:
                        symbol = _get_change_emoji(diff.change_type)
                        detail = _get_inventory_change_detail(diff).replace("|", "\\|")
                        md_parts.append(f"| {symbol} | `{diff.id}` | {diff.name} | {detail} |")
                else:
                    md_parts.append("*No changes*")
                md_parts.append("")

            # Segments inventory changes
            if diff_result.segments_diffs is not None:
                seg_changes = [d for d in diff_result.segments_diffs if d.change_type != ChangeType.UNCHANGED]
                md_parts.append(f"## Segments Changes ({len(seg_changes)})\n")
                if seg_changes:
                    md_parts.append("| Status | ID | Name | Details |")
                    md_parts.append("| --- | --- | --- | --- |")
                    for diff in seg_changes:
                        symbol = _get_change_emoji(diff.change_type)
                        detail = _get_inventory_change_detail(diff).replace("|", "\\|")
                        md_parts.append(f"| {symbol} | `{diff.id}` | {diff.name} | {detail} |")
                else:
                    md_parts.append("*No changes*")
                md_parts.append("")

        md_parts.append("---")
        md_parts.append("*Generated by CJA Auto SDR Generator*")

        markdown_file = os.path.join(output_dir, f"{base_filename}.md")
        with open(markdown_file, "w", encoding="utf-8") as f:
            f.write("\n".join(md_parts))

        logger.info(f"Diff Markdown file created: {markdown_file}")
        return markdown_file

    except (OSError, KeyError, TypeError, ValueError) as e:
        logger.error(_format_error_msg("creating diff Markdown file", error=e))
        raise
