"""Tests for the structured diagnostic event vocabulary.

Validates emit_diagnostic() in text and JSON modes, ContextLoggerAdapter
integration, extra-field merging, and redaction of sensitive nested values.
"""

import io
import json
import logging

from cja_auto_sdr.core.logging import (
    ContextLoggerAdapter,
    JSONFormatter,
    SensitiveDataFilter,
    _format_diagnostic_text_value,
    emit_diagnostic,
    with_log_context,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _make_logger(handler: logging.Handler, level: int = logging.DEBUG) -> logging.Logger:
    """Create a disposable logger wired to the given handler."""
    logger = logging.getLogger(f"test.diag.{id(handler)}")
    logger.setLevel(level)
    logger.addHandler(handler)
    return logger


def _text_handler(stream) -> logging.Handler:
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    handler.addFilter(SensitiveDataFilter())
    return handler


def _json_handler(stream) -> logging.Handler:
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JSONFormatter())
    handler.addFilter(SensitiveDataFilter())
    return handler


# ---------------------------------------------------------------------------
# _format_diagnostic_text_value
# ---------------------------------------------------------------------------
class TestFormatDiagnosticTextValue:
    def test_string(self):
        assert _format_diagnostic_text_value("hello") == "hello"

    def test_int(self):
        assert _format_diagnostic_text_value(42) == "42"

    def test_dict_compact_json(self):
        result = _format_diagnostic_text_value({"a": 1, "b": 2})
        parsed = json.loads(result)
        assert parsed == {"a": 1, "b": 2}
        # Compact: no spaces after separators
        assert " " not in result

    def test_list_compact_json(self):
        result = _format_diagnostic_text_value([1, 2, 3])
        assert result == "[1,2,3]"

    def test_nested_structure(self):
        result = _format_diagnostic_text_value({"x": [1, {"y": 2}]})
        parsed = json.loads(result)
        assert parsed == {"x": [1, {"y": 2}]}


# ---------------------------------------------------------------------------
# emit_diagnostic — text mode
# ---------------------------------------------------------------------------
class TestEmitDiagnosticText:
    def test_basic_event(self):
        buf = io.StringIO()
        logger = _make_logger(_text_handler(buf))
        emit_diagnostic(logger, "test_event", "test_cat", key1="val1", key2=42)
        output = buf.getvalue().strip()
        assert output.startswith("[DIAG] test_event:")
        assert "key1=val1" in output
        assert "key2=42" in output

    def test_no_fields(self):
        buf = io.StringIO()
        logger = _make_logger(_text_handler(buf))
        emit_diagnostic(logger, "simple_event", "cat")
        output = buf.getvalue().strip()
        assert output == "[DIAG] simple_event"

    def test_nested_dict_field_is_compact_json(self):
        buf = io.StringIO()
        logger = _make_logger(_text_handler(buf))
        emit_diagnostic(logger, "ev", "cat", data={"a": 1})
        output = buf.getvalue().strip()
        assert 'data={"a":1}' in output

    def test_nested_list_field_is_compact_json(self):
        buf = io.StringIO()
        logger = _make_logger(_text_handler(buf))
        emit_diagnostic(logger, "ev", "cat", items=[1, 2])
        output = buf.getvalue().strip()
        assert "items=[1,2]" in output


# ---------------------------------------------------------------------------
# emit_diagnostic — JSON mode
# ---------------------------------------------------------------------------
class TestEmitDiagnosticJSON:
    def test_json_fields_merged(self):
        buf = io.StringIO()
        logger = _make_logger(_json_handler(buf))
        emit_diagnostic(logger, "test_event", "resilience", from_state="closed", to_state="open")
        record = json.loads(buf.getvalue().strip())
        assert record["event"] == "test_event"
        assert record["event_category"] == "resilience"
        assert record["from_state"] == "closed"
        assert record["to_state"] == "open"
        # The text message is also present
        assert "[DIAG]" in record["message"]

    def test_json_no_extra_fields(self):
        buf = io.StringIO()
        logger = _make_logger(_json_handler(buf))
        emit_diagnostic(logger, "ping", "health")
        record = json.loads(buf.getvalue().strip())
        assert record["event"] == "ping"
        assert record["event_category"] == "health"


