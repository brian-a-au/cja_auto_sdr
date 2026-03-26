"""Console renderers for org report output."""

from __future__ import annotations

from cja_auto_sdr.core.constants import BANNER_WIDTH
from cja_auto_sdr.org.models import (
    OrgReportComparison,
    OrgReportConfig,
    OrgReportResult,
    OrgReportTrending,
)
from cja_auto_sdr.org.writers.common import _render_distribution_bar as _render_distribution_bar_impl
from cja_auto_sdr.org.writers.compat import make_override_proxy
from cja_auto_sdr.org.writers.trending import _print_trending_console_section as _print_trending_console_section_impl

__all__ = [
    "write_org_report_comparison_console",
    "write_org_report_console",
    "write_org_report_stats_only",
]

_render_distribution_bar = make_override_proxy(
    __name__,
    "_render_distribution_bar",
    _render_distribution_bar_impl,
)
_print_trending_console_section = make_override_proxy(
    __name__,
    "_print_trending_console_section",
    _print_trending_console_section_impl,
)


def write_org_report_console(
    result: OrgReportResult,
    config: OrgReportConfig,
    quiet: bool = False,
    trending: OrgReportTrending | None = None,
) -> None:
    """Write org report to console with ASCII distribution bars.

    Args:
        result: OrgReportResult from analysis
        config: OrgReportConfig used for analysis
        quiet: Suppress decorative output
        trending: Optional trending data to append
    """
    if quiet:
        return

    total_dvs = result.successful_data_views
    print()
    print("=" * 110)
    title = f"ORG-WIDE COMPONENT ANALYSIS REPORT: {result.org_id}"
    if result.is_sampled:
        title += " [SAMPLED]"
    print(title)
    print("=" * 110)
    print(f"Generated: {result.timestamp}")
    if result.is_sampled:
        print(
            f"Data Views Analyzed: {result.successful_data_views} / {result.total_data_views} (sampled from {result.total_available_data_views})",
        )
    else:
        print(f"Data Views Analyzed: {result.successful_data_views} / {result.total_data_views}")
    print(f"Data View Fetch Failures: {result.failed_data_views}")
    print(f"Analysis Duration: {result.duration:.2f}s")
    print()

    # Data Views Summary Table
    print("-" * 110)
    print("DATA VIEWS")
    print("-" * 110)
    print(f"{'Name':<50} {'ID':<30} {'Metrics':>8} {'Dimensions':>10} {'Status':<8}")
    print("-" * 110)

    for dv in sorted(result.data_view_summaries, key=lambda x: x.data_view_name):
        name = dv.data_view_name[:48] + ".." if len(dv.data_view_name) > 50 else dv.data_view_name
        if dv.error is not None:
            print(f"{name:<50} {dv.data_view_id:<30} {'ERROR':>8} {'':>10} {dv.status:<8}")
        else:
            print(f"{name:<50} {dv.data_view_id:<30} {dv.metric_count:>8} {dv.dimension_count:>10} {dv.status:<8}")

    print()

    # Component Summary
    print("-" * 110)
    print("COMPONENT SUMMARY")
    print("-" * 110)

    total_metrics = result.total_unique_metrics
    total_dims = result.total_unique_dimensions
    total_all = result.total_unique_components

    # Calculate total aggregates (non-unique counts across all data views)
    total_metrics_aggregate = sum(dv.metric_count for dv in result.data_view_summaries if dv.error is None)
    total_dimensions_aggregate = sum(dv.dimension_count for dv in result.data_view_summaries if dv.error is None)
    total_components_aggregate = sum(dv.total_components for dv in result.data_view_summaries if dv.error is None)
    total_derived_metrics = sum(dv.derived_metric_count for dv in result.data_view_summaries if dv.error is None)
    total_derived_dimensions = sum(dv.derived_dimension_count for dv in result.data_view_summaries if dv.error is None)
    total_derived_fields = total_derived_metrics + total_derived_dimensions

    dist = result.distribution
    # Build correct label for core threshold: "50% DVs" for percentage, ">=5 DVs" for absolute count
    if config.core_min_count is None:
        core_threshold_label = f"{int(config.core_threshold * 100)}%"
    else:
        core_threshold_label = f">={config.core_min_count}"

    print(f"{'':30} {'Metrics':>12} {'Dimensions':>12} {'Total':>10}")
    print(f"{'Total unique components':<30} {total_metrics:>12} {total_dims:>12} {total_all:>10}")
    print(
        f"{'Total (non-unique)':<30} {total_metrics_aggregate:>12} {total_dimensions_aggregate:>12} {total_components_aggregate:>10}",
    )
    print(
        f"{'Derived fields (non-unique)':<30} {total_derived_metrics:>12} {total_derived_dimensions:>12} {total_derived_fields:>10}",
    )
    # Add "+" suffix only for percentage labels; absolute labels already have ">="
    core_label_suffix = " DVs" if config.core_min_count is not None else "+ DVs"
    print(
        f"{'Core (in ' + core_threshold_label + core_label_suffix + ')':<30} {len(dist.core_metrics):>12} {len(dist.core_dimensions):>12} {dist.total_core:>10}",
    )
    print(
        f"{'Common (in 25-49% DVs)':<30} {len(dist.common_metrics):>12} {len(dist.common_dimensions):>12} {dist.total_common:>10}",
    )
    print(
        f"{'Limited (in 2+ DVs)':<30} {len(dist.limited_metrics):>12} {len(dist.limited_dimensions):>12} {dist.total_limited:>10}",
    )
    print(
        f"{'Isolated (in 1 DV only)':<30} {len(dist.isolated_metrics):>12} {len(dist.isolated_dimensions):>12} {dist.total_isolated:>10}",
    )
    print()

    # Distribution Visualization
    print("-" * 110)
    print("DISTRIBUTION")
    print("-" * 110)

    print("Metrics by data view coverage:")
    print(f"  Core:     {_render_distribution_bar(len(dist.core_metrics), total_metrics)} ({len(dist.core_metrics)})")
    print(
        f"  Common:   {_render_distribution_bar(len(dist.common_metrics), total_metrics)} ({len(dist.common_metrics)})",
    )
    print(
        f"  Limited:  {_render_distribution_bar(len(dist.limited_metrics), total_metrics)} ({len(dist.limited_metrics)})",
    )
    print(
        f"  Isolated: {_render_distribution_bar(len(dist.isolated_metrics), total_metrics)} ({len(dist.isolated_metrics)})",
    )
    print()

    print("Dimensions by data view coverage:")
    print(
        f"  Core:     {_render_distribution_bar(len(dist.core_dimensions), total_dims)} ({len(dist.core_dimensions)})",
    )
    print(
        f"  Common:   {_render_distribution_bar(len(dist.common_dimensions), total_dims)} ({len(dist.common_dimensions)})",
    )
    print(
        f"  Limited:  {_render_distribution_bar(len(dist.limited_dimensions), total_dims)} ({len(dist.limited_dimensions)})",
    )
    print(
        f"  Isolated: {_render_distribution_bar(len(dist.isolated_dimensions), total_dims)} ({len(dist.isolated_dimensions)})",
    )
    print()

    # Core Components (if not summary only)
    if not config.summary_only and dist.total_core > 0:
        print("-" * 110)
        print(f"CORE COMPONENTS (in {core_threshold_label}{core_label_suffix})")
        print("-" * 110)

        if dist.core_metrics:
            print("\nCore Metrics:")
            for comp_id in dist.core_metrics[:15]:  # Limit to 15
                info = result.component_index.get(comp_id)
                if info:
                    if info.name:
                        display = f"{info.name} ({comp_id})"
                        display = display[:55] + ".." if len(display) > 57 else display
                        print(f"  {display:<57} {info.presence_count}/{total_dvs} DVs")
                    else:
                        print(f"  {comp_id:<57} {info.presence_count}/{total_dvs} DVs")
            if len(dist.core_metrics) > 15:
                print(f"  ... and {len(dist.core_metrics) - 15} more")

        if dist.core_dimensions:
            print("\nCore Dimensions:")
            for comp_id in dist.core_dimensions[:15]:
                info = result.component_index.get(comp_id)
                if info:
                    if info.name:
                        display = f"{info.name} ({comp_id})"
                        display = display[:55] + ".." if len(display) > 57 else display
                        print(f"  {display:<57} {info.presence_count}/{total_dvs} DVs")
                    else:
                        print(f"  {comp_id:<57} {info.presence_count}/{total_dvs} DVs")
            if len(dist.core_dimensions) > 15:
                print(f"  ... and {len(dist.core_dimensions) - 15} more")
        print()

    # Similarity Matrix (if computed)
    if result.similarity_pairs:
        print("-" * 110)
        print("HIGH OVERLAP PAIRS")
        print("-" * 110)
        effective_threshold = min(config.overlap_threshold, 0.9)
        threshold_note = ""
        if config.overlap_threshold > 0.9:
            threshold_note = f" (configured {config.overlap_threshold * 100:.0f}%, capped at 90% for governance checks)"
        print(f"Pairs with >= {effective_threshold * 100:.0f}% Jaccard similarity{threshold_note}:")
        print()

        for pair in result.similarity_pairs[:10]:  # Limit to top 10
            name1 = pair.dv1_name[:25] + ".." if len(pair.dv1_name) > 27 else pair.dv1_name
            name2 = pair.dv2_name[:25] + ".." if len(pair.dv2_name) > 27 else pair.dv2_name
            print(f"  {name1:<27} <-> {name2:<27} {pair.jaccard_similarity * 100:>5.1f}%")
            print(f"  {'':27}     {'':27} ({pair.shared_count} shared)")

        if len(result.similarity_pairs) > 10:
            print(f"\n  ... and {len(result.similarity_pairs) - 10} more pairs")

        # Show drift details if enabled
        if config.include_drift:
            has_drift = any(pair.only_in_dv1 or pair.only_in_dv2 for pair in result.similarity_pairs[:5])
            if has_drift:
                print()
                print("Drift Details (top pairs):")
                for pair in result.similarity_pairs[:5]:
                    if pair.only_in_dv1 or pair.only_in_dv2:
                        print(f"\n  {pair.dv1_name} <-> {pair.dv2_name}:")
                        if pair.only_in_dv1:
                            print(f"    Only in {pair.dv1_name[:20]}: {len(pair.only_in_dv1)} components")
                            for comp_id in pair.only_in_dv1[:3]:
                                name = pair.only_in_dv1_names.get(comp_id, "") if pair.only_in_dv1_names else ""
                                display = f"{name} ({comp_id})" if name else comp_id
                                print(f"      - {display[:50]}")
                            if len(pair.only_in_dv1) > 3:
                                print(f"      ... and {len(pair.only_in_dv1) - 3} more")
                        if pair.only_in_dv2:
                            print(f"    Only in {pair.dv2_name[:20]}: {len(pair.only_in_dv2)} components")
                            for comp_id in pair.only_in_dv2[:3]:
                                name = pair.only_in_dv2_names.get(comp_id, "") if pair.only_in_dv2_names else ""
                                display = f"{name} ({comp_id})" if name else comp_id
                                print(f"      - {display[:50]}")
                            if len(pair.only_in_dv2) > 3:
                                print(f"      ... and {len(pair.only_in_dv2) - 3} more")
        print()

    # Component Type Breakdown (if enabled)
    if config.include_component_types and not config.summary_only:
        # Aggregate type counts
        total_standard_metrics = sum(s.standard_metric_count for s in result.data_view_summaries if not s.has_error)
        total_derived_metrics = sum(s.derived_metric_count for s in result.data_view_summaries if not s.has_error)
        total_standard_dims = sum(s.standard_dimension_count for s in result.data_view_summaries if not s.has_error)
        total_derived_dims = sum(s.derived_dimension_count for s in result.data_view_summaries if not s.has_error)

        if total_standard_metrics + total_derived_metrics > 0:
            print("-" * 110)
            print("COMPONENT TYPES (aggregate counts across DVs, standard vs derived field breakdown)")
            print("-" * 110)
            total_metrics = total_standard_metrics + total_derived_metrics
            total_dims = total_standard_dims + total_derived_dims
            # Calculate percentages
            std_metric_pct = (total_standard_metrics / total_metrics * 100) if total_metrics > 0 else 0
            der_metric_pct = (total_derived_metrics / total_metrics * 100) if total_metrics > 0 else 0
            std_dim_pct = (total_standard_dims / total_dims * 100) if total_dims > 0 else 0
            der_dim_pct = (total_derived_dims / total_dims * 100) if total_dims > 0 else 0
            print(f"{'':18} {'Total':>10} {'Standard':>12} {'% Total':>8} {'Derived':>10} {'% Total':>8}")
            print(
                f"{'Metrics':<18} {total_metrics:>10} {total_standard_metrics:>12} {std_metric_pct:>7.1f}% {total_derived_metrics:>10} {der_metric_pct:>7.1f}%",
            )
            print(
                f"{'Dimensions':<18} {total_dims:>10} {total_standard_dims:>12} {std_dim_pct:>7.1f}% {total_derived_dims:>10} {der_dim_pct:>7.1f}%",
            )
            print()

    # Clusters (if enabled)
    if result.clusters:
        print("-" * 110)
        print("DATA VIEW CLUSTERS")
        print("-" * 110)
        print(f"Found {len(result.clusters)} clusters:")
        print()
        for cluster in result.clusters[:10]:
            name = cluster.cluster_name or f"Cluster {cluster.cluster_id}"
            print(f"  [{cluster.cluster_id}] {name} ({cluster.size} DVs, cohesion: {cluster.cohesion_score:.0%})")
            for dv_name in cluster.data_view_names[:3]:
                print(f"      - {dv_name[:50]}")
            if cluster.size > 3:
                print(f"      ... and {cluster.size - 3} more")
        if len(result.clusters) > 10:
            print(f"\n  ... and {len(result.clusters) - 10} more clusters")
        print()

    # Governance Violations (Feature 1)
    if result.governance_violations:
        print("-" * 110)
        print("GOVERNANCE VIOLATIONS")
        print("-" * 110)
        for violation in result.governance_violations:
            print(f"\n[!] {violation.get('message', '')}")
            print(f"    Threshold: {violation.get('threshold')}, Actual: {violation.get('actual')}")
        print()

    # Owner Summary (Feature 5)
    if result.owner_summary:
        print("-" * 110)
        print("OWNER SUMMARY")
        print("-" * 110)
        owner_data = result.owner_summary.get("by_owner", {})
        sorted_owners = result.owner_summary.get("owners_sorted_by_dv_count", [])
        print(f"{'Owner':<30} {'DVs':>6} {'Metrics':>10} {'Dimensions':>12} {'Avg/DV':>8}")
        print("-" * 110)
        for owner in sorted_owners[:15]:
            stats = owner_data.get(owner, {})
            print(
                f"{owner[:30]:<30} {stats.get('data_view_count', 0):>6} "
                f"{stats.get('total_metrics', 0):>10} {stats.get('total_dimensions', 0):>12} "
                f"{stats.get('avg_components_per_dv', 0):>8.1f}",
            )
        if len(sorted_owners) > 15:
            print(f"  ... and {len(sorted_owners) - 15} more owners")
        print()

    # Naming Audit (Feature 3)
    if result.naming_audit:
        print("-" * 110)
        print("NAMING AUDIT")
        print("-" * 110)
        audit = result.naming_audit
        styles = audit.get("case_styles", {})
        print("Case styles distribution:")
        for style, count in sorted(styles.items(), key=lambda x: -x[1]):
            pct = count / audit.get("total_components", 1) * 100
            print(f"  {style:<15} {count:>6} ({pct:>5.1f}%)")
        if audit.get("recommendations"):
            print("\nNaming Recommendations:")
            for rec in audit["recommendations"]:
                print(f"  [{rec.get('severity', 'info')}] {rec.get('message', '')}")
        print()

    # Stale Components (Feature 6)
    if result.stale_components:
        print("-" * 110)
        print("STALE COMPONENTS")
        print("-" * 110)
        print(f"Found {len(result.stale_components)} components with stale naming patterns:")
        print()
        # Group by pattern type
        by_pattern: dict[str, list] = {}
        for comp in result.stale_components:
            pattern = comp.get("pattern", "unknown")
            if pattern not in by_pattern:
                by_pattern[pattern] = []
            by_pattern[pattern].append(comp)
        for pattern, comps in by_pattern.items():
            print(f"  {pattern} ({len(comps)} components):")
            for comp in comps[:5]:
                name = comp.get("name", comp.get("component_id", ""))[:50]
                print(f"    - {name}")
            if len(comps) > 5:
                print(f"    ... and {len(comps) - 5} more")
        print()

    # Recommendations
    if result.recommendations:
        print("-" * 110)
        print("RECOMMENDATIONS")
        print("-" * 110)

        for _i, rec in enumerate(result.recommendations, 1):
            severity_icon = {"high": "!", "medium": "?", "low": "i"}.get(rec.get("severity", "low"), "\u00b7")
            print(f"\n[{severity_icon}] {rec.get('reason', 'No details')}")

            if rec.get("data_view"):
                print(f"    Data View: {rec.get('data_view_name', '')} ({rec.get('data_view')})")
            if rec.get("data_view_1"):
                print(f"    Pair: {rec.get('data_view_1_name', '')} <-> {rec.get('data_view_2_name', '')}")

        print()

    # Trending section (v3.4.0)
    _print_trending_console_section(trending)


