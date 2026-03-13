"""
Org report writer functions.

Extracted from generator.py — all functions that render OrgReportResult
into various output formats (console, JSON, Excel, Markdown, HTML, CSV).
"""

from __future__ import annotations

import html
import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from cja_auto_sdr.core.colors import ConsoleColors
from cja_auto_sdr.core.constants import BANNER_WIDTH, FORMAT_ALIASES
from cja_auto_sdr.core.version import __version__
from cja_auto_sdr.org.models import (
    ComponentInfo,
    OrgReportComparison,
    OrgReportConfig,
    OrgReportResult,
    OrgReportTrending,
    TrendingDelta,
    TrendingSnapshot,
    _snapshot_effective_data_view_count,
)
from cja_auto_sdr.org.snapshot_utils import sorted_snapshot_strings

__all__ = [
    "_flatten_recommendation_for_tabular",
    "_format_recommendation_context_entries",
    "_normalize_org_report_output_format",
    "_normalize_recommendation_for_json",
    "_normalize_recommendation_severity",
    "_render_distribution_bar",
    "_validate_org_report_output_request",
    "build_org_report_json_data",
    "write_org_report_comparison_console",
    "write_org_report_console",
    "write_org_report_csv",
    "write_org_report_excel",
    "write_org_report_html",
    "write_org_report_json",
    "write_org_report_markdown",
    "write_org_report_stats_only",
]


_TRENDING_METRIC_SPECS: tuple[tuple[str, str, str], ...] = (
    ("Data Views", "data_view_count", "data_view_delta"),
    ("Components", "component_count", "component_delta"),
    ("Core", "core_count", "core_delta"),
    ("Isolated", "isolated_count", "isolated_delta"),
    ("High-Sim Pairs", "high_sim_pair_count", "high_sim_pair_delta"),
)


def _format_trending_timestamp_short(ts: str) -> str:
    """Format an ISO timestamp to a short month-day label like 'Jan 12'."""
    try:
        dt = datetime.fromisoformat(ts)
        return dt.strftime("%b %d")
    except ValueError, AttributeError:
        return ts[:10]


def _build_trending_metric_rows(
    records: list[TrendingSnapshot] | list[TrendingDelta],
    *,
    delta: bool,
) -> list[tuple[str, list[int]]]:
    """Return standard trending metric rows for snapshots or period deltas."""
    metric_rows: list[tuple[str, list[int]]] = []
    for label, snapshot_attr, delta_attr in _TRENDING_METRIC_SPECS:
        if delta:
            values = [getattr(record, delta_attr) for record in records]
        elif snapshot_attr == "data_view_count":
            values = [_snapshot_effective_data_view_count(record) for record in records]
        else:
            values = [getattr(record, snapshot_attr) for record in records]
        metric_rows.append((label, values))
    return metric_rows


def _trending_snapshot_metric_rows(
    snapshots: list[TrendingSnapshot],
) -> list[tuple[str, list[int]]]:
    """Return the standard snapshot metric rows for trending tables."""
    return _build_trending_metric_rows(snapshots, delta=False)


def _trending_delta_metric_rows(
    deltas: list[TrendingDelta],
) -> list[tuple[str, list[int]]]:
    """Return the standard delta metric rows for trending tables."""
    return _build_trending_metric_rows(deltas, delta=True)


def _trending_snapshot_column_specs(
    snapshots: list[TrendingSnapshot],
) -> list[tuple[str, str]]:
    """Return unique worksheet keys paired with display labels for trending snapshots."""
    return [
        (f"snapshot_{index + 1}", _format_trending_timestamp_short(snapshot.timestamp))
        for index, snapshot in enumerate(snapshots)
    ]


def _format_trending_period_label(from_timestamp: str, to_timestamp: str) -> str:
    """Return a compact human-readable label for one trending period."""
    return f"{_format_trending_timestamp_short(from_timestamp)} -> {_format_trending_timestamp_short(to_timestamp)}"


def _trending_delta_column_specs(
    deltas: list[TrendingDelta],
) -> list[tuple[str, str]]:
    """Return unique worksheet keys paired with display labels for period deltas."""
    return [
        (f"period_{index + 1}", _format_trending_period_label(delta.from_timestamp, delta.to_timestamp))
        for index, delta in enumerate(deltas)
    ]


def _format_signed_trending_value(value: int) -> str:
    """Return a signed integer string for trend deltas."""
    if value > 0:
        return f"+{value}"
    return str(value)


def _stringify_trending_value(value: int) -> str:
    """Return a plain string representation for trend table cells."""
    return str(value)


def _render_console_trending_table(
    column_labels: list[str],
    metric_rows: list[tuple[str, list[int]]],
    *,
    value_formatter: Callable[[int], str] | None = None,
) -> list[str]:
    """Render one console-friendly trending table."""
    if not column_labels or not metric_rows:
        return []

    render_value = value_formatter or _stringify_trending_value
    label_width = max(20, *(len(label) for label, _values in metric_rows))
    column_width = max(9, *(len(label) for label in column_labels))

    lines = [f"{'':{label_width}s}" + "".join(f"{label:>{column_width}s}" for label in column_labels)]
    for label, values in metric_rows:
        lines.append(
            f"{label:{label_width}s}" + "".join(f"{render_value(value):>{column_width}s}" for value in values),
        )
    return lines


def _render_markdown_trending_table(
    column_labels: list[str],
    metric_rows: list[tuple[str, list[int]]],
    *,
    value_formatter: Callable[[int], str] | None = None,
) -> list[str]:
    """Render one Markdown trending table."""
    if not column_labels or not metric_rows:
        return []

    render_value = value_formatter or _stringify_trending_value
    lines = ["| Metric | " + " | ".join(_escape_markdown_table_cell(label) for label in column_labels) + " |"]
    lines.append("|--------|" + "|".join("---------:" for _ in column_labels) + "|")
    for label, values in metric_rows:
        lines.append(
            f"| {_escape_markdown_table_cell(label)} | "
            + " | ".join(_escape_markdown_table_cell(render_value(value)) for value in values)
            + " |"
        )
    return lines


def _escape_markdown_table_cell(value: Any) -> str:
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


def _render_html_trending_table(
    column_labels: list[str],
    metric_rows: list[tuple[str, list[int]]],
    *,
    value_formatter: Callable[[int], str] | None = None,
) -> str:
    """Render one HTML trending table."""
    if not column_labels or not metric_rows:
        return ""

    render_value = value_formatter or _stringify_trending_value
    rows = [
        "                    <tr>"
        f"<td>{html.escape(label)}</td>"
        + "".join(f"<td>{html.escape(render_value(value))}</td>" for value in values)
        + "</tr>"
        for label, values in metric_rows
    ]
    return (
        '        <div class="card">\n'
        "            <table>\n"
        "                <thead>\n"
        "                    <tr><th>Metric</th>"
        + "".join(f"<th>{html.escape(label)}</th>" for label in column_labels)
        + "</tr>\n"
        "                </thead>\n"
        "                <tbody>\n" + "\n".join(rows) + "\n                </tbody>\n"
        "            </table>\n"
        "        </div>\n"
    )


def _trending_matrix_rows(
    column_specs: list[tuple[str, str]],
    metric_rows: list[tuple[str, list[int]]],
) -> list[dict[str, Any]]:
    """Return tabular rows for Excel export of a trending metric matrix."""
    return [
        {"Metric": label, **{key: value for (key, _), value in zip(column_specs, values, strict=True)}}
        for label, values in metric_rows
    ]


def _trending_snapshot_csv_rows(
    snapshots: list[TrendingSnapshot],
) -> list[dict[str, Any]]:
    """Return row-oriented CSV records for absolute trending snapshots."""
    rows: list[dict[str, Any]] = []
    for snapshot in snapshots:
        for _label, snapshot_attr, _delta_attr in _TRENDING_METRIC_SPECS:
            rows.append(
                {
                    "Snapshot Timestamp": snapshot.timestamp,
                    "Metric": snapshot_attr,
                    "Value": getattr(snapshot, snapshot_attr),
                }
            )
    return rows


def _trending_delta_csv_rows(
    deltas: list[TrendingDelta],
) -> list[dict[str, Any]]:
    """Return row-oriented CSV records for period-over-period deltas."""
    rows: list[dict[str, Any]] = []
    for delta in deltas:
        period_label = _format_trending_period_label(delta.from_timestamp, delta.to_timestamp)
        for label, _snapshot_attr, delta_attr in _TRENDING_METRIC_SPECS:
            rows.append(
                {
                    "From Snapshot Timestamp": delta.from_timestamp,
                    "To Snapshot Timestamp": delta.to_timestamp,
                    "Period": period_label,
                    "Metric": delta_attr,
                    "Metric Label": label,
                    "Value": getattr(delta, delta_attr),
                }
            )
    return rows


def _sorted_drift_score_items(drift_scores: dict[str, float]) -> list[tuple[str, float]]:
    """Return drift scores sorted descending with a stable DV-id tie-breaker."""
    return sorted(drift_scores.items(), key=lambda item: (-item[1], item[0]))


def _top_drift_scores(drift_scores: dict[str, float], limit: int = 10) -> list[tuple[str, float]]:
    """Return drift scores sorted descending, capped at *limit*."""
    return _sorted_drift_score_items(drift_scores)[:limit]


def _resolve_trending_dv_name(trending: OrgReportTrending, dv_id: str) -> str | None:
    """Return the most recent known display name for a drift-ranked data view."""
    for snapshot in reversed(trending.snapshots):
        dv_name = snapshot.dv_names.get(dv_id)
        if dv_name:
            return dv_name
    return None


def _format_trending_dv_label(dv_id: str, dv_name: str | None) -> str:
    """Return a compact human-readable label for one data view."""
    if not dv_name or dv_name == dv_id:
        return dv_id
    return f"{dv_name} ({dv_id})"


