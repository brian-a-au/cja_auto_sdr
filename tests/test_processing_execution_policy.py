"""Unit tests for process_single_dataview execution-policy derivation."""

import json
import sys
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from cja_auto_sdr.api.quality import DataQualityChecker
from cja_auto_sdr.generator import _build_processing_execution_policy, main


@pytest.mark.parametrize(
    (
        "output_format",
        "inventory_only",
        "include_derived_inventory",
        "metrics_only",
        "dimensions_only",
        "quality_report_only",
        "skip_validation",
        "expected_required_components",
        "expected_inventory_omits_standard",
        "expected_embedded_metadata",
        "expected_validation_required",
        "expected_run_validation",
    ),
    [
        ("excel", False, False, False, False, False, False, {"metrics", "dimensions"}, False, False, True, True),
        ("excel", False, False, True, False, False, False, {"metrics"}, False, False, True, True),
        ("excel", False, False, False, True, False, False, {"dimensions"}, False, False, True, True),
        ("json", True, False, False, False, False, False, set(), True, True, False, False),
        ("html", True, False, False, False, False, False, set(), True, True, False, False),
        ("markdown", True, False, False, False, False, False, set(), True, True, False, False),
        ("all", True, False, False, False, False, False, set(), True, True, False, False),
        ("json", True, True, False, False, False, False, {"metrics", "dimensions"}, True, True, False, False),
        ("json", False, False, False, False, True, False, {"metrics", "dimensions"}, False, True, True, True),
        ("json", False, False, False, False, True, True, {"metrics", "dimensions"}, False, True, True, False),
        # notion must emit embedded metadata so the Notion page gets real SDR metadata
        # (Data View Name, Data View ID, timestamp) rather than falling back to base_filename.
        ("notion", False, False, False, False, False, False, {"metrics", "dimensions"}, False, True, True, True),
    ],
)
def test_build_processing_execution_policy_matrix(
    output_format,
    inventory_only,
    include_derived_inventory,
    metrics_only,
    dimensions_only,
    quality_report_only,
    skip_validation,
    expected_required_components,
    expected_inventory_omits_standard,
    expected_embedded_metadata,
    expected_validation_required,
    expected_run_validation,
):
    policy = _build_processing_execution_policy(
        output_format=output_format,
        inventory_only=inventory_only,
        include_derived_inventory=include_derived_inventory,
        metrics_only=metrics_only,
        dimensions_only=dimensions_only,
        quality_report_only=quality_report_only,
        skip_validation=skip_validation,
    )

    assert policy.required_component_endpoints == frozenset(expected_required_components)
    assert policy.inventory_only_omits_standard_sections is expected_inventory_omits_standard
    assert policy.emits_embedded_metadata is expected_embedded_metadata
    assert policy.validation_required_for_output is expected_validation_required
    assert policy.run_data_quality_validation is expected_run_validation


@pytest.mark.parametrize("mode", ["default", "partial", "quality_gate", "skip"])
def test_inner_validation_failure_reaches_cli_policy_and_summary(mode, tmp_path):
    metrics = pd.DataFrame(
        {"id": ["m1", "m2"], "name": ["Duplicate", "Duplicate"], "type": ["int", "int"]},
    )
    dimensions = pd.DataFrame({"id": ["d1"], "name": ["Dimension"], "type": ["string"]})
    fetcher = Mock()
    fetcher.fetch_all_data.return_value = (metrics, dimensions, {"id": "dv_test", "name": "Test"})
    summary_file = tmp_path / "summary.json"
    output_file = tmp_path / "sdr.json"
    argv = [
        "cja_auto_sdr",
        "dv_test",
        "--format",
        "json",
        "--output",
        str(output_file),
        "--run-summary-json",
        str(summary_file),
        "--quiet",
    ]
    argv.extend(
        {
            "default": [],
            "partial": ["--allow-partial"],
            "quality_gate": ["--fail-on-quality", "HIGH"],
            "skip": ["--skip-validation"],
        }[mode]
    )
    original_add = DataQualityChecker.add_issue
    collected = []

    def fail_after_finding(checker, **kwargs):
        issue = original_add(checker, **kwargs)
        collected.append(issue)
        if kwargs["item_type"] == "Metrics" and kwargs["category"] == "Duplicates":
            raise ValueError("injected check failure after finding")
        return issue

    with (
        patch.object(sys, "argv", argv),
        patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_test"], {})),
        patch("cja_auto_sdr.generator.initialize_cja", return_value=Mock()),
        patch("cja_auto_sdr.generator.setup_logging", return_value=Mock()),
        patch("cja_auto_sdr.generator.ParallelAPIFetcher", return_value=fetcher),
        patch.object(DataQualityChecker, "add_issue", fail_after_finding),
    ):
        if mode in {"default", "quality_gate"}:
            with pytest.raises(SystemExit) as caught:
                main()
            assert caught.value.code == 1
        else:
            main()

    payload = json.loads(summary_file.read_text())
    result = payload["results"][0]
    assert result["dq_issues_count"] == 0
    assert result["dq_severity_counts"] == {}
    assert payload["quality_gate_failed"] is False
    if mode in {"default", "quality_gate"}:
        assert any(issue["Severity"] == "HIGH" for issue in collected)
        assert result["failure_code"] == "DQ_VALIDATION_RUNTIME_FAILED"
        assert "injected check failure" in result["error_message"]
        assert payload["exit_code"] == 1
        assert not output_file.exists()
    else:
        assert result["success"] is True
        assert output_file.exists()
        report = json.loads(output_file.read_text())
        metadata = report["metadata"]
        if mode == "partial":
            assert result["partial_output"] is True
            assert result["partial_reasons"] == ["data_quality_validation_runtime_failed"]
            assert metadata["Data Quality Validation Status"] == "Failed"
        else:
            assert collected == []
            assert result["partial_output"] is False
            assert metadata["Data Quality Validation Status"] == "Skipped"
