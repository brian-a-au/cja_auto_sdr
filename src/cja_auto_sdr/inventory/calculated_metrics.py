"""
CJA Calculated Metrics Inventory

Generates a comprehensive inventory of calculated metrics from the CJA API.
Surfaces calculated metric formulas, complexity scores, governance metadata,
and all available API fields for complete SDR documentation.

Since calculated metrics are NOT included in standard SDR output (unlike derived
fields which appear in Metrics/Dimensions sheets), this inventory serves as the
primary and only source for calculated metric documentation.

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
CALC_METRIC_FUNCTION_DISPLAY_NAMES: dict[str, str] = {
    # Arithmetic operations
    "divide": "Division",
    "multiply": "Multiplication",
    "add": "Addition",
    "subtract": "Subtraction",
    "negate": "Negation",
    "abs": "Absolute Value",
    "pow": "Power",
    "sqrt": "Square Root",
    "ceil": "Ceiling",
    "floor": "Floor",
    "round": "Round",
    "log": "Logarithm",
    "log10": "Log Base 10",
    "exp": "Exponential",
    # References
    "metric": "Metric Reference",
    "segment": "Segment Filter",
    "calc-metric": "Calculated Metric",
    "number": "Static Number",
    # Aggregation functions
    "col-sum": "Column Sum",
    "col-max": "Column Max",
    "col-min": "Column Min",
    "col-mean": "Column Mean",
    "col-count": "Column Count",
    "row-sum": "Row Sum",
    "row-max": "Row Max",
    "row-min": "Row Min",
    "row-mean": "Row Mean",
    # Conditional
    "if": "Conditional (If)",
    "and": "Logical And",
    "or": "Logical Or",
    "not": "Logical Not",
    "eq": "Equals",
    "ne": "Not Equals",
    "gt": "Greater Than",
    "gte": "Greater Than or Equal",
    "lt": "Less Than",
    "lte": "Less Than or Equal",
    # Statistical
    "median": "Median",
    "percentile": "Percentile",
    "variance": "Variance",
    "standard-deviation": "Standard Deviation",
    "correlation": "Correlation",
    "regression": "Regression",
    # Time functions
    "time-comparison": "Time Comparison",
    "cumulative": "Cumulative",
    "rolling": "Rolling Window",
    # Miscellaneous
    "coalesce": "Coalesce",
    "static-row": "Static Row",
    "count-rows": "Count Rows",
    "distinct-count": "Distinct Count",
    "approximate-count-distinct": "Approx Distinct Count",
    "visualization-group": "Visualization Group",
}

# Complexity score weights for calculated metrics
COMPLEXITY_WEIGHTS = {
    "operators": 0.25,
    "metric_refs": 0.25,
    "nesting": 0.20,
    "functions": 0.15,
    "segments": 0.10,
    "conditionals": 0.05,
}

# Max values for complexity normalization
COMPLEXITY_MAX_VALUES = {
    "operators": 50,
    "metric_refs": 10,
    "nesting": 8,
    "functions": 15,
    "segments": 5,
    "conditionals": 5,
}


# ==================== DATA CLASSES ====================


@dataclass
class CalculatedMetricSummary:
    """Summary of a single calculated metric for inventory output.

    Since calculated metrics are not included in standard SDR output, this
    dataclass captures ALL available API fields for comprehensive documentation.
    """

    metric_id: str
    metric_name: str
    description: str
    owner: str

    # Complexity
    complexity_score: float

    # Functions
    functions_used: list[str]  # Human-readable function names
    functions_used_internal: list[str]  # Internal func values

    # Structure
    nesting_depth: int
    operator_count: int

    # References
    metric_references: list[str]  # Referenced metric IDs
    segment_references: list[str]  # Referenced segment IDs
    conditional_count: int

    # Formula summary
    formula_summary: str  # Brief description of what the metric calculates

    # Additional metadata
    polarity: str  # positive, negative, neutral
    metric_type: str  # decimal, percent, currency, time, integer
    precision: int  # Decimal precision

    # Governance fields (new)
    approved: bool = False  # Approval status
    favorite: bool = False  # User favorite status
    tags: list[str] = field(default_factory=list)  # Organizational tags

    # Timestamps (new)
    created: str = ""  # ISO 8601 creation timestamp
    modified: str = ""  # ISO 8601 last modified timestamp

    # Ownership details (new)
    owner_id: str = ""  # Owner's user ID

    # Sharing info (new)
    shares: list[dict[str, Any]] = field(default_factory=list)  # Share recipients
    shared_to_count: int = 0  # Number of users/groups shared with

    # Data view association (new)
    data_view_id: str = ""  # Associated data view ID
    site_title: str = ""  # Site/company title

    # Raw definition for full fidelity
    definition_json: str = ""  # Original definition JSON string

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for DataFrame/Excel/CSV output.

        Includes all fields relevant for tabular SDR documentation.
        """
        return {
            "name": self.metric_name,
            "id": self.metric_id,
            "description": self.description or "-",
            "owner": self.owner or "-",
            "approved": "Yes" if self.approved else "No",
            "tags": ", ".join(self.tags) if self.tags else "-",
            "complexity_score": self.complexity_score,
            "functions_used": ", ".join(self.functions_used) if self.functions_used else "-",
            "metric_references": ", ".join(self.metric_references) if self.metric_references else "-",
            "segment_references": ", ".join(self.segment_references) if self.segment_references else "-",
            "formula_summary": self.formula_summary or "-",
            "polarity": self.polarity.title() if self.polarity else "-",
            "format": self.metric_type or "-",
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
            "metric_id": self.metric_id,
            "metric_name": self.metric_name,
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
            # Formula analysis
            "complexity_score": self.complexity_score,
            "functions_used": self.functions_used,
            "functions_used_internal": self.functions_used_internal,
            "nesting_depth": self.nesting_depth,
            "operator_count": self.operator_count,
            "metric_references": self.metric_references,
            "segment_references": self.segment_references,
            "conditional_count": self.conditional_count,
            "formula_summary": self.formula_summary,
            # Format settings
            "polarity": self.polarity,
            "metric_type": self.metric_type,
            "precision": self.precision,
            # Raw definition
            "definition_json": self.definition_json,
        }