# ---------------------------------------------------------------------------
# ContextLoggerAdapter.emit_diagnostic
# ---------------------------------------------------------------------------
class TestContextLoggerAdapterEmitDiagnostic:
    def test_adapter_emits_diagnostic(self):
        buf = io.StringIO()
        base = _make_logger(_text_handler(buf))
        adapter = ContextLoggerAdapter(base, {"run_id": "abc123"})
        adapter.emit_diagnostic("lock_acquired", "lifecycle", lock_path="/tmp/x")
        output = buf.getvalue().strip()
        assert "[DIAG] lock_acquired:" in output
        assert "lock_path=/tmp/x" in output

    def test_adapter_merges_context_in_json(self):
        buf = io.StringIO()
        base = _make_logger(_json_handler(buf))
        adapter = ContextLoggerAdapter(base, {"run_id": "abc123"})
        adapter.emit_diagnostic("ev", "cat", key="val")
        record = json.loads(buf.getvalue().strip())
        assert record["event"] == "ev"
        assert record["run_id"] == "abc123"
        assert record["key"] == "val"

    def test_with_log_context_adapter(self):
        buf = io.StringIO()
        base = _make_logger(_json_handler(buf))
        ctx_logger = with_log_context(base, batch_id="b1")
        assert isinstance(ctx_logger, ContextLoggerAdapter)
        ctx_logger.emit_diagnostic("test_ev", "cat", x=1)
        record = json.loads(buf.getvalue().strip())
        assert record["batch_id"] == "b1"
        assert record["event"] == "test_ev"


# ---------------------------------------------------------------------------
# Redaction of sensitive nested values
# ---------------------------------------------------------------------------
class TestDiagnosticRedaction:
    def test_sensitive_field_redacted_in_text(self):
        buf = io.StringIO()
        logger = _make_logger(_text_handler(buf))
        emit_diagnostic(logger, "ev", "cat", api_key="secret123")
        output = buf.getvalue().strip()
        assert "secret123" not in output
        assert "[REDACTED]" in output

    def test_sensitive_nested_dict_redacted_in_json(self):
        buf = io.StringIO()
        logger = _make_logger(_json_handler(buf))
        emit_diagnostic(logger, "ev", "cat", config={"password": "hunter2", "host": "db.local"})
        record = json.loads(buf.getvalue().strip())
        config = record["config"]
        assert config["password"] == "[REDACTED]"
        assert config["host"] == "db.local"

    def test_sensitive_top_level_field_redacted_in_json(self):
        buf = io.StringIO()
        logger = _make_logger(_json_handler(buf))
        secret_val = "xyz"
        emit_diagnostic(logger, "ev", "cat", client_secret=secret_val)
        record = json.loads(buf.getvalue().strip())
        assert record["client_secret"] == "[REDACTED]"


# ---------------------------------------------------------------------------
# Effective log level / quiet suppression
# ---------------------------------------------------------------------------
class TestDiagnosticLogLevel:
    def test_suppressed_when_info_disabled(self):
        buf = io.StringIO()
        handler = _text_handler(buf)
        handler.setLevel(logging.WARNING)
        logger = _make_logger(handler, level=logging.WARNING)
        emit_diagnostic(logger, "should_not_appear", "cat", x=1)
        assert buf.getvalue() == ""

    def test_emitted_at_info(self):
        buf = io.StringIO()
        logger = _make_logger(_text_handler(buf), level=logging.INFO)
        emit_diagnostic(logger, "should_appear", "cat")
        assert "[DIAG] should_appear" in buf.getvalue()


# ---------------------------------------------------------------------------
# Works with plain Logger (not just Adapter)
# ---------------------------------------------------------------------------
class TestEmitDiagnosticPlainLogger:
    def test_plain_logger(self):
        buf = io.StringIO()
        logger = _make_logger(_json_handler(buf))
        emit_diagnostic(logger, "ev", "cat", key="val")
        record = json.loads(buf.getvalue().strip())
        assert record["event"] == "ev"
        assert record["key"] == "val"
