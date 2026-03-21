"""Tests for the discovery.py extraction — verifies imports and backwards compat."""

import pytest


class TestDiscoveryModuleExists:
    """Verify the new discovery module is importable."""

    def test_discovery_module_importable(self):
        from cja_auto_sdr.cli.commands import discovery
        assert hasattr(discovery, '_format_discovery_json')
        assert hasattr(discovery, '_emit_discovery_error')
        assert hasattr(discovery, '_emit_output_contract_error')
        assert hasattr(discovery, '_emit_json_output')
        assert hasattr(discovery, '_resolve_discovery_output_format')


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
