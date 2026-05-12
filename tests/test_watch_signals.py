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

import pytest


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
