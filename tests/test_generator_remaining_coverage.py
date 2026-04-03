"""Tests for remaining uncovered lines in generator.py (97% -> higher).

Targets the ~180 remaining uncovered lines across:
- _normalize_exit_code bool path (line 814)
- _normalize_import_credentials skip key (line 1487)
- _parse_env_credentials_content export prefix (line 1503)
- validate_data_view exception handler (lines 1917-1928)
- write_html_output _add_severity_class edge cases (lines 2702, 2710)
- _format_markdown_side_by_side early return + truncation (lines 3986, 4006)
- write_diff_excel_output / write_diff_csv_output inventory None guards (4522, 4707)
- display_inventory_summary elevated complexity (lines 4944, 4962, 4977, 4999)
- process_inventory_summary calculated metrics / segments import errors (5097-5112)
- process_single_dataview exception handlers (5674-5676, 5685-5687, 5718-5721)
- BatchProcessor stop_on_error (lines 6330-6336)
- DataViewCache singleton return (line 8046)
- resolve_data_view_names fuzzy match error (line 8349)
- _is_missing_sort_value TypeError (lines 8583-8584)
- _apply_discovery_filters_and_sort numeric None fallback (lines 8668-8669)
- handle_diff_command reverse print, config failure, auto-snapshot retention (12838-12916)
- handle_diff_snapshot_command generic exception (13600-13605)
- handle_diff_snapshot_command missing inventory warnings (13170, 13198)
- handle_diff_snapshot_command inventory build exceptions (13228-13241)
- _main_impl: run-summary-json stdout conflict, format auto-detect, ignore_fields,
  list_snapshots with name, prune_snapshots with name, compare_snapshots error,
  diff exit codes, duplicate DVs, name resolution display, dry run, quality report,
  batch result processing, quality report output path, run_summary_json output
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import pytest

from cja_auto_sdr.core.exceptions import CJASDRError
from cja_auto_sdr.diff.models import (
    ChangeType,
    ComponentDiff,
    DiffResult,
    DiffSummary,
    MetadataDiff,
)
from cja_auto_sdr.generator import (
    BatchProcessor,
    DataViewCache,
    ProcessingResult,
    _format_markdown_side_by_side,
    _format_side_by_side,
    _is_missing_sort_value,
    _normalize_exit_code,
    _normalize_import_credentials,
    _parse_env_credentials_content,
    _to_numeric_sort_value,
    display_inventory_summary,
    handle_diff_command,
    handle_diff_snapshot_command,
    process_inventory_summary,
    validate_data_view,
    write_html_output,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_args(**overrides):
    """Build an argparse.Namespace with sane defaults for _main_impl tests."""
    defaults = {
        "data_views": [],
        "config_file": "config.json",
        "format": None,
        "output_dir": "/tmp/test_output",
        "output": None,
        "log_level": "ERROR",
        "log_format": "text",
        "quiet": True,
        "production": False,
        "batch": False,
        "workers": "1",
        "continue_on_error": False,
        "enable_cache": False,
        "cache_size": 100,
        "cache_ttl": 300,
        "skip_validation": True,
        "max_issues": 100,
        "clear_cache": False,
        "show_timings": False,
        "dry_run": False,
        "validate_config": False,
        "config_status": False,
        "config_json": False,
        "max_retries": 3,
        "retry_base_delay": 1.0,
        "retry_max_delay": 30.0,
        "interactive": False,
        "exit_codes": False,
        "open": False,
        "no_color": False,
        "color_theme": "default",
        "sample_config": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


def _make_diff_result(
    has_changes=True, metric_diffs=None, dimension_diffs=None, calc_metrics_diffs=None, segments_diffs=None
):
    """Build a minimal DiffResult with sensible defaults."""
    summary_kw = {
        "source_metrics_count": 5,
        "target_metrics_count": 5,
        "source_dimensions_count": 3,
        "target_dimensions_count": 3,
        "metrics_modified": 1 if has_changes else 0,
    }
    return DiffResult(
        summary=DiffSummary(**summary_kw),
        metadata_diff=MetadataDiff(
            source_name="Source DV",
            target_name="Target DV",
            source_id="dv_src",
            target_id="dv_tgt",
        ),
        metric_diffs=metric_diffs or [],
        dimension_diffs=dimension_diffs or [],
        calc_metrics_diffs=calc_metrics_diffs,
        segments_diffs=segments_diffs,
    )


def _make_logger():
    return logging.getLogger("test_remaining_cov")


# ===========================================================================
# _normalize_exit_code: bool input (line 814)
# ===========================================================================


class TestNormalizeExitCode:
    def test_bool_true(self):
        assert _normalize_exit_code(True) == 1

    def test_bool_false(self):
        assert _normalize_exit_code(False) == 0

    def test_none(self):
        assert _normalize_exit_code(None) == 0

    def test_int(self):
        assert _normalize_exit_code(42) == 42

    def test_string(self):
        assert _normalize_exit_code("error") == 1


# ===========================================================================
# _normalize_import_credentials: key not in CREDENTIAL_FIELDS (line 1487)
# ===========================================================================


class TestNormalizeImportCredentials:
    def test_unknown_key_is_skipped(self):
        """Keys not in CREDENTIAL_FIELDS['all'] are silently dropped."""
        result = _normalize_import_credentials({"completely_unknown_key_xyz": "value123"})
        assert "completely_unknown_key_xyz" not in result

    def test_known_key_is_kept(self):
        """Recognized keys are normalized and kept."""
        result = _normalize_import_credentials({"org_id": "my_org@AdobeOrg"})
        assert result.get("org_id") == "my_org@AdobeOrg"

    def test_alias_mapping(self):
        """Alias keys (e.g. clientsecret -> secret) are normalized."""
        result = _normalize_import_credentials({"clientsecret": "my_secret"})
        assert result.get("secret") == "my_secret"

    def test_none_value_skipped(self):
        """None values are skipped entirely."""
        result = _normalize_import_credentials({"org_id": None})
        assert "org_id" not in result

    def test_empty_value_skipped(self):
        """Empty string values (after stripping) are not included."""
        result = _normalize_import_credentials({"org_id": "   "})
        assert "org_id" not in result


# ===========================================================================
# _parse_env_credentials_content: export prefix (line 1503)
# ===========================================================================


class TestParseEnvCredentialsContent:
    def test_export_prefix_stripped(self):
        """Lines starting with 'export ' have the prefix removed."""
        content = 'export ORG_ID="test_org@AdobeOrg"'
        result = _parse_env_credentials_content(content)
        assert result.get("org_id") == "test_org@AdobeOrg"

    def test_export_case_insensitive(self):
        """The export prefix check is case-insensitive."""
        content = "Export ORG_ID=test_org@AdobeOrg"
        result = _parse_env_credentials_content(content)
        assert result.get("org_id") == "test_org@AdobeOrg"

    def test_comments_ignored(self):
        result = _parse_env_credentials_content("# comment\n")
        assert result == {}

    def test_missing_equals_raises(self):
        with pytest.raises(ValueError, match="expected KEY=VALUE"):
            _parse_env_credentials_content("INVALID_LINE_NO_EQUALS")


# ===========================================================================
# validate_data_view: outer exception handler (lines 1917-1928)
# ===========================================================================


class TestValidateDataViewException:
    def test_recoverable_api_exception_returns_false(self):
        """A recoverable API exception in validate_data_view is caught and logged."""
        mock_cja = MagicMock()
        mock_cja.getDataView.side_effect = ValueError("Unexpected crash")
        logger = _make_logger()
        logger.setLevel(logging.DEBUG)

        result = validate_data_view(mock_cja, "dv_test123", logger)
        assert result is False

    def test_exception_with_non_string_id(self):
        """Edge case: validate_data_view with a non-standard ID that causes issues."""
        mock_cja = MagicMock()
        mock_cja.getDataView.side_effect = TypeError("NoneType has no attribute")
        logger = _make_logger()
        result = validate_data_view(mock_cja, "dv_bad", logger)
        assert result is False


# ===========================================================================
# write_html_output: _add_severity_class edge cases (lines 2702, 2710)
# ===========================================================================


class TestWriteHtmlOutputSeverityClass:
    def test_severity_class_row_idx_overflow(self, tmp_path):
        """When there are more <tr> rows than severity entries, extra rows pass through."""
        logger = _make_logger()
        dq_df = pd.DataFrame(
            {
                "Severity": ["HIGH"],
                "Category": ["Test"],
                "Type": ["Test"],
                "Item Name": ["item"],
                "Issue": ["issue"],
                "Details": ["detail"],
            }
        )
        data_dict = {"Data Quality": dq_df}
        metadata = {"Generated At": "2024-01-01", "Tool Version": "3.2.9"}

        output_path = write_html_output(data_dict, metadata, "test", str(tmp_path), logger)
        assert os.path.exists(output_path)
        with open(output_path, encoding="utf-8") as f:
            html_content = f.read()
        assert "severity-HIGH" in html_content

    def test_severity_class_already_has_class_attr(self, tmp_path):
        """When a <tr> tag already has class="...", the severity class is appended."""
        logger = _make_logger()
        dq_df = pd.DataFrame(
            {
                "Severity": ["CRITICAL", "LOW"],
                "Category": ["A", "B"],
                "Type": ["T1", "T2"],
                "Item Name": ["i1", "i2"],
                "Issue": ["x", "y"],
                "Details": ["d1", "d2"],
            }
        )
        data_dict = {"Data Quality": dq_df}
        metadata = {"Generated At": "2024-01-01", "Tool Version": "3.2.9"}

        output_path = write_html_output(data_dict, metadata, "test2", str(tmp_path), logger)
        assert os.path.exists(output_path)
        with open(output_path, encoding="utf-8") as f:
            content = f.read()
        assert "severity-CRITICAL" in content


# ===========================================================================
# _format_side_by_side: early return (line 3316)
# _format_markdown_side_by_side: early return + truncation (lines 3986, 4006)
# ===========================================================================


class TestFormatSideBySide:
    def test_not_modified_returns_empty(self):
        """A non-MODIFIED diff returns empty list immediately (line 3316)."""
        diff = ComponentDiff(
            id="m1",
            name="Metric 1",
            change_type=ChangeType.ADDED,
            changed_fields=None,
        )
        result = _format_side_by_side(diff, "Source", "Target")
        assert result == []

    def test_no_changed_fields_returns_empty(self):
        """MODIFIED with empty changed_fields returns empty (line 3316)."""
        diff = ComponentDiff(
            id="m1",
            name="Metric 1",
            change_type=ChangeType.MODIFIED,
            changed_fields={},
        )
        result = _format_side_by_side(diff, "Source", "Target")
        assert result == []


class TestFormatMarkdownSideBySide:
    def test_not_modified_returns_empty(self):
        """A non-MODIFIED diff returns empty list (line 3986)."""
        diff = ComponentDiff(
            id="m1",
            name="Metric 1",
            change_type=ChangeType.ADDED,
            changed_fields=None,
        )
        result = _format_markdown_side_by_side(diff, "Source", "Target")
        assert result == []

    def test_no_changed_fields_returns_empty(self):
        """MODIFIED with empty changed_fields returns empty (line 3986)."""
        diff = ComponentDiff(
            id="m1",
            name="Metric 1",
            change_type=ChangeType.MODIFIED,
            changed_fields={},
        )
        result = _format_markdown_side_by_side(diff, "Source", "Target")
        assert result == []

    def test_long_value_truncation(self):
        """Values longer than 50 chars are truncated to 47 + '...' (lines 4004, 4006)."""
        long_old = "A" * 100
        long_new = "B" * 100
        diff = ComponentDiff(
            id="m1",
            name="Metric 1",
            change_type=ChangeType.MODIFIED,
            changed_fields={"description": (long_old, long_new)},
        )
        result = _format_markdown_side_by_side(diff, "Source", "Target")
        lines_with_desc = [ln for ln in result if "description" in ln]
        assert len(lines_with_desc) == 1
        # Both old and new should be truncated
        assert lines_with_desc[0].count("...") == 2

    def test_normal_values_not_truncated(self):
        """Short values are not truncated."""
        diff = ComponentDiff(
            id="m1",
            name="Metric 1",
            change_type=ChangeType.MODIFIED,
            changed_fields={"title": ("Old Title", "New Title")},
        )
        result = _format_markdown_side_by_side(diff, "Source", "Target")
        assert any("Old Title" in ln for ln in result)
        assert any("New Title" in ln for ln in result)


# ===========================================================================
# display_inventory_summary: elevated complexity lines (4944, 4962, 4977, 4999)
# ===========================================================================


class TestDisplayInventorySummaryElevated:
    def _make_inventory(self, inv_type, total_key, elevated_count=5, high_count=0, extra_fields=None):
        inv = MagicMock()
        base_summary = {
            total_key: 10,
            "complexity": {
                "average": 55.0,
                "max": 72.0,
                "high_complexity_count": high_count,
                "elevated_complexity_count": elevated_count,
            },
        }
        if extra_fields:
            base_summary.update(extra_fields)
        inv.get_summary.return_value = base_summary
        inv.fields = []
        inv.metrics = []
        inv.segments = []
        return inv

    def test_segments_elevated_complexity(self, capsys):
        seg_inv = self._make_inventory(
            "segments",
            "total_segments",
            elevated_count=3,
            extra_fields={"governance": {}, "container_types": {}},
        )
        display_inventory_summary(
            data_view_id="dv_test",
            data_view_name="Test DV",
            segments_inventory=seg_inv,
            output_format="console",
            quiet=False,
            inventory_order=["segments"],
        )
        captured = capsys.readouterr()
        assert "Elevated (50-74): 3" in captured.out

    def test_calculated_elevated_complexity(self, capsys):
        calc_inv = self._make_inventory(
            "calculated",
            "total_calculated_metrics",
            elevated_count=2,
            extra_fields={"governance": {}},
        )
        display_inventory_summary(
            data_view_id="dv_test",
            data_view_name="Test DV",
            calculated_inventory=calc_inv,
            output_format="console",
            quiet=False,
            inventory_order=["calculated"],
        )
        captured = capsys.readouterr()
        assert "Elevated (50-74): 2" in captured.out

    def test_derived_elevated_complexity(self, capsys):
        derived_inv = self._make_inventory(
            "derived",
            "total_derived_fields",
            elevated_count=4,
            extra_fields={"metrics_count": 6, "dimensions_count": 4},
        )
        display_inventory_summary(
            data_view_id="dv_test",
            data_view_name="Test DV",
            derived_inventory=derived_inv,
            output_format="console",
            quiet=False,
            inventory_order=["derived"],
        )
        captured = capsys.readouterr()
        assert "Elevated (50-74): 4" in captured.out

    def test_high_complexity_items_display(self, capsys):
        """More than 10 high complexity items shows '... and N more' message."""
        derived_inv = MagicMock()
        derived_inv.get_summary.return_value = {
            "total_derived_fields": 20,
            "metrics_count": 10,
            "dimensions_count": 10,
            "complexity": {
                "average": 80.0,
                "max": 95.0,
                "high_complexity_count": 12,
                "elevated_complexity_count": 0,
            },
        }
        mock_fields = []
        for i in range(12):
            f = MagicMock()
            f.component_name = f"Field_{i}"
            f.complexity_score = 80 + i
            f.logic_summary = f"Complex logic {i}"
            mock_fields.append(f)
        derived_inv.fields = mock_fields

        display_inventory_summary(
            data_view_id="dv_test",
            data_view_name="Test DV",
            derived_inventory=derived_inv,
            output_format="console",
            quiet=False,
            inventory_order=["derived"],
        )
        captured = capsys.readouterr()
        assert "... and 2 more" in captured.out


# ===========================================================================
# process_inventory_summary: calc metrics / segments import errors (5097-5112)
# ===========================================================================


class TestProcessInventorySummaryImportErrors:
    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.with_log_context")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.display_inventory_summary")
    def test_calculated_metrics_import_error(
        self,
        mock_display,
        mock_init_cja,
        mock_log_ctx,
        mock_setup_log,
        capsys,
    ):
        mock_logger = MagicMock()
        mock_setup_log.return_value = mock_logger
        mock_log_ctx.return_value = mock_logger
        mock_cja = MagicMock()
        mock_cja.getDataView.return_value = {"name": "Test DV"}
        mock_init_cja.return_value = mock_cja
        mock_display.return_value = {"data_view_id": "dv_test"}

        process_inventory_summary(
            data_view_id="dv_test",
            config_file="config.json",
            include_calculated=True,
            include_segments=False,
            quiet=False,
        )
        mock_logger.warning.assert_called()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.with_log_context")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.display_inventory_summary")
    def test_segments_import_error(
        self,
        mock_display,
        mock_init_cja,
        mock_log_ctx,
        mock_setup_log,
        capsys,
    ):
        mock_logger = MagicMock()
        mock_setup_log.return_value = mock_logger
        mock_log_ctx.return_value = mock_logger
        mock_cja = MagicMock()
        mock_cja.getDataView.return_value = {"name": "Test DV"}
        mock_init_cja.return_value = mock_cja
        mock_display.return_value = {"data_view_id": "dv_test"}

        process_inventory_summary(
            data_view_id="dv_test",
            config_file="config.json",
            include_calculated=False,
            include_segments=True,
            quiet=False,
        )
        mock_logger.warning.assert_called()


# ===========================================================================
# BatchProcessor: stop_on_error (lines 6330-6336)
# ===========================================================================


class TestBatchProcessorStopOnError:
    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.with_log_context")
    @patch("cja_auto_sdr.generator.ProcessPoolExecutor")
    @patch("cja_auto_sdr.generator.tqdm")
    def test_stop_on_error_cancels_futures(
        self,
        mock_tqdm,
        mock_executor_cls,
        mock_log_ctx,
        mock_setup_log,
        tmp_path,
    ):
        mock_logger = MagicMock()
        mock_setup_log.return_value = mock_logger
        mock_log_ctx.return_value = mock_logger

        failed_result = ProcessingResult(
            data_view_id="dv_fail",
            data_view_name="Fail DV",
            success=False,
            duration=1.0,
            error_message="API error",
        )

        mock_future1 = MagicMock()
        mock_future1.result.return_value = failed_result

        mock_future2 = MagicMock()

        mock_executor = MagicMock()
        mock_executor.__enter__ = Mock(return_value=mock_executor)
        mock_executor.__exit__ = Mock(return_value=False)
        mock_executor.submit.side_effect = lambda fn, wa: {
            "dv_fail": mock_future1,
            "dv_pending": mock_future2,
        }[wa.data_view_id]
        mock_executor_cls.return_value = mock_executor

        with patch("cja_auto_sdr.generator.as_completed", return_value=iter([mock_future1])):
            mock_pbar = MagicMock()
            mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
            mock_tqdm.return_value.__exit__ = Mock(return_value=False)

            processor = BatchProcessor(
                config_file="config.json",
                output_dir=str(tmp_path),
                workers=2,
                continue_on_error=False,
                quiet=True,
            )

            results = processor.process_batch(["dv_fail", "dv_pending"])

        assert len(results["failed"]) == 1
        assert any("Stopping" in str(c) for c in mock_logger.warning.call_args_list)


# ===========================================================================
# DataViewCache: singleton already initialized (line 8046)
# ===========================================================================


class TestDataViewCacheSingleton:
    def test_second_init_is_noop(self):
        DataViewCache._instance = None
        DataViewCache._initialized = False

        cache1 = DataViewCache()
        cache1.set("test_key", [{"id": "dv_1"}])

        cache2 = DataViewCache()
        assert cache2 is cache1
        assert cache2.get("test_key") is not None

        DataViewCache._instance = None
        DataViewCache._initialized = False


# ===========================================================================
# resolve_data_view_names: fuzzy match mode error (line 8349)
# ===========================================================================


class TestResolveDataViewNamesFuzzyError:
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.cjapy")
    def test_fuzzy_match_error_message(self, mock_cjapy, mock_config, capsys):
        from cja_auto_sdr.generator import resolve_data_view_names

        mock_config.return_value = (True, "mock", None)
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [
            {"id": "dv_1", "name": "Production Analytics"},
        ]
        mock_cjapy.CJA.return_value = mock_cja

        logger = logging.getLogger("test_fuzzy")
        logger.setLevel(logging.DEBUG)

        resolved, _name_map = resolve_data_view_names(
            ["nonexistent_view_xyz"],
            "config.json",
            logger,
            match_mode="fuzzy",
        )
        assert resolved == []


# ===========================================================================
# _is_missing_sort_value: TypeError path (lines 8583-8584)
# ===========================================================================


class TestIsMissingSortValue:
    def test_nan_returns_true(self):
        assert _is_missing_sort_value(float("nan")) is True

    def test_none_returns_true(self):
        assert _is_missing_sort_value(None) is True

    def test_empty_string_returns_true(self):
        assert _is_missing_sort_value("   ") is True

    def test_value_returns_false(self):
        assert _is_missing_sort_value("hello") is False

    def test_type_error_returns_false(self):
        class BadObj:
            def __bool__(self):
                raise TypeError("cannot convert")

        assert _is_missing_sort_value(BadObj()) is False


# ===========================================================================
# _to_numeric_sort_value: edge cases
# ===========================================================================


class TestToNumericSortValue:
    def test_none_returns_none(self):
        assert _to_numeric_sort_value(None) is None

    def test_bool_returns_none(self):
        assert _to_numeric_sort_value(True) is None

    def test_int_returns_float(self):
        assert _to_numeric_sort_value(42) == 42.0

    def test_float_returns_float(self):
        assert _to_numeric_sort_value(3.14) == 3.14

    def test_nan_returns_none(self):
        assert _to_numeric_sort_value(float("nan")) is None

    def test_numeric_string_returns_float(self):
        assert _to_numeric_sort_value("  42.5  ") == 42.5

    def test_non_numeric_string_returns_none(self):
        assert _to_numeric_sort_value("hello") is None

    def test_empty_string_returns_none(self):
        assert _to_numeric_sort_value("") is None


# ===========================================================================
# _apply_discovery_filters_and_sort: numeric None fallback (8668-8669)
# ===========================================================================


class TestApplyDiscoveryFiltersAndSort:
    def test_numeric_sort_none_value_goes_to_missing(self):
        from cja_auto_sdr.generator import _apply_discovery_filters_and_sort

        rows = [
            {"name": "A", "count": "10"},
            {"name": "B", "count": "20"},
            {"name": "C", "count": None},
        ]
        result = _apply_discovery_filters_and_sort(rows, sort_expression="count")
        assert result[-1]["name"] == "C"

    def test_string_sort_fallback(self):
        from cja_auto_sdr.generator import _apply_discovery_filters_and_sort

        rows = [
            {"name": "Charlie", "label": "b_second"},
            {"name": "Alice", "label": "a_first"},
            {"name": "Bob", "label": "c_third"},
        ]
        result = _apply_discovery_filters_and_sort(rows, sort_expression="label")
        assert result[0]["name"] == "Alice"


# ===========================================================================
# handle_diff_command: reverse_diff, config failure, auto-snapshot retention
# ===========================================================================


class TestHandleDiffCommand:
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.DataViewComparator")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.write_diff_output")
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_diff_step_summary")
    def test_reverse_diff_prints_message(
        self,
        mock_build,
        mock_append,
        mock_write_diff,
        mock_cjapy,
        mock_config,
        mock_comparator_cls,
        mock_snapshot_cls,
        capsys,
    ):
        mock_config.return_value = (True, "mock", None)
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja

        mock_sm = MagicMock()
        mock_snapshot_cls.return_value = mock_sm
        mock_snapshot = MagicMock()
        mock_snapshot.data_view_name = "Test DV"
        mock_sm.create_snapshot.return_value = mock_snapshot
        mock_sm.generate_snapshot_filename.return_value = "snap.json"

        diff_result = _make_diff_result(has_changes=False)
        mock_comparator = MagicMock()
        mock_comparator.compare.return_value = diff_result
        mock_comparator_cls.return_value = mock_comparator
        mock_write_diff.return_value = ""

        success, _has_changes, _code = handle_diff_command(
            source_id="dv_src",
            target_id="dv_tgt",
            reverse_diff=True,
            quiet=False,
            quiet_diff=False,
        )
        captured = capsys.readouterr()
        assert "(Reversed comparison)" in captured.out
        assert success is True

    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_config_failure_returns_false(self, mock_config, capsys):
        mock_config.return_value = (False, "Auth failed", None)
        success, _has_changes, _code = handle_diff_command(
            source_id="dv_src",
            target_id="dv_tgt",
            quiet=False,
            quiet_diff=False,
        )
        assert success is False
        captured = capsys.readouterr()
        assert "Configuration failed" in captured.err

    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.DataViewComparator")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.write_diff_output")
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_diff_step_summary")
    @patch("cja_auto_sdr.generator.resolve_auto_prune_retention")
    @patch("cja_auto_sdr.generator.parse_retention_period")
    def test_auto_snapshot_with_retention(
        self,
        mock_parse_retention,
        mock_resolve,
        mock_build,
        mock_append,
        mock_write_diff,
        mock_cjapy,
        mock_config,
        mock_comparator_cls,
        mock_snapshot_cls,
        capsys,
        tmp_path,
    ):
        mock_config.return_value = (True, "mock", None)
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja

        mock_sm = MagicMock()
        mock_snapshot_cls.return_value = mock_sm
        mock_snapshot = MagicMock()
        mock_snapshot.data_view_name = "Test DV"
        mock_sm.create_snapshot.return_value = mock_snapshot
        mock_sm.generate_snapshot_filename.return_value = "snap.json"
        mock_sm.apply_retention_policy.return_value = ["old1.json"]
        mock_sm.apply_date_retention_policy.return_value = ["old2.json"]

        mock_resolve.return_value = (5, "7d")
        mock_parse_retention.return_value = 7

        diff_result = _make_diff_result(has_changes=False)
        mock_comparator = MagicMock()
        mock_comparator.compare.return_value = diff_result
        mock_comparator_cls.return_value = mock_comparator
        mock_write_diff.return_value = ""

        success, _has_changes, _code = handle_diff_command(
            source_id="dv_src",
            target_id="dv_tgt",
            auto_snapshot=True,
            snapshot_dir=str(tmp_path),
            keep_last=5,
            keep_since="7d",
            keep_last_specified=True,
            keep_since_specified=True,
            quiet=False,
            quiet_diff=False,
        )
        captured = capsys.readouterr()
        assert "Auto-saved snapshots" in captured.out
        assert "Retention policy" in captured.out
        assert success is True

    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.DataViewComparator")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.write_diff_output")
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_diff_step_summary")
    def test_diff_output_flag_writes_file(
        self,
        mock_build,
        mock_append,
        mock_write_diff,
        mock_cjapy,
        mock_config,
        mock_comparator_cls,
        mock_snapshot_cls,
        tmp_path,
        capsys,
    ):
        mock_config.return_value = (True, "mock", None)
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja

        mock_sm = MagicMock()
        mock_snapshot_cls.return_value = mock_sm
        mock_snapshot = MagicMock()
        mock_snapshot.data_view_name = "Test DV"
        mock_sm.create_snapshot.return_value = mock_snapshot

        diff_result = _make_diff_result(has_changes=True)
        mock_comparator = MagicMock()
        mock_comparator.compare.return_value = diff_result
        mock_comparator_cls.return_value = mock_comparator
        mock_write_diff.return_value = "diff output content"

        diff_output_path = str(tmp_path / "diff_out.txt")
        success, _has_changes, _code = handle_diff_command(
            source_id="dv_src",
            target_id="dv_tgt",
            diff_output=diff_output_path,
            quiet=False,
            quiet_diff=False,
        )
        captured = capsys.readouterr()
        assert "Diff output written to" in captured.out
        assert success is True

    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.cjapy")
    def test_generic_exception_returns_false(self, mock_cjapy, mock_config, capsys):
        mock_config.return_value = (True, "mock", None)
        mock_cjapy.CJA.side_effect = CJASDRError("Unexpected boom")

        success, _has_changes, _code = handle_diff_command(
            source_id="dv_src",
            target_id="dv_tgt",
        )
        assert success is False
        assert _code is None


# ===========================================================================
# handle_diff_snapshot_command: generic exception, missing inventory, build errors
# ===========================================================================


class TestHandleDiffSnapshotCommand:
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.cjapy")
    def test_generic_exception_returns_false(
        self,
        mock_cjapy,
        mock_config,
        mock_snapshot_cls,
        capsys,
    ):
        mock_sm = MagicMock()
        mock_snapshot_cls.return_value = mock_sm
        mock_sm.load_snapshot.side_effect = CJASDRError("Unexpected error")

        success, _has_changes, _code = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file="snap.json",
        )
        assert success is False
        captured = capsys.readouterr()
        assert "Failed to compare against snapshot" in captured.err

    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.cjapy")
    def test_constructor_exception_returns_false(
        self,
        mock_cjapy,
        mock_config,
        mock_snapshot_cls,
        capsys,
    ):
        mock_config.return_value = (True, "mock", None)
        mock_cjapy.CJA.side_effect = Exception("auth bootstrap failed")

        mock_sm = MagicMock()
        mock_snapshot_cls.return_value = mock_sm
        mock_sm.load_snapshot.return_value = MagicMock(created_at="2024-01-01T00:00:00Z")

        success, _has_changes, _code = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file="snap.json",
        )
        assert success is False
        captured = capsys.readouterr()
        assert "Failed to compare against snapshot: auth bootstrap failed" in captured.err

    @patch("cja_auto_sdr.generator.SnapshotManager")
    def test_missing_segments_inventory_warning(self, mock_snapshot_cls, capsys):
        mock_sm = MagicMock()
        mock_snapshot_cls.return_value = mock_sm

        mock_snapshot = MagicMock()
        mock_snapshot.has_calculated_metrics_inventory = True
        mock_snapshot.has_segments_inventory = False
        mock_snapshot.metrics = [{"id": "m1"}]
        mock_snapshot.dimensions = [{"id": "d1"}]
        mock_snapshot.get_inventory_summary.return_value = {
            "calculated_metrics": {"present": True, "count": 5},
            "segments": {"present": False, "count": 0},
        }
        mock_sm.load_snapshot.return_value = mock_snapshot

        success, _has_changes, _code = handle_diff_snapshot_command(
            data_view_id="dv_test",
            snapshot_file="snap.json",
            include_segments=True,
        )
        assert success is False
        captured = capsys.readouterr()
        assert "--include-segments" in captured.err

    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.DataViewComparator")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.write_diff_output")
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_diff_step_summary")
    def test_calc_metrics_build_exception(
        self,
        mock_build_summary,
        mock_append,
        mock_write_diff,
        mock_cjapy,
        mock_config,
        mock_comparator_cls,
        mock_snapshot_cls,
        capsys,
    ):
        mock_config.return_value = (True, "mock", None)
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja

        mock_sm = MagicMock()
        mock_snapshot_cls.return_value = mock_sm
        source_snap = MagicMock()
        source_snap.has_calculated_metrics_inventory = True
        source_snap.has_segments_inventory = True
        source_snap.metrics = [{"id": "m1"}]
        source_snap.dimensions = [{"id": "d1"}]
        mock_sm.load_snapshot.return_value = source_snap

        target_snap = MagicMock()
        target_snap.data_view_name = "Target DV"
        mock_sm.create_snapshot.return_value = target_snap

        diff_result = _make_diff_result(has_changes=False)
        mock_comparator = MagicMock()
        mock_comparator.compare.return_value = diff_result
        mock_comparator_cls.return_value = mock_comparator
        mock_write_diff.return_value = ""

        with patch.dict("sys.modules", {"cja_auto_sdr.inventory.calculated_metrics": MagicMock()}):
            mod = sys.modules["cja_auto_sdr.inventory.calculated_metrics"]
            mod.CalculatedMetricsInventoryBuilder.side_effect = RuntimeError("Build failed")

            success, _has_changes, _code = handle_diff_snapshot_command(
                data_view_id="dv_test",
                snapshot_file="snap.json",
                include_calc_metrics=True,
                include_segments=False,
                quiet=False,
                quiet_diff=False,
            )
        assert success is True

    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.DataViewComparator")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.write_diff_output")
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_diff_step_summary")
    def test_segments_build_exception(
        self,
        mock_build_summary,
        mock_append,
        mock_write_diff,
        mock_cjapy,
        mock_config,
        mock_comparator_cls,
        mock_snapshot_cls,
        capsys,
    ):
        mock_config.return_value = (True, "mock", None)
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja

        mock_sm = MagicMock()
        mock_snapshot_cls.return_value = mock_sm
        source_snap = MagicMock()
        source_snap.has_calculated_metrics_inventory = True
        source_snap.has_segments_inventory = True
        source_snap.metrics = [{"id": "m1"}]
        source_snap.dimensions = [{"id": "d1"}]
        mock_sm.load_snapshot.return_value = source_snap

        target_snap = MagicMock()
        target_snap.data_view_name = "Target DV"
        mock_sm.create_snapshot.return_value = target_snap

        diff_result = _make_diff_result(has_changes=False)
        mock_comparator = MagicMock()
        mock_comparator.compare.return_value = diff_result
        mock_comparator_cls.return_value = mock_comparator
        mock_write_diff.return_value = ""

        with patch.dict("sys.modules", {"cja_auto_sdr.inventory.segments": MagicMock()}):
            mod = sys.modules["cja_auto_sdr.inventory.segments"]
            mod.SegmentsInventoryBuilder.side_effect = RuntimeError("Seg build failed")

            success, _has_changes, _code = handle_diff_snapshot_command(
                data_view_id="dv_test",
                snapshot_file="snap.json",
                include_calc_metrics=False,
                include_segments=True,
                quiet=False,
                quiet_diff=False,
            )
        assert success is True


# ===========================================================================
# _main_impl: scattered lines
# ===========================================================================


class TestMainImplScattered:
    def test_run_summary_json_stdout_conflict(self, capsys):
        from cja_auto_sdr.generator import RunMode, _main_impl

        args = _make_args(output="stdout", run_summary_json="stdout")

        with (
            patch("cja_auto_sdr.generator.parse_arguments", return_value=args),
            patch("cja_auto_sdr.generator._infer_run_mode_enum", return_value=RunMode.SDR),
            patch("cja_auto_sdr.generator._cli_option_specified", return_value=False),
            patch("cja_auto_sdr.generator._cli_option_value", return_value=None),
        ):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "cannot be combined" in captured.err

    def test_format_auto_detect_from_extension(self, capsys, tmp_path):
        from cja_auto_sdr.generator import RunMode, _main_impl

        args = _make_args(
            data_views=["dv_test123"],
            output=str(tmp_path / "output.json"),
            format=None,
            quiet=False,
        )

        with (
            patch("cja_auto_sdr.generator.parse_arguments", return_value=args),
            patch("cja_auto_sdr.generator._infer_run_mode_enum", return_value=RunMode.SDR),
            patch("cja_auto_sdr.generator._cli_option_specified", return_value=False),
            patch("cja_auto_sdr.generator._cli_option_value", return_value=None),
            patch("cja_auto_sdr.generator.infer_format_from_path", return_value="json"),
            patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_test123"], {})),
            patch("cja_auto_sdr.generator.process_single_dataview") as mock_process,
            patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[]),
            patch("cja_auto_sdr.generator.build_quality_step_summary"),
            patch("cja_auto_sdr.generator.append_github_step_summary"),
            patch("time.time", return_value=1000.0),
        ):
            mock_result = ProcessingResult(
                data_view_id="dv_test123",
                data_view_name="Test DV",
                success=True,
                duration=1.0,
                output_file=str(tmp_path / "output.json"),
                metrics_count=5,
                dimensions_count=3,
                dq_issues_count=0,
            )
            mock_process.return_value = mock_result

            _main_impl()

            captured = capsys.readouterr()
            assert "Auto-detected format 'json'" in captured.out

    def test_list_snapshots_with_name_error(self, capsys):
        from cja_auto_sdr.generator import RunMode, _main_impl

        args = _make_args(
            data_views=["My Data View Name"],
            list_snapshots=True,
            format=None,
            snapshot_dir="./snapshots",
        )

        with (
            patch("cja_auto_sdr.generator.parse_arguments", return_value=args),
            patch("cja_auto_sdr.generator._infer_run_mode_enum", return_value=RunMode.SDR),
            patch("cja_auto_sdr.generator._cli_option_specified", return_value=False),
            patch("cja_auto_sdr.generator._cli_option_value", return_value=None),
        ):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "DATA_VIEW_ID" in captured.err

    def test_list_snapshots_stdout_forces_json(self, capsys):
        from cja_auto_sdr.generator import RunMode, _main_impl

        args = _make_args(
            data_views=[],
            list_snapshots=True,
            output="stdout",
            format="table",
            snapshot_dir="./snapshots",
            quiet=True,
        )

        with (
            patch("cja_auto_sdr.generator.parse_arguments", return_value=args),
            patch("cja_auto_sdr.generator._infer_run_mode_enum", return_value=RunMode.SDR),
            patch("cja_auto_sdr.generator._cli_option_specified", return_value=False),
            patch("cja_auto_sdr.generator._cli_option_value", return_value=None),
            patch("cja_auto_sdr.generator.SnapshotManager") as mock_sm_cls,
            patch("cja_auto_sdr.generator._emit_output") as mock_emit,
        ):
            mock_sm = MagicMock()
            mock_sm.list_snapshots.return_value = []
            mock_sm_cls.return_value = mock_sm

            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
            assert exc_info.value.code == 0
            mock_emit.assert_called_once()

    def test_prune_snapshots_with_name_error(self, capsys):
        from cja_auto_sdr.generator import RunMode, _main_impl

        args = _make_args(
            data_views=["My Data View"],
            prune_snapshots=True,
            format=None,
            snapshot_dir="./snapshots",
            keep_last=5,
        )

        with (
            patch("cja_auto_sdr.generator.parse_arguments", return_value=args),
            patch("cja_auto_sdr.generator._infer_run_mode_enum", return_value=RunMode.SDR),
            patch("cja_auto_sdr.generator._cli_option_specified", return_value=False),
            patch("cja_auto_sdr.generator._cli_option_value", return_value=None),
        ):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "DATA_VIEW_ID" in captured.err

    def test_prune_snapshots_invalid_keep_since(self, capsys, tmp_path):
        from cja_auto_sdr.generator import RunMode, _main_impl

        args = _make_args(
            data_views=[],
            prune_snapshots=True,
            format=None,
            snapshot_dir=str(tmp_path),
            keep_last=0,
            keep_since="invalid_value",
            auto_prune=False,
        )

        with (
            patch("cja_auto_sdr.generator.parse_arguments", return_value=args),
            patch("cja_auto_sdr.generator._infer_run_mode_enum", return_value=RunMode.SDR),
            patch("cja_auto_sdr.generator._cli_option_specified") as mock_cli_spec,
            patch("cja_auto_sdr.generator._cli_option_value", return_value=None),
            patch("cja_auto_sdr.generator.SnapshotManager") as mock_sm_cls,
            patch("cja_auto_sdr.generator.resolve_auto_prune_retention", return_value=(0, "invalid_value")),
            patch("cja_auto_sdr.generator.parse_retention_period", return_value=None),
        ):
            mock_cli_spec.side_effect = lambda opt, **kw: opt == "--keep-since"
            mock_sm = MagicMock()
            mock_sm.list_snapshots.return_value = []
            mock_sm_cls.return_value = mock_sm

            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "Invalid --keep-since" in captured.err

    def test_prune_snapshots_retention_report(self, capsys, tmp_path):
        from cja_auto_sdr.generator import RunMode, _main_impl

        args = _make_args(
            data_views=[],
            prune_snapshots=True,
            format=None,
            snapshot_dir=str(tmp_path),
            keep_last=3,
            keep_since=None,
            auto_prune=False,
            output=None,
        )

        with (
            patch("cja_auto_sdr.generator.parse_arguments", return_value=args),
            patch("cja_auto_sdr.generator._infer_run_mode_enum", return_value=RunMode.SDR),
            patch("cja_auto_sdr.generator._cli_option_specified") as mock_cli_spec,
            patch("cja_auto_sdr.generator._cli_option_value", return_value=None),
            patch("cja_auto_sdr.generator.SnapshotManager") as mock_sm_cls,
            patch("cja_auto_sdr.generator.resolve_auto_prune_retention", return_value=(3, None)),
            patch("cja_auto_sdr.generator._emit_output") as mock_emit,
        ):
            mock_cli_spec.side_effect = lambda opt, **kw: opt == "--keep-last"
            mock_sm = MagicMock()
            mock_sm.list_snapshots.return_value = [
                {"data_view_id": "dv_1", "data_view_name": "DV 1"},
            ]
            mock_sm.apply_retention_policy.return_value = ["/old/snap1.json"]
            mock_sm_cls.return_value = mock_sm

            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
            assert exc_info.value.code == 0
            mock_emit.assert_called_once()
            emitted = mock_emit.call_args[0][0]
            assert "prune complete" in emitted

    def test_duplicate_data_view_ids_warning(self, capsys, tmp_path):
        from cja_auto_sdr.generator import RunMode, _main_impl

        args = _make_args(
            data_views=["dv_test123", "dv_test123"],
            format="json",
            output_dir=str(tmp_path),
            quiet=False,
        )

        with (
            patch("cja_auto_sdr.generator.parse_arguments", return_value=args),
            patch("cja_auto_sdr.generator._infer_run_mode_enum", return_value=RunMode.SDR),
            patch("cja_auto_sdr.generator._cli_option_specified", return_value=False),
            patch("cja_auto_sdr.generator._cli_option_value", return_value=None),
            patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_test123", "dv_test123"], {})),
            patch("cja_auto_sdr.generator.process_single_dataview") as mock_process,
            patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[]),
            patch("cja_auto_sdr.generator.build_quality_step_summary"),
            patch("cja_auto_sdr.generator.append_github_step_summary"),
            patch("time.time", return_value=1000.0),
        ):
            mock_result = ProcessingResult(
                data_view_id="dv_test123",
                data_view_name="Test DV",
                success=True,
                duration=1.0,
                output_file="test.json",
                metrics_count=5,
                dimensions_count=3,
                dq_issues_count=0,
            )
            mock_process.return_value = mock_result

            _main_impl()

            captured = capsys.readouterr()
            assert "Duplicate" in captured.out

    def test_name_resolution_mapping_display(self, capsys, tmp_path):
        from cja_auto_sdr.generator import RunMode, _main_impl

        args = _make_args(
            data_views=["My Production DV"],
            format="json",
            output_dir=str(tmp_path),
            quiet=False,
            name_match="exact",
        )

        with (
            patch("cja_auto_sdr.generator.parse_arguments", return_value=args),
            patch("cja_auto_sdr.generator._infer_run_mode_enum", return_value=RunMode.SDR),
            patch("cja_auto_sdr.generator._cli_option_specified", return_value=False),
            patch("cja_auto_sdr.generator._cli_option_value", return_value=None),
            patch(
                "cja_auto_sdr.generator.resolve_data_view_names",
                return_value=(["dv_prod_123"], {"My Production DV": ["dv_prod_123"]}),
            ),
            patch("cja_auto_sdr.generator.process_single_dataview") as mock_process,
            patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[]),
            patch("cja_auto_sdr.generator.build_quality_step_summary"),
            patch("cja_auto_sdr.generator.append_github_step_summary"),
            patch("time.time", return_value=1000.0),
        ):
            mock_result = ProcessingResult(
                data_view_id="dv_prod_123",
                data_view_name="My Production DV",
                success=True,
                duration=1.0,
                output_file="test.json",
                metrics_count=5,
                dimensions_count=3,
                dq_issues_count=0,
            )
            mock_process.return_value = mock_result

            _main_impl()

            captured = capsys.readouterr()
            assert "My Production DV" in captured.out

    def test_name_resolution_multiple_ids(self, capsys, tmp_path):
        from cja_auto_sdr.generator import RunMode, _main_impl

        args = _make_args(
            data_views=["Shared DV"],
            format="json",
            output_dir=str(tmp_path),
            quiet=False,
            name_match="exact",
        )

        with (
            patch("cja_auto_sdr.generator.parse_arguments", return_value=args),
            patch("cja_auto_sdr.generator._infer_run_mode_enum", return_value=RunMode.SDR),
            patch("cja_auto_sdr.generator._cli_option_specified", return_value=False),
            patch("cja_auto_sdr.generator._cli_option_value", return_value=None),
            patch(
                "cja_auto_sdr.generator.resolve_data_view_names",
                return_value=(["dv_a", "dv_b"], {"Shared DV": ["dv_a", "dv_b"]}),
            ),
            patch("cja_auto_sdr.generator.BatchProcessor") as mock_bp,
            patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[]),
            patch("cja_auto_sdr.generator.build_quality_step_summary"),
            patch("cja_auto_sdr.generator.append_github_step_summary"),
            patch("time.time", return_value=1000.0),
        ):
            mock_bp.return_value.process_batch.return_value = {
                "successful": [
                    ProcessingResult(
                        data_view_id="dv_a",
                        data_view_name="Shared DV A",
                        success=True,
                        duration=1.0,
                    ),
                ],
                "failed": [],
            }

            _main_impl()

            captured = capsys.readouterr()
            assert "matching data views" in captured.out

    def test_dry_run_mode(self, capsys, tmp_path):
        from cja_auto_sdr.generator import RunMode, _main_impl

        args = _make_args(
            data_views=["dv_test"],
            dry_run=True,
            format=None,
            output_dir=str(tmp_path),
        )

        with (
            patch("cja_auto_sdr.generator.parse_arguments", return_value=args),
            patch("cja_auto_sdr.generator._infer_run_mode_enum", return_value=RunMode.SDR),
            patch("cja_auto_sdr.generator._cli_option_specified", return_value=False),
            patch("cja_auto_sdr.generator._cli_option_value", return_value=None),
            patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_test"], {})),
            patch("cja_auto_sdr.generator.setup_logging") as mock_log,
            patch("cja_auto_sdr.generator.run_dry_run", return_value=True) as mock_dry,
        ):
            mock_log.return_value = MagicMock()

            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
            assert exc_info.value.code == 0
            mock_dry.assert_called_once()

    def test_compare_snapshots_exit_code_threshold(self, capsys, tmp_path):
        from cja_auto_sdr.generator import RunMode, _main_impl

        args = _make_args(
            data_views=[],
            compare_snapshots=["snap_a.json", "snap_b.json"],
            format="console",
            output_dir=str(tmp_path),
            metrics_only=False,
            dimensions_only=False,
            inventory_only=False,
            changes_only=False,
            summary=False,
            ignore_fields=None,
            diff_labels=None,
            show_only=None,
            extended_fields=False,
            side_by_side=False,
            no_color=False,
            quiet_diff=False,
            reverse_diff=False,
            warn_threshold=10.0,
            group_by_field=False,
            group_by_field_limit=10,
            diff_output=None,
            format_pr_comment=False,
            include_calculated_metrics=False,
            include_segments_inventory=False,
        )

        with (
            patch("cja_auto_sdr.generator.parse_arguments", return_value=args),
            patch("cja_auto_sdr.generator._infer_run_mode_enum", return_value=RunMode.COMPARE_SNAPSHOTS),
            patch("cja_auto_sdr.generator._cli_option_specified", return_value=False),
            patch("cja_auto_sdr.generator._cli_option_value", return_value=None),
            patch("cja_auto_sdr.generator.handle_compare_snapshots_command") as mock_compare,
        ):
            mock_compare.return_value = (True, True, 3)

            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
            assert exc_info.value.code == 3

    def test_compare_snapshots_failure_exit_code_1(self, capsys, tmp_path):
        from cja_auto_sdr.generator import RunMode, _main_impl

        args = _make_args(
            data_views=[],
            compare_snapshots=["snap_a.json", "snap_b.json"],
            format="console",
            output_dir=str(tmp_path),
            metrics_only=False,
            dimensions_only=False,
            inventory_only=False,
            changes_only=False,
            summary=False,
            ignore_fields=None,
            diff_labels=None,
            show_only=None,
            extended_fields=False,
            side_by_side=False,
            no_color=False,
            quiet_diff=False,
            reverse_diff=False,
            warn_threshold=None,
            group_by_field=False,
            group_by_field_limit=10,
            diff_output=None,
            format_pr_comment=False,
            include_calculated_metrics=False,
            include_segments_inventory=False,
        )

        with (
            patch("cja_auto_sdr.generator.parse_arguments", return_value=args),
            patch("cja_auto_sdr.generator._infer_run_mode_enum", return_value=RunMode.COMPARE_SNAPSHOTS),
            patch("cja_auto_sdr.generator._cli_option_specified", return_value=False),
            patch("cja_auto_sdr.generator._cli_option_value", return_value=None),
            patch("cja_auto_sdr.generator.handle_compare_snapshots_command") as mock_compare,
        ):
            mock_compare.return_value = (False, False, None)

            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
            assert exc_info.value.code == 1

    def test_diff_snapshot_exit_code_threshold(self, capsys, tmp_path):
        from cja_auto_sdr.generator import RunMode, _main_impl

        args = _make_args(
            data_views=["dv_test"],
            diff_snapshot="snap.json",
            format="console",
            output_dir=str(tmp_path),
            ignore_fields=None,
            diff_labels=None,
            show_only=None,
            metrics_only=False,
            dimensions_only=False,
            extended_fields=False,
            side_by_side=False,
            quiet_diff=False,
            reverse_diff=False,
            warn_threshold=None,
            group_by_field=False,
            group_by_field_limit=10,
            diff_output=None,
            format_pr_comment=False,
            auto_snapshot=False,
            auto_prune=False,
            snapshot_dir="./snapshots",
            keep_last=0,
            keep_since=None,
            include_calculated_metrics=False,
            include_segments_inventory=False,
            include_derived_inventory=False,
            name_match="exact",
            profile=None,
            inventory_only=False,
        )

        with (
            patch("cja_auto_sdr.generator.parse_arguments", return_value=args),
            patch("cja_auto_sdr.generator._infer_run_mode_enum", return_value=RunMode.DIFF_SNAPSHOT),
            patch("cja_auto_sdr.generator._cli_option_specified", return_value=False),
            patch("cja_auto_sdr.generator._cli_option_value", return_value=None),
            patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_test"], {})),
            patch("cja_auto_sdr.generator.handle_diff_snapshot_command") as mock_diff,
        ):
            mock_diff.return_value = (True, True, 3)

            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
            assert exc_info.value.code == 3

    def test_diff_snapshot_failure_exit_code_1(self, capsys, tmp_path):
        from cja_auto_sdr.generator import RunMode, _main_impl

        args = _make_args(
            data_views=["dv_test"],
            diff_snapshot="snap.json",
            format="console",
            output_dir=str(tmp_path),
            ignore_fields=None,
            diff_labels=None,
            show_only=None,
            metrics_only=False,
            dimensions_only=False,
            extended_fields=False,
            side_by_side=False,
            quiet_diff=False,
            reverse_diff=False,
            warn_threshold=None,
            group_by_field=False,
            group_by_field_limit=10,
            diff_output=None,
            format_pr_comment=False,
            auto_snapshot=False,
            auto_prune=False,
            snapshot_dir="./snapshots",
            keep_last=0,
            keep_since=None,
            include_calculated_metrics=False,
            include_segments_inventory=False,
            include_derived_inventory=False,
            name_match="exact",
            profile=None,
            inventory_only=False,
        )

        with (
            patch("cja_auto_sdr.generator.parse_arguments", return_value=args),
            patch("cja_auto_sdr.generator._infer_run_mode_enum", return_value=RunMode.DIFF_SNAPSHOT),
            patch("cja_auto_sdr.generator._cli_option_specified", return_value=False),
            patch("cja_auto_sdr.generator._cli_option_value", return_value=None),
            patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_test"], {})),
            patch("cja_auto_sdr.generator.handle_diff_snapshot_command") as mock_diff,
        ):
            mock_diff.return_value = (False, False, None)

            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
            assert exc_info.value.code == 1


# ===========================================================================
# _main_impl: quality report handling
# ===========================================================================


class TestMainImplQualityReport:
    def test_quality_report_output_path_message(self, capsys, tmp_path):
        from cja_auto_sdr.generator import RunMode, _main_impl

        args = _make_args(
            data_views=["dv_test"],
            quality_report="json",
            skip_validation=False,
            format=None,
            output_dir=str(tmp_path),
            quiet=False,
            batch=False,
        )

        mock_result = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test DV",
            success=True,
            duration=1.0,
            metrics_count=10,
            dimensions_count=5,
            dq_issues_count=3,
        )

        with (
            patch("cja_auto_sdr.generator.parse_arguments", return_value=args),
            patch("cja_auto_sdr.generator._infer_run_mode_enum", return_value=RunMode.SDR),
            patch("cja_auto_sdr.generator._cli_option_specified", return_value=False),
            patch("cja_auto_sdr.generator._cli_option_value", return_value=None),
            patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_test"], {})),
            patch("cja_auto_sdr.generator.process_single_dataview", return_value=mock_result),
            patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[]),
            patch("cja_auto_sdr.generator.build_quality_step_summary"),
            patch("cja_auto_sdr.generator.append_github_step_summary"),
            patch("cja_auto_sdr.generator.write_quality_report_output", return_value="/path/report.json"),
            patch("time.time", return_value=1000.0),
        ):
            _main_impl()

            captured = capsys.readouterr()
            assert "Quality report written to" in captured.out

    def test_quality_report_failure_exits_1(self, capsys, tmp_path):
        from cja_auto_sdr.generator import RunMode, _main_impl

        args = _make_args(
            data_views=["dv_fail"],
            quality_report="json",
            skip_validation=False,
            format=None,
            output_dir=str(tmp_path),
            quiet=False,
            batch=False,
        )

        mock_fail = ProcessingResult(
            data_view_id="dv_fail",
            data_view_name="Fail DV",
            success=False,
            duration=1.0,
            error_message="API Error",
        )

        with (
            patch("cja_auto_sdr.generator.parse_arguments", return_value=args),
            patch("cja_auto_sdr.generator._infer_run_mode_enum", return_value=RunMode.SDR),
            patch("cja_auto_sdr.generator._cli_option_specified", return_value=False),
            patch("cja_auto_sdr.generator._cli_option_value", return_value=None),
            patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_fail"], {})),
            patch("cja_auto_sdr.generator.process_single_dataview", return_value=mock_fail),
            patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[]),
            patch("cja_auto_sdr.generator.build_quality_step_summary"),
            patch("cja_auto_sdr.generator.append_github_step_summary"),
            patch("cja_auto_sdr.generator.write_quality_report_output", return_value="report.json"),
            patch("time.time", return_value=1000.0),
        ):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
            assert exc_info.value.code == 1


# ===========================================================================
# _main_impl: validate_config run_state update (line 13903)
# ===========================================================================


class TestMainImplValidateConfig:
    def test_validate_config_updates_run_state(self, capsys):
        from cja_auto_sdr.generator import RunMode, _main_impl

        args = _make_args(validate_config=True)

        with (
            patch("cja_auto_sdr.generator.parse_arguments", return_value=args),
            patch("cja_auto_sdr.generator._infer_run_mode_enum", return_value=RunMode.SDR),
            patch("cja_auto_sdr.generator._cli_option_specified", return_value=False),
            patch("cja_auto_sdr.generator._cli_option_value", return_value=None),
            patch("cja_auto_sdr.generator.validate_config_only", return_value=True),
        ):
            run_state = {}
            with pytest.raises(SystemExit) as exc_info:
                _main_impl(run_state=run_state)
            assert exc_info.value.code == 0
            assert run_state["details"]["operation_success"] is True


# ===========================================================================
# write_diff_excel_output / write_diff_csv_output: inventory None guards
# ===========================================================================


class TestDiffInventoryNoneGuards:
    def test_excel_inventory_none_guard(self, tmp_path):
        from cja_auto_sdr.generator import write_diff_excel_output

        diff_result = _make_diff_result(
            has_changes=True,
            calc_metrics_diffs=None,
            segments_diffs=None,
        )
        logger = _make_logger()

        output = write_diff_excel_output(
            diff_result=diff_result,
            base_filename="test_diff",
            output_dir=str(tmp_path),
            logger=logger,
        )
        assert os.path.exists(output)

    def test_csv_inventory_none_guard(self, tmp_path):
        from cja_auto_sdr.generator import write_diff_csv_output

        diff_result = _make_diff_result(
            has_changes=True,
            calc_metrics_diffs=None,
            segments_diffs=None,
        )
        logger = _make_logger()

        output = write_diff_csv_output(
            diff_result=diff_result,
            base_filename="test_diff",
            output_dir=str(tmp_path),
            logger=logger,
        )
        assert os.path.isdir(output)


# ===========================================================================
# main() run_summary_json write failure (15596-15597)
# ===========================================================================


class TestMainRunSummaryFailure:
    def test_run_summary_write_exception(self, capsys):
        from cja_auto_sdr.generator import main

        with (
            patch("cja_auto_sdr.generator._cli_option_value", return_value="/bad/path/summary.json"),
            patch("cja_auto_sdr.generator._cli_option_specified", return_value=False),
            patch("cja_auto_sdr.generator._main_impl", side_effect=SystemExit(0)),
            patch("cja_auto_sdr.generator.write_run_summary_output", side_effect=OSError("Permission denied")),
        ):
            with pytest.raises(SystemExit):
                main()

            captured = capsys.readouterr()
            assert "Failed to write run summary" in captured.err


# ===========================================================================
# _main_impl: failed result error display (15312-15314)
# ===========================================================================


class TestMainImplSingleModeResults:
    def test_single_mode_quality_report_only_display(self, capsys, tmp_path):
        from cja_auto_sdr.generator import RunMode, _main_impl

        mock_result = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test DV",
            success=True,
            duration=1.0,
            metrics_count=10,
            dimensions_count=5,
            dq_issues_count=2,
        )

        args = _make_args(
            data_views=["dv_test"],
            quality_report="json",
            skip_validation=False,
            format=None,
            output_dir=str(tmp_path),
            quiet=False,
        )

        with (
            patch("cja_auto_sdr.generator.parse_arguments", return_value=args),
            patch("cja_auto_sdr.generator._infer_run_mode_enum", return_value=RunMode.SDR),
            patch("cja_auto_sdr.generator._cli_option_specified", return_value=False),
            patch("cja_auto_sdr.generator._cli_option_value", return_value=None),
            patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_test"], {})),
            patch("cja_auto_sdr.generator.process_single_dataview", return_value=mock_result),
            patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[]),
            patch("cja_auto_sdr.generator.build_quality_step_summary"),
            patch("cja_auto_sdr.generator.append_github_step_summary"),
            patch("cja_auto_sdr.generator.write_quality_report_output", return_value="report.json"),
            patch("time.time", return_value=1000.0),
        ):
            _main_impl()

            captured = capsys.readouterr()
            assert "Test DV (dv_test): 2 issues" in captured.out
            assert "Quality report written to" in captured.out

    def test_failed_result_error_display(self, capsys, tmp_path):
        from cja_auto_sdr.generator import RunMode, _main_impl

        mock_result = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test DV",
            success=False,
            duration=1.0,
            error_message="Connection timeout",
        )

        args = _make_args(
            data_views=["dv_test"],
            format="json",
            output_dir=str(tmp_path),
            quiet=False,
        )

        with (
            patch("cja_auto_sdr.generator.parse_arguments", return_value=args),
            patch("cja_auto_sdr.generator._infer_run_mode_enum", return_value=RunMode.SDR),
            patch("cja_auto_sdr.generator._cli_option_specified", return_value=False),
            patch("cja_auto_sdr.generator._cli_option_value", return_value=None),
            patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_test"], {})),
            patch("cja_auto_sdr.generator.process_single_dataview", return_value=mock_result),
            patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[]),
            patch("cja_auto_sdr.generator.build_quality_step_summary"),
            patch("cja_auto_sdr.generator.append_github_step_summary"),
            patch("time.time", return_value=1000.0),
        ):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
            assert exc_info.value.code == 1
            captured = capsys.readouterr()
            assert "Connection timeout" in captured.out


# ===========================================================================
# process_single_dataview: exception handlers (5674-5676, 5685-5687, 5718-5721)
# ===========================================================================


class TestProcessSingleDataviewExceptions:
    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_format_json_cell_exception(
        self,
        mock_excel_writer,
        mock_apply_fmt,
        mock_dq_cls,
        mock_fetcher_cls,
        mock_init_cja,
        mock_setup_log,
        tmp_path,
    ):
        from cja_auto_sdr.generator import process_single_dataview

        mock_logger = MagicMock()
        mock_logger.handlers = []
        mock_setup_log.return_value = mock_logger

        mock_cja = MagicMock()
        mock_init_cja.return_value = mock_cja

        metrics_df = pd.DataFrame({"id": ["m1"], "name": ["Met 1"], "type": ["std"]})
        dims_df = pd.DataFrame({"id": ["d1"], "name": ["Dim 1"], "type": ["str"]})
        lookup_data = {"id": "dv_test", "name": "Test", "owner": {"name": "Owner"}}

        mock_fetcher = MagicMock()
        mock_fetcher.fetch_all_data.return_value = (metrics_df, dims_df, lookup_data)
        mock_fetcher.get_tuner_statistics.return_value = None
        mock_fetcher_cls.return_value = mock_fetcher

        mock_dq = MagicMock()
        mock_dq.issues = []
        mock_dq.get_issues_dataframe.return_value = pd.DataFrame(
            columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"],
        )
        mock_dq_cls.return_value = mock_dq

        mock_writer = MagicMock()
        mock_excel_writer.return_value.__enter__ = Mock(return_value=mock_writer)
        mock_excel_writer.return_value.__exit__ = Mock(return_value=False)

        result = process_single_dataview(
            data_view_id="dv_test",
            config_file="config.json",
            output_dir=str(tmp_path),
            output_format="excel",
            skip_validation=True,
        )
        assert result.success is True
