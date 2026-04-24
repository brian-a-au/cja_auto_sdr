"""API resilience utilities for CJA Auto SDR.

This module provides error handling, circuit breaker, and retry logic
for robust API communication.
"""

import functools
import logging
import math
import os
import random
import threading
import time
from collections.abc import Callable
from typing import Any, TypeVar

from cja_auto_sdr.core.config import CircuitBreakerConfig, CircuitState
from cja_auto_sdr.core.constants import (
    DEFAULT_RETRY_CONFIG,
    RETRY_JITTER_RANGE,
    RETRYABLE_STATUS_CODES,
    UPSTREAM_ADAPTER_STATUS_CODES,
)
from cja_auto_sdr.core.discovery_exceptions import coerce_http_status_code
from cja_auto_sdr.core.exceptions import CircuitBreakerOpen, RetryableHTTPError
from cja_auto_sdr.core.logging import emit_diagnostic

# Keys examined on dict-shaped cjapy payloads when recovering the HTTP status code.
# cjapy 0.3.1 returns parsed JSON and does not inject a snake_case status_code; the
# real payloads expose statusCode (camelCase), optionally nested under error/response.
_STATUS_KEY_CANDIDATES: tuple[str, ...] = (
    "status_code",
    "statusCode",
    "status",
    "http_status",
    "httpStatus",
    "code",
)
_NESTED_STATUS_KEYS: tuple[str, ...] = ("error", "response")


def _extract_http_status_code_from_result(result: Any) -> int | None:
    """Best-effort extraction of an HTTP status code from an API result.

    Supports:
    - Response-like objects exposing ``status_code`` or ``statusCode`` attributes
    - Mappings with top-level status keys
    - Mappings with status keys nested under ``error`` or ``response``

    Returns None when no plausible HTTP status code is present.
    """
    if result is None:
        return None

    for attr in ("status_code", "statusCode"):
        if hasattr(result, attr):
            code = coerce_http_status_code(getattr(result, attr, None))
            if code is not None:
                return code

    if isinstance(result, dict):
        for key in _STATUS_KEY_CANDIDATES:
            if key in result:
                code = coerce_http_status_code(result.get(key))
                if code is not None:
                    return code

        for nested_key in _NESTED_STATUS_KEYS:
            nested = result.get(nested_key)
            if isinstance(nested, dict):
                for key in _STATUS_KEY_CANDIDATES:
                    if key in nested:
                        code = coerce_http_status_code(nested.get(key))
                        if code is not None:
                            return code

    return None


def _is_upstream_failure_payload(result: Any) -> bool:
    """True when a returned payload carries a status in ``UPSTREAM_ADAPTER_STATUS_CODES``.

    Used by both ``make_api_call_with_retry`` and ``retry_with_backoff`` to
    suppress the ``✓ … succeeded on attempt …`` log (and, where a circuit
    breaker is available, route the breaker signal) on adapter-exhausted
    5xx/429 returns — the payloads cjapy already retried and gave up on.
    """
    status_code = _extract_http_status_code_from_result(result)
    return status_code is not None and status_code in UPSTREAM_ADAPTER_STATUS_CODES


def _parse_env_numeric(value: str | None, cast: Callable[[str], Any]) -> Any | None:
    """Parse an environment value, returning None when invalid."""
    if value is None:
        return None
    try:
        parsed = cast(value)
    except TypeError, ValueError:
        return None
    if isinstance(parsed, float) and not math.isfinite(parsed):
        return None
    return parsed


