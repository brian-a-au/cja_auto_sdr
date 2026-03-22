from __future__ import annotations

import errno
import json
import os
import stat
from pathlib import Path
from unittest.mock import patch

import pytest

import cja_auto_sdr.core.json_io as json_io
from cja_auto_sdr.core.json_io import write_json_atomic


class _StringOnlyValue:
    def __str__(self) -> str:
        return "serialized-via-default"


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
