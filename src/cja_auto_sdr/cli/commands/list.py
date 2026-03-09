"""List/discovery CLI command entrypoints extracted from generator.py."""

# ruff: noqa: T201

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from cja_auto_sdr import generator as _generator

__all__ = [
    "_run_list_command",
    "describe_dataview",
    "list_calculated_metrics",
    "list_connections",
    "list_datasets",
    "list_dataviews",
    "list_dimensions",
    "list_metrics",
    "list_segments",
]

json = _generator.json
pd = _generator.pd
shutil = _generator.shutil
textwrap = _generator.textwrap

DiscoveryNotFoundError = _generator.DiscoveryNotFoundError
RECOVERABLE_OPTIONAL_COMPONENT_COUNT_EXCEPTIONS = _generator.RECOVERABLE_OPTIONAL_COMPONENT_COUNT_EXCEPTIONS

_METRICS_COMPONENT_FETCH_SPEC = _generator._METRICS_COMPONENT_FETCH_SPEC
_DIMENSIONS_COMPONENT_FETCH_SPEC = _generator._DIMENSIONS_COMPONENT_FETCH_SPEC
_SEGMENTS_COMPONENT_FETCH_SPEC = _generator._SEGMENTS_COMPONENT_FETCH_SPEC
_CALCULATED_METRICS_COMPONENT_FETCH_SPEC = _generator._CALCULATED_METRICS_COMPONENT_FETCH_SPEC


def _run_list_command(
    banner_text: str,
    command_name: str,
    fetch_and_format: Callable,
    config_file: str = "config.json",
    output_format: str = "table",
    output_file: str | None = None,
    profile: str | None = None,
    validate_inputs: Callable[[], None] | None = None,
) -> bool:
    """Shared boilerplate for list-* discovery commands."""
    is_stdout = output_file in ("-", "stdout")
    is_machine_readable = _generator._is_machine_readable_output(output_format, output_file)

    active_profile = _generator.resolve_active_profile(profile)

    if not is_machine_readable:
        print()
        print("=" * _generator.BANNER_WIDTH)
        print(banner_text)
        print("=" * _generator.BANNER_WIDTH)
        print()
        if active_profile:
            print(f"Using profile: {active_profile}")
        else:
            print(f"Using configuration: {config_file}")
        print()

    try:
        if validate_inputs:
            validate_inputs()

        logger = logging.getLogger(command_name)
        logger.setLevel(logging.WARNING)
        success, source, _ = _generator.configure_cjapy(
            profile=active_profile,
            config_file=config_file,
            logger=logger,
        )
        if not success:
            _generator._emit_discovery_error(
                f"Configuration error: {source}",
                is_machine_readable=is_machine_readable,
                error_type="configuration_error",
                human_to_stderr=False,
            )
            return False
        cja = _generator.cjapy.CJA()

        if not is_machine_readable:
            print("Connecting to CJA API...")

        output_data = fetch_and_format(cja, is_machine_readable)
        if output_data is not None:
            _generator._emit_output(output_data, output_file, is_stdout)

        return True

    except _generator.DiscoveryNotFoundError as e:
        _generator._emit_discovery_error(
            str(e),
            is_machine_readable=is_machine_readable,
            error_type="not_found",
            human_to_stderr=False,
        )
        return False

    except _generator.DiscoveryArgumentError as e:
        _generator._emit_discovery_error(
            str(e),
            is_machine_readable=is_machine_readable,
            error_type="invalid_arguments",
            human_to_stderr=False,
        )
        return False

    except _generator.OutputContractError as e:
        _generator._emit_output_contract_error(
            str(e),
            is_machine_readable=is_machine_readable,
            human_to_stderr=False,
        )
        return False

    except FileNotFoundError:
        _generator._emit_discovery_error(
            f"Configuration file '{config_file}' not found",
            is_machine_readable=is_machine_readable,
            error_type="configuration_error",
            human_to_stderr=False,
        )
        if not is_machine_readable:
            print()
            print("Generate a sample configuration file with:")
            print("  cja_auto_sdr --sample-config")
        return False

    except KeyboardInterrupt, SystemExit:
        if not is_machine_readable:
            print()
            print(_generator.ConsoleColors.warning("Operation cancelled."))
        raise

    except _generator.RECOVERABLE_COMMAND_HANDLER_EXCEPTIONS as e:
        _generator._emit_discovery_error(
            f"Failed to connect to CJA API: {e!s}",
            is_machine_readable=is_machine_readable,
            error_type="connectivity_error",
            human_to_stderr=False,
        )
        return False


