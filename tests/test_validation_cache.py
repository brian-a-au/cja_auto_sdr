"""Tests for validation result caching

Validates that cache:
1. Returns identical results on cache hits
2. Properly handles cache misses
3. Implements LRU eviction correctly
4. Expires entries based on TTL
5. Is thread-safe under concurrent access
6. Provides accurate statistics
7. Handles edge cases (empty DataFrames, errors)
"""
import pytest
import pandas as pd
import logging
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import sys

sys.path.insert(0, '/Users/bau/DEV/cja_auto_sdr_2026')
from cja_sdr_generator import ValidationCache, DataQualityChecker


class TestValidationCache:
    """Test validation caching functionality"""

    def test_cache_miss_on_first_call(self, sample_metrics_df):
        """First validation should be cache miss"""
        cache = ValidationCache(max_size=100, ttl_seconds=3600)

        result = cache.get(
            sample_metrics_df,
            'Metrics',
            ['id', 'name', 'type'],
            ['id', 'name', 'description']
        )

        assert result is None
        stats = cache.get_statistics()
        assert stats['misses'] == 1
        assert stats['hits'] == 0

    def test_cache_hit_on_second_call(self, sample_metrics_df):
        """Second validation with same data should be cache hit"""
        logger = logging.getLogger("test")
        cache = ValidationCache(max_size=100, ttl_seconds=3600, logger=logger)
        checker = DataQualityChecker(logger, validation_cache=cache)

        # First call - should validate and cache
        checker.check_all_quality_issues_optimized(
            sample_metrics_df,
            'Metrics',
            ['id', 'name', 'type'],
            ['id', 'name', 'description']
        )
        first_issues = checker.issues.copy()

        # Second call - should use cache
        checker2 = DataQualityChecker(logger, validation_cache=cache)
        checker2.check_all_quality_issues_optimized(
            sample_metrics_df,
            'Metrics',
            ['id', 'name', 'type'],
            ['id', 'name', 'description']
        )
        second_issues = checker2.issues

        # Results should be identical
        assert len(first_issues) == len(second_issues)
        assert first_issues == second_issues

        # Should have 1 hit
        stats = cache.get_statistics()
        assert stats['hits'] == 1
        assert stats['hit_rate'] == 50.0  # 1 hit out of 2 total

    def test_cache_miss_on_different_data(self, sample_metrics_df, sample_dimensions_df):
        """Different data should cause cache miss"""
        cache = ValidationCache(max_size=100, ttl_seconds=3600)

        # Store metrics result
        cache.put(
            sample_metrics_df,
            'Metrics',
            ['id', 'name', 'type'],
            ['id', 'name', 'description'],
            []
        )

        # Try to get with dimensions - should miss
        result = cache.get(
            sample_dimensions_df,
            'Dimensions',
            ['id', 'name', 'type'],
            ['id', 'name', 'description']
        )

        assert result is None

    def test_cache_ttl_expiration(self, sample_metrics_df):
        """Cache entries should expire after TTL"""
        cache = ValidationCache(max_size=100, ttl_seconds=1)  # 1 second TTL

        # Store result
        cache.put(
            sample_metrics_df,
            'Metrics',
            ['id', 'name', 'type'],
            ['id', 'name', 'description'],
            [{'test': 'issue'}]
        )

        # Should be cached immediately
        result = cache.get(
            sample_metrics_df,
            'Metrics',
            ['id', 'name', 'type'],
            ['id', 'name', 'description']
        )
        assert result is not None

        # Wait for expiration
        time.sleep(1.5)

        # Should be expired now
        result = cache.get(
            sample_metrics_df,
            'Metrics',
            ['id', 'name', 'type'],
            ['id', 'name', 'description']
        )
        assert result is None

    def test_lru_eviction(self):
        """Cache should evict least recently used entries when full"""
        cache = ValidationCache(max_size=2, ttl_seconds=3600)

        # Create 3 different DataFrames
        df1 = pd.DataFrame({'id': [1], 'name': ['a'], 'type': ['x']})
        df2 = pd.DataFrame({'id': [2], 'name': ['b'], 'type': ['y']})
        df3 = pd.DataFrame({'id': [3], 'name': ['c'], 'type': ['z']})

        # Fill cache to max
        cache.put(df1, 'Metrics', ['id', 'name', 'type'], [], [{'issue': '1'}])
        cache.put(df2, 'Metrics', ['id', 'name', 'type'], [], [{'issue': '2'}])

        stats = cache.get_statistics()
        assert stats['size'] == 2
        assert stats['evictions'] == 0

        # Access df1 to make it most recently used
        cache.get(df1, 'Metrics', ['id', 'name', 'type'], [])

        # Add df3 - should evict df2 (least recently used)
        cache.put(df3, 'Metrics', ['id', 'name', 'type'], [], [{'issue': '3'}])

        stats = cache.get_statistics()
        assert stats['size'] == 2
        assert stats['evictions'] == 1

        # df1 and df3 should be cached, df2 should not
        assert cache.get(df1, 'Metrics', ['id', 'name', 'type'], []) is not None
        assert cache.get(df2, 'Metrics', ['id', 'name', 'type'], []) is None
        assert cache.get(df3, 'Metrics', ['id', 'name', 'type'], []) is not None

    def test_thread_safety(self, sample_metrics_df):
        """Cache should be thread-safe"""
        logger = logging.getLogger("test")
        cache = ValidationCache(max_size=100, ttl_seconds=3600, logger=logger)

        results = []
        errors = []

        def validate():
            try:
                c = DataQualityChecker(logger, validation_cache=cache)
                c.check_all_quality_issues_optimized(
                    sample_metrics_df,
                    'Metrics',
                    ['id', 'name', 'type'],
                    ['id', 'name', 'description']
                )
                results.append(c.issues)
            except Exception as e:
                errors.append(e)

        # Run 10 concurrent validations
        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(validate) for _ in range(10)]
            for future in futures:
                future.result()

        # Should have no errors
        assert len(errors) == 0

        # All results should be identical
        assert len(results) == 10
        first_result = results[0]
        for result in results[1:]:
            assert result == first_result

        # Verify cache was used (total requests should equal number of validations)
        stats = cache.get_statistics()
        assert stats['total_requests'] == 10
        # With concurrent execution, we may get mostly misses as threads start simultaneously
        # The important thing is no errors occurred and results are consistent
        assert stats['size'] >= 1  # At least one result cached

    def test_empty_dataframe_cached(self):
        """Empty DataFrames should be cached"""
        logger = logging.getLogger("test")
        cache = ValidationCache(max_size=100, ttl_seconds=3600, logger=logger)
        checker = DataQualityChecker(logger, validation_cache=cache)

        empty_df = pd.DataFrame()

        # First call
        checker.check_all_quality_issues_optimized(
            empty_df, 'Metrics', ['id', 'name', 'type'], ['id', 'name', 'description']
        )
        first_issues = checker.issues.copy()

        # Second call - should use cache
        checker2 = DataQualityChecker(logger, validation_cache=cache)
        checker2.check_all_quality_issues_optimized(
            empty_df, 'Metrics', ['id', 'name', 'type'], ['id', 'name', 'description']
        )
        second_issues = checker2.issues

        # Should be identical
        assert first_issues == second_issues

        # Should have cache hit
        stats = cache.get_statistics()
        assert stats['hits'] == 1

    def test_critical_errors_cached(self):
        """Critical errors (missing fields) should be cached"""
        logger = logging.getLogger("test")
        cache = ValidationCache(max_size=100, ttl_seconds=3600, logger=logger)
        checker = DataQualityChecker(logger, validation_cache=cache)

        # DataFrame missing required fields
        bad_df = pd.DataFrame({'wrong_field': [1, 2, 3]})

        # First call
        checker.check_all_quality_issues_optimized(
            bad_df, 'Metrics', ['id', 'name', 'type'], ['id', 'name', 'description']
        )
        first_issues = checker.issues.copy()

        # Second call - should use cache
        checker2 = DataQualityChecker(logger, validation_cache=cache)
        checker2.check_all_quality_issues_optimized(
            bad_df, 'Metrics', ['id', 'name', 'type'], ['id', 'name', 'description']
        )
        second_issues = checker2.issues

        # Should be identical
        assert first_issues == second_issues
        assert len(first_issues) > 0  # Should have critical error

        # Should have cache hit
        stats = cache.get_statistics()
        assert stats['hits'] == 1

    def test_cache_statistics_accuracy(self, sample_metrics_df):
        """Cache statistics should be accurate"""
        cache = ValidationCache(max_size=10, ttl_seconds=3600)

        # Initial state
        stats = cache.get_statistics()
        assert stats['hits'] == 0
        assert stats['misses'] == 0
        assert stats['size'] == 0
        assert stats['hit_rate'] == 0

        # One miss
        cache.get(sample_metrics_df, 'Metrics', ['id', 'name', 'type'], [])
        stats = cache.get_statistics()
        assert stats['misses'] == 1
        assert stats['hit_rate'] == 0

        # Store and retrieve
        cache.put(sample_metrics_df, 'Metrics', ['id', 'name', 'type'], [], [])
        cache.get(sample_metrics_df, 'Metrics', ['id', 'name', 'type'], [])

        stats = cache.get_statistics()
        assert stats['hits'] == 1
        assert stats['misses'] == 1
        assert stats['hit_rate'] == 50.0
        assert stats['size'] == 1

    def test_performance_improvement(self, sample_metrics_df):
        """Cache should provide significant performance improvement"""
        logger = logging.getLogger("test")
        cache = ValidationCache(max_size=100, ttl_seconds=3600, logger=logger)

        # Time without cache
        checker_no_cache = DataQualityChecker(logger, validation_cache=None)
        start = time.time()
        for _ in range(10):
            checker_no_cache.issues = []  # Reset
            checker_no_cache.check_all_quality_issues_optimized(
                sample_metrics_df, 'Metrics', ['id', 'name', 'type'], ['id', 'name', 'description']
            )
        time_no_cache = time.time() - start

        # Time with cache
        checker_with_cache = DataQualityChecker(logger, validation_cache=cache)
        start = time.time()
        for _ in range(10):
            checker_with_cache.issues = []  # Reset
            checker_with_cache.check_all_quality_issues_optimized(
                sample_metrics_df, 'Metrics', ['id', 'name', 'type'], ['id', 'name', 'description']
            )
        time_with_cache = time.time() - start

        # Cache should be significantly faster (at least 20% faster)
        improvement = (time_no_cache - time_with_cache) / time_no_cache * 100
        print(f"\nPerformance: no_cache={time_no_cache:.3f}s, with_cache={time_with_cache:.3f}s, improvement={improvement:.1f}%")

        # Should be at least 20% faster (conservative estimate for small test datasets)
        assert improvement >= 20, f"Cache only improved performance by {improvement:.1f}% (expected >= 20%)"

    def test_cache_clear(self, sample_metrics_df):
        """Cache clear should remove all entries"""
        cache = ValidationCache(max_size=100, ttl_seconds=3600)

        # Add entries
        cache.put(sample_metrics_df, 'Metrics', ['id', 'name', 'type'], [], [])
        stats = cache.get_statistics()
        assert stats['size'] == 1

        # Clear
        cache.clear()
        stats = cache.get_statistics()
        assert stats['size'] == 0

        # Should be cache miss now
        result = cache.get(sample_metrics_df, 'Metrics', ['id', 'name', 'type'], [])
        assert result is None

    def test_configuration_changes_cache_miss(self, sample_metrics_df):
        """Different configuration should cause cache miss"""
        cache = ValidationCache(max_size=100, ttl_seconds=3600)

        # Store with one configuration
        cache.put(
            sample_metrics_df,
            'Metrics',
            ['id', 'name', 'type'],
            ['id', 'name'],
            [{'issue': 'test'}]
        )

        # Try to get with different critical_fields - should miss
        result = cache.get(
            sample_metrics_df,
            'Metrics',
            ['id', 'name', 'type'],
            ['id', 'name', 'description']  # Different critical fields
        )

        assert result is None

    def test_dataframe_modification_cache_miss(self):
        """Modified DataFrame should cause cache miss"""
        cache = ValidationCache(max_size=100, ttl_seconds=3600)

        # Original DataFrame
        df1 = pd.DataFrame({
            'id': ['m1', 'm2'],
            'name': ['Metric 1', 'Metric 2'],
            'type': ['int', 'currency']
        })

        # Store result
        cache.put(df1, 'Metrics', ['id', 'name', 'type'], [], [{'issue': 'test'}])

        # Modified DataFrame (different data)
        df2 = pd.DataFrame({
            'id': ['m1', 'm3'],  # Changed m2 to m3
            'name': ['Metric 1', 'Metric 3'],
            'type': ['int', 'currency']
        })

        # Should be cache miss
        result = cache.get(df2, 'Metrics', ['id', 'name', 'type'], [])
        assert result is None

    def test_parallel_validation_with_cache(self, sample_metrics_df, sample_dimensions_df):
        """Cache should work correctly with parallel validation"""
        logger = logging.getLogger("test")
        cache = ValidationCache(max_size=100, ttl_seconds=3600, logger=logger)
        checker = DataQualityChecker(logger, validation_cache=cache)

        # First parallel validation (cache miss)
        checker.check_all_parallel(
            metrics_df=sample_metrics_df,
            dimensions_df=sample_dimensions_df,
            metrics_required_fields=['id', 'name', 'type'],
            dimensions_required_fields=['id', 'name', 'type'],
            critical_fields=['id', 'name', 'description'],
            max_workers=2
        )
        first_count = len(checker.issues)

        # Verify both metrics and dimensions were validated
        assert first_count > 0

        # Second parallel validation (should use cache)
        checker2 = DataQualityChecker(logger, validation_cache=cache)
        checker2.check_all_parallel(
            metrics_df=sample_metrics_df,
            dimensions_df=sample_dimensions_df,
            metrics_required_fields=['id', 'name', 'type'],
            dimensions_required_fields=['id', 'name', 'type'],
            critical_fields=['id', 'name', 'description'],
            max_workers=2
        )
        second_count = len(checker2.issues)

        # Second run should also have issues (from cache)
        assert second_count > 0

        # Should have cache hits (both metrics and dimensions)
        stats = cache.get_statistics()
        assert stats['hits'] >= 2  # At least 2 hits (metrics + dimensions)
        assert stats['total_requests'] >= 4  # 2 misses + 2 hits minimum

    def test_no_cache_backward_compatibility(self, sample_metrics_df):
        """No cache (None) should preserve original behavior"""
        logger = logging.getLogger("test")

        # With cache disabled (None)
        checker = DataQualityChecker(logger, validation_cache=None)
        checker.check_all_quality_issues_optimized(
            sample_metrics_df,
            'Metrics',
            ['id', 'name', 'type'],
            ['id', 'name', 'description']
        )
        issues_no_cache = checker.issues

        # Without specifying cache at all (default behavior)
        checker2 = DataQualityChecker(logger)
        checker2.check_all_quality_issues_optimized(
            sample_metrics_df,
            'Metrics',
            ['id', 'name', 'type'],
            ['id', 'name', 'description']
        )
        issues_default = checker2.issues

        # Results should be identical
        assert len(issues_no_cache) == len(issues_default)
        assert issues_no_cache == issues_default
