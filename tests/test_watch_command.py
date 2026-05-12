"""In-process tests for the watch command entry point.

Signal tests are in test_watch_signals.py (subprocess-based, @pytest.mark.slow).
"""

from unittest.mock import MagicMock, patch

from cja_auto_sdr.cli.commands.watch import (
    _LoggingEmitter,
    _stop_requested,
    run_watch,
)
from cja_auto_sdr.output.watch_event import BaselineEvent


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
    emitter.cycle_complete(cycle=2, data_view_id="dv_abc", total_changes=0, emitted=False)
    emitter.cycle_complete(cycle=2, data_view_id="dv_def", total_changes=3, emitted=True)

    assert mock_emit.call_count == 2
    fields_first = mock_emit.call_args_list[0].kwargs
    fields_second = mock_emit.call_args_list[1].kwargs
    assert fields_first["emitted"] is False
    assert fields_second["emitted"] is True


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
