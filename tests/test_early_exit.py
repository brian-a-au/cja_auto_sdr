"""Tests for DataFrame pre-validation early exit optimization

Validates that early exit works correctly:
1. Valid data continues through all checks
2. Missing required fields triggers early exit
3. Empty DataFrame triggers early exit
4. Only 1 critical issue logged (not multiple)
5. Backward compatibility maintained
"""
import pytest
import sys
import logging
import pandas as pd

sys.path.insert(0, '/Users/bau/DEV/cja_auto_sdr_2026')
from cja_sdr_generator import DataQualityChecker


class TestEarlyExitOnEmptyDataFrame:
    """Test early exit when DataFrame is empty"""

    def test_empty_dataframe_exits_early(self, caplog):
        """Test that empty DataFrame triggers early exit"""
        logger = logging.getLogger("test_empty")
        logger.setLevel(logging.DEBUG)

        dq_checker = DataQualityChecker(logger)

        # Empty DataFrame
        df_empty = pd.DataFrame()

        with caplog.at_level(logging.DEBUG):
            dq_checker.check_all_quality_issues_optimized(
                df_empty,
                'Metrics',
                ['id', 'name', 'type'],
                ['id', 'name']
            )

        # Should have exactly 1 issue (empty DataFrame)
        assert len(dq_checker.issues) == 1
        assert dq_checker.issues[0]['Severity'] == 'CRITICAL'
        assert dq_checker.issues[0]['Category'] == 'Empty Data'

    def test_empty_dataframe_stops_subsequent_checks(self):
        """Test that empty DataFrame prevents subsequent checks from running"""
        logger = logging.getLogger("test_empty_stops")
        logger.setLevel(logging.INFO)

        dq_checker = DataQualityChecker(logger)

        df_empty = pd.DataFrame()

        dq_checker.check_all_quality_issues_optimized(
            df_empty,
            'Metrics',
            ['id', 'name', 'type'],
            ['id', 'name']
        )

        # Should not have duplicate issues, null issues, etc.
        # Only the empty DataFrame issue
        assert len(dq_checker.issues) == 1


class TestEarlyExitOnMissingRequiredFields:
    """Test early exit when required fields are missing"""

    def test_missing_required_fields_exits_early(self):
        """Test that missing required fields triggers early exit"""
        logger = logging.getLogger("test_missing")
        logger.setLevel(logging.INFO)

        dq_checker = DataQualityChecker(logger)

        # DataFrame with data but missing required fields
        df_missing = pd.DataFrame({
            'some_column': ['value1', 'value2', 'value3']
        })

        dq_checker.check_all_quality_issues_optimized(
            df_missing,
            'Metrics',
            ['id', 'name', 'type'],  # Required fields that are missing
            ['id', 'name']
        )

        # Should have exactly 1 issue (missing required fields)
        assert len(dq_checker.issues) == 1
        assert dq_checker.issues[0]['Severity'] == 'CRITICAL'
        assert dq_checker.issues[0]['Category'] == 'Missing Fields'

    def test_missing_fields_stops_subsequent_checks(self):
        """Test that missing required fields prevents subsequent validation"""
        logger = logging.getLogger("test_missing_stops")
        logger.setLevel(logging.INFO)

        dq_checker = DataQualityChecker(logger)

        # DataFrame with duplicate names but missing 'name' field
        df_missing = pd.DataFrame({
            'other_field': ['dup', 'dup', 'unique']
        })

        dq_checker.check_all_quality_issues_optimized(
            df_missing,
            'Metrics',
            ['id', 'name', 'type'],
            ['id', 'name']
        )

        # Should only have missing fields issue, not duplicate issues
        assert len(dq_checker.issues) == 1
        assert 'Missing Fields' in dq_checker.issues[0]['Category']

    def test_partial_missing_fields_exits_early(self):
        """Test early exit when some (not all) required fields are missing"""
        logger = logging.getLogger("test_partial")
        logger.setLevel(logging.INFO)

        dq_checker = DataQualityChecker(logger)

        # Has 'name' but missing 'id' and 'type'
        df_partial = pd.DataFrame({
            'name': ['metric1', 'metric2']
        })

        dq_checker.check_all_quality_issues_optimized(
            df_partial,
            'Metrics',
            ['id', 'name', 'type'],
            ['id', 'name']
        )

        # Should exit early, only 1 issue
        assert len(dq_checker.issues) == 1
        assert dq_checker.issues[0]['Severity'] == 'CRITICAL'


