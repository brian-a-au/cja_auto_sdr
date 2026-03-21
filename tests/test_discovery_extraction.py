"""Tests for the discovery.py extraction — verifies imports and backwards compat."""


class TestDiscoveryModuleExists:
    """Verify the new discovery module is importable."""

    def test_discovery_module_importable(self):
        from cja_auto_sdr.cli.commands import discovery

        assert hasattr(discovery, "_format_discovery_json")
        assert hasattr(discovery, "_emit_discovery_error")
        assert hasattr(discovery, "_emit_output_contract_error")
        assert hasattr(discovery, "_emit_json_output")
        assert hasattr(discovery, "_resolve_discovery_output_format")


class TestDiscoveryQueryHelpers:
    """Verify query/filter helpers are importable from discovery module."""

    def test_compile_discovery_pattern(self):
        from cja_auto_sdr.cli.commands.discovery import _compile_discovery_pattern

        assert callable(_compile_discovery_pattern)

    def test_validate_discovery_query_inputs(self):
        from cja_auto_sdr.cli.commands.discovery import _validate_discovery_query_inputs

        assert callable(_validate_discovery_query_inputs)

    def test_apply_discovery_filters_and_sort(self):
        from cja_auto_sdr.cli.commands.discovery import _apply_discovery_filters_and_sort

        assert callable(_apply_discovery_filters_and_sort)

    def test_is_missing_sort_value(self):
        from cja_auto_sdr.cli.commands.discovery import _is_missing_sort_value

        assert callable(_is_missing_sort_value)

    def test_to_numeric_sort_value(self):
        from cja_auto_sdr.cli.commands.discovery import _to_numeric_sort_value

        assert callable(_to_numeric_sort_value)


class TestDiscoveryDataviewHelpers:
    """Verify dataview lookup helpers are importable from discovery module."""

    def test_fetch_dataview_lookup_payload(self):
        from cja_auto_sdr.cli.commands.discovery import _fetch_dataview_lookup_payload

        assert callable(_fetch_dataview_lookup_payload)

    def test_require_accessible_dataview(self):
        from cja_auto_sdr.cli.commands.discovery import _require_accessible_dataview

        assert callable(_require_accessible_dataview)

    def test_assess_dataview_lookup(self):
        from cja_auto_sdr.cli.commands.discovery import _assess_dataview_lookup

        assert callable(_assess_dataview_lookup)

    def test_coerce_valid_dataview_lookup_payload(self):
        from cja_auto_sdr.cli.commands.discovery import _coerce_valid_dataview_lookup_payload

        assert callable(_coerce_valid_dataview_lookup_payload)

    def test_normalize_describe_dataview_metadata(self):
        from cja_auto_sdr.cli.commands.discovery import _normalize_describe_dataview_metadata

        assert callable(_normalize_describe_dataview_metadata)

    def test_resolve_dataview_name(self):
        from cja_auto_sdr.cli.commands.discovery import _resolve_dataview_name

        assert callable(_resolve_dataview_name)


class TestOutputDirectoryErrors:
    """Verify output-directory errors have consistent format."""

    def test_not_directory_error_format(self):
        import inspect

        from cja_auto_sdr.cli import execution

        source = inspect.getsource(execution)
        assert "ERROR: Output directory" in source or "ERROR: Cannot" in source


class TestHelpTextImprovements:
    """Verify improved help text for key CLI flags."""

    def test_exit_codes_help_text(self):
        import contextlib
        import io

        from cja_auto_sdr.cli.parser import parse_arguments

        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                parse_arguments(["--help"])
        except SystemExit:
            pass
        output = buf.getvalue()
        assert "exit code" in output.lower()
        assert "table" in output.lower() or "meaning" in output.lower()

    def test_batch_help_describes_parallel_data_views(self):
        import contextlib
        import io

        from cja_auto_sdr.cli.parser import parse_arguments

        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                parse_arguments(["--help"])
        except SystemExit:
            pass
        output = buf.getvalue()
        assert "Enable batch processing mode: process multiple data" in output
        assert "views in parallel" in output
        assert "batch directory of config files" not in output

    def test_quiet_help_clarifies_errors(self):
        import contextlib
        import io

        from cja_auto_sdr.cli.parser import parse_arguments

        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                parse_arguments(["--help"])
        except SystemExit:
            pass
        output = buf.getvalue()
        assert "quiet" in output.lower()

    def test_format_uses_shorthand_not_aliases(self):
        import contextlib
        import io

        from cja_auto_sdr.cli.parser import parse_arguments

        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                parse_arguments(["--help"])
        except SystemExit:
            pass
        output = buf.getvalue()
        assert "shorthand" in output.lower() or "Shorthand" in output


