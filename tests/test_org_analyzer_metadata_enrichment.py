from __future__ import annotations

import logging
from unittest.mock import MagicMock

import pandas as pd
import pytest

from cja_auto_sdr.org.analyzer import OrgComponentAnalyzer
from cja_auto_sdr.org.models import OrgReportConfig


@pytest.fixture
def analyzer_with_metadata_enabled(monkeypatch):
    cja = MagicMock()
    cja.getMetrics.return_value = pd.DataFrame([{"id": "metrics/pageviews", "name": "Page Views", "type": "count"}])
    cja.getDimensions.return_value = pd.DataFrame([{"id": "variables/page", "name": "Page", "type": "string"}])
    config = OrgReportConfig(include_metadata=True)
    analyzer = OrgComponentAnalyzer(
        cja=cja,
        config=config,
        logger=logging.getLogger("cja_auto_sdr.org.analyzer"),
        org_id="test_org@AdobeOrg",
    )
    monkeypatch.setattr(analyzer, "_get_thread_client", lambda: cja)
    return analyzer, cja


def test_metadata_enrichment_logs_warning_on_error_shape_getdataview(
    analyzer_with_metadata_enabled,
    caplog,
):
    analyzer, cja = analyzer_with_metadata_enabled
    cja.getDataView.return_value = {"statusCode": 500, "message": "backend timeout"}

    dv = {"id": "dv_abc123", "name": "Test DV"}
    with caplog.at_level(logging.WARNING, logger="cja_auto_sdr.org.analyzer"):
        summary = analyzer._fetch_data_view_components(dv)

    assert summary.data_view_id == "dv_abc123"
    assert summary.owner is None
    assert any("metadata" in record.message.lower() and "dv_abc123" in record.message for record in caplog.records), (
        f"expected metadata warning for dv_abc123, got: {[r.message for r in caplog.records]}"
    )


def test_metadata_enrichment_populates_fields_on_valid_payload(analyzer_with_metadata_enabled):
    analyzer, cja = analyzer_with_metadata_enabled
    cja.getDataView.return_value = {
        "id": "dv_abc123",
        "name": "Test DV",
        "owner": {"name": "Alice", "id": "user_123"},
        "description": "hello",
        "created": "2026-04-20T00:00:00Z",
        "modified": "2026-04-22T00:00:00Z",
    }

    dv = {"id": "dv_abc123", "name": "Test DV"}
    summary = analyzer._fetch_data_view_components(dv)

    assert summary.owner == "Alice"
    assert summary.created == "2026-04-20T00:00:00Z"
    assert summary.has_description is True


def test_metadata_enrichment_logs_warning_on_getdataview_exception(
    analyzer_with_metadata_enabled,
    caplog,
):
    analyzer, cja = analyzer_with_metadata_enabled
    cja.getDataView.side_effect = RuntimeError("backend timeout")

    dv = {"id": "dv_abc123", "name": "Test DV"}
    with caplog.at_level(logging.WARNING, logger="cja_auto_sdr.org.analyzer"):
        summary = analyzer._fetch_data_view_components(dv)

    assert summary.data_view_id == "dv_abc123"
    assert summary.owner is None
    assert summary.owner_id is None
    assert summary.created is None
    assert summary.modified is None
    assert summary.description is None
    assert summary.has_description is False
    assert any(
        "metadata fetch raised" in record.message.lower()
        and "dv_abc123" in record.message
        and "backend timeout" in record.message
        for record in caplog.records
    ), f"expected raised-exception warning for dv_abc123, got: {[r.message for r in caplog.records]}"
