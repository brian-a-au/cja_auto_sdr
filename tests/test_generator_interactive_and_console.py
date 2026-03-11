"""Coverage-focused tests for interactive and org-report console helpers."""

from __future__ import annotations

import json
import logging
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from cja_auto_sdr import generator
from cja_auto_sdr.core.exceptions import CJASDRError
from cja_auto_sdr.org.cache import DEFAULT_ORG_REPORT_SNAPSHOT_KEEP_LAST, OrgReportCache
from cja_auto_sdr.org.models import ComponentInfo, OrgReportComparison, OrgReportConfig
from cja_auto_sdr.org.writers import build_org_report_json_data


def _mock_data_views() -> list[dict[str, object]]:
    return [
        {"id": "dv_001", "name": "Marketing DV", "owner": {"name": "Alice"}},
        {"id": "dv_002", "name": "Product DV", "owner": {"name": "Bob"}},
        {"id": "dv_003", "name": "Finance DV", "owner": {"name": "Carol"}},
    ]


@patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
@patch("cja_auto_sdr.generator.cjapy")
def test_interactive_select_dataviews_retries_and_parses_ranges(mock_cjapy: Mock, _mock_config: Mock):
    mock_cja = Mock()
    mock_cja.getDataViews.return_value = _mock_data_views()
    mock_cjapy.CJA.return_value = mock_cja

    with patch("builtins.input", side_effect=["", "1-a", "10", "1,2-3"]):
        selected = generator.interactive_select_dataviews(profile="dev")

    assert selected == ["dv_001", "dv_002", "dv_003"]


@patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
@patch("cja_auto_sdr.generator.cjapy")
def test_interactive_select_dataviews_cancelled(mock_cjapy: Mock, _mock_config: Mock):
    mock_cja = Mock()
    mock_cja.getDataViews.return_value = _mock_data_views()
    mock_cjapy.CJA.return_value = mock_cja

    with patch("builtins.input", side_effect=["q"]):
        assert generator.interactive_select_dataviews(profile="dev") == []


@patch("cja_auto_sdr.generator.configure_cjapy", return_value=(False, "bad credentials", None))
def test_interactive_select_dataviews_config_failure(_mock_config: Mock):
    assert generator.interactive_select_dataviews(config_file="bad.json") == []


@patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
@patch("cja_auto_sdr.generator.cjapy")
def test_interactive_wizard_full_flow_with_retries(mock_cjapy: Mock, _mock_config: Mock):
    mock_cja = Mock()
    mock_cja.getDataViews.return_value = _mock_data_views()
    mock_cjapy.CJA.return_value = mock_cja

    user_inputs = [
        "",
        "2-1,5",
        "1,2",
        "99",
        "",
        "maybe",
        "y",
        "n",
        "",
        "",
    ]
    with patch("builtins.input", side_effect=user_inputs):
        result = generator.interactive_wizard(profile="dev")

    assert result is not None
    assert result.data_view_ids == ["dv_001", "dv_002"]
    assert result.output_format == "excel"
    assert result.include_segments is True
    assert result.include_calculated is False
    assert result.include_derived is False


@patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None))
@patch("cja_auto_sdr.generator.cjapy")
def test_interactive_wizard_cancelled_at_confirmation(mock_cjapy: Mock, _mock_config: Mock):
    mock_cja = Mock()
    mock_cja.getDataViews.return_value = _mock_data_views()
    mock_cjapy.CJA.return_value = mock_cja

    user_inputs = ["1", "1", "n", "n", "n", "n"]
    with patch("builtins.input", side_effect=user_inputs):
        assert generator.interactive_wizard(profile="dev") is None


@patch("cja_auto_sdr.generator.configure_cjapy", return_value=(False, "bad credentials", None))
def test_interactive_wizard_config_failure(_mock_config: Mock):
    assert generator.interactive_wizard(config_file="bad.json") is None


def test_write_org_report_console_renders_all_major_sections(capsys, rich_org_report_result):
    result = rich_org_report_result
    generator.write_org_report_console(result, result.parameters, quiet=False)
    output = capsys.readouterr().out

    assert "ORG-WIDE COMPONENT ANALYSIS REPORT" in output
    assert "[SAMPLED]" in output
    assert "DATA VIEWS" in output
    assert "COMPONENT SUMMARY" in output
    assert "HIGH OVERLAP PAIRS" in output
    assert "DATA VIEW CLUSTERS" in output
    assert "GOVERNANCE VIOLATIONS" in output
    assert "OWNER SUMMARY" in output
    assert "NAMING AUDIT" in output
    assert "STALE COMPONENTS" in output
    assert "RECOMMENDATIONS" in output


def test_write_org_report_stats_and_comparison_consoles(capsys, rich_org_report_result):
    result = rich_org_report_result
    generator.write_org_report_stats_only(result, quiet=False)

    comparison = OrgReportComparison(
        current_timestamp="2026-02-16T12:00:00+00:00",
        previous_timestamp="2026-02-01T12:00:00+00:00",
        data_views_added=["dv_new_1", "dv_new_2", "dv_new_3", "dv_new_4", "dv_new_5", "dv_new_6"],
        data_views_removed=["dv_old_1", "dv_old_2", "dv_old_3", "dv_old_4", "dv_old_5", "dv_old_6"],
        data_views_added_names=["New 1", "New 2", "New 3", "New 4", "New 5", "New 6"],
        data_views_removed_names=["Old 1", "Old 2", "Old 3", "Old 4", "Old 5", "Old 6"],
        new_high_similarity_pairs=[{"dv1_id": "dv_a", "dv2_id": "dv_b"}],
        resolved_pairs=[{"dv1_id": "dv_x", "dv2_id": "dv_y"}],
        summary={"data_views_delta": 5, "components_delta": -3, "core_delta": 2, "isolated_delta": 0},
    )
    generator.write_org_report_comparison_console(comparison, quiet=False)
    output = capsys.readouterr().out

    assert "ORG STATS" in output
    assert "ORG REPORT COMPARISON (TRENDING)" in output
    assert "Data Views Added" in output
    assert "Resolved High-Similarity Pairs" in output


