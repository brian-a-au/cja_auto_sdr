from __future__ import annotations

import json
import logging
import os
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from cja_auto_sdr.api.fetch import classify_component_payload
from cja_auto_sdr.core.colors import ConsoleColors
from cja_auto_sdr.core.discovery_payloads import (
    TOLERATED_LEGACY_LOOKUP_REASONS,
    PayloadKind,
    assess_dataview_lookup_payload,
)
from cja_auto_sdr.core.error_policies import RECOVERABLE_OPTIONAL_ENRICHMENT_EXCEPTIONS
from cja_auto_sdr.core.exceptions import attach_api_connection_hint_context
from cja_auto_sdr.core.json_io import write_json_atomic
from cja_auto_sdr.diff.models import DataViewSnapshot

_SNAPSHOT_FAILURE_STAGE_ATTR = "_cja_snapshot_failure_stage"


def _annotate_snapshot_failure(exc: Exception, *, stage: str, api_hint_context: str | None = None) -> Exception:
    """Attach snapshot-stage metadata to *exc* so callers can emit accurate hints."""
    setattr(exc, _SNAPSHOT_FAILURE_STAGE_ATTR, stage)
    return attach_api_connection_hint_context(exc, context=api_hint_context)


class SnapshotManager:
    """
    Manages data view snapshot lifecycle.

    Handles creating snapshots from live data views, saving/loading to JSON files,
    and listing available snapshots.
    """

    def __init__(self, logger: logging.Logger | None = None):
        self.logger = logger or logging.getLogger(__name__)

    @staticmethod
    def _default_snapshot_timezone():
        """Return a DST-aware local timezone for legacy naive snapshot timestamps."""
        tz_env = os.environ.get("TZ", "").strip()
        if tz_env:
            try:
                return ZoneInfo(tz_env)
            except ZoneInfoNotFoundError:
                pass

        try:
            return ZoneInfo("localtime")
        except ZoneInfoNotFoundError:
            pass

        for localtime_path in ("/etc/localtime", "/var/db/timezone/zoneinfo/localtime"):
            if not os.path.exists(localtime_path):
                continue
            try:
                with open(localtime_path, "rb") as tz_file:
                    return ZoneInfo.from_file(tz_file)
            except OSError:
                continue

        return datetime.now().astimezone().tzinfo or UTC

    def _parse_snapshot_created_at(self, created_at: str | None) -> datetime | None:
        """Parse snapshot created_at into UTC datetime.

        Legacy snapshots may store naive ISO timestamps (no offset). These are
        interpreted as local time for backwards compatibility, then normalized
        to UTC for ordering/comparison.
        """
        timestamp = (created_at or "").strip()
        if not timestamp:
            return None

        normalized = f"{timestamp[:-1]}+00:00" if timestamp.endswith("Z") else timestamp

        try:
            parsed = datetime.fromisoformat(normalized)
        except ValueError:
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=self._default_snapshot_timezone())

        return parsed.astimezone(UTC)

    def _snapshot_created_at_utc(self, snapshot: dict) -> datetime | None:
        """Resolve snapshot created_at to UTC datetime with mtime fallback."""
        parsed = self._parse_snapshot_created_at(snapshot.get("created_at", ""))
        if parsed is not None:
            return parsed

        filepath = snapshot.get("filepath")
        if filepath and os.path.exists(filepath):
            try:
                return datetime.fromtimestamp(os.path.getmtime(filepath), UTC)
            except OSError:
                return None
        return None

    def _snapshot_sort_key(self, snapshot: dict) -> datetime:
        """Sort key for snapshots by normalized UTC created_at."""
        created_at = self._snapshot_created_at_utc(snapshot)
        return created_at if created_at is not None else datetime.min.replace(tzinfo=UTC)

    def create_snapshot(
        self,
        cja,
        data_view_id: str,
        quiet: bool = False,
        include_calculated_metrics: bool = False,
        include_segments: bool = False,
    ) -> DataViewSnapshot:
        """Create a snapshot from a live data view."""
        self.logger.info(f"Creating snapshot for data view: {data_view_id}")

        try:
            raw_dv_info = cja.getDataView(data_view_id)
        except Exception as exc:
            raise _annotate_snapshot_failure(
                exc,
                stage="data_view_lookup",
                api_hint_context="data_view_lookup",
            ) from exc

        lookup_assessment = assess_dataview_lookup_payload(raw_dv_info, expected_data_view_id=data_view_id)
        legacy_acceptable_dict = (
            isinstance(raw_dv_info, dict)
            and lookup_assessment.kind is PayloadKind.ERROR
            and lookup_assessment.reason in TOLERATED_LEGACY_LOOKUP_REASONS
        )
        if not lookup_assessment.is_valid and not legacy_acceptable_dict:
            detail = ""
            if isinstance(raw_dv_info, dict):
                detail = str(
                    raw_dv_info.get("message") or raw_dv_info.get("error") or raw_dv_info.get("statusCode") or ""
                )
            if lookup_assessment.kind is PayloadKind.EMPTY:
                detail = f"Failed to fetch data view info for {data_view_id}"
            raise _annotate_snapshot_failure(
                ValueError(
                    f"Data view lookup returned {lookup_assessment.kind.value} payload "
                    f"({lookup_assessment.reason}): {detail}".rstrip(": ")
                ),
                stage="data_view_lookup",
                api_hint_context="data_view_lookup",
            )

        dv_info = lookup_assessment.payload or {}
        dv_name = dv_info.get("name", "Unknown")
        dv_owner = dv_info.get("owner", {})
        owner_name = dv_owner.get("name", "") if isinstance(dv_owner, dict) else str(dv_owner)
        dv_description = dv_info.get("description", "")

        self.logger.info("Fetching metrics...")
        try:
            raw_metrics = cja.getMetrics(data_view_id, inclType=True, full=True)
        except Exception as exc:
            raise _annotate_snapshot_failure(exc, stage="metrics_fetch") from exc

        metrics_outcome = classify_component_payload(raw_metrics)
        # Duck-typing shim for pre-classification cjapy DataFrame returns; unwrap without the classifier.
        legacy_metrics_like_frame = (
            metrics_outcome.status == "failed"
            and metrics_outcome.reason == "unsupported_payload_type"
            and hasattr(raw_metrics, "empty")
            and hasattr(raw_metrics, "to_dict")
        )
        if metrics_outcome.status == "failed" and not legacy_metrics_like_frame:
            raise _annotate_snapshot_failure(
                ValueError(
                    f"Metrics fetch returned error payload ({metrics_outcome.reason}): {metrics_outcome.error_message}"
                ),
                stage="metrics_fetch",
            )
        if legacy_metrics_like_frame:
            metrics_list = raw_metrics.to_dict("records") if not raw_metrics.empty else []
        else:
            metrics_list = metrics_outcome.frame.to_dict("records") if not metrics_outcome.frame.empty else []
        self.logger.info(f"  Fetched {len(metrics_list)} metrics")

        self.logger.info("Fetching dimensions...")
        try:
            raw_dimensions = cja.getDimensions(data_view_id, inclType=True, full=True)
        except Exception as exc:
            raise _annotate_snapshot_failure(exc, stage="dimensions_fetch") from exc
        dimensions_outcome = classify_component_payload(raw_dimensions)
        legacy_dimensions_like_frame = (
            dimensions_outcome.status == "failed"
            and dimensions_outcome.reason == "unsupported_payload_type"
            and hasattr(raw_dimensions, "empty")
            and hasattr(raw_dimensions, "to_dict")
        )
        if dimensions_outcome.status == "failed" and not legacy_dimensions_like_frame:
            raise _annotate_snapshot_failure(
                ValueError(
                    f"Dimensions fetch returned error payload "
                    f"({dimensions_outcome.reason}): {dimensions_outcome.error_message}"
                ),
                stage="dimensions_fetch",
            )
        if legacy_dimensions_like_frame:
            dimensions_list = raw_dimensions.to_dict("records") if not raw_dimensions.empty else []
        else:
            dimensions_list = dimensions_outcome.frame.to_dict("records") if not dimensions_outcome.frame.empty else []
        self.logger.info(f"  Fetched {len(dimensions_list)} dimensions")

        snapshot = DataViewSnapshot(
            data_view_id=data_view_id,
            data_view_name=dv_name,
            owner=owner_name,
            description=dv_description,
            metrics=metrics_list,
            dimensions=dimensions_list,
        )

        if include_calculated_metrics:
            if not quiet:
                print("Fetching calculated metrics inventory...")
            try:
                from cja_auto_sdr.inventory.calculated_metrics import CalculatedMetricsInventoryBuilder

                builder = CalculatedMetricsInventoryBuilder(logger=self.logger)
                inventory = builder.build(cja, data_view_id, dv_name)
                snapshot.calculated_metrics_inventory = [m.to_full_dict() for m in inventory.metrics]
                self.logger.info(f"  Fetched {len(snapshot.calculated_metrics_inventory)} calculated metrics")
                if not quiet:
                    print(f"  Calculated metrics: {len(snapshot.calculated_metrics_inventory)} items")
            except ImportError as e:
                self.logger.warning(f"Could not import calculated metrics inventory module: {e}")
                if not quiet:
                    print(ConsoleColors.warning("  Warning: Calculated metrics module not available"))
            except RECOVERABLE_OPTIONAL_ENRICHMENT_EXCEPTIONS as e:
                self.logger.warning(f"Failed to fetch calculated metrics inventory: {e}")
                if not quiet:
                    print(ConsoleColors.warning(f"  Warning: Could not fetch calculated metrics: {e}"))

        if include_segments:
            if not quiet:
                print("Fetching segments inventory...")
            try:
                from cja_auto_sdr.inventory.segments import SegmentsInventoryBuilder

                builder = SegmentsInventoryBuilder(logger=self.logger)
                inventory = builder.build(cja, data_view_id, dv_name)
                snapshot.segments_inventory = [s.to_full_dict() for s in inventory.segments]
                self.logger.info(f"  Fetched {len(snapshot.segments_inventory)} segments")
                if not quiet:
                    print(f"  Segments: {len(snapshot.segments_inventory)} items")
            except ImportError as e:
                self.logger.warning(f"Could not import segments inventory module: {e}")
                if not quiet:
                    print(ConsoleColors.warning("  Warning: Segments module not available"))
            except RECOVERABLE_OPTIONAL_ENRICHMENT_EXCEPTIONS as e:
                self.logger.warning(f"Failed to fetch segments inventory: {e}")
                if not quiet:
                    print(ConsoleColors.warning(f"  Warning: Could not fetch segments: {e}"))

        self.logger.info(f"Snapshot created: {len(metrics_list)} metrics, {len(dimensions_list)} dimensions")
        return snapshot

    def save_snapshot(self, snapshot: DataViewSnapshot, filepath: str) -> str:
        """Save a snapshot to a JSON file."""
        filepath = os.path.abspath(filepath)
        write_json_atomic(filepath, snapshot.to_dict(), indent=2, ensure_ascii=False)

        self.logger.info(f"Snapshot saved to: {filepath}")
        return filepath

    def load_snapshot(self, filepath: str) -> DataViewSnapshot:
        """Load a snapshot from a JSON file."""
        filepath = os.path.abspath(filepath)

        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Snapshot file not found: {filepath}")

        with open(filepath, encoding="utf-8") as f:
            data = json.load(f)

        if "snapshot_version" not in data:
            raise ValueError(f"Invalid snapshot file: {filepath} (missing snapshot_version)")

        snapshot = DataViewSnapshot.from_dict(data)
        self.logger.info(f"Loaded snapshot: {snapshot.data_view_name} ({snapshot.data_view_id})")
        self.logger.info(f"  Created: {snapshot.created_at}")
        self.logger.info(f"  Metrics: {len(snapshot.metrics)}, Dimensions: {len(snapshot.dimensions)}")

        return snapshot

    def list_snapshots(self, directory: str) -> list[dict]:
        """List available snapshots in a directory."""
        snapshots = []
        directory = os.path.abspath(directory)

        if not os.path.exists(directory):
            return snapshots

        for filename in os.listdir(directory):
            if filename.endswith(".json"):
                filepath = os.path.join(directory, filename)
                try:
                    with open(filepath, encoding="utf-8") as f:
                        data = json.load(f)
                    if "snapshot_version" in data:
                        snapshots.append(
                            {
                                "filename": filename,
                                "filepath": filepath,
                                "data_view_id": data.get("data_view_id", ""),
                                "data_view_name": data.get("data_view_name", ""),
                                "created_at": data.get("created_at", ""),
                                "metrics_count": len(data.get("metrics", [])),
                                "dimensions_count": len(data.get("dimensions", [])),
                            },
                        )
                except OSError, json.JSONDecodeError:
                    continue

        return sorted(snapshots, key=self._snapshot_sort_key, reverse=True)

    def get_most_recent_snapshot(self, directory: str, data_view_id: str) -> str | None:
        """Get the filepath of the most recent snapshot for a specific data view."""
        all_snapshots = self.list_snapshots(directory)
        dv_snapshots = [s for s in all_snapshots if s.get("data_view_id") == data_view_id]

        if not dv_snapshots:
            return None

        return dv_snapshots[0].get("filepath")

    def apply_retention_policy(self, directory: str, data_view_id: str, keep_last: int) -> list[str]:
        """Apply retention policy by deleting old snapshots for a specific data view."""
        if keep_last <= 0:
            return []

        all_snapshots = self.list_snapshots(directory)
        dv_snapshots = [s for s in all_snapshots if s.get("data_view_id") == data_view_id]

        if len(dv_snapshots) <= keep_last:
            return []

        deleted = []
        for snapshot in dv_snapshots[keep_last:]:
            filepath = snapshot.get("filepath")
            if filepath and os.path.exists(filepath):
                try:
                    os.remove(filepath)
                    self.logger.info(f"Retention policy: Deleted old snapshot {filepath}")
                    deleted.append(filepath)
                except OSError as e:
                    self.logger.warning(f"Failed to delete snapshot {filepath}: {e}")

        return deleted

    def apply_date_retention_policy(
        self,
        directory: str,
        data_view_id: str,
        keep_since_days: int | None = None,
        delete_older_than_days: int | None = None,
    ) -> list[str]:
        """Apply date-based retention policy by deleting snapshots outside the time window."""
        days = keep_since_days or delete_older_than_days
        if not days or days <= 0:
            return []

        cutoff_date = datetime.now(UTC) - timedelta(days=days)

        all_snapshots = self.list_snapshots(directory)

        if data_view_id and data_view_id != "*":
            snapshots_to_check = [s for s in all_snapshots if s.get("data_view_id") == data_view_id]
        else:
            snapshots_to_check = all_snapshots

        deleted = []
        for snapshot in snapshots_to_check:
            snapshot_created_at = self._snapshot_created_at_utc(snapshot)
            if snapshot_created_at is None:
                continue

            if snapshot_created_at < cutoff_date:
                filepath = snapshot.get("filepath")
                if filepath and os.path.exists(filepath):
                    try:
                        os.remove(filepath)
                        self.logger.info(f"Date retention policy: Deleted snapshot older than {days} days: {filepath}")
                        deleted.append(filepath)
                    except OSError as e:
                        self.logger.warning(f"Failed to delete snapshot {filepath}: {e}")

        if deleted:
            self.logger.info(f"Date retention: Deleted {len(deleted)} snapshot(s) older than {days} days")

        return deleted

    def generate_snapshot_filename(self, data_view_id: str, data_view_name: str | None = None) -> str:
        """Generate a timestamped filename for auto-saved snapshots."""
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        if data_view_name:
            safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in data_view_name)
            safe_name = safe_name[:50]
            return f"{safe_name}_{data_view_id}_{timestamp}.json"
        return f"{data_view_id}_{timestamp}.json"


