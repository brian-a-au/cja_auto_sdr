"""Tests for LockManager and create_lock_backend in cja_auto_sdr.core.locks.manager.

Covers backend selection, lock acquisition/release, heartbeat lifecycle,
ensure_held, and _acquire_with_result.
"""

import logging
import os
import sys
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cja_auto_sdr.core.exceptions import LockOwnershipLostError
from cja_auto_sdr.core.locks.backends import (
    AcquireResult,
    AcquireStatus,
    FcntlFileLockBackend,
    LeaseFileLockBackend,
    LockBackendUnavailableError,
    LockInfo,
)
from cja_auto_sdr.core.locks.manager import LockManager, create_lock_backend


def _mock_handle(lock_id="test-lock-id"):
    handle = MagicMock()
    handle.lock_id = lock_id
    return handle


def _mock_lock_info():
    return LockInfo(
        lock_id="test-lock-id",
        pid=os.getpid(),
        host="localhost",
        owner="test-owner",
        started_at="2026-01-01T00:00:00+00:00",
        updated_at="2026-01-01T00:00:00+00:00",
        backend="mock",
        version=1,
    )


# ---------------------------------------------------------------------------
# create_lock_backend
# ---------------------------------------------------------------------------
class TestCreateLockBackend:
    @patch.object(FcntlFileLockBackend, "is_supported", return_value=True)
    def test_auto_with_fcntl_supported(self, mock_supported):
        backend = create_lock_backend("auto")
        assert isinstance(backend, FcntlFileLockBackend)

    @patch.object(FcntlFileLockBackend, "is_supported", return_value=False)
    def test_auto_with_fcntl_unsupported(self, mock_supported):
        backend = create_lock_backend("auto")
        assert isinstance(backend, LeaseFileLockBackend)

    @patch.object(FcntlFileLockBackend, "is_supported", return_value=True)
    def test_fcntl_supported(self, mock_supported):
        backend = create_lock_backend("fcntl")
        assert isinstance(backend, FcntlFileLockBackend)

    @patch.object(FcntlFileLockBackend, "is_supported", return_value=False)
    def test_fcntl_unsupported_falls_back(self, mock_supported):
        backend = create_lock_backend("fcntl")
        assert isinstance(backend, LeaseFileLockBackend)

    def test_lease_explicit(self):
        backend = create_lock_backend("lease")
        assert isinstance(backend, LeaseFileLockBackend)

    @patch.object(FcntlFileLockBackend, "is_supported", return_value=True)
    def test_unknown_name_falls_back_to_auto(self, mock_supported):
        backend = create_lock_backend("bogus_backend")
        assert isinstance(backend, (FcntlFileLockBackend, LeaseFileLockBackend))

    @patch.object(FcntlFileLockBackend, "is_supported", return_value=True)
    @patch.dict(os.environ, {"CJA_LOCK_BACKEND": "lease"})
    def test_env_var_override(self, mock_supported):
        backend = create_lock_backend()
        assert isinstance(backend, LeaseFileLockBackend)

    @patch.object(FcntlFileLockBackend, "is_supported", return_value=True)
    def test_none_defaults_to_auto(self, mock_supported):
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CJA_LOCK_BACKEND", None)
            backend = create_lock_backend(None)
            assert isinstance(backend, (FcntlFileLockBackend, LeaseFileLockBackend))


# ---------------------------------------------------------------------------
# LockManager init
# ---------------------------------------------------------------------------
class TestLockManagerInit:
    @patch("cja_auto_sdr.core.locks.manager.create_lock_backend")
    def test_stale_threshold_min_clamped(self, mock_create, tmp_path):
        mock_create.return_value = MagicMock()
        mgr = LockManager(lock_path=tmp_path / "test.lock", owner="test", stale_threshold_seconds=0)
        assert mgr.stale_threshold_seconds == 1

    @patch("cja_auto_sdr.core.locks.manager.create_lock_backend")
    def test_stale_threshold_negative_clamped(self, mock_create, tmp_path):
        mock_create.return_value = MagicMock()
        mgr = LockManager(lock_path=tmp_path / "test.lock", owner="test", stale_threshold_seconds=-100)
        assert mgr.stale_threshold_seconds == 1

    @patch("cja_auto_sdr.core.locks.manager.create_lock_backend")
    def test_initial_acquired_is_false(self, mock_create, tmp_path):
        mock_create.return_value = MagicMock()
        mgr = LockManager(lock_path=tmp_path / "test.lock", owner="test")
        assert mgr.acquired is False

    @patch("cja_auto_sdr.core.locks.manager.create_lock_backend")
    def test_initial_lock_lost_is_false(self, mock_create, tmp_path):
        mock_create.return_value = MagicMock()
        mgr = LockManager(lock_path=tmp_path / "test.lock", owner="test")
        assert mgr.lock_lost is False


