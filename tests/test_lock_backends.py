"""Tests for lock backend and manager behavior."""

from __future__ import annotations

import errno
import json
import multiprocessing
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import patch

import pytest

import cja_auto_sdr.core.locks.backends as backends_module
from cja_auto_sdr.core.exceptions import LockOwnershipLostError
from cja_auto_sdr.core.locks.backends import (
    AcquireStatus,
    FcntlFileLockBackend,
    LeaseFileLockBackend,
    LockInfo,
)
from cja_auto_sdr.core.locks.manager import LockManager


def _build_lock_info(
    lock_id: str,
    owner: str = "test-owner",
    *,
    pid: int | None = None,
    host: str | None = None,
    started_at: str | None = None,
    updated_at: str | None = None,
    backend: str = "lease",
) -> LockInfo:
    now = datetime.now(UTC).isoformat()
    return LockInfo(
        lock_id=lock_id,
        pid=os.getpid() if pid is None else pid,
        host=socket.gethostname() if host is None else host,
        owner=owner,
        started_at=now if started_at is None else started_at,
        updated_at=now if updated_at is None else updated_at,
        backend=backend,
        version=1,
    )


def _write_lock_info(lock_path: Path, lock_id: str, *, pid: int | None = None) -> None:
    info = _build_lock_info(lock_id, pid=pid)
    metadata_path = lock_path.with_name(f"{lock_path.name}.info")
    metadata_path.write_text(json.dumps(info.to_dict()) + "\n", encoding="utf-8")


@pytest.fixture
def live_foreign_pid():
    """PID of a live child process (not this process), killed in teardown."""
    proc = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        yield proc.pid
    finally:
        proc.kill()
        proc.wait()


def _flock_holder_worker(lock_path: str, ready_path: str, hold_seconds: float) -> None:
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o600)
    try:
        if backends_module.fcntl is None:
            return
        backends_module.fcntl.flock(fd, backends_module.fcntl.LOCK_EX)
        Path(ready_path).write_text("1", encoding="utf-8")
        time.sleep(hold_seconds)
    finally:
        os.close(fd)


def _wait_for_ready(path: Path, timeout_seconds: float = 3.0) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        if path.exists() and path.read_text(encoding="utf-8").strip() == "1":
            return
        time.sleep(0.02)
    raise AssertionError(f"Timed out waiting for ready signal: {path}")


def test_lease_backend_acquire_writes_bootstrap_metadata() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lease.lock"
        backend = LeaseFileLockBackend()

        handle = backend.acquire(lock_path, stale_threshold_seconds=3600)

        assert handle is not None
        info = backend.read_info(lock_path)
        assert info is not None
        assert info.lock_id == handle.lock_id
        assert info.pid == os.getpid()
        assert info.backend == "lease"

        backend.release(handle)
        assert not lock_path.exists()


def test_lease_backend_waits_for_transient_unreadable_lock_file(live_foreign_pid: int) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lease.lock"
        lock_path.write_text("marker\n", encoding="utf-8")
        metadata_path = lock_path.with_name(f"{lock_path.name}.info")
        metadata_path.write_text("", encoding="utf-8")
        backend = LeaseFileLockBackend()

        lock_id = "delayed-lock-id"

        def _delayed_write() -> None:
            time.sleep(backend.unreadable_retry_sleep_seconds * 2)
            _write_lock_info(lock_path, lock_id, pid=live_foreign_pid)

        writer = threading.Thread(target=_delayed_write, daemon=True)
        writer.start()
        try:
            handle = backend.acquire(lock_path, stale_threshold_seconds=3600)
        finally:
            writer.join(timeout=2)

        # Acquisition should fail because metadata became readable and fresh.
        assert handle is None
        info = backend.read_info(lock_path)
        assert info is not None
        assert info.lock_id == lock_id


def test_lease_backend_reclaims_persistently_unreadable_lock_file() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lease.lock"
        lock_path.write_text("{bad json", encoding="utf-8")
        backend = LeaseFileLockBackend()

        start = time.monotonic()
        handle = backend.acquire(lock_path, stale_threshold_seconds=3600)
        elapsed = time.monotonic() - start

        assert handle is not None
        # Recovery should be bounded by retry window, not stale threshold.
        assert elapsed < 2.0
        backend.release(handle)


