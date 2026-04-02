"""Run-summary output and presentation helpers.

This module contains the output/presentation layer for run summaries:
writing JSON output, GitHub step summary generation, and quality/diff/org
step summary builders. The run-summary schema, payload assembly, and
status inference remain in ``generator.py``.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cja_auto_sdr.api.quality_policy import count_quality_issues_by_severity
from cja_auto_sdr.core.constants import QUALITY_SEVERITY_ORDER
from cja_auto_sdr.core.json_io import write_json_atomic_compatible

if TYPE_CHECKING:
    from cja_auto_sdr.diff.models import DiffResult
    from cja_auto_sdr.org.models import OrgReportResult
    from cja_auto_sdr.pipeline.models import ProcessingResult


def aggregate_quality_issues(results: list[ProcessingResult]) -> list[dict[str, Any]]:
    """Flatten quality issues across processing results with data view context."""
    issues: list[dict[str, Any]] = []
    for result in results:
        for issue in result.dq_issues:
            issue_with_context = dict(issue)
            issue_with_context.setdefault("Data View ID", result.data_view_id)
            issue_with_context.setdefault("Data View Name", result.data_view_name)
            issues.append(issue_with_context)
    return issues


def write_run_summary_output(summary: dict[str, Any], output: str, output_dir: str | Path = ".") -> str:
    """Write structured run summary JSON to file or stdout."""
    output_to_stdout = output in ("-", "stdout")
    if output_to_stdout:
        json.dump(summary, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return "stdout"

    output_path = Path(output)
    if not output_path.is_absolute():
        output_path = Path(output_dir) / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    write_json_atomic_compatible(output_path, summary, indent=2, ensure_ascii=False, trailing_newline=True)
    return str(output_path)


def append_github_step_summary(markdown: str, logger: logging.Logger | None = None) -> bool:
    """Append markdown to GitHub Actions job summary when available."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return False

    try:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(markdown.rstrip() + "\n\n")
        return True
    except OSError as e:
        if logger is not None:
            logger.warning("Failed to write GitHub step summary: %s", e)
        return False


def build_quality_step_summary(results: list[ProcessingResult]) -> str:
    """Build markdown summary table for quality issues."""
    total_views = len(results)
    successful_views = sum(1 for r in results if r.success)
    all_issues = aggregate_quality_issues(results)
    severity_counts = count_quality_issues_by_severity(all_issues)

    lines = [
        "### Data Quality Summary",
        "",
        f"- Data views processed: {successful_views}/{total_views}",
        f"- Total quality issues: {len(all_issues)}",
        "",
    ]

    if severity_counts:
        lines.extend(["| Severity | Count |", "|---|---:|"])
        for severity in QUALITY_SEVERITY_ORDER:
            count = severity_counts.get(severity, 0)
            if count > 0:
                lines.append(f"| {severity} | {count} |")
        lines.append("")

    lines.extend(["| Data View | ID | Issues | Highest Severity |", "|---|---|---:|---|"])
    for result in results:
        highest = "NONE"
        for severity in QUALITY_SEVERITY_ORDER:
            if result.dq_severity_counts.get(severity, 0) > 0:
                highest = severity
                break
        lines.append(
            f"| {result.data_view_name or '-'} | `{result.data_view_id}` | {result.dq_issues_count} | {highest} |",
        )

    return "\n".join(lines)


def build_diff_step_summary(diff_result: DiffResult) -> str:
    """Build markdown summary table for diff output."""
    summary = diff_result.summary
    total_changes = summary.total_changes + summary.calc_metrics_changed + summary.segments_changed
    lines = [
        "### Diff Summary",
        "",
        f"- Source: `{diff_result.metadata_diff.source_id}` ({diff_result.metadata_diff.source_name})",
        f"- Target: `{diff_result.metadata_diff.target_id}` ({diff_result.metadata_diff.target_name})",
        f"- Total changes: {total_changes}",
        "",
        "| Type | Source | Target | Added | Removed | Modified | Unchanged |",
        "|---|---:|---:|---:|---:|---:|---:|",
        (
            f"| Metrics | {summary.source_metrics_count} | {summary.target_metrics_count} | "
            f"{summary.metrics_added} | {summary.metrics_removed} | {summary.metrics_modified} | {summary.metrics_unchanged} |"
        ),
        (
            f"| Dimensions | {summary.source_dimensions_count} | {summary.target_dimensions_count} | "
            f"{summary.dimensions_added} | {summary.dimensions_removed} | {summary.dimensions_modified} | {summary.dimensions_unchanged} |"
        ),
    ]

    if summary.source_calc_metrics_count > 0 or summary.target_calc_metrics_count > 0:
        lines.append(
            f"| Calc Metrics | {summary.source_calc_metrics_count} | {summary.target_calc_metrics_count} | "
            f"{summary.calc_metrics_added} | {summary.calc_metrics_removed} | {summary.calc_metrics_modified} | {summary.calc_metrics_unchanged} |",
        )
    if summary.source_segments_count > 0 or summary.target_segments_count > 0:
        lines.append(
            f"| Segments | {summary.source_segments_count} | {summary.target_segments_count} | "
            f"{summary.segments_added} | {summary.segments_removed} | {summary.segments_modified} | {summary.segments_unchanged} |",
        )

    return "\n".join(lines)


def build_org_step_summary(result: OrgReportResult) -> str:
    """Build markdown summary table for org-report output."""
    dist = result.distribution
    lines = [
        "### Org Report Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Data Views Analyzed | {result.successful_data_views} / {result.total_data_views} |",
        f"| Data View Fetch Failures | {result.failed_data_views} |",
        f"| Total Unique Components | {result.total_unique_components} |",
        f"| Total Unique Metrics | {result.total_unique_metrics} |",
        f"| Total Unique Dimensions | {result.total_unique_dimensions} |",
        f"| Core Components | {dist.total_core} |",
        f"| Common Components | {dist.total_common} |",
        f"| Limited Components | {dist.total_limited} |",
        f"| Isolated Components | {dist.total_isolated} |",
        f"| Recommendations | {len(result.recommendations)} |",
        f"| Governance Violations | {len(result.governance_violations or [])} |",
        f"| Duration (s) | {result.duration:.2f} |",
    ]
    return "\n".join(lines)