class TestValidDataContinuesAllChecks:
    """Test that valid data continues through all validation checks"""

    def test_valid_data_runs_all_checks(self):
        """Test that valid DataFrame runs all validation checks"""
        logger = logging.getLogger("test_valid")
        logger.setLevel(logging.INFO)

        dq_checker = DataQualityChecker(logger)

        # Valid DataFrame with all required fields
        df_valid = pd.DataFrame({
            'id': ['m1', 'm2', 'm3'],
            'name': ['Metric 1', 'Metric 2', 'Metric 3'],
            'type': ['int', 'currency', 'int'],
            'description': ['Desc 1', 'Desc 2', 'Desc 3']
        })

        dq_checker.check_all_quality_issues_optimized(
            df_valid,
            'Metrics',
            ['id', 'name', 'type'],
            ['id', 'name']
        )

        # Should have no issues (valid data)
        assert len(dq_checker.issues) == 0

    def test_valid_data_with_issues_detected(self):
        """Test that valid DataFrame with data quality issues gets all checks run"""
        logger = logging.getLogger("test_valid_issues")
        logger.setLevel(logging.INFO)

        dq_checker = DataQualityChecker(logger)

        # Valid structure but with duplicate names and missing descriptions
        df_with_issues = pd.DataFrame({
            'id': ['m1', 'm2', 'm3'],
            'name': ['Duplicate', 'Duplicate', 'Unique'],
            'type': ['int', 'currency', 'int'],
            'description': ['Desc', '', 'Another desc']  # Empty description
        })

        dq_checker.check_all_quality_issues_optimized(
            df_with_issues,
            'Metrics',
            ['id', 'name', 'type'],
            ['id', 'name']
        )

        # Should detect multiple issues (duplicates, missing description)
        assert len(dq_checker.issues) > 1

        # Verify duplicate detection ran
        duplicate_issues = [i for i in dq_checker.issues if i['Category'] == 'Duplicates']
        assert len(duplicate_issues) > 0

        # Verify missing description check ran
        description_issues = [i for i in dq_checker.issues if 'description' in i['Issue'].lower()]
        assert len(description_issues) > 0


class TestBackwardCompatibility:
    """Test backward compatibility of early exit optimization"""

    def test_same_issues_detected_as_before(self):
        """Test that same issues are detected with early exit as without"""
        logger = logging.getLogger("test_compat")
        logger.setLevel(logging.INFO)

        dq_checker = DataQualityChecker(logger)

        # Valid DataFrame with known issues
        df = pd.DataFrame({
            'id': ['m1', 'm2', 'm3', 'm4'],
            'name': ['Dup', 'Dup', 'Valid', 'Missing Desc'],
            'type': ['int', 'int', 'currency', 'int'],
            'description': ['Desc 1', 'Desc 2', 'Desc 3', '']
        })

        dq_checker.check_all_quality_issues_optimized(
            df,
            'Metrics',
            ['id', 'name', 'type'],
            ['id', 'name']
        )

        # Should detect duplicates and missing description
        assert len(dq_checker.issues) >= 2

        categories = [issue['Category'] for issue in dq_checker.issues]
        assert 'Duplicates' in categories
        assert any('Missing' in cat or 'description' in issue['Issue'].lower()
                   for cat, issue in zip(categories, dq_checker.issues))

    def test_get_issues_dataframe_still_works(self):
        """Test that get_issues_dataframe() works after early exit"""
        logger = logging.getLogger("test_df_compat")
        logger.setLevel(logging.INFO)

        dq_checker = DataQualityChecker(logger)

        # Missing required fields
        df_invalid = pd.DataFrame({
            'other_field': ['val1', 'val2']
        })

        dq_checker.check_all_quality_issues_optimized(
            df_invalid,
            'Metrics',
            ['id', 'name', 'type'],
            ['id', 'name']
        )

        # Should be able to get DataFrame
        issues_df = dq_checker.get_issues_dataframe()
        assert isinstance(issues_df, pd.DataFrame)
        assert len(issues_df) == 1


class TestPerformanceImprovement:
    """Test that early exit provides performance benefit in error scenarios"""

    def test_early_exit_prevents_unnecessary_operations(self):
        """Test that early exit skips expensive checks on invalid data"""
        logger = logging.getLogger("test_perf")
        logger.setLevel(logging.WARNING)  # Production mode

        dq_checker = DataQualityChecker(logger)

        # Large invalid DataFrame (missing required fields)
        # Without early exit, would run duplicate detection, null checks, etc.
        df_large_invalid = pd.DataFrame({
            'wrong_column': [f'value_{i}' for i in range(1000)]
        })

        import time
        start = time.time()
        dq_checker.check_all_quality_issues_optimized(
            df_large_invalid,
            'Metrics',
            ['id', 'name', 'type'],
            ['id', 'name']
        )
        duration = time.time() - start

        # Should complete very quickly (early exit)
        # Without early exit, would take much longer to process 1000 rows
        assert duration < 0.1  # Should be nearly instant

        # Should only have 1 issue (missing fields)
        assert len(dq_checker.issues) == 1

    def test_valid_data_still_runs_all_checks_quickly(self):
        """Test that valid data still completes efficiently"""
        logger = logging.getLogger("test_perf_valid")
        logger.setLevel(logging.WARNING)

        dq_checker = DataQualityChecker(logger)

        # Large valid DataFrame
        df_large_valid = pd.DataFrame({
            'id': [f'm{i}' for i in range(1000)],
            'name': [f'Metric {i}' for i in range(1000)],
            'type': ['int'] * 1000,
            'description': [f'Description {i}' for i in range(1000)]
        })

        import time
        start = time.time()
        dq_checker.check_all_quality_issues_optimized(
            df_large_valid,
            'Metrics',
            ['id', 'name', 'type'],
            ['id', 'name']
        )
        duration = time.time() - start

        # Should still complete quickly with vectorized operations
        assert duration < 0.5  # Generous threshold

        # Should have no issues (valid data)
        assert len(dq_checker.issues) == 0
