"""Coverage-focused compatibility tests for generator discovery helpers.

These tests exercise the generator-side compatibility helpers that still
mirror the extracted implementations in ``cja_auto_sdr.cli.commands.list``.
The goal is to keep the refactor honest while also covering the remaining
generator-side discovery branches.
"""

from __future__ import annotations

import io
import json
import os
from contextlib import redirect_stdout
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

import cja_auto_sdr.generator as generator
from cja_auto_sdr.cli.commands import list as list_commands
from cja_auto_sdr.generator import DiscoveryNotFoundError


def _run_fetcher(fetcher, cja, *, is_machine_readable: bool, capture_stdout: bool = False) -> tuple[str | None, str]:
    if capture_stdout:
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            result = fetcher(cja, is_machine_readable)
        return result, stdout.getvalue()
    return fetcher(cja, is_machine_readable), ""


def _assert_generator_fetcher_matches_extracted(
    generator_fetcher,
    extracted_fetcher,
    cja_factory,
    *,
    is_machine_readable: bool,
    capture_stdout: bool = False,
) -> tuple[str | None, str]:
    generator_result, generator_stdout = _run_fetcher(
        generator_fetcher,
        cja_factory(),
        is_machine_readable=is_machine_readable,
        capture_stdout=capture_stdout,
    )
    extracted_result, extracted_stdout = _run_fetcher(
        extracted_fetcher,
        cja_factory(),
        is_machine_readable=is_machine_readable,
        capture_stdout=capture_stdout,
    )
    assert generator_result == extracted_result
    assert generator_stdout == extracted_stdout
    return generator_result, generator_stdout


@pytest.mark.parametrize(
    ("payload", "output_format", "is_machine_readable", "expected"),
    [
        ([], "json", True, {"dataViews": [], "count": 0}),
        (None, "csv", True, "id,name,owner\n"),
        ([], "table", False, "\nNo data views found or no access to any data views.\n"),
    ],
)
def test_fetch_dataviews_empty_outputs_match_extracted_module(
    payload,
    output_format: str,
    is_machine_readable: bool,
    expected,
) -> None:
    def cja_factory() -> MagicMock:
        cja = MagicMock()
        cja.getDataViews.return_value = payload
        return cja

    result, _ = _assert_generator_fetcher_matches_extracted(
        generator._fetch_dataviews(output_format=output_format),
        list_commands._fetch_dataviews(output_format=output_format),
        cja_factory,
        is_machine_readable=is_machine_readable,
    )

    if output_format == "json":
        assert json.loads(result) == expected
    else:
        assert result == expected


@pytest.mark.parametrize(
    ("output_format", "is_machine_readable"),
    [
        ("json", True),
        ("csv", True),
        ("table", False),
    ],
)
def test_fetch_dataviews_non_empty_outputs_match_extracted_module(
    output_format: str,
    is_machine_readable: bool,
) -> None:
    def cja_factory() -> MagicMock:
        cja = MagicMock()
        cja.getDataViews.return_value = pd.DataFrame(
            [
                {"id": "dv_2", "name": "Zulu", "owner": {"name": "Bob"}},
                {"id": "dv_1", "name": "Alpha", "owner": {"name": "Alice"}},
            ]
        )
        return cja

    result, _ = _assert_generator_fetcher_matches_extracted(
        generator._fetch_dataviews(output_format=output_format, sort_expression="name"),
        list_commands._fetch_dataviews(output_format=output_format, sort_expression="name"),
        cja_factory,
        is_machine_readable=is_machine_readable,
    )

    if output_format == "json":
        payload = json.loads(result)
        assert payload["count"] == 2
        assert payload["dataViews"][0]["name"] == "Alpha"
    elif output_format == "csv":
        assert result.startswith("id,name,owner\n")
        assert "dv_1,Alpha,Alice" in result
    else:
        assert "Found 2 accessible data view(s):" in result
        assert "Usage:" in result
        assert "Note: If multiple data views share the same name" in result


