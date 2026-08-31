"""Shared discovery implementation — single source of truth for discovery internals.

Extracted from generator.py (v3.4.5) so that cli/commands/list.py and
generator.py both import from here instead of maintaining mirrored copies.
"""

# ruff: noqa: T201

from __future__ import annotations

import json
import logging
import re
import shutil
import sys
import textwrap
from collections.abc import Callable
from dataclasses import dataclass, field
from numbers import Integral
from typing import Any

import pandas as pd

from cja_auto_sdr.api.client import _normalize_dataview_listing_payload_or_raise
from cja_auto_sdr.api.resilience import make_api_call_with_retry
from cja_auto_sdr.core.colors import ConsoleColors
from cja_auto_sdr.core.discovery_exceptions import (
    is_dataview_lookup_not_found_error as _is_inaccessible_dataview_lookup_error_core,
)
from cja_auto_sdr.core.discovery_normalization import (
    extract_owner_name as _extract_owner_name_normalized,
)
from cja_auto_sdr.core.discovery_normalization import (
    extract_owner_name_from_record as _extract_owner_name_from_record_normalized,
)
from cja_auto_sdr.core.discovery_normalization import (
    extract_tags as _extract_tags_normalized,
)
from cja_auto_sdr.core.discovery_normalization import (
    is_missing_value as _is_missing_discovery_value,
)
from cja_auto_sdr.core.discovery_normalization import (
    normalize_display_text as _normalize_display_text,
)
from cja_auto_sdr.core.discovery_normalization import (
    pick_first_present_text as _pick_first_present_text,
)
from cja_auto_sdr.core.discovery_payloads import (
    DataViewLookupAssessment as _DataViewLookupAssessment,
)
from cja_auto_sdr.core.discovery_payloads import (
    PayloadKind as _PayloadKind,
)
from cja_auto_sdr.core.discovery_payloads import (
    assess_component_payload as _assess_component_payload,
)
from cja_auto_sdr.core.discovery_payloads import (
    assess_dataview_lookup_payload as _assess_dataview_lookup_payload,
)
from cja_auto_sdr.core.discovery_payloads import (
    count_component_items_or_na as _count_component_items_or_na_from_assessment,
)
from cja_auto_sdr.core.error_policies import RECOVERABLE_OPTIONAL_ENRICHMENT_EXCEPTIONS

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
# Query / filter / sort helpers
# ---------------------------------------------------------------------------


def _to_numeric_sort_value(value: Any) -> float | None:
    """Convert a sortable value to float when it is numerically representable."""
    if value is None or isinstance(value, bool):
        return None

    if isinstance(value, (int, float)):
        try:
            if pd.isna(value):
                return None
        except TypeError, ValueError:
            return None
        return float(value)

    if isinstance(value, str):
        stripped = value.strip()
        if not stripped or not _NUMERIC_SORT_VALUE_RE.fullmatch(stripped):
            return None
        try:
            return float(stripped)
        except ValueError:  # pragma: no cover — regex guard prevents this
            return None

    return None


def _is_missing_sort_value(value: Any) -> bool:
    """Return True for values that should be sorted after concrete values."""
    if value is None:
        return True
    if isinstance(value, str) and not value.strip():
        return True
    try:
        return bool(pd.isna(value))
    except TypeError, ValueError:
        return False


def _compile_discovery_pattern(pattern: str | None, *, option_name: str) -> re.Pattern[str] | None:
    """Compile a discovery regex and raise a user-facing validation error on failure."""
    if not pattern:
        return None
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise DiscoveryArgumentError(f"Invalid {option_name} regex '{pattern}': {exc!s}") from exc


def _validate_discovery_query_inputs(
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
) -> None:
    """Validate discovery query flags before executing API calls."""
    _compile_discovery_pattern(filter_pattern, option_name="--filter")
    _compile_discovery_pattern(exclude_pattern, option_name="--exclude")
    if limit is not None and limit < 0:
        raise DiscoveryArgumentError("--limit cannot be negative")


def _apply_discovery_filters_and_sort(
    rows: list[dict[str, Any]],
    *,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
    searchable_fields: list[str] | None = None,
    default_sort_field: str = "name",
) -> list[dict[str, Any]]:
    """Apply filter/exclude/sort/limit to discovery rows."""
    if limit is not None and limit < 0:
        raise DiscoveryArgumentError("--limit cannot be negative")

    filtered_rows = list(rows)
    fields = searchable_fields or list(rows[0].keys()) if rows else []

    filter_re = _compile_discovery_pattern(filter_pattern, option_name="--filter")
    exclude_re = _compile_discovery_pattern(exclude_pattern, option_name="--exclude")

    # Compute per-row searchable blobs once when filter/exclude is requested.
    if filter_re or exclude_re:
        searchable_rows = [
            (row, " ".join(_to_searchable_text(row.get(field, "")) for field in fields)) for row in filtered_rows
        ]
        if filter_re:
            searchable_rows = [(row, blob) for row, blob in searchable_rows if filter_re.search(blob)]
        if exclude_re:
            searchable_rows = [(row, blob) for row, blob in searchable_rows if not exclude_re.search(blob)]
        filtered_rows = [row for row, _ in searchable_rows]

    sort_field = default_sort_field
    reverse = False
    if sort_expression:
        sort_expr = sort_expression.strip()
        if sort_expr.startswith("-"):
            reverse = True
            sort_field = sort_expr[1:]
        else:
            sort_field = sort_expr

    non_missing_values = [
        row.get(sort_field) for row in filtered_rows if not _is_missing_sort_value(row.get(sort_field))
    ]
    use_numeric_sort = bool(non_missing_values) and all(
        _to_numeric_sort_value(value) is not None for value in non_missing_values
    )

    concrete_rows: list[tuple[float | str, dict[str, Any]]] = []
    missing_rows: list[dict[str, Any]] = []
    for row in filtered_rows:
        raw_value = row.get(sort_field)
        if _is_missing_sort_value(raw_value):
            missing_rows.append(row)
            continue

        if use_numeric_sort:
            numeric_value = _to_numeric_sort_value(raw_value)
            if numeric_value is None:
                missing_rows.append(row)
                continue
            concrete_rows.append((numeric_value, row))
        else:
            concrete_rows.append((_to_searchable_text(raw_value).casefold(), row))

    concrete_rows.sort(key=lambda item: item[0], reverse=reverse)
    filtered_rows = [row for _, row in concrete_rows] + missing_rows

    if limit is not None:
        filtered_rows = filtered_rows[:limit]

    return filtered_rows


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
    from cja_auto_sdr.cli.agent_output import DISCOVERY_STDOUT_FORMATS

    # Local import to avoid circular dependency: generator -> discovery -> generator
    from cja_auto_sdr.generator import _resolve_command_output_format

    return _resolve_command_output_format(
        raw_format,
        supported_formats={"json": "json", "csv": "csv", "console": "table", "table": "table"},
        fallback_format="table",
        output_to_stdout=output_to_stdout,
        stdout_fallback_format="json",
        stdout_allowed_formats=DISCOVERY_STDOUT_FORMATS,
        warning_scope="discovery commands",
    )


# ---------------------------------------------------------------------------
# Dataview lookup helpers
# ---------------------------------------------------------------------------


def _assess_dataview_lookup(
    raw_payload: Any,
    *,
    data_view_id: str,
    require_expected_id: bool = True,
) -> _DataViewLookupAssessment:
    """Assess a getDataView payload with a consistent expected-id policy."""
    expected_data_view_id = data_view_id if require_expected_id else None
    return _assess_dataview_lookup_payload(raw_payload, expected_data_view_id=expected_data_view_id)


