"""Trending table renderers and helpers for org report writers."""

from __future__ import annotations

import html
from collections.abc import Callable
from datetime import datetime
from typing import Any

from cja_auto_sdr.org.models import (
    OrgReportTrending,
    TrendingDelta,
    TrendingSnapshot,
    _snapshot_effective_data_view_count,
)
from cja_auto_sdr.org.writers.compat import (
    call_override,
    make_override_proxy,
)

__all__ = [
    "_TRENDING_METRIC_SPECS",
    "_build_trending_metric_rows",
    "_escape_markdown_table_cell",
    "_format_signed_trending_value",
    "_format_trending_dv_label",
    "_format_trending_period_label",
    "_format_trending_timestamp_short",
    "_print_trending_console_section",
    "_ranked_drift_entries",
    "_render_console_trending_table",
    "_render_html_trending_table",
    "_render_markdown_trending_table",
    "_render_trending_console",
    "_render_trending_html",
    "_render_trending_markdown",
    "_resolve_trending_dv_name",
    "_sorted_drift_score_items",
    "_stringify_trending_value",
    "_top_drift_scores",
    "_trending_date_range",
    "_trending_delta_column_specs",
    "_trending_delta_csv_rows",
    "_trending_delta_metric_rows",
    "_trending_matrix_rows",
    "_trending_snapshot_column_specs",
    "_trending_snapshot_csv_rows",
    "_trending_snapshot_metric_rows",
    "_trending_snapshots_to_dicts",
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
    except (ValueError, AttributeError):
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
        (
            f"snapshot_{index + 1}",
            call_override(
                __name__,
                "_format_trending_timestamp_short",
                _format_trending_timestamp_short,
                snapshot.timestamp,
            ),
        )
        for index, snapshot in enumerate(snapshots)
    ]


def _format_trending_period_label(from_timestamp: str, to_timestamp: str) -> str:
    """Return a compact human-readable label for one trending period."""
    from_label = call_override(
        __name__,
        "_format_trending_timestamp_short",
        _format_trending_timestamp_short,
        from_timestamp,
    )
    to_label = call_override(
        __name__,
        "_format_trending_timestamp_short",
        _format_trending_timestamp_short,
        to_timestamp,
    )
    return f"{from_label} -> {to_label}"


def _trending_delta_column_specs(
    deltas: list[TrendingDelta],
) -> list[tuple[str, str]]:
    """Return unique worksheet keys paired with display labels for period deltas."""
    return [
        (
            f"period_{index + 1}",
            call_override(
                __name__,
                "_format_trending_period_label",
                _format_trending_period_label,
                delta.from_timestamp,
                delta.to_timestamp,
            ),
        )
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
        period_label = call_override(
            __name__,
            "_format_trending_period_label",
            _format_trending_period_label,
            delta.from_timestamp,
            delta.to_timestamp,
        )
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
    first = call_override(
        __name__,
        "_format_trending_timestamp_short",
        _format_trending_timestamp_short,
        snapshots[0].timestamp,
    )
    last = call_override(
        __name__,
        "_format_trending_timestamp_short",
        _format_trending_timestamp_short,
        snapshots[-1].timestamp,
    )
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
    col_labels = [label for _key, label in _trending_snapshot_column_specs(snapshots)]
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
    col_labels = [label for _key, label in _trending_snapshot_column_specs(snapshots)]
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
    col_labels = [label for _key, label in _trending_snapshot_column_specs(snapshots)]

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


_OVERRIDABLE_HELPERS = tuple(name for name in __all__ if name != "_TRENDING_METRIC_SPECS")

for _helper_name in _OVERRIDABLE_HELPERS:
    globals()[_helper_name] = make_override_proxy(__name__, _helper_name, globals()[_helper_name])
del _helper_name
