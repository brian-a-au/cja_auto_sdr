"""The config check of the Adobe credentials standard: ``--show-config``.

The check reports how the tool would find the credential, without a network
call. It follows the lookup of ``core.credentials.CredentialResolver`` step by
step and names every source that holds a value, with the path of each file.
The JSON output has the config check shape of the standard, version 1.
"""

# ruff: noqa: T201

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from cja_auto_sdr.core.constants import BANNER_WIDTH, CREDENTIAL_FIELDS, HIDDEN_VALUE_DISPLAY
from cja_auto_sdr.core.credential_notices import (
    CONFIG_CHECK_SCHEMA,
    PRODUCT,
    STANDARD_FIELDS,
    TOOL_NAME,
    DotenvSnapshot,
    dotenv_snapshot,
    environment_field_origins,
    mask_client_id,
    note_file_keys,
    readable_by_others,
    variable_names,
    warn_if_readable_by_others,
)
from cja_auto_sdr.core.credentials import (
    STRICT_LOOKUP_RELEASE,
    describe_environment_source,
    dotenv_and_config_differ,
    dotenv_and_config_message,
    filter_credentials,
    load_credentials_from_env,
    missing_standard_fields,
    mixed_environment_message,
    partial_environment_message,
    validate_env_credentials,
)
from cja_auto_sdr.core.version import __version__

__all__ = ["build_config_check", "profile_and_config_message", "render_config_check", "show_config"]

_ALL_FIELDS: tuple[str, ...] = (*STANDARD_FIELDS, "sandbox")
_WAYS_TO_GIVE_A_CREDENTIAL = (
    "Give a credential in one of these ways: a profile (cja_auto_sdr --profile-add <name>), "
    "the variables ORG_ID, CLIENT_ID, SECRET and SCOPES, or a config.json file (cja_auto_sdr --sample-config)."
)


def profile_and_config_message(profile: str, *, profile_from_flag: bool) -> str:
    """Return the notice text for a profile and a config file that are both given."""
    if profile_from_flag:
        return (
            "--profile and --config-file were both given. "
            f"This run uses the profile {profile} and does not read the config file. "
            f"Release {STRICT_LOOKUP_RELEASE} will stop with an error instead."
        )
    return (
        "CJA_PROFILE is set and --config-file was given. "
        f"This run uses the profile {profile} and does not read the config file. "
        f"Release {STRICT_LOOKUP_RELEASE} will use the config file instead."
    )


def _quiet_logger() -> logging.Logger:
    """A logger for the validation helpers, whose warning lines the check does not show."""
    quiet = logging.getLogger(f"{__name__}.quiet")
    quiet.setLevel(logging.CRITICAL)
    return quiet


def _fields_of(credentials: dict[str, Any] | None) -> list[str]:
    return [name for name in _ALL_FIELDS if (credentials or {}).get(name)]


def _source(kind: str, name: str, path: str | None, fields: list[str]) -> dict[str, Any]:
    return {"kind": kind, "name": name, "path": path, "used": False, "fields": fields, "skipped": None}


def _problem(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"code": code, "message": message, **extra}


def _partial_problem(name: str, missing: list[str]) -> dict[str, Any]:
    return _problem(
        "partial_source",
        f"{name} is missing: {', '.join(missing)}. A credential needs org_id, client_id, secret and scopes.",
        missing=missing,
    )


