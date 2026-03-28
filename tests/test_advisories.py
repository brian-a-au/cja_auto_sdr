# tests/test_advisories.py
"""Tests for the advisory data model and builders."""

from __future__ import annotations

import pytest

from cja_auto_sdr.core.advisories import (
    AdvisoryFinding,
    AdvisorySummary,
    _ADVISORY_SEVERITY_ORDER,
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