def test_write_org_report_file_outputs_all_formats(tmp_path: Path, rich_org_report_result):
    result = rich_org_report_result
    logger = logging.getLogger("test_org_report_outputs")

    json_path = generator.write_org_report_json(result, tmp_path / "org_report", str(tmp_path), logger)
    excel_path = generator.write_org_report_excel(result, tmp_path / "org_report", str(tmp_path), logger)
    markdown_path = generator.write_org_report_markdown(result, tmp_path / "org_report", str(tmp_path), logger)
    html_path = generator.write_org_report_html(result, tmp_path / "org_report", str(tmp_path), logger)
    csv_dir = generator.write_org_report_csv(result, tmp_path / "org_report.csv", str(tmp_path), logger)

    assert Path(json_path).exists()
    assert Path(excel_path).exists()
    assert Path(markdown_path).exists()
    assert Path(html_path).exists()
    assert Path(csv_dir).is_dir()
    assert (Path(csv_dir) / "org_report_summary.csv").exists()
    assert (Path(csv_dir) / "org_report_data_views.csv").exists()
    assert (Path(csv_dir) / "org_report_components.csv").exists()
    assert (Path(csv_dir) / "org_report_distribution.csv").exists()
    assert (Path(csv_dir) / "org_report_similarity.csv").exists()
    assert (Path(csv_dir) / "org_report_recommendations.csv").exists()


def test_org_report_branches_for_core_min_count_and_quiet_modes(capsys, rich_org_report_result):
    result = rich_org_report_result
    result.parameters.core_min_count = 2
    result.is_sampled = False

    comparison = OrgReportComparison(
        current_timestamp="2026-02-16T12:00:00+00:00",
        previous_timestamp="2026-02-15T12:00:00+00:00",
        summary={"data_views_delta": 0, "components_delta": 0, "core_delta": 0, "isolated_delta": 0},
    )

    generator.write_org_report_console(result, result.parameters, quiet=False)
    out = capsys.readouterr().out
    assert "Core (in >=2 DVs)" in out
    assert "Data Views Analyzed: 2 / 3" in out

    generator.write_org_report_stats_only(result, quiet=True)
    generator.write_org_report_comparison_console(comparison, quiet=True)


def test_run_org_report_all_formats_branch(tmp_path: Path, rich_org_report_result):
    result = rich_org_report_result
    result.thresholds_exceeded = True
    result.governance_violations = [{"message": "threshold exceeded"}]
    org_config = OrgReportConfig(fail_on_threshold=True)

    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer_cls,
        patch("cja_auto_sdr.generator.write_org_report_console") as mock_console,
        patch("cja_auto_sdr.generator.write_org_report_json", return_value=str(tmp_path / "report.json")) as mock_json,
        patch(
            "cja_auto_sdr.generator.write_org_report_excel",
            return_value=str(tmp_path / "report.xlsx"),
        ) as mock_excel,
        patch(
            "cja_auto_sdr.generator.write_org_report_markdown",
            return_value=str(tmp_path / "report.md"),
        ) as mock_markdown,
        patch("cja_auto_sdr.generator.write_org_report_html", return_value=str(tmp_path / "report.html")) as mock_html,
        patch("cja_auto_sdr.generator.write_org_report_csv", return_value=str(tmp_path / "report_csv")) as mock_csv,
        patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary"),
        patch("cja_auto_sdr.generator.append_github_step_summary") as mock_append_summary,
    ):
        mock_cjapy.CJA.return_value = Mock()
        mock_analyzer = Mock()
        mock_analyzer.run_analysis.return_value = result
        mock_analyzer_cls.return_value = mock_analyzer

        success, thresholds_exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="all",
            output_path=str(tmp_path / "org_output"),
            output_dir=str(tmp_path),
            org_config=org_config,
            profile="dev",
            quiet=False,
        )

    assert success is True
    assert thresholds_exceeded is True
    mock_console.assert_called_once()
    mock_json.assert_called_once()
    mock_excel.assert_called_once()
    mock_markdown.assert_called_once()
    mock_html.assert_called_once()
    mock_csv.assert_called_once()
    mock_append_summary.assert_called_once()


def test_run_org_report_stats_only_and_csv_stdout_guard(tmp_path: Path, rich_org_report_result):
    result = rich_org_report_result

    stats_config = OrgReportConfig(org_stats_only=True)
    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer_cls,
        patch("cja_auto_sdr.generator.write_org_report_stats_only") as mock_stats_only,
        patch("cja_auto_sdr.generator.write_org_report_json", return_value=str(tmp_path / "stats.json")) as mock_json,
        patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary"),
        patch("cja_auto_sdr.generator.append_github_step_summary"),
    ):
        mock_cjapy.CJA.return_value = Mock()
        mock_analyzer = Mock()
        mock_analyzer.run_analysis.return_value = result
        mock_analyzer_cls.return_value = mock_analyzer

        success, thresholds_exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="json",
            output_path=str(tmp_path / "org_stats"),
            output_dir=str(tmp_path),
            org_config=stats_config,
            profile=None,
            quiet=False,
        )

    assert success is True
    assert thresholds_exceeded is False
    mock_stats_only.assert_called_once()
    mock_json.assert_called_once()

    csv_config = OrgReportConfig()
    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer_cls,
        patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary"),
        patch("cja_auto_sdr.generator.append_github_step_summary"),
    ):
        mock_cjapy.CJA.return_value = Mock()
        mock_analyzer = Mock()
        mock_analyzer.run_analysis.return_value = result
        mock_analyzer_cls.return_value = mock_analyzer

        success, thresholds_exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="csv",
            output_path="stdout",
            output_dir=str(tmp_path),
            org_config=csv_config,
            quiet=False,
        )

    assert success is False
    assert thresholds_exceeded is False


