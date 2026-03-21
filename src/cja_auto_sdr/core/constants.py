"""Constants and default values for CJA Auto SDR.

This module centralizes all magic numbers, default configurations,
and schema definitions used throughout the application.
"""

import os
from typing import Any

from cja_auto_sdr.core.config import (
    CacheConfig,
    LogConfig,
    RetryConfig,
    WorkerConfig,
)

# ==================== FORMAT ALIASES ====================

# Shorthand format aliases for common output combinations
FORMAT_ALIASES: dict[str, list] = {
    "reports": ["excel", "markdown"],  # Documentation: Excel + Markdown
    "data": ["csv", "json"],  # Data pipelines: CSV + JSON
    "ci": ["json", "markdown"],  # CI/CD logs: JSON + Markdown
}

# File extension to format mapping for auto-detection
EXTENSION_TO_FORMAT: dict[str, str] = {
    ".xlsx": "excel",
    ".xls": "excel",
    ".csv": "csv",
    ".json": "json",
    ".html": "html",
    ".htm": "html",
    ".md": "markdown",
    ".markdown": "markdown",
}

# ==================== DISPLAY CONSTANTS ====================

# Width of banner separator lines (used across CLI output)
BANNER_WIDTH: int = 60

# Progress bar format for tqdm instances
TQDM_BAR_FORMAT: str = "{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}]"

# ==================== WORKER LIMITS ====================

# Worker thread/process limits
DEFAULT_API_FETCH_WORKERS: int = 3  # Concurrent API fetch threads
DEFAULT_VALIDATION_WORKERS: int = 2  # Concurrent validation threads
DEFAULT_BATCH_WORKERS: int = 4  # Default batch processing workers
MAX_BATCH_WORKERS: int = 256  # Maximum allowed batch workers
AUTO_WORKERS_SENTINEL: int = 0  # Sentinel value to trigger auto-detection
DEFAULT_ORG_REPORT_WORKERS: int = 10  # Max concurrent workers for org-wide data view fetches

# ==================== GOVERNANCE THRESHOLDS ====================

# Maximum overlap threshold for governance similarity checks
# Pairs >= 90% similarity are always flagged for governance, regardless of --overlap-threshold
GOVERNANCE_MAX_OVERLAP_THRESHOLD: float = 0.9

# ==================== CACHE DEFAULTS ====================

DEFAULT_CACHE_SIZE: int = 1000  # Maximum cached validation results
DEFAULT_CACHE_TTL: int = 3600  # Cache TTL in seconds (1 hour)

# ==================== LOGGING DEFAULTS ====================

LOG_FILE_MAX_BYTES: int = 10 * 1024 * 1024  # 10MB max per log file
LOG_FILE_BACKUP_COUNT: int = 5  # Number of backup log files to keep

# ==================== DEFAULT CONFIG INSTANCES ====================

# Default configuration instances (use these for consistent defaults)
DEFAULT_RETRY = RetryConfig()
DEFAULT_CACHE = CacheConfig()
DEFAULT_LOG = LogConfig()
DEFAULT_WORKERS = WorkerConfig()

# Default retry settings (dict format for backward compatibility)
# New code should use DEFAULT_RETRY (RetryConfig dataclass) instead
DEFAULT_RETRY_CONFIG: dict[str, Any] = DEFAULT_RETRY.to_dict()

# ==================== QUALITY / SEVERITY ====================

# Canonical severity ordering — used by CLI, validation, and quality-gate logic
QUALITY_SEVERITY_ORDER: tuple[str, ...] = ("CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO")
QUALITY_SEVERITY_RANK: dict[str, int] = {severity: index for index, severity in enumerate(QUALITY_SEVERITY_ORDER)}

# ==================== AUTO-PRUNE DEFAULTS ====================

DEFAULT_AUTO_PRUNE_KEEP_LAST: int = 20
DEFAULT_AUTO_PRUNE_KEEP_SINCE: str = "30d"

# ==================== VALIDATION SCHEMA ====================

# Centralized field definitions for data quality validation.
# Used by DataQualityChecker to identify:
#   - Missing required fields (CRITICAL severity)
#   - Null values in critical fields (MEDIUM severity)
# Modify these lists as the CJA API evolves or validation requirements change.
VALIDATION_SCHEMA: dict[str, list] = {
    "required_metric_fields": ["id", "name", "type"],
    "required_dimension_fields": ["id", "name", "type"],
    "critical_fields": ["id", "name", "title", "description"],
}

