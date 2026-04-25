"""Discovery payload classification for data-view inspection commands."""

from __future__ import annotations

import logging
from collections.abc import Mapping
from dataclasses import dataclass
from enum import Enum
from typing import Any

import pandas as pd

from cja_auto_sdr.core.discovery_normalization import is_missing_value

EXPLICIT_ERROR_KEYS = frozenset({"error", "errorcode", "errordescription", "error_description"})
STATUS_KEYS = frozenset({"statuscode", "status_code", "status"})
ERROR_TEXT_KEYS = frozenset({"message", "detail", "title"})
COMPONENT_SEQUENCE_KEYS = ("content", "items", "results", "data", "rows")
LOOKUP_FAILURE_FLAG_PRECEDENCE = ("lookup_failed", "circuit_breaker_open")
LOOKUP_FAILURE_FLAG_KEYS = frozenset(LOOKUP_FAILURE_FLAG_PRECEDENCE)
LOOKUP_FAILURE_DETAIL_PRECEDENCE = ("lookup_failure_reason",)
LOOKUP_FAILURE_DETAIL_KEYS = frozenset(LOOKUP_FAILURE_DETAIL_PRECEDENCE)
# Dataview payloads may include non-fatal diagnostic text under `error` while
# still returning a valid object with identity fields.
DATAVIEW_EXPLICIT_ERROR_KEYS = frozenset({"errorcode", "errordescription", "error_description"})
UNKNOWN_PLACEHOLDER_ERROR_TEXT_KEYS = frozenset({"error"}) | DATAVIEW_EXPLICIT_ERROR_KEYS
DATAVIEW_DIAGNOSTIC_KEYS = (
    LOOKUP_FAILURE_FLAG_KEYS | LOOKUP_FAILURE_DETAIL_KEYS | STATUS_KEYS | ERROR_TEXT_KEYS | EXPLICIT_ERROR_KEYS
)
DATAVIEW_METADATA_HINT_KEYS = frozenset(
    {
        "owner",
        "ownername",
        "owner_name",
        "ownerfullname",
        "owner_full_name",
        "description",
        "parentdatagroupid",
        "connectionid",
        "connection_id",
        "created",
        "createddate",
        "createdat",
        "created_date",
        "modified",
        "modifieddate",
        "modifiedat",
        "modified_date",
    },
)
# Legacy getDataView payloads from pre-v3.5.14 cjapy paths can classify as ERROR
# because they lack the expected identity fields, yet still carry usable metadata.
# Three operational call sites (diff snapshot, SDR inventory summary, org-report
# metadata enrichment) tolerate these specific reasons to preserve backward
# compatibility. Keep this set in one place so the three sites stay in lockstep.
TOLERATED_LEGACY_LOOKUP_REASONS: frozenset[str] = frozenset(
    {
        "missing_expected_id",
        "missing_identity",
        "insufficient_metadata",
    },
)
_DIAGNOSTIC_KEY_PREFIXES = ("error", "lookup_", "status")
_LOOKUP_MISSING_VALUE = object()
_LOOKUP_CANONICAL_KEY_ALIASES = {
    "id": "id",
    "name": "name",
    "owner": "owner",
    "ownername": "ownerName",
    "owner_name": "owner_name",
    "ownerfullname": "ownerFullName",
    "owner_full_name": "owner_full_name",
    "description": "description",
    "parentdatagroupid": "parentDataGroupId",
    "connectionid": "connectionId",
    "connection_id": "connection_id",
    "created": "created",
    "createddate": "createdDate",
    "createdat": "createdAt",
    "created_date": "created_date",
    "modified": "modified",
    "modifieddate": "modifiedDate",
    "modifiedat": "modifiedAt",
    "modified_date": "modified_date",
    "lookup_failed": "lookup_failed",
    "lookup_failure_reason": "lookup_failure_reason",
    "circuit_breaker_open": "circuit_breaker_open",
    "error": "error",
    "errorcode": "errorCode",
    "errordescription": "errorDescription",
    "error_description": "error_description",
    "status": "status",
    "statuscode": "statusCode",
    "status_code": "status_code",
    "message": "message",
    "detail": "detail",
    "title": "title",
}
_LOOKUP_OWNER_CANONICAL_KEY_ALIASES = {
    "name": "name",
    "fullname": "fullName",
    "full_name": "full_name",
    "ownerfullname": "ownerFullName",
    "login": "login",
    "email": "email",
    "imsuserid": "imsUserId",
    "id": "id",
}
logger = logging.getLogger(__name__)


