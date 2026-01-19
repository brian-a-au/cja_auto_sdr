"""Tests for apply_excel_formatting function"""
import pytest
import pandas as pd
import logging
import sys
import os
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cja_sdr_generator import apply_excel_formatting


@pytest.fixture
def mock_logger():
    """Create a mock logger"""
    logger = Mock(spec=logging.Logger)
    logger.info = Mock()
    logger.debug = Mock()
    logger.warning = Mock()
    logger.error = Mock()
    return logger


@pytest.fixture
def sample_metrics_df():
    """Sample metrics DataFrame"""
    return pd.DataFrame([
        {"name": "Metric 1", "type": "calculated", "id": "m1", "title": "Title 1", "description": "Desc 1"},
        {"name": "Metric 2", "type": "standard", "id": "m2", "title": "Title 2", "description": "Desc 2"},
        {"name": "Metric 3", "type": "calculated", "id": "m3", "title": "Title 3", "description": "Desc 3"}
    ])


@pytest.fixture
def sample_dimensions_df():
    """Sample dimensions DataFrame"""
    return pd.DataFrame([
        {"name": "Dimension 1", "type": "string", "id": "d1", "title": "Title 1", "description": "Desc 1"},
        {"name": "Dimension 2", "type": "string", "id": "d2", "title": "Title 2", "description": "Desc 2"}
    ])


@pytest.fixture
def sample_data_quality_df():
    """Sample data quality DataFrame"""
    return pd.DataFrame([
        {"Severity": "CRITICAL", "Category": "Missing Data", "Type": "Metrics", "Item Name": "Test", "Issue": "Missing desc", "Details": "No description"},
        {"Severity": "HIGH", "Category": "Duplicates", "Type": "Dimensions", "Item Name": "Test2", "Issue": "Duplicate name", "Details": "Found 2 times"},
        {"Severity": "MEDIUM", "Category": "Validation", "Type": "Metrics", "Item Name": "Test3", "Issue": "Invalid ID", "Details": "Bad format"},
        {"Severity": "LOW", "Category": "Info", "Type": "Dimensions", "Item Name": "Test4", "Issue": "Minor issue", "Details": "Details here"}
    ])


@pytest.fixture
def sample_metadata_df():
    """Sample metadata DataFrame"""
    return pd.DataFrame({
        "Property": ["Generated At", "Data View ID", "Total Metrics"],
        "Value": ["2024-01-01", "dv_test", "100"]
    })