def _effective_retry_config() -> dict[str, Any]:
    """Return retry config with env-var overrides applied.

    CLI arguments are propagated via environment variables so that both
    the main process and spawned workers pick them up without mutating
    the module-level DEFAULT_RETRY_CONFIG dict.
    """
    cfg = dict(DEFAULT_RETRY_CONFIG)
    logger = logging.getLogger(__name__)

    parsed_max_retries = _parse_env_numeric(os.environ.get("MAX_RETRIES"), int)
    if parsed_max_retries is not None and parsed_max_retries >= 0:
        cfg["max_retries"] = parsed_max_retries
    elif "MAX_RETRIES" in os.environ:
        logger.warning(
            f"Ignoring invalid MAX_RETRIES={os.environ.get('MAX_RETRIES')!r}; using default {cfg['max_retries']}",
        )

    parsed_base_delay = _parse_env_numeric(os.environ.get("RETRY_BASE_DELAY"), float)
    if parsed_base_delay is not None and parsed_base_delay >= 0:
        cfg["base_delay"] = parsed_base_delay
    elif "RETRY_BASE_DELAY" in os.environ:
        logger.warning(
            f"Ignoring invalid RETRY_BASE_DELAY={os.environ.get('RETRY_BASE_DELAY')!r}; "
            f"using default {cfg['base_delay']}",
        )

    parsed_max_delay = _parse_env_numeric(os.environ.get("RETRY_MAX_DELAY"), float)
    if parsed_max_delay is not None and parsed_max_delay >= 0:
        cfg["max_delay"] = parsed_max_delay
    elif "RETRY_MAX_DELAY" in os.environ:
        logger.warning(
            f"Ignoring invalid RETRY_MAX_DELAY={os.environ.get('RETRY_MAX_DELAY')!r}; using default {cfg['max_delay']}",
        )

    # Guard against invalid windows that can otherwise cause negative sleep.
    if cfg["max_delay"] < cfg["base_delay"]:
        logger.warning(
            f"Ignoring invalid retry delay window (max_delay={cfg['max_delay']} < base_delay={cfg['base_delay']}); "
            f"using max_delay={cfg['base_delay']}",
        )
        cfg["max_delay"] = cfg["base_delay"]

    return cfg


T = TypeVar("T")


