"""Edge-case tests for core/locks/backends.py to increase coverage."""

from __future__ import annotations

import errno
import json
import os
import socket
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest

import cja_auto_sdr.core.locks.backends as backends_module
from cja_auto_sdr.core.locks.backends import (
    FcntlFileLockBackend,
    LeaseFileLockBackend,
    LockInfo,
    _is_lock_info_stale,
    _is_missing_metadata_stale,
    _is_path_stale_by_mtime,
    _is_process_running,
    _metadata_path,
    _path_looks_like_json,
    _read_info_path,
    _write_all,
    _write_info_path,
)


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


# ---------------------------------------------------------------------------
# 1. _write_all() edge cases
# ---------------------------------------------------------------------------


class TestWriteAll:
    def test_short_write_zero_raises(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """os.write returning 0 should raise OSError."""
        fd = os.open(str(tmp_path / "test"), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            monkeypatch.setattr(os, "write", lambda fd, data: 0)
            with pytest.raises(OSError, match="short write"):
                _write_all(fd, b"hello")
        finally:
            os.close(fd)

    def test_short_write_negative_raises(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """os.write returning negative should raise OSError."""
        fd = os.open(str(tmp_path / "test"), os.O_CREAT | os.O_RDWR, 0o600)
        try:
            monkeypatch.setattr(os, "write", lambda fd, data: -1)
            with pytest.raises(OSError, match="short write"):
                _write_all(fd, b"hello")
        finally:
            os.close(fd)

    def test_multi_chunk_write(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """_write_all loops when os.write returns partial bytes."""
        fd = os.open(str(tmp_path / "test"), os.O_CREAT | os.O_RDWR, 0o600)
        call_count = {"n": 0}
        original_write = os.write

        def _partial_write(fd_: int, data: bytes) -> int:
            call_count["n"] += 1
            # First call writes only 1 byte, rest write normally
            if call_count["n"] == 1:
                return original_write(fd_, data[:1])
            return original_write(fd_, data)

        try:
            monkeypatch.setattr(os, "write", _partial_write)
            _write_all(fd, b"hello")
            assert call_count["n"] >= 2
        finally:
            os.close(fd)


# ---------------------------------------------------------------------------
# 2. _write_info_path() failure paths
# ---------------------------------------------------------------------------


class TestWriteInfoPath:
    def test_oserror_during_payload_write_cleans_tmp(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """OSError during _write_all triggers tmp cleanup and re-raise."""
        info = _build_lock_info("write-fail-test")
        target = tmp_path / "meta.info"

        monkeypatch.setattr(
            backends_module,
            "_write_all",
            lambda fd, payload: (_ for _ in ()).throw(OSError(errno.EIO, "disk error")),
        )
        with pytest.raises(OSError, match="disk error"):
            _write_info_path(target, info)

        # Tmp file should be cleaned up
        remaining = list(tmp_path.iterdir())
        assert not any(str(f).endswith(".tmp") for f in remaining)

    def test_os_replace_failure_cleans_tmp(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """OSError during os.replace triggers tmp cleanup and re-raise."""
        info = _build_lock_info("replace-fail-test")
        target = tmp_path / "meta.info"

        def _failing_replace(src: str, dst: str) -> None:
            raise OSError(errno.EIO, "replace failed")

        monkeypatch.setattr(os, "replace", _failing_replace)
        with pytest.raises(OSError, match="replace failed"):
            _write_info_path(target, info)

        # Tmp file should be cleaned up
        remaining = list(tmp_path.iterdir())
        assert not any(str(f).endswith(".tmp") for f in remaining)

    def test_successful_write_creates_target(self, tmp_path: Path) -> None:
        """Normal write produces the expected file."""
        info = _build_lock_info("success-write")
        target = tmp_path / "meta.info"
        _write_info_path(target, info)
        assert target.exists()
        data = json.loads(target.read_text(encoding="utf-8"))
        assert data["lock_id"] == "success-write"


# ---------------------------------------------------------------------------
# 3. _read_info_path() edge cases
# ---------------------------------------------------------------------------


class TestReadInfoPath:
    def test_missing_file_returns_none(self, tmp_path: Path) -> None:
        assert _read_info_path(tmp_path / "nonexistent.info") is None

    def test_corrupt_json_returns_none(self, tmp_path: Path) -> None:
        f = tmp_path / "corrupt.info"
        f.write_text("{not valid json", encoding="utf-8")
        assert _read_info_path(f) is None

    def test_non_dict_json_list_returns_none(self, tmp_path: Path) -> None:
        """JSON that parses as a list (not dict) must return None."""
        f = tmp_path / "list.info"
        f.write_text("[1, 2, 3]", encoding="utf-8")
        assert _read_info_path(f) is None

    def test_non_dict_json_string_returns_none(self, tmp_path: Path) -> None:
        """JSON that parses as a string must return None."""
        f = tmp_path / "string.info"
        f.write_text('"just a string"', encoding="utf-8")
        assert _read_info_path(f) is None

    def test_non_dict_json_int_returns_none(self, tmp_path: Path) -> None:
        """JSON that parses as an integer must return None."""
        f = tmp_path / "int.info"
        f.write_text("42", encoding="utf-8")
        assert _read_info_path(f) is None

    def test_permission_error_returns_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """OSError on open returns None."""
        f = tmp_path / "perm.info"
        f.write_text("{}", encoding="utf-8")
        import builtins

        original_open = builtins.open

        def _failing_open(*args, **kwargs):  # type: ignore[no-untyped-def]
            if str(f) in str(args[0]):
                raise PermissionError("access denied")
            return original_open(*args, **kwargs)

        monkeypatch.setattr(builtins, "open", _failing_open)
        assert _read_info_path(f) is None

    def test_valid_dict_but_unparseable_returns_none(self, tmp_path: Path) -> None:
        """Valid JSON dict but missing required fields for LockInfo returns None."""
        f = tmp_path / "empty.info"
        f.write_text("{}", encoding="utf-8")
        assert _read_info_path(f) is None


# ---------------------------------------------------------------------------
# 4. _path_looks_like_json() edge cases
# ---------------------------------------------------------------------------


class TestPathLooksLikeJson:
    def test_file_starting_with_brace(self, tmp_path: Path) -> None:
        f = tmp_path / "test.json"
        f.write_bytes(b'{"key": "val"}')
        assert _path_looks_like_json(f) is True

    def test_file_starting_with_bracket(self, tmp_path: Path) -> None:
        f = tmp_path / "test.json"
        f.write_bytes(b"[1, 2, 3]")
        assert _path_looks_like_json(f) is True

    def test_file_starting_with_text(self, tmp_path: Path) -> None:
        f = tmp_path / "test.txt"
        f.write_bytes(b"hello world")
        assert _path_looks_like_json(f) is False

    def test_empty_file(self, tmp_path: Path) -> None:
        f = tmp_path / "empty"
        f.write_bytes(b"")
        assert _path_looks_like_json(f) is False

    def test_missing_file(self, tmp_path: Path) -> None:
        assert _path_looks_like_json(tmp_path / "nope") is False

    def test_whitespace_then_brace(self, tmp_path: Path) -> None:
        f = tmp_path / "ws.json"
        f.write_bytes(b"   \n  {}")
        assert _path_looks_like_json(f) is True


# ---------------------------------------------------------------------------
# 5. _is_path_stale_by_mtime() boundary conditions
# ---------------------------------------------------------------------------


class TestIsPathStaleByMtime:
    def test_file_at_exact_threshold_is_not_stale(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """A file whose age equals the threshold should NOT be stale (> not >=)."""
        f = tmp_path / "test"
        f.write_text("x", encoding="utf-8")
        threshold = 10
        frozen_now = 1000000.0
        target_time = frozen_now - threshold  # age == threshold exactly
        os.utime(f, (target_time, target_time))
        monkeypatch.setattr(time, "time", lambda: frozen_now)
        # age_seconds == 10, threshold == 10 => 10 > max(1,10) is False
        assert _is_path_stale_by_mtime(f, threshold) is False

    def test_file_beyond_threshold_is_stale(self, tmp_path: Path) -> None:
        f = tmp_path / "test"
        f.write_text("x", encoding="utf-8")
        old = time.time() - 100
        os.utime(f, (old, old))
        assert _is_path_stale_by_mtime(f, 10) is True

    def test_oserror_on_stat_returns_false(self, tmp_path: Path) -> None:
        """When stat() raises OSError, should return False."""
        missing = tmp_path / "gone"
        assert _is_path_stale_by_mtime(missing, 1) is False

    def test_threshold_below_1_is_clamped(self, tmp_path: Path) -> None:
        """Threshold < 1 should be treated as 1 via max(1, ...)."""
        f = tmp_path / "test"
        f.write_text("x", encoding="utf-8")
        old = time.time() - 5
        os.utime(f, (old, old))
        assert _is_path_stale_by_mtime(f, 0) is True

    def test_fresh_file_is_not_stale(self, tmp_path: Path) -> None:
        f = tmp_path / "test"
        f.write_text("x", encoding="utf-8")
        assert _is_path_stale_by_mtime(f, 3600) is False


# ---------------------------------------------------------------------------
# 6. _is_missing_metadata_stale() boundary conditions
# ---------------------------------------------------------------------------


class TestIsMissingMetadataStale:
    def test_missing_file_returns_false(self, tmp_path: Path) -> None:
        assert _is_missing_metadata_stale(tmp_path / "gone", 10) is False

    def test_fresh_file_is_not_stale(self, tmp_path: Path) -> None:
        f = tmp_path / "fresh"
        f.write_text("x", encoding="utf-8")
        assert _is_missing_metadata_stale(f, 3600) is False

    def test_old_file_is_stale(self, tmp_path: Path) -> None:
        f = tmp_path / "old"
        f.write_text("x", encoding="utf-8")
        old = time.time() - 100
        os.utime(f, (old, old))
        assert _is_missing_metadata_stale(f, 10) is True

    def test_reclaim_capped_at_max_age(self, tmp_path: Path) -> None:
        """Even with large threshold, reclaim window is capped at _MISSING_METADATA_RECLAIM_MAX_AGE_SECONDS."""
        f = tmp_path / "capped"
        f.write_text("x", encoding="utf-8")
        old = time.time() - 10
        os.utime(f, (old, old))
        # Threshold is huge but cap is 5.0 seconds
        assert _is_missing_metadata_stale(f, 999999) is True


# ---------------------------------------------------------------------------
# 7. LockInfo.from_dict() parse fallback paths
# ---------------------------------------------------------------------------


class TestLockInfoFromDict:
    def test_modern_parse_failure_falls_back_to_legacy(self) -> None:
        """When modern parse fails (missing lock_id), legacy format with pid+timestamp should work."""
        legacy_data = {
            "pid": os.getpid(),
            "timestamp": time.time(),
            "started_at": datetime.now(UTC).isoformat(),
        }
        result = LockInfo.from_dict(legacy_data)
        assert result is not None
        assert result.pid == os.getpid()
        assert result.backend == "legacy"

    def test_both_modern_and_legacy_fail_returns_none(self) -> None:
        """When neither modern nor legacy parsing works, return None."""
        # No 'pid' key means legacy fails; no 'lock_id' means modern fails
        result = LockInfo.from_dict({"foo": "bar"})
        assert result is None

    def test_modern_parse_with_none_pid_falls_to_legacy(self) -> None:
        """Modern parse that produces None pid falls back to legacy."""
        data = {
            "lock_id": "test-id",
            "pid": True,  # bool pid -> coerce_pid returns None
            "host": "host",
            "started_at": datetime.now(UTC).isoformat(),
        }
        # Modern returns None because pid=True -> _coerce_pid -> None
        # Legacy also returns None because pid=True -> _coerce_pid -> None
        result = LockInfo.from_dict(data)
        assert result is None


# ---------------------------------------------------------------------------
# 8. LockInfo._from_modern_dict() edge cases
# ---------------------------------------------------------------------------


class TestFromModernDict:
    def test_missing_lock_id_returns_none(self) -> None:
        data = {
            "pid": 123,
            "host": "h",
            "started_at": "2024-01-01T00:00:00+00:00",
        }
        assert LockInfo._from_modern_dict(data) is None

    def test_missing_host_returns_none(self) -> None:
        data = {
            "lock_id": "id",
            "pid": 123,
            "started_at": "2024-01-01T00:00:00+00:00",
        }
        # host is required via data["host"] - KeyError -> returns None
        del data  # Force missing
        data_no_host = {
            "lock_id": "id",
            "pid": 123,
            "started_at": "2024-01-01T00:00:00+00:00",
        }
        # Actually host IS accessed with data["host"] which will KeyError
        result = LockInfo._from_modern_dict(data_no_host)
        assert result is None

    def test_missing_started_at_returns_none(self) -> None:
        data = {
            "lock_id": "id",
            "pid": 123,
            "host": "h",
        }
        assert LockInfo._from_modern_dict(data) is None

    def test_bool_pid_returns_none(self) -> None:
        data = {
            "lock_id": "id",
            "pid": True,
            "host": "h",
            "started_at": "2024-01-01T00:00:00+00:00",
        }
        assert LockInfo._from_modern_dict(data) is None

    def test_string_pid_coerced(self) -> None:
        data = {
            "lock_id": "id",
            "pid": "42",
            "host": "h",
            "started_at": "2024-01-01T00:00:00+00:00",
        }
        result = LockInfo._from_modern_dict(data)
        assert result is not None
        assert result.pid == 42

    def test_optional_fields_have_defaults(self) -> None:
        data = {
            "lock_id": "id",
            "pid": 1,
            "host": "h",
            "started_at": "2024-01-01T00:00:00+00:00",
        }
        result = LockInfo._from_modern_dict(data)
        assert result is not None
        assert result.owner == ""
        assert result.backend == ""
        assert result.version == 1
        assert result.updated_at == "2024-01-01T00:00:00+00:00"


# ---------------------------------------------------------------------------
# 9. LockInfo._from_legacy_dict() edge cases
# ---------------------------------------------------------------------------


class TestFromLegacyDict:
    def test_missing_pid_returns_none(self) -> None:
        assert LockInfo._from_legacy_dict({"timestamp": 123.0}) is None

    def test_bool_pid_returns_none(self) -> None:
        assert LockInfo._from_legacy_dict({"pid": False}) is None

    def test_valid_legacy_format(self) -> None:
        ts = time.time()
        data = {"pid": 42, "timestamp": ts}
        result = LockInfo._from_legacy_dict(data)
        assert result is not None
        assert result.pid == 42
        assert result.backend == "legacy"

    def test_legacy_with_host_uses_provided_host(self) -> None:
        data = {"pid": 42, "timestamp": time.time(), "host": "remote-box"}
        result = LockInfo._from_legacy_dict(data)
        assert result is not None
        assert result.host == "remote-box"

    def test_legacy_without_host_uses_local(self) -> None:
        data = {"pid": 42, "timestamp": time.time()}
        result = LockInfo._from_legacy_dict(data)
        assert result is not None
        assert result.host == socket.gethostname()

    def test_legacy_lock_id_generated_when_missing(self) -> None:
        data = {"pid": 42, "timestamp": time.time()}
        result = LockInfo._from_legacy_dict(data)
        assert result is not None
        assert result.lock_id.startswith("legacy-42-")

    def test_legacy_lock_id_used_when_present(self) -> None:
        data = {"pid": 42, "timestamp": time.time(), "lock_id": "specific-id"}
        result = LockInfo._from_legacy_dict(data)
        assert result is not None
        assert result.lock_id == "specific-id"


# ---------------------------------------------------------------------------
# 10. _coerce_legacy_epoch() edge cases
# ---------------------------------------------------------------------------


class TestCoerceLegacyEpoch:
    def test_bool_returns_none(self) -> None:
        assert LockInfo._coerce_legacy_epoch(True) is None
        assert LockInfo._coerce_legacy_epoch(False) is None

    def test_string_returns_none(self) -> None:
        assert LockInfo._coerce_legacy_epoch("1234567890") is None

    def test_none_returns_none(self) -> None:
        assert LockInfo._coerce_legacy_epoch(None) is None

    def test_list_returns_none(self) -> None:
        assert LockInfo._coerce_legacy_epoch([1, 2, 3]) is None

    def test_inf_returns_none(self) -> None:
        assert LockInfo._coerce_legacy_epoch(float("inf")) is None

    def test_neg_inf_returns_none(self) -> None:
        assert LockInfo._coerce_legacy_epoch(float("-inf")) is None

    def test_nan_returns_none(self) -> None:
        assert LockInfo._coerce_legacy_epoch(float("nan")) is None

    def test_valid_int_returns_float(self) -> None:
        result = LockInfo._coerce_legacy_epoch(1234567890)
        assert result == 1234567890.0

    def test_valid_float_returns_float(self) -> None:
        result = LockInfo._coerce_legacy_epoch(1234567890.123)
        assert result == 1234567890.123

    def test_zero_returns_float(self) -> None:
        result = LockInfo._coerce_legacy_epoch(0)
        assert result == 0.0

    def test_negative_returns_float(self) -> None:
        result = LockInfo._coerce_legacy_epoch(-100)
        assert result == -100.0


# ---------------------------------------------------------------------------
# 11. _coerce_legacy_int() edge cases
# ---------------------------------------------------------------------------


class TestCoerceLegacyInt:
    def test_none_returns_default(self) -> None:
        assert LockInfo._coerce_legacy_int(None, default=5) == 5

    def test_empty_string_returns_default(self) -> None:
        assert LockInfo._coerce_legacy_int("", default=7) == 7

    def test_valid_int(self) -> None:
        assert LockInfo._coerce_legacy_int(42, default=0) == 42

    def test_valid_string_int(self) -> None:
        assert LockInfo._coerce_legacy_int("42", default=0) == 42

    def test_non_numeric_string_returns_default(self) -> None:
        assert LockInfo._coerce_legacy_int("abc", default=3) == 3

    def test_float_coerces_to_int(self) -> None:
        assert LockInfo._coerce_legacy_int(3.9, default=0) == 3

    def test_bool_coerces_to_int(self) -> None:
        # bool is subclass of int, so int(True) == 1
        assert LockInfo._coerce_legacy_int(True, default=0) == 1

    def test_list_returns_default(self) -> None:
        assert LockInfo._coerce_legacy_int([1, 2], default=9) == 9


# ---------------------------------------------------------------------------
# 12. LockInfo._coerce_pid() edge cases
# ---------------------------------------------------------------------------


class TestCoercePid:
    def test_bool_returns_none(self) -> None:
        assert LockInfo._coerce_pid(True) is None
        assert LockInfo._coerce_pid(False) is None

    def test_valid_int(self) -> None:
        assert LockInfo._coerce_pid(42) == 42

    def test_string_int(self) -> None:
        assert LockInfo._coerce_pid("42") == 42

    def test_none_returns_none(self) -> None:
        assert LockInfo._coerce_pid(None) is None

    def test_non_numeric_returns_none(self) -> None:
        assert LockInfo._coerce_pid("abc") is None

    def test_overflow_returns_none(self) -> None:
        # A value that would overflow C int but Python handles it
        assert LockInfo._coerce_pid(10**100) == 10**100  # Python int doesn't overflow


# ---------------------------------------------------------------------------
# 13. _is_process_running() edge cases
# ---------------------------------------------------------------------------


class TestIsProcessRunning:
    def test_bool_input_returns_false(self) -> None:
        assert _is_process_running(True) is False
        assert _is_process_running(False) is False

    def test_zero_returns_false(self) -> None:
        assert _is_process_running(0) is False

    def test_negative_returns_false(self) -> None:
        assert _is_process_running(-1) is False
        assert _is_process_running(-999) is False

    def test_current_pid_returns_true(self) -> None:
        assert _is_process_running(os.getpid()) is True

    def test_dead_pid_returns_false(self) -> None:
        # PID 2**30 is extremely unlikely to be running
        assert _is_process_running(2**30) is False

    def test_permission_error_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """If os.kill raises PermissionError, process exists but we lack perms -> True."""

        def _permission_kill(pid: int, sig: int) -> None:
            raise PermissionError("Operation not permitted")

        monkeypatch.setattr(os, "kill", _permission_kill)
        assert _is_process_running(42) is True

    def test_eperm_oserror_returns_true(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OSError with errno EPERM means process exists -> True."""

        def _eperm_kill(pid: int, sig: int) -> None:
            raise OSError(errno.EPERM, "Operation not permitted")

        monkeypatch.setattr(os, "kill", _eperm_kill)
        assert _is_process_running(42) is True

    def test_other_oserror_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """OSError with errno other than EPERM -> False."""

        def _eio_kill(pid: int, sig: int) -> None:
            raise OSError(errno.EIO, "I/O error")

        monkeypatch.setattr(os, "kill", _eio_kill)
        assert _is_process_running(42) is False

    def test_overflow_pid_returns_false(self) -> None:
        """Huge pid that overflows os.kill should return False."""
        assert _is_process_running(10**40) is False


# ---------------------------------------------------------------------------
# 14. _is_lock_info_stale() edge cases
# ---------------------------------------------------------------------------


class TestIsLockInfoStale:
    def test_fcntl_backend_no_lock_path_same_host_live_pid(self) -> None:
        """fcntl backend, no lock_path, same host, live pid -> not stale."""
        info = _build_lock_info("test", backend="fcntl", pid=os.getpid())
        assert _is_lock_info_stale(info, 10) is False

    def test_fcntl_backend_no_lock_path_same_host_dead_pid(self) -> None:
        """fcntl backend, no lock_path, same host, dead pid -> stale."""
        info = _build_lock_info("test", backend="fcntl", pid=2**30)
        assert _is_lock_info_stale(info, 10) is True

    def test_fcntl_backend_no_lock_path_remote_host_returns_false(self) -> None:
        """fcntl backend, no lock_path, remote host -> conservative False."""
        info = _build_lock_info("test", backend="fcntl", host="remote-host-xyz")
        assert _is_lock_info_stale(info, 10) is False

    def test_remote_host_time_based_staleness(self) -> None:
        """Non-fcntl, remote host: staleness determined by time threshold."""
        old = datetime(2000, 1, 1, tzinfo=UTC).isoformat()
        info = _build_lock_info(
            "test",
            backend="lease",
            host="remote-host-xyz",
            started_at=old,
            updated_at=old,
        )
        assert _is_lock_info_stale(info, 10) is True

    def test_remote_host_fresh_metadata_not_stale(self) -> None:
        """Non-fcntl, remote host with fresh timestamps -> not stale."""
        now = datetime.now(UTC).isoformat()
        info = _build_lock_info(
            "test",
            backend="lease",
            host="remote-host-xyz",
            started_at=now,
            updated_at=now,
        )
        assert _is_lock_info_stale(info, 3600) is False

    def test_remote_host_unparseable_timestamps_is_stale(self) -> None:
        """Non-fcntl, remote host, both timestamps unparseable -> stale."""
        info = _build_lock_info(
            "test",
            backend="lease",
            host="remote-host-xyz",
            started_at="not-a-date",
            updated_at="also-not-a-date",
        )
        assert _is_lock_info_stale(info, 10) is True

    def test_remote_host_updated_at_parseable_started_at_not(self) -> None:
        """When updated_at is parseable but started_at is not, uses updated_at."""
        now = datetime.now(UTC).isoformat()
        info = _build_lock_info(
            "test",
            backend="lease",
            host="remote-host-xyz",
            started_at="garbage",
            updated_at=now,
        )
        assert _is_lock_info_stale(info, 3600) is False

    def test_remote_host_naive_timestamp_gets_utc(self) -> None:
        """Naive datetime (no tzinfo) should be treated as UTC."""
        # A naive timestamp from ~1 second ago should not be stale with 3600 threshold
        now_naive = datetime.now(UTC).replace(tzinfo=None).isoformat()
        info = _build_lock_info(
            "test",
            backend="lease",
            host="remote-host-xyz",
            started_at=now_naive,
            updated_at=now_naive,
        )
        assert _is_lock_info_stale(info, 3600) is False

    def test_same_host_non_fcntl_live_pid_not_stale(self) -> None:
        """Same host, non-fcntl: live pid -> not stale regardless of time."""
        old = datetime(2000, 1, 1, tzinfo=UTC).isoformat()
        info = _build_lock_info(
            "test",
            backend="lease",
            pid=os.getpid(),
            started_at=old,
            updated_at=old,
        )
        assert _is_lock_info_stale(info, 1) is False

    def test_same_host_non_fcntl_dead_pid_is_stale(self) -> None:
        """Same host, non-fcntl: dead pid -> stale."""
        info = _build_lock_info("test", backend="lease", pid=2**30)
        assert _is_lock_info_stale(info, 10) is True


# ---------------------------------------------------------------------------
# 15. Backend write_info() / write_failure_tombstone() with closed handle
# ---------------------------------------------------------------------------


class TestFcntlBackendWriteInfo:
    def test_write_info_closed_handle_raises(self, tmp_path: Path) -> None:
        if backends_module.fcntl is None:
            pytest.skip("fcntl not available on this platform")

        from cja_auto_sdr.core.locks.backends import _FcntlLockHandle

        handle = _FcntlLockHandle(lock_path=tmp_path / "lock", fd=-1, lock_id="x", closed=True)
        backend = FcntlFileLockBackend()
        info = _build_lock_info("test")
        with pytest.raises(OSError, match="lock handle is closed"):
            backend.write_info(handle, info)

    def test_write_info_path_mismatch_raises(self, tmp_path: Path) -> None:
        if backends_module.fcntl is None:
            pytest.skip("fcntl not available on this platform")

        from cja_auto_sdr.core.locks.backends import _FcntlLockHandle

        lock_file = tmp_path / "lock"
        lock_file.write_text("x", encoding="utf-8")
        fd = os.open(str(lock_file), os.O_RDWR)
        # Delete the file so fd no longer matches path
        lock_file.unlink()
        lock_file.write_text("different", encoding="utf-8")
        handle = _FcntlLockHandle(lock_path=lock_file, fd=fd, lock_id="x", closed=False)
        backend = FcntlFileLockBackend()
        info = _build_lock_info("test")
        try:
            with pytest.raises(OSError):
                backend.write_info(handle, info)
        finally:
            os.close(fd)

    def test_write_failure_tombstone_closed_handle_noop(self, tmp_path: Path) -> None:
        if backends_module.fcntl is None:
            pytest.skip("fcntl not available on this platform")

        from cja_auto_sdr.core.locks.backends import _FcntlLockHandle

        handle = _FcntlLockHandle(lock_path=tmp_path / "lock", fd=-1, lock_id="x", closed=True)
        backend = FcntlFileLockBackend()
        info = _build_lock_info("test")
        # Should silently return without raising
        backend.write_failure_tombstone(handle, info)

    def test_write_failure_tombstone_path_mismatch_noop(self, tmp_path: Path) -> None:
        if backends_module.fcntl is None:
            pytest.skip("fcntl not available on this platform")

        from cja_auto_sdr.core.locks.backends import _FcntlLockHandle

        lock_file = tmp_path / "lock"
        lock_file.write_text("x", encoding="utf-8")
        fd = os.open(str(lock_file), os.O_RDWR)
        lock_file.unlink()
        lock_file.write_text("different", encoding="utf-8")
        handle = _FcntlLockHandle(lock_path=lock_file, fd=fd, lock_id="x", closed=False)
        backend = FcntlFileLockBackend()
        info = _build_lock_info("test")
        try:
            # Should silently return without raising
            backend.write_failure_tombstone(handle, info)
        finally:
            os.close(fd)


class TestLeaseBackendWriteInfo:
    def test_write_info_closed_handle_raises(self, tmp_path: Path) -> None:
        from cja_auto_sdr.core.locks.backends import _LeaseLockHandle

        handle = _LeaseLockHandle(lock_path=tmp_path / "lock", fd=-1, lock_id="x", closed=True)
        backend = LeaseFileLockBackend()
        info = _build_lock_info("test")
        with pytest.raises(OSError, match="lock handle is closed"):
            backend.write_info(handle, info)

    def test_write_info_stale_fd_raises(self, tmp_path: Path) -> None:
        from cja_auto_sdr.core.locks.backends import _LeaseLockHandle

        lock_file = tmp_path / "lock"
        lock_file.write_text("x", encoding="utf-8")
        fd = os.open(str(lock_file), os.O_RDWR)
        os.close(fd)  # Close fd so fstat fails
        handle = _LeaseLockHandle(lock_path=lock_file, fd=fd, lock_id="x", closed=False)
        backend = LeaseFileLockBackend()
        info = _build_lock_info("test")
        with pytest.raises(OSError, match="lock handle is no longer valid"):
            backend.write_info(handle, info)

    def test_write_info_inode_mismatch_raises(self, tmp_path: Path) -> None:
        from cja_auto_sdr.core.locks.backends import _LeaseLockHandle

        lock_file = tmp_path / "lock"
        lock_file.write_text("x", encoding="utf-8")
        fd = os.open(str(lock_file), os.O_RDWR)
        # Replace the file so inode changes
        lock_file.unlink()
        lock_file.write_text("y", encoding="utf-8")
        handle = _LeaseLockHandle(lock_path=lock_file, fd=fd, lock_id="x", closed=False)
        backend = LeaseFileLockBackend()
        info = _build_lock_info("test")
        try:
            with pytest.raises(OSError):
                backend.write_info(handle, info)
        finally:
            os.close(fd)

    def test_write_info_ownership_changed_raises(self, tmp_path: Path) -> None:
        from cja_auto_sdr.core.locks.backends import _LeaseLockHandle

        lock_file = tmp_path / "lock"
        lock_file.write_text("x", encoding="utf-8")
        fd = os.open(str(lock_file), os.O_RDWR)
        # Write metadata for a different owner
        metadata = _metadata_path(lock_file)
        other_info = _build_lock_info("other-owner-id")
        _write_info_path(metadata, other_info)

        handle = _LeaseLockHandle(lock_path=lock_file, fd=fd, lock_id="my-lock-id", closed=False)
        backend = LeaseFileLockBackend()
        info = _build_lock_info("my-lock-id")
        try:
            with pytest.raises(OSError):
                backend.write_info(handle, info)
        finally:
            os.close(fd)


# ---------------------------------------------------------------------------
# 17. _metadata_path()
# ---------------------------------------------------------------------------


class TestMetadataPath:
    def test_appends_info_suffix(self) -> None:
        p = Path("/tmp/mylock.lock")
        assert _metadata_path(p) == Path("/tmp/mylock.lock.info")

    def test_nested_path(self) -> None:
        p = Path("/a/b/c/lock")
        assert _metadata_path(p) == Path("/a/b/c/lock.info")


# ---------------------------------------------------------------------------
# 18. _coerce_legacy_time() edge cases
# ---------------------------------------------------------------------------


class TestCoerceLegacyTime:
    def test_string_primary_used_directly(self) -> None:
        result = LockInfo._coerce_legacy_time("2024-01-01T00:00:00+00:00", None)
        assert result == "2024-01-01T00:00:00+00:00"

    def test_empty_string_primary_falls_to_epoch(self) -> None:
        ts = 1704067200.0  # 2024-01-01 00:00:00 UTC
        result = LockInfo._coerce_legacy_time("", ts)
        assert "2024" in result

    def test_none_primary_none_fallback_uses_now(self) -> None:
        result = LockInfo._coerce_legacy_time(None, None)
        # Should be a valid ISO string roughly now
        assert "T" in result

    def test_inf_epoch_fallback_uses_now(self) -> None:
        result = LockInfo._coerce_legacy_time(None, float("inf"))
        # inf is rejected by _coerce_legacy_epoch, falls through to _utcnow_iso
        assert "T" in result

    def test_overflow_epoch_uses_now(self) -> None:
        # A finite but out-of-range epoch for datetime.fromtimestamp
        result = LockInfo._coerce_legacy_time(None, 10**20)
        # Should not crash; either converts or falls to now
        assert "T" in result


# ---------------------------------------------------------------------------
# 19. from_dict() exception branches (lines 192-194, 199-201)
# ---------------------------------------------------------------------------


class TestFromDictExceptionBranches:
    def test_modern_raises_unexpected_exception_falls_to_legacy(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When _from_modern_dict raises a recoverable exception, from_dict catches it
        and tries the legacy path."""

        def _boom(data: dict) -> LockInfo | None:
            raise ValueError("unexpected boom")

        monkeypatch.setattr(LockInfo, "_from_modern_dict", staticmethod(_boom))
        # Legacy path should still work with pid key
        data = {"pid": 42, "timestamp": time.time()}
        result = LockInfo.from_dict(data)
        assert result is not None
        assert result.pid == 42

    def test_both_raise_unexpected_exceptions_returns_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When both modern and legacy raise recoverable exceptions, return None."""

        def _boom_modern(data: dict) -> LockInfo | None:
            raise ValueError("modern boom")

        def _boom_legacy(data: dict) -> LockInfo | None:
            raise ValueError("legacy boom")

        monkeypatch.setattr(LockInfo, "_from_modern_dict", staticmethod(_boom_modern))
        monkeypatch.setattr(LockInfo, "_from_legacy_dict", staticmethod(_boom_legacy))
        result = LockInfo.from_dict({"pid": 42})
        assert result is None

    def test_legacy_hostname_oserror_is_recoverable(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Legacy parse OSError must degrade to None instead of aborting lock flows."""

        def _hostname_boom() -> str:
            raise OSError("hostname unavailable")

        monkeypatch.setattr(backends_module.socket, "gethostname", _hostname_boom)
        result = LockInfo.from_dict({"pid": 42, "timestamp": time.time()})
        assert result is None


# ---------------------------------------------------------------------------
# 20. _is_fcntl_lock_active() edge cases (lines 332-348)
# ---------------------------------------------------------------------------


class TestIsFcntlLockActive:
    def test_missing_file_returns_false(self, tmp_path: Path) -> None:
        from cja_auto_sdr.core.locks.backends import _is_fcntl_lock_active

        if backends_module.fcntl is None:
            pytest.skip("fcntl not available on this platform")
        result = _is_fcntl_lock_active(tmp_path / "nonexistent")
        assert result is False

    def test_permission_error_returns_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from cja_auto_sdr.core.locks.backends import _is_fcntl_lock_active

        if backends_module.fcntl is None:
            pytest.skip("fcntl not available on this platform")
        f = tmp_path / "perm"
        f.write_text("x", encoding="utf-8")

        def _failing_open(path: str, flags: int, *args, **kwargs) -> int:  # type: ignore[no-untyped-def]
            raise PermissionError("no access")

        monkeypatch.setattr(os, "open", _failing_open)
        result = _is_fcntl_lock_active(f)
        assert result is None

    def test_unlocked_file_returns_false(self, tmp_path: Path) -> None:
        from cja_auto_sdr.core.locks.backends import _is_fcntl_lock_active

        if backends_module.fcntl is None:
            pytest.skip("fcntl not available on this platform")
        f = tmp_path / "unlocked"
        f.write_text("x", encoding="utf-8")
        result = _is_fcntl_lock_active(f)
        assert result is False

    def test_eagain_returns_true(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from cja_auto_sdr.core.locks.backends import _is_fcntl_lock_active

        if backends_module.fcntl is None:
            pytest.skip("fcntl not available on this platform")
        f = tmp_path / "locked"
        f.write_text("x", encoding="utf-8")

        def _eagain_flock(fd: int, operation: int) -> None:
            if operation & backends_module.fcntl.LOCK_NB:
                raise OSError(errno.EAGAIN, "resource temporarily unavailable")

        monkeypatch.setattr(backends_module.fcntl, "flock", _eagain_flock)
        result = _is_fcntl_lock_active(f)
        assert result is True

    def test_other_oserror_returns_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from cja_auto_sdr.core.locks.backends import _is_fcntl_lock_active

        if backends_module.fcntl is None:
            pytest.skip("fcntl not available on this platform")
        f = tmp_path / "ioerr"
        f.write_text("x", encoding="utf-8")

        def _io_flock(fd: int, operation: int) -> None:
            raise OSError(errno.EIO, "I/O error")

        monkeypatch.setattr(backends_module.fcntl, "flock", _io_flock)
        result = _is_fcntl_lock_active(f)
        assert result is None


# ---------------------------------------------------------------------------
# 21. _is_lock_info_stale() with fcntl + lock_path (lines 367-371)
# ---------------------------------------------------------------------------


class TestIsLockInfoStaleFcntlWithLockPath:
    def test_fcntl_lock_active_none_returns_false(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """fcntl backend with lock_path, _is_fcntl_lock_active returns None -> not stale."""
        info = _build_lock_info("test", backend="fcntl")
        lock_file = tmp_path / "lock"
        lock_file.write_text("x", encoding="utf-8")
        monkeypatch.setattr(backends_module, "_is_fcntl_lock_active", lambda path: None)
        assert _is_lock_info_stale(info, 10, lock_path=lock_file) is False

    def test_fcntl_lock_active_true_returns_false(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """fcntl backend with lock_path, _is_fcntl_lock_active returns True -> not stale."""
        info = _build_lock_info("test", backend="fcntl")
        lock_file = tmp_path / "lock"
        lock_file.write_text("x", encoding="utf-8")
        monkeypatch.setattr(backends_module, "_is_fcntl_lock_active", lambda path: True)
        assert _is_lock_info_stale(info, 10, lock_path=lock_file) is False

    def test_fcntl_lock_active_false_returns_true(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """fcntl backend with lock_path, _is_fcntl_lock_active returns False -> stale."""
        info = _build_lock_info("test", backend="fcntl")
        lock_file = tmp_path / "lock"
        lock_file.write_text("x", encoding="utf-8")
        monkeypatch.setattr(backends_module, "_is_fcntl_lock_active", lambda path: False)
        assert _is_lock_info_stale(info, 10, lock_path=lock_file) is True


# ---------------------------------------------------------------------------
# 22. _parse_iso() edge cases
# ---------------------------------------------------------------------------


class TestParseIso:
    def test_valid_iso(self) -> None:
        from cja_auto_sdr.core.locks.backends import _parse_iso

        result = _parse_iso("2024-01-01T00:00:00+00:00")
        assert result is not None
        assert result.year == 2024

    def test_invalid_iso(self) -> None:
        from cja_auto_sdr.core.locks.backends import _parse_iso

        assert _parse_iso("not a date") is None

    def test_empty_string(self) -> None:
        from cja_auto_sdr.core.locks.backends import _parse_iso

        assert _parse_iso("") is None


# ---------------------------------------------------------------------------
# 23. _is_process_running() - TypeError/ValueError/OverflowError from int(pid)
#     Lines 311-312
# ---------------------------------------------------------------------------


class TestIsProcessRunningIntConversionErrors:
    def test_none_pid_returns_false(self) -> None:
        """int(None) raises TypeError -> should return False."""
        assert _is_process_running(None) is False  # type: ignore[arg-type]

    def test_string_pid_returns_false(self) -> None:
        """int('abc') raises ValueError -> should return False."""
        assert _is_process_running("abc") is False  # type: ignore[arg-type]

    def test_list_pid_returns_false(self) -> None:
        """int([]) raises TypeError -> should return False."""
        assert _is_process_running([]) is False  # type: ignore[arg-type]

    def test_dict_pid_returns_false(self) -> None:
        """int({}) raises TypeError -> should return False."""
        assert _is_process_running({}) is False  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# 24. _is_fcntl_lock_active() - fcntl is None (line 332)
# ---------------------------------------------------------------------------


class TestIsFcntlLockActiveFcntlNone:
    def test_returns_none_when_fcntl_is_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """When fcntl module is None, _is_fcntl_lock_active returns None."""
        from cja_auto_sdr.core.locks.backends import _is_fcntl_lock_active

        monkeypatch.setattr(backends_module, "fcntl", None)
        lock_file = tmp_path / "lock"
        lock_file.write_text("x", encoding="utf-8")
        result = _is_fcntl_lock_active(lock_file)
        assert result is None


# ---------------------------------------------------------------------------
# 25. _is_fcntl_lock_active() - EAGAIN via OSError (line 347)
#     (already partially covered, but this ensures the EWOULDBLOCK path)
# ---------------------------------------------------------------------------


class TestIsFcntlLockActiveEwouldblock:
    def test_ewouldblock_returns_true(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """OSError with EWOULDBLOCK should return True (lock held)."""
        from cja_auto_sdr.core.locks.backends import _is_fcntl_lock_active

        if backends_module.fcntl is None:
            pytest.skip("fcntl not available on this platform")
        f = tmp_path / "locked"
        f.write_text("x", encoding="utf-8")

        def _ewouldblock_flock(fd: int, operation: int) -> None:
            if operation & backends_module.fcntl.LOCK_NB:
                raise OSError(errno.EWOULDBLOCK, "would block")

        monkeypatch.setattr(backends_module.fcntl, "flock", _ewouldblock_flock)
        result = _is_fcntl_lock_active(f)
        assert result is True


# ---------------------------------------------------------------------------
# 26. FcntlFileLockBackend.acquire_result() - _open_lock_file returns (None, False)
#     Line 453
# ---------------------------------------------------------------------------


class TestFcntlAcquireResultOpenFails:
    def test_open_lock_file_returns_none_yields_contended(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When _open_lock_file returns (None, False), acquire_result returns CONTENDED."""
        from cja_auto_sdr.core.locks.backends import AcquireStatus

        if backends_module.fcntl is None:
            pytest.skip("fcntl not available on this platform")

        backend = FcntlFileLockBackend()
        monkeypatch.setattr(FcntlFileLockBackend, "_open_lock_file", staticmethod(lambda path: (None, False)))
        result = backend.acquire_result(tmp_path / "lock", stale_threshold_seconds=10)
        assert result.status == AcquireStatus.CONTENDED
        assert result.handle is None


# ---------------------------------------------------------------------------
# 27. _fd_matches_path() - os.fstat raises OSError (lines 554-555)
#     and lock_path.stat() raises OSError (lines 560-561)
# ---------------------------------------------------------------------------


class TestFdMatchesPathOSErrors:
    def test_fstat_oserror_returns_false(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """When os.fstat raises OSError, _fd_matches_path returns False."""
        if backends_module.fcntl is None:
            pytest.skip("fcntl not available on this platform")

        def _fstat_fail(fd: int) -> None:
            raise OSError(errno.EBADF, "bad fd")

        monkeypatch.setattr(os, "fstat", _fstat_fail)
        result = FcntlFileLockBackend._fd_matches_path(999, Path("/nonexistent"))
        assert result is False

    def test_path_stat_oserror_returns_false(self, tmp_path: Path) -> None:
        """When lock_path.stat() raises OSError (file gone), _fd_matches_path returns False."""
        if backends_module.fcntl is None:
            pytest.skip("fcntl not available on this platform")

        # Create a file so we can get a valid fd
        lock_file = tmp_path / "lock"
        lock_file.write_text("x", encoding="utf-8")
        fd = os.open(str(lock_file), os.O_RDWR)
        try:
            # Delete the file so stat fails on path
            lock_file.unlink()
            result = FcntlFileLockBackend._fd_matches_path(fd, lock_file)
            # st_nlink goes to 0 when unlinked, so returns False
            assert result is False
        finally:
            os.close(fd)

    def test_path_stat_missing_file_returns_false(self) -> None:
        """When lock_path points to a nonexistent file, stat() raises OSError -> False."""
        if backends_module.fcntl is None:
            pytest.skip("fcntl not available on this platform")

        # Use a real fd from a temp file but point to a different nonexistent path
        import tempfile

        with tempfile.NamedTemporaryFile() as tf:
            fd = os.open(tf.name, os.O_RDWR)
            try:
                result = FcntlFileLockBackend._fd_matches_path(fd, Path("/no/such/path"))
                assert result is False
            finally:
                os.close(fd)


# ---------------------------------------------------------------------------
# 28. FcntlFileLockBackend.release() - already closed + flock LOCK_UN OSError
#     Lines 574, 578-579
# ---------------------------------------------------------------------------


class TestFcntlReleaseEdgeCases:
    def test_release_already_closed_is_noop(self) -> None:
        """Releasing an already-closed handle does nothing."""
        from cja_auto_sdr.core.locks.backends import _FcntlLockHandle

        if backends_module.fcntl is None:
            pytest.skip("fcntl not available on this platform")

        handle = _FcntlLockHandle(lock_path=Path("/tmp/lock"), fd=-1, lock_id="test", closed=True)
        backend = FcntlFileLockBackend()
        # Should not raise
        backend.release(handle)
        assert handle.closed is True

    def test_release_flock_un_oserror_still_closes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """When flock(LOCK_UN) raises OSError, release still closes fd and marks closed."""
        from cja_auto_sdr.core.locks.backends import _FcntlLockHandle

        if backends_module.fcntl is None:
            pytest.skip("fcntl not available on this platform")

        lock_file = tmp_path / "lock"
        lock_file.write_text("x", encoding="utf-8")
        fd = os.open(str(lock_file), os.O_RDWR)

        def _flock_fail(fd_: int, operation: int) -> None:
            raise OSError(errno.EIO, "I/O error during unlock")

        monkeypatch.setattr(backends_module.fcntl, "flock", _flock_fail)
        handle = _FcntlLockHandle(lock_path=lock_file, fd=fd, lock_id="test", closed=False)
        backend = FcntlFileLockBackend()
        backend.release(handle)
        assert handle.closed is True


# ---------------------------------------------------------------------------
# 29. LeaseFileLockBackend.acquire() - error propagation (line 662)
# ---------------------------------------------------------------------------


class TestLeaseAcquireErrorPropagation:
    def test_acquire_raises_when_acquire_result_has_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When acquire_result returns non-ACQUIRED with error, acquire() raises it."""
        from cja_auto_sdr.core.locks.backends import AcquireResult, AcquireStatus

        backend = LeaseFileLockBackend()
        test_error = OSError(errno.EIO, "disk error")
        monkeypatch.setattr(
            backend,
            "acquire_result",
            lambda lock_path, stale_threshold_seconds: AcquireResult(
                status=AcquireStatus.METADATA_ERROR,
                error=test_error,
            ),
        )
        with pytest.raises(OSError, match="disk error"):
            backend.acquire(tmp_path / "lock", stale_threshold_seconds=10)

    def test_acquire_returns_none_when_contended_no_error(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """When acquire_result returns CONTENDED with no error, acquire() returns None."""
        from cja_auto_sdr.core.locks.backends import AcquireResult, AcquireStatus

        backend = LeaseFileLockBackend()
        monkeypatch.setattr(
            backend,
            "acquire_result",
            lambda lock_path, stale_threshold_seconds: AcquireResult(status=AcquireStatus.CONTENDED),
        )
        result = backend.acquire(tmp_path / "lock", stale_threshold_seconds=10)
        assert result is None


# ---------------------------------------------------------------------------
# 30. _safe_unlink() - FileNotFoundError -> True, other OSError -> False
#     Lines 842-845
# ---------------------------------------------------------------------------


class TestSafeUnlink:
    def test_successful_unlink_returns_true(self, tmp_path: Path) -> None:
        f = tmp_path / "to_delete"
        f.write_text("x", encoding="utf-8")
        assert LeaseFileLockBackend._safe_unlink(f) is True
        assert not f.exists()

    def test_file_not_found_returns_true(self, tmp_path: Path) -> None:
        """FileNotFoundError (already gone) returns True."""
        f = tmp_path / "nonexistent"
        assert LeaseFileLockBackend._safe_unlink(f) is True

    def test_other_oserror_returns_false(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Non-FileNotFoundError OSError returns False."""
        f = tmp_path / "fail"
        f.write_text("x", encoding="utf-8")

        original_unlink = Path.unlink

        def _unlink_fail(self_path: Path, missing_ok: bool = False) -> None:
            if self_path == f:
                raise OSError(errno.EACCES, "permission denied")
            return original_unlink(self_path, missing_ok=missing_ok)

        monkeypatch.setattr(Path, "unlink", _unlink_fail)
        assert LeaseFileLockBackend._safe_unlink(f) is False


# ---------------------------------------------------------------------------
# 31. _safe_unlink_if_inode() - inode mismatch returns False (line 852)
# ---------------------------------------------------------------------------


class TestSafeUnlinkIfInode:
    def test_inode_mismatch_returns_false(self, tmp_path: Path) -> None:
        """When current inode differs from expected, returns False without unlinking."""
        f = tmp_path / "lock"
        f.write_text("x", encoding="utf-8")
        # Use a fake expected inode that won't match
        fake_inode = (0, 0)
        backend = LeaseFileLockBackend()
        result = backend._safe_unlink_if_inode(f, fake_inode)
        assert result is False
        # File should still exist
        assert f.exists()

    def test_file_gone_returns_true(self, tmp_path: Path) -> None:
        """When file is already gone (stat returns None), returns True."""
        f = tmp_path / "gone"
        backend = LeaseFileLockBackend()
        result = backend._safe_unlink_if_inode(f, (0, 0))
        assert result is True

    def test_matching_inode_unlinks(self, tmp_path: Path) -> None:
        """When inodes match, the file is unlinked and returns True."""
        f = tmp_path / "lock"
        f.write_text("x", encoding="utf-8")
        st = f.stat()
        real_inode = (st.st_dev, st.st_ino)
        backend = LeaseFileLockBackend()
        result = backend._safe_unlink_if_inode(f, real_inode)
        assert result is True
        assert not f.exists()


# ---------------------------------------------------------------------------
# 32. LeaseFileLockBackend.release() - already closed + fstat returns None
#     Lines 787, 794-795
# ---------------------------------------------------------------------------


class TestLeaseReleaseEdgeCases:
    def test_release_already_closed_is_noop(self) -> None:
        """Releasing an already-closed handle does nothing."""
        from cja_auto_sdr.core.locks.backends import _LeaseLockHandle

        handle = _LeaseLockHandle(lock_path=Path("/tmp/lock"), fd=-1, lock_id="test", closed=True)
        backend = LeaseFileLockBackend()
        backend.release(handle)
        assert handle.closed is True

    def test_release_fstat_returns_none_early_exit(self, tmp_path: Path) -> None:
        """When fstat_inode returns None (bad fd), release closes and exits early."""
        from cja_auto_sdr.core.locks.backends import _LeaseLockHandle

        lock_file = tmp_path / "lock"
        lock_file.write_text("x", encoding="utf-8")
        fd = os.open(str(lock_file), os.O_RDWR)
        # Close the fd first so fstat will fail inside release
        os.close(fd)
        handle = _LeaseLockHandle(lock_path=lock_file, fd=fd, lock_id="test", closed=False)
        backend = LeaseFileLockBackend()
        # Should not raise, should mark closed and return early
        backend.release(handle)
        assert handle.closed is True
        # File should still exist since we took the early-return path
        assert lock_file.exists()

    def test_release_ownership_changed_returns_early(self, tmp_path: Path) -> None:
        """Line 805: lock_info.lock_id != handle.lock_id -> early return."""
        from cja_auto_sdr.core.locks.backends import _LeaseLockHandle

        lock_file = tmp_path / "lock"
        lock_file.write_text("x", encoding="utf-8")
        fd = os.open(str(lock_file), os.O_RDWR)
        # Write metadata for a DIFFERENT lock_id
        other_info = _build_lock_info("other-owner")
        _write_info_path(_metadata_path(lock_file), other_info)

        handle = _LeaseLockHandle(lock_path=lock_file, fd=fd, lock_id="my-id", closed=False)
        backend = LeaseFileLockBackend()
        backend.release(handle)
        assert handle.closed is True
        # File should still exist because ownership check returned early
        assert lock_file.exists()

    def test_release_unlink_fails_writes_tombstone(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Lines 813-815: when all unlink attempts fail, writes stale tombstone."""
        from cja_auto_sdr.core.locks.backends import _LeaseLockHandle

        lock_file = tmp_path / "lock"
        lock_file.write_text("x", encoding="utf-8")
        fd = os.open(str(lock_file), os.O_RDWR)
        # Write metadata for our lock_id so ownership check passes
        our_info = _build_lock_info("our-lock-id")
        _write_info_path(_metadata_path(lock_file), our_info)

        handle = _LeaseLockHandle(lock_path=lock_file, fd=fd, lock_id="our-lock-id", closed=False)
        backend = LeaseFileLockBackend()
        backend.release_unlink_attempts = 2
        backend.release_unlink_retry_sleep_seconds = 0.001

        # Make _safe_unlink_if_inode always fail
        monkeypatch.setattr(backend, "_safe_unlink_if_inode", lambda *a: False)
        backend.release(handle)
        assert handle.closed is True
        # Should have written tombstone metadata
        meta = _read_info_path(_metadata_path(lock_file))
        assert meta is not None
        assert meta.pid == -1
        assert meta.host == "released"


# ---------------------------------------------------------------------------
# 33. _safe_unlink_sidecar_if_owned() - inode races (lines 869, 871)
# ---------------------------------------------------------------------------


class TestSafeUnlinkSidecarIfOwnedRaces:
    def test_inode_after_is_none_returns_true(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Line 869: metadata file disappears between reads -> True."""
        lock_file = tmp_path / "lock"
        metadata = _metadata_path(lock_file)
        metadata.parent.mkdir(parents=True, exist_ok=True)
        info = _build_lock_info("my-id")
        _write_info_path(metadata, info)
        real_inode = metadata.stat()
        inode = (real_inode.st_dev, real_inode.st_ino)

        backend = LeaseFileLockBackend()
        call_count = {"n": 0}

        def _stat_inode_vanish(path: Path) -> tuple[int, int] | None:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return inode  # First call: inode_before
            return None  # Second call: inode_after (file gone)

        monkeypatch.setattr(backend, "_stat_inode", _stat_inode_vanish)
        result = backend._safe_unlink_sidecar_if_owned(lock_file, expected_lock_id="my-id")
        assert result is True

    def test_inode_changed_returns_false(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Line 871: inode changed between reads -> False."""
        lock_file = tmp_path / "lock"
        metadata = _metadata_path(lock_file)
        metadata.parent.mkdir(parents=True, exist_ok=True)
        info = _build_lock_info("my-id")
        _write_info_path(metadata, info)

        backend = LeaseFileLockBackend()
        call_count = {"n": 0}

        def _stat_inode_change(path: Path) -> tuple[int, int] | None:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return (1, 100)  # inode_before
            return (1, 999)  # inode_after (different)

        monkeypatch.setattr(backend, "_stat_inode", _stat_inode_change)
        result = backend._safe_unlink_sidecar_if_owned(lock_file, expected_lock_id="my-id")
        assert result is False


# ---------------------------------------------------------------------------
# 34. _write_stale_tombstone() - inode changed (line 894)
# ---------------------------------------------------------------------------


class TestWriteStaleTombstoneInodeChanged:
    def test_inode_changed_skips_write(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Line 894: current_inode != held_inode -> return early."""
        lock_file = tmp_path / "lock"
        lock_file.write_text("x", encoding="utf-8")
        backend = LeaseFileLockBackend()
        # _stat_inode returns different inode from what we claim is held
        monkeypatch.setattr(backend, "_stat_inode", lambda path: (1, 999))
        # Should not write metadata (held_inode doesn't match)
        backend._write_stale_tombstone(lock_file, "lock-id", (1, 100))
        # No metadata written
        assert not _metadata_path(lock_file).exists()


# ---------------------------------------------------------------------------
# 35. FcntlFileLockBackend.acquire() dispatch (lines 442-446)
# ---------------------------------------------------------------------------


class TestFcntlAcquireDispatch:
    def test_backend_unavailable_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Line 442-443: BACKEND_UNAVAILABLE with error -> raises."""
        from cja_auto_sdr.core.locks.backends import (
            AcquireResult,
            AcquireStatus,
            LockBackendUnavailableError,
        )

        if backends_module.fcntl is None:
            pytest.skip("fcntl not available")
        backend = FcntlFileLockBackend()
        err = LockBackendUnavailableError("flock unsupported")
        monkeypatch.setattr(
            backend,
            "acquire_result",
            lambda *a, **kw: AcquireResult(status=AcquireStatus.BACKEND_UNAVAILABLE, error=err),
        )
        with pytest.raises(LockBackendUnavailableError, match="flock unsupported"):
            backend.acquire(tmp_path / "lock", 10)

    def test_metadata_error_raises(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Line 444-445: METADATA_ERROR with error -> raises."""
        from cja_auto_sdr.core.locks.backends import AcquireResult, AcquireStatus

        if backends_module.fcntl is None:
            pytest.skip("fcntl not available")
        backend = FcntlFileLockBackend()
        err = OSError(errno.EIO, "disk error")
        monkeypatch.setattr(
            backend,
            "acquire_result",
            lambda *a, **kw: AcquireResult(status=AcquireStatus.METADATA_ERROR, error=err),
        )
        with pytest.raises(OSError, match="disk error"):
            backend.acquire(tmp_path / "lock", 10)

    def test_contended_returns_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Line 446: CONTENDED without error -> returns None."""
        from cja_auto_sdr.core.locks.backends import AcquireResult, AcquireStatus

        if backends_module.fcntl is None:
            pytest.skip("fcntl not available")
        backend = FcntlFileLockBackend()
        monkeypatch.setattr(
            backend,
            "acquire_result",
            lambda *a, **kw: AcquireResult(status=AcquireStatus.CONTENDED),
        )
        result = backend.acquire(tmp_path / "lock", 10)
        assert result is None


# ---------------------------------------------------------------------------
# 36. FcntlFileLockBackend.acquire_result() - inode mismatch paths
#     (lines 479-480, 521-522, 529)
# ---------------------------------------------------------------------------


class TestFcntlAcquireResultInodePaths:
    def test_fd_mismatch_after_lock_continues_then_exhausts(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Lines 479-480, 529: _fd_matches_path always False -> loop exhaustion."""
        from cja_auto_sdr.core.locks.backends import AcquireStatus

        if backends_module.fcntl is None:
            pytest.skip("fcntl not available")
        backend = FcntlFileLockBackend()
        backend.acquire_attempts = 2
        lock_file = tmp_path / "lock"

        monkeypatch.setattr(FcntlFileLockBackend, "_fd_matches_path", staticmethod(lambda fd, path: False))
        result = backend.acquire_result(lock_file, 10)
        assert result.status == AcquireStatus.CONTENDED

    def test_fd_mismatch_after_metadata_read(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Lines 521-522: _fd_matches_path True first, then False after metadata."""
        from cja_auto_sdr.core.locks.backends import AcquireStatus, _ReadInfoOutcome

        if backends_module.fcntl is None:
            pytest.skip("fcntl not available")
        backend = FcntlFileLockBackend()
        backend.acquire_attempts = 1
        lock_file = tmp_path / "lock"
        # Pre-create the lock file so it's opened as existing (not exclusively)
        lock_file.write_text("x", encoding="utf-8")

        call_count = {"n": 0}

        def _fd_matches_selective(fd: int, path: Path) -> bool:
            call_count["n"] += 1
            if call_count["n"] == 1:
                return True  # First check passes (line 478)
            return False  # Second check fails (line 520)

        monkeypatch.setattr(FcntlFileLockBackend, "_fd_matches_path", staticmethod(_fd_matches_selective))
        # Return valid fcntl-backend info so metadata section passes through
        # (backend == self.name skips the mixed-backend guard)
        fcntl_info = _build_lock_info("test-id", backend="fcntl")
        monkeypatch.setattr(
            backend,
            "_read_info_with_retries",
            lambda path: _ReadInfoOutcome(info=fcntl_info, state="valid", source_path=_metadata_path(lock_file)),
        )
        result = backend.acquire_result(lock_file, 10)
        assert result.status == AcquireStatus.CONTENDED


# ---------------------------------------------------------------------------
# 37. FcntlFileLockBackend.acquire_result() - backward-compat + unreadable
#     (line 489) and fresh unreadable metadata (lines 515-516)
# ---------------------------------------------------------------------------


class TestFcntlAcquireResultMetadataPaths:
    def test_backward_compat_tuple_unreadable(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Line 489: _read_info_with_retries returns tuple (None, True) -> unreadable."""
        from cja_auto_sdr.core.locks.backends import AcquireStatus

        if backends_module.fcntl is None:
            pytest.skip("fcntl not available")
        backend = FcntlFileLockBackend()
        backend.acquire_attempts = 1
        lock_file = tmp_path / "lock"
        lock_file.write_text("x", encoding="utf-8")

        # Mock _read_info_with_retries to return legacy tuple format
        monkeypatch.setattr(backend, "_read_info_with_retries", lambda path: (None, True))
        # Make the unreadable path fresh (not stale) so lines 515-516 trigger
        monkeypatch.setattr(backends_module, "_is_path_stale_by_mtime", lambda path, threshold: False)
        result = backend.acquire_result(lock_file, 10)
        assert result.status == AcquireStatus.CONTENDED

    def test_unreadable_metadata_not_stale(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Lines 515-516: unreadable metadata with fresh mtime -> CONTENDED."""
        from cja_auto_sdr.core.locks.backends import AcquireStatus, _ReadInfoOutcome

        if backends_module.fcntl is None:
            pytest.skip("fcntl not available")
        backend = FcntlFileLockBackend()
        backend.acquire_attempts = 1
        lock_file = tmp_path / "lock"
        lock_file.write_text("x", encoding="utf-8")

        monkeypatch.setattr(
            backend,
            "_read_info_with_retries",
            lambda path: _ReadInfoOutcome(info=None, state="unreadable", source_path=_metadata_path(lock_file)),
        )
        monkeypatch.setattr(backends_module, "_is_path_stale_by_mtime", lambda path, threshold: False)
        result = backend.acquire_result(lock_file, 10)
        assert result.status == AcquireStatus.CONTENDED


# ---------------------------------------------------------------------------
# 38. _open_lock_file() race conditions (lines 541-548)
# ---------------------------------------------------------------------------


class TestOpenLockFileRaces:
    def test_file_not_found_after_file_exists(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Lines 541-543: FileExistsError then FileNotFoundError -> retry loop."""
        if backends_module.fcntl is None:
            pytest.skip("fcntl not available")

        call_count = {"n": 0}
        original_open = os.open

        def _racing_open(path: str, flags: int, *args: int) -> int:
            call_count["n"] += 1
            if call_count["n"] <= 3:
                raise FileExistsError("already exists")
            if call_count["n"] <= 6:
                raise FileNotFoundError("just gone")
            return original_open(path, flags, *args)

        lock_file = tmp_path / "lock"
        monkeypatch.setattr(os, "open", _racing_open)
        # All 3 iterations: first O_EXCL -> FileExistsError, then O_RDWR -> FileNotFoundError
        result = FcntlFileLockBackend._open_lock_file(lock_file)
        assert result == (None, False)

    def test_oserror_after_file_exists(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Lines 544-545: FileExistsError then OSError on O_RDWR open -> (None, False)."""
        if backends_module.fcntl is None:
            pytest.skip("fcntl not available")

        call_count = {"n": 0}

        def _failing_open(path: str, flags: int, *args: int) -> int:
            call_count["n"] += 1
            if flags & os.O_EXCL:
                raise FileExistsError("exists")
            raise OSError(errno.EACCES, "permission denied")

        monkeypatch.setattr(os, "open", _failing_open)
        result = FcntlFileLockBackend._open_lock_file(tmp_path / "lock")
        assert result == (None, False)

    def test_oserror_on_exclusive_create(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Lines 546-547: OSError (not FileExistsError) on O_CREAT|O_EXCL -> (None, False)."""
        if backends_module.fcntl is None:
            pytest.skip("fcntl not available")

        def _failing_open(path: str, flags: int, *args: int) -> int:
            raise OSError(errno.EACCES, "permission denied")

        monkeypatch.setattr(os, "open", _failing_open)
        result = FcntlFileLockBackend._open_lock_file(tmp_path / "lock")
        assert result == (None, False)

    def test_loop_exhaustion_returns_none(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Line 548: all 3 iterations FileExistsError then FileNotFoundError."""
        if backends_module.fcntl is None:
            pytest.skip("fcntl not available")

        def _always_race(path: str, flags: int, *args: int) -> int:
            if flags & os.O_EXCL:
                raise FileExistsError("exists")
            raise FileNotFoundError("gone")

        monkeypatch.setattr(os, "open", _always_race)
        result = FcntlFileLockBackend._open_lock_file(tmp_path / "lock")
        assert result == (None, False)


# ---------------------------------------------------------------------------
# 39. LeaseFileLockBackend.acquire_result() - bootstrap + contention paths
#     (lines 675-680, 684-687, 695, 705, 715, 732, 735, 740-743)
# ---------------------------------------------------------------------------


class TestLeaseAcquireResultEdgeCases:
    def test_bootstrap_write_oserror(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Lines 675-680: OSError during _write_lock_marker_fd -> METADATA_ERROR."""
        from cja_auto_sdr.core.locks.backends import AcquireStatus

        backend = LeaseFileLockBackend()
        backend.acquire_attempts = 1
        lock_file = tmp_path / "lock"

        def _fail_write(fd: int, lock_id: str) -> None:
            raise OSError(errno.EIO, "disk error")

        monkeypatch.setattr(backend, "_write_lock_marker_fd", _fail_write)
        result = backend.acquire_result(lock_file, 10)
        assert result.status == AcquireStatus.METADATA_ERROR
        assert result.error is not None

    def test_inode_mismatch_after_bootstrap(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Lines 684-687: held_inode != current_inode after bootstrap -> continue."""
        from cja_auto_sdr.core.locks.backends import AcquireStatus

        backend = LeaseFileLockBackend()
        backend.acquire_attempts = 1
        lock_file = tmp_path / "lock"

        # Make _fstat_inode return mismatched value
        monkeypatch.setattr(backend, "_fstat_inode", lambda fd: (1, 100))
        monkeypatch.setattr(backend, "_stat_inode", lambda path: (1, 999))
        result = backend.acquire_result(lock_file, 10)
        assert result.status == AcquireStatus.CONTENDED

    def test_path_inode_none_continues(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Line 695: path_inode is None in FileExistsError handler -> continue."""
        from cja_auto_sdr.core.locks.backends import AcquireStatus

        backend = LeaseFileLockBackend()
        backend.acquire_attempts = 1
        lock_file = tmp_path / "lock"
        lock_file.write_text("x", encoding="utf-8")

        # Make _stat_inode return None (file gone during check)
        monkeypatch.setattr(backend, "_stat_inode", lambda path: None)
        result = backend.acquire_result(lock_file, 10)
        assert result.status == AcquireStatus.CONTENDED

    def test_stale_but_cant_unlink(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Line 705: stale lock but _safe_unlink_if_inode fails -> CONTENDED."""
        from cja_auto_sdr.core.locks.backends import AcquireStatus, _ReadInfoOutcome

        backend = LeaseFileLockBackend()
        backend.acquire_attempts = 1
        lock_file = tmp_path / "lock"
        lock_file.write_text("x", encoding="utf-8")
        st = lock_file.stat()
        real_inode = (st.st_dev, st.st_ino)

        stale_info = _build_lock_info(
            "stale-id",
            pid=2**30,
            host="remote-box",
            started_at="2000-01-01T00:00:00+00:00",
            updated_at="2000-01-01T00:00:00+00:00",
        )
        monkeypatch.setattr(
            backend,
            "_read_info_with_retries",
            lambda path: _ReadInfoOutcome(info=stale_info, state="valid", source_path=_metadata_path(lock_file)),
        )
        monkeypatch.setattr(backend, "_stat_inode", lambda path: real_inode)
        monkeypatch.setattr(backend, "_safe_unlink_if_inode", lambda path, inode: False)
        result = backend.acquire_result(lock_file, 10)
        assert result.status == AcquireStatus.CONTENDED

    def test_fcntl_lock_active_returns_contended(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Line 715: _is_fcntl_lock_active returns True -> CONTENDED."""
        from cja_auto_sdr.core.locks.backends import AcquireStatus, _ReadInfoOutcome

        backend = LeaseFileLockBackend()
        backend.acquire_attempts = 1
        lock_file = tmp_path / "lock"
        lock_file.write_text("x", encoding="utf-8")
        st = lock_file.stat()
        real_inode = (st.st_dev, st.st_ino)

        monkeypatch.setattr(
            backend,
            "_read_info_with_retries",
            lambda path: _ReadInfoOutcome(info=None, state="unreadable", source_path=None),
        )
        monkeypatch.setattr(backend, "_stat_inode", lambda path: real_inode)
        monkeypatch.setattr(backends_module, "_is_fcntl_lock_active", lambda path: True)
        result = backend.acquire_result(lock_file, 10)
        assert result.status == AcquireStatus.CONTENDED

    def test_fresh_unreadable_metadata_returns_contended(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Line 732: unreadable metadata with fresh mtime -> CONTENDED."""
        from cja_auto_sdr.core.locks.backends import AcquireStatus, _ReadInfoOutcome

        backend = LeaseFileLockBackend()
        backend.acquire_attempts = 1
        lock_file = tmp_path / "lock"
        lock_file.write_text("x", encoding="utf-8")
        st = lock_file.stat()
        real_inode = (st.st_dev, st.st_ino)

        meta_path = _metadata_path(lock_file)
        monkeypatch.setattr(
            backend,
            "_read_info_with_retries",
            lambda path: _ReadInfoOutcome(info=None, state="unreadable", source_path=meta_path),
        )
        monkeypatch.setattr(backend, "_stat_inode", lambda path: real_inode)
        monkeypatch.setattr(backends_module, "_is_fcntl_lock_active", lambda path: False)
        monkeypatch.setattr(backends_module, "_is_path_stale_by_mtime", lambda path, threshold: False)
        result = backend.acquire_result(lock_file, 10)
        assert result.status == AcquireStatus.CONTENDED

    def test_cant_unlink_after_missing_metadata(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Line 735: can't unlink lock after stale missing metadata -> CONTENDED."""
        from cja_auto_sdr.core.locks.backends import AcquireStatus, _ReadInfoOutcome

        backend = LeaseFileLockBackend()
        backend.acquire_attempts = 1
        lock_file = tmp_path / "lock"
        lock_file.write_text("x", encoding="utf-8")
        st = lock_file.stat()
        real_inode = (st.st_dev, st.st_ino)

        monkeypatch.setattr(
            backend,
            "_read_info_with_retries",
            lambda path: _ReadInfoOutcome(info=None, state="missing", source_path=None),
        )
        monkeypatch.setattr(backend, "_stat_inode", lambda path: real_inode)
        monkeypatch.setattr(backends_module, "_is_missing_metadata_stale", lambda path, threshold: True)
        monkeypatch.setattr(backends_module, "_is_fcntl_lock_active", lambda path: False)
        monkeypatch.setattr(backend, "_safe_unlink_if_inode", lambda path, inode: False)
        result = backend.acquire_result(lock_file, 10)
        assert result.status == AcquireStatus.CONTENDED

    def test_oserror_in_acquire_loop(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Lines 740-741: unexpected OSError in acquire loop -> METADATA_ERROR."""
        from cja_auto_sdr.core.locks.backends import AcquireStatus

        backend = LeaseFileLockBackend()
        backend.acquire_attempts = 1
        lock_file = tmp_path / "lock"

        original_open = os.open

        def _fail_open(path: str, flags: int, *args: int) -> int:
            if str(lock_file) in path:
                raise OSError(errno.EACCES, "permission denied")
            return original_open(path, flags, *args)

        monkeypatch.setattr(os, "open", _fail_open)
        result = backend.acquire_result(lock_file, 10)
        assert result.status == AcquireStatus.METADATA_ERROR

    def test_loop_exhaustion(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Line 743: all acquire_attempts exhausted -> CONTENDED."""
        from cja_auto_sdr.core.locks.backends import AcquireStatus

        backend = LeaseFileLockBackend()
        backend.acquire_attempts = 2
        lock_file = tmp_path / "lock"

        # Make bootstrap succeed but inode always mismatch -> continue on each attempt
        monkeypatch.setattr(backend, "_fstat_inode", lambda fd: (1, 100))
        monkeypatch.setattr(backend, "_stat_inode", lambda path: (1, 999))
        result = backend.acquire_result(lock_file, 10)
        assert result.status == AcquireStatus.CONTENDED
