"""Logging helpers for CJA Auto SDR."""

import atexit
import contextlib
import importlib.metadata
import json
import logging
import os
import re
import sys
from datetime import UTC, datetime
from functools import lru_cache
from logging.handlers import RotatingFileHandler
from pathlib import Path

from cja_auto_sdr.core.constants import LOG_FILE_BACKUP_COUNT, LOG_FILE_MAX_BYTES
from cja_auto_sdr.core.error_policies import RECOVERABLE_BEST_EFFORT_EXCEPTIONS
from cja_auto_sdr.core.version import __version__

_LOG_RECORD_RESERVED_FIELDS = set(logging.makeLogRecord({}).__dict__.keys()) | {"message", "asctime", "extra_fields"}
_REDACTION_FLAG_ATTR = "_cja_redacted"
_REDACTION_MARKER = object()
_REDACTION_EXCEPTION_ATTR = "_cja_redacted_exception"
_SENSITIVE_FIELD_NAMES = {
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
}
_SENSITIVE_COMPACT_FIELD_NAMES = {
    "password",
    "passwd",
    "pwd",
    "secret",
    "clientsecret",
    "token",
    "accesstoken",
    "refreshtoken",
    "bearertoken",
    "apikey",
    "authorization",
    "authheader",
    "privatekey",
}
_REDACTED_VALUE = "[REDACTED]"
_LOG_MESSAGE_FORMAT_ERROR = "[log-message-format-error]"
_LOG_REDACTION_ERROR = "[log-redaction-error]"
_LOG_FORMAT_ERROR = "[log-format-error]"
_SENSITIVE_KEY_REGEX = (
    r"client[_-]?secret|access[_-]?token|refresh[_-]?token|bearer[_-]?token|api[_-]?key|apikey|"
    r"auth[_-]?header|private[_-]?key|password|passwd|pwd|secret|token"
)
_MESSAGE_VALUE_REGEX = r"""
(?:
    "(?:[^"\\]|\\.)*" |
    '(?:[^'\\]|\\.)*' |
    [^,\s;}]+
)
"""
_AUTHORIZATION_KEY_REGEX = r"""(?:"authorization"|'authorization'|authorization)"""
_AUTHORIZATION_SCHEME_PATTERN = re.compile(
    rf"""(?ix)
    (?P<key>{_AUTHORIZATION_KEY_REGEX})
    (?P<separator>\s*[:=]\s*)
    (?P<value_quote>["']?)
    (?P<scheme>[A-Za-z]+)\s+(?P<credential>[A-Za-z0-9._~+/=-]+)
    (?P=value_quote)
    """,
)
_AUTHORIZATION_VALUE_PATTERN = re.compile(
    rf"""(?ix)
    (?P<key>{_AUTHORIZATION_KEY_REGEX})
    (?P<separator>\s*[:=]\s*)
    (?!["']?[A-Za-z]+\s+[A-Za-z0-9._~+/=\-\[\]]+["']?)
    (?P<value>{_MESSAGE_VALUE_REGEX})
    """,
)
_GENERIC_BEARER_PATTERN = re.compile(r"(?i)\b(bearer)\s+([A-Za-z0-9._~+/=-]+)")
_SENSITIVE_QUOTED_KEY_VALUE_PATTERN = re.compile(
    rf"""(?ix)
    (?P<full_key>["'](?:{_SENSITIVE_KEY_REGEX})["'])
    (?P<separator>\s*[:=]\s*)
    (?P<value>{_MESSAGE_VALUE_REGEX})
    """,
)
_SENSITIVE_UNQUOTED_KEY_VALUE_PATTERN = re.compile(
    rf"""(?ix)
    (?P<full_key>(?<![A-Za-z0-9_])(?:{_SENSITIVE_KEY_REGEX})(?![A-Za-z0-9_]))
    (?P<separator>\s*[:=]\s*)
    (?P<value>{_MESSAGE_VALUE_REGEX})
    """,
)

# Intentional: logging sanitization is a best-effort boundary and must not abort CLI execution.
RECOVERABLE_LOGGING_BOUNDARY_EXCEPTIONS: tuple[type[Exception], ...] = RECOVERABLE_BEST_EFFORT_EXCEPTIONS