def _coerce_valid_dataview_lookup_payload(
    raw_payload: Any,
    *,
    data_view_id: str,
    require_expected_id: bool = True,
) -> tuple[dict[str, Any] | None, str, str]:
    """Return a validated lookup payload or structured failure metadata."""
    assessment = _assess_dataview_lookup(
        raw_payload,
        data_view_id=data_view_id,
        require_expected_id=require_expected_id,
    )
    if assessment.is_valid and assessment.payload is not None:
        return assessment.payload, assessment.reason, assessment.raw_type
    return None, assessment.reason, assessment.raw_type


def _fetch_dataview_lookup_payload(cja: Any, data_view_id: str) -> Any:
    """Call getDataView and normalize inaccessible lookup failures to not_found."""
    try:
        return cja.getDataView(data_view_id)
    except (
        Exception
    ) as lookup_error:  # Intentional: wrapped client/transport lookup failures vary; re-raise non-404/403 cases
        # Classification is centralized in core.discovery_exceptions and supports
        # nested/wrapped transport errors across diverse exception types.
        if _is_inaccessible_dataview_lookup_error_core(lookup_error):
            raise DiscoveryNotFoundError(f"Data view '{data_view_id}' not found") from lookup_error
        raise


def _require_accessible_dataview(cja: Any, data_view_id: str) -> dict[str, Any]:
    """Fetch a data view and raise DiscoveryNotFoundError when inaccessible/invalid."""
    raw_payload = _fetch_dataview_lookup_payload(cja, data_view_id)

    payload, _, _ = _coerce_valid_dataview_lookup_payload(raw_payload, data_view_id=data_view_id)
    if payload is None:
        raise DiscoveryNotFoundError(f"Data view '{data_view_id}' not found")
    return payload


def _normalize_describe_dataview_metadata(raw_dv: dict[str, Any], *, default_id: str) -> dict[str, str]:
    """Normalize describe_dataview metadata fields for safe display/serialization."""
    connection_id = _pick_first_present_text(
        (
            raw_dv.get("parentDataGroupId"),
            raw_dv.get("connectionId"),
            raw_dv.get("connection_id"),
        ),
        default="N/A",
        treat_null_like_strings=True,
    )
    created = _extract_timestamp_from_record(raw_dv, "created") or "N/A"
    modified = _extract_timestamp_from_record(raw_dv, "modified") or "N/A"
    return {
        "id": _normalize_optional_text(raw_dv.get("id"), default=default_id),
        "name": _normalize_optional_text(raw_dv.get("name"), default="N/A"),
        "owner": _extract_owner_name_from_record(raw_dv),
        "description": _normalize_optional_text(raw_dv.get("description"), default=""),
        "connection_id": connection_id,
        "created": created,
        "modified": modified,
    }


def _resolve_dataview_name(cja: Any, data_view_id: str, *, preferred_name: str | None = None) -> str:
    """Look up a canonical data view display name with safe fallback behavior."""
    raw_dv = _require_accessible_dataview(cja, data_view_id)
    normalized_name = _normalize_optional_text(raw_dv.get("name"), default="")
    if normalized_name:
        return normalized_name
    normalized_preferred = _normalize_optional_text(preferred_name, default="")
    return normalized_preferred or "Unknown"


# ---------------------------------------------------------------------------
# Component fetch specs, helpers, and row builders
# ---------------------------------------------------------------------------

# Any Exception should degrade to a fallback count for best-effort component counting.
RECOVERABLE_OPTIONAL_COMPONENT_COUNT_EXCEPTIONS: tuple[type[Exception], ...] = (Exception,)


@dataclass(frozen=True)
class _ComponentFetchSpec:
    """Describe how to fetch one component collection for a data view."""

    method_name: str
    data_view_arg_name: str | None = None
    kwargs: dict[str, str | bool] = field(default_factory=dict)


_METRICS_COMPONENT_FETCH_SPEC = _ComponentFetchSpec(
    method_name="getMetrics",
    kwargs={"inclType": "hidden", "full": True},
)

_DIMENSIONS_COMPONENT_FETCH_SPEC = _ComponentFetchSpec(
    method_name="getDimensions",
    kwargs={"inclType": "hidden", "full": True},
)

_SEGMENTS_COMPONENT_FETCH_SPEC = _ComponentFetchSpec(
    method_name="getFilters",
    data_view_arg_name="dataIds",
    kwargs={"full": True},
)

_CALCULATED_METRICS_COMPONENT_FETCH_SPEC = _ComponentFetchSpec(
    method_name="getCalculatedMetrics",
    data_view_arg_name="dataIds",
    kwargs={"full": True},
)


def _fetch_component_payload(cja: Any, data_view_id: str, fetch_spec: _ComponentFetchSpec) -> Any:
    """Invoke a component-list API call using a declarative fetch spec."""
    fetch_method = getattr(cja, fetch_spec.method_name, None)
    if not callable(fetch_method):
        raise DiscoveryNotFoundError(
            f"CJA client missing expected method '{fetch_spec.method_name}' for data view '{data_view_id}'",
        )

    kwargs = dict(fetch_spec.kwargs)
    if fetch_spec.data_view_arg_name:
        kwargs[fetch_spec.data_view_arg_name] = data_view_id
        return fetch_method(**kwargs)
    return fetch_method(data_view_id, **kwargs)


def _normalize_component_records_or_raise(
    raw_payload: Any,
    *,
    component_label: str,
    data_view_id: str,
) -> list[dict[str, Any]]:
    """Normalize component payloads to dict rows or fail on error-shaped responses."""
    assessment = _assess_component_payload(raw_payload)
    if assessment.kind is _PayloadKind.ERROR:
        raise DiscoveryNotFoundError(f"Failed to retrieve {component_label} for data view '{data_view_id}'")
    if assessment.kind is _PayloadKind.INVALID:
        raise DiscoveryNotFoundError(
            f"Unexpected {component_label} payload type for data view '{data_view_id}'",
        )
    return assessment.rows


def _count_component_items_for_fetch_spec(cja: Any, data_view_id: str, fetch_spec: _ComponentFetchSpec) -> int | str:
    """Return a component count for one fetch spec, falling back to 'N/A' on runtime failures."""
    return _count_component_items_for_fetch_spec_best_effort(
        cja,
        data_view_id,
        fetch_spec,
        fallback_value="N/A",
        use_retry=False,
    )


def _count_component_items_for_fetch_spec_best_effort(
    cja: Any,
    data_view_id: str,
    fetch_spec: _ComponentFetchSpec,
    *,
    fallback_value: int | str,
    use_retry: bool,
    logger: logging.Logger | None = None,
) -> int | str:
    """Fetch one component payload and degrade failures to a caller-provided fallback value."""
    component_label = fetch_spec.method_name
    try:
        if use_retry:
            payload = make_api_call_with_retry(
                _fetch_component_payload,
                cja,
                data_view_id,
                fetch_spec,
                logger=logger,
                operation_name=f"{component_label}({data_view_id})",
            )
        else:
            payload = _fetch_component_payload(cja, data_view_id, fetch_spec)

        count = _count_component_items_or_na_from_assessment(payload)
        if isinstance(count, int):
            return count
        if logger:
            logger.debug("Could not fetch %s count for %s: non-countable payload", component_label, data_view_id)
    except RECOVERABLE_OPTIONAL_COMPONENT_COUNT_EXCEPTIONS as e:  # Intentional best-effort boundary
        if logger:
            logger.debug("Could not fetch %s count for %s: %s", component_label, data_view_id, e, exc_info=True)
    return fallback_value


