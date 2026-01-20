import cjapy
import pandas as pd
import json
import re
from datetime import datetime
import hashlib
import logging
from logging.handlers import RotatingFileHandler
import sys
from typing import (
    Dict, List, Tuple, Optional, Callable, Any, Union,
    TypeVar, Protocol, runtime_checkable
)
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from tqdm import tqdm
import time
import threading
import argparse
import os
import random
import functools
from dataclasses import dataclass, field
import tempfile
import atexit
import uuid
import textwrap
import webbrowser
import platform
import subprocess

# Attempt to load python-dotenv if available (optional dependency)
_DOTENV_AVAILABLE = False
_DOTENV_LOADED = False
try:
    from dotenv import load_dotenv
    _DOTENV_LOADED = load_dotenv()  # Returns True if .env file was found and loaded
    _DOTENV_AVAILABLE = True
except ImportError:
    pass  # python-dotenv not installed

# Attempt to load argcomplete for shell tab-completion (optional dependency)
_ARGCOMPLETE_AVAILABLE = False
try:
    import argcomplete
    _ARGCOMPLETE_AVAILABLE = True
except ImportError:
    pass  # argcomplete not installed

# ==================== VERSION ====================

__version__ = "3.0.11"

# ==================== CUSTOM EXCEPTIONS ====================


class CJASDRError(Exception):
    """Base exception for all CJA SDR errors."""

    def __init__(self, message: str, details: Optional[str] = None):
        self.message = message
        self.details = details
        super().__init__(self.message)

    def __str__(self) -> str:
        if self.details:
            return f"{self.message}: {self.details}"
        return self.message


class ConfigurationError(CJASDRError):
    """Exception raised for configuration-related errors.

    Examples:
        - Missing config file
        - Invalid JSON in config file
        - Missing required credentials
        - Invalid credential format
    """

    def __init__(self, message: str, config_file: Optional[str] = None,
                 field: Optional[str] = None, details: Optional[str] = None):
        self.config_file = config_file
        self.field = field
        super().__init__(message, details)


class APIError(CJASDRError):
    """Exception raised for API communication failures.

    Wraps HTTP errors and network failures with context about
    the operation that failed.
    """

    def __init__(self, message: str, status_code: Optional[int] = None,
                 operation: Optional[str] = None, details: Optional[str] = None,
                 original_error: Optional[Exception] = None):
        self.status_code = status_code
        self.operation = operation
        self.original_error = original_error
        super().__init__(message, details)

    def __str__(self) -> str:
        parts = [self.message]
        if self.status_code:
            parts.append(f"HTTP {self.status_code}")
        if self.operation:
            parts.append(f"during {self.operation}")
        if self.details:
            parts.append(self.details)
        return " - ".join(parts)


class ValidationError(CJASDRError):
    """Exception raised for data quality validation failures.

    Used when validation encounters critical issues that prevent
    further processing.
    """

    def __init__(self, message: str, item_type: Optional[str] = None,
                 issue_count: int = 0, details: Optional[str] = None):
        self.item_type = item_type
        self.issue_count = issue_count
        super().__init__(message, details)


class OutputError(CJASDRError):
    """Exception raised for file writing failures.

    Examples:
        - Permission denied
        - Disk full
        - Invalid path
        - Serialization error
    """

    def __init__(self, message: str, output_path: Optional[str] = None,
                 output_format: Optional[str] = None, details: Optional[str] = None,
                 original_error: Optional[Exception] = None):
        self.output_path = output_path
        self.output_format = output_format
        self.original_error = original_error
        super().__init__(message, details)


# ==================== CONFIGURATION DATACLASSES ====================


@dataclass
class RetryConfig:
    """Configuration for retry logic with exponential backoff.

    Attributes:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay cap in seconds (default: 30.0)
        exponential_base: Multiplier for exponential backoff (default: 2)
        jitter: Add randomization to delays (default: True)
    """
    max_retries: int = 3
    base_delay: float = 1.0
    max_delay: float = 30.0
    exponential_base: int = 2
    jitter: bool = True

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for backward compatibility."""
        return {
            'max_retries': self.max_retries,
            'base_delay': self.base_delay,
            'max_delay': self.max_delay,
            'exponential_base': self.exponential_base,
            'jitter': self.jitter,
        }


@dataclass
class CacheConfig:
    """Configuration for validation result caching.

    Attributes:
        enabled: Whether caching is enabled (default: False)
        max_size: Maximum number of cached entries (default: 1000)
        ttl_seconds: Time-to-live in seconds (default: 3600 = 1 hour)
    """
    enabled: bool = False
    max_size: int = 1000
    ttl_seconds: int = 3600


@dataclass
class LogConfig:
    """Configuration for logging behavior.

    Attributes:
        level: Logging level string (default: "INFO")
        file_max_bytes: Maximum size per log file (default: 10MB)
        file_backup_count: Number of backup log files (default: 5)
    """
    level: str = "INFO"
    file_max_bytes: int = 10 * 1024 * 1024  # 10MB
    file_backup_count: int = 5


@dataclass
class WorkerConfig:
    """Configuration for parallel processing workers.

    Attributes:
        api_fetch_workers: Concurrent API fetch threads (default: 3)
        validation_workers: Concurrent validation threads (default: 2)
        batch_workers: Batch processing workers (default: 4)
        max_batch_workers: Maximum allowed batch workers (default: 256)
    """
    api_fetch_workers: int = 3
    validation_workers: int = 2
    batch_workers: int = 4
    max_batch_workers: int = 256


@dataclass
class SDRConfig:
    """Master configuration for SDR generation.

    Centralizes all configuration options in a single, testable dataclass.

    Attributes:
        retry: Retry configuration
        cache: Cache configuration
        log: Logging configuration
        workers: Worker configuration
        output_format: Output format (excel, csv, json, html, markdown, all)
        output_dir: Output directory path
        skip_validation: Skip data quality validation
        max_issues: Maximum issues to report (0 = all)
        quiet: Suppress non-error output
    """
    retry: RetryConfig = field(default_factory=RetryConfig)
    cache: CacheConfig = field(default_factory=CacheConfig)
    log: LogConfig = field(default_factory=LogConfig)
    workers: WorkerConfig = field(default_factory=WorkerConfig)
    output_format: str = "excel"
    output_dir: str = "."
    skip_validation: bool = False
    max_issues: int = 0
    quiet: bool = False

    @classmethod
    def from_args(cls, args: argparse.Namespace) -> 'SDRConfig':
        """Create configuration from parsed command-line arguments."""
        return cls(
            retry=RetryConfig(
                max_retries=getattr(args, 'max_retries', 3),
                base_delay=getattr(args, 'retry_base_delay', 1.0),
                max_delay=getattr(args, 'retry_max_delay', 30.0),
            ),
            cache=CacheConfig(
                enabled=getattr(args, 'enable_cache', False),
                max_size=getattr(args, 'cache_size', 1000),
                ttl_seconds=getattr(args, 'cache_ttl', 3600),
            ),
            log=LogConfig(
                level=getattr(args, 'log_level', 'INFO'),
            ),
            workers=WorkerConfig(
                batch_workers=getattr(args, 'workers', 4),
            ),
            output_format=getattr(args, 'format', 'excel'),
            output_dir=getattr(args, 'output_dir', '.'),
            skip_validation=getattr(args, 'skip_validation', False),
            max_issues=getattr(args, 'max_issues', 0),
            quiet=getattr(args, 'quiet', False),
        )


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
                quality_results: Optional[List[Dict]] = None
            ) -> str:
                # Write CSV files and return output path
                ...
    """

    def write(
        self,
        metrics_df: pd.DataFrame,
        dimensions_df: pd.DataFrame,
        dataview_info: Dict[str, Any],
        output_path: Path,
        quality_results: Optional[List[Dict[str, Any]]] = None
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
ValidationIssue = Dict[str, Any]

# Type variable for generic return types
T = TypeVar('T')


# ==================== DEFAULT CONSTANTS ====================
# Note: These module-level constants are maintained for backward compatibility.
# New code should use the corresponding dataclass configurations (SDRConfig,
# RetryConfig, CacheConfig, LogConfig, WorkerConfig) for better type safety.

# Worker thread/process limits
DEFAULT_API_FETCH_WORKERS: int = 3      # Concurrent API fetch threads
DEFAULT_VALIDATION_WORKERS: int = 2     # Concurrent validation threads
DEFAULT_BATCH_WORKERS: int = 4          # Default batch processing workers
MAX_BATCH_WORKERS: int = 256            # Maximum allowed batch workers

# Cache defaults
DEFAULT_CACHE_SIZE: int = 1000          # Maximum cached validation results
DEFAULT_CACHE_TTL: int = 3600           # Cache TTL in seconds (1 hour)

# Logging defaults
LOG_FILE_MAX_BYTES: int = 10 * 1024 * 1024  # 10MB max per log file
LOG_FILE_BACKUP_COUNT: int = 5              # Number of backup log files to keep

# Default configuration instances (use these for consistent defaults)
DEFAULT_RETRY = RetryConfig()
DEFAULT_CACHE = CacheConfig()
DEFAULT_LOG = LogConfig()
DEFAULT_WORKERS = WorkerConfig()

# ==================== VALIDATION SCHEMA ====================

# Centralized field definitions for data quality validation.
# Used by DataQualityChecker to identify:
#   - Missing required fields (CRITICAL severity)
#   - Null values in critical fields (MEDIUM severity)
# Modify these lists as the CJA API evolves or validation requirements change.
VALIDATION_SCHEMA = {
    'required_metric_fields': ['id', 'name', 'type'],
    'required_dimension_fields': ['id', 'name', 'type'],
    'critical_fields': ['id', 'name', 'title', 'description'],
}

# ==================== ERROR FORMATTING ====================

def _format_error_msg(operation: str, item_type: str = None, error: Exception = None) -> str:
    """
    Format error messages consistently across the application.

    Args:
        operation: Description of the operation that failed (e.g., "checking duplicates")
        item_type: Optional item type context (e.g., "Metrics", "Dimensions")
        error: Optional exception to include in the message

    Returns:
        Formatted error message string
    """
    msg = f"Error {operation}"
    if item_type:
        msg += f" for {item_type}"
    if error:
        msg += f": {str(error)}"
    return msg


def format_file_size(size_bytes: int) -> str:
    """
    Format file size in human-readable format.

    Args:
        size_bytes: Size in bytes

    Returns:
        Human-readable string (e.g., "1.5 MB", "256 KB", "42 B")
    """
    size = size_bytes
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != 'B' else f"{size} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def open_file_in_default_app(file_path: Union[str, Path]) -> bool:
    """
    Open a file in the default application for its type.

    Works cross-platform (macOS, Linux, Windows).

    Args:
        file_path: Path to the file to open

    Returns:
        True if successful, False otherwise
    """
    file_path = str(file_path)
    try:
        system = platform.system()
        if system == 'Darwin':  # macOS
            subprocess.run(['open', file_path], check=True)
        elif system == 'Windows':
            os.startfile(file_path)  # type: ignore[attr-defined]
        else:  # Linux and others
            subprocess.run(['xdg-open', file_path], check=True)
        return True
    except Exception:
        # Fallback to webbrowser for HTML files
        if file_path.endswith('.html'):
            try:
                webbrowser.open(f'file://{os.path.abspath(file_path)}')
                return True
            except Exception:
                pass
        return False


# ==================== CONSOLE COLORS ====================

class ConsoleColors:
    """ANSI color codes for terminal output"""
    # Colors
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

    # Disable colors if not a TTY or on Windows without ANSI support
    _enabled = sys.stdout.isatty() and (os.name != 'nt' or os.environ.get('TERM'))

    @classmethod
    def success(cls, text: str) -> str:
        """Format text as success (green)"""
        if cls._enabled:
            return f"{cls.GREEN}{text}{cls.RESET}"
        return text

    @classmethod
    def error(cls, text: str) -> str:
        """Format text as error (red)"""
        if cls._enabled:
            return f"{cls.RED}{text}{cls.RESET}"
        return text

    @classmethod
    def warning(cls, text: str) -> str:
        """Format text as warning (yellow)"""
        if cls._enabled:
            return f"{cls.YELLOW}{text}{cls.RESET}"
        return text

    @classmethod
    def info(cls, text: str) -> str:
        """Format text as info (cyan)"""
        if cls._enabled:
            return f"{cls.CYAN}{text}{cls.RESET}"
        return text

    @classmethod
    def bold(cls, text: str) -> str:
        """Format text as bold"""
        if cls._enabled:
            return f"{cls.BOLD}{text}{cls.RESET}"
        return text

    @classmethod
    def status(cls, success: bool, text: str) -> str:
        """Format text based on success/failure status"""
        return cls.success(text) if success else cls.error(text)

# ==================== RETRY CONFIGURATION ====================

# Default retry settings (dict format for backward compatibility)
# New code should use DEFAULT_RETRY (RetryConfig dataclass) instead
DEFAULT_RETRY_CONFIG: Dict[str, Any] = DEFAULT_RETRY.to_dict()

# ==================== ENHANCED ERROR MESSAGES ====================

class ErrorMessageHelper:
    """Provides contextual error messages with actionable suggestions"""

    # Documentation links
    DOCS_BASE = "https://github.com/your-org/cja_auto_sdr/blob/main/docs"
    TROUBLESHOOTING_URL = f"{DOCS_BASE}/TROUBLESHOOTING.md"
    QUICKSTART_URL = f"{DOCS_BASE}/QUICKSTART_GUIDE.md"

    @staticmethod
    def get_http_error_message(status_code: int, operation: str = "API call") -> str:
        """Get detailed error message with suggestions for HTTP status codes"""
        messages = {
            400: {
                "title": "Bad Request",
                "reason": "The request was malformed or contains invalid parameters",
                "suggestions": [
                    "Verify the data view ID format (should start with 'dv_')",
                    "Check that all required parameters are provided",
                    "Review the API request structure",
                ]
            },
            401: {
                "title": "Authentication Failed",
                "reason": "Your credentials are invalid or have expired",
                "suggestions": [
                    "Verify CLIENT_ID and SECRET in config.json or environment variables",
                    "Check that your ORG_ID ends with '@AdobeOrg'",
                    "Ensure SCOPES includes: 'openid, AdobeID, additional_info.projectedProductContext'",
                    "Regenerate credentials at https://developer.adobe.com/console/",
                    f"See authentication setup: {ErrorMessageHelper.QUICKSTART_URL}#configure-credentials",
                ]
            },
            403: {
                "title": "Access Forbidden",
                "reason": "You don't have permission to access this resource",
                "suggestions": [
                    "Verify your Adobe I/O project has CJA API access enabled",
                    "Check that your user account has permission to access this data view",
                    "Confirm the data view ID is correct (run --list-dataviews)",
                    "Contact your Adobe administrator to grant CJA API permissions",
                ]
            },
            404: {
                "title": "Resource Not Found",
                "reason": "The requested data view or resource does not exist",
                "suggestions": [
                    "Verify the data view ID is correct (double-check for typos)",
                    "Run 'cja_auto_sdr --list-dataviews' to see available data views",
                    "The data view may have been deleted or renamed",
                    "Check that you're connected to the correct Adobe organization",
                ]
            },
            429: {
                "title": "Rate Limit Exceeded",
                "reason": "Too many requests sent to the API",
                "suggestions": [
                    "Wait a few minutes before retrying",
                    "Reduce the number of parallel workers (--workers 2)",
                    "Use --max-retries with longer delays (--retry-max-delay 60)",
                    "Process data views in smaller batches",
                    "Enable caching to reduce API calls (--enable-cache)",
                ]
            },
            500: {
                "title": "Internal Server Error",
                "reason": "Adobe's API service encountered an error",
                "suggestions": [
                    "This is typically a temporary issue - retry in a few minutes",
                    "Increase retry attempts (--max-retries 5)",
                    "Check Adobe Status page for known issues",
                    "If persistent, contact Adobe Support with your request details",
                ]
            },
            502: {
                "title": "Bad Gateway",
                "reason": "Upstream server error or network issue",
                "suggestions": [
                    "This is typically a temporary network issue",
                    "Wait a few minutes and retry",
                    "Increase retry attempts (--max-retries 5)",
                ]
            },
            503: {
                "title": "Service Unavailable",
                "reason": "Adobe's API service is temporarily unavailable",
                "suggestions": [
                    "The service may be undergoing maintenance",
                    "Wait 5-10 minutes and retry",
                    "Check Adobe Status page: https://status.adobe.com/",
                    "Use --max-retries 5 to automatically retry",
                ]
            },
            504: {
                "title": "Gateway Timeout",
                "reason": "The request took too long to complete",
                "suggestions": [
                    "The data view may be very large - this is normal",
                    "Increase timeout with --retry-max-delay 60",
                    "Try processing during off-peak hours",
                    "Consider using --skip-validation to reduce processing time",
                ]
            },
        }

        error_info = messages.get(status_code, {
            "title": f"HTTP {status_code}",
            "reason": "An unexpected HTTP error occurred",
            "suggestions": [
                "Check your network connection",
                "Verify API credentials are correct",
                "Review logs for more details",
                f"See troubleshooting guide: {ErrorMessageHelper.TROUBLESHOOTING_URL}",
            ]
        })

        output = [
            f"{'='*60}",
            f"HTTP {status_code}: {error_info['title']}",
            f"{'='*60}",
            f"Operation: {operation}",
            "",
            "Why this happened:",
            f"  {error_info['reason']}",
            "",
            "How to fix it:",
        ]

        for i, suggestion in enumerate(error_info['suggestions'], 1):
            output.append(f"  {i}. {suggestion}")

        output.append("")
        output.append(f"For more help: {ErrorMessageHelper.TROUBLESHOOTING_URL}")

        return "\n".join(output)

    @staticmethod
    def get_network_error_message(error: Exception, operation: str = "operation") -> str:
        """Get detailed message for network-related errors"""
        error_type = type(error).__name__

        messages = {
            "ConnectionError": {
                "reason": "Cannot establish connection to Adobe API servers",
                "suggestions": [
                    "Check your internet connection",
                    "Verify you can reach adobe.io in your browser",
                    "Check if you're behind a corporate firewall or proxy",
                    "Temporarily disable VPN if you're using one",
                    "Verify DNS is working (try: ping adobe.io)",
                ]
            },
            "TimeoutError": {
                "reason": "The request took too long and timed out",
                "suggestions": [
                    "Your network connection may be slow or unstable",
                    "The data view may be very large (this is normal for large views)",
                    "Increase timeout with --retry-max-delay 60",
                    "Try processing during off-peak hours",
                    "Use --max-retries 5 to automatically retry",
                ]
            },
            "SSLError": {
                "reason": "SSL/TLS certificate verification failed",
                "suggestions": [
                    "Your system's SSL certificates may be outdated",
                    "Update certificates: pip install --upgrade certifi",
                    "Check system date/time is correct (SSL certs are time-sensitive)",
                    "Corporate firewalls may be interfering with SSL",
                ]
            },
            "ConnectionResetError": {
                "reason": "Connection was reset by the remote server",
                "suggestions": [
                    "This is usually a temporary network issue",
                    "Wait a moment and retry",
                    "Use --max-retries 5 to automatically handle this",
                ]
            },
        }

        error_info = messages.get(error_type, {
            "reason": "A network error occurred",
            "suggestions": [
                "Check your internet connection",
                "Verify network stability",
                "Try again in a few moments",
                f"See troubleshooting guide: {ErrorMessageHelper.TROUBLESHOOTING_URL}#network-errors",
            ]
        })

        output = [
            f"{'='*60}",
            f"Network Error: {error_type}",
            f"{'='*60}",
            f"During: {operation}",
            f"Error details: {str(error)}",
            "",
            "Why this happened:",
            f"  {error_info['reason']}",
            "",
            "How to fix it:",
        ]

        for i, suggestion in enumerate(error_info['suggestions'], 1):
            output.append(f"  {i}. {suggestion}")

        output.append("")
        output.append(f"For more help: {ErrorMessageHelper.TROUBLESHOOTING_URL}#network-errors")

        return "\n".join(output)

    @staticmethod
    def get_config_error_message(error_type: str, details: str = "") -> str:
        """Get detailed message for configuration errors"""
        messages = {
            "file_not_found": {
                "title": "Configuration File Not Found",
                "reason": "The config.json file does not exist",
                "suggestions": [
                    "Create a configuration file:",
                    "  Option 1: cja_auto_sdr --sample-config",
                    "  Option 2: cp .config.json.example config.json",
                    "",
                    "Or use environment variables instead:",
                    "  export ORG_ID='your_org_id@AdobeOrg'",
                    "  export CLIENT_ID='your_client_id'",
                    "  export SECRET='your_client_secret'",
                    "  export SCOPES='openid, AdobeID, additional_info.projectedProductContext'",
                    "",
                    f"See setup guide: {ErrorMessageHelper.QUICKSTART_URL}",
                ]
            },
            "invalid_json": {
                "title": "Invalid JSON in Configuration File",
                "reason": "The configuration file contains invalid JSON syntax",
                "suggestions": [
                    "Common JSON errors:",
                    "  - Missing quotes around strings",
                    "  - Trailing commas (not allowed in JSON)",
                    "  - Missing closing braces or brackets",
                    "  - Comments (not allowed in standard JSON)",
                    "",
                    "Validate your JSON:",
                    "  - Use a JSON validator: https://jsonlint.com/",
                    "  - Or check with: python -m json.tool config.json",
                    "",
                    "Generate a fresh template:",
                    "  cja_auto_sdr --sample-config",
                ]
            },
            "missing_credentials": {
                "title": "Missing Required Credentials",
                "reason": "One or more required credential fields are missing",
                "suggestions": [
                    "Required fields in config.json:",
                    "  - org_id: Your Adobe Organization ID (ends with @AdobeOrg)",
                    "  - client_id: OAuth Client ID from Adobe Developer Console",
                    "  - secret: Client Secret from Adobe Developer Console",
                    "  - scopes: API scopes (use provided default)",
                    "",
                    "Get credentials from:",
                    "  https://developer.adobe.com/console/",
                    "",
                    f"See detailed setup: {ErrorMessageHelper.QUICKSTART_URL}#configure-credentials",
                ]
            },
            "invalid_format": {
                "title": "Invalid Credential Format",
                "reason": "One or more credentials have an invalid format",
                "suggestions": [
                    "Check credential formats:",
                    "  - org_id must end with '@AdobeOrg'",
                    "  - client_id should be a long alphanumeric string",
                    "  - secret should be a long alphanumeric string",
                    "  - scopes should include: 'openid, AdobeID, additional_info.projectedProductContext'",
                    "",
                    "Verify you copied credentials correctly (no extra spaces or line breaks)",
                    "Try regenerating credentials in Adobe Developer Console",
                ]
            },
        }

        error_info = messages.get(error_type, {
            "title": "Configuration Error",
            "reason": details or "A configuration error occurred",
            "suggestions": [
                "Run validation to check your config:",
                "  cja_auto_sdr --validate-config",
                "",
                f"See troubleshooting: {ErrorMessageHelper.TROUBLESHOOTING_URL}#configuration-errors",
            ]
        })

        output = [
            f"{'='*60}",
            f"{error_info['title']}",
            f"{'='*60}",
        ]

        if details:
            output.extend(["", f"Details: {details}", ""])

        output.extend([
            "Why this happened:",
            f"  {error_info['reason']}",
            "",
            "How to fix it:",
        ])

        for suggestion in error_info['suggestions']:
            if suggestion.startswith("  "):
                output.append(suggestion)
            else:
                output.append(f"  {suggestion}")

        return "\n".join(output)

    @staticmethod
    def get_data_view_error_message(data_view_id: str, available_count: int = None) -> str:
        """Get detailed message for data view not found errors"""
        # Determine if the identifier looks like an ID or a name
        is_id = data_view_id.startswith('dv_')

        output = [
            f"{'='*60}",
            "Data View Not Found",
            f"{'='*60}",
            f"Requested Data View: {data_view_id}",
            "",
            "Why this happened:",
            "  The data view does not exist or you don't have access to it",
            "",
            "How to fix it:",
        ]

        if is_id:
            output.extend([
                "  1. Check for typos in the data view ID",
                "  2. Verify you have access to this data view in CJA",
                "  3. List available data views to confirm the ID:",
                "       cja_auto_sdr --list-dataviews",
            ])
        else:
            output.extend([
                "  1. Check for typos in the data view name",
                "  2. Verify the name is an EXACT match (case-sensitive):",
                "       'Production Analytics' ≠ 'production analytics'",
                "       'Production Analytics' ≠ 'Production'",
                "  3. List available data views to confirm the exact name:",
                "       cja_auto_sdr --list-dataviews",
                "  4. Use quotes around names with spaces:",
                "       cja_auto_sdr \"Production Analytics\"",
            ])

        if available_count is not None:
            next_num = 4 if is_id else 5
            output.append(f"  {next_num}. You have access to {available_count} data view(s)")
            if available_count == 0:
                output.extend([
                    "",
                    "No data views found. This usually means:",
                    "  - Your API credentials don't have CJA access",
                    "  - You're connected to the wrong Adobe organization",
                    "  - No data views exist in this organization",
                ])

        output.extend([
            "",
            f"For more help: {ErrorMessageHelper.TROUBLESHOOTING_URL}#data-view-errors",
        ])

        return "\n".join(output)


# Custom exception for retryable HTTP status codes
class RetryableHTTPError(Exception):
    """Exception raised when API returns a retryable HTTP status code."""
    def __init__(self, status_code: int, message: str = ""):
        self.status_code = status_code
        super().__init__(f"HTTP {status_code}: {message}" if message else f"HTTP {status_code}")


# Exceptions that should trigger a retry (transient errors)
RETRYABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    OSError,  # Includes network-related errors
    RetryableHTTPError,  # Custom exception for HTTP status codes
)

# HTTP status codes that should trigger a retry
RETRYABLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


def retry_with_backoff(
    max_retries: Optional[int] = None,
    base_delay: Optional[float] = None,
    max_delay: Optional[float] = None,
    exponential_base: Optional[int] = None,
    jitter: Optional[bool] = None,
    retryable_exceptions: Optional[Tuple[type, ...]] = None,
    logger: Optional[logging.Logger] = None
) -> Callable[[Callable[..., T]], Callable[..., T]]:
    """
    Decorator that implements retry logic with exponential backoff.

    Automatically retries failed API calls with increasing delays between attempts.
    Includes jitter to prevent thundering herd problems when multiple processes retry.

    Args:
        max_retries: Maximum number of retry attempts (default: 3)
        base_delay: Initial delay in seconds (default: 1.0)
        max_delay: Maximum delay cap in seconds (default: 30.0)
        exponential_base: Multiplier for exponential backoff (default: 2)
        jitter: Add randomization to delays (default: True)
        retryable_exceptions: Tuple of exception types to retry (default: network errors)
        logger: Logger instance for retry messages

    Returns:
        Decorated function with retry capability

    Example:
        @retry_with_backoff(max_retries=3, base_delay=1.0)
        def fetch_data():
            return api.get_data()

    Backoff Formula:
        delay = min(base_delay * (exponential_base ** attempt), max_delay)
        if jitter: delay = delay * random.uniform(0.5, 1.5)
    """
    # Use defaults if not specified
    _max_retries = max_retries if max_retries is not None else DEFAULT_RETRY_CONFIG['max_retries']
    _base_delay = base_delay if base_delay is not None else DEFAULT_RETRY_CONFIG['base_delay']
    _max_delay = max_delay if max_delay is not None else DEFAULT_RETRY_CONFIG['max_delay']
    _exponential_base = exponential_base if exponential_base is not None else DEFAULT_RETRY_CONFIG['exponential_base']
    _jitter = jitter if jitter is not None else DEFAULT_RETRY_CONFIG['jitter']
    _retryable_exceptions = retryable_exceptions if retryable_exceptions is not None else RETRYABLE_EXCEPTIONS

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Any:
            _logger = logger or logging.getLogger(__name__)
            last_exception = None

            for attempt in range(_max_retries + 1):  # +1 for initial attempt
                try:
                    result = func(*args, **kwargs)
                    # Log success after retry
                    if attempt > 0:
                        _logger.info(
                            f"✓ {func.__name__} succeeded on attempt {attempt + 1}/{_max_retries + 1}"
                        )
                    return result
                except _retryable_exceptions as e:
                    last_exception = e

                    if attempt == _max_retries:
                        _logger.error(f"All {_max_retries + 1} attempts failed for {func.__name__}")

                        # Provide enhanced error message based on exception type
                        if isinstance(e, RetryableHTTPError):
                            error_msg = ErrorMessageHelper.get_http_error_message(
                                e.status_code,
                                operation=func.__name__
                            )
                            _logger.error("\n" + error_msg)
                        elif isinstance(e, (ConnectionError, TimeoutError, OSError)):
                            error_msg = ErrorMessageHelper.get_network_error_message(
                                e,
                                operation=func.__name__
                            )
                            _logger.error("\n" + error_msg)
                        else:
                            _logger.error(f"Error: {str(e)}")
                            _logger.error("Troubleshooting: Check network connectivity, verify API credentials, or try again later")
                        raise

                    # Calculate delay with exponential backoff
                    delay = min(_base_delay * (_exponential_base ** attempt), _max_delay)

                    # Add jitter to prevent thundering herd
                    if _jitter:
                        delay = delay * random.uniform(0.5, 1.5)

                    _logger.warning(
                        f"⚠ {func.__name__} attempt {attempt + 1}/{_max_retries + 1} failed: {str(e)}. "
                        f"Retrying in {delay:.1f}s..."
                    )
                    time.sleep(delay)
                except Exception as e:
                    # Non-retryable exception, raise immediately
                    _logger.error(f"{func.__name__} failed with non-retryable error: {str(e)}")
                    raise

            # Should not reach here, but just in case
            if last_exception:
                raise last_exception

        return wrapper
    return decorator


def make_api_call_with_retry(
    api_func: Callable[..., T],
    *args: Any,
    logger: Optional[logging.Logger] = None,
    operation_name: str = "API call",
    **kwargs: Any
) -> T:
    """
    Execute an API call with retry logic.

    This is a function-based alternative to the decorator for cases where
    you need more control or are calling methods on objects.

    Args:
        api_func: The API function to call
        *args: Positional arguments to pass to the function
        logger: Logger instance for retry messages
        operation_name: Human-readable name for logging
        **kwargs: Keyword arguments to pass to the function

    Returns:
        Result from the API call

    Raises:
        The last exception if all retries fail

    Example:
        result = make_api_call_with_retry(
            cja.getMetrics,
            data_view_id,
            logger=logger,
            operation_name="getMetrics"
        )
    """
    _logger = logger or logging.getLogger(__name__)
    max_retries = DEFAULT_RETRY_CONFIG['max_retries']
    base_delay = DEFAULT_RETRY_CONFIG['base_delay']
    max_delay = DEFAULT_RETRY_CONFIG['max_delay']
    exponential_base = DEFAULT_RETRY_CONFIG['exponential_base']
    jitter = DEFAULT_RETRY_CONFIG['jitter']

    last_exception = None

    for attempt in range(max_retries + 1):
        try:
            result = api_func(*args, **kwargs)

            # Check for HTTP status code in response (if exposed by the library)
            status_code = None
            if hasattr(result, 'status_code'):
                status_code = result.status_code
            elif isinstance(result, dict) and 'status_code' in result:
                status_code = result['status_code']
            elif isinstance(result, dict) and 'error' in result and isinstance(result['error'], dict):
                status_code = result['error'].get('status_code')

            if status_code is not None and status_code in RETRYABLE_STATUS_CODES:
                raise RetryableHTTPError(status_code, f"Retryable status from {operation_name}")

            # Log success after retry
            if attempt > 0:
                _logger.info(
                    f"✓ {operation_name} succeeded on attempt {attempt + 1}/{max_retries + 1}"
                )

            return result
        except RETRYABLE_EXCEPTIONS as e:
            last_exception = e

            if attempt == max_retries:
                _logger.error(f"All {max_retries + 1} attempts failed for {operation_name}")

                # Provide enhanced error message based on exception type
                if isinstance(e, RetryableHTTPError):
                    error_msg = ErrorMessageHelper.get_http_error_message(
                        e.status_code,
                        operation=operation_name
                    )
                    _logger.error("\n" + error_msg)
                elif isinstance(e, (ConnectionError, TimeoutError, OSError)):
                    error_msg = ErrorMessageHelper.get_network_error_message(
                        e,
                        operation=operation_name
                    )
                    _logger.error("\n" + error_msg)
                else:
                    _logger.error(f"Error: {str(e)}")
                    _logger.error("Troubleshooting: Check network connectivity, verify API credentials, or try again later")
                raise

            delay = min(base_delay * (exponential_base ** attempt), max_delay)
            if jitter:
                delay = delay * random.uniform(0.5, 1.5)

            _logger.warning(
                f"⚠ {operation_name} attempt {attempt + 1}/{max_retries + 1} failed: {str(e)}. "
                f"Retrying in {delay:.1f}s..."
            )
            time.sleep(delay)
        except Exception as e:
            # Non-retryable exception
            _logger.error(f"{operation_name} failed with non-retryable error: {str(e)}")
            raise

    if last_exception:
        raise last_exception


# ==================== DATA STRUCTURES ====================

@dataclass
class ProcessingResult:
    """Result of processing a single data view"""
    data_view_id: str
    data_view_name: str
    success: bool
    duration: float
    metrics_count: int = 0
    dimensions_count: int = 0
    dq_issues_count: int = 0
    output_file: str = ""
    error_message: str = ""
    file_size_bytes: int = 0

    @property
    def file_size_formatted(self) -> str:
        """Return human-readable file size (e.g., '1.5 MB', '256 KB')."""
        return format_file_size(self.file_size_bytes)


# ==================== DIFF COMPARISON DATA STRUCTURES ====================

from enum import Enum


class ChangeType(Enum):
    """Types of changes detected in diff comparison"""
    ADDED = "added"
    REMOVED = "removed"
    MODIFIED = "modified"
    UNCHANGED = "unchanged"


@dataclass
class ComponentDiff:
    """Represents a diff for a single component (metric or dimension)"""
    id: str
    name: str
    change_type: ChangeType
    source_data: Optional[Dict] = None  # Full data from source
    target_data: Optional[Dict] = None  # Full data from target
    changed_fields: Optional[Dict[str, Tuple[Any, Any]]] = None  # field -> (source_value, target_value)

    def __post_init__(self):
        if self.changed_fields is None:
            self.changed_fields = {}


@dataclass
class MetadataDiff:
    """Represents changes to data view metadata"""
    source_name: str
    target_name: str
    source_id: str
    target_id: str
    source_owner: str = ""
    target_owner: str = ""
    source_description: str = ""
    target_description: str = ""
    changed_fields: Optional[Dict[str, Tuple[str, str]]] = None

    def __post_init__(self):
        if self.changed_fields is None:
            self.changed_fields = {}


@dataclass
class DiffSummary:
    """Summary statistics for a diff operation"""
    source_metrics_count: int = 0
    target_metrics_count: int = 0
    source_dimensions_count: int = 0
    target_dimensions_count: int = 0
    metrics_added: int = 0
    metrics_removed: int = 0
    metrics_modified: int = 0
    metrics_unchanged: int = 0
    dimensions_added: int = 0
    dimensions_removed: int = 0
    dimensions_modified: int = 0
    dimensions_unchanged: int = 0

    @property
    def has_changes(self) -> bool:
        """Returns True if any changes were detected"""
        return (self.metrics_added > 0 or self.metrics_removed > 0 or
                self.metrics_modified > 0 or self.dimensions_added > 0 or
                self.dimensions_removed > 0 or self.dimensions_modified > 0)

    @property
    def total_changes(self) -> int:
        """Total number of changed items"""
        return (self.metrics_added + self.metrics_removed + self.metrics_modified +
                self.dimensions_added + self.dimensions_removed + self.dimensions_modified)

    @property
    def metrics_changed(self) -> int:
        """Total metrics that changed (added + removed + modified)"""
        return self.metrics_added + self.metrics_removed + self.metrics_modified

    @property
    def dimensions_changed(self) -> int:
        """Total dimensions that changed (added + removed + modified)"""
        return self.dimensions_added + self.dimensions_removed + self.dimensions_modified

    @property
    def metrics_change_percent(self) -> float:
        """Percentage of metrics that changed (based on max of source/target count)"""
        total = max(self.source_metrics_count, self.target_metrics_count)
        if total == 0:
            return 0.0
        return (self.metrics_changed / total) * 100

    @property
    def dimensions_change_percent(self) -> float:
        """Percentage of dimensions that changed (based on max of source/target count)"""
        total = max(self.source_dimensions_count, self.target_dimensions_count)
        if total == 0:
            return 0.0
        return (self.dimensions_changed / total) * 100

    @property
    def natural_language_summary(self) -> str:
        """Human-readable summary of changes for PRs, tickets, messages."""
        parts = []

        # Metrics changes
        metric_parts = []
        if self.metrics_added:
            metric_parts.append(f"{self.metrics_added} added")
        if self.metrics_removed:
            metric_parts.append(f"{self.metrics_removed} removed")
        if self.metrics_modified:
            metric_parts.append(f"{self.metrics_modified} modified")
        if metric_parts:
            parts.append(f"Metrics: {', '.join(metric_parts)}")

        # Dimensions changes
        dim_parts = []
        if self.dimensions_added:
            dim_parts.append(f"{self.dimensions_added} added")
        if self.dimensions_removed:
            dim_parts.append(f"{self.dimensions_removed} removed")
        if self.dimensions_modified:
            dim_parts.append(f"{self.dimensions_modified} modified")
        if dim_parts:
            parts.append(f"Dimensions: {', '.join(dim_parts)}")

        if not parts:
            return "No changes detected"

        return "; ".join(parts)


