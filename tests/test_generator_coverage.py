"""Tests targeting uncovered utility functions in generator.py to maximize line coverage.

These tests exercise pure utility functions that do not require API mocking.
"""

from __future__ import annotations

import math

import pytest

from cja_auto_sdr.diff.models import ChangeType, ComponentDiff
from cja_auto_sdr.generator import (
    RunMode,
    _canonical_quality_policy_key,
    _coerce_run_mode,
    _format_diff_value,
    _get_change_detail,
    _get_change_symbol,
    _get_colored_symbol,
    _infer_run_status,
    _normalize_exit_code,
    _parse_non_negative_policy_int,
    count_quality_issues_by_severity,
    find_similar_names,
    is_data_view_id,
    levenshtein_distance,
    mask_sensitive_value,
    normalize_quality_severity,
)

# ==================== _coerce_run_mode ====================


class TestCoerceRunMode:
    """Tests for _coerce_run_mode() — converts values to RunMode enum."""

    def test_returns_run_mode_unchanged(self):
        assert _coerce_run_mode(RunMode.SDR) is RunMode.SDR

    def test_valid_string_returns_enum(self):
        assert _coerce_run_mode("sdr") is RunMode.SDR

    def test_all_enum_members_round_trip(self):
        for member in RunMode:
            assert _coerce_run_mode(member.value) is member

    def test_invalid_string_returns_none(self):
        assert _coerce_run_mode("not_a_mode") is None

    def test_none_returns_none(self):
        assert _coerce_run_mode(None) is None

    def test_int_returns_none(self):
        assert _coerce_run_mode(42) is None

    def test_bool_returns_none(self):
        assert _coerce_run_mode(True) is None

    def test_empty_string_returns_none(self):
        assert _coerce_run_mode("") is None


# ==================== _canonical_quality_policy_key ====================


class TestCanonicalQualityPolicyKey:
    """Tests for _canonical_quality_policy_key() — normalizes policy key strings."""

    def test_hyphen_to_underscore(self):
        assert _canonical_quality_policy_key("fail-on-quality") == "fail_on_quality"

    def test_uppercase_lowered(self):
        assert _canonical_quality_policy_key("FAIL_ON_QUALITY") == "fail_on_quality"

    def test_whitespace_stripped(self):
        assert _canonical_quality_policy_key("  max_issues  ") == "max_issues"

    def test_mixed_hyphens_uppercase_whitespace(self):
        assert _canonical_quality_policy_key("  Fail-On-Quality  ") == "fail_on_quality"

    def test_non_string_coerced(self):
        assert _canonical_quality_policy_key(123) == "123"

    def test_none_coerced(self):
        assert _canonical_quality_policy_key(None) == "none"


# ==================== _parse_non_negative_policy_int ====================


class TestParseNonNegativePolicyInt:
    """Tests for _parse_non_negative_policy_int() — validates policy integer fields."""

    def test_valid_zero(self):
        assert _parse_non_negative_policy_int(0, key="max_issues") == 0

    def test_valid_positive(self):
        assert _parse_non_negative_policy_int(42, key="max_issues") == 42

    def test_negative_raises(self):
        with pytest.raises(ValueError, match="must be >= 0"):
            _parse_non_negative_policy_int(-1, key="max_issues")

    def test_bool_true_raises(self):
        with pytest.raises(ValueError, match="must be an integer"):
            _parse_non_negative_policy_int(True, key="max_issues")

    def test_bool_false_raises(self):
        with pytest.raises(ValueError, match="must be an integer"):
            _parse_non_negative_policy_int(False, key="max_issues")

    def test_float_raises(self):
        with pytest.raises(ValueError, match="must be an integer"):
            _parse_non_negative_policy_int(3.14, key="max_issues")

    def test_string_raises(self):
        with pytest.raises(ValueError, match="must be an integer"):
            _parse_non_negative_policy_int("10", key="max_issues")

    def test_none_raises(self):
        with pytest.raises(ValueError, match="must be an integer"):
            _parse_non_negative_policy_int(None, key="max_issues")


# ==================== normalize_quality_severity ====================


