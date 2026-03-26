"""JSON builder and writer for org report output."""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from cja_auto_sdr.org.models import (
    OrgReportResult,
    OrgReportTrending,
)
from cja_auto_sdr.org.snapshot_utils import sorted_snapshot_strings
from cja_auto_sdr.org.writers.common import (
    _normalize_recommendation_for_json as _normalize_recommendation_for_json_impl,
)
from cja_auto_sdr.org.writers.compat import (
    call_override,
    make_override_proxy,
)
from cja_auto_sdr.org.writers.trending import _trending_snapshots_to_dicts as _trending_snapshots_to_dicts_impl

__all__ = [
    "build_org_report_json_data",
    "write_org_report_json",
]

_normalize_recommendation_for_json = make_override_proxy(
    __name__,
    "_normalize_recommendation_for_json",
    _normalize_recommendation_for_json_impl,
)
_trending_snapshots_to_dicts = make_override_proxy(
    __name__,
    "_trending_snapshots_to_dicts",
    _trending_snapshots_to_dicts_impl,
)


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

    json_data = call_override(
        __name__,
        "build_org_report_json_data",
        build_org_report_json_data,
        result,
        trending=trending,
    )

    # Write JSON
    file_path.parent.mkdir(parents=True, exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, indent=2, ensure_ascii=False)

    logger.info(f"JSON report written to {file_path}")
    return str(file_path)
