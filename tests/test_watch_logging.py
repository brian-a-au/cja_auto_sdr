"""End-to-end coverage of the three watch structured-log events
(watch_loop_start, watch_cycle_complete, watch_loop_stop) firing through
the actual emit_diagnostic call path."""

from unittest.mock import MagicMock, patch

from cja_auto_sdr.cli.commands.watch import _stop_requested, run_watch
from cja_auto_sdr.output.watch_event import BaselineEvent


@patch("cja_auto_sdr.cli.commands.watch.emit_diagnostic")
@patch("cja_auto_sdr.cli.commands.watch.WatchCycleRunner")
def test_run_watch_emits_loop_start_with_correct_fields(MockRunner, mock_emit):
    """watch_loop_start fires once at entry with the configured fields."""
    runner = MockRunner.return_value
    runner.run_cycle.return_value = iter([])
    args = MagicMock()
    args.watch_data_views = ["dv_a", "dv_b"]
    args.watch_interval = "1h"
    args.watch_threshold = 0

    _stop_requested.set()
    try:
        run_watch(args, cja=MagicMock())
    finally:
        _stop_requested.clear()

    loop_start_calls = [c for c in mock_emit.call_args_list if c.args and c.args[1] == "watch_loop_start"]
    assert len(loop_start_calls) == 1
    fields = loop_start_calls[0].kwargs
    assert fields["data_view_count"] == 2
    assert fields["interval_seconds"] == 3600
    assert fields["watch_threshold"] == 0


@patch("cja_auto_sdr.cli.commands.watch.emit_diagnostic")
@patch("cja_auto_sdr.cli.commands.watch.WatchCycleRunner")
def test_run_watch_emits_loop_stop_with_fatal_when_no_signal(MockRunner, mock_emit):
    """watch_loop_stop reports `fatal` when the loop exits without a signal."""
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

    loop_stop_calls = [c for c in mock_emit.call_args_list if c.args and c.args[1] == "watch_loop_stop"]
    assert len(loop_stop_calls) == 1
    assert loop_stop_calls[0].kwargs["reason"] == "fatal"


@patch("cja_auto_sdr.cli.commands.watch.emit_diagnostic")
@patch("cja_auto_sdr.cli.commands.watch.WatchCycleRunner")
def test_run_watch_emits_loop_stop_with_sigint_reason(MockRunner, mock_emit):
    """watch_loop_stop reports `sigint` when the SIGINT handler ran."""
    from cja_auto_sdr.cli.commands import watch as watch_mod

    runner = MockRunner.return_value
    runner.run_cycle.return_value = iter([])
    args = MagicMock()
    args.watch_data_views = ["dv_abc"]
    args.watch_interval = "1h"
    args.watch_threshold = 1

    # Pre-populate the stop_reason_holder as the signal handler would.
    watch_mod._stop_reason_holder["reason"] = "sigint"
    _stop_requested.set()
    try:
        run_watch(args, cja=MagicMock())
    finally:
        _stop_requested.clear()
        watch_mod._stop_reason_holder.clear()

    loop_stop_calls = [c for c in mock_emit.call_args_list if c.args and c.args[1] == "watch_loop_stop"]
    assert len(loop_stop_calls) == 1
    assert loop_stop_calls[0].kwargs["reason"] == "sigint"


@patch("cja_auto_sdr.cli.commands.watch.emit_diagnostic")
@patch("cja_auto_sdr.cli.commands.watch.WatchCycleRunner")
def test_cycle_complete_fires_once_per_baseline_or_change_event(MockRunner, mock_emit):
    """One baseline → one cycle_complete."""
    runner = MockRunner.return_value
    runner.run_cycle.return_value = iter([
        BaselineEvent(
            ts="t", cycle=1, data_view_id="dv_a",
            snapshot_id="s", component_counts={},
        ),
    ])
    args = MagicMock()
    args.watch_data_views = ["dv_a"]
    args.watch_interval = "1h"
    args.watch_threshold = 1

    _stop_requested.set()
    try:
        run_watch(args, cja=MagicMock())
    finally:
        _stop_requested.clear()

    cycle_complete_calls = [c for c in mock_emit.call_args_list if c.args and c.args[1] == "watch_cycle_complete"]
    assert len(cycle_complete_calls) == 1
    assert cycle_complete_calls[0].kwargs["data_view_id"] == "dv_a"