class _ConfigCheck:
    """Builds the config check by following the lookup one source at a time."""

    def __init__(
        self,
        *,
        profile_flag: str | None,
        config_file: str | Path,
        config_file_given: bool,
        logger: logging.Logger,
    ) -> None:
        self.config_file = config_file
        self.config_file_given = config_file_given
        self.logger = logger
        self.sources: list[dict[str, Any]] = []
        self.problems: list[dict[str, Any]] = []
        self.notices: list[dict[str, Any]] = []
        self.warnings: list[dict[str, Any]] = []
        self.credential: dict[str, Any] = {}
        self.winner: dict[str, Any] | None = None
        self.used_text = ""
        # The missing fields of a partial set of environment variables that was skipped.
        self.partial_environment: list[str] | None = None

        flag = profile_flag.strip() if isinstance(profile_flag, str) else ""
        variable = (os.environ.get("CJA_PROFILE") or "").strip()
        self.profile: str | None = flag or variable or None
        self.profile_kind = "flag_profile" if flag else "profile_variable"
        self.snapshot: DotenvSnapshot = dotenv_snapshot()

    # ---------- reading ----------

    def _note_file(self, path: Path) -> None:
        """Warn when others can read a credential file, and record the warning."""
        if readable_by_others(path):
            warn_if_readable_by_others(path)
            self.warnings.append(
                {
                    "code": "file_readable_by_others",
                    "message": f"Other users of this computer can read {os.path.abspath(path)}.",
                    "path": os.path.abspath(path),
                }
            )

    def _read_config_file(self, path: Path) -> dict[str, str] | None:
        """Read the credential fields of a config file. None when it cannot be read."""
        self._note_file(path)
        try:
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
        except (OSError, ValueError) as e:
            self.logger.debug("Cannot read %s: %s", path, e)
            return None
        if not isinstance(payload, dict):
            return None
        note_file_keys(payload, path, self.logger)
        return filter_credentials(payload)

    # ---------- the three steps of the lookup ----------

    def _check_profile(self, profile: str) -> bool:
        """Follow the profile step. Returns True, because a profile never falls back."""
        from cja_auto_sdr.core import profiles

        name = f"profile {profile}"
        is_valid, error = profiles.validate_profile_name(profile)
        if not is_valid:
            self.problems.append(_problem("invalid_profile_name", str(error)))
            return True
        folder = profiles.get_profile_path(profile)
        if not os.path.isdir(folder):
            self.problems.append(
                _problem("profile_not_found", f"Profile '{profile}' not found. Expected directory: {folder}")
            )
            return True

        config_path, dotenv_path = folder / "config.json", folder / ".env"
        for path in (config_path, dotenv_path):
            if os.path.exists(path):
                self._note_file(path)
        from_json = profiles.load_profile_config_json(folder) or {}
        from_dotenv = profiles.load_profile_dotenv(folder) or {}
        merged = {**from_json, **from_dotenv}

        entries: dict[str, dict[str, Any]] = {}
        for label, path, values in (("config.json", config_path, from_json), (".env", dotenv_path, from_dotenv)):
            if values:
                entries[label] = _source(self.profile_kind, f"{name} {label}", str(path), _fields_of(values))
        self.sources.extend(entries.values())
        if not merged:
            self.problems.append(
                _problem("no_credential", f"Profile '{profile}' has no credential in config.json or .env in {folder}")
            )
            return True

        self.credential = merged
        missing = missing_standard_fields(merged)
        if missing:
            for entry in entries.values():
                entry["skipped"], entry["missing"] = "partial", missing
            self.problems.append(_partial_problem(f"The profile {profile}", missing))
            return True

        # The profile's .env wins key by key over its config.json.
        dotenv_fields = [field for field in STANDARD_FIELDS if from_dotenv.get(field)]
        json_fields = [field for field in STANDARD_FIELDS if field not in dotenv_fields]
        for label, used_fields in (("config.json", json_fields), (".env", dotenv_fields)):
            if label in entries:
                entries[label]["used"] = bool(used_fields)
                if not used_fields:
                    entries[label]["skipped"] = "lower_priority"
        self.winner = next(entry for entry in entries.values() if entry["used"])
        self.used_text = f"the profile {profile}"
        if dotenv_fields and json_fields:
            self._notice(
                "mixed_sources",
                f"The profile {profile} mixes config.json ({', '.join(json_fields)}) with .env "
                f"({', '.join(dotenv_fields)}). This run uses them together. "
                f"Release {STRICT_LOOKUP_RELEASE} will take all four fields from one file.",
            )
        return True

    def _check_environment(self, *, decided: bool) -> bool:
        """Follow the environment step. Returns True when the environment gives the credential."""
        origins = environment_field_origins(self.snapshot)
        entries: dict[str, dict[str, Any]] = {}
        from_environment = [name for name in _ALL_FIELDS if origins.get(name) == "environment"]
        if from_environment:
            entries["environment"] = _source("environment", "environment variables", None, from_environment)
        dotenv_fields = self.snapshot.credential_fields()
        if self.snapshot.path and dotenv_fields:
            self._note_file(Path(self.snapshot.path))
            entries["dotenv"] = _source("dotenv", ".env file", self.snapshot.path, dotenv_fields)
        self.sources.extend(entries.values())
        if decided:
            for entry in entries.values():
                entry["skipped"] = "lower_priority"
            return False

        credentials = load_credentials_from_env()
        if not credentials:
            if "dotenv" in entries:
                # Every variable in the file was already set to an empty value, or the file was not loaded.
                entries["dotenv"]["skipped"] = "lower_priority"
            return False

        if validate_env_credentials(credentials, _quiet_logger()):
            self.credential = credentials
            missing = missing_standard_fields(credentials)
            if missing:
                # This release uses the variables without scopes, and then sign-in cannot start.
                for kind, entry in entries.items():
                    if any(origins.get(name) == kind for name in _ALL_FIELDS):
                        entry["skipped"], entry["missing"] = "partial", missing
                    else:
                        entry["skipped"] = "lower_priority"
                self.problems.append(_partial_problem("The credential in the environment variables", missing))
                return True
            for kind, entry in entries.items():
                entry["used"] = any(origins.get(name) == kind for name in STANDARD_FIELDS)
                if not entry["used"]:
                    entry["skipped"] = "lower_priority"
            self.winner = next((entry for entry in entries.values() if entry["used"]), None)
            self.used_text = describe_environment_source(origins, self.snapshot.path)
            mixed = mixed_environment_message(origins, self.snapshot.path)
            if mixed:
                self._notice("mixed_sources", mixed)
            return True

        missing = missing_standard_fields(credentials)
        is_partial = len(missing) < len(STANDARD_FIELDS) and any(
            name in CREDENTIAL_FIELDS["required"] for name in missing
        )
        for kind, entry in entries.items():
            if kind == "dotenv" and not any(origins.get(name) == "dotenv" for name in _ALL_FIELDS):
                entry["skipped"] = "lower_priority"
            elif is_partial:
                entry["skipped"], entry["missing"] = "partial", missing
            elif len(missing) < len(STANDARD_FIELDS):
                entry["reason"] = "A value is not valid, so this release skips the environment variables."
        if is_partial:
            self.partial_environment = missing
        return False

    def _check_config_file(self, *, decided: bool) -> None:
        """Follow the config file step."""
        path = Path(self.config_file)
        kind = "flag_config" if self.config_file_given else "default_config"
        exists = os.path.exists(path)
        credentials = self._read_config_file(path) if exists else None
        if credentials:
            entry = _source(kind, f"config file {path.name}", str(path.resolve()), _fields_of(credentials))
            self.sources.append(entry)
            if decided:
                entry["skipped"] = "lower_priority"
                return
            self.credential = credentials
            missing = missing_standard_fields(credentials)
            if missing:
                entry["skipped"], entry["missing"] = "partial", missing
                self.problems.append(_partial_problem(f"The config file {path.resolve()}", missing))
                return
            entry["used"] = True
            self.winner = entry
            self.used_text = f"the config file ({path.resolve()})"
            return
        if decided:
            return
        if exists:
            message = f"The config file {path.resolve()} holds no credential field that the tool can read. "
        elif self.config_file_given:
            message = f"The config file {path} was not found, and no other source gave a credential. "
        else:
            message = "No source gave a credential. "
        self.problems.append(_problem("no_credential", message + _WAYS_TO_GIVE_A_CREDENTIAL))

    # ---------- notices ----------

    def _notice(self, code: str, message: str, **extra: Any) -> None:
        self.notices.append({"code": code, "message": message, **extra})

    def _add_lookup_notices(self) -> None:
        if self.profile and self.config_file_given:
            self._notice(
                "profile_and_config_both_given",
                profile_and_config_message(self.profile, profile_from_flag=self.profile_kind == "flag_profile"),
            )
        if self.partial_environment:
            next_source = "reads the config file" if self.winner else "finds no other credential"
            self._notice(
                "partial_source_skipped",
                partial_environment_message(self.partial_environment, next_source=next_source),
                missing=self.partial_environment,
            )
        differ, dotenv_path = dotenv_and_config_differ(self.config_file)
        if differ and dotenv_path and self.winner:
            self._notice(
                "dotenv_and_config_differ",
                dotenv_and_config_message(dotenv_path, self.config_file, self.used_text),
            )

    # ---------- the result ----------

    def build(self) -> dict[str, Any]:
        decided = self._check_profile(self.profile) if self.profile else False
        if self.profile and os.environ.get("CJA_PROFILE") and self.profile_kind == "profile_variable":
            set_by = self.snapshot.path if self.snapshot.supplied("CJA_PROFILE") else None
            for entry in self.sources:
                entry["variable"] = "CJA_PROFILE"
                if set_by:
                    entry["variable_set_by"] = set_by
        decided = self._check_environment(decided=decided) or decided
        self._check_config_file(decided=decided)
        self._add_lookup_notices()

        credential = self.credential
        ok = self.winner is not None and not self.problems and not missing_standard_fields(credential)
        return {
            "schema": CONFIG_CHECK_SCHEMA,
            "tool": TOOL_NAME,
            "tool_version": __version__,
            "product": PRODUCT,
            "ok": ok,
            "profile": self.profile,
            "source": (
                {key: self.winner.get(key) for key in ("kind", "name", "path")} if self.winner is not None else None
            ),
            "sources": self.sources,
            "credential": {
                "org_id": credential.get("org_id") or None,
                "client_id": mask_client_id(credential["client_id"]) if credential.get("client_id") else None,
                "secret_set": bool(credential.get("secret")),
                "scopes": credential.get("scopes") or None,
                "sandbox": credential.get("sandbox") or None,
            },
            "problems": self.problems,
            "notices": self.notices,
            "warnings": self.warnings,
        }


