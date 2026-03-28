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
