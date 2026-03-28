"""Edge-case tests for api/resilience.py.

Covers: _parse_env_numeric, _effective_retry_config,
ErrorMessageHelper format consistency, CircuitBreaker compatibility.
"""

import logging
import os
from unittest.mock import patch

import pytest

from cja_auto_sdr.api.resilience import (
    CircuitBreaker,
    ErrorMessageHelper,
    _effective_retry_config,
    _parse_env_numeric,
)
from cja_auto_sdr.core.config import CircuitBreakerConfig, CircuitState
from cja_auto_sdr.core.constants import DEFAULT_RETRY_CONFIG

# ==================== _parse_env_numeric ====================


class TestParseEnvNumeric:
    """Edge cases for _parse_env_numeric."""

    def test_none_returns_none(self):
        assert _parse_env_numeric(None, int) is None

    def test_empty_string_returns_none(self):
        assert _parse_env_numeric("", int) is None

    def test_whitespace_only_returns_none(self):
        """Whitespace-only string returns None (current behavior)."""
        assert _parse_env_numeric("   ", int) is None

    def test_valid_int_string(self):
        assert _parse_env_numeric("42", int) == 42

    def test_valid_float_string(self):
        assert _parse_env_numeric("3.14", float) == pytest.approx(3.14)

    def test_leading_trailing_whitespace_int(self):
        """Python int() strips whitespace: ' 3 ' -> 3."""
        assert _parse_env_numeric(" 3 ", int) == 3

    def test_leading_trailing_whitespace_float(self):
        """Python float() strips whitespace: ' 2.5 ' -> 2.5."""
        assert _parse_env_numeric(" 2.5 ", float) == pytest.approx(2.5)

    def test_inf_rejected_for_float(self):
        """'inf' is not finite, so it should be rejected."""
        assert _parse_env_numeric("inf", float) is None

    def test_negative_inf_rejected_for_float(self):
        assert _parse_env_numeric("-inf", float) is None

    def test_nan_rejected_for_float(self):
        assert _parse_env_numeric("nan", float) is None

    def test_exponential_notation_accepted_for_float(self):
        """'1e10' is a valid Python float."""
        assert _parse_env_numeric("1e10", float) == pytest.approx(1e10)

    def test_non_numeric_string_returns_none(self):
        assert _parse_env_numeric("abc", int) is None

    def test_non_numeric_string_float_returns_none(self):
        assert _parse_env_numeric("not-a-number", float) is None

    def test_negative_int(self):
        assert _parse_env_numeric("-5", int) == -5

    def test_zero_int(self):
        assert _parse_env_numeric("0", int) == 0

    def test_zero_float(self):
        assert _parse_env_numeric("0.0", float) == pytest.approx(0.0)


# ==================== _effective_retry_config ====================


class TestEffectiveRetryConfig:
    """Edge cases for _effective_retry_config env var handling."""

    def test_no_env_vars_returns_defaults(self):
        with patch.dict(os.environ, {}, clear=True):
            # Remove any retry-related env vars
            for key in ("MAX_RETRIES", "RETRY_BASE_DELAY", "RETRY_MAX_DELAY"):
                os.environ.pop(key, None)
            cfg = _effective_retry_config()
            assert cfg["max_retries"] == DEFAULT_RETRY_CONFIG["max_retries"]
            assert cfg["base_delay"] == DEFAULT_RETRY_CONFIG["base_delay"]
            assert cfg["max_delay"] == DEFAULT_RETRY_CONFIG["max_delay"]

    def test_valid_max_retries_override(self):
        with patch.dict(os.environ, {"MAX_RETRIES": "7"}, clear=False):
            cfg = _effective_retry_config()
            assert cfg["max_retries"] == 7

    def test_valid_base_delay_override(self):
        with patch.dict(os.environ, {"RETRY_BASE_DELAY": "2.5"}, clear=False):
            cfg = _effective_retry_config()
            assert cfg["base_delay"] == pytest.approx(2.5)

    def test_valid_max_delay_override(self):
        with patch.dict(os.environ, {"RETRY_MAX_DELAY": "120.0"}, clear=False):
            cfg = _effective_retry_config()
            assert cfg["max_delay"] == pytest.approx(120.0)

    def test_invalid_max_retries_warns_and_uses_default(self, caplog):
        with patch.dict(os.environ, {"MAX_RETRIES": "not_a_number"}, clear=False):
            with caplog.at_level(logging.WARNING):
                cfg = _effective_retry_config()
            assert cfg["max_retries"] == DEFAULT_RETRY_CONFIG["max_retries"]
            assert "Ignoring invalid MAX_RETRIES" in caplog.text

    def test_negative_max_retries_warns(self, caplog):
        with patch.dict(os.environ, {"MAX_RETRIES": "-1"}, clear=False):
            with caplog.at_level(logging.WARNING):
                cfg = _effective_retry_config()
            assert cfg["max_retries"] == DEFAULT_RETRY_CONFIG["max_retries"]

    def test_max_delay_less_than_base_delay_auto_corrects(self, caplog):
        with patch.dict(os.environ, {"RETRY_BASE_DELAY": "10.0", "RETRY_MAX_DELAY": "2.0"}, clear=False):
            with caplog.at_level(logging.WARNING):
                cfg = _effective_retry_config()
            assert cfg["max_delay"] == cfg["base_delay"]
            assert "Ignoring invalid retry delay window" in caplog.text

    def test_multiple_env_vars_set_simultaneously(self):
        env = {"MAX_RETRIES": "5", "RETRY_BASE_DELAY": "0.5", "RETRY_MAX_DELAY": "60.0"}
        with patch.dict(os.environ, env, clear=False):
            cfg = _effective_retry_config()
            assert cfg["max_retries"] == 5
            assert cfg["base_delay"] == pytest.approx(0.5)
            assert cfg["max_delay"] == pytest.approx(60.0)

    def test_zero_max_retries_accepted(self):
        """Zero retries means one attempt only — no retries."""
        with patch.dict(os.environ, {"MAX_RETRIES": "0"}, clear=False):
            cfg = _effective_retry_config()
            assert cfg["max_retries"] == 0

    def test_zero_base_delay_accepted(self):
        with patch.dict(os.environ, {"RETRY_BASE_DELAY": "0"}, clear=False):
            cfg = _effective_retry_config()
            assert cfg["base_delay"] == pytest.approx(0.0)