@dataclass
class CalculatedMetricsInventory:
    """Complete inventory of calculated metrics for a data view."""

    data_view_id: str
    data_view_name: str
    metrics: list[CalculatedMetricSummary] = field(default_factory=list)

    @property
    def total_calculated_metrics(self) -> int:
        return len(self.metrics)

    @property
    def avg_complexity(self) -> float:
        if not self.metrics:
            return 0.0
        return sum(m.complexity_score for m in self.metrics) / len(self.metrics)

    @property
    def max_complexity(self) -> float:
        if not self.metrics:
            return 0.0
        return max(m.complexity_score for m in self.metrics)

    @property
    def approved_count(self) -> int:
        return sum(1 for m in self.metrics if m.approved)

    @property
    def shared_count(self) -> int:
        return sum(1 for m in self.metrics if m.shared_to_count > 0)

    @property
    def tagged_count(self) -> int:
        return sum(1 for m in self.metrics if m.tags)

    def get_dataframe(self) -> pd.DataFrame:
        """Get inventory as a DataFrame for Excel/CSV output."""
        if not self.metrics:
            return pd.DataFrame(
                columns=[
                    "name",
                    "id",
                    "description",
                    "owner",
                    "approved",
                    "tags",
                    "complexity_score",
                    "functions_used",
                    "metric_references",
                    "segment_references",
                    "formula_summary",
                    "summary",
                    "polarity",
                    "format",
                    "created",
                    "modified",
                    "shared_to",
                    "definition_json",
                ],
            )

        # Sort by complexity score descending
        sorted_metrics = sorted(self.metrics, key=lambda m: m.complexity_score, reverse=True)
        df = pd.DataFrame([m.to_dict() for m in sorted_metrics])
        # Add standardized 'summary' column as alias for cross-module consistency
        df["summary"] = df["formula_summary"]
        return df

    def get_summary(self) -> dict[str, Any]:
        """Get summary statistics for the inventory."""
        function_counts: dict[str, int] = {}
        tag_counts: dict[str, int] = {}
        for metric in self.metrics:
            for func in metric.functions_used:
                function_counts[func] = function_counts.get(func, 0) + 1
            for tag in metric.tags:
                tag_counts[tag] = tag_counts.get(tag, 0) + 1

        return {
            "data_view_id": self.data_view_id,
            "data_view_name": self.data_view_name,
            "total_calculated_metrics": self.total_calculated_metrics,
            "governance": {
                "approved_count": sum(1 for m in self.metrics if m.approved),
                "unapproved_count": sum(1 for m in self.metrics if not m.approved),
                "shared_count": sum(1 for m in self.metrics if m.shared_to_count > 0),
                "tagged_count": sum(1 for m in self.metrics if m.tags),
            },
            "complexity": {
                "average": round(self.avg_complexity, 1),
                "max": round(self.max_complexity, 1),
                "high_complexity_count": sum(1 for m in self.metrics if m.complexity_score >= 75),
                "elevated_complexity_count": sum(1 for m in self.metrics if 50 <= m.complexity_score < 75),
            },
            "function_usage": dict(sorted(function_counts.items(), key=lambda x: -x[1])),
            "tag_usage": dict(sorted(tag_counts.items(), key=lambda x: -x[1])) if tag_counts else {},
        }

    def to_json(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "summary": self.get_summary(),
            "metrics": [m.to_full_dict() for m in sorted(self.metrics, key=lambda m: m.complexity_score, reverse=True)],
        }


