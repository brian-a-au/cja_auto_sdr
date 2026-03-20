"""Tests for logging redaction, JSON formatting, and logging setup.

Validates that sensitive data is properly redacted in log messages,
extra fields, and exception info. Also covers the JSON formatter,
context logger adapter, and logging setup helpers.
"""

import json
import logging
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cja_auto_sdr.core.logging import (
    _CORE_DEPENDENCIES,
    ContextLoggerAdapter,
    JSONFormatter,
    SensitiveDataFilter,
    _cached_startup_dependency_versions,
    _collect_dependency_versions,
    _infer_run_mode,
    _is_reserved_or_private_record_key,
    _is_sensitive_field,
    _normalize_field_name,
    _redact_captured_value,
    _redact_message,
    _redact_value,
    _safe_record_message,
    _safe_str,
    _unwrap_logger,
    flush_logging_handlers,
    with_log_context,
)


# ---------------------------------------------------------------------------
# _normalize_field_name
# ---------------------------------------------------------------------------
class TestNormalizeFieldName:
    def test_camel_case(self):
        assert _normalize_field_name("clientSecret") == "client_secret"

    def test_pascal_case(self):
        assert _normalize_field_name("ClientSecret") == "client_secret"

    def test_snake_case_passthrough(self):
        assert _normalize_field_name("client_secret") == "client_secret"

    def test_kebab_case(self):
        assert _normalize_field_name("client-secret") == "client_secret"

    def test_spaces(self):
        assert _normalize_field_name("client secret") == "client_secret"

    def test_mixed_separators(self):
        assert _normalize_field_name("My-API_key") == "my_api_key"

    def test_leading_trailing_whitespace(self):
        assert _normalize_field_name("  accessToken  ") == "access_token"

    def test_consecutive_uppercase(self):
        assert _normalize_field_name("HTTPHeader") == "http_header"

    def test_all_uppercase(self):
        assert _normalize_field_name("PASSWORD") == "password"

    def test_empty_string(self):
        assert _normalize_field_name("") == ""

    def test_single_word_lowercase(self):
        assert _normalize_field_name("token") == "token"

    def test_non_alnum_stripped(self):
        assert _normalize_field_name("api***key") == "api_key"


# ---------------------------------------------------------------------------
# _safe_str
# ---------------------------------------------------------------------------
class TestSafeStr:
    def test_normal_string(self):
        assert _safe_str("hello") == "hello"

    def test_integer(self):
        assert _safe_str(42) == "42"

    def test_none(self):
        assert _safe_str(None) == "None"

    def test_unprintable_object(self):
        class Bad:
            def __str__(self):
                raise TypeError("boom")

        assert _safe_str(Bad()) == "<unprintable>"

    def test_unprintable_object_value_error(self):
        class Bad:
            def __str__(self):
                raise ValueError("boom")

        assert _safe_str(Bad()) == "<unprintable>"

    def test_unprintable_object_runtime_error(self):
        class Bad:
            def __str__(self):
                raise RuntimeError("boom")

        assert _safe_str(Bad()) == "<unprintable>"


# ---------------------------------------------------------------------------
# _safe_record_message
# ---------------------------------------------------------------------------
class TestSafeRecordMessage:
    def test_missing_mapping_placeholder_key_falls_back(self):
        record = logging.LogRecord(
            name="test.logger",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg="%(user)s logged in",
            args=({"id": "u123"},),
            exc_info=None,
        )

        message = _safe_record_message(record)

        assert message.endswith("[log-message-format-error]")
        assert "%(user)s logged in" in message

    def test_runtime_error_from_get_message_falls_back(self):
        record = MagicMock(spec=logging.LogRecord)
        record.getMessage.side_effect = RuntimeError("boom")
        record.msg = "token=%s"

        message = _safe_record_message(record)

        assert message.endswith("[log-message-format-error]")


