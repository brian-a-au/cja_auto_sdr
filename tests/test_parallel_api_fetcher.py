"""Tests for ParallelAPIFetcher class"""

import logging
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import pytest

from cja_auto_sdr.core.config import APITuningConfig
from cja_auto_sdr.core.exceptions import CircuitBreakerOpen
from cja_auto_sdr.generator import ParallelAPIFetcher, PerformanceTracker


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
def mock_perf_tracker(mock_logger):
    """Create a mock performance tracker"""
    tracker = Mock(spec=PerformanceTracker)
    tracker.start = Mock()
    tracker.end = Mock()
    return tracker


@pytest.fixture
def mock_cja():
    """Create a mock CJA instance"""
    return Mock()


@pytest.fixture
def sample_metrics_data():
    """Sample metrics data"""
    return pd.DataFrame(
        [
            {"id": "metric1", "name": "Metric 1", "type": "calculated", "description": "Test"},
            {"id": "metric2", "name": "Metric 2", "type": "standard", "description": "Test 2"},
        ],
    )


@pytest.fixture
def sample_dimensions_data():
    """Sample dimensions data"""
    return pd.DataFrame(
        [
            {"id": "dim1", "name": "Dimension 1", "type": "string", "description": "Test"},
            {"id": "dim2", "name": "Dimension 2", "type": "string", "description": "Test 2"},
        ],
    )


@pytest.fixture
def sample_dataview_info():
    """Sample data view info"""
    return {"id": "dv_test_12345", "name": "Test Data View", "owner": {"name": "Test Owner"}}


class TestParallelAPIFetcherInit:
    """Tests for ParallelAPIFetcher initialization"""

    def test_init_with_defaults(self, mock_cja, mock_logger, mock_perf_tracker):
        """Test initialization with default parameters"""
        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)

        assert fetcher.cja == mock_cja
        assert fetcher.logger == mock_logger
        assert fetcher.perf_tracker == mock_perf_tracker
        assert fetcher.max_workers == 3

    def test_init_with_custom_workers(self, mock_cja, mock_logger, mock_perf_tracker):
        """Test initialization with custom worker count"""
        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker, max_workers=5)

        assert fetcher.max_workers == 5

    def test_init_with_minimum_workers(self, mock_cja, mock_logger, mock_perf_tracker):
        """Test initialization with minimum worker count"""
        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker, max_workers=1)

        assert fetcher.max_workers == 1

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    @patch("cja_auto_sdr.api.fetch.tqdm")
    def test_auto_tune_adjusts_with_default_window_per_fetch_cycle(
        self,
        mock_tqdm,
        mock_api_call,
        mock_cja,
        mock_logger,
        mock_perf_tracker,
        sample_metrics_data,
        sample_dimensions_data,
        sample_dataview_info,
    ):
        """Auto-tuning should be able to adjust within a single 3-call fetch cycle."""
        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        def api_side_effect(func, *args, **kwargs):
            op_name = kwargs.get("operation_name", "")
            if "getMetrics" in op_name:
                return sample_metrics_data
            if "getDimensions" in op_name:
                return sample_dimensions_data
            if "getDataView" in op_name:
                return sample_dataview_info
            return None

        mock_api_call.side_effect = api_side_effect

        tuning_config = APITuningConfig(
            min_workers=1,
            max_workers=2,
            scale_up_threshold_ms=1_000_000.0,
            sample_window=5,  # larger than one fetch cycle (3 calls)
            cooldown_seconds=0.0,
        )
        fetcher = ParallelAPIFetcher(
            mock_cja,
            mock_logger,
            mock_perf_tracker,
            max_workers=1,
            tuning_config=tuning_config,
            quiet=True,
        )

        fetcher.fetch_all_data("dv_test_12345")
        stats = fetcher.get_tuner_statistics()

        assert stats is not None
        assert stats["scale_ups"] >= 1
        assert fetcher.max_workers == 2


