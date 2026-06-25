"""Coverage hardening tests targeting missed statements across generator.py, __main__.py, and helpers.

These tests focus on high-value gaps with real user-facing code paths.
Part of the v3.3.5 hardening release.
"""

from __future__ import annotations

import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

# ---------------------------------------------------------------------------
# Tier 2a — _is_missing_sort_value and _to_numeric_sort_value (lines 8059-8061)
# ---------------------------------------------------------------------------


class TestSortHelpers:
    """Test _is_missing_sort_value and _to_numeric_sort_value edge cases."""

    def test_is_missing_sort_value_none(self) -> None:
        from cja_auto_sdr.generator import _is_missing_sort_value

        assert _is_missing_sort_value(None) is True

    def test_is_missing_sort_value_empty_string(self) -> None:
        from cja_auto_sdr.generator import _is_missing_sort_value

        assert _is_missing_sort_value("") is True
        assert _is_missing_sort_value("   ") is True

    def test_is_missing_sort_value_nan(self) -> None:
        from cja_auto_sdr.generator import _is_missing_sort_value

        assert _is_missing_sort_value(float("nan")) is True

    def test_is_missing_sort_value_concrete(self) -> None:
        from cja_auto_sdr.generator import _is_missing_sort_value

        assert _is_missing_sort_value("hello") is False
        assert _is_missing_sort_value(42) is False

    def test_is_missing_sort_value_non_checkable_type(self) -> None:
        """Types that raise on pd.isna should return False."""
        from cja_auto_sdr.generator import _is_missing_sort_value

        # A dict raises TypeError in pd.isna for ambiguous truth value
        assert _is_missing_sort_value({"key": "value"}) is False

    def test_to_numeric_sort_value_none(self) -> None:
        from cja_auto_sdr.generator import _to_numeric_sort_value

        assert _to_numeric_sort_value(None) is None

    def test_to_numeric_sort_value_bool(self) -> None:
        from cja_auto_sdr.generator import _to_numeric_sort_value

        assert _to_numeric_sort_value(True) is None
        assert _to_numeric_sort_value(False) is None

    def test_to_numeric_sort_value_int(self) -> None:
        from cja_auto_sdr.generator import _to_numeric_sort_value

        assert _to_numeric_sort_value(42) == 42.0

    def test_to_numeric_sort_value_float(self) -> None:
        from cja_auto_sdr.generator import _to_numeric_sort_value

        assert _to_numeric_sort_value(3.14) == 3.14

    def test_to_numeric_sort_value_nan_float(self) -> None:
        from cja_auto_sdr.generator import _to_numeric_sort_value

        assert _to_numeric_sort_value(float("nan")) is None

    def test_to_numeric_sort_value_string_numeric(self) -> None:
        from cja_auto_sdr.generator import _to_numeric_sort_value

        assert _to_numeric_sort_value("3.14") == 3.14

    def test_to_numeric_sort_value_string_non_numeric(self) -> None:
        from cja_auto_sdr.generator import _to_numeric_sort_value

        assert _to_numeric_sort_value("abc") is None

    def test_to_numeric_sort_value_unsupported_type(self) -> None:
        from cja_auto_sdr.generator import _to_numeric_sort_value

        assert _to_numeric_sort_value([1, 2]) is None


# ---------------------------------------------------------------------------
# Tier 1b — Lazy forwarding stubs (cli/interactive.py, cli/main.py)
# ---------------------------------------------------------------------------


