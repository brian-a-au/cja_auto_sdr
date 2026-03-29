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

    def test_generate_manifest_includes_cli_format_aliases(self):
        manifest = json.loads((TOOLS_DIR / "cja_sdr_generate.json").read_text())
        fmt = manifest["parameters"]["properties"]["format"]

        for value in ["all", "reports", "data", "ci"]:
            assert value in fmt["enum"]
        desc = fmt["description"].lower()
        assert "reports" in desc
        assert "data" in desc
        assert "ci" in desc

    def test_governance_threshold_types_match_cli(self):
        manifest = json.loads((TOOLS_DIR / "cja_sdr_governance.json").read_text())
        props = manifest["parameters"]["properties"]

        duplicate_threshold = props["duplicate_threshold"]
        assert duplicate_threshold["type"] == "integer"
        assert duplicate_threshold["minimum"] == 0

        isolated_threshold = props["isolated_threshold"]
        assert isolated_threshold["type"] == "number"
        assert isolated_threshold["minimum"] == 0.0
        assert isolated_threshold["maximum"] == 1.0

    def test_generate_manifest_quality_report_output_contract_matches_cli(self):
        manifest = json.loads((TOOLS_DIR / "cja_sdr_generate.json").read_text())
        props = manifest["parameters"]["properties"]

        assert "output" in props
        assert "output_dir" in props
        output_desc = props["output"]["description"].lower()
        assert "quality report" in output_desc
        assert "stdout" in output_desc
        assert "output_dir" in output_desc

        output_dir_desc = props["output_dir"]["description"].lower()
        assert "auto-named" in output_dir_desc
        assert "quality report" in output_dir_desc

        quality_report_desc = props["quality_report"]["description"].lower()
        assert "standalone" in quality_report_desc
        assert "without sdr files" in quality_report_desc

    def test_diff_snapshot_params_are_file_paths(self):
        manifest = json.loads((TOOLS_DIR / "cja_sdr_diff.json").read_text())
        props = manifest["parameters"]["properties"]
        # snapshot-related params should indicate file paths
        for key in ["compare_snapshots_source", "compare_snapshots_target", "snapshot"]:
            if key in props:
                desc = props[key].get("description", "")
                assert "path" in desc.lower() or "file" in desc.lower(), f"{key} should be described as a file path"

    def test_diff_manifest_limits_diff_output_to_inline_text_formats(self):
        manifest = json.loads((TOOLS_DIR / "cja_sdr_diff.json").read_text())
        props = manifest["parameters"]["properties"]

        assert "output" in props
        assert "diff_output" in props
        assert "output_dir" in props
        assert "format_pr_comment" in props
        assert "include_inventory" not in props

        format_enum = props["format"]["enum"]
        assert "pr_comment" not in format_enum

        output_desc = props["output"]["description"].lower()
        assert "stdout" in output_desc
        assert "diff_output" in output_desc
        assert "json" in output_desc
        assert "format_pr_comment" in output_desc

        diff_output_desc = props["diff_output"]["description"].lower()
        assert "console" in diff_output_desc
        assert "format_pr_comment" in diff_output_desc
        assert "json" in diff_output_desc
        assert "output_dir" in diff_output_desc

        output_dir_desc = props["output_dir"]["description"].lower()
        assert "json" in output_dir_desc
        assert "markdown" in output_dir_desc

        pr_comment_desc = props["format_pr_comment"]["description"].lower()
        assert "--format-pr-comment" in pr_comment_desc
        assert "markdown" in pr_comment_desc

    def test_governance_manifest_describes_output_shape_by_format(self):
        manifest = json.loads((TOOLS_DIR / "cja_sdr_governance.json").read_text())
        props = manifest["parameters"]["properties"]

        output_desc = props["output"]["description"].lower()
        assert "single file" in output_desc
        assert "csv" in output_desc
        assert "multiple csv files" in output_desc
        assert "console" in output_desc

        output_dir_desc = props["output_dir"]["description"].lower()
        assert "auto-named" in output_dir_desc
        assert "csv" in output_dir_desc
        assert "directory" in output_dir_desc

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
            "quality_report",
            "output_dir",
            "diff_output",
            "format_pr_comment",
            "reports",
            "data",
            "ci",
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