def _normalize_field_name(name: str) -> str:
    separated = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name.strip())
    separated = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", separated)
    return re.sub(r"[^a-z0-9]+", "_", separated.lower()).strip("_")


def _safe_str(value: object) -> str:
    try:
        return str(value)
    except RECOVERABLE_LOGGING_BOUNDARY_EXCEPTIONS:
        return "<unprintable>"


def _safe_record_message(record: logging.LogRecord) -> str:
    try:
        return record.getMessage()
    except RECOVERABLE_LOGGING_BOUNDARY_EXCEPTIONS:
        # Keep logging resilient when message formatting fails (bad placeholders or broken __str__).
        return f"{_safe_str(getattr(record, 'msg', ''))} {_LOG_MESSAGE_FORMAT_ERROR}"


def _is_record_redacted(record: logging.LogRecord) -> bool:
    return record.__dict__.get(_REDACTION_FLAG_ATTR) is _REDACTION_MARKER


def _mark_record_redacted(record: logging.LogRecord) -> None:
    record.__dict__[_REDACTION_FLAG_ATTR] = _REDACTION_MARKER


def _safe_format_exception(exc_info: object) -> str:
    try:
        if isinstance(exc_info, tuple) and len(exc_info) == 3:
            return logging.Formatter().formatException(exc_info)
    except RECOVERABLE_LOGGING_BOUNDARY_EXCEPTIONS:
        return "<exception-format-error>"
    return "<exception-unavailable>"


def _mark_record_exception_redacted(record: logging.LogRecord, exception_text: str) -> None:
    record.__dict__[_REDACTION_EXCEPTION_ATTR] = (_REDACTION_MARKER, exception_text)
    # Standard formatters append exc_text when present, preventing raw exc_info rendering.
    record.exc_text = exception_text


def _get_marked_exception_text(record: logging.LogRecord) -> str | None:
    payload = record.__dict__.get(_REDACTION_EXCEPTION_ATTR)
    if isinstance(payload, tuple) and len(payload) == 2 and payload[0] is _REDACTION_MARKER:
        return payload[1] if isinstance(payload[1], str) else _safe_str(payload[1])
    return None


def _is_reserved_or_private_record_key(key: object) -> bool:
    if not isinstance(key, str):
        return True
    return key in _LOG_RECORD_RESERVED_FIELDS or key.startswith("_")


def _is_sensitive_field(name: str) -> bool:
    normalized = _normalize_field_name(name)
    if not normalized:
        return False
    if normalized in _SENSITIVE_FIELD_NAMES:
        return True
    compact = normalized.replace("_", "")
    if compact in _SENSITIVE_COMPACT_FIELD_NAMES:
        return True

    parts = [part for part in normalized.split("_") if part]
    if not parts:  # pragma: no cover — unreachable; non-empty normalized always has parts
        return False

    if "password" in parts or "passwd" in parts or "pwd" in parts:
        return True
    if "secret" in parts or "token" in parts:
        return True
    if "authorization" in parts:
        return True
    return (
        parts[-2:] == ["auth", "header"]
        or parts[-2:] == ["api", "key"]
        or parts[-2:] == ["private", "key"]
        or parts[-1] == "apikey"
        or compact.endswith(("token", "secret", "password", "passwd", "apikey", "authheader", "privatekey"))
    )


def _redact_bearer_match(match: re.Match[str]) -> str:
    return f"{match.group(1)} {_REDACTED_VALUE}"


def _redact_captured_value(value: str) -> str:
    if len(value) >= 2 and value[0] in {"'", '"'} and value[-1] == value[0]:
        return f"{value[0]}{_REDACTED_VALUE}{value[0]}"
    return _REDACTED_VALUE


def _redact_authorization_scheme_match(match: re.Match[str]) -> str:
    quoted_value = f"{match.group('scheme')} {_REDACTED_VALUE}"
    value_quote = match.group("value_quote")
    if value_quote:
        quoted_value = f"{value_quote}{quoted_value}{value_quote}"
    return f"{match.group('key')}{match.group('separator')}{quoted_value}"


