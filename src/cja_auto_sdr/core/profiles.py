"""Profile management helpers extracted from generator.py."""

# ruff: noqa: T201

from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

from cja_auto_sdr.api.client import _normalize_dataview_listing_payload_or_raise
from cja_auto_sdr.api.quality_policy import _canonical_quality_policy_key
from cja_auto_sdr.core.colors import ConsoleColors
from cja_auto_sdr.core.constants import BANNER_WIDTH, CREDENTIAL_FIELDS, ENV_VAR_MAPPING
from cja_auto_sdr.core.credentials import filter_credentials
from cja_auto_sdr.core.exceptions import (
    ProfileConfigError,
    ProfileNotFoundError,
    api_connection_error_summary,
    api_connection_hint,
)
from cja_auto_sdr.core.json_io import write_json_atomic

__all__ = [
    "_normalize_import_credentials",
    "_parse_env_credentials_content",
    "_read_profile_org_id",
    "add_profile_interactive",
    "get_cja_home",
    "get_profile_path",
    "get_profiles_dir",
    "import_profile_non_interactive",
    "list_profiles",
    "load_profile_config_json",
    "load_profile_credentials",
    "load_profile_dotenv",
    "load_profile_import_source",
    "mask_sensitive_value",
    "resolve_active_profile",
    "show_profile",
    "test_profile",
    "validate_profile_name",
]


def _generator_module():
    from cja_auto_sdr import generator as _generator

    return _generator


def get_cja_home() -> Path:
    """Get CJA home directory (~/.cja or $CJA_HOME)."""
    cja_home = os.environ.get("CJA_HOME")
    if cja_home:
        return Path(cja_home).expanduser()
    return Path.home() / ".cja"


def get_profiles_dir() -> Path:
    """Get profiles directory (~/.cja/orgs/)."""
    return _generator_module().get_cja_home() / "orgs"


def get_profile_path(profile_name: str) -> Path:
    """Get the path to a specific profile directory."""
    return _generator_module().get_profiles_dir() / profile_name


def validate_profile_name(name: str) -> tuple[bool, str | None]:
    """Validate profile name characters and length."""
    if not name:
        return False, "Profile name cannot be empty"

    if not re.fullmatch(r"[a-zA-Z0-9][a-zA-Z0-9_-]*", name):
        return False, (
            f"Profile name '{name}' is invalid. "
            "Must start with alphanumeric and contain only letters, numbers, dashes, and underscores."
        )

    if len(name) > 64:
        return False, f"Profile name '{name}' is too long (max 64 characters)"

    return True, None


def load_profile_config_json(profile_path: Path) -> dict[str, str] | None:
    """Load credentials from profile ``config.json`` when present."""
    config_file = profile_path / "config.json"
    if not os.path.exists(config_file):
        return None

    try:
        with open(config_file, encoding="utf-8") as f:
            config = json.load(f)
        if isinstance(config, dict):
            return filter_credentials(config)
        return None
    except OSError:
        return None
    except json.JSONDecodeError:
        return None


def _parse_dotenv_line(raw_line: str) -> tuple[str, str] | None:
    """Parse one ``.env`` line the way python-dotenv does.

    Returns ``(key, value)`` for an assignment and ``None`` for a blank or comment line.
    Handles a leading ``export``, quoted values (``#`` kept inside quotes), and unquoted
    inline comments (`` #`` onward is dropped). A line without ``=`` yields the whole
    line as the key and an empty value; callers that care must check for ``=`` first.
    """
    line = raw_line.strip()
    if not line or line.startswith("#"):
        return None
    if line.lower().startswith("export ") or line.lower().startswith("export\t"):
        line = line[7:].strip()
    key, _, value = line.partition("=")
    key = key.strip()
    value = value.strip()
    if value[:1] in ('"', "'"):
        quote = value[0]
        end = value.find(quote, 1)
        value = value[1:end] if end != -1 else value[1:]
    else:
        match = re.search(r"\s#", value)
        if match:
            value = value[: match.start()]
        value = value.strip()
    return key, value


