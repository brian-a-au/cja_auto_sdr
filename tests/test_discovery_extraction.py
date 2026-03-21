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
