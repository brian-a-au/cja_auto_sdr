"""Tests for discovery payload classification contracts."""

import pandas as pd

from cja_auto_sdr.core.discovery_payloads import (
    PayloadKind,
    _assess_expected_lookup_id,
    _coerce_lookup_scalar_text,
    _has_minimum_dataview_lookup_metadata,
    _is_legacy_unknown_lookup_placeholder,
    _is_truthy_marker,
    _lookup_value_has_substance,
    _normalize_dataview_lookup_payload,
    _unknown_lookup_placeholder_reason,
    _unknown_placeholder_diagnostic_key,
    assess_component_payload,
    assess_dataview_lookup_payload,
    coerce_component_rows_or_none,
    count_component_items_or_na,
    extract_component_sequence,
    is_component_error_payload,
    is_dataview_error_payload,
    looks_like_error_payload,
)


def test_assess_component_empty_typed_dataframe_is_empty() -> None:
    frame = pd.DataFrame(columns=["id", "name", "type"])
    assessment = assess_component_payload(frame)
    assert assessment.kind is PayloadKind.EMPTY
    assert assessment.rows == []


def test_assess_component_empty_dataframe_without_columns_is_empty() -> None:
    frame = pd.DataFrame()
    assessment = assess_component_payload(frame)
    assert assessment.kind is PayloadKind.EMPTY
    assert assessment.reason == "empty_dataframe_no_columns"
    assert assessment.rows == []


def test_assess_component_empty_error_dataframe_is_error() -> None:
    frame = pd.DataFrame(columns=["statusCode", "message"])
    assessment = assess_component_payload(frame)
    assert assessment.kind is PayloadKind.ERROR


def test_assess_component_non_empty_dataframe_recurses_to_records() -> None:
    frame = pd.DataFrame([{"id": "metrics/revenue", "name": "Revenue"}])
    assessment = assess_component_payload(frame)
    assert assessment.kind is PayloadKind.DATA
    assert assessment.reason == "mapping_rows"
    assert assessment.rows == [{"id": "metrics/revenue", "name": "Revenue"}]


def test_assess_component_sequence_payload_prefers_embedded_rows() -> None:
    payload = {"statusCode": 200, "message": "ok", "data": []}
    assessment = assess_component_payload(payload)
    assert assessment.kind is PayloadKind.EMPTY
    assert assessment.rows == []


def test_assess_component_explicit_error_wins_over_envelope_rows() -> None:
    payload = {"errorCode": "forbidden", "data": []}
    assessment = assess_component_payload(payload)
    assert assessment.kind is PayloadKind.ERROR


def test_assess_component_regular_rows_are_data() -> None:
    payload = [
        {"id": "metrics/revenue", "name": "Revenue", "type": "currency"},
        {"id": "metrics/pageviews", "name": "Page Views", "type": "decimal"},
    ]
    assessment = assess_component_payload(payload)
    assert assessment.kind is PayloadKind.DATA
    assert len(assessment.rows) == 2


def test_count_component_items_or_na_for_empty_typed_dataframe() -> None:
    frame = pd.DataFrame(columns=["id", "name", "type"])
    assert count_component_items_or_na(frame) == 0


def test_count_component_items_or_na_for_error_payload() -> None:
    payload = {"statusCode": 500, "message": "backend timeout"}
    assert count_component_items_or_na(payload) == "N/A"


def test_dataview_payload_error_shape_detected() -> None:
    assert is_dataview_error_payload({"statusCode": 404, "errorCode": "not_found"}) is True


def test_dataview_payload_with_identity_not_error() -> None:
    payload = {"id": "dv_1", "name": "Test View", "status": "active"}
    assert is_dataview_error_payload(payload) is False


def test_dataview_payload_with_mixed_case_identity_not_error() -> None:
    payload = {"ID": "dv_1", "Name": "Test View", "statusCode": 200, "message": "ok"}
    assert is_dataview_error_payload(payload) is False


def test_dataview_payload_with_na_identity_values_is_treated_as_error() -> None:
    payload = {"statusCode": 404, "message": "missing", "id": pd.NA, "name": pd.NA}
    assert is_dataview_error_payload(payload) is True


def test_dataview_payload_with_na_id_and_present_name_is_not_error() -> None:
    payload = {"statusCode": 200, "message": "ok", "id": pd.NA, "name": "Test View"}
    assert is_dataview_error_payload(payload) is False


