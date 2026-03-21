"""
CJA Segments Inventory

Generates a comprehensive inventory of segments (filters) from the CJA API.
Surfaces segment definitions, complexity scores, governance metadata,
and all available API fields for complete SDR documentation.

Since many calculated metrics use segment filters, this inventory provides
complete component documentation alongside the calculated metrics inventory.

Supported modes:
- SDR output integration (Excel/JSON/CSV/HTML/Markdown)
- Snapshot diff comparisons (same data view over time)

Version: 1.0.0
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from cja_auto_sdr.inventory.utils import (
    BatchProcessingStats,
    coerce_display_text,
    coerce_scalar_text,
    extract_owner,
    extract_short_name,
    extract_tags,
    format_iso_date,
    normalize_api_response,
    normalize_func_name,
    validate_required_id,
)

# ==================== VERSION ====================

__version__ = "1.0.0"

# ==================== CONSTANTS ====================

# Mapping of internal function names to human-readable display names
SEGMENT_FUNCTION_DISPLAY_NAMES: dict[str, str] = {
    # Logical operators
    "and": "And",
    "or": "Or",
    "not": "Not",
    # Comparison operators
    "eq": "Equals",
    "ne": "Not Equals",
    "gt": "Greater Than",
    "gte": "Greater Than or Equal",
    "lt": "Less Than",
    "lte": "Less Than or Equal",
    # String operators
    "contains": "Contains",
    "not-contains": "Does Not Contain",
    "starts-with": "Starts With",
    "ends-with": "Ends With",
    "matches": "Matches Regex",
    "not-matches": "Does Not Match Regex",
    # Existence operators
    "exists": "Exists",
    "not-exists": "Does Not Exist",
    # Container types
    "container": "Container",
    "sequence": "Sequential",
    "sequence-prefix": "Sequence Prefix",
    "sequence-suffix": "Sequence Suffix",
    "exclude": "Exclude",
    # Attribution
    "attribution": "Attribution",
    "attribution-instance": "Attribution Instance",
    # References
    "segment": "Segment Reference",
    "dimension": "Dimension Reference",
    "metric": "Metric Reference",
    # Functions
    "streq": "String Equals",
    "strne": "String Not Equals",
    "streq-in": "String In List",
    "strne-in": "String Not In List",
    "within": "Within",
    "after": "After",
    "before": "Before",
    "event": "Event",
    "hit": "Hit",
    "visit": "Visit",
    "visitor": "Visitor",
}

# Complexity score weights for segments
COMPLEXITY_WEIGHTS = {
    "predicates": 0.30,
    "logic_operators": 0.20,
    "nesting": 0.20,
    "dimension_refs": 0.10,
    "metric_refs": 0.10,
    "regex": 0.10,
}

# Max values for complexity normalization
COMPLEXITY_MAX_VALUES = {
    "predicates": 50,
    "logic_operators": 20,
    "nesting": 8,
    "dimension_refs": 15,
    "metric_refs": 5,
    "regex": 5,
}


# ==================== DATA CLASSES ====================


@dataclass
class SegmentSummary:
    """Summary of a single segment for inventory output.

    Captures all available API fields for comprehensive documentation.
    """

    segment_id: str
    segment_name: str
    description: str
    owner: str

    # Complexity
    complexity_score: float

    # Functions
    functions_used: list[str]  # Human-readable function names
    functions_used_internal: list[str]  # Internal func values

    # Structure
    predicate_count: int
    logic_operator_count: int
    nesting_depth: int
    container_count: int

    # References
    dimension_references: list[str]  # Referenced dimension IDs
    metric_references: list[str]  # Referenced metric IDs
    other_segment_references: list[str]  # Referenced segment IDs

    # Summary
    definition_summary: str  # Brief description of what the segment defines
    container_type: str  # visitor, visit, hit

    # Governance fields
    approved: bool = False  # Approval status
    favorite: bool = False  # User favorite status
    tags: list[str] = field(default_factory=list)  # Organizational tags

    # Timestamps
    created: str = ""  # ISO 8601 creation timestamp
    modified: str = ""  # ISO 8601 last modified timestamp

    # Ownership details
    owner_id: str = ""  # Owner's user ID

    # Sharing info
    shares: list[dict[str, Any]] = field(default_factory=list)  # Share recipients
    shared_to_count: int = 0  # Number of users/groups shared with

    # Data view association
    data_view_id: str = ""  # Associated data view ID
    site_title: str = ""  # Site/company title

    # Raw definition for full fidelity
    definition_json: str = ""  # Original definition JSON string

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for DataFrame/Excel/CSV output.

        Includes all fields relevant for tabular SDR documentation.
        """
        return {
            "name": self.segment_name,
            "id": self.segment_id,
            "description": self.description or "-",
            "owner": self.owner or "-",
            "approved": "Yes" if self.approved else "No",
            "tags": ", ".join(self.tags) if self.tags else "-",
            "complexity_score": self.complexity_score,
            "container_type": self.container_type.title() if self.container_type else "-",
            "functions_used": ", ".join(self.functions_used) if self.functions_used else "-",
            "dimension_references": ", ".join(self.dimension_references) if self.dimension_references else "-",
            "metric_references": ", ".join(self.metric_references) if self.metric_references else "-",
            "segment_references": ", ".join(self.other_segment_references) if self.other_segment_references else "-",
            "definition_summary": self.definition_summary or "-",
            "created": format_iso_date(self.created),
            "modified": format_iso_date(self.modified),
            "shared_to": self.shared_to_count if self.shared_to_count > 0 else "-",
            "definition_json": self.definition_json,  # Keep empty string for raw JSON
        }

    def to_full_dict(self) -> dict[str, Any]:
        """Convert to full dictionary for JSON output with all details.

        Includes every available field for comprehensive JSON export.
        """
        return {
            # Identity
            "segment_id": self.segment_id,
            "segment_name": self.segment_name,
            "description": self.description,
            # Ownership
            "owner": self.owner,
            "owner_id": self.owner_id,
            # Governance
            "approved": self.approved,
            "favorite": self.favorite,
            "tags": self.tags,
            # Timestamps
            "created": self.created,
            "modified": self.modified,
            # Sharing
            "shares": self.shares,
            "shared_to_count": self.shared_to_count,
            # Data view
            "data_view_id": self.data_view_id,
            "site_title": self.site_title,
            # Definition analysis
            "complexity_score": self.complexity_score,
            "container_type": self.container_type,
            "functions_used": self.functions_used,
            "functions_used_internal": self.functions_used_internal,
            "predicate_count": self.predicate_count,
            "logic_operator_count": self.logic_operator_count,
            "nesting_depth": self.nesting_depth,
            "container_count": self.container_count,
            "dimension_references": self.dimension_references,
            "metric_references": self.metric_references,
            "other_segment_references": self.other_segment_references,
            "definition_summary": self.definition_summary,
            # Raw definition
            "definition_json": self.definition_json,
        }


