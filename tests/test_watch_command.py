"""In-process tests for the watch command entry point.

Signal tests are in test_watch_signals.py (subprocess-based, @pytest.mark.slow).
"""

from unittest.mock import MagicMock, patch

from cja_auto_sdr.cli.commands.watch import (
    _LoggingEmitter,
    _stop_requested,
    run_watch,
)
from cja_auto_sdr.output.watch_event import BaselineEvent, ChangeEvent, ErrorEvent


@patch("cja_auto_sdr.cli.commands.watch.emit_diagnostic")
def test_logging_emitter_loop_start_emits_diagnostic(mock_emit):
    emitter = _LoggingEmitter(logger=MagicMock())
    emitter.loop_start(data_view_count=2, interval_seconds=3600, watch_threshold=1)

    assert mock_emit.call_count == 1
    args, kwargs = mock_emit.call_args
    assert args[1] == "watch_loop_start"
    assert args[2] == "watch"
    assert kwargs == {"data_view_count": 2, "interval_seconds": 3600, "watch_threshold": 1}


@patch("cja_auto_sdr.cli.commands.watch.emit_diagnostic")
def test_logging_emitter_loop_stop_emits_diagnostic(mock_emit):
    emitter = _LoggingEmitter(logger=MagicMock())
    emitter.loop_stop(reason="sigint", cycles_completed=5)

    assert mock_emit.call_count == 1
    args, kwargs = mock_emit.call_args
    assert args[1] == "watch_loop_stop"
    assert args[2] == "watch"
    assert kwargs == {"reason": "sigint", "cycles_completed": 5}


@patch("cja_auto_sdr.cli.commands.watch.emit_diagnostic")
def test_logging_emitter_cycle_complete_fires_per_event(mock_emit):
    emitter = _LoggingEmitter(logger=MagicMock())
    emitter.cycle_complete(cycle=2, data_view_id="dv_abc", total_changes=0)
    emitter.cycle_complete(cycle=2, data_view_id="dv_def", total_changes=3)

    assert mock_emit.call_count == 2
    args_first, kwargs_first = mock_emit.call_args_list[0]
    _, kwargs_second = mock_emit.call_args_list[1]
    assert args_first[1] == "watch_cycle_complete"
    assert kwargs_first == {"cycle": 2, "data_view_id": "dv_abc", "total_changes": 0}
    assert kwargs_second == {"cycle": 2, "data_view_id": "dv_def", "total_changes": 3}


@patch("cja_auto_sdr.cli.commands.watch.emit_diagnostic")
@patch("cja_auto_sdr.cli.commands.watch.WatchCycleRunner")
def test_run_watch_skips_cycle_complete_for_error_events(MockRunner, mock_emit, capsys):
    """Regression: per spec, watch_cycle_complete must NOT fire for ErrorEvents."""
    runner = MockRunner.return_value
    runner.run_cycle.return_value = iter([
        ErrorEvent(
            ts="2026-05-11T00:00:00Z",
            cycle=1,
            data_view_id="dv_bad",
            stage="fetch",
            error_class="ConnectionError",
            error_message="boom",
        ),
    ])
    args = MagicMock()
    args.watch_data_views = ["dv_bad"]
    args.watch_interval = "1h"
    args.watch_threshold = 1

    _stop_requested.set()
    try:
        run_watch(args, cja=MagicMock())
    finally:
        _stop_requested.clear()

    # Filter for cycle_complete events only (loop_start/loop_stop also fire).
    cycle_complete_calls = [
        c for c in mock_emit.call_args_list if c.args and c.args[1] == "watch_cycle_complete"
    ]
    assert cycle_complete_calls == [], "watch_cycle_complete must not fire for error events"


@patch("cja_auto_sdr.cli.commands.watch._sleep_with_stop")
@patch("cja_auto_sdr.cli.commands.watch.emit_diagnostic")
@patch("cja_auto_sdr.cli.commands.watch.WatchCycleRunner")
def test_run_watch_no_phantom_cycle_when_signal_arrives_during_sleep(
    MockRunner, mock_emit, mock_sleep, capsys
):
    """Regression: signal arriving during sleep must NOT trigger a second cycle.

    Simulates the production bug where SIGINT during _sleep_with_stop left the
    outer `while True:` loop free to run a phantom cycle. _sleep_with_stop is
    mocked to set _stop_requested mid-call.
    """
    runner = MockRunner.return_value
    # Return a fresh iterator each call (cycle 1 emits baseline; if a phantom
    # cycle 2 runs, this side_effect makes it observable).
    cycles = [
        iter([
            BaselineEvent(
                ts="2026-05-11T00:00:00Z",
                cycle=1,
                data_view_id="dv_abc",
                snapshot_id="s1",
                component_counts={},
            ),
        ]),
        iter([
            ChangeEvent(
                ts="2026-05-11T01:00:00Z",
                cycle=2,
                data_view_id="dv_abc",
                previous_snapshot_id="s1",
                current_snapshot_id="s2",
                total_changes=1,
                changes_by_category={},
            ),
        ]),
    ]
    runner.run_cycle.side_effect = lambda **_: cycles.pop(0)

    def fake_sleep(_secs):
        # Mid-sleep: signal handler fires and sets the stop flag.
        _stop_requested.set()

    mock_sleep.side_effect = fake_sleep

    args = MagicMock()
    args.watch_data_views = ["dv_abc"]
    args.watch_interval = "1h"
    args.watch_threshold = 1

    try:
        exit_code = run_watch(args, cja=MagicMock())
    finally:
        _stop_requested.clear()

    assert exit_code == 0
    captured = capsys.readouterr()
    # Exactly one event line — the baseline. No phantom change event.
    event_lines = [line for line in captured.out.split("\n") if line.strip()]
    assert len(event_lines) == 1, f"expected 1 event, got {len(event_lines)}: {event_lines}"
    assert '"type":"baseline"' in event_lines[0]
    assert '"type":"change"' not in captured.out

    # loop_stop should report cycles_completed=1, not 2.
    loop_stop_calls = [
        c for c in mock_emit.call_args_list if c.args and c.args[1] == "watch_loop_stop"
    ]
    assert len(loop_stop_calls) == 1
    assert loop_stop_calls[0].kwargs["cycles_completed"] == 1


@patch("cja_auto_sdr.cli.commands.watch.WatchCycleRunner")
def test_run_watch_emits_baseline_then_exits_on_stop(MockRunner, capsys):
    runner = MockRunner.return_value
    runner.run_cycle.return_value = iter([
        BaselineEvent(
            ts="2026-05-11T00:00:00Z",
            cycle=1,
            data_view_id="dv_abc",
            snapshot_id="s1",
            component_counts={},
        ),
    ])
    args = MagicMock()
    args.watch_data_views = ["dv_abc"]
    args.watch_interval = "1h"
    args.watch_threshold = 1

    _stop_requested.set()
    try:
        exit_code = run_watch(args, cja=MagicMock())
    finally:
        _stop_requested.clear()

    assert exit_code == 0
    captured = capsys.readouterr()
    assert '"type":"baseline"' in captured.out
    assert '"data_view_id":"dv_abc"' in captured.out
