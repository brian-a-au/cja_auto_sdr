"""Edge-case tests for api/quality.py.

Covers: severity ordering import, None vs 'None' handling, empty
data, duplicate detection, description validation, parallel execution.
"""

import logging
from concurrent.futures import Future
from unittest.mock import patch

import pandas as pd

from cja_auto_sdr.api.quality import DataQualityChecker
from cja_auto_sdr.core.constants import DEFAULT_VALIDATION_WORKERS, QUALITY_SEVERITY_ORDER

# ==================== Severity Ordering ====================


class TestSeverityOrdering:
    """Verify SEVERITY_ORDER derives from canonical constants."""

    def test_severity_order_matches_constants(self):
        assert DataQualityChecker.SEVERITY_ORDER == list(QUALITY_SEVERITY_ORDER)

    def test_severity_order_is_critical_to_info(self):
        assert DataQualityChecker.SEVERITY_ORDER == ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]

    def test_severity_order_is_list(self):
        """Exposed type is list[str], not tuple."""
        assert isinstance(DataQualityChecker.SEVERITY_ORDER, list)


# ==================== Empty / Missing Data ====================


class TestEmptyData:
    """Edge cases for empty and minimal DataFrames."""

    def _make_checker(self):
        return DataQualityChecker(logger=logging.getLogger("test"), quiet=True)

    def test_empty_dataframe_produces_critical_issue(self):
        checker = self._make_checker()
        df = pd.DataFrame()
        checker.check_all_quality_issues_optimized(df, "Metrics", ["id", "name"], ["id", "name"])
        assert len(checker.issues) == 1
        assert checker.issues[0]["Severity"] == "CRITICAL"
        assert checker.issues[0]["Category"] == "Empty Data"

    def test_dataframe_missing_expected_columns(self):
        """DataFrame with columns that don't match required fields."""
        checker = self._make_checker()
        df = pd.DataFrame({"unrelated": ["value"]})
        checker.check_all_quality_issues_optimized(df, "Metrics", ["id", "name", "type"], ["id"])
        critical_issues = [i for i in checker.issues if i["Severity"] == "CRITICAL"]
        assert len(critical_issues) >= 1
        assert "Missing Fields" in critical_issues[0]["Category"]

    def test_dataframe_with_only_id_column(self):
        """DataFrame with only 'id' — missing required 'name' and 'type'."""
        checker = self._make_checker()
        df = pd.DataFrame({"id": ["m1"]})
        checker.check_all_quality_issues_optimized(df, "Metrics", ["id", "name", "type"], ["id"])
        critical_issues = [i for i in checker.issues if i["Severity"] == "CRITICAL"]
        assert len(critical_issues) >= 1
        assert "name" in critical_issues[0]["Details"] or "type" in critical_issues[0]["Details"]

    def test_dataframe_with_all_null_name_column(self):
        checker = self._make_checker()
        df = pd.DataFrame({"id": ["m1", "m2"], "name": [None, None], "type": ["metric", "metric"]})
        checker.check_all_quality_issues_optimized(df, "Metrics", ["id", "name", "type"], ["id", "name"])
        null_issues = [i for i in checker.issues if i["Category"] == "Null Values"]
        assert len(null_issues) >= 1


# ==================== None vs "None" String ====================


class TestNoneVsNoneString:
    """Document handling of None vs 'None' string values."""

    def test_none_value_detected_as_null(self):
        checker = DataQualityChecker(logger=logging.getLogger("test"), quiet=True)
        df = pd.DataFrame({"id": ["m1"], "name": [None], "type": ["metric"]})
        checker.check_null_values(df, "Metrics", ["name"])
        null_issues = [i for i in checker.issues if i["Category"] == "Null Values"]
        assert len(null_issues) == 1

    def test_none_string_not_detected_as_null(self):
        """'None' as a string is NOT null — document this behavior."""
        checker = DataQualityChecker(logger=logging.getLogger("test"), quiet=True)
        df = pd.DataFrame({"id": ["m1"], "name": ["None"], "type": ["metric"]})
        checker.check_null_values(df, "Metrics", ["name"])
        null_issues = [i for i in checker.issues if i["Category"] == "Null Values"]
        assert len(null_issues) == 0

    def test_empty_string_name_not_null(self):
        """Empty string '' is NOT null in pandas — document."""
        checker = DataQualityChecker(logger=logging.getLogger("test"), quiet=True)
        df = pd.DataFrame({"id": ["m1"], "name": [""], "type": ["metric"]})
        checker.check_null_values(df, "Metrics", ["name"])
        null_issues = [i for i in checker.issues if i["Category"] == "Null Values"]
        assert len(null_issues) == 0


# ==================== Duplicate Detection ====================


