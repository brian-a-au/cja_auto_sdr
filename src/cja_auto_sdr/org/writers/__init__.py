"""
Org report writer functions.

Extracted from generator.py — all functions that render OrgReportResult
into various output formats (console, JSON, Excel, Markdown, HTML, CSV).
"""

from __future__ import annotations

import html as _html
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from cja_auto_sdr.core.version import __version__
from cja_auto_sdr.org.models import (
    ComponentInfo,
    OrgReportResult,
    OrgReportTrending,
)
from cja_auto_sdr.org.snapshot_utils import sorted_snapshot_strings

# ---------------------------------------------------------------------------
# Re-exports from common.py
# ---------------------------------------------------------------------------
from cja_auto_sdr.org.writers.common import (
    _flatten_recommendation_for_tabular,
    _format_recommendation_context_entries,
    _normalize_org_report_output_format,
    _normalize_recommendation_for_json,
    _normalize_recommendation_severity,
    _render_distribution_bar,
    _validate_org_report_output_request,
)

# ---------------------------------------------------------------------------
# Re-exports from console.py
# ---------------------------------------------------------------------------
from cja_auto_sdr.org.writers.console import (
    write_org_report_comparison_console,
    write_org_report_console,
    write_org_report_stats_only,
)

# ---------------------------------------------------------------------------
# Re-exports from json.py
# ---------------------------------------------------------------------------
from cja_auto_sdr.org.writers.json import (
    build_org_report_json_data,
    write_org_report_json,
)

# ---------------------------------------------------------------------------
# Re-exports from trending.py  (private helpers that tests import directly)
# ---------------------------------------------------------------------------
from cja_auto_sdr.org.writers.trending import (
    _TRENDING_METRIC_SPECS,
    _build_trending_metric_rows,
    _escape_markdown_table_cell,
    _format_signed_trending_value,
    _format_trending_dv_label,
    _format_trending_period_label,
    _format_trending_timestamp_short,
    _print_trending_console_section,
    _ranked_drift_entries,
    _render_console_trending_table,
    _render_html_trending_table,
    _render_markdown_trending_table,
    _render_trending_console,
    _render_trending_html,
    _render_trending_markdown,
    _resolve_trending_dv_name,
    _sorted_drift_score_items,
    _stringify_trending_value,
    _top_drift_scores,
    _trending_date_range,
    _trending_delta_column_specs,
    _trending_delta_csv_rows,
    _trending_delta_metric_rows,
    _trending_matrix_rows,
    _trending_snapshot_column_specs,
    _trending_snapshot_csv_rows,
    _trending_snapshot_metric_rows,
    _trending_snapshots_to_dicts,
)

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
