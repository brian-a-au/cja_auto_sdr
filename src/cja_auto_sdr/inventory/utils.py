"""
CJA Inventory Shared Utilities

Common utility functions used across all CJA inventory modules:
- cja_calculated_metrics_inventory.py
- cja_derived_fields_inventory.py
- cja_segments_inventory.py

This module provides shared functionality to eliminate code duplication
and ensure consistent behavior across inventory types.

Version: 1.0.0
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

import pandas as pd

__version__ = "1.0.0"


# ==================== DATE FORMATTING ====================


def format_iso_date(iso_date: Any) -> str:
    """Format ISO date string to readable format (YYYY-MM-DD HH:MM).

    Args:
        iso_date: ISO 8601 date string (e.g., "2024-01-15T10:30:00Z")

    Returns:
        Formatted date string or "-" if invalid/empty
    """
    if iso_date is None:
        return "-"
    value = iso_date if isinstance(iso_date, str) else str(iso_date)
    value = value.strip()
    if not value:
        return "-"
    try:
        # Handle various ISO formats including timezone
        if "T" in value:
            dt = datetime.fromisoformat(value)
            return dt.strftime("%Y-%m-%d %H:%M")
        return value[:10]  # Just the date part
    except ValueError, TypeError:
        return value[:19] if len(value) > 19 else value


# ==================== OWNER/TAGS EXTRACTION ====================


def extract_owner(owner_data: Any) -> tuple[str, str]:
    """Extract owner name and ID from CJA API owner field.

    Args:
        owner_data: Owner field from API response (dict, str, or None)

    Returns:
        Tuple of (owner_name, owner_id)
    """
    if isinstance(owner_data, dict):
        return (
            owner_data.get("name", ""),
            owner_data.get("id", owner_data.get("login", "")),
        )
    if owner_data:
        return (str(owner_data), "")
    return ("", "")


def extract_tags(tags_data: Any) -> list[str]:
    """Extract tag names from CJA API tags field.

    Args:
        tags_data: Tags field from API response (list or None)

    Returns:
        List of tag name strings
    """
    if isinstance(tags_data, list):
        return [t.get("name", str(t)) if isinstance(t, dict) else str(t) for t in tags_data]
    return []


# ==================== API RESPONSE HANDLING ====================


def normalize_api_response(
    response: Any,
    response_type: str = "items",
    logger: logging.Logger | None = None,
) -> list[dict[str, Any]] | None:
    """Normalize CJA API responses (DataFrame or list) to list of dicts.

    Args:
        response: DataFrame, list, or None from CJA API
        response_type: Name for logging (e.g., "calculated metrics", "segments")
        logger: Optional logger instance

    Returns:
        List of dicts or None if empty/invalid
    """
    log = logger or logging.getLogger(__name__)

    if response is None:
        log.info(f"No {response_type} found (None response)")
        return None

    if isinstance(response, pd.DataFrame):
        if response.empty:
            log.info(f"No {response_type} found (empty DataFrame)")
            return None
        return response.to_dict("records")

    if isinstance(response, list):
        if not response:
            log.info(f"No {response_type} found (empty list)")
            return None
        return response

    log.warning(f"Unexpected response type for {response_type}: {type(response)}")
    return None


# ==================== REFERENCE NAME EXTRACTION ====================


def extract_short_name(full_id: Any, separator: str = "/") -> str:
    """Extract short name from full path-like ID.

    Examples:
        "metrics/revenue" -> "revenue"
        "variables/evar1" -> "evar1"
        "simple_id" -> "simple_id"
        "_experience.analytics.customDimensions.eVars.eVar1" -> "eVar1"

    Args:
        full_id: Full path-like identifier
        separator: Path separator (default "/")

    Returns:
        Short name extracted from the path
    """
    if full_id is None:
        return ""
    try:
        is_na = pd.isna(full_id)
        if isinstance(is_na, bool):
            if is_na:
                return ""
        elif hasattr(is_na, "all") and bool(is_na.all()):
            return ""
    except TypeError, ValueError:
        pass

    full_id = str(full_id).strip()
    if not full_id:
        return ""
    if separator in full_id:
        return full_id.split(separator)[-1]
    # Also handle dot notation (XDM paths)
    if "." in full_id:
        return full_id.split(".")[-1]
    return full_id


# ==================== NORMALIZATION HELPERS ====================


def normalize_func_name(value: Any) -> str:
    """Normalize function names to comparable string keys."""
    if isinstance(value, str):
        return value.strip()
    return ""


def coerce_scalar_text(value: Any) -> str:
    """Convert scalar values to text while ignoring null/object payloads."""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()

    try:
        is_na = pd.isna(value)
        if isinstance(is_na, bool) and is_na:
            return ""
    except TypeError, ValueError:
        pass

    if hasattr(value, "isoformat"):
        try:
            iso_value = value.isoformat()
            if iso_value is None:
                return ""
            return str(iso_value).strip()
        except TypeError, ValueError:
            pass

    if pd.api.types.is_scalar(value):
        return str(value).strip()
    return ""


def coerce_display_text(value: Any, fallback: str = "") -> str:
    """Normalize text values for summaries/dataclass fields."""
    normalized = coerce_scalar_text(value)
    return normalized or fallback


# ==================== COMPLEXITY SCORING ====================


def compute_complexity_score(
    factors: dict[str, int],
    weights: dict[str, float],
    max_values: dict[str, int],
) -> float:
    """Compute a generic weighted complexity score (0-100).

    This provides a standardized approach to complexity scoring across
    all inventory types. Each factor is normalized to 0-1 range using
    its max value, then weighted according to the provided weights.

    Args:
        factors: Dict of factor_name -> count (e.g., {"operators": 5, "nesting": 2})
        weights: Dict of factor_name -> weight (should sum to ~1.0)
        max_values: Dict of factor_name -> max_count (for normalization)

    Returns:
        Complexity score from 0.0 to 100.0

    Example:
        >>> factors = {"operators": 10, "metric_refs": 3, "nesting": 2}
        >>> weights = {"operators": 0.4, "metric_refs": 0.3, "nesting": 0.3}
        >>> max_values = {"operators": 50, "metric_refs": 10, "nesting": 8}
        >>> compute_complexity_score(factors, weights, max_values)
        18.8
    """
    normalized: dict[str, float] = {}
    for factor, count in factors.items():
        max_val = max_values.get(factor, 1)
        normalized[factor] = min(1.0, count / max_val) if max_val > 0 else 0.0

    weighted_score = sum(normalized.get(factor, 0.0) * weight for factor, weight in weights.items())

    return round(weighted_score * 100, 1)


# ==================== BATCH PROCESSING HELPERS ====================


class BatchProcessingStats:
    """Track statistics for batch processing operations.

    Use this to track how many items were processed successfully vs skipped,
    providing visibility into data quality issues.
    """

    def __init__(self, logger: logging.Logger | None = None):
        self.processed = 0
        self.skipped = 0
        self.errors: list[str] = []
        self.logger = logger or logging.getLogger(__name__)

    def record_success(self) -> None:
        """Record a successfully processed item."""
        self.processed += 1

    def record_skip(self, reason: str, item_id: str = "") -> None:
        """Record a skipped item with reason.

        Args:
            reason: Why the item was skipped
            item_id: Optional identifier for the skipped item
        """
        self.skipped += 1
        if item_id:
            self.logger.warning(f"Skipped {item_id}: {reason}")
        else:
            self.logger.warning(f"Skipped item: {reason}")

    def record_error(self, error: str, item_id: str = "") -> None:
        """Record an error during processing.

        Args:
            error: Error message
            item_id: Optional identifier for the failed item
        """
        self.skipped += 1
        error_msg = f"{item_id}: {error}" if item_id else error
        self.errors.append(error_msg)
        self.logger.warning(f"Error processing item: {error_msg}")

    def log_summary(self, item_type: str = "items") -> None:
        """Log a summary of processing results.

        Args:
            item_type: Name of items being processed (e.g., "metrics", "segments")
        """
        total = self.processed + self.skipped
        if total == 0:
            return

        if self.skipped > 0:
            skip_pct = (self.skipped / total) * 100
            self.logger.warning(
                f"Batch processing: {self.processed} {item_type} processed, {self.skipped} skipped ({skip_pct:.1f}%)",
            )
        else:
            self.logger.info(f"Batch processing: {self.processed} {item_type} processed successfully")

    @property
    def has_issues(self) -> bool:
        """Check if any items were skipped or had errors."""
        return self.skipped > 0 or len(self.errors) > 0


# ==================== VALIDATION HELPERS ====================


def validate_required_id(
    item_data: dict[str, Any],
    id_field: str = "id",
    name_field: str = "name",
    logger: logging.Logger | None = None,
) -> str | None:
    """Validate that an item has a required ID field.

    Args:
        item_data: Dict containing the item data
        id_field: Name of the ID field to check
        name_field: Name field for logging context
        logger: Optional logger instance

    Returns:
        The normalized ID value if valid, None if missing/empty/NaN-like
    """
    raw_item_id = item_data.get(id_field, "")

    missing_id = False
    try:
        is_na = pd.isna(raw_item_id)
        if isinstance(is_na, bool):
            missing_id = is_na
        elif hasattr(is_na, "all"):
            missing_id = bool(is_na.all())
    except TypeError, ValueError:
        missing_id = False

    item_id = "" if missing_id else str(raw_item_id).strip()
    if item_id.lower() in {"", "nan", "none", "null"}:
        log = logger or logging.getLogger(__name__)
        item_name = item_data.get(name_field, "Unknown")
        log.warning(f"Item '{item_name}' has no {id_field} - skipping")
        return None
    return item_id


# ==================== MODULE EXPORTS ====================

__all__ = [
    "BatchProcessingStats",
    "__version__",
    "coerce_display_text",
    "coerce_scalar_text",
    "compute_complexity_score",
    "extract_owner",
    "extract_short_name",
    "extract_tags",
    "format_iso_date",
    "normalize_api_response",
    "normalize_func_name",
    "validate_required_id",
]
