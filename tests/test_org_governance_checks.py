"""Requested governance gates distinguish unavailable evidence from a passing result."""

import json
import logging
import sys
from unittest.mock import Mock, patch

import pytest

from cja_auto_sdr import generator
from cja_auto_sdr.org.analyzer import OrgComponentAnalyzer
from cja_auto_sdr.org.models import DataViewSummary, OrgReportConfig
from cja_auto_sdr.org.writers import build_org_report_json_data


def _summaries(*, empty=False, failed=False):
    summaries = [
        DataViewSummary(
            data_view_id=f"dv{i}",
            data_view_name=f"View {i}",
            metric_ids=set() if empty else {"shared", f"unique{i}"},
            metric_count=0 if empty else 2,
        )
        for i in range(3)
    ]
    if failed:
        summaries.append(DataViewSummary(data_view_id="failed", data_view_name="Failed", error="API unavailable"))
    return summaries


def _analyzer(config, summaries):
    config.skip_lock = True
    config.cja_per_thread = False
    analyzer = OrgComponentAnalyzer(Mock(), config, logging.getLogger(__name__), org_id="test@AdobeOrg")
    analyzer._list_and_filter_data_views = Mock(return_value=([{"id": s.data_view_id} for s in summaries], True, 10))
    analyzer._fetch_all_data_views = Mock(return_value=summaries)
    return analyzer


@pytest.mark.parametrize(
    ("settings", "reason"),
    [
        ({"skip_similarity": True}, "skip_similarity"),
        ({"org_stats_only": True}, "org_stats_only"),
        ({"similarity_max_dvs": 2}, "similarity_guardrail"),
    ],
)
def test_unavailable_duplicate_gate_names_reason_and_scope(settings, reason):
    result = _analyzer(OrgReportConfig(duplicate_threshold=0, **settings), _summaries(failed=True)).run_analysis()
    check = result.governance_checks[0]
    assert check["status"] == "not_evaluated"
    assert check["reason"] == reason
    assert check["actual"] is None
    assert check["scope"] == {
        "selected_data_views": 4,
        "successful_data_views": 3,
        "failed_data_views": 1,
        "total_available_data_views": 10,
        "is_sampled": True,
    }
    assert check["denominator"] == 3
    assert result.governance_violations == []
    assert not result.thresholds_exceeded


def test_computed_empty_duplicate_gate_passes_and_isolated_boundary_is_inclusive():
    result = _analyzer(OrgReportConfig(duplicate_threshold=0, isolated_threshold=0.75), _summaries()).run_analysis()
    assert result.similarity_pairs == []
    duplicate, isolated = result.governance_checks
    assert (duplicate["status"], duplicate["actual"]) == ("pass", 0)
    assert (isolated["status"], isolated["actual"], isolated["denominator"]) == ("pass", 0.75, 4)
    assert build_org_report_json_data(result)["governance_checks"] == result.governance_checks


def test_zero_components_isolated_gate_is_not_evaluated():
    result = _analyzer(OrgReportConfig(isolated_threshold=0), _summaries(empty=True)).run_analysis()
    assert result.governance_checks[0]["status"] == "not_evaluated"
    assert result.governance_checks[0]["reason"] == "no_components"
    assert result.governance_checks[0]["denominator"] == 0
    assert result.governance_checks[0]["actual"] is None