class ErrorMessageHelper:
    """Provides contextual error messages with actionable suggestions."""

    # Documentation links
    DOCS_BASE = "https://github.com/brian-a-au/cja_auto_sdr/blob/main/docs"
    TROUBLESHOOTING_URL = f"{DOCS_BASE}/TROUBLESHOOTING.md"
    QUICKSTART_URL = f"{DOCS_BASE}/QUICKSTART_GUIDE.md"

    @staticmethod
    def get_http_error_message(status_code: int, operation: str = "API call") -> str:
        """Get detailed error message with suggestions for HTTP status codes."""
        messages = {
            400: {
                "title": "Bad Request",
                "reason": "The request was malformed or contains invalid parameters",
                "suggestions": [
                    "Verify the data view ID format (should start with 'dv_')",
                    "Check that all required parameters are provided",
                    "Review the API request structure",
                ],
            },
            401: {
                "title": "Authentication Failed",
                "reason": "Your credentials are invalid or have expired",
                "suggestions": [
                    "Verify CLIENT_ID and SECRET in config.json or environment variables",
                    "Check that your ORG_ID ends with '@AdobeOrg'",
                    "Ensure SCOPES is set (copy from Adobe Developer Console)",
                    "Regenerate credentials at https://developer.adobe.com/console/",
                    f"See authentication setup: {ErrorMessageHelper.QUICKSTART_URL}#configure-credentials",
                ],
            },
            403: {
                "title": "Access Forbidden",
                "reason": "You don't have permission to access this resource",
                "suggestions": [
                    "Verify your Adobe I/O project has CJA API access enabled",
                    "Check that your user account has permission to access this data view",
                    "Confirm the data view ID is correct (run --list-dataviews)",
                    "Contact your Adobe administrator to grant CJA API permissions",
                ],
            },
            404: {
                "title": "Resource Not Found",
                "reason": "The requested data view or resource does not exist",
                "suggestions": [
                    "Verify the data view ID is correct (double-check for typos)",
                    "Run 'cja_auto_sdr --list-dataviews' to see available data views",
                    "The data view may have been deleted or renamed",
                    "Check that you're connected to the correct Adobe organization",
                ],
            },
            429: {
                "title": "Rate Limit Exceeded",
                "reason": "Too many requests sent to the API",
                "suggestions": [
                    "Wait a few minutes before retrying",
                    "Reduce the number of parallel workers (--workers 2)",
                    "Use --max-retries with longer delays (--retry-max-delay 60)",
                    "Process data views in smaller batches",
                    "Enable caching to reduce API calls (--enable-cache)",
                ],
            },
            500: {
                "title": "Internal Server Error",
                "reason": "Adobe's API service encountered an error",
                "suggestions": [
                    "This is typically a temporary issue - retry in a few minutes",
                    "Increase retry attempts (--max-retries 5)",
                    "Check Adobe Status page for known issues",
                    "If persistent, contact Adobe Support with your request details",
                ],
            },
            502: {
                "title": "Bad Gateway",
                "reason": "Upstream server error or network issue",
                "suggestions": [
                    "This is typically a temporary network issue",
                    "Wait a few minutes and retry",
                    "Increase retry attempts (--max-retries 5)",
                ],
            },
            503: {
                "title": "Service Unavailable",
                "reason": "Adobe's API service is temporarily unavailable",
                "suggestions": [
                    "The service may be undergoing maintenance",
                    "Wait 5-10 minutes and retry",
                    "Check Adobe Status page: https://status.adobe.com/",
                    "Use --max-retries 5 to automatically retry",
                ],
            },
            504: {
                "title": "Gateway Timeout",
                "reason": "The request took too long to complete",
                "suggestions": [
                    "The data view may be very large - this is normal",
                    "Increase timeout with --retry-max-delay 60",
                    "Try processing during off-peak hours",
                    "Consider using --skip-validation to reduce processing time",
                ],
            },
        }

        error_info = messages.get(
            status_code,
            {
                "title": f"HTTP {status_code}",
                "reason": "An unexpected HTTP error occurred",
                "suggestions": [
                    "Check your network connection",
                    "Verify API credentials are correct",
                    "Review logs for more details",
                    f"See troubleshooting guide: {ErrorMessageHelper.TROUBLESHOOTING_URL}",
                ],
            },
        )

        output = [
            f"{'=' * 60}",
            f"HTTP {status_code}: {error_info['title']}",
            f"{'=' * 60}",
            f"Operation: {operation}",
            "",
            "Why this happened:",
            f"  {error_info['reason']}",
            "",
            "How to fix it:",
        ]

        for i, suggestion in enumerate(error_info["suggestions"], 1):
            output.append(f"  {i}. {suggestion}")

        output.append("")
        output.append(f"For more help: {ErrorMessageHelper.TROUBLESHOOTING_URL}")

        return "\n".join(output)

    @staticmethod
    def get_network_error_message(error: Exception, operation: str = "operation") -> str:
        """Get detailed message for network-related errors."""
        error_type = type(error).__name__

        messages = {
            "ConnectionError": {
                "reason": "Cannot establish connection to Adobe API servers",
                "suggestions": [
                    "Check your internet connection",
                    "Verify you can reach adobe.io in your browser",
                    "Check if you're behind a corporate firewall or proxy",
                    "Temporarily disable VPN if you're using one",
                    "Verify DNS is working (try: ping adobe.io)",
                ],
            },
            "TimeoutError": {
                "reason": "The request took too long and timed out",
                "suggestions": [
                    "Your network connection may be slow or unstable",
                    "The data view may be very large (this is normal for large views)",
                    "Increase timeout with --retry-max-delay 60",
                    "Try processing during off-peak hours",
                    "Use --max-retries 5 to automatically retry",
                ],
            },
            "SSLError": {
                "reason": "SSL/TLS certificate verification failed",
                "suggestions": [
                    "Your system's SSL certificates may be outdated",
                    "Update certificates: pip install --upgrade certifi",
                    "Check system date/time is correct (SSL certs are time-sensitive)",
                    "Corporate firewalls may be interfering with SSL",
                ],
            },
            "ConnectionResetError": {
                "reason": "Connection was reset by the remote server",
                "suggestions": [
                    "This is usually a temporary network issue",
                    "Wait a moment and retry",
                    "Use --max-retries 5 to automatically handle this",
                ],
            },
        }

        error_info = messages.get(
            error_type,
            {
                "reason": "A network error occurred",
                "suggestions": [
                    "Check your internet connection",
                    "Verify network stability",
                    "Try again in a few moments",
                    f"See troubleshooting guide: {ErrorMessageHelper.TROUBLESHOOTING_URL}#network-errors",
                ],
            },
        )

        output = [
            f"{'=' * 60}",
            f"Network Error: {error_type}",
            f"{'=' * 60}",
            f"During: {operation}",
            f"Error details: {error!s}",
            "",
            "Why this happened:",
            f"  {error_info['reason']}",
            "",
            "How to fix it:",
        ]

        for i, suggestion in enumerate(error_info["suggestions"], 1):
            output.append(f"  {i}. {suggestion}")

        output.append("")
        output.append(f"For more help: {ErrorMessageHelper.TROUBLESHOOTING_URL}#network-errors")

        return "\n".join(output)

    @staticmethod
    def get_config_error_message(error_type: str, details: str = "") -> str:
        """Get detailed message for configuration errors."""
        messages = {
            "file_not_found": {
                "title": "Configuration File Not Found",
                "reason": "The config.json file does not exist",
                "suggestions": [
                    "Create a configuration file:",
                    "  Option 1: cja_auto_sdr --sample-config",
                    "  Option 2: cp config.json.example config.json",
                    "",
                    "Or use environment variables instead:",
                    "  export ORG_ID='your_org_id@AdobeOrg'",
                    "  export CLIENT_ID='your_client_id'",
                    "  export SECRET='your_client_secret'",
                    "  export SCOPES='your_scopes_from_developer_console'",
                    "",
                    f"See setup guide: {ErrorMessageHelper.QUICKSTART_URL}",
                ],
            },
            "invalid_json": {
                "title": "Invalid JSON in Configuration File",
                "reason": "The configuration file contains invalid JSON syntax",
                "suggestions": [
                    "Common JSON errors:",
                    "  - Missing quotes around strings",
                    "  - Trailing commas (not allowed in JSON)",
                    "  - Missing closing braces or brackets",
                    "  - Comments (not allowed in standard JSON)",
                    "",
                    "Validate your JSON:",
                    "  - Use a JSON validator: https://jsonlint.com/",
                    "  - Or check with: python -m json.tool config.json",
                    "",
                    "Generate a fresh template:",
                    "  cja_auto_sdr --sample-config",
                ],
            },
            "missing_credentials": {
                "title": "Missing Required Credentials",
                "reason": "One or more required credential fields are missing",
                "suggestions": [
                    "Required fields in config.json:",
                    "  - org_id: Your Adobe Organization ID (ends with @AdobeOrg)",
                    "  - client_id: OAuth Client ID from Adobe Developer Console",
                    "  - secret: Client Secret from Adobe Developer Console",
                    "  - scopes: API scopes (use provided default)",
                    "",
                    "Get credentials from:",
                    "  https://developer.adobe.com/console/",
                    "",
                    f"See detailed setup: {ErrorMessageHelper.QUICKSTART_URL}#configure-credentials",
                ],
            },
            "invalid_format": {
                "title": "Invalid Credential Format",
                "reason": "One or more credentials have an invalid format",
                "suggestions": [
                    "Check credential formats:",
                    "  - org_id must end with '@AdobeOrg'",
                    "  - client_id should be a long alphanumeric string",
                    "  - secret should be a long alphanumeric string",
                    "  - scopes should be copied from Adobe Developer Console",
                    "",
                    "Verify you copied credentials correctly (no extra spaces or line breaks)",
                    "Try regenerating credentials in Adobe Developer Console",
                ],
            },
        }

        error_info = messages.get(
            error_type,
            {
                "title": "Configuration Error",
                "reason": details or "A configuration error occurred",
                "suggestions": [
                    "Run validation to check your config:",
                    "  cja_auto_sdr --validate-config",
                    "",
                    f"See troubleshooting: {ErrorMessageHelper.TROUBLESHOOTING_URL}#configuration-errors",
                ],
            },
        )

        output = [
            f"{'=' * 60}",
            f"{error_info['title']}",
            f"{'=' * 60}",
        ]

        if details:
            output.extend(["", f"Details: {details}", ""])

        output.extend(
            [
                "Why this happened:",
                f"  {error_info['reason']}",
                "",
                "How to fix it:",
            ],
        )

        for suggestion in error_info["suggestions"]:
            if suggestion.startswith("  "):
                output.append(suggestion)
            else:
                output.append(f"  {suggestion}")

        return "\n".join(output)

    @staticmethod
    def get_data_view_error_message(data_view_id: str, available_count: int | None = None) -> str:
        """Get detailed message for data view not found errors."""
        # Determine if the identifier looks like an ID or a name
        is_id = data_view_id.startswith("dv_")

        output = [
            f"{'=' * 60}",
            "Data View Not Found",
            f"{'=' * 60}",
            f"Requested Data View: {data_view_id}",
            "",
            "Why this happened:",
            "  The data view does not exist or you don't have access to it",
            "",
            "How to fix it:",
        ]

        if is_id:
            output.extend(
                [
                    "  1. Check for typos in the data view ID",
                    "  2. Verify you have access to this data view in CJA",
                    "  3. List available data views to confirm the ID:",
                    "       cja_auto_sdr --list-dataviews",
                ],
            )
        else:
            output.extend(
                [
                    "  1. Check for typos in the data view name",
                    "  2. Verify the name is an EXACT match (case-sensitive):",
                    "       'Production Analytics' ≠ 'production analytics'",
                    "       'Production Analytics' ≠ 'Production'",
                    "  3. List available data views to confirm the exact name:",
                    "       cja_auto_sdr --list-dataviews",
                    "  4. Use quotes around names with spaces:",
                    '       cja_auto_sdr "Production Analytics"',
                ],
            )

        if available_count is not None:
            next_num = 4 if is_id else 5
            output.append(f"  {next_num}. You have access to {available_count} data view(s)")
            if available_count == 0:
                output.extend(
                    [
                        "",
                        "No data views found. This usually means:",
                        "  - Your API credentials don't have CJA access",
                        "  - You're connected to the wrong Adobe organization",
                        "  - No data views exist in this organization",
                    ],
                )

        output.extend(
            [
                "",
                f"For more help: {ErrorMessageHelper.TROUBLESHOOTING_URL}#data-view-errors",
            ],
        )

        return "\n".join(output)


