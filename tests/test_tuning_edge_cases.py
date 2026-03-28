"""Edge-case tests for api/tuning.py.

Covers: config clamping, threshold boundaries, cooldown,
rolling window accumulation, inverted bounds.
"""

from unittest.mock import patch

import pytest

from cja_auto_sdr.api.tuning import APIWorkerTuner
from cja_auto_sdr.core.config import APITuningConfig

# ==================== Configuration Semantics ====================


class TestConfigSemantics:
    """Verify tuner respects config without crashing on edge cases."""

    def test_valid_config_accepted(self):
        config = APITuningConfig(min_workers=1, max_workers=5)
        tuner = APIWorkerTuner(config=config, initial_workers=3)
        assert tuner.current_workers == 3

    def test_min_workers_greater_than_max_does_not_raise(self):
        """Inverted bounds: resolved workers clamp to min_workers."""
        config = APITuningConfig(min_workers=10, max_workers=5)
        tuner = APIWorkerTuner(config=config, initial_workers=3)
        # max(min_workers=10, min(initial=3, max_workers=5)) = max(10, 3) = 10
        assert tuner.current_workers == 10

    def test_initial_workers_clamped_to_max(self):
        config = APITuningConfig(min_workers=1, max_workers=5)
        tuner = APIWorkerTuner(config=config, initial_workers=100)
        assert tuner.current_workers == 5

    def test_initial_workers_clamped_to_min(self):
        config = APITuningConfig(min_workers=3, max_workers=10)
        tuner = APIWorkerTuner(config=config, initial_workers=1)
        assert tuner.current_workers == 3

    def test_sample_window_zero_immediate_adjustment(self):
        """sample_window=0: first recording can trigger adjustment."""
        config = APITuningConfig(
            min_workers=1,
            max_workers=5,
            sample_window=0,
            cooldown_seconds=0,
            scale_up_threshold_ms=500.0,
        )
        tuner = APIWorkerTuner(config=config, initial_workers=2)

        # With sample_window=0, the "not enough samples" guard
        # (len < sample_window) is always False, so first call decides
        result = tuner.record_response_time(100.0)  # Below scale_up threshold
        # Whether it adjusts depends on if avg < scale_up_threshold
        # 100.0 < 500.0 → scale up from 2 to 3
        assert result == 3


# ==================== Threshold Boundaries ====================


class TestThresholdBoundaries:
    """Test exact-threshold behavior (strictly less / strictly greater)."""

    def _make_tuner(self, initial_workers=3, **config_kwargs):
        defaults = {
            "min_workers": 1,
            "max_workers": 10,
            "sample_window": 1,
            "cooldown_seconds": 0,
            "scale_up_threshold_ms": 200.0,
            "scale_down_threshold_ms": 2000.0,
        }
        defaults.update(config_kwargs)
        config = APITuningConfig(**defaults)
        return APIWorkerTuner(config=config, initial_workers=initial_workers)

    def test_avg_exactly_at_scale_up_threshold_no_change(self):
        """avg == scale_up_threshold_ms: no adjustment (< is strict)."""
        tuner = self._make_tuner()
        result = tuner.record_response_time(200.0)
        assert result is None

    def test_avg_below_scale_up_threshold_scales_up(self):
        tuner = self._make_tuner()
        result = tuner.record_response_time(199.0)
        assert result == 4  # 3 -> 4

    def test_avg_exactly_at_scale_down_threshold_no_change(self):
        """avg == scale_down_threshold_ms: no adjustment (> is strict)."""
        tuner = self._make_tuner()
        result = tuner.record_response_time(2000.0)
        assert result is None

    def test_avg_above_scale_down_threshold_scales_down(self):
        tuner = self._make_tuner()
        result = tuner.record_response_time(2001.0)
        assert result == 2  # 3 -> 2

    def test_zero_ms_response_time_valid(self):
        """0ms response time is valid — below scale_up threshold."""
        tuner = self._make_tuner()
        result = tuner.record_response_time(0.0)
        assert result == 4  # 0.0 < 200.0 → scale up

    def test_at_max_workers_no_scale_up(self):
        tuner = self._make_tuner(initial_workers=10)
        result = tuner.record_response_time(50.0)  # Well below threshold
        assert result is None  # Already at max


# ==================== Cooldown ====================


class TestCooldown:
    """Verify cooldown prevents rapid adjustments."""

    def test_adjustment_rejected_during_cooldown(self):
        config = APITuningConfig(
            min_workers=1,
            max_workers=10,
            sample_window=1,
            cooldown_seconds=60,
            scale_up_threshold_ms=500.0,
        )
        tuner = APIWorkerTuner(config=config, initial_workers=3)

        # First adjustment succeeds
        result1 = tuner.record_response_time(100.0)
        assert result1 == 4

        # Second immediately rejected due to cooldown
        result2 = tuner.record_response_time(100.0)
        assert result2 is None

    def test_adjustment_allowed_after_cooldown_expires(self):
        config = APITuningConfig(
            min_workers=1,
            max_workers=10,
            sample_window=1,
            cooldown_seconds=5,
            scale_up_threshold_ms=500.0,
        )
        tuner = APIWorkerTuner(config=config, initial_workers=3)

        # First adjustment
        result1 = tuner.record_response_time(100.0)
        assert result1 == 4

        # Simulate cooldown expiry
        with patch("cja_auto_sdr.api.tuning.time") as mock_time:
            mock_time.time.return_value = tuner._last_adjustment_time + 10  # Well past cooldown
            result2 = tuner.record_response_time(100.0)
            assert result2 == 5


# ==================== Rolling Window ====================


class TestRollingWindow:
    """Verify rolling window correctly manages samples."""

    def test_window_drops_old_entries(self):
        config = APITuningConfig(
            min_workers=1,
            max_workers=10,
            sample_window=3,
            cooldown_seconds=0,
            scale_up_threshold_ms=200.0,
            scale_down_threshold_ms=2000.0,
        )
        tuner = APIWorkerTuner(config=config, initial_workers=5)

        # Record values that average in the middle (no adjustment)
        tuner.record_response_time(500.0)
        tuner.record_response_time(500.0)
        tuner.record_response_time(500.0)  # Window full, avg=500 → no change

        with tuner._lock:
            assert len(tuner._response_times) <= 3

    def test_statistics_remain_consistent(self):
        config = APITuningConfig(min_workers=1, max_workers=10, sample_window=5, cooldown_seconds=0)
        tuner = APIWorkerTuner(config=config, initial_workers=3)

        for i in range(100):
            tuner.record_response_time(float(i))

        stats = tuner.get_statistics()
        assert stats["total_requests"] == 100
        assert stats["average_response_ms"] == pytest.approx(sum(range(100)) / 100)
        assert stats["sample_window_size"] <= 5