def build_config_check(
    *,
    profile_flag: str | None = None,
    config_file: str | Path = "config.json",
    config_file_given: bool = False,
    logger: logging.Logger | None = None,
) -> dict[str, Any]:
    """Return the config check as a dict in the shape of the standard. Makes no network call.

    Args:
        profile_flag: The value of ``--profile`` when the flag was given, else None.
            ``CJA_PROFILE`` is read here.
        config_file: The config file path, from ``--config-file`` or the default.
        config_file_given: True when ``--config-file`` or ``--config`` was given.
        logger: Receives the debug line for each unknown key of a file.
    """
    from cja_auto_sdr.api.client import _bootstrap_dotenv

    logger = logger or logging.getLogger(__name__)
    # The lookup loads .env first, so the check does the same.
    _bootstrap_dotenv(logger)
    return _ConfigCheck(
        profile_flag=profile_flag,
        config_file=config_file,
        config_file_given=config_file_given,
        logger=logger,
    ).build()


def _source_status(entry: dict[str, Any]) -> str:
    if entry["used"]:
        return "used"
    if entry.get("skipped") == "partial":
        return f"skipped, missing {', '.join(entry.get('missing', []))}"
    if entry.get("skipped") == "lower_priority":
        return "not used, a higher source won"
    return "not used"