@dataclass
class DiffResult:
    """Complete result of a diff comparison"""
    summary: DiffSummary
    metadata_diff: MetadataDiff
    metric_diffs: List[ComponentDiff]
    dimension_diffs: List[ComponentDiff]
    source_label: str = "Source"
    target_label: str = "Target"
    generated_at: str = ""
    tool_version: str = ""

    def __post_init__(self):
        if not self.generated_at:
            self.generated_at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        if not self.tool_version:
            self.tool_version = __version__


@dataclass
class DataViewSnapshot:
    """A point-in-time snapshot of a data view for comparison"""
    snapshot_version: str = "1.0"
    created_at: str = ""
    data_view_id: str = ""
    data_view_name: str = ""
    owner: str = ""
    description: str = ""
    metrics: List[Dict] = None  # Full metric data from API
    dimensions: List[Dict] = None  # Full dimension data from API
    metadata: Dict = None  # Tool version, counts, etc.

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
        if self.metrics is None:
            self.metrics = []
        if self.dimensions is None:
            self.dimensions = []
        if self.metadata is None:
            self.metadata = {
                'tool_version': __version__,
                'metrics_count': len(self.metrics) if self.metrics else 0,
                'dimensions_count': len(self.dimensions) if self.dimensions else 0
            }

    def to_dict(self) -> Dict:
        """Convert snapshot to dictionary for JSON serialization"""
        return {
            'snapshot_version': self.snapshot_version,
            'created_at': self.created_at,
            'data_view_id': self.data_view_id,
            'data_view_name': self.data_view_name,
            'owner': self.owner,
            'description': self.description,
            'metrics': self.metrics,
            'dimensions': self.dimensions,
            'metadata': {
                'tool_version': self.metadata.get('tool_version', __version__),
                'metrics_count': len(self.metrics),
                'dimensions_count': len(self.dimensions)
            }
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'DataViewSnapshot':
        """Create snapshot from dictionary (loaded from JSON)"""
        return cls(
            snapshot_version=data.get('snapshot_version', '1.0'),
            created_at=data.get('created_at', ''),
            data_view_id=data.get('data_view_id', ''),
            data_view_name=data.get('data_view_name', ''),
            owner=data.get('owner', ''),
            description=data.get('description', ''),
            metrics=data.get('metrics', []),
            dimensions=data.get('dimensions', []),
            metadata=data.get('metadata', {})
        )


# ==================== SNAPSHOT MANAGER ====================

class SnapshotManager:
    """
    Manages data view snapshot lifecycle.

    Handles creating snapshots from live data views, saving/loading to JSON files,
    and listing available snapshots.
    """

    def __init__(self, logger: logging.Logger = None):
        self.logger = logger or logging.getLogger(__name__)

    def create_snapshot(self, cja, data_view_id: str, quiet: bool = False) -> DataViewSnapshot:
        """
        Create a snapshot from a live data view.

        Args:
            cja: Initialized cjapy.CJA instance
            data_view_id: The data view ID to snapshot
            quiet: Suppress progress output

        Returns:
            DataViewSnapshot with current state of data view
        """
        self.logger.info(f"Creating snapshot for data view: {data_view_id}")

        # Fetch data view info
        dv_info = cja.getDataView(data_view_id)
        if not dv_info:
            raise ValueError(f"Failed to fetch data view info for {data_view_id}")

        dv_name = dv_info.get('name', 'Unknown')
        dv_owner = dv_info.get('owner', {})
        owner_name = dv_owner.get('name', '') if isinstance(dv_owner, dict) else str(dv_owner)
        dv_description = dv_info.get('description', '')

        # Fetch metrics
        self.logger.info("Fetching metrics...")
        metrics_df = cja.getMetrics(data_view_id, inclType=True, full=True)
        metrics_list = []
        if metrics_df is not None and not metrics_df.empty:
            metrics_list = metrics_df.to_dict('records')
        self.logger.info(f"  Fetched {len(metrics_list)} metrics")

        # Fetch dimensions
        self.logger.info("Fetching dimensions...")
        dimensions_df = cja.getDimensions(data_view_id, inclType=True, full=True)
        dimensions_list = []
        if dimensions_df is not None and not dimensions_df.empty:
            dimensions_list = dimensions_df.to_dict('records')
        self.logger.info(f"  Fetched {len(dimensions_list)} dimensions")

        snapshot = DataViewSnapshot(
            data_view_id=data_view_id,
            data_view_name=dv_name,
            owner=owner_name,
            description=dv_description,
            metrics=metrics_list,
            dimensions=dimensions_list
        )

        self.logger.info(f"Snapshot created: {len(metrics_list)} metrics, {len(dimensions_list)} dimensions")
        return snapshot

    def save_snapshot(self, snapshot: DataViewSnapshot, filepath: str) -> str:
        """
        Save a snapshot to a JSON file.

        Args:
            snapshot: The snapshot to save
            filepath: Output file path

        Returns:
            Absolute path to saved file
        """
        filepath = os.path.abspath(filepath)
        os.makedirs(os.path.dirname(filepath) or '.', exist_ok=True)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(snapshot.to_dict(), f, indent=2, ensure_ascii=False)

        self.logger.info(f"Snapshot saved to: {filepath}")
        return filepath

    def load_snapshot(self, filepath: str) -> DataViewSnapshot:
        """
        Load a snapshot from a JSON file.

        Args:
            filepath: Path to snapshot file

        Returns:
            DataViewSnapshot loaded from file

        Raises:
            FileNotFoundError: If file doesn't exist
            json.JSONDecodeError: If file is not valid JSON
            ValueError: If file is not a valid snapshot
        """
        filepath = os.path.abspath(filepath)

        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Snapshot file not found: {filepath}")

        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)

        # Validate it's a snapshot file
        if 'snapshot_version' not in data:
            raise ValueError(f"Invalid snapshot file: {filepath} (missing snapshot_version)")

        snapshot = DataViewSnapshot.from_dict(data)
        self.logger.info(f"Loaded snapshot: {snapshot.data_view_name} ({snapshot.data_view_id})")
        self.logger.info(f"  Created: {snapshot.created_at}")
        self.logger.info(f"  Metrics: {len(snapshot.metrics)}, Dimensions: {len(snapshot.dimensions)}")

        return snapshot

    def list_snapshots(self, directory: str) -> List[Dict]:
        """
        List available snapshots in a directory.

        Args:
            directory: Directory to search for snapshots

        Returns:
            List of snapshot metadata dictionaries
        """
        snapshots = []
        directory = os.path.abspath(directory)

        if not os.path.exists(directory):
            return snapshots

        for filename in os.listdir(directory):
            if filename.endswith('.json'):
                filepath = os.path.join(directory, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if 'snapshot_version' in data:
                        snapshots.append({
                            'filename': filename,
                            'filepath': filepath,
                            'data_view_id': data.get('data_view_id', ''),
                            'data_view_name': data.get('data_view_name', ''),
                            'created_at': data.get('created_at', ''),
                            'metrics_count': len(data.get('metrics', [])),
                            'dimensions_count': len(data.get('dimensions', []))
                        })
                except (json.JSONDecodeError, IOError):
                    continue

        return sorted(snapshots, key=lambda x: x.get('created_at', ''), reverse=True)

    def apply_retention_policy(self, directory: str, data_view_id: str, keep_last: int) -> List[str]:
        """
        Apply retention policy by deleting old snapshots for a specific data view.

        Args:
            directory: Directory containing snapshots
            data_view_id: Data view ID to filter snapshots
            keep_last: Number of most recent snapshots to keep (0 = keep all)

        Returns:
            List of deleted file paths
        """
        if keep_last <= 0:
            return []

        # Get all snapshots for this data view
        all_snapshots = self.list_snapshots(directory)
        dv_snapshots = [s for s in all_snapshots if s.get('data_view_id') == data_view_id]

        # Already sorted by created_at (newest first) from list_snapshots
        if len(dv_snapshots) <= keep_last:
            return []

        # Delete old snapshots beyond the retention limit
        deleted = []
        for snapshot in dv_snapshots[keep_last:]:
            filepath = snapshot.get('filepath')
            if filepath and os.path.exists(filepath):
                try:
                    os.remove(filepath)
                    self.logger.info(f"Retention policy: Deleted old snapshot {filepath}")
                    deleted.append(filepath)
                except OSError as e:
                    self.logger.warning(f"Failed to delete snapshot {filepath}: {e}")

        return deleted

    def generate_snapshot_filename(self, data_view_id: str, data_view_name: str = None) -> str:
        """
        Generate a timestamped filename for auto-saved snapshots.

        Args:
            data_view_id: Data view ID
            data_view_name: Optional data view name for more readable filenames

        Returns:
            Filename string (without directory path)
        """
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        # Sanitize name for use in filename
        if data_view_name:
            safe_name = "".join(c if c.isalnum() or c in '-_' else '_' for c in data_view_name)
            safe_name = safe_name[:50]  # Limit length
            return f"{safe_name}_{data_view_id}_{timestamp}.json"
        return f"{data_view_id}_{timestamp}.json"


# ==================== GIT INTEGRATION ====================

def is_git_repository(path: Path) -> bool:
    """Check if the given path is inside a Git repository.

    Args:
        path: Directory path to check

    Returns:
        True if path is inside a Git repository
    """
    try:
        result = subprocess.run(
            ['git', 'rev-parse', '--git-dir'],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=10
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


def git_get_user_info() -> Tuple[str, str]:
    """Get Git user name and email from config.

    Returns:
        Tuple of (name, email), with fallbacks if not configured
    """
    name = "CJA SDR Generator"
    email = ""

    try:
        result = subprocess.run(
            ['git', 'config', 'user.name'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            name = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    try:
        result = subprocess.run(
            ['git', 'config', 'user.email'],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0 and result.stdout.strip():
            email = result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return name, email


def save_git_friendly_snapshot(
    snapshot: DataViewSnapshot,
    output_dir: Path,
    quality_issues: List[Dict] = None,
    logger: logging.Logger = None
) -> Dict[str, Path]:
    """Save snapshot in Git-friendly format (separate JSON files).

    Creates a directory structure optimized for Git diffs:
    - metrics.json: Sorted list of metrics
    - dimensions.json: Sorted list of dimensions
    - metadata.json: Data view metadata and quality summary

    Args:
        snapshot: DataViewSnapshot to save
        output_dir: Directory to save files (will create subdir for data view)
        quality_issues: Optional list of quality issues to include
        logger: Optional logger

    Returns:
        Dict mapping file type to saved file path
    """
    logger = logger or logging.getLogger(__name__)

    # Create data view directory
    safe_name = "".join(c if c.isalnum() or c in '-_' else '_' for c in snapshot.data_view_name)
    safe_name = safe_name[:50] if safe_name else snapshot.data_view_id
    dv_dir = output_dir / f"{safe_name}_{snapshot.data_view_id}"
    dv_dir.mkdir(parents=True, exist_ok=True)

    saved_files = {}

    # Sort metrics by ID for consistent diffs
    metrics_sorted = sorted(snapshot.metrics, key=lambda x: x.get('id', ''))
    metrics_file = dv_dir / "metrics.json"
    with open(metrics_file, 'w', encoding='utf-8') as f:
        json.dump(metrics_sorted, f, indent=2, ensure_ascii=False, default=str)
    saved_files['metrics'] = metrics_file
    logger.debug(f"Saved {len(metrics_sorted)} metrics to {metrics_file}")

    # Sort dimensions by ID for consistent diffs
    dimensions_sorted = sorted(snapshot.dimensions, key=lambda x: x.get('id', ''))
    dimensions_file = dv_dir / "dimensions.json"
    with open(dimensions_file, 'w', encoding='utf-8') as f:
        json.dump(dimensions_sorted, f, indent=2, ensure_ascii=False, default=str)
    saved_files['dimensions'] = dimensions_file
    logger.debug(f"Saved {len(dimensions_sorted)} dimensions to {dimensions_file}")

    # Create metadata file
    metadata = {
        'snapshot_version': snapshot.snapshot_version,
        'created_at': snapshot.created_at,
        'data_view_id': snapshot.data_view_id,
        'data_view_name': snapshot.data_view_name,
        'owner': snapshot.owner,
        'description': snapshot.description,
        'tool_version': __version__,
        'summary': {
            'metrics_count': len(snapshot.metrics),
            'dimensions_count': len(snapshot.dimensions),
            'total_components': len(snapshot.metrics) + len(snapshot.dimensions)
        }
    }

    # Add quality summary if provided
    if quality_issues:
        severity_counts = {}
        for issue in quality_issues:
            sev = issue.get('Severity', 'UNKNOWN')
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
        metadata['quality'] = {
            'total_issues': len(quality_issues),
            'by_severity': severity_counts
        }

    metadata_file = dv_dir / "metadata.json"
    with open(metadata_file, 'w', encoding='utf-8') as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False, default=str)
    saved_files['metadata'] = metadata_file
    logger.debug(f"Saved metadata to {metadata_file}")

    return saved_files


def generate_git_commit_message(
    data_view_id: str,
    data_view_name: str,
    metrics_count: int,
    dimensions_count: int,
    quality_issues: List[Dict] = None,
    diff_result: 'DiffResult' = None,
    custom_message: str = None
) -> str:
    """Generate a descriptive Git commit message for SDR snapshot.

    Args:
        data_view_id: Data view ID
        data_view_name: Data view name
        metrics_count: Number of metrics
        dimensions_count: Number of dimensions
        quality_issues: Optional list of quality issues
        diff_result: Optional diff result (for change summary)
        custom_message: Optional custom message to prepend

    Returns:
        Formatted commit message
    """
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M')

    # Subject line
    if custom_message:
        subject = f"[{data_view_id}] {custom_message}"
    else:
        subject = f"[{data_view_id}] SDR snapshot {timestamp}"

    lines = [subject, ""]

    # Data view info
    lines.append(f"Data View: {data_view_name}")
    lines.append(f"ID: {data_view_id}")
    lines.append(f"Components: {metrics_count} metrics, {dimensions_count} dimensions")
    lines.append("")

    # Change summary if diff available
    if diff_result and diff_result.summary.has_changes:
        summary = diff_result.summary
        lines.append("Changes:")
        if summary.metrics_added > 0:
            lines.append(f"  + {summary.metrics_added} metrics added")
        if summary.metrics_removed > 0:
            lines.append(f"  - {summary.metrics_removed} metrics removed")
        if summary.metrics_modified > 0:
            lines.append(f"  ~ {summary.metrics_modified} metrics modified")
        if summary.dimensions_added > 0:
            lines.append(f"  + {summary.dimensions_added} dimensions added")
        if summary.dimensions_removed > 0:
            lines.append(f"  - {summary.dimensions_removed} dimensions removed")
        if summary.dimensions_modified > 0:
            lines.append(f"  ~ {summary.dimensions_modified} dimensions modified")
        lines.append("")

    # Quality summary
    if quality_issues:
        severity_counts = {}
        for issue in quality_issues:
            sev = issue.get('Severity', 'UNKNOWN')
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        lines.append("Quality:")
        for sev in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO']:
            count = severity_counts.get(sev, 0)
            if count > 0:
                lines.append(f"  {sev}: {count}")
        lines.append("")

    # Footer
    lines.append(f"Generated by CJA SDR Generator v{__version__}")

    return "\n".join(lines)


def git_commit_snapshot(
    snapshot_dir: Path,
    data_view_id: str,
    data_view_name: str,
    metrics_count: int,
    dimensions_count: int,
    quality_issues: List[Dict] = None,
    diff_result: 'DiffResult' = None,
    custom_message: str = None,
    push: bool = False,
    logger: logging.Logger = None
) -> Tuple[bool, str]:
    """Commit snapshot files to Git with auto-generated message.

    Args:
        snapshot_dir: Directory containing the snapshot files
        data_view_id: Data view ID
        data_view_name: Data view name
        metrics_count: Number of metrics
        dimensions_count: Number of dimensions
        quality_issues: Optional quality issues for commit message
        diff_result: Optional diff result for change summary
        custom_message: Optional custom message to include
        push: Whether to push after committing
        logger: Optional logger

    Returns:
        Tuple of (success, commit_sha or error message)
    """
    logger = logger or logging.getLogger(__name__)

    # Check if Git is available
    if not is_git_repository(snapshot_dir):
        return False, f"Not a Git repository: {snapshot_dir}"

    try:
        # Stage the snapshot files
        logger.info(f"Staging snapshot files in {snapshot_dir}")
        result = subprocess.run(
            ['git', 'add', '.'],
            cwd=str(snapshot_dir),
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            return False, f"git add failed: {result.stderr}"

        # Check if there are changes to commit
        result = subprocess.run(
            ['git', 'diff', '--cached', '--quiet'],
            cwd=str(snapshot_dir),
            capture_output=True,
            timeout=10
        )
        if result.returncode == 0:
            logger.info("No changes to commit (snapshot unchanged)")
            return True, "no_changes"

        # Generate commit message
        commit_message = generate_git_commit_message(
            data_view_id=data_view_id,
            data_view_name=data_view_name,
            metrics_count=metrics_count,
            dimensions_count=dimensions_count,
            quality_issues=quality_issues,
            diff_result=diff_result,
            custom_message=custom_message
        )

        # Commit
        logger.info("Committing snapshot to Git")
        result = subprocess.run(
            ['git', 'commit', '-m', commit_message],
            cwd=str(snapshot_dir),
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            return False, f"git commit failed: {result.stderr}"

        # Get commit SHA
        result = subprocess.run(
            ['git', 'rev-parse', 'HEAD'],
            cwd=str(snapshot_dir),
            capture_output=True,
            text=True,
            timeout=10
        )
        commit_sha = result.stdout.strip()[:8] if result.returncode == 0 else "unknown"

        logger.info(f"Committed snapshot: {commit_sha}")

        # Push if requested
        if push:
            logger.info("Pushing to remote")
            result = subprocess.run(
                ['git', 'push'],
                cwd=str(snapshot_dir),
                capture_output=True,
                text=True,
                timeout=60
            )
            if result.returncode != 0:
                logger.warning(f"git push failed: {result.stderr}")
                return True, f"{commit_sha} (push failed: {result.stderr.strip()})"
            logger.info("Pushed to remote successfully")

        return True, commit_sha

    except subprocess.TimeoutExpired:
        return False, "Git operation timed out"
    except FileNotFoundError:
        return False, "Git not found - ensure Git is installed and in PATH"
    except Exception as e:
        return False, f"Git error: {str(e)}"


def git_init_snapshot_repo(
    directory: Path,
    logger: logging.Logger = None
) -> Tuple[bool, str]:
    """Initialize a new Git repository for snapshots.

    Args:
        directory: Directory to initialize
        logger: Optional logger

    Returns:
        Tuple of (success, message)
    """
    logger = logger or logging.getLogger(__name__)

    try:
        directory.mkdir(parents=True, exist_ok=True)

        if is_git_repository(directory):
            return True, "Already a Git repository"

        logger.info(f"Initializing Git repository in {directory}")
        result = subprocess.run(
            ['git', 'init'],
            cwd=str(directory),
            capture_output=True,
            text=True,
            timeout=30
        )
        if result.returncode != 0:
            return False, f"git init failed: {result.stderr}"

        # Create .gitignore
        gitignore = directory / ".gitignore"
        gitignore.write_text("# CJA SDR Snapshots\n*.log\n*.tmp\n.DS_Store\n")

        # Create README
        readme = directory / "README.md"
        readme.write_text(f"""# CJA SDR Snapshots

This repository contains Solution Design Reference (SDR) snapshots from Adobe Customer Journey Analytics.

## Structure

```
<data_view_name>_<data_view_id>/
├── metrics.json      # All metrics (sorted by ID)
├── dimensions.json   # All dimensions (sorted by ID)
└── metadata.json     # Data view info and quality summary
```

## Usage

View history:
```bash
git log --oneline
```

Compare versions:
```bash
git diff HEAD~1 HEAD -- <data_view_dir>/metrics.json
```

---
Generated by CJA SDR Generator v{__version__}
""")

        # Initial commit
        subprocess.run(['git', 'add', '.'], cwd=str(directory), capture_output=True, timeout=30)
        subprocess.run(
            ['git', 'commit', '-m', 'Initialize SDR snapshot repository'],
            cwd=str(directory),
            capture_output=True,
            timeout=30
        )

        logger.info(f"Initialized Git repository: {directory}")
        return True, "Repository initialized"

    except Exception as e:
        return False, f"Initialization failed: {str(e)}"


# ==================== DATA VIEW COMPARATOR ====================

class DataViewComparator:
    """
    Compares two data view snapshots and produces a DiffResult.

    Supports comparing:
    - Two live data views
    - A live data view against a saved snapshot
    - Two saved snapshots

    Features:
    - Matches components by ID
    - Detects additions, removals, and modifications
    - Configurable field comparison
    - Field ignore list support
    - Extended field comparison including attribution, format settings
    """

    # Default fields to compare for change detection (basic set)
    DEFAULT_COMPARE_FIELDS = ['name', 'title', 'description', 'type', 'schemaPath']

    # Extended fields for comprehensive comparison (includes configuration settings)
    EXTENDED_COMPARE_FIELDS = [
        # Basic identification
        'name', 'title', 'description', 'type', 'schemaPath',
        # Component configuration
        'hidden', 'hideFromReporting', 'precision', 'format',
        # Behavioral settings
        'segmentable', 'reportable', 'componentType',
        # Attribution settings (for metrics)
        'attribution', 'attributionModel', 'lookbackWindow',
        # Data settings
        'dataType', 'hasData', 'approved',
        # Bucketing (for dimensions)
        'bucketing', 'bucketingSetting',
        # Persistence
        'persistence', 'persistenceSetting', 'allocation',
        # Derived/calculated
        'formula', 'isCalculated', 'derivedFieldId',
    ]

    def __init__(self, logger: logging.Logger = None, ignore_fields: List[str] = None,
                 compare_fields: List[str] = None, use_extended_fields: bool = False,
                 show_only: Optional[List[str]] = None, metrics_only: bool = False,
                 dimensions_only: bool = False):
        """
        Initialize the comparator.

        Args:
            logger: Logger instance
            ignore_fields: Fields to ignore during comparison
            compare_fields: Fields to compare (overrides default)
            use_extended_fields: Use extended field set for comprehensive comparison
            show_only: Filter to show only specific change types ('added', 'removed', 'modified', 'unchanged')
            metrics_only: Only include metrics in comparison
            dimensions_only: Only include dimensions in comparison
        """
        self.logger = logger or logging.getLogger(__name__)
        self.ignore_fields = set(ignore_fields or [])
        if compare_fields:
            self.compare_fields = compare_fields
        elif use_extended_fields:
            self.compare_fields = self.EXTENDED_COMPARE_FIELDS
        else:
            self.compare_fields = self.DEFAULT_COMPARE_FIELDS
        self.show_only = set(show_only) if show_only else None
        self.metrics_only = metrics_only
        self.dimensions_only = dimensions_only

    def compare(self, source: DataViewSnapshot, target: DataViewSnapshot,
                source_label: str = "Source", target_label: str = "Target") -> DiffResult:
        """
        Compare two data view snapshots.

        Args:
            source: Source snapshot (baseline)
            target: Target snapshot (current state)
            source_label: Label for source in output
            target_label: Label for target in output

        Returns:
            DiffResult with all differences
        """
        self.logger.info(f"Comparing data views:")
        self.logger.info(f"  {source_label}: {source.data_view_name} ({source.data_view_id})")
        self.logger.info(f"  {target_label}: {target.data_view_name} ({target.data_view_id})")

        # Compare metrics (unless dimensions_only is set)
        if self.dimensions_only:
            metric_diffs = []
        else:
            metric_diffs = self._compare_components(
                source.metrics, target.metrics, "metrics"
            )
            # Apply show_only filter if set
            metric_diffs = self._apply_show_only_filter(metric_diffs)

        # Compare dimensions (unless metrics_only is set)
        if self.metrics_only:
            dimension_diffs = []
        else:
            dimension_diffs = self._compare_components(
                source.dimensions, target.dimensions, "dimensions"
            )
            # Apply show_only filter if set
            dimension_diffs = self._apply_show_only_filter(dimension_diffs)

        # Build metadata diff
        metadata_diff = self._build_metadata_diff(source, target)

        # Build summary (use original lists for accurate counts)
        summary = self._build_summary(source, target, metric_diffs, dimension_diffs)

        self.logger.info(f"Comparison complete:")
        self.logger.info(f"  Metrics: +{summary.metrics_added} -{summary.metrics_removed} ~{summary.metrics_modified}")
        self.logger.info(f"  Dimensions: +{summary.dimensions_added} -{summary.dimensions_removed} ~{summary.dimensions_modified}")

        return DiffResult(
            summary=summary,
            metadata_diff=metadata_diff,
            metric_diffs=metric_diffs,
            dimension_diffs=dimension_diffs,
            source_label=source_label,
            target_label=target_label
        )

    def _apply_show_only_filter(self, diffs: List[ComponentDiff]) -> List[ComponentDiff]:
        """Apply show_only filter to diff results."""
        if not self.show_only:
            return diffs

        # Map show_only strings to ChangeType enum values
        type_map = {
            'added': ChangeType.ADDED,
            'removed': ChangeType.REMOVED,
            'modified': ChangeType.MODIFIED,
            'unchanged': ChangeType.UNCHANGED,
        }

        allowed_types = {type_map[t] for t in self.show_only if t in type_map}

        return [d for d in diffs if d.change_type in allowed_types]

    def _compare_components(self, source_list: List[Dict], target_list: List[Dict],
                           component_type: str) -> List[ComponentDiff]:
        """Compare two lists of components by ID"""
        diffs = []

        # Build lookup maps by ID
        source_map = {item.get('id'): item for item in source_list if item.get('id')}
        target_map = {item.get('id'): item for item in target_list if item.get('id')}

        all_ids = set(source_map.keys()) | set(target_map.keys())

        for item_id in sorted(all_ids):
            source_item = source_map.get(item_id)
            target_item = target_map.get(item_id)

            if source_item and not target_item:
                # Removed
                diffs.append(ComponentDiff(
                    id=item_id,
                    name=source_item.get('name', source_item.get('title', 'Unknown')),
                    change_type=ChangeType.REMOVED,
                    source_data=source_item,
                    target_data=None
                ))
            elif target_item and not source_item:
                # Added
                diffs.append(ComponentDiff(
                    id=item_id,
                    name=target_item.get('name', target_item.get('title', 'Unknown')),
                    change_type=ChangeType.ADDED,
                    source_data=None,
                    target_data=target_item
                ))
            else:
                # Both exist - check for modifications
                changed_fields = self._find_changed_fields(source_item, target_item)
                if changed_fields:
                    diffs.append(ComponentDiff(
                        id=item_id,
                        name=target_item.get('name', target_item.get('title', 'Unknown')),
                        change_type=ChangeType.MODIFIED,
                        source_data=source_item,
                        target_data=target_item,
                        changed_fields=changed_fields
                    ))
                else:
                    diffs.append(ComponentDiff(
                        id=item_id,
                        name=target_item.get('name', target_item.get('title', 'Unknown')),
                        change_type=ChangeType.UNCHANGED,
                        source_data=source_item,
                        target_data=target_item
                    ))

        return diffs

    def _find_changed_fields(self, source: Dict, target: Dict) -> Dict[str, Tuple[Any, Any]]:
        """Find fields that differ between source and target, including nested structures."""
        changed = {}

        for field in self.compare_fields:
            if field in self.ignore_fields:
                continue

            source_val = source.get(field)
            target_val = target.get(field)

            # Normalize for comparison (handle None vs empty string, nested dicts)
            source_normalized = self._normalize_value(source_val)
            target_normalized = self._normalize_value(target_val)

            if source_normalized != target_normalized:
                changed[field] = (source_val, target_val)

        return changed

    def _normalize_value(self, value: Any) -> Any:
        """Normalize a value for comparison, handling nested structures."""
        if value is None:
            return ''
        # Handle NaN values (pandas/numpy NaN, float nan)
        # Must check before string since pd.isna works on scalars
        try:
            if pd.isna(value):
                return ''
        except (TypeError, ValueError):
            # pd.isna can fail on some types like dicts/lists
            pass
        if isinstance(value, str):
            return value.strip()
        if isinstance(value, dict):
            # Recursively normalize dict values and sort keys for consistent comparison
            return self._normalize_dict(value)
        if isinstance(value, list):
            # Normalize list items
            return [self._normalize_value(v) for v in value]
        return value

    def _normalize_dict(self, d: Dict) -> Dict:
        """Normalize a dictionary for comparison."""
        if not d:
            return {}
        result = {}
        for k, v in sorted(d.items()):
            normalized = self._normalize_value(v)
            # Skip empty values for cleaner comparison
            if normalized != '' and normalized != {} and normalized != []:
                result[k] = normalized
        return result

    def _build_metadata_diff(self, source: DataViewSnapshot, target: DataViewSnapshot) -> MetadataDiff:
        """Build metadata diff between snapshots"""
        changed_fields = {}

        if source.data_view_name != target.data_view_name:
            changed_fields['name'] = (source.data_view_name, target.data_view_name)
        if source.owner != target.owner:
            changed_fields['owner'] = (source.owner, target.owner)
        if source.description != target.description:
            changed_fields['description'] = (source.description, target.description)

        return MetadataDiff(
            source_name=source.data_view_name,
            target_name=target.data_view_name,
            source_id=source.data_view_id,
            target_id=target.data_view_id,
            source_owner=source.owner,
            target_owner=target.owner,
            source_description=source.description,
            target_description=target.description,
            changed_fields=changed_fields
        )

    def _build_summary(self, source: DataViewSnapshot, target: DataViewSnapshot,
                       metric_diffs: List[ComponentDiff],
                       dimension_diffs: List[ComponentDiff]) -> DiffSummary:
        """Build summary statistics from diffs"""
        return DiffSummary(
            source_metrics_count=len(source.metrics),
            target_metrics_count=len(target.metrics),
            source_dimensions_count=len(source.dimensions),
            target_dimensions_count=len(target.dimensions),
            metrics_added=sum(1 for d in metric_diffs if d.change_type == ChangeType.ADDED),
            metrics_removed=sum(1 for d in metric_diffs if d.change_type == ChangeType.REMOVED),
            metrics_modified=sum(1 for d in metric_diffs if d.change_type == ChangeType.MODIFIED),
            metrics_unchanged=sum(1 for d in metric_diffs if d.change_type == ChangeType.UNCHANGED),
            dimensions_added=sum(1 for d in dimension_diffs if d.change_type == ChangeType.ADDED),
            dimensions_removed=sum(1 for d in dimension_diffs if d.change_type == ChangeType.REMOVED),
            dimensions_modified=sum(1 for d in dimension_diffs if d.change_type == ChangeType.MODIFIED),
            dimensions_unchanged=sum(1 for d in dimension_diffs if d.change_type == ChangeType.UNCHANGED)
        )


# ==================== LOGGING SETUP ====================

# Module-level tracking to prevent duplicate logger initialization
_logging_initialized = False
_current_log_file = None
_atexit_registered = False

def setup_logging(
    data_view_id: Optional[str] = None,
    batch_mode: bool = False,
    log_level: Optional[str] = None
) -> logging.Logger:
    """Setup logging to both file and console.

    Args:
        data_view_id: Data view ID for log file naming
        batch_mode: Whether running in batch mode
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured logger instance

    Priority: 1) Passed parameter, 2) Environment variable LOG_LEVEL, 3) Default INFO
    """
    global _logging_initialized, _current_log_file, _atexit_registered

    # Register atexit handler once to ensure logs are flushed on exit
    if not _atexit_registered:
        atexit.register(logging.shutdown)
        _atexit_registered = True

    # Create logs directory if it doesn't exist
    log_dir = Path("logs")
    try:
        log_dir.mkdir(exist_ok=True)
    except PermissionError:
        print(f"Warning: Cannot create logs directory (permission denied). Logging to console only.", file=sys.stderr)
        log_dir = None
    except OSError as e:
        print(f"Warning: Cannot create logs directory: {e}. Logging to console only.", file=sys.stderr)
        log_dir = None

    # Create log filename with timestamp
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    if log_dir is not None:
        if batch_mode:
            log_file = log_dir / f"SDR_Batch_Generation_{timestamp}.log"
        else:
            log_file = log_dir / f"SDR_Generation_{data_view_id}_{timestamp}.log"
    else:
        log_file = None

    # Determine log level with priority: parameter > env var > default
    if log_level is None:
        log_level = os.environ.get('LOG_LEVEL', 'INFO')

    # Validate log level
    valid_levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL']
    if log_level.upper() not in valid_levels:
        print(f"Warning: Invalid log level '{log_level}', using INFO", file=sys.stderr)
        log_level = 'INFO'

    # Get numeric log level
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # Clear any existing handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

    # Configure logging handlers
    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file is not None:
        # Use RotatingFileHandler to prevent unbounded log growth
        handlers.append(RotatingFileHandler(
            log_file,
            maxBytes=LOG_FILE_MAX_BYTES,
            backupCount=LOG_FILE_BACKUP_COUNT
        ))

    # Configure logging
    logging.basicConfig(
        level=numeric_level,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=handlers,
        force=True
    )

    logger = logging.getLogger(__name__)

    # Track initialization state to prevent duplicates
    _logging_initialized = True
    _current_log_file = log_file

    if log_file is not None:
        logger.info(f"Logging initialized. Log file: {log_file}")
    else:
        logger.info("Logging initialized. Console output only.")

    # Flush handlers to ensure log file is not empty even on early exit
    for handler in logger.handlers:
        handler.flush()

    return logger

# ==================== PERFORMANCE TRACKING ====================

class PerformanceTracker:
    """Track execution time for operations"""
    def __init__(self, logger: logging.Logger):
        self.metrics = {}
        self.logger = logger
        self.start_times = {}

    def start(self, operation_name: str):
        """Start timing an operation"""
        self.start_times[operation_name] = time.time()

    def end(self, operation_name: str):
        """End timing an operation"""
        if operation_name in self.start_times:
            duration = time.time() - self.start_times[operation_name]
            self.metrics[operation_name] = duration

            # Log individual operations only in DEBUG mode for performance
            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(f"⏱️  {operation_name} completed in {duration:.2f}s")

            del self.start_times[operation_name]

    def get_summary(self) -> str:
        """Generate performance summary"""
        if not self.metrics:
            return "No performance metrics collected"

        total = sum(self.metrics.values())
        lines = ["", "=" * 60, "PERFORMANCE SUMMARY", "=" * 60]

        for operation, duration in sorted(self.metrics.items(), key=lambda x: x[1], reverse=True):
            percentage = (duration / total) * 100 if total > 0 else 0
            lines.append(f"{operation:35s}: {duration:6.2f}s ({percentage:5.1f}%)")

        lines.extend(["=" * 60, f"{'Total Execution Time':35s}: {total:6.2f}s", "=" * 60])
        return "\n".join(lines)

    def add_cache_statistics(self, cache):
        """Add cache statistics to performance metrics"""
        stats = cache.get_statistics()

        if stats['total_requests'] > 0:
            self.logger.info("")
            self.logger.info("=" * 60)
            self.logger.info("VALIDATION CACHE STATISTICS")
            self.logger.info("=" * 60)
            self.logger.info(f"Cache Hits:        {stats['hits']}")
            self.logger.info(f"Cache Misses:      {stats['misses']}")
            self.logger.info(f"Hit Rate:          {stats['hit_rate']:.1f}%")
            self.logger.info(f"Cache Size:        {stats['size']}/{stats['max_size']}")
            self.logger.info(f"Evictions:         {stats['evictions']}")

            if stats['hits'] > 0:
                # Assume average validation takes 50ms, cache lookup takes 1ms
                time_saved = stats['hits'] * 0.049  # 49ms saved per hit
                self.logger.info(f"Estimated Time Saved: {time_saved:.2f}s")

            self.logger.info("=" * 60)

# ==================== VALIDATION CACHE ====================

class ValidationCache:
    """
    Thread-safe LRU cache for data quality validation results

    Caches validation results based on DataFrame content hash and configuration.
    Uses LRU eviction policy to prevent unbounded memory growth.

    Performance Impact:
    - Cache hits: 50-90% faster than running validation
    - Cache misses: ~1-2% overhead for hashing (negligible)
    - Memory: ~1-5MB per 1000 cached entries

    Thread Safety:
    - Uses threading.Lock for all cache operations
    - Safe for use with parallel validation (check_all_parallel)
    """

    def __init__(self, max_size: int = 1000, ttl_seconds: int = 3600, logger: logging.Logger = None):
        """
        Initialize validation cache

        Args:
            max_size: Maximum number of cached entries, >= 1 (default: 1000)
            ttl_seconds: Time-to-live for cache entries in seconds, >= 1 (default: 3600 = 1 hour)
            logger: Logger instance for cache statistics (default: module logger)
        """
        self.max_size = max_size
        self.ttl_seconds = ttl_seconds
        self.logger = logger or logging.getLogger(__name__)

        # Cache storage: key -> (issues_list, timestamp)
        self._cache: Dict[str, Tuple[List[Dict], float]] = {}

        # LRU tracking: key -> last_access_time
        self._access_times: Dict[str, float] = {}

        # Thread safety
        self._lock = threading.Lock()

        # Statistics
        self._hits = 0
        self._misses = 0
        self._evictions = 0

        self.logger.debug(f"ValidationCache initialized: max_size={max_size}, ttl={ttl_seconds}s")

    def _generate_cache_key(self, df: pd.DataFrame, item_type: str,
                           required_fields: List[str], critical_fields: List[str]) -> str:
        """
        Generate cache key from DataFrame content and configuration

        Strategy:
        - Uses pandas.util.hash_pandas_object for efficient DataFrame hashing
        - Combines DataFrame hash with configuration parameters
        - Returns consistent hash for identical inputs

        Args:
            df: DataFrame to hash
            item_type: 'Metrics' or 'Dimensions'
            required_fields: List of required field names
            critical_fields: List of critical field names

        Returns:
            Cache key string in format: "{item_type}:{df_hash}:{config_hash}"
        """
        try:
            # Hash DataFrame content using pandas built-in function
            # This is much faster than manual iteration (1-2ms vs 10-50ms for 1000 rows)

            # Hash DataFrame structure and content
            df_hash = pd.util.hash_pandas_object(df, index=False).sum()

            # Hash configuration (required_fields + critical_fields)
            config_str = f"{sorted(required_fields)}:{sorted(critical_fields)}"
            config_hash = hashlib.md5(config_str.encode()).hexdigest()[:8]

            # Combine into cache key
            cache_key = f"{item_type}:{df_hash}:{config_hash}"

            return cache_key

        except Exception as e:
            self.logger.warning(f"Error generating cache key: {e}. Cache disabled for this call.")
            # Return unique key to force cache miss
            return f"error:{time.time()}"

    def get(self, df: pd.DataFrame, item_type: str,
           required_fields: List[str], critical_fields: List[str]) -> Tuple[Optional[List[Dict]], str]:
        """
        Retrieve cached validation results if available

        Returns:
            Tuple of (issues list or None, cache_key).
            The cache_key can be passed to put() to avoid recomputing the hash.
        """
        cache_key = self._generate_cache_key(df, item_type, required_fields, critical_fields)

        # Check debug logging once outside the lock to avoid repeated checks
        debug_enabled = self.logger.isEnabledFor(logging.DEBUG)

        with self._lock:
            if cache_key not in self._cache:
                self._misses += 1
                if debug_enabled:
                    self.logger.debug(f"Cache MISS: {item_type} (key: {cache_key[:20]}...)")
                return None, cache_key

            cached_issues, timestamp = self._cache[cache_key]

            # Check TTL expiration
            age = time.time() - timestamp
            if age > self.ttl_seconds:
                if debug_enabled:
                    self.logger.debug(f"Cache EXPIRED: {item_type} (age: {age:.1f}s)")
                del self._cache[cache_key]
                del self._access_times[cache_key]
                self._misses += 1
                return None, cache_key

            # Cache hit - update access time
            self._access_times[cache_key] = time.time()
            self._hits += 1
            if debug_enabled:
                self.logger.debug(f"Cache HIT: {item_type} ({len(cached_issues)} issues)")

            # Return deep copy to prevent mutation of cached data
            return [issue.copy() for issue in cached_issues], cache_key

    def put(self, df: pd.DataFrame, item_type: str,
           required_fields: List[str], critical_fields: List[str],
           issues: List[Dict], cache_key: str = None):
        """
        Store validation results in cache

        Implements LRU eviction when cache is full.

        Args:
            cache_key: Optional pre-computed cache key from get() to avoid rehashing
        """
        if cache_key is None:
            cache_key = self._generate_cache_key(df, item_type, required_fields, critical_fields)

        # Check debug logging once to avoid repeated checks in hot path
        debug_enabled = self.logger.isEnabledFor(logging.DEBUG)

        with self._lock:
            # Evict oldest entry if cache is full
            if len(self._cache) >= self.max_size and cache_key not in self._cache:
                self._evict_lru(debug_enabled)

            # Store issues with timestamp
            # Deep copy to prevent external mutation
            self._cache[cache_key] = ([issue.copy() for issue in issues], time.time())
            self._access_times[cache_key] = time.time()

            if debug_enabled:
                self.logger.debug(f"Cache STORE: {item_type} ({len(issues)} issues)")

    def _evict_lru(self, debug_enabled: bool = False):
        """Evict least recently used cache entry.

        Args:
            debug_enabled: Whether debug logging is enabled (avoids repeated checks)
        """
        if not self._access_times:
            return

        # Find least recently used key
        lru_key = min(self._access_times.items(), key=lambda x: x[1])[0]

        # Remove from cache
        del self._cache[lru_key]
        del self._access_times[lru_key]
        self._evictions += 1

        if debug_enabled:
            self.logger.debug(f"Cache EVICT: LRU entry removed (total evictions: {self._evictions})")

    def get_statistics(self) -> Dict[str, any]:
        """
        Get cache performance statistics

        Returns:
            Dict with hits, misses, hit_rate, size, evictions
        """
        with self._lock:
            total_requests = self._hits + self._misses
            hit_rate = (self._hits / total_requests * 100) if total_requests > 0 else 0

            return {
                'hits': self._hits,
                'misses': self._misses,
                'hit_rate': hit_rate,
                'size': len(self._cache),
                'max_size': self.max_size,
                'evictions': self._evictions,
                'total_requests': total_requests
            }

    def clear(self):
        """Clear all cache entries (useful for testing)"""
        with self._lock:
            self._cache.clear()
            self._access_times.clear()
            self.logger.debug("Cache cleared")

    def log_statistics(self):
        """
        Log cache statistics in a user-friendly format.

        Logs hit rate, total requests, cache size, and estimated time savings.
        Only logs if there have been cache requests.
        """
        stats = self.get_statistics()
        if stats['total_requests'] == 0:
            self.logger.debug("Cache statistics: No requests recorded")
            return

        # Estimate time saved (average validation ~50ms, cache lookup ~1ms)
        estimated_time_saved = stats['hits'] * 0.049  # 49ms saved per hit

        self.logger.info(f"Cache Statistics: {stats['hits']}/{stats['total_requests']} hits "
                        f"({stats['hit_rate']:.1f}% hit rate)")
        self.logger.info(f"  - Cache size: {stats['size']}/{stats['max_size']} entries")
        if stats['evictions'] > 0:
            self.logger.info(f"  - Evictions: {stats['evictions']}")
        if estimated_time_saved > 0.1:
            self.logger.info(f"  - Estimated time saved: {estimated_time_saved:.2f}s")

# ==================== CONFIG SCHEMA ====================

# Configuration schema definition for validation
# Uses OAuth Server-to-Server authentication: org_id, client_id, secret, scopes
CONFIG_SCHEMA = {
    # Fields required for OAuth Server-to-Server authentication
    'base_required_fields': {
        'org_id': {'type': str, 'description': 'Adobe Organization ID'},
        'client_id': {'type': str, 'description': 'OAuth Client ID'},
        'secret': {'type': str, 'description': 'Client Secret'},
    },
    'optional_fields': {
        'scopes': {'type': str, 'description': 'OAuth scopes'},
        'sandbox': {'type': str, 'description': 'Sandbox name (optional)'},
    }
}

# Deprecated JWT authentication fields (removed in v3.0.8)
# These fields indicate a user is trying to use the old JWT auth method
JWT_DEPRECATED_FIELDS = {
    'tech_acct': 'Technical Account ID (JWT auth)',
    'private_key': 'Private key file path (JWT auth)',
    'pathToKey': 'Private key file path (JWT auth)',
}

# Environment variable to config field mapping (for credentials)
ENV_VAR_MAPPING = {
    'org_id': 'ORG_ID',
    'client_id': 'CLIENT_ID',
    'secret': 'SECRET',
    'scopes': 'SCOPES',
    'sandbox': 'SANDBOX',
}

# Additional environment variables (non-credential settings)
# OUTPUT_DIR - Output directory for generated files (used by --output-dir)


def load_credentials_from_env() -> Optional[Dict[str, str]]:
    """
    Load Adobe API credentials from environment variables.

    Environment variables:
        ORG_ID: Adobe Organization ID
        CLIENT_ID: OAuth Client ID
        SECRET: Client Secret
        SCOPES: OAuth scopes
        SANDBOX: Sandbox name (optional)

    Returns:
        Dictionary with credentials if any env vars are set, None otherwise
    """
    credentials = {}
    for config_key, env_var in ENV_VAR_MAPPING.items():
        value = os.environ.get(env_var)
        if value and value.strip():
            credentials[config_key] = value.strip()

    # Return None if no CJA environment variables are set
    if not credentials:
        return None

    return credentials


def validate_env_credentials(credentials: Dict[str, str], logger: logging.Logger) -> bool:
    """
    Validate that environment credentials have minimum required fields for OAuth.

    Args:
        credentials: Dictionary of credentials from environment
        logger: Logger instance

    Returns:
        True if credentials have minimum required fields
    """
    base_required = ['org_id', 'client_id', 'secret']

    for field in base_required:
        if field not in credentials or not credentials[field].strip():
            logger.debug(f"Missing required environment variable: {ENV_VAR_MAPPING.get(field, field)}")
            return False

    # Check for OAuth scopes (recommended but not strictly required)
    if 'scopes' not in credentials:
        logger.warning("Environment credentials missing OAuth scopes - recommend setting SCOPES")

    return True


def _config_from_env(credentials: Dict[str, str], logger: logging.Logger):
    """
    Configure cjapy using environment credentials.

    Creates a temporary JSON config file that is cleaned up on exit.

    Args:
        credentials: Dictionary of credentials from environment
        logger: Logger instance
    """
    # cjapy.importConfigFile expects a JSON file, so we create a temporary one
    # This is cleaned up on exit
    temp_config = tempfile.NamedTemporaryFile(
        mode='w',
        suffix='.json',
        delete=False,
        prefix='cja_env_config_'
    )

    json.dump(credentials, temp_config)
    temp_config.close()

    logger.debug(f"Created temporary config file: {temp_config.name}")

    # Register cleanup
    def cleanup_temp_config():
        try:
            os.unlink(temp_config.name)
        except OSError:
            pass

    atexit.register(cleanup_temp_config)

    # Import the temporary config
    cjapy.importConfigFile(temp_config.name)


# ==================== CJA INITIALIZATION ====================

def validate_config_file(
    config_file: Union[str, Path],
    logger: logging.Logger
) -> bool:
    """
    Validate configuration file exists and has required structure.

    Performs comprehensive validation:
    1. File existence and readability
    2. JSON syntax validation
    3. Required fields presence
    4. Field type validation
    5. Empty value detection
    6. Private key file validation (if path provided)

    Args:
        config_file: Path to the configuration JSON file
        logger: Logger instance for output

    Returns:
        True if validation passes, False otherwise

    Raises:
        ConfigurationError: If validation fails (when exceptions are preferred)
    """
    validation_errors = []
    validation_warnings = []

    try:
        logger.info(f"Validating configuration file: {config_file}")

        config_path = Path(config_file)

        # Check if file exists
        if not config_path.exists():
            error_msg = ErrorMessageHelper.get_config_error_message(
                "file_not_found",
                details=f"Looking for: {config_path.absolute()}"
            )
            logger.error("\n" + error_msg)
            return False

        # Check if file is readable
        if not config_path.is_file():
            logger.error(f"'{config_file}' is not a valid file")
            return False

        # Validate JSON structure
        try:
            with open(config_path, 'r') as f:
                config_data = json.load(f)
        except json.JSONDecodeError as e:
            error_msg = ErrorMessageHelper.get_config_error_message(
                "invalid_json",
                details=f"Line {e.lineno}, Column {e.colno}: {e.msg}"
            )
            logger.error("\n" + error_msg)
            return False

        # Validate it's a dictionary
        if not isinstance(config_data, dict):
            logger.error("Configuration file must contain a JSON object (dictionary)")
            return False

        # Check for base required fields (required for all auth methods)
        for field_name, field_info in CONFIG_SCHEMA['base_required_fields'].items():
            if field_name not in config_data:
                validation_errors.append(f"Missing required field: '{field_name}' ({field_info['description']})")
            elif not isinstance(config_data[field_name], field_info['type']):
                validation_errors.append(
                    f"Invalid type for '{field_name}': expected {field_info['type'].__name__}, "
                    f"got {type(config_data[field_name]).__name__}"
                )
            elif not config_data[field_name] or (isinstance(config_data[field_name], str) and not config_data[field_name].strip()):
                validation_errors.append(f"Empty value for required field: '{field_name}'")

        # OAuth Server-to-Server auth - warn if scopes not provided
        if 'scopes' not in config_data or not config_data.get('scopes', '').strip():
            validation_warnings.append(
                "OAuth Server-to-Server auth: 'scopes' field not set. "
                "Consider adding scopes (e.g., 'openid,AdobeID,additional_info.projectedProductContext') "
                "for proper API access."
            )

        # Validate optional fields if present
        for field_name, field_info in CONFIG_SCHEMA['optional_fields'].items():
            if field_name in config_data:
                if not isinstance(config_data[field_name], field_info['type']):
                    validation_warnings.append(
                        f"Invalid type for optional field '{field_name}': expected {field_info['type'].__name__}"
                    )

        # Check for deprecated JWT authentication fields
        deprecated_found = []
        for field, description in JWT_DEPRECATED_FIELDS.items():
            if field in config_data:
                deprecated_found.append(f"'{field}' ({description})")
        if deprecated_found:
            validation_warnings.append(
                f"DEPRECATED: JWT authentication was removed in v3.0.8. "
                f"Found JWT fields: {', '.join(deprecated_found)}. "
                f"Please migrate to OAuth Server-to-Server authentication. "
                f"See docs/QUICKSTART_GUIDE.md for setup instructions."
            )

        # Check for unknown fields (potential typos)
        known_fields = (set(CONFIG_SCHEMA['base_required_fields'].keys()) |
                        set(CONFIG_SCHEMA['optional_fields'].keys()) |
                        set(JWT_DEPRECATED_FIELDS.keys()))  # Include deprecated fields as "known"
        unknown_fields = set(config_data.keys()) - known_fields
        if unknown_fields:
            validation_warnings.append(f"Unknown fields in config (possible typos): {', '.join(unknown_fields)}")

        # Report validation results
        if validation_errors:
            logger.error("Configuration validation FAILED:")
            for error in validation_errors:
                logger.error(f"  - {error}")
            logger.error("")

            # Provide enhanced error message if missing credentials
            if any("Missing required field" in err for err in validation_errors):
                error_msg = ErrorMessageHelper.get_config_error_message(
                    "missing_credentials",
                    details="One or more required fields are missing from your config file"
                )
                logger.error(error_msg)
            elif any("Empty value" in err for err in validation_errors):
                error_msg = ErrorMessageHelper.get_config_error_message(
                    "invalid_format",
                    details="One or more fields have empty or invalid values"
                )
                logger.error(error_msg)
            return False

        if validation_warnings:
            logger.warning("Configuration validation warnings:")
            for warning in validation_warnings:
                logger.warning(f"  - {warning}")

        logger.info("Configuration file validated successfully")
        return True

    except PermissionError as e:
        logger.error(f"Permission denied reading config file: {e}")
        logger.error("Check file permissions for the configuration file")
        return False
    except Exception as e:
        logger.error(f"Unexpected error validating config file ({type(e).__name__}): {str(e)}")
        return False

def initialize_cja(
    config_file: Union[str, Path] = "config.json",
    logger: Optional[logging.Logger] = None
) -> Optional[cjapy.CJA]:
    """Initialize CJA connection with comprehensive error handling.

    Credential Loading Priority:
        1. Environment variables (ORG_ID, CLIENT_ID, SECRET, etc.)
        2. Configuration file (config.json)

    Args:
        config_file: Path to CJA configuration file
        logger: Logger instance (uses module logger if None)

    Returns:
        Initialized CJA instance, or None if initialization fails

    Raises:
        ConfigurationError: If credentials are invalid or missing
        APIError: If API connection fails
    """
    try:
        logger.info("=" * 60)
        logger.info("INITIALIZING CJA CONNECTION")
        logger.info("=" * 60)

        # Log dotenv status for debugging
        if _DOTENV_AVAILABLE:
            if _DOTENV_LOADED:
                logger.debug(".env file found and loaded")
            else:
                logger.debug(".env file not found (python-dotenv available but no .env file)")
        else:
            logger.debug("python-dotenv not installed (.env files will not be auto-loaded)")

        # Try environment variables first
        env_credentials = load_credentials_from_env()
        use_env_credentials = False

        if env_credentials:
            logger.info("Found environment variables with CJA credentials...")
            if validate_env_credentials(env_credentials, logger):
                use_env_credentials = True
                logger.info("Using credentials from environment variables")
            else:
                logger.info("Environment credentials incomplete, falling back to config file")

        if use_env_credentials:
            # Use environment credentials
            logger.info("Loading CJA configuration from environment...")
            _config_from_env(env_credentials, logger)
            logger.info("Configuration loaded from environment variables")
        else:
            # Fall back to config file
            logger.info(f"Validating configuration file: {config_file}")
            if not validate_config_file(config_file, logger):
                logger.critical("Configuration file validation failed")
                logger.critical("Please create a valid config file OR set environment variables.")
                logger.critical("")
                logger.critical("Option 1: Environment Variables")
                logger.critical("  export ORG_ID=your_org_id@AdobeOrg")
                logger.critical("  export CLIENT_ID=your_client_id")
                logger.critical("  export SECRET=your_client_secret")
                logger.critical("  export SCOPES='openid, AdobeID, additional_info.projectedProductContext'")
                logger.critical("")
                logger.critical("Option 2: Config File (config.json):")
                logger.critical(json.dumps({
                    "org_id": "your_org_id",
                    "client_id": "your_client_id",
                    "secret": "your_client_secret",
                    "scopes": "openid, AdobeID, additional_info.projectedProductContext"
                }, indent=2))
                return None

            # Load config file
            logger.info("Loading CJA configuration...")
            cjapy.importConfigFile(config_file)
            logger.info("Configuration loaded successfully")
        
        # Attempt to create CJA instance
        logger.info("Creating CJA instance...")
        cja = cjapy.CJA()
        logger.info("CJA instance created successfully")
        
        # Test connection with a simple API call (with retry)
        logger.info("Testing API connection...")
        try:
            # Attempt to list data views to verify connection with retry
            test_call = make_api_call_with_retry(
                cja.getDataViews,
                logger=logger,
                operation_name="getDataViews (connection test)"
            )
            if test_call is not None:
                logger.info(f"✓ API connection successful! Found {len(test_call) if hasattr(test_call, '__len__') else 'multiple'} data view(s)")
            else:
                logger.warning("API connection test returned None - connection may be unstable")
        except Exception as test_error:
            logger.warning(f"Could not verify connection with test call: {str(test_error)}")
            logger.warning("Proceeding anyway - errors may occur during data fetching")
        
        logger.info("CJA initialization complete")
        return cja
        
    except FileNotFoundError as e:
        logger.critical("=" * 60)
        logger.critical("CONFIGURATION FILE ERROR")
        logger.critical("=" * 60)
        logger.critical(f"Config file not found: {config_file}")
        logger.critical(f"Current working directory: {Path.cwd()}")
        logger.critical("Please ensure the configuration file exists in the correct location")
        return None
        
    except ImportError as e:
        logger.critical("=" * 60)
        logger.critical("DEPENDENCY ERROR")
        logger.critical("=" * 60)
        logger.critical(f"Failed to import cjapy module: {str(e)}")
        logger.critical("Please ensure cjapy is installed: pip install cjapy")
        return None
        
    except AttributeError as e:
        logger.critical("=" * 60)
        logger.critical("CJA CONFIGURATION ERROR")
        logger.critical("=" * 60)
        logger.critical(f"Configuration error: {str(e)}")
        logger.critical("This usually indicates an issue with the authentication credentials")
        logger.critical("Please verify all fields in your configuration file are correct")
        return None
        
    except PermissionError as e:
        logger.critical("=" * 60)
        logger.critical("PERMISSION ERROR")
        logger.critical("=" * 60)
        logger.critical(f"Cannot read configuration file: {str(e)}")
        logger.critical("Please check file permissions")
        return None
        
    except Exception as e:
        logger.critical("=" * 60)
        logger.critical("CJA INITIALIZATION FAILED")
        logger.critical("=" * 60)
        logger.critical(f"Unexpected error: {str(e)}")
        logger.critical(f"Error type: {type(e).__name__}")
        logger.exception("Full error details:")
        logger.critical("")
        logger.critical("Troubleshooting steps:")
        logger.critical("1. Verify your configuration file exists and is valid JSON")
        logger.critical("2. Check that all authentication credentials are correct")
        logger.critical("3. Ensure your API credentials have the necessary permissions")
        logger.critical("4. Verify you have network connectivity to Adobe services")
        logger.critical("5. Check if cjapy library is up to date: pip install --upgrade cjapy")
        return None

# ==================== DATA VIEW VALIDATION ====================

def validate_data_view(
    cja: cjapy.CJA,
    data_view_id: str,
    logger: logging.Logger
) -> bool:
    """Validate that the data view exists and is accessible.

    Args:
        cja: Initialized CJA instance
        data_view_id: Data view ID to validate
        logger: Logger instance

    Returns:
        True if data view is valid and accessible, False otherwise
    """
    try:
        logger.info("=" * 60)
        logger.info("VALIDATING DATA VIEW")
        logger.info("=" * 60)
        logger.info(f"Data View ID: {data_view_id}")
        
        # Basic format validation
        if not data_view_id or not isinstance(data_view_id, str):
            logger.error("Invalid data view ID format")
            logger.error("Data view ID must be a non-empty string")
            return False
        
        if not data_view_id.startswith('dv_'):
            logger.warning(f"Data view ID '{data_view_id}' does not follow standard format (dv_...)")
            logger.warning("This may still be valid, but unusual")
        
        # Attempt to fetch data view info
        logger.info("Fetching data view information from API...")
        try:
            dv_info = cja.getDataView(data_view_id)
        except AttributeError as e:
            logger.error("API method 'getDataView' not available")
            logger.error("This may indicate an outdated version of cjapy")
            logger.error("Please update cjapy: pip install --upgrade cjapy")
            return False
        except Exception as api_error:
            logger.error(f"API call failed: {str(api_error)}")
            logger.error("Possible reasons:")
            logger.error("  1. Data view does not exist")
            logger.error("  2. You don't have permission to access this data view")
            logger.error("  3. Network connectivity issues")
            logger.error("  4. API authentication has expired")
            return False
        
        # Validate response
        if not dv_info:
            # Try to list available data views to provide context
            available_count = None
            try:
                available_dvs = cja.getDataViews()
                available_count = len(available_dvs) if available_dvs else 0

                if available_count > 0:
                    logger.info(f"You have access to {available_count} data view(s):")
                    for i, dv in enumerate(available_dvs[:10]):  # Show first 10
                        dv_id = dv.get('id', 'unknown')
                        dv_name = dv.get('name', 'unknown')
                        logger.info(f"  {i+1}. {dv_name} (ID: {dv_id})")
                    if available_count > 10:
                        logger.info(f"  ... and {available_count - 10} more")
                    logger.info("")
            except Exception as list_error:
                logger.debug(f"Could not list available data views: {str(list_error)}")

            # Show enhanced error message
            error_msg = ErrorMessageHelper.get_data_view_error_message(
                data_view_id,
                available_count=available_count
            )
            logger.error("\n" + error_msg)
            return False
        
        # Extract and validate data view details
        dv_name = dv_info.get('name', 'Unknown')
        dv_description = dv_info.get('description', 'No description')
        dv_owner = dv_info.get('owner', {}).get('name', 'Unknown')
        
        logger.info("✓ Data view validated successfully!")
        logger.info(f"  Name: {dv_name}")
        logger.info(f"  ID: {data_view_id}")
        logger.info(f"  Owner: {dv_owner}")
        if dv_description and dv_description != 'No description':
            logger.info(f"  Description: {dv_description[:100]}{'...' if len(dv_description) > 100 else ''}")
        
        # Additional validation checks
        warnings = []
        
        if 'components' in dv_info:
            components = dv_info.get('components', {})
            if not components.get('dimensions') and not components.get('metrics'):
                warnings.append("Data view appears to have no components defined")
        
        if warnings:
            logger.warning("Data view validation warnings:")
            for warning in warnings:
                logger.warning(f"  - {warning}")
        
        return True
        
    except Exception as e:
        logger.error("=" * 60)
        logger.error("DATA VIEW VALIDATION ERROR")
        logger.error("=" * 60)
        logger.error(f"Unexpected error during validation: {str(e)}")
        logger.exception("Full error details:")
        logger.error("")
        logger.error("Please verify:")
        logger.error("  1. The data view ID is correct")
        logger.error("  2. You have access to this data view")
        logger.error("  3. Your API credentials are valid")
        return False

# ==================== OPTIMIZED API DATA FETCHING ====================

class ParallelAPIFetcher:
    """Fetch multiple API endpoints in parallel using threading"""

    def __init__(self, cja: cjapy.CJA, logger: logging.Logger, perf_tracker: 'PerformanceTracker',
                 max_workers: int = 3, quiet: bool = False):
        self.cja = cja
        self.logger = logger
        self.perf_tracker = perf_tracker
        self.max_workers = max_workers
        self.quiet = quiet
    
    def fetch_all_data(self, data_view_id: str) -> Tuple[pd.DataFrame, pd.DataFrame, dict]:
        """
        Fetch metrics, dimensions, and data view info in parallel
        
        Returns:
            Tuple of (metrics_df, dimensions_df, dataview_info)
        """
        self.logger.info("Starting parallel data fetch operations...")
        self.perf_tracker.start("Parallel API Fetch")

        results = {
            'metrics': None,
            'dimensions': None,
            'dataview': None
        }

        errors = {}

        # Define fetch tasks
        tasks = {
            'metrics': lambda: self._fetch_metrics(data_view_id),
            'dimensions': lambda: self._fetch_dimensions(data_view_id),
            'dataview': lambda: self._fetch_dataview_info(data_view_id)
        }

        # Execute tasks in parallel using ThreadPoolExecutor
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_name = {
                executor.submit(task): name
                for name, task in tasks.items()
            }

            # Collect results as they complete with progress indicator
            with tqdm(
                total=len(tasks),
                desc="Fetching API data",
                unit="item",
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}]",
                leave=False,
                disable=self.quiet
            ) as pbar:
                for future in as_completed(future_to_name):
                    task_name = future_to_name[future]
                    try:
                        results[task_name] = future.result()
                        pbar.set_postfix_str(f"✓ {task_name}", refresh=True)
                        self.logger.info(f"✓ {task_name.capitalize()} fetch completed")
                    except Exception as e:
                        errors[task_name] = str(e)
                        pbar.set_postfix_str(f"✗ {task_name}", refresh=True)
                        self.logger.error(f"✗ {task_name.capitalize()} fetch failed: {e}")
                    pbar.update(1)

        self.perf_tracker.end("Parallel API Fetch")
        
        # Log summary
        success_count = sum(1 for v in results.values() if v is not None)
        self.logger.info(f"Parallel fetch complete: {success_count}/3 successful")
        
        if errors:
            self.logger.warning(f"Errors encountered: {list(errors.keys())}")
        
        # Return results with proper None checking for DataFrames
        metrics_result = results.get('metrics')
        dimensions_result = results.get('dimensions')
        dataview_result = results.get('dataview')
        
        # Handle DataFrame None checks properly
        if metrics_result is None or (isinstance(metrics_result, pd.DataFrame) and metrics_result.empty):
            metrics_result = pd.DataFrame()
        
        if dimensions_result is None or (isinstance(dimensions_result, pd.DataFrame) and dimensions_result.empty):
            dimensions_result = pd.DataFrame()
        
        if dataview_result is None:
            dataview_result = {}
        
        return metrics_result, dimensions_result, dataview_result
    
    def _fetch_metrics(self, data_view_id: str) -> pd.DataFrame:
        """Fetch metrics with error handling and retry"""
        try:
            self.logger.debug(f"Fetching metrics for {data_view_id}")

            # Use retry for transient network errors
            metrics = make_api_call_with_retry(
                self.cja.getMetrics,
                data_view_id,
                inclType=True,
                full=True,
                logger=self.logger,
                operation_name="getMetrics"
            )

            if metrics is None or (isinstance(metrics, pd.DataFrame) and metrics.empty):
                self.logger.warning("No metrics returned from API")
                return pd.DataFrame()

            self.logger.info(f"Successfully fetched {len(metrics)} metrics")
            return metrics

        except AttributeError as e:
            self.logger.error(f"API method error - getMetrics may not be available: {str(e)}")
            return pd.DataFrame()
        except Exception as e:
            self.logger.error(f"Failed to fetch metrics: {str(e)}")
            return pd.DataFrame()

    def _fetch_dimensions(self, data_view_id: str) -> pd.DataFrame:
        """Fetch dimensions with error handling and retry"""
        try:
            self.logger.debug(f"Fetching dimensions for {data_view_id}")

            # Use retry for transient network errors
            dimensions = make_api_call_with_retry(
                self.cja.getDimensions,
                data_view_id,
                inclType=True,
                full=True,
                logger=self.logger,
                operation_name="getDimensions"
            )

            if dimensions is None or (isinstance(dimensions, pd.DataFrame) and dimensions.empty):
                self.logger.warning("No dimensions returned from API")
                return pd.DataFrame()

            self.logger.info(f"Successfully fetched {len(dimensions)} dimensions")
            return dimensions

        except AttributeError as e:
            self.logger.error(f"API method error - getDimensions may not be available: {str(e)}")
            return pd.DataFrame()
        except Exception as e:
            self.logger.error(f"Failed to fetch dimensions: {str(e)}")
            return pd.DataFrame()

    def _fetch_dataview_info(self, data_view_id: str) -> dict:
        """Fetch data view information with error handling and retry"""
        try:
            self.logger.debug(f"Fetching data view information for {data_view_id}")

            # Use retry for transient network errors
            lookup_data = make_api_call_with_retry(
                self.cja.getDataView,
                data_view_id,
                logger=self.logger,
                operation_name="getDataView"
            )

            if not lookup_data:
                self.logger.error("Data view information returned empty")
                return {"name": "Unknown", "id": data_view_id}

            self.logger.info(f"Successfully fetched data view info: {lookup_data.get('name', 'Unknown')}")
            return lookup_data

        except Exception as e:
            self.logger.error(f"Failed to fetch data view information: {str(e)}")
            return {"name": "Unknown", "id": data_view_id, "error": str(e)}

# ==================== DATA QUALITY VALIDATION ====================

class DataQualityChecker:
    # Severity levels in priority order (highest to lowest) for proper sorting
    SEVERITY_ORDER = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO']

    def __init__(self, logger: logging.Logger, validation_cache: Optional[ValidationCache] = None,
                 quiet: bool = False):
        self.issues = []
        self.logger = logger
        self.validation_cache = validation_cache  # Optional cache for performance
        self._issues_lock = threading.Lock()  # Thread safety for parallel validation
        self.quiet = quiet
    
    def add_issue(self, severity: str, category: str, item_type: str,
                  item_name: str, description: str, details: str = ""):
        """Add a data quality issue to the tracker (thread-safe)"""
        issue = {
            'Severity': severity,
            'Category': category,
            'Type': item_type,
            'Item Name': item_name,
            'Issue': description,
            'Details': details
        }

        # Thread-safe append operation
        with self._issues_lock:
            self.issues.append(issue)

        # Conditional logging based on log level for performance
        # Only log individual issues in DEBUG mode
        if self.logger.isEnabledFor(logging.DEBUG):
            self.logger.debug(f"DQ Issue [{severity}] - {item_type}: {description}")
        elif severity in ['CRITICAL', 'HIGH'] and self.logger.isEnabledFor(logging.WARNING):
            # In non-DEBUG modes, only log CRITICAL/HIGH severity issues
            self.logger.warning(f"DQ Issue [{severity}] - {item_type}: {description}")
    
    def check_duplicates(self, df: pd.DataFrame, item_type: str):
        """Check for duplicate names in metrics or dimensions"""
        try:
            if df.empty:
                self.logger.info(f"Skipping duplicate check for empty {item_type} dataframe")
                return
            
            if 'name' not in df.columns:
                self.logger.warning(f"'name' column not found in {item_type}. Skipping duplicate check.")
                return
            
            duplicates = df['name'].value_counts()
            duplicates = duplicates[duplicates > 1]
            
            for name, count in duplicates.items():
                self.add_issue(
                    severity='HIGH',
                    category='Duplicates',
                    item_type=item_type,
                    item_name=str(name),
                    description=f'Duplicate name found {count} times',
                    details=f'This {item_type.lower()} name appears {count} times in the data view'
                )
        except Exception as e:
            self.logger.error(_format_error_msg("checking duplicates", item_type, e))
    
    def check_required_fields(self, df: pd.DataFrame, item_type: str, 
                            required_fields: List[str]):
        """Validate that required fields are present"""
        try:
            if df.empty:
                self.logger.info(f"Skipping required fields check for empty {item_type} dataframe")
                return
            
            missing_fields = [field for field in required_fields if field not in df.columns]
            
            if missing_fields:
                self.add_issue(
                    severity='CRITICAL',
                    category='Missing Fields',
                    item_type=item_type,
                    item_name='N/A',
                    description=f'Required fields missing from API response',
                    details=f'Missing fields: {", ".join(missing_fields)}'
                )
        except Exception as e:
            self.logger.error(_format_error_msg("checking required fields", item_type, e))
    
    def check_null_values(self, df: pd.DataFrame, item_type: str, 
                         critical_fields: List[str]):
        """Check for null values in critical fields"""
        try:
            if df.empty:
                self.logger.info(f"Skipping null value check for empty {item_type} dataframe")
                return
            
            for field in critical_fields:
                if field in df.columns:
                    null_count = df[field].isna().sum()
                    if null_count > 0:
                        null_items = df[df[field].isna()]['name'].tolist() if 'name' in df.columns else []
                        self.add_issue(
                            severity='MEDIUM',
                            category='Null Values',
                            item_type=item_type,
                            item_name=', '.join(str(x) for x in null_items),
                            description=f'Null values in "{field}" field',
                            details=f'{null_count} item(s) missing {field}. Items: {", ".join(str(x) for x in null_items)}'
                        )
        except Exception as e:
            self.logger.error(_format_error_msg("checking null values", item_type, e))
    
    def check_missing_descriptions(self, df: pd.DataFrame, item_type: str):
        """Check for items without descriptions"""
        try:
            if df.empty:
                self.logger.info(f"Skipping description check for empty {item_type} dataframe")
                return
            
            if 'description' not in df.columns:
                self.logger.info(f"'description' column not found in {item_type}")
                return
            
            missing_desc = df[df['description'].isna() | (df['description'] == '')]
            
            if len(missing_desc) > 0:
                item_names = missing_desc['name'].tolist() if 'name' in missing_desc.columns else []
                self.add_issue(
                    severity='LOW',
                    category='Missing Descriptions',
                    item_type=item_type,
                    item_name=f'{len(missing_desc)} items',
                    description=f'{len(missing_desc)} items without descriptions',
                    details=f'Items: {", ".join(str(x) for x in item_names)}'
                )
        except Exception as e:
            self.logger.error(_format_error_msg("checking descriptions", item_type, e))
    
    def check_empty_dataframe(self, df: pd.DataFrame, item_type: str):
        """Check if dataframe is empty"""
        try:
            if df.empty:
                self.add_issue(
                    severity='CRITICAL',
                    category='Empty Data',
                    item_type=item_type,
                    item_name='N/A',
                    description=f'No {item_type.lower()} found in data view',
                    details=f'The API returned an empty dataset for {item_type.lower()}'
                )
        except Exception as e:
            self.logger.error(_format_error_msg("checking if dataframe is empty", item_type, e))
    
    def check_id_validity(self, df: pd.DataFrame, item_type: str):
        """Check for missing or invalid IDs"""
        try:
            if df.empty:
                self.logger.info(f"Skipping ID validity check for empty {item_type} dataframe")
                return
            
            if 'id' not in df.columns:
                self.logger.warning(f"'id' column not found in {item_type}")
                return
            
            missing_ids = df[df['id'].isna() | (df['id'] == '')]
            if len(missing_ids) > 0:
                self.add_issue(
                    severity='HIGH',
                    category='Invalid IDs',
                    item_type=item_type,
                    item_name=f'{len(missing_ids)} items',
                    description=f'{len(missing_ids)} items with missing or invalid IDs',
                    details='Items without valid IDs may cause issues in reporting'
                )
        except Exception as e:
            self.logger.error(_format_error_msg("checking ID validity", item_type, e))
    
    def check_all_quality_issues_optimized(self, df: pd.DataFrame, item_type: str,
                                           required_fields: List[str],
                                           critical_fields: List[str]):
        """
        Optimized single-pass validation combining all checks

        PERFORMANCE OPTIMIZATIONS:
        - 40-55% faster than sequential individual checks
        - Reduces DataFrame scans from 6 to 1
        - Uses vectorized pandas operations
        - Early exit on critical errors (5-10% additional improvement)
        - Validation caching (50-90% improvement on cache hits)
        - Better CPU cache utilization

        Args:
            df: DataFrame to validate (metrics or dimensions)
            item_type: Type of items ('Metrics' or 'Dimensions')
            required_fields: Fields that must be present in the DataFrame
            critical_fields: Fields to check for null values

        Early Exit Conditions:
            - Cache hit: Returns cached results immediately
            - Empty DataFrame: Exits immediately
            - Missing required fields: Exits after logging critical error
        """
        try:
            # Check cache first (before any processing)
            # get() returns (issues, cache_key) - reuse cache_key in put() to avoid rehashing
            cache_key = None
            if self.validation_cache is not None:
                cached_issues, cache_key = self.validation_cache.get(
                    df, item_type, required_fields, critical_fields
                )
                if cached_issues is not None:
                    # Cache hit - add issues to tracker and return
                    with self._issues_lock:
                        self.issues.extend(cached_issues)
                    self.logger.debug(f"Using cached validation results for {item_type}")
                    return

            # Track where validation starts (for caching results at the end)
            issues_start_index = len(self.issues)

            # Check 1: Empty DataFrame (quick exit)
            if df.empty:
                self.add_issue(
                    severity='CRITICAL',
                    category='Empty Data',
                    item_type=item_type,
                    item_name='N/A',
                    description=f'No {item_type.lower()} found in data view',
                    details=f'The API returned an empty dataset for {item_type.lower()}'
                )
                # Cache the result before returning (reuse cache_key to avoid rehashing)
                if self.validation_cache is not None:
                    new_issues = self.issues[issues_start_index:]
                    self.validation_cache.put(df, item_type, required_fields, critical_fields, new_issues, cache_key)
                return

            # Check 2: Required fields validation (no iteration needed)
            missing_fields = [field for field in required_fields if field not in df.columns]
            if missing_fields:
                self.add_issue(
                    severity='CRITICAL',
                    category='Missing Fields',
                    item_type=item_type,
                    item_name='N/A',
                    description='Required fields missing from API response',
                    details=f'Missing fields: {", ".join(missing_fields)}'
                )
                # Cache the critical error result before returning (reuse cache_key)
                if self.validation_cache is not None:
                    new_issues = self.issues[issues_start_index:]
                    self.validation_cache.put(df, item_type, required_fields, critical_fields, new_issues, cache_key)
                return  # Early exit: cannot proceed without required fields

            # Check 3: Vectorized duplicate detection
            if 'name' in df.columns:
                duplicates = df['name'].value_counts()
                duplicates = duplicates[duplicates > 1]

                for name, count in duplicates.items():
                    self.add_issue(
                        severity='HIGH',
                        category='Duplicates',
                        item_type=item_type,
                        item_name=str(name),
                        description=f'Duplicate name found {count} times',
                        details=f'This {item_type.lower()} name appears {count} times in the data view'
                    )

            # Check 4: Vectorized null value checks (single operation for all fields)
            available_critical_fields = [f for f in critical_fields if f in df.columns]
            if available_critical_fields:
                # Single vectorized operation instead of looping
                null_counts = df[available_critical_fields].isna().sum()

                for field, null_count in null_counts[null_counts > 0].items():
                    null_items = df[df[field].isna()]['name'].tolist() if 'name' in df.columns else []
                    self.add_issue(
                        severity='MEDIUM',
                        category='Null Values',
                        item_type=item_type,
                        item_name=', '.join(str(x) for x in null_items),
                        description=f'Null values in "{field}" field',
                        details=f'{null_count} item(s) missing {field}. Items: {", ".join(str(x) for x in null_items)}'
                    )

            # Check 5: Vectorized missing descriptions check
            if 'description' in df.columns:
                missing_desc = df[df['description'].isna() | (df['description'] == '')]

                if len(missing_desc) > 0:
                    item_names = missing_desc['name'].tolist() if 'name' in missing_desc.columns else []
                    self.add_issue(
                        severity='LOW',
                        category='Missing Descriptions',
                        item_type=item_type,
                        item_name=f'{len(missing_desc)} items',
                        description=f'{len(missing_desc)} items without descriptions',
                        details=f'Items: {", ".join(str(x) for x in item_names)}'
                    )

            # Check 6: Vectorized ID validity check
            if 'id' in df.columns:
                missing_ids = df[df['id'].isna() | (df['id'] == '')]

                if len(missing_ids) > 0:
                    self.add_issue(
                        severity='HIGH',
                        category='Invalid IDs',
                        item_type=item_type,
                        item_name=f'{len(missing_ids)} items',
                        description=f'{len(missing_ids)} items with missing or invalid IDs',
                        details='Items without valid IDs may cause issues in reporting'
                    )

            if self.logger.isEnabledFor(logging.DEBUG):
                self.logger.debug(f"Optimized validation complete for {item_type}: {len(df)} items checked")

            # Store results in cache after successful validation (reuse cache_key to avoid rehashing)
            if self.validation_cache is not None:
                new_issues = self.issues[issues_start_index:]
                self.validation_cache.put(df, item_type, required_fields, critical_fields, new_issues, cache_key)

        except Exception as e:
            self.logger.error(_format_error_msg("in optimized validation", item_type, e))
            self.logger.exception("Full error details:")

    def check_all_parallel(self,
                          metrics_df: pd.DataFrame,
                          dimensions_df: pd.DataFrame,
                          metrics_required_fields: List[str],
                          dimensions_required_fields: List[str],
                          critical_fields: List[str],
                          max_workers: int = 2):
        """
        Run validation checks in parallel for metrics and dimensions

        PERFORMANCE: 10-15% faster than sequential validation
        - Uses ThreadPoolExecutor to validate metrics and dimensions concurrently
        - Thread-safe issue collection using locks
        - Maintains identical validation results to sequential method

        Args:
            metrics_df: DataFrame containing metrics data
            dimensions_df: DataFrame containing dimensions data
            metrics_required_fields: Required fields for metrics validation
            dimensions_required_fields: Required fields for dimensions validation
            critical_fields: Fields to check for null values (shared across both)
            max_workers: Number of worker threads (default: 2, one for metrics, one for dimensions)

        Returns:
            None (issues are stored in self.issues)

        Thread Safety:
            - Uses self._issues_lock to protect shared self.issues list
            - Each validation task runs independently on separate DataFrames
            - Logging module is inherently thread-safe
        """
        try:
            self.logger.info("Starting parallel validation (metrics and dimensions)")

            # Define validation tasks
            tasks = {
                'metrics': lambda: self.check_all_quality_issues_optimized(
                    metrics_df, 'Metrics', metrics_required_fields, critical_fields
                ),
                'dimensions': lambda: self.check_all_quality_issues_optimized(
                    dimensions_df, 'Dimensions', dimensions_required_fields, critical_fields
                )
            }

            # Execute validations in parallel
            with ThreadPoolExecutor(max_workers=max_workers) as executor:
                # Submit all validation tasks
                future_to_name = {
                    executor.submit(task): name
                    for name, task in tasks.items()
                }

                # Collect results as they complete with progress indicator
                with tqdm(
                    total=len(tasks),
                    desc="Validating data",
                    unit="check",
                    bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}]",
                    leave=False,
                    disable=self.quiet
                ) as pbar:
                    for future in as_completed(future_to_name):
                        task_name = future_to_name[future]
                        try:
                            future.result()  # This will re-raise any exception from the task
                            pbar.set_postfix_str(f"✓ {task_name}", refresh=True)
                            self.logger.debug(f"✓ {task_name.capitalize()} validation completed")
                        except Exception as e:
                            pbar.set_postfix_str(f"✗ {task_name}", refresh=True)
                            self.logger.error(f"✗ {task_name.capitalize()} validation failed: {e}")
                            self.logger.exception("Full error details:")
                        pbar.update(1)

            self.logger.info(f"Parallel validation complete. Found {len(self.issues)} issue(s)")

        except Exception as e:
            self.logger.error(_format_error_msg("in parallel validation", error=e))
            self.logger.exception("Full error details:")
            raise

    def get_issues_dataframe(self, max_issues: int = 0) -> pd.DataFrame:
        """Return all issues as a DataFrame sorted by severity (CRITICAL first)

        Args:
            max_issues: Maximum number of issues to return (0 = all issues)
        """
        try:
            if not self.issues:
                self.logger.info("No data quality issues found")
                return pd.DataFrame({
                    'Severity': ['INFO'],
                    'Category': ['Data Quality'],
                    'Type': ['All'],
                    'Item Name': ['N/A'],
                    'Issue': ['No data quality issues detected'],
                    'Details': ['All validation checks passed successfully']
                })

            df = pd.DataFrame(self.issues)

            # Use CategoricalDtype for proper severity ordering (CRITICAL > HIGH > MEDIUM > LOW > INFO)
            severity_dtype = pd.CategoricalDtype(categories=self.SEVERITY_ORDER, ordered=True)
            df['Severity'] = df['Severity'].astype(severity_dtype)

            # Reorder columns: Severity first for better readability
            preferred_order = ['Severity', 'Category', 'Type', 'Item Name', 'Issue', 'Details']
            existing_cols = [col for col in preferred_order if col in df.columns]
            other_cols = [col for col in df.columns if col not in preferred_order]
            df = df[existing_cols + other_cols]

            # Sort by severity (ascending=True with ordered categorical puts CRITICAL first)
            # then by Category alphabetically
            df = df.sort_values(
                by=['Severity', 'Category'],
                ascending=[True, True]
            )

            # Limit to top N issues if max_issues > 0
            if max_issues > 0 and len(df) > max_issues:
                self.logger.info(f"Limiting data quality issues to top {max_issues} (of {len(df)} total)")
                df = df.head(max_issues)

            return df
        except Exception as e:
            self.logger.error(_format_error_msg("creating issues dataframe", error=e))
            return pd.DataFrame({
                'Severity': ['ERROR'],
                'Category': ['System'],
                'Type': ['Processing'],
                'Item Name': ['N/A'],
                'Issue': ['Error generating data quality report'],
                'Details': [str(e)]
            })

    def log_summary(self):
        """Log aggregated summary of data quality issues for performance

        Instead of logging each individual issue (which can be 100+ log entries),
        this method logs a concise summary with counts by severity.
        Individual issue details are still captured in self.issues list.
        """
        if not self.issues:
            self.logger.info("✓ No data quality issues found")
            return

        # Aggregate by severity
        severity_counts = {}
        for issue in self.issues:
            sev = issue['Severity']
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        # Log summary
        self.logger.info(f"Data quality validation complete: {len(self.issues)} issue(s) found")

        # Log severity breakdown at INFO level
        if self.logger.isEnabledFor(logging.INFO):
            for sev in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:
                if sev in severity_counts:
                    self.logger.info(f"  {sev}: {severity_counts[sev]}")

# ==================== EXCEL GENERATION ====================

class ExcelFormatCache:
    """Cache for Excel format objects to avoid recreating identical formats.

    xlsxwriter creates a new format object for each add_format() call, even if
    the properties are identical. This class caches formats by their properties
    to reuse them across multiple sheets, improving performance by 15-25% for
    workbooks with multiple sheets.

    Usage:
        cache = ExcelFormatCache(workbook)
        header_fmt = cache.get_format({'bold': True, 'bg_color': '#366092'})
    """

    def __init__(self, workbook):
        self.workbook = workbook
        self._cache: Dict[tuple, Any] = {}

    def get_format(self, properties: Dict[str, Any]) -> Any:
        """Get or create a format with the given properties.

        Args:
            properties: Dictionary of format properties (e.g., {'bold': True})

        Returns:
            xlsxwriter Format object
        """
        # Convert dict to a hashable key (sorted tuple of items)
        # Handle nested values by converting to string representation
        cache_key = tuple(sorted((k, str(v)) for k, v in properties.items()))

        if cache_key not in self._cache:
            self._cache[cache_key] = self.workbook.add_format(properties)

        return self._cache[cache_key]


def apply_excel_formatting(writer, df, sheet_name, logger: logging.Logger,
                           format_cache: Optional[ExcelFormatCache] = None):
    """Apply formatting to Excel sheets with error handling.

    Args:
        writer: pandas ExcelWriter object
        df: DataFrame to format
        sheet_name: Name of the sheet
        logger: Logger instance
        format_cache: Optional ExcelFormatCache for format reuse across sheets
    """
    try:
        logger.info(f"Formatting sheet: {sheet_name}")

        # Calculate row offset for Data Quality sheet (summary section at top)
        summary_rows = 0
        if sheet_name == 'Data Quality' and 'Severity' in df.columns:
            summary_rows = 7  # Title + header + 5 severity levels + blank row

        # Reorder columns for Metrics/Dimensions sheets (Name first for readability)
        if sheet_name in ('Metrics', 'Dimensions') and 'name' in df.columns:
            preferred_order = ['name', 'type', 'id', 'title', 'description']
            existing_cols = [col for col in preferred_order if col in df.columns]
            other_cols = [col for col in df.columns if col not in preferred_order]
            df = df[existing_cols + other_cols]

        # Write dataframe to sheet with offset for summary
        df.to_excel(writer, sheet_name=sheet_name, index=False, startrow=summary_rows)

        workbook = writer.book
        worksheet = writer.sheets[sheet_name]

        # Use format cache if provided, otherwise create formats directly
        # Format cache improves performance by 15-25% when formatting multiple sheets
        cache = format_cache if format_cache else ExcelFormatCache(workbook)

        # Add summary section for Data Quality sheet
        if sheet_name == 'Data Quality' and 'Severity' in df.columns:
            # Calculate severity counts
            severity_counts = df['Severity'].value_counts()

            # Summary formats (using cache for reuse)
            title_format = cache.get_format({
                'bold': True,
                'font_size': 14,
                'font_color': '#366092',
                'bottom': 2
            })
            summary_header = cache.get_format({
                'bold': True,
                'bg_color': '#D9E1F2',
                'border': 1,
                'align': 'center'
            })
            summary_cell = cache.get_format({
                'border': 1,
                'align': 'center'
            })

            # Write summary title
            worksheet.write(0, 0, "Issue Summary", title_format)
            worksheet.merge_range(0, 0, 0, 1, "Issue Summary", title_format)

            # Write summary headers
            worksheet.write(1, 0, "Severity", summary_header)
            worksheet.write(1, 1, "Count", summary_header)

            # Write severity counts in order
            severity_order = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO']
            row = 2
            total_count = 0
            for sev in severity_order:
                count = severity_counts.get(sev, 0)
                if count > 0 or sev in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:  # Always show main levels
                    worksheet.write(row, 0, sev, summary_cell)
                    worksheet.write(row, 1, int(count), summary_cell)
                    total_count += count
                    row += 1

            # Set column widths for summary
            worksheet.set_column(0, 0, 12)
            worksheet.set_column(1, 1, 8)

        # Common format definitions (cached for reuse across sheets)
        header_format = cache.get_format({
            'bold': True,
            'bg_color': '#366092',
            'font_color': 'white',
            'border': 1,
            'align': 'center',
            'text_wrap': True
        })

        grey_format = cache.get_format({
            'bg_color': '#F2F2F2',
            'border': 1,
            'text_wrap': True,
            'align': 'top',
            'valign': 'top'
        })

        white_format = cache.get_format({
            'bg_color': '#FFFFFF',
            'border': 1,
            'text_wrap': True,
            'align': 'top',
            'valign': 'top'
        })

        # Bold formats for Name column in Metrics/Dimensions sheets
        name_bold_grey = cache.get_format({
            'bg_color': '#F2F2F2',
            'border': 1,
            'text_wrap': True,
            'align': 'top',
            'valign': 'top',
            'bold': True
        })

        name_bold_white = cache.get_format({
            'bg_color': '#FFFFFF',
            'border': 1,
            'text_wrap': True,
            'align': 'top',
            'valign': 'top',
            'bold': True
        })

        # Special formats for Data Quality sheet
        if sheet_name == 'Data Quality':
            # Severity icons for visual indicators (Excel only)
            severity_icons = {
                'CRITICAL': '\u25cf',  # ● filled circle
                'HIGH': '\u25b2',      # ▲ triangle up
                'MEDIUM': '\u25a0',    # ■ filled square
                'LOW': '\u25cb',       # ○ empty circle
                'INFO': '\u2139'       # ℹ info symbol
            }

            # Row formats (for non-severity columns) - using cache
            critical_format = cache.get_format({
                'bg_color': '#FFC7CE',
                'font_color': '#9C0006',
                'border': 1,
                'text_wrap': True,
                'align': 'top',
                'valign': 'top'
            })

            high_format = cache.get_format({
                'bg_color': '#FFEB9C',
                'font_color': '#9C6500',
                'border': 1,
                'text_wrap': True,
                'align': 'top',
                'valign': 'top'
            })

            medium_format = cache.get_format({
                'bg_color': '#C6EFCE',
                'font_color': '#006100',
                'border': 1,
                'text_wrap': True,
                'align': 'top',
                'valign': 'top'
            })

            low_format = cache.get_format({
                'bg_color': '#DDEBF7',
                'font_color': '#1F4E78',
                'border': 1,
                'text_wrap': True,
                'align': 'top',
                'valign': 'top'
            })

            info_format = cache.get_format({
                'bg_color': '#E2EFDA',
                'font_color': '#375623',
                'border': 1,
                'text_wrap': True,
                'align': 'top',
                'valign': 'top'
            })

            # Bold formats for Severity column (emphasize priority) - using cache
            critical_bold = cache.get_format({
                'bg_color': '#FFC7CE',
                'font_color': '#9C0006',
                'bold': True,
                'border': 1,
                'align': 'center',
                'valign': 'vcenter'
            })

            high_bold = cache.get_format({
                'bg_color': '#FFEB9C',
                'font_color': '#9C6500',
                'bold': True,
                'border': 1,
                'align': 'center',
                'valign': 'vcenter'
            })

            medium_bold = cache.get_format({
                'bg_color': '#C6EFCE',
                'font_color': '#006100',
                'bold': True,
                'border': 1,
                'align': 'center',
                'valign': 'vcenter'
            })

            low_bold = cache.get_format({
                'bg_color': '#DDEBF7',
                'font_color': '#1F4E78',
                'bold': True,
                'border': 1,
                'align': 'center',
                'valign': 'vcenter'
            })

            info_bold = cache.get_format({
                'bg_color': '#E2EFDA',
                'font_color': '#375623',
                'bold': True,
                'border': 1,
                'align': 'center',
                'valign': 'vcenter'
            })

            # Map severity to formats
            severity_formats = {
                'CRITICAL': (critical_format, critical_bold),
                'HIGH': (high_format, high_bold),
                'MEDIUM': (medium_format, medium_bold),
                'LOW': (low_format, low_bold),
                'INFO': (info_format, info_bold)
            }
        
        # Format header row (offset by summary rows if present)
        header_row = summary_rows
        for col_num, value in enumerate(df.columns.values):
            worksheet.write(header_row, col_num, value, header_format)
        
        # Column width caps - tighter limits for Metrics/Dimensions sheets
        if sheet_name in ('Metrics', 'Dimensions'):
            # Specific column width limits for better readability
            column_width_caps = {
                'name': 40,
                'type': 20,
                'id': 35,
                'title': 40,
                'description': 55,  # Narrower than default, relies on text wrap
            }
            default_cap = 50  # Narrower default for other columns
        else:
            column_width_caps = {}
            default_cap = 100

        # Set column widths with appropriate caps
        for idx, col in enumerate(df.columns):
            series = df[col]
            col_lower = col.lower()
            max_cap = column_width_caps.get(col_lower, default_cap)
            max_len = min(
                max(
                    max(len(str(val).split('\n')[0]) for val in series) if len(series) > 0 else 0,
                    len(str(series.name))
                ) + 2,
                max_cap
            )
            worksheet.set_column(idx, idx, max_len)
        
        # Apply row formatting (offset by summary rows)
        data_start_row = summary_rows + 1  # +1 for header row
        for idx in range(len(df)):
            max_lines = max(str(val).count('\n') for val in df.iloc[idx]) + 1
            row_height = min(max_lines * 15, 400)
            excel_row = data_start_row + idx

            # Apply severity-based formatting for Data Quality sheet
            if sheet_name == 'Data Quality' and 'Severity' in df.columns:
                severity = str(df.iloc[idx]['Severity'])
                row_format, bold_format = severity_formats.get(
                    severity, (low_format, low_bold)
                )

                # Set row height and default format
                worksheet.set_row(excel_row, row_height, row_format)

                # Write Severity column with icon and bold format
                severity_col_idx = df.columns.get_loc('Severity')
                icon = severity_icons.get(severity, '')
                worksheet.write(excel_row, severity_col_idx, f"{icon} {severity}", bold_format)
            else:
                row_format = grey_format if idx % 2 == 0 else white_format
                worksheet.set_row(excel_row, row_height, row_format)

                # Apply bold Name column for Metrics/Dimensions sheets
                if sheet_name in ('Metrics', 'Dimensions') and 'name' in df.columns:
                    name_col_idx = df.columns.get_loc('name')
                    name_format = name_bold_grey if idx % 2 == 0 else name_bold_white
                    worksheet.write(excel_row, name_col_idx, df.iloc[idx]['name'], name_format)

        # Add autofilter to data table (offset by summary rows)
        worksheet.autofilter(summary_rows, 0, summary_rows + len(df), len(df.columns) - 1)

        # Freeze header row (summary + data header visible when scrolling)
        worksheet.freeze_panes(summary_rows + 1, 0)
        
        logger.info(f"Successfully formatted sheet: {sheet_name}")
        
    except Exception as e:
        logger.error(_format_error_msg(f"formatting sheet {sheet_name}", error=e))
        raise

# ==================== OUTPUT FORMAT WRITERS ====================

def write_csv_output(
    data_dict: Dict[str, pd.DataFrame],
    base_filename: str,
    output_dir: Union[str, Path],
    logger: logging.Logger
) -> str:
    """
    Write data to CSV files (one per sheet)

    Args:
        data_dict: Dictionary mapping sheet names to DataFrames
        base_filename: Base filename without extension
        output_dir: Output directory path
        logger: Logger instance

    Returns:
        Path to output directory containing CSV files
    """
    try:
        logger.info("Generating CSV output...")

        # Create subdirectory for CSV files
        csv_dir = os.path.join(output_dir, f"{base_filename}_csv")
        os.makedirs(csv_dir, exist_ok=True)

        # Write each DataFrame to a separate CSV file
        for sheet_name, df in data_dict.items():
            csv_file = os.path.join(csv_dir, f"{sheet_name.replace(' ', '_').lower()}.csv")
            df.to_csv(csv_file, index=False, encoding='utf-8')
            logger.info(f"  ✓ Created CSV: {os.path.basename(csv_file)}")

        logger.info(f"CSV files created in: {csv_dir}")
        return csv_dir

    except PermissionError as e:
        logger.error(f"Permission denied creating CSV files: {e}")
        logger.error("Check write permissions for the output directory")
        raise
    except OSError as e:
        logger.error(f"OS error creating CSV files: {e}")
        logger.error("Check disk space and path validity")
        raise
    except Exception as e:
        logger.error(_format_error_msg("creating CSV files", error=e))
        raise


def write_json_output(
    data_dict: Dict[str, pd.DataFrame],
    metadata_dict: Dict[str, Any],
    base_filename: str,
    output_dir: Union[str, Path],
    logger: logging.Logger
) -> str:
    """
    Write data to JSON format with hierarchical structure

    Args:
        data_dict: Dictionary mapping sheet names to DataFrames
        metadata_dict: Metadata information
        base_filename: Base filename without extension
        output_dir: Output directory path
        logger: Logger instance

    Returns:
        Path to JSON output file
    """
    try:
        logger.info("Generating JSON output...")

        # Build JSON structure
        json_data = {
            "metadata": metadata_dict,
            "data_view": {},
            "metrics": [],
            "dimensions": [],
            "data_quality": []
        }

        # Convert DataFrames to JSON-serializable format
        for sheet_name, df in data_dict.items():
            # Convert DataFrame to list of dictionaries
            records = df.to_dict(orient='records')

            # Map to appropriate section
            if sheet_name == "Data Quality":
                json_data["data_quality"] = records
            elif sheet_name == "Metrics":
                json_data["metrics"] = records
            elif sheet_name == "Dimensions":
                json_data["dimensions"] = records
            elif sheet_name == "DataView Details":
                # For single-record sheets, store as object not array
                json_data["data_view"] = records[0] if records else {}

        # Write JSON file
        json_file = os.path.join(output_dir, f"{base_filename}.json")
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)

        logger.info(f"✓ JSON file created: {json_file}")
        return json_file

    except PermissionError as e:
        logger.error(f"Permission denied creating JSON file: {e}")
        logger.error("Check write permissions for the output directory")
        raise
    except OSError as e:
        logger.error(f"OS error creating JSON file: {e}")
        logger.error("Check disk space and path validity")
        raise
    except (TypeError, ValueError) as e:
        logger.error(f"JSON serialization error: {e}")
        logger.error("Data contains non-serializable values")
        raise
    except Exception as e:
        logger.error(_format_error_msg("creating JSON file", error=e))
        raise


def write_html_output(
    data_dict: Dict[str, pd.DataFrame],
    metadata_dict: Dict[str, Any],
    base_filename: str,
    output_dir: Union[str, Path],
    logger: logging.Logger
) -> str:
    """
    Write data to HTML format with professional styling

    Args:
        data_dict: Dictionary mapping sheet names to DataFrames
        metadata_dict: Metadata information
        base_filename: Base filename without extension
        output_dir: Output directory path
        logger: Logger instance

    Returns:
        Path to HTML output file
    """
    try:
        logger.info("Generating HTML output...")

        # Build HTML content
        html_parts = []

        # HTML header with CSS
        html_parts.append('''
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>CJA Solution Design Reference</title>
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
            margin-bottom: 30px;
        }
        h2 {
            color: #34495e;
            margin-top: 40px;
            margin-bottom: 20px;
            border-left: 4px solid #3498db;
            padding-left: 15px;
        }
        .metadata {
            background-color: #ecf0f1;
            padding: 20px;
            border-radius: 5px;
            margin-bottom: 30px;
        }
        .metadata-item {
            margin: 8px 0;
            display: flex;
            align-items: baseline;
        }
        .metadata-label {
            font-weight: bold;
            min-width: 200px;
            color: #2c3e50;
        }
        .metadata-value {
            color: #555;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 14px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        thead {
            background-color: #3498db;
            color: white;
        }
        th {
            padding: 12px;
            text-align: left;
            font-weight: 600;
            position: sticky;
            top: 0;
        }
        td {
            padding: 10px 12px;
            border-bottom: 1px solid #ddd;
        }
        tbody tr:nth-child(even) {
            background-color: #f8f9fa;
        }
        tbody tr:hover {
            background-color: #e8f4f8;
        }
        .severity-CRITICAL {
            background-color: #e74c3c !important;
            color: white;
            font-weight: bold;
        }
        .severity-HIGH {
            background-color: #e67e22 !important;
            color: white;
        }
        .severity-MEDIUM {
            background-color: #f39c12 !important;
            color: white;
        }
        .severity-LOW {
            background-color: #95a5a6 !important;
            color: white;
        }
        .severity-INFO {
            background-color: #3498db !important;
            color: white;
        }
        .section {
            margin-bottom: 50px;
        }
        .footer {
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            text-align: center;
            color: #7f8c8d;
            font-size: 12px;
        }
        @media print {
            body {
                background-color: white;
            }
            .container {
                box-shadow: none;
            }
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>📊 CJA Solution Design Reference</h1>
        ''')

        # Metadata section
        html_parts.append('<div class="metadata">')
        html_parts.append('<h2>📋 Metadata</h2>')
        for key, value in metadata_dict.items():
            safe_value = str(value).replace('<', '&lt;').replace('>', '&gt;')
            html_parts.append(f'''
            <div class="metadata-item">
                <span class="metadata-label">{key}:</span>
                <span class="metadata-value">{safe_value}</span>
            </div>
            ''')
        html_parts.append('</div>')

        # Data sections
        section_icons = {
            "Data Quality": "🔍",
            "DataView Details": "📊",
            "Metrics": "📈",
            "Dimensions": "📐"
        }

        for sheet_name, df in data_dict.items():
            if df.empty:
                continue

            icon = section_icons.get(sheet_name, "📄")
            html_parts.append(f'<div class="section">')
            html_parts.append(f'<h2>{icon} {sheet_name}</h2>')

            # Convert DataFrame to HTML with custom styling
            df_html = df.to_html(index=False, escape=False, classes='data-table')

            # Add severity-based row classes for Data Quality sheet
            if sheet_name == "Data Quality" and 'Severity' in df.columns:
                rows = df_html.split('<tr>')
                styled_rows = [rows[0]]  # Keep header

                for i, row in enumerate(rows[1:], 1):
                    if i <= len(df):
                        severity = df.iloc[i-1]['Severity'] if i-1 < len(df) else ''
                        if severity in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO']:
                            row = f'<tr class="severity-{severity}">' + row.split('>', 1)[1]
                        else:
                            row = '<tr>' + row
                        styled_rows.append(row)

                df_html = ''.join(styled_rows)

            html_parts.append(df_html)
            html_parts.append('</div>')

        # Footer
        html_parts.append(f'''
        <div class="footer">
            <p>Generated by CJA SDR Generator v{__version__}</p>
            <p>Generated at {metadata_dict.get("Generated At", "N/A")}</p>
        </div>
    </div>
</body>
</html>
        ''')

        # Write HTML file
        html_file = os.path.join(output_dir, f"{base_filename}.html")
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(html_parts))

        logger.info(f"✓ HTML file created: {html_file}")
        return html_file

    except PermissionError as e:
        logger.error(f"Permission denied creating HTML file: {e}")
        logger.error("Check write permissions for the output directory")
        raise
    except OSError as e:
        logger.error(f"OS error creating HTML file: {e}")
        logger.error("Check disk space and path validity")
        raise
    except Exception as e:
        logger.error(_format_error_msg("creating HTML file", error=e))
        raise