class TestParallelAPIFetcherFetchAllData:
    """Tests for fetch_all_data method"""

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    @patch("cja_auto_sdr.api.fetch.tqdm")
    def test_fetch_all_data_success(
        self,
        mock_tqdm,
        mock_api_call,
        mock_cja,
        mock_logger,
        mock_perf_tracker,
        sample_metrics_data,
        sample_dimensions_data,
        sample_dataview_info,
    ):
        """Test successful parallel data fetching"""
        # Setup mock tqdm context manager
        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        # Setup API responses
        def api_side_effect(func, *args, **kwargs):
            if "getMetrics" in kwargs.get("operation_name", ""):
                return sample_metrics_data
            if "getDimensions" in kwargs.get("operation_name", ""):
                return sample_dimensions_data
            if "getDataView" in kwargs.get("operation_name", ""):
                return sample_dataview_info
            return None

        mock_api_call.side_effect = api_side_effect

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        metrics, dimensions, dataview = fetcher.fetch_all_data("dv_test_12345")

        # Verify results
        assert not metrics.empty
        assert not dimensions.empty
        assert dataview == sample_dataview_info

        # Verify performance tracking
        mock_perf_tracker.start.assert_called_once_with("Parallel API Fetch")
        mock_perf_tracker.end.assert_called_once_with("Parallel API Fetch")

        statuses = fetcher.get_fetch_statuses()
        assert statuses["metrics"].status == "success"
        assert statuses["dimensions"].status == "success"
        assert statuses["dataview"].status == "success"

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    @patch("cja_auto_sdr.api.fetch.tqdm")
    def test_fetch_all_data_empty_metrics(
        self,
        mock_tqdm,
        mock_api_call,
        mock_cja,
        mock_logger,
        mock_perf_tracker,
        sample_dimensions_data,
        sample_dataview_info,
    ):
        """Test handling of empty metrics response"""
        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        def api_side_effect(func, *args, **kwargs):
            if "getMetrics" in kwargs.get("operation_name", ""):
                return None
            if "getDimensions" in kwargs.get("operation_name", ""):
                return sample_dimensions_data
            if "getDataView" in kwargs.get("operation_name", ""):
                return sample_dataview_info
            return None

        mock_api_call.side_effect = api_side_effect

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        metrics, dimensions, dataview = fetcher.fetch_all_data("dv_test_12345")

        assert metrics.empty
        assert not dimensions.empty
        assert dataview == sample_dataview_info
        assert fetcher.get_fetch_statuses()["metrics"].status == "empty"

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    @patch("cja_auto_sdr.api.fetch.tqdm")
    def test_fetch_all_data_records_failed_endpoint_status(
        self,
        mock_tqdm,
        mock_api_call,
        mock_cja,
        mock_logger,
        mock_perf_tracker,
        sample_dimensions_data,
        sample_dataview_info,
    ):
        """Endpoint failures should be tracked separately from empty responses."""
        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        def api_side_effect(func, *args, **kwargs):
            if "getMetrics" in kwargs.get("operation_name", ""):
                raise RuntimeError("metrics transport down")
            if "getDimensions" in kwargs.get("operation_name", ""):
                return sample_dimensions_data
            if "getDataView" in kwargs.get("operation_name", ""):
                return sample_dataview_info
            return None

        mock_api_call.side_effect = api_side_effect

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        metrics, dimensions, dataview = fetcher.fetch_all_data("dv_test_12345")

        assert metrics.empty
        assert not dimensions.empty
        assert dataview == sample_dataview_info
        statuses = fetcher.get_fetch_statuses()
        assert statuses["metrics"].status == "failed"
        assert "metrics transport down" in statuses["metrics"].error_message
        assert statuses["dimensions"].status == "success"

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    @patch("cja_auto_sdr.api.fetch.tqdm")
    def test_fetch_all_data_empty_dimensions(
        self,
        mock_tqdm,
        mock_api_call,
        mock_cja,
        mock_logger,
        mock_perf_tracker,
        sample_metrics_data,
        sample_dataview_info,
    ):
        """Test handling of empty dimensions response"""
        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        def api_side_effect(func, *args, **kwargs):
            if "getMetrics" in kwargs.get("operation_name", ""):
                return sample_metrics_data
            if "getDimensions" in kwargs.get("operation_name", ""):
                return pd.DataFrame()
            if "getDataView" in kwargs.get("operation_name", ""):
                return sample_dataview_info
            return None

        mock_api_call.side_effect = api_side_effect

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        metrics, dimensions, dataview = fetcher.fetch_all_data("dv_test_12345")

        assert not metrics.empty
        assert dimensions.empty
        assert dataview == sample_dataview_info

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    @patch("cja_auto_sdr.api.fetch.tqdm")
    def test_fetch_all_data_empty_dataview(
        self,
        mock_tqdm,
        mock_api_call,
        mock_cja,
        mock_logger,
        mock_perf_tracker,
        sample_metrics_data,
        sample_dimensions_data,
    ):
        """Test handling of empty dataview response"""
        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        def api_side_effect(func, *args, **kwargs):
            if "getMetrics" in kwargs.get("operation_name", ""):
                return sample_metrics_data
            if "getDimensions" in kwargs.get("operation_name", ""):
                return sample_dimensions_data
            if "getDataView" in kwargs.get("operation_name", ""):
                return None
            return None

        mock_api_call.side_effect = api_side_effect

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        metrics, dimensions, dataview = fetcher.fetch_all_data("dv_test_12345")

        assert not metrics.empty
        assert not dimensions.empty
        # When dataview info fetch fails, it returns a fallback dict with Unknown name
        assert dataview["name"] == "Unknown"
        assert dataview["id"] == "dv_test_12345"
        assert dataview["lookup_failed"] is True
        assert dataview["lookup_failure_reason"] == "none_payload"


