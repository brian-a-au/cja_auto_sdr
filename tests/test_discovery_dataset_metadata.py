"""Contracts for connection-scoped dataset metadata in dataset discovery JSON."""

from __future__ import annotations

import csv
import io
import json
from unittest.mock import MagicMock

import pandas as pd
import pytest

from cja_auto_sdr.cli.commands.discovery import _extract_dataset_info, _fetch_datasets


def _run_dataset_fetch(
    *,
    connections: list[dict] | None = None,
    data_views: list[dict] | None = None,
    output_format: str = "json",
    filter_pattern: str | None = None,
    exclude_pattern: str | None = None,
    sort_expression: str | None = None,
) -> tuple[str, MagicMock]:
    cja = MagicMock()
    cja.getConnections.return_value = connections or []
    cja.getDataViews.return_value = data_views or []
    result = _fetch_datasets(
        output_format,
        filter_pattern=filter_pattern,
        exclude_pattern=exclude_pattern,
        sort_expression=sort_expression,
    )(cja, output_format in {"json", "csv"})
    assert isinstance(result, str)
    return result, cja


@pytest.mark.parametrize("dataset_type", ["event", "profile", "lookup", "summary"])
def test_dataset_role_is_retained_without_inference(dataset_type: str) -> None:
    result = _extract_dataset_info(
        {"id": "ds_1", "name": "Neutral Name", "type": dataset_type},
        include_connection_metadata=True,
    )

    assert result == {
        "id": "ds_1",
        "name": "Neutral Name",
        "connectionMetadata": {"role": dataset_type},
    }


def test_dataset_metadata_normalizes_schema_identity_lookup_and_ingestion() -> None:
    result = _extract_dataset_info(
        {
            "dataSetId": "ds_lookup",
            "dataSetName": "Account Lookup",
            "type": "lookup",
            "schemaInfo": {
                "schemaId": "schema_1",
                "schemaName": "Account Schema",
                "schemaRef": {"id": "ref_1", "contentType": "application/vnd.adobe.xed-full+json;version=1"},
            },
            "timestampId": "_repo.timestamp",
            "visitorId": "person.id",
            "identityNamespace": "ECID",
            "usePrimaryIdNamespace": False,
            "identityMap": False,
            "identityNamespaceCol": "_repo.identity.namespace",
            "lookupKeyField": "accountId",
            "lookupParentFields": ["accountId", "region"],
            "lookupParentDataSetId": "ds_event",
            "lookupParentDataSetType": "event",
            "streaming": False,
            "backfillSummary": {
                "total": 4,
                "failed": 1,
                "inProgress": 0,
                "completed": 3,
                "invalid": False,
            },
            "lastIngestedTime": "2026-08-29T12:34:56Z",
            "streamingEnabledAt": "2026-01-02T03:04:05Z",
            "dataSourceType": {"id": "webData", "type": "Web Data", "description": "Browser events"},
        },
        include_connection_metadata=True,
    )

    assert result == {
        "id": "ds_lookup",
        "name": "Account Lookup",
        "connectionMetadata": {
            "role": "lookup",
            "schema": {
                "id": "schema_1",
                "name": "Account Schema",
                "ref": {
                    "id": "ref_1",
                    "contentType": "application/vnd.adobe.xed-full+json;version=1",
                },
            },
            "identity": {
                "timestampId": "_repo.timestamp",
                "visitorId": "person.id",
                "namespace": "ECID",
                "usePrimaryIdNamespace": False,
                "identityMap": False,
                "namespaceColumn": "_repo.identity.namespace",
            },
            "lookup": {
                "keyField": "accountId",
                "parentFields": ["accountId", "region"],
                "parentDatasetId": "ds_event",
                "parentDatasetType": "event",
            },
            "ingestion": {
                "streaming": False,
                "backfillSummary": {
                    "total": 4,
                    "failed": 1,
                    "inProgress": 0,
                    "completed": 3,
                    "invalid": False,
                },
                "lastIngestedTime": "2026-08-29T12:34:56Z",
                "streamingEnabledAt": "2026-01-02T03:04:05Z",
            },
            "dataSource": {"id": "webData", "type": "Web Data", "description": "Browser events"},
        },
    }


def test_missing_metadata_preserves_existing_dataset_contract_exactly() -> None:
    assert _extract_dataset_info(
        {"dataset_id": "ds_legacy", "dataset_name": "Legacy"},
        include_connection_metadata=True,
    ) == {"id": "ds_legacy", "name": "Legacy"}


