from __future__ import annotations

import json
import logging
import subprocess
import sys
from copy import deepcopy
from unittest.mock import MagicMock

import pandas as pd
import pytest

from cja_auto_sdr.diff.models import DataViewSnapshot
from cja_auto_sdr.diff.snapshot import SnapshotManager
from cja_auto_sdr.inventory.calculated_metrics import CalculatedMetricsInventoryBuilder
from cja_auto_sdr.inventory.segments import SegmentsInventoryBuilder


@pytest.fixture
def mock_cja():
    cja = MagicMock()
    cja.getDataView.return_value = {
        "id": "dv_abc123",
        "name": "Test Data View",
        "owner": {"name": "Alice"},
        "description": "",
    }
    cja.getMetrics.return_value = pd.DataFrame([{"id": "metrics/pageviews", "name": "Page Views", "type": "count"}])
    cja.getDimensions.return_value = pd.DataFrame([{"id": "variables/page", "name": "Page", "type": "string"}])
    return cja


@pytest.fixture
def snapshot_manager():
    return SnapshotManager(logger=logging.getLogger("test.diff.snapshot"))


def test_create_snapshot_fails_closed_on_error_shape_getdataview_payload(snapshot_manager, mock_cja):
    mock_cja.getDataView.return_value = {"statusCode": 500, "message": "backend timeout"}

    with pytest.raises(Exception) as excinfo:
        snapshot_manager.create_snapshot(mock_cja, "dv_abc123")

    assert getattr(excinfo.value, "_cja_snapshot_failure_stage", None) == "data_view_lookup"
    assert "500" in str(excinfo.value) or "backend timeout" in str(excinfo.value)


def test_create_snapshot_fails_closed_on_error_shape_getmetrics_payload(snapshot_manager, mock_cja):
    mock_cja.getMetrics.return_value = {"statusCode": 503, "message": "backend timeout"}

    with pytest.raises(Exception) as excinfo:
        snapshot_manager.create_snapshot(mock_cja, "dv_abc123")

    assert getattr(excinfo.value, "_cja_snapshot_failure_stage", None) == "metrics_fetch"
    assert not (
        isinstance(excinfo.value, AttributeError)
        and "empty" in str(excinfo.value)
        and getattr(excinfo.value, "_cja_snapshot_failure_stage", None) is None
    )


def test_create_snapshot_fails_closed_on_error_shape_getdimensions_payload(snapshot_manager, mock_cja):
    mock_cja.getDimensions.return_value = {"statusCode": 503, "message": "backend timeout"}

    with pytest.raises(Exception) as excinfo:
        snapshot_manager.create_snapshot(mock_cja, "dv_abc123")

    assert getattr(excinfo.value, "_cja_snapshot_failure_stage", None) == "dimensions_fetch"


def test_create_snapshot_succeeds_on_valid_payloads(snapshot_manager, mock_cja):
    snapshot = snapshot_manager.create_snapshot(mock_cja, "dv_abc123")
    assert snapshot.data_view_id == "dv_abc123"
    assert snapshot.data_view_name == "Test Data View"
    assert len(snapshot.metrics) == 1
    assert len(snapshot.dimensions) == 1


def test_create_snapshot_does_not_leak_attributeerror_on_dict_metrics(snapshot_manager, mock_cja):
    mock_cja.getMetrics.return_value = {"statusCode": 503, "message": "backend timeout"}

    with pytest.raises(Exception) as excinfo:
        snapshot_manager.create_snapshot(mock_cja, "dv_abc123")

    assert getattr(excinfo.value, "_cja_snapshot_failure_stage", None) == "metrics_fetch"
    assert not isinstance(excinfo.value, AttributeError)


