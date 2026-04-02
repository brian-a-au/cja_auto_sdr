"""Tests for uncovered lines in generator.py: process_single_dataview, run_dry_run,
BatchProcessor, generate_inventory exception handlers, and related helpers.

Targets uncovered line ranges:
- 5097-5112: generate_inventory / process_inventory_summary calculated/segments exception paths
- 5296-5297, 5309, 5318: circuit breaker + API tuning config in process_single_dataview
- 5380-5381: shared_cache usage in process_single_dataview
- 5454-5532: Inventory building import errors + exceptions
- 5547-5549, 5600-5620, 5623-5661: Metadata creation with inventory stats
- 5674-5676, 5685-5687: Metadata exception handler, format_json_cell exception
- 5705-5706, 5718-5721, 5731, 5743, 5745, 5755, 5757, 5767, 5769: Output format routing
- 5791: FORMAT_ALIASES lookup
- 5835-5859: Inventory sheets with placeholders in Excel
- 5921, 5948-5960: Inventory summary stats collection
- 6000-6011: Exception handlers for file writing
- 6234-6235: BatchProcessor.__init__ OSError
- 6330-6336: BatchProcessor stop on error
- 6499-6511, 6533-6538, 6555-6557: run_dry_run profile validation
- 6611-6612, 6623-6624, 6640-6642, 6691-6694: run_dry_run API validation errors
"""

import argparse
import json
import logging
import threading
import time
from itertools import count
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import pytest

