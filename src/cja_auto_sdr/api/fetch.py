"""Parallel API data fetching for CJA Auto SDR."""

import logging
import threading
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, replace
from typing import Any

import cjapy
import pandas as pd
from tqdm import tqdm

from cja_auto_sdr.api.resilience import CircuitBreaker, make_api_call_with_retry
from cja_auto_sdr.api.tuning import APIWorkerTuner
from cja_auto_sdr.core.config import APITuningConfig
from cja_auto_sdr.core.constants import TQDM_BAR_FORMAT
from cja_auto_sdr.core.discovery_payloads import assess_dataview_lookup_payload
from cja_auto_sdr.core.exceptions import CircuitBreakerOpen
from cja_auto_sdr.core.perf import PerformanceTracker

API_FETCH_TASK_COUNT = 3  # metrics + dimensions + dataview


@dataclass(frozen=True, slots=True)
class EndpointFetchStatus:
    """Outcome metadata for a single API endpoint fetch."""

    endpoint: str
    status: str
    reason: str = ""
    error_message: str = ""
    item_count: int | None = None


class ParallelAPIFetcher:
    """Fetch multiple API endpoints in parallel using threading.

    Supports optional API auto-tuning and circuit breaker protection.

    Args:
        cja: CJA API client
        logger: Logger instance
        perf_tracker: Performance tracker for timing metrics
        max_workers: Maximum parallel workers (default: 3)
        quiet: Suppress progress output (default: False)
        tuning_config: Optional API worker auto-tuning configuration
        circuit_breaker: Optional circuit breaker for failure protection
    """

    def __init__(
        self,
        cja: cjapy.CJA,
        logger: logging.Logger,
        perf_tracker: PerformanceTracker,
        max_workers: int = 3,
        quiet: bool = False,
        tuning_config: APITuningConfig | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ):
        self.cja = cja
        self.logger = logger
        self.perf_tracker = perf_tracker
        self.max_workers = max_workers
        self.quiet = quiet
        self.circuit_breaker = circuit_breaker
        self._fetch_status_lock = threading.Lock()
        self._last_fetch_statuses: dict[str, EndpointFetchStatus] = {}
        self._reset_fetch_statuses()

        # Initialize API tuner if config provided
        self.tuner: APIWorkerTuner | None = None
        if tuning_config is not None:
            # Each fetch cycle emits one timing per API task. Clamp the window so
            # auto-tuning can make at least one decision per data view run.
            effective_window = max(1, min(tuning_config.sample_window, API_FETCH_TASK_COUNT))
            effective_config = tuning_config
            if effective_window != tuning_config.sample_window:
                effective_config = replace(tuning_config, sample_window=effective_window)
                self.logger.debug(
                    "API tuner sample_window clamped from %s to %s for per-data-view fetch cycle",
                    tuning_config.sample_window,
                    effective_window,
                )

            self.tuner = APIWorkerTuner(config=effective_config, initial_workers=max_workers, logger=logger)
            # Use tuner's worker count as effective max
            self.max_workers = self.tuner.current_workers

    def _reset_fetch_statuses(self) -> None:
        with self._fetch_status_lock:
            self._last_fetch_statuses = {
                endpoint: EndpointFetchStatus(endpoint=endpoint, status="pending")
                for endpoint in ("metrics", "dimensions", "dataview")
            }

    def _record_fetch_status(
        self,
        endpoint: str,
        status: str,
        *,
        reason: str = "",
        error_message: str = "",
        item_count: int | None = None,
    ) -> None:
        with self._fetch_status_lock:
            self._last_fetch_statuses[endpoint] = EndpointFetchStatus(
                endpoint=endpoint,
                status=status,
                reason=reason,
                error_message=error_message,
                item_count=item_count,
            )

    def get_fetch_statuses(self) -> dict[str, EndpointFetchStatus]:
        """Return the most recent per-endpoint fetch outcomes."""
        with self._fetch_status_lock:
            return dict(self._last_fetch_statuses)

    def fetch_all_data(self, data_view_id: str) -> tuple[pd.DataFrame, pd.DataFrame, dict]:
        """
        Fetch metrics, dimensions, and data view info in parallel

        Returns:
            Tuple of (metrics_df, dimensions_df, dataview_info)
        """
        self.logger.info("Starting parallel data fetch operations...")
        self.perf_tracker.start("Parallel API Fetch")
        self._reset_fetch_statuses()

        results = {"metrics": None, "dimensions": None, "dataview": None}

        errors = {}

        # Define fetch tasks
        tasks = {
            "metrics": lambda: self._fetch_metrics(data_view_id),
            "dimensions": lambda: self._fetch_dimensions(data_view_id),
            "dataview": lambda: self._fetch_dataview_info(data_view_id),
        }

        # Execute tasks in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_name = {executor.submit(task): name for name, task in tasks.items()}

            # Collect results as they complete with progress indicator
            with tqdm(
                total=len(tasks),
                desc="Fetching API data",
                unit="item",
                bar_format=TQDM_BAR_FORMAT,
                leave=False,
                disable=self.quiet,
            ) as pbar:
                for future in as_completed(future_to_name):
                    task_name = future_to_name[future]
                    try:
                        results[task_name] = future.result()
                        task_status = self.get_fetch_statuses().get(task_name)
                        if task_status is not None and task_status.status == "failed":
                            detail = task_status.error_message or task_status.reason or "unknown failure"
                            errors[task_name] = detail
                            pbar.set_postfix_str(f"\u2717 {task_name}", refresh=True)
                            self.logger.error("\u2717 %s fetch failed: %s", task_name.capitalize(), detail)
                        elif task_status is not None and task_status.status == "empty":
                            pbar.set_postfix_str(f"\u2205 {task_name}", refresh=True)
                            self.logger.warning("\u2205 %s fetch returned no components", task_name.capitalize())
                        else:
                            pbar.set_postfix_str(f"\u2713 {task_name}", refresh=True)
                            self.logger.info("\u2713 %s fetch completed", task_name.capitalize())
                    except Exception as e:  # Intentional: per-task boundary for heterogeneous worker failures
                        errors[task_name] = str(e)
                        self._record_fetch_status(
                            task_name,
                            "failed",
                            reason="future_exception",
                            error_message=str(e),
                        )
                        pbar.set_postfix_str(f"\u2717 {task_name}", refresh=True)
                        self.logger.error("\u2717 %s fetch failed: %s", task_name.capitalize(), e)
                    pbar.update(1)

        self.perf_tracker.end("Parallel API Fetch")

        # Log summary
        success_count = sum(1 for status in self.get_fetch_statuses().values() if status.status == "success")
        self.logger.info("Parallel fetch complete: %s/3 successful", success_count)

        if errors:
            self.logger.warning("Errors encountered: %s", list(errors.keys()))

        # Return results with proper None checking for DataFrames
        metrics_result = results.get("metrics")
        dimensions_result = results.get("dimensions")
        dataview_result = results.get("dataview")

        # Handle DataFrame None checks properly
        if metrics_result is None or (isinstance(metrics_result, pd.DataFrame) and metrics_result.empty):
            metrics_result = pd.DataFrame()

        if dimensions_result is None or (isinstance(dimensions_result, pd.DataFrame) and dimensions_result.empty):
            dimensions_result = pd.DataFrame()

        if dataview_result is None:
            dataview_result = {}

        return metrics_result, dimensions_result, dataview_result

    def _timed_api_call(self, api_func: Callable, *args, operation_name: str, **kwargs) -> Any:
        """
        Execute an API call with timing for auto-tuning.

        Wraps make_api_call_with_retry with timing measurement and tuner feedback.
        Only records timing on successful calls so retries don't inflate metrics.
        """
        start_time = time.perf_counter()
        result = make_api_call_with_retry(
            api_func,
            *args,
            logger=self.logger,
            operation_name=operation_name,
            circuit_breaker=self.circuit_breaker,
            **kwargs,
        )
        # Record response time only on success to avoid retry delays inflating metrics
        if self.tuner is not None:
            duration_ms = (time.perf_counter() - start_time) * 1000
            new_workers = self.tuner.record_response_time(duration_ms)
            if new_workers is not None:
                self.max_workers = new_workers
        return result

    def _fetch_metrics(self, data_view_id: str) -> pd.DataFrame:
        """Fetch metrics with error handling and retry"""
        try:
            self.logger.debug("Fetching metrics for %s", data_view_id)

            # Use retry for transient network errors with circuit breaker support
            metrics = self._timed_api_call(
                self.cja.getMetrics,
                data_view_id,
                inclType=True,
                full=True,
                operation_name="getMetrics",
            )

            if metrics is None or (isinstance(metrics, pd.DataFrame) and metrics.empty):
                self.logger.warning("No metrics returned from API")
                self._record_fetch_status("metrics", "empty", reason="empty_response", item_count=0)
                return pd.DataFrame()

            self.logger.info("Successfully fetched %s metrics", len(metrics))
            self._record_fetch_status("metrics", "success", item_count=len(metrics))
            return metrics

        except CircuitBreakerOpen as e:
            self.logger.warning("Circuit breaker open for metrics fetch: %s", e.message)
            self._record_fetch_status(
                "metrics",
                "failed",
                reason="circuit_breaker_open",
                error_message=e.message,
            )
            return pd.DataFrame()
        except AttributeError as e:
            self.logger.error("API method error - getMetrics may not be available: %s", e)
            self._record_fetch_status(
                "metrics",
                "failed",
                reason="attribute_error",
                error_message=str(e),
            )
            return pd.DataFrame()
        except Exception as e:  # Intentional: preserve resilient fallback-to-empty contract for metrics fetch
            self.logger.error("Failed to fetch metrics: %s", e)
            self._record_fetch_status("metrics", "failed", reason="exception", error_message=str(e))
            return pd.DataFrame()

    def _fetch_dimensions(self, data_view_id: str) -> pd.DataFrame:
        """Fetch dimensions with error handling and retry"""
        try:
            self.logger.debug("Fetching dimensions for %s", data_view_id)

            # Use retry for transient network errors with circuit breaker support
            dimensions = self._timed_api_call(
                self.cja.getDimensions,
                data_view_id,
                inclType=True,
                full=True,
                operation_name="getDimensions",
            )

            if dimensions is None or (isinstance(dimensions, pd.DataFrame) and dimensions.empty):
                self.logger.warning("No dimensions returned from API")
                self._record_fetch_status("dimensions", "empty", reason="empty_response", item_count=0)
                return pd.DataFrame()

            self.logger.info("Successfully fetched %s dimensions", len(dimensions))
            self._record_fetch_status("dimensions", "success", item_count=len(dimensions))
            return dimensions

        except CircuitBreakerOpen as e:
            self.logger.warning("Circuit breaker open for dimensions fetch: %s", e.message)
            self._record_fetch_status(
                "dimensions",
                "failed",
                reason="circuit_breaker_open",
                error_message=e.message,
            )
            return pd.DataFrame()
        except AttributeError as e:
            self.logger.error("API method error - getDimensions may not be available: %s", e)
            self._record_fetch_status(
                "dimensions",
                "failed",
                reason="attribute_error",
                error_message=str(e),
            )
            return pd.DataFrame()
        except Exception as e:  # Intentional: preserve resilient fallback-to-empty contract for dimensions fetch
            self.logger.error("Failed to fetch dimensions: %s", e)
            self._record_fetch_status("dimensions", "failed", reason="exception", error_message=str(e))
            return pd.DataFrame()

    def _fetch_dataview_info(self, data_view_id: str) -> dict:
        """Fetch data view information with error handling and retry"""
        try:
            self.logger.debug("Fetching data view information for %s", data_view_id)

            # Use retry for transient network errors with circuit breaker support
            lookup_data = self._timed_api_call(self.cja.getDataView, data_view_id, operation_name="getDataView")

            assessment = assess_dataview_lookup_payload(lookup_data, expected_data_view_id=data_view_id)
            if not assessment.is_valid:
                self.logger.error("Data view information returned invalid payload (%s)", assessment.reason)
                self._record_fetch_status(
                    "dataview",
                    "failed",
                    reason=assessment.reason,
                    error_message="invalid data view lookup payload",
                )
                detail = "invalid data view lookup payload"
                if isinstance(lookup_data, dict):
                    error_text = lookup_data.get("error") or lookup_data.get("message")
                    if error_text is not None:
                        detail = str(error_text)
                return self._build_lookup_failure_payload(
                    data_view_id,
                    reason=assessment.reason,
                    error_message=detail,
                )

            validated_payload = assessment.payload or {}
            self.logger.info("Successfully fetched data view info: %s", validated_payload.get("name", "Unknown"))
            self._record_fetch_status("dataview", "success")
            return validated_payload

        except CircuitBreakerOpen as e:
            self.logger.warning("Circuit breaker open for data view fetch: %s", e.message)
            self._record_fetch_status(
                "dataview",
                "failed",
                reason="circuit_breaker_open",
                error_message=e.message,
            )
            return self._build_lookup_failure_payload(
                data_view_id,
                reason="circuit_breaker_open",
                error_message=e.message,
                circuit_breaker_open=True,
            )
        except Exception as e:  # Intentional: preserve resilient lookup-failure payload contract
            self.logger.error("Failed to fetch data view information: %s", e)
            self._record_fetch_status("dataview", "failed", reason="exception", error_message=str(e))
            return self._build_lookup_failure_payload(
                data_view_id,
                reason="exception",
                error_message=str(e),
            )

    @staticmethod
    def _build_lookup_failure_payload(
        data_view_id: str,
        *,
        reason: str,
        error_message: str | None = None,
        circuit_breaker_open: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": "Unknown",
            "id": data_view_id,
            "lookup_failed": True,
            "lookup_failure_reason": reason,
        }
        if error_message:
            payload["error"] = error_message
        if circuit_breaker_open:
            payload["circuit_breaker_open"] = True
        return payload

    def get_tuner_statistics(self) -> dict[str, Any] | None:
        """Get API tuner statistics if tuning is enabled."""
        if self.tuner is not None:
            return self.tuner.get_statistics()
        return None