def _count_component_items_for_fetch_spec_with_retry(
    cja: Any,
    data_view_id: str,
    fetch_spec: _ComponentFetchSpec,
    *,
    logger: logging.Logger,
) -> int:
    """Return component count via retry-aware fetches, degrading non-fatal issues to zero."""
    count = _count_component_items_for_fetch_spec_best_effort(
        cja,
        data_view_id,
        fetch_spec,
        fallback_value=0,
        use_retry=True,
        logger=logger,
    )
    return count if isinstance(count, int) else 0


def _build_component_list_fetcher(
    *,
    data_view_id: str,
    data_view_name: str | None,
    output_format: str,
    filter_pattern: str | None,
    exclude_pattern: str | None,
    limit: int | None,
    sort_expression: str | None,
    component_label: str,
    table_item_label: str,
    component_json_key: str,
    empty_csv_header: str,
    fetch_spec: _ComponentFetchSpec,
    display_row_builder: Callable[[dict[str, Any]], dict[str, Any]],
    searchable_fields: list[str],
    csv_columns: list[str],
    table_columns: list[str],
    table_labels: list[str],
    table_row_transform: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
) -> Callable:
    """Return a shared fetch-and-format callback for list-* inspection commands."""

    def _inner(cja: Any, is_machine_readable: bool) -> str | None:
        # Local imports to avoid circular dependency: generator -> discovery -> generator
        from cja_auto_sdr.generator import _format_as_csv, _format_as_table

        dv_name = _resolve_dataview_name(cja, data_view_id, preferred_name=data_view_name)

        raw_components = _normalize_component_records_or_raise(
            _fetch_component_payload(cja, data_view_id, fetch_spec),
            component_label=component_label,
            data_view_id=data_view_id,
        )

        if not raw_components:
            if is_machine_readable:
                if output_format == "json":
                    return _format_discovery_json(
                        {
                            "dataViewId": data_view_id,
                            "dataViewName": dv_name,
                            component_json_key: [],
                            "count": 0,
                        }
                    )
                return f"{empty_csv_header}\n"
            return f"\nNo {component_label} found for data view '{data_view_id}'.\n"

        display_data = [display_row_builder(item) for item in raw_components if isinstance(item, dict)]
        display_data = _apply_discovery_filters_and_sort(
            display_data,
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
            sort_expression=sort_expression,
            searchable_fields=searchable_fields,
            default_sort_field="name",
        )

        if output_format == "json":
            return _format_discovery_json(
                {
                    "dataViewId": data_view_id,
                    "dataViewName": dv_name,
                    component_json_key: display_data,
                    "count": len(display_data),
                }
            )

        tabular_data = table_row_transform(display_data) if table_row_transform else display_data
        if output_format == "csv":
            return _format_as_csv(csv_columns, tabular_data)
        return _format_as_table(
            f"Found {len(tabular_data)} {table_item_label}(s) in data view '{dv_name}':",
            tabular_data,
            columns=table_columns,
            col_labels=table_labels,
        )

    return _inner


def _normalize_component_text_fields(item: dict[str, Any], *, defaults: dict[str, str]) -> dict[str, str]:
    """Normalize a component row's text fields with per-field defaults."""
    return {
        field_name: _normalize_optional_text(item.get(field_name), default=default_value)
        for field_name, default_value in defaults.items()
    }


def _normalize_optional_component_int(value: Any, *, default: int = 0) -> int:
    """Normalize optional integer-ish component values for strict JSON output."""
    if _is_missing_discovery_value(value, treat_blank_string=True, treat_null_like_strings=True):
        return default
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if value.is_integer():
            return int(value)
        return default
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return default
        try:
            return int(stripped)
        except ValueError:
            return default
    return default


def _approved_display(value: Any) -> str:
    """Convert an approved flag to a display string."""
    if value is None:
        return "N/A"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    return str(value)


def _tags_display(tags: Any) -> str:
    """Render already-normalized tag lists for table/csv output."""
    if not isinstance(tags, list):
        return ""
    return ", ".join(tag for tag in tags if isinstance(tag, str))


