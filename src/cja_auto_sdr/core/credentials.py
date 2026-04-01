"""Credential loading and resolution helpers for CJA Auto SDR."""

import json
import logging
import os
import re
from abc import ABC, abstractmethod
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from cja_auto_sdr.core.config_validation import validate_credentials
from cja_auto_sdr.core.constants import (
    BANNER_WIDTH,
    CREDENTIAL_FIELDS,
    ENV_VAR_MAPPING,
)
from cja_auto_sdr.core.exceptions import (
    CredentialSourceError,
    ProfileConfigError,
    ProfileNotFoundError,
)


def normalize_credential_value(value: Any) -> str:
    """Normalize a credential value consistently across all sources.

    Handles stripping whitespace and quotes from values.

    Args:
        value: The value to normalize (can be any type)

    Returns:
        Normalized string value
    """
    if value is None:
        return ""
    s = str(value).strip()
    # Remove surrounding quotes (common in .env files)
    if len(s) >= 2 and ((s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'"))):
        s = s[1:-1]
    return s


_SCOPES_TOKEN_SPLIT_RE = re.compile(r"[\s,]+")


def _normalize_scope_tokens(value: Any) -> list[str]:
    """Return normalized scope tokens from string or iterable inputs."""
    if value is None:
        return []

    if isinstance(value, str):
        normalized = normalize_credential_value(value)
        return [token for token in _SCOPES_TOKEN_SPLIT_RE.split(normalized) if token]

    if isinstance(value, Iterable) and not isinstance(value, (bytes, bytearray, dict)):
        tokens: list[str] = []
        for item in value:
            tokens.extend(_normalize_scope_tokens(item))
        return tokens

    normalized = normalize_credential_value(value)
    return [normalized] if normalized else []


def normalize_scopes_value(value: Any, *, compact: bool = False) -> str:
    """Normalize the scopes field while preserving legacy string formatting by default."""
    if isinstance(value, str) and not compact:
        return normalize_credential_value(value)
    return ",".join(_normalize_scope_tokens(value))


def normalize_credential_field(name: str, value: Any) -> str:
    """Normalize a credential field according to its expected cjapy contract."""
    if name == "scopes":
        return normalize_scopes_value(value)
    return normalize_credential_value(value)


def filter_credentials(credentials: dict[str, Any]) -> dict[str, str]:
    """Filter and normalize credentials to known fields only.

    Args:
        credentials: Raw credentials dictionary

    Returns:
        Filtered dictionary with only known credential fields, normalized values
    """
    normalized: dict[str, str] = {}
    for key, value in credentials.items():
        if key not in CREDENTIAL_FIELDS["all"] or not value:
            continue
        normalized_value = normalize_credential_field(key, value)
        if normalized_value:
            normalized[key] = normalized_value
    return normalized


# ==================== CREDENTIAL LOADERS ====================


class CredentialLoader(ABC):
    """Abstract base class for loading credentials from different sources.

    Provides consistent interface and error handling for all credential sources.
    """

    @property
    @abstractmethod
    def source_name(self) -> str:
        """Return the name of this credential source."""
        ...

    def load(self, logger: logging.Logger) -> dict[str, str] | None:
        """Load credentials, handling errors gracefully.

        Args:
            logger: Logger instance

        Returns:
            Dictionary of credentials if successful, None otherwise
        """
        try:
            creds = self._load_impl(logger)
            if creds:
                return filter_credentials(creds)
            return None
        except (OSError, json.JSONDecodeError) as e:
            logger.debug("Failed to load credentials from %s: %s", self.source_name, e)
            return None

    @abstractmethod
    def _load_impl(self, logger: logging.Logger) -> dict[str, Any] | None:
        """Implementation-specific loading logic.

        Args:
            logger: Logger instance

        Returns:
            Raw credentials dictionary, or None if not available
        """
        ...


class JsonFileCredentialLoader(CredentialLoader):
    """Load credentials from a JSON file."""

    def __init__(self, file_path: Path):
        self.file_path = file_path

    @property
    def source_name(self) -> str:
        return f"json:{self.file_path.name}"

    def _load_impl(self, _logger: logging.Logger) -> dict[str, Any] | None:
        if not self.file_path.exists():
            return None

        with open(self.file_path) as f:
            config = json.load(f)

        if isinstance(config, dict):
            return config
        return None


class DotenvCredentialLoader(CredentialLoader):
    """Load credentials from a .env file."""

    def __init__(self, file_path: Path):
        self.file_path = file_path

    @property
    def source_name(self) -> str:
        return f"dotenv:{self.file_path.name}"

    def _load_impl(self, _logger: logging.Logger) -> dict[str, Any] | None:
        if not self.file_path.exists():
            return None

        credentials = {}
        with open(self.file_path) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip().lower()
                    value = value.strip()
                    # Remove quotes
                    if (
                        value
                        and len(value) >= 2
                        and (
                            (value.startswith('"') and value.endswith('"'))
                            or (value.startswith("'") and value.endswith("'"))
                        )
                    ):
                        value = value[1:-1]
                    if key and value:
                        credentials[key] = value

        return credentials or None


class EnvironmentCredentialLoader(CredentialLoader):
    """Load credentials from environment variables."""

    @property
    def source_name(self) -> str:
        return "environment"

    def _load_impl(self, _logger: logging.Logger) -> dict[str, Any] | None:
        credentials = {}
        for config_key, env_var in ENV_VAR_MAPPING.items():
            value = os.environ.get(env_var)
            if value and value.strip():
                credentials[config_key] = value.strip()

        return credentials or None


# ==================== CREDENTIAL RESOLVER ====================


class CredentialResolver:
    """Resolves credentials using priority-based strategy.

    Priority order:
    1. Profile credentials (if --profile or CJA_PROFILE specified)
    2. Environment variables
    3. Configuration file

    This class consolidates the credential loading logic that was previously
    scattered throughout initialize_cja().
    """

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def resolve(
        self,
        profile: str | None = None,
        config_file: str | Path = "config.json",
    ) -> tuple[dict[str, str], str]:
        """Resolve credentials following priority order.

        Args:
            profile: Profile name to load (optional)
            config_file: Path to config file (fallback)

        Returns:
            Tuple of (credentials, source_name)

        Raises:
            CredentialSourceError: If no valid credentials found
        """
        # 1. Try profile credentials (highest priority)
        if profile:
            creds, source = self._try_profile(profile)
            if creds:
                return creds, source

        # 2. Try environment variables
        creds, source = self._try_environment()
        if creds:
            # Warn if config file also exists
            config_path = Path(config_file)
            if config_path.exists():
                self._warn_multiple_sources(config_path)
            return creds, source

        # 3. Try config file (lowest priority)
        creds, source = self._try_config_file(config_file)
        if creds:
            return creds, source

        # No valid credentials found
        raise CredentialSourceError(
            "No valid credentials found",
            source="all",
            reason="Checked profile, environment variables, and config file",
            details="Set credentials via --profile, environment variables, or config.json",
        )

    def _try_profile(self, profile_name: str) -> tuple[dict[str, str] | None, str]:
        """Try to load credentials from a profile.

        Args:
            profile_name: Name of the profile

        Returns:
            Tuple of (credentials or None, source_name)

        Raises:
            CredentialSourceError: If profile loading fails critically
        """
        # Import here to avoid circular dependency — profile functions are still in generator.py
        from cja_auto_sdr.generator import load_profile_credentials

        self.logger.info("Loading credentials from profile '%s'...", profile_name)
        try:
            creds = load_profile_credentials(profile_name, self.logger)
            if creds:
                is_valid, issues = validate_credentials(
                    creds,
                    self.logger,
                    strict=False,
                    source=f"profile:{profile_name}",
                )
                if is_valid:
                    self.logger.info("Using credentials from profile '%s'", profile_name)
                    return creds, f"profile:{profile_name}"
                self.logger.warning("Profile '%s' credentials have issues: %s", profile_name, issues)
        except ProfileNotFoundError as e:
            raise CredentialSourceError(
                str(e),
                source=f"profile:{profile_name}",
                reason="Profile directory not found",
                details=e.details,
            ) from e
        except ProfileConfigError as e:
            raise CredentialSourceError(
                str(e),
                source=f"profile:{profile_name}",
                reason="Invalid profile configuration",
                details=e.details,
            ) from e

        return None, ""

    def _try_environment(self) -> tuple[dict[str, str] | None, str]:
        """Try to load credentials from environment variables.

        Returns:
            Tuple of (credentials or None, source_name)
        """
        loader = EnvironmentCredentialLoader()
        creds = loader.load(self.logger)

        if creds:
            is_valid, _ = validate_credentials(creds, self.logger, strict=True, source="environment")
            if is_valid:
                self.logger.info("Using credentials from environment variables")
                return creds, "environment"
            self.logger.debug("Environment credentials invalid, trying next source")

        return None, ""

    def _try_config_file(self, config_file: str | Path) -> tuple[dict[str, str] | None, str]:
        """Try to load credentials from config file.

        Args:
            config_file: Path to config file

        Returns:
            Tuple of (credentials or None, source_name)

        Raises:
            CredentialSourceError: If config file has critical errors
        """
        config_path = Path(config_file)

        if not config_path.exists():
            self.logger.debug("Config file not found: %s", config_path)
            return None, ""

        loader = JsonFileCredentialLoader(config_path)
        creds = loader.load(self.logger)

        if creds:
            is_valid, issues = validate_credentials(
                creds,
                self.logger,
                strict=False,
                source=f"config:{config_path.name}",
            )
            if is_valid:
                self.logger.info("Using credentials from %s", config_file)
                return creds, f"config:{config_path.name}"
            # Config file exists but has issues
            raise CredentialSourceError(
                f"Config file '{config_file}' has validation errors",
                source=f"config:{config_path.name}",
                reason="; ".join(issues[:3]),  # Show first 3 issues
                details="Fix the issues or use environment variables instead",
            )

        return None, ""

    def _warn_multiple_sources(self, config_path: Path) -> None:
        """Warn user when multiple credential sources exist."""
        self.logger.warning("=" * BANNER_WIDTH)
        self.logger.warning("NOTICE: Both environment variables AND config file detected")
        self.logger.warning("  Environment variables: ORG_ID, CLIENT_ID, SECRET, etc.")
        self.logger.warning("  Config file: %s", config_path)
        self.logger.warning("  Using: ENVIRONMENT VARIABLES (takes precedence)")
        self.logger.warning("")
        self.logger.warning("To avoid confusion:")
        self.logger.warning("  - Remove config.json if using environment variables")
        self.logger.warning("  - Or unset env vars: unset ORG_ID CLIENT_ID SECRET SCOPES")
        self.logger.warning("=" * BANNER_WIDTH)


def load_credentials_from_env() -> dict[str, str] | None:
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
    credentials: dict[str, str] = {}
    for config_key, env_var in ENV_VAR_MAPPING.items():
        value = os.environ.get(env_var)
        if value and value.strip():
            credentials[config_key] = value.strip()

    # Return None if no CJA environment variables are set
    if not credentials:
        return None

    return filter_credentials(credentials) or None


def validate_env_credentials(credentials: dict[str, str], logger: logging.Logger) -> bool:
    """
    Validate that environment credentials have minimum required fields for OAuth.

    Uses CREDENTIAL_FIELDS (single source of truth) and validate_credentials for
    consistent validation across all credential sources.

    Args:
        credentials: Dictionary of credentials from environment
        logger: Logger instance

    Returns:
        True if credentials have minimum required fields
    """
    # Use CREDENTIAL_FIELDS for required fields (single source of truth)
    for field in CREDENTIAL_FIELDS["required"]:
        if field not in credentials or not credentials[field].strip():
            logger.debug("Missing required environment variable: %s", ENV_VAR_MAPPING.get(field, field))
            return False

    # Use unified validation function
    is_valid, _issues = validate_credentials(credentials, logger, strict=False, source="environment")

    return is_valid
