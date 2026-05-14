"""Local page ID registry for Notion integration.

Maps data view IDs to Notion page IDs so re-runs update existing pages.
Registry file: .notion_pages.json in the output directory.

Concurrent batch workers calling :func:`store_page_id` against the same
registry file are serialized via an ``fcntl.flock`` exclusive lock on a
sidecar ``.notion_pages.json.lock`` file. The lock wraps the entire
read-modify-write sequence so two workers cannot clobber each other's entries.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path

from cja_auto_sdr.core.json_io import write_json_atomic_compatible

REGISTRY_FILENAME = ".notion_pages.json"
_LOCK_SUFFIX = ".lock"


def get_registry_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / REGISTRY_FILENAME


def _lock_path_for(registry_path: Path) -> Path:
    return registry_path.with_name(registry_path.name + _LOCK_SUFFIX)


@contextmanager
def _exclusive_registry_lock(registry_path: Path):
    """Serialize concurrent read-modify-write on the registry.

    Uses ``fcntl.flock`` on POSIX and ``msvcrt.locking`` on Windows against a
    sidecar lock file, so process-pool workers on either platform cannot
    clobber each other's updates. The package is declared OS-independent, so
    both paths must provide real cross-process locking.
    """
    lock_path = _lock_path_for(registry_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)

    fd = lock_path.open("a+")
    try:
        try:
            import fcntl  # POSIX

            fcntl.flock(fd.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fd.fileno(), fcntl.LOCK_UN)
            return
        except ImportError:
            pass

        # Windows path: msvcrt.locking takes an exclusive byte-range lock and
        # blocks until acquired (LK_LOCK retries internally; loop in case of
        # the documented "lock violation" raise after retries exhaust).
        import msvcrt
        import time

        fd.seek(0)
        while True:
            try:
                msvcrt.locking(fd.fileno(), msvcrt.LK_LOCK, 1)
                break
            except OSError:
                time.sleep(0.05)
        try:
            yield
        finally:
            fd.seek(0)
            msvcrt.locking(fd.fileno(), msvcrt.LK_UNLCK, 1)
    finally:
        fd.close()


def load_registry(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError, OSError:
        return {}


def save_registry(path: Path, registry: dict[str, str]) -> None:
    write_json_atomic_compatible(
        path,
        registry,
        indent=2,
        ensure_ascii=False,
        trailing_newline=False,
    )


def lookup_page_id(registry_path: Path, data_view_id: str) -> str | None:
    return load_registry(registry_path).get(data_view_id)


def store_page_id(registry_path: Path, data_view_id: str, page_id: str) -> None:
    """Atomically update the registry under an exclusive cross-process lock."""
    with _exclusive_registry_lock(registry_path):
        registry = load_registry(registry_path)
        registry[data_view_id] = page_id
        save_registry(registry_path, registry)