@pytest.mark.parametrize(("value", "expected"), [("accountId", "accountId"), (None, None)])
def test_lookup_parent_fields_preserve_documented_scalar_and_null(value, expected) -> None:
    result = _extract_dataset_info(
        {"id": "ds_lookup", "name": "Lookup", "lookupParentFields": value},
        include_connection_metadata=True,
    )

    assert result["connectionMetadata"]["lookup"]["parentFields"] == expected


def test_explicit_null_false_and_empty_metadata_remain_distinct() -> None:
    result = _extract_dataset_info(
        {
            "id": "ds_1",
            "name": "Dataset \udcff",
            "type": None,
            "schemaInfo": {},
            "identityNamespace": "",
            "usePrimaryIdNamespace": False,
            "lookupParentFields": [],
            "streaming": False,
            "backfillSummary": None,
            "dataSourceType": {},
        },
        include_connection_metadata=True,
    )

    assert result["name"] == "Dataset \udcff"
    assert result["connectionMetadata"] == {
        "role": None,
        "schema": {},
        "identity": {"namespace": "", "usePrimaryIdNamespace": False},
        "lookup": {"parentFields": []},
        "ingestion": {"streaming": False, "backfillSummary": None},
        "dataSource": {},
    }
    assert "timestampId" not in result["connectionMetadata"]["identity"]


def test_malformed_optional_metadata_is_omitted_from_strict_json() -> None:
    result = _extract_dataset_info(
        {
            "id": "ds_1",
            "name": "Dataset",
            "type": {"not": "text"},
            "schemaInfo": ["not", "an", "object"],
            "timestampId": pd.NA,
            "identityMap": "false",
            "lookupParentFields": ["valid", {"bad": "field"}],
            "streaming": 0,
            "backfillSummary": {"total": float("nan"), "failed": "one", "invalid": 0},
            "lastIngestedTime": {"bad": "timestamp"},
            "dataSourceType": "webData",
        },
        include_connection_metadata=True,
    )

    assert result == {"id": "ds_1", "name": "Dataset"}
    assert json.loads(json.dumps(result, allow_nan=False)) == result


def test_repeated_dataset_ids_keep_connection_scoped_metadata_separate() -> None:
    output, cja = _run_dataset_fetch(
        connections=[
            {
                "id": "conn_event",
                "name": "Events",
                "dataSets": [{"dataSetId": "ds_shared", "name": "Shared", "type": "event", "streaming": True}],
            },
            {
                "id": "conn_lookup",
                "name": "Lookups",
                "dataSets": [
                    {
                        "dataSetId": "ds_shared",
                        "name": "Shared",
                        "type": "lookup",
                        "lookupKeyField": "id",
                        "streaming": False,
                    }
                ],
            },
        ],
        data_views=[
            {"id": "dv_event", "name": "Event View", "parentDataGroupId": "conn_event"},
            {"id": "dv_lookup", "name": "Lookup View", "parentDataGroupId": "conn_lookup"},
        ],
    )

    payload = json.loads(output)
    by_id = {item["id"]: item for item in payload["dataViews"]}
    assert by_id["dv_event"]["datasets"][0]["connectionMetadata"] == {
        "role": "event",
        "ingestion": {"streaming": True},
    }
    assert by_id["dv_lookup"]["datasets"][0]["connectionMetadata"] == {
        "role": "lookup",
        "lookup": {"keyField": "id"},
        "ingestion": {"streaming": False},
    }
    cja.getConnections.assert_called_once_with(
        output="raw",
        expansion=("name,ownerFullName,dataSets,schemaInfo,dataSetLastIngested,backfillsSummaryDataSets"),
    )


def test_permission_degraded_dataset_discovery_remains_id_only() -> None:
    output, _ = _run_dataset_fetch(
        connections=[],
        data_views=[{"id": "dv_1", "name": "View", "parentDataGroupId": "conn_hidden"}],
    )

    payload = json.loads(output)
    assert payload["dataViews"] == [
        {
            "id": "dv_1",
            "name": "View",
            "connection": {"id": "conn_hidden", "name": None},
            "datasets": [],
        }
    ]
    assert "product-admin privileges" in payload["warning"]


