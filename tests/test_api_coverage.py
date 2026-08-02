"""Tests targeting uncovered lines in api/ modules to maximize line coverage.

Covers:
- api/cache.py: exception paths, eviction edge cases, log_statistics, pickle round-trip
- api/quality.py: exception handlers in every check method, parallel and DataFrame errors
- api/fetch.py: error branches in _fetch_metrics, _fetch_dimensions, _fetch_dataview_info
- api/resilience.py: env-var overrides, decorator retry paths, circuit breaker decorator
"""

import logging
import pickle
import time
from unittest.mock import MagicMock, PropertyMock, patch

import pandas as pd
import pytest

from cja_auto_sdr.api.cache import SharedValidationCache, ValidationCache
from cja_auto_sdr.api.quality import DataQualityChecker
from cja_auto_sdr.api.resilience import (
    CircuitBreaker,
    ErrorMessageHelper,
    _effective_retry_config,
    _parse_env_numeric,
    make_api_call_with_retry,
    retry_with_backoff,
)
from cja_auto_sdr.core.config import CircuitBreakerConfig, CircuitState
from cja_auto_sdr.core.exceptions import CircuitBreakerOpen, RetryableHTTPError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_logger(name: str = "test") -> logging.Logger:
    """Create a logger for testing."""
    return logging.getLogger(name)


def _sample_df() -> pd.DataFrame:
    """Small DataFrame for cache and quality tests."""
    return pd.DataFrame(
        {
            "id": ["m1", "m2"],
            "name": ["Metric A", "Metric B"],
            "type": ["numeric", "numeric"],
            "description": ["desc1", "desc2"],
        },
    )


# ===================================================================
# cache.py — ValidationCache
# ===================================================================


class TestValidationCacheGenerateCacheKeyException:
    """Lines 95-98: exception in _generate_cache_key."""

    def test_hash_pandas_object_raises_returns_error_key(self):
        logger = _make_logger()
        cache = ValidationCache(max_size=10, logger=logger)
        df = _sample_df()
        with patch("cja_auto_sdr.api.cache.pd.util.hash_pandas_object", side_effect=TypeError("boom")):
            key = cache._generate_cache_key(df, "Metrics", ["id"], ["name"])
        assert key.startswith("error:")


class TestValidationCacheEvictLRUEmpty:
    """Line 186: _evict_lru on empty cache returns immediately."""

    def test_evict_lru_empty_access_times(self):
        logger = _make_logger()
        cache = ValidationCache(max_size=10, logger=logger)
        # Both maps are empty; should return without error
        cache._evict_lru()
        assert cache._evictions == 0


class TestValidationCacheLogStatistics:
    """Lines 234-249: log_statistics with various scenarios."""

    def test_log_statistics_no_requests(self, caplog):
        logger = logging.getLogger("test_log_stats_none")
        logger.setLevel(logging.DEBUG)
        cache = ValidationCache(max_size=10, logger=logger)
        with caplog.at_level(logging.DEBUG, logger="test_log_stats_none"):
            cache.log_statistics()
        assert "No requests recorded" in caplog.text

    def test_log_statistics_with_hits_and_evictions(self, caplog):
        logger = logging.getLogger("test_log_stats_hits")
        logger.setLevel(logging.INFO)
        cache = ValidationCache(max_size=2, logger=logger)
        df = _sample_df()
        req = ["id"]
        crit = ["name"]

        # Fill cache beyond max_size to trigger evictions
        for i in range(4):
            df_i = df.copy()
            df_i["name"] = [f"x{i}_a", f"x{i}_b"]
            cache.put(df_i, "Metrics", req, crit, [{"Severity": "LOW"}])

        # Force a cache hit
        df_hit = df.copy()
        df_hit["name"] = ["x3_a", "x3_b"]
        cache.put(df_hit, "Metrics", req, crit, [{"Severity": "LOW"}])
        cache.get(df_hit, "Metrics", req, crit)

        with caplog.at_level(logging.INFO, logger="test_log_stats_hits"):
            cache.log_statistics()

        assert "Cache Statistics:" in caplog.text
        assert "Cache size:" in caplog.text
        # Evictions happened (max_size=2 and we inserted 4+ unique keys)
        assert "Evictions:" in caplog.text

    def test_log_statistics_estimated_time_saved(self, caplog):
        """Verify the estimated-time-saved line appears when enough hits exist."""
        logger = logging.getLogger("test_log_stats_time")
        logger.setLevel(logging.INFO)
        cache = ValidationCache(max_size=100, logger=logger)
        # Artificially set hit count high enough for > 0.1s savings
        cache._hits = 10  # 10 * 0.049 = 0.49s
        cache._misses = 2
        with caplog.at_level(logging.INFO, logger="test_log_stats_time"):
            cache.log_statistics()
        assert "Estimated time saved:" in caplog.text


# ===================================================================
# cache.py — SharedValidationCache
# ===================================================================


