from __future__ import annotations

import errno
import json
import os
import stat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

import cja_auto_sdr.core.json_io as json_io
from cja_auto_sdr.core.json_io import (
    write_json_atomic,
    write_json_atomic_compatible,
    write_text_atomic_compatible,
)

_SKIP_PERMISSION_SEMANTICS = os.name == "nt" or getattr(os, "geteuid", lambda: -1)() == 0


class _StringOnlyValue:
    def __str__(self) -> str:
        return "serialized-via-default"


def _near_name_max_path(tmp_path: Path, suffix: str) -> Path:
    if not hasattr(os, "pathconf"):
        pytest.skip("requires os.pathconf support")
    name_max = os.pathconf(str(tmp_path), "PC_NAME_MAX")
    if name_max <= len(suffix) + 1:
        pytest.skip("filesystem name limit too small for test fixture")
    stem = "a" * (name_max - len(suffix) - 1)
    return tmp_path / f"{stem}{suffix}"


def test_write_json_atomic_supports_default_sort_keys_and_trailing_newline(tmp_path):
    output_path = tmp_path / "payload.json"

    write_json_atomic(
        output_path,
        {
            "z_key": _StringOnlyValue(),
            "a_key": 1,
        },
        sort_keys=True,
        trailing_newline=True,
        default=str,
    )

    raw_text = output_path.read_text(encoding="utf-8")

    assert raw_text.endswith("\n")
    assert raw_text.index('"a_key"') < raw_text.index('"z_key"')
    assert json.loads(raw_text) == {
        "a_key": 1,
        "z_key": "serialized-via-default",
    }


@pytest.mark.skipif(not hasattr(os, "fchmod"), reason="requires os.fchmod support")
def test_write_json_atomic_applies_explicit_file_mode(tmp_path):
    output_path = tmp_path / "secret.json"

    write_json_atomic(output_path, {"token": "value"}, file_mode=0o600)

    assert Path(output_path).exists()
    assert stat.S_IMODE(output_path.stat().st_mode) == 0o600


# ---------------------------------------------------------------------------
# Coverage gap tests (moved from test_small_gap_coverage.py)
# ---------------------------------------------------------------------------


def test_json_io_fsync_directory_suppresses_best_effort_errors(tmp_path) -> None:
    with patch("cja_auto_sdr.core.json_io.os.open", side_effect=OSError(errno.EPERM, "no dir fsync")):
        json_io._fsync_directory(tmp_path)


def test_json_io_fsync_directory_reraises_unexpected_errors(tmp_path) -> None:
    with (
        patch("cja_auto_sdr.core.json_io.os.open", side_effect=OSError(errno.ENOENT, "missing")),
        pytest.raises(OSError, match="missing"),
    ):
        json_io._fsync_directory(tmp_path)


def test_write_json_atomic_closes_fd_when_fdopen_fails(tmp_path) -> None:
    output_path = tmp_path / "payload.json"

    with (
        patch("cja_auto_sdr.core.json_io.os.open", return_value=123),
        patch("cja_auto_sdr.core.json_io.os.fdopen", side_effect=OSError("fdopen boom")),
        patch("cja_auto_sdr.core.json_io.os.close") as mock_close,
        pytest.raises(OSError, match="fdopen boom"),
    ):
        json_io.write_json_atomic(output_path, {"key": "value"})

    mock_close.assert_called_with(123)


# ---------------------------------------------------------------------------
# Compatibility-preserving atomic helpers (v3.5.7)
# ---------------------------------------------------------------------------


