"""Tests for process_single_dataview function"""
import pytest
import pandas as pd
import logging
import sys
import os
import json
import tempfile
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, PropertyMock

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cja_sdr_generator import (
    process_single_dataview,
    process_single_dataview_worker,
    ProcessingResult
)


@pytest.fixture
def mock_config_file(tmp_path):
    """Create a temporary config file"""
    config_data = {
        "org_id": "test_org@AdobeOrg",
        "client_id": "test_client_id",
        "secret": "test_secret",
        "scopes": "openid, AdobeID"
    }
    config_file = tmp_path / "test_config.json"
    config_file.write_text(json.dumps(config_data))
    return str(config_file)


@pytest.fixture
def temp_output_dir(tmp_path):
    """Create a temporary output directory"""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return str(output_dir)


@pytest.fixture
def sample_metrics_df():
    """Sample metrics DataFrame"""
    return pd.DataFrame([
        {"id": "metric1", "name": "Metric 1", "type": "calculated", "description": "Test metric", "title": "Metric 1"},
        {"id": "metric2", "name": "Metric 2", "type": "standard", "description": "Test metric 2", "title": "Metric 2"}
    ])


@pytest.fixture
def sample_dimensions_df():
    """Sample dimensions DataFrame"""
    return pd.DataFrame([
        {"id": "dim1", "name": "Dimension 1", "type": "string", "description": "Test dim", "title": "Dimension 1"},
        {"id": "dim2", "name": "Dimension 2", "type": "string", "description": "Test dim 2", "title": "Dimension 2"}
    ])


@pytest.fixture
def sample_dataview_info():
    """Sample data view info"""
    return {
        "id": "dv_test_12345",
        "name": "Test Data View",
        "owner": {"name": "Test Owner"},
        "description": "Test description"
    }


class TestProcessSingleDataviewSuccess:
    """Tests for successful processing scenarios"""

    @patch('cja_sdr_generator.setup_logging')
    @patch('cja_sdr_generator.initialize_cja')
    @patch('cja_sdr_generator.validate_data_view')
    @patch('cja_sdr_generator.ParallelAPIFetcher')
    @patch('cja_sdr_generator.DataQualityChecker')
    @patch('cja_sdr_generator.apply_excel_formatting')
    @patch('pandas.ExcelWriter')
    def test_successful_processing(self, mock_excel_writer, mock_apply_formatting,
                                    mock_dq_checker_class, mock_fetcher_class,
                                    mock_validate_dv, mock_init_cja, mock_setup_logging,
                                    mock_config_file, temp_output_dir,
                                    sample_metrics_df, sample_dimensions_df, sample_dataview_info):
        """Test successful end-to-end processing"""
        # Setup mocks
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger

        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja
        mock_validate_dv.return_value = True

        # Setup fetcher
        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        # Setup data quality checker
        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(columns=['Severity', 'Category', 'Type', 'Item Name', 'Issue', 'Details'])
        mock_dq_checker_class.return_value = mock_dq_checker

        # Setup Excel writer
        mock_writer = MagicMock()
        mock_excel_writer.return_value.__enter__ = Mock(return_value=mock_writer)
        mock_excel_writer.return_value.__exit__ = Mock(return_value=False)

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir
        )

        assert result.success is True
        assert result.data_view_id == "dv_test_12345"
        assert result.data_view_name == "Test Data View"
        assert result.metrics_count == 2
        assert result.dimensions_count == 2

    @patch('cja_sdr_generator.setup_logging')
    @patch('cja_sdr_generator.initialize_cja')
    @patch('cja_sdr_generator.validate_data_view')
    @patch('cja_sdr_generator.ParallelAPIFetcher')
    @patch('cja_sdr_generator.DataQualityChecker')
    @patch('cja_sdr_generator.apply_excel_formatting')
    @patch('pandas.ExcelWriter')
    def test_processing_with_cache_disabled(self, mock_excel_writer, mock_apply_formatting,
                                              mock_dq_checker_class, mock_fetcher_class,
                                              mock_validate_dv, mock_init_cja, mock_setup_logging,
                                              mock_config_file, temp_output_dir,
                                              sample_metrics_df, sample_dimensions_df, sample_dataview_info):
        """Test processing with cache disabled (default)"""
        mock_logger = Mock()
        mock_logger.handlers = []  # Make handlers iterable
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja
        mock_validate_dv.return_value = True

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(columns=['Severity', 'Category', 'Type', 'Item Name', 'Issue', 'Details'])
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_writer = MagicMock()
        mock_excel_writer.return_value.__enter__ = Mock(return_value=mock_writer)
        mock_excel_writer.return_value.__exit__ = Mock(return_value=False)

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            enable_cache=False  # Default behavior
        )

        assert result.success is True
        # DataQualityChecker should be called with no cache
        mock_dq_checker_class.assert_called_once()


