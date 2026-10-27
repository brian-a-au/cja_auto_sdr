"""API module - CJA API integration components.

This module provides:
- Error message helpers with actionable suggestions
- Circuit breaker pattern for API resilience
- Retry logic with exponential backoff

Note: Some API components are currently thin wrappers around generator
to preserve backwards compatibility while modularization progresses.
"""

from __future__ import annotations

from cja_auto_sdr.api.resilience import (
    RETRYABLE_EXCEPTIONS,
    CircuitBreaker,
    ErrorMessageHelper,
    make_api_call_with_retry,
    retry_with_backoff,
)

__all__ = [
    "RETRYABLE_EXCEPTIONS",
    "APIWorkerTuner",
    "CircuitBreaker",
    "DataQualityChecker",
    # Resilience (from api/resilience.py)
    "ErrorMessageHelper",
    # Fetch + quality
    "ParallelAPIFetcher",
    "SharedValidationCache",
    # Caches + tuning
    "ValidationCache",
    # Client + validation
    "configure_cjapy",
    "initialize_cja",
    "make_api_call_with_retry",
    "retry_with_backoff",
    "validate_data_view",
]


from cja_auto_sdr.core.lazy import make_getattr

__getattr__ = make_getattr(
    __name__,
    [
        "configure_cjapy",
        "initialize_cja",
        "validate_data_view",
        "ParallelAPIFetcher",
        "DataQualityChecker",
        "ValidationCache",
        "SharedValidationCache",
        "APIWorkerTuner",
    ],
    mapping={
        "configure_cjapy": "cja_auto_sdr.api.client",
        "initialize_cja": "cja_auto_sdr.api.client",
        "validate_data_view": "cja_auto_sdr.api.validation",
        "ParallelAPIFetcher": "cja_auto_sdr.api.fetch",
        "DataQualityChecker": "cja_auto_sdr.api.quality",
        "ValidationCache": "cja_auto_sdr.api.cache",
        "SharedValidationCache": "cja_auto_sdr.api.cache",
        "APIWorkerTuner": "cja_auto_sdr.api.tuning",
    },
)