def _fetch_dataviews(
    output_format: str,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> Callable:
    """Return a fetch_and_format callback for list_dataviews."""

    def _inner(cja: Any, is_machine_readable: bool) -> str | None:
        available_dvs = cja.getDataViews()

        if available_dvs is None or (hasattr(available_dvs, "__len__") and len(available_dvs) == 0):
            if is_machine_readable:
                if output_format == "json":
                    return json.dumps({"dataViews": [], "count": 0}, indent=2)
                return "id,name,owner\n"
            return "\nNo data views found or no access to any data views.\n"

        if isinstance(available_dvs, pd.DataFrame):
            available_dvs = available_dvs.to_dict("records")

        display_data = []
        for dv in available_dvs:
            if isinstance(dv, dict):
                dv_id = _generator._normalize_optional_text(dv.get("id"), default="N/A")
                dv_name = _generator._normalize_optional_text(dv.get("name"), default="N/A")
                owner_name = _generator._extract_owner_name(dv.get("owner"))
                display_data.append({"id": dv_id, "name": dv_name, "owner": owner_name})

        display_data = _generator._apply_discovery_filters_and_sort(
            display_data,
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
            sort_expression=sort_expression,
            searchable_fields=["id", "name", "owner"],
            default_sort_field="name",
        )

        if output_format == "json":
            return _generator._format_discovery_json({"dataViews": display_data, "count": len(display_data)})
        if output_format == "csv":
            return _generator._format_as_csv(["id", "name", "owner"], display_data)
        table = _generator._format_as_table(
            f"Found {len(display_data)} accessible data view(s):",
            display_data,
            columns=["id", "name", "owner"],
            col_labels=["ID", "Name", "Owner"],
        )
        labels = ["ID", "Name", "Owner"]
        cols = ["id", "name", "owner"]
        widths = [
            max(len(lbl), max((len(str(item.get(col, ""))) for item in display_data), default=0)) + 2
            for col, lbl in zip(cols, labels, strict=True)
        ]
        total_width = sum(widths)
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


def _assess_dataview_lookup(
    raw_payload: Any,
    *,
    data_view_id: str,
    require_expected_id: bool = True,
) -> Any:
    """Assess a getDataView payload with a consistent expected-id policy."""
    expected_data_view_id = data_view_id if require_expected_id else None
    return _generator._assess_dataview_lookup_payload(raw_payload, expected_data_view_id=expected_data_view_id)


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
    except Exception as lookup_error:  # Intentional: wrapped client/transport lookup failures vary
        if _generator._is_inaccessible_dataview_lookup_error(lookup_error):
            raise DiscoveryNotFoundError(f"Data view '{data_view_id}' not found") from lookup_error
        raise


def _require_accessible_dataview(cja: Any, data_view_id: str) -> dict[str, Any]:
    """Fetch a data view and raise DiscoveryNotFoundError when inaccessible/invalid."""
    raw_payload = _fetch_dataview_lookup_payload(cja, data_view_id)
    payload, _, _ = _coerce_valid_dataview_lookup_payload(raw_payload, data_view_id=data_view_id)
    if payload is None:
        raise DiscoveryNotFoundError(f"Data view '{data_view_id}' not found")
    return payload


def _normalize_component_records_or_raise(
    raw_payload: Any,
    *,
    component_label: str,
    data_view_id: str,
) -> list[dict[str, Any]]:
    """Normalize component payloads to dict rows or fail on error-shaped responses."""
    assessment = _generator._assess_component_payload(raw_payload)
    if assessment.kind is _generator._PayloadKind.ERROR:
        raise DiscoveryNotFoundError(f"Failed to retrieve {component_label} for data view '{data_view_id}'")
    if assessment.kind is _generator._PayloadKind.INVALID:
        raise DiscoveryNotFoundError(
            f"Unexpected {component_label} payload type for data view '{data_view_id}'",
        )
    return assessment.rows


def _normalize_describe_dataview_metadata(raw_dv: dict[str, Any], *, default_id: str) -> dict[str, str]:
    """Normalize describe_dataview metadata fields for safe display/serialization."""
    connection_id = _generator._pick_first_present_text(
        (
            raw_dv.get("parentDataGroupId"),
            raw_dv.get("connectionId"),
            raw_dv.get("connection_id"),
        ),
        default="N/A",
        treat_null_like_strings=True,
    )
    created = _generator._extract_timestamp_from_record(raw_dv, "created") or "N/A"
    modified = _generator._extract_timestamp_from_record(raw_dv, "modified") or "N/A"
    return {
        "id": _generator._normalize_optional_text(raw_dv.get("id"), default=default_id),
        "name": _generator._normalize_optional_text(raw_dv.get("name"), default="N/A"),
        "owner": _generator._extract_owner_name_from_record(raw_dv),
        "description": _generator._normalize_optional_text(raw_dv.get("description"), default=""),
        "connection_id": connection_id,
        "created": created,
        "modified": modified,
    }


def _fetch_describe_dataview(data_view_id: str, output_format: str) -> Callable:
    """Return a fetch_and_format callback for describe_dataview."""

    def _inner(cja: Any, _is_machine_readable: bool) -> str | None:
        raw_dv = _require_accessible_dataview(cja, data_view_id)

        dv_metadata = _normalize_describe_dataview_metadata(raw_dv, default_id=data_view_id)
        counts = [
            _generator._count_component_items_for_fetch_spec(cja, data_view_id, _METRICS_COMPONENT_FETCH_SPEC),
            _generator._count_component_items_for_fetch_spec(cja, data_view_id, _DIMENSIONS_COMPONENT_FETCH_SPEC),
            _generator._count_component_items_for_fetch_spec(cja, data_view_id, _SEGMENTS_COMPONENT_FETCH_SPEC),
            _generator._count_component_items_for_fetch_spec(
                cja, data_view_id, _CALCULATED_METRICS_COMPONENT_FETCH_SPEC
            ),
        ]
        n_metrics, n_dimensions, n_segments, n_calc_metrics = counts
        numeric_counts = [count for count in counts if isinstance(count, int)]
        total = sum(numeric_counts) if len(numeric_counts) == len(counts) else "N/A"

        if output_format == "json":
            return _generator._format_discovery_json(
                {
                    "dataView": {
                        "id": dv_metadata["id"],
                        "name": dv_metadata["name"],
                        "owner": dv_metadata["owner"],
                        "description": dv_metadata["description"],
                        "connectionId": dv_metadata["connection_id"],
                        "created": dv_metadata["created"],
                        "modified": dv_metadata["modified"],
                        "components": {
                            "dimensions": n_dimensions,
                            "metrics": n_metrics,
                            "calculatedMetrics": n_calc_metrics,
                            "segments": n_segments,
                            "total": total,
                        },
                    }
                }
            )

        if output_format == "csv":
            row = {
                "id": dv_metadata["id"],
                "name": dv_metadata["name"],
                "owner": dv_metadata["owner"],
                "description": dv_metadata["description"],
                "connection_id": dv_metadata["connection_id"],
                "created": dv_metadata["created"],
                "modified": dv_metadata["modified"],
                "dimensions": n_dimensions,
                "metrics": n_metrics,
                "calculated_metrics": n_calc_metrics,
                "segments": n_segments,
                "total": total,
            }
            return _generator._format_as_csv(
                [
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
                ],
                [row],
            )

        term_width = shutil.get_terminal_size().columns
        desc_text = dv_metadata["description"] or "(none)"
        desc_prefix = "  Description:   "
        desc_avail = term_width - len(desc_prefix)
        lines = [
            "",
            f"Data View: {dv_metadata['name']}",
            "=" * term_width,
            f"  ID:            {dv_metadata['id']}",
            f"  Owner:         {dv_metadata['owner']}",
        ]
        if desc_avail > 20 and len(desc_text) > desc_avail:
            wrapped = textwrap.wrap(desc_text, width=desc_avail)
            lines.append(desc_prefix + wrapped[0])
            lines.extend((" " * len(desc_prefix)) + chunk for chunk in wrapped[1:])
        else:
            lines.append(f"{desc_prefix}{desc_text}")
        lines.extend(
            [
                f"  Connection:    {dv_metadata['connection_id']}",
                f"  Created:       {dv_metadata['created']}",
                f"  Modified:      {dv_metadata['modified']}",
                "",
                "  Components:",
                f"    Dimensions:          {n_dimensions}",
                f"    Metrics:             {n_metrics}",
                f"    Calculated Metrics:  {n_calc_metrics}",
                f"    Segments:            {n_segments}",
                "    ─────────────────────────",
                f"    Total:               {total}",
                "=" * term_width,
                "",
            ]
        )
        return "\n".join(lines)

    return _inner


def _resolve_dataview_name(cja: Any, data_view_id: str, *, preferred_name: str | None = None) -> str:
    """Look up a canonical data view display name with safe fallback behavior."""
    raw_dv = _require_accessible_dataview(cja, data_view_id)
    normalized_name = _generator._normalize_optional_text(raw_dv.get("name"), default="")
    if normalized_name:
        return normalized_name
    normalized_preferred = _generator._normalize_optional_text(preferred_name, default="")
    return normalized_preferred or "Unknown"


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


def _fetch_component_payload(cja: Any, data_view_id: str, fetch_spec: Any) -> Any:
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
    fetch_spec: Any,
    display_row_builder: Callable[[dict[str, Any]], dict[str, Any]],
    searchable_fields: list[str],
    csv_columns: list[str],
    table_columns: list[str],
    table_labels: list[str],
    table_row_transform: Callable[[list[dict[str, Any]]], list[dict[str, Any]]] | None = None,
) -> Callable:
    """Return a shared fetch-and-format callback for list-* inspection commands."""

    def _inner(cja: Any, is_machine_readable: bool) -> str | None:
        dv_name = _resolve_dataview_name(cja, data_view_id, preferred_name=data_view_name)
        raw_components = _normalize_component_records_or_raise(
            _fetch_component_payload(cja, data_view_id, fetch_spec),
            component_label=component_label,
            data_view_id=data_view_id,
        )

        if not raw_components:
            if is_machine_readable:
                if output_format == "json":
                    return _generator._format_discovery_json(
                        {component_json_key: [], "count": 0, "dataViewId": data_view_id}
                    )
                return f"{empty_csv_header}\n"
            return f"\nNo {component_label} found in data view '{dv_name}' ({data_view_id}).\n"

        display_rows = [display_row_builder(item) for item in raw_components if isinstance(item, dict)]
        display_rows = _generator._apply_discovery_filters_and_sort(
            display_rows,
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
            sort_expression=sort_expression,
            searchable_fields=searchable_fields,
            default_sort_field="name",
        )

        if output_format == "json":
            return _generator._format_discovery_json(
                {
                    component_json_key: display_rows,
                    "count": len(display_rows),
                    "dataViewId": data_view_id,
                    "dataViewName": dv_name,
                }
            )
        if output_format == "csv":
            csv_rows = table_row_transform(display_rows) if table_row_transform else display_rows
            return _generator._format_as_csv(csv_columns, csv_rows)

        table_rows = table_row_transform(display_rows) if table_row_transform else display_rows
        return _generator._format_as_table(
            f"Found {len(table_rows)} {table_item_label}(s) in data view '{dv_name}':",
            table_rows,
            columns=table_columns,
            col_labels=table_labels,
        )

    return _inner