@pytest.mark.parametrize(
    ("inventory", "change", "field", "old_value", "new_value"),
    [
        ("calculated_metrics_inventory", "rename", "name", "Original metric", "Renamed metric"),
        ("segments_inventory", "rename", "name", "Original segment", "Renamed segment"),
        (
            "segments_inventory",
            "reference",
            "segment_references",
            ["original"],
            ["replacement"],
        ),
    ],
)
def test_serialized_inventory_changes_reach_snapshot_cli(
    snapshot_manager, tmp_path, inventory, change, field, old_value, new_value
):
    """Production inventory keys must survive snapshot storage and CLI comparison."""
    if inventory == "calculated_metrics_inventory":
        raw = {
            "id": "cm_1",
            "name": old_value,
            "definition": {
                "func": "calc-metric",
                "formula": {
                    "func": "divide",
                    "col1": {"func": "metric", "name": "metrics/revenue"},
                    "col2": {"func": "metric", "name": "metrics/orders"},
                },
            },
        }
        builder = CalculatedMetricsInventoryBuilder()._process_metric
        flag = "--include-calculated"
        serialized_key = "metric_name"
        diff_key = "calculated_metrics_diffs"
        summary_key = "calculated_metrics"
    else:
        raw = {
            "id": "s_1",
            "name": "Original segment",
            "definition": {
                "func": "container",
                "context": "hits",
                "pred": {"func": "segment", "segment": {"id": "segments/original"}},
            },
        }
        builder = SegmentsInventoryBuilder()._process_segment
        flag = "--include-segments"
        serialized_key = "segment_name" if change == "rename" else "other_segment_references"
        diff_key = "segments_diffs"
        summary_key = "segments"

    changed = deepcopy(raw)
    if change == "rename":
        changed["name"] = new_value
    else:
        changed["definition"]["pred"]["segment"]["id"] = f"segments/{new_value[0]}"
    source_item = builder(raw).to_full_dict()
    target_item = builder(changed).to_full_dict()
    assert source_item[serialized_key] == old_value
    assert target_item[serialized_key] == new_value

    source = DataViewSnapshot(data_view_id="dv_1", data_view_name="Test", **{inventory: [source_item]})
    target = DataViewSnapshot(data_view_id="dv_1", data_view_name="Test", **{inventory: [target_item]})
    source_file = tmp_path / "source.json"
    target_file = tmp_path / "target.json"
    snapshot_manager.save_snapshot(source, str(source_file))
    snapshot_manager.save_snapshot(target, str(target_file))
    before = (source_file.read_bytes(), target_file.read_bytes())

    command = [
        sys.executable,
        "-m",
        "cja_auto_sdr",
        "--compare-snapshots",
        str(source_file),
        str(target_file),
        flag,
        "--format",
        "json",
        "--output",
        "-",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    payload = json.loads(result.stdout)
    assert result.returncode == 2
    assert payload["summary"]["has_changes"] is True
    assert payload["inventory_summary"][summary_key]["modified"] == 1
    item_diff = payload[diff_key][0]
    assert item_diff["change_type"] == "modified"
    assert item_diff["changed_fields"][field] == {"source": old_value, "target": new_value}
    assert set(item_diff["changed_fields"]) == ({field, "definition_json"} if change == "reference" else {field})
    assert item_diff["source_data"] == source_item
    assert item_diff["target_data"] == target_item
    assert (source_file.read_bytes(), target_file.read_bytes()) == before

    unselected = subprocess.run([part for part in command if part != flag], capture_output=True, text=True, check=False)
    assert unselected.returncode == 0
    assert json.loads(unselected.stdout)["summary"]["has_changes"] is False

    ignored = subprocess.run([*command, "--ignore-fields", field], capture_output=True, text=True, check=False)
    assert ignored.returncode == 0
    assert json.loads(ignored.stdout)["summary"]["has_changes"] is False


@pytest.mark.parametrize("kind", ["segment", "calculated_metric"])
def test_hidden_definition_changes_reach_offline_cli(snapshot_manager, tmp_path, kind):
    if kind == "segment":
        definition = {
            "func": "container",
            "context": "hits",
            "pred": {
                "func": "and",
                "preds": [
                    {
                        "func": "streq",
                        "dimension": "variables/replacement" if i == 0 else "variables/page",
                        "val": str(i),
                    }
                    for i in range(4)
                ],
            },
        }
        raw = {"id": "s_1", "name": "Segment", "definition": definition}
        builder = SegmentsInventoryBuilder()._process_segment
        inventory, flag, diff_key = "segments_inventory", "--include-segments", "segments_diffs"
        changed = deepcopy(raw)
        changed["definition"]["pred"]["preds"][3]["val"] = "hidden change"
    else:
        raw = {
            "id": "cm_1",
            "name": "Metric",
            "definition": {
                "func": "calc-metric",
                "formula": {
                    "func": "add",
                    "col1": {"func": "metric", "name": "metrics/orders"},
                    "col2": {"func": "number", "value": 4},
                },
            },
        }
        builder = CalculatedMetricsInventoryBuilder()._process_metric
        inventory, flag, diff_key = "calculated_metrics_inventory", "--include-calculated", "calculated_metrics_diffs"
        changed = deepcopy(raw)
        changed["definition"]["formula"]["col2"]["value"] = 5
    items = [builder(value).to_full_dict() for value in (raw, changed)]
    assert {k: v for k, v in items[0].items() if k != "definition_json"} == {
        k: v for k, v in items[1].items() if k != "definition_json"
    }
    files = [tmp_path / "source.json", tmp_path / "target.json"]
    for file, item in zip(files, items, strict=True):
        snapshot_manager.save_snapshot(
            DataViewSnapshot(data_view_id="dv_1", data_view_name="Test", **{inventory: [item]}), str(file)
        )
    command = [
        sys.executable,
        "-m",
        "cja_auto_sdr",
        "--compare-snapshots",
        *map(str, files),
        flag,
        "--format",
        "json",
        "--output",
        "-",
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    assert result.returncode == 2
    assert set(json.loads(result.stdout)[diff_key][0]["changed_fields"]) == {"definition_json"}

    filtered = subprocess.run([*command, "--changes-only"], capture_output=True, text=True, check=False)
    assert filtered.returncode == 2
    assert len(json.loads(filtered.stdout)[diff_key]) == 1
    threshold = subprocess.run([*command, "--warn-threshold", "0"], capture_output=True, text=True, check=False)
    assert threshold.returncode == 2  # Inventory-only edits preserve component percentage semantics.
    snapshot_manager.save_snapshot(
        DataViewSnapshot(
            data_view_id="dv_1",
            data_view_name="Test",
            metrics=[{"id": "m", "name": "added"}],
            **{inventory: [items[1]]},
        ),
        str(files[1]),
    )
    threshold = subprocess.run([*command, "--warn-threshold", "0"], capture_output=True, text=True, check=False)
    assert threshold.returncode == 3
    snapshot_manager.save_snapshot(
        DataViewSnapshot(data_view_id="dv_1", data_view_name="Test", **{inventory: [items[1]]}), str(files[1])
    )
    ignored = subprocess.run(
        [*command, "--ignore-fields", "definition_json"], capture_output=True, text=True, check=False
    )
    assert ignored.returncode == 0
    if kind == "segment":
        # Fourth predicate references are beyond the abbreviated summary.
        changed["definition"]["pred"]["preds"][3]["dimension"] = "variables/replacement"
        item = builder(changed).to_full_dict()
        snapshot_manager.save_snapshot(
            DataViewSnapshot(data_view_id="dv_1", data_view_name="Test", **{inventory: [item]}), str(files[1])
        )
        simultaneous = subprocess.run(
            [*command, "--ignore-fields", "dimension_references"], capture_output=True, text=True, check=False
        )
        assert simultaneous.returncode == 2
        changed["definition"]["pred"]["preds"][3]["val"] = "3"
        item = builder(changed).to_full_dict()
        snapshot_manager.save_snapshot(
            DataViewSnapshot(data_view_id="dv_1", data_view_name="Test", **{inventory: [item]}), str(files[1])
        )
        reference_only = subprocess.run(
            [*command, "--ignore-fields", "dimension_references"], capture_output=True, text=True, check=False
        )
        assert reference_only.returncode == 0
    # Malformed nonempty paired input fails through the CLI error contract.
    item = deepcopy(items[1])
    item["definition_json"] = "invalid"
    snapshot_manager.save_snapshot(
        DataViewSnapshot(data_view_id="dv_1", data_view_name="Test", **{inventory: [item]}), str(files[1])
    )
    malformed = subprocess.run(command, capture_output=True, text=True, check=False)
    assert malformed.returncode == 1
    assert "definition_json" in malformed.stderr
    opt_out = subprocess.run([part for part in command if part != flag], capture_output=True, text=True, check=False)
    assert opt_out.returncode == 0
    assert json.loads(opt_out.stdout)["summary"]["has_changes"] is False
    omitted = subprocess.run(
        [*command, "--ignore-fields", "definition_json"], capture_output=True, text=True, check=False
    )
    assert omitted.returncode == 0
    item.pop("definition_json")
    snapshot_manager.save_snapshot(
        DataViewSnapshot(data_view_id="dv_1", data_view_name="Test", **{inventory: [item]}), str(files[0])
    )
    legacy = subprocess.run(command, capture_output=True, text=True, check=False)
    assert legacy.returncode == 0
    assert json.loads(legacy.stdout)["summary"]["has_changes"] is False
    assert "missing or empty definition_json" in legacy.stderr