# ---------------------------------------------------------------------------
# _is_sensitive_field
# ---------------------------------------------------------------------------
class TestIsSensitiveField:
    @pytest.mark.parametrize(
        "name",
        [
            "password",
            "passwd",
            "pwd",
            "secret",
            "client_secret",
            "token",
            "access_token",
            "refresh_token",
            "bearer_token",
            "api_key",
            "apikey",
            "authorization",
            "auth_header",
            "private_key",
        ],
    )
    def test_direct_sensitive_names(self, name):
        assert _is_sensitive_field(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            "clientSecret",
            "accessToken",
            "refreshToken",
            "bearerToken",
            "apiKey",
            "authHeader",
            "privateKey",
        ],
    )
    def test_camel_case_sensitive_names(self, name):
        assert _is_sensitive_field(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            "ClientSecret",
            "AccessToken",
            "RefreshToken",
            "BearerToken",
            "ApiKey",
            "AuthHeader",
            "PrivateKey",
        ],
    )
    def test_pascal_case_sensitive_names(self, name):
        assert _is_sensitive_field(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            "my_api_key",
            "old_password",
            "db_secret",
            "jwt_token",
            "x_authorization",
        ],
    )
    def test_compound_sensitive_names(self, name):
        assert _is_sensitive_field(name) is True

    @pytest.mark.parametrize(
        "name",
        [
            "username",
            "email",
            "data_view_id",
            "name",
            "description",
            "count",
            "format",
            "level",
            "module",
        ],
    )
    def test_non_sensitive_names(self, name):
        assert _is_sensitive_field(name) is False

    def test_empty_string_is_not_sensitive(self):
        assert _is_sensitive_field("") is False

    def test_password_upper_case(self):
        assert _is_sensitive_field("PASSWORD") is True

    def test_mixed_case_api_key(self):
        assert _is_sensitive_field("API_KEY") is True


# ---------------------------------------------------------------------------
# _redact_captured_value
# ---------------------------------------------------------------------------
class TestRedactCapturedValue:
    def test_double_quoted_string(self):
        assert _redact_captured_value('"my_secret_value"') == '"[REDACTED]"'

    def test_single_quoted_string(self):
        assert _redact_captured_value("'my_secret_value'") == "'[REDACTED]'"

    def test_unquoted_string(self):
        assert _redact_captured_value("my_secret_value") == "[REDACTED]"

    def test_empty_quoted_string(self):
        assert _redact_captured_value('""') == '"[REDACTED]"'

    def test_single_char_not_treated_as_quoted(self):
        assert _redact_captured_value("x") == "[REDACTED]"


# ---------------------------------------------------------------------------
# _redact_message
# ---------------------------------------------------------------------------
class TestRedactMessage:
    def test_password_equals_value(self):
        result = _redact_message("password=foo123")
        assert "foo123" not in result
        assert "[REDACTED]" in result

    def test_bearer_token(self):
        result = _redact_message("Bearer eyJhbGciOiJIUzI1NiJ9.abc.def")
        assert "eyJhbGciOiJIUzI1NiJ9" not in result
        assert "Bearer [REDACTED]" in result

    def test_bearer_case_insensitive(self):
        result = _redact_message("bearer mytoken123")
        assert "mytoken123" not in result

    def test_quoted_key_value_single_quotes(self):
        result = _redact_message("'secret': 'myval'")
        assert "myval" not in result
        assert "[REDACTED]" in result

    def test_quoted_key_value_double_quotes(self):
        result = _redact_message('"password": "super_secret"')
        assert "super_secret" not in result

    def test_unquoted_key_equals_value(self):
        result = _redact_message("token=abc123def")
        assert "abc123def" not in result

    def test_authorization_with_scheme(self):
        result = _redact_message("authorization: Basic dXNlcjpwYXNz")
        assert "dXNlcjpwYXNz" not in result
        assert "Basic" in result

    def test_no_sensitive_content_unchanged(self):
        msg = "Processing data view dv_12345 with 100 metrics"
        assert _redact_message(msg) == msg

    def test_api_key_redacted(self):
        result = _redact_message("api_key=ABCDEF123456")
        assert "ABCDEF123456" not in result

    def test_client_secret_in_json_like_string(self):
        result = _redact_message('{"client_secret": "s3cr3t_value"}')
        assert "s3cr3t_value" not in result

    def test_multiple_sensitive_fields_in_one_message(self):
        result = _redact_message("password=abc token=xyz")
        assert "abc" not in result
        assert "xyz" not in result
        assert result.count("[REDACTED]") >= 2