class TestLazyForwarding:
    """Verify lazy forwarding modules resolve their advertised symbols."""

    def test_cli_interactive_lazy_forwarding(self) -> None:
        """cli.interactive exposes interactive_select_dataviews as callable."""
        from cja_auto_sdr.cli.interactive import interactive_select_dataviews

        assert callable(interactive_select_dataviews)

    def test_cli_interactive_wizard_forwarding(self) -> None:
        """cli.interactive exposes interactive_wizard as callable."""
        from cja_auto_sdr.cli.interactive import interactive_wizard

        assert callable(interactive_wizard)

    def test_cli_interactive_prompt_forwarding(self) -> None:
        """cli.interactive exposes prompt_for_selection as callable."""
        from cja_auto_sdr.cli.interactive import prompt_for_selection

        assert callable(prompt_for_selection)

    def test_cli_main_lazy_forwarding(self) -> None:
        """cli.main exposes main as callable."""
        from cja_auto_sdr.cli.main import main

        assert callable(main)


# ---------------------------------------------------------------------------
# Tier 2a — _normalize_optional_component_int edge cases (lines 8924-8940)
# ---------------------------------------------------------------------------


class TestNormalizeOptionalComponentInt:
    """Test _normalize_optional_component_int with bool, float, str inputs."""

    def test_bool_true(self) -> None:
        from cja_auto_sdr.generator import _normalize_optional_component_int

        assert _normalize_optional_component_int(True) == 1

    def test_bool_false(self) -> None:
        from cja_auto_sdr.generator import _normalize_optional_component_int

        assert _normalize_optional_component_int(False) == 0

    def test_float_integer_value(self) -> None:
        from cja_auto_sdr.generator import _normalize_optional_component_int

        assert _normalize_optional_component_int(3.0) == 3

    def test_float_non_integer_value(self) -> None:
        """Non-integer float returns default."""
        from cja_auto_sdr.generator import _normalize_optional_component_int

        assert _normalize_optional_component_int(3.5) == 0

    def test_string_numeric(self) -> None:
        from cja_auto_sdr.generator import _normalize_optional_component_int

        assert _normalize_optional_component_int("42") == 42

    def test_string_non_numeric(self) -> None:
        """Non-numeric string returns default."""
        from cja_auto_sdr.generator import _normalize_optional_component_int

        assert _normalize_optional_component_int("abc") == 0

    def test_string_empty(self) -> None:
        """Empty string returns default."""
        from cja_auto_sdr.generator import _normalize_optional_component_int

        assert _normalize_optional_component_int("") == 0

    def test_string_whitespace(self) -> None:
        """Whitespace-only string returns default."""
        from cja_auto_sdr.generator import _normalize_optional_component_int

        assert _normalize_optional_component_int("   ") == 0

    def test_non_matching_type(self) -> None:
        """Unsupported type (e.g. list) returns default."""
        from cja_auto_sdr.generator import _normalize_optional_component_int

        assert _normalize_optional_component_int([1, 2]) == 0


# ---------------------------------------------------------------------------
# Tier 2a — _coerce_http_status_code edge cases (lines 8434-8448)
# ---------------------------------------------------------------------------


class TestCoerceHttpStatusCode:
    """Test _coerce_http_status_code edge cases for bool, out-of-range, string patterns."""

    def test_bool_returns_none(self) -> None:
        from cja_auto_sdr.generator import _coerce_http_status_code

        assert _coerce_http_status_code(True) is None
        assert _coerce_http_status_code(False) is None

    def test_int_out_of_range_high(self) -> None:
        from cja_auto_sdr.generator import _coerce_http_status_code

        assert _coerce_http_status_code(999) is None

    def test_int_out_of_range_low(self) -> None:
        from cja_auto_sdr.generator import _coerce_http_status_code

        assert _coerce_http_status_code(50) is None

    def test_int_valid(self) -> None:
        from cja_auto_sdr.generator import _coerce_http_status_code

        assert _coerce_http_status_code(404) == 404

    def test_string_digit_valid(self) -> None:
        from cja_auto_sdr.generator import _coerce_http_status_code

        assert _coerce_http_status_code("200") == 200

    def test_string_digit_out_of_range(self) -> None:
        from cja_auto_sdr.generator import _coerce_http_status_code

        assert _coerce_http_status_code("999") is None

    def test_string_empty(self) -> None:
        from cja_auto_sdr.generator import _coerce_http_status_code

        assert _coerce_http_status_code("") is None

    def test_string_with_embedded_code(self) -> None:
        """String like 'HTTP 403 Forbidden' extracts the status code."""
        from cja_auto_sdr.generator import _coerce_http_status_code

        assert _coerce_http_status_code("HTTP 403 Forbidden") == 403

    def test_string_with_out_of_range_embedded(self) -> None:
        """Embedded numeric code outside range returns None."""
        from cja_auto_sdr.generator import _coerce_http_status_code

        assert _coerce_http_status_code("Error code 999") is None

    def test_non_matching_type(self) -> None:
        """Unsupported types (e.g. list) return None."""
        from cja_auto_sdr.generator import _coerce_http_status_code

        assert _coerce_http_status_code([404]) is None


