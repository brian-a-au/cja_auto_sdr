# tests/test_advisories.py
"""Tests for the advisory data model and builders."""

from __future__ import annotations

from cja_auto_sdr.core.advisories import (
    _ADVISORY_SEVERITY_ORDER,
    AdvisoryFinding,
    AdvisorySummary,
)


class TestAdvisoryModel:
    """Verify advisory data model serialization and invariants."""

    def test_severity_order(self):
        assert _ADVISORY_SEVERITY_ORDER == ("info", "warning", "critical")

    def test_finding_creation(self):
        finding = AdvisoryFinding(
            type="high_overlap",
            severity="warning",
            message="High overlap detected",
            details={"pairs": 3, "threshold": 0.8},
            recommended_actions=["review_overlap_pairs"],
        )
        assert finding.type == "high_overlap"
        assert finding.severity == "warning"

    def test_empty_summary_to_dict(self):
        summary = AdvisorySummary(
            advisories_version="1.0",
            severity="info",
            findings=[],
            summary={"total_findings": 0, "by_severity": {}},
        )
        d = summary.to_dict()
        assert d["advisories_version"] == "1.0"
        assert d["severity"] == "info"
        assert d["findings"] == []
        assert d["summary"]["total_findings"] == 0
        assert d["summary"]["by_severity"] == {}

    def test_summary_with_findings_to_dict(self):
        finding = AdvisoryFinding(
            type="governance_threshold_breach",
            severity="critical",
            message="Threshold breach detected",
            details={"violations": [], "count": 1},
            recommended_actions=["review_governance_thresholds"],
        )
        summary = AdvisorySummary(
            advisories_version="1.0",
            severity="critical",
            findings=[finding],
            summary={"total_findings": 1, "by_severity": {"critical": 1}},
        )
        d = summary.to_dict()
        assert d["severity"] == "critical"
        assert len(d["findings"]) == 1
        assert d["findings"][0]["type"] == "governance_threshold_breach"
        assert d["findings"][0]["recommended_actions"] == ["review_governance_thresholds"]

    def test_advisories_version_always_present(self):
        summary = AdvisorySummary(
            advisories_version="1.0",
            severity="info",
            findings=[],
            summary={"total_findings": 0, "by_severity": {}},
        )
        d = summary.to_dict()
        assert "advisories_version" in d


# ---------------------------------------------------------------------------
# Org-report advisory builder tests
# ---------------------------------------------------------------------------

_DOCUMENTED_RECOMMENDED_ACTIONS = {
    "review_overlap_pairs",
    "verify_intentional_duplicates",
    "review_isolated_views",
    "add_descriptions",
    "review_stale_views",
    "review_governance_thresholds",
    "remediate_threshold_breach",
    "investigate_fetch_failures",
    "review_drift_activity",
    "compare_recent_reports",
}


def _make_minimal_org_result(**overrides):
    """Build a valid OrgReportResult with sensible defaults."""
    from cja_auto_sdr.org.models import (
        ComponentDistribution,
        DataViewSummary,
        OrgReportConfig,
        OrgReportResult,
    )

    defaults = {
        "timestamp": "2026-03-28T00:00:00Z",
        "org_id": "test-org",
        "parameters": OrgReportConfig(),
        "data_view_summaries": [
            DataViewSummary(
                data_view_id="dv1",
                data_view_name="Data View 1",
                metric_count=10,
                dimension_count=5,
            )
        ],
        "component_index": {},
        "distribution": ComponentDistribution(),
        "similarity_pairs": None,
        "recommendations": [],
        "duration": 1.0,
    }
    defaults.update(overrides)
    return OrgReportResult(**defaults)