@pytest.mark.parametrize(("output_format", "is_machine_readable"), [("json", True), ("csv", True)])
def test_fetch_describe_dataview_machine_readable_outputs_match_extracted_module(
    output_format: str,
    is_machine_readable: bool,
) -> None:
    def cja_factory() -> MagicMock:
        cja = MagicMock()
        cja.getDataView.return_value = {
            "id": "dv_1",
            "name": "Revenue View",
            "owner": {"name": "Alice"},
            "description": "Primary reporting data view",
            "connectionId": "conn_1",
            "createdAt": "2025-01-01T00:00:00Z",
            "modifiedDate": "2025-01-02T00:00:00Z",
        }
        cja.getMetrics.return_value = [{"id": "m1"}, {"id": "m2"}]
        cja.getDimensions.return_value = [{"id": "d1"}]
        cja.getFilters.return_value = [{"id": "s1"}]
        cja.getCalculatedMetrics.return_value = [{"id": "cm1"}]
        return cja

    result, _ = _assert_generator_fetcher_matches_extracted(
        generator._fetch_describe_dataview("dv_1", output_format),
        list_commands._fetch_describe_dataview("dv_1", output_format),
        cja_factory,
        is_machine_readable=is_machine_readable,
    )

    if output_format == "json":
        payload = json.loads(result)
        assert payload["dataView"]["components"]["total"] == 5
        assert payload["dataView"]["connectionId"] == "conn_1"
    else:
        assert result.startswith("id,name,owner,description,connection_id,created,modified")
        assert "dv_1,Revenue View,Alice" in result


def test_fetch_describe_dataview_table_wraps_description_and_handles_na_total() -> None:
    terminal_size = os.terminal_size((48, 20))

    def cja_factory() -> MagicMock:
        cja = MagicMock()
        cja.getDataView.return_value = {
            "id": "dv_1",
            "name": "Wrapped View",
            "owner": {"name": "Alice"},
            "description": ("A deliberately long description that should wrap across multiple lines in table mode."),
            "parentDataGroupId": "conn_wrapped",
            "created": "2025-01-01",
            "modified": "2025-01-02",
        }
        cja.getMetrics.return_value = [{"id": "m1"}]
        cja.getDimensions.return_value = [{"id": "d1"}]
        cja.getFilters.side_effect = RuntimeError("segment lookup failed")
        cja.getCalculatedMetrics.return_value = []
        return cja

    with (
        patch("cja_auto_sdr.generator.shutil.get_terminal_size", return_value=terminal_size),
        patch("cja_auto_sdr.cli.commands.list.shutil.get_terminal_size", return_value=terminal_size),
        patch("cja_auto_sdr.cli.commands.discovery.shutil.get_terminal_size", return_value=terminal_size),
    ):
        result, _ = _assert_generator_fetcher_matches_extracted(
            generator._fetch_describe_dataview("dv_1", "table"),
            list_commands._fetch_describe_dataview("dv_1", "table"),
            cja_factory,
            is_machine_readable=False,
        )

    assert "Data View: Wrapped View" in result
    assert "Description:" in result
    assert "multiple lines in table mode." in result
    assert "Total:               N/A" in result