def test_run_org_report_reports_alias_and_individual_format_branches(tmp_path: Path, rich_org_report_result):
    result = rich_org_report_result
    base_output = tmp_path / "org_report_out"

    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "cja_auto_sdr.generator.configure_cjapy",
                return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"}),
            ),
        )
        mock_cjapy = stack.enter_context(patch("cja_auto_sdr.generator.cjapy"))
        mock_analyzer_cls = stack.enter_context(patch("cja_auto_sdr.generator.OrgComponentAnalyzer"))
        stack.enter_context(patch("cja_auto_sdr.generator.write_org_report_console", return_value=None))
        stack.enter_context(
            patch("cja_auto_sdr.generator.write_org_report_json", return_value=str(tmp_path / "report.json")),
        )
        stack.enter_context(
            patch("cja_auto_sdr.generator.write_org_report_excel", return_value=str(tmp_path / "report.xlsx")),
        )
        stack.enter_context(
            patch("cja_auto_sdr.generator.write_org_report_markdown", return_value=str(tmp_path / "report.md")),
        )
        stack.enter_context(
            patch("cja_auto_sdr.generator.write_org_report_html", return_value=str(tmp_path / "report.html")),
        )
        stack.enter_context(
            patch("cja_auto_sdr.generator.write_org_report_csv", return_value=str(tmp_path / "report_csv")),
        )
        stack.enter_context(patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary"))
        stack.enter_context(patch("cja_auto_sdr.generator.append_github_step_summary"))

        mock_cjapy.CJA.return_value = Mock()
        analyzer = Mock()
        analyzer.run_analysis.return_value = result
        mock_analyzer_cls.return_value = analyzer

        # Alias branch
        ok, exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="reports",
            output_path=str(base_output),
            output_dir=str(tmp_path),
            org_config=OrgReportConfig(),
            quiet=False,
        )
        assert ok is True
        assert exceeded is False

        # Single-format branches
        for fmt in ("console", "json", "excel", "markdown", "html", "csv"):
            ok, exceeded = generator.run_org_report(
                config_file="config.json",
                output_format=fmt,
                output_path=str(base_output),
                output_dir=str(tmp_path),
                org_config=OrgReportConfig(),
                quiet=False,
            )
            assert ok is True
            assert exceeded is False


def test_run_org_report_cache_and_comparison_error_paths(tmp_path: Path, rich_org_report_result):
    result = rich_org_report_result
    config = OrgReportConfig(use_cache=True, compare_org_report="missing_previous.json")

    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        patch("cja_auto_sdr.generator.OrgReportCache") as mock_cache_cls,
        patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer_cls,
        patch("cja_auto_sdr.generator.compare_org_reports", side_effect=FileNotFoundError),
        patch("cja_auto_sdr.generator.write_org_report_console"),
        patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary"),
        patch("cja_auto_sdr.generator.append_github_step_summary"),
    ):
        mock_cjapy.CJA.return_value = Mock()
        cache = Mock()
        cache.get_stats.return_value = {"entries": 3}
        mock_cache_cls.return_value = cache

        analyzer = Mock()
        analyzer.run_analysis.return_value = result
        mock_analyzer_cls.return_value = analyzer

        ok, exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=config,
            quiet=False,
        )

    assert ok is True
    assert exceeded is False


def test_run_org_report_trending_window_uses_persistent_snapshot_cache(tmp_path: Path, rich_org_report_result):
    first_result = deepcopy(rich_org_report_result)
    first_result.timestamp = "2026-02-01T00:00:00Z"
    first_result.org_id = "test_org@AdobeOrg"
    first_result.is_sampled = False

    second_result = deepcopy(rich_org_report_result)
    second_result.timestamp = "2026-03-01T00:00:00Z"
    second_result.org_id = "test_org@AdobeOrg"
    second_result.is_sampled = False

    snapshot_cache_root = tmp_path / "cache"

    def _cache_factory(*args, **kwargs):
        return OrgReportCache(cache_dir=snapshot_cache_root, logger=kwargs.get("logger"))

    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        patch("cja_auto_sdr.generator.OrgReportCache", side_effect=_cache_factory),
        patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer_cls,
        patch("cja_auto_sdr.generator.write_org_report_console") as mock_console,
        patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary"),
        patch("cja_auto_sdr.generator.append_github_step_summary"),
    ):
        mock_cjapy.CJA.return_value = Mock()
        analyzer = Mock()
        analyzer.run_analysis.side_effect = [first_result, second_result]
        mock_analyzer_cls.return_value = analyzer

        ok1, exceeded1 = generator.run_org_report(
            config_file="config.json",
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path / "run_one"),
            org_config=OrgReportConfig(),
            quiet=False,
            trending_window=3,
        )
        ok2, exceeded2 = generator.run_org_report(
            config_file="config.json",
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path / "run_two"),
            org_config=OrgReportConfig(),
            quiet=False,
            trending_window=3,
        )

    assert ok1 is True
    assert exceeded1 is False
    assert ok2 is True
    assert exceeded2 is False
    assert mock_console.call_count == 2

    first_trending = mock_console.call_args_list[0].kwargs.get("trending")
    second_trending = mock_console.call_args_list[1].kwargs.get("trending")
    assert first_trending is None
    assert second_trending is not None
    assert second_trending.window_size == 2

    snapshot_dir = OrgReportCache(cache_dir=snapshot_cache_root).get_org_report_snapshot_dir("test_org@AdobeOrg")
    assert len(list(snapshot_dir.glob("*.json"))) == 2


