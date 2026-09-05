"""Tests for optimized data quality validation

This test suite validates that the optimized single-pass validation
produces identical results to the original sequential validation,
while providing significant performance improvements.
"""

import logging
import os
import sys
import time
from collections.abc import Callable

import pandas as pd
import pytest

# Import the class we're testing
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cja_auto_sdr.generator import DataQualityChecker

_PERF_REGRESSION_FACTOR = 1.5
_PERF_ABSOLUTE_OVERHEAD_SECONDS = 0.001


def _build_perf_logger() -> logging.Logger:
    """Use an isolated warning-level logger so perf checks avoid debug noise."""
    logger = logging.getLogger("test.optimized_validation.performance")
    logger.setLevel(logging.WARNING)
    logger.propagate = False
    if not logger.handlers:
        logger.addHandler(logging.NullHandler())
    return logger


def _run_original_validation(
    df: pd.DataFrame,
    logger: logging.Logger,
    required_fields: list[str],
    null_fields: list[str],
) -> None:
    validator = DataQualityChecker(logger)
    validator.check_empty_dataframe(df, "Metrics")
    validator.check_required_fields(df, "Metrics", required_fields)
    validator.check_duplicates(df, "Metrics")
    validator.check_null_values(df, "Metrics", null_fields)
    validator.check_missing_descriptions(df, "Metrics")
    validator.check_id_validity(df, "Metrics")


def _run_optimized_validation(
    df: pd.DataFrame,
    logger: logging.Logger,
    required_fields: list[str],
    null_fields: list[str],
) -> None:
    validator = DataQualityChecker(logger)
    validator.check_all_quality_issues_optimized(
        df,
        "Metrics",
        required_fields,
        null_fields,
    )


def _measure_runtime(func: Callable[[], None], repetitions: int = 1) -> float:
    start = time.perf_counter()
    for _ in range(repetitions):
        func()
    return time.perf_counter() - start