@pytest.mark.parametrize("output_format", ["csv", "table"])
def test_tabular_output_ignores_enriched_metadata(output_format: str) -> None:
    output, cja = _run_dataset_fetch(
        connections=[
            {
                "id": "conn_1",
                "name": "Connection",
                "dataSets": [
                    {
                        "id": "ds_1",
                        "name": "Dataset",
                        "type": "event",
                        "schemaInfo": {"schemaId": "schema_1"},
                        "streaming": False,
                    }
                ],
            }
        ],
        data_views=[{"id": "dv_1", "name": "View", "parentDataGroupId": "conn_1"}],
        output_format=output_format,
    )

    if output_format == "csv":
        assert list(csv.reader(io.StringIO(output))) == [
            ["dataview_id", "dataview_name", "connection_id", "connection_name", "dataset_id", "dataset_name"],
            ["dv_1", "View", "conn_1", "Connection", "ds_1", "Dataset"],
        ]
    else:
        assert "ds_1  Dataset" in output
        assert "schema_1" not in output
        assert "streaming" not in output
    cja.getConnections.assert_called_once_with(output="raw", expansion="name,ownerFullName,dataSets")


def test_filtering_and_sorting_still_use_enriched_dataset_rows() -> None:
    output, _ = _run_dataset_fetch(
        connections=[
            {"id": "conn_z", "name": "Zed", "dataSets": [{"id": "ds_z", "name": "Keep Me", "type": "event"}]},
            {"id": "conn_a", "name": "Alpha", "dataSets": [{"id": "ds_a", "name": "Drop Me", "type": "lookup"}]},
        ],
        data_views=[
            {"id": "dv_z", "name": "Zulu", "parentDataGroupId": "conn_z"},
            {"id": "dv_a", "name": "Alpha", "parentDataGroupId": "conn_a"},
        ],
        filter_pattern="Keep Me|Drop Me",
        sort_expression="name",
    )

    payload = json.loads(output)
    assert [item["id"] for item in payload["dataViews"]] == ["dv_a", "dv_z"]
    assert payload["dataViews"][0]["datasets"][0]["connectionMetadata"]["role"] == "lookup"


@pytest.mark.parametrize("output_format", ["json", "csv", "table"])
def test_metadata_only_terms_do_not_change_legacy_filter_or_exclude(output_format: str) -> None:
    kwargs = {
        "connections": [
            {
                "id": "conn_1",
                "name": "Connection",
                "dataSets": [{"id": "ds_1", "name": "Neutral Dataset", "type": "lookup"}],
            }
        ],
        "data_views": [{"id": "dv_1", "name": "Neutral View", "parentDataGroupId": "conn_1"}],
        "output_format": output_format,
    }

    filtered, _ = _run_dataset_fetch(filter_pattern="lookup", **kwargs)
    excluded, _ = _run_dataset_fetch(exclude_pattern="lookup", **kwargs)

    if output_format == "json":
        assert json.loads(filtered) == {"dataViews": [], "count": 0}
        assert json.loads(excluded)["dataViews"][0]["datasets"][0]["connectionMetadata"]["role"] == "lookup"
    elif output_format == "csv":
        assert len(list(csv.reader(io.StringIO(filtered)))) == 1
        assert len(list(csv.reader(io.StringIO(excluded)))) == 2
    else:
        assert "Found 0 data view(s)" in filtered
        assert "Neutral Dataset" in excluded


def test_dataset_sort_uses_legacy_id_and_name_projection() -> None:
    output, _ = _run_dataset_fetch(
        connections=[
            {
                "id": "conn_alpha",
                "name": "Connection Alpha",
                "dataSets": [{"id": "ds_same", "name": "Alpha", "type": "zzz"}],
            },
            {
                "id": "conn_zulu",
                "name": "Connection Zulu",
                "dataSets": [{"id": "ds_same", "name": "Zulu", "type": "aaa"}],
            },
        ],
        data_views=[
            {"id": "dv_zulu", "name": "Zulu View", "parentDataGroupId": "conn_zulu"},
            {"id": "dv_alpha", "name": "Alpha View", "parentDataGroupId": "conn_alpha"},
        ],
        sort_expression="datasets",
    )

    payload = json.loads(output)
    assert [item["id"] for item in payload["dataViews"]] == ["dv_alpha", "dv_zulu"]
    assert payload["dataViews"][0]["datasets"][0]["connectionMetadata"]["role"] == "zzz"
