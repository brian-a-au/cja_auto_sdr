"""Tests for PerformanceTracker in cja_auto_sdr.core.perf

Validates:
1. MAX_METRICS eviction when capacity is exceeded (lines 29-30)
2. add_cache_statistics logging output (lines 59-74)
3. add_cache_statistics with hits > 0 shows estimated time saved (lines 69-72)
4. add_cache_statistics with zero total_requests logs nothing
"""

import logging
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cja_auto_sdr.core.perf import PerformanceTracker


class TestMaxMetricsEviction:
    """Test that metrics dict evicts oldest entry when MAX_METRICS is reached"""

    def test_evicts_oldest_when_at_capacity(self):
        """When metrics dict reaches MAX_METRICS, adding a new entry drops the oldest"""
        logger = logging.getLogger("test_perf_eviction")
        tracker = PerformanceTracker(logger)

        # Use a small limit to make the test fast
        tracker.MAX_METRICS = 3

        # Fill up to capacity
        tracker.start("op_a")
        tracker.end("op_a")
        tracker.start("op_b")
        tracker.end("op_b")
        tracker.start("op_c")
        tracker.end("op_c")

        assert len(tracker.metrics) == 3
        assert "op_a" in tracker.metrics

        # Adding one more should evict the oldest (op_a)
        tracker.start("op_d")
        tracker.end("op_d")

        assert len(tracker.metrics) == 3
        assert "op_a" not in tracker.metrics
        assert "op_b" in tracker.metrics
        assert "op_c" in tracker.metrics
        assert "op_d" in tracker.metrics

    def test_evicts_sequentially(self):
        """Repeated inserts beyond capacity keep evicting the oldest"""
        logger = logging.getLogger("test_perf_eviction_seq")
        tracker = PerformanceTracker(logger)
        tracker.MAX_METRICS = 2

        tracker.start("first")
        tracker.end("first")
        tracker.start("second")
        tracker.end("second")

        # At capacity: {first, second}
        tracker.start("third")
        tracker.end("third")
        # Evicts first -> {second, third}
        assert "first" not in tracker.metrics
        assert "second" in tracker.metrics
        assert "third" in tracker.metrics

        tracker.start("fourth")
        tracker.end("fourth")
        # Evicts second -> {third, fourth}
        assert "second" not in tracker.metrics
        assert "third" in tracker.metrics
        assert "fourth" in tracker.metrics

    def test_eviction_at_default_max_metrics(self):
        """Verify eviction fires at the actual MAX_METRICS=500 boundary"""
        logger = logging.getLogger("test_perf_default_max")
        tracker = PerformanceTracker(logger)

        # Pre-populate metrics dict directly to avoid timing 500 operations
        for i in range(tracker.MAX_METRICS):
            tracker.metrics[f"op_{i}"] = float(i)

        assert len(tracker.metrics) == 500
        assert "op_0" in tracker.metrics

        # Adding one more via start/end should evict op_0
        tracker.start("overflow")
        tracker.end("overflow")

        assert len(tracker.metrics) == 500
        assert "op_0" not in tracker.metrics
        assert "overflow" in tracker.metrics


class TestAddCacheStatistics:
    """Test add_cache_statistics logging (lines 59-74)"""

    def _make_cache_stub(self, *, total_requests, hits, misses, hit_rate, size, max_size, evictions):
        """Create a simple stub object with a get_statistics method."""

        class CacheStub:
            def get_statistics(self_inner):
                return {
                    "total_requests": total_requests,
                    "hits": hits,
                    "misses": misses,
                    "hit_rate": hit_rate,
                    "size": size,
                    "max_size": max_size,
                    "evictions": evictions,
                }

        return CacheStub()

    def test_logs_cache_stats_when_requests_exist(self, caplog):
        """When total_requests > 0, cache stats are logged"""
        logger = logging.getLogger("test_cache_stats")
        tracker = PerformanceTracker(logger)

        cache = self._make_cache_stub(
            total_requests=100,
            hits=0,
            misses=100,
            hit_rate=0.0,
            size=50,
            max_size=200,
            evictions=0,
        )

        with caplog.at_level(logging.INFO, logger="test_cache_stats"):
            tracker.add_cache_statistics(cache)

        assert "VALIDATION CACHE STATISTICS" in caplog.text
        assert "Cache Hits:        0" in caplog.text
        assert "Cache Misses:      100" in caplog.text
        assert "Hit Rate:          0.0%" in caplog.text
        assert "Cache Size:        50/200" in caplog.text
        assert "Evictions:         0" in caplog.text
        # No hits, so estimated time saved should NOT appear
        assert "Estimated Time Saved" not in caplog.text

    def test_logs_estimated_time_saved_when_hits_positive(self, caplog):
        """When hits > 0, estimated time saved line is included"""
        logger = logging.getLogger("test_cache_time_saved")
        tracker = PerformanceTracker(logger)

        cache = self._make_cache_stub(
            total_requests=200,
            hits=100,
            misses=100,
            hit_rate=50.0,
            size=80,
            max_size=200,
            evictions=5,
        )

        with caplog.at_level(logging.INFO, logger="test_cache_time_saved"):
            tracker.add_cache_statistics(cache)

        assert "VALIDATION CACHE STATISTICS" in caplog.text
        assert "Cache Hits:        100" in caplog.text
        assert "Cache Misses:      100" in caplog.text
        assert "Hit Rate:          50.0%" in caplog.text
        assert "Evictions:         5" in caplog.text
        # 100 hits * 0.049 = 4.90s
        assert "Estimated Time Saved: 4.90s" in caplog.text

    def test_no_logging_when_zero_requests(self, caplog):
        """When total_requests == 0, nothing is logged"""
        logger = logging.getLogger("test_cache_no_requests")
        tracker = PerformanceTracker(logger)

        cache = self._make_cache_stub(
            total_requests=0,
            hits=0,
            misses=0,
            hit_rate=0.0,
            size=0,
            max_size=200,
            evictions=0,
        )

        with caplog.at_level(logging.INFO, logger="test_cache_no_requests"):
            tracker.add_cache_statistics(cache)

        assert "VALIDATION CACHE STATISTICS" not in caplog.text

    def test_estimated_time_saved_calculation(self, caplog):
        """Verify the estimated time saved formula: hits * 0.049"""
        logger = logging.getLogger("test_cache_time_calc")
        tracker = PerformanceTracker(logger)

        cache = self._make_cache_stub(
            total_requests=10,
            hits=1,
            misses=9,
            hit_rate=10.0,
            size=5,
            max_size=100,
            evictions=0,
        )

        with caplog.at_level(logging.INFO, logger="test_cache_time_calc"):
            tracker.add_cache_statistics(cache)

        # 1 hit * 0.049 = 0.05s (rounded to 2 decimals)
        assert "Estimated Time Saved: 0.05s" in caplog.text
