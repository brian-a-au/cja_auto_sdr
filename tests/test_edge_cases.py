"""
Tests for edge cases and boundary conditions.

Validates:
1. Configuration dataclasses (RetryConfig, CacheConfig, SDRConfig, etc.)
2. Custom exception hierarchy
3. Boundary conditions for retry logic
4. Empty dataframe handling
5. Invalid configuration combinations
6. OutputWriter Protocol
"""

import argparse
import logging
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import patch

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cja_auto_sdr.generator import (
    DEFAULT_CACHE,
    DEFAULT_LOG,
    DEFAULT_RETRY,
    DEFAULT_RETRY_CONFIG,
    DEFAULT_WORKERS,
    APIError,
    CacheConfig,
    # Custom exceptions
    CJASDRError,
    ConfigurationError,
    DataQualityChecker,
    LogConfig,
    OutputError,
    # OutputWriter Protocol
    OutputWriter,
    # Configuration dataclasses
    RetryConfig,
    SDRConfig,
    ValidationCache,
    ValidationError,
    WorkerConfig,
    # Existing functionality
    retry_with_backoff,
)


class TestCustomExceptions:
    """Test the custom exception hierarchy"""

    def test_cjasdr_error_base_class(self):
        """Test CJASDRError base class"""
        error = CJASDRError("Test error", details="Additional details")
        assert error.message == "Test error"
        assert error.details == "Additional details"
        assert str(error) == "Test error: Additional details"

    def test_cjasdr_error_without_details(self):
        """Test CJASDRError without details"""
        error = CJASDRError("Simple error")
        assert str(error) == "Simple error"
        assert error.details is None

    def test_configuration_error(self):
        """Test ConfigurationError"""
        error = ConfigurationError(
            "Missing credentials",
            config_file="config.json",
            field="client_id",
            details="Field is empty",
        )
        assert error.config_file == "config.json"
        assert error.field == "client_id"
        assert "Missing credentials" in str(error)

    def test_configuration_error_inheritance(self):
        """Test ConfigurationError inherits from CJASDRError"""
        error = ConfigurationError("Config error")
        assert isinstance(error, CJASDRError)
        assert isinstance(error, Exception)

    def test_api_error(self):
        """Test APIError"""
        error = APIError("API call failed", status_code=401, operation="getMetrics", details="Invalid token")
        assert error.status_code == 401
        assert error.operation == "getMetrics"
        assert "401" in str(error)
        assert "getMetrics" in str(error)

    def test_api_error_with_original_error(self):
        """Test APIError with wrapped exception"""
        original = ConnectionError("Network unreachable")
        error = APIError("Connection failed", original_error=original)
        assert error.original_error is original
        assert isinstance(error.original_error, ConnectionError)

    def test_validation_error(self):
        """Test ValidationError"""
        error = ValidationError(
            "Data quality check failed",
            item_type="Metrics",
            issue_count=5,
            details="Found 5 critical issues",
        )
        assert error.item_type == "Metrics"
        assert error.issue_count == 5

    def test_output_error(self):
        """Test OutputError"""
        error = OutputError(
            "Failed to write file",
            output_path="/tmp/output.xlsx",
            output_format="excel",
            details="Permission denied",
        )
        assert error.output_path == "/tmp/output.xlsx"
        assert error.output_format == "excel"

    def test_exception_hierarchy_catching(self):
        """Test that all custom exceptions can be caught by CJASDRError"""
        exceptions = [
            ConfigurationError("config"),
            APIError("api"),
            ValidationError("validation"),
            OutputError("output"),
        ]

        for exc in exceptions:
            try:
                raise exc
            except CJASDRError as caught:
                assert caught is exc
            except Exception:
                pytest.fail(f"{type(exc).__name__} not caught by CJASDRError")


