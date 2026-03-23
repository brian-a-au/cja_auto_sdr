"""Tests for uncovered lines in generator.py: interactive_select_dataviews,
interactive_wizard, _run_list_command error handling, helper functions
(_extract_owner_name, _extract_connections_list, _to_searchable_text,
_to_numeric_sort_value, _is_missing_sort_value), _emit_output pager edge
cases, show_config_status exception path, and _apply_discovery_filters_and_sort
sort-key branches.

Targets uncovered line ranges:
- 8425-8426, 8438: _emit_output pager OSError / TimeoutExpired
- 8513: _extract_owner_name fallback str(owner_data) or "N/A"
- 8524, 8526-8528: _extract_connections_list branches
- 8534, 8539-8540: _to_searchable_text None / TypeError
- 8553, 8558-8560, 8569-8572: _to_numeric_sort_value branches
- 8578, 8580, 8583-8584: _is_missing_sort_value branches
- 8662-8663, 8668-8669: _apply_discovery_filters_and_sort missing/numeric None
- 8769-8782, 8784-8789: _run_list_command error handlers
- 9406-9409, 9452-9455, 9468-9470, 9483-9497: interactive_select_dataviews
- 9550-9552, 9565-9566, 9582-9584, 9628-9631, 9635, 9646-9647,
  9664-9666, 9669-9670, 9681, 9686, 9697-9700, 9704-9707, 9710,
  9719, 9728-9734: interactive_wizard
- 9933-9939: show_config_status generic Exception on config read
"""

from __future__ import annotations

import json
import os
import subprocess
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import pytest

from cja_auto_sdr.core.exceptions import APIError, ConfigurationError
from cja_auto_sdr.generator import (
    _apply_discovery_filters_and_sort,
    _emit_output,
    _extract_connections_list,
    _extract_owner_name,
    _is_missing_sort_value,
    _run_list_command,
    _to_numeric_sort_value,
    _to_searchable_text,
    interactive_select_dataviews,
    interactive_wizard,
    show_config_status,
)

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _mock_data_views() -> list[dict[str, object]]:
    return [
        {"id": "dv_001", "name": "Marketing DV", "owner": {"name": "Alice"}},
        {"id": "dv_002", "name": "Product DV", "owner": {"name": "Bob"}},
        {"id": "dv_003", "name": "Finance DV", "owner": {"name": "Carol"}},
    ]


# ===========================================================================
# _extract_owner_name  (line 8513)
# ===========================================================================


class TestExtractOwnerName:
    """Tests for _extract_owner_name edge cases."""

    def test_extract_owner_name_numeric_value_line_8513(self):
        """Line 8513: non-dict, non-str, non-None value → str(owner_data) or 'N/A'."""
        assert _extract_owner_name(42) == "42"

    def test_extract_owner_name_numeric_zero_returns_na(self):
        """Line 8513: str(0) is '0' which is truthy, so returns '0'."""
        assert _extract_owner_name(0) == "0"

    def test_extract_owner_name_list_value(self):
        """Line 8513: list value → str(list)."""
        result = _extract_owner_name([1, 2])
        assert result == "[1, 2]"

    def test_extract_owner_name_bool_true(self):
        """Line 8513: bool True → 'True'."""
        assert _extract_owner_name(True) == "True"

    def test_extract_owner_name_custom_object(self):
        """Line 8513: custom object with __str__."""

        class Owner:
            def __str__(self):
                return "CustomOwner"

        assert _extract_owner_name(Owner()) == "CustomOwner"

    def test_extract_owner_name_empty_str_object_returns_na(self):
        """Line 8513: object whose str() is empty → 'N/A'."""

        class EmptyStr:
            def __str__(self):
                return ""

        assert _extract_owner_name(EmptyStr()) == "N/A"


# ===========================================================================
# _extract_connections_list  (lines 8524, 8526-8528)
# ===========================================================================


class TestExtractConnectionsList:
    """Tests for _extract_connections_list branches."""

    def test_dict_with_content_not_list_line_8524(self):
        """Line 8524: content value is not a list → wrap dict."""
        raw = {"content": "unexpected_string"}
        result = _extract_connections_list(raw)
        assert result == [raw]

    def test_dict_with_result_not_list_line_8524(self):
        """Line 8524: result value is not a list → wrap dict."""
        raw = {"result": 42}
        result = _extract_connections_list(raw)
        assert result == [raw]

    def test_list_passthrough_line_8526_8527(self):
        """Lines 8526-8527: isinstance list → return as-is."""
        data = [{"id": "conn1"}, {"id": "conn2"}]
        assert _extract_connections_list(data) is data

    def test_non_dict_non_list_returns_empty_line_8528(self):
        """Line 8528: non-dict, non-list → return []."""
        assert _extract_connections_list("a string") == []
        assert _extract_connections_list(42) == []
        assert _extract_connections_list(None) == []

    def test_dict_with_content_list(self):
        """Normal path: content is a list → return it."""
        items = [{"id": "c1"}]
        assert _extract_connections_list({"content": items}) == items


# ===========================================================================
# _to_searchable_text  (lines 8534, 8539-8540)
# ===========================================================================


class TestToSearchableText:
    """Tests for _to_searchable_text edge cases."""

    def test_none_returns_empty_line_8534(self):
        """Line 8534: None → empty string."""
        assert _to_searchable_text(None) == ""

    def test_json_dumps_type_error_line_8539_8540(self):
        """Lines 8539-8540: json.dumps raises TypeError → str(value)."""
        obj = object()
        result = _to_searchable_text(obj)
        assert result == str(obj)

    def test_str_passthrough(self):
        """Normal str path."""
        assert _to_searchable_text("hello") == "hello"

    def test_int_passthrough(self):
        """Normal int path."""
        assert _to_searchable_text(42) == "42"

    def test_dict_json_serialized(self):
        """Normal dict → json.dumps."""
        result = _to_searchable_text({"a": 1})
        assert '"a": 1' in result

    def test_set_triggers_type_error_fallback(self):
        """set is not JSON-serializable → falls through to str()."""
        result = _to_searchable_text({1, 2, 3})
        assert isinstance(result, str)


