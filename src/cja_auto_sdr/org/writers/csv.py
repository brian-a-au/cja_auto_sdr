"""CSV org-report writer.

Renders OrgReportResult as a directory of CSV files.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from cja_auto_sdr.org.models import (
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
    _trending_delta_csv_rows as _trending_delta_csv_rows_impl,
)
from cja_auto_sdr.org.writers.trending import (
    _trending_snapshot_csv_rows as _trending_snapshot_csv_rows_impl,
)

__all__ = [
    "write_org_report_csv",
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
_trending_delta_csv_rows = make_override_proxy(
    __name__,
    "_trending_delta_csv_rows",
    _trending_delta_csv_rows_impl,
)
_trending_snapshot_csv_rows = make_override_proxy(
    __name__,
    "_trending_snapshot_csv_rows",
    _trending_snapshot_csv_rows_impl,
)


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