@pytest.mark.parametrize(
    ("extra", "exit_code", "status"),
    [
        (["--skip-similarity", "--fail-on-threshold"], 1, "error"),
        (["--org-stats", "--fail-on-threshold"], 1, "error"),
        (["--similarity-max-dvs", "2", "--fail-on-threshold"], 1, "error"),
        (["--skip-similarity"], 0, "success"),
        (["--fail-on-threshold"], 2, "policy_exit"),
    ],
)
def test_cli_json_and_run_summary_preserve_evaluation_failure_precedence(
    tmp_path, capsys, monkeypatch, extra, exit_code, status
):
    summary_path = tmp_path / "summary.json"
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    argv = [
        "cja_auto_sdr",
        "--org-report",
        "--format",
        "json",
        "--output",
        "-",
        "--duplicate-threshold",
        "0",
        "--isolated-threshold",
        "0",
        "--run-summary-json",
        str(summary_path),
        *extra,
    ]
    with (
        patch.object(sys, "argv", argv),
        patch.object(generator, "configure_cjapy", return_value=(True, "test", {"org_id": "test@AdobeOrg"})),
        patch.object(generator.cjapy, "CJA", return_value=Mock()),
        patch.object(
            generator,
            "OrgComponentAnalyzer",
            side_effect=lambda cja, config, logger, **kw: _analyzer(config, _summaries()),
        ),
        pytest.raises(SystemExit) as exc,
    ):
        generator.main()
    assert exc.value.code == exit_code
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    if exit_code == 1:
        error = json.loads(captured.err)
        assert error["error_type"] == "governance_evaluation_error"
        assert "duplicate_threshold" in error["error"]
        assert report["governance_checks"][0]["reason"] in error["error"]
    else:
        assert captured.err == ""
    summary = json.loads(summary_path.read_text())
    assert summary["exit_code"] == exit_code
    assert summary["status"] == status
    assert summary["details"]["operation_success"] is (exit_code != 1)
    assert report["thresholds_exceeded"] is True
    assert summary["details"]["governance_checks"] == report["governance_checks"]
    assert report["governance_checks"][1]["status"] == "fail"


@pytest.mark.parametrize(("threshold", "status"), [(3, "pass"), (2, "fail")])
def test_duplicate_exact_boundary_and_legacy_violation_shape(threshold, status):
    summaries = _summaries()
    for summary in summaries:
        summary.metric_ids = {"shared"}
        summary.metric_count = 1
    result = _analyzer(OrgReportConfig(duplicate_threshold=threshold), summaries).run_analysis()
    check = result.governance_checks[0]
    assert (check["actual"], check["denominator"], check["status"]) == (3, 3, status)
    assert result.thresholds_exceeded is (status == "fail")
    if status == "fail":
        assert result.governance_violations == [
            {
                "type": "duplicate_threshold_exceeded",
                "threshold": 2,
                "actual": 3,
                "message": "Found 3 high-similarity pairs (>=90%), threshold is 2",
            }
        ]


def test_no_requested_gates_and_legacy_construction_have_empty_checks():
    from dataclasses import asdict

    from cja_auto_sdr.org.models import OrgReportResult

    result = _analyzer(OrgReportConfig(), _summaries()).run_analysis()
    assert result.governance_checks == []
    assert result.governance_violations is None
    # Dataclass callers created before the additive field remain supported.
    legacy = {field: getattr(result, field) for field in asdict(result) if field != "governance_checks"}
    assert OrgReportResult(**legacy).governance_checks == []


def test_empty_selection_still_exposes_requested_checks():
    result = _analyzer(OrgReportConfig(duplicate_threshold=0, isolated_threshold=0), []).run_analysis()
    assert [check["status"] for check in result.governance_checks] == ["not_evaluated", "not_evaluated"]
    assert result.governance_checks[0]["reason"] == "no_data_views"


