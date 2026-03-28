"""Edge-case tests for api/fetch.py.

Covers: failure return type consistency (DataFrame vs dict),
task count alignment, error context propagation.
"""

import logging
from concurrent.futures import Future
from unittest.mock import MagicMock, patch

import pandas as pd

from cja_auto_sdr.api.fetch import API_FETCH_TASK_COUNT, ParallelAPIFetcher
from cja_auto_sdr.core.perf import PerformanceTracker


def _make_fetcher(**kwargs):
    """Create a ParallelAPIFetcher with mocked CJA client."""
    cja = MagicMock()
    logger = logging.getLogger("test_fetch")
    perf = PerformanceTracker(logger=logger)
    defaults = {"cja": cja, "logger": logger, "perf_tracker": perf, "quiet": True}
    defaults.update(kwargs)
    return ParallelAPIFetcher(**defaults), cja


# ==================== Task Count ====================


class TestTaskCount:
    """Verify API_FETCH_TASK_COUNT matches actual task definitions."""

    def test_task_count_matches_fetch_tasks(self):
        """API_FETCH_TASK_COUNT should match the 3 tasks: metrics, dimensions, dataview info."""
        assert API_FETCH_TASK_COUNT == 3

    def test_fetch_all_submits_expected_number_of_tasks(self):
        """fetch_all_data should submit exactly API_FETCH_TASK_COUNT tasks."""
        fetcher, cja = _make_fetcher()
        cja.getMetrics.return_value = pd.DataFrame()
        cja.getDimensions.return_value = pd.DataFrame()
        cja.getDataView.return_value = {"id": "dv_test", "name": "Test"}

        submitted_futures: list[Future] = []

        class FakeExecutor:
            def __init__(self, max_workers):
                self.max_workers = max_workers

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def submit(self, fn):
                future = Future()
                future.set_result(fn())
                submitted_futures.append(future)
                return future

        with patch("cja_auto_sdr.api.fetch.ThreadPoolExecutor", FakeExecutor), patch(
            "cja_auto_sdr.api.fetch.as_completed",
            side_effect=list,
        ):
            fetcher.fetch_all_data("dv_test")

        assert len(submitted_futures) == API_FETCH_TASK_COUNT


# ==================== Failure Return Types ====================


class TestFailureReturnTypes:
    """Document the asymmetry: metrics/dimensions return DataFrame, dataview returns dict."""

    def test_metrics_failure_returns_empty_dataframe(self):
        fetcher, cja = _make_fetcher()
        cja.getMetrics.side_effect = RuntimeError("API error")
        cja.getDimensions.return_value = pd.DataFrame()
        cja.getDataView.return_value = {"id": "dv_test", "name": "Test"}

        metrics, _dimensions, _dataview = fetcher.fetch_all_data("dv_test")
        assert isinstance(metrics, pd.DataFrame)
        assert metrics.empty

    def test_dimensions_failure_returns_empty_dataframe(self):
        fetcher, cja = _make_fetcher()
        cja.getMetrics.return_value = pd.DataFrame()
        cja.getDimensions.side_effect = RuntimeError("API error")
        cja.getDataView.return_value = {"id": "dv_test", "name": "Test"}

        _metrics, dimensions, _dataview = fetcher.fetch_all_data("dv_test")
        assert isinstance(dimensions, pd.DataFrame)
        assert dimensions.empty

    def test_dataview_failure_returns_dict(self):
        fetcher, cja = _make_fetcher()
        cja.getMetrics.return_value = pd.DataFrame()
        cja.getDimensions.return_value = pd.DataFrame()
        cja.getDataView.side_effect = RuntimeError("API error")

        _metrics, _dimensions, dataview = fetcher.fetch_all_data("dv_test")
        assert isinstance(dataview, dict)
        # Failure payload includes lookup_failed flag
        assert dataview.get("lookup_failed") is True

    def test_all_failures_return_safe_defaults(self):
        fetcher, cja = _make_fetcher()
        cja.getMetrics.side_effect = RuntimeError("fail")
        cja.getDimensions.side_effect = RuntimeError("fail")
        cja.getDataView.side_effect = RuntimeError("fail")

        metrics, dimensions, dataview_result = fetcher.fetch_all_data("dv_test")
        assert isinstance(metrics, pd.DataFrame) and metrics.empty
        assert isinstance(dimensions, pd.DataFrame) and dimensions.empty
        assert isinstance(dataview_result, dict)


# ==================== Error Context Propagation ====================


class TestErrorContextPropagation:
    """Verify per-task errors are captured with context."""

    def test_failed_task_does_not_prevent_others(self):
        fetcher, cja = _make_fetcher()
        # Only metrics fails
        cja.getMetrics.side_effect = RuntimeError("metrics fail")
        cja.getDimensions.return_value = pd.DataFrame({"id": ["d1"], "name": ["Dim"]})
        cja.getDataView.return_value = {"id": "dv_test", "name": "Test"}

        _metrics, _dimensions, _dataview = fetcher.fetch_all_data("dv_test")

        # Metrics failed but others succeeded
        statuses = fetcher.get_fetch_statuses()
        assert statuses["metrics"].status == "failed"
        # Dimensions should have succeeded or returned empty
        assert statuses["dimensions"].status in ("success", "empty")
        assert statuses["dataview"].status in ("success", "failed")

    def test_error_status_has_context(self):
        fetcher, cja = _make_fetcher()
        cja.getMetrics.side_effect = RuntimeError("specific error message")
        cja.getDimensions.return_value = pd.DataFrame()
        cja.getDataView.return_value = {"id": "dv_test", "name": "Test"}

        fetcher.fetch_all_data("dv_test")
        statuses = fetcher.get_fetch_statuses()
        assert statuses["metrics"].status == "failed"
        assert "specific error message" in statuses["metrics"].error_message

    def test_none_api_result_treated_as_empty(self):
        fetcher, cja = _make_fetcher()
        cja.getMetrics.return_value = None
        cja.getDimensions.return_value = None
        cja.getDataView.return_value = {"id": "dv_test", "name": "Test"}

        metrics, dimensions, _dataview = fetcher.fetch_all_data("dv_test")
        assert isinstance(metrics, pd.DataFrame) and metrics.empty
        assert isinstance(dimensions, pd.DataFrame) and dimensions.empty
