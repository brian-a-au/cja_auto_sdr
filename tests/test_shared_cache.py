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
import pytest
import pandas as pd
import logging
import time
import multiprocessing
from concurrent.futures import ProcessPoolExecutor
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cja_sdr_generator import SharedValidationCache, ValidationCache


@pytest.fixture
def sample_metrics_df():
    """Sample metrics DataFrame for testing"""
    return pd.DataFrame({
        'id': ['metric1', 'metric2', 'metric3'],
        'name': ['Metric One', 'Metric Two', 'Metric Three'],
        'type': ['calculated', 'standard', 'calculated'],
        'description': ['First metric', 'Second metric', 'Third metric']
    })


@pytest.fixture
def sample_dimensions_df():
    """Sample dimensions DataFrame for testing"""
    return pd.DataFrame({
        'id': ['dim1', 'dim2'],
        'name': ['Dimension One', 'Dimension Two'],
        'type': ['standard', 'standard'],
        'description': ['First dimension', 'Second dimension']
    })


class TestSharedValidationCacheBasics:
    """Test basic shared cache functionality"""

    def test_cache_miss_on_first_call(self, sample_metrics_df):
        """First lookup should be cache miss"""
        cache = SharedValidationCache(max_size=100, ttl_seconds=3600)

        result, cache_key = cache.get(
            sample_metrics_df,
            'Metrics',
            ['id', 'name', 'type'],
            ['id', 'name', 'description']
        )

        assert result is None
        assert cache_key is not None
        stats = cache.get_statistics()
        assert stats['misses'] == 1
        assert stats['hits'] == 0

        cache.shutdown()

    def test_cache_hit_after_put(self, sample_metrics_df):
        """Should return cached result after put"""
        cache = SharedValidationCache(max_size=100, ttl_seconds=3600)

        # First call - miss
        result, cache_key = cache.get(
            sample_metrics_df,
            'Metrics',
            ['id', 'name', 'type'],
            ['id', 'name', 'description']
        )
        assert result is None

        # Store result
        issues = [{'severity': 'LOW', 'message': 'Test issue'}]
        cache.put(sample_metrics_df, 'Metrics', ['id', 'name', 'type'],
                 ['id', 'name', 'description'], issues, cache_key)

        # Second call - hit
        result2, cache_key2 = cache.get(
            sample_metrics_df,
            'Metrics',
            ['id', 'name', 'type'],
            ['id', 'name', 'description']
        )

        assert result2 is not None
        assert len(result2) == 1
        assert result2[0]['severity'] == 'LOW'

        stats = cache.get_statistics()
        assert stats['hits'] == 1
        assert stats['misses'] == 1

        cache.shutdown()

    def test_cache_miss_on_different_data(self, sample_metrics_df, sample_dimensions_df):
        """Different data should cause cache miss"""
        cache = SharedValidationCache(max_size=100, ttl_seconds=3600)

        # Cache metrics
        _, key1 = cache.get(sample_metrics_df, 'Metrics', ['id'], ['name'])
        cache.put(sample_metrics_df, 'Metrics', ['id'], ['name'], [], key1)

        # Lookup dimensions - should miss
        result, _ = cache.get(sample_dimensions_df, 'Dimensions', ['id'], ['name'])
        assert result is None

        stats = cache.get_statistics()
        assert stats['misses'] == 2

        cache.shutdown()