class PayloadKind(Enum):
    """Normalized classification for discovery API payloads."""

    DATA = "data"
    EMPTY = "empty"
    ERROR = "error"
    INVALID = "invalid"


@dataclass(frozen=True)
class PayloadAssessment:
    """Normalized payload assessment used by discovery list/describe commands."""

    kind: PayloadKind
    rows: list[dict[str, Any]]
    reason: str
    raw_type: str


@dataclass(frozen=True)
class DataViewLookupAssessment:
    """Normalized assessment for getDataView lookup payloads."""

    kind: PayloadKind
    payload: dict[str, Any] | None
    reason: str
    raw_type: str

    @property
    def is_valid(self) -> bool:
        return self.kind is PayloadKind.DATA


def normalized_payload_keys(payload: Mapping[str, Any]) -> set[str]:
    """Return normalized dictionary keys for payload-shape checks."""
    return {str(key).strip().casefold() for key in payload}


def has_identity_value(payload: Mapping[str, Any], identity_keys: tuple[str, ...]) -> bool:
    """Return True when any identity key has a non-missing value."""
    for key in identity_keys:
        value = payload.get(key)
        if is_missing_value(value, treat_blank_string=True, treat_null_like_strings=True):
            continue
        return True
    return False


def _lookup_value_has_substance(
    value: Any,
    *,
    _seen_containers: set[int] | None = None,
) -> bool:
    """Return True when lookup values contain meaningful content.

    Empty mappings/sequences (or nested containers containing only missing leaf
    values) should be treated as absent when classifying lookup payloads.
    """
    if is_missing_value(value, treat_blank_string=True, treat_null_like_strings=True):
        return False

    if isinstance(value, Mapping):
        if not value:
            return False
        seen = _seen_containers if _seen_containers is not None else set()
        container_id = id(value)
        if container_id in seen:
            return False
        seen.add(container_id)
        return any(_lookup_value_has_substance(child, _seen_containers=seen) for child in value.values())

    if isinstance(value, (list, tuple, set)):
        if len(value) == 0:
            return False
        seen = _seen_containers if _seen_containers is not None else set()
        container_id = id(value)
        if container_id in seen:
            return False
        seen.add(container_id)
        return any(_lookup_value_has_substance(child, _seen_containers=seen) for child in value)

    return True


def _lookup_value_is_missing(value: Any) -> bool:
    return not _lookup_value_has_substance(value)


def _should_replace_lookup_value(current_value: Any, replacement_value: Any) -> bool:
    if current_value is _LOOKUP_MISSING_VALUE:
        return True
    return _lookup_value_is_missing(current_value) and not _lookup_value_is_missing(replacement_value)


