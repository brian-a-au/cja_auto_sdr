from __future__ import annotations

import contextlib
import errno
import functools
import json
import os
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

_DIRECTORY_FSYNC_BEST_EFFORT_ERRNOS = {
    errno.EACCES,
    errno.EBADF,
    errno.EINVAL,
    errno.EPERM,
    getattr(errno, "ENOTSUP", errno.EINVAL),
}


def _reject_symlink_destination(target_path: Path) -> None:
    """Disallow replacing an existing symlink with atomic rename semantics."""
    if target_path.is_symlink():
        raise OSError(errno.ELOOP, "Refusing to atomically replace symlink destination", str(target_path))


def _fsync_directory(directory: Path) -> None:
    """Best-effort directory fsync for rename durability after power loss."""
    flags = os.O_RDONLY
    if hasattr(os, "O_DIRECTORY"):
        flags |= os.O_DIRECTORY

    dir_fd: int | None = None
    try:
        dir_fd = os.open(directory, flags)
        os.fsync(dir_fd)
    except OSError as exc:
        if exc.errno not in _DIRECTORY_FSYNC_BEST_EFFORT_ERRNOS:
            raise
    finally:
        if dir_fd is not None:
            os.close(dir_fd)


def write_json_atomic(
    path: str | Path,
    payload: Any,
    *,
    indent: int | None = 2,
    ensure_ascii: bool = True,
    sort_keys: bool = False,
    default: Callable[[Any], Any] | None = None,
    file_mode: int | None = None,
    trailing_newline: bool = False,
) -> Path:
    """Persist JSON atomically, rejecting existing target symlinks and fsyncing the parent dir."""
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)
    _reject_symlink_destination(target_path)
    tmp_path = target_path.with_name(f".{target_path.name}.{uuid.uuid4().hex}.tmp")
    open_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    create_mode = file_mode if file_mode is not None else 0o666

    try:
        fd = os.open(tmp_path, open_flags, create_mode)
        try:
            if file_mode is not None and hasattr(os, "fchmod"):
                os.fchmod(fd, file_mode)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                fd = -1
                json.dump(
                    payload,
                    f,
                    indent=indent,
                    ensure_ascii=ensure_ascii,
                    sort_keys=sort_keys,
                    default=default,
                )
                if trailing_newline:
                    f.write("\n")
                f.flush()
                os.fsync(f.fileno())
        finally:
            if fd != -1:
                os.close(fd)

        os.replace(tmp_path, target_path)
        _fsync_directory(target_path.parent)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp_path.unlink()
        raise

    return target_path


# ---------------------------------------------------------------------------
# Compatibility-preserving atomic helpers (v3.5.7)
# ---------------------------------------------------------------------------
# These preserve ``open(path, "w")`` overwrite semantics for existing files by
# writing through the existing inode directly, including symlink-following.
# For create-new paths they still use temp-file-and-rename so new artifacts get
# durable atomic creation without silently changing overwrite-visible behavior.
# ---------------------------------------------------------------------------


def _resolve_dest(target_path: Path) -> tuple[Path, Path]:
    """Resolve a possibly-symlinked destination and its parent directory.

    Returns ``(resolved_path, temp_dir)`` where *temp_dir* is the parent of
    the resolved target so the temp file lives on the same filesystem.
    """
    if target_path.is_symlink():
        resolved = target_path.resolve()
        return resolved, resolved.parent
    return target_path, target_path.parent


def _directory_supports_atomic_replace(directory: Path) -> bool:
    """Return True when *directory* can accept temp-file creation and replace."""
    return directory.exists() and os.access(directory, os.W_OK | os.X_OK)


def _compatible_tmp_path(directory: Path) -> Path:
    """Return a short temp-file path that fits even when target names are near NAME_MAX."""
    return directory / f".{uuid.uuid4().hex}.tmp"


def _cleanup_tmp_path(tmp_path: Path) -> None:
    """Best-effort temp-file cleanup for compatibility helper fallbacks/errors."""
    with contextlib.suppress(OSError):
        tmp_path.unlink()


def _target_exists_for_compatible_write(target_path: Path, resolved: Path) -> bool:
    """Return True when the effective destination already exists."""
    if target_path.is_symlink():
        return resolved.exists()
    return target_path.exists()


def _write_direct_text_compatible(
    path: Path,
    content: str,
    *,
    encoding: str,
    file_mode: int | None = None,
) -> None:
    """Write directly to preserve inode-backed overwrite semantics."""
    with open(path, "w", encoding=encoding) as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())

    if file_mode is not None:
        os.chmod(path, file_mode)


