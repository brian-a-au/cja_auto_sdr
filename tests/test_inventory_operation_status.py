"""Failed optional inventories must read as unavailable, never as empty (AE3)."""

import json
import logging
from unittest.mock import MagicMock, Mock

import pandas as pd
import pytest

from cja_auto_sdr import generator
from cja_auto_sdr.inventory.calculated_metrics import CalculatedMetricsInventoryBuilder
from cja_auto_sdr.inventory.derived_fields import DerivedFieldInventoryBuilder
from cja_auto_sdr.inventory.segments import SegmentsInventoryBuilder

BUILDERS = {
    "derived": DerivedFieldInventoryBuilder,
    "calculated": CalculatedMetricsInventoryBuilder,
    "segments": SegmentsInventoryBuilder,
}
FLAGS = {
    "derived": "include_derived_inventory",
    "calculated": "include_calculated_metrics",
    "segments": "include_segments_inventory",
}
SECTIONS = {"derived": "derived_fields", "calculated": "calculated_metrics", "segments": "segments"}
RECORDS = {"derived": "fields", "calculated": "metrics", "segments": "segments"}
STATUS_ROWS = {
    "derived": "Derived Fields Inventory Status",
    "calculated": "Calculated Metrics Inventory Status",
    "segments": "Segments Inventory Status",
}
UNAVAILABLE = {
    "derived": "Derived field inventory unavailable",
    "calculated": "Calculated metrics inventory unavailable",
    "segments": "Segments inventory unavailable",
}
NOTE = "Inventory collection failed; see logs. This is not an empty result."


@pytest.fixture
def run(monkeypatch, tmp_path):
    logger = logging.getLogger("inventory_status")
    metrics = pd.DataFrame([{"id": "m1", "name": "Metric", "type": "int", "description": "Metric", "title": "Metric"}])
    dimensions = pd.DataFrame([{"id": "d1", "name": "Dim", "type": "string", "description": "Dim", "title": "Dim"}])
    fetcher = Mock()
    fetcher.fetch_all_data.return_value = (metrics, dimensions, {"id": "dv_test", "name": "Test"})
    monkeypatch.setattr(generator, "initialize_cja", Mock(return_value=Mock()))
    monkeypatch.setattr(generator, "ParallelAPIFetcher", Mock(return_value=fetcher))
    monkeypatch.setattr(generator, "setup_logging", Mock(return_value=logger))

    def go(behaviors, **kwargs):
        """behaviors: key -> 'empty' | 'error' | 'import_error' (requested inventories)."""
        for key, behavior in behaviors.items():
            if behavior == "empty":
                inventory = MagicMock()
                inventory.__bool__.return_value = False  # empty inventory falls back to placeholder records
                inventory.get_dataframe.return_value = pd.DataFrame()
                inventory.get_summary.return_value = {}
                inventory.to_json.return_value = {}
                mock = Mock(return_value=inventory)
            elif behavior == "error":
                mock = Mock(side_effect=RuntimeError("boom"))
            else:
                mock = Mock(side_effect=ImportError("missing"))
            monkeypatch.setattr(BUILDERS[key], "build", mock)
        flags = {FLAGS[key]: True for key in behaviors}
        destination = tmp_path / "out.json"
        result = generator.process_single_dataview(
            "dv_test",
            output_dir=str(tmp_path),
            output_file=str(destination),
            output_format="json",
            **flags,
            **kwargs,
        )
        payload = json.loads(destination.read_text()) if destination.exists() else None
        return result, payload

    return go


@pytest.mark.parametrize("key", ["derived", "calculated", "segments"])
@pytest.mark.parametrize("behavior", ["error", "import_error"])
def test_failed_inventory_renders_unavailable_not_empty(run, key, behavior):
    result, payload = run({key: behavior})
    assert result.success
    assert result.inventory_statuses == {key: "failed"}
    record = payload[SECTIONS[key]][RECORDS[key]][0]
    assert record["Status"] == UNAVAILABLE[key]
    assert "No " not in record["Status"]
    assert record["Note"] == NOTE
    assert payload["metadata"][STATUS_ROWS[key]] == "failed"