class TestProcessSingleDataviewFailures:
    """Tests for failure scenarios"""

    @patch('cja_sdr_generator.setup_logging')
    @patch('cja_sdr_generator.initialize_cja')
    def test_cja_initialization_failure(self, mock_init_cja, mock_setup_logging,
                                         mock_config_file, temp_output_dir):
        """Test handling of CJA initialization failure"""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_init_cja.return_value = None

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir
        )

        assert result.success is False
        assert "initialization failed" in result.error_message.lower()

    @patch('cja_sdr_generator.setup_logging')
    @patch('cja_sdr_generator.initialize_cja')
    @patch('cja_sdr_generator.validate_data_view')
    def test_data_view_validation_failure(self, mock_validate_dv, mock_init_cja,
                                           mock_setup_logging, mock_config_file, temp_output_dir):
        """Test handling of data view validation failure"""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja
        mock_validate_dv.return_value = False

        result = process_single_dataview(
            data_view_id="dv_invalid",
            config_file=mock_config_file,
            output_dir=temp_output_dir
        )

        assert result.success is False
        assert "validation failed" in result.error_message.lower()

    @patch('cja_sdr_generator.setup_logging')
    @patch('cja_sdr_generator.initialize_cja')
    @patch('cja_sdr_generator.validate_data_view')
    @patch('cja_sdr_generator.ParallelAPIFetcher')
    def test_empty_data_fetched(self, mock_fetcher_class, mock_validate_dv,
                                 mock_init_cja, mock_setup_logging,
                                 mock_config_file, temp_output_dir, sample_dataview_info):
        """Test handling of empty metrics and dimensions"""
        mock_logger = Mock()
        mock_logger.handlers = []  # Make handlers iterable
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja
        mock_validate_dv.return_value = True

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (pd.DataFrame(), pd.DataFrame(), sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir
        )

        assert result.success is False
        assert "no metrics or dimensions" in result.error_message.lower()

    @patch('cja_sdr_generator.setup_logging')
    @patch('cja_sdr_generator.initialize_cja')
    @patch('cja_sdr_generator.validate_data_view')
    @patch('cja_sdr_generator.ParallelAPIFetcher')
    @patch('cja_sdr_generator.DataQualityChecker')
    @patch('pandas.ExcelWriter')
    def test_permission_error_writing_file(self, mock_excel_writer, mock_dq_checker_class,
                                            mock_fetcher_class, mock_validate_dv,
                                            mock_init_cja, mock_setup_logging,
                                            mock_config_file, temp_output_dir,
                                            sample_metrics_df, sample_dimensions_df, sample_dataview_info):
        """Test handling of permission error when writing output"""
        mock_logger = Mock()
        mock_logger.handlers = []  # Make handlers iterable
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja
        mock_validate_dv.return_value = True

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(columns=['Severity', 'Category', 'Type', 'Item Name', 'Issue', 'Details'])
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_excel_writer.side_effect = PermissionError("File is open")

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir
        )

        assert result.success is False
        assert "permission" in result.error_message.lower()


