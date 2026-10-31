"""Raw-response validation for cjapy metrics/dimensions fetches.

cjapy's ``getMetrics``/``getDimensions`` build ``pd.DataFrame(res.get("content", []))``,
so an API error body (403/500 JSON, or the connector's ``{"error": "Request Error"}``
stub) silently becomes an empty DataFrame. These tests drive a real ``cjapy.CJA``
instance over a scripted connector and assert that error pages are surfaced as
failures while a genuine ``content: []`` stays empty.
"""

from __future__ import annotations

import logging
from typing import Any
from unittest.mock import MagicMock

import cjapy
import pandas as pd
import pytest

from cja_auto_sdr.api.fetch import (
    ComponentFetchFailure,
    ParallelAPIFetcher,
    classify_component_payload,
    fetch_component_payload,
)
from cja_auto_sdr.core.perf import PerformanceTracker

DV_ID = "dv_test123"


class _ScriptedConnector:
    """Connector stand-in returning scripted responses per endpoint suffix."""

    def __init__(self, responses: dict[str, list[Any]]):
        self._responses = {key: list(value) for key, value in responses.items()}
        self.calls: list[tuple[str, dict]] = []

    def getData(self, endpoint: str, params: dict | None = None, **_kwargs: Any) -> Any:
        self.calls.append((endpoint, dict(params or {})))
        for suffix, queue in self._responses.items():
            if endpoint.endswith(suffix):
                return queue.pop(0)
        return {"id": DV_ID, "name": "Test DV"}


def _native_cja(responses: dict[str, list[Any]]) -> cjapy.CJA:
    cja = cjapy.CJA.__new__(cjapy.CJA)
    cja.connector = _ScriptedConnector(responses)
    cja.endpoint = "https://cja.example.test"
    cja.loggingEnabled = False
    cja.logger = None
    return cja


def _page(rows: list[dict], *, last: bool = True) -> dict:
    return {"content": rows, "lastPage": last, "totalElements": len(rows)}


FORBIDDEN = {"errorCode": "403003", "errorDescription": "Forbidden", "statusCode": 403, "message": "Access denied"}


