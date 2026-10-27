"""Tests for per-family SDR coverage state and quality audit status."""

from __future__ import annotations

import json
import logging
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from cja_auto_sdr.api.fetch import EndpointFetchStatus
from cja_auto_sdr.output.sdr import (
    build_json_payload,
    build_typed_json_payload,
    df_to_markdown_table,
    write_excel_output,
    write_html_output,
    write_markdown_output,
)
from cja_auto_sdr.output.sdr.coverage import (
    COVERAGE_COLUMNS,
    COVERAGE_SHEET_NAME,
    CoverageState,
    QualityState,
    build_sdr_coverage,
    coverage_section_labels,
    excluded_standard_families,
    quality_gate_verdict,
)

LOGGER = logging.getLogger("test_sdr_coverage")


def _issue(severity: str) -> dict[str, str]:
    return {"Severity": severity, "Category": "c", "Type": "t", "Item Name": "i", "Issue": "x", "Details": ""}


def _rows_by_family(coverage):
    return {row.family: row for row in coverage.rows}


# ---------------------------------------------------------------------------
# Pure coverage derivation
# ---------------------------------------------------------------------------


class TestFamilyStates:
    def test_default_run_collects_standard_families_and_inventories_not_requested(self):
        coverage = build_sdr_coverage(metrics_count=3, dimensions_count=0, validation_status="completed")
        rows = _rows_by_family(coverage)
        assert list(rows) == ["metrics", "dimensions", "derived_fields", "calculated_metrics", "segments"]
        assert rows["metrics"].state is CoverageState.COLLECTED
        assert rows["metrics"].count == 3
        assert rows["dimensions"].state is CoverageState.COLLECTED_EMPTY
        assert rows["dimensions"].count == 0
        for family in ("derived_fields", "calculated_metrics", "segments"):
            assert rows[family].state is CoverageState.NOT_REQUESTED
            assert rows[family].count is None
        assert "--include-segments" in rows["segments"].detail
        assert coverage.collected_components == ("metrics", "dimensions")

    @pytest.mark.parametrize(
        ("metrics_only", "dimensions_only", "excluded", "flag"),
        [
            (True, False, "dimensions", "--metrics-only"),
            (False, True, "metrics", "--dimensions-only"),
        ],
    )
    def test_component_filters_mark_family_excluded(self, metrics_only, dimensions_only, excluded, flag):
        coverage = build_sdr_coverage(
            metrics_count=2,
            dimensions_count=2,
            metrics_only=metrics_only,
            dimensions_only=dimensions_only,
        )
        row = _rows_by_family(coverage)[excluded]
        assert row.state is CoverageState.EXCLUDED
        assert row.count is None
        assert flag in row.detail
        assert excluded not in coverage.collected_components

    def test_both_filters_keep_both_families(self):
        assert excluded_standard_families(metrics_only=True, dimensions_only=True) == {}

    def test_inventory_only_excludes_standard_families(self):
        excluded = excluded_standard_families(metrics_only=False, dimensions_only=False, inventory_only=True)
        assert excluded == {"metrics": "--inventory-only", "dimensions": "--inventory-only"}
        coverage = build_sdr_coverage(
            metrics_count=0,
            dimensions_count=0,
            inventory_only=True,
            inventory_statuses={"segments": "completed"},
            inventory_counts={"segments": 4},
        )
        assert coverage.collected_components == ("segments",)
        assert _rows_by_family(coverage)["segments"].state is CoverageState.COLLECTED

    def test_failed_standard_fetch_is_unavailable_not_empty(self):
        coverage = build_sdr_coverage(
            metrics_count=0,
            dimensions_count=1,
            fetch_statuses={
                "metrics": EndpointFetchStatus(endpoint="metrics", status="failed", error_message="HTTP 500"),
                "dimensions": EndpointFetchStatus(endpoint="dimensions", status="success"),
            },
        )
        row = _rows_by_family(coverage)["metrics"]
        assert row.state is CoverageState.FAILED
        assert row.count is None
        assert "unavailable — not an empty result" in row.detail
        assert "HTTP 500" in row.detail
        # A failed family was still requested, so it stays in scope.
        assert "metrics" in coverage.collected_components

    def test_failed_fetch_for_excluded_family_stays_excluded(self):
        coverage = build_sdr_coverage(
            metrics_count=1,
            dimensions_count=0,
            metrics_only=True,
            fetch_statuses={"dimensions": {"status": "failed", "reason": "timeout"}},
        )
        assert _rows_by_family(coverage)["dimensions"].state is CoverageState.EXCLUDED

    def test_fetch_status_mapping_reason_used_when_no_error_message(self):
        coverage = build_sdr_coverage(
            metrics_count=0,
            dimensions_count=0,
            fetch_statuses={"dimensions": {"status": "FAILED", "reason": "timeout"}},
        )
        row = _rows_by_family(coverage)["dimensions"]
        assert row.state is CoverageState.FAILED
        assert "timeout" in row.detail

    def test_inventory_states(self):
        coverage = build_sdr_coverage(
            metrics_count=1,
            dimensions_count=1,
            inventory_statuses={"derived": "completed", "calculated": "failed", "segments": "completed"},
            inventory_counts={"derived": 0, "segments": 7},
        )
        rows = _rows_by_family(coverage)
        assert rows["derived_fields"].state is CoverageState.COLLECTED_EMPTY
        assert rows["derived_fields"].count == 0
        assert rows["calculated_metrics"].state is CoverageState.FAILED
        assert rows["calculated_metrics"].count is None
        assert "not an empty result" in rows["calculated_metrics"].detail
        assert rows["segments"].state is CoverageState.COLLECTED
        assert rows["segments"].count == 7
        assert coverage.collected_components == (
            "metrics",
            "dimensions",
            "derived_fields",
            "calculated_metrics",
            "segments",
        )

    def test_row_heading_and_labels(self):
        coverage = build_sdr_coverage(metrics_count=1, dimensions_count=0)
        rows = _rows_by_family(coverage)
        assert rows["calculated_metrics"].heading == "Calculated Metrics"
        assert rows["metrics"].label == "Collected"
        assert rows["dimensions"].label == "Collected — no components"
        assert rows["segments"].label == "Not requested"


