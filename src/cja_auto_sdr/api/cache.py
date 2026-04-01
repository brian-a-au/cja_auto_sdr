"""Validation caches for CJA Auto SDR."""

import atexit
import contextlib
import hashlib
import itertools
import logging
import multiprocessing
import threading
import time
from collections import OrderedDict
from typing import Any

import pandas as pd

from cja_auto_sdr.core.constants import CACHE_KEY_HASH_LENGTH

_ERROR_KEY_COUNTER = itertools.count()


def _unique_error_key() -> str:
    """Return a unique cache key that forces a miss on key-generation failure."""
    return (
        f"error:{time.monotonic_ns()}:"
        f"{multiprocessing.current_process().pid}:{threading.get_ident()}:{next(_ERROR_KEY_COUNTER)}"
    )


def _local_cache_clock() -> float:
    """Return a monotonic clock for in-process cache bookkeeping."""
    return time.monotonic()


def _shared_cache_clock() -> float:
    """Return a monotonic clock for same-host Manager-backed cache state."""
    return time.monotonic()


def _validate_cache_params(max_size: int, ttl_seconds: int) -> None:
    """Validate cache initialization parameters."""
    if max_size < 1:
        raise ValueError(f"max_size must be >= 1, got {max_size}")
    if ttl_seconds <= 0:
        raise ValueError(f"ttl_seconds must be > 0, got {ttl_seconds}")


