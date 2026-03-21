"""Shared discovery implementation — single source of truth for discovery internals.

Extracted from generator.py (v3.4.5) so that cli/commands/list.py and
generator.py both import from here instead of maintaining mirrored copies.
"""

# ruff: noqa: T201

from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

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
    filtered_rows = list(rows)
    fields = searchable_fields or list(rows[0].keys()) if rows else []

    _validate_discovery_query_inputs(filter_pattern=filter_pattern, exclude_pattern=exclude_pattern, limit=limit)
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