def test_lock_manager_heartbeat_updates_lease_metadata() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lease.lock"
        manager = LockManager(
            lock_path=lock_path,
            owner="test-owner",
            stale_threshold_seconds=1,
            backend_name="lease",
        )

        assert manager.acquire() is True
        first_info = manager.read_info()
        assert first_info is not None
        first_updated_at = first_info["updated_at"]

        refreshed = False
        deadline = time.time() + 3
        while time.time() < deadline:
            current_info = manager.read_info()
            if current_info is not None and current_info["updated_at"] != first_updated_at:
                refreshed = True
                break
            time.sleep(0.1)

        manager.release()
        assert refreshed is True


def test_lock_manager_fails_closed_when_lease_heartbeat_write_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lease.lock"
        manager = LockManager(
            lock_path=lock_path,
            owner="test-owner",
            stale_threshold_seconds=1,
            backend_name="lease",
        )
        assert manager.acquire() is True

        original_release = manager.backend.release
        release_calls = {"count": 0}

        def _release_wrapper(handle):  # type: ignore[no-untyped-def]
            release_calls["count"] += 1
            return original_release(handle)

        monkeypatch.setattr(manager.backend, "release", _release_wrapper)
        monkeypatch.setattr(
            manager.backend,
            "write_info",
            lambda handle, info: (_ for _ in ()).throw(OSError(errno.EIO, "heartbeat write failed")),
        )

        deadline = time.time() + 4
        while time.time() < deadline and not manager.lock_lost:
            time.sleep(0.05)

        assert manager.lock_lost is True
        assert manager.acquired is False
        assert release_calls["count"] >= 1
        with pytest.raises(LockOwnershipLostError):
            manager.ensure_held()


def test_lock_manager_writes_metadata_to_sidecar_file() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lease.lock"
        sidecar_path = lock_path.with_name(f"{lock_path.name}.info")
        manager = LockManager(
            lock_path=lock_path,
            owner="test-owner",
            stale_threshold_seconds=3600,
            backend_name="lease",
        )

        assert manager.acquire() is True
        assert sidecar_path.exists()
        payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
        assert payload["backend"] == "lease"
        assert payload["owner"] == "test-owner"
        manager.release()


def test_lock_manager_falls_back_to_lease_when_flock_unsupported(monkeypatch: pytest.MonkeyPatch) -> None:
    if backends_module.fcntl is None:
        pytest.skip("fcntl not available on this platform")

    def _unsupported_flock(fd: int, operation: int) -> None:
        del fd, operation
        raise OSError(errno.EOPNOTSUPP, "flock unsupported")

    monkeypatch.setattr(backends_module.fcntl, "flock", _unsupported_flock)

    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lock.lock"
        manager = LockManager(
            lock_path=lock_path,
            owner="test-owner",
            stale_threshold_seconds=10,
            backend_name="auto",
        )
        assert isinstance(manager.backend, FcntlFileLockBackend)

        assert manager.acquire() is True
        assert isinstance(manager.backend, LeaseFileLockBackend)
        info = manager.read_info()
        assert info is not None
        assert info["backend"] == "lease"
        manager.release()


def test_lock_manager_surfaces_non_contention_flock_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    if backends_module.fcntl is None:
        pytest.skip("fcntl not available on this platform")

    def _broken_flock(fd: int, operation: int) -> None:
        del fd, operation
        raise OSError(errno.EIO, "flock I/O error")

    monkeypatch.setattr(backends_module.fcntl, "flock", _broken_flock)

    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lock.lock"
        manager = LockManager(
            lock_path=lock_path,
            owner="test-owner",
            stale_threshold_seconds=10,
            backend_name="auto",
        )
        with pytest.raises(OSError, match="flock I/O error"):
            manager.acquire()
        assert isinstance(manager.backend, FcntlFileLockBackend)