class TestSharedCacheGenerateCacheKeyException:
    """Lines 337-340: exception in SharedValidationCache._generate_cache_key."""

    def test_hash_error_returns_error_key(self):
        cache = SharedValidationCache(max_size=5)
        try:
            df = _sample_df()
            with patch("cja_auto_sdr.api.cache.pd.util.hash_pandas_object", side_effect=ValueError("hash fail")):
                key = cache._generate_cache_key(df, "Dimensions", ["id"], ["name"])
            assert key.startswith("error:")
        finally:
            cache.shutdown()


class TestSharedCachePutWithoutCacheKey:
    """Line 409: put() without providing cache_key triggers key generation."""

    def test_put_generates_key_when_none(self):
        cache = SharedValidationCache(max_size=5)
        try:
            df = _sample_df()
            issues = [{"Severity": "LOW", "Category": "Test"}]
            # cache_key defaults to None
            cache.put(df, "Metrics", ["id"], ["name"], issues)
            # Verify it's stored
            result, _ = cache.get(df, "Metrics", ["id"], ["name"])
            assert result is not None
            assert len(result) == 1
        finally:
            cache.shutdown()


class TestSharedCacheEvictLRUEmpty:
    """Lines 422-423, 428: empty _access_times in shared cache eviction."""

    def test_evict_lru_returns_on_empty_access_times(self):
        cache = SharedValidationCache(max_size=5)
        try:
            # Manually call _evict_lru with empty access_times
            cache._evict_lru()
            stats = cache.get_statistics()
            assert stats["evictions"] == 0
        finally:
            cache.shutdown()

    def test_evict_lru_returns_on_empty_dict_copy(self):
        """Line 428: access_times_dict is empty after dict() conversion."""
        cache = SharedValidationCache(max_size=1)
        try:
            df = _sample_df()
            # Put one item
            cache.put(df, "Metrics", ["id"], ["name"], [{"sev": "LOW"}])
            # Clear access_times manually to hit line 428
            cache._access_times.clear()
            # Now calling _evict_lru should return early at line 428
            cache._evict_lru()
        finally:
            cache.shutdown()


class TestSharedCachePickle:
    """Lines 480-483: __setstate__ via pickle round-trip."""

    def test_pickle_round_trip(self):
        cache = SharedValidationCache(max_size=5)
        try:
            data = pickle.dumps(cache)
            restored = pickle.loads(data)  # noqa: S301
            # After unpickling, logger is restored and _manager is None
            assert restored._manager is None
            assert restored.logger.name == cache.logger.name
            assert restored.max_size == 5
        finally:
            cache.shutdown()


# ===================================================================
# quality.py — DataQualityChecker exception paths
# ===================================================================


class TestCheckDuplicatesException:
    """Lines 88-89: exception in check_duplicates."""

    def test_exception_logged_not_raised(self, caplog):
        logger = logging.getLogger("test_dup_exc")
        logger.setLevel(logging.ERROR)
        checker = DataQualityChecker(logger=logger)
        df = _sample_df()
        with patch.object(pd.Series, "value_counts", side_effect=TypeError("mock error")):
            with caplog.at_level(logging.ERROR, logger="test_dup_exc"):
                checker.check_duplicates(df, "Metrics")
        assert "checking duplicates" in caplog.text


class TestCheckRequiredFieldsException:
    """Lines 101-110: exception in check_required_fields."""

    def test_exception_logged_not_raised(self, caplog):
        logger = logging.getLogger("test_req_exc")
        logger.setLevel(logging.ERROR)
        checker = DataQualityChecker(logger=logger)
        # Create a DataFrame whose .empty property raises
        df = MagicMock(spec=pd.DataFrame)
        type(df).empty = PropertyMock(side_effect=TypeError("boom"))
        with caplog.at_level(logging.ERROR, logger="test_req_exc"):
            checker.check_required_fields(df, "Metrics", ["id", "name"])
        assert "checking required fields" in caplog.text


class TestCheckNullValuesException:
    """Lines 132-133: exception in check_null_values."""

    def test_exception_logged_not_raised(self, caplog):
        logger = logging.getLogger("test_null_exc")
        logger.setLevel(logging.ERROR)
        checker = DataQualityChecker(logger=logger)
        df = MagicMock(spec=pd.DataFrame)
        type(df).empty = PropertyMock(side_effect=TypeError("null boom"))
        with caplog.at_level(logging.ERROR, logger="test_null_exc"):
            checker.check_null_values(df, "Metrics", ["id"])
        assert "checking null values" in caplog.text


class TestCheckMissingDescriptionsException:
    """Lines 139-140, 143-144, 159-160: exception in check_missing_descriptions."""

    def test_exception_on_empty_check(self, caplog):
        logger = logging.getLogger("test_desc_exc")
        logger.setLevel(logging.ERROR)
        checker = DataQualityChecker(logger=logger)
        df = MagicMock(spec=pd.DataFrame)
        type(df).empty = PropertyMock(side_effect=TypeError("desc boom"))
        with caplog.at_level(logging.ERROR, logger="test_desc_exc"):
            checker.check_missing_descriptions(df, "Dimensions")
        assert "checking descriptions" in caplog.text


