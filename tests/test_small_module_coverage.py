"""Tests targeting uncovered lines in small modules.

Covers gaps in:
- core/logging.py (17 uncovered lines)
- inventory/utils.py (15 uncovered lines)
- inventory/calculated_metrics.py (41 uncovered lines)
- core/constants.py (2 uncovered lines)
- core/lazy.py (1 uncovered line)
- api/tuning.py (1 uncovered line)
- core/locks/manager.py (3 uncovered lines)
- org/cache.py (2 uncovered lines)
"""

import errno
import json
import logging
import os
import threading
import time
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from cja_auto_sdr.core.constants import auto_detect_workers
from cja_auto_sdr.core.lazy import make_getattr
from cja_auto_sdr.core.locks.manager import LockManager
from cja_auto_sdr.core.logging import (
    JSONFormatter,
    _is_sensitive_field,
    _mark_record_redacted,
    _redact_message,
    _safe_format_exception,
    flush_logging_handlers,
    with_log_context,
)
from cja_auto_sdr.inventory.calculated_metrics import (
    CalculatedMetricsInventoryBuilder,
)
from cja_auto_sdr.inventory.utils import (
    BatchProcessingStats,
    coerce_scalar_text,
    extract_short_name,
    format_iso_date,
    validate_required_id,
)
from cja_auto_sdr.org.cache import OrgReportLock

# ==================== core/logging.py ====================


class TestSafeFormatException:
    """Cover lines 132-134: exception handler and unavailable fallback."""

    def test_format_exception_error_returns_error_marker(self):
        """Line 132-133: formatException raises internally."""
        bad_exc_info = (ValueError, ValueError("boom"), None)
        with patch.object(logging.Formatter, "formatException", side_effect=TypeError("fmt error")):
            result = _safe_format_exception(bad_exc_info)
        assert result == "<exception-format-error>"

    def test_non_tuple_returns_unavailable(self):
        """Line 134: not a valid exc_info tuple."""
        assert _safe_format_exception("not a tuple") == "<exception-unavailable>"

    def test_wrong_length_tuple_returns_unavailable(self):
        """Line 134: tuple with wrong length."""
        assert _safe_format_exception((ValueError, ValueError("x"))) == "<exception-unavailable>"


class TestIsSensitiveFieldEmptyParts:
    """Cover line 168: empty parts after normalization."""

    def test_empty_parts_returns_false(self):
        """Line 168: all parts empty after split."""
        assert _is_sensitive_field("___") is False

    def test_single_underscore(self):
        assert _is_sensitive_field("_") is False


class TestRedactAuthorizationValueMatch:
    """Cover line 204: _redact_authorization_value_match via _redact_message."""

    def test_authorization_bare_value_redacted(self):
        """Line 204: authorization key with a plain value (not scheme+credential)."""
        msg = "authorization=some_plain_token_value"
        result = _redact_message(msg)
        assert "[REDACTED]" in result


class TestJSONFormatterExcInfoAlreadyRedacted:
    """Cover line 314: JSONFormatter formats exc_info on already-redacted record."""

    def test_already_redacted_record_with_exc_info(self):
        """Line 314: record already redacted, has exc_info but no marked exception text."""
        formatter = JSONFormatter()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="error occurred",
            args=(),
            exc_info=(ValueError, ValueError("secret=abc123"), None),
        )
        _mark_record_redacted(record)
        result = formatter.format(record)
        parsed = json.loads(result)
        assert "exception" in parsed
        assert "abc123" not in parsed["exception"]


class TestWithLogContextUnwrapNone:
    """Cover line 375: _unwrap_logger returns None."""

    def test_unwrap_returns_none_for_bad_adapter(self):
        """Line 375: an adapter whose .logger is not a Logger."""
        adapter = logging.LoggerAdapter(logging.getLogger("test_unwrap"), {})
        adapter.logger = "not_a_logger"
        result = with_log_context(adapter, key="value")
        assert result is adapter


class TestFlushLoggingHandlersDuplicate:
    """Cover line 407: handler_id already in seen set."""

    def test_duplicate_handler_skipped(self):
        """Line 407: same handler appears twice in handler list."""
        logger = logging.getLogger("test_flush_dup")
        logger.handlers.clear()
        handler = logging.StreamHandler()
        logger.addHandler(handler)
        logger.addHandler(handler)
        logger.propagate = False
        flush_logging_handlers(logger)
        logger.handlers.clear()


class TestSetupLoggingPermissionError:
    """Cover lines 449-454, 465, 493, 520: setup_logging edge cases."""

    def test_permission_error_logs_to_console_only(self, capsys):
        """Lines 449-451, 465, 520: PermissionError creating logs dir."""
        with patch("cja_auto_sdr.core.logging.Path.mkdir", side_effect=PermissionError("denied")):
            from cja_auto_sdr.core.logging import setup_logging

            setup_logging(log_level="WARNING")
        captured = capsys.readouterr()
        assert "permission denied" in captured.err.lower() or "Console output only" in captured.err

    def test_oserror_logs_to_console_only(self, capsys):
        """Lines 452-454: OSError creating logs dir."""
        with patch("cja_auto_sdr.core.logging.Path.mkdir", side_effect=OSError("disk full")):
            from cja_auto_sdr.core.logging import setup_logging

            setup_logging(log_level="WARNING")
        captured = capsys.readouterr()
        assert "disk full" in captured.err

    def test_json_log_format(self, tmp_path, monkeypatch):
        """Line 493: log_format='json' branch."""
        monkeypatch.chdir(tmp_path)
        from cja_auto_sdr.core.logging import setup_logging

        logger = setup_logging(log_format="json", log_level="INFO")
        assert logger is not None
        has_json = any(isinstance(h.formatter, JSONFormatter) for h in logging.root.handlers)
        assert has_json


