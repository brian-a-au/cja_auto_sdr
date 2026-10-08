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
    assert item_diff["changed_fields"] == {field: {"source": old_value, "target": new_value}}
    assert item_diff["source_data"] == source_item
    assert item_diff["target_data"] == target_item
    assert (source_file.read_bytes(), target_file.read_bytes()) == before

    unselected = subprocess.run([part for part in command if part != flag], capture_output=True, text=True, check=False)
    assert unselected.returncode == 0
    assert json.loads(unselected.stdout)["summary"]["has_changes"] is False

    ignored = subprocess.run([*command, "--ignore-fields", field], capture_output=True, text=True, check=False)
    assert ignored.returncode == 0
    assert json.loads(ignored.stdout)["summary"]["has_changes"] is False