class TestFetchComponentPayload:
    def test_success_matches_cjapy_dataframe(self):
        rows = [{"id": "metrics/a", "name": "A", "extra": 1}, {"id": "metrics/b", "name": "B"}]
        cja = _native_cja({"/metrics": [_page(rows)]})
        result = fetch_component_payload(cja, "metrics", DV_ID, inclType=True, full=True)
        pd.testing.assert_frame_equal(result, pd.DataFrame(rows))
        endpoint, params = cja.connector.calls[0]
        assert endpoint.endswith(f"/data/dataviews/{DV_ID}/metrics")
        assert "expansion" in params

    def test_pagination_accumulates_pages(self):
        cja = _native_cja(
            {"/dimensions": [_page([{"id": "variables/a"}], last=False), _page([{"id": "variables/b"}])]},
        )
        result = fetch_component_payload(cja, "dimensions", DV_ID, inclType=True, full=True)
        assert list(result["id"]) == ["variables/a", "variables/b"]

    def test_genuine_empty_content_stays_empty(self):
        cja = _native_cja({"/dimensions": [_page([])]})
        result = fetch_component_payload(cja, "dimensions", DV_ID, inclType=True, full=True)
        assert isinstance(result, pd.DataFrame)
        assert result.empty
        assert classify_component_payload(result).status == "empty"

    @pytest.mark.parametrize("empty_error", [None, "", [], {}])
    def test_null_or_empty_error_keys_on_valid_page_are_not_failures(self, empty_error):
        page = {**_page([{"id": "variables/a"}]), "error": empty_error, "errorCode": empty_error}
        cja = _native_cja({"/dimensions": [page]})
        result = fetch_component_payload(cja, "dimensions", DV_ID, inclType=True, full=True)
        assert isinstance(result, pd.DataFrame)
        assert list(result["id"]) == ["variables/a"]

    @pytest.mark.parametrize(
        ("payload", "expected_reason"),
        [
            (FORBIDDEN, "error_payload"),
            ({"error": "Request Error"}, "error_payload"),
            ({"error_code": "500", "message": "boom"}, "error_payload"),
            ({"statusCode": 500, "message": "Internal"}, "http_status"),
            ({"totalElements": 0}, "missing_content"),
            ({"content": "nope"}, "missing_content"),
            ({"content": [{"name": "no id"}]}, "row_missing_id"),
            ({"content": ["not-a-dict"]}, "row_missing_id"),
            ("plain text body", "non_mapping_page"),
        ],
    )
    def test_error_pages_become_failures(self, payload, expected_reason):
        cja = _native_cja({"/dimensions": [payload]})
        result = fetch_component_payload(cja, "dimensions", DV_ID, inclType=True, full=True)
        assert isinstance(result, ComponentFetchFailure)
        assert result.reason == expected_reason
        assert DV_ID in result.message
        assert "dimensions" in result.message
        outcome = classify_component_payload(result)
        assert outcome.status == "failed"
        assert outcome.reason == expected_reason
        assert outcome.error_message == result.message

    def test_failure_message_carries_error_code_and_status(self):
        cja = _native_cja({"/metrics": [FORBIDDEN]})
        result = fetch_component_payload(cja, "metrics", DV_ID, inclType=True, full=True)
        assert result["statusCode"] == 403
        assert result["errorCode"] == "403003"
        assert "403003" in result.message
        assert "Access denied" in result.message

    def test_error_on_later_page_fails_whole_fetch(self):
        cja = _native_cja({"/metrics": [_page([{"id": "metrics/a"}], last=False), {"error": "Request Error"}]})
        result = fetch_component_payload(cja, "metrics", DV_ID, inclType=True, full=True)
        assert isinstance(result, ComponentFetchFailure)

    def test_non_native_client_uses_method_result_unchanged(self):
        frame = pd.DataFrame([{"id": "metrics/a"}])
        cja = MagicMock()
        cja.getMetrics.return_value = frame
        assert fetch_component_payload(cja, "metrics", DV_ID, inclType=True, full=True) is frame
        cja.getMetrics.assert_called_once_with(DV_ID, inclType=True, full=True)

    def test_instance_patched_method_on_native_client_is_honored(self):
        cja = _native_cja({})
        frame = pd.DataFrame([{"id": "variables/a"}])
        cja.getDimensions = MagicMock(return_value=frame)
        assert fetch_component_payload(cja, "dimensions", DV_ID, inclType="hidden", full=True) is frame

    def test_fetch_with_expansion_pages_with_narrow_params(self):
        cja = _native_cja(
            {
                "/metrics": [
                    _page([{"id": "metrics/a", "name": "A", "type": "int"}], last=False),
                    _page([{"id": "metrics/b", "name": "B", "sourceFieldType": "derived"}]),
                ],
            },
        )
        result = fetch_component_payload(
            cja, "metrics", DV_ID, inclType=True, full=True, expansion="type,sourceFieldType"
        )
        assert isinstance(result, pd.DataFrame)
        assert list(result["id"]) == ["metrics/a", "metrics/b"]
        assert list(result["name"]) == ["A", "B"]
        assert len(cja.connector.calls) == 2
        for page_number, (endpoint, params) in enumerate(cja.connector.calls):
            assert endpoint == f"https://cja.example.test/data/dataviews/{DV_ID}/metrics"
            assert params == {"page": page_number, "expansion": "type,sourceFieldType"}

    def test_fetch_with_expansion_error_body_returns_failure(self):
        cja = _native_cja({"/dimensions": [_page([{"id": "variables/a"}], last=False), {"totalElements": 0}]})
        result = fetch_component_payload(cja, "dimensions", DV_ID, expansion="type,sourceFieldType")
        assert isinstance(result, ComponentFetchFailure)
        assert result.reason == "missing_content"
        assert DV_ID in result.message
        assert "dimensions" in result.message

    def test_fetch_with_expansion_forwards_hidden_include_type(self):
        cja = _native_cja({"/dimensions": [_page([{"id": "variables/a"}])]})
        fetch_component_payload(cja, "dimensions", DV_ID, inclType="hidden", expansion="type")
        assert cja.connector.calls[0][1] == {"page": 0, "expansion": "type", "includeType": "hidden"}

    def test_fetch_with_expansion_ignored_by_test_doubles(self):
        frame = pd.DataFrame([{"id": "variables/a"}])
        cja = MagicMock()
        cja.getDimensions.return_value = frame
        assert fetch_component_payload(cja, "dimensions", DV_ID, expansion="type,sourceFieldType") is frame
        cja.getDimensions.assert_called_once_with(DV_ID, inclType=True, full=True)

    def test_unknown_component_rejected(self):
        with pytest.raises(ValueError, match="Unsupported component"):
            fetch_component_payload(MagicMock(), "segments", DV_ID)


