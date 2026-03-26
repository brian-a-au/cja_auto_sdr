"""Console diff output renderer — colored terminal output.

Extracted from generator.py. Provides:
- write_diff_console_output: Full console diff report with color-coded output
- _format_side_by_side: Side-by-side comparison table with box-drawing characters
"""

from __future__ import annotations

import textwrap

from cja_auto_sdr.diff.models import ChangeType, DiffResult
from cja_auto_sdr.output.diff.common import (
    ANSIColors,
    _format_diff_value,
    _get_change_detail,
    _get_colored_symbol,
    _get_inventory_change_detail,
)

__all__ = [
    "write_diff_console_output",
]


def _format_side_by_side(
    diff,
    source_label: str,
    target_label: str,
    col_width: int = 35,
    max_col_width: int = 60,
) -> list[str]:
    """
    Format a component diff as a side-by-side comparison table.

    Args:
        diff: The ComponentDiff to format
        source_label: Label for source side
        target_label: Label for target side
        col_width: Base width of each column
        max_col_width: Maximum width of each column (text will wrap)

    Returns:
        List of formatted lines for the side-by-side view
    """
    lines: list[str] = []
    if diff.change_type != ChangeType.MODIFIED or not diff.changed_fields:
        return lines

    # Pre-compute all display strings
    field_displays = []
    for field_name, (old_val, new_val) in diff.changed_fields.items():
        old_str = _format_diff_value(old_val, truncate=False)
        new_str = _format_diff_value(new_val, truncate=False)
        old_display = f"{field_name}: {old_str}"
        new_display = f"{field_name}: {new_str}"
        field_displays.append((old_display, new_display))

    # Calculate column width: expand to fit content but cap at max_col_width
    col_width = max(col_width, len(source_label) + 2, len(target_label) + 2)
    for old_display, new_display in field_displays:
        col_width = max(col_width, min(len(old_display), max_col_width), min(len(new_display), max_col_width))
    col_width = min(col_width, max_col_width)

    # Header for this component
    lines.append(f"    ┌{'─' * (col_width + 2)}┬{'─' * (col_width + 2)}┐")
    lines.append(f"    │ {source_label:<{col_width}} │ {target_label:<{col_width}} │")
    lines.append(f"    ├{'─' * (col_width + 2)}┼{'─' * (col_width + 2)}┤")

    # Changed fields with text wrapping
    for old_display, new_display in field_displays:
        # Wrap each side independently
        old_wrapped = textwrap.wrap(old_display, width=col_width) or [""]
        new_wrapped = textwrap.wrap(new_display, width=col_width) or [""]

        # Pad to same number of lines
        max_lines = max(len(old_wrapped), len(new_wrapped))
        old_wrapped.extend([""] * (max_lines - len(old_wrapped)))
        new_wrapped.extend([""] * (max_lines - len(new_wrapped)))

        # Output each line
        for old_line, new_line in zip(old_wrapped, new_wrapped, strict=True):
            lines.append(f"    │ {old_line:<{col_width}} │ {new_line:<{col_width}} │")

    lines.append(f"    └{'─' * (col_width + 2)}┴{'─' * (col_width + 2)}┘")

    return lines


