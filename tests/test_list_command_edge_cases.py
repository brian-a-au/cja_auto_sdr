"""Edge-case tests for cja_auto_sdr.cli.commands.list targeting uncovered branches.

Lines targeted: 168, 281, 430-431, 450, 497-498, 537, 623, 626, 632,
                763, 768, 827, 830, 868, 910, 913, 934, 949, 1014, 1036,
                1040-1041, 1043
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pandas as pd
import pytest

from cja_auto_sdr.cli.commands.list import (
    DiscoveryNotFoundError,
    _approved_display,
    _build_metric_display_row,
    _fetch_component_payload,
    _fetch_connections,
    _fetch_datasets,
    _fetch_dataviews,
    _normalize_component_records_or_raise,
    _resolve_dataview_name,
    _tags_display,
)

# ---------------------------------------------------------------------------
# _approved_display edge cases (lines 623, 626, 632)
# ---------------------------------------------------------------------------


class TestApprovedDisplay:
    """Tests for _approved_display covering all branches."""

    def test_none_returns_na(self) -> None:
        """L623: None value returns 'N/A'."""
        assert _approved_display(None) == "N/A"

    def test_true_returns_yes(self) -> None:
        assert _approved_display(True) == "Yes"

    def test_false_returns_no(self) -> None:
        """L626: False bool returns 'No'."""
        assert _approved_display(False) == "No"

    def test_non_bool_string_returns_str(self) -> None:
        """L626: non-bool value returns str()."""
        assert _approved_display("maybe") == "maybe"

    def test_non_bool_int_returns_str(self) -> None:
        """L626: integer returns str representation."""
        assert _approved_display(42) == "42"


# ---------------------------------------------------------------------------
# _tags_display edge cases (line 632)
# ---------------------------------------------------------------------------


class TestTagsDisplay:
    """Tests for _tags_display covering the non-list branch."""

    def test_non_list_returns_empty_string(self) -> None:
        """L632: non-list input returns empty string."""
        assert _tags_display("not-a-list") == ""
        assert _tags_display(None) == ""
        assert _tags_display(42) == ""

    def test_empty_list_returns_empty_string(self) -> None:
        assert _tags_display([]) == ""

    def test_list_of_strings_returns_joined(self) -> None:
        assert _tags_display(["a", "b", "c"]) == "a, b, c"

    def test_filters_out_non_strings(self) -> None:
        assert _tags_display(["a", None, "b", 42]) == "a, b"


# ---------------------------------------------------------------------------
# _normalize_component_records_or_raise (line 281: INVALID kind)
# ---------------------------------------------------------------------------


class TestNormalizeComponentRecordsOrRaise:
    """Tests for _normalize_component_records_or_raise."""

    def test_invalid_payload_raises_discovery_not_found(self) -> None:
        """L281: INVALID payload kind raises DiscoveryNotFoundError."""
        # A non-list, non-dict, non-DataFrame raw payload → INVALID kind
        invalid_payload = 42  # integer is unsupported_payload_type → INVALID
        with pytest.raises(DiscoveryNotFoundError, match="Unexpected metrics payload"):
            _normalize_component_records_or_raise(
                invalid_payload,
                component_label="metrics",
                data_view_id="dv_test",
            )

    def test_error_payload_raises_discovery_not_found(self) -> None:
        """ERROR kind also raises DiscoveryNotFoundError."""
        error_payload = {"statusCode": 403, "message": "Forbidden"}
        with pytest.raises(DiscoveryNotFoundError, match="Failed to retrieve dimensions"):
            _normalize_component_records_or_raise(
                error_payload,
                component_label="dimensions",
                data_view_id="dv_test",
            )

    def test_valid_list_payload_returns_rows(self) -> None:
        rows = [{"id": "m1", "name": "Metric 1"}]
        result = _normalize_component_records_or_raise(
            rows,
            component_label="metrics",
            data_view_id="dv_test",
        )
        assert result == rows


# ---------------------------------------------------------------------------
# _resolve_dataview_name fallback (lines 430-431)
# ---------------------------------------------------------------------------


class TestResolveDataviewName:
    """Tests for _resolve_dataview_name covering fallback branches."""

    def _make_cja_with_dv(self, dv_id: str, dv_payload: dict) -> MagicMock:
        cja = MagicMock()
        cja.getDataView.return_value = dv_payload
        return cja

    def test_returns_name_from_payload(self) -> None:
        cja = self._make_cja_with_dv("dv_test", {"id": "dv_test", "name": "My Data View"})
        result = _resolve_dataview_name(cja, "dv_test")
        assert result == "My Data View"

    def test_returns_preferred_name_when_payload_name_missing(self) -> None:
        """L430: fallback to preferred_name when payload name normalizes to empty.

        'null' passes lookup validation but _normalize_optional_text normalizes it to ''.
        """
        # 'null' passes lookup validation but normalizes to '' → triggers fallback
        cja = self._make_cja_with_dv(
            "dv_test",
            {"id": "dv_test", "name": "null", "ownerFullName": "owner", "parentDataGroupId": "conn1"},
        )
        result = _resolve_dataview_name(cja, "dv_test", preferred_name="Preferred Name")
        assert result == "Preferred Name"

    def test_returns_unknown_when_both_names_missing(self) -> None:
        """L431: returns 'Unknown' when payload name normalizes to empty and no preferred_name."""
        cja = self._make_cja_with_dv(
            "dv_test",
            {"id": "dv_test", "name": "null", "ownerFullName": "owner", "parentDataGroupId": "conn1"},
        )
        result = _resolve_dataview_name(cja, "dv_test", preferred_name=None)
        assert result == "Unknown"

    def test_returns_unknown_when_preferred_name_also_blank(self) -> None:
        """L431: blank preferred_name also falls through to 'Unknown'."""
        cja = self._make_cja_with_dv(
            "dv_test",
            {"id": "dv_test", "name": "null", "ownerFullName": "owner", "parentDataGroupId": "conn1"},
        )
        result = _resolve_dataview_name(cja, "dv_test", preferred_name="")
        assert result == "Unknown"


# ---------------------------------------------------------------------------
# _fetch_component_payload: non-callable method (line 450)
# ---------------------------------------------------------------------------


class TestFetchComponentPayload:
    """Tests for _fetch_component_payload."""

    def test_missing_method_raises_discovery_not_found(self) -> None:
        """L450: getattr returns None (non-callable) → DiscoveryNotFoundError."""
        from cja_auto_sdr.cli.commands.list import _METRICS_COMPONENT_FETCH_SPEC

        cja = MagicMock()
        # Make the expected method not callable
        method_name = _METRICS_COMPONENT_FETCH_SPEC.method_name
        setattr(cja, method_name, None)

        with pytest.raises(DiscoveryNotFoundError, match=f"missing expected method '{method_name}'"):
            _fetch_component_payload(cja, "dv_test", _METRICS_COMPONENT_FETCH_SPEC)

    def test_callable_method_is_invoked(self) -> None:
        from cja_auto_sdr.cli.commands.list import _METRICS_COMPONENT_FETCH_SPEC

        cja = MagicMock()
        cja.getMetrics.return_value = [{"id": "m1"}]
        result = _fetch_component_payload(cja, "dv_test", _METRICS_COMPONENT_FETCH_SPEC)
        assert result == [{"id": "m1"}]


# ---------------------------------------------------------------------------
# _fetch_dataviews: empty list + CSV format (line 168)
# ---------------------------------------------------------------------------


class TestFetchDataviewsEmpty:
    """Tests for _fetch_dataviews inner function with empty result."""

    def test_empty_list_csv_format_returns_header_only(self) -> None:
        """L168: empty data views + CSV + machine_readable → header only."""
        cja = MagicMock()
        cja.getDataViews.return_value = []

        fetcher = _fetch_dataviews(output_format="csv")
        result = fetcher(cja, is_machine_readable=True)
        assert result == "id,name,owner\n"

    def test_empty_none_csv_format_returns_header_only(self) -> None:
        """L168: None data views + CSV + machine_readable → header only."""
        cja = MagicMock()
        cja.getDataViews.return_value = None

        fetcher = _fetch_dataviews(output_format="csv")
        result = fetcher(cja, is_machine_readable=True)
        assert result == "id,name,owner\n"

    def test_empty_json_format_returns_empty_json(self) -> None:
        """JSON format returns empty JSON response (not the CSV branch)."""
        import json

        cja = MagicMock()
        cja.getDataViews.return_value = []

        fetcher = _fetch_dataviews(output_format="json")
        result = fetcher(cja, is_machine_readable=True)
        parsed = json.loads(result)
        assert parsed["count"] == 0
        assert parsed["dataViews"] == []

    def test_empty_non_machine_readable_returns_human_message(self) -> None:
        cja = MagicMock()
        cja.getDataViews.return_value = []

        fetcher = _fetch_dataviews(output_format="table")
        result = fetcher(cja, is_machine_readable=False)
        assert "No data views" in result


# ---------------------------------------------------------------------------
# _build_component_list_fetcher: empty components (lines 497-498, 537)
# ---------------------------------------------------------------------------


class TestBuildComponentListFetcherEmpty:
    """Tests for component list fetcher when no components found."""

    def _make_cja(self, dv_payload: dict, metrics_payload: list) -> MagicMock:
        cja = MagicMock()
        cja.getDataView.return_value = dv_payload
        cja.getMetrics.return_value = metrics_payload
        return cja

    def test_empty_metrics_csv_returns_header_only(self) -> None:
        """L497-498: empty components + CSV + machine_readable → header-only."""
        from cja_auto_sdr.cli.commands.list import _fetch_metrics_list

        cja = self._make_cja(
            {"id": "dv_test", "name": "Test DV"},
            [],  # empty metrics
        )
        fetcher = _fetch_metrics_list("dv_test", output_format="csv")
        result = fetcher(cja, is_machine_readable=True)
        assert result == "id,name,type,description\n"

    def test_empty_metrics_json_returns_empty_json(self) -> None:
        """Empty components + JSON + machine_readable → empty JSON."""
        import json

        from cja_auto_sdr.cli.commands.list import _fetch_metrics_list

        cja = self._make_cja(
            {"id": "dv_test", "name": "Test DV"},
            [],
        )
        fetcher = _fetch_metrics_list("dv_test", output_format="json")
        result = fetcher(cja, is_machine_readable=True)
        parsed = json.loads(result)
        assert parsed["count"] == 0
        assert parsed["metrics"] == []

    def test_empty_metrics_table_non_machine_readable(self) -> None:
        """Empty components + non-machine_readable → human message."""
        from cja_auto_sdr.cli.commands.list import _fetch_metrics_list

        cja = self._make_cja(
            {"id": "dv_test", "name": "Test DV"},
            [],
        )
        fetcher = _fetch_metrics_list("dv_test", output_format="table")
        result = fetcher(cja, is_machine_readable=False)
        assert "No metrics found" in result


class TestBuildMetricDisplayRow:
    """Test _build_metric_display_row (line 537)."""

    def test_builds_display_row_from_item(self) -> None:
        """L537: function returns a dict with normalized fields."""
        item = {"id": "metrics/revenue", "name": "Revenue", "type": "currency", "description": "Total revenue"}
        result = _build_metric_display_row(item)
        assert result["id"] == "metrics/revenue"
        assert result["name"] == "Revenue"
        assert "owner" in result
        assert "precision" in result

    def test_builds_display_row_with_missing_fields(self) -> None:
        """Defaults applied when fields are absent."""
        result = _build_metric_display_row({})
        assert result["id"] == "N/A"
        assert result["name"] == "N/A"


# ---------------------------------------------------------------------------
# _fetch_connections: DataFrame path and non-dict items (lines 763, 768)
# ---------------------------------------------------------------------------


class TestFetchConnectionsDataFramePath:
    """Tests for _fetch_connections covering DataFrame conversion and non-dict dv items."""

    def test_empty_connections_with_dataframe_dvs(self) -> None:
        """L763: when connections empty, getDataViews returns DataFrame → converted to records."""
        cja = MagicMock()
        cja.getConnections.return_value = []  # empty → triggers fallback path
        # Return a DataFrame instead of a list
        cja.getDataViews.return_value = pd.DataFrame([{"id": "dv1", "name": "DV1", "parentDataGroupId": "conn_abc"}])

        fetcher = _fetch_connections(output_format="table")
        result = fetcher(cja, is_machine_readable=False)
        # Should derive connection from data views
        assert "conn_abc" in result

    def test_empty_connections_with_non_dict_dv_items(self) -> None:
        """L768: non-dict items in available_dvs are skipped."""
        cja = MagicMock()
        cja.getConnections.return_value = []
        # Mix of non-dict items and a valid dict
        cja.getDataViews.return_value = [
            "not-a-dict",  # should be skipped (L768)
            {"id": "dv1", "parentDataGroupId": "conn_xyz"},
        ]

        fetcher = _fetch_connections(output_format="table")
        result = fetcher(cja, is_machine_readable=False)
        assert "conn_xyz" in result

    def test_empty_connections_no_dvs_machine_readable_csv(self) -> None:
        """L821: machine_readable + CSV + no connections → header only."""
        cja = MagicMock()
        cja.getConnections.return_value = []
        cja.getDataViews.return_value = []

        fetcher = _fetch_connections(output_format="csv")
        result = fetcher(cja, is_machine_readable=True)
        assert result == "connection_id,connection_name,owner,dataset_id,dataset_name\n"


# ---------------------------------------------------------------------------
# _fetch_connections: non-dict conn and non-list datasets (lines 827, 830)
# ---------------------------------------------------------------------------


class TestFetchConnectionsNonDictConn:
    """Tests for connection loop handling non-dict/invalid data."""

    def test_non_dict_conn_item_is_skipped(self) -> None:
        """L827: non-dict connection in list is skipped."""
        cja = MagicMock()
        # _extract_connections_list returns a list, so pass a list directly
        cja.getConnections.return_value = [
            "not-a-dict",  # should be skipped
            {"id": "conn1", "name": "Connection 1", "dataSets": [{"id": "ds1", "name": "DS1"}]},
        ]

        fetcher = _fetch_connections(output_format="table")
        result = fetcher(cja, is_machine_readable=False)
        assert "Connection 1" in result
        assert "not-a-dict" not in result

    def test_non_list_datasets_becomes_empty(self) -> None:
        """L830: non-list dataSets value → treated as empty list."""
        cja = MagicMock()
        cja.getConnections.return_value = [
            {"id": "conn1", "name": "Connection 1", "dataSets": "invalid-not-a-list"},
        ]

        fetcher = _fetch_connections(output_format="table")
        result = fetcher(cja, is_machine_readable=False)
        assert "Connection 1" in result
        # No datasets listed
        assert "Datasets: (none)" in result

    def test_csv_connection_without_datasets_produces_empty_row(self) -> None:
        """L868: CSV output for connection with no datasets includes empty row."""
        cja = MagicMock()
        cja.getConnections.return_value = [
            {"id": "conn1", "name": "Connection 1", "dataSets": []},
        ]

        fetcher = _fetch_connections(output_format="csv")
        result = fetcher(cja, is_machine_readable=True)
        assert "conn1" in result
        assert "Connection 1" in result


# ---------------------------------------------------------------------------
# _fetch_datasets: DataFrame conversion and non-dict items (lines 910, 913, 934)
# ---------------------------------------------------------------------------


class TestFetchDatasetsEdgeCases:
    """Tests for _fetch_datasets covering DataFrame conversion and skip branches."""

    def test_dataframe_connections_converted_to_records(self) -> None:
        """L910: DataFrame from getConnections passed → iterated via _extract_connections_list."""
        cja = MagicMock()
        # getConnections returns a raw dict → _extract_connections_list extracts 'content'
        cja.getConnections.return_value = {
            "content": [{"id": "conn1", "name": "Connection 1", "dataSets": [{"id": "ds1", "name": "DS1"}]}]
        }
        cja.getDataViews.return_value = [{"id": "dv1", "name": "DV1", "parentDataGroupId": "conn1"}]

        fetcher = _fetch_datasets(output_format="table")
        result = fetcher(cja, is_machine_readable=False)
        assert "DV1" in result

    def test_non_dict_conn_in_datasets_skipped(self) -> None:
        """L913: non-dict conn items skipped in conn_map building."""
        cja = MagicMock()
        # Mix of valid and invalid conn items
        cja.getConnections.return_value = [
            "not-a-dict",  # skipped at L913
            {"id": "conn1", "name": "Connection 1", "dataSets": []},
        ]
        cja.getDataViews.return_value = [{"id": "dv1", "name": "DV1", "parentDataGroupId": "conn1"}]

        fetcher = _fetch_datasets(output_format="table")
        result = fetcher(cja, is_machine_readable=False)
        assert "DV1" in result

    def test_non_list_datasets_in_conn_map_building(self) -> None:
        """L913: non-list dataSets in conn_map building → treated as empty list."""
        cja = MagicMock()
        cja.getConnections.return_value = [
            {"id": "conn1", "name": "Connection 1", "dataSets": "invalid-string"},
        ]
        cja.getDataViews.return_value = [{"id": "dv1", "name": "DV1", "parentDataGroupId": "conn1"}]

        fetcher = _fetch_datasets(output_format="table")
        result = fetcher(cja, is_machine_readable=False)
        assert "DV1" in result
        # Dataset should be empty since dataSets was non-list
        assert "Datasets: (none)" in result

    def test_available_dvs_dataframe_converted(self) -> None:
        """L920-921: getDataViews returns DataFrame → converted to records."""
        cja = MagicMock()
        cja.getConnections.return_value = []
        cja.getDataViews.return_value = pd.DataFrame([{"id": "dv1", "name": "DV1", "parentDataGroupId": "conn1"}])

        fetcher = _fetch_datasets(output_format="table")
        result = fetcher(cja, is_machine_readable=False)
        # Should process the data view
        assert "DV1" in result

    def test_non_dict_dv_items_skipped(self) -> None:
        """L934: non-dict dv items are skipped in display_data building."""
        cja = MagicMock()
        cja.getConnections.return_value = []
        cja.getDataViews.return_value = [
            "not-a-dict",  # skipped at L934
            None,  # also not a dict
            {"id": "dv1", "name": "DV1", "parentDataGroupId": "conn1"},
        ]

        fetcher = _fetch_datasets(output_format="table")
        result = fetcher(cja, is_machine_readable=False)
        assert "DV1" in result


# ---------------------------------------------------------------------------
# _fetch_datasets: dataset table/CSV output branches (lines 949, 1014, 1036, 1040-1043)
# ---------------------------------------------------------------------------


class TestFetchDatasetsOutputBranches:
    """Tests for _fetch_datasets output formatting branches."""

    def test_csv_dv_without_datasets_produces_empty_row(self) -> None:
        """L1014: CSV output for DV with no datasets → row with empty dataset fields."""
        cja = MagicMock()
        cja.getConnections.return_value = [
            {"id": "conn1", "name": "Connection 1", "dataSets": []},
        ]
        cja.getDataViews.return_value = [{"id": "dv1", "name": "DV1", "parentDataGroupId": "conn1"}]

        fetcher = _fetch_datasets(output_format="csv")
        result = fetcher(cja, is_machine_readable=True)
        # CSV should contain the DV info but empty dataset fields
        assert "dv1" in result
        assert "DV1" in result

    def test_table_connection_with_name_shows_name(self) -> None:
        """L1036: connection with name shows 'Connection: name (id)' format."""
        cja = MagicMock()
        cja.getConnections.return_value = [
            {"id": "conn1", "name": "My Connection", "dataSets": [{"id": "ds1", "name": "DS1"}]},
        ]
        cja.getDataViews.return_value = [{"id": "dv1", "name": "DV1", "parentDataGroupId": "conn1"}]

        fetcher = _fetch_datasets(output_format="table")
        result = fetcher(cja, is_machine_readable=False)
        assert "My Connection" in result
        assert "conn1" in result

    def test_table_connection_without_name_shows_id_only(self) -> None:
        """L1038: connection without name shows just 'Connection: id'."""
        cja = MagicMock()
        cja.getConnections.return_value = []
        cja.getDataViews.return_value = [{"id": "dv1", "name": "DV1", "parentDataGroupId": "conn_no_name"}]

        fetcher = _fetch_datasets(output_format="table")
        result = fetcher(cja, is_machine_readable=False)
        assert "conn_no_name" in result

    def test_table_dv_with_datasets_lists_them(self) -> None:
        """L1040-1041: DV with datasets shows 'Datasets (N):' and dataset IDs."""
        cja = MagicMock()
        cja.getConnections.return_value = [
            {
                "id": "conn1",
                "name": "Connection 1",
                "dataSets": [{"id": "ds1", "name": "Dataset 1"}, {"id": "ds2", "name": "Dataset 2"}],
            },
        ]
        cja.getDataViews.return_value = [{"id": "dv1", "name": "DV1", "parentDataGroupId": "conn1"}]

        fetcher = _fetch_datasets(output_format="table")
        result = fetcher(cja, is_machine_readable=False)
        assert "Datasets (2)" in result
        assert "ds1" in result
        assert "ds2" in result

    def test_table_dv_no_datasets_no_conn_details_omits_none_label(self) -> None:
        """L1043: DV without datasets and no_conn_details → no 'Datasets: (none)' shown."""
        cja = MagicMock()
        # Empty connections → no_conn_details = True for a DV with a parentDataGroupId
        cja.getConnections.return_value = []
        cja.getDataViews.return_value = [{"id": "dv1", "name": "DV1", "parentDataGroupId": "conn_unknown"}]

        fetcher = _fetch_datasets(output_format="table")
        result = fetcher(cja, is_machine_readable=False)
        # no_conn_details is True here, so "Datasets: (none)" should NOT appear
        assert "Datasets: (none)" not in result

    def test_table_dv_no_datasets_with_conn_details_shows_none_label(self) -> None:
        """L1043 (else branch): DV without datasets and conn_details available → 'Datasets: (none)'."""
        cja = MagicMock()
        # conn_map is populated but DV's connection has no datasets
        cja.getConnections.return_value = [
            {"id": "conn1", "name": "Connection 1", "dataSets": []},
        ]
        cja.getDataViews.return_value = [{"id": "dv1", "name": "DV1", "parentDataGroupId": "conn1"}]

        fetcher = _fetch_datasets(output_format="table")
        result = fetcher(cja, is_machine_readable=False)
        assert "Datasets: (none)" in result

    def test_csv_dv_with_datasets_produces_flat_rows(self) -> None:
        """L949 area: CSV output for DV with datasets expands into flat rows."""
        cja = MagicMock()
        cja.getConnections.return_value = [
            {
                "id": "conn1",
                "name": "Connection 1",
                "dataSets": [{"id": "ds1", "name": "Dataset 1"}],
            }
        ]
        cja.getDataViews.return_value = [{"id": "dv1", "name": "DV1", "parentDataGroupId": "conn1"}]

        fetcher = _fetch_datasets(output_format="csv")
        result = fetcher(cja, is_machine_readable=True)
        assert "ds1" in result
        assert "Dataset 1" in result
        assert "dv1" in result
