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
