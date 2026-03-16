"""Lock manager orchestrating backend selection and lifecycle."""

from __future__ import annotations

import logging
import os
import socket
import threading
import uuid
from contextlib import suppress
from dataclasses import replace
from datetime import UTC, datetime
from pathlib import Path

from cja_auto_sdr.core.exceptions import LockOwnershipLostError
from cja_auto_sdr.core.locks.backends import (
    AcquireResult,
    AcquireStatus,
    FcntlFileLockBackend,
    LeaseFileLockBackend,
    LockBackend,
    LockBackendUnavailableError,
    LockHandle,
    LockInfo,
)
from cja_auto_sdr.core.logging import emit_diagnostic

DEFAULT_LOCK_BACKEND_ENV = "CJA_LOCK_BACKEND"


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def create_lock_backend(
    backend_name: str | None = None,
    *,
    logger: logging.Logger | None = None,
) -> LockBackend:
    """Create lock backend from explicit value or environment override."""
    log = logger or logging.getLogger(__name__)
    requested = (backend_name or os.environ.get(DEFAULT_LOCK_BACKEND_ENV, "auto")).strip().lower()

    if requested == "auto":
        if FcntlFileLockBackend.is_supported():
            return FcntlFileLockBackend()
        emit_diagnostic(
            log,
            "lock_backend_fallback",
            "lifecycle",
            from_backend="fcntl",
            to_backend="lease",
            reason="fcntl_unavailable",
        )
        return LeaseFileLockBackend()

    if requested == "fcntl":
        if FcntlFileLockBackend.is_supported():
            return FcntlFileLockBackend()
        emit_diagnostic(
            log,
            "lock_backend_fallback",
            "lifecycle",
            from_backend="fcntl",
            to_backend="lease",
            reason="fcntl_requested_unavailable",
        )
        return LeaseFileLockBackend()

    if requested == "lease":
        return LeaseFileLockBackend()

    log.warning("Unknown lock backend '%s'; falling back to auto selection", requested)
    return create_lock_backend("auto", logger=log)