@pytest.mark.parametrize(
    ("output_format", "is_machine_readable"),
    [
        ("json", True),
        ("csv", True),
        ("table", False),
    ],
)
def test_fetch_metrics_list_outputs_match_extracted_module(
    output_format: str,
    is_machine_readable: bool,
) -> None:
    def cja_factory() -> MagicMock:
        cja = MagicMock()
        cja.getDataView.return_value = {"id": "dv_1", "name": "Metrics View"}
        cja.getMetrics.return_value = [
            {"id": "m_rev", "name": "Revenue", "type": "currency", "description": "Total revenue"},
            {"id": "m_orders", "name": "Orders", "type": "int", "description": "Order count"},
        ]
        return cja

    generator_fetcher = generator._fetch_metrics_list(
        "dv_1",
        output_format=output_format,
        data_view_name="Metrics View",
        filter_pattern="Revenue|Orders",
        exclude_pattern="Orders",
        limit=1,
        sort_expression="-name",
    )

    if output_format == "json":
        extracted_fetcher = list_commands._fetch_metrics_list(
            "dv_1",
            output_format=output_format,
            data_view_name="Metrics View",
            filter_pattern="Revenue|Orders",
            exclude_pattern="Orders",
            limit=1,
            sort_expression="-name",
        )
        generator_result, _ = _run_fetcher(generator_fetcher, cja_factory(), is_machine_readable=is_machine_readable)
        extracted_result, _ = _run_fetcher(extracted_fetcher, cja_factory(), is_machine_readable=is_machine_readable)
        result = generator_result
        assert json.loads(generator_result) == json.loads(extracted_result)
    elif output_format == "csv":
        result, _ = _assert_generator_fetcher_matches_extracted(
            generator_fetcher,
            list_commands._fetch_metrics_list(
                "dv_1",
                output_format=output_format,
                data_view_name="Metrics View",
                filter_pattern="Revenue|Orders",
                exclude_pattern="Orders",
                limit=1,
                sort_expression="-name",
            ),
            cja_factory,
            is_machine_readable=is_machine_readable,
        )
    else:
        result, _ = _run_fetcher(generator_fetcher, cja_factory(), is_machine_readable=is_machine_readable)

    if output_format == "json":
        payload = json.loads(result)
        assert payload["count"] == 1
        assert payload["metrics"][0]["name"] == "Revenue"
    elif output_format == "csv":
        assert "m_rev,Revenue,currency,Total revenue" in result
    else:
        assert "Found 1 metric(s) in data view 'Metrics View':" in result


@pytest.mark.parametrize(
    ("output_format", "is_machine_readable", "expected"),
    [
        ("json", True, {"count": 0, "metrics": []}),
        ("csv", True, "id,name,type,description\n"),
        ("table", False, "\nNo metrics found for data view 'dv_1'.\n"),
    ],
)
def test_fetch_metrics_list_empty_outputs_match_extracted_module(
    output_format: str,
    is_machine_readable: bool,
    expected,
) -> None:
    def cja_factory() -> MagicMock:
        cja = MagicMock()
        cja.getDataView.return_value = {"id": "dv_1", "name": "Metrics View"}
        cja.getMetrics.return_value = []
        return cja

    generator_fetcher = generator._fetch_metrics_list("dv_1", output_format=output_format)

    if output_format == "json":
        extracted_fetcher = list_commands._fetch_metrics_list("dv_1", output_format=output_format)
        generator_result, _ = _run_fetcher(generator_fetcher, cja_factory(), is_machine_readable=is_machine_readable)
        extracted_result, _ = _run_fetcher(extracted_fetcher, cja_factory(), is_machine_readable=is_machine_readable)
        result = generator_result
        generator_payload = json.loads(generator_result)
        extracted_payload = json.loads(extracted_result)
        assert generator_payload["metrics"] == extracted_payload["metrics"]
        assert generator_payload["count"] == extracted_payload["count"] == 0
        assert generator_payload["dataViewId"] == extracted_payload["dataViewId"] == "dv_1"
    elif output_format == "csv":
        result, _ = _assert_generator_fetcher_matches_extracted(
            generator_fetcher,
            list_commands._fetch_metrics_list("dv_1", output_format=output_format),
            cja_factory,
            is_machine_readable=is_machine_readable,
        )
    else:
        result, _ = _run_fetcher(generator_fetcher, cja_factory(), is_machine_readable=is_machine_readable)

    if output_format == "json":
        payload = json.loads(result)
        assert payload["count"] == expected["count"]
        assert payload["metrics"] == expected["metrics"]
    else:
        assert result == expected