def test_run_org_report_trending_window_includes_legacy_snapshot_history(tmp_path: Path, rich_org_report_result):
    baseline = deepcopy(rich_org_report_result)
    baseline.timestamp = "2026-02-01T00:00:00Z"
    baseline.org_id = "test_org@AdobeOrg"
    baseline.is_sampled = False

    current = deepcopy(rich_org_report_result)
    current.timestamp = "2026-03-01T00:00:00Z"
    current.org_id = "test_org@AdobeOrg"
    current.is_sampled = False

    snapshot_cache_root = tmp_path / "cache"
    cache = OrgReportCache(cache_dir=snapshot_cache_root)
    legacy_dir = cache.get_org_report_snapshot_root_dir() / "test_org_AdobeOrg"
    legacy_dir.mkdir(parents=True, exist_ok=True)
    legacy_path = legacy_dir / "baseline.json"
    legacy_path.write_text(json.dumps(build_org_report_json_data(baseline)), encoding="utf-8")

    def _cache_factory(*args, **kwargs):
        return OrgReportCache(cache_dir=snapshot_cache_root, logger=kwargs.get("logger"))

    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        patch("cja_auto_sdr.generator.OrgReportCache", side_effect=_cache_factory),
        patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer_cls,
        patch("cja_auto_sdr.generator.write_org_report_console") as mock_console,
        patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary"),
        patch("cja_auto_sdr.generator.append_github_step_summary"),
    ):
        mock_cjapy.CJA.return_value = Mock()
        analyzer = Mock()
        analyzer.run_analysis.return_value = current
        mock_analyzer_cls.return_value = analyzer

        ok, exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path / "run"),
            org_config=OrgReportConfig(),
            quiet=False,
            trending_window=3,
        )

    assert ok is True
    assert exceeded is False

    trending = mock_console.call_args.kwargs.get("trending")
    assert trending is not None
    assert [snapshot.timestamp for snapshot in trending.snapshots] == ["2026-02-01T00:00:00Z", "2026-03-01T00:00:00Z"]
    assert trending.snapshots[0].source_path == str(legacy_path.resolve(strict=False))


def test_run_org_report_trending_window_prunes_snapshot_history(tmp_path: Path, rich_org_report_result):
    result = deepcopy(rich_org_report_result)
    result.timestamp = "2026-03-01T00:00:00Z"
    result.org_id = "test_org@AdobeOrg"
    result.is_sampled = False

    snapshot_cache_root = tmp_path / "cache"

    def _cache_factory(*args, **kwargs):
        return OrgReportCache(cache_dir=snapshot_cache_root, logger=kwargs.get("logger"))

    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        patch("cja_auto_sdr.generator.OrgReportCache", side_effect=_cache_factory),
        patch.object(OrgReportCache, "prune_org_report_snapshots", return_value=[]) as mock_prune,
        patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer_cls,
        patch("cja_auto_sdr.generator.write_org_report_console"),
        patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary"),
        patch("cja_auto_sdr.generator.append_github_step_summary"),
    ):
        mock_cjapy.CJA.return_value = Mock()
        analyzer = Mock()
        analyzer.run_analysis.return_value = result
        mock_analyzer_cls.return_value = analyzer

        ok, exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=OrgReportConfig(),
            quiet=False,
            trending_window=3,
        )

    assert ok is True
    assert exceeded is False
    mock_prune.assert_called_once()
    assert mock_prune.call_args.kwargs["org_id"] == "test_org@AdobeOrg"
    assert mock_prune.call_args.kwargs["keep_last"] == max(DEFAULT_ORG_REPORT_SNAPSHOT_KEEP_LAST, 3)
    assert len(mock_prune.call_args.kwargs["preserved_snapshot_paths"]) == 1


def test_run_org_report_trending_window_pins_compare_baseline_into_window(tmp_path: Path, rich_org_report_result):
    current = deepcopy(rich_org_report_result)
    current.timestamp = "2026-03-01T00:00:00Z"
    current.org_id = "test_org@AdobeOrg"
    current.is_sampled = False

    snapshot_cache_root = tmp_path / "cache"
    cache = OrgReportCache(cache_dir=snapshot_cache_root)
    for day in range(2, DEFAULT_ORG_REPORT_SNAPSHOT_KEEP_LAST + 7):
        baseline_result = deepcopy(rich_org_report_result)
        baseline_result.timestamp = f"2026-01-{day:02d}T00:00:00Z"
        baseline_result.org_id = "test_org@AdobeOrg"
        baseline_result.is_sampled = False
        cache.save_org_report_snapshot(build_org_report_json_data(baseline_result), org_id=baseline_result.org_id)

    explicit_dir = tmp_path / "explicit"
    explicit_dir.mkdir()
    explicit_baseline = explicit_dir / "baseline.json"
    explicit_baseline_result = deepcopy(rich_org_report_result)
    explicit_baseline_result.timestamp = "2026-01-01T00:00:00Z"
    explicit_baseline_result.org_id = "test_org@AdobeOrg"
    explicit_baseline_result.is_sampled = False
    explicit_baseline.write_text(
        json.dumps(build_org_report_json_data(explicit_baseline_result)),
        encoding="utf-8",
    )

    def _cache_factory(*args, **kwargs):
        return OrgReportCache(cache_dir=snapshot_cache_root, logger=kwargs.get("logger"))

    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        patch("cja_auto_sdr.generator.OrgReportCache", side_effect=_cache_factory),
        patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer_cls,
        patch("cja_auto_sdr.generator.write_org_report_console") as mock_console,
        patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary"),
        patch("cja_auto_sdr.generator.append_github_step_summary"),
    ):
        mock_cjapy.CJA.return_value = Mock()
        analyzer = Mock()
        analyzer.run_analysis.return_value = current
        mock_analyzer_cls.return_value = analyzer

        ok, exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=OrgReportConfig(compare_org_report=str(explicit_baseline)),
            quiet=False,
            trending_window=3,
        )

    assert ok is True
    assert exceeded is False
    trending = mock_console.call_args.kwargs.get("trending")
    assert trending is not None
    assert trending.window_size == 3
    assert str(explicit_baseline.resolve(strict=False)) in {snapshot.source_path for snapshot in trending.snapshots}
    assert trending.snapshots[0].timestamp == "2026-01-01T00:00:00Z"
    assert trending.snapshots[-1].timestamp == "2026-03-01T00:00:00Z"
    assert explicit_baseline.exists()