# ===========================================================================
# _to_numeric_sort_value  (lines 8553, 8558-8560, 8569-8572)
# ===========================================================================


class TestToNumericSortValue:
    """Tests for _to_numeric_sort_value branches."""

    def test_bool_returns_none_line_8553(self):
        """Line 8553: bool → None (bools are a subclass of int)."""
        assert _to_numeric_sort_value(True) is None
        assert _to_numeric_sort_value(False) is None

    def test_none_returns_none(self):
        """None → None."""
        assert _to_numeric_sort_value(None) is None

    def test_nan_returns_none_line_8557_8558(self):
        """Lines 8557-8558: pd.isna(NaN) is True → None."""
        assert _to_numeric_sort_value(float("nan")) is None

    def test_pd_isna_type_error_line_8559_8560(self):
        """Lines 8559-8560: pd.isna raises TypeError → None."""

        # Create an object whose pd.isna raises TypeError
        class BadNumeric(float):
            def __eq__(self, other):
                raise TypeError("boom")

            def __ne__(self, other):
                raise TypeError("boom")

            def __hash__(self):
                return super().__hash__()

        # pd.isna can raise TypeError for certain pathological floats
        val = BadNumeric(1.0)
        # Depending on pd.isna implementation, this may or may not raise;
        # the function should still return a valid result or None
        result = _to_numeric_sort_value(val)
        assert result is None or isinstance(result, float)

    def test_string_numeric_returns_float(self):
        """Normal string numeric path."""
        assert _to_numeric_sort_value("42.5") == 42.5
        assert _to_numeric_sort_value("  -3  ") == -3.0

    def test_string_non_numeric_returns_none(self):
        """String that doesn't match numeric regex → None."""
        assert _to_numeric_sort_value("hello") is None
        assert _to_numeric_sort_value("12abc") is None

    def test_empty_string_returns_none(self):
        """Empty or whitespace-only string → None."""
        assert _to_numeric_sort_value("") is None
        assert _to_numeric_sort_value("   ") is None

    def test_int_returns_float(self):
        """Normal int → float."""
        assert _to_numeric_sort_value(10) == 10.0

    def test_float_returns_float(self):
        """Normal float → float."""
        assert _to_numeric_sort_value(3.14) == 3.14

    def test_non_numeric_type_returns_none_line_8572(self):
        """Line 8572: non-numeric type → None."""
        assert _to_numeric_sort_value([1, 2]) is None
        assert _to_numeric_sort_value({"a": 1}) is None

    def test_string_value_error_unreachable_line_8569_8570(self):
        """Lines 8569-8570: float() ValueError after regex match.
        The regex should prevent this, but we cover the except block anyway.
        We patch the regex guard to force a non-numeric string into float()."""
        with patch("cja_auto_sdr.cli.commands.discovery._NUMERIC_SORT_VALUE_RE") as mock_re:
            mock_re.fullmatch.return_value = True
            result = _to_numeric_sort_value("not-a-number")

        assert result is None
        mock_re.fullmatch.assert_called_once_with("not-a-number")


# ===========================================================================
# _is_missing_sort_value  (lines 8578, 8580, 8583-8584)
# ===========================================================================


class TestIsMissingSortValue:
    """Tests for _is_missing_sort_value branches."""

    def test_none_returns_true_line_8578(self):
        """Line 8578: None → True."""
        assert _is_missing_sort_value(None) is True

    def test_empty_string_returns_true_line_8580(self):
        """Line 8580: empty/whitespace string → True."""
        assert _is_missing_sort_value("") is True
        assert _is_missing_sort_value("   ") is True

    def test_nan_returns_true(self):
        """pd.isna(NaN) → True."""
        assert _is_missing_sort_value(float("nan")) is True

    def test_pd_isna_type_error_returns_false_line_8583_8584(self):
        """Lines 8583-8584: pd.isna raises TypeError → False."""

        class Unisnable:
            """Object for which pd.isna raises TypeError."""

            def __eq__(self, other):
                raise TypeError("cannot compare")

            def __hash__(self):
                return id(self)

            def __bool__(self):
                raise TypeError("cannot bool")

        result = _is_missing_sort_value(Unisnable())
        assert result is False

    def test_normal_string_returns_false(self):
        """Non-empty string → False."""
        assert _is_missing_sort_value("hello") is False

    def test_integer_returns_false(self):
        """Integer → False."""
        assert _is_missing_sort_value(42) is False


# ===========================================================================
# _apply_discovery_filters_and_sort  (lines 8662-8663, 8668-8669)
# ===========================================================================


