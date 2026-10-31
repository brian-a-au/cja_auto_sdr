"""Subprocess-based signal tests for watch mode.

These tests exercise the actual signal handler installation, loop sleep,
signal delivery, and clean unwind — without real CJA credentials.
Marked @pytest.mark.slow so they're excluded from the default unit slice.
"""

import os
import signal
import subprocess
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

from cja_auto_sdr.cli.commands import watch as watch_mod
from cja_auto_sdr.output.watch_event import ErrorEvent


def _error_event(cycle: int, dv: str) -> ErrorEvent:
    return ErrorEvent(
        ts="2026-05-11T00:00:00Z",
        cycle=cycle,
        data_view_id=dv,
        stage="fetch",
        error_class="ConnectionError",
        error_message="boom",
    )


def _watch_args(dvs: list[str]) -> MagicMock:
    args = MagicMock()
    args.watch_data_views = dvs
    args.watch_interval = "1h"
    args.watch_threshold = 1
    args.quiet = True
    return args


def _loop_stop_calls(mock_emit: MagicMock) -> list:
    return [c for c in mock_emit.call_args_list if c.args and c.args[1] == "watch_loop_stop"]


@patch("cja_auto_sdr.cli.commands.watch.emit_diagnostic")
@patch("cja_auto_sdr.cli.commands.watch.WatchCycleRunner")
def test_stop_requested_mid_cycle_skips_remaining_data_views(MockRunner, mock_emit, capsys):
    def fake_cycle(**_kwargs):
        # The signal arrives while the first data view is in flight, so the flag is
        # already set when its event reaches the loop.
        watch_mod._stop_requested.set()
        yield _error_event(1, "dv_a")
        yield _error_event(1, "dv_b")
        yield _error_event(1, "dv_c")

    MockRunner.return_value.run_cycle.side_effect = fake_cycle

    rc = watch_mod.run_watch(_watch_args(["dv_a", "dv_b", "dv_c"]), cja=MagicMock())

    out_lines = [ln for ln in capsys.readouterr().out.splitlines() if ln.strip()]
    assert rc == 0
    assert len(out_lines) == 1
    stops = _loop_stop_calls(mock_emit)
    assert len(stops) == 1
    assert stops[0].kwargs["cycles_completed"] == 0


def test_second_signal_raises_keyboard_interrupt():
    watch_mod._install_signal_handlers()
    try:
        handler = signal.getsignal(signal.SIGINT)
        handler(signal.SIGINT, None)
        assert watch_mod._stop_requested.is_set()
        with pytest.raises(KeyboardInterrupt):
            handler(signal.SIGINT, None)
    finally:
        watch_mod._restore_signal_handlers()


@patch("cja_auto_sdr.cli.commands.watch._sleep_with_stop")
@patch("cja_auto_sdr.cli.commands.watch.emit_diagnostic")
@patch("cja_auto_sdr.cli.commands.watch.WatchCycleRunner")
def test_signal_during_sleep_stops_before_next_cycle(MockRunner, mock_emit, mock_sleep, capsys):
    MockRunner.return_value.run_cycle.side_effect = lambda **_kw: iter([_error_event(1, "dv_a")])
    mock_sleep.side_effect = lambda _s: watch_mod._stop_requested.set()

    rc = watch_mod.run_watch(_watch_args(["dv_a"]), cja=MagicMock())

    assert rc == 0
    assert MockRunner.return_value.run_cycle.call_count == 1
    stops = _loop_stop_calls(mock_emit)
    assert len(stops) == 1
    assert stops[0].kwargs["cycles_completed"] == 1


@pytest.mark.slow
def test_sigint_exits_zero():
    proc = subprocess.Popen(
        [sys.executable, "-m", "cja_auto_sdr", "--watch", "dv_does_not_exist", "--interval", "1h"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "CJA_AUTO_SDR_WATCH_TEST_MODE": "1"},
    )
    time.sleep(2)
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail("watch loop did not respond to SIGINT within 10s")

    assert proc.returncode == 0


@pytest.mark.slow
def test_sigterm_exits_zero():
    proc = subprocess.Popen(
        [sys.executable, "-m", "cja_auto_sdr", "--watch", "dv_does_not_exist", "--interval", "1h"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "CJA_AUTO_SDR_WATCH_TEST_MODE": "1"},
    )
    time.sleep(2)
    proc.send_signal(signal.SIGTERM)
    try:
        proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.fail("watch loop did not respond to SIGTERM within 10s")

    assert proc.returncode == 0
