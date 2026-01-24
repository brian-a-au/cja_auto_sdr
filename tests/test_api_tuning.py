"""Tests for API worker auto-tuning

Validates that APIWorkerTuner:
1. Starts with correct initial worker count
2. Scales up when responses are fast
3. Scales down when responses are slow
4. Respects min/max worker bounds
5. Enforces cooldown between adjustments
6. Is thread-safe under concurrent access
7. Provides accurate statistics
8. Properly resets state
"""
import pytest
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cja_sdr_generator import APIWorkerTuner, APITuningConfig


class TestAPIWorkerTunerBasics:
    """Test basic API worker tuner functionality"""

    def test_initial_worker_count(self):
        """Tuner should start with correct initial worker count"""
        tuner = APIWorkerTuner(initial_workers=5)
        assert tuner.current_workers == 5

    def test_respects_min_workers(self):
        """Initial workers should not go below minimum"""
        config = APITuningConfig(min_workers=3, max_workers=10)
        tuner = APIWorkerTuner(config=config, initial_workers=1)
        assert tuner.current_workers == 3

    def test_respects_max_workers(self):
        """Initial workers should not exceed maximum"""
        config = APITuningConfig(min_workers=1, max_workers=5)
        tuner = APIWorkerTuner(config=config, initial_workers=10)
        assert tuner.current_workers == 5

    def test_no_adjustment_before_sample_window(self):
        """Should not adjust before collecting enough samples"""
        config = APITuningConfig(sample_window=5)
        tuner = APIWorkerTuner(config=config, initial_workers=3)

        # Record less than sample_window responses
        for _ in range(4):
            result = tuner.record_response_time(50)  # Fast responses
            assert result is None

        assert tuner.current_workers == 3


class TestAPIWorkerTunerScaling:
    """Test worker scaling behavior"""

    def test_scales_up_on_fast_responses(self):
        """Should add workers when responses are faster than threshold"""
        config = APITuningConfig(
            min_workers=1,
            max_workers=10,
            scale_up_threshold_ms=200,
            scale_down_threshold_ms=2000,
            sample_window=3,
            cooldown_seconds=0  # Disable cooldown for testing
        )
        tuner = APIWorkerTuner(config=config, initial_workers=3)

        # Record fast responses
        for i in range(3):
            result = tuner.record_response_time(50)  # 50ms - below scale_up threshold

        # Should have scaled up
        assert tuner.current_workers == 4

    def test_scales_down_on_slow_responses(self):
        """Should remove workers when responses are slower than threshold"""
        config = APITuningConfig(
            min_workers=1,
            max_workers=10,
            scale_up_threshold_ms=200,
            scale_down_threshold_ms=2000,
            sample_window=3,
            cooldown_seconds=0  # Disable cooldown for testing
        )
        tuner = APIWorkerTuner(config=config, initial_workers=5)

        # Record slow responses
        for i in range(3):
            result = tuner.record_response_time(3000)  # 3000ms - above scale_down threshold

        # Should have scaled down
        assert tuner.current_workers == 4

    def test_no_change_within_thresholds(self):
        """Should not adjust when response times are within acceptable range"""
        config = APITuningConfig(
            min_workers=1,
            max_workers=10,
            scale_up_threshold_ms=200,
            scale_down_threshold_ms=2000,
            sample_window=3,
            cooldown_seconds=0
        )
        tuner = APIWorkerTuner(config=config, initial_workers=5)

        # Record moderate responses (between thresholds)
        for i in range(3):
            tuner.record_response_time(500)  # 500ms - within range

        assert tuner.current_workers == 5

    def test_does_not_exceed_max_workers(self):
        """Should not scale beyond max_workers"""
        config = APITuningConfig(
            min_workers=1,
            max_workers=3,
            scale_up_threshold_ms=200,
            sample_window=3,
            cooldown_seconds=0
        )
        tuner = APIWorkerTuner(config=config, initial_workers=3)

        # Record fast responses
        for i in range(3):
            result = tuner.record_response_time(50)

        # Should not exceed max
        assert tuner.current_workers == 3
        assert result is None  # No adjustment made

    def test_does_not_go_below_min_workers(self):
        """Should not scale below min_workers"""
        config = APITuningConfig(
            min_workers=2,
            max_workers=10,
            scale_down_threshold_ms=2000,
            sample_window=3,
            cooldown_seconds=0
        )
        tuner = APIWorkerTuner(config=config, initial_workers=2)

        # Record slow responses
        for i in range(3):
            result = tuner.record_response_time(5000)

        # Should not go below min
        assert tuner.current_workers == 2
        assert result is None  # No adjustment made


class TestAPIWorkerTunerCooldown:
    """Test cooldown between adjustments"""

    def test_enforces_cooldown_period(self):
        """Should not adjust during cooldown period"""
        config = APITuningConfig(
            min_workers=1,
            max_workers=10,
            scale_up_threshold_ms=200,
            sample_window=3,
            cooldown_seconds=1.0  # 1 second cooldown
        )
        tuner = APIWorkerTuner(config=config, initial_workers=3)

        # First adjustment
        for i in range(3):
            tuner.record_response_time(50)
        assert tuner.current_workers == 4

        # Try to adjust again immediately - should be in cooldown
        for i in range(3):
            result = tuner.record_response_time(50)
        assert tuner.current_workers == 4  # No change due to cooldown

    def test_allows_adjustment_after_cooldown(self):
        """Should allow adjustment after cooldown expires"""
        config = APITuningConfig(
            min_workers=1,
            max_workers=10,
            scale_up_threshold_ms=200,
            sample_window=3,
            cooldown_seconds=0.1  # 100ms cooldown
        )
        tuner = APIWorkerTuner(config=config, initial_workers=3)

        # First adjustment
        for i in range(3):
            tuner.record_response_time(50)
        assert tuner.current_workers == 4

        # Wait for cooldown
        time.sleep(0.15)

        # Should allow second adjustment
        for i in range(3):
            tuner.record_response_time(50)
        assert tuner.current_workers == 5