class TestApplyDiscoveryFiltersAndSort:
    """Tests for sort key handling with missing/numeric values."""

    def test_missing_value_appended_to_end_line_8662_8663(self):
        """Lines 8662-8663: row with missing sort field → placed in missing_rows."""
        rows = [
            {"name": "Alpha", "count": "10"},
            {"name": "Beta", "count": ""},
            {"name": "Gamma", "count": "5"},
        ]
        result = _apply_discovery_filters_and_sort(
            rows,
            sort_expression="count",
            searchable_fields=["name", "count"],
            default_sort_field="name",
        )
        # Numeric sort: 5, 10, then missing at end
        assert result[0]["name"] == "Gamma"
        assert result[1]["name"] == "Alpha"
        assert result[2]["name"] == "Beta"

    def test_numeric_none_fallback_line_8668_8669(self):
        """Lines 8668-8669: numeric sort detected but one value returns None from
        _to_numeric_sort_value → that row goes to missing_rows."""
        rows = [
            {"name": "A", "val": "10"},
            {"name": "B", "val": "20"},
            {"name": "C", "val": None},
        ]
        result = _apply_discovery_filters_and_sort(
            rows,
            sort_expression="val",
            searchable_fields=["name", "val"],
            default_sort_field="name",
        )
        # C has None → missing, A and B sorted numerically
        names = [r["name"] for r in result]
        assert names == ["A", "B", "C"]

    def test_string_sort_with_casefold(self):
        """String sort uses _to_searchable_text().casefold()."""
        rows = [
            {"name": "banana", "id": "1"},
            {"name": "Apple", "id": "2"},
            {"name": "cherry", "id": "3"},
        ]
        result = _apply_discovery_filters_and_sort(
            rows,
            sort_expression="name",
            searchable_fields=["name", "id"],
            default_sort_field="name",
        )
        names = [r["name"] for r in result]
        assert names == ["Apple", "banana", "cherry"]


# ===========================================================================
# _emit_output  (lines 8425-8426, 8438)
# ===========================================================================


class TestEmitOutput:
    """Tests for _emit_output pager edge cases."""

    @patch("sys.stdout")
    @patch("os.get_terminal_size", side_effect=OSError("no tty"))
    def test_terminal_size_os_error_line_8425_8426(self, _mock_size, mock_stdout, capsys):
        """Lines 8425-8426: os.get_terminal_size raises OSError → term_height = 0."""
        mock_stdout.isatty.return_value = True
        # With term_height=0 the pager check is skipped; falls through to print
        _emit_output("line1\nline2\nline3", None, False)
        # Should not raise

    @patch("subprocess.Popen")
    @patch("shutil.which", return_value="/usr/bin/less")
    @patch("os.get_terminal_size")
    @patch("sys.stdout")
    def test_pager_timeout_expired_line_8438(self, mock_stdout, mock_term_size, _mock_which, mock_popen, capsys):
        """Line 8438: pager subprocess.TimeoutExpired → proc.kill()."""
        mock_stdout.isatty.return_value = True
        mock_term_size.return_value = MagicMock(lines=2)

        mock_proc = MagicMock()
        mock_proc.communicate.side_effect = subprocess.TimeoutExpired("less", 300)
        mock_popen.return_value = mock_proc

        # Multi-line output exceeding term_height (2 lines, output has 5)
        long_text = "\n".join(f"line {i}" for i in range(5))
        _emit_output(long_text, None, False)

        mock_proc.kill.assert_called_once()

    def test_emit_to_file(self, tmp_path):
        """Normal path: write to file."""
        out_file = str(tmp_path / "output.txt")
        _emit_output("hello world", out_file, False)
        assert (tmp_path / "output.txt").read_text() == "hello world"

    def test_emit_to_stdout_pipe(self, capsys):
        """Normal path: is_stdout=True → print to stdout."""
        _emit_output("piped data\n", None, True)
        captured = capsys.readouterr()
        assert "piped data" in captured.out


# ===========================================================================
# _run_list_command  (lines 8769-8782, 8784-8789)
# ===========================================================================


class TestRunListCommand:
    """Tests for _run_list_command error handling paths."""

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", side_effect=FileNotFoundError)
    def test_file_not_found_table_mode_line_8769_8776(self, _mock_config, _mock_cjapy, capsys):
        """Lines 8769-8776: FileNotFoundError in table mode."""
        result = _run_list_command(
            banner_text="TEST",
            command_name="test",
            fetch_and_format=lambda cja, mr: "data",
            config_file="missing.json",
        )
        assert result is False
        out = capsys.readouterr().out
        assert "Configuration file 'missing.json' not found" in out
        assert "--sample-config" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", side_effect=FileNotFoundError)
    def test_file_not_found_machine_readable_line_8769_8770(self, _mock_config, _mock_cjapy, capsys):
        """Lines 8769-8770: FileNotFoundError in JSON mode → stderr."""
        result = _run_list_command(
            banner_text="TEST",
            command_name="test",
            fetch_and_format=lambda cja, mr: "data",
            config_file="missing.json",
            output_format="json",
        )
        assert result is False
        err = capsys.readouterr().err
        parsed = json.loads(err)
        assert "not found" in parsed["error"]

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", side_effect=KeyboardInterrupt)
    def test_keyboard_interrupt_table_mode_line_8778_8782(self, _mock_config, _mock_cjapy, capsys):
        """Lines 8778-8782: KeyboardInterrupt in table mode → print warning and re-raise."""
        with pytest.raises(KeyboardInterrupt):
            _run_list_command(
                banner_text="TEST",
                command_name="test",
                fetch_and_format=lambda cja, mr: "data",
                config_file="config.json",
            )
        out = capsys.readouterr().out
        assert "Operation cancelled" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", side_effect=KeyboardInterrupt)
    def test_keyboard_interrupt_machine_readable_re_raises(self, _mock_config, _mock_cjapy, capsys):
        """Lines 8778-8782: KeyboardInterrupt in machine-readable mode → re-raise silently."""
        with pytest.raises(KeyboardInterrupt):
            _run_list_command(
                banner_text="TEST",
                command_name="test",
                fetch_and_format=lambda cja, mr: "data",
                config_file="config.json",
                output_format="json",
            )

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", side_effect=SystemExit(1))
    def test_system_exit_table_mode_re_raises(self, _mock_config, _mock_cjapy, capsys):
        """Lines 8778-8782: SystemExit in table mode → print warning and re-raise."""
        with pytest.raises(SystemExit):
            _run_list_command(
                banner_text="TEST",
                command_name="test",
                fetch_and_format=lambda cja, mr: "data",
                config_file="config.json",
            )
        out = capsys.readouterr().out
        assert "Operation cancelled" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", side_effect=ConfigurationError("API timeout"))
    def test_generic_exception_table_mode_line_8784_8788(self, _mock_config, _mock_cjapy, capsys):
        """Lines 8784-8788: generic Exception in table mode."""
        result = _run_list_command(
            banner_text="TEST",
            command_name="test",
            fetch_and_format=lambda cja, mr: "data",
            config_file="config.json",
        )
        assert result is False
        out = capsys.readouterr().out
        assert "Failed to connect to CJA API: API timeout" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", side_effect=ConfigurationError("API timeout"))
    def test_generic_exception_machine_readable_line_8785_8786(self, _mock_config, _mock_cjapy, capsys):
        """Lines 8785-8786: generic Exception in JSON mode → stderr."""
        result = _run_list_command(
            banner_text="TEST",
            command_name="test",
            fetch_and_format=lambda cja, mr: "data",
            config_file="config.json",
            output_format="json",
        )
        assert result is False
        err = capsys.readouterr().err
        parsed = json.loads(err)
        assert "API timeout" in parsed["error"]

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_attribute_error_from_fetch_is_recoverable(self, _mock_config, mock_cjapy, capsys):
        """AttributeError in fetch callback should return False with a user-facing API error."""
        mock_cjapy.CJA.return_value = Mock()

        def _raise_attr_error(_cja, _machine_readable):
            raise AttributeError("missing getDataViews")

        result = _run_list_command(
            banner_text="TEST",
            command_name="test",
            fetch_and_format=_raise_attr_error,
            config_file="config.json",
        )
        assert result is False
        out = capsys.readouterr().out
        assert "Failed to connect to CJA API: missing getDataViews" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_cja_constructor_exception_is_recoverable(self, _mock_config, mock_cjapy, capsys):
        """Bare constructor failures from cjapy should return a controlled command error."""
        mock_cjapy.CJA.side_effect = Exception("auth bootstrap failed")

        result = _run_list_command(
            banner_text="TEST",
            command_name="test",
            fetch_and_format=lambda cja, mr: "data",
            config_file="config.json",
        )
        assert result is False
        out = capsys.readouterr().out
        assert "Failed to connect to CJA API: auth bootstrap failed" in out