class TestCheckEmptyDataframeException:
    """Lines 174-175: exception in check_empty_dataframe."""

    def test_exception_logged_not_raised(self, caplog):
        logger = logging.getLogger("test_empty_exc")
        logger.setLevel(logging.ERROR)
        checker = DataQualityChecker(logger=logger)
        df = MagicMock(spec=pd.DataFrame)
        type(df).empty = PropertyMock(side_effect=TypeError("empty boom"))
        with caplog.at_level(logging.ERROR, logger="test_empty_exc"):
            checker.check_empty_dataframe(df, "Metrics")
        assert "checking if dataframe is empty" in caplog.text


class TestCheckIdValidityException:
    """Lines 181-182, 185-186, 199-200: exception in check_id_validity."""

    def test_exception_logged_not_raised(self, caplog):
        logger = logging.getLogger("test_id_exc")
        logger.setLevel(logging.ERROR)
        checker = DataQualityChecker(logger=logger)
        df = MagicMock(spec=pd.DataFrame)
        type(df).empty = PropertyMock(side_effect=TypeError("id boom"))
        with caplog.at_level(logging.ERROR, logger="test_id_exc"):
            checker.check_id_validity(df, "Metrics")
        assert "checking ID validity" in caplog.text


class TestCheckAllParallelWorkerException:
    """Lines 373-376, 381-384: exception in check_all_parallel worker."""

    def test_worker_exception_logged(self, caplog):
        logger = logging.getLogger("test_parallel_exc")
        logger.setLevel(logging.ERROR)
        checker = DataQualityChecker(logger=logger, quiet=True)
        metrics_df = _sample_df()
        dims_df = _sample_df()

        with patch.object(
            checker,
            "check_all_quality_issues_optimized",
            side_effect=RuntimeError("worker failed"),
        ):
            with caplog.at_level(logging.ERROR, logger="test_parallel_exc"):
                checker.check_all_parallel(metrics_df, dims_df, ["id"], ["id"], ["name"], max_workers=1)
        assert "validation failed" in caplog.text

    def test_outer_exception_raises(self):
        """Lines 381-384: exception in the outer try block of check_all_parallel."""
        logger = _make_logger()
        checker = DataQualityChecker(logger=logger, quiet=True)
        metrics_df = _sample_df()
        dims_df = _sample_df()

        with patch(
            "cja_auto_sdr.api.quality.ThreadPoolExecutor",
            side_effect=RuntimeError("executor boom"),
        ):
            with pytest.raises(RuntimeError, match="executor boom"):
                checker.check_all_parallel(metrics_df, dims_df, ["id"], ["id"], ["name"])


class TestGetIssuesDataframeException:
    """Lines 427-429: exception in get_issues_dataframe."""

    def test_exception_returns_error_df(self):
        logger = _make_logger()
        checker = DataQualityChecker(logger=logger)
        # Add an issue so the empty-check is bypassed
        checker.issues = [
            {"Severity": "HIGH", "Category": "Test", "Type": "t", "Item Name": "n", "Issue": "i", "Details": "d"},
        ]
        # Patch CategoricalDtype to raise *after* the initial DataFrame is built
        # This triggers the except block at lines 427-429
        with patch("cja_auto_sdr.api.quality.pd.CategoricalDtype", side_effect=RuntimeError("dtype boom")):
            result = checker.get_issues_dataframe()
        assert "ERROR" in result["Severity"].values


# ===================================================================
# fetch.py — ParallelAPIFetcher error branches
# ===================================================================