# ---------------------------------------------------------------------------
# _redact_value (recursive)
# ---------------------------------------------------------------------------
class TestRedactValue:
    def test_dict_sensitive_key_redacted(self):
        result = _redact_value({"password": "secret123", "name": "test"})
        assert result["password"] == "[REDACTED]"
        assert result["name"] == "test"

    def test_nested_dict(self):
        result = _redact_value({"config": {"api_key": "key123", "timeout": 30}})
        assert result["config"]["api_key"] == "[REDACTED]"
        assert result["config"]["timeout"] == 30

    def test_list_with_sensitive_dicts(self):
        result = _redact_value([{"token": "tok_abc"}, {"name": "safe"}])
        assert result[0]["token"] == "[REDACTED]"
        assert result[1]["name"] == "safe"

    def test_tuple_preserved_as_tuple(self):
        result = _redact_value(({"secret": "s"}, "hello"))
        assert isinstance(result, tuple)
        assert result[0]["secret"] == "[REDACTED]"
        assert result[1] == "hello"

    def test_string_with_sensitive_content(self):
        result = _redact_value("password=foo")
        assert isinstance(result, str)
        assert "foo" not in result

    def test_non_sensitive_string_unchanged(self):
        assert _redact_value("just a normal message") == "just a normal message"

    def test_integer_passthrough(self):
        assert _redact_value(42) == 42

    def test_none_passthrough(self):
        assert _redact_value(None) is None

    def test_bool_passthrough(self):
        assert _redact_value(True) is True

    def test_deeply_nested_structure(self):
        data = {"level1": {"level2": {"level3": {"private_key": "deep_secret"}}}}
        result = _redact_value(data)
        assert result["level1"]["level2"]["level3"]["private_key"] == "[REDACTED]"

    def test_empty_dict(self):
        assert _redact_value({}) == {}

    def test_empty_list(self):
        assert _redact_value([]) == []


# ---------------------------------------------------------------------------
# SensitiveDataFilter
# ---------------------------------------------------------------------------
class TestSensitiveDataFilter:
    def _make_record(self, msg="test", args=(), level=logging.INFO, **kwargs):
        record = logging.LogRecord(
            name="test.logger",
            level=level,
            pathname="test.py",
            lineno=1,
            msg=msg,
            args=args,
            exc_info=None,
        )
        for k, v in kwargs.items():
            setattr(record, k, v)
        return record

    def test_sensitive_message_is_redacted(self):
        f = SensitiveDataFilter()
        record = self._make_record(msg="password=hunter2")
        f.filter(record)
        assert "hunter2" not in record.msg
        assert "[REDACTED]" in record.msg

    def test_args_cleared_after_filtering(self):
        f = SensitiveDataFilter()
        record = self._make_record(msg="user=%s", args=("admin",))
        f.filter(record)
        assert record.args == ()

    def test_filter_always_returns_true(self):
        f = SensitiveDataFilter()
        record = self._make_record(msg="password=secret")
        assert f.filter(record) is True

    def test_idempotent_already_redacted_skips(self):
        f = SensitiveDataFilter()
        record = self._make_record(msg="token=abc123")
        f.filter(record)
        first_pass_msg = record.msg
        f.filter(record)
        assert record.msg == first_pass_msg

    def test_exc_info_redaction(self):
        f = SensitiveDataFilter()
        try:
            raise ValueError("password=s3cret in traceback")
        except ValueError:
            exc_info = sys.exc_info()
        record = self._make_record(msg="Error occurred")
        record.exc_info = exc_info
        f.filter(record)
        assert record.exc_text is not None
        assert "s3cret" not in record.exc_text
        assert "[REDACTED]" in record.exc_text

    def test_extra_fields_redaction(self):
        f = SensitiveDataFilter()
        record = self._make_record(msg="request info")
        record.extra_fields = {"api_key": "key_abc", "endpoint": "/v1/data"}
        f.filter(record)
        assert record.extra_fields["api_key"] == "[REDACTED]"
        assert record.extra_fields["endpoint"] == "/v1/data"

    def test_custom_attrs_with_sensitive_name_redacted(self):
        f = SensitiveDataFilter()
        record = self._make_record(msg="hello")
        record.__dict__["client_secret"] = "my_secret_value"
        f.filter(record)
        assert record.__dict__["client_secret"] == "[REDACTED]"

    def test_non_sensitive_custom_attr_with_sensitive_content_redacted(self):
        f = SensitiveDataFilter()
        record = self._make_record(msg="hello")
        record.__dict__["request_headers"] = "authorization: Bearer tok_abc"
        f.filter(record)
        assert "tok_abc" not in str(record.__dict__["request_headers"])

    def test_mapping_placeholder_key_error_does_not_raise(self):
        f = SensitiveDataFilter()
        record = self._make_record(msg="%(user)s token=%(token)s", args=({"token": "abc123"},))

        assert f.filter(record) is True
        assert record.args == ()
        assert "[log-message-format-error]" in record.msg

    def test_value_error_during_message_stringify_does_not_raise(self):
        class _BadStr:
            def __str__(self):
                raise ValueError("boom")

        f = SensitiveDataFilter()
        record = self._make_record(msg=_BadStr())

        assert f.filter(record) is True
        assert record.args == ()
        assert "<unprintable>" in record.msg
        assert "[log-message-format-error]" in record.msg


