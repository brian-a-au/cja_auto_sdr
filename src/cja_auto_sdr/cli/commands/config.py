"""Configuration-related CLI helpers extracted from generator.py."""

# ruff: noqa: T201

from __future__ import annotations

import importlib.metadata
import json
import logging
import os
from pathlib import Path
from typing import Any

__all__ = [
    "_check_output_dir_access",
    "_read_config_status_file",
    "_resolve_output_dir_path",
    "generate_sample_config",
    "show_config_status",
    "validate_config_only",
]


def _generator_module():
    from cja_auto_sdr import generator as _generator

    return _generator


def generate_sample_config(output_path: str = "config.sample.json") -> bool:
    """Generate a sample configuration file."""
    generator = _generator_module()
    sample_config = {
        "org_id": "YOUR_ORG_ID@AdobeOrg",
        "client_id": "your_client_id_here",
        "secret": "your_client_secret_here",
        "scopes": "your_scopes_from_developer_console",
    }

    print()
    print("=" * generator.BANNER_WIDTH)
    print("GENERATING SAMPLE CONFIGURATION FILE")
    print("=" * generator.BANNER_WIDTH)
    print()

    try:
        with open(output_path, "w", encoding="utf-8") as f:
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
        print("     cja_auto_sdr --list-dataviews")
        print()
        print("=" * generator.BANNER_WIDTH)
        return True
    except (PermissionError, OSError) as e:
        print(generator.ConsoleColors.error(f"ERROR: Failed to create sample config: {e!s}"))
        return False


