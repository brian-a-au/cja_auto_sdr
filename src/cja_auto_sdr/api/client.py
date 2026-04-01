"""CJA client initialization for CJA Auto SDR."""

import logging
import os
import tempfile
import time
from collections.abc import Mapping, Sequence
from pathlib import Path

import cjapy

from cja_auto_sdr.api.resilience import make_api_call_with_retry
from cja_auto_sdr.core.constants import BANNER_WIDTH
from cja_auto_sdr.core.credentials import (
    CredentialResolver,
    normalize_credential_value,
    normalize_scopes_value,
)
from cja_auto_sdr.core.error_policies import (
    RECOVERABLE_CONNECTION_TEST_EXCEPTIONS,
    RECOVERABLE_DOTENV_BOOTSTRAP_EXCEPTIONS,
)
from cja_auto_sdr.core.exceptions import (
    CredentialSourceError,
    ProfileConfigError,
    ProfileNotFoundError,
)

_LEGACY_TEMP_CONFIG_PREFIXES = ("cja_env_config_", "cja_profile_test_")
_LEGACY_TEMP_CONFIG_SUFFIX = ".json"
_LEGACY_TEMP_CONFIG_MAX_AGE_SECONDS = 3600.0
_temp_cleanup_next_check_monotonic = 0.0
CredentialConfigValue = str | Sequence[str] | None


def _bootstrap_dotenv(logger: logging.Logger) -> None:
    """Load .env variables if python-dotenv is available."""
    try:
        from dotenv import load_dotenv
    except ImportError:
        logger.debug("python-dotenv not installed (.env files will not be auto-loaded)")
        return
    except RECOVERABLE_DOTENV_BOOTSTRAP_EXCEPTIONS as e:
        logger.debug("Failed to import python-dotenv for .env auto-loading: %s", e)
        return

    try:
        dotenv_loaded = load_dotenv()
        if dotenv_loaded:
            logger.debug(".env file found and loaded")
        else:
            logger.debug(".env file not found (python-dotenv available but no .env file)")
    except RECOVERABLE_DOTENV_BOOTSTRAP_EXCEPTIONS as e:
        logger.debug("Failed to load .env via python-dotenv: %s", e)


def _cleanup_stale_temp_configs(logger: logging.Logger) -> float:
    """Remove leftover temp credential files from older releases.

    Returns the number of seconds to wait before the next cleanup scan.
    """
    temp_dir = Path(tempfile.gettempdir())
    now = time.time()
    next_scan_in = _LEGACY_TEMP_CONFIG_MAX_AGE_SECONDS
    retry_immediately = False

    try:
        candidates = set()
        for prefix in _LEGACY_TEMP_CONFIG_PREFIXES:
            candidates.update(temp_dir.glob(f"{prefix}*{_LEGACY_TEMP_CONFIG_SUFFIX}"))
    except OSError as e:
        logger.debug("Failed to scan temp directory for stale config files: %s", e)
        return 0.0

    removed = 0
    for candidate in candidates:
        try:
            age_seconds = now - candidate.stat().st_mtime
        except OSError:
            continue
        if age_seconds < _LEGACY_TEMP_CONFIG_MAX_AGE_SECONDS:
            next_scan_in = min(next_scan_in, _LEGACY_TEMP_CONFIG_MAX_AGE_SECONDS - age_seconds)
            continue
        try:
            candidate.unlink()
        except OSError:
            retry_immediately = True
            continue
        removed += 1

    if removed:
        logger.debug("Removed %s stale temp credential file(s) from previous runs", removed)
    if retry_immediately:
        return 0.0
    return max(0.0, next_scan_in)


def _build_cjapy_config_kwargs(credentials: Mapping[str, CredentialConfigValue]) -> dict[str, str | None]:
    """Normalize credential payloads to the string contract expected by ``cjapy.configure``."""
    scopes = normalize_scopes_value(credentials.get("scopes"), compact=True)
    return {
        "org_id": normalize_credential_value(credentials.get("org_id")) or None,
        "client_id": normalize_credential_value(credentials.get("client_id")) or None,
        "secret": normalize_credential_value(credentials.get("secret")) or None,
        "scopes": scopes or None,
    }