# ---------------------------------------------------------------------------
# JSONFormatter
# ---------------------------------------------------------------------------
class TestJSONFormatter:
    def _make_record(self, msg="test", level=logging.INFO, **kwargs):
        record = logging.LogRecord(
            name="test.logger",
            level=level,
            pathname="test.py",
            lineno=1,
            msg=msg,
            args=(),
            exc_info=None,
        )
        for k, v in kwargs.items():
            setattr(record, k, v)
        return record

    def test_produces_valid_json(self):
        fmt = JSONFormatter()
        record = self._make_record(msg="hello world")
        output = fmt.format(record)
        parsed = json.loads(output)
        assert isinstance(parsed, dict)

    def test_contains_expected_fields(self):
        fmt = JSONFormatter()
        record = self._make_record(msg="hello world")
        parsed = json.loads(fmt.format(record))
        for field in ("timestamp", "level", "logger", "message", "module", "function", "line"):
            assert field in parsed

    def test_level_matches(self):
        fmt = JSONFormatter()
        record = self._make_record(msg="warn", level=logging.WARNING)
        parsed = json.loads(fmt.format(record))
        assert parsed["level"] == "WARNING"

    def test_sensitive_message_redacted(self):
        fmt = JSONFormatter()
        record = self._make_record(msg="password=hunter2")
        parsed = json.loads(fmt.format(record))
        assert "hunter2" not in parsed["message"]
        assert "[REDACTED]" in parsed["message"]

    def test_extra_fields_included(self):
        fmt = JSONFormatter()
        record = self._make_record(msg="hello")
        record.extra_fields = {"data_view": "dv_123", "count": 5}
        parsed = json.loads(fmt.format(record))
        assert parsed["data_view"] == "dv_123"
        assert parsed["count"] == 5

    def test_sensitive_extra_fields_redacted(self):
        fmt = JSONFormatter()
        record = self._make_record(msg="hello")
        record.extra_fields = {"token": "secret_tok", "name": "safe"}
        parsed = json.loads(fmt.format(record))
        assert parsed["token"] == "[REDACTED]"
        assert parsed["name"] == "safe"

    def test_exc_info_included(self):
        fmt = JSONFormatter()
        try:
            raise RuntimeError("test error")
        except RuntimeError:
            exc_info = sys.exc_info()
        record = self._make_record(msg="fail")
        record.exc_info = exc_info
        parsed = json.loads(fmt.format(record))
        assert "exception" in parsed
        assert "RuntimeError" in parsed["exception"]

    def test_exc_info_with_sensitive_data_redacted(self):
        fmt = JSONFormatter()
        try:
            raise RuntimeError("token=ABCDEF")
        except RuntimeError:
            exc_info = sys.exc_info()
        record = self._make_record(msg="fail")
        record.exc_info = exc_info
        parsed = json.loads(fmt.format(record))
        assert "ABCDEF" not in parsed["exception"]

    def test_already_redacted_record_not_double_redacted(self):
        filt = SensitiveDataFilter()
        fmt = JSONFormatter()
        record = self._make_record(msg="password=hunter2")
        filt.filter(record)
        parsed = json.loads(fmt.format(record))
        assert "hunter2" not in parsed["message"]
        assert "[REDACTED]" in parsed["message"]

    def test_custom_record_attrs_in_json(self):
        fmt = JSONFormatter()
        record = self._make_record(msg="hello")
        record.__dict__["custom_field"] = "custom_value"
        parsed = json.loads(fmt.format(record))
        assert parsed.get("custom_field") == "custom_value"

    def test_message_runtime_error_is_non_fatal(self):
        fmt = JSONFormatter()
        record = self._make_record(msg="hello")
        record.getMessage = MagicMock(side_effect=RuntimeError("boom"))

        parsed = json.loads(fmt.format(record))
        assert "[log-message-format-error]" in parsed["message"]

    def test_non_string_extra_key_is_normalized(self):
        fmt = JSONFormatter()
        record = self._make_record(msg="hello")
        record.extra_fields = {("tuple", "key"): "value"}

        parsed = json.loads(fmt.format(record))
        assert "('tuple', 'key')" in parsed
        assert parsed["('tuple', 'key')"] == "value"

    def test_formatter_fallback_entry_on_unexpected_error(self):
        fmt = JSONFormatter()
        record = self._make_record(msg="hello")
        record.created = "bad-timestamp"

        parsed = json.loads(fmt.format(record))
        assert parsed["message"] == "[log-format-error]"


