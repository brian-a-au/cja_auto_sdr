from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pandas as pd
import pytest

from cja_auto_sdr.diff.snapshot import SnapshotManager


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
