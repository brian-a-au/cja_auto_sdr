"""In-process tests for the watch command entry point.

Signal tests are in test_watch_signals.py (subprocess-based, @pytest.mark.slow).
"""

import signal as _signal
from unittest.mock import MagicMock, patch

import pytest

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
    runner.run_cycle.return_value = iter(
        [
            ErrorEvent(
                ts="2026-05-11T00:00:00Z",
                cycle=1,
                data_view_id="dv_bad",
                stage="fetch",
                error_class="ConnectionError",
                error_message="boom",
            ),
        ]
    )
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
    cycle_complete_calls = [c for c in mock_emit.call_args_list if c.args and c.args[1] == "watch_cycle_complete"]
    assert cycle_complete_calls == [], "watch_cycle_complete must not fire for error events"


@patch("cja_auto_sdr.cli.commands.watch._sleep_with_stop")
@patch("cja_auto_sdr.cli.commands.watch.emit_diagnostic")
@patch("cja_auto_sdr.cli.commands.watch.WatchCycleRunner")
def test_run_watch_no_phantom_cycle_when_signal_arrives_during_sleep(MockRunner, mock_emit, mock_sleep, capsys):
    """Regression: signal arriving during sleep must NOT trigger a second cycle.

    Simulates the production bug where SIGINT during _sleep_with_stop left the
    outer `while True:` loop free to run a phantom cycle. _sleep_with_stop is
    mocked to set _stop_requested mid-call.
    """
    runner = MockRunner.return_value
    # Return a fresh iterator each call (cycle 1 emits baseline; if a phantom
    # cycle 2 runs, this side_effect makes it observable).
    cycles = [
        iter(
            [
                BaselineEvent(
                    ts="2026-05-11T00:00:00Z",
                    cycle=1,
                    data_view_id="dv_abc",
                    snapshot_id="s1",
                    component_counts={},
                ),
            ]
        ),
        iter(
            [
                ChangeEvent(
                    ts="2026-05-11T01:00:00Z",
                    cycle=2,
                    data_view_id="dv_abc",
                    previous_snapshot_id="s1",
                    current_snapshot_id="s2",
                    total_changes=1,
                    changes_by_category={},
                ),
            ]
        ),
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
    # Filter for NDJSON event lines only — setup_logging now writes startup banner
    # to stdout in non-quiet mode, which would otherwise inflate the count.
    event_lines = [line for line in captured.out.split("\n") if line.strip().startswith("{")]
    assert len(event_lines) == 1, f"expected 1 NDJSON event, got {len(event_lines)}: {event_lines}"
    assert '"type":"baseline"' in event_lines[0]
    assert '"type":"change"' not in "\n".join(event_lines)

    # loop_stop should report cycles_completed=1, not 2.
    loop_stop_calls = [c for c in mock_emit.call_args_list if c.args and c.args[1] == "watch_loop_stop"]
    assert len(loop_stop_calls) == 1
    assert loop_stop_calls[0].kwargs["cycles_completed"] == 1


@patch("cja_auto_sdr.cli.commands.watch.WatchCycleRunner")
@patch("cja_auto_sdr.cli.commands.watch.setup_logging")
def test_run_watch_initializes_logging_before_emitting_diagnostics(mock_setup_logging, MockRunner, capsys):
    """Codex review found: _main_impl's sys.exit(run_watch(args)) skips the SDR
    setup_logging() call, so without an explicit call inside run_watch the
    structured-log events were dropped. Verify setup_logging is called before
    the first diagnostic fires, with log_level/log_format threaded through."""
    mock_setup_logging.return_value = MagicMock()
    runner = MockRunner.return_value
    runner.run_cycle.return_value = iter(
        [
            BaselineEvent(
                ts="2026-05-11T00:00:00Z",
                cycle=1,
                data_view_id="dv_abc",
                snapshot_id="s1",
                component_counts={},
            ),
        ]
    )
    args = MagicMock()
    args.watch_data_views = ["dv_abc"]
    args.watch_interval = "1h"
    args.watch_threshold = 1
    args.log_level = "DEBUG"
    args.log_format = "json"

    _stop_requested.set()
    try:
        run_watch(args, cja=MagicMock())
    finally:
        _stop_requested.clear()

    mock_setup_logging.assert_called_once()
    kwargs = mock_setup_logging.call_args.kwargs
    assert kwargs["log_level"] == "DEBUG"
    assert kwargs["log_format"] == "json"
    assert kwargs["batch_mode"] is True


@patch("cja_auto_sdr.cli.commands.watch.WatchCycleRunner")
def test_run_watch_emits_baseline_then_exits_on_stop(MockRunner, capsys):
    runner = MockRunner.return_value
    runner.run_cycle.return_value = iter(
        [
            BaselineEvent(
                ts="2026-05-11T00:00:00Z",
                cycle=1,
                data_view_id="dv_abc",
                snapshot_id="s1",
                component_counts={},
            ),
        ]
    )
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


@patch("cja_auto_sdr.cli.commands.watch.parse_duration_seconds")
def test_run_watch_invalid_interval_uses_exit_error(mock_parse, capsys):
    """Issue 3: defensive --interval failure path now uses _exit_error
    (ConsoleColors.error wrapper + sys.exit(1)) instead of raw print/return."""
    mock_parse.return_value = None  # simulate invalid interval

    args = MagicMock()
    args.watch_data_views = ["dv_abc"]
    args.watch_interval = "garbage"
    args.watch_threshold = 1

    with pytest.raises(SystemExit) as exc:
        run_watch(args, cja=MagicMock())

    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "ERROR:" in captured.err
    assert "garbage" in captured.err


@patch("cja_auto_sdr.cli.commands.watch.WatchCycleRunner")
def test_run_watch_restores_signal_handlers_on_exit(MockRunner):
    """Issue 1: run_watch must restore the previous SIGINT/SIGTERM handlers
    so calling it from a test session doesn't leave the watch handler
    installed across subsequent SIGINT delivery."""
    sentinel_int = _signal.getsignal(_signal.SIGINT)
    sentinel_term = _signal.getsignal(_signal.SIGTERM)

    runner = MockRunner.return_value
    runner.run_cycle.return_value = iter([])
    args = MagicMock()
    args.watch_data_views = ["dv_abc"]
    args.watch_interval = "1h"
    args.watch_threshold = 1

    _stop_requested.set()
    try:
        run_watch(args, cja=MagicMock())
    finally:
        _stop_requested.clear()

    assert _signal.getsignal(_signal.SIGINT) is sentinel_int
    assert _signal.getsignal(_signal.SIGTERM) is sentinel_term


@patch("cja_auto_sdr.cli.commands.watch.WatchCycleRunner")
def test_run_watch_emits_in_memory_note_on_stderr(MockRunner, capsys):
    """Issue 6: operators should be told once that watch holds snapshots in memory."""
    runner = MockRunner.return_value
    runner.run_cycle.return_value = iter([])
    args = MagicMock()
    args.watch_data_views = ["dv_abc"]
    args.watch_interval = "1h"
    args.watch_threshold = 1
    args.quiet = False

    _stop_requested.set()
    try:
        run_watch(args, cja=MagicMock())
    finally:
        _stop_requested.clear()

    captured = capsys.readouterr()
    assert "snapshots in memory" in captured.err
    assert captured.err.count("snapshots in memory") == 1, "note should fire once, not per cycle"


@patch("cja_auto_sdr.cli.commands.watch.WatchCycleRunner")
def test_run_watch_suppresses_in_memory_note_in_quiet_mode(MockRunner, capsys):
    """Quiet mode suppresses the in-memory note."""
    runner = MockRunner.return_value
    runner.run_cycle.return_value = iter([])
    args = MagicMock()
    args.watch_data_views = ["dv_abc"]
    args.watch_interval = "1h"
    args.watch_threshold = 1
    args.quiet = True

    _stop_requested.set()
    try:
        run_watch(args, cja=MagicMock())
    finally:
        _stop_requested.clear()

    captured = capsys.readouterr()
    assert "snapshots in memory" not in captured.err