class TestQualityStatus:
    def test_completed_without_gate(self):
        coverage = build_sdr_coverage(
            metrics_count=1,
            dimensions_count=1,
            validation_status="completed",
            dq_issues=[_issue("HIGH"), _issue("LOW"), _issue("LOW")],
        )
        quality = coverage.quality
        assert quality.state is QualityState.RAN
        assert quality.issue_count == 3
        assert quality.severity_counts == {"HIGH": 1, "LOW": 2}
        assert quality.gate_threshold is None
        assert quality.gate_verdict is None
        assert quality.line == "Quality audit ran: 3 issues (HIGH: 1, LOW: 2)."

    def test_completed_no_issues_line(self):
        coverage = build_sdr_coverage(metrics_count=1, dimensions_count=1, validation_status="completed")
        assert coverage.quality.line == "Quality audit ran: no issues found."

    def test_single_issue_line_is_singular(self):
        coverage = build_sdr_coverage(
            metrics_count=1, dimensions_count=1, validation_status="completed", dq_issues=[_issue("INFO")]
        )
        assert coverage.quality.line == "Quality audit ran: 1 issue (INFO: 1)."

    @pytest.mark.parametrize(
        ("issues", "threshold", "verdict"),
        [
            ([_issue("HIGH")], "HIGH", "FAIL"),
            ([_issue("CRITICAL")], "high", "FAIL"),
            ([_issue("MEDIUM")], "HIGH", "PASS"),
            ([], "LOW", "PASS"),
        ],
    )
    def test_gate_verdict(self, issues, threshold, verdict):
        coverage = build_sdr_coverage(
            metrics_count=1,
            dimensions_count=1,
            validation_status="completed",
            dq_issues=issues,
            fail_on_quality=threshold,
        )
        assert coverage.quality.gate_threshold == threshold.upper()
        assert coverage.quality.gate_verdict == verdict
        assert f"Quality gate {verdict} at threshold {threshold.upper()}." in coverage.quality.line

    def test_gate_verdict_helper_reuses_gate_semantics(self):
        assert quality_gate_verdict([_issue("HIGH")], "MEDIUM") == "FAIL"
        assert quality_gate_verdict([_issue("LOW")], "MEDIUM") == "PASS"

    def test_gate_not_evaluated_when_validation_did_not_complete(self):
        coverage = build_sdr_coverage(
            metrics_count=1,
            dimensions_count=1,
            validation_status="failed",
            validation_status_detail="Failed (boom)",
            fail_on_quality="HIGH",
        )
        assert coverage.quality.state is QualityState.FAILED
        assert coverage.quality.issue_count is None
        assert coverage.quality.gate_verdict == "NOT_EVALUATED"
        assert "Failed (boom)" in coverage.quality.line

    def test_skipped_uses_detail(self):
        coverage = build_sdr_coverage(
            metrics_count=1,
            dimensions_count=1,
            validation_status="skipped",
            validation_status_detail="Skipped (--skip-validation)",
        )
        assert coverage.quality.state is QualityState.SKIPPED
        assert coverage.quality.line == "Quality audit skipped: --skip-validation."

    def test_skipped_without_detail(self):
        coverage = build_sdr_coverage(metrics_count=1, dimensions_count=1, validation_status="skipped")
        assert coverage.quality.line == "Quality audit skipped."

    def test_not_run_when_status_unknown(self):
        coverage = build_sdr_coverage(metrics_count=1, dimensions_count=1)
        assert coverage.quality.state is QualityState.NOT_RUN
        assert coverage.quality.line == "No quality audit ran."