class LockManager:
    """Backend-agnostic non-blocking lock manager."""

    def __init__(
        self,
        *,
        lock_path: Path,
        owner: str,
        stale_threshold_seconds: int = 3600,
        backend_name: str | None = None,
        logger: logging.Logger | None = None,
    ):
        self.lock_path = lock_path
        self.owner = owner
        self.stale_threshold_seconds = max(1, stale_threshold_seconds)
        self.logger = logger or logging.getLogger(__name__)
        self.backend = create_lock_backend(backend_name, logger=self.logger)

        self._handle: LockHandle | None = None
        self._lock_info: LockInfo | None = None

        self._heartbeat_stop = threading.Event()
        self._heartbeat_thread: threading.Thread | None = None
        self._state_lock = threading.RLock()
        self._lock_lost = threading.Event()
        self._lock_lost_reason: str | None = None

    @property
    def acquired(self) -> bool:
        with self._state_lock:
            return self._handle is not None

    @property
    def lock_lost(self) -> bool:
        return self._lock_lost.is_set()

    def acquire(self) -> bool:
        """Attempt lock acquisition without blocking."""
        with self._state_lock:
            if self._handle is not None:
                return True

        result = self._acquire_with_result(self.backend, self.lock_path, self.stale_threshold_seconds)
        if result.status == AcquireStatus.BACKEND_UNAVAILABLE and isinstance(self.backend, FcntlFileLockBackend):
            fallback = LeaseFileLockBackend()
            emit_diagnostic(
                self.logger,
                "lock_backend_fallback",
                "lifecycle",
                from_backend="fcntl",
                to_backend="lease",
                reason="acquire_backend_unavailable",
            )
            result = self._acquire_with_result(fallback, self.lock_path, self.stale_threshold_seconds)
            with self._state_lock:
                self.backend = fallback

        if result.status == AcquireStatus.BACKEND_UNAVAILABLE:
            if result.error is not None:
                raise result.error
            raise LockBackendUnavailableError(f"lock backend unavailable for '{self.lock_path}'")

        if result.status == AcquireStatus.METADATA_ERROR:
            if result.error is not None:
                raise result.error
            return False

        handle = result.handle
        if result.status != AcquireStatus.ACQUIRED or handle is None:
            current_owner = None
            with suppress(Exception):  # best-effort metadata read
                info = self.read_info()
                if info is not None:
                    current_owner = {k: info[k] for k in ("pid", "owner", "backend", "started_at") if k in info} or None
            emit_diagnostic(
                self.logger,
                "lock_acquire_failed",
                "lifecycle",
                lock_path=str(self.lock_path),
                backend=self.backend.name,
                reason=result.status.value,
                current_owner=current_owner or "unknown",
            )
            return False

        lock_info = LockInfo(
            lock_id=getattr(handle, "lock_id", str(uuid.uuid4())),
            pid=os.getpid(),
            host=socket.gethostname(),
            owner=self.owner,
            started_at=_utcnow_iso(),
            updated_at=_utcnow_iso(),
            backend=self.backend.name,
            version=1,
        )

        try:
            self.backend.write_info(handle, lock_info)
        except OSError:
            # Metadata persistence is sidecar-based. Release primitive lock and fail,
            # but never mutate lock-path ownership in manager cleanup.
            self._write_failure_tombstone_best_effort(handle, lock_info)
            self.backend.release(handle)
            return False

        with self._state_lock:
            self._handle = handle
            self._lock_info = lock_info
            self._lock_lost.clear()
            self._lock_lost_reason = None
        self._start_heartbeat_if_needed()
        emit_diagnostic(
            self.logger,
            "lock_acquired",
            "lifecycle",
            lock_path=str(self.lock_path),
            lock_id=lock_info.lock_id,
            backend=self.backend.name,
        )
        return True

    def release(self) -> None:
        """Release lock if held."""
        self._stop_heartbeat()
        with self._state_lock:
            handle = self._handle
            lock_info = self._lock_info
            self._handle = None
            self._lock_info = None
        if handle is None:
            return
        self.backend.release(handle)
        emit_diagnostic(
            self.logger,
            "lock_released",
            "lifecycle",
            lock_path=str(self.lock_path),
            lock_id=lock_info.lock_id if lock_info else "unknown",
            backend=self.backend.name,
        )

    def read_info(self) -> dict | None:
        """Read lock metadata for diagnostics."""
        lock_info = self.backend.read_info(self.lock_path)
        if lock_info is None:
            return None
        return lock_info.to_dict()

    def _start_heartbeat_if_needed(self) -> None:
        with self._state_lock:
            if not self.backend.requires_heartbeat or self._handle is None or self._lock_info is None:
                return
            if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
                return

        interval_seconds = min(30.0, max(1.0, self.stale_threshold_seconds / 3))
        self._heartbeat_stop.clear()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop,
            args=(interval_seconds,),
            daemon=True,
            name=f"lock-heartbeat-{self.lock_path.name}",
        )
        self._heartbeat_thread.start()

    def _stop_heartbeat(self) -> None:
        self._heartbeat_stop.set()
        if self._heartbeat_thread is not None and self._heartbeat_thread.is_alive():
            self._heartbeat_thread.join(timeout=1.0)
        self._heartbeat_thread = None

    def _heartbeat_loop(self, interval_seconds: float) -> None:
        while not self._heartbeat_stop.wait(interval_seconds):
            with self._state_lock:
                if self._handle is None or self._lock_info is None:
                    return
                handle = self._handle
                refreshed_info = replace(self._lock_info, updated_at=_utcnow_iso())
                self._lock_info = refreshed_info
            try:
                self.backend.write_info(handle, refreshed_info)
            except OSError as e:
                if self._heartbeat_stop.is_set():
                    return  # Lock was intentionally released; not a real failure
                self._handle_heartbeat_failure(e)
                return

    def _write_failure_tombstone_best_effort(self, handle: LockHandle, lock_info: LockInfo) -> None:
        writer = getattr(self.backend, "write_failure_tombstone", None)
        if writer is None:
            return
        try:
            writer(handle, lock_info)
        except (
            Exception
        ):  # Intentional: Best-effort tombstone write; backend method resolved via getattr with unknown failure modes
            # Best effort only; release path remains authoritative.
            return

    def _handle_heartbeat_failure(self, error: OSError) -> None:
        reason = f"heartbeat metadata write failed: {error}"
        self.logger.error("Lock heartbeat failed for %s; releasing lock (%s)", self.lock_path, error)
        with self._state_lock:
            handle = self._handle
            lock_info = self._lock_info
            if handle is None:
                return
            self._handle = None
            self._lock_info = None
            self._lock_lost_reason = reason
            self._lock_lost.set()
        self._heartbeat_stop.set()
        emit_diagnostic(
            self.logger,
            "lock_heartbeat_lost",
            "lifecycle",
            lock_path=str(self.lock_path),
            lock_id=lock_info.lock_id if lock_info else "unknown",
            error=str(error),
        )
        with suppress(OSError):
            self.backend.release(handle)

    def ensure_held(self) -> None:
        with self._state_lock:
            if self._handle is not None:
                return
            if self._lock_lost.is_set():
                raise LockOwnershipLostError(
                    str(self.lock_path),
                    reason=self._lock_lost_reason,
                )

    @staticmethod
    def _acquire_with_result(
        backend: LockBackend,
        lock_path: Path,
        stale_threshold_seconds: int,
    ) -> AcquireResult:
        if hasattr(backend, "acquire_result"):
            return backend.acquire_result(lock_path, stale_threshold_seconds)
        try:
            handle = backend.acquire(lock_path, stale_threshold_seconds)  # pragma: no cover
        except LockBackendUnavailableError as e:
            return AcquireResult(status=AcquireStatus.BACKEND_UNAVAILABLE, error=e)
        except OSError as e:
            return AcquireResult(status=AcquireStatus.METADATA_ERROR, error=e)
        if handle is None:
            return AcquireResult(status=AcquireStatus.CONTENDED)
        return AcquireResult(status=AcquireStatus.ACQUIRED, handle=handle)
