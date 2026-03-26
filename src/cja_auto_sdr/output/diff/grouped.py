"""Grouped-by-field diff output renderer.

Extracted from generator.py. Provides:
- write_diff_grouped_by_field_output: Diff output grouped by changed field
"""

from __future__ import annotations

from cja_auto_sdr.diff.models import ChangeType, DiffResult
from cja_auto_sdr.output.diff.common import (
    ANSIColors,
    _format_diff_value,
    detect_breaking_changes,
)

__all__ = [
    "write_diff_grouped_by_field_output",
]


def write_diff_grouped_by_field_output(diff_result: DiffResult, use_color: bool = True, limit: int = 10) -> str:
    """
    Write diff output grouped by changed field instead of by component.

    Args:
        diff_result: The DiffResult to output
        use_color: Use ANSI color codes
        limit: Max items per section (0 = unlimited)

    Returns:
        Formatted string for console output
    """
    lines: list[str] = []
    summary = diff_result.summary
    meta = diff_result.metadata_diff
    c = use_color

    # Header
    lines.append("=" * 80)
    lines.append(ANSIColors.bold("DATA VIEW COMPARISON - GROUPED BY FIELD", c))
    lines.append("=" * 80)
    lines.append(f"{diff_result.source_label}: {meta.source_name}")
    lines.append(f"{diff_result.target_label}: {meta.target_name}")
    lines.append(f"Generated: {diff_result.generated_at}")
    lines.append("=" * 80)

    # Collect all changed fields across all components
    field_changes: dict[str, list[tuple[str, str, object, object]]] = {}  # field -> [(id, name, old, new), ...]

    all_diffs = diff_result.metric_diffs + diff_result.dimension_diffs
    for diff in all_diffs:
        if diff.change_type == ChangeType.MODIFIED and diff.changed_fields:
            for field, (old_val, new_val) in diff.changed_fields.items():
                if field not in field_changes:
                    field_changes[field] = []
                field_changes[field].append((diff.id, diff.name, old_val, new_val))

    # Use shared detect_breaking_changes for breaking change detection
    breaking = detect_breaking_changes(diff_result)
    # Filter to only type/schema changes (not removals) for inline display
    breaking_field_changes = [b for b in breaking if b["change_type"] in ("type_changed", "schema_changed")]

    # Summary
    lines.append("")
    lines.append(ANSIColors.bold("SUMMARY", c))
    lines.append(f"Total components changed: {summary.total_changes}")
    lines.append(f"  Added: {ANSIColors.green(str(summary.metrics_added + summary.dimensions_added), c)}")
    lines.append(f"  Removed: {ANSIColors.red(str(summary.metrics_removed + summary.dimensions_removed), c)}")
    lines.append(f"  Modified: {ANSIColors.yellow(str(summary.metrics_modified + summary.dimensions_modified), c)}")
    lines.append(f"Fields with changes: {len(field_changes)}")

    # Breaking changes warning
    if breaking_field_changes:
        lines.append("")
        lines.append(ANSIColors.red("⚠  BREAKING CHANGES DETECTED", c))
        lines.append("-" * 40)
        for bc in breaking_field_changes:
            lines.append(f"  {bc['component_id']}: {bc['field']} changed")
            lines.append(
                f"    '{_format_diff_value(bc['old_value'], truncate=False)}' → '{_format_diff_value(bc['new_value'], truncate=False)}'",
            )

    # Group by field
    lines.append("")
    lines.append(ANSIColors.bold("CHANGES BY FIELD", c))
    lines.append("-" * 80)

    for field in sorted(field_changes.keys()):
        changes = field_changes[field]
        lines.append("")
        lines.append(f"{ANSIColors.cyan(field, c)} ({len(changes)} component{'s' if len(changes) != 1 else ''}):")

        items_to_show = changes if limit == 0 else changes[:limit]
        for comp_id, _comp_name, old_val, new_val in items_to_show:
            old_str = _format_diff_value(old_val, truncate=True)
            new_str = _format_diff_value(new_val, truncate=True)
            lines.append(f"  {comp_id}: '{old_str}' → '{new_str}'")

        if limit > 0 and len(changes) > limit:
            lines.append(f"  ... and {len(changes) - limit} more")

    # Added/removed summary
    added = [d for d in all_diffs if d.change_type == ChangeType.ADDED]
    removed = [d for d in all_diffs if d.change_type == ChangeType.REMOVED]

    if added:
        lines.append("")
        lines.append(ANSIColors.green(f"ADDED ({len(added)})", c))
        added_to_show = added if limit == 0 else added[:limit]
        lines.extend(f"  [+] {diff.id}" for diff in added_to_show)
        if limit > 0 and len(added) > limit:
            lines.append(f"  ... and {len(added) - limit} more")

    if removed:
        lines.append("")
        lines.append(ANSIColors.red(f"REMOVED ({len(removed)})", c))
        removed_to_show = removed if limit == 0 else removed[:limit]
        lines.extend(f"  [-] {diff.id}" for diff in removed_to_show)
        if limit > 0 and len(removed) > limit:
            lines.append(f"  ... and {len(removed) - limit} more")

    lines.append("")
    lines.append("=" * 80)
    lines.append(ANSIColors.cyan(f"Summary: {summary.natural_language_summary}", c))
    lines.append("=" * 80)

    return "\n".join(lines)
