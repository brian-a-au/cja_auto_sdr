# tests/test_agent_contract_docs.py
"""Smoke tests for root agent-contract documentation."""

from __future__ import annotations

from pathlib import Path

import pytest

AGENTS_MD = Path(__file__).resolve().parent.parent / "AGENTS.md"
AGENT_AUTOMATION_MD = Path(__file__).resolve().parent.parent / "docs" / "AGENT_AUTOMATION.md"


class TestAgentContractDocs:
    """Verify AGENTS.md and docs/AGENT_AUTOMATION.md expose the required contract surface."""

    def test_agents_md_exists(self):
        assert AGENTS_MD.exists()

    def test_agent_automation_md_exists(self):
        assert AGENT_AUTOMATION_MD.exists()

    def test_agent_integration_section_exists(self):
        content = AGENTS_MD.read_text()
        assert "## Agent Integration" in content or "# Agent Integration" in content

    def test_agent_mode_documented(self):
        content = AGENTS_MD.read_text()
        assert "--agent-mode" in content

    def test_advisories_documented(self):
        content = AGENTS_MD.read_text()
        assert "advisories" in content.lower()

    def test_tools_directory_referenced(self):
        content = AGENTS_MD.read_text()
        assert "tools/" in content

    def test_playbooks_referenced(self):
        content = AGENTS_MD.read_text()
        assert "agent-playbooks" in content

    def test_workflows_referenced(self):
        content = AGENTS_MD.read_text()
        assert "agent-workflows" in content

    def test_agent_mode_applicability_documented(self):
        content = AGENTS_MD.read_text()
        assert "applicability" in content.lower() or "command-family" in content.lower()

    def test_exact_id_guidance_documented(self):
        content = AGENTS_MD.read_text()
        assert "prefer exact data view ids" in content.lower() or "prefer exact ids" in content.lower()

    def test_orchestrator_scope_documented(self):
        content = AGENTS_MD.read_text().lower()
        assert "scripts/orchestrator.py" in content
        assert "not a full" in content or "not the primary" in content or "batched sdr" in content

    def test_inspection_commands_use_current_form(self):
        """Inspection commands should use --flag <VALUE> form, not positional."""
        content = AGENTS_MD.read_text()
        expected = [
            "uv run cja_auto_sdr --describe-dataview <DATA_VIEW_ID_OR_NAME>",
            "uv run cja_auto_sdr --list-metrics <DATA_VIEW_ID_OR_NAME>",
            "uv run cja_auto_sdr --list-dimensions <DATA_VIEW_ID_OR_NAME>",
            "uv run cja_auto_sdr --list-segments <DATA_VIEW_ID_OR_NAME>",
            "uv run cja_auto_sdr --list-calculated-metrics <DATA_VIEW_ID_OR_NAME>",
        ]
        disallowed = [
            "uv run cja_auto_sdr <dv_id> --describe-dataview",
            "uv run cja_auto_sdr <dv_id> --list-metrics",
            "uv run cja_auto_sdr <dv_id> --list-dimensions",
            "uv run cja_auto_sdr <dv_id> --list-segments",
            "uv run cja_auto_sdr <dv_id> --list-calculated-metrics",
        ]
        for line in expected:
            assert line in content, f"Missing expected command form: {line}"
        for line in disallowed:
            assert line not in content, f"Found disallowed command form: {line}"

    def test_no_invalid_stdout_pair(self):
        """AGENTS.md should not document --run-summary-json - with --output - together."""
        content = AGENTS_MD.read_text()
        lines = content.split("\n")
        for line in lines:
            if "--run-summary-json -" in line and "--output -" in line:
                pytest.fail("AGENTS.md documents invalid --run-summary-json - + --output - pair")