def _redact_authorization_value_match(match: re.Match[str]) -> str:
    return f"{match.group('key')}{match.group('separator')}{_redact_captured_value(match.group('value'))}"


def _redact_key_value_match(match: re.Match[str]) -> str:
    return f"{match.group('full_key')}{match.group('separator')}{_redact_captured_value(match.group('value'))}"


def _redact_message(message: str) -> str:
    redacted = _AUTHORIZATION_SCHEME_PATTERN.sub(_redact_authorization_scheme_match, message)
    redacted = _AUTHORIZATION_VALUE_PATTERN.sub(_redact_authorization_value_match, redacted)
    redacted = _SENSITIVE_QUOTED_KEY_VALUE_PATTERN.sub(_redact_key_value_match, redacted)
    redacted = _SENSITIVE_UNQUOTED_KEY_VALUE_PATTERN.sub(_redact_key_value_match, redacted)
    return _GENERIC_BEARER_PATTERN.sub(_redact_bearer_match, redacted)


def _redact_value(value: object) -> object:
    if isinstance(value, dict):
        redacted_dict: dict[object, object] = {}
        for key, item in value.items():
            if _is_sensitive_field(_safe_str(key)):
                redacted_dict[key] = _REDACTED_VALUE
            else:
                redacted_dict[key] = _redact_value(item)
        return redacted_dict
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_value(item) for item in value)
    if isinstance(value, str):
        return _redact_message(value)
    return value


def _redact_extra_fields(extra_fields: dict[str, object]) -> dict[str, object]:
    redacted: dict[str, object] = {}
    for key, value in extra_fields.items():
        if _is_sensitive_field(_safe_str(key)):
            redacted[key] = _REDACTED_VALUE
        else:
            redacted[key] = _redact_value(value)
    return redacted


def _safe_redact_message(message: str) -> str:
    try:
        return _redact_message(message)
    except RECOVERABLE_LOGGING_BOUNDARY_EXCEPTIONS:
        return _LOG_REDACTION_ERROR


def _safe_redact_value(value: object, fallback: object = _LOG_REDACTION_ERROR) -> object:
    try:
        return _redact_value(value)
    except RECOVERABLE_LOGGING_BOUNDARY_EXCEPTIONS:
        return fallback


def _safe_redact_extra_fields(extra_fields: dict[str, object]) -> dict[str, object]:
    try:
        return _redact_extra_fields(extra_fields)
    except RECOVERABLE_LOGGING_BOUNDARY_EXCEPTIONS:
        return {
            key: _REDACTED_VALUE if _is_sensitive_field(_safe_str(key)) else _LOG_REDACTION_ERROR
            for key in extra_fields
        }


def _normalize_json_extra_fields(extra_fields: dict[object, object]) -> dict[str, object]:
    normalized: dict[str, object] = {}
    for key, value in extra_fields.items():
        normalized[_safe_str(key)] = value
    return normalized


def _json_formatter_fallback_entry(record: logging.LogRecord) -> dict[str, object]:
    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "level": _safe_str(getattr(record, "levelname", "ERROR")),
        "logger": _safe_str(getattr(record, "name", __name__)),
        "message": _LOG_FORMAT_ERROR,
    }


def _safe_json_dumps(payload: dict[str, object]) -> str:
    try:
        return json.dumps(payload, default=_safe_str)
    except RECOVERABLE_LOGGING_BOUNDARY_EXCEPTIONS:
        return json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": "ERROR",
                "logger": __name__,
                "message": _LOG_FORMAT_ERROR,
            },
        )


