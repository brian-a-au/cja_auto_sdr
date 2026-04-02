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

import logging
import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cja_auto_sdr.api.cache import ValidationCache
from cja_auto_sdr.generator import DataQualityChecker


class TestValidationCache:
    """Test validation caching functionality"""

    def test_cache_miss_on_first_call(self, sample_metrics_df):
        """First validation should be cache miss"""
        cache = ValidationCache(max_size=100, ttl_seconds=3600)

        result, cache_key = cache.get(
            sample_metrics_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )

        assert result is None
        assert cache_key is not None  # Key should be returned for reuse
        stats = cache.get_statistics()
        assert stats["misses"] == 1
        assert stats["hits"] == 0

    def test_cache_hit_on_second_call(self, sample_metrics_df):
        """Second validation with same data should be cache hit"""
        logger = logging.getLogger("test")
        cache = ValidationCache(max_size=100, ttl_seconds=3600, logger=logger)
        checker = DataQualityChecker(logger, validation_cache=cache)

        # First call - should validate and cache
        checker.check_all_quality_issues_optimized(
            sample_metrics_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )
        first_issues = checker.issues.copy()

        # Second call - should use cache
        checker2 = DataQualityChecker(logger, validation_cache=cache)
        checker2.check_all_quality_issues_optimized(
            sample_metrics_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )
        second_issues = checker2.issues

        # Results should be identical
        assert len(first_issues) == len(second_issues)
        assert first_issues == second_issues

        # Should have 1 hit
        stats = cache.get_statistics()
        assert stats["hits"] == 1
        assert stats["hit_rate"] == pytest.approx(50.0)  # 1 hit out of 2 total

    def test_cache_miss_on_different_data(self, sample_metrics_df, sample_dimensions_df):
        """Different data should cause cache miss"""
        cache = ValidationCache(max_size=100, ttl_seconds=3600)

        # Store metrics result
        cache.put(sample_metrics_df, "Metrics", ["id", "name", "type"], ["id", "name", "description"], [])

        # Try to get with dimensions - should miss
        result, _ = cache.get(sample_dimensions_df, "Dimensions", ["id", "name", "type"], ["id", "name", "description"])

        assert result is None

    def test_cache_ttl_expiration(self, sample_metrics_df):
        """Cache entries should expire after TTL (deterministic, no sleep)"""
        fake_now = [1000000.0]

        def mock_monotonic():
            return fake_now[0]

        with patch("cja_auto_sdr.api.cache.time") as mock_time_module:
            mock_time_module.monotonic = mock_monotonic
            mock_time_module.monotonic_ns = lambda: int(fake_now[0] * 1e9)

            cache = ValidationCache(max_size=100, ttl_seconds=1)  # 1 second TTL

            # Store result
            cache.put(
                sample_metrics_df,
                "Metrics",
                ["id", "name", "type"],
                ["id", "name", "description"],
                [{"test": "issue"}],
            )

            # Should be cached immediately
            result, _ = cache.get(sample_metrics_df, "Metrics", ["id", "name", "type"], ["id", "name", "description"])
            assert result is not None

            # Advance time past TTL
            fake_now[0] += 1.5

            # Should be expired now
            result, _ = cache.get(sample_metrics_df, "Metrics", ["id", "name", "type"], ["id", "name", "description"])
            assert result is None

    def test_lru_eviction(self):
        """Cache should evict least recently used entries when full"""
        cache = ValidationCache(max_size=2, ttl_seconds=3600)

        # Create 3 different DataFrames
        df1 = pd.DataFrame({"id": [1], "name": ["a"], "type": ["x"]})
        df2 = pd.DataFrame({"id": [2], "name": ["b"], "type": ["y"]})
        df3 = pd.DataFrame({"id": [3], "name": ["c"], "type": ["z"]})

        # Fill cache to max
        cache.put(df1, "Metrics", ["id", "name", "type"], [], [{"issue": "1"}])
        cache.put(df2, "Metrics", ["id", "name", "type"], [], [{"issue": "2"}])

        stats = cache.get_statistics()
        assert stats["size"] == 2
        assert stats["evictions"] == 0

        # Access df1 to make it most recently used
        cache.get(df1, "Metrics", ["id", "name", "type"], [])

        # Add df3 - should evict df2 (least recently used)
        cache.put(df3, "Metrics", ["id", "name", "type"], [], [{"issue": "3"}])

        stats = cache.get_statistics()
        assert stats["size"] == 2
        assert stats["evictions"] == 1

        # df1 and df3 should be cached, df2 should not
        result1, _ = cache.get(df1, "Metrics", ["id", "name", "type"], [])
        result2, _ = cache.get(df2, "Metrics", ["id", "name", "type"], [])
        result3, _ = cache.get(df3, "Metrics", ["id", "name", "type"], [])
        assert result1 is not None
        assert result2 is None
        assert result3 is not None

    def test_put_defers_prune_until_capacity_pressure(self):
        """Inserts below capacity should not trigger full-cache expiration scans."""
        cache = ValidationCache(max_size=3, ttl_seconds=3600)
        dfs = [pd.DataFrame({"id": [idx], "name": [f"n{idx}"], "type": ["x"]}) for idx in range(4)]

        with patch.object(cache, "_prune_expired_entries", wraps=cache._prune_expired_entries) as mock_prune:
            cache.put(dfs[0], "Metrics", ["id", "name", "type"], [], [{"issue": "0"}])
            cache.put(dfs[1], "Metrics", ["id", "name", "type"], [], [{"issue": "1"}])
            cache.put(dfs[2], "Metrics", ["id", "name", "type"], [], [{"issue": "2"}])
            assert mock_prune.call_count == 0

            # First insert under pressure should trigger capacity maintenance once.
            cache.put(dfs[3], "Metrics", ["id", "name", "type"], [], [{"issue": "3"}])
            assert mock_prune.call_count == 1

        stats = cache.get_statistics()
        assert stats["size"] == 3
        assert stats["evictions"] == 1

    def test_capacity_pressure_prunes_expired_before_evicting(self):
        """When full, expired entries should be reclaimed before any live-key eviction."""
        fake_now = [1000000.0]

        def mock_monotonic():
            return fake_now[0]

        with patch("cja_auto_sdr.api.cache.time") as mock_time_module:
            mock_time_module.monotonic = mock_monotonic
            mock_time_module.monotonic_ns = lambda: int(fake_now[0] * 1e9)
            cache = ValidationCache(max_size=2, ttl_seconds=1)
            df1 = pd.DataFrame({"id": [1], "name": ["a"], "type": ["x"]})
            df2 = pd.DataFrame({"id": [2], "name": ["b"], "type": ["y"]})
            df3 = pd.DataFrame({"id": [3], "name": ["c"], "type": ["z"]})

            cache.put(df1, "Metrics", ["id", "name", "type"], [], [{"issue": "1"}])
            cache.put(df2, "Metrics", ["id", "name", "type"], [], [{"issue": "2"}])

            fake_now[0] += 1.5

            with patch.object(cache, "_evict_lru", wraps=cache._evict_lru) as mock_evict:
                cache.put(df3, "Metrics", ["id", "name", "type"], [], [{"issue": "3"}])
                assert mock_evict.call_count == 0

            stats = cache.get_statistics()
            assert stats["size"] == 1
            assert stats["evictions"] == 0

    def test_lru_overwrite_refreshes_recency(self):
        """Overwriting an existing key should refresh it to MRU for later eviction decisions."""
        cache = ValidationCache(max_size=2, ttl_seconds=3600)

        df1 = pd.DataFrame({"id": [1], "name": ["a"], "type": ["x"]})
        df2 = pd.DataFrame({"id": [2], "name": ["b"], "type": ["y"]})
        df3 = pd.DataFrame({"id": [3], "name": ["c"], "type": ["z"]})

        cache.put(df1, "Metrics", ["id", "name", "type"], [], [{"issue": "1"}])
        cache.put(df2, "Metrics", ["id", "name", "type"], [], [{"issue": "2"}])

        # Overwrite df1; this write should refresh recency to MRU.
        cache.put(df1, "Metrics", ["id", "name", "type"], [], [{"issue": "1-updated"}])

        # Adding df3 should evict df2, not the recently updated df1.
        cache.put(df3, "Metrics", ["id", "name", "type"], [], [{"issue": "3"}])

        result1, _ = cache.get(df1, "Metrics", ["id", "name", "type"], [])
        result2, _ = cache.get(df2, "Metrics", ["id", "name", "type"], [])
        result3, _ = cache.get(df3, "Metrics", ["id", "name", "type"], [])

        assert result1 is not None
        assert result1[0]["issue"] == "1-updated"
        assert result2 is None
        assert result3 is not None

    def test_overwrite_moves_to_end_only_once(self):
        """Overwrite path should perform a single move_to_end after assignment."""
        cache = ValidationCache(max_size=2, ttl_seconds=3600)
        df1 = pd.DataFrame({"id": [1], "name": ["a"], "type": ["x"]})

        with patch.object(cache._cache, "move_to_end", wraps=cache._cache.move_to_end) as mock_move_to_end:
            cache.put(df1, "Metrics", ["id", "name", "type"], [], [{"issue": "1"}])
            first_put_calls = mock_move_to_end.call_count

            cache.put(df1, "Metrics", ["id", "name", "type"], [], [{"issue": "1-updated"}])
            second_put_calls = mock_move_to_end.call_count - first_put_calls

        assert first_put_calls == 1
        assert second_put_calls == 1

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
                    "Metrics",
                    ["id", "name", "type"],
                    ["id", "name", "description"],
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
        assert stats["total_requests"] == 10
        # With concurrent execution, we may get mostly misses as threads start simultaneously
        # The important thing is no errors occurred and results are consistent
        assert stats["size"] >= 1  # At least one result cached

    def test_empty_dataframe_cached(self):
        """Empty DataFrames should be cached"""
        logger = logging.getLogger("test")
        cache = ValidationCache(max_size=100, ttl_seconds=3600, logger=logger)
        checker = DataQualityChecker(logger, validation_cache=cache)

        empty_df = pd.DataFrame()

        # First call
        checker.check_all_quality_issues_optimized(
            empty_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )
        first_issues = checker.issues.copy()

        # Second call - should use cache
        checker2 = DataQualityChecker(logger, validation_cache=cache)
        checker2.check_all_quality_issues_optimized(
            empty_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )
        second_issues = checker2.issues

        # Should be identical
        assert first_issues == second_issues

        # Should have cache hit
        stats = cache.get_statistics()
        assert stats["hits"] == 1

    def test_critical_errors_cached(self):
        """Critical errors (missing fields) should be cached"""
        logger = logging.getLogger("test")
        cache = ValidationCache(max_size=100, ttl_seconds=3600, logger=logger)
        checker = DataQualityChecker(logger, validation_cache=cache)

        # DataFrame missing required fields
        bad_df = pd.DataFrame({"wrong_field": [1, 2, 3]})

        # First call
        checker.check_all_quality_issues_optimized(
            bad_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )
        first_issues = checker.issues.copy()

        # Second call - should use cache
        checker2 = DataQualityChecker(logger, validation_cache=cache)
        checker2.check_all_quality_issues_optimized(
            bad_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )
        second_issues = checker2.issues

        # Should be identical
        assert first_issues == second_issues
        assert len(first_issues) > 0  # Should have critical error

        # Should have cache hit
        stats = cache.get_statistics()
        assert stats["hits"] == 1

    def test_cache_statistics_accuracy(self, sample_metrics_df):
        """Cache statistics should be accurate"""
        cache = ValidationCache(max_size=10, ttl_seconds=3600)

        # Initial state
        stats = cache.get_statistics()
        assert stats["hits"] == 0
        assert stats["misses"] == 0
        assert stats["size"] == 0
        assert stats["hit_rate"] == 0

        # One miss
        _, cache_key = cache.get(sample_metrics_df, "Metrics", ["id", "name", "type"], [])
        stats = cache.get_statistics()
        assert stats["misses"] == 1
        assert stats["hit_rate"] == 0

        # Store and retrieve (use cache_key to avoid rehashing)
        cache.put(sample_metrics_df, "Metrics", ["id", "name", "type"], [], [], cache_key)
        cache.get(sample_metrics_df, "Metrics", ["id", "name", "type"], [])

        stats = cache.get_statistics()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["hit_rate"] == pytest.approx(50.0)
        assert stats["size"] == 1

    @pytest.mark.slow
    def test_performance_improvement(self, large_sample_dataframe):
        """Cache should provide measurable benefit on a realistic dataset."""
        logger = logging.getLogger("test.validation_cache.performance")
        logger.setLevel(logging.WARNING)
        logger.propagate = False
        if not logger.handlers:
            logger.addHandler(logging.NullHandler())

        required_fields = ["id", "name", "type"]
        critical_fields = ["id", "name", "description"]
        repetitions = 10
        samples = 5

        def _run_iterations(checker: DataQualityChecker) -> None:
            for _ in range(repetitions):
                checker.issues = []  # Reset
                checker.check_all_quality_issues_optimized(
                    large_sample_dataframe,
                    "Metrics",
                    required_fields,
                    critical_fields,
                )

        no_cache_runs = []
        with_cache_runs = []

        for _ in range(samples):
            checker_no_cache = DataQualityChecker(logger, validation_cache=None)
            start = time.perf_counter()
            _run_iterations(checker_no_cache)
            no_cache_runs.append(time.perf_counter() - start)

            cache = ValidationCache(max_size=100, ttl_seconds=3600, logger=logger)
            checker_with_cache = DataQualityChecker(logger, validation_cache=cache)
            start = time.perf_counter()
            _run_iterations(checker_with_cache)
            with_cache_runs.append(time.perf_counter() - start)

            stats = cache.get_statistics()
            assert stats["hits"] == repetitions - 1
            assert stats["misses"] == 1

        time_no_cache = sorted(no_cache_runs)[len(no_cache_runs) // 2]
        time_with_cache = sorted(with_cache_runs)[len(with_cache_runs) // 2]

        improvement = (time_no_cache - time_with_cache) / time_no_cache * 100
        print(
            f"\nPerformance (median of {samples} runs, dataset size={len(large_sample_dataframe)}): "
            f"no_cache={time_no_cache:.3f}s, with_cache={time_with_cache:.3f}s, improvement={improvement:.1f}%",
        )

        assert improvement >= 5, f"Cache only improved performance by {improvement:.1f}% (expected >= 5%)"

    def test_cache_clear(self, sample_metrics_df):
        """Cache clear should remove all entries"""
        cache = ValidationCache(max_size=100, ttl_seconds=3600)

        # Add entries
        cache.put(sample_metrics_df, "Metrics", ["id", "name", "type"], [], [])
        stats = cache.get_statistics()
        assert stats["size"] == 1

        # Clear
        cache.clear()
        stats = cache.get_statistics()
        assert stats["size"] == 0

        # Should be cache miss now
        result, _ = cache.get(sample_metrics_df, "Metrics", ["id", "name", "type"], [])
        assert result is None

    def test_configuration_changes_cache_miss(self, sample_metrics_df):
        """Different configuration should cause cache miss"""
        cache = ValidationCache(max_size=100, ttl_seconds=3600)

        # Store with one configuration
        cache.put(sample_metrics_df, "Metrics", ["id", "name", "type"], ["id", "name"], [{"issue": "test"}])

        # Try to get with different critical_fields - should miss
        result, _ = cache.get(
            sample_metrics_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],  # Different critical fields
        )

        assert result is None

    def test_dataframe_modification_cache_miss(self):
        """Modified DataFrame should cause cache miss"""
        cache = ValidationCache(max_size=100, ttl_seconds=3600)

        # Original DataFrame
        df1 = pd.DataFrame({"id": ["m1", "m2"], "name": ["Metric 1", "Metric 2"], "type": ["int", "currency"]})

        # Store result
        cache.put(df1, "Metrics", ["id", "name", "type"], [], [{"issue": "test"}])

        # Modified DataFrame (different data)
        df2 = pd.DataFrame(
            {
                "id": ["m1", "m3"],  # Changed m2 to m3
                "name": ["Metric 1", "Metric 3"],
                "type": ["int", "currency"],
            },
        )

        # Should be cache miss
        result, _ = cache.get(df2, "Metrics", ["id", "name", "type"], [])
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
            metrics_required_fields=["id", "name", "type"],
            dimensions_required_fields=["id", "name", "type"],
            critical_fields=["id", "name", "description"],
            max_workers=2,
        )
        first_count = len(checker.issues)

        # Verify both metrics and dimensions were validated
        assert first_count > 0

        # Second parallel validation (should use cache)
        checker2 = DataQualityChecker(logger, validation_cache=cache)
        checker2.check_all_parallel(
            metrics_df=sample_metrics_df,
            dimensions_df=sample_dimensions_df,
            metrics_required_fields=["id", "name", "type"],
            dimensions_required_fields=["id", "name", "type"],
            critical_fields=["id", "name", "description"],
            max_workers=2,
        )
        second_count = len(checker2.issues)

        # Second run should also have issues (from cache)
        assert second_count > 0

        # Should have cache hits (both metrics and dimensions)
        stats = cache.get_statistics()
        assert stats["hits"] >= 2  # At least 2 hits (metrics + dimensions)
        assert stats["total_requests"] >= 4  # 2 misses + 2 hits minimum

    def test_no_cache_backward_compatibility(self, sample_metrics_df):
        """No cache (None) should preserve original behavior"""
        logger = logging.getLogger("test")

        # With cache disabled (None)
        checker = DataQualityChecker(logger, validation_cache=None)
        checker.check_all_quality_issues_optimized(
            sample_metrics_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )
        issues_no_cache = checker.issues

        # Without specifying cache at all (default behavior)
        checker2 = DataQualityChecker(logger)
        checker2.check_all_quality_issues_optimized(
            sample_metrics_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )
        issues_default = checker2.issues

        # Results should be identical
        assert len(issues_no_cache) == len(issues_default)
        assert issues_no_cache == issues_default

    def test_cache_key_reuse_optimization(self, sample_metrics_df):
        """Test that cache key from get() can be reused in put() to avoid rehashing"""
        cache = ValidationCache(max_size=100, ttl_seconds=3600)

        # Get returns (None, cache_key) on miss
        result, cache_key = cache.get(
            sample_metrics_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )
        assert result is None
        assert cache_key is not None
        assert "Metrics:" in cache_key  # Key should contain item_type

        # Put with the same cache_key should work
        test_issues = [{"test": "issue"}]
        cache.put(
            sample_metrics_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
            test_issues,
            cache_key,  # Reuse cache_key
        )

        # Get should now return the cached issues
        cached_result, _ = cache.get(
            sample_metrics_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )
        assert cached_result is not None
        assert len(cached_result) == 1
        assert cached_result[0]["test"] == "issue"

        # Verify cache stats
        stats = cache.get_statistics()
        assert stats["hits"] == 1
        assert stats["misses"] == 1

    def test_cache_key_consistency(self, sample_metrics_df):
        """Test that cache key is consistent for same inputs"""
        cache = ValidationCache(max_size=100, ttl_seconds=3600)

        # Get key twice with same parameters
        _, key1 = cache.get(sample_metrics_df, "Metrics", ["id", "name", "type"], ["id", "name"])
        _, key2 = cache.get(sample_metrics_df, "Metrics", ["id", "name", "type"], ["id", "name"])

        # Keys should be identical
        assert key1 == key2

    def test_cache_key_differs_for_different_config(self, sample_metrics_df):
        """Test that cache key differs when config changes"""
        cache = ValidationCache(max_size=100, ttl_seconds=3600)

        _, key1 = cache.get(sample_metrics_df, "Metrics", ["id", "name", "type"], ["id", "name"])
        _, key2 = cache.get(
            sample_metrics_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],  # Different critical fields
        )

        # Keys should be different
        assert key1 != key2

    def test_put_without_cache_key_backward_compatible(self, sample_metrics_df):
        """Test that put() works without cache_key (backward compatibility)"""
        cache = ValidationCache(max_size=100, ttl_seconds=3600)

        # Put without providing cache_key (should compute it internally)
        test_issues = [{"severity": "HIGH", "message": "test"}]
        cache.put(
            sample_metrics_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
            test_issues,
            # No cache_key parameter
        )

        # Should be retrievable
        result, _ = cache.get(sample_metrics_df, "Metrics", ["id", "name", "type"], ["id", "name", "description"])
        assert result is not None
        assert len(result) == 1
        assert result[0]["severity"] == "HIGH"

    def test_invalid_cache_configuration_raises(self):
        """Invalid size/TTL should fail fast during initialization."""
        with pytest.raises(ValueError, match="max_size must be >= 1"):
            ValidationCache(max_size=0, ttl_seconds=3600)

        with pytest.raises(ValueError, match="ttl_seconds must be > 0"):
            ValidationCache(max_size=10, ttl_seconds=0)


# ---------------------------------------------------------------------------
# Coverage gap tests (moved from test_small_gap_coverage.py)
# ---------------------------------------------------------------------------


def test_validation_cache_capacity_clear_fallback_warns_and_clears_cache() -> None:
    logger = MagicMock()
    cache = ValidationCache(max_size=1, ttl_seconds=3600, logger=logger)
    cache._cache["existing"] = ([{"issue": "old"}], 1.0)

    with patch.object(cache, "_evict_lru", side_effect=lambda debug_enabled=False: None):
        with cache._lock:
            cache._ensure_capacity_for_new_entry(now=2.0)

    logger.warning.assert_called_once()
    assert not cache._cache
