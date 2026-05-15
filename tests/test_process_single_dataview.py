"""Tests for process_single_dataview function"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cja_auto_sdr.api.fetch import EndpointFetchStatus
from cja_auto_sdr.generator import (
    ProcessingConfig,
    ProcessingResult,
    WorkerArgs,
    process_single_dataview,
    process_single_dataview_worker,
)


@pytest.fixture
def mock_config_file(tmp_path):
    """Create a temporary config file"""
    config_data = {
        "org_id": "test_org@AdobeOrg",
        "client_id": "test_client_id",
        "secret": "test_secret",
        "scopes": "openid, AdobeID",
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
    return pd.DataFrame(
        [
            {
                "id": "metric1",
                "name": "Metric 1",
                "type": "calculated",
                "description": "Test metric",
                "title": "Metric 1",
            },
            {
                "id": "metric2",
                "name": "Metric 2",
                "type": "standard",
                "description": "Test metric 2",
                "title": "Metric 2",
            },
        ],
    )


@pytest.fixture
def sample_dimensions_df():
    """Sample dimensions DataFrame"""
    return pd.DataFrame(
        [
            {"id": "dim1", "name": "Dimension 1", "type": "string", "description": "Test dim", "title": "Dimension 1"},
            {
                "id": "dim2",
                "name": "Dimension 2",
                "type": "string",
                "description": "Test dim 2",
                "title": "Dimension 2",
            },
        ],
    )


@pytest.fixture
def sample_dataview_info():
    """Sample data view info"""
    return {
        "id": "dv_test_12345",
        "name": "Test Data View",
        "owner": {"name": "Test Owner"},
        "description": "Test description",
    }


class TestProcessSingleDataviewSuccess:
    """Tests for successful processing scenarios"""

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_successful_processing(
        self,
        mock_excel_writer,
        mock_apply_formatting,
        mock_dq_checker_class,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_metrics_df,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Test successful end-to-end processing"""
        # Setup mocks
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger

        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        # Setup fetcher
        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        # Setup data quality checker
        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(
            columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"],
        )
        mock_dq_checker_class.return_value = mock_dq_checker

        # Setup Excel writer
        mock_writer = MagicMock()
        mock_excel_writer.return_value.__enter__ = Mock(return_value=mock_writer)
        mock_excel_writer.return_value.__exit__ = Mock(return_value=False)

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
        )

        assert result.success is True
        assert result.data_view_id == "dv_test_12345"
        assert result.data_view_name == "Test Data View"
        assert result.metrics_count == 2
        assert result.dimensions_count == 2

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_processing_with_cache_disabled(
        self,
        mock_excel_writer,
        mock_apply_formatting,
        mock_dq_checker_class,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_metrics_df,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Test processing with cache disabled (default)"""
        mock_logger = Mock()
        mock_logger.handlers = []  # Make handlers iterable
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(
            columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"],
        )
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_writer = MagicMock()
        mock_excel_writer.return_value.__enter__ = Mock(return_value=mock_writer)
        mock_excel_writer.return_value.__exit__ = Mock(return_value=False)

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            enable_cache=False,  # Default behavior
        )

        assert result.success is True
        # DataQualityChecker should be called with no cache
        mock_dq_checker_class.assert_called_once()


class TestProcessSingleDataviewFailures:
    """Tests for failure scenarios"""

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    def test_cja_initialization_failure(self, mock_init_cja, mock_setup_logging, mock_config_file, temp_output_dir):
        """Test handling of CJA initialization failure"""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_init_cja.return_value = None

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
        )

        assert result.success is False
        assert "initialization failed" in result.error_message.lower()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    def test_data_view_validation_failure(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
    ):
        """Test handling of data view validation failure (empty lookup_data)"""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (pd.DataFrame(), pd.DataFrame(), {})
        mock_fetcher_class.return_value = mock_fetcher

        result = process_single_dataview(
            data_view_id="dv_invalid",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
        )

        assert result.success is False
        assert "validation failed" in result.error_message.lower()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    def test_data_view_validation_failure_none_lookup(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
    ):
        """Test handling of data view validation failure (None lookup_data)"""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (pd.DataFrame(), pd.DataFrame(), None)
        mock_fetcher_class.return_value = mock_fetcher

        result = process_single_dataview(
            data_view_id="dv_invalid",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
        )

        assert result.success is False
        assert "validation failed" in result.error_message.lower()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    def test_data_view_validation_failure_unknown_placeholder_with_error_diagnostic(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
    ):
        """Unknown placeholder + diagnostic keys must fail validation even without explicit failure markers."""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (
            pd.DataFrame(),
            pd.DataFrame(),
            {
                "id": "dv_invalid",
                "name": "Unknown",
                "error": "not found",
            },
        )
        mock_fetcher_class.return_value = mock_fetcher

        result = process_single_dataview(
            data_view_id="dv_invalid",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
        )

        assert result.success is False
        assert "validation failed" in result.error_message.lower()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    def test_data_view_validation_failure_error_placeholder(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
    ):
        """Error placeholders from dataview lookup must fail validation."""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (
            pd.DataFrame(),
            pd.DataFrame(),
            {
                "id": "dv_invalid",
                "name": "Unknown",
                "lookup_failed": True,
                "lookup_failure_reason": "exception",
                "error": "upstream failure",
            },
        )
        mock_fetcher_class.return_value = mock_fetcher

        result = process_single_dataview(
            data_view_id="dv_invalid",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
        )

        assert result.success is False
        assert "validation failed" in result.error_message.lower()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    def test_metrics_fetch_failure_aborts_partial_sdr(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Metrics transport failures should fail the run instead of generating a partial SDR."""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_init_cja.return_value = Mock()

        mock_fetcher = Mock()
        lookup_data = dict(sample_dataview_info, id="dv_partial")
        mock_fetcher.fetch_all_data.return_value = (pd.DataFrame(), sample_dimensions_df, lookup_data)
        mock_fetcher.get_fetch_statuses.return_value = {
            "metrics": EndpointFetchStatus(
                endpoint="metrics",
                status="failed",
                reason="exception",
                error_message="metrics api down",
            ),
            "dimensions": EndpointFetchStatus(endpoint="dimensions", status="success"),
            "dataview": EndpointFetchStatus(endpoint="dataview", status="success"),
        }
        mock_fetcher_class.return_value = mock_fetcher

        result = process_single_dataview(
            data_view_id="dv_partial",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
        )

        assert result.success is False
        assert "component fetch failed" in result.error_message.lower()
        assert "metrics api down" in result.error_message.lower()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    def test_dimensions_fetch_failure_aborts_partial_sdr(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_metrics_df,
        sample_dataview_info,
    ):
        """Dimensions transport failures should fail the run instead of generating a partial SDR."""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_init_cja.return_value = Mock()

        mock_fetcher = Mock()
        lookup_data = dict(sample_dataview_info, id="dv_partial")
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, pd.DataFrame(), lookup_data)
        mock_fetcher.get_fetch_statuses.return_value = {
            "metrics": EndpointFetchStatus(endpoint="metrics", status="success"),
            "dimensions": EndpointFetchStatus(
                endpoint="dimensions",
                status="failed",
                reason="exception",
                error_message="dimensions api down",
            ),
            "dataview": EndpointFetchStatus(endpoint="dataview", status="success"),
        }
        mock_fetcher_class.return_value = mock_fetcher

        result = process_single_dataview(
            data_view_id="dv_partial",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
        )

        assert result.success is False
        assert "component fetch failed" in result.error_message.lower()
        assert "dimensions api down" in result.error_message.lower()

    @patch("cja_auto_sdr.generator.write_json_output")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    def test_allow_partial_continues_on_required_component_fetch_failure(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_dq_checker_class,
        mock_write_json,
        mock_config_file,
        temp_output_dir,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """--allow-partial should permit exploratory SDR output after required component fetch failures."""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_init_cja.return_value = Mock()

        mock_fetcher = Mock()
        lookup_data = dict(sample_dataview_info, id="dv_partial")
        mock_fetcher.fetch_all_data.return_value = (pd.DataFrame(), sample_dimensions_df, lookup_data)
        mock_fetcher.get_fetch_statuses.return_value = {
            "metrics": EndpointFetchStatus(
                endpoint="metrics",
                status="failed",
                reason="exception",
                error_message="metrics timeout",
            ),
            "dimensions": EndpointFetchStatus(endpoint="dimensions", status="success"),
            "dataview": EndpointFetchStatus(endpoint="dataview", status="success"),
        }
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(
            columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"],
        )
        mock_dq_checker_class.return_value = mock_dq_checker
        mock_write_json.return_value = f"{temp_output_dir}/partial.json"

        result = process_single_dataview(
            data_view_id="dv_partial",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            output_format="json",
            allow_partial=True,
        )

        assert result.success is True
        assert result.error_message == ""
        mock_write_json.assert_called_once()
        metadata_dict = mock_write_json.call_args.args[1]
        assert metadata_dict["Partial Output"] == "Yes"
        assert metadata_dict["Partial Reasons"] == "required_endpoints_failed:metrics"

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_allow_partial_excel_metadata_marks_partial_output(
        self,
        mock_excel_writer,
        mock_apply_formatting,
        mock_dq_checker_class,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Partial exploratory Excel outputs should identify themselves in metadata."""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_init_cja.return_value = Mock()

        mock_fetcher = Mock()
        lookup_data = dict(sample_dataview_info, id="dv_partial")
        mock_fetcher.fetch_all_data.return_value = (pd.DataFrame(), sample_dimensions_df, lookup_data)
        mock_fetcher.get_fetch_statuses.return_value = {
            "metrics": EndpointFetchStatus(
                endpoint="metrics",
                status="failed",
                reason="exception",
                error_message="metrics timeout",
            ),
            "dimensions": EndpointFetchStatus(endpoint="dimensions", status="success"),
            "dataview": EndpointFetchStatus(endpoint="dataview", status="success"),
        }
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(
            columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"],
        )
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_writer = MagicMock()
        mock_excel_writer.return_value.__enter__ = Mock(return_value=mock_writer)
        mock_excel_writer.return_value.__exit__ = Mock(return_value=False)

        result = process_single_dataview(
            data_view_id="dv_partial",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            allow_partial=True,
        )

        assert result.success is True
        metadata_dfs = [
            call.args[1]
            for call in mock_apply_formatting.call_args_list
            if len(call.args) >= 3 and call.args[2] == "Metadata"
        ]
        assert metadata_dfs
        metadata_df = metadata_dfs[0]
        metadata_map = dict(zip(metadata_df["Property"], metadata_df["Value"], strict=False))
        assert metadata_map["Partial Output"] == "Yes"
        assert metadata_map["Partial Reasons"] == "required_endpoints_failed:metrics"

    @patch("cja_auto_sdr.generator.write_json_output")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    def test_allow_partial_preserves_context_when_output_write_fails(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_dq_checker_class,
        mock_write_json,
        mock_config_file,
        temp_output_dir,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Late output failures should retain the earlier partial-run context."""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_init_cja.return_value = Mock()

        mock_fetcher = Mock()
        lookup_data = dict(sample_dataview_info, id="dv_partial")
        mock_fetcher.fetch_all_data.return_value = (pd.DataFrame(), sample_dimensions_df, lookup_data)
        mock_fetcher.get_fetch_statuses.return_value = {
            "metrics": EndpointFetchStatus(
                endpoint="metrics",
                status="failed",
                reason="exception",
                error_message="metrics timeout",
            ),
            "dimensions": EndpointFetchStatus(endpoint="dimensions", status="success"),
            "dataview": EndpointFetchStatus(endpoint="dataview", status="success"),
        }
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(
            columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"],
        )
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_write_json.side_effect = PermissionError("file is locked")

        result = process_single_dataview(
            data_view_id="dv_partial",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            output_format="json",
            allow_partial=True,
        )

        assert result.success is False
        assert result.failure_reason == "output_permission_denied"
        assert result.partial_output is True
        assert result.partial_reasons == ["required_endpoints_failed:metrics"]
        assert "Permission denied" in result.error_message

    @patch("cja_auto_sdr.inventory.segments.SegmentsInventoryBuilder")
    @patch("cja_auto_sdr.inventory.calculated_metrics.CalculatedMetricsInventoryBuilder")
    @patch("cja_auto_sdr.generator.write_csv_output")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.setup_logging")
    def test_inventory_only_csv_calculated_segments_skips_irrelevant_fetch_and_validation(
        self,
        mock_setup_logging,
        mock_init_cja,
        mock_fetcher_class,
        mock_dq_checker_class,
        mock_write_csv,
        mock_calculated_builder_class,
        mock_segments_builder_class,
        mock_config_file,
        temp_output_dir,
        sample_dataview_info,
    ):
        """Inventory-only CSV should not fail on metrics/dimensions fetch or validation paths it does not emit."""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_init_cja.return_value = Mock()

        mock_fetcher = Mock()
        lookup_data = dict(sample_dataview_info, id="dv_inventory")
        mock_fetcher.fetch_all_data.return_value = (pd.DataFrame(), pd.DataFrame(), lookup_data)
        mock_fetcher.get_fetch_statuses.return_value = {
            "metrics": EndpointFetchStatus(
                endpoint="metrics",
                status="failed",
                reason="exception",
                error_message="metrics timeout",
            ),
            "dimensions": EndpointFetchStatus(
                endpoint="dimensions",
                status="failed",
                reason="exception",
                error_message="dimensions timeout",
            ),
            "dataview": EndpointFetchStatus(endpoint="dataview", status="success"),
        }
        mock_fetcher_class.return_value = mock_fetcher

        mock_write_csv.return_value = f"{temp_output_dir}/inventory_csv"

        calculated_inventory = Mock()
        calculated_inventory.get_dataframe.return_value = pd.DataFrame([{"id": "cm1", "name": "Calc 1"}])
        calculated_inventory.get_summary.return_value = {"total_calculated_metrics": 1, "complexity": {}}
        calculated_builder = Mock()
        calculated_builder.build.return_value = calculated_inventory
        mock_calculated_builder_class.return_value = calculated_builder

        segments_inventory = Mock()
        segments_inventory.get_dataframe.return_value = pd.DataFrame([{"id": "seg1", "name": "Segment 1"}])
        segments_inventory.get_summary.return_value = {"total_segments": 1, "complexity": {}}
        segments_builder = Mock()
        segments_builder.build.return_value = segments_inventory
        mock_segments_builder_class.return_value = segments_builder

        result = process_single_dataview(
            data_view_id="dv_inventory",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            output_format="csv",
            inventory_only=True,
            include_calculated_metrics=True,
            include_segments_inventory=True,
        )

        assert result.success is True
        assert result.error_message == ""
        mock_dq_checker_class.assert_not_called()
        mock_write_csv.assert_called_once()
        data_dict = mock_write_csv.call_args[0][0]
        assert "Metrics" not in data_dict
        assert "Dimensions" not in data_dict
        assert "Calculated Metrics" in data_dict
        assert "Segments" in data_dict

    @patch("cja_auto_sdr.inventory.segments.SegmentsInventoryBuilder")
    @patch("cja_auto_sdr.inventory.calculated_metrics.CalculatedMetricsInventoryBuilder")
    @patch("cja_auto_sdr.generator.write_json_output")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.setup_logging")
    def test_inventory_only_json_calculated_segments_skips_irrelevant_fetch_and_validation(
        self,
        mock_setup_logging,
        mock_init_cja,
        mock_fetcher_class,
        mock_dq_checker_class,
        mock_write_json,
        mock_calculated_builder_class,
        mock_segments_builder_class,
        mock_config_file,
        temp_output_dir,
        sample_dataview_info,
    ):
        """Inventory-only JSON should not fail-closed on metrics/dimensions transport failures."""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_init_cja.return_value = Mock()

        mock_fetcher = Mock()
        lookup_data = dict(sample_dataview_info, id="dv_inventory")
        mock_fetcher.fetch_all_data.return_value = (pd.DataFrame(), pd.DataFrame(), lookup_data)
        mock_fetcher.get_fetch_statuses.return_value = {
            "metrics": EndpointFetchStatus(
                endpoint="metrics",
                status="failed",
                reason="exception",
                error_message="metrics timeout",
            ),
            "dimensions": EndpointFetchStatus(
                endpoint="dimensions",
                status="failed",
                reason="exception",
                error_message="dimensions timeout",
            ),
            "dataview": EndpointFetchStatus(endpoint="dataview", status="success"),
        }
        mock_fetcher_class.return_value = mock_fetcher

        mock_write_json.return_value = f"{temp_output_dir}/inventory.json"

        calculated_inventory = Mock()
        calculated_inventory.get_dataframe.return_value = pd.DataFrame([{"id": "cm1", "name": "Calc 1"}])
        calculated_inventory.get_summary.return_value = {"total_calculated_metrics": 1, "complexity": {}}
        calculated_builder = Mock()
        calculated_builder.build.return_value = calculated_inventory
        mock_calculated_builder_class.return_value = calculated_builder

        segments_inventory = Mock()
        segments_inventory.get_dataframe.return_value = pd.DataFrame([{"id": "seg1", "name": "Segment 1"}])
        segments_inventory.get_summary.return_value = {"total_segments": 1, "complexity": {}}
        segments_builder = Mock()
        segments_builder.build.return_value = segments_inventory
        mock_segments_builder_class.return_value = segments_builder

        result = process_single_dataview(
            data_view_id="dv_inventory",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            output_format="json",
            inventory_only=True,
            include_calculated_metrics=True,
            include_segments_inventory=True,
        )

        assert result.success is True
        assert result.error_message == ""
        mock_dq_checker_class.assert_not_called()
        mock_write_json.assert_called_once()
        data_dict = mock_write_json.call_args[0][0]
        metadata_dict = mock_write_json.call_args[0][1]
        assert "Metrics" not in data_dict
        assert "Dimensions" not in data_dict
        assert "Data Quality" not in data_dict
        assert "Calculated Metrics" in data_dict
        assert "Segments" in data_dict
        assert metadata_dict["Data Quality Validation Status"] == "Skipped"
        assert metadata_dict["Data Quality Issues"] == "Not run"
        assert "Skipped" in metadata_dict["Data Quality Summary"]
        assert str(metadata_dict["Total Metrics"]).startswith("Unavailable (metrics fetch failed")
        assert str(metadata_dict["Total Dimensions"]).startswith("Unavailable (dimensions fetch failed")

    @patch("cja_auto_sdr.generator.write_csv_output")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.setup_logging")
    def test_inventory_only_csv_with_derived_inventory_still_fails_on_component_fetch(
        self,
        mock_setup_logging,
        mock_init_cja,
        mock_fetcher_class,
        mock_dq_checker_class,
        mock_write_csv,
        mock_config_file,
        temp_output_dir,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Derived inventory depends on component payloads and must remain fail-closed."""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_init_cja.return_value = Mock()

        mock_fetcher = Mock()
        lookup_data = dict(sample_dataview_info, id="dv_inventory")
        mock_fetcher.fetch_all_data.return_value = (pd.DataFrame(), sample_dimensions_df, lookup_data)
        mock_fetcher.get_fetch_statuses.return_value = {
            "metrics": EndpointFetchStatus(
                endpoint="metrics",
                status="failed",
                reason="exception",
                error_message="metrics timeout",
            ),
            "dimensions": EndpointFetchStatus(endpoint="dimensions", status="success"),
            "dataview": EndpointFetchStatus(endpoint="dataview", status="success"),
        }
        mock_fetcher_class.return_value = mock_fetcher

        result = process_single_dataview(
            data_view_id="dv_inventory",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            output_format="csv",
            inventory_only=True,
            include_derived_inventory=True,
        )

        assert result.success is False
        assert "component fetch failed" in result.error_message.lower()
        assert "metrics timeout" in result.error_message.lower()
        mock_dq_checker_class.assert_not_called()
        mock_write_csv.assert_not_called()

    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.setup_logging")
    def test_metrics_only_fails_when_required_metrics_payload_is_empty(
        self,
        mock_setup_logging,
        mock_init_cja,
        mock_fetcher_class,
        mock_dq_checker_class,
        mock_config_file,
        temp_output_dir,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Metrics-only output must fail closed when the required metrics payload is empty."""
        mock_logger = Mock()
        mock_logger.handlers = []
        mock_setup_logging.return_value = mock_logger
        mock_init_cja.return_value = Mock()

        mock_fetcher = Mock()
        lookup_data = dict(sample_dataview_info, id="dv_metrics_only")
        mock_fetcher.fetch_all_data.return_value = (pd.DataFrame(), sample_dimensions_df, lookup_data)
        mock_fetcher.get_fetch_statuses.return_value = {
            "metrics": EndpointFetchStatus(endpoint="metrics", status="success"),
            "dimensions": EndpointFetchStatus(endpoint="dimensions", status="success"),
            "dataview": EndpointFetchStatus(endpoint="dataview", status="success"),
        }
        mock_fetcher_class.return_value = mock_fetcher

        result = process_single_dataview(
            data_view_id="dv_metrics_only",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            metrics_only=True,
        )

        assert result.success is False
        assert result.failure_reason == "required_endpoints_empty:metrics"
        assert "required component payloads were empty: metrics" in result.error_message.lower()
        mock_dq_checker_class.assert_not_called()

    @patch("cja_auto_sdr.generator.write_json_output")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.setup_logging")
    def test_skip_validation_json_marks_metadata_as_skipped(
        self,
        mock_setup_logging,
        mock_init_cja,
        mock_fetcher_class,
        mock_dq_checker_class,
        mock_write_json,
        mock_config_file,
        temp_output_dir,
        sample_metrics_df,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Embedded metadata must report skipped validation explicitly when --skip-validation is used."""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_init_cja.return_value = Mock()

        mock_fetcher = Mock()
        lookup_data = dict(sample_dataview_info, id="dv_skip_validation")
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, lookup_data)
        mock_fetcher.get_fetch_statuses.return_value = {
            "metrics": EndpointFetchStatus(endpoint="metrics", status="success"),
            "dimensions": EndpointFetchStatus(endpoint="dimensions", status="success"),
            "dataview": EndpointFetchStatus(endpoint="dataview", status="success"),
        }
        mock_fetcher_class.return_value = mock_fetcher
        mock_write_json.return_value = f"{temp_output_dir}/skipped_validation.json"

        result = process_single_dataview(
            data_view_id="dv_skip_validation",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            output_format="json",
            skip_validation=True,
        )

        assert result.success is True
        mock_dq_checker_class.assert_not_called()
        mock_write_json.assert_called_once()
        metadata_dict = mock_write_json.call_args[0][1]
        assert metadata_dict["Data Quality Validation Status"] == "Skipped"
        assert metadata_dict["Data Quality Issues"] == "Not run"
        assert metadata_dict["Data Quality Summary"] == "Skipped (--skip-validation)"

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    def test_data_view_validation_failure_legacy_unknown_placeholder(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
    ):
        """Legacy Unknown/id-only placeholders must fail validation."""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (
            pd.DataFrame(),
            pd.DataFrame(),
            {"id": "dv_invalid", "name": "Unknown"},
        )
        mock_fetcher_class.return_value = mock_fetcher

        result = process_single_dataview(
            data_view_id="dv_invalid",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
        )

        assert result.success is False
        assert "validation failed" in result.error_message.lower()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    def test_data_view_validation_failure_circuit_breaker_placeholder(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
    ):
        """Circuit-breaker placeholders from dataview lookup must fail validation."""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (
            pd.DataFrame(),
            pd.DataFrame(),
            {
                "id": "dv_invalid",
                "name": "Unknown",
                "lookup_failed": True,
                "lookup_failure_reason": "circuit_breaker_open",
                "circuit_breaker_open": True,
                "error": "breaker open",
            },
        )
        mock_fetcher_class.return_value = mock_fetcher

        result = process_single_dataview(
            data_view_id="dv_invalid",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
        )

        assert result.success is False
        assert "validation failed" in result.error_message.lower()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    def test_empty_data_fetched(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_dataview_info,
    ):
        """Test handling of empty metrics and dimensions"""
        mock_logger = Mock()
        mock_logger.handlers = []  # Make handlers iterable
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (pd.DataFrame(), pd.DataFrame(), sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
        )

        assert result.success is False
        assert "no metrics or dimensions" in result.error_message.lower()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("pandas.ExcelWriter")
    def test_permission_error_writing_file(
        self,
        mock_excel_writer,
        mock_dq_checker_class,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_metrics_df,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Test handling of permission error when writing output"""
        mock_logger = Mock()
        mock_logger.handlers = []  # Make handlers iterable
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(
            columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"],
        )
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_excel_writer.side_effect = PermissionError("File is open")

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
        )

        assert result.success is False
        assert "permission" in result.error_message.lower()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.output.writers.notion.write_notion_output")
    def test_notion_writer_failure_returns_failed_result_not_systemexit(
        self,
        mock_write_notion,
        mock_dq_checker_class,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_metrics_df,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Notion writer errors must return a failed ProcessingResult — never SystemExit.

        Regression: when invoked inside a batch worker, raising SystemExit kills the
        pool worker and aborts the whole batch, defeating --continue-on-error. The
        Notion error path must surface as ProcessingResult(success=False) so the
        batch can mark this data view failed and proceed.
        """
        from cja_auto_sdr.output.writers.notion import NotionConfigurationError

        mock_logger = Mock()
        mock_logger.handlers = []
        mock_setup_logging.return_value = mock_logger
        mock_init_cja.return_value = Mock()

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(
            columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"],
        )
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_write_notion.side_effect = NotionConfigurationError("NOTION_API_KEY not set")

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            output_format="notion",
        )

        assert result.success is False
        assert "NOTION_API_KEY" in result.error_message
        assert result.failure_code == "OUTPUT_WRITE_FAILED"
        assert result.failure_reason == "output_write_failed:NotionConfigurationError"


class TestProcessSingleDataviewOutputFormats:
    """Tests for different output formats"""

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.write_csv_output")
    def test_csv_output_format(
        self,
        mock_write_csv,
        mock_dq_checker_class,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_metrics_df,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Test CSV output format"""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(
            columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"],
        )
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_write_csv.return_value = f"{temp_output_dir}/test_csv"

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            output_format="csv",
        )

        assert result.success is True
        assert result.output_file == f"{temp_output_dir}/test_csv"
        assert result.output_files == [f"{temp_output_dir}/test_csv"]
        mock_write_csv.assert_called_once()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.write_json_output")
    def test_json_output_format(
        self,
        mock_write_json,
        mock_dq_checker_class,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_metrics_df,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Test JSON output format"""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(
            columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"],
        )
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_write_json.return_value = f"{temp_output_dir}/test.json"

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            output_format="json",
        )

        assert result.success is True
        assert result.output_file == f"{temp_output_dir}/test.json"
        assert result.output_files == [f"{temp_output_dir}/test.json"]
        mock_write_json.assert_called_once()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.write_html_output")
    def test_html_output_format(
        self,
        mock_write_html,
        mock_dq_checker_class,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_metrics_df,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Test HTML output format"""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(
            columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"],
        )
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_write_html.return_value = f"{temp_output_dir}/test.html"

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            output_format="html",
        )

        assert result.success is True
        assert result.output_file == f"{temp_output_dir}/test.html"
        assert result.output_files == [f"{temp_output_dir}/test.html"]
        mock_write_html.assert_called_once()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.write_markdown_output")
    def test_markdown_output_format(
        self,
        mock_write_md,
        mock_dq_checker_class,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_metrics_df,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Test Markdown output format"""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(
            columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"],
        )
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_write_md.return_value = f"{temp_output_dir}/test.md"

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            output_format="markdown",
        )

        assert result.success is True
        assert result.output_file == f"{temp_output_dir}/test.md"
        assert result.output_files == [f"{temp_output_dir}/test.md"]
        mock_write_md.assert_called_once()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.write_markdown_output")
    @patch("cja_auto_sdr.generator.write_html_output")
    @patch("cja_auto_sdr.generator.write_json_output")
    @patch("cja_auto_sdr.generator.write_csv_output")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_all_output_format_tracks_all_emitted_artifacts(
        self,
        mock_excel_writer,
        mock_apply_formatting,
        mock_write_csv,
        mock_write_json,
        mock_write_html,
        mock_write_md,
        mock_dq_checker_class,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_metrics_df,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Test multi-format runs keep primary and full artifact lists aligned."""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(
            columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"],
        )
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_writer = MagicMock()
        mock_excel_writer.return_value.__enter__ = Mock(return_value=mock_writer)
        mock_excel_writer.return_value.__exit__ = Mock(return_value=False)

        csv_output = f"{temp_output_dir}/test_csv"
        json_output = f"{temp_output_dir}/test.json"
        html_output = f"{temp_output_dir}/test.html"
        markdown_output = f"{temp_output_dir}/test.md"
        mock_write_csv.return_value = csv_output
        mock_write_json.return_value = json_output
        mock_write_html.return_value = html_output
        mock_write_md.return_value = markdown_output

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            output_format="all",
        )

        expected_excel = f"{temp_output_dir}/CJA_DataView_{sample_dataview_info['name']}_dv_test_12345_SDR.xlsx"
        assert result.success is True
        assert result.output_file == expected_excel
        assert result.output_files == [expected_excel, csv_output, json_output, html_output, markdown_output]
        mock_write_csv.assert_called_once()
        mock_write_json.assert_called_once()
        mock_write_html.assert_called_once()
        mock_write_md.assert_called_once()


class TestProcessSingleDataviewCaching:
    """Tests for caching functionality"""

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.ValidationCache")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_cache_enabled(
        self,
        mock_excel_writer,
        mock_apply_formatting,
        mock_dq_checker_class,
        mock_cache_class,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_metrics_df,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Test that cache is created when enabled"""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_cache = Mock()
        mock_cache.get_statistics.return_value = {
            "hits": 0,
            "misses": 0,
            "hit_rate": 0.0,
            "size": 0,
            "max_size": 500,
            "evictions": 0,
            "total_requests": 0,
        }
        mock_cache_class.return_value = mock_cache

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(
            columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"],
        )
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
            cache_ttl=1800,
        )

        assert result.success is True
        mock_cache_class.assert_called_once()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.ValidationCache")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_clear_cache_option(
        self,
        mock_excel_writer,
        mock_apply_formatting,
        mock_dq_checker_class,
        mock_cache_class,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_metrics_df,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Test that cache is cleared when clear_cache=True"""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_cache = Mock()
        mock_cache.get_statistics.return_value = {
            "hits": 0,
            "misses": 0,
            "hit_rate": 0.0,
            "size": 0,
            "max_size": 1000,
            "evictions": 0,
            "total_requests": 0,
        }
        mock_cache_class.return_value = mock_cache

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(
            columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"],
        )
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_writer = MagicMock()
        mock_excel_writer.return_value.__enter__ = Mock(return_value=mock_writer)
        mock_excel_writer.return_value.__exit__ = Mock(return_value=False)

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            enable_cache=True,
            clear_cache=True,
        )

        assert result.success is True
        mock_cache.clear.assert_called_once()


class TestProcessSingleDataviewWorker:
    """Tests for the worker wrapper function"""

    @patch("cja_auto_sdr.generator.process_single_dataview")
    def test_worker_unpacks_args(self, mock_process):
        """Test that worker correctly unpacks arguments"""
        expected_result = ProcessingResult(
            data_view_id="dv_test_12345",
            data_view_name="Test",
            success=True,
            duration=1.0,
        )
        mock_process.return_value = expected_result

        args = WorkerArgs(
            data_view_id="dv_test_12345",
            config_file="config.json",
            output_dir="/output",
        )

        result = process_single_dataview_worker(args)

        assert result == expected_result
        mock_process.assert_called_once_with(
            "dv_test_12345",
            processing_config=ProcessingConfig(
                config_file="config.json",
                output_dir="/output",
                log_level="INFO",
                log_format="text",
                output_format="excel",
                enable_cache=False,
                cache_size=1000,
                cache_ttl=3600,
                quiet=False,
                skip_validation=False,
                max_issues=0,
                clear_cache=False,
                show_timings=False,
                metrics_only=False,
                dimensions_only=False,
                profile=None,
                shared_cache=None,
                api_tuning_config=None,
                circuit_breaker_config=None,
                include_derived_inventory=False,
                include_calculated_metrics=False,
                include_segments_inventory=False,
                inventory_only=False,
                inventory_order=None,
                quality_report_only=False,
            ),
        )


class TestProcessSingleDataviewFilenaming:
    """Tests for file naming logic"""

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_filename_sanitization(
        self,
        mock_excel_writer,
        mock_apply_formatting,
        mock_dq_checker_class,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_metrics_df,
        sample_dimensions_df,
    ):
        """Test that special characters are removed from filenames"""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        # Data view with special characters in name
        special_name_info = {
            "id": "dv_test_12345",
            "name": "Test/View:With*Special<Chars>",
            "owner": {"name": "Test Owner"},
        }

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, special_name_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(
            columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"],
        )
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_writer = MagicMock()
        mock_excel_writer.return_value.__enter__ = Mock(return_value=mock_writer)
        mock_excel_writer.return_value.__exit__ = Mock(return_value=False)

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
        )

        assert result.success is True
        # The filename should have special characters removed
        assert result.output_file is not None
        assert "/" not in Path(result.output_file).name
        assert ":" not in Path(result.output_file).name


class TestProcessSingleDataviewMaxIssues:
    """Tests for max_issues parameter"""

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_max_issues_parameter_passed(
        self,
        mock_excel_writer,
        mock_apply_formatting,
        mock_dq_checker_class,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_metrics_df,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Test that max_issues parameter is passed to get_issues_dataframe"""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(
            columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"],
        )
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_writer = MagicMock()
        mock_excel_writer.return_value.__enter__ = Mock(return_value=mock_writer)
        mock_excel_writer.return_value.__exit__ = Mock(return_value=False)

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            max_issues=10,
        )

        assert result.success is True
        mock_dq_checker.get_issues_dataframe.assert_called_once_with(max_issues=10)

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    def test_quality_report_only_respects_max_issues(
        self,
        mock_dq_checker_class,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_metrics_df,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Quality report mode should keep only the max_issues-limited set in ProcessingResult."""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        all_issues = [
            {
                "Severity": "CRITICAL",
                "Category": "Missing Fields",
                "Type": "Metrics",
                "Item Name": "N/A",
                "Issue": "Critical issue",
                "Details": "details",
            },
            {
                "Severity": "HIGH",
                "Category": "Duplicates",
                "Type": "Dimensions",
                "Item Name": "dup",
                "Issue": "High issue",
                "Details": "details",
            },
            {
                "Severity": "LOW",
                "Category": "Descriptions",
                "Type": "Metrics",
                "Item Name": "missing desc",
                "Issue": "Low issue",
                "Details": "details",
            },
        ]
        limited_issues = all_issues[:2]

        mock_dq_checker = Mock()
        mock_dq_checker.issues = all_issues
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(limited_issues)
        mock_dq_checker_class.return_value = mock_dq_checker

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            quality_report_only=True,
            max_issues=2,
        )

        assert result.success is True
        assert result.dq_issues_count == 2
        assert [issue["Issue"] for issue in result.dq_issues] == ["Critical issue", "High issue"]
        mock_dq_checker.get_issues_dataframe.assert_called_once_with(max_issues=2)

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.write_json_output")
    def test_sdr_generation_fails_on_unexpected_validation_runtime_error(
        self,
        mock_write_json,
        mock_dq_checker_class,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_metrics_df,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Unexpected validation runtime errors should fail the SDR run."""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.check_all_parallel.side_effect = RuntimeError("threadpool failure")
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(
            columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"],
        )
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_write_json.return_value = f"{temp_output_dir}/test.json"

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            output_format="json",
        )

        assert result.success is False
        assert result.dq_issues_count == 0
        assert "data quality validation failed" in result.error_message.lower()
        assert "threadpool failure" in result.error_message.lower()
        assert any(
            "Aborting SDR generation because data quality validation did not complete" in str(call.args[0])
            for call in mock_logger.info.call_args_list
            if call.args
        )
        mock_write_json.assert_not_called()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.write_json_output")
    def test_allow_partial_continues_when_validation_runtime_errors(
        self,
        mock_write_json,
        mock_dq_checker_class,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_metrics_df,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """--allow-partial should continue SDR generation when validation runtime fails."""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_init_cja.return_value = Mock()

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.check_all_parallel.side_effect = RuntimeError("threadpool failure")
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(
            columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"],
        )
        mock_dq_checker_class.return_value = mock_dq_checker

        mock_write_json.return_value = f"{temp_output_dir}/partial_validation.json"

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            output_format="json",
            allow_partial=True,
        )

        assert result.success is True
        assert result.error_message == ""
        assert result.dq_issues_count == 0
        assert result.dq_severity_counts == {}
        mock_write_json.assert_called_once()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.write_json_output")
    def test_sdr_generation_fails_when_issue_dataframe_payload_is_not_dataframe(
        self,
        mock_write_json,
        mock_dq_checker_class,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_metrics_df,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Non-DataFrame issue payloads should fail closed in SDR mode."""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = [{"Severity": "HIGH", "Issue": "Malformed issue payload"}]
        mock_dq_checker.get_issues_dataframe.return_value = {"invalid": "payload"}
        mock_dq_checker_class.return_value = mock_dq_checker

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            output_format="json",
        )

        assert result.success is False
        assert "data quality validation failed" in result.error_message.lower()
        assert "non-dataframe payload" in result.error_message.lower()
        mock_dq_checker.get_issues_dataframe.assert_called_once_with(max_issues=0)
        mock_write_json.assert_not_called()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.write_json_output")
    def test_sdr_generation_fails_when_issue_dataframe_extraction_raises(
        self,
        mock_write_json,
        mock_dq_checker_class,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_metrics_df,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Issue dataframe extraction failures should fail closed in SDR mode."""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = [{"Severity": "HIGH", "Issue": "Malformed issue payload"}]
        mock_dq_checker.get_issues_dataframe.side_effect = RuntimeError("issue dataframe extraction failed")
        mock_dq_checker_class.return_value = mock_dq_checker

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            output_format="json",
        )

        assert result.success is False
        assert "data quality validation failed" in result.error_message.lower()
        assert "issue dataframe extraction failed" in result.error_message.lower()
        mock_dq_checker.get_issues_dataframe.assert_called_once_with(max_issues=0)
        mock_write_json.assert_not_called()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    def test_quality_report_only_fails_when_validation_runtime_errors(
        self,
        mock_dq_checker_class,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_metrics_df,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Quality report mode should fail on unexpected validation runtime errors."""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.check_all_parallel.side_effect = RuntimeError("threadpool failure")
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(
            columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"],
        )
        mock_dq_checker_class.return_value = mock_dq_checker

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            quality_report_only=True,
        )

        assert result.success is False
        assert "Data quality validation failed" in result.error_message
        assert "threadpool failure" in result.error_message

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    def test_allow_partial_does_not_override_quality_report_fail_closed_validation(
        self,
        mock_dq_checker_class,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_metrics_df,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Quality-report mode must remain fail-closed even if --allow-partial is enabled."""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_init_cja.return_value = Mock()

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.check_all_parallel.side_effect = RuntimeError("threadpool failure")
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(
            columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"],
        )
        mock_dq_checker_class.return_value = mock_dq_checker

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            quality_report_only=True,
            allow_partial=True,
        )

        assert result.success is False
        assert "Data quality validation failed" in result.error_message

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    def test_quality_report_only_fails_when_validation_errors(
        self,
        mock_dq_checker_class,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_metrics_df,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Quality report mode should fail when validation itself raises an exception."""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        from cja_auto_sdr.core.exceptions import ValidationError

        mock_dq_checker = Mock()
        mock_dq_checker.issues = []
        mock_dq_checker.check_all_parallel.side_effect = ValidationError("unexpected validation failure")
        mock_dq_checker.get_issues_dataframe.return_value = pd.DataFrame(
            columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"],
        )
        mock_dq_checker_class.return_value = mock_dq_checker

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            quality_report_only=True,
        )

        assert result.success is False
        assert "Data quality validation failed" in result.error_message
        assert "unexpected validation failure" in result.error_message

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    def test_quality_report_only_fails_when_issue_dataframe_extraction_raises(
        self,
        mock_dq_checker_class,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_metrics_df,
        sample_dimensions_df,
        sample_dataview_info,
    ):
        """Quality-report mode should fail if issue dataframe extraction raises."""
        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, sample_dataview_info)
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq_checker = Mock()
        mock_dq_checker.issues = [{"Severity": "HIGH", "Issue": "Malformed issue payload"}]
        mock_dq_checker.get_issues_dataframe.side_effect = RuntimeError("issue dataframe extraction failed")
        mock_dq_checker_class.return_value = mock_dq_checker

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            quality_report_only=True,
        )

        assert result.success is False
        assert "Data quality validation failed" in result.error_message
        assert "issue dataframe extraction failed" in result.error_message
        mock_dq_checker.get_issues_dataframe.assert_called_once_with(max_issues=0)


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
            file_size_bytes=1024,
        )

        assert result.success is True
        assert result.metrics_count == 100
        assert result.dimensions_count == 50
        assert result.dq_issues_count == 5
        assert result.output_files == ["/path/to/file.xlsx"]

    def test_processing_result_failure(self):
        """Test ProcessingResult for failed processing"""
        result = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test",
            success=False,
            duration=1.0,
            error_message="Connection failed",
        )

        assert result.output_file == ""
        assert result.output_files == []

    def test_processing_result_normalizes_multi_artifact_state(self):
        """Test additive multi-artifact state normalization."""
        result = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test",
            success=True,
            duration=1.0,
            output_files=["/tmp/report.xlsx", "/tmp/report.json", "/tmp/report.xlsx"],
        )

        assert result.output_file == "/tmp/report.xlsx"
        assert result.output_files == ["/tmp/report.xlsx", "/tmp/report.json"]

    def test_processing_result_file_size_formatted(self):
        """Test file_size_formatted property"""
        result = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test",
            success=True,
            duration=1.0,
            file_size_bytes=1536,  # 1.5 KB
        )

        formatted = result.file_size_formatted
        assert "KB" in formatted or "B" in formatted