class TestParallelAPIFetcherFetchMetrics:
    """Tests for _fetch_metrics method"""

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_metrics_success(self, mock_api_call, mock_cja, mock_logger, mock_perf_tracker, sample_metrics_data):
        """Test successful metrics fetching"""
        mock_api_call.return_value = sample_metrics_data

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_metrics("dv_test_12345")

        assert not result.empty
        assert len(result) == 2
        mock_api_call.assert_called_once()

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_metrics_returns_none(self, mock_api_call, mock_cja, mock_logger, mock_perf_tracker):
        """Test handling of None response from API"""
        mock_api_call.return_value = None

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_metrics("dv_test_12345")

        assert result.empty
        mock_logger.warning.assert_called()

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_metrics_returns_empty_df(self, mock_api_call, mock_cja, mock_logger, mock_perf_tracker):
        """Test handling of empty DataFrame response"""
        mock_api_call.return_value = pd.DataFrame()

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_metrics("dv_test_12345")

        assert result.empty

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_metrics_attribute_error(self, mock_api_call, mock_cja, mock_logger, mock_perf_tracker):
        """Test handling of AttributeError (API method not available)"""
        mock_api_call.side_effect = AttributeError("getMetrics not available")

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_metrics("dv_test_12345")

        assert result.empty
        mock_logger.error.assert_called()

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_metrics_generic_exception(self, mock_api_call, mock_cja, mock_logger, mock_perf_tracker):
        """Test handling of generic exception"""
        mock_api_call.side_effect = Exception("Network error")

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_metrics("dv_test_12345")

        assert result.empty
        mock_logger.error.assert_called()


class TestParallelAPIFetcherFetchDimensions:
    """Tests for _fetch_dimensions method"""

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_dimensions_success(
        self,
        mock_api_call,
        mock_cja,
        mock_logger,
        mock_perf_tracker,
        sample_dimensions_data,
    ):
        """Test successful dimensions fetching"""
        mock_api_call.return_value = sample_dimensions_data

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_dimensions("dv_test_12345")

        assert not result.empty
        assert len(result) == 2

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_dimensions_returns_none(self, mock_api_call, mock_cja, mock_logger, mock_perf_tracker):
        """Test handling of None response"""
        mock_api_call.return_value = None

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_dimensions("dv_test_12345")

        assert result.empty

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_dimensions_attribute_error(self, mock_api_call, mock_cja, mock_logger, mock_perf_tracker):
        """Test handling of AttributeError"""
        mock_api_call.side_effect = AttributeError("getDimensions not available")

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_dimensions("dv_test_12345")

        assert result.empty
        mock_logger.error.assert_called()

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_dimensions_generic_exception(self, mock_api_call, mock_cja, mock_logger, mock_perf_tracker):
        """Test handling of generic exception"""
        mock_api_call.side_effect = Exception("API timeout")

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_dimensions("dv_test_12345")

        assert result.empty