# ---------------------------------------------------------------------------
# LockManager.acquire
# ---------------------------------------------------------------------------
class TestLockManagerAcquire:
    def _make_manager(self, tmp_path, backend=None):
        mock_backend = backend or MagicMock()
        mock_backend.name = "mock"
        mock_backend.requires_heartbeat = False
        with patch("cja_auto_sdr.core.locks.manager.create_lock_backend", return_value=mock_backend):
            return LockManager(lock_path=tmp_path / "test.lock", owner="test-owner", stale_threshold_seconds=3600)

    def test_successful_acquire(self, tmp_path):
        handle = _mock_handle()
        mock_backend = MagicMock()
        mock_backend.name = "mock"
        mock_backend.requires_heartbeat = False
        mgr = self._make_manager(tmp_path, mock_backend)
        with patch.object(
            LockManager,
            "_acquire_with_result",
            return_value=AcquireResult(status=AcquireStatus.ACQUIRED, handle=handle),
        ):
            result = mgr.acquire()
        assert result is True
        assert mgr.acquired is True
        mock_backend.write_info.assert_called_once()

    def test_already_acquired_returns_true(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        mgr._handle = _mock_handle()
        assert mgr.acquire() is True

    def test_contended_returns_false(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        with patch.object(
            LockManager,
            "_acquire_with_result",
            return_value=AcquireResult(status=AcquireStatus.CONTENDED),
        ):
            assert mgr.acquire() is False
            assert mgr.acquired is False

    def test_backend_unavailable_with_fcntl_falls_back(self, tmp_path):
        handle = _mock_handle()
        call_count = {"n": 0}

        def _side_effect(backend, lock_path, stale):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return AcquireResult(status=AcquireStatus.BACKEND_UNAVAILABLE)
            return AcquireResult(status=AcquireStatus.ACQUIRED, handle=handle)

        real_fcntl = FcntlFileLockBackend()
        with patch("cja_auto_sdr.core.locks.manager.create_lock_backend", return_value=real_fcntl):
            mgr = LockManager(lock_path=tmp_path / "test.lock", owner="test-owner")
        with (
            patch.object(LockManager, "_acquire_with_result", side_effect=_side_effect),
            patch.object(LeaseFileLockBackend, "write_info"),
        ):
            result = mgr.acquire()
        assert result is True
        assert isinstance(mgr.backend, LeaseFileLockBackend)

    def test_backend_unavailable_raises_with_error(self, tmp_path):
        error = LockBackendUnavailableError("both failed")
        mock_backend = MagicMock()
        mock_backend.name = "lease"
        mock_backend.requires_heartbeat = False
        mgr = self._make_manager(tmp_path, mock_backend)
        with patch.object(
            LockManager,
            "_acquire_with_result",
            return_value=AcquireResult(status=AcquireStatus.BACKEND_UNAVAILABLE, error=error),
        ):
            with pytest.raises(LockBackendUnavailableError, match="both failed"):
                mgr.acquire()

    def test_backend_unavailable_no_error_raises_default(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.name = "lease"
        mock_backend.requires_heartbeat = False
        mgr = self._make_manager(tmp_path, mock_backend)
        with patch.object(
            LockManager,
            "_acquire_with_result",
            return_value=AcquireResult(status=AcquireStatus.BACKEND_UNAVAILABLE),
        ):
            with pytest.raises(LockBackendUnavailableError, match="lock backend unavailable"):
                mgr.acquire()

    def test_metadata_error_with_error_raises(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        error = OSError("metadata broken")
        with patch.object(
            LockManager,
            "_acquire_with_result",
            return_value=AcquireResult(status=AcquireStatus.METADATA_ERROR, error=error),
        ):
            with pytest.raises(OSError, match="metadata broken"):
                mgr.acquire()

    def test_metadata_error_without_error_returns_false(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        with patch.object(
            LockManager,
            "_acquire_with_result",
            return_value=AcquireResult(status=AcquireStatus.METADATA_ERROR),
        ):
            assert mgr.acquire() is False

    def test_write_info_oserror_returns_false(self, tmp_path):
        handle = _mock_handle()
        mock_backend = MagicMock()
        mock_backend.name = "mock"
        mock_backend.requires_heartbeat = False
        mock_backend.write_info.side_effect = OSError("disk full")
        mgr = self._make_manager(tmp_path, mock_backend)
        with patch.object(
            LockManager,
            "_acquire_with_result",
            return_value=AcquireResult(status=AcquireStatus.ACQUIRED, handle=handle),
        ):
            result = mgr.acquire()
        assert result is False
        assert mgr.acquired is False
        mock_backend.release.assert_called_once_with(handle)

    def test_contended_emits_structured_current_owner(self, tmp_path):
        """lock_acquire_failed diagnostic should include structured current_owner dict."""
        mgr = self._make_manager(tmp_path)
        info_dict = {
            "pid": 12345,
            "owner": "other-org",
            "backend": "lease",
            "started_at": "2026-03-15T10:00:00",
            "host": "host1",
            "updated_at": "2026-03-15T10:01:00",
        }
        with (
            patch.object(
                LockManager,
                "_acquire_with_result",
                return_value=AcquireResult(status=AcquireStatus.CONTENDED),
            ),
            patch.object(mgr, "read_info", return_value=info_dict),
            patch("cja_auto_sdr.core.locks.manager.emit_diagnostic") as mock_diag,
        ):
            result = mgr.acquire()
        assert result is False
        mock_diag.assert_called_once()
        call_kwargs = mock_diag.call_args[1]
        current_owner = call_kwargs["current_owner"]
        assert isinstance(current_owner, dict)
        assert current_owner["pid"] == 12345
        assert current_owner["owner"] == "other-org"
        assert current_owner["backend"] == "lease"
        assert current_owner["started_at"] == "2026-03-15T10:00:00"
        # host and updated_at should NOT be in the structured owner dict
        assert "host" not in current_owner
        assert "updated_at" not in current_owner

    def test_contended_emits_unknown_when_no_info(self, tmp_path):
        """lock_acquire_failed diagnostic should emit 'unknown' when read_info returns None."""
        mgr = self._make_manager(tmp_path)
        with (
            patch.object(
                LockManager,
                "_acquire_with_result",
                return_value=AcquireResult(status=AcquireStatus.CONTENDED),
            ),
            patch.object(mgr, "read_info", return_value=None),
            patch("cja_auto_sdr.core.locks.manager.emit_diagnostic") as mock_diag,
        ):
            result = mgr.acquire()
        assert result is False
        call_kwargs = mock_diag.call_args[1]
        assert call_kwargs["current_owner"] == "unknown"


# ---------------------------------------------------------------------------
# LockManager.release
# ---------------------------------------------------------------------------
class TestLockManagerRelease:
    def _make_manager(self, tmp_path, backend=None):
        mock_backend = backend or MagicMock()
        mock_backend.name = "mock"
        mock_backend.requires_heartbeat = False
        with patch("cja_auto_sdr.core.locks.manager.create_lock_backend", return_value=mock_backend):
            return LockManager(lock_path=tmp_path / "test.lock", owner="test-owner")

    def test_release_clears_handle(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.name = "mock"
        mock_backend.requires_heartbeat = False
        mgr = self._make_manager(tmp_path, mock_backend)
        handle = _mock_handle()
        mgr._handle = handle
        mgr._lock_info = _mock_lock_info()
        mgr.release()
        assert mgr._handle is None
        assert mgr._lock_info is None
        assert mgr.acquired is False
        mock_backend.release.assert_called_once_with(handle)

    def test_release_when_not_acquired_is_noop(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.name = "mock"
        mock_backend.requires_heartbeat = False
        mgr = self._make_manager(tmp_path, mock_backend)
        mgr.release()
        mock_backend.release.assert_not_called()

    def test_release_stops_heartbeat(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.name = "mock"
        mock_backend.requires_heartbeat = False
        mgr = self._make_manager(tmp_path, mock_backend)
        mgr._handle = _mock_handle()
        with patch.object(mgr, "_stop_heartbeat") as mock_stop:
            mgr.release()
        mock_stop.assert_called_once()


# ---------------------------------------------------------------------------
# LockManager.read_info
# ---------------------------------------------------------------------------
class TestLockManagerReadInfo:
    def test_read_info_returns_dict(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.name = "mock"
        mock_backend.requires_heartbeat = False
        info = _mock_lock_info()
        mock_backend.read_info.return_value = info
        with patch("cja_auto_sdr.core.locks.manager.create_lock_backend", return_value=mock_backend):
            mgr = LockManager(lock_path=tmp_path / "test.lock", owner="test")
        result = mgr.read_info()
        assert isinstance(result, dict)
        assert result["lock_id"] == "test-lock-id"

    def test_read_info_returns_none_when_no_info(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.name = "mock"
        mock_backend.requires_heartbeat = False
        mock_backend.read_info.return_value = None
        with patch("cja_auto_sdr.core.locks.manager.create_lock_backend", return_value=mock_backend):
            mgr = LockManager(lock_path=tmp_path / "test.lock", owner="test")
        assert mgr.read_info() is None


# ---------------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------------
class TestLockManagerHeartbeat:
    def _make_manager(self, tmp_path, backend):
        with patch("cja_auto_sdr.core.locks.manager.create_lock_backend", return_value=backend):
            return LockManager(lock_path=tmp_path / "hb.lock", owner="test-owner", stale_threshold_seconds=3600)

    def test_heartbeat_not_started_when_not_required(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.name = "mock"
        mock_backend.requires_heartbeat = False
        mgr = self._make_manager(tmp_path, mock_backend)
        mgr._handle = _mock_handle()
        mgr._lock_info = _mock_lock_info()
        mgr._start_heartbeat_if_needed()
        assert mgr._heartbeat_thread is None

    def test_heartbeat_not_started_when_no_handle(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.name = "mock"
        mock_backend.requires_heartbeat = True
        mgr = self._make_manager(tmp_path, mock_backend)
        mgr._start_heartbeat_if_needed()
        assert mgr._heartbeat_thread is None

    def test_heartbeat_started_when_required(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.name = "mock"
        mock_backend.requires_heartbeat = True
        mgr = self._make_manager(tmp_path, mock_backend)
        mgr._handle = _mock_handle()
        mgr._lock_info = _mock_lock_info()
        mgr._start_heartbeat_if_needed()
        assert mgr._heartbeat_thread is not None
        assert mgr._heartbeat_thread.is_alive()
        mgr._stop_heartbeat()

    def test_stop_heartbeat_clears_thread(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.name = "mock"
        mock_backend.requires_heartbeat = True
        mgr = self._make_manager(tmp_path, mock_backend)
        mgr._handle = _mock_handle()
        mgr._lock_info = _mock_lock_info()
        mgr._start_heartbeat_if_needed()
        mgr._stop_heartbeat()
        assert mgr._heartbeat_thread is None

    def test_handle_heartbeat_failure_sets_lock_lost(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.name = "mock"
        mock_backend.requires_heartbeat = False
        mgr = self._make_manager(tmp_path, mock_backend)
        handle = _mock_handle()
        mgr._handle = handle
        mgr._lock_info = _mock_lock_info()
        mgr._handle_heartbeat_failure(OSError("write failed"))
        assert mgr.lock_lost is True
        assert mgr.acquired is False
        assert "write failed" in (mgr._lock_lost_reason or "")
        mock_backend.release.assert_called_once_with(handle)

    def test_handle_heartbeat_failure_when_no_handle_is_noop(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.name = "mock"
        mock_backend.requires_heartbeat = False
        mgr = self._make_manager(tmp_path, mock_backend)
        mgr._handle_heartbeat_failure(OSError("write failed"))
        mock_backend.release.assert_not_called()

    def test_write_failure_tombstone_calls_backend(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.name = "mock"
        mock_backend.requires_heartbeat = False
        mgr = self._make_manager(tmp_path, mock_backend)
        handle = _mock_handle()
        info = _mock_lock_info()
        mgr._write_failure_tombstone_best_effort(handle, info)
        mock_backend.write_failure_tombstone.assert_called_once_with(handle, info)

    def test_write_failure_tombstone_skips_when_no_writer(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.name = "mock"
        mock_backend.requires_heartbeat = False
        del mock_backend.write_failure_tombstone
        mgr = self._make_manager(tmp_path, mock_backend)
        mgr._write_failure_tombstone_best_effort(_mock_handle(), _mock_lock_info())

    def test_write_failure_tombstone_swallows_exception(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.name = "mock"
        mock_backend.requires_heartbeat = False
        mock_backend.write_failure_tombstone.side_effect = RuntimeError("boom")
        mgr = self._make_manager(tmp_path, mock_backend)
        mgr._write_failure_tombstone_best_effort(_mock_handle(), _mock_lock_info())


# ---------------------------------------------------------------------------
# ensure_held
# ---------------------------------------------------------------------------
class TestEnsureHeld:
    def _make_manager(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.name = "mock"
        mock_backend.requires_heartbeat = False
        with patch("cja_auto_sdr.core.locks.manager.create_lock_backend", return_value=mock_backend):
            return LockManager(lock_path=tmp_path / "test.lock", owner="test-owner")

    def test_returns_none_when_handle_exists(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        mgr._handle = _mock_handle()
        assert mgr.ensure_held() is None

    def test_raises_when_lock_lost(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        mgr._lock_lost.set()
        mgr._lock_lost_reason = "heartbeat failure"
        with pytest.raises(LockOwnershipLostError) as exc_info:
            mgr.ensure_held()
        assert "test.lock" in str(exc_info.value)
        assert exc_info.value.reason == "heartbeat failure"

    def test_raises_with_none_reason(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        mgr._lock_lost.set()
        with pytest.raises(LockOwnershipLostError) as exc_info:
            mgr.ensure_held()
        assert exc_info.value.reason is None

    def test_no_raise_when_not_acquired_and_not_lost(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        assert mgr.ensure_held() is None


# ---------------------------------------------------------------------------
# _acquire_with_result
# ---------------------------------------------------------------------------
class TestAcquireWithResult:
    def test_backend_with_acquire_result_method(self):
        mock_backend = MagicMock()
        expected = AcquireResult(status=AcquireStatus.ACQUIRED, handle=_mock_handle())
        mock_backend.acquire_result.return_value = expected
        result = LockManager._acquire_with_result(mock_backend, Path("/tmp/test.lock"), 3600)
        assert result is expected

    def test_backend_without_acquire_result_acquired(self):
        mock_backend = MagicMock(spec=[])
        handle = _mock_handle()
        mock_backend.acquire = MagicMock(return_value=handle)
        result = LockManager._acquire_with_result(mock_backend, Path("/tmp/test.lock"), 3600)
        assert result.status == AcquireStatus.ACQUIRED
        assert result.handle is handle

    def test_backend_without_acquire_result_returns_none(self):
        mock_backend = MagicMock(spec=[])
        mock_backend.acquire = MagicMock(return_value=None)
        result = LockManager._acquire_with_result(mock_backend, Path("/tmp/test.lock"), 3600)
        assert result.status == AcquireStatus.CONTENDED

    def test_backend_lock_unavailable_error(self):
        mock_backend = MagicMock(spec=[])
        error = LockBackendUnavailableError("not available")
        mock_backend.acquire = MagicMock(side_effect=error)
        result = LockManager._acquire_with_result(mock_backend, Path("/tmp/test.lock"), 3600)
        assert result.status == AcquireStatus.BACKEND_UNAVAILABLE
        assert result.error is error

    def test_backend_oserror(self):
        mock_backend = MagicMock(spec=[])
        error = OSError("disk failure")
        mock_backend.acquire = MagicMock(side_effect=error)
        result = LockManager._acquire_with_result(mock_backend, Path("/tmp/test.lock"), 3600)
        assert result.status == AcquireStatus.METADATA_ERROR
        assert result.error is error


# ---------------------------------------------------------------------------
# Properties
# ---------------------------------------------------------------------------
class TestProperties:
    def _make_manager(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.name = "mock"
        mock_backend.requires_heartbeat = False
        with patch("cja_auto_sdr.core.locks.manager.create_lock_backend", return_value=mock_backend):
            return LockManager(lock_path=tmp_path / "test.lock", owner="test-owner")

    def test_acquired_true_when_handle_set(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        mgr._handle = _mock_handle()
        assert mgr.acquired is True

    def test_acquired_false_when_handle_none(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        assert mgr.acquired is False

    def test_lock_lost_true_when_event_set(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        mgr._lock_lost.set()
        assert mgr.lock_lost is True

    def test_lock_lost_false_when_event_clear(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        assert mgr.lock_lost is False


# ---------------------------------------------------------------------------
# Diagnostic event coverage
# ---------------------------------------------------------------------------
class TestCreateLockBackendDiagnostics:
    @patch.object(FcntlFileLockBackend, "is_supported", return_value=False)
    def test_auto_fallback_emits_diagnostic(self, _mock_supported):
        with patch("cja_auto_sdr.core.locks.manager.emit_diagnostic") as mock_diag:
            backend = create_lock_backend("auto")

        assert isinstance(backend, LeaseFileLockBackend)
        mock_diag.assert_called_once()
        args, kwargs = mock_diag.call_args
        assert args[1] == "lock_backend_fallback"
        assert args[2] == "lifecycle"
        assert kwargs["level"] == logging.WARNING
        assert kwargs["from_backend"] == "fcntl"
        assert kwargs["to_backend"] == "lease"
        assert kwargs["reason"] == "fcntl_unavailable"

    @patch.object(FcntlFileLockBackend, "is_supported", return_value=False)
    def test_requested_fcntl_fallback_emits_diagnostic(self, _mock_supported):
        with patch("cja_auto_sdr.core.locks.manager.emit_diagnostic") as mock_diag:
            backend = create_lock_backend("fcntl")

        assert isinstance(backend, LeaseFileLockBackend)
        mock_diag.assert_called_once()
        kwargs = mock_diag.call_args[1]
        assert kwargs["level"] == logging.WARNING
        assert kwargs["reason"] == "fcntl_requested_unavailable"

    @patch.object(FcntlFileLockBackend, "is_supported", return_value=True)
    def test_supported_auto_backend_does_not_emit_diagnostic(self, _mock_supported):
        with patch("cja_auto_sdr.core.locks.manager.emit_diagnostic") as mock_diag:
            backend = create_lock_backend("auto")

        assert isinstance(backend, FcntlFileLockBackend)
        mock_diag.assert_not_called()

    def test_explicit_lease_backend_does_not_emit_diagnostic(self):
        with patch("cja_auto_sdr.core.locks.manager.emit_diagnostic") as mock_diag:
            backend = create_lock_backend("lease")

        assert isinstance(backend, LeaseFileLockBackend)
        mock_diag.assert_not_called()


class TestLockManagerDiagnostics:
    def _make_manager(self, tmp_path, backend=None):
        mock_backend = backend if backend is not None else MagicMock()
        if backend is None:
            mock_backend.name = "mock"
            mock_backend.requires_heartbeat = False
        with patch("cja_auto_sdr.core.locks.manager.create_lock_backend", return_value=mock_backend):
            return LockManager(lock_path=tmp_path / "test.lock", owner="test-owner", stale_threshold_seconds=3600)

    def test_successful_acquire_emits_lock_acquired_diagnostic(self, tmp_path):
        handle = _mock_handle("acq-id")
        mock_backend = MagicMock()
        mock_backend.name = "lease"
        mock_backend.requires_heartbeat = False
        mgr = self._make_manager(tmp_path, mock_backend)

        with (
            patch.object(
                LockManager,
                "_acquire_with_result",
                return_value=AcquireResult(status=AcquireStatus.ACQUIRED, handle=handle),
            ),
            patch("cja_auto_sdr.core.locks.manager.emit_diagnostic") as mock_diag,
        ):
            assert mgr.acquire() is True

        acquired_calls = [call for call in mock_diag.call_args_list if call[0][1] == "lock_acquired"]
        assert len(acquired_calls) == 1
        call_kwargs = acquired_calls[0][1]
        assert call_kwargs["lock_path"] == str(tmp_path / "test.lock")
        assert call_kwargs["backend"] == "lease"
        assert "lock_id" in call_kwargs

    def test_contention_does_not_emit_lock_acquired_diagnostic(self, tmp_path):
        mgr = self._make_manager(tmp_path)

        with (
            patch.object(
                LockManager,
                "_acquire_with_result",
                return_value=AcquireResult(status=AcquireStatus.CONTENDED),
            ),
            patch.object(mgr, "read_info", return_value=None),
            patch("cja_auto_sdr.core.locks.manager.emit_diagnostic") as mock_diag,
        ):
            mgr.acquire()

        acquired_calls = [call for call in mock_diag.call_args_list if call[0][1] == "lock_acquired"]
        assert acquired_calls == []

    def test_release_emits_lock_released_diagnostic(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.name = "fcntl"
        mock_backend.requires_heartbeat = False
        mgr = self._make_manager(tmp_path, mock_backend)
        mgr._handle = _mock_handle("rel-id")
        mgr._lock_info = _mock_lock_info()

        with patch("cja_auto_sdr.core.locks.manager.emit_diagnostic") as mock_diag:
            mgr.release()

        released_calls = [call for call in mock_diag.call_args_list if call[0][1] == "lock_released"]
        assert len(released_calls) == 1
        call_kwargs = released_calls[0][1]
        assert call_kwargs["lock_path"] == str(tmp_path / "test.lock")
        assert call_kwargs["backend"] == "fcntl"

    def test_release_without_lock_does_not_emit_lock_released_diagnostic(self, tmp_path):
        mgr = self._make_manager(tmp_path)

        with patch("cja_auto_sdr.core.locks.manager.emit_diagnostic") as mock_diag:
            mgr.release()

        released_calls = [call for call in mock_diag.call_args_list if call[0][1] == "lock_released"]
        assert released_calls == []

    def test_handle_heartbeat_failure_emits_lock_heartbeat_lost_diagnostic(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.name = "lease"
        mock_backend.requires_heartbeat = False
        mgr = self._make_manager(tmp_path, mock_backend)
        mgr._handle = _mock_handle("hb-id")
        info = _mock_lock_info()
        mgr._lock_info = info

        with patch("cja_auto_sdr.core.locks.manager.emit_diagnostic") as mock_diag:
            mgr._handle_heartbeat_failure(OSError("disk full"))

        hb_calls = [call for call in mock_diag.call_args_list if call[0][1] == "lock_heartbeat_lost"]
        assert len(hb_calls) == 1
        call_kwargs = hb_calls[0][1]
        assert call_kwargs["lock_path"] == str(tmp_path / "test.lock")
        assert call_kwargs["lock_id"] == info.lock_id
        assert "disk full" in call_kwargs["error"]

    def test_acquire_time_fallback_emits_diagnostic(self, tmp_path):
        handle = _mock_handle("fallback-id")
        call_count = {"count": 0}

        def _side_effect(_backend, _lock_path, _stale):
            call_count["count"] += 1
            if call_count["count"] == 1:
                return AcquireResult(status=AcquireStatus.BACKEND_UNAVAILABLE)
            return AcquireResult(status=AcquireStatus.ACQUIRED, handle=handle)

        real_fcntl = FcntlFileLockBackend()
        with patch("cja_auto_sdr.core.locks.manager.create_lock_backend", return_value=real_fcntl):
            mgr = LockManager(lock_path=tmp_path / "test.lock", owner="test-owner")

        with (
            patch.object(LockManager, "_acquire_with_result", side_effect=_side_effect),
            patch.object(LeaseFileLockBackend, "write_info"),
            patch("cja_auto_sdr.core.locks.manager.emit_diagnostic") as mock_diag,
        ):
            assert mgr.acquire() is True

        fallback_calls = [call for call in mock_diag.call_args_list if call[0][1] == "lock_backend_fallback"]
        assert len(fallback_calls) == 1
        kwargs = fallback_calls[0][1]
        assert kwargs["level"] == logging.WARNING
        assert kwargs["from_backend"] == "fcntl"
        assert kwargs["to_backend"] == "lease"
        assert kwargs["reason"] == "acquire_backend_unavailable"

    def test_acquire_then_release_emits_lifecycle_sequence(self, tmp_path):
        handle = _mock_handle("lifecycle-id")
        mock_backend = MagicMock()
        mock_backend.name = "lease"
        mock_backend.requires_heartbeat = False
        mgr = self._make_manager(tmp_path, mock_backend)

        with (
            patch.object(
                LockManager,
                "_acquire_with_result",
                return_value=AcquireResult(status=AcquireStatus.ACQUIRED, handle=handle),
            ),
            patch("cja_auto_sdr.core.locks.manager.emit_diagnostic") as mock_diag,
        ):
            mgr.acquire()
            mgr.release()

        event_names = [call[0][1] for call in mock_diag.call_args_list]
        assert "lock_acquired" in event_names
        assert "lock_released" in event_names
        assert event_names.index("lock_acquired") < event_names.index("lock_released")

    def test_heartbeat_loop_emits_loss_diagnostic_on_write_failure(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.name = "lease"
        mock_backend.requires_heartbeat = True
        mock_backend.write_info.side_effect = OSError("NFS stale")
        mgr = self._make_manager(tmp_path, mock_backend)
        mgr._handle = _mock_handle("hb-loop-id")
        mgr._lock_info = _mock_lock_info()

        with patch("cja_auto_sdr.core.locks.manager.emit_diagnostic") as mock_diag:
            mgr._heartbeat_loop(0.01)

        hb_calls = [call for call in mock_diag.call_args_list if call[0][1] == "lock_heartbeat_lost"]
        assert len(hb_calls) == 1
        assert mgr.lock_lost is True

    def test_heartbeat_loop_stops_cleanly_after_intentional_release(self, tmp_path):
        mock_backend = MagicMock()
        mock_backend.name = "lease"
        mock_backend.requires_heartbeat = True
        mock_backend.write_info.side_effect = OSError("write after release")
        mgr = self._make_manager(tmp_path, mock_backend)
        mgr._handle = _mock_handle()
        mgr._lock_info = _mock_lock_info()
        mgr._heartbeat_stop.set()

        with patch("cja_auto_sdr.core.locks.manager.emit_diagnostic") as mock_diag:
            mgr._heartbeat_loop(0.01)

        hb_calls = [call for call in mock_diag.call_args_list if call[0][1] == "lock_heartbeat_lost"]
        assert hb_calls == []
        assert mgr.lock_lost is False

    def test_ensure_held_raises_lock_ownership_lost_after_heartbeat_failure(self, tmp_path):
        mgr = self._make_manager(tmp_path)
        mgr._handle = _mock_handle()
        mgr._lock_info = _mock_lock_info()

        with patch("cja_auto_sdr.core.locks.manager.emit_diagnostic"):
            mgr._handle_heartbeat_failure(OSError("disk error"))

        with pytest.raises(LockOwnershipLostError) as exc_info:
            mgr.ensure_held()

        assert "heartbeat metadata write failed" in (exc_info.value.reason or "")

    def test_lock_acquire_failed_diagnostic_uses_status_value_as_reason(self, tmp_path):
        mgr = self._make_manager(tmp_path)

        with (
            patch.object(
                LockManager,
                "_acquire_with_result",
                return_value=AcquireResult(status=AcquireStatus.CONTENDED),
            ),
            patch.object(mgr, "read_info", return_value=None),
            patch("cja_auto_sdr.core.locks.manager.emit_diagnostic") as mock_diag,
        ):
            mgr.acquire()

        failed_calls = [call for call in mock_diag.call_args_list if call[0][1] == "lock_acquire_failed"]
        assert len(failed_calls) == 1
        assert failed_calls[0][1]["reason"] == "contended"


# ---------------------------------------------------------------------------
# Coverage gap tests (moved from test_small_module_coverage.py)
# ---------------------------------------------------------------------------


class TestLockManagerHeartbeatEdgeCases:
    """Cover lines 180, 202, 210."""

    def test_heartbeat_thread_already_alive(self, tmp_path):
        """Line 180: _start_heartbeat_if_needed when thread is already alive."""
        lock_path = tmp_path / "test.lock"
        manager = LockManager(
            lock_path=lock_path,
            owner="test",
            stale_threshold_seconds=30,
            backend_name="lease",
        )
        manager._heartbeat_thread = threading.Thread(target=lambda: time.sleep(10), daemon=True)
        manager._heartbeat_thread.start()

        mock_handle = MagicMock()
        mock_info = MagicMock()
        manager._handle = mock_handle
        manager._lock_info = mock_info

        manager._start_heartbeat_if_needed()

        manager._heartbeat_stop.set()
        manager._heartbeat_thread.join(timeout=1)

    def test_heartbeat_loop_handle_none(self, tmp_path):
        """Line 202: _heartbeat_loop returns when handle becomes None."""
        lock_path = tmp_path / "test.lock"
        manager = LockManager(
            lock_path=lock_path,
            owner="test",
            stale_threshold_seconds=3,
            backend_name="lease",
        )
        manager._handle = None
        manager._lock_info = None
        manager._heartbeat_stop.clear()

        done = threading.Event()

        def run_loop():
            manager._heartbeat_loop(0.01)
            done.set()

        t = threading.Thread(target=run_loop, daemon=True)
        t.start()
        assert done.wait(timeout=2), "Heartbeat loop did not exit"

    def test_heartbeat_loop_oserror_after_stop(self, tmp_path):
        """Line 210: OSError during heartbeat but _heartbeat_stop is already set."""
        lock_path = tmp_path / "test.lock"
        manager = LockManager(
            lock_path=lock_path,
            owner="test",
            stale_threshold_seconds=3,
            backend_name="lease",
        )

        from cja_auto_sdr.core.locks.backends import LockInfo

        mock_handle = MagicMock()
        mock_info = LockInfo(
            lock_id="test",
            pid=os.getpid(),
            host="localhost",
            owner="test",
            started_at="2026-01-01T00:00:00",
            updated_at="2026-01-01T00:00:00",
            backend="lease",
            version=1,
        )
        manager._handle = mock_handle
        manager._lock_info = mock_info

        manager.backend.write_info = MagicMock(side_effect=OSError("disk error"))

        done = threading.Event()

        def run_loop():
            manager._heartbeat_stop.clear()

            call_count = {"n": 0}

            def mock_wait(timeout):
                call_count["n"] += 1
                if call_count["n"] == 1:
                    time.sleep(0.01)
                    return False
                return True

            manager._heartbeat_stop.wait = mock_wait
            manager._heartbeat_stop.set()

            manager._heartbeat_loop(0.01)
            done.set()

        t = threading.Thread(target=run_loop, daemon=True)
        t.start()
        assert done.wait(timeout=5), "Heartbeat loop did not exit"
