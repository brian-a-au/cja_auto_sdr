"""List/discovery CLI command entrypoints extracted from generator.py."""

# ruff: noqa: T201

from __future__ import annotations

import json
import logging
import shutil
import textwrap
from collections.abc import Callable

import pandas as pd

from cja_auto_sdr import generator as _generator
from cja_auto_sdr.cli.commands import discovery as _discovery

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

# Backward compat: historically, import sites reached many extracted discovery
# internals through list.py. Keep list.py as a compatibility shim so the
# refactor only changes implementation location, not module surface.
globals().update({"json": json, "pd": pd, "shutil": shutil, "textwrap": textwrap})
_BACKWARD_COMPAT_DISCOVERY_EXPORTS = (
    "RECOVERABLE_OPTIONAL_COMPONENT_COUNT_EXCEPTIONS",
    "DiscoveryArgumentError",
    "DiscoveryNotFoundError",
    "DiscoveryOutputContractError",
    "OutputContractError",
    "_CALCULATED_METRICS_COMPONENT_FETCH_SPEC",
    "_ComponentFetchSpec",
    "_DIMENSIONS_COMPONENT_FETCH_SPEC",
    "_METRICS_COMPONENT_FETCH_SPEC",
    "_NUMERIC_SORT_VALUE_RE",
    "_SEGMENTS_COMPONENT_FETCH_SPEC",
    "_apply_discovery_filters_and_sort",
    "_approved_display",
    "_assess_dataview_lookup",
    "_build_calculated_metric_display_row",
    "_build_component_list_fetcher",
    "_build_dimension_display_row",
    "_build_metric_display_row",
    "_build_segment_display_row",
    "_coerce_valid_dataview_lookup_payload",
    "_compile_discovery_pattern",
    "_count_component_items_for_fetch_spec",
    "_count_component_items_for_fetch_spec_best_effort",
    "_count_component_items_for_fetch_spec_with_retry",
    "_emit_discovery_error",
    "_emit_json_output",
    "_emit_output_contract_error",
    "_extract_connections_list",
    "_extract_dataset_info",
    "_extract_owner_name",
    "_extract_owner_name_from_record",
    "_extract_timestamp_from_record",
    "_fetch_calculated_metrics_list",
    "_fetch_component_payload",
    "_fetch_connections",
    "_fetch_datasets",
    "_fetch_dataview_lookup_payload",
    "_fetch_dataviews",
    "_fetch_describe_dataview",
    "_fetch_dimensions_list",
    "_fetch_metrics_list",
    "_fetch_segments_list",
    "_format_discovery_json",
    "_format_governance_rows_for_tabular",
    "_is_machine_readable_output",
    "_is_missing_sort_value",
    "_normalize_component_records_or_raise",
    "_normalize_component_text_fields",
    "_normalize_describe_dataview_metadata",
    "_normalize_optional_component_int",
    "_normalize_optional_text",
    "_require_accessible_dataview",
    "_resolve_dataview_name",
    "_resolve_discovery_output_format",
    "_tags_display",
    "_to_numeric_sort_value",
    "_to_searchable_text",
    "_validate_discovery_query_inputs",
)
globals().update({name: getattr(_discovery, name) for name in _BACKWARD_COMPAT_DISCOVERY_EXPORTS})

# Keep direct module references explicit for linting and runtime clarity.
DiscoveryArgumentError = _discovery.DiscoveryArgumentError
DiscoveryNotFoundError = _discovery.DiscoveryNotFoundError
DiscoveryOutputContractError = _discovery.DiscoveryOutputContractError
OutputContractError = _discovery.OutputContractError
_emit_discovery_error = _discovery._emit_discovery_error
_emit_output_contract_error = _discovery._emit_output_contract_error
_fetch_calculated_metrics_list = _discovery._fetch_calculated_metrics_list
_fetch_connections = _discovery._fetch_connections
_fetch_datasets = _discovery._fetch_datasets
_fetch_dataviews = _discovery._fetch_dataviews
_fetch_describe_dataview = _discovery._fetch_describe_dataview
_fetch_dimensions_list = _discovery._fetch_dimensions_list
_fetch_metrics_list = _discovery._fetch_metrics_list
_fetch_segments_list = _discovery._fetch_segments_list
_is_machine_readable_output = _discovery._is_machine_readable_output
_validate_discovery_query_inputs = _discovery._validate_discovery_query_inputs


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
    is_machine_readable = _is_machine_readable_output(output_format, output_file)

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
            _emit_discovery_error(
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

    except DiscoveryNotFoundError as e:
        _emit_discovery_error(
            str(e),
            is_machine_readable=is_machine_readable,
            error_type="not_found",
            human_to_stderr=False,
        )
        return False

    except DiscoveryArgumentError as e:
        _emit_discovery_error(
            str(e),
            is_machine_readable=is_machine_readable,
            error_type="invalid_arguments",
            human_to_stderr=False,
        )
        return False

    except OutputContractError as e:
        _emit_output_contract_error(
            str(e),
            is_machine_readable=is_machine_readable,
            human_to_stderr=False,
        )
        return False

    except FileNotFoundError:
        _emit_discovery_error(
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

    except (KeyboardInterrupt, SystemExit):
        if not is_machine_readable:
            print()
            print(_generator.ConsoleColors.warning("Operation cancelled."))
        raise

    except _generator.RECOVERABLE_COMMAND_HANDLER_EXCEPTIONS as e:
        _emit_discovery_error(
            f"Failed to connect to CJA API: {e!s}",
            is_machine_readable=is_machine_readable,
            error_type="connectivity_error",
            human_to_stderr=False,
        )
        _generator._print_api_hint(e, enabled=not is_machine_readable)
        return False


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
        validate_inputs=lambda: _validate_discovery_query_inputs(
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
        validate_inputs=lambda: _validate_discovery_query_inputs(
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
        validate_inputs=lambda: _validate_discovery_query_inputs(
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
        validate_inputs=lambda: _validate_discovery_query_inputs(
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
        validate_inputs=lambda: _validate_discovery_query_inputs(
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
        validate_inputs=lambda: _validate_discovery_query_inputs(
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
        validate_inputs=lambda: _validate_discovery_query_inputs(
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
        ),
    )