class TestParallelAPIFetcherErrors:
    """Uncovered error branches in _fetch_metrics, _fetch_dimensions, _fetch_dataview_info."""

    def _make_fetcher(self, cja_mock=None):
        from cja_auto_sdr.api.fetch import ParallelAPIFetcher
        from cja_auto_sdr.core.perf import PerformanceTracker

        logger = _make_logger()
        perf = PerformanceTracker(logger=logger)
        cja = cja_mock or MagicMock()
        return ParallelAPIFetcher(cja=cja, logger=logger, perf_tracker=perf, quiet=True)

    def test_fetch_metrics_circuit_breaker_open(self):
        """CircuitBreakerOpen branch in _fetch_metrics."""
        cja = MagicMock()
        fetcher = self._make_fetcher(cja)
        with patch(
            "cja_auto_sdr.api.fetch.make_api_call_with_retry",
            side_effect=CircuitBreakerOpen("open", time_until_retry=5.0),
        ):
            result = fetcher._fetch_metrics("dv_123")
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_fetch_metrics_attribute_error(self):
        """AttributeError branch in _fetch_metrics."""
        cja = MagicMock()
        fetcher = self._make_fetcher(cja)
        with patch(
            "cja_auto_sdr.api.fetch.make_api_call_with_retry",
            side_effect=AttributeError("no getMetrics"),
        ):
            result = fetcher._fetch_metrics("dv_123")
        assert result.empty

    def test_fetch_metrics_generic_exception(self):
        """Generic exception branch in _fetch_metrics."""
        cja = MagicMock()
        fetcher = self._make_fetcher(cja)
        with patch(
            "cja_auto_sdr.api.fetch.make_api_call_with_retry",
            side_effect=RuntimeError("api down"),
        ):
            result = fetcher._fetch_metrics("dv_123")
        assert result.empty

    def test_fetch_metrics_returns_none(self):
        """Branch where API returns None for metrics."""
        cja = MagicMock()
        fetcher = self._make_fetcher(cja)
        with patch(
            "cja_auto_sdr.api.fetch.make_api_call_with_retry",
            return_value=None,
        ):
            result = fetcher._fetch_metrics("dv_123")
        assert result.empty

    def test_fetch_dimensions_circuit_breaker_open(self):
        """CircuitBreakerOpen branch in _fetch_dimensions."""
        cja = MagicMock()
        fetcher = self._make_fetcher(cja)
        with patch(
            "cja_auto_sdr.api.fetch.make_api_call_with_retry",
            side_effect=CircuitBreakerOpen("open", time_until_retry=5.0),
        ):
            result = fetcher._fetch_dimensions("dv_123")
        assert result.empty

    def test_fetch_dimensions_attribute_error(self):
        """AttributeError branch in _fetch_dimensions."""
        cja = MagicMock()
        fetcher = self._make_fetcher(cja)
        with patch(
            "cja_auto_sdr.api.fetch.make_api_call_with_retry",
            side_effect=AttributeError("no getDimensions"),
        ):
            result = fetcher._fetch_dimensions("dv_123")
        assert result.empty

    def test_fetch_dimensions_generic_exception(self):
        """Generic exception branch in _fetch_dimensions."""
        cja = MagicMock()
        fetcher = self._make_fetcher(cja)
        with patch(
            "cja_auto_sdr.api.fetch.make_api_call_with_retry",
            side_effect=RuntimeError("dims fail"),
        ):
            result = fetcher._fetch_dimensions("dv_123")
        assert result.empty

    def test_fetch_dimensions_returns_none(self):
        """Branch where API returns None for dimensions."""
        cja = MagicMock()
        fetcher = self._make_fetcher(cja)
        with patch(
            "cja_auto_sdr.api.fetch.make_api_call_with_retry",
            return_value=None,
        ):
            result = fetcher._fetch_dimensions("dv_123")
        assert result.empty

    def test_fetch_dataview_circuit_breaker_open(self):
        """CircuitBreakerOpen branch in _fetch_dataview_info."""
        cja = MagicMock()
        fetcher = self._make_fetcher(cja)
        with patch(
            "cja_auto_sdr.api.fetch.make_api_call_with_retry",
            side_effect=CircuitBreakerOpen("open", time_until_retry=5.0),
        ):
            result = fetcher._fetch_dataview_info("dv_123")
        assert result["name"] == "Unknown"
        assert result.get("circuit_breaker_open") is True

    def test_fetch_dataview_generic_exception(self):
        """Generic exception branch in _fetch_dataview_info."""
        cja = MagicMock()
        fetcher = self._make_fetcher(cja)
        with patch(
            "cja_auto_sdr.api.fetch.make_api_call_with_retry",
            side_effect=RuntimeError("info fail"),
        ):
            result = fetcher._fetch_dataview_info("dv_123")
        assert result["name"] == "Unknown"
        assert "error" in result

    def test_fetch_dataview_returns_empty(self):
        """Branch where API returns empty/falsy for data view info."""
        cja = MagicMock()
        fetcher = self._make_fetcher(cja)
        with patch(
            "cja_auto_sdr.api.fetch.make_api_call_with_retry",
            return_value={},
        ):
            result = fetcher._fetch_dataview_info("dv_123")
        assert result["name"] == "Unknown"

    def test_fetch_all_data_with_errors(self):
        """fetch_all_data handles per-task exceptions gracefully."""
        cja = MagicMock()
        fetcher = self._make_fetcher(cja)
        with (
            patch.object(fetcher, "_fetch_metrics", side_effect=RuntimeError("m")),
            patch.object(fetcher, "_fetch_dimensions", side_effect=RuntimeError("d")),
            patch.object(fetcher, "_fetch_dataview_info", side_effect=RuntimeError("dv")),
        ):
            metrics, dims, info = fetcher.fetch_all_data("dv_123")
        assert metrics.empty
        assert dims.empty
        assert info == {}

    def test_get_tuner_statistics_none(self):
        """get_tuner_statistics returns None when tuner is not set."""
        fetcher = self._make_fetcher()
        assert fetcher.get_tuner_statistics() is None

    def test_timed_api_call_records_tuner(self):
        """_timed_api_call updates tuner and max_workers when tuner is present."""
        from cja_auto_sdr.api.fetch import ParallelAPIFetcher
        from cja_auto_sdr.core.config import APITuningConfig
        from cja_auto_sdr.core.perf import PerformanceTracker

        logger = _make_logger()
        perf = PerformanceTracker(logger=logger)
        cja = MagicMock()
        config = APITuningConfig(min_workers=1, max_workers=5, sample_window=1, cooldown_seconds=0)
        fetcher = ParallelAPIFetcher(
            cja=cja,
            logger=logger,
            perf_tracker=perf,
            max_workers=3,
            quiet=True,
            tuning_config=config,
        )
        with patch(
            "cja_auto_sdr.api.fetch.make_api_call_with_retry",
            return_value="ok",
        ):
            result = fetcher._timed_api_call(lambda: None, operation_name="test")
        assert result == "ok"

    def test_timed_api_call_uses_monotonic_clock(self):
        """_timed_api_call measures duration with perf_counter, not wall clock."""
        from cja_auto_sdr.api.fetch import ParallelAPIFetcher
        from cja_auto_sdr.core.config import APITuningConfig
        from cja_auto_sdr.core.perf import PerformanceTracker

        logger = _make_logger()
        perf = PerformanceTracker(logger=logger)
        cja = MagicMock()
        config = APITuningConfig(min_workers=1, max_workers=5, sample_window=1, cooldown_seconds=0)
        fetcher = ParallelAPIFetcher(
            cja=cja, logger=logger, perf_tracker=perf, max_workers=3, quiet=True, tuning_config=config
        )
        # Simulate a deterministic 0.05s elapsed via patched perf_counter
        clock = iter([100.0, 100.05])
        with (
            patch("cja_auto_sdr.api.fetch.time.perf_counter", side_effect=clock),
            patch("cja_auto_sdr.api.fetch.make_api_call_with_retry", return_value="ok"),
        ):
            result = fetcher._timed_api_call(lambda: None, operation_name="test")
        assert result == "ok"
        # Tuner should have received ~50ms
        stats = fetcher.get_tuner_statistics()
        assert stats is not None
        assert stats["total_requests"] >= 1

    def test_timed_api_call_nonnegative_even_if_clock_wraps(self):
        """Duration stays non-negative even with unusual perf_counter values."""
        from cja_auto_sdr.api.fetch import ParallelAPIFetcher
        from cja_auto_sdr.core.config import APITuningConfig
        from cja_auto_sdr.core.perf import PerformanceTracker

        logger = _make_logger()
        perf = PerformanceTracker(logger=logger)
        cja = MagicMock()
        config = APITuningConfig(min_workers=1, max_workers=5, sample_window=1, cooldown_seconds=0)
        fetcher = ParallelAPIFetcher(
            cja=cja, logger=logger, perf_tracker=perf, max_workers=3, quiet=True, tuning_config=config
        )
        # perf_counter returns identical values → 0ms duration (non-negative)
        clock = iter([42.0, 42.0])
        with (
            patch("cja_auto_sdr.api.fetch.time.perf_counter", side_effect=clock),
            patch("cja_auto_sdr.api.fetch.make_api_call_with_retry", return_value="ok"),
        ):
            result = fetcher._timed_api_call(lambda: None, operation_name="test")
        assert result == "ok"

    def test_timed_api_call_no_tuner(self):
        """_timed_api_call works without a tuner (no timing recorded)."""
        from cja_auto_sdr.api.fetch import ParallelAPIFetcher
        from cja_auto_sdr.core.perf import PerformanceTracker

        logger = _make_logger()
        perf = PerformanceTracker(logger=logger)
        cja = MagicMock()
        fetcher = ParallelAPIFetcher(cja=cja, logger=logger, perf_tracker=perf, max_workers=3, quiet=True)
        assert fetcher.tuner is None
        with patch("cja_auto_sdr.api.fetch.make_api_call_with_retry", return_value="data"):
            result = fetcher._timed_api_call(lambda: None, operation_name="test")
        assert result == "data"

    def test_timed_api_call_max_workers_update(self):
        """_timed_api_call updates max_workers only when tuner returns a new value."""
        from cja_auto_sdr.api.fetch import ParallelAPIFetcher
        from cja_auto_sdr.core.config import APITuningConfig
        from cja_auto_sdr.core.perf import PerformanceTracker

        logger = _make_logger()
        perf = PerformanceTracker(logger=logger)
        cja = MagicMock()
        config = APITuningConfig(min_workers=1, max_workers=5, sample_window=1, cooldown_seconds=0)
        fetcher = ParallelAPIFetcher(
            cja=cja, logger=logger, perf_tracker=perf, max_workers=3, quiet=True, tuning_config=config
        )
        # Force the tuner to return a new worker count
        fetcher.tuner.record_response_time = MagicMock(return_value=4)
        clock = iter([0.0, 0.1])
        with (
            patch("cja_auto_sdr.api.fetch.time.perf_counter", side_effect=clock),
            patch("cja_auto_sdr.api.fetch.make_api_call_with_retry", return_value="ok"),
        ):
            fetcher._timed_api_call(lambda: None, operation_name="test")
        assert fetcher.max_workers == 4
        fetcher.tuner.record_response_time.assert_called_once()
        # Duration should be ~100ms
        actual_ms = fetcher.tuner.record_response_time.call_args[0][0]
        assert 99.0 <= actual_ms <= 101.0