class TestAPIWorkerTunerStatistics:
    """Test statistics tracking"""

    def test_tracks_total_requests(self):
        """Should track total request count"""
        tuner = APIWorkerTuner(initial_workers=3)

        for i in range(10):
            tuner.record_response_time(100)

        stats = tuner.get_statistics()
        assert stats['total_requests'] == 10

    def test_tracks_scale_ups(self):
        """Should track scale-up count"""
        config = APITuningConfig(
            min_workers=1,
            max_workers=10,
            scale_up_threshold_ms=200,
            sample_window=3,
            cooldown_seconds=0
        )
        tuner = APIWorkerTuner(config=config, initial_workers=3)

        # Trigger scale-up
        for i in range(3):
            tuner.record_response_time(50)

        stats = tuner.get_statistics()
        assert stats['scale_ups'] == 1

    def test_tracks_scale_downs(self):
        """Should track scale-down count"""
        config = APITuningConfig(
            min_workers=1,
            max_workers=10,
            scale_down_threshold_ms=2000,
            sample_window=3,
            cooldown_seconds=0
        )
        tuner = APIWorkerTuner(config=config, initial_workers=5)

        # Trigger scale-down
        for i in range(3):
            tuner.record_response_time(3000)

        stats = tuner.get_statistics()
        assert stats['scale_downs'] == 1

    def test_calculates_average_response_time(self):
        """Should calculate average response time correctly"""
        tuner = APIWorkerTuner(initial_workers=3)

        response_times = [100, 200, 300, 400, 500]
        for rt in response_times:
            tuner.record_response_time(rt)

        stats = tuner.get_statistics()
        expected_avg = sum(response_times) / len(response_times)
        assert abs(stats['average_response_ms'] - expected_avg) < 0.01


class TestAPIWorkerTunerThreadSafety:
    """Test thread safety"""

    def test_concurrent_response_recording(self):
        """Should handle concurrent response recordings safely"""
        config = APITuningConfig(
            min_workers=1,
            max_workers=50,
            sample_window=100,
            cooldown_seconds=0
        )
        tuner = APIWorkerTuner(config=config, initial_workers=10)

        errors = []

        def record_responses():
            try:
                for _ in range(100):
                    tuner.record_response_time(100)
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(record_responses) for _ in range(10)]
            for future in futures:
                future.result()

        assert len(errors) == 0
        stats = tuner.get_statistics()
        assert stats['total_requests'] == 1000

    def test_concurrent_worker_reads(self):
        """Should handle concurrent worker count reads safely"""
        tuner = APIWorkerTuner(initial_workers=5)

        results = []

        def read_workers():
            for _ in range(100):
                results.append(tuner.current_workers)

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(read_workers) for _ in range(10)]
            for future in futures:
                future.result()

        # All reads should return valid worker counts
        assert all(isinstance(r, int) and r > 0 for r in results)


class TestAPIWorkerTunerReset:
    """Test reset functionality"""

    def test_reset_clears_samples(self):
        """Reset should clear response time samples"""
        config = APITuningConfig(sample_window=5)
        tuner = APIWorkerTuner(config=config, initial_workers=3)

        for _ in range(3):
            tuner.record_response_time(100)

        tuner.reset()

        stats = tuner.get_statistics()
        assert stats['sample_window_size'] == 0

    def test_reset_keeps_worker_count_by_default(self):
        """Reset should keep current worker count by default"""
        tuner = APIWorkerTuner(initial_workers=5)
        tuner.reset()

        assert tuner.current_workers == 5

    def test_reset_can_set_new_worker_count(self):
        """Reset can optionally set new worker count"""
        config = APITuningConfig(min_workers=1, max_workers=10)
        tuner = APIWorkerTuner(config=config, initial_workers=5)

        tuner.reset(workers=8)

        assert tuner.current_workers == 8

    def test_reset_respects_bounds(self):
        """Reset should respect min/max bounds"""
        config = APITuningConfig(min_workers=2, max_workers=8)
        tuner = APIWorkerTuner(config=config, initial_workers=5)

        tuner.reset(workers=1)
        assert tuner.current_workers == 2

        tuner.reset(workers=100)
        assert tuner.current_workers == 8


class TestAPITuningConfig:
    """Test configuration dataclass"""

    def test_default_values(self):
        """Config should have sensible defaults"""
        config = APITuningConfig()

        assert config.min_workers == 1
        assert config.max_workers == 10
        assert config.scale_up_threshold_ms == 200.0
        assert config.scale_down_threshold_ms == 2000.0
        assert config.sample_window == 5
        assert config.cooldown_seconds == 10.0

    def test_custom_values(self):
        """Config should accept custom values"""
        config = APITuningConfig(
            min_workers=2,
            max_workers=20,
            scale_up_threshold_ms=100.0,
            scale_down_threshold_ms=5000.0,
            sample_window=10,
            cooldown_seconds=5.0
        )

        assert config.min_workers == 2
        assert config.max_workers == 20
        assert config.scale_up_threshold_ms == 100.0
        assert config.scale_down_threshold_ms == 5000.0
        assert config.sample_window == 10
        assert config.cooldown_seconds == 5.0