def test_run_org_report_trending_window_deduplicates_explicit_previous_trending_report(
    tmp_path: Path, rich_org_report_result
):
    baseline = deepcopy(rich_org_report_result)
    baseline.timestamp = "2026-02-01T00:00:00Z"
    baseline.org_id = "test_org@AdobeOrg"
    baseline.is_sampled = False

    current = deepcopy(rich_org_report_result)
    current.timestamp = "2026-03-01T00:00:00Z"
    current.org_id = "test_org@AdobeOrg"
    current.is_sampled = False

    snapshot_cache_root = tmp_path / "cache"
    cache = OrgReportCache(cache_dir=snapshot_cache_root)
    cache.save_org_report_snapshot(build_org_report_json_data(baseline), org_id=baseline.org_id)

    explicit_dir = tmp_path / "explicit"
    explicit_dir.mkdir()
    explicit_payload = build_org_report_json_data(baseline)
    explicit_payload["trending"] = {
        "window_size": 2,
        "snapshots": [{"timestamp": "2026-01-01T00:00:00Z"}],
        "deltas": [],
        "drift_scores": {},
    }
    explicit_baseline = explicit_dir / "baseline.json"
    explicit_baseline.write_text(json.dumps(explicit_payload), encoding="utf-8")

    def _cache_factory(*args, **kwargs):
        return OrgReportCache(cache_dir=snapshot_cache_root, logger=kwargs.get("logger"))

    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        patch("cja_auto_sdr.generator.OrgReportCache", side_effect=_cache_factory),
        patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer_cls,
        patch("cja_auto_sdr.generator.write_org_report_console") as mock_console,
        patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary"),
        patch("cja_auto_sdr.generator.append_github_step_summary"),
    ):
        mock_cjapy.CJA.return_value = Mock()
        analyzer = Mock()
        analyzer.run_analysis.return_value = current
        mock_analyzer_cls.return_value = analyzer

        ok, exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=OrgReportConfig(compare_org_report=str(explicit_baseline)),
            quiet=False,
            trending_window=3,
        )

    assert ok is True
    assert exceeded is False

    trending = mock_console.call_args.kwargs.get("trending")
    assert trending is not None
    assert [snapshot.timestamp for snapshot in trending.snapshots] == ["2026-02-01T00:00:00Z", "2026-03-01T00:00:00Z"]


def test_run_org_report_trending_window_renders_across_file_formats_with_persistent_cache(
    tmp_path: Path, rich_org_report_result, capsys
):
    openpyxl = pytest.importorskip("openpyxl")

    baseline = deepcopy(rich_org_report_result)
    baseline.timestamp = "2026-02-01T00:00:00Z"
    baseline.org_id = "test_org@AdobeOrg"
    baseline.is_sampled = False

    current = deepcopy(rich_org_report_result)
    current.timestamp = "2026-03-01T00:00:00Z"
    current.org_id = "test_org@AdobeOrg"
    current.is_sampled = False

    snapshot_cache_root = tmp_path / "cache"
    OrgReportCache(cache_dir=snapshot_cache_root).save_org_report_snapshot(
        build_org_report_json_data(baseline), org_id=baseline.org_id
    )

    def _cache_factory(*args, **kwargs):
        return OrgReportCache(cache_dir=snapshot_cache_root, logger=kwargs.get("logger"))

    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        patch("cja_auto_sdr.generator.OrgReportCache", side_effect=_cache_factory),
        patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer_cls,
        patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary"),
        patch("cja_auto_sdr.generator.append_github_step_summary"),
    ):
        mock_cjapy.CJA.return_value = Mock()
        analyzer = Mock()
        analyzer.run_analysis.return_value = current
        mock_analyzer_cls.return_value = analyzer

        format_outputs = {
            "json": tmp_path / "json" / "org_report.json",
            "excel": tmp_path / "excel" / "org_report.xlsx",
            "markdown": tmp_path / "markdown" / "org_report.md",
            "html": tmp_path / "html" / "org_report.html",
        }

        ok_console, exceeded_console = generator.run_org_report(
            config_file="config.json",
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path / "console"),
            org_config=OrgReportConfig(),
            quiet=False,
            trending_window=3,
        )
        assert ok_console is True
        assert exceeded_console is False
        assert "TRENDING" in capsys.readouterr().out

        for fmt, output_path in format_outputs.items():
            ok, exceeded = generator.run_org_report(
                config_file="config.json",
                output_format=fmt,
                output_path=str(output_path),
                output_dir=str(output_path.parent),
                org_config=OrgReportConfig(),
                quiet=False,
                trending_window=3,
            )
            assert ok is True
            assert exceeded is False

        ok_csv, exceeded_csv = generator.run_org_report(
            config_file="config.json",
            output_format="csv",
            output_path=None,
            output_dir=str(tmp_path / "csv"),
            org_config=OrgReportConfig(),
            quiet=False,
            trending_window=3,
        )
        assert ok_csv is True
        assert exceeded_csv is False

    json_payload = json.loads(format_outputs["json"].read_text(encoding="utf-8"))
    assert "trending" in json_payload
    assert "Trending" in format_outputs["markdown"].read_text(encoding="utf-8")
    assert "Trending" in format_outputs["html"].read_text(encoding="utf-8")
    assert "Trending" in openpyxl.load_workbook(format_outputs["excel"]).sheetnames
    assert list((tmp_path / "csv").rglob("*trending*.csv"))


def test_run_org_report_trending_window_persists_sampled_history_for_inspection(tmp_path: Path, rich_org_report_result):
    sampled_result = deepcopy(rich_org_report_result)
    sampled_result.timestamp = "2026-03-01T00:00:00Z"
    sampled_result.org_id = "test_org@AdobeOrg"
    sampled_result.is_sampled = True

    snapshot_cache_root = tmp_path / "cache"

    def _cache_factory(*args, **kwargs):
        return OrgReportCache(cache_dir=snapshot_cache_root, logger=kwargs.get("logger"))

    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        patch("cja_auto_sdr.generator.OrgReportCache", side_effect=_cache_factory),
        patch.object(OrgReportCache, "prune_org_report_snapshots", return_value=[]) as mock_prune,
        patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer_cls,
        patch("cja_auto_sdr.generator.write_org_report_console") as mock_console,
        patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary"),
        patch("cja_auto_sdr.generator.append_github_step_summary"),
    ):
        mock_cjapy.CJA.return_value = Mock()
        analyzer = Mock()
        analyzer.run_analysis.return_value = sampled_result
        mock_analyzer_cls.return_value = analyzer

        ok, exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=OrgReportConfig(),
            quiet=False,
            trending_window=3,
        )

    assert ok is True
    assert exceeded is False
    assert mock_console.call_args.kwargs.get("trending") is None
    mock_prune.assert_called_once()

    snapshot_cache = OrgReportCache(cache_dir=snapshot_cache_root)
    snapshot_dir = snapshot_cache.get_org_report_snapshot_dir("test_org@AdobeOrg")
    assert len(list(snapshot_dir.glob("*.json"))) == 1
    snapshots = snapshot_cache.list_org_report_snapshots("test_org@AdobeOrg")
    assert len(snapshots) == 1
    assert snapshots[0]["history_eligible"] is False
    assert snapshots[0]["history_exclusion_reason"] == "sampled"


