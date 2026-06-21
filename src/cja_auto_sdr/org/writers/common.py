"""Shared normalization, validation, and rendering helpers for org report writers."""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from cja_auto_sdr.core.colors import ConsoleColors
from cja_auto_sdr.core.constants import FORMAT_ALIASES


def _render_distribution_bar(count: int, total: int, width: int = 30) -> str:
    """Render ASCII progress bar for distribution visualization.

    Args:
        count: Number of items in this bucket
        total: Total items across all buckets
        width: Width of the bar in characters

    Returns:
        ASCII bar string like "████████░░░░░░░░ 45%"
    """
    if total == 0:
        return "░" * width + "  0%"

    pct = count / total
    filled = int(pct * width)
    bar = "█" * filled + "░" * (width - filled)
    return f"{bar} {pct * 100:>3.0f}%"


def _normalize_recommendation_severity(severity: Any) -> str:
    """Normalize recommendation severity to supported output classes."""
    value = str(severity or "low").strip().lower()
    return value if value in {"high", "medium", "low"} else "low"


def _format_recommendation_context_entries(rec: dict[str, Any]) -> list[tuple[str, str]]:
    """Build human-readable recommendation context entries for output renderers."""

    def _fmt_data_view(name: Any, dv_id: Any) -> str:
        name_text = str(name).strip() if name is not None else ""
        id_text = str(dv_id).strip() if dv_id is not None else ""
        if name_text and id_text:
            return f"{name_text} ({id_text})"
        return name_text or id_text

    context_entries: list[tuple[str, str]] = []

    data_view_text = _fmt_data_view(rec.get("data_view_name"), rec.get("data_view"))
    if data_view_text:
        context_entries.append(("Data View", data_view_text))

    pair_left = _fmt_data_view(rec.get("data_view_1_name"), rec.get("data_view_1"))
    pair_right = _fmt_data_view(rec.get("data_view_2_name"), rec.get("data_view_2"))
    if pair_left or pair_right:
        if pair_left and pair_right:
            context_entries.append(("Pair", f"{pair_left} \u2194 {pair_right}"))
        else:
            context_entries.append(("Pair", pair_left or pair_right))

    similarity = rec.get("similarity")
    if isinstance(similarity, (int, float)) and not isinstance(similarity, bool):
        context_entries.append(("Similarity", f"{similarity * 100:.1f}%"))

    for label, key in (
        ("Isolated Count", "isolated_count"),
        ("Derived Count", "derived_count"),
        ("Total Count", "total_count"),
        ("Count", "count"),
        ("Drift Count", "drift_count"),
    ):
        if key in rec and rec.get(key) is not None:
            context_entries.append((label, str(rec.get(key))))

    ratio = rec.get("ratio")
    if isinstance(ratio, (int, float)) and not isinstance(ratio, bool):
        context_entries.append(("Ratio", f"{ratio * 100:.1f}%"))

    modified = rec.get("modified")
    if modified:
        context_entries.append(("Last Modified", str(modified)))

    return context_entries


def _normalize_recommendation_for_json(raw_rec: Any) -> dict[str, Any]:
    """Normalize recommendation payload for JSON serialization and output parity."""
    rec = dict(raw_rec) if isinstance(raw_rec, dict) else {"type": "unknown", "reason": str(raw_rec)}
    rec["severity"] = _normalize_recommendation_severity(rec.get("severity", "low"))
    context_entries = _format_recommendation_context_entries(rec)
    if context_entries:
        rec["context"] = [{"label": label, "value": value} for label, value in context_entries]
    # Ensure output is JSON-serializable even if recommendations include odd values.
    normalized = json.loads(json.dumps(rec, ensure_ascii=False, default=str))
    return normalized if isinstance(normalized, dict) else {"type": "unknown", "reason": str(normalized)}


def _flatten_recommendation_for_tabular(rec: dict[str, Any]) -> dict[str, Any]:
    """Flatten recommendation fields for CSV/Excel exports with full context columns."""
    known_keys = {
        "type",
        "severity",
        "reason",
        "data_view",
        "data_view_name",
        "data_view_1",
        "data_view_1_name",
        "data_view_2",
        "data_view_2_name",
        "similarity",
        "isolated_count",
        "derived_count",
        "total_count",
        "ratio",
        "count",
        "drift_count",
        "modified",
        "context",
    }
    extra_details = {k: v for k, v in rec.items() if k not in known_keys}

    return {
        "Type": rec.get("type", ""),
        "Severity": _normalize_recommendation_severity(rec.get("severity", "low")),
        "Description": rec.get("reason", ""),
        "Data View ID": rec.get("data_view", ""),
        "Data View Name": rec.get("data_view_name", ""),
        "Data View 1 ID": rec.get("data_view_1", ""),
        "Data View 1 Name": rec.get("data_view_1_name", ""),
        "Data View 2 ID": rec.get("data_view_2", ""),
        "Data View 2 Name": rec.get("data_view_2_name", ""),
        "Similarity": rec.get("similarity", ""),
        "Isolated Count": rec.get("isolated_count", ""),
        "Derived Count": rec.get("derived_count", ""),
        "Total Count": rec.get("total_count", ""),
        "Ratio": rec.get("ratio", ""),
        "Count": rec.get("count", ""),
        "Drift Count": rec.get("drift_count", ""),
        "Modified": rec.get("modified", ""),
        "Extra Details": json.dumps(extra_details, sort_keys=True, default=str) if extra_details else "",
    }


def _normalize_org_report_output_format(output_format: str | None) -> str:
    """Normalize org-report output format to a canonical lowercase value."""
    return (output_format or "console").strip().lower()


def _validate_org_report_output_request(
    output_format: str,
    output_to_stdout: bool,
    status_print: Callable[..., None],
) -> bool:
    """Validate org-report output arguments before expensive analysis starts."""
    valid_formats = {"console", "json", "excel", "markdown", "html", "csv", "notion", "all", *FORMAT_ALIASES}
    if output_format not in valid_formats:
        status_print(
            ConsoleColors.error(
                f"ERROR: Unknown format '{output_format}'. Valid formats: "
                "console, json, excel, markdown, html, csv, notion, all, reports, data, ci",
            ),
        )
        return False

    if output_to_stdout and output_format not in {"json", "console"}:
        status_print(
            ConsoleColors.error(
                "ERROR: --output stdout is only supported for --format json or --format console in org-report mode."
            ),
        )
        return False

    return True
