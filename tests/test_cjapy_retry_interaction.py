"""Contract tests for real cjapy-style status payload normalization.

cjapy 0.3.1 returns parsed JSON dicts (not Response objects) and does not
inject a snake_case ``status_code`` field. The upstream ``AdobeRequest._build_session``
installs a urllib3.Retry adapter that covers 429/500/502/503/504 with exponential
backoff.

Post-v3.5.14 contract:

- the retry wrapper normalizes camelCase ``statusCode``, nested ``error.statusCode``,
  and ``response.statusCode`` the same way it normalized legacy ``status_code``
- ``RETRYABLE_STATUS_CODES`` is narrowed to ``{408}`` so we don't stack retries on
  top of cjapy's adapter; 429/500/502/503/504 pass through to the caller
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from cja_auto_sdr.api.resilience import (
    CircuitBreaker,
    _extract_http_status_code_from_result,
    make_api_call_with_retry,
)
from cja_auto_sdr.core.config import CircuitBreakerConfig
from cja_auto_sdr.core.exceptions import RetryableHTTPError


@pytest.fixture
def recorded_sleeps(monkeypatch):
    """Capture retry sleeps without actually blocking the test."""
    sleeps: list[float] = []

    def _fake_sleep(seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr("cja_auto_sdr.api.resilience.time.sleep", _fake_sleep)
    return sleeps


class TestUpstreamAdapterNonOverlapContract:
    """Project retries are disjoint from cjapy adapter statuses.

    ``cjapy.connector.AdobeRequest._build_session`` installs a urllib3.Retry adapter
    that handles 429/500/502/503/504 with exponential backoff. When a response
    reaches the project layer, the adapter has already retried. Project-layer retries
    on the same statuses would stack, so ``RETRYABLE_STATUS_CODES`` must exclude them.

    408 is NOT in cjapy's status_forcelist, so it remains the project layer's responsibility.
    """

    @pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
    def test_upstream_adapter_statuses_do_not_trigger_project_retry(self, recorded_sleeps, status):
        """Adapter-visible statuses reach us only after cjapy already retried — we must pass them through."""
        payload = {"statusCode": status, "message": "upstream exhausted"}
        api_func = MagicMock(return_value=payload)

        result = make_api_call_with_retry(api_func, operation_name="probe")

        assert result == payload
        assert api_func.call_count == 1, "project layer must not retry adapter-visible statuses"
        assert recorded_sleeps == []

    @pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
    def test_legacy_status_code_key_also_passes_through_for_adapter_statuses(self, recorded_sleeps, status):
        """Snake_case status_code must behave the same as camelCase for adapter-visible statuses."""
        payload = {"status_code": status, "message": "upstream exhausted"}
        api_func = MagicMock(return_value=payload)

        result = make_api_call_with_retry(api_func, operation_name="probe")

        assert result == payload
        assert api_func.call_count == 1
        assert recorded_sleeps == []


class TestProjectOwnedRetryableStatuses:
    """408 remains project-retryable (not in cjapy's status_forcelist)."""

    def test_408_retries_on_camelCase_statusCode(self, recorded_sleeps):
        api_func = MagicMock(
            side_effect=[
                {"statusCode": 408, "message": "request timeout"},
                {"statusCode": 200, "data": "ok"},
            ],
        )

        result = make_api_call_with_retry(api_func, operation_name="probe")

        assert result == {"statusCode": 200, "data": "ok"}
        assert api_func.call_count == 2
        assert len(recorded_sleeps) == 1

    def test_408_retries_on_legacy_status_code_key(self, recorded_sleeps):
        api_func = MagicMock(
            side_effect=[
                {"status_code": 408, "message": "request timeout"},
                {"status_code": 200, "data": "ok"},
            ],
        )

        result = make_api_call_with_retry(api_func, operation_name="probe")

        assert result == {"status_code": 200, "data": "ok"}
        assert api_func.call_count == 2
        assert len(recorded_sleeps) == 1

    def test_408_raises_retryable_http_error_after_exhaustion(self, monkeypatch):
        monkeypatch.setenv("MAX_RETRIES", "0")

        with pytest.raises(RetryableHTTPError) as exc_info:
            make_api_call_with_retry(
                lambda: {"statusCode": 408, "message": "request timeout"},
                operation_name="probe",
            )

        assert exc_info.value.status_code == 408

    def test_408_raises_on_nested_error_statusCode(self, monkeypatch):
        monkeypatch.setenv("MAX_RETRIES", "0")

        with pytest.raises(RetryableHTTPError):
            make_api_call_with_retry(
                lambda: {"error": {"statusCode": 408, "message": "request timeout"}},
                operation_name="probe",
            )

    def test_408_raises_on_response_nested_statusCode(self, monkeypatch):
        monkeypatch.setenv("MAX_RETRIES", "0")

        with pytest.raises(RetryableHTTPError):
            make_api_call_with_retry(
                lambda: {"response": {"statusCode": 408, "message": "request timeout"}},
                operation_name="probe",
            )


class TestCircuitBreakerFailureAccounting:
    """CircuitBreaker records one failure per exhausted op, not per retry attempt."""

    def test_circuit_breaker_records_one_failure_after_retry_exhaustion(self, recorded_sleeps):
        breaker = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=2))
        # 408 is project-retryable, so this will exhaust all retries.
        api_func = MagicMock(return_value={"statusCode": 408, "message": "request timeout"})

        with pytest.raises(RetryableHTTPError):
            make_api_call_with_retry(api_func, operation_name="probe", circuit_breaker=breaker)

        stats = breaker.get_statistics()
        assert api_func.call_count == 4  # initial + 3 default retries
        assert stats["total_failures"] == 1

    def test_circuit_breaker_records_no_failure_when_status_passes_through(self, recorded_sleeps):
        """503 is no longer project-retryable, so the breaker doesn't see a failure."""
        breaker = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=2))
        api_func = MagicMock(return_value={"statusCode": 503, "message": "backend timeout"})

        result = make_api_call_with_retry(api_func, operation_name="probe", circuit_breaker=breaker)

        assert result == {"statusCode": 503, "message": "backend timeout"}
        stats = breaker.get_statistics()
        # A returned (non-raising) payload is recorded as success for the circuit breaker.
        assert stats["total_failures"] == 0


