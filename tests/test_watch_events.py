import json

import pytest

from cja_auto_sdr.output.watch_event import (
    SCHEMA_VERSION,
    BaselineEvent,
    ChangeEvent,
    ErrorEvent,
    serialize_event,
)


def test_schema_version_constant():
    assert SCHEMA_VERSION == "cja-watch-event/v1"


def test_baseline_event_serialization():
    event = BaselineEvent(
        ts="2026-05-11T18:42:11Z",
        cycle=1,
        data_view_id="dv_abc",
        snapshot_id="snap-1",
        component_counts={"dimensions": 124, "metrics": 86},
    )
    line = serialize_event(event)
    assert line.endswith("\n")
    payload = json.loads(line)
    assert payload["schema"] == "cja-watch-event/v1"
    assert payload["type"] == "baseline"
    assert payload["ts"] == "2026-05-11T18:42:11Z"
    assert payload["cycle"] == 1
    assert payload["data_view_id"] == "dv_abc"
    assert payload["snapshot_id"] == "snap-1"
    assert payload["component_counts"]["dimensions"] == 124


def test_change_event_serialization():
    event = ChangeEvent(
        ts="2026-05-11T19:42:11Z",
        cycle=5,
        data_view_id="dv_abc",
        previous_snapshot_id="snap-1",
        current_snapshot_id="snap-2",
        total_changes=7,
        changes_by_category={
            "dimensions": {"added": 1, "removed": 0, "modified": 2},
            "metrics": {"added": 0, "removed": 0, "modified": 0},
            "calculated_metrics": {"added": 1, "removed": 0, "modified": 1},
            "segments": {"added": 2, "removed": 0, "modified": 0},
        },
    )
    payload = json.loads(serialize_event(event))
    assert payload["type"] == "change"
    assert payload["total_changes"] == 7
    assert payload["changes_by_category"]["segments"]["added"] == 2


def test_error_event_redacts_bearer_token():
    event = ErrorEvent(
        ts="2026-05-11T20:42:11Z",
        cycle=4,
        data_view_id="dv_abc",
        stage="fetch",
        error_class="ConnectionError",
        error_message="Authorization: Bearer abc123xyz failed",
    )
    payload = json.loads(serialize_event(event))
    assert payload["type"] == "error"
    assert "abc123xyz" not in payload["error_message"]
    assert payload["stage"] == "fetch"
    assert payload["error_class"] == "ConnectionError"


def test_event_field_order_is_schema_then_type_then_ts_first():
    # Ensures the envelope is human-scannable.
    event = BaselineEvent(
        ts="2026-05-11T18:42:11Z",
        cycle=1,
        data_view_id="dv_abc",
        snapshot_id="snap-1",
        component_counts={},
    )
    line = serialize_event(event)
    # Field-order assertion: schema key appears before type key in raw text.
    assert line.index('"schema"') < line.index('"type"') < line.index('"ts"')


@pytest.mark.parametrize("event_type", [BaselineEvent, ChangeEvent, ErrorEvent])
def test_event_lines_end_with_newline(event_type):
    # Common envelope sanity: NDJSON requires trailing newline per line.
    kwargs = {
        BaselineEvent: dict(ts="t", cycle=1, data_view_id="d", snapshot_id="s", component_counts={}),
        ChangeEvent: dict(
            ts="t", cycle=1, data_view_id="d",
            previous_snapshot_id="a", current_snapshot_id="b",
            total_changes=0, changes_by_category={},
        ),
        ErrorEvent: dict(
            ts="t", cycle=1, data_view_id="d",
            stage="fetch", error_class="E", error_message="m",
        ),
    }[event_type]
    assert serialize_event(event_type(**kwargs)).endswith("\n")
