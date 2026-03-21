"""
CJA Derived Field Inventory

Generates a summary inventory of derived fields within a CJA Data View.
Surfaces derived field logic, complexity scores, and metadata for efficient
SDR documentation reviews.

Supported modes:
- SDR output integration (Excel/JSON/CSV/HTML/Markdown)

Note: This inventory is for SDR generation only. Derived fields also appear
in standard Metrics/Dimensions SDR sheets and API outputs, so derived field
changes are automatically captured in the standard Metrics/Dimensions diff.
The inventory provides additional logic analysis (complexity scores, functions
used, branch counts, etc.) that supplements standard component metadata.

Version: 1.0.0
"""

from __future__ import annotations

import json
import logging
import math
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from cja_auto_sdr.inventory.utils import (
    BatchProcessingStats,
    coerce_display_text,
    coerce_scalar_text,
    extract_short_name,
    normalize_func_name,
    validate_required_id,
)

# ==================== VERSION ====================

__version__ = "1.0.0"

# ==================== CONSTANTS ====================

# Mapping of internal function names to human-readable display names
FUNCTION_DISPLAY_NAMES: dict[str, str] = {
    "raw-field": "Field Reference",
    "match": "Case When",
    "classify": "Lookup/Classify",
    "deduplicate": "Deduplicate",
    "profile": "Profile Field",
    "timezone-shift": "Timezone Shift",
    "datetime-bucket": "Date Bucket",
    "datetime-slice": "Date Slice",
    "datetime-subtract": "Date Math",
    "iso-date": "ISO Date",
    "field-def-reference": "Component Reference",
    "divide": "Math (Division)",
    "multiply": "Math (Multiplication)",
    "add": "Math (Addition)",
    "subtract": "Math (Subtraction)",
    "do-not-use-lift": "Lift (Internal)",
    "lowercase": "Lowercase",
    "uppercase": "Uppercase",
    "trim": "Trim",
    "split": "Split",
    "concatenate": "Concatenate",
    "url-parse": "URL Parse",
    "regex-replace": "Regex Replace",
    "next": "Next Value",
    "previous": "Previous Value",
    "summarize": "Summarize",
    "merge": "Merge Fields",
    "typecast": "Typecast",
    "lookup": "Lookup",
    "find-replace": "Find & Replace",
    "depth": "Depth",
}

# Complexity score weights
COMPLEXITY_WEIGHTS = {
    "operators": 0.30,
    "branches": 0.25,
    "nesting": 0.20,
    "functions": 0.10,
    "schema_fields": 0.10,
    "regex": 0.05,
}

# Max values for complexity normalization
COMPLEXITY_MAX_VALUES = {
    "operators": 200,
    "branches": 50,
    "nesting": 5,
    "functions": 20,
    "schema_fields": 10,
    "regex": 5,
}


# ==================== DATA CLASSES ====================