def _config_from_env(credentials: dict[str, str], logger: logging.Logger):
    """
    Configure cjapy directly from in-memory OAuth credentials.

    Older releases wrote environment/profile credentials to temporary JSON
    files for ``cjapy.importConfigFile``. ``cjapy`` also supports direct
    programmatic configuration, so use that path instead and opportunistically
    clean up stale temp files left behind by previous versions.

    Args:
        credentials: Dictionary of credentials from environment
        logger: Logger instance
    """
    global _temp_cleanup_next_check_monotonic  # noqa: PLW0603
    now = time.monotonic()
    if now >= _temp_cleanup_next_check_monotonic:
        next_scan_in = _cleanup_stale_temp_configs(logger)
        _temp_cleanup_next_check_monotonic = now + max(0.0, next_scan_in)
    cjapy.configure(**_build_cjapy_config_kwargs(credentials))
    logger.debug("Configured cjapy directly from in-memory credentials")


def configure_cjapy(
    profile: str | None = None,
    config_file: str = "config.json",
    logger: logging.Logger | None = None,
) -> tuple[bool, str, dict[str, str] | None]:
    """
    Configure cjapy with credentials using priority: profile > env > config file.

    This is a lightweight configuration function that sets up cjapy credentials
    without creating a CJA instance. Use this for commands that need credential
    configuration but manage their own CJA lifecycle.

    Uses CredentialResolver internally to resolve credentials following the
    standard priority order.

    Args:
        profile: Optional profile name to use for credentials
        config_file: Path to fallback config file
        logger: Optional logger instance

    Returns:
        Tuple of (success, source_description, credentials_dict)
        - success: True if cjapy was configured successfully
        - source_description: Description of credential source used
        - credentials_dict: The credentials that were used (for display purposes)
    """
    if logger is None:
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.WARNING)

    try:
        # Ensure direct api.client consumers get .env loading parity with generator path.
        _bootstrap_dotenv(logger)

        # Resolve active profile after dotenv bootstrap so CJA_PROFILE values coming
        # from .env are available to all callers, including those passing profile=None.
        active_profile = profile.strip() if isinstance(profile, str) and profile.strip() else None
        if active_profile is None:
            env_profile = os.environ.get("CJA_PROFILE")
            if env_profile and env_profile.strip():
                active_profile = env_profile.strip()

        # Use CredentialResolver for unified credential resolution
        resolver = CredentialResolver(logger)
        credentials, source = resolver.resolve(profile=active_profile, config_file=config_file)

        # Configure cjapy with the resolved credentials
        # Source format from resolver: "profile:name", "environment", "config:filename"
        if source.startswith("profile:") or source == "environment":
            # Profile or environment credentials use the direct in-memory cjapy path.
            _config_from_env(credentials, logger)
        else:
            # Config file can be imported directly
            cjapy.importConfigFile(config_file)

        # Format source for display (convert resolver format to user-friendly format)
        if source.startswith("profile:"):
            display_source = f"Profile: {source.split(':', 1)[1]}"
        elif source == "environment":
            display_source = "Environment variables"
        elif source.startswith("config:"):
            display_source = f"Config file: {Path(config_file).resolve()}"
        else:
            display_source = source

        return True, display_source, credentials

    except CredentialSourceError as e:
        logger.error("Credential error: %s", e)
        return False, str(e), None
    except (ProfileNotFoundError, ProfileConfigError) as e:
        logger.error("Profile error: %s", e)
        return False, f"Profile error: {e}", None


