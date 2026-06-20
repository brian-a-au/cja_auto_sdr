"""Local page ID registry for Notion integration (v2 schema).

Maps data view IDs to ``{page_id, database_row_id}`` records so re-runs can
update both the detail page and its matching row in the SDR Registry database.

Registry file: ``.notion_pages.json`` in the output directory.

Forward compatibility: v1 entries of the form ``{"<dv_id>": "<page_id>"}`` are
read transparently and rewritten into the v2 ``{"page_id": ..., "database_row_id": ...}``
dict on the next ``store_*`` call. v3.7.0 callers that only set ``page_id``
continue to work unchanged.

Concurrent batch workers calling ``store_page_id`` or ``store_database_row_id``
against the same registry file are serialized via an exclusive cross-process
lock on a sidecar ``.notion_pages.json.lock`` file.
"""

from __future__ import annotations

import json
from contextlib import contextmanager
from pathlib import Path
from typing import TypedDict

from cja_auto_sdr.core.json_io import write_json_atomic_compatible

REGISTRY_FILENAME = ".notion_pages.json"
_LOCK_SUFFIX = ".lock"


class RegistryEntry(TypedDict):
    page_id: str | None
    database_row_id: str | None


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

        import msvcrt  # Windows
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


def _coerce_entry(raw: object) -> RegistryEntry:
    """Read v1 string entries OR v2 dict entries; always return a v2 RegistryEntry."""
    if isinstance(raw, str):
        return {"page_id": raw, "database_row_id": None}
    if isinstance(raw, dict):
        return {
            "page_id": raw.get("page_id"),
            "database_row_id": raw.get("database_row_id"),
        }
    return {"page_id": None, "database_row_id": None}


def load_registry(path: Path) -> dict[str, RegistryEntry]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError, OSError, UnicodeDecodeError:
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): _coerce_entry(v) for k, v in data.items()}


def save_registry(path: Path, registry: dict[str, RegistryEntry]) -> None:
    write_json_atomic_compatible(
        path,
        registry,
        indent=2,
        ensure_ascii=False,
        trailing_newline=False,
    )


def lookup_page_id(registry_path: Path, data_view_id: str) -> str | None:
    return load_registry(registry_path).get(data_view_id, {}).get("page_id")


def lookup_database_row_id(registry_path: Path, data_view_id: str) -> str | None:
    return load_registry(registry_path).get(data_view_id, {}).get("database_row_id")


def _store_field(registry_path: Path, data_view_id: str, field: str, value: str | None) -> None:
    with _exclusive_registry_lock(registry_path):
        registry = load_registry(registry_path)
        entry: RegistryEntry = registry.get(
            data_view_id,
            {"page_id": None, "database_row_id": None},
        )
        entry[field] = value  # type: ignore[literal-required]
        registry[data_view_id] = entry
        save_registry(registry_path, registry)


def store_page_id(registry_path: Path, data_view_id: str, page_id: str) -> None:
    """Atomically update the registry's page_id for this data view."""
    _store_field(registry_path, data_view_id, "page_id", page_id)


def store_database_row_id(
    registry_path: Path,
    data_view_id: str,
    database_row_id: str,
) -> None:
    """Atomically update the registry's database_row_id for this data view."""
    _store_field(registry_path, data_view_id, "database_row_id", database_row_id)