def write_diff_console_output(
    diff_result: DiffResult,
    changes_only: bool = False,
    summary_only: bool = False,
    side_by_side: bool = False,
    use_color: bool = True,
) -> str:
    """
    Write diff comparison to console with color-coded output.

    Args:
        diff_result: The DiffResult to output
        changes_only: Only show changed items (hide unchanged)
        summary_only: Only show summary statistics
        side_by_side: Show side-by-side comparison for modified items
        use_color: Use ANSI color codes in output (default: True)

    Returns:
        Formatted string for console output
    """
    lines: list[str] = []
    summary = diff_result.summary
    meta = diff_result.metadata_diff
    c = use_color  # Shorthand for color enabled flag

    # Header
    lines.append("=" * 80)
    lines.append(ANSIColors.bold("DATA VIEW COMPARISON REPORT", c))
    lines.append("=" * 80)
    lines.append(f"{diff_result.source_label}: {meta.source_name} ({meta.source_id})")
    lines.append(f"{diff_result.target_label}: {meta.target_name} ({meta.target_id})")
    lines.append(f"Generated: {diff_result.generated_at}")
    lines.append("=" * 80)

    # Summary table with percentages
    lines.append("")
    lines.append(ANSIColors.bold("SUMMARY", c))

    # Build full header labels with data view name and ID
    src_header = f"{diff_result.source_label}: {meta.source_name} ({meta.source_id})"
    tgt_header = f"{diff_result.target_label}: {meta.target_name} ({meta.target_id})"

    # Calculate dynamic column widths based on full header lengths
    src_width = max(8, len(src_header))
    tgt_width = max(8, len(tgt_header))
    total_width = 20 + src_width + tgt_width + 10 + 10 + 10 + 12 + 12 + 7  # +7 for spacing

    lines.append(
        f"{'':20s} {src_header:>{src_width}s} {tgt_header:>{tgt_width}s} {'Added':>10s} {'Removed':>10s} {'Modified':>10s} {'Unchanged':>12s} {'Changed':>12s}",
    )
    lines.append("-" * total_width)

    # Metrics row with percentage (using ANSI-aware padding for colored strings)
    metrics_pct = f"({summary.metrics_change_percent:.1f}%)"
    added_str = (
        ANSIColors.green(f"+{summary.metrics_added}", c) if summary.metrics_added else f"+{summary.metrics_added}"
    )
    removed_str = (
        ANSIColors.red(f"-{summary.metrics_removed}", c) if summary.metrics_removed else f"-{summary.metrics_removed}"
    )
    modified_str = (
        ANSIColors.yellow(f"~{summary.metrics_modified}", c)
        if summary.metrics_modified
        else f"~{summary.metrics_modified}"
    )
    lines.append(
        f"{'Metrics':20s} {summary.source_metrics_count:{src_width}d} {summary.target_metrics_count:{tgt_width}d} "
        f"{ANSIColors.rjust(added_str, 10)} {ANSIColors.rjust(removed_str, 10)} {ANSIColors.rjust(modified_str, 10)} {summary.metrics_unchanged:>12d} {metrics_pct:>12s}",
    )

    # Dimensions row with percentage (using ANSI-aware padding for colored strings)
    dims_pct = f"({summary.dimensions_change_percent:.1f}%)"
    added_str = (
        ANSIColors.green(f"+{summary.dimensions_added}", c)
        if summary.dimensions_added
        else f"+{summary.dimensions_added}"
    )
    removed_str = (
        ANSIColors.red(f"-{summary.dimensions_removed}", c)
        if summary.dimensions_removed
        else f"-{summary.dimensions_removed}"
    )
    modified_str = (
        ANSIColors.yellow(f"~{summary.dimensions_modified}", c)
        if summary.dimensions_modified
        else f"~{summary.dimensions_modified}"
    )
    lines.append(
        f"{'Dimensions':20s} {summary.source_dimensions_count:{src_width}d} {summary.target_dimensions_count:{tgt_width}d} "
        f"{ANSIColors.rjust(added_str, 10)} {ANSIColors.rjust(removed_str, 10)} {ANSIColors.rjust(modified_str, 10)} {summary.dimensions_unchanged:>12d} {dims_pct:>12s}",
    )

    # Inventory rows (if present)
    if summary.has_inventory_changes or (
        summary.source_calc_metrics_count > 0 or summary.target_calc_metrics_count > 0
    ):
        lines.append("-" * total_width)
        lines.append(ANSIColors.bold("INVENTORY", c))

        # Calculated metrics row
        if summary.source_calc_metrics_count > 0 or summary.target_calc_metrics_count > 0:
            added_str = (
                ANSIColors.green(f"+{summary.calc_metrics_added}", c)
                if summary.calc_metrics_added
                else f"+{summary.calc_metrics_added}"
            )
            removed_str = (
                ANSIColors.red(f"-{summary.calc_metrics_removed}", c)
                if summary.calc_metrics_removed
                else f"-{summary.calc_metrics_removed}"
            )
            modified_str = (
                ANSIColors.yellow(f"~{summary.calc_metrics_modified}", c)
                if summary.calc_metrics_modified
                else f"~{summary.calc_metrics_modified}"
            )
            lines.append(
                f"{'Calc Metrics':20s} {summary.source_calc_metrics_count:{src_width}d} {summary.target_calc_metrics_count:{tgt_width}d} "
                f"{ANSIColors.rjust(added_str, 10)} {ANSIColors.rjust(removed_str, 10)} {ANSIColors.rjust(modified_str, 10)} {summary.calc_metrics_unchanged:>12d} {'':>12s}",
            )

        # Segments row
        if summary.source_segments_count > 0 or summary.target_segments_count > 0:
            added_str = (
                ANSIColors.green(f"+{summary.segments_added}", c)
                if summary.segments_added
                else f"+{summary.segments_added}"
            )
            removed_str = (
                ANSIColors.red(f"-{summary.segments_removed}", c)
                if summary.segments_removed
                else f"-{summary.segments_removed}"
            )
            modified_str = (
                ANSIColors.yellow(f"~{summary.segments_modified}", c)
                if summary.segments_modified
                else f"~{summary.segments_modified}"
            )
            lines.append(
                f"{'Segments':20s} {summary.source_segments_count:{src_width}d} {summary.target_segments_count:{tgt_width}d} "
                f"{ANSIColors.rjust(added_str, 10)} {ANSIColors.rjust(removed_str, 10)} {ANSIColors.rjust(modified_str, 10)} {summary.segments_unchanged:>12d} {'':>12s}",
            )

    lines.append("-" * total_width)

    if summary_only:
        lines.append("")
        if summary.has_changes:
            lines.append(f"Total changes: {summary.total_changes}")
            lines.append(f"Summary: {summary.natural_language_summary}")
        else:
            lines.append(ANSIColors.green("No differences found.", c))
        lines.append("=" * 80)
        return "\n".join(lines)

    # Get changes for both metrics and dimensions
    metric_changes = [d for d in diff_result.metric_diffs if d.change_type != ChangeType.UNCHANGED]
    dim_changes = [d for d in diff_result.dimension_diffs if d.change_type != ChangeType.UNCHANGED]

    # Calculate global max ID width for consistent alignment across both sections
    all_changes = metric_changes + dim_changes
    global_max_id_len = max((len(d.id) for d in all_changes), default=0)

    # Metrics changes
    if metric_changes or not changes_only:
        lines.append("")
        change_count = len(metric_changes)
        lines.append(ANSIColors.bold(f"METRICS CHANGES ({change_count})", c))
        if metric_changes:
            for diff in metric_changes:
                colored_symbol = _get_colored_symbol(diff.change_type, c)
                lines.append(f'  [{colored_symbol}] {diff.id:{global_max_id_len}s} "{diff.name}"')
                if side_by_side and diff.change_type == ChangeType.MODIFIED:
                    # Side-by-side view for modified items
                    sbs_lines = _format_side_by_side(diff, diff_result.source_label, diff_result.target_label)
                    lines.extend(sbs_lines)
                else:
                    detail = _get_change_detail(diff)
                    if detail:
                        lines.append(f"      {detail}")
        else:
            lines.append("  No changes")

    # Dimensions changes
    if dim_changes or not changes_only:
        lines.append("")
        change_count = len(dim_changes)
        lines.append(ANSIColors.bold(f"DIMENSIONS CHANGES ({change_count})", c))
        if dim_changes:
            for diff in dim_changes:
                colored_symbol = _get_colored_symbol(diff.change_type, c)
                lines.append(f'  [{colored_symbol}] {diff.id:{global_max_id_len}s} "{diff.name}"')
                if side_by_side and diff.change_type == ChangeType.MODIFIED:
                    # Side-by-side view for modified items
                    sbs_lines = _format_side_by_side(diff, diff_result.source_label, diff_result.target_label)
                    lines.extend(sbs_lines)
                else:
                    detail = _get_change_detail(diff)
                    if detail:
                        lines.append(f"      {detail}")
        else:
            lines.append("  No changes")

    # Inventory changes (if present)
    if diff_result.has_inventory_diffs:
        lines.append("")
        lines.append("-" * 80)
        lines.append(ANSIColors.bold("INVENTORY CHANGES", c))
        lines.append("-" * 80)

        # Calculated metrics inventory changes
        if diff_result.calc_metrics_diffs is not None:
            calc_changes = [d for d in diff_result.calc_metrics_diffs if d.change_type != ChangeType.UNCHANGED]
            lines.append("")
            lines.append(ANSIColors.bold(f"CALCULATED METRICS ({len(calc_changes)} changes)", c))
            if calc_changes:
                for diff in calc_changes:
                    colored_symbol = _get_colored_symbol(diff.change_type, c)
                    lines.append(f'  [{colored_symbol}] {diff.id} "{diff.name}"')
                    if diff.change_type == ChangeType.MODIFIED and diff.changed_fields:
                        detail = _get_inventory_change_detail(diff)
                        if detail:
                            lines.append(f"      {detail}")
            else:
                lines.append("  No changes")

        # Segments inventory changes
        if diff_result.segments_diffs is not None:
            seg_changes = [d for d in diff_result.segments_diffs if d.change_type != ChangeType.UNCHANGED]
            lines.append("")
            lines.append(ANSIColors.bold(f"SEGMENTS ({len(seg_changes)} changes)", c))
            if seg_changes:
                for diff in seg_changes:
                    colored_symbol = _get_colored_symbol(diff.change_type, c)
                    lines.append(f'  [{colored_symbol}] {diff.id} "{diff.name}"')
                    if diff.change_type == ChangeType.MODIFIED and diff.changed_fields:
                        detail = _get_inventory_change_detail(diff)
                        if detail:
                            lines.append(f"      {detail}")
            else:
                lines.append("  No changes")

    # Footer with total summary
    lines.append("")
    lines.append("=" * 80)
    if summary.has_changes:
        # Build color-coded total summary line
        total_parts = []
        if summary.total_added:
            total_parts.append(ANSIColors.green(f"{summary.total_added} added", c))
        if summary.total_removed:
            total_parts.append(ANSIColors.red(f"{summary.total_removed} removed", c))
        if summary.total_modified:
            total_parts.append(ANSIColors.yellow(f"{summary.total_modified} modified", c))
        total_line = ", ".join(total_parts)
        lines.append(ANSIColors.bold(f"Total: {total_line}", c))
        lines.append(
            f"  Metrics: {summary.metrics_added} added, {summary.metrics_removed} removed, {summary.metrics_modified} modified",
        )
        lines.append(
            f"  Dimensions: {summary.dimensions_added} added, {summary.dimensions_removed} removed, {summary.dimensions_modified} modified",
        )
        # Add inventory summary lines if present
        if summary.has_inventory_changes:
            if summary.source_calc_metrics_count > 0 or summary.target_calc_metrics_count > 0:
                lines.append(
                    f"  Calc Metrics: {summary.calc_metrics_added} added, {summary.calc_metrics_removed} removed, {summary.calc_metrics_modified} modified",
                )
            if summary.source_segments_count > 0 or summary.target_segments_count > 0:
                lines.append(
                    f"  Segments: {summary.segments_added} added, {summary.segments_removed} removed, {summary.segments_modified} modified",
                )
    else:
        lines.append(ANSIColors.green("✓ No differences found", c))
    lines.append("=" * 80)

    return "\n".join(lines)