def write_markdown_output(
    data_dict: Dict[str, pd.DataFrame],
    metadata_dict: Dict[str, Any],
    base_filename: str,
    output_dir: Union[str, Path],
    logger: logging.Logger
) -> str:
    """
    Write data to Markdown format for GitHub, Confluence, and other platforms

    Features:
    - GitHub-flavored markdown tables
    - Table of contents with section links
    - Collapsible sections for large tables
    - Proper escaping of special characters
    - Issue summary for Data Quality

    Args:
        data_dict: Dictionary mapping sheet names to DataFrames
        metadata_dict: Metadata information
        base_filename: Base filename without extension
        output_dir: Output directory path
        logger: Logger instance

    Returns:
        Path to Markdown output file
    """
    try:
        logger.info("Generating Markdown output...")

        def escape_markdown(text: str) -> str:
            """Escape special markdown characters in table cells"""
            if pd.isna(text) or text is None:
                return ""
            text = str(text)
            # Escape pipe characters that would break tables
            text = text.replace('|', '\\|')
            # Escape backticks
            text = text.replace('`', '\\`')
            # Replace newlines with spaces in table cells
            text = text.replace('\n', ' ')
            text = text.replace('\r', ' ')
            return text.strip()

        def df_to_markdown_table(df: pd.DataFrame, sheet_name: str) -> str:
            """Convert DataFrame to markdown table format.

            Uses vectorized operations instead of iterrows() for better performance
            on large DataFrames (20-40% faster for datasets with 100+ rows).
            """
            if df.empty:
                return f"\n*No {sheet_name.lower()} found.*\n"

            # Header row
            headers = [escape_markdown(col) for col in df.columns]
            header_row = '| ' + ' | '.join(headers) + ' |'

            # Separator row with left alignment
            separator_row = '| ' + ' | '.join(['---'] * len(headers)) + ' |'

            # Data rows - vectorized approach using apply() instead of iterrows()
            # This avoids the overhead of creating Series objects for each row
            def format_row(row: pd.Series) -> str:
                cells = [escape_markdown(row[col]) for col in df.columns]
                return '| ' + ' | '.join(cells) + ' |'

            data_rows = df.apply(format_row, axis=1).tolist()

            return '\n'.join([header_row, separator_row] + data_rows)

        md_parts = []

        # Title
        md_parts.append("# 📊 CJA Solution Design Reference\n")

        # Metadata section
        md_parts.append("## 📋 Metadata\n")
        if metadata_dict:
            for key, value in metadata_dict.items():
                md_parts.append(f"**{key}:** {escape_markdown(str(value))}")
            md_parts.append("")

        # Table of contents
        md_parts.append("## 📑 Table of Contents\n")
        toc_items = []
        for sheet_name in data_dict.keys():
            # Create anchor-safe links
            anchor = sheet_name.lower().replace(' ', '-').replace('_', '-')
            toc_items.append(f"- [{sheet_name}](#{anchor})")
        md_parts.append('\n'.join(toc_items))
        md_parts.append("\n---\n")

        # Process each sheet
        for sheet_name, df in data_dict.items():
            md_parts.append(f"## {sheet_name}\n")

            # Add special handling for Data Quality sheet
            if sheet_name == 'Data Quality' and not df.empty and 'Severity' in df.columns:
                # Add issue summary
                severity_counts = df['Severity'].value_counts()
                md_parts.append("### Issue Summary\n")
                md_parts.append("| Severity | Count |")
                md_parts.append("| --- | --- |")

                severity_order = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO']
                for sev in severity_order:
                    count = severity_counts.get(sev, 0)
                    if count > 0 or sev in ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW']:
                        emoji = {'CRITICAL': '🔴', 'HIGH': '🟠', 'MEDIUM': '🟡', 'LOW': '⚪', 'INFO': '🔵'}.get(sev, '')
                        md_parts.append(f"| {emoji} {sev} | {count} |")
                md_parts.append("")

            # For large tables (>50 rows), use collapsible sections
            if len(df) > 50:
                md_parts.append(f"<details>")
                md_parts.append(f"<summary>View {len(df)} rows (click to expand)</summary>\n")
                md_parts.append(df_to_markdown_table(df, sheet_name))
                md_parts.append("\n</details>\n")
            else:
                # For smaller tables, show directly
                md_parts.append(df_to_markdown_table(df, sheet_name))
                md_parts.append("")

            # Add counts
            md_parts.append(f"*Total {sheet_name}: {len(df)} items*\n")
            md_parts.append("---\n")

        # Footer
        md_parts.append("---")
        md_parts.append("*Generated by CJA Auto SDR Generator*")

        # Write to file
        markdown_file = os.path.join(output_dir, f"{base_filename}.md")
        with open(markdown_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(md_parts))

        logger.info(f"✓ Markdown file created: {markdown_file}")
        return markdown_file

    except PermissionError as e:
        logger.error(f"Permission denied creating Markdown file: {e}")
        logger.error("Check write permissions for the output directory")
        raise
    except OSError as e:
        logger.error(f"OS error creating Markdown file: {e}")
        logger.error("Check disk space and path validity")
        raise
    except Exception as e:
        logger.error(_format_error_msg("creating Markdown file", error=e))
        raise