# ---------------------------------------------------------------------------
# Tier 2a — _iter_error_chain_nodes and _extract_http_status_codes (lines 8460-8488)
# ---------------------------------------------------------------------------


class TestIterErrorChainNodes:
    """Test _iter_error_chain_nodes traversal through dicts, chained errors, and responses."""

    def test_dict_node_with_nested_error(self) -> None:
        """Dict node with 'error' key traverses into the nested error."""
        from cja_auto_sdr.generator import _iter_error_chain_nodes

        inner_error = {"status_code": 403}
        outer_error = Exception("wrapper")
        outer_error.response = {"error": inner_error}  # type: ignore[attr-defined]

        nodes = _iter_error_chain_nodes(outer_error)
        # Should find the outer exception, the response dict, and the inner dict
        assert any(isinstance(n, dict) and n.get("status_code") == 403 for n in nodes)

    def test_chained_cause(self) -> None:
        """Exception with __cause__ traverses the chain."""
        from cja_auto_sdr.generator import _iter_error_chain_nodes

        cause = ValueError("root cause")
        wrapper = RuntimeError("wrapper")
        wrapper.__cause__ = cause

        nodes = _iter_error_chain_nodes(wrapper)
        assert cause in nodes
        assert wrapper in nodes

    def test_circular_reference_avoided(self) -> None:
        """Circular references do not cause infinite loops."""
        from cja_auto_sdr.generator import _iter_error_chain_nodes

        a = Exception("a")
        b = Exception("b")
        a.__cause__ = b
        b.__cause__ = a

        nodes = _iter_error_chain_nodes(a)
        assert a in nodes
        assert b in nodes


class TestExtractHttpStatusCodes:
    """Test _extract_http_status_codes extracting codes from nested errors."""

    def test_extracts_from_dict_node(self) -> None:
        """Status code in a dict node is extracted."""
        from cja_auto_sdr.generator import _extract_http_status_codes

        error = Exception("api error")
        error.response = {"status_code": 403}  # type: ignore[attr-defined]

        codes = _extract_http_status_codes(error)
        assert 403 in codes

    def test_extracts_from_attribute(self) -> None:
        """Status code in an attribute of the error object is extracted."""
        from cja_auto_sdr.generator import _extract_http_status_codes

        error = Exception("api error")
        error.status_code = 404  # type: ignore[attr-defined]

        codes = _extract_http_status_codes(error)
        assert 404 in codes

    def test_bool_status_code_ignored(self) -> None:
        """Boolean status_code attributes are ignored (not coerced)."""
        from cja_auto_sdr.generator import _extract_http_status_codes

        error = Exception("api error")
        error.status_code = True  # type: ignore[attr-defined]

        codes = _extract_http_status_codes(error)
        assert len(codes) == 0


# ---------------------------------------------------------------------------
# Tier 2a — _normalize_exit_code with bool input (line 972)
# ---------------------------------------------------------------------------