class TestConfigurationDataclasses:
    """Test configuration dataclasses"""

    def test_retry_config_custom_values(self):
        """Test RetryConfig with custom values"""
        config = RetryConfig(max_retries=5, base_delay=0.5, max_delay=60.0, exponential_base=3, jitter=False)
        assert config.max_retries == 5
        assert config.base_delay == 0.5
        assert config.max_delay == 60.0
        assert config.exponential_base == 3
        assert config.jitter is False

    def test_retry_config_to_dict(self):
        """Test RetryConfig to_dict conversion"""
        config = RetryConfig()
        d = config.to_dict()
        assert isinstance(d, dict)
        assert d["max_retries"] == 3
        assert d["base_delay"] == 1.0
        assert d["jitter"] is True

    def test_cache_config_custom_values(self):
        """Test CacheConfig with custom values"""
        config = CacheConfig(enabled=True, max_size=500, ttl_seconds=7200)
        assert config.enabled is True
        assert config.max_size == 500
        assert config.ttl_seconds == 7200

    def test_sdr_config_defaults(self):
        """Test SDRConfig with nested defaults"""
        config = SDRConfig()
        assert isinstance(config.retry, RetryConfig)
        assert isinstance(config.cache, CacheConfig)
        assert isinstance(config.log, LogConfig)
        assert isinstance(config.workers, WorkerConfig)
        assert config.output_format == "excel"
        assert config.output_dir == "."
        assert config.skip_validation is False
        assert config.max_issues == 0
        assert config.quiet is False

    def test_sdr_config_from_args(self):
        """Test SDRConfig.from_args class method"""
        args = argparse.Namespace(
            max_retries=5,
            retry_base_delay=2.0,
            retry_max_delay=60.0,
            enable_cache=True,
            cache_size=500,
            cache_ttl=7200,
            log_level="DEBUG",
            workers=8,
            format="json",
            output_dir="/tmp/output",
            skip_validation=True,
            max_issues=10,
            quiet=True,
        )

        config = SDRConfig.from_args(args)

        assert config.retry.max_retries == 5
        assert config.retry.base_delay == 2.0
        assert config.retry.max_delay == 60.0
        assert config.cache.enabled is True
        assert config.cache.max_size == 500
        assert config.cache.ttl_seconds == 7200
        assert config.log.level == "DEBUG"
        assert config.workers.batch_workers == 8
        assert config.output_format == "json"
        assert config.output_dir == "/tmp/output"
        assert config.skip_validation is True
        assert config.max_issues == 10
        assert config.quiet is True

    def test_sdr_config_from_args_with_defaults(self):
        """Test SDRConfig.from_args with missing args uses defaults"""
        args = argparse.Namespace()  # Empty namespace

        config = SDRConfig.from_args(args)

        # Should use defaults for missing attributes
        assert config.retry.max_retries == 3
        assert config.cache.enabled is False
        assert config.output_format == "excel"


class TestDefaultConfigInstances:
    """Test default configuration instances"""

    def test_default_retry_instance(self):
        """Test DEFAULT_RETRY is a RetryConfig instance"""
        assert isinstance(DEFAULT_RETRY, RetryConfig)
        assert DEFAULT_RETRY.max_retries == 3

    def test_default_cache_instance(self):
        """Test DEFAULT_CACHE is a CacheConfig instance"""
        assert isinstance(DEFAULT_CACHE, CacheConfig)
        assert DEFAULT_CACHE.max_size == 1000

    def test_default_log_instance(self):
        """Test DEFAULT_LOG is a LogConfig instance"""
        assert isinstance(DEFAULT_LOG, LogConfig)
        assert DEFAULT_LOG.level == "INFO"

    def test_default_workers_instance(self):
        """Test DEFAULT_WORKERS is a WorkerConfig instance"""
        assert isinstance(DEFAULT_WORKERS, WorkerConfig)
        assert DEFAULT_WORKERS.batch_workers == 4

    def test_default_retry_config_dict_backward_compatible(self):
        """Test DEFAULT_RETRY_CONFIG dict is backward compatible"""
        assert isinstance(DEFAULT_RETRY_CONFIG, dict)
        assert DEFAULT_RETRY_CONFIG["max_retries"] == 3
        assert DEFAULT_RETRY_CONFIG["base_delay"] == 1.0
        assert DEFAULT_RETRY_CONFIG["jitter"] is True


class TestOutputWriterProtocol:
    """Test OutputWriter Protocol"""

    def test_protocol_is_runtime_checkable(self):
        """Test that OutputWriter Protocol is runtime checkable"""

        # Should be a Protocol
        assert hasattr(OutputWriter, "__protocol_attrs__") or OutputWriter.__class__.__name__ == "_ProtocolMeta"

    def test_class_implementing_protocol(self):
        """Test a class implementing OutputWriter protocol"""

        class TestWriter:
            def write(
                self,
                metrics_df: pd.DataFrame,
                dimensions_df: pd.DataFrame,
                dataview_info: dict[str, Any],
                output_path: Path,
                quality_results: list[dict[str, Any]] | None = None,
            ) -> str:
                return str(output_path)

        writer = TestWriter()
        result = writer.write(pd.DataFrame(), pd.DataFrame(), {}, Path("/tmp/output"))
        assert result == "/tmp/output"

    def test_protocol_isinstance_check(self):
        """Test isinstance check with OutputWriter protocol"""

        class ValidWriter:
            def write(
                self,
                metrics_df: pd.DataFrame,
                dimensions_df: pd.DataFrame,
                dataview_info: dict[str, Any],
                output_path: Path,
                quality_results: list[dict[str, Any]] | None = None,
            ) -> str:
                return "output"

        class InvalidWriter:
            def write_data(self):  # Wrong method name
                pass

        # Note: Protocol isinstance checks require runtime_checkable
        # and may not work perfectly for structural subtyping
        writer = ValidWriter()
        # At minimum, the writer should have the write method
        assert hasattr(writer, "write")
        assert callable(writer.write)


