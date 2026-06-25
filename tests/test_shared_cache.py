"""Tests for shared validation cache

Validates that SharedValidationCache:
1. Has same API as ValidationCache (drop-in replacement)
2. Returns identical results on cache hits
3. Properly handles cache misses
4. Implements LRU eviction correctly
5. Expires entries based on TTL
6. Provides accurate statistics
7. Can be used across processes (multiprocessing.Manager)
8. Properly shuts down Manager resources
"""

from concurrent.futures import ProcessPoolExecutor
from unittest.mock import patch

import pandas as pd
import pytest

from cja_auto_sdr.api.cache import SharedValidationCache
from cja_auto_sdr.generator import ValidationCache


def _shared_cache_processpool_worker(cache):
    """Worker helper to validate cache proxy behavior after pickling."""
    df = pd.DataFrame({"id": ["shared-probe"]})
    try:
        result, cache_key = cache.get(df, "Metrics", ["id"], ["id"])
        if result is None:
            cache.put(df, "Metrics", ["id"], ["id"], [{"source": "worker"}], cache_key)
            result, _ = cache.get(df, "Metrics", ["id"], ["id"])
        return {"status": "ok", "result": result, "stats": cache.get_statistics()}
    except Exception as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


def _shared_cache_touch_worker(cache, item_id):
    """Worker helper that touches a cached key to refresh its shared recency."""
    df = pd.DataFrame({"id": [item_id]})
    try:
        result, _ = cache.get(df, "Metrics", ["id"], ["id"])
        return {"status": "ok", "hit": result is not None, "stats": cache.get_statistics()}
    except Exception as exc:
        return {"status": "error", "error": f"{type(exc).__name__}: {exc}"}


@pytest.fixture
def sample_metrics_df():
    """Sample metrics DataFrame for testing"""
    return pd.DataFrame(
        {
            "id": ["metric1", "metric2", "metric3"],
            "name": ["Metric One", "Metric Two", "Metric Three"],
            "type": ["calculated", "standard", "calculated"],
            "description": ["First metric", "Second metric", "Third metric"],
        },
    )


@pytest.fixture
def sample_dimensions_df():
    """Sample dimensions DataFrame for testing"""
    return pd.DataFrame(
        {
            "id": ["dim1", "dim2"],
            "name": ["Dimension One", "Dimension Two"],
            "type": ["standard", "standard"],
            "description": ["First dimension", "Second dimension"],
        },
    )


class TestSharedValidationCacheBasics:
    """Test basic shared cache functionality"""

    def test_invalid_cache_configuration_raises(self):
        """Invalid size/TTL should fail fast during initialization."""
        with pytest.raises(ValueError, match="max_size must be >= 1"):
            SharedValidationCache(max_size=0, ttl_seconds=3600)

        with pytest.raises(ValueError, match="ttl_seconds must be > 0"):
            SharedValidationCache(max_size=10, ttl_seconds=0)

    def test_cache_miss_on_first_call(self, sample_metrics_df):
        """First lookup should be cache miss"""
        cache = SharedValidationCache(max_size=100, ttl_seconds=3600)

        result, cache_key = cache.get(
            sample_metrics_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )

        assert result is None
        assert cache_key is not None
        stats = cache.get_statistics()
        assert stats["misses"] == 1
        assert stats["hits"] == 0

        cache.shutdown()

    def test_cache_hit_after_put(self, sample_metrics_df):
        """Should return cached result after put"""
        cache = SharedValidationCache(max_size=100, ttl_seconds=3600)

        # First call - miss
        result, cache_key = cache.get(
            sample_metrics_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )
        assert result is None

        # Store result
        issues = [{"severity": "LOW", "message": "Test issue"}]
        cache.put(
            sample_metrics_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
            issues,
            cache_key,
        )

        # Second call - hit
        result2, _cache_key2 = cache.get(
            sample_metrics_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )

        assert result2 is not None
        assert len(result2) == 1
        assert result2[0]["severity"] == "LOW"

        stats = cache.get_statistics()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

        cache.shutdown()

    def test_cache_miss_on_different_data(self, sample_metrics_df, sample_dimensions_df):
        """Different data should cause cache miss"""
        cache = SharedValidationCache(max_size=100, ttl_seconds=3600)

        # Cache metrics
        _, key1 = cache.get(sample_metrics_df, "Metrics", ["id"], ["name"])
        cache.put(sample_metrics_df, "Metrics", ["id"], ["name"], [], key1)

        # Lookup dimensions - should miss
        result, _ = cache.get(sample_dimensions_df, "Dimensions", ["id"], ["name"])
        assert result is None

        stats = cache.get_statistics()
        assert stats["misses"] == 2

        cache.shutdown()


