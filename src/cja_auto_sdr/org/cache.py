"""
Org-wide report caching functionality.

This module provides caching for data view component data to speed up
repeat analysis runs, and a lock mechanism to prevent concurrent runs.
"""

from __future__ import annotations

import contextlib
import errno
import json
import logging
import math
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from cja_auto_sdr.core.json_io import load_json_cached, write_json_atomic
from cja_auto_sdr.core.locks.manager import LockManager, normalize_lock_stale_threshold_seconds
from cja_auto_sdr.org.models import DataViewSummary
from cja_auto_sdr.org.snapshot_utils import (
    ORG_REPORT_SNAPSHOT_ROOT_DIRNAME,
    is_org_report_snapshot_payload,
    iter_org_report_snapshot_files,
    newest_first_snapshot_sort_fields,
    org_report_snapshot_content_hash,
    org_report_snapshot_dedupe_key,
    org_report_snapshot_dir_key,
    org_report_snapshot_dir_paths,
    org_report_snapshot_history_assessment,
    org_report_snapshot_metadata,
    org_report_snapshot_preference_key,
    snapshot_path_text,
    snapshot_slug,
)

DEFAULT_ORG_REPORT_SNAPSHOT_KEEP_LAST = 25


class OrgReportLock:
    """Cross-process lock to prevent concurrent org-report runs for one org.

    Ownership is determined by backend lock primitives (OS advisory lock
    by default). File metadata is diagnostic only and does not decide lock
    ownership.

    Usage:
        with OrgReportLock(org_id) as lock:
            if not lock.acquired:
                print("Another org-report is running")
                return
            # ... run analysis ...

    Args:
        org_id: Organization ID to lock
        lock_dir: Directory for lock files. Defaults to ~/.cja_auto_sdr/locks/
        stale_threshold_seconds: Lease staleness for fallback backend heartbeat/recovery.
        lock_backend: Optional backend override ("auto", "fcntl", "lease")
    """

    def __init__(
        self,
        org_id: str,
        lock_dir: Path | None = None,
        stale_threshold_seconds: int = 3600,
        lock_backend: str | None = None,
    ):
        if lock_dir is None:
            lock_dir = Path.home() / ".cja_auto_sdr" / "locks"
        self.lock_dir = lock_dir
        # Sanitize org_id for filename (keep only safe chars)
        import re

        safe_org_id = re.sub(r"[^a-zA-Z0-9_-]", "_", org_id)
        self.lock_file = lock_dir / f"org_report_{safe_org_id}.lock"
        normalized_stale_threshold_seconds = normalize_lock_stale_threshold_seconds(stale_threshold_seconds)
        self.stale_threshold = normalized_stale_threshold_seconds
        self.acquired = False
        self._manager = LockManager(
            lock_path=self.lock_file,
            owner=org_id,
            stale_threshold_seconds=normalized_stale_threshold_seconds,
            backend_name=lock_backend,
        )

    def __enter__(self) -> OrgReportLock:
        self.acquired = self._try_acquire()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.acquired:
            self._release()

    def _try_acquire(self) -> bool:
        """Attempt to acquire lock non-blocking."""
        return self._manager.acquire()

    def _release(self) -> None:
        """Release lock if currently held by this process."""
        self._manager.release()

    @property
    def lock_lost(self) -> bool:
        return self._manager.lock_lost

    @property
    def backend_name(self) -> str:
        return self._manager.backend_name

    def ensure_healthy(self) -> None:
        """Raise if lock ownership has been lost during execution."""
        self._manager.ensure_held()

    @staticmethod
    def _is_process_running(pid: int) -> bool:
        """Legacy helper kept for compatibility with existing tests."""
        if isinstance(pid, bool):
            return False
        try:
            normalized_pid = int(pid)
        except TypeError, ValueError, OverflowError:
            return False
        if normalized_pid <= 0:
            return False
        try:
            os.kill(normalized_pid, 0)  # Signal 0 doesn't kill, just checks
            return True
        except ProcessLookupError:
            return False
        except PermissionError:
            # EPERM means the process exists but we do not have permission to signal it.
            return True
        except OverflowError:
            return False
        except OSError as e:
            return e.errno == errno.EPERM

    def get_lock_info(self) -> dict[str, Any] | None:
        """Get information about the current lock holder.

        Returns:
            Dict with pid, timestamp, started_at or None if no lock
        """
        return self._manager.read_info()