# ---------------------------------------------------------------------------
# Elapsed-duration timing hardening (v3.5.6)
# ---------------------------------------------------------------------------


class TestElapsedDurationTimingHardening:
    """Verify process_single_dataview uses perf_counter for duration, not wall-clock."""

    def test_duration_uses_perf_counter(self) -> None:
        """Duration is derived from perf_counter, not time.time."""
        import time
        from unittest.mock import MagicMock, patch

        from cja_auto_sdr.generator import process_single_dataview

        perf_start = 100.0
        perf_end = 102.5

        mock_time = MagicMock(wraps=time)
        mock_time.perf_counter = MagicMock(side_effect=[perf_start, perf_end, perf_end])
        mock_time.monotonic = time.monotonic

        with (
            patch("cja_auto_sdr.generator.time", mock_time),
            patch("cja_auto_sdr.generator.initialize_cja", side_effect=RuntimeError("test")),
            patch("cja_auto_sdr.generator.setup_logging", return_value=MagicMock()),
            patch("cja_auto_sdr.generator.with_log_context", return_value=MagicMock()),
            patch("cja_auto_sdr.generator.flush_logging_handlers"),
            patch("cja_auto_sdr.generator.PerformanceTracker"),
        ):
            result = process_single_dataview(data_view_id="dv_test")

        assert result.success is False
        assert result.duration >= 0
        assert abs(result.duration - 2.5) < 0.01

    def test_failure_banner_duration_text_shape(self) -> None:
        """Failure banners emit 'Duration: X.XXs' format using perf_counter."""
        import time
        from unittest.mock import MagicMock, patch

        from cja_auto_sdr.generator import process_single_dataview

        counter = iter([500.0, 503.75, 503.75, 503.75, 503.75])

        mock_time = MagicMock(wraps=time)
        mock_time.perf_counter = MagicMock(side_effect=counter)
        mock_time.monotonic = time.monotonic

        captured_messages: list[str] = []

        def capture_info(msg, *args):
            captured_messages.append(msg % args if args else msg)

        mock_logger = MagicMock()
        mock_logger.info = MagicMock(side_effect=capture_info)
        mock_logger.debug = MagicMock()
        mock_logger.critical = MagicMock()
        mock_logger.exception = MagicMock()

        with (
            patch("cja_auto_sdr.generator.time", mock_time),
            patch("cja_auto_sdr.generator.initialize_cja", side_effect=RuntimeError("boom")),
            patch("cja_auto_sdr.generator.setup_logging", return_value=mock_logger),
            patch("cja_auto_sdr.generator.with_log_context", return_value=mock_logger),
            patch("cja_auto_sdr.generator.flush_logging_handlers"),
            patch("cja_auto_sdr.generator.PerformanceTracker"),
        ):
            result = process_single_dataview(data_view_id="dv_test")

        assert result.success is False
        duration_lines = [m for m in captured_messages if "Duration:" in m]
        assert len(duration_lines) >= 1
        assert duration_lines[0] == "Duration: 3.75s"