# ==================== DIFF COMPARISON OUTPUT WRITERS ====================

# ANSI color codes for terminal output
class ANSIColors:
    """ANSI escape codes for colored terminal output."""
    GREEN = '\033[92m'   # Added
    RED = '\033[91m'     # Removed
    YELLOW = '\033[93m'  # Modified
    CYAN = '\033[96m'    # Info/headers
    BOLD = '\033[1m'
    RESET = '\033[0m'
    # Regex to strip ANSI escape codes for visible length calculation
    ANSI_ESCAPE = re.compile(r'\033\[[0-9;]*m')

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

    @classmethod
    def visible_len(cls, text: str) -> int:
        """Return the visible length of a string, ignoring ANSI escape codes."""
        return len(cls.ANSI_ESCAPE.sub('', text))

    @classmethod
    def rjust(cls, text: str, width: int) -> str:
        """Right-justify a string accounting for ANSI escape codes."""
        visible = cls.visible_len(text)
        padding = max(0, width - visible)
        return ' ' * padding + text

    @classmethod
    def ljust(cls, text: str, width: int) -> str:
        """Left-justify a string accounting for ANSI escape codes."""
        visible = cls.visible_len(text)
        padding = max(0, width - visible)
        return text + ' ' * padding


def write_diff_console_output(diff_result: DiffResult, changes_only: bool = False,
                               summary_only: bool = False, side_by_side: bool = False,
                               use_color: bool = True) -> str:
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

    lines.append(f"{'':20s} {src_header:>{src_width}s} {tgt_header:>{tgt_width}s} {'Added':>10s} {'Removed':>10s} {'Modified':>10s} {'Unchanged':>12s} {'Changed':>12s}")
    lines.append("-" * total_width)

    # Metrics row with percentage (using ANSI-aware padding for colored strings)
    metrics_pct = f"({summary.metrics_change_percent:.1f}%)"
    added_str = ANSIColors.green(f"+{summary.metrics_added}", c) if summary.metrics_added else f"+{summary.metrics_added}"
    removed_str = ANSIColors.red(f"-{summary.metrics_removed}", c) if summary.metrics_removed else f"-{summary.metrics_removed}"
    modified_str = ANSIColors.yellow(f"~{summary.metrics_modified}", c) if summary.metrics_modified else f"~{summary.metrics_modified}"
    lines.append(f"{'Metrics':20s} {summary.source_metrics_count:{src_width}d} {summary.target_metrics_count:{tgt_width}d} "
                f"{ANSIColors.rjust(added_str, 10)} {ANSIColors.rjust(removed_str, 10)} {ANSIColors.rjust(modified_str, 10)} {summary.metrics_unchanged:>12d} {metrics_pct:>12s}")

    # Dimensions row with percentage (using ANSI-aware padding for colored strings)
    dims_pct = f"({summary.dimensions_change_percent:.1f}%)"
    added_str = ANSIColors.green(f"+{summary.dimensions_added}", c) if summary.dimensions_added else f"+{summary.dimensions_added}"
    removed_str = ANSIColors.red(f"-{summary.dimensions_removed}", c) if summary.dimensions_removed else f"-{summary.dimensions_removed}"
    modified_str = ANSIColors.yellow(f"~{summary.dimensions_modified}", c) if summary.dimensions_modified else f"~{summary.dimensions_modified}"
    lines.append(f"{'Dimensions':20s} {summary.source_dimensions_count:{src_width}d} {summary.target_dimensions_count:{tgt_width}d} "
                f"{ANSIColors.rjust(added_str, 10)} {ANSIColors.rjust(removed_str, 10)} {ANSIColors.rjust(modified_str, 10)} {summary.dimensions_unchanged:>12d} {dims_pct:>12s}")
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
                symbol = _get_change_symbol(diff.change_type)
                colored_symbol = _get_colored_symbol(diff.change_type, c)
                lines.append(f"  [{colored_symbol}] {diff.id:{global_max_id_len}s} \"{diff.name}\"")
                if side_by_side and diff.change_type == ChangeType.MODIFIED:
                    # Side-by-side view for modified items
                    sbs_lines = _format_side_by_side(
                        diff, diff_result.source_label, diff_result.target_label
                    )
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
                symbol = _get_change_symbol(diff.change_type)
                colored_symbol = _get_colored_symbol(diff.change_type, c)
                lines.append(f"  [{colored_symbol}] {diff.id:{global_max_id_len}s} \"{diff.name}\"")
                if side_by_side and diff.change_type == ChangeType.MODIFIED:
                    # Side-by-side view for modified items
                    sbs_lines = _format_side_by_side(
                        diff, diff_result.source_label, diff_result.target_label
                    )
                    lines.extend(sbs_lines)
                else:
                    detail = _get_change_detail(diff)
                    if detail:
                        lines.append(f"      {detail}")
        else:
            lines.append("  No changes")

    # Footer with natural language summary
    lines.append("")
    lines.append("=" * 80)
    if summary.has_changes:
        lines.append(ANSIColors.cyan(f"Summary: {summary.natural_language_summary}", c))
    else:
        lines.append(ANSIColors.green("✓ No differences found", c))
    lines.append("=" * 80)

    return "\n".join(lines)


