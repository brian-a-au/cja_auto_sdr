"""SDR Registry database schema + helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from cja_auto_sdr.output.notion_database import (
    DATABASE_SCHEMA,
    _iso_date_value,
    build_row_properties,
    derive_data_quality_status,
    ensure_database,
    upsert_database_row,
)


def test_schema_has_all_expected_properties() -> None:
    expected = {
        "Name",
        "Data View ID",
        "SDR Page",
        "Last Updated",
        "Tool Version",
        "Captured At",
        "Currency",
        "Timezone",
        "Metrics Count",
        "Dimensions Count",
        "Segments Count",
        "Calculated Metrics Count",
        "Derived Fields Count",
        "Data Quality",
    }
    assert set(DATABASE_SCHEMA.keys()) == expected
    assert DATABASE_SCHEMA["Name"]["title"] == {}
    assert "options" in DATABASE_SCHEMA["Data Quality"]["select"]


def test_derive_data_quality_healthy_when_dq_empty() -> None:
    assert derive_data_quality_status(pd.DataFrame()) == "healthy"
    assert derive_data_quality_status(None) == "healthy"


def test_derive_data_quality_degraded_on_error_severity() -> None:
    df = pd.DataFrame([{"Severity": "ERROR", "Message": "x"}])
    assert derive_data_quality_status(df) == "degraded"


def test_derive_data_quality_partial_on_warn_severity() -> None:
    df = pd.DataFrame([{"Severity": "WARN", "Message": "x"}])
    assert derive_data_quality_status(df) == "partial"


def test_derive_data_quality_degraded_on_high_severity() -> None:
    df = pd.DataFrame([{"Severity": "HIGH", "Message": "x"}])
    assert derive_data_quality_status(df) == "degraded"


def test_derive_data_quality_partial_on_medium_severity() -> None:
    df = pd.DataFrame([{"Severity": "MEDIUM", "Message": "x"}])
    assert derive_data_quality_status(df) == "partial"


def test_build_row_properties_counts_each_section() -> None:
    data_dict = {
        "Metrics": pd.DataFrame([{"a": 1}, {"a": 2}]),
        "Dimensions": pd.DataFrame([{"a": 1}]),
        "Segments": pd.DataFrame(),
        "Calculated Metrics": pd.DataFrame([{"a": 1}, {"a": 2}, {"a": 3}]),
        "Derived Fields": pd.DataFrame(),
    }
    metadata = {
        "Data View Name": "Production DV",
        "Data View ID": "dv_prod",
        "Currency": "USD",
        "Timezone": "America/Los_Angeles",
        "Generated Date & timestamp and timezone": "2026-05-15T10:00:00-07:00",
    }
    page_id = "page-abc"

    props = build_row_properties(data_dict, metadata, page_id, tool_version="3.8.0")

    assert props["Name"]["title"][0]["text"]["content"] == "Production DV"
    assert props["Data View ID"]["rich_text"][0]["text"]["content"] == "dv_prod"
    assert props["SDR Page"]["rich_text"][0]["text"]["content"] == "notion://pages/page-abc"
    assert props["Metrics Count"]["number"] == 2
    assert props["Dimensions Count"]["number"] == 1
    assert props["Segments Count"]["number"] == 0
    assert props["Calculated Metrics Count"]["number"] == 3
    assert props["Tool Version"]["rich_text"][0]["text"]["content"] == "3.8.0"
    assert props["Data Quality"]["select"]["name"] == "healthy"


def test_ensure_database_creates_when_id_is_none() -> None:
    client = MagicMock()
    client.databases.create.return_value = {
        "id": "new-db-id",
        "data_sources": [{"id": "new-ds-id", "name": "CJA SDR Registry"}],
    }

    result = ensure_database(
        client,
        parent_page_id="parent-page",
        database_id=None,
        create_if_missing=True,
    )

    assert result == ("new-db-id", "new-ds-id")
    client.databases.create.assert_called_once()
    create_kwargs = client.databases.create.call_args.kwargs
    assert create_kwargs["parent"] == {"type": "page_id", "page_id": "parent-page"}
    assert "initial_data_source" in create_kwargs
    assert create_kwargs["initial_data_source"] == {"properties": DATABASE_SCHEMA}
    assert "properties" not in create_kwargs


def test_ensure_database_validates_when_id_given() -> None:
    client = MagicMock()
    client.databases.retrieve.return_value = {
        "id": "existing-db",
        "data_sources": [{"id": "ds-1"}],
    }
    client.data_sources.retrieve.return_value = {
        "id": "ds-1",
        "properties": {name: {"id": "x"} for name in DATABASE_SCHEMA},
    }

    result = ensure_database(
        client,
        parent_page_id="parent-page",
        database_id="existing-db",
        create_if_missing=False,
    )

    assert result == ("existing-db", "ds-1")
    client.databases.retrieve.assert_called_once_with(database_id="existing-db")
    client.data_sources.retrieve.assert_called_once_with(data_source_id="ds-1")
    client.databases.create.assert_not_called()


def test_ensure_database_rejects_invalid_existing_schema() -> None:
    client = MagicMock()
    client.databases.retrieve.return_value = {
        "id": "broken-db",
        "data_sources": [{"id": "ds-bad"}],
    }
    client.data_sources.retrieve.return_value = {
        "id": "ds-bad",
        "properties": {"Name": {"id": "x"}},  # missing all others
    }

    with pytest.raises(ValueError, match="missing required properties"):
        ensure_database(
            client,
            parent_page_id="parent-page",
            database_id="broken-db",
            create_if_missing=False,
        )


def test_ensure_database_refuses_to_create_without_flag() -> None:
    client = MagicMock()

    with pytest.raises(ValueError, match="--notion-create-database"):
        ensure_database(
            client,
            parent_page_id="parent-page",
            database_id=None,
            create_if_missing=False,
        )


def test_build_catalog_row_properties_shape() -> None:
    """build_catalog_row_properties leaves unmeasured columns as None/empty/unknown."""
    from cja_auto_sdr.output.notion_database import build_catalog_row_properties

    props = build_catalog_row_properties(
        data_view_name="My DV",
        data_view_id="dv_abc",
        metrics_count=8,
        dimensions_count=4,
        page_id="page-111",
        tool_version="3.8.0",
        captured_at="2026-06-19T00:00:00Z",
    )

    assert props["Name"]["title"][0]["text"]["content"] == "My DV"
    assert props["Data View ID"]["rich_text"][0]["text"]["content"] == "dv_abc"
    assert "page-111" in props["SDR Page"]["rich_text"][0]["text"]["content"]
    assert props["Metrics Count"] == {"number": 8}
    assert props["Dimensions Count"] == {"number": 4}
    assert props["Segments Count"] == {"number": None}
    assert props["Calculated Metrics Count"] == {"number": None}
    assert props["Derived Fields Count"] == {"number": None}
    assert props["Data Quality"] == {"select": {"name": "unknown"}}
    assert props["Currency"]["rich_text"][0]["text"]["content"] == ""
    assert props["Timezone"]["rich_text"][0]["text"]["content"] == ""
    assert props["Tool Version"]["rich_text"][0]["text"]["content"] == "3.8.0"

    # No page_id case
    props_no_page = build_catalog_row_properties(
        data_view_name="My DV",
        data_view_id="dv_abc",
        metrics_count=0,
        dimensions_count=0,
        tool_version="3.8.0",
    )
    assert props_no_page["SDR Page"]["rich_text"][0]["text"]["content"] == ""


# ---------------------------------------------------------------------------
# upsert_database_row — data_source_id parent
# ---------------------------------------------------------------------------


def test_upsert_database_row_creates_with_data_source_parent() -> None:
    client = MagicMock()
    client.pages.create.return_value = {"id": "new-row-id"}

    row_id = upsert_database_row(
        client,
        data_source_id="ds-1",
        existing_row_id=None,
        properties={"Name": {"title": []}},
    )

    assert row_id == "new-row-id"
    client.pages.create.assert_called_once_with(
        parent={"type": "data_source_id", "data_source_id": "ds-1"},
        properties={"Name": {"title": []}},
    )
    client.pages.update.assert_not_called()


def test_upsert_database_row_updates_existing_row() -> None:
    client = MagicMock()
    client.pages.update.return_value = {"id": "existing-row-id"}

    row_id = upsert_database_row(
        client,
        data_source_id="ds-1",
        existing_row_id="existing-row-id",
        properties={"Name": {"title": []}},
    )

    assert row_id == "existing-row-id"
    client.pages.update.assert_called_once_with(
        page_id="existing-row-id",
        properties={"Name": {"title": []}},
    )
    client.pages.create.assert_not_called()


# ---------------------------------------------------------------------------
# _iso_date_value — timestamp normalization
# ---------------------------------------------------------------------------


def test_iso_date_value_parses_space_separated_with_tz() -> None:
    result = _iso_date_value("2026-06-19 14:20:00 PDT")
    assert result == {"start": "2026-06-19T14:20:00"}


def test_iso_date_value_returns_none_for_unparseable() -> None:
    result = _iso_date_value("not-a-date")
    assert result is None


def test_iso_date_value_parses_iso8601() -> None:
    result = _iso_date_value("2026-06-19T14:20:00+00:00")
    assert result == {"start": "2026-06-19T14:20:00+00:00"}


def test_iso_date_value_returns_none_for_empty() -> None:
    assert _iso_date_value(None) is None
    assert _iso_date_value("") is None


def test_iso_date_value_date_only() -> None:
    # fromisoformat("2026-06-19") succeeds → isoformat includes midnight time
    result = _iso_date_value("2026-06-19")
    assert result is not None
    assert result["start"].startswith("2026-06-19")


def test_build_row_properties_captured_at_space_timestamp() -> None:
    """Metadata 'Generated Date & timestamp and timezone' with space-separated tz is normalized."""
    data_dict = {"Metrics": pd.DataFrame(), "Dimensions": pd.DataFrame()}
    metadata = {
        "Data View Name": "Test DV",
        "Data View ID": "dv_test",
        "Generated Date & timestamp and timezone": "2026-06-19 14:20:00 PDT",
    }
    props = build_row_properties(data_dict, metadata, "page-x", tool_version="3.8.0")
    captured = props["Captured At"]["date"]
    assert captured is not None
    assert captured["start"] == "2026-06-19T14:20:00"


def test_build_row_properties_captured_at_unparseable_yields_none() -> None:
    """Unparseable captured_at value → Captured At date is None."""
    data_dict = {"Metrics": pd.DataFrame()}
    metadata = {
        "Data View Name": "Test DV",
        "Data View ID": "dv_test",
        "Generated Date & timestamp and timezone": "not-a-date",
    }
    props = build_row_properties(data_dict, metadata, "page-x", tool_version="3.8.0")
    assert props["Captured At"] == {"date": None}


def test_find_existing_row_id_returns_match() -> None:
    """find_existing_row_id queries the data source by Data View ID and returns the row id."""
    from cja_auto_sdr.output.notion_database import find_existing_row_id

    client = MagicMock()
    client.data_sources.query.return_value = {"results": [{"id": "row-123"}]}
    rid = find_existing_row_id(client, data_source_id="ds-1", data_view_id="dv1")
    assert rid == "row-123"
    kwargs = client.data_sources.query.call_args.kwargs
    assert kwargs["data_source_id"] == "ds-1"
    assert kwargs["filter"]["property"] == "Data View ID"
    assert kwargs["filter"]["rich_text"]["equals"] == "dv1"


def test_find_existing_row_id_returns_none_when_no_match() -> None:
    from cja_auto_sdr.output.notion_database import find_existing_row_id

    client = MagicMock()
    client.data_sources.query.return_value = {"results": []}
    assert find_existing_row_id(client, data_source_id="ds-1", data_view_id="dv1") is None