class SensitiveDataFilter(logging.Filter):
    """Best-effort redaction for sensitive values in log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        if _is_record_redacted(record):
            return True

        try:
            record.msg = _safe_redact_message(_safe_record_message(record))
            record.args = ()

            if record.exc_info:
                exception_text = _safe_redact_message(_safe_format_exception(record.exc_info))
                _mark_record_exception_redacted(record, exception_text)

            record_extra_fields = getattr(record, "extra_fields", None)
            if isinstance(record_extra_fields, dict):
                record.extra_fields = _safe_redact_extra_fields(record_extra_fields)

            for key, value in list(record.__dict__.items()):
                if _is_reserved_or_private_record_key(key):
                    continue
                key_name = _safe_str(key)
                if _is_sensitive_field(key_name):
                    record.__dict__[key] = _REDACTED_VALUE
                    continue
                record.__dict__[key] = _safe_redact_value(value)
            _mark_record_redacted(record)
        except RECOVERABLE_LOGGING_BOUNDARY_EXCEPTIONS:
            with contextlib.suppress(*RECOVERABLE_LOGGING_BOUNDARY_EXCEPTIONS):
                record.msg = _LOG_REDACTION_ERROR
                record.args = ()
                _mark_record_redacted(record)
        return True


class JSONFormatter(logging.Formatter):
    """
    JSON formatter for structured logging output.

    Produces JSON lines suitable for log aggregation systems (Splunk, ELK, CloudWatch).
    Each log record is a single JSON object on one line.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        try:
            already_redacted = _is_record_redacted(record)
            message = _safe_record_message(record)
            if not already_redacted:
                message = _safe_redact_message(message)
            exception_text = _get_marked_exception_text(record)

            log_entry = {
                "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
                "level": record.levelname,
                "logger": record.name,
                "message": message,
                "module": record.module,
                "function": record.funcName,
                "line": record.lineno,
                "process": record.process,
                "process_name": record.processName,
                "thread": record.thread,
                "thread_name": record.threadName,
            }

            # Add exception info if present
            if record.exc_info:
                if exception_text is None:
                    exception_text = _safe_redact_message(_safe_format_exception(record.exc_info))
                    if already_redacted:
                        _mark_record_exception_redacted(record, exception_text)
                log_entry["exception"] = exception_text

            # Add any explicit extra fields passed to the logger.
            extra_fields: dict[object, object] = {}
            record_extra_fields = getattr(record, "extra_fields", None)
            if isinstance(record_extra_fields, dict):
                extra_fields.update(record_extra_fields)

            # Also include custom LogRecord attributes set via logging's `extra`.
            for key, value in record.__dict__.items():
                if _is_reserved_or_private_record_key(key):
                    continue
                extra_fields.setdefault(key, value)

            if extra_fields:
                normalized_extra_fields = _normalize_json_extra_fields(extra_fields)
                if already_redacted:
                    log_entry.update(normalized_extra_fields)
                else:
                    log_entry.update(_safe_redact_extra_fields(normalized_extra_fields))

            return _safe_json_dumps(log_entry)
        except RECOVERABLE_LOGGING_BOUNDARY_EXCEPTIONS:
            return _safe_json_dumps(_json_formatter_fallback_entry(record))


# Module-level tracking to prevent duplicate logger initialization
_logging_initialized = False
_current_log_file = None
_atexit_registered = False


class ContextLoggerAdapter(logging.LoggerAdapter):
    """LoggerAdapter that merges contextual fields into record extras."""

    def process(self, msg: str, kwargs: dict) -> tuple[str, dict]:
        extra = kwargs.get("extra")
        merged_extra = dict(self.extra)
        if isinstance(extra, dict):
            merged_extra.update(extra)
        kwargs["extra"] = merged_extra
        return msg, kwargs

    def emit_diagnostic(self, event: str, category: str, **fields: object) -> None:
        """Emit a structured diagnostic event through this adapter."""
        emit_diagnostic(self, event, category, **fields)


def _format_diagnostic_text_value(value: object) -> str:
    """Format a single diagnostic field value for text mode output."""
    if isinstance(value, (dict, list)):
        try:
            return json.dumps(value, separators=(",", ":"), default=_safe_str)
        except RECOVERABLE_LOGGING_BOUNDARY_EXCEPTIONS:
            return _safe_str(value)
    return _safe_str(value)