class TestParallelAPIFetcherFetchDataviewInfo:
    """Tests for _fetch_dataview_info method"""

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_dataview_info_success(
        self,
        mock_api_call,
        mock_cja,
        mock_logger,
        mock_perf_tracker,
        sample_dataview_info,
    ):
        """Test successful dataview info fetching"""
        mock_api_call.return_value = sample_dataview_info

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_dataview_info("dv_test_12345")

        assert result == sample_dataview_info
        assert result["name"] == "Test Data View"

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_dataview_info_canonicalizes_mixed_case_identity_and_owner(
        self,
        mock_api_call,
        mock_cja,
        mock_logger,
        mock_perf_tracker,
    ):
        """Successful mixed-case payloads should expose canonical keys downstream."""
        mock_api_call.return_value = {
            "ID": "dv_test_12345",
            "Name": "Test Data View",
            "Owner": {"NAME": "Test Owner"},
        }

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_dataview_info("dv_test_12345")

        assert result["id"] == "dv_test_12345"
        assert result["name"] == "Test Data View"
        assert result["owner"]["name"] == "Test Owner"

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_dataview_info_returns_none(self, mock_api_call, mock_cja, mock_logger, mock_perf_tracker):
        """Test handling of None response"""
        mock_api_call.return_value = None

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_dataview_info("dv_test_12345")

        assert result["name"] == "Unknown"
        assert result["id"] == "dv_test_12345"
        assert result["lookup_failed"] is True
        assert result["lookup_failure_reason"] == "none_payload"
        mock_logger.error.assert_called()

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_dataview_info_returns_empty_dict(self, mock_api_call, mock_cja, mock_logger, mock_perf_tracker):
        """Test handling of empty dict response"""
        mock_api_call.return_value = {}

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_dataview_info("dv_test_12345")

        assert result["name"] == "Unknown"
        assert result["id"] == "dv_test_12345"
        assert result["lookup_failed"] is True
        assert result["lookup_failure_reason"] == "empty_mapping"

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_dataview_info_rejects_legacy_unknown_placeholder(
        self,
        mock_api_call,
        mock_cja,
        mock_logger,
        mock_perf_tracker,
    ):
        """Legacy fallback payload shape should be normalized into explicit failure payload."""
        mock_api_call.return_value = {"id": "dv_test_12345", "name": "Unknown"}

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_dataview_info("dv_test_12345")

        assert result["name"] == "Unknown"
        assert result["id"] == "dv_test_12345"
        assert result["lookup_failed"] is True
        assert result["lookup_failure_reason"] == "legacy_unknown_placeholder"

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_dataview_info_rejects_unknown_placeholder_with_error_diagnostic(
        self,
        mock_api_call,
        mock_cja,
        mock_logger,
        mock_perf_tracker,
    ):
        """Unknown placeholder with diagnostic keys should be normalized into failure payload."""
        mock_api_call.return_value = {"id": "dv_test_12345", "name": "Unknown", "error": "not found"}

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_dataview_info("dv_test_12345")

        assert result["name"] == "Unknown"
        assert result["id"] == "dv_test_12345"
        assert result["lookup_failed"] is True
        assert result["lookup_failure_reason"] == "unknown_placeholder_diagnostic:error"

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_dataview_info_rejects_id_plus_error_only_payload(
        self,
        mock_api_call,
        mock_cja,
        mock_logger,
        mock_perf_tracker,
    ):
        """Lookup payload with only id+error should fail closed."""
        mock_api_call.return_value = {"id": "dv_test_12345", "error": "not found"}

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_dataview_info("dv_test_12345")

        assert result["name"] == "Unknown"
        assert result["id"] == "dv_test_12345"
        assert result["lookup_failed"] is True
        assert result["lookup_failure_reason"] == "error_shape"

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_dataview_info_rejects_empty_owner_container_with_error(
        self,
        mock_api_call,
        mock_cja,
        mock_logger,
        mock_perf_tracker,
    ):
        """Lookup payload with empty owner container should fail closed."""
        mock_api_call.return_value = {"id": "dv_test_12345", "owner": {}, "error": "not found"}

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_dataview_info("dv_test_12345")

        assert result["name"] == "Unknown"
        assert result["id"] == "dv_test_12345"
        assert result["lookup_failed"] is True
        assert result["lookup_failure_reason"] == "error_shape"

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_dataview_info_prefers_non_empty_case_collided_owner_payload(
        self,
        mock_api_call,
        mock_cja,
        mock_logger,
        mock_perf_tracker,
    ):
        """Case-collided owner keys should keep richer values over empty placeholders."""
        mock_api_call.return_value = {
            "id": "dv_test_12345",
            "owner": {},
            "Owner": {"NAME": "Test Owner"},
            "error": "transient warning",
        }

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_dataview_info("dv_test_12345")

        assert result["id"] == "dv_test_12345"
        assert result["owner"]["name"] == "Test Owner"
        assert "lookup_failed" not in result

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_dataview_info_rejects_id_only_payload_as_insufficient_metadata(
        self,
        mock_api_call,
        mock_cja,
        mock_logger,
        mock_perf_tracker,
    ):
        """Lookup payload with only id should fail closed as insufficient metadata."""
        mock_api_call.return_value = {"id": "dv_test_12345"}

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_dataview_info("dv_test_12345")

        assert result["name"] == "Unknown"
        assert result["id"] == "dv_test_12345"
        assert result["lookup_failed"] is True
        assert result["lookup_failure_reason"] == "insufficient_metadata"

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_dataview_info_rejects_payload_missing_expected_id(
        self,
        mock_api_call,
        mock_cja,
        mock_logger,
        mock_perf_tracker,
    ):
        """Lookup payload with name/error but missing id should fail closed."""
        mock_api_call.return_value = {"name": "Some Name", "error": "not found"}

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_dataview_info("dv_test_12345")

        assert result["name"] == "Unknown"
        assert result["id"] == "dv_test_12345"
        assert result["lookup_failed"] is True
        assert result["lookup_failure_reason"] == "missing_expected_id"

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_dataview_info_circuit_breaker_open(
        self,
        mock_api_call,
        mock_cja,
        mock_logger,
        mock_perf_tracker,
    ):
        """Circuit breaker opens should return explicit failure payload."""
        mock_api_call.side_effect = CircuitBreakerOpen("breaker open", time_until_retry=10)

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_dataview_info("dv_test_12345")

        assert result["name"] == "Unknown"
        assert result["id"] == "dv_test_12345"
        assert result["lookup_failed"] is True
        assert result["lookup_failure_reason"] == "circuit_breaker_open"
        assert result["circuit_breaker_open"] is True
        assert "error" in result

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_dataview_info_exception(self, mock_api_call, mock_cja, mock_logger, mock_perf_tracker):
        """Test handling of exception"""
        mock_api_call.side_effect = Exception("API error")

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_dataview_info("dv_test_12345")

        assert result["name"] == "Unknown"
        assert result["id"] == "dv_test_12345"
        assert result["lookup_failed"] is True
        assert result["lookup_failure_reason"] == "exception"
        assert "error" in result


