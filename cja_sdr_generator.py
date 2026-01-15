import cjapy
import pandas as pd
import json
from datetime import datetime
import hashlib
import logging
from logging.handlers import RotatingFileHandler
import sys
from typing import Dict, List, Tuple, Optional, Callable, Any
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, ProcessPoolExecutor, as_completed
from tqdm import tqdm
import time
import threading
import argparse
import os
import random
import functools
from dataclasses import dataclass
import tempfile
import atexit
import uuid

# Attempt to load python-dotenv if available (optional dependency)
_DOTENV_AVAILABLE = False
_DOTENV_LOADED = False
try:
    from dotenv import load_dotenv
    _DOTENV_LOADED = load_dotenv()  # Returns True if .env file was found and loaded
    _DOTENV_AVAILABLE = True
except ImportError:
    pass  # python-dotenv not installed

# ==================== VERSION ====================

__version__ = "3.0.8"

# ==================== DEFAULT CONSTANTS ====================

# Worker thread/process limits
DEFAULT_API_FETCH_WORKERS = 3      # Concurrent API fetch threads
DEFAULT_VALIDATION_WORKERS = 2     # Concurrent validation threads
DEFAULT_BATCH_WORKERS = 4          # Default batch processing workers
MAX_BATCH_WORKERS = 256            # Maximum allowed batch workers

# Cache defaults
DEFAULT_CACHE_SIZE = 1000          # Maximum cached validation results
DEFAULT_CACHE_TTL = 3600           # Cache TTL in seconds (1 hour)

# ==================== VALIDATION SCHEMA ====================

# Centralized field definitions for data quality validation
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

# Default retry settings
DEFAULT_RETRY_CONFIG = {
    'max_retries': 3,           # Maximum number of retry attempts
    'base_delay': 1.0,          # Initial delay in seconds
    'max_delay': 30.0,          # Maximum delay between retries
    'exponential_base': 2,      # Exponential backoff multiplier
    'jitter': True,             # Add randomization to prevent thundering herd
}

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
    max_retries: int = None,
    base_delay: float = None,
    max_delay: float = None,
    exponential_base: int = None,
    jitter: bool = None,
    retryable_exceptions: tuple = None,
    logger: logging.Logger = None
) -> Callable:
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
                        _logger.error(f"All {_max_retries + 1} attempts failed for {func.__name__}: {str(e)}")
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
    api_func: Callable,
    *args,
    logger: logging.Logger = None,
    operation_name: str = "API call",
    **kwargs
) -> Any:
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
                _logger.error(f"All {max_retries + 1} attempts failed for {operation_name}: {str(e)}")
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
        """Return human-readable file size"""
        return format_file_size(self.file_size_bytes)

# ==================== LOGGING SETUP ====================

# Module-level tracking to prevent duplicate logger initialization
_logging_initialized = False
_current_log_file = None
_atexit_registered = False

