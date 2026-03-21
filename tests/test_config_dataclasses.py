"""Tests for configuration dataclasses and constants utility functions.

Covers config.py (RetryConfig, CacheConfig, LogConfig, WorkerConfig,
APITuningConfig, CircuitState, CircuitBreakerConfig, SDRConfig, WizardConfig)
and constants.py (auto_detect_workers, infer_format_from_path,
should_generate_format, CREDENTIAL_FIELDS, FORMAT_ALIASES, etc.).
"""

import argparse
import os
import sys
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cja_auto_sdr.core.config import (
    APITuningConfig,
    CacheConfig,
    CircuitBreakerConfig,
    CircuitState,
    LogConfig,
    RetryConfig,
    SDRConfig,
    WizardConfig,
    WorkerConfig,
)
from cja_auto_sdr.core.constants import (
    AUTO_WORKERS_SENTINEL,
    BANNER_WIDTH,
    CONFIG_SCHEMA,
    CREDENTIAL_FIELDS,
    DEFAULT_API_FETCH_WORKERS,
    DEFAULT_BATCH_WORKERS,
    DEFAULT_CACHE_SIZE,
    DEFAULT_CACHE_TTL,
    DEFAULT_ORG_REPORT_WORKERS,
    DEFAULT_RETRY,
    DEFAULT_RETRY_CONFIG,
    DEFAULT_VALIDATION_WORKERS,
    ENV_VAR_MAPPING,
    FORMAT_ALIASES,
    GOVERNANCE_MAX_OVERLAP_THRESHOLD,
    JWT_DEPRECATED_FIELDS,
    LOG_FILE_BACKUP_COUNT,
    LOG_FILE_MAX_BYTES,
    MAX_BATCH_WORKERS,
    RETRYABLE_STATUS_CODES,
    VALIDATION_SCHEMA,
    _get_credential_fields,
    auto_detect_workers,
    infer_format_from_path,
    should_generate_format,
)


# ==================== RetryConfig ====================
class TestRetryConfig:
    def test_default_values(self):
        config = RetryConfig()
        assert config.max_retries == 3
        assert config.base_delay == 1.0
        assert config.max_delay == 30.0
        assert config.exponential_base == 2
        assert config.jitter is True

    def test_custom_values(self):
        config = RetryConfig(max_retries=5, base_delay=2.0, max_delay=60.0, exponential_base=3, jitter=False)
        assert config.max_retries == 5
        assert config.base_delay == 2.0
        assert config.max_delay == 60.0
        assert config.exponential_base == 3
        assert config.jitter is False

    def test_to_dict(self):
        config = RetryConfig()
        d = config.to_dict()
        assert d == {"max_retries": 3, "base_delay": 1.0, "max_delay": 30.0, "exponential_base": 2, "jitter": True}

    def test_to_dict_custom(self):
        config = RetryConfig(max_retries=10, base_delay=0.5)
        d = config.to_dict()
        assert d["max_retries"] == 10
        assert d["base_delay"] == 0.5


# ==================== CacheConfig ====================
class TestCacheConfig:
    def test_default_values(self):
        config = CacheConfig()
        assert config.enabled is False
        assert config.max_size == 1000
        assert config.ttl_seconds == 3600

    def test_custom_values(self):
        config = CacheConfig(enabled=True, max_size=500, ttl_seconds=1800)
        assert config.enabled is True
        assert config.max_size == 500


# ==================== LogConfig ====================
class TestLogConfig:
    def test_default_values(self):
        config = LogConfig()
        assert config.level == "INFO"
        assert config.file_max_bytes == 10 * 1024 * 1024
        assert config.file_backup_count == 5


# ==================== WorkerConfig ====================
class TestWorkerConfig:
    def test_default_values(self):
        config = WorkerConfig()
        assert config.api_fetch_workers == 3
        assert config.validation_workers == 2
        assert config.batch_workers == 4
        assert config.max_batch_workers == 256


# ==================== APITuningConfig ====================
class TestAPITuningConfig:
    def test_default_values(self):
        config = APITuningConfig()
        assert config.min_workers == 1
        assert config.max_workers == 10
        assert config.scale_up_threshold_ms == 200.0
        assert config.scale_down_threshold_ms == 2000.0
        assert config.sample_window == 5
        assert config.cooldown_seconds == 10.0