class TestOrgReportAdvisoryBuilder:
    """Verify build_org_report_advisories() produces correct advisory summaries."""

    def test_empty_result_produces_info_severity(self):
        from cja_auto_sdr.core.advisory_builders import build_org_report_advisories

        result = _make_minimal_org_result()
        summary = build_org_report_advisories(result)

        assert isinstance(summary, AdvisorySummary)
        assert summary.severity == "info"
        assert summary.findings == []
        assert summary.advisories_version == "1.0"

    def test_fetch_failures_produce_warning(self):
        from cja_auto_sdr.core.advisory_builders import build_org_report_advisories
        from cja_auto_sdr.org.models import DataViewSummary

        failed_dv = DataViewSummary(
            data_view_id="dv-fail",
            data_view_name="Failing DV",
            error="Connection timeout",
        )
        result = _make_minimal_org_result(data_view_summaries=[failed_dv])
        summary = build_org_report_advisories(result)

        types = [f.type for f in summary.findings]
        assert "fetch_failures" in types

        finding = next(f for f in summary.findings if f.type == "fetch_failures")
        assert finding.severity == "warning"
        assert "dv-fail" in finding.details.get("data_view_ids", [])
        assert "reason_counts" in finding.details
        assert summary.severity in ("warning", "critical")

    def test_high_overlap_produces_warning(self):
        from cja_auto_sdr.core.advisory_builders import build_org_report_advisories
        from cja_auto_sdr.org.models import OrgReportConfig, SimilarityPair

        # overlap_threshold defaults to 0.8 — use a pair that exceeds it
        pair = SimilarityPair(
            dv1_id="dv1",
            dv1_name="DV One",
            dv2_id="dv2",
            dv2_name="DV Two",
            jaccard_similarity=0.95,
            shared_count=19,
            union_count=20,
        )
        result = _make_minimal_org_result(
            parameters=OrgReportConfig(overlap_threshold=0.8),
            similarity_pairs=[pair],
        )
        summary = build_org_report_advisories(result)

        types = [f.type for f in summary.findings]
        assert "high_overlap" in types

        finding = next(f for f in summary.findings if f.type == "high_overlap")
        assert finding.severity == "warning"

    def test_governance_threshold_breach_produces_critical(self):
        from cja_auto_sdr.core.advisory_builders import build_org_report_advisories

        violation = {"type": "duplicate_threshold", "count": 5, "limit": 3}
        result = _make_minimal_org_result(
            thresholds_exceeded=True,
            governance_violations=[violation],
        )
        summary = build_org_report_advisories(result)

        types = [f.type for f in summary.findings]
        assert "governance_threshold_breach" in types

        finding = next(f for f in summary.findings if f.type == "governance_threshold_breach")
        assert finding.severity == "critical"
        assert summary.severity == "critical"

    def test_drift_activity_from_trending(self):
        from cja_auto_sdr.core.advisory_builders import build_org_report_advisories
        from cja_auto_sdr.org.models import OrgReportTrending

        trending = OrgReportTrending(
            drift_scores={"dv1": 0.72, "dv2": 0.45},
            window_size=3,
        )
        result = _make_minimal_org_result()
        summary = build_org_report_advisories(result, trending=trending)

        types = [f.type for f in summary.findings]
        assert "drift_activity" in types

        finding = next(f for f in summary.findings if f.type == "drift_activity")
        assert finding.severity in ("info", "warning", "critical")

    def test_no_mutation_of_input(self):
        from cja_auto_sdr.core.advisory_builders import build_org_report_advisories
        from cja_auto_sdr.org.models import OrgReportTrending

        result = _make_minimal_org_result()
        trending = OrgReportTrending(drift_scores={"dv1": 0.5}, window_size=2)

        # Capture state before
        original_summaries = list(result.data_view_summaries)
        original_similarity = result.similarity_pairs
        original_thresholds_exceeded = result.thresholds_exceeded
        original_drift_scores = dict(trending.drift_scores)

        build_org_report_advisories(result, trending=trending)

        assert result.data_view_summaries == original_summaries
        assert result.similarity_pairs == original_similarity
        assert result.thresholds_exceeded == original_thresholds_exceeded
        assert trending.drift_scores == original_drift_scores

    def test_recommended_actions_in_registry(self):
        from cja_auto_sdr.core.advisory_builders import build_org_report_advisories
        from cja_auto_sdr.org.models import DataViewSummary, OrgReportConfig, OrgReportTrending, SimilarityPair

        pair = SimilarityPair(
            dv1_id="dv1",
            dv1_name="DV One",
            dv2_id="dv2",
            dv2_name="DV Two",
            jaccard_similarity=0.95,
            shared_count=19,
            union_count=20,
        )
        failed_dv = DataViewSummary(
            data_view_id="dv-fail",
            data_view_name="Failing DV",
            error="Timeout",
        )
        violation = {"type": "duplicate_threshold", "count": 5, "limit": 3}
        trending = OrgReportTrending(drift_scores={"dv1": 0.6}, window_size=2)

        result = _make_minimal_org_result(
            parameters=OrgReportConfig(overlap_threshold=0.8),
            similarity_pairs=[pair],
            data_view_summaries=[failed_dv],
            thresholds_exceeded=True,
            governance_violations=[violation],
        )
        summary = build_org_report_advisories(result, trending=trending)

        all_actions = {action for finding in summary.findings for action in finding.recommended_actions}
        assert all_actions <= _DOCUMENTED_RECOMMENDED_ACTIONS