class TestDiscoveryComponentHelpers:
    """Verify component fetch specs and row builders are importable."""

    def test_component_fetch_spec_class(self):
        from cja_auto_sdr.cli.commands.discovery import _ComponentFetchSpec

        assert _ComponentFetchSpec is not None

    def test_metrics_fetch_spec(self):
        from cja_auto_sdr.cli.commands.discovery import _METRICS_COMPONENT_FETCH_SPEC

        assert _METRICS_COMPONENT_FETCH_SPEC is not None

    def test_dimensions_fetch_spec(self):
        from cja_auto_sdr.cli.commands.discovery import _DIMENSIONS_COMPONENT_FETCH_SPEC

        assert _DIMENSIONS_COMPONENT_FETCH_SPEC is not None

    def test_segments_fetch_spec(self):
        from cja_auto_sdr.cli.commands.discovery import _SEGMENTS_COMPONENT_FETCH_SPEC

        assert _SEGMENTS_COMPONENT_FETCH_SPEC is not None

    def test_calc_metrics_fetch_spec(self):
        from cja_auto_sdr.cli.commands.discovery import _CALCULATED_METRICS_COMPONENT_FETCH_SPEC

        assert _CALCULATED_METRICS_COMPONENT_FETCH_SPEC is not None

    def test_fetch_component_payload(self):
        from cja_auto_sdr.cli.commands.discovery import _fetch_component_payload

        assert callable(_fetch_component_payload)

    def test_build_component_list_fetcher(self):
        from cja_auto_sdr.cli.commands.discovery import _build_component_list_fetcher

        assert callable(_build_component_list_fetcher)

    def test_build_metric_display_row(self):
        from cja_auto_sdr.cli.commands.discovery import _build_metric_display_row

        assert callable(_build_metric_display_row)

    def test_build_dimension_display_row(self):
        from cja_auto_sdr.cli.commands.discovery import _build_dimension_display_row

        assert callable(_build_dimension_display_row)

    def test_build_segment_display_row(self):
        from cja_auto_sdr.cli.commands.discovery import _build_segment_display_row

        assert callable(_build_segment_display_row)

    def test_build_calculated_metric_display_row(self):
        from cja_auto_sdr.cli.commands.discovery import _build_calculated_metric_display_row

        assert callable(_build_calculated_metric_display_row)

    def test_normalize_component_text_fields(self):
        from cja_auto_sdr.cli.commands.discovery import _normalize_component_text_fields

        assert callable(_normalize_component_text_fields)

    def test_format_governance_rows(self):
        from cja_auto_sdr.cli.commands.discovery import _format_governance_rows_for_tabular

        assert callable(_format_governance_rows_for_tabular)


class TestDiscoveryFetchers:
    """Verify discovery fetchers are importable from discovery module."""

    def test_fetch_dataviews(self):
        from cja_auto_sdr.cli.commands.discovery import _fetch_dataviews

        assert callable(_fetch_dataviews)

    def test_fetch_describe_dataview(self):
        from cja_auto_sdr.cli.commands.discovery import _fetch_describe_dataview

        assert callable(_fetch_describe_dataview)

    def test_fetch_metrics_list(self):
        from cja_auto_sdr.cli.commands.discovery import _fetch_metrics_list

        assert callable(_fetch_metrics_list)

    def test_fetch_dimensions_list(self):
        from cja_auto_sdr.cli.commands.discovery import _fetch_dimensions_list

        assert callable(_fetch_dimensions_list)

    def test_fetch_segments_list(self):
        from cja_auto_sdr.cli.commands.discovery import _fetch_segments_list

        assert callable(_fetch_segments_list)

    def test_fetch_calculated_metrics_list(self):
        from cja_auto_sdr.cli.commands.discovery import _fetch_calculated_metrics_list

        assert callable(_fetch_calculated_metrics_list)

    def test_fetch_connections(self):
        from cja_auto_sdr.cli.commands.discovery import _fetch_connections

        assert callable(_fetch_connections)

    def test_fetch_datasets(self):
        from cja_auto_sdr.cli.commands.discovery import _fetch_datasets

        assert callable(_fetch_datasets)

    def test_extract_dataset_info(self):
        from cja_auto_sdr.cli.commands.discovery import _extract_dataset_info

        assert callable(_extract_dataset_info)

    def test_extract_connections_list(self):
        from cja_auto_sdr.cli.commands.discovery import _extract_connections_list

        assert callable(_extract_connections_list)


class TestTqdmBarFormatCentralized:
    """Verify TQDM_BAR_FORMAT is centralized in constants."""

    def test_tqdm_bar_format_in_constants(self):
        from cja_auto_sdr.core.constants import TQDM_BAR_FORMAT

        assert isinstance(TQDM_BAR_FORMAT, str)
        assert "{l_bar}" in TQDM_BAR_FORMAT