def _get_change_symbol(change_type: ChangeType) -> str:
    """Get symbol for change type"""
    symbols = {
        ChangeType.ADDED: "+",
        ChangeType.REMOVED: "-",
        ChangeType.MODIFIED: "~",
        ChangeType.UNCHANGED: " "
    }
    return symbols.get(change_type, "?")


def _get_colored_symbol(change_type: ChangeType, use_color: bool = True) -> str:
    """Get color-coded symbol for change type"""
    symbol = _get_change_symbol(change_type)
    if not use_color:
        return symbol
    if change_type == ChangeType.ADDED:
        return ANSIColors.green(symbol, use_color)
    elif change_type == ChangeType.REMOVED:
        return ANSIColors.red(symbol, use_color)
    elif change_type == ChangeType.MODIFIED:
        return ANSIColors.yellow(symbol, use_color)
    return symbol


def _format_diff_value(val: Any, truncate: bool = True, max_len: int = 30) -> str:
    """Format a value for diff display, handling None and NaN."""
    if val is None:
        return "(empty)"
    try:
        if pd.isna(val):
            return "(empty)"
    except (TypeError, ValueError):
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


def _format_side_by_side(
    diff: ComponentDiff,
    source_label: str,
    target_label: str,
    col_width: int = 35,
    max_col_width: int = 60
) -> List[str]:
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
    for field, (old_val, new_val) in diff.changed_fields.items():
        old_str = _format_diff_value(old_val, truncate=False)
        new_str = _format_diff_value(new_val, truncate=False)
        old_display = f"{field}: {old_str}"
        new_display = f"{field}: {new_str}"
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
        old_wrapped = textwrap.wrap(old_display, width=col_width) or ['']
        new_wrapped = textwrap.wrap(new_display, width=col_width) or ['']

        # Pad to same number of lines
        max_lines = max(len(old_wrapped), len(new_wrapped))
        old_wrapped.extend([''] * (max_lines - len(old_wrapped)))
        new_wrapped.extend([''] * (max_lines - len(new_wrapped)))

        # Output each line
        for old_line, new_line in zip(old_wrapped, new_wrapped):
            lines.append(f"    │ {old_line:<{col_width}} │ {new_line:<{col_width}} │")

    lines.append(f"    └{'─' * (col_width + 2)}┴{'─' * (col_width + 2)}┘")

    return lines


def write_diff_grouped_by_field_output(diff_result: DiffResult, use_color: bool = True) -> str:
    """
    Write diff output grouped by changed field instead of by component.

    Args:
        diff_result: The DiffResult to output
        use_color: Use ANSI color codes

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
    field_changes: Dict[str, List[Tuple[str, str, Any, Any]]] = {}  # field -> [(id, name, old, new), ...]

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
                if field in ('type', 'schemaPath'):
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
        lines.append(ANSIColors.red("⚠️  BREAKING CHANGES DETECTED", c))
        lines.append("-" * 40)
        for comp_id, comp_name, field, old_val, new_val in breaking_changes:
            lines.append(f"  {comp_id}: {field} changed")
            lines.append(f"    '{_format_diff_value(old_val, truncate=False)}' → '{_format_diff_value(new_val, truncate=False)}'")

    # Group by field
    lines.append("")
    lines.append(ANSIColors.bold("CHANGES BY FIELD", c))
    lines.append("-" * 80)

    for field in sorted(field_changes.keys()):
        changes = field_changes[field]
        lines.append("")
        lines.append(f"{ANSIColors.cyan(field, c)} ({len(changes)} component{'s' if len(changes) != 1 else ''}):")

        for comp_id, comp_name, old_val, new_val in changes[:10]:  # Limit to 10 per field
            old_str = _format_diff_value(old_val, truncate=True)
            new_str = _format_diff_value(new_val, truncate=True)
            lines.append(f"  {comp_id}: '{old_str}' → '{new_str}'")

        if len(changes) > 10:
            lines.append(f"  ... and {len(changes) - 10} more")

    # Added/removed summary
    added = [d for d in all_diffs if d.change_type == ChangeType.ADDED]
    removed = [d for d in all_diffs if d.change_type == ChangeType.REMOVED]

    if added:
        lines.append("")
        lines.append(ANSIColors.green(f"ADDED ({len(added)})", c))
        for diff in added[:10]:
            lines.append(f"  [+] {diff.id}")
        if len(added) > 10:
            lines.append(f"  ... and {len(added) - 10} more")

    if removed:
        lines.append("")
        lines.append(ANSIColors.red(f"REMOVED ({len(removed)})", c))
        for diff in removed[:10]:
            lines.append(f"  [-] {diff.id}")
        if len(removed) > 10:
            lines.append(f"  ... and {len(removed) - 10} more")

    lines.append("")
    lines.append("=" * 80)
    lines.append(ANSIColors.cyan(f"Summary: {summary.natural_language_summary}", c))
    lines.append("=" * 80)

    return "\n".join(lines)


def write_diff_pr_comment_output(diff_result: DiffResult, changes_only: bool = False) -> str:
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
    meta = diff_result.metadata_diff

    # Header
    lines.append("### 📊 Data View Comparison")
    lines.append("")
    lines.append(f"**{diff_result.source_label}** → **{diff_result.target_label}**")
    lines.append("")

    # Summary table
    lines.append("| Component | Source | Target | Added | Removed | Modified | Unchanged | Changed |")
    lines.append("|-----------|-------:|-------:|------:|--------:|---------:|----------:|--------:|")
    lines.append(f"| Metrics | {summary.source_metrics_count} | {summary.target_metrics_count} | "
                f"+{summary.metrics_added} | -{summary.metrics_removed} | ~{summary.metrics_modified} | "
                f"{summary.metrics_unchanged} | {summary.metrics_change_percent:.1f}% |")
    lines.append(f"| Dimensions | {summary.source_dimensions_count} | {summary.target_dimensions_count} | "
                f"+{summary.dimensions_added} | -{summary.dimensions_removed} | ~{summary.dimensions_modified} | "
                f"{summary.dimensions_unchanged} | {summary.dimensions_change_percent:.1f}% |")
    lines.append("")

    # Breaking changes warning
    breaking_changes = []
    all_diffs = diff_result.metric_diffs + diff_result.dimension_diffs
    for diff in all_diffs:
        if diff.change_type == ChangeType.MODIFIED and diff.changed_fields:
            for field in diff.changed_fields:
                if field in ('type', 'schemaPath'):
                    old_val, new_val = diff.changed_fields[field]
                    breaking_changes.append((diff.id, field, old_val, new_val))

    if breaking_changes:
        lines.append("#### ⚠️ Breaking Changes Detected")
        lines.append("")
        lines.append("| Component | Field | Before | After |")
        lines.append("|-----------|-------|--------|-------|")
        for comp_id, field, old_val, new_val in breaking_changes[:10]:
            lines.append(f"| `{comp_id}` | {field} | `{_format_diff_value(old_val, truncate=False)}` | `{_format_diff_value(new_val, truncate=False)}` |")
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
            symbol = {ChangeType.ADDED: "➕", ChangeType.REMOVED: "➖", ChangeType.MODIFIED: "✏️"}.get(diff.change_type, "")
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
            symbol = {ChangeType.ADDED: "➕", ChangeType.REMOVED: "➖", ChangeType.MODIFIED: "✏️"}.get(diff.change_type, "")
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


def detect_breaking_changes(diff_result: DiffResult) -> List[Dict[str, Any]]:
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
            breaking_changes.append({
                'component_id': diff.id,
                'component_name': diff.name,
                'change_type': 'removed',
                'severity': 'high',
                'description': f"Component '{diff.name}' was removed"
            })

        # Check for type or schema changes
        elif diff.change_type == ChangeType.MODIFIED and diff.changed_fields:
            for field, (old_val, new_val) in diff.changed_fields.items():
                if field == 'type':
                    breaking_changes.append({
                        'component_id': diff.id,
                        'component_name': diff.name,
                        'change_type': 'type_changed',
                        'field': field,
                        'old_value': old_val,
                        'new_value': new_val,
                        'severity': 'high',
                        'description': f"Data type changed from '{_format_diff_value(old_val, truncate=False)}' to '{_format_diff_value(new_val, truncate=False)}'"
                    })
                elif field == 'schemaPath':
                    breaking_changes.append({
                        'component_id': diff.id,
                        'component_name': diff.name,
                        'change_type': 'schema_changed',
                        'field': field,
                        'old_value': old_val,
                        'new_value': new_val,
                        'severity': 'medium',
                        'description': f"Schema path changed from '{_format_diff_value(old_val, truncate=False)}' to '{_format_diff_value(new_val, truncate=False)}'"
                    })

    return breaking_changes


def write_diff_json_output(
    diff_result: DiffResult,
    base_filename: str,
    output_dir: Union[str, Path],
    logger: logging.Logger,
    changes_only: bool = False
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

        def serialize_component_diff(d: ComponentDiff) -> Dict:
            return {
                "id": d.id,
                "name": d.name,
                "change_type": d.change_type.value,
                "changed_fields": {k: {"source": v[0], "target": v[1]}
                                   for k, v in (d.changed_fields or {}).items()},
                "source_data": d.source_data,
                "target_data": d.target_data
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
                "target_label": diff_result.target_label
            },
            "source": {
                "id": meta.source_id,
                "name": meta.source_name,
                "owner": meta.source_owner,
                "description": meta.source_description
            },
            "target": {
                "id": meta.target_id,
                "name": meta.target_name,
                "owner": meta.target_owner,
                "description": meta.target_description
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
                "total_changes": summary.total_changes
            },
            "metric_diffs": [serialize_component_diff(d) for d in metric_diffs],
            "dimension_diffs": [serialize_component_diff(d) for d in dimension_diffs]
        }

        json_file = os.path.join(output_dir, f"{base_filename}.json")
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)

        logger.info(f"Diff JSON file created: {json_file}")
        return json_file

    except Exception as e:
        logger.error(_format_error_msg("creating diff JSON file", error=e))
        raise


def write_diff_markdown_output(
    diff_result: DiffResult,
    base_filename: str,
    output_dir: Union[str, Path],
    logger: logging.Logger,
    changes_only: bool = False,
    side_by_side: bool = False
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
        md_parts.append(f"| Component | {diff_result.source_label} | {diff_result.target_label} | Added | Removed | Modified | Unchanged | Changed |")
        md_parts.append("| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |")
        md_parts.append(f"| Metrics | {summary.source_metrics_count} | {summary.target_metrics_count} | "
                       f"+{summary.metrics_added} | -{summary.metrics_removed} | ~{summary.metrics_modified} | "
                       f"{summary.metrics_unchanged} | {summary.metrics_change_percent:.1f}% |")
        md_parts.append(f"| Dimensions | {summary.source_dimensions_count} | {summary.target_dimensions_count} | "
                       f"+{summary.dimensions_added} | -{summary.dimensions_removed} | ~{summary.dimensions_modified} | "
                       f"{summary.dimensions_unchanged} | {summary.dimensions_change_percent:.1f}% |")
        md_parts.append("")

        if not summary.has_changes:
            md_parts.append("**No differences found.**\n")
        else:
            md_parts.append(f"**Total changes:** {summary.total_changes}\n")

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
                            md_parts.extend(_format_markdown_side_by_side(
                                diff, diff_result.source_label, diff_result.target_label
                            ))
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
                            md_parts.extend(_format_markdown_side_by_side(
                                diff, diff_result.source_label, diff_result.target_label
                            ))
            else:
                md_parts.append("*No changes*")
            md_parts.append("")

        md_parts.append("---")
        md_parts.append("*Generated by CJA Auto SDR Generator*")

        markdown_file = os.path.join(output_dir, f"{base_filename}.md")
        with open(markdown_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(md_parts))

        logger.info(f"Diff Markdown file created: {markdown_file}")
        return markdown_file

    except Exception as e:
        logger.error(_format_error_msg("creating diff Markdown file", error=e))
        raise


def _get_change_emoji(change_type: ChangeType) -> str:
    """Get emoji for change type"""
    emojis = {
        ChangeType.ADDED: "+",
        ChangeType.REMOVED: "-",
        ChangeType.MODIFIED: "~",
        ChangeType.UNCHANGED: ""
    }
    return emojis.get(change_type, "")


def _format_markdown_side_by_side(
    diff: ComponentDiff,
    source_label: str,
    target_label: str
) -> List[str]:
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

    for field, (old_val, new_val) in diff.changed_fields.items():
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

        lines.append(f"| `{field}` | {old_str} | {new_str} |")

    lines.append("")
    return lines


def write_diff_html_output(
    diff_result: DiffResult,
    base_filename: str,
    output_dir: Union[str, Path],
    logger: logging.Logger,
    changes_only: bool = False
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

        summary = diff_result.summary
        meta = diff_result.metadata_diff
        html_parts = []

        # HTML header with CSS
        html_parts.append('''
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
''')

        # Metadata section
        html_parts.append(f'''
        <div class="metadata">
            <p><strong>{diff_result.source_label}:</strong> {meta.source_name} (<code>{meta.source_id}</code>)</p>
            <p><strong>{diff_result.target_label}:</strong> {meta.target_name} (<code>{meta.target_id}</code>)</p>
            <p><strong>Generated:</strong> {diff_result.generated_at}</p>
        </div>
''')

        # Summary table
        html_parts.append(f'''
        <h2>Summary</h2>
        <table class="summary-table">
            <tr>
                <th>Component</th>
                <th>{diff_result.source_label}</th>
                <th>{diff_result.target_label}</th>
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
''')

        if not summary.has_changes:
            html_parts.append('<p class="no-changes">No differences found.</p>')
        else:
            html_parts.append(f'<p class="total-changes">Total changes: {summary.total_changes}</p>')

        # Helper function to generate diff table
        def generate_diff_table(diffs: List[ComponentDiff], title: str):
            changes = [d for d in diffs if d.change_type != ChangeType.UNCHANGED]
            if not changes and changes_only:
                return ""

            html = f"<h2>{title}</h2>\n"
            if not changes:
                html += "<p><em>No changes</em></p>\n"
                return html

            html += '''<table class="diff-table">
                <tr>
                    <th>Status</th>
                    <th>ID</th>
                    <th>Name</th>
                    <th>Details</th>
                </tr>'''

            for diff in changes:
                row_class = f"row-{diff.change_type.value}"
                badge_class = f"badge-{diff.change_type.value}"
                badge_text = diff.change_type.value.upper()
                detail = _get_change_detail(diff)
                detail_escaped = detail.replace('<', '&lt;').replace('>', '&gt;')

                html += f'''
                <tr class="{row_class}">
                    <td><span class="badge {badge_class}">{badge_text}</span></td>
                    <td><code>{diff.id}</code></td>
                    <td>{diff.name}</td>
                    <td>{detail_escaped}</td>
                </tr>'''

            html += "</table>\n"
            return html

        html_parts.append(generate_diff_table(diff_result.metric_diffs, "Metrics Changes"))
        html_parts.append(generate_diff_table(diff_result.dimension_diffs, "Dimensions Changes"))

        # Footer
        html_parts.append(f'''
        <div class="footer">
            <p>Generated by CJA SDR Generator v{diff_result.tool_version}</p>
        </div>
    </div>
</body>
</html>
''')

        html_file = os.path.join(output_dir, f"{base_filename}.html")
        with open(html_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(html_parts))

        logger.info(f"Diff HTML file created: {html_file}")
        return html_file

    except Exception as e:
        logger.error(_format_error_msg("creating diff HTML file", error=e))
        raise


def write_diff_excel_output(
    diff_result: DiffResult,
    base_filename: str,
    output_dir: Union[str, Path],
    logger: logging.Logger,
    changes_only: bool = False
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

        with pd.ExcelWriter(excel_file, engine='xlsxwriter') as writer:
            workbook = writer.book

            # Define formats
            header_format = workbook.add_format({
                'bold': True, 'bg_color': '#3498db', 'font_color': 'white',
                'border': 1, 'align': 'center'
            })
            added_format = workbook.add_format({'bg_color': '#d4edda', 'border': 1})
            removed_format = workbook.add_format({'bg_color': '#f8d7da', 'border': 1})
            modified_format = workbook.add_format({'bg_color': '#fff3cd', 'border': 1})
            normal_format = workbook.add_format({'border': 1})

            # Summary sheet
            summary_data = {
                'Component': ['Metrics', 'Dimensions'],
                diff_result.source_label: [summary.source_metrics_count, summary.source_dimensions_count],
                diff_result.target_label: [summary.target_metrics_count, summary.target_dimensions_count],
                'Added': [summary.metrics_added, summary.dimensions_added],
                'Removed': [summary.metrics_removed, summary.dimensions_removed],
                'Modified': [summary.metrics_modified, summary.dimensions_modified],
                'Unchanged': [summary.metrics_unchanged, summary.dimensions_unchanged],
                'Changed %': [f"{summary.metrics_change_percent:.1f}%", f"{summary.dimensions_change_percent:.1f}%"]
            }
            summary_df = pd.DataFrame(summary_data)
            summary_df.to_excel(writer, sheet_name='Summary', index=False)

            # Metadata sheet
            metadata_data = {
                'Property': ['Source ID', 'Source Name', 'Target ID', 'Target Name',
                           'Generated At', 'Has Changes', 'Total Changes'],
                'Value': [meta.source_id, meta.source_name, meta.target_id, meta.target_name,
                         diff_result.generated_at, str(summary.has_changes), summary.total_changes]
            }
            metadata_df = pd.DataFrame(metadata_data)
            metadata_df.to_excel(writer, sheet_name='Metadata', index=False)

            # Helper function to write diff sheet
            def write_diff_sheet(diffs: List[ComponentDiff], sheet_name: str):
                if changes_only:
                    diffs = [d for d in diffs if d.change_type != ChangeType.UNCHANGED]

                if not diffs:
                    df = pd.DataFrame({'Message': ['No changes']})
                    df.to_excel(writer, sheet_name=sheet_name, index=False)
                    return

                rows = []
                for diff in diffs:
                    rows.append({
                        'Status': diff.change_type.value.upper(),
                        'ID': diff.id,
                        'Name': diff.name,
                        'Details': _get_change_detail(diff)
                    })

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
                        worksheet.write(row_idx, col_idx, df.iloc[row_idx-1, col_idx], fmt)

            write_diff_sheet(diff_result.metric_diffs, 'Metrics Diff')
            write_diff_sheet(diff_result.dimension_diffs, 'Dimensions Diff')

        logger.info(f"Diff Excel file created: {excel_file}")
        return excel_file

    except Exception as e:
        logger.error(_format_error_msg("creating diff Excel file", error=e))
        raise


def write_diff_csv_output(
    diff_result: DiffResult,
    base_filename: str,
    output_dir: Union[str, Path],
    logger: logging.Logger,
    changes_only: bool = False
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

        # Summary CSV
        summary_data = {
            'Component': ['Metrics', 'Dimensions'],
            'Source_Count': [summary.source_metrics_count, summary.source_dimensions_count],
            'Target_Count': [summary.target_metrics_count, summary.target_dimensions_count],
            'Added': [summary.metrics_added, summary.dimensions_added],
            'Removed': [summary.metrics_removed, summary.dimensions_removed],
            'Modified': [summary.metrics_modified, summary.dimensions_modified],
            'Unchanged': [summary.metrics_unchanged, summary.dimensions_unchanged],
            'Changed_Percent': [summary.metrics_change_percent, summary.dimensions_change_percent]
        }
        pd.DataFrame(summary_data).to_csv(
            os.path.join(csv_dir, 'summary.csv'), index=False
        )
        logger.info("  Created: summary.csv")

        # Metadata CSV
        metadata_data = {
            'Property': ['source_id', 'source_name', 'target_id', 'target_name',
                        'generated_at', 'has_changes', 'total_changes'],
            'Value': [meta.source_id, meta.source_name, meta.target_id, meta.target_name,
                     diff_result.generated_at, str(summary.has_changes), summary.total_changes]
        }
        pd.DataFrame(metadata_data).to_csv(
            os.path.join(csv_dir, 'metadata.csv'), index=False
        )
        logger.info("  Created: metadata.csv")

        # Helper function to write diff CSV
        def write_diff_csv(diffs: List[ComponentDiff], filename: str):
            if changes_only:
                diffs = [d for d in diffs if d.change_type != ChangeType.UNCHANGED]

            rows = []
            for diff in diffs:
                rows.append({
                    'status': diff.change_type.value,
                    'id': diff.id,
                    'name': diff.name,
                    'details': _get_change_detail(diff)
                })

            pd.DataFrame(rows).to_csv(
                os.path.join(csv_dir, filename), index=False
            )
            logger.info(f"  Created: {filename}")

        write_diff_csv(diff_result.metric_diffs, 'metrics_diff.csv')
        write_diff_csv(diff_result.dimension_diffs, 'dimensions_diff.csv')

        logger.info(f"Diff CSV files created in: {csv_dir}")
        return csv_dir

    except Exception as e:
        logger.error(_format_error_msg("creating diff CSV files", error=e))
        raise


def write_diff_output(
    diff_result: DiffResult,
    output_format: str,
    base_filename: str,
    output_dir: Union[str, Path],
    logger: logging.Logger,
    changes_only: bool = False,
    summary_only: bool = False,
    side_by_side: bool = False,
    use_color: bool = True,
    group_by_field: bool = False
) -> Optional[str]:
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

    Returns:
        Console output string (for console/pr-comment format) or None
    """
    os.makedirs(output_dir, exist_ok=True)
    output_files = []
    console_output = None

    # Handle group-by-field output mode
    if group_by_field and output_format in ['console', 'all']:
        console_output = write_diff_grouped_by_field_output(diff_result, use_color)
        print(console_output)
        if output_format == 'console':
            return console_output

    # Handle PR comment format
    if output_format == 'pr-comment':
        console_output = write_diff_pr_comment_output(diff_result, changes_only)
        print(console_output)
        return console_output

    if output_format in ['console', 'all'] and not group_by_field:
        console_output = write_diff_console_output(diff_result, changes_only, summary_only, side_by_side, use_color)
        print(console_output)

    if output_format == 'console':
        return console_output

    if output_format in ['json', 'all']:
        output_files.append(write_diff_json_output(
            diff_result, base_filename, output_dir, logger, changes_only
        ))

    if output_format in ['markdown', 'all']:
        output_files.append(write_diff_markdown_output(
            diff_result, base_filename, output_dir, logger, changes_only, side_by_side
        ))

    if output_format in ['html', 'all']:
        output_files.append(write_diff_html_output(
            diff_result, base_filename, output_dir, logger, changes_only
        ))

    if output_format in ['excel', 'all']:
        output_files.append(write_diff_excel_output(
            diff_result, base_filename, output_dir, logger, changes_only
        ))

    if output_format in ['csv', 'all']:
        output_files.append(write_diff_csv_output(
            diff_result, base_filename, output_dir, logger, changes_only
        ))

    return console_output


# ==================== REFACTORED SINGLE DATAVIEW PROCESSING ====================

