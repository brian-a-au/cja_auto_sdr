"""Lock backend implementations.

Design principles:
- Ownership is defined by backend lock state (OS lock or lease ownership).
- Metadata is informational and must not be treated as lock truth.
- Metadata writes are best-effort observability and should never make
  a held lock appear free.
"""

from __future__ import annotations

import contextlib
import errno
import json
import logging
import math
import os
import socket
import time
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any, Literal, Protocol

from cja_auto_sdr.core.error_policies import RECOVERABLE_LOCK_METADATA_PARSE_EXCEPTIONS

_logger = logging.getLogger(__name__)

try:
    import fcntl
except ImportError:  # pragma: no cover - exercised on non-POSIX only
    fcntl = None

_FLOCK_UNSUPPORTED_ERRNOS = {
    err_no
    for err_no in (
        getattr(errno, "ENOTSUP", None),
        getattr(errno, "EOPNOTSUPP", None),
        getattr(errno, "ENOSYS", None),
    )
    if err_no is not None
}

_MISSING_METADATA_RECLAIM_MAX_AGE_SECONDS = 5.0


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _write_all(fd: int, payload: bytes) -> None:
    """Write complete payload to fd, handling short writes."""
    total_written = 0
    while total_written < len(payload):
        written = os.write(fd, payload[total_written:])
        if written <= 0:
            raise OSError("short write while persisting lock metadata")
        total_written += written


def _metadata_path(lock_path: Path) -> Path:
    return lock_path.with_name(f"{lock_path.name}.info")