class TestNormalizeQualitySeverity:
    """Tests for normalize_quality_severity() — normalizes severity strings."""

    @pytest.mark.parametrize(
        ("raw", "expected"),
        [
            ("critical", "CRITICAL"),
            ("CRITICAL", "CRITICAL"),
            ("high", "HIGH"),
            ("High", "HIGH"),
            ("medium", "MEDIUM"),
            ("low", "LOW"),
            ("info", "INFO"),
        ],
    )
    def test_valid_severities(self, raw, expected):
        assert normalize_quality_severity(raw) == expected

    def test_invalid_severity_raises(self):
        with pytest.raises(ValueError, match="Invalid quality severity"):
            normalize_quality_severity("UNKNOWN")

    def test_empty_string_raises(self):
        with pytest.raises(ValueError, match="Invalid quality severity"):
            normalize_quality_severity("")


# ==================== count_quality_issues_by_severity ====================


class TestCountQualityIssuesBySeverity:
    """Tests for count_quality_issues_by_severity() — counts issues by severity."""

    def test_empty_list(self):
        result = count_quality_issues_by_severity([])
        assert result == {}

    def test_single_severity(self):
        issues = [{"Severity": "HIGH"}, {"Severity": "HIGH"}]
        result = count_quality_issues_by_severity(issues)
        assert result == {"HIGH": 2}

    def test_mixed_severities(self):
        issues = [
            {"Severity": "HIGH"},
            {"Severity": "LOW"},
            {"Severity": "HIGH"},
            {"Severity": "CRITICAL"},
        ]
        result = count_quality_issues_by_severity(issues)
        assert result == {"CRITICAL": 1, "HIGH": 2, "LOW": 1}

    def test_unknown_severity_ignored(self):
        issues = [{"Severity": "BOGUS"}, {"Severity": "HIGH"}]
        result = count_quality_issues_by_severity(issues)
        assert result == {"HIGH": 1}

    def test_missing_severity_key_ignored(self):
        issues = [{"other": "field"}, {"Severity": "LOW"}]
        result = count_quality_issues_by_severity(issues)
        assert result == {"LOW": 1}

    def test_lowercase_severity_normalised(self):
        """Lowercase severity in data is uppercased and counted."""
        issues = [{"Severity": "high"}]
        result = count_quality_issues_by_severity(issues)
        assert result == {"HIGH": 1}


# ==================== _normalize_exit_code ====================


class TestNormalizeExitCode:
    """Tests for _normalize_exit_code() — normalizes SystemExit.code to int."""

    def test_none_returns_zero(self):
        assert _normalize_exit_code(None) == 0

    def test_int_returns_same(self):
        assert _normalize_exit_code(0) == 0
        assert _normalize_exit_code(1) == 1
        assert _normalize_exit_code(2) == 2
        assert _normalize_exit_code(127) == 127

    def test_bool_true_returns_one(self):
        # bool is subclass of int, so isinstance(True, int) is True
        # True is handled by the int branch and returns int(True) == 1
        assert _normalize_exit_code(True) == 1

    def test_bool_false_returns_zero(self):
        assert _normalize_exit_code(False) == 0

    def test_string_returns_one(self):
        assert _normalize_exit_code("error message") == 1

    def test_empty_string_returns_one(self):
        assert _normalize_exit_code("") == 1

    def test_list_returns_one(self):
        assert _normalize_exit_code([1, 2, 3]) == 1


# ==================== _infer_run_status ====================


class TestInferRunStatus:
    """Tests for _infer_run_status() — classifies run status from exit code + state."""

    def test_exit_zero_is_success(self):
        assert _infer_run_status(0, {}) == "success"

    def test_exit_zero_ignores_state(self):
        assert _infer_run_status(0, {"quality_gate_failed": True}) == "success"

    def test_quality_gate_exit_one_is_error(self):
        run_state = {"quality_gate_failed": True}
        assert _infer_run_status(1, run_state) == "error"

    def test_org_threshold_missing_fail_on_is_error(self):
        run_state = {
            "mode": RunMode.ORG_REPORT,
            "details": {
                "thresholds_exceeded": True,
                "fail_on_threshold": False,
            },
        }
        assert _infer_run_status(2, run_state) == "error"

    @pytest.mark.parametrize("mode", [RunMode.DIFF, RunMode.DIFF_SNAPSHOT, RunMode.COMPARE_SNAPSHOTS])
    @pytest.mark.parametrize("exit_code", [2, 3])
    def test_diff_modes_policy_exit(self, mode, exit_code):
        run_state = {
            "mode": mode,
            "details": {"operation_success": True},
        }
        assert _infer_run_status(exit_code, run_state) == "policy_exit"

    def test_unknown_exit_code_is_error(self):
        assert _infer_run_status(1, {}) == "error"

    def test_none_details_is_error(self):
        assert _infer_run_status(1, {"details": None}) == "error"