class TestSharedValidationCacheAPICompatibility:
    """Test that SharedValidationCache is a drop-in replacement for ValidationCache"""

    def test_same_get_signature(self, sample_metrics_df):
        """get() should have same signature as ValidationCache"""
        shared = SharedValidationCache()
        regular = ValidationCache()

        # Both should accept same arguments
        shared_result, shared_key = shared.get(sample_metrics_df, "Metrics", ["id", "name"], ["id", "description"])
        regular_result, regular_key = regular.get(sample_metrics_df, "Metrics", ["id", "name"], ["id", "description"])

        # Both return same structure
        assert shared_result is None
        assert regular_result is None
        assert isinstance(shared_key, str)
        assert isinstance(regular_key, str)

        shared.shutdown()

    def test_same_put_signature(self, sample_metrics_df):
        """put() should have same signature as ValidationCache"""
        shared = SharedValidationCache()
        regular = ValidationCache()

        issues = [{"severity": "LOW", "message": "Test"}]

        # Both should accept same arguments
        _, shared_key = shared.get(sample_metrics_df, "Metrics", ["id"], ["name"])
        _, regular_key = regular.get(sample_metrics_df, "Metrics", ["id"], ["name"])

        # Should not raise
        shared.put(sample_metrics_df, "Metrics", ["id"], ["name"], issues, shared_key)
        regular.put(sample_metrics_df, "Metrics", ["id"], ["name"], issues, regular_key)

        shared.shutdown()

    def test_same_statistics_structure(self):
        """get_statistics() should return same structure"""
        shared = SharedValidationCache()
        regular = ValidationCache()

        shared_stats = shared.get_statistics()
        regular_stats = regular.get_statistics()

        # Should have same keys
        assert set(shared_stats.keys()) == set(regular_stats.keys())

        shared.shutdown()


