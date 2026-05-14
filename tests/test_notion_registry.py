"""Tests for Notion page ID registry."""
from __future__ import annotations

import json

from cja_auto_sdr.output.notion_registry import (
    REGISTRY_FILENAME,
    get_registry_path,
    load_registry,
    lookup_page_id,
    save_registry,
    store_page_id,
)


def test_registry_filename_constant():
    assert REGISTRY_FILENAME == ".notion_pages.json"


def test_get_registry_path(tmp_path):
    result = get_registry_path(tmp_path)
    assert result == tmp_path / REGISTRY_FILENAME


def test_load_registry_missing_file_returns_empty(tmp_path):
    result = load_registry(tmp_path / "nonexistent.json")
    assert result == {}


def test_load_registry_reads_existing(tmp_path):
    reg_path = tmp_path / REGISTRY_FILENAME
    reg_path.write_text(json.dumps({"dv_123": "page-abc"}))
    result = load_registry(reg_path)
    assert result == {"dv_123": "page-abc"}


def test_save_registry_writes_json(tmp_path):
    reg_path = tmp_path / REGISTRY_FILENAME
    save_registry(reg_path, {"dv_456": "page-def"})
    data = json.loads(reg_path.read_text())
    assert data == {"dv_456": "page-def"}


def test_lookup_page_id_found(tmp_path):
    reg_path = tmp_path / REGISTRY_FILENAME
    reg_path.write_text(json.dumps({"dv_123": "page-abc", "dv_456": "page-def"}))
    assert lookup_page_id(reg_path, "dv_123") == "page-abc"


def test_lookup_page_id_not_found(tmp_path):
    reg_path = tmp_path / REGISTRY_FILENAME
    reg_path.write_text(json.dumps({"dv_123": "page-abc"}))
    assert lookup_page_id(reg_path, "dv_999") is None


def test_lookup_page_id_missing_registry(tmp_path):
    result = lookup_page_id(tmp_path / "nonexistent.json", "dv_123")
    assert result is None


def test_store_page_id_creates_new_entry(tmp_path):
    reg_path = tmp_path / REGISTRY_FILENAME
    store_page_id(reg_path, "dv_123", "page-abc")
    data = json.loads(reg_path.read_text())
    assert data["dv_123"] == "page-abc"


def test_store_page_id_updates_existing_entry(tmp_path):
    reg_path = tmp_path / REGISTRY_FILENAME
    reg_path.write_text(json.dumps({"dv_123": "page-old"}))
    store_page_id(reg_path, "dv_123", "page-new")
    data = json.loads(reg_path.read_text())
    assert data["dv_123"] == "page-new"


def test_store_page_id_preserves_other_entries(tmp_path):
    reg_path = tmp_path / REGISTRY_FILENAME
    reg_path.write_text(json.dumps({"dv_existing": "page-existing"}))
    store_page_id(reg_path, "dv_new", "page-new")
    data = json.loads(reg_path.read_text())
    assert data["dv_existing"] == "page-existing"
    assert data["dv_new"] == "page-new"