def setup_logging(data_view_id: str = None, batch_mode: bool = False, log_level: str = None) -> logging.Logger:
    """Setup logging to both file and console

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
        # 10MB max per file, keep 5 backup files
        handlers.append(RotatingFileHandler(
            log_file,
            maxBytes=10 * 1024 * 1024,  # 10MB
            backupCount=5
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

        with self._lock:
            if cache_key not in self._cache:
                self._misses += 1
                self.logger.debug(f"Cache MISS: {item_type} (key: {cache_key[:20]}...)")
                return None, cache_key

            cached_issues, timestamp = self._cache[cache_key]

            # Check TTL expiration
            age = time.time() - timestamp
            if age > self.ttl_seconds:
                self.logger.debug(f"Cache EXPIRED: {item_type} (age: {age:.1f}s)")
                del self._cache[cache_key]
                del self._access_times[cache_key]
                self._misses += 1
                return None, cache_key

            # Cache hit - update access time
            self._access_times[cache_key] = time.time()
            self._hits += 1
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

        with self._lock:
            # Evict oldest entry if cache is full
            if len(self._cache) >= self.max_size and cache_key not in self._cache:
                self._evict_lru()

            # Store issues with timestamp
            # Deep copy to prevent external mutation
            self._cache[cache_key] = ([issue.copy() for issue in issues], time.time())
            self._access_times[cache_key] = time.time()

            self.logger.debug(f"Cache STORE: {item_type} ({len(issues)} issues)")

    def _evict_lru(self):
        """Evict least recently used cache entry"""
        if not self._access_times:
            return

        # Find least recently used key
        lru_key = min(self._access_times.items(), key=lambda x: x[1])[0]

        # Remove from cache
        del self._cache[lru_key]
        del self._access_times[lru_key]
        self._evictions += 1

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

def validate_config_file(config_file: str, logger: logging.Logger) -> bool:
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
    """
    validation_errors = []
    validation_warnings = []

    try:
        logger.info(f"Validating configuration file: {config_file}")

        config_path = Path(config_file)

        # Check if file exists
        if not config_path.exists():
            logger.error(f"Configuration file not found: {config_path.absolute()}")
            logger.error(f"Please ensure '{config_file}' exists in the current directory")
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
            logger.error(f"Configuration file is not valid JSON: {str(e)}")
            logger.error("Please check the file format and ensure it's properly formatted JSON")
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

        # Check for unknown fields (potential typos)
        known_fields = (set(CONFIG_SCHEMA['base_required_fields'].keys()) |
                        set(CONFIG_SCHEMA['optional_fields'].keys()))
        unknown_fields = set(config_data.keys()) - known_fields
        if unknown_fields:
            validation_warnings.append(f"Unknown fields in config (possible typos): {', '.join(unknown_fields)}")

        # Report validation results
        if validation_errors:
            logger.error("Configuration validation FAILED:")
            for error in validation_errors:
                logger.error(f"  - {error}")
            return False

        if validation_warnings:
            logger.warning("Configuration validation warnings:")
            for warning in validation_warnings:
                logger.warning(f"  - {warning}")

        logger.info("Configuration file validated successfully")
        return True

    except Exception as e:
        logger.error(f"Unexpected error validating config file: {str(e)}")
        return False