class TestSharedValidationCacheEviction:
    """Test LRU eviction behavior"""

    def test_evicts_when_full(self, sample_metrics_df):
        """Should evict oldest entry when cache is full"""
        cache = SharedValidationCache(max_size=2, ttl_seconds=3600)

        # Add 3 entries to cache with size 2
        dfs = [
            pd.DataFrame({"id": ["item0"]}),
            pd.DataFrame({"id": ["item1"]}),
            pd.DataFrame({"id": ["item2"]}),
        ]

        for i, df in enumerate(dfs):
            _, key = cache.get(df, "Metrics", ["id"], ["id"])
            cache.put(df, "Metrics", ["id"], ["id"], [{"num": i}], key)

        stats = cache.get_statistics()
        assert stats["size"] == 2
        assert stats["evictions"] >= 1

        cache.shutdown()

    def test_evicts_least_recently_used(self):
        """Should evict least recently used entry"""
        cache = SharedValidationCache(max_size=2, ttl_seconds=3600)

        df1 = pd.DataFrame({"id": ["a"]})
        df2 = pd.DataFrame({"id": ["b"]})
        df3 = pd.DataFrame({"id": ["c"]})

        # Add df1 and df2
        _, key1 = cache.get(df1, "Metrics", ["id"], ["id"])
        cache.put(df1, "Metrics", ["id"], ["id"], [{"v": 1}], key1)

        _, key2 = cache.get(df2, "Metrics", ["id"], ["id"])
        cache.put(df2, "Metrics", ["id"], ["id"], [{"v": 2}], key2)

        # Access df1 to make it more recent
        cache.get(df1, "Metrics", ["id"], ["id"])

        # Add df3 - should evict df2 (least recently used)
        _, key3 = cache.get(df3, "Metrics", ["id"], ["id"])
        cache.put(df3, "Metrics", ["id"], ["id"], [{"v": 3}], key3)

        # df1 should still be in cache
        result1, _ = cache.get(df1, "Metrics", ["id"], ["id"])
        assert result1 is not None

        # df2 should be evicted
        result2, _ = cache.get(df2, "Metrics", ["id"], ["id"])
        assert result2 is None

        cache.shutdown()

    def test_access_recency_ignores_wall_clock_jumps(self):
        """LRU recency should follow monotonic access order even if wall time jumps backward."""
        wall_now = [1000.0]
        monotonic_now = [10.0]

        def mock_time():
            return wall_now[0]

        def mock_monotonic():
            return monotonic_now[0]

        with patch("cja_auto_sdr.api.cache.time") as mock_time_module:
            mock_time_module.time = mock_time
            mock_time_module.monotonic = mock_monotonic
            mock_time_module.monotonic_ns = lambda: int(monotonic_now[0] * 1e9)
            cache = SharedValidationCache(max_size=2, ttl_seconds=3600)

            try:
                df1 = pd.DataFrame({"id": ["a"]})
                df2 = pd.DataFrame({"id": ["b"]})
                df3 = pd.DataFrame({"id": ["c"]})

                _, key1 = cache.get(df1, "Metrics", ["id"], ["id"])
                cache.put(df1, "Metrics", ["id"], ["id"], [{"v": 1}], key1)

                wall_now[0] = 1001.0
                monotonic_now[0] = 20.0
                _, key2 = cache.get(df2, "Metrics", ["id"], ["id"])
                cache.put(df2, "Metrics", ["id"], ["id"], [{"v": 2}], key2)

                # Wall clock jumps backward, but monotonic access ordering keeps advancing.
                wall_now[0] = 10.0
                monotonic_now[0] = 30.0
                cache.get(df1, "Metrics", ["id"], ["id"])

                wall_now[0] = 5.0
                monotonic_now[0] = 40.0
                _, key3 = cache.get(df3, "Metrics", ["id"], ["id"])
                cache.put(df3, "Metrics", ["id"], ["id"], [{"v": 3}], key3)

                result1, _ = cache.get(df1, "Metrics", ["id"], ["id"])
                result2, _ = cache.get(df2, "Metrics", ["id"], ["id"])
                result3, _ = cache.get(df3, "Metrics", ["id"], ["id"])

                assert result1 is not None
                assert result2 is None
                assert result3 is not None
            finally:
                cache.shutdown()

    def test_put_defers_full_scans_until_capacity_pressure(self):
        """New keys below capacity should not trigger prune/reconcile full scans."""
        cache = SharedValidationCache(max_size=3, ttl_seconds=3600)

        try:
            dfs = [pd.DataFrame({"id": [f"item{idx}"]}) for idx in range(4)]

            with (
                patch.object(cache, "_prune_expired_entries", wraps=cache._prune_expired_entries) as mock_prune,
                patch.object(cache, "_reconcile_access_times", wraps=cache._reconcile_access_times) as mock_reconcile,
            ):
                for idx in range(3):
                    _, key = cache.get(dfs[idx], "Metrics", ["id"], ["id"])
                    cache.put(dfs[idx], "Metrics", ["id"], ["id"], [{"v": idx}], key)

                assert mock_prune.call_count == 0
                assert mock_reconcile.call_count == 0

                _, key = cache.get(dfs[3], "Metrics", ["id"], ["id"])
                cache.put(dfs[3], "Metrics", ["id"], ["id"], [{"v": 3}], key)

                assert mock_prune.call_count == 1
                assert mock_reconcile.call_count == 1

            stats = cache.get_statistics()
            assert stats["size"] == 3
            assert stats["evictions"] >= 1
        finally:
            cache.shutdown()

    def test_capacity_pressure_skips_reconcile_when_prune_frees_space(self):
        """Reconciliation should be skipped if expiration pruning already frees capacity."""
        fake_now = [1000000.0]

        def mock_monotonic():
            return fake_now[0]

        with patch("cja_auto_sdr.api.cache.time") as mock_time_module:
            mock_time_module.time = mock_monotonic
            mock_time_module.monotonic = mock_monotonic
            mock_time_module.monotonic_ns = lambda: int(fake_now[0] * 1e9)
            cache = SharedValidationCache(max_size=2, ttl_seconds=1)

            try:
                df1 = pd.DataFrame({"id": ["expired-1"]})
                df2 = pd.DataFrame({"id": ["expired-2"]})
                df3 = pd.DataFrame({"id": ["fresh"]})

                _, key1 = cache.get(df1, "Metrics", ["id"], ["id"])
                cache.put(df1, "Metrics", ["id"], ["id"], [{"v": 1}], key1)
                _, key2 = cache.get(df2, "Metrics", ["id"], ["id"])
                cache.put(df2, "Metrics", ["id"], ["id"], [{"v": 2}], key2)

                fake_now[0] += 1.5

                with patch.object(
                    cache, "_reconcile_access_times", wraps=cache._reconcile_access_times
                ) as mock_reconcile:
                    _, key3 = cache.get(df3, "Metrics", ["id"], ["id"])
                    cache.put(df3, "Metrics", ["id"], ["id"], [{"v": 3}], key3)
                    assert mock_reconcile.call_count == 0

                stats = cache.get_statistics()
                assert stats["size"] == 1
                assert stats["evictions"] == 0
            finally:
                cache.shutdown()

    def test_overwrite_refreshes_recency_before_eviction(self):
        """Overwriting an entry should refresh recency so it is not evicted next."""
        cache = SharedValidationCache(max_size=2, ttl_seconds=3600)

        try:
            df1 = pd.DataFrame({"id": ["a"]})
            df2 = pd.DataFrame({"id": ["b"]})
            df3 = pd.DataFrame({"id": ["c"]})

            _, key1 = cache.get(df1, "Metrics", ["id"], ["id"])
            cache.put(df1, "Metrics", ["id"], ["id"], [{"v": 1}], key1)

            _, key2 = cache.get(df2, "Metrics", ["id"], ["id"])
            cache.put(df2, "Metrics", ["id"], ["id"], [{"v": 2}], key2)

            # Overwrite df1 to refresh its recency.
            cache.put(df1, "Metrics", ["id"], ["id"], [{"v": 10}], key1)

            _, key3 = cache.get(df3, "Metrics", ["id"], ["id"])
            cache.put(df3, "Metrics", ["id"], ["id"], [{"v": 3}], key3)

            result1, _ = cache.get(df1, "Metrics", ["id"], ["id"])
            result2, _ = cache.get(df2, "Metrics", ["id"], ["id"])
            result3, _ = cache.get(df3, "Metrics", ["id"], ["id"])

            assert result1 is not None
            assert result1[0]["v"] == 10
            assert result2 is None
            assert result3 is not None
        finally:
            cache.shutdown()

    def test_put_recovers_when_access_times_missing(self):
        """Defensive path: put() should restore LRU metadata before eviction."""
        cache = SharedValidationCache(max_size=1, ttl_seconds=3600)

        try:
            df1 = pd.DataFrame({"id": ["stale"]})
            df2 = pd.DataFrame({"id": ["fresh"]})

            _, key1 = cache.get(df1, "Metrics", ["id"], ["id"])
            cache.put(df1, "Metrics", ["id"], ["id"], [{"v": "old"}], key1)

            # Simulate metadata drift/corruption where access tracking is lost.
            cache._access_times.clear()

            _, key2 = cache.get(df2, "Metrics", ["id"], ["id"])
            cache.put(df2, "Metrics", ["id"], ["id"], [{"v": "new"}], key2)

            result1, _ = cache.get(df1, "Metrics", ["id"], ["id"])
            result2, _ = cache.get(df2, "Metrics", ["id"], ["id"])
            stats = cache.get_statistics()

            assert result1 is None
            assert result2 is not None
            assert stats["size"] == 1
            assert stats["evictions"] >= 1
        finally:
            cache.shutdown()