# ---------------------------------------------------------------------------
# _infer_run_mode
# ---------------------------------------------------------------------------
class TestInferRunMode:
    def test_batch_mode(self):
        assert _infer_run_mode(data_view_id="dv_123", batch_mode=True) == "batch"

    def test_batch_mode_without_data_view(self):
        assert _infer_run_mode(data_view_id=None, batch_mode=True) == "batch"

    def test_single_mode(self):
        assert _infer_run_mode(data_view_id="dv_123", batch_mode=False) == "single"

    def test_discovery_mode(self):
        assert _infer_run_mode(data_view_id=None, batch_mode=False) == "discovery"

    def test_empty_string_data_view_is_discovery(self):
        assert _infer_run_mode(data_view_id="", batch_mode=False) == "discovery"


# ---------------------------------------------------------------------------
# with_log_context / ContextLoggerAdapter
# ---------------------------------------------------------------------------
class TestWithLogContext:
    def test_logger_returns_context_adapter(self):
        base = logging.getLogger("test.context.base")
        adapter = with_log_context(base, request_id="req_123")
        assert isinstance(adapter, ContextLoggerAdapter)
        assert adapter.extra["request_id"] == "req_123"

    def test_mock_object_returned_as_is(self):
        mock_logger = MagicMock()
        result = with_log_context(mock_logger, foo="bar")
        assert result is mock_logger

    def test_existing_adapter_context_merged(self):
        base = logging.getLogger("test.context.merge")
        adapter1 = with_log_context(base, key1="val1")
        adapter2 = with_log_context(adapter1, key2="val2")
        assert isinstance(adapter2, ContextLoggerAdapter)
        assert adapter2.extra["key1"] == "val1"
        assert adapter2.extra["key2"] == "val2"

    def test_none_values_excluded(self):
        base = logging.getLogger("test.context.none")
        adapter = with_log_context(base, keep="yes", drop=None)
        assert "keep" in adapter.extra
        assert "drop" not in adapter.extra

    def test_context_overrides_existing(self):
        base = logging.getLogger("test.context.override")
        adapter1 = with_log_context(base, key="old")
        adapter2 = with_log_context(adapter1, key="new")
        assert adapter2.extra["key"] == "new"


class TestContextLoggerAdapterProcess:
    def test_process_merges_extra(self):
        base = logging.getLogger("test.adapter.process")
        adapter = ContextLoggerAdapter(base, {"ctx_key": "ctx_val"})
        msg, kwargs = adapter.process("hello", {"extra": {"call_key": "call_val"}})
        assert msg == "hello"
        assert kwargs["extra"]["ctx_key"] == "ctx_val"
        assert kwargs["extra"]["call_key"] == "call_val"

    def test_process_no_extra_in_kwargs(self):
        base = logging.getLogger("test.adapter.noextra")
        adapter = ContextLoggerAdapter(base, {"ctx_key": "ctx_val"})
        _msg, kwargs = adapter.process("hello", {})
        assert kwargs["extra"]["ctx_key"] == "ctx_val"

    def test_call_extra_overrides_context(self):
        base = logging.getLogger("test.adapter.override")
        adapter = ContextLoggerAdapter(base, {"key": "from_context"})
        _msg, kwargs = adapter.process("hello", {"extra": {"key": "from_call"}})
        assert kwargs["extra"]["key"] == "from_call"