# ==================== mask_sensitive_value ====================


class TestMaskSensitiveValue:
    """Tests for mask_sensitive_value() — masks strings for display."""

    def test_empty_string_returns_empty_label(self):
        assert mask_sensitive_value("") == "(empty)"

    def test_short_string_all_asterisks(self):
        # Length 8 with show_chars=4 => 4*2=8 => all asterisks
        assert mask_sensitive_value("abcdefgh") == "********"

    def test_short_string_below_threshold(self):
        assert mask_sensitive_value("abc") == "***"

    def test_long_string_partial_mask(self):
        # "abcdefghijklm" (13 chars) with show_chars=4:
        # first 4 = "abcd", last 4 = "jklm", middle = 13 - 8 = 5 asterisks
        result = mask_sensitive_value("abcdefghijklm")
        assert result.startswith("abcd")
        assert result.endswith("jklm")
        assert result == "abcd*****jklm"

    def test_custom_show_chars(self):
        # "abcdefghij" (10 chars) with show_chars=2 => "ab******ij"
        result = mask_sensitive_value("abcdefghij", show_chars=2)
        assert result == "ab******ij"

    def test_show_chars_one(self):
        # "secret" (6 chars) with show_chars=1: "s****t"
        result = mask_sensitive_value("secret", show_chars=1)
        assert result == "s****t"

    def test_single_char(self):
        assert mask_sensitive_value("x") == "*"


# ==================== _get_change_symbol ====================


class TestGetChangeSymbol:
    """Tests for _get_change_symbol() — maps ChangeType to plain symbols."""

    @pytest.mark.parametrize(
        ("change_type", "expected"),
        [
            (ChangeType.ADDED, "+"),
            (ChangeType.REMOVED, "-"),
            (ChangeType.MODIFIED, "~"),
            (ChangeType.UNCHANGED, " "),
        ],
    )
    def test_known_types(self, change_type, expected):
        assert _get_change_symbol(change_type) == expected

    def test_unknown_type_returns_question_mark(self):
        # Pass something that is not in the dict
        assert _get_change_symbol("not_a_change_type") == "?"


# ==================== _get_colored_symbol ====================


class TestGetColoredSymbol:
    """Tests for _get_colored_symbol() — color-coded symbols."""

    def test_color_disabled_returns_plain_symbol(self):
        for ct in ChangeType:
            symbol = _get_colored_symbol(ct, use_color=False)
            assert symbol == _get_change_symbol(ct)

    def test_added_with_color_has_ansi(self):
        result = _get_colored_symbol(ChangeType.ADDED, use_color=True)
        assert "+" in result
        assert "\033[" in result  # ANSI escape present

    def test_removed_with_color_has_ansi(self):
        result = _get_colored_symbol(ChangeType.REMOVED, use_color=True)
        assert "-" in result
        assert "\033[" in result

    def test_modified_with_color_has_ansi(self):
        result = _get_colored_symbol(ChangeType.MODIFIED, use_color=True)
        assert "~" in result
        assert "\033[" in result

    def test_unchanged_with_color_returns_plain(self):
        # UNCHANGED does not get coloured
        result = _get_colored_symbol(ChangeType.UNCHANGED, use_color=True)
        assert result == " "


# ==================== _format_diff_value ====================


class TestFormatDiffValue:
    """Tests for _format_diff_value() — formats values for diff display."""

    def test_none_returns_empty_label(self):
        assert _format_diff_value(None) == "(empty)"

    def test_nan_returns_empty_label(self):
        assert _format_diff_value(float("nan")) == "(empty)"

    def test_numpy_nan_returns_empty_label(self):
        assert _format_diff_value(math.nan) == "(empty)"

    def test_string_returned_as_is(self):
        assert _format_diff_value("hello") == "hello"

    def test_integer_stringified(self):
        assert _format_diff_value(42) == "42"

    def test_truncation_at_default_max(self):
        long_val = "a" * 50
        result = _format_diff_value(long_val, truncate=True, max_len=30)
        assert len(result) == 30
        assert result == "a" * 30

    def test_no_truncation(self):
        long_val = "a" * 50
        result = _format_diff_value(long_val, truncate=False)
        assert result == long_val

    def test_custom_max_len(self):
        result = _format_diff_value("abcdefghij", truncate=True, max_len=5)
        assert result == "abcde"

    def test_exact_max_len_not_truncated(self):
        result = _format_diff_value("abcde", truncate=True, max_len=5)
        assert result == "abcde"