class TestSharedValidationCacheTTL:
    """Test TTL expiration behavior"""

    def test_expires_after_ttl(self, sample_metrics_df):
        """Entries should expire by monotonic elapsed time even if wall time jumps."""
        wall_now = [1000.0]
        monotonic_now = [10.0]

        def mock_time():
            return wall_now[0]

        def mock_monotonic():
            return monotonic_now[0]

        with patch("cja_auto_sdr.api.cache.time") as mock_time_module:
            mock_time_module.time = mock_time
            mock_time_module.monotonic = mock_monotonic
            mock_time_module.monotonic_ns = lambda: int(monotonic_now[0] * 1e9)
            cache = SharedValidationCache(max_size=100, ttl_seconds=1)

            try:
                _, key = cache.get(sample_metrics_df, "Metrics", ["id"], ["id"])
                cache.put(sample_metrics_df, "Metrics", ["id"], ["id"], [{"test": 1}], key)

                wall_now[0] = 2000.0
                monotonic_now[0] = 10.5
                result1, _ = cache.get(sample_metrics_df, "Metrics", ["id"], ["id"])
                assert result1 is not None

                wall_now[0] = 1.0
                monotonic_now[0] = 11.2
                result2, _ = cache.get(sample_metrics_df, "Metrics", ["id"], ["id"])
                assert result2 is None
            finally:
                cache.shutdown()


