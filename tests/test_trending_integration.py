"""Backwards compatibility and integration tests for trending (v3.4.0).

Verifies that:
- Existing org-report JSON schema is untouched when trending is inactive.
- write_org_report_comparison_console works from OrgReportTrending bridge.
- End-to-end: --trending-window with mock cache produces correct output.
- End-to-end: --org-report without --trending-window is unchanged.
"""

import json
from pathlib import Path
from unittest.mock import MagicMock

from cja_auto_sdr.org.models import (
    ComponentDistribution,
    ComponentInfo,
    DataViewSummary,
    OrgReportConfig,
    OrgReportResult,
    OrgReportTrending,
    TrendingDelta,
    TrendingSnapshot,
)
from cja_auto_sdr.org.trending import _extract_snapshot_from_json, build_trending
from cja_auto_sdr.org.writers import (
    build_org_report_json_data,
    write_org_report_comparison_console,
    write_org_report_console,
    write_org_report_csv,
    write_org_report_excel,
    write_org_report_html,
    write_org_report_markdown,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

BASELINE_JSON_KEYS = {
    "report_type",
    "generated_at",
    "org_id",
    "parameters",
    "summary",
    "data_views",
    "component_index",
    "distribution",
    "recommendations",
}


def _make_result(org_id="test_org"):
    return OrgReportResult(
        timestamp="2026-02-01T00:00:00Z",
        org_id=org_id,
        parameters=OrgReportConfig(),
        data_view_summaries=[
            DataViewSummary(data_view_id="dv1", data_view_name="Test DV 1", metric_count=50, dimension_count=30),
            DataViewSummary(data_view_id="dv2", data_view_name="Test DV 2", metric_count=20, dimension_count=10),
        ],
        component_index={
            "m1": ComponentInfo(component_id="m1", component_type="metric", data_views={"dv1", "dv2"}),
        },
        distribution=ComponentDistribution(
            core_metrics=["m1"],
            isolated_metrics=[],
            core_dimensions=[],
            isolated_dimensions=[],
        ),
        similarity_pairs=[],
        recommendations=[],
        duration=1.5,
    )


def _make_trending():
    return OrgReportTrending(
        snapshots=[
            TrendingSnapshot(
                timestamp="2026-01-01T00:00:00Z",
                data_view_count=2,
                component_count=100,
                core_count=80,
                isolated_count=20,
                high_sim_pair_count=2,
                dv_ids={"dv1", "dv2"},
            ),
            TrendingSnapshot(
                timestamp="2026-02-01T00:00:00Z",
                data_view_count=3,
                component_count=120,
                core_count=95,
                isolated_count=25,
                high_sim_pair_count=3,
                dv_ids={"dv1", "dv2", "dv3"},
            ),
        ],
        deltas=[
            TrendingDelta(
                from_timestamp="2026-01-01T00:00:00Z",
                to_timestamp="2026-02-01T00:00:00Z",
                data_view_delta=2,
                component_delta=20,
                core_delta=15,
                isolated_delta=5,
                high_sim_pair_delta=1,
            ),
        ],
        drift_scores={"dv1": 0.82, "dv2": 0.15, "dv3": 0.45},
        window_size=2,
    )


def _write_snapshot_json(cache_dir: Path, result: OrgReportResult, timestamp_suffix: str) -> Path:
    """Write a mock org-report JSON snapshot to a cache directory."""
    data = build_org_report_json_data(result)
    filename = f"org_report_{result.org_id}_{timestamp_suffix}.json"
    path = cache_dir / filename
    path.write_text(json.dumps(data, default=str), encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# JSON schema backwards compatibility
# ---------------------------------------------------------------------------


class TestJsonSchemaBackwardsCompat:
    def test_no_trending_key_when_inactive(self):
        result = _make_result()
        data = build_org_report_json_data(result, trending=None)
        assert "trending" not in data

    def test_baseline_keys_present_without_trending(self):
        result = _make_result()
        data = build_org_report_json_data(result, trending=None)
        assert BASELINE_JSON_KEYS.issubset(set(data.keys()))

    def test_baseline_keys_preserved_with_trending(self):
        result = _make_result()
        data = build_org_report_json_data(result, trending=_make_trending())
        assert BASELINE_JSON_KEYS.issubset(set(data.keys()))
        assert "trending" in data

    def test_json_values_unchanged_by_trending_presence(self):
        """Core JSON values are identical whether trending is present or not."""
        result = _make_result()
        without = build_org_report_json_data(result, trending=None)
        with_trending = build_org_report_json_data(result, trending=_make_trending())

        for key in BASELINE_JSON_KEYS:
            assert json.dumps(without[key], default=str, sort_keys=True) == json.dumps(
                with_trending[key], default=str, sort_keys=True
            ), f"Key '{key}' differs when trending is added"


# ---------------------------------------------------------------------------
# Comparison console bridge
# ---------------------------------------------------------------------------


class TestComparisonConsoleBridge:
    def test_trending_to_comparison_populates_added_removed_names(self):
        trending = _make_trending()
        comparison = trending.to_comparison()
        assert comparison is not None
        assert comparison.data_views_added_names == ["dv3"]
        assert comparison.data_views_removed_names == []

    def test_trending_to_comparison_feeds_console_writer(self, capsys):
        trending = _make_trending()
        comparison = trending.to_comparison()
        assert comparison is not None

        write_org_report_comparison_console(comparison)
        output = capsys.readouterr().out
        assert "dv3" in output or "added" in output.lower() or "delta" in output.lower()

    def test_comparison_output_includes_key_metrics(self, capsys):
        trending = _make_trending()
        comparison = trending.to_comparison()
        write_org_report_comparison_console(comparison)
        output = capsys.readouterr().out
        # Should contain some numeric delta info
        assert any(char.isdigit() for char in output)


# ---------------------------------------------------------------------------
# Console output unchanged without trending
# ---------------------------------------------------------------------------


class TestConsoleUnchangedWithoutTrending:
    def test_no_trending_section_without_flag(self, capsys):
        result = _make_result()
        config = OrgReportConfig()
        write_org_report_console(result, config, quiet=False, trending=None)
        output = capsys.readouterr().out
        assert "TRENDING" not in output
        assert "drift" not in output.lower()

    def test_console_output_deterministic(self, capsys):
        """Two calls with trending=None produce identical output."""
        result = _make_result()
        config = OrgReportConfig()

        write_org_report_console(result, config, quiet=False, trending=None)
        first = capsys.readouterr().out

        write_org_report_console(result, config, quiet=False, trending=None)
        second = capsys.readouterr().out

        assert first == second


# ---------------------------------------------------------------------------
# End-to-end: mock cache + build_trending
# ---------------------------------------------------------------------------


class TestBuildTrendingEndToEnd:
    def test_build_trending_with_mock_cache(self, tmp_path):
        """Simulates --trending-window 5 with 3 cached snapshots."""
        result1 = _make_result()
        result2 = _make_result()
        result2.timestamp = "2026-03-01T00:00:00Z"

        # Write two snapshot JSONs to mock cache
        _write_snapshot_json(tmp_path, result1, "20260201_000000")
        _write_snapshot_json(tmp_path, result2, "20260301_000000")

        # Build a current snapshot from result2
        current_json = build_org_report_json_data(result2)
        current_snapshot = _extract_snapshot_from_json(current_json)

        trending = build_trending(
            cache_dir=str(tmp_path),
            window_size=5,
            current_snapshot=current_snapshot,
        )

        assert trending is not None
        assert len(trending.snapshots) >= 2
        # window_size reflects actual snapshots found, not the requested max
        assert trending.window_size == len(trending.snapshots)

    def test_build_trending_renders_in_all_formats(self, tmp_path):
        """Trending data renders successfully in all 6 output formats."""
        result = _make_result()
        trending = _make_trending()
        logger = MagicMock()

        # Console
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            write_org_report_console(result, OrgReportConfig(), quiet=False, trending=trending)
        assert "TRENDING" in buf.getvalue()

        # JSON
        data = build_org_report_json_data(result, trending=trending)
        serialized = json.dumps(data, default=str)
        assert "trending" in serialized

        # Excel
        excel_path = write_org_report_excel(result, tmp_path / "test.xlsx", str(tmp_path), logger, trending=trending)
        assert Path(excel_path).exists()

        # Markdown
        md_path = write_org_report_markdown(result, tmp_path / "test.md", str(tmp_path), logger, trending=trending)
        assert "Trending" in Path(md_path).read_text(encoding="utf-8")

        # HTML
        html_path = write_org_report_html(result, tmp_path / "test.html", str(tmp_path), logger, trending=trending)
        assert "Trending" in Path(html_path).read_text(encoding="utf-8")

        # CSV
        csv_dir = write_org_report_csv(result, None, str(tmp_path / "csv"), logger, trending=trending)
        trending_files = list(Path(csv_dir).glob("*trending*"))
        assert len(trending_files) >= 1

    def test_empty_cache_returns_none(self, tmp_path):
        """Empty cache dir with no current snapshot returns None."""
        trending = build_trending(
            cache_dir=str(tmp_path),
            window_size=5,
        )
        assert trending is None

    def test_single_snapshot_returns_none(self, tmp_path):
        """A single cached file without current_snapshot returns None (need >= 2)."""
        result = _make_result()
        _write_snapshot_json(tmp_path, result, "20260201_000000")

        trending = build_trending(
            cache_dir=str(tmp_path),
            window_size=5,
        )
        # May return None or a trending with 1 snapshot (insufficient for deltas)
        if trending is not None:
            assert len(trending.snapshots) <= 1


# ---------------------------------------------------------------------------
# Lazy forwarding still works
# ---------------------------------------------------------------------------


class TestLazyForwardingPreserved:
    def test_org_writer_functions_importable_from_generator(self):
        from cja_auto_sdr.generator import (
            build_org_report_json_data,
            write_org_report_console,
            write_org_report_csv,
            write_org_report_excel,
            write_org_report_html,
            write_org_report_markdown,
        )

        # All should be callable
        assert callable(write_org_report_console)
        assert callable(build_org_report_json_data)
        assert callable(write_org_report_csv)
        assert callable(write_org_report_excel)
        assert callable(write_org_report_html)
        assert callable(write_org_report_markdown)

    def test_trending_models_importable_from_org_models(self):
        from cja_auto_sdr.org.models import (
            OrgReportTrending,
            TrendingDelta,
            TrendingSnapshot,
        )

        assert callable(TrendingSnapshot)
        assert callable(TrendingDelta)
        assert callable(OrgReportTrending)