class TestCoverageSerialization:
    def _coverage(self):
        return build_sdr_coverage(
            metrics_count=2,
            dimensions_count=0,
            metrics_only=True,
            validation_status="completed",
            dq_issues=[_issue("HIGH")],
            fail_on_quality="HIGH",
        )

    def test_frame_has_family_rows_then_quality_row(self):
        frame = self._coverage().to_frame()
        assert list(frame.columns) == list(COVERAGE_COLUMNS) == ["Family", "State", "Count", "Detail"]
        assert frame["Family"].tolist() == [
            "Metrics",
            "Dimensions",
            "Derived Fields",
            "Calculated Metrics",
            "Segments",
            "Data Quality",
        ]
        assert frame["State"].tolist()[:2] == ["collected", "excluded"]
        assert frame.iloc[-1]["State"] == "ran"
        assert frame.iloc[-1]["Count"] == 1
        assert "Quality gate FAIL" in frame.iloc[-1]["Detail"]

    def test_to_json(self):
        payload = self._coverage().to_json()
        assert payload["families"][0] == {
            "family": "metrics",
            "state": "collected",
            "count": 2,
            "detail": "Collected",
        }
        assert payload["families"][1]["state"] == "excluded"
        assert payload["families"][1]["count"] is None
        assert payload["quality"] == {
            "state": "ran",
            "detail": "Quality audit ran: 1 issue (HIGH: 1). Quality gate FAIL at threshold HIGH.",
            "issue_count": 1,
            "severity_counts": {"HIGH": 1},
            "gate": {"threshold": "HIGH", "verdict": "FAIL"},
        }
        json.dumps(payload)

    def test_to_json_without_gate(self):
        coverage = build_sdr_coverage(metrics_count=1, dimensions_count=1)
        assert coverage.to_json()["quality"]["gate"] is None

    def test_metadata_rows(self):
        assert self._coverage().quality.metadata_rows() == [
            ("Quality Gate Verdict", "FAIL"),
            ("Quality Gate Threshold", "HIGH"),
        ]
        assert build_sdr_coverage(metrics_count=1, dimensions_count=1).quality.metadata_rows() == []

    def test_section_labels_from_data_dict(self):
        data_dict = {COVERAGE_SHEET_NAME: self._coverage().to_frame()}
        labels = coverage_section_labels(data_dict)
        assert labels["Dimensions"].startswith("Excluded from this run")
        assert labels["Data Quality"].startswith("Quality audit ran")
        assert coverage_section_labels({}) == {}
        assert coverage_section_labels({COVERAGE_SHEET_NAME: pd.DataFrame()}) == {}


