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
    from cja_auto_sdr.diff.models import DiffResult
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


def build_diff_advisories(
    diff_result: DiffResult,
    *,
    changes_only: bool = False,
) -> AdvisorySummary:
    """Derive an AdvisorySummary from a DiffResult.

    This is a pure function — it does not mutate *diff_result*.

    Checks performed:
    - breaking_changes: Any REMOVED components → severity critical
    - schema_changes: Any MODIFIED components → severity warning
    - additions_only: All changes are additions and no removals/modifications → severity info

    Excluded types: high_change_volume, rename-derived findings.
    """
    from cja_auto_sdr.diff.models import ChangeType

    findings: list[AdvisoryFinding] = []
    summary = diff_result.summary

    # Collect all component diffs across types
    all_diffs = list(diff_result.metric_diffs or []) + list(diff_result.dimension_diffs or [])
    inv_diffs = list(diff_result.calc_metrics_diffs or []) + list(diff_result.segments_diffs or [])

    if changes_only:
        active_diffs = [d for d in all_diffs if d.change_type != ChangeType.UNCHANGED]
        active_inv_diffs = [d for d in inv_diffs if d.change_type != ChangeType.UNCHANGED]
    else:
        active_diffs = all_diffs
        active_inv_diffs = inv_diffs

    # 1. Breaking changes — REMOVED components
    removed = [d for d in all_diffs + inv_diffs if d.change_type == ChangeType.REMOVED]
    if removed:
        component_details = [
            {"component_id": d.id, "component_name": d.name, "change_type": d.change_type.value} for d in removed
        ]
        findings.append(
            AdvisoryFinding(
                type="breaking_changes",
                severity="critical",
                message=f"{len(removed)} component(s) removed — downstream dependencies may break.",
                details={
                    "removed_count": len(removed),
                    "components": component_details,
                    "total_components": len(active_diffs) + len(active_inv_diffs),
                },
                recommended_actions=[
                    "review_breaking_changes",
                    "update_downstream_dependencies",
                ],
            )
        )

    # 2. Schema changes — MODIFIED components (only when no breaking changes already cover it)
    modified = [d for d in all_diffs + inv_diffs if d.change_type == ChangeType.MODIFIED]
    if modified and not removed:
        component_details = [
            {
                "component_id": d.id,
                "component_name": d.name,
                "changed_fields": list(d.changed_fields.keys()) if d.changed_fields else [],
            }
            for d in modified
        ]
        findings.append(
            AdvisoryFinding(
                type="schema_changes",
                severity="warning",
                message=f"{len(modified)} component(s) modified — validate field mappings.",
                details={
                    "modified_count": len(modified),
                    "components": component_details,
                    "total_components": len(active_diffs) + len(active_inv_diffs),
                },
                recommended_actions=[
                    "review_schema_changes",
                    "validate_mappings",
                ],
            )
        )

    # 3. Additions only — all changes are additions, no removals or modifications
    total_removed = summary.total_removed
    total_modified = summary.total_modified
    total_added = summary.total_added
    if total_added > 0 and total_removed == 0 and total_modified == 0:
        added = [d for d in all_diffs + inv_diffs if d.change_type == ChangeType.ADDED]
        component_details = [{"component_id": d.id, "component_name": d.name} for d in added]
        findings.append(
            AdvisoryFinding(
                type="additions_only",
                severity="info",
                message=f"{total_added} component(s) added — no removals or modifications detected.",
                details={
                    "added_count": total_added,
                    "components": component_details,
                    "total_components": len(active_diffs) + len(active_inv_diffs),
                },
                recommended_actions=["acknowledge_additive_change"],
            )
        )

    severity = _max_severity([f.severity for f in findings])
    return AdvisorySummary(
        advisories_version="1.0",
        severity=severity,
        findings=findings,
        summary=_make_summary_block(findings),
    )


def build_advisory_rollup(summary: AdvisorySummary) -> dict[str, Any]:
    """Build a compact advisory rollup for run-summary integration."""
    seen_types: list[str] = []
    seen_actions: list[str] = []
    for f in summary.findings:
        if f.type not in seen_types:
            seen_types.append(f.type)
        for action in f.recommended_actions:
            if action not in seen_actions:
                seen_actions.append(action)

    return {
        "advisories_version": summary.advisories_version,
        "severity": summary.severity,
        "summary": summary.summary,
        "types": seen_types,
        "recommended_actions": seen_actions,
    }
