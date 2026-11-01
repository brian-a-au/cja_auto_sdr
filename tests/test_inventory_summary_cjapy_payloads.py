from __future__ import annotations

import logging
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest


@pytest.fixture
def mock_cja():
    cja = MagicMock()
    cja.getDataView.return_value = {
        "id": "dv_abc123",
        "name": "Inventory Data View",
        "owner": {"name": "Alice"},
    }
    cja.getMetrics.return_value = pd.DataFrame([])
    cja.getDimensions.return_value = pd.DataFrame([])
    return cja


@patch("cja_auto_sdr.generator.initialize_cja")
@patch("cja_auto_sdr.generator.setup_logging")
def test_inventory_summary_returns_error_on_error_shape_getdataview(
    mock_setup_logging,
    mock_initialize_cja,
    mock_cja,
    capsys,
):
    from cja_auto_sdr.generator import process_inventory_summary

    mock_setup_logging.return_value = MagicMock()
    mock_initialize_cja.return_value = mock_cja
    mock_cja.getDataView.return_value = {"statusCode": 500, "message": "backend timeout"}

    result = process_inventory_summary(data_view_id="dv_abc123", include_derived=True)

    assert "error" in result
    assert "500" in result["error"] or "backend timeout" in result["error"]
    stderr = capsys.readouterr().err
    assert "ERROR" in stderr


@patch("cja_auto_sdr.generator.initialize_cja")
@patch("cja_auto_sdr.generator.setup_logging")
def test_derived_inventory_step_handles_error_shape_metrics_payload(
    mock_setup_logging,
    mock_initialize_cja,
    mock_cja,
    caplog,
):
    from cja_auto_sdr.generator import process_inventory_summary

    mock_setup_logging.return_value = logging.getLogger("test.inventory_summary")
    mock_initialize_cja.return_value = mock_cja
    mock_cja.getMetrics.return_value = {"statusCode": 503, "message": "backend timeout"}

    with caplog.at_level(logging.WARNING, logger="test.inventory_summary"):
        result = process_inventory_summary(data_view_id="dv_abc123", include_derived=True, quiet=True)

    assert "error" not in result
    assert "derived_fields" not in result.get("inventories", {})
    warning_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "derived fields inventory" in warning_text
    assert "object_error_shape" in warning_text
    assert "503" in warning_text


@patch("cja_auto_sdr.generator.initialize_cja")
@patch("cja_auto_sdr.generator.setup_logging")
def test_inventory_summary_succeeds_on_valid_lookup(mock_setup_logging, mock_initialize_cja, mock_cja):
    from cja_auto_sdr.generator import process_inventory_summary

    mock_setup_logging.return_value = MagicMock()
    mock_initialize_cja.return_value = mock_cja

    result = process_inventory_summary(data_view_id="dv_abc123", include_derived=False, quiet=True)

    assert "error" not in result
    assert result.get("data_view_id") == "dv_abc123"


@patch("cja_auto_sdr.generator.initialize_cja")
@patch("cja_auto_sdr.generator.setup_logging")
def test_derived_inventory_step_does_not_raise_on_error_dimensions_payload(
    mock_setup_logging,
    mock_initialize_cja,
    mock_cja,
    caplog,
):
    from cja_auto_sdr.generator import process_inventory_summary

    mock_setup_logging.return_value = logging.getLogger("test.inventory_summary")
    mock_initialize_cja.return_value = mock_cja
    mock_cja.getDimensions.return_value = {"statusCode": 500, "message": "dims down"}

    with caplog.at_level(logging.WARNING, logger="test.inventory_summary"):
        result = process_inventory_summary(data_view_id="dv_abc123", include_derived=True, quiet=True)

    assert "error" not in result
    assert "derived_fields" not in result.get("inventories", {})
    warning_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "derived fields inventory" in warning_text
    assert "object_error_shape" in warning_text
    assert "500" in warning_text


# ==================== dimensions prefetch (PERF-7) ====================


def _run_derived_summary(mock_cja, fake_fetch, caplog=None):
    from cja_auto_sdr.generator import process_inventory_summary

    with (
        patch("cja_auto_sdr.generator.initialize_cja", return_value=mock_cja),
        patch("cja_auto_sdr.generator.setup_logging", return_value=logging.getLogger("test.inventory_summary")),
        patch("cja_auto_sdr.generator._fetch_validated_component_payload", side_effect=fake_fetch),
    ):
        return process_inventory_summary(data_view_id="dv_abc123", include_derived=True, quiet=True)


def test_inventory_summary_overlaps_component_fetches(mock_cja):
    import threading

    dims_started = threading.Event()
    seen = {}

    def fake_fetch(cja, kind, data_view_id, **kwargs):
        if kind == "dimensions":
            dims_started.set()
            return pd.DataFrame([])
        seen["overlapped"] = dims_started.wait(timeout=5)
        return pd.DataFrame([])

    result = _run_derived_summary(mock_cja, fake_fetch)

    assert seen["overlapped"] is True
    assert "error" not in result
    assert "derived_fields" in result.get("inventories", {})


def test_inventory_summary_metrics_error_still_reported_and_dimensions_joined(mock_cja, caplog):
    import threading
    import time

    dims_started = threading.Event()
    dims_finished = threading.Event()

    def fake_fetch(cja, kind, data_view_id, **kwargs):
        if kind == "dimensions":
            dims_started.set()
            time.sleep(0.05)
            dims_finished.set()
            return pd.DataFrame([])
        dims_started.wait(timeout=5)
        return {"statusCode": 503, "message": "metrics down"}

    with caplog.at_level(logging.WARNING, logger="test.inventory_summary"):
        result = _run_derived_summary(mock_cja, fake_fetch)

    assert "error" not in result
    assert "derived_fields" not in result.get("inventories", {})
    warning_text = "\n".join(record.getMessage() for record in caplog.records)
    assert "metrics fetch returned error payload" in warning_text
    assert "503" in warning_text
    assert dims_finished.is_set()