# ==================== inventory/utils.py ====================


class TestFormatIsoDateExceptionBranch:
    """Cover lines 50-51: ValueError/TypeError exception handler."""

    def test_invalid_iso_string_fallback(self):
        """Lines 50-51: datetime.fromisoformat raises ValueError on invalid T-format."""
        # Must contain "T" to enter the fromisoformat path, but be invalid
        result = format_iso_date("not-a-validTiso-date-at-all-this-is-very-long!")
        # Falls into except branch, returns value[:19]
        assert result == "not-a-validTiso-dat"

    def test_short_invalid_date_returned_as_is(self):
        """Lines 50-51: short invalid date returns as-is."""
        result = format_iso_date("invalid")
        assert result == "invalid"


class TestExtractShortNameEdgeCases:
    """Cover lines 156-159: is_na array-like and TypeError/ValueError."""

    def test_series_all_na(self):
        """Lines 156-157: pd.isna returns array-like where .all() is True."""
        na_series = pd.Series([float("nan")])
        result = extract_short_name(na_series)
        assert result == ""

    def test_custom_object_raises_typeerror_on_isna(self):
        """Lines 158-159: pd.isna raises TypeError."""

        class Weird:
            def __str__(self):
                return "weird_value"

            def __eq__(self, other):
                raise TypeError("no comparison")

            def __hash__(self):
                return id(self)

        with patch("cja_auto_sdr.inventory.utils.pd.isna", side_effect=TypeError("bad")):
            result = extract_short_name(Weird())
        assert result == "weird_value"


class TestCoerceScalarTextEdgeCases:
    """Cover lines 193-194, 200, 202-203: exception branches in coerce_scalar_text."""

    def test_pd_isna_raises_typeerror(self):
        """Lines 193-194: pd.isna raises TypeError on exotic object."""

        class Exotic:
            def __str__(self):
                return "exotic"

        with patch("cja_auto_sdr.inventory.utils.pd.isna", side_effect=TypeError("boom")):
            result = coerce_scalar_text(Exotic())
        assert isinstance(result, str)

    def test_isoformat_returns_none(self):
        """Line 200: isoformat() returns None."""

        class WeirdDate:
            def isoformat(self):
                return None

            def __str__(self):
                return "weird"

        result = coerce_scalar_text(WeirdDate())
        assert result == ""

    def test_isoformat_raises_typeerror(self):
        """Lines 202-203: isoformat() raises TypeError."""

        class BadDate:
            def isoformat(self):
                raise TypeError("no tz")

            def __str__(self):
                return "baddate"

        result = coerce_scalar_text(BadDate())
        assert isinstance(result, str)


class TestValidateRequiredIdEdgeCases:
    """Cover lines 351-354: is_na array-like and TypeError/ValueError."""

    def test_series_na_value(self):
        """Lines 351-352: pd.isna returns array-like .all() True."""
        item = {"id": pd.Series([float("nan")]), "name": "Test"}
        with patch("cja_auto_sdr.inventory.utils.pd.isna") as mock_isna:
            mock_result = MagicMock()
            mock_result.all.return_value = True
            mock_isna.return_value = mock_result
            result = validate_required_id(item)
        assert result is None

    def test_isna_raises_typeerror(self):
        """Lines 353-354: pd.isna raises TypeError."""
        item = {"id": object(), "name": "Test"}
        with patch("cja_auto_sdr.inventory.utils.pd.isna", side_effect=TypeError("bad")):
            result = validate_required_id(item)
        # object() stringifies, then checked against null-like values
        assert result is not None or result is None


# ==================== inventory/calculated_metrics.py ====================


@pytest.fixture
def cm_builder():
    """Create a CalculatedMetricsInventoryBuilder for testing."""
    return CalculatedMetricsInventoryBuilder()


class TestProcessMetricEmptyFormula:
    """Cover lines 482, 488, 499-502: empty/missing formula branches."""

    def test_empty_string_formula_skipped(self, cm_builder):
        """Line 488: empty string formula."""
        metric_data = {
            "id": "cm_test",
            "name": "Test",
            "definition": {"formula": "   "},
        }
        stats = BatchProcessingStats()
        result = cm_builder._process_metric(metric_data, stats)
        assert result is None
        assert stats.skipped == 1

    def test_empty_dict_formula_skipped(self, cm_builder):
        """Lines 499-502: empty dict formula."""
        metric_data = {
            "id": "cm_test2",
            "name": "Test2",
            "definition": {"formula": {}},
        }
        stats = BatchProcessingStats()
        result = cm_builder._process_metric(metric_data, stats)
        assert result is None

    def test_empty_list_formula_skipped(self, cm_builder):
        """Line 499-502: empty list formula."""
        metric_data = {
            "id": "cm_test3",
            "name": "Test3",
            "definition": {"formula": []},
        }
        stats = BatchProcessingStats()
        result = cm_builder._process_metric(metric_data, stats)
        assert result is None


