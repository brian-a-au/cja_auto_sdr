"""Performance tracking helpers for CJA Auto SDR."""

import logging
import time

from cja_auto_sdr.core.constants import BANNER_WIDTH


class PerformanceTracker:
    """Track execution time for operations"""

    MAX_METRICS = 500

    def __init__(self, logger: logging.Logger):
        self.metrics: dict[str, float] = {}
        self.logger = logger
        self.start_times: dict[str, float] = {}

    def start(self, operation_name: str):
        """Start timing an operation"""
        self.start_times[operation_name] = time.perf_counter()

    def end(self, operation_name: str):
        """End timing an operation"""
        if operation_name in self.start_times:
            duration = time.perf_counter() - self.start_times[operation_name]
            if len(self.metrics) >= self.MAX_METRICS:
                # Drop oldest entry to prevent unbounded growth
                oldest = next(iter(self.metrics))
                del self.metrics[oldest]
            self.metrics[operation_name] = duration

            # Log individual operations only in DEBUG mode for performance
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug("\u23f1\ufe0f  %s completed in %.2fs", operation_name, duration)

            del self.start_times[operation_name]

    def get_summary(self) -> str:
        """Generate performance summary"""
        if not self.metrics:
            return "No performance metrics collected"

        total = sum(self.metrics.values())
        lines = ["", "=" * BANNER_WIDTH, "PERFORMANCE SUMMARY", "=" * BANNER_WIDTH]

        for operation, duration in sorted(self.metrics.items(), key=lambda x: x[1], reverse=True):
            percentage = (duration / total) * 100 if total > 0 else 0
            lines.append(f"{operation:35s}: {duration:6.2f}s ({percentage:5.1f}%)")

        lines.extend(["=" * BANNER_WIDTH, f"{'Total Execution Time':35s}: {total:6.2f}s", "=" * BANNER_WIDTH])
        return "\n".join(lines)

    def add_cache_statistics(self, cache):
        """Add cache statistics to performance metrics"""
        stats = cache.get_statistics()

        if stats["total_requests"] > 0:
            self.logger.info("")
            self.logger.info("=" * BANNER_WIDTH)
            self.logger.info("VALIDATION CACHE STATISTICS")
            self.logger.info("=" * BANNER_WIDTH)
            self.logger.info("Cache Hits:        %s", stats["hits"])
            self.logger.info("Cache Misses:      %s", stats["misses"])
            self.logger.info("Hit Rate:          %.1f%%", stats["hit_rate"])
            self.logger.info("Cache Size:        %s/%s", stats["size"], stats["max_size"])
            self.logger.info("Evictions:         %s", stats["evictions"])

            if stats["hits"] > 0:
                # Assume average validation takes 50ms, cache lookup takes 1ms
                time_saved = stats["hits"] * 0.049  # 49ms saved per hit
                self.logger.info("Estimated Time Saved: %.2fs", time_saved)

            self.logger.info("=" * BANNER_WIDTH)