def test_run_org_report_without_trending_window_leaves_output_unchanged(tmp_path: Path, rich_org_report_result):
    result = deepcopy(rich_org_report_result)
    result.timestamp = "2026-03-01T00:00:00Z"
    result.org_id = "test_org@AdobeOrg"
    output_path = tmp_path / "org_report.json"

    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        patch("cja_auto_sdr.generator.OrgReportCache") as mock_cache_cls,
        patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer_cls,
        patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary"),
        patch("cja_auto_sdr.generator.append_github_step_summary"),
    ):
        mock_cjapy.CJA.return_value = Mock()
        analyzer = Mock()
        analyzer.run_analysis.return_value = result
        mock_analyzer_cls.return_value = analyzer

        ok, exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="json",
            output_path=str(output_path),
            output_dir=str(tmp_path),
            org_config=OrgReportConfig(),
            quiet=False,
            trending_window=None,
        )

    assert ok is True
    assert exceeded is False
    assert mock_cache_cls.call_count == 0

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert "trending" not in payload


def test_run_org_report_comparison_os_error_is_non_fatal(tmp_path: Path, rich_org_report_result, capsys):
    result = rich_org_report_result
    config = OrgReportConfig(compare_org_report="previous.json")

    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer_cls,
        patch("cja_auto_sdr.generator.compare_org_reports", side_effect=PermissionError("permission denied")),
        patch("cja_auto_sdr.generator.write_org_report_console") as mock_console,
        patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary"),
        patch("cja_auto_sdr.generator.append_github_step_summary"),
    ):
        mock_cjapy.CJA.return_value = Mock()
        analyzer = Mock()
        analyzer.run_analysis.return_value = result
        mock_analyzer_cls.return_value = analyzer

        ok, exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=config,
            quiet=False,
        )

    assert ok is True
    assert exceeded is False
    mock_console.assert_called_once()
    out = capsys.readouterr().out
    assert "Warning: Could not compare reports: permission denied" in out


def test_run_org_report_comparison_ineligible_legacy_baseline_is_non_fatal(
    tmp_path: Path, rich_org_report_result, capsys
):
    result = rich_org_report_result
    baseline_path = tmp_path / "legacy_baseline.json"
    baseline_path.write_text(
        json.dumps(
            {
                "generated_at": "2026-02-01T00:00:00Z",
                "org_id": "test_org@AdobeOrg",
                "summary": {"data_views_total": 2, "total_unique_components": 5},
                "distribution": {"core": {"total": 2}, "isolated": {"total": 3}},
                "similarity_pairs": [],
            }
        ),
        encoding="utf-8",
    )

    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer_cls,
        patch("cja_auto_sdr.generator.write_org_report_console") as mock_console,
        patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary"),
        patch("cja_auto_sdr.generator.append_github_step_summary"),
    ):
        mock_cjapy.CJA.return_value = Mock()
        analyzer = Mock()
        analyzer.run_analysis.return_value = result
        mock_analyzer_cls.return_value = analyzer

        ok, exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=OrgReportConfig(compare_org_report=str(baseline_path)),
            quiet=False,
        )

    assert ok is True
    assert exceeded is False
    mock_console.assert_called_once()
    out = capsys.readouterr().out
    assert "legacy_missing_fidelity_markers" in out


def test_run_org_report_failure_paths(tmp_path: Path, rich_org_report_result):
    with patch("cja_auto_sdr.generator.configure_cjapy", return_value=(False, "bad credentials", None)):
        ok, exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=OrgReportConfig(),
            quiet=False,
        )
    assert ok is False
    assert exceeded is False

    empty_result = rich_org_report_result
    empty_result.data_view_summaries = []
    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer_cls,
    ):
        mock_cjapy.CJA.return_value = Mock()
        analyzer = Mock()
        analyzer.run_analysis.return_value = empty_result
        mock_analyzer_cls.return_value = analyzer

        ok, exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=OrgReportConfig(),
            quiet=False,
        )
    assert ok is False
    assert exceeded is False

    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer_cls,
    ):
        mock_cjapy.CJA.return_value = Mock()
        analyzer = Mock()
        analyzer.run_analysis.side_effect = CJASDRError("analysis failed")
        mock_analyzer_cls.return_value = analyzer

        ok, exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=OrgReportConfig(),
            quiet=False,
        )
    assert ok is False
    assert exceeded is False


def test_run_org_report_alias_output_value_error_returns_controlled_failure(
    tmp_path: Path, rich_org_report_result, capsys
):
    result = rich_org_report_result

    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer_cls,
    ):
        mock_cjapy.CJA.return_value = Mock()
        analyzer = Mock()
        analyzer.run_analysis.return_value = result
        mock_analyzer_cls.return_value = analyzer

        ok, exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="data",
            output_path=".",
            output_dir=str(tmp_path),
            org_config=OrgReportConfig(),
            quiet=True,
        )

    assert ok is False
    assert exceeded is False
    out = capsys.readouterr().out
    assert "ERROR: Org report failed" in out


def test_run_org_report_unexpected_cja_runtime_error_returns_controlled_failure(tmp_path: Path, capsys):
    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
    ):
        mock_cjapy.CJA.side_effect = RuntimeError("bootstrap exploded")

        ok, exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=OrgReportConfig(),
            quiet=True,
        )

    assert ok is False
    assert exceeded is False
    assert "ERROR: Org report failed: bootstrap exploded" in capsys.readouterr().out