def initialize_cja(
    config_file: str | Path = "config.json",
    logger: logging.Logger | None = None,
    profile: str | None = None,
) -> cjapy.CJA | None:
    """Initialize CJA connection with comprehensive error handling.

    Uses CredentialResolver for unified credential loading with priority:
        1. Profile credentials (if --profile or CJA_PROFILE specified)
        2. Environment variables (ORG_ID, CLIENT_ID, SECRET, etc.)
        3. Configuration file (config.json)

    Args:
        config_file: Path to CJA configuration file
        logger: Logger instance (uses module logger if None)
        profile: Profile name to load credentials from (optional)

    Returns:
        Initialized CJA instance, or None if initialization fails

    Raises:
        ConfigurationError: If credentials are invalid or missing
        APIError: If API connection fails
    """
    # Import here to avoid circular dependency — this helper still lives in generator.py
    from cja_auto_sdr.generator import resolve_active_profile

    logger = logger or logging.getLogger(__name__)
    try:
        logger.info("=" * BANNER_WIDTH)
        logger.info("INITIALIZING CJA CONNECTION")
        logger.info("=" * BANNER_WIDTH)

        # Ensure initialize_cja() path loads .env before credential resolution.
        _bootstrap_dotenv(logger)

        # Resolve active profile (--profile > CJA_PROFILE > None)
        active_profile = resolve_active_profile(profile)

        # Use CredentialResolver for unified credential loading
        resolver = CredentialResolver(logger)
        try:
            credentials, source = resolver.resolve(profile=active_profile, config_file=config_file)
            logger.info("Credentials loaded from: %s", source)
        except CredentialSourceError as e:
            logger.critical("=" * BANNER_WIDTH)
            logger.critical("CREDENTIAL LOADING FAILED")
            logger.critical("=" * BANNER_WIDTH)
            logger.critical(str(e))
            if e.reason:
                logger.critical("Reason: %s", e.reason)
            if e.details:
                logger.critical(e.details)
            logger.critical("")
            logger.critical("Options to provide credentials:")
            logger.critical("  1. Profile:   cja_auto_sdr --profile <name> ...")
            logger.critical("  2. Env vars:  export ORG_ID=... CLIENT_ID=... SECRET=... SCOPES=...")
            logger.critical("  3. Config:    Create config.json with credentials")
            return None

        # Configure cjapy with resolved credentials
        if source.startswith("config:"):
            # Config file - use cjapy's native loading
            logger.info("Loading CJA configuration from %s...", config_file)
            cjapy.importConfigFile(config_file)
        else:
            # Profile or environment credentials go through direct in-memory configuration.
            logger.info("Loading CJA configuration from %s...", source)
            _config_from_env(credentials, logger)

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
                operation_name="getDataViews (connection test)",
            )
            if test_call is not None:
                logger.info(
                    "\u2713 API connection successful! Found %s data view(s)",
                    len(test_call) if hasattr(test_call, "__len__") else "multiple",
                )
            else:
                logger.warning("API connection test returned None - connection may be unstable")
        except RECOVERABLE_CONNECTION_TEST_EXCEPTIONS as test_error:
            logger.warning("Could not verify connection with test call: %s", test_error)
            logger.warning("Proceeding anyway - errors may occur during data fetching")

        logger.info("CJA initialization complete")
        return cja

    except FileNotFoundError:
        logger.critical("=" * BANNER_WIDTH)
        logger.critical("CONFIGURATION FILE ERROR")
        logger.critical("=" * BANNER_WIDTH)
        logger.critical("Config file not found: %s", config_file)
        logger.critical("Current working directory: %s", Path.cwd())
        logger.critical("Please ensure the configuration file exists in the correct location")
        return None

    except ImportError as e:
        logger.critical("=" * BANNER_WIDTH)
        logger.critical("DEPENDENCY ERROR")
        logger.critical("=" * BANNER_WIDTH)
        logger.critical("Failed to import cjapy module: %s", e)
        logger.critical("Please ensure cjapy is installed: pip install cjapy")
        return None

    except AttributeError as e:
        logger.critical("=" * BANNER_WIDTH)
        logger.critical("CJA CONFIGURATION ERROR")
        logger.critical("=" * BANNER_WIDTH)
        logger.critical("Configuration error: %s", e)
        logger.critical("This usually indicates an issue with the authentication credentials")
        logger.critical("Please verify all fields in your configuration file are correct")
        return None

    except PermissionError as e:
        logger.critical("=" * BANNER_WIDTH)
        logger.critical("PERMISSION ERROR")
        logger.critical("=" * BANNER_WIDTH)
        logger.critical("Cannot read configuration file: %s", e)
        logger.critical("Please check file permissions")
        return None

    except Exception as e:  # Intentional: Top-level init boundary; credentials, config, and API subsystems can all fail with heterogeneous errors
        logger.critical("=" * BANNER_WIDTH)
        logger.critical("CJA INITIALIZATION FAILED")
        logger.critical("=" * BANNER_WIDTH)
        logger.critical("Unexpected error: %s", e)
        logger.critical("Error type: %s", type(e).__name__)
        logger.exception("Full error details:")
        logger.critical("")
        logger.critical("Troubleshooting steps:")
        logger.critical("1. Verify your configuration file exists and is valid JSON")
        logger.critical("2. Check that all authentication credentials are correct")
        logger.critical("3. Ensure your API credentials have the necessary permissions")
        logger.critical("4. Verify you have network connectivity to Adobe services")
        logger.critical("5. Check if cjapy library is up to date: pip install --upgrade cjapy")
        return None