def test_fcntl_unsupported_path_does_not_unlink_existing_sidecar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if backends_module.fcntl is None:
        pytest.skip("fcntl not available on this platform")

    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lock.lock"
        metadata_path = lock_path.with_name(f"{lock_path.name}.info")
        existing = _build_lock_info("existing-owner-id", owner="existing-owner", backend="lease")
        metadata_path.write_text(json.dumps(existing.to_dict()) + "\n", encoding="utf-8")

        backend = FcntlFileLockBackend()
        fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)

        def _unsupported_flock(fd_: int, operation: int) -> None:
            del fd_, operation
            raise OSError(errno.EOPNOTSUPP, "flock unsupported")

        monkeypatch.setattr(backend, "_open_lock_file", lambda path: (fd, True))
        monkeypatch.setattr(backends_module.fcntl, "flock", _unsupported_flock)

        result = backend.acquire_result(lock_path, stale_threshold_seconds=10)
        assert result.status == AcquireStatus.BACKEND_UNAVAILABLE
        assert metadata_path.exists()
        current = backend.read_info(lock_path)
        assert current is not None
        assert current.lock_id == "existing-owner-id"


def test_fcntl_backend_blocks_when_active_lease_lock_exists() -> None:
    if backends_module.fcntl is None:
        pytest.skip("fcntl not available on this platform")

    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lock.lock"
        lease_manager = LockManager(
            lock_path=lock_path,
            owner="lease-owner",
            stale_threshold_seconds=3600,
            backend_name="lease",
        )
        assert lease_manager.acquire() is True

        fcntl_manager = LockManager(
            lock_path=lock_path,
            owner="fcntl-owner",
            stale_threshold_seconds=3600,
            backend_name="fcntl",
        )
        try:
            assert fcntl_manager.acquire() is False
        finally:
            lease_manager.release()

        assert fcntl_manager.acquire() is True
        fcntl_manager.release()


def test_fcntl_backend_blocks_when_lease_lock_created_after_path_check() -> None:
    if backends_module.fcntl is None:
        pytest.skip("fcntl not available on this platform")

    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lock.lock"
        lease_manager = LockManager(
            lock_path=lock_path,
            owner="lease-owner",
            stale_threshold_seconds=3600,
            backend_name="lease",
        )
        assert lease_manager.acquire() is True

        # Simulate the race condition by forcing the fcntl open path to report
        # "not created exclusively", which requires metadata validation.
        preopened_fd = os.open(lock_path, os.O_RDWR)
        try:
            with patch.object(FcntlFileLockBackend, "_open_lock_file", return_value=(preopened_fd, False)):
                fcntl_manager = LockManager(
                    lock_path=lock_path,
                    owner="fcntl-owner",
                    stale_threshold_seconds=3600,
                    backend_name="fcntl",
                )
                assert fcntl_manager.acquire() is False
        finally:
            try:
                os.close(preopened_fd)
            except OSError:
                pass

        lease_manager.release()


def test_fcntl_backend_retries_when_lock_path_disappears_mid_acquire(monkeypatch: pytest.MonkeyPatch) -> None:
    if backends_module.fcntl is None:
        pytest.skip("fcntl not available on this platform")

    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lock.lock"
        lock_path.touch()
        backend = FcntlFileLockBackend()

        first_fd = os.open(lock_path, os.O_RDWR)
        second_fd = os.open(lock_path, os.O_RDWR)
        open_count = {"count": 0}

        def _open_side_effect(path: Path) -> tuple[int, bool]:
            assert path == lock_path
            open_count["count"] += 1
            if open_count["count"] == 1:
                return first_fd, False
            return second_fd, False

        read_count = {"count": 0}

        def _read_side_effect(path: Path) -> tuple[LockInfo | None, bool]:
            assert path == lock_path
            read_count["count"] += 1
            if read_count["count"] == 1:
                # Simulate lock path disappearing mid-acquire.
                return None, False
            return _build_lock_info("stable-owner", backend="fcntl"), True

        monkeypatch.setattr(backend, "_open_lock_file", _open_side_effect)
        monkeypatch.setattr(backend, "_read_info_with_retries", _read_side_effect)
        monkeypatch.setattr(backend, "_fd_matches_path", lambda fd, path: True)

        handle = backend.acquire(lock_path, stale_threshold_seconds=3600)
        assert handle is not None
        assert open_count["count"] == 2
        assert handle.fd == second_fd
        backend.release(handle)

        with pytest.raises(OSError):
            os.fstat(first_fd)