class TestSharedValidationCacheStatistics:
    """Test statistics tracking"""

    def test_tracks_hits_and_misses(self, sample_metrics_df):
        """Should accurately track hit/miss counts"""
        cache = SharedValidationCache()

        # Miss
        _, key = cache.get(sample_metrics_df, "Metrics", ["id"], ["id"])
        cache.put(sample_metrics_df, "Metrics", ["id"], ["id"], [], key)

        # Hit
        cache.get(sample_metrics_df, "Metrics", ["id"], ["id"])
        cache.get(sample_metrics_df, "Metrics", ["id"], ["id"])

        stats = cache.get_statistics()
        assert stats["hits"] == 2
        assert stats["misses"] == 1
        assert stats["hit_rate"] == pytest.approx(66.67, rel=0.1)

        cache.shutdown()

    def test_tracks_size(self, sample_metrics_df, sample_dimensions_df):
        """Should track cache size"""
        cache = SharedValidationCache()

        _, key1 = cache.get(sample_metrics_df, "Metrics", ["id"], ["id"])
        cache.put(sample_metrics_df, "Metrics", ["id"], ["id"], [], key1)

        _, key2 = cache.get(sample_dimensions_df, "Dims", ["id"], ["id"])
        cache.put(sample_dimensions_df, "Dims", ["id"], ["id"], [], key2)

        stats = cache.get_statistics()
        assert stats["size"] == 2

        cache.shutdown()


class TestSharedValidationCacheClear:
    """Test cache clearing"""

    def test_clear_removes_all_entries(self, sample_metrics_df):
        """clear() should remove all entries"""
        cache = SharedValidationCache()

        _, key = cache.get(sample_metrics_df, "Metrics", ["id"], ["id"])
        cache.put(sample_metrics_df, "Metrics", ["id"], ["id"], [], key)

        cache.clear()

        result, _ = cache.get(sample_metrics_df, "Metrics", ["id"], ["id"])
        assert result is None

        stats = cache.get_statistics()
        assert stats["size"] == 0

        cache.shutdown()


class TestSharedValidationCacheShutdown:
    """Test proper cleanup"""

    def test_shutdown_cleans_up_manager(self):
        """shutdown() should cleanup Manager resources"""
        cache = SharedValidationCache()

        # Add some data
        df = pd.DataFrame({"id": ["test"]})
        _, key = cache.get(df, "Metrics", ["id"], ["id"])
        cache.put(df, "Metrics", ["id"], ["id"], [], key)

        # Shutdown should not raise
        cache.shutdown()

        # Second shutdown should be safe
        cache.shutdown()

    def test_cache_unusable_after_shutdown(self):
        """Cache operations should fail after shutdown"""
        cache = SharedValidationCache()
        cache.shutdown()

        df = pd.DataFrame({"id": ["test"]})

        # Operations may raise or return None/empty - just verify no crash
        try:
            cache.get(df, "Metrics", ["id"], ["id"])
        except Exception:
            pass  # Expected after shutdown