# ==================== ErrorMessageHelper ====================


class TestErrorMessageHelperFormatConsistency:
    """Verify ErrorMessageHelper produces consistent, non-empty messages."""

    KNOWN_STATUS_CODES = [400, 401, 403, 404, 429, 500, 502, 503, 504]

    @pytest.mark.parametrize("status_code", KNOWN_STATUS_CODES)
    def test_known_status_produces_non_empty_message(self, status_code):
        msg = ErrorMessageHelper.get_http_error_message(status_code)
        assert msg, f"Empty message for status {status_code}"

    @pytest.mark.parametrize("status_code", KNOWN_STATUS_CODES)
    def test_known_status_contains_code_in_output(self, status_code):
        msg = ErrorMessageHelper.get_http_error_message(status_code)
        assert str(status_code) in msg

    @pytest.mark.parametrize("status_code", KNOWN_STATUS_CODES)
    def test_known_status_has_sections(self, status_code):
        msg = ErrorMessageHelper.get_http_error_message(status_code)
        assert "Why this happened:" in msg
        assert "How to fix it:" in msg

    @pytest.mark.parametrize("status_code", KNOWN_STATUS_CODES)
    def test_known_status_has_numbered_suggestions(self, status_code):
        msg = ErrorMessageHelper.get_http_error_message(status_code)
        numbered_lines = [line.lstrip() for line in msg.splitlines()]
        assert any(line.startswith("1. ") for line in numbered_lines)
        assert any(line.startswith("2. ") for line in numbered_lines)

    def test_unknown_status_produces_message(self):
        msg = ErrorMessageHelper.get_http_error_message(418)
        assert "HTTP 418" in msg
        assert "How to fix it:" in msg

    def test_network_error_message_connection(self):
        msg = ErrorMessageHelper.get_network_error_message(ConnectionError("test"))
        assert "ConnectionError" in msg
        assert "How to fix it:" in msg

    def test_network_error_message_timeout(self):
        msg = ErrorMessageHelper.get_network_error_message(TimeoutError("test"))
        assert "TimeoutError" in msg

    def test_network_error_unknown_type(self):
        msg = ErrorMessageHelper.get_network_error_message(RuntimeError("test"))
        assert "RuntimeError" in msg
        assert "How to fix it:" in msg

    def test_config_error_known_types(self):
        for error_type in ("file_not_found", "invalid_json", "missing_credentials", "invalid_format"):
            msg = ErrorMessageHelper.get_config_error_message(error_type)
            assert msg, f"Empty message for config error type {error_type}"
            assert "How to fix it:" in msg

    def test_config_error_unknown_type(self):
        msg = ErrorMessageHelper.get_config_error_message("unknown_type", "some detail")
        assert "some detail" in msg


# ==================== CircuitBreaker ====================


class TestCircuitBreakerCompatibility:
    """Lock current CircuitBreaker contracts for v3.4.9."""

    def test_default_config_is_valid(self):
        cb = CircuitBreaker()
        assert cb.state == CircuitState.CLOSED
        assert cb.allow_request() is True

    def test_timeout_zero_allows_immediate_half_open(self):
        """timeout_seconds=0 means immediate OPEN -> HALF_OPEN recovery probe."""
        config = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=0)
        cb = CircuitBreaker(config=config)

        # Trip the circuit
        cb.record_failure(Exception("fail"))
        assert cb.state == CircuitState.OPEN

        # With timeout=0, next allow_request should transition to HALF_OPEN
        assert cb.allow_request() is True
        assert cb.state == CircuitState.HALF_OPEN

    def test_half_open_closes_after_success_threshold(self):
        config = CircuitBreakerConfig(failure_threshold=1, success_threshold=2, timeout_seconds=0)
        cb = CircuitBreaker(config=config)

        # Trip to OPEN
        cb.record_failure(Exception("fail"))
        assert cb.state == CircuitState.OPEN

        # Move to HALF_OPEN via allow_request
        cb.allow_request()
        assert cb.state == CircuitState.HALF_OPEN

        # First success — still HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN

        # Second success — closes
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_half_open_reopens_on_failure(self):
        config = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=0)
        cb = CircuitBreaker(config=config)

        cb.record_failure(Exception("fail"))
        cb.allow_request()  # OPEN -> HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_failure(Exception("fail again"))
        assert cb.state == CircuitState.OPEN

    def test_open_rejects_during_timeout(self):
        config = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=9999)
        cb = CircuitBreaker(config=config)

        cb.record_failure(Exception("fail"))
        assert cb.state == CircuitState.OPEN
        assert cb.allow_request() is False

    def test_statistics_keys_stable(self):
        cb = CircuitBreaker()
        stats = cb.get_statistics()
        expected_keys = {
            "state",
            "failure_count",
            "success_count",
            "total_requests",
            "total_failures",
            "total_rejections",
            "trips",
            "time_in_state_seconds",
            "time_until_retry_seconds",
        }
        assert set(stats.keys()) == expected_keys