class TestParallelAPIFetcherErrorHandling:
    """Tests for error handling scenarios"""

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    @patch("cja_auto_sdr.api.fetch.tqdm")
    def test_partial_failure_continues(
        self,
        mock_tqdm,
        mock_api_call,
        mock_cja,
        mock_logger,
        mock_perf_tracker,
        sample_dimensions_data,
        sample_dataview_info,
    ):
        """Test that partial failures don't stop other fetches"""
        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        call_count = [0]

        def api_side_effect(func, *args, **kwargs):
            call_count[0] += 1
            op_name = kwargs.get("operation_name", "")
            if "getMetrics" in op_name:
                raise Exception("Metrics fetch failed")
            if "getDimensions" in op_name:
                return sample_dimensions_data
            if "getDataView" in op_name:
                return sample_dataview_info
            return None

        mock_api_call.side_effect = api_side_effect

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        metrics, dimensions, dataview = fetcher.fetch_all_data("dv_test_12345")

        # Metrics should be empty due to error, but others should succeed
        assert metrics.empty
        assert not dimensions.empty
        assert dataview == sample_dataview_info

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    @patch("cja_auto_sdr.api.fetch.tqdm")
    def test_all_failures_return_empty(self, mock_tqdm, mock_api_call, mock_cja, mock_logger, mock_perf_tracker):
        """Test that all failures return empty/default values"""
        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        mock_api_call.side_effect = Exception("All calls fail")

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        metrics, dimensions, dataview = fetcher.fetch_all_data("dv_test_12345")

        assert metrics.empty
        assert dimensions.empty
        # On failure, dataview returns fallback dict with error
        assert dataview["name"] == "Unknown"
        assert dataview["lookup_failed"] is True
        assert dataview["lookup_failure_reason"] == "exception"
        assert "error" in dataview