@pytest.mark.parametrize(
    ("key", "text"),
    [
        ("derived", "No derived fields found for this data view"),
        ("calculated", "No calculated metrics found for this data view"),
        ("segments", "No segments found for this data view"),
    ],
)
def test_empty_successful_inventory_says_no_items_found(run, key, text):
    result, payload = run({key: "empty"})
    assert result.inventory_statuses == {key: "completed"}
    assert payload[SECTIONS[key]][RECORDS[key]][0]["Status"] == text
    assert payload["metadata"][STATUS_ROWS[key]] == "completed"


def test_unrequested_inventory_has_no_status_row(run):
    result, payload = run({"segments": "empty"})
    assert result.inventory_statuses == {"segments": "completed"}
    assert STATUS_ROWS["segments"] in payload["metadata"]
    assert STATUS_ROWS["derived"] not in payload["metadata"]
    assert STATUS_ROWS["calculated"] not in payload["metadata"]
    result, payload = run({})
    assert result.inventory_statuses == {}
    assert not [k for k in payload["metadata"] if k.endswith("Inventory Status")]


def test_import_failure_marks_failed_and_keeps_exit_code(run):
    result, _ = run({"segments": "import_error"})
    assert result.success
    assert result.inventory_statuses == {"segments": "failed"}
    assert result.partial_output is False
    assert result.partial_reasons == []
    assert result.failure_code == ""


def test_parallel_inventory_statuses_per_key(run):
    result, payload = run({"derived": "empty", "calculated": "error", "segments": "error"})
    assert result.inventory_statuses == {"derived": "completed", "calculated": "failed", "segments": "failed"}
    assert payload["metadata"][STATUS_ROWS["derived"]] == "completed"
    assert payload["metadata"][STATUS_ROWS["calculated"]] == "failed"
    assert payload["calculated_metrics"]["metrics"][0]["Status"] == UNAVAILABLE["calculated"]
    assert payload["derived_fields"]["fields"][0]["Status"].startswith("No derived fields")


def test_inventory_only_json_carries_statuses(run):
    result, payload = run({"segments": "error"}, inventory_only=True)
    assert result.inventory_statuses == {"segments": "failed"}
    assert payload["metadata"][STATUS_ROWS["segments"]] == "failed"
    assert payload["segments"]["segments"][0]["Status"] == UNAVAILABLE["segments"]


def test_statuses_agree_across_json_metadata_and_run_summary(run):
    result, payload = run({"derived": "empty", "segments": "error"})
    summary = generator._processing_result_to_summary(result)
    assert summary["inventory_statuses"] == {"derived": "completed", "segments": "failed"}
    assert payload["metadata"][STATUS_ROWS["derived"]] == summary["inventory_statuses"]["derived"]
    assert payload["metadata"][STATUS_ROWS["segments"]] == summary["inventory_statuses"]["segments"]


def test_failed_inventory_renders_unavailable_sheet_in_excel(run, monkeypatch, tmp_path):
    import zipfile

    monkeypatch.setattr(SegmentsInventoryBuilder, "build", Mock(side_effect=RuntimeError("boom")))
    destination = tmp_path / "report.xlsx"
    result = generator.process_single_dataview(
        "dv_test",
        output_dir=str(tmp_path),
        output_file=str(destination),
        output_format="excel",
        inventory_only=True,
        include_segments_inventory=True,
    )
    assert result.success
    with zipfile.ZipFile(destination) as workbook:
        strings = workbook.read("xl/sharedStrings.xml").decode()
    assert "Segments inventory unavailable" in strings
    assert "No segments found" not in strings


def test_metadata_dataframe_status_rows_only_for_requested():
    frame = generator._build_sdr_metadata_dataframe(
        data_view_id="dv",
        lookup_data={"name": "n"},
        metrics=pd.DataFrame(),
        dimensions=pd.DataFrame(),
        fetch_statuses={},
        validation_status="ok",
        validation_status_detail="",
        dq_issues=[],
        severity_counts={},
        partial_reasons=None,
        segments_inventory_obj=None,
        calculated_inventory_obj=None,
        derived_inventory_obj=None,
        inventory_statuses={"derived": "not_requested", "segments": "failed"},
    )
    rows = dict(zip(frame["Property"], frame["Value"], strict=True))
    assert rows["Segments Inventory Status"] == "failed"
    assert "Derived Fields Inventory Status" not in rows