class TestProcessSingleDataviewOutputFormats:
    """Tests for different output formats"""

    @patch('cja_sdr_generator.setup_logging')
    @patch('cja_sdr_generator.initialize_cja')
    @patch('cja_sdr_generator.validate_data_view')
    @patch('cja_sdr_generator.ParallelAPIFetcher')
    @patch('cja_sdr_generator.DataQualityChecker')
    @patch('cja_sdr_generator.write_csv_output')
    def test_csv_output_format(self, mock_write_csv, mock_dq_checker_class,
                                mock_fetcher_class, mock_validate_dv,
                                mock_init_cja, mock_setup_logging,
                                mock_config_file, temp_output_dir,
                                sample_metrics_df, sample_dimensions_df, sample_dataview_info):
        """Test CSV output format"""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja
        mock_validate_dv.return_value = True

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(columns=['Severity', 'Category', 'Type', 'Item Name', 'Issue', 'Details'])
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_write_csv.return_value = f"{temp_output_dir}/test_csv"

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            output_format="csv"
        )

        assert result.success is True
        mock_write_csv.assert_called_once()

    @patch('cja_sdr_generator.setup_logging')
    @patch('cja_sdr_generator.initialize_cja')
    @patch('cja_sdr_generator.validate_data_view')
    @patch('cja_sdr_generator.ParallelAPIFetcher')
    @patch('cja_sdr_generator.DataQualityChecker')
    @patch('cja_sdr_generator.write_json_output')
    def test_json_output_format(self, mock_write_json, mock_dq_checker_class,
                                 mock_fetcher_class, mock_validate_dv,
                                 mock_init_cja, mock_setup_logging,
                                 mock_config_file, temp_output_dir,
                                 sample_metrics_df, sample_dimensions_df, sample_dataview_info):
        """Test JSON output format"""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja
        mock_validate_dv.return_value = True

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(columns=['Severity', 'Category', 'Type', 'Item Name', 'Issue', 'Details'])
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_write_json.return_value = f"{temp_output_dir}/test.json"

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            output_format="json"
        )

        assert result.success is True
        mock_write_json.assert_called_once()

    @patch('cja_sdr_generator.setup_logging')
    @patch('cja_sdr_generator.initialize_cja')
    @patch('cja_sdr_generator.validate_data_view')
    @patch('cja_sdr_generator.ParallelAPIFetcher')
    @patch('cja_sdr_generator.DataQualityChecker')
    @patch('cja_sdr_generator.write_html_output')
    def test_html_output_format(self, mock_write_html, mock_dq_checker_class,
                                 mock_fetcher_class, mock_validate_dv,
                                 mock_init_cja, mock_setup_logging,
                                 mock_config_file, temp_output_dir,
                                 sample_metrics_df, sample_dimensions_df, sample_dataview_info):
        """Test HTML output format"""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja
        mock_validate_dv.return_value = True

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(columns=['Severity', 'Category', 'Type', 'Item Name', 'Issue', 'Details'])
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_write_html.return_value = f"{temp_output_dir}/test.html"

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            output_format="html"
        )

        assert result.success is True
        mock_write_html.assert_called_once()

    @patch('cja_sdr_generator.setup_logging')
    @patch('cja_sdr_generator.initialize_cja')
    @patch('cja_sdr_generator.validate_data_view')
    @patch('cja_sdr_generator.ParallelAPIFetcher')
    @patch('cja_sdr_generator.DataQualityChecker')
    @patch('cja_sdr_generator.write_markdown_output')
    def test_markdown_output_format(self, mock_write_md, mock_dq_checker_class,
                                     mock_fetcher_class, mock_validate_dv,
                                     mock_init_cja, mock_setup_logging,
                                     mock_config_file, temp_output_dir,
                                     sample_metrics_df, sample_dimensions_df, sample_dataview_info):
        """Test Markdown output format"""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja
        mock_validate_dv.return_value = True

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(columns=['Severity', 'Category', 'Type', 'Item Name', 'Issue', 'Details'])
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_write_md.return_value = f"{temp_output_dir}/test.md"

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            output_format="markdown"
        )

        assert result.success is True
        mock_write_md.assert_called_once()