def emit_diagnostic(
    logger: logging.Logger | logging.LoggerAdapter,
    event: str,
    category: str,
    **fields: object,
) -> None:
    """Emit a structured diagnostic event at INFO level.

    In text mode the message is formatted as ``[DIAG] {event}: key=value, ...``.
    In JSON mode ``event``, ``event_category``, and *fields* are merged into
    the JSON log record via the ``extra`` dict.

    The call respects the effective log level and ``--quiet`` behaviour: if
    ``INFO`` is suppressed, diagnostic events are also suppressed.
    """
    extra: dict[str, object] = {"event": event, "event_category": category, **fields}

    # Build human-readable text representation.
    kv_parts = [f"{k}={_format_diagnostic_text_value(v)}" for k, v in fields.items()]
    text_suffix = f": {', '.join(kv_parts)}" if kv_parts else ""
    message = f"[DIAG] {event}{text_suffix}"

    logger.info(message, extra=extra)


def _unwrap_logger(logger: logging.Logger | logging.LoggerAdapter | None) -> logging.Logger | None:
    current = logger
    while isinstance(current, logging.LoggerAdapter):
        current = current.logger
    if isinstance(current, logging.Logger):
        return current
    return None


def with_log_context(
    logger: logging.Logger | logging.LoggerAdapter | object,
    **context: object,
) -> logging.Logger | logging.LoggerAdapter | object:
    """Return a logger enriched with persistent contextual fields."""
    if not isinstance(logger, (logging.Logger, logging.LoggerAdapter)):
        # Preserve test doubles/mocks that may not satisfy logging interfaces.
        return logger

    base_logger = _unwrap_logger(logger)
    if base_logger is None:
        return logger

    normalized_context = {k: v for k, v in context.items() if v is not None}
    existing_context = {}
    if isinstance(logger, logging.LoggerAdapter):
        existing_context = dict(getattr(logger, "extra", {}))

    existing_context.update(normalized_context)
    return ContextLoggerAdapter(base_logger, existing_context)


def flush_logging_handlers(logger: logging.Logger | logging.LoggerAdapter | None = None) -> None:
    """Flush logger handlers, including propagated root handlers."""
    handlers: list[logging.Handler] = []
    seen: set[int] = set()

    unwrapped_logger = _unwrap_logger(logger)

    if unwrapped_logger is not None:
        current: logging.Logger | None = unwrapped_logger
        while current is not None:
            handlers.extend(current.handlers)
            if not current.propagate:
                break
            current = current.parent

    if not handlers:
        handlers.extend(logging.root.handlers)

    for handler in handlers:
        handler_id = id(handler)
        if handler_id in seen:
            continue
        seen.add(handler_id)
        with contextlib.suppress(Exception):
            handler.flush()


_CORE_DEPENDENCIES = ("cjapy", "pandas", "numpy", "xlsxwriter", "tqdm")


def _collect_dependency_versions() -> dict[str, str]:
    """Return a mapping of core dependency names to their installed versions.

    Falls back to ``"?"`` for any package that cannot be found.
    """
    versions: dict[str, str] = {}
    for pkg in _CORE_DEPENDENCIES:
        try:
            versions[pkg] = importlib.metadata.version(pkg)
        except Exception:  # Intentional: metadata backends can raise heterogeneous parse/IO errors.
            versions[pkg] = "?"
    return versions


@lru_cache(maxsize=1)
def _cached_startup_dependency_versions() -> tuple[tuple[str, str], ...]:
    """Cache dependency versions used by startup logging across setup calls."""
    return tuple(_collect_dependency_versions().items())


def _startup_dependency_versions_for_logging() -> dict[str, str]:
    """Return startup dependency versions as a fresh dict copy."""
    return dict(_cached_startup_dependency_versions())


def _infer_run_mode(data_view_id: str | None, batch_mode: bool) -> str:
    """Infer the run mode from setup_logging parameters."""
    if batch_mode:
        return "batch"
    if data_view_id:
        return "single"
    return "discovery"


