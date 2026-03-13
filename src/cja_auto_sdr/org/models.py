"""
Org-wide analysis data models.

This module contains all dataclasses used for org-wide component analysis.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from cja_auto_sdr.org.identifiers import normalize_org_report_data_view_id


@dataclass
class OrgReportConfig:
    """Configuration for org-wide component analysis.

    Attributes:
        filter_pattern: Regex pattern to include data views by name
        exclude_pattern: Regex pattern to exclude data views by name
        limit: Maximum number of data views to analyze
        core_threshold: Threshold for "core" components (default: 0.5 = 50% of DVs)
        core_min_count: Alternative absolute count for "core" (overrides threshold)
        overlap_threshold: Threshold for "high overlap" pairs (default: 0.8 = 80%)
        summary_only: Show summary statistics only
        verbose: Include full component lists
        include_names: Include component names (slower, requires extra API calls)
        skip_similarity: Skip O(n^2) similarity matrix calculation
        include_component_types: Include standard/derived field breakdown
        include_metadata: Include owner, creation/modification dates, descriptions
        include_drift: Include component drift details for similar pairs
        sample_size: Number of DVs to randomly sample (None = no sampling)
        sample_seed: Random seed for reproducible sampling
        sample_stratified: Stratify sample by name prefix
        use_cache: Enable incremental caching
        cache_max_age_hours: Maximum cache age in hours
        clear_cache: Clear cache before running
        enable_clustering: Enable hierarchical clustering
        cluster_method: Clustering method (ward, average, complete)
        isolated_review_threshold: Min isolated components to trigger review recommendation
    """

    filter_pattern: str | None = None
    exclude_pattern: str | None = None
    limit: int | None = None
    core_threshold: float = 0.5
    core_min_count: int | None = None
    overlap_threshold: float = 0.8
    summary_only: bool = False
    verbose: bool = False
    include_names: bool = False
    skip_similarity: bool = False
    # Component type breakdown
    include_component_types: bool = True
    # Metadata
    include_metadata: bool = False
    # Drift detection
    include_drift: bool = False
    # Sampling
    sample_size: int | None = None
    sample_seed: int | None = None
    sample_stratified: bool = False
    # Caching
    use_cache: bool = False
    cache_max_age_hours: int = 24
    clear_cache: bool = False
    # Clustering
    enable_clustering: bool = False
    cluster_method: str = (
        "average"  # 'average' (recommended) or 'complete' - both work correctly with Jaccard distances
    )
    quiet: bool = False  # Suppress progress output (tqdm)
    # Similarity guardrails
    similarity_max_dvs: int | None = 250  # Skip similarity if DVs exceed this count (unless forced)
    force_similarity: bool = False  # Force similarity even if guardrails would skip
    # Threading safety
    cja_per_thread: bool = True  # Use a separate cjapy client per thread for safety
    # Recommendation thresholds
    isolated_review_threshold: int = 20  # Min isolated components per DV to trigger review recommendation
    # Governance thresholds (Feature 1)
    duplicate_threshold: int | None = None  # Max allowed high-similarity pairs (>=90%)
    isolated_threshold: float | None = None  # Max isolated component percentage (0.0-1.0)
    fail_on_threshold: bool = False  # Enable exit code 2 when thresholds exceeded
    # Org-stats mode (Feature 2)
    org_stats_only: bool = False  # Quick summary only mode
    # Naming audit (Feature 3)
    audit_naming: bool = False  # Detect naming pattern inconsistencies
    # Trending/drift report (Feature 4)
    compare_org_report: str | None = None  # Path to previous org-report JSON for comparison
    # Owner summary (Feature 5)
    include_owner_summary: bool = False  # Group stats by data view owner
    # Stale component heuristics (Feature 6)
    flag_stale: bool = False  # Flag components with stale naming patterns
    # Memory warning threshold
    memory_warning_threshold_mb: int | None = 100  # Warn if component index exceeds this size (0 to disable)
    # Memory hard limit
    memory_limit_mb: int | None = None  # Abort if component index exceeds this size (None = no limit)
    # Smart cache validation
    validate_cache: bool = False  # Validate cache entries against data view modification timestamps
    # Concurrency lock
    skip_lock: bool = False  # Skip the file-based lock that prevents concurrent runs (for testing)


@dataclass
class ComponentInfo:
    """Metadata for a component tracked across data views.

    Attributes:
        component_id: Unique identifier for the component
        component_type: Type of component ('metric' or 'dimension')
        name: Human-readable name (populated if include_names=True)
        data_views: Set of data view IDs containing this component
    """

    component_id: str
    component_type: str  # 'metric' or 'dimension'
    name: str | None = None
    data_views: set[str] = field(default_factory=set)

    @property
    def presence_count(self) -> int:
        """Number of data views containing this component."""
        return len(self.data_views)


@dataclass
class DataViewSummary:
    """Summary of a data view's components for org-wide analysis.

    Attributes:
        data_view_id: Data view identifier
        data_view_name: Human-readable name
        metric_ids: Set of metric IDs in this data view
        dimension_ids: Set of dimension IDs in this data view
        metric_count: Count of metrics
        dimension_count: Count of dimensions
        status: Data view status (active/inactive)
        fetch_duration: Time taken to fetch this data view
        error: Error message if fetch failed
        metric_names: Optional dict mapping metric ID to name
        dimension_names: Optional dict mapping dimension ID to name
        standard_metric_count: Count of standard metrics
        derived_metric_count: Count of derived metrics
        standard_dimension_count: Count of standard dimensions
        derived_dimension_count: Count of derived dimensions
        owner: Data view owner name
        owner_id: Data view owner ID
        created: ISO timestamp when DV was created
        modified: ISO timestamp when DV was last modified
        description: Data view description
        has_description: Whether DV has a description
    """

    data_view_id: str
    data_view_name: str
    metric_ids: set[str] = field(default_factory=set)
    dimension_ids: set[str] = field(default_factory=set)
    metric_count: int = 0
    dimension_count: int = 0
    status: str = "active"
    fetch_duration: float = 0.0
    error: str | None = None
    metric_names: dict[str, str] | None = None
    dimension_names: dict[str, str] | None = None
    # Component type breakdown
    standard_metric_count: int = 0
    derived_metric_count: int = 0
    standard_dimension_count: int = 0
    derived_dimension_count: int = 0
    # Metadata fields
    owner: str | None = None
    owner_id: str | None = None
    created: str | None = None
    modified: str | None = None
    description: str | None = None
    has_description: bool = False

    @property
    def has_error(self) -> bool:
        """Whether this summary represents a fetch failure."""
        return self.error is not None

    @property
    def normalized_error_reason(self) -> str | None:
        """Fetch failure reason with normalized whitespace.

        This is the *read-time* normalization layer and the canonical accessor
        that all output writers should use.  It complements the *write-time*
        layer in ``OrgAnalyzer._normalize_exception_message`` which runs once
        at capture time.  Returns None when there is no fetch failure.
        """
        if self.error is None:
            return None
        normalized_reason = " ".join(self.error.split())
        return normalized_reason or "Unknown error"

    @property
    def total_components(self) -> int:
        """Total number of components (metrics + dimensions)."""
        return self.metric_count + self.dimension_count

    @property
    def all_component_ids(self) -> set[str]:
        """Combined set of all component IDs."""
        return self.metric_ids | self.dimension_ids

    def get_component_name(self, component_id: str) -> str | None:
        """Get the name for a component ID if available."""
        if self.metric_names and component_id in self.metric_names:
            return self.metric_names[component_id]
        if self.dimension_names and component_id in self.dimension_names:
            return self.dimension_names[component_id]
        return None


@dataclass
class SimilarityPair:
    """Similarity measurement between two data views.

    Uses Jaccard similarity: |A ∩ B| / |A U B|

    Attributes:
        dv1_id: First data view ID
        dv1_name: First data view name
        dv2_id: Second data view ID
        dv2_name: Second data view name
        jaccard_similarity: Jaccard similarity score (0.0 to 1.0)
        shared_count: Number of shared components
        union_count: Total unique components in union
        only_in_dv1: Component IDs unique to first data view (drift detection)
        only_in_dv2: Component IDs unique to second data view (drift detection)
        only_in_dv1_names: Optional dict mapping unique DV1 component IDs to names
        only_in_dv2_names: Optional dict mapping unique DV2 component IDs to names
    """

    dv1_id: str
    dv1_name: str
    dv2_id: str
    dv2_name: str
    jaccard_similarity: float
    shared_count: int
    union_count: int
    # Drift detection fields
    only_in_dv1: list[str] = field(default_factory=list)
    only_in_dv2: list[str] = field(default_factory=list)
    only_in_dv1_names: dict[str, str] | None = None
    only_in_dv2_names: dict[str, str] | None = None


@dataclass
class DataViewCluster:
    """A cluster of related data views identified by hierarchical clustering.

    Attributes:
        cluster_id: Unique identifier for this cluster
        cluster_name: Inferred name from common prefixes (optional)
        data_view_ids: List of data view IDs in this cluster
        data_view_names: List of data view names in this cluster
        cohesion_score: Average within-cluster similarity (0.0 to 1.0)
    """

    cluster_id: int
    cluster_name: str | None = None
    data_view_ids: list[str] = field(default_factory=list)
    data_view_names: list[str] = field(default_factory=list)
    cohesion_score: float = 0.0

    @property
    def size(self) -> int:
        """Number of data views in this cluster."""
        return len(self.data_view_ids)


@dataclass
class ComponentDistribution:
    """Distribution of components across data views.

    Buckets:
        - core: In >= core_threshold% of data views
        - common: In 25-49% of data views
        - limited: In 2+ data views but < 25%
        - isolated: In exactly 1 data view
    """

    core_metrics: list[str] = field(default_factory=list)
    core_dimensions: list[str] = field(default_factory=list)
    common_metrics: list[str] = field(default_factory=list)
    common_dimensions: list[str] = field(default_factory=list)
    limited_metrics: list[str] = field(default_factory=list)
    limited_dimensions: list[str] = field(default_factory=list)
    isolated_metrics: list[str] = field(default_factory=list)
    isolated_dimensions: list[str] = field(default_factory=list)

    @property
    def total_core(self) -> int:
        return len(self.core_metrics) + len(self.core_dimensions)

    @property
    def total_common(self) -> int:
        return len(self.common_metrics) + len(self.common_dimensions)

    @property
    def total_limited(self) -> int:
        return len(self.limited_metrics) + len(self.limited_dimensions)

    @property
    def total_isolated(self) -> int:
        return len(self.isolated_metrics) + len(self.isolated_dimensions)


@dataclass
class OrgReportResult:
    """Complete result of org-wide component analysis.

    Attributes:
        timestamp: ISO timestamp of report generation
        org_id: Organization ID (if available)
        parameters: Configuration parameters used
        data_view_summaries: Summary for each analyzed data view
        component_index: Index mapping component_id -> ComponentInfo
        distribution: Component distribution across buckets
        similarity_pairs: Pairwise similarity scores (None if skipped)
        recommendations: List of governance recommendations
        duration: Total analysis duration in seconds
        clusters: Data view clusters (None if clustering disabled)
        is_sampled: Whether this report used sampling
        total_available_data_views: Total DVs available before sampling
    """

    timestamp: str
    org_id: str
    parameters: OrgReportConfig
    data_view_summaries: list[DataViewSummary]
    component_index: dict[str, ComponentInfo]
    distribution: ComponentDistribution
    similarity_pairs: list[SimilarityPair] | None
    recommendations: list[dict[str, Any]]
    duration: float
    # Clustering results
    clusters: list[DataViewCluster] | None = None
    # Sampling metadata
    is_sampled: bool = False
    total_available_data_views: int = 0
    # Governance thresholds (Feature 1)
    governance_violations: list[dict[str, Any]] | None = None
    thresholds_exceeded: bool = False
    # Naming audit (Feature 3)
    naming_audit: dict[str, Any] | None = None
    # Owner summary (Feature 5)
    owner_summary: dict[str, Any] | None = None
    # Stale components (Feature 6)
    stale_components: list[dict[str, Any]] | None = None

    @property
    def total_data_views(self) -> int:
        return len(self.data_view_summaries)

    @property
    def successful_data_views(self) -> int:
        return sum(1 for summary in self.data_view_summaries if not summary.has_error)

    @property
    def failed_data_views(self) -> int:
        return sum(1 for summary in self.data_view_summaries if summary.has_error)

    @property
    def failed_data_view_ids(self) -> list[str]:
        return [summary.data_view_id for summary in self.data_view_summaries if summary.has_error]

    @property
    def failed_data_view_reason_counts(self) -> dict[str, int]:
        """Count failed data views by normalized error reason."""
        reason_counts: Counter[str] = Counter()
        for summary in self.data_view_summaries:
            normalized_reason = summary.normalized_error_reason
            if normalized_reason is None:
                continue
            reason_counts[normalized_reason] += 1
        return dict(sorted(reason_counts.items()))

    @property
    def total_unique_metrics(self) -> int:
        return sum(1 for component in self.component_index.values() if component.component_type == "metric")

    @property
    def total_unique_dimensions(self) -> int:
        return sum(1 for component in self.component_index.values() if component.component_type == "dimension")

    @property
    def total_unique_components(self) -> int:
        return len(self.component_index)


@dataclass
class OrgReportComparison:
    """Result of comparing two org-reports for trending/drift analysis (Feature 4).

    Attributes:
        current_timestamp: Timestamp of the current report
        previous_timestamp: Timestamp of the previous report
        data_views_added: List of data view IDs added since previous report
        data_views_removed: List of data view IDs removed since previous report
        components_added: Count of new unique components
        components_removed: Count of removed unique components
        core_delta: Change in core component count
        isolated_delta: Change in isolated component count
        new_high_similarity_pairs: New pairs with >=90% similarity
        resolved_pairs: Previously high-similarity pairs now resolved
        summary: Dict with overview statistics
    """

    current_timestamp: str
    previous_timestamp: str
    data_views_added: list[str] = field(default_factory=list)
    data_views_removed: list[str] = field(default_factory=list)
    data_views_added_names: list[str] = field(default_factory=list)
    data_views_removed_names: list[str] = field(default_factory=list)
    components_added: int = 0
    components_removed: int = 0
    core_delta: int = 0
    isolated_delta: int = 0
    new_high_similarity_pairs: list[dict[str, Any]] = field(default_factory=list)
    resolved_pairs: list[dict[str, Any]] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)


@dataclass
class OrgReportComparisonInput:
    """Normalized comparison input for org-report delta calculations."""

    timestamp: str
    data_view_ids: set[str] = field(default_factory=set)
    has_data_view_ids: bool = False
    complete_data_view_ids: bool | None = None
    data_view_names: dict[str, str] = field(default_factory=dict)
    data_view_count: int = 0
    comparison_data_view_count: int | None = None
    component_count: int = 0
    component_ids: set[str] | None = None
    core_count: int = 0
    isolated_count: int = 0
    high_similarity_pairs: set[tuple[str, str]] = field(default_factory=set)
    complete_high_similarity_pairs: bool | None = None


def _resolve_data_view_total(source: OrgReportComparisonInput) -> int:
    """Resolve the headline data-view total for summary deltas.

    Exact ID sets win when they are known complete. Otherwise we preserve the
    reported snapshot headline count because summary deltas describe total
    population change, not just the successfully compared subset. The analyzed
    count is only a legacy fallback for summary totals when a manual snapshot
    never supplied a headline total; it must not be used to infer exact ID
    completeness.
    """
    if _has_complete_data_view_ids(source):
        return len(source.data_view_ids)
    reported_total = _safe_non_negative_int(source.data_view_count)
    if reported_total > 0 or source.comparison_data_view_count is None:
        return reported_total
    return _safe_non_negative_int(source.comparison_data_view_count)


def _has_complete_data_view_ids(source: OrgReportComparisonInput) -> bool:
    """Return True when data_view_ids cover the full snapshot population."""
    if source.complete_data_view_ids is not None:
        return source.complete_data_view_ids
    return source.has_data_view_ids


def _has_complete_high_similarity_pairs(source: OrgReportComparisonInput) -> bool:
    """Return True when high_similarity_pairs reflect full similarity output."""
    if source.complete_high_similarity_pairs is not None:
        return source.complete_high_similarity_pairs
    # Manual snapshots must opt in explicitly; an empty pair set is ambiguous
    # between "no high-similarity pairs" and "similarity analysis was partial".
    return False


def _resolve_component_total(source: OrgReportComparisonInput) -> int:
    """Resolve component totals, preferring exact component identities when present."""
    if source.component_ids is not None:
        return len(source.component_ids)
    return _safe_non_negative_int(source.component_count)


def _safe_non_negative_int(value: Any) -> int:
    """Coerce arbitrary count-like values to a non-negative integer."""
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return max(0, value)
    if isinstance(value, float):
        return max(0, int(value))
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return 0
        try:
            return max(0, int(stripped))
        except ValueError:
            return 0
    return 0


def _resolve_component_change_counts(
    previous: OrgReportComparisonInput,
    current: OrgReportComparisonInput,
) -> tuple[int, int]:
    """Compute added/removed component counts with exact-set fallback."""
    if previous.component_ids is not None and current.component_ids is not None:
        return (
            len(current.component_ids - previous.component_ids),
            len(previous.component_ids - current.component_ids),
        )

    current_total = _resolve_component_total(current)
    previous_total = _resolve_component_total(previous)
    return (
        max(0, current_total - previous_total),
        max(0, previous_total - current_total),
    )


def _serialize_similarity_pair_delta(pairs: set[tuple[str, str]]) -> list[dict[str, str]]:
    """Render normalized similarity-pair identities in stable order."""
    return [{"dv1_id": dv1_id, "dv2_id": dv2_id} for dv1_id, dv2_id in sorted(pairs)]


def _normalized_similarity_pairs(pairs: set[tuple[str, str]]) -> set[tuple[str, str]]:
    """Normalize manual similarity-pair sets before diffing them."""
    normalized_pairs: set[tuple[str, str]] = set()
    for pair in pairs:
        if not isinstance(pair, tuple) or len(pair) != 2:
            continue
        dv1_id = normalize_org_report_data_view_id(pair[0])
        dv2_id = normalize_org_report_data_view_id(pair[1])
        if not dv1_id or not dv2_id:
            continue
        normalized_pairs.add(tuple(sorted((dv1_id, dv2_id))))
    return normalized_pairs


def _resolve_high_similarity_pair_changes(
    previous: OrgReportComparisonInput,
    current: OrgReportComparisonInput,
) -> tuple[set[tuple[str, str]], set[tuple[str, str]]]:
    """Return exact similarity-pair deltas only when both sides are complete."""
    if not _has_complete_high_similarity_pairs(previous) or not _has_complete_high_similarity_pairs(current):
        return set(), set()

    previous_pairs = _normalized_similarity_pairs(previous.high_similarity_pairs)
    current_pairs = _normalized_similarity_pairs(current.high_similarity_pairs)
    return (
        current_pairs - previous_pairs,
        previous_pairs - current_pairs,
    )


def _resolve_data_view_id_changes(
    previous: OrgReportComparisonInput,
    current: OrgReportComparisonInput,
) -> tuple[list[str], list[str]]:
    """Return exact added/removed data-view IDs when both sides expose them."""
    if not _has_complete_data_view_ids(previous) or not _has_complete_data_view_ids(current):
        return [], []
    return (
        sorted(current.data_view_ids - previous.data_view_ids),
        sorted(previous.data_view_ids - current.data_view_ids),
    )


def build_org_report_comparison(
    *,
    previous: OrgReportComparisonInput,
    current: OrgReportComparisonInput,
) -> OrgReportComparison:
    """Build a comparison from normalized org-report snapshot inputs."""
    added_ids, removed_ids = _resolve_data_view_id_changes(previous, current)
    components_added, components_removed = _resolve_component_change_counts(previous, current)

    current_dv_total = _resolve_data_view_total(current)
    previous_dv_total = _resolve_data_view_total(previous)
    current_component_total = _resolve_component_total(current)
    previous_component_total = _resolve_component_total(previous)

    new_pairs, resolved_pairs = _resolve_high_similarity_pair_changes(previous, current)

    return OrgReportComparison(
        current_timestamp=current.timestamp,
        previous_timestamp=previous.timestamp,
        data_views_added=added_ids,
        data_views_removed=removed_ids,
        data_views_added_names=[current.data_view_names.get(dv_id, dv_id) for dv_id in added_ids],
        data_views_removed_names=[previous.data_view_names.get(dv_id, dv_id) for dv_id in removed_ids],
        components_added=components_added,
        components_removed=components_removed,
        core_delta=current.core_count - previous.core_count,
        isolated_delta=current.isolated_count - previous.isolated_count,
        new_high_similarity_pairs=_serialize_similarity_pair_delta(new_pairs),
        resolved_pairs=_serialize_similarity_pair_delta(resolved_pairs),
        summary={
            "data_views_delta": current_dv_total - previous_dv_total,
            "components_delta": current_component_total - previous_component_total,
            "core_delta": current.core_count - previous.core_count,
            "isolated_delta": current.isolated_count - previous.isolated_count,
            "new_duplicates": len(new_pairs),
            "resolved_duplicates": len(resolved_pairs),
        },
    )


# ---------------------------------------------------------------------------
# Trending dataclasses (v3.4.0)
# ---------------------------------------------------------------------------


@dataclass
class TrendingSnapshot:
    """A single point-in-time snapshot of org-report key metrics.

    Extracted from a cached org-report JSON file.  Snapshots are ordered
    oldest-to-newest within an OrgReportTrending instance.
    """

    timestamp: str
    org_id: str | None = None
    data_view_count: int | None = None
    analyzed_data_view_count: int | None = None
    component_count: int = 0
    core_count: int = 0
    isolated_count: int = 0
    high_sim_pair_count: int = 0
    # Snapshot identity metadata for persistence/deduplication.
    snapshot_id: str | None = None
    content_hash: str | None = None
    source_path: str | None = None
    component_ids: set[str] | None = None
    high_similarity_pairs: set[tuple[str, str]] = field(default_factory=set)
    # Per-data-view component counts for drift scoring
    dv_component_counts: dict[str, int] = field(default_factory=dict)
    dv_core_ratios: dict[str, float] = field(default_factory=dict)
    dv_max_similarity: dict[str, float] = field(default_factory=dict)
    dv_ids: set[str] = field(default_factory=set)
    dv_names: dict[str, str] = field(default_factory=dict)
    has_data_view_ids: bool = False
    complete_data_view_ids: bool | None = None
    complete_high_similarity_pairs: bool | None = None
    _complete_data_view_ids_explicit: bool = field(default=False, init=False, repr=False, compare=False)
    _data_view_count_explicit: bool = field(default=False, init=False, repr=False, compare=False)
    _reported_data_view_count: int = field(default=0, init=False, repr=False, compare=False)
    _data_view_count_declares_zero: bool = field(default=False, init=False, repr=False, compare=False)

    def __setattr__(self, name: str, value: Any) -> None:
        """Normalize manual DV state while preserving count-provenance flags."""
        if name == "data_view_count":
            declared_total = _snapshot_count_declares_total(value)
            object.__setattr__(self, "_data_view_count_declares_zero", _snapshot_count_declares_zero(value))
            object.__setattr__(self, "_data_view_count_explicit", declared_total)
            object.__setattr__(
                self, "_reported_data_view_count", _safe_non_negative_int(value) if declared_total else 0
            )
            value = 0 if value is None else _safe_non_negative_int(value)
        elif name == "analyzed_data_view_count":
            value = None if value is None else _safe_non_negative_int(value)
        object.__setattr__(self, name, value)
        if name == "complete_data_view_ids":
            object.__setattr__(self, "_complete_data_view_ids_explicit", value is not None)

    def __post_init__(self) -> None:
        """Normalize manual DV fidelity flags without overstating snapshot coverage."""
        data_view_assessment = _snapshot_data_view_assessment(self)
        if self.data_view_count != data_view_assessment.effective_total:
            object.__setattr__(self, "data_view_count", data_view_assessment.effective_total)
        if not self.has_data_view_ids and data_view_assessment.ids:
            self.has_data_view_ids = True
        if self.complete_data_view_ids is None:
            object.__setattr__(self, "complete_data_view_ids", data_view_assessment.complete_data_view_ids)
        if self.complete_high_similarity_pairs is None:
            self.complete_high_similarity_pairs = False


@dataclass(frozen=True)
class _TrendingSnapshotIdentifierAssessment:
    """Normalized manual DV identity state for one authoritative source."""

    ids: set[str]
    source: str
    ambiguous: bool


@dataclass(frozen=True)
class _TrendingSnapshotDataViewAssessment:
    """Centralized manual DV identity and fidelity state for one snapshot."""

    ids: set[str]
    names: dict[str, str]
    has_data_view_ids: bool
    ambiguous_identifiers: bool
    reported_total: int
    reported_total_declares_zero: bool
    effective_total: int
    complete_data_view_ids: bool


def _snapshot_data_view_ids(snapshot: TrendingSnapshot) -> set[str]:
    """Return normalized authoritative DV IDs for one manual snapshot."""
    return set(_snapshot_identifier_assessment(snapshot).ids)


def _snapshot_data_view_names(
    snapshot: TrendingSnapshot,
    *,
    authoritative_ids: set[str] | None = None,
    restrict_to_authoritative_ids: bool = False,
) -> dict[str, str]:
    """Return normalized DV names, filtered to authoritative IDs when needed."""
    normalized_names: dict[str, str] = {}
    for raw_dv_id, dv_name in snapshot.dv_names.items():
        normalized_dv_id = normalize_org_report_data_view_id(raw_dv_id)
        if not normalized_dv_id:
            continue
        if (
            restrict_to_authoritative_ids
            and authoritative_ids is not None
            and normalized_dv_id not in authoritative_ids
        ):
            continue
        normalized_names[normalized_dv_id] = str(dv_name)
    return normalized_names


def _normalized_snapshot_identifier_values(values: Any) -> tuple[str, ...]:
    """Return non-empty normalized identifiers from one manual snapshot source."""
    normalized_values: list[str] = []
    for value in values:
        normalized_value = normalize_org_report_data_view_id(value)
        if normalized_value:
            normalized_values.append(normalized_value)
    return tuple(normalized_values)


def _snapshot_identifier_source_has_invalid_values(values: Any) -> bool:
    """Return True when a manual ID source contains values that normalize to empty."""
    return any(not normalize_org_report_data_view_id(value) for value in values)


def _snapshot_identifier_source_has_normalized_duplicates(values: Any) -> bool:
    """Return True when one manual ID source collapses to duplicate normalized IDs."""
    normalized_values = _normalized_snapshot_identifier_values(values)
    return len(normalized_values) != len(set(normalized_values))


def _snapshot_identifier_assessment(snapshot: TrendingSnapshot) -> _TrendingSnapshotIdentifierAssessment:
    """Return normalized DV identities from the authoritative manual source."""
    if snapshot.dv_ids:
        normalized_values = _normalized_snapshot_identifier_values(snapshot.dv_ids)
        return _TrendingSnapshotIdentifierAssessment(
            ids=set(normalized_values),
            source="dv_ids",
            ambiguous=(
                _snapshot_identifier_source_has_invalid_values(snapshot.dv_ids)
                or _snapshot_identifier_source_has_normalized_duplicates(snapshot.dv_ids)
            ),
        )
    if snapshot.dv_names:
        normalized_values = _normalized_snapshot_identifier_values(snapshot.dv_names)
        return _TrendingSnapshotIdentifierAssessment(
            ids=set(normalized_values),
            source="dv_names",
            ambiguous=(
                _snapshot_identifier_source_has_invalid_values(snapshot.dv_names)
                or _snapshot_identifier_source_has_normalized_duplicates(snapshot.dv_names)
            ),
        )
    return _TrendingSnapshotIdentifierAssessment(ids=set(), source="none", ambiguous=False)


def _snapshot_has_ambiguous_data_view_identifiers(snapshot: TrendingSnapshot) -> bool:
    """Return True when the authoritative manual DV identity source is ambiguous."""
    return _snapshot_identifier_assessment(snapshot).ambiguous


def _snapshot_declares_data_view_total(snapshot: TrendingSnapshot) -> bool:
    """Return True when a manual snapshot explicitly supplied a DV headline total."""
    if "_data_view_count_explicit" in snapshot.__dict__:
        return bool(snapshot._data_view_count_explicit)
    return _snapshot_declares_zero_data_views(snapshot) or _safe_non_negative_int(snapshot.data_view_count) > 0


def _snapshot_has_analyzed_data_view_total(snapshot: TrendingSnapshot) -> bool:
    """Return True when a manual snapshot explicitly supplied an analyzed DV total."""
    return snapshot.analyzed_data_view_count is not None


def _snapshot_count_declares_zero(raw_value: Any) -> bool:
    """Return True when a raw manual count value explicitly signals zero."""
    if isinstance(raw_value, bool):
        return False
    if isinstance(raw_value, int | float):
        return raw_value == 0
    if isinstance(raw_value, str):
        return raw_value.strip() == "0"
    return False


def _snapshot_count_declares_total(raw_value: Any) -> bool:
    """Return True when a raw manual count value explicitly supplies a usable total."""
    return _snapshot_count_declares_zero(raw_value) or _safe_non_negative_int(raw_value) > 0


def _snapshot_declares_zero_data_views(snapshot: TrendingSnapshot) -> bool:
    """Return True when a manual snapshot explicitly reports a zero-DV population."""
    if "_data_view_count_declares_zero" in snapshot.__dict__:
        return bool(snapshot._data_view_count_declares_zero)
    raw_total = snapshot.data_view_count
    return _snapshot_count_declares_zero(raw_total)


def _snapshot_reported_data_view_total(snapshot: TrendingSnapshot) -> int:
    """Return the explicit manual headline total, if one was actually supplied."""
    if "_reported_data_view_count" in snapshot.__dict__:
        return _safe_non_negative_int(snapshot._reported_data_view_count)
    if _snapshot_declares_data_view_total(snapshot):
        return _safe_non_negative_int(snapshot.data_view_count)
    return 0


def _snapshot_inferred_complete_data_view_ids(
    snapshot: TrendingSnapshot,
    normalized_dv_ids: set[str] | None = None,
    *,
    ambiguous_identifiers: bool | None = None,
) -> bool:
    """Infer manual DV completeness from normalized IDs and explicit totals."""
    observed_ids = normalized_dv_ids if normalized_dv_ids is not None else _snapshot_data_view_ids(snapshot)
    if ambiguous_identifiers is None:
        ambiguous_identifiers = _snapshot_has_ambiguous_data_view_identifiers(snapshot)
    if ambiguous_identifiers:
        return False

    if observed_ids:
        if _snapshot_declares_data_view_total(snapshot):
            return len(observed_ids) == _snapshot_reported_data_view_total(snapshot)
        # Preserve legacy/manual exact-ID comparisons when callers supplied
        # only an authoritative ID set. An analyzed-only count cannot prove
        # completeness because failed rows may still have stable IDs.
        return not _snapshot_has_analyzed_data_view_total(snapshot)
    return _snapshot_declares_zero_data_views(snapshot)


def _snapshot_data_view_ids_cover_snapshot(
    snapshot: TrendingSnapshot,
    normalized_dv_ids: set[str] | None = None,
) -> bool:
    """Infer whether manual snapshot IDs cover the full reported snapshot population."""
    return _snapshot_inferred_complete_data_view_ids(snapshot, normalized_dv_ids)


def _snapshot_uses_explicit_complete_data_view_ids(snapshot: TrendingSnapshot) -> bool:
    """Return True when complete_data_view_ids came from the caller, not inference."""
    return getattr(snapshot, "_complete_data_view_ids_explicit", snapshot.complete_data_view_ids is not None)


def _snapshot_effective_data_view_total(
    snapshot: TrendingSnapshot,
    normalized_dv_ids: set[str] | None = None,
    *,
    ambiguous_identifiers: bool | None = None,
    complete_data_view_ids: bool | None = None,
) -> int:
    """Return the effective DV total used by comparisons, deltas, and rendering."""
    observed_ids = normalized_dv_ids if normalized_dv_ids is not None else _snapshot_data_view_ids(snapshot)
    if complete_data_view_ids is None:
        complete_data_view_ids = _snapshot_inferred_complete_data_view_ids(
            snapshot,
            observed_ids,
            ambiguous_identifiers=ambiguous_identifiers,
        )
    if complete_data_view_ids:
        return len(observed_ids)

    reported_total = _snapshot_reported_data_view_total(snapshot)
    if _snapshot_declares_data_view_total(snapshot):
        return reported_total
    if snapshot.analyzed_data_view_count is None:
        return 0
    return _safe_non_negative_int(snapshot.analyzed_data_view_count)


def _snapshot_data_view_assessment(snapshot: TrendingSnapshot) -> _TrendingSnapshotDataViewAssessment:
    """Return centralized manual DV fidelity state for comparison and rendering."""
    identifier_state = _snapshot_identifier_assessment(snapshot)
    normalized_ids = set(identifier_state.ids)
    normalized_names = _snapshot_data_view_names(
        snapshot,
        authoritative_ids=normalized_ids if identifier_state.source == "dv_ids" else None,
        restrict_to_authoritative_ids=identifier_state.source == "dv_ids",
    )
    ambiguous_identifiers = identifier_state.ambiguous
    complete_data_view_ids = _snapshot_inferred_complete_data_view_ids(
        snapshot,
        normalized_ids,
        ambiguous_identifiers=ambiguous_identifiers,
    )
    if _snapshot_uses_explicit_complete_data_view_ids(snapshot):
        complete_data_view_ids = bool(snapshot.complete_data_view_ids)
    effective_total = _snapshot_effective_data_view_total(
        snapshot,
        normalized_ids,
        ambiguous_identifiers=ambiguous_identifiers,
        complete_data_view_ids=complete_data_view_ids,
    )
    return _TrendingSnapshotDataViewAssessment(
        ids=normalized_ids,
        names=normalized_names,
        has_data_view_ids=bool(normalized_ids) or snapshot.has_data_view_ids,
        ambiguous_identifiers=ambiguous_identifiers,
        reported_total=_snapshot_reported_data_view_total(snapshot),
        reported_total_declares_zero=_snapshot_declares_zero_data_views(snapshot),
        effective_total=effective_total,
        complete_data_view_ids=bool(complete_data_view_ids),
    )


def _snapshot_effective_data_view_count(snapshot: TrendingSnapshot) -> int:
    """Return the centralized effective DV total for one snapshot."""
    return _snapshot_data_view_assessment(snapshot).effective_total


def _snapshot_comparison_input(snapshot: TrendingSnapshot) -> OrgReportComparisonInput:
    """Normalize one TrendingSnapshot into comparison input fields."""
    data_view_state = _snapshot_data_view_assessment(snapshot)
    return OrgReportComparisonInput(
        timestamp=snapshot.timestamp,
        data_view_ids=data_view_state.ids,
        has_data_view_ids=data_view_state.has_data_view_ids,
        complete_data_view_ids=data_view_state.complete_data_view_ids,
        data_view_names=data_view_state.names,
        data_view_count=data_view_state.effective_total,
        comparison_data_view_count=snapshot.analyzed_data_view_count,
        component_count=snapshot.component_count,
        component_ids=None if snapshot.component_ids is None else set(snapshot.component_ids),
        core_count=snapshot.core_count,
        isolated_count=snapshot.isolated_count,
        high_similarity_pairs=_normalized_similarity_pairs(set(snapshot.high_similarity_pairs)),
        complete_high_similarity_pairs=snapshot.complete_high_similarity_pairs,
    )


@dataclass
class TrendingDelta:
    """Computed delta between two consecutive TrendingSnapshots."""

    from_timestamp: str
    to_timestamp: str
    data_view_delta: int = 0
    component_delta: int = 0
    core_delta: int = 0
    isolated_delta: int = 0
    high_sim_pair_delta: int = 0


@dataclass
class OrgReportTrending:
    """Multi-snapshot trending analysis across cached org-reports.

    Attributes:
        snapshots: Ordered oldest-to-newest list of snapshot summaries.
        deltas: Computed deltas between consecutive snapshots.
        drift_scores: Per-data-view drift score (0.0-1.0) across the window.
        window_size: Actual number of snapshots included.
    """

    snapshots: list[TrendingSnapshot] = field(default_factory=list)
    deltas: list[TrendingDelta] = field(default_factory=list)
    drift_scores: dict[str, float] = field(default_factory=dict)
    window_size: int = 0

    def to_comparison(self) -> OrgReportComparison | None:
        """Produce an OrgReportComparison for the most recent pair.

        Returns None if fewer than 2 snapshots exist.
        """
        if len(self.snapshots) < 2:
            return None

        prev = self.snapshots[-2]
        curr = self.snapshots[-1]
        return build_org_report_comparison(
            previous=_snapshot_comparison_input(prev),
            current=_snapshot_comparison_input(curr),
        )