class ValidationCache:
    """
    Thread-safe LRU cache for data quality validation results

    Caches validation results based on DataFrame content hash and configuration.
    Uses LRU eviction policy to prevent unbounded memory growth.

    Performance Impact:
    - Cache hits: 50-90% faster than running validation
    - Cache misses: ~1-2% overhead for hashing (negligible)
    - Memory: ~1-5MB per 1000 cached entries

    Thread Safety:
    - Uses threading.Lock for all cache operations
    - Safe for use with parallel validation (check_all_parallel)
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600, logger: logging.Logger | None = None):
        """
        Initialize validation cache

        Args:
            max_size: Maximum number of cached entries, >= 1 (default: 1000)
            ttl_seconds: Time-to-live for cache entries in seconds, >= 1 (default: 3600 = 1 hour)
            logger: Logger instance for cache statistics (default: module logger)
        """
        _validate_cache_params(max_size, ttl_seconds)

        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.logger = logger or logging.getLogger(__name__)

        # Cache storage: key -> (issues_list, timestamp)
        # OrderedDict tracks insertion/access order for O(1) LRU eviction
        self._cache: OrderedDict[str, tuple[list[dict], float]] = OrderedDict()

        # Thread safety
        self._lock = threading.Lock()

        # Statistics
        self._hits = 0
        self._misses = 0
        self._evictions = 0

        self.logger.debug("ValidationCache initialized: max_size=%s, ttl=%ss", max_size, ttl_seconds)

    def _generate_cache_key(
        self,
        df: pd.DataFrame,
        item_type: str,
        required_fields: list[str],
        critical_fields: list[str],
    ) -> str:
        """
        Generate cache key from DataFrame content and configuration

        Strategy:
        - Uses pandas.util.hash_pandas_object for efficient DataFrame hashing
        - Combines DataFrame hash with configuration parameters
        - Returns consistent hash for identical inputs

        Args:
            df: DataFrame to hash
            item_type: 'Metrics' or 'Dimensions'
            required_fields: List of required field names
            critical_fields: List of critical field names

        Returns:
            Cache key string in format: "{item_type}:{df_hash}:{config_hash}"
        """
        try:
            # Hash DataFrame content using pandas built-in function
            # This is much faster than manual iteration (1-2ms vs 10-50ms for 1000 rows)

            # Hash DataFrame structure and content
            df_hash = pd.util.hash_pandas_object(df, index=False).sum()

            # Hash configuration (required_fields + critical_fields)
            config_str = f"{sorted(required_fields)}:{sorted(critical_fields)}"
            config_hash = hashlib.md5(config_str.encode(), usedforsecurity=False).hexdigest()[:CACHE_KEY_HASH_LENGTH]

            # Combine into cache key
            return f"{item_type}:{df_hash}:{config_hash}"

        except (TypeError, KeyError, ValueError) as e:
            self.logger.warning("Error generating cache key: %s. Cache disabled for this call.", e)
            # Return unique key to force cache miss
            return _unique_error_key()

    def get(
        self,
        df: pd.DataFrame,
        item_type: str,
        required_fields: list[str],
        critical_fields: list[str],
    ) -> tuple[list[dict] | None, str]:
        """
        Retrieve cached validation results if available

        Returns:
            Tuple of (issues list or None, cache_key).
            The cache_key can be passed to put() to avoid recomputing the hash.
        """
        cache_key = self._generate_cache_key(df, item_type, required_fields, critical_fields)

        # Check debug logging once outside the lock to avoid repeated checks
        debug_enabled = self.logger.isEnabledFor(logging.DEBUG)

        with self._lock:
            if cache_key not in self._cache:
                self._misses += 1
                if debug_enabled:
                    self.logger.debug("Cache MISS: %s (key: %s...)", item_type, cache_key[:20])
                return None, cache_key

            cached_issues, timestamp = self._cache[cache_key]

            # Check TTL expiration
            age = _local_cache_clock() - timestamp
            if age > self.ttl_seconds:
                if debug_enabled:
                    self.logger.debug("Cache EXPIRED: %s (age: %.1fs)", item_type, age)
                del self._cache[cache_key]
                self._misses += 1
                return None, cache_key

            # Cache hit - move to end for LRU tracking
            self._cache.move_to_end(cache_key)
            self._hits += 1
            if debug_enabled:
                self.logger.debug("Cache HIT: %s (%s issues)", item_type, len(cached_issues))

            # Return deep copy to prevent mutation of cached data
            return [issue.copy() for issue in cached_issues], cache_key

    def put(
        self,
        df: pd.DataFrame,
        item_type: str,
        required_fields: list[str],
        critical_fields: list[str],
        issues: list[dict],
        cache_key: str | None = None,
    ):
        """
        Store validation results in cache

        Implements LRU eviction when cache is full.

        Args:
            cache_key: Optional pre-computed cache key from get() to avoid rehashing
        """
        if cache_key is None:
            cache_key = self._generate_cache_key(df, item_type, required_fields, critical_fields)

        # Check debug logging once to avoid repeated checks in hot path
        debug_enabled = self.logger.isEnabledFor(logging.DEBUG)

        with self._lock:
            now = _local_cache_clock()

            if cache_key not in self._cache:
                self._ensure_capacity_for_new_entry(now, debug_enabled)

            # Store issues with timestamp
            # Deep copy to prevent external mutation
            self._cache[cache_key] = ([issue.copy() for issue in issues], now)
            # OrderedDict preserves position on overwrite, so one move_to_end()
            # after assignment is sufficient for both inserts and overwrites.
            self._cache.move_to_end(cache_key)

            if debug_enabled:
                self.logger.debug("Cache STORE: %s (%s issues)", item_type, len(issues))

    def _ensure_capacity_for_new_entry(self, now: float, debug_enabled: bool = False) -> None:
        """Make room for one new entry when capacity pressure exists (must be called within lock)."""
        if len(self._cache) < self.max_size:
            return

        # Prefer reclaiming expired entries before evicting live data, but only
        # when the cache is already at capacity.
        self._prune_expired_entries(now, debug_enabled)

        # Defensive bound in case a future change causes eviction to stop shrinking.
        max_eviction_attempts = len(self._cache) + 1
        for _ in range(max_eviction_attempts):
            if len(self._cache) < self.max_size:
                return
            self._evict_lru(debug_enabled)

        if len(self._cache) >= self.max_size:
            self.logger.warning("Cache capacity maintenance could not evict entries; clearing cache defensively")
            self._cache.clear()

    def _prune_expired_entries(self, now: float, debug_enabled: bool = False) -> int:
        """Remove expired entries before capacity-based eviction (must be called within lock)."""
        expired_keys = [key for key, (_issues, timestamp) in self._cache.items() if now - timestamp > self.ttl_seconds]
        for key in expired_keys:
            del self._cache[key]

        if expired_keys and debug_enabled:
            self.logger.debug("Cache PRUNE: removed %s expired entries", len(expired_keys))

        return len(expired_keys)

    def _evict_lru(self, debug_enabled: bool = False):
        """Evict least recently used cache entry.

        Args:
            debug_enabled: Whether debug logging is enabled (avoids repeated checks)
        """
        if not self._cache:
            return

        lru_key = next(iter(self._cache))
        del self._cache[lru_key]
        self._evictions += 1

        if debug_enabled:
            self.logger.debug("Cache EVICT: LRU entry removed (total evictions: %s)", self._evictions)

    def get_statistics(self) -> dict[str, Any]:
        """
        Get cache performance statistics

        Returns:
            Dict with hits, misses, hit_rate, size, evictions
        """
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0

            return {
                "hits": self._hits,
                "misses": self._misses,
                "hit_rate": hit_rate,
                "size": len(self._cache),
                "max_size": self.max_size,
                "evictions": self._evictions,
                "total_requests": total_requests,
            }

    def clear(self):
        """Clear all cache entries (useful for testing)"""
        with self._lock:
            self._cache.clear()
            self.logger.debug("Cache cleared")

    def log_statistics(self):
        """
        Log cache statistics in a user-friendly format.

        Logs hit rate, total requests, cache size, and estimated time savings.
        Only logs if there have been cache requests.
        """
        stats = self.get_statistics()
        if stats["total_requests"] == 0:
            self.logger.debug("Cache statistics: No requests recorded")
            return

        # Estimate time saved (average validation ~50ms, cache lookup ~1ms)
        estimated_time_saved = stats["hits"] * 0.049  # 49ms saved per hit

        self.logger.info(
            "Cache Statistics: %s/%s hits (%.1f%% hit rate)",
            stats["hits"],
            stats["total_requests"],
            stats["hit_rate"],
        )
        self.logger.info("  - Cache size: %s/%s entries", stats["size"], stats["max_size"])
        if stats["evictions"] > 0:
            self.logger.info("  - Evictions: %s", stats["evictions"])
        if estimated_time_saved > 0.1:
            self.logger.info("  - Estimated time saved: %.2fs", estimated_time_saved)


class SharedValidationCache:
    """
    Process-safe shared cache for validation results across batch workers.

    Uses multiprocessing.Manager to share cache state across multiple
    processes in batch mode. This allows validation results to be reused
    across different data views being processed in parallel.

    API Compatibility:
    - Implements the same interface as ValidationCache for drop-in replacement
    - get() and put() methods accept DataFrame objects like ValidationCache

    Key Differences from ValidationCache:
    - Uses Manager().dict() instead of regular dict (process-safe)
    - Manager-level locking instead of threading.Lock
    - Requires explicit shutdown() to cleanup Manager resources
    - Slightly higher overhead but enables cross-process sharing

    Usage:
        # In BatchProcessor
        shared_cache = SharedValidationCache(max_size=1000)

        # Pass to workers (cache reference is pickle-safe via Manager)
        worker_args = (data_view_id, ..., shared_cache)

        # In worker process - same API as ValidationCache
        cached, key = shared_cache.get(df, item_type, req_fields, crit_fields)
        if cached is None:
            result = run_validation(...)
            shared_cache.put(df, item_type, req_fields, crit_fields, result, key)

        # After batch processing
        shared_cache.shutdown()
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600, logger: logging.Logger | None = None):
        """
        Initialize shared validation cache.

        Args:
            max_size: Maximum number of cached entries (default: 1000)
            ttl_seconds: Time-to-live for cache entries in seconds (default: 3600)
            logger: Logger instance for cache statistics (default: module logger)
        """
        _validate_cache_params(max_size, ttl_seconds)

        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.logger = logger or logging.getLogger(__name__)

        # Create multiprocessing Manager for shared state
        self._manager = multiprocessing.Manager()

        # Shared cache storage: key -> (issues_list, timestamp)
        self._cache = self._manager.dict()

        # Shared LRU tracking: key -> last_access_time
        self._access_times = self._manager.dict()

        # Shared statistics
        self._stats = self._manager.dict({"hits": 0, "misses": 0, "evictions": 0})

        # Manager-level lock for cache operations
        self._lock = self._manager.Lock()

        # Ensure cleanup on exit even if shutdown() is never called explicitly
        atexit.register(self.shutdown)

    def _generate_cache_key(
        self,
        df: pd.DataFrame,
        item_type: str,
        required_fields: list[str],
        critical_fields: list[str],
    ) -> str:
        """
        Generate cache key from DataFrame content and configuration.

        Same algorithm as ValidationCache for compatibility.
        """
        try:
            # Hash DataFrame structure and content
            df_hash = pd.util.hash_pandas_object(df, index=False).sum()

            # Hash configuration (required_fields + critical_fields)
            config_str = f"{sorted(required_fields)}:{sorted(critical_fields)}"
            config_hash = hashlib.md5(config_str.encode(), usedforsecurity=False).hexdigest()[:CACHE_KEY_HASH_LENGTH]

            # Combine into cache key
            return f"{item_type}:{df_hash}:{config_hash}"

        except (TypeError, KeyError, ValueError) as e:
            self.logger.warning("Error generating cache key: %s. Cache disabled for this call.", e)
            # Return unique key to force cache miss
            return _unique_error_key()

    def get(
        self,
        df: pd.DataFrame,
        item_type: str,
        required_fields: list[str],
        critical_fields: list[str],
    ) -> tuple[list[dict] | None, str]:
        """
        Retrieve cached validation results if available.

        Same interface as ValidationCache for compatibility.

        Args:
            df: DataFrame to look up in cache
            item_type: 'Metrics' or 'Dimensions'
            required_fields: List of required field names
            critical_fields: List of critical field names

        Returns:
            Tuple of (issues list or None, cache_key).
            The cache_key can be passed to put() to avoid recomputing the hash.
        """
        cache_key = self._generate_cache_key(df, item_type, required_fields, critical_fields)

        with self._lock:
            if cache_key not in self._cache:
                self._stats["misses"] = self._stats.get("misses", 0) + 1
                return None, cache_key

            cached_data = self._cache[cache_key]
            cached_issues, timestamp = cached_data

            # Check TTL expiration
            age = _shared_cache_clock() - timestamp
            if age > self.ttl_seconds:
                self._remove_entry(cache_key)
                self._stats["misses"] = self._stats.get("misses", 0) + 1
                return None, cache_key

            # Cache hit - update access time and stats
            self._access_times[cache_key] = _shared_cache_clock()
            self._stats["hits"] = self._stats.get("hits", 0) + 1

            # Return copy to prevent mutation
            return [issue.copy() for issue in cached_issues], cache_key

    def _remove_entry(self, cache_key: str) -> bool:
        """Remove key from cache and access metadata (must be called within lock)."""
        removed = self._cache.pop(cache_key, None) is not None
        self._access_times.pop(cache_key, None)
        return removed

    def _reconcile_access_times(self, now: float) -> None:
        """Keep _access_times and _cache in sync (must be called within lock)."""
        cache_keys = set(self._cache.keys())
        access_keys = set(self._access_times.keys())

        # Remove stale access-time records for entries no longer in cache.
        for stale_key in access_keys - cache_keys:
            self._access_times.pop(stale_key, None)

        # Backfill missing access-time records so eviction always has a candidate.
        for missing_key in cache_keys - access_keys:
            self._access_times[missing_key] = now

    def _prune_expired_entries(self, now: float) -> int:
        """Drop expired entries from shared cache before capacity-based eviction."""
        expired_keys = [key for key, (_issues, timestamp) in self._cache.items() if now - timestamp > self.ttl_seconds]

        for key in expired_keys:
            self._remove_entry(key)

        return len(expired_keys)

    def _ensure_capacity_for_new_entry(self, now: float) -> None:
        """Make room for one new entry when capacity pressure exists (must be called within lock)."""
        if len(self._cache) < self.max_size:
            return

        self._prune_expired_entries(now)
        if len(self._cache) < self.max_size:
            return

        self._reconcile_access_times(now)

        # Defensive bound in case a future change causes eviction to stop shrinking.
        max_eviction_attempts = len(self._cache) + 1
        for _ in range(max_eviction_attempts):
            if len(self._cache) < self.max_size:
                return
            if not self._evict_lru(now=now, access_times_reconciled=True):
                break

        # Last-resort fallback: drop oldest key from cache iteration to avoid
        # blocking inserts on metadata corruption.
        while len(self._cache) >= self.max_size:
            fallback_key = next(iter(self._cache), None)
            if fallback_key is None:
                break
            self._remove_entry(fallback_key)
            self._stats["evictions"] = self._stats.get("evictions", 0) + 1

    def put(
        self,
        df: pd.DataFrame,
        item_type: str,
        required_fields: list[str],
        critical_fields: list[str],
        issues: list[dict],
        cache_key: str | None = None,
    ) -> None:
        """
        Store validation results in cache.

        Same interface as ValidationCache for compatibility.

        Args:
            df: DataFrame being cached (used if cache_key not provided)
            item_type: 'Metrics' or 'Dimensions'
            required_fields: List of required field names
            critical_fields: List of critical field names
            issues: List of validation issues to cache
            cache_key: Optional pre-computed cache key from get()
        """
        if cache_key is None:
            cache_key = self._generate_cache_key(df, item_type, required_fields, critical_fields)

        with self._lock:
            now = _shared_cache_clock()

            if cache_key not in self._cache:
                self._ensure_capacity_for_new_entry(now)

            # Store issues with timestamp (deep copy for safety)
            self._cache[cache_key] = ([issue.copy() for issue in issues], now)
            self._access_times[cache_key] = now

    def _evict_lru(self, now: float | None = None, access_times_reconciled: bool = False) -> bool:
        """Evict least recently used cache entry (must be called within lock).

        NOTE: Manager().dict() does not provide ordered pop semantics, so this
        implementation necessarily scans access-time metadata in O(N).
        """
        if not self._cache:
            self._access_times.clear()
            return False

        current_time = now if now is not None else _shared_cache_clock()
        if not access_times_reconciled:
            self._reconcile_access_times(current_time)

        access_items = list(self._access_times.items())
        if access_items:
            lru_key = min(access_items, key=lambda item: item[1])[0]
        else:
            lru_key = next(iter(self._cache))

        if self._remove_entry(lru_key):
            self._stats["evictions"] = self._stats.get("evictions", 0) + 1
            return True

        # Access metadata pointed at a missing cache key. Clean it up and
        # fall back to evicting a concrete cache entry if possible.
        self._access_times.pop(lru_key, None)
        fallback_key = next(iter(self._cache), None)
        if fallback_key is None:
            return False

        removed = self._remove_entry(fallback_key)
        if removed:
            self._stats["evictions"] = self._stats.get("evictions", 0) + 1
        return removed

    def get_statistics(self) -> dict[str, Any]:
        """
        Get cache performance statistics.

        Returns:
            Dict with hits, misses, hit_rate, size, evictions
        """
        with self._lock:
            stats = dict(self._stats)
            hits = stats.get("hits", 0)
            misses = stats.get("misses", 0)
            total_requests = hits + misses
            hit_rate = (hits / total_requests * 100) if total_requests > 0 else 0

            return {
                "hits": hits,
                "misses": misses,
                "hit_rate": hit_rate,
                "size": len(self._cache),
                "max_size": self.max_size,
                "evictions": stats.get("evictions", 0),
                "total_requests": total_requests,
            }

    def clear(self) -> None:
        """Clear all cache entries."""
        with self._lock:
            self._cache.clear()
            self._access_times.clear()

    def __getstate__(self) -> dict[str, Any]:
        """Support pickling for ProcessPoolExecutor by excluding non-picklable objects."""
        state = self.__dict__.copy()
        state["_logger_name"] = self.logger.name
        del state["logger"]
        del state["_manager"]
        return state

    def __setstate__(self, state: dict[str, Any]) -> None:
        """Restore state after unpickling, reconstructing the logger."""
        logger_name = state.pop("_logger_name")
        self.__dict__.update(state)
        self.logger = logging.getLogger(logger_name)
        self._manager = None  # Manager lives on the parent side only

    def shutdown(self) -> None:
        """
        Shutdown the Manager and cleanup resources.

        IMPORTANT: Call this after batch processing is complete to avoid
        resource leaks. The cache cannot be used after shutdown.
        """
        manager = self._manager
        if manager is None:
            return

        self._manager = None
        with contextlib.suppress(Exception):
            manager.shutdown()
