"""Custom exceptions for CJA Auto SDR.

All exception classes are designed to provide clear, actionable error messages
with context about what went wrong and how to fix it.
"""


class CJASDRError(Exception):
    """Base exception for all CJA SDR errors."""

    def __init__(self, message: str, details: str | None = None):
        self.message = message
        self.details = details
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


class ConfigurationError(CJASDRError):
    """Exception raised for configuration-related errors.

    Examples:
        - Missing config file
        - Invalid JSON in config file
        - Missing required credentials
        - Invalid credential format
    """

    def __init__(
        self,
        message: str,
        config_file: str | None = None,
        field: str | None = None,
        details: str | None = None,
    ):
        self.config_file = config_file
        self.field = field
        super().__init__(message, details)


class APIError(CJASDRError):
    """Exception raised for API communication failures.

    Wraps HTTP errors and network failures with context about
    the operation that failed.
    """

    def __init__(
        self,
        message: str,
        status_code: int | None = None,
        operation: str | None = None,
        details: str | None = None,
        original_error: Exception | None = None,
    ):
        self.status_code = status_code
        self.operation = operation
        self.original_error = original_error
        super().__init__(message, details)

    def __str__(self) -> str:
        parts = [self.message]
        if self.status_code:
            parts.append(f"HTTP {self.status_code}")
        if self.operation:
            parts.append(f"during {self.operation}")
        if self.details:
            parts.append(self.details)
        return " - ".join(parts)


class ValidationError(CJASDRError):
    """Exception raised for data quality validation failures.

    Used when validation encounters critical issues that prevent
    further processing.
    """

    def __init__(self, message: str, item_type: str | None = None, issue_count: int = 0, details: str | None = None):
        self.item_type = item_type
        self.issue_count = issue_count
        super().__init__(message, details)


class OutputError(CJASDRError):
    """Exception raised for file writing failures.

    Examples:
        - Permission denied
        - Disk full
        - Invalid path
        - Serialization error
    """

    def __init__(
        self,
        message: str,
        output_path: str | None = None,
        output_format: str | None = None,
        details: str | None = None,
        original_error: Exception | None = None,
    ):
        self.output_path = output_path
        self.output_format = output_format
        self.original_error = original_error
        super().__init__(message, details)


class ProfileError(CJASDRError):
    """Base exception for profile-related errors.

    Used when operations involving credential profiles fail.
    """

    def __init__(self, message: str, profile_name: str | None = None, details: str | None = None):
        self.profile_name = profile_name
        super().__init__(message, details)


class ProfileNotFoundError(ProfileError):
    """Raised when a profile directory doesn't exist.

    Examples:
        - Profile directory not found in ~/.cja/orgs/
        - Neither config.json nor .env exists in profile directory
    """


class ProfileConfigError(ProfileError):
    """Raised when a profile has invalid configuration.

    Examples:
        - Invalid JSON in config.json
        - Missing required credentials
        - Invalid profile name format
    """


class CredentialSourceError(CJASDRError):
    """Exception raised when credential loading fails from any source.

    Provides consistent error handling across all credential sources
    (profiles, environment variables, config files).

    Attributes:
        source: Name of the credential source (e.g., "profile", "env", "config_file")
        reason: Why the credential loading failed
    """

    def __init__(self, message: str, source: str, reason: str | None = None, details: str | None = None):
        self.source = source
        self.reason = reason
        super().__init__(message, details)

    def __str__(self) -> str:
        parts = [f"[{self.source}] {self.message}"]
        if self.reason:
            parts.append(f"Reason: {self.reason}")
        if self.details:
            parts.append(self.details)
        return " - ".join(parts)


class CircuitBreakerOpen(Exception):
    """Exception raised when circuit breaker is open and request is rejected."""

    def __init__(self, message: str = "Circuit breaker is open", time_until_retry: float = 0):
        self.message = message
        self.time_until_retry = time_until_retry
        super().__init__(self.message)