def normalize_lookup_items(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Return case-folded lookup payload keys for defensive field access.

    When multiple source keys collapse to the same normalized key (for example,
    ``id`` + ``ID``), prefer any non-missing value.
    """
    normalized_items: dict[str, Any] = {}
    for key, value in payload.items():
        normalized_key = str(key).strip().casefold()
        current_value = normalized_items.get(normalized_key, _LOOKUP_MISSING_VALUE)
        if _should_replace_lookup_value(current_value, value):
            normalized_items[normalized_key] = value
    return normalized_items


def _canonicalize_lookup_owner(owner_payload: Mapping[str, Any]) -> dict[str, Any]:
    canonical_owner = dict(owner_payload)
    normalized_owner = normalize_lookup_items(canonical_owner)
    for normalized_key, canonical_key in _LOOKUP_OWNER_CANONICAL_KEY_ALIASES.items():
        if normalized_key not in normalized_owner:
            continue
        candidate_value = normalized_owner[normalized_key]
        current_value = canonical_owner.get(canonical_key, _LOOKUP_MISSING_VALUE)
        if _should_replace_lookup_value(current_value, candidate_value):
            canonical_owner[canonical_key] = candidate_value
    return canonical_owner


def canonicalize_dataview_lookup_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Backfill canonical dataview lookup keys while preserving original fields."""
    canonical_payload = dict(payload)
    normalized_items = normalize_lookup_items(canonical_payload)
    for normalized_key, canonical_key in _LOOKUP_CANONICAL_KEY_ALIASES.items():
        if normalized_key not in normalized_items:
            continue
        candidate_value = normalized_items[normalized_key]
        current_value = canonical_payload.get(canonical_key, _LOOKUP_MISSING_VALUE)
        if _should_replace_lookup_value(current_value, candidate_value):
            canonical_payload[canonical_key] = candidate_value

    owner_payload = canonical_payload.get("owner")
    if isinstance(owner_payload, Mapping):
        canonical_payload["owner"] = _canonicalize_lookup_owner(owner_payload)

    return canonical_payload


def _schema_indicates_error(
    keys: set[str],
    *,
    has_identity: bool,
    explicit_error_keys: frozenset[str] = EXPLICIT_ERROR_KEYS,
) -> bool:
    if not keys:
        return True
    if keys & explicit_error_keys:
        return True
    if has_identity:
        return False
    return bool(keys & STATUS_KEYS) and bool(keys & ERROR_TEXT_KEYS)


def looks_like_error_payload(
    payload: Mapping[str, Any],
    *,
    identity_keys: tuple[str, ...] = ("id", "name"),
    explicit_error_keys: frozenset[str] = EXPLICIT_ERROR_KEYS,
) -> bool:
    """Return True when object keys match an API-error-like shape."""
    keys = normalized_payload_keys(payload)
    has_identity = has_identity_value(payload, identity_keys)
    return _schema_indicates_error(keys, has_identity=has_identity, explicit_error_keys=explicit_error_keys)


def _lookup_field_is_present(value: Any) -> bool:
    return _lookup_value_has_substance(value)


def _lookup_contains_any_present_key(
    normalized_items: Mapping[str, Any],
    *,
    candidate_keys: frozenset[str],
) -> bool:
    return any(_lookup_field_is_present(normalized_items.get(candidate_key)) for candidate_key in candidate_keys)


def _is_diagnostic_lookup_key(normalized_key: str) -> bool:
    if normalized_key in DATAVIEW_DIAGNOSTIC_KEYS:
        return True
    return normalized_key.startswith(_DIAGNOSTIC_KEY_PREFIXES)


def _has_minimum_dataview_lookup_metadata(normalized_items: Mapping[str, Any]) -> bool:
    """Return True when lookup payload carries more than bare identity/error hints."""
    if _lookup_field_is_present(normalized_items.get("name")):
        return True

    if _lookup_contains_any_present_key(normalized_items, candidate_keys=DATAVIEW_METADATA_HINT_KEYS):
        return True

    # Allow future nested metadata payloads while still failing closed on sparse
    # scalar error objects (for example: {"id": "...", "error": "..."}).
    for key, value in normalized_items.items():
        normalized_key = str(key)
        if normalized_key == "id" or _is_diagnostic_lookup_key(normalized_key):
            continue
        if _lookup_field_is_present(value):
            return True
    return False


def _is_diagnostic_only_dataview_payload(normalized_items: Mapping[str, Any]) -> bool:
    if not has_identity_value(normalized_items, ("id", "name")):
        return False

    has_diagnostic_signal = any(
        _lookup_field_is_present(value) and _is_diagnostic_lookup_key(str(key))
        for key, value in normalized_items.items()
    )
    if not has_diagnostic_signal:
        return False

    return not _has_minimum_dataview_lookup_metadata(normalized_items)


def is_dataview_error_payload(payload: Mapping[str, Any]) -> bool:
    """Return True when getDataView payload appears to be an API error object."""
    normalized_payload = normalize_lookup_items(payload)
    if looks_like_error_payload(
        normalized_payload,
        identity_keys=("id", "name"),
        explicit_error_keys=DATAVIEW_EXPLICIT_ERROR_KEYS,
    ):
        return True

    return _is_diagnostic_only_dataview_payload(normalized_payload)


def _is_truthy_marker(value: Any) -> bool:
    if is_missing_value(value, treat_blank_string=True, treat_null_like_strings=True):
        return False
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    if isinstance(value, str):
        normalized = value.strip().casefold()
        return normalized not in {"false", "0", "no", "off"}
    try:
        return bool(value)
    except (TypeError, ValueError) as exc:
        logger.debug(
            "Treating lookup marker value as truthy after bool() coercion failure: type=%s error=%s",
            type(value).__name__,
            exc,
        )
        return True


def _first_lookup_failure_flag_key(normalized_items: Mapping[str, Any]) -> str | None:
    """Return first truthy lookup-failure flag in fixed precedence order."""
    for marker_key in LOOKUP_FAILURE_FLAG_PRECEDENCE:
        if _is_truthy_marker(normalized_items.get(marker_key)):
            return marker_key
    return None


def _first_lookup_failure_detail_key(normalized_items: Mapping[str, Any]) -> str | None:
    """Return first lookup-failure detail key with a present value."""
    for detail_key in LOOKUP_FAILURE_DETAIL_PRECEDENCE:
        detail_value = normalized_items.get(detail_key)
        if not _lookup_field_is_present(detail_value):
            continue
        return detail_key
    return None


def _normalize_dataview_lookup_payload(raw_payload: Any) -> tuple[dict[str, Any] | None, str, str]:
    raw_type = type(raw_payload).__name__
    if raw_payload is None:
        return None, raw_type, "none_payload"

    if isinstance(raw_payload, pd.DataFrame):
        # Some cjapy pathways may hand back a one-row DataFrame for getDataView.
        # Normalize this to a plain mapping so downstream validation is uniform.
        if raw_payload.empty:
            return None, raw_type, "empty_dataframe"
        records = raw_payload.to_dict("records")
        if not records:
            return None, raw_type, "empty_dataframe_records"
        first_record = records[0]
        if not isinstance(first_record, Mapping):
            return None, raw_type, "non_mapping_dataframe_row"
        return dict(first_record), raw_type, "dataframe_first_record"

    if isinstance(raw_payload, Mapping):
        return dict(raw_payload), raw_type, "mapping_payload"

    return None, raw_type, "unsupported_payload_type"


def _coerce_lookup_scalar_text(value: Any) -> str | None:
    """Safely coerce primitive lookup scalar values to text."""
    if isinstance(value, str):
        return value
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="ignore")
        except (AttributeError, TypeError, ValueError):
            return None
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    return None