# ---------------------------------------------------------------------------
# Diff advisory builder tests
# ---------------------------------------------------------------------------

_DOCUMENTED_DIFF_RECOMMENDED_ACTIONS = {
    "review_breaking_changes",
    "update_downstream_dependencies",
    "review_schema_changes",
    "validate_mappings",
    "acknowledge_additive_change",
}


def _make_minimal_diff_result(**overrides):
    """Build a valid DiffResult with sensible defaults using real types."""
    from cja_auto_sdr.diff.models import (
        DiffResult,
        DiffSummary,
        MetadataDiff,
    )

    defaults = {
        "summary": DiffSummary(),
        "metadata_diff": MetadataDiff(
            source_name="Source DV",
            target_name="Target DV",
            source_id="dv-src",
            target_id="dv-tgt",
        ),
        "metric_diffs": [],
        "dimension_diffs": [],
    }
    defaults.update(overrides)
    return DiffResult(**defaults)


class TestDiffAdvisoryBuilder:
    """Verify build_diff_advisories() produces correct advisory summaries."""

    def test_empty_diff_produces_info_severity(self):
        from cja_auto_sdr.core.advisory_builders import build_diff_advisories

        diff = _make_minimal_diff_result()
        summary = build_diff_advisories(diff)

        assert isinstance(summary, AdvisorySummary)
        assert summary.severity == "info"
        assert summary.advisories_version == "1.0"

    def test_breaking_changes_produce_critical(self):
        from cja_auto_sdr.core.advisory_builders import build_diff_advisories
        from cja_auto_sdr.diff.models import ChangeType, ComponentDiff, DiffSummary

        removed = ComponentDiff(id="m1", name="Revenue", change_type=ChangeType.REMOVED)
        diff = _make_minimal_diff_result(
            summary=DiffSummary(metrics_removed=1),
            metric_diffs=[removed],
        )
        summary = build_diff_advisories(diff)

        types = [f.type for f in summary.findings]
        assert "breaking_changes" in types

        finding = next(f for f in summary.findings if f.type == "breaking_changes")
        assert finding.severity == "critical"
        assert summary.severity == "critical"

    def test_schema_changes_from_modified(self):
        from cja_auto_sdr.core.advisory_builders import build_diff_advisories
        from cja_auto_sdr.diff.models import ChangeType, ComponentDiff, DiffSummary

        modified = ComponentDiff(
            id="d1",
            name="Page Name",
            change_type=ChangeType.MODIFIED,
            changed_fields={"type": ("string", "integer")},
        )
        diff = _make_minimal_diff_result(
            summary=DiffSummary(dimensions_modified=1),
            dimension_diffs=[modified],
        )
        summary = build_diff_advisories(diff)

        types = [f.type for f in summary.findings]
        assert "schema_changes" in types

        finding = next(f for f in summary.findings if f.type == "schema_changes")
        assert finding.severity == "warning"

    def test_additions_only_produces_info(self):
        from cja_auto_sdr.core.advisory_builders import build_diff_advisories
        from cja_auto_sdr.diff.models import ChangeType, ComponentDiff, DiffSummary

        added = ComponentDiff(id="m2", name="New Metric", change_type=ChangeType.ADDED)
        diff = _make_minimal_diff_result(
            summary=DiffSummary(metrics_added=1),
            metric_diffs=[added],
        )
        summary = build_diff_advisories(diff)

        types = [f.type for f in summary.findings]
        assert "additions_only" in types

        finding = next(f for f in summary.findings if f.type == "additions_only")
        assert finding.severity == "info"

    def test_changes_only_filters_unchanged_from_details(self):
        from cja_auto_sdr.core.advisory_builders import build_diff_advisories
        from cja_auto_sdr.diff.models import ChangeType, ComponentDiff, DiffSummary

        added = ComponentDiff(id="m2", name="New Metric", change_type=ChangeType.ADDED)
        unchanged = ComponentDiff(id="m3", name="Old Metric", change_type=ChangeType.UNCHANGED)
        diff = _make_minimal_diff_result(
            summary=DiffSummary(metrics_added=1, metrics_unchanged=1),
            metric_diffs=[added, unchanged],
        )

        summary_all = build_diff_advisories(diff, changes_only=False)
        summary_filtered = build_diff_advisories(diff, changes_only=True)

        # With changes_only=True, total component count in details should be smaller
        finding_all = next((f for f in summary_all.findings if f.type == "additions_only"), None)
        finding_filtered = next((f for f in summary_filtered.findings if f.type == "additions_only"), None)

        # Both should still produce a finding; filtered version should report fewer total components
        assert finding_all is not None
        assert finding_filtered is not None
        assert finding_filtered.details.get("total_components", 0) <= finding_all.details.get("total_components", 0)

    def test_no_high_change_volume_emitted(self):
        from cja_auto_sdr.core.advisory_builders import build_diff_advisories
        from cja_auto_sdr.diff.models import ChangeType, ComponentDiff, DiffSummary

        # Even with many changes, high_change_volume must NOT appear
        diffs = [ComponentDiff(id=f"m{i}", name=f"Metric {i}", change_type=ChangeType.MODIFIED) for i in range(50)]
        diff = _make_minimal_diff_result(
            summary=DiffSummary(metrics_modified=50),
            metric_diffs=diffs,
        )
        summary = build_diff_advisories(diff)

        types = [f.type for f in summary.findings]
        assert "high_change_volume" not in types

    def test_recommended_actions_in_registry(self):
        from cja_auto_sdr.core.advisory_builders import build_diff_advisories
        from cja_auto_sdr.diff.models import ChangeType, ComponentDiff, DiffSummary

        removed = ComponentDiff(id="m1", name="Revenue", change_type=ChangeType.REMOVED)
        added = ComponentDiff(id="m2", name="New Metric", change_type=ChangeType.ADDED)
        modified = ComponentDiff(id="d1", name="Page", change_type=ChangeType.MODIFIED)

        diff = _make_minimal_diff_result(
            summary=DiffSummary(metrics_removed=1, metrics_added=1, dimensions_modified=1),
            metric_diffs=[removed, added],
            dimension_diffs=[modified],
        )
        summary = build_diff_advisories(diff)

        all_actions = {action for finding in summary.findings for action in finding.recommended_actions}
        assert all_actions <= _DOCUMENTED_DIFF_RECOMMENDED_ACTIONS


