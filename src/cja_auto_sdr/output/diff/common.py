"""Shared helpers for diff output renderers.

This module contains low-level formatting helpers used by the console,
markdown, grouped, and PR-comment diff renderers.
"""

from __future__ import annotations

from typing import Any

import pandas as pd

from cja_auto_sdr.core.colors import ConsoleColors
from cja_auto_sdr.diff.models import (
    ChangeType,
    ComponentDiff,
    DiffResult,
    InventoryItemDiff,
)

# ---------------------------------------------------------------------------
# ANSIColors adapter — delegates to ConsoleColors constants but accepts an
# explicit 'enabled' parameter so callers can toggle color per-call.
# ---------------------------------------------------------------------------


class ANSIColors:
    """ANSI escape codes for colored terminal output.

    This class provides the same functionality as ConsoleColors but with an
    explicit 'enabled' parameter for cases where color control is needed
    independent of TTY detection.
    """

    # Re-export constants from ConsoleColors
    GREEN = ConsoleColors.GREEN
    RED = ConsoleColors.RED
    YELLOW = ConsoleColors.YELLOW
    CYAN = ConsoleColors.CYAN
    BOLD = ConsoleColors.BOLD
    RESET = ConsoleColors.RESET
    ANSI_ESCAPE = ConsoleColors.ANSI_ESCAPE

    @classmethod
    def green(cls, text: str, enabled: bool = True) -> str:
        return f"{cls.GREEN}{text}{cls.RESET}" if enabled else text

    @classmethod
    def red(cls, text: str, enabled: bool = True) -> str:
        return f"{cls.RED}{text}{cls.RESET}" if enabled else text

    @classmethod
    def yellow(cls, text: str, enabled: bool = True) -> str:
        return f"{cls.YELLOW}{text}{cls.RESET}" if enabled else text

    @classmethod
    def cyan(cls, text: str, enabled: bool = True) -> str:
        return f"{cls.CYAN}{text}{cls.RESET}" if enabled else text

    @classmethod
    def bold(cls, text: str, enabled: bool = True) -> str:
        return f"{cls.BOLD}{text}{cls.RESET}" if enabled else text

    # Delegate utility methods to ConsoleColors
    visible_len = ConsoleColors.visible_len
    rjust = ConsoleColors.rjust
    ljust = ConsoleColors.ljust


# ---------------------------------------------------------------------------
# Value formatting
# ---------------------------------------------------------------------------


def _display_name(value: object) -> str:
    """Return a printable name: blank for None, NaN, pd.NA, and NaT."""
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except (TypeError, ValueError):
        pass
    return str(value)


def _format_diff_value(val: Any, truncate: bool = True, max_len: int = 30) -> str:
    """Format a value for diff display, handling None and NaN."""
    if val is None:
        return "(empty)"
    try:
        if pd.isna(val):
            return "(empty)"
    except (TypeError, ValueError):
        pass
    result = str(val)
    if truncate and len(result) > max_len:
        result = result[:max_len] + "..."
    return result


# ---------------------------------------------------------------------------
# Change symbols / emoji
# ---------------------------------------------------------------------------


def _get_change_symbol(change_type: ChangeType) -> str:
    """Get symbol for change type"""
    symbols = {ChangeType.ADDED: "+", ChangeType.REMOVED: "-", ChangeType.MODIFIED: "~", ChangeType.UNCHANGED: " "}
    return symbols.get(change_type, "?")


def _get_colored_symbol(change_type: ChangeType, use_color: bool = True) -> str:
    """Get color-coded symbol for change type"""
    symbol = _get_change_symbol(change_type)
    if not use_color:
        return symbol
    if change_type == ChangeType.ADDED:
        return ANSIColors.green(symbol, use_color)
    if change_type == ChangeType.REMOVED:
        return ANSIColors.red(symbol, use_color)
    if change_type == ChangeType.MODIFIED:
        return ANSIColors.yellow(symbol, use_color)
    return symbol


def _get_change_emoji(change_type: ChangeType) -> str:
    """Get emoji for change type"""
    emojis = {ChangeType.ADDED: "+", ChangeType.REMOVED: "-", ChangeType.MODIFIED: "~", ChangeType.UNCHANGED: ""}
    return emojis.get(change_type, "")