class TestNormalizeExitCode:
    """Test _normalize_exit_code with edge-case inputs."""

    def test_none_returns_zero(self) -> None:
        from cja_auto_sdr.generator import _normalize_exit_code

        assert _normalize_exit_code(None) == 0

    def test_int_passthrough(self) -> None:
        from cja_auto_sdr.generator import _normalize_exit_code

        assert _normalize_exit_code(42) == 42

    def test_bool_true(self) -> None:
        """Bool True normalizes to 1."""
        from cja_auto_sdr.generator import _normalize_exit_code

        assert _normalize_exit_code(True) == 1

    def test_bool_false(self) -> None:
        """Bool False normalizes to 0."""
        from cja_auto_sdr.generator import _normalize_exit_code

        assert _normalize_exit_code(False) == 0

    def test_string_returns_one(self) -> None:
        """Non-int, non-bool, non-None value normalizes to 1."""
        from cja_auto_sdr.generator import _normalize_exit_code

        assert _normalize_exit_code("error message") == 1


# ---------------------------------------------------------------------------
# Tier 2a — _normalize_single_dataview_payload edge cases (lines 8409-8413)
# ---------------------------------------------------------------------------


class TestNormalizeSingleDataviewPayload:
    """Test _normalize_single_dataview_payload with DataFrame and dict inputs."""

    def test_none_returns_none(self) -> None:
        from cja_auto_sdr.generator import _normalize_single_dataview_payload

        assert _normalize_single_dataview_payload(None) is None

    def test_empty_dataframe_returns_none(self) -> None:
        from cja_auto_sdr.generator import _normalize_single_dataview_payload

        assert _normalize_single_dataview_payload(pd.DataFrame()) is None

    def test_dataframe_with_empty_records(self) -> None:
        """DataFrame that produces empty records list returns None."""
        from cja_auto_sdr.generator import _normalize_single_dataview_payload

        # A DataFrame with columns but no rows
        df = pd.DataFrame(columns=["id", "name"])
        assert _normalize_single_dataview_payload(df) is None

    def test_dataframe_with_valid_record(self) -> None:
        from cja_auto_sdr.generator import _normalize_single_dataview_payload

        df = pd.DataFrame([{"id": "dv_123", "name": "Test DV"}])
        result = _normalize_single_dataview_payload(df)
        assert result is not None
        assert result["id"] == "dv_123"

    def test_dict_passthrough(self) -> None:
        from cja_auto_sdr.generator import _normalize_single_dataview_payload

        d = {"id": "dv_123", "name": "Test DV"}
        assert _normalize_single_dataview_payload(d) is d

    def test_unsupported_type_returns_none(self) -> None:
        from cja_auto_sdr.generator import _normalize_single_dataview_payload

        assert _normalize_single_dataview_payload("not a dict") is None


# ---------------------------------------------------------------------------
# Tier 2a — _resolve_discovery_output_format (line 7966)
# ---------------------------------------------------------------------------


class TestResolveCommandOutputFormat:
    """Test _resolve_command_output_format stdout and fallback policies."""

    def test_stdout_defaults_to_stdout_fallback_when_missing(self) -> None:
        from cja_auto_sdr.generator import _resolve_command_output_format

        result = _resolve_command_output_format(
            None,
            supported_formats={"json": "json", "csv": "csv", "table": "table"},
            fallback_format="table",
            output_to_stdout=True,
            stdout_fallback_format="json",
            stdout_allowed_formats=("json", "csv"),
            warning_scope="test command",
        )
        assert result == "json"

    def test_stdout_preserves_explicit_allowed_format(self) -> None:
        from cja_auto_sdr.generator import _resolve_command_output_format

        result = _resolve_command_output_format(
            "csv",
            supported_formats={"json": "json", "csv": "csv", "table": "table"},
            fallback_format="table",
            output_to_stdout=True,
            stdout_fallback_format="json",
            stdout_allowed_formats=("json", "csv"),
            warning_scope="test command",
        )
        assert result == "csv"

    def test_stdout_disallowed_supported_format_warns_and_falls_back(self, caplog: pytest.LogCaptureFixture) -> None:
        from cja_auto_sdr.generator import _resolve_command_output_format

        with caplog.at_level(logging.WARNING, logger="cja_auto_sdr.generator"):
            result = _resolve_command_output_format(
                "table",
                supported_formats={"json": "json", "csv": "csv", "table": "table"},
                fallback_format="table",
                output_to_stdout=True,
                stdout_fallback_format="json",
                stdout_allowed_formats=("json", "csv"),
                warning_scope="test command",
            )

        assert result == "json"
        assert "with --output stdout" in caplog.text
        assert "using json" in caplog.text