@dataclass
class DerivedFieldSummary:
    """Summary of a single derived field for inventory output."""

    component_id: str
    component_name: str
    component_type: str  # 'Metric' or 'Dimension'

    # Complexity
    complexity_score: float

    # Functions
    functions_used: list[str]  # Human-readable function names
    functions_used_internal: list[str]  # Internal func values

    # Structure
    branch_count: int
    nesting_depth: int
    operator_count: int

    # Field references
    schema_field_count: int
    schema_fields: list[str]  # Field IDs referenced
    lookup_references: list[str]
    component_references: list[str]

    # Metadata from definition
    rule_names: list[str]  # #rule_name values from definition
    rule_descriptions: list[str]  # #rule_description values

    # Logic summary
    logic_summary: str  # Brief description of what the field does

    # Output type
    inferred_output_type: str  # 'numeric', 'string', 'boolean', 'unknown'

    # Metadata from data view component (may have limited availability)
    description: str = ""

    # Raw definition for full fidelity
    definition_json: str = ""  # Original fieldDefinition JSON string

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for DataFrame/JSON output."""
        return {
            "name": self.component_name,
            "type": self.component_type,
            "id": self.component_id,
            "description": self.description or "-",
            "complexity_score": self.complexity_score,
            "functions_used": ", ".join(self.functions_used) if self.functions_used else "-",
            "branch_count": self.branch_count,  # Keep as number (0 is valid)
            "schema_fields": self.schema_field_count,
            "schema_field_list": ", ".join(self.schema_fields[:5]) + ("..." if len(self.schema_fields) > 5 else "")
            if self.schema_fields
            else "-",
            "lookup_references": ", ".join(self.lookup_references) if self.lookup_references else "-",
            "rule_names": ", ".join(self.rule_names) if self.rule_names else "-",
            "logic_summary": self.logic_summary or "-",
            "output_type": self.inferred_output_type.title() if self.inferred_output_type else "-",
            "definition_json": self.definition_json,  # Keep empty string for raw JSON
        }

    def to_full_dict(self) -> dict[str, Any]:
        """Convert to full dictionary for JSON output with all details."""
        return {
            "component_id": self.component_id,
            "component_name": self.component_name,
            "component_type": self.component_type,
            "description": self.description,
            "complexity_score": self.complexity_score,
            "functions_used": self.functions_used,
            "functions_used_internal": self.functions_used_internal,
            "branch_count": self.branch_count,
            "nesting_depth": self.nesting_depth,
            "operator_count": self.operator_count,
            "schema_field_count": self.schema_field_count,
            "schema_fields": self.schema_fields,
            "lookup_references": self.lookup_references,
            "component_references": self.component_references,
            "rule_names": self.rule_names,
            "rule_descriptions": self.rule_descriptions,
            "logic_summary": self.logic_summary,
            "inferred_output_type": self.inferred_output_type,
            "definition_json": self.definition_json,
        }


@dataclass
class DerivedFieldInventory:
    """Complete inventory of derived fields for a data view."""

    data_view_id: str
    data_view_name: str
    fields: list[DerivedFieldSummary] = field(default_factory=list)

    @property
    def total_derived_fields(self) -> int:
        return len(self.fields)

    @property
    def metrics_count(self) -> int:
        return sum(1 for f in self.fields if f.component_type == "Metric")

    @property
    def dimensions_count(self) -> int:
        return sum(1 for f in self.fields if f.component_type == "Dimension")

    @property
    def avg_complexity(self) -> float:
        if not self.fields:
            return 0.0
        return sum(f.complexity_score for f in self.fields) / len(self.fields)

    @property
    def max_complexity(self) -> float:
        if not self.fields:
            return 0.0
        return max(f.complexity_score for f in self.fields)

    def get_dataframe(self) -> pd.DataFrame:
        """Get inventory as a DataFrame for Excel/CSV output."""
        if not self.fields:
            return pd.DataFrame(
                columns=[
                    "name",
                    "type",
                    "id",
                    "description",
                    "complexity_score",
                    "functions_used",
                    "branch_count",
                    "schema_fields",
                    "schema_field_list",
                    "lookup_references",
                    "rule_names",
                    "logic_summary",
                    "summary",
                    "output_type",
                    "definition_json",
                ],
            )

        # Sort by complexity score descending
        sorted_fields = sorted(self.fields, key=lambda f: f.complexity_score, reverse=True)
        df = pd.DataFrame([f.to_dict() for f in sorted_fields])
        # Add standardized 'summary' column as alias for cross-module consistency
        df["summary"] = df["logic_summary"]
        return df

    def get_summary(self) -> dict[str, Any]:
        """Get summary statistics for the inventory."""
        function_counts: dict[str, int] = {}
        for fld in self.fields:
            for func in fld.functions_used:
                function_counts[func] = function_counts.get(func, 0) + 1

        return {
            "data_view_id": self.data_view_id,
            "data_view_name": self.data_view_name,
            "total_derived_fields": self.total_derived_fields,
            "metrics_count": self.metrics_count,
            "dimensions_count": self.dimensions_count,
            "complexity": {
                "average": round(self.avg_complexity, 1),
                "max": round(self.max_complexity, 1),
                "high_complexity_count": sum(1 for f in self.fields if f.complexity_score >= 75),
                "elevated_complexity_count": sum(1 for f in self.fields if 50 <= f.complexity_score < 75),
            },
            "function_usage": dict(sorted(function_counts.items(), key=lambda x: -x[1])),
        }

    def to_json(self) -> dict[str, Any]:
        """Convert to JSON-serializable dictionary."""
        return {
            "summary": self.get_summary(),
            "fields": [f.to_full_dict() for f in sorted(self.fields, key=lambda f: f.complexity_score, reverse=True)],
        }


# ==================== PARSER CLASS ====================


class DerivedFieldInventoryBuilder:
    """
    Builds a derived field inventory from CJA data view components.

    Usage:
        builder = DerivedFieldInventoryBuilder(logger)
        inventory = builder.build(metrics_df, dimensions_df, data_view_id, data_view_name)
    """

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)

    def build(
        self,
        metrics_df: pd.DataFrame,
        dimensions_df: pd.DataFrame,
        data_view_id: str = "",
        data_view_name: str = "",
    ) -> DerivedFieldInventory:
        """
        Build a derived field inventory from metrics and dimensions DataFrames.

        Args:
            metrics_df: DataFrame containing metrics data
            dimensions_df: DataFrame containing dimensions data
            data_view_id: Data view ID for the inventory
            data_view_name: Data view name for the inventory

        Returns:
            DerivedFieldInventory containing all derived field summaries
        """
        inventory = DerivedFieldInventory(
            data_view_id=data_view_id,
            data_view_name=data_view_name,
        )

        # Track processing statistics
        stats = BatchProcessingStats(logger=self.logger)

        # Process metrics
        if metrics_df is not None and not metrics_df.empty:
            for _, row in metrics_df.iterrows():
                summary = self._process_row(row, "Metric", stats)
                if summary:
                    inventory.fields.append(summary)
                    stats.record_success()

        # Process dimensions
        if dimensions_df is not None and not dimensions_df.empty:
            for _, row in dimensions_df.iterrows():
                summary = self._process_row(row, "Dimension", stats)
                if summary:
                    inventory.fields.append(summary)
                    stats.record_success()

        # Log processing summary
        stats.log_summary("derived fields")

        self.logger.info(
            f"Derived field inventory built: {inventory.total_derived_fields} fields "
            f"({inventory.metrics_count} metrics, {inventory.dimensions_count} dimensions)",
        )

        return inventory

    def _process_row(
        self,
        row: pd.Series,
        component_type: str,
        stats: BatchProcessingStats | None = None,
    ) -> DerivedFieldSummary | None:
        """Process a single row and return a DerivedFieldSummary if it's a derived field."""
        # Check if this is a derived field
        source_type = self._normalize_source_type(row.get("sourceFieldType", ""))

        if source_type != "derived":
            return None  # Not a derived field, skip silently (this is expected)

        # Get field definition
        field_def_str = row.get("fieldDefinition")

        # Handle NaN, empty, or invalid definitions
        try:
            is_na = pd.isna(field_def_str)
            if hasattr(is_na, "__len__") and not isinstance(is_na, bool):
                is_na = bool(is_na.all()) if len(is_na) > 0 else True
            else:
                is_na = bool(is_na)
        except TypeError, ValueError:  # pragma: no cover — pd.isna rarely raises
            is_na = field_def_str is None

        if is_na or field_def_str in ("NaN", "", "null", None):
            return None  # Empty definition for derived field is unexpected but not an error

        # Parse JSON
        try:
            if isinstance(field_def_str, str):
                functions = json.loads(field_def_str)
            elif isinstance(field_def_str, list):
                functions = field_def_str
            else:
                component_name = self._coerce_display_text(row.get("name", "Unknown"), fallback="Unknown")
                self.logger.warning(
                    f"Derived field '{component_name}' has unexpected definition type: {type(field_def_str)}",
                )
                if stats:
                    stats.record_skip("unexpected definition type", component_name)
                return None
        except (json.JSONDecodeError, TypeError) as e:
            component_name = self._coerce_display_text(row.get("name", "Unknown"), fallback="Unknown")
            self.logger.warning(f"Failed to parse fieldDefinition for '{component_name}': {e}")
            if stats:
                stats.record_skip(f"JSON parse error: {e}", component_name)
            return None

        if not isinstance(functions, list) or len(functions) == 0:
            return None  # Empty function list is not an error, just nothing to document

        component_name = self._coerce_display_text(row.get("name", "Unknown"), fallback="Unknown")
        component_id = validate_required_id({"id": row.get("id"), "name": component_name}, logger=self.logger)
        if not component_id:
            if stats:
                stats.record_skip("missing ID", component_name)
            return None

        component_description = self._coerce_display_text(row.get("description", ""), fallback="")

        # Parse the definition
        parsed = self._parse_definition(functions)

        # Generate logic summary
        logic_summary = self._generate_logic_summary(
            functions=functions,
            parsed=parsed,
            _component_name=component_name,
        )

        # Prepare definition JSON string
        if isinstance(field_def_str, str):
            definition_json_str = field_def_str
        else:
            definition_json_str = json.dumps(functions, separators=(",", ":"))

        return DerivedFieldSummary(
            component_id=component_id,
            component_name=component_name,
            component_type=component_type,
            complexity_score=parsed["complexity_score"],
            functions_used=parsed["functions_display"],
            functions_used_internal=parsed["functions_internal"],
            branch_count=parsed["branch_count"],
            nesting_depth=parsed["nesting_depth"],
            operator_count=parsed["operator_count"],
            schema_field_count=len(parsed["schema_fields"]),
            schema_fields=parsed["schema_fields"],
            lookup_references=parsed["lookup_references"],
            component_references=parsed["component_references"],
            rule_names=parsed["rule_names"],
            rule_descriptions=parsed["rule_descriptions"],
            logic_summary=logic_summary,
            inferred_output_type=parsed["inferred_output_type"],
            description=component_description,
            definition_json=definition_json_str,
        )

    def _parse_definition(self, functions: list[dict[str, Any]]) -> dict[str, Any]:
        """Parse a field definition and extract all relevant data."""
        functions_internal: list[str] = []
        schema_fields: list[str] = []
        lookup_references: list[str] = []
        component_references: list[str] = []
        rule_names: list[str] = []
        rule_descriptions: list[str] = []
        regex_patterns: list[str] = []

        total_operators = 0
        max_nesting = 0
        total_branches = 0

        for func_obj in self._iter_function_dicts(functions):
            func_type = self._normalize_func_name(func_obj.get("func", ""))
            if not func_type:
                continue

            if func_type not in functions_internal:
                functions_internal.append(func_type)

            # Extract rule metadata from any function type that has it
            rule_name = self._coerce_scalar_text(func_obj.get("#rule_name", ""))
            rule_desc = self._coerce_scalar_text(func_obj.get("#rule_description", ""))
            if rule_name and rule_name not in rule_names:
                rule_names.append(rule_name)
            if rule_desc and rule_desc not in rule_descriptions:
                rule_descriptions.append(rule_desc)

            # Extract field references
            if func_type == "raw-field":
                field_id = func_obj.get("id", "")
                field_id_normalized = str(field_id).strip() if field_id is not None else ""
                if (
                    field_id_normalized
                    and field_id_normalized.lower() not in {"nan", "none", "null"}
                    and field_id_normalized not in schema_fields
                ):
                    schema_fields.append(field_id_normalized)

            # Extract component references
            elif func_type == "field-def-reference":
                ref_id = func_obj.get("id", "")
                namespace = func_obj.get("namespace", "")
                ref_id_normalized = str(ref_id).strip() if ref_id is not None else ""
                namespace_normalized = str(namespace).strip() if namespace is not None else ""
                if ref_id_normalized and ref_id_normalized.lower() not in {"nan", "none", "null"}:
                    full_ref = (
                        f"{namespace_normalized}/{ref_id_normalized}" if namespace_normalized else ref_id_normalized
                    )
                    if full_ref not in component_references:
                        component_references.append(full_ref)

            # Extract lookup references
            elif func_type == "classify":
                mapping = func_obj.get("mapping", {})
                if isinstance(mapping, dict):
                    key_field = mapping.get("key-field", "")
                    key_field_normalized = str(key_field).strip() if key_field is not None else ""
                    if (
                        key_field_normalized
                        and key_field_normalized.lower() not in {"nan", "none", "null"}
                        and key_field_normalized not in lookup_references
                    ):
                        lookup_references.append(key_field_normalized)

            # Extract regex patterns
            elif func_type == "regex-replace":
                pattern = func_obj.get("pattern", "")
                if pattern:
                    regex_patterns.append(pattern)

            # Process match (Case When) branches
            elif func_type == "match":
                branches = func_obj.get("branches", [])
                if not isinstance(branches, list):
                    branches = []

                valid_branches = [branch for branch in branches if isinstance(branch, dict)]
                total_branches += len(valid_branches)

                # Count operators in branches
                for branch in valid_branches:
                    total_operators += 1
                    pred = branch.get("pred", {})
                    if isinstance(pred, dict):
                        ops, depth = self._count_predicate_operators(pred)
                        total_operators += ops
                        max_nesting = max(max_nesting, depth)

        # Convert to display names
        functions_display = [
            FUNCTION_DISPLAY_NAMES.get(f, f.replace("-", " ").title())
            for f in functions_internal
            if f != "raw-field"  # Don't show raw-field, it's implied
        ]

        # Compute complexity score
        complexity_score = self._compute_complexity_score(
            operators=total_operators,
            branches=total_branches,
            nesting=max_nesting,
            functions=len(functions_internal),
            schema_fields=len(schema_fields),
            regex=len(regex_patterns),
        )

        # Infer output type
        inferred_output_type = self._infer_output_type(functions)

        return {
            "functions_internal": functions_internal,
            "functions_display": functions_display,
            "schema_fields": schema_fields,
            "lookup_references": lookup_references,
            "component_references": component_references,
            "rule_names": rule_names,
            "rule_descriptions": rule_descriptions,
            "operator_count": total_operators,
            "branch_count": total_branches,
            "nesting_depth": max_nesting,
            "complexity_score": complexity_score,
            "inferred_output_type": inferred_output_type,
        }

    def _normalize_func_name(self, value: Any) -> str:
        """Normalize function names to strings suitable for comparisons/lookup keys."""
        return normalize_func_name(value)

    def _normalize_source_type(self, value: Any) -> str:
        """Normalize sourceFieldType values from scalar/list-like payloads."""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, (list, tuple)):
            for item in value:
                normalized = self._normalize_source_type(item)
                if normalized:
                    return normalized
        if hasattr(value, "tolist") and not isinstance(value, dict):
            try:
                return self._normalize_source_type(value.tolist())
            except TypeError, ValueError:
                return ""
        return ""

    def _coerce_scalar_text(self, value: Any) -> str:
        """Convert scalar values to display text while ignoring null/object payloads."""
        return coerce_scalar_text(value)

    def _coerce_display_text(self, value: Any, fallback: str = "") -> str:
        """Normalize display text with a fallback for null/unsupported value shapes."""
        return coerce_display_text(value, fallback=fallback)

    def _coerce_int_index(self, value: Any, default: int = 0) -> int:
        """Safely coerce split indexes to integers without raising on malformed values."""
        if isinstance(value, bool) or value is None:
            return default

        if isinstance(value, (int, float)):
            if isinstance(value, float) and not math.isfinite(value):
                return default
            try:
                return int(value)
            except TypeError, ValueError, OverflowError:  # pragma: no cover — finite floats always convert
                return default

        if isinstance(value, str):
            trimmed = value.strip()
            if not trimmed:
                return default
            try:
                return int(trimmed)
            except ValueError:
                return default

        return default

    def _iter_function_dicts(self, functions: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
        """Yield only dict function objects from mixed lists."""
        for func_obj in functions:
            if isinstance(func_obj, dict):
                yield func_obj

    def _count_predicate_operators(self, pred: dict[str, Any], depth: int = 0) -> tuple[int, int]:
        """Recursively count operators in a predicate structure."""
        if not isinstance(pred, dict):
            return 0, depth

        count = 0
        max_depth = depth

        func = self._normalize_func_name(pred.get("func", ""))

        # Logical operators that can contain nested predicates
        if func in ("and", "or"):
            count += 1
            nested_preds = pred.get("preds", [])
            if isinstance(nested_preds, list):
                for nested in nested_preds:
                    nested_count, nested_depth = self._count_predicate_operators(nested, depth + 1)
                    count += nested_count
                    max_depth = max(max_depth, nested_depth)

        # Comparison operators
        elif func in (
            "eq",
            "ne",
            "gt",
            "lt",
            "gte",
            "lte",
            "isset",
            "contains",
            "starts_with",
            "ends_with",
            "regex_match",
            "is_visitors_first",
            "true",
        ):
            count += 1

        return count, max_depth

    def _compute_complexity_score(
        self,
        operators: int,
        branches: int,
        nesting: int,
        functions: int,
        schema_fields: int,
        regex: int,
    ) -> float:
        """Compute a complexity score (0-100) for a derived field."""
        # Normalize each factor to 0-1 range
        op_score = min(1.0, operators / COMPLEXITY_MAX_VALUES["operators"])
        branch_score = min(1.0, branches / COMPLEXITY_MAX_VALUES["branches"])
        nesting_score = min(1.0, nesting / COMPLEXITY_MAX_VALUES["nesting"])
        func_score = min(1.0, functions / COMPLEXITY_MAX_VALUES["functions"])
        schema_score = min(1.0, schema_fields / COMPLEXITY_MAX_VALUES["schema_fields"])
        regex_score = min(1.0, regex / COMPLEXITY_MAX_VALUES["regex"])

        # Weighted sum
        weighted_score = (
            op_score * COMPLEXITY_WEIGHTS["operators"]
            + branch_score * COMPLEXITY_WEIGHTS["branches"]
            + nesting_score * COMPLEXITY_WEIGHTS["nesting"]
            + func_score * COMPLEXITY_WEIGHTS["functions"]
            + schema_score * COMPLEXITY_WEIGHTS["schema_fields"]
            + regex_score * COMPLEXITY_WEIGHTS["regex"]
        )

        return round(weighted_score * 100, 1)

    def _infer_output_type(self, functions: list[dict[str, Any]]) -> str:
        """Infer the output type of the derived field."""
        if not functions:
            return "unknown"

        last_func = functions[-1]
        func_type = self._normalize_func_name(last_func.get("func", ""))

        # Math operations produce numeric output
        if func_type in ("divide", "multiply", "add", "subtract"):
            return "numeric"

        # Check match branches for output type
        if func_type == "match":
            branches = last_func.get("branches", [])
            numeric_outputs = 0
            string_outputs = 0

            for branch in branches:
                if not isinstance(branch, dict):
                    continue
                map_to = branch.get("map-to")
                if isinstance(map_to, (int, float)):
                    numeric_outputs += 1
                elif isinstance(map_to, str):
                    string_outputs += 1

            if numeric_outputs > 0 and string_outputs == 0:
                return "numeric"
            if string_outputs > 0 and numeric_outputs == 0:
                return "string"

        # String manipulation functions
        if func_type in ("lowercase", "uppercase", "trim", "concatenate", "split", "url-parse", "regex-replace"):
            return "string"

        return "unknown"

    def _generate_logic_summary(
        self,
        functions: list[dict[str, Any]],
        parsed: dict[str, Any],
        _component_name: str,
    ) -> str:
        """Generate a brief human-readable summary of what the derived field does."""
        parts = []

        functions_internal = parsed["functions_internal"]

        # Describe the primary logic
        if "match" in functions_internal:
            # Extract example conditions and outputs from match branches
            match_details = self._describe_match_logic(functions)
            if match_details:
                parts.append(match_details)
            elif parsed["rule_names"]:
                branch_count = parsed["branch_count"]
                branch_word = "branch" if branch_count == 1 else "branches"
                rule_names = parsed["rule_names"]
                if len(rule_names) <= 4:
                    rules_str = ", ".join(rule_names)
                else:
                    rules_str = ", ".join(rule_names[:3]) + f", +{len(rule_names) - 3} more"
                parts.append(f"Conditional logic ({branch_count} {branch_word}): {rules_str}")
            else:
                branch_count = parsed["branch_count"]
                branch_word = "branch" if branch_count == 1 else "branches"
                parts.append(f"Conditional logic with {branch_count} {branch_word}")

        elif "classify" in functions_internal:
            lookup_details = self._describe_lookup_logic(functions)
            if lookup_details:
                parts.append(lookup_details)
            elif parsed["rule_names"]:
                # Classify with rule names
                rule_names = parsed["rule_names"]
                if len(rule_names) <= 4:
                    rules_str = ", ".join(rule_names)
                else:
                    rules_str = ", ".join(rule_names[:3]) + f", +{len(rule_names) - 3} more"
                parts.append(f"Lookup classification: {rules_str}")
            elif parsed["lookup_references"]:  # pragma: no cover — _describe_lookup_logic covers this
                parts.append(f"Lookup from {parsed['lookup_references'][0]}")
            else:
                parts.append("Lookup/classify operation")

        elif any(f in functions_internal for f in ["divide", "multiply", "add", "subtract"]):
            math_details = self._describe_math_logic(functions, parsed)
            if math_details:
                parts.append(math_details)
            else:
                math_ops = [f for f in functions_internal if f in ["divide", "multiply", "add", "subtract"]]
                parts.append(f"Math: {', '.join(FUNCTION_DISPLAY_NAMES.get(f, f) for f in math_ops)}")

        elif "url-parse" in functions_internal:
            url_details = self._describe_url_parse_logic(functions)
            parts.append(url_details)

        elif "concatenate" in functions_internal:
            concat_details = self._describe_concat_logic(functions, parsed)
            parts.append(concat_details)

        elif "regex-replace" in functions_internal:
            regex_details = self._describe_regex_logic(functions)
            parts.append(regex_details)

        elif "next" in functions_internal or "previous" in functions_internal:
            seq_details = self._describe_sequential_logic(functions)
            parts.append(seq_details)

        elif "summarize" in functions_internal:
            parts.append("Summarizes values")

        elif "deduplicate" in functions_internal:
            dedup_details = self._describe_dedup_logic(functions)
            parts.append(dedup_details)

        elif "merge" in functions_internal:
            merge_details = self._describe_merge_logic(functions, parsed)
            parts.append(merge_details)

        elif "split" in functions_internal:
            split_details = self._describe_split_logic(functions)
            parts.append(split_details)

        elif "typecast" in functions_internal:
            typecast_details = self._describe_typecast_logic(functions)
            parts.append(typecast_details)

        elif "datetime-bucket" in functions_internal:
            bucket_details = self._describe_datetime_bucket_logic(functions)
            parts.append(bucket_details)

        elif "datetime-slice" in functions_internal:
            slice_details = self._describe_datetime_slice_logic(functions)
            parts.append(slice_details)

        elif "timezone-shift" in functions_internal:
            tz_details = self._describe_timezone_shift_logic(functions)
            parts.append(tz_details)

        elif "find-replace" in functions_internal:
            find_replace_details = self._describe_find_replace_logic(functions)
            parts.append(find_replace_details)

        elif "depth" in functions_internal:
            depth_details = self._describe_depth_logic(functions)
            parts.append(depth_details)

        elif "profile" in functions_internal:
            profile_details = self._describe_profile_logic(functions)
            parts.append(profile_details)

        # Add transformation info
        transforms = []
        if "lowercase" in functions_internal:
            transforms.append("lowercase")
        if "uppercase" in functions_internal:
            transforms.append("uppercase")
        if "trim" in functions_internal:
            transforms.append("trim")

        if transforms and parts:
            parts.append(f"→ {'/'.join(transforms)}")
        elif transforms and not parts:
            parts.append(f"Applies {'/'.join(transforms)}")

        # Add field reference info if simple
        if not parts and parsed["schema_fields"]:
            if len(parsed["schema_fields"]) == 1:
                field_name = self._get_field_short_name(parsed["schema_fields"][0])
                parts.append(f"References {field_name}")
            else:
                parts.append(f"Combines {len(parsed['schema_fields'])} fields")

        return " ".join(parts) if parts else "Custom derived field logic"

    def _get_field_short_name(self, field_id: str) -> str:
        """Extract a short readable name from a field ID."""
        if not field_id:
            return "unknown"
        # Use shared utility for consistent name extraction
        short_name = extract_short_name(field_id)
        return short_name or "unknown"

    def _normalize_label_key(self, value: Any) -> str:
        """Normalize dynamic label/reference values to hashable string keys."""
        if value is None:
            return ""
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            for key in ("label", "field", "id", "name", "value"):
                if key in value:
                    normalized = self._normalize_label_key(value.get(key))
                    if normalized:
                        return normalized
            return ""
        if isinstance(value, (int, float, bool)):
            return str(value)
        return str(value).strip()

    def _build_label_map(self, functions: list[dict[str, Any]]) -> dict[str, str]:
        """Build a mapping from labels to field names/descriptions."""
        label_map = {}
        for func_obj in self._iter_function_dicts(functions):
            label = self._normalize_label_key(func_obj.get("label", ""))
            if not label:
                continue

            func_type = self._normalize_func_name(func_obj.get("func", ""))
            if func_type == "raw-field":
                # Map label to the field ID's short name
                field_id = func_obj.get("id", "")
                label_map[label] = self._get_field_short_name(field_id)
            elif func_type == "url-parse":
                # Map label to URL component description
                component = func_obj.get("component", {})
                if isinstance(component, dict):
                    comp_func = component.get("func", "")
                    if comp_func == "query":
                        param = component.get("param", "")
                        label_map[label] = f"?{param}" if param else "query"
                    else:
                        label_map[label] = comp_func
                else:
                    label_map[label] = str(component)
            elif func_type in ("lowercase", "uppercase", "trim", "split"):
                # Use input field if available
                field = self._normalize_label_key(func_obj.get("field", ""))
                if field and field in label_map:
                    label_map[label] = f"{func_type}({label_map[field]})"
                else:
                    label_map[label] = func_type

        return label_map

    def _describe_match_logic(self, functions: list[dict[str, Any]]) -> str:
        """Generate detailed description of match/Case When logic."""
        # Build label map for resolving field references
        label_map = self._build_label_map(functions)

        for func_obj in self._iter_function_dicts(functions):
            if func_obj.get("func") != "match":
                continue

            branches = func_obj.get("branches", [])
            if not isinstance(branches, list):
                continue
            branches = [branch for branch in branches if isinstance(branch, dict)]
            if not branches:
                continue

            # Get the match field for predicates that don't specify their own field
            match_field = self._normalize_label_key(func_obj.get("field", ""))
            if match_field in label_map:
                match_field_resolved = label_map[match_field]
            else:
                match_field_resolved = self._get_field_short_name(match_field) if match_field else ""

            # Get conditions and outputs
            examples = []
            for branch in branches:
                map_to = branch.get("map-to", "")
                pred = branch.get("pred", {})
                condition_desc = self._describe_predicate(pred, label_map=label_map, match_field=match_field_resolved)

                # Handle map-to value
                output_str = self._format_map_to_value(map_to, label_map)

                if condition_desc and output_str:
                    examples.append(f"{condition_desc}→{output_str}")
                elif output_str and not condition_desc:
                    # If we have output but no condition, try to show something useful
                    pred_func = pred.get("func", "") if isinstance(pred, dict) else ""
                    if pred_func == "true":  # pragma: no cover — _describe_predicate returns "default" for true
                        examples.append(f"default→{output_str}")
                    elif output_str:
                        # Show the output values even without condition detail
                        examples.append(f"→{output_str}")

            # Check for default/else value
            default = func_obj.get("default", "")
            default_str = ""
            if default:
                default_formatted = self._format_map_to_value(default, label_map)
                if default_formatted:
                    default_str = f", else: {default_formatted}"

            branch_count = len(branches)
            if examples:
                # Smart summary: show all unique outputs, summarize repetitive conditions
                # Group by output to see if there are many conditions leading to same output
                output_conditions: dict[str, list[str]] = {}
                for ex in examples:
                    if "→" in ex:
                        parts = ex.split("→", 1)
                        cond = parts[0]
                        out = parts[1] if len(parts) > 1 else ""
                        if out not in output_conditions:
                            output_conditions[out] = []
                        output_conditions[out].append(cond)

                # Build summary
                summary_parts = []
                for output, conditions in output_conditions.items():
                    if len(conditions) == 1:
                        summary_parts.append(f"{conditions[0]}→{output}")
                    elif len(conditions) <= 3:
                        cond_str = " OR ".join(conditions)
                        summary_parts.append(f"({cond_str})→{output}")
                    else:
                        # Many conditions for same output - summarize
                        sample = conditions[0]
                        summary_parts.append(f"({sample} OR +{len(conditions) - 1} more)→{output}")

                example_str = "; ".join(summary_parts)
                return f"Case When ({branch_count}): {example_str}{default_str}"

        return ""

    def _format_map_to_value(self, map_to: Any, label_map: dict[str, str]) -> str:
        """Format a map-to value for display, resolving field references where possible."""
        if map_to is None:
            return ""

        if isinstance(map_to, dict):
            map_type = map_to.get("type", "")
            map_value = self._normalize_label_key(map_to.get("value", ""))
            if map_type == "field" and map_value:
                # Try to resolve the field reference through label_map
                if map_value in label_map:
                    resolved = label_map[map_value]
                    return f"[{resolved}]"
                # Otherwise show a cleaner version
                short_name = self._get_field_short_name(map_value)
                return f"[{short_name}]"
            if "val" in map_to:
                val = map_to["val"]
                return f'"{val}"' if isinstance(val, str) else str(val)
            return "[dynamic]"

        if isinstance(map_to, str):
            return f'"{map_to}"'

        # Numeric or other types
        return str(map_to)

    def _describe_predicate(
        self,
        pred: dict[str, Any],
        max_depth: int = 2,
        label_map: dict[str, str] | None = None,
        match_field: str = "",
    ) -> str:
        """Convert a predicate to a brief human-readable condition."""
        if not isinstance(pred, dict) or max_depth <= 0:
            return ""

        func = self._normalize_func_name(pred.get("func", ""))
        label_map = label_map or {}

        # Helper to get field name - handles both arg1 structure and direct field reference
        def get_field() -> str:
            # Try arg1 structure first (nested object)
            arg1 = pred.get("arg1", {})
            if isinstance(arg1, dict) and arg1:
                return self._get_field_from_arg(arg1)
            # Fall back to direct field reference (CJA common format)
            field_ref = pred.get("field", "")
            if field_ref:
                field_ref = self._normalize_label_key(field_ref)
                # Try to resolve label to actual field name
                if field_ref in label_map:
                    return label_map[field_ref]
                return self._get_field_short_name(field_ref)
            # Use match_field as fallback for predicates without explicit field
            return match_field

        # Helper to get value - handles multiple CJA formats
        def get_value():
            # Try arg2 structure first (nested object with val)
            arg2 = pred.get("arg2", {})
            if isinstance(arg2, dict) and "val" in arg2:
                return arg2["val"]
            # Try direct "val" key (common CJA format)
            if "val" in pred:
                return pred["val"]
            # Fall back to direct "value" key
            return pred.get("value", "")

        # Comparison operators
        if func in ("eq", "streq"):
            field = get_field()
            value = get_value()
            if field and value is not None:
                return f'{field}="{value}"' if isinstance(value, str) else f"{field}={value}"
            if value is not None:
                # No field specified, just show the value match
                return f'="{value}"' if isinstance(value, str) else f"={value}"
        elif func in ("ne", "strne"):
            field = get_field()
            value = get_value()
            if field and value is not None:
                return f'{field}≠"{value}"' if isinstance(value, str) else f"{field}≠{value}"
            if value is not None:
                return f'≠"{value}"' if isinstance(value, str) else f"≠{value}"
        elif func == "gt":
            field = get_field()
            value = get_value()
            if field and value is not None:
                return f"{field}>{value}"
        elif func in ("gte", "ge"):
            field = get_field()
            value = get_value()
            if field and value is not None:
                return f"{field}>={value}"
        elif func == "lt":
            field = get_field()
            value = get_value()
            if field and value is not None:
                return f"{field}<{value}"
        elif func in ("lte", "le"):
            field = get_field()
            value = get_value()
            if field and value is not None:
                return f"{field}<={value}"
        elif func == "contains":
            field = get_field()
            value = get_value()
            if field and value:
                return f'{field} contains "{value}"'
        elif func == "starts_with":
            field = get_field()
            value = get_value()
            if field and value:
                return f'{field} starts "{value}"'
        elif func == "ends_with":
            field = get_field()
            value = get_value()
            if field and value:
                return f'{field} ends "{value}"'
        elif func == "isset":
            field = get_field()
            if field:
                return f"{field} exists"
        elif func == "regex_match":
            field = get_field()
            value = get_value()
            pattern = value if isinstance(value, str) else ""
            if field and pattern:
                short_pattern = pattern[:20] + "..." if len(pattern) > 20 else pattern
                return f"{field} matches /{short_pattern}/"

        # Logical operators
        elif func == "and":
            preds = pred.get("preds", [])
            if isinstance(preds, list) and preds:
                parts = [self._describe_predicate(p, max_depth - 1, label_map, match_field) for p in preds[:3]]
                parts = [p for p in parts if p]
                if parts:
                    suffix = f" AND +{len(preds) - 3} more" if len(preds) > 3 else ""
                    return " AND ".join(parts) + suffix
        elif func == "or":
            preds = pred.get("preds", [])
            if isinstance(preds, list) and preds:
                parts = [self._describe_predicate(p, max_depth - 1, label_map, match_field) for p in preds[:3]]
                parts = [p for p in parts if p]
                if parts:
                    suffix = f" OR +{len(preds) - 3} more" if len(preds) > 3 else ""
                    return " OR ".join(parts) + suffix

        # Handle "true" predicate (default/catch-all)
        elif func == "true":
            return "default"

        return ""

    def _get_field_from_arg(self, arg: dict[str, Any]) -> str:
        """Extract field name from an argument node."""
        if not isinstance(arg, dict):
            return ""
        func = arg.get("func", "")
        if func == "raw-field":
            return self._get_field_short_name(arg.get("id", ""))
        if func == "field-def-reference":
            return self._get_field_short_name(arg.get("id", ""))
        # Handle direct field reference
        if "id" in arg:
            return self._get_field_short_name(arg.get("id", ""))
        return ""

    def _describe_lookup_logic(self, functions: list[dict[str, Any]]) -> str:
        """Generate detailed description of lookup/classify logic."""
        for func_obj in self._iter_function_dicts(functions):
            if func_obj.get("func") != "classify":
                continue

            mapping = func_obj.get("mapping", {})
            if isinstance(mapping, dict):
                key_field = mapping.get("key-field", "")
                value_field = mapping.get("value-field", "")
                dataset = mapping.get("dataset", "")
                if key_field and value_field:
                    dataset_name = dataset.split("/")[-1] if isinstance(dataset, str) and dataset else "lookup"
                    return f"Lookup: {self._get_field_short_name(key_field)} → {self._get_field_short_name(value_field)} from {dataset_name}"
                if key_field:
                    return f"Lookup by {self._get_field_short_name(key_field)}"

        return ""

    def _describe_url_parse_logic(self, functions: list[dict[str, Any]]) -> str:
        """Generate detailed description of URL parsing logic."""
        for func_obj in self._iter_function_dicts(functions):
            if func_obj.get("func") != "url-parse":
                continue

            component = func_obj.get("component", "")
            input_field = ""

            # Find the input field
            args = func_obj.get("args", [])
            if isinstance(args, list) and args and isinstance(args[0], dict):
                input_field = self._get_field_short_name(args[0].get("id", ""))

            root_param = self._coerce_scalar_text(func_obj.get("param", ""))
            component_names = {
                "hostname": "hostname",
                "path": "path",
                "query": "query string",
                "fragment": "fragment",
                "protocol": "protocol",
                "port": "port",
                "query_param": f"query param '{root_param}'" if root_param else "query string",
            }
            if isinstance(component, dict):
                # Some payloads provide URL component as an object, e.g. {"func": "query", "param": "..."}.
                comp_func = self._normalize_func_name(component.get("func", ""))
                if comp_func == "query":
                    param_str = self._coerce_scalar_text(component.get("param", ""))
                    component_desc = f"query param '{param_str}'" if param_str else "query string"
                else:
                    component_desc = component_names.get(comp_func, comp_func or "URL component")
            elif isinstance(component, str):
                component_desc = component_names.get(component, component)
            else:
                component_desc = self._coerce_scalar_text(component) or "URL component"

            if input_field:
                return f"URL parse: extract {component_desc} from {input_field}"
            return f"URL parse: extract {component_desc}"

        return "URL parsing"

    def _describe_concat_logic(self, functions: list[dict[str, Any]], _parsed: dict[str, Any]) -> str:
        """Generate detailed description of concatenation logic."""
        for func_obj in self._iter_function_dicts(functions):
            if func_obj.get("func") != "concatenate":
                continue

            delimiter = func_obj.get("delimiter", "")
            args = func_obj.get("args", [])
            if not isinstance(args, list):
                args = []
            field_count = len([a for a in args if isinstance(a, dict) and a.get("func") == "raw-field"])

            if delimiter:
                delim_desc = f'"{delimiter}"' if str(delimiter).strip() else "(space)"
                if field_count > 0:
                    return f"Concat {field_count} fields with {delim_desc}"
                return f"Concatenate with {delim_desc}"

            if field_count > 0:
                return f"Concatenate {field_count} fields"

        return "Concatenates multiple fields"

    def _describe_regex_logic(self, functions: list[dict[str, Any]]) -> str:
        """Generate detailed description of regex replacement logic."""
        for func_obj in self._iter_function_dicts(functions):
            if func_obj.get("func") != "regex-replace":
                continue

            pattern = self._coerce_scalar_text(func_obj.get("pattern", ""))
            replacement = self._coerce_scalar_text(func_obj.get("replacement", ""))

            if pattern:
                short_pattern = pattern[:25] + "..." if len(pattern) > 25 else pattern
                if replacement:
                    short_repl = replacement[:15] + "..." if len(replacement) > 15 else replacement
                    return f'Regex: /{short_pattern}/ → "{short_repl}"'
                return f"Regex: remove /{short_pattern}/"

        return "Regex pattern replacement"

    def _describe_sequential_logic(self, functions: list[dict[str, Any]]) -> str:
        """Generate detailed description of next/previous value logic."""
        for func_obj in self._iter_function_dicts(functions):
            func = func_obj.get("func", "")
            if func not in ("next", "previous"):
                continue

            direction = "Next" if func == "next" else "Previous"
            persistence = func_obj.get("persistence", "")

            args = func_obj.get("args", [])
            field_name = ""
            if isinstance(args, list) and args and isinstance(args[0], dict):
                field_name = self._get_field_short_name(args[0].get("id", ""))

            if field_name:
                if persistence:
                    return f"{direction} value of {field_name} ({persistence})"
                return f"{direction} value of {field_name}"

            return f"{direction} value lookup"

        return "Sequential value lookup"

    def _describe_dedup_logic(self, functions: list[dict[str, Any]]) -> str:
        """Generate detailed description of deduplication logic."""
        for func_obj in self._iter_function_dicts(functions):
            if func_obj.get("func") != "deduplicate":
                continue

            scope = func_obj.get("scope", "")  # session, person, etc.
            args = func_obj.get("args", [])
            field_name = ""
            if isinstance(args, list) and args and isinstance(args[0], dict):
                field_name = self._get_field_short_name(args[0].get("id", ""))

            if field_name and scope:
                return f"Deduplicate {field_name} per {scope}"
            if field_name:
                return f"Deduplicate {field_name}"

        return "Deduplicates values"

    def _describe_merge_logic(self, _functions: list[dict[str, Any]], parsed: dict[str, Any]) -> str:
        """Generate detailed description of merge fields logic."""
        schema_fields = parsed.get("schema_fields", [])
        if len(schema_fields) >= 2:
            names = [self._get_field_short_name(f) for f in schema_fields[:3]]
            if len(schema_fields) > 3:
                return f"Merge: {', '.join(names)}, +{len(schema_fields) - 3} more"
            return f"Merge: {', '.join(names)}"
        return "Merge multiple fields"

    def _describe_split_logic(self, functions: list[dict[str, Any]]) -> str:
        """Generate detailed description of split logic."""
        for func_obj in self._iter_function_dicts(functions):
            if func_obj.get("func") != "split":
                continue

            delimiter = func_obj.get("delimiter", "")
            index_raw = func_obj.get("index", 0)
            index = self._coerce_int_index(index_raw, default=0)

            args = func_obj.get("args", [])
            field_name = ""
            if isinstance(args, list) and args and isinstance(args[0], dict):
                field_name = self._get_field_short_name(args[0].get("id", ""))

            delim_desc = f'"{delimiter}"' if delimiter else "delimiter"
            if field_name:
                return f"Split {field_name} by {delim_desc}, get part {index + 1}"
            return f"Split by {delim_desc}, get part {index + 1}"

        return "Split string"

    def _describe_math_logic(self, functions: list[dict[str, Any]], parsed: dict[str, Any]) -> str:
        """Generate detailed description of math operations."""
        schema_fields = parsed.get("schema_fields", [])
        field_names = [self._get_field_short_name(f) for f in schema_fields[:2]]

        for func_obj in self._iter_function_dicts(functions):
            func = func_obj.get("func", "")
            if func == "divide" and len(field_names) >= 2:
                return f"Math: {field_names[0]} / {field_names[1]}"
            if func == "multiply" and len(field_names) >= 2:
                return f"Math: {field_names[0]} x {field_names[1]}"
            if func == "add" and len(field_names) >= 2:
                return f"Math: {field_names[0]} + {field_names[1]}"
            if func == "subtract" and len(field_names) >= 2:
                return f"Math: {field_names[0]} - {field_names[1]}"

        return ""

    def _describe_typecast_logic(self, functions: list[dict[str, Any]]) -> str:
        """Generate detailed description of typecast logic."""
        for func_obj in self._iter_function_dicts(functions):
            if func_obj.get("func") != "typecast":
                continue

            target_type = func_obj.get("type", func_obj.get("to", ""))
            field_ref = func_obj.get("field", "")
            input_field = ""

            # Find the input field from args or referenced label
            args = func_obj.get("args", [])
            if isinstance(args, list) and args and isinstance(args[0], dict):
                input_field = self._get_field_short_name(args[0].get("id", ""))
            elif field_ref:
                input_field = field_ref

            if input_field and target_type:
                return f"Converts {input_field} to {target_type}"
            if target_type:
                return f"Converts to {target_type}"

        return "Type conversion"

    def _describe_datetime_bucket_logic(self, functions: list[dict[str, Any]]) -> str:
        """Generate detailed description of datetime bucketing logic."""
        for func_obj in self._iter_function_dicts(functions):
            if func_obj.get("func") != "datetime-bucket":
                continue

            interval = func_obj.get("bucket", func_obj.get("interval", func_obj.get("granularity", "")))
            field_ref = func_obj.get("field", "")
            input_field = ""

            args = func_obj.get("args", [])
            if isinstance(args, list) and args and isinstance(args[0], dict):
                input_field = self._get_field_short_name(args[0].get("id", ""))
            elif field_ref:
                input_field = field_ref

            if input_field and interval:
                return f"Buckets {input_field} by {interval}"
            if interval:
                return f"Date bucketing by {interval}"

        return "Date bucketing"

    def _describe_datetime_slice_logic(self, functions: list[dict[str, Any]]) -> str:
        """Generate detailed description of datetime slicing logic."""
        for func_obj in self._iter_function_dicts(functions):
            if func_obj.get("func") != "datetime-slice":
                continue

            component = func_obj.get("component", func_obj.get("part", func_obj.get("slice", "")))
            field_ref = func_obj.get("field", "")
            input_field = ""

            args = func_obj.get("args", [])
            if isinstance(args, list) and args and isinstance(args[0], dict):
                input_field = self._get_field_short_name(args[0].get("id", ""))
            elif field_ref:
                input_field = field_ref

            if input_field and component:
                return f"Extracts {component} from {input_field}"
            if component:
                return f"Extracts {component} from date"

        return "Date component extraction"

    def _describe_timezone_shift_logic(self, functions: list[dict[str, Any]]) -> str:
        """Generate detailed description of timezone shift logic."""
        for func_obj in self._iter_function_dicts(functions):
            if func_obj.get("func") != "timezone-shift":
                continue

            src_tz = func_obj.get("from", func_obj.get("source-timezone", func_obj.get("sourceTimezone", "")))
            dst_tz = func_obj.get("to", func_obj.get("target-timezone", func_obj.get("targetTimezone", "")))
            field_ref = func_obj.get("field", "")
            input_field = ""

            args = func_obj.get("args", [])
            if isinstance(args, list) and args and isinstance(args[0], dict):
                input_field = self._get_field_short_name(args[0].get("id", ""))
            elif field_ref:
                input_field = field_ref

            if input_field and src_tz and dst_tz:
                return f"Shifts {input_field} from {src_tz} to {dst_tz}"
            if src_tz and dst_tz:
                return f"Timezone shift from {src_tz} to {dst_tz}"
            if dst_tz:
                return f"Timezone shift to {dst_tz}"

        return "Timezone shift"

    def _describe_find_replace_logic(self, functions: list[dict[str, Any]]) -> str:
        """Generate detailed description of find and replace logic."""
        for func_obj in self._iter_function_dicts(functions):
            if func_obj.get("func") != "find-replace":
                continue

            find_val = func_obj.get("find", func_obj.get("pattern", func_obj.get("search", "")))
            replace_val = func_obj.get("replace", func_obj.get("replacement", func_obj.get("with", "")))
            field_ref = func_obj.get("field", "")
            input_field = ""

            args = func_obj.get("args", [])
            if isinstance(args, list) and args and isinstance(args[0], dict):
                input_field = self._get_field_short_name(args[0].get("id", ""))
            elif field_ref:
                input_field = field_ref

            # Truncate long patterns/replacements
            if find_val:
                find_str = str(find_val)
                if len(find_str) > 20:
                    find_val = find_str[:20] + "..."
            if replace_val:
                replace_str = str(replace_val)
                if len(replace_str) > 15:
                    replace_val = replace_str[:15] + "..."

            if input_field and find_val:
                if replace_val:
                    return f"Replaces '{find_val}' with '{replace_val}' in {input_field}"
                return f"Removes '{find_val}' from {input_field}"
            if find_val:
                if replace_val:
                    return f"Replaces '{find_val}' with '{replace_val}'"
                return f"Removes '{find_val}'"

        return "Find and replace"

    def _describe_depth_logic(self, functions: list[dict[str, Any]]) -> str:
        """Generate detailed description of depth counting logic."""
        for func_obj in self._iter_function_dicts(functions):
            if func_obj.get("func") != "depth":
                continue

            delimiter = func_obj.get("delimiter", func_obj.get("separator", "/"))
            field_ref = func_obj.get("field", "")
            input_field = ""

            args = func_obj.get("args", [])
            if isinstance(args, list) and args and isinstance(args[0], dict):
                input_field = self._get_field_short_name(args[0].get("id", ""))
            elif field_ref:
                input_field = field_ref

            if input_field:
                return f"Counts depth of {input_field} using '{delimiter}' separator"
            return "Counts path depth"

        return "Depth counting"

    def _describe_profile_logic(self, functions: list[dict[str, Any]]) -> str:
        """Generate detailed description of profile attribute reference."""
        for func_obj in self._iter_function_dicts(functions):
            if func_obj.get("func") != "profile":
                continue

            # Profile references can have various attribute identifiers
            attr_name = func_obj.get("attribute", func_obj.get("name", func_obj.get("id", "")))
            namespace = func_obj.get("namespace", "")

            if attr_name:
                if namespace:
                    return f"References profile attribute {namespace}/{attr_name}"
                return f"References profile attribute {attr_name}"

        return "Profile attribute reference"


# ==================== MODULE EXPORTS ====================

__all__ = [
    "FUNCTION_DISPLAY_NAMES",
    "DerivedFieldInventory",
    "DerivedFieldInventoryBuilder",
    "DerivedFieldSummary",
    "__version__",
]
