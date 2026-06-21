"""Registry v2 (dict entry) migration + round-trip tests."""

from __future__ import annotations

import json
from pathlib import Path

from cja_auto_sdr.output.notion_registry import (
    add_orphaned_page_id,
    get_registry_path,
    load_registry,
    lookup_database_row_id,
    lookup_orphaned_page_ids,
    lookup_page_id,
    remove_orphaned_page_ids,
    store_database_row_id,
    store_page_id,
)


def test_loads_v1_string_entries_as_v2_dict(tmp_path: Path) -> None:
    """A legacy {dv_id: page_id} file is read as {dv_id: {"page_id": ...}}."""
    path = get_registry_path(tmp_path)
    path.write_text(json.dumps({"dv1": "page-abc"}), encoding="utf-8")

    reg = load_registry(path)

    assert reg == {"dv1": {"page_id": "page-abc", "database_row_id": None, "orphaned_page_ids": []}}


def test_lookup_page_id_works_on_legacy_format(tmp_path: Path) -> None:
    path = get_registry_path(tmp_path)
    path.write_text(json.dumps({"dv1": "page-abc"}), encoding="utf-8")

    assert lookup_page_id(path, "dv1") == "page-abc"
    assert lookup_database_row_id(path, "dv1") is None


def test_store_page_id_writes_v2_dict_entry(tmp_path: Path) -> None:
    path = get_registry_path(tmp_path)

    store_page_id(path, "dv1", "page-xyz")

    raw = json.loads(path.read_text(encoding="utf-8"))
    assert raw == {"dv1": {"page_id": "page-xyz", "database_row_id": None, "orphaned_page_ids": []}}


def test_store_database_row_id_preserves_page_id(tmp_path: Path) -> None:
    path = get_registry_path(tmp_path)
    store_page_id(path, "dv1", "page-xyz")

    store_database_row_id(path, "dv1", "row-123")

    assert lookup_page_id(path, "dv1") == "page-xyz"
    assert lookup_database_row_id(path, "dv1") == "row-123"


def test_store_page_id_preserves_existing_database_row_id(tmp_path: Path) -> None:
    """Refreshing the page must not blow away the linked DB row."""
    path = get_registry_path(tmp_path)
    store_page_id(path, "dv1", "page-old")
    store_database_row_id(path, "dv1", "row-123")

    store_page_id(path, "dv1", "page-new")

    assert lookup_page_id(path, "dv1") == "page-new"
    assert lookup_database_row_id(path, "dv1") == "row-123"


def test_missing_dv_returns_none(tmp_path: Path) -> None:
    path = get_registry_path(tmp_path)
    assert lookup_page_id(path, "nope") is None
    assert lookup_database_row_id(path, "nope") is None


def test_corrupt_file_treated_as_empty(tmp_path: Path) -> None:
    path = get_registry_path(tmp_path)
    path.write_bytes(b"\xff\xfe\xfd")
    assert load_registry(path) == {}


def test_load_normalizes_missing_orphans_to_empty_list(tmp_path: Path) -> None:
    path = get_registry_path(tmp_path)
    path.write_text(json.dumps({"dv1": {"page_id": "p1", "database_row_id": "r1"}}), encoding="utf-8")
    assert load_registry(path)["dv1"]["orphaned_page_ids"] == []


def test_add_orphaned_page_id_appends_and_dedups(tmp_path: Path) -> None:
    path = get_registry_path(tmp_path)
    store_page_id(path, "dv1", "p-new")
    add_orphaned_page_id(path, "dv1", "p-old")
    add_orphaned_page_id(path, "dv1", "p-old")  # dedup
    add_orphaned_page_id(path, "dv1", "p-older")
    assert lookup_orphaned_page_ids(path, "dv1") == ["p-old", "p-older"]
    assert lookup_page_id(path, "dv1") == "p-new"  # current page untouched


def test_remove_orphaned_page_ids_drops_pruned(tmp_path: Path) -> None:
    path = get_registry_path(tmp_path)
    add_orphaned_page_id(path, "dv1", "p-old")
    add_orphaned_page_id(path, "dv1", "p-older")
    remove_orphaned_page_ids(path, "dv1", ["p-old"])
    assert lookup_orphaned_page_ids(path, "dv1") == ["p-older"]


def test_lookup_orphans_missing_dv_returns_empty(tmp_path: Path) -> None:
    path = get_registry_path(tmp_path)
    assert lookup_orphaned_page_ids(path, "nope") == []
