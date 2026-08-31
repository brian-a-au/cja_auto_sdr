"""Validate tool manifests against code-owned agent-output contract definitions.

These tests fail when manifests drift from the runtime capability tables,
catching the exact class of bug that motivated the v3.5.1 hardening work.
"""

from __future__ import annotations

import json
from pathlib import Path

from cja_auto_sdr.cli.agent_output import (
    DIFF_STDOUT_FORMATS,
    DISCOVERY_STDOUT_FORMATS,
    ORG_REPORT_STDOUT_FORMATS,
)

_TOOLS_DIR = Path(__file__).resolve().parents[1] / "tools"


def _load_manifest(name: str) -> dict:
    path = _TOOLS_DIR / f"{name}.json"
    return json.loads(path.read_text())


def _manifest_format_enum(manifest: dict) -> list[str]:
    """Extract the format parameter's enum values from a manifest."""
    props = manifest.get("parameters", {}).get("properties", {})
    return props.get("format", {}).get("enum", [])


# ---------------------------------------------------------------------------
# Diff manifest contract
# ---------------------------------------------------------------------------


class TestDiffManifestContract:
    """Verify cja_sdr_diff.json stays aligned with DIFF_STDOUT_FORMATS."""

    def setup_method(self):
        self.manifest = _load_manifest("cja_sdr_diff")
        self.format_enum = set(_manifest_format_enum(self.manifest))

    def test_manifest_format_enum_is_nonempty(self):
        assert self.format_enum, "diff manifest must declare format enum"

    def test_stdout_formats_are_subset_of_manifest_enum(self):
        """Every stdout-capable format must appear in the manifest enum."""
        assert DIFF_STDOUT_FORMATS <= self.format_enum, (
            f"DIFF_STDOUT_FORMATS {DIFF_STDOUT_FORMATS} not in manifest enum {self.format_enum}"
        )

    def test_file_only_formats_not_in_stdout_set(self):
        """Formats declared by manifest but not in stdout set are file-only."""
        file_only = self.format_enum - DIFF_STDOUT_FORMATS
        for fmt in file_only:
            assert fmt not in DIFF_STDOUT_FORMATS

    def test_output_description_mentions_json_stdout(self):
        """The output parameter must document JSON as the stdout-capable format."""
        output_desc = self.manifest["parameters"]["properties"]["output"]["description"]
        assert "json" in output_desc.lower(), "diff output description must mention JSON stdout capability"

    def test_agent_mode_description_mentions_json(self):
        """Agent mode description must reference structured JSON output."""
        desc = self.manifest["parameters"]["properties"]["agent_mode"]["description"]
        assert "json" in desc.lower(), "diff agent_mode description must mention JSON"


# ---------------------------------------------------------------------------
# Governance (org-report) manifest contract
# ---------------------------------------------------------------------------


class TestGovernanceManifestContract:
    """Verify cja_sdr_governance.json stays aligned with ORG_REPORT_STDOUT_FORMATS."""

    def setup_method(self):
        self.manifest = _load_manifest("cja_sdr_governance")
        self.format_enum = set(_manifest_format_enum(self.manifest))

    def test_manifest_format_enum_is_nonempty(self):
        assert self.format_enum, "governance manifest must declare format enum"

    def test_stdout_formats_are_subset_of_manifest_enum(self):
        """Every stdout-capable format must appear in the manifest enum."""
        assert ORG_REPORT_STDOUT_FORMATS <= self.format_enum, (
            f"ORG_REPORT_STDOUT_FORMATS {ORG_REPORT_STDOUT_FORMATS} not in manifest enum {self.format_enum}"
        )

    def test_file_only_formats_not_in_stdout_set(self):
        """Formats declared by manifest but not in stdout set are file-only."""
        file_only = self.format_enum - ORG_REPORT_STDOUT_FORMATS
        for fmt in file_only:
            assert fmt not in ORG_REPORT_STDOUT_FORMATS

    def test_agent_mode_description_mentions_json(self):
        """Agent mode description must reference structured JSON output."""
        desc = self.manifest["parameters"]["properties"]["agent_mode"]["description"]
        assert "json" in desc.lower(), "governance agent_mode description must mention JSON"


# ---------------------------------------------------------------------------
# Discovery manifest contract
# ---------------------------------------------------------------------------


class TestDiscoveryManifestContract:
    """Verify cja_sdr_discover.json stays aligned with DISCOVERY_STDOUT_FORMATS."""

    def setup_method(self):
        self.manifest = _load_manifest("cja_sdr_discover")
        self.format_enum = set(_manifest_format_enum(self.manifest))

    def test_manifest_format_enum_is_nonempty(self):
        assert self.format_enum, "discovery manifest must declare format enum"

    def test_agent_stdout_formats_are_subset_of_manifest_enum(self):
        """Runtime stdout-capable discovery formats must appear in the manifest enum."""
        assert DISCOVERY_STDOUT_FORMATS <= self.format_enum, (
            f"DISCOVERY_STDOUT_FORMATS {DISCOVERY_STDOUT_FORMATS} not in manifest enum {self.format_enum}"
        )

    def test_agent_mode_description_mentions_json(self):
        """Agent mode description must reference JSON output."""
        desc = self.manifest["parameters"]["properties"]["agent_mode"]["description"]
        assert "json" in desc.lower(), "discovery agent_mode description must mention JSON"

    def test_dataset_metadata_contract_is_agent_discoverable(self):
        """Agents must be told that dataset metadata is additive and Connection-scoped."""
        desc = self.manifest["description"]
        assert "connectionMetadata" in desc
        assert "dataset-to-Connection relationship" in desc
        assert "ignore unknown future keys" in desc


# ---------------------------------------------------------------------------
# Cross-manifest consistency
# ---------------------------------------------------------------------------


class TestCrossManifestConsistency:
    """Verify shared patterns across all agent-enabled manifests."""

    AGENT_MANIFESTS = ("cja_sdr_diff", "cja_sdr_governance", "cja_sdr_discover")

    def test_all_agent_manifests_have_agent_mode_param(self):
        for name in self.AGENT_MANIFESTS:
            manifest = _load_manifest(name)
            props = manifest["parameters"]["properties"]
            assert "agent_mode" in props, f"{name} missing agent_mode parameter"

    def test_all_agent_manifests_have_format_param(self):
        for name in self.AGENT_MANIFESTS:
            manifest = _load_manifest(name)
            props = manifest["parameters"]["properties"]
            assert "format" in props, f"{name} missing format parameter"

    def test_agent_mode_is_boolean_in_all_manifests(self):
        for name in self.AGENT_MANIFESTS:
            manifest = _load_manifest(name)
            agent_mode = manifest["parameters"]["properties"]["agent_mode"]
            assert agent_mode["type"] == "boolean", f"{name} agent_mode must be boolean"

    def test_json_is_in_every_format_enum(self):
        """JSON must be a valid format in every agent-enabled manifest."""
        for name in self.AGENT_MANIFESTS:
            manifest = _load_manifest(name)
            formats = _manifest_format_enum(manifest)
            assert "json" in formats, f"{name} format enum must include 'json'"