class OrgReportCache:
    """Cache for org-wide report data view components.

    Stores fetched DataViewSummary objects to disk for faster repeat runs.
    Cache is JSON-based and stores component IDs, counts, and metadata.
    """

    def __init__(self, cache_dir: Path | None = None, logger: logging.Logger | None = None):
        """Initialize the cache.

        Args:
            cache_dir: Directory for cache files. Defaults to ~/.cja_auto_sdr/cache/
            logger: Optional logger for cache load/save warnings
        """
        if cache_dir is None:
            cache_dir = Path.home() / ".cja_auto_sdr" / "cache"
        self.cache_dir = cache_dir
        self.cache_file = cache_dir / "org_report_cache.json"
        self.logger = logger or logging.getLogger(__name__)
        self._cache: dict[str, dict[str, Any]] = {}
        self._load_cache()

    def _load_cache(self) -> None:
        """Load cache from disk."""
        if self.cache_file.exists():
            try:
                with open(self.cache_file, encoding="utf-8") as f:
                    payload = json.load(f)
            except (OSError, ValueError) as e:
                # Includes invalid UTF-8/JSON and the JSON integer decoding limit.
                self.logger.warning("Failed to load org report cache from %s: %s", self.cache_file, type(e).__name__)
                self._cache = {}
                return
            if isinstance(payload, dict):
                self._cache = payload
            else:
                self.logger.warning("Ignoring org report cache with invalid root shape at %s", self.cache_file)
                self._cache = {}

    @staticmethod
    def _entry_validation_error(dv_id: str, entry: Any) -> str | None:
        """Identify malformed consumed fields without coercing values or exposing contents.

        Absent legacy fields retain the defaults used by get(); unknown additive
        fields are ignored. Validation tokens are opaque, unlike the cache age.
        """
        if not isinstance(entry, dict):
            return "entry shape"
        if "data_view_id" in entry and entry["data_view_id"] != dv_id:
            return "data_view_id"
        for field in ("data_view_name", "status"):
            if field in entry and not isinstance(entry[field], str):
                return field
        for field in ("metric_ids", "dimension_ids"):
            if field in entry and (
                not isinstance(entry[field], list) or not all(isinstance(value, str) for value in entry[field])
            ):
                return field
        for field in (
            "metric_count",
            "dimension_count",
            "standard_metric_count",
            "derived_metric_count",
            "standard_dimension_count",
            "derived_dimension_count",
        ):
            if field in entry and (type(entry[field]) is not int or entry[field] < 0):
                return field
        if "fetch_duration" in entry:
            duration = entry["fetch_duration"]
            if type(duration) not in (int, float) or duration < 0:
                return "fetch_duration"
            try:
                if not math.isfinite(duration):
                    return "fetch_duration"
            except OverflowError:
                return "fetch_duration"
        for field in ("metric_names", "dimension_names"):
            names = entry.get(field)
            if names is not None and (
                not isinstance(names, dict)
                or not all(isinstance(key, str) and isinstance(value, str) for key, value in names.items())
            ):
                return field
        for field in ("error", "owner", "owner_id", "created", "modified", "description", "validation_modified"):
            if entry.get(field) is not None and not isinstance(entry[field], str):
                return field
        for field in ("has_description", "include_names", "include_metadata", "include_component_types"):
            if field in entry and not isinstance(entry[field], bool):
                return field
        fetched_at = entry.get("fetched_at")
        if not isinstance(fetched_at, str):
            return "fetched_at"
        try:
            if datetime.fromisoformat(fetched_at).tzinfo is None:
                return "fetched_at"
        except ValueError:
            return "fetched_at"
        return None

    def _get_entry(self, dv_id: str) -> dict[str, Any] | None:
        """Return a usable entry, evicting only malformed data and warning once."""
        if dv_id not in self._cache:
            return None
        entry = self._cache[dv_id]
        invalid_field = self._entry_validation_error(dv_id, entry)
        if invalid_field is not None:
            self.logger.warning("Ignoring malformed org report cache entry for %s: invalid %s", dv_id, invalid_field)
            del self._cache[dv_id]
            return None
        return entry

    def _save_cache(self) -> None:
        """Save cache to disk via atomic write-then-rename."""
        try:
            write_json_atomic(self.cache_file, self._cache, indent=2, default=str)
        except OSError as e:
            self.logger.warning("Failed to save org report cache to %s: %s", self.cache_file, e)

    @staticmethod
    def _sanitize_org_id(org_id: str | None) -> str:
        """Return a filesystem-safe org identifier."""
        return snapshot_slug(org_id)

    def get_org_report_snapshot_dir(self, org_id: str | None = None) -> Path:
        """Return the persistent snapshot directory for org-report trending history."""
        return self.get_org_report_snapshot_root_dir() / org_report_snapshot_dir_key(org_id)

    def _iter_org_report_snapshot_dirs(self, org_id: str | None = None) -> list[Path]:
        """Return snapshot directories to scan, including legacy layouts for one org."""
        return list(org_report_snapshot_dir_paths(self.get_org_report_snapshot_root_dir(), org_id=org_id))

    def get_org_report_snapshot_root_dir(self) -> Path:
        """Return the root directory containing per-org snapshot history."""
        return self.cache_dir / ORG_REPORT_SNAPSHOT_ROOT_DIRNAME

    def save_org_report_snapshot(self, report_data: dict[str, Any], org_id: str | None = None) -> Path:
        """Persist an org-report JSON payload for future trending windows."""
        if not is_org_report_snapshot_payload(report_data):
            raise ValueError("Invalid org-report snapshot payload")

        resolved_org_id = org_id or str(report_data.get("org_id") or "unknown")
        snapshot_dir = self.get_org_report_snapshot_dir(resolved_org_id)
        snapshot_dir.mkdir(parents=True, exist_ok=True)

        timestamp = str(report_data.get("generated_at") or datetime.now(UTC).isoformat())
        timestamp_slug = snapshot_slug(timestamp, fallback="snapshot")
        snapshot_id = uuid.uuid4().hex
        history_assessment = org_report_snapshot_history_assessment(report_data)
        payload = dict(report_data)
        payload["_snapshot_meta"] = {
            "snapshot_id": snapshot_id,
            "content_hash": org_report_snapshot_content_hash(report_data),
            "history_eligible": history_assessment.eligible,
            "history_exclusion_reason": history_assessment.exclusion_reason,
        }
        file_path = snapshot_dir / (
            f"org_report_{self._sanitize_org_id(resolved_org_id)}_{timestamp_slug}_{snapshot_id[:8]}.json"
        )
        try:
            write_json_atomic(file_path, payload, indent=2, ensure_ascii=False)
        except OSError, TypeError, ValueError:
            raise

        return file_path

    @staticmethod
    def _snapshot_metadata_sort_key(snapshot: dict[str, Any]) -> tuple[bool, float, str, str]:
        """Return a stable newest-first sort key for snapshot metadata."""
        return newest_first_snapshot_sort_fields(
            snapshot.get("generated_at"),
            tie_breaker=str(snapshot.get("filepath", "")),
        )

    @classmethod
    def _sort_snapshot_metadata(cls, snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Sort snapshot metadata newest-first with undated entries at the end."""
        return sorted(snapshots, key=cls._snapshot_metadata_sort_key)

    @staticmethod
    def _snapshot_counts_against_keep_last(snapshot: dict[str, Any]) -> bool:
        """Return True when a persisted snapshot should consume keep-last quota."""
        return bool(snapshot.get("filepath"))

    @classmethod
    def _retained_keep_last_paths(
        cls,
        snapshots: list[dict[str, Any]],
        *,
        keep_last: int,
    ) -> set[str]:
        """Return normalized paths for snapshots protected by keep-last retention."""
        if keep_last <= 0:
            return set()

        counted_snapshots = [snapshot for snapshot in snapshots if cls._snapshot_counts_against_keep_last(snapshot)]
        return {
            snapshot_path_text(snapshot.get("filepath"))
            for snapshot in counted_snapshots[:keep_last]
            if snapshot.get("filepath")
        }

    @staticmethod
    def _should_retain_snapshot(
        snapshot: dict[str, Any],
        *,
        retained_paths: set[str],
        cutoff: datetime | None,
    ) -> bool:
        """Return True when a snapshot satisfies at least one retention rule."""
        filepath = snapshot_path_text(snapshot.get("filepath"))
        if filepath and filepath in retained_paths:
            return True
        if cutoff is None:
            return False

        snapshot_epoch = snapshot.get("generated_at_epoch")
        if snapshot_epoch is None:
            return False
        return datetime.fromtimestamp(snapshot_epoch, tz=UTC) >= cutoff

    def _load_org_report_snapshot_metadata(
        self,
        snapshot_file: str | Path,
        *,
        include_data_views: bool = False,
    ) -> dict[str, Any] | None:
        """Load one persisted org-report snapshot and return summarized metadata."""
        path = Path(snapshot_file)
        try:
            payload = load_json_cached(path)
        except (OSError, ValueError) as exc:
            self.logger.warning("Skipping org-report snapshot %s: %s", path, exc)
            return None

        if not isinstance(payload, dict):
            self.logger.warning("Skipping org-report snapshot %s: expected JSON object", path)
            return None

        metadata = org_report_snapshot_metadata(payload, source_path=path, include_data_views=include_data_views)
        if metadata is None:
            self.logger.warning("Skipping org-report snapshot %s: expected org-report snapshot payload", path)
            return None
        return metadata

    @staticmethod
    def _snapshot_identity_key(snapshot: dict[str, Any]) -> tuple[str, ...]:
        """Return the logical identity for one persisted snapshot."""
        return org_report_snapshot_dedupe_key(
            org_id=snapshot.get("org_id"),
            content_hash=snapshot.get("content_hash"),
            snapshot_id=snapshot.get("snapshot_id"),
            generated_at=snapshot.get("generated_at"),
            source_path=snapshot.get("filepath"),
        )

    @staticmethod
    def _snapshot_preference_key(snapshot: dict[str, Any]) -> tuple[int, int]:
        """Return how strongly one physical snapshot copy should be preferred."""
        return org_report_snapshot_preference_key(
            org_id=snapshot.get("org_id"),
            source_path=snapshot.get("filepath"),
            snapshot_id=snapshot.get("snapshot_id"),
        )

    @classmethod
    def _canonical_snapshot_metadata(cls, snapshots: list[dict[str, Any]]) -> dict[str, Any]:
        """Return the preferred physical copy for one logical snapshot."""
        preferred_snapshot = snapshots[0]
        preferred_key = cls._snapshot_preference_key(preferred_snapshot)
        for snapshot in snapshots[1:]:
            snapshot_key = cls._snapshot_preference_key(snapshot)
            if snapshot_key > preferred_key:
                preferred_snapshot = snapshot
                preferred_key = snapshot_key
        return preferred_snapshot

    @classmethod
    def _group_snapshot_metadata_by_identity(
        cls,
        snapshots: list[dict[str, Any]],
    ) -> dict[tuple[str, ...], list[dict[str, Any]]]:
        """Group physical snapshot files by logical snapshot identity."""
        grouped: dict[tuple[str, ...], list[dict[str, Any]]] = {}
        for snapshot in snapshots:
            grouped.setdefault(cls._snapshot_identity_key(snapshot), []).append(snapshot)
        return grouped

    def _load_org_report_snapshots(self, org_id: str | None = None) -> list[dict[str, Any]]:
        """Load raw org-report snapshot metadata, one entry per physical file."""
        snapshots: list[dict[str, Any]] = []
        for snapshot_file in iter_org_report_snapshot_files(self.get_org_report_snapshot_root_dir(), org_id=org_id):
            metadata = self._load_org_report_snapshot_metadata(snapshot_file)
            if metadata is None:
                continue
            if org_id is not None and str(metadata.get("org_id") or "unknown") != str(org_id):
                continue
            snapshots.append(metadata)
        return snapshots

    def list_org_report_snapshots(self, org_id: str | None = None) -> list[dict[str, Any]]:
        """List persisted org-report snapshots, optionally filtered to one org."""
        grouped_snapshots = self._group_snapshot_metadata_by_identity(self._load_org_report_snapshots(org_id=org_id))
        canonical_snapshots = [
            self._canonical_snapshot_metadata(group_snapshots) for group_snapshots in grouped_snapshots.values()
        ]
        return self._sort_snapshot_metadata(canonical_snapshots)

    def inspect_org_report_snapshot(self, snapshot_file: str | Path) -> dict[str, Any]:
        """Return detailed summary metadata for one persisted org-report snapshot."""
        metadata = self._load_org_report_snapshot_metadata(snapshot_file, include_data_views=True)
        if metadata is None:
            raise ValueError(f"Invalid org-report snapshot: {snapshot_file}")
        return metadata

    def prune_org_report_snapshots(
        self,
        *,
        org_id: str | None = None,
        keep_last: int = 0,
        keep_since_days: int | None = None,
        preserved_snapshot_paths: list[str | Path] | tuple[str | Path, ...] = (),
    ) -> list[str]:
        """Delete persisted org-report snapshots outside the requested retention window."""
        if keep_last <= 0 and keep_since_days is None:
            return []

        snapshots = self._load_org_report_snapshots(org_id=org_id)
        preserved_paths = {
            normalized for normalized in (snapshot_path_text(path) for path in preserved_snapshot_paths) if normalized
        }
        grouped: dict[str, list[tuple[dict[str, Any], list[dict[str, Any]]]]] = {}
        for duplicate_group in self._group_snapshot_metadata_by_identity(snapshots).values():
            canonical_snapshot = self._canonical_snapshot_metadata(duplicate_group)
            grouped.setdefault(str(canonical_snapshot.get("org_id") or "unknown"), []).append(
                (canonical_snapshot, duplicate_group)
            )

        cutoff: datetime | None = None
        if keep_since_days is not None and keep_since_days >= 0:
            cutoff = datetime.now(UTC) - timedelta(days=keep_since_days)

        deleted_paths: list[str] = []
        for org_snapshot_groups in grouped.values():
            sorted_snapshots = self._sort_snapshot_metadata(
                [canonical_snapshot for canonical_snapshot, _ in org_snapshot_groups]
            )
            duplicate_groups_by_key = {
                self._snapshot_identity_key(canonical_snapshot): duplicate_group
                for canonical_snapshot, duplicate_group in org_snapshot_groups
            }

            retained_paths: set[str] = set()
            if keep_last > 0:
                retained_paths = self._retained_keep_last_paths(sorted_snapshots, keep_last=keep_last)

            for snapshot in sorted_snapshots:
                duplicate_group = duplicate_groups_by_key.get(self._snapshot_identity_key(snapshot), [])
                duplicate_paths = {
                    filepath
                    for filepath in (snapshot_path_text(item.get("filepath")) for item in duplicate_group)
                    if filepath
                }
                if not duplicate_paths:
                    continue

                keep_group = self._should_retain_snapshot(snapshot, retained_paths=retained_paths, cutoff=cutoff)
                preserved_duplicate_paths = duplicate_paths & preserved_paths
                keep_group = keep_group or bool(preserved_duplicate_paths)

                kept_paths = set(preserved_duplicate_paths)
                canonical_path = snapshot_path_text(snapshot.get("filepath"))
                if keep_group and canonical_path:
                    kept_paths.add(canonical_path)

                for filepath in sorted(duplicate_paths - kept_paths):
                    with contextlib.suppress(OSError):
                        Path(filepath).unlink()
                    if not Path(filepath).exists():
                        deleted_paths.append(filepath)

        return sorted(set(deleted_paths))

    def get(
        self,
        dv_id: str,
        max_age_hours: int = 24,
        required_flags: dict[str, bool] | None = None,
        current_modified: str | None = None,
    ) -> DataViewSummary | None:
        """Get cached data view summary if fresh enough.

        Args:
            dv_id: Data view ID
            max_age_hours: Maximum cache age in hours
            required_flags: Optional flags indicating required cached fields
            current_modified: Current data view modification timestamp for validation.
                If provided and differs from cached timestamp, returns None.

        Returns:
            Cached DataViewSummary or None if not cached or stale
        """
        entry = self._get_entry(dv_id)
        if entry is None:
            return None
        fetched_at = entry.get("fetched_at")
        if not fetched_at:
            return None

        try:
            fetched_time = datetime.fromisoformat(fetched_at)
            if datetime.now(UTC) - fetched_time > timedelta(hours=max_age_hours):
                return None  # Cache is stale
        except ValueError, TypeError:
            return None

        # Validate modification timestamp if provided
        # Omitting current_modified preserves age-only lookup behavior. The
        # analyzer rejects missing listing timestamps before validated lookup.
        if current_modified is not None:
            # Only an absent key falls back to legacy metadata. Explicit None
            # means the scheduling listing supplied no validation evidence.
            cached_modified = entry.get("validation_modified", entry.get("modified"))
            if not cached_modified or cached_modified != current_modified:
                return None  # Data view has been modified since cached

        if required_flags:
            include_names = required_flags.get("include_names", False)
            include_metadata = required_flags.get("include_metadata", False)
            include_component_types = required_flags.get("include_component_types", False)

            if include_names and not entry.get("include_names", False):
                return None
            if include_metadata and not entry.get("include_metadata", False):
                return None
            if include_component_types and not entry.get("include_component_types", False):
                return None

        # Reconstruct DataViewSummary from cached data
        try:
            return DataViewSummary(
                data_view_id=entry.get("data_view_id", dv_id),
                data_view_name=entry.get("data_view_name", "Unknown"),
                metric_ids=set(entry.get("metric_ids", [])),
                dimension_ids=set(entry.get("dimension_ids", [])),
                metric_count=entry.get("metric_count", 0),
                dimension_count=entry.get("dimension_count", 0),
                status=entry.get("status", "active"),
                fetch_duration=entry.get("fetch_duration", 0.0),
                error=entry.get("error"),
                metric_names=entry.get("metric_names"),
                dimension_names=entry.get("dimension_names"),
                standard_metric_count=entry.get("standard_metric_count", 0),
                derived_metric_count=entry.get("derived_metric_count", 0),
                standard_dimension_count=entry.get("standard_dimension_count", 0),
                derived_dimension_count=entry.get("derived_dimension_count", 0),
                owner=entry.get("owner"),
                owner_id=entry.get("owner_id"),
                created=entry.get("created"),
                modified=entry.get("modified"),
                description=entry.get("description"),
                has_description=entry.get("has_description", False),
            )
        except (ValueError, TypeError) as e:
            self.logger.debug("Cache deserialization failed for %s: %s", dv_id, e)
            return None

    def put(
        self,
        summary: DataViewSummary,
        include_names: bool = False,
        include_metadata: bool = False,
        include_component_types: bool = False,
    ) -> None:
        """Store a DataViewSummary in the cache.

        Args:
            summary: DataViewSummary to cache
            include_names: Whether names were included in the summary
            include_metadata: Whether metadata was included in the summary
            include_component_types: Whether component type counts were included
        """
        self._cache[summary.data_view_id] = self._build_entry(
            summary,
            include_names=include_names,
            include_metadata=include_metadata,
            include_component_types=include_component_types,
            validation_modified=summary.modified,
        )
        self._save_cache()

    def put_many(
        self,
        summaries: list[DataViewSummary],
        include_names: bool = False,
        include_metadata: bool = False,
        include_component_types: bool = False,
        validation_modified_by_id: dict[str, str | None] | None = None,
    ) -> None:
        """Store summaries in one write, optionally with listing validation tokens.

        A supplied mapping is authoritative, including missing timestamps; it
        must not fall back to timestamps from optional metadata enrichment.
        Without a mapping, preserve callers that supply summary.modified.
        """
        if not summaries:
            return
        for summary in summaries:
            self._cache[summary.data_view_id] = self._build_entry(
                summary,
                include_names=include_names,
                include_metadata=include_metadata,
                include_component_types=include_component_types,
                validation_modified=(
                    summary.modified
                    if validation_modified_by_id is None
                    else validation_modified_by_id.get(summary.data_view_id)
                ),
            )
        self._save_cache()

    def _build_entry(
        self,
        summary: DataViewSummary,
        *,
        include_names: bool,
        include_metadata: bool,
        include_component_types: bool,
        validation_modified: str | None,
    ) -> dict[str, Any]:
        return {
            "data_view_id": summary.data_view_id,
            "data_view_name": summary.data_view_name,
            "metric_ids": list(summary.metric_ids),
            "dimension_ids": list(summary.dimension_ids),
            "metric_count": summary.metric_count,
            "dimension_count": summary.dimension_count,
            "status": summary.status,
            "fetch_duration": summary.fetch_duration,
            "error": summary.error,
            "metric_names": summary.metric_names,
            "dimension_names": summary.dimension_names,
            "standard_metric_count": summary.standard_metric_count,
            "derived_metric_count": summary.derived_metric_count,
            "standard_dimension_count": summary.standard_dimension_count,
            "derived_dimension_count": summary.derived_dimension_count,
            "owner": summary.owner,
            "owner_id": summary.owner_id,
            "created": summary.created,
            "modified": summary.modified,
            "validation_modified": validation_modified,
            "description": summary.description,
            "has_description": summary.has_description,
            "include_names": include_names,
            "include_metadata": include_metadata,
            "include_component_types": include_component_types,
            "fetched_at": datetime.now(UTC).isoformat(),
        }

    def invalidate(self, dv_id: str | None = None) -> None:
        """Clear cache entries.

        Args:
            dv_id: Specific data view ID to clear, or None to clear all
        """
        if dv_id is None:
            self._cache = {}
        elif dv_id in self._cache:
            del self._cache[dv_id]
        self._save_cache()

    def has_valid_entry(self, dv_id: str, max_age_hours: int = 24) -> bool:
        """Check if a cache entry exists and is within age limit.

        Args:
            dv_id: Data view ID
            max_age_hours: Maximum cache age in hours

        Returns:
            True if entry exists and is fresh enough to potentially use
        """
        entry = self._get_entry(dv_id)
        if entry is None:
            return False
        fetched_at = entry.get("fetched_at")
        if not fetched_at:
            return False

        try:
            fetched_time = datetime.fromisoformat(fetched_at)
            if datetime.now(UTC) - fetched_time > timedelta(hours=max_age_hours):
                return False  # Cache is stale anyway
        except ValueError, TypeError:
            return False

        return True

    def get_cached_modified(self, dv_id: str) -> str | None:
        """Get the cached modification timestamp for a data view.

        Args:
            dv_id: Data view ID

        Returns:
            Cached modification timestamp or None if not cached
        """
        entry = self._get_entry(dv_id)
        if entry is None:
            return None
        return entry.get("modified")

    def get_stats(self) -> dict[str, Any]:
        """Get cache statistics.

        Returns:
            Dict with cache statistics
        """
        return {
            "entries": len(self._cache),
            "cache_file": str(self.cache_file),
            "cache_size_bytes": self.cache_file.stat().st_size if self.cache_file.exists() else 0,
        }