def _ranked_drift_entries(
    trending: OrgReportTrending,
    *,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Return ranked drift entries with the best available DV names attached."""
    ranked_scores = _sorted_drift_score_items(trending.drift_scores)
    if limit is not None:
        ranked_scores = ranked_scores[:limit]

    return [
        {
            "data_view_id": dv_id,
            "data_view_name": _resolve_trending_dv_name(trending, dv_id),
            "drift_score": score,
        }
        for dv_id, score in ranked_scores
    ]


def _trending_date_range(snapshots: list[TrendingSnapshot]) -> str:
    """Return 'first_label -> last_label' for a list of snapshots."""
    if not snapshots:
        return ""
    first = _format_trending_timestamp_short(snapshots[0].timestamp)
    last = _format_trending_timestamp_short(snapshots[-1].timestamp)
    return f"{first} \u2192 {last}"


def _render_trending_console(trending: OrgReportTrending) -> str:
    """Render a multi-period trending table and drift list for console output."""
    lines: list[str] = []
    snapshots = trending.snapshots
    if len(snapshots) < 2:
        return ""

    date_range = _trending_date_range(snapshots)
    lines.append("")
    lines.append("\u2550" * 56)
    lines.append(f"TRENDING ({len(snapshots)} snapshots, {date_range})")
    lines.append("\u2550" * 56)

    # Column headers
    col_labels = [_format_trending_timestamp_short(s.timestamp) for s in snapshots]
    lines.extend(_render_console_trending_table(col_labels, _trending_snapshot_metric_rows(snapshots)))

    if trending.deltas:
        lines.append("")
        lines.append("Period Deltas:")
        delta_labels = [label for _key, label in _trending_delta_column_specs(trending.deltas)]
        lines.extend(
            _render_console_trending_table(
                delta_labels,
                _trending_delta_metric_rows(trending.deltas),
                value_formatter=_format_signed_trending_value,
            )
        )

    # Drift scores
    if trending.drift_scores:
        lines.append("")
        lines.append("Top Drift:")
        for entry in _ranked_drift_entries(trending, limit=10):
            label = _format_trending_dv_label(entry["data_view_id"], entry["data_view_name"])
            lines.append(f"  \u25b8 {label:<40.40s} {entry['drift_score']:.2f}")

    return "\n".join(lines)


def _print_trending_console_section(trending: OrgReportTrending | None) -> None:
    """Emit the console trending section when a usable window is available."""
    if trending is None or len(trending.snapshots) < 2:
        return

    print(_render_trending_console(trending))
    print()


def _trending_snapshots_to_dicts(trending: OrgReportTrending) -> dict[str, Any]:
    """Convert trending data to a JSON-serializable dict."""
    return {
        "window_size": trending.window_size,
        "snapshots": [
            {
                "timestamp": s.timestamp,
                "data_view_count": _snapshot_effective_data_view_count(s),
                "component_count": s.component_count,
                "core_count": s.core_count,
                "isolated_count": s.isolated_count,
                "high_sim_pair_count": s.high_sim_pair_count,
            }
            for s in trending.snapshots
        ],
        "deltas": [
            {
                "from_timestamp": d.from_timestamp,
                "to_timestamp": d.to_timestamp,
                "data_view_delta": d.data_view_delta,
                "component_delta": d.component_delta,
                "core_delta": d.core_delta,
                "isolated_delta": d.isolated_delta,
                "high_sim_pair_delta": d.high_sim_pair_delta,
            }
            for d in trending.deltas
        ],
        "drift_scores": dict(_sorted_drift_score_items(trending.drift_scores)),
        "drift_details": _ranked_drift_entries(trending),
    }


def _render_trending_markdown(trending: OrgReportTrending) -> str:
    """Render a trending section for Markdown output."""
    snapshots = trending.snapshots
    if len(snapshots) < 2:
        return ""

    lines: list[str] = []
    date_range = _trending_date_range(snapshots)
    lines.append(f"## Trending ({len(snapshots)} snapshots, {date_range})")
    lines.append("")

    # Table header
    col_labels = [_format_trending_timestamp_short(s.timestamp) for s in snapshots]
    lines.extend(_render_markdown_trending_table(col_labels, _trending_snapshot_metric_rows(snapshots)))
    lines.append("")

    if trending.deltas:
        lines.append("### Period Deltas")
        lines.append("")
        delta_labels = [label for _key, label in _trending_delta_column_specs(trending.deltas)]
        lines.extend(
            _render_markdown_trending_table(
                delta_labels,
                _trending_delta_metric_rows(trending.deltas),
                value_formatter=_format_signed_trending_value,
            )
        )

    lines.append("")

    if trending.drift_scores:
        lines.append("### Top Drift Scores")
        lines.append("")
        lines.append("| Data View ID | Data View Name | Drift Score |")
        lines.append("|--------------|----------------|------------:|")
        for entry in _ranked_drift_entries(trending, limit=10):
            dv_id = _escape_markdown_table_cell(entry["data_view_id"])
            dv_name = _escape_markdown_table_cell(entry["data_view_name"] or "")
            lines.append(f"| {dv_id} | {dv_name} | {entry['drift_score']:.2f} |")
        lines.append("")

    return "\n".join(lines)


def _render_trending_html(trending: OrgReportTrending) -> str:
    """Render a trending section for HTML output."""
    snapshots = trending.snapshots
    if len(snapshots) < 2:
        return ""

    date_range = _trending_date_range(snapshots)
    col_labels = [_format_trending_timestamp_short(s.timestamp) for s in snapshots]

    html_out = f"""
        <h2>Trending ({len(snapshots)} snapshots, {html.escape(date_range)})</h2>
"""
    html_out += _render_html_trending_table(col_labels, _trending_snapshot_metric_rows(snapshots))

    if trending.deltas:
        html_out += """
        <h3>Period Deltas</h3>
"""
        delta_labels = [label for _key, label in _trending_delta_column_specs(trending.deltas)]
        html_out += _render_html_trending_table(
            delta_labels,
            _trending_delta_metric_rows(trending.deltas),
            value_formatter=_format_signed_trending_value,
        )

    if trending.drift_scores:
        html_out += """
        <h3>Top Drift Scores</h3>
        <div class="card">
            <table>
                <thead>
                    <tr><th>Data View ID</th><th>Data View Name</th><th>Drift Score</th></tr>
                </thead>
                <tbody>
"""
        for entry in _ranked_drift_entries(trending, limit=10):
            html_out += (
                "                    <tr>"
                f"<td><code>{html.escape(entry['data_view_id'])}</code></td>"
                f"<td>{html.escape(entry['data_view_name'] or '')}</td>"
                f"<td>{entry['drift_score']:.2f}</td>"
                "</tr>\n"
            )
        html_out += """                </tbody>
            </table>
        </div>
"""

    return html_out


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


def write_org_report_console(
    result: OrgReportResult,
    config: OrgReportConfig,
    quiet: bool = False,
    trending: OrgReportTrending | None = None,
) -> None:
    """Write org report to console with ASCII distribution bars.

    Args:
        result: OrgReportResult from analysis
        config: OrgReportConfig used for analysis
        quiet: Suppress decorative output
        trending: Optional trending data to append
    """
    if quiet:
        return

    total_dvs = result.successful_data_views
    print()
    print("=" * 110)
    title = f"ORG-WIDE COMPONENT ANALYSIS REPORT: {result.org_id}"
    if result.is_sampled:
        title += " [SAMPLED]"
    print(title)
    print("=" * 110)
    print(f"Generated: {result.timestamp}")
    if result.is_sampled:
        print(
            f"Data Views Analyzed: {result.successful_data_views} / {result.total_data_views} (sampled from {result.total_available_data_views})",
        )
    else:
        print(f"Data Views Analyzed: {result.successful_data_views} / {result.total_data_views}")
    print(f"Data View Fetch Failures: {result.failed_data_views}")
    print(f"Analysis Duration: {result.duration:.2f}s")
    print()

    # Data Views Summary Table
    print("-" * 110)
    print("DATA VIEWS")
    print("-" * 110)
    print(f"{'Name':<50} {'ID':<30} {'Metrics':>8} {'Dimensions':>10} {'Status':<8}")
    print("-" * 110)

    for dv in sorted(result.data_view_summaries, key=lambda x: x.data_view_name):
        name = dv.data_view_name[:48] + ".." if len(dv.data_view_name) > 50 else dv.data_view_name
        if dv.error is not None:
            print(f"{name:<50} {dv.data_view_id:<30} {'ERROR':>8} {'':>10} {dv.status:<8}")
        else:
            print(f"{name:<50} {dv.data_view_id:<30} {dv.metric_count:>8} {dv.dimension_count:>10} {dv.status:<8}")

    print()

    # Component Summary
    print("-" * 110)
    print("COMPONENT SUMMARY")
    print("-" * 110)

    total_metrics = result.total_unique_metrics
    total_dims = result.total_unique_dimensions
    total_all = result.total_unique_components

    # Calculate total aggregates (non-unique counts across all data views)
    total_metrics_aggregate = sum(dv.metric_count for dv in result.data_view_summaries if dv.error is None)
    total_dimensions_aggregate = sum(dv.dimension_count for dv in result.data_view_summaries if dv.error is None)
    total_components_aggregate = sum(dv.total_components for dv in result.data_view_summaries if dv.error is None)
    total_derived_metrics = sum(dv.derived_metric_count for dv in result.data_view_summaries if dv.error is None)
    total_derived_dimensions = sum(dv.derived_dimension_count for dv in result.data_view_summaries if dv.error is None)
    total_derived_fields = total_derived_metrics + total_derived_dimensions

    dist = result.distribution
    # Build correct label for core threshold: "50% DVs" for percentage, ">=5 DVs" for absolute count
    if config.core_min_count is None:
        core_threshold_label = f"{int(config.core_threshold * 100)}%"
    else:
        core_threshold_label = f">={config.core_min_count}"

    print(f"{'':30} {'Metrics':>12} {'Dimensions':>12} {'Total':>10}")
    print(f"{'Total unique components':<30} {total_metrics:>12} {total_dims:>12} {total_all:>10}")
    print(
        f"{'Total (non-unique)':<30} {total_metrics_aggregate:>12} {total_dimensions_aggregate:>12} {total_components_aggregate:>10}",
    )
    print(
        f"{'Derived fields (non-unique)':<30} {total_derived_metrics:>12} {total_derived_dimensions:>12} {total_derived_fields:>10}",
    )
    # Add "+" suffix only for percentage labels; absolute labels already have ">="
    core_label_suffix = " DVs" if config.core_min_count is not None else "+ DVs"
    print(
        f"{'Core (in ' + core_threshold_label + core_label_suffix + ')':<30} {len(dist.core_metrics):>12} {len(dist.core_dimensions):>12} {dist.total_core:>10}",
    )
    print(
        f"{'Common (in 25-49% DVs)':<30} {len(dist.common_metrics):>12} {len(dist.common_dimensions):>12} {dist.total_common:>10}",
    )
    print(
        f"{'Limited (in 2+ DVs)':<30} {len(dist.limited_metrics):>12} {len(dist.limited_dimensions):>12} {dist.total_limited:>10}",
    )
    print(
        f"{'Isolated (in 1 DV only)':<30} {len(dist.isolated_metrics):>12} {len(dist.isolated_dimensions):>12} {dist.total_isolated:>10}",
    )
    print()

    # Distribution Visualization
    print("-" * 110)
    print("DISTRIBUTION")
    print("-" * 110)

    print("Metrics by data view coverage:")
    print(f"  Core:     {_render_distribution_bar(len(dist.core_metrics), total_metrics)} ({len(dist.core_metrics)})")
    print(
        f"  Common:   {_render_distribution_bar(len(dist.common_metrics), total_metrics)} ({len(dist.common_metrics)})",
    )
    print(
        f"  Limited:  {_render_distribution_bar(len(dist.limited_metrics), total_metrics)} ({len(dist.limited_metrics)})",
    )
    print(
        f"  Isolated: {_render_distribution_bar(len(dist.isolated_metrics), total_metrics)} ({len(dist.isolated_metrics)})",
    )
    print()

    print("Dimensions by data view coverage:")
    print(
        f"  Core:     {_render_distribution_bar(len(dist.core_dimensions), total_dims)} ({len(dist.core_dimensions)})",
    )
    print(
        f"  Common:   {_render_distribution_bar(len(dist.common_dimensions), total_dims)} ({len(dist.common_dimensions)})",
    )
    print(
        f"  Limited:  {_render_distribution_bar(len(dist.limited_dimensions), total_dims)} ({len(dist.limited_dimensions)})",
    )
    print(
        f"  Isolated: {_render_distribution_bar(len(dist.isolated_dimensions), total_dims)} ({len(dist.isolated_dimensions)})",
    )
    print()

    # Core Components (if not summary only)
    if not config.summary_only and dist.total_core > 0:
        print("-" * 110)
        print(f"CORE COMPONENTS (in {core_threshold_label}{core_label_suffix})")
        print("-" * 110)

        if dist.core_metrics:
            print("\nCore Metrics:")
            for comp_id in dist.core_metrics[:15]:  # Limit to 15
                info = result.component_index.get(comp_id)
                if info:
                    if info.name:
                        display = f"{info.name} ({comp_id})"
                        display = display[:55] + ".." if len(display) > 57 else display
                        print(f"  {display:<57} {info.presence_count}/{total_dvs} DVs")
                    else:
                        print(f"  {comp_id:<57} {info.presence_count}/{total_dvs} DVs")
            if len(dist.core_metrics) > 15:
                print(f"  ... and {len(dist.core_metrics) - 15} more")

        if dist.core_dimensions:
            print("\nCore Dimensions:")
            for comp_id in dist.core_dimensions[:15]:
                info = result.component_index.get(comp_id)
                if info:
                    if info.name:
                        display = f"{info.name} ({comp_id})"
                        display = display[:55] + ".." if len(display) > 57 else display
                        print(f"  {display:<57} {info.presence_count}/{total_dvs} DVs")
                    else:
                        print(f"  {comp_id:<57} {info.presence_count}/{total_dvs} DVs")
            if len(dist.core_dimensions) > 15:
                print(f"  ... and {len(dist.core_dimensions) - 15} more")
        print()

    # Similarity Matrix (if computed)
    if result.similarity_pairs:
        print("-" * 110)
        print("HIGH OVERLAP PAIRS")
        print("-" * 110)
        effective_threshold = min(config.overlap_threshold, 0.9)
        threshold_note = ""
        if config.overlap_threshold > 0.9:
            threshold_note = f" (configured {config.overlap_threshold * 100:.0f}%, capped at 90% for governance checks)"
        print(f"Pairs with >= {effective_threshold * 100:.0f}% Jaccard similarity{threshold_note}:")
        print()

        for pair in result.similarity_pairs[:10]:  # Limit to top 10
            name1 = pair.dv1_name[:25] + ".." if len(pair.dv1_name) > 27 else pair.dv1_name
            name2 = pair.dv2_name[:25] + ".." if len(pair.dv2_name) > 27 else pair.dv2_name
            print(f"  {name1:<27} <-> {name2:<27} {pair.jaccard_similarity * 100:>5.1f}%")
            print(f"  {'':27}     {'':27} ({pair.shared_count} shared)")

        if len(result.similarity_pairs) > 10:
            print(f"\n  ... and {len(result.similarity_pairs) - 10} more pairs")

        # Show drift details if enabled
        if config.include_drift:
            has_drift = any(pair.only_in_dv1 or pair.only_in_dv2 for pair in result.similarity_pairs[:5])
            if has_drift:
                print()
                print("Drift Details (top pairs):")
                for pair in result.similarity_pairs[:5]:
                    if pair.only_in_dv1 or pair.only_in_dv2:
                        print(f"\n  {pair.dv1_name} <-> {pair.dv2_name}:")
                        if pair.only_in_dv1:
                            print(f"    Only in {pair.dv1_name[:20]}: {len(pair.only_in_dv1)} components")
                            for comp_id in pair.only_in_dv1[:3]:
                                name = pair.only_in_dv1_names.get(comp_id, "") if pair.only_in_dv1_names else ""
                                display = f"{name} ({comp_id})" if name else comp_id
                                print(f"      - {display[:50]}")
                            if len(pair.only_in_dv1) > 3:
                                print(f"      ... and {len(pair.only_in_dv1) - 3} more")
                        if pair.only_in_dv2:
                            print(f"    Only in {pair.dv2_name[:20]}: {len(pair.only_in_dv2)} components")
                            for comp_id in pair.only_in_dv2[:3]:
                                name = pair.only_in_dv2_names.get(comp_id, "") if pair.only_in_dv2_names else ""
                                display = f"{name} ({comp_id})" if name else comp_id
                                print(f"      - {display[:50]}")
                            if len(pair.only_in_dv2) > 3:
                                print(f"      ... and {len(pair.only_in_dv2) - 3} more")
        print()

    # Component Type Breakdown (if enabled)
    if config.include_component_types and not config.summary_only:
        # Aggregate type counts
        total_standard_metrics = sum(s.standard_metric_count for s in result.data_view_summaries if not s.has_error)
        total_derived_metrics = sum(s.derived_metric_count for s in result.data_view_summaries if not s.has_error)
        total_standard_dims = sum(s.standard_dimension_count for s in result.data_view_summaries if not s.has_error)
        total_derived_dims = sum(s.derived_dimension_count for s in result.data_view_summaries if not s.has_error)

        if total_standard_metrics + total_derived_metrics > 0:
            print("-" * 110)
            print("COMPONENT TYPES (aggregate counts across DVs, standard vs derived field breakdown)")
            print("-" * 110)
            total_metrics = total_standard_metrics + total_derived_metrics
            total_dims = total_standard_dims + total_derived_dims
            # Calculate percentages
            std_metric_pct = (total_standard_metrics / total_metrics * 100) if total_metrics > 0 else 0
            der_metric_pct = (total_derived_metrics / total_metrics * 100) if total_metrics > 0 else 0
            std_dim_pct = (total_standard_dims / total_dims * 100) if total_dims > 0 else 0
            der_dim_pct = (total_derived_dims / total_dims * 100) if total_dims > 0 else 0
            print(f"{'':18} {'Total':>10} {'Standard':>12} {'% Total':>8} {'Derived':>10} {'% Total':>8}")
            print(
                f"{'Metrics':<18} {total_metrics:>10} {total_standard_metrics:>12} {std_metric_pct:>7.1f}% {total_derived_metrics:>10} {der_metric_pct:>7.1f}%",
            )
            print(
                f"{'Dimensions':<18} {total_dims:>10} {total_standard_dims:>12} {std_dim_pct:>7.1f}% {total_derived_dims:>10} {der_dim_pct:>7.1f}%",
            )
            print()

    # Clusters (if enabled)
    if result.clusters:
        print("-" * 110)
        print("DATA VIEW CLUSTERS")
        print("-" * 110)
        print(f"Found {len(result.clusters)} clusters:")
        print()
        for cluster in result.clusters[:10]:
            name = cluster.cluster_name or f"Cluster {cluster.cluster_id}"
            print(f"  [{cluster.cluster_id}] {name} ({cluster.size} DVs, cohesion: {cluster.cohesion_score:.0%})")
            for dv_name in cluster.data_view_names[:3]:
                print(f"      - {dv_name[:50]}")
            if cluster.size > 3:
                print(f"      ... and {cluster.size - 3} more")
        if len(result.clusters) > 10:
            print(f"\n  ... and {len(result.clusters) - 10} more clusters")
        print()

    # Governance Violations (Feature 1)
    if result.governance_violations:
        print("-" * 110)
        print("GOVERNANCE VIOLATIONS")
        print("-" * 110)
        for violation in result.governance_violations:
            print(f"\n[!] {violation.get('message', '')}")
            print(f"    Threshold: {violation.get('threshold')}, Actual: {violation.get('actual')}")
        print()

    # Owner Summary (Feature 5)
    if result.owner_summary:
        print("-" * 110)
        print("OWNER SUMMARY")
        print("-" * 110)
        owner_data = result.owner_summary.get("by_owner", {})
        sorted_owners = result.owner_summary.get("owners_sorted_by_dv_count", [])
        print(f"{'Owner':<30} {'DVs':>6} {'Metrics':>10} {'Dimensions':>12} {'Avg/DV':>8}")
        print("-" * 110)
        for owner in sorted_owners[:15]:
            stats = owner_data.get(owner, {})
            print(
                f"{owner[:30]:<30} {stats.get('data_view_count', 0):>6} "
                f"{stats.get('total_metrics', 0):>10} {stats.get('total_dimensions', 0):>12} "
                f"{stats.get('avg_components_per_dv', 0):>8.1f}",
            )
        if len(sorted_owners) > 15:
            print(f"  ... and {len(sorted_owners) - 15} more owners")
        print()

    # Naming Audit (Feature 3)
    if result.naming_audit:
        print("-" * 110)
        print("NAMING AUDIT")
        print("-" * 110)
        audit = result.naming_audit
        styles = audit.get("case_styles", {})
        print("Case styles distribution:")
        for style, count in sorted(styles.items(), key=lambda x: -x[1]):
            pct = count / audit.get("total_components", 1) * 100
            print(f"  {style:<15} {count:>6} ({pct:>5.1f}%)")
        if audit.get("recommendations"):
            print("\nNaming Recommendations:")
            for rec in audit["recommendations"]:
                print(f"  [{rec.get('severity', 'info')}] {rec.get('message', '')}")
        print()

    # Stale Components (Feature 6)
    if result.stale_components:
        print("-" * 110)
        print("STALE COMPONENTS")
        print("-" * 110)
        print(f"Found {len(result.stale_components)} components with stale naming patterns:")
        print()
        # Group by pattern type
        by_pattern: dict[str, list] = {}
        for comp in result.stale_components:
            pattern = comp.get("pattern", "unknown")
            if pattern not in by_pattern:
                by_pattern[pattern] = []
            by_pattern[pattern].append(comp)
        for pattern, comps in by_pattern.items():
            print(f"  {pattern} ({len(comps)} components):")
            for comp in comps[:5]:
                name = comp.get("name", comp.get("component_id", ""))[:50]
                print(f"    - {name}")
            if len(comps) > 5:
                print(f"    ... and {len(comps) - 5} more")
        print()

    # Recommendations
    if result.recommendations:
        print("-" * 110)
        print("RECOMMENDATIONS")
        print("-" * 110)

        for _i, rec in enumerate(result.recommendations, 1):
            severity_icon = {"high": "!", "medium": "?", "low": "i"}.get(rec.get("severity", "low"), "·")
            print(f"\n[{severity_icon}] {rec.get('reason', 'No details')}")

            if rec.get("data_view"):
                print(f"    Data View: {rec.get('data_view_name', '')} ({rec.get('data_view')})")
            if rec.get("data_view_1"):
                print(f"    Pair: {rec.get('data_view_1_name', '')} <-> {rec.get('data_view_2_name', '')}")

        print()

    # Trending section (v3.4.0)
    _print_trending_console_section(trending)


def write_org_report_stats_only(
    result: OrgReportResult,
    quiet: bool = False,
    trending: OrgReportTrending | None = None,
) -> None:
    """Write minimal org-report stats to console (Feature 2: --org-stats mode).

    Args:
        result: OrgReportResult from analysis
        quiet: Suppress output
        trending: Optional trending window to append after the stats summary
    """
    if quiet:
        return

    print()
    print("=" * BANNER_WIDTH)
    print(f"ORG STATS: {result.org_id}")
    print("=" * BANNER_WIDTH)
    print(f"Data Views: {result.successful_data_views} analyzed")
    print(f"Fetch Failures: {result.failed_data_views}")
    print(f"Components: {result.total_unique_components} unique")
    print(f"  Metrics:    {result.total_unique_metrics}")
    print(f"  Dimensions: {result.total_unique_dimensions}")
    print("Distribution:")
    dist = result.distribution
    total = result.total_unique_components or 1
    print(f"  Core:     {dist.total_core:>6} ({dist.total_core / total * 100:>5.1f}%)")
    print(f"  Common:   {dist.total_common:>6} ({dist.total_common / total * 100:>5.1f}%)")
    print(f"  Limited:  {dist.total_limited:>6} ({dist.total_limited / total * 100:>5.1f}%)")
    print(f"  Isolated: {dist.total_isolated:>6} ({dist.total_isolated / total * 100:>5.1f}%)")
    print(f"Duration: {result.duration:.2f}s")
    print("=" * BANNER_WIDTH)
    print()

    _print_trending_console_section(trending)


def write_org_report_comparison_console(comparison: OrgReportComparison, quiet: bool = False) -> None:
    """Write org-report comparison to console with trending arrows (Feature 4).

    Args:
        comparison: OrgReportComparison from compare_org_reports()
        quiet: Suppress output
    """
    if quiet:
        return

    def trend_arrow(delta: int) -> str:
        if delta > 0:
            return f"↑{delta}"
        if delta < 0:
            return f"↓{abs(delta)}"
        return "→0"

    print()
    print("=" * 70)
    print("ORG REPORT COMPARISON (TRENDING)")
    print("=" * 70)
    print(f"Previous: {comparison.previous_timestamp}")
    print(f"Current:  {comparison.current_timestamp}")
    print()

    summary = comparison.summary
    print("-" * 70)
    print("CHANGES")
    print("-" * 70)
    print(f"Data Views:  {trend_arrow(summary.get('data_views_delta', 0))}")
    print(f"Components:  {trend_arrow(summary.get('components_delta', 0))}")
    print(f"Core:        {trend_arrow(summary.get('core_delta', 0))}")
    print(f"Isolated:    {trend_arrow(summary.get('isolated_delta', 0))}")
    print()

    if comparison.data_views_added:
        print(f"Data Views Added ({len(comparison.data_views_added)}):")
        for _i, dv_name in enumerate(comparison.data_views_added_names[:5]):
            print(f"  + {dv_name}")
        if len(comparison.data_views_added) > 5:
            print(f"  ... and {len(comparison.data_views_added) - 5} more")

    if comparison.data_views_removed:
        print(f"Data Views Removed ({len(comparison.data_views_removed)}):")
        for dv_name in comparison.data_views_removed_names[:5]:
            print(f"  - {dv_name}")
        if len(comparison.data_views_removed) > 5:
            print(f"  ... and {len(comparison.data_views_removed) - 5} more")

    if comparison.new_high_similarity_pairs:
        print(f"\nNew High-Similarity Pairs ({len(comparison.new_high_similarity_pairs)}):")
        for pair in comparison.new_high_similarity_pairs[:3]:
            print(f"  ! {pair.get('dv1_id', '')} <-> {pair.get('dv2_id', '')}")

    if comparison.resolved_pairs:
        print(f"\nResolved High-Similarity Pairs ({len(comparison.resolved_pairs)}):")
        for pair in comparison.resolved_pairs[:3]:
            print(f"  ✓ {pair.get('dv1_id', '')} <-> {pair.get('dv2_id', '')}")

    print()
    print("=" * 70)
    print()


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
            context_entries.append(("Pair", f"{pair_left} ↔ {pair_right}"))
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


def build_org_report_json_data(
    result: OrgReportResult,
    trending: OrgReportTrending | None = None,
) -> dict[str, Any]:
    """Build org report JSON payload."""
    effective_overlap_threshold = min(result.parameters.overlap_threshold, 0.9)
    similarity_analysis_complete = result.similarity_pairs is not None
    if result.parameters.org_stats_only:
        similarity_analysis_mode = "org_stats_only"
    elif result.parameters.skip_similarity:
        similarity_analysis_mode = "skip_similarity"
    elif similarity_analysis_complete:
        similarity_analysis_mode = "complete"
    else:
        similarity_analysis_mode = "runtime_skipped"

    data: dict[str, Any] = {
        "report_type": "org_analysis",
        "version": "1.0",
        "generated_at": result.timestamp,
        "org_id": result.org_id,
        "parameters": {
            "filter_pattern": result.parameters.filter_pattern,
            "exclude_pattern": result.parameters.exclude_pattern,
            "limit": result.parameters.limit,
            "core_threshold": result.parameters.core_threshold,
            "core_min_count": result.parameters.core_min_count,
            "overlap_threshold": result.parameters.overlap_threshold,
            "overlap_threshold_effective": effective_overlap_threshold,
            "include_component_types": result.parameters.include_component_types,
            "include_metadata": result.parameters.include_metadata,
            "include_drift": result.parameters.include_drift,
            "skip_similarity": result.parameters.skip_similarity,
            "sample_size": result.parameters.sample_size,
            "sample_seed": result.parameters.sample_seed,
            "enable_clustering": result.parameters.enable_clustering,
            "similarity_max_dvs": result.parameters.similarity_max_dvs,
            "force_similarity": result.parameters.force_similarity,
            "org_stats_only": result.parameters.org_stats_only,
        },
        "summary": {
            "data_views_total": result.total_data_views,
            "data_views_analyzed": result.successful_data_views,
            "data_views_failed": result.failed_data_views,
            "total_available_data_views": result.total_available_data_views,
            "is_sampled": result.is_sampled,
            "similarity_analysis_complete": similarity_analysis_complete,
            "similarity_analysis_mode": similarity_analysis_mode,
            "total_unique_metrics": result.total_unique_metrics,
            "total_unique_dimensions": result.total_unique_dimensions,
            "total_unique_components": result.total_unique_components,
            "total_metrics_non_unique": sum(dv.metric_count for dv in result.data_view_summaries if dv.error is None),
            "total_dimensions_non_unique": sum(
                dv.dimension_count for dv in result.data_view_summaries if dv.error is None
            ),
            "total_components_non_unique": sum(
                dv.total_components for dv in result.data_view_summaries if dv.error is None
            ),
            "derived_metrics_non_unique": sum(
                dv.derived_metric_count for dv in result.data_view_summaries if dv.error is None
            ),
            "derived_dimensions_non_unique": sum(
                dv.derived_dimension_count for dv in result.data_view_summaries if dv.error is None
            ),
            "total_derived_fields_non_unique": sum(
                dv.derived_metric_count + dv.derived_dimension_count
                for dv in result.data_view_summaries
                if dv.error is None
            ),
            "analysis_duration_seconds": round(result.duration, 2),
        },
        "data_view_fetch_failures": {
            "count": result.failed_data_views,
            "data_view_ids": result.failed_data_view_ids,
            "failure_reason_counts": result.failed_data_view_reason_counts,
        },
        "distribution": {
            "core": {
                "metrics_count": len(result.distribution.core_metrics),
                "dimensions_count": len(result.distribution.core_dimensions),
                "metrics": sorted(result.distribution.core_metrics),
                "dimensions": sorted(result.distribution.core_dimensions),
            },
            "common": {
                "metrics_count": len(result.distribution.common_metrics),
                "dimensions_count": len(result.distribution.common_dimensions),
                "metrics": sorted(result.distribution.common_metrics),
                "dimensions": sorted(result.distribution.common_dimensions),
            },
            "limited": {
                "metrics_count": len(result.distribution.limited_metrics),
                "dimensions_count": len(result.distribution.limited_dimensions),
                "metrics": sorted(result.distribution.limited_metrics),
                "dimensions": sorted(result.distribution.limited_dimensions),
            },
            "isolated": {
                "metrics_count": len(result.distribution.isolated_metrics),
                "dimensions_count": len(result.distribution.isolated_dimensions),
                "metrics": sorted(result.distribution.isolated_metrics),
                "dimensions": sorted(result.distribution.isolated_dimensions),
            },
        },
        "data_views": [
            {
                "id": dv.data_view_id,
                "name": dv.data_view_name,
                "metrics_count": dv.metric_count,
                "dimensions_count": dv.dimension_count,
                "total_components": dv.total_components,
                "status": dv.status,
                "error": dv.normalized_error_reason if dv.has_error else None,
                # Component type breakdown
                "standard_metrics": dv.standard_metric_count,
                "derived_metrics": dv.derived_metric_count,
                "standard_dimensions": dv.standard_dimension_count,
                "derived_dimensions": dv.derived_dimension_count,
                # Metadata
                "owner": dv.owner,
                "owner_id": dv.owner_id,
                "created": dv.created,
                "modified": dv.modified,
                "description": dv.description,
                "has_description": dv.has_description,
            }
            for dv in result.data_view_summaries
        ],
        "component_index": {
            comp_id: {
                "type": info.component_type,
                "name": info.name,
                "data_view_count": info.presence_count,
                "data_views": sorted_snapshot_strings(info.data_views),
            }
            for comp_id, info in sorted(result.component_index.items())
        },
        "similarity_pairs": [
            {
                "data_view_1": {"id": pair.dv1_id, "name": pair.dv1_name},
                "data_view_2": {"id": pair.dv2_id, "name": pair.dv2_name},
                "jaccard_similarity": pair.jaccard_similarity,
                "shared_components": pair.shared_count,
                "union_size": pair.union_count,
                # Drift detection
                "only_in_dv1": pair.only_in_dv1,
                "only_in_dv2": pair.only_in_dv2,
                "only_in_dv1_names": pair.only_in_dv1_names,
                "only_in_dv2_names": pair.only_in_dv2_names,
            }
            for pair in (result.similarity_pairs or [])
        ],
        "clusters": [
            {
                "cluster_id": cluster.cluster_id,
                "cluster_name": cluster.cluster_name,
                "data_view_ids": cluster.data_view_ids,
                "data_view_names": cluster.data_view_names,
                "size": cluster.size,
                "cohesion_score": cluster.cohesion_score,
            }
            for cluster in (result.clusters or [])
        ]
        if result.clusters
        else None,
        "recommendations": [_normalize_recommendation_for_json(rec) for rec in result.recommendations],
        # New features
        "governance_violations": result.governance_violations,
        "thresholds_exceeded": result.thresholds_exceeded,
        "naming_audit": result.naming_audit,
        "owner_summary": result.owner_summary,
        "stale_components": result.stale_components,
    }
    if trending is not None and len(trending.snapshots) >= 2:
        data["trending"] = _trending_snapshots_to_dicts(trending)
    return data


def write_org_report_json(
    result: OrgReportResult,
    output_path: Path | None,
    output_dir: str,
    logger: logging.Logger,
    trending: OrgReportTrending | None = None,
) -> str:
    """Write org report as structured JSON.

    Args:
        result: OrgReportResult from analysis
        output_path: Optional specific output path
        output_dir: Output directory if no path specified
        logger: Logger instance
        trending: Optional trending data to include

    Returns:
        Path to created JSON file
    """
    if output_path:
        file_path = output_path if str(output_path).endswith(".json") else Path(f"{output_path}.json")
    else:
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        file_path = Path(output_dir) / f"org_report_{result.org_id}_{timestamp}.json"

    json_data = build_org_report_json_data(result, trending=trending)

    # Write JSON
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    logger.info(f"JSON report written to {file_path}")
    return str(file_path)


def write_org_report_excel(
    result: OrgReportResult,
    output_path: Path | None,
    output_dir: str,
    logger: logging.Logger,
    trending: OrgReportTrending | None = None,
) -> str:
    """Write org report as multi-sheet Excel workbook.

    Sheets:
    - Summary: Overview statistics
    - Data Views: List of all analyzed data views
    - Core Components: Components in threshold% of DVs
    - Distribution: Component distribution breakdown
    - Similarity: High-overlap pairs
    - Recommendations: Actionable items
    - Trending: Multi-snapshot trending data (if provided)

    Args:
        result: OrgReportResult from analysis
        output_path: Optional specific output path
        output_dir: Output directory if no path specified
        logger: Logger instance
        trending: Optional trending data to include

    Returns:
        Path to created Excel file
    """
    if output_path:
        file_path = output_path if str(output_path).endswith(".xlsx") else Path(f"{output_path}.xlsx")
    else:
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        file_path = Path(output_dir) / f"org_report_{result.org_id}_{timestamp}.xlsx"

    file_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(file_path, engine="xlsxwriter") as writer:
        # Sheet 1: Summary
        # Calculate total aggregates (non-unique counts across all data views)
        total_metrics_aggregate = sum(dv.metric_count for dv in result.data_view_summaries if dv.error is None)
        total_dimensions_aggregate = sum(dv.dimension_count for dv in result.data_view_summaries if dv.error is None)
        total_components_aggregate = sum(dv.total_components for dv in result.data_view_summaries if dv.error is None)
        total_derived_metrics = sum(dv.derived_metric_count for dv in result.data_view_summaries if dv.error is None)
        total_derived_dimensions = sum(
            dv.derived_dimension_count for dv in result.data_view_summaries if dv.error is None
        )
        total_derived_fields = total_derived_metrics + total_derived_dimensions
        effective_overlap_threshold = min(result.parameters.overlap_threshold, 0.9)

        metrics = [
            "Organization ID",
            "Report Generated",
            "Data Views Total",
            "Data Views Analyzed",
            "Total Unique Metrics",
            "Total Unique Dimensions",
            "Total Unique Components",
            "Total Metrics (Non-Unique)",
            "Total Dimensions (Non-Unique)",
            "Total Components (Non-Unique)",
            "Derived Metrics (Non-Unique)",
            "Derived Dimensions (Non-Unique)",
            "Total Derived Fields (Non-Unique)",
            "Core Components",
            "Common Components",
            "Limited Components",
            "Isolated Components",
            "Overlap Threshold (Configured)",
            "Overlap Threshold (Effective)",
            "Analysis Duration (seconds)",
        ]
        values = [
            result.org_id,
            result.timestamp,
            result.total_data_views,
            result.successful_data_views,
            result.total_unique_metrics,
            result.total_unique_dimensions,
            result.total_unique_components,
            total_metrics_aggregate,
            total_dimensions_aggregate,
            total_components_aggregate,
            total_derived_metrics,
            total_derived_dimensions,
            total_derived_fields,
            result.distribution.total_core,
            result.distribution.total_common,
            result.distribution.total_limited,
            result.distribution.total_isolated,
            result.parameters.overlap_threshold,
            effective_overlap_threshold,
            round(result.duration, 2),
        ]
        # Add sampling info
        if result.is_sampled:
            metrics.extend(["Is Sampled", "Total Available DVs", "Sample Seed"])
            values.extend(["Yes", result.total_available_data_views, result.parameters.sample_seed])
        # Add clustering info
        if result.clusters:
            metrics.append("Cluster Count")
            values.append(len(result.clusters))
        summary_data = {"Metric": metrics, "Value": values}
        summary_df = pd.DataFrame(summary_data)
        summary_df.to_excel(writer, sheet_name="Summary", index=False)

        worksheet = writer.sheets["Summary"]
        worksheet.set_column("A:A", 30)
        worksheet.set_column("B:B", 25)

        # Sheet 2: Data Views
        dv_data = []
        for dv in result.data_view_summaries:
            row = {
                "ID": dv.data_view_id,
                "Name": dv.data_view_name,
                "Metrics": dv.metric_count,
                "Dimensions": dv.dimension_count,
                "Total": dv.total_components,
                "Status": dv.status,
                "Error": dv.normalized_error_reason if dv.has_error else "",
            }
            # Add component type columns if enabled
            if result.parameters.include_component_types:
                row["Standard Metrics"] = dv.standard_metric_count
                row["Derived Metrics"] = dv.derived_metric_count
                row["Standard Dimensions"] = dv.standard_dimension_count
                row["Derived Dimensions"] = dv.derived_dimension_count
            # Add metadata columns if enabled
            if result.parameters.include_metadata:
                row["Owner"] = dv.owner or ""
                row["Created"] = dv.created or ""
                row["Modified"] = dv.modified or ""
                row["Has Description"] = "Yes" if dv.has_description else "No"
            dv_data.append(row)
        dv_df = pd.DataFrame(dv_data)
        dv_df.to_excel(writer, sheet_name="Data Views", index=False)

        worksheet = writer.sheets["Data Views"]
        worksheet.set_column("A:A", 20)
        worksheet.set_column("B:B", 40)
        worksheet.set_column("C:G", 12)
        if result.parameters.include_component_types:
            worksheet.set_column("H:K", 18)  # 4 columns: Standard/Derived Metrics/Dimensions
        if result.parameters.include_metadata:
            worksheet.set_column("L:O", 18)

        # Sheet 3: Core Components
        core_data = []
        for comp_id in result.distribution.core_metrics:
            info = result.component_index.get(comp_id)
            if info:
                core_data.append(
                    {
                        "Component ID": comp_id,
                        "Type": "Metric",
                        "Name": info.name or "",
                        "Data View Count": info.presence_count,
                        "Coverage %": info.presence_count / result.successful_data_views
                        if result.successful_data_views > 0
                        else 0,
                    },
                )
        for comp_id in result.distribution.core_dimensions:
            info = result.component_index.get(comp_id)
            if info:
                core_data.append(
                    {
                        "Component ID": comp_id,
                        "Type": "Dimension",
                        "Name": info.name or "",
                        "Data View Count": info.presence_count,
                        "Coverage %": info.presence_count / result.successful_data_views
                        if result.successful_data_views > 0
                        else 0,
                    },
                )

        if core_data:
            core_df = pd.DataFrame(core_data)
            core_df.to_excel(writer, sheet_name="Core Components", index=False)
            worksheet = writer.sheets["Core Components"]
            worksheet.set_column("A:A", 40)
            worksheet.set_column("B:B", 12)
            worksheet.set_column("C:C", 30)
            worksheet.set_column("D:E", 15)

        # Sheet 4: Isolated by Data View
        isolated_data = []
        for dv in result.data_view_summaries:
            if dv.error is not None:
                continue
            isolated_metrics = [
                c
                for c in result.distribution.isolated_metrics
                if dv.data_view_id in result.component_index.get(c, ComponentInfo("", "")).data_views
            ]
            isolated_dims = [
                c
                for c in result.distribution.isolated_dimensions
                if dv.data_view_id in result.component_index.get(c, ComponentInfo("", "")).data_views
            ]
            if isolated_metrics or isolated_dims:
                isolated_data.append(
                    {
                        "Data View ID": dv.data_view_id,
                        "Data View Name": dv.data_view_name,
                        "Isolated Metrics": len(isolated_metrics),
                        "Isolated Dimensions": len(isolated_dims),
                        "Total Isolated": len(isolated_metrics) + len(isolated_dims),
                    },
                )

        if isolated_data:
            isolated_df = pd.DataFrame(isolated_data)
            isolated_df = isolated_df.sort_values("Total Isolated", ascending=False)
            isolated_df.to_excel(writer, sheet_name="Isolated by DV", index=False)
            worksheet = writer.sheets["Isolated by DV"]
            worksheet.set_column("A:A", 20)
            worksheet.set_column("B:B", 40)
            worksheet.set_column("C:E", 18)

        # Sheet 5: Similarity Matrix
        if result.similarity_pairs:
            sim_data = []
            for pair in result.similarity_pairs:
                row = {
                    "Data View 1 ID": pair.dv1_id,
                    "Data View 1 Name": pair.dv1_name,
                    "Data View 2 ID": pair.dv2_id,
                    "Data View 2 Name": pair.dv2_name,
                    "Similarity %": pair.jaccard_similarity,
                    "Shared Components": pair.shared_count,
                    "Union Size": pair.union_count,
                }
                if result.parameters.include_drift:
                    row["Only in DV1"] = len(pair.only_in_dv1)
                    row["Only in DV2"] = len(pair.only_in_dv2)
                    row["Drift Total"] = len(pair.only_in_dv1) + len(pair.only_in_dv2)
                sim_data.append(row)
            sim_df = pd.DataFrame(sim_data)
            sim_df.to_excel(writer, sheet_name="Similarity", index=False)
            worksheet = writer.sheets["Similarity"]
            worksheet.set_column("A:A", 20)
            worksheet.set_column("B:B", 35)
            worksheet.set_column("C:C", 20)
            worksheet.set_column("D:D", 35)
            worksheet.set_column("E:J", 15)

        # Sheet 5b: Drift Details (if enabled)
        if result.parameters.include_drift and result.similarity_pairs:
            drift_data = []
            for pair in result.similarity_pairs:
                if pair.only_in_dv1 or pair.only_in_dv2:
                    for comp_id in pair.only_in_dv1:
                        name = pair.only_in_dv1_names.get(comp_id, "") if pair.only_in_dv1_names else ""
                        drift_data.append(
                            {
                                "DV1 ID": pair.dv1_id,
                                "DV1 Name": pair.dv1_name,
                                "DV2 ID": pair.dv2_id,
                                "DV2 Name": pair.dv2_name,
                                "Component ID": comp_id,
                                "Component Name": name,
                                "Location": f"Only in {pair.dv1_name}",
                            },
                        )
                    for comp_id in pair.only_in_dv2:
                        name = pair.only_in_dv2_names.get(comp_id, "") if pair.only_in_dv2_names else ""
                        drift_data.append(
                            {
                                "DV1 ID": pair.dv1_id,
                                "DV1 Name": pair.dv1_name,
                                "DV2 ID": pair.dv2_id,
                                "DV2 Name": pair.dv2_name,
                                "Component ID": comp_id,
                                "Component Name": name,
                                "Location": f"Only in {pair.dv2_name}",
                            },
                        )
            if drift_data:
                drift_df = pd.DataFrame(drift_data)
                drift_df.to_excel(writer, sheet_name="Drift Details", index=False)
                worksheet = writer.sheets["Drift Details"]
                worksheet.set_column("A:A", 20)
                worksheet.set_column("B:B", 30)
                worksheet.set_column("C:C", 20)
                worksheet.set_column("D:D", 30)
                worksheet.set_column("E:E", 40)
                worksheet.set_column("F:F", 30)
                worksheet.set_column("G:G", 25)

        # Sheet 5c: Clusters (if enabled)
        if result.clusters:
            cluster_data = []
            for cluster in result.clusters:
                cluster_data.extend(
                    {
                        "Cluster ID": cluster.cluster_id,
                        "Cluster Name": cluster.cluster_name or f"Cluster {cluster.cluster_id}",
                        "Cluster Size": cluster.size,
                        "Cohesion": cluster.cohesion_score,
                        "Data View ID": dv_id,
                        "Data View Name": dv_name,
                    }
                    for dv_id, dv_name in zip(cluster.data_view_ids, cluster.data_view_names, strict=True)
                )
            if cluster_data:
                cluster_df = pd.DataFrame(cluster_data)
                cluster_df.to_excel(writer, sheet_name="Clusters", index=False)
                worksheet = writer.sheets["Clusters"]
                worksheet.set_column("A:A", 12)
                worksheet.set_column("B:B", 25)
                worksheet.set_column("C:C", 12)
                worksheet.set_column("D:D", 12)
                worksheet.set_column("E:E", 20)
                worksheet.set_column("F:F", 40)

        # Sheet 6: Recommendations
        if result.recommendations:
            rec_data = [
                _flatten_recommendation_for_tabular(_normalize_recommendation_for_json(rec))
                for rec in result.recommendations
            ]
            rec_df = pd.DataFrame(rec_data)
            rec_df.to_excel(writer, sheet_name="Recommendations", index=False)
            worksheet = writer.sheets["Recommendations"]
            worksheet.set_column("A:B", 20)
            worksheet.set_column("C:C", 60)
            worksheet.set_column("D:I", 24)
            worksheet.set_column("J:Q", 14)
            worksheet.set_column("R:R", 40)

        # Sheet 7: Trending (v3.4.0)
        if trending is not None and len(trending.snapshots) >= 2:
            snapshots = trending.snapshots
            snapshot_column_specs = _trending_snapshot_column_specs(snapshots)
            snapshot_rows = _trending_matrix_rows(snapshot_column_specs, _trending_snapshot_metric_rows(snapshots))
            trending_df = pd.DataFrame(snapshot_rows)
            trending_df.to_excel(writer, sheet_name="Trending", index=False)
            worksheet = writer.sheets["Trending"]
            worksheet.set_column("A:A", 20)
            for col_idx, (_key, display_label) in enumerate(snapshot_column_specs, start=1):
                worksheet.write(0, col_idx, display_label)
                worksheet.set_column(col_idx, col_idx, 14)

            worksheet.conditional_format(
                1,
                1,
                len(snapshot_rows),
                len(snapshot_column_specs),
                {
                    "type": "3_color_scale",
                    "min_color": "#F4CCCC",
                    "mid_color": "#FFF2CC",
                    "max_color": "#D9EAD3",
                },
            )

            next_start_row = len(snapshot_rows) + 2

            if trending.deltas:
                delta_column_specs = _trending_delta_column_specs(trending.deltas)
                delta_rows = _trending_matrix_rows(delta_column_specs, _trending_delta_metric_rows(trending.deltas))
                worksheet.write(next_start_row, 0, "Period Deltas")
                delta_df = pd.DataFrame(delta_rows)
                delta_df.to_excel(writer, sheet_name="Trending", index=False, startrow=next_start_row + 1)
                for col_idx, (_key, display_label) in enumerate(delta_column_specs, start=1):
                    worksheet.write(next_start_row + 1, col_idx, display_label)
                    worksheet.set_column(col_idx, col_idx, max(14, len(display_label) + 2))
                worksheet.conditional_format(
                    next_start_row + 2,
                    1,
                    next_start_row + 1 + len(delta_rows),
                    len(delta_column_specs),
                    {
                        "type": "3_color_scale",
                        "min_color": "#F4CCCC",
                        "mid_color": "#FFF2CC",
                        "max_color": "#D9EAD3",
                    },
                )
                next_start_row += len(delta_rows) + 4

            if trending.drift_scores:
                worksheet.write(next_start_row, 0, "Drift Scores")
                drift_start_row = next_start_row + 1
                drift_data = [
                    {
                        "Data View ID": entry["data_view_id"],
                        "Data View Name": entry["data_view_name"] or "",
                        "Drift Score": entry["drift_score"],
                    }
                    for entry in _ranked_drift_entries(trending)
                ]
                drift_df = pd.DataFrame(drift_data)
                drift_df.to_excel(writer, sheet_name="Trending", index=False, startrow=drift_start_row)
                worksheet.conditional_format(
                    drift_start_row + 1,
                    2,
                    drift_start_row + len(drift_data),
                    2,
                    {
                        "type": "data_bar",
                        "bar_color": "#6D9EEB",
                    },
                )

    logger.info(f"Excel report written to {file_path}")
    return str(file_path)


def write_org_report_markdown(
    result: OrgReportResult,
    output_path: Path | None,
    output_dir: str,
    logger: logging.Logger,
    trending: OrgReportTrending | None = None,
) -> str:
    """Write org report as GitHub-flavored markdown.

    Args:
        result: OrgReportResult from analysis
        output_path: Optional specific output path
        output_dir: Output directory if no path specified
        logger: Logger instance
        trending: Optional trending data to append

    Returns:
        Path to created Markdown file
    """
    if output_path:
        file_path = output_path if str(output_path).endswith(".md") else Path(f"{output_path}.md")
    else:
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        file_path = Path(output_dir) / f"org_report_{result.org_id}_{timestamp}.md"

    file_path.parent.mkdir(parents=True, exist_ok=True)

    lines = []

    # Header
    lines.append(f"# Org-Wide Component Analysis Report: {result.org_id}")
    lines.append("")
    lines.append(f"**Organization:** {result.org_id}")
    lines.append(f"**Generated:** {result.timestamp}")
    lines.append("")

    # Summary Table
    # Calculate total aggregates (non-unique counts across all data views)
    total_metrics_aggregate = sum(dv.metric_count for dv in result.data_view_summaries if dv.error is None)
    total_dimensions_aggregate = sum(dv.dimension_count for dv in result.data_view_summaries if dv.error is None)
    total_components_aggregate = sum(dv.total_components for dv in result.data_view_summaries if dv.error is None)
    total_derived_metrics = sum(dv.derived_metric_count for dv in result.data_view_summaries if dv.error is None)
    total_derived_dimensions = sum(dv.derived_dimension_count for dv in result.data_view_summaries if dv.error is None)
    total_derived_fields = total_derived_metrics + total_derived_dimensions

    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Data Views Analyzed | {result.successful_data_views} / {result.total_data_views} |")
    lines.append(f"| Data View Fetch Failures | {result.failed_data_views} |")
    lines.append(f"| Total Unique Metrics | {result.total_unique_metrics:,} |")
    lines.append(f"| Total Unique Dimensions | {result.total_unique_dimensions:,} |")
    lines.append(f"| Total Unique Components | {result.total_unique_components:,} |")
    lines.append(f"| Total Metrics (Non-Unique) | {total_metrics_aggregate:,} |")
    lines.append(f"| Total Dimensions (Non-Unique) | {total_dimensions_aggregate:,} |")
    lines.append(f"| Total Components (Non-Unique) | {total_components_aggregate:,} |")
    lines.append(f"| Derived Metrics (Non-Unique) | {total_derived_metrics:,} |")
    lines.append(f"| Derived Dimensions (Non-Unique) | {total_derived_dimensions:,} |")
    lines.append(f"| Total Derived Fields (Non-Unique) | {total_derived_fields:,} |")
    lines.append(f"| Analysis Duration | {result.duration:.2f}s |")
    lines.append("")

    # Distribution
    lines.append("## Component Distribution")
    lines.append("")
    lines.append("| Category | Metrics | Dimensions | Total |")
    lines.append("|----------|--------:|----------:|------:|")

    dist = result.distribution
    # Build correct label for core threshold
    if result.parameters.core_min_count is None:
        core_label = f"{int(result.parameters.core_threshold * 100)}%+"
        core_desc = f"{int(result.parameters.core_threshold * 100)}% or more of"
    else:
        core_label = f">={result.parameters.core_min_count}"
        core_desc = f"{result.parameters.core_min_count} or more"

    lines.append(
        f"| Core ({core_label} DVs) | {len(dist.core_metrics)} | {len(dist.core_dimensions)} | {dist.total_core} |",
    )
    lines.append(
        f"| Common (25-49% DVs) | {len(dist.common_metrics)} | {len(dist.common_dimensions)} | {dist.total_common} |",
    )
    lines.append(
        f"| Limited (2+ DVs) | {len(dist.limited_metrics)} | {len(dist.limited_dimensions)} | {dist.total_limited} |",
    )
    lines.append(
        f"| Isolated (1 DV only) | {len(dist.isolated_metrics)} | {len(dist.isolated_dimensions)} | {dist.total_isolated} |",
    )
    lines.append("")

    # Data Views Table
    lines.append("## Data Views")
    lines.append("")
    lines.append("| Name | ID | Metrics | Dimensions | Status |")
    lines.append("|------|----|---------:|----------:|--------|")

    for dv in sorted(result.data_view_summaries, key=lambda x: x.data_view_name):
        name = dv.data_view_name.replace("|", "\\|")
        if dv.error is not None:
            lines.append(f"| {name} | `{dv.data_view_id}` | ERROR | - | {dv.status} |")
        else:
            lines.append(f"| {name} | `{dv.data_view_id}` | {dv.metric_count} | {dv.dimension_count} | {dv.status} |")
    lines.append("")

    # Core Components
    if dist.total_core > 0:
        lines.append("## Core Components")
        lines.append("")
        lines.append(f"Components present in {core_desc} data views.")
        lines.append("")

        # Check if any components have names
        has_names = any(info.name for info in result.component_index.values())

        if dist.core_metrics:
            lines.append("### Core Metrics")
            lines.append("")
            if has_names:
                lines.append("| Component ID | Name | Data View Count |")
                lines.append("|--------------|------|----------------:|")
            else:
                lines.append("| Component ID | Data View Count |")
                lines.append("|--------------|----------------:|")
            for comp_id in dist.core_metrics[:20]:
                info = result.component_index.get(comp_id)
                if info:
                    if has_names:
                        name = (info.name or "-").replace("|", "\\|")
                        lines.append(f"| `{comp_id}` | {name} | {info.presence_count} |")
                    else:
                        lines.append(f"| `{comp_id}` | {info.presence_count} |")
            if len(dist.core_metrics) > 20:
                if has_names:
                    lines.append(f"| *... {len(dist.core_metrics) - 20} more* | | |")
                else:
                    lines.append(f"| *... {len(dist.core_metrics) - 20} more* | |")
            lines.append("")

        if dist.core_dimensions:
            lines.append("### Core Dimensions")
            lines.append("")
            if has_names:
                lines.append("| Component ID | Name | Data View Count |")
                lines.append("|--------------|------|----------------:|")
            else:
                lines.append("| Component ID | Data View Count |")
                lines.append("|--------------|----------------:|")
            for comp_id in dist.core_dimensions[:20]:
                info = result.component_index.get(comp_id)
                if info:
                    if has_names:
                        name = (info.name or "-").replace("|", "\\|")
                        lines.append(f"| `{comp_id}` | {name} | {info.presence_count} |")
                    else:
                        lines.append(f"| `{comp_id}` | {info.presence_count} |")
            if len(dist.core_dimensions) > 20:
                if has_names:
                    lines.append(f"| *... {len(dist.core_dimensions) - 20} more* | | |")
                else:
                    lines.append(f"| *... {len(dist.core_dimensions) - 20} more* | |")
            lines.append("")

    # Similarity Matrix
    if result.similarity_pairs:
        lines.append("## High Overlap Pairs")
        lines.append("")
        effective_threshold = min(result.parameters.overlap_threshold, 0.9)
        threshold_note = ""
        if result.parameters.overlap_threshold > 0.9:
            threshold_note = (
                f" (configured {int(result.parameters.overlap_threshold * 100)}%, capped at 90% for governance checks)"
            )
        lines.append(f"Data view pairs with >= {int(effective_threshold * 100)}% Jaccard similarity{threshold_note}.")
        lines.append("")
        lines.append("| Data View 1 | Data View 2 | Similarity | Shared |")
        lines.append("|-------------|-------------|------------|-------:|")

        for pair in result.similarity_pairs[:15]:
            name1 = pair.dv1_name.replace("|", "\\|")
            name2 = pair.dv2_name.replace("|", "\\|")
            lines.append(f"| {name1} | {name2} | {pair.jaccard_similarity * 100:.1f}% | {pair.shared_count} |")

        if len(result.similarity_pairs) > 15:
            lines.append(f"| *... {len(result.similarity_pairs) - 15} more pairs* | | | |")
        lines.append("")

    # Recommendations
    if result.recommendations:
        lines.append("## Recommendations")
        lines.append("")

        for i, raw_rec in enumerate(result.recommendations, 1):
            rec = _normalize_recommendation_for_json(raw_rec)
            severity = rec.get("severity", "low")
            severity_badge = {"high": "\U0001f534", "medium": "\U0001f7e1", "low": "\U0001f535"}.get(severity, "\u26aa")
            rec_type = str(rec.get("type", "Unknown")).replace("_", " ").title()
            lines.append(f"### {i}. {severity_badge} {rec_type}")
            lines.append("")
            reason = str(rec.get("reason", "No details provided.")).replace("|", "\\|").replace("`", "\\`")
            lines.append(reason)
            lines.append("")

            for label, value in _format_recommendation_context_entries(rec):
                value_text = str(value).replace("|", "\\|").replace("`", "\\`")
                lines.append(f"- **{label}:** {value_text}")
            lines.append("")

    # Trending section (v3.4.0)
    if trending is not None and len(trending.snapshots) >= 2:
        lines.append(_render_trending_markdown(trending))

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(f"*Report generated by CJA SDR Generator v{__version__}*")

    # Write file
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info(f"Markdown report written to {file_path}")
    return str(file_path)


def write_org_report_html(
    result: OrgReportResult,
    output_path: Path | None,
    output_dir: str,
    logger: logging.Logger,
    trending: OrgReportTrending | None = None,
) -> str:
    """Write org report as styled HTML.

    Args:
        result: OrgReportResult from analysis
        output_path: Optional specific output path
        output_dir: Output directory if no path specified
        logger: Logger instance
        trending: Optional trending data to append

    Returns:
        Path to created HTML file
    """
    if output_path:
        file_path = output_path if str(output_path).endswith(".html") else Path(f"{output_path}.html")
    else:
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        file_path = Path(output_dir) / f"org_report_{result.org_id}_{timestamp}.html"

    file_path.parent.mkdir(parents=True, exist_ok=True)

    dist = result.distribution
    has_names = any(info.name for info in result.component_index.values())

    # Escape org_id for HTML output
    org_id_escaped = html.escape(result.org_id)

    # Calculate total aggregates (non-unique counts across all data views)
    total_components_aggregate = sum(dv.total_components for dv in result.data_view_summaries if dv.error is None)
    total_derived_metrics = sum(dv.derived_metric_count for dv in result.data_view_summaries if dv.error is None)
    total_derived_dimensions = sum(dv.derived_dimension_count for dv in result.data_view_summaries if dv.error is None)
    total_derived_fields = total_derived_metrics + total_derived_dimensions

    html_out = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Org-Wide Component Analysis Report</title>
    <style>
        :root {{
            --primary: #1a73e8;
            --success: #34a853;
            --warning: #fbbc04;
            --danger: #ea4335;
            --bg: #f8f9fa;
            --card-bg: #ffffff;
            --text: #202124;
            --text-secondary: #5f6368;
            --border: #dadce0;
        }}
        * {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: var(--bg);
            color: var(--text);
            line-height: 1.6;
            padding: 2rem;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        h1 {{ color: var(--primary); margin-bottom: 0.5rem; }}
        h2 {{ color: var(--text); margin: 2rem 0 1rem; border-bottom: 2px solid var(--primary); padding-bottom: 0.5rem; }}
        h3 {{ color: var(--text-secondary); margin: 1.5rem 0 0.75rem; }}
        .meta {{ color: var(--text-secondary); margin-bottom: 2rem; }}
        .card {{
            background: var(--card-bg);
            border-radius: 8px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
            padding: 1.5rem;
            margin-bottom: 1.5rem;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 1rem;
        }}
        .stat-card {{
            background: var(--card-bg);
            border-radius: 8px;
            padding: 1rem;
            text-align: center;
            border: 1px solid var(--border);
        }}
        .stat-value {{ font-size: 2rem; font-weight: bold; color: var(--primary); }}
        .stat-label {{ color: var(--text-secondary); font-size: 0.875rem; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 1rem 0;
            font-size: 0.9rem;
        }}
        th, td {{
            padding: 0.75rem;
            text-align: left;
            border-bottom: 1px solid var(--border);
        }}
        th {{ background: var(--bg); font-weight: 600; }}
        tr:hover {{ background: #f1f3f4; }}
        .badge {{
            display: inline-block;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-size: 0.75rem;
            font-weight: 500;
        }}
        .badge-core {{ background: #e8f5e9; color: #2e7d32; }}
        .badge-common {{ background: #e3f2fd; color: #1565c0; }}
        .badge-limited {{ background: #fff3e0; color: #ef6c00; }}
        .badge-isolated {{ background: #fce4ec; color: #c2185b; }}
        .badge-high {{ background: var(--danger); color: white; }}
        .badge-medium {{ background: var(--warning); color: #333; }}
        .badge-low {{ background: var(--primary); color: white; }}
        .progress-bar {{
            background: #e0e0e0;
            border-radius: 4px;
            height: 20px;
            overflow: hidden;
        }}
        .progress-fill {{
            height: 100%;
            background: var(--primary);
            transition: width 0.3s;
        }}
        code {{ background: #f1f3f4; padding: 0.2rem 0.4rem; border-radius: 4px; font-size: 0.85rem; }}
        .recommendation {{ padding: 1rem; border-left: 4px solid var(--primary); margin: 1rem 0; background: #f8f9fa; }}
        .recommendation.high {{ border-color: var(--danger); }}
        .recommendation.medium {{ border-color: var(--warning); }}
        .rec-context {{ margin: 0.6rem 0 0 1.2rem; color: var(--text-secondary); }}
        .rec-context li {{ margin: 0.2rem 0; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Org-Wide Component Analysis Report</h1>
        <p class="meta">Organization: {org_id_escaped} | Generated: {result.timestamp} | Duration: {result.duration:.2f}s</p>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{result.successful_data_views}/{result.total_data_views}</div>
                <div class="stat-label">Data Views Analyzed</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{result.failed_data_views}</div>
                <div class="stat-label">Data View Fetch Failures</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{result.total_unique_metrics:,}</div>
                <div class="stat-label">Unique Metrics</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{result.total_unique_dimensions:,}</div>
                <div class="stat-label">Unique Dimensions</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{result.total_unique_components:,}</div>
                <div class="stat-label">Total Unique Components</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{total_components_aggregate:,}</div>
                <div class="stat-label">Total Components (Non-Unique)</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{total_derived_fields:,}</div>
                <div class="stat-label">Total Derived Fields (Non-Unique)</div>
            </div>
        </div>

        <h2>Component Distribution</h2>
        <div class="card">
            <table>
                <thead>
                    <tr><th>Category</th><th>Metrics</th><th>Dimensions</th><th>Total</th><th>Distribution</th></tr>
                </thead>
                <tbody>
"""

    total = result.total_unique_components or 1

    # Build correct label for core threshold
    if result.parameters.core_min_count is None:
        core_label = f"{int(result.parameters.core_threshold * 100)}%+"
        core_desc = f"{int(result.parameters.core_threshold * 100)}% or more of"
    else:
        core_label = f"&gt;={result.parameters.core_min_count}"
        core_desc = f"{result.parameters.core_min_count} or more"

    for bucket, m_list, d_list, badge_class in [
        (f"Core ({core_label} DVs)", dist.core_metrics, dist.core_dimensions, "core"),
        ("Common (25-49% DVs)", dist.common_metrics, dist.common_dimensions, "common"),
        ("Limited (2+ DVs)", dist.limited_metrics, dist.limited_dimensions, "limited"),
        ("Isolated (1 DV)", dist.isolated_metrics, dist.isolated_dimensions, "isolated"),
    ]:
        bucket_total = len(m_list) + len(d_list)
        pct = bucket_total / total * 100
        html_out += f"""                    <tr>
                        <td><span class="badge badge-{badge_class}">{bucket}</span></td>
                        <td>{len(m_list)}</td>
                        <td>{len(d_list)}</td>
                        <td>{bucket_total}</td>
                        <td><div class="progress-bar"><div class="progress-fill" style="width: {pct:.1f}%"></div></div></td>
                    </tr>
"""

    html_out += """                </tbody>
            </table>
        </div>

        <h2>Data Views</h2>
        <div class="card">
            <table>
                <thead>
                    <tr><th>Name</th><th>ID</th><th>Metrics</th><th>Dimensions</th><th>Status</th></tr>
                </thead>
                <tbody>
"""

    for dv in sorted(result.data_view_summaries, key=lambda x: x.data_view_name):
        # Escape user-sourced strings to prevent HTML injection
        dv_name_escaped = html.escape(dv.data_view_name)
        dv_id_escaped = html.escape(dv.data_view_id)
        if dv.error is not None:
            error_escaped = html.escape(dv.error)
            html_out += f'                    <tr><td>{dv_name_escaped}</td><td><code>{dv_id_escaped}</code></td><td colspan="2">ERROR: {error_escaped}</td><td>{dv.status}</td></tr>\n'
        else:
            html_out += f"                    <tr><td>{dv_name_escaped}</td><td><code>{dv_id_escaped}</code></td><td>{dv.metric_count}</td><td>{dv.dimension_count}</td><td>{dv.status}</td></tr>\n"

    html_out += """                </tbody>
            </table>
        </div>
"""

    # Core Components
    if dist.total_core > 0:
        html_out += f"""
        <h2>Core Components</h2>
        <p>Components present in {core_desc} data views.</p>
        <div class="card">
            <table>
                <thead>
                    <tr><th>Component ID</th>{"<th>Name</th>" if has_names else ""}<th>Type</th><th>Data View Count</th></tr>
                </thead>
                <tbody>
"""
        for comp_id in (dist.core_metrics + dist.core_dimensions)[:30]:
            info = result.component_index.get(comp_id)
            if info:
                comp_id_escaped = html.escape(comp_id)
                name_escaped = html.escape(info.name) if info.name else "-"
                name_col = f"<td>{name_escaped}</td>" if has_names else ""
                html_out += f"                    <tr><td><code>{comp_id_escaped}</code></td>{name_col}<td>{info.component_type.title()}</td><td>{info.presence_count}</td></tr>\n"

        if dist.total_core > 30:
            html_out += f'                    <tr><td colspan="{"4" if has_names else "3"}"><em>... and {dist.total_core - 30} more</em></td></tr>\n'

        html_out += """                </tbody>
            </table>
        </div>
"""

    # Similarity Pairs
    if result.similarity_pairs:
        effective_threshold = min(result.parameters.overlap_threshold, 0.9)
        threshold_note = ""
        if result.parameters.overlap_threshold > 0.9:
            threshold_note = (
                f" (configured {int(result.parameters.overlap_threshold * 100)}%, capped at 90% for governance checks)"
            )
        html_out += f"""
        <h2>High Overlap Pairs</h2>
        <p>Data view pairs with &gt;= {int(effective_threshold * 100)}% Jaccard similarity{threshold_note}.</p>
        <div class="card">
            <table>
                <thead>
                    <tr><th>Data View 1</th><th>Data View 2</th><th>Similarity</th><th>Shared</th></tr>
                </thead>
                <tbody>
"""
        for pair in result.similarity_pairs[:20]:
            dv1_escaped = html.escape(pair.dv1_name)
            dv2_escaped = html.escape(pair.dv2_name)
            html_out += f"                    <tr><td>{dv1_escaped}</td><td>{dv2_escaped}</td><td>{pair.jaccard_similarity * 100:.1f}%</td><td>{pair.shared_count}</td></tr>\n"

        if len(result.similarity_pairs) > 20:
            html_out += f'                    <tr><td colspan="4"><em>... and {len(result.similarity_pairs) - 20} more pairs</em></td></tr>\n'

        html_out += """                </tbody>
            </table>
        </div>
"""

    # Recommendations
    if result.recommendations:
        html_out += """
        <h2>Recommendations</h2>
"""
        for raw_rec in result.recommendations:
            rec = _normalize_recommendation_for_json(raw_rec)
            severity = rec.get("severity", "low")
            rec_type = html.escape(str(rec.get("type", "Unknown")).replace("_", " ").title())
            rec_reason = html.escape(rec.get("reason", "No details provided."))
            context_entries = _format_recommendation_context_entries(rec)
            context_html = ""
            if context_entries:
                context_html = '            <ul class="rec-context">\n'
                for label, value in context_entries:
                    label_escaped = html.escape(str(label))
                    value_escaped = html.escape(str(value))
                    context_html += f"                <li><strong>{label_escaped}:</strong> {value_escaped}</li>\n"
                context_html += "            </ul>\n"
            html_out += f"""        <div class="recommendation {severity}">
            <strong><span class="badge badge-{severity}">{severity.upper()}</span> {rec_type}</strong>
            <p>{rec_reason}</p>
{context_html}
        </div>
"""

    # Trending section (v3.4.0)
    if trending is not None and len(trending.snapshots) >= 2:
        html_out += _render_trending_html(trending)

    html_out += """
        <hr style="margin: 2rem 0; border: none; border-top: 1px solid var(--border);">
        <p style="color: var(--text-secondary); font-size: 0.875rem;">Generated by CJA SDR Generator</p>
    </div>
</body>
</html>"""

    with open(file_path, "w", encoding="utf-8") as f:
        f.write(html_out)

    logger.info(f"HTML report written to {file_path}")
    return str(file_path)


def write_org_report_csv(
    result: OrgReportResult,
    output_path: Path | None,
    output_dir: str,
    logger: logging.Logger,
    trending: OrgReportTrending | None = None,
) -> str:
    """Write org report as multiple CSV files.

    Creates the following CSV files:
    - org_report_summary.csv: High-level statistics
    - org_report_data_views.csv: Per-data-view breakdown
    - org_report_components.csv: Component index with names and coverage
    - org_report_similarity.csv: Similarity pairs (if computed)
    - org_report_distribution.csv: Distribution bucket counts
    - org_report_trending.csv: Trending snapshot data (if provided)
    - org_report_trending_deltas.csv: Period-over-period trending deltas (if provided)

    Args:
        result: OrgReportResult from analysis
        output_path: Optional base path (suffix will be added)
        output_dir: Output directory if no path specified
        logger: Logger instance
        trending: Optional trending data to include

    Returns:
        Path to the created directory containing CSV files
    """
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    # Determine output directory
    if output_path:
        csv_dir = Path(output_path)
        if csv_dir.suffix == ".csv":
            csv_dir = csv_dir.parent / csv_dir.stem
    else:
        csv_dir = Path(output_dir) / f"org_report_{result.org_id}_{timestamp}"

    csv_dir.mkdir(parents=True, exist_ok=True)

    # 1. Summary CSV
    # Calculate total aggregates (non-unique counts across all data views)
    total_metrics_aggregate = sum(dv.metric_count for dv in result.data_view_summaries if dv.error is None)
    total_dimensions_aggregate = sum(dv.dimension_count for dv in result.data_view_summaries if dv.error is None)
    total_components_aggregate = sum(dv.total_components for dv in result.data_view_summaries if dv.error is None)
    total_derived_metrics = sum(dv.derived_metric_count for dv in result.data_view_summaries if dv.error is None)
    total_derived_dimensions = sum(dv.derived_dimension_count for dv in result.data_view_summaries if dv.error is None)
    total_derived_fields = total_derived_metrics + total_derived_dimensions
    effective_overlap_threshold = min(result.parameters.overlap_threshold, 0.9)

    summary_data = [
        {
            "Report Type": "Org-Wide Component Analysis",
            "Generated At": result.timestamp,
            "Org ID": result.org_id,
            "Total Data Views": result.total_data_views,
            "Successful Data Views": result.successful_data_views,
            "Failed Data Views": result.failed_data_views,
            "Total Unique Metrics": result.total_unique_metrics,
            "Total Unique Dimensions": result.total_unique_dimensions,
            "Total Unique Components": result.total_unique_components,
            "Total Metrics (Non-Unique)": total_metrics_aggregate,
            "Total Dimensions (Non-Unique)": total_dimensions_aggregate,
            "Total Components (Non-Unique)": total_components_aggregate,
            "Derived Metrics (Non-Unique)": total_derived_metrics,
            "Derived Dimensions (Non-Unique)": total_derived_dimensions,
            "Total Derived Fields (Non-Unique)": total_derived_fields,
            "Core Threshold": result.parameters.core_threshold,
            "Overlap Threshold (Configured)": result.parameters.overlap_threshold,
            "Overlap Threshold (Effective)": effective_overlap_threshold,
            "Analysis Duration (s)": round(result.duration, 2),
        },
    ]
    summary_df = pd.DataFrame(summary_data)
    summary_path = csv_dir / "org_report_summary.csv"
    summary_df.to_csv(summary_path, index=False, encoding="utf-8")

    # 2. Data Views CSV
    dv_data = [
        {
            "Data View ID": dv.data_view_id,
            "Data View Name": dv.data_view_name,
            "Metrics Count": dv.metric_count,
            "Dimensions Count": dv.dimension_count,
            "Total Components": dv.total_components,
            "Status": dv.status,
            "Error": dv.normalized_error_reason if dv.has_error else "",
            "Fetch Duration (s)": round(dv.fetch_duration, 3),
        }
        for dv in result.data_view_summaries
    ]
    dv_df = pd.DataFrame(dv_data)
    dv_path = csv_dir / "org_report_data_views.csv"
    dv_df.to_csv(dv_path, index=False, encoding="utf-8")

    # 3. Components CSV
    comp_data = []
    for comp_id, info in result.component_index.items():
        # Determine distribution bucket
        if comp_id in result.distribution.core_metrics or comp_id in result.distribution.core_dimensions:
            bucket = "Core"
        elif comp_id in result.distribution.common_metrics or comp_id in result.distribution.common_dimensions:
            bucket = "Common"
        elif comp_id in result.distribution.limited_metrics or comp_id in result.distribution.limited_dimensions:
            bucket = "Limited"
        else:
            bucket = "Isolated"

        coverage_pct = (
            (info.presence_count / result.successful_data_views * 100) if result.successful_data_views > 0 else 0
        )

        comp_data.append(
            {
                "Component ID": comp_id,
                "Component Type": info.component_type.title(),
                "Name": info.name or "",
                "Data View Count": info.presence_count,
                "Coverage (%)": round(coverage_pct, 1),
                "Distribution Bucket": bucket,
                "Data Views": ";".join(sorted(info.data_views)),
            },
        )
    comp_df = pd.DataFrame(comp_data)
    comp_df = comp_df.sort_values(["Distribution Bucket", "Data View Count"], ascending=[True, False])
    comp_path = csv_dir / "org_report_components.csv"
    comp_df.to_csv(comp_path, index=False, encoding="utf-8")

    # 4. Distribution CSV
    dist = result.distribution
    dist_data = [
        {
            "Bucket": "Core",
            "Metrics": len(dist.core_metrics),
            "Dimensions": len(dist.core_dimensions),
            "Total": dist.total_core,
        },
        {
            "Bucket": "Common",
            "Metrics": len(dist.common_metrics),
            "Dimensions": len(dist.common_dimensions),
            "Total": dist.total_common,
        },
        {
            "Bucket": "Limited",
            "Metrics": len(dist.limited_metrics),
            "Dimensions": len(dist.limited_dimensions),
            "Total": dist.total_limited,
        },
        {
            "Bucket": "Isolated",
            "Metrics": len(dist.isolated_metrics),
            "Dimensions": len(dist.isolated_dimensions),
            "Total": dist.total_isolated,
        },
    ]
    dist_df = pd.DataFrame(dist_data)
    dist_path = csv_dir / "org_report_distribution.csv"
    dist_df.to_csv(dist_path, index=False, encoding="utf-8")

    # 5. Similarity CSV (if computed)
    if result.similarity_pairs:
        effective_overlap_threshold = min(result.parameters.overlap_threshold, 0.9)
        sim_data = [
            {
                "Data View 1 ID": pair.dv1_id,
                "Data View 1 Name": pair.dv1_name,
                "Data View 2 ID": pair.dv2_id,
                "Data View 2 Name": pair.dv2_name,
                "Jaccard Similarity": pair.jaccard_similarity,
                "Shared Components": pair.shared_count,
                "Union Size": pair.union_count,
                "Overlap Threshold (Configured)": result.parameters.overlap_threshold,
                "Overlap Threshold (Effective)": effective_overlap_threshold,
            }
            for pair in result.similarity_pairs
        ]
        sim_df = pd.DataFrame(sim_data)
        sim_path = csv_dir / "org_report_similarity.csv"
        sim_df.to_csv(sim_path, index=False, encoding="utf-8")

    # 6. Recommendations CSV (if any)
    if result.recommendations:
        rec_data = [
            _flatten_recommendation_for_tabular(_normalize_recommendation_for_json(rec))
            for rec in result.recommendations
        ]
        rec_df = pd.DataFrame(rec_data)
        rec_path = csv_dir / "org_report_recommendations.csv"
        rec_df.to_csv(rec_path, index=False, encoding="utf-8")

    # 7. Trending CSV (if provided)
    if trending is not None and len(trending.snapshots) >= 2:
        trending_df = pd.DataFrame(_trending_snapshot_csv_rows(trending.snapshots))
        trending_path = csv_dir / "org_report_trending.csv"
        trending_df.to_csv(trending_path, index=False, encoding="utf-8")

        if trending.deltas:
            delta_df = pd.DataFrame(_trending_delta_csv_rows(trending.deltas))
            delta_path = csv_dir / "org_report_trending_deltas.csv"
            delta_df.to_csv(delta_path, index=False, encoding="utf-8")

        # Drift scores CSV
        if trending.drift_scores:
            drift_data = [
                {
                    "Data View ID": entry["data_view_id"],
                    "Data View Name": entry["data_view_name"] or "",
                    "Drift Score": entry["drift_score"],
                }
                for entry in _ranked_drift_entries(trending)
            ]
            drift_df = pd.DataFrame(drift_data)
            drift_path = csv_dir / "org_report_trending_drift.csv"
            drift_df.to_csv(drift_path, index=False, encoding="utf-8")

    logger.info(f"CSV reports written to {csv_dir}")
    return str(csv_dir)


def _normalize_org_report_output_format(output_format: str | None) -> str:
    """Normalize org-report output format to a canonical lowercase value."""
    return (output_format or "console").strip().lower()


def _validate_org_report_output_request(
    output_format: str,
    output_to_stdout: bool,
    status_print: Callable[..., None],
) -> bool:
    """Validate org-report output arguments before expensive analysis starts."""
    valid_formats = {"console", "json", "excel", "markdown", "html", "csv", "all", *FORMAT_ALIASES}
    if output_format not in valid_formats:
        status_print(
            ConsoleColors.error(
                f"ERROR: Unknown format '{output_format}'. Valid formats: "
                "console, json, excel, markdown, html, csv, all, reports, data, ci",
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