def render_config_check(report: dict[str, Any]) -> str:
    """Return the config check as text for a person."""
    credential = report["credential"]
    lines = ["", "=" * BANNER_WIDTH, "CREDENTIAL CONFIGURATION", "=" * BANNER_WIDTH, ""]
    lines.append(f"Result: {'ready' if report['ok'] else 'not ready'}")
    lines.append(f"Profile: {report['profile'] or '(none)'}")
    lines.append("")
    lines.append("Sources, highest first:")
    if not report["sources"]:
        lines.append("  (no source holds a value)")
    for entry in report["sources"]:
        lines.append(f"  - {entry['name']} ({_source_status(entry)})")
        if entry.get("path"):
            lines.append(f"      file: {entry['path']}")
        elif entry["kind"] == "environment":
            lines.append(f"      variables: {variable_names(entry['fields'])}")
        if entry.get("variable_set_by"):
            lines.append(f"      CJA_PROFILE was set by: {entry['variable_set_by']}")
        lines.append(f"      fields: {', '.join(entry['fields'])}")
        if entry.get("reason"):
            lines.append(f"      {entry['reason']}")
    lines.append("")
    lines.append("Credential:")
    lines.append(f"  org_id: {credential['org_id'] or 'not set'}")
    lines.append(f"  client_id: {credential['client_id'] or 'not set'}")
    lines.append(f"  secret: {HIDDEN_VALUE_DISPLAY if credential['secret_set'] else 'not set'}")
    lines.append(f"  scopes: {credential['scopes'] or 'not set'}")
    lines.append(f"  sandbox: {credential['sandbox'] or 'not set (optional)'}")
    # Warnings are printed on stderr when a file is read, so they are not repeated here.
    for title, key in (("Problems", "problems"), ("Notices", "notices")):
        if report[key]:
            lines.append("")
            lines.append(f"{title}:")
            lines.extend(f"  - [{item['code']}] {item['message']}" for item in report[key])
    lines.append("")
    if report["ok"]:
        lines.append("To test the credential against Adobe, run:")
        lines.append("  cja_auto_sdr --validate-config")
        lines.append("")
    return "\n".join(lines)


def show_config(
    config_file: str | Path = "config.json",
    *,
    profile_flag: str | None = None,
    config_file_given: bool = False,
    output_json: bool = False,
) -> bool:
    """Print the config check. Returns True when the credential is ready to use."""
    report = build_config_check(
        profile_flag=profile_flag,
        config_file=config_file,
        config_file_given=config_file_given,
    )
    if output_json:
        print(json.dumps(report, indent=2))
    else:
        print(render_config_check(report))
    return bool(report["ok"])
