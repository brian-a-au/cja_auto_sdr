"""
Tests targeting uncovered lines in org report writers, comparison, and batch processing functions.

Covers:
- compare_org_reports() backward-compat parsing (old JSON format)
- write_org_report_console() scattered branches
- write_org_report_stats_only()
- write_org_report_comparison_console()
- write_org_report_json()
- write_org_report_excel()
- write_org_report_markdown() ellipsis rows for >20 components
- write_org_report_html()
- write_org_report_csv()
- run_org_report() comparison/stats-only dispatch
- _main_impl workers validation and org-report dispatch
"""

import csv
import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cja_auto_sdr.generator import (
    _render_distribution_bar,
    build_org_report_json_data,
    build_org_step_summary,
    compare_org_reports,
    run_org_report,
    write_org_report_comparison_console,
    write_org_report_console,
    write_org_report_csv,
    write_org_report_excel,
    write_org_report_html,
    write_org_report_json,
    write_org_report_markdown,
    write_org_report_stats_only,
)
from cja_auto_sdr.org.models import (
    ComponentDistribution,
    ComponentInfo,
    DataViewCluster,
    DataViewSummary,
    OrgReportComparison,
    OrgReportConfig,
    OrgReportResult,
    OrgReportTrending,
    SimilarityPair,
    TrendingDelta,
    TrendingSnapshot,
)
from cja_auto_sdr.org.writers import (
    _format_trending_timestamp_short,
    _render_console_trending_table,
    _render_html_trending_table,
    _render_markdown_trending_table,
    _render_trending_console,
    _render_trending_html,
    _render_trending_markdown,
    _top_drift_scores,
    _trending_date_range,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_component_info(comp_id, comp_type="metric", name=None, data_views=None):
    """Build a ComponentInfo with the given fields."""
    info = ComponentInfo(component_id=comp_id, component_type=comp_type, name=name)
    info.data_views = set(data_views or [])
    return info


def _make_data_view_summary(dv_id, dv_name, metric_count=5, dimension_count=3, error=None):
    """Build a minimal DataViewSummary."""
    return DataViewSummary(
        data_view_id=dv_id,
        data_view_name=dv_name,
        metric_ids={f"m_{dv_id}_{i}" for i in range(metric_count)},
        dimension_ids={f"d_{dv_id}_{i}" for i in range(dimension_count)},
        metric_count=metric_count,
        dimension_count=dimension_count,
        standard_metric_count=metric_count - 1,
        derived_metric_count=1,
        standard_dimension_count=dimension_count - 1,
        derived_dimension_count=1,
        error=error,
    )


def _make_similarity_pair(dv1_id, dv1_name, dv2_id, dv2_name, similarity=0.85):
    """Build a SimilarityPair."""
    return SimilarityPair(
        dv1_id=dv1_id,
        dv1_name=dv1_name,
        dv2_id=dv2_id,
        dv2_name=dv2_name,
        jaccard_similarity=similarity,
        shared_count=10,
        union_count=12,
    )


def _make_org_result(
    num_dvs=3,
    num_core_metrics=2,
    num_core_dims=2,
    num_isolated_metrics=1,
    num_isolated_dims=1,
    include_names=False,
    include_similarity=True,
    include_clusters=False,
    include_recommendations=True,
    include_governance_violations=False,
    include_owner_summary=False,
    include_naming_audit=False,
    include_stale=False,
    is_sampled=False,
    config_overrides=None,
):
    """Build a complete OrgReportResult suitable for testing all writers."""
    config = OrgReportConfig(**(config_overrides or {}))

    dv_summaries = [_make_data_view_summary(f"dv_{i:03d}", f"Data View {i}") for i in range(1, num_dvs + 1)]

    # Build component index
    component_index = {}
    core_metrics = []
    core_dimensions = []
    isolated_metrics = []
    isolated_dimensions = []

    for i in range(num_core_metrics):
        cid = f"core_metric_{i}"
        name = f"Core Metric {i}" if include_names else None
        component_index[cid] = _make_component_info(
            cid, "metric", name=name, data_views=[f"dv_{j:03d}" for j in range(1, num_dvs + 1)]
        )
        core_metrics.append(cid)

    for i in range(num_core_dims):
        cid = f"core_dim_{i}"
        name = f"Core Dimension {i}" if include_names else None
        component_index[cid] = _make_component_info(
            cid, "dimension", name=name, data_views=[f"dv_{j:03d}" for j in range(1, num_dvs + 1)]
        )
        core_dimensions.append(cid)

    for i in range(num_isolated_metrics):
        cid = f"isolated_metric_{i}"
        component_index[cid] = _make_component_info(cid, "metric", data_views=["dv_001"])
        isolated_metrics.append(cid)

    for i in range(num_isolated_dims):
        cid = f"isolated_dim_{i}"
        component_index[cid] = _make_component_info(cid, "dimension", data_views=["dv_001"])
        isolated_dimensions.append(cid)

    distribution = ComponentDistribution(
        core_metrics=core_metrics,
        core_dimensions=core_dimensions,
        common_metrics=["common_m_0"],
        common_dimensions=["common_d_0"],
        limited_metrics=["limited_m_0"],
        limited_dimensions=["limited_d_0"],
        isolated_metrics=isolated_metrics,
        isolated_dimensions=isolated_dimensions,
    )
    # Add common/limited components to index
    component_index["common_m_0"] = _make_component_info("common_m_0", "metric", data_views=["dv_001", "dv_002"])
    component_index["common_d_0"] = _make_component_info("common_d_0", "dimension", data_views=["dv_001", "dv_002"])
    component_index["limited_m_0"] = _make_component_info("limited_m_0", "metric", data_views=["dv_001", "dv_002"])
    component_index["limited_d_0"] = _make_component_info("limited_d_0", "dimension", data_views=["dv_001", "dv_002"])

    similarity_pairs = None
    if include_similarity:
        similarity_pairs = [
            _make_similarity_pair("dv_001", "Data View 1", "dv_002", "Data View 2", 0.92),
            _make_similarity_pair("dv_001", "Data View 1", "dv_003", "Data View 3", 0.85),
        ]

    clusters = None
    if include_clusters:
        clusters = [
            DataViewCluster(
                cluster_id=0,
                cluster_name="Analytics Cluster",
                data_view_ids=["dv_001", "dv_002"],
                data_view_names=["Data View 1", "Data View 2"],
                cohesion_score=0.88,
            ),
        ]

    recommendations = []
    if include_recommendations:
        recommendations = [
            {
                "type": "high_overlap",
                "severity": "high",
                "reason": "DV 1 and DV 2 share >90% of components",
                "data_view_1": "dv_001",
                "data_view_1_name": "Data View 1",
                "data_view_2": "dv_002",
                "data_view_2_name": "Data View 2",
                "similarity": 0.92,
            },
            {
                "type": "isolated_components",
                "severity": "medium",
                "reason": "Data View 1 has many isolated components",
                "data_view": "dv_001",
                "data_view_name": "Data View 1",
                "isolated_count": 5,
            },
            {
                "type": "governance",
                "severity": "low",
                "reason": "Consider standardizing naming conventions",
            },
        ]

    governance_violations = None
    if include_governance_violations:
        governance_violations = [
            {"message": "Too many high-similarity pairs", "threshold": 2, "actual": 5},
        ]

    owner_summary = None
    if include_owner_summary:
        owner_summary = {
            "by_owner": {
                "Alice": {
                    "data_view_count": 2,
                    "total_metrics": 10,
                    "total_dimensions": 6,
                    "avg_components_per_dv": 8.0,
                },
                "Bob": {"data_view_count": 1, "total_metrics": 5, "total_dimensions": 3, "avg_components_per_dv": 8.0},
            },
            "owners_sorted_by_dv_count": ["Alice", "Bob"],
        }

    naming_audit = None
    if include_naming_audit:
        naming_audit = {
            "total_components": 10,
            "case_styles": {"camelCase": 6, "snake_case": 4},
            "recommendations": [
                {"severity": "medium", "message": "Mixed naming conventions detected"},
            ],
        }

    stale_components = None
    if include_stale:
        stale_components = [
            {"pattern": "deprecated_prefix", "component_id": "old_metric_1", "name": "OLD_metric_1"},
            {"pattern": "deprecated_prefix", "component_id": "old_metric_2", "name": "OLD_metric_2"},
            {"pattern": "test_prefix", "component_id": "test_dim_1", "name": "test_dimension"},
        ]

    return OrgReportResult(
        timestamp="2025-01-15T10:00:00Z",
        org_id="test_org_123",
        parameters=config,
        data_view_summaries=dv_summaries,
        component_index=component_index,
        distribution=distribution,
        similarity_pairs=similarity_pairs,
        recommendations=recommendations,
        duration=1.23,
        clusters=clusters,
        is_sampled=is_sampled,
        total_available_data_views=10 if is_sampled else 0,
        governance_violations=governance_violations,
        thresholds_exceeded=include_governance_violations,
        naming_audit=naming_audit,
        owner_summary=owner_summary,
        stale_components=stale_components,
    )


def _mark_full_fidelity_baseline(payload):
    """Add current snapshot-fidelity markers to manual comparison fixtures."""
    payload = dict(payload)
    parameters = dict(payload.get("parameters", {}))
    parameters.setdefault("skip_similarity", False)
    parameters.setdefault("org_stats_only", False)
    payload["parameters"] = parameters

    summary = dict(payload.get("summary", {}))
    summary.setdefault("similarity_analysis_complete", True)
    summary.setdefault("similarity_analysis_mode", "complete")
    payload["summary"] = summary

    payload.setdefault("similarity_pairs", [])
    return payload


# ===================================================================
# compare_org_reports
# ===================================================================


class TestCompareOrgReports:
    """Tests for compare_org_reports(), focusing on backward-compat parsing."""

    def test_compare_with_flat_similarity_pairs(self, tmp_path):
        """Cover lines 10479-10481: flat dv1_id/dv2_id format."""
        prev_report = _mark_full_fidelity_baseline(
            {
                "generated_at": "2024-12-01T10:00:00Z",
                "data_views": [
                    {"data_view_id": "dv_001", "data_view_name": "DV 1"},
                    {"data_view_id": "dv_002", "data_view_name": "DV 2"},
                ],
                "summary": {"total_unique_components": 20},
                "distribution": {
                    "core": {"metrics_count": 5, "dimensions_count": 3},
                    "isolated": {"metrics_count": 2, "dimensions_count": 1},
                },
                "similarity_pairs": [
                    {"dv1_id": "dv_001", "dv2_id": "dv_002", "jaccard_similarity": 0.95},
                ],
            }
        )
        prev_path = tmp_path / "prev_report.json"
        prev_path.write_text(json.dumps(prev_report), encoding="utf-8")

        current = _make_org_result(include_similarity=True)
        comparison = compare_org_reports(current, str(prev_path))

        assert isinstance(comparison, OrgReportComparison)
        assert comparison.previous_timestamp == "2024-12-01T10:00:00Z"
        assert comparison.current_timestamp == "2025-01-15T10:00:00Z"

    def test_compare_with_nested_similarity_pairs(self, tmp_path):
        """Cover lines 10483-10484: old nested data_view_1/data_view_2 format."""
        prev_report = _mark_full_fidelity_baseline(
            {
                "generated_at": "2024-11-01T10:00:00Z",
                "data_views": [
                    {"data_view_id": "dv_001", "data_view_name": "DV 1"},
                    {"data_view_id": "dv_002", "data_view_name": "DV 2"},
                ],
                "summary": {"total_unique_components": 15},
                "distribution": {
                    "core": {"total": 5},
                    "isolated": {"total": 2},
                },
                "similarity_pairs": [
                    {
                        "data_view_1": {"id": "dv_001"},
                        "data_view_2": {"id": "dv_002"},
                        "jaccard_similarity": 0.91,
                    },
                ],
            }
        )
        prev_path = tmp_path / "prev_report_old.json"
        prev_path.write_text(json.dumps(prev_report), encoding="utf-8")

        current = _make_org_result(include_similarity=True)
        comparison = compare_org_reports(current, str(prev_path))

        assert isinstance(comparison, OrgReportComparison)
        # Both the current and previous should have (dv_001, dv_002) as high-sim
        # so new_high_similarity_pairs should be empty
        assert comparison.summary["new_duplicates"] == 0
        assert comparison.summary["resolved_duplicates"] == 0

    def test_compare_detects_added_and_removed_dvs(self, tmp_path):
        """Verify data_views_added and data_views_removed are populated."""
        prev_report = _mark_full_fidelity_baseline(
            {
                "timestamp": "2024-10-01T10:00:00Z",
                "data_views": [
                    {"data_view_id": "dv_001", "data_view_name": "DV 1"},
                    {"data_view_id": "dv_old", "data_view_name": "Old DV"},
                ],
                "summary": {"total_unique_components": 10},
                "distribution": {
                    "core": {"metrics_count": 2, "dimensions_count": 1},
                    "isolated": {"metrics_count": 1, "dimensions_count": 0},
                },
                "similarity_pairs": [],
            }
        )
        prev_path = tmp_path / "prev.json"
        prev_path.write_text(json.dumps(prev_report), encoding="utf-8")

        current = _make_org_result(include_similarity=True)
        comparison = compare_org_reports(current, str(prev_path))

        # dv_old was removed, dv_002 and dv_003 were added
        assert "dv_old" in comparison.data_views_removed
        assert "dv_002" in comparison.data_views_added or "dv_003" in comparison.data_views_added
        assert comparison.summary["data_views_delta"] != 0

    def test_compare_uses_fallback_key_names(self, tmp_path):
        """Cover fallback key parsing: 'id' instead of 'data_view_id'."""
        prev_report = _mark_full_fidelity_baseline(
            {
                "generated_at": "2024-09-01T10:00:00Z",
                "data_views": [
                    {"id": "dv_001", "name": "DV 1"},
                ],
                "summary": {"total_unique_components": 5},
                "distribution": {
                    "core": {"metrics_count": 1, "dimensions_count": 1},
                    "isolated": {"metrics_count": 0, "dimensions_count": 0},
                },
                "similarity_pairs": [],
            }
        )
        prev_path = tmp_path / "prev_fallback.json"
        prev_path.write_text(json.dumps(prev_report), encoding="utf-8")

        current = _make_org_result(include_similarity=True)
        comparison = compare_org_reports(current, str(prev_path))

        assert comparison.previous_timestamp == "2024-09-01T10:00:00Z"
        # dv_001 is in both, so it should not be in added or removed
        assert "dv_001" not in comparison.data_views_removed

    def test_compare_new_and_resolved_pairs(self, tmp_path):
        """Verify new_high_similarity_pairs and resolved_pairs are computed."""
        prev_report = _mark_full_fidelity_baseline(
            {
                "generated_at": "2024-08-01T10:00:00Z",
                "data_views": [
                    {"data_view_id": "dv_001", "data_view_name": "DV 1"},
                    {"data_view_id": "dv_002", "data_view_name": "DV 2"},
                    {"data_view_id": "dv_003", "data_view_name": "DV 3"},
                ],
                "summary": {"total_unique_components": 20},
                "distribution": {
                    "core": {"total": 5},
                    "isolated": {"total": 2},
                },
                "similarity_pairs": [
                    # Old pair that will be "resolved" because current has no such pair
                    {"dv1_id": "dv_002", "dv2_id": "dv_003", "jaccard_similarity": 0.95},
                ],
            }
        )
        prev_path = tmp_path / "prev_pairs.json"
        prev_path.write_text(json.dumps(prev_report), encoding="utf-8")

        # Current has dv_001<->dv_002 at 0.92 (new) but NOT dv_002<->dv_003
        current = _make_org_result(include_similarity=True)
        comparison = compare_org_reports(current, str(prev_path))

        assert comparison.summary["new_duplicates"] >= 1
        assert comparison.summary["resolved_duplicates"] >= 1

    def test_compare_allows_current_reports_when_similarity_is_skipped(self, tmp_path):
        prev_report = _mark_full_fidelity_baseline(
            {
                "generated_at": "2024-08-01T10:00:00Z",
                "data_views": [
                    {"data_view_id": "dv_001", "data_view_name": "Data View 1"},
                    {"data_view_id": "dv_002", "data_view_name": "Data View 2"},
                    {"data_view_id": "dv_003", "data_view_name": "Data View 3"},
                ],
                "summary": {"total_unique_components": 20},
                "distribution": {
                    "core": {"total": 5},
                    "isolated": {"total": 2},
                },
                "similarity_pairs": [
                    {"dv1_id": "dv_001", "dv2_id": "dv_002", "jaccard_similarity": 0.95},
                ],
            }
        )
        prev_path = tmp_path / "prev_skip_similarity.json"
        prev_path.write_text(json.dumps(prev_report), encoding="utf-8")

        current = _make_org_result(include_similarity=False, config_overrides={"skip_similarity": True})
        comparison = compare_org_reports(current, str(prev_path))

        assert comparison.current_timestamp == current.timestamp
        assert comparison.summary["data_views_delta"] == 0
        assert comparison.summary["new_duplicates"] == 0
        assert comparison.summary["resolved_duplicates"] == 0
        assert comparison.new_high_similarity_pairs == []
        assert comparison.resolved_pairs == []

    def test_compare_allows_cached_previous_reports_when_persisted_skip_similarity_matches_payload(self, tmp_path):
        prev_report = _mark_full_fidelity_baseline(
            {
                "generated_at": "2024-08-01T10:00:00Z",
                "_snapshot_meta": {
                    "snapshot_id": "persisted-123",
                    "history_eligible": False,
                    "history_exclusion_reason": "skip_similarity",
                },
                "data_views": [
                    {"data_view_id": "dv_001", "data_view_name": "Data View 1", "error": None},
                    {"data_view_id": "dv_002", "data_view_name": "Data View 2", "error": None},
                    {"data_view_id": "dv_003", "data_view_name": "Data View 3", "error": None},
                ],
                "summary": {
                    "data_views_total": 3,
                    "data_views_analyzed": 3,
                    "total_unique_components": 20,
                    "similarity_analysis_complete": False,
                    "similarity_analysis_mode": "skip_similarity",
                },
                "distribution": {
                    "core": {"total": 5},
                    "isolated": {"total": 2},
                },
                "similarity_pairs": [],
            }
        )
        prev_path = tmp_path / "prev_cached_skip_similarity.json"
        prev_path.write_text(json.dumps(prev_report), encoding="utf-8")

        current = _make_org_result(include_similarity=True)
        comparison = compare_org_reports(current, str(prev_path))

        assert comparison.previous_timestamp == "2024-08-01T10:00:00Z"
        assert comparison.summary["data_views_delta"] == 0
        assert comparison.summary["resolved_duplicates"] == 0
        assert comparison.resolved_pairs == []

    def test_compare_rejects_previous_reports_with_persisted_manual_override(self, tmp_path):
        prev_report = _mark_full_fidelity_baseline(
            {
                "generated_at": "2024-08-01T10:00:00Z",
                "_snapshot_meta": {
                    "snapshot_id": "persisted-123",
                    "history_eligible": False,
                    "history_exclusion_reason": "manual_override",
                },
                "data_views": [
                    {"data_view_id": "dv_001", "data_view_name": "Data View 1", "error": None},
                    {"data_view_id": "dv_002", "data_view_name": "Data View 2", "error": None},
                    {"data_view_id": "dv_003", "data_view_name": "Data View 3", "error": None},
                ],
                "summary": {
                    "data_views_total": 3,
                    "data_views_analyzed": 3,
                    "total_unique_components": 20,
                },
                "distribution": {
                    "core": {"total": 5},
                    "isolated": {"total": 2},
                },
                "similarity_pairs": [],
            }
        )
        prev_path = tmp_path / "prev_manual_override.json"
        prev_path.write_text(json.dumps(prev_report), encoding="utf-8")

        current = _make_org_result(include_similarity=True)

        with pytest.raises(ValueError, match="manual_override"):
            compare_org_reports(current, str(prev_path))

    @pytest.mark.parametrize("payload", [([1, 2, 3],), ("scalar-root",), (7,)])
    def test_compare_rejects_previous_reports_with_non_object_json_root(self, tmp_path, payload):
        prev_path = tmp_path / "prev_non_object.json"
        prev_path.write_text(json.dumps(payload), encoding="utf-8")

        current = _make_org_result(include_similarity=True)

        with pytest.raises(ValueError, match=r"Previous report .*expected org-report snapshot payload"):
            compare_org_reports(current, str(prev_path))

    def test_compare_rejects_current_reports_with_failed_data_views(self, tmp_path):
        """Current partial results should fail closed instead of emitting drift deltas."""
        prev_report = _mark_full_fidelity_baseline(
            {
                "generated_at": "2024-08-01T10:00:00Z",
                "data_views": [
                    {"data_view_id": "dv_001", "data_view_name": "Data View 1"},
                    {"data_view_id": "dv_002", "data_view_name": "Data View 2"},
                    {"data_view_id": "dv_003", "data_view_name": "Data View 3"},
                ],
                "summary": {"total_unique_components": 20},
                "distribution": {
                    "core": {"total": 5},
                    "isolated": {"total": 2},
                },
                "similarity_pairs": [],
            }
        )
        prev_path = tmp_path / "prev_blank_error.json"
        prev_path.write_text(json.dumps(prev_report), encoding="utf-8")

        current = _make_org_result(include_similarity=True)
        current.data_view_summaries[0] = _make_data_view_summary("dv_001", "Data View 1", error="")

        with pytest.raises(
            ValueError,
            match=r"Current org-report is not eligible for comparison: .*incomplete_data_views",
        ):
            compare_org_reports(current, str(prev_path))

    def test_compare_allows_current_reports_with_missing_data_view_ids_but_suppresses_exact_dv_lists(
        self,
        tmp_path,
    ):
        prev_report = _mark_full_fidelity_baseline(
            {
                "generated_at": "2024-08-01T10:00:00Z",
                "data_views": [
                    {"data_view_id": "dv_001", "data_view_name": "Data View 1"},
                    {"data_view_id": "dv_002", "data_view_name": "Data View 2"},
                    {"data_view_id": "dv_003", "data_view_name": "Data View 3"},
                ],
                "summary": {"total_unique_components": 20},
                "distribution": {
                    "core": {"total": 5},
                    "isolated": {"total": 2},
                },
                "similarity_pairs": [],
            }
        )
        prev_path = tmp_path / "prev_missing_current_id.json"
        prev_path.write_text(json.dumps(prev_report), encoding="utf-8")

        current = _make_org_result(include_similarity=True)
        current.data_view_summaries[1] = _make_data_view_summary("", "Missing Data View 2")

        comparison = compare_org_reports(current, str(prev_path))

        assert comparison.data_views_added == []
        assert comparison.data_views_removed == []
        assert comparison.summary["data_views_delta"] == 0
        assert comparison.new_high_similarity_pairs == []
        assert comparison.resolved_pairs == []

    def test_compare_allows_current_reports_with_duplicate_normalized_data_view_ids_but_suppresses_exact_dv_lists(
        self,
        tmp_path,
    ):
        prev_report = _mark_full_fidelity_baseline(
            {
                "generated_at": "2024-08-01T10:00:00Z",
                "data_views": [
                    {"data_view_id": "dv_001", "data_view_name": "Data View 1"},
                    {"data_view_id": "dv_002", "data_view_name": "Data View 2"},
                    {"data_view_id": "dv_003", "data_view_name": "Data View 3"},
                ],
                "summary": {"total_unique_components": 20},
                "distribution": {
                    "core": {"total": 5},
                    "isolated": {"total": 2},
                },
                "similarity_pairs": [],
            }
        )
        prev_path = tmp_path / "prev_duplicate_current.json"
        prev_path.write_text(json.dumps(prev_report), encoding="utf-8")

        current = _make_org_result(include_similarity=True)
        current.data_view_summaries[1] = _make_data_view_summary(" dv_001 ", "Duplicate Data View 1")

        comparison = compare_org_reports(current, str(prev_path))

        assert comparison.data_views_added == []
        assert comparison.data_views_removed == []
        assert comparison.summary["data_views_delta"] == 0
        assert comparison.new_high_similarity_pairs == []
        assert comparison.resolved_pairs == []

    def test_compare_rejects_current_reports_with_duplicate_exact_raw_data_view_ids(self, tmp_path):
        prev_report = _mark_full_fidelity_baseline(
            {
                "generated_at": "2024-08-01T10:00:00Z",
                "data_views": [
                    {"data_view_id": "dv_001", "data_view_name": "Data View 1"},
                    {"data_view_id": "dv_002", "data_view_name": "Data View 2"},
                    {"data_view_id": "dv_003", "data_view_name": "Data View 3"},
                ],
                "summary": {"total_unique_components": 20},
                "distribution": {
                    "core": {"total": 5},
                    "isolated": {"total": 2},
                },
                "similarity_pairs": [],
            }
        )
        prev_path = tmp_path / "prev_duplicate_current_raw_id.json"
        prev_path.write_text(json.dumps(prev_report), encoding="utf-8")

        current = _make_org_result(include_similarity=True)
        current.data_view_summaries[1] = _make_data_view_summary("dv_001", "Duplicate Data View 1")

        with pytest.raises(
            ValueError,
            match=r"Current org-report is not eligible for comparison: .*incomplete_data_views",
        ):
            compare_org_reports(current, str(prev_path))

    def test_compare_rejects_incomplete_previous_reports(self, tmp_path):
        prev_report = _mark_full_fidelity_baseline(
            {
                "generated_at": "2024-08-01T10:00:00Z",
                "data_views": [
                    {"data_view_id": "dv_001", "data_view_name": "Data View 1", "error": None},
                    {"data_view_id": "dv_002", "data_view_name": "Data View 2", "error": "timeout"},
                    {"data_view_id": "dv_003", "data_view_name": "Data View 3", "error": None},
                ],
                "summary": {
                    "data_views_total": 3,
                    "data_views_analyzed": 2,
                    "total_unique_components": 20,
                },
                "distribution": {
                    "core": {"total": 5},
                    "isolated": {"total": 2},
                },
                "similarity_pairs": [],
            }
        )
        prev_path = tmp_path / "prev_partial_failure.json"
        prev_path.write_text(json.dumps(prev_report), encoding="utf-8")

        current = _make_org_result(include_similarity=True)
        current.data_view_summaries = [
            _make_data_view_summary("dv_001", "Data View 1"),
            _make_data_view_summary("dv_003", "Data View 3"),
        ]

        with pytest.raises(ValueError, match="incomplete_data_views"):
            compare_org_reports(current, str(prev_path))

    def test_compare_rejects_previous_reports_with_compact_rows(self, tmp_path):
        prev_report = _mark_full_fidelity_baseline(
            {
                "generated_at": "2024-08-01T10:00:00Z",
                "data_views": [
                    {"data_view_id": "dv_001", "data_view_name": "Data View 1", "error": None},
                    {"data_view_id": "dv_002", "data_view_name": "Data View 2", "error": None},
                ],
                "summary": {
                    "data_views_total": 3,
                    "data_views_analyzed": 3,
                    "total_unique_components": 20,
                },
                "distribution": {
                    "core": {"total": 5},
                    "isolated": {"total": 2},
                },
                "similarity_pairs": [],
            }
        )
        prev_path = tmp_path / "prev_compact_rows.json"
        prev_path.write_text(json.dumps(prev_report), encoding="utf-8")

        current = _make_org_result(include_similarity=True)

        with pytest.raises(ValueError, match="incomplete_data_views"):
            compare_org_reports(current, str(prev_path))

    def test_compare_allows_previous_reports_with_missing_data_view_ids_but_suppresses_exact_dv_lists(
        self,
        tmp_path,
    ):
        prev_report = _mark_full_fidelity_baseline(
            {
                "generated_at": "2024-08-01T10:00:00Z",
                "data_views": [
                    {"data_view_id": "dv_001", "data_view_name": "Data View 1", "error": None},
                    {"data_view_name": "Missing ID", "error": None},
                ],
                "summary": {
                    "data_views_total": 2,
                    "data_views_analyzed": 2,
                    "total_unique_components": 20,
                },
                "distribution": {
                    "core": {"total": 5},
                    "isolated": {"total": 2},
                },
                "similarity_pairs": [],
            }
        )
        prev_path = tmp_path / "prev_missing_id.json"
        prev_path.write_text(json.dumps(prev_report), encoding="utf-8")

        current = _make_org_result(include_similarity=True)

        comparison = compare_org_reports(current, str(prev_path))

        assert comparison.data_views_added == []
        assert comparison.data_views_removed == []
        assert comparison.summary["data_views_delta"] == 1
        assert comparison.new_high_similarity_pairs == []
        assert comparison.resolved_pairs == []

    def test_compare_allows_previous_reports_with_blank_legacy_aliases_when_id_fallbacks_are_unique(
        self,
        tmp_path,
    ):
        prev_report = _mark_full_fidelity_baseline(
            {
                "generated_at": "2024-08-01T10:00:00Z",
                "data_views": [
                    {"data_view_id": "", "id": "dv_001", "data_view_name": "Data View 1", "error": None},
                    {"data_view_id": "   ", "id": "dv_002", "data_view_name": "Data View 2", "error": None},
                    {"data_view_id": None, "id": "dv_003", "data_view_name": "Data View 3", "error": None},
                ],
                "summary": {
                    "data_views_total": 3,
                    "data_views_analyzed": 3,
                    "total_unique_components": 20,
                },
                "distribution": {
                    "core": {"total": 5},
                    "isolated": {"total": 2},
                },
                "similarity_pairs": [
                    {
                        "dv1_id": "",
                        "dv2_id": "   ",
                        "data_view_1": {"id": "dv_001"},
                        "data_view_2": {"id": "dv_002"},
                        "jaccard_similarity": 0.95,
                    }
                ],
            }
        )
        prev_path = tmp_path / "prev_blank_legacy_alias_id.json"
        prev_path.write_text(json.dumps(prev_report), encoding="utf-8")

        current = _make_org_result(include_similarity=True)

        comparison = compare_org_reports(current, str(prev_path))

        assert comparison.data_views_added == []
        assert comparison.data_views_removed == []
        assert comparison.summary["data_views_delta"] == 0
        assert comparison.new_high_similarity_pairs == []
        assert comparison.resolved_pairs == []

    def test_compare_rejects_previous_reports_with_duplicate_exact_raw_data_view_ids(self, tmp_path):
        prev_report = _mark_full_fidelity_baseline(
            {
                "generated_at": "2024-08-01T10:00:00Z",
                "data_views": [
                    {"data_view_id": "dv_001", "data_view_name": "Data View 1", "error": None},
                    {"id": "dv_001", "name": "Duplicate Data View 1", "error": None},
                ],
                "summary": {
                    "data_views_total": 2,
                    "data_views_analyzed": 2,
                    "total_unique_components": 20,
                },
                "distribution": {
                    "core": {"total": 5},
                    "isolated": {"total": 2},
                },
                "similarity_pairs": [],
            }
        )
        prev_path = tmp_path / "prev_duplicate_exact_raw_id.json"
        prev_path.write_text(json.dumps(prev_report), encoding="utf-8")

        current = _make_org_result(include_similarity=True)

        with pytest.raises(ValueError, match="incomplete_data_views"):
            compare_org_reports(current, str(prev_path))

    def test_compare_allows_previous_reports_with_duplicate_normalized_data_view_ids_but_suppresses_exact_dv_lists(
        self,
        tmp_path,
    ):
        prev_report = _mark_full_fidelity_baseline(
            {
                "generated_at": "2024-08-01T10:00:00Z",
                "data_views": [
                    {"data_view_id": "dv_001", "data_view_name": "Data View 1", "error": None},
                    {"id": " dv_001 ", "name": "Duplicate Data View 1", "error": None},
                ],
                "summary": {
                    "data_views_total": 2,
                    "data_views_analyzed": 2,
                    "total_unique_components": 20,
                },
                "distribution": {
                    "core": {"total": 5},
                    "isolated": {"total": 2},
                },
                "similarity_pairs": [],
            }
        )
        prev_path = tmp_path / "prev_duplicate_id.json"
        prev_path.write_text(json.dumps(prev_report), encoding="utf-8")

        current = _make_org_result(include_similarity=True)

        comparison = compare_org_reports(current, str(prev_path))

        assert comparison.data_views_added == []
        assert comparison.data_views_removed == []
        assert comparison.summary["data_views_delta"] == 1
        assert comparison.new_high_similarity_pairs == []
        assert comparison.resolved_pairs == []

    def test_compare_uses_exact_component_ids_when_available(self, tmp_path):
        prev_report = _mark_full_fidelity_baseline(
            {
                "generated_at": "2024-08-01T10:00:00Z",
                "data_views": [{"data_view_id": "dv_001", "data_view_name": "Data View 1"}],
                "summary": {"total_unique_components": 2},
                "component_index": {
                    "shared": {"type": "metric", "data_views": ["dv_001"]},
                    "removed": {"type": "dimension", "data_views": ["dv_001"]},
                },
                "distribution": {
                    "core": {"total": 1},
                    "isolated": {"total": 1},
                },
                "similarity_pairs": [],
            }
        )
        prev_path = tmp_path / "prev_exact_components.json"
        prev_path.write_text(json.dumps(prev_report), encoding="utf-8")

        current = OrgReportResult(
            timestamp="2025-01-15T10:00:00Z",
            org_id="test_org",
            parameters=OrgReportConfig(),
            data_view_summaries=[_make_data_view_summary("dv_001", "Data View 1")],
            component_index={
                "shared": _make_component_info("shared", data_views=["dv_001"]),
                "added_1": _make_component_info("added_1", data_views=["dv_001"]),
                "added_2": _make_component_info("added_2", data_views=["dv_001"]),
            },
            distribution=ComponentDistribution(),
            similarity_pairs=[],
            recommendations=[],
            duration=1.0,
        )

        comparison = compare_org_reports(current, str(prev_path))

        assert comparison.components_added == 2
        assert comparison.components_removed == 1
        assert comparison.summary["components_delta"] == 1

    def test_compare_rejects_cached_markerless_legacy_baseline(self, tmp_path):
        prev_report = {
            "generated_at": "2024-08-01T10:00:00Z",
            "_snapshot_meta": {
                "snapshot_id": "persisted-123",
                "history_eligible": True,
                "history_exclusion_reason": None,
            },
            "data_views": [{"data_view_id": "dv_001", "data_view_name": "Data View 1"}],
            "summary": {"total_unique_components": 2},
            "distribution": {"core": {"total": 1}, "isolated": {"total": 1}},
            "similarity_pairs": [],
        }
        prev_path = tmp_path / "prev_legacy.json"
        prev_path.write_text(json.dumps(prev_report), encoding="utf-8")

        current = _make_org_result(include_similarity=True)

        with pytest.raises(ValueError, match="legacy_missing_fidelity_markers"):
            compare_org_reports(current, str(prev_path))


# ===================================================================
# write_org_report_console
# ===================================================================


class TestWriteOrgReportConsole:
    """Tests for write_org_report_console()."""

    def test_console_output_basic(self, capsys):
        result = _make_org_result()
        config = OrgReportConfig()
        write_org_report_console(result, config)

        captured = capsys.readouterr().out
        assert "ORG-WIDE COMPONENT ANALYSIS REPORT" in captured
        assert "test_org_123" in captured
        assert "DATA VIEWS" in captured
        assert "COMPONENT SUMMARY" in captured
        assert "DISTRIBUTION" in captured
        assert "HIGH OVERLAP PAIRS" in captured
        assert "RECOMMENDATIONS" in captured

    def test_console_quiet_mode(self, capsys):
        result = _make_org_result()
        config = OrgReportConfig()
        write_org_report_console(result, config, quiet=True)
        assert capsys.readouterr().out == ""

    def test_console_sampled_report(self, capsys):
        result = _make_org_result(is_sampled=True)
        config = OrgReportConfig()
        write_org_report_console(result, config)

        captured = capsys.readouterr().out
        assert "[SAMPLED]" in captured
        assert "sampled from" in captured

    def test_console_with_error_dv(self, capsys):
        result = _make_org_result()
        result.data_view_summaries.append(_make_data_view_summary("dv_err", "Error DV", error="Fetch failed"))
        config = OrgReportConfig()
        write_org_report_console(result, config)

        captured = capsys.readouterr().out
        assert "ERROR" in captured
        assert "Data View Fetch Failures: 1" in captured

    def test_console_core_min_count_label(self, capsys):
        result = _make_org_result(config_overrides={"core_min_count": 5})
        config = result.parameters
        write_org_report_console(result, config)

        captured = capsys.readouterr().out
        assert ">=5" in captured

    def test_console_summary_only_skips_core_details(self, capsys):
        result = _make_org_result(config_overrides={"summary_only": True})
        config = result.parameters
        write_org_report_console(result, config)

        captured = capsys.readouterr().out
        assert "CORE COMPONENTS" not in captured

    def test_console_with_named_core_components(self, capsys):
        result = _make_org_result(include_names=True)
        config = OrgReportConfig()
        write_org_report_console(result, config)

        captured = capsys.readouterr().out
        assert "Core Metric" in captured

    def test_console_core_metrics_ellipsis_over_15(self, capsys):
        result = _make_org_result(num_core_metrics=18)
        config = OrgReportConfig()
        write_org_report_console(result, config)

        captured = capsys.readouterr().out
        assert "... and 3 more" in captured

    def test_console_core_dimensions_ellipsis_over_15(self, capsys):
        result = _make_org_result(num_core_dims=18)
        config = OrgReportConfig()
        write_org_report_console(result, config)

        captured = capsys.readouterr().out
        assert "... and 3 more" in captured

    def test_console_drift_details(self, capsys):
        result = _make_org_result(config_overrides={"include_drift": True})
        # Add drift data to similarity pairs
        result.similarity_pairs[0].only_in_dv1 = ["comp_a", "comp_b", "comp_c", "comp_d"]
        result.similarity_pairs[0].only_in_dv2 = ["comp_x", "comp_y"]
        result.similarity_pairs[0].only_in_dv1_names = {"comp_a": "Component A"}
        result.similarity_pairs[0].only_in_dv2_names = {"comp_x": "Component X"}
        config = result.parameters
        write_org_report_console(result, config)

        captured = capsys.readouterr().out
        assert "Drift Details" in captured
        assert "Component A" in captured
        assert "... and 1 more" in captured

    def test_console_clusters_section(self, capsys):
        result = _make_org_result(include_clusters=True)
        config = OrgReportConfig()
        write_org_report_console(result, config)

        captured = capsys.readouterr().out
        assert "DATA VIEW CLUSTERS" in captured
        assert "Analytics Cluster" in captured

    def test_console_governance_violations(self, capsys):
        result = _make_org_result(include_governance_violations=True)
        config = OrgReportConfig()
        write_org_report_console(result, config)

        captured = capsys.readouterr().out
        assert "GOVERNANCE VIOLATIONS" in captured
        assert "Too many high-similarity pairs" in captured

    def test_console_owner_summary(self, capsys):
        result = _make_org_result(include_owner_summary=True)
        config = OrgReportConfig()
        write_org_report_console(result, config)

        captured = capsys.readouterr().out
        assert "OWNER SUMMARY" in captured
        assert "Alice" in captured

    def test_console_naming_audit(self, capsys):
        result = _make_org_result(include_naming_audit=True)
        config = OrgReportConfig()
        write_org_report_console(result, config)

        captured = capsys.readouterr().out
        assert "NAMING AUDIT" in captured
        assert "camelCase" in captured
        assert "Mixed naming" in captured

    def test_console_stale_components(self, capsys):
        result = _make_org_result(include_stale=True)
        config = OrgReportConfig()
        write_org_report_console(result, config)

        captured = capsys.readouterr().out
        assert "STALE COMPONENTS" in captured
        assert "deprecated_prefix" in captured

    def test_console_component_types_section(self, capsys):
        result = _make_org_result(config_overrides={"include_component_types": True, "summary_only": False})
        config = result.parameters
        write_org_report_console(result, config)

        captured = capsys.readouterr().out
        assert "COMPONENT TYPES" in captured

    def test_console_overlap_threshold_capped(self, capsys):
        result = _make_org_result(config_overrides={"overlap_threshold": 0.95})
        config = result.parameters
        write_org_report_console(result, config)

        captured = capsys.readouterr().out
        assert "capped at 90%" in captured

    def test_console_long_dv_name_truncated(self, capsys):
        result = _make_org_result()
        result.data_view_summaries[0].data_view_name = "A" * 55
        config = OrgReportConfig()
        write_org_report_console(result, config)

        captured = capsys.readouterr().out
        assert ".." in captured


# ===================================================================
# write_org_report_stats_only
# ===================================================================


class TestWriteOrgReportStatsOnly:
    """Tests for write_org_report_stats_only()."""

    def test_stats_only_output(self, capsys):
        result = _make_org_result()
        write_org_report_stats_only(result)

        captured = capsys.readouterr().out
        assert "ORG STATS" in captured
        assert "test_org_123" in captured
        assert "Data Views:" in captured
        assert "Fetch Failures:" in captured
        assert "Components:" in captured
        assert "Distribution:" in captured

    def test_stats_only_quiet(self, capsys):
        result = _make_org_result()
        write_org_report_stats_only(result, quiet=True)
        assert capsys.readouterr().out == ""


# ===================================================================
# write_org_report_comparison_console
# ===================================================================


class TestWriteOrgReportComparisonConsole:
    """Tests for write_org_report_comparison_console()."""

    def _make_comparison(
        self,
        added=None,
        removed=None,
        new_sim_pairs=None,
        resolved_pairs=None,
    ):
        return OrgReportComparison(
            current_timestamp="2025-01-15T10:00:00Z",
            previous_timestamp="2024-12-01T10:00:00Z",
            data_views_added=added or [],
            data_views_removed=removed or [],
            data_views_added_names=[f"Added DV {i}" for i in range(len(added or []))],
            data_views_removed_names=[f"Removed DV {i}" for i in range(len(removed or []))],
            components_added=5,
            components_removed=2,
            core_delta=1,
            isolated_delta=-1,
            new_high_similarity_pairs=new_sim_pairs or [],
            resolved_pairs=resolved_pairs or [],
            summary={
                "data_views_delta": len(added or []) - len(removed or []),
                "components_delta": 3,
                "core_delta": 1,
                "isolated_delta": -1,
                "new_duplicates": len(new_sim_pairs or []),
                "resolved_duplicates": len(resolved_pairs or []),
            },
        )

    def test_comparison_basic_output(self, capsys):
        comparison = self._make_comparison()
        write_org_report_comparison_console(comparison)

        captured = capsys.readouterr().out
        assert "ORG REPORT COMPARISON" in captured
        assert "CHANGES" in captured

    def test_comparison_quiet(self, capsys):
        comparison = self._make_comparison()
        write_org_report_comparison_console(comparison, quiet=True)
        assert capsys.readouterr().out == ""

    def test_comparison_with_added_dvs(self, capsys):
        comparison = self._make_comparison(added=["dv_new_1", "dv_new_2"])
        write_org_report_comparison_console(comparison)

        captured = capsys.readouterr().out
        assert "Data Views Added (2)" in captured

    def test_comparison_with_removed_dvs(self, capsys):
        comparison = self._make_comparison(removed=["dv_old_1"])
        write_org_report_comparison_console(comparison)

        captured = capsys.readouterr().out
        assert "Data Views Removed (1)" in captured

    def test_comparison_with_new_sim_pairs(self, capsys):
        comparison = self._make_comparison(
            new_sim_pairs=[{"dv1_id": "dv_001", "dv2_id": "dv_002"}],
        )
        write_org_report_comparison_console(comparison)

        captured = capsys.readouterr().out
        assert "New High-Similarity Pairs" in captured

    def test_comparison_with_resolved_pairs(self, capsys):
        comparison = self._make_comparison(
            resolved_pairs=[{"dv1_id": "dv_001", "dv2_id": "dv_003"}],
        )
        write_org_report_comparison_console(comparison)

        captured = capsys.readouterr().out
        assert "Resolved High-Similarity Pairs" in captured

    def test_comparison_trend_arrows(self, capsys):
        comparison = self._make_comparison(added=["dv_x"])
        write_org_report_comparison_console(comparison)

        captured = capsys.readouterr().out
        # Positive delta should show up-arrow
        assert "\u2191" in captured or "↑" in captured


# ===================================================================
# write_org_report_json
# ===================================================================


class TestWriteOrgReportJson:
    """Tests for write_org_report_json()."""

    def test_json_with_explicit_path(self, tmp_path):
        result = _make_org_result()
        logger = logging.getLogger("test_json")
        out_path = tmp_path / "report.json"

        returned = write_org_report_json(result, out_path, str(tmp_path), logger)
        assert Path(returned).exists()

        data = json.loads(Path(returned).read_text(encoding="utf-8"))
        assert data["report_type"] == "org_analysis"
        assert data["org_id"] == "test_org_123"

    def test_json_auto_generated_path(self, tmp_path):
        result = _make_org_result()
        logger = logging.getLogger("test_json_auto")

        returned = write_org_report_json(result, None, str(tmp_path), logger)
        assert Path(returned).exists()
        assert "org_report_test_org_123" in returned

    def test_json_adds_extension_if_missing(self, tmp_path):
        result = _make_org_result()
        logger = logging.getLogger("test_json_ext")
        out_path = tmp_path / "report_no_ext"

        returned = write_org_report_json(result, out_path, str(tmp_path), logger)
        assert returned.endswith(".json")


# ===================================================================
# write_org_report_excel
# ===================================================================


class TestWriteOrgReportExcel:
    """Tests for write_org_report_excel()."""

    def test_excel_basic(self, tmp_path):
        result = _make_org_result()
        logger = logging.getLogger("test_excel")
        out_path = tmp_path / "report.xlsx"

        returned = write_org_report_excel(result, out_path, str(tmp_path), logger)
        assert Path(returned).exists()
        assert returned.endswith(".xlsx")

    def test_excel_auto_generated_path(self, tmp_path):
        result = _make_org_result()
        logger = logging.getLogger("test_excel_auto")

        returned = write_org_report_excel(result, None, str(tmp_path), logger)
        assert Path(returned).exists()

    def test_excel_with_sampling_info(self, tmp_path):
        result = _make_org_result(is_sampled=True)
        logger = logging.getLogger("test_excel_sampled")
        out_path = tmp_path / "sampled.xlsx"

        returned = write_org_report_excel(result, out_path, str(tmp_path), logger)
        assert Path(returned).exists()

    def test_excel_with_clusters(self, tmp_path):
        result = _make_org_result(include_clusters=True)
        logger = logging.getLogger("test_excel_clusters")
        out_path = tmp_path / "clusters.xlsx"

        returned = write_org_report_excel(result, out_path, str(tmp_path), logger)
        assert Path(returned).exists()

    def test_excel_with_drift(self, tmp_path):
        result = _make_org_result(config_overrides={"include_drift": True})
        result.similarity_pairs[0].only_in_dv1 = ["comp_a"]
        result.similarity_pairs[0].only_in_dv2 = ["comp_b"]
        logger = logging.getLogger("test_excel_drift")
        out_path = tmp_path / "drift.xlsx"

        returned = write_org_report_excel(result, out_path, str(tmp_path), logger)
        assert Path(returned).exists()

    def test_excel_with_metadata(self, tmp_path):
        result = _make_org_result(config_overrides={"include_metadata": True})
        logger = logging.getLogger("test_excel_meta")
        out_path = tmp_path / "metadata.xlsx"

        returned = write_org_report_excel(result, out_path, str(tmp_path), logger)
        assert Path(returned).exists()

    def test_excel_with_recommendations(self, tmp_path):
        result = _make_org_result(include_recommendations=True)
        logger = logging.getLogger("test_excel_recs")
        out_path = tmp_path / "recs.xlsx"

        returned = write_org_report_excel(result, out_path, str(tmp_path), logger)
        assert Path(returned).exists()


# ===================================================================
# write_org_report_markdown
# ===================================================================


class TestWriteOrgReportMarkdown:
    """Tests for write_org_report_markdown()."""

    def test_markdown_basic(self, tmp_path):
        result = _make_org_result()
        logger = logging.getLogger("test_md")
        out_path = tmp_path / "report.md"

        returned = write_org_report_markdown(result, out_path, str(tmp_path), logger)
        content = Path(returned).read_text(encoding="utf-8")
        assert "# Org-Wide Component Analysis Report" in content
        assert "test_org_123" in content
        assert "## Summary" in content
        assert "## Component Distribution" in content
        assert "## Data Views" in content

    def test_markdown_auto_generated_path(self, tmp_path):
        result = _make_org_result()
        logger = logging.getLogger("test_md_auto")

        returned = write_org_report_markdown(result, None, str(tmp_path), logger)
        assert Path(returned).exists()
        assert returned.endswith(".md")

    def test_markdown_core_metrics_ellipsis_no_names(self, tmp_path):
        """Cover line 11730: ellipsis row for >20 core metrics without names."""
        result = _make_org_result(num_core_metrics=25, include_names=False)
        logger = logging.getLogger("test_md_ellipsis_metrics")
        out_path = tmp_path / "ellipsis_metrics.md"

        returned = write_org_report_markdown(result, out_path, str(tmp_path), logger)
        content = Path(returned).read_text(encoding="utf-8")
        assert "*... 5 more*" in content

    def test_markdown_core_dimensions_ellipsis_no_names(self, tmp_path):
        """Cover line 11754: ellipsis row for >20 core dimensions without names."""
        result = _make_org_result(num_core_dims=25, include_names=False)
        logger = logging.getLogger("test_md_ellipsis_dims")
        out_path = tmp_path / "ellipsis_dims.md"

        returned = write_org_report_markdown(result, out_path, str(tmp_path), logger)
        content = Path(returned).read_text(encoding="utf-8")
        assert "*... 5 more*" in content

    def test_markdown_core_metrics_ellipsis_with_names(self, tmp_path):
        """Cover ellipsis row for >20 core metrics WITH names (three-column table)."""
        result = _make_org_result(num_core_metrics=25, include_names=True)
        logger = logging.getLogger("test_md_ellipsis_names")
        out_path = tmp_path / "ellipsis_names.md"

        returned = write_org_report_markdown(result, out_path, str(tmp_path), logger)
        content = Path(returned).read_text(encoding="utf-8")
        assert "*... 5 more*" in content
        # With names, ellipsis row has 3 columns (extra pipe)
        # Check that the line has the right number of columns
        for line in content.splitlines():
            if "*... 5 more*" in line and "Core Metric" not in line:
                assert line.count("|") >= 4  # | ... | | |
                break

    def test_markdown_core_min_count_label(self, tmp_path):
        result = _make_org_result(config_overrides={"core_min_count": 3})
        logger = logging.getLogger("test_md_min_count")
        out_path = tmp_path / "min_count.md"

        returned = write_org_report_markdown(result, out_path, str(tmp_path), logger)
        content = Path(returned).read_text(encoding="utf-8")
        assert ">=3" in content

    def test_markdown_with_error_dv(self, tmp_path):
        result = _make_org_result()
        result.data_view_summaries.append(_make_data_view_summary("dv_err", "Error DV", error="API timeout"))
        logger = logging.getLogger("test_md_error")
        out_path = tmp_path / "error_dv.md"

        returned = write_org_report_markdown(result, out_path, str(tmp_path), logger)
        content = Path(returned).read_text(encoding="utf-8")
        assert "ERROR" in content
        assert "| Data View Fetch Failures | 1 |" in content

    def test_markdown_similarity_pairs(self, tmp_path):
        result = _make_org_result(include_similarity=True)
        logger = logging.getLogger("test_md_sim")
        out_path = tmp_path / "sim.md"

        returned = write_org_report_markdown(result, out_path, str(tmp_path), logger)
        content = Path(returned).read_text(encoding="utf-8")
        assert "## High Overlap Pairs" in content

    def test_markdown_recommendations(self, tmp_path):
        result = _make_org_result(include_recommendations=True)
        logger = logging.getLogger("test_md_recs")
        out_path = tmp_path / "recs.md"

        returned = write_org_report_markdown(result, out_path, str(tmp_path), logger)
        content = Path(returned).read_text(encoding="utf-8")
        assert "## Recommendations" in content

    def test_markdown_overlap_threshold_note(self, tmp_path):
        result = _make_org_result(config_overrides={"overlap_threshold": 0.95})
        logger = logging.getLogger("test_md_thresh")
        out_path = tmp_path / "thresh.md"

        returned = write_org_report_markdown(result, out_path, str(tmp_path), logger)
        content = Path(returned).read_text(encoding="utf-8")
        assert "capped at 90%" in content


# ===================================================================
# write_org_report_html
# ===================================================================


class TestWriteOrgReportHtml:
    """Tests for write_org_report_html()."""

    def test_html_basic(self, tmp_path):
        result = _make_org_result()
        logger = logging.getLogger("test_html")
        out_path = tmp_path / "report.html"

        returned = write_org_report_html(result, out_path, str(tmp_path), logger)
        content = Path(returned).read_text(encoding="utf-8")
        assert "<!DOCTYPE html>" in content
        assert "Org-Wide Component Analysis Report" in content
        assert "test_org_123" in content

    def test_html_auto_generated_path(self, tmp_path):
        result = _make_org_result()
        logger = logging.getLogger("test_html_auto")

        returned = write_org_report_html(result, None, str(tmp_path), logger)
        assert Path(returned).exists()
        assert returned.endswith(".html")

    def test_html_with_core_components(self, tmp_path):
        result = _make_org_result(include_names=True)
        logger = logging.getLogger("test_html_core")
        out_path = tmp_path / "core.html"

        returned = write_org_report_html(result, out_path, str(tmp_path), logger)
        content = Path(returned).read_text(encoding="utf-8")
        assert "Core Components" in content
        assert "Core Metric" in content

    def test_html_with_similarity_pairs(self, tmp_path):
        result = _make_org_result(include_similarity=True)
        logger = logging.getLogger("test_html_sim")
        out_path = tmp_path / "sim.html"

        returned = write_org_report_html(result, out_path, str(tmp_path), logger)
        content = Path(returned).read_text(encoding="utf-8")
        assert "High Overlap Pairs" in content

    def test_html_with_recommendations(self, tmp_path):
        result = _make_org_result(include_recommendations=True)
        logger = logging.getLogger("test_html_recs")
        out_path = tmp_path / "recs.html"

        returned = write_org_report_html(result, out_path, str(tmp_path), logger)
        content = Path(returned).read_text(encoding="utf-8")
        assert "Recommendations" in content
        assert "badge-high" in content

    def test_html_core_min_count_label(self, tmp_path):
        result = _make_org_result(config_overrides={"core_min_count": 4})
        logger = logging.getLogger("test_html_min")
        out_path = tmp_path / "min.html"

        returned = write_org_report_html(result, out_path, str(tmp_path), logger)
        content = Path(returned).read_text(encoding="utf-8")
        assert "&gt;=4" in content

    def test_html_with_error_dv(self, tmp_path):
        result = _make_org_result()
        result.data_view_summaries.append(_make_data_view_summary("dv_err", "Error<script>DV", error="<b>fail</b>"))
        logger = logging.getLogger("test_html_error")
        out_path = tmp_path / "error.html"

        returned = write_org_report_html(result, out_path, str(tmp_path), logger)
        content = Path(returned).read_text(encoding="utf-8")
        # HTML-escaped error text
        assert "&lt;b&gt;fail&lt;/b&gt;" in content
        assert "Data View Fetch Failures" in content

    def test_html_overlap_threshold_note(self, tmp_path):
        result = _make_org_result(config_overrides={"overlap_threshold": 0.95})
        logger = logging.getLogger("test_html_thresh")
        out_path = tmp_path / "thresh.html"

        returned = write_org_report_html(result, out_path, str(tmp_path), logger)
        content = Path(returned).read_text(encoding="utf-8")
        assert "capped at 90%" in content


# ===================================================================
# write_org_report_csv
# ===================================================================


class TestWriteOrgReportCsv:
    """Tests for write_org_report_csv()."""

    def test_csv_basic(self, tmp_path):
        result = _make_org_result()
        logger = logging.getLogger("test_csv")

        returned = write_org_report_csv(result, None, str(tmp_path), logger)
        csv_dir = Path(returned)
        assert csv_dir.is_dir()
        assert (csv_dir / "org_report_summary.csv").exists()
        assert (csv_dir / "org_report_data_views.csv").exists()
        assert (csv_dir / "org_report_components.csv").exists()
        assert (csv_dir / "org_report_distribution.csv").exists()

    def test_csv_with_similarity(self, tmp_path):
        result = _make_org_result(include_similarity=True)
        logger = logging.getLogger("test_csv_sim")

        returned = write_org_report_csv(result, None, str(tmp_path), logger)
        csv_dir = Path(returned)
        assert (csv_dir / "org_report_similarity.csv").exists()

    def test_csv_with_recommendations(self, tmp_path):
        result = _make_org_result(include_recommendations=True)
        logger = logging.getLogger("test_csv_recs")

        returned = write_org_report_csv(result, None, str(tmp_path), logger)
        csv_dir = Path(returned)
        assert (csv_dir / "org_report_recommendations.csv").exists()

    def test_csv_with_explicit_path_csv_suffix(self, tmp_path):
        """When output_path ends with .csv, use parent/stem as directory."""
        result = _make_org_result()
        logger = logging.getLogger("test_csv_suffix")
        out_path = tmp_path / "my_report.csv"

        returned = write_org_report_csv(result, out_path, str(tmp_path), logger)
        csv_dir = Path(returned)
        assert csv_dir.name == "my_report"
        assert csv_dir.is_dir()

    def test_csv_with_explicit_path_no_suffix(self, tmp_path):
        result = _make_org_result()
        logger = logging.getLogger("test_csv_nosuffix")
        out_path = tmp_path / "csv_output"

        returned = write_org_report_csv(result, out_path, str(tmp_path), logger)
        csv_dir = Path(returned)
        assert csv_dir.is_dir()

    def test_csv_summary_includes_failed_data_views(self, tmp_path):
        result = _make_org_result()
        result.data_view_summaries.append(_make_data_view_summary("dv_err", "Error DV", error="Failure"))
        logger = logging.getLogger("test_csv_failed_dvs")

        returned = write_org_report_csv(result, None, str(tmp_path), logger)
        summary_path = Path(returned) / "org_report_summary.csv"

        with summary_path.open(encoding="utf-8", newline="") as handle:
            first_row = next(csv.DictReader(handle))

        assert first_row["Failed Data Views"] == "1"

    def test_csv_data_view_rows_render_unknown_error_for_blank_failure(self, tmp_path):
        result = _make_org_result()
        result.data_view_summaries.append(_make_data_view_summary("dv_err_blank", "Error DV Blank", error=""))
        logger = logging.getLogger("test_csv_blank_error")

        returned = write_org_report_csv(result, None, str(tmp_path), logger)
        data_views_path = Path(returned) / "org_report_data_views.csv"

        with data_views_path.open(encoding="utf-8", newline="") as handle:
            rows = list(csv.DictReader(handle))

        blank_error_row = next(row for row in rows if row["Data View ID"] == "dv_err_blank")
        assert blank_error_row["Error"] == "Unknown error"


# ===================================================================
# build_org_report_json_data
# ===================================================================


class TestBuildOrgReportJsonData:
    """Tests for build_org_report_json_data()."""

    def test_json_data_structure(self):
        result = _make_org_result()
        data = build_org_report_json_data(result)

        assert data["report_type"] == "org_analysis"
        assert data["version"] == "1.0"
        assert data["org_id"] == "test_org_123"
        assert "summary" in data
        assert "distribution" in data
        assert "data_views" in data
        assert "component_index" in data
        assert "recommendations" in data
        assert data["summary"]["data_views_failed"] == 0
        assert data["summary"]["similarity_analysis_complete"] is True
        assert data["summary"]["similarity_analysis_mode"] == "complete"
        assert data["data_view_fetch_failures"]["count"] == 0
        assert data["data_view_fetch_failures"]["data_view_ids"] == []
        assert data["data_view_fetch_failures"]["failure_reason_counts"] == {}

    def test_json_data_includes_failed_data_view_telemetry(self):
        result = _make_org_result()
        result.data_view_summaries.append(_make_data_view_summary("dv_err", "Error DV", error="Failure"))
        data = build_org_report_json_data(result)

        assert data["summary"]["data_views_failed"] == 1
        assert data["data_view_fetch_failures"]["count"] == 1
        assert data["data_view_fetch_failures"]["data_view_ids"] == ["dv_err"]
        assert data["data_view_fetch_failures"]["failure_reason_counts"] == {"Failure": 1}

    def test_json_data_rolls_up_failed_data_view_reason_counts(self):
        result = _make_org_result()
        result.data_view_summaries.extend(
            [
                _make_data_view_summary("dv_err_1", "Error DV 1", error="Timeout"),
                _make_data_view_summary("dv_err_2", "Error DV 2", error="Timeout"),
                _make_data_view_summary("dv_err_3", "Error DV 3", error="Permission denied"),
            ],
        )
        data = build_org_report_json_data(result)

        assert data["data_view_fetch_failures"]["count"] == 3
        assert data["data_view_fetch_failures"]["failure_reason_counts"] == {
            "Permission denied": 1,
            "Timeout": 2,
        }

    def test_json_data_treats_empty_error_as_failed_data_view(self):
        result = _make_org_result()
        result.data_view_summaries.append(
            _make_data_view_summary(
                "dv_err_blank",
                "Error DV Blank",
                metric_count=7,
                dimension_count=4,
                error="",
            ),
        )
        data = build_org_report_json_data(result)

        assert data["summary"]["data_views_total"] == 4
        assert data["summary"]["data_views_analyzed"] == 3
        assert data["summary"]["data_views_failed"] == 1
        assert data["summary"]["total_metrics_non_unique"] == 15
        assert data["summary"]["total_dimensions_non_unique"] == 9
        assert data["summary"]["total_derived_fields_non_unique"] == 6
        assert data["data_view_fetch_failures"]["count"] == 1
        assert data["data_view_fetch_failures"]["data_view_ids"] == ["dv_err_blank"]
        assert data["data_view_fetch_failures"]["failure_reason_counts"] == {"Unknown error": 1}
        serialized_error = next(dv for dv in data["data_views"] if dv["id"] == "dv_err_blank")["error"]
        assert serialized_error == "Unknown error"

    def test_json_data_with_clusters(self):
        result = _make_org_result(include_clusters=True)
        data = build_org_report_json_data(result)

        assert data["clusters"] is not None
        assert len(data["clusters"]) == 1
        assert data["clusters"][0]["cluster_name"] == "Analytics Cluster"

    def test_json_data_without_similarity(self):
        result = _make_org_result(include_similarity=False)
        data = build_org_report_json_data(result)

        assert data["similarity_pairs"] == []
        assert data["summary"]["similarity_analysis_complete"] is False
        assert data["summary"]["similarity_analysis_mode"] == "runtime_skipped"

    def test_json_data_governance_fields(self):
        result = _make_org_result(
            include_governance_violations=True,
            include_naming_audit=True,
            include_owner_summary=True,
            include_stale=True,
        )
        data = build_org_report_json_data(result)

        assert data["governance_violations"] is not None
        assert data["thresholds_exceeded"] is True
        assert data["naming_audit"] is not None
        assert data["owner_summary"] is not None
        assert data["stale_components"] is not None

    def test_json_data_sorts_order_insensitive_snapshot_collections(self):
        result = _make_org_result()
        result.distribution.core_metrics = ["core_metric_1", "core_metric_0"]
        result.distribution.common_dimensions = ["common_d_1", "common_d_0"]
        result.component_index = {
            "zeta": _make_component_info("zeta", data_views=["dv_010", "dv_002", "dv_001"]),
            "alpha": _make_component_info("alpha", data_views=["dv_003", "dv_001"]),
        }

        data = build_org_report_json_data(result)

        assert data["distribution"]["core"]["metrics"] == ["core_metric_0", "core_metric_1"]
        assert data["distribution"]["common"]["dimensions"] == ["common_d_0", "common_d_1"]
        assert list(data["component_index"]) == ["alpha", "zeta"]
        assert data["component_index"]["alpha"]["data_views"] == ["dv_001", "dv_003"]
        assert data["component_index"]["zeta"]["data_views"] == ["dv_001", "dv_002", "dv_010"]


# ===================================================================
# _render_distribution_bar
# ===================================================================


class TestRenderDistributionBar:
    """Tests for _render_distribution_bar()."""

    def test_zero_total(self):
        bar = _render_distribution_bar(0, 0)
        assert "0%" in bar

    def test_full_bar(self):
        bar = _render_distribution_bar(100, 100)
        assert "100%" in bar

    def test_half_bar(self):
        bar = _render_distribution_bar(50, 100)
        assert "50%" in bar


class TestBuildOrgStepSummary:
    """Tests for build_org_step_summary()."""

    def test_includes_failed_data_view_count(self):
        result = _make_org_result()
        result.data_view_summaries.append(_make_data_view_summary("dv_err", "Error DV", error="Failure"))

        summary = build_org_step_summary(result)

        assert "Data View Fetch Failures" in summary
        assert "| Data View Fetch Failures | 1 |" in summary


class TestOrgFailureTelemetryAcrossOutputs:
    """Contract tests ensuring failure telemetry remains visible in all org-report outputs."""

    def test_failure_telemetry_present_across_outputs_with_zero_failures(self, tmp_path):
        result = _make_org_result()
        logger = logging.getLogger("test_org_telemetry_zero")

        json_path = Path(write_org_report_json(result, tmp_path / "report.json", str(tmp_path), logger))
        json_data = json.loads(json_path.read_text(encoding="utf-8"))
        assert json_data["data_view_fetch_failures"]["count"] == 0
        assert json_data["data_view_fetch_failures"]["data_view_ids"] == []
        assert json_data["data_view_fetch_failures"]["failure_reason_counts"] == {}

        csv_dir = Path(write_org_report_csv(result, None, str(tmp_path), logger))
        with (csv_dir / "org_report_summary.csv").open(encoding="utf-8", newline="") as handle:
            csv_row = next(csv.DictReader(handle))
        assert csv_row["Failed Data Views"] == "0"

        markdown_path = Path(write_org_report_markdown(result, tmp_path / "report.md", str(tmp_path), logger))
        markdown_text = markdown_path.read_text(encoding="utf-8")
        assert "| Data View Fetch Failures | 0 |" in markdown_text

        html_path = Path(write_org_report_html(result, tmp_path / "report.html", str(tmp_path), logger))
        html_text = html_path.read_text(encoding="utf-8")
        assert "Data View Fetch Failures" in html_text

        step_summary = build_org_step_summary(result)
        assert "| Data View Fetch Failures | 0 |" in step_summary

    def test_failure_telemetry_present_across_outputs_with_nonzero_failures(self, tmp_path):
        result = _make_org_result()
        result.data_view_summaries.extend(
            [
                _make_data_view_summary("dv_err_1", "Error DV 1", error="Timeout"),
                _make_data_view_summary("dv_err_2", "Error DV 2", error="Permission denied"),
            ],
        )
        logger = logging.getLogger("test_org_telemetry_nonzero")

        json_path = Path(write_org_report_json(result, tmp_path / "report_fail.json", str(tmp_path), logger))
        json_data = json.loads(json_path.read_text(encoding="utf-8"))
        assert json_data["data_view_fetch_failures"]["count"] == 2
        assert json_data["data_view_fetch_failures"]["data_view_ids"] == ["dv_err_1", "dv_err_2"]
        assert json_data["data_view_fetch_failures"]["failure_reason_counts"] == {
            "Permission denied": 1,
            "Timeout": 1,
        }

        csv_dir = Path(write_org_report_csv(result, None, str(tmp_path), logger))
        with (csv_dir / "org_report_summary.csv").open(encoding="utf-8", newline="") as handle:
            csv_row = next(csv.DictReader(handle))
        assert csv_row["Failed Data Views"] == "2"

        markdown_path = Path(
            write_org_report_markdown(result, tmp_path / "report_fail.md", str(tmp_path), logger),
        )
        markdown_text = markdown_path.read_text(encoding="utf-8")
        assert "| Data View Fetch Failures | 2 |" in markdown_text

        html_path = Path(write_org_report_html(result, tmp_path / "report_fail.html", str(tmp_path), logger))
        html_text = html_path.read_text(encoding="utf-8")
        assert "Data View Fetch Failures" in html_text

        step_summary = build_org_step_summary(result)
        assert "| Data View Fetch Failures | 2 |" in step_summary


# ===================================================================
# run_org_report (mocked)
# ===================================================================


class TestRunOrgReport:
    """Tests for run_org_report() covering comparison and stats-only dispatch."""

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary")
    @patch("cja_auto_sdr.generator.OrgComponentAnalyzer")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_run_org_report_stats_only_console(
        self, mock_configure, mock_cjapy, mock_analyzer_cls, mock_summary, mock_append, tmp_path, capsys
    ):
        """Cover org_stats_only mode invocation."""
        mock_configure.return_value = (True, "config.json", {"org_id": "test_org"})
        mock_cjapy.CJA.return_value = MagicMock()

        result = _make_org_result()
        mock_analyzer_cls.return_value.run_analysis.return_value = result

        config = OrgReportConfig(org_stats_only=True)
        success, thresholds = run_org_report(
            config_file=str(tmp_path / "config.json"),
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=config,
            quiet=False,
        )

        assert success is True
        assert thresholds is False

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary")
    @patch("cja_auto_sdr.generator.OrgComponentAnalyzer")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_run_org_report_stats_only_json(
        self, mock_configure, mock_cjapy, mock_analyzer_cls, mock_summary, mock_append, tmp_path
    ):
        """Cover org_stats_only + json format path."""
        mock_configure.return_value = (True, "config.json", {"org_id": "test_org"})
        mock_cjapy.CJA.return_value = MagicMock()

        result = _make_org_result()
        mock_analyzer_cls.return_value.run_analysis.return_value = result

        config = OrgReportConfig(org_stats_only=True)
        success, _thresholds = run_org_report(
            config_file=str(tmp_path / "config.json"),
            output_format="json",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=config,
            quiet=False,
        )

        assert success is True

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary")
    @patch("cja_auto_sdr.generator.OrgComponentAnalyzer")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_run_org_report_with_comparison(
        self, mock_configure, mock_cjapy, mock_analyzer_cls, mock_summary, mock_append, tmp_path
    ):
        """Cover comparison output dispatch (lines 12449-12458)."""
        mock_configure.return_value = (True, "config.json", {"org_id": "test_org"})
        mock_cjapy.CJA.return_value = MagicMock()

        result = _make_org_result()
        mock_analyzer_cls.return_value.run_analysis.return_value = result

        # Write a previous report file
        prev_report = _mark_full_fidelity_baseline(
            {
                "generated_at": "2024-12-01T10:00:00Z",
                "data_views": [{"data_view_id": "dv_001", "data_view_name": "DV 1"}],
                "summary": {"total_unique_components": 10},
                "distribution": {
                    "core": {"total": 3},
                    "isolated": {"total": 1},
                },
                "similarity_pairs": [],
            }
        )
        prev_path = tmp_path / "prev.json"
        prev_path.write_text(json.dumps(prev_report), encoding="utf-8")

        config = OrgReportConfig(compare_org_report=str(prev_path))
        success, _thresholds = run_org_report(
            config_file=str(tmp_path / "config.json"),
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=config,
            quiet=False,
        )

        assert success is True

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary")
    @patch("cja_auto_sdr.generator.OrgComponentAnalyzer")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_run_org_report_comparison_file_not_found(
        self, mock_configure, mock_cjapy, mock_analyzer_cls, mock_summary, mock_append, tmp_path, capsys
    ):
        """Cover FileNotFoundError branch in comparison."""
        mock_configure.return_value = (True, "config.json", {"org_id": "test_org"})
        mock_cjapy.CJA.return_value = MagicMock()

        result = _make_org_result()
        mock_analyzer_cls.return_value.run_analysis.return_value = result

        config = OrgReportConfig(compare_org_report="/nonexistent/prev.json")
        success, _ = run_org_report(
            config_file=str(tmp_path / "config.json"),
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=config,
            quiet=False,
        )

        # Should still succeed (comparison failure is non-fatal)
        assert success is True

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary")
    @patch("cja_auto_sdr.generator.OrgComponentAnalyzer")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_run_org_report_comparison_invalid_json(
        self, mock_configure, mock_cjapy, mock_analyzer_cls, mock_summary, mock_append, tmp_path, capsys
    ):
        """Cover JSONDecodeError branch in comparison."""
        mock_configure.return_value = (True, "config.json", {"org_id": "test_org"})
        mock_cjapy.CJA.return_value = MagicMock()

        result = _make_org_result()
        mock_analyzer_cls.return_value.run_analysis.return_value = result

        bad_path = tmp_path / "bad.json"
        bad_path.write_text("not valid json {{{", encoding="utf-8")

        config = OrgReportConfig(compare_org_report=str(bad_path))
        success, _ = run_org_report(
            config_file=str(tmp_path / "config.json"),
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=config,
            quiet=False,
        )

        assert success is True

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary")
    @patch("cja_auto_sdr.generator.OrgComponentAnalyzer")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_run_org_report_all_formats(
        self, mock_configure, mock_cjapy, mock_analyzer_cls, mock_summary, mock_append, tmp_path
    ):
        """Cover 'all' format generation path."""
        mock_configure.return_value = (True, "config.json", {"org_id": "test_org"})
        mock_cjapy.CJA.return_value = MagicMock()

        result = _make_org_result()
        mock_analyzer_cls.return_value.run_analysis.return_value = result

        config = OrgReportConfig()
        success, _ = run_org_report(
            config_file=str(tmp_path / "config.json"),
            output_format="all",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=config,
            quiet=False,
        )

        assert success is True

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary")
    @patch("cja_auto_sdr.generator.OrgComponentAnalyzer")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_run_org_report_excel_format(
        self, mock_configure, mock_cjapy, mock_analyzer_cls, mock_summary, mock_append, tmp_path
    ):
        """Cover excel format output."""
        mock_configure.return_value = (True, "config.json", {"org_id": "test_org"})
        mock_cjapy.CJA.return_value = MagicMock()

        result = _make_org_result()
        mock_analyzer_cls.return_value.run_analysis.return_value = result

        config = OrgReportConfig()
        success, _ = run_org_report(
            config_file=str(tmp_path / "config.json"),
            output_format="excel",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=config,
            quiet=False,
        )

        assert success is True

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary")
    @patch("cja_auto_sdr.generator.OrgComponentAnalyzer")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_run_org_report_markdown_format(
        self, mock_configure, mock_cjapy, mock_analyzer_cls, mock_summary, mock_append, tmp_path
    ):
        """Cover markdown format output."""
        mock_configure.return_value = (True, "config.json", {"org_id": "test_org"})
        mock_cjapy.CJA.return_value = MagicMock()

        result = _make_org_result()
        mock_analyzer_cls.return_value.run_analysis.return_value = result

        config = OrgReportConfig()
        success, _ = run_org_report(
            config_file=str(tmp_path / "config.json"),
            output_format="markdown",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=config,
            quiet=False,
        )

        assert success is True

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary")
    @patch("cja_auto_sdr.generator.OrgComponentAnalyzer")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_run_org_report_html_format(
        self, mock_configure, mock_cjapy, mock_analyzer_cls, mock_summary, mock_append, tmp_path
    ):
        """Cover HTML format output (line 12497-12499)."""
        mock_configure.return_value = (True, "config.json", {"org_id": "test_org"})
        mock_cjapy.CJA.return_value = MagicMock()

        result = _make_org_result()
        mock_analyzer_cls.return_value.run_analysis.return_value = result

        config = OrgReportConfig()
        success, _ = run_org_report(
            config_file=str(tmp_path / "config.json"),
            output_format="html",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=config,
            quiet=False,
        )

        assert success is True

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary")
    @patch("cja_auto_sdr.generator.OrgComponentAnalyzer")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_run_org_report_csv_format(
        self, mock_configure, mock_cjapy, mock_analyzer_cls, mock_summary, mock_append, tmp_path
    ):
        """Cover CSV format output."""
        mock_configure.return_value = (True, "config.json", {"org_id": "test_org"})
        mock_cjapy.CJA.return_value = MagicMock()

        result = _make_org_result()
        mock_analyzer_cls.return_value.run_analysis.return_value = result

        config = OrgReportConfig()
        success, _ = run_org_report(
            config_file=str(tmp_path / "config.json"),
            output_format="csv",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=config,
            quiet=False,
        )

        assert success is True

    @patch("cja_auto_sdr.generator.OrgComponentAnalyzer")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_run_org_report_invalid_format(self, mock_configure, mock_cjapy, mock_analyzer_cls, tmp_path):
        """Cover invalid format validation."""
        mock_configure.return_value = (True, "config.json", {"org_id": "test_org"})

        config = OrgReportConfig()
        success, _ = run_org_report(
            config_file=str(tmp_path / "config.json"),
            output_format="invalid_format",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=config,
            quiet=False,
        )

        assert success is False

    @patch("cja_auto_sdr.generator.OrgComponentAnalyzer")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_run_org_report_configure_failure(self, mock_configure, mock_cjapy, mock_analyzer_cls, tmp_path):
        """Cover configure_cjapy failure path."""
        mock_configure.return_value = (False, "Bad credentials", None)

        config = OrgReportConfig()
        success, _ = run_org_report(
            config_file=str(tmp_path / "config.json"),
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=config,
            quiet=False,
        )

        assert success is False

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary")
    @patch("cja_auto_sdr.generator.OrgComponentAnalyzer")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_run_org_report_no_data_views(
        self, mock_configure, mock_cjapy, mock_analyzer_cls, mock_summary, mock_append, tmp_path
    ):
        """Cover zero data views found."""
        mock_configure.return_value = (True, "config.json", {"org_id": "test_org"})
        mock_cjapy.CJA.return_value = MagicMock()

        result = _make_org_result(num_dvs=0)
        result.data_view_summaries = []
        mock_analyzer_cls.return_value.run_analysis.return_value = result

        config = OrgReportConfig()
        success, _ = run_org_report(
            config_file=str(tmp_path / "config.json"),
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=config,
            quiet=False,
        )

        assert success is False

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary")
    @patch("cja_auto_sdr.generator.OrgComponentAnalyzer")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_run_org_report_governance_threshold_exceeded(
        self, mock_configure, mock_cjapy, mock_analyzer_cls, mock_summary, mock_append, tmp_path
    ):
        """Cover governance thresholds exceeded messaging."""
        mock_configure.return_value = (True, "config.json", {"org_id": "test_org"})
        mock_cjapy.CJA.return_value = MagicMock()

        result = _make_org_result(include_governance_violations=True)
        mock_analyzer_cls.return_value.run_analysis.return_value = result

        config = OrgReportConfig(fail_on_threshold=True)
        success, thresholds = run_org_report(
            config_file=str(tmp_path / "config.json"),
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=config,
            quiet=False,
        )

        assert success is True
        assert thresholds is True

    @patch("cja_auto_sdr.generator.OrgComponentAnalyzer")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_run_org_report_stdout_non_json_rejected(self, mock_configure, mock_cjapy, mock_analyzer_cls, tmp_path):
        """Cover stdout output validation for non-json formats."""
        mock_configure.return_value = (True, "config.json", {"org_id": "test_org"})

        config = OrgReportConfig()
        success, _ = run_org_report(
            config_file=str(tmp_path / "config.json"),
            output_format="excel",
            output_path="stdout",
            output_dir=str(tmp_path),
            org_config=config,
            quiet=False,
        )

        assert success is False


# ===================================================================
# _main_impl workers validation
# ===================================================================


class TestMainImplWorkersValidation:
    """Tests for _main_impl workers validation (lines 13656-13677)."""

    @patch("cja_auto_sdr.generator.parse_arguments")
    def test_workers_invalid_string(self, mock_parse, capsys):
        """Cover workers ValueError branch (line 13658-13659)."""
        args = MagicMock()
        args.workers = "notanumber"
        args.quiet = False
        args.no_color = False
        args.data_views = []
        args.run_summary = None
        mock_parse.return_value = args

        from cja_auto_sdr.generator import _main_impl

        with pytest.raises(SystemExit):
            _main_impl()

    @patch("cja_auto_sdr.generator.parse_arguments")
    def test_workers_below_minimum(self, mock_parse, capsys):
        """Cover workers < 1 validation (line 13662-13663)."""
        args = MagicMock()
        args.workers = "0"
        args.quiet = False
        args.no_color = False
        args.data_views = []
        args.run_summary = None
        mock_parse.return_value = args

        from cja_auto_sdr.generator import _main_impl

        with pytest.raises(SystemExit):
            _main_impl()


# ===================================================================
# org.writers edge-case tests (L68-69, L147, L169, L187, L267, L309,
# L320, L400, L443, L1088)
# ===================================================================


def _make_trending(num_snapshots: int = 2) -> OrgReportTrending:
    """Build a minimal OrgReportTrending with *num_snapshots* entries."""
    snapshots = [
        TrendingSnapshot(
            timestamp=f"2025-0{i + 1}-01T00:00:00",
            data_view_count=i + 3,
            component_count=(i + 1) * 10,
            core_count=(i + 1) * 5,
            isolated_count=i,
            high_sim_pair_count=i,
        )
        for i in range(num_snapshots)
    ]
    deltas = []
    if num_snapshots >= 2:
        for i in range(num_snapshots - 1):
            deltas.append(
                TrendingDelta(
                    from_timestamp=snapshots[i].timestamp,
                    to_timestamp=snapshots[i + 1].timestamp,
                    data_view_delta=1,
                    component_delta=10,
                    core_delta=5,
                    isolated_delta=1,
                    high_sim_pair_delta=1,
                )
            )
    return OrgReportTrending(
        snapshots=snapshots,
        deltas=deltas,
        drift_scores={"dv_001": 0.8, "dv_002": 0.5},
        window_size=num_snapshots,
    )


class TestFormatTrendingTimestampShortFallback:
    """Tests for _format_trending_timestamp_short fallback (L68-69)."""

    def test_valid_iso_timestamp_formats_correctly(self):
        result = _format_trending_timestamp_short("2025-03-15T10:30:00")
        assert result == "Mar 15"

    def test_invalid_timestamp_returns_first_10_chars(self):
        """ValueError path: non-ISO string triggers fallback (L68-69)."""
        result = _format_trending_timestamp_short("not-a-real-date-string")
        assert result == "not-a-real"

    def test_short_invalid_timestamp_returns_truncated(self):
        """ValueError path: short invalid string still returns ts[:10]."""
        result = _format_trending_timestamp_short("bad")
        assert result == "bad"

    def test_empty_string_returns_empty(self):
        """ValueError path: empty string triggers fallback returning empty."""
        result = _format_trending_timestamp_short("")
        assert result == ""


class TestRenderConsoleTrendingTableEmpty:
    """Tests for _render_console_trending_table empty-input guard (L147)."""

    def test_empty_column_labels_returns_empty_list(self):
        """L147: empty column_labels -> return []."""
        result = _render_console_trending_table([], [("Metrics", [1, 2])])
        assert result == []

    def test_empty_metric_rows_returns_empty_list(self):
        """L147: empty metric_rows -> return []."""
        result = _render_console_trending_table(["Jan 01", "Feb 01"], [])
        assert result == []

    def test_both_empty_returns_empty_list(self):
        """L147: both empty -> return []."""
        result = _render_console_trending_table([], [])
        assert result == []


class TestRenderMarkdownTrendingTableEmpty:
    """Tests for _render_markdown_trending_table empty-input guard (L169)."""

    def test_empty_column_labels_returns_empty_list(self):
        """L169: empty column_labels -> return []."""
        result = _render_markdown_trending_table([], [("Metrics", [1, 2])])
        assert result == []

    def test_empty_metric_rows_returns_empty_list(self):
        """L169: empty metric_rows -> return []."""
        result = _render_markdown_trending_table(["Jan 01", "Feb 01"], [])
        assert result == []

    def test_both_empty_returns_empty_list(self):
        """L169: both empty -> return []."""
        result = _render_markdown_trending_table([], [])
        assert result == []


class TestRenderHtmlTrendingTableEmpty:
    """Tests for _render_html_trending_table empty-input guard (L187)."""

    def test_empty_column_labels_returns_empty_string(self):
        """L187: empty column_labels -> return ''."""
        result = _render_html_trending_table([], [("Metrics", [1, 2])])
        assert result == ""

    def test_empty_metric_rows_returns_empty_string(self):
        """L187: empty metric_rows -> return ''."""
        result = _render_html_trending_table(["Jan 01", "Feb 01"], [])
        assert result == ""

    def test_both_empty_returns_empty_string(self):
        """L187: both empty -> return ''."""
        result = _render_html_trending_table([], [])
        assert result == ""


class TestTopDriftScores:
    """Tests for _top_drift_scores (L267)."""

    def test_returns_top_n_entries(self):
        """L267: result is sliced to limit."""
        scores = {"dv_a": 0.9, "dv_b": 0.7, "dv_c": 0.5, "dv_d": 0.3}
        result = _top_drift_scores(scores, limit=2)
        assert len(result) == 2
        assert result[0][0] == "dv_a"
        assert result[1][0] == "dv_b"

    def test_default_limit_is_ten(self):
        """L267: default limit is 10."""
        scores = {f"dv_{i:02d}": float(i) for i in range(20)}
        result = _top_drift_scores(scores)
        assert len(result) == 10

    def test_empty_scores_returns_empty(self):
        """L267: empty dict returns empty list."""
        result = _top_drift_scores({})
        assert result == []


class TestTrendingDateRangeEmptySnapshots:
    """Tests for _trending_date_range empty guard (L309)."""

    def test_empty_snapshots_returns_empty_string(self):
        """L309: empty snapshots list -> return ''."""
        result = _trending_date_range([])
        assert result == ""

    def test_single_snapshot_returns_same_label_both_sides(self):
        """L309 not triggered: single snapshot returns first == last."""
        snapshots = [TrendingSnapshot(timestamp="2025-01-15T00:00:00")]
        result = _trending_date_range(snapshots)
        assert result == "Jan 15 \u2192 Jan 15"


class TestRenderTrendingConsoleOneSnapshot:
    """Tests for _render_trending_console with <2 snapshots (L320)."""

    def test_single_snapshot_returns_empty_string(self):
        """L320: len(snapshots) < 2 -> return ''."""
        trending = _make_trending(num_snapshots=1)
        result = _render_trending_console(trending)
        assert result == ""

    def test_no_snapshots_returns_empty_string(self):
        """L320: no snapshots -> return ''."""
        trending = OrgReportTrending(snapshots=[], deltas=[], drift_scores={}, window_size=0)
        result = _render_trending_console(trending)
        assert result == ""


class TestRenderTrendingMarkdownOneSnapshot:
    """Tests for _render_trending_markdown with <2 snapshots (L400)."""

    def test_single_snapshot_returns_empty_string(self):
        """L400: len(snapshots) < 2 -> return ''."""
        trending = _make_trending(num_snapshots=1)
        result = _render_trending_markdown(trending)
        assert result == ""

    def test_no_snapshots_returns_empty_string(self):
        """L400: no snapshots -> return ''."""
        trending = OrgReportTrending(snapshots=[], deltas=[], drift_scores={}, window_size=0)
        result = _render_trending_markdown(trending)
        assert result == ""


class TestRenderTrendingMarkdownEscaping:
    """Trending Markdown should escape DV cells so drift tables remain valid."""

    def test_drift_rows_escape_pipes_and_backticks(self):
        trending = OrgReportTrending(
            snapshots=[
                TrendingSnapshot(
                    timestamp="2026-03-01T00:00:00Z",
                    data_view_count=1,
                    dv_ids={"dv|1"},
                    dv_names={"dv|1": "Name | Broken `Table`"},
                ),
                TrendingSnapshot(
                    timestamp="2026-03-02T00:00:00Z",
                    data_view_count=1,
                    dv_ids={"dv|1"},
                    dv_names={"dv|1": "Name | Broken `Table`"},
                ),
            ],
            drift_scores={"dv|1": 1.0},
            window_size=2,
        )

        result = _render_trending_markdown(trending)

        assert "| dv\\|1 | Name \\| Broken \\`Table\\` | 1.00 |" in result
        assert "| dv|1 | Name | Broken `Table` | 1.00 |" not in result


class TestRenderTrendingHtmlOneSnapshot:
    """Tests for _render_trending_html with <2 snapshots (L443)."""

    def test_single_snapshot_returns_empty_string(self):
        """L443: len(snapshots) < 2 -> return ''."""
        trending = _make_trending(num_snapshots=1)
        result = _render_trending_html(trending)
        assert result == ""

    def test_no_snapshots_returns_empty_string(self):
        """L443: no snapshots -> return ''."""
        trending = OrgReportTrending(snapshots=[], deltas=[], drift_scores={}, window_size=0)
        result = _render_trending_html(trending)
        assert result == ""


class TestBuildOrgReportJsonDataSkipSimilarity:
    """Tests for build_org_report_json_data skip_similarity path (L1088)."""

    def test_skip_similarity_sets_mode(self):
        """L1088: parameters.skip_similarity=True -> similarity_analysis_mode='skip_similarity'."""
        result = _make_org_result(include_similarity=False, config_overrides={"skip_similarity": True})
        data = build_org_report_json_data(result)

        assert data["summary"]["similarity_analysis_mode"] == "skip_similarity"
        assert data["summary"]["similarity_analysis_complete"] is False

    def test_org_stats_only_takes_priority_over_skip_similarity(self):
        """org_stats_only path (L1086) takes priority even if skip_similarity is also True."""
        result = _make_org_result(
            include_similarity=False,
            config_overrides={"org_stats_only": True, "skip_similarity": True},
        )
        data = build_org_report_json_data(result)

        assert data["summary"]["similarity_analysis_mode"] == "org_stats_only"