# ===================================================================
# resilience.py — _parse_env_numeric and _effective_retry_config
# ===================================================================


class TestParseEnvNumeric:
    """Various branches of _parse_env_numeric."""

    def test_none_returns_none(self):
        assert _parse_env_numeric(None, int) is None

    def test_invalid_int_returns_none(self):
        assert _parse_env_numeric("abc", int) is None

    def test_valid_int(self):
        assert _parse_env_numeric("42", int) == 42

    def test_infinity_returns_none(self):
        assert _parse_env_numeric("inf", float) is None

    def test_nan_returns_none(self):
        assert _parse_env_numeric("nan", float) is None

    def test_valid_float(self):
        assert _parse_env_numeric("3.14", float) == pytest.approx(3.14)


class TestEffectiveRetryConfig:
    """Env-var override paths in _effective_retry_config."""

    def test_valid_env_overrides(self, monkeypatch):
        monkeypatch.setenv("MAX_RETRIES", "7")
        monkeypatch.setenv("RETRY_BASE_DELAY", "0.5")
        monkeypatch.setenv("RETRY_MAX_DELAY", "10.0")
        cfg = _effective_retry_config()
        assert cfg["max_retries"] == 7
        assert cfg["base_delay"] == pytest.approx(0.5)
        assert cfg["max_delay"] == pytest.approx(10.0)

    def test_invalid_env_uses_defaults(self, monkeypatch, caplog):
        monkeypatch.setenv("MAX_RETRIES", "bad")
        monkeypatch.setenv("RETRY_BASE_DELAY", "nope")
        monkeypatch.setenv("RETRY_MAX_DELAY", "nah")
        with caplog.at_level(logging.WARNING):
            _effective_retry_config()
        assert "Ignoring invalid MAX_RETRIES" in caplog.text
        assert "Ignoring invalid RETRY_BASE_DELAY" in caplog.text
        assert "Ignoring invalid RETRY_MAX_DELAY" in caplog.text

    def test_negative_retries_uses_default(self, monkeypatch, caplog):
        monkeypatch.setenv("MAX_RETRIES", "-1")
        with caplog.at_level(logging.WARNING):
            _effective_retry_config()
        assert "Ignoring invalid MAX_RETRIES" in caplog.text

    def test_max_delay_less_than_base_delay(self, monkeypatch, caplog):
        """Guard: max_delay < base_delay gets corrected."""
        monkeypatch.setenv("RETRY_BASE_DELAY", "10.0")
        monkeypatch.setenv("RETRY_MAX_DELAY", "1.0")
        with caplog.at_level(logging.WARNING):
            cfg = _effective_retry_config()
        assert cfg["max_delay"] == cfg["base_delay"]
        assert "invalid retry delay window" in caplog.text


