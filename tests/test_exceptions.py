"""Tests for all custom exception classes in cja_auto_sdr.core.exceptions.

Validates construction, attribute storage, __str__ formatting, and inheritance
for every exception class.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cja_auto_sdr.core.exceptions import (
    APIError,
    CircuitBreakerOpen,
    CJASDRError,
    ConcurrentOrgReportError,
    ConfigurationError,
    CredentialSourceError,
    LockOwnershipLostError,
    MemoryLimitExceeded,
    OutputError,
    ProfileConfigError,
    ProfileError,
    ProfileNotFoundError,
    RetryableHTTPError,
    ValidationError,
)


class TestCJASDRError:
    def test_message_only(self):
        err = CJASDRError("something failed")
        assert err.message == "something failed"
        assert err.details is None
        assert str(err) == "something failed"

    def test_message_with_details(self):
        err = CJASDRError("something failed", details="check logs")
        assert err.message == "something failed"
        assert err.details == "check logs"
        assert str(err) == "something failed: check logs"

    def test_inherits_exception(self):
        assert issubclass(CJASDRError, Exception)

    def test_raise_and_catch(self):
        with pytest.raises(Exception):
            raise CJASDRError("test")

    def test_empty_details(self):
        err = CJASDRError("msg", details="")
        assert str(err) == "msg"


class TestConfigurationError:
    def test_message_only(self):
        err = ConfigurationError("bad config")
        assert err.message == "bad config"
        assert err.config_file is None
        assert err.field is None
        assert err.details is None

    def test_all_params(self):
        err = ConfigurationError("bad config", config_file="config.json", field="org_id", details="missing")
        assert err.config_file == "config.json"
        assert err.field == "org_id"
        assert err.details == "missing"

    def test_inherits_cjasdr_error(self):
        assert issubclass(ConfigurationError, CJASDRError)
        with pytest.raises(CJASDRError):
            raise ConfigurationError("test")


class TestAPIError:
    def test_message_only(self):
        err = APIError("api failed")
        assert str(err) == "api failed"
        assert err.status_code is None
        assert err.operation is None
        assert err.original_error is None

    def test_all_params(self):
        orig = RuntimeError("connection reset")
        err = APIError("api failed", status_code=503, operation="fetch", details="unavailable", original_error=orig)
        assert err.status_code == 503
        assert err.operation == "fetch"
        assert err.original_error is orig

    def test_str_message_only(self):
        assert str(APIError("api failed")) == "api failed"

    def test_str_with_status_code(self):
        assert str(APIError("api failed", status_code=404)) == "api failed - HTTP 404"

    def test_str_with_operation(self):
        assert str(APIError("api failed", operation="fetch data views")) == "api failed - during fetch data views"

    def test_str_with_details(self):
        assert str(APIError("api failed", details="server unavailable")) == "api failed - server unavailable"

    def test_str_all_fields(self):
        err = APIError("api failed", status_code=503, operation="fetch", details="unavailable")
        assert str(err) == "api failed - HTTP 503 - during fetch - unavailable"

    def test_str_status_code_zero_is_falsy(self):
        assert str(APIError("api failed", status_code=0)) == "api failed"

    def test_inherits_cjasdr_error(self):
        assert issubclass(APIError, CJASDRError)

    def test_original_error_preserved(self):
        orig = ConnectionError("reset")
        err = APIError("api failed", original_error=orig)
        assert isinstance(err.original_error, ConnectionError)


class TestValidationError:
    def test_message_only(self):
        err = ValidationError("validation failed")
        assert err.item_type is None
        assert err.issue_count == 0

    def test_all_params(self):
        err = ValidationError("failed", item_type="dimension", issue_count=42, details="missing descriptions")
        assert err.item_type == "dimension"
        assert err.issue_count == 42
        assert err.details == "missing descriptions"

    def test_str_with_details(self):
        assert str(ValidationError("failed", details="too many")) == "failed: too many"

    def test_inherits_cjasdr_error(self):
        assert issubclass(ValidationError, CJASDRError)


class TestOutputError:
    def test_message_only(self):
        err = OutputError("write failed")
        assert err.output_path is None
        assert err.output_format is None
        assert err.original_error is None

    def test_all_params(self):
        orig = PermissionError("denied")
        err = OutputError(
            "write failed",
            output_path="/tmp/out.xlsx",
            output_format="excel",
            details="denied",
            original_error=orig,
        )
        assert err.output_path == "/tmp/out.xlsx"
        assert err.output_format == "excel"
        assert err.original_error is orig

    def test_inherits_cjasdr_error(self):
        assert issubclass(OutputError, CJASDRError)


class TestProfileError:
    def test_message_only(self):
        err = ProfileError("profile error")
        assert err.profile_name is None

    def test_all_params(self):
        err = ProfileError("error", profile_name="prod", details="not found")
        assert err.profile_name == "prod"
        assert err.details == "not found"

    def test_profile_not_found_inherits_profile_error(self):
        assert issubclass(ProfileNotFoundError, ProfileError)
        assert issubclass(ProfileNotFoundError, CJASDRError)
        err = ProfileNotFoundError("not found", profile_name="staging", details="dir missing")
        assert isinstance(err, ProfileError)
        assert err.profile_name == "staging"

    def test_profile_config_error_inherits_profile_error(self):
        assert issubclass(ProfileConfigError, ProfileError)
        assert issubclass(ProfileConfigError, CJASDRError)
        err = ProfileConfigError("invalid json", profile_name="dev")
        assert isinstance(err, ProfileError)

    def test_catch_as_parent(self):
        with pytest.raises(ProfileError):
            raise ProfileNotFoundError("not found")
        with pytest.raises(ProfileError):
            raise ProfileConfigError("bad config")
        with pytest.raises(CJASDRError):
            raise ProfileNotFoundError("not found")


class TestCredentialSourceError:
    def test_required_params(self):
        err = CredentialSourceError("cred failed", source="profile")
        assert err.source == "profile"
        assert err.reason is None

    def test_all_params(self):
        err = CredentialSourceError("cred failed", source="env", reason="not set", details="check .env")
        assert err.source == "env"
        assert err.reason == "not set"

    def test_str_source_and_message_only(self):
        assert str(CredentialSourceError("cred failed", source="profile")) == "[profile] cred failed"

    def test_str_with_reason(self):
        assert (
            str(CredentialSourceError("cred failed", source="env", reason="not set"))
            == "[env] cred failed - Reason: not set"
        )

    def test_str_with_details(self):
        assert (
            str(CredentialSourceError("cred failed", source="config_file", details="check docs"))
            == "[config_file] cred failed - check docs"
        )

    def test_str_with_reason_and_details(self):
        err = CredentialSourceError("cred failed", source="env", reason="not set", details="check .env")
        assert str(err) == "[env] cred failed - Reason: not set - check .env"

    def test_str_empty_reason_is_falsy(self):
        assert str(CredentialSourceError("cred failed", source="profile", reason="")) == "[profile] cred failed"

    def test_inherits_cjasdr_error(self):
        assert issubclass(CredentialSourceError, CJASDRError)


class TestCircuitBreakerOpen:
    def test_defaults(self):
        err = CircuitBreakerOpen()
        assert err.message == "Circuit breaker is open"
        assert err.time_until_retry == 0

    def test_custom_params(self):
        err = CircuitBreakerOpen(message="tripped", time_until_retry=30.5)
        assert err.message == "tripped"
        assert err.time_until_retry == 30.5

    def test_str(self):
        assert str(CircuitBreakerOpen()) == "Circuit breaker is open"
        assert str(CircuitBreakerOpen(message="custom")) == "custom"

    def test_not_cjasdr_error(self):
        assert issubclass(CircuitBreakerOpen, Exception)
        assert not issubclass(CircuitBreakerOpen, CJASDRError)
        assert not isinstance(CircuitBreakerOpen(), CJASDRError)

    def test_cannot_catch_as_cjasdr_error(self):
        with pytest.raises(CircuitBreakerOpen):
            try:
                raise CircuitBreakerOpen
            except CJASDRError:
                pytest.fail("should not be caught as CJASDRError")


class TestRetryableHTTPError:
    def test_status_code_only(self):
        err = RetryableHTTPError(429)
        assert err.status_code == 429
        assert str(err) == "HTTP 429"

    def test_with_message(self):
        err = RetryableHTTPError(503, message="Service Unavailable")
        assert str(err) == "HTTP 503: Service Unavailable"

    def test_empty_message(self):
        assert str(RetryableHTTPError(500, message="")) == "HTTP 500"

    def test_not_cjasdr_error(self):
        assert issubclass(RetryableHTTPError, Exception)
        assert not issubclass(RetryableHTTPError, CJASDRError)

    def test_cannot_catch_as_cjasdr_error(self):
        with pytest.raises(RetryableHTTPError):
            try:
                raise RetryableHTTPError(500)
            except CJASDRError:
                pytest.fail("should not be caught as CJASDRError")


class TestConcurrentOrgReportError:
    def test_org_id_only(self):
        err = ConcurrentOrgReportError("org123")
        assert err.org_id == "org123"
        assert err.lock_holder_pid is None
        assert err.started_at is None
        assert err.details is None
        assert str(err) == "Another --org-report is already running for org 'org123'"

    def test_with_pid(self):
        err = ConcurrentOrgReportError("org123", lock_holder_pid=9999)
        assert err.details == "PID 9999"
        assert "PID 9999" in str(err)

    def test_with_started_at(self):
        err = ConcurrentOrgReportError("org123", started_at="2026-02-14T10:00:00")
        assert err.details == "started at 2026-02-14T10:00:00"

    def test_all_fields(self):
        err = ConcurrentOrgReportError("org123", lock_holder_pid=9999, started_at="2026-02-14T10:00:00")
        assert err.details == "PID 9999, started at 2026-02-14T10:00:00"
        expected = "Another --org-report is already running for org 'org123': PID 9999, started at 2026-02-14T10:00:00"
        assert str(err) == expected

    def test_lock_holder_owner_field(self):
        err = ConcurrentOrgReportError("org123", lock_holder_owner="ci-runner")
        assert err.lock_holder_owner == "ci-runner"
        assert "owner ci-runner" in err.details

    def test_lock_backend_field(self):
        err = ConcurrentOrgReportError("org123", lock_backend="lease")
        assert err.lock_backend == "lease"
        assert "backend lease" in err.details

    def test_all_fields_with_owner_and_backend(self):
        err = ConcurrentOrgReportError(
            "org123",
            lock_holder_pid=9999,
            lock_holder_owner="ci-runner",
            lock_backend="fcntl",
            started_at="2026-02-14T10:00:00",
        )
        assert err.lock_holder_owner == "ci-runner"
        assert err.lock_backend == "fcntl"
        assert "PID 9999" in err.details
        assert "owner ci-runner" in err.details
        assert "backend fcntl" in err.details
        assert "started at 2026-02-14T10:00:00" in err.details

    def test_owner_and_backend_default_to_none(self):
        err = ConcurrentOrgReportError("org123")
        assert err.lock_holder_owner is None
        assert err.lock_backend is None

    def test_inherits_cjasdr_error(self):
        assert issubclass(ConcurrentOrgReportError, CJASDRError)


class TestLockOwnershipLostError:
    def test_lock_path_only(self):
        err = LockOwnershipLostError("/tmp/lock")
        assert err.lock_path == "/tmp/lock"
        assert err.reason is None
        assert str(err) == "Lock ownership was lost for '/tmp/lock'"

    def test_with_reason(self):
        err = LockOwnershipLostError("/tmp/lock", reason="stale lock")
        assert err.reason == "stale lock"
        assert err.details == "stale lock"
        assert str(err) == "Lock ownership was lost for '/tmp/lock': stale lock"

    def test_reason_is_keyword_only(self):
        with pytest.raises(TypeError):
            LockOwnershipLostError("/tmp/lock", "some reason")

    def test_inherits_cjasdr_error(self):
        assert issubclass(LockOwnershipLostError, CJASDRError)


class TestMemoryLimitExceeded:
    def test_stores_attributes(self):
        err = MemoryLimitExceeded(estimated_mb=512.3, limit_mb=256)
        assert err.estimated_mb == 512.3
        assert err.limit_mb == 256

    def test_message_includes_values(self):
        err = MemoryLimitExceeded(estimated_mb=512.3, limit_mb=256)
        assert "512.3MB" in err.message
        assert "256MB" in err.message

    def test_message_suggests_flags(self):
        err = MemoryLimitExceeded(estimated_mb=100.0, limit_mb=50)
        assert "--sample" in err.message
        assert "--limit" in err.message
        assert "--filter" in err.message
        assert "--memory-limit" in err.message

    def test_str_matches_message(self):
        err = MemoryLimitExceeded(estimated_mb=200.0, limit_mb=100)
        assert str(err) == err.message

    def test_details_is_none(self):
        err = MemoryLimitExceeded(estimated_mb=200.0, limit_mb=100)
        assert err.details is None

    def test_estimated_mb_formatting(self):
        err = MemoryLimitExceeded(estimated_mb=512.456, limit_mb=256)
        assert "512.5MB" in err.message

    def test_inherits_cjasdr_error(self):
        assert issubclass(MemoryLimitExceeded, CJASDRError)


class TestApiConnectionHintStatusFromMessage:
    """Tests for _api_connection_hint_status_from_message keyword fallbacks."""

    def test_unauthorized_keyword_without_numeric_status_returns_401(self):
        from cja_auto_sdr.core.exceptions import _api_connection_hint_status_from_message

        # Marker present ("unauthorized") but no 3-digit code, so coercion yields
        # nothing and the "unauthorized" keyword fallback returns 401.
        assert _api_connection_hint_status_from_message("Request unauthorized") == 401

    def test_forbidden_keyword_without_numeric_status_returns_403(self):
        from cja_auto_sdr.core.exceptions import _api_connection_hint_status_from_message

        # Marker present ("forbidden") but no coercible 401/403 status, so the
        # "forbidden" keyword fallback returns 403.
        assert _api_connection_hint_status_from_message("Access forbidden") == 403