def test_lease_backend_does_not_expire_local_live_pid_even_if_old(live_foreign_pid: int) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lease.lock"
        old = datetime(2000, 1, 1, tzinfo=UTC).isoformat()
        info = _build_lock_info(
            "live-local-pid",
            owner="live-owner",
            pid=live_foreign_pid,
            host=socket.gethostname(),
            started_at=old,
            updated_at=old,
            backend="lease",
        )
        lock_path.write_text(json.dumps(info.to_dict()) + "\n", encoding="utf-8")

        backend = LeaseFileLockBackend()
        handle = backend.acquire(lock_path, stale_threshold_seconds=1)
        assert handle is None

        current = backend.read_info(lock_path)
        assert current is not None
        assert current.lock_id == "live-local-pid"


def test_lease_lock_with_own_pid_but_unknown_lock_id_is_stale(tmp_path: Path) -> None:
    lock_path = tmp_path / "org.lock"
    old = datetime(2000, 1, 1, tzinfo=UTC).isoformat()
    info = _build_lock_info(
        "previous-run",
        pid=os.getpid(),
        started_at=old,
        updated_at=old,
        backend="lease",
    )
    lock_path.write_text("previous-run\n", encoding="utf-8")
    lock_path.with_name(f"{lock_path.name}.info").write_text(json.dumps(info.to_dict()) + "\n", encoding="utf-8")

    result = LeaseFileLockBackend().acquire_result(lock_path, stale_threshold_seconds=60)

    assert result.status == AcquireStatus.ACQUIRED
    assert result.handle is not None
    LeaseFileLockBackend().release(result.handle)


def test_lease_lock_held_in_this_process_is_not_stolen(tmp_path: Path) -> None:
    backend = LeaseFileLockBackend()
    first = backend.acquire_result(tmp_path / "org.lock", stale_threshold_seconds=60)
    assert first.status == AcquireStatus.ACQUIRED
    assert first.handle is not None
    second = backend.acquire_result(tmp_path / "org.lock", stale_threshold_seconds=60)
    assert second.status == AcquireStatus.CONTENDED
    backend.release(first.handle)


def test_lock_info_from_dict_rejects_modern_bool_pid() -> None:
    payload = _build_lock_info("modern-bool-pid").to_dict()
    payload["pid"] = True
    assert LockInfo.from_dict(payload) is None


def test_lock_info_from_dict_rejects_legacy_bool_pid() -> None:
    payload = {
        "pid": True,
        "timestamp": time.time() - 60,
        "started_at": datetime.now(UTC).isoformat(),
    }
    assert LockInfo.from_dict(payload) is None


@pytest.mark.parametrize("invalid_pid", [0, -1, 10**40, True])
def test_backend_pid_liveness_rejects_invalid_values(invalid_pid: int) -> None:
    assert backends_module._is_process_running(invalid_pid) is False


@pytest.mark.parametrize("invalid_pid", [0, -1, 10**40])
def test_lease_backend_reclaims_same_host_invalid_pid_metadata(invalid_pid: int) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lease.lock"
        lock_path.write_text("lease-marker\n", encoding="utf-8")
        info = _build_lock_info(
            f"invalid-pid-{invalid_pid}",
            owner="invalid-owner",
            pid=invalid_pid,
            host=socket.gethostname(),
            backend="lease",
        )
        metadata_path = lock_path.with_name(f"{lock_path.name}.info")
        metadata_path.write_text(json.dumps(info.to_dict()) + "\n", encoding="utf-8")

        backend = LeaseFileLockBackend()
        handle = backend.acquire(lock_path, stale_threshold_seconds=3600)
        assert handle is not None
        backend.release(handle)


def test_lease_backend_reclaims_stale_bool_pid_metadata() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lease.lock"
        lock_path.write_text("lease-marker\n", encoding="utf-8")
        metadata_path = lock_path.with_name(f"{lock_path.name}.info")
        payload = _build_lock_info("bool-pid-lock", backend="lease").to_dict()
        payload["pid"] = True
        metadata_path.write_text(json.dumps(payload) + "\n", encoding="utf-8")
        old = time.time() - 10
        os.utime(metadata_path, (old, old))

        with patch.object(backends_module, "_is_process_running", return_value=True) as is_running:
            backend = LeaseFileLockBackend()
            handle = backend.acquire(lock_path, stale_threshold_seconds=1)
            assert handle is not None
            assert is_running.call_count == 0
            backend.release(handle)