class TestResolveDiscoveryOutputFormat:
    """Test _resolve_discovery_output_format unsupported format warning path."""

    def test_json_passthrough(self) -> None:
        from cja_auto_sdr.generator import _resolve_discovery_output_format

        assert _resolve_discovery_output_format("json", output_to_stdout=False) == "json"

    def test_csv_passthrough(self) -> None:
        from cja_auto_sdr.generator import _resolve_discovery_output_format

        assert _resolve_discovery_output_format("csv", output_to_stdout=False) == "csv"

    def test_stdout_defaults_to_json(self) -> None:
        from cja_auto_sdr.generator import _resolve_discovery_output_format

        assert _resolve_discovery_output_format(None, output_to_stdout=True) == "json"

    def test_stdout_preserves_explicit_csv(self) -> None:
        from cja_auto_sdr.generator import _resolve_discovery_output_format

        assert _resolve_discovery_output_format("csv", output_to_stdout=True) == "csv"

    def test_stdout_console_alias_warns_and_defaults_to_json(self, caplog: pytest.LogCaptureFixture) -> None:
        from cja_auto_sdr.generator import _resolve_discovery_output_format

        with caplog.at_level(logging.WARNING, logger="cja_auto_sdr.generator"):
            result = _resolve_discovery_output_format("console", output_to_stdout=True)

        assert result == "json"
        assert "discovery commands" in caplog.text
        assert "using json" in caplog.text

    def test_unsupported_format_warns_and_defaults_to_table(self) -> None:
        """Unsupported format like 'excel' triggers a warning and falls back to 'table'."""
        from cja_auto_sdr.generator import _resolve_discovery_output_format

        result = _resolve_discovery_output_format("excel", output_to_stdout=False)
        assert result == "table"

    def test_stdout_unsupported_format_warns_and_defaults_to_json(self, caplog: pytest.LogCaptureFixture) -> None:
        from cja_auto_sdr.generator import _resolve_discovery_output_format

        with caplog.at_level(logging.WARNING, logger="cja_auto_sdr.generator"):
            result = _resolve_discovery_output_format("excel", output_to_stdout=True)

        assert result == "json"
        assert "using json" in caplog.text

    def test_console_alias_maps_to_table(self) -> None:
        """Console alias should normalize to table for discovery commands."""
        from cja_auto_sdr.generator import _resolve_discovery_output_format

        assert _resolve_discovery_output_format("console", output_to_stdout=False) == "table"

    def test_format_tokens_are_normalized_defensively(self) -> None:
        """Mixed-case and surrounding whitespace should still resolve correctly."""
        from cja_auto_sdr.generator import _resolve_discovery_output_format

        assert _resolve_discovery_output_format(" JSON ", output_to_stdout=False) == "json"


# ---------------------------------------------------------------------------
# Tier 2a — _approved_display and _tags_display (lines 9117-9128)
# ---------------------------------------------------------------------------