class TestProcessSingleDataviewCaching:
    """Tests for caching functionality"""

    @patch('cja_sdr_generator.setup_logging')
    @patch('cja_sdr_generator.initialize_cja')
    @patch('cja_sdr_generator.validate_data_view')
    @patch('cja_sdr_generator.ParallelAPIFetcher')
    @patch('cja_sdr_generator.ValidationCache')
    @patch('cja_sdr_generator.DataQualityChecker')
    @patch('cja_sdr_generator.apply_excel_formatting')
    @patch('pandas.ExcelWriter')
    def test_cache_enabled(self, mock_excel_writer, mock_apply_formatting,
                            mock_dq_checker_class, mock_cache_class,
                            mock_fetcher_class, mock_validate_dv,
                            mock_init_cja, mock_setup_logging,
                            mock_config_file, temp_output_dir,
                            sample_metrics_df, sample_dimensions_df, sample_dataview_info):
        """Test that cache is created when enabled"""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja
        mock_validate_dv.return_value = True

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_cache = Mock()
        mock_cache_class.return_value = mock_cache

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(columns=['Severity', 'Category', 'Type', 'Item Name', 'Issue', 'Details'])
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_writer = MagicMock()
        mock_excel_writer.return_value.__enter__ = Mock(return_value=mock_writer)
        mock_excel_writer.return_value.__exit__ = Mock(return_value=False)

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            enable_cache=True,
            cache_size=500,
            cache_ttl=1800
        )

        assert result.success is True
        mock_cache_class.assert_called_once()

    @patch('cja_sdr_generator.setup_logging')
    @patch('cja_sdr_generator.initialize_cja')
    @patch('cja_sdr_generator.validate_data_view')
    @patch('cja_sdr_generator.ParallelAPIFetcher')
    @patch('cja_sdr_generator.ValidationCache')
    @patch('cja_sdr_generator.DataQualityChecker')
    @patch('cja_sdr_generator.apply_excel_formatting')
    @patch('pandas.ExcelWriter')
    def test_clear_cache_option(self, mock_excel_writer, mock_apply_formatting,
                                 mock_dq_checker_class, mock_cache_class,
                                 mock_fetcher_class, mock_validate_dv,
                                 mock_init_cja, mock_setup_logging,
                                 mock_config_file, temp_output_dir,
                                 sample_metrics_df, sample_dimensions_df, sample_dataview_info):
        """Test that cache is cleared when clear_cache=True"""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja
        mock_validate_dv.return_value = True

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_cache = Mock()
        mock_cache_class.return_value = mock_cache

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(columns=['Severity', 'Category', 'Type', 'Item Name', 'Issue', 'Details'])
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_writer = MagicMock()
        mock_excel_writer.return_value.__enter__ = Mock(return_value=mock_writer)
        mock_excel_writer.return_value.__exit__ = Mock(return_value=False)

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            enable_cache=True,
            clear_cache=True
        )

        assert result.success is True
        mock_cache.clear.assert_called_once()


class TestProcessSingleDataviewWorker:
    """Tests for the worker wrapper function"""

    @patch('cja_sdr_generator.process_single_dataview')
    def test_worker_unpacks_args(self, mock_process):
        """Test that worker correctly unpacks arguments"""
        expected_result = ProcessingResult(
            data_view_id="dv_test_12345",
            data_view_name="Test",
            success=True,
            duration=1.0
        )
        mock_process.return_value = expected_result

        args = (
            "dv_test_12345",  # data_view_id
            "config.json",   # config_file
            "/output",       # output_dir
            "INFO",          # log_level
            "text",          # log_format
            "excel",         # output_format
            False,           # enable_cache
            1000,            # cache_size
            3600,            # cache_ttl
            False,           # quiet
            False,           # skip_validation
            0,               # max_issues
            False,           # clear_cache
            False,           # show_timings
            False,           # metrics_only
            False,           # dimensions_only
            None             # profile
        )

        result = process_single_dataview_worker(args)

        assert result == expected_result
        mock_process.assert_called_once_with(
            "dv_test_12345", "config.json", "/output", "INFO", "text", "excel",
            False, 1000, 3600, False, False, 0, False, False, False, False, profile=None
        )