# Exceptions that should trigger a retry (transient errors).
# Note: ConnectionError and TimeoutError are subclasses of OSError; we keep
# them explicit here to document the network-oriented intent.
RETRYABLE_EXCEPTIONS: tuple[type, ...] = (
    ConnectionError,
    TimeoutError,
    OSError,  # Includes network-related errors
    RetryableHTTPError,  # Custom exception for HTTP status codes
)


class CircuitBreaker:
    """
    Thread-safe circuit breaker implementation for API resilience.

    The circuit breaker pattern prevents cascading failures by stopping
    requests to a failing service. It has three states:

    - CLOSED: Normal operation, requests flow through
    - OPEN: Circuit tripped after too many failures, requests fail fast
    - HALF_OPEN: Testing if service recovered after timeout

    State Transitions:
    - CLOSED → OPEN: After failure_threshold consecutive failures
    - OPEN → HALF_OPEN: After timeout_seconds has elapsed
    - HALF_OPEN → CLOSED: After success_threshold successful requests
    - HALF_OPEN → OPEN: After any failure

    Thread Safety:
    - Uses threading.Lock for all state transitions
    - Safe for use with ThreadPoolExecutor

    Example:
        breaker = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=3))

        if breaker.allow_request():
            try:
                result = api_call()
                breaker.record_success()
            except Exception as e:
                breaker.record_failure(e)
                raise
        else:
            raise CircuitBreakerOpen()
    """

    def __init__(self, config: CircuitBreakerConfig = None, logger: logging.Logger | None = None):
        """
        Initialize the circuit breaker.

        Args:
            config: Configuration settings (uses defaults if not provided)
            logger: Logger instance for state change logging
        """
        self.config = config or CircuitBreakerConfig()
        self.logger = logger or logging.getLogger(__name__)

        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._success_count = 0
        self._last_failure_time: float | None = None
        self._last_state_change_time = time.monotonic()
        self._lock = threading.Lock()

        # Statistics
        self._total_requests = 0
        self._total_failures = 0
        self._total_rejections = 0
        self._trips = 0  # Number of times circuit opened

    @property
    def state(self) -> CircuitState:
        """Get current circuit state (thread-safe)."""
        with self._lock:
            return self._state

    def allow_request(self) -> bool:
        """
        Check if a request should be allowed through.

        Returns:
            True if request is allowed, False if circuit is open

        Side Effects:
            - Transitions OPEN → HALF_OPEN if timeout has elapsed
            - Increments rejection counter if request is blocked
        """
        with self._lock:
            self._total_requests += 1

            if self._state == CircuitState.CLOSED:
                return True

            if self._state == CircuitState.OPEN:
                # Check if timeout has elapsed for recovery attempt
                if self._last_failure_time is not None:
                    elapsed = time.monotonic() - self._last_failure_time
                    if elapsed >= self.config.timeout_seconds:
                        self._transition_to(CircuitState.HALF_OPEN)
                        return True

                # Still in timeout period
                self._total_rejections += 1
                return False

            # HALF_OPEN - allow limited requests to test recovery
            return True

    def record_success(self) -> None:
        """
        Record a successful request.

        Side Effects:
            - Resets failure count in CLOSED state
            - Increments success count in HALF_OPEN state
            - Transitions HALF_OPEN → CLOSED if success threshold reached
        """
        with self._lock:
            if self._state == CircuitState.CLOSED:
                self._failure_count = 0  # Reset consecutive failure count
            elif self._state == CircuitState.HALF_OPEN:
                self._success_count += 1
                if self._success_count >= self.config.success_threshold:
                    self._transition_to(CircuitState.CLOSED)
                    self._failure_count = 0
                    self._success_count = 0

    def record_failure(self, _exception: Exception | None = None) -> None:
        """
        Record a failed request.

        Args:
            exception: The exception that caused the failure (for logging)

        Side Effects:
            - Increments failure count
            - Transitions CLOSED → OPEN if failure threshold reached
            - Transitions HALF_OPEN → OPEN immediately on any failure
        """
        with self._lock:
            self._failure_count += 1
            self._total_failures += 1
            self._last_failure_time = time.monotonic()

            if self._state == CircuitState.CLOSED:
                if self._failure_count >= self.config.failure_threshold:
                    self._transition_to(CircuitState.OPEN)
                    self._trips += 1
            elif self._state == CircuitState.HALF_OPEN:
                # Any failure in half-open immediately opens the circuit
                self._transition_to(CircuitState.OPEN)
                self._success_count = 0

    def _transition_to(self, new_state: CircuitState) -> None:
        """
        Transition to a new state (must be called within lock).

        Args:
            new_state: The state to transition to
        """
        old_state = self._state
        self._state = new_state
        self._last_state_change_time = time.monotonic()

        if old_state != new_state:
            emit_diagnostic(
                self.logger,
                "circuit_breaker_transition",
                "resilience",
                from_state=old_state.value,
                to_state=new_state.value,
                failure_count=self._failure_count,
                success_count=self._success_count,
            )

    def get_statistics(self) -> dict[str, Any]:
        """
        Get circuit breaker statistics.

        Returns:
            Dict with state, counts, and timing information
        """
        with self._lock:
            time_in_state = time.monotonic() - self._last_state_change_time
            time_until_retry = 0.0

            if self._state == CircuitState.OPEN and self._last_failure_time is not None:
                time_until_retry = max(0.0, self.config.timeout_seconds - (time.monotonic() - self._last_failure_time))

            return {
                "state": self._state.value,
                "failure_count": self._failure_count,
                "success_count": self._success_count,
                "total_requests": self._total_requests,
                "total_failures": self._total_failures,
                "total_rejections": self._total_rejections,
                "trips": self._trips,
                "time_in_state_seconds": time_in_state,
                "time_until_retry_seconds": time_until_retry,
            }

    def reset(self) -> None:
        """Reset the circuit breaker to initial state."""
        with self._lock:
            self._state = CircuitState.CLOSED
            self._failure_count = 0
            self._success_count = 0
            self._last_failure_time = None
            self._last_state_change_time = time.monotonic()
            self.logger.debug("Circuit breaker reset to CLOSED state")

    def __call__(self, func: Callable[..., T]) -> Callable[..., T]:
        """
        Use as a decorator for functions.

        Example:
            @circuit_breaker
            def api_call():
                return requests.get(url)
        """

        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> T:
            if not self.allow_request():
                stats = self.get_statistics()
                raise CircuitBreakerOpen(
                    f"Circuit breaker is open (will retry in {stats['time_until_retry_seconds']:.1f}s)",
                    time_until_retry=stats["time_until_retry_seconds"],
                )
            try:
                result = func(*args, **kwargs)
                self.record_success()
                return result
            except Exception as e:  # Intentional: Circuit breaker must observe all failures to track error rate
                self.record_failure(e)
                raise

        return wrapper