# ==================== CircuitState ====================
class TestCircuitState:
    def test_values(self):
        assert CircuitState.CLOSED.value == "closed"
        assert CircuitState.OPEN.value == "open"
        assert CircuitState.HALF_OPEN.value == "half_open"

    def test_iteration(self):
        states = list(CircuitState)
        assert len(states) == 3


# ==================== CircuitBreakerConfig ====================
class TestCircuitBreakerConfig:
    def test_default_values(self):
        config = CircuitBreakerConfig()
        assert config.failure_threshold == 5
        assert config.success_threshold == 2
        assert config.timeout_seconds == 30.0


# ==================== SDRConfig ====================
class TestSDRConfig:
    def test_default_values(self):
        config = SDRConfig()
        assert config.output_format == "excel"
        assert config.output_dir == "."
        assert config.skip_validation is False
        assert config.max_issues == 0
        assert config.quiet is False

    def test_default_nested_configs(self):
        config = SDRConfig()
        assert isinstance(config.retry, RetryConfig)
        assert isinstance(config.cache, CacheConfig)
        assert isinstance(config.log, LogConfig)
        assert isinstance(config.workers, WorkerConfig)

    def test_independent_instances(self):
        config1 = SDRConfig()
        config2 = SDRConfig()
        config1.retry.max_retries = 99
        assert config2.retry.max_retries == 3


# ==================== SDRConfig.from_args ====================
class TestFromArgs:
    def test_from_args_full(self):
        args = argparse.Namespace(
            max_retries=5,
            retry_base_delay=2.0,
            retry_max_delay=60.0,
            enable_cache=True,
            cache_size=2000,
            cache_ttl=7200,
            log_level="DEBUG",
            workers=8,
            format="json",
            output_dir="/tmp",
            skip_validation=True,
            max_issues=100,
            quiet=True,
        )
        config = SDRConfig.from_args(args)
        assert config.retry.max_retries == 5
        assert config.retry.base_delay == 2.0
        assert config.cache.enabled is True
        assert config.cache.max_size == 2000
        assert config.log.level == "DEBUG"
        assert config.workers.batch_workers == 8
        assert config.output_format == "json"
        assert config.quiet is True

    def test_from_args_empty_namespace(self):
        args = argparse.Namespace()
        config = SDRConfig.from_args(args)
        assert config.retry.max_retries == 3
        assert config.cache.enabled is False
        assert config.output_format == "excel"
        assert config.output_dir == "."

    def test_from_args_partial(self):
        args = argparse.Namespace(format="csv", quiet=True)
        config = SDRConfig.from_args(args)
        assert config.output_format == "csv"
        assert config.quiet is True
        assert config.retry.max_retries == 3

    def test_from_args_returns_sdr_config(self):
        config = SDRConfig.from_args(argparse.Namespace())
        assert isinstance(config, SDRConfig)


# ==================== WizardConfig ====================
class TestWizardConfig:
    def test_default_values(self):
        config = WizardConfig()
        assert config.config_file == "config.json"
        assert config.data_views == []
        assert config.output_format == "excel"
        assert config.output_dir == "."
        assert config.skip_validation is False

    def test_data_views_independent_per_instance(self):
        config1 = WizardConfig()
        config2 = WizardConfig()
        config1.data_views.append("dv_mutated")
        assert config2.data_views == []


# ==================== auto_detect_workers ====================
class TestAutoDetectWorkers:
    @patch("os.cpu_count", return_value=8)
    def test_base_workers_from_cpu(self, mock_cpu):
        result = auto_detect_workers(num_data_views=10)
        assert result == 7

    @patch("os.cpu_count", return_value=8)
    def test_small_job_single_dv(self, mock_cpu):
        result = auto_detect_workers(num_data_views=1)
        assert result == 2

    @patch("os.cpu_count", return_value=8)
    def test_small_job_two_dvs(self, mock_cpu):
        result = auto_detect_workers(num_data_views=2)
        assert result == 4

    @patch("os.cpu_count", return_value=4)
    def test_four_cpus(self, mock_cpu):
        result = auto_detect_workers(num_data_views=5)
        assert result == 3

    @patch("os.cpu_count", return_value=None)
    def test_cpu_count_returns_none(self, mock_cpu):
        result = auto_detect_workers(num_data_views=5)
        assert result == 3

    @patch("os.cpu_count", return_value=16)
    def test_high_component_count_over_5000(self, mock_cpu):
        result = auto_detect_workers(num_data_views=20, total_components=6000)
        assert result == 7

    @patch("os.cpu_count", return_value=16)
    def test_high_component_count_over_10000(self, mock_cpu):
        result = auto_detect_workers(num_data_views=20, total_components=15000)
        assert result == 5

    @patch("os.cpu_count", return_value=4)
    def test_high_component_count_over_10000_low_cpus(self, mock_cpu):
        result = auto_detect_workers(num_data_views=10, total_components=12000)
        assert result == 1

    @patch("os.cpu_count", return_value=8)
    def test_zero_components_no_reduction(self, mock_cpu):
        result = auto_detect_workers(num_data_views=10, total_components=0)
        assert result == 7

    @patch("os.cpu_count", return_value=8)
    def test_result_at_least_one(self, mock_cpu):
        result = auto_detect_workers(num_data_views=1, total_components=0)
        assert result >= 1

    @patch("os.cpu_count", return_value=8)
    def test_result_at_most_max_batch_workers(self, mock_cpu):
        result = auto_detect_workers(num_data_views=1000, total_components=0)
        assert result <= MAX_BATCH_WORKERS

    @patch("os.cpu_count", return_value=8)
    def test_default_arguments(self, mock_cpu):
        result = auto_detect_workers()
        assert result == 2


