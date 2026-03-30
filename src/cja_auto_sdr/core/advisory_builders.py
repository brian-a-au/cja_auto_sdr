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
from cja_auto_sdr.core.constants import effective_governance_overlap_threshold

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


def _top_nonzero_drift_scores(drift_scores: dict[str, float], *, limit: int = 10) -> list[dict[str, Any]]:
    """Return the highest non-zero drift scores in stable order."""
    ranked = sorted(
        ({"data_view_id": data_view_id, "score": score} for data_view_id, score in drift_scores.items() if score > 0),
        key=lambda entry: (-entry["score"], entry["data_view_id"]),
    )
    return ranked[:limit]


def build_org_report_advisories(
    result: OrgReportResult,
    trending: OrgReportTrending | None = None,
) -> AdvisorySummary:
    """Derive an AdvisorySummary from an OrgReportResult.

    This is a pure function — it does not mutate *result* or *trending*.

    Checks performed:
    - fetch_failures: Any data views with errors → severity warning
    - high_overlap: Similarity pairs whose Jaccard score >= effective overlap threshold → warning
    - isolated_review: existing review_isolated recommendations → info
    - metadata_hygiene: missing_descriptions and stale_data_view recommendations → warning
    - governance_threshold_breach: thresholds_exceeded=True with violations → critical
    - drift_activity: trending provided with non-zero drift_scores → info
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
                    "count": len(failed_ids),
                    "data_view_ids": failed_ids,
                    "failure_reason_counts": reason_counts,
                },
                recommended_actions=["investigate_fetch_failures"],
            )
        )

    # 2. High overlap
    if result.similarity_pairs is not None:
        configured_threshold = result.parameters.overlap_threshold
        threshold = effective_governance_overlap_threshold(configured_threshold)
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
                    message=(
                        f"{len(high_pairs)} data view pair(s) exceed the "
                        f"{'effective ' if configured_threshold > threshold else ''}"
                        f"overlap threshold of {threshold:.0%}."
                    ),
                    details={
                        "pairs": pair_details,
                        "threshold": threshold,
                        "max_similarity": max(p.jaccard_similarity for p in high_pairs),
                    },
                    recommended_actions=[
                        "review_overlap_pairs",
                        "verify_intentional_duplicates",
                    ],
                )
            )

    # 3. Isolated review
    isolated_recommendations = [rec for rec in result.recommendations if rec.get("type") == "review_isolated"]
    if isolated_recommendations:
        data_views = [
            {
                "data_view_id": rec.get("data_view"),
                "data_view_name": rec.get("data_view_name"),
                "isolated_count": rec.get("isolated_count"),
            }
            for rec in isolated_recommendations
        ]
        findings.append(
            AdvisoryFinding(
                type="isolated_review",
                severity="info",
                message=f"{len(data_views)} data view(s) have high isolated-component counts.",
                details={
                    "data_views": data_views,
                    "count": len(data_views),
                },
                recommended_actions=["review_isolated_views"],
            )
        )

    # 4. Metadata hygiene
    stale_recommendations = [rec for rec in result.recommendations if rec.get("type") == "stale_data_view"]
    missing_description_recommendations = [
        rec for rec in result.recommendations if rec.get("type") == "missing_descriptions"
    ]
    if stale_recommendations or missing_description_recommendations:
        missing_description_count = sum(int(rec.get("count", 0) or 0) for rec in missing_description_recommendations)
        stale_view_ids = [rec.get("data_view") for rec in stale_recommendations if rec.get("data_view")]
        recommended_actions: list[str] = []
        if missing_description_count > 0:
            recommended_actions.append("add_descriptions")
        if stale_view_ids:
            recommended_actions.append("review_stale_views")

        findings.append(
            AdvisoryFinding(
                type="metadata_hygiene",
                severity="warning",
                message=(
                    f"Metadata hygiene issues detected across {missing_description_count} undocumented "
                    f"and {len(stale_view_ids)} stale data view(s)."
                ),
                details={
                    "missing_description_count": missing_description_count,
                    "stale_view_ids": stale_view_ids,
                },
                recommended_actions=recommended_actions,
            )
        )

    # 5. Governance threshold breach
    if result.thresholds_exceeded:
        violations = list(result.governance_violations or [])
        findings.append(
            AdvisoryFinding(
                type="governance_threshold_breach",
                severity="critical",
                message="One or more governance thresholds have been exceeded.",
                details={
                    "violations": violations,
                    "count": len(violations),
                },
                recommended_actions=[
                    "review_governance_thresholds",
                    "remediate_threshold_breach",
                ],
            )
        )

    # 6. Drift activity from trending
    if trending is not None and trending.drift_scores:
        top_drift_scores = _top_nonzero_drift_scores(dict(trending.drift_scores))
        if top_drift_scores:
            findings.append(
                AdvisoryFinding(
                    type="drift_activity",
                    severity="info",
                    message=(
                        f"Drift activity detected across {len(top_drift_scores)} data view(s) "
                        f"over a {trending.window_size}-snapshot window."
                    ),
                    details={
                        "top_drift_scores": top_drift_scores,
                        "window": trending.window_size,
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
    - breaking_changes: Any breaking change detected by detect_breaking_changes() → severity critical
    - schema_changes: Breaking-change subset with type/schema changes → severity warning
    - additions_only: All changes are additions and no removals/modifications → severity info

    Excluded types: high_change_volume, rename-derived findings.
    """
    from cja_auto_sdr.diff.models import ChangeType
    from cja_auto_sdr.output.diff.common import detect_breaking_changes

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

    # 1. Breaking changes — use the canonical breaking-change detector.
    breaking_changes = detect_breaking_changes(diff_result)
    if breaking_changes:
        findings.append(
            AdvisoryFinding(
                type="breaking_changes",
                severity="critical",
                message=f"{len(breaking_changes)} breaking change(s) detected — downstream dependencies may break.",
                details={
                    "count": len(breaking_changes),
                    "changes": breaking_changes,
                    "total_components": len(active_diffs) + len(active_inv_diffs),
                },
                recommended_actions=[
                    "review_breaking_changes",
                    "update_downstream_dependencies",
                ],
            )
        )

    # 2. Schema changes — breaking-change subset for type/schema deltas.
    schema_changes = [
        change for change in breaking_changes if change.get("change_type") in {"type_changed", "schema_changed"}
    ]
    if schema_changes:
        findings.append(
            AdvisoryFinding(
                type="schema_changes",
                severity="warning",
                message=f"{len(schema_changes)} schema-level breaking change(s) detected — validate field mappings.",
                details={
                    "count": len(schema_changes),
                    "changes": schema_changes,
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
    return {
        "advisories_version": summary.advisories_version,
        "severity": summary.severity,
        "summary": summary.summary,
        "types": summary.finding_types(),
        "recommended_actions": summary.recommended_actions(),
    }