def _assess_expected_lookup_id(
    normalized_items: Mapping[str, Any],
    *,
    expected_data_view_id: str | None,
) -> tuple[str | None, str | None]:
    """Validate lookup `id` against the expected data view id."""
    if expected_data_view_id is None:
        return None, None

    payload_id = normalized_items.get("id")
    if is_missing_value(payload_id, treat_blank_string=True, treat_null_like_strings=True):
        return None, "missing_expected_id"

    payload_id_text = _coerce_lookup_scalar_text(payload_id)
    if payload_id_text is None:
        return None, "invalid_id_type"

    normalized_id = payload_id_text.strip()
    if not normalized_id:
        return None, "missing_expected_id"

    if normalized_id != expected_data_view_id:
        return normalized_id, "id_mismatch"

    return normalized_id, None


def _is_legacy_unknown_lookup_placeholder(
    *,
    expected_data_view_id: str | None,
    normalized_items: Mapping[str, Any],
) -> bool:
    if expected_data_view_id is None:
        return False

    _, id_reason = _assess_expected_lookup_id(normalized_items, expected_data_view_id=expected_data_view_id)
    if id_reason is not None:
        return False

    normalized_keys = set(normalized_items)
    if not normalized_keys.issubset({"id", "name"}):
        return False

    name_value = normalized_items.get("name")
    if is_missing_value(name_value, treat_blank_string=True, treat_null_like_strings=True):
        return False
    name_text = _coerce_lookup_scalar_text(name_value)
    if name_text is None:
        return False
    return name_text.strip().casefold() == "unknown"


def _unknown_placeholder_diagnostic_key(normalized_items: Mapping[str, Any]) -> str | None:
    """Return a diagnostic key when an Unknown placeholder carries lookup-failure hints."""
    marker_key = _first_lookup_failure_flag_key(normalized_items)
    if marker_key is not None:
        return marker_key

    detail_key = _first_lookup_failure_detail_key(normalized_items)
    if detail_key is not None:
        return detail_key

    for text_key in sorted(UNKNOWN_PLACEHOLDER_ERROR_TEXT_KEYS):
        detail_value = normalized_items.get(text_key)
        if not _lookup_field_is_present(detail_value):
            continue
        return text_key

    status_keys_present = any(_lookup_field_is_present(normalized_items.get(status_key)) for status_key in STATUS_KEYS)
    if status_keys_present:
        for text_key in sorted(ERROR_TEXT_KEYS):
            detail_value = normalized_items.get(text_key)
            if not _lookup_field_is_present(detail_value):
                continue
            return text_key

    for key, value in normalized_items.items():
        if not str(key).startswith("lookup_"):
            continue
        if not _lookup_field_is_present(value):
            continue
        return str(key)

    return None


