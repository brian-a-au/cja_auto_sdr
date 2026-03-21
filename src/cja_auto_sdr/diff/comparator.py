from __future__ import annotations

import logging
from typing import Any, ClassVar

import pandas as pd

from cja_auto_sdr.diff.models import (
    ChangeType,
    ComponentDiff,
    DataViewSnapshot,
    DiffResult,
    DiffSummary,
    InventoryItemDiff,
    MetadataDiff,
)


class DataViewComparator:
    """
    Compares two data view snapshots and produces a DiffResult.

    Supports comparing:
    - Two live data views
    - A live data view against a saved snapshot
    - Two saved snapshots
    """

    DEFAULT_COMPARE_FIELDS: ClassVar[list[str]] = ["name", "title", "description", "type", "schemaPath"]
    EXTENDED_COMPARE_FIELDS: ClassVar[list[str]] = [
        "name",
        "title",
        "description",
        "type",
        "schemaPath",
        "hidden",
        "hideFromReporting",
        "precision",
        "format",
        "segmentable",
        "reportable",
        "componentType",
        "attribution",
        "attributionModel",
        "lookbackWindow",
        "dataType",
        "hasData",
        "approved",
        "bucketing",
        "bucketingSetting",
        "persistence",
        "persistenceSetting",
        "allocation",
        "formula",
        "isCalculated",
        "derivedFieldId",
    ]

    CALC_METRICS_COMPARE_FIELDS: ClassVar[list[str]] = [
        "name",
        "description",
        "owner",
        "complexity_score",
        "approved",
        "functions_used",
        "formula_summary",
        "metric_references",
        "segment_references",
        "nesting_depth",
        "tags",
    ]

    SEGMENTS_COMPARE_FIELDS: ClassVar[list[str]] = [
        "name",
        "description",
        "owner",
        "complexity_score",
        "approved",
        "functions_used",
        "definition_summary",
        "metric_references",
        "segment_references",
        "dimension_references",
        "nesting_depth",
        "tags",
    ]
    DERIVED_FIELDS_COMPARE_FIELDS: ClassVar[list[str]] = [
        "name",
        "description",
        "owner",
        "complexity_score",
        "approved",
        "logic_summary",
        "dimension_references",
        "segment_references",
        "metric_references",
        "tags",
    ]
    ORDER_INSENSITIVE_LIST_FIELDS: ClassVar[set[str]] = {
        "functions_used",
        "metric_references",
        "segment_references",
        "dimension_references",
        "tags",
    }

    def __init__(
        self,
        logger: logging.Logger | None = None,
        ignore_fields: list[str] | None = None,
        compare_fields: list[str] | None = None,
        use_extended_fields: bool = False,
        show_only: list[str] | None = None,
        metrics_only: bool = False,
        dimensions_only: bool = False,
        include_calc_metrics: bool = False,
        include_segments: bool = False,
    ):
        self.logger = logger or logging.getLogger(__name__)
        self.ignore_fields = set(ignore_fields or [])
        if compare_fields:
            self.compare_fields = compare_fields
        elif use_extended_fields:
            self.compare_fields = self.EXTENDED_COMPARE_FIELDS
        else:
            self.compare_fields = self.DEFAULT_COMPARE_FIELDS
        self.show_only = set(show_only) if show_only else None
        self.metrics_only = metrics_only
        self.dimensions_only = dimensions_only
        self.include_calc_metrics = include_calc_metrics
        self.include_segments = include_segments

    def compare(
        self,
        source: DataViewSnapshot,
        target: DataViewSnapshot,
        source_label: str = "Source",
        target_label: str = "Target",
    ) -> DiffResult:
        self.logger.info("Comparing data views:")
        self.logger.info(f"  {source_label}: {source.data_view_name} ({source.data_view_id})")
        self.logger.info(f"  {target_label}: {target.data_view_name} ({target.data_view_id})")

        if self.dimensions_only:
            metric_diffs = []
        else:
            metric_diffs = self._compare_components(source.metrics, target.metrics, "metrics")
            metric_diffs = self._apply_show_only_filter(metric_diffs)

        if self.metrics_only:
            dimension_diffs = []
        else:
            dimension_diffs = self._compare_components(source.dimensions, target.dimensions, "dimensions")
            dimension_diffs = self._apply_show_only_filter(dimension_diffs)

        calc_metrics_diffs = None
        segments_diffs = None

        if self.include_calc_metrics:
            calc_metrics_diffs = self._compare_inventory_items(
                source.calculated_metrics_inventory or [],
                target.calculated_metrics_inventory or [],
                "calculated_metric",
                id_field="metric_id",
                name_field="metric_name",
            )
            self.logger.info(f"  Calculated Metrics: {self._count_changes(calc_metrics_diffs)}")

        if self.include_segments:
            segments_diffs = self._compare_inventory_items(
                source.segments_inventory or [],
                target.segments_inventory or [],
                "segment",
                id_field="segment_id",
                name_field="segment_name",
            )
            self.logger.info(f"  Segments: {self._count_changes(segments_diffs)}")

        metadata_diff = self._build_metadata_diff(source, target)

        summary = self._build_summary(source, target, metric_diffs, dimension_diffs, calc_metrics_diffs, segments_diffs)

        self.logger.info("Comparison complete:")
        self.logger.info(f"  Metrics: +{summary.metrics_added} -{summary.metrics_removed} ~{summary.metrics_modified}")
        self.logger.info(
            f"  Dimensions: +{summary.dimensions_added} -{summary.dimensions_removed} ~{summary.dimensions_modified}",
        )

        return DiffResult(
            summary=summary,
            metadata_diff=metadata_diff,
            metric_diffs=metric_diffs,
            dimension_diffs=dimension_diffs,
            source_label=source_label,
            target_label=target_label,
            calc_metrics_diffs=calc_metrics_diffs,
            segments_diffs=segments_diffs,
        )

    def _count_changes(self, diffs: list[InventoryItemDiff] | None) -> str:
        if not diffs:
            return "0 items"
        added = sum(1 for d in diffs if d.change_type == ChangeType.ADDED)
        removed = sum(1 for d in diffs if d.change_type == ChangeType.REMOVED)
        modified = sum(1 for d in diffs if d.change_type == ChangeType.MODIFIED)
        return f"+{added} -{removed} ~{modified}"

    def _compare_items_generic(
        self,
        source_list: list[dict],
        target_list: list[dict],
        id_field: str,
        name_extractor: callable,
        diff_factory: callable,
        find_changed_fields: callable,
    ) -> list:
        """Generic comparison logic for items identified by an ID field.

        Args:
            source_list: List of source items (dicts)
            target_list: List of target items (dicts)
            id_field: Field name to use as unique ID
            name_extractor: Function (item) -> name string
            diff_factory: Function (id, name, change_type, source, target, changed_fields) -> diff object
            find_changed_fields: Function (source_item, target_item) -> dict of changed fields

        Returns:
            List of diff objects created by diff_factory
        """
        diffs = []

        source_map = {item.get(id_field): item for item in source_list if item.get(id_field)}
        target_map = {item.get(id_field): item for item in target_list if item.get(id_field)}

        all_ids = set(source_map.keys()) | set(target_map.keys())

        for item_id in sorted(all_ids):
            source_item = source_map.get(item_id)
            target_item = target_map.get(item_id)

            if source_item and not target_item:
                diffs.append(
                    diff_factory(item_id, name_extractor(source_item), ChangeType.REMOVED, source_item, None, None),
                )
            elif target_item and not source_item:
                diffs.append(
                    diff_factory(item_id, name_extractor(target_item), ChangeType.ADDED, None, target_item, None),
                )
            else:
                changed_fields = find_changed_fields(source_item, target_item)
                change_type = ChangeType.MODIFIED if changed_fields else ChangeType.UNCHANGED
                diffs.append(
                    diff_factory(
                        item_id,
                        name_extractor(target_item),
                        change_type,
                        source_item,
                        target_item,
                        changed_fields,
                    ),
                )

        return diffs

    def _compare_inventory_items(
        self,
        source_list: list[dict],
        target_list: list[dict],
        inventory_type: str,
        id_field: str = "id",
        name_field: str = "name",
    ) -> list[InventoryItemDiff]:
        def name_extractor(item: dict) -> str:
            return item.get(name_field, "Unknown")

        def diff_factory(item_id, name, change_type, source, target, changed_fields):
            return InventoryItemDiff(
                id=item_id,
                name=name,
                change_type=change_type,
                inventory_type=inventory_type,
                source_data=source,
                target_data=target,
                changed_fields=changed_fields or {},
            )

        def find_changed(source_item, target_item):
            return self._find_inventory_changed_fields(source_item, target_item, inventory_type)

        return self._compare_items_generic(
            source_list,
            target_list,
            id_field,
            name_extractor,
            diff_factory,
            find_changed,
        )

    def _find_inventory_changed_fields(
        self,
        source: dict,
        target: dict,
        inventory_type: str,
    ) -> dict[str, tuple[Any, Any]]:
        changed = {}

        if inventory_type == "calculated_metric":
            compare_fields = self.CALC_METRICS_COMPARE_FIELDS
        elif inventory_type == "segment":
            compare_fields = self.SEGMENTS_COMPARE_FIELDS
        elif inventory_type == "derived_field":
            compare_fields = self.DERIVED_FIELDS_COMPARE_FIELDS
        else:
            compare_fields = self.CALC_METRICS_COMPARE_FIELDS

        for field in compare_fields:
            if field in self.ignore_fields:
                continue

            source_val = source.get(field)
            target_val = target.get(field)

            source_normalized = self._normalize_value(source_val, field_name=field)
            target_normalized = self._normalize_value(target_val, field_name=field)

            if source_normalized != target_normalized:
                changed[field] = (source_val, target_val)

        return changed

    def _apply_show_only_filter(self, diffs: list[ComponentDiff]) -> list[ComponentDiff]:
        if not self.show_only:
            return diffs

        type_map = {
            "added": ChangeType.ADDED,
            "removed": ChangeType.REMOVED,
            "modified": ChangeType.MODIFIED,
            "unchanged": ChangeType.UNCHANGED,
        }

        allowed_types = {type_map[t] for t in self.show_only if t in type_map}

        return [d for d in diffs if d.change_type in allowed_types]

    def _compare_components(
        self,
        source_list: list[dict],
        target_list: list[dict],
        _component_type: str,
    ) -> list[ComponentDiff]:
        def name_extractor(item: dict) -> str:
            return item.get("name", item.get("title", "Unknown"))

        def diff_factory(item_id, name, change_type, source, target, changed_fields):
            return ComponentDiff(
                id=item_id,
                name=name,
                change_type=change_type,
                source_data=source,
                target_data=target,
                changed_fields=changed_fields or {},
            )

        return self._compare_items_generic(
            source_list,
            target_list,
            "id",
            name_extractor,
            diff_factory,
            self._find_changed_fields,
        )

    def _find_changed_fields(self, source: dict, target: dict) -> dict[str, tuple[Any, Any]]:
        changed = {}

        for field in self.compare_fields:
            if field in self.ignore_fields:
                continue

            source_val = source.get(field)
            target_val = target.get(field)

            source_normalized = self._normalize_value(source_val, field_name=field)
            target_normalized = self._normalize_value(target_val, field_name=field)

            if source_normalized != target_normalized:
                changed[field] = (source_val, target_val)

        return changed

    def _normalize_value(self, value: Any, field_name: str | None = None) -> Any:
        if value is None:
            return ""
        try:
            if pd.isna(value):
                return ""
        except TypeError, ValueError:
            pass
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            return self._normalize_dict(value)
        if isinstance(value, list):
            normalized_list = [self._normalize_value(v) for v in value]
            if field_name in self.ORDER_INSENSITIVE_LIST_FIELDS:
                # Treat selected inventory-style lists as sets for stable comparison.
                return sorted(normalized_list, key=repr)
            return normalized_list
        return value

    def _normalize_dict(self, d: dict) -> dict:
        if not d:
            return {}
        result = {}
        for k, v in sorted(d.items()):
            normalized = self._normalize_value(v, field_name=k)
            if normalized != "" and normalized != {} and normalized != []:
                result[k] = normalized
        return result

    def _build_metadata_diff(self, source: DataViewSnapshot, target: DataViewSnapshot) -> MetadataDiff:
        changed_fields = {}

        if source.data_view_name != target.data_view_name:
            changed_fields["name"] = (source.data_view_name, target.data_view_name)
        if source.owner != target.owner:
            changed_fields["owner"] = (source.owner, target.owner)
        if source.description != target.description:
            changed_fields["description"] = (source.description, target.description)

        return MetadataDiff(
            source_name=source.data_view_name,
            target_name=target.data_view_name,
            source_id=source.data_view_id,
            target_id=target.data_view_id,
            source_owner=source.owner,
            target_owner=target.owner,
            source_description=source.description,
            target_description=target.description,
            changed_fields=changed_fields,
        )

    def _build_summary(
        self,
        source: DataViewSnapshot,
        target: DataViewSnapshot,
        metric_diffs: list[ComponentDiff],
        dimension_diffs: list[ComponentDiff],
        calc_metrics_diffs: list[InventoryItemDiff] | None = None,
        segments_diffs: list[InventoryItemDiff] | None = None,
    ) -> DiffSummary:
        summary = DiffSummary(
            source_metrics_count=len(source.metrics),
            target_metrics_count=len(target.metrics),
            source_dimensions_count=len(source.dimensions),
            target_dimensions_count=len(target.dimensions),
            metrics_added=sum(1 for d in metric_diffs if d.change_type == ChangeType.ADDED),
            metrics_removed=sum(1 for d in metric_diffs if d.change_type == ChangeType.REMOVED),
            metrics_modified=sum(1 for d in metric_diffs if d.change_type == ChangeType.MODIFIED),
            metrics_unchanged=sum(1 for d in metric_diffs if d.change_type == ChangeType.UNCHANGED),
            dimensions_added=sum(1 for d in dimension_diffs if d.change_type == ChangeType.ADDED),
            dimensions_removed=sum(1 for d in dimension_diffs if d.change_type == ChangeType.REMOVED),
            dimensions_modified=sum(1 for d in dimension_diffs if d.change_type == ChangeType.MODIFIED),
            dimensions_unchanged=sum(1 for d in dimension_diffs if d.change_type == ChangeType.UNCHANGED),
        )

        if calc_metrics_diffs is not None:
            summary.source_calc_metrics_count = len(source.calculated_metrics_inventory or [])
            summary.target_calc_metrics_count = len(target.calculated_metrics_inventory or [])
            summary.calc_metrics_added = sum(1 for d in calc_metrics_diffs if d.change_type == ChangeType.ADDED)
            summary.calc_metrics_removed = sum(1 for d in calc_metrics_diffs if d.change_type == ChangeType.REMOVED)
            summary.calc_metrics_modified = sum(1 for d in calc_metrics_diffs if d.change_type == ChangeType.MODIFIED)
            summary.calc_metrics_unchanged = sum(1 for d in calc_metrics_diffs if d.change_type == ChangeType.UNCHANGED)

        if segments_diffs is not None:
            summary.source_segments_count = len(source.segments_inventory or [])
            summary.target_segments_count = len(target.segments_inventory or [])
            summary.segments_added = sum(1 for d in segments_diffs if d.change_type == ChangeType.ADDED)
            summary.segments_removed = sum(1 for d in segments_diffs if d.change_type == ChangeType.REMOVED)
            summary.segments_modified = sum(1 for d in segments_diffs if d.change_type == ChangeType.MODIFIED)
            summary.segments_unchanged = sum(1 for d in segments_diffs if d.change_type == ChangeType.UNCHANGED)

        return summary