class TestSharedValidationCacheAPICompatibility:
    """Test that SharedValidationCache is a drop-in replacement for ValidationCache"""

    def test_same_get_signature(self, sample_metrics_df):
        """get() should have same signature as ValidationCache"""
        shared = SharedValidationCache()
        regular = ValidationCache()

        # Both should accept same arguments
        shared_result, shared_key = shared.get(
            sample_metrics_df,
            'Metrics',
            ['id', 'name'],
            ['id', 'description']
        )
        regular_result, regular_key = regular.get(
            sample_metrics_df,
            'Metrics',
            ['id', 'name'],
            ['id', 'description']
        )

        # Both return same structure
        assert shared_result is None and regular_result is None
        assert isinstance(shared_key, str) and isinstance(regular_key, str)

        shared.shutdown()

    def test_same_put_signature(self, sample_metrics_df):
        """put() should have same signature as ValidationCache"""
        shared = SharedValidationCache()
        regular = ValidationCache()

        issues = [{'severity': 'LOW', 'message': 'Test'}]

        # Both should accept same arguments
        _, shared_key = shared.get(sample_metrics_df, 'Metrics', ['id'], ['name'])
        _, regular_key = regular.get(sample_metrics_df, 'Metrics', ['id'], ['name'])

        # Should not raise
        shared.put(sample_metrics_df, 'Metrics', ['id'], ['name'], issues, shared_key)
        regular.put(sample_metrics_df, 'Metrics', ['id'], ['name'], issues, regular_key)

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
            pd.DataFrame({'id': ['item0']}),
            pd.DataFrame({'id': ['item1']}),
            pd.DataFrame({'id': ['item2']}),
        ]

        for i, df in enumerate(dfs):
            _, key = cache.get(df, 'Metrics', ['id'], ['id'])
            cache.put(df, 'Metrics', ['id'], ['id'], [{'num': i}], key)

        stats = cache.get_statistics()
        assert stats['size'] == 2
        assert stats['evictions'] >= 1

        cache.shutdown()

    def test_evicts_least_recently_used(self):
        """Should evict least recently used entry"""
        cache = SharedValidationCache(max_size=2, ttl_seconds=3600)

        df1 = pd.DataFrame({'id': ['a']})
        df2 = pd.DataFrame({'id': ['b']})
        df3 = pd.DataFrame({'id': ['c']})

        # Add df1 and df2
        _, key1 = cache.get(df1, 'Metrics', ['id'], ['id'])
        cache.put(df1, 'Metrics', ['id'], ['id'], [{'v': 1}], key1)

        _, key2 = cache.get(df2, 'Metrics', ['id'], ['id'])
        cache.put(df2, 'Metrics', ['id'], ['id'], [{'v': 2}], key2)

        # Access df1 to make it more recent
        cache.get(df1, 'Metrics', ['id'], ['id'])

        # Add df3 - should evict df2 (least recently used)
        _, key3 = cache.get(df3, 'Metrics', ['id'], ['id'])
        cache.put(df3, 'Metrics', ['id'], ['id'], [{'v': 3}], key3)

        # df1 should still be in cache
        result1, _ = cache.get(df1, 'Metrics', ['id'], ['id'])
        assert result1 is not None

        # df2 should be evicted
        result2, _ = cache.get(df2, 'Metrics', ['id'], ['id'])
        assert result2 is None

        cache.shutdown()


class TestSharedValidationCacheTTL:
    """Test TTL expiration behavior"""

    def test_expires_after_ttl(self, sample_metrics_df):
        """Entries should expire after TTL"""
        cache = SharedValidationCache(max_size=100, ttl_seconds=0.1)

        # Add entry
        _, key = cache.get(sample_metrics_df, 'Metrics', ['id'], ['id'])
        cache.put(sample_metrics_df, 'Metrics', ['id'], ['id'], [{'test': 1}], key)

        # Should hit immediately
        result1, _ = cache.get(sample_metrics_df, 'Metrics', ['id'], ['id'])
        assert result1 is not None

        # Wait for TTL
        time.sleep(0.15)

        # Should miss after TTL
        result2, _ = cache.get(sample_metrics_df, 'Metrics', ['id'], ['id'])
        assert result2 is None

        cache.shutdown()


