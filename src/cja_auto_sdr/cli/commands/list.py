"""List/discovery CLI command entrypoints extracted from generator.py."""

# ruff: noqa: T201

from __future__ import annotations

import logging
from collections.abc import Callable

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

json = _discovery.json
pd = _discovery.pd
shutil = _discovery.shutil
textwrap = _discovery.textwrap

DiscoveryNotFoundError = _discovery.DiscoveryNotFoundError
RECOVERABLE_OPTIONAL_COMPONENT_COUNT_EXCEPTIONS = _discovery.RECOVERABLE_OPTIONAL_COMPONENT_COUNT_EXCEPTIONS

_METRICS_COMPONENT_FETCH_SPEC = _discovery._METRICS_COMPONENT_FETCH_SPEC
_DIMENSIONS_COMPONENT_FETCH_SPEC = _discovery._DIMENSIONS_COMPONENT_FETCH_SPEC
_SEGMENTS_COMPONENT_FETCH_SPEC = _discovery._SEGMENTS_COMPONENT_FETCH_SPEC
_CALCULATED_METRICS_COMPONENT_FETCH_SPEC = _discovery._CALCULATED_METRICS_COMPONENT_FETCH_SPEC


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
    is_machine_readable = _discovery._is_machine_readable_output(output_format, output_file)

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
            _discovery._emit_discovery_error(
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

    except _discovery.DiscoveryNotFoundError as e:
        _discovery._emit_discovery_error(
            str(e),
            is_machine_readable=is_machine_readable,
            error_type="not_found",
            human_to_stderr=False,
        )
        return False

    except _discovery.DiscoveryArgumentError as e:
        _discovery._emit_discovery_error(
            str(e),
            is_machine_readable=is_machine_readable,
            error_type="invalid_arguments",
            human_to_stderr=False,
        )
        return False

    except _discovery.OutputContractError as e:
        _discovery._emit_output_contract_error(
            str(e),
            is_machine_readable=is_machine_readable,
            human_to_stderr=False,
        )
        return False

    except FileNotFoundError:
        _discovery._emit_discovery_error(
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
        _discovery._emit_discovery_error(
            f"Failed to connect to CJA API: {e!s}",
            is_machine_readable=is_machine_readable,
            error_type="connectivity_error",
            human_to_stderr=False,
        )
        return False


_fetch_dataviews = _discovery._fetch_dataviews
_assess_dataview_lookup = _discovery._assess_dataview_lookup
_coerce_valid_dataview_lookup_payload = _discovery._coerce_valid_dataview_lookup_payload
_fetch_dataview_lookup_payload = _discovery._fetch_dataview_lookup_payload
_require_accessible_dataview = _discovery._require_accessible_dataview
_normalize_component_records_or_raise = _discovery._normalize_component_records_or_raise
_normalize_describe_dataview_metadata = _discovery._normalize_describe_dataview_metadata
_fetch_describe_dataview = _discovery._fetch_describe_dataview
_resolve_dataview_name = _discovery._resolve_dataview_name
_format_governance_rows_for_tabular = _discovery._format_governance_rows_for_tabular
_fetch_component_payload = _discovery._fetch_component_payload
_build_component_list_fetcher = _discovery._build_component_list_fetcher
_build_metric_display_row = _discovery._build_metric_display_row
_fetch_metrics_list = _discovery._fetch_metrics_list
_build_dimension_display_row = _discovery._build_dimension_display_row
_fetch_dimensions_list = _discovery._fetch_dimensions_list
_approved_display = _discovery._approved_display
_tags_display = _discovery._tags_display
_build_segment_display_row = _discovery._build_segment_display_row
_fetch_segments_list = _discovery._fetch_segments_list
_build_calculated_metric_display_row = _discovery._build_calculated_metric_display_row
_fetch_calculated_metrics_list = _discovery._fetch_calculated_metrics_list
_fetch_connections = _discovery._fetch_connections
_fetch_datasets = _discovery._fetch_datasets


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
        validate_inputs=lambda: _discovery._validate_discovery_query_inputs(
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
        validate_inputs=lambda: _discovery._validate_discovery_query_inputs(
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
        validate_inputs=lambda: _discovery._validate_discovery_query_inputs(
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
        validate_inputs=lambda: _discovery._validate_discovery_query_inputs(
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
        validate_inputs=lambda: _discovery._validate_discovery_query_inputs(
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
        validate_inputs=lambda: _discovery._validate_discovery_query_inputs(
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
        validate_inputs=lambda: _discovery._validate_discovery_query_inputs(
            filter_pattern=filter_pattern,
            exclude_pattern=exclude_pattern,
            limit=limit,
        ),
    )