class TestWriteJsonAtomicCompatible:
    """Tests for write_json_atomic_compatible."""

    def test_trailing_newline_by_default(self, tmp_path):
        out = tmp_path / "out.json"
        write_json_atomic_compatible(out, {"key": "value"})
        raw = out.read_text(encoding="utf-8")
        assert raw.endswith("\n")
        assert json.loads(raw) == {"key": "value"}

    def test_no_trailing_newline_when_disabled(self, tmp_path):
        out = tmp_path / "out.json"
        write_json_atomic_compatible(out, {"a": 1}, trailing_newline=False)
        raw = out.read_text(encoding="utf-8")
        assert not raw.endswith("\n")

    def test_supports_default_and_sort_keys(self, tmp_path):
        out = tmp_path / "sorted.json"
        write_json_atomic_compatible(
            out,
            {
                "z_key": _StringOnlyValue(),
                "a_key": 1,
            },
            sort_keys=True,
            default=str,
        )

        raw = out.read_text(encoding="utf-8")
        assert raw.endswith("\n")
        assert raw.index('"a_key"') < raw.index('"z_key"')
        assert json.loads(raw) == {
            "a_key": 1,
            "z_key": "serialized-via-default",
        }

    def test_near_name_max_path_uses_short_temp_name(self, tmp_path):
        out = _near_name_max_path(tmp_path, ".json")

        write_json_atomic_compatible(out, {"ok": True})

        assert json.loads(out.read_text(encoding="utf-8")) == {"ok": True}

    def test_follows_existing_symlink(self, tmp_path):
        real_file = tmp_path / "real.json"
        real_file.write_text("{}", encoding="utf-8")
        link = tmp_path / "link.json"
        link.symlink_to(real_file)

        write_json_atomic_compatible(link, {"via": "symlink"})

        assert link.is_symlink()
        assert json.loads(real_file.read_text(encoding="utf-8")) == {"via": "symlink"}

    def test_preserves_existing_file_mode_on_overwrite(self, tmp_path):
        out = tmp_path / "out.json"
        out.write_text("{}", encoding="utf-8")
        os.chmod(out, 0o644)

        write_json_atomic_compatible(out, {"updated": True})

        assert stat.S_IMODE(out.stat().st_mode) == 0o644

    @pytest.mark.skipif(not hasattr(os, "link"), reason="requires hard-link support")
    def test_hard_linked_overwrite_falls_back_to_direct_write(self, tmp_path):
        out = tmp_path / "out.json"
        alias = tmp_path / "latest.json"
        out.write_text('{"old": true}\n', encoding="utf-8")
        os.link(out, alias)
        inode_before = out.stat().st_ino

        write_json_atomic_compatible(out, {"updated": True})

        assert out.stat().st_ino == inode_before
        assert alias.stat().st_ino == inode_before
        assert json.loads(alias.read_text(encoding="utf-8")) == {"updated": True}

    @pytest.mark.skipif(not hasattr(os, "listxattr"), reason="requires os.listxattr support")
    def test_xattr_bearing_file_falls_back_to_direct_write(self, tmp_path):
        out = tmp_path / "tagged.json"
        out.write_text('{"old": true}\n', encoding="utf-8")
        inode_before = out.stat().st_ino

        with patch("cja_auto_sdr.core.json_io.os.listxattr", return_value=["user.test"]):
            write_json_atomic_compatible(out, {"updated": True})

        assert out.stat().st_ino == inode_before
        assert json.loads(out.read_text(encoding="utf-8")) == {"updated": True}

    def test_existing_file_without_xattr_introspection_falls_back_to_direct_write(self, tmp_path, monkeypatch):
        out = tmp_path / "acl-managed.json"
        out.write_text('{"old": true}\n', encoding="utf-8")
        inode_before = out.stat().st_ino

        monkeypatch.delattr(json_io.os, "listxattr", raising=False)

        write_json_atomic_compatible(out, {"updated": True})

        assert out.stat().st_ino == inode_before
        assert json.loads(out.read_text(encoding="utf-8")) == {"updated": True}

    def test_replace_denied_overwrite_falls_back_to_direct_write(self, tmp_path):
        out = tmp_path / "rename-denied.json"
        out.write_text('{"old": true}\n', encoding="utf-8")
        inode_before = out.stat().st_ino

        with (
            patch("cja_auto_sdr.core.json_io._path_has_extended_metadata", return_value=False),
            patch(
                "cja_auto_sdr.core.json_io.os.replace",
                side_effect=PermissionError(errno.EPERM, "replace denied"),
            ),
        ):
            write_json_atomic_compatible(out, {"updated": True})

        assert out.stat().st_ino == inode_before
        assert json.loads(out.read_text(encoding="utf-8")) == {"updated": True}
        assert list(tmp_path.glob(".*tmp")) == []

    def test_explicit_file_mode_overrides_existing(self, tmp_path):
        out = tmp_path / "out.json"
        out.write_text("{}", encoding="utf-8")
        os.chmod(out, 0o644)

        write_json_atomic_compatible(out, {"secret": True}, file_mode=0o600)

        assert stat.S_IMODE(out.stat().st_mode) == 0o600

    def test_new_file_honours_umask(self, tmp_path):
        out = tmp_path / "new.json"
        write_json_atomic_compatible(out, {"new": True})
        assert out.exists()
        # File should exist with umask-driven permissions (not hardcoded)
        mode = stat.S_IMODE(out.stat().st_mode)
        assert mode & 0o600 == 0o600  # owner rw at minimum

    @pytest.mark.skipif(_SKIP_PERMISSION_SEMANTICS, reason="requires POSIX non-root permission semantics")
    def test_read_only_existing_file_matches_open_permissions(self, tmp_path):
        out = tmp_path / "readonly.json"
        out.write_text("{}", encoding="utf-8")
        os.chmod(out, 0o444)

        with pytest.raises(PermissionError):
            write_json_atomic_compatible(out, {"blocked": True})

        assert out.read_text(encoding="utf-8") == "{}"

    def test_broken_symlink_does_not_create_missing_target_parent(self, tmp_path):
        links_dir = tmp_path / "links"
        links_dir.mkdir()
        link = links_dir / "out.json"
        link.symlink_to("../missing/out.json")

        with pytest.raises(FileNotFoundError):
            write_json_atomic_compatible(link, {"blocked": True})

        assert link.is_symlink()
        assert not (tmp_path / "missing").exists()

    @pytest.mark.skipif(_SKIP_PERMISSION_SEMANTICS, reason="requires POSIX non-root permission semantics")
    def test_non_writable_directory_falls_back_to_direct_overwrite(self, tmp_path):
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        out = out_dir / "report.json"
        out.write_text('{"old": true}', encoding="utf-8")

        os.chmod(out_dir, 0o555)  # noqa: S103
        try:
            write_json_atomic_compatible(out, {"new": True})
        finally:
            os.chmod(out_dir, 0o755)  # noqa: S103

        assert json.loads(out.read_text(encoding="utf-8")) == {"new": True}

    def test_temp_cleanup_on_failure(self, tmp_path):
        out = tmp_path / "fail.json"
        with (
            patch("cja_auto_sdr.core.json_io.json.dump", side_effect=TypeError("boom")),
            pytest.raises(TypeError, match="boom"),
        ):
            write_json_atomic_compatible(out, {"bad": object()})

        # No temp files should remain
        remaining = list(tmp_path.glob(".*tmp"))
        assert remaining == []

    def test_ensure_ascii_matches_json_dump_default(self, tmp_path):
        out = tmp_path / "unicode.json"
        write_json_atomic_compatible(out, {"name": "\u00e9l\u00e8ve"})
        raw = out.read_text(encoding="utf-8")
        assert "\\u00e9l\\u00e8ve" in raw

    def test_ensure_ascii_false_when_requested(self, tmp_path):
        out = tmp_path / "unicode.json"
        write_json_atomic_compatible(out, {"name": "\u00e9l\u00e8ve"}, ensure_ascii=False)
        raw = out.read_text(encoding="utf-8")
        assert "\u00e9l\u00e8ve" in raw

    @pytest.mark.skipif(os.name == "nt" or not hasattr(os, "chown"), reason="requires POSIX os.chown")
    def test_apply_existing_metadata_replays_owner_group(self, tmp_path):
        resolved = tmp_path / "resolved.json"
        staged = tmp_path / ".resolved.json.tmp"
        resolved.write_text("{}", encoding="utf-8")
        staged.write_text("{}", encoding="utf-8")
        original_stat = Path.stat

        def fake_stat(self):
            if self == resolved:
                return SimpleNamespace(st_mode=stat.S_IFREG | 0o640, st_uid=123, st_gid=456, st_nlink=1)
            if self == staged:
                return SimpleNamespace(st_uid=789, st_gid=987)
            return original_stat(self)

        with (
            patch("pathlib.Path.stat", autospec=True, side_effect=fake_stat),
            patch("cja_auto_sdr.core.json_io.os.chmod") as mock_chmod,
            patch("cja_auto_sdr.core.json_io.os.chown") as mock_chown,
        ):
            json_io._apply_existing_metadata(staged, resolved, None)

        mock_chmod.assert_called_once_with(staged, 0o640)
        mock_chown.assert_called_once_with(staged, 123, 456)

    @pytest.mark.skipif(os.name == "nt" or not hasattr(os, "chown"), reason="requires POSIX os.chown")
    def test_inherited_group_atomic_overwrite_does_not_require_chown(self, tmp_path):
        out = tmp_path / "report.json"
        out.write_text('{"old": true}\n', encoding="utf-8")
        inode_before = out.stat().st_ino
        existing_stat = out.stat()
        staged = tmp_path / ".stage.tmp"
        inherited_gid = existing_stat.st_gid + 1000
        original_stat = Path.stat

        def fake_stat(self):
            if self == out:
                return SimpleNamespace(
                    st_mode=existing_stat.st_mode,
                    st_uid=existing_stat.st_uid,
                    st_gid=inherited_gid,
                    st_nlink=1,
                )
            if self == staged:
                return SimpleNamespace(st_uid=existing_stat.st_uid, st_gid=inherited_gid)
            return original_stat(self)

        with (
            patch("cja_auto_sdr.core.json_io._compatible_tmp_path", return_value=staged),
            patch("cja_auto_sdr.core.json_io._path_has_extended_metadata", return_value=False),
            patch("pathlib.Path.stat", autospec=True, side_effect=fake_stat),
            patch("cja_auto_sdr.core.json_io.os.chown") as mock_chown,
        ):
            write_json_atomic_compatible(out, {"updated": True})

        assert out.stat().st_ino != inode_before
        assert json.loads(out.read_text(encoding="utf-8")) == {"updated": True}
        mock_chown.assert_not_called()


