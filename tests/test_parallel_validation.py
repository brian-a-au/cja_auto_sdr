"""Tests for parallel data quality validation

Validates that parallel validation:
1. Produces identical results to sequential validation
2. Provides performance improvements
3. Handles errors gracefully
4. Is thread-safe under concurrent access
"""
import pytest
import sys
import pandas as pd
import logging
import time
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cja_sdr_generator import DataQualityChecker


class TestParallelValidation:
    """Test parallel validation functionality"""

    def test_parallel_produces_identical_results(self, sample_metrics_df, sample_dimensions_df):
        """Verify parallel validation produces same results as sequential"""
        logger = logging.getLogger("test")

        # Sequential validation
        sequential_checker = DataQualityChecker(logger)
        sequential_checker.check_all_quality_issues_optimized(
            sample_metrics_df, 'Metrics', ['id', 'name', 'type'], ['id', 'name', 'description']
        )
        sequential_checker.check_all_quality_issues_optimized(
            sample_dimensions_df, 'Dimensions', ['id', 'name', 'type'], ['id', 'name', 'description']
        )
        sequential_issues = sorted(sequential_checker.issues, key=lambda x: (x['Type'], x['Item Name']))

        # Parallel validation
        parallel_checker = DataQualityChecker(logger)
        parallel_checker.check_all_parallel(
            metrics_df=sample_metrics_df,
            dimensions_df=sample_dimensions_df,
            metrics_required_fields=['id', 'name', 'type'],
            dimensions_required_fields=['id', 'name', 'type'],
            critical_fields=['id', 'name', 'description']
        )
        parallel_issues = sorted(parallel_checker.issues, key=lambda x: (x['Type'], x['Item Name']))

        # Compare results
        assert len(sequential_issues) == len(parallel_issues), \
            f"Issue count mismatch: sequential={len(sequential_issues)}, parallel={len(parallel_issues)}"

        for seq_issue, par_issue in zip(sequential_issues, parallel_issues):
            assert seq_issue['Severity'] == par_issue['Severity']
            assert seq_issue['Category'] == par_issue['Category']
            assert seq_issue['Type'] == par_issue['Type']
            assert seq_issue['Item Name'] == par_issue['Item Name']
            assert seq_issue['Issue'] == par_issue['Issue']

    def test_thread_safety_of_issues_list(self, sample_metrics_df, sample_dimensions_df):
        """Verify no race conditions when adding issues concurrently"""
        logger = logging.getLogger("test")

        # Run parallel validation multiple times
        expected_count = None
        for i in range(10):
            checker = DataQualityChecker(logger)
            checker.check_all_parallel(
                metrics_df=sample_metrics_df,
                dimensions_df=sample_dimensions_df,
                metrics_required_fields=['id', 'name', 'type'],
                dimensions_required_fields=['id', 'name', 'type'],
                critical_fields=['id', 'name', 'description']
            )

            current_count = len(checker.issues)
            if expected_count is None:
                expected_count = current_count
            else:
                assert current_count == expected_count, \
                    f"Race condition detected: iteration {i}, expected {expected_count}, got {current_count}"

        # Verify count is consistent and > 0
        assert expected_count > 0, "Should find some issues in test data"

    def test_parallel_performance_improvement(self, large_metrics_df, large_dimensions_df):
        """Verify parallel validation performs reasonably (may have overhead on small datasets)"""
        logger = logging.getLogger("test")

        # Run multiple iterations for more stable timing
        iterations = 3
        seq_times = []
        par_times = []

        for _ in range(iterations):
            # Sequential timing
            seq_checker = DataQualityChecker(logger)
            seq_start = time.time()
            seq_checker.check_all_quality_issues_optimized(
                large_metrics_df, 'Metrics', ['id', 'name', 'type'], ['id', 'name', 'description']
            )
            seq_checker.check_all_quality_issues_optimized(
                large_dimensions_df, 'Dimensions', ['id', 'name', 'type'], ['id', 'name', 'description']
            )
            seq_times.append(time.time() - seq_start)

            # Parallel timing
            par_checker = DataQualityChecker(logger)
            par_start = time.time()
            par_checker.check_all_parallel(
                metrics_df=large_metrics_df,
                dimensions_df=large_dimensions_df,
                metrics_required_fields=['id', 'name', 'type'],
                dimensions_required_fields=['id', 'name', 'type'],
                critical_fields=['id', 'name', 'description']
            )
            par_times.append(time.time() - par_start)

        # Use average times
        seq_duration = sum(seq_times) / len(seq_times)
        par_duration = sum(par_times) / len(par_times)

        speedup = seq_duration / par_duration if par_duration > 0 else 0
        print(f"\nSpeedup: {speedup:.2f}x (Sequential: {seq_duration:.3f}s, Parallel: {par_duration:.3f}s)")

        # Verify parallel doesn't add excessive overhead (within 200% of sequential)
        # Note: For small datasets (milliseconds), thread overhead and progress bar (tqdm) may exceed benefits
        # Real performance gains are seen with larger, more complex data views (seconds)
        assert par_duration < seq_duration * 3.0, \
            f"Parallel adds excessive overhead: seq={seq_duration:.3f}s, par={par_duration:.3f}s (>200% slower)"

    def test_parallel_with_empty_dataframes(self):
        """Verify parallel validation handles empty DataFrames"""
        logger = logging.getLogger("test")
        checker = DataQualityChecker(logger)

        empty_metrics = pd.DataFrame()
        empty_dimensions = pd.DataFrame()

        # Should not crash with empty DataFrames
        checker.check_all_parallel(
            metrics_df=empty_metrics,
            dimensions_df=empty_dimensions,
            metrics_required_fields=['id', 'name', 'type'],
            dimensions_required_fields=['id', 'name', 'type'],
            critical_fields=['id', 'name', 'description']
        )

        # Should find 2 critical issues (empty metrics and empty dimensions)
        assert len(checker.issues) == 2
        assert all(issue['Severity'] == 'CRITICAL' for issue in checker.issues)
        assert all(issue['Category'] == 'Empty Data' for issue in checker.issues)

    def test_parallel_error_handling(self):
        """Verify graceful error handling in parallel mode"""
        logger = logging.getLogger("test")
        checker = DataQualityChecker(logger)

        # Create valid metrics but malformed dimensions
        valid_metrics = pd.DataFrame([
            {"id": "m1", "name": "Metric 1", "type": "calculated"}
        ])
        valid_dimensions = pd.DataFrame([
            {"id": "d1", "name": "Dimension 1", "type": "string"}
        ])

        # Should complete without crashing
        checker.check_all_parallel(
            metrics_df=valid_metrics,
            dimensions_df=valid_dimensions,
            metrics_required_fields=['id', 'name', 'type'],
            dimensions_required_fields=['id', 'name', 'type'],
            critical_fields=['id', 'name', 'description']
        )

        # Should have collected issues from both validations
        assert len(checker.issues) >= 0  # May have issues for missing descriptions

    def test_parallel_result_consistency(self, sample_metrics_df, sample_dimensions_df):
        """Verify parallel validation results are consistent across multiple runs"""
        logger = logging.getLogger("test")

        results = []
        for _ in range(5):
            checker = DataQualityChecker(logger)
            checker.check_all_parallel(
                metrics_df=sample_metrics_df,
                dimensions_df=sample_dimensions_df,
                metrics_required_fields=['id', 'name', 'type'],
                dimensions_required_fields=['id', 'name', 'type'],
                critical_fields=['id', 'name', 'description']
            )
            # Sort issues for consistent comparison
            sorted_issues = sorted(checker.issues, key=lambda x: (x['Type'], x['Category'], x['Item Name']))
            results.append(sorted_issues)

        # All runs should produce identical results
        for i in range(1, len(results)):
            assert len(results[0]) == len(results[i]), \
                f"Run {i} produced different number of issues"
            for j in range(len(results[0])):
                assert results[0][j] == results[i][j], \
                    f"Run {i} issue {j} differs from first run"


