"""Tests for data quality validation"""
import pytest
import sys
import pandas as pd
import logging
import os


# Import the class we're testing
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cja_sdr_generator import DataQualityChecker


class TestDataQualityValidation:
    """Test data quality validation functions"""

    def test_duplicate_detection_metrics(self, sample_metrics_df):
        """Test detection of duplicate metric names"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        # Add a duplicate
        duplicate_df = pd.concat([
            sample_metrics_df,
            pd.DataFrame([{
                "id": "metric3",
                "name": "Test Metric 1",  # Duplicate name
                "type": "calculated",
                "title": "Duplicate Metric",
                "description": "Duplicate"
            }])
        ], ignore_index=True)

        validator.check_duplicates(duplicate_df, "Metrics")
        issues_df = validator.get_issues_dataframe()

        # Should detect duplicate names
        assert len(issues_df) > 0
        assert any('duplicate' in str(row['Issue']).lower() for _, row in issues_df.iterrows())

    def test_duplicate_detection_dimensions(self, sample_dimensions_df):
        """Test detection of duplicate dimension names"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        validator.check_duplicates(sample_dimensions_df, "Dimensions")
        issues_df = validator.get_issues_dataframe()

        # sample_dimensions_df already has duplicates
        assert len(issues_df) > 0

    def test_missing_description_detection(self, sample_metrics_df):
        """Test detection of missing descriptions"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        validator.check_missing_descriptions(sample_metrics_df, "Metrics")
        issues_df = validator.get_issues_dataframe()

        # Should detect missing description in metric2
        assert len(issues_df) > 0

    def test_null_value_detection(self, sample_metrics_df):
        """Test detection of null values in critical fields"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        validator.check_null_values(sample_metrics_df, "Metrics", ["id", "name", "description"])
        issues_df = validator.get_issues_dataframe()

        # Should detect null values
        assert len(issues_df) > 0

    def test_empty_dataset_detection(self):
        """Test detection of empty datasets"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        empty_df = pd.DataFrame()
        validator.check_empty_dataframe(empty_df, "Metrics")
        issues_df = validator.get_issues_dataframe()

        # Should detect empty dataset
        assert len(issues_df) > 0
        assert any('empty' in str(row['Issue']).lower() or 'no' in str(row['Issue']).lower()
                  for _, row in issues_df.iterrows())

    def test_severity_levels(self, sample_metrics_df):
        """Test that severity levels are assigned correctly"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        validator.check_missing_descriptions(sample_metrics_df, "Metrics")
        issues_df = validator.get_issues_dataframe()

        # Check that severity levels are valid
        valid_severities = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO']
        for _, issue in issues_df.iterrows():
            assert issue['Severity'] in valid_severities

    def test_issue_structure(self, sample_metrics_df):
        """Test that issues have required fields"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        validator.check_missing_descriptions(sample_metrics_df, "Metrics")
        issues_df = validator.get_issues_dataframe()

        required_fields = ['Severity', 'Category', 'Type', 'Item Name', 'Issue', 'Details']
        for field in required_fields:
            assert field in issues_df.columns

    def test_required_field_validation(self):
        """Test validation of required fields"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        # Create DataFrame with missing required fields
        incomplete_df = pd.DataFrame([
            {
                "id": "metric1",
                "name": None,  # Missing required field
                "type": "calculated"
            }
        ])

        validator.check_required_fields(incomplete_df, "Metrics", ["id", "name", "type"])
        issues_df = validator.get_issues_dataframe()

        # Should detect missing required fields
        assert len(issues_df) > 0

    def test_id_validity_check(self):
        """Test ID validity checking"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        # Create DataFrame with invalid IDs
        df_with_invalid_ids = pd.DataFrame([
            {"id": None, "name": "Test 1", "type": "metric"},
            {"id": "", "name": "Test 2", "type": "metric"},
            {"id": "valid_id", "name": "Test 3", "type": "metric"}
        ])

        validator.check_id_validity(df_with_invalid_ids, "Metrics")
        issues_df = validator.get_issues_dataframe()

        # Should detect invalid IDs
        assert len(issues_df) > 0

    def test_multiple_checks_combined(self, sample_metrics_df, sample_dimensions_df):
        """Test running multiple validation checks"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        # Run multiple checks
        validator.check_duplicates(sample_metrics_df, "Metrics")
        validator.check_missing_descriptions(sample_metrics_df, "Metrics")
        validator.check_null_values(sample_metrics_df, "Metrics", ["description"])
        validator.check_duplicates(sample_dimensions_df, "Dimensions")

        issues_df = validator.get_issues_dataframe()

        # Should have issues from multiple checks
        assert len(issues_df) > 0
        # Should have both Metrics and Dimensions issues
        assert "Metrics" in issues_df['Type'].values
        assert "Dimensions" in issues_df['Type'].values