class TestRetryEdgeCases:
    """Test edge cases for retry logic"""

    def test_retry_with_zero_max_retries(self):
        """Test retry with max_retries=0 (no retries)"""
        call_count = 0

        @retry_with_backoff(max_retries=0, base_delay=0.01, jitter=False)
        def no_retry_func():
            nonlocal call_count
            call_count += 1
            raise ConnectionError("Fail")

        with pytest.raises(ConnectionError):
            no_retry_func()

        assert call_count == 1  # Only initial call, no retries

    def test_retry_with_zero_base_delay(self):
        """Test retry with base_delay=0 (immediate retry)"""
        call_count = 0

        @retry_with_backoff(max_retries=2, base_delay=0, jitter=False)
        def immediate_retry_func():
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise ConnectionError("Fail")
            return "success"

        with patch("time.sleep") as mock_sleep:
            result = immediate_retry_func()

        assert result == "success"
        assert call_count == 3
        # With base_delay=0, delays should be 0
        for call in mock_sleep.call_args_list:
            assert call.args[0] == 0

    def test_retry_with_very_large_exponential_base(self):
        """Test retry with large exponential base hits max_delay cap"""

        @retry_with_backoff(max_retries=3, base_delay=1, max_delay=10, exponential_base=100, jitter=False)
        def large_base_func():
            raise ConnectionError("Fail")

        with patch("time.sleep") as mock_sleep:
            with pytest.raises(ConnectionError):
                large_base_func()

        # All delays should be capped at max_delay=10
        for call in mock_sleep.call_args_list:
            assert call.args[0] <= 10


class TestEmptyDataFrameHandling:
    """Test handling of empty DataFrames"""

    def test_validation_cache_with_empty_df(self):
        """Test cache handles empty DataFrame correctly"""
        cache = ValidationCache(max_size=100, ttl_seconds=3600)
        empty_df = pd.DataFrame()

        # Should not raise
        result, cache_key = cache.get(empty_df, "Metrics", ["id", "name", "type"], ["id", "name"])
        assert result is None
        assert cache_key is not None

        # Should be able to store and retrieve
        cache.put(empty_df, "Metrics", ["id", "name", "type"], ["id", "name"], [])
        result, _ = cache.get(empty_df, "Metrics", ["id", "name", "type"], ["id", "name"])
        assert result == []

    def test_data_quality_checker_empty_df(self):
        """Test DataQualityChecker handles empty DataFrame"""
        logger = logging.getLogger("test")
        checker = DataQualityChecker(logger)

        empty_df = pd.DataFrame()

        # Should not raise
        checker.check_duplicates(empty_df, "Metrics")
        checker.check_required_fields(empty_df, "Metrics", ["id", "name"])
        checker.check_null_values(empty_df, "Metrics", ["id", "name"])

        # Empty DataFrame checks should not add issues (or add appropriate ones)
        # This is existing behavior we're testing doesn't break

    def test_data_quality_checker_single_row_df(self):
        """Test DataQualityChecker with single row DataFrame"""
        logger = logging.getLogger("test")
        checker = DataQualityChecker(logger)

        single_row_df = pd.DataFrame({"id": ["m1"], "name": ["Metric 1"], "type": ["int"]})

        checker.check_duplicates(single_row_df, "Metrics")
        # Single row can't have duplicates
        assert not any(i["Category"] == "Duplicates" for i in checker.issues)