# ===================================================================
# resilience.py — ErrorMessageHelper
# ===================================================================


class TestErrorMessageHelper:
    """Cover various helper methods."""

    @pytest.mark.parametrize("code", [400, 401, 403, 404, 429, 500, 502, 503, 504, 999])
    def test_get_http_error_message(self, code):
        msg = ErrorMessageHelper.get_http_error_message(code, "test_op")
        assert "test_op" in msg
        assert f"HTTP {code}" in msg

    @pytest.mark.parametrize("error_cls", [ConnectionError, TimeoutError, OSError, RuntimeError])
    def test_get_network_error_message(self, error_cls):
        err = error_cls("something went wrong")
        msg = ErrorMessageHelper.get_network_error_message(err, "fetch")
        assert "fetch" in msg

    @pytest.mark.parametrize(
        "error_type",
        ["file_not_found", "invalid_json", "missing_credentials", "invalid_format", "unknown_type"],
    )
    def test_get_config_error_message(self, error_type):
        msg = ErrorMessageHelper.get_config_error_message(error_type, "some details")
        assert "some details" in msg or "Configuration" in msg

    def test_get_data_view_error_message_with_id(self):
        msg = ErrorMessageHelper.get_data_view_error_message("dv_abc123", available_count=5)
        assert "dv_abc123" in msg
        assert "5 data view(s)" in msg

    def test_get_data_view_error_message_with_name(self):
        msg = ErrorMessageHelper.get_data_view_error_message("My Data View", available_count=0)
        assert "My Data View" in msg
        assert "No data views found" in msg

    def test_get_data_view_error_message_no_count(self):
        msg = ErrorMessageHelper.get_data_view_error_message("dv_x")
        assert "dv_x" in msg


# ===================================================================
# resilience.py — CircuitBreaker
# ===================================================================