class TestParallelAPIFetcherLogging:
    """Tests for logging behavior"""

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    @patch("cja_auto_sdr.api.fetch.tqdm")
    def test_logs_start_message(self, mock_tqdm, mock_api_call, mock_cja, mock_logger, mock_perf_tracker):
        """Test that starting message is logged"""
        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)
        mock_api_call.return_value = pd.DataFrame()

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        fetcher.fetch_all_data("dv_test_12345")

        # Verify start message logged
        calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("parallel" in c.lower() for c in calls)

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    @patch("cja_auto_sdr.api.fetch.tqdm")
    def test_logs_completion_summary(
        self,
        mock_tqdm,
        mock_api_call,
        mock_cja,
        mock_logger,
        mock_perf_tracker,
        sample_metrics_data,
    ):
        """Test that completion summary is logged"""
        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)
        mock_api_call.return_value = sample_metrics_data

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        fetcher.fetch_all_data("dv_test_12345")

        # Verify completion logged
        calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("complete" in c.lower() for c in calls)


class TestCjapyErrorPayloadContract:
    """Component fetches must classify cjapy-style error dicts as failures, not success."""

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_metrics_rejects_statusCode_error_payload(
        self,
        mock_api_call,
        mock_cja,
        mock_logger,
        mock_perf_tracker,
    ):
        mock_api_call.return_value = {"statusCode": 500, "message": "backend timeout"}

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_metrics("dv_test_12345")

        assert isinstance(result, pd.DataFrame)
        assert result.empty
        status = fetcher.get_fetch_statuses()["metrics"]
        assert status.status == "failed"
        assert status.item_count is None
        detail = (status.error_message or "") + " " + (status.reason or "")
        assert "backend timeout" in detail or "error" in detail.lower()

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_dimensions_rejects_statusCode_error_payload(
        self,
        mock_api_call,
        mock_cja,
        mock_logger,
        mock_perf_tracker,
    ):
        mock_api_call.return_value = {"statusCode": 502, "message": "bad gateway"}

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_dimensions("dv_test_12345")

        assert isinstance(result, pd.DataFrame)
        assert result.empty
        status = fetcher.get_fetch_statuses()["dimensions"]
        assert status.status == "failed"
        assert status.item_count is None

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    def test_fetch_metrics_accepts_list_of_rows(
        self,
        mock_api_call,
        mock_cja,
        mock_logger,
        mock_perf_tracker,
    ):
        """cjapy may return a list of row dicts — we must normalize to DataFrame."""
        mock_api_call.return_value = [
            {"id": "m1", "name": "M1", "type": "standard", "description": "x"},
            {"id": "m2", "name": "M2", "type": "calculated", "description": "y"},
        ]

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        result = fetcher._fetch_metrics("dv_test_12345")

        assert isinstance(result, pd.DataFrame)
        assert len(result) == 2
        status = fetcher.get_fetch_statuses()["metrics"]
        assert status.status == "success"
        assert status.item_count == 2

    @patch("cja_auto_sdr.api.fetch.make_api_call_with_retry")
    @patch("cja_auto_sdr.api.fetch.tqdm")
    def test_fetch_all_data_reports_failed_metrics_for_error_payload(
        self,
        mock_tqdm,
        mock_api_call,
        mock_cja,
        mock_logger,
        mock_perf_tracker,
    ):
        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        def _side_effect(api_func, *args, **kwargs):
            operation = kwargs.get("operation_name", "")
            if operation == "getMetrics":
                return {"statusCode": 500, "message": "backend timeout"}
            if operation == "getDimensions":
                return pd.DataFrame([{"id": "x", "name": "x", "type": "string", "description": "x"}])
            return {"id": "dv_test_12345", "name": "T", "description": "d"}

        mock_api_call.side_effect = _side_effect

        fetcher = ParallelAPIFetcher(mock_cja, mock_logger, mock_perf_tracker)
        metrics, _dimensions, _dataview = fetcher.fetch_all_data("dv_test_12345")

        # After normalization: error dict must not surface as metrics; status is failed.
        assert isinstance(metrics, pd.DataFrame)
        assert metrics.empty
        assert fetcher.get_fetch_statuses()["metrics"].status == "failed"