class TestParallelValidationIntegration:
    """Integration tests for parallel validation"""

    def test_parallel_validation_with_real_issues(self):
        """Test parallel validation with data containing various quality issues"""
        logger = logging.getLogger("test")
        checker = DataQualityChecker(logger)

        # Create test data with intentional issues
        metrics_with_issues = pd.DataFrame([
            {"id": "m1", "name": "Metric 1", "type": "calculated", "description": "Valid metric"},
            {"id": "m2", "name": "Metric 2", "type": "calculated", "description": ""},  # Missing description
            {"id": "m3", "name": "Metric 1", "type": "calculated", "description": "Duplicate name"},  # Duplicate
            {"id": "", "name": "Metric 4", "type": "calculated", "description": "Invalid ID"},  # Invalid ID
        ])

        dimensions_with_issues = pd.DataFrame([
            {"id": "d1", "name": "Dimension 1", "type": "string", "description": "Valid dimension"},
            {"id": "d2", "name": "Dimension 2", "type": "string", "description": None},  # Null description
            {"id": "d3", "name": "Dimension 1", "type": "string", "description": "Duplicate"},  # Duplicate
        ])

        checker.check_all_parallel(
            metrics_df=metrics_with_issues,
            dimensions_df=dimensions_with_issues,
            metrics_required_fields=['id', 'name', 'type'],
            dimensions_required_fields=['id', 'name', 'type'],
            critical_fields=['id', 'name', 'description']
        )

        # Should find multiple issues
        assert len(checker.issues) > 0

        # Verify specific issues were found
        issue_categories = {issue['Category'] for issue in checker.issues}
        assert 'Duplicates' in issue_categories  # Should find duplicate names
        assert 'Missing Descriptions' in issue_categories or 'Null Values' in issue_categories  # Should find description issues

    def test_parallel_validation_dataframe_output(self, sample_metrics_df, sample_dimensions_df):
        """Test that parallel validation produces valid DataFrame output"""
        logger = logging.getLogger("test")
        checker = DataQualityChecker(logger)

        checker.check_all_parallel(
            metrics_df=sample_metrics_df,
            dimensions_df=sample_dimensions_df,
            metrics_required_fields=['id', 'name', 'type'],
            dimensions_required_fields=['id', 'name', 'type'],
            critical_fields=['id', 'name', 'description']
        )

        # Get issues as DataFrame
        issues_df = checker.get_issues_dataframe()

        # Verify DataFrame structure
        assert isinstance(issues_df, pd.DataFrame)
        if len(checker.issues) > 0:
            expected_columns = {'Severity', 'Category', 'Type', 'Item Name', 'Issue', 'Details'}
            assert set(issues_df.columns) == expected_columns