class RetryableHTTPError(Exception):
    """Exception raised when API returns a retryable HTTP status code."""

    def __init__(self, status_code: int, message: str = ""):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}: {message}" if message else f"HTTP {status_code}")


class ConcurrentOrgReportError(CJASDRError):
    """Exception raised when another org-report is already running for the same org.

    Prevents wasted API calls and rate limit issues from concurrent runs.

    Attributes:
        org_id: Organization ID that is locked
        lock_holder_pid: PID of the process holding the lock
        started_at: When the other run started
        lock_holder_owner: Owner identifier from lock metadata (additive, optional)
        lock_backend: Lock backend name from lock metadata (additive, optional)
    """

    def __init__(
        self,
        org_id: str,
        lock_holder_pid: int | None = None,
        started_at: str | None = None,
        lock_holder_owner: str | None = None,
        lock_backend: str | None = None,
    ):
        self.org_id = org_id
        self.lock_holder_pid = lock_holder_pid
        self.started_at = started_at
        self.lock_holder_owner = lock_holder_owner
        self.lock_backend = lock_backend

        message = f"Another --org-report is already running for org '{org_id}'"
        details_parts = []
        if lock_holder_pid:
            details_parts.append(f"PID {lock_holder_pid}")
        if lock_holder_owner:
            details_parts.append(f"owner {lock_holder_owner}")
        if lock_backend:
            details_parts.append(f"backend {lock_backend}")
        if started_at:
            details_parts.append(f"started at {started_at}")

        details = ", ".join(details_parts) if details_parts else None
        super().__init__(message, details)


class LockOwnershipLostError(CJASDRError):
    """Exception raised when a previously acquired lock can no longer be maintained."""

    def __init__(
        self,
        lock_path: str,
        *,
        reason: str | None = None,
    ):
        self.lock_path = lock_path
        self.reason = reason
        message = f"Lock ownership was lost for '{lock_path}'"
        super().__init__(message, reason)


class MemoryLimitExceeded(CJASDRError):
    """Exception raised when component index memory exceeds the configured hard limit.

    This protects against out-of-memory conditions for very large organizations.

    Attributes:
        estimated_mb: Estimated memory usage in megabytes
        limit_mb: Configured memory limit in megabytes
    """

    def __init__(self, estimated_mb: float, limit_mb: int):
        self.estimated_mb = estimated_mb
        self.limit_mb = limit_mb

        message = (
            f"Component index memory ({estimated_mb:.1f}MB) exceeds limit ({limit_mb}MB). "
            "Use --sample, --limit, or --filter to reduce data view count, "
            "or increase --memory-limit."
        )
        super().__init__(message)


def api_connection_hint(exc: Exception) -> str | None:
    """Return an actionable hint for common API connection failures.

    Maps opaque exceptions (e.g. ``KeyError('content')``) to plain-English
    guidance so users don't have to guess what went wrong.
    """
    if isinstance(exc, KeyError):
        key = str(exc).strip("'\"")
        if key == "content":
            return (
                "Hint: This usually means the API returned an empty or malformed response.\n"
                "      Verify that both the CJA API and AEP API are added to your Adobe\n"
                "      Developer Console project, and that the service account is granted\n"
                "      access to the correct product profiles."
            )
        return (
            f"Hint: API response missing expected key '{key}'.\n"
            "      Check your OAuth credentials and Developer Console project configuration."
        )
    from cja_auto_sdr.core.discovery_exceptions import coerce_http_status_code, extract_http_status_codes

    status = next((code for code in extract_http_status_codes(exc) if code in (401, 403)), None)
    if status is None:
        message_status = coerce_http_status_code(str(exc))
        if message_status in (401, 403):
            status = message_status

    if status in (401, 403):
        return (
            f"Hint: Received HTTP {status} — authentication or authorization failed.\n"
            "      Verify your client_id, client_secret, and OAuth scopes match the\n"
            "      Developer Console configuration."
        )
    return None
