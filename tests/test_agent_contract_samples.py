"""Lightweight validation of representative sample_outputs/agent/ contract fixtures."""

from __future__ import annotations

import json
from pathlib import Path

SAMPLES_DIR = Path(__file__).resolve().parent.parent / "sample_outputs" / "agent"


class TestAgentContractSamples:
    """Validate structural expectations of agent contract fixtures."""

    def test_readme_exists(self):
        assert (SAMPLES_DIR / "README.md").exists()

    def test_discovery_fixture_has_dataviews(self):
        data = json.loads((SAMPLES_DIR / "sample_list_dataviews_agent_mode.json").read_text())
        assert "dataViews" in data
        assert isinstance(data["dataViews"], list)
        assert len(data["dataViews"]) > 0
        assert "id" in data["dataViews"][0]

    def test_org_report_fixture_has_advisories(self):
        data = json.loads((SAMPLES_DIR / "sample_org_report_with_advisories.json").read_text())
        assert "advisories" in data
        adv = data["advisories"]
        assert adv["advisories_version"] == "1.0"
        assert "severity" in adv
        assert "findings" in adv
        assert "summary" in adv

    def test_diff_fixture_has_advisories(self):
        data = json.loads((SAMPLES_DIR / "sample_diff_with_advisories.json").read_text())
        assert "advisories" in data
        adv = data["advisories"]
        assert adv["advisories_version"] == "1.0"
        assert "severity" in adv
        assert "findings" in adv
        assert "summary" in adv

    def test_run_summary_fixture_has_details_advisories(self):
        data = json.loads((SAMPLES_DIR / "sample_run_summary_with_advisories.json").read_text())
        assert "details" in data
        assert "advisories" in data["details"]
        adv = data["details"]["advisories"]
        assert "advisories_version" in adv
        assert "types" in adv
        assert "recommended_actions" in adv

    def test_fixtures_are_small(self):
        """Contract fixtures should be intentionally small."""
        for path in SAMPLES_DIR.glob("*.json"):
            content = path.read_text()
            assert len(content) < 5000, f"{path.name} is too large for a contract fixture"