# ==================== RETRYABLE ERRORS ====================

# HTTP status codes that should trigger a retry
RETRYABLE_STATUS_CODES: set[int] = {408, 429, 500, 502, 503, 504}

# ==================== CONFIG SCHEMA ====================

# Schema for validating config.json files
CONFIG_SCHEMA: dict[str, dict[str, Any]] = {
    "base_required_fields": {
        "org_id": {"type": str, "description": "Adobe Organization ID"},
        "client_id": {"type": str, "description": "OAuth Client ID"},
        "secret": {"type": str, "description": "Client Secret"},
    },
    "optional_fields": {
        "scopes": {"type": str, "description": "OAuth scopes"},
        "sandbox": {"type": str, "description": "Sandbox name (optional)"},
    },
}

# Deprecated JWT fields that should be migrated
JWT_DEPRECATED_FIELDS: dict[str, str] = {
    "tech_acct": "Technical Account ID (JWT auth)",
    "private_key": "Private key file path (JWT auth)",
    "pathToKey": "Private key file path (JWT auth)",
}

# ==================== ENVIRONMENT VARIABLE MAPPING ====================

# Maps environment variable names to config.json field names
ENV_VAR_MAPPING: dict[str, str] = {
    "org_id": "ORG_ID",
    "client_id": "CLIENT_ID",
    "secret": "SECRET",
    "scopes": "SCOPES",
    "sandbox": "SANDBOX",
}


def auto_detect_workers(num_data_views: int = 1, total_components: int = 0) -> int:
    """
    Auto-detect optimal number of parallel workers based on system resources.

    Uses a heuristic based on:
    - CPU core count (primary factor)
    - Number of data views to process
    - Total component count (if known)

    Args:
        num_data_views: Number of data views to process
        total_components: Optional total metrics + dimensions count

    Returns:
        Recommended number of workers (1 to MAX_BATCH_WORKERS)
    """
    # Get CPU count, default to 4 if detection fails
    try:
        cpu_count = os.cpu_count() or 4
    except Exception:  # Intentional: CPU detection can fail on exotic platforms; safe fallback to 4 cores
        cpu_count = 4

    # Base workers on CPU count (leave some headroom for system)
    base_workers = max(2, cpu_count - 1)

    # For small jobs (1-2 data views), don't over-parallelize
    if num_data_views <= 2:
        workers = min(base_workers, num_data_views * 2)
    else:
        # Scale with data view count but cap at CPU-based limit
        workers = min(base_workers, num_data_views)

    # If we know component count, adjust based on complexity
    # More components = more memory per worker, so use fewer workers
    if total_components > 0:
        # Large data views (>5000 components) - reduce workers to manage memory
        if total_components > 10000:
            workers = max(1, workers // 3)
        # Large data views (>5000 components) - reduce workers to manage memory
        elif total_components > 5000:
            workers = max(2, workers // 2)

    # Ensure within bounds
    return max(1, min(workers, MAX_BATCH_WORKERS))


def infer_format_from_path(output_path: str) -> str | None:
    """
    Infer output format from file extension.

    Args:
        output_path: The output file path

    Returns:
        Format string if recognized extension, None otherwise
    """
    import os as _os

    if not output_path or output_path in ("-", "stdout"):
        return None
    ext = _os.path.splitext(output_path)[1].lower()
    return EXTENSION_TO_FORMAT.get(ext)


def should_generate_format(output_format: str, target_format: str) -> bool:
    """
    Check if a specific format should be generated based on the output_format setting.

    Args:
        output_format: The format requested by user (e.g., 'all', 'reports', 'excel')
        target_format: The specific format to check (e.g., 'excel', 'json')

    Returns:
        True if target_format should be generated
    """
    if output_format == target_format:
        return True
    if output_format == "all":
        return target_format in ["excel", "csv", "json", "html", "markdown", "console"]
    if output_format in FORMAT_ALIASES:
        return target_format in FORMAT_ALIASES[output_format]
    return False


def _get_credential_fields() -> dict[str, set]:
    """
    Get all credential field names from the config schema.

    Returns:
        Dict with 'required' and 'optional' sets of field names
    """
    required = set(CONFIG_SCHEMA["base_required_fields"].keys())
    optional = set(CONFIG_SCHEMA["optional_fields"].keys())
    return {
        "required": required,
        "optional": optional,
        "all": required | optional,
    }


# Pre-computed credential fields for faster access
CREDENTIAL_FIELDS: dict[str, set] = _get_credential_fields()