def _write_direct_json_compatible(
    path: Path,
    payload: Any,
    *,
    indent: int | None,
    ensure_ascii: bool,
    sort_keys: bool,
    default: Callable[[Any], Any] | None,
    file_mode: int | None,
    trailing_newline: bool,
) -> None:
    """Write JSON directly to preserve inode-backed overwrite semantics."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            payload,
            f,
            indent=indent,
            ensure_ascii=ensure_ascii,
            sort_keys=sort_keys,
            default=default,
        )
        if trailing_newline:
            f.write("\n")
        f.flush()
        os.fsync(f.fileno())

    if file_mode is not None:
        os.chmod(path, file_mode)


def _stage_json_write(
    tmp_path: Path,
    payload: Any,
    *,
    indent: int | None,
    ensure_ascii: bool,
    sort_keys: bool,
    default: Callable[[Any], Any] | None,
    trailing_newline: bool,
) -> None:
    """Write JSON content to a staged temp file and fsync it."""
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(
            payload,
            f,
            indent=indent,
            ensure_ascii=ensure_ascii,
            sort_keys=sort_keys,
            default=default,
        )
        if trailing_newline:
            f.write("\n")
        f.flush()
        os.fsync(f.fileno())


def _stage_text_write(tmp_path: Path, content: str, *, encoding: str) -> None:
    """Write text content to a staged temp file and fsync it."""
    with open(tmp_path, "w", encoding=encoding) as f:
        f.write(content)
        f.flush()
        os.fsync(f.fileno())


def _write_new_atomic_compatible(
    *,
    target_path: Path,
    resolved: Path,
    temp_dir: Path,
    file_mode: int | None,
    direct_write: Callable[[], None],
    stage_write: Callable[[Path], None],
) -> Path:
    """Atomically create a new compatible destination when the parent allows it."""
    if not _directory_supports_atomic_replace(temp_dir):
        direct_write()
        return target_path

    tmp_path = _compatible_tmp_path(temp_dir)

    try:
        stage_write(tmp_path)
        if file_mode is not None:
            os.chmod(tmp_path, file_mode)
        os.replace(tmp_path, resolved)
        _fsync_directory(temp_dir)
    except BaseException:
        _cleanup_tmp_path(tmp_path)
        raise

    return target_path


def write_json_atomic_compatible(
    path: str | Path,
    payload: Any,
    *,
    indent: int | None = 2,
    ensure_ascii: bool = True,
    sort_keys: bool = False,
    default: Callable[[Any], Any] | None = None,
    file_mode: int | None = None,
    trailing_newline: bool = True,
) -> Path:
    """Write JSON compatibly, preserving overwrite-visible path semantics.

    Unlike :func:`write_json_atomic` this helper:

    * follows existing symlinks (writes through to the resolved target)
    * preserves the existing destination inode on overwrite
    * honours the process umask for new files (unless *file_mode* is given)
    * keeps stdlib ``json.dump(..., ensure_ascii=True)`` escaping by default
    * uses temp-file-and-replace only for create-new paths where that does not
      change existing overwrite semantics
    """
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    resolved, temp_dir = _resolve_dest(target_path)

    def direct_write() -> None:
        _write_direct_json_compatible(
            path=target_path,
            payload=payload,
            indent=indent,
            ensure_ascii=ensure_ascii,
            sort_keys=sort_keys,
            default=default,
            file_mode=file_mode,
            trailing_newline=trailing_newline,
        )

    if _target_exists_for_compatible_write(target_path, resolved):
        direct_write()
        return target_path

    return _write_new_atomic_compatible(
        target_path=target_path,
        resolved=resolved,
        temp_dir=temp_dir,
        file_mode=file_mode,
        direct_write=direct_write,
        stage_write=lambda tmp_path: _stage_json_write(
            tmp_path,
            payload,
            indent=indent,
            ensure_ascii=ensure_ascii,
            sort_keys=sort_keys,
            default=default,
            trailing_newline=trailing_newline,
        ),
    )


def write_text_atomic_compatible(
    path: str | Path,
    content: str,
    *,
    encoding: str = "utf-8",
    file_mode: int | None = None,
) -> Path:
    """Write text compatibly, preserving overwrite-visible path semantics.

    This is the text-file counterpart of :func:`write_json_atomic_compatible`.
    """
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    resolved, temp_dir = _resolve_dest(target_path)

    def direct_write() -> None:
        _write_direct_text_compatible(
            path=target_path,
            content=content,
            encoding=encoding,
            file_mode=file_mode,
        )

    if _target_exists_for_compatible_write(target_path, resolved):
        direct_write()
        return target_path

    return _write_new_atomic_compatible(
        target_path=target_path,
        resolved=resolved,
        temp_dir=temp_dir,
        file_mode=file_mode,
        direct_write=direct_write,
        stage_write=lambda tmp_path: _stage_text_write(tmp_path, content, encoding=encoding),
    )


# ---------------------------------------------------------------------------
# Process-local parse cache (v3.11.2)
# ---------------------------------------------------------------------------
# Memoizes JSON parses keyed by (path, mtime, size) so repeated reads of the
# same on-disk snapshot within a process (e.g. org-report trending window
# scans and cache-prune metadata loads) skip redundant I/O + json.loads work.
# Callers MUST treat the returned object as read-only: it is shared across
# every caller that hits the same cache key.
# ---------------------------------------------------------------------------


@functools.lru_cache(maxsize=256)
def _load_json_cached_by_stat(path: str, mtime_ns: int, size: int) -> dict:  # noqa: ARG001 — cache key components
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_json_cached(path) -> dict:
    """Parse a JSON file, memoized by (path, mtime, size).

    The returned object is shared across callers and MUST NOT be mutated.
    """
    st = os.stat(path)
    return _load_json_cached_by_stat(str(path), st.st_mtime_ns, st.st_size)


# expose cache_clear for tests
load_json_cached.cache_clear = _load_json_cached_by_stat.cache_clear