def write_org_report_stats_only(
    result: OrgReportResult,
    quiet: bool = False,
    trending: OrgReportTrending | None = None,
) -> None:
    """Write minimal org-report stats to console (Feature 2: --org-stats mode).

    Args:
        result: OrgReportResult from analysis
        quiet: Suppress output
        trending: Optional trending window to append after the stats summary
    """
    if quiet:
        return

    print()
    print("=" * BANNER_WIDTH)
    print(f"ORG STATS: {result.org_id}")
    print("=" * BANNER_WIDTH)
    print(f"Data Views: {result.successful_data_views} analyzed")
    print(f"Fetch Failures: {result.failed_data_views}")
    print(f"Components: {result.total_unique_components} unique")
    print(f"  Metrics:    {result.total_unique_metrics}")
    print(f"  Dimensions: {result.total_unique_dimensions}")
    print("Distribution:")
    dist = result.distribution
    total = result.total_unique_components or 1
    print(f"  Core:     {dist.total_core:>6} ({dist.total_core / total * 100:>5.1f}%)")
    print(f"  Common:   {dist.total_common:>6} ({dist.total_common / total * 100:>5.1f}%)")
    print(f"  Limited:  {dist.total_limited:>6} ({dist.total_limited / total * 100:>5.1f}%)")
    print(f"  Isolated: {dist.total_isolated:>6} ({dist.total_isolated / total * 100:>5.1f}%)")
    print(f"Duration: {result.duration:.2f}s")
    print("=" * BANNER_WIDTH)
    print()

    _print_trending_console_section(trending)