# ---------------------------------------------------------------------------
# _unwrap_logger
# ---------------------------------------------------------------------------
class TestUnwrapLogger:
    def test_plain_logger(self):
        base = logging.getLogger("test.unwrap.plain")
        assert _unwrap_logger(base) is base

    def test_adapter_unwrapped(self):
        base = logging.getLogger("test.unwrap.adapter")
        adapter = logging.LoggerAdapter(base, {})
        assert _unwrap_logger(adapter) is base

    def test_nested_adapters_unwrapped(self):
        base = logging.getLogger("test.unwrap.nested")
        a1 = logging.LoggerAdapter(base, {})
        a2 = logging.LoggerAdapter(a1, {})
        assert _unwrap_logger(a2) is base

    def test_none_returns_none(self):
        assert _unwrap_logger(None) is None

    def test_non_logger_returns_none(self):
        assert _unwrap_logger("not a logger") is None


# ---------------------------------------------------------------------------
# _is_reserved_or_private_record_key
# ---------------------------------------------------------------------------
class TestIsReservedOrPrivateRecordKey:
    def test_standard_log_record_keys_are_reserved(self):
        for key in ("name", "msg", "args", "levelname", "levelno", "pathname", "lineno"):
            assert _is_reserved_or_private_record_key(key) is True

    def test_message_and_asctime_reserved(self):
        assert _is_reserved_or_private_record_key("message") is True
        assert _is_reserved_or_private_record_key("asctime") is True

    def test_extra_fields_key_reserved(self):
        assert _is_reserved_or_private_record_key("extra_fields") is True

    def test_private_underscore_keys(self):
        assert _is_reserved_or_private_record_key("_cja_redacted") is True
        assert _is_reserved_or_private_record_key("_internal") is True

    def test_non_string_key_is_reserved(self):
        assert _is_reserved_or_private_record_key(42) is True
        assert _is_reserved_or_private_record_key(None) is True

    def test_custom_key_not_reserved(self):
        assert _is_reserved_or_private_record_key("data_view_id") is False
        assert _is_reserved_or_private_record_key("sdr_version") is False


# ---------------------------------------------------------------------------
# flush_logging_handlers
# ---------------------------------------------------------------------------
class TestFlushLoggingHandlers:
    def test_flush_with_no_arguments(self):
        flush_logging_handlers()

    def test_flush_with_none(self):
        flush_logging_handlers(None)

    def test_flush_with_logger(self):
        logger = logging.getLogger("test.flush.logger")
        handler = logging.StreamHandler()
        logger.addHandler(handler)
        try:
            flush_logging_handlers(logger)
        finally:
            logger.removeHandler(handler)

    def test_flush_with_adapter(self):
        logger = logging.getLogger("test.flush.adapter")
        handler = logging.StreamHandler()
        logger.addHandler(handler)
        adapter = logging.LoggerAdapter(logger, {})
        try:
            flush_logging_handlers(adapter)
        finally:
            logger.removeHandler(handler)

    def test_flush_handler_exception_suppressed(self):
        logger = logging.getLogger("test.flush.error")
        bad_handler = MagicMock(spec=logging.Handler)
        bad_handler.flush.side_effect = OSError("disk full")
        logger.addHandler(bad_handler)
        logger.propagate = False
        try:
            flush_logging_handlers(logger)
        finally:
            logger.removeHandler(bad_handler)
            logger.propagate = True

    def test_deduplicates_shared_handler_across_propagation_chain(self):
        shared_handler = logging.StreamHandler()
        shared_handler.flush = MagicMock()

        parent = logging.getLogger("test.flush.parent")
        child = logging.getLogger("test.flush.parent.child")
        original_parent_handlers = list(parent.handlers)
        original_child_handlers = list(child.handlers)
        original_parent_propagate = parent.propagate
        original_child_propagate = child.propagate

        parent.handlers = [shared_handler]
        parent.propagate = False
        child.handlers = [shared_handler]
        child.propagate = True

        try:
            flush_logging_handlers(child)
        finally:
            child.handlers = original_child_handlers
            parent.handlers = original_parent_handlers
            child.propagate = original_child_propagate
            parent.propagate = original_parent_propagate

        shared_handler.flush.assert_called_once()

    def test_flushes_distinct_handlers_across_propagation_chain(self):
        parent_handler = logging.StreamHandler()
        child_handler = logging.StreamHandler()
        parent_handler.flush = MagicMock()
        child_handler.flush = MagicMock()

        parent = logging.getLogger("test.flush.distinct.parent")
        child = logging.getLogger("test.flush.distinct.parent.child")
        original_parent_handlers = list(parent.handlers)
        original_child_handlers = list(child.handlers)
        original_parent_propagate = parent.propagate
        original_child_propagate = child.propagate

        parent.handlers = [parent_handler]
        parent.propagate = False
        child.handlers = [child_handler]
        child.propagate = True

        try:
            flush_logging_handlers(child)
        finally:
            child.handlers = original_child_handlers
            parent.handlers = original_parent_handlers
            child.propagate = original_child_propagate
            parent.propagate = original_parent_propagate

        parent_handler.flush.assert_called_once()
        child_handler.flush.assert_called_once()