# ---------------------------------------------------------------------------
# Writers
# ---------------------------------------------------------------------------


def _writer_data_dict(**coverage_kwargs):
    coverage = build_sdr_coverage(**coverage_kwargs)
    return {
        "Metadata": pd.DataFrame({"Property": ["Data View ID"], "Value": ["dv_1"]}),
        COVERAGE_SHEET_NAME: coverage.to_frame(),
        "Data Quality": pd.DataFrame(),
        "Metrics": pd.DataFrame(),
    }, coverage


class TestWritersRenderCoverage:
    def test_markdown_renders_coverage_and_state_labels_for_empty_sections(self, tmp_path):
        data_dict, _ = _writer_data_dict(
            metrics_count=0,
            dimensions_count=0,
            validation_status="skipped",
            validation_status_detail="Skipped (--skip-validation)",
        )
        path = write_markdown_output(data_dict, {"Data View ID": "dv_1"}, "sdr", str(tmp_path), LOGGER)
        text = open(path, encoding="utf-8").read()
        assert "## Coverage" in text
        assert text.index("## Coverage") < text.index("## Data Quality")
        assert "*Quality audit skipped: --skip-validation.*" in text
        assert "*Collected — no components*" in text
        assert "*No metrics found.*" not in text

    def test_markdown_table_default_empty_message_unchanged(self):
        assert df_to_markdown_table(pd.DataFrame(), "Metrics") == "\n*No metrics found.*\n"
        assert df_to_markdown_table(pd.DataFrame(), "Metrics", empty_message="Excluded") == "\n*Excluded*\n"

    def test_html_keeps_empty_sections_with_state_label(self, tmp_path):
        data_dict, _ = _writer_data_dict(metrics_count=0, dimensions_count=0, validation_status="completed")
        data_dict["Unlabelled"] = pd.DataFrame()
        path = write_html_output(data_dict, {"Data View ID": "dv_1"}, "sdr", str(tmp_path), LOGGER)
        text = open(path, encoding="utf-8").read()
        assert "Coverage</h2>" in text
        assert "Metrics</h2>" in text
        assert "Collected — no components" in text
        assert "Data Quality</h2>" in text
        assert "Quality audit ran: no issues found." in text
        assert "Unlabelled</h2>" in text
        assert "No data available for Unlabelled" in text

    def test_excel_writer_placeholder_uses_state_label(self, tmp_path):
        data_dict, _ = _writer_data_dict(
            metrics_count=0,
            dimensions_count=0,
            validation_status="skipped",
            validation_status_detail="Skipped (--skip-validation)",
        )
        path = write_excel_output(data_dict, "sdr", str(tmp_path), LOGGER)
        sheets = pd.read_excel(path, sheet_name=None, header=None)
        assert list(sheets)[:2] == ["Metadata", "Coverage"]
        assert (
            sheets["Data Quality"]
            .astype(str)
            .apply(lambda col: col.str.contains("Quality audit skipped: --skip-validation."))
            .any()
            .any()
        )
        assert (
            sheets["Metrics"].astype(str).apply(lambda col: col.str.contains("Collected — no components")).any().any()
        )

    def test_json_payload_adds_coverage_keys(self):
        coverage = build_sdr_coverage(metrics_count=0, dimensions_count=0, metrics_only=True)
        payload = build_json_payload({"Metrics": pd.DataFrame()}, {}, coverage=coverage)
        assert payload["collected_components"] == ["metrics"]
        assert payload["coverage"] == coverage.to_json()
        # Excluded family keeps its key (empty list) for backward compatibility.
        assert payload["dimensions"] == []
        # Without coverage the legacy shape is unchanged.
        assert "coverage" not in build_json_payload({}, {})

    def test_json_payload_ignores_coverage_sheet_records(self):
        coverage = build_sdr_coverage(metrics_count=0, dimensions_count=0)
        payload = build_json_payload({COVERAGE_SHEET_NAME: coverage.to_frame()}, {}, coverage=coverage)
        assert "Coverage" not in payload

    def test_typed_payload_adds_coverage_keys(self):
        coverage = build_sdr_coverage(metrics_count=0, dimensions_count=0, dimensions_only=True)
        payload = build_typed_json_payload(
            data_dict={"Dimensions": pd.DataFrame()},
            native_frames={},
            data_view={},
            metadata_dict={},
            coverage=coverage,
        )
        assert payload["schema_version"] == "cja-auto-sdr.sdr-typed/1"
        assert payload["collected_components"] == ["dimensions"]
        assert payload["coverage"]["families"][0]["state"] == "excluded"
        assert "coverage" not in build_typed_json_payload(
            data_dict={}, native_frames={}, data_view={}, metadata_dict={}
        )

    def test_notion_blocks_include_coverage_section(self):
        from cja_auto_sdr.output.writers.notion import build_sdr_blocks

        data_dict, _ = _writer_data_dict(metrics_count=1, dimensions_count=1)
        blocks = build_sdr_blocks(data_dict, {"Data View ID": "dv_1"})
        headings = [
            "".join(part["text"]["content"] for part in block["heading_2"]["rich_text"])
            for block in blocks
            if block.get("type") == "heading_2"
        ]
        assert any("Coverage" in heading for heading in headings)


