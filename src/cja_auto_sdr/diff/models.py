from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from enum import Enum
from typing import Any

from cja_auto_sdr.core.version import __version__


class ChangeType(Enum):
    """Types of changes detected in diff comparison."""

    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


@dataclass
class ComponentDiff:
    """Represents a diff for a single component (metric or dimension)."""

    id: str
    name: str
    change_type: ChangeType
    source_data: dict | None = None  # Full data from source
    target_data: dict | None = None  # Full data from target
    changed_fields: dict[str, tuple[Any, Any]] | None = None  # field -> (source_value, target_value)

    def __post_init__(self):
        if self.changed_fields is None:
            self.changed_fields = {}


@dataclass
class MetadataDiff:
    """Represents changes to data view metadata."""

    source_name: str
    target_name: str
    source_id: str
    target_id: str
    source_owner: str = ""
    target_owner: str = ""
    source_description: str = ""
    target_description: str = ""
    changed_fields: dict[str, tuple[str, str]] | None = None

    def __post_init__(self):
        if self.changed_fields is None:
            self.changed_fields = {}


@dataclass
class DiffSummary:
    """Summary statistics for a diff operation."""

    source_metrics_count: int = 0
    target_metrics_count: int = 0
    source_dimensions_count: int = 0
    target_dimensions_count: int = 0
    metrics_added: int = 0
    metrics_removed: int = 0
    metrics_modified: int = 0
    metrics_unchanged: int = 0
    dimensions_added: int = 0
    dimensions_removed: int = 0
    dimensions_modified: int = 0
    dimensions_unchanged: int = 0
    # Inventory diff counts (optional)
    source_calc_metrics_count: int = 0
    target_calc_metrics_count: int = 0
    calc_metrics_added: int = 0
    calc_metrics_removed: int = 0
    calc_metrics_modified: int = 0
    calc_metrics_unchanged: int = 0
    source_segments_count: int = 0
    target_segments_count: int = 0
    segments_added: int = 0
    segments_removed: int = 0
    segments_modified: int = 0
    segments_unchanged: int = 0

    @property
    def has_changes(self) -> bool:
        """Returns True if any changes were detected."""
        return (
            self.metrics_added > 0
            or self.metrics_removed > 0
            or self.metrics_modified > 0
            or self.dimensions_added > 0
            or self.dimensions_removed > 0
            or self.dimensions_modified > 0
            or self.has_inventory_changes
        )

    @property
    def has_inventory_changes(self) -> bool:
        """Returns True if any inventory changes were detected."""
        return (
            self.calc_metrics_added > 0
            or self.calc_metrics_removed > 0
            or self.calc_metrics_modified > 0
            or self.segments_added > 0
            or self.segments_removed > 0
            or self.segments_modified > 0
        )

    @property
    def total_changes(self) -> int:
        """Total number of changed items."""
        return (
            self.metrics_added
            + self.metrics_removed
            + self.metrics_modified
            + self.dimensions_added
            + self.dimensions_removed
            + self.dimensions_modified
        )

    @property
    def metrics_changed(self) -> int:
        """Total metrics that changed (added + removed + modified)."""
        return self.metrics_added + self.metrics_removed + self.metrics_modified

    @property
    def dimensions_changed(self) -> int:
        """Total dimensions that changed (added + removed + modified)."""
        return self.dimensions_added + self.dimensions_removed + self.dimensions_modified

    @property
    def metrics_change_percent(self) -> float:
        """Percentage of metrics that changed (based on max of source/target count)."""
        total = max(self.source_metrics_count, self.target_metrics_count)
        if total == 0:
            return 0.0
        return (self.metrics_changed / total) * 100

    @property
    def dimensions_change_percent(self) -> float:
        """Percentage of dimensions that changed (based on max of source/target count)."""
        total = max(self.source_dimensions_count, self.target_dimensions_count)
        if total == 0:
            return 0.0
        return (self.dimensions_changed / total) * 100

    @property
    def calc_metrics_changed(self) -> int:
        """Total calculated metrics that changed."""
        return self.calc_metrics_added + self.calc_metrics_removed + self.calc_metrics_modified

    @property
    def calc_metrics_change_percent(self) -> float:
        """Percentage of calculated metrics that changed."""
        total = max(self.source_calc_metrics_count, self.target_calc_metrics_count)
        if total == 0:
            return 0.0
        return (self.calc_metrics_changed / total) * 100

    @property
    def segments_changed(self) -> int:
        """Total segments that changed."""
        return self.segments_added + self.segments_removed + self.segments_modified

    @property
    def segments_change_percent(self) -> float:
        """Percentage of segments that changed."""
        total = max(self.source_segments_count, self.target_segments_count)
        if total == 0:
            return 0.0
        return (self.segments_changed / total) * 100

    @property
    def natural_language_summary(self) -> str:
        """Human-readable summary of changes for PRs, tickets, messages."""
        parts = []

        # Metrics changes
        metric_parts = []
        if self.metrics_added:
            metric_parts.append(f"{self.metrics_added} added")
        if self.metrics_removed:
            metric_parts.append(f"{self.metrics_removed} removed")
        if self.metrics_modified:
            metric_parts.append(f"{self.metrics_modified} modified")
        if metric_parts:
            parts.append(f"Metrics: {', '.join(metric_parts)}")

        # Dimensions changes
        dim_parts = []
        if self.dimensions_added:
            dim_parts.append(f"{self.dimensions_added} added")
        if self.dimensions_removed:
            dim_parts.append(f"{self.dimensions_removed} removed")
        if self.dimensions_modified:
            dim_parts.append(f"{self.dimensions_modified} modified")
        if dim_parts:
            parts.append(f"Dimensions: {', '.join(dim_parts)}")

        # Calculated metrics inventory changes
        calc_parts = []
        if self.calc_metrics_added:
            calc_parts.append(f"{self.calc_metrics_added} added")
        if self.calc_metrics_removed:
            calc_parts.append(f"{self.calc_metrics_removed} removed")
        if self.calc_metrics_modified:
            calc_parts.append(f"{self.calc_metrics_modified} modified")
        if calc_parts:
            parts.append(f"Calculated Metrics: {', '.join(calc_parts)}")

        # Segments inventory changes
        seg_parts = []
        if self.segments_added:
            seg_parts.append(f"{self.segments_added} added")
        if self.segments_removed:
            seg_parts.append(f"{self.segments_removed} removed")
        if self.segments_modified:
            seg_parts.append(f"{self.segments_modified} modified")
        if seg_parts:
            parts.append(f"Segments: {', '.join(seg_parts)}")

        if not parts:
            return "No changes detected"

        return "; ".join(parts)

    @property
    def total_added(self) -> int:
        """Total items added across all component types."""
        return self.metrics_added + self.dimensions_added + self.calc_metrics_added + self.segments_added

    @property
    def total_removed(self) -> int:
        """Total items removed across all component types."""
        return self.metrics_removed + self.dimensions_removed + self.calc_metrics_removed + self.segments_removed

    @property
    def total_modified(self) -> int:
        """Total items modified across all component types."""
        return self.metrics_modified + self.dimensions_modified + self.calc_metrics_modified + self.segments_modified

    @property
    def total_summary(self) -> str:
        """One-line summary of total changes: '3 added, 2 removed, 5 modified'."""
        if not self.has_changes:
            return "No changes"

        parts = []
        if self.total_added:
            parts.append(f"{self.total_added} added")
        if self.total_removed:
            parts.append(f"{self.total_removed} removed")
        if self.total_modified:
            parts.append(f"{self.total_modified} modified")

        return ", ".join(parts) if parts else "No changes"


