"""Tests for staged CSV bundle publication and the completion manifest."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import pandas as pd
import pytest

from cja_auto_sdr.core.exceptions import OutputError
from cja_auto_sdr.output import csv_staging
from cja_auto_sdr.output.csv_staging import (
    CSV_MANIFEST_NAME,
    CSV_MANIFEST_VERSION,
    csv_member_name,
    publish_csv_bundle,
)


def _frame(value: str, rows: int = 2) -> pd.DataFrame:
    return pd.DataFrame({"id": [f"{value}{i}" for i in range(rows)], "name": [f"n{i}" for i in range(rows)]})


def _snapshot(path: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in sorted(path.iterdir()) if p.is_file()}


def _staging_dirs(path: Path) -> list[Path]:
    return [p for p in path.iterdir() if p.is_dir() and p.name.startswith(".csv-")]


def test_constants() -> None:
    assert CSV_MANIFEST_NAME == "_manifest.json"
    assert CSV_MANIFEST_VERSION == "1.0"


def test_member_name_matches_legacy_naming() -> None:
    assert csv_member_name("Data Quality") == "data_quality.csv"
    assert csv_member_name("Metrics") == "metrics.csv"


@pytest.mark.parametrize("name", ["../x", "a/b", "a\\b"])
def test_unsafe_member_names_rejected(name: str) -> None:
    with pytest.raises(OutputError):
        csv_member_name(name)


def test_unsafe_name_rejected_before_touching_disk(tmp_path: Path) -> None:
    target = tmp_path / "bundle"
    with pytest.raises(OutputError):
        publish_csv_bundle({"Metrics": _frame("m"), "a/b": _frame("x")}, target)
    assert not target.exists()


def test_colliding_names_rejected(tmp_path: Path) -> None:
    target = tmp_path / "bundle"
    with pytest.raises(OutputError, match=r"data_view\.csv"):
        publish_csv_bundle({"Data View": _frame("a"), "data_view": _frame("b")}, target)
    assert not target.exists()


def test_empty_frames_rejected(tmp_path: Path) -> None:
    with pytest.raises(OutputError, match="No CSV sections to write"):
        publish_csv_bundle({}, tmp_path / "bundle")


def test_publish_writes_members_and_manifest(tmp_path: Path) -> None:
    result = publish_csv_bundle({"Metrics": _frame("m", 3), "Data Quality": _frame("q", 1)}, tmp_path / "b")
    assert result == tmp_path / "b"
    manifest = json.loads((result / CSV_MANIFEST_NAME).read_text(encoding="utf-8"))
    assert manifest["manifest_version"] == "1.0"
    assert manifest["complete"] is True
    assert manifest["generated_at"].endswith("+00:00")
    assert [f["name"] for f in manifest["files"]] == ["metrics.csv", "data_quality.csv"]
    assert [f["sheet"] for f in manifest["files"]] == ["Metrics", "Data Quality"]
    assert not _staging_dirs(result)


def test_manifest_hashes_and_rows_match_bytes(tmp_path: Path) -> None:
    result = publish_csv_bundle({"Metrics": _frame("m", 3), "Dimensions": _frame("d", 0)}, tmp_path)
    manifest = json.loads((result / CSV_MANIFEST_NAME).read_text(encoding="utf-8"))
    assert (result / CSV_MANIFEST_NAME).read_text(encoding="utf-8").endswith("\n")
    rows = {f["name"]: f["rows"] for f in manifest["files"]}
    assert rows == {"metrics.csv": 3, "dimensions.csv": 0}
    for entry in manifest["files"]:
        data = (result / entry["name"]).read_bytes()
        assert entry["sha256"] == hashlib.sha256(data).hexdigest()
        assert entry["bytes"] == len(data)


def test_second_render_failure_preserves_existing_bundle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:  # AE2
    publish_csv_bundle({"Metrics": _frame("m"), "Dimensions": _frame("d")}, tmp_path)
    before = _snapshot(tmp_path)

    original = pd.DataFrame.to_csv
    calls = {"n": 0}

    def fail_on_second(self: pd.DataFrame, *args: object, **kwargs: object) -> object:
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("disk full")
        return original(self, *args, **kwargs)

    monkeypatch.setattr(pd.DataFrame, "to_csv", fail_on_second)
    with pytest.raises(OSError, match="disk full"):
        publish_csv_bundle({"Metrics": _frame("m2"), "Dimensions": _frame("d2")}, tmp_path)
    assert _snapshot(tmp_path) == before
    assert not _staging_dirs(tmp_path)


def test_member_replace_failure_leaves_no_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    publish_csv_bundle({"Metrics": _frame("m")}, tmp_path)
    original = os.replace
    calls = {"n": 0}

    def fail_second(src: object, dst: object) -> None:
        calls["n"] += 1
        if calls["n"] == 2:
            raise OSError("replace failed")
        original(src, dst)

    monkeypatch.setattr(csv_staging.os, "replace", fail_second)
    with pytest.raises(OSError, match="replace failed"):
        publish_csv_bundle({"Metrics": _frame("m2"), "Dimensions": _frame("d2")}, tmp_path)
    assert not (tmp_path / CSV_MANIFEST_NAME).exists()
    assert not _staging_dirs(tmp_path)


def test_manifest_publish_failure_leaves_no_manifest(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    original = os.replace

    def fail_manifest(src: object, dst: object) -> None:
        if Path(str(dst)).name == CSV_MANIFEST_NAME:
            raise OSError("manifest failed")
        original(src, dst)

    monkeypatch.setattr(csv_staging.os, "replace", fail_manifest)
    with pytest.raises(OSError, match="manifest failed"):
        publish_csv_bundle({"Metrics": _frame("m")}, tmp_path)
    assert not (tmp_path / CSV_MANIFEST_NAME).exists()
    assert not _staging_dirs(tmp_path)


def test_fewer_sections_lists_only_current_and_keeps_extras(tmp_path: Path) -> None:
    publish_csv_bundle({"Metrics": _frame("m"), "Segments": _frame("s")}, tmp_path)
    (tmp_path / "notes.txt").write_text("keep me", encoding="utf-8")
    publish_csv_bundle({"Metrics": _frame("m2")}, tmp_path)
    manifest = json.loads((tmp_path / CSV_MANIFEST_NAME).read_text(encoding="utf-8"))
    assert [f["name"] for f in manifest["files"]] == ["metrics.csv"]
    assert (tmp_path / "segments.csv").exists()
    assert (tmp_path / "notes.txt").read_text(encoding="utf-8") == "keep me"


def test_publish_over_legacy_bundle_without_manifest(tmp_path: Path) -> None:
    (tmp_path / "metrics.csv").write_text("old\n", encoding="utf-8")
    publish_csv_bundle({"Metrics": _frame("m")}, tmp_path)
    assert (tmp_path / CSV_MANIFEST_NAME).exists()
    assert "m0" in (tmp_path / "metrics.csv").read_text(encoding="utf-8")


def test_cleanup_error_does_not_mask_primary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args: object, **kwargs: object) -> None:
        raise PermissionError("cleanup denied")

    def fail_to_csv(self: pd.DataFrame, *args: object, **kwargs: object) -> None:
        raise OSError("primary failure")

    monkeypatch.setattr(pd.DataFrame, "to_csv", fail_to_csv)
    monkeypatch.setattr(csv_staging.shutil, "rmtree", boom)
    with pytest.raises(OSError, match="primary failure"):
        publish_csv_bundle({"Metrics": _frame("m")}, tmp_path)