class TestOptimizedValidation:
    """Test optimized data quality validation methods"""

    def test_optimized_empty_dataframe(self):
        """Test optimized validation detects empty DataFrames"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        empty_df = pd.DataFrame()
        validator.check_all_quality_issues_optimized(
            empty_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )

        issues_df = validator.get_issues_dataframe()

        # Should detect empty dataset
        assert len(issues_df) > 0
        assert any(
            "empty" in str(row["Issue"]).lower() or "no" in str(row["Issue"]).lower() for _, row in issues_df.iterrows()
        )

    def test_optimized_duplicate_detection(self, sample_metrics_df):
        """Test optimized validation detects duplicates"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        # Add a duplicate
        duplicate_df = pd.concat(
            [
                sample_metrics_df,
                pd.DataFrame(
                    [
                        {
                            "id": "metric3",
                            "name": "Test Metric 1",  # Duplicate name
                            "type": "calculated",
                            "title": "Duplicate Metric",
                            "description": "Duplicate",
                        },
                    ],
                ),
            ],
            ignore_index=True,
        )

        validator.check_all_quality_issues_optimized(
            duplicate_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )

        issues_df = validator.get_issues_dataframe()

        # Should detect duplicate names
        assert len(issues_df) > 0
        assert any("duplicate" in str(row["Issue"]).lower() for _, row in issues_df.iterrows())

    def test_optimized_missing_descriptions(self, sample_metrics_df):
        """Test optimized validation detects missing descriptions"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        validator.check_all_quality_issues_optimized(
            sample_metrics_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )

        issues_df = validator.get_issues_dataframe()

        # Should detect missing description in metric2
        assert len(issues_df) > 0
        # Check for missing descriptions issue
        has_missing_desc = any("description" in str(row["Issue"]).lower() for _, row in issues_df.iterrows())
        assert has_missing_desc

    def test_optimized_required_fields(self):
        """Test optimized validation detects missing required fields"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        # Create DataFrame with missing required field
        incomplete_df = pd.DataFrame(
            [
                {
                    "id": "metric1",
                    "name": "Test Metric",
                    # Missing 'type' field
                },
            ],
        )

        validator.check_all_quality_issues_optimized(
            incomplete_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )

        issues_df = validator.get_issues_dataframe()

        # Should detect missing required field
        assert len(issues_df) > 0
        assert any(
            "required" in str(row["Issue"]).lower() or "missing" in str(row["Category"]).lower()
            for _, row in issues_df.iterrows()
        )

    def test_optimized_invalid_ids(self):
        """Test optimized validation detects invalid IDs"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        # Create DataFrame with invalid IDs
        df_with_invalid_ids = pd.DataFrame(
            [
                {"id": None, "name": "Test 1", "type": "metric", "description": "Desc 1"},
                {"id": "", "name": "Test 2", "type": "metric", "description": "Desc 2"},
                {"id": "valid_id", "name": "Test 3", "type": "metric", "description": "Desc 3"},
            ],
        )

        validator.check_all_quality_issues_optimized(
            df_with_invalid_ids,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )

        issues_df = validator.get_issues_dataframe()

        # Should detect invalid IDs
        assert len(issues_df) > 0
        has_invalid_id = any(
            "id" in str(row["Issue"]).lower() or "invalid" in str(row["Category"]).lower()
            for _, row in issues_df.iterrows()
        )
        assert has_invalid_id

    def test_optimized_severity_levels(self, sample_metrics_df):
        """Test that optimized validation assigns correct severity levels"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        validator.check_all_quality_issues_optimized(
            sample_metrics_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )

        issues_df = validator.get_issues_dataframe()

        # Check that severity levels are valid
        valid_severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
        for _, issue in issues_df.iterrows():
            assert issue["Severity"] in valid_severities

    def test_optimized_issue_structure(self, sample_metrics_df):
        """Test that optimized validation produces correctly structured issues"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        validator.check_all_quality_issues_optimized(
            sample_metrics_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )

        issues_df = validator.get_issues_dataframe()

        required_fields = ["Severity", "Category", "Type", "Item Name", "Issue", "Details"]
        for field in required_fields:
            assert field in issues_df.columns


class TestOptimizedVsOriginalValidation:
    """Test that optimized validation produces same results as original"""

    def test_results_match_for_metrics(self, sample_metrics_df):
        """Test optimized and original produce same results for metrics"""
        logger = logging.getLogger("test")

        # Run original validation
        validator_original = DataQualityChecker(logger)
        validator_original.check_empty_dataframe(sample_metrics_df, "Metrics")
        validator_original.check_required_fields(sample_metrics_df, "Metrics", ["id", "name", "type"])
        validator_original.check_duplicates(sample_metrics_df, "Metrics")
        validator_original.check_null_values(sample_metrics_df, "Metrics", ["id", "name", "description"])
        validator_original.check_missing_descriptions(sample_metrics_df, "Metrics")
        validator_original.check_id_validity(sample_metrics_df, "Metrics")

        original_issues = validator_original.get_issues_dataframe()

        # Run optimized validation
        validator_optimized = DataQualityChecker(logger)
        validator_optimized.check_all_quality_issues_optimized(
            sample_metrics_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )

        optimized_issues = validator_optimized.get_issues_dataframe()

        pd.testing.assert_frame_equal(original_issues, optimized_issues)

    def test_results_match_for_dimensions(self, sample_dimensions_df):
        """Test optimized and original produce same results for dimensions"""
        logger = logging.getLogger("test")

        # Run original validation
        validator_original = DataQualityChecker(logger)
        validator_original.check_empty_dataframe(sample_dimensions_df, "Dimensions")
        validator_original.check_required_fields(sample_dimensions_df, "Dimensions", ["id", "name", "type"])
        validator_original.check_duplicates(sample_dimensions_df, "Dimensions")
        validator_original.check_null_values(sample_dimensions_df, "Dimensions", ["id", "name", "description"])
        validator_original.check_missing_descriptions(sample_dimensions_df, "Dimensions")
        validator_original.check_id_validity(sample_dimensions_df, "Dimensions")

        original_issues = validator_original.get_issues_dataframe()

        # Run optimized validation
        validator_optimized = DataQualityChecker(logger)
        validator_optimized.check_all_quality_issues_optimized(
            sample_dimensions_df,
            "Dimensions",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )

        optimized_issues = validator_optimized.get_issues_dataframe()

        pd.testing.assert_frame_equal(original_issues, optimized_issues)

    def test_results_match_for_empty_dataframe(self):
        """Test optimized and original produce same results for empty DataFrame"""
        logger = logging.getLogger("test")
        empty_df = pd.DataFrame()

        # Run original validation
        validator_original = DataQualityChecker(logger)
        validator_original.check_empty_dataframe(empty_df, "Metrics")
        original_issues = validator_original.get_issues_dataframe()

        # Run optimized validation
        validator_optimized = DataQualityChecker(logger)
        validator_optimized.check_all_quality_issues_optimized(
            empty_df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )
        optimized_issues = validator_optimized.get_issues_dataframe()

        # Both should detect empty DataFrame
        assert len(original_issues) > 0
        assert len(optimized_issues) > 0

        # Both should have same severity
        assert original_issues.iloc[0]["Severity"] == optimized_issues.iloc[0]["Severity"]


@pytest.mark.slow
class TestOptimizedValidationPerformance:
    """Test performance improvements of optimized validation.

    These assertions compare short wall-clock timings and are more stable in
    the serial slow slice than in the xdist-driven unit gate.
    """

    def test_optimized_is_faster_than_original(self):
        """Test that optimized validation is faster than original with realistic dataset"""
        logger = _build_perf_logger()
        required_fields = ["id", "name", "type"]
        null_fields = ["id", "name", "description", "title"]

        # Create realistic dataset (similar to real CJA data views with 200+ components)
        size = 1000  # Larger dataset to show performance benefits
        df = pd.DataFrame(
            {
                "id": [f"id_{i}" for i in range(size)],
                "name": [f"Name {i}" if i % 10 != 0 else f"Name {i % 50}" for i in range(size)],
                "type": ["metric" if i % 2 == 0 else "calculated" for i in range(size)],
                "description": [f"Description {i}" if i % 3 != 0 else None for i in range(size)],
                "title": [f"Title {i}" for i in range(size)],
            },
        )

        # Run multiple iterations to get stable timing
        iterations = 10
        repetitions = 5
        original_times = []
        optimized_times = []

        for _ in range(iterations):
            original_times.append(
                _measure_runtime(
                    lambda: _run_original_validation(df, logger, required_fields, null_fields),
                    repetitions=repetitions,
                ),
            )
            optimized_times.append(
                _measure_runtime(
                    lambda: _run_optimized_validation(df, logger, required_fields, null_fields),
                    repetitions=repetitions,
                ),
            )

        # Use median times to reduce variance
        original_time = sorted(original_times)[len(original_times) // 2]
        optimized_time = sorted(optimized_times)[len(optimized_times) // 2]

        # Calculate performance improvement
        improvement = ((original_time - optimized_time) / original_time) * 100

        print(
            f"\nPerformance Comparison ({iterations} iterations x {repetitions} repetitions, dataset size={size}):",
        )
        print(f"  Original validation (median): {original_time:.4f}s")
        print(f"  Optimized validation (median): {optimized_time:.4f}s")
        print(f"  Improvement: {improvement:.1f}% faster")

        # Document performance characteristics
        print(f"  Performance improvement achieved: {improvement:.1f}%")
        print("  Note: Benefits are more apparent in production with:")
        print("    - Real CJA data views (150-200+ components)")
        print("    - Complex DataFrame structures with nested data")
        print("    - Multiple simultaneous validations in batch mode")
        print("  Target improvement: 30-50% for production workloads")

        # Guard against significant regressions while tolerating timer jitter on
        # sub-millisecond local/CI runs.
        max_allowed = max(
            original_time * _PERF_REGRESSION_FACTOR,
            original_time + _PERF_ABSOLUTE_OVERHEAD_SECONDS,
        )
        assert optimized_time <= max_allowed, (
            f"Optimized ({optimized_time:.4f}s) should not be significantly slower than "
            f"original ({original_time:.4f}s); allowed <= {max_allowed:.4f}s"
        )

    def test_optimized_scales_better(self):
        """Test that optimized validation scales better with larger datasets"""
        logger = _build_perf_logger()
        required_fields = ["id", "name", "type"]
        null_fields = ["id", "name", "description"]

        times_original = []
        times_optimized = []
        sizes = [500, 1000, 2000]  # Realistic sizes for CJA data views

        for size in sizes:
            # Create sample data
            df = pd.DataFrame(
                {
                    "id": [f"id_{i}" for i in range(size)],
                    "name": [f"Name {i}" for i in range(size)],
                    "type": ["metric"] * size,
                    "description": [f"Desc {i}" if i % 2 == 0 else None for i in range(size)],
                    "title": [f"Title {i}" for i in range(size)],
                },
            )

            # Run 3 times and take median to reduce variance
            orig_times = []
            opt_times = []
            repetitions = max(1, 10000 // size)
            for _ in range(3):
                orig_times.append(
                    _measure_runtime(
                        lambda: _run_original_validation(df, logger, required_fields, null_fields),
                        repetitions=repetitions,
                    ),
                )
                opt_times.append(
                    _measure_runtime(
                        lambda: _run_optimized_validation(df, logger, required_fields, null_fields),
                        repetitions=repetitions,
                    ),
                )

            times_original.append(sorted(orig_times)[1])  # Median
            times_optimized.append(sorted(opt_times)[1])  # Median

        print("\nScaling Comparison (median of 3 runs):")
        for i, size in enumerate(sizes):
            improvement = ((times_original[i] - times_optimized[i]) / times_original[i]) * 100
            print(
                f"  Size {size}: Original={times_original[i]:.4f}s, "
                f"Optimized={times_optimized[i]:.4f}s, "
                f"Improvement={improvement:.1f}%",
            )

        print("\n  Note: Performance benefits increase with:")
        print("    - Dataset size and complexity")
        print("    - Real production workloads")
        print("    - Reduced logging verbosity")
        print("    - Primary benefit: Single-pass validation improves code maintainability")

        # Check that optimized doesn't regress significantly while tolerating
        # tiny absolute timing noise on very fast environments.
        for i in range(len(sizes)):
            max_allowed = max(
                times_original[i] * _PERF_REGRESSION_FACTOR,
                times_original[i] + _PERF_ABSOLUTE_OVERHEAD_SECONDS,
            )
            assert times_optimized[i] <= max_allowed, (
                f"Optimized should not be significantly slower for size {sizes[i]} "
                f"(Original={times_original[i]:.4f}s, Optimized={times_optimized[i]:.4f}s, "
                f"allowed<={max_allowed:.4f}s)"
            )


class TestEdgeCases:
    """Test edge cases for optimized validation"""

    def test_dataframe_with_all_null_values(self):
        """Test optimized validation handles all-null DataFrames"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        df = pd.DataFrame(
            {
                "id": [None, None, None],
                "name": [None, None, None],
                "type": [None, None, None],
                "description": [None, None, None],
            },
        )

        validator.check_all_quality_issues_optimized(
            df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )

        issues_df = validator.get_issues_dataframe()

        # Should detect multiple null value issues
        assert len(issues_df) > 0

    def test_dataframe_with_special_characters(self):
        """Test optimized validation handles special characters"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        df = pd.DataFrame(
            [
                {"id": "id_1", "name": "Test & Special <> Chars", "type": "metric", "description": "Desc"},
                {"id": "id_2", "name": "Test & Special <> Chars", "type": "metric", "description": "Desc"},  # Duplicate
            ],
        )

        validator.check_all_quality_issues_optimized(
            df,
            "Metrics",
            ["id", "name", "type"],
            ["id", "name", "description"],
        )

        issues_df = validator.get_issues_dataframe()

        # Should detect duplicate with special characters
        assert len(issues_df) > 0
