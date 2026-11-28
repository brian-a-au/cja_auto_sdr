"""Shared helpers for the Adobe credentials standard, version 1.

This module holds the one client ID mask, the notice and warning lines, the
file mode checks, and the ``.env`` bootstrap with the record of what it loaded.
It imports only the standard library, ``core.constants`` and
``core.error_policies``, so any module can use it without joining an import
cycle.

A notice or a warning is one line on stderr. It never goes to stdout, so it
cannot break JSON output, and it never changes the exit code.
"""

from __future__ import annotations

import hashlib
import logging
import os
import sys
from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cja_auto_sdr.core.constants import CREDENTIAL_FIELDS, ENV_VAR_MAPPING, HIDDEN_VALUE_DISPLAY
from cja_auto_sdr.core.error_policies import RECOVERABLE_DOTENV_BOOTSTRAP_EXCEPTIONS

__all__ = [
    "CONFIG_CHECK_SCHEMA",
    "LIVE_TEST_SCHEMA",
    "PRODUCT",
    "STANDARD_FIELDS",
    "STRICT_LOOKUP_RELEASE",
    "TOOL_NAME",
    "DotenvSnapshot",
    "bootstrap_dotenv",
    "dotenv_snapshot",
    "emit_notice",
    "emit_warning",
    "environment_field_origins",
    "forget_shown_messages",
    "make_private_dirs",
    "mask_client_id",
    "note_file_keys",
    "record_dotenv_load",
    "reset_credential_notice_state",
    "variable_names",
    "warn_if_readable_by_others",
]

# Names used in the JSON shapes of the standard.
CONFIG_CHECK_SCHEMA = "adobe-credentials/v1/config-check"
LIVE_TEST_SCHEMA = "adobe-credentials/v1/live-test"
TOOL_NAME = "cja_auto_sdr"
PRODUCT = "cja"

# The release that applies the strict lookup rules of the Adobe credentials standard.
STRICT_LOOKUP_RELEASE = "4.0"

# The four credential fields of the standard, in the order they are reported.
STANDARD_FIELDS: tuple[str, ...] = ("org_id", "client_id", "secret", "scopes")

# A run can use several processes, e.g. batch workers. Each line is shown once
# for the whole run, so the lines already shown are kept in this variable, which
# child processes inherit.
SHOWN_MESSAGES_VARIABLE = "_CJA_AUTO_SDR_SHOWN_MESSAGES"

_CLIENT_ID_VISIBLE_CHARS = 4
_GROUP_OR_OTHER_READ = 0o044
_PRIVATE_DIR_MODE = 0o700


def mask_client_id(client_id: Any) -> str:
    """Return the client ID as its first 4 characters, ``****``, and its last 4.

    A client ID of 8 characters or fewer is shown as ``****``. Every place that
    shows a client ID calls this function.
    """
    text = client_id if isinstance(client_id, str) else ""
    if len(text) <= _CLIENT_ID_VISIBLE_CHARS * 2:
        return HIDDEN_VALUE_DISPLAY
    return f"{text[:_CLIENT_ID_VISIBLE_CHARS]}{HIDDEN_VALUE_DISPLAY}{text[-_CLIENT_ID_VISIBLE_CHARS:]}"


def variable_names(fields: Iterable[str]) -> str:
    """Return the environment variable names for *fields*, e.g. ``SECRET, SCOPES``."""
    return ", ".join(ENV_VAR_MAPPING.get(name, name.upper()) for name in fields)


# ==================== NOTICE AND WARNING LINES ====================


def _message_token(code: str, dedupe_key: str) -> str:
    return hashlib.sha256(f"{code}|{dedupe_key}".encode()).hexdigest()[:16]


def _emit_once(label: str, code: str, message: str, dedupe_key: str | None) -> bool:
    token = _message_token(code, dedupe_key if dedupe_key is not None else message)
    shown = [item for item in os.environ.get(SHOWN_MESSAGES_VARIABLE, "").split(",") if item]
    if token in shown:
        return False
    shown.append(token)
    os.environ[SHOWN_MESSAGES_VARIABLE] = ",".join(shown)
    sys.stderr.write(f"{label} [{code}]: {message}\n")
    return True