def test_run_org_report_org_stats_json_stdout_branch(tmp_path: Path, capsys, rich_org_report_result):
    result = rich_org_report_result
    config = OrgReportConfig(org_stats_only=True)

    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer_cls,
        patch("cja_auto_sdr.generator.write_org_report_stats_only"),
        patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary"),
        patch("cja_auto_sdr.generator.append_github_step_summary"),
    ):
        mock_cjapy.CJA.return_value = Mock()
        analyzer = Mock()
        analyzer.run_analysis.return_value = result
        mock_analyzer_cls.return_value = analyzer

        ok, exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="json",
            output_path="stdout",
            output_dir=str(tmp_path),
            org_config=config,
            quiet=False,
        )

    stdout = capsys.readouterr().out
    assert ok is True
    assert exceeded is False
    assert '"report_type": "org_analysis"' in stdout


def test_run_org_report_org_stats_console_uses_cached_trending_for_low_fidelity_current_run(
    tmp_path: Path, capsys, rich_org_report_result
):
    baseline_one = deepcopy(rich_org_report_result)
    baseline_one.timestamp = "2026-01-01T00:00:00Z"
    baseline_one.org_id = "test_org@AdobeOrg"
    baseline_one.is_sampled = False

    baseline_two = deepcopy(rich_org_report_result)
    baseline_two.timestamp = "2026-02-01T00:00:00Z"
    baseline_two.org_id = "test_org@AdobeOrg"
    baseline_two.is_sampled = False

    current = deepcopy(rich_org_report_result)
    current.timestamp = "2026-03-01T00:00:00Z"
    current.org_id = "test_org@AdobeOrg"
    current.is_sampled = False
    current.parameters.org_stats_only = True
    current.similarity_pairs = None

    snapshot_cache_root = tmp_path / "cache"
    OrgReportCache(cache_dir=snapshot_cache_root).save_org_report_snapshot(
        build_org_report_json_data(baseline_one), org_id=baseline_one.org_id
    )
    OrgReportCache(cache_dir=snapshot_cache_root).save_org_report_snapshot(
        build_org_report_json_data(baseline_two), org_id=baseline_two.org_id
    )

    def _cache_factory(*args, **kwargs):
        return OrgReportCache(cache_dir=snapshot_cache_root, logger=kwargs.get("logger"))

    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        patch("cja_auto_sdr.generator.OrgReportCache", side_effect=_cache_factory),
        patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer_cls,
        patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary"),
        patch("cja_auto_sdr.generator.append_github_step_summary"),
    ):
        mock_cjapy.CJA.return_value = Mock()
        analyzer = Mock()
        analyzer.run_analysis.return_value = current
        mock_analyzer_cls.return_value = analyzer

        ok, exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=OrgReportConfig(org_stats_only=True),
            quiet=False,
            trending_window=3,
        )

    output = capsys.readouterr().out
    assert ok is True
    assert exceeded is False
    assert "ORG STATS" in output
    assert "TRENDING" in output
    assert "full similarity analysis" in output
    assert "Using eligible cached snapshots only." in output

    snapshot_cache = OrgReportCache(cache_dir=snapshot_cache_root)
    snapshot_dir = snapshot_cache.get_org_report_snapshot_dir("test_org@AdobeOrg")
    assert len(list(snapshot_dir.glob("*.json"))) == 3
    snapshots = snapshot_cache.list_org_report_snapshots("test_org@AdobeOrg")
    assert snapshots[0]["generated_at"] == "2026-03-01T00:00:00Z"
    assert snapshots[0]["history_eligible"] is False
    assert snapshots[0]["history_exclusion_reason"] == "org_stats_only"


def test_run_org_report_trending_window_uses_current_snapshot_when_persist_fails(
    tmp_path: Path, capsys, rich_org_report_result
):
    baseline = deepcopy(rich_org_report_result)
    baseline.timestamp = "2026-02-01T00:00:00Z"
    baseline.org_id = "test_org@AdobeOrg"
    baseline.is_sampled = False

    current = deepcopy(rich_org_report_result)
    current.timestamp = "2026-03-01T00:00:00Z"
    current.org_id = "test_org@AdobeOrg"
    current.is_sampled = False

    snapshot_cache_root = tmp_path / "cache"
    OrgReportCache(cache_dir=snapshot_cache_root).save_org_report_snapshot(
        build_org_report_json_data(baseline), org_id=baseline.org_id
    )

    def _cache_factory(*args, **kwargs):
        return OrgReportCache(cache_dir=snapshot_cache_root, logger=kwargs.get("logger"))

    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        patch("cja_auto_sdr.generator.OrgReportCache", side_effect=_cache_factory),
        patch.object(OrgReportCache, "save_org_report_snapshot", side_effect=OSError("disk full")),
        patch.object(OrgReportCache, "prune_org_report_snapshots", return_value=[]) as mock_prune,
        patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer_cls,
        patch("cja_auto_sdr.generator.write_org_report_console") as mock_console,
        patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary"),
        patch("cja_auto_sdr.generator.append_github_step_summary"),
    ):
        mock_cjapy.CJA.return_value = Mock()
        analyzer = Mock()
        analyzer.run_analysis.return_value = current
        mock_analyzer_cls.return_value = analyzer

        ok, exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=OrgReportConfig(),
            quiet=False,
            trending_window=3,
        )

    assert ok is True
    assert exceeded is False
    assert "Could not persist org-report snapshot history: disk full" in capsys.readouterr().out

    trending = mock_console.call_args.kwargs.get("trending")
    assert trending is not None
    assert [snapshot.timestamp for snapshot in trending.snapshots] == ["2026-02-01T00:00:00Z", "2026-03-01T00:00:00Z"]
    mock_prune.assert_not_called()