class TestApprovedAndTagsDisplay:
    """Test _approved_display and _tags_display edge cases."""

    def test_approved_display_none(self) -> None:
        from cja_auto_sdr.generator import _approved_display

        assert _approved_display(None) == "N/A"

    def test_approved_display_true(self) -> None:
        from cja_auto_sdr.generator import _approved_display

        assert _approved_display(True) == "Yes"

    def test_approved_display_false(self) -> None:
        from cja_auto_sdr.generator import _approved_display

        assert _approved_display(False) == "No"

    def test_approved_display_string(self) -> None:
        from cja_auto_sdr.generator import _approved_display

        assert _approved_display("custom") == "custom"

    def test_tags_display_non_list(self) -> None:
        from cja_auto_sdr.generator import _tags_display

        assert _tags_display(None) == ""
        assert _tags_display("not-a-list") == ""

    def test_tags_display_list(self) -> None:
        from cja_auto_sdr.generator import _tags_display

        assert _tags_display(["a", "b", "c"]) == "a, b, c"

    def test_tags_display_filters_non_strings(self) -> None:
        from cja_auto_sdr.generator import _tags_display

        assert _tags_display(["a", 123, "b"]) == "a, b"


# ---------------------------------------------------------------------------
# Tier 2b — __main__.py _minimum_option_arity (lines 100-103)
# ---------------------------------------------------------------------------


class TestMinimumOptionArity:
    """Test _minimum_option_arity with nargs='+' and default fallback."""

    def test_nargs_none(self) -> None:
        from cja_auto_sdr.__main__ import _minimum_option_arity

        assert _minimum_option_arity(None) == 1

    def test_nargs_int(self) -> None:
        from cja_auto_sdr.__main__ import _minimum_option_arity

        assert _minimum_option_arity(2) == 2
        assert _minimum_option_arity(0) == 0

    def test_nargs_plus(self) -> None:
        """nargs='+' returns 1 (at least one value required)."""
        from cja_auto_sdr.__main__ import _minimum_option_arity

        assert _minimum_option_arity("+") == 1

    def test_nargs_question_mark(self) -> None:
        """nargs='?' returns 0."""
        from cja_auto_sdr.__main__ import _minimum_option_arity

        assert _minimum_option_arity("?") == 0

    def test_nargs_star(self) -> None:
        """nargs='*' returns 0."""
        from cja_auto_sdr.__main__ import _minimum_option_arity

        assert _minimum_option_arity("*") == 0


# ---------------------------------------------------------------------------
# Tier 2b — __main__.py _scan_option_tokens compound short flags (lines 183-199)
# ---------------------------------------------------------------------------


class TestScanOptionTokensCompound:
    """Test _scan_option_tokens with compound short flags."""

    def test_compound_short_flags_qV(self) -> None:
        """Compound -qV resolves both -q and -V."""
        from cja_auto_sdr.__main__ import _scan_option_tokens

        result = _scan_option_tokens(["-qV"])
        assert "-V" in result.options
        assert "-q" in result.options
        assert not result.has_parse_error

    def test_single_short_option_with_arity(self) -> None:
        """Short option with min_arity > 0 consumes next token."""
        from cja_auto_sdr.__main__ import _scan_option_tokens

        # -p takes a value; the next token should be consumed
        result = _scan_option_tokens(["-p", "default"])
        assert "-p" in result.options
        assert not result.has_parse_error

    def test_double_dash_stops_scanning(self) -> None:
        """-- terminates option scanning."""
        from cja_auto_sdr.__main__ import _scan_option_tokens

        result = _scan_option_tokens(["--", "--version"])
        assert "--version" not in result.options
        assert not result.has_parse_error


# ---------------------------------------------------------------------------
# Tier 2b — __main__.py _render_completion_script unsupported shell (line 358)
# ---------------------------------------------------------------------------


class TestRenderCompletionScript:
    """Test _render_completion_script error path."""

    def test_unsupported_shell_raises(self) -> None:
        from cja_auto_sdr.__main__ import _render_completion_script

        with pytest.raises(ValueError, match="Unsupported shell"):
            _render_completion_script("powershell", "cja_auto_sdr")

    def test_supported_shell_returns_script(self) -> None:
        from cja_auto_sdr.__main__ import _render_completion_script

        script = _render_completion_script("bash", "cja_auto_sdr")
        assert "cja_auto_sdr" in script