# ---------------------------------------------------------------------------
# Advisory rollup builder tests
# ---------------------------------------------------------------------------


class TestAdvisoryRollup:
    """Verify compact advisory rollup for run-summary integration."""

    def test_rollup_from_empty_summary(self):
        from cja_auto_sdr.core.advisory_builders import build_advisory_rollup

        summary = AdvisorySummary(
            advisories_version="1.0",
            severity="info",
            findings=[],
            summary={"total_findings": 0, "by_severity": {}},
        )
        rollup = build_advisory_rollup(summary)
        assert rollup["advisories_version"] == "1.0"
        assert rollup["severity"] == "info"
        assert rollup["summary"]["total_findings"] == 0
        assert rollup["types"] == []
        assert rollup["recommended_actions"] == []

    def test_rollup_deduplicates_types_and_actions(self):
        from cja_auto_sdr.core.advisory_builders import build_advisory_rollup

        findings = [
            AdvisoryFinding(
                type="breaking_changes",
                severity="critical",
                message="test",
                details={},
                recommended_actions=["review_breaking_changes", "update_downstream_dependencies"],
            ),
            AdvisoryFinding(
                type="schema_changes",
                severity="warning",
                message="test",
                details={},
                recommended_actions=["review_schema_changes", "review_breaking_changes"],
            ),
        ]
        summary = AdvisorySummary(
            advisories_version="1.0",
            severity="critical",
            findings=findings,
            summary={"total_findings": 2, "by_severity": {"critical": 1, "warning": 1}},
        )
        rollup = build_advisory_rollup(summary)
        assert sorted(rollup["types"]) == ["breaking_changes", "schema_changes"]
        assert len(rollup["recommended_actions"]) == len(set(rollup["recommended_actions"]))

    def test_rollup_severity_matches_summary(self):
        from cja_auto_sdr.core.advisory_builders import build_advisory_rollup

        findings = [
            AdvisoryFinding(
                type="fetch_failures",
                severity="warning",
                message="test",
                details={},
                recommended_actions=["investigate_fetch_failures"],
            ),
        ]
        summary = AdvisorySummary(
            advisories_version="1.0",
            severity="warning",
            findings=findings,
            summary={"total_findings": 1, "by_severity": {"warning": 1}},
        )
        rollup = build_advisory_rollup(summary)
        assert rollup["severity"] == "warning"