class TestSharedValidationCacheSerialization:
    """Test cache behavior when pickled and sent to worker processes."""

    def test_process_pool_round_trip_preserves_shared_state(self):
        """Worker writes should be visible in parent via shared Manager proxies."""
        cache = SharedValidationCache(max_size=10, ttl_seconds=3600)
        parent_df = pd.DataFrame({"id": ["shared-probe"]})

        try:
            with ProcessPoolExecutor(max_workers=1) as executor:
                output = executor.submit(_shared_cache_processpool_worker, cache).result(timeout=30)

            assert output["status"] == "ok", output.get("error", "worker failed")
            worker_result = output["result"]
            assert worker_result is not None
            assert worker_result[0]["source"] == "worker"

            parent_result, _ = cache.get(parent_df, "Metrics", ["id"], ["id"])
            assert parent_result is not None
            assert parent_result[0]["source"] == "worker"

            parent_stats = cache.get_statistics()
            assert parent_stats["size"] == 1
            assert parent_stats["hits"] >= 1
            assert parent_stats["misses"] >= 1
        finally:
            cache.shutdown()

    def test_worker_access_refreshes_lru_before_parent_eviction(self):
        """A worker-process hit should keep that key hot for the parent's next eviction."""
        cache = SharedValidationCache(max_size=2, ttl_seconds=3600)
        df1 = pd.DataFrame({"id": ["a"]})
        df2 = pd.DataFrame({"id": ["b"]})
        df3 = pd.DataFrame({"id": ["c"]})

        try:
            _, key1 = cache.get(df1, "Metrics", ["id"], ["id"])
            cache.put(df1, "Metrics", ["id"], ["id"], [{"v": 1}], key1)

            _, key2 = cache.get(df2, "Metrics", ["id"], ["id"])
            cache.put(df2, "Metrics", ["id"], ["id"], [{"v": 2}], key2)

            with ProcessPoolExecutor(max_workers=1) as executor:
                output = executor.submit(_shared_cache_touch_worker, cache, "a").result(timeout=30)

            assert output["status"] == "ok", output.get("error", "worker failed")
            assert output["hit"] is True

            _, key3 = cache.get(df3, "Metrics", ["id"], ["id"])
            cache.put(df3, "Metrics", ["id"], ["id"], [{"v": 3}], key3)

            result1, _ = cache.get(df1, "Metrics", ["id"], ["id"])
            result2, _ = cache.get(df2, "Metrics", ["id"], ["id"])
            result3, _ = cache.get(df3, "Metrics", ["id"], ["id"])

            assert result1 is not None
            assert result2 is None
            assert result3 is not None
        finally:
            cache.shutdown()


class TestSharedValidationCacheDataIntegrity:
    """Test data integrity across operations"""

    def test_returns_copy_of_cached_data(self, sample_metrics_df):
        """Should return copy to prevent mutation of cached data"""
        cache = SharedValidationCache()

        original_issues = [{"severity": "LOW", "message": "Test"}]

        _, key = cache.get(sample_metrics_df, "Metrics", ["id"], ["id"])
        cache.put(sample_metrics_df, "Metrics", ["id"], ["id"], original_issues, key)

        # Get cached data
        result1, _ = cache.get(sample_metrics_df, "Metrics", ["id"], ["id"])

        # Mutate returned data
        result1[0]["message"] = "Modified"

        # Get again - should have original value
        result2, _ = cache.get(sample_metrics_df, "Metrics", ["id"], ["id"])
        assert result2[0]["message"] == "Test"

        cache.shutdown()

    def test_stores_copy_of_input_data(self, sample_metrics_df):
        """Should store copy to prevent external mutation affecting cache"""
        cache = SharedValidationCache()

        issues = [{"severity": "LOW", "message": "Original"}]

        _, key = cache.get(sample_metrics_df, "Metrics", ["id"], ["id"])
        cache.put(sample_metrics_df, "Metrics", ["id"], ["id"], issues, key)

        # Mutate original data
        issues[0]["message"] = "Modified"

        # Get cached data - should have original value
        result, _ = cache.get(sample_metrics_df, "Metrics", ["id"], ["id"])
        assert result[0]["message"] == "Original"

        cache.shutdown()


# ---------------------------------------------------------------------------
# Coverage gap tests (moved from test_small_gap_coverage.py)
# ---------------------------------------------------------------------------