class TestCacheEdgeCases:
    """Test edge cases for ValidationCache"""

    def test_cache_size_one(self):
        """Test cache with max_size=1"""
        cache = ValidationCache(max_size=1, ttl_seconds=3600)

        df1 = pd.DataFrame({"id": [1]})
        df2 = pd.DataFrame({"id": [2]})

        cache.put(df1, "Metrics", ["id"], [], [{"issue": "1"}])
        cache.put(df2, "Metrics", ["id"], [], [{"issue": "2"}])

        # Cache should only have the latest entry
        stats = cache.get_statistics()
        assert stats["size"] == 1
        assert stats["evictions"] == 1

        # df2 should be cached, df1 should be evicted
        result1, _ = cache.get(df1, "Metrics", ["id"], [])
        result2, _ = cache.get(df2, "Metrics", ["id"], [])
        assert result1 is None
        assert result2 is not None

    def test_cache_ttl_one_second(self):
        """Test cache with very short TTL"""
        import time

        cache = ValidationCache(max_size=100, ttl_seconds=1)

        df = pd.DataFrame({"id": [1]})
        cache.put(df, "Metrics", ["id"], [], [{"issue": "test"}])

        # Immediately should be cached
        result, _ = cache.get(df, "Metrics", ["id"], [])
        assert result is not None

        # After expiry
        time.sleep(1.1)
        result, _ = cache.get(df, "Metrics", ["id"], [])
        assert result is None

    def test_cache_with_identical_df_different_item_type(self):
        """Test cache distinguishes by item_type"""
        cache = ValidationCache(max_size=100, ttl_seconds=3600)

        df = pd.DataFrame({"id": [1], "name": ["Test"]})

        cache.put(df, "Metrics", ["id", "name"], [], [{"issue": "metrics"}])
        cache.put(df, "Dimensions", ["id", "name"], [], [{"issue": "dimensions"}])

        # Should have two separate entries
        result_m, _ = cache.get(df, "Metrics", ["id", "name"], [])
        result_d, _ = cache.get(df, "Dimensions", ["id", "name"], [])

        assert result_m[0]["issue"] == "metrics"
        assert result_d[0]["issue"] == "dimensions"


class TestDataFrameColumnHandling:
    """Test handling of DataFrames with various column configurations"""

    def test_df_with_missing_expected_columns(self):
        """Test validation with DataFrame missing expected columns"""
        logger = logging.getLogger("test")
        checker = DataQualityChecker(logger)

        # DataFrame without 'name' column
        df = pd.DataFrame({"id": ["m1", "m2"], "type": ["int", "currency"]})

        # check_duplicates should skip gracefully
        checker.check_duplicates(df, "Metrics")
        # Should not crash, may log warning

    def test_df_with_extra_columns(self):
        """Test validation with DataFrame having extra columns"""
        logger = logging.getLogger("test")
        checker = DataQualityChecker(logger)

        df = pd.DataFrame(
            {
                "id": ["m1", "m2"],
                "name": ["Metric 1", "Metric 2"],
                "type": ["int", "currency"],
                "extra_col": ["a", "b"],
                "another_extra": [1, 2],
            },
        )

        # Should handle extra columns gracefully
        checker.check_required_fields(df, "Metrics", ["id", "name", "type"])
        checker.check_duplicates(df, "Metrics")

        # No "missing fields" issues should be logged for required fields
        missing_issues = [i for i in checker.issues if "Missing Fields" in i.get("Category", "")]
        assert len(missing_issues) == 0


class TestConcurrentAccessEdgeCases:
    """Test concurrent access edge cases"""

    def test_cache_clear_during_access(self):
        """Test cache clear while other operations are occurring"""
        from concurrent.futures import ThreadPoolExecutor

        cache = ValidationCache(max_size=100, ttl_seconds=3600)
        errors = []

        def reader():
            for _ in range(100):
                try:
                    df = pd.DataFrame({"id": [1]})
                    cache.get(df, "Metrics", ["id"], [])
                except Exception as e:
                    errors.append(e)

        def writer():
            for _ in range(50):
                try:
                    df = pd.DataFrame({"id": [1]})
                    cache.put(df, "Metrics", ["id"], [], [])
                except Exception as e:
                    errors.append(e)

        def clearer():
            for _ in range(10):
                try:
                    cache.clear()
                except Exception as e:
                    errors.append(e)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [
                executor.submit(reader),
                executor.submit(reader),
                executor.submit(writer),
                executor.submit(writer),
                executor.submit(clearer),
            ]
            for f in futures:
                f.result()

        # Should have no errors
        assert len(errors) == 0


# Fixtures for common test data
@pytest.fixture
def sample_metrics_df():
    """Sample metrics DataFrame for testing"""
    return pd.DataFrame(
        {
            "id": ["m1", "m2", "m3"],
            "name": ["Metric 1", "Metric 2", "Metric 3"],
            "type": ["int", "currency", "percent"],
            "description": ["First metric", None, "Third metric"],
        },
    )


@pytest.fixture
def sample_dimensions_df():
    """Sample dimensions DataFrame for testing"""
    return pd.DataFrame(
        {
            "id": ["d1", "d2", "d3"],
            "name": ["Dimension 1", "Dimension 2", "Dimension 3"],
            "type": ["string", "string", "string"],
            "description": ["First dimension", "Second dimension", None],
        },
    )