def test_fetch_calculated_metrics_list_matches_extracted_module() -> None:
    def cja_factory() -> MagicMock:
        cja = MagicMock()
        cja.getDataView.return_value = {"id": "dv_1", "name": "Calc View"}
        cja.getCalculatedMetrics.return_value = [
            {
                "id": "cm_1",
                "name": "Margin",
                "description": "Margin percentage",
                "type": "percent",
                "polarity": "positive",
                "precision": "  ",
                "approved": True,
                "tags": [{"name": "finance"}, "kpi"],
                "owner": {"name": "Alice"},
                "createdAt": "2025-01-01",
                "modifiedDate": "2025-01-02",
            }
        ]
        return cja

    generator_result, _ = _run_fetcher(
        generator._fetch_calculated_metrics_list("dv_1", output_format="json"),
        cja_factory(),
        is_machine_readable=True,
    )
    extracted_result, _ = _run_fetcher(
        list_commands._fetch_calculated_metrics_list("dv_1", output_format="json"),
        cja_factory(),
        is_machine_readable=True,
    )

    assert json.loads(generator_result) == json.loads(extracted_result)

    payload = json.loads(generator_result)
    assert payload["count"] == 1
    assert payload["calculatedMetrics"][0]["approved"] is True
    assert payload["calculatedMetrics"][0]["precision"] == 0
    assert payload["calculatedMetrics"][0]["tags"] == ["finance", "kpi"]


@pytest.mark.parametrize(("output_format", "is_machine_readable"), [("json", True), ("csv", True), ("table", False)])
def test_fetch_connections_with_permission_fallback_matches_extracted_module(
    output_format: str,
    is_machine_readable: bool,
) -> None:
    def cja_factory() -> MagicMock:
        cja = MagicMock()
        cja.getConnections.return_value = []
        cja.getDataViews.return_value = pd.DataFrame(
            [
                {"id": "dv_1", "name": "Alpha", "parentDataGroupId": "conn_a"},
                {"id": "dv_2", "name": "Bravo", "parentDataGroupId": "conn_a"},
                {"id": "dv_3", "name": "Charlie", "parentDataGroupId": "conn_b"},
            ]
        )
        return cja

    result, _ = _assert_generator_fetcher_matches_extracted(
        generator._fetch_connections(output_format=output_format),
        list_commands._fetch_connections(output_format=output_format),
        cja_factory,
        is_machine_readable=is_machine_readable,
    )

    if output_format == "json":
        payload = json.loads(result)
        assert payload["count"] == 2
        assert "product-admin privileges" in payload["warning"]
    elif output_format == "csv":
        assert "connection_id,connection_name,owner,dataset_id,dataset_name,dataview_count" in result
        assert "conn_a,,,," in result
    else:
        assert "Found 2 connection(s) referenced by data views:" in result
        assert "conn_a  (2 data view(s))" in result


@pytest.mark.parametrize(
    ("output_format", "is_machine_readable", "expected"),
    [
        ("json", True, {"connections": [], "count": 0}),
        ("csv", True, "connection_id,connection_name,owner,dataset_id,dataset_name\n"),
        ("table", False, "\nNo connections found or no access to any connections.\n"),
    ],
)
def test_fetch_connections_empty_outputs_match_extracted_module(
    output_format: str,
    is_machine_readable: bool,
    expected,
) -> None:
    def cja_factory() -> MagicMock:
        cja = MagicMock()
        cja.getConnections.return_value = []
        cja.getDataViews.return_value = []
        return cja

    result, _ = _assert_generator_fetcher_matches_extracted(
        generator._fetch_connections(output_format=output_format),
        list_commands._fetch_connections(output_format=output_format),
        cja_factory,
        is_machine_readable=is_machine_readable,
    )

    if output_format == "json":
        assert json.loads(result) == expected
    else:
        assert result == expected