def test_shared_cache_reconcile_access_times_removes_stale_and_backfills_missing() -> None:
    cache = SharedValidationCache(max_size=2, ttl_seconds=3600)

    try:
        cache._cache["live"] = ([{"issue": "new"}], 1.0)
        cache._access_times["stale"] = 0.5

        with cache._lock:
            cache._reconcile_access_times(now=5.0)

        assert "stale" not in cache._access_times
        assert cache._access_times["live"] == 5.0
    finally:
        cache.shutdown()


def test_shared_cache_capacity_fallback_removes_entry_when_evict_lru_stalls() -> None:
    cache = SharedValidationCache(max_size=1, ttl_seconds=3600)

    try:
        cache._cache["old"] = ([{"issue": "old"}], 1.0)
        cache._access_times["old"] = 1.0

        with patch.object(cache, "_evict_lru", return_value=False):
            with cache._lock:
                cache._ensure_capacity_for_new_entry(now=2.0)

        assert dict(cache._cache) == {}
        assert cache.get_statistics()["evictions"] == 1
    finally:
        cache.shutdown()


def test_shared_cache_evict_lru_uses_cache_iteration_when_access_times_missing() -> None:
    cache = SharedValidationCache(max_size=1, ttl_seconds=3600)

    try:
        cache._cache["real"] = ([{"issue": "kept"}], 1.0)

        with cache._lock:
            removed = cache._evict_lru(now=2.0, access_times_reconciled=True)

        assert removed is True
        assert dict(cache._cache) == {}
        assert cache.get_statistics()["evictions"] == 1
    finally:
        cache.shutdown()


def test_shared_cache_evict_lru_falls_back_after_stale_access_metadata() -> None:
    cache = SharedValidationCache(max_size=1, ttl_seconds=3600)

    try:
        cache._cache["real"] = ([{"issue": "kept"}], 1.0)
        cache._access_times["ghost"] = 0.0

        with cache._lock:
            removed = cache._evict_lru(now=2.0, access_times_reconciled=True)

        assert removed is True
        assert dict(cache._cache) == {}
        assert "ghost" not in cache._access_times
        assert cache.get_statistics()["evictions"] == 1
    finally:
        cache.shutdown()


class _LenIterMismatchCache:
    """A mapping whose ``len()`` reports entries but whose iteration yields none.

    Real ``Manager().dict()`` / ``dict`` keep ``__len__`` and ``__iter__`` in
    agreement, so the defensive ``fallback_key is None`` guards can only be hit
    by simulating metadata that disagrees with itself.
    """

    def __init__(self, reported_len: int) -> None:
        self._reported_len = reported_len

    def __len__(self) -> int:
        return self._reported_len

    def __bool__(self) -> bool:
        return self._reported_len > 0

    def __iter__(self):
        return iter(())

    def pop(self, key, default=None):
        return default


def test_shared_cache_capacity_fallback_breaks_when_iteration_empty() -> None:
    """Defensive guard: the last-resort loop stops if iteration yields no key."""
    cache = SharedValidationCache(max_size=1, ttl_seconds=3600)

    try:
        with (
            patch.object(cache, "_prune_expired_entries"),
            patch.object(cache, "_reconcile_access_times"),
            patch.object(cache, "_evict_lru", return_value=False),
        ):
            # len() says full (>= max_size) but iteration is empty -> fallback_key is None.
            cache._cache = _LenIterMismatchCache(reported_len=cache.max_size)
            with cache._lock:
                cache._ensure_capacity_for_new_entry(now=2.0)

        # No eviction recorded because the loop broke immediately on an empty iterator.
        assert cache.get_statistics()["evictions"] == 0
    finally:
        cache.shutdown()


def test_shared_cache_evict_lru_returns_false_when_fallback_iteration_empty() -> None:
    """Defensive guard: eviction reports failure when no concrete key can be found."""
    cache = SharedValidationCache(max_size=1, ttl_seconds=3600)

    try:
        # Access metadata points at a key that is not in the (truthy but empty-on-iter) cache.
        cache._access_times["ghost"] = 0.0
        cache._cache = _LenIterMismatchCache(reported_len=1)

        with cache._lock:
            removed = cache._evict_lru(now=2.0, access_times_reconciled=True)

        assert removed is False
        # Stale access metadata for the missing key was cleaned up on the way out.
        assert "ghost" not in cache._access_times
        assert cache.get_statistics()["evictions"] == 0
    finally:
        cache.shutdown()