@pytest.mark.parametrize("format_name", ["console", "stats", "markdown", "html", "csv", "excel"])
def test_human_writers_expose_unavailable_status_scope_and_recovery(format_name, tmp_path, capsys):
    from pathlib import Path

    import pandas as pd

    from cja_auto_sdr.org import writers

    result = _analyzer(
        OrgReportConfig(duplicate_threshold=0, skip_similarity=True), _summaries(failed=True)
    ).run_analysis()
    if format_name == "console":
        writers.write_org_report_console(result, result.parameters)
        text = capsys.readouterr().out
    elif format_name == "stats":
        writers.write_org_report_stats_only(result)
        text = capsys.readouterr().out
    else:
        writer = getattr(writers, f"write_org_report_{format_name}")
        path = Path(writer(result, tmp_path / "report", str(tmp_path), logging.getLogger(__name__)))
        if format_name == "excel":
            text = pd.read_excel(path, sheet_name="Governance Checks").to_string()
        elif format_name == "csv":
            text = (path / "org_report_governance_checks.csv").read_text()
        else:
            text = path.read_text()
    assert "not_evaluated" in text
    assert "skip_similarity" in text
    assert "3 successful / 4 selected" in text
    assert "1 failed" in text
    assert "Rerun without --skip-similarity" in text


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize("zero_components", [False, True])
def test_cli_unavailable_check_without_violations(tmp_path, capsys, monkeypatch, strict, zero_components):
    summary_path = tmp_path / "summary.json"
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    gate = ["--isolated-threshold", "0"] if zero_components else ["--duplicate-threshold", "0", "--skip-similarity"]
    argv = [
        "cja_auto_sdr",
        "--org-report",
        "--format",
        "json",
        "--output",
        "-",
        "--run-summary-json",
        str(summary_path),
        *gate,
    ]
    if strict:
        argv.append("--fail-on-threshold")
    with (
        patch.object(sys, "argv", argv),
        patch.object(generator, "configure_cjapy", return_value=(True, "test", {"org_id": "test@AdobeOrg"})),
        patch.object(generator.cjapy, "CJA", return_value=Mock()),
        patch.object(
            generator,
            "OrgComponentAnalyzer",
            side_effect=lambda cja, config, logger, **kw: _analyzer(config, _summaries(empty=zero_components)),
        ),
        pytest.raises(SystemExit) as exc,
    ):
        generator.main()
    assert exc.value.code == (1 if strict else 0)
    captured = capsys.readouterr()
    report = json.loads(captured.out)
    if strict:
        error = json.loads(captured.err)
        assert error["error_type"] == "governance_evaluation_error"
        assert report["governance_checks"][0]["reason"] in error["error"]
    else:
        assert captured.err == ""
    summary = json.loads(summary_path.read_text())
    assert report["governance_checks"][0]["status"] == "not_evaluated"
    assert report["governance_violations"] == []
    assert report["thresholds_exceeded"] is False
    assert summary["details"]["governance_checks"] == report["governance_checks"]
    assert summary["status"] == ("error" if strict else "success")


@pytest.mark.parametrize("partial_fetch", [False, True])
def test_strict_computed_empty_gate_passes_for_disclosed_successful_subset(
    tmp_path, capsys, monkeypatch, partial_fetch
):
    summary_path = tmp_path / "summary.json"
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    argv = [
        "cja_auto_sdr",
        "--org-report",
        "--format",
        "json",
        "--output",
        "-",
        "--duplicate-threshold",
        "0",
        "--fail-on-threshold",
        "--run-summary-json",
        str(summary_path),
    ]
    with (
        patch.object(sys, "argv", argv),
        patch.object(generator, "configure_cjapy", return_value=(True, "test", {"org_id": "test@AdobeOrg"})),
        patch.object(generator.cjapy, "CJA", return_value=Mock()),
        patch.object(
            generator,
            "OrgComponentAnalyzer",
            side_effect=lambda cja, config, logger, **kw: _analyzer(config, _summaries(failed=partial_fetch)),
        ),
        pytest.raises(SystemExit) as exc,
    ):
        generator.main()
    assert exc.value.code == 0
    report = json.loads(capsys.readouterr().out)
    summary = json.loads(summary_path.read_text())
    assert report["governance_checks"][0]["status"] == "pass"
    assert report["governance_checks"][0]["scope"]["failed_data_views"] == int(partial_fetch)
    assert report["thresholds_exceeded"] is False
    assert summary["details"]["governance_checks"] == report["governance_checks"]
    assert summary["status"] == "success"