def test_lease_backend_reclaims_local_fcntl_metadata_when_no_flock_held() -> None:
    if backends_module.fcntl is None:
        pytest.skip("fcntl not available on this platform")

    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lease.lock"
        info = _build_lock_info(
            "local-fcntl-holder",
            owner="local-owner",
            pid=os.getpid(),
            host=socket.gethostname(),
            backend="fcntl",
        )
        lock_path.write_text(json.dumps(info.to_dict()) + "\n", encoding="utf-8")

        backend = LeaseFileLockBackend()
        handle = backend.acquire(lock_path, stale_threshold_seconds=3600)
        assert handle is not None
        backend.release(handle)


def test_metadata_write_failure_does_not_leave_fresh_false_lockout() -> None:
    if backends_module.fcntl is None:
        pytest.skip("fcntl not available on this platform")

    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lock.lock"
        sidecar_path = lock_path.with_name(f"{lock_path.name}.info")
        manager = LockManager(
            lock_path=lock_path,
            owner="test-owner",
            stale_threshold_seconds=3600,
            backend_name="fcntl",
        )

        write_calls = {"count": 0}
        original_write = FcntlFileLockBackend.write_info

        def _fail_first_write(self: FcntlFileLockBackend, handle, info):  # type: ignore[no-untyped-def]
            write_calls["count"] += 1
            if write_calls["count"] == 1:
                raise OSError(errno.EIO, "simulated write failure")
            return original_write(self, handle, info)

        with patch.object(FcntlFileLockBackend, "write_info", _fail_first_write):
            assert manager.acquire() is False

        # Failure path writes a tombstone sidecar to avoid fresh missing-metadata lockout.
        tombstone = json.loads(sidecar_path.read_text(encoding="utf-8"))
        assert tombstone["pid"] == -1
        assert tombstone["host"] == "released"

        # Recovery should not wait for stale_threshold; immediate retry succeeds.
        assert manager.acquire() is True
        manager.release()


def test_fcntl_blocks_fresh_preexisting_lock_file_without_sidecar() -> None:
    if backends_module.fcntl is None:
        pytest.skip("fcntl not available on this platform")

    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lock.lock"
        lock_path.write_text("lease-marker\n", encoding="utf-8")
        manager = LockManager(
            lock_path=lock_path,
            owner="test-owner",
            stale_threshold_seconds=3600,
            backend_name="fcntl",
        )
        assert manager.acquire() is False


def test_fcntl_reclaims_stale_preexisting_lock_file_without_sidecar() -> None:
    if backends_module.fcntl is None:
        pytest.skip("fcntl not available on this platform")

    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lock.lock"
        lock_path.write_text("lease-marker\n", encoding="utf-8")
        old = time.time() - 10
        os.utime(lock_path, (old, old))
        manager = LockManager(
            lock_path=lock_path,
            owner="test-owner",
            stale_threshold_seconds=3600,
            backend_name="fcntl",
        )
        assert manager.acquire() is True
        manager.release()


def test_write_failure_path_releases_without_manager_unlink(monkeypatch: pytest.MonkeyPatch) -> None:
    if backends_module.fcntl is None:
        pytest.skip("fcntl not available on this platform")

    with tempfile.TemporaryDirectory() as tmpdir:
        manager = LockManager(
            lock_path=Path(tmpdir) / "lock.lock",
            owner="test-owner",
            stale_threshold_seconds=3600,
            backend_name="fcntl",
        )

        events: list[str] = []

        def _fail_write(handle, info):  # type: ignore[no-untyped-def]
            del handle, info
            raise OSError(errno.EIO, "simulated write failure")

        original_release = manager.backend.release

        def _release_wrapper(handle):  # type: ignore[no-untyped-def]
            events.append("release")
            return original_release(handle)

        monkeypatch.setattr(manager.backend, "write_info", _fail_write)
        monkeypatch.setattr(manager.backend, "release", _release_wrapper)

        assert manager.acquire() is False
        assert events == ["release"]


