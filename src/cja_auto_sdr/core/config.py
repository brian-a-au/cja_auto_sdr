"""Configuration dataclasses for CJA Auto SDR.

These dataclasses centralize all configuration options for type safety
and easy testing. They can be created from command-line arguments or
used directly in code.
"""

import argparse
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


@dataclass
class RetryConfig:
    """Configuration for retry logic with exponential backoff.

    Attributes:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay cap in seconds (default: 30.0)
        exponential_base: Multiplier for exponential backoff (default: 2)
        jitter: Add randomization to delays (default: True)
    """

    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: int = 2
    jitter: bool = True

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for backward compatibility."""
        return {
            "max_retries": self.max_retries,
            "base_delay": self.base_delay,
            "max_delay": self.max_delay,
            "exponential_base": self.exponential_base,
            "jitter": self.jitter,
        }


@dataclass
class CacheConfig:
    """Configuration for validation result caching.

    Attributes:
        enabled: Whether caching is enabled (default: False)
        max_size: Maximum number of cached entries (default: 1000)
        ttl_seconds: Time-to-live in seconds (default: 3600 = 1 hour)
    """

    enabled: bool = False
    max_size: int = 1000
    ttl_seconds: int = 3600


@dataclass
class LogConfig:
    """Configuration for logging behavior.

    Attributes:
        level: Logging level string (default: "INFO")
        file_max_bytes: Maximum size per log file (default: 10MB)
        file_backup_count: Number of backup log files (default: 5)
    """

    level: str = "INFO"
    file_max_bytes: int = 10 * 1024 * 1024  # 10MB
    file_backup_count: int = 5


@dataclass
class WorkerConfig:
    """Configuration for parallel processing workers.

    Attributes:
        api_fetch_workers: Concurrent API fetch threads (default: 3)
        validation_workers: Concurrent validation threads (default: 2)
        batch_workers: Batch processing workers (default: 4)
        max_batch_workers: Maximum allowed batch workers (default: 256)
    """

    api_fetch_workers: int = 3
    validation_workers: int = 2
    batch_workers: int = 4
    max_batch_workers: int = 256


@dataclass
class APITuningConfig:
    """Configuration for API worker auto-tuning.

    Dynamically adjusts the number of API fetch workers based on response times.
    Opt-in feature enabled via --api-auto-tune CLI flag.

    Attributes:
        min_workers: Minimum number of workers (default: 1)
        max_workers: Maximum number of workers (default: 10)
        scale_up_threshold_ms: Add workers if avg response time below this (default: 200ms)
        scale_down_threshold_ms: Remove workers if avg response time above this (default: 2000ms)
        sample_window: Number of requests to average before adjusting (default: 5)
        cooldown_seconds: Minimum time between adjustments (default: 10s)
    """

    min_workers: int = 1
    max_workers: int = 10
    scale_up_threshold_ms: float = 200.0
    scale_down_threshold_ms: float = 2000.0
    sample_window: int = 5
    cooldown_seconds: float = 10.0


class CircuitState(Enum):
    """States for the circuit breaker pattern."""

    CLOSED = "closed"  # Normal operation, requests flow through
    OPEN = "open"  # Circuit tripped, requests fail fast
    HALF_OPEN = "half_open"  # Testing if service recovered


@dataclass
class CircuitBreakerConfig:
    """Configuration for circuit breaker pattern.

    Prevents cascading failures by stopping requests to a failing service.
    Opt-in feature enabled via --circuit-breaker CLI flag.

    Attributes:
        failure_threshold: Consecutive failures before opening circuit (default: 5)
        success_threshold: Successes in half-open to close circuit (default: 2)
        timeout_seconds: Time before attempting recovery (open→half-open) (default: 30)
    """

    failure_threshold: int = 5
    success_threshold: int = 2
    timeout_seconds: float = 30.0


@dataclass
class SDRConfig:
    """Master configuration for SDR generation.

    Centralizes all configuration options in a single, testable dataclass.

    Attributes:
        retry: Retry configuration
        cache: Cache configuration
        log: Logging configuration
        workers: Worker configuration
        output_format: Output format (excel, csv, json, html, markdown, all)
        output_dir: Output directory path
        skip_validation: Skip data quality validation
        max_issues: Maximum issues to report (0 = all)
        quiet: Suppress non-error output
    """

    retry: RetryConfig = field(default_factory=RetryConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    log: LogConfig = field(default_factory=LogConfig)
    workers: WorkerConfig = field(default_factory=WorkerConfig)
    output_format: str = "excel"
    output_dir: str = "."
    skip_validation: bool = False
    max_issues: int = 0
    quiet: bool = False

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> SDRConfig:
        """Create configuration from parsed command-line arguments."""
        return cls(
            retry=RetryConfig(
                max_retries=getattr(args, "max_retries", 3),
                base_delay=getattr(args, "retry_base_delay", 1.0),
                max_delay=getattr(args, "retry_max_delay", 30.0),
            ),
            cache=CacheConfig(
                enabled=getattr(args, "enable_cache", False),
                max_size=getattr(args, "cache_size", 1000),
                ttl_seconds=getattr(args, "cache_ttl", 3600),
            ),
            log=LogConfig(
                level=getattr(args, "log_level", "INFO"),
            ),
            workers=WorkerConfig(
                batch_workers=getattr(args, "workers", 4),
            ),
            output_format=getattr(args, "format", "excel"),
            output_dir=getattr(args, "output_dir", "."),
            skip_validation=getattr(args, "skip_validation", False),
            max_issues=getattr(args, "max_issues", 0),
            quiet=getattr(args, "quiet", False),
        )


@dataclass
class WizardConfig:
    """Configuration options collected from the interactive wizard."""

    config_file: str = "config.json"
    data_views: list[str] = field(default_factory=list)
    output_format: str = "excel"
    output_dir: str = "."
    skip_validation: bool = False