def test_dataview_payload_with_identity_and_error_field_is_not_error() -> None:
    payload = {"id": "dv_1", "name": "Test View", "error": "non-fatal detail"}
    assert is_dataview_error_payload(payload) is False


def test_dataview_payload_with_id_and_error_only_is_treated_as_error() -> None:
    payload = {"id": "dv_missing", "error": "not found"}
    assert is_dataview_error_payload(payload) is True


def test_assess_dataview_lookup_payload_accepts_valid_payload() -> None:
    payload = {"id": "dv_1", "name": "Valid View", "owner": {"name": "Owner"}}
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")
    assert assessment.kind is PayloadKind.DATA
    assert assessment.is_valid is True


def test_assess_dataview_lookup_payload_accepts_valid_payload_with_error_field() -> None:
    payload = {"id": "dv_1", "name": "Valid View", "error": "temporary warning"}
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")
    assert assessment.kind is PayloadKind.DATA
    assert assessment.reason == "valid_lookup_payload"
    assert assessment.is_valid is True


def test_assess_dataview_lookup_payload_accepts_owner_only_metadata_with_error_field() -> None:
    payload = {"id": "dv_1", "owner": {"name": "Owner"}, "error": "transient warning"}
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")
    assert assessment.kind is PayloadKind.DATA
    assert assessment.reason == "valid_lookup_payload"
    assert assessment.is_valid is True


def test_assess_dataview_lookup_payload_rejects_empty_owner_container_with_error_field() -> None:
    payload = {"id": "dv_1", "owner": {}, "error": "not found"}
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")
    assert assessment.kind is PayloadKind.ERROR
    assert assessment.reason == "error_shape"


def test_assess_dataview_lookup_payload_rejects_owner_container_with_only_blank_values() -> None:
    payload = {"id": "dv_1", "owner": {"name": "  ", "email": "null"}, "error": "not found"}
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")
    assert assessment.kind is PayloadKind.ERROR
    assert assessment.reason == "error_shape"


def test_assess_dataview_lookup_payload_prefers_non_empty_case_collided_owner_payload() -> None:
    payload = {
        "id": "dv_1",
        "owner": {},
        "Owner": {"NAME": "Owner Name"},
        "error": "transient warning",
    }
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")
    assert assessment.kind is PayloadKind.DATA
    assert assessment.reason == "valid_lookup_payload"
    assert assessment.payload is not None
    assert assessment.payload["owner"]["name"] == "Owner Name"


def test_assess_dataview_lookup_payload_rejects_id_plus_error_only_payload() -> None:
    payload = {"id": "dv_1", "error": "not found"}
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")
    assert assessment.kind is PayloadKind.ERROR
    assert assessment.reason == "error_shape"


def test_assess_dataview_lookup_payload_rejects_id_only_payload_as_insufficient_metadata() -> None:
    payload = {"id": "dv_1"}
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")
    assert assessment.kind is PayloadKind.ERROR
    assert assessment.reason == "insufficient_metadata"


def test_assess_dataview_lookup_payload_rejects_unknown_placeholder_with_error_field() -> None:
    payload = {"id": "dv_1", "name": "Unknown", "error": "not found"}
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")
    assert assessment.kind is PayloadKind.ERROR
    assert assessment.reason == "unknown_placeholder_diagnostic:error"


def test_assess_dataview_lookup_payload_rejects_unknown_placeholder_with_status_and_message() -> None:
    payload = {"id": "dv_1", "name": "Unknown", "statusCode": 404, "message": "not found"}
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")
    assert assessment.kind is PayloadKind.ERROR
    assert assessment.reason == "unknown_placeholder_diagnostic:message"


def test_assess_dataview_lookup_payload_allows_unknown_named_dataview_without_diagnostics() -> None:
    payload = {"id": "dv_1", "name": "Unknown", "owner": {"name": "Owner"}}
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")
    assert assessment.kind is PayloadKind.DATA
    assert assessment.reason == "valid_lookup_payload"
    assert assessment.is_valid is True


def test_assess_dataview_lookup_payload_rejects_explicit_lookup_failed_marker() -> None:
    payload = {
        "id": "dv_1",
        "name": "Unknown",
        "lookup_failed": True,
        "lookup_failure_reason": "exception",
        "error": "network timeout",
    }
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")
    assert assessment.kind is PayloadKind.ERROR
    assert assessment.reason == "failure_flag:lookup_failed"