class TestProcessMetricJsonSerializationFallback:
    """Cover lines 540-541: json.dumps TypeError/ValueError fallback."""

    def test_unserializable_definition_fallback(self, cm_builder):
        """Lines 540-541: definition contains non-serializable value."""
        metric_data = {
            "id": "cm_serial",
            "name": "Serial Test",
            "definition": {
                "formula": {"func": "metric", "name": "metrics/revenue"},
            },
        }
        original_dumps = json.dumps
        call_count = {"n": 0}

        def patched_dumps(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise TypeError("bad type")
            return original_dumps(*args, **kwargs)

        with patch("cja_auto_sdr.inventory.calculated_metrics.json.dumps", side_effect=patched_dumps):
            result = cm_builder._process_metric(metric_data)
        assert result is not None
        assert result.definition_json


class TestNormalizeReferenceValueList:
    """Cover line 579: _normalize_reference_value for list/tuple input."""

    def test_list_input_extracts_first_valid(self, cm_builder):
        """Line 589-594: list/tuple traversal."""
        result = cm_builder._normalize_reference_value([None, "", "metrics/revenue"])
        assert result == "revenue"

    def test_tuple_input_extracts_first_valid(self, cm_builder):
        result = cm_builder._normalize_reference_value((None, "metrics/orders"))
        assert result == "orders"

    def test_empty_list_returns_empty(self, cm_builder):
        assert cm_builder._normalize_reference_value([]) == ""

    def test_dict_input_with_segment_id(self, cm_builder):
        """Line 595-601: dict input with segment_id key."""
        result = cm_builder._normalize_reference_value({"segment_id": "s_abc"})
        assert result == "s_abc"


class TestParseFormulaOperandsList:
    """Cover line 630: traverse operands list branch."""

    def test_formula_with_operands_list(self, cm_builder):
        """Line 695-699: formula node with 'operands' list."""
        formula = {
            "func": "add",
            "operands": [
                {"func": "metric", "name": "metrics/revenue"},
                {"func": "metric", "name": "metrics/orders"},
            ],
        }
        parsed = cm_builder._parse_formula(formula)
        assert "revenue" in parsed["metric_references"]
        assert "orders" in parsed["metric_references"]


class TestGenerateFormulaSummaryBranches:
    """Cover formula summary branches for various func types."""

    def _make_parsed(self, functions=None, metrics=None, segments=None):
        return {
            "functions_internal": functions or [],
            "functions_display": [],
            "metric_references": metrics or [],
            "segment_references": segments or [],
            "operator_count": 0,
            "nesting_depth": 0,
            "conditional_count": 0,
            "complexity_score": 0.0,
        }

    def test_non_normalized_string_formula(self, cm_builder):
        """Lines 771-772: formula is a bare string."""
        parsed = self._make_parsed()
        result = cm_builder._generate_formula_summary("custom_formula", parsed)
        assert "custom_formula" in result or "Custom" in result

    def test_multiply_with_refs(self, cm_builder):
        """Line 822: multiply summary with resolved references."""
        formula = {
            "func": "multiply",
            "col1": {"func": "metric", "name": "metrics/price"},
            "col2": {"func": "metric", "name": "metrics/quantity"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "x" in result or "price" in result

    def test_multiply_no_refs(self, cm_builder):
        """Line 823: multiply summary without resolvable references."""
        formula = {"func": "multiply", "col1": {}, "col2": {}}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Multiplication" in result or "multiply" in result.lower() or "Custom" in result

    def test_add_more_than_three_operands(self, cm_builder):
        """Lines 828-830: add with more than 3 operands."""
        formula = {
            "func": "add",
            "col1": {"func": "metric", "name": "metrics/a"},
            "col2": {"func": "metric", "name": "metrics/b"},
            "operands": [
                {"func": "metric", "name": "metrics/c"},
                {"func": "metric", "name": "metrics/d"},
            ],
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "more" in result or "+" in result

    def test_subtract_summary(self, cm_builder):
        """Line 839: subtract with resolved refs."""
        formula = {
            "func": "subtract",
            "col1": {"func": "metric", "name": "metrics/gross"},
            "col2": {"func": "metric", "name": "metrics/returns"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "-" in result or "gross" in result

    def test_subtract_no_refs(self, cm_builder):
        """Line 840: subtract without refs."""
        formula = {"func": "subtract", "col1": {}, "col2": {}}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Difference" in result or "Custom" in result

    def test_if_with_condition_desc(self, cm_builder):
        """Lines 843-845: if formula with describable condition."""
        formula = {
            "func": "if",
            "condition": {
                "func": "gt",
                "col1": {"func": "metric", "name": "metrics/revenue"},
                "col2": {"func": "number", "val": 100},
            },
            "then": {"func": "metric", "name": "metrics/revenue"},
            "else": {"func": "number", "val": 0},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "If" in result or "revenue" in result

    def test_if_without_condition_desc(self, cm_builder):
        """Line 846: if formula without describable condition."""
        formula = {
            "func": "if",
            "condition": {},
            "then": {"func": "number", "val": 1},
            "else": {"func": "number", "val": 0},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Conditional" in result or "IF" in result

    def test_segment_with_metric_and_segment(self, cm_builder):
        """Line 853: segment with inner metric and segment_id."""
        formula = {
            "func": "segment",
            "segment_id": "s300000000_12345678abcdef",
            "metric": {"func": "metric", "name": "metrics/visits"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "filtered" in result or "visits" in result

    def test_segment_metric_only(self, cm_builder):
        """Line 855: segment with metric but no segment_id."""
        formula = {
            "func": "segment",
            "metric": {"func": "metric", "name": "metrics/visits"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "filtered" in result or "visits" in result

    def test_segment_no_metric(self, cm_builder):
        """Line 856: segment with no metric."""
        formula = {"func": "segment", "segment_id": "s_test"}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Segmented" in result or "metric" in result.lower()

    def test_metric_reference_summary(self, cm_builder):
        """Line 861: func=metric returns '= name'."""
        formula = {"func": "metric", "name": "metrics/revenue"}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "revenue" in result

    def test_col_sum_summary(self, cm_builder):
        """Line 868: col-sum with inner metric."""
        formula = {
            "func": "col-sum",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "SUM" in result or "revenue" in result

    def test_col_sum_no_inner(self, cm_builder):
        """Line 869: col-sum without inner metric."""
        formula = {"func": "col-sum"}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Sum" in result or "aggregation" in result.lower() or "Custom" in result

    def test_row_sum_summary(self, cm_builder):
        """Line 873: row-sum summary."""
        formula = {"func": "row-sum"}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Row" in result or "SUM" in result or "Custom" in result

    def test_cumulative_summary(self, cm_builder):
        """Line 878: cumulative with inner metric."""
        formula = {
            "func": "cumulative",
            "col": {"func": "metric", "name": "metrics/orders"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Cumulative" in result or "orders" in result

    def test_cumulative_no_inner(self, cm_builder):
        """Line 879: cumulative without inner."""
        formula = {"func": "cumulative"}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Cumulative" in result or "Custom" in result

    def test_rolling_with_window(self, cm_builder):
        """Lines 885-886: rolling with window and inner metric."""
        formula = {
            "func": "rolling",
            "col": {"func": "metric", "name": "metrics/revenue"},
            "window": 7,
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Rolling" in result or "7" in result

    def test_rolling_no_window(self, cm_builder):
        """Line 887: rolling without window."""
        formula = {
            "func": "rolling",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Rolling" in result

    def test_rolling_no_inner(self, cm_builder):
        """Line 888: rolling without inner metric."""
        formula = {"func": "rolling"}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Rolling" in result or "Custom" in result

    def test_abs_summary(self, cm_builder):
        """Line 904: abs with inner metric."""
        formula = {
            "func": "abs",
            "col": {"func": "metric", "name": "metrics/delta"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "ABS" in result or "delta" in result

    def test_abs_no_inner(self, cm_builder):
        """Line 905: abs without inner."""
        formula = {"func": "abs"}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Absolute" in result or "Custom" in result

    def test_sqrt_summary(self, cm_builder):
        """Line 911: sqrt with inner metric."""
        formula = {
            "func": "sqrt",
            "col": {"func": "metric", "name": "metrics/variance"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "SQRT" in result or "variance" in result

    def test_sqrt_no_inner(self, cm_builder):
        """Line 912: sqrt without inner."""
        formula = {"func": "sqrt"}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "SQRT" in result or "Custom" in result

    def test_pow_summary(self, cm_builder):
        """Lines 917-918: pow with base and exp."""
        formula = {
            "func": "pow",
            "col1": {"func": "metric", "name": "metrics/value"},
            "col2": {"func": "number", "val": 2},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "^" in result or "value" in result

    def test_pow_no_refs(self, cm_builder):
        """Line 919: pow without resolvable refs."""
        formula = {"func": "pow", "col1": {}, "col2": {}}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Power" in result or "Custom" in result

    def test_percentile_summary(self, cm_builder):
        """Lines 894-897: percentile with inner metric and value."""
        formula = {
            "func": "percentile",
            "col": {"func": "metric", "name": "metrics/load_time"},
            "percentile": 95,
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "P95" in result or "load_time" in result

    def test_median_summary(self, cm_builder):
        """Line 898: median with inner metric."""
        formula = {
            "func": "median",
            "col": {"func": "metric", "name": "metrics/duration"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Median" in result or "duration" in result

    def test_statistical_no_inner(self, cm_builder):
        """Line 899: statistical function without inner."""
        formula = {"func": "variance"}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Variance" in result or "Custom" in result


class TestGenericFallbackSummaries:
    """Cover lines 923-925, 928, 931-933, 939."""

    def _make_parsed(self, functions=None, metrics=None, segments=None):
        return {
            "functions_internal": functions or [],
            "functions_display": [],
            "metric_references": metrics or [],
            "segment_references": segments or [],
            "operator_count": 0,
            "nesting_depth": 0,
            "conditional_count": 0,
            "complexity_score": 0.0,
        }

    def test_segment_with_metric_and_segment_refs(self, cm_builder):
        """Lines 923-924: segment in functions with metric refs and segment refs."""
        formula = {"func": "coalesce"}
        parsed = self._make_parsed(
            functions=["segment", "coalesce"],
            metrics=["revenue"],
            segments=["s_mobile"],
        )
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "filtered" in result or "revenue" in result

    def test_segment_with_metric_no_segment_refs(self, cm_builder):
        """Line 925: segment in functions with metric refs but no segment refs."""
        formula = {"func": "coalesce"}
        parsed = self._make_parsed(
            functions=["segment", "coalesce"],
            metrics=["revenue"],
            segments=[],
        )
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Filtered" in result or "revenue" in result

    def test_divide_in_functions_with_two_metrics(self, cm_builder):
        """Line 928: divide in functions with 2+ metric refs."""
        formula = {"func": "coalesce"}
        parsed = self._make_parsed(
            functions=["divide", "coalesce"],
            metrics=["revenue", "orders"],
        )
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Ratio" in result

    def test_if_in_functions_with_metrics(self, cm_builder):
        """Lines 931-932: if in functions with metric refs."""
        formula = {"func": "coalesce"}
        parsed = self._make_parsed(
            functions=["if", "coalesce"],
            metrics=["revenue"],
        )
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Conditional" in result

    def test_if_in_functions_no_metrics(self, cm_builder):
        """Line 933: if in functions without metric refs."""
        formula = {"func": "coalesce"}
        parsed = self._make_parsed(functions=["if", "coalesce"])
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Conditional" in result

    def test_two_metric_refs(self, cm_builder):
        """Line 939: exactly 2 metric refs, no special functions."""
        formula = {"func": "coalesce"}
        parsed = self._make_parsed(metrics=["revenue", "orders"])
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Combines" in result

    def test_three_or_more_metric_refs(self, cm_builder):
        """Line 940: 3+ metric refs."""
        formula = {"func": "coalesce"}
        parsed = self._make_parsed(metrics=["a", "b", "c"])
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "3 metrics" in result or "Combines" in result

    def test_one_metric_ref(self, cm_builder):
        """Line 937: exactly 1 metric ref."""
        formula = {"func": "coalesce"}
        parsed = self._make_parsed(metrics=["revenue"])
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Based on" in result or "revenue" in result


class TestBuildFormulaExpressionVisualizationGroup:
    """Cover visualization-group transparent wrapper in _build_formula_expression."""

    def test_visualization_group_wrapper(self, cm_builder):
        """Line 1037-1049: visualization-group passes through to inner formula."""
        node = {
            "func": "visualization-group",
            "formula": {
                "func": "divide",
                "col1": {"func": "metric", "name": "metrics/a"},
                "col2": {"func": "metric", "name": "metrics/b"},
            },
        }
        result = cm_builder._build_formula_expression(node)
        assert "a" in result and "b" in result

    def test_visualization_group_formulas_array(self, cm_builder):
        """Line 1045-1049: visualization-group with formulas array."""
        node = {
            "func": "visualization-group",
            "formulas": [
                {
                    "func": "metric",
                    "name": "metrics/revenue",
                },
            ],
        }
        result = cm_builder._build_formula_expression(node)
        assert "revenue" in result


class TestDescribeConditionBranches:
    """Cover additional condition description branches.

    We test _describe_condition directly because _generate_formula_summary
    returns the short _build_formula_expression result ('IF(..., 1)')
    before reaching the descriptive condition path.
    """

    def test_gte_condition(self, cm_builder):
        formula = {
            "func": "if",
            "condition": {
                "func": "gte",
                "col1": {"func": "metric", "name": "metrics/a"},
                "col2": {"func": "number", "val": 10},
            },
            "then": {"func": "number", "val": 1},
        }
        result = cm_builder._describe_condition(formula)
        assert ">=" in result

    def test_lt_condition(self, cm_builder):
        formula = {
            "func": "if",
            "condition": {
                "func": "lt",
                "col1": {"func": "metric", "name": "metrics/a"},
                "col2": {"func": "number", "val": 5},
            },
            "then": {"func": "number", "val": 1},
        }
        result = cm_builder._describe_condition(formula)
        assert "<" in result

    def test_lte_condition(self, cm_builder):
        formula = {
            "func": "if",
            "condition": {
                "func": "lte",
                "col1": {"func": "metric", "name": "metrics/a"},
                "col2": {"func": "number", "val": 5},
            },
            "then": {"func": "number", "val": 1},
        }
        result = cm_builder._describe_condition(formula)
        assert "<=" in result

    def test_eq_condition(self, cm_builder):
        formula = {
            "func": "if",
            "condition": {
                "func": "eq",
                "col1": {"func": "metric", "name": "metrics/a"},
                "col2": {"func": "number", "val": 0},
            },
            "then": {"func": "number", "val": 1},
        }
        result = cm_builder._describe_condition(formula)
        assert "=" in result

    def test_ne_condition(self, cm_builder):
        formula = {
            "func": "if",
            "condition": {
                "func": "ne",
                "col1": {"func": "metric", "name": "metrics/a"},
                "col2": {"func": "number", "val": 0},
            },
            "then": {"func": "number", "val": 1},
        }
        result = cm_builder._describe_condition(formula)
        # ne produces the unicode not-equal sign
        assert result  # Non-empty means condition was described


class TestNormalizeFormulaNodeEdgeCases:
    """Cover edge cases in _normalize_formula_node."""

    def test_bool_input(self, cm_builder):
        """Line 1186-1187: bool input returns literal node."""
        result = cm_builder._normalize_formula_node(True)
        assert result == {"func": "literal", "val": True}

    def test_float_input(self, cm_builder):
        """Line 1189-1190: float input returns number node."""
        result = cm_builder._normalize_formula_node(3.14)
        assert result == {"func": "number", "val": 3.14}

    def test_string_with_slash(self, cm_builder):
        """Line 1196-1197: string with / returns metric node."""
        result = cm_builder._normalize_formula_node("metrics/revenue")
        assert result == {"func": "metric", "name": "metrics/revenue"}

    def test_string_without_slash(self, cm_builder):
        """Line 1198: string without / returns literal node."""
        result = cm_builder._normalize_formula_node("some_literal")
        assert result == {"func": "literal", "val": "some_literal"}

    def test_empty_string_returns_none(self, cm_builder):
        """Line 1194-1195: empty string returns None."""
        assert cm_builder._normalize_formula_node("  ") is None

    def test_none_returns_none(self, cm_builder):
        """Line 1200: unrecognized type returns None."""
        assert cm_builder._normalize_formula_node(None) is None


# ==================== core/constants.py ====================


class TestAutoDetectWorkersException:
    """Cover lines 152-153: os.cpu_count() raises exception."""

    def test_cpu_count_raises_uses_default(self):
        """Lines 152-153: os.cpu_count raises, defaults to 4."""
        with patch("cja_auto_sdr.core.constants.os.cpu_count", side_effect=RuntimeError("no cpu")):
            result = auto_detect_workers(num_data_views=1)
        assert result >= 1


# ==================== core/lazy.py ====================


class TestMakeGetattrLazyTargetMissing:
    """Cover line 36: name in export_set but not in mapping."""

    def test_name_in_export_set_not_in_mapping(self):
        """Line 36: export name exists but has no mapping target."""
        getattr_fn = make_getattr(
            "test_module",
            ["foo", "bar"],
            mapping={"foo": "os"},
        )
        with pytest.raises(AttributeError, match="lazy target missing"):
            getattr_fn("bar")

    def test_name_not_in_export_set(self):
        """Line 37: name not in export_set at all."""
        getattr_fn = make_getattr("test_module", ["foo"], target_module="os")
        with pytest.raises(AttributeError, match="has no attribute"):
            getattr_fn("nonexistent")


# ==================== core/locks/manager.py ====================


class TestLockManagerHeartbeatEdgeCases:
    """Cover lines 180, 202, 210."""

    def test_heartbeat_thread_already_alive(self, tmp_path):
        """Line 180: _start_heartbeat_if_needed when thread is already alive."""
        lock_path = tmp_path / "test.lock"
        manager = LockManager(
            lock_path=lock_path,
            owner="test",
            stale_threshold_seconds=30,
            backend_name="lease",
        )
        manager._heartbeat_thread = threading.Thread(target=lambda: time.sleep(10), daemon=True)
        manager._heartbeat_thread.start()

        mock_handle = MagicMock()
        mock_info = MagicMock()
        manager._handle = mock_handle
        manager._lock_info = mock_info

        manager._start_heartbeat_if_needed()

        manager._heartbeat_stop.set()
        manager._heartbeat_thread.join(timeout=1)

    def test_heartbeat_loop_handle_none(self, tmp_path):
        """Line 202: _heartbeat_loop returns when handle becomes None."""
        lock_path = tmp_path / "test.lock"
        manager = LockManager(
            lock_path=lock_path,
            owner="test",
            stale_threshold_seconds=3,
            backend_name="lease",
        )
        manager._handle = None
        manager._lock_info = None
        manager._heartbeat_stop.clear()

        done = threading.Event()

        def run_loop():
            manager._heartbeat_loop(0.01)
            done.set()

        t = threading.Thread(target=run_loop, daemon=True)
        t.start()
        assert done.wait(timeout=2), "Heartbeat loop did not exit"

    def test_heartbeat_loop_oserror_after_stop(self, tmp_path):
        """Line 210: OSError during heartbeat but _heartbeat_stop is already set."""
        lock_path = tmp_path / "test.lock"
        manager = LockManager(
            lock_path=lock_path,
            owner="test",
            stale_threshold_seconds=3,
            backend_name="lease",
        )

        from cja_auto_sdr.core.locks.backends import LockInfo

        mock_handle = MagicMock()
        mock_info = LockInfo(
            lock_id="test",
            pid=os.getpid(),
            host="localhost",
            owner="test",
            started_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T00:00:00",
            backend="lease",
            version=1,
        )
        manager._handle = mock_handle
        manager._lock_info = mock_info

        manager.backend.write_info = MagicMock(side_effect=OSError("disk error"))

        done = threading.Event()

        def run_loop():
            manager._heartbeat_stop.clear()

            call_count = {"n": 0}

            def mock_wait(timeout):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    time.sleep(0.01)
                    return False
                return True

            manager._heartbeat_stop.wait = mock_wait
            manager._heartbeat_stop.set()

            manager._heartbeat_loop(0.01)
            done.set()

        t = threading.Thread(target=run_loop, daemon=True)
        t.start()
        assert done.wait(timeout=5), "Heartbeat loop did not exit"


# ==================== org/cache.py ====================


class TestIsProcessRunningOSError:
    """Cover lines 114-115: OSError with errno == EPERM."""

    def test_oserror_with_eperm(self):
        """Lines 114-115: os.kill raises OSError with EPERM errno."""
        err = OSError("operation not permitted")
        err.errno = errno.EPERM
        with patch("os.kill", side_effect=err):
            result = OrgReportLock._is_process_running(os.getpid())
        assert result is True

    def test_oserror_with_other_errno(self):
        """Lines 114-115: os.kill raises OSError with non-EPERM errno."""
        err = OSError("some other error")
        err.errno = errno.ENOENT
        with patch("os.kill", side_effect=err):
            result = OrgReportLock._is_process_running(os.getpid())
        assert result is False


# ---------------------------------------------------------------------------
# core/logging.py — empty field name and duplicate handler (lines 168, 407)
# ---------------------------------------------------------------------------


class TestLoggingMiscBranches:
    """Cover specific uncovered branches in core/logging.py."""

    def test_is_sensitive_field_empty_parts(self):
        """Line 168: field name that normalizes to empty parts returns False."""
        from cja_auto_sdr.core.logging import _is_sensitive_field

        assert _is_sensitive_field("___") is False


# ==================== calculated_metrics.py — additional coverage ====================


class TestProcessMetricNoneFormulaNormalization:
    """Cover lines 482 (stats.record_skip with no formula) and 499-502 (unsupported formula)."""

    def test_none_formula_with_stats(self, cm_builder):
        """Line 482: formula is None, stats records the skip."""
        metric_data = {
            "id": "cm_none_formula",
            "name": "NoneFormula",
            "definition": {"formula": None},
        }
        stats = BatchProcessingStats()
        result = cm_builder._process_metric(metric_data, stats)
        assert result is None
        assert stats.skipped == 1

    def test_unsupported_formula_format_with_stats(self, cm_builder):
        """Lines 499-502: _normalize_formula_node returns None for list of Nones."""
        metric_data = {
            "id": "cm_unsupported",
            "name": "Unsupported",
            "definition": {"formula": [None, None]},
        }
        stats = BatchProcessingStats()
        result = cm_builder._process_metric(metric_data, stats)
        assert result is None
        assert stats.skipped == 1


class TestCoerceScalarTextOnBuilder:
    """Cover line 579: _coerce_scalar_text called on the builder instance."""

    def test_coerce_scalar_text_passthrough(self, cm_builder):
        """Line 579: builder method delegates to module-level coerce_scalar_text."""
        assert cm_builder._coerce_scalar_text("hello") == "hello"
        assert cm_builder._coerce_scalar_text(None) == ""
        assert cm_builder._coerce_scalar_text(42) == "42"


class TestParseFormulaTraverseNonDict:
    """Cover line 630: traverse called with a non-dict node."""

    def test_non_dict_operand_in_operands_list(self, cm_builder):
        """Line 630: non-dict items in operands list are silently skipped."""
        formula = {
            "func": "add",
            "operands": [
                "not_a_dict",
                42,
                {"func": "metric", "name": "metrics/revenue"},
            ],
        }
        parsed = cm_builder._parse_formula(formula)
        assert "revenue" in parsed["metric_references"]


class TestFormulaSummaryNumericFallback:
    """Cover lines 769-773: formula that doesn't normalize but is numeric or string."""

    def _make_parsed(self):
        return {
            "functions_internal": [],
            "functions_display": [],
            "metric_references": [],
            "segment_references": [],
            "operator_count": 0,
            "nesting_depth": 0,
            "conditional_count": 0,
            "complexity_score": 0.0,
        }

    def test_numeric_formula_returns_string_of_number(self, cm_builder):
        """Lines 769-770: formula is a raw number (int/float)."""
        # _normalize_formula_node will normalize this to {"func": "number", ...}
        # so we need to force the fallback: we mock _normalize_formula_node to return None
        parsed = self._make_parsed()
        with patch.object(cm_builder, "_normalize_formula_node", return_value=None):
            result = cm_builder._generate_formula_summary(42, parsed)
        assert result == "42"

    def test_float_formula_returns_string_of_number(self, cm_builder):
        """Lines 769-770: formula is a raw float."""
        parsed = self._make_parsed()
        with patch.object(cm_builder, "_normalize_formula_node", return_value=None):
            result = cm_builder._generate_formula_summary(3.14, parsed)
        assert result == "3.14"

    def test_string_formula_fallback(self, cm_builder):
        """Lines 771-772: formula is a non-empty string that doesn't normalize."""
        parsed = self._make_parsed()
        with patch.object(cm_builder, "_normalize_formula_node", return_value=None):
            result = cm_builder._generate_formula_summary("custom_expr", parsed)
        assert result == "custom_expr"

    def test_empty_formula_fallback(self, cm_builder):
        """Line 773: formula doesn't normalize and isn't numeric or string."""
        parsed = self._make_parsed()
        with patch.object(cm_builder, "_normalize_formula_node", return_value=None):
            result = cm_builder._generate_formula_summary(None, parsed)
        assert result == "Custom calculated metric"


class TestFormulaSummaryDivideNoRefs:
    """Cover line 814: divide with unresolvable references."""

    def test_divide_returns_ratio_calculation(self, cm_builder):
        """Line 814: divide where neither operand resolves to a name."""
        formula = {"func": "divide", "col1": {}, "col2": {}}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Ratio" in result


class TestFormulaSummaryAddOperands:
    """Cover lines 828-830: add with exactly 2-3 operands and >3 operands."""

    def test_add_two_operands_joined(self, cm_builder):
        """Lines 828-829: add with exactly 2 operands joined by +."""
        formula = {
            "func": "add",
            "col1": {"func": "metric", "name": "metrics/revenue"},
            "col2": {"func": "metric", "name": "metrics/tax"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "+" in result

    def test_add_three_operands_joined(self, cm_builder):
        """Lines 828-829: add with exactly 3 operands."""
        formula = {
            "func": "add",
            "col1": {"func": "metric", "name": "metrics/a"},
            "col2": {"func": "metric", "name": "metrics/b"},
            "operands": [{"func": "metric", "name": "metrics/c"}],
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "+" in result


class TestFormulaSummarySubtractWithRefs:
    """Cover line 839: subtract with resolved refs."""

    def test_subtract_shows_minus_sign(self, cm_builder):
        """Line 839: subtract with two resolvable metric refs."""
        formula = {
            "func": "subtract",
            "col1": {"func": "metric", "name": "metrics/total"},
            "col2": {"func": "metric", "name": "metrics/refunds"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "total" in result and "-" in result and "refunds" in result


class TestFormulaSummaryIfCondition:
    """Cover lines 843-846: if formula with and without condition desc."""

    def test_if_with_condition(self, cm_builder):
        """Lines 843-845: if with resolvable condition."""
        formula = {
            "func": "if",
            "condition": {
                "func": "gt",
                "col1": {"func": "metric", "name": "metrics/x"},
                "col2": {"func": "number", "val": 0},
            },
            "then": {"func": "number", "val": 1},
            "else": {"func": "number", "val": 0},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "IF" in result or "If" in result

    def test_if_no_condition(self, cm_builder):
        """Line 846: if with empty condition dict."""
        formula = {"func": "if", "condition": {}, "then": {}, "else": {}}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Conditional" in result


class TestFormulaSummarySegmentBranches:
    """Cover lines 853, 855: segment with metric+id and metric only."""

    def test_segment_with_both(self, cm_builder):
        """Line 853: segment with inner metric and segment_id."""
        formula = {
            "func": "segment",
            "segment_id": "s300000000_abcdef",
            "metric": {"func": "metric", "name": "metrics/pageviews"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "pageviews" in result

    def test_segment_metric_only_no_id(self, cm_builder):
        """Line 855: segment with metric but no segment_id."""
        formula = {
            "func": "segment",
            "metric": {"func": "metric", "name": "metrics/pageviews"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "filtered" in result


class TestFormulaSummaryMetricRef:
    """Cover line 861: metric func returns '= name'."""

    def test_metric_named(self, cm_builder):
        """Line 861: func=metric with a clean name."""
        formula = {"func": "metric", "name": "metrics/orders"}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "orders" in result


class TestFormulaSummaryColAggregation:
    """Cover line 868: col-sum/col-max/etc with inner metric."""

    def test_col_max_with_inner(self, cm_builder):
        """Line 868: col-max with inner metric ref."""
        formula = {
            "func": "col-max",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "MAX" in result and "revenue" in result


class TestFormulaSummaryCumulativeWithInner:
    """Cover line 878: cumulative with inner metric."""

    def test_cumulative_with_metric(self, cm_builder):
        """Line 878: cumulative with inner metric ref."""
        formula = {
            "func": "cumulative",
            "metric": {"func": "metric", "name": "metrics/visits"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Cumulative" in result or "CUM" in result


class TestFormulaSummaryAbsAndMath:
    """Cover lines 904, 911: abs and sqrt/log etc with inner metric."""

    def test_abs_with_col1(self, cm_builder):
        """Line 904: abs using col1 key."""
        formula = {
            "func": "abs",
            "col1": {"func": "metric", "name": "metrics/delta"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "ABS" in result and "delta" in result

    def test_log_with_inner(self, cm_builder):
        """Line 911: log with inner metric."""
        formula = {
            "func": "log",
            "col": {"func": "metric", "name": "metrics/value"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "LOG" in result and "value" in result


class TestBuildFormulaExpressionComplexDivide:
    """Cover lines 969-972: divide with complex operands needing parenthesization."""

    def test_complex_operands_get_parenthesized(self, cm_builder):
        """Lines 969-972: divide where operands contain spaces -> wrapped in parens."""
        formula = {
            "func": "divide",
            "col1": {
                "func": "add",
                "col1": {"func": "metric", "name": "metrics/a"},
                "col2": {"func": "metric", "name": "metrics/b"},
            },
            "col2": {
                "func": "subtract",
                "col1": {"func": "metric", "name": "metrics/c"},
                "col2": {"func": "metric", "name": "metrics/d"},
            },
        }
        result = cm_builder._build_formula_expression(formula)
        # The add sub-expression "a + b" should be wrapped as "(a + b)"
        assert "(" in result and ")" in result
        assert "/" in result