class TestCallSitesFailClosed:
    def test_parallel_fetcher_marks_forbidden_dimensions_failed(self):
        cja = _native_cja({"/metrics": [_page([{"id": "metrics/a"}])], "/dimensions": [FORBIDDEN]})
        logger = logging.getLogger("test_component_fetch_validation")
        fetcher = ParallelAPIFetcher(cja, logger, PerformanceTracker(logger), max_workers=1, quiet=True)
        metrics, dimensions, _info = fetcher.fetch_all_data(DV_ID)
        statuses = fetcher.get_fetch_statuses()
        assert len(metrics) == 1
        assert dimensions.empty
        assert statuses["metrics"].status == "success"
        assert statuses["dimensions"].status == "failed"
        assert statuses["dimensions"].reason == "error_payload"
        assert "403003" in statuses["dimensions"].error_message

    def test_parallel_fetcher_keeps_genuine_empty(self):
        cja = _native_cja({"/metrics": [_page([{"id": "metrics/a"}])], "/dimensions": [_page([])]})
        logger = logging.getLogger("test_component_fetch_validation")
        fetcher = ParallelAPIFetcher(cja, logger, PerformanceTracker(logger), max_workers=1, quiet=True)
        fetcher.fetch_all_data(DV_ID)
        assert fetcher.get_fetch_statuses()["dimensions"].status == "empty"

    def test_snapshot_creation_fails_closed_on_forbidden_dimensions(self):
        from cja_auto_sdr.diff.snapshot import SnapshotManager

        cja = _native_cja({"/metrics": [_page([{"id": "metrics/a"}])], "/dimensions": [FORBIDDEN]})
        with pytest.raises(ValueError, match="Dimensions fetch returned error payload"):
            SnapshotManager(logging.getLogger("snap")).create_snapshot(cja, DV_ID, quiet=True)

    def test_org_analyzer_records_forbidden_dimensions_as_error(self):
        from cja_auto_sdr.org.analyzer import OrgComponentAnalyzer
        from cja_auto_sdr.org.models import OrgReportConfig

        cja = _native_cja({"/metrics": [_page([{"id": "metrics/a"}])], "/dimensions": [FORBIDDEN]})
        analyzer = OrgComponentAnalyzer(cja, OrgReportConfig(), logging.getLogger("org"))
        analyzer._thread_local.cja = cja
        summary = analyzer._fetch_data_view_components({"id": DV_ID, "name": "Test DV"})
        assert summary.error
        assert "dimensions" in summary.error
        assert DV_ID in summary.error

    def test_org_analyzer_genuine_empty_is_not_error(self):
        from cja_auto_sdr.org.analyzer import OrgComponentAnalyzer
        from cja_auto_sdr.org.models import OrgReportConfig

        cja = _native_cja({"/metrics": [_page([{"id": "metrics/a"}])], "/dimensions": [_page([])]})
        analyzer = OrgComponentAnalyzer(cja, OrgReportConfig(), logging.getLogger("org"))
        analyzer._thread_local.cja = cja
        summary = analyzer._fetch_data_view_components({"id": DV_ID, "name": "Test DV"})
        assert not summary.error
        assert summary.metric_count == 1
        assert summary.dimension_count == 0


class TestDiscoveryComponentCounts:
    def test_describe_counts_forbidden_dimensions_as_unavailable(self):
        from cja_auto_sdr.cli.commands.discovery import (
            _DIMENSIONS_COMPONENT_FETCH_SPEC,
            _METRICS_COMPONENT_FETCH_SPEC,
            _count_component_items_for_fetch_spec,
        )

        cja = _native_cja({"/metrics": [_page([{"id": "metrics/a"}])], "/dimensions": [FORBIDDEN]})
        assert _count_component_items_for_fetch_spec(cja, DV_ID, _METRICS_COMPONENT_FETCH_SPEC) == 1
        assert _count_component_items_for_fetch_spec(cja, DV_ID, _DIMENSIONS_COMPONENT_FETCH_SPEC) == "N/A"
        _endpoint, params = cja.connector.calls[-1]
        assert params.get("includeType") == "hidden"