from cja_auto_sdr.core.config import APITuningConfig, CircuitBreakerConfig
from cja_auto_sdr.core.exceptions import (
    APIError,
    ConfigurationError,
    OutputError,
    ProfileConfigError,
    ProfileNotFoundError,
    RetryableHTTPError,
)
from cja_auto_sdr.generator import (
    BatchProcessor,
    DiscoveryNotFoundError,
    ProcessingResult,
    process_single_dataview,
    run_dry_run,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_config_file(tmp_path):
    """Create a temporary config file."""
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
    """Create a temporary output directory."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return str(output_dir)


@pytest.fixture
def sample_metrics_df():
    """Sample metrics DataFrame with 'type' column for metadata coverage."""
    return pd.DataFrame(
        [
            {"id": "m1", "name": "Metric 1", "type": "calculated", "description": "desc", "title": "Metric 1"},
            {"id": "m2", "name": "Metric 2", "type": "standard", "description": "desc", "title": "Metric 2"},
        ],
    )


@pytest.fixture
def sample_dimensions_df():
    """Sample dimensions DataFrame with 'type' column for metadata coverage."""
    return pd.DataFrame(
        [
            {"id": "d1", "name": "Dim 1", "type": "string", "description": "desc", "title": "Dim 1"},
            {"id": "d2", "name": "Dim 2", "type": "string", "description": "desc", "title": "Dim 2"},
        ],
    )


@pytest.fixture
def sample_dataview_info():
    """Sample data view lookup info dict."""
    return {
        "id": "dv_test_12345",
        "name": "Test Data View",
        "owner": {"name": "Test Owner"},
        "description": "Test description",
    }


def _make_mock_inventory_obj(
    *,
    total_derived_fields=0,
    total_calculated_metrics=0,
    total_segments=0,
    metrics_count=0,
    dimensions_count=0,
):
    """Build a mock inventory object with a get_summary() method."""
    obj = MagicMock()
    summary = {
        "total_derived_fields": total_derived_fields,
        "total_calculated_metrics": total_calculated_metrics,
        "total_segments": total_segments,
        "metrics_count": metrics_count,
        "dimensions_count": dimensions_count,
        "complexity": {
            "high_complexity_count": 2,
            "elevated_complexity_count": 3,
            "average": 45.5,
            "max": 90.0,
        },
    }
    obj.get_summary.return_value = summary
    obj.get_dataframe.return_value = pd.DataFrame({"col": [1, 2, 3]})
    return obj


def _standard_process_mocks():
    """Return a dictionary of common patches for process_single_dataview."""
    return {
        "setup_logging": "cja_auto_sdr.generator.setup_logging",
        "initialize_cja": "cja_auto_sdr.generator.initialize_cja",
        "fetcher_class": "cja_auto_sdr.generator.ParallelAPIFetcher",
        "dq_checker_class": "cja_auto_sdr.generator.DataQualityChecker",
        "apply_excel": "cja_auto_sdr.generator.apply_excel_formatting",
        "excel_writer": "pandas.ExcelWriter",
    }


def _configure_standard_mocks(
    mock_setup_logging,
    mock_init_cja,
    mock_fetcher_class,
    mock_dq_checker_class,
    mock_excel_writer,
    metrics_df,
    dimensions_df,
    dataview_info,
):
    """Wire up all standard mocks and return (logger, fetcher, dq_checker)."""
    mock_logger = Mock()
    mock_logger.handlers = []
    mock_setup_logging.return_value = mock_logger

    mock_cja = Mock()
    mock_init_cja.return_value = mock_cja

    mock_fetcher = Mock()
    mock_fetcher.fetch_all_data.return_value = (metrics_df, dimensions_df, dataview_info)
    mock_fetcher.get_tuner_statistics.return_value = None
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

    return mock_logger, mock_fetcher, mock_dq_checker


def _mock_call_contains(mock_method: Mock, text: str) -> bool:
    """Return True when any logged call contains the given text fragment.

    Raises:
        AssertionError: When no call contains the expected text. This includes
            the observed call args list to make failures easier to debug.
    """
    matched = any(call.args and text in str(call.args[0]) for call in mock_method.call_args_list)
    if not matched:
        raise AssertionError(f"Expected {text!r} in {mock_method.call_args_list!r}")
    return True


# ============================================================================
# Tests: process_single_dataview - circuit breaker + API tuning (5296-5318)
# ============================================================================


class TestProcessSingleDataviewCircuitBreakerAndTuning:
    """Cover lines 5296-5297, 5309, 5318: circuit breaker creation and API tuning logging."""

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    @patch("cja_auto_sdr.generator.CircuitBreaker")
    def test_circuit_breaker_created_when_config_provided(
        self,
        mock_cb_class,
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
        """Circuit breaker is instantiated when circuit_breaker_config is provided."""
        _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            mock_excel_writer,
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )

        cb_config = CircuitBreakerConfig(failure_threshold=3, success_threshold=1, timeout_seconds=15.0)
        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            circuit_breaker_config=cb_config,
            skip_validation=True,
        )
        assert result.success is True
        mock_cb_class.assert_called_once()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_api_tuning_config_logged(
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
        """API tuning config triggers logging when provided."""
        _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            mock_excel_writer,
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )

        tuning = APITuningConfig(min_workers=2, max_workers=8)
        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            api_tuning_config=tuning,
            skip_validation=True,
        )
        assert result.success is True

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_tuner_statistics_logged_when_available(
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
        """Line 5318: tuner stats dict logged when get_tuner_statistics returns data."""
        _mock_logger, mock_fetcher, _ = _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            mock_excel_writer,
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )
        mock_fetcher.get_tuner_statistics.return_value = {
            "scale_ups": 3,
            "scale_downs": 1,
            "average_response_ms": 150.0,
        }

        tuning = APITuningConfig(min_workers=1, max_workers=5)
        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            api_tuning_config=tuning,
            skip_validation=True,
        )
        assert result.success is True


# ============================================================================
# Tests: shared_cache usage (5380-5381)
# ============================================================================


class TestProcessSingleDataviewSharedCache:
    """Cover lines 5380-5381: shared_cache is used instead of creating a new one."""

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_shared_cache_passed_to_dq_checker(
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
        """When shared_cache is provided, it is used as validation_cache."""
        _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            mock_excel_writer,
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )
        fake_shared_cache = MagicMock()
        fake_shared_cache.get_statistics.return_value = {
            "hits": 0,
            "misses": 0,
            "hit_rate": 0.0,
            "size": 0,
            "max_size": 1000,
            "evictions": 0,
            "total_requests": 0,
        }

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            shared_cache=fake_shared_cache,
        )
        assert result.success is True
        # DataQualityChecker should receive the shared cache
        mock_dq_checker_class.assert_called_once()
        call_kwargs = mock_dq_checker_class.call_args
        assert call_kwargs[1]["validation_cache"] is fake_shared_cache


# ============================================================================
# Tests: Inventory building ImportError + Exception (5454-5532)
# ============================================================================


class TestProcessSingleDataviewInventoryBuilding:
    """Cover inventory building branches in process_single_dataview."""

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_derived_inventory_import_error(
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
        """ImportError while importing DerivedFieldInventoryBuilder is caught gracefully."""
        mock_logger, _, _ = _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            mock_excel_writer,
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )

        with patch(
            "cja_auto_sdr.inventory.derived_fields.DerivedFieldInventoryBuilder",
            side_effect=ImportError("no module"),
        ):
            result = process_single_dataview(
                data_view_id="dv_test_12345",
                config_file=mock_config_file,
                output_dir=temp_output_dir,
                include_derived_inventory=True,
                skip_validation=True,
            )
        assert result.success is True
        assert result.derived_fields_count == 0
        assert _mock_call_contains(mock_logger.warning, "Could not import derived field inventory: no module")
        assert _mock_call_contains(mock_logger.info, "Skipping derived field inventory - module not available")

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_derived_inventory_runtime_error_exception(
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
        """Unexpected runtime exception during derived field inventory is non-fatal."""
        mock_logger, _, _ = _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            mock_excel_writer,
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )

        with patch(
            "cja_auto_sdr.inventory.derived_fields.DerivedFieldInventoryBuilder",
        ) as mock_builder_cls:
            mock_builder_cls.return_value.build.side_effect = RuntimeError("build fail")
            result = process_single_dataview(
                data_view_id="dv_test_12345",
                config_file=mock_config_file,
                output_dir=temp_output_dir,
                include_derived_inventory=True,
                skip_validation=True,
            )
        assert result.success is True
        assert result.derived_fields_count == 0
        assert _mock_call_contains(mock_logger.error, "Error during derived field inventory: build fail")
        assert _mock_call_contains(
            mock_logger.info, "Continuing with SDR generation despite derived field inventory errors"
        )

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_calculated_metrics_import_error(
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
        """ImportError while importing CalculatedMetricsInventoryBuilder is caught."""
        mock_logger, _, _ = _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            mock_excel_writer,
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )

        with patch(
            "cja_auto_sdr.inventory.calculated_metrics.CalculatedMetricsInventoryBuilder",
            side_effect=ImportError("no module"),
        ):
            result = process_single_dataview(
                data_view_id="dv_test_12345",
                config_file=mock_config_file,
                output_dir=temp_output_dir,
                include_calculated_metrics=True,
                skip_validation=True,
            )
        assert result.success is True
        assert result.calculated_metrics_count == 0
        assert _mock_call_contains(mock_logger.warning, "Could not import calculated metrics inventory: no module")
        assert _mock_call_contains(mock_logger.info, "Skipping calculated metrics inventory - module not available")

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_calculated_metrics_runtime_error_exception(
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
        """Unexpected runtime exception during calculated metrics inventory is non-fatal."""
        mock_logger, _, _ = _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            mock_excel_writer,
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )

        with patch(
            "cja_auto_sdr.inventory.calculated_metrics.CalculatedMetricsInventoryBuilder",
        ) as mock_cls:
            mock_cls.return_value.build.side_effect = RuntimeError("calc fail")
            result = process_single_dataview(
                data_view_id="dv_test_12345",
                config_file=mock_config_file,
                output_dir=temp_output_dir,
                include_calculated_metrics=True,
                skip_validation=True,
            )
        assert result.success is True
        assert result.calculated_metrics_count == 0
        assert _mock_call_contains(mock_logger.error, "Error during calculated metrics inventory: calc fail")
        assert _mock_call_contains(
            mock_logger.info,
            "Continuing with SDR generation despite calculated metrics inventory errors",
        )

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_calculated_metrics_transport_exception(
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
        """Transport errors during calculated metrics inventory should be non-fatal."""
        mock_logger, _, _ = _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            mock_excel_writer,
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )

        with patch(
            "cja_auto_sdr.inventory.calculated_metrics.CalculatedMetricsInventoryBuilder",
        ) as mock_cls:
            mock_cls.return_value.build.side_effect = ConnectionError("calc transport fail")
            result = process_single_dataview(
                data_view_id="dv_test_12345",
                config_file=mock_config_file,
                output_dir=temp_output_dir,
                include_calculated_metrics=True,
                skip_validation=True,
            )
        assert result.success is True
        assert result.calculated_metrics_count == 0
        assert _mock_call_contains(mock_logger.error, "Error during calculated metrics inventory: calc transport fail")
        assert _mock_call_contains(
            mock_logger.info,
            "Continuing with SDR generation despite calculated metrics inventory errors",
        )

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_segments_inventory_import_error(
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
        """ImportError while importing SegmentsInventoryBuilder is caught."""
        mock_logger, _, _ = _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            mock_excel_writer,
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )

        with patch(
            "cja_auto_sdr.inventory.segments.SegmentsInventoryBuilder",
            side_effect=ImportError("no segments module"),
        ):
            result = process_single_dataview(
                data_view_id="dv_test_12345",
                config_file=mock_config_file,
                output_dir=temp_output_dir,
                include_segments_inventory=True,
                skip_validation=True,
            )
        assert result.success is True
        assert result.segments_count == 0
        assert _mock_call_contains(mock_logger.warning, "Could not import segments inventory: no segments module")
        assert _mock_call_contains(mock_logger.info, "Skipping segments inventory - module not available")

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_segments_inventory_runtime_error_exception(
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
        """Unexpected runtime exception during segments inventory is non-fatal."""
        mock_logger, _, _ = _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            mock_excel_writer,
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )

        with patch(
            "cja_auto_sdr.inventory.segments.SegmentsInventoryBuilder",
        ) as mock_cls:
            mock_cls.return_value.build.side_effect = RuntimeError("seg fail")
            result = process_single_dataview(
                data_view_id="dv_test_12345",
                config_file=mock_config_file,
                output_dir=temp_output_dir,
                include_segments_inventory=True,
                skip_validation=True,
            )
        assert result.success is True
        assert result.segments_count == 0
        assert _mock_call_contains(mock_logger.error, "Error during segments inventory: seg fail")
        assert _mock_call_contains(mock_logger.info, "Continuing with SDR generation despite segments inventory errors")

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_segments_inventory_transport_exception(
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
        """Transport errors during segments inventory should be non-fatal."""
        mock_logger, _, _ = _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            mock_excel_writer,
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )

        with patch(
            "cja_auto_sdr.inventory.segments.SegmentsInventoryBuilder",
        ) as mock_cls:
            mock_cls.return_value.build.side_effect = ConnectionError("segments transport fail")
            result = process_single_dataview(
                data_view_id="dv_test_12345",
                config_file=mock_config_file,
                output_dir=temp_output_dir,
                include_segments_inventory=True,
                skip_validation=True,
            )
        assert result.success is True
        assert result.segments_count == 0
        assert _mock_call_contains(mock_logger.error, "Error during segments inventory: segments transport fail")
        assert _mock_call_contains(mock_logger.info, "Continuing with SDR generation despite segments inventory errors")

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_parallel_inventory_serializes_shared_cja_calls(
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
        """Calculated/segments inventory builders should not call the shared CJA client concurrently."""
        _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            mock_excel_writer,
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )

        calc_inv = _make_mock_inventory_obj(total_calculated_metrics=5)
        seg_inv = _make_mock_inventory_obj(total_segments=7)

        state_lock = threading.Lock()
        active_calls = 0
        max_active_calls = 0
        first_call_claimed = False
        release_first_call = threading.Event()

        def _probe_build(return_inventory):
            nonlocal active_calls, max_active_calls, first_call_claimed

            with state_lock:
                active_calls += 1
                max_active_calls = max(max_active_calls, active_calls)
                is_first = not first_call_claimed
                if is_first:
                    first_call_claimed = True

            try:
                if is_first:
                    # Without serialization, the second builder enters and releases this wait.
                    # With serialization, this times out because the second call is blocked.
                    release_first_call.wait(timeout=0.30)
                else:
                    release_first_call.set()
                time.sleep(0.05)
                return return_inventory
            finally:
                with state_lock:
                    active_calls -= 1

        with (
            patch("cja_auto_sdr.inventory.calculated_metrics.CalculatedMetricsInventoryBuilder") as mock_calc_cls,
            patch("cja_auto_sdr.inventory.segments.SegmentsInventoryBuilder") as mock_seg_cls,
        ):
            mock_calc_cls.return_value.build.side_effect = lambda *_args, **_kwargs: _probe_build(calc_inv)
            mock_seg_cls.return_value.build.side_effect = lambda *_args, **_kwargs: _probe_build(seg_inv)

            result = process_single_dataview(
                data_view_id="dv_test_12345",
                config_file=mock_config_file,
                output_dir=temp_output_dir,
                include_calculated_metrics=True,
                include_segments_inventory=True,
                skip_validation=True,
            )

        assert result.success is True
        assert result.calculated_metrics_count == 5
        assert result.segments_count == 7
        assert max_active_calls == 1


# ============================================================================
# Tests: Metadata creation with inventory stats (5547-5676)
# ============================================================================


class TestProcessSingleDataviewMetadataWithInventory:
    """Cover metadata construction with inventory objects present."""

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_metadata_with_all_inventory_objects(
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
        """Lines 5599-5669: metadata includes inventory stats for all three inventory types."""
        _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            mock_excel_writer,
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )

        seg_inv = _make_mock_inventory_obj(total_segments=10)
        calc_inv = _make_mock_inventory_obj(total_calculated_metrics=5)
        derived_inv = _make_mock_inventory_obj(total_derived_fields=7, metrics_count=3, dimensions_count=4)

        with (
            patch("cja_auto_sdr.inventory.segments.SegmentsInventoryBuilder") as mock_seg_cls,
            patch("cja_auto_sdr.inventory.calculated_metrics.CalculatedMetricsInventoryBuilder") as mock_calc_cls,
            patch("cja_auto_sdr.inventory.derived_fields.DerivedFieldInventoryBuilder") as mock_der_cls,
        ):
            mock_seg_cls.return_value.build.return_value = seg_inv
            mock_calc_cls.return_value.build.return_value = calc_inv
            mock_der_cls.return_value.build.return_value = derived_inv

            result = process_single_dataview(
                data_view_id="dv_test_12345",
                config_file=mock_config_file,
                output_dir=temp_output_dir,
                include_derived_inventory=True,
                include_calculated_metrics=True,
                include_segments_inventory=True,
                skip_validation=True,
            )
        assert result.success is True
        assert result.segments_count == 10
        assert result.calculated_metrics_count == 5
        assert result.derived_fields_count == 7

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_metadata_exception_creates_placeholder(
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
        """Lines 5674-5676: exception during metadata creation produces fallback DataFrame."""
        _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            mock_excel_writer,
            sample_metrics_df,
            sample_dimensions_df,
            # Return a non-dict lookup_data to trigger the metadata exception
            # when .get() is called on it:
            {"id": "dv_test_12345", "name": "Test DV"},
        )

        # Make value_counts() raise inside the metadata try block by
        # providing a metrics DataFrame whose 'type' column blows up
        bad_metrics = sample_metrics_df.copy()
        bad_type_series = Mock()
        bad_type_series.value_counts.side_effect = TypeError("boom")
        with patch.object(bad_metrics, "__getitem__", side_effect=TypeError("boom")):
            # Reconfigure fetcher to return the bad metrics
            mock_fetcher = mock_fetcher_class.return_value
            mock_fetcher.fetch_all_data.return_value = (
                bad_metrics,
                sample_dimensions_df,
                {"id": "dv_test_12345", "name": "Test DV"},
            )
            result = process_single_dataview(
                data_view_id="dv_test_12345",
                config_file=mock_config_file,
                output_dir=temp_output_dir,
                skip_validation=True,
            )
        assert result.success is True


# ============================================================================
# Tests: Lookup data processing exception (5547-5549)
# ============================================================================


class TestProcessSingleDataviewLookupDataException:
    """Cover line 5547-5549: exception when processing lookup_data."""

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_lookup_data_processing_exception(
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
        """When lookup_data processing raises, a fallback DataFrame is created."""
        mock_logger = Mock()
        mock_logger.handlers = []
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        # Return lookup_data that passes post-fetch validation (non-empty real dict)
        # but has a value that causes errors during metadata DataFrame creation.
        # The metadata processing iterates over lookup_data items and tries to
        # build a DataFrame; a value that errors on str() will trigger the fallback.
        bad_value = MagicMock()
        bad_value.__str__ = Mock(side_effect=TypeError("bad str"))
        bad_value.__repr__ = Mock(side_effect=TypeError("bad repr"))
        bad_lookup = {"id": "dv_test_12345", "name": "Unknown", "bad_key": bad_value}
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, bad_lookup)
        mock_fetcher.get_tuner_statistics.return_value = None
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq = Mock()
        mock_dq.issues = []
        mock_dq.get_issues_dataframe.return_value = pd.DataFrame(
            columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"],
        )
        mock_dq_checker_class.return_value = mock_dq

        mock_writer = MagicMock()
        mock_excel_writer.return_value.__enter__ = Mock(return_value=mock_writer)
        mock_excel_writer.return_value.__exit__ = Mock(return_value=False)

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            skip_validation=True,
        )
        # Even if lookup processing fails, SDR still succeeds
        assert result.success is True


# ============================================================================
# Tests: JSON formatting exception (5705-5706)
# ============================================================================


class TestProcessSingleDataviewJSONFormatException:
    """Cover lines 5705-5706: exception applying JSON formatting."""

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_json_formatting_exception_handled(
        self,
        mock_excel_writer,
        mock_apply_formatting,
        mock_dq_checker_class,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        temp_output_dir,
        sample_dataview_info,
    ):
        """Exception during JSON cell formatting is logged but does not crash."""
        _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            mock_excel_writer,
            # Use a DataFrame whose .map() will raise
            pd.DataFrame({"id": ["m1"], "name": ["M1"], "type": ["standard"]}),
            pd.DataFrame({"id": ["d1"], "name": ["D1"], "type": ["string"]}),
            sample_dataview_info,
        )

        # Make .map raise on the lookup_df columns iteration
        original_map = pd.Series.map

        map_calls = count(1)

        def failing_map(self, func, **kwargs):
            # Fail on the 4th call to exercise the except block
            if next(map_calls) == 4:
                raise ValueError("map failed")
            return original_map(self, func, **kwargs)

        with patch.object(pd.Series, "map", failing_map):
            result = process_single_dataview(
                data_view_id="dv_test_12345",
                config_file=mock_config_file,
                output_dir=temp_output_dir,
                skip_validation=True,
            )
        assert result.success is True


# ============================================================================
# Tests: Filename exception fallback (5718-5721)
# ============================================================================


class TestProcessSingleDataviewFilenameException:
    """Cover lines 5718-5721: exception creating filename uses fallback."""

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_filename_creation_exception_uses_fallback(
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
        """When filename creation raises, fallback filename is used."""
        mock_logger = Mock()
        mock_logger.handlers = []
        mock_setup_logging.return_value = mock_logger
        mock_cja = Mock()
        mock_init_cja.return_value = mock_cja

        mock_fetcher = Mock()
        # lookup_data returns something that causes .get("name") to raise
        # when used with string operations for sanitization
        bad_info = {"id": "dv_test_12345"}
        # The get("name", "Unknown") returns "Unknown", but let's make isalnum() fail
        # by patching the generator join operation
        bad_info["name"] = MagicMock()
        bad_info["name"].__str__ = Mock(side_effect=RuntimeError("str fail"))
        mock_fetcher.fetch_all_data.return_value = (sample_metrics_df, sample_dimensions_df, bad_info)
        mock_fetcher.get_tuner_statistics.return_value = None
        mock_fetcher_class.return_value = mock_fetcher

        mock_dq = Mock()
        mock_dq.issues = []
        mock_dq.get_issues_dataframe.return_value = pd.DataFrame(
            columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"],
        )
        mock_dq_checker_class.return_value = mock_dq

        mock_writer = MagicMock()
        mock_excel_writer.return_value.__enter__ = Mock(return_value=mock_writer)
        mock_excel_writer.return_value.__exit__ = Mock(return_value=False)

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            skip_validation=True,
        )
        assert result.success is True


# ============================================================================
# Tests: Output format routing (5731, 5743-5769, 5791)
# ============================================================================


class TestProcessSingleDataviewOutputFormats:
    """Cover inventory_only mode, placeholder creation, and FORMAT_ALIASES."""

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_inventory_only_mode(
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
        """Line 5731: inventory_only=True produces empty data_dict."""
        _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            mock_excel_writer,
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            inventory_only=True,
            skip_validation=True,
        )
        assert result.success is True

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_placeholder_sheets_when_inventory_flags_but_no_data(
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
        """Lines 5743-5769: placeholder sheets created when flags set but no inventory data found."""
        _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            mock_excel_writer,
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )

        # Make all inventory builders raise ImportError so data stays empty
        with (
            patch(
                "cja_auto_sdr.inventory.derived_fields.DerivedFieldInventoryBuilder",
                side_effect=ImportError("no mod"),
            ),
            patch(
                "cja_auto_sdr.inventory.calculated_metrics.CalculatedMetricsInventoryBuilder",
                side_effect=ImportError("no mod"),
            ),
            patch(
                "cja_auto_sdr.inventory.segments.SegmentsInventoryBuilder",
                side_effect=ImportError("no mod"),
            ),
        ):
            result = process_single_dataview(
                data_view_id="dv_test_12345",
                config_file=mock_config_file,
                output_dir=temp_output_dir,
                include_derived_inventory=True,
                include_calculated_metrics=True,
                include_segments_inventory=True,
                skip_validation=True,
            )
        assert result.success is True

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.write_json_output")
    def test_format_alias_reports(
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
        """Line 5791: FORMAT_ALIASES resolves 'data' to ['csv', 'json']."""
        _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            MagicMock(),  # not used for non-excel
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )
        mock_write_json.return_value = str(Path(temp_output_dir) / "out.json")

        with (
            patch("cja_auto_sdr.generator.write_csv_output") as mock_csv,
            patch("cja_auto_sdr.generator.apply_excel_formatting"),
            patch("pandas.ExcelWriter") as mock_ew,
        ):
            mock_csv.return_value = str(Path(temp_output_dir) / "csv_dir")
            mock_writer = MagicMock()
            mock_ew.return_value.__enter__ = Mock(return_value=mock_writer)
            mock_ew.return_value.__exit__ = Mock(return_value=False)

            result = process_single_dataview(
                data_view_id="dv_test_12345",
                config_file=mock_config_file,
                output_dir=temp_output_dir,
                output_format="data",
                skip_validation=True,
            )
        assert result.success is True
        mock_csv.assert_called_once()
        mock_write_json.assert_called_once()


# ============================================================================
# Tests: Excel inventory placeholder sheets in writer loop (5835-5859)
# ============================================================================


class TestProcessSingleDataviewExcelPlaceholders:
    """Cover lines 5835-5859: inventory placeholder sheets written to Excel."""

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_excel_placeholder_sheets_for_empty_inventory(
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
        """Placeholder sheets are written in Excel loop when flags set but data empty."""
        _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            mock_excel_writer,
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )

        with (
            patch(
                "cja_auto_sdr.inventory.derived_fields.DerivedFieldInventoryBuilder",
                side_effect=ImportError("x"),
            ),
            patch(
                "cja_auto_sdr.inventory.calculated_metrics.CalculatedMetricsInventoryBuilder",
                side_effect=ImportError("x"),
            ),
            patch(
                "cja_auto_sdr.inventory.segments.SegmentsInventoryBuilder",
                side_effect=ImportError("x"),
            ),
        ):
            result = process_single_dataview(
                data_view_id="dv_test_12345",
                config_file=mock_config_file,
                output_dir=temp_output_dir,
                include_derived_inventory=True,
                include_calculated_metrics=True,
                include_segments_inventory=True,
                output_format="excel",
                skip_validation=True,
                inventory_order=["segments", "calculated", "derived"],
            )
        assert result.success is True
        # apply_excel_formatting should have been called for standard + placeholder sheets
        assert mock_apply_formatting.call_count >= 5

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_excel_sheet_write_exception_handled(
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
        """Lines 5857-5859: exception writing individual sheet logs error and continues."""
        _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            mock_excel_writer,
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )
        mock_apply_formatting.side_effect = OSError("write fail")

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            skip_validation=True,
        )
        assert result.success is True


# ============================================================================
# Tests: show_timings + inventory summary stats (5921, 5948-5960)
# ============================================================================


class TestProcessSingleDataviewTimingsAndSummary:
    """Cover lines 5921 and 5948-5960: show_timings output and inventory summary collection."""

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_show_timings_prints_summary(
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
        capsys,
    ):
        """Line 5921: when show_timings=True, perf summary is printed to stdout."""
        _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            mock_excel_writer,
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            show_timings=True,
            skip_validation=True,
        )
        assert result.success is True
        captured = capsys.readouterr()
        # show_timings should print a valid perf summary string
        assert captured.out.strip() != ""
        assert "Traceback" not in captured.out
        assert any(marker in captured.out for marker in ("PERFORMANCE SUMMARY", "No performance metrics collected"))


# ============================================================================
# Tests: File writing exception handlers (6000-6011)
# ============================================================================


class TestProcessSingleDataviewFileWriteErrors:
    """Cover lines 5982-6017: PermissionError and generic Exception during file write."""

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_permission_error_during_write(
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
        """PermissionError during Excel write returns failed result."""
        _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            mock_excel_writer,
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )
        mock_excel_writer.side_effect = PermissionError("denied")

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            skip_validation=True,
        )
        assert result.success is False
        assert "Permission denied" in result.error_message

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    def test_generic_exception_during_write(
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
        """Lines 6000-6011: generic exception during file write returns failed result."""
        _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            mock_excel_writer,
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )
        mock_excel_writer.side_effect = OSError("disk full")

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            skip_validation=True,
        )
        assert result.success is False
        assert "disk full" in result.error_message


# ============================================================================
# Tests: BatchProcessor.__init__ OSError (6234-6235)
# ============================================================================


class TestBatchProcessorInitOSError:
    """Cover lines 6234-6235: OSError creating output directory."""

    @patch("cja_auto_sdr.generator.setup_logging")
    def test_oserror_raises_output_error(self, mock_setup_logging, mock_config_file):
        """OSError during mkdir raises OutputError."""
        mock_setup_logging.return_value = Mock()

        with (
            patch("pathlib.Path.mkdir", side_effect=OSError("no space")),
            pytest.raises(OutputError, match="Cannot create output directory"),
        ):
            BatchProcessor(
                config_file=mock_config_file,
                output_dir="/nonexistent/deeply/nested/path",
                workers=2,
            )


# ============================================================================
# Tests: BatchProcessor stop on error (6330-6336)
# ============================================================================


class TestBatchProcessorStopOnError:
    """Cover lines 6330-6336: stop batch when continue_on_error=False."""

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.as_completed")
    @patch("cja_auto_sdr.generator.ProcessPoolExecutor")
    def test_batch_stops_on_first_error(
        self, mock_executor_cls, mock_as_completed, mock_setup_logging, tmp_path, mock_config_file
    ):
        """When continue_on_error=False, batch stops after first failure."""
        mock_setup_logging.return_value = Mock()

        failed_result = ProcessingResult(
            data_view_id="dv_fail",
            data_view_name="Fail View",
            success=False,
            duration=1.0,
            error_message="API error",
        )
        success_result = ProcessingResult(
            data_view_id="dv_ok",
            data_view_name="OK View",
            success=True,
            duration=0.5,
        )

        # Mock the executor to avoid ProcessPoolExecutor pickling issues
        mock_future_fail = Mock()
        mock_future_fail.result.return_value = failed_result
        mock_future_ok = Mock()
        mock_future_ok.result.return_value = success_result

        mock_executor_instance = MagicMock()
        mock_executor_instance.__enter__ = Mock(return_value=mock_executor_instance)
        mock_executor_instance.__exit__ = Mock(return_value=False)
        mock_executor_instance.submit.side_effect = [mock_future_fail, mock_future_ok]
        mock_executor_cls.return_value = mock_executor_instance

        # Return only the first future — batch should stop after the failure
        mock_as_completed.return_value = [mock_future_fail]

        output_dir = str(tmp_path / "batch_output")

        bp = BatchProcessor(
            config_file=mock_config_file,
            output_dir=output_dir,
            workers=1,
            continue_on_error=False,
            quiet=True,
        )
        results = bp.process_batch(["dv_fail", "dv_ok"])
        # At least one failure should be recorded
        assert len(results["failed"]) >= 1


# ============================================================================
# Tests: run_dry_run (6499-6694)
# ============================================================================


class TestRunDryRunProfileValidation:
    """Cover run_dry_run profile validation paths."""

    def test_profile_not_found(self, capsys):
        """Lines 6506-6508: ProfileNotFoundError during profile validation."""
        logger = logging.getLogger("test_dry_run_pnf")
        with patch(
            "cja_auto_sdr.generator.load_profile_credentials",
            side_effect=ProfileNotFoundError("myprofile"),
        ):
            result = run_dry_run(["dv_test"], "config.json", logger, profile="myprofile")
        assert result is False
        captured = capsys.readouterr()
        assert "not found" in captured.out

    def test_profile_config_error(self, capsys):
        """Lines 6509-6511: ProfileConfigError during profile validation."""
        logger = logging.getLogger("test_dry_run_pce")
        with patch(
            "cja_auto_sdr.generator.load_profile_credentials",
            side_effect=ProfileConfigError("bad config"),
        ):
            result = run_dry_run(["dv_test"], "config.json", logger, profile="badprofile")
        assert result is False
        captured = capsys.readouterr()
        assert "configuration error" in captured.out

    def test_profile_no_valid_credentials(self, capsys):
        """Lines 6503-6505: profile found but returns no valid credentials."""
        logger = logging.getLogger("test_dry_run_nocreds")
        with patch("cja_auto_sdr.generator.load_profile_credentials", return_value=None):
            result = run_dry_run(["dv_test"], "config.json", logger, profile="emptycreds")
        assert result is False
        captured = capsys.readouterr()
        assert "no valid credentials" in captured.out

    def test_profile_valid_credentials(self, capsys):
        """Lines 6501-6502: profile found with valid credentials."""
        logger = logging.getLogger("test_dry_run_valid")
        with (
            patch("cja_auto_sdr.generator.load_profile_credentials", return_value={"client_id": "x"}),
            patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "profile", {})),
            patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
            patch("cja_auto_sdr.generator.make_api_call_with_retry") as mock_retry,
        ):
            mock_cja = MagicMock()
            mock_cjapy.CJA.return_value = mock_cja
            mock_retry.side_effect = [
                [{"id": "dv_test", "name": "Test"}],  # getDataViews
                {"name": "Test", "id": "dv_test"},  # getDataView
                [],  # getMetrics
                [],  # getDimensions
            ]
            run_dry_run(["dv_test"], "config.json", logger, profile="goodprofile")
        captured = capsys.readouterr()
        assert "Profile 'goodprofile' found and valid" in captured.out


class TestRunDryRunAPIValidation:
    """Cover run_dry_run API connection and data view validation."""

    def test_configure_cjapy_fails(self, capsys):
        """Lines 6533-6538: configure_cjapy returns failure."""
        logger = logging.getLogger("test_dry_run_cjapy_fail")
        with (
            patch("cja_auto_sdr.generator.validate_config_file", return_value=True),
            patch("cja_auto_sdr.generator.configure_cjapy", return_value=(False, "bad creds", {})),
        ):
            result = run_dry_run(["dv_test"], "config.json", logger)
        assert result is False
        captured = capsys.readouterr()
        assert "Credential configuration failed" in captured.out

    def test_api_connection_exception(self, capsys):
        """Lines 6558-6565: exception during API connection test."""
        logger = logging.getLogger("test_dry_run_api_exc")
        with (
            patch("cja_auto_sdr.generator.validate_config_file", return_value=True),
            patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "config", {})),
            patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        ):
            mock_cjapy.CJA.side_effect = ConfigurationError("connection refused")
            result = run_dry_run(["dv_test"], "config.json", logger)
        assert result is False
        captured = capsys.readouterr()
        assert "API connection failed" in captured.out

    def test_api_connection_missing_method_exception(self, capsys):
        """Missing cjapy methods should be reported as controlled dry-run failure."""
        logger = logging.getLogger("test_dry_run_api_missing_method")
        with (
            patch("cja_auto_sdr.generator.validate_config_file", return_value=True),
            patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "config", {})),
            patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        ):
            mock_cjapy.CJA.return_value = object()  # no getDataViews attribute
            result = run_dry_run(["dv_test"], "config.json", logger)
        assert result is False
        captured = capsys.readouterr()
        assert "API connection failed" in captured.out

    def test_api_connection_key_error_shows_hint(self, capsys):
        """KeyError('content') during the step-[2/3] probe should include the remediation hint."""
        logger = logging.getLogger("test_dry_run_api_keyerror_hint")
        with (
            patch("cja_auto_sdr.generator.validate_config_file", return_value=True),
            patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "config", {})),
            patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
            patch("cja_auto_sdr.generator.make_api_call_with_retry", side_effect=KeyError("content")),
        ):
            mock_cjapy.CJA.return_value = MagicMock()
            result = run_dry_run(["dv_test"], "config.json", logger)
        assert result is False
        captured = capsys.readouterr()
        assert "API connection failed: 'content'" in captured.out
        assert "AEP API" in captured.out

    def test_api_connection_runtime_auth_error_shows_hint(self, capsys):
        """HTTP 401/403 text in the fallback branch should still surface the API hint."""
        logger = logging.getLogger("test_dry_run_api_runtime_hint")
        with (
            patch("cja_auto_sdr.generator.validate_config_file", return_value=True),
            patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "config", {})),
            patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
            patch("cja_auto_sdr.generator.make_api_call_with_retry", side_effect=RuntimeError("HTTP 403 Forbidden")),
        ):
            mock_cjapy.CJA.return_value = MagicMock()
            result = run_dry_run(["dv_test"], "config.json", logger)
        assert result is False
        captured = capsys.readouterr()
        assert "API connection failed: HTTP 403 Forbidden" in captured.out
        assert "authentication or authorization failed" in captured.out

    def test_api_connection_unexpected_runtime_exception(self, capsys):
        """Unexpected runtime exceptions during API probe should still fail gracefully."""
        logger = logging.getLogger("test_dry_run_api_runtime")
        with (
            patch("cja_auto_sdr.generator.validate_config_file", return_value=True),
            patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "config", {})),
            patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
            patch("cja_auto_sdr.generator.make_api_call_with_retry", side_effect=RuntimeError("runtime boom")),
        ):
            mock_cjapy.CJA.return_value = MagicMock()
            result = run_dry_run(["dv_test"], "config.json", logger)
        assert result is False
        captured = capsys.readouterr()
        assert "API connection failed: runtime boom" in captured.out

    def test_dv_validation_with_metric_dimension_errors(self, capsys):
        """Lines 6611-6624: errors fetching metrics/dimensions counts are handled."""
        logger = logging.getLogger("test_dry_run_metric_err")
        with (
            patch("cja_auto_sdr.generator.validate_config_file", return_value=True),
            patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "config", {})),
            patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
            patch("cja_auto_sdr.generator.make_api_call_with_retry") as mock_retry,
        ):
            mock_cja = MagicMock()
            mock_cjapy.CJA.return_value = mock_cja

            mock_retry.side_effect = [
                [],  # getDataViews
                {"id": "dv_test", "name": "Test DV"},  # getDataView
                OSError("metrics fetch fail"),  # getMetrics
                ValueError("dimensions fetch fail"),  # getDimensions
            ]

            result = run_dry_run(["dv_test"], "config.json", logger)
        # Still passes because the DV was found
        assert result is True

    def test_dv_validation_missing_component_method_degrades_to_zero(self, capsys):
        """Missing metric/dimension methods should not abort dry-run validation."""
        logger = logging.getLogger("test_dry_run_missing_component_method")

        def _mock_retry_call(*_args, **kwargs):
            op = kwargs.get("operation_name")
            if op == "getDataViews (dry-run)":
                return []
            if op == "getDataView(dv_partial)":
                return {"id": "dv_partial", "name": "Partial DV"}
            if op == "getMetrics(dv_partial)":
                raise DiscoveryNotFoundError("missing getMetrics")
            if op == "getDimensions(dv_partial)":
                return [{"id": "d1"}, {"id": "d2"}]
            raise AssertionError(f"Unexpected operation: {op}")

        with (
            patch("cja_auto_sdr.generator.validate_config_file", return_value=True),
            patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "config", {})),
            patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
            patch("cja_auto_sdr.generator.make_api_call_with_retry", side_effect=_mock_retry_call),
            patch("cja_auto_sdr.cli.commands.discovery.make_api_call_with_retry", side_effect=_mock_retry_call),
        ):
            mock_cja = MagicMock()
            mock_cjapy.CJA.return_value = mock_cja

            result = run_dry_run(["dv_partial"], "config.json", logger)

        assert result is True
        captured = capsys.readouterr()
        assert "dv_partial: Partial DV" in captured.out
        assert "Components: 0 metrics, 2 dimensions" in captured.out

    def test_dv_not_found(self, capsys):
        """Lines 6636-6638: data view getDataView returns None."""
        logger = logging.getLogger("test_dry_run_dv_not_found")
        with (
            patch("cja_auto_sdr.generator.validate_config_file", return_value=True),
            patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "config", {})),
            patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
            patch("cja_auto_sdr.generator.make_api_call_with_retry") as mock_retry,
        ):
            mock_cja = MagicMock()
            mock_cjapy.CJA.return_value = mock_cja

            mock_retry.side_effect = [
                [],  # getDataViews
                None,  # getDataView returns None
            ]

            result = run_dry_run(["dv_missing"], "config.json", logger)
        assert result is False
        captured = capsys.readouterr()
        assert "Not found" in captured.out

    def test_dv_validation_generic_exception(self, capsys):
        """Lines 6643-6646: generic exception during data view validation."""
        logger = logging.getLogger("test_dry_run_dv_exc")
        with (
            patch("cja_auto_sdr.generator.validate_config_file", return_value=True),
            patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "config", {})),
            patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
            patch("cja_auto_sdr.generator.make_api_call_with_retry") as mock_retry,
        ):
            mock_cja = MagicMock()
            mock_cjapy.CJA.return_value = mock_cja

            mock_retry.side_effect = [
                [],  # getDataViews
                APIError("unexpected error"),
            ]

            result = run_dry_run(["dv_err"], "config.json", logger)
        assert result is False
        captured = capsys.readouterr()
        assert "Error" in captured.out

    def test_dv_validation_unexpected_runtime_exception(self, capsys):
        """Unexpected runtime errors during per-view validation should not traceback."""
        logger = logging.getLogger("test_dry_run_dv_runtime_exc")
        with (
            patch("cja_auto_sdr.generator.validate_config_file", return_value=True),
            patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "config", {})),
            patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
            patch("cja_auto_sdr.generator.make_api_call_with_retry") as mock_retry,
        ):
            mock_cja = MagicMock()
            mock_cjapy.CJA.return_value = mock_cja

            mock_retry.side_effect = [
                [],  # getDataViews
                RuntimeError("per-view runtime failure"),
            ]

            result = run_dry_run(["dv_err"], "config.json", logger)
        assert result is False
        captured = capsys.readouterr()
        assert "dv_err: Error - per-view runtime failure" in captured.out

    def test_dv_validation_http_403_uses_data_view_access_hint(self, capsys):
        """Per-data-view 403 failures should mention no-access/not-found guidance."""
        logger = logging.getLogger("test_dry_run_dv_403_hint")
        with (
            patch("cja_auto_sdr.generator.validate_config_file", return_value=True),
            patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "config", {})),
            patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
            patch("cja_auto_sdr.generator.make_api_call_with_retry") as mock_retry,
        ):
            mock_cja = MagicMock()
            mock_cjapy.CJA.return_value = mock_cja

            mock_retry.side_effect = [
                [],  # getDataViews
                RuntimeError("HTTP 403 Forbidden"),
            ]

            result = run_dry_run(["dv_forbidden"], "config.json", logger)
        assert result is False
        captured = capsys.readouterr()
        assert "dv_forbidden: Error - HTTP 403 Forbidden" in captured.out
        assert "accessing this data view" in captured.out
        assert "have access to it" in captured.out

    def test_dv_component_validation_http_403_uses_generic_auth_hint(self, capsys):
        """Later component-count 403s should not be mislabeled as lookup failures."""
        logger = logging.getLogger("test_dry_run_dv_component_403_hint")
        with (
            patch("cja_auto_sdr.generator.validate_config_file", return_value=True),
            patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "config", {})),
            patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
            patch("cja_auto_sdr.generator.make_api_call_with_retry") as mock_retry,
            patch(
                "cja_auto_sdr.generator._count_component_items_for_fetch_spec_with_retry",
                side_effect=RuntimeError("HTTP 403 Forbidden"),
            ),
        ):
            mock_cja = MagicMock()
            mock_cjapy.CJA.return_value = mock_cja

            mock_retry.side_effect = [
                [],  # getDataViews
                {"id": "dv_components", "name": "Component DV"},
            ]

            result = run_dry_run(["dv_components"], "config.json", logger)
        assert result is False
        captured = capsys.readouterr()
        assert "dv_components: Error - HTTP 403 Forbidden" in captured.out
        assert "authentication or authorization failed" in captured.out
        assert "accessing this data view" not in captured.out

    def test_dv_validation_retryable_error_continues_to_next_view(self, capsys):
        """Retryable transport failure for one data view should not abort the full loop."""
        logger = logging.getLogger("test_dry_run_retryable_continue")
        with (
            patch("cja_auto_sdr.generator.validate_config_file", return_value=True),
            patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "config", {})),
            patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
            patch("cja_auto_sdr.generator.make_api_call_with_retry") as mock_retry,
        ):
            mock_cja = MagicMock()
            mock_cjapy.CJA.return_value = mock_cja

            def _mock_retry_call(*_args, **kwargs):
                op = kwargs.get("operation_name")
                if op == "getDataViews (dry-run)":
                    return []
                if op == "getDataView(dv_flaky)":
                    raise RetryableHTTPError(504, "gateway timeout")
                if op == "getDataView(dv_ok)":
                    return {"id": "dv_ok", "name": "Healthy DV"}
                if op == "getMetrics(dv_ok)":
                    return []
                if op == "getDimensions(dv_ok)":
                    return []
                raise AssertionError(f"Unexpected operation: {op}")

            mock_retry.side_effect = _mock_retry_call

            result = run_dry_run(["dv_flaky", "dv_ok"], "config.json", logger)

        # One invalid + one valid should still complete the loop and return False.
        assert result is False
        captured = capsys.readouterr()
        assert "dv_flaky" in captured.out
        assert "dv_ok: Healthy DV" in captured.out


# ============================================================================
# Tests: _bounded_float (6691-6694)
# ============================================================================


class TestBoundedFloat:
    """Cover lines 6691-6694: _bounded_float type factory."""

    def test_valid_value_within_bounds(self):
        from cja_auto_sdr.generator import _bounded_float

        converter = _bounded_float(0.0, 1.0)
        assert converter("0.5") == 0.5

    def test_value_at_lower_bound(self):
        from cja_auto_sdr.generator import _bounded_float

        converter = _bounded_float(0.0, 1.0)
        assert converter("0.0") == 0.0

    def test_value_at_upper_bound(self):
        from cja_auto_sdr.generator import _bounded_float

        converter = _bounded_float(0.0, 1.0)
        assert converter("1.0") == 1.0

    def test_value_below_lower_bound_raises(self):
        from cja_auto_sdr.generator import _bounded_float

        converter = _bounded_float(0.0, 1.0)
        with pytest.raises(argparse.ArgumentTypeError, match="must be between"):
            converter("-0.1")

    def test_value_above_upper_bound_raises(self):
        from cja_auto_sdr.generator import _bounded_float

        converter = _bounded_float(0.0, 1.0)
        with pytest.raises(argparse.ArgumentTypeError, match="must be between"):
            converter("1.1")

    def test_function_name_set(self):
        from cja_auto_sdr.generator import _bounded_float

        converter = _bounded_float(0.0, 100.0)
        assert "float[0.0-100.0]" in converter.__name__


# ============================================================================
# Tests: process_inventory_summary exception handlers (5097-5112)
# ============================================================================


class TestProcessInventorySummaryExceptionHandlers:
    """Cover lines 5097-5112: calculated/segments exception handlers in process_inventory_summary."""

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.display_inventory_summary")
    def test_calculated_metrics_exception_handled(
        self,
        mock_display,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        capsys,
    ):
        """Lines 5097-5102: exception building calculated metrics inventory is caught."""
        from cja_auto_sdr.generator import process_inventory_summary

        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger

        mock_cja = MagicMock()
        mock_init_cja.return_value = mock_cja
        mock_cja.dataviews.get_single.return_value = {"name": "Test DV"}

        mock_display.return_value = {"status": "ok"}

        # Patch the import of the calculated metrics module to simulate failure
        import builtins

        original_import = builtins.__import__

        def fail_calculated_import(name, *args, **kwargs):
            if name == "cja_auto_sdr.inventory.calculated_metrics":
                raise ImportError("no calculated module")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fail_calculated_import):
            process_inventory_summary(
                data_view_id="dv_test",
                config_file=mock_config_file,
                include_calculated=True,
                quiet=True,
            )
        # Should still return a result (display_inventory_summary called with None inventory)
        mock_display.assert_called_once()
        call_kwargs = mock_display.call_args[1]
        assert call_kwargs["calculated_inventory"] is None
        assert _mock_call_contains(
            mock_logger.warning,
            "Failed to build calculated metrics inventory: no calculated module",
        )

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.display_inventory_summary")
    def test_segments_exception_handled(
        self,
        mock_display,
        mock_init_cja,
        mock_setup_logging,
        mock_config_file,
        capsys,
    ):
        """Lines 5107-5114: exception building segments inventory is caught."""
        from cja_auto_sdr.generator import process_inventory_summary

        mock_logger = Mock()
        mock_setup_logging.return_value = mock_logger

        mock_cja = MagicMock()
        mock_init_cja.return_value = mock_cja
        mock_cja.dataviews.get_single.return_value = {"name": "Test DV"}

        mock_display.return_value = {"status": "ok"}

        import builtins

        original_import = builtins.__import__

        def fail_segments_import(name, *args, **kwargs):
            if name == "cja_auto_sdr.inventory.segments":
                raise ImportError("no segments module")
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=fail_segments_import):
            process_inventory_summary(
                data_view_id="dv_test",
                config_file=mock_config_file,
                include_segments=True,
                quiet=True,
            )
        mock_display.assert_called_once()
        call_kwargs = mock_display.call_args[1]
        assert call_kwargs["segments_inventory"] is None
        assert _mock_call_contains(
            mock_logger.warning,
            "Failed to build segments inventory: no segments module",
        )


# ============================================================================
# Tests: run_dry_run keyboard interrupt handlers (6554-6557, 6639-6642)
# ============================================================================


class TestRunDryRunKeyboardInterrupt:
    """Cover keyboard interrupt handling in run_dry_run."""

    def test_keyboard_interrupt_during_api_connection(self, capsys):
        """Lines 6554-6557: KeyboardInterrupt during API connection re-raises."""
        logger = logging.getLogger("test_dry_run_kbi_api")
        with (
            patch("cja_auto_sdr.generator.validate_config_file", return_value=True),
            patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "config", {})),
            patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        ):
            mock_cjapy.CJA.side_effect = KeyboardInterrupt()
            with pytest.raises(KeyboardInterrupt):
                run_dry_run(["dv_test"], "config.json", logger)

    def test_keyboard_interrupt_during_dv_validation(self, capsys):
        """Lines 6639-6642: KeyboardInterrupt during DV validation re-raises."""
        logger = logging.getLogger("test_dry_run_kbi_dv")
        with (
            patch("cja_auto_sdr.generator.validate_config_file", return_value=True),
            patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "config", {})),
            patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
            patch("cja_auto_sdr.generator.make_api_call_with_retry") as mock_retry,
        ):
            mock_cja = MagicMock()
            mock_cjapy.CJA.return_value = mock_cja

            mock_retry.side_effect = [
                [],  # getDataViews
                KeyboardInterrupt(),
            ]

            with pytest.raises(KeyboardInterrupt):
                run_dry_run(["dv_test"], "config.json", logger)


# ============================================================================
# Tests: run_dry_run config file validation failure
# ============================================================================


class TestRunDryRunConfigFileValidation:
    """Cover config file validation path when no profile is specified."""

    def test_config_file_validation_fails(self, capsys):
        """Lines 6516-6518: config file validation fails."""
        logger = logging.getLogger("test_dry_run_config_fail")
        with patch("cja_auto_sdr.generator.validate_config_file", return_value=False):
            result = run_dry_run(["dv_test"], "config.json", logger)
        assert result is False
        captured = capsys.readouterr()
        assert "Configuration file validation failed" in captured.out


# ============================================================================
# Tests: run_dry_run API returns None (unstable)
# ============================================================================


class TestRunDryRunAPIReturnsNone:
    """Cover the branch where getDataViews returns None."""

    def test_api_returns_none_for_dataviews(self, capsys):
        """Lines 6551-6553: API returns None - warning printed."""
        logger = logging.getLogger("test_dry_run_api_none")
        with (
            patch("cja_auto_sdr.generator.validate_config_file", return_value=True),
            patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "config", {})),
            patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
            patch("cja_auto_sdr.generator.make_api_call_with_retry") as mock_retry,
        ):
            mock_cja = MagicMock()
            mock_cjapy.CJA.return_value = mock_cja

            mock_retry.side_effect = [
                None,  # getDataViews (unstable)
                {"id": "dv_test", "name": "Found DV"},  # getDataView
                [],  # getMetrics
                [],  # getDimensions
            ]

            run_dry_run(["dv_test"], "config.json", logger)
        captured = capsys.readouterr()
        assert "may be unstable" in captured.out


# ============================================================================
# Tests: process_single_dataview with multiple output formats
# ============================================================================


class TestProcessSingleDataviewMultipleFormats:
    """Cover HTML, markdown, and all-formats output routing."""

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.apply_excel_formatting")
    @patch("pandas.ExcelWriter")
    @patch("cja_auto_sdr.generator.write_html_output")
    @patch("cja_auto_sdr.generator.write_markdown_output")
    @patch("cja_auto_sdr.generator.write_csv_output")
    @patch("cja_auto_sdr.generator.write_json_output")
    def test_all_formats(
        self,
        mock_json,
        mock_csv,
        mock_md,
        mock_html,
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
        """output_format='all' generates all five formats."""
        _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            mock_excel_writer,
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )
        mock_json.return_value = str(Path(temp_output_dir) / "out.json")
        mock_csv.return_value = str(Path(temp_output_dir) / "csv_dir")
        mock_html.return_value = str(Path(temp_output_dir) / "out.html")
        mock_md.return_value = str(Path(temp_output_dir) / "out.md")

        result = process_single_dataview(
            data_view_id="dv_test_12345",
            config_file=mock_config_file,
            output_dir=temp_output_dir,
            output_format="all",
            skip_validation=True,
        )
        assert result.success is True
        mock_csv.assert_called_once()
        mock_json.assert_called_once()
        mock_html.assert_called_once()
        mock_md.assert_called_once()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.write_html_output")
    def test_html_format(
        self,
        mock_html,
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
        """HTML format routing works."""
        _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            MagicMock(),
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )
        mock_html.return_value = str(Path(temp_output_dir) / "out.html")

        with (
            patch("cja_auto_sdr.generator.apply_excel_formatting"),
            patch("pandas.ExcelWriter") as mock_ew,
        ):
            mock_writer = MagicMock()
            mock_ew.return_value.__enter__ = Mock(return_value=mock_writer)
            mock_ew.return_value.__exit__ = Mock(return_value=False)
            result = process_single_dataview(
                data_view_id="dv_test_12345",
                config_file=mock_config_file,
                output_dir=temp_output_dir,
                output_format="html",
                skip_validation=True,
            )
        assert result.success is True
        mock_html.assert_called_once()

    @patch("cja_auto_sdr.generator.setup_logging")
    @patch("cja_auto_sdr.generator.initialize_cja")
    @patch("cja_auto_sdr.generator.ParallelAPIFetcher")
    @patch("cja_auto_sdr.generator.DataQualityChecker")
    @patch("cja_auto_sdr.generator.write_markdown_output")
    def test_markdown_format(
        self,
        mock_md,
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
        """Markdown format routing works."""
        _configure_standard_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            mock_dq_checker_class,
            MagicMock(),
            sample_metrics_df,
            sample_dimensions_df,
            sample_dataview_info,
        )
        mock_md.return_value = str(Path(temp_output_dir) / "out.md")

        with (
            patch("cja_auto_sdr.generator.apply_excel_formatting"),
            patch("pandas.ExcelWriter") as mock_ew,
        ):
            mock_writer = MagicMock()
            mock_ew.return_value.__enter__ = Mock(return_value=mock_writer)
            mock_ew.return_value.__exit__ = Mock(return_value=False)
            result = process_single_dataview(
                data_view_id="dv_test_12345",
                config_file=mock_config_file,
                output_dir=temp_output_dir,
                output_format="markdown",
                skip_validation=True,
            )
        assert result.success is True
        mock_md.assert_called_once()
