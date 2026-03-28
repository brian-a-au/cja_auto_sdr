# src/cja_auto_sdr/core/advisory_builders.py
"""Advisory builders — pure functions that derive advisories from result objects.

Each builder consumes canonical in-memory result objects and produces an
AdvisorySummary. JSON writers serialize builder output; they must not
independently recalculate findings.
"""

from __future__ import annotations

from collections import Counter
from typing import TYPE_CHECKING, Any

from cja_auto_sdr.core.advisories import (
    _ADVISORY_SEVERITY_ORDER,
    AdvisoryFinding,
    AdvisorySummary,
)

if TYPE_CHECKING:
    from cja_auto_sdr.org.models import OrgReportResult, OrgReportTrending


def _max_severity(severities: list[str]) -> str:
    """Return the highest severity level from a list, defaulting to 'info'."""
    if not severities:
        return "info"
    order = {s: i for i, s in enumerate(_ADVISORY_SEVERITY_ORDER)}
    return max(severities, key=lambda s: order.get(s, 0))


def _make_summary_block(findings: list[AdvisoryFinding]) -> dict[str, Any]:
    """Build the summary dict for an AdvisorySummary."""
    by_severity: Counter[str] = Counter(f.severity for f in findings)
    return {
        "total_findings": len(findings),
        "by_severity": dict(by_severity),
    }


def build_org_report_advisories(
    result: OrgReportResult,
    trending: OrgReportTrending | None = None,
) -> AdvisorySummary:
    """Derive an AdvisorySummary from an OrgReportResult.

    This is a pure function — it does not mutate *result* or *trending*.

    Checks performed:
    - fetch_failures: Any data views with errors → severity warning
    - high_overlap: Similarity pairs whose Jaccard score >= overlap_threshold → warning
    - governance_threshold_breach: thresholds_exceeded=True with violations → critical
    - drift_activity: trending provided with non-empty drift_scores → warning
    """
    findings: list[AdvisoryFinding] = []

    # 1. Fetch failures
    failed_ids = list(result.failed_data_view_ids)
    if failed_ids:
        reason_counts = dict(result.failed_data_view_reason_counts)
        findings.append(
            AdvisoryFinding(
                type="fetch_failures",
                severity="warning",
                message=f"{len(failed_ids)} data view(s) could not be fetched.",
                details={
                    "data_view_ids": failed_ids,
                    "reason_counts": reason_counts,
                },
                recommended_actions=["investigate_fetch_failures"],
            )
        )

    # 2. High overlap
    if result.similarity_pairs is not None:
        threshold = result.parameters.overlap_threshold
        high_pairs = [p for p in result.similarity_pairs if p.jaccard_similarity >= threshold]
        if high_pairs:
            pair_details = [
                {
                    "dv1_id": p.dv1_id,
                    "dv1_name": p.dv1_name,
                    "dv2_id": p.dv2_id,
                    "dv2_name": p.dv2_name,
                    "jaccard_similarity": p.jaccard_similarity,
                }
                for p in high_pairs
            ]
            findings.append(
                AdvisoryFinding(
                    type="high_overlap",
                    severity="warning",
                    message=(f"{len(high_pairs)} data view pair(s) exceed the overlap threshold of {threshold:.0%}."),
                    details={
                        "pair_count": len(high_pairs),
                        "threshold": threshold,
                        "pairs": pair_details,
                    },
                    recommended_actions=[
                        "review_overlap_pairs",
                        "verify_intentional_duplicates",
                    ],
                )
            )

    # 3. Governance threshold breach
    if result.thresholds_exceeded:
        violations = list(result.governance_violations or [])
        findings.append(
            AdvisoryFinding(
                type="governance_threshold_breach",
                severity="critical",
                message="One or more governance thresholds have been exceeded.",
                details={
                    "violations": violations,
                    "violation_count": len(violations),
                },
                recommended_actions=[
                    "review_governance_thresholds",
                    "remediate_threshold_breach",
                ],
            )
        )

    # 4. Drift activity from trending
    if trending is not None and trending.drift_scores:
        drift_scores = dict(trending.drift_scores)
        findings.append(
            AdvisoryFinding(
                type="drift_activity",
                severity="warning",
                message=(
                    f"Drift activity detected across {len(drift_scores)} data view(s) "
                    f"over a {trending.window_size}-snapshot window."
                ),
                details={
                    "drift_scores": drift_scores,
                    "data_view_count": len(drift_scores),
                    "window_size": trending.window_size,
                },
                recommended_actions=[
                    "review_drift_activity",
                    "compare_recent_reports",
                ],
            )
        )

    severity = _max_severity([f.severity for f in findings])
    return AdvisorySummary(
        advisories_version="1.0",
        severity=severity,
        findings=findings,
        summary=_make_summary_block(findings),
    )