# ==================== _get_change_detail ====================


class TestGetChangeDetail:
    """Tests for _get_change_detail() — formats changed fields for display."""

    def test_modified_with_changes(self):
        diff = ComponentDiff(
            id="dim1",
            name="Dimension 1",
            change_type=ChangeType.MODIFIED,
            changed_fields={"description": ("old desc", "new desc")},
        )
        result = _get_change_detail(diff)
        assert "description: 'old desc' -> 'new desc'" in result

    def test_modified_multiple_fields(self):
        diff = ComponentDiff(
            id="dim1",
            name="Dimension 1",
            change_type=ChangeType.MODIFIED,
            changed_fields={
                "description": ("old", "new"),
                "type": ("string", "integer"),
            },
        )
        result = _get_change_detail(diff)
        assert "; " in result
        assert "description:" in result
        assert "type:" in result

    def test_added_returns_empty(self):
        diff = ComponentDiff(
            id="dim1",
            name="Dimension 1",
            change_type=ChangeType.ADDED,
        )
        assert _get_change_detail(diff) == ""

    def test_removed_returns_empty(self):
        diff = ComponentDiff(
            id="dim1",
            name="Dimension 1",
            change_type=ChangeType.REMOVED,
        )
        assert _get_change_detail(diff) == ""

    def test_modified_no_changes_returns_empty(self):
        diff = ComponentDiff(
            id="dim1",
            name="Dimension 1",
            change_type=ChangeType.MODIFIED,
            changed_fields={},
        )
        assert _get_change_detail(diff) == ""

    def test_none_values_shown_as_empty(self):
        diff = ComponentDiff(
            id="dim1",
            name="Dimension 1",
            change_type=ChangeType.MODIFIED,
            changed_fields={"description": (None, "new desc")},
        )
        result = _get_change_detail(diff)
        assert "(empty)" in result
        assert "'new desc'" in result


# ==================== is_data_view_id ====================


class TestIsDataViewId:
    """Tests for is_data_view_id() — checks 'dv_' prefix."""

    def test_valid_id(self):
        assert is_data_view_id("dv_abc123") is True

    def test_just_prefix(self):
        assert is_data_view_id("dv_") is True

    def test_wrong_prefix(self):
        assert is_data_view_id("my_dataview") is False

    def test_empty_string(self):
        assert is_data_view_id("") is False

    def test_similar_prefix(self):
        assert is_data_view_id("DV_abc123") is False

    def test_name_containing_dv(self):
        assert is_data_view_id("some_dv_name") is False


# ==================== levenshtein_distance ====================


class TestLevenshteinDistance:
    """Tests for levenshtein_distance() — edit distance calculation."""

    def test_identical_strings(self):
        assert levenshtein_distance("hello", "hello") == 0

    def test_empty_first(self):
        assert levenshtein_distance("", "abc") == 3

    def test_empty_second(self):
        assert levenshtein_distance("abc", "") == 3

    def test_both_empty(self):
        assert levenshtein_distance("", "") == 0

    def test_single_char_diff(self):
        assert levenshtein_distance("cat", "car") == 1

    def test_insertion(self):
        assert levenshtein_distance("cat", "cats") == 1

    def test_deletion(self):
        assert levenshtein_distance("cats", "cat") == 1

    def test_reversed_args_same_distance(self):
        assert levenshtein_distance("kitten", "sitting") == levenshtein_distance("sitting", "kitten")

    def test_known_distance(self):
        # kitten -> sitting: 3 edits
        assert levenshtein_distance("kitten", "sitting") == 3

    def test_completely_different(self):
        assert levenshtein_distance("abc", "xyz") == 3


# ==================== find_similar_names ====================


