import argparse
import contextlib
import csv
import hashlib
import html
import importlib.metadata
import io
import json
import logging
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import textwrap
import threading
import time
import uuid
from collections.abc import Callable, Collection, Iterable, Mapping
from concurrent.futures import ProcessPoolExecutor, as_completed
from concurrent.futures.process import BrokenProcessPool
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, NoReturn, Protocol, runtime_checkable

import cjapy
import pandas as pd
from tqdm import tqdm

from cja_auto_sdr.api.quality_policy import (
    QUALITY_POLICY_ALLOWED_KEYS,
    QUALITY_REPORT_PREFERRED_COLUMNS,
    _build_quality_report_dataframe,
    _canonical_quality_policy_key,
    _parse_boolean_policy_flag,
    _parse_non_negative_policy_int,
    apply_quality_policy_defaults,
    count_quality_issues_by_severity,
    has_quality_issues_at_or_above,
    load_quality_policy,
    normalize_quality_severity,
    write_quality_report_output,
)

# Dotenv loading is intentionally performed during runtime paths (CLI parsing and
# API configuration), not at import time, to avoid import-time filesystem I/O.
# ==================== IMPORTS FROM MODULAR SUBPACKAGES ====================
# These imports are from the new modular structure introduced in v3.2.0
# They are re-exported here for backwards compatibility
from cja_auto_sdr.api.resilience import (
    RETRYABLE_EXCEPTIONS,
    CircuitBreaker,
    ErrorMessageHelper,
    make_api_call_with_retry,
    retry_with_backoff,
)
from cja_auto_sdr.cli.option_resolution import resolve_long_option_token as _resolve_long_option_token
from cja_auto_sdr.core.colors import (
    ConsoleColors,
    _format_error_msg,
    format_file_size,
    open_file_in_default_app,
)
from cja_auto_sdr.core.config import (
    APITuningConfig,
    CacheConfig,
    CircuitBreakerConfig,
    CircuitState,
    LogConfig,
    RetryConfig,
    SDRConfig,
    WorkerConfig,
)
from cja_auto_sdr.core.constants import (
    AUTO_WORKERS_SENTINEL,
    BANNER_WIDTH,
    CONFIG_SCHEMA,
    CREDENTIAL_FIELDS,
    DEFAULT_API_FETCH_WORKERS,
    DEFAULT_AUTO_PRUNE_KEEP_LAST,
    DEFAULT_AUTO_PRUNE_KEEP_SINCE,
    DEFAULT_BATCH_WORKERS,
    DEFAULT_CACHE,
    DEFAULT_CACHE_SIZE,
    DEFAULT_CACHE_TTL,
    DEFAULT_LOG,
    DEFAULT_RETRY,
    DEFAULT_RETRY_CONFIG,
    DEFAULT_VALIDATION_WORKERS,
    DEFAULT_WORKERS,
    ENV_VAR_MAPPING,
    EXTENSION_TO_FORMAT,
    FORMAT_ALIASES,
    JWT_DEPRECATED_FIELDS,
    LOG_FILE_BACKUP_COUNT,
    LOG_FILE_MAX_BYTES,
    MAX_BATCH_WORKERS,
    QUALITY_SEVERITY_ORDER,
    QUALITY_SEVERITY_RANK,
    RETRYABLE_STATUS_CODES,
    VALIDATION_SCHEMA,
    _get_credential_fields,
    auto_detect_workers,
    infer_format_from_path,
    should_generate_format,
)
from cja_auto_sdr.core.discovery_exceptions import (
    coerce_http_status_code as _coerce_http_status_code_core,
)
from cja_auto_sdr.core.discovery_exceptions import (
    extract_http_status_codes as _extract_http_status_codes_core,
)
from cja_auto_sdr.core.discovery_exceptions import (
    is_dataview_lookup_not_found_error as _is_inaccessible_dataview_lookup_error_core,
)
from cja_auto_sdr.core.discovery_exceptions import (
    iter_error_chain_nodes as _iter_error_chain_nodes_core,
)
from cja_auto_sdr.core.discovery_normalization import (
    extract_owner_name as _extract_owner_name_normalized,
)
from cja_auto_sdr.core.discovery_normalization import (
    extract_owner_name_from_record as _extract_owner_name_from_record_normalized,
)
from cja_auto_sdr.core.discovery_normalization import (
    extract_tags as _extract_tags_normalized,
)
from cja_auto_sdr.core.discovery_normalization import (
    is_missing_value as _is_missing_discovery_value,
)
from cja_auto_sdr.core.discovery_normalization import (
    normalize_display_text as _normalize_display_text,
)
from cja_auto_sdr.core.discovery_normalization import (
    pick_first_present_text as _pick_first_present_text,
)
from cja_auto_sdr.core.discovery_payloads import (
    DataViewLookupAssessment as _DataViewLookupAssessment,
)
from cja_auto_sdr.core.discovery_payloads import (
    PayloadKind as _PayloadKind,
)
from cja_auto_sdr.core.discovery_payloads import (
    assess_component_payload as _assess_component_payload,
)
from cja_auto_sdr.core.discovery_payloads import (
    assess_dataview_lookup_payload as _assess_dataview_lookup_payload,
)
from cja_auto_sdr.core.discovery_payloads import (
    count_component_items_or_na as _count_component_items_or_na_from_assessment,
)
from cja_auto_sdr.core.exceptions import (
    APIError,
    CircuitBreakerOpen,
    CJASDRError,
    ConfigurationError,
    CredentialSourceError,
    OutputError,
    ProfileConfigError,
    ProfileError,
    ProfileNotFoundError,
    RetryableHTTPError,
    ValidationError,
)
from cja_auto_sdr.core.version import __version__
from cja_auto_sdr.org.analyzer import OrgComponentAnalyzer
from cja_auto_sdr.org.cache import DEFAULT_ORG_REPORT_SNAPSHOT_KEEP_LAST, OrgReportCache

# ==================== LEGACY DEFINITIONS REMOVED ====================
# The following sections have been moved to cja_auto_sdr.core:
# - Version (__version__) -> core/version.py
# - Exceptions (CJASDRError, etc.) -> core/exceptions.py
# - Config dataclasses (RetryConfig, etc.) -> core/config.py
# - Constants (FORMAT_ALIASES, etc.) -> core/constants.py
# - Colors (ConsoleColors, etc.) -> core/colors.py
#
# The following sections have been moved to cja_auto_sdr.api:
# - ErrorMessageHelper -> api/resilience.py
# - CircuitBreaker -> api/resilience.py
# - RETRYABLE_EXCEPTIONS -> api/resilience.py
# - retry_with_backoff -> api/resilience.py
# - make_api_call_with_retry -> api/resilience.py
#
# They are imported above for backwards compatibility.
# ==================== ORG-WIDE ANALYSIS IMPORTS ====================
# These were moved to cja_auto_sdr.org in v3.2.0
# They are re-exported here for backwards compatibility
from cja_auto_sdr.org.models import (
    ComponentDistribution,
    ComponentInfo,
    DataViewCluster,
    DataViewSummary,
    OrgReportComparison,
    OrgReportComparisonInput,
    OrgReportConfig,
    OrgReportResult,
    OrgReportTrending,
    SimilarityPair,
    build_org_report_comparison,
)

# ==================== LEGACY ORG-WIDE DEFINITIONS (REMOVED) ====================
# The following classes have been moved to cja_auto_sdr.org:
# - OrgReportConfig -> org/models.py
# - ComponentInfo -> org/models.py
# - DataViewSummary -> org/models.py
# - SimilarityPair -> org/models.py
# - DataViewCluster -> org/models.py
# - ComponentDistribution -> org/models.py
# - OrgReportResult -> org/models.py
# - OrgReportComparison -> org/models.py
# - OrgReportCache -> org/cache.py
# - OrgComponentAnalyzer -> org/analyzer.py
from cja_auto_sdr.org.writers import (
    _flatten_recommendation_for_tabular,
    _format_recommendation_context_entries,
    _normalize_org_report_output_format,
    _normalize_recommendation_for_json,
    _normalize_recommendation_severity,
    _render_distribution_bar,
    _validate_org_report_output_request,
    build_org_report_json_data,
    write_org_report_comparison_console,
    write_org_report_console,
    write_org_report_csv,
    write_org_report_excel,
    write_org_report_html,
    write_org_report_json,
    write_org_report_markdown,
    write_org_report_stats_only,
)

TQDM_BAR_FORMAT = "{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}]"
PARALLEL_INVENTORY_MIN_TASKS = 2

# ==================== OUTPUT WRITER PROTOCOL ====================


@runtime_checkable
class OutputWriter(Protocol):
    """Protocol defining the interface for output format writers.

    All output writers should implement this interface to ensure
    consistent behavior and enable easy addition of new formats.

    Example implementation:
        class CSVWriter:
            def write(
                self,
                metrics_df: pd.DataFrame,
                dimensions_df: pd.DataFrame,
                dataview_info: dict,
                output_path: Path,
                quality_results: list[dict[str, Any]] | None = None
            ) -> str:
                # Write CSV files and return output path
                ...
    """

    def write(
        self,
        metrics_df: pd.DataFrame,
        dimensions_df: pd.DataFrame,
        dataview_info: dict[str, Any],
        output_path: Path,
        quality_results: list[dict[str, Any]] | None = None,
    ) -> str:
        """Write output in the implemented format.

        Args:
            metrics_df: DataFrame containing metrics data
            dimensions_df: DataFrame containing dimensions data
            dataview_info: Dictionary with data view metadata
            output_path: Base path for output files
            quality_results: Optional list of data quality issues

        Returns:
            Path to the created output file(s)

        Raises:
            OutputError: If writing fails
        """
        ...


# Type alias for validation issues
ValidationIssue = dict[str, Any]
DATA_QUALITY_COLUMNS: tuple[str, ...] = (
    "Severity",
    "Category",
    "Type",
    "Item Name",
    "Issue",
    "Details",
)

# Stable failure identity values used in ProcessingResult and run summaries.
FAILURE_CODE_CJA_INIT_FAILED = "CJA_INIT_FAILED"
FAILURE_CODE_DATAVIEW_LOOKUP_INVALID = "DATAVIEW_LOOKUP_INVALID"
FAILURE_CODE_COMPONENT_FETCH_FAILED = "COMPONENT_FETCH_FAILED"
FAILURE_CODE_REQUIRED_COMPONENTS_EMPTY = "REQUIRED_COMPONENTS_EMPTY"
FAILURE_CODE_DQ_VALIDATION_RUNTIME_FAILED = "DQ_VALIDATION_RUNTIME_FAILED"
FAILURE_CODE_OUTPUT_PERMISSION_DENIED = "OUTPUT_PERMISSION_DENIED"
FAILURE_CODE_OUTPUT_WRITE_FAILED = "OUTPUT_WRITE_FAILED"
FAILURE_CODE_BATCH_WORKER_EXCEPTION = "BATCH_WORKER_EXCEPTION"
FAILURE_CODE_UNEXPECTED_RUNTIME_ERROR = "UNEXPECTED_RUNTIME_ERROR"
FAILURE_CODE_UNCLASSIFIED_FAILURE = "UNCLASSIFIED_FAILURE"
FAILURE_CODE_REGISTRY: tuple[str, ...] = (
    FAILURE_CODE_CJA_INIT_FAILED,
    FAILURE_CODE_DATAVIEW_LOOKUP_INVALID,
    FAILURE_CODE_COMPONENT_FETCH_FAILED,
    FAILURE_CODE_REQUIRED_COMPONENTS_EMPTY,
    FAILURE_CODE_DQ_VALIDATION_RUNTIME_FAILED,
    FAILURE_CODE_OUTPUT_PERMISSION_DENIED,
    FAILURE_CODE_OUTPUT_WRITE_FAILED,
    FAILURE_CODE_BATCH_WORKER_EXCEPTION,
    FAILURE_CODE_UNEXPECTED_RUNTIME_ERROR,
    FAILURE_CODE_UNCLASSIFIED_FAILURE,
)

RUN_SUMMARY_SCHEMA_VERSION = "1.1"

# Note: Constants, error formatting, and ConsoleColors have been moved to
# cja_auto_sdr.core and are imported above.
# Note: ErrorMessageHelper, CircuitBreaker, retry_with_backoff, and
# make_api_call_with_retry have been moved to cja_auto_sdr.api.resilience

# ==================== PLACEHOLDER FOR DELETED API RESILIENCE CODE ====================
# The following large section (ErrorMessageHelper, RetryableHTTPError, RETRYABLE_EXCEPTIONS,
# CircuitBreaker, retry_with_backoff, make_api_call_with_retry) has been moved to
# cja_auto_sdr.api.resilience and imported above.
# ==================== DATA STRUCTURES ====================


from cja_auto_sdr.pipeline.models import BatchConfig, ProcessingConfig, ProcessingResult, WorkerArgs


@dataclass(frozen=True)
class ProcessingExecutionPolicy:
    """Derived execution policy for fetch/validation fail-closed behavior."""

    requested_formats: frozenset[str]
    inventory_only_omits_standard_sections: bool
    emits_embedded_metadata: bool
    required_component_endpoints: frozenset[str]
    validation_required_for_output: bool
    run_data_quality_validation: bool


@dataclass(frozen=True)
class DataQualityValidationResult:
    """Structured data-quality validation outcome for single-data-view processing."""

    data_quality_df: pd.DataFrame
    dq_issues: list[ValidationIssue] = field(default_factory=list)
    severity_counts: dict[str, int] = field(default_factory=dict)
    status: str = "completed"
    status_detail: str = ""
    failed: bool = False
    error_message: str = ""


@dataclass(frozen=True)
class DiffConfig:
    """Configuration bundle for live data view diff comparisons."""

    source_id: str
    target_id: str
    config_file: str = "config.json"
    output_format: str = "console"
    output_dir: str = "."
    changes_only: bool = False
    summary_only: bool = False
    ignore_fields: list[str] | None = None
    labels: tuple[str, str] | None = None
    quiet: bool = False
    show_only: list[str] | None = None
    metrics_only: bool = False
    dimensions_only: bool = False
    extended_fields: bool = False
    side_by_side: bool = False
    no_color: bool = False
    quiet_diff: bool = False
    reverse_diff: bool = False
    warn_threshold: float | None = None
    group_by_field: bool = False
    group_by_field_limit: int = 10
    diff_output: str | None = None
    format_pr_comment: bool = False
    auto_snapshot: bool = False
    auto_prune: bool = False
    snapshot_dir: str = "./snapshots"
    keep_last: int = 0
    keep_since: str | None = None
    keep_last_specified: bool = False
    keep_since_specified: bool = False
    profile: str | None = None


@dataclass(frozen=True)
class DiffSnapshotConfig:
    """Configuration bundle for snapshot-vs-live diff comparisons."""

    data_view_id: str
    snapshot_file: str
    config_file: str = "config.json"
    output_format: str = "console"
    output_dir: str = "."
    changes_only: bool = False
    summary_only: bool = False
    ignore_fields: list[str] | None = None
    labels: tuple[str, str] | None = None
    quiet: bool = False
    show_only: list[str] | None = None
    metrics_only: bool = False
    dimensions_only: bool = False
    extended_fields: bool = False
    side_by_side: bool = False
    no_color: bool = False
    quiet_diff: bool = False
    reverse_diff: bool = False
    warn_threshold: float | None = None
    group_by_field: bool = False
    group_by_field_limit: int = 10
    diff_output: str | None = None
    format_pr_comment: bool = False
    auto_snapshot: bool = False
    auto_prune: bool = False
    snapshot_dir: str = "./snapshots"
    keep_last: int = 0
    keep_since: str | None = None
    keep_last_specified: bool = False
    keep_since_specified: bool = False
    profile: str | None = None
    include_calc_metrics: bool = False
    include_segments: bool = False


class RunMode(Enum):
    """CLI run modes used by dispatch and run summary classification."""

    EXIT_CODES = "exit_codes"
    COMPLETION = "completion"
    SAMPLE_CONFIG = "sample_config"
    PROFILE_MANAGEMENT = "profile_management"
    GIT_INIT = "git_init"
    DISCOVERY = "discovery"
    CONFIG_STATUS = "config_status"
    VALIDATE_CONFIG = "validate_config"
    STATS = "stats"
    ORG_REPORT_SNAPSHOTS = "org_report_snapshots"
    ORG_REPORT = "org_report"
    LIST_SNAPSHOTS = "list_snapshots"
    PRUNE_SNAPSHOTS = "prune_snapshots"
    COMPARE_SNAPSHOTS = "compare_snapshots"
    DIFF = "diff"
    SNAPSHOT = "snapshot"
    DIFF_SNAPSHOT = "diff_snapshot"
    DRY_RUN = "dry_run"
    INVENTORY_SUMMARY = "inventory_summary"
    SDR = "sdr"


def _coerce_run_mode(mode: Any) -> RunMode | None:
    """Convert a raw run mode value to RunMode when possible."""
    if isinstance(mode, RunMode):
        return mode
    if isinstance(mode, str):
        with contextlib.suppress(ValueError):
            return RunMode(mode)
    return None


def _exit_error(msg: str) -> NoReturn:
    """Print a coloured error message to stderr and exit with code 1."""
    print(ConsoleColors.error(f"ERROR: {msg}"), file=sys.stderr)
    sys.exit(1)


def _normalize_output_format(raw_format: Any) -> str | None:
    """Normalize CLI output format values defensively."""
    if raw_format is None:
        return None

    normalized = str(raw_format).strip().lower()
    return normalized or None


def _resolve_command_output_format(
    raw_format: Any,
    *,
    supported_formats: Mapping[str, str],
    fallback_format: str,
    warning_scope: str,
    logger: logging.Logger | None = None,
    output_to_stdout: bool = False,
    stdout_fallback_format: str | None = None,
    stdout_allowed_formats: Collection[str] | None = None,
) -> str:
    """Resolve requested output format to a supported command format.

    Args:
        raw_format: User-provided format token from CLI args.
        supported_formats: Mapping of accepted aliases to canonical format names.
        fallback_format: Canonical fallback format when input is missing/unsupported.
        warning_scope: Human-readable command scope for warning messages.
        logger: Optional logger for warning emissions.
        output_to_stdout: Whether command output is being piped to stdout.
        stdout_fallback_format: Fallback format override for stdout paths.
        stdout_allowed_formats: Canonical formats allowed for stdout output.
    """
    active_logger = logger or logging.getLogger(__name__)
    allowed_stdout_formats = tuple(dict.fromkeys(stdout_allowed_formats or ()))

    effective_fallback = fallback_format
    if output_to_stdout and stdout_fallback_format is not None:
        effective_fallback = stdout_fallback_format
    if output_to_stdout and allowed_stdout_formats and effective_fallback not in allowed_stdout_formats:
        effective_fallback = allowed_stdout_formats[0]

    normalized_format = _normalize_output_format(raw_format)
    if normalized_format is None:
        return effective_fallback

    resolved_format = supported_formats.get(normalized_format)
    if resolved_format is None:
        active_logger.warning(
            "--format %s is not supported for %s; using %s",
            raw_format,
            warning_scope,
            effective_fallback,
        )
        return effective_fallback

    if output_to_stdout and allowed_stdout_formats and resolved_format not in allowed_stdout_formats:
        active_logger.warning(
            "--format %s is not supported for %s with --output stdout; using %s",
            raw_format,
            warning_scope,
            effective_fallback,
        )
        return effective_fallback

    return resolved_format


def _print_error_list_to_stderr(
    header: str, details: list[Any], *, fallback_detail: str = "Unknown validation error"
) -> None:
    """Emit an error header and detail lines to stderr using one consistent stream."""
    print(ConsoleColors.error(header), file=sys.stderr)

    emitted_detail = False
    for detail in details:
        detail_text = str(detail).strip()
        if not detail_text:
            continue
        print(ConsoleColors.error(f"  - {detail_text}"), file=sys.stderr)
        emitted_detail = True

    if not emitted_detail:
        print(ConsoleColors.error(f"  - {fallback_detail}"), file=sys.stderr)


def _cli_option_specified(option_name: str, argv: list[str] | None = None) -> bool:
    """Return True if an option was explicitly provided via long-form token.

    Accepts canonical forms (`--flag`, `--flag=value`) and argparse-compatible
    long-option abbreviations (`--fla`, `--fla=value`) for the same option.
    """
    tokens = argv if argv is not None else sys.argv[1:]

    known_long_options = _known_long_options() if option_name.startswith("--") else frozenset()

    for token in tokens:
        if token == option_name or token.startswith(f"{option_name}="):
            return True

        if (
            option_name.startswith("--")
            and _resolve_long_option_token(token, known_long_options).canonical_option == option_name
        ):
            return True

    return False


@lru_cache(maxsize=1)
def _known_long_options() -> frozenset[str]:
    """Return canonical long-option strings from the configured parser."""
    parser = parse_arguments(return_parser=True, enable_autocomplete=False)
    # CPython argparse internals: `_actions` is the parser's canonical option
    # registry and keeps this aligned with argparse abbreviation semantics.
    return frozenset(
        option for action in parser._actions for option in action.option_strings if option.startswith("--")
    )


def _cli_option_value(option_name: str, argv: list[str] | None = None) -> str | None:
    """Return the last valid value for --option VALUE or --option=VALUE from argv.

    This helper is intentionally conservative: for `--option VALUE` forms it
    ignores candidates that look like another long/short option (except `-`,
    which is a valid stdout token for some flags).
    """
    tokens = argv if argv is not None else sys.argv[1:]
    resolved_value: str | None = None
    known_long_options = _known_long_options() if option_name.startswith("--") else frozenset()

    for index, token in enumerate(tokens):
        canonical_option: str | None = None
        inline_value: str | None = None

        if token == option_name:
            canonical_option = option_name
        elif token.startswith(f"{option_name}="):
            canonical_option = option_name
            inline_value = token.split("=", 1)[1]
        elif option_name.startswith("--"):
            resolved_option = _resolve_long_option_token(token, known_long_options).canonical_option
            if resolved_option == option_name:
                canonical_option = option_name
                if "=" in token:
                    inline_value = token.split("=", 1)[1]

        if canonical_option != option_name:
            continue

        if inline_value is not None:
            if inline_value:
                resolved_value = inline_value
            continue

        if index + 1 >= len(tokens):
            continue

        candidate = tokens[index + 1]
        if candidate != "-" and candidate.startswith("-"):
            # Looks like another flag, so treat this occurrence as invalid.
            continue
        resolved_value = candidate

    return resolved_value


# QUALITY_REPORT_PREFERRED_COLUMNS -> api/quality_policy.py (re-imported above)
# QUALITY_POLICY_ALLOWED_KEYS -> api/quality_policy.py (re-imported above)

# Recoverable API/runtime failures that should surface as user-facing command
# errors (not uncaught tracebacks). Keep this centralized to avoid accidental
# exception narrowing drift across CLI command handlers.
RECOVERABLE_API_EXCEPTIONS: tuple[type[Exception], ...] = (
    APIError,
    RetryableHTTPError,
    OSError,
    AttributeError,
    KeyError,
    TypeError,
    ValueError,
)
RECOVERABLE_CONFIG_API_EXCEPTIONS: tuple[type[Exception], ...] = (
    ConfigurationError,
    *RECOVERABLE_API_EXCEPTIONS,
)
RECOVERABLE_BATCH_WORKER_EXCEPTIONS: tuple[type[Exception], ...] = (
    BrokenProcessPool,
    CJASDRError,
    *RECOVERABLE_API_EXCEPTIONS,
)
RECOVERABLE_ORG_REPORT_EXCEPTIONS: tuple[type[Exception], ...] = (
    CJASDRError,
    *RECOVERABLE_CONFIG_API_EXCEPTIONS,
)
# Final guard for CLI command handlers. Some runtime/auth/bootstrap failures
# from third-party dependencies (notably cjapy) still surface as plain
# `Exception`; command boundaries should return controlled failures, not
# tracebacks.
#
# Prefer the tiered pattern used in handle_compare_snapshots_command()
# (FileNotFoundError -> ValueError -> CJASDRError|OSError -> Exception)
# for new command handlers to preserve differentiated user messaging.
RECOVERABLE_COMMAND_HANDLER_EXCEPTIONS: tuple[type[Exception], ...] = (
    CJASDRError,
    *RECOVERABLE_CONFIG_API_EXCEPTIONS,
    Exception,
)
# Recoverable failures during optional inventory collection. These code paths
# are best-effort and must never fail the primary SDR/inventory-summary flow.
# Keep this broad by design to protect command robustness against unexpected
# third-party or builder regressions while still allowing BaseException
# subclasses (e.g., KeyboardInterrupt/SystemExit) to propagate.
RECOVERABLE_OPTIONAL_INVENTORY_EXCEPTIONS: tuple[type[Exception], ...] = (Exception,)
RECOVERABLE_INVENTORY_SUMMARY_EXCEPTIONS: tuple[type[Exception], ...] = RECOVERABLE_OPTIONAL_INVENTORY_EXCEPTIONS
# Optional git snapshot re-fetch runs after successful SDR generation and must
# not terminate the command. Keep broad to preserve graceful degradation.
RECOVERABLE_GIT_SNAPSHOT_REFETCH_EXCEPTIONS: tuple[type[Exception], ...] = (Exception,)
# Data quality validation runs at a fail-closed boundary for SDR generation.
# Catch broad Exception here to return a controlled failed ProcessingResult.
VALIDATION_CATCH_BOUNDARY_EXCEPTIONS: tuple[type[Exception], ...] = (Exception,)
# Backwards-compatible alias for external imports that referenced the old name.
RECOVERABLE_VALIDATION_EXCEPTIONS: tuple[type[Exception], ...] = VALIDATION_CATCH_BOUNDARY_EXCEPTIONS
# Per-item stats collection must be fully resilient: one broken DV must never
# abort the stats command. Intentionally broad.
RECOVERABLE_STATS_ROW_EXCEPTIONS: tuple[type[Exception], ...] = (Exception,)
# Optional component-count lookups (dry-run projections, describe metadata) are
# best-effort. Any Exception should degrade to a fallback count instead of
# terminating the command flow.
RECOVERABLE_OPTIONAL_COMPONENT_COUNT_EXCEPTIONS: tuple[type[Exception], ...] = (Exception,)


def _log_optional_inventory_failure(
    logger: Any,
    *,
    inventory_label: str,
    error: Exception,
    summary_mode: bool,
) -> None:
    """Log non-fatal optional inventory failures consistently."""
    if summary_mode:
        logger.warning(f"Failed to build {inventory_label}: {error}")
    else:
        logger.error(_format_error_msg(f"during {inventory_label}", error=error))
        logger.info(f"Continuing with SDR generation despite {inventory_label} errors")
    logger.debug(f"Optional inventory failure details: {error!r}")


def _log_validation_failure(logger: Any, *, error: Exception) -> None:
    """Log fatal validation failures consistently."""
    logger.error(_format_error_msg("during data quality validation", error=error))
    logger.info("Aborting SDR generation because data quality validation did not complete")
    logger.debug(f"Validation failure details: {error!r}")


def _empty_data_quality_dataframe() -> pd.DataFrame:
    """Return an empty, schema-consistent data-quality dataframe."""
    return pd.DataFrame(columns=list(DATA_QUALITY_COLUMNS))


def _collect_data_quality_results(
    *,
    dq_checker: Any,
    max_issues: int,
) -> tuple[pd.DataFrame, list[ValidationIssue], dict[str, int]]:
    """Collect data-quality dataframe payloads with defensive shape/type checks."""
    data_quality_df = dq_checker.get_issues_dataframe(max_issues=max_issues)
    if not isinstance(data_quality_df, pd.DataFrame):
        raise TypeError(
            f"Data quality checker returned non-DataFrame payload ({type(data_quality_df).__name__})",
        )

    dq_issues = data_quality_df.to_dict(orient="records") if dq_checker.issues else []
    severity_counts = count_quality_issues_by_severity(dq_issues)
    return data_quality_df, dq_issues, severity_counts


def _run_data_quality_validation(
    *,
    logger: Any,
    perf_tracker: Any,
    metrics: pd.DataFrame,
    dimensions: pd.DataFrame,
    quiet: bool,
    production_mode: bool,
    shared_cache: Any,
    enable_cache: bool,
    cache_size: int,
    cache_ttl: int,
    clear_cache: bool,
    max_issues: int,
    skip_validation: bool,
    execution_policy: ProcessingExecutionPolicy,
) -> DataQualityValidationResult:
    """Execute validation and issue extraction with fail-closed semantics."""
    if not execution_policy.run_data_quality_validation:
        if skip_validation:
            status_detail = "Skipped (--skip-validation)"
        else:
            status_detail = "Skipped (data quality validation is not part of the requested output contract)"
        logger.info("=" * BANNER_WIDTH)
        if skip_validation:
            logger.info("Skipping data quality validation (--skip-validation)")
        else:
            logger.info(
                "Skipping data quality validation (not emitted for inventory-only %s output)",
                ", ".join(sorted(execution_policy.requested_formats)),
            )
        logger.info("=" * BANNER_WIDTH)
        return DataQualityValidationResult(
            data_quality_df=_empty_data_quality_dataframe(),
            status="skipped",
            status_detail=status_detail,
        )

    logger.info("=" * BANNER_WIDTH)
    logger.info("Starting data quality validation (optimized)")
    logger.info("=" * BANNER_WIDTH)

    perf_tracker.start("Data Quality Validation")
    try:
        # Create validation cache if enabled.
        # Use shared cache if provided (from batch processing), otherwise create local cache.
        validation_cache = None
        if shared_cache is not None:
            validation_cache = shared_cache
            logger.info("Using shared validation cache from batch processor")
        elif enable_cache:
            validation_cache = ValidationCache(max_size=cache_size, ttl_seconds=cache_ttl, logger=logger)
            if clear_cache:
                validation_cache.clear()
                logger.info(f"Validation cache cleared and enabled (max_size={cache_size}, ttl={cache_ttl}s)")
            else:
                logger.info(f"Validation cache enabled (max_size={cache_size}, ttl={cache_ttl}s)")

        dq_checker = DataQualityChecker(
            logger,
            validation_cache=validation_cache,
            quiet=quiet,
            log_high_severity_issues=not production_mode,
        )

        # Run parallel data quality checks (10-15% faster than sequential).
        logger.info("Running parallel data quality checks...")
        dq_checker.check_all_parallel(
            metrics_df=metrics,
            dimensions_df=dimensions,
            metrics_required_fields=VALIDATION_SCHEMA["required_metric_fields"],
            dimensions_required_fields=VALIDATION_SCHEMA["required_dimension_fields"],
            critical_fields=VALIDATION_SCHEMA["critical_fields"],
            max_workers=DEFAULT_VALIDATION_WORKERS,
        )
        dq_checker.log_summary()

        # Log cache statistics if cache was used.
        if validation_cache is not None:
            perf_tracker.add_cache_statistics(validation_cache)

        data_quality_df, dq_issues, severity_counts = _collect_data_quality_results(
            dq_checker=dq_checker,
            max_issues=max_issues,
        )
        return DataQualityValidationResult(
            data_quality_df=data_quality_df,
            dq_issues=dq_issues,
            severity_counts=severity_counts,
            status="completed",
            status_detail="Completed",
        )
    except VALIDATION_CATCH_BOUNDARY_EXCEPTIONS as e:
        _log_validation_failure(logger, error=e)
        return DataQualityValidationResult(
            data_quality_df=_empty_data_quality_dataframe(),
            status="failed",
            status_detail=f"Failed ({e})",
            failed=True,
            error_message=str(e),
        )
    finally:
        perf_tracker.end("Data Quality Validation")


def _resolve_requested_output_formats(output_format: str) -> frozenset[str]:
    """Resolve output aliases into concrete format names."""
    if output_format == "all":
        return frozenset({"excel", "csv", "json", "html", "markdown"})
    if output_format in FORMAT_ALIASES:
        return frozenset(str(fmt) for fmt in FORMAT_ALIASES[output_format])
    return frozenset({output_format})


STANDARD_COMPONENT_ENDPOINTS: frozenset[str] = frozenset({"metrics", "dimensions"})
EMBEDDED_METADATA_FORMATS: frozenset[str] = frozenset({"json", "html", "markdown"})


def _should_emit_standard_sdr_sections(*, inventory_only: bool) -> bool:
    """Return whether this run emits standard SDR sections (metadata/quality/components)."""
    # Inventory-only mode always excludes standard SDR sections from output payloads.
    return not inventory_only


def _resolve_standard_component_requirements(*, metrics_only: bool, dimensions_only: bool) -> frozenset[str]:
    """Resolve required standard component endpoints for non-inventory-only SDR runs."""
    if metrics_only and dimensions_only:
        return STANDARD_COMPONENT_ENDPOINTS

    required_component_endpoints: set[str] = set()
    if not dimensions_only:
        required_component_endpoints.add("metrics")
    if not metrics_only:
        required_component_endpoints.add("dimensions")
    return frozenset(required_component_endpoints)


def _resolve_required_component_endpoints(
    *,
    inventory_only: bool,
    include_derived_inventory: bool,
    metrics_only: bool,
    dimensions_only: bool,
    quality_report_only: bool,
) -> frozenset[str]:
    """Resolve component endpoints that must fail-closed for this run."""
    if quality_report_only:
        return STANDARD_COMPONENT_ENDPOINTS
    if include_derived_inventory:
        # Derived inventory always depends on both component payloads.
        return STANDARD_COMPONENT_ENDPOINTS
    if not _should_emit_standard_sdr_sections(inventory_only=inventory_only):
        return frozenset()
    return _resolve_standard_component_requirements(
        metrics_only=metrics_only,
        dimensions_only=dimensions_only,
    )


def _build_processing_execution_policy(
    *,
    output_format: str,
    inventory_only: bool,
    include_derived_inventory: bool,
    metrics_only: bool,
    dimensions_only: bool,
    quality_report_only: bool,
    skip_validation: bool,
) -> ProcessingExecutionPolicy:
    """Determine which fetch/validation failures must be fail-closed for this run."""
    requested_formats = _resolve_requested_output_formats(output_format)
    emits_standard_sdr_sections = _should_emit_standard_sdr_sections(inventory_only=inventory_only)
    inventory_only_omits_standard_sections = not emits_standard_sdr_sections
    emits_embedded_metadata = bool(requested_formats & EMBEDDED_METADATA_FORMATS)

    required_component_endpoints = _resolve_required_component_endpoints(
        inventory_only=inventory_only,
        include_derived_inventory=include_derived_inventory,
        metrics_only=metrics_only,
        dimensions_only=dimensions_only,
        quality_report_only=quality_report_only,
    )

    validation_required_for_output = quality_report_only or emits_standard_sdr_sections
    run_data_quality_validation = validation_required_for_output and not skip_validation

    return ProcessingExecutionPolicy(
        requested_formats=requested_formats,
        inventory_only_omits_standard_sections=inventory_only_omits_standard_sections,
        emits_embedded_metadata=emits_embedded_metadata,
        required_component_endpoints=required_component_endpoints,
        validation_required_for_output=validation_required_for_output,
        run_data_quality_validation=run_data_quality_validation,
    )


def _resolve_empty_required_component_endpoints(
    *,
    required_component_endpoints: Collection[str],
    metrics: pd.DataFrame,
    dimensions: pd.DataFrame,
    fetch_statuses: Mapping[str, Any],
) -> list[str]:
    """Return required component endpoints whose fetched payloads are empty."""
    component_frames = {
        "metrics": metrics,
        "dimensions": dimensions,
    }
    empty_required_components: list[str] = []
    for endpoint in sorted(required_component_endpoints):
        status = fetch_statuses.get(endpoint)
        if str(getattr(status, "status", "")).lower() == "failed":
            continue
        frame = component_frames.get(endpoint)
        if isinstance(frame, pd.DataFrame) and frame.empty:
            empty_required_components.append(endpoint)
    return empty_required_components


def _resolve_component_metadata_values(
    *,
    endpoint: str,
    dataframe: pd.DataFrame,
    breakdown: list[str],
    fetch_statuses: Mapping[str, Any],
) -> tuple[int | str, str]:
    """Build truthful metadata values for a component count and breakdown."""
    status = fetch_statuses.get(endpoint)
    endpoint_status = str(getattr(status, "status", "")).lower()
    failure_detail = str(getattr(status, "error_message", "")) or str(getattr(status, "reason", ""))
    if endpoint_status == "failed":
        unavailable_detail = f"Unavailable ({endpoint} fetch failed"
        if failure_detail:
            unavailable_detail += f": {failure_detail}"
        unavailable_detail += ")"
        return unavailable_detail, unavailable_detail

    component_label = endpoint.replace("_", " ")
    empty_message = f"No {component_label} found"
    return len(dataframe), "\n".join(breakdown) if breakdown else empty_message


def _resolve_validation_metadata_values(
    *,
    validation_status: str,
    validation_status_detail: str,
    dq_issues: Collection[Mapping[str, Any]],
    severity_counts: Mapping[str, int],
) -> tuple[str, int | str, str]:
    """Build truthful metadata values for validation status and issue summary."""
    if validation_status == "completed":
        dq_summary = [f"{sev}: {count}" for sev, count in severity_counts.items()]
        return "Completed", len(dq_issues), "\n".join(dq_summary) if dq_summary else "No issues"
    if validation_status == "failed":
        return "Failed", "Unavailable", validation_status_detail or "Validation failed"
    return "Skipped", "Not run", validation_status_detail or "Validation skipped"


def _build_sdr_metadata_dataframe(
    *,
    data_view_id: str,
    lookup_data: Mapping[str, Any] | None,
    metrics: pd.DataFrame,
    dimensions: pd.DataFrame,
    fetch_statuses: Mapping[str, Any],
    validation_status: str,
    validation_status_detail: str,
    dq_issues: Collection[Mapping[str, Any]],
    severity_counts: Mapping[str, int],
    partial_reasons: Iterable[str] | None,
    segments_inventory_obj: Any,
    calculated_inventory_obj: Any,
    derived_inventory_obj: Any,
) -> pd.DataFrame:
    """Build the metadata DataFrame for SDR artifacts."""
    metric_types = metrics["type"].value_counts().to_dict() if not metrics.empty and "type" in metrics.columns else {}
    metric_summary = [f"{type_}: {count}" for type_, count in metric_types.items()]

    dimension_types = (
        dimensions["type"].value_counts().to_dict() if not dimensions.empty and "type" in dimensions.columns else {}
    )
    dimension_summary = [f"{type_}: {count}" for type_, count in dimension_types.items()]

    local_tz = datetime.now(UTC).astimezone().tzinfo
    current_time = datetime.now(local_tz)
    formatted_timestamp = current_time.strftime("%Y-%m-%d %H:%M:%S %Z")

    metrics_count_value, metrics_breakdown_value = _resolve_component_metadata_values(
        endpoint="metrics",
        dataframe=metrics,
        breakdown=metric_summary,
        fetch_statuses=fetch_statuses,
    )
    dimensions_count_value, dimensions_breakdown_value = _resolve_component_metadata_values(
        endpoint="dimensions",
        dataframe=dimensions,
        breakdown=dimension_summary,
        fetch_statuses=fetch_statuses,
    )
    validation_status_value, dq_issues_value, dq_summary_value = _resolve_validation_metadata_values(
        validation_status=validation_status,
        validation_status_detail=validation_status_detail,
        dq_issues=dq_issues,
        severity_counts=severity_counts,
    )

    metadata_properties = [
        "Generated Date & timestamp and timezone",
        "Data View ID",
        "Data View Name",
        "Total Metrics",
        "Metrics Breakdown",
        "Total Dimensions",
        "Dimensions Breakdown",
        "Data Quality Validation Status",
        "Data Quality Issues",
        "Data Quality Summary",
    ]
    metadata_values = [
        formatted_timestamp,
        data_view_id,
        lookup_data.get("name", "Unknown") if isinstance(lookup_data, Mapping) else "Unknown",
        metrics_count_value,
        metrics_breakdown_value,
        dimensions_count_value,
        dimensions_breakdown_value,
        validation_status_value,
        dq_issues_value,
        dq_summary_value,
    ]

    normalized_partial_output, normalized_partial_reasons = _normalize_partial_state(False, partial_reasons)
    if normalized_partial_output:
        metadata_properties.extend(["Partial Output", "Partial Reasons"])
        metadata_values.extend(["Yes", ", ".join(normalized_partial_reasons)])

    if segments_inventory_obj or calculated_inventory_obj or derived_inventory_obj:
        metadata_properties.append("--- Inventory Statistics ---")
        metadata_values.append("")

    if segments_inventory_obj:
        seg_summary = segments_inventory_obj.get_summary()
        seg_count = seg_summary.get("total_segments", 0)
        seg_complexity = seg_summary.get("complexity", {})
        seg_high = seg_complexity.get("high_complexity_count", 0)
        seg_elevated = seg_complexity.get("elevated_complexity_count", 0)
        seg_avg = seg_complexity.get("average", 0)
        seg_max = seg_complexity.get("max", 0)
        metadata_properties.extend(
            [
                "Segments Count",
                "Segments Complexity (Avg / Max)",
                "Segments High Complexity (≥75)",
                "Segments Elevated Complexity (50-74)",
            ],
        )
        metadata_values.extend([seg_count, f"{seg_avg:.1f} / {seg_max:.1f}", seg_high, seg_elevated])

    if calculated_inventory_obj:
        calc_summary = calculated_inventory_obj.get_summary()
        calc_count = calc_summary.get("total_calculated_metrics", 0)
        calc_complexity = calc_summary.get("complexity", {})
        calc_high = calc_complexity.get("high_complexity_count", 0)
        calc_elevated = calc_complexity.get("elevated_complexity_count", 0)
        calc_avg = calc_complexity.get("average", 0)
        calc_max = calc_complexity.get("max", 0)
        metadata_properties.extend(
            [
                "Calculated Metrics Count",
                "Calculated Metrics Complexity (Avg / Max)",
                "Calculated Metrics High Complexity (≥75)",
                "Calculated Metrics Elevated Complexity (50-74)",
            ],
        )
        metadata_values.extend([calc_count, f"{calc_avg:.1f} / {calc_max:.1f}", calc_high, calc_elevated])

    if derived_inventory_obj:
        derived_summary = derived_inventory_obj.get_summary()
        derived_count = derived_summary.get("total_derived_fields", 0)
        derived_metrics = derived_summary.get("metrics_count", 0)
        derived_dimensions = derived_summary.get("dimensions_count", 0)
        derived_complexity = derived_summary.get("complexity", {})
        derived_high = derived_complexity.get("high_complexity_count", 0)
        derived_elevated = derived_complexity.get("elevated_complexity_count", 0)
        derived_avg = derived_complexity.get("average", 0)
        derived_max = derived_complexity.get("max", 0)
        metadata_properties.extend(
            [
                "Derived Fields Count",
                "Derived Fields Breakdown",
                "Derived Fields Complexity (Avg / Max)",
                "Derived Fields High Complexity (≥75)",
                "Derived Fields Elevated Complexity (50-74)",
            ],
        )
        metadata_values.extend(
            [
                derived_count,
                f"Metrics: {derived_metrics}, Dimensions: {derived_dimensions}",
                f"{derived_avg:.1f} / {derived_max:.1f}",
                derived_high,
                derived_elevated,
            ],
        )

    return pd.DataFrame({"Property": metadata_properties, "Value": metadata_values})


def _metadata_dataframe_to_dict(metadata_df: pd.DataFrame) -> dict[str, Any]:
    """Convert metadata DataFrame into embedded metadata dict form."""
    if metadata_df.empty:
        return {}
    return metadata_df.set_index(metadata_df.columns[0])[metadata_df.columns[1]].to_dict()


def _run_optional_inventory_step[T](
    *,
    logger: Any,
    inventory_label: str,
    summary_mode: bool,
    build_inventory: Callable[[], T],
    recoverable_exceptions: tuple[type[Exception], ...] = RECOVERABLE_OPTIONAL_INVENTORY_EXCEPTIONS,
    on_import_error: Callable[[ImportError], None] | None = None,
) -> T | None:
    """Run best-effort optional inventory logic without aborting the primary command flow."""
    try:
        return build_inventory()
    except ImportError as e:
        if on_import_error is not None:
            on_import_error(e)
        else:
            _log_optional_inventory_failure(
                logger,
                inventory_label=inventory_label,
                error=e,
                summary_mode=summary_mode,
            )
        logger.debug(f"Optional inventory import failure details: {e!r}")
    except recoverable_exceptions as e:
        _log_optional_inventory_failure(
            logger,
            inventory_label=inventory_label,
            error=e,
            summary_mode=summary_mode,
        )
    return None


def _refetch_git_snapshot_for_commit(
    *,
    snapshot: DataViewSnapshot,
    data_view_id: str,
    config_file: str,
    profile: str | None,
    include_calculated_metrics: bool,
    include_segments_inventory: bool,
) -> DataViewSnapshot:
    """Best-effort snapshot re-fetch used by optional --git-commit flow."""
    needs_fetch = not snapshot.metrics and not snapshot.dimensions
    needs_inventory = include_calculated_metrics or include_segments_inventory
    if not (needs_fetch or needs_inventory):
        return snapshot

    fetch_reason = "inventory" if needs_inventory and not needs_fetch else "data"
    print(f"Fetching {fetch_reason} for Git snapshot...")
    try:
        temp_logger = logging.getLogger("git_snapshot")
        temp_logger.setLevel(logging.WARNING)
        cja = initialize_cja(config_file, temp_logger, profile=profile)
        if cja:
            snapshot_mgr = SnapshotManager(temp_logger)
            return snapshot_mgr.create_snapshot(
                cja,
                data_view_id,
                quiet=True,
                include_calculated_metrics=include_calculated_metrics,
                include_segments=include_segments_inventory,
            )
    except RECOVERABLE_GIT_SNAPSHOT_REFETCH_EXCEPTIONS as e:
        print(ConsoleColors.warning(f"  Could not fetch snapshot data: {e}"))
    return snapshot


# Quality policy helpers -> api/quality_policy.py (re-imported above):
# _canonical_quality_policy_key, _parse_non_negative_policy_int,
# _parse_boolean_policy_flag, load_quality_policy, apply_quality_policy_defaults,
# normalize_quality_severity, count_quality_issues_by_severity,
# has_quality_issues_at_or_above


def aggregate_quality_issues(results: list[ProcessingResult]) -> list[dict[str, Any]]:
    """Flatten quality issues across processing results with data view context."""
    issues: list[dict[str, Any]] = []
    for result in results:
        for issue in result.dq_issues:
            issue_with_context = dict(issue)
            issue_with_context.setdefault("Data View ID", result.data_view_id)
            issue_with_context.setdefault("Data View Name", result.data_view_name)
            issues.append(issue_with_context)
    return issues


def resolve_auto_prune_retention(
    keep_last: int,
    keep_since: str | None,
    auto_prune: bool,
    keep_last_specified: bool = False,
    keep_since_specified: bool = False,
) -> tuple[int, str | None]:
    """Resolve effective retention settings for auto-prune defaults.

    Defaults are applied only when both retention flags were omitted.
    Explicit values (including --keep-last 0) are preserved.
    """
    effective_keep_last = keep_last
    effective_keep_since = keep_since

    if auto_prune and not keep_last_specified and not keep_since_specified:
        if effective_keep_last <= 0:
            effective_keep_last = DEFAULT_AUTO_PRUNE_KEEP_LAST
        if not effective_keep_since:
            effective_keep_since = DEFAULT_AUTO_PRUNE_KEEP_SINCE

    return effective_keep_last, effective_keep_since


# _build_quality_report_dataframe, write_quality_report_output -> api/quality_policy.py (re-imported above)


def _normalize_exit_code(code: Any) -> int:
    """Normalize SystemExit.code or arbitrary values to an integer exit code."""
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    if isinstance(code, bool):
        return int(code)
    return 1


def _infer_run_status(exit_code: int, run_state: dict[str, Any]) -> str:
    """Classify run summary status based on known policy paths, not raw exit code alone."""
    if exit_code == 0:
        return "success"

    details = run_state.get("details") or {}
    mode = _coerce_run_mode(run_state.get("mode"))
    operation_success = details.get("operation_success")

    # SDR quality gate
    if bool(run_state.get("quality_gate_failed", False)) and exit_code == 2:
        return "policy_exit"

    # Org governance threshold gate
    if (
        mode == RunMode.ORG_REPORT
        and exit_code == 2
        and bool(details.get("thresholds_exceeded"))
        and bool(details.get("fail_on_threshold"))
    ):
        return "policy_exit"

    # Diff family policy exits (changes found or warn-threshold exit 3)
    if (
        mode in {RunMode.DIFF, RunMode.DIFF_SNAPSHOT, RunMode.COMPARE_SNAPSHOTS}
        and operation_success is True
        and exit_code in (2, 3)
    ):
        return "policy_exit"

    return "error"


def _run_mode_checks(args: argparse.Namespace) -> tuple[tuple[RunMode, bool], ...]:
    """Build run-mode checks once so inference and validation share precedence."""
    completion_shell = _completion_shell_from_args(args)
    return (
        (RunMode.EXIT_CODES, getattr(args, "exit_codes", False)),
        (RunMode.COMPLETION, completion_shell is not None),
        (RunMode.SAMPLE_CONFIG, getattr(args, "sample_config", False)),
        (
            RunMode.PROFILE_MANAGEMENT,
            bool(
                getattr(args, "profile_list", False)
                or getattr(args, "profile_add", None)
                or getattr(args, "profile_test", None)
                or getattr(args, "profile_import", None)
                or getattr(args, "profile_show", None)
                or getattr(args, "profile_overwrite", False),
            ),
        ),
        (RunMode.GIT_INIT, getattr(args, "git_init", False)),
        (
            RunMode.DISCOVERY,
            bool(
                getattr(args, "list_dataviews", False)
                or getattr(args, "list_connections", False)
                or getattr(args, "list_datasets", False)
                or getattr(args, "describe_dataview", None)
                or getattr(args, "list_metrics", None)
                or getattr(args, "list_dimensions", None)
                or getattr(args, "list_segments", None)
                or getattr(args, "list_calculated_metrics", None)
            ),
        ),
        (RunMode.CONFIG_STATUS, bool(getattr(args, "config_status", False) or getattr(args, "config_json", False))),
        (RunMode.VALIDATE_CONFIG, getattr(args, "validate_config", False)),
        (RunMode.STATS, getattr(args, "stats", False)),
        (
            RunMode.ORG_REPORT_SNAPSHOTS,
            bool(
                getattr(args, "list_org_report_snapshots", False)
                or getattr(args, "inspect_org_report_snapshot", None)
                or getattr(args, "prune_org_report_snapshots", False)
            ),
        ),
        (RunMode.ORG_REPORT, getattr(args, "org_report", False)),
        (RunMode.LIST_SNAPSHOTS, getattr(args, "list_snapshots", False)),
        (RunMode.PRUNE_SNAPSHOTS, getattr(args, "prune_snapshots", False)),
        (RunMode.COMPARE_SNAPSHOTS, bool(getattr(args, "compare_snapshots", None))),
        (RunMode.DIFF, getattr(args, "diff", False)),
        (RunMode.SNAPSHOT, bool(getattr(args, "snapshot", None))),
        (
            RunMode.DIFF_SNAPSHOT,
            bool(getattr(args, "compare_with_prev", False) or getattr(args, "diff_snapshot", None)),
        ),
        (RunMode.DRY_RUN, getattr(args, "dry_run", False)),
        (RunMode.INVENTORY_SUMMARY, getattr(args, "inventory_summary", False)),
    )


def _infer_run_mode_enum(args: argparse.Namespace) -> RunMode:
    """Infer run mode using the same precedence as command dispatch in _main_impl."""
    for mode, is_active in _run_mode_checks(args):
        if is_active:
            return mode
    return RunMode.SDR


def _active_run_modes(args: argparse.Namespace) -> list[RunMode]:
    """Return all active primary run modes for defensive conflict validation."""
    return [mode for mode, is_active in _run_mode_checks(args) if is_active]


def _org_report_snapshot_retention_flags_specified(argv: list[str] | None = None) -> tuple[bool, bool]:
    """Return whether org-report snapshot retention flags were explicitly provided."""
    return (
        _cli_option_specified("--org-report-keep-last", argv=argv),
        _cli_option_specified("--org-report-keep-since", argv=argv),
    )


def _validate_org_report_snapshot_cli_args(
    args: argparse.Namespace,
    *,
    active_modes: Collection[RunMode],
) -> None:
    """Fail closed for mixed or unsupported org-report snapshot maintenance invocations."""
    snapshot_actions = (
        ("--list-org-report-snapshots", bool(getattr(args, "list_org_report_snapshots", False))),
        ("--inspect-org-report-snapshot", bool(getattr(args, "inspect_org_report_snapshot", None))),
        ("--prune-org-report-snapshots", bool(getattr(args, "prune_org_report_snapshots", False))),
    )
    active_actions = [label for label, is_active in snapshot_actions if is_active]
    if not active_actions:
        return

    if len(active_actions) > 1:
        _exit_error(
            "Use only one of --list-org-report-snapshots, --inspect-org-report-snapshot, or --prune-org-report-snapshots",
        )

    conflicting_modes = sorted(
        {mode for mode in active_modes if mode != RunMode.ORG_REPORT_SNAPSHOTS}, key=lambda m: m.value
    )
    if conflicting_modes:
        if conflicting_modes == [RunMode.ORG_REPORT]:
            _exit_error("Org-report snapshot maintenance commands cannot be combined with --org-report")
        conflict_labels = ", ".join(mode.value for mode in conflicting_modes)
        _exit_error(
            f"Org-report snapshot maintenance commands cannot be combined with other command modes ({conflict_labels})",
        )

    if getattr(args, "data_views", []):
        _exit_error("Org-report snapshot maintenance commands do not accept positional data view arguments")

    if getattr(args, "inspect_org_report_snapshot", None) and getattr(args, "org_report_snapshot_org", None):
        _exit_error(
            "--org-report-snapshot-org can only be used with --list-org-report-snapshots or --prune-org-report-snapshots",
        )

    keep_last_specified, keep_since_specified = _org_report_snapshot_retention_flags_specified()
    effective_keep_last = getattr(args, "org_report_keep_last", 0)
    if keep_last_specified and effective_keep_last < 0:
        _exit_error("--org-report-keep-last cannot be negative")

    if not getattr(args, "prune_org_report_snapshots", False) and (keep_last_specified or keep_since_specified):
        _exit_error(
            "--org-report-keep-last and --org-report-keep-since are only supported with --prune-org-report-snapshots",
        )


def _completion_shell_from_args(args: argparse.Namespace) -> str | None:
    """Return normalized completion shell from parsed args, if present."""
    raw_completion = getattr(args, "completion", None)
    if not isinstance(raw_completion, str):
        return None
    normalized = raw_completion.strip().lower()
    return normalized or None


def _handle_completion_prevalidation(
    completion_shell: str,
    run_state: dict[str, Any] | None = None,
) -> NoReturn:
    """Handle completion mode before unrelated global validation paths."""
    from cja_auto_sdr.__main__ import _handle_completion

    try:
        _handle_completion(completion_shell, sys.argv[0] if sys.argv else None)
    except SystemExit as exc:
        if run_state is not None:
            run_state["details"] = {"operation_success": _normalize_exit_code(exc.code) == 0}
        raise


def _dispatch_prevalidation_mode(
    args: argparse.Namespace,
    inferred_mode: RunMode,
    run_state: dict[str, Any] | None = None,
) -> None:
    """Dispatch pre-validation command modes using inferred run-mode precedence.

    Completion must short-circuit before unrelated global validation, but only
    when completion is the selected mode for this argv.
    """
    if inferred_mode != RunMode.COMPLETION:
        return

    completion_shell = _completion_shell_from_args(args)
    if completion_shell is None:
        _exit_error("Internal error: completion mode inferred without a completion shell value")
    _handle_completion_prevalidation(completion_shell, run_state=run_state)


def _sync_run_summary_cli_metadata(
    run_state: dict[str, Any] | None,
    args: argparse.Namespace,
    *,
    inferred_mode: RunMode | None = None,
) -> None:
    """Synchronize run-summary metadata derived directly from parsed CLI args.

    Keep this centralized so early exits (validation/policy) still emit
    consistent telemetry values such as allow_partial.
    """
    if run_state is None:
        return

    if inferred_mode is not None:
        run_state["mode"] = inferred_mode.value
    run_state["profile"] = getattr(args, "profile", None)
    run_state["config_file"] = getattr(args, "config_file", None)
    run_state["output_format"] = getattr(args, "format", None)
    run_state["output_dir"] = getattr(args, "output_dir", ".")
    run_state["data_view_inputs"] = list(getattr(args, "data_views", []))
    run_state["run_summary_output"] = getattr(args, "run_summary_json", run_state.get("run_summary_output"))
    run_state["allow_partial"] = bool(getattr(args, "allow_partial", False))


def _normalize_partial_reason_values(partial_reasons: Iterable[str] | None) -> list[str]:
    """Return stable, de-duplicated partial reasons."""
    normalized: list[str] = []
    if partial_reasons is None:
        return normalized
    for raw_reason in partial_reasons:
        reason = str(raw_reason).strip()
        if reason and reason not in normalized:
            normalized.append(reason)
    return normalized


def _normalize_output_artifact_values(output_files: Iterable[str] | None) -> list[str]:
    """Return stable, de-duplicated emitted artifact paths."""
    normalized: list[str] = []
    if output_files is None:
        return normalized
    for raw_path in output_files:
        path = str(raw_path).strip()
        if path and path not in normalized:
            normalized.append(path)
    return normalized


def _normalize_output_artifact_state(
    output_file: str | None,
    output_files: Iterable[str] | None,
) -> tuple[str, list[str]]:
    """Normalize primary output file and emitted artifact list together."""
    normalized_output_files = _normalize_output_artifact_values(output_files)
    primary_output = str(output_file or "").strip()
    if primary_output:
        if primary_output in normalized_output_files:
            normalized_output_files = [
                primary_output,
                *[path for path in normalized_output_files if path != primary_output],
            ]
        else:
            normalized_output_files.insert(0, primary_output)
    elif normalized_output_files:
        primary_output = normalized_output_files[0]
    return primary_output, normalized_output_files


def _normalize_partial_state(
    partial_output: bool | None,
    partial_reasons: Iterable[str] | None,
) -> tuple[bool, list[str]]:
    """Normalize partial-run state once for all producers and serializers."""
    normalized_partial_reasons = _normalize_partial_reason_values(partial_reasons)
    normalized_partial_output = bool(partial_output) or bool(normalized_partial_reasons)
    return normalized_partial_output, normalized_partial_reasons


def _build_processing_result(
    *,
    data_view_id: str,
    data_view_name: str,
    success: bool,
    duration: float,
    partial_reasons: Iterable[str] | None = None,
    partial_output: bool | None = None,
    **kwargs: Any,
) -> ProcessingResult:
    """Construct ProcessingResult objects and defer partial-state normalization to ``ProcessingResult``."""
    return ProcessingResult(
        data_view_id=data_view_id,
        data_view_name=data_view_name,
        success=success,
        duration=duration,
        partial_output=partial_output,
        partial_reasons=list(partial_reasons) if partial_reasons is not None else [],
        **kwargs,
    )


def _infer_run_mode(args: argparse.Namespace) -> str:
    """Compatibility wrapper that returns the run mode as a string value."""
    return _infer_run_mode_enum(args).value


def _fallback_failure_code_from_message(error_message: str) -> str:
    """Infer a stable failure code from legacy free-text messages."""
    normalized = error_message.lower()
    if "component fetch failed" in normalized:
        return FAILURE_CODE_COMPONENT_FETCH_FAILED
    if "data quality validation failed" in normalized:
        return FAILURE_CODE_DQ_VALIDATION_RUNTIME_FAILED
    if "data view validation failed" in normalized:
        return FAILURE_CODE_DATAVIEW_LOOKUP_INVALID
    if "no metrics or dimensions found" in normalized:
        return FAILURE_CODE_REQUIRED_COMPONENTS_EMPTY
    if "initialization failed" in normalized:
        return FAILURE_CODE_CJA_INIT_FAILED
    if "permission denied" in normalized:
        return FAILURE_CODE_OUTPUT_PERMISSION_DENIED
    return FAILURE_CODE_UNCLASSIFIED_FAILURE


def _normalize_failure_identity(result: ProcessingResult) -> tuple[str, str]:
    """Return stable failure code/reason for run-summary serialization."""
    if result.success:
        return "", ""

    code = result.failure_code.strip()
    reason = result.failure_reason.strip()
    if not code:
        code = _fallback_failure_code_from_message(result.error_message)
    if not reason:
        reason = code.lower()
    return code, reason


def _build_failure_rollups(serialized_results: list[dict[str, Any]]) -> dict[str, dict[str, int]]:
    """Aggregate failed-result counts by stable code and reason."""
    by_code: dict[str, int] = {}
    by_reason: dict[str, int] = {}
    for result in serialized_results:
        if bool(result.get("success")):
            continue
        code = str(result.get("failure_code") or FAILURE_CODE_UNCLASSIFIED_FAILURE)
        reason = str(result.get("failure_reason") or code.lower())
        by_code[code] = by_code.get(code, 0) + 1
        by_reason[reason] = by_reason.get(reason, 0) + 1
    return {
        "by_code": dict(sorted(by_code.items())),
        "by_reason": dict(sorted(by_reason.items())),
    }


def _result_output_paths(result: Any) -> list[str]:
    """Extract normalized emitted artifact paths from a result-like object."""
    if isinstance(result, dict):
        output_file = result.get("output_file")
        output_files = result.get("output_files")
    else:
        output_file = getattr(result, "output_file", "")
        output_files = getattr(result, "output_files", None)
    _primary_output, normalized_output_files = _normalize_output_artifact_state(output_file, output_files)
    return normalized_output_files


def _processing_result_to_summary(result: ProcessingResult) -> dict[str, Any]:
    """Serialize ProcessingResult into run summary shape."""
    failure_code, failure_reason = _normalize_failure_identity(result)
    return {
        "data_view_id": result.data_view_id,
        "data_view_name": result.data_view_name,
        "success": result.success,
        "duration_seconds": round(result.duration, 3),
        "metrics_count": result.metrics_count,
        "dimensions_count": result.dimensions_count,
        "dq_issues_count": result.dq_issues_count,
        "dq_severity_counts": result.dq_severity_counts,
        "output_file": result.output_file,
        "output_files": result.emitted_output_files,
        "error_message": result.error_message,
        "failure_code": failure_code,
        "failure_reason": failure_reason,
        "partial_output": result.partial_output,
        "partial_reasons": result.partial_reasons,
        "file_size_bytes": result.file_size_bytes,
        "segments_count": result.segments_count,
        "segments_high_complexity": result.segments_high_complexity,
        "calculated_metrics_count": result.calculated_metrics_count,
        "calculated_metrics_high_complexity": result.calculated_metrics_high_complexity,
        "derived_fields_count": result.derived_fields_count,
        "derived_fields_high_complexity": result.derived_fields_high_complexity,
    }


def _collect_environment_info() -> dict[str, Any]:
    """Collect runtime environment info for the run summary payload.

    Reuses :func:`core.logging._collect_dependency_versions` as the single
    source of truth for dependency names and version lookup, remapping the
    ``"?"`` fallback to ``"unknown"`` for the JSON contract.
    """
    vi = sys.version_info
    python_version = f"{vi.major}.{vi.minor}.{vi.micro}"

    deps = {pkg: (v if v != "?" else "unknown") for pkg, v in _collect_dependency_versions().items()}

    return {
        "python_version": python_version,
        "platform": sys.platform,
        "platform_version": platform.platform(),
        "dependencies": deps,
    }


def _build_run_summary_payload(
    *,
    run_state: Mapping[str, Any],
    exit_code: int,
    summary_start: str,
    summary_start_perf: float,
) -> dict[str, Any]:
    """Build the machine-readable run summary payload."""
    serialized_results = [_processing_result_to_summary(r) for r in run_state.get("processed_results", [])]
    success_count = sum(1 for r in serialized_results if r.get("success"))
    failure_count = len(serialized_results) - success_count
    return {
        "summary_version": RUN_SUMMARY_SCHEMA_VERSION,
        "tool_version": __version__,
        "environment": _collect_environment_info(),
        "started_at": summary_start,
        "ended_at": datetime.now(UTC).isoformat(),
        "duration_seconds": round(time.time() - summary_start_perf, 3),
        "exit_code": exit_code,
        "status": _infer_run_status(exit_code, run_state),
        "mode": run_state.get("mode", "unknown"),
        "profile": run_state.get("profile"),
        "config_file": run_state.get("config_file"),
        "output_format": run_state.get("output_format"),
        "allow_partial": bool(run_state.get("allow_partial", False)),
        "command": {"argv": list(sys.argv), "cwd": str(Path.cwd())},
        "inputs": {
            "data_view_inputs": run_state.get("data_view_inputs", []),
            "resolved_data_views": run_state.get("resolved_data_views", []),
        },
        "results": serialized_results,
        "result_counts": {
            "total": len(serialized_results),
            "successful": success_count,
            "failed": failure_count,
            "quality_issues": int(run_state.get("quality_issues_count", 0) or 0),
        },
        "failure_rollups": _build_failure_rollups(serialized_results),
        "quality_gate_failed": bool(run_state.get("quality_gate_failed", False)),
        "quality_policy": run_state.get("quality_policy"),
        "details": run_state.get("details", {}),
    }


def write_run_summary_output(summary: dict[str, Any], output: str, output_dir: str | Path = ".") -> str:
    """Write structured run summary JSON to file or stdout."""
    output_to_stdout = output in ("-", "stdout")
    if output_to_stdout:
        json.dump(summary, sys.stdout, indent=2, ensure_ascii=False)
        print()
        return "stdout"

    output_path = Path(output)
    if not output_path.is_absolute():
        output_path = Path(output_dir) / output_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
        f.write("\n")
    return str(output_path)


def append_github_step_summary(markdown: str, logger: logging.Logger | None = None) -> bool:
    """Append markdown to GitHub Actions job summary when available."""
    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not summary_path:
        return False

    try:
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write(markdown.rstrip() + "\n\n")
        return True
    except OSError as e:
        if logger is not None:
            logger.warning(f"Failed to write GitHub step summary: {e}")
        return False


def build_quality_step_summary(results: list[ProcessingResult]) -> str:
    """Build markdown summary table for quality issues."""
    total_views = len(results)
    successful_views = sum(1 for r in results if r.success)
    all_issues = aggregate_quality_issues(results)
    severity_counts = count_quality_issues_by_severity(all_issues)

    lines = [
        "### Data Quality Summary",
        "",
        f"- Data views processed: {successful_views}/{total_views}",
        f"- Total quality issues: {len(all_issues)}",
        "",
    ]

    if severity_counts:
        lines.extend(["| Severity | Count |", "|---|---:|"])
        for severity in QUALITY_SEVERITY_ORDER:
            count = severity_counts.get(severity, 0)
            if count > 0:
                lines.append(f"| {severity} | {count} |")
        lines.append("")

    lines.extend(["| Data View | ID | Issues | Highest Severity |", "|---|---|---:|---|"])
    for result in results:
        highest = "NONE"
        for severity in QUALITY_SEVERITY_ORDER:
            if result.dq_severity_counts.get(severity, 0) > 0:
                highest = severity
                break
        lines.append(
            f"| {result.data_view_name or '-'} | `{result.data_view_id}` | {result.dq_issues_count} | {highest} |",
        )

    return "\n".join(lines)


def build_diff_step_summary(diff_result: DiffResult) -> str:
    """Build markdown summary table for diff output."""
    summary = diff_result.summary
    total_changes = summary.total_changes + summary.calc_metrics_changed + summary.segments_changed
    lines = [
        "### Diff Summary",
        "",
        f"- Source: `{diff_result.metadata_diff.source_id}` ({diff_result.metadata_diff.source_name})",
        f"- Target: `{diff_result.metadata_diff.target_id}` ({diff_result.metadata_diff.target_name})",
        f"- Total changes: {total_changes}",
        "",
        "| Type | Source | Target | Added | Removed | Modified | Unchanged |",
        "|---|---:|---:|---:|---:|---:|---:|",
        (
            f"| Metrics | {summary.source_metrics_count} | {summary.target_metrics_count} | "
            f"{summary.metrics_added} | {summary.metrics_removed} | {summary.metrics_modified} | {summary.metrics_unchanged} |"
        ),
        (
            f"| Dimensions | {summary.source_dimensions_count} | {summary.target_dimensions_count} | "
            f"{summary.dimensions_added} | {summary.dimensions_removed} | {summary.dimensions_modified} | {summary.dimensions_unchanged} |"
        ),
    ]

    if summary.source_calc_metrics_count > 0 or summary.target_calc_metrics_count > 0:
        lines.append(
            f"| Calc Metrics | {summary.source_calc_metrics_count} | {summary.target_calc_metrics_count} | "
            f"{summary.calc_metrics_added} | {summary.calc_metrics_removed} | {summary.calc_metrics_modified} | {summary.calc_metrics_unchanged} |",
        )
    if summary.source_segments_count > 0 or summary.target_segments_count > 0:
        lines.append(
            f"| Segments | {summary.source_segments_count} | {summary.target_segments_count} | "
            f"{summary.segments_added} | {summary.segments_removed} | {summary.segments_modified} | {summary.segments_unchanged} |",
        )

    return "\n".join(lines)


def build_org_step_summary(result: OrgReportResult) -> str:
    """Build markdown summary table for org-report output."""
    dist = result.distribution
    lines = [
        "### Org Report Summary",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Data Views Analyzed | {result.successful_data_views} / {result.total_data_views} |",
        f"| Data View Fetch Failures | {result.failed_data_views} |",
        f"| Total Unique Components | {result.total_unique_components} |",
        f"| Total Unique Metrics | {result.total_unique_metrics} |",
        f"| Total Unique Dimensions | {result.total_unique_dimensions} |",
        f"| Core Components | {dist.total_core} |",
        f"| Common Components | {dist.total_common} |",
        f"| Limited Components | {dist.total_limited} |",
        f"| Isolated Components | {dist.total_isolated} |",
        f"| Recommendations | {len(result.recommendations)} |",
        f"| Governance Violations | {len(result.governance_violations or [])} |",
        f"| Duration (s) | {result.duration:.2f} |",
    ]
    return "\n".join(lines)


# ==================== DIFF COMPARISON ====================

from cja_auto_sdr.api.cache import SharedValidationCache, ValidationCache

# ==================== API WORKER TUNER (moved to api/tuning.py) ====================
from cja_auto_sdr.api.tuning import APIWorkerTuner

# ==================== LOGGING SETUP ====================
# ==================== LOGGING (moved to core/logging.py) ====================
from cja_auto_sdr.core.logging import (
    _CORE_DEPENDENCIES,
    JSONFormatter,
    _collect_dependency_versions,
    flush_logging_handlers,
    setup_logging,
    with_log_context,
)

# ==================== PERFORMANCE TRACKING (moved to core/perf.py) ====================
from cja_auto_sdr.core.perf import PerformanceTracker
from cja_auto_sdr.diff.comparator import DataViewComparator
from cja_auto_sdr.diff.git import (
    generate_git_commit_message,
    git_commit_snapshot,
    git_get_user_info,
    git_init_snapshot_repo,
    is_git_repository,
    save_git_friendly_snapshot,
)
from cja_auto_sdr.diff.models import (
    ChangeType,
    ComponentDiff,
    DataViewSnapshot,
    DiffResult,
    DiffSummary,
    InventoryItemDiff,
    MetadataDiff,
)
from cja_auto_sdr.diff.snapshot import SnapshotManager, parse_retention_period

# ==================== PROFILE MANAGEMENT ====================


def _profiles_module():
    from cja_auto_sdr.core import profiles as _profiles

    return _profiles


def get_cja_home() -> Path:
    return _profiles_module().get_cja_home()


def get_profiles_dir() -> Path:
    return _profiles_module().get_profiles_dir()


def get_profile_path(profile_name: str) -> Path:
    return _profiles_module().get_profile_path(profile_name)


def validate_profile_name(name: str) -> tuple[bool, str | None]:
    return _profiles_module().validate_profile_name(name)


def load_profile_config_json(profile_path: Path) -> dict[str, str] | None:
    return _profiles_module().load_profile_config_json(profile_path)


def load_profile_dotenv(profile_path: Path) -> dict[str, str] | None:
    return _profiles_module().load_profile_dotenv(profile_path)


def load_profile_credentials(profile_name: str, logger: logging.Logger) -> dict[str, str] | None:
    return _profiles_module().load_profile_credentials(profile_name, logger)


def resolve_active_profile(cli_profile: str | None = None) -> str | None:
    return _profiles_module().resolve_active_profile(cli_profile)


def _read_profile_org_id(profile_path: Path) -> str | None:
    return _profiles_module()._read_profile_org_id(profile_path)


def list_profiles(output_format: str = "table") -> bool:
    return _profiles_module().list_profiles(output_format=output_format)


def add_profile_interactive(profile_name: str) -> bool:
    return _profiles_module().add_profile_interactive(profile_name)


def _normalize_import_credentials(raw_credentials: dict[str, Any]) -> dict[str, str]:
    return _profiles_module()._normalize_import_credentials(raw_credentials)


def _parse_env_credentials_content(content: str) -> dict[str, str]:
    return _profiles_module()._parse_env_credentials_content(content)


def load_profile_import_source(source_file: str | Path) -> dict[str, str]:
    return _profiles_module().load_profile_import_source(source_file)


def import_profile_non_interactive(profile_name: str, source_file: str | Path, overwrite: bool = False) -> bool:
    return _profiles_module().import_profile_non_interactive(profile_name, source_file, overwrite=overwrite)


def mask_sensitive_value(value: str, show_chars: int = 4) -> str:
    return _profiles_module().mask_sensitive_value(value, show_chars=show_chars)


def show_profile(profile_name: str) -> bool:
    return _profiles_module().show_profile(profile_name)


def test_profile(profile_name: str) -> bool:
    return _profiles_module().test_profile(profile_name)


# ==================== CONFIG VALIDATION (moved to core/config_validation.py) ====================
# ==================== CJA CLIENT (moved to api/client.py) ====================
from cja_auto_sdr.api.client import _bootstrap_dotenv, _config_from_env, configure_cjapy, initialize_cja
from cja_auto_sdr.core.config_validation import (
    ConfigValidator,
    validate_config_file,
    validate_credentials,
)

# ==================== CREDENTIAL LOADING (moved to core/credentials.py) ====================
from cja_auto_sdr.core.credentials import (
    CredentialLoader,
    CredentialResolver,
    DotenvCredentialLoader,
    EnvironmentCredentialLoader,
    JsonFileCredentialLoader,
    filter_credentials,
    load_credentials_from_env,
    normalize_credential_value,
    validate_env_credentials,
)

# ==================== DATA VIEW VALIDATION ====================


def validate_data_view(cja: cjapy.CJA, data_view_id: str, logger: logging.Logger) -> bool:
    """Validate that the data view exists and is accessible.

    Args:
        cja: Initialized CJA instance
        data_view_id: Data view ID to validate
        logger: Logger instance

    Returns:
        True if data view is valid and accessible, False otherwise
    """
    try:
        logger.info("=" * BANNER_WIDTH)
        logger.info("VALIDATING DATA VIEW")
        logger.info("=" * BANNER_WIDTH)
        logger.info(f"Data View ID: {data_view_id}")

        # Basic format validation
        if not data_view_id or not isinstance(data_view_id, str):
            logger.error("Invalid data view ID format")
            logger.error("Data view ID must be a non-empty string")
            return False

        if not data_view_id.startswith("dv_"):
            logger.warning(f"Data view ID '{data_view_id}' does not follow standard format (dv_...)")
            logger.warning("This may still be valid, but unusual")

        # Attempt to fetch data view info
        logger.info("Fetching data view information from API...")
        try:
            raw_dv_info = _fetch_dataview_lookup_payload(cja, data_view_id)
        except DiscoveryNotFoundError:
            raw_dv_info = None
        except AttributeError as e:
            logger.error("API method 'getDataView' not available")
            logger.error("Possible causes:")
            logger.error("  1. Outdated cjapy version - try: pip install --upgrade cjapy")
            logger.error("  2. CJA connection not properly initialized")
            logger.error("  3. Authentication failed silently")
            logger.debug(f"AttributeError details: {e}")
            return False
        except (APIError, ConfigurationError, OSError) as api_error:
            logger.error(f"API call failed: {api_error!s}")
            logger.error("Possible reasons:")
            logger.error("  1. Data view does not exist")
            logger.error("  2. You don't have permission to access this data view")
            logger.error("  3. Network connectivity issues")
            logger.error("  4. API authentication has expired")
            return False

        # Validate response
        dv_info, lookup_failure_reason, lookup_raw_type = _coerce_valid_dataview_lookup_payload(
            raw_dv_info,
            data_view_id=data_view_id,
        )
        if dv_info is None:
            logger.error("Data view lookup returned invalid payload (%s)", lookup_failure_reason)
            logger.debug(
                "Rejected data view lookup payload: data_view_id=%s raw_type=%s",
                data_view_id,
                lookup_raw_type,
            )

        if not dv_info:
            # Try to list available data views to provide context
            available_count = None
            try:
                available_dvs = cja.getDataViews()
                available_count = len(available_dvs) if available_dvs else 0

                if available_count > 0:
                    logger.info(f"You have access to {available_count} data view(s):")
                    for i, dv in enumerate(available_dvs[:10]):  # Show first 10
                        dv_id = dv.get("id", "unknown")
                        dv_name = dv.get("name", "unknown")
                        logger.info(f"  {i + 1}. {dv_name} (ID: {dv_id})")
                    if available_count > 10:
                        logger.info(f"  ... and {available_count - 10} more")
                    logger.info("")
            except (APIError, AttributeError, KeyError, TypeError, ValueError) as list_error:
                logger.debug(f"Could not list available data views: {list_error!s}")

            # Show enhanced error message
            error_msg = ErrorMessageHelper.get_data_view_error_message(data_view_id, available_count=available_count)
            logger.error("\n" + error_msg)
            return False

        # Extract and validate data view details
        try:
            if not isinstance(dv_info, dict):
                raise TypeError(f"Expected data view payload to be dict, got {type(dv_info).__name__}")

            dv_name = dv_info.get("name", "Unknown")
            dv_description = dv_info.get("description", "No description")
            if not isinstance(dv_description, str):
                dv_description = str(dv_description) if dv_description is not None else "No description"

            owner_info = dv_info.get("owner", {})
            if not isinstance(owner_info, dict):
                raise TypeError(f"Expected data view owner payload to be dict, got {type(owner_info).__name__}")
            dv_owner = owner_info.get("name", "Unknown")

            has_components = "components" in dv_info
            components = dv_info.get("components", {})
            if has_components and not isinstance(components, dict):
                raise TypeError(f"Expected components payload to be dict, got {type(components).__name__}")
        except (AttributeError, KeyError, TypeError, ValueError) as payload_error:
            logger.error("Malformed data view payload returned by API")
            logger.debug(f"Payload validation error: {payload_error!s}")
            return False

        logger.info("✓ Data view validated successfully!")
        logger.info(f"  Name: {dv_name}")
        logger.info(f"  ID: {data_view_id}")
        logger.info(f"  Owner: {dv_owner}")
        if dv_description and dv_description != "No description":
            logger.info(f"  Description: {dv_description[:100]}{'...' if len(dv_description) > 100 else ''}")

        # Additional validation checks
        warnings = []

        if has_components and not components.get("dimensions") and not components.get("metrics"):
            warnings.append("Data view appears to have no components defined")

        if warnings:
            logger.warning("Data view validation warnings:")
            for warning in warnings:
                logger.warning(f"  - {warning}")

        return True

    except KeyboardInterrupt, SystemExit:
        raise
    except RECOVERABLE_CONFIG_API_EXCEPTIONS as e:  # cjapy API/bootstrap calls
        logger.error("=" * BANNER_WIDTH)
        logger.error("DATA VIEW VALIDATION ERROR")
        logger.error("=" * BANNER_WIDTH)
        logger.error(f"Unexpected error during validation: {e!s}")
        logger.exception("Full error details:")
        logger.error("")
        logger.error("Please verify:")
        logger.error("  1. The data view ID is correct")
        logger.error("  2. You have access to this data view")
        logger.error("  3. Your API credentials are valid")
        return False


# ==================== OPTIMIZED API DATA FETCHING (moved to api/fetch.py) ====================
from cja_auto_sdr.api.fetch import EndpointFetchStatus, ParallelAPIFetcher

# ==================== DATA QUALITY VALIDATION (moved to api/quality.py) ====================
from cja_auto_sdr.api.quality import DataQualityChecker

# ==================== SDR OUTPUT WRITERS (moved to output/sdr/__init__.py) ====================
from cja_auto_sdr.output.sdr import (
    ExcelFormatCache,
    apply_excel_formatting,
    write_csv_output,
    write_excel_output,
    write_html_output,
    write_json_output,
    write_markdown_output,
)

# The following functions were moved to cja_auto_sdr.output.sdr:
# - ExcelFormatCache (class)
# - apply_excel_formatting
# - write_excel_output
# - write_csv_output
# - write_json_output
# - write_html_output
# - write_markdown_output


# ==================== DIFF COMPARISON OUTPUT WRITERS ====================


# ANSIColors is an alias for diff output compatibility
# It delegates to ConsoleColors but accepts an 'enabled' parameter for explicit control
class ANSIColors:
    """ANSI escape codes for colored terminal output.

    This class provides the same functionality as ConsoleColors but with an
    explicit 'enabled' parameter for cases where color control is needed
    independent of TTY detection.
    """

    # Re-export constants from ConsoleColors
    GREEN = ConsoleColors.GREEN
    RED = ConsoleColors.RED
    YELLOW = ConsoleColors.YELLOW
    CYAN = ConsoleColors.CYAN
    BOLD = ConsoleColors.BOLD
    RESET = ConsoleColors.RESET
    ANSI_ESCAPE = ConsoleColors.ANSI_ESCAPE

    @classmethod
    def green(cls, text: str, enabled: bool = True) -> str:
        return f"{cls.GREEN}{text}{cls.RESET}" if enabled else text

    @classmethod
    def red(cls, text: str, enabled: bool = True) -> str:
        return f"{cls.RED}{text}{cls.RESET}" if enabled else text

    @classmethod
    def yellow(cls, text: str, enabled: bool = True) -> str:
        return f"{cls.YELLOW}{text}{cls.RESET}" if enabled else text

    @classmethod
    def cyan(cls, text: str, enabled: bool = True) -> str:
        return f"{cls.CYAN}{text}{cls.RESET}" if enabled else text

    @classmethod
    def bold(cls, text: str, enabled: bool = True) -> str:
        return f"{cls.BOLD}{text}{cls.RESET}" if enabled else text

    # Delegate utility methods to ConsoleColors
    visible_len = ConsoleColors.visible_len
    rjust = ConsoleColors.rjust
    ljust = ConsoleColors.ljust


def write_diff_console_output(
    diff_result: DiffResult,
    changes_only: bool = False,
    summary_only: bool = False,
    side_by_side: bool = False,
    use_color: bool = True,
) -> str:
    """
    Write diff comparison to console with color-coded output.

    Args:
        diff_result: The DiffResult to output
        changes_only: Only show changed items (hide unchanged)
        summary_only: Only show summary statistics
        side_by_side: Show side-by-side comparison for modified items
        use_color: Use ANSI color codes in output (default: True)

    Returns:
        Formatted string for console output
    """
    lines = []
    summary = diff_result.summary
    meta = diff_result.metadata_diff
    c = use_color  # Shorthand for color enabled flag

    # Header
    lines.append("=" * 80)
    lines.append(ANSIColors.bold("DATA VIEW COMPARISON REPORT", c))
    lines.append("=" * 80)
    lines.append(f"{diff_result.source_label}: {meta.source_name} ({meta.source_id})")
    lines.append(f"{diff_result.target_label}: {meta.target_name} ({meta.target_id})")
    lines.append(f"Generated: {diff_result.generated_at}")
    lines.append("=" * 80)

    # Summary table with percentages
    lines.append("")
    lines.append(ANSIColors.bold("SUMMARY", c))

    # Build full header labels with data view name and ID
    src_header = f"{diff_result.source_label}: {meta.source_name} ({meta.source_id})"
    tgt_header = f"{diff_result.target_label}: {meta.target_name} ({meta.target_id})"

    # Calculate dynamic column widths based on full header lengths
    src_width = max(8, len(src_header))
    tgt_width = max(8, len(tgt_header))
    total_width = 20 + src_width + tgt_width + 10 + 10 + 10 + 12 + 12 + 7  # +7 for spacing

    lines.append(
        f"{'':20s} {src_header:>{src_width}s} {tgt_header:>{tgt_width}s} {'Added':>10s} {'Removed':>10s} {'Modified':>10s} {'Unchanged':>12s} {'Changed':>12s}",
    )
    lines.append("-" * total_width)

    # Metrics row with percentage (using ANSI-aware padding for colored strings)
    metrics_pct = f"({summary.metrics_change_percent:.1f}%)"
    added_str = (
        ANSIColors.green(f"+{summary.metrics_added}", c) if summary.metrics_added else f"+{summary.metrics_added}"
    )
    removed_str = (
        ANSIColors.red(f"-{summary.metrics_removed}", c) if summary.metrics_removed else f"-{summary.metrics_removed}"
    )
    modified_str = (
        ANSIColors.yellow(f"~{summary.metrics_modified}", c)
        if summary.metrics_modified
        else f"~{summary.metrics_modified}"
    )
    lines.append(
        f"{'Metrics':20s} {summary.source_metrics_count:{src_width}d} {summary.target_metrics_count:{tgt_width}d} "
        f"{ANSIColors.rjust(added_str, 10)} {ANSIColors.rjust(removed_str, 10)} {ANSIColors.rjust(modified_str, 10)} {summary.metrics_unchanged:>12d} {metrics_pct:>12s}",
    )

    # Dimensions row with percentage (using ANSI-aware padding for colored strings)
    dims_pct = f"({summary.dimensions_change_percent:.1f}%)"
    added_str = (
        ANSIColors.green(f"+{summary.dimensions_added}", c)
        if summary.dimensions_added
        else f"+{summary.dimensions_added}"
    )
    removed_str = (
        ANSIColors.red(f"-{summary.dimensions_removed}", c)
        if summary.dimensions_removed
        else f"-{summary.dimensions_removed}"
    )
    modified_str = (
        ANSIColors.yellow(f"~{summary.dimensions_modified}", c)
        if summary.dimensions_modified
        else f"~{summary.dimensions_modified}"
    )
    lines.append(
        f"{'Dimensions':20s} {summary.source_dimensions_count:{src_width}d} {summary.target_dimensions_count:{tgt_width}d} "
        f"{ANSIColors.rjust(added_str, 10)} {ANSIColors.rjust(removed_str, 10)} {ANSIColors.rjust(modified_str, 10)} {summary.dimensions_unchanged:>12d} {dims_pct:>12s}",
    )

    # Inventory rows (if present)
    if summary.has_inventory_changes or (
        summary.source_calc_metrics_count > 0 or summary.target_calc_metrics_count > 0
    ):
        lines.append("-" * total_width)
        lines.append(ANSIColors.bold("INVENTORY", c))

        # Calculated metrics row
        if summary.source_calc_metrics_count > 0 or summary.target_calc_metrics_count > 0:
            added_str = (
                ANSIColors.green(f"+{summary.calc_metrics_added}", c)
                if summary.calc_metrics_added
                else f"+{summary.calc_metrics_added}"
            )
            removed_str = (
                ANSIColors.red(f"-{summary.calc_metrics_removed}", c)
                if summary.calc_metrics_removed
                else f"-{summary.calc_metrics_removed}"
            )
            modified_str = (
                ANSIColors.yellow(f"~{summary.calc_metrics_modified}", c)
                if summary.calc_metrics_modified
                else f"~{summary.calc_metrics_modified}"
            )
            lines.append(
                f"{'Calc Metrics':20s} {summary.source_calc_metrics_count:{src_width}d} {summary.target_calc_metrics_count:{tgt_width}d} "
                f"{ANSIColors.rjust(added_str, 10)} {ANSIColors.rjust(removed_str, 10)} {ANSIColors.rjust(modified_str, 10)} {summary.calc_metrics_unchanged:>12d} {'':>12s}",
            )

        # Segments row
        if summary.source_segments_count > 0 or summary.target_segments_count > 0:
            added_str = (
                ANSIColors.green(f"+{summary.segments_added}", c)
                if summary.segments_added
                else f"+{summary.segments_added}"
            )
            removed_str = (
                ANSIColors.red(f"-{summary.segments_removed}", c)
                if summary.segments_removed
                else f"-{summary.segments_removed}"
            )
            modified_str = (
                ANSIColors.yellow(f"~{summary.segments_modified}", c)
                if summary.segments_modified
                else f"~{summary.segments_modified}"
            )
            lines.append(
                f"{'Segments':20s} {summary.source_segments_count:{src_width}d} {summary.target_segments_count:{tgt_width}d} "
                f"{ANSIColors.rjust(added_str, 10)} {ANSIColors.rjust(removed_str, 10)} {ANSIColors.rjust(modified_str, 10)} {summary.segments_unchanged:>12d} {'':>12s}",
            )

    lines.append("-" * total_width)

    if summary_only:
        lines.append("")
        if summary.has_changes:
            lines.append(f"Total changes: {summary.total_changes}")
            lines.append(f"Summary: {summary.natural_language_summary}")
        else:
            lines.append(ANSIColors.green("No differences found.", c))
        lines.append("=" * 80)
        return "\n".join(lines)

    # Get changes for both metrics and dimensions
    metric_changes = [d for d in diff_result.metric_diffs if d.change_type != ChangeType.UNCHANGED]
    dim_changes = [d for d in diff_result.dimension_diffs if d.change_type != ChangeType.UNCHANGED]

    # Calculate global max ID width for consistent alignment across both sections
    all_changes = metric_changes + dim_changes
    global_max_id_len = max((len(d.id) for d in all_changes), default=0)

    # Metrics changes
    if metric_changes or not changes_only:
        lines.append("")
        change_count = len(metric_changes)
        lines.append(ANSIColors.bold(f"METRICS CHANGES ({change_count})", c))
        if metric_changes:
            for diff in metric_changes:
                colored_symbol = _get_colored_symbol(diff.change_type, c)
                lines.append(f'  [{colored_symbol}] {diff.id:{global_max_id_len}s} "{diff.name}"')
                if side_by_side and diff.change_type == ChangeType.MODIFIED:
                    # Side-by-side view for modified items
                    sbs_lines = _format_side_by_side(diff, diff_result.source_label, diff_result.target_label)
                    lines.extend(sbs_lines)
                else:
                    detail = _get_change_detail(diff)
                    if detail:
                        lines.append(f"      {detail}")
        else:
            lines.append("  No changes")

    # Dimensions changes
    if dim_changes or not changes_only:
        lines.append("")
        change_count = len(dim_changes)
        lines.append(ANSIColors.bold(f"DIMENSIONS CHANGES ({change_count})", c))
        if dim_changes:
            for diff in dim_changes:
                colored_symbol = _get_colored_symbol(diff.change_type, c)
                lines.append(f'  [{colored_symbol}] {diff.id:{global_max_id_len}s} "{diff.name}"')
                if side_by_side and diff.change_type == ChangeType.MODIFIED:
                    # Side-by-side view for modified items
                    sbs_lines = _format_side_by_side(diff, diff_result.source_label, diff_result.target_label)
                    lines.extend(sbs_lines)
                else:
                    detail = _get_change_detail(diff)
                    if detail:
                        lines.append(f"      {detail}")
        else:
            lines.append("  No changes")

    # Inventory changes (if present)
    if diff_result.has_inventory_diffs:
        lines.append("")
        lines.append("-" * 80)
        lines.append(ANSIColors.bold("INVENTORY CHANGES", c))
        lines.append("-" * 80)

        # Calculated metrics inventory changes
        if diff_result.calc_metrics_diffs is not None:
            calc_changes = [d for d in diff_result.calc_metrics_diffs if d.change_type != ChangeType.UNCHANGED]
            lines.append("")
            lines.append(ANSIColors.bold(f"CALCULATED METRICS ({len(calc_changes)} changes)", c))
            if calc_changes:
                for diff in calc_changes:
                    colored_symbol = _get_colored_symbol(diff.change_type, c)
                    lines.append(f'  [{colored_symbol}] {diff.id} "{diff.name}"')
                    if diff.change_type == ChangeType.MODIFIED and diff.changed_fields:
                        detail = _get_inventory_change_detail(diff)
                        if detail:
                            lines.append(f"      {detail}")
            else:
                lines.append("  No changes")

        # Segments inventory changes
        if diff_result.segments_diffs is not None:
            seg_changes = [d for d in diff_result.segments_diffs if d.change_type != ChangeType.UNCHANGED]
            lines.append("")
            lines.append(ANSIColors.bold(f"SEGMENTS ({len(seg_changes)} changes)", c))
            if seg_changes:
                for diff in seg_changes:
                    colored_symbol = _get_colored_symbol(diff.change_type, c)
                    lines.append(f'  [{colored_symbol}] {diff.id} "{diff.name}"')
                    if diff.change_type == ChangeType.MODIFIED and diff.changed_fields:
                        detail = _get_inventory_change_detail(diff)
                        if detail:
                            lines.append(f"      {detail}")
            else:
                lines.append("  No changes")

    # Footer with total summary
    lines.append("")
    lines.append("=" * 80)
    if summary.has_changes:
        # Build color-coded total summary line
        total_parts = []
        if summary.total_added:
            total_parts.append(ANSIColors.green(f"{summary.total_added} added", c))
        if summary.total_removed:
            total_parts.append(ANSIColors.red(f"{summary.total_removed} removed", c))
        if summary.total_modified:
            total_parts.append(ANSIColors.yellow(f"{summary.total_modified} modified", c))
        total_line = ", ".join(total_parts)
        lines.append(ANSIColors.bold(f"Total: {total_line}", c))
        lines.append(
            f"  Metrics: {summary.metrics_added} added, {summary.metrics_removed} removed, {summary.metrics_modified} modified",
        )
        lines.append(
            f"  Dimensions: {summary.dimensions_added} added, {summary.dimensions_removed} removed, {summary.dimensions_modified} modified",
        )
        # Add inventory summary lines if present
        if summary.has_inventory_changes:
            if summary.source_calc_metrics_count > 0 or summary.target_calc_metrics_count > 0:
                lines.append(
                    f"  Calc Metrics: {summary.calc_metrics_added} added, {summary.calc_metrics_removed} removed, {summary.calc_metrics_modified} modified",
                )
            if summary.source_segments_count > 0 or summary.target_segments_count > 0:
                lines.append(
                    f"  Segments: {summary.segments_added} added, {summary.segments_removed} removed, {summary.segments_modified} modified",
                )
    else:
        lines.append(ANSIColors.green("✓ No differences found", c))
    lines.append("=" * 80)

    return "\n".join(lines)


def _get_change_symbol(change_type: ChangeType) -> str:
    """Get symbol for change type"""
    symbols = {ChangeType.ADDED: "+", ChangeType.REMOVED: "-", ChangeType.MODIFIED: "~", ChangeType.UNCHANGED: " "}
    return symbols.get(change_type, "?")


def _get_colored_symbol(change_type: ChangeType, use_color: bool = True) -> str:
    """Get color-coded symbol for change type"""
    symbol = _get_change_symbol(change_type)
    if not use_color:
        return symbol
    if change_type == ChangeType.ADDED:
        return ANSIColors.green(symbol, use_color)
    if change_type == ChangeType.REMOVED:
        return ANSIColors.red(symbol, use_color)
    if change_type == ChangeType.MODIFIED:
        return ANSIColors.yellow(symbol, use_color)
    return symbol


def _format_diff_value(val: Any, truncate: bool = True, max_len: int = 30) -> str:
    """Format a value for diff display, handling None and NaN."""
    if val is None:
        return "(empty)"
    try:
        if pd.isna(val):
            return "(empty)"
    except TypeError, ValueError:
        pass
    result = str(val)
    if truncate and len(result) > max_len:
        result = result[:max_len]
    return result


def _get_change_detail(diff: ComponentDiff, truncate: bool = True) -> str:
    """Get detail string for a component diff"""
    if diff.change_type == ChangeType.MODIFIED and diff.changed_fields:
        changes = []
        for field, (old_val, new_val) in diff.changed_fields.items():
            old_str = _format_diff_value(old_val, truncate)
            new_str = _format_diff_value(new_val, truncate)
            changes.append(f"{field}: '{old_str}' -> '{new_str}'")
        return "; ".join(changes)
    return ""


def _get_inventory_change_detail(diff: InventoryItemDiff, truncate: bool = True) -> str:
    """Get detail string for an inventory item diff"""
    if diff.change_type == ChangeType.MODIFIED and diff.changed_fields:
        changes = []
        for field, (old_val, new_val) in diff.changed_fields.items():
            old_str = _format_diff_value(old_val, truncate)
            new_str = _format_diff_value(new_val, truncate)
            changes.append(f"{field}: '{old_str}' -> '{new_str}'")
        return "; ".join(changes)
    return ""


def _format_side_by_side(
    diff: ComponentDiff,
    source_label: str,
    target_label: str,
    col_width: int = 35,
    max_col_width: int = 60,
) -> list[str]:
    """
    Format a component diff as a side-by-side comparison table.

    Args:
        diff: The ComponentDiff to format
        source_label: Label for source side
        target_label: Label for target side
        col_width: Base width of each column
        max_col_width: Maximum width of each column (text will wrap)

    Returns:
        List of formatted lines for the side-by-side view
    """
    lines = []
    if diff.change_type != ChangeType.MODIFIED or not diff.changed_fields:
        return lines

    # Pre-compute all display strings
    field_displays = []
    for field_name, (old_val, new_val) in diff.changed_fields.items():
        old_str = _format_diff_value(old_val, truncate=False)
        new_str = _format_diff_value(new_val, truncate=False)
        old_display = f"{field_name}: {old_str}"
        new_display = f"{field_name}: {new_str}"
        field_displays.append((old_display, new_display))

    # Calculate column width: expand to fit content but cap at max_col_width
    col_width = max(col_width, len(source_label) + 2, len(target_label) + 2)
    for old_display, new_display in field_displays:
        col_width = max(col_width, min(len(old_display), max_col_width), min(len(new_display), max_col_width))
    col_width = min(col_width, max_col_width)

    # Header for this component
    lines.append(f"    ┌{'─' * (col_width + 2)}┬{'─' * (col_width + 2)}┐")
    lines.append(f"    │ {source_label:<{col_width}} │ {target_label:<{col_width}} │")
    lines.append(f"    ├{'─' * (col_width + 2)}┼{'─' * (col_width + 2)}┤")

    # Changed fields with text wrapping
    for old_display, new_display in field_displays:
        # Wrap each side independently
        old_wrapped = textwrap.wrap(old_display, width=col_width) or [""]
        new_wrapped = textwrap.wrap(new_display, width=col_width) or [""]

        # Pad to same number of lines
        max_lines = max(len(old_wrapped), len(new_wrapped))
        old_wrapped.extend([""] * (max_lines - len(old_wrapped)))
        new_wrapped.extend([""] * (max_lines - len(new_wrapped)))

        # Output each line
        for old_line, new_line in zip(old_wrapped, new_wrapped, strict=True):
            lines.append(f"    │ {old_line:<{col_width}} │ {new_line:<{col_width}} │")

    lines.append(f"    └{'─' * (col_width + 2)}┴{'─' * (col_width + 2)}┘")

    return lines


def write_diff_grouped_by_field_output(diff_result: DiffResult, use_color: bool = True, limit: int = 10) -> str:
    """
    Write diff output grouped by changed field instead of by component.

    Args:
        diff_result: The DiffResult to output
        use_color: Use ANSI color codes
        limit: Max items per section (0 = unlimited)

    Returns:
        Formatted string for console output
    """
    lines = []
    summary = diff_result.summary
    meta = diff_result.metadata_diff
    c = use_color

    # Header
    lines.append("=" * 80)
    lines.append(ANSIColors.bold("DATA VIEW COMPARISON - GROUPED BY FIELD", c))
    lines.append("=" * 80)
    lines.append(f"{diff_result.source_label}: {meta.source_name}")
    lines.append(f"{diff_result.target_label}: {meta.target_name}")
    lines.append(f"Generated: {diff_result.generated_at}")
    lines.append("=" * 80)

    # Collect all changed fields across all components
    field_changes: dict[str, list[tuple[str, str, Any, Any]]] = {}  # field -> [(id, name, old, new), ...]

    # Also track breaking changes (type or schemaPath changes)
    breaking_changes = []

    all_diffs = diff_result.metric_diffs + diff_result.dimension_diffs
    for diff in all_diffs:
        if diff.change_type == ChangeType.MODIFIED and diff.changed_fields:
            for field, (old_val, new_val) in diff.changed_fields.items():
                if field not in field_changes:
                    field_changes[field] = []
                field_changes[field].append((diff.id, diff.name, old_val, new_val))

                # Track breaking changes
                if field in ("type", "schemaPath"):
                    breaking_changes.append((diff.id, diff.name, field, old_val, new_val))

    # Summary
    lines.append("")
    lines.append(ANSIColors.bold("SUMMARY", c))
    lines.append(f"Total components changed: {summary.total_changes}")
    lines.append(f"  Added: {ANSIColors.green(str(summary.metrics_added + summary.dimensions_added), c)}")
    lines.append(f"  Removed: {ANSIColors.red(str(summary.metrics_removed + summary.dimensions_removed), c)}")
    lines.append(f"  Modified: {ANSIColors.yellow(str(summary.metrics_modified + summary.dimensions_modified), c)}")
    lines.append(f"Fields with changes: {len(field_changes)}")

    # Breaking changes warning
    if breaking_changes:
        lines.append("")
        lines.append(ANSIColors.red("⚠  BREAKING CHANGES DETECTED", c))
        lines.append("-" * 40)
        for comp_id, _comp_name, field, old_val, new_val in breaking_changes:
            lines.append(f"  {comp_id}: {field} changed")
            lines.append(
                f"    '{_format_diff_value(old_val, truncate=False)}' → '{_format_diff_value(new_val, truncate=False)}'",
            )

    # Group by field
    lines.append("")
    lines.append(ANSIColors.bold("CHANGES BY FIELD", c))
    lines.append("-" * 80)

    for field in sorted(field_changes.keys()):
        changes = field_changes[field]
        lines.append("")
        lines.append(f"{ANSIColors.cyan(field, c)} ({len(changes)} component{'s' if len(changes) != 1 else ''}):")

        items_to_show = changes if limit == 0 else changes[:limit]
        for comp_id, _comp_name, old_val, new_val in items_to_show:
            old_str = _format_diff_value(old_val, truncate=True)
            new_str = _format_diff_value(new_val, truncate=True)
            lines.append(f"  {comp_id}: '{old_str}' → '{new_str}'")

        if limit > 0 and len(changes) > limit:
            lines.append(f"  ... and {len(changes) - limit} more")

    # Added/removed summary
    added = [d for d in all_diffs if d.change_type == ChangeType.ADDED]
    removed = [d for d in all_diffs if d.change_type == ChangeType.REMOVED]

    if added:
        lines.append("")
        lines.append(ANSIColors.green(f"ADDED ({len(added)})", c))
        added_to_show = added if limit == 0 else added[:limit]
        lines.extend(f"  [+] {diff.id}" for diff in added_to_show)
        if limit > 0 and len(added) > limit:
            lines.append(f"  ... and {len(added) - limit} more")

    if removed:
        lines.append("")
        lines.append(ANSIColors.red(f"REMOVED ({len(removed)})", c))
        removed_to_show = removed if limit == 0 else removed[:limit]
        lines.extend(f"  [-] {diff.id}" for diff in removed_to_show)
        if limit > 0 and len(removed) > limit:
            lines.append(f"  ... and {len(removed) - limit} more")

    lines.append("")
    lines.append("=" * 80)
    lines.append(ANSIColors.cyan(f"Summary: {summary.natural_language_summary}", c))
    lines.append("=" * 80)

    return "\n".join(lines)


def write_diff_pr_comment_output(diff_result: DiffResult, _changes_only: bool = False) -> str:
    """
    Write diff output in GitHub/GitLab PR comment format with collapsible details.

    Args:
        diff_result: The DiffResult to output
        changes_only: Only include changed items

    Returns:
        Markdown formatted string optimized for PR comments
    """
    lines = []
    summary = diff_result.summary

    # Header
    lines.append("### 📊 Data View Comparison")
    lines.append("")
    lines.append(f"**{diff_result.source_label}** → **{diff_result.target_label}**")
    lines.append("")

    # Summary table
    lines.append("| Component | Source | Target | Added | Removed | Modified | Unchanged | Changed |")
    lines.append("|-----------|-------:|-------:|------:|--------:|---------:|----------:|--------:|")
    lines.append(
        f"| Metrics | {summary.source_metrics_count} | {summary.target_metrics_count} | "
        f"+{summary.metrics_added} | -{summary.metrics_removed} | ~{summary.metrics_modified} | "
        f"{summary.metrics_unchanged} | {summary.metrics_change_percent:.1f}% |",
    )
    lines.append(
        f"| Dimensions | {summary.source_dimensions_count} | {summary.target_dimensions_count} | "
        f"+{summary.dimensions_added} | -{summary.dimensions_removed} | ~{summary.dimensions_modified} | "
        f"{summary.dimensions_unchanged} | {summary.dimensions_change_percent:.1f}% |",
    )
    lines.append("")

    # Breaking changes warning
    breaking_changes = []
    all_diffs = diff_result.metric_diffs + diff_result.dimension_diffs
    for diff in all_diffs:
        if diff.change_type == ChangeType.MODIFIED and diff.changed_fields:
            for field in diff.changed_fields:
                if field in ("type", "schemaPath"):
                    old_val, new_val = diff.changed_fields[field]
                    breaking_changes.append((diff.id, field, old_val, new_val))

    if breaking_changes:
        lines.append("#### ⚠ Breaking Changes Detected")
        lines.append("")
        lines.append("| Component | Field | Before | After |")
        lines.append("|-----------|-------|--------|-------|")
        for comp_id, field, old_val, new_val in breaking_changes[:10]:
            lines.append(
                f"| `{comp_id}` | {field} | `{_format_diff_value(old_val, truncate=False)}` | `{_format_diff_value(new_val, truncate=False)}` |",
            )
        if len(breaking_changes) > 10:
            lines.append(f"| ... | | | +{len(breaking_changes) - 10} more |")
        lines.append("")

    # Natural language summary
    lines.append(f"**Summary:** {summary.natural_language_summary}")
    lines.append("")

    # Collapsible details
    metric_changes = [d for d in diff_result.metric_diffs if d.change_type != ChangeType.UNCHANGED]
    dim_changes = [d for d in diff_result.dimension_diffs if d.change_type != ChangeType.UNCHANGED]

    if metric_changes:
        lines.append("<details>")
        lines.append(f"<summary>📈 Metrics Changes ({len(metric_changes)})</summary>")
        lines.append("")
        lines.append("| Change | ID | Name |")
        lines.append("|--------|----|----- |")
        for diff in metric_changes[:25]:
            symbol = {ChangeType.ADDED: "➕", ChangeType.REMOVED: "➖", ChangeType.MODIFIED: "✏️"}.get(
                diff.change_type,
                "",
            )
            lines.append(f"| {symbol} | `{diff.id}` | {diff.name} |")
        if len(metric_changes) > 25:
            lines.append(f"| ... | | +{len(metric_changes) - 25} more |")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    if dim_changes:
        lines.append("<details>")
        lines.append(f"<summary>📏 Dimensions Changes ({len(dim_changes)})</summary>")
        lines.append("")
        lines.append("| Change | ID | Name |")
        lines.append("|--------|----|----- |")
        for diff in dim_changes[:25]:
            symbol = {ChangeType.ADDED: "➕", ChangeType.REMOVED: "➖", ChangeType.MODIFIED: "✏️"}.get(
                diff.change_type,
                "",
            )
            lines.append(f"| {symbol} | `{diff.id}` | {diff.name} |")
        if len(dim_changes) > 25:
            lines.append(f"| ... | | +{len(dim_changes) - 25} more |")
        lines.append("")
        lines.append("</details>")
        lines.append("")

    # Footer
    lines.append("---")
    lines.append(f"*Generated by CJA SDR Generator v{diff_result.tool_version}*")

    return "\n".join(lines)


def detect_breaking_changes(diff_result: DiffResult) -> list[dict[str, Any]]:
    """
    Detect breaking changes in a diff result.

    Breaking changes include:
    - Changes to 'type' field (data type changes)
    - Changes to 'schemaPath' field (schema mapping changes)
    - Removal of existing components

    Args:
        diff_result: The DiffResult to analyze

    Returns:
        List of breaking change dictionaries with details
    """
    breaking_changes = []

    all_diffs = diff_result.metric_diffs + diff_result.dimension_diffs

    for diff in all_diffs:
        # Removed components are breaking
        if diff.change_type == ChangeType.REMOVED:
            breaking_changes.append(
                {
                    "component_id": diff.id,
                    "component_name": diff.name,
                    "change_type": "removed",
                    "severity": "high",
                    "description": f"Component '{diff.name}' was removed",
                },
            )

        # Check for type or schema changes
        elif diff.change_type == ChangeType.MODIFIED and diff.changed_fields:
            for field, (old_val, new_val) in diff.changed_fields.items():
                if field == "type":
                    breaking_changes.append(
                        {
                            "component_id": diff.id,
                            "component_name": diff.name,
                            "change_type": "type_changed",
                            "field": field,
                            "old_value": old_val,
                            "new_value": new_val,
                            "severity": "high",
                            "description": f"Data type changed from '{_format_diff_value(old_val, truncate=False)}' to '{_format_diff_value(new_val, truncate=False)}'",
                        },
                    )
                elif field == "schemaPath":
                    breaking_changes.append(
                        {
                            "component_id": diff.id,
                            "component_name": diff.name,
                            "change_type": "schema_changed",
                            "field": field,
                            "old_value": old_val,
                            "new_value": new_val,
                            "severity": "medium",
                            "description": f"Schema path changed from '{_format_diff_value(old_val, truncate=False)}' to '{_format_diff_value(new_val, truncate=False)}'",
                        },
                    )

    return breaking_changes


def write_diff_json_output(
    diff_result: DiffResult,
    base_filename: str,
    output_dir: str | Path,
    logger: logging.Logger,
    changes_only: bool = False,
) -> str:
    """
    Write diff comparison to JSON format.

    Args:
        diff_result: The DiffResult to output
        base_filename: Base filename without extension
        output_dir: Output directory path
        logger: Logger instance
        changes_only: Only include changed items

    Returns:
        Path to JSON output file
    """
    try:
        logger.info("Generating diff JSON output...")

        summary = diff_result.summary
        meta = diff_result.metadata_diff

        def serialize_component_diff(d: ComponentDiff) -> dict:
            return {
                "id": d.id,
                "name": d.name,
                "change_type": d.change_type.value,
                "changed_fields": {k: {"source": v[0], "target": v[1]} for k, v in (d.changed_fields or {}).items()},
                "source_data": d.source_data,
                "target_data": d.target_data,
            }

        def serialize_inventory_diff(d: InventoryItemDiff) -> dict:
            return {
                "id": d.id,
                "name": d.name,
                "change_type": d.change_type.value,
                "inventory_type": d.inventory_type,
                "changed_fields": {k: {"source": v[0], "target": v[1]} for k, v in (d.changed_fields or {}).items()},
                "source_data": d.source_data,
                "target_data": d.target_data,
            }

        # Filter diffs if changes_only
        metric_diffs = diff_result.metric_diffs
        dimension_diffs = diff_result.dimension_diffs
        if changes_only:
            metric_diffs = [d for d in metric_diffs if d.change_type != ChangeType.UNCHANGED]
            dimension_diffs = [d for d in dimension_diffs if d.change_type != ChangeType.UNCHANGED]

        json_data = {
            "metadata": {
                "generated_at": diff_result.generated_at,
                "tool_version": diff_result.tool_version,
                "source_label": diff_result.source_label,
                "target_label": diff_result.target_label,
            },
            "source": {
                "id": meta.source_id,
                "name": meta.source_name,
                "owner": meta.source_owner,
                "description": meta.source_description,
            },
            "target": {
                "id": meta.target_id,
                "name": meta.target_name,
                "owner": meta.target_owner,
                "description": meta.target_description,
            },
            "summary": {
                "source_metrics_count": summary.source_metrics_count,
                "target_metrics_count": summary.target_metrics_count,
                "source_dimensions_count": summary.source_dimensions_count,
                "target_dimensions_count": summary.target_dimensions_count,
                "metrics_added": summary.metrics_added,
                "metrics_removed": summary.metrics_removed,
                "metrics_modified": summary.metrics_modified,
                "metrics_unchanged": summary.metrics_unchanged,
                "metrics_change_percent": summary.metrics_change_percent,
                "dimensions_added": summary.dimensions_added,
                "dimensions_removed": summary.dimensions_removed,
                "dimensions_modified": summary.dimensions_modified,
                "dimensions_unchanged": summary.dimensions_unchanged,
                "dimensions_change_percent": summary.dimensions_change_percent,
                "has_changes": summary.has_changes,
                "total_changes": summary.total_changes,
                "total_added": summary.total_added,
                "total_removed": summary.total_removed,
                "total_modified": summary.total_modified,
                "total_summary": summary.total_summary,
            },
            "metric_diffs": [serialize_component_diff(d) for d in metric_diffs],
            "dimension_diffs": [serialize_component_diff(d) for d in dimension_diffs],
        }

        # Add inventory diffs if present
        if diff_result.has_inventory_diffs:
            inventory_summary = {}
            if summary.source_calc_metrics_count > 0 or summary.target_calc_metrics_count > 0:
                inventory_summary["calculated_metrics"] = {
                    "source_count": summary.source_calc_metrics_count,
                    "target_count": summary.target_calc_metrics_count,
                    "added": summary.calc_metrics_added,
                    "removed": summary.calc_metrics_removed,
                    "modified": summary.calc_metrics_modified,
                    "unchanged": summary.calc_metrics_unchanged,
                }
            if summary.source_segments_count > 0 or summary.target_segments_count > 0:
                inventory_summary["segments"] = {
                    "source_count": summary.source_segments_count,
                    "target_count": summary.target_segments_count,
                    "added": summary.segments_added,
                    "removed": summary.segments_removed,
                    "modified": summary.segments_modified,
                    "unchanged": summary.segments_unchanged,
                }
            json_data["inventory_summary"] = inventory_summary

            if diff_result.calc_metrics_diffs is not None:
                calc_diffs = diff_result.calc_metrics_diffs
                if changes_only:
                    calc_diffs = [d for d in calc_diffs if d.change_type != ChangeType.UNCHANGED]
                json_data["calculated_metrics_diffs"] = [serialize_inventory_diff(d) for d in calc_diffs]

            if diff_result.segments_diffs is not None:
                seg_diffs = diff_result.segments_diffs
                if changes_only:
                    seg_diffs = [d for d in seg_diffs if d.change_type != ChangeType.UNCHANGED]
                json_data["segments_diffs"] = [serialize_inventory_diff(d) for d in seg_diffs]

        json_file = os.path.join(output_dir, f"{base_filename}.json")
        with open(json_file, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Diff JSON file created: {json_file}")
        return json_file

    except (OSError, TypeError, ValueError) as e:
        logger.error(_format_error_msg("creating diff JSON file", error=e))
        raise


def write_diff_markdown_output(
    diff_result: DiffResult,
    base_filename: str,
    output_dir: str | Path,
    logger: logging.Logger,
    changes_only: bool = False,
    side_by_side: bool = False,
) -> str:
    """
    Write diff comparison to Markdown format.

    Args:
        diff_result: The DiffResult to output
        base_filename: Base filename without extension
        output_dir: Output directory path
        logger: Logger instance
        changes_only: Only include changed items
        side_by_side: Show side-by-side comparison for modified items

    Returns:
        Path to Markdown output file
    """
    try:
        logger.info("Generating diff Markdown output...")

        summary = diff_result.summary
        meta = diff_result.metadata_diff
        md_parts = []

        # Title
        md_parts.append("# Data View Comparison Report\n")

        # Metadata
        md_parts.append("## Comparison Details\n")
        md_parts.append(f"**{diff_result.source_label}:** {meta.source_name} (`{meta.source_id}`)")
        md_parts.append(f"**{diff_result.target_label}:** {meta.target_name} (`{meta.target_id}`)")
        md_parts.append(f"**Generated:** {diff_result.generated_at}")
        md_parts.append(f"**Tool Version:** {diff_result.tool_version}\n")

        # Summary table
        md_parts.append("## Summary\n")
        md_parts.append(
            f"| Component | {diff_result.source_label} | {diff_result.target_label} | Added | Removed | Modified | Unchanged | Changed |",
        )
        md_parts.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        md_parts.append(
            f"| Metrics | {summary.source_metrics_count} | {summary.target_metrics_count} | "
            f"+{summary.metrics_added} | -{summary.metrics_removed} | ~{summary.metrics_modified} | "
            f"{summary.metrics_unchanged} | {summary.metrics_change_percent:.1f}% |",
        )
        md_parts.append(
            f"| Dimensions | {summary.source_dimensions_count} | {summary.target_dimensions_count} | "
            f"+{summary.dimensions_added} | -{summary.dimensions_removed} | ~{summary.dimensions_modified} | "
            f"{summary.dimensions_unchanged} | {summary.dimensions_change_percent:.1f}% |",
        )

        # Add inventory rows to summary if present
        if diff_result.has_inventory_diffs:
            if summary.source_calc_metrics_count > 0 or summary.target_calc_metrics_count > 0:
                md_parts.append(
                    f"| **Calc Metrics** | {summary.source_calc_metrics_count} | {summary.target_calc_metrics_count} | "
                    f"+{summary.calc_metrics_added} | -{summary.calc_metrics_removed} | ~{summary.calc_metrics_modified} | "
                    f"{summary.calc_metrics_unchanged} | - |",
                )
            if summary.source_segments_count > 0 or summary.target_segments_count > 0:
                md_parts.append(
                    f"| **Segments** | {summary.source_segments_count} | {summary.target_segments_count} | "
                    f"+{summary.segments_added} | -{summary.segments_removed} | ~{summary.segments_modified} | "
                    f"{summary.segments_unchanged} | - |",
                )
        md_parts.append("")

        if not summary.has_changes:
            md_parts.append("**✓ No differences found.**\n")
        else:
            md_parts.append(f"**Total: {summary.total_summary}**\n")

        # Metrics changes
        metric_changes = [d for d in diff_result.metric_diffs if d.change_type != ChangeType.UNCHANGED]
        if metric_changes or not changes_only:
            md_parts.append("## Metrics Changes\n")
            if metric_changes:
                md_parts.append("| Status | ID | Name | Details |")
                md_parts.append("| --- | --- | --- | --- |")
                for diff in metric_changes:
                    symbol = _get_change_emoji(diff.change_type)
                    detail = _get_change_detail(diff).replace("|", "\\|")
                    md_parts.append(f"| {symbol} | `{diff.id}` | {diff.name} | {detail} |")

                # Add side-by-side detail for modified items
                if side_by_side:
                    modified = [d for d in metric_changes if d.change_type == ChangeType.MODIFIED]
                    if modified:
                        md_parts.append("\n### Modified Metrics - Side by Side\n")
                        for diff in modified:
                            md_parts.extend(
                                _format_markdown_side_by_side(diff, diff_result.source_label, diff_result.target_label),
                            )
            else:
                md_parts.append("*No changes*")
            md_parts.append("")

        # Dimensions changes
        dim_changes = [d for d in diff_result.dimension_diffs if d.change_type != ChangeType.UNCHANGED]
        if dim_changes or not changes_only:
            md_parts.append("## Dimensions Changes\n")
            if dim_changes:
                md_parts.append("| Status | ID | Name | Details |")
                md_parts.append("| --- | --- | --- | --- |")
                for diff in dim_changes:
                    symbol = _get_change_emoji(diff.change_type)
                    detail = _get_change_detail(diff).replace("|", "\\|")
                    md_parts.append(f"| {symbol} | `{diff.id}` | {diff.name} | {detail} |")

                # Add side-by-side detail for modified items
                if side_by_side:
                    modified = [d for d in dim_changes if d.change_type == ChangeType.MODIFIED]
                    if modified:
                        md_parts.append("\n### Modified Dimensions - Side by Side\n")
                        for diff in modified:
                            md_parts.extend(
                                _format_markdown_side_by_side(diff, diff_result.source_label, diff_result.target_label),
                            )
            else:
                md_parts.append("*No changes*")
            md_parts.append("")

        # Inventory changes (if present)
        if diff_result.has_inventory_diffs:
            md_parts.append("---\n")
            md_parts.append("# Inventory Changes\n")

            # Calculated metrics inventory changes
            if diff_result.calc_metrics_diffs is not None:
                calc_changes = [d for d in diff_result.calc_metrics_diffs if d.change_type != ChangeType.UNCHANGED]
                md_parts.append(f"## Calculated Metrics Changes ({len(calc_changes)})\n")
                if calc_changes:
                    md_parts.append("| Status | ID | Name | Details |")
                    md_parts.append("| --- | --- | --- | --- |")
                    for diff in calc_changes:
                        symbol = _get_change_emoji(diff.change_type)
                        detail = _get_inventory_change_detail(diff).replace("|", "\\|")
                        md_parts.append(f"| {symbol} | `{diff.id}` | {diff.name} | {detail} |")
                else:
                    md_parts.append("*No changes*")
                md_parts.append("")

            # Segments inventory changes
            if diff_result.segments_diffs is not None:
                seg_changes = [d for d in diff_result.segments_diffs if d.change_type != ChangeType.UNCHANGED]
                md_parts.append(f"## Segments Changes ({len(seg_changes)})\n")
                if seg_changes:
                    md_parts.append("| Status | ID | Name | Details |")
                    md_parts.append("| --- | --- | --- | --- |")
                    for diff in seg_changes:
                        symbol = _get_change_emoji(diff.change_type)
                        detail = _get_inventory_change_detail(diff).replace("|", "\\|")
                        md_parts.append(f"| {symbol} | `{diff.id}` | {diff.name} | {detail} |")
                else:
                    md_parts.append("*No changes*")
                md_parts.append("")

        md_parts.append("---")
        md_parts.append("*Generated by CJA Auto SDR Generator*")

        markdown_file = os.path.join(output_dir, f"{base_filename}.md")
        with open(markdown_file, "w", encoding="utf-8") as f:
            f.write("\n".join(md_parts))

        logger.info(f"Diff Markdown file created: {markdown_file}")
        return markdown_file

    except (OSError, KeyError, TypeError, ValueError) as e:
        logger.error(_format_error_msg("creating diff Markdown file", error=e))
        raise


def _get_change_emoji(change_type: ChangeType) -> str:
    """Get emoji for change type"""
    emojis = {ChangeType.ADDED: "+", ChangeType.REMOVED: "-", ChangeType.MODIFIED: "~", ChangeType.UNCHANGED: ""}
    return emojis.get(change_type, "")


def _format_markdown_side_by_side(diff: ComponentDiff, source_label: str, target_label: str) -> list[str]:
    """
    Format a component diff as a side-by-side markdown table.

    Args:
        diff: The ComponentDiff to format
        source_label: Label for source side
        target_label: Label for target side

    Returns:
        List of markdown lines for the side-by-side view
    """
    lines = []
    if diff.change_type != ChangeType.MODIFIED or not diff.changed_fields:
        return lines

    # Component header
    lines.append(f"\n**`{diff.id}`** - {diff.name}\n")

    # Side-by-side table
    lines.append(f"| Field | {source_label} | {target_label} |")
    lines.append("| --- | --- | --- |")

    for field_name, (old_val, new_val) in diff.changed_fields.items():
        old_formatted = _format_diff_value(old_val, truncate=False)
        new_formatted = _format_diff_value(new_val, truncate=False)
        # Use italic for empty values in markdown
        old_str = "*(empty)*" if old_formatted == "(empty)" else old_formatted.replace("|", "\\|")
        new_str = "*(empty)*" if new_formatted == "(empty)" else new_formatted.replace("|", "\\|")

        # Truncate very long values
        if len(old_str) > 50:
            old_str = old_str[:47] + "..."
        if len(new_str) > 50:
            new_str = new_str[:47] + "..."

        lines.append(f"| `{field_name}` | {old_str} | {new_str} |")

    lines.append("")
    return lines


def write_diff_html_output(
    diff_result: DiffResult,
    base_filename: str,
    output_dir: str | Path,
    logger: logging.Logger,
    changes_only: bool = False,
) -> str:
    """
    Write diff comparison to HTML format with professional styling.

    Args:
        diff_result: The DiffResult to output
        base_filename: Base filename without extension
        output_dir: Output directory path
        logger: Logger instance
        changes_only: Only include changed items

    Returns:
        Path to HTML output file
    """
    try:
        logger.info("Generating diff HTML output...")

        _html_escape = html.escape  # Capture before nested functions shadow 'html'

        def _safe_html_escape(value: Any) -> str:
            """Escape arbitrary values safely for HTML rendering."""
            return _html_escape("" if value is None else str(value))

        summary = diff_result.summary
        meta = diff_result.metadata_diff
        html_parts = []

        # HTML header with CSS
        html_parts.append("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Data View Comparison Report</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            color: #333;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
            border-radius: 8px;
        }
        h1 {
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }
        h2 {
            color: #34495e;
            margin-top: 30px;
            border-left: 4px solid #3498db;
            padding-left: 15px;
        }
        .metadata {
            background-color: #ecf0f1;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .summary-table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }
        .summary-table th, .summary-table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        .summary-table th {
            background-color: #3498db;
            color: white;
        }
        .diff-table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 14px;
        }
        .diff-table th {
            background-color: #34495e;
            color: white;
            padding: 12px;
            text-align: left;
        }
        .diff-table td {
            padding: 10px 12px;
            border-bottom: 1px solid #ddd;
        }
        .row-added {
            background-color: #d4edda !important;
        }
        .row-removed {
            background-color: #f8d7da !important;
        }
        .row-modified {
            background-color: #fff3cd !important;
        }
        .badge {
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 12px;
        }
        .badge-added { background-color: #28a745; color: white; }
        .badge-removed { background-color: #dc3545; color: white; }
        .badge-modified { background-color: #ffc107; color: black; }
        .no-changes {
            color: #28a745;
            font-weight: bold;
            font-size: 18px;
            text-align: center;
            padding: 20px;
        }
        .total-changes {
            font-size: 18px;
            font-weight: bold;
            margin: 20px 0;
        }
        .footer {
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            text-align: center;
            color: #7f8c8d;
            font-size: 12px;
        }
        code {
            background-color: #f8f9fa;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Consolas', monospace;
            font-size: 13px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Data View Comparison Report</h1>
""")

        # Metadata section
        html_parts.append(f"""
        <div class="metadata">
            <p><strong>{_safe_html_escape(diff_result.source_label)}:</strong> {_safe_html_escape(meta.source_name)} (<code>{_safe_html_escape(meta.source_id)}</code>)</p>
            <p><strong>{_safe_html_escape(diff_result.target_label)}:</strong> {_safe_html_escape(meta.target_name)} (<code>{_safe_html_escape(meta.target_id)}</code>)</p>
            <p><strong>Generated:</strong> {_safe_html_escape(diff_result.generated_at)}</p>
        </div>
""")

        # Summary table
        html_parts.append(f"""
        <h2>Summary</h2>
        <table class="summary-table">
            <tr>
                <th>Component</th>
                <th>{_safe_html_escape(diff_result.source_label)}</th>
                <th>{_safe_html_escape(diff_result.target_label)}</th>
                <th>Added</th>
                <th>Removed</th>
                <th>Modified</th>
                <th>Unchanged</th>
                <th>Changed</th>
            </tr>
            <tr>
                <td>Metrics</td>
                <td>{summary.source_metrics_count}</td>
                <td>{summary.target_metrics_count}</td>
                <td><span class="badge badge-added">+{summary.metrics_added}</span></td>
                <td><span class="badge badge-removed">-{summary.metrics_removed}</span></td>
                <td><span class="badge badge-modified">~{summary.metrics_modified}</span></td>
                <td>{summary.metrics_unchanged}</td>
                <td>{summary.metrics_change_percent:.1f}%</td>
            </tr>
            <tr>
                <td>Dimensions</td>
                <td>{summary.source_dimensions_count}</td>
                <td>{summary.target_dimensions_count}</td>
                <td><span class="badge badge-added">+{summary.dimensions_added}</span></td>
                <td><span class="badge badge-removed">-{summary.dimensions_removed}</span></td>
                <td><span class="badge badge-modified">~{summary.dimensions_modified}</span></td>
                <td>{summary.dimensions_unchanged}</td>
                <td>{summary.dimensions_change_percent:.1f}%</td>
            </tr>
        </table>
""")

        # Add inventory rows to summary if present
        if diff_result.has_inventory_diffs:
            inv_rows = []
            if summary.source_calc_metrics_count > 0 or summary.target_calc_metrics_count > 0:
                inv_rows.append(f"""
            <tr>
                <td><strong>Calc Metrics</strong></td>
                <td>{summary.source_calc_metrics_count}</td>
                <td>{summary.target_calc_metrics_count}</td>
                <td><span class="badge badge-added">+{summary.calc_metrics_added}</span></td>
                <td><span class="badge badge-removed">-{summary.calc_metrics_removed}</span></td>
                <td><span class="badge badge-modified">~{summary.calc_metrics_modified}</span></td>
                <td>{summary.calc_metrics_unchanged}</td>
                <td>-</td>
            </tr>""")
            if summary.source_segments_count > 0 or summary.target_segments_count > 0:
                inv_rows.append(f"""
            <tr>
                <td><strong>Segments</strong></td>
                <td>{summary.source_segments_count}</td>
                <td>{summary.target_segments_count}</td>
                <td><span class="badge badge-added">+{summary.segments_added}</span></td>
                <td><span class="badge badge-removed">-{summary.segments_removed}</span></td>
                <td><span class="badge badge-modified">~{summary.segments_modified}</span></td>
                <td>{summary.segments_unchanged}</td>
                <td>-</td>
            </tr>""")
            if inv_rows:
                # Insert inventory rows before the closing </table> tag
                html_parts[-1] = html_parts[-1].replace("</table>", "".join(inv_rows) + "\n        </table>")

        if not summary.has_changes:
            html_parts.append('<p class="no-changes">No differences found.</p>')
        else:
            html_parts.append(f'<p class="total-changes">Total changes: {summary.total_changes}</p>')

        # Helper function to generate diff table
        def generate_diff_table(diffs: list[ComponentDiff], title: str):
            changes = [d for d in diffs if d.change_type != ChangeType.UNCHANGED]
            if not changes and changes_only:
                return ""

            html = f"<h2>{title}</h2>\n"
            if not changes:
                html += "<p><em>No changes</em></p>\n"
                return html

            html += """<table class="diff-table">
                <tr>
                    <th>Status</th>
                    <th>ID</th>
                    <th>Name</th>
                    <th>Details</th>
                </tr>"""

            for diff in changes:
                row_class = f"row-{diff.change_type.value}"
                badge_class = f"badge-{diff.change_type.value}"
                badge_text = diff.change_type.value.upper()
                detail = _get_change_detail(diff)
                detail_escaped = _html_escape(detail)

                html += f"""
                <tr class="{row_class}">
                    <td><span class="badge {badge_class}">{badge_text}</span></td>
                    <td><code>{_html_escape(str(diff.id))}</code></td>
                    <td>{_html_escape(str(diff.name))}</td>
                    <td>{detail_escaped}</td>
                </tr>"""

            html += "</table>\n"
            return html

        html_parts.append(generate_diff_table(diff_result.metric_diffs, "Metrics Changes"))
        html_parts.append(generate_diff_table(diff_result.dimension_diffs, "Dimensions Changes"))

        # Inventory diff sections (if present)
        if diff_result.has_inventory_diffs:

            def generate_inventory_diff_table(diffs: list[InventoryItemDiff] | None, title: str):
                if diffs is None:
                    return ""
                changes = [d for d in diffs if d.change_type != ChangeType.UNCHANGED]
                if not changes and changes_only:
                    return ""

                html = f"<h2>{title}</h2>\n"
                if not changes:
                    html += "<p><em>No changes</em></p>\n"
                    return html

                html += """<table class="diff-table">
                    <tr>
                        <th>Status</th>
                        <th>ID</th>
                        <th>Name</th>
                        <th>Details</th>
                    </tr>"""

                for diff in changes:
                    row_class = f"row-{diff.change_type.value}"
                    badge_class = f"badge-{diff.change_type.value}"
                    badge_text = diff.change_type.value.upper()
                    detail = _get_inventory_change_detail(diff)
                    detail_escaped = _html_escape(detail)

                    html += f"""
                    <tr class="{row_class}">
                        <td><span class="badge {badge_class}">{badge_text}</span></td>
                        <td><code>{_html_escape(str(diff.id))}</code></td>
                        <td>{_html_escape(str(diff.name))}</td>
                        <td>{detail_escaped}</td>
                    </tr>"""

                html += "</table>\n"
                return html

            html_parts.append(
                "<h2 style='border-top: 2px solid #3498db; padding-top: 20px; margin-top: 30px;'>Inventory Changes</h2>",
            )
            html_parts.append(
                generate_inventory_diff_table(diff_result.calc_metrics_diffs, "Calculated Metrics Changes"),
            )
            html_parts.append(generate_inventory_diff_table(diff_result.segments_diffs, "Segments Changes"))

        # Footer
        html_parts.append(f"""
        <div class="footer">
            <p>Generated by CJA SDR Generator v{diff_result.tool_version}</p>
        </div>
    </div>
</body>
</html>
""")

        html_file = os.path.join(output_dir, f"{base_filename}.html")
        with open(html_file, "w", encoding="utf-8") as f:
            f.write("\n".join(html_parts))

        logger.info(f"Diff HTML file created: {html_file}")
        return html_file

    except (OSError, KeyError, TypeError, ValueError) as e:
        logger.error(_format_error_msg("creating diff HTML file", error=e))
        raise


def write_diff_excel_output(
    diff_result: DiffResult,
    base_filename: str,
    output_dir: str | Path,
    logger: logging.Logger,
    changes_only: bool = False,
) -> str:
    """
    Write diff comparison to Excel format with color-coded rows.

    Args:
        diff_result: The DiffResult to output
        base_filename: Base filename without extension
        output_dir: Output directory path
        logger: Logger instance
        changes_only: Only include changed items

    Returns:
        Path to Excel output file
    """
    try:
        logger.info("Generating diff Excel output...")

        summary = diff_result.summary
        meta = diff_result.metadata_diff
        excel_file = os.path.join(output_dir, f"{base_filename}.xlsx")

        with pd.ExcelWriter(excel_file, engine="xlsxwriter") as writer:
            workbook = writer.book

            # Define formats
            added_format = workbook.add_format({"bg_color": "#d4edda", "border": 1})
            removed_format = workbook.add_format({"bg_color": "#f8d7da", "border": 1})
            modified_format = workbook.add_format({"bg_color": "#fff3cd", "border": 1})
            normal_format = workbook.add_format({"border": 1})

            # Summary sheet - build rows dynamically
            summary_rows = [
                {
                    "Component": "Metrics",
                    diff_result.source_label: summary.source_metrics_count,
                    diff_result.target_label: summary.target_metrics_count,
                    "Added": summary.metrics_added,
                    "Removed": summary.metrics_removed,
                    "Modified": summary.metrics_modified,
                    "Unchanged": summary.metrics_unchanged,
                    "Changed %": f"{summary.metrics_change_percent:.1f}%",
                },
                {
                    "Component": "Dimensions",
                    diff_result.source_label: summary.source_dimensions_count,
                    diff_result.target_label: summary.target_dimensions_count,
                    "Added": summary.dimensions_added,
                    "Removed": summary.dimensions_removed,
                    "Modified": summary.dimensions_modified,
                    "Unchanged": summary.dimensions_unchanged,
                    "Changed %": f"{summary.dimensions_change_percent:.1f}%",
                },
            ]

            # Add inventory rows if present (check for actual inventory diffs)
            if diff_result.calc_metrics_diffs is not None:
                summary_rows.append(
                    {
                        "Component": "Calc Metrics",
                        diff_result.source_label: summary.source_calc_metrics_count,
                        diff_result.target_label: summary.target_calc_metrics_count,
                        "Added": summary.calc_metrics_added,
                        "Removed": summary.calc_metrics_removed,
                        "Modified": summary.calc_metrics_modified,
                        "Unchanged": summary.calc_metrics_unchanged,
                        "Changed %": f"{summary.calc_metrics_change_percent:.1f}%",
                    },
                )
            if diff_result.segments_diffs is not None:
                summary_rows.append(
                    {
                        "Component": "Segments",
                        diff_result.source_label: summary.source_segments_count,
                        diff_result.target_label: summary.target_segments_count,
                        "Added": summary.segments_added,
                        "Removed": summary.segments_removed,
                        "Modified": summary.segments_modified,
                        "Unchanged": summary.segments_unchanged,
                        "Changed %": f"{summary.segments_change_percent:.1f}%",
                    },
                )

            summary_df = pd.DataFrame(summary_rows)
            summary_df.to_excel(writer, sheet_name="Summary", index=False)

            # Metadata sheet
            metadata_data = {
                "Property": [
                    "Source ID",
                    "Source Name",
                    "Target ID",
                    "Target Name",
                    "Generated At",
                    "Has Changes",
                    "Total Changes",
                ],
                "Value": [
                    meta.source_id,
                    meta.source_name,
                    meta.target_id,
                    meta.target_name,
                    diff_result.generated_at,
                    str(summary.has_changes),
                    summary.total_changes,
                ],
            }
            metadata_df = pd.DataFrame(metadata_data)
            metadata_df.to_excel(writer, sheet_name="Metadata", index=False)

            # Helper function to write diff sheet
            def write_diff_sheet(diffs: list[ComponentDiff], sheet_name: str):
                if changes_only:
                    diffs = [d for d in diffs if d.change_type != ChangeType.UNCHANGED]

                if not diffs:
                    df = pd.DataFrame({"Message": ["No changes"]})
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                    return

                rows = [
                    {
                        "Status": diff.change_type.value.upper(),
                        "ID": diff.id,
                        "Name": diff.name,
                        "Details": _get_change_detail(diff),
                    }
                    for diff in diffs
                ]

                df = pd.DataFrame(rows)
                df.to_excel(writer, sheet_name=sheet_name, index=False)

                # Apply color formatting
                worksheet = writer.sheets[sheet_name]
                for row_idx, diff in enumerate(diffs, start=1):
                    if diff.change_type == ChangeType.ADDED:
                        fmt = added_format
                    elif diff.change_type == ChangeType.REMOVED:
                        fmt = removed_format
                    elif diff.change_type == ChangeType.MODIFIED:
                        fmt = modified_format
                    else:
                        fmt = normal_format

                    for col_idx in range(len(df.columns)):
                        worksheet.write(row_idx, col_idx, df.iloc[row_idx - 1, col_idx], fmt)

            write_diff_sheet(diff_result.metric_diffs, "Metrics Diff")
            write_diff_sheet(diff_result.dimension_diffs, "Dimensions Diff")

            # Helper function to write inventory diff sheet
            def write_inventory_diff_sheet(diffs: list[InventoryItemDiff] | None, sheet_name: str):
                if diffs is None:
                    return

                if changes_only:
                    diffs = [d for d in diffs if d.change_type != ChangeType.UNCHANGED]

                if not diffs:
                    df = pd.DataFrame({"Message": ["No changes"]})
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                    return

                rows = [
                    {
                        "Status": diff.change_type.value.upper(),
                        "ID": diff.id,
                        "Name": diff.name,
                        "Details": _get_inventory_change_detail(diff),
                    }
                    for diff in diffs
                ]

                df = pd.DataFrame(rows)
                df.to_excel(writer, sheet_name=sheet_name, index=False)

                # Apply color formatting
                worksheet = writer.sheets[sheet_name]
                for row_idx, diff in enumerate(diffs, start=1):
                    if diff.change_type == ChangeType.ADDED:
                        fmt = added_format
                    elif diff.change_type == ChangeType.REMOVED:
                        fmt = removed_format
                    elif diff.change_type == ChangeType.MODIFIED:
                        fmt = modified_format
                    else:
                        fmt = normal_format

                    for col_idx in range(len(df.columns)):
                        worksheet.write(row_idx, col_idx, df.iloc[row_idx - 1, col_idx], fmt)

            # Write inventory diff sheets if present
            if diff_result.calc_metrics_diffs is not None:
                write_inventory_diff_sheet(diff_result.calc_metrics_diffs, "Calc Metrics Diff")
            if diff_result.segments_diffs is not None:
                write_inventory_diff_sheet(diff_result.segments_diffs, "Segments Diff")

        logger.info(f"Diff Excel file created: {excel_file}")
        return excel_file

    except (OSError, KeyError, TypeError, ValueError) as e:
        logger.error(_format_error_msg("creating diff Excel file", error=e))
        raise


def write_diff_csv_output(
    diff_result: DiffResult,
    base_filename: str,
    output_dir: str | Path,
    logger: logging.Logger,
    changes_only: bool = False,
) -> str:
    """
    Write diff comparison to CSV files.

    Args:
        diff_result: The DiffResult to output
        base_filename: Base filename without extension
        output_dir: Output directory path
        logger: Logger instance
        changes_only: Only include changed items

    Returns:
        Path to output directory containing CSV files
    """
    try:
        logger.info("Generating diff CSV output...")

        summary = diff_result.summary
        meta = diff_result.metadata_diff

        # Create subdirectory for CSV files
        csv_dir = os.path.join(output_dir, f"{base_filename}_csv")
        os.makedirs(csv_dir, exist_ok=True)

        # Summary CSV - build rows dynamically
        summary_rows = [
            {
                "Component": "Metrics",
                "Source_Count": summary.source_metrics_count,
                "Target_Count": summary.target_metrics_count,
                "Added": summary.metrics_added,
                "Removed": summary.metrics_removed,
                "Modified": summary.metrics_modified,
                "Unchanged": summary.metrics_unchanged,
                "Changed_Percent": summary.metrics_change_percent,
            },
            {
                "Component": "Dimensions",
                "Source_Count": summary.source_dimensions_count,
                "Target_Count": summary.target_dimensions_count,
                "Added": summary.dimensions_added,
                "Removed": summary.dimensions_removed,
                "Modified": summary.dimensions_modified,
                "Unchanged": summary.dimensions_unchanged,
                "Changed_Percent": summary.dimensions_change_percent,
            },
        ]

        # Add inventory rows if present (check for actual inventory diffs)
        if diff_result.calc_metrics_diffs is not None:
            summary_rows.append(
                {
                    "Component": "Calc_Metrics",
                    "Source_Count": summary.source_calc_metrics_count,
                    "Target_Count": summary.target_calc_metrics_count,
                    "Added": summary.calc_metrics_added,
                    "Removed": summary.calc_metrics_removed,
                    "Modified": summary.calc_metrics_modified,
                    "Unchanged": summary.calc_metrics_unchanged,
                    "Changed_Percent": summary.calc_metrics_change_percent,
                },
            )
        if diff_result.segments_diffs is not None:
            summary_rows.append(
                {
                    "Component": "Segments",
                    "Source_Count": summary.source_segments_count,
                    "Target_Count": summary.target_segments_count,
                    "Added": summary.segments_added,
                    "Removed": summary.segments_removed,
                    "Modified": summary.segments_modified,
                    "Unchanged": summary.segments_unchanged,
                    "Changed_Percent": summary.segments_change_percent,
                },
            )

        pd.DataFrame(summary_rows).to_csv(os.path.join(csv_dir, "summary.csv"), index=False, encoding="utf-8")
        logger.info("  Created: summary.csv")

        # Metadata CSV
        metadata_data = {
            "Property": [
                "source_id",
                "source_name",
                "target_id",
                "target_name",
                "generated_at",
                "has_changes",
                "total_changes",
            ],
            "Value": [
                meta.source_id,
                meta.source_name,
                meta.target_id,
                meta.target_name,
                diff_result.generated_at,
                str(summary.has_changes),
                summary.total_changes,
            ],
        }
        pd.DataFrame(metadata_data).to_csv(os.path.join(csv_dir, "metadata.csv"), index=False, encoding="utf-8")
        logger.info("  Created: metadata.csv")

        # Helper function to write diff CSV
        def write_diff_csv(diffs: list[ComponentDiff], filename: str):
            if changes_only:
                diffs = [d for d in diffs if d.change_type != ChangeType.UNCHANGED]

            rows = [
                {
                    "status": diff.change_type.value,
                    "id": diff.id,
                    "name": diff.name,
                    "details": _get_change_detail(diff),
                }
                for diff in diffs
            ]

            pd.DataFrame(rows).to_csv(os.path.join(csv_dir, filename), index=False, encoding="utf-8")
            logger.info(f"  Created: {filename}")

        write_diff_csv(diff_result.metric_diffs, "metrics_diff.csv")
        write_diff_csv(diff_result.dimension_diffs, "dimensions_diff.csv")

        # Helper function to write inventory diff CSV
        def write_inventory_diff_csv(diffs: list[InventoryItemDiff] | None, filename: str):
            if diffs is None:
                return

            if changes_only:
                diffs = [d for d in diffs if d.change_type != ChangeType.UNCHANGED]

            rows = [
                {
                    "status": diff.change_type.value,
                    "id": diff.id,
                    "name": diff.name,
                    "details": _get_inventory_change_detail(diff),
                }
                for diff in diffs
            ]

            pd.DataFrame(rows).to_csv(os.path.join(csv_dir, filename), index=False, encoding="utf-8")
            logger.info(f"  Created: {filename}")

        # Write inventory diff CSVs if present
        if diff_result.calc_metrics_diffs is not None:
            write_inventory_diff_csv(diff_result.calc_metrics_diffs, "calc_metrics_diff.csv")
        if diff_result.segments_diffs is not None:
            write_inventory_diff_csv(diff_result.segments_diffs, "segments_diff.csv")

        logger.info(f"Diff CSV files created in: {csv_dir}")
        return csv_dir

    except (OSError, KeyError, TypeError, ValueError) as e:
        logger.error(_format_error_msg("creating diff CSV files", error=e))
        raise


def write_diff_output(
    diff_result: DiffResult,
    output_format: str,
    base_filename: str,
    output_dir: str | Path,
    logger: logging.Logger,
    changes_only: bool = False,
    summary_only: bool = False,
    side_by_side: bool = False,
    use_color: bool = True,
    group_by_field: bool = False,
    group_by_field_limit: int = 10,
) -> str | None:
    """
    Write diff comparison output in specified format(s).

    Args:
        diff_result: The DiffResult to output
        output_format: Output format ('console', 'json', 'markdown', 'html', 'excel', 'csv', 'all', 'pr-comment')
        base_filename: Base filename without extension
        output_dir: Output directory path
        logger: Logger instance
        changes_only: Only include changed items
        summary_only: Only show summary (console only)
        side_by_side: Show side-by-side comparison for modified items
        use_color: Use ANSI color codes in console output
        group_by_field: Group changes by field name instead of component
        group_by_field_limit: Max items per section in group-by-field output (0 = unlimited)

    Returns:
        Console output string (for console/pr-comment format) or None
    """
    os.makedirs(output_dir, exist_ok=True)
    output_files = []
    console_output = None

    # Handle group-by-field output mode
    if group_by_field and should_generate_format(output_format, "console"):
        console_output = write_diff_grouped_by_field_output(diff_result, use_color, group_by_field_limit)
        print(console_output)
        if output_format == "console":
            return console_output

    # Handle PR comment format
    if output_format == "pr-comment":
        console_output = write_diff_pr_comment_output(diff_result, changes_only)
        print(console_output)
        return console_output

    if should_generate_format(output_format, "console") and not group_by_field:
        console_output = write_diff_console_output(diff_result, changes_only, summary_only, side_by_side, use_color)
        print(console_output)

    if output_format == "console":
        return console_output

    if should_generate_format(output_format, "json"):
        output_files.append(write_diff_json_output(diff_result, base_filename, output_dir, logger, changes_only))

    if should_generate_format(output_format, "markdown"):
        output_files.append(
            write_diff_markdown_output(diff_result, base_filename, output_dir, logger, changes_only, side_by_side),
        )

    if should_generate_format(output_format, "html"):
        output_files.append(write_diff_html_output(diff_result, base_filename, output_dir, logger, changes_only))

    if should_generate_format(output_format, "excel"):
        output_files.append(write_diff_excel_output(diff_result, base_filename, output_dir, logger, changes_only))

    if should_generate_format(output_format, "csv"):
        output_files.append(write_diff_csv_output(diff_result, base_filename, output_dir, logger, changes_only))

    return console_output


# ==================== INVENTORY SUMMARY MODE ====================


def display_inventory_summary(
    data_view_id: str,
    data_view_name: str,
    derived_inventory: Any | None = None,
    calculated_inventory: Any | None = None,
    segments_inventory: Any | None = None,
    output_format: str = "console",
    output_dir: str | Path = ".",
    quiet: bool = False,
    inventory_order: list[str] | None = None,
) -> dict[str, Any]:
    """
    Display inventory summary statistics without generating full inventory sheets.

    Args:
        data_view_id: The data view ID
        data_view_name: Human-readable data view name
        derived_inventory: DerivedFieldInventory object (optional)
        calculated_inventory: CalculatedMetricsInventory object (optional)
        segments_inventory: SegmentsInventory object (optional)
        output_format: Output format - "console" or "json"
        output_dir: Directory for JSON output
        quiet: Suppress console output
        inventory_order: Order of inventory types as specified in CLI (default: ['segments', 'calculated', 'derived'])

    Returns:
        Dictionary with summary statistics
    """
    summary = {
        "data_view_id": data_view_id,
        "data_view_name": data_view_name,
        "timestamp": datetime.now(UTC).isoformat(),
        "inventories": {},
    }

    high_complexity_items = []

    # Process derived fields inventory
    if derived_inventory:
        derived_summary = derived_inventory.get_summary()
        summary["inventories"]["derived_fields"] = derived_summary

        # Collect high-complexity items (>=70)
        high_complexity_items.extend(
            {
                "type": "Derived Field",
                "name": field.component_name,
                "complexity": field.complexity_score,
                "summary": field.logic_summary[:60] + "..." if len(field.logic_summary) > 60 else field.logic_summary,
            }
            for field in derived_inventory.fields
            if field.complexity_score >= 70
        )

    # Process calculated metrics inventory
    if calculated_inventory:
        calc_summary = calculated_inventory.get_summary()
        summary["inventories"]["calculated_metrics"] = calc_summary

        # Collect high-complexity items (>=70)
        high_complexity_items.extend(
            {
                "type": "Calculated Metric",
                "name": metric.metric_name,
                "complexity": metric.complexity_score,
                "summary": metric.formula_summary[:60] + "..."
                if len(metric.formula_summary) > 60
                else metric.formula_summary,
            }
            for metric in calculated_inventory.metrics
            if metric.complexity_score >= 70
        )

    # Process segments inventory
    if segments_inventory:
        seg_summary = segments_inventory.get_summary()
        summary["inventories"]["segments"] = seg_summary

        # Collect high-complexity items (>=70)
        high_complexity_items.extend(
            {
                "type": "Segment",
                "name": segment.segment_name,
                "complexity": segment.complexity_score,
                "summary": segment.definition_summary[:60] + "..."
                if len(segment.definition_summary) > 60
                else segment.definition_summary,
            }
            for segment in segments_inventory.segments
            if segment.complexity_score >= 70
        )

    # Sort high-complexity items by score descending
    high_complexity_items.sort(key=lambda x: x["complexity"], reverse=True)
    summary["high_complexity_items"] = high_complexity_items

    # Console output
    if not quiet and output_format in ("console", "all"):
        print()
        print(ConsoleColors.bold(f"Inventory Summary: {data_view_name}"))
        print(ConsoleColors.dim(f"Data View ID: {data_view_id}"))
        print()

        # Determine display order (default: segments, calculated, derived)
        display_order = inventory_order or ["segments", "calculated", "derived"]

        # Helper functions for displaying each inventory type
        def display_segments():
            if "segments" not in summary["inventories"]:
                return
            ss = summary["inventories"]["segments"]
            print(ConsoleColors.cyan("Segments"))
            print(f"  Total:       {ss['total_segments']}")
            gov = ss.get("governance", {})
            if gov:
                print(f"  Approved:    {gov.get('approved_count', 0)}")
                print(f"  Shared:      {gov.get('shared_count', 0)}")
                print(f"  Tagged:      {gov.get('tagged_count', 0)}")
            containers = ss.get("container_types", {})
            if containers:
                container_str = ", ".join(f"{k}: {v}" for k, v in containers.items())
                print(f"  Containers:  {container_str}")
            print(f"  Complexity:  avg={ss['complexity']['average']:.1f}, max={ss['complexity']['max']:.1f}")
            if ss["complexity"]["high_complexity_count"] > 0:
                print(ConsoleColors.warning(f"  High (>=75): {ss['complexity']['high_complexity_count']}"))
            if ss["complexity"]["elevated_complexity_count"] > 0:
                print(ConsoleColors.dim(f"  Elevated (50-74): {ss['complexity']['elevated_complexity_count']}"))
            print()

        def display_calculated():
            if "calculated_metrics" not in summary["inventories"]:
                return
            cs = summary["inventories"]["calculated_metrics"]
            print(ConsoleColors.cyan("Calculated Metrics"))
            print(f"  Total:       {cs['total_calculated_metrics']}")
            gov = cs.get("governance", {})
            if gov:
                print(f"  Approved:    {gov.get('approved_count', 0)}")
                print(f"  Shared:      {gov.get('shared_count', 0)}")
                print(f"  Tagged:      {gov.get('tagged_count', 0)}")
            print(f"  Complexity:  avg={cs['complexity']['average']:.1f}, max={cs['complexity']['max']:.1f}")
            if cs["complexity"]["high_complexity_count"] > 0:
                print(ConsoleColors.warning(f"  High (>=75): {cs['complexity']['high_complexity_count']}"))
            if cs["complexity"]["elevated_complexity_count"] > 0:
                print(ConsoleColors.dim(f"  Elevated (50-74): {cs['complexity']['elevated_complexity_count']}"))
            print()

        def display_derived():
            if "derived_fields" not in summary["inventories"]:
                return
            ds = summary["inventories"]["derived_fields"]
            print(ConsoleColors.cyan("Derived Fields"))
            print(f"  Total:       {ds['total_derived_fields']}")
            print(f"  Metrics:     {ds['metrics_count']}")
            print(f"  Dimensions:  {ds['dimensions_count']}")
            print(f"  Complexity:  avg={ds['complexity']['average']:.1f}, max={ds['complexity']['max']:.1f}")
            if ds["complexity"]["high_complexity_count"] > 0:
                print(ConsoleColors.warning(f"  High (>=75): {ds['complexity']['high_complexity_count']}"))
            if ds["complexity"]["elevated_complexity_count"] > 0:
                print(ConsoleColors.dim(f"  Elevated (50-74): {ds['complexity']['elevated_complexity_count']}"))
            print()

        # Display in specified order
        display_funcs = {
            "segments": display_segments,
            "calculated": display_calculated,
            "derived": display_derived,
        }
        for inv_type in display_order:
            if inv_type in display_funcs:
                display_funcs[inv_type]()

        # High complexity warnings
        if high_complexity_items:
            print(ConsoleColors.warning(f"High-Complexity Items ({len(high_complexity_items)}):"))
            for item in high_complexity_items[:10]:  # Show top 10
                complexity = item["complexity"]
                print(f"  {ConsoleColors.bold(f'{complexity:3}')} {item['type']:18} {item['name']}")
                if item["summary"]:
                    print(f"       {ConsoleColors.dim(item['summary'])}")
            if len(high_complexity_items) > 10:
                print(ConsoleColors.dim(f"  ... and {len(high_complexity_items) - 10} more"))
            print()

    # JSON output
    if output_format in ("json", "all"):
        os.makedirs(output_dir, exist_ok=True)
        safe_name = re.sub(r"[^\w\-]", "_", data_view_name)[:50]
        json_path = Path(output_dir) / f"{safe_name}_inventory_summary.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(summary, f, indent=2, default=str)
        if not quiet:
            print(f"Summary saved to: {json_path}")

    return summary


def process_inventory_summary(
    data_view_id: str,
    config_file: str = "config.json",
    output_dir: str | Path = ".",
    log_level: str = "INFO",
    log_format: str = "text",
    output_format: str = "console",
    quiet: bool = False,
    profile: str | None = None,
    include_derived: bool = False,
    include_calculated: bool = False,
    include_segments: bool = False,
    inventory_order: list[str] | None = None,
) -> dict[str, Any]:
    """
    Process inventory summary mode - fetch inventory data and display statistics.

    Args:
        data_view_id: The data view ID to process
        config_file: Path to CJA config file
        output_dir: Directory for JSON output
        log_level: Logging level
        log_format: Log output format - "text" (default) or "json"
        output_format: Output format - "console" or "json"
        quiet: Suppress console output
        profile: Config profile name
        include_derived: Include derived fields inventory
        include_calculated: Include calculated metrics inventory
        include_segments: Include segments inventory
        inventory_order: Order of inventory types as specified in CLI

    Returns:
        Dictionary with summary statistics
    """
    base_logger = setup_logging(data_view_id, batch_mode=False, log_level=log_level, log_format=log_format)
    logger = with_log_context(base_logger, run_mode="inventory_summary", data_view_id=data_view_id)

    # Initialize CJA
    cja = initialize_cja(config_file, logger, profile=profile)
    if cja is None:
        print(ConsoleColors.error("ERROR: Failed to initialize CJA connection"), file=sys.stderr)
        return {"error": "CJA initialization failed"}

    # Get data view info
    try:
        lookup_data = cja.dataviews.get_single(data_view_id)
        dv_name = lookup_data.get("name", data_view_id) if isinstance(lookup_data, dict) else data_view_id
    except RECOVERABLE_CONFIG_API_EXCEPTIONS as e:
        print(ConsoleColors.error(f"ERROR: Failed to fetch data view: {e}"), file=sys.stderr)
        return {"error": str(e)}
    except (RuntimeError, AttributeError) as e:  # Residual non-API failures (e.g. cjapy internals)
        print(ConsoleColors.error(f"ERROR: Failed to fetch data view (unexpected): {e}"), file=sys.stderr)
        logger.debug("Unexpected error fetching data view", exc_info=True)
        return {"error": str(e)}

    if not quiet:
        print(ConsoleColors.info(f"Fetching inventory data for: {dv_name}"))

    derived_inventory = None
    calculated_inventory = None
    segments_inventory = None

    # Fetch derived fields inventory
    if include_derived:

        def _build_derived_inventory_summary() -> Any:
            from cja_auto_sdr.inventory.derived_fields import DerivedFieldInventoryBuilder

            # Need metrics and dimensions for derived fields
            metrics_data = cja.dataviews.get_metrics(data_view_id)
            dimensions_data = cja.dataviews.get_dimensions(data_view_id)

            metrics_df = pd.DataFrame(metrics_data) if metrics_data else pd.DataFrame()
            dimensions_df = pd.DataFrame(dimensions_data) if dimensions_data else pd.DataFrame()

            builder = DerivedFieldInventoryBuilder(logger=logger)
            derived = builder.build(metrics_df, dimensions_df, data_view_id, dv_name)
            if not quiet:
                print(ConsoleColors.dim(f"  Derived fields: {derived.total_derived_fields}"))
            return derived

        derived_inventory = _run_optional_inventory_step(
            logger=logger,
            inventory_label="derived fields inventory",
            summary_mode=True,
            build_inventory=_build_derived_inventory_summary,
            recoverable_exceptions=RECOVERABLE_INVENTORY_SUMMARY_EXCEPTIONS,
        )

    # Fetch calculated metrics inventory
    if include_calculated:

        def _build_calculated_inventory_summary() -> Any:
            from cja_auto_sdr.inventory.calculated_metrics import CalculatedMetricsInventoryBuilder

            builder = CalculatedMetricsInventoryBuilder(logger=logger)
            calculated = builder.build(cja, data_view_id, dv_name)
            if not quiet:
                print(ConsoleColors.dim(f"  Calculated metrics: {calculated.total_calculated_metrics}"))
            return calculated

        calculated_inventory = _run_optional_inventory_step(
            logger=logger,
            inventory_label="calculated metrics inventory",
            summary_mode=True,
            build_inventory=_build_calculated_inventory_summary,
            recoverable_exceptions=RECOVERABLE_INVENTORY_SUMMARY_EXCEPTIONS,
        )

    # Fetch segments inventory
    if include_segments:

        def _build_segments_inventory_summary() -> Any:
            from cja_auto_sdr.inventory.segments import SegmentsInventoryBuilder

            builder = SegmentsInventoryBuilder(logger=logger)
            segments = builder.build(cja, data_view_id, dv_name)
            if not quiet:
                print(ConsoleColors.dim(f"  Segments: {segments.total_segments}"))
            return segments

        segments_inventory = _run_optional_inventory_step(
            logger=logger,
            inventory_label="segments inventory",
            summary_mode=True,
            build_inventory=_build_segments_inventory_summary,
            recoverable_exceptions=RECOVERABLE_INVENTORY_SUMMARY_EXCEPTIONS,
        )

    # Display summary
    return display_inventory_summary(
        data_view_id=data_view_id,
        data_view_name=dv_name,
        derived_inventory=derived_inventory,
        calculated_inventory=calculated_inventory,
        segments_inventory=segments_inventory,
        output_format=output_format,
        output_dir=output_dir,
        quiet=quiet,
        inventory_order=inventory_order,
    )


# ==================== REFACTORED SINGLE DATAVIEW PROCESSING ====================


def process_single_dataview(
    data_view_id: str,
    config_file: str = "config.json",
    output_dir: str | Path = ".",
    log_level: str = "INFO",
    log_format: str = "text",
    output_format: str = "excel",
    enable_cache: bool = False,
    cache_size: int = 1000,
    cache_ttl: int = 3600,
    quiet: bool = False,
    skip_validation: bool = False,
    max_issues: int = 0,
    clear_cache: bool = False,
    show_timings: bool = False,
    metrics_only: bool = False,
    dimensions_only: bool = False,
    profile: str | None = None,
    shared_cache: SharedValidationCache | None = None,
    api_tuning_config: APITuningConfig | None = None,
    circuit_breaker_config: CircuitBreakerConfig | None = None,
    include_derived_inventory: bool = False,
    include_calculated_metrics: bool = False,
    include_segments_inventory: bool = False,
    inventory_only: bool = False,
    inventory_order: list[str] | None = None,
    quality_report_only: bool = False,
    allow_partial: bool = False,
    production_mode: bool = False,
    batch_id: str | None = None,
    processing_config: ProcessingConfig | None = None,
) -> ProcessingResult:
    """
    Process a single data view and generate SDR in specified format(s)

    Args:
        data_view_id: The data view ID to process (must start with 'dv_')
        config_file: Path to CJA config file (default: 'config.json')
        output_dir: Directory to save output files (default: current directory)
        log_level: Logging level - one of DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO)
        log_format: Log output format - "text" (default) or "json" for structured logging
        output_format: Output format - one of excel, csv, json, html, markdown, all (default: excel)
        enable_cache: Enable validation result caching (default: False)
        cache_size: Maximum cached validation results, >= 1 (default: 1000)
        cache_ttl: Cache time-to-live in seconds, >= 1 (default: 3600)
        quiet: Suppress non-error output (default: False)
        skip_validation: Skip data quality validation for faster processing (default: False)
        max_issues: Limit data quality issues to top N by severity, >= 0; 0 = all (default: 0)
        clear_cache: Clear validation cache before processing (default: False)
        show_timings: Display performance timing breakdown after processing (default: False)
        include_derived_inventory: Include derived field inventory in output (default: False)
        include_calculated_metrics: Include calculated metrics inventory in output (default: False)
        include_segments_inventory: Include segments inventory in output (default: False)
        inventory_only: Output only inventory sheets, skip standard SDR content (default: False)
        inventory_order: Order of inventory sheets as they appear in CLI (default: ['derived', 'calculated', 'segments'])
        quality_report_only: Validate and return quality issues without generating SDR files (default: False)
        allow_partial: Opt-in exploratory mode to continue on selected fail-closed boundaries (default: False)
        production_mode: Reduce per-issue warning log volume for production runs (default: False)
        batch_id: Optional batch correlation ID for structured logging context (default: None)

    Returns:
        ProcessingResult with processing details including success status, metrics/dimensions count,
        output file path, and any error messages
    """
    if processing_config is None:
        processing_config = ProcessingConfig(
            config_file=config_file,
            output_dir=output_dir,
            log_level=log_level,
            log_format=log_format,
            output_format=output_format,
            enable_cache=enable_cache,
            cache_size=cache_size,
            cache_ttl=cache_ttl,
            quiet=quiet,
            skip_validation=skip_validation,
            max_issues=max_issues,
            clear_cache=clear_cache,
            show_timings=show_timings,
            metrics_only=metrics_only,
            dimensions_only=dimensions_only,
            profile=profile,
            shared_cache=shared_cache,
            api_tuning_config=api_tuning_config,
            circuit_breaker_config=circuit_breaker_config,
            include_derived_inventory=include_derived_inventory,
            include_calculated_metrics=include_calculated_metrics,
            include_segments_inventory=include_segments_inventory,
            inventory_only=inventory_only,
            inventory_order=inventory_order,
            quality_report_only=quality_report_only,
            allow_partial=allow_partial,
            production_mode=production_mode,
            batch_id=batch_id,
        )

    config_file = processing_config.config_file
    output_dir = processing_config.output_dir
    log_level = processing_config.log_level
    log_format = processing_config.log_format
    output_format = processing_config.output_format
    enable_cache = processing_config.enable_cache
    cache_size = processing_config.cache_size
    cache_ttl = processing_config.cache_ttl
    quiet = processing_config.quiet
    skip_validation = processing_config.skip_validation
    max_issues = processing_config.max_issues
    clear_cache = processing_config.clear_cache
    show_timings = processing_config.show_timings
    metrics_only = processing_config.metrics_only
    dimensions_only = processing_config.dimensions_only
    profile = processing_config.profile
    shared_cache = processing_config.shared_cache
    api_tuning_config = processing_config.api_tuning_config
    circuit_breaker_config = processing_config.circuit_breaker_config
    include_derived_inventory = processing_config.include_derived_inventory
    include_calculated_metrics = processing_config.include_calculated_metrics
    include_segments_inventory = processing_config.include_segments_inventory
    inventory_only = processing_config.inventory_only
    inventory_order = processing_config.inventory_order
    quality_report_only = processing_config.quality_report_only
    allow_partial = processing_config.allow_partial
    production_mode = processing_config.production_mode
    batch_id = processing_config.batch_id

    start_time = time.time()

    # Setup logging for this data view
    base_logger = setup_logging(data_view_id, batch_mode=False, log_level=log_level, log_format=log_format)
    run_mode = "batch_worker" if batch_id else "single"
    logger = with_log_context(base_logger, run_mode=run_mode, data_view_id=data_view_id, batch_id=batch_id)
    perf_tracker = PerformanceTracker(logger)
    execution_policy = _build_processing_execution_policy(
        output_format=output_format,
        inventory_only=inventory_only,
        include_derived_inventory=include_derived_inventory,
        metrics_only=metrics_only,
        dimensions_only=dimensions_only,
        quality_report_only=quality_report_only,
        skip_validation=skip_validation,
    )
    allow_partial_for_sdr = allow_partial and not quality_report_only
    partial_reasons: list[str] = []

    def _finalize_result(
        *,
        data_view_name: str,
        success: bool,
        duration: float | None = None,
        partial_reasons_override: Iterable[str] | None = None,
        **kwargs: Any,
    ) -> ProcessingResult:
        """Build terminal results with the current partial-run context attached."""
        return _build_processing_result(
            data_view_id=data_view_id,
            data_view_name=data_view_name,
            success=success,
            duration=time.time() - start_time if duration is None else duration,
            partial_reasons=partial_reasons if partial_reasons_override is None else partial_reasons_override,
            **kwargs,
        )

    logger.debug(
        "Execution policy: formats=%s, embedded_metadata=%s, required_components=%s, validation_required=%s, run_validation=%s",
        sorted(execution_policy.requested_formats),
        execution_policy.emits_embedded_metadata,
        sorted(execution_policy.required_component_endpoints),
        execution_policy.validation_required_for_output,
        execution_policy.run_data_quality_validation,
    )

    try:
        # Initialize CJA
        cja = initialize_cja(config_file, logger, profile=profile)
        if cja is None:
            return _finalize_result(
                data_view_name="Unknown",
                success=False,
                error_message="CJA initialization failed",
                failure_code=FAILURE_CODE_CJA_INIT_FAILED,
                failure_reason="cja_initialization_failed",
            )

        logger.info("✓ CJA connection established successfully")

        # Fetch data with parallel optimization
        logger.info("=" * BANNER_WIDTH)
        logger.info("Starting optimized data fetch operations")
        logger.info("=" * BANNER_WIDTH)

        # Create circuit breaker if config provided
        circuit_breaker = None
        if circuit_breaker_config is not None:
            circuit_breaker = CircuitBreaker(config=circuit_breaker_config, logger=logger)
            logger.info(f"Circuit breaker enabled (failure_threshold={circuit_breaker_config.failure_threshold})")

        fetcher = ParallelAPIFetcher(
            cja,
            logger,
            perf_tracker,
            max_workers=DEFAULT_API_FETCH_WORKERS,
            quiet=quiet,
            tuning_config=api_tuning_config,
            circuit_breaker=circuit_breaker,
        )
        if api_tuning_config is not None:
            logger.info(
                f"API auto-tuning enabled (min={api_tuning_config.min_workers}, max={api_tuning_config.max_workers})",
            )

        metrics, dimensions, lookup_data = fetcher.fetch_all_data(data_view_id)

        # Validate fetched data view lookup metadata (defensive gate before processing).
        lookup_data, lookup_failure_reason, lookup_raw_type = _coerce_valid_dataview_lookup_payload(
            lookup_data,
            data_view_id=data_view_id,
        )
        if lookup_data is None:
            logger.error(
                "Data view validation failed — invalid lookup payload (%s)",
                lookup_failure_reason,
            )
            logger.debug(
                "Lookup payload rejected: raw_type=%s",
                lookup_raw_type,
            )
            return _finalize_result(
                data_view_name="Unknown",
                success=False,
                error_message="Data view validation failed",
                failure_code=FAILURE_CODE_DATAVIEW_LOOKUP_INVALID,
                failure_reason=f"lookup_payload_invalid:{lookup_failure_reason}",
            )
        logger.info("✓ Data view validated and fetched successfully")

        # Log tuner statistics if tuning was enabled
        tuner_stats = fetcher.get_tuner_statistics()
        if tuner_stats is not None and isinstance(tuner_stats, dict):
            logger.info(
                f"API tuner stats: {tuner_stats['scale_ups']} scale-ups, "
                f"{tuner_stats['scale_downs']} scale-downs, "
                f"avg response: {tuner_stats['average_response_ms']:.0f}ms",
            )

        fetch_statuses: dict[str, EndpointFetchStatus] = {}
        get_fetch_statuses = getattr(fetcher, "get_fetch_statuses", None)
        if callable(get_fetch_statuses):
            raw_fetch_statuses = get_fetch_statuses()
            if isinstance(raw_fetch_statuses, dict):
                fetch_statuses = raw_fetch_statuses

        required_component_endpoints = execution_policy.required_component_endpoints
        component_failures: list[str] = []
        nonblocking_component_failures: list[str] = []
        for endpoint in ("metrics", "dimensions"):
            status = fetch_statuses.get(endpoint)
            endpoint_status = getattr(status, "status", None)
            endpoint_reason = str(getattr(status, "reason", ""))
            endpoint_error = str(getattr(status, "error_message", ""))

            if endpoint_status == "failed":
                detail = endpoint_error or endpoint_reason or "unknown API failure"
                failure_message = f"{endpoint}: {detail}"
                if endpoint in required_component_endpoints:
                    component_failures.append(failure_message)
                else:
                    nonblocking_component_failures.append(failure_message)

        if nonblocking_component_failures:
            logger.warning(
                "Non-blocking component fetch failures for unrequested sections: %s",
                "; ".join(nonblocking_component_failures),
            )

        if component_failures:
            dv_name = lookup_data.get("name", "Unknown") if isinstance(lookup_data, dict) else "Unknown"
            if allow_partial_for_sdr:
                logger.warning(
                    "Component fetch failed for required sections, but continuing due to --allow-partial (exploratory mode).",
                )
                for failure in component_failures:
                    logger.warning(f"  - {failure}")
                failed_endpoints = sorted({part.split(":", 1)[0].strip() for part in component_failures if part})
                component_partial_reason = f"required_endpoints_failed:{','.join(failed_endpoints)}"
                if component_partial_reason not in partial_reasons:
                    partial_reasons.append(component_partial_reason)
            else:
                logger.critical("Component fetch failed. Refusing to generate a partial SDR.")
                for failure in component_failures:
                    logger.critical(f"  - {failure}")
                logger.info("=" * BANNER_WIDTH)
                logger.info("EXECUTION FAILED")
                logger.info("=" * BANNER_WIDTH)
                logger.info(f"Data View: {dv_name} ({data_view_id})")
                logger.info("Error: Component fetch failed")
                logger.info(f"Duration: {time.time() - start_time:.2f}s")
                logger.info("=" * BANNER_WIDTH)
                flush_logging_handlers(logger)
                failed_endpoints = sorted({part.split(":", 1)[0].strip() for part in component_failures if part})
                return _finalize_result(
                    data_view_name=dv_name,
                    success=False,
                    metrics_count=len(metrics),
                    dimensions_count=len(dimensions),
                    error_message=f"Component fetch failed: {'; '.join(component_failures)}",
                    failure_code=FAILURE_CODE_COMPONENT_FETCH_FAILED,
                    failure_reason=f"required_endpoints_failed:{','.join(failed_endpoints)}",
                )

        empty_required_component_endpoints = _resolve_empty_required_component_endpoints(
            required_component_endpoints=required_component_endpoints,
            metrics=metrics,
            dimensions=dimensions,
            fetch_statuses=fetch_statuses,
        )
        if empty_required_component_endpoints:
            dv_name = lookup_data.get("name", "Unknown") if isinstance(lookup_data, dict) else "Unknown"
            empty_required_components = ", ".join(empty_required_component_endpoints)
            missing_all_standard_components = (
                set(empty_required_component_endpoints) == STANDARD_COMPONENT_ENDPOINTS
                and required_component_endpoints == STANDARD_COMPONENT_ENDPOINTS
            )
            standard_sdr_allows_sparse_components = (
                required_component_endpoints == STANDARD_COMPONENT_ENDPOINTS
                and not quality_report_only
                and not include_derived_inventory
                and not inventory_only
                and not metrics_only
                and not dimensions_only
            )
            if standard_sdr_allows_sparse_components and not missing_all_standard_components:
                logger.warning(
                    "Standard SDR component payload was empty for one section; continuing with available data: %s",
                    empty_required_components,
                )
            elif allow_partial_for_sdr:
                logger.warning(
                    "Required component payloads were empty, but continuing due to --allow-partial (exploratory mode): %s",
                    empty_required_components,
                )
                partial_reason = f"required_endpoints_empty:{','.join(empty_required_component_endpoints)}"
                if missing_all_standard_components:
                    partial_reason = "required_components_empty"
                if partial_reason not in partial_reasons:
                    partial_reasons.append(partial_reason)
            else:
                if missing_all_standard_components:
                    logger.critical("No metrics or dimensions fetched. Cannot generate SDR.")
                    logger.critical("Possible causes:")
                    logger.critical("  1. Data view has no metrics or dimensions configured")
                    logger.critical("  2. Your API credentials lack permission to read components")
                    logger.critical("  3. The data view is newly created and not yet populated")
                    logger.critical("  4. API rate limiting or temporary service issue")
                    logger.critical("")
                    logger.critical("Troubleshooting steps:")
                    logger.critical("  - Verify the data view has components in the CJA UI")
                    logger.critical("  - Check your OAuth scopes include component read permissions")
                    logger.critical("  - Try running with --list-dataviews to verify access")
                else:
                    logger.critical(
                        "Required component payloads were empty for requested output sections: %s",
                        empty_required_components,
                    )
                logger.info("=" * BANNER_WIDTH)
                logger.info("EXECUTION FAILED")
                logger.info("=" * BANNER_WIDTH)
                logger.info(f"Data View: {dv_name} ({data_view_id})")
                if missing_all_standard_components:
                    logger.info("Error: No metrics or dimensions found")
                else:
                    logger.info(f"Error: Required component payloads were empty: {empty_required_components}")
                logger.info(f"Duration: {time.time() - start_time:.2f}s")
                logger.info("=" * BANNER_WIDTH)
                # Flush handlers to ensure log is written
                flush_logging_handlers(logger)
                failure_reason = f"required_endpoints_empty:{','.join(empty_required_component_endpoints)}"
                error_message = f"Required component payloads were empty: {empty_required_components}"
                if missing_all_standard_components:
                    failure_reason = "required_components_empty"
                    error_message = "No metrics or dimensions found - data view may be empty or inaccessible"
                return _finalize_result(
                    data_view_name=dv_name,
                    success=False,
                    error_message=error_message,
                    failure_code=FAILURE_CODE_REQUIRED_COMPONENTS_EMPTY,
                    failure_reason=failure_reason,
                )

        logger.info("Data fetch operations completed successfully")

        validation_result = _run_data_quality_validation(
            logger=logger,
            perf_tracker=perf_tracker,
            metrics=metrics,
            dimensions=dimensions,
            quiet=quiet,
            production_mode=production_mode,
            shared_cache=shared_cache,
            enable_cache=enable_cache,
            cache_size=cache_size,
            cache_ttl=cache_ttl,
            clear_cache=clear_cache,
            max_issues=max_issues,
            skip_validation=skip_validation,
            execution_policy=execution_policy,
        )
        data_quality_df = validation_result.data_quality_df
        dq_issues = validation_result.dq_issues
        severity_counts = validation_result.severity_counts
        validation_status = validation_result.status
        validation_status_detail = validation_result.status_detail
        validation_failed = validation_result.failed
        validation_error_message = validation_result.error_message

        if validation_failed and execution_policy.validation_required_for_output:
            dv_name = lookup_data.get("name", "Unknown") if isinstance(lookup_data, dict) else "Unknown"
            if allow_partial_for_sdr:
                logger.warning(
                    "Data quality validation failed at runtime, but continuing due to --allow-partial (exploratory mode).",
                )
                logger.warning("Validation error: %s", validation_error_message or "unknown")
                data_quality_df = _empty_data_quality_dataframe()
                dq_issues = []
                severity_counts = {}
                if "data_quality_validation_runtime_failed" not in partial_reasons:
                    partial_reasons.append("data_quality_validation_runtime_failed")
            else:
                logger.info("=" * BANNER_WIDTH)
                logger.info("EXECUTION FAILED")
                logger.info("=" * BANNER_WIDTH)
                logger.info(f"Data View: {dv_name} ({data_view_id})")
                logger.info("Error: Data quality validation failed")
                logger.info(f"Duration: {time.time() - start_time:.2f}s")
                logger.info("=" * BANNER_WIDTH)
                flush_logging_handlers(logger)
                return _finalize_result(
                    data_view_name=dv_name,
                    success=False,
                    metrics_count=len(metrics),
                    dimensions_count=len(dimensions),
                    dq_issues_count=len(dq_issues),
                    dq_issues=dq_issues,
                    dq_severity_counts=severity_counts,
                    error_message=f"Data quality validation failed: {validation_error_message}",
                    failure_code=FAILURE_CODE_DQ_VALIDATION_RUNTIME_FAILED,
                    failure_reason="data_quality_validation_runtime_failed",
                )

        if quality_report_only:
            dv_name = lookup_data.get("name", "Unknown") if isinstance(lookup_data, dict) else "Unknown"
            return _finalize_result(
                data_view_name=dv_name,
                success=True,
                metrics_count=len(metrics),
                dimensions_count=len(dimensions),
                dq_issues_count=len(dq_issues),
                dq_issues=dq_issues,
                dq_severity_counts=severity_counts,
                error_message="",
            )

        # Optional inventory builds (parallelized when 2+ are enabled)
        derived_inventory_df = pd.DataFrame()
        derived_inventory_obj = None  # Store inventory object for JSON output
        calculated_metrics_df = pd.DataFrame()
        calculated_inventory_obj = None  # Store inventory object for JSON output
        segments_inventory_df = pd.DataFrame()
        segments_inventory_obj = None  # Store inventory object for JSON output

        # Collect enabled inventory tasks — closures defined conditionally.
        # The shared logger is intentional; stdlib logging is thread-safe, but
        # emitted lines may interleave when inventories run concurrently.
        _inventory_tasks: list[tuple[str, Callable, Callable, str]] = []
        # Inventory builders for calculated metrics and segments both call API
        # methods on the same `cja` instance. Serialize those calls in case the
        # client/session object is not safe for concurrent method execution.
        cja_inventory_lock = threading.Lock()

        if include_derived_inventory:
            logger.info("=" * BANNER_WIDTH)
            logger.info("Building derived field inventory")
            logger.info("=" * BANNER_WIDTH)

            def _build_derived_inventory() -> tuple[Any, pd.DataFrame]:
                from cja_auto_sdr.inventory.derived_fields import DerivedFieldInventoryBuilder

                builder = DerivedFieldInventoryBuilder(logger=logger)
                dv_name = lookup_data.get("name", data_view_id) if isinstance(lookup_data, dict) else data_view_id
                derived_inventory = builder.build(metrics, dimensions, data_view_id, dv_name)

                derived_df = derived_inventory.get_dataframe()

                inv_summary = derived_inventory.get_summary()
                logger.info(
                    f"Derived field inventory: {inv_summary.get('total_derived_fields', 0)} fields "
                    f"({inv_summary.get('metrics_count', 0)} metrics, {inv_summary.get('dimensions_count', 0)} dimensions)",
                )
                return derived_inventory, derived_df

            def _handle_derived_import_error(error: ImportError) -> None:
                logger.warning(f"Could not import derived field inventory: {error}")
                logger.info("Skipping derived field inventory - module not available")

            _inventory_tasks.append(
                ("derived", _build_derived_inventory, _handle_derived_import_error, "derived field inventory")
            )

        if include_calculated_metrics:
            logger.info("=" * BANNER_WIDTH)
            logger.info("Building calculated metrics inventory")
            logger.info("=" * BANNER_WIDTH)

            def _build_calculated_inventory() -> tuple[Any, pd.DataFrame]:
                from cja_auto_sdr.inventory.calculated_metrics import CalculatedMetricsInventoryBuilder

                builder = CalculatedMetricsInventoryBuilder(logger=logger)
                dv_name = lookup_data.get("name", data_view_id) if isinstance(lookup_data, dict) else data_view_id
                with cja_inventory_lock:
                    calculated_inventory = builder.build(cja, data_view_id, dv_name)

                calculated_df = calculated_inventory.get_dataframe()

                calc_summary = calculated_inventory.get_summary()
                logger.info(f"Calculated metrics inventory: {calc_summary.get('total_calculated_metrics', 0)} metrics")
                return calculated_inventory, calculated_df

            def _handle_calculated_import_error(error: ImportError) -> None:
                logger.warning(f"Could not import calculated metrics inventory: {error}")
                logger.info("Skipping calculated metrics inventory - module not available")

            _inventory_tasks.append(
                (
                    "calculated",
                    _build_calculated_inventory,
                    _handle_calculated_import_error,
                    "calculated metrics inventory",
                )
            )

        if include_segments_inventory:
            logger.info("=" * BANNER_WIDTH)
            logger.info("Building segments inventory")
            logger.info("=" * BANNER_WIDTH)

            def _build_segments_inventory() -> tuple[Any, pd.DataFrame]:
                from cja_auto_sdr.inventory.segments import SegmentsInventoryBuilder

                builder = SegmentsInventoryBuilder(logger=logger)
                dv_name = lookup_data.get("name", data_view_id) if isinstance(lookup_data, dict) else data_view_id
                with cja_inventory_lock:
                    segments_inventory = builder.build(cja, data_view_id, dv_name)

                segments_df = segments_inventory.get_dataframe()

                seg_summary = segments_inventory.get_summary()
                logger.info(f"Segments inventory: {seg_summary.get('total_segments', 0)} segments")
                return segments_inventory, segments_df

            def _handle_segments_import_error(error: ImportError) -> None:
                logger.warning(f"Could not import segments inventory: {error}")
                logger.info("Skipping segments inventory - module not available")

            _inventory_tasks.append(
                ("segments", _build_segments_inventory, _handle_segments_import_error, "segments inventory")
            )

        def _assign_inventory_result(key: str, payload: Any) -> None:
            """Assign inventory result to the correct outer variables.

            This mutates outer state from the coordinator thread only.
            Worker threads only build payloads.
            """
            nonlocal derived_inventory_obj, derived_inventory_df
            nonlocal calculated_inventory_obj, calculated_metrics_df
            nonlocal segments_inventory_obj, segments_inventory_df
            if payload is None:
                return
            if key == "derived":
                derived_inventory_obj, derived_inventory_df = payload
            elif key == "calculated":
                calculated_inventory_obj, calculated_metrics_df = payload
            elif key == "segments":
                segments_inventory_obj, segments_inventory_df = payload

        if len(_inventory_tasks) >= PARALLEL_INVENTORY_MIN_TASKS:
            from concurrent.futures import ThreadPoolExecutor, as_completed

            with ThreadPoolExecutor(max_workers=len(_inventory_tasks)) as executor:
                futures = {}
                for key, build_fn, err_fn, label in _inventory_tasks:
                    future = executor.submit(
                        _run_optional_inventory_step,
                        logger=logger,
                        inventory_label=label,
                        summary_mode=False,
                        build_inventory=build_fn,
                        on_import_error=err_fn,
                    )
                    futures[future] = key
                # Keep assignment on the main thread in completion order.
                for future in as_completed(futures):
                    key = futures[future]
                    _assign_inventory_result(key, future.result())
        else:
            # Single inventory or none — run sequentially (no thread overhead)
            for key, build_fn, err_fn, label in _inventory_tasks:
                payload = _run_optional_inventory_step(
                    logger=logger,
                    inventory_label=label,
                    summary_mode=False,
                    build_inventory=build_fn,
                    on_import_error=err_fn,
                )
                _assign_inventory_result(key, payload)

        # Data processing
        logger.info("=" * BANNER_WIDTH)
        logger.info("Processing data for Excel export")
        logger.info("=" * BANNER_WIDTH)

        try:
            # Process lookup data into DataFrame
            logger.info("Processing data view lookup information...")
            lookup_data_copy = {k: [v] if not isinstance(v, (list, tuple)) else v for k, v in lookup_data.items()}
            max_length = max(len(v) for v in lookup_data_copy.values()) if lookup_data_copy else 1
            lookup_data_copy = {k: v + [None] * (max_length - len(v)) for k, v in lookup_data_copy.items()}
            lookup_df = pd.DataFrame(lookup_data_copy)
            logger.info(f"Processed lookup data with {len(lookup_df)} rows")
        except (KeyError, TypeError, ValueError) as e:
            logger.error(_format_error_msg("processing lookup data", error=e))
            lookup_df = pd.DataFrame({"Error": ["Failed to process data view information"]})

        try:
            # Enhanced metadata creation
            logger.info("Creating metadata summary...")
            metadata_df = _build_sdr_metadata_dataframe(
                data_view_id=data_view_id,
                lookup_data=lookup_data,
                metrics=metrics,
                dimensions=dimensions,
                fetch_statuses=fetch_statuses,
                validation_status=validation_status,
                validation_status_detail=validation_status_detail,
                dq_issues=dq_issues,
                severity_counts=severity_counts,
                partial_reasons=partial_reasons,
                segments_inventory_obj=segments_inventory_obj,
                calculated_inventory_obj=calculated_inventory_obj,
                derived_inventory_obj=derived_inventory_obj,
            )
            logger.info("Metadata created successfully")
        except (KeyError, TypeError, ValueError) as e:
            logger.error(_format_error_msg("creating metadata", error=e))
            metadata_df = pd.DataFrame({"Property": ["Error"], "Value": ["Failed to create metadata"]})

        # Function to format JSON cells
        def format_json_cell(value):
            """Format JSON objects for Excel display"""
            try:
                if isinstance(value, (dict, list)):
                    return json.dumps(value, indent=2)
                return value
            except (TypeError, ValueError) as e:
                logger.warning(f"Error formatting JSON cell: {e!s}")
                return str(value)

        try:
            # Apply JSON formatting to all dataframes
            logger.info("Applying JSON formatting to dataframes...")

            for col in lookup_df.columns:
                lookup_df[col] = lookup_df[col].map(format_json_cell)

            if not metrics.empty:
                for col in metrics.columns:
                    metrics[col] = metrics[col].map(format_json_cell)

            if not dimensions.empty:
                for col in dimensions.columns:
                    dimensions[col] = dimensions[col].map(format_json_cell)

            logger.info("JSON formatting applied successfully")
        except (KeyError, TypeError, ValueError) as e:
            logger.error(_format_error_msg("applying JSON formatting", error=e))

        # Create Excel file name
        try:
            dv_name = lookup_data.get("name", "Unknown") if isinstance(lookup_data, dict) else "Unknown"
            # Sanitize filename
            dv_name = "".join(c for c in dv_name if c.isalnum() or c in (" ", "-", "_")).rstrip()
            excel_file_name = f"CJA_DataView_{dv_name}_{data_view_id}_SDR.xlsx"

            # Add output directory path
            output_path = Path(output_dir) / excel_file_name
            logger.info(f"Excel file will be saved as: {output_path}")
        except (KeyError, TypeError, ValueError) as e:
            logger.error(_format_error_msg("creating filename", error=e))
            excel_file_name = f"CJA_DataView_{data_view_id}_SDR.xlsx"
            output_path = Path(output_dir) / excel_file_name

        # Prepare data for output generation
        logger.info("=" * BANNER_WIDTH)
        logger.info(f"Generating output in format: {output_format}")
        logger.info("=" * BANNER_WIDTH)

        # Prepare data dictionary for all formats
        # Keep standard section emission aligned with execution-policy decisions.
        emits_standard_sdr_sections = not execution_policy.inventory_only_omits_standard_sections
        if not emits_standard_sdr_sections:
            data_dict = {}
        else:
            data_dict = {
                "Metadata": metadata_df,
                "Data Quality": data_quality_df,
                "DataView Details": lookup_df,
                "Metrics": metrics,
                "Dimensions": dimensions,
            }

        # Add derived field inventory if available or placeholder if flag was used
        if not derived_inventory_df.empty:
            data_dict["Derived Fields"] = derived_inventory_df
        elif include_derived_inventory:
            data_dict["Derived Fields"] = pd.DataFrame(
                {
                    "Status": ["No derived fields found for this data view"],
                    "Data View ID": [data_view_id],
                    "Note": ["This data view has no derived fields configured"],
                },
            )

        # Add calculated metrics inventory if available or placeholder if flag was used
        if not calculated_metrics_df.empty:
            data_dict["Calculated Metrics"] = calculated_metrics_df
        elif include_calculated_metrics:
            data_dict["Calculated Metrics"] = pd.DataFrame(
                {
                    "Status": ["No calculated metrics found for this data view"],
                    "Data View ID": [data_view_id],
                    "Note": ["This data view has no associated calculated metrics"],
                },
            )

        # Add segments inventory if available or placeholder if flag was used
        if not segments_inventory_df.empty:
            data_dict["Segments"] = segments_inventory_df
        elif include_segments_inventory:
            data_dict["Segments"] = pd.DataFrame(
                {
                    "Status": ["No segments found for this data view"],
                    "Data View ID": [data_view_id],
                    "Note": ["This data view has no associated segments"],
                },
            )

        # Prepare metadata dictionary for JSON/HTML
        metadata_dict = {}
        if execution_policy.emits_embedded_metadata and not metadata_df.empty:
            metadata_dict = _metadata_dataframe_to_dict(metadata_df)

        # Base filename without extension
        base_filename = output_path.stem if isinstance(output_path, Path) else Path(output_path).stem

        # Determine which formats to generate
        if output_format == "all":
            formats_to_generate = ["excel", "csv", "json", "html", "markdown"]
        elif output_format in FORMAT_ALIASES:
            formats_to_generate = FORMAT_ALIASES[output_format]
        else:
            formats_to_generate = [output_format]

        output_files = []

        try:
            for fmt in formats_to_generate:
                if fmt == "excel":
                    logger.info("Generating Excel file...")
                    with pd.ExcelWriter(str(output_path), engine="xlsxwriter") as writer:
                        # Create format cache once for the entire workbook
                        # This improves performance by 15-25% by reusing format objects
                        format_cache = ExcelFormatCache(writer.book)

                        # Write sheets in order, with Data Quality first for visibility
                        sheets_to_write = []

                        # Skip standard sheets when output policy omits them.
                        if emits_standard_sdr_sections:
                            sheets_to_write.extend(
                                [
                                    (metadata_df, "Metadata"),
                                    (data_quality_df, "Data Quality"),
                                ],
                            )
                            sheets_to_write.append((lookup_df, "DataView"))
                            # Add component sheets based on filters
                            if not dimensions_only:
                                sheets_to_write.append((metrics, "Metrics"))
                            if not metrics_only:
                                sheets_to_write.append((dimensions, "Dimensions"))

                        # Add inventory sheets at the end, ordered by CLI argument order
                        inv_order = inventory_order or ["derived", "calculated", "segments"]
                        inventory_sheets = {
                            "derived": (derived_inventory_df, "Derived Fields", include_derived_inventory),
                            "calculated": (calculated_metrics_df, "Calculated Metrics", include_calculated_metrics),
                            "segments": (segments_inventory_df, "Segments", include_segments_inventory),
                        }
                        for inv_type in inv_order:
                            if inv_type in inventory_sheets:
                                df, name, flag_enabled = inventory_sheets[inv_type]
                                if not df.empty:
                                    sheets_to_write.append((df, name))
                                elif flag_enabled:
                                    # Add placeholder when flag was used but no data found
                                    placeholder_df = pd.DataFrame(
                                        {
                                            "Status": [f"No {name.lower()} found for this data view"],
                                            "Data View ID": [data_view_id],
                                            "Note": [
                                                "This data view has no associated " + name.lower().replace(" ", " "),
                                            ],
                                        },
                                    )
                                    sheets_to_write.append((placeholder_df, name))

                        for sheet_data, sheet_name in sheets_to_write:
                            try:
                                if sheet_data.empty:
                                    logger.warning(f"Sheet {sheet_name} is empty, creating placeholder")
                                    placeholder_df = pd.DataFrame({"Note": [f"No data available for {sheet_name}"]})
                                    apply_excel_formatting(writer, placeholder_df, sheet_name, logger, format_cache)
                                else:
                                    apply_excel_formatting(writer, sheet_data, sheet_name, logger, format_cache)
                            except (OutputError, OSError, KeyError, TypeError, ValueError) as e:
                                logger.error(f"Failed to write sheet {sheet_name}: {e!s}")
                                continue

                    logger.info(f"✓ Excel file created: {output_path}")
                    output_files.append(str(output_path))

                elif fmt == "csv":
                    csv_output = write_csv_output(data_dict, base_filename, output_dir, logger)
                    output_files.append(csv_output)

                elif fmt == "json":
                    inventory_objects = {
                        "derived": derived_inventory_obj,
                        "calculated": calculated_inventory_obj,
                        "segments": segments_inventory_obj,
                    }
                    json_output = write_json_output(
                        data_dict,
                        metadata_dict,
                        base_filename,
                        output_dir,
                        logger,
                        inventory_objects,
                    )
                    output_files.append(json_output)

                elif fmt == "html":
                    html_output = write_html_output(data_dict, metadata_dict, base_filename, output_dir, logger)
                    output_files.append(html_output)

                elif fmt == "markdown":
                    markdown_output = write_markdown_output(data_dict, metadata_dict, base_filename, output_dir, logger)
                    output_files.append(markdown_output)

            if len(output_files) > 1:
                logger.info(f"✓ SDR generation complete! {len(output_files)} files created")
                for file_path in output_files:
                    logger.info(f"  • {file_path}")
            else:
                logger.info(f"✓ SDR generation complete! File saved as: {output_files[0]}")

            primary_output_file, normalized_output_files = _normalize_output_artifact_state("", output_files)

            # Final summary
            logger.info("=" * BANNER_WIDTH)
            logger.info("EXECUTION SUMMARY")
            logger.info("=" * BANNER_WIDTH)
            logger.info(f"Data View: {dv_name} ({data_view_id})")
            logger.info(f"Metrics: {len(metrics)}")
            logger.info(f"Dimensions: {len(dimensions)}")
            logger.info(f"Data Quality Validation: {validation_status.title()}")
            if validation_status == "completed":
                logger.info(f"Data Quality Issues: {len(dq_issues)}")
            else:
                logger.info(f"Data Quality Issues: {validation_status_detail}")

            if validation_status == "completed" and dq_issues:
                logger.info("Data Quality Issues by Severity:")
                for severity, count in severity_counts.items():
                    logger.info(f"  {severity}: {count}")

            if len(normalized_output_files) > 1:
                logger.info("Output files:")
                for file_path in normalized_output_files:
                    logger.info(f"  • {file_path}")
            else:
                logger.info(f"Output file: {primary_output_file}")
            logger.info("=" * BANNER_WIDTH)

            logger.info("Script execution completed successfully")
            logger.info(perf_tracker.get_summary())

            # Display timing summary on stdout if requested
            if show_timings:
                print(perf_tracker.get_summary())

            duration = time.time() - start_time

            # Calculate total file size
            total_size = 0
            for file_path in output_files:
                try:
                    if os.path.isdir(file_path):
                        # For CSV directories, sum all files
                        for root, _dirs, files in os.walk(file_path):
                            for f in files:
                                total_size += os.path.getsize(os.path.join(root, f))
                    else:
                        total_size += os.path.getsize(file_path)
                except OSError:
                    pass

            # Collect inventory statistics for result
            segments_count = 0
            segments_high_complexity = 0
            calculated_metrics_count = 0
            calculated_metrics_high_complexity = 0
            derived_fields_count = 0
            derived_fields_high_complexity = 0

            if segments_inventory_obj:
                seg_summary = segments_inventory_obj.get_summary()
                segments_count = seg_summary.get("total_segments", 0)
                segments_high_complexity = seg_summary.get("complexity", {}).get("high_complexity_count", 0)

            if calculated_inventory_obj:
                calc_summary = calculated_inventory_obj.get_summary()
                calculated_metrics_count = calc_summary.get("total_calculated_metrics", 0)
                calculated_metrics_high_complexity = calc_summary.get("complexity", {}).get("high_complexity_count", 0)

            if derived_inventory_obj:
                derived_summary = derived_inventory_obj.get_summary()
                derived_fields_count = derived_summary.get("total_derived_fields", 0)
                derived_fields_high_complexity = derived_summary.get("complexity", {}).get("high_complexity_count", 0)

            return _finalize_result(
                data_view_name=dv_name,
                success=True,
                duration=duration,
                metrics_count=len(metrics),
                dimensions_count=len(dimensions),
                dq_issues_count=len(dq_issues),
                dq_issues=dq_issues,
                dq_severity_counts=severity_counts,
                output_file=primary_output_file,
                output_files=normalized_output_files,
                file_size_bytes=total_size,
                segments_count=segments_count,
                segments_high_complexity=segments_high_complexity,
                calculated_metrics_count=calculated_metrics_count,
                calculated_metrics_high_complexity=calculated_metrics_high_complexity,
                derived_fields_count=derived_fields_count,
                derived_fields_high_complexity=derived_fields_high_complexity,
            )

        except PermissionError as e:
            logger.critical(f"Permission denied writing to {output_path}. File may be open in another program.")
            logger.critical("Please close the file and try again.")
            logger.info("=" * BANNER_WIDTH)
            logger.info("EXECUTION FAILED")
            logger.info("=" * BANNER_WIDTH)
            logger.info(f"Data View: {dv_name} ({data_view_id})")
            logger.info("Error: Permission denied")
            logger.info(f"Duration: {time.time() - start_time:.2f}s")
            logger.info("=" * BANNER_WIDTH)
            flush_logging_handlers(logger)
            return _finalize_result(
                data_view_name=dv_name,
                success=False,
                error_message=f"Permission denied: {e!s}",
                failure_code=FAILURE_CODE_OUTPUT_PERMISSION_DENIED,
                failure_reason="output_permission_denied",
            )
        except (OSError, KeyError, TypeError, ValueError) as e:
            logger.critical(f"Failed to generate output file: {e!s}")
            logger.exception("Full exception details:")
            logger.info("=" * BANNER_WIDTH)
            logger.info("EXECUTION FAILED")
            logger.info("=" * BANNER_WIDTH)
            logger.info(f"Data View: {dv_name} ({data_view_id})")
            logger.info(f"Error: {e!s}")
            logger.info(f"Duration: {time.time() - start_time:.2f}s")
            logger.info("=" * BANNER_WIDTH)
            flush_logging_handlers(logger)
            return _finalize_result(
                data_view_name=dv_name,
                success=False,
                error_message=str(e),
                failure_code=FAILURE_CODE_OUTPUT_WRITE_FAILED,
                failure_reason=f"output_write_failed:{type(e).__name__}",
            )

    except Exception as e:  # Intentional: top-level processing boundary for API + runtime errors
        logger.critical(f"Unexpected error processing data view {data_view_id}: {e!s}")
        logger.exception("Full exception details:")
        logger.info("=" * BANNER_WIDTH)
        logger.info("EXECUTION FAILED")
        logger.info("=" * BANNER_WIDTH)
        logger.info(f"Data View ID: {data_view_id}")
        logger.info(f"Error: {e!s}")
        logger.info(f"Duration: {time.time() - start_time:.2f}s")
        logger.info("=" * BANNER_WIDTH)
        flush_logging_handlers(logger)
        return _finalize_result(
            data_view_name="Unknown",
            success=False,
            error_message=str(e),
            failure_code=FAILURE_CODE_UNEXPECTED_RUNTIME_ERROR,
            failure_reason=f"unexpected_runtime_error:{type(e).__name__}",
        )


# ==================== WORKER FUNCTION FOR MULTIPROCESSING ====================


def process_single_dataview_worker(args: WorkerArgs) -> ProcessingResult:
    """Worker function for multiprocessing."""
    from cja_auto_sdr.pipeline.workers import process_single_dataview_worker as _impl

    return _impl(args)


# ==================== BATCH PROCESSOR CLASS ====================


BatchProcessor = importlib.import_module("cja_auto_sdr.pipeline.batch").BatchProcessor


# ==================== DRY-RUN MODE ====================


def run_dry_run(data_views: list[str], config_file: str, logger: logging.Logger, profile: str | None = None) -> bool:
    """
    Validate configuration and connectivity without generating reports.

    Performs the following checks:
    1. Credential validation (profile, environment variables, or config file)
    2. CJA API connection test
    3. Data view accessibility verification

    Args:
        data_views: List of data view IDs to validate
        config_file: Path to configuration file
        logger: Logger instance
        profile: Optional profile name to use for credentials

    Returns:
        True if all validations pass, False otherwise
    """
    print()
    print("=" * BANNER_WIDTH)
    print("DRY-RUN MODE - Validating configuration and connectivity")
    print("=" * BANNER_WIDTH)
    print()

    all_passed = True

    def _dry_run_error_text(error: Exception) -> str:
        """Return a stable non-empty error string for user-facing dry-run output."""
        text = str(error).strip()
        return text or error.__class__.__name__

    # Step 1: Validate credentials
    print("[1/3] Validating credentials...")
    if profile:
        # Validate profile credentials
        try:
            profile_creds = load_profile_credentials(profile, logger)
            if profile_creds:
                print(f"  ✓ Profile '{profile}' found and valid")
            else:
                print(f"  ✗ Profile '{profile}' has no valid credentials")
                all_passed = False
        except ProfileNotFoundError:
            print(f"  ✗ Profile '{profile}' not found")
            all_passed = False
        except ProfileConfigError as e:
            print(f"  ✗ Profile '{profile}' configuration error: {e}")
            all_passed = False
    else:
        # Validate config file
        if validate_config_file(config_file, logger):
            print(f"  ✓ Configuration file '{config_file}' is valid")
        else:
            print("  ✗ Configuration file validation failed")
            all_passed = False

    if not all_passed:
        print()
        print("=" * BANNER_WIDTH)
        print("DRY-RUN FAILED - Fix configuration issues before proceeding")
        print("=" * BANNER_WIDTH)
        return False

    # Step 2: Test CJA connection
    print()
    print("[2/3] Testing CJA API connection...")
    try:
        success, source, _ = configure_cjapy(profile=profile, config_file=config_file, logger=logger)
        if not success:
            print(f"  ✗ Credential configuration failed: {source}")
            print()
            print("=" * BANNER_WIDTH)
            print("DRY-RUN FAILED - Cannot configure credentials")
            print("=" * BANNER_WIDTH)
            return False
        cja = cjapy.CJA()

        # Test API with getDataViews call (with retry for transient errors)
        available_dvs = make_api_call_with_retry(
            cja.getDataViews,
            logger=logger,
            operation_name="getDataViews (dry-run)",
        )
        if available_dvs is not None:
            dv_count = len(available_dvs) if hasattr(available_dvs, "__len__") else 0
            print("  ✓ API connection successful")
            print(f"  ✓ Found {dv_count} accessible data view(s)")
        else:
            print("  ⚠ API connection returned None - may be unstable")
            available_dvs = []
    except KeyboardInterrupt, SystemExit:
        print()
        print(ConsoleColors.warning("Dry-run cancelled."))
        raise
    except RECOVERABLE_CONFIG_API_EXCEPTIONS as e:
        print(f"  ✗ API connection failed: {_dry_run_error_text(e)}")
        all_passed = False
        print()
        print("=" * BANNER_WIDTH)
        print("DRY-RUN FAILED - Cannot connect to CJA API")
        print("=" * BANNER_WIDTH)
        return False
    except (RuntimeError, AttributeError) as e:  # Residual non-API failures (e.g. cjapy internals)
        logger.debug("Unexpected dry-run API connection failure", exc_info=True)
        print(f"  ✗ API connection failed: {_dry_run_error_text(e)}")
        all_passed = False
        print()
        print("=" * BANNER_WIDTH)
        print("DRY-RUN FAILED - Cannot connect to CJA API")
        print("=" * BANNER_WIDTH)
        return False

    # Step 3: Validate each data view
    print()
    print(f"[3/3] Validating {len(data_views)} data view(s)...")

    # Build set of available data view IDs for quick lookup
    available_ids = set()
    if available_dvs is not None and (
        (isinstance(available_dvs, pd.DataFrame) and not available_dvs.empty)
        or (not isinstance(available_dvs, pd.DataFrame) and available_dvs)
    ):
        for dv in available_dvs:
            if isinstance(dv, dict):
                available_ids.add(dv.get("id", ""))

    valid_count = 0
    invalid_count = 0
    total_metrics = 0
    total_dimensions = 0
    dv_details = []

    for dv_id in data_views:
        # Try to get data view info (with retry for transient errors)
        try:
            raw_dv_info = make_api_call_with_retry(
                cja.getDataView,
                dv_id,
                logger=logger,
                operation_name=f"getDataView({dv_id})",
            )
            dv_info, lookup_failure_reason, lookup_raw_type = _coerce_valid_dataview_lookup_payload(
                raw_dv_info,
                data_view_id=dv_id,
            )
            if dv_info is not None:
                dv_name = dv_info.get("name", "Unknown")

                # Fetch component counts for predictions
                metrics_count = _count_component_items_for_fetch_spec_with_retry(
                    cja,
                    dv_id,
                    _METRICS_COMPONENT_FETCH_SPEC,
                    logger=logger,
                )
                dimensions_count = _count_component_items_for_fetch_spec_with_retry(
                    cja,
                    dv_id,
                    _DIMENSIONS_COMPONENT_FETCH_SPEC,
                    logger=logger,
                )

                total_metrics += metrics_count
                total_dimensions += dimensions_count
                dv_details.append(
                    {"id": dv_id, "name": dv_name, "metrics": metrics_count, "dimensions": dimensions_count},
                )

                print(f"  ✓ {dv_id}: {dv_name}")
                print(f"      Components: {metrics_count} metrics, {dimensions_count} dimensions")
                valid_count += 1
            else:
                print(f"  ✗ {dv_id}: Not found or no access")
                print(f"      Lookup validation failed: {lookup_failure_reason}")
                logger.debug(
                    "Dry-run rejected lookup payload for %s: reason=%s raw_type=%s",
                    dv_id,
                    lookup_failure_reason,
                    lookup_raw_type,
                )
                invalid_count += 1
                all_passed = False
        except KeyboardInterrupt, SystemExit:
            print()
            print(ConsoleColors.warning("Validation cancelled."))
            raise
        except RECOVERABLE_CONFIG_API_EXCEPTIONS as e:
            print(f"  ✗ {dv_id}: Error - {e!s}")
            invalid_count += 1
            all_passed = False
        except (RuntimeError, AttributeError) as e:  # Residual non-API failures (e.g. cjapy internals)
            logger.debug(f"Unexpected dry-run validation error for {dv_id}: {e!s}", exc_info=True)
            print(f"  ✗ {dv_id}: Error - {_dry_run_error_text(e)}")
            invalid_count += 1
            all_passed = False

    # Calculate time estimates
    # Based on benchmarks: ~0.5s per component for validation, ~0.1s without
    total_components = total_metrics + total_dimensions
    est_time_with_validation = total_components * 0.01 + len(data_views) * 2  # API overhead per view
    est_time_skip_validation = total_components * 0.005 + len(data_views) * 1.5

    # Summary
    print()
    print("=" * BANNER_WIDTH)
    print("DRY-RUN SUMMARY")
    print("=" * BANNER_WIDTH)
    print("  Configuration: ✓ Valid")
    print("  API Connection: ✓ Connected")
    print(f"  Data Views: {valid_count} valid, {invalid_count} invalid")
    print()

    if valid_count > 0:
        print("  Predictions:")
        print(f"    Total components: {total_metrics} metrics + {total_dimensions} dimensions = {total_components}")
        print(f"    Est. time (with validation): ~{est_time_with_validation:.0f}s")
        print(f"    Est. time (--skip-validation): ~{est_time_skip_validation:.0f}s")
        print()

    if all_passed:
        print("✓ All validations passed - ready to generate reports")
        print()
        print("Run without --dry-run to generate SDR reports:")
        print(f"  cja_auto_sdr {' '.join(data_views)}")
    else:
        print("✗ Some validations failed - please fix issues before proceeding")

    print("=" * BANNER_WIDTH)

    return all_passed


# ==================== COMMAND-LINE INTERFACE ====================
# Canonical implementation lives in ``cli.parser``; re-exported here for
# backwards compatibility with code that imports from ``generator``.

from cja_auto_sdr.cli.parser import (
    _bounded_float,
    _safe_env_number,
    parse_arguments,
)

# ==================== DATA VIEW NAME RESOLUTION ====================


def is_data_view_id(identifier: str) -> bool:
    """
    Check if a string is a data view ID (starts with 'dv_')

    Args:
        identifier: String to check

    Returns:
        True if identifier is a data view ID, False if it's a name
    """
    return identifier.startswith("dv_")


def levenshtein_distance(s1: str, s2: str) -> int:
    """
    Calculate the Levenshtein (edit) distance between two strings.

    This is used to find similar data view names when exact match fails.

    Args:
        s1: First string
        s2: Second string

    Returns:
        The minimum number of single-character edits needed to transform s1 into s2
    """
    if len(s1) < len(s2):
        return levenshtein_distance(s2, s1)

    if len(s2) == 0:
        return len(s1)

    previous_row = range(len(s2) + 1)
    for i, c1 in enumerate(s1):
        current_row = [i + 1]
        for j, c2 in enumerate(s2):
            # j+1 instead of j since previous_row and current_row are one character longer
            insertions = previous_row[j + 1] + 1
            deletions = current_row[j] + 1
            substitutions = previous_row[j] + (c1 != c2)
            current_row.append(min(insertions, deletions, substitutions))
        previous_row = current_row

    return previous_row[-1]


def find_similar_names(
    target: str,
    available_names: list[str],
    max_suggestions: int = 3,
    max_distance: int | None = None,
) -> list[tuple[str, int]]:
    """
    Find names similar to the target using Levenshtein distance.

    Args:
        target: The name to find matches for
        available_names: List of available names to search
        max_suggestions: Maximum number of suggestions to return
        max_distance: Maximum edit distance to consider (default: half of target length + 2)

    Returns:
        List of (name, distance) tuples, sorted by distance (closest first)
    """
    if max_distance is None:
        max_distance = len(target) // 2 + 2

    # Calculate distances
    suggestions = []
    target_lower = target.lower()

    for name in available_names:
        # Check exact case-insensitive match first
        if name.lower() == target_lower:
            suggestions.append((name, 0))
            continue

        # Calculate distance
        distance = levenshtein_distance(target_lower, name.lower())
        if distance <= max_distance:
            suggestions.append((name, distance))

    # Sort by distance and return top matches
    suggestions.sort(key=lambda x: (x[1], x[0]))
    return suggestions[:max_suggestions]


# ==================== DATA VIEW CACHE ====================


class DataViewCache:
    """
    Thread-safe cache for data view listings to avoid repeated API calls.

    The cache has a configurable TTL and is automatically invalidated after
    the TTL expires. This is useful when performing multiple diff operations
    in the same session.
    """

    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
                    cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return
        self._cache: dict[str, tuple[list[dict], float]] = {}
        self._ttl_seconds = 300  # 5 minute default TTL
        self._initialized = True

    def get(self, cache_key: str) -> list[dict] | None:
        """
        Get cached data views for a context key.

        Args:
            cache_key: Cache key representing the credential/config context

        Returns:
            List of data view dicts if cached and not expired, None otherwise
        """
        with self._lock:
            if cache_key in self._cache:
                data, timestamp = self._cache[cache_key]
                if time.time() - timestamp < self._ttl_seconds:
                    return data
                # Expired - remove from cache
                del self._cache[cache_key]
            return None

    def set(self, cache_key: str, data: list[dict]) -> None:
        """
        Cache data views for a context key.

        Args:
            cache_key: Cache key representing the credential/config context
            data: List of data view dicts to cache
        """
        with self._lock:
            self._cache[cache_key] = (data, time.time())

    def clear(self) -> None:
        """Clear all cached data."""
        with self._lock:
            self._cache.clear()

    def set_ttl(self, seconds: int) -> None:
        """Set the cache TTL in seconds."""
        self._ttl_seconds = seconds


# Global cache instance
_data_view_cache = DataViewCache()


def _build_data_view_cache_key(
    config_file: str,
    credential_source: str,
    credentials: dict[str, str] | None = None,
    profile: str | None = None,
) -> str:
    """Build a stable cache key for data-view listings.

    Includes credential context so multiple profiles/credential sources using
    the same config path do not share stale cache entries.
    """
    config_path = str(Path(config_file).expanduser())
    with contextlib.suppress(OSError):
        config_path = str(Path(config_file).expanduser().resolve())

    normalized_credentials: dict[str, str] = {}
    if credentials:
        normalized_credentials = {
            key: str(value).strip() for key, value in credentials.items() if value is not None and str(value).strip()
        }
    credentials_fingerprint = hashlib.sha256(
        json.dumps(normalized_credentials, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8"),
    ).hexdigest()

    return "|".join(
        [
            config_path,
            str(profile or ""),
            str(credential_source or ""),
            credentials_fingerprint,
        ],
    )


def get_cached_data_views(cja, cache_key: str, logger: logging.Logger) -> list[dict]:
    """
    Get data views with caching support.

    Args:
        cja: CJA API instance
        cache_key: Cache key for the current credential/config context
        logger: Logger instance

    Returns:
        List of data view dicts
    """
    # Check cache first
    cached = _data_view_cache.get(cache_key)
    if cached is not None:
        logger.debug(f"Using cached data views ({len(cached)} entries)")
        return cached

    # Fetch from API
    logger.debug("Fetching data views from API (cache miss)")
    available_dvs = cja.getDataViews()

    if available_dvs is None:
        return []

    # Convert to list if DataFrame
    if isinstance(available_dvs, pd.DataFrame):
        available_dvs = available_dvs.to_dict("records")

    # Cache the result
    _data_view_cache.set(cache_key, available_dvs)
    logger.debug(f"Cached {len(available_dvs)} data views")

    return available_dvs


def prompt_for_selection(options: list[tuple[str, str]], prompt_text: str) -> str | None:
    from cja_auto_sdr.cli.interactive import prompt_for_selection as _impl

    return _impl(options, prompt_text)


@dataclass(frozen=True)
class NameResolutionDiagnostics:
    """Diagnostic metadata captured during data view name resolution."""

    error_type: str | None = None
    error_message: str | None = None
    resolved_name_by_id: dict[str, str] = field(default_factory=dict)


type NameResolutionResult = tuple[list[str], dict[str, list[str]]]
type NameResolutionResultWithDiagnostics = tuple[list[str], dict[str, list[str]], NameResolutionDiagnostics]


def _build_name_resolution_result(
    resolved_ids: list[str],
    name_to_ids_map: dict[str, list[str]],
    diagnostics: NameResolutionDiagnostics,
    *,
    include_diagnostics: bool,
) -> NameResolutionResult | NameResolutionResultWithDiagnostics:
    from cja_auto_sdr.cli.commands.stats import _build_name_resolution_result as _impl

    return _impl(
        resolved_ids=resolved_ids,
        name_to_ids_map=name_to_ids_map,
        diagnostics=diagnostics,
        include_diagnostics=include_diagnostics,
    )


def _coerce_name_resolution_result(
    result: NameResolutionResult | NameResolutionResultWithDiagnostics,
) -> NameResolutionResultWithDiagnostics:
    from cja_auto_sdr.cli.commands.stats import _coerce_name_resolution_result as _impl

    return _impl(result)


def _build_inspection_name_resolution_logger() -> logging.Logger:
    from cja_auto_sdr.cli.commands.stats import _build_inspection_name_resolution_logger as _impl

    return _impl()


def resolve_data_view_names(
    identifiers: list[str],
    config_file: str = "config.json",
    logger: logging.Logger | None = None,
    suggest_similar: bool = True,
    profile: str | None = None,
    match_mode: str = "exact",
    include_diagnostics: bool = False,
) -> NameResolutionResult | NameResolutionResultWithDiagnostics:
    from cja_auto_sdr.cli.commands.stats import resolve_data_view_names as _impl

    return _impl(
        identifiers=identifiers,
        config_file=config_file,
        logger=logger,
        suggest_similar=suggest_similar,
        profile=profile,
        match_mode=match_mode,
        include_diagnostics=include_diagnostics,
    )


# ==================== DATASET INFO HELPER ====================


def _extract_dataset_info(dataset: Any) -> dict:
    """
    Resilient parser for dataset objects from connection API responses.

    The dataSets field in connection responses may use varying field names.
    This helper tries common field names and falls back gracefully.

    Args:
        dataset: A dataset object (dict or other) from the dataSets array

    Returns:
        Dict with 'id' and 'name' keys (values may be 'N/A' if not found)
    """
    if not isinstance(dataset, dict):
        # Preserve previous fallback semantics for scalar falsey values while
        # avoiding ambiguous truthiness checks on pandas missing scalars.
        if _is_missing_discovery_value(dataset, treat_blank_string=True, treat_null_like_strings=True):
            return {"id": "N/A", "name": "N/A"}
        if isinstance(dataset, (bool, int, float)) and not dataset:
            return {"id": "N/A", "name": "N/A"}
        return {"id": _normalize_display_text(dataset, default="N/A"), "name": "N/A"}

    # Try common ID field names (prefer canonical/camelCase, keep snake_case for compatibility)
    ds_id = _pick_first_present_text(
        (
            dataset.get("id"),
            dataset.get("datasetId"),
            dataset.get("dataSetId"),
            dataset.get("dataset_id"),
        ),
        default="N/A",
        treat_null_like_strings=True,
    )

    # Try common name field names
    ds_name = _pick_first_present_text(
        (
            dataset.get("name"),
            dataset.get("datasetName"),
            dataset.get("dataSetName"),
            dataset.get("dataset_name"),
            dataset.get("title"),
        ),
        default="N/A",
        treat_null_like_strings=True,
    )

    return {"id": ds_id, "name": ds_name}


# ==================== LIST HELPERS ====================


def _emit_output(data: str, output_file: str | None, is_stdout: bool) -> None:
    """Emit output data to a file, stdout pipe, or the console.

    When output_file is None (no --output flag), falls through to print().
    When writing to a TTY and the output exceeds the terminal height,
    the text is piped through the system pager (``$PAGER``, defaulting
    to ``less -R``).
    """
    if output_file and not is_stdout:
        parent = os.path.dirname(output_file)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(output_file, "w", encoding="utf-8") as f:
            f.write(data)
    else:
        text = data.rstrip("\n")
        # Use a pager when output is longer than the terminal and stdout
        # is an interactive TTY (not a pipe / redirect).
        if not is_stdout and sys.stdout.isatty():
            line_count = text.count("\n") + 1
            try:
                term_height = os.get_terminal_size().lines
            except OSError:
                term_height = 0
            if term_height and line_count > term_height:
                pager_raw = os.environ.get("PAGER", "less")
                try:
                    pager_cmd = shlex.split(pager_raw)
                except ValueError:
                    pager_cmd = []
                if not pager_cmd:
                    pager_cmd = ["less"]

                pager_exec = pager_cmd[0]
                if shutil.which(pager_exec):
                    launch_cmd = [*pager_cmd]
                    if os.path.basename(pager_exec) == "less" and "-R" not in launch_cmd[1:]:
                        launch_cmd.append("-R")
                    try:
                        proc = subprocess.Popen(
                            launch_cmd,
                            stdin=subprocess.PIPE,
                        )
                        proc.communicate(text.encode("utf-8"), timeout=300)
                        return
                    except subprocess.TimeoutExpired:
                        proc.kill()
                    except OSError:
                        pass
                    # pager unavailable or timed out — fall through to plain print
        print(text)


# ==================== SHARED OUTPUT FORMATTERS ====================


def _format_as_json(payload: dict, *, contract_label: str = "Output") -> str:
    """Format a result dict as indented JSON with strict contract checks."""
    try:
        return json.dumps(payload, indent=2, allow_nan=False)
    except ValueError as exc:
        raise OutputContractError(
            f"{contract_label} contains non-JSON-compliant values",
        ) from exc


def _format_as_csv(columns: list[str], rows: list[dict]) -> str:
    """Format discovery rows as CSV with the given column headers."""
    buf = io.StringIO(newline="")
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(col, "") for col in columns])
    return buf.getvalue()


def _format_as_table(
    header_line: str,
    items: list[dict],
    columns: list[str],
    col_labels: list[str] | None = None,
) -> str:
    """Format discovery items as an aligned text table.

    Args:
        header_line: Summary line (e.g. "Found 5 accessible data view(s):").
        items: List of dicts, one per row.
        columns: Dict keys to include, in order.
        col_labels: Display labels for each column (defaults to title-cased keys).

    Returns:
        Formatted table string with leading/trailing blank lines.
    """
    labels = col_labels or [c.replace("_", " ").title() for c in columns]
    widths = [
        max(len(lbl), max((len(str(item.get(col, ""))) for item in items), default=0)) + 2
        for col, lbl in zip(columns, labels, strict=True)
    ]
    # Constrain total width to terminal so the last column wraps instead of overflowing
    term_width = shutil.get_terminal_size().columns
    if sum(widths) > term_width and len(widths) > 1:
        other_width = sum(widths[:-1])
        if other_width < term_width:
            widths[-1] = max(term_width - other_width, len(labels[-1]) + 2, 20)
    lines: list[str] = ["", header_line, ""]
    lines.append("".join(f"{lbl:<{w}}" for lbl, w in zip(labels, widths, strict=True)))
    lines.append("-" * min(sum(widths), term_width))
    for item in items:
        cells = [str(item.get(col, "")) for col in columns]
        last_text_w = widths[-1] - 2
        if len(cells[-1]) > last_text_w > 0:
            wrapped = textwrap.wrap(cells[-1], width=last_text_w) or [""]
            prefix = "".join(f"{cells[i]:<{widths[i]}}" for i in range(len(columns) - 1))
            lines.append(prefix + wrapped[0])
            indent = " " * sum(widths[:-1])
            lines.extend(indent + cont for cont in wrapped[1:])
        else:
            lines.append("".join(f"{item.get(col, '')!s:<{w}}" for col, w in zip(columns, widths, strict=True)))
    lines.append("")
    return "\n".join(lines)


def _format_discovery_json(payload: dict) -> str:
    """Format discovery payloads with a discovery-specific contract label."""
    try:
        return _format_as_json(payload, contract_label="Discovery output")
    except OutputContractError as exc:
        raise DiscoveryOutputContractError(str(exc)) from exc


def _extract_owner_name(owner_data: Any) -> str:
    """Extract a displayable owner name from an API owner object.

    The owner field varies across CJA API endpoints:
    - Data views may return ``{"name": "Jane Doe"}``
    - Connections may return ``{"imsUserId": "ABC@AdobeID"}``
    - Some endpoints return ``None`` or a bare string.
    """
    return _extract_owner_name_normalized(owner_data, default="N/A")


def _normalize_optional_text(value: Any, *, default: str = "") -> str:
    """Normalize optional display values, handling None/NaN and whitespace."""
    return _normalize_display_text(
        value,
        default=default,
        treat_null_like_strings=True,
    )


def _extract_owner_name_from_record(record: dict[str, Any]) -> str:
    """Extract owner name from record-level owner aliases used by CJA endpoints."""
    return _extract_owner_name_from_record_normalized(record, default="N/A")


def _extract_timestamp_from_record(record: dict[str, Any], field: str) -> str:
    """Extract created/modified timestamps from common CJA field aliases."""
    aliases_by_field = {
        "created": ("created", "createdDate", "createdAt", "created_date"),
        "modified": ("modified", "modifiedDate", "modifiedAt", "modified_date"),
    }
    aliases = aliases_by_field.get(field, (field,))
    for key in aliases:
        value = _normalize_optional_text(record.get(key))
        if value:
            return value
    return ""


def _extract_connections_list(raw_connections: Any) -> list:
    """Extract the connection list from a raw getConnections API response."""
    if isinstance(raw_connections, dict):
        connections = raw_connections.get("content", raw_connections.get("result", []))
        if not isinstance(connections, list):
            # content/result was an unexpected type (e.g. a string); wrap the
            # whole dict so downstream isinstance(conn, dict) checks can decide
            # whether to process or skip it.
            return [raw_connections]
        return connections
    if isinstance(raw_connections, list):
        return raw_connections
    return []


def _to_searchable_text(value: Any) -> str:
    """Convert nested values to text for filter/exclude matching."""
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


class DiscoveryArgumentError(ValueError):
    """Raised when discovery filter/sort arguments are invalid."""


class OutputContractError(ValueError):
    """Raised when machine-readable command output violates JSON contracts."""


class DiscoveryOutputContractError(OutputContractError):
    """Raised when machine-readable discovery output violates JSON contracts."""


class DiscoveryNotFoundError(LookupError):
    """Raised when a requested discovery resource is not found."""


_NUMERIC_SORT_VALUE_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")


def _is_machine_readable_output(output_format: str | None, output_file: str | None = None) -> bool:
    """Return True when command output is intended for machine consumption."""
    return output_format in ("json", "csv") or output_file in ("-", "stdout")


def _resolve_discovery_output_format(raw_format: str | None, *, output_to_stdout: bool) -> str:
    """Normalize discovery output format with stdout piping semantics."""
    return _resolve_command_output_format(
        raw_format,
        supported_formats={"json": "json", "csv": "csv", "console": "table", "table": "table"},
        fallback_format="table",
        output_to_stdout=output_to_stdout,
        stdout_fallback_format="json",
        stdout_allowed_formats={"json", "csv"},
        warning_scope="this command",
    )


def _emit_discovery_error(
    message: str,
    *,
    is_machine_readable: bool,
    error_type: str,
    additional_fields: dict[str, Any] | None = None,
    human_to_stderr: bool = False,
) -> None:
    """Emit discovery/inspection errors in machine or human-readable form."""
    if is_machine_readable:
        payload: dict[str, Any] = {"error": message, "error_type": error_type}
        if additional_fields:
            payload.update(additional_fields)
        print(json.dumps(payload, allow_nan=False), file=sys.stderr)
        return

    stream = sys.stderr if human_to_stderr else sys.stdout
    print(ConsoleColors.error(f"ERROR: {message}"), file=stream)


def _emit_output_contract_error(
    message: str,
    *,
    is_machine_readable: bool,
    human_to_stderr: bool = True,
) -> None:
    """Emit output-contract violations using a stable error envelope."""
    _emit_discovery_error(
        message,
        is_machine_readable=is_machine_readable,
        error_type="output_contract",
        human_to_stderr=human_to_stderr,
    )


def _emit_json_output(
    payload: dict[str, Any],
    *,
    output_file: str | None,
    is_stdout: bool,
    contract_label: str,
    human_error_to_stderr: bool = True,
) -> None:
    """Serialize payload to strict JSON and emit it, exiting cleanly on contract errors."""
    try:
        serialized_payload = _format_as_json(payload, contract_label=contract_label)
    except OutputContractError as exc:
        _emit_output_contract_error(
            str(exc),
            is_machine_readable=_is_machine_readable_output("json", output_file),
            human_to_stderr=human_error_to_stderr,
        )
        raise SystemExit(1) from exc

    _emit_output(serialized_payload, output_file, is_stdout)


def _to_numeric_sort_value(value: Any) -> float | None:
    """Convert a sortable value to float when it is numerically representable."""
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        try:
            if pd.isna(value):
                return None
        except TypeError, ValueError:
            return None
        return float(value)

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or not _NUMERIC_SORT_VALUE_RE.fullmatch(stripped):
            return None
        try:
            return float(stripped)
        except ValueError:  # pragma: no cover — regex guard prevents this
            return None

    return None


def _is_missing_sort_value(value: Any) -> bool:
    """Return True for values that should be sorted after concrete values."""
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    try:
        return bool(pd.isna(value))
    except TypeError, ValueError:
        return False


def _compile_discovery_pattern(pattern: str | None, *, option_name: str) -> re.Pattern[str] | None:
    """Compile a discovery regex and raise a user-facing validation error on failure."""
    if not pattern:
        return None
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise DiscoveryArgumentError(f"Invalid {option_name} regex '{pattern}': {exc!s}") from exc


def _validate_discovery_query_inputs(
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
) -> None:
    """Validate discovery query flags before executing API calls."""
    _compile_discovery_pattern(filter_pattern, option_name="--filter")
    _compile_discovery_pattern(exclude_pattern, option_name="--exclude")
    if limit is not None and limit < 0:
        raise DiscoveryArgumentError("--limit cannot be negative")


def _apply_discovery_filters_and_sort(
    rows: list[dict[str, Any]],
    *,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
    searchable_fields: list[str] | None = None,
    default_sort_field: str = "name",
) -> list[dict[str, Any]]:
    """Apply filter/exclude/sort/limit to discovery rows."""
    filtered_rows = list(rows)
    fields = searchable_fields or list(rows[0].keys()) if rows else []

    _validate_discovery_query_inputs(filter_pattern=filter_pattern, exclude_pattern=exclude_pattern, limit=limit)
    filter_re = _compile_discovery_pattern(filter_pattern, option_name="--filter")
    exclude_re = _compile_discovery_pattern(exclude_pattern, option_name="--exclude")

    # Compute per-row searchable blobs once when filter/exclude is requested.
    if filter_re or exclude_re:
        searchable_rows = [
            (row, " ".join(_to_searchable_text(row.get(field, "")) for field in fields)) for row in filtered_rows
        ]
        if filter_re:
            searchable_rows = [(row, blob) for row, blob in searchable_rows if filter_re.search(blob)]
        if exclude_re:
            searchable_rows = [(row, blob) for row, blob in searchable_rows if not exclude_re.search(blob)]
        filtered_rows = [row for row, _ in searchable_rows]

    sort_field = default_sort_field
    reverse = False
    if sort_expression:
        sort_expr = sort_expression.strip()
        if sort_expr.startswith("-"):
            reverse = True
            sort_field = sort_expr[1:]
        else:
            sort_field = sort_expr

    non_missing_values = [
        row.get(sort_field) for row in filtered_rows if not _is_missing_sort_value(row.get(sort_field))
    ]
    use_numeric_sort = bool(non_missing_values) and all(
        _to_numeric_sort_value(value) is not None for value in non_missing_values
    )

    concrete_rows: list[tuple[float | str, dict[str, Any]]] = []
    missing_rows: list[dict[str, Any]] = []
    for row in filtered_rows:
        raw_value = row.get(sort_field)
        if _is_missing_sort_value(raw_value):
            missing_rows.append(row)
            continue

        if use_numeric_sort:
            numeric_value = _to_numeric_sort_value(raw_value)
            if numeric_value is None:
                missing_rows.append(row)
                continue
            concrete_rows.append((numeric_value, row))
        else:
            concrete_rows.append((_to_searchable_text(raw_value).casefold(), row))

    concrete_rows.sort(key=lambda item: item[0], reverse=reverse)
    filtered_rows = [row for _, row in concrete_rows] + missing_rows

    if limit is not None:
        filtered_rows = filtered_rows[:limit]

    return filtered_rows


def _run_list_command(
    banner_text: str,
    command_name: str,
    fetch_and_format: Callable,
    config_file: str = "config.json",
    output_format: str = "table",
    output_file: str | None = None,
    profile: str | None = None,
    validate_inputs: Callable[[], None] | None = None,
) -> bool:
    """Shared boilerplate for list-* discovery commands."""
    from cja_auto_sdr.cli.commands.list import _run_list_command as _impl

    return _impl(
        banner_text=banner_text,
        command_name=command_name,
        fetch_and_format=fetch_and_format,
        config_file=config_file,
        output_format=output_format,
        output_file=output_file,
        profile=profile,
        validate_inputs=validate_inputs,
    )


# ==================== LIST DATA VIEWS ====================


def _fetch_dataviews(
    output_format: str,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> Callable:
    """Return a fetch_and_format callback for list_dataviews."""

    def _inner(cja: Any, is_machine_readable: bool) -> str | None:
        available_dvs = cja.getDataViews()

        if available_dvs is None or (hasattr(available_dvs, "__len__") and len(available_dvs) == 0):
            if is_machine_readable:
                if output_format == "json":
                    return json.dumps({"dataViews": [], "count": 0}, indent=2)
                return "id,name,owner\n"
            return "\nNo data views found or no access to any data views.\n"

        if isinstance(available_dvs, pd.DataFrame):
            available_dvs = available_dvs.to_dict("records")

        display_data = []
        for dv in available_dvs:
            if isinstance(dv, dict):
                dv_id = _normalize_optional_text(dv.get("id"), default="N/A")
                dv_name = _normalize_optional_text(dv.get("name"), default="N/A")
                owner_name = _extract_owner_name(dv.get("owner"))
                display_data.append({"id": dv_id, "name": dv_name, "owner": owner_name})

        display_data = _apply_discovery_filters_and_sort(
            display_data,
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
            sort_expression=sort_expression,
            searchable_fields=["id", "name", "owner"],
            default_sort_field="name",
        )

        if output_format == "json":
            return _format_discovery_json({"dataViews": display_data, "count": len(display_data)})
        if output_format == "csv":
            return _format_as_csv(["id", "name", "owner"], display_data)
        table = _format_as_table(
            f"Found {len(display_data)} accessible data view(s):",
            display_data,
            columns=["id", "name", "owner"],
            col_labels=["ID", "Name", "Owner"],
        )
        # Compute total width to match table separator for usage footer
        labels = ["ID", "Name", "Owner"]
        cols = ["id", "name", "owner"]
        widths = [
            max(len(lbl), max((len(str(item.get(col, ""))) for item in display_data), default=0)) + 2
            for col, lbl in zip(cols, labels, strict=True)
        ]
        total_width = sum(widths)
        footer_lines = [
            "=" * total_width,
            "Usage:",
            "  cja_auto_sdr <DATA_VIEW_ID>       # Use ID directly",
            '  cja_auto_sdr "<DATA_VIEW_NAME>"   # Use exact name (quotes recommended)',
            "",
            "Note: If multiple data views share the same name, all will be processed.",
            "=" * total_width,
        ]
        return table + "\n".join(footer_lines)

    return _inner


def list_dataviews(
    config_file: str = "config.json",
    output_format: str = "table",
    output_file: str | None = None,
    profile: str | None = None,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> bool:
    """List all accessible data views and exit."""
    from cja_auto_sdr.cli.commands.list import list_dataviews as _impl

    return _impl(
        config_file=config_file,
        output_format=output_format,
        output_file=output_file,
        profile=profile,
        filter_pattern=filter_pattern,
        exclude_pattern=exclude_pattern,
        limit=limit,
        sort_expression=sort_expression,
    )


# ==================== DESCRIBE DATA VIEW ====================


def _normalize_single_dataview_payload(raw_dv: Any) -> dict[str, Any] | None:
    """Normalize getDataView payloads to one dict row when possible."""
    if raw_dv is None:
        return None
    if isinstance(raw_dv, pd.DataFrame):
        if raw_dv.empty:
            return None
        records = raw_dv.to_dict("records")
        if not records:
            return None
        first_record = records[0]
        return first_record if isinstance(first_record, dict) else None
    return raw_dv if isinstance(raw_dv, dict) else None


def _assess_dataview_lookup(
    raw_payload: Any,
    *,
    data_view_id: str,
    require_expected_id: bool = True,
) -> _DataViewLookupAssessment:
    """Assess a getDataView payload with a consistent expected-id policy."""
    expected_data_view_id = data_view_id if require_expected_id else None
    return _assess_dataview_lookup_payload(raw_payload, expected_data_view_id=expected_data_view_id)


def _coerce_valid_dataview_lookup_payload(
    raw_payload: Any,
    *,
    data_view_id: str,
    require_expected_id: bool = True,
) -> tuple[dict[str, Any] | None, str, str]:
    """Return a validated lookup payload or structured failure metadata."""
    assessment = _assess_dataview_lookup(
        raw_payload,
        data_view_id=data_view_id,
        require_expected_id=require_expected_id,
    )
    if assessment.is_valid and assessment.payload is not None:
        return assessment.payload, assessment.reason, assessment.raw_type
    return None, assessment.reason, assessment.raw_type


def _coerce_http_status_code(value: Any) -> int | None:
    """Compatibility wrapper for centralized HTTP status-code coercion."""
    return _coerce_http_status_code_core(value)


def _iter_error_chain_nodes(error: Exception) -> list[Any]:
    """Compatibility wrapper for centralized nested exception traversal."""
    return _iter_error_chain_nodes_core(error)


def _extract_http_status_codes(error: Exception) -> set[int]:
    """Compatibility wrapper for centralized HTTP status extraction."""
    return _extract_http_status_codes_core(error)


def _is_inaccessible_dataview_lookup_error(error: Exception) -> bool:
    """Compatibility wrapper for centralized dataview lookup classification."""
    return _is_inaccessible_dataview_lookup_error_core(error)


def _fetch_dataview_lookup_payload(cja: Any, data_view_id: str) -> Any:
    """Call getDataView and normalize inaccessible lookup failures to not_found."""
    try:
        return cja.getDataView(data_view_id)
    except (
        Exception
    ) as lookup_error:  # Intentional: wrapped client/transport lookup failures vary; re-raise non-404/403 cases
        # Classification is centralized in core.discovery_exceptions and supports
        # nested/wrapped transport errors across diverse exception types.
        if _is_inaccessible_dataview_lookup_error(lookup_error):
            raise DiscoveryNotFoundError(f"Data view '{data_view_id}' not found") from lookup_error
        raise


def _require_accessible_dataview(cja: Any, data_view_id: str) -> dict[str, Any]:
    """Fetch a data view and raise DiscoveryNotFoundError when inaccessible/invalid."""
    raw_payload = _fetch_dataview_lookup_payload(cja, data_view_id)

    payload, _, _ = _coerce_valid_dataview_lookup_payload(raw_payload, data_view_id=data_view_id)
    if payload is None:
        raise DiscoveryNotFoundError(f"Data view '{data_view_id}' not found")
    return payload


def _normalize_component_records_or_raise(
    raw_payload: Any,
    *,
    component_label: str,
    data_view_id: str,
) -> list[dict[str, Any]]:
    """Normalize component payloads to dict rows or fail on error-shaped responses."""
    assessment = _assess_component_payload(raw_payload)
    if assessment.kind is _PayloadKind.ERROR:
        raise DiscoveryNotFoundError(f"Failed to retrieve {component_label} for data view '{data_view_id}'")
    if assessment.kind is _PayloadKind.INVALID:
        raise DiscoveryNotFoundError(
            f"Unexpected {component_label} payload type for data view '{data_view_id}'",
        )
    return assessment.rows


def _normalize_describe_dataview_metadata(raw_dv: dict[str, Any], *, default_id: str) -> dict[str, str]:
    """Normalize describe_dataview metadata fields for safe display/serialization."""
    connection_id = _pick_first_present_text(
        (
            raw_dv.get("parentDataGroupId"),
            raw_dv.get("connectionId"),
            raw_dv.get("connection_id"),
        ),
        default="N/A",
        treat_null_like_strings=True,
    )
    created = _extract_timestamp_from_record(raw_dv, "created") or "N/A"
    modified = _extract_timestamp_from_record(raw_dv, "modified") or "N/A"
    return {
        "id": _normalize_optional_text(raw_dv.get("id"), default=default_id),
        "name": _normalize_optional_text(raw_dv.get("name"), default="N/A"),
        "owner": _extract_owner_name_from_record(raw_dv),
        "description": _normalize_optional_text(raw_dv.get("description"), default=""),
        "connection_id": connection_id,
        "created": created,
        "modified": modified,
    }


def _fetch_describe_dataview(
    data_view_id: str,
    output_format: str,
) -> Callable:
    """Return a fetch_and_format callback for describe_dataview."""

    def _inner(cja: Any, _is_machine_readable: bool) -> str | None:
        raw_dv = _require_accessible_dataview(cja, data_view_id)

        dv_metadata = _normalize_describe_dataview_metadata(raw_dv, default_id=data_view_id)
        dv_id = dv_metadata["id"]
        dv_name = dv_metadata["name"]
        owner_name = dv_metadata["owner"]
        description = dv_metadata["description"]
        connection_id = dv_metadata["connection_id"]
        created = dv_metadata["created"]
        modified = dv_metadata["modified"]

        n_metrics = _count_component_items_for_fetch_spec(
            cja,
            data_view_id,
            _METRICS_COMPONENT_FETCH_SPEC,
        )
        n_dimensions = _count_component_items_for_fetch_spec(
            cja,
            data_view_id,
            _DIMENSIONS_COMPONENT_FETCH_SPEC,
        )
        n_segments = _count_component_items_for_fetch_spec(
            cja,
            data_view_id,
            _SEGMENTS_COMPONENT_FETCH_SPEC,
        )
        n_calc_metrics = _count_component_items_for_fetch_spec(
            cja,
            data_view_id,
            _CALCULATED_METRICS_COMPONENT_FETCH_SPEC,
        )

        # Compute total only when all counts are numeric
        counts = [n_metrics, n_dimensions, n_segments, n_calc_metrics]
        numeric_counts = [c for c in counts if isinstance(c, int)]
        total = sum(numeric_counts) if len(numeric_counts) == len(counts) else "N/A"

        if output_format == "json":
            payload = {
                "dataView": {
                    "id": dv_id,
                    "name": dv_name,
                    "owner": owner_name,
                    "description": description,
                    "connectionId": connection_id,
                    "created": created,
                    "modified": modified,
                    "components": {
                        "dimensions": n_dimensions,
                        "metrics": n_metrics,
                        "calculatedMetrics": n_calc_metrics,
                        "segments": n_segments,
                        "total": total,
                    },
                }
            }
            return _format_discovery_json(payload)

        if output_format == "csv":
            columns = [
                "id",
                "name",
                "owner",
                "description",
                "connection_id",
                "created",
                "modified",
                "dimensions",
                "metrics",
                "calculated_metrics",
                "segments",
                "total",
            ]
            row = {
                "id": dv_id,
                "name": dv_name,
                "owner": owner_name,
                "description": description,
                "connection_id": connection_id,
                "created": created,
                "modified": modified,
                "dimensions": n_dimensions,
                "metrics": n_metrics,
                "calculated_metrics": n_calc_metrics,
                "segments": n_segments,
                "total": total,
            }
            return _format_as_csv(columns, [row])

        # Table output
        term_width = shutil.get_terminal_size().columns
        rule_width = term_width
        lines: list[str] = []
        lines.append("")
        lines.append(f"Data View: {dv_name}")
        lines.append("=" * rule_width)
        lines.append(f"  ID:            {dv_id}")
        lines.append(f"  Owner:         {owner_name}")
        desc_text = description or "(none)"
        desc_prefix = "  Description:   "
        desc_avail = term_width - len(desc_prefix)
        if desc_avail > 20 and len(desc_text) > desc_avail:
            wrapped = textwrap.wrap(desc_text, width=desc_avail)
            lines.append(desc_prefix + wrapped[0])
            indent = " " * len(desc_prefix)
            lines.extend(indent + cont for cont in wrapped[1:])
        else:
            lines.append(f"{desc_prefix}{desc_text}")
        lines.append(f"  Connection:    {connection_id}")
        lines.append(f"  Created:       {created}")
        lines.append(f"  Modified:      {modified}")
        lines.append("")
        lines.append("  Components:")
        lines.append(f"    Dimensions:          {n_dimensions}")
        lines.append(f"    Metrics:             {n_metrics}")
        lines.append(f"    Calculated Metrics:  {n_calc_metrics}")
        lines.append(f"    Segments:            {n_segments}")
        lines.append("    ─────────────────────────")
        lines.append(f"    Total:               {total}")
        lines.append("=" * rule_width)
        lines.append("")
        return "\n".join(lines)

    return _inner


def describe_dataview(
    data_view_id: str,
    config_file: str = "config.json",
    output_format: str = "table",
    output_file: str | None = None,
    profile: str | None = None,
) -> bool:
    """Describe a single data view with component counts and exit."""
    from cja_auto_sdr.cli.commands.list import describe_dataview as _impl

    return _impl(
        data_view_id=data_view_id,
        config_file=config_file,
        output_format=output_format,
        output_file=output_file,
        profile=profile,
    )


# ==================== LIST METRICS ====================


def _resolve_dataview_name(cja: Any, data_view_id: str, *, preferred_name: str | None = None) -> str:
    """Look up a canonical data view display name with safe fallback behavior."""
    raw_dv = _require_accessible_dataview(cja, data_view_id)
    normalized_name = _normalize_optional_text(raw_dv.get("name"), default="")
    if normalized_name:
        return normalized_name
    normalized_preferred = _normalize_optional_text(preferred_name, default="")
    return normalized_preferred or "Unknown"


def _format_governance_rows_for_tabular(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert governance fields into table/csv-friendly strings."""
    return [
        {
            **row,
            "approved": _approved_display(row.get("approved")),
            "tags": _tags_display(row.get("tags")),
        }
        for row in rows
    ]


@dataclass(frozen=True)
class _ComponentFetchSpec:
    """Describe how to fetch one component collection for a data view."""

    method_name: str
    data_view_arg_name: str | None = None
    kwargs: dict[str, str | bool] = field(default_factory=dict)


_METRICS_COMPONENT_FETCH_SPEC = _ComponentFetchSpec(
    method_name="getMetrics",
    kwargs={"inclType": "hidden", "full": True},
)

_DIMENSIONS_COMPONENT_FETCH_SPEC = _ComponentFetchSpec(
    method_name="getDimensions",
    kwargs={"inclType": "hidden", "full": True},
)

_SEGMENTS_COMPONENT_FETCH_SPEC = _ComponentFetchSpec(
    method_name="getFilters",
    data_view_arg_name="dataIds",
    kwargs={"full": True},
)

_CALCULATED_METRICS_COMPONENT_FETCH_SPEC = _ComponentFetchSpec(
    method_name="getCalculatedMetrics",
    data_view_arg_name="dataIds",
    kwargs={"full": True},
)


def _fetch_component_payload(cja: Any, data_view_id: str, fetch_spec: _ComponentFetchSpec) -> Any:
    """Invoke a component-list API call using a declarative fetch spec."""
    fetch_method = getattr(cja, fetch_spec.method_name, None)
    if not callable(fetch_method):
        raise DiscoveryNotFoundError(
            f"CJA client missing expected method '{fetch_spec.method_name}' for data view '{data_view_id}'",
        )

    kwargs = dict(fetch_spec.kwargs)
    if fetch_spec.data_view_arg_name:
        kwargs[fetch_spec.data_view_arg_name] = data_view_id
        return fetch_method(**kwargs)
    return fetch_method(data_view_id, **kwargs)


def _count_component_items_for_fetch_spec(cja: Any, data_view_id: str, fetch_spec: _ComponentFetchSpec) -> int | str:
    """Return a component count for one fetch spec, falling back to 'N/A' on runtime failures."""
    return _count_component_items_for_fetch_spec_best_effort(
        cja,
        data_view_id,
        fetch_spec,
        fallback_value="N/A",
        use_retry=False,
    )


def _count_component_items_for_fetch_spec_best_effort(
    cja: Any,
    data_view_id: str,
    fetch_spec: _ComponentFetchSpec,
    *,
    fallback_value: int | str,
    use_retry: bool,
    logger: logging.Logger | None = None,
) -> int | str:
    """Fetch one component payload and degrade failures to a caller-provided fallback value."""
    component_label = fetch_spec.method_name
    try:
        if use_retry:
            payload = make_api_call_with_retry(
                _fetch_component_payload,
                cja,
                data_view_id,
                fetch_spec,
                logger=logger,
                operation_name=f"{component_label}({data_view_id})",
            )
        else:
            payload = _fetch_component_payload(cja, data_view_id, fetch_spec)

        count = _count_component_items_or_na_from_assessment(payload)
        if isinstance(count, int):
            return count
        if logger:
            logger.debug("Could not fetch %s count for %s: non-countable payload", component_label, data_view_id)
    except RECOVERABLE_OPTIONAL_COMPONENT_COUNT_EXCEPTIONS as e:  # Intentional best-effort boundary
        if logger:
            logger.debug("Could not fetch %s count for %s: %s", component_label, data_view_id, e, exc_info=True)
    return fallback_value


def _count_component_items_for_fetch_spec_with_retry(
    cja: Any,
    data_view_id: str,
    fetch_spec: _ComponentFetchSpec,
    *,
    logger: logging.Logger,
) -> int:
    """Return component count via retry-aware fetches, degrading non-fatal issues to zero."""
    count = _count_component_items_for_fetch_spec_best_effort(
        cja,
        data_view_id,
        fetch_spec,
        fallback_value=0,
        use_retry=True,
        logger=logger,
    )
    return count if isinstance(count, int) else 0


def _build_component_list_fetcher(
    *,
    data_view_id: str,
    data_view_name: str | None,
    output_format: str,
    filter_pattern: str | None,
    exclude_pattern: str | None,
    limit: int | None,
    sort_expression: str | None,
    component_label: str,
    table_item_label: str,
    component_json_key: str,
    empty_csv_header: str,
    fetch_spec: _ComponentFetchSpec,
    display_row_builder: Callable[[dict[str, Any]], dict[str, Any]],
    searchable_fields: list[str],
    csv_columns: list[str],
    table_columns: list[str],
    table_labels: list[str],
    table_row_transform: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
) -> Callable:
    """Return a shared fetch-and-format callback for list-* inspection commands."""

    def _inner(cja: Any, is_machine_readable: bool) -> str | None:
        dv_name = _resolve_dataview_name(cja, data_view_id, preferred_name=data_view_name)

        raw_components = _normalize_component_records_or_raise(
            _fetch_component_payload(cja, data_view_id, fetch_spec),
            component_label=component_label,
            data_view_id=data_view_id,
        )

        if not raw_components:
            if is_machine_readable:
                if output_format == "json":
                    return _format_discovery_json(
                        {
                            "dataViewId": data_view_id,
                            "dataViewName": dv_name,
                            component_json_key: [],
                            "count": 0,
                        }
                    )
                return f"{empty_csv_header}\n"
            return f"\nNo {component_label} found for data view '{data_view_id}'.\n"

        display_data = [display_row_builder(item) for item in raw_components if isinstance(item, dict)]
        display_data = _apply_discovery_filters_and_sort(
            display_data,
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
            sort_expression=sort_expression,
            searchable_fields=searchable_fields,
            default_sort_field="name",
        )

        if output_format == "json":
            return _format_discovery_json(
                {
                    "dataViewId": data_view_id,
                    "dataViewName": dv_name,
                    component_json_key: display_data,
                    "count": len(display_data),
                }
            )

        tabular_data = table_row_transform(display_data) if table_row_transform else display_data
        if output_format == "csv":
            return _format_as_csv(csv_columns, tabular_data)
        return _format_as_table(
            f"Found {len(tabular_data)} {table_item_label}(s) in data view '{dv_name}':",
            tabular_data,
            columns=table_columns,
            col_labels=table_labels,
        )

    return _inner


def _normalize_component_text_fields(item: dict[str, Any], *, defaults: dict[str, str]) -> dict[str, str]:
    """Normalize a component row's text fields with per-field defaults."""
    return {
        field_name: _normalize_optional_text(item.get(field_name), default=default_value)
        for field_name, default_value in defaults.items()
    }


def _normalize_optional_component_int(value: Any, *, default: int = 0) -> int:
    """Normalize optional integer-ish component values for strict JSON output."""
    if _is_missing_discovery_value(value, treat_blank_string=True, treat_null_like_strings=True):
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return default
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return int(stripped)
        except ValueError:
            return default
    return default


def _build_metric_display_row(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize one metrics-list row for output."""
    return {
        **_normalize_component_text_fields(
            item,
            defaults={
                "id": "N/A",
                "name": "N/A",
                "type": "N/A",
                "description": "",
            },
        ),
    }


def _fetch_metrics_list(
    data_view_id: str,
    output_format: str,
    data_view_name: str | None = None,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> Callable:
    """Return a fetch_and_format callback for list_metrics."""
    return _build_component_list_fetcher(
        data_view_id=data_view_id,
        data_view_name=data_view_name,
        output_format=output_format,
        filter_pattern=filter_pattern,
        exclude_pattern=exclude_pattern,
        limit=limit,
        sort_expression=sort_expression,
        component_label="metrics",
        table_item_label="metric",
        component_json_key="metrics",
        empty_csv_header="id,name,type,description",
        fetch_spec=_METRICS_COMPONENT_FETCH_SPEC,
        display_row_builder=_build_metric_display_row,
        searchable_fields=["id", "name", "type", "description"],
        csv_columns=["id", "name", "type", "description"],
        table_columns=["id", "name", "type", "description"],
        table_labels=["ID", "Name", "Type", "Description"],
    )


def list_metrics(
    data_view_id: str,
    config_file: str = "config.json",
    output_format: str = "table",
    output_file: str | None = None,
    profile: str | None = None,
    data_view_name: str | None = None,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> bool:
    """List all metrics for a given data view."""
    from cja_auto_sdr.cli.commands.list import list_metrics as _impl

    return _impl(
        data_view_id=data_view_id,
        config_file=config_file,
        output_format=output_format,
        output_file=output_file,
        profile=profile,
        data_view_name=data_view_name,
        filter_pattern=filter_pattern,
        exclude_pattern=exclude_pattern,
        limit=limit,
        sort_expression=sort_expression,
    )


# ==================== LIST DIMENSIONS ====================


def _build_dimension_display_row(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize one dimensions-list row for output."""
    return {
        **_normalize_component_text_fields(
            item,
            defaults={
                "id": "N/A",
                "name": "N/A",
                "type": "N/A",
                "description": "",
            },
        ),
    }


def _fetch_dimensions_list(
    data_view_id: str,
    output_format: str,
    data_view_name: str | None = None,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> Callable:
    """Return a fetch_and_format callback for list_dimensions."""
    return _build_component_list_fetcher(
        data_view_id=data_view_id,
        data_view_name=data_view_name,
        output_format=output_format,
        filter_pattern=filter_pattern,
        exclude_pattern=exclude_pattern,
        limit=limit,
        sort_expression=sort_expression,
        component_label="dimensions",
        table_item_label="dimension",
        component_json_key="dimensions",
        empty_csv_header="id,name,type,description",
        fetch_spec=_DIMENSIONS_COMPONENT_FETCH_SPEC,
        display_row_builder=_build_dimension_display_row,
        searchable_fields=["id", "name", "type", "description"],
        csv_columns=["id", "name", "type", "description"],
        table_columns=["id", "name", "type", "description"],
        table_labels=["ID", "Name", "Type", "Description"],
    )


def list_dimensions(
    data_view_id: str,
    config_file: str = "config.json",
    output_format: str = "table",
    output_file: str | None = None,
    profile: str | None = None,
    data_view_name: str | None = None,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> bool:
    """List all dimensions for a given data view."""
    from cja_auto_sdr.cli.commands.list import list_dimensions as _impl

    return _impl(
        data_view_id=data_view_id,
        config_file=config_file,
        output_format=output_format,
        output_file=output_file,
        profile=profile,
        data_view_name=data_view_name,
        filter_pattern=filter_pattern,
        exclude_pattern=exclude_pattern,
        limit=limit,
        sort_expression=sort_expression,
    )


# ==================== LIST SEGMENTS ====================


def _approved_display(value: Any) -> str:
    """Convert an approved flag to a display string."""
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _tags_display(tags: Any) -> str:
    """Render already-normalized tag lists for table/csv output."""
    if not isinstance(tags, list):
        return ""
    return ", ".join(tag for tag in tags if isinstance(tag, str))


def _build_segment_display_row(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize one segments-list row for output."""
    tags = _extract_tags_normalized(item.get("tags"))
    approved_raw = item.get("approved")
    return {
        **_normalize_component_text_fields(
            item,
            defaults={
                "id": "N/A",
                "name": "N/A",
                "description": "",
            },
        ),
        "owner": _extract_owner_name_from_record(item),
        "approved": approved_raw if isinstance(approved_raw, bool) else None,
        "tags": tags,
        "created": _extract_timestamp_from_record(item, "created"),
        "modified": _extract_timestamp_from_record(item, "modified"),
    }


def _fetch_segments_list(
    data_view_id: str,
    output_format: str,
    data_view_name: str | None = None,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> Callable:
    """Return a fetch_and_format callback for list_segments."""
    return _build_component_list_fetcher(
        data_view_id=data_view_id,
        data_view_name=data_view_name,
        output_format=output_format,
        filter_pattern=filter_pattern,
        exclude_pattern=exclude_pattern,
        limit=limit,
        sort_expression=sort_expression,
        component_label="segments",
        table_item_label="segment",
        component_json_key="segments",
        empty_csv_header="id,name,owner,approved,description,tags,created,modified",
        fetch_spec=_SEGMENTS_COMPONENT_FETCH_SPEC,
        display_row_builder=_build_segment_display_row,
        searchable_fields=["id", "name", "owner", "description", "tags"],
        csv_columns=["id", "name", "owner", "approved", "description", "tags", "created", "modified"],
        table_columns=["id", "name", "owner", "approved", "description"],
        table_labels=["ID", "Name", "Owner", "Approved", "Description"],
        table_row_transform=_format_governance_rows_for_tabular,
    )


def list_segments(
    data_view_id: str,
    config_file: str = "config.json",
    output_format: str = "table",
    output_file: str | None = None,
    profile: str | None = None,
    data_view_name: str | None = None,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> bool:
    """List all segments (filters) for a given data view."""
    from cja_auto_sdr.cli.commands.list import list_segments as _impl

    return _impl(
        data_view_id=data_view_id,
        config_file=config_file,
        output_format=output_format,
        output_file=output_file,
        profile=profile,
        data_view_name=data_view_name,
        filter_pattern=filter_pattern,
        exclude_pattern=exclude_pattern,
        limit=limit,
        sort_expression=sort_expression,
    )


# ==================== LIST CALCULATED METRICS ====================


def _build_calculated_metric_display_row(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize one calculated-metrics row for output."""
    tags = _extract_tags_normalized(item.get("tags"))
    approved_raw = item.get("approved")
    return {
        **_normalize_component_text_fields(
            item,
            defaults={
                "id": "N/A",
                "name": "N/A",
                "description": "",
                "type": "",
                "polarity": "",
            },
        ),
        "owner": _extract_owner_name_from_record(item),
        "precision": _normalize_optional_component_int(item.get("precision"), default=0),
        "approved": approved_raw if isinstance(approved_raw, bool) else None,
        "tags": tags,
        "created": _extract_timestamp_from_record(item, "created"),
        "modified": _extract_timestamp_from_record(item, "modified"),
    }


def _fetch_calculated_metrics_list(
    data_view_id: str,
    output_format: str,
    data_view_name: str | None = None,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> Callable:
    """Return a fetch_and_format callback for list_calculated_metrics."""
    return _build_component_list_fetcher(
        data_view_id=data_view_id,
        data_view_name=data_view_name,
        output_format=output_format,
        filter_pattern=filter_pattern,
        exclude_pattern=exclude_pattern,
        limit=limit,
        sort_expression=sort_expression,
        component_label="calculated metrics",
        table_item_label="calculated metric",
        component_json_key="calculatedMetrics",
        empty_csv_header="id,name,owner,type,polarity,precision,approved,tags,created,modified,description",
        fetch_spec=_CALCULATED_METRICS_COMPONENT_FETCH_SPEC,
        display_row_builder=_build_calculated_metric_display_row,
        searchable_fields=["id", "name", "owner", "type", "polarity", "description"],
        csv_columns=[
            "id",
            "name",
            "owner",
            "type",
            "polarity",
            "precision",
            "approved",
            "tags",
            "created",
            "modified",
            "description",
        ],
        table_columns=["id", "name", "owner", "type", "polarity", "approved", "description"],
        table_labels=["ID", "Name", "Owner", "Type", "Polarity", "Approved", "Description"],
        table_row_transform=_format_governance_rows_for_tabular,
    )


def list_calculated_metrics(
    data_view_id: str,
    config_file: str = "config.json",
    output_format: str = "table",
    output_file: str | None = None,
    profile: str | None = None,
    data_view_name: str | None = None,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> bool:
    """List all calculated metrics for a given data view."""
    from cja_auto_sdr.cli.commands.list import list_calculated_metrics as _impl

    return _impl(
        data_view_id=data_view_id,
        config_file=config_file,
        output_format=output_format,
        output_file=output_file,
        profile=profile,
        data_view_name=data_view_name,
        filter_pattern=filter_pattern,
        exclude_pattern=exclude_pattern,
        limit=limit,
        sort_expression=sort_expression,
    )


# ==================== LIST CONNECTIONS ====================


def _fetch_connections(
    output_format: str,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> Callable:
    """Return a fetch_and_format callback for list_connections."""

    def _inner(cja: Any, is_machine_readable: bool) -> str | None:
        raw_connections = cja.getConnections(output="raw", expansion="name,ownerFullName,dataSets")
        connections = _extract_connections_list(raw_connections)

        if not connections:
            # Check whether data views reference connections we can't see
            # (the GET /connections API requires product-admin privileges).
            available_dvs = cja.getDataViews()
            if isinstance(available_dvs, pd.DataFrame):
                available_dvs = available_dvs.to_dict("records")

            conn_ids_from_dvs: dict[str, int] = {}  # conn_id -> count of data views
            for dv in available_dvs or []:
                if not isinstance(dv, dict):
                    continue
                pid = dv.get("parentDataGroupId")
                if not _is_missing_discovery_value(pid, treat_blank_string=True, treat_null_like_strings=True):
                    conn_ids_from_dvs[pid] = conn_ids_from_dvs.get(pid, 0) + 1

            if conn_ids_from_dvs:
                # Permissions issue — derive connection IDs from data views
                _PERM_WARNING = (
                    "Note: The GET /connections API requires product-admin privileges.\n"
                    "Connection details are unavailable. Showing connection IDs derived\n"
                    "from data views instead."
                )
                derived = [
                    {"id": cid, "name": None, "owner": None, "datasets": [], "dataview_count": cnt}
                    for cid, cnt in sorted(conn_ids_from_dvs.items())
                ]
                derived = _apply_discovery_filters_and_sort(
                    derived,
                    filter_pattern=filter_pattern,
                    exclude_pattern=exclude_pattern,
                    limit=limit,
                    sort_expression=sort_expression,
                    searchable_fields=["id", "name", "owner", "dataview_count"],
                    default_sort_field="id",
                )

                if output_format == "json":
                    return _format_discovery_json(
                        {
                            "connections": derived,
                            "count": len(derived),
                            "warning": _PERM_WARNING.replace("\n", " "),
                        },
                    )
                if output_format == "csv":
                    flat = [
                        {
                            "connection_id": d["id"],
                            "connection_name": "",
                            "owner": "",
                            "dataset_id": "",
                            "dataset_name": "",
                            "dataview_count": d["dataview_count"],
                        }
                        for d in derived
                    ]
                    return _format_as_csv(
                        ["connection_id", "connection_name", "owner", "dataset_id", "dataset_name", "dataview_count"],
                        flat,
                    )
                lines: list[str] = []
                lines.append("")
                lines.append(_PERM_WARNING)
                lines.append("")
                lines.append(f"Found {len(derived)} connection(s) referenced by data views:")
                lines.append("")
                lines.extend(f"  {d['id']}  ({d['dataview_count']} data view(s))" for d in derived)
                lines.append("")
                return "\n".join(lines)

            # Genuinely no connections
            if is_machine_readable:
                if output_format == "json":
                    return _format_discovery_json({"connections": [], "count": 0})
                return "connection_id,connection_name,owner,dataset_id,dataset_name\n"
            return "\nNo connections found or no access to any connections.\n"

        display_data = []
        for conn in connections:
            if not isinstance(conn, dict):
                continue
            conn_id = _normalize_optional_text(conn.get("id"), default="N/A")
            conn_name = _normalize_optional_text(conn.get("name"), default="N/A")
            owner_full_name = _normalize_optional_text(conn.get("ownerFullName"), default="")
            owner_name = owner_full_name or _extract_owner_name(conn.get("owner"))

            raw_datasets = conn.get("dataSets", conn.get("datasets", []))
            if not isinstance(raw_datasets, list):
                raw_datasets = []
            datasets = [_extract_dataset_info(ds) for ds in raw_datasets]

            display_data.append(
                {
                    "id": conn_id,
                    "name": conn_name,
                    "owner": owner_name,
                    "datasets": datasets,
                },
            )

        display_data = _apply_discovery_filters_and_sort(
            display_data,
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
            sort_expression=sort_expression,
            searchable_fields=["id", "name", "owner", "datasets"],
            default_sort_field="name",
        )

        if output_format == "json":
            return _format_discovery_json({"connections": display_data, "count": len(display_data)})
        if output_format == "csv":
            # Flatten nested datasets: one CSV row per dataset
            flat_rows: list[dict] = []
            for conn in display_data:
                if conn["datasets"]:
                    flat_rows.extend(
                        {
                            "connection_id": conn["id"],
                            "connection_name": conn["name"],
                            "owner": conn["owner"],
                            "dataset_id": ds["id"],
                            "dataset_name": ds["name"],
                        }
                        for ds in conn["datasets"]
                    )
                else:
                    flat_rows.append(
                        {
                            "connection_id": conn["id"],
                            "connection_name": conn["name"],
                            "owner": conn["owner"],
                            "dataset_id": "",
                            "dataset_name": "",
                        },
                    )
            return _format_as_csv(
                ["connection_id", "connection_name", "owner", "dataset_id", "dataset_name"],
                flat_rows,
            )
        lines: list[str] = []
        lines.append("")
        lines.append(f"Found {len(display_data)} accessible connection(s):")
        lines.append("")
        for conn in display_data:
            lines.append(f"Connection: {conn['name']} ({conn['id']})")
            lines.append(f"Owner: {conn['owner']}")
            if conn["datasets"]:
                lines.append(f"Datasets ({len(conn['datasets'])}):")
                for ds in conn["datasets"]:
                    lines.append(f"  {ds['id']}  {ds['name']}")
            else:
                lines.append("Datasets: (none)")
            lines.append("")
        return "\n".join(lines)

    return _inner


def list_connections(
    config_file: str = "config.json",
    output_format: str = "table",
    output_file: str | None = None,
    profile: str | None = None,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> bool:
    """List all accessible connections with their datasets and exit."""
    from cja_auto_sdr.cli.commands.list import list_connections as _impl

    return _impl(
        config_file=config_file,
        output_format=output_format,
        output_file=output_file,
        profile=profile,
        filter_pattern=filter_pattern,
        exclude_pattern=exclude_pattern,
        limit=limit,
        sort_expression=sort_expression,
    )


# ==================== LIST DATASETS ====================


def _fetch_datasets(
    output_format: str,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> Callable:
    """Return a fetch_and_format callback for list_datasets."""

    def _inner(cja: Any, is_machine_readable: bool) -> str | None:
        # Step 1: Fetch all connections and build lookup map
        raw_connections = cja.getConnections(output="raw", expansion="name,ownerFullName,dataSets")
        conn_map: dict = {}  # connection_id -> {name, datasets}
        for conn in _extract_connections_list(raw_connections):
            if not isinstance(conn, dict):
                continue
            conn_id = _normalize_optional_text(conn.get("id"), default="")
            conn_name = _normalize_optional_text(conn.get("name"), default="N/A")
            raw_datasets = conn.get("dataSets", conn.get("datasets", []))
            if not isinstance(raw_datasets, list):
                raw_datasets = []
            conn_map[conn_id] = {
                "name": conn_name,
                "datasets": [_extract_dataset_info(ds) for ds in raw_datasets],
            }

        # Step 2: Fetch all data views
        available_dvs = cja.getDataViews()
        if isinstance(available_dvs, pd.DataFrame):
            available_dvs = available_dvs.to_dict("records")

        if not available_dvs:
            if is_machine_readable:
                if output_format == "json":
                    return _format_discovery_json({"dataViews": [], "count": 0})
                return "dataview_id,dataview_name,connection_id,connection_name,dataset_id,dataset_name\n"
            return "\nNo data views found or no access to any data views.\n"

        # Detect permissions gap: conn_map is empty but data views have connections
        _no_conn_details = False
        if not conn_map:
            for dv in available_dvs or []:
                if not isinstance(dv, dict):
                    continue
                pid = dv.get("parentDataGroupId")
                if not _is_missing_discovery_value(pid, treat_blank_string=True, treat_null_like_strings=True):
                    _no_conn_details = True
                    break

        # Step 3: Build output records using parentDataGroupId
        if not is_machine_readable:
            print(f"Processing {len(available_dvs)} data view(s)...")
        display_data = []
        for i, dv in enumerate(available_dvs):
            if not isinstance(dv, dict):
                continue
            dv_id = _normalize_optional_text(dv.get("id"), default="N/A")
            dv_name = _normalize_optional_text(dv.get("name"), default="N/A")

            if not is_machine_readable:
                print(f"  [{i + 1}/{len(available_dvs)}] {dv_name}...", end="\r")

            parent_conn_id = dv.get("parentDataGroupId")
            # DataFrame-backed records can carry missing values as NaN/NA.
            # Normalize to None so machine-readable output emits "N/A", not NaN.
            if _is_missing_discovery_value(parent_conn_id, treat_blank_string=True, treat_null_like_strings=True):
                parent_conn_id = None

            conn_info = conn_map.get(parent_conn_id) if parent_conn_id else None
            conn_name = conn_info.get("name", "N/A") if conn_info else None
            datasets = conn_info.get("datasets", []) if conn_info else []

            display_data.append(
                {
                    "id": dv_id,
                    "name": dv_name,
                    "connection": {"id": parent_conn_id or "N/A", "name": conn_name},
                    "datasets": datasets,
                },
            )

        display_data = _apply_discovery_filters_and_sort(
            display_data,
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
            sort_expression=sort_expression,
            searchable_fields=["id", "name", "connection", "datasets"],
            default_sort_field="name",
        )

        if not is_machine_readable:
            # Clear progress line with ANSI erase-line escape
            print("\033[2K", end="\r")

        _CONN_PERM_WARNING = (
            "Note: Connection details are unavailable (the GET /connections API\n"
            "requires product-admin privileges). Showing connection IDs only."
        )

        result_payload: dict = {"dataViews": display_data, "count": len(display_data)}
        if _no_conn_details:
            result_payload["warning"] = _CONN_PERM_WARNING.replace("\n", " ")

        if output_format == "json":
            return _format_discovery_json(result_payload)
        if output_format == "csv":
            # Flatten nested datasets: one CSV row per dataset per data view
            flat_rows: list[dict] = []
            for entry in display_data:
                conn_id = entry["connection"]["id"]
                conn_name_val = entry["connection"]["name"] or ""
                if entry["datasets"]:
                    flat_rows.extend(
                        {
                            "dataview_id": entry["id"],
                            "dataview_name": entry["name"],
                            "connection_id": conn_id,
                            "connection_name": conn_name_val,
                            "dataset_id": ds["id"],
                            "dataset_name": ds["name"],
                        }
                        for ds in entry["datasets"]
                    )
                else:
                    flat_rows.append(
                        {
                            "dataview_id": entry["id"],
                            "dataview_name": entry["name"],
                            "connection_id": conn_id,
                            "connection_name": conn_name_val,
                            "dataset_id": "",
                            "dataset_name": "",
                        },
                    )
            return _format_as_csv(
                ["dataview_id", "dataview_name", "connection_id", "connection_name", "dataset_id", "dataset_name"],
                flat_rows,
            )
        lines: list[str] = []
        lines.append("")
        if _no_conn_details:
            lines.append(_CONN_PERM_WARNING)
            lines.append("")
        lines.append(f"Found {len(display_data)} data view(s) with dataset information:")
        lines.append("")
        for entry in display_data:
            lines.append(f"Data View: {entry['name']} ({entry['id']})")
            c_name = entry["connection"]["name"]
            c_id = entry["connection"]["id"]
            if c_name:
                lines.append(f"Connection: {c_name} ({c_id})")
            else:
                lines.append(f"Connection: {c_id}")
            if entry["datasets"]:
                lines.append(f"Datasets ({len(entry['datasets'])}):")
                lines.extend(f"  {ds['id']}  {ds['name']}" for ds in entry["datasets"])
            elif not _no_conn_details:
                lines.append("Datasets: (none)")
            lines.append("")
        return "\n".join(lines)

    return _inner


def list_datasets(
    config_file: str = "config.json",
    output_format: str = "table",
    output_file: str | None = None,
    profile: str | None = None,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> bool:
    """List all data views with their backing connections and underlying datasets."""
    from cja_auto_sdr.cli.commands.list import list_datasets as _impl

    return _impl(
        config_file=config_file,
        output_format=output_format,
        output_file=output_file,
        profile=profile,
        filter_pattern=filter_pattern,
        exclude_pattern=exclude_pattern,
        limit=limit,
        sort_expression=sort_expression,
    )


# ==================== INTERACTIVE DATA VIEW SELECTION ====================


def interactive_select_dataviews(config_file: str = "config.json", profile: str | None = None) -> list[str]:
    from cja_auto_sdr.cli.interactive import interactive_select_dataviews as _impl

    return _impl(config_file=config_file, profile=profile)


# ==================== INTERACTIVE MODE ====================


@dataclass
class WizardConfig:
    """Configuration collected from interactive mode"""

    data_view_ids: list[str]
    output_format: str = "excel"
    output_dir: str | None = None
    include_segments: bool = False
    include_calculated: bool = False
    include_derived: bool = False
    inventory_only: bool = False


def interactive_wizard(config_file: str = "config.json", profile: str | None = None) -> WizardConfig | None:
    from cja_auto_sdr.cli.interactive import interactive_wizard as _impl

    return _impl(config_file=config_file, profile=profile)


# ==================== SAMPLE CONFIG GENERATOR ====================


def generate_sample_config(output_path: str = "config.sample.json") -> bool:
    from cja_auto_sdr.cli.commands.config import generate_sample_config as _impl

    return _impl(output_path=output_path)


# ==================== CONFIG STATUS ====================


def _read_config_status_file(config_file: str, logger: logging.Logger) -> tuple[dict[str, Any] | None, str | None]:
    from cja_auto_sdr.cli.commands.config import _read_config_status_file as _impl

    return _impl(config_file=config_file, logger=logger)


def show_config_status(config_file: str = "config.json", profile: str | None = None, output_json: bool = False) -> bool:
    from cja_auto_sdr.cli.commands.config import show_config_status as _impl

    return _impl(config_file=config_file, profile=profile, output_json=output_json)


# ==================== VALIDATE CONFIG ====================


def _resolve_output_dir_path(output_dir: str | Path) -> Path:
    from cja_auto_sdr.cli.commands.config import _resolve_output_dir_path as _impl

    return _impl(output_dir)


def _check_output_dir_access(output_dir: str | Path) -> tuple[bool, Path, str, Path | None]:
    from cja_auto_sdr.cli.commands.config import _check_output_dir_access as _impl

    return _impl(output_dir)


def validate_config_only(
    config_file: str = "config.json",
    profile: str | None = None,
    output_dir: str = ".",
) -> bool:
    from cja_auto_sdr.cli.commands.config import validate_config_only as _impl

    return _impl(config_file=config_file, profile=profile, output_dir=output_dir)


# ==================== STATS COMMAND ====================


def _stats_error_row(data_view_id: str, error: Exception) -> dict[str, Any]:
    from cja_auto_sdr.cli.commands.stats import _stats_error_row as _impl

    return _impl(data_view_id, error)


def _require_numeric_component_count_for_stats(
    cja: cjapy.CJA,
    data_view_id: str,
    *,
    fetch_spec: _ComponentFetchSpec,
    component_label: str,
) -> int:
    from cja_auto_sdr.cli.commands.stats import _require_numeric_component_count_for_stats as _impl

    return _impl(cja, data_view_id, fetch_spec=fetch_spec, component_label=component_label)


def _collect_stats_row(cja: cjapy.CJA, data_view_id: str) -> dict[str, Any]:
    from cja_auto_sdr.cli.commands.stats import _collect_stats_row as _impl

    return _impl(cja, data_view_id)


def _collect_stats_row_with_fallback(cja: cjapy.CJA, data_view_id: str, logger: logging.Logger) -> dict[str, Any]:
    from cja_auto_sdr.cli.commands.stats import _collect_stats_row_with_fallback as _impl

    return _impl(cja, data_view_id, logger)


def show_stats(
    data_views: list[str],
    config_file: str = "config.json",
    output_format: str = "table",
    output_file: str | None = None,
    quiet: bool = False,
    profile: str | None = None,
) -> bool:
    from cja_auto_sdr.cli.commands.stats import show_stats as _impl

    return _impl(
        data_views=data_views,
        config_file=config_file,
        output_format=output_format,
        output_file=output_file,
        quiet=quiet,
        profile=profile,
    )


def compare_org_reports(current: OrgReportResult, previous_path: str) -> OrgReportComparison:
    """Compare current org-report to a previous report for trending analysis (Feature 4).

    Args:
        current: Current OrgReportResult
        previous_path: Path to previous org-report JSON file

    Returns:
        OrgReportComparison with delta information
    """
    # Load previous report
    with open(previous_path, encoding="utf-8") as f:
        prev_data = json.load(f)

    from cja_auto_sdr.org.snapshot_utils import (
        org_report_snapshot_comparison_input,
    )

    try:
        previous_snapshot = org_report_snapshot_comparison_input(
            prev_data,
            require_history_eligible=False,
            require_comparison_eligible=True,
        )
    except ValueError as exc:
        raise ValueError(f"Previous report {previous_path} is not eligible for comparison: {exc}") from exc

    try:
        current_snapshot = org_report_snapshot_comparison_input(
            build_org_report_json_data(current),
            require_history_eligible=False,
            require_comparison_eligible=True,
        )
    except ValueError as exc:
        raise ValueError(f"Current org-report is not eligible for comparison: {exc}") from exc

    return build_org_report_comparison(
        previous=previous_snapshot,
        current=current_snapshot,
    )


def _org_report_history_exclusion_note(
    history_exclusion_reason: str | None,
    *,
    trending_available: bool,
) -> str:
    """Return a user-facing note for low-fidelity current org-report runs."""
    base_note = (
        "Note: Sampled org reports are excluded from persistent trending history."
        if history_exclusion_reason == "sampled"
        else "Note: Org reports without full similarity analysis are excluded from persistent trending history."
    )
    if trending_available:
        return f"{base_note} Using eligible cached snapshots only."
    return f"{base_note} Fewer than 2 eligible cached snapshots found — trending skipped."


def _requested_org_report_baseline_path(org_config: OrgReportConfig) -> Path | None:
    """Return the explicitly requested org-report baseline, if any.

    ``--compare-org-report`` serves two roles in the v3.4.0 org-report flow:
    it is both the comparison baseline and an explicit history anchor that should
    be folded into the trending window when trending is enabled. Centralizing the
    path resolution here keeps both features wired to the same source of truth.
    """
    if not org_config.compare_org_report:
        return None
    return Path(org_config.compare_org_report)


def _org_report_trending_preserved_snapshot_paths(
    *,
    snapshot_cache_dir: Path,
    org_id: str,
    trending_window: int,
    saved_snapshot_path: str | Path,
    explicit_history_file: str | Path | None,
    trending: OrgReportTrending | None,
) -> list[str]:
    """Return normalized snapshot paths that must survive auto-prune."""
    from cja_auto_sdr.org.snapshot_utils import snapshot_path_text
    from cja_auto_sdr.org.trending import discover_snapshots

    eligible_window = (
        trending.snapshots
        if trending is not None
        else discover_snapshots(
            cache_dir=snapshot_cache_dir,
            window_size=trending_window,
            explicit_file=explicit_history_file,
            org_id=org_id,
        )
    )

    preserved_paths: list[str] = []
    seen_paths: set[str] = set()
    for raw_path in (
        saved_snapshot_path,
        explicit_history_file,
        *(snapshot.source_path for snapshot in eligible_window),
    ):
        normalized_path = snapshot_path_text(raw_path)
        if not normalized_path or normalized_path in seen_paths:
            continue
        seen_paths.add(normalized_path)
        preserved_paths.append(normalized_path)

    return preserved_paths


def _build_org_report_trending_window(
    *,
    result: OrgReportResult,
    trending_window: int,
    cache: OrgReportCache | None,
    explicit_history_file: str | Path | None,
    logger: logging.Logger,
    quiet: bool,
    status_print: Callable[..., None],
):
    """Build a trending window while treating current-run eligibility and persistence separately."""
    from cja_auto_sdr.org.snapshot_utils import org_report_snapshot_history_assessment
    from cja_auto_sdr.org.trending import _extract_snapshot_from_json, build_trending
    from cja_auto_sdr.org.writers import build_org_report_json_data as _build_json_for_snapshot

    snapshot_cache = cache if cache is not None else OrgReportCache(logger=logger)
    snapshot_cache_dir = snapshot_cache.get_org_report_snapshot_root_dir()
    current_json = _build_json_for_snapshot(result)
    history_assessment = org_report_snapshot_history_assessment(current_json)
    history_exclusion_reason = history_assessment.exclusion_reason

    current_snapshot = None
    saved_snapshot_path: str | Path | None = None
    try:
        saved_snapshot_path = snapshot_cache.save_org_report_snapshot(current_json, org_id=result.org_id)
    except (OSError, ValueError) as exc:
        if not quiet:
            status_print(ConsoleColors.warning(f"Warning: Could not persist org-report snapshot history: {exc}"))

    if history_exclusion_reason is None:
        current_snapshot = _extract_snapshot_from_json(current_json)
        if current_snapshot is None and not quiet:
            status_print(
                ConsoleColors.warning(
                    "Warning: Current org-report could not be normalized for persistent trending history; "
                    "using eligible cached snapshots only.",
                ),
            )

    trending = build_trending(
        cache_dir=snapshot_cache_dir,
        window_size=trending_window,
        current_snapshot=current_snapshot,
        explicit_file=explicit_history_file,
        org_id=result.org_id,
    )

    if not quiet:
        if history_exclusion_reason is not None:
            status_print(
                ConsoleColors.warning(
                    _org_report_history_exclusion_note(
                        history_exclusion_reason,
                        trending_available=trending is not None,
                    ),
                ),
            )
        elif trending is None:
            status_print(
                ConsoleColors.warning(
                    "Note: Fewer than 2 org-report snapshots found in persistent cache — trending skipped."
                ),
            )

    if saved_snapshot_path is not None:
        preserved_snapshot_paths = _org_report_trending_preserved_snapshot_paths(
            snapshot_cache_dir=snapshot_cache_dir,
            org_id=result.org_id,
            trending_window=trending_window,
            saved_snapshot_path=saved_snapshot_path,
            explicit_history_file=explicit_history_file,
            trending=trending,
        )
        try:
            snapshot_cache.prune_org_report_snapshots(
                org_id=result.org_id,
                keep_last=max(DEFAULT_ORG_REPORT_SNAPSHOT_KEEP_LAST, trending_window),
                preserved_snapshot_paths=preserved_snapshot_paths,
            )
        except OSError as exc:
            if not quiet:
                status_print(ConsoleColors.warning(f"Warning: Could not prune org-report snapshot history: {exc}"))

    return trending


# ==================== ORG REPORT WRITERS (EXTRACTED) ====================
# The following functions have been moved to cja_auto_sdr.org.writers:
# - _render_distribution_bar
# - write_org_report_console
# - write_org_report_stats_only
# - write_org_report_comparison_console
# - _normalize_recommendation_severity
# - _format_recommendation_context_entries
# - _normalize_recommendation_for_json
# - _flatten_recommendation_for_tabular
# - build_org_report_json_data
# - write_org_report_json
# - write_org_report_excel
# - write_org_report_markdown
# - write_org_report_html
# - write_org_report_csv
# - _normalize_org_report_output_format
# - _validate_org_report_output_request


def run_org_report(
    config_file: str,
    output_format: str,
    output_path: str | None,
    output_dir: str,
    org_config: OrgReportConfig,
    profile: str | None = None,
    quiet: bool = False,
    trending_window: int | None = None,
) -> tuple[bool, bool]:
    """Run org-wide component analysis and generate report.

    Args:
        config_file: Path to CJA configuration file
        output_format: Output format (console, json, excel, markdown, html, csv, all)
        output_path: Optional specific output file path
        output_dir: Output directory for generated files
        org_config: OrgReportConfig with analysis parameters
        profile: Optional profile name for credentials
        quiet: Suppress progress output
        trending_window: If set, compute trending across last N cached snapshots

    Returns:
        Tuple of (success, thresholds_exceeded) - thresholds_exceeded triggers exit code 2
    """
    # Setup logging
    logger = logging.getLogger("org_report")
    logger.setLevel(logging.INFO if not quiet else logging.WARNING)

    output_format = _normalize_org_report_output_format(output_format)
    output_to_stdout = output_path in ("-", "stdout")
    status_to_stderr = output_to_stdout and output_format == "json"
    status_stream = sys.stderr if status_to_stderr else sys.stdout

    def _status_print(*args, **kwargs) -> None:
        kwargs.setdefault("file", status_stream)
        print(*args, **kwargs)

    if not _validate_org_report_output_request(output_format, output_to_stdout, _status_print):
        return False, False

    if not quiet:
        _status_print()
        _status_print("=" * 110)
        _status_print("ORG-WIDE COMPONENT ANALYSIS")
        _status_print("=" * 110)
        if profile:
            _status_print(f"\nUsing profile: {profile}")
        _status_print()

    try:
        # Configure CJA connection
        success, source, credentials = configure_cjapy(profile, config_file)
        if not success:
            _status_print(ConsoleColors.error(f"ERROR: {source}"))
            return False, False

        # Extract org_id from credentials
        org_id = credentials.get("org_id", "unknown") if credentials else "unknown"

        cja = cjapy.CJA()

        # Create cache if caching enabled
        cache = None
        if org_config.use_cache:
            cache = OrgReportCache()
            if not quiet:
                stats = cache.get_stats()
                if stats["entries"] > 0:
                    _status_print(f"Cache: {stats['entries']} entries available")

        # Run analysis
        analyzer = OrgComponentAnalyzer(cja, org_config, logger, org_id=org_id, cache=cache)
        result = analyzer.run_analysis()
        requested_baseline_path = _requested_org_report_baseline_path(org_config)

        if result.total_data_views == 0:
            _status_print(ConsoleColors.warning("No data views found matching criteria"))
            return False, False

        # Handle org-report comparison (Feature 4)
        comparison = None
        if requested_baseline_path is not None:
            try:
                if not quiet:
                    _status_print(f"\nComparing to previous report: {requested_baseline_path}")
                comparison = compare_org_reports(result, str(requested_baseline_path))
                with contextlib.redirect_stdout(status_stream):
                    write_org_report_comparison_console(comparison, quiet)
            except FileNotFoundError:
                _status_print(ConsoleColors.error(f"ERROR: Previous report not found: {requested_baseline_path}"))
            except json.JSONDecodeError:
                _status_print(
                    ConsoleColors.error(f"ERROR: Invalid JSON in previous report: {requested_baseline_path}"),
                )
            except ValueError as exc:
                _status_print(ConsoleColors.error(f"ERROR: {exc}"))
            except RECOVERABLE_API_EXCEPTIONS as e:
                _status_print(ConsoleColors.warning(f"Warning: Could not compare reports: {e}"))

        # Trending analysis (v3.4.0)
        trending = None
        if trending_window is not None:
            try:
                trending = _build_org_report_trending_window(
                    result=result,
                    trending_window=trending_window,
                    cache=cache,
                    explicit_history_file=requested_baseline_path,
                    logger=logger,
                    quiet=quiet,
                    status_print=_status_print,
                )
            except OSError as e:
                if not quiet:
                    _status_print(ConsoleColors.warning(f"Warning: Could not load org-report snapshot history: {e}"))

        # Generate output based on format
        output_path_obj = Path(output_path) if output_path and not output_to_stdout else None

        # Handle org-stats mode (Feature 2) - minimal output
        if org_config.org_stats_only:
            with contextlib.redirect_stdout(status_stream):
                write_org_report_stats_only(result, quiet=quiet, trending=trending)
            # Still output JSON if requested for CI integration
            if output_format == "json":
                if output_to_stdout:
                    json.dump(
                        build_org_report_json_data(result, trending=trending), sys.stdout, indent=2, ensure_ascii=False
                    )
                    print()
                else:
                    file_path = write_org_report_json(result, output_path_obj, output_dir, logger, trending=trending)
                    if not quiet:
                        _status_print(f"JSON saved to: {file_path}")
            append_github_step_summary(build_org_step_summary(result), logger)
            return True, result.thresholds_exceeded

        # Handle format aliases (reports, data, ci)
        if output_format in FORMAT_ALIASES:
            formats_to_generate = FORMAT_ALIASES[output_format]
            generated_files = []
            alias_base = output_path_obj.with_suffix("") if output_path_obj else None
            for fmt in formats_to_generate:
                if fmt == "json":
                    path = write_org_report_json(result, alias_base, output_dir, logger, trending=trending)
                    generated_files.append(f"JSON: {path}")
                elif fmt == "excel":
                    path = write_org_report_excel(result, alias_base, output_dir, logger, trending=trending)
                    generated_files.append(f"Excel: {path}")
                elif fmt == "markdown":
                    path = write_org_report_markdown(result, alias_base, output_dir, logger, trending=trending)
                    generated_files.append(f"Markdown: {path}")
                elif fmt == "csv":
                    path = write_org_report_csv(result, alias_base, output_dir, logger, trending=trending)
                    generated_files.append(f"CSV: {path}")
                elif fmt == "html":
                    path = write_org_report_html(result, alias_base, output_dir, logger, trending=trending)
                    generated_files.append(f"HTML: {path}")
            if not quiet:
                _status_print(f"\n{ConsoleColors.success('✓')} Reports saved ({output_format} alias):")
                for f in generated_files:
                    _status_print(f"  - {f}")
        elif output_format == "console" or (output_format is None and output_path is None):
            write_org_report_console(result, org_config, quiet, trending=trending)
        elif output_format == "json":
            if output_to_stdout:
                json.dump(
                    build_org_report_json_data(result, trending=trending), sys.stdout, indent=2, ensure_ascii=False
                )
                print()
            else:
                file_path = write_org_report_json(result, output_path_obj, output_dir, logger, trending=trending)
                if not quiet:
                    _status_print(f"\n{ConsoleColors.success('✓')} JSON report saved to: {file_path}")
        elif output_format == "excel":
            file_path = write_org_report_excel(result, output_path_obj, output_dir, logger, trending=trending)
            if not quiet:
                _status_print(f"\n{ConsoleColors.success('✓')} Excel report saved to: {file_path}")
        elif output_format == "markdown":
            file_path = write_org_report_markdown(result, output_path_obj, output_dir, logger, trending=trending)
            if not quiet:
                _status_print(f"\n{ConsoleColors.success('✓')} Markdown report saved to: {file_path}")
        elif output_format == "html":
            file_path = write_org_report_html(result, output_path_obj, output_dir, logger, trending=trending)
            if not quiet:
                _status_print(f"\n{ConsoleColors.success('✓')} HTML report saved to: {file_path}")
        elif output_format == "csv":
            if output_to_stdout:
                _status_print(
                    ConsoleColors.error(
                        "ERROR: CSV output for org-report writes multiple files and cannot be sent to stdout. Use --output-dir or a file path.",
                    ),
                )
                return False, False
            csv_dir = write_org_report_csv(result, output_path_obj, output_dir, logger, trending=trending)
            if not quiet:
                _status_print(f"\n{ConsoleColors.success('✓')} CSV reports saved to: {csv_dir}")
        elif output_format == "all":
            # Generate all formats
            write_org_report_console(result, org_config, quiet, trending=trending)
            all_base = output_path_obj.with_suffix("") if output_path_obj else None
            json_path = write_org_report_json(result, all_base, output_dir, logger, trending=trending)
            excel_path = write_org_report_excel(result, all_base, output_dir, logger, trending=trending)
            md_path = write_org_report_markdown(result, all_base, output_dir, logger, trending=trending)
            html_path = write_org_report_html(result, all_base, output_dir, logger, trending=trending)
            csv_dir = write_org_report_csv(result, all_base, output_dir, logger, trending=trending)
            if not quiet:
                _status_print(f"\n{ConsoleColors.success('✓')} Reports saved:")
                _status_print(f"  - JSON: {json_path}")
                _status_print(f"  - Excel: {excel_path}")
                _status_print(f"  - Markdown: {md_path}")
                _status_print(f"  - HTML: {html_path}")
                _status_print(f"  - CSV: {csv_dir}")
        else:
            # Defensive fallback. This should be unreachable due to early validation.
            _status_print(ConsoleColors.error(f"ERROR: Unsupported format '{output_format}'"))
            return False, False

        if not quiet:
            _status_print()
            _status_print("=" * 110)
            _status_print(f"Analysis completed in {result.duration:.2f}s")
            # Show governance violation summary if thresholds exceeded
            if result.thresholds_exceeded and org_config.fail_on_threshold:
                _status_print(
                    ConsoleColors.warning(
                        f"GOVERNANCE THRESHOLDS EXCEEDED - {len(result.governance_violations or [])} violation(s)",
                    ),
                )
            _status_print("=" * 110)

        append_github_step_summary(build_org_step_summary(result), logger)
        return True, result.thresholds_exceeded

    except FileNotFoundError:
        _status_print(ConsoleColors.error(f"ERROR: Configuration file '{config_file}' not found"))
        return False, False

    except KeyboardInterrupt, SystemExit:
        if not quiet:
            _status_print()
            _status_print(ConsoleColors.warning("Operation cancelled."))
        raise

    except RECOVERABLE_COMMAND_HANDLER_EXCEPTIONS as e:
        _status_print(ConsoleColors.error(f"ERROR: Org report failed: {e!s}"))
        if isinstance(e, RECOVERABLE_ORG_REPORT_EXCEPTIONS):
            logger.exception("Org report error")
        else:
            logger.exception("Unexpected org report error")
        return False, False


# ==================== DIFF AND SNAPSHOT COMMAND HANDLERS ====================


def handle_snapshot_command(
    data_view_id: str,
    snapshot_file: str,
    config_file: str = "config.json",
    quiet: bool = False,
    profile: str | None = None,
    include_calculated_metrics: bool = False,
    include_segments: bool = False,
) -> bool:
    from cja_auto_sdr.diff.commands import handle_snapshot_command as _impl

    return _impl(
        data_view_id=data_view_id,
        snapshot_file=snapshot_file,
        config_file=config_file,
        quiet=quiet,
        profile=profile,
        include_calculated_metrics=include_calculated_metrics,
        include_segments=include_segments,
    )


def handle_diff_command(
    source_id: str,
    target_id: str,
    config_file: str = "config.json",
    output_format: str = "console",
    output_dir: str = ".",
    changes_only: bool = False,
    summary_only: bool = False,
    ignore_fields: list[str] | None = None,
    labels: tuple[str, str] | None = None,
    quiet: bool = False,
    show_only: list[str] | None = None,
    metrics_only: bool = False,
    dimensions_only: bool = False,
    extended_fields: bool = False,
    side_by_side: bool = False,
    no_color: bool = False,
    quiet_diff: bool = False,
    reverse_diff: bool = False,
    warn_threshold: float | None = None,
    group_by_field: bool = False,
    group_by_field_limit: int = 10,
    diff_output: str | None = None,
    format_pr_comment: bool = False,
    auto_snapshot: bool = False,
    auto_prune: bool = False,
    snapshot_dir: str = "./snapshots",
    keep_last: int = 0,
    keep_since: str | None = None,
    keep_last_specified: bool = False,
    keep_since_specified: bool = False,
    profile: str | None = None,
    diff_config: DiffConfig | None = None,
) -> tuple[bool, bool, int | None]:
    from cja_auto_sdr.diff.commands import handle_diff_command as _impl

    return _impl(
        source_id=source_id,
        target_id=target_id,
        config_file=config_file,
        output_format=output_format,
        output_dir=output_dir,
        changes_only=changes_only,
        summary_only=summary_only,
        ignore_fields=ignore_fields,
        labels=labels,
        quiet=quiet,
        show_only=show_only,
        metrics_only=metrics_only,
        dimensions_only=dimensions_only,
        extended_fields=extended_fields,
        side_by_side=side_by_side,
        no_color=no_color,
        quiet_diff=quiet_diff,
        reverse_diff=reverse_diff,
        warn_threshold=warn_threshold,
        group_by_field=group_by_field,
        group_by_field_limit=group_by_field_limit,
        diff_output=diff_output,
        format_pr_comment=format_pr_comment,
        auto_snapshot=auto_snapshot,
        auto_prune=auto_prune,
        snapshot_dir=snapshot_dir,
        keep_last=keep_last,
        keep_since=keep_since,
        keep_last_specified=keep_last_specified,
        keep_since_specified=keep_since_specified,
        profile=profile,
        diff_config=diff_config,
    )


def handle_diff_snapshot_command(
    data_view_id: str,
    snapshot_file: str,
    config_file: str = "config.json",
    output_format: str = "console",
    output_dir: str = ".",
    changes_only: bool = False,
    summary_only: bool = False,
    ignore_fields: list[str] | None = None,
    labels: tuple[str, str] | None = None,
    quiet: bool = False,
    show_only: list[str] | None = None,
    metrics_only: bool = False,
    dimensions_only: bool = False,
    extended_fields: bool = False,
    side_by_side: bool = False,
    no_color: bool = False,
    quiet_diff: bool = False,
    reverse_diff: bool = False,
    warn_threshold: float | None = None,
    group_by_field: bool = False,
    group_by_field_limit: int = 10,
    diff_output: str | None = None,
    format_pr_comment: bool = False,
    auto_snapshot: bool = False,
    auto_prune: bool = False,
    snapshot_dir: str = "./snapshots",
    keep_last: int = 0,
    keep_since: str | None = None,
    keep_last_specified: bool = False,
    keep_since_specified: bool = False,
    profile: str | None = None,
    include_calc_metrics: bool = False,
    include_segments: bool = False,
    diff_snapshot_config: DiffSnapshotConfig | None = None,
) -> tuple[bool, bool, int | None]:
    from cja_auto_sdr.diff.commands import handle_diff_snapshot_command as _impl

    return _impl(
        data_view_id=data_view_id,
        snapshot_file=snapshot_file,
        config_file=config_file,
        output_format=output_format,
        output_dir=output_dir,
        changes_only=changes_only,
        summary_only=summary_only,
        ignore_fields=ignore_fields,
        labels=labels,
        quiet=quiet,
        show_only=show_only,
        metrics_only=metrics_only,
        dimensions_only=dimensions_only,
        extended_fields=extended_fields,
        side_by_side=side_by_side,
        no_color=no_color,
        quiet_diff=quiet_diff,
        reverse_diff=reverse_diff,
        warn_threshold=warn_threshold,
        group_by_field=group_by_field,
        group_by_field_limit=group_by_field_limit,
        diff_output=diff_output,
        format_pr_comment=format_pr_comment,
        auto_snapshot=auto_snapshot,
        auto_prune=auto_prune,
        snapshot_dir=snapshot_dir,
        keep_last=keep_last,
        keep_since=keep_since,
        keep_last_specified=keep_last_specified,
        keep_since_specified=keep_since_specified,
        profile=profile,
        include_calc_metrics=include_calc_metrics,
        include_segments=include_segments,
        diff_snapshot_config=diff_snapshot_config,
    )


def handle_compare_snapshots_command(
    source_file: str,
    target_file: str,
    output_format: str = "console",
    output_dir: str = ".",
    changes_only: bool = False,
    summary_only: bool = False,
    ignore_fields: list[str] | None = None,
    labels: tuple[str, str] | None = None,
    quiet: bool = False,
    show_only: list[str] | None = None,
    metrics_only: bool = False,
    dimensions_only: bool = False,
    extended_fields: bool = False,
    side_by_side: bool = False,
    no_color: bool = False,
    quiet_diff: bool = False,
    reverse_diff: bool = False,
    warn_threshold: float | None = None,
    group_by_field: bool = False,
    group_by_field_limit: int = 10,
    diff_output: str | None = None,
    format_pr_comment: bool = False,
    include_calc_metrics: bool = False,
    include_segments: bool = False,
) -> tuple[bool, bool, int | None]:
    from cja_auto_sdr.diff.commands import handle_compare_snapshots_command as _impl

    return _impl(
        source_file=source_file,
        target_file=target_file,
        output_format=output_format,
        output_dir=output_dir,
        changes_only=changes_only,
        summary_only=summary_only,
        ignore_fields=ignore_fields,
        labels=labels,
        quiet=quiet,
        show_only=show_only,
        metrics_only=metrics_only,
        dimensions_only=dimensions_only,
        extended_fields=extended_fields,
        side_by_side=side_by_side,
        no_color=no_color,
        quiet_diff=quiet_diff,
        reverse_diff=reverse_diff,
        warn_threshold=warn_threshold,
        group_by_field=group_by_field,
        group_by_field_limit=group_by_field_limit,
        diff_output=diff_output,
        format_pr_comment=format_pr_comment,
        include_calc_metrics=include_calc_metrics,
        include_segments=include_segments,
    )


def _dispatch_snapshot_cli_modes(
    args: argparse.Namespace,
    *,
    data_view_inputs: list[str],
    output_to_stdout: bool,
    ignore_fields: list[str] | None,
    labels: tuple[str, str] | None,
    show_only: list[str] | None,
    keep_last_specified: bool,
    keep_since_specified: bool,
    run_state: dict[str, Any] | None = None,
) -> list[str]:
    from cja_auto_sdr.diff.cli import dispatch_snapshot_cli_modes as _impl

    return _impl(
        args,
        data_view_inputs=data_view_inputs,
        output_to_stdout=output_to_stdout,
        ignore_fields=ignore_fields,
        labels=labels,
        show_only=show_only,
        keep_last_specified=keep_last_specified,
        keep_since_specified=keep_since_specified,
        run_state=run_state,
    )


def _dispatch_cross_data_view_diff_cli_mode(
    args: argparse.Namespace,
    *,
    data_view_inputs: list[str],
    ignore_fields: list[str] | None,
    labels: tuple[str, str] | None,
    show_only: list[str] | None,
    keep_last_specified: bool,
    keep_since_specified: bool,
    run_state: dict[str, Any] | None = None,
) -> None:
    from cja_auto_sdr.diff.cli import dispatch_cross_data_view_diff_cli_mode as _impl

    _impl(
        args,
        data_view_inputs=data_view_inputs,
        ignore_fields=ignore_fields,
        labels=labels,
        show_only=show_only,
        keep_last_specified=keep_last_specified,
        keep_since_specified=keep_since_specified,
        run_state=run_state,
    )


def _execute_sdr_processing_modes(
    args: argparse.Namespace,
    *,
    data_views: list[str],
    effective_log_level: str,
    sdr_format: str,
    processing_start_time: float,
    workers_auto: bool,
    quality_report_only: bool,
    inventory_order: list[str],
    api_tuning_config: Any,
    circuit_breaker_config: Any,
) -> dict[str, Any]:
    from cja_auto_sdr.cli.execution import execute_sdr_processing_modes as _impl

    return _impl(
        args,
        data_views=data_views,
        effective_log_level=effective_log_level,
        sdr_format=sdr_format,
        processing_start_time=processing_start_time,
        workers_auto=workers_auto,
        quality_report_only=quality_report_only,
        inventory_order=inventory_order,
        api_tuning_config=api_tuning_config,
        circuit_breaker_config=circuit_breaker_config,
    )


def _resolve_inventory_mode_configuration(args: argparse.Namespace, *, argv: list[str]) -> list[str]:
    from cja_auto_sdr.cli.execution import resolve_inventory_mode_configuration as _impl

    return _impl(args, argv=argv)


def _dispatch_inventory_summary_mode(
    args: argparse.Namespace,
    *,
    data_views: list[str],
    effective_log_level: str,
    inventory_order: list[str],
    run_state: dict[str, Any] | None = None,
) -> None:
    from cja_auto_sdr.cli.execution import dispatch_inventory_summary_mode as _impl

    _impl(
        args,
        data_views=data_views,
        effective_log_level=effective_log_level,
        inventory_order=inventory_order,
        run_state=run_state,
    )


def _prepare_sdr_execution_context(
    args: argparse.Namespace,
    *,
    data_views: list[str],
    show_processing_count: bool = False,
    run_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    from cja_auto_sdr.cli.execution import prepare_sdr_execution_context as _impl

    return _impl(
        args,
        data_views=data_views,
        show_processing_count=show_processing_count,
        run_state=run_state,
    )


# ==================== MAIN FUNCTION ====================


def _describe_dataview_ignored_options(args: argparse.Namespace) -> list[str]:
    """Return discovery filtering options that have no effect on --describe-dataview."""
    ignored: list[str] = []
    if getattr(args, "org_filter", None) is not None:
        ignored.append("--filter")
    if getattr(args, "org_exclude", None) is not None:
        ignored.append("--exclude")
    if getattr(args, "discovery_sort", None) is not None:
        ignored.append("--sort")
    if getattr(args, "org_limit", None) is not None:
        ignored.append("--limit")
    return ignored


def _warn_describe_dataview_ignored_options(args: argparse.Namespace) -> None:
    """Warn when describe_dataview is invoked with ignored discovery options."""
    ignored_options = _describe_dataview_ignored_options(args)
    if not ignored_options:
        return
    verb = "is" if len(ignored_options) == 1 else "are"
    option_label = "option" if len(ignored_options) == 1 else "options"
    print(
        ConsoleColors.warning(
            f"Warning: {', '.join(ignored_options)} {option_label} {verb} ignored with --describe-dataview."
        ),
        file=sys.stderr,
    )


def _build_org_report_snapshot_listing_rows(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize persisted org-report snapshot rows for listing output."""
    return [
        {
            "org_id": snapshot.get("org_id", ""),
            "generated_at": snapshot.get("generated_at", ""),
            "data_views_total": snapshot.get("data_views_total", 0),
            "total_unique_components": snapshot.get("total_unique_components", 0),
            "core_count": snapshot.get("core_count", 0),
            "isolated_count": snapshot.get("isolated_count", 0),
            "high_similarity_pairs": snapshot.get("high_similarity_pairs", 0),
            "history_eligible": (
                snapshot.get("history_eligible", "") if snapshot.get("history_eligible") is not None else ""
            ),
            "history_exclusion_reason": snapshot.get("history_exclusion_reason") or "",
            "filepath": str(snapshot.get("filepath") or snapshot.get("filename") or ""),
        }
        for snapshot in snapshots
    ]


def _resolve_org_report_snapshot_prune_retention(args: argparse.Namespace) -> tuple[int, int | None, str | None]:
    """Resolve validated retention settings for --prune-org-report-snapshots."""
    effective_keep_last = getattr(args, "org_report_keep_last", 0)
    effective_keep_since = getattr(args, "org_report_keep_since", None)
    keep_last_specified, keep_since_specified = _org_report_snapshot_retention_flags_specified()

    if keep_last_specified and effective_keep_last < 0:
        _exit_error("--org-report-keep-last cannot be negative")
    if not keep_last_specified and not keep_since_specified:
        _exit_error(
            "--prune-org-report-snapshots requires --org-report-keep-last and/or --org-report-keep-since",
        )

    keep_since_days = None
    if keep_since_specified:
        keep_since_days = parse_retention_period(effective_keep_since)
        if keep_since_days is None:
            _exit_error(f"Invalid --org-report-keep-since value: {effective_keep_since}")

    return effective_keep_last, keep_since_days, effective_keep_since


def _handle_org_report_snapshot_cli(
    args: argparse.Namespace,
    *,
    output_to_stdout: bool,
    run_state: dict[str, Any] | None = None,
) -> NoReturn:
    """Handle listing, inspection, and pruning for persisted org-report snapshots."""
    snapshot_cache = OrgReportCache()
    org_id = getattr(args, "org_report_snapshot_org", None)
    output_file = getattr(args, "output", None)

    if getattr(args, "list_org_report_snapshots", False):
        snapshots = snapshot_cache.list_org_report_snapshots(org_id=org_id)
        output_format = args.format if args.format in ("json", "csv") else "table"
        if output_to_stdout and output_format == "table":
            output_format = "json"

        if output_format == "json":
            _emit_json_output(
                {
                    "snapshot_root": str(snapshot_cache.get_org_report_snapshot_root_dir()),
                    "org_id": org_id,
                    "count": len(snapshots),
                    "snapshots": snapshots,
                },
                output_file=output_file,
                is_stdout=output_to_stdout,
                contract_label="Org-report snapshot listing output",
            )
        elif output_format == "csv":
            rows = _build_org_report_snapshot_listing_rows(snapshots)
            _emit_output(
                _format_as_csv(
                    [
                        "org_id",
                        "generated_at",
                        "data_views_total",
                        "total_unique_components",
                        "core_count",
                        "isolated_count",
                        "high_similarity_pairs",
                        "history_eligible",
                        "history_exclusion_reason",
                        "filepath",
                    ],
                    rows,
                ),
                output_file,
                output_to_stdout,
            )
        else:
            if snapshots:
                table_rows = _build_org_report_snapshot_listing_rows(snapshots)
                header = f"Found {len(table_rows)} org-report snapshot(s)"
                if org_id:
                    header += f" for {org_id}"
                header += f" in {snapshot_cache.get_org_report_snapshot_root_dir()}:"
                table_text = _format_as_table(
                    header,
                    table_rows,
                    columns=["org_id", "generated_at", "data_views_total", "total_unique_components", "filepath"],
                    col_labels=["Org ID", "Generated", "Data Views", "Components", "Snapshot Path"],
                )
            else:
                table_text = (
                    f"\nNo org-report snapshots found in {snapshot_cache.get_org_report_snapshot_root_dir()}.\n"
                )
            _emit_output(table_text, output_file, output_to_stdout)

        if run_state is not None:
            run_state["output_format"] = output_format
            run_state["details"] = {"operation_success": True, "snapshot_count": len(snapshots), "org_id": org_id}
        sys.exit(0)

    snapshot_path = getattr(args, "inspect_org_report_snapshot", None)
    if snapshot_path:
        try:
            snapshot = snapshot_cache.inspect_org_report_snapshot(snapshot_path)
        except (OSError, ValueError) as exc:
            _exit_error(str(exc))

        output_format = args.format if args.format in ("json", "csv") else "table"
        if output_to_stdout and output_format == "table":
            output_format = "json"

        if output_format == "json":
            _emit_json_output(
                {"snapshot": snapshot},
                output_file=output_file,
                is_stdout=output_to_stdout,
                contract_label="Org-report snapshot inspection output",
            )
        elif output_format == "csv":
            _emit_output(
                _format_as_csv(
                    [
                        "org_id",
                        "generated_at",
                        "data_views_total",
                        "total_unique_components",
                        "core_count",
                        "isolated_count",
                        "high_similarity_pairs",
                        "history_eligible",
                        "history_exclusion_reason",
                        "filepath",
                    ],
                    [snapshot],
                ),
                output_file,
                output_to_stdout,
            )
        else:
            lines = [
                "",
                "Org-Report Snapshot",
                "=" * 80,
                f"Org ID:               {snapshot.get('org_id', '')}",
                f"Generated:            {snapshot.get('generated_at', '')}",
                f"Data views:           {snapshot.get('data_views_total', 0)}",
                f"Unique components:    {snapshot.get('total_unique_components', 0)}",
                f"Core components:      {snapshot.get('core_count', 0)}",
                f"Isolated components:  {snapshot.get('isolated_count', 0)}",
                f"High-similarity pairs:{snapshot.get('high_similarity_pairs', 0)}",
                f"History eligible:     {snapshot.get('history_eligible', '')}",
                f"History exclusion:    {snapshot.get('history_exclusion_reason') or ''}",
                f"File:                 {snapshot.get('filepath', '')}",
            ]
            preview_names = snapshot.get("data_view_names_preview", [])
            if preview_names:
                lines.extend(["", "Data view preview:"])
                lines.extend([f"  - {name}" for name in preview_names])
                if snapshot.get("data_view_names_truncated"):
                    lines.append(f"  ... ({snapshot.get('data_view_names_total', len(preview_names))} total)")
            lines.append("")
            _emit_output("\n".join(lines), output_file, output_to_stdout)

        if run_state is not None:
            run_state["output_format"] = output_format
            run_state["details"] = {
                "operation_success": True,
                "snapshot_file": snapshot.get("filepath", snapshot_path),
                "org_id": snapshot.get("org_id"),
            }
        sys.exit(0)

    effective_keep_last, keep_since_days, effective_keep_since = _resolve_org_report_snapshot_prune_retention(args)

    deleted_paths = snapshot_cache.prune_org_report_snapshots(
        org_id=org_id,
        keep_last=effective_keep_last,
        keep_since_days=keep_since_days,
    )

    output_format = args.format if args.format in ("json", "csv") else "table"
    if output_to_stdout and output_format == "table":
        output_format = "json"

    if output_format == "json":
        _emit_json_output(
            {
                "snapshot_root": str(snapshot_cache.get_org_report_snapshot_root_dir()),
                "org_id": org_id,
                "deleted_count": len(deleted_paths),
                "deleted_files": deleted_paths,
                "retention": {"keep_last": effective_keep_last, "keep_since": effective_keep_since},
            },
            output_file=output_file,
            is_stdout=output_to_stdout,
            contract_label="Org-report snapshot prune output",
        )
    elif output_format == "csv":
        _emit_output(
            _format_as_csv(["filepath"], [{"filepath": path} for path in deleted_paths]), output_file, output_to_stdout
        )
    else:
        lines = [
            "",
            f"Org-report snapshot prune complete for {snapshot_cache.get_org_report_snapshot_root_dir()}",
            f"Deleted files: {len(deleted_paths)}",
            f"Retention keep_last: {effective_keep_last}",
            f"Retention keep_since: {effective_keep_since or '-'}",
        ]
        if org_id:
            lines.append(f"Target org: {org_id}")
        if deleted_paths:
            lines.extend(["", "Deleted files:"])
            lines.extend([f"  - {Path(path).name}" for path in deleted_paths])
        lines.append("")
        _emit_output("\n".join(lines), output_file, output_to_stdout)

    if run_state is not None:
        run_state["output_format"] = output_format
        run_state["details"] = {
            "operation_success": True,
            "deleted_count": len(deleted_paths),
            "retention": {"keep_last": effective_keep_last, "keep_since": effective_keep_since},
            "org_id": org_id,
        }
    sys.exit(0)


def _dispatch_post_validation_report_modes(
    args: argparse.Namespace,
    *,
    output_to_stdout: bool,
    run_state: dict[str, Any] | None = None,
) -> list[str]:
    """Handle config/status, interactive, stats, and org-report branches."""
    if getattr(args, "config_status", False) or getattr(args, "config_json", False):
        output_json = getattr(args, "config_json", False)
        success = show_config_status(args.config_file, profile=getattr(args, "profile", None), output_json=output_json)
        if run_state is not None:
            run_state["details"] = {"operation_success": success}
        sys.exit(0 if success else 1)

    if args.validate_config:
        success = validate_config_only(
            args.config_file,
            profile=getattr(args, "profile", None),
            output_dir=getattr(args, "output_dir", "."),
        )
        if run_state is not None:
            run_state["details"] = {"operation_success": success}
        sys.exit(0 if success else 1)

    data_view_inputs = args.data_views
    if run_state is not None:
        run_state["data_view_inputs"] = list(data_view_inputs)

    if getattr(args, "interactive", False):
        if data_view_inputs:
            print(ConsoleColors.warning("Note: --interactive mode ignores positional data view arguments"))

        wizard_config = interactive_wizard(args.config_file, profile=getattr(args, "profile", None))
        if wizard_config is None:
            print("Cancelled. Exiting.")
            sys.exit(0)

        data_view_inputs = wizard_config.data_view_ids
        args.format = wizard_config.output_format
        args.include_segments_inventory = wizard_config.include_segments
        args.include_calculated_metrics = wizard_config.include_calculated
        args.include_derived_inventory = wizard_config.include_derived
        args.inventory_only = wizard_config.inventory_only
        if run_state is not None:
            run_state["data_view_inputs"] = list(data_view_inputs)

        print()
        print("=" * BANNER_WIDTH)
        print("GENERATING SDR...")
        print("=" * BANNER_WIDTH)
        print()

    if getattr(args, "stats", False):
        if not data_view_inputs:
            print(ConsoleColors.error("ERROR: --stats requires at least one data view ID or name"), file=sys.stderr)
            sys.exit(1)

        temp_logger = logging.getLogger("name_resolution")
        temp_logger.setLevel(logging.WARNING)
        resolved_ids, _ = resolve_data_view_names(
            data_view_inputs,
            args.config_file,
            temp_logger,
            profile=getattr(args, "profile", None),
            match_mode=getattr(args, "name_match", "exact"),
        )

        if not resolved_ids:
            print(ConsoleColors.error("ERROR: No valid data views found"), file=sys.stderr)
            sys.exit(1)
        if run_state is not None:
            run_state["resolved_data_views"] = list(resolved_ids)

        stats_format = "table"
        if args.format in ("json", "csv"):
            stats_format = args.format
        elif output_to_stdout:
            stats_format = "json"

        success = show_stats(
            resolved_ids,
            config_file=args.config_file,
            output_format=stats_format,
            output_file=getattr(args, "output", None),
            quiet=args.quiet,
            profile=getattr(args, "profile", None),
        )
        if run_state is not None:
            run_state["output_format"] = stats_format
            run_state["details"] = {"operation_success": success}
        sys.exit(0 if success else 1)

    if getattr(args, "org_report", False):
        org_config = OrgReportConfig(
            filter_pattern=getattr(args, "org_filter", None),
            exclude_pattern=getattr(args, "org_exclude", None),
            limit=getattr(args, "org_limit", None),
            core_threshold=getattr(args, "core_threshold", 0.5),
            core_min_count=getattr(args, "core_min_count", None),
            overlap_threshold=getattr(args, "overlap_threshold", 0.8),
            summary_only=getattr(args, "org_summary", False) or getattr(args, "summary", False),
            verbose=getattr(args, "org_verbose", False),
            include_names=getattr(args, "org_include_names", False),
            skip_similarity=getattr(args, "skip_similarity", False),
            similarity_max_dvs=getattr(args, "org_similarity_max_dvs", 250),
            force_similarity=getattr(args, "org_force_similarity", False),
            include_component_types=not getattr(args, "no_component_types", False),
            include_metadata=getattr(args, "org_include_metadata", False),
            include_drift=getattr(args, "org_include_drift", False),
            sample_size=getattr(args, "org_sample_size", None),
            sample_seed=getattr(args, "org_sample_seed", None),
            sample_stratified=getattr(args, "org_sample_stratified", False),
            use_cache=getattr(args, "org_use_cache", False),
            cache_max_age_hours=getattr(args, "org_cache_max_age", 24),
            clear_cache=getattr(args, "org_clear_cache", False),
            validate_cache=getattr(args, "org_validate_cache", False),
            memory_warning_threshold_mb=getattr(args, "org_memory_warning", 100),
            memory_limit_mb=getattr(args, "org_memory_limit", None),
            enable_clustering=getattr(args, "org_cluster", False),
            cluster_method=getattr(args, "org_cluster_method", "average"),
            quiet=args.quiet,
            cja_per_thread=not getattr(args, "org_shared_client", False),
            duplicate_threshold=getattr(args, "org_duplicate_threshold", None),
            isolated_threshold=getattr(args, "org_isolated_threshold", None),
            fail_on_threshold=getattr(args, "org_fail_on_threshold", False),
            org_stats_only=getattr(args, "org_stats_only", False),
            audit_naming=getattr(args, "org_audit_naming", False),
            compare_org_report=getattr(args, "org_compare_report", None),
            include_owner_summary=getattr(args, "org_owner_summary", False),
            flag_stale=getattr(args, "org_flag_stale", False),
        )

        output_format = args.format or "console"
        trending_window = getattr(args, "trending_window", None)
        if trending_window is not None and trending_window < 2:
            _exit_error("--trending-window must be >= 2")

        success, thresholds_exceeded = run_org_report(
            config_file=args.config_file,
            output_format=output_format,
            output_path=getattr(args, "output", None),
            output_dir=args.output_dir,
            org_config=org_config,
            profile=getattr(args, "profile", None),
            quiet=args.quiet,
            trending_window=trending_window,
        )
        if run_state is not None:
            run_state["output_format"] = output_format
            run_state["details"] = {
                "operation_success": success,
                "thresholds_exceeded": thresholds_exceeded,
                "fail_on_threshold": org_config.fail_on_threshold,
            }

        if success:
            if thresholds_exceeded and org_config.fail_on_threshold:
                sys.exit(2)
            sys.exit(0)
        sys.exit(1)

    return data_view_inputs


def _main_impl(run_state: dict[str, Any] | None = None):
    """Main CLI implementation."""

    # Parse arguments (will show error and help if no data views provided)
    args = parse_arguments()
    inferred_mode = _infer_run_mode_enum(args)
    active_modes = _active_run_modes(args)
    _sync_run_summary_cli_metadata(run_state, args, inferred_mode=inferred_mode)
    _validate_org_report_snapshot_cli_args(args, active_modes=active_modes)

    # Dispatch early command modes before unrelated validation. Use inferred
    # mode so dispatch precedence cannot diverge from run-mode classification.
    _dispatch_prevalidation_mode(args, inferred_mode, run_state=run_state)

    run_summary_to_stdout = getattr(args, "run_summary_json", None) in ("-", "stdout")
    quality_policy_path = getattr(args, "quality_policy", None)
    applied_quality_policy: dict[str, Any] = {}
    if quality_policy_path:
        if run_state is not None:
            run_state["quality_policy"] = {
                "path": str(Path(quality_policy_path).expanduser()),
                "applied": {},
            }
        try:
            quality_policy = load_quality_policy(quality_policy_path)
        except (OSError, json.JSONDecodeError, ValueError) as e:
            _exit_error(f"Failed to load --quality-policy '{quality_policy_path}': {e}")
        # Only apply quality defaults for SDR generation mode. This keeps
        # shared policy files usable across non-SDR commands.
        if inferred_mode == RunMode.SDR:
            applied_quality_policy = apply_quality_policy_defaults(args, quality_policy)
            _sync_run_summary_cli_metadata(run_state, args, inferred_mode=inferred_mode)
        if run_state is not None and isinstance(run_state.get("quality_policy"), dict):
            run_state["quality_policy"]["applied"] = applied_quality_policy

    # Configure global color policy for all ConsoleColors call sites.
    ConsoleColors.configure(no_color=getattr(args, "no_color", False))

    # Parse and validate --workers argument
    workers_auto = False
    if args.workers.lower() == "auto":
        workers_auto = True
        # Will be set later based on data view count
        args.workers = DEFAULT_BATCH_WORKERS  # Temporary default
    else:
        try:
            args.workers = int(args.workers)
        except ValueError:
            _exit_error(f"--workers must be 'auto' or an integer, got '{args.workers}'")

    # Validate numeric parameter bounds
    if not workers_auto and args.workers < 1:
        _exit_error("--workers must be at least 1")
    if not workers_auto and args.workers > MAX_BATCH_WORKERS:
        _exit_error(f"--workers cannot exceed {MAX_BATCH_WORKERS}")
    if args.cache_size < 1:
        _exit_error("--cache-size must be at least 1")
    if args.cache_ttl < 1:
        _exit_error("--cache-ttl must be at least 1 second")
    if args.max_issues < 0:
        _exit_error("--max-issues cannot be negative")
    if args.max_retries < 0:
        _exit_error("--max-retries cannot be negative")
    if args.retry_base_delay < 0:
        _exit_error("--retry-base-delay cannot be negative")
    if args.retry_max_delay < args.retry_base_delay:
        _exit_error("--retry-max-delay must be >= --retry-base-delay")
    if getattr(args, "org_sample_size", None) is not None and args.org_sample_size < 1:
        _exit_error("--sample must be at least 1")

    # Track whether retention flags were explicitly provided so auto-prune
    # defaults don't override intentional values like --keep-last 0.
    keep_last_specified = _cli_option_specified("--keep-last")
    keep_since_specified = _cli_option_specified("--keep-since")

    non_sdr_mode = inferred_mode != RunMode.SDR
    if getattr(args, "allow_partial", False) and non_sdr_mode:
        _exit_error("--allow-partial is only supported in SDR generation mode")
    if getattr(args, "fail_on_quality", None) and non_sdr_mode:
        _exit_error("--fail-on-quality is only supported in SDR generation mode")
    if getattr(args, "trending_window", None) is not None and inferred_mode != RunMode.ORG_REPORT:
        _exit_error("--trending-window is only supported with --org-report")

    if (
        getattr(args, "auto_prune", False)
        and not getattr(args, "auto_snapshot", False)
        and not getattr(args, "prune_snapshots", False)
    ):
        _exit_error("--auto-prune requires --auto-snapshot or --prune-snapshots")
    if getattr(args, "fail_on_quality", None) and args.skip_validation:
        _exit_error("--fail-on-quality cannot be used with --skip-validation")
    if getattr(args, "quality_report", None) and args.skip_validation:
        _exit_error("--quality-report cannot be used with --skip-validation")
    if getattr(args, "quality_report", None) and non_sdr_mode:
        _exit_error("--quality-report is only supported in SDR generation mode")
    if getattr(args, "allow_partial", False) and getattr(args, "quality_report", None):
        _exit_error("--allow-partial cannot be used with --quality-report")
    if getattr(args, "allow_partial", False) and getattr(args, "fail_on_quality", None):
        _exit_error("--allow-partial cannot be used with --fail-on-quality")

    if getattr(args, "list_snapshots", False) and getattr(args, "prune_snapshots", False):
        _exit_error("Use either --list-snapshots or --prune-snapshots, not both")
    if getattr(args, "profile_overwrite", False) and not getattr(args, "profile_import", None):
        _exit_error("--profile-overwrite requires --profile-import")

    # Propagate retry config via env vars so both the current process
    # (read by _effective_retry_config in resilience.py) and child
    # processes (ProcessPoolExecutor workers) pick up CLI overrides.
    os.environ["MAX_RETRIES"] = str(args.max_retries)
    os.environ["RETRY_BASE_DELAY"] = str(args.retry_base_delay)
    os.environ["RETRY_MAX_DELAY"] = str(args.retry_max_delay)

    # Handle --output for stdout - implies quiet mode
    output_to_stdout = getattr(args, "output", None) in ("-", "stdout")
    if run_summary_to_stdout and output_to_stdout:
        _exit_error("--run-summary-json stdout cannot be combined with --output stdout")
    if output_to_stdout or run_summary_to_stdout:
        args.quiet = True

    # Auto-detect format from output file extension if --format not explicitly set
    output_path = getattr(args, "output", None)
    if output_path and not args.format:
        inferred_format = infer_format_from_path(output_path)
        if inferred_format:
            args.format = inferred_format
            if not args.quiet:
                print(f"Auto-detected format '{inferred_format}' from output file extension")
    _sync_run_summary_cli_metadata(run_state, args)

    if inferred_mode == RunMode.ORG_REPORT_SNAPSHOTS:
        _handle_org_report_snapshot_cli(args, output_to_stdout=output_to_stdout, run_state=run_state)

    # Set color theme for diff output (accessible accessibility)
    color_theme = getattr(args, "color_theme", "default")
    if color_theme and color_theme != "default":
        ConsoleColors.set_theme(color_theme)

    # Handle --exit-codes mode (no data view required)
    if getattr(args, "exit_codes", False):
        from cja_auto_sdr.core.exit_codes import print_exit_codes

        print_exit_codes(banner_width=BANNER_WIDTH)
        sys.exit(0)

    # Handle --sample-config mode (no data view required)
    if args.sample_config:
        success = generate_sample_config()
        if run_state is not None:
            run_state["details"] = {"operation_success": success}
        sys.exit(0 if success else 1)

    # ==================== PROFILE MANAGEMENT COMMANDS ====================

    # Handle --profile-list mode (no data view required)
    if getattr(args, "profile_list", False):
        list_format = _resolve_command_output_format(
            args.format,
            supported_formats={"json": "json", "console": "table", "table": "table"},
            fallback_format="table",
            warning_scope="--profile-list",
        )
        success = list_profiles(output_format=list_format)
        if run_state is not None:
            run_state["details"] = {"operation_success": success}
        sys.exit(0 if success else 1)

    # Handle --profile-import mode (no data view required)
    if getattr(args, "profile_import", None):
        profile_name, source_file = args.profile_import
        success = import_profile_non_interactive(
            profile_name,
            source_file,
            overwrite=getattr(args, "profile_overwrite", False),
        )
        if run_state is not None:
            run_state["details"] = {"operation_success": success}
        sys.exit(0 if success else 1)

    # Handle --profile-add mode (no data view required)
    if getattr(args, "profile_add", None):
        success = add_profile_interactive(args.profile_add)
        if run_state is not None:
            run_state["details"] = {"operation_success": success}
        sys.exit(0 if success else 1)

    # Handle --profile-test mode (no data view required)
    if getattr(args, "profile_test", None):
        success = test_profile(args.profile_test)
        if run_state is not None:
            run_state["details"] = {"operation_success": success}
        sys.exit(0 if success else 1)

    # Handle --profile-show mode (no data view required)
    if getattr(args, "profile_show", None):
        success = show_profile(args.profile_show)
        if run_state is not None:
            run_state["details"] = {"operation_success": success}
        sys.exit(0 if success else 1)

    # Handle --git-init mode (no data view required)
    if getattr(args, "git_init", False):
        git_dir = Path(getattr(args, "git_dir", "./sdr-snapshots"))
        print(f"Initializing Git repository at: {git_dir}")
        success, message = git_init_snapshot_repo(git_dir)
        if success:
            print(ConsoleColors.success(f"SUCCESS: {message}"))
            print(f"  Directory: {git_dir.absolute()}")
            print()
            print("Next steps:")
            print("  1. Run SDR generation with --git-commit to save and commit snapshots")
            print(f"  2. Add a remote: cd {git_dir} && git remote add origin <url>")
            print("  3. Use --git-push to push commits to remote")
        else:
            print(ConsoleColors.error(f"FAILED: {message}"))
        if run_state is not None:
            run_state["details"] = {"operation_success": success}
        sys.exit(0 if success else 1)

    # Validate Git argument combinations
    if getattr(args, "git_push", False) and not getattr(args, "git_commit", False):
        print(ConsoleColors.error("ERROR: --git-push requires --git-commit"), file=sys.stderr)
        sys.exit(1)

    # Validate: --include-derived is not supported with --git-commit
    # Derived fields are for SDR generation only - they're computed from metrics/dimensions
    if getattr(args, "git_commit", False) and getattr(args, "include_derived_inventory", False):
        print(ConsoleColors.error("ERROR: --include-derived cannot be used with --git-commit"), file=sys.stderr)
        print("Derived fields inventory is only available in SDR generation mode.", file=sys.stderr)
        print("Derived field changes are captured in the standard Metrics/Dimensions diff.", file=sys.stderr)
        sys.exit(1)

    # Handle discovery commands (no data view required)
    _discovery_commands = {
        "list_dataviews": list_dataviews,
        "list_connections": list_connections,
        "list_datasets": list_datasets,
    }
    for attr, func in _discovery_commands.items():
        if getattr(args, attr, False):
            list_format = _resolve_discovery_output_format(args.format, output_to_stdout=output_to_stdout)
            success = func(
                args.config_file,
                output_format=list_format,
                output_file=getattr(args, "output", None),
                profile=getattr(args, "profile", None),
                filter_pattern=getattr(args, "org_filter", None),
                exclude_pattern=getattr(args, "org_exclude", None),
                limit=getattr(args, "org_limit", None),
                sort_expression=getattr(args, "discovery_sort", None),
            )
            if run_state is not None:
                run_state["output_format"] = list_format
                run_state["details"] = {"operation_success": success, "discovery_command": attr}
            sys.exit(0 if success else 1)

    # ID-bearing discovery commands (inspection commands that take a data view ID or name)
    _discovery_commands_id = {
        "describe_dataview": describe_dataview,
        "list_metrics": list_metrics,
        "list_dimensions": list_dimensions,
        "list_segments": list_segments,
        "list_calculated_metrics": list_calculated_metrics,
    }
    for attr, func in _discovery_commands_id.items():
        resource_id_or_name = getattr(args, attr, None)
        if resource_id_or_name:
            list_format = _resolve_discovery_output_format(args.format, output_to_stdout=output_to_stdout)
            is_machine_readable_discovery = _is_machine_readable_output(list_format, getattr(args, "output", None))
            if attr == "describe_dataview" and not is_machine_readable_discovery:
                _warn_describe_dataview_ignored_options(args)
            resolved_resource_name: str | None = None
            # Resolve name → ID if needed (IDs pass through without API call)
            if is_data_view_id(resource_id_or_name):
                resource_id = resource_id_or_name
            else:
                temp_logger = _build_inspection_name_resolution_logger()
                resolution_result = resolve_data_view_names(
                    [resource_id_or_name],
                    args.config_file,
                    temp_logger,
                    profile=getattr(args, "profile", None),
                    match_mode=getattr(args, "name_match", "exact"),
                    include_diagnostics=True,
                )
                resolved_ids, _, resolution_diagnostics = _coerce_name_resolution_result(resolution_result)
                resolved_name_by_id = resolution_diagnostics.resolved_name_by_id
                if not resolved_ids:
                    resolution_error_type = resolution_diagnostics.error_type or "not_found"
                    if resolution_error_type == "not_found":
                        resolution_message = (
                            f"Could not resolve data view: '{resource_id_or_name}'. "
                            "Run 'cja_auto_sdr --list-dataviews' to see available names and IDs."
                        )
                    else:
                        resolution_message = (
                            resolution_diagnostics.error_message
                            or f"Failed to resolve data view: '{resource_id_or_name}'."
                        )
                    _emit_discovery_error(
                        resolution_message,
                        is_machine_readable=is_machine_readable_discovery,
                        error_type=resolution_error_type,
                        human_to_stderr=True,
                    )
                    sys.exit(1)
                if len(resolved_ids) > 1:
                    if is_machine_readable_discovery:
                        _emit_discovery_error(
                            (
                                f"Name '{resource_id_or_name}' is ambiguous and matches "
                                f"{len(resolved_ids)} data views. Specify an exact data view ID."
                            ),
                            is_machine_readable=True,
                            error_type="ambiguous_name",
                            additional_fields={
                                "data_view_name": resource_id_or_name,
                                "matches": resolved_ids,
                            },
                            human_to_stderr=True,
                        )
                        sys.exit(1)
                    options = [(dv_id, f"{resource_id_or_name} ({dv_id})") for dv_id in resolved_ids]
                    selected = prompt_for_selection(
                        options,
                        f"Name '{resource_id_or_name}' matches {len(resolved_ids)} data views. Please select one:",
                    )
                    if selected:
                        resource_id = selected
                        resolved_resource_name = resolved_name_by_id.get(resource_id)
                    else:
                        print(
                            ConsoleColors.error(
                                f"ERROR: Name '{resource_id_or_name}' is ambiguous — matches {len(resolved_ids)} data views:",
                            ),
                            file=sys.stderr,
                        )
                        for dv_id in resolved_ids:
                            print(f"  • {dv_id}", file=sys.stderr)
                        print("\nPlease specify the exact data view ID instead of the name.", file=sys.stderr)
                        sys.exit(1)
                else:
                    resource_id = resolved_ids[0]
                    resolved_resource_name = resolved_name_by_id.get(resource_id)

            if attr == "describe_dataview":
                success = func(
                    resource_id,
                    config_file=args.config_file,
                    output_format=list_format,
                    output_file=getattr(args, "output", None),
                    profile=getattr(args, "profile", None),
                )
            else:
                list_kwargs: dict[str, Any] = {
                    "config_file": args.config_file,
                    "output_format": list_format,
                    "output_file": getattr(args, "output", None),
                    "profile": getattr(args, "profile", None),
                    "filter_pattern": getattr(args, "org_filter", None),
                    "exclude_pattern": getattr(args, "org_exclude", None),
                    "limit": getattr(args, "org_limit", None),
                    "sort_expression": getattr(args, "discovery_sort", None),
                }
                if resolved_resource_name is not None:
                    list_kwargs["data_view_name"] = resolved_resource_name
                success = func(resource_id, **list_kwargs)
            if run_state is not None:
                run_state["output_format"] = list_format
                run_state["details"] = {"operation_success": success, "discovery_command": attr}
            sys.exit(0 if success else 1)

    data_view_inputs = _dispatch_post_validation_report_modes(
        args,
        output_to_stdout=output_to_stdout,
        run_state=run_state,
    )

    # Parse ignore_fields if provided
    ignore_fields = None
    if hasattr(args, "ignore_fields") and args.ignore_fields:
        ignore_fields = [f.strip() for f in args.ignore_fields.split(",")]

    # Parse show_only filter if provided
    show_only = None
    if hasattr(args, "show_only") and args.show_only:
        show_only = [t.strip().lower() for t in args.show_only.split(",")]
        valid_types = {"added", "removed", "modified", "unchanged"}
        invalid = set(show_only) - valid_types
        if invalid:
            print(ConsoleColors.error(f"ERROR: Invalid --show-only types: {invalid}"), file=sys.stderr)
            print(f"Valid types: {', '.join(valid_types)}", file=sys.stderr)
            sys.exit(1)

    # Parse labels if provided
    labels = None
    if hasattr(args, "diff_labels") and args.diff_labels:
        labels = tuple(args.diff_labels)

    # Expand --include-all-inventory before any mode-specific dispatch so
    # snapshot/diff handlers receive the resolved inventory flags.
    if getattr(args, "include_all_inventory", False):
        # Always enable segments and calculated metrics.
        args.include_segments_inventory = True
        args.include_calculated_metrics = True

        # Derived inventory is SDR-only; snapshot and snapshot-diff modes
        # should not include it.
        snapshot_like_mode = (
            getattr(args, "snapshot", None)
            or getattr(args, "git_commit", False)
            or getattr(args, "diff_snapshot", None)
            or getattr(args, "compare_snapshots", None)
            or getattr(args, "compare_with_prev", False)
        )
        if not snapshot_like_mode:
            args.include_derived_inventory = True

        if not args.quiet:
            enabled = ["--include-segments", "--include-calculated"]
            if not snapshot_like_mode:
                enabled.append("--include-derived")
            print(ConsoleColors.info(f"--include-all-inventory enabled: {', '.join(enabled)}"))

    data_view_inputs = _dispatch_snapshot_cli_modes(
        args,
        data_view_inputs=data_view_inputs,
        output_to_stdout=output_to_stdout,
        ignore_fields=ignore_fields,
        labels=labels,
        show_only=show_only,
        keep_last_specified=keep_last_specified,
        keep_since_specified=keep_since_specified,
        run_state=run_state,
    )

    # Handle --diff mode (compare two data views)
    if hasattr(args, "diff") and args.diff:
        _dispatch_cross_data_view_diff_cli_mode(
            args,
            data_view_inputs=data_view_inputs,
            ignore_fields=ignore_fields,
            labels=labels,
            show_only=show_only,
            keep_last_specified=keep_last_specified,
            keep_since_specified=keep_since_specified,
            run_state=run_state,
        )

    # Validate that at least one data view is provided
    if not data_view_inputs:
        print(ConsoleColors.error("ERROR: At least one data view ID or name is required"), file=sys.stderr)
        print("Usage: cja_auto_sdr DATA_VIEW_ID_OR_NAME [DATA_VIEW_ID_OR_NAME ...]", file=sys.stderr)
        print("       Use --help for more information", file=sys.stderr)
        sys.exit(1)

    # Resolve data view names to IDs
    # Create a temporary logger for name resolution
    temp_logger = logging.getLogger("name_resolution")
    temp_logger.setLevel(logging.INFO if not args.quiet else logging.ERROR)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
    temp_logger.addHandler(handler)
    temp_logger.propagate = False

    # Show what we're resolving
    names_provided = [dv for dv in data_view_inputs if not is_data_view_id(dv)]

    if names_provided and not args.quiet:
        print()
        print(ConsoleColors.info(f"Resolving {len(names_provided)} data view name(s)..."))

    data_views, name_to_ids_map = resolve_data_view_names(
        data_view_inputs,
        args.config_file,
        temp_logger,
        profile=getattr(args, "profile", None),
        match_mode=getattr(args, "name_match", "exact"),
    )

    # Remove the temporary handler
    temp_logger.removeHandler(handler)

    # Check if resolution failed
    if not data_views:
        print()
        print(ConsoleColors.error("ERROR: No valid data views found"), file=sys.stderr)
        print()
        print("Possible issues:", file=sys.stderr)
        print("  - Data view ID(s) or name(s) not found or you don't have access", file=sys.stderr)
        print("  - Data view name is not an EXACT match (names are case-sensitive)", file=sys.stderr)
        print("  - Configuration issue preventing data view lookup", file=sys.stderr)
        print()
        print("Tips for using Data View Names:", file=sys.stderr)
        print("  • Names must match EXACTLY: 'Production Analytics' ≠ 'production analytics'", file=sys.stderr)
        print('  • Use quotes around names: cja_auto_sdr "Production Analytics"', file=sys.stderr)
        print("  • IDs start with 'dv_': cja_auto_sdr dv_12345", file=sys.stderr)
        print()
        print("Try running: cja_auto_sdr --list-dataviews", file=sys.stderr)
        print("  to see all accessible data view IDs and names", file=sys.stderr)
        sys.exit(1)

    # Show resolution summary if names were used
    if name_to_ids_map and not args.quiet:
        print()
        print(ConsoleColors.success("Data view name resolution:"))
        for name, ids in name_to_ids_map.items():
            if len(ids) == 1:
                print(f"  ✓ '{name}' → {ids[0]}")
            else:
                print(f"  ✓ '{name}' → {len(ids)} matching data views:")
                for dv_id in ids:
                    print(f"      - {dv_id}")
        print()

    # Check for duplicate data view IDs and deduplicate
    original_count = len(data_views)
    seen = set()
    duplicates = []
    unique_data_views = []
    for dv in data_views:
        if dv in seen:
            duplicates.append(dv)
        else:
            seen.add(dv)
            unique_data_views.append(dv)

    if duplicates and not args.quiet:
        print(ConsoleColors.warning(f"Duplicate data view IDs removed: {set(duplicates)}"))
        print(f"  Processing {len(unique_data_views)} unique data view(s) instead of {original_count}")
        print()

    data_views = unique_data_views
    if run_state is not None:
        run_state["resolved_data_views"] = list(data_views)

    execution_context = _prepare_sdr_execution_context(
        args,
        data_views=data_views,
        show_processing_count=bool(names_provided),
        run_state=run_state,
    )
    effective_log_level = execution_context["effective_log_level"]
    quality_report_format = execution_context["quality_report_format"]
    quality_report_only = execution_context["quality_report_only"]
    sdr_format = execution_context["sdr_format"]
    processing_start_time = execution_context["processing_start_time"]
    api_tuning_config = execution_context["api_tuning_config"]
    circuit_breaker_config = execution_context["circuit_breaker_config"]
    inventory_order = execution_context["inventory_order"]

    successful_results: list[ProcessingResult] = []
    quality_report_results: list[ProcessingResult] = []
    processed_results: list[ProcessingResult] = []
    overall_failure = False
    processing_failures_detected = False
    execution_result = _execute_sdr_processing_modes(
        args,
        data_views=data_views,
        effective_log_level=effective_log_level,
        sdr_format=sdr_format,
        processing_start_time=processing_start_time,
        workers_auto=workers_auto,
        quality_report_only=quality_report_only,
        inventory_order=inventory_order,
        api_tuning_config=api_tuning_config,
        circuit_breaker_config=circuit_breaker_config,
    )
    successful_results = list(execution_result["successful_results"])
    quality_report_results = list(execution_result["quality_report_results"])
    processed_results = list(execution_result["processed_results"])
    overall_failure = bool(execution_result["overall_failure"])
    processing_failures_detected = bool(execution_result["processing_failures_detected"])

    all_quality_issues = aggregate_quality_issues(successful_results)
    if run_state is not None:
        run_state["processed_results"] = [*processed_results]
        run_state["quality_issues_count"] = len(all_quality_issues)

    if quality_report_only:
        summary_results = quality_report_results
    else:
        summary_results = processed_results
    if summary_results:
        append_github_step_summary(build_quality_step_summary(summary_results))

    if quality_report_only:
        try:
            report_target = write_quality_report_output(
                all_quality_issues,
                report_format=quality_report_format,
                output=getattr(args, "output", None),
                output_dir=args.output_dir,
            )
            if not args.quiet:
                if report_target == "stdout":
                    print(ConsoleColors.success("Quality report written to stdout"))
                else:
                    print(ConsoleColors.success(f"Quality report written to: {report_target}"))
        except (OSError, OutputError, KeyError, TypeError, ValueError) as e:
            print(ConsoleColors.error(f"ERROR: Failed to write quality report: {e!s}"), file=sys.stderr)
            overall_failure = True

    fail_on_quality = getattr(args, "fail_on_quality", None)
    quality_gate_failed = False
    if fail_on_quality and has_quality_issues_at_or_above(all_quality_issues, fail_on_quality):
        quality_gate_failed = True
        threshold_rank = QUALITY_SEVERITY_RANK[fail_on_quality]
        failing_counts = count_quality_issues_by_severity(
            [
                issue
                for issue in all_quality_issues
                if QUALITY_SEVERITY_RANK.get(str(issue.get("Severity", "")).upper(), 99) <= threshold_rank
            ],
        )
        if not args.quiet:
            print(
                ConsoleColors.error(f"QUALITY GATE FAILED: Found issues at or above {fail_on_quality} severity."),
                file=sys.stderr,
            )
            for severity in QUALITY_SEVERITY_ORDER:
                count = failing_counts.get(severity, 0)
                if count > 0:
                    print(f"  {severity}: {count}", file=sys.stderr)

    if run_state is not None:
        run_state["quality_gate_failed"] = quality_gate_failed

    if quality_gate_failed:
        # Exit code 1 has precedence when processing failed.
        if processing_failures_detected or overall_failure:
            sys.exit(1)
        sys.exit(2)

    if overall_failure:
        sys.exit(1)


def main():
    """Main entry point with optional run summary emission."""

    summary_start = datetime.now(UTC).isoformat()
    summary_start_perf = time.time()
    run_state: dict[str, Any] = {
        "mode": "unknown",
        "data_view_inputs": [],
        "resolved_data_views": [],
        "processed_results": [],
        "quality_issues_count": 0,
        "quality_gate_failed": False,
        "details": {},
        "run_summary_output": _cli_option_value("--run-summary-json"),
        "profile": None,
        "config_file": None,
        "output_format": None,
        "quality_policy": None,
        "allow_partial": _cli_option_specified("--allow-partial"),
    }
    exit_code = 0

    redirect_stdout_for_run_summary = run_state.get("run_summary_output") in ("-", "stdout")
    run_context = (
        contextlib.redirect_stdout(sys.stderr) if redirect_stdout_for_run_summary else contextlib.nullcontext()
    )

    try:
        with run_context:
            _main_impl(run_state=run_state)
    except KeyboardInterrupt:
        exit_code = 130
        raise
    except SystemExit as exc:
        exit_code = _normalize_exit_code(exc.code)
        raise
    except Exception:  # Intentional: last-resort handler in main()
        exit_code = 1
        raise
    finally:
        run_summary_output = run_state.get("run_summary_output")
        if run_summary_output:
            summary_payload = _build_run_summary_payload(
                run_state=run_state,
                exit_code=exit_code,
                summary_start=summary_start,
                summary_start_perf=summary_start_perf,
            )
            output_dir = run_state.get("output_dir") or "."
            try:
                write_run_summary_output(summary_payload, run_summary_output, output_dir=output_dir)
            except Exception as e:  # Intentional: finally-block guard; must not mask original exception
                print(
                    ConsoleColors.warning(f"Warning: Failed to write run summary to '{run_summary_output}': {e!s}"),
                    file=sys.stderr,
                )


if __name__ == "__main__":
    main()