def _read_config_status_file(config_file: str, logger: logging.Logger) -> tuple[dict[str, Any] | None, str | None]:
    """Read config JSON for --config-status and return a controlled error message on failure."""
    generator = _generator_module()
    try:
        with open(config_file, encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError:
        return None, f"{config_file} is not valid JSON"
    except (UnicodeDecodeError, generator.ConfigurationError, OSError) as e:
        return None, f"Cannot read {config_file}: {e}"
    except (TypeError, ValueError) as e:
        logger.debug("Unexpected error reading config file in --config-status", exc_info=True)
        return None, f"Cannot read {config_file}: {e}"

    if not isinstance(payload, dict):
        return None, f"{config_file} must contain a JSON object"

    return payload, None


def show_config_status(config_file: str = "config.json", profile: str | None = None, output_json: bool = False) -> bool:
    """Show configuration status without connecting to API."""
    generator = _generator_module()

    if not output_json:
        print()
        print("=" * generator.BANNER_WIDTH)
        print("CONFIGURATION STATUS")
        print("=" * generator.BANNER_WIDTH)
        print()

    config_source = None
    config_source_type = None
    config_data: dict[str, Any] = {}
    logger = logging.getLogger(__name__)

    def _emit_config_status_error(message: str, *, include_help: bool = False) -> bool:
        if output_json:
            print(json.dumps({"error": message, "valid": False}, indent=2))
        else:
            print(generator.ConsoleColors.error(f"ERROR: {message}"))
            if include_help:
                print()
                print("Options:")
                print(f"  1. Create config file: {config_file}")
                print("  2. Set environment variables: ORG_ID, CLIENT_ID, SECRET, SCOPES")
                print("  3. Create a profile: cja_auto_sdr --profile-add <name>")
                print()
                print("Generate a sample config with:")
                print("  cja_auto_sdr --sample-config")
        return False

    if profile:
        try:
            profile_creds = generator.load_profile_credentials(profile, logger)
            if profile_creds:
                config_source = f"Profile: {profile}"
                config_source_type = "profile"
                config_data = profile_creds
        except (generator.ProfileNotFoundError, generator.ProfileConfigError) as e:
            return _emit_config_status_error(f"Profile '{profile}' - {e}")

    if not config_source:
        env_credentials = generator.load_credentials_from_env()
        if env_credentials and generator.validate_env_credentials(env_credentials, logger):
            config_source = "Environment variables"
            config_source_type = "environment"
            config_data = env_credentials

    if not config_source:
        config_path = Path(config_file)
        if config_path.exists():
            config_payload, read_error = _read_config_status_file(config_file, logger)
            if read_error:
                return _emit_config_status_error(read_error)
            config_data = config_payload or {}
            config_source = f"Config file: {config_path.resolve()}"
            config_source_type = "file"
        else:
            return _emit_config_status_error("No configuration found", include_help=True)

    fields = [
        ("org_id", "ORG_ID", True, False),
        ("client_id", "CLIENT_ID", True, True),
        ("secret", "SECRET", True, True),
        ("scopes", "SCOPES", False, False),
        ("sandbox", "SANDBOX", False, False),
    ]

    all_required_set = True
    credentials_info = {}
    for key, _display_name, required, sensitive in fields:
        value = config_data.get(key, "")
        if value:
            if sensitive:
                if isinstance(value, str) and len(value) > 8:
                    masked = value[:4] + "*" * (len(value) - 8) + value[-4:]
                else:
                    masked = "****"
                display_value = masked
            else:
                display_value = value
            credentials_info[key] = {"value": display_value, "set": True, "required": required}
        else:
            credentials_info[key] = {"value": None, "set": False, "required": required}
            if required:
                all_required_set = False

    if output_json:
        result = {
            "source": config_source,
            "source_type": config_source_type,
            "profile": profile,
            "config_file": str(Path(config_file).resolve()) if config_source_type == "file" else None,
            "credentials": credentials_info,
            "valid": all_required_set,
        }
        print(json.dumps(result, indent=2))
    else:
        print(f"Source: {config_source}")
        print()
        print("Credentials:")
        for key, display_name, required, _sensitive in fields:
            info = credentials_info[key]
            if info["set"]:
                status = generator.ConsoleColors.success("✓")
                print(f"  {status} {display_name}: {info['value']}")
            elif required:
                status = generator.ConsoleColors.error("✗")
                print(f"  {status} {display_name}: not set (required)")
            else:
                print(f"  - {display_name}: not set (optional)")

        print()
        if all_required_set:
            print(generator.ConsoleColors.success("Configuration is complete."))
            print()
            print("To verify API connectivity, run:")
            print("  cja_auto_sdr --validate-config")
        else:
            print(generator.ConsoleColors.error("Configuration is incomplete."))
            print()
            print("See documentation:")
            print("  https://github.com/brian-a-au/cja_auto_sdr/blob/main/docs/CONFIGURATION.md")
        print()

    return all_required_set


def _resolve_output_dir_path(output_dir: str | Path) -> Path:
    """Resolve output directory for permission checks without requiring it to exist."""
    output_path = Path(output_dir).expanduser()
    try:
        return output_path.resolve(strict=False)
    except OSError, RuntimeError, ValueError:
        return Path(os.path.abspath(str(output_path)))


def _check_output_dir_access(output_dir: str | Path) -> tuple[bool, Path, str, Path | None]:
    """Check whether an output directory is writable now or creatable later."""
    resolved_dir = _resolve_output_dir_path(output_dir)

    if resolved_dir.exists():
        if not resolved_dir.is_dir():
            return False, resolved_dir, "not_directory", None
        if os.access(resolved_dir, os.W_OK | os.X_OK):
            return True, resolved_dir, "writable", None
        return False, resolved_dir, "not_writable", None

    for candidate in resolved_dir.parents:
        if not candidate.exists():
            continue
        if not candidate.is_dir():
            return False, resolved_dir, "parent_not_directory", candidate
        if os.access(candidate, os.W_OK | os.X_OK):
            return True, resolved_dir, "creatable", candidate
        return False, resolved_dir, "parent_not_writable", candidate

    return False, resolved_dir, "no_existing_parent", None


def validate_config_only(
    config_file: str = "config.json",
    profile: str | None = None,
    output_dir: str = ".",
) -> bool:
    """Validate configuration and API connectivity without processing data views."""
    generator = _generator_module()

    print()
    print("=" * generator.BANNER_WIDTH)
    print("CONFIGURATION VALIDATION")
    print("=" * generator.BANNER_WIDTH)
    print()

    all_passed = True
    active_credentials = None
    credential_source = None
    logger = logging.getLogger(__name__)

    def display_credentials(creds: dict[str, str], source_name: str) -> bool:
        required_fields = ["org_id", "client_id", "secret"]
        optional_fields = ["scopes", "sandbox"]
        missing = []

        print()
        print("  Credential status:")
        for field_name in required_fields:
            if creds.get(field_name):
                value = creds[field_name]
                if field_name in ["secret", "client_id"]:
                    masked = value[:4] + "****" + value[-4:] if len(value) > 8 else "****"
                else:
                    masked = value
                print(generator.ConsoleColors.success(f"    \u2713 {field_name}: {masked}"))
            else:
                print(generator.ConsoleColors.error(f"    \u2717 {field_name}: not set (required)"))
                missing.append(field_name)

        for field_name in optional_fields:
            if creds.get(field_name):
                print(generator.ConsoleColors.success(f"    \u2713 {field_name}: {creds[field_name]}"))
            else:
                print(generator.ConsoleColors.info(f"    - {field_name}: not set (optional)"))

        print()
        if missing:
            print(generator.ConsoleColors.error(f"  \u2717 Missing required fields: {', '.join(missing)}"))
            return False
        print(generator.ConsoleColors.success("  \u2713 All required fields present"))
        print(generator.ConsoleColors.info(f"  \u2192 Using: {source_name}"))
        return True

    print("[1/5] Checking environment...")
    vi = generator.sys.version_info
    python_version = f"{vi.major}.{vi.minor}.{vi.micro}"
    if vi >= (3, 14):
        print(generator.ConsoleColors.success(f"  \u2713 Python {python_version} (minimum: 3.14)"))
    else:
        print(generator.ConsoleColors.error(f"  \u2717 Python {python_version} (minimum: 3.14)"))
        all_passed = False
    platform_system = generator.platform.system()
    platform_release = generator.platform.release()
    platform_label = generator.sys.platform
    if platform_system == "Darwin":
        mac_ver = generator.platform.mac_ver()[0]
        platform_label += f" (macOS {mac_ver})" if mac_ver else f" ({platform_system} {platform_release})"
    elif platform_system:
        platform_label += f" ({platform_system} {platform_release})"
    print(generator.ConsoleColors.success(f"  \u2713 Platform: {platform_label}"))

    print()
    print("[2/5] Checking dependencies...")
    for pkg in generator._CORE_DEPENDENCIES:
        try:
            ver = importlib.metadata.version(pkg)
            print(generator.ConsoleColors.success(f"  \u2713 {pkg} {ver}"))
        except importlib.metadata.PackageNotFoundError:
            print(generator.ConsoleColors.error(f"  \u2717 {pkg} (not installed)"))
            all_passed = False
        except (OSError, ValueError) as exc:
            print(generator.ConsoleColors.error(f"  \u2717 {pkg} (metadata error: {exc})"))
            all_passed = False

    for pkg, purpose in (
        ("scipy", "for --org-report clustering"),
        ("argcomplete", "for shell tab-completion"),
        ("python-dotenv", "for .env file loading"),
    ):
        try:
            ver = importlib.metadata.version(pkg)
            print(f"  - {pkg} {ver} (optional, {purpose})")
        except importlib.metadata.PackageNotFoundError:
            print(f"  - {pkg} not installed (optional, {purpose})")
        except (OSError, ValueError) as exc:
            print(f"  - {pkg} metadata error: {exc} (optional, {purpose})")

    if not all_passed:
        print()
        print("=" * generator.BANNER_WIDTH)
        print(generator.ConsoleColors.error("VALIDATION FAILED - Fix issues above"))
        print("=" * generator.BANNER_WIDTH)
        return False

    print()
    print("[3/5] Checking credentials...")

    if profile:
        print(f"  Checking profile '{profile}'...")
        try:
            profile_creds = generator.load_profile_credentials(profile, logger)
            if profile_creds:
                print(generator.ConsoleColors.success(f"  \u2713 Profile '{profile}' found"))
                if display_credentials(profile_creds, f"Profile: {profile}"):
                    active_credentials = profile_creds
                    credential_source = "profile"
                else:
                    all_passed = False
        except generator.ProfileNotFoundError:
            print(generator.ConsoleColors.error(f"  \u2717 Profile '{profile}' not found"))
            print()
            print("  Create the profile with:")
            print(f"    cja_auto_sdr --profile-add {profile}")
            all_passed = False
        except generator.ProfileConfigError as e:
            print(generator.ConsoleColors.error(f"  \u2717 Profile '{profile}' has invalid configuration: {e}"))
            all_passed = False

    if not active_credentials and all_passed:
        env_credentials = generator.load_credentials_from_env()
        if env_credentials:
            print(generator.ConsoleColors.success("  \u2713 Environment variables detected"))
            if generator.validate_env_credentials(env_credentials, logger):
                if display_credentials(env_credentials, "Environment variables"):
                    active_credentials = env_credentials
                    credential_source = "env"
            else:
                print(
                    generator.ConsoleColors.warning(
                        "  \u26a0 Environment credentials incomplete, checking config file..."
                    )
                )
        elif not profile:
            print("  - No environment variables set")

    if not active_credentials and all_passed:
        print()
        print("[3/5] Checking configuration file...")
        config_path = Path(config_file)
        if config_path.exists():
            abs_path = config_path.resolve()
            print(generator.ConsoleColors.success(f"  \u2713 Config file found: {abs_path}"))
            try:
                with open(config_file, encoding="utf-8") as f:
                    config = json.load(f)
                print(generator.ConsoleColors.success("  \u2713 Config file is valid JSON"))
                if display_credentials(config, f"Config file ({config_file})"):
                    active_credentials = config
                    credential_source = "file"
                else:
                    all_passed = False
            except json.JSONDecodeError as e:
                print(generator.ConsoleColors.error(f"  \u2717 Invalid JSON: {e!s}"))
                all_passed = False
        else:
            print(generator.ConsoleColors.error(f"  \u2717 Config file not found: {config_file}"))
            print()
            print("  To create a sample config file:")
            print("    cja_auto_sdr --sample-config")
            print()
            print("  Or set environment variables:")
            print("    export ORG_ID=your_org_id@AdobeOrg")
            print("    export CLIENT_ID=your_client_id")
            print("    export SECRET=your_client_secret")
            print()
            print("  Or create a profile:")
            print("    cja_auto_sdr --profile-add <name>")
            all_passed = False
    elif active_credentials and credential_source in ("profile", "env"):
        print()
        print(f"[3/5] Skipping config file check (using {credential_source} credentials)")

    if not all_passed:
        print()
        print("=" * generator.BANNER_WIDTH)
        print(generator.ConsoleColors.error("VALIDATION FAILED - Fix issues above"))
        print("=" * generator.BANNER_WIDTH)
        return False

    print()
    print("[4/5] Testing API connection...")
    try:
        if credential_source in ("profile", "env"):
            generator._config_from_env(active_credentials, logger)
        else:
            generator.cjapy.importConfigFile(config_file)

        cja = generator.cjapy.CJA()
        print(generator.ConsoleColors.success("  \u2713 CJA client initialized"))

        available_dvs = cja.getDataViews()
        if available_dvs is not None:
            dv_count = len(available_dvs) if hasattr(available_dvs, "__len__") else 0
            print(generator.ConsoleColors.success("  \u2713 API connection successful"))
            print(generator.ConsoleColors.success(f"  \u2713 Found {dv_count} accessible data view(s)"))
        else:
            print(generator.ConsoleColors.warning("  \u26a0 API returned empty response - connection may be unstable"))
    except KeyboardInterrupt, SystemExit:
        print()
        print(generator.ConsoleColors.warning("Validation cancelled."))
        raise
    except generator.RECOVERABLE_CONFIG_API_EXCEPTIONS as e:
        print(generator.ConsoleColors.error(f"  \u2717 API connection failed: {e!s}"))
        all_passed = False
    except (AttributeError, RuntimeError) as e:
        print(generator.ConsoleColors.error(f"  \u2717 API connection failed (unexpected): {e!s}"))
        logging.getLogger(__name__).debug("Unexpected validate-config error", exc_info=True)
        all_passed = False

    if all_passed:
        print()
        print("[5/5] Checking output permissions...")
        output_access_ok, resolved_dir, access_reason, parent_dir = _check_output_dir_access(output_dir)
        if output_access_ok and access_reason == "creatable" and parent_dir is not None:
            print(
                generator.ConsoleColors.success(
                    f"  \u2713 Output directory creatable: {resolved_dir} (parent writable: {parent_dir})"
                )
            )
        elif output_access_ok:
            print(generator.ConsoleColors.success(f"  \u2713 Output directory writable: {resolved_dir}"))
        else:
            if access_reason == "not_directory":
                print(generator.ConsoleColors.error(f"  \u2717 Output path is not a directory: {resolved_dir}"))
            elif access_reason == "parent_not_directory" and parent_dir is not None:
                print(
                    generator.ConsoleColors.error(
                        "  \u2717 Cannot create output directory: "
                        f"{resolved_dir} (path component is not a directory: {parent_dir})"
                    )
                )
            elif access_reason == "parent_not_writable" and parent_dir is not None:
                print(
                    generator.ConsoleColors.error(
                        f"  \u2717 Cannot create output directory: {resolved_dir} (parent not writable: {parent_dir})"
                    )
                )
            elif access_reason == "no_existing_parent":
                print(
                    generator.ConsoleColors.error(
                        f"  \u2717 Cannot determine writable parent for output directory: {resolved_dir}"
                    )
                )
            else:
                print(generator.ConsoleColors.error(f"  \u2717 Output directory not writable: {resolved_dir}"))
            all_passed = False

    print()
    print("=" * generator.BANNER_WIDTH)
    if all_passed:
        print(generator.ConsoleColors.success("VALIDATION PASSED - Configuration is valid!"))
        print()
        print("Next steps — run with a data view to generate SDR reports:")
        print("  cja_auto_sdr <DATA_VIEW_ID>")
        print()
        print("Or list available data views:")
        print("  cja_auto_sdr --list-dataviews")
        print("=" * generator.BANNER_WIDTH)
    else:
        print(generator.ConsoleColors.error("VALIDATION FAILED - Check errors above"))
        print("=" * generator.BANNER_WIDTH)

    return all_passed