def test_assess_dataview_lookup_payload_prefers_lookup_failed_when_multiple_failure_flags_present() -> None:
    payload = {
        "id": "dv_1",
        "name": "Unknown",
        "lookup_failed": True,
        "circuit_breaker_open": True,
    }
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")
    assert assessment.kind is PayloadKind.ERROR
    assert assessment.reason == "failure_flag:lookup_failed"


def test_assess_dataview_lookup_payload_uses_next_failure_flag_when_higher_precedence_is_falsey() -> None:
    payload = {
        "id": "dv_1",
        "name": "Unknown",
        "lookup_failed": "false",
        "circuit_breaker_open": "true",
    }
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")
    assert assessment.kind is PayloadKind.ERROR
    assert assessment.reason == "failure_flag:circuit_breaker_open"


def test_assess_dataview_lookup_payload_rejects_circuit_breaker_marker() -> None:
    payload = {"id": "dv_1", "name": "Unknown", "circuit_breaker_open": "true"}
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")
    assert assessment.kind is PayloadKind.ERROR
    assert assessment.reason == "failure_flag:circuit_breaker_open"


def test_assess_dataview_lookup_payload_rejects_lookup_failure_reason_detail() -> None:
    payload = {"id": "dv_1", "name": "Unknown", "lookup_failure_reason": "exception"}
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")
    assert assessment.kind is PayloadKind.ERROR
    assert assessment.reason == "failure_detail:lookup_failure_reason"


def test_assess_dataview_lookup_payload_rejects_legacy_unknown_placeholder() -> None:
    payload = {"id": "dv_1", "name": "Unknown"}
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")
    assert assessment.kind is PayloadKind.ERROR
    assert assessment.reason == "legacy_unknown_placeholder"


def test_assess_dataview_lookup_payload_rejects_id_mismatch() -> None:
    payload = {"id": "dv_other", "name": "Valid View"}
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")
    assert assessment.kind is PayloadKind.ERROR
    assert assessment.reason == "id_mismatch"


def test_assess_dataview_lookup_payload_rejects_missing_id_when_expected() -> None:
    payload = {"name": "Some Name", "error": "not found"}
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")
    assert assessment.kind is PayloadKind.ERROR
    assert assessment.reason == "missing_expected_id"


def test_assess_dataview_lookup_payload_rejects_blank_id_when_expected() -> None:
    payload = {"id": "  ", "name": "Some Name"}
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")
    assert assessment.kind is PayloadKind.ERROR
    assert assessment.reason == "missing_expected_id"


def test_assess_dataview_lookup_payload_accepts_mixed_case_identity_keys() -> None:
    payload = {"ID": "dv_1", "Name": "Valid View", "owner": {"name": "Owner"}}
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")
    assert assessment.kind is PayloadKind.DATA
    assert assessment.reason == "valid_lookup_payload"
    assert assessment.is_valid is True
    assert assessment.payload is not None
    assert assessment.payload["id"] == "dv_1"
    assert assessment.payload["name"] == "Valid View"


def test_assess_dataview_lookup_payload_canonicalizes_mixed_case_metadata_fields() -> None:
    payload = {
        "ID": "dv_1",
        "Name": "Valid View",
        "Owner": {"NAME": "Owner Name", "IMSUSERID": "owner@example.com"},
        "Description": "A test view",
        "ParentDataGroupID": "conn_1",
        "CreatedDATE": "2025-01-01",
        "MODIFIEDAT": "2025-06-01",
    }
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")

    assert assessment.kind is PayloadKind.DATA
    assert assessment.payload is not None
    assert assessment.payload["id"] == "dv_1"
    assert assessment.payload["name"] == "Valid View"
    assert assessment.payload["description"] == "A test view"
    assert assessment.payload["parentDataGroupId"] == "conn_1"
    assert assessment.payload["createdDate"] == "2025-01-01"
    assert assessment.payload["modifiedAt"] == "2025-06-01"
    assert assessment.payload["owner"] == {
        "NAME": "Owner Name",
        "IMSUSERID": "owner@example.com",
        "name": "Owner Name",
        "imsUserId": "owner@example.com",
    }


def test_assess_dataview_lookup_payload_handles_non_stringifiable_name_value() -> None:
    class _ExplodingName:
        def __str__(self) -> str:  # pragma: no cover - explicit failure path
            raise RuntimeError("boom")

    payload = {"id": "dv_1", "name": _ExplodingName()}
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")
    assert assessment.kind is PayloadKind.DATA
    assert assessment.is_valid is True