def parse_retention_period(period_str: str) -> int | None:
    """
    Parse a retention period string into days.

    Supports formats:
    - '7d' or '7D' - 7 days
    - '2w' or '2W' - 2 weeks (14 days)
    - '1m' or '1M' - 1 month (30 days)
    - '30' - 30 days (plain number)
    """
    if not period_str:
        return None

    period_str = period_str.strip().lower()

    if period_str.isdigit():
        return int(period_str)

    try:
        if period_str.endswith("d"):
            return int(period_str[:-1])
        if period_str.endswith("w"):
            return int(period_str[:-1]) * 7
        if period_str.endswith("m"):
            return int(period_str[:-1]) * 30
    except ValueError:
        pass

    return None


_DURATION_UNIT_SECONDS = {"h": 3600, "d": 86_400, "w": 604_800}


def parse_duration_seconds(period_str: str) -> int | None:
    """Parse an Nh/Nd/Nw duration string to whole seconds.

    Returns None for any input that does not match exactly `<positive-int><h|d|w>`.
    Whitespace, decimals, zero, and negative values are rejected.
    """
    if not period_str or len(period_str) < 2:
        return None
    unit = period_str[-1]
    if unit not in _DURATION_UNIT_SECONDS:
        return None
    head = period_str[:-1]
    if not head.isascii() or not head.isdigit():  # rejects "-1", "1.5", " 1", "", and Unicode digits
        return None
    n = int(head)
    if n <= 0:
        return None
    return n * _DURATION_UNIT_SECONDS[unit]