# ==================== BUILDER CLASS ====================


class CalculatedMetricsInventoryBuilder:
    """
    Builds a calculated metrics inventory from CJA API.

    Usage:
        builder = CalculatedMetricsInventoryBuilder(logger)
        inventory = builder.build(cja, data_view_id, data_view_name)
    """

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)

    def build(
        self,
        cja: Any,
        data_view_id: str,
        data_view_name: str = "",
    ) -> CalculatedMetricsInventory:
        """
        Build a calculated metrics inventory from the CJA API.

        Args:
            cja: CJA API instance (cjapy.CJA)
            data_view_id: Data view ID to filter metrics by
            data_view_name: Data view name for the inventory

        Returns:
            CalculatedMetricsInventory containing all calculated metric summaries
        """
        inventory = CalculatedMetricsInventory(
            data_view_id=data_view_id,
            data_view_name=data_view_name,
        )

        try:
            # Get calculated metrics filtered by data view ID
            calc_metrics_df = cja.getCalculatedMetrics(dataIds=data_view_id, full=True)

            # Normalize API response (handles DataFrame, list, None)
            metrics_list = normalize_api_response(
                calc_metrics_df,
                response_type="calculated metrics",
                logger=self.logger,
            )

            if metrics_list is None:
                return inventory

            # Process each metric with tracking
            stats = BatchProcessingStats(logger=self.logger)
            for metric_data in metrics_list:
                if not isinstance(metric_data, dict):
                    stats.record_skip("unexpected metric payload type", str(type(metric_data)))
                    continue
                summary = self._process_metric(metric_data, stats)
                if summary:
                    inventory.metrics.append(summary)
                    stats.record_success()

            # Log processing summary
            stats.log_summary("calculated metrics")

            self.logger.info(f"Calculated metrics inventory built: {inventory.total_calculated_metrics} metrics")

        except Exception:  # Intentional: Orchestrator boundary; logs full traceback and re-raises for caller handling
            self.logger.exception(f"Error fetching calculated metrics for data view {data_view_id}")
            raise

        return inventory

    def _process_metric(
        self,
        metric_data: dict[str, Any],
        stats: BatchProcessingStats | None = None,
    ) -> CalculatedMetricSummary | None:
        """Process a single calculated metric and return a summary.

        Extracts all available fields from the API response for comprehensive
        documentation since calculated metrics are not in standard SDR output.
        """
        # Validate required ID field (fail fast on missing critical data)
        metric_id = validate_required_id(metric_data, id_field="id", name_field="name", logger=self.logger)
        if not metric_id:
            if stats:
                stats.record_skip("missing ID", metric_data.get("name", "Unknown"))
            return None

        metric_name = self._coerce_display_text(metric_data.get("name", "Unknown"), fallback="Unknown")
        description = self._coerce_display_text(metric_data.get("description", ""), fallback="")

        # Extract owner info using shared utility
        owner, owner_id = extract_owner(metric_data.get("owner", {}))
        owner = self._coerce_display_text(owner, fallback="")
        owner_id = self._coerce_display_text(owner_id, fallback="")

        # Get definition
        definition = metric_data.get("definition", {})
        if not definition or not isinstance(definition, dict):
            self.logger.warning(f"Skipping metric '{metric_name}' ({metric_id}) - no valid definition")
            if stats:
                stats.record_skip("no valid definition", metric_id)
            return None

        # Get the formula from the definition
        raw_formula = definition.get("formula")
        if raw_formula is None:
            self.logger.warning(f"Skipping metric '{metric_name}' ({metric_id}) - no formula in definition")
            if stats:
                stats.record_skip("no formula in definition", metric_id)
            return None

        if isinstance(raw_formula, str) and not raw_formula.strip():
            self.logger.warning(f"Skipping metric '{metric_name}' ({metric_id}) - no formula in definition")
            if stats:
                stats.record_skip("no formula in definition", metric_id)
            return None

        if isinstance(raw_formula, (dict, list)) and len(raw_formula) == 0:
            self.logger.warning(f"Skipping metric '{metric_name}' ({metric_id}) - no formula in definition")
            if stats:
                stats.record_skip("no formula in definition", metric_id)
            return None

        formula = self._normalize_formula_node(raw_formula)
        if formula is None:
            self.logger.warning(f"Skipping metric '{metric_name}' ({metric_id}) - unsupported formula format")
            if stats:
                stats.record_skip("unsupported formula format", metric_id)
            return None

        # Parse the formula
        parsed = self._parse_formula(formula)

        # Extract format metadata
        polarity = metric_data.get("polarity", "positive")
        metric_type = metric_data.get("type", "decimal")
        precision = metric_data.get("precision", 0)

        # Extract governance fields
        approved = bool(metric_data.get("approved", False))
        favorite = bool(metric_data.get("favorite", False))

        # Extract tags using shared utility
        tags = extract_tags(metric_data.get("tags", []))

        # Extract timestamps
        created = self._coerce_display_text(metric_data.get("created", metric_data.get("createdDate", "")), fallback="")
        modified = self._coerce_display_text(
            metric_data.get("modified", metric_data.get("modifiedDate", "")),
            fallback="",
        )

        # Extract sharing info
        shares_data = metric_data.get("shares", [])
        shares = shares_data if isinstance(shares_data, list) else []
        shared_to_count = len(shares)

        # Extract data view association
        data_view_id = self._coerce_display_text(metric_data.get("dataId", metric_data.get("rsid", "")), fallback="")
        site_title = self._coerce_display_text(metric_data.get("siteTitle", ""), fallback="")

        # Generate formula summary
        formula_summary = self._generate_formula_summary(formula, parsed)

        # Serialize definition to JSON string for full fidelity
        try:
            definition_json_str = json.dumps(definition, separators=(",", ":"))
        except TypeError, ValueError:
            definition_json_str = json.dumps(str(definition))

        return CalculatedMetricSummary(
            metric_id=metric_id,
            metric_name=metric_name,
            description=description,
            owner=owner,
            owner_id=owner_id,
            complexity_score=parsed["complexity_score"],
            functions_used=parsed["functions_display"],
            functions_used_internal=parsed["functions_internal"],
            nesting_depth=parsed["nesting_depth"],
            operator_count=parsed["operator_count"],
            metric_references=parsed["metric_references"],
            segment_references=parsed["segment_references"],
            conditional_count=parsed["conditional_count"],
            formula_summary=formula_summary,
            polarity=polarity,
            metric_type=metric_type,
            precision=precision,
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
        """Normalize IDs and reference values from mixed payload shapes."""
        if value is None:
            return ""
        if isinstance(value, (list, tuple)):
            for item in value:
                candidate = self._normalize_reference_value(item)
                if candidate:
                    return candidate
            return ""
        if isinstance(value, dict):
            for key in ("segment_id", "id", "name", "metric", "value", "val"):
                if key in value:
                    candidate = self._normalize_reference_value(value.get(key))
                    if candidate:
                        return candidate
            return ""
        normalized = extract_short_name(value)
        if normalized.lower() in {"", "nan", "none", "null"}:
            return ""
        return normalized

    def _parse_formula(self, formula: Any, depth: int = 0) -> dict[str, Any]:
        """
        Recursively parse a formula and extract all relevant data.

        Args:
            formula: The formula dict to parse
            depth: Current nesting depth

        Returns:
            Dictionary with parsed information
        """
        functions_internal: set[str] = set()
        metric_refs: set[str] = set()
        segment_refs: set[str] = set()

        total_operators = 0
        max_nesting = depth
        total_conditionals = 0

        def traverse(node: Any, current_depth: int) -> None:
            nonlocal total_operators, max_nesting, total_conditionals

            if not isinstance(node, dict):  # pragma: no cover — all callers guard with isinstance
                return

            max_nesting = max(max_nesting, current_depth)

            func = self._normalize_func_name(node.get("func", ""))
            if func:
                functions_internal.add(func)

                # Count operators
                if func in (
                    "divide",
                    "multiply",
                    "add",
                    "subtract",
                    "negate",
                    "pow",
                    "sqrt",
                    "abs",
                    "ceil",
                    "floor",
                    "round",
                    "log",
                    "log10",
                    "exp",
                ):
                    total_operators += 1

                # Count conditionals
                if func in ("if", "and", "or", "not", "eq", "ne", "gt", "gte", "lt", "lte"):
                    total_conditionals += 1

                # Extract metric references
                if func == "metric":
                    clean_name = self._normalize_reference_value(node.get("name", ""))
                    if clean_name:
                        metric_refs.add(clean_name)

                # Extract segment references
                if func == "segment":
                    clean_segment = self._normalize_reference_value(node.get("segment_id", node.get("id", "")))
                    if clean_segment:
                        segment_refs.add(clean_segment)

            # Traverse child nodes
            for key in [
                "col1",
                "col2",
                "col",
                "metric",
                "val",
                "formula",
                "then",
                "else",
                "left",
                "right",
                "condition",
                "value",
                "operand",
                "dividend",
                "divisor",
            ]:
                if key in node and isinstance(node[key], dict):
                    traverse(node[key], current_depth + 1)

            # Handle lists of operands
            for key in ["operands", "values", "metrics", "columns"]:
                if key in node and isinstance(node[key], list):
                    for item in node[key]:
                        if isinstance(item, dict):
                            traverse(item, current_depth + 1)

        traverse(formula, depth)

        # Convert to display names
        functions_display = [
            CALC_METRIC_FUNCTION_DISPLAY_NAMES.get(f, f.replace("-", " ").title())
            for f in functions_internal
            if f != "number"  # Don't show static numbers
        ]

        # Compute complexity score
        complexity_score = self._compute_complexity_score(
            operators=total_operators,
            metric_refs=len(metric_refs),
            nesting=max_nesting,
            functions=len(functions_internal),
            segments=len(segment_refs),
            conditionals=total_conditionals,
        )

        return {
            "functions_internal": list(functions_internal),
            "functions_display": functions_display,
            "metric_references": sorted(metric_refs),
            "segment_references": sorted(segment_refs),
            "operator_count": total_operators,
            "nesting_depth": max_nesting,
            "conditional_count": total_conditionals,
            "complexity_score": complexity_score,
        }

    def _compute_complexity_score(
        self,
        operators: int,
        metric_refs: int,
        nesting: int,
        functions: int,
        segments: int,
        conditionals: int,
    ) -> float:
        """Compute a complexity score (0-100) for a calculated metric."""
        # Normalize each factor to 0-1 range
        op_score = min(1.0, operators / COMPLEXITY_MAX_VALUES["operators"])
        ref_score = min(1.0, metric_refs / COMPLEXITY_MAX_VALUES["metric_refs"])
        nesting_score = min(1.0, nesting / COMPLEXITY_MAX_VALUES["nesting"])
        func_score = min(1.0, functions / COMPLEXITY_MAX_VALUES["functions"])
        seg_score = min(1.0, segments / COMPLEXITY_MAX_VALUES["segments"])
        cond_score = min(1.0, conditionals / COMPLEXITY_MAX_VALUES["conditionals"])

        # Weighted sum
        weighted_score = (
            op_score * COMPLEXITY_WEIGHTS["operators"]
            + ref_score * COMPLEXITY_WEIGHTS["metric_refs"]
            + nesting_score * COMPLEXITY_WEIGHTS["nesting"]
            + func_score * COMPLEXITY_WEIGHTS["functions"]
            + seg_score * COMPLEXITY_WEIGHTS["segments"]
            + cond_score * COMPLEXITY_WEIGHTS["conditionals"]
        )

        return round(weighted_score * 100, 1)

    def _generate_formula_summary(
        self,
        formula: Any,
        parsed: dict[str, Any],
    ) -> str:
        """Generate a brief human-readable summary of what the calculated metric does."""
        normalized_formula = self._normalize_formula_node(formula)
        if not normalized_formula:
            if isinstance(formula, (int, float)) and not isinstance(formula, bool):
                return str(formula)
            if isinstance(formula, str) and formula.strip():
                return formula.strip()
            return "Custom calculated metric"

        # Unwrap visualization-group wrapper if present
        actual_formula = normalized_formula
        func = actual_formula.get("func", "")
        if func == "visualization-group":
            # Try to find the actual formula inside
            for key in ["formula", "col", "metric", "col1"]:
                if key not in actual_formula:
                    continue
                nested_formula = self._normalize_formula_node(actual_formula[key])
                if nested_formula is not None:
                    actual_formula = nested_formula
                    break
            else:
                # Check formulas array
                formulas = actual_formula.get("formulas", [])
                if formulas and isinstance(formulas, list):
                    nested_formula = self._normalize_formula_node(formulas)
                    if nested_formula is not None:
                        actual_formula = nested_formula

        # Try to build a formula expression first
        formula_expr = self._build_formula_expression(actual_formula, max_depth=4)
        if formula_expr and len(formula_expr) <= 80:
            return formula_expr

        # Fall back to descriptive summary for complex formulas
        func = actual_formula.get("func", "")
        functions_internal = parsed["functions_internal"]
        metric_refs = parsed["metric_references"]
        segment_refs = parsed["segment_references"]

        # Try to generate a meaningful description based on the primary operation
        if func == "divide":
            col1 = actual_formula.get("col1", {})
            col2 = actual_formula.get("col2", {})
            numerator = self._get_reference_name(col1)
            denominator = self._get_reference_name(col2)
            if numerator and denominator:
                return f"{numerator} / {denominator}"
            return "Ratio calculation"

        if func == "multiply":
            col1 = actual_formula.get("col1", {})
            col2 = actual_formula.get("col2", {})
            left = self._get_reference_name(col1)
            right = self._get_reference_name(col2)
            if left and right:
                return f"{left} x {right}"
            return "Multiplication of metrics"

        if func == "add":
            operands = self._get_add_operands(actual_formula)
            if operands:
                if len(operands) <= 3:
                    return " + ".join(operands)
                return f"{' + '.join(operands[:2])} + {len(operands) - 2} more"
            return "Sum of metrics"

        if func == "subtract":
            col1 = actual_formula.get("col1", {})
            col2 = actual_formula.get("col2", {})
            left = self._get_reference_name(col1)
            right = self._get_reference_name(col2)
            if left and right:
                return f"{left} - {right}"
            return "Difference calculation"

        if func == "if":
            condition_desc = self._describe_condition(actual_formula)
            if condition_desc:
                return f"If {condition_desc}"
            return "Conditional calculation"

        if func == "segment":
            inner_metric = self._get_reference_name(actual_formula.get("metric", {}))
            segment_id = actual_formula.get("segment_id", actual_formula.get("id", ""))
            segment_name = self._get_short_id(segment_id)
            if inner_metric and segment_name:
                return f"{inner_metric} filtered by {segment_name}"
            if inner_metric:
                return f"{inner_metric} (filtered)"
            return "Segmented metric"

        if func == "metric":
            clean_name = self._normalize_reference_value(actual_formula.get("name", ""))
            if clean_name:
                return f"= {clean_name}"
            return "Metric reference"

        if func in ("col-sum", "col-max", "col-min", "col-mean", "col-count"):
            op_name = func.replace("col-", "").upper()
            inner = self._get_reference_name(actual_formula.get("col", actual_formula.get("metric", {})))
            if inner:
                return f"{op_name}({inner})"
            return f"Column {op_name.title()} aggregation"

        if func in ("row-sum", "row-max", "row-min", "row-mean"):
            op_name = func.replace("row-", "").upper()
            return f"Row {op_name.title()} aggregation"

        if func == "cumulative":
            inner = self._get_reference_name(actual_formula.get("col", actual_formula.get("metric", {})))
            if inner:
                return f"Cumulative({inner})"
            return "Cumulative calculation"

        if func == "rolling":
            inner = self._get_reference_name(actual_formula.get("col", actual_formula.get("metric", {})))
            window = actual_formula.get("window", "")
            if inner:
                if window:
                    return f"Rolling {window}({inner})"
                return f"Rolling({inner})"
            return "Rolling window calculation"

        if func in ("median", "percentile", "variance", "standard-deviation"):
            inner = self._get_reference_name(actual_formula.get("col", actual_formula.get("metric", {})))
            op_name = func.replace("-", " ").title()
            if inner:
                if func == "percentile":
                    pct = actual_formula.get("percentile", actual_formula.get("val", ""))
                    if pct:
                        return f"P{pct}({inner})"
                return f"{op_name}({inner})"
            return f"{op_name} calculation"

        if func == "abs":
            inner = self._get_reference_name(actual_formula.get("col", actual_formula.get("col1", {})))
            if inner:
                return f"ABS({inner})"
            return "Absolute value"

        if func in ("sqrt", "log", "log10", "exp", "ceil", "floor", "round"):
            inner = self._get_reference_name(actual_formula.get("col", actual_formula.get("col1", {})))
            op_name = func.upper()
            if inner:
                return f"{op_name}({inner})"
            return f"{op_name} function"

        if func == "pow":
            base = self._get_reference_name(actual_formula.get("col1", {}))
            exp = self._get_reference_name(actual_formula.get("col2", {}))
            if base and exp:
                return f"{base}^{exp}"
            return "Power calculation"

        # Generic summary based on functions used
        if "segment" in functions_internal and metric_refs:
            if segment_refs:
                return f"{metric_refs[0]} filtered by segment"
            return f"Filtered {metric_refs[0]}"

        if "divide" in functions_internal and len(metric_refs) >= 2:
            return f"Ratio: {metric_refs[0]} / {metric_refs[1]}"

        if "if" in functions_internal:
            if metric_refs:
                return f"Conditional: based on {metric_refs[0]}"
            return "Conditional calculation"

        if metric_refs:
            if len(metric_refs) == 1:
                return f"Based on {metric_refs[0]}"
            if len(metric_refs) == 2:
                return f"Combines {metric_refs[0]} and {metric_refs[1]}"
            return f"Combines {len(metric_refs)} metrics: {', '.join(metric_refs[:2])}, ..."

        return "Custom calculated metric"

    def _build_formula_expression(self, node: Any, max_depth: int = 4) -> str:
        """Build a formula expression string like 'A / B' or 'SUM(A, B)'."""
        if not isinstance(node, dict) or max_depth <= 0:
            return ""

        func = node.get("func", "")

        if func == "metric":
            return self._normalize_reference_value(node.get("name", ""))

        if func == "number":
            val = node.get("val", "")
            return str(val) if val is not None else ""

        if func == "literal":
            val = node.get("val", "")
            if isinstance(val, str):
                return val
            return str(val) if val is not None else ""

        if func == "divide":
            left = self._build_formula_expression(node.get("col1", {}), max_depth - 1)
            right = self._build_formula_expression(node.get("col2", {}), max_depth - 1)
            if left and right:
                # Add parens if operands are complex
                if " " in left and not left.startswith("("):
                    left = f"({left})"
                if " " in right and not right.startswith("("):
                    right = f"({right})"
                return f"{left} / {right}"

        if func == "multiply":
            left = self._build_formula_expression(node.get("col1", {}), max_depth - 1)
            right = self._build_formula_expression(node.get("col2", {}), max_depth - 1)
            if left and right:
                return f"{left} x {right}"

        if func == "add":
            operands = []
            for key in ["col1", "col2"]:
                if key in node:
                    expr = self._build_formula_expression(node[key], max_depth - 1)
                    if expr:
                        operands.append(expr)
            if "operands" in node and isinstance(node["operands"], list):
                for op in node["operands"]:
                    expr = self._build_formula_expression(op, max_depth - 1)
                    if expr:
                        operands.append(expr)
            if operands:
                return " + ".join(operands)

        if func == "subtract":
            left = self._build_formula_expression(node.get("col1", {}), max_depth - 1)
            right = self._build_formula_expression(node.get("col2", {}), max_depth - 1)
            if left and right:
                return f"{left} - {right}"

        if func == "segment":
            inner = self._build_formula_expression(node.get("metric", {}), max_depth - 1)
            segment_id = node.get("segment_id", node.get("id", ""))
            segment_name = self._get_short_id(segment_id)
            if inner and segment_name:
                return f"{inner}[{segment_name}]"
            if inner:
                return f"{inner}[filtered]"

        if func in ("col-sum", "col-max", "col-min", "col-mean", "col-count"):
            inner = self._build_formula_expression(node.get("col", node.get("metric", {})), max_depth - 1)
            op_name = func.replace("col-", "").upper()
            if inner:
                return f"{op_name}({inner})"

        if func == "if":
            then_val = self._build_formula_expression(node.get("then", {}), max_depth - 1)
            else_val = self._build_formula_expression(node.get("else", {}), max_depth - 1)
            if then_val and else_val:
                return f"IF(..., {then_val}, {else_val})"
            if then_val:
                return f"IF(..., {then_val})"

        if func in ("abs", "sqrt", "log", "log10", "exp", "ceil", "floor", "round", "negate"):
            inner = self._build_formula_expression(node.get("col", node.get("col1", {})), max_depth - 1)
            op_name = func.upper()
            if inner:
                return f"{op_name}({inner})"

        if func == "cumulative":
            inner = self._build_formula_expression(node.get("col", node.get("metric", {})), max_depth - 1)
            if inner:
                return f"CUM({inner})"

        # Handle visualization-group as a transparent wrapper
        if func == "visualization-group":
            # Try to get the inner formula from various possible keys
            for key in ["formula", "col", "metric", "col1"]:
                if key in node:
                    inner = self._build_formula_expression(node[key], max_depth)
                    if inner:
                        return inner
            # Check for formulas array
            formulas = node.get("formulas", [])
            if formulas and isinstance(formulas, list) and len(formulas) > 0:
                inner = self._build_formula_expression(formulas[0], max_depth)
                if inner:
                    return inner

        # Handle static-row / count-rows
        if func in ("static-row", "count-rows", "row-count"):
            return "COUNT_ROWS()"

        # Handle distinct count
        if func in ("distinct-count", "approximate-count-distinct"):
            inner = self._build_formula_expression(node.get("col", node.get("metric", {})), max_depth - 1)
            if inner:
                return f"DISTINCT({inner})"
            return "DISTINCT_COUNT()"

        return ""

    def _get_add_operands(self, formula: Any) -> list[str]:
        """Extract all operands from an add operation."""
        if not isinstance(formula, dict):
            return []

        operands = []
        for key in ["col1", "col2"]:
            if key in formula:
                name = self._get_reference_name(formula[key])
                if name:
                    operands.append(name)
        if "operands" in formula and isinstance(formula["operands"], list):
            for op in formula["operands"]:
                name = self._get_reference_name(op)
                if name:
                    operands.append(name)
        return operands

    def _describe_condition(self, formula: Any) -> str:
        """Generate a brief description of an if condition."""
        if not isinstance(formula, dict):
            return ""

        condition = formula.get("condition", formula.get("cond", {}))
        if not isinstance(condition, dict):
            return ""

        func = condition.get("func", "")

        # Helper to get left/right operands - handles both col1/col2 and left/right formats
        def get_left():
            return self._get_reference_name(condition.get("col1", condition.get("left", {})))

        def get_right():
            return self._get_reference_name(condition.get("col2", condition.get("right", {})))

        if func == "gt":
            left, right = get_left(), get_right()
            if left and right:
                return f"{left} > {right}"
        elif func == "gte":
            left, right = get_left(), get_right()
            if left and right:
                return f"{left} >= {right}"
        elif func == "lt":
            left, right = get_left(), get_right()
            if left and right:
                return f"{left} < {right}"
        elif func == "lte":
            left, right = get_left(), get_right()
            if left and right:
                return f"{left} <= {right}"
        elif func == "eq":
            left, right = get_left(), get_right()
            if left and right:
                return f"{left} = {right}"
        elif func == "ne":
            left, right = get_left(), get_right()
            if left and right:
                return f"{left} ≠ {right}"

        return ""

    def _get_short_id(self, full_id: Any) -> str:
        """Get a shortened version of an ID for display."""
        normalized_id = self._normalize_reference_value(full_id)
        if not normalized_id:
            return ""
        # Handle IDs like "s300000000_1234567890abcdef" -> show last part
        if "_" in normalized_id:
            parts = normalized_id.split("_")
            if len(parts[-1]) > 8:
                return parts[-1][:8] + "..."
            return parts[-1]
        if len(normalized_id) > 12:
            return normalized_id[:12] + "..."
        return normalized_id

    def _get_reference_name(self, node: dict[str, Any]) -> str:
        """Extract a human-readable name from a formula node."""
        if not isinstance(node, dict):
            return ""

        func = node.get("func", "")

        if func == "metric":
            return self._normalize_reference_value(node.get("name", ""))

        if func == "number":
            val = node.get("val", "")
            return str(val) if val is not None else ""

        if func == "literal":
            val = node.get("val", "")
            return str(val) if val is not None else ""

        if func == "segment":
            inner = node.get("metric", {})
            return self._get_reference_name(inner)

        # For aggregations, try to get the inner metric name
        if func in ("col-sum", "col-max", "col-min", "col-mean", "col-count", "cumulative", "rolling"):
            inner = node.get("col", node.get("metric", {}))
            inner_name = self._get_reference_name(inner)
            if inner_name:
                op = func.replace("col-", "").upper() if func.startswith("col-") else func.upper()[:3]
                return f"{op}({inner_name})"

        return ""

    def _normalize_formula_node(self, node: Any) -> dict[str, Any] | None:
        """Normalize formula payloads to a dict node for downstream parsing."""
        if isinstance(node, dict):
            return node

        if isinstance(node, list):
            for item in node:
                normalized = self._normalize_formula_node(item)
                if normalized is not None:
                    return normalized
            return None

        if isinstance(node, bool):
            return {"func": "literal", "val": node}

        if isinstance(node, (int, float)):
            return {"func": "number", "val": node}

        if isinstance(node, str):
            value = node.strip()
            if not value:
                return None
            if "/" in value:
                return {"func": "metric", "name": value}
            return {"func": "literal", "val": value}

        return None


# ==================== MODULE EXPORTS ====================

__all__ = [
    "CALC_METRIC_FUNCTION_DISPLAY_NAMES",
    "CalculatedMetricSummary",
    "CalculatedMetricsInventory",
    "CalculatedMetricsInventoryBuilder",
    "__version__",
]