class TestProcessSingleDataviewFilenaming:
    """Tests for file naming logic"""

    @patch('cja_sdr_generator.setup_logging')
    @patch('cja_sdr_generator.initialize_cja')
    @patch('cja_sdr_generator.validate_data_view')
    @patch('cja_sdr_generator.ParallelAPIFetcher')
    @patch('cja_sdr_generator.DataQualityChecker')
    @patch('cja_sdr_generator.apply_excel_formatting')
    @patch('pandas.ExcelWriter')
    def test_filename_sanitization(self, mock_excel_writer, mock_apply_formatting,
                                    mock_dq_checker_class, mock_fetcher_class,
                                    mock_validate_dv, mock_init_cja, mock_setup_logging,
                                    mock_config_file, temp_output_dir,
                                    sample_metrics_df, sample_dimensions_df):
        """Test that special characters are removed from filenames"""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja
        mock_validate_dv.return_value = True

        # Data view with special characters in name
        special_name_info = {
            "id": "dv_test_12345",
            "name": "Test/View:With*Special<Chars>",
            "owner": {"name": "Test Owner"}
        }

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, special_name_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(columns=['Severity', 'Category', 'Type', 'Item Name', 'Issue', 'Details'])
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_writer = MagicMock()
        mock_excel_writer.return_value.__enter__ = Mock(return_value=mock_writer)
        mock_excel_writer.return_value.__exit__ = Mock(return_value=False)

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir
        )

        assert result.success is True
        # The filename should have special characters removed
        assert result.output_file is not None
        assert "/" not in Path(result.output_file).name
        assert ":" not in Path(result.output_file).name


class TestProcessSingleDataviewMaxIssues:
    """Tests for max_issues parameter"""

    @patch('cja_sdr_generator.setup_logging')
    @patch('cja_sdr_generator.initialize_cja')
    @patch('cja_sdr_generator.validate_data_view')
    @patch('cja_sdr_generator.ParallelAPIFetcher')
    @patch('cja_sdr_generator.DataQualityChecker')
    @patch('cja_sdr_generator.apply_excel_formatting')
    @patch('pandas.ExcelWriter')
    def test_max_issues_parameter_passed(self, mock_excel_writer, mock_apply_formatting,
                                          mock_dq_checker_class, mock_fetcher_class,
                                          mock_validate_dv, mock_init_cja, mock_setup_logging,
                                          mock_config_file, temp_output_dir,
                                          sample_metrics_df, sample_dimensions_df, sample_dataview_info):
        """Test that max_issues parameter is passed to get_issues_dataframe"""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja
        mock_validate_dv.return_value = True

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(columns=['Severity', 'Category', 'Type', 'Item Name', 'Issue', 'Details'])
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_writer = MagicMock()
        mock_excel_writer.return_value.__enter__ = Mock(return_value=mock_writer)
        mock_excel_writer.return_value.__exit__ = Mock(return_value=False)

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            max_issues=10
        )

        assert result.success is True
        mock_dq_checker.get_issues_dataframe.assert_called_once_with(max_issues=10)


class TestProcessingResultDataclass:
    """Tests for ProcessingResult dataclass"""

    def test_processing_result_success(self):
        """Test ProcessingResult for successful processing"""
        result = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test",
            success=True,
            duration=5.0,
            metrics_count=100,
            dimensions_count=50,
            dq_issues_count=5,
            output_file="/path/to/file.xlsx",
            file_size_bytes=1024
        )

        assert result.success is True
        assert result.metrics_count == 100
        assert result.dimensions_count == 50
        assert result.dq_issues_count == 5

    def test_processing_result_failure(self):
        """Test ProcessingResult for failed processing"""
        result = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test",
            success=False,
            duration=1.0,
            error_message="Connection failed"
        )

        assert result.success is False
        assert result.error_message == "Connection failed"

    def test_processing_result_file_size_formatted(self):
        """Test file_size_formatted property"""
        result = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test",
            success=True,
            duration=1.0,
            file_size_bytes=1536  # 1.5 KB
        )

        formatted = result.file_size_formatted
        assert "KB" in formatted or "B" in formatted