# ---------------------------------------------------------------------------
# Change detail formatters
# ---------------------------------------------------------------------------


def _join_changed_fields(
    changed_fields: dict[str, tuple[Any, Any]],
    truncate: bool,
    max_len: int | None,
) -> str:
    """Join ``field: 'old' -> 'new'`` entries, optionally bounded to *max_len* characters.

    When the full text exceeds *max_len*, each old/new value is shortened evenly and
    ends with ``...`` so the arrow and both sides stay visible.
    """
    pairs = [
        (field, _format_diff_value(old_val, truncate), _format_diff_value(new_val, truncate))
        for field, (old_val, new_val) in changed_fields.items()
    ]

    def render(values: list[tuple[str, str, str]]) -> str:
        return "; ".join(f"{field}: '{old}' -> '{new}'" for field, old, new in values)

    text = render(pairs)
    if max_len is None or len(text) <= max_len:
        return text

    overhead = len(render([(field, "", "") for field, _, _ in pairs]))
    per_value = max((max_len - overhead) // (2 * len(pairs)), 4)
    shortened = [
        (
            field,
            old if len(old) <= per_value else old[: per_value - 3] + "...",
            new if len(new) <= per_value else new[: per_value - 3] + "...",
        )
        for field, old, new in pairs
    ]
    return render(shortened)


def _get_change_detail(diff: ComponentDiff, truncate: bool = True, max_len: int | None = None) -> str:
    """Get detail string for a component diff"""
    if diff.change_type == ChangeType.MODIFIED and diff.changed_fields:
        return _join_changed_fields(diff.changed_fields, truncate, max_len)
    return ""


def _get_inventory_change_detail(diff: InventoryItemDiff, truncate: bool = True, max_len: int | None = None) -> str:
    """Get detail string for an inventory item diff"""
    if diff.change_type == ChangeType.MODIFIED and diff.changed_fields:
        return _join_changed_fields(diff.changed_fields, truncate, max_len)
    return ""


# ---------------------------------------------------------------------------
# Breaking change detection
# ---------------------------------------------------------------------------


def detect_breaking_changes(diff_result: DiffResult) -> list[dict[str, Any]]:
    """
    Detect breaking changes in a diff result.

    Breaking changes include:
    - Changes to 'type' field (data type changes)
    - Changes to 'schemaPath' field (schema mapping changes)
    - Removal of existing components

    Args:
        diff_result: The DiffResult to analyze

    Returns:
        List of breaking change dictionaries with details
    """
    breaking_changes: list[dict[str, Any]] = []

    all_diffs = diff_result.metric_diffs + diff_result.dimension_diffs

    for diff in all_diffs:
        # Removed components are breaking
        if diff.change_type == ChangeType.REMOVED:
            breaking_changes.append(
                {
                    "component_id": diff.id,
                    "component_name": diff.name,
                    "change_type": "removed",
                    "severity": "high",
                    "description": f"Component '{diff.name}' was removed",
                },
            )

        # Check for type or schema changes
        elif diff.change_type == ChangeType.MODIFIED and diff.changed_fields:
            for field, (old_val, new_val) in diff.changed_fields.items():
                if field == "type":
                    breaking_changes.append(
                        {
                            "component_id": diff.id,
                            "component_name": diff.name,
                            "change_type": "type_changed",
                            "field": field,
                            "old_value": old_val,
                            "new_value": new_val,
                            "severity": "high",
                            "description": f"Data type changed from '{_format_diff_value(old_val, truncate=False)}' to '{_format_diff_value(new_val, truncate=False)}'",
                        },
                    )
                elif field == "schemaPath":
                    breaking_changes.append(
                        {
                            "component_id": diff.id,
                            "component_name": diff.name,
                            "change_type": "schema_changed",
                            "field": field,
                            "old_value": old_val,
                            "new_value": new_val,
                            "severity": "medium",
                            "description": f"Schema path changed from '{_format_diff_value(old_val, truncate=False)}' to '{_format_diff_value(new_val, truncate=False)}'",
                        },
                    )

    return breaking_changes