# ==================== infer_format_from_path ====================
class TestInferFormatFromPath:
    def test_xlsx_extension(self):
        assert infer_format_from_path("output.xlsx") == "excel"

    def test_csv_extension(self):
        assert infer_format_from_path("output.csv") == "csv"

    def test_json_extension(self):
        assert infer_format_from_path("report.json") == "json"

    def test_html_extension(self):
        assert infer_format_from_path("report.html") == "html"

    def test_htm_extension(self):
        assert infer_format_from_path("report.htm") == "html"

    def test_md_extension(self):
        assert infer_format_from_path("README.md") == "markdown"

    def test_markdown_extension(self):
        assert infer_format_from_path("doc.markdown") == "markdown"

    def test_unknown_extension(self):
        assert infer_format_from_path("output.txt") is None

    def test_empty_string(self):
        assert infer_format_from_path("") is None

    def test_dash_returns_none(self):
        assert infer_format_from_path("-") is None

    def test_stdout_returns_none(self):
        assert infer_format_from_path("stdout") is None

    def test_case_insensitive(self):
        assert infer_format_from_path("output.XLSX") == "excel"
        assert infer_format_from_path("output.Json") == "json"
        assert infer_format_from_path("output.MD") == "markdown"

    def test_path_with_directory(self):
        assert infer_format_from_path("/home/user/reports/output.csv") == "csv"


# ==================== should_generate_format ====================
class TestShouldGenerateFormat:
    def test_exact_match(self):
        assert should_generate_format("excel", "excel") is True
        assert should_generate_format("csv", "csv") is True

    def test_all_includes_standard_formats(self):
        for fmt in ["excel", "csv", "json", "html", "markdown", "console"]:
            assert should_generate_format("all", fmt) is True

    def test_all_excludes_unknown_format(self):
        assert should_generate_format("all", "pdf") is False

    def test_reports_alias(self):
        assert should_generate_format("reports", "excel") is True
        assert should_generate_format("reports", "markdown") is True
        assert should_generate_format("reports", "csv") is False

    def test_data_alias(self):
        assert should_generate_format("data", "csv") is True
        assert should_generate_format("data", "json") is True
        assert should_generate_format("data", "excel") is False

    def test_ci_alias(self):
        assert should_generate_format("ci", "json") is True
        assert should_generate_format("ci", "markdown") is True
        assert should_generate_format("ci", "excel") is False

    def test_non_matching_returns_false(self):
        assert should_generate_format("excel", "csv") is False


# ==================== CREDENTIAL_FIELDS ====================
class TestCredentialFields:
    def test_has_required_key(self):
        assert "required" in CREDENTIAL_FIELDS

    def test_has_optional_key(self):
        assert "optional" in CREDENTIAL_FIELDS

    def test_has_all_key(self):
        assert "all" in CREDENTIAL_FIELDS

    def test_required_includes_core_fields(self):
        required = CREDENTIAL_FIELDS["required"]
        assert "org_id" in required
        assert "client_id" in required
        assert "secret" in required

    def test_optional_includes_expected_fields(self):
        optional = CREDENTIAL_FIELDS["optional"]
        assert "scopes" in optional
        assert "sandbox" in optional

    def test_all_is_union(self):
        assert CREDENTIAL_FIELDS["all"] == CREDENTIAL_FIELDS["required"] | CREDENTIAL_FIELDS["optional"]

    def test_required_and_optional_disjoint(self):
        assert CREDENTIAL_FIELDS["required"] & CREDENTIAL_FIELDS["optional"] == set()

    def test_get_credential_fields_returns_same(self):
        assert _get_credential_fields() == CREDENTIAL_FIELDS

    def test_values_are_sets(self):
        for key in ("required", "optional", "all"):
            assert isinstance(CREDENTIAL_FIELDS[key], set)


