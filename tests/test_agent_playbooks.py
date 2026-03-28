# tests/test_agent_playbooks.py
"""Tests for docs/agent-playbooks/ cross-agent task playbooks."""

from __future__ import annotations

from pathlib import Path

import pytest

PLAYBOOKS_DIR = Path(__file__).resolve().parent.parent / "docs" / "agent-playbooks"

REQUIRED_PLAYBOOKS = [
    "sdr-auditor.md",
    "diff-reviewer.md",
    "onboarding-guide.md",
    "quality-monitor.md",
    "snapshot-manager.md",
]

REQUIRED_SECTIONS = [
    "## Purpose",
    "## When To Use",
    "## Inputs",
    "## Constraints",
    "## Primary CLI Flows",
    "## Success Criteria",
    "## Follow-Up Actions",
]


class TestAgentPlaybooks:
    """Validate playbook structure and content."""

    def test_readme_exists(self):
        assert (PLAYBOOKS_DIR / "README.md").exists()

    def test_template_exists(self):
        assert (PLAYBOOKS_DIR / "TEMPLATE.md").exists()

    @pytest.fixture(params=REQUIRED_PLAYBOOKS)
    def playbook_path(self, request):
        return PLAYBOOKS_DIR / request.param

    def test_playbook_exists(self, playbook_path):
        assert playbook_path.exists(), f"Missing playbook: {playbook_path.name}"

    def test_playbook_has_required_sections(self, playbook_path):
        content = playbook_path.read_text()
        for section in REQUIRED_SECTIONS:
            assert section in content, f"Missing '{section}' in {playbook_path.name}"

    def test_playbook_sections_have_content(self, playbook_path):
        content = playbook_path.read_text()
        lines = content.split("\n")
        for section in REQUIRED_SECTIONS:
            try:
                idx = next(i for i, line in enumerate(lines) if line.strip() == section)
            except StopIteration:
                pytest.fail(f"Missing '{section}' in {playbook_path.name}")
            remaining = [line for line in lines[idx + 1 :] if line.strip()]
            assert remaining, f"Empty section '{section}' in {playbook_path.name}"
            if remaining[0].startswith("## "):
                pytest.fail(f"Empty section '{section}' in {playbook_path.name}")

    def test_playbook_links_to_agents_md(self, playbook_path):
        content = playbook_path.read_text()
        assert "AGENTS.md" in content, f"{playbook_path.name} must link to AGENTS.md"

    def test_unattended_examples_are_id_first(self, playbook_path):
        """Unattended automation examples should use exact IDs, not names."""
        content = playbook_path.read_text()
        lines = content.split("\n")
        for i, line in enumerate(lines):
            if "uv run cja_auto_sdr" in line and "--agent-mode" in line:
                # If it references a data view, it should use ID format
                # Allow <dv_id>, <DATA_VIEW_ID>, dv_..., or $DV_ID variable patterns
                if "my_data_view_name" in line.lower():
                    pytest.fail(f"Line {i + 1} in {playbook_path.name}: unattended example uses name instead of ID")
