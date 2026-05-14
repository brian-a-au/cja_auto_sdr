"""Local page ID registry for Notion integration.

Maps data view IDs to Notion page IDs so re-runs update existing pages.
Registry file: .notion_pages.json in the output directory.
"""

from __future__ import annotations

import json
from pathlib import Path

from cja_auto_sdr.core.json_io import write_json_atomic_compatible

REGISTRY_FILENAME = ".notion_pages.json"


def get_registry_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / REGISTRY_FILENAME


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
    registry = load_registry(registry_path)
    registry[data_view_id] = page_id
    save_registry(registry_path, registry)