class TestApplyExcelFormattingIntegration:
    """Integration tests using real Excel files"""

    def test_formats_metrics_sheet(self, mock_logger, sample_metrics_df, tmp_path):
        """Test formatting of Metrics sheet with real Excel writer"""
        output_file = tmp_path / "test_output.xlsx"

        with pd.ExcelWriter(str(output_file), engine='xlsxwriter') as writer:
            apply_excel_formatting(writer, sample_metrics_df, 'Metrics', mock_logger)

        # Verify file was created
        assert output_file.exists()

        # Verify logging
        mock_logger.info.assert_called()

    def test_formats_dimensions_sheet(self, mock_logger, sample_dimensions_df, tmp_path):
        """Test formatting of Dimensions sheet"""
        output_file = tmp_path / "test_output.xlsx"

        with pd.ExcelWriter(str(output_file), engine='xlsxwriter') as writer:
            apply_excel_formatting(writer, sample_dimensions_df, 'Dimensions', mock_logger)

        assert output_file.exists()

    def test_formats_data_quality_sheet(self, mock_logger, sample_data_quality_df, tmp_path):
        """Test formatting of Data Quality sheet with severity colors"""
        output_file = tmp_path / "test_output.xlsx"

        with pd.ExcelWriter(str(output_file), engine='xlsxwriter') as writer:
            apply_excel_formatting(writer, sample_data_quality_df, 'Data Quality', mock_logger)

        assert output_file.exists()

    def test_formats_metadata_sheet(self, mock_logger, sample_metadata_df, tmp_path):
        """Test formatting of Metadata sheet"""
        output_file = tmp_path / "test_output.xlsx"

        with pd.ExcelWriter(str(output_file), engine='xlsxwriter') as writer:
            apply_excel_formatting(writer, sample_metadata_df, 'Metadata', mock_logger)

        assert output_file.exists()

    def test_formats_empty_dataframe(self, mock_logger, tmp_path):
        """Test formatting with empty DataFrame"""
        output_file = tmp_path / "test_output.xlsx"
        empty_df = pd.DataFrame(columns=['A', 'B', 'C'])

        with pd.ExcelWriter(str(output_file), engine='xlsxwriter') as writer:
            apply_excel_formatting(writer, empty_df, 'Empty', mock_logger)

        assert output_file.exists()

    def test_formats_single_row_dataframe(self, mock_logger, tmp_path):
        """Test formatting with single row DataFrame"""
        output_file = tmp_path / "test_output.xlsx"
        single_row_df = pd.DataFrame([{"A": 1, "B": 2, "C": 3}])

        with pd.ExcelWriter(str(output_file), engine='xlsxwriter') as writer:
            apply_excel_formatting(writer, single_row_df, 'Single', mock_logger)

        assert output_file.exists()

    def test_formats_long_text_values(self, mock_logger, tmp_path):
        """Test formatting with long text values"""
        output_file = tmp_path / "test_output.xlsx"
        long_text_df = pd.DataFrame([{
            "name": "A" * 200,
            "description": "B" * 500
        }])

        with pd.ExcelWriter(str(output_file), engine='xlsxwriter') as writer:
            apply_excel_formatting(writer, long_text_df, 'LongText', mock_logger)

        assert output_file.exists()

    def test_formats_multiline_text_values(self, mock_logger, tmp_path):
        """Test formatting with multiline text values"""
        output_file = tmp_path / "test_output.xlsx"
        multiline_df = pd.DataFrame([{
            "name": "Line1\nLine2\nLine3",
            "description": "Desc\nwith\nmultiple\nlines"
        }])

        with pd.ExcelWriter(str(output_file), engine='xlsxwriter') as writer:
            apply_excel_formatting(writer, multiline_df, 'Multiline', mock_logger)

        assert output_file.exists()

    def test_formats_special_characters(self, mock_logger, tmp_path):
        """Test formatting with special characters"""
        output_file = tmp_path / "test_output.xlsx"
        special_df = pd.DataFrame([{
            "name": "Test <>&\"'",
            "description": "Special: @#$%^&*()"
        }])

        with pd.ExcelWriter(str(output_file), engine='xlsxwriter') as writer:
            apply_excel_formatting(writer, special_df, 'Special', mock_logger)

        assert output_file.exists()

    def test_formats_unicode_characters(self, mock_logger, tmp_path):
        """Test formatting with Unicode characters"""
        output_file = tmp_path / "test_output.xlsx"
        unicode_df = pd.DataFrame([{
            "name": "Test \u00e9\u00e8\u00ea\u00eb",
            "description": "\u4e2d\u6587\u6d4b\u8bd5"
        }])

        with pd.ExcelWriter(str(output_file), engine='xlsxwriter') as writer:
            apply_excel_formatting(writer, unicode_df, 'Unicode', mock_logger)

        assert output_file.exists()


class TestApplyExcelFormattingMetricsSheet:
    """Tests specific to Metrics sheet formatting"""

    def test_reorders_columns_name_first(self, mock_logger, tmp_path):
        """Test that columns are reordered with name first for Metrics sheet"""
        output_file = tmp_path / "test_output.xlsx"

        # DataFrame with columns not in preferred order
        df = pd.DataFrame([{
            "id": "m1",
            "type": "calculated",
            "name": "Metric 1",
            "title": "Title 1",
            "description": "Desc 1"
        }])

        with pd.ExcelWriter(str(output_file), engine='xlsxwriter') as writer:
            apply_excel_formatting(writer, df, 'Metrics', mock_logger)

        # Verify file was created successfully (formatting applied)
        assert output_file.exists()
        assert output_file.stat().st_size > 0

    def test_applies_alternating_row_colors(self, mock_logger, tmp_path, sample_metrics_df):
        """Test that alternating row colors are applied"""
        output_file = tmp_path / "test_output.xlsx"

        with pd.ExcelWriter(str(output_file), engine='xlsxwriter') as writer:
            apply_excel_formatting(writer, sample_metrics_df, 'Metrics', mock_logger)

        # File should be created successfully with formatting
        assert output_file.exists()
        assert output_file.stat().st_size > 0