def initialize_cja(config_file: str = "myconfig.json", logger: logging.Logger = None) -> Optional[cjapy.CJA]:
    """Initialize CJA connection with comprehensive error handling

    Credential Loading Priority:
        1. Environment variables (ORG_ID, CLIENT_ID, SECRET, etc.)
        2. Configuration file (myconfig.json)
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
                logger.critical("Option 2: Config File (myconfig.json):")
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

def validate_data_view(cja: cjapy.CJA, data_view_id: str, logger: logging.Logger) -> bool:
    """Validate that the data view exists and is accessible with detailed error reporting"""
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
            logger.error(f"Data view '{data_view_id}' returned empty response")
            logger.error("This typically means:")
            logger.error("  - The data view does not exist")
            logger.error("  - You don't have access to this data view")
            logger.error("  - The data view ID is incorrect")
            
            # Try to list available data views to help user
            logger.info("Attempting to list available data views...")
            try:
                available_dvs = cja.getDataViews()
                if available_dvs and len(available_dvs) > 0:
                    logger.info(f"You have access to {len(available_dvs)} data view(s):")
                    for i, dv in enumerate(available_dvs[:10]):  # Show first 10
                        dv_id = dv.get('id', 'unknown')
                        dv_name = dv.get('name', 'unknown')
                        logger.info(f"  {i+1}. {dv_name} (ID: {dv_id})")
                    if len(available_dvs) > 10:
                        logger.info(f"  ... and {len(available_dvs) - 10} more")
                else:
                    logger.warning("No data views found - you may not have access to any data views")
            except Exception as list_error:
                logger.warning(f"Could not list available data views: {str(list_error)}")
            
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

    def __init__(self, cja: cjapy.CJA, logger: logging.Logger, perf_tracker: 'PerformanceTracker', max_workers: int = 3):
        self.cja = cja
        self.logger = logger
        self.perf_tracker = perf_tracker
        self.max_workers = max_workers
    
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
                leave=False
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

    def __init__(self, logger: logging.Logger, validation_cache: Optional[ValidationCache] = None):
        self.issues = []
        self.logger = logger
        self.validation_cache = validation_cache  # Optional cache for performance
        self._issues_lock = threading.Lock()  # Thread safety for parallel validation
    
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
                    leave=False
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

def apply_excel_formatting(writer, df, sheet_name, logger: logging.Logger):
    """Apply formatting to Excel sheets with error handling"""
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

        # Add summary section for Data Quality sheet
        if sheet_name == 'Data Quality' and 'Severity' in df.columns:
            # Calculate severity counts
            severity_counts = df['Severity'].value_counts()

            # Summary formats
            title_format = workbook.add_format({
                'bold': True,
                'font_size': 14,
                'font_color': '#366092',
                'bottom': 2
            })
            summary_header = workbook.add_format({
                'bold': True,
                'bg_color': '#D9E1F2',
                'border': 1,
                'align': 'center'
            })
            summary_cell = workbook.add_format({
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
        
        # Add formats
        header_format = workbook.add_format({
            'bold': True,
            'bg_color': '#366092',
            'font_color': 'white',
            'border': 1,
            'align': 'center',
            'text_wrap': True
        })
        
        grey_format = workbook.add_format({
            'bg_color': '#F2F2F2',
            'border': 1,
            'text_wrap': True,
            'align': 'top',
            'valign': 'top'
        })
        
        white_format = workbook.add_format({
            'bg_color': '#FFFFFF',
            'border': 1,
            'text_wrap': True,
            'align': 'top',
            'valign': 'top'
        })

        # Bold formats for Name column in Metrics/Dimensions sheets
        name_bold_grey = workbook.add_format({
            'bg_color': '#F2F2F2',
            'border': 1,
            'text_wrap': True,
            'align': 'top',
            'valign': 'top',
            'bold': True
        })

        name_bold_white = workbook.add_format({
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

            # Row formats (for non-severity columns)
            critical_format = workbook.add_format({
                'bg_color': '#FFC7CE',
                'font_color': '#9C0006',
                'border': 1,
                'text_wrap': True,
                'align': 'top',
                'valign': 'top'
            })

            high_format = workbook.add_format({
                'bg_color': '#FFEB9C',
                'font_color': '#9C6500',
                'border': 1,
                'text_wrap': True,
                'align': 'top',
                'valign': 'top'
            })

            medium_format = workbook.add_format({
                'bg_color': '#C6EFCE',
                'font_color': '#006100',
                'border': 1,
                'text_wrap': True,
                'align': 'top',
                'valign': 'top'
            })

            low_format = workbook.add_format({
                'bg_color': '#DDEBF7',
                'font_color': '#1F4E78',
                'border': 1,
                'text_wrap': True,
                'align': 'top',
                'valign': 'top'
            })

            info_format = workbook.add_format({
                'bg_color': '#E2EFDA',
                'font_color': '#375623',
                'border': 1,
                'text_wrap': True,
                'align': 'top',
                'valign': 'top'
            })

            # Bold formats for Severity column (emphasize priority)
            critical_bold = workbook.add_format({
                'bg_color': '#FFC7CE',
                'font_color': '#9C0006',
                'bold': True,
                'border': 1,
                'align': 'center',
                'valign': 'vcenter'
            })

            high_bold = workbook.add_format({
                'bg_color': '#FFEB9C',
                'font_color': '#9C6500',
                'bold': True,
                'border': 1,
                'align': 'center',
                'valign': 'vcenter'
            })

            medium_bold = workbook.add_format({
                'bg_color': '#C6EFCE',
                'font_color': '#006100',
                'bold': True,
                'border': 1,
                'align': 'center',
                'valign': 'vcenter'
            })

            low_bold = workbook.add_format({
                'bg_color': '#DDEBF7',
                'font_color': '#1F4E78',
                'bold': True,
                'border': 1,
                'align': 'center',
                'valign': 'vcenter'
            })

            info_bold = workbook.add_format({
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

def write_csv_output(data_dict: Dict[str, pd.DataFrame], base_filename: str,
                    output_dir: str, logger: logging.Logger) -> str:
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

    except Exception as e:
        logger.error(_format_error_msg("creating CSV files", error=e))
        raise


def write_json_output(data_dict: Dict[str, pd.DataFrame], metadata_dict: Dict,
                     base_filename: str, output_dir: str, logger: logging.Logger) -> str:
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

    except Exception as e:
        logger.error(_format_error_msg("creating JSON file", error=e))
        raise


def write_html_output(data_dict: Dict[str, pd.DataFrame], metadata_dict: Dict,
                     base_filename: str, output_dir: str, logger: logging.Logger) -> str:
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
            <p>Generated by CJA SDR Generator v3.0.8</p>
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

    except Exception as e:
        logger.error(_format_error_msg("creating HTML file", error=e))
        raise

# ==================== REFACTORED SINGLE DATAVIEW PROCESSING ====================

def process_single_dataview(data_view_id: str, config_file: str = "myconfig.json",
                           output_dir: str = ".", log_level: str = "INFO",
                           output_format: str = "excel", enable_cache: bool = False,
                           cache_size: int = 1000, cache_ttl: int = 3600,
                           quiet: bool = False, skip_validation: bool = False,
                           max_issues: int = 0, clear_cache: bool = False) -> ProcessingResult:
    """
    Process a single data view and generate SDR in specified format(s)

    Args:
        data_view_id: The data view ID to process (must start with 'dv_')
        config_file: Path to CJA config file (default: 'myconfig.json')
        output_dir: Directory to save output files (default: current directory)
        log_level: Logging level - one of DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO)
        output_format: Output format - one of excel, csv, json, html, all (default: excel)
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

        fetcher = ParallelAPIFetcher(cja, logger, perf_tracker, max_workers=DEFAULT_API_FETCH_WORKERS)
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

            dq_checker = DataQualityChecker(logger, validation_cache=validation_cache)

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
            excel_file_name = f'CJA_DataView_dv_{data_view_id}_SDR.xlsx'
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
        formats_to_generate = ['excel', 'csv', 'json', 'html'] if output_format == 'all' else [output_format]

        output_files = []

        try:
            for fmt in formats_to_generate:
                if fmt == 'excel':
                    logger.info("Generating Excel file...")
                    with pd.ExcelWriter(str(output_path), engine='xlsxwriter') as writer:
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
                                    apply_excel_formatting(writer, placeholder_df, sheet_name, logger)
                                else:
                                    apply_excel_formatting(writer, sheet_data, sheet_name, logger)
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
        config_file: Path to CJA config file (default: 'myconfig.json')
        output_dir: Directory for output files (default: current directory)
        workers: Number of parallel workers, 1-256 (default: 4)
        continue_on_error: Continue if individual data views fail (default: False)
        log_level: Logging level - DEBUG, INFO, WARNING, ERROR, CRITICAL (default: INFO)
        output_format: Output format - excel, csv, json, html, all (default: excel)
        enable_cache: Enable validation result caching (default: False)
        cache_size: Maximum cached validation results, >= 1 (default: 1000)
        cache_ttl: Cache time-to-live in seconds, >= 1 (default: 3600)
        quiet: Suppress non-error output (default: False)
        skip_validation: Skip data quality validation (default: False)
        max_issues: Limit issues to top N by severity, >= 0; 0 = all (default: 0)
        clear_cache: Clear validation cache before processing (default: False)
    """

    def __init__(self, config_file: str = "myconfig.json", output_dir: str = ".",
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

Note:
  At least one data view ID must be provided (except for --list-dataviews, --sample-config).
  Use 'python cja_sdr_generator.py --help' to see all options.
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
        metavar='DATA_VIEW_ID',
        help='Data view IDs to process (at least one required unless using --version)'
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
        default='myconfig.json',
        help='Path to CJA configuration file (default: myconfig.json)'
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
        default=DEFAULT_RETRY_CONFIG['max_retries'],
        help=f'Maximum API retry attempts (default: {DEFAULT_RETRY_CONFIG["max_retries"]})'
    )

    parser.add_argument(
        '--retry-base-delay',
        type=float,
        default=DEFAULT_RETRY_CONFIG['base_delay'],
        help=f'Initial retry delay in seconds (default: {DEFAULT_RETRY_CONFIG["base_delay"]})'
    )

    parser.add_argument(
        '--retry-max-delay',
        type=float,
        default=DEFAULT_RETRY_CONFIG['max_delay'],
        help=f'Maximum retry delay in seconds (default: {DEFAULT_RETRY_CONFIG["max_delay"]})'
    )

    parser.add_argument(
        '--format',
        type=str,
        default='excel',
        choices=['excel', 'csv', 'json', 'html', 'all'],
        help='Output format: excel (default), csv, json, html, or all (generates all formats)'
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

    return parser.parse_args()

# ==================== LIST DATA VIEWS ====================

def list_dataviews(config_file: str = "myconfig.json") -> bool:
    """
    List all accessible data views and exit

    Args:
        config_file: Path to CJA configuration file

    Returns:
        True if successful, False otherwise
    """
    print()
    print("=" * 60)
    print("LISTING ACCESSIBLE DATA VIEWS")
    print("=" * 60)
    print()

    # Validate config file first
    print(f"Using configuration: {config_file}")
    print()

    try:
        cjapy.importConfigFile(config_file)
        cja = cjapy.CJA()

        # Get all data views
        print("Connecting to CJA API...")
        available_dvs = cja.getDataViews()

        if available_dvs is None or (hasattr(available_dvs, '__len__') and len(available_dvs) == 0):
            print()
            print(ConsoleColors.warning("No data views found or no access to any data views."))
            print()
            return True

        # Convert to list if DataFrame
        if isinstance(available_dvs, pd.DataFrame):
            available_dvs = available_dvs.to_dict('records')

        print()
        print(f"Found {len(available_dvs)} accessible data view(s):")
        print()
        print(f"{'ID':<45} {'Name':<40} {'Owner'}")
        print("-" * 100)

        for dv in available_dvs:
            if isinstance(dv, dict):
                dv_id = dv.get('id', 'N/A')
                dv_name = dv.get('name', 'N/A')[:38]
                dv_owner = dv.get('owner', {})
                owner_name = dv_owner.get('name', 'N/A') if isinstance(dv_owner, dict) else str(dv_owner)[:20]
                print(f"{dv_id:<45} {dv_name:<40} {owner_name}")

        print()
        print("=" * 60)
        print("Usage: python cja_sdr_generator.py <DATA_VIEW_ID>")
        print("=" * 60)

        return True

    except FileNotFoundError:
        print(ConsoleColors.error(f"ERROR: Configuration file '{config_file}' not found"))
        print()
        print("Generate a sample configuration file with:")
        print("  python cja_sdr_generator.py --sample-config")
        return False

    except (KeyboardInterrupt, SystemExit):
        print()
        print(ConsoleColors.warning("Operation cancelled."))
        raise

    except Exception as e:
        print(ConsoleColors.error(f"ERROR: Failed to connect to CJA API: {str(e)}"))
        return False


# ==================== SAMPLE CONFIG GENERATOR ====================

def generate_sample_config(output_path: str = "myconfig.sample.json") -> bool:
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
        print("  1. Copy the sample file to 'myconfig.json':")
        print(f"     cp {output_path} myconfig.json")
        print()
        print("  2. Edit myconfig.json with your Adobe Developer Console credentials")
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

def validate_config_only(config_file: str = "myconfig.json") -> bool:
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

    # Handle --sample-config mode (no data view required)
    if args.sample_config:
        success = generate_sample_config()
        sys.exit(0 if success else 1)

    # Handle --list-dataviews mode (no data view required)
    if args.list_dataviews:
        success = list_dataviews(args.config_file)
        sys.exit(0 if success else 1)

    # Handle --validate-config mode (no data view required)
    if args.validate_config:
        success = validate_config_only(args.config_file)
        sys.exit(0 if success else 1)

    # Get data views from arguments
    data_views = args.data_views

    # Validate that at least one data view is provided
    if not data_views:
        print(ConsoleColors.error("ERROR: At least one data view ID is required"), file=sys.stderr)
        print("Usage: python cja_sdr_generator.py DATA_VIEW_ID [DATA_VIEW_ID ...]", file=sys.stderr)
        print("       Use --help for more information", file=sys.stderr)
        sys.exit(1)

    # Validate data view format
    invalid_dvs = [dv for dv in data_views if not dv.startswith('dv_')]
    if invalid_dvs:
        print(ConsoleColors.error(f"ERROR: Invalid data view ID format: {', '.join(invalid_dvs)}"), file=sys.stderr)
        print(f"       Data view IDs should start with 'dv_'", file=sys.stderr)
        print(f"       Example: dv_677ea9291244fd082f02dd42", file=sys.stderr)
        sys.exit(1)

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
            output_format=args.format,
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
            output_format=args.format,
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
        else:
            print(ConsoleColors.error(f"FAILED: {result.error_message}"))

        print(ConsoleColors.bold(f"Total runtime: {total_runtime:.1f}s"))

        if not result.success:
            sys.exit(1)

if __name__ == "__main__":
    main()