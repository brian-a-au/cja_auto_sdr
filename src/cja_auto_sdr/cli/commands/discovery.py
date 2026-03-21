"""Shared discovery implementation — single source of truth for discovery internals.

Extracted from generator.py (v3.4.5) so that cli/commands/list.py and
generator.py both import from here instead of maintaining mirrored copies.
"""

# ruff: noqa: T201

from __future__ import annotations

import json
import re
import sys
from typing import Any

from cja_auto_sdr.core.colors import ConsoleColors
from cja_auto_sdr.core.discovery_normalization import (
    extract_owner_name as _extract_owner_name_normalized,
)
from cja_auto_sdr.core.discovery_normalization import (
    extract_owner_name_from_record as _extract_owner_name_from_record_normalized,
)
from cja_auto_sdr.core.discovery_normalization import (
    normalize_display_text as _normalize_display_text,
)

# ---------------------------------------------------------------------------
# Exception classes
# ---------------------------------------------------------------------------


class DiscoveryArgumentError(ValueError):
    """Raised when discovery filter/sort arguments are invalid."""


class OutputContractError(ValueError):
    """Raised when machine-readable command output violates JSON contracts."""


class DiscoveryOutputContractError(OutputContractError):
    """Raised when machine-readable discovery output violates JSON contracts."""


class DiscoveryNotFoundError(LookupError):
    """Raised when a requested discovery resource is not found."""


# ---------------------------------------------------------------------------
# Compiled regex constants
# ---------------------------------------------------------------------------

_NUMERIC_SORT_VALUE_RE = re.compile(r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$")


# ---------------------------------------------------------------------------
# Normalisation helpers
# ---------------------------------------------------------------------------


def _normalize_optional_text(value: Any, *, default: str = "") -> str:
    """Normalize optional display values, handling None/NaN and whitespace."""
    return _normalize_display_text(
        value,
        default=default,
        treat_null_like_strings=True,
    )


def _extract_owner_name(owner_data: Any) -> str:
    """Extract a displayable owner name from an API owner object.

    The owner field varies across CJA API endpoints:
    - Data views may return ``{"name": "Jane Doe"}``
    - Connections may return ``{"imsUserId": "ABC@AdobeID"}``
    - Some endpoints return ``None`` or a bare string.
    """
    return _extract_owner_name_normalized(owner_data, default="N/A")


def _extract_owner_name_from_record(record: dict[str, Any]) -> str:
    """Extract owner name from record-level owner aliases used by CJA endpoints."""
    return _extract_owner_name_from_record_normalized(record, default="N/A")


def _extract_timestamp_from_record(record: dict[str, Any], field: str) -> str:
    """Extract created/modified timestamps from common CJA field aliases."""
    aliases_by_field = {
        "created": ("created", "createdDate", "createdAt", "created_date"),
        "modified": ("modified", "modifiedDate", "modifiedAt", "modified_date"),
    }
    aliases = aliases_by_field.get(field, (field,))
    for key in aliases:
        value = _normalize_optional_text(record.get(key))
        if value:
            return value
    return ""


def _to_searchable_text(value: Any) -> str:
    """Convert nested values to text for filter/exclude matching."""
    if value is None:
        return ""
    if isinstance(value, (str, int, float, bool)):
        return str(value)
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


# ---------------------------------------------------------------------------
# Machine-readable output helpers
# ---------------------------------------------------------------------------


def _is_machine_readable_output(output_format: str | None, output_file: str | None = None) -> bool:
    """Return True when command output is intended for machine consumption."""
    return output_format in ("json", "csv") or output_file in ("-", "stdout")


def _format_discovery_json(payload: dict) -> str:
    """Format discovery payloads with a discovery-specific contract label."""
    try:
        return json.dumps(payload, indent=2, allow_nan=False)
    except ValueError as exc:
        raise DiscoveryOutputContractError(
            "Discovery output contains non-JSON-compliant values",
        ) from exc


def _emit_discovery_error(
    message: str,
    *,
    is_machine_readable: bool,
    error_type: str,
    additional_fields: dict[str, Any] | None = None,
    human_to_stderr: bool = False,
) -> None:
    """Emit discovery/inspection errors in machine or human-readable form."""
    if is_machine_readable:
        payload: dict[str, Any] = {"error": message, "error_type": error_type}
        if additional_fields:
            payload.update(additional_fields)
        print(json.dumps(payload, allow_nan=False), file=sys.stderr)
        return

    stream = sys.stderr if human_to_stderr else sys.stdout
    print(ConsoleColors.error(f"ERROR: {message}"), file=stream)


def _emit_output_contract_error(
    message: str,
    *,
    is_machine_readable: bool,
    human_to_stderr: bool = True,
) -> None:
    """Emit output-contract violations using a stable error envelope."""
    _emit_discovery_error(
        message,
        is_machine_readable=is_machine_readable,
        error_type="output_contract",
        human_to_stderr=human_to_stderr,
    )


def _emit_json_output(
    payload: dict[str, Any],
    *,
    output_file: str | None,
    is_stdout: bool,
    contract_label: str,
    human_error_to_stderr: bool = True,
) -> None:
    """Serialize payload to strict JSON and emit it, exiting cleanly on contract errors."""
    # Local import to avoid circular dependency: generator -> discovery -> generator
    from cja_auto_sdr.generator import _emit_output

    try:
        serialized_payload = json.dumps(payload, indent=2, allow_nan=False)
    except ValueError as exc:
        _emit_output_contract_error(
            f"{contract_label} contains non-JSON-compliant values",
            is_machine_readable=_is_machine_readable_output("json", output_file),
            human_to_stderr=human_error_to_stderr,
        )
        raise SystemExit(1) from exc

    _emit_output(serialized_payload, output_file, is_stdout)


def _resolve_discovery_output_format(raw_format: str | None, *, output_to_stdout: bool) -> str:
    """Normalize discovery output format with stdout piping semantics."""
    # Local import to avoid circular dependency: generator -> discovery -> generator
    from cja_auto_sdr.generator import _resolve_command_output_format

    return _resolve_command_output_format(
        raw_format,
        supported_formats={"json": "json", "csv": "csv", "console": "table", "table": "table"},
        fallback_format="table",
        output_to_stdout=output_to_stdout,
        stdout_fallback_format="json",
        stdout_allowed_formats={"json", "csv"},
        warning_scope="this command",
    )
