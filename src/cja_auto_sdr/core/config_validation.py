"""Configuration validation helpers for CJA Auto SDR."""

import json
import logging
from pathlib import Path

from cja_auto_sdr.api.resilience import ErrorMessageHelper
from cja_auto_sdr.core.constants import (
    CONFIG_SCHEMA,
    CREDENTIAL_FIELDS,
    JWT_DEPRECATED_FIELDS,
)


class ConfigValidator:
    """Provides detailed validation and suggestions for configuration fields."""

    @staticmethod
    def validate_org_id(org_id: str) -> tuple[bool, str | None]:
        """
        Validate that ORG_ID has the correct format.

        Args:
            org_id: The organization ID to validate

        Returns:
            Tuple of (is_valid, error_message). error_message is None if valid.
        """
        if not org_id or not org_id.strip():
            return False, "ORG_ID cannot be empty"

        org_id = org_id.strip()

        # Check for @AdobeOrg suffix
        if not org_id.endswith("@AdobeOrg"):
            # Try to be helpful by detecting common mistakes
            if "@" in org_id:
                return False, (
                    f"ORG_ID '{org_id}' has incorrect suffix. "
                    f"It must end with '@AdobeOrg', not '{org_id.split('@')[1]}'"
                )
            return False, (f"ORG_ID '{org_id}' is missing '@AdobeOrg' suffix. Correct format: '{org_id}@AdobeOrg'")

        # Check that there's something before the @AdobeOrg
        org_prefix = org_id[:-9]  # Remove '@AdobeOrg'
        if not org_prefix:
            return False, "ORG_ID cannot be just '@AdobeOrg' - needs organization prefix"

        return True, None

    @staticmethod
    def validate_scopes(scopes: str) -> tuple[bool, str | None, list[str]]:
        """
        Validate OAuth scopes are provided.

        Scopes vary based on Adobe Developer Console project configuration.
        See: https://developer.adobe.com/developer-console/docs/guides/authentication/

        Args:
            scopes: Comma or space-separated scopes string

        Returns:
            Tuple of (is_valid, error_message, missing_scopes).
            error_message is None if valid. missing_scopes is always empty (no longer validated).
        """
        if not scopes or not scopes.strip():
            return False, "SCOPES cannot be empty - copy from Adobe Developer Console", []

        return True, None, []

    @staticmethod
    def validate_client_id(client_id: str) -> tuple[bool, str | None]:
        """
        Validate client ID format.

        Args:
            client_id: The client ID to validate

        Returns:
            Tuple of (is_valid, error_message). error_message is None if valid.
        """
        if not client_id or not client_id.strip():
            return False, "CLIENT_ID cannot be empty"

        client_id = client_id.strip()

        # Adobe client IDs are typically 32 hex characters
        if len(client_id) < 16:
            return False, (
                f"CLIENT_ID '{client_id[:8]}...' appears too short. Adobe OAuth client IDs are typically 32 characters."
            )

        return True, None

    @staticmethod
    def validate_secret(secret: str) -> tuple[bool, str | None]:
        """
        Validate client secret format.

        Args:
            secret: The client secret to validate

        Returns:
            Tuple of (is_valid, error_message). error_message is None if valid.
        """
        if not secret or not secret.strip():
            return False, "SECRET cannot be empty"

        secret = secret.strip()

        # Adobe secrets are typically longer
        if len(secret) < 16:
            return False, "SECRET appears too short. Adobe OAuth secrets are typically longer."

        return True, None

    @classmethod
    def validate_all(cls, credentials: dict[str, str], logger: logging.Logger) -> list[str]:
        """
        Run all validations and return list of issues.

        Args:
            credentials: Dictionary of credentials
            logger: Logger instance

        Returns:
            List of validation issues (empty if all valid)
        """
        issues = []

        # Validate ORG_ID
        if "org_id" in credentials:
            valid, error = cls.validate_org_id(credentials["org_id"])
            if not valid:
                issues.append(error)
                logger.warning("Configuration issue: %s", error)

        # Validate CLIENT_ID
        if "client_id" in credentials:
            valid, error = cls.validate_client_id(credentials["client_id"])
            if not valid:
                issues.append(error)
                logger.warning("Configuration issue: %s", error)

        # Validate SECRET
        if "secret" in credentials:
            valid, error = cls.validate_secret(credentials["secret"])
            if not valid:
                issues.append(error)
                logger.warning("Configuration issue: %s", error)

        # Validate SCOPES (warning only - not strictly required)
        if "scopes" in credentials:
            valid, error, _missing = cls.validate_scopes(credentials["scopes"])
            if not valid:
                logger.warning("Configuration warning: %s", error)
                # Don't add to issues - scopes are a warning, not an error

        return issues