def write_org_report_comparison_console(comparison: OrgReportComparison, quiet: bool = False) -> None:
    """Write org-report comparison to console with trending arrows (Feature 4).

    Args:
        comparison: OrgReportComparison from compare_org_reports()
        quiet: Suppress output
    """
    if quiet:
        return

    def trend_arrow(delta: int) -> str:
        if delta > 0:
            return f"\u2191{delta}"
        if delta < 0:
            return f"\u2193{abs(delta)}"
        return "\u21920"

    print()
    print("=" * 70)
    print("ORG REPORT COMPARISON (TRENDING)")
    print("=" * 70)
    print(f"Previous: {comparison.previous_timestamp}")
    print(f"Current:  {comparison.current_timestamp}")
    print()

    summary = comparison.summary
    print("-" * 70)
    print("CHANGES")
    print("-" * 70)
    print(f"Data Views:  {trend_arrow(summary.get('data_views_delta', 0))}")
    print(f"Components:  {trend_arrow(summary.get('components_delta', 0))}")
    print(f"Core:        {trend_arrow(summary.get('core_delta', 0))}")
    print(f"Isolated:    {trend_arrow(summary.get('isolated_delta', 0))}")
    print()

    if comparison.data_views_added:
        print(f"Data Views Added ({len(comparison.data_views_added)}):")
        for _i, dv_name in enumerate(comparison.data_views_added_names[:5]):
            print(f"  + {dv_name}")
        if len(comparison.data_views_added) > 5:
            print(f"  ... and {len(comparison.data_views_added) - 5} more")

    if comparison.data_views_removed:
        print(f"Data Views Removed ({len(comparison.data_views_removed)}):")
        for dv_name in comparison.data_views_removed_names[:5]:
            print(f"  - {dv_name}")
        if len(comparison.data_views_removed) > 5:
            print(f"  ... and {len(comparison.data_views_removed) - 5} more")

    if comparison.new_high_similarity_pairs:
        print(f"\nNew High-Similarity Pairs ({len(comparison.new_high_similarity_pairs)}):")
        for pair in comparison.new_high_similarity_pairs[:3]:
            print(f"  ! {pair.get('dv1_id', '')} <-> {pair.get('dv2_id', '')}")

    if comparison.resolved_pairs:
        print(f"\nResolved High-Similarity Pairs ({len(comparison.resolved_pairs)}):")
        for pair in comparison.resolved_pairs[:3]:
            print(f"  \u2713 {pair.get('dv1_id', '')} <-> {pair.get('dv2_id', '')}")

    print()
    print("=" * 70)
    print()