# ---------------------------------------------------------------------------
# process_single_dataview integration
# ---------------------------------------------------------------------------


@pytest.fixture
def config_file(tmp_path):
    path = tmp_path / "config.json"
    path.write_text(json.dumps({"org_id": "o@AdobeOrg", "client_id": "c", "secret": "s", "scopes": "openid"}))
    return str(path)


def _frames():
    metrics = pd.DataFrame(
        [{"id": "m1", "name": "M1", "type": "standard", "description": "d", "title": "M1"}],
    )
    dimensions = pd.DataFrame(
        [{"id": "d1", "name": "D1", "type": "string", "description": "d", "title": "D1"}],
    )
    lookup = {"id": "dv_cov", "name": "Coverage View", "owner": {"name": "o"}}
    return metrics, dimensions, lookup


def _run(tmp_path, config_file, *, issues=(), **kwargs):
    from cja_auto_sdr.generator import process_single_dataview

    metrics, dimensions, lookup = _frames()
    with (
        patch("cja_auto_sdr.generator.setup_logging") as mock_setup_logging,
        patch("cja_auto_sdr.generator.initialize_cja") as mock_init,
        patch("cja_auto_sdr.generator.ParallelAPIFetcher") as mock_fetcher_class,
        patch("cja_auto_sdr.generator.DataQualityChecker") as mock_dq_class,
    ):
        logger = Mock()
        logger.handlers = []
        mock_setup_logging.return_value = logger
        mock_init.return_value = Mock()
        fetcher = Mock()
        fetcher.fetch_all_data.return_value = (metrics, dimensions, lookup)
        fetcher.get_fetch_statuses.return_value = {
            "metrics": EndpointFetchStatus(endpoint="metrics", status="success"),
            "dimensions": EndpointFetchStatus(endpoint="dimensions", status="success"),
        }
        fetcher.get_tuner_statistics.return_value = None
        mock_fetcher_class.return_value = fetcher
        dq = Mock()
        dq.issues = list(issues)
        dq.get_issues_dataframe.return_value = pd.DataFrame(
            list(issues), columns=["Severity", "Category", "Type", "Item Name", "Issue", "Details"]
        )
        mock_dq_class.return_value = dq
        return process_single_dataview(
            data_view_id="dv_cov",
            config_file=config_file,
            output_dir=str(tmp_path),
            **kwargs,
        )


