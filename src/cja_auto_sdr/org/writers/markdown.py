"""Markdown org-report writer.

Renders OrgReportResult as a GitHub-flavored Markdown document.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from pathlib import Path

from cja_auto_sdr.core.version import __version__
from cja_auto_sdr.org.models import (
    OrgReportResult,
    OrgReportTrending,
)
from cja_auto_sdr.org.writers.common import (
    _format_recommendation_context_entries,
    _normalize_recommendation_for_json,
)
from cja_auto_sdr.org.writers.trending import (
    _render_trending_markdown,
)


def write_org_report_markdown(
    result: OrgReportResult,
    output_path: Path | None,
    output_dir: str,
    logger: logging.Logger,
    trending: OrgReportTrending | None = None,
) -> str:
    """Write org report as GitHub-flavored markdown.

    Args:
        result: OrgReportResult from analysis
        output_path: Optional specific output path
        output_dir: Output directory if no path specified
        logger: Logger instance
        trending: Optional trending data to append

    Returns:
        Path to created Markdown file
    """
    if output_path:
        file_path = output_path if str(output_path).endswith(".md") else Path(f"{output_path}.md")
    else:
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        file_path = Path(output_dir) / f"org_report_{result.org_id}_{timestamp}.md"

    file_path.parent.mkdir(parents=True, exist_ok=True)

    lines = []

    # Header
    lines.append(f"# Org-Wide Component Analysis Report: {result.org_id}")
    lines.append("")
    lines.append(f"**Organization:** {result.org_id}")
    lines.append(f"**Generated:** {result.timestamp}")
    lines.append("")

    # Summary Table
    # Calculate total aggregates (non-unique counts across all data views)
    total_metrics_aggregate = sum(dv.metric_count for dv in result.data_view_summaries if dv.error is None)
    total_dimensions_aggregate = sum(dv.dimension_count for dv in result.data_view_summaries if dv.error is None)
    total_components_aggregate = sum(dv.total_components for dv in result.data_view_summaries if dv.error is None)
    total_derived_metrics = sum(dv.derived_metric_count for dv in result.data_view_summaries if dv.error is None)
    total_derived_dimensions = sum(dv.derived_dimension_count for dv in result.data_view_summaries if dv.error is None)
    total_derived_fields = total_derived_metrics + total_derived_dimensions

    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | Value |")
    lines.append("|--------|-------|")
    lines.append(f"| Data Views Analyzed | {result.successful_data_views} / {result.total_data_views} |")
    lines.append(f"| Data View Fetch Failures | {result.failed_data_views} |")
    lines.append(f"| Total Unique Metrics | {result.total_unique_metrics:,} |")
    lines.append(f"| Total Unique Dimensions | {result.total_unique_dimensions:,} |")
    lines.append(f"| Total Unique Components | {result.total_unique_components:,} |")
    lines.append(f"| Total Metrics (Non-Unique) | {total_metrics_aggregate:,} |")
    lines.append(f"| Total Dimensions (Non-Unique) | {total_dimensions_aggregate:,} |")
    lines.append(f"| Total Components (Non-Unique) | {total_components_aggregate:,} |")
    lines.append(f"| Derived Metrics (Non-Unique) | {total_derived_metrics:,} |")
    lines.append(f"| Derived Dimensions (Non-Unique) | {total_derived_dimensions:,} |")
    lines.append(f"| Total Derived Fields (Non-Unique) | {total_derived_fields:,} |")
    lines.append(f"| Analysis Duration | {result.duration:.2f}s |")
    lines.append("")

    # Distribution
    lines.append("## Component Distribution")
    lines.append("")
    lines.append("| Category | Metrics | Dimensions | Total |")
    lines.append("|----------|--------:|----------:|------:|")

    dist = result.distribution
    # Build correct label for core threshold
    if result.parameters.core_min_count is None:
        core_label = f"{int(result.parameters.core_threshold * 100)}%+"
        core_desc = f"{int(result.parameters.core_threshold * 100)}% or more of"
    else:
        core_label = f">={result.parameters.core_min_count}"
        core_desc = f"{result.parameters.core_min_count} or more"

    lines.append(
        f"| Core ({core_label} DVs) | {len(dist.core_metrics)} | {len(dist.core_dimensions)} | {dist.total_core} |",
    )
    lines.append(
        f"| Common (25-49% DVs) | {len(dist.common_metrics)} | {len(dist.common_dimensions)} | {dist.total_common} |",
    )
    lines.append(
        f"| Limited (2+ DVs) | {len(dist.limited_metrics)} | {len(dist.limited_dimensions)} | {dist.total_limited} |",
    )
    lines.append(
        f"| Isolated (1 DV only) | {len(dist.isolated_metrics)} | {len(dist.isolated_dimensions)} | {dist.total_isolated} |",
    )
    lines.append("")

    # Data Views Table
    lines.append("## Data Views")
    lines.append("")
    lines.append("| Name | ID | Metrics | Dimensions | Status |")
    lines.append("|------|----|---------:|----------:|--------|")

    for dv in sorted(result.data_view_summaries, key=lambda x: x.data_view_name):
        name = dv.data_view_name.replace("|", "\\|")
        if dv.error is not None:
            lines.append(f"| {name} | `{dv.data_view_id}` | ERROR | - | {dv.status} |")
        else:
            lines.append(f"| {name} | `{dv.data_view_id}` | {dv.metric_count} | {dv.dimension_count} | {dv.status} |")
    lines.append("")

    # Core Components
    if dist.total_core > 0:
        lines.append("## Core Components")
        lines.append("")
        lines.append(f"Components present in {core_desc} data views.")
        lines.append("")

        # Check if any components have names
        has_names = any(info.name for info in result.component_index.values())

        if dist.core_metrics:
            lines.append("### Core Metrics")
            lines.append("")
            if has_names:
                lines.append("| Component ID | Name | Data View Count |")
                lines.append("|--------------|------|----------------:|")
            else:
                lines.append("| Component ID | Data View Count |")
                lines.append("|--------------|----------------:|")
            for comp_id in dist.core_metrics[:20]:
                info = result.component_index.get(comp_id)
                if info:
                    if has_names:
                        name = (info.name or "-").replace("|", "\\|")
                        lines.append(f"| `{comp_id}` | {name} | {info.presence_count} |")
                    else:
                        lines.append(f"| `{comp_id}` | {info.presence_count} |")
            if len(dist.core_metrics) > 20:
                if has_names:
                    lines.append(f"| *... {len(dist.core_metrics) - 20} more* | | |")
                else:
                    lines.append(f"| *... {len(dist.core_metrics) - 20} more* | |")
            lines.append("")

        if dist.core_dimensions:
            lines.append("### Core Dimensions")
            lines.append("")
            if has_names:
                lines.append("| Component ID | Name | Data View Count |")
                lines.append("|--------------|------|----------------:|")
            else:
                lines.append("| Component ID | Data View Count |")
                lines.append("|--------------|----------------:|")
            for comp_id in dist.core_dimensions[:20]:
                info = result.component_index.get(comp_id)
                if info:
                    if has_names:
                        name = (info.name or "-").replace("|", "\\|")
                        lines.append(f"| `{comp_id}` | {name} | {info.presence_count} |")
                    else:
                        lines.append(f"| `{comp_id}` | {info.presence_count} |")
            if len(dist.core_dimensions) > 20:
                if has_names:
                    lines.append(f"| *... {len(dist.core_dimensions) - 20} more* | | |")
                else:
                    lines.append(f"| *... {len(dist.core_dimensions) - 20} more* | |")
            lines.append("")

    # Similarity Matrix
    if result.similarity_pairs:
        lines.append("## High Overlap Pairs")
        lines.append("")
        effective_threshold = min(result.parameters.overlap_threshold, 0.9)
        threshold_note = ""
        if result.parameters.overlap_threshold > 0.9:
            threshold_note = (
                f" (configured {int(result.parameters.overlap_threshold * 100)}%, capped at 90% for governance checks)"
            )
        lines.append(f"Data view pairs with >= {int(effective_threshold * 100)}% Jaccard similarity{threshold_note}.")
        lines.append("")
        lines.append("| Data View 1 | Data View 2 | Similarity | Shared |")
        lines.append("|-------------|-------------|------------|-------:|")

        for pair in result.similarity_pairs[:15]:
            name1 = pair.dv1_name.replace("|", "\\|")
            name2 = pair.dv2_name.replace("|", "\\|")
            lines.append(f"| {name1} | {name2} | {pair.jaccard_similarity * 100:.1f}% | {pair.shared_count} |")

        if len(result.similarity_pairs) > 15:
            lines.append(f"| *... {len(result.similarity_pairs) - 15} more pairs* | | | |")
        lines.append("")

    # Recommendations
    if result.recommendations:
        lines.append("## Recommendations")
        lines.append("")

        for i, raw_rec in enumerate(result.recommendations, 1):
            rec = _normalize_recommendation_for_json(raw_rec)
            severity = rec.get("severity", "low")
            severity_badge = {"high": "\U0001f534", "medium": "\U0001f7e1", "low": "\U0001f535"}.get(severity, "\u26aa")
            rec_type = str(rec.get("type", "Unknown")).replace("_", " ").title()
            lines.append(f"### {i}. {severity_badge} {rec_type}")
            lines.append("")
            reason = str(rec.get("reason", "No details provided.")).replace("|", "\\|").replace("`", "\\`")
            lines.append(reason)
            lines.append("")

            for label, value in _format_recommendation_context_entries(rec):
                value_text = str(value).replace("|", "\\|").replace("`", "\\`")
                lines.append(f"- **{label}:** {value_text}")
            lines.append("")

    # Trending section (v3.4.0)
    if trending is not None and len(trending.snapshots) >= 2:
        lines.append(_render_trending_markdown(trending))

    # Footer
    lines.append("---")
    lines.append("")
    lines.append(f"*Report generated by CJA SDR Generator v{__version__}*")

    # Write file
    with open(file_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    logger.info(f"Markdown report written to {file_path}")
    return str(file_path)