def process_single_dataview(
    data_view_id: str,
    config_file: str = "config.json",
    output_dir: Union[str, Path] = ".",
    log_level: str = "INFO",
    output_format: str = "excel",
    enable_cache: bool = False,
    cache_size: int = 1000,
    cache_ttl: int = 3600,
    quiet: bool = False,
    skip_validation: bool = False,
    max_issues: int = 0,
    clear_cache: bool = False
) -> ProcessingResult:
    """
    Process a single data view and generate SDR in specified format(s)

    Args:
        data_view_id: The data view ID to process (must start with 'dv_')
        config_file: Path to CJA config file (default: 'config.json')
        output_dir: Directory to save output files (default: current directory)
        log_level: Logging level - one of DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO)
        output_format: Output format - one of excel, csv, json, html, markdown, all (default: excel)
        enable_cache: Enable validation result caching (default: False)
        cache_size: Maximum cached validation results, >= 1 (default: 1000)
        cache_ttl: Cache time-to-live in seconds, >= 1 (default: 3600)
        quiet: Suppress non-error output (default: False)
        skip_validation: Skip data quality validation for faster processing (default: False)
        max_issues: Limit data quality issues to top N by severity, >= 0; 0 = all (default: 0)
        clear_cache: Clear validation cache before processing (default: False)

    Returns:
        ProcessingResult with processing details including success status, metrics/dimensions count,
        output file path, and any error messages
    """
    start_time = time.time()

    # Setup logging for this data view
    logger = setup_logging(data_view_id, batch_mode=False, log_level=log_level)
    perf_tracker = PerformanceTracker(logger)

    try:
        # Initialize CJA
        cja = initialize_cja(config_file, logger)
        if cja is None:
            return ProcessingResult(
                data_view_id=data_view_id,
                data_view_name="Unknown",
                success=False,
                duration=time.time() - start_time,
                error_message="CJA initialization failed"
            )

        logger.info("✓ CJA connection established successfully")

        # Validate data view
        if not validate_data_view(cja, data_view_id, logger):
            return ProcessingResult(
                data_view_id=data_view_id,
                data_view_name="Unknown",
                success=False,
                duration=time.time() - start_time,
                error_message="Data view validation failed"
            )

        logger.info("✓ Data view validation complete - proceeding with data fetch")

        # Fetch data with parallel optimization
        logger.info("=" * 60)
        logger.info("Starting optimized data fetch operations")
        logger.info("=" * 60)

        fetcher = ParallelAPIFetcher(cja, logger, perf_tracker, max_workers=DEFAULT_API_FETCH_WORKERS, quiet=quiet)
        metrics, dimensions, lookup_data = fetcher.fetch_all_data(data_view_id)

        # Check if we have any data to process
        if metrics.empty and dimensions.empty:
            dv_name = lookup_data.get("name", "Unknown") if isinstance(lookup_data, dict) else "Unknown"
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
            logger.info("=" * 60)
            logger.info("EXECUTION FAILED")
            logger.info("=" * 60)
            logger.info(f"Data View: {dv_name} ({data_view_id})")
            logger.info(f"Error: No metrics or dimensions found")
            logger.info(f"Duration: {time.time() - start_time:.2f}s")
            logger.info("=" * 60)
            # Flush handlers to ensure log is written
            for handler in logger.handlers:
                handler.flush()
            return ProcessingResult(
                data_view_id=data_view_id,
                data_view_name=dv_name,
                success=False,
                duration=time.time() - start_time,
                error_message="No metrics or dimensions found - data view may be empty or inaccessible"
            )

        logger.info("Data fetch operations completed successfully")

        # Data quality validation (skip if --skip-validation flag is set)
        if skip_validation:
            logger.info("=" * 60)
            logger.info("Skipping data quality validation (--skip-validation)")
            logger.info("=" * 60)
            data_quality_df = pd.DataFrame(columns=['Severity', 'Category', 'Type', 'Item Name', 'Issue', 'Details'])
        else:
            logger.info("=" * 60)
            logger.info("Starting data quality validation (optimized)")
            logger.info("=" * 60)

            # Start performance tracking for data quality validation
            perf_tracker.start("Data Quality Validation")

            # Create validation cache if enabled
            validation_cache = None
            if enable_cache:
                validation_cache = ValidationCache(
                    max_size=cache_size,
                    ttl_seconds=cache_ttl,
                    logger=logger
                )
                if clear_cache:
                    validation_cache.clear()
                    logger.info(f"Validation cache cleared and enabled (max_size={cache_size}, ttl={cache_ttl}s)")
                else:
                    logger.info(f"Validation cache enabled (max_size={cache_size}, ttl={cache_ttl}s)")

            dq_checker = DataQualityChecker(logger, validation_cache=validation_cache, quiet=quiet)

            # Run parallel data quality checks (10-15% faster than sequential)
            logger.info("Running parallel data quality checks...")

            try:
                # Parallel validation for metrics and dimensions (10-15% faster)
                dq_checker.check_all_parallel(
                    metrics_df=metrics,
                    dimensions_df=dimensions,
                    metrics_required_fields=VALIDATION_SCHEMA['required_metric_fields'],
                    dimensions_required_fields=VALIDATION_SCHEMA['required_dimension_fields'],
                    critical_fields=VALIDATION_SCHEMA['critical_fields'],
                    max_workers=DEFAULT_VALIDATION_WORKERS
                )

                # Log aggregated summary instead of individual issue count
                dq_checker.log_summary()

                # Log cache statistics if cache was used
                if validation_cache is not None:
                    perf_tracker.add_cache_statistics(validation_cache)

                # End performance tracking
                perf_tracker.end("Data Quality Validation")

            except Exception as e:
                logger.error(_format_error_msg("during data quality validation", error=e))
                logger.info("Continuing with SDR generation despite validation errors")
                perf_tracker.end("Data Quality Validation")

            # Get data quality issues dataframe (limited if max_issues > 0)
            data_quality_df = dq_checker.get_issues_dataframe(max_issues=max_issues)

        # Data processing
        logger.info("=" * 60)
        logger.info("Processing data for Excel export")
        logger.info("=" * 60)

        try:
            # Process lookup data into DataFrame
            logger.info("Processing data view lookup information...")
            lookup_data_copy = {k: [v] if not isinstance(v, (list, tuple)) else v for k, v in lookup_data.items()}
            max_length = max(len(v) for v in lookup_data_copy.values()) if lookup_data_copy else 1
            lookup_data_copy = {k: v + [None] * (max_length - len(v)) for k, v in lookup_data_copy.items()}
            lookup_df = pd.DataFrame(lookup_data_copy)
            logger.info(f"Processed lookup data with {len(lookup_df)} rows")
        except Exception as e:
            logger.error(_format_error_msg("processing lookup data", error=e))
            lookup_df = pd.DataFrame({'Error': ['Failed to process data view information']})

        try:
            # Enhanced metadata creation
            logger.info("Creating metadata summary...")
            metric_types = metrics['type'].value_counts().to_dict() if not metrics.empty and 'type' in metrics.columns else {}
            metric_summary = [f"{type_}: {count}" for type_, count in metric_types.items()]

            dimension_types = dimensions['type'].value_counts().to_dict() if not dimensions.empty and 'type' in dimensions.columns else {}
            dimension_summary = [f"{type_}: {count}" for type_, count in dimension_types.items()]

            # Get current timezone and formatted timestamp
            local_tz = datetime.now().astimezone().tzinfo
            current_time = datetime.now(local_tz)
            formatted_timestamp = current_time.strftime('%Y-%m-%d %H:%M:%S %Z')

            # Count data quality issues by severity
            severity_counts = data_quality_df['Severity'].value_counts().to_dict()
            dq_summary = [f"{sev}: {count}" for sev, count in severity_counts.items()]

            # Create enhanced metadata DataFrame
            metadata_df = pd.DataFrame({
                'Property': [
                    'Generated Date & timestamp and timezone',
                    'Data View ID',
                    'Data View Name',
                    'Total Metrics',
                    'Metrics Breakdown',
                    'Total Dimensions',
                    'Dimensions Breakdown',
                    'Data Quality Issues',
                    'Data Quality Summary'
                ],
                'Value': [
                    formatted_timestamp,
                    data_view_id,
                    lookup_data.get("name", "Unknown") if isinstance(lookup_data, dict) else "Unknown",
                    len(metrics),
                    '\n'.join(metric_summary) if metric_summary else 'No metrics found',
                    len(dimensions),
                    '\n'.join(dimension_summary) if dimension_summary else 'No dimensions found',
                    len(dq_checker.issues),
                    '\n'.join(dq_summary) if dq_summary else 'No issues'
                ]
            })
            logger.info("Metadata created successfully")
        except Exception as e:
            logger.error(_format_error_msg("creating metadata", error=e))
            metadata_df = pd.DataFrame({'Error': ['Failed to create metadata']})

        # Function to format JSON cells
        def format_json_cell(value):
            """Format JSON objects for Excel display"""
            try:
                if isinstance(value, (dict, list)):
                    return json.dumps(value, indent=2)
                return value
            except Exception as e:
                logger.warning(f"Error formatting JSON cell: {str(e)}")
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
        except Exception as e:
            logger.error(_format_error_msg("applying JSON formatting", error=e))

        # Create Excel file name
        try:
            dv_name = lookup_data.get("name", "Unknown") if isinstance(lookup_data, dict) else "Unknown"
            # Sanitize filename
            dv_name = "".join(c for c in dv_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
            excel_file_name = f'CJA_DataView_{dv_name}_{data_view_id}_SDR.xlsx'

            # Add output directory path
            output_path = Path(output_dir) / excel_file_name
            logger.info(f"Excel file will be saved as: {output_path}")
        except Exception as e:
            logger.error(_format_error_msg("creating filename", error=e))
            excel_file_name = f'CJA_DataView_{data_view_id}_SDR.xlsx'
            output_path = Path(output_dir) / excel_file_name

        # Prepare data for output generation
        logger.info("=" * 60)
        logger.info(f"Generating output in format: {output_format}")
        logger.info("=" * 60)

        # Prepare data dictionary for all formats
        data_dict = {
            'Metadata': metadata_df,
            'Data Quality': data_quality_df,
            'DataView Details': lookup_df,
            'Metrics': metrics,
            'Dimensions': dimensions
        }

        # Prepare metadata dictionary for JSON/HTML
        metadata_dict = metadata_df.set_index(metadata_df.columns[0])[metadata_df.columns[1]].to_dict() if not metadata_df.empty else {}

        # Base filename without extension
        base_filename = output_path.stem if isinstance(output_path, Path) else Path(output_path).stem

        # Determine which formats to generate
        formats_to_generate = ['excel', 'csv', 'json', 'html', 'markdown'] if output_format == 'all' else [output_format]

        output_files = []

        try:
            for fmt in formats_to_generate:
                if fmt == 'excel':
                    logger.info("Generating Excel file...")
                    with pd.ExcelWriter(str(output_path), engine='xlsxwriter') as writer:
                        # Create format cache once for the entire workbook
                        # This improves performance by 15-25% by reusing format objects
                        format_cache = ExcelFormatCache(writer.book)

                        # Write sheets in order, with Data Quality first for visibility
                        sheets_to_write = [
                            (metadata_df, 'Metadata'),
                            (data_quality_df, 'Data Quality'),
                            (lookup_df, 'DataView'),
                            (metrics, 'Metrics'),
                            (dimensions, 'Dimensions')
                        ]

                        for sheet_data, sheet_name in sheets_to_write:
                            try:
                                if sheet_data.empty:
                                    logger.warning(f"Sheet {sheet_name} is empty, creating placeholder")
                                    placeholder_df = pd.DataFrame({'Note': [f'No data available for {sheet_name}']})
                                    apply_excel_formatting(writer, placeholder_df, sheet_name, logger, format_cache)
                                else:
                                    apply_excel_formatting(writer, sheet_data, sheet_name, logger, format_cache)
                            except Exception as e:
                                logger.error(f"Failed to write sheet {sheet_name}: {str(e)}")
                                continue

                    logger.info(f"✓ Excel file created: {output_path}")
                    output_files.append(str(output_path))

                elif fmt == 'csv':
                    csv_output = write_csv_output(data_dict, base_filename, output_dir, logger)
                    output_files.append(csv_output)

                elif fmt == 'json':
                    json_output = write_json_output(data_dict, metadata_dict, base_filename, output_dir, logger)
                    output_files.append(json_output)

                elif fmt == 'html':
                    html_output = write_html_output(data_dict, metadata_dict, base_filename, output_dir, logger)
                    output_files.append(html_output)

                elif fmt == 'markdown':
                    markdown_output = write_markdown_output(data_dict, metadata_dict, base_filename, output_dir, logger)
                    output_files.append(markdown_output)

            if len(output_files) > 1:
                logger.info(f"✓ SDR generation complete! {len(output_files)} files created")
                for file_path in output_files:
                    logger.info(f"  • {file_path}")
            else:
                logger.info(f"✓ SDR generation complete! File saved as: {output_files[0]}")

            # Final summary
            logger.info("=" * 60)
            logger.info("EXECUTION SUMMARY")
            logger.info("=" * 60)
            logger.info(f"Data View: {dv_name} ({data_view_id})")
            logger.info(f"Metrics: {len(metrics)}")
            logger.info(f"Dimensions: {len(dimensions)}")
            logger.info(f"Data Quality Issues: {len(dq_checker.issues)}")

            if dq_checker.issues:
                logger.info("Data Quality Issues by Severity:")
                for severity, count in severity_counts.items():
                    logger.info(f"  {severity}: {count}")

            logger.info(f"Output file: {output_path}")
            logger.info("=" * 60)

            logger.info("Script execution completed successfully")
            logger.info(perf_tracker.get_summary())

            duration = time.time() - start_time

            # Calculate total file size
            total_size = 0
            for file_path in output_files:
                try:
                    if os.path.isdir(file_path):
                        # For CSV directories, sum all files
                        for root, dirs, files in os.walk(file_path):
                            for f in files:
                                total_size += os.path.getsize(os.path.join(root, f))
                    else:
                        total_size += os.path.getsize(file_path)
                except OSError:
                    pass

            return ProcessingResult(
                data_view_id=data_view_id,
                data_view_name=dv_name,
                success=True,
                duration=duration,
                metrics_count=len(metrics),
                dimensions_count=len(dimensions),
                dq_issues_count=len(dq_checker.issues),
                output_file=str(output_path),
                file_size_bytes=total_size
            )

        except PermissionError as e:
            logger.critical(f"Permission denied writing to {output_path}. File may be open in another program.")
            logger.critical("Please close the file and try again.")
            logger.info("=" * 60)
            logger.info("EXECUTION FAILED")
            logger.info("=" * 60)
            logger.info(f"Data View: {dv_name} ({data_view_id})")
            logger.info(f"Error: Permission denied")
            logger.info(f"Duration: {time.time() - start_time:.2f}s")
            logger.info("=" * 60)
            for handler in logger.handlers:
                handler.flush()
            return ProcessingResult(
                data_view_id=data_view_id,
                data_view_name=dv_name,
                success=False,
                duration=time.time() - start_time,
                error_message=f"Permission denied: {str(e)}"
            )
        except Exception as e:
            logger.critical(f"Failed to generate Excel file: {str(e)}")
            logger.exception("Full exception details:")
            logger.info("=" * 60)
            logger.info("EXECUTION FAILED")
            logger.info("=" * 60)
            logger.info(f"Data View: {dv_name} ({data_view_id})")
            logger.info(f"Error: {str(e)}")
            logger.info(f"Duration: {time.time() - start_time:.2f}s")
            logger.info("=" * 60)
            for handler in logger.handlers:
                handler.flush()
            return ProcessingResult(
                data_view_id=data_view_id,
                data_view_name=dv_name,
                success=False,
                duration=time.time() - start_time,
                error_message=str(e)
            )

    except Exception as e:
        logger.critical(f"Unexpected error processing data view {data_view_id}: {str(e)}")
        logger.exception("Full exception details:")
        logger.info("=" * 60)
        logger.info("EXECUTION FAILED")
        logger.info("=" * 60)
        logger.info(f"Data View ID: {data_view_id}")
        logger.info(f"Error: {str(e)}")
        logger.info(f"Duration: {time.time() - start_time:.2f}s")
        logger.info("=" * 60)
        for handler in logger.handlers:
            handler.flush()
        return ProcessingResult(
            data_view_id=data_view_id,
            data_view_name="Unknown",
            success=False,
            duration=time.time() - start_time,
            error_message=str(e)
        )

# ==================== WORKER FUNCTION FOR MULTIPROCESSING ====================

def process_single_dataview_worker(args: tuple) -> ProcessingResult:
    """
    Worker function for multiprocessing

    Args:
        args: Tuple of (data_view_id, config_file, output_dir, log_level, output_format,
                       enable_cache, cache_size, cache_ttl, quiet, skip_validation, max_issues)

    Returns:
        ProcessingResult
    """
    data_view_id, config_file, output_dir, log_level, output_format, enable_cache, cache_size, cache_ttl, quiet, skip_validation, max_issues, clear_cache = args
    return process_single_dataview(data_view_id, config_file, output_dir, log_level, output_format,
                                   enable_cache, cache_size, cache_ttl, quiet, skip_validation, max_issues, clear_cache)

# ==================== BATCH PROCESSOR CLASS ====================

class BatchProcessor:
    """
    Process multiple data views in parallel using multiprocessing.

    Provides parallel execution of SDR generation across multiple data views
    with configurable worker count and error handling.

    Args:
        config_file: Path to CJA config file (default: 'config.json')
        output_dir: Directory for output files (default: current directory)
        workers: Number of parallel workers, 1-256 (default: 4)
        continue_on_error: Continue if individual data views fail (default: False)
        log_level: Logging level - DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO)
        output_format: Output format - excel, csv, json, html, markdown, all (default: excel)
        enable_cache: Enable validation result caching (default: False)
        cache_size: Maximum cached validation results, >= 1 (default: 1000)
        cache_ttl: Cache time-to-live in seconds, >= 1 (default: 3600)
        quiet: Suppress non-error output (default: False)
        skip_validation: Skip data quality validation (default: False)
        max_issues: Limit issues to top N by severity, >= 0; 0 = all (default: 0)
        clear_cache: Clear validation cache before processing (default: False)
    """

    def __init__(self, config_file: str = "config.json", output_dir: str = ".",
                 workers: int = 4, continue_on_error: bool = False, log_level: str = "INFO",
                 output_format: str = "excel", enable_cache: bool = False,
                 cache_size: int = 1000, cache_ttl: int = 3600, quiet: bool = False,
                 skip_validation: bool = False, max_issues: int = 0, clear_cache: bool = False):
        self.config_file = config_file
        self.output_dir = output_dir
        self.clear_cache = clear_cache
        self.workers = workers
        self.continue_on_error = continue_on_error
        self.log_level = log_level
        self.output_format = output_format
        self.enable_cache = enable_cache
        self.cache_size = cache_size
        self.cache_ttl = cache_ttl
        self.quiet = quiet
        self.skip_validation = skip_validation
        self.max_issues = max_issues
        self.batch_id = str(uuid.uuid4())[:8]  # Short correlation ID for log tracing
        self.logger = setup_logging(batch_mode=True, log_level=log_level)
        self.logger.info(f"Batch ID: {self.batch_id}")

        # Create output directory if it doesn't exist
        try:
            Path(output_dir).mkdir(parents=True, exist_ok=True)
        except PermissionError:
            print(ConsoleColors.error(f"ERROR: Permission denied creating output directory: {output_dir}"), file=sys.stderr)
            print("       Check that you have write permissions for the parent directory.", file=sys.stderr)
            sys.exit(1)
        except OSError as e:
            print(ConsoleColors.error(f"ERROR: Cannot create output directory '{output_dir}': {e}"), file=sys.stderr)
            print("       Verify the path is valid and the disk has available space.", file=sys.stderr)
            sys.exit(1)

    def process_batch(self, data_view_ids: List[str]) -> Dict:
        """
        Process multiple data views in parallel

        Args:
            data_view_ids: List of data view IDs to process

        Returns:
            Dictionary with processing results
        """
        self.logger.info("=" * 60)
        self.logger.info(f"[{self.batch_id}] BATCH PROCESSING START")
        self.logger.info("=" * 60)
        self.logger.info(f"[{self.batch_id}] Data views to process: {len(data_view_ids)}")
        self.logger.info(f"[{self.batch_id}] Parallel workers: {self.workers}")
        self.logger.info(f"[{self.batch_id}] Continue on error: {self.continue_on_error}")
        self.logger.info(f"[{self.batch_id}] Output directory: {self.output_dir}")
        self.logger.info(f"[{self.batch_id}] Output format: {self.output_format}")
        self.logger.info("=" * 60)

        batch_start_time = time.time()

        results = {
            'successful': [],
            'failed': [],
            'total': len(data_view_ids),
            'total_duration': 0
        }

        # Prepare arguments for each worker
        worker_args = [
            (dv_id, self.config_file, self.output_dir, self.log_level, self.output_format,
             self.enable_cache, self.cache_size, self.cache_ttl, self.quiet, self.skip_validation,
             self.max_issues, self.clear_cache)
            for dv_id in data_view_ids
        ]

        # Process with ProcessPoolExecutor for true parallelism
        with ProcessPoolExecutor(max_workers=self.workers) as executor:
            # Submit all tasks
            future_to_dv = {
                executor.submit(process_single_dataview_worker, args): args[0]
                for args in worker_args
            }

            # Collect results as they complete with progress bar
            with tqdm(
                total=len(data_view_ids),
                desc="Processing data views",
                unit="view",
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
                disable=self.quiet
            ) as pbar:
                for future in as_completed(future_to_dv):
                    dv_id = future_to_dv[future]
                    try:
                        result = future.result()

                        if result.success:
                            results['successful'].append(result)
                            pbar.set_postfix_str(f"✓ {dv_id[:20]}", refresh=True)
                            self.logger.info(f"[{self.batch_id}] ✓ {dv_id}: SUCCESS ({result.duration:.1f}s)")
                        else:
                            results['failed'].append(result)
                            pbar.set_postfix_str(f"✗ {dv_id[:20]}", refresh=True)
                            self.logger.error(f"[{self.batch_id}] ✗ {dv_id}: FAILED - {result.error_message}")

                            if not self.continue_on_error:
                                self.logger.warning(f"[{self.batch_id}] Stopping batch processing due to error (use --continue-on-error to continue)")
                                # Cancel remaining tasks
                                for f in future_to_dv:
                                    f.cancel()
                                break

                    except (KeyboardInterrupt, SystemExit):
                        # Allow graceful shutdown on Ctrl+C
                        self.logger.warning(f"[{self.batch_id}] Interrupted - cancelling remaining tasks...")
                        for f in future_to_dv:
                            f.cancel()
                        raise
                    except Exception as e:
                        self.logger.error(f"[{self.batch_id}] ✗ {dv_id}: EXCEPTION - {str(e)}")
                        results['failed'].append(ProcessingResult(
                            data_view_id=dv_id,
                            data_view_name="Unknown",
                            success=False,
                            duration=0,
                            error_message=str(e)
                        ))

                        if not self.continue_on_error:
                            self.logger.warning(f"[{self.batch_id}] Stopping batch processing due to error")
                            break

                    pbar.update(1)

        results['total_duration'] = time.time() - batch_start_time

        # Print summary
        self.print_summary(results)

        return results

    def print_summary(self, results: Dict):
        """Print detailed batch processing summary with color-coded output"""
        total = results['total']
        successful_count = len(results['successful'])
        failed_count = len(results['failed'])
        success_rate = (successful_count / total * 100) if total > 0 else 0
        total_duration = results['total_duration']
        avg_duration = (total_duration / total) if total > 0 else 0

        # Calculate total output size
        total_file_size = sum(r.file_size_bytes for r in results['successful'])
        total_size_formatted = format_file_size(total_file_size)

        # Log to file
        self.logger.info("")
        self.logger.info("=" * 60)
        self.logger.info(f"[{self.batch_id}] BATCH PROCESSING SUMMARY")
        self.logger.info("=" * 60)
        self.logger.info(f"[{self.batch_id}] Total data views: {total}")
        self.logger.info(f"[{self.batch_id}] Successful: {successful_count}")
        self.logger.info(f"[{self.batch_id}] Failed: {failed_count}")
        self.logger.info(f"[{self.batch_id}] Success rate: {success_rate:.1f}%")
        self.logger.info(f"[{self.batch_id}] Total output size: {total_size_formatted}")
        self.logger.info(f"[{self.batch_id}] Total duration: {total_duration:.1f}s")
        self.logger.info(f"[{self.batch_id}] Average per data view: {avg_duration:.1f}s")
        if total_duration > 0:
            throughput = total / total_duration
            self.logger.info(f"[{self.batch_id}] Throughput: {throughput:.2f} views/second")
        self.logger.info("=" * 60)

        # Print color-coded console output
        print()
        print("=" * 60)
        print(ConsoleColors.bold("BATCH PROCESSING SUMMARY"))
        print("=" * 60)
        print(f"Total data views: {total}")
        print(f"Successful: {ConsoleColors.success(str(successful_count))}")
        if failed_count > 0:
            print(f"Failed: {ConsoleColors.error(str(failed_count))}")
        else:
            print(f"Failed: {failed_count}")
        print(f"Success rate: {ConsoleColors.status(success_rate == 100, f'{success_rate:.1f}%')}")
        print(f"Total output size: {total_size_formatted}")
        print(f"Total duration: {total_duration:.1f}s")
        print(f"Average per data view: {avg_duration:.1f}s")
        if total_duration > 0:
            throughput = total / total_duration
            print(f"Throughput: {throughput:.2f} views/second")
        print()

        if results['successful']:
            print(ConsoleColors.success("Successful Data Views:"))
            self.logger.info("")
            self.logger.info("Successful Data Views:")
            for result in results['successful']:
                size_str = result.file_size_formatted
                line = f"  {result.data_view_id:20s}  {result.data_view_name:30s}  {size_str:>10s}  {result.duration:5.1f}s"
                print(ConsoleColors.success("  ✓") + line[3:])
                self.logger.info(f"  ✓ {result.data_view_id:20s}  {result.data_view_name:30s}  {size_str:>10s}  {result.duration:5.1f}s")
            print()
            self.logger.info("")

        if results['failed']:
            print(ConsoleColors.error("Failed Data Views:"))
            self.logger.info("Failed Data Views:")
            for result in results['failed']:
                line = f"  {result.data_view_id:20s}  {result.error_message}"
                print(ConsoleColors.error("  ✗") + line[3:])
                self.logger.info(f"  ✗ {result.data_view_id:20s}  {result.error_message}")
            print()
            self.logger.info("")

        print("=" * 60)
        self.logger.info("=" * 60)

        if total > 0 and total_duration > 0:
            throughput = (total / total_duration) * 60  # per minute
            print(f"Throughput: {throughput:.1f} data views per minute")
            print("=" * 60)
            self.logger.info(f"Throughput: {throughput:.1f} data views per minute")
            self.logger.info("=" * 60)

# ==================== DRY-RUN MODE ====================

def run_dry_run(data_views: List[str], config_file: str, logger: logging.Logger) -> bool:
    """
    Validate configuration and connectivity without generating reports.

    Performs the following checks:
    1. Configuration file validation (exists, valid JSON, required fields)
    2. CJA API connection test
    3. Data view accessibility verification

    Args:
        data_views: List of data view IDs to validate
        config_file: Path to configuration file
        logger: Logger instance

    Returns:
        True if all validations pass, False otherwise
    """
    print()
    print("=" * 60)
    print("DRY-RUN MODE - Validating configuration and connectivity")
    print("=" * 60)
    print()

    all_passed = True

    # Step 1: Validate config file
    print("[1/3] Validating configuration file...")
    if validate_config_file(config_file, logger):
        print(f"  ✓ Configuration file '{config_file}' is valid")
    else:
        print(f"  ✗ Configuration file validation failed")
        all_passed = False
        print()
        print("=" * 60)
        print("DRY-RUN FAILED - Fix configuration issues before proceeding")
        print("=" * 60)
        return False

    # Step 2: Test CJA connection
    print()
    print("[2/3] Testing CJA API connection...")
    try:
        cjapy.importConfigFile(config_file)
        cja = cjapy.CJA()

        # Test API with getDataViews call (with retry for transient errors)
        available_dvs = make_api_call_with_retry(
            cja.getDataViews,
            logger=logger,
            operation_name="getDataViews (dry-run)"
        )
        if available_dvs is not None:
            dv_count = len(available_dvs) if hasattr(available_dvs, '__len__') else 0
            print(f"  ✓ API connection successful")
            print(f"  ✓ Found {dv_count} accessible data view(s)")
        else:
            print("  ⚠ API connection returned None - may be unstable")
            available_dvs = []
    except (KeyboardInterrupt, SystemExit):
        print()
        print(ConsoleColors.warning("Dry-run cancelled."))
        raise
    except Exception as e:
        print(f"  ✗ API connection failed: {str(e)}")
        all_passed = False
        print()
        print("=" * 60)
        print("DRY-RUN FAILED - Cannot connect to CJA API")
        print("=" * 60)
        return False

    # Step 3: Validate each data view
    print()
    print(f"[3/3] Validating {len(data_views)} data view(s)...")

    # Build set of available data view IDs for quick lookup
    available_ids = set()
    if available_dvs is not None and (isinstance(available_dvs, pd.DataFrame) and not available_dvs.empty or not isinstance(available_dvs, pd.DataFrame) and available_dvs):
        for dv in available_dvs:
            if isinstance(dv, dict):
                available_ids.add(dv.get('id', ''))

    valid_count = 0
    invalid_count = 0
    total_metrics = 0
    total_dimensions = 0
    dv_details = []

    for dv_id in data_views:
        # Try to get data view info (with retry for transient errors)
        try:
            dv_info = make_api_call_with_retry(
                cja.getDataView,
                dv_id,
                logger=logger,
                operation_name=f"getDataView({dv_id})"
            )
            if dv_info:
                dv_name = dv_info.get('name', 'Unknown')

                # Fetch component counts for predictions
                metrics_count = 0
                dimensions_count = 0
                try:
                    metrics = make_api_call_with_retry(
                        cja.getMetrics,
                        dv_id,
                        logger=logger,
                        operation_name=f"getMetrics({dv_id})"
                    )
                    if metrics is not None:
                        metrics_count = len(metrics) if hasattr(metrics, '__len__') else 0
                except Exception:
                    pass  # Count will be 0 if fetch fails

                try:
                    dimensions = make_api_call_with_retry(
                        cja.getDimensions,
                        dv_id,
                        logger=logger,
                        operation_name=f"getDimensions({dv_id})"
                    )
                    if dimensions is not None:
                        dimensions_count = len(dimensions) if hasattr(dimensions, '__len__') else 0
                except Exception:
                    pass  # Count will be 0 if fetch fails

                total_metrics += metrics_count
                total_dimensions += dimensions_count
                dv_details.append({
                    'id': dv_id,
                    'name': dv_name,
                    'metrics': metrics_count,
                    'dimensions': dimensions_count
                })

                print(f"  ✓ {dv_id}: {dv_name}")
                print(f"      Components: {metrics_count} metrics, {dimensions_count} dimensions")
                valid_count += 1
            else:
                print(f"  ✗ {dv_id}: Not found or no access")
                invalid_count += 1
                all_passed = False
        except (KeyboardInterrupt, SystemExit):
            print()
            print(ConsoleColors.warning("Validation cancelled."))
            raise
        except Exception as e:
            print(f"  ✗ {dv_id}: Error - {str(e)}")
            invalid_count += 1
            all_passed = False

    # Calculate time estimates
    # Based on benchmarks: ~0.5s per component for validation, ~0.1s without
    total_components = total_metrics + total_dimensions
    est_time_with_validation = total_components * 0.01 + len(data_views) * 2  # API overhead per view
    est_time_skip_validation = total_components * 0.005 + len(data_views) * 1.5

    # Summary
    print()
    print("=" * 60)
    print("DRY-RUN SUMMARY")
    print("=" * 60)
    print(f"  Configuration: ✓ Valid")
    print(f"  API Connection: ✓ Connected")
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

    print("=" * 60)

    return all_passed

# ==================== COMMAND-LINE INTERFACE ====================

def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments"""
    parser = argparse.ArgumentParser(
        description='CJA SDR Generator - Generate System Design Records for CJA Data Views',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog='''
Examples:
  # Single data view
  python cja_sdr_generator.py dv_12345

  # Multiple data views (automatically triggers parallel processing)
  python cja_sdr_generator.py dv_12345 dv_67890 dv_abcde

  # Batch processing with explicit flag (same as above)
  python cja_sdr_generator.py --batch dv_12345 dv_67890 dv_abcde

  # Custom workers
  python cja_sdr_generator.py --batch dv_12345 dv_67890 --workers 2

  # Custom output directory
  python cja_sdr_generator.py dv_12345 --output-dir ./reports

  # Continue on errors
  python cja_sdr_generator.py --batch dv_* --continue-on-error

  # With custom log level
  python cja_sdr_generator.py --batch dv_* --log-level WARNING

  # Export as CSV files
  python cja_sdr_generator.py dv_12345 --format csv

  # Export as JSON
  python cja_sdr_generator.py dv_12345 --format json

  # Export as HTML
  python cja_sdr_generator.py dv_12345 --format html

  # Export as Markdown (GitHub/Confluence)
  python cja_sdr_generator.py dv_12345 --format markdown

  # Export in all formats
  python cja_sdr_generator.py dv_12345 --format all

  # Dry-run to validate config and connectivity
  python cja_sdr_generator.py dv_12345 --dry-run

  # Quiet mode (errors only)
  python cja_sdr_generator.py dv_12345 --quiet

  # List all accessible data views
  python cja_sdr_generator.py --list-dataviews

  # Skip data quality validation (faster processing)
  python cja_sdr_generator.py dv_12345 --skip-validation

  # Generate sample configuration file
  python cja_sdr_generator.py --sample-config

  # Limit data quality issues to top 10 by severity
  python cja_sdr_generator.py dv_12345 --max-issues 10

  # Validate only (alias for --dry-run)
  python cja_sdr_generator.py dv_12345 --validate-only

  # --- Data View Comparison (Diff) ---

  # Compare two live data views
  python cja_sdr_generator.py --diff dv_prod_12345 dv_staging_67890
  python cja_sdr_generator.py --diff "Production Analytics" "Staging Analytics"

  # Save a snapshot for later comparison
  python cja_sdr_generator.py dv_12345 --snapshot ./snapshots/baseline.json

  # Compare current state against a saved snapshot
  python cja_sdr_generator.py dv_12345 --diff-snapshot ./snapshots/baseline.json

  # Diff output options
  python cja_sdr_generator.py --diff dv_A dv_B --format html --output-dir ./reports
  python cja_sdr_generator.py --diff dv_A dv_B --format all
  python cja_sdr_generator.py --diff dv_A dv_B --changes-only
  python cja_sdr_generator.py --diff dv_A dv_B --summary

  # Advanced diff options
  python cja_sdr_generator.py --diff dv_A dv_B --ignore-fields description,title
  python cja_sdr_generator.py --diff dv_A dv_B --diff-labels Production Staging

  # Auto-snapshot: automatically save snapshots during diff for audit trail
  python cja_sdr_generator.py --diff dv_A dv_B --auto-snapshot
  python cja_sdr_generator.py --diff dv_A dv_B --auto-snapshot --snapshot-dir ./history
  python cja_sdr_generator.py --diff dv_A dv_B --auto-snapshot --keep-last 10

  # --- Quick UX Features ---

  # Quick stats without full report
  python cja_sdr_generator.py dv_12345 --stats
  python cja_sdr_generator.py dv_1 dv_2 dv_3 --stats

  # Stats in JSON format for scripting
  python cja_sdr_generator.py dv_12345 --stats --format json
  python cja_sdr_generator.py dv_12345 --stats --output -    # Output to stdout

  # Open file after generation
  python cja_sdr_generator.py dv_12345 --open

  # List data views in JSON format (for scripting/piping)
  python cja_sdr_generator.py --list-dataviews --format json
  python cja_sdr_generator.py --list-dataviews --output -    # JSON to stdout

Note:
  At least one data view ID must be provided (except for --list-dataviews, --sample-config, --stats).
  Use 'python cja_sdr_generator.py --help' to see all options.

Exit Codes:
  0 - Success (diff: no differences found)
  1 - Error occurred
  2 - Success with differences found (diff mode only)

Requirements:
  Python 3.14 or higher required. Verify with: python --version
        '''
    )

    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {__version__}',
        help='Show program version and exit'
    )

    parser.add_argument(
        'data_views',
        nargs='*',
        metavar='DATA_VIEW_ID_OR_NAME',
        help='Data view IDs (e.g., dv_12345) or exact names (use quotes for names with spaces). '
             'If a name matches multiple data views, all will be processed. '
             'At least one required unless using --version, --list-dataviews, etc.'
    )

    parser.add_argument(
        '--batch',
        action='store_true',
        help='Enable batch processing mode (parallel execution)'
    )

    parser.add_argument(
        '--workers',
        type=int,
        default=DEFAULT_BATCH_WORKERS,
        help=f'Number of parallel workers for batch mode (default: {DEFAULT_BATCH_WORKERS}, max: {MAX_BATCH_WORKERS})'
    )

    parser.add_argument(
        '--output-dir',
        type=str,
        default=os.environ.get('OUTPUT_DIR', '.'),
        help='Output directory for generated files (default: current directory, or OUTPUT_DIR env var)'
    )

    parser.add_argument(
        '--config-file',
        type=str,
        default='config.json',
        help='Path to CJA configuration file (default: config.json)'
    )

    parser.add_argument(
        '--continue-on-error',
        action='store_true',
        help='Continue processing remaining data views if one fails'
    )

    parser.add_argument(
        '--log-level',
        type=str,
        default=os.environ.get('LOG_LEVEL', 'INFO'),
        choices=['DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL'],
        help='Logging level (default: INFO, or LOG_LEVEL environment variable)'
    )

    parser.add_argument(
        '--production',
        action='store_true',
        help='Enable production mode (minimal logging for maximum performance)'
    )

    parser.add_argument(
        '--enable-cache',
        action='store_true',
        help='Enable validation result caching (50-90%% faster on repeated validations)'
    )

    parser.add_argument(
        '--clear-cache',
        action='store_true',
        help='Clear validation cache before processing (use with --enable-cache for fresh validation)'
    )

    parser.add_argument(
        '--cache-size',
        type=int,
        default=DEFAULT_CACHE_SIZE,
        help=f'Maximum number of cached validation results (default: {DEFAULT_CACHE_SIZE})'
    )

    parser.add_argument(
        '--cache-ttl',
        type=int,
        default=DEFAULT_CACHE_TTL,
        help=f'Cache time-to-live in seconds (default: {DEFAULT_CACHE_TTL} = 1 hour)'
    )

    parser.add_argument(
        '--max-retries',
        type=int,
        default=int(os.environ.get('MAX_RETRIES', DEFAULT_RETRY_CONFIG['max_retries'])),
        help=f'Maximum API retry attempts (default: {DEFAULT_RETRY_CONFIG["max_retries"]}, or MAX_RETRIES env var)'
    )

    parser.add_argument(
        '--retry-base-delay',
        type=float,
        default=float(os.environ.get('RETRY_BASE_DELAY', DEFAULT_RETRY_CONFIG['base_delay'])),
        help=f'Initial retry delay in seconds (default: {DEFAULT_RETRY_CONFIG["base_delay"]}, or RETRY_BASE_DELAY env var)'
    )

    parser.add_argument(
        '--retry-max-delay',
        type=float,
        default=float(os.environ.get('RETRY_MAX_DELAY', DEFAULT_RETRY_CONFIG['max_delay'])),
        help=f'Maximum retry delay in seconds (default: {DEFAULT_RETRY_CONFIG["max_delay"]}, or RETRY_MAX_DELAY env var)'
    )

    parser.add_argument(
        '--format',
        type=str,
        default=None,
        choices=['console', 'excel', 'csv', 'json', 'html', 'markdown', 'all'],
        help='Output format: console, excel, csv, json, html, markdown, or all. Default: excel for SDR generation, console for diff'
    )

    parser.add_argument(
        '--dry-run', '--validate-only',
        action='store_true',
        dest='dry_run',
        help='Validate configuration and connectivity without generating reports'
    )

    parser.add_argument(
        '--quiet', '-q',
        action='store_true',
        help='Quiet mode - suppress all output except errors and final summary'
    )

    parser.add_argument(
        '--list-dataviews',
        action='store_true',
        help='List all accessible data views and exit (no data view ID required)'
    )

    parser.add_argument(
        '--skip-validation',
        action='store_true',
        help='Skip data quality validation for faster processing (20-30%% faster)'
    )

    parser.add_argument(
        '--sample-config',
        action='store_true',
        help='Generate a sample configuration file and exit'
    )

    parser.add_argument(
        '--validate-config',
        action='store_true',
        help='Validate configuration and API connectivity without processing any data views'
    )

    parser.add_argument(
        '--max-issues',
        type=int,
        default=0,
        metavar='N',
        help='Limit data quality issues to top N by severity (0 = show all, default: 0)'
    )

    # ==================== UX ENHANCEMENT ARGUMENTS ====================

    parser.add_argument(
        '--open',
        action='store_true',
        help='Open the generated file(s) in the default application after creation'
    )

    parser.add_argument(
        '--stats',
        action='store_true',
        help='Show quick statistics about data view(s) without generating full reports. '
             'Displays counts of metrics, dimensions, and basic info'
    )

    parser.add_argument(
        '--output',
        type=str,
        metavar='PATH',
        help='Output file path. Use "-" or "stdout" to write to standard output (JSON/CSV only). '
             'For stdout, implies --quiet to suppress other output'
    )

    # ==================== DIFF COMPARISON ARGUMENTS ====================

    diff_group = parser.add_argument_group('Diff Comparison', 'Options for comparing data views')

    diff_group.add_argument(
        '--diff',
        action='store_true',
        help='Compare two data views. Provide exactly 2 data view IDs/names as positional arguments'
    )

    diff_group.add_argument(
        '--snapshot',
        type=str,
        metavar='FILE',
        help='Save a snapshot of the data view to a JSON file (use with single data view)'
    )

    diff_group.add_argument(
        '--diff-snapshot',
        type=str,
        metavar='FILE',
        help='Compare data view against a saved snapshot file'
    )

    diff_group.add_argument(
        '--compare-snapshots',
        nargs=2,
        metavar=('SOURCE', 'TARGET'),
        help='Compare two snapshot files directly (no API calls required). '
             'Example: --compare-snapshots baseline.json current.json'
    )

    diff_group.add_argument(
        '--changes-only',
        action='store_true',
        help='Only show changed items in diff output (hide unchanged)'
    )

    diff_group.add_argument(
        '--summary',
        action='store_true',
        help='Show summary statistics only (no detailed changes)'
    )

    diff_group.add_argument(
        '--ignore-fields',
        type=str,
        metavar='FIELDS',
        help='Comma-separated list of fields to ignore during comparison (e.g., "description,title")'
    )

    diff_group.add_argument(
        '--diff-labels',
        nargs=2,
        metavar=('SOURCE', 'TARGET'),
        help='Custom labels for the two sides of the comparison (default: Source, Target)'
    )

    diff_group.add_argument(
        '--show-only',
        type=str,
        metavar='TYPES',
        help='Filter diff output to show only specific change types. '
             'Comma-separated list: added,removed,modified,unchanged (e.g., "added,modified")'
    )

    diff_group.add_argument(
        '--metrics-only',
        action='store_true',
        help='Only compare metrics (exclude dimensions from diff)'
    )

    diff_group.add_argument(
        '--dimensions-only',
        action='store_true',
        help='Only compare dimensions (exclude metrics from diff)'
    )

    diff_group.add_argument(
        '--extended-fields',
        action='store_true',
        help='Use extended field comparison including attribution, format, bucketing, '
             'persistence settings (default: basic fields only)'
    )

    diff_group.add_argument(
        '--side-by-side',
        action='store_true',
        help='Show side-by-side comparison view for modified items (console and markdown)'
    )

    diff_group.add_argument(
        '--no-color',
        action='store_true',
        help='Disable ANSI color codes in console output'
    )

    diff_group.add_argument(
        '--quiet-diff',
        action='store_true',
        help='Suppress diff output, only return exit code (0=no changes, 2=changes found)'
    )

    diff_group.add_argument(
        '--reverse-diff',
        action='store_true',
        help='Reverse the comparison direction (swap source and target)'
    )

    diff_group.add_argument(
        '--warn-threshold',
        type=float,
        metavar='PERCENT',
        help='Exit with code 3 if change percentage exceeds threshold (e.g., --warn-threshold 10)'
    )

    diff_group.add_argument(
        '--group-by-field',
        action='store_true',
        help='Group changes by field name instead of by component'
    )

    diff_group.add_argument(
        '--diff-output',
        type=str,
        metavar='FILE',
        help='Write diff output directly to file instead of stdout'
    )

    diff_group.add_argument(
        '--format-pr-comment',
        action='store_true',
        help='Output in GitHub/GitLab PR comment format (markdown with collapsible details)'
    )

    diff_group.add_argument(
        '--auto-snapshot',
        action='store_true',
        help='Automatically save snapshots of data views during diff comparison. '
             'Creates timestamped snapshots in --snapshot-dir for audit trail'
    )

    diff_group.add_argument(
        '--snapshot-dir',
        type=str,
        default='./snapshots',
        metavar='DIR',
        help='Directory for auto-saved snapshots (default: ./snapshots). Used with --auto-snapshot'
    )

    diff_group.add_argument(
        '--keep-last',
        type=int,
        default=0,
        metavar='N',
        help='Retention policy: keep only the last N snapshots per data view (0 = keep all). '
             'Used with --auto-snapshot'
    )

    # ==================== GIT INTEGRATION ARGUMENTS ====================

    git_group = parser.add_argument_group('Git Integration', 'Options for version-controlled snapshots')

    git_group.add_argument(
        '--git-commit',
        action='store_true',
        help='Save snapshot in Git-friendly format and commit to Git repository. '
             'Creates separate JSON files (metrics.json, dimensions.json, metadata.json) '
             'for easy diffing in Git'
    )

    git_group.add_argument(
        '--git-push',
        action='store_true',
        help='Push to remote after committing (requires --git-commit)'
    )

    git_group.add_argument(
        '--git-message',
        type=str,
        metavar='MESSAGE',
        help='Custom message for Git commit (used with --git-commit)'
    )

    git_group.add_argument(
        '--git-dir',
        type=str,
        default='./sdr-snapshots',
        metavar='DIR',
        help='Directory for Git-tracked snapshots (default: ./sdr-snapshots). '
             'Will be initialized as Git repo if not already'
    )

    git_group.add_argument(
        '--git-init',
        action='store_true',
        help='Initialize a new Git repository for snapshots at --git-dir location'
    )

    # Enable shell tab-completion if argcomplete is installed
    if _ARGCOMPLETE_AVAILABLE:
        argcomplete.autocomplete(parser)

    return parser.parse_args()

# ==================== DATA VIEW NAME RESOLUTION ====================

def is_data_view_id(identifier: str) -> bool:
    """
    Check if a string is a data view ID (starts with 'dv_')

    Args:
        identifier: String to check

    Returns:
        True if identifier is a data view ID, False if it's a name
    """
    return identifier.startswith('dv_')


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


def find_similar_names(target: str, available_names: List[str], max_suggestions: int = 3,
                       max_distance: int = None) -> List[Tuple[str, int]]:
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
        self._cache: Dict[str, Tuple[List[Dict], float]] = {}
        self._ttl_seconds = 300  # 5 minute default TTL
        self._initialized = True

    def get(self, config_file: str) -> Optional[List[Dict]]:
        """
        Get cached data views for a config file.

        Args:
            config_file: The config file key

        Returns:
            List of data view dicts if cached and not expired, None otherwise
        """
        with self._lock:
            if config_file in self._cache:
                data, timestamp = self._cache[config_file]
                if time.time() - timestamp < self._ttl_seconds:
                    return data
                # Expired - remove from cache
                del self._cache[config_file]
            return None

    def set(self, config_file: str, data: List[Dict]) -> None:
        """
        Cache data views for a config file.

        Args:
            config_file: The config file key
            data: List of data view dicts to cache
        """
        with self._lock:
            self._cache[config_file] = (data, time.time())

    def clear(self) -> None:
        """Clear all cached data."""
        with self._lock:
            self._cache.clear()

    def set_ttl(self, seconds: int) -> None:
        """Set the cache TTL in seconds."""
        self._ttl_seconds = seconds


# Global cache instance
_data_view_cache = DataViewCache()


def get_cached_data_views(cja, config_file: str, logger: logging.Logger) -> List[Dict]:
    """
    Get data views with caching support.

    Args:
        cja: CJA API instance
        config_file: Config file path (used as cache key)
        logger: Logger instance

    Returns:
        List of data view dicts
    """
    # Check cache first
    cached = _data_view_cache.get(config_file)
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
        available_dvs = available_dvs.to_dict('records')

    # Cache the result
    _data_view_cache.set(config_file, available_dvs)
    logger.debug(f"Cached {len(available_dvs)} data views")

    return available_dvs


def prompt_for_selection(options: List[Tuple[str, str]], prompt_text: str) -> Optional[str]:
    """
    Prompt user to select from a list of options interactively.

    Args:
        options: List of (id, display_text) tuples
        prompt_text: Text to display before options

    Returns:
        Selected ID or None if user cancels
    """
    # Check if we're in an interactive terminal
    if not sys.stdin.isatty():
        return None

    print(f"\n{prompt_text}")
    print("-" * 40)

    for i, (opt_id, display) in enumerate(options, 1):
        print(f"  [{i}] {display}")
        print(f"      ID: {opt_id}")

    print(f"  [0] Cancel")
    print()

    while True:
        try:
            choice = input("Enter selection (number): ").strip()
            if choice == '0' or choice.lower() in ('q', 'quit', 'cancel'):
                return None

            idx = int(choice)
            if 1 <= idx <= len(options):
                return options[idx - 1][0]

            print(f"Invalid selection. Enter 1-{len(options)} or 0 to cancel.")
        except ValueError:
            print("Please enter a number.")
        except (EOFError, KeyboardInterrupt):
            print("\nCancelled.")
            return None


def resolve_data_view_names(identifiers: List[str], config_file: str = "config.json",
                            logger: logging.Logger = None,
                            suggest_similar: bool = True) -> Tuple[List[str], Dict[str, List[str]]]:
    """
    Resolve data view names to IDs. If an identifier is already an ID, keep it as-is.
    If it's a name, look up all data views with that exact name.

    Features:
    - Caches API calls for performance when resolving multiple names
    - Suggests similar names using fuzzy matching when exact match fails

    Args:
        identifiers: List of data view IDs or names
        config_file: Path to CJA configuration file
        logger: Logger instance for logging
        suggest_similar: If True, suggest similar names when exact match fails

    Returns:
        Tuple of (resolved_ids, name_to_ids_map)
        - resolved_ids: List of all resolved data view IDs
        - name_to_ids_map: Dict mapping names to their resolved IDs (for reporting)
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    resolved_ids = []
    name_to_ids_map = {}

    try:
        # Initialize CJA connection
        logger.info(f"Resolving data view identifiers: {identifiers}")
        cjapy.importConfigFile(config_file)
        cja = cjapy.CJA()

        # Get all available data views (with caching)
        logger.debug("Fetching all data views for name resolution")
        available_dvs = get_cached_data_views(cja, config_file, logger)

        if not available_dvs:
            logger.error("No data views found or no access to any data views")
            return [], {}

        # Build a lookup map: name -> list of IDs
        name_to_id_lookup = {}
        id_to_name_lookup = {}

        for dv in available_dvs:
            if isinstance(dv, dict):
                dv_id = dv.get('id')
                dv_name = dv.get('name')

                if dv_id and dv_name:
                    id_to_name_lookup[dv_id] = dv_name
                    if dv_name not in name_to_id_lookup:
                        name_to_id_lookup[dv_name] = []
                    name_to_id_lookup[dv_name].append(dv_id)

        logger.debug(f"Built lookup map with {len(name_to_id_lookup)} unique names and {len(id_to_name_lookup)} IDs")

        # Process each identifier
        for identifier in identifiers:
            if is_data_view_id(identifier):
                # It's an ID - validate it exists
                if identifier in id_to_name_lookup:
                    resolved_ids.append(identifier)
                    logger.debug(f"ID '{identifier}' validated: {id_to_name_lookup[identifier]}")
                else:
                    logger.warning(f"Data view ID '{identifier}' not found in accessible data views")
                    # Still add it - will fail during processing with proper error message
                    resolved_ids.append(identifier)
            else:
                # It's a name - look up all matching IDs
                if identifier in name_to_id_lookup:
                    matching_ids = name_to_id_lookup[identifier]
                    resolved_ids.extend(matching_ids)
                    name_to_ids_map[identifier] = matching_ids

                    if len(matching_ids) == 1:
                        logger.info(f"Name '{identifier}' resolved to ID: {matching_ids[0]}")
                    else:
                        logger.info(f"Name '{identifier}' matched {len(matching_ids)} data views: {matching_ids}")
                else:
                    # Name not found - try to find similar names for helpful error message
                    logger.error(f"Data view name '{identifier}' not found in accessible data views")

                    if suggest_similar:
                        similar = find_similar_names(identifier, list(name_to_id_lookup.keys()))
                        if similar:
                            # Check for case-insensitive match first
                            case_match = [s for s in similar if s[1] == 0]
                            if case_match:
                                logger.error(f"  → Did you mean '{case_match[0][0]}'? (case mismatch)")
                            else:
                                suggestions = [f"'{s[0]}'" for s in similar]
                                logger.error(f"  → Did you mean: {', '.join(suggestions)}?")

                    logger.error(f"  → Name matching is CASE-SENSITIVE and requires EXACT match")
                    logger.error(f"  → Run 'cja_auto_sdr --list-dataviews' to see all available names")
                    # Don't add to resolved_ids - this is an error

        logger.info(f"Resolved {len(identifiers)} identifier(s) to {len(resolved_ids)} data view ID(s)")
        return resolved_ids, name_to_ids_map

    except FileNotFoundError:
        logger.error(f"Configuration file '{config_file}' not found")
        return [], {}
    except Exception as e:
        logger.error(f"Failed to resolve data view names: {str(e)}")
        return [], {}


# ==================== LIST DATA VIEWS ====================

def list_dataviews(config_file: str = "config.json", output_format: str = "table",
                   output_file: Optional[str] = None) -> bool:
    """
    List all accessible data views and exit

    Args:
        config_file: Path to CJA configuration file
        output_format: Output format - "table" (default), "json", or "csv"
        output_file: Optional file path to write output (or "-" for stdout)

    Returns:
        True if successful, False otherwise
    """
    is_stdout = output_file in ('-', 'stdout')
    is_machine_readable = output_format in ('json', 'csv') or is_stdout

    # For machine-readable output, suppress decorative text
    if not is_machine_readable:
        print()
        print("=" * 60)
        print("LISTING ACCESSIBLE DATA VIEWS")
        print("=" * 60)
        print()
        print(f"Using configuration: {config_file}")
        print()

    try:
        cjapy.importConfigFile(config_file)
        cja = cjapy.CJA()

        # Get all data views
        if not is_machine_readable:
            print("Connecting to CJA API...")
        available_dvs = cja.getDataViews()

        if available_dvs is None or (hasattr(available_dvs, '__len__') and len(available_dvs) == 0):
            if is_machine_readable:
                if output_format == 'json':
                    output_data = json.dumps({"dataViews": [], "count": 0}, indent=2)
                else:  # csv
                    output_data = "id,name,owner\n"
                if is_stdout:
                    print(output_data)
                elif output_file:
                    with open(output_file, 'w') as f:
                        f.write(output_data)
            else:
                print()
                print(ConsoleColors.warning("No data views found or no access to any data views."))
                print()
            return True

        # Convert to list if DataFrame
        if isinstance(available_dvs, pd.DataFrame):
            available_dvs = available_dvs.to_dict('records')

        # Prepare data
        display_data = []
        for dv in available_dvs:
            if isinstance(dv, dict):
                dv_id = dv.get('id', 'N/A')
                dv_name = dv.get('name', 'N/A')
                dv_owner = dv.get('owner', {})
                owner_name = dv_owner.get('name', 'N/A') if isinstance(dv_owner, dict) else str(dv_owner)

                display_data.append({
                    'id': dv_id,
                    'name': dv_name,
                    'owner': owner_name
                })

        # Output based on format
        if output_format == 'json' or (is_stdout and output_format != 'csv'):
            output_data = json.dumps({
                "dataViews": display_data,
                "count": len(display_data)
            }, indent=2)
            if is_stdout:
                print(output_data)
            elif output_file:
                with open(output_file, 'w') as f:
                    f.write(output_data)
            else:
                print(output_data)
        elif output_format == 'csv':
            lines = ["id,name,owner"]
            for item in display_data:
                # Escape quotes and commas in CSV
                name = item['name'].replace('"', '""')
                owner = item['owner'].replace('"', '""')
                lines.append(f'{item["id"]},"{name}","{owner}"')
            output_data = '\n'.join(lines)
            if is_stdout:
                print(output_data)
            elif output_file:
                with open(output_file, 'w') as f:
                    f.write(output_data)
            else:
                print(output_data)
        else:
            # Table format (default)
            print()
            print(f"Found {len(available_dvs)} accessible data view(s):")
            print()

            # Calculate dynamic column widths
            max_id_width = max(len('ID'), max(len(item['id']) for item in display_data)) + 2
            max_name_width = max(len('Name'), max(len(item['name']) for item in display_data)) + 2
            max_owner_width = max(len('Owner'), max(len(item['owner']) for item in display_data)) + 2

            total_width = max_id_width + max_name_width + max_owner_width
            print(f"{'ID':<{max_id_width}} {'Name':<{max_name_width}} {'Owner':<{max_owner_width}}")
            print("-" * total_width)

            for item in display_data:
                print(f"{item['id']:<{max_id_width}} {item['name']:<{max_name_width}} {item['owner']:<{max_owner_width}}")

            print()
            print("=" * total_width)
            print("Usage:")
            print("  python cja_sdr_generator.py <DATA_VIEW_ID>       # Use ID directly")
            print("  python cja_sdr_generator.py \"<DATA_VIEW_NAME>\"   # Use exact name (quotes recommended)")
            print()
            print("Note: If multiple data views share the same name, all will be processed.")
            print("=" * total_width)

        return True

    except FileNotFoundError:
        if is_machine_readable:
            error_json = json.dumps({"error": f"Configuration file '{config_file}' not found"})
            print(error_json, file=sys.stderr if is_stdout else sys.stdout)
        else:
            print(ConsoleColors.error(f"ERROR: Configuration file '{config_file}' not found"))
            print()
            print("Generate a sample configuration file with:")
            print("  python cja_sdr_generator.py --sample-config")
        return False

    except (KeyboardInterrupt, SystemExit):
        if not is_machine_readable:
            print()
            print(ConsoleColors.warning("Operation cancelled."))
        raise

    except Exception as e:
        if is_machine_readable:
            error_json = json.dumps({"error": f"Failed to connect to CJA API: {str(e)}"})
            print(error_json, file=sys.stderr if is_stdout else sys.stdout)
        else:
            print(ConsoleColors.error(f"ERROR: Failed to connect to CJA API: {str(e)}"))
        return False


# ==================== SAMPLE CONFIG GENERATOR ====================

def generate_sample_config(output_path: str = "config.sample.json") -> bool:
    """
    Generate a sample configuration file

    Args:
        output_path: Path to write the sample config file

    Returns:
        True if successful, False otherwise
    """
    sample_config = {
        "org_id": "YOUR_ORG_ID@AdobeOrg",
        "client_id": "your_client_id_here",
        "secret": "your_client_secret_here",
        "scopes": "openid, AdobeID, additional_info.projectedProductContext"
    }

    print()
    print("=" * 60)
    print("GENERATING SAMPLE CONFIGURATION FILE")
    print("=" * 60)
    print()

    try:
        with open(output_path, 'w') as f:
            json.dump(sample_config, f, indent=2)

        print(f"✓ Sample configuration file created: {output_path}")
        print()
        print("Next steps:")
        print("  1. Copy the sample file to 'config.json':")
        print(f"     cp {output_path} config.json")
        print()
        print("  2. Edit config.json with your Adobe Developer Console credentials")
        print()
        print("  3. Test your configuration:")
        print("     python cja_sdr_generator.py --list-dataviews")
        print()
        print("=" * 60)

        return True

    except (PermissionError, OSError, IOError) as e:
        print(ConsoleColors.error(f"ERROR: Failed to create sample config: {str(e)}"))
        return False


# ==================== VALIDATE CONFIG ====================

def validate_config_only(config_file: str = "config.json") -> bool:
    """
    Validate configuration file and API connectivity without processing data views.

    Tests:
        1. Environment variables or config file exists
        2. Required credentials are present
        3. CJA API connection works

    Args:
        config_file: Path to CJA configuration file

    Returns:
        True if configuration is valid and API is reachable
    """
    print()
    print("=" * 60)
    print("CONFIGURATION VALIDATION")
    print("=" * 60)
    print()

    all_passed = True

    # Step 1: Check environment variables
    print("[1/3] Checking credentials...")
    env_credentials = load_credentials_from_env()

    if env_credentials:
        print(f"  ✓ Environment variables detected")
        print()
        print("  Credential status:")
        # Show detailed status for each credential
        required_vars = ['org_id', 'client_id', 'secret']
        optional_vars = ['scopes', 'sandbox']
        for var in required_vars:
            env_name = ENV_VAR_MAPPING.get(var, var.upper())
            if var in env_credentials and env_credentials[var]:
                # Mask sensitive values
                value = env_credentials[var]
                if var in ['secret', 'client_id']:
                    masked = value[:4] + '****' + value[-4:] if len(value) > 8 else '****'
                else:
                    masked = value
                print(f"    ✓ {env_name}: {masked}")
            else:
                print(f"    ✗ {env_name}: not set (required)")
        for var in optional_vars:
            env_name = ENV_VAR_MAPPING.get(var, var.upper())
            if var in env_credentials and env_credentials[var]:
                print(f"    ✓ {env_name}: {env_credentials[var]}")
            else:
                print(f"    - {env_name}: not set (optional)")
        print()
        if validate_env_credentials(env_credentials, logging.getLogger(__name__)):
            print(f"  ✓ Environment credentials are valid")
            print(f"  → Using: Environment variables")
        else:
            print(f"  ⚠ Environment credentials incomplete, checking config file...")
            env_credentials = None  # Fall through to config file check
    else:
        print(f"  - No environment variables set")

    # Step 2: Check config file if no valid env credentials
    if not env_credentials:
        print()
        print("[2/3] Checking configuration file...")
        config_path = Path(config_file)
        if config_path.exists():
            abs_path = config_path.resolve()
            print(f"  ✓ Config file found: {abs_path}")
            try:
                with open(config_file, 'r') as f:
                    config = json.load(f)
                print(f"  ✓ Config file is valid JSON")
                print()
                print("  Credential status:")

                # Show detailed status for each field
                required_fields = ['org_id', 'client_id', 'secret']
                optional_fields = ['scopes', 'sandbox']
                missing = []

                for field in required_fields:
                    if field in config and config[field]:
                        value = config[field]
                        if field in ['secret', 'client_id']:
                            masked = value[:4] + '****' + value[-4:] if len(value) > 8 else '****'
                        else:
                            masked = value
                        print(f"    ✓ {field}: {masked}")
                    else:
                        print(f"    ✗ {field}: not set (required)")
                        missing.append(field)

                for field in optional_fields:
                    if field in config and config[field]:
                        print(f"    ✓ {field}: {config[field]}")
                    else:
                        print(f"    - {field}: not set (optional)")

                print()
                if missing:
                    print(f"  ✗ Missing required fields: {', '.join(missing)}")
                    all_passed = False
                else:
                    print(f"  ✓ All required fields present")
                    print(f"  → Using: Config file ({config_file})")
            except json.JSONDecodeError as e:
                print(f"  ✗ Invalid JSON: {str(e)}")
                all_passed = False
        else:
            print(f"  ✗ Config file not found: {config_file}")
            print()
            print("  To create a sample config file:")
            print("    python cja_sdr_generator.py --sample-config")
            print()
            print("  Or set environment variables:")
            print("    export ORG_ID=your_org_id@AdobeOrg")
            print("    export CLIENT_ID=your_client_id")
            print("    export SECRET=your_client_secret")
            all_passed = False
    else:
        print()
        print("[2/3] Skipping config file check (using environment credentials)")

    if not all_passed:
        print()
        print("=" * 60)
        print(ConsoleColors.error("VALIDATION FAILED - Fix issues above"))
        print("=" * 60)
        return False

    # Step 3: Test API connection
    print()
    print("[3/3] Testing API connection...")
    try:
        # Initialize CJA (will use env vars or config file automatically)
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.WARNING)  # Suppress normal output

        if env_credentials:
            _config_from_env(env_credentials, logger)
        else:
            cjapy.importConfigFile(config_file)

        cja = cjapy.CJA()
        print(f"  ✓ CJA client initialized")

        # Test connection with API call
        available_dvs = cja.getDataViews()
        if available_dvs is not None:
            dv_count = len(available_dvs) if hasattr(available_dvs, '__len__') else 0
            print(f"  ✓ API connection successful")
            print(f"  ✓ Found {dv_count} accessible data view(s)")
        else:
            print(f"  ⚠ API returned empty response - connection may be unstable")

    except (KeyboardInterrupt, SystemExit):
        print()
        print(ConsoleColors.warning("Validation cancelled."))
        raise
    except Exception as e:
        print(f"  ✗ API connection failed: {str(e)}")
        all_passed = False

    # Summary
    print()
    print("=" * 60)
    if all_passed:
        print(ConsoleColors.success("VALIDATION PASSED - Configuration is valid!"))
    else:
        print(ConsoleColors.error("VALIDATION FAILED - Check errors above"))
    print("=" * 60)

    return all_passed