def emit_notice(code: str, message: str, *, dedupe_key: str | None = None) -> bool:
    """Print one notice line on stderr, once per run. Returns True when it was printed.

    A notice says that a later release will act differently. *code* is a notice
    code of the standard.
    """
    return _emit_once("Notice", code, message, dedupe_key)


def emit_warning(code: str, message: str, *, dedupe_key: str | None = None) -> bool:
    """Print one warning line on stderr, once per run. Returns True when it was printed."""
    return _emit_once("Warning", code, message, dedupe_key)


def forget_shown_messages() -> None:
    """Forget the lines already shown.

    ``main()`` calls this when a run starts, so a record that the run inherited
    from another run of the tool cannot hide a line. Worker processes do not
    call it, so they keep the lines that the main process already showed.
    """
    os.environ.pop(SHOWN_MESSAGES_VARIABLE, None)


def reset_credential_notice_state() -> None:
    """Forget the lines already shown and the ``.env`` record. Tests call this."""
    global _dotenv_record  # noqa: PLW0603
    forget_shown_messages()
    _dotenv_record = None


# ==================== FILE AND FOLDER MODES ====================


def _file_modes_apply() -> bool:
    """Return False on Windows, where the mode bits do not describe access."""
    return os.name != "nt"


def readable_by_others(path: str | Path) -> bool:
    """Return True when the group or other users can read the file at *path*.

    The mode of a symlink's target is the one that counts. The check is skipped
    on Windows, where the mode bits do not describe access.
    """
    if not _file_modes_apply():
        return False
    try:
        mode = os.stat(path).st_mode
    except OSError:
        return False
    return bool(mode & _GROUP_OR_OTHER_READ)


def warn_if_readable_by_others(path: str | Path) -> bool:
    """Warn once per run when the credential file at *path* can be read by others."""
    if not readable_by_others(path):
        return False
    shown_path = os.path.abspath(path)
    emit_warning(
        "file_readable_by_others",
        f"Other users of this computer can read the credential file {shown_path}. Run: chmod 600 {shown_path}",
        dedupe_key=shown_path,
    )
    return True


def make_private_dirs(path: Path) -> None:
    """Create *path* and its missing parents. Each folder that is created gets mode 0700.

    A folder that already exists keeps its mode. The mode is not set on Windows.
    """
    missing: list[Path] = []
    current = path
    while not os.path.exists(current):
        missing.append(current)
        if current.parent == current:
            break
        current = current.parent
    path.mkdir(parents=True, exist_ok=True)
    if not _file_modes_apply():
        return
    for created in missing:
        os.chmod(created, _PRIVATE_DIR_MODE)


# ==================== FILE KEYS ====================


def note_file_keys(payload: Mapping[str, Any], path: str | Path, logger: logging.Logger) -> None:
    """Report the keys of a credential file that the tool does not read.

    A key the tool does not know gives one debug line that names the key. A
    credential key in upper case, e.g. ``ORG_ID``, also gives a warning, because
    file keys are lower case and the key was not read.
    """
    known = CREDENTIAL_FIELDS["all"]
    for key in payload:
        if key in known:
            continue
        logger.debug("Ignoring unknown key '%s' in %s", key, path)
        if isinstance(key, str) and key != key.lower() and key.lower() in known:
            shown_path = os.path.abspath(path)
            emit_warning(
                "upper_case_key",
                f"{shown_path} holds the key {key}. File keys are lower case, so this key was not read. "
                f"Rename it to {key.lower()}.",
                dedupe_key=f"{shown_path}|{key}",
            )


# ==================== THE .ENV RECORD ====================

# The path of the .env file that the bootstrap loaded, and the names of the
# variables that it set. None when the bootstrap did not run in this process.
_dotenv_record: tuple[str, frozenset[str]] | None = None