# ---------------------------------------------------------------------------
# Tier 2a — _extract_dataset_info scalar fallback (line 7705)
# ---------------------------------------------------------------------------


class TestExtractDatasetInfo:
    """Test _extract_dataset_info with non-dict inputs."""

    def test_none_returns_na(self) -> None:
        from cja_auto_sdr.generator import _extract_dataset_info

        result = _extract_dataset_info(None)
        assert result["id"] == "N/A"
        assert result["name"] == "N/A"

    def test_falsey_int_returns_na(self) -> None:
        """Falsey int (0) returns N/A for both fields."""
        from cja_auto_sdr.generator import _extract_dataset_info

        result = _extract_dataset_info(0)
        assert result["id"] == "N/A"

    def test_string_becomes_id(self) -> None:
        """Plain string is used as the id value."""
        from cja_auto_sdr.generator import _extract_dataset_info

        result = _extract_dataset_info("ds_12345")
        assert result["id"] == "ds_12345"
        assert result["name"] == "N/A"

    def test_dict_extracts_fields(self) -> None:
        from cja_auto_sdr.generator import _extract_dataset_info

        result = _extract_dataset_info({"id": "ds_1", "name": "Dataset 1"})
        assert result["id"] == "ds_1"
        assert result["name"] == "Dataset 1"


# ---------------------------------------------------------------------------
# Tier 2a — _read_config_status_file edge cases (lines 10297-10303)
# ---------------------------------------------------------------------------


class TestReadConfigStatusFile:
    """Test _read_config_status_file error handling paths."""

    def test_valid_json_returns_payload(self, tmp_path: Path) -> None:
        from cja_auto_sdr.generator import _read_config_status_file

        config = tmp_path / "config.json"
        config.write_text('{"org_id": "test123"}')
        logger = logging.getLogger("test")
        payload, err = _read_config_status_file(str(config), logger)
        assert payload is not None
        assert err is None
        assert payload["org_id"] == "test123"

    def test_invalid_json_returns_error(self, tmp_path: Path) -> None:
        from cja_auto_sdr.generator import _read_config_status_file

        config = tmp_path / "config.json"
        config.write_text("{invalid json")
        logger = logging.getLogger("test")
        payload, err = _read_config_status_file(str(config), logger)
        assert payload is None
        assert "not valid JSON" in err

    def test_not_a_dict_returns_error(self, tmp_path: Path) -> None:
        from cja_auto_sdr.generator import _read_config_status_file

        config = tmp_path / "config.json"
        config.write_text("[1, 2, 3]")
        logger = logging.getLogger("test")
        payload, err = _read_config_status_file(str(config), logger)
        assert payload is None
        assert "must contain a JSON object" in err

    def test_missing_file_returns_error(self) -> None:
        from cja_auto_sdr.generator import _read_config_status_file

        logger = logging.getLogger("test")
        payload, err = _read_config_status_file("/nonexistent/config.json", logger)
        assert payload is None
        assert "Cannot read" in err


# ---------------------------------------------------------------------------
# Tier 2a — _describe_dataview_ignored_options (lines 14236-14243)
# ---------------------------------------------------------------------------