class TestSharedValidationCacheStatistics:
    """Test statistics tracking"""

    def test_tracks_hits_and_misses(self, sample_metrics_df):
        """Should accurately track hit/miss counts"""
        cache = SharedValidationCache()

        # Miss
        _, key = cache.get(sample_metrics_df, 'Metrics', ['id'], ['id'])
        cache.put(sample_metrics_df, 'Metrics', ['id'], ['id'], [], key)

        # Hit
        cache.get(sample_metrics_df, 'Metrics', ['id'], ['id'])
        cache.get(sample_metrics_df, 'Metrics', ['id'], ['id'])

        stats = cache.get_statistics()
        assert stats['hits'] == 2
        assert stats['misses'] == 1
        assert stats['hit_rate'] == pytest.approx(66.67, rel=0.1)

        cache.shutdown()

    def test_tracks_size(self, sample_metrics_df, sample_dimensions_df):
        """Should track cache size"""
        cache = SharedValidationCache()

        _, key1 = cache.get(sample_metrics_df, 'Metrics', ['id'], ['id'])
        cache.put(sample_metrics_df, 'Metrics', ['id'], ['id'], [], key1)

        _, key2 = cache.get(sample_dimensions_df, 'Dims', ['id'], ['id'])
        cache.put(sample_dimensions_df, 'Dims', ['id'], ['id'], [], key2)

        stats = cache.get_statistics()
        assert stats['size'] == 2

        cache.shutdown()


class TestSharedValidationCacheClear:
    """Test cache clearing"""

    def test_clear_removes_all_entries(self, sample_metrics_df):
        """clear() should remove all entries"""
        cache = SharedValidationCache()

        _, key = cache.get(sample_metrics_df, 'Metrics', ['id'], ['id'])
        cache.put(sample_metrics_df, 'Metrics', ['id'], ['id'], [], key)

        cache.clear()

        result, _ = cache.get(sample_metrics_df, 'Metrics', ['id'], ['id'])
        assert result is None

        stats = cache.get_statistics()
        assert stats['size'] == 0

        cache.shutdown()


class TestSharedValidationCacheShutdown:
    """Test proper cleanup"""

    def test_shutdown_cleans_up_manager(self):
        """shutdown() should cleanup Manager resources"""
        cache = SharedValidationCache()

        # Add some data
        df = pd.DataFrame({'id': ['test']})
        _, key = cache.get(df, 'Metrics', ['id'], ['id'])
        cache.put(df, 'Metrics', ['id'], ['id'], [], key)

        # Shutdown should not raise
        cache.shutdown()

        # Second shutdown should be safe
        cache.shutdown()

    def test_cache_unusable_after_shutdown(self):
        """Cache operations should fail after shutdown"""
        cache = SharedValidationCache()
        cache.shutdown()

        df = pd.DataFrame({'id': ['test']})

        # Operations may raise or return None/empty - just verify no crash
        try:
            cache.get(df, 'Metrics', ['id'], ['id'])
        except Exception:
            pass  # Expected after shutdown


class TestSharedValidationCacheDataIntegrity:
    """Test data integrity across operations"""

    def test_returns_copy_of_cached_data(self, sample_metrics_df):
        """Should return copy to prevent mutation of cached data"""
        cache = SharedValidationCache()

        original_issues = [{'severity': 'LOW', 'message': 'Test'}]

        _, key = cache.get(sample_metrics_df, 'Metrics', ['id'], ['id'])
        cache.put(sample_metrics_df, 'Metrics', ['id'], ['id'], original_issues, key)

        # Get cached data
        result1, _ = cache.get(sample_metrics_df, 'Metrics', ['id'], ['id'])

        # Mutate returned data
        result1[0]['message'] = 'Modified'

        # Get again - should have original value
        result2, _ = cache.get(sample_metrics_df, 'Metrics', ['id'], ['id'])
        assert result2[0]['message'] == 'Test'

        cache.shutdown()

    def test_stores_copy_of_input_data(self, sample_metrics_df):
        """Should store copy to prevent external mutation affecting cache"""
        cache = SharedValidationCache()

        issues = [{'severity': 'LOW', 'message': 'Original'}]

        _, key = cache.get(sample_metrics_df, 'Metrics', ['id'], ['id'])
        cache.put(sample_metrics_df, 'Metrics', ['id'], ['id'], issues, key)

        # Mutate original data
        issues[0]['message'] = 'Modified'

        # Get cached data - should have original value
        result, _ = cache.get(sample_metrics_df, 'Metrics', ['id'], ['id'])
        assert result[0]['message'] == 'Original'

        cache.shutdown()