@dataclass
class SegmentsInventory:
    """Complete inventory of segments for a data view."""

    data_view_id: str
    data_view_name: str
    segments: list[SegmentSummary] = field(default_factory=list)

    @property
    def total_segments(self) -> int:
        return len(self.segments)

    @property
    def avg_complexity(self) -> float:
        if not self.segments:
            return 0.0
        return sum(s.complexity_score for s in self.segments) / len(self.segments)

    @property
    def max_complexity(self) -> float:
        if not self.segments:
            return 0.0
        return max(s.complexity_score for s in self.segments)

    @property
    def approved_count(self) -> int:
        return sum(1 for s in self.segments if s.approved)

    @property
    def shared_count(self) -> int:
        return sum(1 for s in self.segments if s.shared_to_count > 0)

    @property
    def tagged_count(self) -> int:
        return sum(1 for s in self.segments if s.tags)

    def get_dataframe(self) -> pd.DataFrame:
        """Get inventory as a DataFrame for Excel/CSV output."""
        if not self.segments:
            return pd.DataFrame(
                columns=[
                    "name",
                    "id",
                    "description",
                    "owner",
                    "approved",
                    "tags",
                    "complexity_score",
                    "container_type",
                    "functions_used",
                    "dimension_references",
                    "metric_references",
                    "segment_references",
                    "definition_summary",
                    "summary",
                    "created",
                    "modified",
                    "shared_to",
                    "definition_json",
                ],
            )

        # Sort by complexity score descending
        sorted_segments = sorted(self.segments, key=lambda s: s.complexity_score, reverse=True)
        df = pd.DataFrame([s.to_dict() for s in sorted_segments])
        # Add standardized 'summary' column as alias for cross-module consistency
        df["summary"] = df["definition_summary"]
        return df

    def get_summary(self) -> dict[str, Any]:
        """Get summary statistics for the inventory."""
        function_counts: dict[str, int] = {}
        tag_counts: dict[str, int] = {}
        container_counts: dict[str, int] = {}

        for segment in self.segments:
            for func in segment.functions_used:
                function_counts[func] = function_counts.get(func, 0) + 1
            for tag in segment.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1
            if segment.container_type:
                container_counts[segment.container_type] = container_counts.get(segment.container_type, 0) + 1

        return {
            "data_view_id": self.data_view_id,
            "data_view_name": self.data_view_name,
            "total_segments": self.total_segments,
            "governance": {
                "approved_count": sum(1 for s in self.segments if s.approved),
                "unapproved_count": sum(1 for s in self.segments if not s.approved),
                "shared_count": sum(1 for s in self.segments if s.shared_to_count > 0),
                "tagged_count": sum(1 for s in self.segments if s.tags),
            },
            "complexity": {
                "average": round(self.avg_complexity, 1),
                "max": round(self.max_complexity, 1),
                "high_complexity_count": sum(1 for s in self.segments if s.complexity_score >= 75),
                "elevated_complexity_count": sum(1 for s in self.segments if 50 <= s.complexity_score < 75),
            },
            "container_types": dict(sorted(container_counts.items(), key=lambda x: -x[1])) if container_counts else {},
            "function_usage": dict(sorted(function_counts.items(), key=lambda x: -x[1])),
            "tag_usage": dict(sorted(tag_counts.items(), key=lambda x: -x[1])) if tag_counts else {},
        }

    def to_json(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "summary": self.get_summary(),
            "segments": [
                s.to_full_dict() for s in sorted(self.segments, key=lambda s: s.complexity_score, reverse=True)
            ],
        }