# ==================== FORMAT_ALIASES ====================
class TestFormatAliases:
    def test_reports_alias_contents(self):
        assert "excel" in FORMAT_ALIASES["reports"]
        assert "markdown" in FORMAT_ALIASES["reports"]

    def test_data_alias_contents(self):
        assert "csv" in FORMAT_ALIASES["data"]
        assert "json" in FORMAT_ALIASES["data"]

    def test_ci_alias_contents(self):
        assert "json" in FORMAT_ALIASES["ci"]
        assert "markdown" in FORMAT_ALIASES["ci"]

    def test_all_aliases_present(self):
        assert set(FORMAT_ALIASES.keys()) == {"reports", "data", "ci"}


# ==================== Constants Values ====================
class TestConstantValues:
    def test_banner_width(self):
        assert BANNER_WIDTH == 80

    def test_max_batch_workers(self):
        assert MAX_BATCH_WORKERS == 256

    def test_default_api_fetch_workers(self):
        assert DEFAULT_API_FETCH_WORKERS == 3

    def test_default_validation_workers(self):
        assert DEFAULT_VALIDATION_WORKERS == 2

    def test_default_batch_workers(self):
        assert DEFAULT_BATCH_WORKERS == 4

    def test_auto_workers_sentinel(self):
        assert AUTO_WORKERS_SENTINEL == 0

    def test_default_org_report_workers(self):
        assert DEFAULT_ORG_REPORT_WORKERS == 10

    def test_governance_max_overlap_threshold(self):
        assert GOVERNANCE_MAX_OVERLAP_THRESHOLD == 0.9

    def test_default_cache_size(self):
        assert DEFAULT_CACHE_SIZE == 1000

    def test_default_cache_ttl(self):
        assert DEFAULT_CACHE_TTL == 3600

    def test_log_file_max_bytes(self):
        assert LOG_FILE_MAX_BYTES == 10 * 1024 * 1024

    def test_log_file_backup_count(self):
        assert LOG_FILE_BACKUP_COUNT == 5

    def test_retryable_status_codes(self):
        assert RETRYABLE_STATUS_CODES == {408, 429, 500, 502, 503, 504}

    def test_default_retry_config_matches_dataclass(self):
        assert DEFAULT_RETRY_CONFIG == RetryConfig().to_dict()

    def test_default_retry_is_retry_config_instance(self):
        assert isinstance(DEFAULT_RETRY, RetryConfig)


# ==================== Schemas and Mappings ====================
class TestSchemasAndMappings:
    def test_validation_schema_has_required_metric_fields(self):
        assert "required_metric_fields" in VALIDATION_SCHEMA
        assert "id" in VALIDATION_SCHEMA["required_metric_fields"]

    def test_validation_schema_has_required_dimension_fields(self):
        assert "required_dimension_fields" in VALIDATION_SCHEMA

    def test_validation_schema_has_critical_fields(self):
        assert "critical_fields" in VALIDATION_SCHEMA
        for f in ["id", "name", "title", "description"]:
            assert f in VALIDATION_SCHEMA["critical_fields"]

    def test_config_schema_has_base_required_fields(self):
        assert "base_required_fields" in CONFIG_SCHEMA
        assert "org_id" in CONFIG_SCHEMA["base_required_fields"]

    def test_jwt_deprecated_fields(self):
        assert "tech_acct" in JWT_DEPRECATED_FIELDS
        assert "private_key" in JWT_DEPRECATED_FIELDS
        assert "pathToKey" in JWT_DEPRECATED_FIELDS

    def test_env_var_mapping(self):
        assert ENV_VAR_MAPPING["org_id"] == "ORG_ID"
        assert ENV_VAR_MAPPING["client_id"] == "CLIENT_ID"
        assert ENV_VAR_MAPPING["secret"] == "SECRET"

    def test_env_var_mapping_covers_all_credential_fields(self):
        for field_name in CREDENTIAL_FIELDS["all"]:
            assert field_name in ENV_VAR_MAPPING