def setup_logging(
    data_view_id: str | None = None,
    batch_mode: bool = False,
    log_level: str | None = None,
    log_format: str = "text",
) -> logging.Logger:
    """Setup logging to both file and console.

    Args:
        data_view_id: Data view ID for log file naming
        batch_mode: Whether running in batch mode
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_format: Output format - "text" (default) or "json" for structured logging

    Returns:
        Configured logger instance

    Priority: 1) Passed parameter, 2) Environment variable LOG_LEVEL, 3) Default INFO
    """
    global _logging_initialized, _current_log_file, _atexit_registered

    # Register atexit handler once to ensure logs are flushed on exit
    if not _atexit_registered:
        atexit.register(logging.shutdown)
        _atexit_registered = True

    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    try:
        log_dir.mkdir(exist_ok=True)
    except PermissionError:
        print("Warning: Cannot create logs directory (permission denied). Logging to console only.", file=sys.stderr)
        log_dir = None
    except OSError as e:
        print(f"Warning: Cannot create logs directory: {e}. Logging to console only.", file=sys.stderr)
        log_dir = None

    # Create log filename with timestamp
    timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

    if log_dir is not None:
        if batch_mode:
            log_file = log_dir / f"SDR_Batch_Generation_{timestamp}.log"
        else:
            log_file = log_dir / f"SDR_Generation_{data_view_id}_{timestamp}.log"
    else:
        log_file = None

    # Determine log level with priority: parameter > env var > default
    if log_level is None:
        log_level = os.environ.get("LOG_LEVEL", "INFO")

    # Validate log level
    valid_levels = ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
    if log_level.upper() not in valid_levels:
        print(f"Warning: Invalid log level '{log_level}', using INFO", file=sys.stderr)
        log_level = "INFO"

    # Get numeric log level
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Clear any existing handlers from root logger
    for handler in logging.root.handlers[:]:
        handler.close()
        logging.root.removeHandler(handler)

    # Configure logging handlers
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file is not None:
        # Use RotatingFileHandler to prevent unbounded log growth
        handlers.append(RotatingFileHandler(log_file, maxBytes=LOG_FILE_MAX_BYTES, backupCount=LOG_FILE_BACKUP_COUNT))

    # Select formatter based on log_format
    if log_format.lower() == "json":
        formatter = JSONFormatter()
    else:
        formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")

    # Apply formatter and level to all handlers, then add to root logger
    for handler in handlers:
        handler.setFormatter(formatter)
        handler.setLevel(numeric_level)
        handler.addFilter(SensitiveDataFilter())
        logging.root.addHandler(handler)

    # Set root logger level explicitly
    logging.root.setLevel(numeric_level)

    # Get the module logger
    logger = logging.getLogger("cja_auto_sdr.generator")
    # Ensure it propagates to root and doesn't have its own restrictive level
    logger.propagate = True
    logger.setLevel(logging.NOTSET)

    # Track initialization state to prevent duplicates
    _logging_initialized = True
    _current_log_file = log_file

    if logger.isEnabledFor(logging.INFO):
        if log_file is not None:
            logger.info(f"Logging initialized. Log file: {log_file}")
        else:
            logger.info("Logging initialized. Console output only.")
        logger.info(f"CJA SDR Generator version: {__version__}", extra={"sdr_version": __version__})
        logger.info(
            f"Python {sys.version.split()[0]} on {sys.platform}",
            extra={"python_version": sys.version.split()[0], "platform": sys.platform},
        )
        try:
            dep_versions = _startup_dependency_versions_for_logging()
        except Exception:  # Intentional: Multiple metadata backends can raise heterogeneous parse/IO errors
            dep_versions = dict.fromkeys(_CORE_DEPENDENCIES, "?")
            logger.debug("Failed to resolve dependency versions for startup logging", exc_info=True)
        dep_summary = ", ".join(f"{pkg}={ver}" for pkg, ver in dep_versions.items())
        logger.info(f"Dependencies: {dep_summary}", extra={"dependency_versions": dep_versions})
        logger.info(f"Log level: {log_level.upper()}", extra={"log_level": log_level.upper()})
        logger.info(f"Run mode: {_infer_run_mode(data_view_id, batch_mode)}")

    # Flush handlers to ensure log file is not empty even on early exit
    for handler in logging.root.handlers:
        handler.flush()

    return logger