# ---------------------------------------------------------------------------
# Org-report JSON advisory integration tests
# ---------------------------------------------------------------------------


class TestOrgReportJsonAdvisories:
    """Verify advisories block appears in org-report JSON output."""

    def test_advisories_present_in_org_json(self):
        from cja_auto_sdr.org.writers.json import build_org_report_json_data

        result = _make_minimal_org_result()
        data = build_org_report_json_data(result)
        assert "advisories" in data
        assert data["advisories"]["advisories_version"] == "1.0"

    def test_advisories_empty_when_no_issues(self):
        from cja_auto_sdr.org.writers.json import build_org_report_json_data

        result = _make_minimal_org_result()
        data = build_org_report_json_data(result)
        assert data["advisories"]["findings"] == []
        assert data["advisories"]["summary"]["total_findings"] == 0

    def test_advisories_reflects_fetch_failures(self):
        from cja_auto_sdr.org.models import DataViewSummary
        from cja_auto_sdr.org.writers.json import build_org_report_json_data

        failed_dv = DataViewSummary(
            data_view_id="dv-fail",
            data_view_name="Failing DV",
            error="Connection timeout",
        )
        result = _make_minimal_org_result(data_view_summaries=[failed_dv])
        data = build_org_report_json_data(result)
        types = [f["type"] for f in data["advisories"]["findings"]]
        assert "fetch_failures" in types

    def test_advisories_includes_drift_when_trending_provided(self):
        from cja_auto_sdr.org.models import OrgReportTrending, TrendingSnapshot
        from cja_auto_sdr.org.writers.json import build_org_report_json_data

        snapshots = [
            TrendingSnapshot(
                timestamp="2025-01-01T00:00:00",
                data_view_count=3,
                component_count=10,
                core_count=5,
                isolated_count=1,
                high_sim_pair_count=0,
            ),
            TrendingSnapshot(
                timestamp="2025-02-01T00:00:00",
                data_view_count=4,
                component_count=14,
                core_count=6,
                isolated_count=2,
                high_sim_pair_count=1,
            ),
        ]
        trending = OrgReportTrending(
            snapshots=snapshots,
            drift_scores={"dv1": 0.72},
            window_size=2,
        )
        result = _make_minimal_org_result()
        data = build_org_report_json_data(result, trending=trending)
        types = [f["type"] for f in data["advisories"]["findings"]]
        assert "drift_activity" in types

    def test_advisories_is_additive_does_not_remove_existing_keys(self):
        from cja_auto_sdr.org.writers.json import build_org_report_json_data

        result = _make_minimal_org_result()
        data = build_org_report_json_data(result)
        # Core existing top-level keys must all still be present
        for key in (
            "report_type",
            "version",
            "generated_at",
            "org_id",
            "parameters",
            "summary",
            "data_view_fetch_failures",
            "distribution",
            "data_views",
            "component_index",
            "similarity_pairs",
            "recommendations",
        ):
            assert key in data, f"Expected key {key!r} missing after advisories injection"