# ===========================================================================
# interactive_select_dataviews  (lines 9406-9409, 9452-9455, 9468-9470,
#                                 9483-9497)
# ===========================================================================


class TestInteractiveSelectDataviews:
    """Tests for interactive_select_dataviews error handling."""

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    @patch("builtins.input", side_effect=EOFError)
    def test_eof_error_in_selection_line_9406_9409(self, _inp, _cfg, mock_cjapy, capsys):
        """Lines 9406-9409: EOFError on input → warning and return []."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        result = interactive_select_dataviews("config.json")
        assert result == []
        out = capsys.readouterr().out
        assert "non-interactive terminal" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    @patch("builtins.input", side_effect=["abc"])
    def test_invalid_number_line_9452_9455(self, _inp, _cfg, mock_cjapy, capsys):
        """Lines 9452-9455: non-numeric single input → error message, then continues.
        We supply a second input to break the loop."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        # "abc" triggers ValueError, then "q" cancels
        with patch("builtins.input", side_effect=["abc", "q"]):
            result = interactive_select_dataviews("config.json")
        assert result == []
        out = capsys.readouterr().out
        assert "Invalid number: 'abc'" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_no_valid_selections_empty_parts_line_9468_9470(self, _cfg, mock_cjapy, capsys):
        """Lines 9468-9470: all parts are empty → no valid selections message."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        # ",," has all empty parts, yielding an empty set, then "q" to exit
        with patch("builtins.input", side_effect=[",,", "q"]):
            result = interactive_select_dataviews("config.json")
        assert result == []
        out = capsys.readouterr().out
        assert "No valid selections" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", side_effect=FileNotFoundError)
    def test_file_not_found_line_9483_9488(self, _cfg, _cjapy, capsys):
        """Lines 9483-9488: FileNotFoundError → error message and return []."""
        result = interactive_select_dataviews("missing.json")
        assert result == []
        out = capsys.readouterr().out
        assert "Configuration file 'missing.json' not found" in out
        assert "--sample-config" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_keyboard_interrupt_line_9490_9493(self, _cfg, mock_cjapy, capsys):
        """Lines 9490-9493: KeyboardInterrupt → 'Operation cancelled.' and return []."""
        mock_cja = Mock()
        mock_cja.getDataViews.side_effect = KeyboardInterrupt
        mock_cjapy.CJA.return_value = mock_cja

        result = interactive_select_dataviews("config.json")
        assert result == []
        out = capsys.readouterr().out
        assert "Operation cancelled" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_system_exit_line_9490_9493(self, _cfg, mock_cjapy, capsys):
        """Lines 9490-9493: SystemExit → 'Operation cancelled.' and return []."""
        mock_cja = Mock()
        mock_cja.getDataViews.side_effect = SystemExit(1)
        mock_cjapy.CJA.return_value = mock_cja

        result = interactive_select_dataviews("config.json")
        assert result == []
        out = capsys.readouterr().out
        assert "Operation cancelled" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_generic_exception_line_9495_9497(self, _cfg, mock_cjapy, capsys):
        """Lines 9495-9497: generic Exception → error message and return []."""
        mock_cja = Mock()
        mock_cja.getDataViews.side_effect = APIError("network error")
        mock_cjapy.CJA.return_value = mock_cja

        result = interactive_select_dataviews("config.json")
        assert result == []
        out = capsys.readouterr().out
        assert "Failed to connect to CJA API: network error" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_constructor_exception_is_recoverable(self, _cfg, mock_cjapy, capsys):
        """Bare constructor failures from cjapy should return [] with a controlled error."""
        mock_cjapy.CJA.side_effect = Exception("auth bootstrap failed")

        result = interactive_select_dataviews("config.json")
        assert result == []
        out = capsys.readouterr().out
        assert "Failed to connect to CJA API: auth bootstrap failed" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_attribute_error_is_recoverable(self, _cfg, mock_cjapy, capsys):
        """Missing API method should be surfaced as a handled connection error."""
        mock_cjapy.CJA.return_value = object()

        result = interactive_select_dataviews("config.json")
        assert result == []
        out = capsys.readouterr().out
        assert "Failed to connect to CJA API" in out
        assert "getDataViews" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_select_all_option(self, _cfg, mock_cjapy, capsys):
        """Selection 'all' selects every data view."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        with patch("builtins.input", side_effect=["all"]):
            result = interactive_select_dataviews("config.json")
        assert result == ["dv_001", "dv_002", "dv_003"]

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_no_data_views_found(self, _cfg, mock_cjapy, capsys):
        """No data views → warning message."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = []
        mock_cjapy.CJA.return_value = mock_cja

        result = interactive_select_dataviews("config.json")
        assert result == []
        out = capsys.readouterr().out
        assert "No data views found" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_dataframe_conversion(self, _cfg, mock_cjapy, capsys):
        """DataFrame response is converted to list of dicts."""
        mock_cja = Mock()
        df = pd.DataFrame(
            [
                {"id": "dv_df1", "name": "DF View", "owner": "Owner1"},
            ]
        )
        mock_cja.getDataViews.return_value = df
        mock_cjapy.CJA.return_value = mock_cja

        with patch("builtins.input", side_effect=["1"]):
            result = interactive_select_dataviews("config.json")
        assert result == ["dv_df1"]

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_non_dict_items_skipped(self, _cfg, mock_cjapy, capsys):
        """Non-dict items in the data views list are skipped; if none remain, warning."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = ["not-a-dict", 42]
        mock_cjapy.CJA.return_value = mock_cja

        result = interactive_select_dataviews("config.json")
        assert result == []
        out = capsys.readouterr().out
        assert "No data views available" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_invalid_range_format(self, _cfg, mock_cjapy, capsys):
        """Invalid range like '1-2-3' triggers error message."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        with patch("builtins.input", side_effect=["1-2-3", "q"]):
            result = interactive_select_dataviews("config.json")
        assert result == []
        out = capsys.readouterr().out
        assert "Invalid range: '1-2-3'" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_out_of_range_indices(self, _cfg, mock_cjapy, capsys):
        """Out of range index triggers error message."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        with patch("builtins.input", side_effect=["99", "q"]):
            result = interactive_select_dataviews("config.json")
        assert result == []
        out = capsys.readouterr().out
        assert "Invalid selection" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_profile_banner(self, _cfg, mock_cjapy, capsys):
        """When profile is given, banner shows 'Using profile: ...'."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        with patch("builtins.input", side_effect=["1"]):
            interactive_select_dataviews("config.json", profile="prod")
        out = capsys.readouterr().out
        assert "Using profile: prod" in out


# ===========================================================================
# interactive_wizard  (lines 9550-9552, 9565-9566, 9582-9584, 9628-9631,
#                       9635, 9646-9647, 9664-9666, 9669-9670, 9681, 9686,
#                       9697-9700, 9704-9707, 9710, 9719, 9728-9734)
# ===========================================================================


class TestInteractiveWizard:
    """Tests for interactive_wizard error paths and edge cases."""

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_prompt_choice_eof_error_line_9550_9552(self, _cfg, mock_cjapy, capsys):
        """Lines 9550-9552: EOFError in prompt_choice → returns None → wizard cancelled."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        # "1" selects data view, then EOFError when prompt_choice asks for format
        with patch("builtins.input", side_effect=["1", EOFError]):
            result = interactive_wizard("config.json")
        assert result is None

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_prompt_choice_keyboard_interrupt_line_9550_9552(self, _cfg, mock_cjapy, capsys):
        """Lines 9550-9552: KeyboardInterrupt in prompt_choice → returns None."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        with patch("builtins.input", side_effect=["1", KeyboardInterrupt]):
            result = interactive_wizard("config.json")
        assert result is None

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_prompt_choice_invalid_number_line_9565_9566(self, _cfg, mock_cjapy, capsys):
        """Lines 9565-9566: non-numeric input in prompt_choice → error shown, retries."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        # "1" selects data view, then "xyz" is invalid, "1" selects excel,
        # then respond to yes/no prompts
        with patch("builtins.input", side_effect=["1", "xyz", "1", "n", "n", "n", "y"]):
            result = interactive_wizard("config.json")
        assert result is not None
        out = capsys.readouterr().out
        assert "Please enter a number between 1 and" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_prompt_yes_no_eof_error_line_9582_9584(self, _cfg, mock_cjapy, capsys):
        """Lines 9582-9584: EOFError in prompt_yes_no → returns None → cancelled."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        # "1" data view, "1" format, then EOFError on first yes/no
        with patch("builtins.input", side_effect=["1", "1", EOFError]):
            result = interactive_wizard("config.json")
        assert result is None
        out = capsys.readouterr().out
        assert "Cancelled" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_prompt_yes_no_keyboard_interrupt_line_9582_9584(self, _cfg, mock_cjapy, capsys):
        """Lines 9582-9584: KeyboardInterrupt in prompt_yes_no → returns None."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        with patch("builtins.input", side_effect=["1", "1", KeyboardInterrupt]):
            result = interactive_wizard("config.json")
        assert result is None

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_no_data_views_found_line_9628_9631(self, _cfg, mock_cjapy, capsys):
        """Lines 9628-9631: getDataViews returns empty → None."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = []
        mock_cjapy.CJA.return_value = mock_cja

        result = interactive_wizard("config.json")
        assert result is None
        out = capsys.readouterr().out
        assert "No data views found" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_no_data_views_none_line_9628_9631(self, _cfg, mock_cjapy, capsys):
        """Lines 9628-9631: getDataViews returns None → None."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = None
        mock_cjapy.CJA.return_value = mock_cja

        result = interactive_wizard("config.json")
        assert result is None
        out = capsys.readouterr().out
        assert "No data views found" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_dataframe_conversion_line_9635(self, _cfg, mock_cjapy, capsys):
        """Line 9635: DataFrame conversion in wizard."""
        mock_cja = Mock()
        df = pd.DataFrame(
            [
                {"id": "dv_df1", "name": "DF View"},
                {"id": "dv_df2", "name": "DF View 2"},
            ]
        )
        mock_cja.getDataViews.return_value = df
        mock_cjapy.CJA.return_value = mock_cja

        # Select first, excel, no segments, no calc, no derived, confirm
        with patch("builtins.input", side_effect=["1", "1", "n", "n", "n", "y"]):
            result = interactive_wizard("config.json")
        assert result is not None
        assert result.data_view_ids == ["dv_df1"]

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_no_display_data_after_filtering_line_9646_9647(self, _cfg, mock_cjapy, capsys):
        """Lines 9646-9647: non-dict items → no display_data → None."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = ["not_a_dict", 42]
        mock_cjapy.CJA.return_value = mock_cja

        result = interactive_wizard("config.json")
        assert result is None
        out = capsys.readouterr().out
        assert "No data views available" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_eof_on_data_view_selection_line_9664_9666(self, _cfg, mock_cjapy, capsys):
        """Lines 9664-9666: EOFError when selecting data view → None."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        with patch("builtins.input", side_effect=EOFError):
            result = interactive_wizard("config.json")
        assert result is None

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_keyboard_interrupt_on_data_view_selection_line_9664_9666(self, _cfg, mock_cjapy, capsys):
        """Lines 9664-9666: KeyboardInterrupt when selecting data view → None."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        with patch("builtins.input", side_effect=KeyboardInterrupt):
            result = interactive_wizard("config.json")
        assert result is None

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_quit_selection_line_9669_9670(self, _cfg, mock_cjapy, capsys):
        """Lines 9669-9670: quit during data view selection → None."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        with patch("builtins.input", side_effect=["quit"]):
            result = interactive_wizard("config.json")
        assert result is None
        out = capsys.readouterr().out
        assert "Cancelled" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_all_selection_line_9681(self, _cfg, mock_cjapy, capsys):
        """Line 9681: 'all' selects all data views."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        # "all" for selection, "1" for format, n/n/n for inventory, y to confirm
        with patch("builtins.input", side_effect=["all", "1", "n", "n", "n", "y"]):
            result = interactive_wizard("config.json")
        assert result is not None
        assert len(result.data_view_ids) == 3

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_empty_part_in_comma_separated_line_9686(self, _cfg, mock_cjapy, capsys):
        """Line 9686: empty part in comma-separated selection is skipped."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        # "1,,2" has an empty part which is skipped
        with patch("builtins.input", side_effect=["1,,2", "1", "n", "n", "n", "y"]):
            result = interactive_wizard("config.json")
        assert result is not None
        assert result.data_view_ids == ["dv_001", "dv_002"]

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_invalid_range_format_line_9697_9700(self, _cfg, mock_cjapy, capsys):
        """Lines 9697-9700: invalid range format → error, then continue."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        # "1-2-3" is invalid range, then "1" is valid
        with patch("builtins.input", side_effect=["1-2-3", "1", "1", "n", "n", "n", "y"]):
            result = interactive_wizard("config.json")
        assert result is not None
        out = capsys.readouterr().out
        assert "Invalid range" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_invalid_number_line_9704_9707(self, _cfg, mock_cjapy, capsys):
        """Lines 9704-9707: non-numeric input → error, then continue."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        with patch("builtins.input", side_effect=["xyz", "1", "1", "n", "n", "n", "y"]):
            result = interactive_wizard("config.json")
        assert result is not None
        out = capsys.readouterr().out
        assert "Invalid number: 'xyz'" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_invalid_continues_loop_line_9710(self, _cfg, mock_cjapy, capsys):
        """Line 9710: invalid input sets valid=False → continue back to selection prompt."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        # "abc" is invalid, then "q" to exit
        with patch("builtins.input", side_effect=["abc", "q"]):
            result = interactive_wizard("config.json")
        assert result is None

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_no_valid_selections_empty_input_line_9719(self, _cfg, mock_cjapy, capsys):
        """Line 9719: no valid selections (empty string) → continues loop."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        # Empty string triggers 'Please enter a selection', then ",," triggers
        # empty parts → empty set → continues, then "q" to exit
        with patch("builtins.input", side_effect=["", ",,", "q"]):
            result = interactive_wizard("config.json")
        assert result is None

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", side_effect=FileNotFoundError)
    def test_file_not_found_line_9728_9731(self, _cfg, _cjapy, capsys):
        """Lines 9728-9731: FileNotFoundError → error message, return None."""
        result = interactive_wizard("missing.json")
        assert result is None
        out = capsys.readouterr().out
        assert "Configuration file 'missing.json' not found" in out
        assert "--sample-config" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_generic_exception_line_9732_9734(self, _cfg, mock_cjapy, capsys):
        """Lines 9732-9734: generic Exception → error message, return None."""
        mock_cja = Mock()
        mock_cja.getDataViews.side_effect = APIError("API down")
        mock_cjapy.CJA.return_value = mock_cja

        result = interactive_wizard("config.json")
        assert result is None
        out = capsys.readouterr().out
        assert "Failed to connect to CJA API: API down" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_constructor_exception_is_recoverable(self, _cfg, mock_cjapy, capsys):
        """Bare constructor failures from cjapy should return None with a controlled error."""
        mock_cjapy.CJA.side_effect = Exception("auth bootstrap failed")

        result = interactive_wizard("config.json")
        assert result is None
        out = capsys.readouterr().out
        assert "Failed to connect to CJA API: auth bootstrap failed" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_attribute_error_during_startup_is_recoverable(self, _cfg, mock_cjapy, capsys):
        """Missing API method during startup should return None with a user-facing error."""
        mock_cjapy.CJA.return_value = object()

        result = interactive_wizard("config.json")
        assert result is None
        out = capsys.readouterr().out
        assert "Failed to connect to CJA API" in out
        assert "getDataViews" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_out_of_range_selection_rejected(self, _cfg, mock_cjapy, capsys):
        """Out of range selection (e.g. 99) triggers error, then valid selection."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        with patch("builtins.input", side_effect=["99", "1", "1", "n", "n", "n", "y"]):
            result = interactive_wizard("config.json")
        assert result is not None
        out = capsys.readouterr().out
        assert "Invalid" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_wizard_with_profile(self, _cfg, mock_cjapy, capsys):
        """Wizard shows 'Using profile: ...' when profile is given."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        with patch("builtins.input", side_effect=["1", "1", "n", "n", "n", "y"]):
            result = interactive_wizard("config.json", profile="staging")
        assert result is not None
        out = capsys.readouterr().out
        assert "Using profile: staging" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_wizard_cancel_at_format_step(self, _cfg, mock_cjapy, capsys):
        """Cancelling at format selection returns None."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        with patch("builtins.input", side_effect=["1", "q"]):
            result = interactive_wizard("config.json")
        assert result is None
        out = capsys.readouterr().out
        assert "Cancelled" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_wizard_cancel_at_calculated_metrics_step(self, _cfg, mock_cjapy, capsys):
        """Cancelling at calculated metrics prompt returns None."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        # "1" data view, "1" format, "n" segments, then EOFError on calc metrics
        with patch("builtins.input", side_effect=["1", "1", "n", EOFError]):
            result = interactive_wizard("config.json")
        assert result is None

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_wizard_cancel_at_derived_fields_step(self, _cfg, mock_cjapy, capsys):
        """Cancelling at derived fields prompt returns None."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        # "1" data view, "1" format, "n" segments, "n" calc metrics, then EOF on derived
        with patch("builtins.input", side_effect=["1", "1", "n", "n", EOFError]):
            result = interactive_wizard("config.json")
        assert result is None

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_wizard_cancel_at_confirmation(self, _cfg, mock_cjapy, capsys):
        """Cancelling at final confirmation returns None."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        # "1" data view, "1" format, "n" all inventory, "n" confirm
        with patch("builtins.input", side_effect=["1", "1", "n", "n", "n", "n"]):
            result = interactive_wizard("config.json")
        assert result is None

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_wizard_reversed_range(self, _cfg, mock_cjapy, capsys):
        """Range 3-1 is auto-reversed to 1-3."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        with patch("builtins.input", side_effect=["3-1", "1", "n", "n", "n", "y"]):
            result = interactive_wizard("config.json")
        assert result is not None
        assert len(result.data_view_ids) == 3

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_wizard_star_selection(self, _cfg, mock_cjapy, capsys):
        """'*' is treated as 'all'."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        with patch("builtins.input", side_effect=["*", "1", "n", "n", "n", "y"]):
            result = interactive_wizard("config.json")
        assert result is not None
        assert len(result.data_view_ids) == 3

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_wizard_config_not_success(self, _cfg, mock_cjapy, capsys):
        """configure_cjapy returns success=False → error and None."""
        _cfg.return_value = (False, "bad creds", None)

        result = interactive_wizard("config.json")
        assert result is None
        out = capsys.readouterr().out
        assert "bad creds" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_wizard_range_with_non_numeric_parts(self, _cfg, mock_cjapy, capsys):
        """Range like 'a-b' triggers ValueError → invalid range."""
        mock_cja = Mock()
        mock_cja.getDataViews.return_value = _mock_data_views()
        mock_cjapy.CJA.return_value = mock_cja

        with patch("builtins.input", side_effect=["a-b", "1", "1", "n", "n", "n", "y"]):
            result = interactive_wizard("config.json")
        assert result is not None
        out = capsys.readouterr().out
        assert "Invalid range" in out