def _only(tmp_path, pattern):
    matches = list(tmp_path.glob(pattern))
    assert len(matches) == 1, matches
    return matches[0]


class TestProcessSingleDataviewCoverage:
    def test_metrics_only_json_omits_dimensions_and_reports_coverage(self, tmp_path, config_file):
        result = _run(tmp_path, config_file, output_format="json", metrics_only=True)
        assert result.success is True
        payload = json.loads(_only(tmp_path, "*_SDR.json").read_text(encoding="utf-8"))
        assert payload["dimensions"] == []
        assert len(payload["metrics"]) == 1
        assert payload["collected_components"] == ["metrics"]
        states = {row["family"]: row["state"] for row in payload["coverage"]["families"]}
        assert states["dimensions"] == "excluded"
        assert states["metrics"] == "collected"
        assert states["segments"] == "not_requested"
        assert payload["coverage"]["quality"]["state"] == "ran"

    def test_dimensions_only_csv_bundle_has_coverage_and_no_metrics(self, tmp_path, config_file):
        result = _run(tmp_path, config_file, output_format="csv", dimensions_only=True)
        assert result.success is True
        csv_dir = _only(tmp_path, "*_csv")
        names = {p.name for p in csv_dir.iterdir()}
        assert "coverage.csv" in names
        assert "metrics.csv" not in names
        assert "dimensions.csv" in names
        manifest = json.loads((csv_dir / "_manifest.json").read_text(encoding="utf-8"))
        assert "coverage.csv" in {entry["name"] for entry in manifest["files"]}
        coverage = pd.read_csv(csv_dir / "coverage.csv")
        assert coverage.set_index("Family").loc["Metrics", "State"] == "excluded"

    def test_markdown_and_html_omit_excluded_family(self, tmp_path, config_file):
        result = _run(tmp_path, config_file, output_format="markdown", metrics_only=True)
        assert result.success is True
        text = _only(tmp_path, "*.md").read_text(encoding="utf-8")
        assert "## Coverage" in text
        assert "## Dimensions" not in text
        assert "## Metrics" in text

        html_dir = tmp_path / "html"
        html_dir.mkdir()
        result = _run(html_dir, config_file, output_format="html", metrics_only=True)
        assert result.success is True
        html_text = _only(html_dir, "*.html").read_text(encoding="utf-8")
        assert "Coverage</h2>" in html_text
        assert "Dimensions</h2>" not in html_text

    def test_excel_has_coverage_after_metadata_and_gate_rows(self, tmp_path, config_file):
        result = _run(
            tmp_path,
            config_file,
            output_format="excel",
            dimensions_only=True,
            issues=[_issue("HIGH")],
            fail_on_quality="HIGH",
        )
        assert result.success is True
        workbook = pd.read_excel(_only(tmp_path, "*.xlsx"), sheet_name=None, header=None)
        assert list(workbook)[:3] == ["Metadata", "Coverage", "Data Quality"]
        assert "Metrics" not in workbook
        metadata_text = workbook["Metadata"].astype(str).to_string()
        assert "Quality Gate Verdict" in metadata_text
        assert "FAIL" in metadata_text
        assert "Quality Gate Threshold" in metadata_text

    def test_skip_validation_excel_data_quality_sheet_shows_skip_detail(self, tmp_path, config_file):
        result = _run(tmp_path, config_file, output_format="excel", skip_validation=True)
        assert result.success is True
        workbook = pd.read_excel(_only(tmp_path, "*.xlsx"), sheet_name=None, header=None)
        dq_text = workbook["Data Quality"].astype(str).to_string()
        assert "Quality audit skipped: --skip-validation." in dq_text

    def test_json_typed_has_coverage(self, tmp_path, config_file):
        result = _run(tmp_path, config_file, output_format="json", json_typed=True, fail_on_quality="LOW")
        assert result.success is True
        payload = json.loads(_only(tmp_path, "*_SDR.json").read_text(encoding="utf-8"))
        assert payload["schema_version"] == "cja-auto-sdr.sdr-typed/1"
        assert payload["collected_components"] == ["metrics", "dimensions"]
        assert payload["coverage"]["quality"]["gate"] == {"threshold": "LOW", "verdict": "PASS"}
        assert payload["metadata"]["Quality Gate Verdict"] == "PASS"
        assert payload["metadata"]["Quality Gate Threshold"] == "LOW"

    def test_inventory_only_json_reports_standard_families_excluded(self, tmp_path, config_file):
        segments_inventory = Mock()
        segments_inventory.get_dataframe.return_value = pd.DataFrame([{"Segment Name": "S1"}])
        segments_inventory.get_summary.return_value = {"total_segments": 1}
        segments_inventory.to_json.return_value = {"segments": [{"name": "S1"}]}
        with patch("cja_auto_sdr.inventory.segments.SegmentsInventoryBuilder") as builder_class:
            builder_class.return_value.build.return_value = segments_inventory
            result = _run(
                tmp_path,
                config_file,
                output_format="json",
                inventory_only=True,
                include_segments_inventory=True,
            )
        assert result.success is True
        payload = json.loads(_only(tmp_path, "*_SDR.json").read_text(encoding="utf-8"))
        assert payload["collected_components"] == ["segments"]
        states = {row["family"]: row for row in payload["coverage"]["families"]}
        assert states["metrics"]["state"] == "excluded"
        assert states["segments"]["state"] == "collected"
        assert states["segments"]["count"] == 1

    def test_both_component_filters_keep_both_families(self, tmp_path, config_file):
        result = _run(tmp_path, config_file, output_format="json", metrics_only=True, dimensions_only=True)
        assert result.success is True
        payload = json.loads(_only(tmp_path, "*_SDR.json").read_text(encoding="utf-8"))
        assert payload["collected_components"] == ["metrics", "dimensions"]
        assert len(payload["metrics"]) == 1
        assert len(payload["dimensions"]) == 1