@pytest.mark.parametrize(("output_format", "is_machine_readable"), [("json", True), ("csv", True), ("table", False)])
def test_fetch_connections_accessible_outputs_match_extracted_module(
    output_format: str,
    is_machine_readable: bool,
) -> None:
    def cja_factory() -> MagicMock:
        cja = MagicMock()
        cja.getConnections.return_value = [
            {
                "id": "conn_1",
                "name": "Primary Connection",
                "ownerFullName": "Alice",
                "dataSets": [{"id": "ds_1", "name": "Dataset One"}],
            },
            {
                "id": "conn_2",
                "name": "Secondary Connection",
                "ownerFullName": "",
                "owner": {"name": "Bob"},
                "dataSets": "invalid-datasets",
            },
        ]
        return cja

    result, _ = _assert_generator_fetcher_matches_extracted(
        generator._fetch_connections(output_format=output_format),
        list_commands._fetch_connections(output_format=output_format),
        cja_factory,
        is_machine_readable=is_machine_readable,
    )

    if output_format == "json":
        payload = json.loads(result)
        assert payload["count"] == 2
        assert payload["connections"][0]["datasets"][0]["id"] == "ds_1"
    elif output_format == "csv":
        assert "conn_1,Primary Connection,Alice,ds_1,Dataset One" in result
        assert "conn_2,Secondary Connection,Bob,," in result
    else:
        assert "Connection: Primary Connection (conn_1)" in result
        assert "Datasets: (none)" in result


@pytest.mark.parametrize(
    ("output_format", "is_machine_readable", "capture_stdout", "expected"),
    [
        ("json", True, False, {"dataViews": [], "count": 0}),
        ("csv", True, False, "dataview_id,dataview_name,connection_id,connection_name,dataset_id,dataset_name\n"),
        ("table", False, True, "\nNo data views found or no access to any data views.\n"),
    ],
)
def test_fetch_datasets_empty_outputs_match_extracted_module(
    output_format: str,
    is_machine_readable: bool,
    capture_stdout: bool,
    expected,
) -> None:
    def cja_factory() -> MagicMock:
        cja = MagicMock()
        cja.getConnections.return_value = []
        cja.getDataViews.return_value = []
        return cja

    result, stdout = _assert_generator_fetcher_matches_extracted(
        generator._fetch_datasets(output_format=output_format),
        list_commands._fetch_datasets(output_format=output_format),
        cja_factory,
        is_machine_readable=is_machine_readable,
        capture_stdout=capture_stdout,
    )

    if output_format == "json":
        assert json.loads(result) == expected
    else:
        assert result == expected
    assert stdout == ""


@pytest.mark.parametrize(("output_format", "is_machine_readable"), [("json", True), ("csv", True), ("table", False)])
def test_fetch_datasets_without_connection_details_matches_extracted_module(
    output_format: str,
    is_machine_readable: bool,
) -> None:
    def cja_factory() -> MagicMock:
        cja = MagicMock()
        cja.getConnections.return_value = []
        cja.getDataViews.return_value = pd.DataFrame(
            [
                {"id": "dv_1", "name": "Alpha", "parentDataGroupId": "conn_a"},
                {"id": "dv_2", "name": "Bravo", "parentDataGroupId": "conn_b"},
            ]
        )
        return cja

    result, stdout = _assert_generator_fetcher_matches_extracted(
        generator._fetch_datasets(output_format=output_format),
        list_commands._fetch_datasets(output_format=output_format),
        cja_factory,
        is_machine_readable=is_machine_readable,
        capture_stdout=not is_machine_readable,
    )

    if output_format == "json":
        payload = json.loads(result)
        assert payload["count"] == 2
        assert "warning" in payload
    elif output_format == "csv":
        assert "dv_1,Alpha,conn_a" in result
    else:
        assert "Found 2 data view(s) with dataset information:" in result
        assert "Connection: conn_a" in result
        assert "Processing 2 data view(s)..." in stdout