def _build_metric_display_row(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize one metrics-list row for output."""
    return {
        **_generator._normalize_component_text_fields(
            item,
            defaults={"id": "N/A", "name": "N/A", "description": "", "type": "N/A"},
        ),
        "owner": _generator._extract_owner_name_from_record(item),
        "precision": _generator._normalize_optional_component_int(item.get("precision"), default=0),
    }


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
        display_row_builder=_generator._build_metric_display_row,
        searchable_fields=["id", "name", "type", "description"],
        csv_columns=["id", "name", "type", "description"],
        table_columns=["id", "name", "type", "description"],
        table_labels=["ID", "Name", "Type", "Description"],
    )


def _build_dimension_display_row(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize one dimensions-list row for output."""
    return {
        **_generator._normalize_component_text_fields(
            item,
            defaults={"id": "N/A", "name": "N/A", "description": "", "type": "N/A"},
        ),
        "owner": _generator._extract_owner_name_from_record(item),
    }


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


def _build_segment_display_row(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize one segments-list row for output."""
    tags = _generator._extract_tags_normalized(item.get("tags"))
    approved_raw = item.get("approved")
    return {
        **_generator._normalize_component_text_fields(
            item,
            defaults={"id": "N/A", "name": "N/A", "description": ""},
        ),
        "owner": _generator._extract_owner_name_from_record(item),
        "approved": approved_raw if isinstance(approved_raw, bool) else None,
        "tags": tags,
        "created": _generator._extract_timestamp_from_record(item, "created"),
        "modified": _generator._extract_timestamp_from_record(item, "modified"),
    }


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


def _build_calculated_metric_display_row(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize one calculated-metrics row for output."""
    tags = _generator._extract_tags_normalized(item.get("tags"))
    approved_raw = item.get("approved")
    return {
        **_generator._normalize_component_text_fields(
            item,
            defaults={"id": "N/A", "name": "N/A", "description": "", "type": "", "polarity": ""},
        ),
        "owner": _generator._extract_owner_name_from_record(item),
        "precision": _generator._normalize_optional_component_int(item.get("precision"), default=0),
        "approved": approved_raw if isinstance(approved_raw, bool) else None,
        "tags": tags,
        "created": _generator._extract_timestamp_from_record(item, "created"),
        "modified": _generator._extract_timestamp_from_record(item, "modified"),
    }


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
        raw_connections = cja.getConnections(output="raw", expansion="name,ownerFullName,dataSets")
        connections = _generator._extract_connections_list(raw_connections)

        if not connections:
            available_dvs = cja.getDataViews()
            if isinstance(available_dvs, pd.DataFrame):
                available_dvs = available_dvs.to_dict("records")

            conn_ids_from_dvs: dict[str, int] = {}
            for dv in available_dvs or []:
                if not isinstance(dv, dict):
                    continue
                pid = dv.get("parentDataGroupId")
                if not _generator._is_missing_discovery_value(
                    pid, treat_blank_string=True, treat_null_like_strings=True
                ):
                    conn_ids_from_dvs[pid] = conn_ids_from_dvs.get(pid, 0) + 1

            if conn_ids_from_dvs:
                warning = (
                    "Note: The GET /connections API requires product-admin privileges.\n"
                    "Connection details are unavailable. Showing connection IDs derived\n"
                    "from data views instead."
                )
                derived = [
                    {"id": conn_id, "name": None, "owner": None, "datasets": [], "dataview_count": count}
                    for conn_id, count in sorted(conn_ids_from_dvs.items())
                ]
                derived = _generator._apply_discovery_filters_and_sort(
                    derived,
                    filter_pattern=filter_pattern,
                    exclude_pattern=exclude_pattern,
                    limit=limit,
                    sort_expression=sort_expression,
                    searchable_fields=["id", "name", "owner", "dataview_count"],
                    default_sort_field="id",
                )
                if output_format == "json":
                    return _generator._format_discovery_json(
                        {"connections": derived, "count": len(derived), "warning": warning.replace("\n", " ")}
                    )
                if output_format == "csv":
                    return _generator._format_as_csv(
                        ["connection_id", "connection_name", "owner", "dataset_id", "dataset_name", "dataview_count"],
                        [
                            {
                                "connection_id": row["id"],
                                "connection_name": "",
                                "owner": "",
                                "dataset_id": "",
                                "dataset_name": "",
                                "dataview_count": row["dataview_count"],
                            }
                            for row in derived
                        ],
                    )
                lines = ["", warning, "", f"Found {len(derived)} connection(s) referenced by data views:", ""]
                lines.extend(f"  {row['id']}  ({row['dataview_count']} data view(s))" for row in derived)
                lines.append("")
                return "\n".join(lines)

            if is_machine_readable:
                if output_format == "json":
                    return _generator._format_discovery_json({"connections": [], "count": 0})
                return "connection_id,connection_name,owner,dataset_id,dataset_name\n"
            return "\nNo connections found or no access to any connections.\n"

        display_data = []
        for conn in connections:
            if not isinstance(conn, dict):
                continue
            raw_datasets = conn.get("dataSets", conn.get("datasets", []))
            if not isinstance(raw_datasets, list):
                raw_datasets = []
            display_data.append(
                {
                    "id": _generator._normalize_optional_text(conn.get("id"), default="N/A"),
                    "name": _generator._normalize_optional_text(conn.get("name"), default="N/A"),
                    "owner": _generator._normalize_optional_text(conn.get("ownerFullName"), default="")
                    or _generator._extract_owner_name(conn.get("owner")),
                    "datasets": [_generator._extract_dataset_info(dataset) for dataset in raw_datasets],
                }
            )

        display_data = _generator._apply_discovery_filters_and_sort(
            display_data,
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
            sort_expression=sort_expression,
            searchable_fields=["id", "name", "owner", "datasets"],
            default_sort_field="name",
        )

        if output_format == "json":
            return _generator._format_discovery_json({"connections": display_data, "count": len(display_data)})
        if output_format == "csv":
            flat_rows: list[dict[str, Any]] = []
            for conn in display_data:
                if conn["datasets"]:
                    flat_rows.extend(
                        {
                            "connection_id": conn["id"],
                            "connection_name": conn["name"],
                            "owner": conn["owner"],
                            "dataset_id": dataset["id"],
                            "dataset_name": dataset["name"],
                        }
                        for dataset in conn["datasets"]
                    )
                else:
                    flat_rows.append(
                        {
                            "connection_id": conn["id"],
                            "connection_name": conn["name"],
                            "owner": conn["owner"],
                            "dataset_id": "",
                            "dataset_name": "",
                        }
                    )
            return _generator._format_as_csv(
                ["connection_id", "connection_name", "owner", "dataset_id", "dataset_name"],
                flat_rows,
            )
        lines = ["", f"Found {len(display_data)} accessible connection(s):", ""]
        for conn in display_data:
            lines.append(f"Connection: {conn['name']} ({conn['id']})")
            lines.append(f"Owner: {conn['owner']}")
            if conn["datasets"]:
                lines.append(f"Datasets ({len(conn['datasets'])}):")
                lines.extend(f"  {dataset['id']}  {dataset['name']}" for dataset in conn["datasets"])
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
        raw_connections = cja.getConnections(output="raw", expansion="name,ownerFullName,dataSets")
        conn_map: dict[str, dict[str, Any]] = {}
        for conn in _generator._extract_connections_list(raw_connections):
            if not isinstance(conn, dict):
                continue
            raw_datasets = conn.get("dataSets", conn.get("datasets", []))
            if not isinstance(raw_datasets, list):
                raw_datasets = []
            conn_map[_generator._normalize_optional_text(conn.get("id"), default="")] = {
                "name": _generator._normalize_optional_text(conn.get("name"), default="N/A"),
                "datasets": [_generator._extract_dataset_info(dataset) for dataset in raw_datasets],
            }

        available_dvs = cja.getDataViews()
        if isinstance(available_dvs, pd.DataFrame):
            available_dvs = available_dvs.to_dict("records")

        if not available_dvs:
            if is_machine_readable:
                if output_format == "json":
                    return _generator._format_discovery_json({"dataViews": [], "count": 0})
                return "dataview_id,dataview_name,connection_id,connection_name,dataset_id,dataset_name\n"
            return "\nNo data views found or no access to any data views.\n"

        no_conn_details = False
        if not conn_map:
            for dv in available_dvs or []:
                if not isinstance(dv, dict):
                    continue
                if not _generator._is_missing_discovery_value(
                    dv.get("parentDataGroupId"),
                    treat_blank_string=True,
                    treat_null_like_strings=True,
                ):
                    no_conn_details = True
                    break

        if not is_machine_readable:
            print(f"Processing {len(available_dvs)} data view(s)...")

        display_data = []
        for index, dv in enumerate(available_dvs):
            if not isinstance(dv, dict):
                continue
            if not is_machine_readable:
                print(
                    f"  [{index + 1}/{len(available_dvs)}] {_generator._normalize_optional_text(dv.get('name'), default='N/A')}...",
                    end="\r",
                )
            parent_conn_id = dv.get("parentDataGroupId")
            if _generator._is_missing_discovery_value(
                parent_conn_id, treat_blank_string=True, treat_null_like_strings=True
            ):
                parent_conn_id = None
            conn_info = conn_map.get(parent_conn_id) if parent_conn_id else None
            display_data.append(
                {
                    "id": _generator._normalize_optional_text(dv.get("id"), default="N/A"),
                    "name": _generator._normalize_optional_text(dv.get("name"), default="N/A"),
                    "connection": {
                        "id": parent_conn_id or "N/A",
                        "name": conn_info.get("name") if conn_info else None,
                    },
                    "datasets": conn_info.get("datasets", []) if conn_info else [],
                }
            )

        display_data = _generator._apply_discovery_filters_and_sort(
            display_data,
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
            sort_expression=sort_expression,
            searchable_fields=["id", "name", "connection", "datasets"],
            default_sort_field="name",
        )

        if not is_machine_readable:
            print("\033[2K", end="\r")

        warning = (
            "Note: Connection details are unavailable (the GET /connections API\n"
            "requires product-admin privileges). Showing connection IDs only."
        )
        payload: dict[str, Any] = {"dataViews": display_data, "count": len(display_data)}
        if no_conn_details:
            payload["warning"] = warning.replace("\n", " ")

        if output_format == "json":
            return _generator._format_discovery_json(payload)
        if output_format == "csv":
            flat_rows: list[dict[str, Any]] = []
            for entry in display_data:
                conn_id = entry["connection"]["id"]
                conn_name = entry["connection"]["name"] or ""
                if entry["datasets"]:
                    flat_rows.extend(
                        {
                            "dataview_id": entry["id"],
                            "dataview_name": entry["name"],
                            "connection_id": conn_id,
                            "connection_name": conn_name,
                            "dataset_id": dataset["id"],
                            "dataset_name": dataset["name"],
                        }
                        for dataset in entry["datasets"]
                    )
                else:
                    flat_rows.append(
                        {
                            "dataview_id": entry["id"],
                            "dataview_name": entry["name"],
                            "connection_id": conn_id,
                            "connection_name": conn_name,
                            "dataset_id": "",
                            "dataset_name": "",
                        }
                    )
            return _generator._format_as_csv(
                ["dataview_id", "dataview_name", "connection_id", "connection_name", "dataset_id", "dataset_name"],
                flat_rows,
            )
        lines = [""]
        if no_conn_details:
            lines.extend([warning, ""])
        lines.append(f"Found {len(display_data)} data view(s) with dataset information:")
        lines.append("")
        for entry in display_data:
            lines.append(f"Data View: {entry['name']} ({entry['id']})")
            if entry["connection"]["name"]:
                lines.append(f"Connection: {entry['connection']['name']} ({entry['connection']['id']})")
            else:
                lines.append(f"Connection: {entry['connection']['id']}")
            if entry["datasets"]:
                lines.append(f"Datasets ({len(entry['datasets'])}):")
                lines.extend(f"  {dataset['id']}  {dataset['name']}" for dataset in entry["datasets"])
            elif not no_conn_details:
                lines.append("Datasets: (none)")
            lines.append("")
        return "\n".join(lines)

    return _inner


def list_dataviews(
    config_file: str = "config.json",
    output_format: str = "table",
    output_file: str | None = None,
    profile: str | None = None,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> bool:
    """List all accessible data views and exit."""
    return _run_list_command(
        banner_text="LISTING ACCESSIBLE DATA VIEWS",
        command_name="list_dataviews",
        fetch_and_format=_fetch_dataviews(
            output_format,
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
            sort_expression=sort_expression,
        ),
        config_file=config_file,
        output_format=output_format,
        output_file=output_file,
        profile=profile,
        validate_inputs=lambda: _generator._validate_discovery_query_inputs(
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
        ),
    )


def describe_dataview(
    data_view_id: str,
    config_file: str = "config.json",
    output_format: str = "table",
    output_file: str | None = None,
    profile: str | None = None,
) -> bool:
    """Describe a single data view with component counts and exit."""
    return _run_list_command(
        banner_text=f"DESCRIBING DATA VIEW: {data_view_id}",
        command_name="describe_dataview",
        fetch_and_format=_fetch_describe_dataview(data_view_id, output_format),
        config_file=config_file,
        output_format=output_format,
        output_file=output_file,
        profile=profile,
    )


def list_metrics(
    data_view_id: str,
    config_file: str = "config.json",
    output_format: str = "table",
    output_file: str | None = None,
    profile: str | None = None,
    data_view_name: str | None = None,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> bool:
    """List all metrics for a given data view."""
    return _run_list_command(
        banner_text=f"LISTING METRICS FOR DATA VIEW: {data_view_id}",
        command_name="list_metrics",
        fetch_and_format=_fetch_metrics_list(
            data_view_id,
            output_format,
            data_view_name=data_view_name,
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
            sort_expression=sort_expression,
        ),
        config_file=config_file,
        output_format=output_format,
        output_file=output_file,
        profile=profile,
        validate_inputs=lambda: _generator._validate_discovery_query_inputs(
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
        ),
    )


def list_dimensions(
    data_view_id: str,
    config_file: str = "config.json",
    output_format: str = "table",
    output_file: str | None = None,
    profile: str | None = None,
    data_view_name: str | None = None,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> bool:
    """List all dimensions for a given data view."""
    return _run_list_command(
        banner_text=f"LISTING DIMENSIONS FOR DATA VIEW: {data_view_id}",
        command_name="list_dimensions",
        fetch_and_format=_fetch_dimensions_list(
            data_view_id,
            output_format,
            data_view_name=data_view_name,
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
            sort_expression=sort_expression,
        ),
        config_file=config_file,
        output_format=output_format,
        output_file=output_file,
        profile=profile,
        validate_inputs=lambda: _generator._validate_discovery_query_inputs(
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
        ),
    )


def list_segments(
    data_view_id: str,
    config_file: str = "config.json",
    output_format: str = "table",
    output_file: str | None = None,
    profile: str | None = None,
    data_view_name: str | None = None,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> bool:
    """List all segments (filters) for a given data view."""
    return _run_list_command(
        banner_text=f"LISTING SEGMENTS FOR DATA VIEW: {data_view_id}",
        command_name="list_segments",
        fetch_and_format=_fetch_segments_list(
            data_view_id,
            output_format,
            data_view_name=data_view_name,
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
            sort_expression=sort_expression,
        ),
        config_file=config_file,
        output_format=output_format,
        output_file=output_file,
        profile=profile,
        validate_inputs=lambda: _generator._validate_discovery_query_inputs(
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
        ),
    )


def list_calculated_metrics(
    data_view_id: str,
    config_file: str = "config.json",
    output_format: str = "table",
    output_file: str | None = None,
    profile: str | None = None,
    data_view_name: str | None = None,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> bool:
    """List all calculated metrics for a given data view."""
    return _run_list_command(
        banner_text=f"LISTING CALCULATED METRICS FOR DATA VIEW: {data_view_id}",
        command_name="list_calculated_metrics",
        fetch_and_format=_fetch_calculated_metrics_list(
            data_view_id,
            output_format,
            data_view_name=data_view_name,
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
            sort_expression=sort_expression,
        ),
        config_file=config_file,
        output_format=output_format,
        output_file=output_file,
        profile=profile,
        validate_inputs=lambda: _generator._validate_discovery_query_inputs(
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
        ),
    )


def list_connections(
    config_file: str = "config.json",
    output_format: str = "table",
    output_file: str | None = None,
    profile: str | None = None,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> bool:
    """List all accessible connections with their datasets and exit."""
    return _run_list_command(
        banner_text="LISTING ACCESSIBLE CONNECTIONS",
        command_name="list_connections",
        fetch_and_format=_fetch_connections(
            output_format,
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
            sort_expression=sort_expression,
        ),
        config_file=config_file,
        output_format=output_format,
        output_file=output_file,
        profile=profile,
        validate_inputs=lambda: _generator._validate_discovery_query_inputs(
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
        ),
    )


def list_datasets(
    config_file: str = "config.json",
    output_format: str = "table",
    output_file: str | None = None,
    profile: str | None = None,
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    limit: int | None = None,
    sort_expression: str | None = None,
) -> bool:
    """List all data views with their backing connections and underlying datasets."""
    return _run_list_command(
        banner_text="LISTING DATA VIEWS WITH DATASETS",
        command_name="list_datasets",
        fetch_and_format=_fetch_datasets(
            output_format,
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
            sort_expression=sort_expression,
        ),
        config_file=config_file,
        output_format=output_format,
        output_file=output_file,
        profile=profile,
        validate_inputs=lambda: _generator._validate_discovery_query_inputs(
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
        ),
    )