# ---------------------------------------------------------------------------
# Diff JSON advisory integration tests
# ---------------------------------------------------------------------------


class TestDiffJsonAdvisories:
    """Verify advisories block appears in diff JSON output."""

    def test_build_diff_json_data_exists(self):
        from cja_auto_sdr.output.diff.json import build_diff_json_data

        result = _make_minimal_diff_result()
        data = build_diff_json_data(result)
        assert "metadata" in data
        assert "summary" in data

    def test_advisories_present_in_diff_json(self):
        from cja_auto_sdr.output.diff.json import build_diff_json_data

        result = _make_minimal_diff_result()
        data = build_diff_json_data(result)
        assert "advisories" in data
        assert data["advisories"]["advisories_version"] == "1.0"

    def test_diff_json_data_matches_file_writer_shape(self):
        from cja_auto_sdr.output.diff.json import build_diff_json_data

        result = _make_minimal_diff_result()
        data = build_diff_json_data(result)
        expected_keys = {"metadata", "source", "target", "summary", "metric_diffs", "dimension_diffs", "advisories"}
        assert expected_keys.issubset(set(data.keys()))

    def test_advisories_empty_when_no_changes(self):
        from cja_auto_sdr.output.diff.json import build_diff_json_data

        result = _make_minimal_diff_result()
        data = build_diff_json_data(result)
        assert data["advisories"]["findings"] == []
        assert data["advisories"]["summary"]["total_findings"] == 0

    def test_advisories_reflects_breaking_changes(self):
        from cja_auto_sdr.diff.models import ChangeType, ComponentDiff, DiffSummary
        from cja_auto_sdr.output.diff.json import build_diff_json_data

        removed = ComponentDiff(id="m1", name="Revenue", change_type=ChangeType.REMOVED)
        result = _make_minimal_diff_result(
            summary=DiffSummary(metrics_removed=1),
            metric_diffs=[removed],
        )
        data = build_diff_json_data(result)
        types = [f["type"] for f in data["advisories"]["findings"]]
        assert "breaking_changes" in types

    def test_advisories_is_additive_does_not_remove_existing_keys(self):
        from cja_auto_sdr.output.diff.json import build_diff_json_data

        result = _make_minimal_diff_result()
        data = build_diff_json_data(result)
        for key in ("metadata", "source", "target", "summary", "metric_diffs", "dimension_diffs"):
            assert key in data, f"Expected key {key!r} missing after advisories injection"