class TestFindSimilarNames:
    """Tests for find_similar_names() — similar name finder using edit distance."""

    def test_exact_match_case_insensitive(self):
        result = find_similar_names("Hello", ["hello", "world"])
        assert len(result) >= 1
        assert result[0] == ("hello", 0)

    def test_close_match(self):
        result = find_similar_names("tset", ["test", "best", "zzzz"])
        # "tset" -> "test" is distance 2 (swap); should be found
        names = [name for name, _ in result]
        assert "test" in names

    def test_no_match_beyond_threshold(self):
        result = find_similar_names("abc", ["xyzxyzxyz", "qwertyuiop"])
        assert result == []

    def test_max_suggestions_limits_results(self):
        names = [f"test{i}" for i in range(10)]
        result = find_similar_names("test0", names, max_suggestions=2)
        assert len(result) <= 2

    def test_max_distance_parameter(self):
        result = find_similar_names("abc", ["abd", "xyz"], max_distance=1)
        names = [name for name, _ in result]
        assert "abd" in names
        assert "xyz" not in names

    def test_empty_available_names(self):
        result = find_similar_names("test", [])
        assert result == []

    def test_results_sorted_by_distance(self):
        result = find_similar_names("test", ["test", "tset", "xxxx"], max_distance=5)
        distances = [d for _, d in result]
        assert distances == sorted(distances)


# ==================== _build_quality_report_dataframe ====================


class TestBuildQualityReportDataframe:
    """Tests for _build_quality_report_dataframe() — stable column ordering."""

    def test_empty_issues_returns_preferred_columns(self):
        from cja_auto_sdr.generator import (
            QUALITY_REPORT_PREFERRED_COLUMNS,
            _build_quality_report_dataframe,
        )

        df = _build_quality_report_dataframe([])
        assert list(df.columns) == list(QUALITY_REPORT_PREFERRED_COLUMNS)
        assert len(df) == 0

    def test_issues_with_preferred_columns_first(self):
        from cja_auto_sdr.generator import (
            QUALITY_REPORT_PREFERRED_COLUMNS,
            _build_quality_report_dataframe,
        )

        issues = [
            {
                "Extra": "val",
                "Severity": "HIGH",
                "Category": "naming",
                "Data View ID": "dv_1",
                "Data View Name": "Test",
                "Type": "dim",
                "Item Name": "x",
                "Issue": "bad",
                "Details": "d",
            },
        ]
        df = _build_quality_report_dataframe(issues)
        # Preferred columns come first, then extras
        cols = list(df.columns)
        preferred = [c for c in QUALITY_REPORT_PREFERRED_COLUMNS if c in cols]
        assert cols[: len(preferred)] == preferred
        assert "Extra" in cols
        assert cols.index("Extra") >= len(preferred)

    def test_issues_with_subset_of_preferred_columns(self):
        from cja_auto_sdr.generator import _build_quality_report_dataframe

        issues = [{"Severity": "LOW", "Custom": "abc"}]
        df = _build_quality_report_dataframe(issues)
        assert list(df.columns) == ["Severity", "Custom"]
        assert len(df) == 1


# ==================== write_quality_report_output ====================


class TestWriteQualityReportOutput:
    """Tests for write_quality_report_output() — format validation + output routing."""

    def test_unsupported_format_raises(self):
        from cja_auto_sdr.generator import write_quality_report_output

        with pytest.raises(ValueError, match="Unsupported quality report format"):
            write_quality_report_output([], "xml", None, ".")

    def test_stdout_json(self, capsys):
        from cja_auto_sdr.generator import write_quality_report_output

        issues = [{"Severity": "HIGH", "Issue": "test"}]
        result = write_quality_report_output(issues, "json", "-", ".")
        assert result == "stdout"
        captured = capsys.readouterr()
        assert '"Severity": "HIGH"' in captured.out

    def test_stdout_csv(self, capsys):
        from cja_auto_sdr.generator import write_quality_report_output

        issues = [{"Severity": "LOW", "Issue": "missing"}]
        result = write_quality_report_output(issues, "csv", "stdout", ".")
        assert result == "stdout"
        captured = capsys.readouterr()
        assert "Severity" in captured.out
        assert "LOW" in captured.out

    def test_auto_generated_filename(self, tmp_path):
        from cja_auto_sdr.generator import write_quality_report_output

        result = write_quality_report_output([], "json", None, str(tmp_path))
        assert result.startswith(str(tmp_path))
        assert "quality_report_" in result
        assert result.endswith(".json")

    def test_auto_generated_filename_csv(self, tmp_path):
        from cja_auto_sdr.generator import write_quality_report_output

        result = write_quality_report_output([], "csv", None, str(tmp_path))
        assert result.endswith(".csv")
        assert "quality_report_" in result

    def test_explicit_output_path(self, tmp_path):
        import json

        from cja_auto_sdr.generator import write_quality_report_output

        out_file = str(tmp_path / "my_report.json")
        issues = [{"Severity": "HIGH"}]
        result = write_quality_report_output(issues, "json", out_file, ".")
        assert result == out_file
        with open(out_file) as f:
            data = json.load(f)
        assert data == issues