def test_fcntl_backend_reclaims_stale_unreadable_metadata_file() -> None:
    if backends_module.fcntl is None:
        pytest.skip("fcntl not available on this platform")

    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lock.lock"
        lock_path.write_text("{legacy-corrupt", encoding="utf-8")
        old = time.time() - 7200
        os.utime(lock_path, (old, old))

        manager = LockManager(
            lock_path=lock_path,
            owner="test-owner",
            stale_threshold_seconds=1,
            backend_name="fcntl",
        )
        assert manager.acquire() is True
        info = manager.read_info()
        assert info is not None
        assert info["backend"] == "fcntl"
        manager.release()


def test_legacy_lock_metadata_is_parsed_for_staleness_recovery(monkeypatch: pytest.MonkeyPatch) -> None:
    if backends_module.fcntl is None:
        pytest.skip("fcntl not available on this platform")

    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lock.lock"
        legacy_payload = {
            "pid": 12345,
            "timestamp": time.time(),
            "started_at": datetime.now(UTC).isoformat(),
            "version": "bad",
        }
        lock_path.write_text(json.dumps(legacy_payload) + "\n", encoding="utf-8")

        monkeypatch.setattr(backends_module, "_is_process_running", lambda pid: False)

        manager = LockManager(
            lock_path=lock_path,
            owner="test-owner",
            stale_threshold_seconds=3600,
            backend_name="fcntl",
        )
        assert manager.acquire() is True
        info = manager.read_info()
        assert info is not None
        assert info["backend"] == "fcntl"
        manager.release()


@pytest.mark.parametrize(
    ("legacy_timestamp", "legacy_version"),
    [
        (float("nan"), "bad"),
        (float("inf"), float("inf")),
        (-float("inf"), -float("inf")),
        (10**20, 10**40),
    ],
)
def test_legacy_lock_metadata_malformed_numeric_fields_do_not_crash_acquire(
    monkeypatch: pytest.MonkeyPatch,
    legacy_timestamp: float,
    legacy_version: float | str | int,
) -> None:
    if backends_module.fcntl is None:
        pytest.skip("fcntl not available on this platform")

    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lock.lock"
        legacy_payload = {
            "pid": 12345,
            "timestamp": legacy_timestamp,
            "started_at": legacy_timestamp,
            "updated_at": legacy_timestamp,
            "version": legacy_version,
        }
        lock_path.write_text(json.dumps(legacy_payload) + "\n", encoding="utf-8")

        monkeypatch.setattr(backends_module, "_is_process_running", lambda pid: False)

        manager = LockManager(
            lock_path=lock_path,
            owner="test-owner",
            stale_threshold_seconds=3600,
            backend_name="fcntl",
        )
        assert manager.acquire() is True
        info = manager.read_info()
        assert info is not None
        assert info["backend"] == "fcntl"
        manager.release()


def test_lease_backend_blocks_takeover_of_active_remote_fcntl_holder() -> None:
    if backends_module.fcntl is None:
        pytest.skip("fcntl not available on this platform")

    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lock.lock"
        old = datetime(2000, 1, 1, tzinfo=UTC).isoformat()
        info = _build_lock_info(
            "remote-fcntl-holder",
            owner="remote-owner",
            host="remote-host",
            started_at=old,
            updated_at=old,
            backend="fcntl",
        )
        lock_path.write_text(json.dumps(info.to_dict()) + "\n", encoding="utf-8")

        ready_path = Path(tmpdir) / "ready.txt"
        proc = multiprocessing.Process(
            target=_flock_holder_worker,
            args=(str(lock_path), str(ready_path), 1.5),
        )
        proc.start()
        try:
            _wait_for_ready(ready_path)
            backend = LeaseFileLockBackend()
            assert backend.acquire(lock_path, stale_threshold_seconds=1) is None
        finally:
            proc.join(timeout=3)
            assert not proc.is_alive()


def test_lease_backend_reclaims_stale_remote_fcntl_metadata_when_unlock_observed() -> None:
    if backends_module.fcntl is None:
        pytest.skip("fcntl not available on this platform")

    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lock.lock"
        old = datetime(2000, 1, 1, tzinfo=UTC).isoformat()
        info = _build_lock_info(
            "remote-fcntl-holder",
            owner="remote-owner",
            host="remote-host",
            started_at=old,
            updated_at=old,
            backend="fcntl",
        )
        lock_path.write_text(json.dumps(info.to_dict()) + "\n", encoding="utf-8")

        backend = LeaseFileLockBackend()
        handle = backend.acquire(lock_path, stale_threshold_seconds=1)
        assert handle is not None
        backend.release(handle)