def test_assess_dataview_lookup_payload_handles_recursive_owner_container() -> None:
    owner_payload: dict[str, object] = {}
    owner_payload["self"] = owner_payload
    payload = {"id": "dv_1", "owner": owner_payload, "error": "not found"}
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")
    assert assessment.kind is PayloadKind.ERROR
    assert assessment.reason == "error_shape"


def test_assess_dataview_lookup_payload_rejects_invalid_id_type() -> None:
    class _ExplodingId:
        def __str__(self) -> str:  # pragma: no cover - explicit failure path
            raise RuntimeError("boom")

    payload = {"id": _ExplodingId(), "name": "Valid View"}
    assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")
    assert assessment.kind is PayloadKind.ERROR
    assert assessment.reason == "invalid_id_type"


def test_normalize_dataview_lookup_payload_uses_first_dataframe_record() -> None:
    frame = pd.DataFrame([{"id": "dv_1", "name": "Valid View", "owner": "Owner"}])
    payload, raw_type, reason = _normalize_dataview_lookup_payload(frame)
    assert payload == {"id": "dv_1", "name": "Valid View", "owner": "Owner"}
    assert raw_type == "DataFrame"
    assert reason == "dataframe_first_record"


def test_normalize_dataview_lookup_payload_rejects_non_mapping_dataframe_rows() -> None:
    class _BadRecordFrame(pd.DataFrame):
        @property
        def _constructor(self):
            return _BadRecordFrame

        def to_dict(self, orient="dict", *args, **kwargs):
            if orient == "records":
                return [42]
            return super().to_dict(orient=orient, *args, **kwargs)

    frame = _BadRecordFrame({"id": ["dv_1"]})
    payload, raw_type, reason = _normalize_dataview_lookup_payload(frame)
    assert payload is None
    assert raw_type == "_BadRecordFrame"
    assert reason == "non_mapping_dataframe_row"


def test_truthy_marker_fallback_logs_debug_and_treats_value_as_truthy(caplog) -> None:
    class _ExplodingBool:
        def __bool__(self):  # pragma: no cover - explicit failure path
            raise TypeError("cannot coerce to bool")

    payload = {"id": "dv_1", "name": "Unknown", "lookup_failed": _ExplodingBool()}
    with caplog.at_level("DEBUG", logger="cja_auto_sdr.core.discovery_payloads"):
        assessment = assess_dataview_lookup_payload(payload, expected_data_view_id="dv_1")

    assert assessment.kind is PayloadKind.ERROR
    assert assessment.reason == "failure_flag:lookup_failed"
    assert any("Treating lookup marker value as truthy" in record.message for record in caplog.records)


# ---------------------------------------------------------------------------
# looks_like_error_payload — empty dict (line 56)
# ---------------------------------------------------------------------------


def test_empty_dict_looks_like_error() -> None:
    """Empty keys → _schema_indicates_error returns True."""
    assert looks_like_error_payload({}) is True


# ---------------------------------------------------------------------------
# extract_component_sequence branches (lines 83, 85, 88-92)
# ---------------------------------------------------------------------------


def test_extract_component_sequence_none_value_returns_empty() -> None:
    """Component key present but value is None → empty list."""
    assert extract_component_sequence({"data": None}) == []


def test_extract_component_sequence_dataframe_value() -> None:
    """Component key holds a DataFrame → converted to records."""
    df = pd.DataFrame({"id": ["m1", "m2"], "name": ["Revenue", "Views"]})
    result = extract_component_sequence({"data": df})
    assert result == [{"id": "m1", "name": "Revenue"}, {"id": "m2", "name": "Views"}]


def test_extract_component_sequence_nested_mapping() -> None:
    """Component key holds a nested dict with its own component key → recurse."""
    payload = {"results": {"data": [{"id": "1"}]}}
    assert extract_component_sequence(payload) == [{"id": "1"}]


def test_extract_component_sequence_nested_mapping_no_match() -> None:
    """Nested mapping with no component keys → empty list."""
    payload = {"items": {"randomKey": "value"}}
    assert extract_component_sequence(payload) == []


# ---------------------------------------------------------------------------
# assess_component_payload branches (lines 110, 129, 139, 142)
# ---------------------------------------------------------------------------


def test_assess_none_payload_is_empty() -> None:
    """None input → EMPTY with reason 'none_payload'."""
    assessment = assess_component_payload(None)
    assert assessment.kind is PayloadKind.EMPTY
    assert assessment.reason == "none_payload"