class TestWriteTextAtomicCompatible:
    """Tests for write_text_atomic_compatible."""

    def test_writes_text_content(self, tmp_path):
        out = tmp_path / "out.html"
        write_text_atomic_compatible(out, "<html>hello</html>")
        assert out.read_text(encoding="utf-8") == "<html>hello</html>"

    def test_near_name_max_path_uses_short_temp_name(self, tmp_path):
        out = _near_name_max_path(tmp_path, ".md")

        write_text_atomic_compatible(out, "ok")

        assert out.read_text(encoding="utf-8") == "ok"

    def test_follows_existing_symlink(self, tmp_path):
        real_file = tmp_path / "real.md"
        real_file.write_text("old", encoding="utf-8")
        link = tmp_path / "link.md"
        link.symlink_to(real_file)

        write_text_atomic_compatible(link, "new content")

        assert link.is_symlink()
        assert real_file.read_text(encoding="utf-8") == "new content"

    def test_preserves_existing_file_mode_on_overwrite(self, tmp_path):
        out = tmp_path / "out.md"
        out.write_text("old", encoding="utf-8")
        os.chmod(out, 0o644)

        write_text_atomic_compatible(out, "new")

        assert stat.S_IMODE(out.stat().st_mode) == 0o644

    @pytest.mark.skipif(not hasattr(os, "link"), reason="requires hard-link support")
    def test_hard_linked_overwrite_falls_back_to_direct_write(self, tmp_path):
        out = tmp_path / "out.md"
        alias = tmp_path / "latest.md"
        out.write_text("old", encoding="utf-8")
        os.link(out, alias)
        inode_before = out.stat().st_ino

        write_text_atomic_compatible(out, "new")

        assert out.stat().st_ino == inode_before
        assert alias.stat().st_ino == inode_before
        assert alias.read_text(encoding="utf-8") == "new"

    @pytest.mark.skipif(not hasattr(os, "listxattr"), reason="requires os.listxattr support")
    def test_xattr_bearing_file_falls_back_to_direct_write(self, tmp_path):
        out = tmp_path / "tagged.md"
        out.write_text("old", encoding="utf-8")
        inode_before = out.stat().st_ino

        with patch("cja_auto_sdr.core.json_io.os.listxattr", return_value=["user.test"]):
            write_text_atomic_compatible(out, "new")

        assert out.stat().st_ino == inode_before
        assert out.read_text(encoding="utf-8") == "new"

    def test_replace_denied_overwrite_falls_back_to_direct_write(self, tmp_path):
        out = tmp_path / "rename-denied.md"
        out.write_text("old", encoding="utf-8")
        inode_before = out.stat().st_ino

        with (
            patch("cja_auto_sdr.core.json_io._path_has_extended_metadata", return_value=False),
            patch(
                "cja_auto_sdr.core.json_io.os.replace",
                side_effect=PermissionError(errno.EPERM, "replace denied"),
            ),
        ):
            write_text_atomic_compatible(out, "new")

        assert out.stat().st_ino == inode_before
        assert out.read_text(encoding="utf-8") == "new"
        assert list(tmp_path.glob(".*tmp")) == []

    def test_explicit_file_mode_overrides_existing(self, tmp_path):
        out = tmp_path / "out.md"
        out.write_text("old", encoding="utf-8")
        os.chmod(out, 0o644)

        write_text_atomic_compatible(out, "secret", file_mode=0o600)

        assert stat.S_IMODE(out.stat().st_mode) == 0o600

    def test_temp_cleanup_on_failure(self, tmp_path):
        out = tmp_path / "fail.txt"
        with (
            patch("cja_auto_sdr.core.json_io.os.fsync", side_effect=OSError("disk full")),
            pytest.raises(OSError, match="disk full"),
        ):
            write_text_atomic_compatible(out, "content")

        remaining = list(tmp_path.glob(".*tmp"))
        assert remaining == []

    @pytest.mark.skipif(_SKIP_PERMISSION_SEMANTICS, reason="requires POSIX non-root permission semantics")
    def test_non_writable_directory_falls_back_to_direct_overwrite(self, tmp_path):
        out_dir = tmp_path / "output"
        out_dir.mkdir()
        out = out_dir / "report.md"
        out.write_text("old", encoding="utf-8")

        os.chmod(out_dir, 0o555)  # noqa: S103
        try:
            write_text_atomic_compatible(out, "new content")
        finally:
            os.chmod(out_dir, 0o755)  # noqa: S103

        assert out.read_text(encoding="utf-8") == "new content"