# ==================== STATS COMMAND ====================

def show_stats(data_views: List[str], config_file: str = "config.json",
               output_format: str = "table", output_file: Optional[str] = None,
               quiet: bool = False) -> bool:
    """
    Show quick statistics about data view(s) without generating full reports.

    Args:
        data_views: List of data view IDs to get stats for
        config_file: Path to CJA configuration file
        output_format: Output format - "table" (default), "json", or "csv"
        output_file: Optional file path to write output (or "-" for stdout)
        quiet: Suppress decorative output

    Returns:
        True if successful, False otherwise
    """
    is_stdout = output_file in ('-', 'stdout')
    is_machine_readable = output_format in ('json', 'csv') or is_stdout

    if not is_machine_readable and not quiet:
        print()
        print("=" * 60)
        print("DATA VIEW STATISTICS")
        print("=" * 60)
        print()

    try:
        cjapy.importConfigFile(config_file)
        cja = cjapy.CJA()

        stats_data = []

        for dv_id in data_views:
            try:
                # Get data view info
                dv_info = cja.getDataView(dv_id)
                dv_name = dv_info.get('name', 'Unknown') if isinstance(dv_info, dict) else 'Unknown'

                # Get metrics and dimensions
                metrics_df = cja.getMetrics(dv_id)
                dimensions_df = cja.getDimensions(dv_id)

                metrics_count = len(metrics_df) if metrics_df is not None and not metrics_df.empty else 0
                dimensions_count = len(dimensions_df) if dimensions_df is not None and not dimensions_df.empty else 0

                # Get owner info
                owner_info = dv_info.get('owner', {}) if isinstance(dv_info, dict) else {}
                owner_name = owner_info.get('name', 'N/A') if isinstance(owner_info, dict) else 'N/A'

                # Get description
                description = dv_info.get('description', '') if isinstance(dv_info, dict) else ''

                stats_data.append({
                    'id': dv_id,
                    'name': dv_name,
                    'owner': owner_name,
                    'metrics': metrics_count,
                    'dimensions': dimensions_count,
                    'total_components': metrics_count + dimensions_count,
                    'description': description[:100] + '...' if len(description) > 100 else description
                })

            except Exception as e:
                stats_data.append({
                    'id': dv_id,
                    'name': 'ERROR',
                    'owner': 'N/A',
                    'metrics': 0,
                    'dimensions': 0,
                    'total_components': 0,
                    'description': f'Error: {str(e)}'
                })

        # Output based on format
        if output_format == 'json' or (is_stdout and output_format != 'csv'):
            output_data = json.dumps({
                "stats": stats_data,
                "count": len(stats_data),
                "totals": {
                    "metrics": sum(s['metrics'] for s in stats_data),
                    "dimensions": sum(s['dimensions'] for s in stats_data),
                    "components": sum(s['total_components'] for s in stats_data)
                }
            }, indent=2)
            if is_stdout:
                print(output_data)
            elif output_file:
                with open(output_file, 'w') as f:
                    f.write(output_data)
            else:
                print(output_data)
        elif output_format == 'csv':
            lines = ["id,name,owner,metrics,dimensions,total_components"]
            for item in stats_data:
                name = item['name'].replace('"', '""')
                owner = item['owner'].replace('"', '""')
                lines.append(f'{item["id"]},"{name}","{owner}",{item["metrics"]},{item["dimensions"]},{item["total_components"]}')
            output_data = '\n'.join(lines)
            if is_stdout:
                print(output_data)
            elif output_file:
                with open(output_file, 'w') as f:
                    f.write(output_data)
            else:
                print(output_data)
        else:
            # Table format
            if stats_data:
                # Calculate column widths
                max_id_width = max(len('ID'), max(len(s['id']) for s in stats_data)) + 2
                max_name_width = min(40, max(len('Name'), max(len(s['name']) for s in stats_data)) + 2)

                # Print header
                header = f"{'ID':<{max_id_width}} {'Name':<{max_name_width}} {'Metrics':>8} {'Dims':>8} {'Total':>8}"
                print(header)
                print("-" * len(header))

                # Print data
                for item in stats_data:
                    name = item['name'][:max_name_width-2] + '..' if len(item['name']) > max_name_width-2 else item['name']
                    print(f"{item['id']:<{max_id_width}} {name:<{max_name_width}} {item['metrics']:>8} {item['dimensions']:>8} {item['total_components']:>8}")

                # Print totals
                print("-" * len(header))
                total_metrics = sum(s['metrics'] for s in stats_data)
                total_dims = sum(s['dimensions'] for s in stats_data)
                total_all = sum(s['total_components'] for s in stats_data)
                print(f"{'TOTAL':<{max_id_width}} {'':<{max_name_width}} {total_metrics:>8} {total_dims:>8} {total_all:>8}")

            print()
            print("=" * 60)

        return True

    except FileNotFoundError:
        if is_machine_readable:
            error_json = json.dumps({"error": f"Configuration file '{config_file}' not found"})
            print(error_json, file=sys.stderr if is_stdout else sys.stdout)
        else:
            print(ConsoleColors.error(f"ERROR: Configuration file '{config_file}' not found"))
        return False

    except (KeyboardInterrupt, SystemExit):
        if not is_machine_readable:
            print()
            print(ConsoleColors.warning("Operation cancelled."))
        raise

    except Exception as e:
        if is_machine_readable:
            error_json = json.dumps({"error": f"Failed to get stats: {str(e)}"})
            print(error_json, file=sys.stderr if is_stdout else sys.stdout)
        else:
            print(ConsoleColors.error(f"ERROR: Failed to get stats: {str(e)}"))
        return False


# ==================== DIFF AND SNAPSHOT COMMAND HANDLERS ====================

def handle_snapshot_command(data_view_id: str, snapshot_file: str, config_file: str = "config.json",
                            quiet: bool = False) -> bool:
    """
    Handle the --snapshot command to save a data view snapshot.

    Args:
        data_view_id: The data view ID to snapshot
        snapshot_file: Path to save the snapshot
        config_file: Path to CJA configuration file
        quiet: Suppress progress output

    Returns:
        True if successful, False otherwise
    """
    try:
        if not quiet:
            print()
            print("=" * 60)
            print("CREATING DATA VIEW SNAPSHOT")
            print("=" * 60)
            print(f"Data View: {data_view_id}")
            print(f"Output: {snapshot_file}")
            print()

        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO if not quiet else logging.WARNING)

        # Initialize CJA
        cjapy.importConfigFile(config_file)
        cja = cjapy.CJA()

        # Create and save snapshot
        snapshot_manager = SnapshotManager(logger)
        snapshot = snapshot_manager.create_snapshot(cja, data_view_id, quiet)
        saved_path = snapshot_manager.save_snapshot(snapshot, snapshot_file)

        if not quiet:
            print()
            print("=" * 60)
            print(ConsoleColors.success("SNAPSHOT CREATED SUCCESSFULLY"))
            print("=" * 60)
            print(f"Data View: {snapshot.data_view_name} ({snapshot.data_view_id})")
            print(f"Metrics: {len(snapshot.metrics)}")
            print(f"Dimensions: {len(snapshot.dimensions)}")
            print(f"Saved to: {saved_path}")
            print("=" * 60)

        return True

    except Exception as e:
        print(ConsoleColors.error(f"ERROR: Failed to create snapshot: {str(e)}"), file=sys.stderr)
        return False


