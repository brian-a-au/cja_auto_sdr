"""HTML org-report writer.

Renders OrgReportResult as a styled HTML document.
"""

from __future__ import annotations

import html as _html
import logging
from datetime import UTC, datetime
from pathlib import Path

from cja_auto_sdr.org.models import (
    OrgReportResult,
    OrgReportTrending,
)
from cja_auto_sdr.org.writers.common import (
    _format_recommendation_context_entries,
    _normalize_recommendation_for_json,
)
from cja_auto_sdr.org.writers.trending import (
    _render_trending_html,
)


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
    org_id_escaped = _html.escape(result.org_id)

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
        dv_name_escaped = _html.escape(dv.data_view_name)
        dv_id_escaped = _html.escape(dv.data_view_id)
        if dv.error is not None:
            error_escaped = _html.escape(dv.error)
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
                comp_id_escaped = _html.escape(comp_id)
                name_escaped = _html.escape(info.name) if info.name else "-"
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
            dv1_escaped = _html.escape(pair.dv1_name)
            dv2_escaped = _html.escape(pair.dv2_name)
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
            rec_type = _html.escape(str(rec.get("type", "Unknown")).replace("_", " ").title())
            rec_reason = _html.escape(rec.get("reason", "No details provided."))
            context_entries = _format_recommendation_context_entries(rec)
            context_html = ""
            if context_entries:
                context_html = '            <ul class="rec-context">\n'
                for label, value in context_entries:
                    label_escaped = _html.escape(str(label))
                    value_escaped = _html.escape(str(value))
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