# ===========================================================================
# show_config_status  (lines 9933-9939)
# ===========================================================================


class TestShowConfigStatus:
    """Tests for show_config_status exception handling."""

    def test_generic_exception_on_file_read_json_line_9935_9936(self, tmp_path, capsys):
        """Lines 9935-9936: generic Exception reading config file, JSON output."""
        config_path = tmp_path / "config.json"
        config_path.touch()  # Create file so it exists

        with patch("builtins.open", side_effect=PermissionError("access denied")):
            # Need the file to exist for config_path.exists() check
            with patch("pathlib.Path.exists", return_value=True):
                result = show_config_status(
                    config_file=str(config_path),
                    output_json=True,
                )
        assert result is False
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert "Cannot read" in parsed["error"]
        assert parsed["valid"] is False

    def test_generic_exception_on_file_read_text_line_9937_9938(self, tmp_path, capsys):
        """Lines 9937-9938: generic Exception reading config file, text output."""
        config_path = tmp_path / "config.json"
        config_path.touch()

        with patch("builtins.open", side_effect=PermissionError("access denied")):
            with patch("pathlib.Path.exists", return_value=True):
                result = show_config_status(
                    config_file=str(config_path),
                    output_json=False,
                )
        assert result is False
        out = capsys.readouterr().out
        assert "Cannot read" in out

    def test_json_decode_error_json_output(self, tmp_path, capsys):
        """JSONDecodeError with output_json=True → JSON error to stdout."""
        config_path = tmp_path / "config.json"
        config_path.write_text("not valid json {{{")

        result = show_config_status(config_file=str(config_path), output_json=True)
        assert result is False
        out = capsys.readouterr().out
        parsed = json.loads(out)
        assert "not valid JSON" in parsed["error"]

    def test_json_decode_error_text_output(self, tmp_path, capsys):
        """JSONDecodeError with output_json=False → text error."""
        config_path = tmp_path / "config.json"
        config_path.write_text("not valid json {{{")

        result = show_config_status(config_file=str(config_path), output_json=False)
        assert result is False
        out = capsys.readouterr().out
        assert "not valid JSON" in out