class TestDescribeDataviewIgnoredOptions:
    """Test _describe_dataview_ignored_options detects filtering flags."""

    def test_no_ignored_options(self) -> None:
        from cja_auto_sdr.generator import _describe_dataview_ignored_options

        args = SimpleNamespace(org_filter=None, org_exclude=None, discovery_sort=None, org_limit=None)
        assert _describe_dataview_ignored_options(args) == []

    def test_filter_ignored(self) -> None:
        from cja_auto_sdr.generator import _describe_dataview_ignored_options

        args = SimpleNamespace(org_filter="pattern", org_exclude=None, discovery_sort=None, org_limit=None)
        result = _describe_dataview_ignored_options(args)
        assert "--filter" in result

    def test_exclude_ignored(self) -> None:
        from cja_auto_sdr.generator import _describe_dataview_ignored_options

        args = SimpleNamespace(org_filter=None, org_exclude="pattern", discovery_sort=None, org_limit=None)
        result = _describe_dataview_ignored_options(args)
        assert "--exclude" in result

    def test_all_ignored(self) -> None:
        from cja_auto_sdr.generator import _describe_dataview_ignored_options

        args = SimpleNamespace(org_filter="f", org_exclude="e", discovery_sort="name", org_limit=10)
        result = _describe_dataview_ignored_options(args)
        assert "--filter" in result
        assert "--exclude" in result
        assert "--sort" in result
        assert "--limit" in result


# ---------------------------------------------------------------------------
# Tier 2b — _is_argcomplete_completion_active (line 80-86 in __main__.py)
# ---------------------------------------------------------------------------


class TestIsArgcompleteCompletionActive:
    """Test _is_argcomplete_completion_active edge cases."""

    def test_not_set(self) -> None:
        from cja_auto_sdr.__main__ import _is_argcomplete_completion_active

        assert _is_argcomplete_completion_active({}) is False

    def test_set_truthy(self) -> None:
        from cja_auto_sdr.__main__ import _is_argcomplete_completion_active

        assert _is_argcomplete_completion_active({"_ARGCOMPLETE": "1"}) is True

    def test_set_falsey(self) -> None:
        from cja_auto_sdr.__main__ import _is_argcomplete_completion_active

        assert _is_argcomplete_completion_active({"_ARGCOMPLETE": "0"}) is False
        assert _is_argcomplete_completion_active({"_ARGCOMPLETE": ""}) is False
        assert _is_argcomplete_completion_active({"_ARGCOMPLETE": "false"}) is False


# ---------------------------------------------------------------------------
# Tier 2b — _accepts_inline_option_value (line 91 in __main__.py)
# ---------------------------------------------------------------------------


class TestAcceptsInlineOptionValue:
    """Test _accepts_inline_option_value."""

    def test_zero_nargs(self) -> None:
        from cja_auto_sdr.__main__ import _accepts_inline_option_value

        assert _accepts_inline_option_value(0) is False

    def test_nonzero_nargs(self) -> None:
        from cja_auto_sdr.__main__ import _accepts_inline_option_value

        assert _accepts_inline_option_value(1) is True
        assert _accepts_inline_option_value(None) is True
        assert _accepts_inline_option_value("?") is True


# ---------------------------------------------------------------------------
# v3.4.5 coverage gap tests (moved from test_v345_coverage_gaps.py)
# ---------------------------------------------------------------------------


class TestPromptForSelectionKeyboardInterrupt:
    """Lines 58-60: KeyboardInterrupt during input returns None."""

    def test_keyboard_interrupt_returns_none(self) -> None:
        from cja_auto_sdr.cli.interactive import prompt_for_selection

        options = [("id1", "Option 1"), ("id2", "Option 2")]
        with patch("builtins.input", side_effect=KeyboardInterrupt):
            result = prompt_for_selection(options, "Pick one:")
        assert result is None

    def test_keyboard_interrupt_on_tty_returns_none(self) -> None:
        """Lines 56-58: with a TTY, the input loop is entered and a
        KeyboardInterrupt during ``input()`` returns None via the handler."""
        from cja_auto_sdr.cli.interactive import prompt_for_selection

        options = [("id1", "Option 1"), ("id2", "Option 2")]
        with (
            patch("sys.stdin") as mock_stdin,
            patch("builtins.input", side_effect=KeyboardInterrupt),
        ):
            mock_stdin.isatty.return_value = True
            result = prompt_for_selection(options, "Pick one:")
        assert result is None
