from __future__ import annotations

import pandas as pd

from cja_auto_sdr.api.fetch import ComponentFetchOutcome, classify_component_payload


def test_classify_non_empty_dataframe_is_success():
    frame = pd.DataFrame([{"id": "a"}, {"id": "b"}])
    outcome = classify_component_payload(frame)
    assert isinstance(outcome, ComponentFetchOutcome)
    assert outcome.status == "success"
    assert outcome.item_count == 2
    assert len(outcome.frame) == 2


def test_classify_empty_dataframe_is_empty():
    outcome = classify_component_payload(pd.DataFrame())
    assert outcome.status == "empty"
    assert outcome.reason == "empty_response"
    assert outcome.item_count == 0
    assert outcome.frame.empty


def test_classify_list_of_dicts_is_success():
    outcome = classify_component_payload([{"id": "a"}])
    assert outcome.status == "success"
    assert outcome.item_count == 1


def test_classify_dict_envelope_is_success():
    outcome = classify_component_payload({"content": [{"id": "a"}, {"id": "b"}]})
    assert outcome.status == "success"
    assert outcome.item_count == 2
    assert outcome.frame["id"].tolist() == ["a", "b"]


def test_classify_empty_sequence_is_empty():
    outcome = classify_component_payload([])
    assert outcome.status == "empty"
    assert outcome.item_count == 0


def test_classify_statuscode_error_dict_is_failed():
    outcome = classify_component_payload({"statusCode": 500, "message": "backend timeout"})
    assert outcome.status == "failed"
    assert "500" in outcome.error_message
    assert "backend timeout" in outcome.error_message
    assert outcome.item_count is None
    assert outcome.frame.empty


def test_classify_explicit_error_key_is_failed():
    outcome = classify_component_payload({"error": "auth expired"})
    assert outcome.status == "failed"
    assert "auth expired" in outcome.error_message


def test_classify_none_is_empty():
    outcome = classify_component_payload(None)
    assert outcome.status == "empty"
    assert outcome.item_count == 0


def test_classify_non_mapping_sequence_rows_are_failed():
    outcome = classify_component_payload([1, 2])
    assert outcome.status == "failed"
    assert "non_mapping_sequence_rows" in outcome.reason
    assert outcome.item_count is None
    assert outcome.frame.empty


def test_classify_unsupported_type_is_failed():
    outcome = classify_component_payload(42)
    assert outcome.status == "failed"
    assert "invalid" in outcome.reason.lower() or "unsupported" in outcome.reason.lower()