def handle_diff_command(source_id: str, target_id: str, config_file: str = "config.json",
                        output_format: str = "console", output_dir: str = ".",
                        changes_only: bool = False, summary_only: bool = False,
                        ignore_fields: Optional[List[str]] = None, labels: Optional[Tuple[str, str]] = None,
                        quiet: bool = False, show_only: Optional[List[str]] = None,
                        metrics_only: bool = False, dimensions_only: bool = False,
                        extended_fields: bool = False, side_by_side: bool = False,
                        no_color: bool = False, quiet_diff: bool = False,
                        reverse_diff: bool = False, warn_threshold: Optional[float] = None,
                        group_by_field: bool = False, diff_output: Optional[str] = None,
                        format_pr_comment: bool = False, auto_snapshot: bool = False,
                        snapshot_dir: str = "./snapshots", keep_last: int = 0) -> Tuple[bool, bool, Optional[int]]:
    """
    Handle the --diff command to compare two data views.

    Args:
        source_id: Source data view ID
        target_id: Target data view ID
        config_file: Path to CJA configuration file
        output_format: Output format
        output_dir: Output directory
        changes_only: Only show changed items
        summary_only: Only show summary
        ignore_fields: Fields to ignore
        labels: Custom labels (source_label, target_label)
        quiet: Suppress progress output
        show_only: Filter to show only specific change types
        metrics_only: Only compare metrics
        dimensions_only: Only compare dimensions
        extended_fields: Use extended field comparison
        side_by_side: Show side-by-side comparison view
        no_color: Disable ANSI color codes
        quiet_diff: Suppress output, only return exit code
        reverse_diff: Swap source and target
        warn_threshold: Exit with code 3 if change % exceeds threshold
        group_by_field: Group changes by field name
        diff_output: Write output to file instead of stdout
        format_pr_comment: Output in PR comment format
        auto_snapshot: Automatically save snapshots during diff
        snapshot_dir: Directory for auto-saved snapshots
        keep_last: Retention policy - keep only last N snapshots per data view (0 = keep all)

    Returns:
        Tuple of (success, has_changes, exit_code_override)
        exit_code_override is 3 if warn_threshold exceeded, None otherwise
    """
    try:
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO if not quiet else logging.WARNING)

        # Handle reverse diff - swap source and target
        if reverse_diff:
            source_id, target_id = target_id, source_id

        if not quiet and not quiet_diff:
            print()
            print("=" * 60)
            print("COMPARING DATA VIEWS")
            print("=" * 60)
            print(f"Source: {source_id}")
            print(f"Target: {target_id}")
            if reverse_diff:
                print("(Reversed comparison)")
            print()

        # Initialize CJA
        cjapy.importConfigFile(config_file)
        cja = cjapy.CJA()

        # Create snapshots from live data views
        snapshot_manager = SnapshotManager(logger)

        if not quiet and not quiet_diff:
            print("Fetching source data view...")
        source_snapshot = snapshot_manager.create_snapshot(cja, source_id, quiet or quiet_diff)

        if not quiet and not quiet_diff:
            print("Fetching target data view...")
        target_snapshot = snapshot_manager.create_snapshot(cja, target_id, quiet or quiet_diff)

        # Auto-save snapshots if enabled
        if auto_snapshot:
            os.makedirs(snapshot_dir, exist_ok=True)

            # Save source snapshot
            source_filename = snapshot_manager.generate_snapshot_filename(
                source_id, source_snapshot.data_view_name
            )
            source_path = os.path.join(snapshot_dir, source_filename)
            snapshot_manager.save_snapshot(source_snapshot, source_path)

            # Save target snapshot
            target_filename = snapshot_manager.generate_snapshot_filename(
                target_id, target_snapshot.data_view_name
            )
            target_path = os.path.join(snapshot_dir, target_filename)
            snapshot_manager.save_snapshot(target_snapshot, target_path)

            if not quiet and not quiet_diff:
                print(f"Auto-saved snapshots to: {snapshot_dir}/")
                print(f"  - {source_filename}")
                print(f"  - {target_filename}")

            # Apply retention policy if configured
            if keep_last > 0:
                deleted_source = snapshot_manager.apply_retention_policy(
                    snapshot_dir, source_id, keep_last
                )
                deleted_target = snapshot_manager.apply_retention_policy(
                    snapshot_dir, target_id, keep_last
                )
                total_deleted = len(deleted_source) + len(deleted_target)
                if total_deleted > 0 and not quiet and not quiet_diff:
                    print(f"  Retention policy: Deleted {total_deleted} old snapshot(s)")

            if not quiet and not quiet_diff:
                print()

        # Compare
        source_label = labels[0] if labels else "Source"
        target_label = labels[1] if labels else "Target"

        comparator = DataViewComparator(
            logger,
            ignore_fields=ignore_fields,
            use_extended_fields=extended_fields,
            show_only=show_only,
            metrics_only=metrics_only,
            dimensions_only=dimensions_only
        )
        diff_result = comparator.compare(source_snapshot, target_snapshot, source_label, target_label)

        # Check warn threshold
        exit_code_override = None
        if warn_threshold is not None:
            max_change_pct = max(
                diff_result.summary.metrics_change_percent,
                diff_result.summary.dimensions_change_percent
            )
            if max_change_pct > warn_threshold:
                exit_code_override = 3
                if not quiet_diff:
                    print(ConsoleColors.warning(
                        f"WARNING: Change threshold exceeded! {max_change_pct:.1f}% > {warn_threshold}%"
                    ), file=sys.stderr)

        # Generate output (unless quiet_diff is set)
        if not quiet_diff:
            # Determine effective format
            effective_format = 'pr-comment' if format_pr_comment else output_format

            base_filename = f"diff_{source_id}_{target_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            output_content = write_diff_output(
                diff_result, effective_format, base_filename, output_dir, logger,
                changes_only, summary_only, side_by_side, use_color=not no_color,
                group_by_field=group_by_field
            )

            # Handle --diff-output flag
            if diff_output and output_content:
                with open(diff_output, 'w', encoding='utf-8') as f:
                    f.write(output_content)
                if not quiet:
                    print(f"Diff output written to: {diff_output}")

            if not quiet and output_format != 'console':
                print()
                print(ConsoleColors.success("Diff report generated successfully"))

        return True, diff_result.summary.has_changes, exit_code_override

    except Exception as e:
        print(ConsoleColors.error(f"ERROR: Failed to compare data views: {str(e)}"), file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False, False, None


def handle_diff_snapshot_command(data_view_id: str, snapshot_file: str, config_file: str = "config.json",
                                  output_format: str = "console", output_dir: str = ".",
                                  changes_only: bool = False, summary_only: bool = False,
                                  ignore_fields: Optional[List[str]] = None, labels: Optional[Tuple[str, str]] = None,
                                  quiet: bool = False, show_only: Optional[List[str]] = None,
                                  metrics_only: bool = False, dimensions_only: bool = False,
                                  extended_fields: bool = False, side_by_side: bool = False,
                                  no_color: bool = False, quiet_diff: bool = False,
                                  reverse_diff: bool = False, warn_threshold: Optional[float] = None,
                                  group_by_field: bool = False, diff_output: Optional[str] = None,
                                  format_pr_comment: bool = False, auto_snapshot: bool = False,
                                  snapshot_dir: str = "./snapshots", keep_last: int = 0) -> Tuple[bool, bool, Optional[int]]:
    """
    Handle the --diff-snapshot command to compare a data view against a saved snapshot.

    Args:
        data_view_id: The current data view ID to compare
        snapshot_file: Path to the saved snapshot file
        config_file: Path to CJA configuration file
        output_format: Output format
        output_dir: Output directory
        changes_only: Only show changed items
        summary_only: Only show summary
        ignore_fields: Fields to ignore
        labels: Custom labels (source_label, target_label)
        quiet: Suppress progress output
        show_only: Filter to show only specific change types
        metrics_only: Only compare metrics
        dimensions_only: Only compare dimensions
        extended_fields: Use extended field comparison
        side_by_side: Show side-by-side comparison view
        no_color: Disable ANSI color codes
        quiet_diff: Suppress output, only return exit code
        reverse_diff: Swap source and target
        warn_threshold: Exit with code 3 if change % exceeds threshold
        group_by_field: Group changes by field name
        diff_output: Write output to file instead of stdout
        format_pr_comment: Output in PR comment format
        auto_snapshot: Automatically save snapshot of current data view state
        snapshot_dir: Directory for auto-saved snapshots
        keep_last: Retention policy - keep only last N snapshots per data view (0 = keep all)

    Returns:
        Tuple of (success, has_changes, exit_code_override)
    """
    try:
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO if not quiet else logging.WARNING)

        if not quiet and not quiet_diff:
            print()
            print("=" * 60)
            print("COMPARING DATA VIEW AGAINST SNAPSHOT")
            print("=" * 60)
            print(f"Data View: {data_view_id}")
            print(f"Snapshot: {snapshot_file}")
            if reverse_diff:
                print("(Reversed comparison)")
            print()

        # Load the saved snapshot (source/baseline)
        snapshot_manager = SnapshotManager(logger)
        source_snapshot = snapshot_manager.load_snapshot(snapshot_file)

        # Initialize CJA and create current snapshot (target)
        cjapy.importConfigFile(config_file)
        cja = cjapy.CJA()

        if not quiet and not quiet_diff:
            print("Fetching current data view state...")
        target_snapshot = snapshot_manager.create_snapshot(cja, data_view_id, quiet or quiet_diff)

        # Auto-save current state snapshot if enabled
        if auto_snapshot:
            os.makedirs(snapshot_dir, exist_ok=True)

            # Save current state snapshot
            current_filename = snapshot_manager.generate_snapshot_filename(
                data_view_id, target_snapshot.data_view_name
            )
            current_path = os.path.join(snapshot_dir, current_filename)
            snapshot_manager.save_snapshot(target_snapshot, current_path)

            if not quiet and not quiet_diff:
                print(f"Auto-saved current state to: {snapshot_dir}/{current_filename}")

            # Apply retention policy if configured
            if keep_last > 0:
                deleted = snapshot_manager.apply_retention_policy(
                    snapshot_dir, data_view_id, keep_last
                )
                if deleted and not quiet and not quiet_diff:
                    print(f"  Retention policy: Deleted {len(deleted)} old snapshot(s)")

            if not quiet and not quiet_diff:
                print()

        # Handle reverse_diff - swap source and target
        if reverse_diff:
            source_snapshot, target_snapshot = target_snapshot, source_snapshot

        # Compare (snapshot is baseline/source, current state is target)
        source_label = labels[0] if labels else f"Snapshot ({source_snapshot.created_at[:10]})"
        target_label = labels[1] if labels else "Current"

        comparator = DataViewComparator(
            logger,
            ignore_fields=ignore_fields,
            use_extended_fields=extended_fields,
            show_only=show_only,
            metrics_only=metrics_only,
            dimensions_only=dimensions_only
        )
        diff_result = comparator.compare(source_snapshot, target_snapshot, source_label, target_label)

        # Check warn threshold
        exit_code_override = None
        if warn_threshold is not None:
            max_change_pct = max(
                diff_result.summary.metrics_change_percent,
                diff_result.summary.dimensions_change_percent
            )
            if max_change_pct > warn_threshold:
                exit_code_override = 3
                if not quiet_diff:
                    print(ConsoleColors.warning(
                        f"WARNING: Change threshold exceeded! {max_change_pct:.1f}% > {warn_threshold}%"
                    ), file=sys.stderr)

        # Generate output (unless quiet_diff is set)
        if not quiet_diff:
            # Determine effective format
            effective_format = 'pr-comment' if format_pr_comment else output_format

            base_filename = f"diff_{data_view_id}_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            output_content = write_diff_output(
                diff_result, effective_format, base_filename, output_dir, logger,
                changes_only, summary_only, side_by_side, use_color=not no_color,
                group_by_field=group_by_field
            )

            # Handle --diff-output flag
            if diff_output and output_content:
                with open(diff_output, 'w', encoding='utf-8') as f:
                    f.write(output_content)
                if not quiet:
                    print(f"Diff output written to: {diff_output}")

            if not quiet and output_format != 'console':
                print()
                print(ConsoleColors.success("Diff report generated successfully"))

        return True, diff_result.summary.has_changes, exit_code_override

    except FileNotFoundError as e:
        print(ConsoleColors.error(f"ERROR: Snapshot file not found: {snapshot_file}"), file=sys.stderr)
        return False, False, None
    except ValueError as e:
        print(ConsoleColors.error(f"ERROR: Invalid snapshot file: {str(e)}"), file=sys.stderr)
        return False, False, None
    except Exception as e:
        print(ConsoleColors.error(f"ERROR: Failed to compare against snapshot: {str(e)}"), file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False, False, None


def handle_compare_snapshots_command(source_file: str, target_file: str,
                                      output_format: str = "console", output_dir: str = ".",
                                      changes_only: bool = False, summary_only: bool = False,
                                      ignore_fields: Optional[List[str]] = None, labels: Optional[Tuple[str, str]] = None,
                                      quiet: bool = False, show_only: Optional[List[str]] = None,
                                      metrics_only: bool = False, dimensions_only: bool = False,
                                      extended_fields: bool = False, side_by_side: bool = False,
                                      no_color: bool = False, quiet_diff: bool = False,
                                      reverse_diff: bool = False, warn_threshold: Optional[float] = None,
                                      group_by_field: bool = False, diff_output: Optional[str] = None,
                                      format_pr_comment: bool = False) -> Tuple[bool, bool, Optional[int]]:
    """
    Handle the --compare-snapshots command to compare two snapshot files directly.

    This is useful for:
    - Comparing snapshots from different points in time
    - Offline comparison without API access
    - CI/CD pipelines where you want to compare pre/post snapshots

    Args:
        source_file: Path to the source (baseline) snapshot file
        target_file: Path to the target snapshot file
        output_format: Output format
        output_dir: Output directory
        changes_only: Only show changed items
        summary_only: Only show summary
        ignore_fields: Fields to ignore
        labels: Custom labels (source_label, target_label)
        quiet: Suppress progress output
        show_only: Filter to show only specific change types
        metrics_only: Only compare metrics
        dimensions_only: Only compare dimensions
        extended_fields: Use extended field comparison
        side_by_side: Show side-by-side comparison view
        no_color: Disable ANSI color codes
        quiet_diff: Suppress output, only return exit code
        reverse_diff: Swap source and target
        warn_threshold: Exit with code 3 if change % exceeds threshold
        group_by_field: Group changes by field name
        diff_output: Write output to file instead of stdout
        format_pr_comment: Output in PR comment format

    Returns:
        Tuple of (success, has_changes, exit_code_override)
    """
    try:
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO if not quiet else logging.WARNING)

        if not quiet and not quiet_diff:
            print()
            print("=" * 60)
            print("COMPARING TWO SNAPSHOTS")
            print("=" * 60)
            print(f"Source: {source_file}")
            print(f"Target: {target_file}")
            if reverse_diff:
                print("(Reversed comparison)")
            print()

        # Load both snapshots
        snapshot_manager = SnapshotManager(logger)

        if not quiet and not quiet_diff:
            print("Loading source snapshot...")
        source_snapshot = snapshot_manager.load_snapshot(source_file)

        if not quiet and not quiet_diff:
            print("Loading target snapshot...")
        target_snapshot = snapshot_manager.load_snapshot(target_file)

        # Handle reverse_diff - swap source and target
        if reverse_diff:
            source_snapshot, target_snapshot = target_snapshot, source_snapshot
            source_file, target_file = target_file, source_file

        # Determine labels
        if labels:
            source_label, target_label = labels
        else:
            # Use snapshot metadata for labels
            source_label = f"{source_snapshot.data_view_name} ({source_snapshot.created_at[:10]})"
            target_label = f"{target_snapshot.data_view_name} ({target_snapshot.created_at[:10]})"

        if not quiet and not quiet_diff:
            print(f"Comparing: {source_label} vs {target_label}")
            print()

        # Compare snapshots
        comparator = DataViewComparator(
            logger,
            ignore_fields=ignore_fields,
            use_extended_fields=extended_fields,
            show_only=show_only,
            metrics_only=metrics_only,
            dimensions_only=dimensions_only
        )
        diff_result = comparator.compare(source_snapshot, target_snapshot, source_label, target_label)

        # Check warn threshold
        exit_code_override = None
        if warn_threshold is not None:
            max_change_pct = max(
                diff_result.summary.metrics_change_percent,
                diff_result.summary.dimensions_change_percent
            )
            if max_change_pct > warn_threshold:
                exit_code_override = 3
                if not quiet_diff:
                    print(ConsoleColors.warning(
                        f"WARNING: Change threshold exceeded! {max_change_pct:.1f}% > {warn_threshold}%"
                    ), file=sys.stderr)

        # Generate output (unless quiet_diff is set)
        if not quiet_diff:
            # Determine effective format
            effective_format = 'pr-comment' if format_pr_comment else output_format

            # Generate base filename from snapshot names
            source_base = Path(source_file).stem
            target_base = Path(target_file).stem
            base_filename = f"diff_{source_base}_vs_{target_base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}"

            output_content = write_diff_output(
                diff_result, effective_format, base_filename, output_dir, logger,
                changes_only, summary_only, side_by_side, use_color=not no_color,
                group_by_field=group_by_field
            )

            # Handle --diff-output flag
            if diff_output and output_content:
                with open(diff_output, 'w', encoding='utf-8') as f:
                    f.write(output_content)
                if not quiet:
                    print(f"Diff output written to: {diff_output}")

            if not quiet and output_format != 'console':
                print()
                print(ConsoleColors.success("Diff report generated successfully"))

        return True, diff_result.summary.has_changes, exit_code_override

    except FileNotFoundError as e:
        print(ConsoleColors.error(f"ERROR: Snapshot file not found: {str(e)}"), file=sys.stderr)
        return False, False, None
    except ValueError as e:
        print(ConsoleColors.error(f"ERROR: Invalid snapshot file: {str(e)}"), file=sys.stderr)
        return False, False, None
    except Exception as e:
        print(ConsoleColors.error(f"ERROR: Failed to compare snapshots: {str(e)}"), file=sys.stderr)
        import traceback
        traceback.print_exc()
        return False, False, None


# ==================== MAIN FUNCTION ====================

def main():
    """Main entry point for the script"""
    main_start_time = time.time()

    # Parse arguments (will show error and help if no data views provided)
    try:
        args = parse_arguments()
    except SystemExit as e:
        # argparse calls sys.exit() on error or --help
        # Re-raise to maintain expected behavior
        raise

    # Validate numeric parameter bounds
    if args.workers < 1:
        print(ConsoleColors.error("ERROR: --workers must be at least 1"), file=sys.stderr)
        sys.exit(1)
    if args.workers > MAX_BATCH_WORKERS:
        print(ConsoleColors.error(f"ERROR: --workers cannot exceed {MAX_BATCH_WORKERS}"), file=sys.stderr)
        sys.exit(1)
    if args.cache_size < 1:
        print(ConsoleColors.error("ERROR: --cache-size must be at least 1"), file=sys.stderr)
        sys.exit(1)
    if args.cache_ttl < 1:
        print(ConsoleColors.error("ERROR: --cache-ttl must be at least 1 second"), file=sys.stderr)
        sys.exit(1)
    if args.max_issues < 0:
        print(ConsoleColors.error("ERROR: --max-issues cannot be negative"), file=sys.stderr)
        sys.exit(1)
    if args.max_retries < 0:
        print(ConsoleColors.error("ERROR: --max-retries cannot be negative"), file=sys.stderr)
        sys.exit(1)
    if args.retry_base_delay < 0:
        print(ConsoleColors.error("ERROR: --retry-base-delay cannot be negative"), file=sys.stderr)
        sys.exit(1)
    if args.retry_max_delay < args.retry_base_delay:
        print(ConsoleColors.error("ERROR: --retry-max-delay must be >= --retry-base-delay"), file=sys.stderr)
        sys.exit(1)

    # Update global retry config with CLI arguments
    DEFAULT_RETRY_CONFIG['max_retries'] = args.max_retries
    DEFAULT_RETRY_CONFIG['base_delay'] = args.retry_base_delay
    DEFAULT_RETRY_CONFIG['max_delay'] = args.retry_max_delay

    # Handle --output for stdout - implies quiet mode
    output_to_stdout = getattr(args, 'output', None) in ('-', 'stdout')
    if output_to_stdout:
        args.quiet = True

    # Handle --sample-config mode (no data view required)
    if args.sample_config:
        success = generate_sample_config()
        sys.exit(0 if success else 1)

    # Handle --git-init mode (no data view required)
    if getattr(args, 'git_init', False):
        git_dir = Path(getattr(args, 'git_dir', './sdr-snapshots'))
        print(f"Initializing Git repository at: {git_dir}")
        success, message = git_init_snapshot_repo(git_dir)
        if success:
            print(ConsoleColors.success(f"SUCCESS: {message}"))
            print(f"  Directory: {git_dir.absolute()}")
            print()
            print("Next steps:")
            print(f"  1. Run SDR generation with --git-commit to save and commit snapshots")
            print(f"  2. Add a remote: cd {git_dir} && git remote add origin <url>")
            print(f"  3. Use --git-push to push commits to remote")
        else:
            print(ConsoleColors.error(f"FAILED: {message}"))
        sys.exit(0 if success else 1)

    # Validate Git argument combinations
    if getattr(args, 'git_push', False) and not getattr(args, 'git_commit', False):
        print(ConsoleColors.error("ERROR: --git-push requires --git-commit"), file=sys.stderr)
        sys.exit(1)

    # Handle --list-dataviews mode (no data view required)
    if args.list_dataviews:
        # Determine format for list output
        list_format = 'table'
        if args.format in ('json', 'csv'):
            list_format = args.format
        elif output_to_stdout:
            list_format = 'json'  # Default to JSON for stdout

        success = list_dataviews(
            args.config_file,
            output_format=list_format,
            output_file=getattr(args, 'output', None)
        )
        sys.exit(0 if success else 1)

    # Handle --validate-config mode (no data view required)
    if args.validate_config:
        success = validate_config_only(args.config_file)
        sys.exit(0 if success else 1)

    # Get data views from arguments
    data_view_inputs = args.data_views

    # Handle --stats mode (requires data views)
    if getattr(args, 'stats', False):
        if not data_view_inputs:
            print(ConsoleColors.error("ERROR: --stats requires at least one data view ID or name"), file=sys.stderr)
            sys.exit(1)

        # Resolve data view names first
        temp_logger = logging.getLogger('name_resolution')
        temp_logger.setLevel(logging.WARNING)
        resolved_ids, _ = resolve_data_view_names(data_view_inputs, args.config_file, temp_logger)

        if not resolved_ids:
            print(ConsoleColors.error("ERROR: No valid data views found"), file=sys.stderr)
            sys.exit(1)

        # Determine format for stats output
        stats_format = 'table'
        if args.format in ('json', 'csv'):
            stats_format = args.format
        elif output_to_stdout:
            stats_format = 'json'

        success = show_stats(
            resolved_ids,
            config_file=args.config_file,
            output_format=stats_format,
            output_file=getattr(args, 'output', None),
            quiet=args.quiet
        )
        sys.exit(0 if success else 1)

    # Parse ignore_fields if provided
    ignore_fields = None
    if hasattr(args, 'ignore_fields') and args.ignore_fields:
        ignore_fields = [f.strip() for f in args.ignore_fields.split(',')]

    # Parse show_only filter if provided
    show_only = None
    if hasattr(args, 'show_only') and args.show_only:
        show_only = [t.strip().lower() for t in args.show_only.split(',')]
        valid_types = {'added', 'removed', 'modified', 'unchanged'}
        invalid = set(show_only) - valid_types
        if invalid:
            print(ConsoleColors.error(f"ERROR: Invalid --show-only types: {invalid}"), file=sys.stderr)
            print(f"Valid types: {', '.join(valid_types)}", file=sys.stderr)
            sys.exit(1)

    # Parse labels if provided
    labels = None
    if hasattr(args, 'diff_labels') and args.diff_labels:
        labels = tuple(args.diff_labels)

    # Handle --compare-snapshots mode (compare two snapshot files directly)
    if hasattr(args, 'compare_snapshots') and args.compare_snapshots:
        source_file, target_file = args.compare_snapshots

        # Check for conflicting options
        if getattr(args, 'metrics_only', False) and getattr(args, 'dimensions_only', False):
            print(ConsoleColors.error("ERROR: Cannot use both --metrics-only and --dimensions-only"), file=sys.stderr)
            sys.exit(1)

        # Default to console for diff commands
        diff_format = args.format if args.format else 'console'
        success, has_changes, exit_code_override = handle_compare_snapshots_command(
            source_file=source_file,
            target_file=target_file,
            output_format=diff_format,
            output_dir=args.output_dir,
            changes_only=getattr(args, 'changes_only', False),
            summary_only=getattr(args, 'summary', False),
            ignore_fields=ignore_fields,
            labels=labels,
            quiet=args.quiet,
            show_only=show_only,
            metrics_only=getattr(args, 'metrics_only', False),
            dimensions_only=getattr(args, 'dimensions_only', False),
            extended_fields=getattr(args, 'extended_fields', False),
            side_by_side=getattr(args, 'side_by_side', False),
            no_color=getattr(args, 'no_color', False),
            quiet_diff=getattr(args, 'quiet_diff', False),
            reverse_diff=getattr(args, 'reverse_diff', False),
            warn_threshold=getattr(args, 'warn_threshold', None),
            group_by_field=getattr(args, 'group_by_field', False),
            diff_output=getattr(args, 'diff_output', None),
            format_pr_comment=getattr(args, 'format_pr_comment', False)
        )

        # Exit with code 3 if threshold exceeded, 2 if differences found, 0 if no changes
        if success:
            if exit_code_override is not None:
                sys.exit(exit_code_override)
            sys.exit(2 if has_changes else 0)
        else:
            sys.exit(1)

    # Handle --diff mode (compare two data views)
    if hasattr(args, 'diff') and args.diff:
        if len(data_view_inputs) != 2:
            print(ConsoleColors.error("ERROR: --diff requires exactly 2 data view IDs or names"), file=sys.stderr)
            print("Usage: cja_auto_sdr --diff DATA_VIEW_A DATA_VIEW_B", file=sys.stderr)
            sys.exit(1)

        # Check for conflicting options
        if getattr(args, 'metrics_only', False) and getattr(args, 'dimensions_only', False):
            print(ConsoleColors.error("ERROR: Cannot use both --metrics-only and --dimensions-only"), file=sys.stderr)
            sys.exit(1)

        # Resolve names to IDs if needed - resolve EACH identifier separately
        # to ensure 1:1 mapping for diff comparison
        temp_logger = logging.getLogger('name_resolution')
        temp_logger.setLevel(logging.WARNING)

        source_input = data_view_inputs[0]
        target_input = data_view_inputs[1]

        # Resolve source identifier
        source_resolved, source_map = resolve_data_view_names([source_input], args.config_file, temp_logger)
        if not source_resolved:
            print(ConsoleColors.error(f"ERROR: Could not resolve source data view: '{source_input}'"), file=sys.stderr)
            sys.exit(1)
        if len(source_resolved) > 1:
            # Ambiguous - try interactive selection if in terminal
            options = [(dv_id, f"{source_input} ({dv_id})") for dv_id in source_resolved]
            selected = prompt_for_selection(
                options,
                f"Source name '{source_input}' matches {len(source_resolved)} data views. Please select one:"
            )
            if selected:
                source_resolved = [selected]
            else:
                # Not interactive or user cancelled
                print(ConsoleColors.error(f"ERROR: Source name '{source_input}' is ambiguous - matches {len(source_resolved)} data views:"), file=sys.stderr)
                for dv_id in source_resolved:
                    print(f"  • {dv_id}", file=sys.stderr)
                print("\nPlease specify the exact data view ID instead of the name.", file=sys.stderr)
                sys.exit(1)

        # Resolve target identifier
        target_resolved, target_map = resolve_data_view_names([target_input], args.config_file, temp_logger)
        if not target_resolved:
            print(ConsoleColors.error(f"ERROR: Could not resolve target data view: '{target_input}'"), file=sys.stderr)
            sys.exit(1)
        if len(target_resolved) > 1:
            # Ambiguous - try interactive selection if in terminal
            options = [(dv_id, f"{target_input} ({dv_id})") for dv_id in target_resolved]
            selected = prompt_for_selection(
                options,
                f"Target name '{target_input}' matches {len(target_resolved)} data views. Please select one:"
            )
            if selected:
                target_resolved = [selected]
            else:
                # Not interactive or user cancelled
                print(ConsoleColors.error(f"ERROR: Target name '{target_input}' is ambiguous - matches {len(target_resolved)} data views:"), file=sys.stderr)
                for dv_id in target_resolved:
                    print(f"  • {dv_id}", file=sys.stderr)
                print("\nPlease specify the exact data view ID instead of the name.", file=sys.stderr)
                sys.exit(1)

        resolved_ids = [source_resolved[0], target_resolved[0]]

        # Default to console for diff commands
        diff_format = args.format if args.format else 'console'
        success, has_changes, exit_code_override = handle_diff_command(
            source_id=resolved_ids[0],
            target_id=resolved_ids[1],
            config_file=args.config_file,
            output_format=diff_format,
            output_dir=args.output_dir,
            changes_only=getattr(args, 'changes_only', False),
            summary_only=getattr(args, 'summary', False),
            ignore_fields=ignore_fields,
            labels=labels,
            quiet=args.quiet,
            show_only=show_only,
            metrics_only=getattr(args, 'metrics_only', False),
            dimensions_only=getattr(args, 'dimensions_only', False),
            extended_fields=getattr(args, 'extended_fields', False),
            side_by_side=getattr(args, 'side_by_side', False),
            no_color=getattr(args, 'no_color', False),
            quiet_diff=getattr(args, 'quiet_diff', False),
            reverse_diff=getattr(args, 'reverse_diff', False),
            warn_threshold=getattr(args, 'warn_threshold', None),
            group_by_field=getattr(args, 'group_by_field', False),
            diff_output=getattr(args, 'diff_output', None),
            format_pr_comment=getattr(args, 'format_pr_comment', False),
            auto_snapshot=getattr(args, 'auto_snapshot', False),
            snapshot_dir=getattr(args, 'snapshot_dir', './snapshots'),
            keep_last=getattr(args, 'keep_last', 0)
        )

        # Exit with code 3 if threshold exceeded, 2 if differences found, 0 if no changes
        if success:
            if exit_code_override is not None:
                sys.exit(exit_code_override)
            sys.exit(2 if has_changes else 0)
        else:
            sys.exit(1)

    # Handle --snapshot mode (save a data view snapshot)
    if hasattr(args, 'snapshot') and args.snapshot:
        if len(data_view_inputs) != 1:
            print(ConsoleColors.error("ERROR: --snapshot requires exactly 1 data view ID or name"), file=sys.stderr)
            print("Usage: cja_auto_sdr DATA_VIEW --snapshot ./snapshots/baseline.json", file=sys.stderr)
            sys.exit(1)

        # Resolve name to ID if needed - ensure 1:1 mapping
        temp_logger = logging.getLogger('name_resolution')
        temp_logger.setLevel(logging.WARNING)
        resolved_ids, _ = resolve_data_view_names(data_view_inputs, args.config_file, temp_logger)

        if not resolved_ids:
            print(ConsoleColors.error(f"ERROR: Could not resolve data view: '{data_view_inputs[0]}'"), file=sys.stderr)
            sys.exit(1)
        if len(resolved_ids) > 1:
            # Ambiguous - try interactive selection if in terminal
            dv_name = data_view_inputs[0]
            options = [(dv_id, f"{dv_name} ({dv_id})") for dv_id in resolved_ids]
            selected = prompt_for_selection(
                options,
                f"Name '{dv_name}' matches {len(resolved_ids)} data views. Please select one:"
            )
            if selected:
                resolved_ids = [selected]
            else:
                print(ConsoleColors.error(f"ERROR: Name '{dv_name}' is ambiguous - matches {len(resolved_ids)} data views:"), file=sys.stderr)
                for dv_id in resolved_ids:
                    print(f"  • {dv_id}", file=sys.stderr)
                print("\nPlease specify the exact data view ID instead of the name.", file=sys.stderr)
                sys.exit(1)

        success = handle_snapshot_command(
            data_view_id=resolved_ids[0],
            snapshot_file=args.snapshot,
            config_file=args.config_file,
            quiet=args.quiet
        )
        sys.exit(0 if success else 1)

    # Handle --diff-snapshot mode (compare against a saved snapshot)
    if hasattr(args, 'diff_snapshot') and args.diff_snapshot:
        if len(data_view_inputs) != 1:
            print(ConsoleColors.error("ERROR: --diff-snapshot requires exactly 1 data view ID or name"), file=sys.stderr)
            print("Usage: cja_auto_sdr DATA_VIEW --diff-snapshot ./snapshots/baseline.json", file=sys.stderr)
            sys.exit(1)

        # Check for conflicting options
        if getattr(args, 'metrics_only', False) and getattr(args, 'dimensions_only', False):
            print(ConsoleColors.error("ERROR: Cannot use both --metrics-only and --dimensions-only"), file=sys.stderr)
            sys.exit(1)

        # Resolve name to ID if needed - ensure 1:1 mapping
        temp_logger = logging.getLogger('name_resolution')
        temp_logger.setLevel(logging.WARNING)
        resolved_ids, _ = resolve_data_view_names(data_view_inputs, args.config_file, temp_logger)

        if not resolved_ids:
            print(ConsoleColors.error(f"ERROR: Could not resolve data view: '{data_view_inputs[0]}'"), file=sys.stderr)
            sys.exit(1)
        if len(resolved_ids) > 1:
            # Ambiguous - try interactive selection if in terminal
            dv_name = data_view_inputs[0]
            options = [(dv_id, f"{dv_name} ({dv_id})") for dv_id in resolved_ids]
            selected = prompt_for_selection(
                options,
                f"Name '{dv_name}' matches {len(resolved_ids)} data views. Please select one:"
            )
            if selected:
                resolved_ids = [selected]
            else:
                print(ConsoleColors.error(f"ERROR: Name '{dv_name}' is ambiguous - matches {len(resolved_ids)} data views:"), file=sys.stderr)
                for dv_id in resolved_ids:
                    print(f"  • {dv_id}", file=sys.stderr)
                print("\nPlease specify the exact data view ID instead of the name.", file=sys.stderr)
                sys.exit(1)

        # Default to console for diff commands
        diff_format = args.format if args.format else 'console'
        success, has_changes, exit_code_override = handle_diff_snapshot_command(
            data_view_id=resolved_ids[0],
            snapshot_file=args.diff_snapshot,
            config_file=args.config_file,
            output_format=diff_format,
            output_dir=args.output_dir,
            changes_only=getattr(args, 'changes_only', False),
            summary_only=getattr(args, 'summary', False),
            ignore_fields=ignore_fields,
            labels=labels,
            quiet=args.quiet,
            show_only=show_only,
            metrics_only=getattr(args, 'metrics_only', False),
            dimensions_only=getattr(args, 'dimensions_only', False),
            extended_fields=getattr(args, 'extended_fields', False),
            side_by_side=getattr(args, 'side_by_side', False),
            no_color=getattr(args, 'no_color', False),
            quiet_diff=getattr(args, 'quiet_diff', False),
            reverse_diff=getattr(args, 'reverse_diff', False),
            warn_threshold=getattr(args, 'warn_threshold', None),
            group_by_field=getattr(args, 'group_by_field', False),
            diff_output=getattr(args, 'diff_output', None),
            format_pr_comment=getattr(args, 'format_pr_comment', False),
            auto_snapshot=getattr(args, 'auto_snapshot', False),
            snapshot_dir=getattr(args, 'snapshot_dir', './snapshots'),
            keep_last=getattr(args, 'keep_last', 0)
        )

        # Exit with code 3 if threshold exceeded, 2 if differences found, 0 if no changes
        if success:
            if exit_code_override is not None:
                sys.exit(exit_code_override)
            sys.exit(2 if has_changes else 0)
        else:
            sys.exit(1)

    # Validate that at least one data view is provided
    if not data_view_inputs:
        print(ConsoleColors.error("ERROR: At least one data view ID or name is required"), file=sys.stderr)
        print("Usage: python cja_sdr_generator.py DATA_VIEW_ID_OR_NAME [DATA_VIEW_ID_OR_NAME ...]", file=sys.stderr)
        print("       Use --help for more information", file=sys.stderr)
        sys.exit(1)

    # Resolve data view names to IDs
    # Create a temporary logger for name resolution
    temp_logger = logging.getLogger('name_resolution')
    temp_logger.setLevel(logging.INFO if not args.quiet else logging.ERROR)
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
    temp_logger.addHandler(handler)
    temp_logger.propagate = False

    # Show what we're resolving
    ids_provided = [dv for dv in data_view_inputs if is_data_view_id(dv)]
    names_provided = [dv for dv in data_view_inputs if not is_data_view_id(dv)]

    if names_provided and not args.quiet:
        print()
        print(ConsoleColors.info(f"Resolving {len(names_provided)} data view name(s)..."))

    data_views, name_to_ids_map = resolve_data_view_names(data_view_inputs, args.config_file, temp_logger)

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
        print("  • Use quotes around names: cja_auto_sdr \"Production Analytics\"", file=sys.stderr)
        print("  • IDs start with 'dv_': cja_auto_sdr dv_12345", file=sys.stderr)
        print()
        print("Try running: python cja_sdr_generator.py --list-dataviews", file=sys.stderr)
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

    # Validate the resolved data view IDs
    if not args.quiet and names_provided:
        print(ConsoleColors.info(f"Processing {len(data_views)} data view(s) total..."))
        print()

    # Priority logic for log level: --quiet > --production > --log-level
    if args.quiet:
        effective_log_level = 'ERROR'
    elif args.production:
        effective_log_level = 'WARNING'
    else:
        effective_log_level = args.log_level

    # Handle dry-run mode
    if args.dry_run:
        logger = setup_logging(batch_mode=True, log_level='WARNING')
        success = run_dry_run(data_views, args.config_file, logger)
        sys.exit(0 if success else 1)

    # Default to excel for SDR generation
    sdr_format = args.format if args.format else 'excel'

    # Validate format - console is only supported for diff comparison
    if sdr_format == 'console':
        print(ConsoleColors.error("Error: Console format is only supported for diff comparison."))
        print()
        print("For SDR generation, use one of these formats:")
        print("  --format excel     Excel workbook with multiple sheets (default)")
        print("  --format csv       CSV files (one per data type)")
        print("  --format json      JSON file with all data")
        print("  --format html      HTML report")
        print("  --format markdown  Markdown document")
        print("  --format all       Generate all formats")
        print()
        print("For diff comparison, console is the default:")
        print("  cja_auto_sdr --diff dv_A dv_B              # Console output")
        print("  cja_auto_sdr --diff dv_A dv_B --format json  # JSON output")
        sys.exit(1)

    # Process data views
    if args.batch or len(data_views) > 1:
        # Batch mode - parallel processing
        if not args.quiet:
            print(ConsoleColors.info(f"Processing {len(data_views)} data view(s) in batch mode with {args.workers} workers..."))
            print()

        processor = BatchProcessor(
            config_file=args.config_file,
            output_dir=args.output_dir,
            workers=args.workers,
            continue_on_error=args.continue_on_error,
            log_level=effective_log_level,
            output_format=sdr_format,
            enable_cache=args.enable_cache,
            cache_size=args.cache_size,
            cache_ttl=args.cache_ttl,
            quiet=args.quiet,
            skip_validation=args.skip_validation,
            max_issues=args.max_issues,
            clear_cache=args.clear_cache
        )

        results = processor.process_batch(data_views)

        # Print total runtime
        total_runtime = time.time() - main_start_time
        print()
        print(ConsoleColors.bold(f"Total runtime: {total_runtime:.1f}s"))

        # Handle --open flag for batch mode (open all successful files)
        if getattr(args, 'open', False) and results.get('successful'):
            files_to_open = []
            for success_info in results['successful']:
                if isinstance(success_info, dict) and success_info.get('output_file'):
                    files_to_open.append(success_info['output_file'])
                elif hasattr(success_info, 'output_file') and success_info.output_file:
                    files_to_open.append(success_info.output_file)

            if files_to_open:
                print()
                print(f"Opening {len(files_to_open)} file(s)...")
                for file_path in files_to_open:
                    if not open_file_in_default_app(file_path):
                        print(ConsoleColors.warning(f"  Could not open: {file_path}"))

        # Exit with error code if any failed (unless continue-on-error)
        if results['failed'] and not args.continue_on_error:
            sys.exit(1)

    else:
        # Single mode - process one data view
        if not args.quiet:
            print(ConsoleColors.info(f"Processing data view: {data_views[0]}"))
            print()

        result = process_single_dataview(
            data_views[0],
            config_file=args.config_file,
            output_dir=args.output_dir,
            log_level=effective_log_level,
            output_format=sdr_format,
            enable_cache=args.enable_cache,
            cache_size=args.cache_size,
            cache_ttl=args.cache_ttl,
            quiet=args.quiet,
            skip_validation=args.skip_validation,
            max_issues=args.max_issues,
            clear_cache=args.clear_cache
        )

        # Print final status with color and total runtime
        total_runtime = time.time() - main_start_time
        print()
        if result.success:
            print(ConsoleColors.success(f"SUCCESS: SDR generated for {result.data_view_name}"))
            print(f"  Output: {result.output_file}")
            print(f"  Size: {result.file_size_formatted}")
            print(f"  Metrics: {result.metrics_count}, Dimensions: {result.dimensions_count}")
            if result.dq_issues_count > 0:
                print(ConsoleColors.warning(f"  Data Quality Issues: {result.dq_issues_count}"))

            # Handle --git-commit for single mode
            if getattr(args, 'git_commit', False):
                print()
                git_dir = Path(getattr(args, 'git_dir', './sdr-snapshots'))

                # Initialize repo if needed
                if not is_git_repository(git_dir):
                    print(f"Initializing Git repository at: {git_dir}")
                    init_success, init_msg = git_init_snapshot_repo(git_dir)
                    if not init_success:
                        print(ConsoleColors.error(f"Git init failed: {init_msg}"))
                    else:
                        print(ConsoleColors.success(f"  Repository initialized"))

                # Create snapshot for Git
                snapshot = DataViewSnapshot(
                    data_view_id=result.data_view_id,
                    data_view_name=result.data_view_name,
                    metrics=result.metrics_data if hasattr(result, 'metrics_data') else [],
                    dimensions=result.dimensions_data if hasattr(result, 'dimensions_data') else []
                )

                # If we don't have the raw data in result, we need to fetch it
                # For now, we'll create a minimal snapshot from available info
                if not snapshot.metrics and not snapshot.dimensions:
                    # Re-fetch data for Git snapshot
                    print("Fetching data for Git snapshot...")
                    try:
                        temp_logger = logging.getLogger('git_snapshot')
                        temp_logger.setLevel(logging.WARNING)
                        cja = initialize_cja(args.config_file, temp_logger)
                        if cja:
                            snapshot_mgr = SnapshotManager(temp_logger)
                            snapshot = snapshot_mgr.create_snapshot(cja, result.data_view_id, quiet=True)
                    except Exception as e:
                        print(ConsoleColors.warning(f"  Could not fetch snapshot data: {e}"))

                # Save Git-friendly snapshot
                print(f"Saving snapshot to: {git_dir}")
                saved_files = save_git_friendly_snapshot(
                    snapshot=snapshot,
                    output_dir=git_dir,
                    quality_issues=result.dq_issues if hasattr(result, 'dq_issues') else None
                )

                # Commit to Git
                git_push = getattr(args, 'git_push', False)
                git_message = getattr(args, 'git_message', None)

                commit_success, commit_result = git_commit_snapshot(
                    snapshot_dir=git_dir,
                    data_view_id=result.data_view_id,
                    data_view_name=result.data_view_name,
                    metrics_count=result.metrics_count,
                    dimensions_count=result.dimensions_count,
                    quality_issues=result.dq_issues if hasattr(result, 'dq_issues') else None,
                    custom_message=git_message,
                    push=git_push
                )

                if commit_success:
                    if commit_result == "no_changes":
                        print(ConsoleColors.info("  No changes to commit (snapshot unchanged)"))
                    else:
                        print(ConsoleColors.success(f"  Committed: {commit_result}"))
                        if git_push:
                            print(ConsoleColors.success("  Pushed to remote"))
                else:
                    print(ConsoleColors.error(f"  Git commit failed: {commit_result}"))

            # Handle --open flag for single mode
            if getattr(args, 'open', False) and result.output_file:
                print()
                print("Opening file...")
                if not open_file_in_default_app(result.output_file):
                    print(ConsoleColors.warning(f"  Could not open: {result.output_file}"))
        else:
            print(ConsoleColors.error(f"FAILED: {result.error_message}"))

        print(ConsoleColors.bold(f"Total runtime: {total_runtime:.1f}s"))

        if not result.success:
            sys.exit(1)

if __name__ == "__main__":
    main()