def test_lease_backend_reclaims_stale_missing_metadata_when_flock_probe_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lease.lock"
        lock_path.write_text("marker\n", encoding="utf-8")
        old = time.time() - 7200
        os.utime(lock_path, (old, old))

        backend = LeaseFileLockBackend()
        monkeypatch.setattr(backends_module, "_is_fcntl_lock_active", lambda path: None)

        handle = backend.acquire(lock_path, stale_threshold_seconds=1)
        assert handle is not None
        backend.release(handle)


def test_lease_backend_blocks_fresh_missing_metadata_when_flock_probe_reports_unlocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lease.lock"
        lock_path.write_text("marker\n", encoding="utf-8")

        backend = LeaseFileLockBackend()
        monkeypatch.setattr(backends_module, "_is_fcntl_lock_active", lambda path: False)

        handle = backend.acquire(lock_path, stale_threshold_seconds=3600)
        assert handle is None


def test_lease_backend_reclaims_stale_missing_metadata_when_flock_probe_reports_unlocked(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lease.lock"
        lock_path.write_text("marker\n", encoding="utf-8")
        old = time.time() - 10
        os.utime(lock_path, (old, old))

        backend = LeaseFileLockBackend()
        monkeypatch.setattr(backends_module, "_is_fcntl_lock_active", lambda path: False)

        handle = backend.acquire(lock_path, stale_threshold_seconds=3600)
        assert handle is not None
        backend.release(handle)


def test_lease_backend_blocks_fresh_missing_metadata_when_flock_probe_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lease.lock"
        lock_path.write_text("marker\n", encoding="utf-8")

        backend = LeaseFileLockBackend()
        monkeypatch.setattr(backends_module, "_is_fcntl_lock_active", lambda path: None)

        handle = backend.acquire(lock_path, stale_threshold_seconds=3600)
        assert handle is None


def test_lease_release_closes_fd_before_unlink(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lease.lock"
        backend = LeaseFileLockBackend()
        handle = backend.acquire(lock_path, stale_threshold_seconds=3600)
        assert handle is not None

        events: list[str] = []
        original_close = backends_module.os.close

        def _close_wrapper(fd: int) -> None:
            events.append("close")
            original_close(fd)

        def _unlink_wrapper(path: Path) -> bool:
            events.append("unlink")
            return True

        monkeypatch.setattr(backends_module.os, "close", _close_wrapper)
        monkeypatch.setattr(backend, "_safe_unlink", _unlink_wrapper)

        backend.release(handle)
        assert events[0] == "close"
        assert "unlink" in events


def test_lease_release_writes_tombstone_when_unlink_fails(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lease.lock"
        backend = LeaseFileLockBackend()
        handle = backend.acquire(lock_path, stale_threshold_seconds=3600)
        assert handle is not None

        monkeypatch.setattr(backend, "_safe_unlink", lambda path: False)
        backend.release(handle)

        info = backend.read_info(lock_path)
        assert info is not None
        assert info.lock_id == handle.lock_id
        assert info.pid == -1
        assert info.host == "released"


def test_lease_release_does_not_unlink_new_owner_sidecar_on_race(monkeypatch: pytest.MonkeyPatch) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lease.lock"
        metadata_path = lock_path.with_name(f"{lock_path.name}.info")
        backend = LeaseFileLockBackend()
        handle = backend.acquire(lock_path, stale_threshold_seconds=3600)
        assert handle is not None

        original_unlink_if_inode = backend._safe_unlink_if_inode
        injected = {"done": False}
        new_lock_id = "new-owner-lock-id"

        def _unlink_with_race(path: Path, expected_inode: tuple[int, int]) -> bool:
            result = original_unlink_if_inode(path, expected_inode)
            if path == lock_path and result and not injected["done"]:
                injected["done"] = True
                lock_path.write_text("marker\n", encoding="utf-8")
                new_info = _build_lock_info(new_lock_id, owner="new-owner", backend="lease")
                metadata_path.write_text(json.dumps(new_info.to_dict()) + "\n", encoding="utf-8")
            return result

        monkeypatch.setattr(backend, "_safe_unlink_if_inode", _unlink_with_race)

        backend.release(handle)
        current = backend.read_info(lock_path)
        assert current is not None
        assert current.lock_id == new_lock_id
        assert metadata_path.exists()


def test_failed_metadata_write_does_not_unlink_lock_path() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lock.lock"
        manager = LockManager(
            lock_path=lock_path,
            owner="test-owner",
            stale_threshold_seconds=3600,
            backend_name="fcntl",
        )

        lock_path.write_text("preexisting", encoding="utf-8")

        def _fail_write(handle, info):  # type: ignore[no-untyped-def]
            del handle, info
            raise OSError(errno.EIO, "simulated write failure")

        with patch.object(FcntlFileLockBackend, "write_info", _fail_write):
            assert manager.acquire() is False

        assert lock_path.exists()


def test_lease_backend_stale_holder_cannot_overwrite_new_owner_metadata() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lease.lock"
        backend = LeaseFileLockBackend()

        stale_handle = backend.acquire(lock_path, stale_threshold_seconds=3600)
        assert stale_handle is not None
        stale_info = _build_lock_info(stale_handle.lock_id, owner="stale-owner")
        backend.write_info(stale_handle, stale_info)

        # Simulate lease takeover: stale lock path is removed and recreated by a new owner.
        assert backend._safe_unlink(lock_path) is True

        active_handle = backend.acquire(lock_path, stale_threshold_seconds=3600)
        assert active_handle is not None
        active_info = _build_lock_info(active_handle.lock_id, owner="active-owner")
        backend.write_info(active_handle, active_info)

        # Late heartbeat/write from stale holder must not clobber active owner metadata.
        with pytest.raises(OSError):
            backend.write_info(stale_handle, replace(stale_info, updated_at=datetime.now(UTC).isoformat()))
        current = backend.read_info(lock_path)
        assert current is not None
        assert current.lock_id == active_handle.lock_id
        assert current.owner == "active-owner"

        backend.release(active_handle)
        backend.release(stale_handle)


def test_lease_stale_reclaim_does_not_unlink_new_owner_sidecar_on_race(
    monkeypatch: pytest.MonkeyPatch,
    live_foreign_pid: int,
) -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        lock_path = Path(tmpdir) / "lease.lock"
        metadata_path = lock_path.with_name(f"{lock_path.name}.info")

        lock_path.write_text("marker\n", encoding="utf-8")
        stale = _build_lock_info(
            "stale-owner-id",
            owner="stale-owner",
            pid=999999999,
            host=socket.gethostname(),
            started_at=datetime(2000, 1, 1, tzinfo=UTC).isoformat(),
            updated_at=datetime(2000, 1, 1, tzinfo=UTC).isoformat(),
            backend="lease",
        )
        metadata_path.write_text(json.dumps(stale.to_dict()) + "\n", encoding="utf-8")

        backend = LeaseFileLockBackend()
        original_unlink_if_inode = backend._safe_unlink_if_inode
        injected = {"done": False}
        new_lock_id = "contender-owner-id"

        def _unlink_with_race(path: Path, expected_inode: tuple[int, int]) -> bool:
            result = original_unlink_if_inode(path, expected_inode)
            if path == lock_path and result and not injected["done"]:
                injected["done"] = True
                lock_path.write_text("marker\n", encoding="utf-8")
                new_info = _build_lock_info(new_lock_id, owner="new-owner", pid=live_foreign_pid, backend="lease")
                metadata_path.write_text(json.dumps(new_info.to_dict()) + "\n", encoding="utf-8")
            return result

        monkeypatch.setattr(backend, "_safe_unlink_if_inode", _unlink_with_race)

        handle = backend.acquire(lock_path, stale_threshold_seconds=1)
        assert handle is None
        current = backend.read_info(lock_path)
        assert current is not None
        assert current.lock_id == new_lock_id
        assert metadata_path.exists()


class TestReadInfoPathUnsearchableParent:
    def test_lock_info_under_unsearchable_dir_returns_none(self, unsearchable_dir):
        from cja_auto_sdr.core.locks.backends import _read_info_path

        assert _read_info_path(unsearchable_dir / "org.lock.info") is None
