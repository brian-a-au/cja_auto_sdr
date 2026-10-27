"""
CJA Inventory Modules

Provides inventory builders for CJA components:
- Calculated Metrics
- Derived Fields
- Segments
"""

from __future__ import annotations

from cja_auto_sdr.inventory.calculated_metrics import (
    CalculatedMetricsInventory,
    CalculatedMetricsInventoryBuilder,
    CalculatedMetricSummary,
)
from cja_auto_sdr.inventory.derived_fields import (
    DerivedFieldInventory,
    DerivedFieldInventoryBuilder,
    DerivedFieldSummary,
)
from cja_auto_sdr.inventory.segments import (
    SegmentsInventory,
    SegmentsInventoryBuilder,
    SegmentSummary,
)
from cja_auto_sdr.inventory.utils import (
    BatchProcessingStats,
    compute_complexity_score,
    extract_owner,
    extract_short_name,
    extract_tags,
    format_iso_date,
    normalize_api_response,
    validate_required_id,
)

__all__ = [
    # Utilities
    "BatchProcessingStats",
    # Calculated Metrics
    "CalculatedMetricSummary",
    "CalculatedMetricsInventory",
    "CalculatedMetricsInventoryBuilder",
    "DerivedFieldInventory",
    "DerivedFieldInventoryBuilder",
    # Derived Fields
    "DerivedFieldSummary",
    # Segments
    "SegmentSummary",
    "SegmentsInventory",
    "SegmentsInventoryBuilder",
    "compute_complexity_score",
    # Lazy-loaded
    "display_inventory_summary",
    "extract_owner",
    "extract_short_name",
    "extract_tags",
    "format_iso_date",
    "normalize_api_response",
    "validate_required_id",
]


from cja_auto_sdr.core.lazy import make_getattr

__getattr__ = make_getattr(
    __name__,
    ["display_inventory_summary"],
    mapping={"display_inventory_summary": "cja_auto_sdr.inventory.summary"},
)