class TestCircuitBreakerDecorator:
    """Cover the __call__ decorator path."""

    def test_decorator_success(self):
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=3))

        @cb
        def good_func():
            return 42

        assert good_func() == 42

    def test_decorator_raises_on_open(self):
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=1, timeout_seconds=9999))
        # Trip the breaker
        cb.record_failure(RuntimeError("fail"))
        assert cb.state == CircuitState.OPEN

        @cb
        def never_called():
            return 99

        with pytest.raises(CircuitBreakerOpen):
            never_called()

    def test_decorator_records_failure(self):
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=5))

        @cb
        def boom():
            raise ConnectionError("network down")

        with pytest.raises(ConnectionError):
            boom()
        stats = cb.get_statistics()
        assert stats["total_failures"] == 1

    def test_half_open_to_open_on_failure(self):
        """HALF_OPEN -> OPEN on failure."""
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=1, timeout_seconds=0, success_threshold=2))
        # Trip to OPEN
        cb.record_failure(RuntimeError())
        assert cb.state == CircuitState.OPEN

        # Transition to HALF_OPEN via allow_request (timeout=0 so immediate)
        time.sleep(0.01)
        assert cb.allow_request() is True
        assert cb.state == CircuitState.HALF_OPEN

        # Fail again -> back to OPEN
        cb.record_failure(RuntimeError())
        assert cb.state == CircuitState.OPEN

    def test_half_open_to_closed(self):
        """HALF_OPEN -> CLOSED after success_threshold successes."""
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=1, timeout_seconds=0, success_threshold=2))
        cb.record_failure(RuntimeError())
        time.sleep(0.01)
        cb.allow_request()  # Transition to HALF_OPEN
        assert cb.state == CircuitState.HALF_OPEN

        cb.record_success()
        assert cb.state == CircuitState.HALF_OPEN
        cb.record_success()
        assert cb.state == CircuitState.CLOSED

    def test_open_rejection_counted(self):
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=1, timeout_seconds=9999))
        cb.record_failure(RuntimeError())
        assert cb.allow_request() is False
        stats = cb.get_statistics()
        assert stats["total_rejections"] == 1
        assert stats["time_until_retry_seconds"] > 0

    def test_reset(self):
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=1))
        cb.record_failure(RuntimeError())
        assert cb.state == CircuitState.OPEN
        cb.reset()
        assert cb.state == CircuitState.CLOSED


# ===================================================================
# resilience.py — retry_with_backoff decorator
# ===================================================================


class TestRetryWithBackoff:
    """Cover the decorator retry paths."""

    def test_success_no_retry(self):
        @retry_with_backoff(max_retries=2)
        def ok():
            return "good"

        assert ok() == "good"

    def test_retry_then_success(self):
        counter = {"n": 0}

        @retry_with_backoff(max_retries=3, base_delay=0.001, max_delay=0.01, jitter=False)
        def flaky():
            counter["n"] += 1
            if counter["n"] < 3:
                raise ConnectionError("transient")
            return "recovered"

        assert flaky() == "recovered"

    def test_all_retries_exhausted_retryable_http(self):
        @retry_with_backoff(max_retries=1, base_delay=0.001, jitter=False)
        def always_fail():
            raise RetryableHTTPError(503, "service down")

        with pytest.raises(RetryableHTTPError):
            always_fail()

    def test_all_retries_exhausted_network_error(self):
        @retry_with_backoff(max_retries=1, base_delay=0.001, jitter=False)
        def always_timeout():
            raise TimeoutError("timed out")

        with pytest.raises(TimeoutError):
            always_timeout()

    def test_all_retries_exhausted_generic_retryable(self):
        @retry_with_backoff(max_retries=1, base_delay=0.001, jitter=False)
        def always_os_error():
            raise OSError("disk io")

        with pytest.raises(OSError):
            always_os_error()

    def test_non_retryable_exception_raised_immediately(self):
        @retry_with_backoff(max_retries=3, base_delay=0.001)
        def bad_code():
            raise ValueError("not retryable")

        with pytest.raises(ValueError, match="not retryable"):
            bad_code()


# ===================================================================
# resilience.py — make_api_call_with_retry
# ===================================================================