class TestDuplicateDetection:
    """Edge cases for duplicate name detection."""

    def _make_checker(self):
        return DataQualityChecker(logger=logging.getLogger("test"), quiet=True)

    def test_exact_duplicates_detected(self):
        checker = self._make_checker()
        df = pd.DataFrame({"id": ["m1", "m2"], "name": ["Foo", "Foo"], "type": ["metric", "metric"]})
        checker.check_duplicates(df, "Metrics")
        dup_issues = [i for i in checker.issues if i["Category"] == "Duplicates"]
        assert len(dup_issues) == 1

    def test_case_different_not_detected_as_duplicate(self):
        """'Foo' vs 'foo' are NOT considered duplicates — document."""
        checker = self._make_checker()
        df = pd.DataFrame({"id": ["m1", "m2"], "name": ["Foo", "foo"], "type": ["metric", "metric"]})
        checker.check_duplicates(df, "Metrics")
        dup_issues = [i for i in checker.issues if i["Category"] == "Duplicates"]
        assert len(dup_issues) == 0

    def test_no_duplicates_clean(self):
        checker = self._make_checker()
        df = pd.DataFrame({"id": ["m1", "m2"], "name": ["Alpha", "Beta"], "type": ["metric", "metric"]})
        checker.check_duplicates(df, "Metrics")
        dup_issues = [i for i in checker.issues if i["Category"] == "Duplicates"]
        assert len(dup_issues) == 0

    def test_empty_dataframe_skips_duplicate_check(self):
        checker = self._make_checker()
        df = pd.DataFrame()
        checker.check_duplicates(df, "Metrics")
        assert len(checker.issues) == 0


# ==================== Description Validation ====================


class TestDescriptionValidation:
    """Edge cases for missing description checks."""

    def _make_checker(self):
        return DataQualityChecker(logger=logging.getLogger("test"), quiet=True)

    def test_whitespace_only_description_not_treated_as_missing(self):
        """Whitespace-only descriptions are NOT caught by empty-string check — document."""
        checker = self._make_checker()
        df = pd.DataFrame({"id": ["m1"], "name": ["A"], "description": ["   "]})
        checker.check_missing_descriptions(df, "Metrics")
        desc_issues = [i for i in checker.issues if i["Category"] == "Missing Descriptions"]
        # Current behavior: whitespace-only is NOT treated as missing (only isna() or == "")
        assert len(desc_issues) == 0

    def test_very_long_description_no_crash(self):
        checker = self._make_checker()
        df = pd.DataFrame({"id": ["m1"], "name": ["A"], "description": ["x" * 100_000]})
        checker.check_missing_descriptions(df, "Metrics")
        # Should complete without error
        assert len(checker.issues) == 0


# ==================== Parallel Execution ====================


class TestParallelExecution:
    """Verify parallel and sequential produce identical results."""

    def test_check_all_parallel_uses_default_validation_workers(self):
        metrics_df = pd.DataFrame({"id": ["m1"], "name": ["Metric A"], "type": ["metric"]})
        dimensions_df = pd.DataFrame({"id": ["d1"], "name": ["Dimension A"], "type": ["dimension"]})
        executor_workers = []

        class FakeExecutor:
            def __init__(self, max_workers):
                executor_workers.append(max_workers)

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def submit(self, fn):
                future = Future()
                future.set_result(fn())
                return future

        checker = DataQualityChecker(logger=logging.getLogger("test"), quiet=True)
        with patch("cja_auto_sdr.api.quality.ThreadPoolExecutor", FakeExecutor), patch(
            "cja_auto_sdr.api.quality.as_completed",
            side_effect=list,
        ):
            checker.check_all_parallel(
                metrics_df,
                dimensions_df,
                ["id", "name", "type"],
                ["id", "name", "type"],
                ["id", "name"],
            )

        assert executor_workers == [DEFAULT_VALIDATION_WORKERS]

    def test_parallel_and_sequential_same_results(self):
        metrics_df = pd.DataFrame({
            "id": ["m1", "m2"],
            "name": ["Alpha", "Alpha"],
            "type": ["metric", "metric"],
            "description": ["desc", ""],
        })
        dimensions_df = pd.DataFrame({
            "id": ["d1"],
            "name": [None],
            "type": ["dimension"],
            "description": ["desc"],
        })

        req_m = ["id", "name", "type"]
        req_d = ["id", "name", "type"]
        crit = ["id", "name"]

        # Sequential
        seq_checker = DataQualityChecker(logger=logging.getLogger("test_seq"), quiet=True)
        seq_checker.check_all_quality_issues_optimized(metrics_df, "Metrics", req_m, crit)
        seq_checker.check_all_quality_issues_optimized(dimensions_df, "Dimensions", req_d, crit)

        # Parallel
        par_checker = DataQualityChecker(logger=logging.getLogger("test_par"), quiet=True)
        par_checker.check_all_parallel(metrics_df, dimensions_df, req_m, req_d, crit)

        # Compare issue sets (order may differ)
        seq_sorted = sorted(seq_checker.issues, key=lambda i: (i["Severity"], i["Category"], i["Issue"]))
        par_sorted = sorted(par_checker.issues, key=lambda i: (i["Severity"], i["Category"], i["Issue"]))
        assert seq_sorted == par_sorted

    def test_get_issues_dataframe_severity_ordering(self):
        """Verify get_issues_dataframe sorts CRITICAL before LOW."""
        checker = DataQualityChecker(logger=logging.getLogger("test"), quiet=True)
        checker.add_issue("LOW", "Cat", "Metrics", "item", "low issue")
        checker.add_issue("CRITICAL", "Cat", "Metrics", "item", "critical issue")
        df = checker.get_issues_dataframe()
        severities = df["Severity"].tolist()
        assert severities[0] == "CRITICAL"
        assert severities[1] == "LOW"
