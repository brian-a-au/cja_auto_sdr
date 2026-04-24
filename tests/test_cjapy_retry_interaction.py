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
- when an adapter-exhausted payload carries a status in
  ``UPSTREAM_ADAPTER_STATUS_CODES`` (429/500/502/503/504), the wrapper records a
  circuit-breaker failure and suppresses the success-after-retry log so
  repeated upstream distress trips the breaker and telemetry is coherent
"""

from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pytest

from cja_auto_sdr.api.resilience import (
    CircuitBreaker,
    _extract_http_status_code_from_result,
    _is_upstream_failure_payload,
    make_api_call_with_retry,
    retry_with_backoff,
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

    def test_circuit_breaker_records_failure_when_adapter_exhausted_status_passes_through(self, recorded_sleeps):
        """Adapter-exhausted 5xx/429 pass-throughs must count as breaker failures.

        cjapy already retried these upstream. The payload reaching us is a real
        upstream failure signal, so the breaker must see it even though we don't
        retry again at the project layer.
        """
        breaker = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=2))
        api_func = MagicMock(return_value={"statusCode": 503, "message": "backend timeout"})

        result = make_api_call_with_retry(api_func, operation_name="probe", circuit_breaker=breaker)

        assert result == {"statusCode": 503, "message": "backend timeout"}
        stats = breaker.get_statistics()
        assert stats["total_failures"] == 1
        assert api_func.call_count == 1

    def test_back_to_back_adapter_exhausted_503_trips_circuit_breaker(self, recorded_sleeps):
        """Two consecutive 503 pass-throughs open a threshold-2 breaker."""
        breaker = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=2))
        api_func = MagicMock(return_value={"statusCode": 503, "message": "backend timeout"})

        make_api_call_with_retry(api_func, operation_name="probe", circuit_breaker=breaker)
        make_api_call_with_retry(api_func, operation_name="probe", circuit_breaker=breaker)

        stats = breaker.get_statistics()
        assert stats["total_failures"] == 2
        assert stats["state"] == "open"
        assert stats["trips"] == 1

    def test_nested_error_statusCode_503_records_breaker_failure(self, recorded_sleeps):
        """Nested upstream-failure status carries through the same contract."""
        breaker = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=5))
        api_func = MagicMock(return_value={"error": {"statusCode": 500, "message": "upstream"}})

        make_api_call_with_retry(api_func, operation_name="probe", circuit_breaker=breaker)

        assert breaker.get_statistics()["total_failures"] == 1

    def test_non_upstream_4xx_payload_still_records_breaker_success(self, recorded_sleeps):
        """401/403/404 are caller-side errors, not infrastructure distress.

        They are not in UPSTREAM_ADAPTER_STATUS_CODES and must not consume
        breaker failure budget; the endpoint answered, the breaker is healthy.
        """
        breaker = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=2))
        api_func = MagicMock(return_value={"statusCode": 401, "message": "unauthorized"})

        make_api_call_with_retry(api_func, operation_name="probe", circuit_breaker=breaker)

        stats = breaker.get_statistics()
        assert stats["total_failures"] == 0
        assert stats["state"] == "closed"

    def test_success_after_retry_log_suppressed_on_adapter_exhausted_pass_through(
        self,
        recorded_sleeps,
        monkeypatch,
        caplog,
    ):
        """ConnectionError -> 503 pass-through must NOT log '✓ succeeded on attempt'.

        Previously the retry wrapper logged success for any non-exception return,
        even when the return was an error-shaped payload — contradictory telemetry
        next to caller-side failure handling.
        """
        monkeypatch.setenv("MAX_RETRIES", "2")
        api_func = MagicMock(
            side_effect=[
                ConnectionError("transient"),
                {"statusCode": 503, "message": "backend timeout"},
            ],
        )

        with caplog.at_level(logging.INFO, logger="cja_auto_sdr.api.resilience"):
            result = make_api_call_with_retry(api_func, operation_name="probe")

        assert result == {"statusCode": 503, "message": "backend timeout"}
        assert api_func.call_count == 2
        assert not any("succeeded on attempt" in record.getMessage() for record in caplog.records)

    def test_success_after_retry_log_emitted_on_genuine_recovery(
        self,
        recorded_sleeps,
        monkeypatch,
        caplog,
    ):
        """ConnectionError -> 200 still logs the success-after-retry line."""
        monkeypatch.setenv("MAX_RETRIES", "2")
        api_func = MagicMock(
            side_effect=[
                ConnectionError("transient"),
                {"statusCode": 200, "data": "ok"},
            ],
        )

        with caplog.at_level(logging.INFO, logger="cja_auto_sdr.api.resilience"):
            result = make_api_call_with_retry(api_func, operation_name="probe")

        assert result == {"statusCode": 200, "data": "ok"}
        assert any("succeeded on attempt" in record.getMessage() for record in caplog.records)


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


class TestIsUpstreamFailurePayload:
    """The shared predicate used by both make_api_call_with_retry and retry_with_backoff."""

    @pytest.mark.parametrize("status", [429, 500, 502, 503, 504])
    def test_true_for_adapter_statuses(self, status):
        assert _is_upstream_failure_payload({"statusCode": status}) is True

    def test_true_for_nested_error_statusCode(self):
        assert _is_upstream_failure_payload({"error": {"statusCode": 500}}) is True

    @pytest.mark.parametrize("status", [200, 204, 301, 400, 401, 403, 404, 408, 422])
    def test_false_for_non_upstream_statuses(self, status):
        assert _is_upstream_failure_payload({"statusCode": status}) is False

    def test_false_for_no_status_payload(self):
        assert _is_upstream_failure_payload({"data": "ok"}) is False

    def test_false_for_none(self):
        assert _is_upstream_failure_payload(None) is False


class TestRetryWithBackoffDecorator:
    """The decorator shares the log-suppression rule with make_api_call_with_retry.

    It has no circuit-breaker plumbing, so the only signal to fix is the
    ``✓ … succeeded on attempt …`` log — which must not fire when the final
    return is an adapter-exhausted 5xx/429 payload (cjapy already retried).
    """

    def test_success_log_suppressed_on_adapter_exhausted_pass_through(self, recorded_sleeps, caplog):
        calls = {"n": 0}

        @retry_with_backoff(max_retries=2, base_delay=0.001, max_delay=0.01)
        def flaky():
            calls["n"] += 1
            if calls["n"] < 2:
                raise ConnectionError("transient")
            return {"statusCode": 503, "message": "backend timeout"}

        with caplog.at_level(logging.INFO, logger="cja_auto_sdr.api.resilience"):
            result = flaky()

        assert result == {"statusCode": 503, "message": "backend timeout"}
        assert calls["n"] == 2
        assert not any("succeeded on attempt" in record.getMessage() for record in caplog.records)

    def test_success_log_emitted_on_genuine_recovery(self, recorded_sleeps, caplog):
        calls = {"n": 0}

        @retry_with_backoff(max_retries=2, base_delay=0.001, max_delay=0.01)
        def flaky():
            calls["n"] += 1
            if calls["n"] < 2:
                raise ConnectionError("transient")
            return {"statusCode": 200, "data": "ok"}

        with caplog.at_level(logging.INFO, logger="cja_auto_sdr.api.resilience"):
            result = flaky()

        assert result == {"statusCode": 200, "data": "ok"}
        assert any("succeeded on attempt" in record.getMessage() for record in caplog.records)

    def test_no_log_on_first_attempt_success_even_with_upstream_status(self, recorded_sleeps, caplog):
        """attempt == 0 never emits the success-after-retry log regardless of payload."""

        @retry_with_backoff(max_retries=2, base_delay=0.001, max_delay=0.01)
        def immediate():
            return {"statusCode": 503, "message": "backend timeout"}

        with caplog.at_level(logging.INFO, logger="cja_auto_sdr.api.resilience"):
            immediate()

        assert not any("succeeded on attempt" in record.getMessage() for record in caplog.records)