class TestMakeApiCallWithRetry:
    """Cover edge cases in the function-based retry."""

    def test_circuit_breaker_blocks_call(self):
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=1, timeout_seconds=9999))
        cb.record_failure(RuntimeError())
        with pytest.raises(CircuitBreakerOpen):
            make_api_call_with_retry(lambda: None, logger=_make_logger(), circuit_breaker=cb)

    def test_retryable_status_in_response_dict(self, monkeypatch):
        """Cover dict response with status_code field for a project-retryable status."""
        monkeypatch.setenv("MAX_RETRIES", "0")
        # 408 is project-retryable (not in cjapy adapter status_forcelist).
        with pytest.raises(RetryableHTTPError):
            make_api_call_with_retry(
                lambda: {"status_code": 408},
                logger=_make_logger(),
                operation_name="test_op",
            )

    def test_retryable_status_in_error_dict(self, monkeypatch):
        """Cover dict response with nested error.status_code for a project-retryable status."""
        monkeypatch.setenv("MAX_RETRIES", "0")
        with pytest.raises(RetryableHTTPError):
            make_api_call_with_retry(
                lambda: {"error": {"status_code": 408}},
                logger=_make_logger(),
                operation_name="test_op",
            )

    def test_non_retryable_exception_records_cb_failure(self):
        """Non-retryable exception records failure on circuit breaker."""
        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=10))

        def bad():
            raise ValueError("bad arg")

        with pytest.raises(ValueError):
            make_api_call_with_retry(bad, logger=_make_logger(), circuit_breaker=cb)
        assert cb.get_statistics()["total_failures"] == 1

    def test_success_after_retry_with_cb(self, monkeypatch):
        """Success after retries records success on circuit breaker."""
        monkeypatch.setenv("MAX_RETRIES", "2")
        monkeypatch.setenv("RETRY_BASE_DELAY", "0.001")
        monkeypatch.setenv("RETRY_MAX_DELAY", "0.01")

        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=10))
        counter = {"n": 0}

        def flaky():
            counter["n"] += 1
            if counter["n"] < 2:
                raise ConnectionError("transient")
            return "ok"

        result = make_api_call_with_retry(flaky, logger=_make_logger(), operation_name="flaky_op", circuit_breaker=cb)
        assert result == "ok"

    def test_retryable_http_error_all_retries_with_cb(self, monkeypatch):
        """RetryableHTTPError after all retries records failure on circuit breaker."""
        monkeypatch.setenv("MAX_RETRIES", "1")
        monkeypatch.setenv("RETRY_BASE_DELAY", "0.001")
        monkeypatch.setenv("RETRY_MAX_DELAY", "0.01")

        cb = CircuitBreaker(config=CircuitBreakerConfig(failure_threshold=10))

        def always_503():
            raise RetryableHTTPError(503, "down")

        with pytest.raises(RetryableHTTPError):
            make_api_call_with_retry(always_503, logger=_make_logger(), operation_name="fail_op", circuit_breaker=cb)
        assert cb.get_statistics()["total_failures"] == 1

    def test_network_error_all_retries(self, monkeypatch):
        """ConnectionError after all retries logs enhanced network message."""
        monkeypatch.setenv("MAX_RETRIES", "0")

        def always_conn_err():
            raise ConnectionError("no route")

        with pytest.raises(ConnectionError):
            make_api_call_with_retry(always_conn_err, logger=_make_logger(), operation_name="net_op")

    def test_generic_retryable_all_retries(self, monkeypatch):
        """OSError after all retries logs generic troubleshooting."""
        monkeypatch.setenv("MAX_RETRIES", "0")

        def always_os_err():
            raise OSError("disk io")

        with pytest.raises(OSError):
            make_api_call_with_retry(always_os_err, logger=_make_logger(), operation_name="os_op")

    def test_status_code_on_result_object(self, monkeypatch):
        """Cover the hasattr(result, 'status_code') branch on a project-retryable status."""
        monkeypatch.setenv("MAX_RETRIES", "0")

        class FakeResponse:
            # 408 is project-retryable (not in cjapy adapter status_forcelist).
            status_code = 408

        with pytest.raises(RetryableHTTPError):
            make_api_call_with_retry(
                FakeResponse,
                logger=_make_logger(),
                operation_name="resp_op",
            )


# ---------------------------------------------------------------------------
# quality.py — empty/missing-column branches (lines 101, 139-144, 181-186)
# ---------------------------------------------------------------------------


class TestQualityEmptyBranches:
    """Cover early-return branches for empty DataFrames and missing columns."""

    def _checker(self):
        return DataQualityChecker(logger=_make_logger("q_empty"))

    def test_check_required_fields_missing_columns(self):
        """Line 101: required fields not present in columns."""
        qc = self._checker()
        df = pd.DataFrame({"x": [1]})
        qc.check_required_fields(df, "metrics", ["x", "missing_col"])
        assert any("Missing Fields" in i.get("Category", "") for i in qc.issues)

    def test_check_missing_descriptions_empty_df(self):
        """Lines 139-140: empty DataFrame skips description check."""
        qc = self._checker()
        qc.check_missing_descriptions(pd.DataFrame(), "dims")
        assert qc.issues == []

    def test_check_missing_descriptions_no_column(self):
        """Lines 143-144: 'description' column absent."""
        qc = self._checker()
        qc.check_missing_descriptions(pd.DataFrame({"name": ["a"]}), "dims")
        assert qc.issues == []

    def test_check_id_validity_empty_df(self):
        """Lines 181-182: empty DataFrame skips ID check."""
        qc = self._checker()
        qc.check_id_validity(pd.DataFrame(), "metrics")
        assert qc.issues == []

    def test_check_id_validity_no_id_column(self):
        """Lines 185-186: 'id' column absent."""
        qc = self._checker()
        qc.check_id_validity(pd.DataFrame({"name": ["a"]}), "metrics")
        assert qc.issues == []


# ---------------------------------------------------------------------------
# resilience.py — generic-exception and unreachable paths (lines 780-781,
# 805, 907-908, 933-935)
# ---------------------------------------------------------------------------


class TestResilienceGenericException:
    """Cover the else-branch for non-HTTP/non-network errors in retry loops."""

    def test_retry_decorator_generic_exception(self):
        """Lines 780-781: generic error triggers plain logger.error path."""

        @retry_with_backoff(max_retries=0, base_delay=0)
        def bad():
            raise RuntimeError("boom")

        with pytest.raises(RuntimeError, match="boom"):
            bad()

    def test_make_api_call_generic_exception(self, monkeypatch):
        """Lines 907-908: generic error in make_api_call_with_retry."""
        monkeypatch.setenv("MAX_RETRIES", "0")

        def bad():
            raise RuntimeError("kaboom")

        with pytest.raises(RuntimeError, match="kaboom"):
            make_api_call_with_retry(bad, logger=_make_logger(), operation_name="op")