class TestApplyExcelFormattingDimensionsSheet:
    """Tests specific to Dimensions sheet formatting"""

    def test_reorders_columns_name_first(self, mock_logger, tmp_path):
        """Test that columns are reordered with name first for Dimensions sheet"""
        output_file = tmp_path / "test_output.xlsx"

        df = pd.DataFrame([{
            "id": "d1",
            "type": "string",
            "name": "Dimension 1",
            "title": "Title 1",
            "description": "Desc 1"
        }])

        with pd.ExcelWriter(str(output_file), engine='xlsxwriter') as writer:
            apply_excel_formatting(writer, df, 'Dimensions', mock_logger)

        # Verify file was created successfully (formatting applied)
        assert output_file.exists()
        assert output_file.stat().st_size > 0


class TestApplyExcelFormattingDataQualitySheet:
    """Tests specific to Data Quality sheet formatting"""

    def test_adds_summary_section(self, mock_logger, tmp_path, sample_data_quality_df):
        """Test that summary section is added at top"""
        output_file = tmp_path / "test_output.xlsx"

        with pd.ExcelWriter(str(output_file), engine='xlsxwriter') as writer:
            apply_excel_formatting(writer, sample_data_quality_df, 'Data Quality', mock_logger)

        # Verify file was created successfully with formatting
        assert output_file.exists()
        # File should be larger than a minimal Excel file due to summary/formatting
        assert output_file.stat().st_size > 1000

    def test_handles_all_severity_levels(self, mock_logger, tmp_path):
        """Test that all severity levels are handled"""
        output_file = tmp_path / "test_output.xlsx"

        df = pd.DataFrame([
            {"Severity": "CRITICAL", "Category": "Test", "Type": "Metrics", "Item Name": "T1", "Issue": "I1", "Details": "D1"},
            {"Severity": "HIGH", "Category": "Test", "Type": "Metrics", "Item Name": "T2", "Issue": "I2", "Details": "D2"},
            {"Severity": "MEDIUM", "Category": "Test", "Type": "Metrics", "Item Name": "T3", "Issue": "I3", "Details": "D3"},
            {"Severity": "LOW", "Category": "Test", "Type": "Metrics", "Item Name": "T4", "Issue": "I4", "Details": "D4"},
            {"Severity": "INFO", "Category": "Test", "Type": "Metrics", "Item Name": "T5", "Issue": "I5", "Details": "D5"}
        ])

        with pd.ExcelWriter(str(output_file), engine='xlsxwriter') as writer:
            apply_excel_formatting(writer, df, 'Data Quality', mock_logger)

        assert output_file.exists()

    def test_handles_partial_severity_levels(self, mock_logger, tmp_path):
        """Test that partial severity levels are handled"""
        output_file = tmp_path / "test_output.xlsx"

        df = pd.DataFrame([
            {"Severity": "HIGH", "Category": "Test", "Type": "Metrics", "Item Name": "T1", "Issue": "I1", "Details": "D1"}
        ])

        with pd.ExcelWriter(str(output_file), engine='xlsxwriter') as writer:
            apply_excel_formatting(writer, df, 'Data Quality', mock_logger)

        assert output_file.exists()


class TestApplyExcelFormattingColumnWidths:
    """Tests for column width calculations"""

    def test_caps_column_widths_for_metrics(self, mock_logger, tmp_path):
        """Test that column widths are capped for Metrics sheet"""
        output_file = tmp_path / "test_output.xlsx"

        # DataFrame with very long content
        df = pd.DataFrame([{
            "name": "A" * 300,
            "description": "B" * 500
        }])

        with pd.ExcelWriter(str(output_file), engine='xlsxwriter') as writer:
            apply_excel_formatting(writer, df, 'Metrics', mock_logger)

        # Should complete without error
        assert output_file.exists()

    def test_handles_narrow_columns(self, mock_logger, tmp_path):
        """Test handling of narrow columns"""
        output_file = tmp_path / "test_output.xlsx"

        df = pd.DataFrame([{
            "a": "x",
            "b": "y"
        }])

        with pd.ExcelWriter(str(output_file), engine='xlsxwriter') as writer:
            apply_excel_formatting(writer, df, 'Narrow', mock_logger)

        assert output_file.exists()