def load_profile_dotenv(profile_path: Path) -> dict[str, str] | None:
    """Load credentials from a profile ``.env`` file when present."""
    env_file = profile_path / ".env"
    if not os.path.exists(env_file):
        return None

    credentials = {}
    try:
        with open(env_file, encoding="utf-8") as f:
            for raw_line in f:
                if "=" not in raw_line:
                    continue
                parsed = _parse_dotenv_line(raw_line)
                if parsed is None:
                    continue
                key, value = parsed
                if key and value:
                    config_key = key.lower()
                    if config_key in CREDENTIAL_FIELDS["all"]:
                        credentials[config_key] = value
    except OSError:
        return None
    except UnicodeDecodeError:
        return None

    filtered_credentials = filter_credentials(credentials)
    return filtered_credentials or None


def load_profile_credentials(profile_name: str, logger: logging.Logger) -> dict[str, str] | None:
    """Load and merge credentials from ``config.json`` and ``.env``."""
    generator = _generator_module()

    is_valid, error_msg = generator.validate_profile_name(profile_name)
    if not is_valid:
        raise ProfileConfigError(error_msg, profile_name=profile_name)

    profile_path = generator.get_profile_path(profile_name)

    if not os.path.exists(profile_path):
        raise ProfileNotFoundError(
            f"Profile '{profile_name}' not found",
            profile_name=profile_name,
            details=f"Expected directory: {profile_path}",
        )

    if not os.path.isdir(profile_path):
        raise ProfileConfigError(
            "Profile path is not a directory",
            profile_name=profile_name,
            details=str(profile_path),
        )

    credentials = generator.load_profile_config_json(profile_path) or {}
    json_source = bool(credentials)

    env_credentials = generator.load_profile_dotenv(profile_path)
    if env_credentials:
        credentials.update({key: value for key, value in env_credentials.items() if value})

    if not credentials:
        raise ProfileConfigError(
            f"Profile '{profile_name}' has no configuration",
            profile_name=profile_name,
            details=f"Expected config.json or .env in {profile_path}",
        )

    if json_source and env_credentials:
        logger.debug("Profile '%s': merged config.json with .env overrides", profile_name)
    elif json_source:
        logger.debug("Profile '%s': loaded from config.json", profile_name)
    else:
        logger.debug("Profile '%s': loaded from .env", profile_name)

    return credentials


def resolve_active_profile(cli_profile: str | None = None) -> str | None:
    """Resolve active profile: ``--profile`` > ``CJA_PROFILE`` > ``None``."""
    if cli_profile:
        return cli_profile
    return os.environ.get("CJA_PROFILE")