def _format_governance_rows_for_tabular(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert governance fields into table/csv-friendly strings."""
    return [
        {
            **row,
            "approved": _approved_display(row.get("approved")),
            "tags": _tags_display(row.get("tags")),
        }
        for row in rows
    ]


def _build_metric_display_row(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize one metrics-list row for output."""
    return {
        **_normalize_component_text_fields(
            item,
            defaults={
                "id": "N/A",
                "name": "N/A",
                "type": "N/A",
                "description": "",
            },
        ),
        "owner": _extract_owner_name_from_record(item),
        "precision": _normalize_optional_component_int(item.get("precision"), default=0),
    }


def _build_dimension_display_row(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize one dimensions-list row for output."""
    return {
        **_normalize_component_text_fields(
            item,
            defaults={
                "id": "N/A",
                "name": "N/A",
                "type": "N/A",
                "description": "",
            },
        ),
        "owner": _extract_owner_name_from_record(item),
    }


def _build_segment_display_row(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize one segments-list row for output."""
    tags = _extract_tags_normalized(item.get("tags"))
    approved_raw = item.get("approved")
    return {
        **_normalize_component_text_fields(
            item,
            defaults={
                "id": "N/A",
                "name": "N/A",
                "description": "",
            },
        ),
        "owner": _extract_owner_name_from_record(item),
        "approved": approved_raw if isinstance(approved_raw, bool) else None,
        "tags": tags,
        "created": _extract_timestamp_from_record(item, "created"),
        "modified": _extract_timestamp_from_record(item, "modified"),
    }


def _build_calculated_metric_display_row(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize one calculated-metrics row for output."""
    tags = _extract_tags_normalized(item.get("tags"))
    approved_raw = item.get("approved")
    return {
        **_normalize_component_text_fields(
            item,
            defaults={
                "id": "N/A",
                "name": "N/A",
                "description": "",
                "type": "",
                "polarity": "",
            },
        ),
        "owner": _extract_owner_name_from_record(item),
        "precision": _normalize_optional_component_int(item.get("precision"), default=0),
        "approved": approved_raw if isinstance(approved_raw, bool) else None,
        "tags": tags,
        "created": _extract_timestamp_from_record(item, "created"),
        "modified": _extract_timestamp_from_record(item, "modified"),
    }


# ---------------------------------------------------------------------------
# Dataset and connection extractors
# ---------------------------------------------------------------------------


_DATASET_METADATA_MISSING = object()
_DATASET_DISCOVERY_BASE_EXPANSION = "name,ownerFullName,dataSets"
_DATASET_DISCOVERY_CONNECTION_EXPANSION = (
    f"{_DATASET_DISCOVERY_BASE_EXPANSION},dataSetLastIngested,backfillsSummaryDataSets"
)
_DATASET_DISCOVERY_SCHEMA_EXPANSION = "dataSets,schemaInfo"


def _normalize_dataset_metadata_text(value: Any) -> str | object | None:
    """Normalize an optional API text field without collapsing null or empty."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return _DATASET_METADATA_MISSING


def _normalize_dataset_metadata_bool(value: Any) -> bool | object | None:
    """Normalize an optional API boolean without coercing truthy values."""
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    return _DATASET_METADATA_MISSING


def _normalize_dataset_metadata_int(value: Any) -> int | object | None:
    """Normalize an optional API integer without accepting booleans or floats."""
    if value is None:
        return None
    if isinstance(value, Integral) and not isinstance(value, bool):
        return int(value)
    return _DATASET_METADATA_MISSING


def _normalize_lookup_parent_fields(value: Any) -> str | list[str | None] | object | None:
    """Accept the documented string form and observed list-shaped parent fields."""
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        if all(item is None or isinstance(item, str) for item in value):
            return list(value)
        return _DATASET_METADATA_MISSING
    return _DATASET_METADATA_MISSING


def _normalized_dataset_metadata_field(
    record: dict[str, Any],
    source_key: str,
    normalizer: Callable[[Any], Any],
) -> Any:
    """Return a normalized allowlisted field or the internal missing sentinel."""
    if source_key not in record:
        return _DATASET_METADATA_MISSING
    return normalizer(record[source_key])


def _normalize_allowlisted_object(
    value: Any,
    fields: tuple[tuple[str, str, Callable[[Any], Any]], ...],
) -> dict[str, Any] | object | None:
    """Normalize a nested Adobe object through an explicit field allowlist."""
    if value is None:
        return None
    if not isinstance(value, dict):
        return _DATASET_METADATA_MISSING

    normalized: dict[str, Any] = {}
    for source_key, output_key, normalizer in fields:
        field_value = _normalized_dataset_metadata_field(value, source_key, normalizer)
        if field_value is not _DATASET_METADATA_MISSING:
            normalized[output_key] = field_value
    if normalized or not value:
        return normalized
    return _DATASET_METADATA_MISSING


_SCHEMA_REF_FIELDS = (
    ("id", "id", _normalize_dataset_metadata_text),
    ("contentType", "contentType", _normalize_dataset_metadata_text),
)
_SCHEMA_FIELDS = (
    ("schemaId", "id", _normalize_dataset_metadata_text),
    ("schemaName", "name", _normalize_dataset_metadata_text),
    (
        "schemaRef",
        "ref",
        lambda value: _normalize_allowlisted_object(value, _SCHEMA_REF_FIELDS),
    ),
)
_BACKFILL_SUMMARY_FIELDS = (
    ("total", "total", _normalize_dataset_metadata_int),
    ("failed", "failed", _normalize_dataset_metadata_int),
    ("inProgress", "inProgress", _normalize_dataset_metadata_int),
    ("completed", "completed", _normalize_dataset_metadata_int),
    ("invalid", "invalid", _normalize_dataset_metadata_bool),
)
_DATA_SOURCE_FIELDS = (
    ("id", "id", _normalize_dataset_metadata_text),
    ("type", "type", _normalize_dataset_metadata_text),
    ("description", "description", _normalize_dataset_metadata_text),
)


def _normalize_schema_info(value: Any) -> dict[str, Any] | object | None:
    """Normalize the allowlisted schemaInfo object."""
    return _normalize_allowlisted_object(value, _SCHEMA_FIELDS)


def _normalize_backfill_summary(value: Any) -> dict[str, Any] | object | None:
    """Normalize the allowlisted backfillSummary object."""
    return _normalize_allowlisted_object(value, _BACKFILL_SUMMARY_FIELDS)


def _normalize_data_source_type(value: Any) -> dict[str, Any] | object | None:
    """Normalize the allowlisted dataSourceType object."""
    return _normalize_allowlisted_object(value, _DATA_SOURCE_FIELDS)


_IDENTITY_FIELDS = (
    ("timestampId", "timestampId", _normalize_dataset_metadata_text),
    ("visitorId", "visitorId", _normalize_dataset_metadata_text),
    ("identityNamespace", "namespace", _normalize_dataset_metadata_text),
    ("usePrimaryIdNamespace", "usePrimaryIdNamespace", _normalize_dataset_metadata_bool),
    ("identityMap", "identityMap", _normalize_dataset_metadata_bool),
    ("identityNamespaceCol", "namespaceColumn", _normalize_dataset_metadata_text),
)
_LOOKUP_FIELDS = (
    ("lookupKeyField", "keyField", _normalize_dataset_metadata_text),
    ("lookupParentFields", "parentFields", _normalize_lookup_parent_fields),
    ("lookupParentDataSetId", "parentDatasetId", _normalize_dataset_metadata_text),
    ("lookupParentDataSetType", "parentDatasetType", _normalize_dataset_metadata_text),
)
_INGESTION_FIELDS = (
    ("streaming", "streaming", _normalize_dataset_metadata_bool),
    ("backfillSummary", "backfillSummary", _normalize_backfill_summary),
    ("lastIngestedTime", "lastIngestedTime", _normalize_dataset_metadata_text),
    ("streamingEnabledAt", "streamingEnabledAt", _normalize_dataset_metadata_text),
)


def _build_dataset_metadata_group(
    dataset: dict[str, Any],
    fields: tuple[tuple[str, str, Callable[[Any], Any]], ...],
) -> dict[str, Any]:
    """Build one metadata group, omitting absent and malformed source fields."""
    group: dict[str, Any] = {}
    for source_key, output_key, normalizer in fields:
        field_value = _normalized_dataset_metadata_field(dataset, source_key, normalizer)
        if field_value is not _DATASET_METADATA_MISSING:
            group[output_key] = field_value
    return group


def _extract_dataset_connection_metadata(dataset: dict[str, Any]) -> dict[str, Any]:
    """Extract allowlisted connection-scoped dataset metadata for JSON discovery."""
    metadata: dict[str, Any] = {}

    role = _normalized_dataset_metadata_field(dataset, "type", _normalize_dataset_metadata_text)
    if role is not _DATASET_METADATA_MISSING:
        metadata["role"] = role

    schema = _normalized_dataset_metadata_field(
        dataset,
        "schemaInfo",
        _normalize_schema_info,
    )
    if schema is not _DATASET_METADATA_MISSING:
        metadata["schema"] = schema

    identity = _build_dataset_metadata_group(dataset, _IDENTITY_FIELDS)
    if identity:
        metadata["identity"] = identity

    lookup = _build_dataset_metadata_group(dataset, _LOOKUP_FIELDS)
    if lookup:
        metadata["lookup"] = lookup

    ingestion = _build_dataset_metadata_group(dataset, _INGESTION_FIELDS)
    if ingestion:
        metadata["ingestion"] = ingestion

    data_source = _normalized_dataset_metadata_field(
        dataset,
        "dataSourceType",
        _normalize_data_source_type,
    )
    if data_source is not _DATASET_METADATA_MISSING:
        metadata["dataSource"] = data_source

    return metadata


def _extract_dataset_info(dataset: Any, *, include_connection_metadata: bool = False) -> dict:
    """
    Resilient parser for dataset objects from connection API responses.

    The dataSets field in connection responses may use varying field names.
    This helper tries common field names and falls back gracefully.

    Args:
        dataset: A dataset object (dict or other) from the dataSets array

    Returns:
        Dict with 'id' and 'name' keys (values may be 'N/A' if not found),
        plus optional normalized connection metadata when requested.
    """
    if not isinstance(dataset, dict):
        # Preserve previous fallback semantics for scalar falsey values while
        # avoiding ambiguous truthiness checks on pandas missing scalars.
        if _is_missing_discovery_value(dataset, treat_blank_string=True, treat_null_like_strings=True):
            return {"id": "N/A", "name": "N/A"}
        if isinstance(dataset, (bool, int, float)) and not dataset:
            return {"id": "N/A", "name": "N/A"}
        return {"id": _normalize_display_text(dataset, default="N/A"), "name": "N/A"}

    # Try common ID field names (prefer canonical/camelCase, keep snake_case for compatibility)
    ds_id = _pick_first_present_text(
        (
            dataset.get("id"),
            dataset.get("datasetId"),
            dataset.get("dataSetId"),
            dataset.get("dataset_id"),
        ),
        default="N/A",
        treat_null_like_strings=True,
    )

    # Try common name field names
    ds_name = _pick_first_present_text(
        (
            dataset.get("name"),
            dataset.get("datasetName"),
            dataset.get("dataSetName"),
            dataset.get("dataset_name"),
            dataset.get("title"),
        ),
        default="N/A",
        treat_null_like_strings=True,
    )

    result: dict[str, Any] = {"id": ds_id, "name": ds_name}
    if include_connection_metadata:
        connection_metadata = _extract_dataset_connection_metadata(dataset)
        if connection_metadata:
            result["connectionMetadata"] = connection_metadata
    return result


def _dataset_needs_schema_hydration(dataset: Any) -> bool:
    """Return whether a dataset can gain valid schemaInfo from a detail response."""
    if not isinstance(dataset, dict) or _extract_dataset_info(dataset)["id"] == "N/A":
        return False
    if "schemaInfo" not in dataset:
        return True
    return _normalize_schema_info(dataset["schemaInfo"]) is _DATASET_METADATA_MISSING


def _merge_dataset_schema_info(
    raw_datasets: list[Any],
    connection_detail: Any,
    *,
    expected_connection_id: str,
) -> list[Any]:
    """Merge schemaInfo from a by-ID Connection response without replacing base fields."""
    if not isinstance(connection_detail, dict):
        return raw_datasets
    reported_connection_id = connection_detail.get("id", connection_detail.get("idWithoutPrefix"))
    if isinstance(reported_connection_id, str) and reported_connection_id.removeprefix(
        "dg_"
    ) != expected_connection_id.removeprefix("dg_"):
        return raw_datasets
    detail_datasets = connection_detail.get("dataSets", connection_detail.get("datasets", []))
    if not isinstance(detail_datasets, list):
        return raw_datasets

    schema_by_dataset_id: dict[str, Any] = {}
    for detail_dataset in detail_datasets:
        if not isinstance(detail_dataset, dict) or "schemaInfo" not in detail_dataset:
            continue
        schema_info = detail_dataset["schemaInfo"]
        if _normalize_schema_info(schema_info) is _DATASET_METADATA_MISSING:
            continue
        dataset_id = _extract_dataset_info(detail_dataset)["id"]
        if dataset_id != "N/A" and dataset_id not in schema_by_dataset_id:
            schema_by_dataset_id[dataset_id] = schema_info

    if not schema_by_dataset_id:
        return raw_datasets

    merged_datasets: list[Any] = []
    changed = False
    for raw_dataset in raw_datasets:
        if not _dataset_needs_schema_hydration(raw_dataset):
            merged_datasets.append(raw_dataset)
            continue
        dataset_id = _extract_dataset_info(raw_dataset)["id"]
        if dataset_id not in schema_by_dataset_id:
            merged_datasets.append(raw_dataset)
            continue
        merged_datasets.append({**raw_dataset, "schemaInfo": schema_by_dataset_id[dataset_id]})
        changed = True
    return merged_datasets if changed else raw_datasets


def _extract_connections_list(raw_connections: Any) -> list:
    """Extract the connection list from a raw getConnections API response."""
    if isinstance(raw_connections, dict):
        connections = raw_connections.get("content", raw_connections.get("result", []))
        if not isinstance(connections, list):
            # content/result was an unexpected type (e.g. a string); wrap the
            # whole dict so downstream isinstance(conn, dict) checks can decide
            # whether to process or skip it.
            return [raw_connections]
        return connections
    if isinstance(raw_connections, list):
        return raw_connections
    return []


# ---------------------------------------------------------------------------
# Discovery fetchers
# ---------------------------------------------------------------------------


def _fetch_dataviews(
    output_format: str,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> Callable:
    """Return a fetch_and_format callback for list_dataviews."""

    def _inner(cja: Any, is_machine_readable: bool) -> str | None:
        # Local imports to avoid circular dependency: generator -> discovery -> generator
        from cja_auto_sdr.generator import _format_as_csv, _format_as_table

        available_dvs = cja.getDataViews()
        normalized_dvs = (
            []
            if available_dvs is None
            else _normalize_dataview_listing_payload_or_raise(
                available_dvs,
                operation="getDataViews (list_dataviews)",
            )
        )

        if not normalized_dvs:
            if is_machine_readable:
                if output_format == "json":
                    return json.dumps({"dataViews": [], "count": 0}, indent=2)
                return "id,name,owner\n"
            return "\nNo data views found or no access to any data views.\n"

        display_data = []
        for dv in normalized_dvs:
            if isinstance(dv, dict):
                dv_id = _normalize_optional_text(dv.get("id"), default="N/A")
                dv_name = _normalize_optional_text(dv.get("name"), default="N/A")
                owner_name = _extract_owner_name(dv.get("owner"))
                display_data.append({"id": dv_id, "name": dv_name, "owner": owner_name})

        display_data = _apply_discovery_filters_and_sort(
            display_data,
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
            sort_expression=sort_expression,
            searchable_fields=["id", "name", "owner"],
            default_sort_field="name",
        )

        if output_format == "json":
            return _format_discovery_json({"dataViews": display_data, "count": len(display_data)})
        if output_format == "csv":
            return _format_as_csv(["id", "name", "owner"], display_data)
        table = _format_as_table(
            f"Found {len(display_data)} accessible data view(s):",
            display_data,
            columns=["id", "name", "owner"],
            col_labels=["ID", "Name", "Owner"],
        )
        # Derive total width from the first separator line in the rendered table
        table_lines = table.split("\n")
        total_width = max(
            (len(line) for line in table_lines if line and line[0] in ("=", "-", "─")),
            default=60,
        )
        footer_lines = [
            "=" * total_width,
            "Usage:",
            "  cja_auto_sdr <DATA_VIEW_ID>       # Use ID directly",
            '  cja_auto_sdr "<DATA_VIEW_NAME>"   # Use exact name (quotes recommended)',
            "",
            "Note: If multiple data views share the same name, all will be processed.",
            "=" * total_width,
        ]
        return table + "\n".join(footer_lines)

    return _inner


def _fetch_describe_dataview(
    data_view_id: str,
    output_format: str,
) -> Callable:
    """Return a fetch_and_format callback for describe_dataview."""

    def _inner(cja: Any, _is_machine_readable: bool) -> str | None:
        # Local imports to avoid circular dependency: generator -> discovery -> generator
        from cja_auto_sdr.generator import _format_as_csv

        raw_dv = _require_accessible_dataview(cja, data_view_id)

        dv_metadata = _normalize_describe_dataview_metadata(raw_dv, default_id=data_view_id)
        dv_id = dv_metadata["id"]
        dv_name = dv_metadata["name"]
        owner_name = dv_metadata["owner"]
        description = dv_metadata["description"]
        connection_id = dv_metadata["connection_id"]
        created = dv_metadata["created"]
        modified = dv_metadata["modified"]

        n_metrics = _count_component_items_for_fetch_spec(
            cja,
            data_view_id,
            _METRICS_COMPONENT_FETCH_SPEC,
        )
        n_dimensions = _count_component_items_for_fetch_spec(
            cja,
            data_view_id,
            _DIMENSIONS_COMPONENT_FETCH_SPEC,
        )
        n_segments = _count_component_items_for_fetch_spec(
            cja,
            data_view_id,
            _SEGMENTS_COMPONENT_FETCH_SPEC,
        )
        n_calc_metrics = _count_component_items_for_fetch_spec(
            cja,
            data_view_id,
            _CALCULATED_METRICS_COMPONENT_FETCH_SPEC,
        )

        # Compute total only when all counts are numeric
        counts = [n_metrics, n_dimensions, n_segments, n_calc_metrics]
        numeric_counts = [c for c in counts if isinstance(c, int)]
        total = sum(numeric_counts) if len(numeric_counts) == len(counts) else "N/A"

        if output_format == "json":
            payload = {
                "dataView": {
                    "id": dv_id,
                    "name": dv_name,
                    "owner": owner_name,
                    "description": description,
                    "connectionId": connection_id,
                    "created": created,
                    "modified": modified,
                    "components": {
                        "dimensions": n_dimensions,
                        "metrics": n_metrics,
                        "calculatedMetrics": n_calc_metrics,
                        "segments": n_segments,
                        "total": total,
                    },
                }
            }
            return _format_discovery_json(payload)

        if output_format == "csv":
            columns = [
                "id",
                "name",
                "owner",
                "description",
                "connection_id",
                "created",
                "modified",
                "dimensions",
                "metrics",
                "calculated_metrics",
                "segments",
                "total",
            ]
            row = {
                "id": dv_id,
                "name": dv_name,
                "owner": owner_name,
                "description": description,
                "connection_id": connection_id,
                "created": created,
                "modified": modified,
                "dimensions": n_dimensions,
                "metrics": n_metrics,
                "calculated_metrics": n_calc_metrics,
                "segments": n_segments,
                "total": total,
            }
            return _format_as_csv(columns, [row])

        # Table output
        term_width = shutil.get_terminal_size().columns
        rule_width = term_width
        lines: list[str] = []
        lines.append("")
        lines.append(f"Data View: {dv_name}")
        lines.append("=" * rule_width)
        lines.append(f"  ID:            {dv_id}")
        lines.append(f"  Owner:         {owner_name}")
        desc_text = description or "(none)"
        desc_prefix = "  Description:   "
        desc_avail = term_width - len(desc_prefix)
        if desc_avail > 20 and len(desc_text) > desc_avail:
            wrapped = textwrap.wrap(desc_text, width=desc_avail)
            lines.append(desc_prefix + wrapped[0])
            indent = " " * len(desc_prefix)
            lines.extend(indent + cont for cont in wrapped[1:])
        else:
            lines.append(f"{desc_prefix}{desc_text}")
        lines.append(f"  Connection:    {connection_id}")
        lines.append(f"  Created:       {created}")
        lines.append(f"  Modified:      {modified}")
        lines.append("")
        lines.append("  Components:")
        lines.append(f"    Dimensions:          {n_dimensions}")
        lines.append(f"    Metrics:             {n_metrics}")
        lines.append(f"    Calculated Metrics:  {n_calc_metrics}")
        lines.append(f"    Segments:            {n_segments}")
        _count_vals = [v for v in (n_dimensions, n_metrics, n_calc_metrics, n_segments, total) if isinstance(v, int)]
        _max_count = max(_count_vals) if _count_vals else 0
        _separator_width = len("    Calculated Metrics:  ") + max(len(str(_max_count)), len("N/A"))
        lines.append(f"    {'─' * (_separator_width - 4)}")
        lines.append(f"    Total:               {total}")
        lines.append("=" * rule_width)
        lines.append("")
        return "\n".join(lines)

    return _inner


def _fetch_metrics_list(
    data_view_id: str,
    output_format: str,
    data_view_name: str | None = None,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> Callable:
    """Return a fetch_and_format callback for list_metrics."""
    return _build_component_list_fetcher(
        data_view_id=data_view_id,
        data_view_name=data_view_name,
        output_format=output_format,
        filter_pattern=filter_pattern,
        exclude_pattern=exclude_pattern,
        limit=limit,
        sort_expression=sort_expression,
        component_label="metrics",
        table_item_label="metric",
        component_json_key="metrics",
        empty_csv_header="id,name,type,description",
        fetch_spec=_METRICS_COMPONENT_FETCH_SPEC,
        display_row_builder=_build_metric_display_row,
        searchable_fields=["id", "name", "type", "description"],
        csv_columns=["id", "name", "type", "description"],
        table_columns=["id", "name", "type", "description"],
        table_labels=["ID", "Name", "Type", "Description"],
    )


def _fetch_dimensions_list(
    data_view_id: str,
    output_format: str,
    data_view_name: str | None = None,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> Callable:
    """Return a fetch_and_format callback for list_dimensions."""
    return _build_component_list_fetcher(
        data_view_id=data_view_id,
        data_view_name=data_view_name,
        output_format=output_format,
        filter_pattern=filter_pattern,
        exclude_pattern=exclude_pattern,
        limit=limit,
        sort_expression=sort_expression,
        component_label="dimensions",
        table_item_label="dimension",
        component_json_key="dimensions",
        empty_csv_header="id,name,type,description",
        fetch_spec=_DIMENSIONS_COMPONENT_FETCH_SPEC,
        display_row_builder=_build_dimension_display_row,
        searchable_fields=["id", "name", "type", "description"],
        csv_columns=["id", "name", "type", "description"],
        table_columns=["id", "name", "type", "description"],
        table_labels=["ID", "Name", "Type", "Description"],
    )


def _fetch_segments_list(
    data_view_id: str,
    output_format: str,
    data_view_name: str | None = None,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> Callable:
    """Return a fetch_and_format callback for list_segments."""
    return _build_component_list_fetcher(
        data_view_id=data_view_id,
        data_view_name=data_view_name,
        output_format=output_format,
        filter_pattern=filter_pattern,
        exclude_pattern=exclude_pattern,
        limit=limit,
        sort_expression=sort_expression,
        component_label="segments",
        table_item_label="segment",
        component_json_key="segments",
        empty_csv_header="id,name,owner,approved,description,tags,created,modified",
        fetch_spec=_SEGMENTS_COMPONENT_FETCH_SPEC,
        display_row_builder=_build_segment_display_row,
        searchable_fields=["id", "name", "owner", "description", "tags"],
        csv_columns=["id", "name", "owner", "approved", "description", "tags", "created", "modified"],
        table_columns=["id", "name", "owner", "approved", "description"],
        table_labels=["ID", "Name", "Owner", "Approved", "Description"],
        table_row_transform=_format_governance_rows_for_tabular,
    )


def _fetch_calculated_metrics_list(
    data_view_id: str,
    output_format: str,
    data_view_name: str | None = None,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> Callable:
    """Return a fetch_and_format callback for list_calculated_metrics."""
    return _build_component_list_fetcher(
        data_view_id=data_view_id,
        data_view_name=data_view_name,
        output_format=output_format,
        filter_pattern=filter_pattern,
        exclude_pattern=exclude_pattern,
        limit=limit,
        sort_expression=sort_expression,
        component_label="calculated metrics",
        table_item_label="calculated metric",
        component_json_key="calculatedMetrics",
        empty_csv_header="id,name,owner,type,polarity,precision,approved,tags,created,modified,description",
        fetch_spec=_CALCULATED_METRICS_COMPONENT_FETCH_SPEC,
        display_row_builder=_build_calculated_metric_display_row,
        searchable_fields=["id", "name", "owner", "type", "polarity", "description"],
        csv_columns=[
            "id",
            "name",
            "owner",
            "type",
            "polarity",
            "precision",
            "approved",
            "tags",
            "created",
            "modified",
            "description",
        ],
        table_columns=["id", "name", "owner", "type", "polarity", "approved", "description"],
        table_labels=["ID", "Name", "Owner", "Type", "Polarity", "Approved", "Description"],
        table_row_transform=_format_governance_rows_for_tabular,
    )


def _fetch_connections(
    output_format: str,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> Callable:
    """Return a fetch_and_format callback for list_connections."""

    def _inner(cja: Any, is_machine_readable: bool) -> str | None:
        # Local imports to avoid circular dependency: generator -> discovery -> generator
        from cja_auto_sdr.generator import _format_as_csv

        raw_connections = cja.getConnections(output="raw", expansion="name,ownerFullName,dataSets")
        connections = _extract_connections_list(raw_connections)

        if not connections:
            # Check whether data views reference connections we can't see
            # (the GET /connections API requires product-admin privileges).
            available_dvs = cja.getDataViews()
            available_dvs = (
                []
                if available_dvs is None
                else _normalize_dataview_listing_payload_or_raise(
                    available_dvs,
                    operation="getDataViews (list_connections fallback)",
                )
            )

            conn_ids_from_dvs: dict[str, int] = {}  # conn_id -> count of data views
            for dv in available_dvs or []:
                if not isinstance(dv, dict):
                    continue
                pid = dv.get("parentDataGroupId")
                if not _is_missing_discovery_value(pid, treat_blank_string=True, treat_null_like_strings=True):
                    conn_ids_from_dvs[pid] = conn_ids_from_dvs.get(pid, 0) + 1

            if conn_ids_from_dvs:
                # Permissions issue — derive connection IDs from data views
                _PERM_WARNING = (
                    "Note: The GET /connections API requires product-admin privileges.\n"
                    "Connection details are unavailable. Showing connection IDs derived\n"
                    "from data views instead."
                )
                derived = [
                    {"id": cid, "name": None, "owner": None, "datasets": [], "dataview_count": cnt}
                    for cid, cnt in sorted(conn_ids_from_dvs.items())
                ]
                derived = _apply_discovery_filters_and_sort(
                    derived,
                    filter_pattern=filter_pattern,
                    exclude_pattern=exclude_pattern,
                    limit=limit,
                    sort_expression=sort_expression,
                    searchable_fields=["id", "name", "owner", "dataview_count"],
                    default_sort_field="id",
                )

                if output_format == "json":
                    return _format_discovery_json(
                        {
                            "connections": derived,
                            "count": len(derived),
                            "warning": _PERM_WARNING.replace("\n", " "),
                        },
                    )
                if output_format == "csv":
                    flat = [
                        {
                            "connection_id": d["id"],
                            "connection_name": "",
                            "owner": "",
                            "dataset_id": "",
                            "dataset_name": "",
                            "dataview_count": d["dataview_count"],
                        }
                        for d in derived
                    ]
                    return _format_as_csv(
                        ["connection_id", "connection_name", "owner", "dataset_id", "dataset_name", "dataview_count"],
                        flat,
                    )
                lines: list[str] = []
                lines.append("")
                lines.append(_PERM_WARNING)
                lines.append("")
                lines.append(f"Found {len(derived)} connection(s) referenced by data views:")
                lines.append("")
                lines.extend(f"  {d['id']}  ({d['dataview_count']} data view(s))" for d in derived)
                lines.append("")
                return "\n".join(lines)

            # Genuinely no connections
            if is_machine_readable:
                if output_format == "json":
                    return _format_discovery_json({"connections": [], "count": 0})
                return "connection_id,connection_name,owner,dataset_id,dataset_name\n"
            return "\nNo connections found or no access to any connections.\n"

        display_data = []
        for conn in connections:
            if not isinstance(conn, dict):
                continue
            conn_id = _normalize_optional_text(conn.get("id"), default="N/A")
            conn_name = _normalize_optional_text(conn.get("name"), default="N/A")
            owner_full_name = _normalize_optional_text(conn.get("ownerFullName"), default="")
            owner_name = owner_full_name or _extract_owner_name(conn.get("owner"))

            raw_datasets = conn.get("dataSets", conn.get("datasets", []))
            if not isinstance(raw_datasets, list):
                raw_datasets = []
            datasets = [_extract_dataset_info(ds) for ds in raw_datasets]

            display_data.append(
                {
                    "id": conn_id,
                    "name": conn_name,
                    "owner": owner_name,
                    "datasets": datasets,
                },
            )

        display_data = _apply_discovery_filters_and_sort(
            display_data,
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
            sort_expression=sort_expression,
            searchable_fields=["id", "name", "owner", "datasets"],
            default_sort_field="name",
        )

        if output_format == "json":
            return _format_discovery_json({"connections": display_data, "count": len(display_data)})
        if output_format == "csv":
            # Flatten nested datasets: one CSV row per dataset
            flat_rows: list[dict] = []
            for conn in display_data:
                if conn["datasets"]:
                    flat_rows.extend(
                        {
                            "connection_id": conn["id"],
                            "connection_name": conn["name"],
                            "owner": conn["owner"],
                            "dataset_id": ds["id"],
                            "dataset_name": ds["name"],
                        }
                        for ds in conn["datasets"]
                    )
                else:
                    flat_rows.append(
                        {
                            "connection_id": conn["id"],
                            "connection_name": conn["name"],
                            "owner": conn["owner"],
                            "dataset_id": "",
                            "dataset_name": "",
                        },
                    )
            return _format_as_csv(
                ["connection_id", "connection_name", "owner", "dataset_id", "dataset_name"],
                flat_rows,
            )
        lines: list[str] = []
        lines.append("")
        lines.append(f"Found {len(display_data)} accessible connection(s):")
        lines.append("")
        for conn in display_data:
            lines.append(f"Connection: {conn['name']} ({conn['id']})")
            lines.append(f"Owner: {conn['owner']}")
            if conn["datasets"]:
                lines.append(f"Datasets ({len(conn['datasets'])}):")
                for ds in conn["datasets"]:
                    lines.append(f"  {ds['id']}  {ds['name']}")
            else:
                lines.append("Datasets: (none)")
            lines.append("")
        return "\n".join(lines)

    return _inner


def _fetch_datasets(
    output_format: str,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> Callable:
    """Return a fetch_and_format callback for list_datasets."""

    def _inner(cja: Any, is_machine_readable: bool) -> str | None:
        # Local imports to avoid circular dependency: generator -> discovery -> generator
        from cja_auto_sdr.generator import _format_as_csv

        # Step 1: Fetch all connections and build lookup map
        include_connection_metadata = output_format == "json"
        connection_expansion = (
            _DATASET_DISCOVERY_CONNECTION_EXPANSION
            if include_connection_metadata
            else _DATASET_DISCOVERY_BASE_EXPANSION
        )
        raw_connections = cja.getConnections(output="raw", expansion=connection_expansion)
        conn_map: dict = {}  # connection_id -> {name, datasets}
        raw_datasets_by_connection: dict[str, list[Any]] = {}
        for conn in _extract_connections_list(raw_connections):
            if not isinstance(conn, dict):
                continue
            conn_id = _normalize_optional_text(conn.get("id"), default="")
            conn_name = _normalize_optional_text(conn.get("name"), default="N/A")
            raw_datasets = conn.get("dataSets", conn.get("datasets", []))
            if not isinstance(raw_datasets, list):
                raw_datasets = []
            datasets = [
                _extract_dataset_info(ds, include_connection_metadata=include_connection_metadata)
                for ds in raw_datasets
            ]
            conn_info = {
                "name": conn_name,
                "datasets": [{"id": ds["id"], "name": ds["name"]} for ds in datasets],
            }
            if include_connection_metadata:
                conn_info["json_datasets"] = datasets
                raw_datasets_by_connection[conn_id] = raw_datasets
            conn_map[conn_id] = conn_info

        # Step 2: Fetch all data views
        available_dvs = cja.getDataViews()
        available_dvs = (
            []
            if available_dvs is None
            else _normalize_dataview_listing_payload_or_raise(
                available_dvs,
                operation="getDataViews (list_datasets)",
            )
        )

        if not available_dvs:
            if is_machine_readable:
                if output_format == "json":
                    return _format_discovery_json({"dataViews": [], "count": 0})
                return "dataview_id,dataview_name,connection_id,connection_name,dataset_id,dataset_name\n"
            return "\nNo data views found or no access to any data views.\n"

        # Detect permissions gap: conn_map is empty but data views have connections
        _no_conn_details = False
        if not conn_map:
            for dv in available_dvs or []:
                if not isinstance(dv, dict):
                    continue
                pid = dv.get("parentDataGroupId")
                if not _is_missing_discovery_value(pid, treat_blank_string=True, treat_null_like_strings=True):
                    _no_conn_details = True
                    break

        # Step 3: Build output records using parentDataGroupId
        if not is_machine_readable:
            print(f"Processing {len(available_dvs)} data view(s)...")
        display_data = []
        for i, dv in enumerate(available_dvs):
            if not isinstance(dv, dict):
                continue
            dv_id = _normalize_optional_text(dv.get("id"), default="N/A")
            dv_name = _normalize_optional_text(dv.get("name"), default="N/A")

            if not is_machine_readable and sys.stdout.isatty():
                print(f"  [{i + 1}/{len(available_dvs)}] {dv_name}...", end="\r")

            parent_conn_id = dv.get("parentDataGroupId")
            # DataFrame-backed records can carry missing values as NaN/NA.
            # Normalize to None so machine-readable output emits "N/A", not NaN.
            if _is_missing_discovery_value(parent_conn_id, treat_blank_string=True, treat_null_like_strings=True):
                parent_conn_id = None

            conn_info = conn_map.get(parent_conn_id) if parent_conn_id else None
            conn_name = conn_info.get("name", "N/A") if conn_info else None
            datasets = conn_info.get("datasets", []) if conn_info else []

            display_data.append(
                {
                    "id": dv_id,
                    "name": dv_name,
                    "connection": {"id": parent_conn_id or "N/A", "name": conn_name},
                    "datasets": datasets,
                },
            )

        display_data = _apply_discovery_filters_and_sort(
            display_data,
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
            sort_expression=sort_expression,
            searchable_fields=["id", "name", "connection", "datasets"],
            default_sort_field="name",
        )

        # schemaInfo is supported by Adobe only on GET /connections/{id}, not
        # GET /connections. Hydrate only Connections retained in the final JSON
        # rows, treating this optional detail as best effort.
        if include_connection_metadata and conn_map:
            connection_ids_to_hydrate: list[str] = []
            for entry in display_data:
                connection = entry.get("connection")
                if not isinstance(connection, dict):
                    continue
                connection_id = connection.get("id")
                raw_datasets = raw_datasets_by_connection.get(connection_id, [])
                if (
                    isinstance(connection_id, str)
                    and connection_id in conn_map
                    and any(_dataset_needs_schema_hydration(dataset) for dataset in raw_datasets)
                ):
                    connection_ids_to_hydrate.append(connection_id)

            for connection_id in dict.fromkeys(connection_ids_to_hydrate):
                try:
                    connection_detail = cja.getConnection(
                        connectionId=connection_id.removeprefix("dg_"),
                        expansion=_DATASET_DISCOVERY_SCHEMA_EXPANSION,
                    )
                except RECOVERABLE_OPTIONAL_ENRICHMENT_EXCEPTIONS:  # Intentional best-effort boundary
                    continue
                raw_datasets = raw_datasets_by_connection[connection_id]
                merged_datasets = _merge_dataset_schema_info(
                    raw_datasets,
                    connection_detail,
                    expected_connection_id=connection_id,
                )
                if merged_datasets is raw_datasets:
                    continue
                conn_map[connection_id]["json_datasets"] = [
                    _extract_dataset_info(dataset, include_connection_metadata=True) for dataset in merged_datasets
                ]

        if not is_machine_readable and sys.stdout.isatty():
            # Clear progress line with ANSI erase-line escape
            print("\033[2K", end="\r")

        _CONN_PERM_WARNING = (
            "Note: Connection details are unavailable (the GET /connections API\n"
            "requires product-admin privileges). Showing connection IDs only."
        )

        result_data = display_data
        if output_format == "json":
            result_data = [
                {
                    **entry,
                    "datasets": conn_map.get(entry["connection"]["id"], {}).get(
                        "json_datasets",
                        entry["datasets"],
                    ),
                }
                for entry in display_data
            ]

        result_payload: dict = {"dataViews": result_data, "count": len(result_data)}
        if _no_conn_details:
            result_payload["warning"] = _CONN_PERM_WARNING.replace("\n", " ")

        if output_format == "json":
            return _format_discovery_json(result_payload)
        if output_format == "csv":
            # Flatten nested datasets: one CSV row per dataset per data view
            flat_rows: list[dict] = []
            for entry in display_data:
                conn_id = entry["connection"]["id"]
                conn_name_val = entry["connection"]["name"] or ""
                if entry["datasets"]:
                    flat_rows.extend(
                        {
                            "dataview_id": entry["id"],
                            "dataview_name": entry["name"],
                            "connection_id": conn_id,
                            "connection_name": conn_name_val,
                            "dataset_id": ds["id"],
                            "dataset_name": ds["name"],
                        }
                        for ds in entry["datasets"]
                    )
                else:
                    flat_rows.append(
                        {
                            "dataview_id": entry["id"],
                            "dataview_name": entry["name"],
                            "connection_id": conn_id,
                            "connection_name": conn_name_val,
                            "dataset_id": "",
                            "dataset_name": "",
                        },
                    )
            return _format_as_csv(
                ["dataview_id", "dataview_name", "connection_id", "connection_name", "dataset_id", "dataset_name"],
                flat_rows,
            )
        lines: list[str] = []
        lines.append("")
        if _no_conn_details:
            lines.append(_CONN_PERM_WARNING)
            lines.append("")
        if _no_conn_details:
            lines.append(f"Found {len(display_data)} data view(s) with backing connection information:")
        else:
            lines.append(f"Found {len(display_data)} data view(s) with connection and dataset information:")
        lines.append("")
        for entry in display_data:
            lines.append(f"Data View: {entry['name']} ({entry['id']})")
            c_name = entry["connection"]["name"]
            c_id = entry["connection"]["id"]
            if c_name:
                lines.append(f"Connection: {c_name} ({c_id})")
            else:
                lines.append(f"Connection: {c_id}")
            if entry["datasets"]:
                lines.append(f"Datasets ({len(entry['datasets'])}):")
                lines.extend(f"  {ds['id']}  {ds['name']}" for ds in entry["datasets"])
            elif not _no_conn_details:
                lines.append("Datasets: (none)")
            lines.append("")
        return "\n".join(lines)

    return _inner