@dataclass(frozen=True)
class DotenvSnapshot:
    """What is known about the ``.env`` file of this run."""

    path: str | None = None
    values: dict[str, str] = field(default_factory=dict)
    # The names of the variables that the file set in this process. None when that
    # is not known, e.g. in a worker process that inherited its environment.
    loaded_names: frozenset[str] | None = None

    def credential_fields(self) -> list[str]:
        """Return the credential fields that the file holds a value for."""
        return [name for name, variable in ENV_VAR_MAPPING.items() if (self.values.get(variable) or "").strip()]

    def supplied(self, variable: str) -> bool:
        """Return True when the value of *variable* in the environment came from the file."""
        value = os.environ.get(variable)
        if value is None:
            return False
        if self.loaded_names is not None:
            return variable in self.loaded_names
        return self.values.get(variable) == value


def record_dotenv_load(path: str, loaded_names: Iterable[str]) -> None:
    """Remember the ``.env`` file that was loaded and the variables that it set."""
    global _dotenv_record  # noqa: PLW0603
    names = frozenset(loaded_names)
    if _dotenv_record is not None and _dotenv_record[0] == path:
        names |= _dotenv_record[1]
    _dotenv_record = (path, names)


def bootstrap_dotenv(logger: logging.Logger) -> None:
    """Load .env variables into the environment. Variables that are already set are kept."""
    try:
        from dotenv import find_dotenv, load_dotenv
    except ImportError:
        logger.debug("python-dotenv not installed (.env files will not be auto-loaded)")
        return
    except RECOVERABLE_DOTENV_BOOTSTRAP_EXCEPTIONS as e:
        logger.debug("Failed to import python-dotenv for .env auto-loading: %s", e)
        return

    try:
        dotenv_path = find_dotenv(usecwd=True)
        names_before = set(os.environ)
        dotenv_loaded = load_dotenv(dotenv_path)
        if isinstance(dotenv_path, str) and dotenv_path:
            # Remember which variables came from the file, so the config check can name it.
            record_dotenv_load(dotenv_path, set(os.environ) - names_before)
        if dotenv_loaded:
            logger.debug(".env file found and loaded")
        else:
            logger.debug(".env file not found (python-dotenv available but no .env file)")
    except RECOVERABLE_DOTENV_BOOTSTRAP_EXCEPTIONS as e:
        logger.debug("Failed to load .env via python-dotenv: %s", e)


def _dotenv_disabled() -> bool:
    # python-dotenv skips every load when this variable is set to a true value.
    return os.environ.get("PYTHON_DOTENV_DISABLED", "").casefold() in {"1", "true", "t", "yes", "y"}


def dotenv_snapshot() -> DotenvSnapshot:
    """Return the ``.env`` file of this run, with its values. Never raises."""
    try:
        from dotenv import dotenv_values, find_dotenv
    except ImportError:
        return DotenvSnapshot()

    try:
        if _dotenv_record is not None:
            path, loaded_names = _dotenv_record
        else:
            # The bootstrap did not run in this process. Look where it would look.
            path, loaded_names = ("" if _dotenv_disabled() else find_dotenv(usecwd=True)), None
        if not isinstance(path, str) or not path:
            return DotenvSnapshot()
        values = {key: value for key, value in dotenv_values(path).items() if isinstance(value, str)}
    except (OSError, ValueError):
        return DotenvSnapshot()
    return DotenvSnapshot(path=path, values=values, loaded_names=loaded_names)


def environment_field_origins(snapshot: DotenvSnapshot | None = None) -> dict[str, str]:
    """Return where each credential variable that is set came from.

    The result maps a field name to ``"dotenv"`` when the ``.env`` file set the
    variable, and to ``"environment"`` when the variable was already set.
    """
    snapshot = snapshot if snapshot is not None else dotenv_snapshot()
    origins: dict[str, str] = {}
    for name, variable in ENV_VAR_MAPPING.items():
        value = os.environ.get(variable)
        if not value or not value.strip():
            continue
        origins[name] = "dotenv" if snapshot.supplied(variable) else "environment"
    return origins
