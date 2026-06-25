# tests/test_watch_pipeline.py
from unittest.mock import MagicMock

import pytest

from cja_auto_sdr.output.watch_event import BaselineEvent, ChangeEvent, ErrorEvent
from cja_auto_sdr.pipeline.watch import WatchCycleRunner


@pytest.fixture
def fake_snapshot():
    snap = MagicMock()
    snap.data_view_id = "dv_abc"
    snap.data_view_name = "Test DV"
    snap.dimensions = [{"id": "d1"}] * 124
    snap.metrics = [{"id": "m1"}] * 86
    snap.calculated_metrics_inventory = []
    snap.segments_inventory = []
    return snap


def test_first_cycle_emits_baseline(fake_snapshot):
    snapshot_manager = MagicMock()
    snapshot_manager.create_snapshot.return_value = fake_snapshot
    comparator = MagicMock()
    runner = WatchCycleRunner(snapshot_manager=snapshot_manager, comparator=comparator, threshold=1)

    events = list(runner.run_cycle(cja=MagicMock(), data_view_ids=["dv_abc"], cycle=1))

    assert len(events) == 1
    assert isinstance(events[0], BaselineEvent)
    assert events[0].data_view_id == "dv_abc"
    assert events[0].cycle == 1
    comparator.compare.assert_not_called()


def test_second_cycle_with_no_changes_threshold_default_emits_nothing(fake_snapshot):
    snapshot_manager = MagicMock()
    snapshot_manager.create_snapshot.return_value = fake_snapshot
    comparator = MagicMock()
    diff_result = MagicMock()
    diff_result.summary.total_changes = 0
    diff_result.summary.calc_metrics_added = 0
    diff_result.summary.calc_metrics_removed = 0
    diff_result.summary.calc_metrics_modified = 0
    diff_result.summary.segments_added = 0
    diff_result.summary.segments_removed = 0
    diff_result.summary.segments_modified = 0
    comparator.compare.return_value = diff_result
    runner = WatchCycleRunner(snapshot_manager=snapshot_manager, comparator=comparator, threshold=1)

    list(runner.run_cycle(cja=MagicMock(), data_view_ids=["dv_abc"], cycle=1))  # baseline
    events = list(runner.run_cycle(cja=MagicMock(), data_view_ids=["dv_abc"], cycle=2))

    assert events == []
    comparator.compare.assert_called_once()


def test_second_cycle_with_no_changes_threshold_zero_emits_heartbeat(fake_snapshot):
    snapshot_manager = MagicMock()
    snapshot_manager.create_snapshot.return_value = fake_snapshot
    comparator = MagicMock()
    diff_result = MagicMock()
    diff_result.summary.total_changes = 0
    diff_result.summary.calc_metrics_added = 0
    diff_result.summary.calc_metrics_removed = 0
    diff_result.summary.calc_metrics_modified = 0
    diff_result.summary.segments_added = 0
    diff_result.summary.segments_removed = 0
    diff_result.summary.segments_modified = 0
    comparator.compare.return_value = diff_result
    runner = WatchCycleRunner(snapshot_manager=snapshot_manager, comparator=comparator, threshold=0)

    list(runner.run_cycle(cja=MagicMock(), data_view_ids=["dv_abc"], cycle=1))
    events = list(runner.run_cycle(cja=MagicMock(), data_view_ids=["dv_abc"], cycle=2))

    assert len(events) == 1
    assert isinstance(events[0], ChangeEvent)
    assert events[0].total_changes == 0


def test_second_cycle_with_changes_emits_change_event(fake_snapshot):
    snapshot_manager = MagicMock()
    snapshot_manager.create_snapshot.return_value = fake_snapshot
    comparator = MagicMock()
    diff_result = MagicMock()
    diff_result.summary.total_changes = 5  # metrics + dimensions
    diff_result.summary.calc_metrics_added = 1
    diff_result.summary.calc_metrics_removed = 0
    diff_result.summary.calc_metrics_modified = 1
    diff_result.summary.segments_added = 2
    diff_result.summary.segments_removed = 0
    diff_result.summary.segments_modified = 0
    diff_result.summary.metrics_added = 0
    diff_result.summary.metrics_removed = 0
    diff_result.summary.metrics_modified = 0
    diff_result.summary.dimensions_added = 1
    diff_result.summary.dimensions_removed = 0
    diff_result.summary.dimensions_modified = 4
    comparator.compare.return_value = diff_result
    runner = WatchCycleRunner(snapshot_manager=snapshot_manager, comparator=comparator, threshold=1)

    list(runner.run_cycle(cja=MagicMock(), data_view_ids=["dv_abc"], cycle=1))
    events = list(runner.run_cycle(cja=MagicMock(), data_view_ids=["dv_abc"], cycle=2))

    assert len(events) == 1
    assert isinstance(events[0], ChangeEvent)
    # Watch-specific total includes inventory:
    assert events[0].total_changes == 5 + (1 + 1) + (2 + 0 + 0)


def test_fetch_failure_emits_error_event_and_continues():
    snapshot_manager = MagicMock()
    snapshot_manager.create_snapshot.side_effect = [
        ConnectionError("network down"),
    ]
    comparator = MagicMock()
    runner = WatchCycleRunner(snapshot_manager=snapshot_manager, comparator=comparator, threshold=1)

    events = list(runner.run_cycle(cja=MagicMock(), data_view_ids=["dv_abc"], cycle=1))

    assert len(events) == 1
    assert isinstance(events[0], ErrorEvent)
    assert events[0].stage == "fetch"
    assert events[0].error_class == "ConnectionError"
    assert events[0].data_view_id == "dv_abc"


def test_diff_failure_emits_error_event_and_continues(fake_snapshot):
    """A comparator.compare() exception on a non-baseline cycle yields an
    ErrorEvent with stage='diff' and does not abort the run."""
    snapshot_manager = MagicMock()
    snapshot_manager.create_snapshot.return_value = fake_snapshot
    comparator = MagicMock()
    comparator.compare.side_effect = ValueError("diff exploded")
    runner = WatchCycleRunner(snapshot_manager=snapshot_manager, comparator=comparator, threshold=1)

    list(runner.run_cycle(cja=MagicMock(), data_view_ids=["dv_abc"], cycle=1))  # baseline
    events = list(runner.run_cycle(cja=MagicMock(), data_view_ids=["dv_abc"], cycle=2))

    assert len(events) == 1
    assert isinstance(events[0], ErrorEvent)
    assert events[0].stage == "diff"
    assert events[0].error_class == "ValueError"
    assert events[0].data_view_id == "dv_abc"


def test_one_failure_does_not_block_other_data_views(fake_snapshot):
    snapshot_manager = MagicMock()
    snapshot_manager.create_snapshot.side_effect = [
        ConnectionError("network down"),
        fake_snapshot,
    ]
    comparator = MagicMock()
    runner = WatchCycleRunner(snapshot_manager=snapshot_manager, comparator=comparator, threshold=1)

    events = list(runner.run_cycle(cja=MagicMock(), data_view_ids=["dv_bad", "dv_good"], cycle=1))

    assert len(events) == 2
    assert isinstance(events[0], ErrorEvent)
    assert events[0].data_view_id == "dv_bad"
    assert isinstance(events[1], BaselineEvent)
    assert events[1].data_view_id == "dv_good"
