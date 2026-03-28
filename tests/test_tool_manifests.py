# tests/test_tool_manifests.py
"""Tests for tools/ JSON tool manifests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

TOOLS_DIR = Path(__file__).resolve().parent.parent / "tools"

REQUIRED_MANIFESTS = [
    "cja_sdr_generate.json",
    "cja_sdr_discover.json",
    "cja_sdr_config.json",
    "cja_sdr_diff.json",
    "cja_sdr_governance.json",
]

REQUIRED_TOP_KEYS = {"name", "description", "parameters"}


class TestToolManifests:
    """Validate tool manifest structure and content."""

    def test_readme_exists(self):
        assert (TOOLS_DIR / "README.md").exists()

    @pytest.fixture(params=REQUIRED_MANIFESTS)
    def manifest(self, request):
        path = TOOLS_DIR / request.param
        assert path.exists(), f"Missing manifest: {request.param}"
        return json.loads(path.read_text())

    @pytest.fixture(params=REQUIRED_MANIFESTS)
    def manifest_name(self, request):
        return request.param

    def test_manifest_is_valid_json(self, manifest):
        assert isinstance(manifest, dict)

    def test_manifest_has_required_keys(self, manifest):
        for key in REQUIRED_TOP_KEYS:
            assert key in manifest, f"Missing key: {key}"

    def test_parameters_type_is_object(self, manifest):
        assert manifest["parameters"]["type"] == "object"

    def test_parameters_have_properties(self, manifest):
        assert "properties" in manifest["parameters"]

    def test_generate_manifest_quality_report_is_format_enum(self):
        manifest = json.loads((TOOLS_DIR / "cja_sdr_generate.json").read_text())
        props = manifest["parameters"]["properties"]
        if "quality_report" in props:
            assert "enum" in props["quality_report"]
            assert "json" in props["quality_report"]["enum"]
            assert "csv" in props["quality_report"]["enum"]

    def test_generate_manifest_fail_on_quality_includes_info(self):
        manifest = json.loads((TOOLS_DIR / "cja_sdr_generate.json").read_text())
        props = manifest["parameters"]["properties"]
        if "fail_on_quality" in props:
            assert "INFO" in props["fail_on_quality"]["enum"]

    def test_diff_snapshot_params_are_file_paths(self):
        manifest = json.loads((TOOLS_DIR / "cja_sdr_diff.json").read_text())
        props = manifest["parameters"]["properties"]
        # snapshot-related params should indicate file paths
        for key in ["compare_snapshots_source", "compare_snapshots_target", "snapshot"]:
            if key in props:
                desc = props[key].get("description", "")
                assert "path" in desc.lower() or "file" in desc.lower(), f"{key} should be described as a file path"

    def test_no_show_config_in_manifests(self):
        for name in REQUIRED_MANIFESTS:
            manifest = json.loads((TOOLS_DIR / name).read_text())
            props = manifest["parameters"]["properties"]
            assert "show_config" not in props, f"show_config should not be in {name}"

    def test_readme_covers_required_topics(self):
        content = (TOOLS_DIR / "README.md").read_text()
        required_topics = [
            "agent_mode",
            "stdout",
            "run-summary-json",
            "orchestrator",
            "applicability",
            "preflight",
        ]
        for topic in required_topics:
            assert topic.lower() in content.lower(), f"README missing topic: {topic}"

    def test_golden_shape_generate(self):
        manifest = json.loads((TOOLS_DIR / "cja_sdr_generate.json").read_text())
        assert manifest["name"] == "cja_sdr_generate"
        assert "parameters" in manifest
        props = manifest["parameters"]["properties"]
        assert "data_view_id" in props

    def test_golden_shape_discover(self):
        manifest = json.loads((TOOLS_DIR / "cja_sdr_discover.json").read_text())
        assert manifest["name"] == "cja_sdr_discover"

    def test_golden_shape_config(self):
        manifest = json.loads((TOOLS_DIR / "cja_sdr_config.json").read_text())
        assert manifest["name"] == "cja_sdr_config"

    def test_golden_shape_diff(self):
        manifest = json.loads((TOOLS_DIR / "cja_sdr_diff.json").read_text())
        assert manifest["name"] == "cja_sdr_diff"

    def test_golden_shape_governance(self):
        manifest = json.loads((TOOLS_DIR / "cja_sdr_governance.json").read_text())
        assert manifest["name"] == "cja_sdr_governance"