def _write_info_path(path: Path, info: LockInfo) -> None:
    """Atomically persist metadata to a sidecar file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    fd = os.open(str(tmp_path), os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
    try:
        payload = (json.dumps(info.to_dict(), sort_keys=True) + "\n").encode("utf-8")
        _write_all(fd, payload)
        os.fsync(fd)
    except OSError, TypeError, ValueError:
        with contextlib.suppress(OSError):
            os.close(fd)
        with contextlib.suppress(OSError):
            tmp_path.unlink()
        raise
    else:
        with contextlib.suppress(OSError):
            os.close(fd)
        try:
            os.replace(tmp_path, path)
        except OSError:
            with contextlib.suppress(OSError):
                tmp_path.unlink()
            raise


def _read_info_path(path: Path) -> LockInfo | None:
    if not path.exists():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError, json.JSONDecodeError:
        return None
    if not isinstance(data, dict):
        return None
    return LockInfo.from_dict(data)


def _path_looks_like_json(path: Path) -> bool:
    """Best-effort hint for legacy metadata files."""
    try:
        with open(path, "rb") as f:
            chunk = f.read(64).lstrip()
    except OSError:
        return False
    if not chunk:
        return False
    return chunk[:1] in (b"{", b"[")


def _is_path_stale_by_mtime(path: Path, stale_threshold_seconds: int) -> bool:
    try:
        age_seconds = time.time() - path.stat().st_mtime
    except OSError:
        return False
    return age_seconds > max(1, stale_threshold_seconds)


def _is_missing_metadata_stale(lock_path: Path, stale_threshold_seconds: int) -> bool:
    """Treat metadata-missing states as stale only after a bounded grace window."""
    try:
        age_seconds = time.time() - lock_path.stat().st_mtime
    except OSError:
        return False
    reclaim_after_seconds = min(
        float(max(1, stale_threshold_seconds)),
        _MISSING_METADATA_RECLAIM_MAX_AGE_SECONDS,
    )
    return age_seconds >= reclaim_after_seconds


def _write_info_fd(fd: int, info: LockInfo) -> None:
    payload = (json.dumps(info.to_dict(), sort_keys=True) + "\n").encode("utf-8")
    os.lseek(fd, 0, os.SEEK_SET)
    os.ftruncate(fd, 0)
    _write_all(fd, payload)
    os.fsync(fd)


class AcquireStatus(StrEnum):
    """Explicit lock acquisition outcomes used by backend internals."""

    ACQUIRED = "acquired"
    CONTENDED = "contended"
    BACKEND_UNAVAILABLE = "backend_unavailable"
    METADATA_ERROR = "metadata_error"


@dataclass
class AcquireResult:
    status: AcquireStatus
    handle: LockHandle | None = None
    error: OSError | None = None


@dataclass
class _ReadInfoOutcome:
    info: LockInfo | None
    state: Literal["valid", "missing", "unreadable"]
    source_path: Path | None = None


class LockBackendUnavailableError(OSError):
    """Raised when a backend exists but is unusable for the target lock path."""


@dataclass
class LockInfo:
    """Serializable lock metadata for diagnostics."""

    lock_id: str
    pid: int
    host: str
    owner: str
    started_at: str
    updated_at: str
    backend: str
    version: int = 1

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def _parse_best_effort(
        cls,
        parser: Callable[[dict[str, Any]], LockInfo | None],
        data: dict[str, Any],
        *,
        parser_name: str,
    ) -> LockInfo | None:
        try:
            return parser(data)
        except RECOVERABLE_LOCK_METADATA_PARSE_EXCEPTIONS as e:
            _logger.debug("%s lock info parse failed: %s", parser_name, e)
            return None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LockInfo | None:
        modern = cls._parse_best_effort(cls._from_modern_dict, data, parser_name="Modern")
        if modern is not None:
            return modern
        return cls._parse_best_effort(cls._from_legacy_dict, data, parser_name="Legacy")

    @classmethod
    def _from_modern_dict(cls, data: dict[str, Any]) -> LockInfo | None:
        try:
            pid = cls._coerce_pid(data["pid"])
            if pid is None:
                return None
            return cls(
                lock_id=str(data["lock_id"]),
                pid=pid,
                host=str(data["host"]),
                owner=str(data.get("owner", "")),
                started_at=str(data["started_at"]),
                updated_at=str(data.get("updated_at", data["started_at"])),
                backend=str(data.get("backend", "")),
                version=int(data.get("version", 1)),
            )
        except KeyError, TypeError, ValueError, OverflowError:
            return None

    @classmethod
    def _from_legacy_dict(cls, data: dict[str, Any]) -> LockInfo | None:
        # Legacy format: {"pid": int, "timestamp": float, "started_at": str}
        # Keep compatibility for stale-lock recovery after upgrades.
        if "pid" not in data:
            return None

        pid = cls._coerce_pid(data["pid"])
        if pid is None:
            return None

        started_at = cls._coerce_legacy_time(data.get("started_at"), data.get("timestamp"))
        updated_at = cls._coerce_legacy_time(data.get("updated_at"), data.get("timestamp")) or started_at
        host = str(data.get("host") or socket.gethostname())
        backend = str(data.get("backend") or "legacy")
        lock_id = str(data.get("lock_id") or f"legacy-{pid}-{uuid.uuid4().hex}")
        version = cls._coerce_legacy_int(data.get("version"), default=0)

        return cls(
            lock_id=lock_id,
            pid=pid,
            host=host,
            owner=str(data.get("owner", "")),
            started_at=started_at,
            updated_at=updated_at,
            backend=backend,
            version=version,
        )

    @staticmethod
    def _coerce_legacy_time(primary: Any, fallback_epoch: Any) -> str:
        if isinstance(primary, str) and primary:
            return primary
        for candidate in (primary, fallback_epoch):
            epoch = LockInfo._coerce_legacy_epoch(candidate)
            if epoch is None:
                continue
            try:
                return datetime.fromtimestamp(epoch, UTC).isoformat()
            except OverflowError, OSError, ValueError:
                continue
        return _utcnow_iso()

    @staticmethod
    def _coerce_legacy_epoch(value: Any) -> float | None:
        if isinstance(value, bool):
            return None
        if not isinstance(value, (int, float)):
            return None
        try:
            epoch = float(value)
        except TypeError, ValueError, OverflowError:  # pragma: no cover - value is already int|float
            return None
        if not math.isfinite(epoch):
            return None
        return epoch

    @staticmethod
    def _coerce_legacy_int(value: Any, *, default: int) -> int:
        try:
            if value in (None, ""):
                return default
            return int(value)
        except TypeError, ValueError, OverflowError:
            return default

    @staticmethod
    def _coerce_pid(value: Any) -> int | None:
        if isinstance(value, bool):
            return None
        try:
            return int(value)
        except TypeError, ValueError, OverflowError:
            return None


def _parse_iso(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _is_process_running(pid: int) -> bool:
    # Metadata can be malformed; never probe process groups/special values.
    if isinstance(pid, bool):
        return False
    try:
        normalized_pid = int(pid)
    except TypeError, ValueError, OverflowError:
        return False
    if normalized_pid <= 0:
        return False

    try:
        os.kill(normalized_pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OverflowError:
        return False
    except OSError as e:
        return e.errno == errno.EPERM


def _is_fcntl_lock_active(lock_path: Path) -> bool | None:
    """Return True if a flock holder is active, False if not, None if unknown."""
    if fcntl is None:
        return None
    try:
        probe_fd = os.open(str(lock_path), os.O_RDWR)
    except FileNotFoundError:
        return False
    except OSError:
        return None

    try:
        assert fcntl is not None  # For type checkers.
        fcntl.flock(probe_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        return True
    except OSError as e:
        if e.errno in (errno.EAGAIN, errno.EWOULDBLOCK):  # pragma: no cover - Python maps EAGAIN to BlockingIOError
            return True
        return None
    else:
        with contextlib.suppress(OSError):
            assert fcntl is not None
            fcntl.flock(probe_fd, fcntl.LOCK_UN)
        return False
    finally:
        with contextlib.suppress(OSError):
            os.close(probe_fd)


def _is_lock_info_stale(info: LockInfo, stale_threshold_seconds: int, *, lock_path: Path | None = None) -> bool:
    if info.backend == "fcntl":
        if lock_path is None:
            # Without lock path we cannot probe flock state. Fall back to pid-liveness
            # only for same-host metadata; otherwise be conservative.
            if info.host == socket.gethostname():
                return not _is_process_running(info.pid)
            return False
        lock_active = _is_fcntl_lock_active(lock_path)
        if lock_active is None:
            # If we cannot determine lock state safely, do not force takeover.
            return False
        return not lock_active

    if info.host == socket.gethostname():
        # Never expire a same-host non-fcntl lock while its PID is still alive.
        return not _is_process_running(info.pid)

    reference = _parse_iso(info.updated_at) or _parse_iso(info.started_at)
    if reference is None:
        return True

    now = datetime.now(UTC)
    if reference.tzinfo is None:
        reference = reference.replace(tzinfo=UTC)

    return (now - reference).total_seconds() > max(1, stale_threshold_seconds)


class LockHandle(Protocol):
    """Opaque backend-specific lock handle."""

    lock_path: Path
    lock_id: str


class LockBackend(Protocol):
    """Backend abstraction for lock acquisition and metadata operations."""

    name: str
    requires_heartbeat: bool

    def acquire_result(self, lock_path: Path, stale_threshold_seconds: int) -> AcquireResult:
        """Try acquiring lock non-blocking and return explicit outcome."""

    def acquire(self, lock_path: Path, stale_threshold_seconds: int) -> LockHandle | None:
        """Try acquiring lock non-blocking. Returns handle if acquired."""

    def release(self, handle: LockHandle) -> None:
        """Release lock held by handle."""

    def write_info(self, handle: LockHandle, info: LockInfo) -> None:
        """Persist metadata for the currently held lock."""

    def read_info(self, lock_path: Path) -> LockInfo | None:
        """Read metadata for diagnostics, if available."""


@dataclass
class _FcntlLockHandle:
    lock_path: Path
    fd: int
    lock_id: str
    closed: bool = False


class FcntlFileLockBackend:
    """POSIX advisory locking backend backed by `fcntl.flock`."""

    name = "fcntl"
    requires_heartbeat = False
    acquire_attempts = 3
    metadata_read_retry_attempts = 3
    metadata_read_retry_sleep_seconds = 0.02

    @staticmethod
    def is_supported() -> bool:
        return fcntl is not None

    def acquire(self, lock_path: Path, stale_threshold_seconds: int) -> _FcntlLockHandle | None:
        result = self.acquire_result(lock_path, stale_threshold_seconds)
        if result.status == AcquireStatus.ACQUIRED and result.handle is not None:
            return result.handle
        if result.status == AcquireStatus.BACKEND_UNAVAILABLE and result.error is not None:
            raise result.error
        if result.error is not None:
            raise result.error
        return None

    def acquire_result(self, lock_path: Path, stale_threshold_seconds: int) -> AcquireResult:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        for _ in range(self.acquire_attempts):
            fd, created_exclusively = self._open_lock_file(lock_path)
            if fd is None:
                return AcquireResult(status=AcquireStatus.CONTENDED)

            try:
                assert fcntl is not None  # For type checkers.
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                os.close(fd)
                return AcquireResult(status=AcquireStatus.CONTENDED)
            except OSError as e:
                os.close(fd)
                if e.errno in (
                    errno.EAGAIN,
                    errno.EWOULDBLOCK,
                ):  # pragma: no cover - Python maps EAGAIN to BlockingIOError
                    return AcquireResult(status=AcquireStatus.CONTENDED)
                if e.errno in _FLOCK_UNSUPPORTED_ERRNOS:
                    if created_exclusively:
                        with contextlib.suppress(OSError):
                            lock_path.unlink()
                        # Do not unlink sidecar metadata here: a contender may
                        # acquire/recreate immediately after path unlink.
                    return AcquireResult(
                        status=AcquireStatus.BACKEND_UNAVAILABLE,
                        error=LockBackendUnavailableError(f"flock is unsupported for lock path '{lock_path}'"),
                    )
                return AcquireResult(status=AcquireStatus.METADATA_ERROR, error=e)

            # If lock path no longer points to this inode, reacquire from scratch.
            if not self._fd_matches_path(fd, lock_path):
                self._unlock_close_fd(fd)
                continue

            if not created_exclusively:
                info_outcome = self._read_info_with_retries(lock_path)
                if isinstance(info_outcome, tuple):  # Backward-compat for monkeypatched tests.
                    legacy_info, lock_file_exists = info_outcome
                    if legacy_info is not None:
                        info_outcome = _ReadInfoOutcome(info=legacy_info, state="valid", source_path=lock_path)
                    elif lock_file_exists:
                        info_outcome = _ReadInfoOutcome(info=None, state="unreadable", source_path=lock_path)
                    else:
                        info_outcome = _ReadInfoOutcome(info=None, state="missing", source_path=lock_path)
                if info_outcome.info is not None:
                    # Mixed-backend safeguard: honor active non-fcntl owner metadata.
                    if info_outcome.info.backend != self.name and not _is_lock_info_stale(
                        info_outcome.info,
                        stale_threshold_seconds,
                        lock_path=lock_path,
                    ):
                        self._unlock_close_fd(fd)
                        return AcquireResult(status=AcquireStatus.CONTENDED)
                elif info_outcome.state == "missing":
                    if info_outcome.source_path is not None or not lock_path.exists():
                        # Lock path disappeared during validation; retry acquisition.
                        self._unlock_close_fd(fd)
                        continue
                    if not _is_missing_metadata_stale(lock_path, stale_threshold_seconds):
                        # Fresh missing metadata is typically a bootstrap race; do not steal.
                        self._unlock_close_fd(fd)
                        return AcquireResult(status=AcquireStatus.CONTENDED)
                    # Stale missing metadata can be reclaimed by this fcntl holder.
                elif info_outcome.state == "unreadable":
                    stale_ref = info_outcome.source_path or _metadata_path(lock_path)
                    if not _is_path_stale_by_mtime(stale_ref, stale_threshold_seconds):
                        # Conservatively treat fresh unreadable metadata as active contention.
                        self._unlock_close_fd(fd)
                        return AcquireResult(status=AcquireStatus.CONTENDED)
                    # Stale unreadable metadata is reclaimed by current holder's sidecar write.

            # Re-check path identity after metadata read to catch replacement races.
            if not self._fd_matches_path(fd, lock_path):
                self._unlock_close_fd(fd)
                continue

            return AcquireResult(
                status=AcquireStatus.ACQUIRED,
                handle=_FcntlLockHandle(lock_path=lock_path, fd=fd, lock_id=str(uuid.uuid4())),
            )

        return AcquireResult(status=AcquireStatus.CONTENDED)

    @staticmethod
    def _open_lock_file(lock_path: Path) -> tuple[int | None, bool]:
        for _ in range(3):
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
                return fd, True
            except FileExistsError:
                try:
                    fd = os.open(str(lock_path), os.O_RDWR)
                    return fd, False
                except FileNotFoundError:
                    # File disappeared between checks; retry exclusive create.
                    continue
                except OSError:
                    return None, False
            except OSError:
                return None, False
        return None, False

    @staticmethod
    def _fd_matches_path(fd: int, lock_path: Path) -> bool:
        try:
            fd_stat = os.fstat(fd)
        except OSError:
            return False
        if fd_stat.st_nlink == 0:
            return False
        try:
            path_stat = lock_path.stat()
        except OSError:
            return False
        return fd_stat.st_dev == path_stat.st_dev and fd_stat.st_ino == path_stat.st_ino

    @staticmethod
    def _unlock_close_fd(fd: int) -> None:
        with contextlib.suppress(OSError):
            assert fcntl is not None
            fcntl.flock(fd, fcntl.LOCK_UN)
        with contextlib.suppress(OSError):
            os.close(fd)

    def release(self, handle: _FcntlLockHandle) -> None:
        if handle.closed:
            return
        try:
            assert fcntl is not None  # For type checkers.
            fcntl.flock(handle.fd, fcntl.LOCK_UN)
        except OSError:
            pass
        finally:
            with contextlib.suppress(OSError):
                os.close(handle.fd)
            handle.closed = True

    def write_info(self, handle: _FcntlLockHandle, info: LockInfo) -> None:
        if handle.closed:
            raise OSError("lock handle is closed")
        if not self._fd_matches_path(handle.fd, handle.lock_path):
            raise OSError(errno.ESTALE, "lock path changed while writing metadata")
        _write_info_path(_metadata_path(handle.lock_path), info)

    def write_failure_tombstone(self, handle: _FcntlLockHandle, info: LockInfo) -> None:
        if handle.closed or not self._fd_matches_path(handle.fd, handle.lock_path):
            return
        stale_info = LockInfo(
            lock_id=info.lock_id,
            pid=-1,
            host="released",
            owner="",
            started_at="1970-01-01T00:00:00+00:00",
            updated_at="1970-01-01T00:00:00+00:00",
            backend=self.name,
            version=1,
        )
        _write_info_path(_metadata_path(handle.lock_path), stale_info)

    def read_info(self, lock_path: Path) -> LockInfo | None:
        metadata = _read_info_path(_metadata_path(lock_path))
        if metadata is not None:
            return metadata
        # Compatibility path: pre-sidecar lock files embedded metadata directly in lock file.
        return _read_info_path(lock_path)

    def _read_info_with_retries(self, lock_path: Path) -> _ReadInfoOutcome:
        metadata_path = _metadata_path(lock_path)
        legacy_candidate = False
        for attempt in range(self.metadata_read_retry_attempts + 1):
            info = self.read_info(lock_path)
            if info is not None:
                source = metadata_path if _read_info_path(metadata_path) is not None else lock_path
                return _ReadInfoOutcome(info=info, state="valid", source_path=source)

            metadata_exists = metadata_path.exists()
            legacy_candidate = metadata_path != lock_path and _path_looks_like_json(lock_path)

            if not metadata_exists and not legacy_candidate:
                return _ReadInfoOutcome(info=None, state="missing", source_path=None)
            if attempt < self.metadata_read_retry_attempts:
                time.sleep(self.metadata_read_retry_sleep_seconds)
        source = metadata_path if metadata_path.exists() else (lock_path if legacy_candidate else None)
        return _ReadInfoOutcome(info=None, state="unreadable", source_path=source)


@dataclass
class _LeaseLockHandle:
    lock_path: Path
    fd: int
    lock_id: str
    closed: bool = False


class LeaseFileLockBackend:
    """File-lease fallback backend for environments without `fcntl`.

    The lock file itself acts as lease marker. Stale/corrupt lease files
    are reclaimed during acquisition attempts.
    """

    name = "lease"
    requires_heartbeat = True
    acquire_attempts = 3
    unreadable_retry_attempts = 10
    unreadable_retry_sleep_seconds = 0.05
    release_unlink_attempts = 5
    release_unlink_retry_sleep_seconds = 0.02

    def acquire(self, lock_path: Path, stale_threshold_seconds: int) -> _LeaseLockHandle | None:
        result = self.acquire_result(lock_path, stale_threshold_seconds)
        if result.status == AcquireStatus.ACQUIRED and result.handle is not None:
            return result.handle
        if result.error is not None:
            raise result.error
        return None

    def acquire_result(self, lock_path: Path, stale_threshold_seconds: int) -> AcquireResult:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_id = str(uuid.uuid4())

        for _ in range(self.acquire_attempts):
            try:
                fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
                try:
                    self._write_lock_marker_fd(fd, lock_id)
                    _write_info_path(_metadata_path(lock_path), self._build_bootstrap_info(lock_id))
                except OSError as e:
                    with contextlib.suppress(OSError):
                        os.close(fd)
                    self._safe_unlink(lock_path)
                    self._safe_unlink_sidecar_if_owned(lock_path, expected_lock_id=lock_id)
                    return AcquireResult(status=AcquireStatus.METADATA_ERROR, error=e)
                held_inode = self._fstat_inode(fd)
                current_inode = self._stat_inode(lock_path)
                if held_inode is None or current_inode != held_inode:
                    with contextlib.suppress(OSError):
                        os.close(fd)
                    self._safe_unlink_sidecar_if_owned(lock_path, expected_lock_id=lock_id)
                    continue
                return AcquireResult(
                    status=AcquireStatus.ACQUIRED,
                    handle=_LeaseLockHandle(lock_path=lock_path, fd=fd, lock_id=lock_id),
                )
            except FileExistsError:
                path_inode = self._stat_inode(lock_path)
                if path_inode is None:
                    continue

                info_outcome = self._read_info_with_retries(lock_path)
                if info_outcome.info is not None:
                    if _is_lock_info_stale(
                        info_outcome.info,
                        stale_threshold_seconds,
                        lock_path=lock_path,
                    ):
                        if not self._safe_unlink_if_inode(lock_path, path_inode):
                            return AcquireResult(status=AcquireStatus.CONTENDED)
                        self._safe_unlink_sidecar_if_owned(
                            lock_path,
                            expected_lock_id=info_outcome.info.lock_id,
                        )
                        continue
                    return AcquireResult(status=AcquireStatus.CONTENDED)

                lock_active = _is_fcntl_lock_active(lock_path)
                if lock_active is True:
                    return AcquireResult(status=AcquireStatus.CONTENDED)
                if info_outcome.state == "missing" and not _is_missing_metadata_stale(
                    lock_path,
                    stale_threshold_seconds,
                ):
                    # Fresh missing metadata is usually a transient bootstrap window.
                    return AcquireResult(status=AcquireStatus.CONTENDED)

                if info_outcome.state == "unreadable":
                    stale_ref = info_outcome.source_path or _metadata_path(lock_path)
                    if (
                        stale_ref == lock_path
                        and _path_looks_like_json(lock_path)
                        and not _metadata_path(lock_path).exists()
                    ):
                        pass
                    elif not _is_path_stale_by_mtime(stale_ref, stale_threshold_seconds):
                        return AcquireResult(status=AcquireStatus.CONTENDED)

                if not self._safe_unlink_if_inode(lock_path, path_inode):
                    return AcquireResult(status=AcquireStatus.CONTENDED)
                # For missing/unreadable metadata we cannot prove ownership, so
                # sidecar cleanup is intentionally skipped to avoid deleting a
                # just-acquired contender's metadata.
                continue
            except OSError as e:
                return AcquireResult(status=AcquireStatus.METADATA_ERROR, error=e)

        return AcquireResult(status=AcquireStatus.CONTENDED)

    @staticmethod
    def _build_bootstrap_info(lock_id: str) -> LockInfo:
        now = _utcnow_iso()
        return LockInfo(
            lock_id=lock_id,
            pid=os.getpid(),
            host=socket.gethostname(),
            owner="",
            started_at=now,
            updated_at=now,
            backend="lease",
            version=1,
        )

    @staticmethod
    def _write_lock_marker_fd(fd: int, lock_id: str) -> None:
        # The primitive lock file tracks ownership at filesystem level.
        # A small marker avoids ambiguous empty-file state across mixed backends.
        payload = f"{lock_id}\n".encode()
        os.lseek(fd, 0, os.SEEK_SET)
        os.ftruncate(fd, 0)
        _write_all(fd, payload)
        os.fsync(fd)

    def _read_info_with_retries(self, lock_path: Path) -> _ReadInfoOutcome:
        metadata_path = _metadata_path(lock_path)
        for attempt in range(self.unreadable_retry_attempts + 1):
            info = self.read_info(lock_path)
            if info is not None:
                source = metadata_path if _read_info_path(metadata_path) is not None else lock_path
                return _ReadInfoOutcome(info=info, state="valid", source_path=source)

            metadata_exists = metadata_path.exists()
            legacy_candidate = metadata_path != lock_path and _path_looks_like_json(lock_path)
            if not metadata_exists and not legacy_candidate:
                return _ReadInfoOutcome(info=None, state="missing", source_path=None)
            if attempt < self.unreadable_retry_attempts:
                time.sleep(self.unreadable_retry_sleep_seconds)
        source = metadata_path if metadata_path.exists() else (lock_path if legacy_candidate else None)
        return _ReadInfoOutcome(info=None, state="unreadable", source_path=source)

    def release(self, handle: _LeaseLockHandle) -> None:
        if handle.closed:
            return

        held_inode = self._fstat_inode(handle.fd)
        with contextlib.suppress(OSError):
            os.close(handle.fd)
        handle.closed = True

        if held_inode is None:
            return

        for attempt in range(self.release_unlink_attempts):
            path_inode = self._stat_inode(handle.lock_path)
            if path_inode is None or path_inode != held_inode:
                return

            lock_info = self.read_info(handle.lock_path)
            if lock_info is not None and lock_info.lock_id != handle.lock_id:
                return

            if self._safe_unlink_if_inode(handle.lock_path, held_inode):
                self._safe_unlink_sidecar_if_owned(handle.lock_path, expected_lock_id=handle.lock_id)
                return
            if attempt < self.release_unlink_attempts - 1:
                time.sleep(self.release_unlink_retry_sleep_seconds)

        # Last-resort fallback: if unlink consistently fails (e.g. platform-specific
        # file-handle contention), write stale metadata so contenders can recover.
        self._write_stale_tombstone(handle.lock_path, handle.lock_id, held_inode)

    def write_info(self, handle: _LeaseLockHandle, info: LockInfo) -> None:
        if handle.closed:
            raise OSError("lock handle is closed")
        held_inode = self._fstat_inode(handle.fd)
        if held_inode is None:
            raise OSError(errno.ESTALE, "lock handle is no longer valid")
        current_inode = self._stat_inode(handle.lock_path)
        if current_inode != held_inode:
            raise OSError(errno.ESTALE, "lock path changed while writing metadata")
        existing = self.read_info(handle.lock_path)
        if existing is not None and existing.lock_id != handle.lock_id:
            raise OSError(errno.EPERM, "lock metadata ownership changed")
        _write_info_path(_metadata_path(handle.lock_path), info)

    def read_info(self, lock_path: Path) -> LockInfo | None:
        metadata = _read_info_path(_metadata_path(lock_path))
        if metadata is not None:
            return metadata
        # Compatibility path: pre-sidecar lock files embedded metadata directly in lock file.
        return _read_info_path(lock_path)

    @staticmethod
    def _safe_unlink(lock_path: Path) -> bool:
        try:
            lock_path.unlink()
            return True
        except FileNotFoundError:
            return True
        except OSError:
            return False

    def _safe_unlink_if_inode(self, lock_path: Path, expected_inode: tuple[int, int]) -> bool:
        current = self._stat_inode(lock_path)
        if current is None:
            return True
        if current != expected_inode:
            return False
        return self._safe_unlink(lock_path)

    def _safe_unlink_sidecar_if_owned(self, lock_path: Path, *, expected_lock_id: str) -> bool:
        """Best-effort sidecar cleanup guarded against new-owner races."""
        metadata_path = _metadata_path(lock_path)
        inode_before = self._stat_inode(metadata_path)
        if inode_before is None:
            return True

        metadata = _read_info_path(metadata_path)
        if metadata is None or metadata.lock_id != expected_lock_id:
            return False

        inode_after = self._stat_inode(metadata_path)
        if inode_after is None:
            return True
        if inode_after != inode_before:
            return False

        return self._safe_unlink_if_inode(metadata_path, inode_after)

    @staticmethod
    def _fstat_inode(fd: int) -> tuple[int, int] | None:
        try:
            stat_result = os.fstat(fd)
            return stat_result.st_dev, stat_result.st_ino
        except OSError:
            return None

    @staticmethod
    def _stat_inode(lock_path: Path) -> tuple[int, int] | None:
        try:
            stat_result = lock_path.stat()
            return stat_result.st_dev, stat_result.st_ino
        except OSError:
            return None

    def _write_stale_tombstone(self, lock_path: Path, lock_id: str, held_inode: tuple[int, int]) -> None:
        current_inode = self._stat_inode(lock_path)
        if current_inode != held_inode:
            return
        stale_info = LockInfo(
            lock_id=lock_id,
            pid=-1,
            host="released",
            owner="",
            started_at="1970-01-01T00:00:00+00:00",
            updated_at="1970-01-01T00:00:00+00:00",
            backend=self.name,
            version=1,
        )
        with contextlib.suppress(OSError):
            _write_info_path(_metadata_path(lock_path), stale_info)