def _unknown_lookup_placeholder_reason(
    expected_data_view_id: str | None,
    normalized_items: Mapping[str, Any],
) -> str | None:
    """Return placeholder failure reason when payload matches fallback Unknown lookup output."""
    if _is_legacy_unknown_lookup_placeholder(
        expected_data_view_id=expected_data_view_id,
        normalized_items=normalized_items,
    ):
        return "legacy_unknown_placeholder"

    if expected_data_view_id is None:
        return None

    _, id_reason = _assess_expected_lookup_id(normalized_items, expected_data_view_id=expected_data_view_id)
    if id_reason is not None:
        return None

    name_value = normalized_items.get("name")
    if is_missing_value(name_value, treat_blank_string=True, treat_null_like_strings=True):
        return None
    name_text = _coerce_lookup_scalar_text(name_value)
    if name_text is None or name_text.strip().casefold() != "unknown":
        return None

    diagnostic_key = _unknown_placeholder_diagnostic_key(normalized_items)
    if diagnostic_key is None:
        return None
    return f"unknown_placeholder_diagnostic:{diagnostic_key}"


def assess_dataview_lookup_payload(
    raw_payload: Any,
    *,
    expected_data_view_id: str | None = None,
) -> DataViewLookupAssessment:
    """Classify getDataView payloads into DATA/EMPTY/ERROR/INVALID."""
    payload, raw_type, normalize_reason = _normalize_dataview_lookup_payload(raw_payload)
    if payload is None:
        kind = (
            PayloadKind.EMPTY
            if normalize_reason in {"none_payload", "empty_dataframe", "empty_dataframe_records"}
            else PayloadKind.INVALID
        )
        return DataViewLookupAssessment(kind=kind, payload=None, reason=normalize_reason, raw_type=raw_type)

    if not payload:
        return DataViewLookupAssessment(
            kind=PayloadKind.EMPTY,
            payload=None,
            reason="empty_mapping",
            raw_type=raw_type,
        )

    canonical_payload = canonicalize_dataview_lookup_payload(payload)
    normalized_items = normalize_lookup_items(canonical_payload)

    marker_key = _first_lookup_failure_flag_key(normalized_items)
    if marker_key is not None:
        return DataViewLookupAssessment(
            kind=PayloadKind.ERROR,
            payload=canonical_payload,
            reason=f"failure_flag:{marker_key}",
            raw_type=raw_type,
        )

    detail_key = _first_lookup_failure_detail_key(normalized_items)
    if detail_key is not None:
        return DataViewLookupAssessment(
            kind=PayloadKind.ERROR,
            payload=canonical_payload,
            reason=f"failure_detail:{detail_key}",
            raw_type=raw_type,
        )

    if is_dataview_error_payload(canonical_payload):
        return DataViewLookupAssessment(
            kind=PayloadKind.ERROR,
            payload=canonical_payload,
            reason="error_shape",
            raw_type=raw_type,
        )

    if not has_identity_value(normalized_items, ("id", "name")):
        return DataViewLookupAssessment(
            kind=PayloadKind.ERROR,
            payload=canonical_payload,
            reason="missing_identity",
            raw_type=raw_type,
        )

    _, id_reason = _assess_expected_lookup_id(normalized_items, expected_data_view_id=expected_data_view_id)
    if id_reason is not None:
        return DataViewLookupAssessment(
            kind=PayloadKind.ERROR,
            payload=canonical_payload,
            reason=id_reason,
            raw_type=raw_type,
        )

    unknown_placeholder_reason = _unknown_lookup_placeholder_reason(
        expected_data_view_id=expected_data_view_id,
        normalized_items=normalized_items,
    )
    if unknown_placeholder_reason is not None:
        return DataViewLookupAssessment(
            kind=PayloadKind.ERROR,
            payload=canonical_payload,
            reason=unknown_placeholder_reason,
            raw_type=raw_type,
        )

    if not _has_minimum_dataview_lookup_metadata(normalized_items):
        return DataViewLookupAssessment(
            kind=PayloadKind.ERROR,
            payload=canonical_payload,
            reason="insufficient_metadata",
            raw_type=raw_type,
        )

    return DataViewLookupAssessment(
        kind=PayloadKind.DATA,
        payload=canonical_payload,
        reason="valid_lookup_payload",
        raw_type=raw_type,
    )


