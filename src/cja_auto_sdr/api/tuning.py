"""API worker auto-tuning for CJA Auto SDR."""

import logging
import threading
import time
from dataclasses import replace
from typing import Any

from cja_auto_sdr.core.config import APITuningConfig


class APIWorkerTuner:
    """
    Thread-safe auto-tuner for API worker pool size.

    Dynamically adjusts the number of concurrent API workers based on
    response time measurements. Scales up when responses are fast (API
    has capacity) and scales down when responses are slow (API is stressed).

    Algorithm:
    - Maintains a rolling window of response times
    - After sample_window measurements, calculates average
    - If avg < scale_up_threshold_ms: increase workers (if below max)
    - If avg > scale_down_threshold_ms: decrease workers (if above min)
    - Enforces cooldown period between adjustments

    Thread Safety:
    - Uses threading.Lock for all state updates
    - Safe for use with ThreadPoolExecutor

    Example:
        tuner = APIWorkerTuner(config=APITuningConfig(min_workers=1, max_workers=10))

        # After each API call
        new_count = tuner.record_response_time(duration_ms)
        if new_count is not None:
            executor.resize(new_count)  # Adjust pool size
    """

    def __init__(self, config: APITuningConfig = None, initial_workers: int = 3, logger: logging.Logger | None = None):
        """
        Initialize the API worker tuner.

        Args:
            config: Tuning configuration (uses defaults if not provided)
            initial_workers: Starting number of workers
            logger: Logger instance for tuning decisions
        """
        self.config = config or APITuningConfig()
        self.logger = logger or logging.getLogger(__name__)

        # Guard against invalid direct-construction configs. fetch.py already
        # clamps per-data-view windows; do the same here so the tuner behaves
        # consistently even when constructed directly in tests or library use.
        if self.config.sample_window < 1:
            original_window = self.config.sample_window
            self.config = replace(self.config, sample_window=1)
            self.logger.debug(
                "API tuner sample_window clamped from %s to %s for direct tuner use",
                original_window,
                self.config.sample_window,
            )

        # Current worker count
        self._current_workers = max(self.config.min_workers, min(initial_workers, self.config.max_workers))

        # Rolling window of response times
        self._response_times: list[float] = []
        self._last_adjustment_time = 0.0

        # Thread safety
        self._lock = threading.Lock()

        # Statistics
        self._total_requests = 0
        self._scale_ups = 0
        self._scale_downs = 0
        self._total_response_time_ms = 0.0

    @property
    def current_workers(self) -> int:
        """Get current worker count (thread-safe)."""
        with self._lock:
            return self._current_workers

    def record_response_time(self, duration_ms: float) -> int | None:
        """
        Record a response time and potentially adjust worker count.

        Args:
            duration_ms: Response time in milliseconds

        Returns:
            New worker count if adjusted, None if no change needed

        Note:
            Call this after each API request completes (success or failure).
        """
        with self._lock:
            self._total_requests += 1
            self._total_response_time_ms += duration_ms
            self._response_times.append(duration_ms)

            # Keep only the most recent samples
            if len(self._response_times) > self.config.sample_window:
                self._response_times = self._response_times[-self.config.sample_window :]

            # Only adjust after we have enough samples
            if len(self._response_times) < self.config.sample_window:
                return None

            # Check cooldown period
            now = time.monotonic()
            if now - self._last_adjustment_time < self.config.cooldown_seconds:
                return None

            # Calculate average response time
            avg_time = sum(self._response_times) / len(self._response_times)

            # Determine if adjustment is needed
            new_workers = None

            if avg_time < self.config.scale_up_threshold_ms:
                # Fast responses - try to add workers
                if self._current_workers < self.config.max_workers:
                    new_workers = self._current_workers + 1
                    self._scale_ups += 1
                    self.logger.info(
                        "API tuner: scaling UP %s \u2192 %s workers (avg response: %.0fms < %sms threshold)",
                        self._current_workers,
                        new_workers,
                        avg_time,
                        self.config.scale_up_threshold_ms,
                    )

            elif avg_time > self.config.scale_down_threshold_ms and self._current_workers > self.config.min_workers:
                # Slow responses - try to reduce workers
                new_workers = self._current_workers - 1
                self._scale_downs += 1
                self.logger.info(
                    "API tuner: scaling DOWN %s \u2192 %s workers (avg response: %.0fms > %sms threshold)",
                    self._current_workers,
                    new_workers,
                    avg_time,
                    self.config.scale_down_threshold_ms,
                )

            if new_workers is not None:
                self._current_workers = new_workers
                self._last_adjustment_time = now
                self._response_times.clear()  # Reset window after adjustment
                return new_workers

            return None

    def get_statistics(self) -> dict[str, Any]:
        """
        Get tuner statistics.

        Returns:
            Dict with worker counts, adjustment history, and performance metrics
        """
        with self._lock:
            avg_response = self._total_response_time_ms / self._total_requests if self._total_requests > 0 else 0.0

            return {
                "current_workers": self._current_workers,
                "min_workers": self.config.min_workers,
                "max_workers": self.config.max_workers,
                "total_requests": self._total_requests,
                "scale_ups": self._scale_ups,
                "scale_downs": self._scale_downs,
                "average_response_ms": avg_response,
                "sample_window_size": len(self._response_times),
            }

    def reset(self, workers: int | None = None) -> None:
        """
        Reset the tuner state.

        Args:
            workers: Reset to specific worker count (default: keep current)
        """
        with self._lock:
            if workers is not None:
                self._current_workers = max(self.config.min_workers, min(workers, self.config.max_workers))
            self._response_times.clear()
            self._last_adjustment_time = 0.0
            self.logger.debug("API tuner reset (workers: %s)", self._current_workers)