def test_assess_single_object_row() -> None:
    """Mapping without error/sequence keys and with identity → DATA single row."""
    payload = {"id": "obj_1", "name": "Object", "description": "Details"}
    assessment = assess_component_payload(payload)
    assert assessment.kind is PayloadKind.DATA
    assert assessment.reason == "single_object_row"
    assert assessment.rows == [payload]


def test_assess_non_mapping_sequence_is_invalid() -> None:
    """List of non-Mapping items → INVALID."""
    assessment = assess_component_payload([1, 2, 3])
    assert assessment.kind is PayloadKind.INVALID
    assert assessment.reason == "non_mapping_sequence_rows"


def test_assess_unsupported_payload_type_is_invalid() -> None:
    assessment = assess_component_payload(42)
    assert assessment.kind is PayloadKind.INVALID
    assert assessment.reason == "unsupported_payload_type"


def test_assess_error_row_in_sequence() -> None:
    """List containing an error-shaped dict → ERROR 'error_row_detected'."""
    payload = [
        {"id": "obj_1", "name": "Valid"},
        {"statusCode": 500, "message": "Server error"},
    ]
    assessment = assess_component_payload(payload)
    assert assessment.kind is PayloadKind.ERROR
    assert assessment.reason == "error_row_detected"


# ---------------------------------------------------------------------------
# coerce_component_rows_or_none (lines 151-154)
# ---------------------------------------------------------------------------


def test_coerce_data_payload_returns_rows() -> None:
    result = coerce_component_rows_or_none([{"id": "1"}])
    assert result == [{"id": "1"}]


def test_coerce_empty_payload_returns_empty_list() -> None:
    result = coerce_component_rows_or_none([])
    assert result == []


def test_coerce_error_payload_returns_none() -> None:
    result = coerce_component_rows_or_none({"statusCode": 500, "message": "fail"})
    assert result is None


def test_coerce_invalid_payload_returns_none() -> None:
    result = coerce_component_rows_or_none([1, 2, 3])
    assert result is None


# ---------------------------------------------------------------------------
# is_component_error_payload (line 159)
# ---------------------------------------------------------------------------


def test_is_component_error_payload_true() -> None:
    assert is_component_error_payload({"statusCode": 500, "message": "Error"}) is True


def test_is_component_error_payload_false() -> None:
    assert is_component_error_payload([{"id": "1", "name": "OK"}]) is False


# ---------------------------------------------------------------------------
# Coverage gap tests (moved from test_remaining_gap_coverage_pass2.py)
# ---------------------------------------------------------------------------


def test_discovery_lookup_helpers_cover_remaining_edge_paths() -> None:
    recursive_items: list[object] = []
    recursive_items.append(recursive_items)

    assert _lookup_value_has_substance(()) is False
    assert _lookup_value_has_substance(recursive_items) is False
    assert _has_minimum_dataview_lookup_metadata({"id": "dv1", "future_metadata": {"owner": "alice"}}) is True
    assert _is_truthy_marker(2) is True
    assert _is_truthy_marker(0) is False

    class _EmptyRecordsFrame(pd.DataFrame):
        @property
        def _constructor(self):
            return _EmptyRecordsFrame

        def to_dict(self, orient="dict", *args, **kwargs):
            if orient == "records":
                return []
            return super().to_dict(orient=orient, *args, **kwargs)

    payload, raw_type, reason = _normalize_dataview_lookup_payload(_EmptyRecordsFrame({"id": ["dv1"]}))
    assert payload is None
    assert raw_type == "_EmptyRecordsFrame"
    assert reason == "empty_dataframe_records"

    class _BadBytes(bytes):
        def decode(self, *args, **kwargs):
            raise TypeError("bad decode")

    assert _coerce_lookup_scalar_text(_BadBytes(b"dv1")) is None
    assert _coerce_lookup_scalar_text(7) == "7"
    assert _assess_expected_lookup_id({"id": "   "}, expected_data_view_id="dv1") == (None, "missing_expected_id")
    assert (
        _is_legacy_unknown_lookup_placeholder(
            expected_data_view_id="dv1",
            normalized_items={"id": "dv_other", "name": "Unknown"},
        )
        is False
    )
    assert _unknown_placeholder_diagnostic_key({"lookup_failed": True}) == "lookup_failed"
    assert _unknown_placeholder_diagnostic_key({"lookup_failure_reason": "timeout"}) == "lookup_failure_reason"
    assert _unknown_placeholder_diagnostic_key({"lookup_debug": "detail"}) == "lookup_debug"
    assert _unknown_lookup_placeholder_reason("dv1", {"id": "dv_other", "name": "Unknown"}) is None