class TestEdgeCases:
    def test_skip_reason_passthrough_for_custom_detail(self):
        coverage = build_sdr_coverage(
            metrics_count=1, dimensions_count=1, validation_status="skipped", validation_status_detail="custom reason"
        )
        assert coverage.quality.line == "Quality audit skipped: custom reason."

    def test_not_evaluated_gate_line(self):
        coverage = build_sdr_coverage(
            metrics_count=1, dimensions_count=1, validation_status="skipped", fail_on_quality="HIGH"
        )
        assert coverage.quality.line.endswith("Quality gate at threshold HIGH not evaluated.")
        assert coverage.quality.metadata_rows() == [
            ("Quality Gate Verdict", "NOT_EVALUATED"),
            ("Quality Gate Threshold", "HIGH"),
        ]

    def test_failed_without_note(self):
        coverage = build_sdr_coverage(
            metrics_count=0, dimensions_count=0, fetch_statuses={"metrics": {"status": "failed"}}
        )
        row = _rows_by_family(coverage)["metrics"]
        assert row.detail == "Fetch failed: unavailable — not an empty result"
        assert row.label == "Fetch failed"


class TestFailOnQualityThreading:
    def test_worker_args_forward_fail_on_quality(self):
        from cja_auto_sdr.generator import WorkerArgs, process_single_dataview_worker

        with patch("cja_auto_sdr.generator.process_single_dataview") as mock_process:
            process_single_dataview_worker(WorkerArgs(data_view_id="dv_1", fail_on_quality="HIGH"))
        config = mock_process.call_args.kwargs["processing_config"]
        assert config.fail_on_quality == "HIGH"

    def test_batch_processor_forwards_fail_on_quality(self):
        from cja_auto_sdr.pipeline.batch import BatchProcessor
        from cja_auto_sdr.pipeline.models import BatchConfig

        with patch("cja_auto_sdr.generator.setup_logging", return_value=Mock()):
            processor = BatchProcessor(batch_config=BatchConfig(fail_on_quality="MEDIUM"))
        assert processor.fail_on_quality == "MEDIUM"