# ==================== BUILDER CLASS ====================


class SegmentsInventoryBuilder:
    """
    Builds a segments inventory from CJA API.

    Usage:
        builder = SegmentsInventoryBuilder(logger)
        inventory = builder.build(cja, data_view_id, data_view_name)
    """

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)

    def build(
        self,
        cja: Any,
        data_view_id: str,
        data_view_name: str = "",
    ) -> SegmentsInventory:
        """
        Build a segments inventory from the CJA API.

        Args:
            cja: CJA API instance (cjapy.CJA)
            data_view_id: Data view ID to filter segments by
            data_view_name: Data view name for the inventory

        Returns:
            SegmentsInventory containing all segment summaries
        """
        inventory = SegmentsInventory(
            data_view_id=data_view_id,
            data_view_name=data_view_name,
        )

        try:
            # Get segments (filters) filtered by data view ID
            segments_df = cja.getFilters(dataIds=data_view_id, full=True)

            # Normalize API response (handles DataFrame, list, None)
            segments_list = normalize_api_response(
                segments_df,
                response_type="segments",
                logger=self.logger,
            )

            if segments_list is None:
                return inventory

            # Process each segment with tracking
            stats = BatchProcessingStats(logger=self.logger)
            for segment_data in segments_list:
                if not isinstance(segment_data, dict):
                    stats.record_skip("unexpected segment payload type", str(type(segment_data)))
                    continue
                summary = self._process_segment(segment_data, stats)
                if summary:
                    inventory.segments.append(summary)
                    stats.record_success()

            # Log processing summary
            stats.log_summary("segments")

            self.logger.info(f"Segments inventory built: {inventory.total_segments} segments")

        except Exception:  # Intentional: Orchestrator boundary; logs full traceback and re-raises for caller handling
            self.logger.exception(f"Error fetching segments for data view {data_view_id}")
            raise

        return inventory

    def _process_segment(
        self,
        segment_data: dict[str, Any],
        stats: BatchProcessingStats | None = None,
    ) -> SegmentSummary | None:
        """Process a single segment and return a summary.

        Extracts all available fields from the API response for comprehensive
        documentation.
        """
        # Validate required ID field (fail fast on missing critical data)
        segment_id = validate_required_id(segment_data, id_field="id", name_field="name", logger=self.logger)
        if not segment_id:
            if stats:
                stats.record_skip("missing ID", segment_data.get("name", "Unknown"))
            return None

        segment_name = self._coerce_display_text(segment_data.get("name", "Unknown"), fallback="Unknown")
        description = self._coerce_display_text(segment_data.get("description", ""), fallback="")

        # Extract owner info using shared utility
        owner, owner_id = extract_owner(segment_data.get("owner", {}))
        owner = self._coerce_display_text(owner, fallback="")
        owner_id = self._coerce_display_text(owner_id, fallback="")

        # Get definition
        definition = segment_data.get("definition", {})
        if not definition or not isinstance(definition, dict):
            self.logger.warning(f"Skipping segment '{segment_name}' ({segment_id}) - no valid definition")
            if stats:
                stats.record_skip("no valid definition", segment_id)
            return None

        # Parse the definition
        parsed = self._parse_definition(definition)

        # Extract governance fields
        approved = bool(segment_data.get("approved", False))
        favorite = bool(segment_data.get("favorite", False))

        # Extract tags using shared utility
        tags = extract_tags(segment_data.get("tags", []))

        # Extract timestamps
        created = self._coerce_display_text(
            segment_data.get("created", segment_data.get("createdDate", "")),
            fallback="",
        )
        modified = self._coerce_display_text(
            segment_data.get("modified", segment_data.get("modifiedDate", "")),
            fallback="",
        )

        # Extract sharing info
        shares_data = segment_data.get("shares", [])
        shares = shares_data if isinstance(shares_data, list) else []
        shared_to_count = len(shares)

        # Extract data view association
        data_view_id = self._coerce_display_text(segment_data.get("dataId", segment_data.get("rsid", "")), fallback="")
        site_title = self._coerce_display_text(segment_data.get("siteTitle", ""), fallback="")

        # Generate definition summary
        definition_summary = self._generate_definition_summary(definition, parsed)

        # Serialize definition to JSON string for full fidelity
        try:
            definition_json_str = json.dumps(definition, separators=(",", ":"))
        except TypeError, ValueError:
            definition_json_str = json.dumps(str(definition))

        return SegmentSummary(
            segment_id=segment_id,
            segment_name=segment_name,
            description=description,
            owner=owner,
            owner_id=owner_id,
            complexity_score=parsed["complexity_score"],
            functions_used=parsed["functions_display"],
            functions_used_internal=parsed["functions_internal"],
            predicate_count=parsed["predicate_count"],
            logic_operator_count=parsed["logic_operator_count"],
            nesting_depth=parsed["nesting_depth"],
            container_count=parsed["container_count"],
            dimension_references=parsed["dimension_references"],
            metric_references=parsed["metric_references"],
            other_segment_references=parsed["segment_references"],
            definition_summary=definition_summary,
            container_type=parsed["container_type"],
            approved=approved,
            favorite=favorite,
            tags=tags,
            created=created,
            modified=modified,
            shares=shares,
            shared_to_count=shared_to_count,
            data_view_id=data_view_id,
            site_title=site_title,
            definition_json=definition_json_str,
        )

    def _normalize_func_name(self, value: Any) -> str:
        """Normalize function names to comparable string keys."""
        return normalize_func_name(value)

    def _coerce_scalar_text(self, value: Any) -> str:
        """Convert scalar values to text while ignoring null/object payloads."""
        return coerce_scalar_text(value)

    def _coerce_display_text(self, value: Any, fallback: str = "") -> str:
        """Normalize text values for summaries/dataclass fields."""
        return coerce_display_text(value, fallback=fallback)

    def _normalize_reference_value(self, value: Any) -> str:
        """Normalize variable API reference payloads (string/dict/etc.) into a short ID."""
        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            for item in value:
                candidate = self._normalize_reference_value(item)
                if candidate:
                    return candidate
            return ""
        if isinstance(value, dict):
            for key in ("id", "name", "dimension", "metric", "segment", "value", "val"):
                if key in value:
                    candidate = self._normalize_reference_value(value.get(key))
                    if candidate:
                        return candidate
            return ""
        normalized = extract_short_name(value)
        if normalized.lower() in {"", "nan", "none", "null"}:
            return ""
        return normalized

    def _parse_definition(self, definition: dict[str, Any], depth: int = 0) -> dict[str, Any]:
        """
        Recursively parse a segment definition and extract all relevant data.

        Args:
            definition: The definition dict to parse
            depth: Current nesting depth

        Returns:
            Dictionary with parsed information
        """
        functions_internal: set[str] = set()
        dimension_refs: set[str] = set()
        metric_refs: set[str] = set()
        segment_refs: set[str] = set()

        total_predicates = 0
        total_logic_operators = 0
        max_nesting = depth
        total_containers = 0
        regex_count = 0
        container_type = ""

        def traverse(node: Any, current_depth: int) -> None:
            nonlocal total_predicates, total_logic_operators, max_nesting, total_containers, regex_count, container_type

            if not isinstance(node, dict):  # pragma: no cover — all callers guard with isinstance
                return

            max_nesting = max(max_nesting, current_depth)

            func = self._normalize_func_name(node.get("func", ""))
            if func:
                functions_internal.add(func)

                # Count predicates (comparison operations)
                if func in (
                    "eq",
                    "ne",
                    "gt",
                    "gte",
                    "lt",
                    "lte",
                    "streq",
                    "strne",
                    "contains",
                    "not-contains",
                    "starts-with",
                    "ends-with",
                    "matches",
                    "not-matches",
                    "exists",
                    "not-exists",
                    "streq-in",
                    "strne-in",
                    "within",
                    "after",
                    "before",
                ):
                    total_predicates += 1

                # Count regex patterns
                if func in ("matches", "not-matches"):
                    regex_count += 1

                # Count logic operators
                if func in ("and", "or", "not"):
                    total_logic_operators += 1

                # Count containers
                if func in ("container", "sequence", "sequence-prefix", "sequence-suffix", "exclude"):
                    total_containers += 1

            # Extract container type (context)
            context = node.get("context", "")
            if context and isinstance(context, str) and not container_type:
                container_type = context.lower()

            # Extract dimension references using shared utility
            dimension = node.get("dimension", node.get("dim", ""))
            if dimension:
                clean_name = self._normalize_reference_value(dimension)
                if clean_name:
                    dimension_refs.add(clean_name)

            # Extract metric references using shared utility
            metric = node.get("metric", "")
            if metric:
                clean_name = self._normalize_reference_value(metric)
                if clean_name:
                    metric_refs.add(clean_name)

            # Extract segment references
            seg_ref = node.get("segment", node.get("seg", ""))
            if seg_ref:
                clean_name = self._normalize_reference_value(seg_ref)
                if clean_name:
                    segment_refs.add(clean_name)

            # Check for 'pred' which contains a predicate or nested structure
            pred = node.get("pred", {})
            if isinstance(pred, dict) and pred:
                traverse(pred, current_depth + 1)

            # Check for 'preds' which contains multiple predicates (and/or)
            preds = node.get("preds", [])
            if isinstance(preds, list):
                for p in preds:
                    if isinstance(p, dict):
                        traverse(p, current_depth + 1)

            # Traverse container's inner content
            container_def = node.get("container", {})
            if isinstance(container_def, dict) and container_def:
                traverse(container_def, current_depth + 1)

            # Traverse exclude content
            exclude_def = node.get("exclude", {})
            if isinstance(exclude_def, dict) and exclude_def:
                traverse(exclude_def, current_depth + 1)

            # Handle sequence checkpoints
            checkpoints = node.get("checkpoints", [])
            if isinstance(checkpoints, list):
                for checkpoint in checkpoints:
                    if isinstance(checkpoint, dict):
                        traverse(checkpoint, current_depth + 1)

            # Handle val arrays (for streq-in, etc.)
            val = node.get("val", [])
            if isinstance(val, list) and val:
                total_predicates += len(val) - 1  # Each additional value adds complexity

        traverse(definition, depth)

        # Convert to display names
        functions_display = [
            SEGMENT_FUNCTION_DISPLAY_NAMES.get(f, f.replace("-", " ").title())
            for f in functions_internal
            if f not in ("number", "string")  # Don't show literal types
        ]

        # Compute complexity score
        complexity_score = self._compute_complexity_score(
            predicates=total_predicates,
            logic_operators=total_logic_operators,
            nesting=max_nesting,
            dimension_refs=len(dimension_refs),
            metric_refs=len(metric_refs),
            regex=regex_count,
        )

        return {
            "functions_internal": list(functions_internal),
            "functions_display": functions_display,
            "dimension_references": sorted(dimension_refs),
            "metric_references": sorted(metric_refs),
            "segment_references": sorted(segment_refs),
            "predicate_count": total_predicates,
            "logic_operator_count": total_logic_operators,
            "nesting_depth": max_nesting,
            "container_count": total_containers,
            "container_type": container_type,
            "complexity_score": complexity_score,
        }

    def _compute_complexity_score(
        self,
        predicates: int,
        logic_operators: int,
        nesting: int,
        dimension_refs: int,
        metric_refs: int,
        regex: int,
    ) -> float:
        """Compute a complexity score (0-100) for a segment."""
        # Normalize each factor to 0-1 range
        pred_score = min(1.0, predicates / COMPLEXITY_MAX_VALUES["predicates"])
        logic_score = min(1.0, logic_operators / COMPLEXITY_MAX_VALUES["logic_operators"])
        nesting_score = min(1.0, nesting / COMPLEXITY_MAX_VALUES["nesting"])
        dim_score = min(1.0, dimension_refs / COMPLEXITY_MAX_VALUES["dimension_refs"])
        met_score = min(1.0, metric_refs / COMPLEXITY_MAX_VALUES["metric_refs"])
        regex_score = min(1.0, regex / COMPLEXITY_MAX_VALUES["regex"])

        # Weighted sum
        weighted_score = (
            pred_score * COMPLEXITY_WEIGHTS["predicates"]
            + logic_score * COMPLEXITY_WEIGHTS["logic_operators"]
            + nesting_score * COMPLEXITY_WEIGHTS["nesting"]
            + dim_score * COMPLEXITY_WEIGHTS["dimension_refs"]
            + met_score * COMPLEXITY_WEIGHTS["metric_refs"]
            + regex_score * COMPLEXITY_WEIGHTS["regex"]
        )

        return round(weighted_score * 100, 1)

    def _generate_definition_summary(
        self,
        definition: dict[str, Any],
        parsed: dict[str, Any],
    ) -> str:
        """Generate a brief human-readable summary of what the segment defines."""
        container_type = parsed["container_type"]
        dimension_refs = parsed["dimension_references"]
        metric_refs = parsed["metric_references"]
        functions_internal = parsed["functions_internal"]
        predicate_count = parsed["predicate_count"]
        logic_operator_count = parsed["logic_operator_count"]

        # Try to build a natural language description
        context_word = container_type.title() if container_type else "Hit"
        if container_type == "hits":
            context_word = "Hit"
        elif container_type == "visits":
            context_word = "Visit"
        elif container_type == "visitors":
            context_word = "Person"

        # Try to get specific conditions from the definition
        condition_desc = self._describe_definition(definition, max_depth=3)
        if condition_desc:
            return f"{context_word} where {condition_desc}"

        # Fallback to descriptive summary
        if (
            "sequence" in functions_internal
            or "sequence-prefix" in functions_internal
            or "sequence-suffix" in functions_internal
        ):
            if dimension_refs:
                return f"{context_word} with sequential {dimension_refs[0]} conditions"
            return f"{context_word} with sequential conditions"

        if "exclude" in functions_internal:
            if dimension_refs:
                return f"{context_word} excluding {dimension_refs[0]} conditions"
            return f"{context_word} with exclusion logic"

        if dimension_refs and metric_refs:
            return f"{context_word} where {dimension_refs[0]} meets criteria with {metric_refs[0]}"

        if dimension_refs:
            if len(dimension_refs) == 1:
                return f"{context_word} where {dimension_refs[0]} meets criteria"
            if len(dimension_refs) <= 3:
                return f"{context_word} where {', '.join(dimension_refs)} meet criteria"
            return f"{context_word} with {len(dimension_refs)} dimension conditions"

        if metric_refs:
            if len(metric_refs) == 1:
                return f"{context_word} where {metric_refs[0]} meets criteria"
            return f"{context_word} with {len(metric_refs)} metric conditions"

        if predicate_count > 0:
            if logic_operator_count > 0:
                return f"{context_word} with {predicate_count} conditions ({logic_operator_count} combined)"
            return f"{context_word} with {predicate_count} conditions"

        return f"{context_word} segment"

    def _describe_definition(self, node: dict[str, Any], max_depth: int = 3) -> str:
        """Build a condition description string from the definition."""
        if not isinstance(node, dict) or max_depth <= 0:
            return ""

        func = node.get("func", "")
        func = self._normalize_func_name(func)
        context = node.get("context", "")

        # Handle container - go to inner content
        if func == "container" or context:
            pred = node.get("pred", {})
            if isinstance(pred, dict) and pred:
                return self._describe_definition(pred, max_depth)
            # Try container key
            container_def = node.get("container", {})
            if isinstance(container_def, dict) and container_def:
                return self._describe_definition(container_def, max_depth)

        # Handle logical operators
        if func == "and":
            preds = node.get("preds", [])
            if isinstance(preds, list) and preds:
                parts = []
                for p in preds[:3]:  # Limit to 3 for readability
                    desc = self._describe_definition(p, max_depth - 1)
                    if desc:
                        parts.append(desc)
                if parts:
                    suffix = f" AND +{len(preds) - 3} more" if len(preds) > 3 else ""
                    return " AND ".join(parts) + suffix

        if func == "or":
            preds = node.get("preds", [])
            if isinstance(preds, list) and preds:
                parts = []
                for p in preds[:3]:
                    desc = self._describe_definition(p, max_depth - 1)
                    if desc:
                        parts.append(desc)
                if parts:
                    suffix = f" OR +{len(preds) - 3} more" if len(preds) > 3 else ""
                    return " OR ".join(parts) + suffix

        if func == "not":
            pred = node.get("pred", {})
            inner = self._describe_definition(pred, max_depth - 1)
            if inner:
                return f"NOT ({inner})"

        # Handle comparison operators
        dimension = node.get("dimension", node.get("dim", ""))
        if dimension:
            dimension = self._normalize_reference_value(dimension)

        metric = node.get("metric", "")
        if metric:
            metric = self._normalize_reference_value(metric)

        val = node.get("val", "")
        # Handle list values
        if isinstance(val, list):
            if len(val) == 1:
                val = val[0]
            elif len(val) <= 3:
                val = ", ".join(str(v) for v in val)
            else:
                val = f"{val[0]}, +{len(val) - 1} more"

        field_name = dimension or metric or ""

        if func in ("eq", "streq"):
            if field_name and val:
                return f"{field_name} = '{val}'" if isinstance(val, str) else f"{field_name} = {val}"
        elif func in ("ne", "strne"):
            if field_name and val:
                return f"{field_name} != '{val}'" if isinstance(val, str) else f"{field_name} != {val}"
        elif func == "streq-in":
            if field_name and val:
                return f"{field_name} in ({val})"
        elif func == "contains":
            if field_name and val:
                return f"{field_name} contains '{val}'"
        elif func == "not-contains":
            if field_name and val:
                return f"{field_name} does not contain '{val}'"
        elif func == "starts-with":
            if field_name and val:
                return f"{field_name} starts with '{val}'"
        elif func == "ends-with":
            if field_name and val:
                return f"{field_name} ends with '{val}'"
        elif func == "matches":
            if field_name and val:
                val_str = str(val)
                short_pattern = val_str[:20] + "..." if len(val_str) > 20 else val_str
                return f"{field_name} matches /{short_pattern}/"
        elif func == "exists":
            if field_name:
                return f"{field_name} exists"
        elif func == "not-exists":
            if field_name:
                return f"{field_name} does not exist"
        elif func in ("gt", "gte", "lt", "lte"):
            op_map = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<="}
            if field_name and val is not None:
                return f"{field_name} {op_map[func]} {val}"

        # Handle sequence
        if func in ("sequence", "sequence-prefix", "sequence-suffix"):
            checkpoints = node.get("checkpoints", [])
            if isinstance(checkpoints, list) and checkpoints:
                return f"sequential pattern with {len(checkpoints)} steps"

        # Handle exclude
        if func == "exclude":
            container = node.get("container", {})
            inner = self._describe_definition(container, max_depth - 1)
            if inner:
                return f"excluding ({inner})"

        return ""


# ==================== MODULE EXPORTS ====================

__all__ = [
    "SEGMENT_FUNCTION_DISPLAY_NAMES",
    "SegmentSummary",
    "SegmentsInventory",
    "SegmentsInventoryBuilder",
    "__version__",
]