def validate_credentials(
    credentials: dict[str, str],
    logger: logging.Logger,
    strict: bool = False,
    source: str = "unknown",
) -> tuple[bool, list[str]]:
    """Unified validation for credentials from any source.

    Provides consistent validation across profiles, environment variables,
    and config files using CONFIG_SCHEMA and ConfigValidator.

    Args:
        credentials: Dictionary of credentials to validate
        logger: Logger instance
        strict: If True, fail on any issue. If False, return issues list but may pass.
        source: Name of credential source for logging (e.g., "profile", "env", "config_file")

    Returns:
        Tuple of (is_valid, issues). is_valid is True if credentials are usable.
    """
    issues = []

    # Check required fields are present and non-empty
    for field in CREDENTIAL_FIELDS["required"]:
        if field not in credentials:
            issues.append(f"Missing required field: '{field}'")
        elif not credentials[field] or not str(credentials[field]).strip():
            issues.append(f"Empty value for required field: '{field}'")

    # Run detailed validation with ConfigValidator
    validation_issues = ConfigValidator.validate_all(credentials, logger)
    issues.extend(validation_issues)

    # Check for scopes (warning, not error)
    if "scopes" not in credentials or not credentials.get("scopes", "").strip():
        logger.warning(
            "Credentials from %s missing OAuth scopes - "
            "recommend setting scopes (copy from Adobe Developer Console)",
            source,
        )

    # Filter credentials to known fields only
    unknown_fields = set(credentials.keys()) - CREDENTIAL_FIELDS["all"]
    if unknown_fields:
        logger.debug("Ignoring unknown fields from %s: %s", source, ", ".join(unknown_fields))

    is_valid = (
        len(issues) == 0
        if strict
        else all("Missing required field" not in issue and "Empty value" not in issue for issue in issues)
    )

    if issues:
        for issue in issues:
            logger.warning("Credential validation (%s): %s", source, issue)

    return is_valid, issues


def validate_config_file(config_file: str | Path, logger: logging.Logger) -> bool:
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
        logger.info("Validating configuration file: %s", config_file)

        config_path = Path(config_file)

        # Check if file exists
        if not config_path.exists():
            error_msg = ErrorMessageHelper.get_config_error_message(
                "file_not_found",
                details=f"Looking for: {config_path.absolute()}",
            )
            logger.error("\n" + error_msg)
            return False

        # Check if file is readable
        if not config_path.is_file():
            logger.error("'%s' is not a valid file", config_file)
            return False

        # Validate JSON structure
        try:
            with open(config_path) as f:
                config_data = json.load(f)
        except json.JSONDecodeError as e:
            error_msg = ErrorMessageHelper.get_config_error_message(
                "invalid_json",
                details=f"Line {e.lineno}, Column {e.colno}: {e.msg}",
            )
            logger.error("\n" + error_msg)
            return False

        # Validate it's a dictionary
        if not isinstance(config_data, dict):
            logger.error("Configuration file must contain a JSON object (dictionary)")
            return False

        # Check for base required fields (required for all auth methods)
        for field_name, field_info in CONFIG_SCHEMA["base_required_fields"].items():
            if field_name not in config_data:
                validation_errors.append(f"Missing required field: '{field_name}' ({field_info['description']})")
            elif not isinstance(config_data[field_name], field_info["type"]):
                validation_errors.append(
                    f"Invalid type for '{field_name}': expected {field_info['type'].__name__}, "
                    f"got {type(config_data[field_name]).__name__}",
                )
            elif not config_data[field_name] or (
                isinstance(config_data[field_name], str) and not config_data[field_name].strip()
            ):
                validation_errors.append(f"Empty value for required field: '{field_name}'")

        # OAuth Server-to-Server auth - warn if scopes not provided
        if "scopes" not in config_data or not config_data.get("scopes", "").strip():
            validation_warnings.append(
                "OAuth Server-to-Server auth: 'scopes' field not set. "
                "Copy scopes from your Adobe Developer Console project.",
            )

        # Validate optional fields if present
        for field_name, field_info in CONFIG_SCHEMA["optional_fields"].items():
            if field_name in config_data and not isinstance(config_data[field_name], field_info["type"]):
                validation_warnings.append(
                    f"Invalid type for optional field '{field_name}': expected {field_info['type'].__name__}",
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
                f"See docs/QUICKSTART_GUIDE.md for setup instructions.",
            )

        # Check for unknown fields (potential typos)
        known_fields = (
            set(CONFIG_SCHEMA["base_required_fields"].keys())
            | set(CONFIG_SCHEMA["optional_fields"].keys())
            | set(JWT_DEPRECATED_FIELDS.keys())
        )  # Include deprecated fields as "known"
        unknown_fields = set(config_data.keys()) - known_fields
        if unknown_fields:
            validation_warnings.append(f"Unknown fields in config (possible typos): {', '.join(unknown_fields)}")

        # Report validation results
        if validation_errors:
            logger.error("Configuration validation FAILED:")
            for error in validation_errors:
                logger.error("  - %s", error)
            logger.error("")

            # Provide enhanced error message if missing credentials
            if any("Missing required field" in err for err in validation_errors):
                error_msg = ErrorMessageHelper.get_config_error_message(
                    "missing_credentials",
                    details="One or more required fields are missing from your config file",
                )
                logger.error(error_msg)
            elif any("Empty value" in err for err in validation_errors):
                error_msg = ErrorMessageHelper.get_config_error_message(
                    "invalid_format",
                    details="One or more fields have empty or invalid values",
                )
                logger.error(error_msg)
            return False

        if validation_warnings:
            logger.warning("Configuration validation warnings:")
            for warning in validation_warnings:
                logger.warning("  - %s", warning)

        logger.info("Configuration file validated successfully")
        return True

    except PermissionError as e:
        logger.error("Permission denied reading config file: %s", e)
        logger.error("Check file permissions for the configuration file")
        return False
    except (OSError, AttributeError, TypeError, ValueError) as e:
        logger.error("Unexpected error validating config file (%s): %s", type(e).__name__, e)
        return False