@dataclass
class InventoryItemDiff:
    """Represents a diff for a single inventory item (calculated metric or segment)."""

    id: str
    name: str
    change_type: ChangeType
    inventory_type: str  # 'calculated_metric' or 'segment'
    source_data: dict | None = None
    target_data: dict | None = None
    changed_fields: dict[str, tuple[Any, Any]] | None = None

    def __post_init__(self):
        if self.changed_fields is None:
            self.changed_fields = {}


@dataclass
class DiffResult:
    """Complete result of a diff comparison."""

    summary: DiffSummary
    metadata_diff: MetadataDiff
    metric_diffs: list[ComponentDiff]
    dimension_diffs: list[ComponentDiff]
    source_label: str = "Source"
    target_label: str = "Target"
    generated_at: str = ""
    tool_version: str = ""
    # Inventory diffs (optional)
    calc_metrics_diffs: list[InventoryItemDiff] | None = None
    segments_diffs: list[InventoryItemDiff] | None = None

    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M:%S")
        if not self.tool_version:
            self.tool_version = __version__

    @property
    def has_inventory_diffs(self) -> bool:
        """Check if any inventory diffs are included."""
        return self.calc_metrics_diffs is not None or self.segments_diffs is not None


@dataclass
class DataViewSnapshot:
    """A point-in-time snapshot of a data view for comparison."""

    snapshot_version: str = "1.0"
    created_at: str = ""
    data_view_id: str = ""
    data_view_name: str = ""
    owner: str = ""
    description: str = ""
    metrics: list[dict] = None  # Full metric data from API
    dimensions: list[dict] = None  # Full dimension data from API
    metadata: dict = None  # Tool version, counts, etc.
    # Inventory data (optional, v2.0+)
    calculated_metrics_inventory: list[dict] | None = None
    segments_inventory: list[dict] | None = None

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now(UTC).isoformat()
        if self.metrics is None:
            self.metrics = []
        if self.dimensions is None:
            self.dimensions = []
        if self.metadata is None:
            self.metadata = {
                "tool_version": __version__,
                "metrics_count": len(self.metrics) if self.metrics else 0,
                "dimensions_count": len(self.dimensions) if self.dimensions else 0,
            }
        # Auto-upgrade version when inventory fields are explicitly included,
        # even when those arrays are empty.
        if self.calculated_metrics_inventory is not None or self.segments_inventory is not None:
            self.snapshot_version = "2.0"

    @property
    def has_calculated_metrics_inventory(self) -> bool:
        """Check if snapshot contains calculated metrics inventory."""
        return self.calculated_metrics_inventory is not None

    @property
    def has_segments_inventory(self) -> bool:
        """Check if snapshot contains segments inventory."""
        return self.segments_inventory is not None

    def get_inventory_summary(self) -> dict[str, Any]:
        """Get summary of what inventory data is present in the snapshot."""
        return {
            "calculated_metrics": {
                "present": self.has_calculated_metrics_inventory,
                "count": len(self.calculated_metrics_inventory) if self.calculated_metrics_inventory is not None else 0,
            },
            "segments": {
                "present": self.has_segments_inventory,
                "count": len(self.segments_inventory) if self.segments_inventory is not None else 0,
            },
        }

    def to_dict(self) -> dict:
        """Convert snapshot to dictionary for JSON serialization."""
        result = {
            "snapshot_version": self.snapshot_version,
            "created_at": self.created_at,
            "data_view_id": self.data_view_id,
            "data_view_name": self.data_view_name,
            "owner": self.owner,
            "description": self.description,
            "metrics": self.metrics,
            "dimensions": self.dimensions,
            "metadata": {
                "tool_version": self.metadata.get("tool_version", __version__),
                "metrics_count": len(self.metrics),
                "dimensions_count": len(self.dimensions),
            },
        }
        if self.calculated_metrics_inventory is not None:
            result["calculated_metrics_inventory"] = self.calculated_metrics_inventory
            result["metadata"]["calculated_metrics_count"] = len(self.calculated_metrics_inventory)
        if self.segments_inventory is not None:
            result["segments_inventory"] = self.segments_inventory
            result["metadata"]["segments_count"] = len(self.segments_inventory)
        return result

    @classmethod
    def from_dict(cls, data: dict) -> DataViewSnapshot:
        """Create snapshot from dictionary (loaded from JSON)."""
        return cls(
            snapshot_version=data.get("snapshot_version", "1.0"),
            created_at=data.get("created_at", ""),
            data_view_id=data.get("data_view_id", ""),
            data_view_name=data.get("data_view_name", ""),
            owner=data.get("owner", ""),
            description=data.get("description", ""),
            metrics=data.get("metrics", []),
            dimensions=data.get("dimensions", []),
            metadata=data.get("metadata", {}),
            calculated_metrics_inventory=data.get("calculated_metrics_inventory"),
            segments_inventory=data.get("segments_inventory"),
        )