def retry_with_backoff(
    max_retries: int | None = None,
    base_delay: float | None = None,
    max_delay: float | None = None,
    exponential_base: int | None = None,
    jitter: bool | None = None,
    retryable_exceptions: tuple[type, ...] | None = None,
    logger: logging.Logger | None = None,
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator that implements retry logic with exponential backoff.

    Automatically retries failed API calls with increasing delays between attempts.
    Includes jitter to prevent thundering herd problems when multiple processes retry.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay cap in seconds (default: 30.0)
        exponential_base: Multiplier for exponential backoff (default: 2)
        jitter: Add randomization to delays (default: True)
        retryable_exceptions: Tuple of exception types to retry (default: network errors)
        logger: Logger instance for retry messages

    Returns:
        Decorated function with retry capability

    Example:
        @retry_with_backoff(max_retries=3, base_delay=1.0)
        def fetch_data():
            return api.get_data()

    Backoff Formula:
        delay = min(base_delay * (exponential_base ** attempt), max_delay)
        if jitter: delay = delay * random.uniform(*RETRY_JITTER_RANGE)
    """
    # Use defaults if not specified
    _max_retries = max_retries if max_retries is not None else DEFAULT_RETRY_CONFIG["max_retries"]
    _base_delay = base_delay if base_delay is not None else DEFAULT_RETRY_CONFIG["base_delay"]
    _max_delay = max_delay if max_delay is not None else DEFAULT_RETRY_CONFIG["max_delay"]
    _exponential_base = exponential_base if exponential_base is not None else DEFAULT_RETRY_CONFIG["exponential_base"]
    _jitter = jitter if jitter is not None else DEFAULT_RETRY_CONFIG["jitter"]
    _retryable_exceptions = retryable_exceptions if retryable_exceptions is not None else RETRYABLE_EXCEPTIONS

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            _logger = logger or logging.getLogger(__name__)

            for attempt in range(_max_retries + 1):  # +1 for initial attempt
                try:
                    result = func(*args, **kwargs)
                    # Log success after retry, unless the return carries an
                    # adapter-exhausted upstream-failure status (5xx/429) — in
                    # that case the "return" is actually an upstream failure
                    # payload and the caller will classify it; logging success
                    # would contradict that classification.
                    if attempt > 0 and not _is_upstream_failure_payload(result):
                        _logger.info("✓ %s succeeded on attempt %s/%s", func.__name__, attempt + 1, _max_retries + 1)
                    return result
                except _retryable_exceptions as e:
                    if attempt == _max_retries:
                        _logger.error("All %s attempts failed for %s", _max_retries + 1, func.__name__)

                        # Provide enhanced error message based on exception type
                        if isinstance(e, RetryableHTTPError):
                            error_msg = ErrorMessageHelper.get_http_error_message(
                                e.status_code,
                                operation=func.__name__,
                            )
                            _logger.error("\n" + error_msg)
                        # ConnectionError/TimeoutError are OSError subclasses;
                        # listed explicitly for readability and intent.
                        elif isinstance(e, (ConnectionError, TimeoutError, OSError)):
                            error_msg = ErrorMessageHelper.get_network_error_message(e, operation=func.__name__)
                            _logger.error("\n" + error_msg)
                        else:  # pragma: no cover — RETRYABLE_EXCEPTIONS exhausted above
                            _logger.error("Error: %s", e)
                            _logger.error(
                                "Troubleshooting: Check network connectivity, verify API credentials, or try again later",
                            )
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(_base_delay * (_exponential_base**attempt), _max_delay)

                    # Add jitter to prevent thundering herd
                    if _jitter:
                        delay = delay * random.uniform(*RETRY_JITTER_RANGE)

                    _logger.warning(
                        "⚠ %s attempt %s/%s failed: %s. Retrying in %.1fs...",
                        func.__name__,
                        attempt + 1,
                        _max_retries + 1,
                        e,
                        delay,
                    )
                    time.sleep(delay)
                except (
                    Exception
                ) as e:  # Intentional: Retry loop must catch all to distinguish retryable vs non-retryable
                    # Non-retryable exception, raise immediately
                    _logger.error("%s failed with non-retryable error: %s", func.__name__, e)
                    raise

            # Defensive guard: should be unreachable since the last attempt
            # always returns or raises, but protects against implicit None.
            raise RuntimeError(f"Retry loop exited unexpectedly for {func.__name__}")  # pragma: no cover

        return wrapper

    return decorator


def make_api_call_with_retry[T](
    api_func: Callable[..., T],
    *args: Any,
    logger: logging.Logger | None = None,
    operation_name: str = "API call",
    circuit_breaker: CircuitBreaker | None = None,
    **kwargs: Any,
) -> T:
    """
    Execute an API call with retry logic and optional circuit breaker.

    This is a function-based alternative to the decorator for cases where
    you need more control or are calling methods on objects.

    Args:
        api_func: The API function to call
        *args: Positional arguments to pass to the function
        logger: Logger instance for retry messages
        operation_name: Human-readable name for logging
        circuit_breaker: Optional circuit breaker for failure protection
        **kwargs: Keyword arguments to pass to the function

    Returns:
        Result from the API call

    Raises:
        CircuitBreakerOpen: If circuit breaker is open and rejecting requests
        The last exception if all retries fail

    Example:
        result = make_api_call_with_retry(
            cja.getMetrics,
            data_view_id,
            logger=logger,
            operation_name="getMetrics",
            circuit_breaker=my_circuit_breaker
        )
    """
    _logger = logger or logging.getLogger(__name__)
    _cfg = _effective_retry_config()
    max_retries = _cfg["max_retries"]
    base_delay = _cfg["base_delay"]
    max_delay = _cfg["max_delay"]
    exponential_base = _cfg["exponential_base"]
    jitter = _cfg["jitter"]

    # Check circuit breaker before attempting any calls
    if circuit_breaker is not None and not circuit_breaker.allow_request():
        stats = circuit_breaker.get_statistics()
        raise CircuitBreakerOpen(
            f"Circuit breaker is open for {operation_name} (will retry in {stats['time_until_retry_seconds']:.1f}s)",
            time_until_retry=stats["time_until_retry_seconds"],
        )

    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            result = api_func(*args, **kwargs)

            # Check for HTTP status code in response. cjapy 0.3.1 returns parsed
            # JSON dicts exposing camelCase statusCode (optionally nested under
            # error/response), so we normalize across all supported shapes.
            status_code = _extract_http_status_code_from_result(result)

            if status_code is not None and status_code in RETRYABLE_STATUS_CODES:
                raise RetryableHTTPError(status_code, f"Retryable status from {operation_name}")

            # Adapter-exhausted upstream failure: cjapy's urllib3.Retry adapter
            # already retried 429/500/502/503/504 before this payload reached us.
            # We don't retry again (that stacks), but we must signal the failure
            # so repeated 5xx/429 trips the breaker and telemetry stays coherent.
            is_upstream_failure = status_code is not None and status_code in UPSTREAM_ADAPTER_STATUS_CODES

            if attempt > 0 and not is_upstream_failure:
                _logger.info("✓ %s succeeded on attempt %s/%s", operation_name, attempt + 1, max_retries + 1)

            if circuit_breaker is not None:
                if is_upstream_failure:
                    circuit_breaker.record_failure(
                        RetryableHTTPError(
                            status_code,
                            f"Adapter-exhausted upstream status {status_code} from {operation_name}",
                        ),
                    )
                else:
                    circuit_breaker.record_success()

            return result
        except RETRYABLE_EXCEPTIONS as e:
            last_exception = e

            if attempt == max_retries:
                _logger.error("All %s attempts failed for %s", max_retries + 1, operation_name)

                # Provide enhanced error message based on exception type
                if isinstance(e, RetryableHTTPError):
                    error_msg = ErrorMessageHelper.get_http_error_message(e.status_code, operation=operation_name)
                    _logger.error("\n" + error_msg)
                # ConnectionError/TimeoutError are OSError subclasses;
                # listed explicitly for readability and intent.
                elif isinstance(e, (ConnectionError, TimeoutError, OSError)):
                    error_msg = ErrorMessageHelper.get_network_error_message(e, operation=operation_name)
                    _logger.error("\n" + error_msg)
                else:  # pragma: no cover — RETRYABLE_EXCEPTIONS exhausted above
                    _logger.error("Error: %s", e)
                    _logger.error(
                        "Troubleshooting: Check network connectivity, verify API credentials, or try again later",
                    )

                # Record failure to circuit breaker (only after all retries exhausted)
                if circuit_breaker is not None:
                    circuit_breaker.record_failure(e)
                raise

            delay = min(base_delay * (exponential_base**attempt), max_delay)
            if jitter:
                delay = delay * random.uniform(*RETRY_JITTER_RANGE)

            _logger.warning(
                "⚠ %s attempt %s/%s failed: %s. Retrying in %.1fs...",
                operation_name,
                attempt + 1,
                max_retries + 1,
                e,
                delay,
            )
            time.sleep(delay)
        except Exception as e:  # Intentional: Retry loop must catch all to distinguish retryable vs non-retryable
            # Non-retryable exception
            _logger.error("%s failed with non-retryable error: %s", operation_name, e)
            # Record failure to circuit breaker
            if circuit_breaker is not None:
                circuit_breaker.record_failure(e)
            raise

    if last_exception:  # pragma: no cover — unreachable; loop always returns or raises
        raise last_exception
    raise RuntimeError(f"Retry loop exited unexpectedly for {operation_name}")  # pragma: no cover