# ==================== write_run_summary_output ====================


class TestWriteRunSummaryOutput:
    """Tests for write_run_summary_output() — stdout + file routing."""

    def test_stdout_dash(self, capsys):
        from cja_auto_sdr.generator import write_run_summary_output

        summary = {"status": "success", "exit_code": 0}
        result = write_run_summary_output(summary, "-")
        assert result == "stdout"
        captured = capsys.readouterr()
        assert '"status": "success"' in captured.out

    def test_stdout_keyword(self, capsys):
        from cja_auto_sdr.generator import write_run_summary_output

        result = write_run_summary_output({"k": "v"}, "stdout")
        assert result == "stdout"

    def test_relative_path_resolved_with_output_dir(self, tmp_path):
        import json

        from cja_auto_sdr.generator import write_run_summary_output

        summary = {"mode": "sdr"}
        result = write_run_summary_output(summary, "summary.json", output_dir=str(tmp_path))
        assert result == str(tmp_path / "summary.json")
        with open(result) as f:
            data = json.load(f)
        assert data == summary

    def test_absolute_path_not_changed(self, tmp_path):
        import json

        from cja_auto_sdr.generator import write_run_summary_output

        out = str(tmp_path / "abs_summary.json")
        summary = {"exit_code": 0}
        result = write_run_summary_output(summary, out, output_dir="/should/not/matter")
        assert result == out
        with open(out) as f:
            assert json.load(f) == summary


# ==================== append_github_step_summary ====================


class TestAppendGithubStepSummary:
    """Tests for append_github_step_summary() — env var + file append + error."""

    def test_returns_false_when_env_not_set(self, monkeypatch):
        from cja_auto_sdr.generator import append_github_step_summary

        monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
        assert append_github_step_summary("# Summary") is False

    def test_appends_to_file(self, monkeypatch, tmp_path):
        from cja_auto_sdr.generator import append_github_step_summary

        summary_file = tmp_path / "summary.md"
        summary_file.write_text("")
        monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary_file))
        result = append_github_step_summary("# Quality Report")
        assert result is True
        content = summary_file.read_text()
        assert "# Quality Report" in content
        assert content.endswith("\n\n")

    def test_oserror_returns_false_with_logger(self, monkeypatch):
        import logging

        from cja_auto_sdr.generator import append_github_step_summary

        monkeypatch.setenv("GITHUB_STEP_SUMMARY", "/nonexistent/path/summary.md")
        logger = logging.getLogger("test_github_summary")
        result = append_github_step_summary("# Test", logger=logger)
        assert result is False

    def test_oserror_returns_false_without_logger(self, monkeypatch):
        from cja_auto_sdr.generator import append_github_step_summary

        monkeypatch.setenv("GITHUB_STEP_SUMMARY", "/nonexistent/path/summary.md")
        result = append_github_step_summary("# Test", logger=None)
        assert result is False


# ==================== load_profile_config_json ====================


class TestLoadProfileConfigJson:
    """Tests for load_profile_config_json() — error paths."""

    def test_missing_config_returns_none(self, tmp_path):
        from cja_auto_sdr.generator import load_profile_config_json

        assert load_profile_config_json(tmp_path) is None

    def test_valid_dict_returns_credentials(self, tmp_path):
        import json

        from cja_auto_sdr.generator import load_profile_config_json

        config = {"client_id": "abc123", "org_id": "org1"}
        (tmp_path / "config.json").write_text(json.dumps(config))
        result = load_profile_config_json(tmp_path)
        assert result is not None
        assert result["client_id"] == "abc123"
        assert result["org_id"] == "org1"

    def test_non_dict_json_returns_none(self, tmp_path):
        from cja_auto_sdr.generator import load_profile_config_json

        (tmp_path / "config.json").write_text('["not", "a", "dict"]')
        result = load_profile_config_json(tmp_path)
        assert result is None

    def test_invalid_json_returns_none(self, tmp_path):
        from cja_auto_sdr.generator import load_profile_config_json

        (tmp_path / "config.json").write_text("{invalid json!!!")
        result = load_profile_config_json(tmp_path)
        assert result is None