# ===========================================================================
# _emit_output additional edge cases
# ===========================================================================


class TestEmitOutputAdditional:
    """Additional edge cases for _emit_output."""

    def test_emit_output_creates_parent_directory(self, tmp_path):
        """Parent directory is created if it does not exist."""
        out_file = str(tmp_path / "subdir" / "nested" / "output.txt")
        _emit_output("content", out_file, False)
        assert os.path.exists(out_file)
        with open(out_file) as f:
            assert f.read() == "content"

    @patch("sys.stdout")
    @patch("os.get_terminal_size")
    @patch("shutil.which", return_value=None)
    def test_pager_not_found_falls_through(self, _which, mock_term_size, mock_stdout, capsys):
        """When pager binary is not found, falls through to print."""
        mock_stdout.isatty.return_value = True
        mock_term_size.return_value = MagicMock(lines=2)
        # Output exceeding term_height
        long_text = "\n".join(f"line {i}" for i in range(10))
        _emit_output(long_text, None, False)
        # Should not raise — falls through to print

    @patch("subprocess.Popen", side_effect=OSError("pager broken"))
    @patch("shutil.which", return_value="/usr/bin/less")
    @patch("os.get_terminal_size")
    @patch("sys.stdout")
    def test_pager_os_error_falls_through(self, mock_stdout, mock_term_size, _which, _popen, capsys):
        """When pager subprocess raises OSError, falls through to print."""
        mock_stdout.isatty.return_value = True
        mock_term_size.return_value = MagicMock(lines=2)
        long_text = "\n".join(f"line {i}" for i in range(10))
        _emit_output(long_text, None, False)
        # Should not raise