# ---------------------------------------------------------------------------
# _collect_dependency_versions
# ---------------------------------------------------------------------------
class TestCollectDependencyVersions:
    """Tests for the dependency version collection helper."""

    def test_returns_all_core_dependencies(self):
        """Result dict has an entry for every package in _CORE_DEPENDENCIES."""
        versions = _collect_dependency_versions()
        assert set(versions.keys()) == set(_CORE_DEPENDENCIES)

    def test_installed_packages_return_version_strings(self):
        """Packages that are installed should return non-empty version strings (not '?')."""
        versions = _collect_dependency_versions()
        # pandas and numpy are always installed in our test environment
        for pkg in ("pandas", "numpy"):
            assert versions[pkg] != "?", f"{pkg} should be installed"
            assert versions[pkg], f"{pkg} version should not be empty"

    def test_missing_package_returns_question_mark(self):
        """A package that is not installed should map to '?'."""
        import importlib.metadata

        with patch(
            "cja_auto_sdr.core.logging.importlib.metadata.version",
            side_effect=importlib.metadata.PackageNotFoundError("no-such-pkg"),
        ):
            versions = _collect_dependency_versions()
        for pkg in _CORE_DEPENDENCIES:
            assert versions[pkg] == "?"

    def test_partial_failure_only_affects_missing(self):
        """If one package is missing, others should still report real versions."""
        import importlib.metadata

        real_version = importlib.metadata.version

        def selective_fail(name: str) -> str:
            if name == "xlsxwriter":
                raise importlib.metadata.PackageNotFoundError(name)
            return real_version(name)

        with patch("cja_auto_sdr.core.logging.importlib.metadata.version", side_effect=selective_fail):
            versions = _collect_dependency_versions()
        assert versions["xlsxwriter"] == "?"
        assert versions["pandas"] != "?"

    def test_preserves_dependency_order(self):
        """Keys should match the order of _CORE_DEPENDENCIES."""
        versions = _collect_dependency_versions()
        assert list(versions.keys()) == list(_CORE_DEPENDENCIES)

    def test_non_package_not_found_error_returns_question_mark(self):
        """Non-PackageNotFoundError exceptions should map to '?' (not propagate)."""

        def metadata_bomb(name: str) -> str:
            raise ValueError(f"malformed metadata for {name}")

        with patch("cja_auto_sdr.core.logging.importlib.metadata.version", side_effect=metadata_bomb):
            versions = _collect_dependency_versions()
        for pkg in _CORE_DEPENDENCIES:
            assert versions[pkg] == "?", f"{pkg} should be '?' on ValueError"

    def test_oserror_during_metadata_lookup_returns_question_mark(self):
        """OSError (e.g. corrupt dist-info) should be caught and map to '?'."""

        def corrupt_metadata(name: str) -> str:
            raise OSError(f"cannot read metadata for {name}")

        with patch("cja_auto_sdr.core.logging.importlib.metadata.version", side_effect=corrupt_metadata):
            versions = _collect_dependency_versions()
        for pkg in _CORE_DEPENDENCIES:
            assert versions[pkg] == "?"

    def test_mixed_exception_types_only_affect_failing_packages(self):
        """Different exception types per package should each be caught individually."""
        import importlib.metadata

        real_version = importlib.metadata.version

        def mixed_failures(name: str) -> str:
            if name == "cjapy":
                raise ValueError("bad metadata")
            if name == "tqdm":
                raise OSError("cannot read")
            if name == "xlsxwriter":
                raise importlib.metadata.PackageNotFoundError(name)
            return real_version(name)

        with patch("cja_auto_sdr.core.logging.importlib.metadata.version", side_effect=mixed_failures):
            versions = _collect_dependency_versions()
        assert versions["cjapy"] == "?"
        assert versions["tqdm"] == "?"
        assert versions["xlsxwriter"] == "?"
        assert versions["pandas"] != "?"
        assert versions["numpy"] != "?"

    def test_startup_log_contains_dependency_line(self, capsys):
        """setup_logging should emit a 'Dependencies:' INFO line."""
        from cja_auto_sdr.core.logging import setup_logging

        setup_logging("test_dv", batch_mode=False, log_level="INFO")
        captured = capsys.readouterr().out

        dep_lines = [line for line in captured.splitlines() if "Dependencies:" in line]
        assert len(dep_lines) == 1
        msg = dep_lines[0]
        # Should mention every core dependency
        for pkg in _CORE_DEPENDENCIES:
            assert f"{pkg}=" in msg

    def test_startup_log_json_includes_dependency_versions(self, capsys):
        """JSON log format should include dependency_versions as a structured field."""
        import json as _json

        from cja_auto_sdr.core.logging import setup_logging

        setup_logging("test_dv", batch_mode=False, log_level="INFO", log_format="json")
        captured = capsys.readouterr().out

        dep_entries = []
        for line in captured.splitlines():
            try:
                entry = _json.loads(line)
            except _json.JSONDecodeError:
                continue
            if "Dependencies:" in entry.get("message", ""):
                dep_entries.append(entry)

        assert len(dep_entries) == 1
        dep_field = dep_entries[0].get("dependency_versions")
        assert isinstance(dep_field, dict)
        assert set(dep_field.keys()) == set(_CORE_DEPENDENCIES)

    def test_startup_logging_skips_dependency_lookup_when_info_disabled(self):
        """setup_logging should avoid dependency lookup work when INFO logs are disabled."""
        from cja_auto_sdr.core.logging import setup_logging

        _cached_startup_dependency_versions.cache_clear()
        try:
            with patch(
                "cja_auto_sdr.core.logging._collect_dependency_versions",
                side_effect=AssertionError("dependency lookup should not run"),
            ):
                setup_logging("test_dv", batch_mode=False, log_level="WARNING")
        finally:
            _cached_startup_dependency_versions.cache_clear()

    def test_startup_logging_reuses_cached_dependency_lookup_across_invocations(self):
        """Repeated setup_logging(INFO) calls should reuse cached startup dependency versions."""
        from cja_auto_sdr.core.logging import setup_logging

        _cached_startup_dependency_versions.cache_clear()
        call_count = {"count": 0}

        def _fake_collect() -> dict[str, str]:
            call_count["count"] += 1
            return {pkg: f"v{index}" for index, pkg in enumerate(_CORE_DEPENDENCIES)}

        try:
            with patch("cja_auto_sdr.core.logging._collect_dependency_versions", side_effect=_fake_collect):
                setup_logging("test_dv_1", batch_mode=False, log_level="INFO")
                setup_logging("test_dv_2", batch_mode=False, log_level="INFO")
        finally:
            _cached_startup_dependency_versions.cache_clear()

        assert call_count["count"] == 1

    def test_startup_logging_dependency_lookup_failure_falls_back_to_unknown(self, capsys):
        """Unexpected startup dependency lookup errors should not break logging setup."""
        from cja_auto_sdr.core.logging import setup_logging

        _cached_startup_dependency_versions.cache_clear()
        try:
            with patch(
                "cja_auto_sdr.core.logging._startup_dependency_versions_for_logging",
                side_effect=RuntimeError("metadata backend unavailable"),
            ):
                setup_logging("test_dv", batch_mode=False, log_level="INFO")
        finally:
            _cached_startup_dependency_versions.cache_clear()

        captured = capsys.readouterr().out
        dep_lines = [line for line in captured.splitlines() if "Dependencies:" in line]
        assert len(dep_lines) == 1
        dep_line = dep_lines[0]
        for pkg in _CORE_DEPENDENCIES:
            assert f"{pkg}=?" in dep_line