class TestNonRetryableStatusesPassThrough:
    """Payloads carrying non-retryable statuses are returned as-is with no retry."""

    @pytest.mark.parametrize("status", [400, 401, 403, 404, 422])
    def test_client_error_passes_through(self, recorded_sleeps, status):
        payload = {"statusCode": status, "message": "client error"}
        api_func = MagicMock(return_value=payload)

        result = make_api_call_with_retry(api_func, operation_name="probe")

        assert result == payload
        assert api_func.call_count == 1
        assert recorded_sleeps == []


class TestExtractHttpStatusCode:
    """Direct tests for the status-extraction helper."""

    def test_extracts_top_level_statusCode(self):
        assert _extract_http_status_code_from_result({"statusCode": 503}) == 503

    def test_extracts_top_level_status_code(self):
        assert _extract_http_status_code_from_result({"status_code": 503}) == 503

    def test_extracts_nested_error_statusCode(self):
        assert _extract_http_status_code_from_result({"error": {"statusCode": 500}}) == 500

    def test_extracts_nested_response_statusCode(self):
        assert _extract_http_status_code_from_result({"response": {"statusCode": 429}}) == 429

    def test_extracts_status_attribute(self):
        class _Resp:
            status_code = 502

        assert _extract_http_status_code_from_result(_Resp()) == 502

    def test_extracts_statusCode_attribute(self):
        class _Resp:
            statusCode = 504

        assert _extract_http_status_code_from_result(_Resp()) == 504

    def test_returns_none_for_no_status(self):
        assert _extract_http_status_code_from_result({"data": "ok"}) is None

    def test_returns_none_for_none(self):
        assert _extract_http_status_code_from_result(None) is None

    def test_returns_none_for_out_of_range_status(self):
        assert _extract_http_status_code_from_result({"statusCode": 9999}) is None

    def test_returns_none_for_bool_status(self):
        assert _extract_http_status_code_from_result({"statusCode": True}) is None

    def test_extracts_http_status_key(self):
        assert _extract_http_status_code_from_result({"http_status": 503}) == 503