@pytest.mark.parametrize(("output_format", "is_machine_readable"), [("json", True), ("csv", True), ("table", False)])
def test_fetch_datasets_with_connection_details_matches_extracted_module(
    output_format: str,
    is_machine_readable: bool,
) -> None:
    def cja_factory() -> MagicMock:
        cja = MagicMock()
        cja.getConnections.return_value = [
            {"id": "conn_1", "name": "Primary Connection", "dataSets": [{"id": "ds_1", "name": "Dataset One"}]},
            {"id": "conn_2", "name": "Secondary Connection", "dataSets": []},
        ]
        cja.getDataViews.return_value = [
            {"id": "dv_1", "name": "Alpha", "parentDataGroupId": "conn_1"},
            {"id": "dv_2", "name": "Bravo", "parentDataGroupId": "conn_2"},
            {"id": "dv_3", "name": "Orphan", "parentDataGroupId": ""},
        ]
        return cja

    result, stdout = _assert_generator_fetcher_matches_extracted(
        generator._fetch_datasets(output_format=output_format),
        list_commands._fetch_datasets(output_format=output_format),
        cja_factory,
        is_machine_readable=is_machine_readable,
        capture_stdout=not is_machine_readable,
    )

    if output_format == "json":
        payload = json.loads(result)
        assert payload["count"] == 3
        assert payload["dataViews"][0]["datasets"][0]["id"] == "ds_1"
    elif output_format == "csv":
        assert "dv_1,Alpha,conn_1,Primary Connection,ds_1,Dataset One" in result
        assert "dv_2,Bravo,conn_2,Secondary Connection,," in result
        assert "dv_3,Orphan,N/A,," in result
    else:
        assert "Connection: Primary Connection (conn_1)" in result
        assert "Connection: N/A" in result
        assert "Datasets: (none)" in result
        assert "Processing 3 data view(s)..." in stdout


@pytest.mark.parametrize(
    ("preferred_name", "expected"),
    [
        ("Preferred View", "Preferred View"),
        (None, "Unknown"),
    ],
)
def test_resolve_dataview_name_fallbacks_match_extracted_module(preferred_name: str | None, expected: str) -> None:
    cja_generator = MagicMock()
    cja_generator.getDataView.return_value = {
        "id": "dv_1",
        "name": "null",
        "ownerFullName": "Alice",
        "parentDataGroupId": "conn_1",
    }

    cja_extracted = MagicMock()
    cja_extracted.getDataView.return_value = {
        "id": "dv_1",
        "name": "null",
        "ownerFullName": "Alice",
        "parentDataGroupId": "conn_1",
    }

    assert generator._resolve_dataview_name(cja_generator, "dv_1", preferred_name=preferred_name) == expected
    assert list_commands._resolve_dataview_name(cja_extracted, "dv_1", preferred_name=preferred_name) == expected


def test_require_accessible_dataview_rejects_invalid_lookup_payload() -> None:
    cja = MagicMock()
    cja.getDataView.return_value = None

    with pytest.raises(DiscoveryNotFoundError, match="Data view 'dv_missing' not found"):
        generator._require_accessible_dataview(cja, "dv_missing")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"statusCode": 404, "message": "missing"}, "Failed to retrieve metrics"),
        (42, "Unexpected metrics payload type"),
    ],
)
def test_normalize_component_records_or_raise_handles_error_and_invalid_payloads(payload, message: str) -> None:
    with pytest.raises(DiscoveryNotFoundError, match=message):
        generator._normalize_component_records_or_raise(
            payload,
            component_label="metrics",
            data_view_id="dv_1",
        )


def test_apply_discovery_filters_and_sort_handles_non_numeric_values_in_numeric_sort() -> None:
    rows = [
        {"name": "Alpha", "count": None},
        {"name": "Bravo", "count": "5"},
        {"name": "Charlie", "count": "2"},
    ]

    result = generator._apply_discovery_filters_and_sort(rows, sort_expression="count")

    assert [row["name"] for row in result] == ["Charlie", "Bravo", "Alpha"]


def test_segment_and_calculated_metric_display_rows_match_extracted_module() -> None:
    item = {
        "id": "item_1",
        "name": "Segment or Metric",
        "description": "Desc",
        "approved": True,
        "tags": [{"name": "tag-a"}, "tag-b"],
        "owner": {"name": "Alice"},
        "precision": "  ",
        "type": "percent",
        "polarity": "positive",
        "createdAt": "2025-01-01",
        "modifiedDate": "2025-01-02",
    }

    assert generator._build_segment_display_row(item) == list_commands._build_segment_display_row(item)
    assert generator._build_calculated_metric_display_row(item) == list_commands._build_calculated_metric_display_row(
        item
    )