def extract_component_sequence(payload: Mapping[str, Any]) -> list[Any] | None:
    """Extract list-like component rows from common API envelope shapes."""
    for key in COMPONENT_SEQUENCE_KEYS:
        if key not in payload:
            continue
        value = payload.get(key)
        if value is None:
            return []
        if isinstance(value, pd.DataFrame):
            return value.to_dict("records")
        if isinstance(value, (list, tuple, set)):
            return list(value)
        if isinstance(value, Mapping):
            nested = extract_component_sequence(value)
            if nested is not None:
                return nested
        return []
    return None


def looks_like_component_error_payload(payload: Mapping[str, Any]) -> bool:
    """Return True when a component row payload matches an API error shape."""
    return looks_like_error_payload(payload, identity_keys=("id", "name"))


def _empty_dataframe_schema_is_error(frame: pd.DataFrame) -> bool:
    return _schema_indicates_error({str(column).strip().casefold() for column in frame.columns}, has_identity=False)


def assess_component_payload(raw_payload: Any) -> PayloadAssessment:
    """Classify mixed component payload shapes into DATA/EMPTY/ERROR/INVALID."""
    raw_type = type(raw_payload).__name__

    if raw_payload is None:
        return PayloadAssessment(PayloadKind.EMPTY, [], "none_payload", raw_type)

    if isinstance(raw_payload, pd.DataFrame):
        if raw_payload.empty:
            if len(raw_payload.columns) == 0:
                return PayloadAssessment(PayloadKind.EMPTY, [], "empty_dataframe_no_columns", raw_type)
            if _empty_dataframe_schema_is_error(raw_payload):
                return PayloadAssessment(PayloadKind.ERROR, [], "empty_dataframe_error_schema", raw_type)
            return PayloadAssessment(PayloadKind.EMPTY, [], "empty_dataframe_rows", raw_type)
        return assess_component_payload(raw_payload.to_dict("records"))

    if isinstance(raw_payload, Mapping):
        if normalized_payload_keys(raw_payload) & EXPLICIT_ERROR_KEYS:
            return PayloadAssessment(PayloadKind.ERROR, [], "object_explicit_error_shape", raw_type)
        extracted_rows = extract_component_sequence(raw_payload)
        if extracted_rows is not None:
            return assess_component_payload(extracted_rows)
        if looks_like_component_error_payload(raw_payload):
            return PayloadAssessment(PayloadKind.ERROR, [], "object_error_shape", raw_type)
        return PayloadAssessment(PayloadKind.DATA, [dict(raw_payload)], "single_object_row", raw_type)

    if isinstance(raw_payload, (list, tuple, set)):
        rows = list(raw_payload)
        if not rows:
            return PayloadAssessment(PayloadKind.EMPTY, [], "empty_sequence", raw_type)

        dict_rows = [dict(row) for row in rows if isinstance(row, Mapping)]

        if not dict_rows:
            return PayloadAssessment(PayloadKind.INVALID, [], "non_mapping_sequence_rows", raw_type)

        if any(looks_like_component_error_payload(row) for row in dict_rows):
            return PayloadAssessment(PayloadKind.ERROR, [], "error_row_detected", raw_type)

        return PayloadAssessment(PayloadKind.DATA, dict_rows, "mapping_rows", raw_type)

    return PayloadAssessment(PayloadKind.INVALID, [], "unsupported_payload_type", raw_type)


def coerce_component_rows_or_none(raw_payload: Any) -> list[dict[str, Any]] | None:
    """Normalize component payloads into row dicts, or None when invalid/error."""
    assessment = assess_component_payload(raw_payload)
    if assessment.kind in {PayloadKind.DATA, PayloadKind.EMPTY}:
        return assessment.rows
    return None


def is_component_error_payload(raw_payload: Any) -> bool:
    """Return True when a component payload is assessed as an API error."""
    return assess_component_payload(raw_payload).kind is PayloadKind.ERROR


def count_component_items_or_na(raw_payload: Any) -> int | str:
    """Return component count or 'N/A' when payload is unavailable/invalid."""
    assessment = assess_component_payload(raw_payload)
    if assessment.kind in {PayloadKind.ERROR, PayloadKind.INVALID}:
        return "N/A"
    return len(assessment.rows)