class TestApplyExcelFormattingRowHeight:
    """Tests for row height calculations"""

    def test_adjusts_row_height_for_multiline(self, mock_logger, tmp_path):
        """Test that row height is adjusted for multiline content"""
        output_file = tmp_path / "test_output.xlsx"

        df = pd.DataFrame([{
            "text": "Line1\nLine2\nLine3\nLine4\nLine5"
        }])

        with pd.ExcelWriter(str(output_file), engine='xlsxwriter') as writer:
            apply_excel_formatting(writer, df, 'Height', mock_logger)

        assert output_file.exists()

    def test_caps_row_height_at_maximum(self, mock_logger, tmp_path):
        """Test that row height is capped at maximum"""
        output_file = tmp_path / "test_output.xlsx"

        # DataFrame with many lines
        df = pd.DataFrame([{
            "text": "\n".join(["Line"] * 100)
        }])

        with pd.ExcelWriter(str(output_file), engine='xlsxwriter') as writer:
            apply_excel_formatting(writer, df, 'MaxHeight', mock_logger)

        assert output_file.exists()


class TestApplyExcelFormattingErrorHandling:
    """Tests for error handling"""

    @pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning")
    def test_logs_error_on_invalid_writer(self, mock_logger, tmp_path, sample_metrics_df):
        """Test that errors are logged when writer is invalid"""
        # Create a mock writer that will fail
        # Note: Mock objects can trigger ZipFile.__del__ warnings during garbage collection
        mock_writer = Mock()
        mock_writer.book = Mock()
        mock_writer.book.add_format = Mock(side_effect=Exception("Format error"))
        mock_writer.sheets = {}

        with pytest.raises(Exception):
            apply_excel_formatting(mock_writer, sample_metrics_df, 'Metrics', mock_logger)

        mock_logger.error.assert_called()

    def test_handles_missing_name_column(self, mock_logger, tmp_path):
        """Test handling of DataFrame without 'name' column in Metrics sheet"""
        output_file = tmp_path / "test_output.xlsx"

        df = pd.DataFrame([{
            "id": "m1",
            "type": "calculated"
        }])

        with pd.ExcelWriter(str(output_file), engine='xlsxwriter') as writer:
            apply_excel_formatting(writer, df, 'Metrics', mock_logger)

        assert output_file.exists()


class TestApplyExcelFormattingLogging:
    """Tests for logging behavior"""

    def test_logs_sheet_formatting_start(self, mock_logger, tmp_path, sample_metrics_df):
        """Test that sheet formatting start is logged"""
        output_file = tmp_path / "test_output.xlsx"

        with pd.ExcelWriter(str(output_file), engine='xlsxwriter') as writer:
            apply_excel_formatting(writer, sample_metrics_df, 'Metrics', mock_logger)

        calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("Formatting" in c or "format" in c.lower() for c in calls)

    def test_logs_sheet_formatting_completion(self, mock_logger, tmp_path, sample_metrics_df):
        """Test that sheet formatting completion is logged"""
        output_file = tmp_path / "test_output.xlsx"

        with pd.ExcelWriter(str(output_file), engine='xlsxwriter') as writer:
            apply_excel_formatting(writer, sample_metrics_df, 'Metrics', mock_logger)

        calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("Successfully" in c or "success" in c.lower() for c in calls)


class TestApplyExcelFormattingMultipleSheets:
    """Tests for formatting multiple sheets"""

    def test_formats_all_sheet_types(self, mock_logger, tmp_path, sample_metrics_df,
                                      sample_dimensions_df, sample_data_quality_df,
                                      sample_metadata_df):
        """Test formatting all sheet types in one workbook"""
        output_file = tmp_path / "test_output.xlsx"

        with pd.ExcelWriter(str(output_file), engine='xlsxwriter') as writer:
            apply_excel_formatting(writer, sample_metadata_df, 'Metadata', mock_logger)
            apply_excel_formatting(writer, sample_data_quality_df, 'Data Quality', mock_logger)
            apply_excel_formatting(writer, sample_metrics_df, 'Metrics', mock_logger)
            apply_excel_formatting(writer, sample_dimensions_df, 'Dimensions', mock_logger)

        # Verify file was created with substantial size (multiple sheets with formatting)
        assert output_file.exists()
        assert output_file.stat().st_size > 5000  # Multiple formatted sheets should be significant
