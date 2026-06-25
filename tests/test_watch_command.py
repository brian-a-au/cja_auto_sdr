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


# ---------------------------------------------------------------------------
# Internal helpers — installed signal handler, _sleep_with_stop, _NullCja,
# _resolve_cja_client. These are mocked away in the loop-level tests above, so
# the unit slice never exercised their bodies (the real behavior was only
# covered by the @slow subprocess tests in test_watch_signals.py).
# ---------------------------------------------------------------------------


def test_installed_signal_handler_records_reason_and_sets_stop_flag():
    """The handler installed by _install_signal_handlers maps the signal to a
    reason string and sets the module stop flag (both SIGINT and SIGTERM)."""
    from cja_auto_sdr.cli.commands import watch as watch_mod

    watch_mod._install_signal_handlers()

    sigint_handler = _signal.getsignal(_signal.SIGINT)
    sigint_handler(_signal.SIGINT, None)
    assert watch_mod._stop_requested.is_set()
    assert watch_mod._stop_reason_holder["reason"] == "sigint"

    watch_mod._stop_requested.clear()
    watch_mod._stop_reason_holder.clear()

    sigterm_handler = _signal.getsignal(_signal.SIGTERM)
    sigterm_handler(_signal.SIGTERM, None)
    assert watch_mod._stop_requested.is_set()
    assert watch_mod._stop_reason_holder["reason"] == "sigterm"
    # reset_watch_module_state (autouse) restores the previous handlers + state.


def test_sleep_with_stop_returns_when_deadline_already_passed():
    """A zero-second interval takes the remaining<=0 early-return path."""
    from cja_auto_sdr.cli.commands.watch import _sleep_with_stop

    _stop_requested.clear()
    _sleep_with_stop(0)  # returns immediately, no hang


def test_sleep_with_stop_wakes_immediately_when_stop_event_is_set():
    """A positive interval enters the wait branch and unblocks as soon as the
    stop event fires, rather than sleeping the full duration."""
    import threading

    from cja_auto_sdr.cli.commands.watch import _sleep_with_stop

    _stop_requested.clear()
    timer = threading.Timer(0.02, _stop_requested.set)
    timer.start()
    try:
        _sleep_with_stop(2)  # would block ~2s if the wake-on-stop path were broken
    finally:
        timer.cancel()
        _stop_requested.clear()


def test_null_cja_getdataview_raises_connection_error():
    """The test-mode stub fails fast so snapshot fetch errors without real creds."""
    from cja_auto_sdr.cli.commands.watch import _NullCja

    with pytest.raises(ConnectionError, match="test mode"):
        _NullCja().getDataView("dv_x")


def test_resolve_cja_client_returns_null_cja_in_test_mode(monkeypatch):
    """With the test-mode env var set, _resolve_cja_client short-circuits to _NullCja."""
    from cja_auto_sdr.cli.commands import watch as watch_mod

    monkeypatch.setenv("CJA_AUTO_SDR_WATCH_TEST_MODE", "1")
    client = watch_mod._resolve_cja_client(MagicMock())
    assert isinstance(client, watch_mod._NullCja)


def test_resolve_cja_client_configures_and_returns_real_client(monkeypatch):
    """Without test mode, _resolve_cja_client configures credentials then returns
    generator.cjapy.CJA()."""
    from cja_auto_sdr.cli.commands import watch as watch_mod

    monkeypatch.delenv("CJA_AUTO_SDR_WATCH_TEST_MODE", raising=False)
    args = MagicMock()
    args.profile = "prod"
    args.config_file = "cfg.json"

    with (
        patch("cja_auto_sdr.api.client.configure_cjapy", return_value=(True, "env", {})) as mock_cfg,
        patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
    ):
        result = watch_mod._resolve_cja_client(args)

    mock_cfg.assert_called_once()
    assert mock_cfg.call_args.kwargs["profile"] == "prod"
    assert mock_cfg.call_args.kwargs["config_file"] == "cfg.json"
    assert result is mock_cjapy.CJA.return_value


def test_resolve_cja_client_raises_when_configuration_fails(monkeypatch):
    """A failed configure_cjapy surfaces as a RuntimeError."""
    from cja_auto_sdr.cli.commands import watch as watch_mod

    monkeypatch.delenv("CJA_AUTO_SDR_WATCH_TEST_MODE", raising=False)
    args = MagicMock()
    args.profile = None
    args.config_file = "config.json"

    with patch("cja_auto_sdr.api.client.configure_cjapy", return_value=(False, None, None)):
        with pytest.raises(RuntimeError, match="Failed to configure CJA credentials"):
            watch_mod._resolve_cja_client(args)


@patch("cja_auto_sdr.cli.commands.watch._resolve_cja_client", side_effect=RuntimeError("cred boom"))
def test_run_watch_returns_1_when_credential_resolution_fails(mock_resolve, capsys):
    """When cja is None and credential resolution raises RuntimeError, run_watch
    prints the error to stderr and returns exit code 1."""
    args = MagicMock()
    args.watch_data_views = ["dv_abc"]
    args.watch_interval = "1h"
    args.watch_threshold = 1

    exit_code = run_watch(args, cja=None)

    assert exit_code == 1
    captured = capsys.readouterr()
    assert "ERROR: cred boom" in captured.err
    mock_resolve.assert_called_once()
