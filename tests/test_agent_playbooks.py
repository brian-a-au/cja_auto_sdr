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

    def test_playbooks_use_current_credential_env_names(self):
        for name in REQUIRED_PLAYBOOKS:
            content = (PLAYBOOKS_DIR / name).read_text()
            assert "CJA_CLIENT_ID" not in content
            assert "CJA_CLIENT_SECRET" not in content
            assert "CJA_ORG_ID" not in content

    def test_diff_reviewer_uses_compare_snapshots_for_snapshot_files(self):
        content = (PLAYBOOKS_DIR / "diff-reviewer.md").read_text()
        assert "--compare-snapshots" in content
        assert "--diff baseline current" not in content

    def test_playbooks_do_not_document_fail_on_advisory(self):
        for name in REQUIRED_PLAYBOOKS:
            content = (PLAYBOOKS_DIR / name).read_text()
            assert "--fail-on-advisory" not in content

    def test_quality_monitor_and_sdr_auditor_do_not_mix_org_report_with_fail_on_quality(self):
        for name in ["quality-monitor.md", "sdr-auditor.md"]:
            content = (PLAYBOOKS_DIR / name).read_text()
            assert "--org-report --agent-mode \\\n  --fail-on-quality" not in content

    def test_diff_reviewer_describes_current_diff_json_shape(self):
        content = (PLAYBOOKS_DIR / "diff-reviewer.md").read_text()
        assert "summary.has_changes" in content
        assert "metric_diffs" in content
        assert "dimension_diffs" in content
        assert "advisories.findings" in content
        assert "diff.changes" not in content
        assert "breaking_changes_count" not in content

    def test_snapshot_related_playbooks_describe_trending_window_as_snapshot_count(self):
        for name in ["diff-reviewer.md", "snapshot-manager.md", "sdr-auditor.md"]:
            content = (PLAYBOOKS_DIR / name).read_text().lower()
            if "--trending-window" in content:
                assert "cached org-report snapshots" in content or "snapshot window" in content

    def test_onboarding_guide_uses_current_profile_creation_flow(self):
        content = (PLAYBOOKS_DIR / "onboarding-guide.md").read_text()
        assert "--profile-add production" in content
        assert "--config --profile production" not in content

    def test_playbooks_do_not_document_exit_64(self):
        for name in REQUIRED_PLAYBOOKS:
            content = (PLAYBOOKS_DIR / name).read_text()
            assert "Exit 64" not in content

    def test_quality_monitor_uses_supported_quality_severities(self):
        content = (PLAYBOOKS_DIR / "quality-monitor.md").read_text()
        assert 'Severity == "WARNING"' not in content
        for severity in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]:
            assert f'Severity == "{severity}"' in content

    def test_diff_reviewer_treats_warn_threshold_exit_as_completed_comparison(self):
        content = (PLAYBOOKS_DIR / "diff-reviewer.md").read_text()
        assert "Exit code 0, 2, or 3" in content

    def test_sdr_auditor_default_org_report_flow_does_not_claim_exit_2(self):
        content = (PLAYBOOKS_DIR / "sdr-auditor.md").read_text()
        assert "Exit 2 — configured governance threshold exceeded." not in content
        assert (
            "If `--fail-on-threshold` is used, exit code 2 indicates a configured governance threshold breach."
            in content
        )