def _read_profile_org_id(profile_path: Path) -> str | None:
    """Read ``org_id`` from a profile directory using profile precedence rules."""
    generator = _generator_module()
    org_id: str | None = None

    config_file = profile_path / "config.json"
    if os.path.exists(config_file):
        try:
            with open(config_file, encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                value = data.get("org_id")
                if value and isinstance(value, str) and value.strip():
                    org_id = value.strip()
        except OSError:
            pass
        except json.JSONDecodeError:
            pass
        except ValueError:
            pass

    env_credentials = generator.load_profile_dotenv(profile_path)
    if env_credentials:
        env_org_id = env_credentials.get("org_id")
        if isinstance(env_org_id, str):
            normalized_org_id = env_org_id.strip()
            if normalized_org_id:
                org_id = normalized_org_id

    return org_id


def list_profiles(output_format: str = "table") -> bool:
    """List all configured profiles."""
    generator = _generator_module()
    profiles_dir = generator.get_profiles_dir()

    if not os.path.exists(profiles_dir):
        if output_format == "json":
            print(json.dumps({"profiles": [], "count": 0}, indent=2))
        else:
            print()
            print("No profiles directory found.")
            print(f"Expected: {profiles_dir}")
            print()
            print("To create profiles, run:")
            print("  cja_auto_sdr --profile-add <profile-name>")
            print()
        return True

    profiles = []
    active_profile = os.environ.get("CJA_PROFILE")

    for item in sorted(profiles_dir.iterdir()):
        if not os.path.isdir(item):
            continue

        profile_name = item.name
        has_config_json = os.path.exists(item / "config.json")
        has_env = os.path.exists(item / ".env")
        is_active = profile_name == active_profile

        if has_config_json or has_env:
            config_source = []
            if has_config_json:
                config_source.append("config.json")
            if has_env:
                config_source.append(".env")

            try:
                org_id = generator._read_profile_org_id(item)
            except Exception:
                logging.getLogger(__name__).debug(
                    "Failed to read org_id from profile '%s': skipping",
                    profile_name,
                    exc_info=True,
                )
                org_id = None

            profiles.append(
                {
                    "name": profile_name,
                    "active": is_active,
                    "sources": config_source,
                    "path": str(item),
                    "org_id": org_id,
                }
            )

    if output_format == "json":
        print(json.dumps({"profiles": profiles, "count": len(profiles), "active": active_profile}, indent=2))
        return True

    print()
    print("=" * BANNER_WIDTH)
    print("AVAILABLE PROFILES")
    print("=" * BANNER_WIDTH)
    print()

    if not profiles:
        print("No profiles found.")
        print()
        print("To create a profile, run:")
        print("  cja_auto_sdr --profile-add <profile-name>")
        print()
        return True

    max_org_width = 30
    print(f"  {'Profile':<23} {'Org ID':<{max_org_width}}  {'Sources':<20} {'Status'}")
    print("  " + "-" * 60)
    for profile in profiles:
        status = "[active]" if profile["active"] else ""
        sources = ", ".join(profile["sources"])
        marker = "\u25cf" if profile["active"] else " "
        org_display = profile["org_id"] or "\u2014"
        if len(org_display) > max_org_width:
            org_display = org_display[: max_org_width - 1] + "\u2026"
        print(f"{marker} {profile['name']:<23} {org_display:<{max_org_width}}  {sources:<20} {status}")

    print()
    print(f"Total: {len(profiles)} profile(s)")
    print()
    print("Usage:")
    print("  cja_auto_sdr --profile <name> --list-dataviews")
    print("  export CJA_PROFILE=<name>")
    print()
    return True


def add_profile_interactive(profile_name: str) -> bool:
    """Interactively create a new profile."""
    generator = _generator_module()

    is_valid, error_msg = generator.validate_profile_name(profile_name)
    if not is_valid:
        print(ConsoleColors.error(f"Error: {error_msg}"), file=sys.stderr)
        return False

    profile_path = generator.get_profile_path(profile_name)

    if os.path.exists(profile_path):
        print(f"Profile '{profile_name}' already exists at: {profile_path}")
        print()
        response = input("Overwrite? [y/N]: ").strip().lower()
        if response != "y":
            print("Aborted.")
            return False

    try:
        profile_path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(ConsoleColors.error(f"Error creating profile directory: {e}"), file=sys.stderr)
        return False

    print()
    print("=" * BANNER_WIDTH)
    print(f"CREATING PROFILE: {profile_name}")
    print("=" * BANNER_WIDTH)
    print()
    print("Enter your Adobe OAuth credentials.")
    print("(Get these from Adobe Developer Console → Project → Credentials)")
    print()

    try:
        org_id = input("Organization ID (ends with @AdobeOrg): ").strip()
        if not org_id:
            print(ConsoleColors.error("Error: Organization ID is required"), file=sys.stderr)
            return False

        client_id = input("Client ID: ").strip()
        if not client_id:
            print(ConsoleColors.error("Error: Client ID is required"), file=sys.stderr)
            return False

        import getpass

        try:
            secret = getpass.getpass("Client Secret: ").strip()
        except getpass.GetPassWarning:
            print(
                ConsoleColors.error(
                    "Error: Cannot securely read secret (no TTY available). Use --profile-import instead."
                ),
                file=sys.stderr,
            )
            return False

        if not secret:
            print(ConsoleColors.error("Error: Client Secret is required"), file=sys.stderr)
            return False

        scopes = input("OAuth Scopes (from Developer Console): ").strip()
        if not scopes:
            print(ConsoleColors.error("Error: OAuth Scopes are required"), file=sys.stderr)
            return False
    except KeyboardInterrupt:
        print("\nAborted.")
        return False
    except EOFError:
        print("\nAborted.")
        return False

    config = {"org_id": org_id, "client_id": client_id, "secret": secret, "scopes": scopes}

    config_file = profile_path / "config.json"
    try:
        write_json_atomic(config_file, config, indent=2, file_mode=0o600)
    except OSError as e:
        print(ConsoleColors.error(f"Error writing config file: {e}"), file=sys.stderr)
        return False

    print()
    print(f"Profile '{profile_name}' created successfully!")
    print(f"  Location: {profile_path}")
    print()
    print("Test your profile:")
    print(f"  cja_auto_sdr --profile-test {profile_name}")
    print()
    print("Use your profile:")
    print(f"  cja_auto_sdr --profile {profile_name} --list-dataviews")
    print()
    return True


def _normalize_import_credentials(raw_credentials: dict[str, Any]) -> dict[str, str]:
    """Normalize imported credential keys to canonical config field names."""
    env_to_config_key = {env_name.lower(): config_key for config_key, env_name in ENV_VAR_MAPPING.items()}
    alias_map = {
        "organization_id": "org_id",
        "orgid": "org_id",
        "clientid": "client_id",
        "client_secret": "secret",
        "clientsecret": "secret",
    }

    normalized: dict[str, str] = {}
    for raw_key, raw_value in raw_credentials.items():
        if raw_value is None:
            continue
        key = _canonical_quality_policy_key(raw_key)
        key = env_to_config_key.get(key, key)
        key = alias_map.get(key, key)
        if key not in CREDENTIAL_FIELDS["all"]:
            continue
        value = str(raw_value).strip().strip('"').strip("'")
        if value:
            normalized[key] = value

    return normalized


def _parse_env_credentials_content(content: str) -> dict[str, str]:
    """Parse ``.env``-formatted credential content."""
    credentials: dict[str, str] = {}
    for line_number, raw_line in enumerate(content.splitlines(), start=1):
        parsed = _parse_dotenv_line(raw_line)
        if parsed is None:
            continue
        if "=" not in raw_line:
            raise ValueError(f"Invalid .env content at line {line_number}: expected KEY=VALUE")
        key, value = parsed
        if not key:
            raise ValueError(f"Invalid .env content at line {line_number}: empty key")
        credentials.update(_normalize_import_credentials({key: value}))

    return credentials


def load_profile_import_source(source_file: str | Path) -> dict[str, str]:
    """Load credentials from JSON, ``.env``, or a profile directory."""
    source_path = Path(source_file).expanduser()
    if not os.path.exists(source_path):
        raise FileNotFoundError(f"Source not found: {source_path}")

    if os.path.isdir(source_path):
        config_json_path = source_path / "config.json"
        dotenv_path = source_path / ".env"
        merged_credentials: dict[str, str] = {}

        if os.path.exists(config_json_path):
            with open(config_json_path, encoding="utf-8") as f:
                config_payload = json.load(f)
            if not isinstance(config_payload, dict):
                raise ValueError(f"Invalid profile config in {config_json_path}: expected JSON object")
            if isinstance(config_payload.get("credentials"), dict):
                config_payload = config_payload["credentials"]
            merged_credentials.update(_normalize_import_credentials(config_payload))

        if os.path.exists(dotenv_path):
            merged_credentials.update(_parse_env_credentials_content(dotenv_path.read_text(encoding="utf-8")))

        if not merged_credentials:
            raise ValueError(f"No credentials found in directory: {source_path}")
        return merged_credentials

    if source_path.suffix.lower() == ".json":
        with open(source_path, encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict):
            raise ValueError("Profile import JSON must be an object")
        if isinstance(payload.get("credentials"), dict):
            payload = payload["credentials"]
        credentials = _normalize_import_credentials(payload)
    else:
        credentials = _parse_env_credentials_content(source_path.read_text(encoding="utf-8"))

    if not credentials:
        raise ValueError("No supported credential fields were found in import source")
    return credentials


def import_profile_non_interactive(profile_name: str, source_file: str | Path, overwrite: bool = False) -> bool:
    """Import a profile from JSON or ``.env`` without prompts."""
    generator = _generator_module()

    is_valid_name, error_msg = generator.validate_profile_name(profile_name)
    if not is_valid_name:
        print(ConsoleColors.error(f"Error: {error_msg}"), file=sys.stderr)
        return False

    profile_path = generator.get_profile_path(profile_name)
    profile_exists = os.path.exists(profile_path)
    if profile_exists and not overwrite:
        print(f"Profile '{profile_name}' already exists at: {profile_path}")
        print("Use --profile-overwrite with --profile-import to replace it.")
        return False

    try:
        credentials = load_profile_import_source(source_file)
    except OSError as e:
        print(ConsoleColors.error(f"Error loading profile import source '{source_file}': {e}"), file=sys.stderr)
        return False
    except json.JSONDecodeError as e:
        print(ConsoleColors.error(f"Error loading profile import source '{source_file}': {e}"), file=sys.stderr)
        return False
    except ValueError as e:
        print(ConsoleColors.error(f"Error loading profile import source '{source_file}': {e}"), file=sys.stderr)
        return False

    validation_logger = logging.getLogger("profile_import")
    validation_logger.setLevel(logging.WARNING)
    is_usable, issues = generator.validate_credentials(
        credentials,
        validation_logger,
        strict=True,
        source=f"profile import ({source_file})",
    )
    if not is_usable:
        generator._print_error_list_to_stderr("Error: Imported credentials failed validation:", issues)
        return False

    config_payload = {
        key: value for key in ("org_id", "client_id", "secret", "scopes", "sandbox") if (value := credentials.get(key))
    }

    try:
        profile_path.mkdir(parents=True, exist_ok=True)
        config_path = profile_path / "config.json"
        write_json_atomic(config_path, config_payload, indent=2, file_mode=0o600, trailing_newline=True)
    except OSError as e:
        print(ConsoleColors.error(f"Error writing profile config: {e}"), file=sys.stderr)
        return False

    if profile_exists and os.path.exists(profile_path / ".env"):
        print(
            "Warning: Existing .env file was kept and may override imported config.json values when this profile is used.",
        )

    print()
    print(f"Profile '{profile_name}' imported successfully.")
    print(f"  Source: {Path(source_file).expanduser()}")
    print(f"  Location: {profile_path}")
    print()
    print("Next steps:")
    print(f"  cja_auto_sdr --profile-test {profile_name}")
    print(f"  cja_auto_sdr --profile {profile_name} --list-dataviews")
    print()
    return True


def mask_sensitive_value(value: str, show_chars: int = 4) -> str:
    """Mask sensitive values for display."""
    if not value:
        return "(empty)"

    if len(value) <= show_chars * 2:
        return "*" * len(value)

    return f"{value[:show_chars]}{'*' * (len(value) - show_chars * 2)}{value[-show_chars:]}"


def show_profile(profile_name: str) -> bool:
    """Display profile configuration with masked sensitive values."""
    generator = _generator_module()

    try:
        logger = logging.getLogger("profile_show")
        logger.setLevel(logging.WARNING)
        credentials = generator.load_profile_credentials(profile_name, logger)
    except ProfileNotFoundError as e:
        print(ConsoleColors.error(f"Error: {e}"), file=sys.stderr)
        return False
    except ProfileConfigError as e:
        print(ConsoleColors.error(f"Error: {e}"), file=sys.stderr)
        return False

    profile_path = generator.get_profile_path(profile_name)

    print()
    print("=" * BANNER_WIDTH)
    print(f"PROFILE: {profile_name}")
    print("=" * BANNER_WIDTH)
    print()
    print(f"Location: {profile_path}")
    print()

    sources = []
    if os.path.exists(profile_path / "config.json"):
        sources.append("config.json")
    if os.path.exists(profile_path / ".env"):
        sources.append(".env")
    print(f"Sources: {', '.join(sources)}")
    print()

    print("Credentials:")
    print("-" * 40)

    sensitive_fields = {"secret", "client_id"}
    for key in ["org_id", "client_id", "secret", "scopes", "sandbox"]:
        if key in credentials:
            value = credentials[key]
            if key in sensitive_fields:
                display_value = generator.mask_sensitive_value(value)
            else:
                display_value = value
            print(f"  {key}: {display_value}")

    print()
    return True


def test_profile(profile_name: str) -> bool:
    """Test profile credentials and API connectivity."""
    generator = _generator_module()

    print()
    print("=" * BANNER_WIDTH)
    print(f"TESTING PROFILE: {profile_name}")
    print("=" * BANNER_WIDTH)
    print()

    try:
        logger = logging.getLogger("profile_test")
        logger.setLevel(logging.WARNING)
        credentials = generator.load_profile_credentials(profile_name, logger)
    except ProfileNotFoundError as e:
        print(ConsoleColors.error(f"ERROR: {e}"), file=sys.stderr)
        return False
    except ProfileConfigError as e:
        print(ConsoleColors.error(f"ERROR: {e}"), file=sys.stderr)
        return False

    print("1. Profile found and loaded")

    issues = generator.ConfigValidator.validate_all(credentials, logger)
    if issues:
        print("2. Credential validation: WARNINGS")
        for issue in issues:
            print(f"   - {issue}")
    else:
        print("2. Credential validation: OK")

    print("3. Testing API connectivity...")

    def _print_profile_test_failure(exc: Exception) -> bool:
        """Render a controlled profile-test failure with optional remediation hint."""
        print(ConsoleColors.error("   API connection: FAILED"), file=sys.stderr)
        summary = api_connection_error_summary(exc) or str(exc)
        print(ConsoleColors.error(f"   Error: {summary}"), file=sys.stderr)
        print(file=sys.stderr)
        print(ConsoleColors.error("Profile test: FAILED"), file=sys.stderr)
        print(file=sys.stderr)

        hint = api_connection_hint(exc)
        if hint:
            for line in hint.splitlines():
                print(ConsoleColors.warning(f"  {line}"))
            print()
        print("Common issues:")
        print("  - Invalid client_id or secret")
        print("  - Incorrect OAuth scopes")
        print("  - API project not provisioned for CJA")
        print("  - Missing AEP API in Developer Console project")
        print("  - Service account not granted product profile access")
        print()
        return False

    try:
        generator._config_from_env(credentials, logger)
        cja = generator.cjapy.CJA()
        dataviews = cja.getDataViews()
        normalized_dataviews = (
            []
            if dataviews is None
            else _normalize_dataview_listing_payload_or_raise(
                dataviews,
                operation="getDataViews (profile test)",
            )
        )

        if dataviews is not None:
            count = len(normalized_dataviews)
            print("   API connection: SUCCESS")
            print(f"   Data views accessible: {count}")
            print()
            print("Profile test: PASSED")
            print()
            return True

        print("   API connection: OK (no data views found)")
        print()
        print("Profile test: PASSED")
        print()
        return True
    except generator.RECOVERABLE_CONFIG_API_EXCEPTIONS as e:
        return _print_profile_test_failure(e)
    except Exception as e:
        if isinstance(e, SystemError):
            raise
        logger.debug("Unexpected profile-test connectivity error", exc_info=True)
        return _print_profile_test_failure(e)