def test_org_report_renderers_core_min_count_and_unnamed_component_branches(
    tmp_path: Path,
    capsys,
    rich_org_report_result,
):
    result = rich_org_report_result
    result.parameters.core_min_count = 3

    # Force markdown/html/console branches that depend on unnamed components and large core lists.
    # This exercises the "more rows" truncation and no-name formatting paths.
    result.distribution.core_metrics = [f"metric/core_extra/{i}" for i in range(25)]
    result.distribution.core_dimensions = [f"dimension/core_extra/{i}" for i in range(25)]
    result.similarity_pairs = []

    for comp_id in result.distribution.core_metrics:
        result.component_index[comp_id] = ComponentInfo(
            component_id=comp_id,
            component_type="metric",
            name=None,
            data_views={"dv_001", "dv_003"},
        )
    for comp_id in result.distribution.core_dimensions:
        result.component_index[comp_id] = ComponentInfo(
            component_id=comp_id,
            component_type="dimension",
            name=None,
            data_views={"dv_001", "dv_003"},
        )

    logger = logging.getLogger("test_org_report_renderer_branches")
    md_path = generator.write_org_report_markdown(result, tmp_path / "core_min", str(tmp_path), logger)
    html_path = generator.write_org_report_html(result, tmp_path / "core_min_html", str(tmp_path), logger)
    generator.write_org_report_console(result, result.parameters, quiet=False)
    output = capsys.readouterr().out

    assert Path(md_path).exists()
    assert Path(html_path).exists()
    assert "Core (in >=3 DVs)" in output


def test_run_org_report_defensive_unsupported_format_fallback(tmp_path: Path, rich_org_report_result):
    result = rich_org_report_result
    with (
        patch("cja_auto_sdr.generator._validate_org_report_output_request", return_value=True),
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer_cls,
    ):
        mock_cjapy.CJA.return_value = Mock()
        analyzer = Mock()
        analyzer.run_analysis.return_value = result
        mock_analyzer_cls.return_value = analyzer

        ok, exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="unsupported_internal_mode",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=OrgReportConfig(),
            quiet=False,
        )

    assert ok is False
    assert exceeded is False


def test_run_org_report_data_alias_and_internal_csv_stdout_branch(tmp_path: Path, rich_org_report_result):
    result = rich_org_report_result
    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer_cls,
        patch("cja_auto_sdr.generator.write_org_report_json", return_value=str(tmp_path / "report.json")) as mock_json,
        patch("cja_auto_sdr.generator.write_org_report_csv", return_value=str(tmp_path / "report_csv")) as mock_csv,
        patch("cja_auto_sdr.generator.build_org_step_summary", return_value="summary"),
        patch("cja_auto_sdr.generator.append_github_step_summary"),
    ):
        mock_cjapy.CJA.return_value = Mock()
        analyzer = Mock()
        analyzer.run_analysis.return_value = result
        mock_analyzer_cls.return_value = analyzer

        ok, exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="data",
            output_path=str(tmp_path / "org_data"),
            output_dir=str(tmp_path),
            org_config=OrgReportConfig(),
            quiet=False,
        )
    assert ok is True
    assert exceeded is False
    mock_json.assert_called()
    mock_csv.assert_called()

    # Internal defensive CSV-stdout branch (normally blocked by upfront validation).
    with (
        patch("cja_auto_sdr.generator._validate_org_report_output_request", return_value=True),
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer_cls,
    ):
        mock_cjapy.CJA.return_value = Mock()
        analyzer = Mock()
        analyzer.run_analysis.return_value = result
        mock_analyzer_cls.return_value = analyzer
        ok, exceeded = generator.run_org_report(
            config_file="config.json",
            output_format="csv",
            output_path="stdout",
            output_dir=str(tmp_path),
            org_config=OrgReportConfig(),
            quiet=False,
        )
    assert ok is False
    assert exceeded is False


def test_run_org_report_file_not_found_and_keyboard_interrupt_paths(tmp_path: Path):
    with patch("cja_auto_sdr.generator.configure_cjapy", side_effect=FileNotFoundError):
        ok, exceeded = generator.run_org_report(
            config_file="missing.json",
            output_format="console",
            output_path=None,
            output_dir=str(tmp_path),
            org_config=OrgReportConfig(),
            quiet=False,
        )
    assert ok is False
    assert exceeded is False

    with (
        patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", {"org_id": "test_org@AdobeOrg"})),
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer_cls,
    ):
        mock_cjapy.CJA.return_value = Mock()
        analyzer = Mock()
        analyzer.run_analysis.side_effect = KeyboardInterrupt
        mock_analyzer_cls.return_value = analyzer
        with pytest.raises(KeyboardInterrupt):
            generator.run_org_report(
                config_file="config.json",
                output_format="console",
                output_path=None,
                output_dir=str(tmp_path),
                org_config=OrgReportConfig(),
                quiet=False,
            )


def test_recommendation_context_and_normalization_helpers():
    rec = {
        "data_view_name": "Primary",
        "data_view": "dv_1",
        "data_view_1_name": "Left",
        "data_view_1": "dv_left",
        "similarity": 0.88,
        "isolated_count": 4,
        "derived_count": 2,
        "total_count": 10,
        "count": 5,
        "drift_count": 1,
        "ratio": 0.4,
        "modified": "2026-02-10T00:00:00+00:00",
    }
    entries = generator._format_recommendation_context_entries(rec)
    assert ("Data View", "Primary (dv_1)") in entries
    assert ("Pair", "Left (dv_left)") in entries
    assert ("Similarity", "88.0%") in entries
    assert ("Isolated Count", "4") in entries
    assert ("Derived Count", "2") in entries
    assert ("Total Count", "10") in entries
    assert ("Count", "5") in entries
    assert ("Drift Count", "1") in entries
    assert ("Ratio", "40.0%") in entries
    assert ("Last Modified", "2026-02-10T00:00:00+00:00") in entries

    assert generator._normalize_recommendation_severity("HIGH") == "high"
    assert generator._normalize_recommendation_severity("unexpected") == "low"

    normalized = generator._normalize_recommendation_for_json("raw text recommendation")
    assert normalized["type"] == "unknown"
    assert normalized["severity"] == "low"
    assert "raw text recommendation" in normalized["reason"]

    flattened = generator._flatten_recommendation_for_tabular(
        {"type": "naming", "severity": "MEDIUM", "reason": "Use one style", "custom_field": {"x": 1}},
    )
    assert flattened["Severity"] == "medium"
    assert "custom_field" in flattened["Extra Details"]
