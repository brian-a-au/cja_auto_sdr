from __future__ import annotations

import contextlib
import errno
import json
import os
import stat
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
# These follow symlinks and preserve existing file modes on overwrite.
# They use temp-file-and-rename only when that path preserves the success/fail
# semantics of a plain ``open(path, "w")`` call; otherwise they fall back to a
# direct write so compatibility wins over hardening.
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


def _file_supports_direct_overwrite(path: Path) -> bool:
    """Return True when a plain ``open(path, "w")`` overwrite should succeed."""
    return path.is_file() and os.access(path, os.W_OK)


def _should_use_atomic_compatible_write(target_path: Path, resolved: Path, temp_dir: Path) -> bool:
    """Use atomic replace only when it preserves plain open() success semantics."""
    if target_path.is_symlink():
        if resolved.exists():
            return _file_supports_direct_overwrite(resolved) and _directory_supports_atomic_replace(temp_dir)
        return _directory_supports_atomic_replace(temp_dir)

    if target_path.exists():
        return _file_supports_direct_overwrite(target_path) and _directory_supports_atomic_replace(temp_dir)

    return _directory_supports_atomic_replace(temp_dir)


def _write_direct_text_compatible(
    path: Path,
    content: str,
    *,
    encoding: str,
    file_mode: int | None = None,
) -> None:
    """Write directly to preserve edge-case ``open(..., "w")`` semantics."""
    with open(path, "w", encoding=encoding) as f:
        f.write(content)

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
    """Write JSON directly to preserve edge-case ``open(..., "w")`` semantics."""
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

    if file_mode is not None:
        os.chmod(path, file_mode)


def _apply_existing_mode(tmp_path: Path, resolved: Path, file_mode: int | None) -> None:
    """Copy the resolved destination's permission bits onto *tmp_path*.

    If *file_mode* is explicitly provided it takes precedence.  When the
    destination does not yet exist the temp file keeps the mode it was
    created with (umask-driven), matching ``open(..., "w")`` semantics.
    """
    if file_mode is not None:
        os.chmod(tmp_path, file_mode)
        return
    try:
        existing_mode = stat.S_IMODE(resolved.stat().st_mode)
        os.chmod(tmp_path, existing_mode)
    except FileNotFoundError:
        pass  # new file — keep umask-driven mode


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
    """Atomically write JSON while preserving symlink-following and file-mode semantics.

    Unlike :func:`write_json_atomic` this helper:

    * follows existing symlinks (writes through to the resolved target)
    * preserves the existing destination file's mode on overwrite
    * honours the process umask for new files (unless *file_mode* is given)
    * keeps stdlib ``json.dump(..., ensure_ascii=True)`` escaping by default
    """
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    resolved, temp_dir = _resolve_dest(target_path)
    if not _should_use_atomic_compatible_write(target_path, resolved, temp_dir):
        _write_direct_json_compatible(
            target_path,
            payload,
            indent=indent,
            ensure_ascii=ensure_ascii,
            sort_keys=sort_keys,
            default=default,
            file_mode=file_mode,
            trailing_newline=trailing_newline,
        )
        return target_path

    temp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = temp_dir / f".{resolved.name}.{uuid.uuid4().hex}.tmp"

    try:
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

        _apply_existing_mode(tmp_path, resolved, file_mode)
        os.replace(tmp_path, resolved)
        _fsync_directory(temp_dir)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp_path.unlink()
        raise

    return target_path


def write_text_atomic_compatible(
    path: str | Path,
    content: str,
    *,
    encoding: str = "utf-8",
    file_mode: int | None = None,
) -> Path:
    """Atomically write text while preserving symlink-following and file-mode semantics.

    This is the text-file counterpart of :func:`write_json_atomic_compatible`.
    """
    target_path = Path(path)
    target_path.parent.mkdir(parents=True, exist_ok=True)

    resolved, temp_dir = _resolve_dest(target_path)
    if not _should_use_atomic_compatible_write(target_path, resolved, temp_dir):
        _write_direct_text_compatible(target_path, content, encoding=encoding, file_mode=file_mode)
        return target_path

    temp_dir.mkdir(parents=True, exist_ok=True)
    tmp_path = temp_dir / f".{resolved.name}.{uuid.uuid4().hex}.tmp"

    try:
        with open(tmp_path, "w", encoding=encoding) as f:
            f.write(content)
            f.flush()
            os.fsync(f.fileno())

        _apply_existing_mode(tmp_path, resolved, file_mode)
        os.replace(tmp_path, resolved)
        _fsync_directory(temp_dir)
    except BaseException:
        with contextlib.suppress(OSError):
            tmp_path.unlink()
        raise

    return target_path
