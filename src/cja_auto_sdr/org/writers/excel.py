"""Excel org-report writer.

Renders OrgReportResult as a multi-sheet .xlsx workbook.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from cja_auto_sdr.org.models import (
    ComponentInfo,
    OrgReportResult,
    OrgReportTrending,
)
from cja_auto_sdr.org.writers.common import (
    _flatten_recommendation_for_tabular as _flatten_recommendation_for_tabular_impl,
)
from cja_auto_sdr.org.writers.common import (
    _normalize_recommendation_for_json as _normalize_recommendation_for_json_impl,
)
from cja_auto_sdr.org.writers.compat import make_override_proxy
from cja_auto_sdr.org.writers.trending import (
    _ranked_drift_entries as _ranked_drift_entries_impl,
)
from cja_auto_sdr.org.writers.trending import (
    _trending_delta_column_specs as _trending_delta_column_specs_impl,
)
from cja_auto_sdr.org.writers.trending import (
    _trending_delta_metric_rows as _trending_delta_metric_rows_impl,
)
from cja_auto_sdr.org.writers.trending import (
    _trending_matrix_rows as _trending_matrix_rows_impl,
)
from cja_auto_sdr.org.writers.trending import (
    _trending_snapshot_column_specs as _trending_snapshot_column_specs_impl,
)
from cja_auto_sdr.org.writers.trending import (
    _trending_snapshot_metric_rows as _trending_snapshot_metric_rows_impl,
)

__all__ = [
    "write_org_report_excel",
]

_flatten_recommendation_for_tabular = make_override_proxy(
    __name__,
    "_flatten_recommendation_for_tabular",
    _flatten_recommendation_for_tabular_impl,
)
_normalize_recommendation_for_json = make_override_proxy(
    __name__,
    "_normalize_recommendation_for_json",
    _normalize_recommendation_for_json_impl,
)
_ranked_drift_entries = make_override_proxy(
    __name__,
    "_ranked_drift_entries",
    _ranked_drift_entries_impl,
)
_trending_delta_column_specs = make_override_proxy(
    __name__,
    "_trending_delta_column_specs",
    _trending_delta_column_specs_impl,
)
_trending_delta_metric_rows = make_override_proxy(
    __name__,
    "_trending_delta_metric_rows",
    _trending_delta_metric_rows_impl,
)
_trending_matrix_rows = make_override_proxy(
    __name__,
    "_trending_matrix_rows",
    _trending_matrix_rows_impl,
)
_trending_snapshot_column_specs = make_override_proxy(
    __name__,
    "_trending_snapshot_column_specs",
    _trending_snapshot_column_specs_impl,
)
_trending_snapshot_metric_rows = make_override_proxy(
    __name__,
    "_trending_snapshot_metric_rows",
    _trending_snapshot_metric_rows_impl,
)


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
