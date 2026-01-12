"""Tests for logging optimization features

Validates that logging optimizations work correctly:
1. Production mode flag
2. Environment variable support
3. Conditional data quality logging
4. Summary logging
5. Performance tracker logging levels
"""
import pytest
import sys
import logging
import os
from unittest.mock import patch
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cja_sdr_generator import (
    setup_logging, DataQualityChecker, PerformanceTracker, parse_arguments
)


class TestProductionMode:
    """Test production mode flag and behavior"""

    def test_production_flag_parsing(self):
        """Test that --production flag is recognized"""
        test_args = ['cja_sdr_generator.py', '--production', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert hasattr(args, 'production')
            assert args.production is True

    def test_production_flag_default_false(self):
        """Test that production flag defaults to False"""
        test_args = ['cja_sdr_generator.py', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.production is False


class TestEnvironmentVariable:
    """Test CJA_LOG_LEVEL environment variable support"""

    def test_env_var_sets_log_level(self):
        """Test that CJA_LOG_LEVEL environment variable works"""
        with patch.dict(os.environ, {'CJA_LOG_LEVEL': 'WARNING'}):
            logger = setup_logging('test_dv', batch_mode=False)
            # Check root logger level since basicConfig sets it
            assert logging.root.level == logging.WARNING

    def test_env_var_overridden_by_parameter(self):
        """Test that explicit parameter overrides environment variable"""
        with patch.dict(os.environ, {'CJA_LOG_LEVEL': 'WARNING'}):
            logger = setup_logging('test_dv', batch_mode=False, log_level='DEBUG')
            # Check root logger level
            assert logging.root.level == logging.DEBUG

    def test_invalid_env_var_falls_back_to_info(self):
        """Test that invalid CJA_LOG_LEVEL falls back to INFO"""
        with patch.dict(os.environ, {'CJA_LOG_LEVEL': 'INVALID'}):
            logger = setup_logging('test_dv', batch_mode=False)
            # Check root logger level
            assert logging.root.level == logging.INFO


class TestDataQualityLogging:
    """Test data quality issue logging optimizations"""

    def test_low_severity_not_logged_in_info_mode(self, caplog):
        """Test that LOW severity issues are not logged in INFO mode"""
        logger = logging.getLogger("test_info")
        logger.setLevel(logging.INFO)

        dq_checker = DataQualityChecker(logger)

        with caplog.at_level(logging.INFO):
            dq_checker.add_issue(
                severity='LOW',
                category='Test',
                item_type='Metrics',
                item_name='test_metric',
                description='Low severity test issue',
                details='Details'
            )

        # Should NOT have individual log entry for LOW severity
        assert not any('Low severity test issue' in record.message for record in caplog.records)

    def test_critical_issues_logged_in_warning_mode(self, caplog):
        """Test that CRITICAL issues are logged even in WARNING mode"""
        logger = logging.getLogger("test_warning")
        logger.setLevel(logging.WARNING)

        dq_checker = DataQualityChecker(logger)

        with caplog.at_level(logging.WARNING):
            dq_checker.add_issue(
                severity='CRITICAL',
                category='Test',
                item_type='Metrics',
                item_name='test_metric',
                description='Critical issue',
                details='Details'
            )

        # Should have warning log entry for CRITICAL severity
        assert any('CRITICAL' in record.message for record in caplog.records)

    def test_all_issues_logged_in_debug_mode(self, caplog):
        """Test that all issues are logged in DEBUG mode"""
        logger = logging.getLogger("test_debug")
        logger.setLevel(logging.DEBUG)

        dq_checker = DataQualityChecker(logger)

        with caplog.at_level(logging.DEBUG):
            dq_checker.add_issue(
                severity='LOW',
                category='Test',
                item_type='Metrics',
                item_name='test_metric',
                description='Debug test issue',
                details='Details'
            )

        # Should have debug log entry
        assert any('Debug test issue' in record.message for record in caplog.records)


class TestSummaryLogging:
    """Test aggregated summary logging"""

    def test_summary_with_no_issues(self, caplog):
        """Test summary logging when no issues found"""
        logger = logging.getLogger("test_no_issues")
        logger.setLevel(logging.INFO)

        dq_checker = DataQualityChecker(logger)

        with caplog.at_level(logging.INFO):
            dq_checker.log_summary()

        # Should log success message
        assert any('No data quality issues found' in record.message for record in caplog.records)

    def test_summary_with_multiple_issues(self, caplog):
        """Test summary logging with multiple issues"""
        logger = logging.getLogger("test_summary")
        logger.setLevel(logging.INFO)

        dq_checker = DataQualityChecker(logger)

        # Add multiple issues
        for i in range(5):
            dq_checker.add_issue(
                severity='MEDIUM',
                category='Test',
                item_type='Metrics',
                item_name=f'metric_{i}',
                description=f'Issue {i}',
                details=''
            )

        with caplog.at_level(logging.INFO):
            dq_checker.log_summary()

        # Should have summary with count
        assert any('5 issue(s)' in record.message for record in caplog.records)
        assert any('MEDIUM: 5' in record.message for record in caplog.records)

    def test_summary_aggregates_by_severity(self, caplog):
        """Test that summary properly aggregates by severity"""
        logger = logging.getLogger("test_agg")
        logger.setLevel(logging.INFO)

        dq_checker = DataQualityChecker(logger)

        # Add issues of different severities
        dq_checker.add_issue('CRITICAL', 'Test', 'Metrics', 'metric1', 'Issue 1', '')
        dq_checker.add_issue('CRITICAL', 'Test', 'Metrics', 'metric2', 'Issue 2', '')
        dq_checker.add_issue('HIGH', 'Test', 'Dimensions', 'dim1', 'Issue 3', '')
        dq_checker.add_issue('MEDIUM', 'Test', 'Metrics', 'metric3', 'Issue 4', '')

        with caplog.at_level(logging.INFO):
            dq_checker.log_summary()

        # Should show breakdown
        assert any('CRITICAL: 2' in record.message for record in caplog.records)
        assert any('HIGH: 1' in record.message for record in caplog.records)
        assert any('MEDIUM: 1' in record.message for record in caplog.records)


class TestPerformanceTrackerLogging:
    """Test performance tracker logging levels"""

    def test_perf_tracker_not_logged_in_info_mode(self, caplog):
        """Test that individual operations are NOT logged in INFO mode"""
        logger = logging.getLogger("test_perf_info")
        logger.setLevel(logging.INFO)

        tracker = PerformanceTracker(logger)

        caplog.clear()
        with caplog.at_level(logging.INFO):
            tracker.start("Test Operation")
            tracker.end("Test Operation")

        # Should NOT have individual operation log
        assert not any('completed in' in record.message for record in caplog.records)

    def test_perf_tracker_logged_in_debug_mode(self, caplog):
        """Test that individual operations are logged in DEBUG mode"""
        logger = logging.getLogger("test_perf_debug")
        logger.setLevel(logging.DEBUG)

        tracker = PerformanceTracker(logger)

        with caplog.at_level(logging.DEBUG):
            tracker.start("Test Operation")
            tracker.end("Test Operation")

        # Should have debug log entry
        assert any('completed in' in record.message for record in caplog.records)


class TestBackwardCompatibility:
    """Test backward compatibility"""

    def test_issues_still_collected(self):
        """Test that issues are still collected in issues list"""
        logger = logging.getLogger("test_compat")
        logger.setLevel(logging.WARNING)  # Production mode level

        dq_checker = DataQualityChecker(logger)

        # Add low severity issue - won't be logged but should be collected
        dq_checker.add_issue('LOW', 'Test', 'Metrics', 'metric1', 'Issue 1', 'Details')

        # Issue should still be in list
        assert len(dq_checker.issues) == 1
        assert dq_checker.issues[0]['Severity'] == 'LOW'

    def test_get_issues_dataframe_still_works(self):
        """Test that get_issues_dataframe still works correctly"""
        logger = logging.getLogger("test_df")
        logger.setLevel(logging.WARNING)

        dq_checker = DataQualityChecker(logger)

        dq_checker.add_issue('HIGH', 'Test', 'Metrics', 'metric1', 'Issue 1', 'Details')
        dq_checker.add_issue('LOW', 'Test', 'Dimensions', 'dim1', 'Issue 2', 'Details')

        issues_df = dq_checker.get_issues_dataframe()

        # DataFrame should have both issues
        assert len(issues_df) == 2
        assert isinstance(issues_df, pd.DataFrame)