# ==================== load_profile_dotenv ====================


class TestLoadProfileDotenv:
    """Tests for load_profile_dotenv() — OSError handling."""

    def test_missing_env_returns_none(self, tmp_path):
        from cja_auto_sdr.generator import load_profile_dotenv

        assert load_profile_dotenv(tmp_path) is None

    def test_oserror_returns_none(self, tmp_path, monkeypatch):
        from unittest.mock import patch

        from cja_auto_sdr.generator import load_profile_dotenv

        env_file = tmp_path / ".env"
        env_file.write_text("client_id=abc")

        with patch("builtins.open", side_effect=OSError("permission denied")):
            result = load_profile_dotenv(tmp_path)
        # When open raises OSError, returns None
        assert result is None

    def test_valid_env_returns_credentials(self, tmp_path):
        from cja_auto_sdr.generator import load_profile_dotenv

        (tmp_path / ".env").write_text("client_id=abc123\norg_id=org1\n")
        result = load_profile_dotenv(tmp_path)
        assert result is not None
        assert result["client_id"] == "abc123"

    def test_empty_env_returns_none(self, tmp_path):
        from cja_auto_sdr.generator import load_profile_dotenv

        (tmp_path / ".env").write_text("# just a comment\n\n")
        result = load_profile_dotenv(tmp_path)
        assert result is None


# ==================== list_profiles ====================


class TestListProfiles:
    """Tests for list_profiles() — branch coverage for no-dir and format."""

    def test_no_profiles_dir_json(self, monkeypatch, capsys):
        from cja_auto_sdr.generator import list_profiles

        # Point profiles dir to a nonexistent directory
        monkeypatch.setattr(
            "cja_auto_sdr.generator.get_profiles_dir",
            lambda: __import__("pathlib").Path("/nonexistent/profiles/dir"),
        )
        result = list_profiles(output_format="json")
        assert result is True
        captured = capsys.readouterr()
        assert '"profiles": []' in captured.out
        assert '"count": 0' in captured.out

    def test_no_profiles_dir_table(self, monkeypatch, capsys):
        from cja_auto_sdr.generator import list_profiles

        monkeypatch.setattr(
            "cja_auto_sdr.generator.get_profiles_dir",
            lambda: __import__("pathlib").Path("/nonexistent/profiles/dir"),
        )
        result = list_profiles(output_format="table")
        assert result is True
        captured = capsys.readouterr()
        assert "No profiles directory found" in captured.out

    def test_skips_non_directory_entries(self, monkeypatch, tmp_path, capsys):
        import json

        from cja_auto_sdr.generator import list_profiles

        # Create a file (not a directory) inside profiles dir
        (tmp_path / "not_a_dir.txt").write_text("hi")
        # Create a valid profile directory
        profile_dir = tmp_path / "myprofile"
        profile_dir.mkdir()
        (profile_dir / "config.json").write_text('{"client_id": "x"}')

        monkeypatch.setattr("cja_auto_sdr.generator.get_profiles_dir", lambda: tmp_path)
        monkeypatch.delenv("CJA_PROFILE", raising=False)
        result = list_profiles(output_format="json")
        assert result is True
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["count"] == 1
        assert data["profiles"][0]["name"] == "myprofile"

    def test_profile_with_both_sources(self, monkeypatch, tmp_path, capsys):
        import json

        from cja_auto_sdr.generator import list_profiles

        profile_dir = tmp_path / "dual"
        profile_dir.mkdir()
        (profile_dir / "config.json").write_text('{"client_id": "x"}')
        (profile_dir / ".env").write_text("org_id=y\n")

        monkeypatch.setattr("cja_auto_sdr.generator.get_profiles_dir", lambda: tmp_path)
        monkeypatch.delenv("CJA_PROFILE", raising=False)
        result = list_profiles(output_format="json")
        assert result is True
        data = json.loads(capsys.readouterr().out)
        assert data["profiles"][0]["sources"] == ["config.json", ".env"]
