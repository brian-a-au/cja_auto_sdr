"""Cross-platform smoke checks for lock PID liveness probes.

These run in the macOS and Windows smoke jobs as well as on Linux. On Windows,
``os.kill(pid, 0)`` sends CTRL_C_EVENT, so the probe must leave a live process
untouched.
"""

from __future__ import annotations

import os
import subprocess
import sys

import pytest

from cja_auto_sdr.core.locks.backends import _is_process_running
from cja_auto_sdr.org.cache import OrgReportLock

PROBES = [_is_process_running, OrgReportLock._is_process_running]


@pytest.fixture
def sleeping_child():
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        yield proc
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.wait(timeout=10)


@pytest.mark.parametrize("probe", PROBES)
def test_current_process_is_running(probe) -> None:
    assert probe(os.getpid()) is True


@pytest.mark.parametrize("probe", PROBES)
def test_probe_reports_live_child_without_disturbing_it(probe, sleeping_child) -> None:
    assert probe(sleeping_child.pid) is True
    # The probe must not signal, interrupt, or terminate the process.
    with pytest.raises(subprocess.TimeoutExpired):
        sleeping_child.wait(timeout=0.5)


@pytest.mark.parametrize("probe", PROBES)
def test_exited_child_is_not_running(probe) -> None:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait(timeout=30)
    assert probe(proc.pid) is False