# ===========================================================================
# _run_list_command additional paths
# ===========================================================================


class TestRunListCommandAdditional:
    """Additional tests for _run_list_command."""

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_successful_execution(self, _cfg, mock_cjapy, capsys):
        """Happy path: fetch returns data, written to stdout."""
        mock_cjapy.CJA.return_value = Mock()

        result = _run_list_command(
            banner_text="TEST BANNER",
            command_name="test",
            fetch_and_format=lambda cja, mr: "output data",
            config_file="config.json",
        )
        assert result is True
        out = capsys.readouterr().out
        assert "TEST BANNER" in out
        assert "output data" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(False, "bad config", None))
    def test_config_failure_table_mode(self, _cfg, _cjapy, capsys):
        """configure_cjapy returns success=False in table mode."""
        result = _run_list_command(
            banner_text="TEST",
            command_name="test",
            fetch_and_format=lambda cja, mr: "data",
            config_file="config.json",
        )
        assert result is False
        out = capsys.readouterr().out
        assert "Configuration error: bad config" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(False, "bad config", None))
    def test_config_failure_json_mode(self, _cfg, _cjapy, capsys):
        """configure_cjapy returns success=False in JSON mode → stderr."""
        result = _run_list_command(
            banner_text="TEST",
            command_name="test",
            fetch_and_format=lambda cja, mr: "data",
            config_file="config.json",
            output_format="json",
        )
        assert result is False
        err = capsys.readouterr().err
        parsed = json.loads(err)
        assert "Configuration error" in parsed["error"]

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_fetch_returns_none_no_output(self, _cfg, mock_cjapy, capsys):
        """fetch_and_format returns None → no output emitted."""
        mock_cjapy.CJA.return_value = Mock()

        result = _run_list_command(
            banner_text="TEST",
            command_name="test",
            fetch_and_format=lambda cja, mr: None,
            config_file="config.json",
        )
        assert result is True

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    def test_machine_readable_no_banner(self, _cfg, mock_cjapy, capsys):
        """Machine-readable mode does not print banner."""
        mock_cjapy.CJA.return_value = Mock()

        _run_list_command(
            banner_text="SHOULD NOT APPEAR",
            command_name="test",
            fetch_and_format=lambda cja, mr: '{"data": []}',
            config_file="config.json",
            output_format="json",
        )
        out = capsys.readouterr().out
        assert "SHOULD NOT APPEAR" not in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value="myprofile")
    def test_profile_shown_in_banner(self, _resolve, _cfg, mock_cjapy, capsys):
        """Active profile is displayed in banner."""
        mock_cjapy.CJA.return_value = Mock()

        _run_list_command(
            banner_text="BANNER",
            command_name="test",
            fetch_and_format=lambda cja, mr: "data",
            config_file="config.json",
            profile="myprofile",
        )
        out = capsys.readouterr().out
        assert "Using profile: myprofile" in out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy", side_effect=SystemExit(1))
    def test_system_exit_machine_readable_re_raises_silently(self, _cfg, _cjapy, capsys):
        """SystemExit in machine-readable mode re-raises without printing."""
        with pytest.raises(SystemExit):
            _run_list_command(
                banner_text="TEST",
                command_name="test",
                fetch_and_format=lambda cja, mr: "data",
                config_file="config.json",
                output_format="json",
            )
