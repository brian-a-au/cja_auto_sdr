from __future__ import annotations

import json
import os

import pytest


@pytest.mark.parametrize("use_string_path", [False, True])
def test_load_json_cached_invalidates_replaced_file_with_same_mtime_and_size(tmp_path, use_string_path):
    from cja_auto_sdr.core import json_io

    path = tmp_path / "snap.json"
    replacement = tmp_path / "replacement.json"
    path.write_text('{"value": "old"}', encoding="utf-8")
    argument = str(path) if use_string_path else path
    original = json_io.load_json_cached(argument)
    before = path.stat()

    replacement.write_text('{"value": "new"}', encoding="utf-8")
    os.utime(replacement, ns=(before.st_atime_ns, before.st_mtime_ns))
    os.replace(replacement, path)
    after = path.stat()
    assert (after.st_mtime_ns, after.st_size) == (before.st_mtime_ns, before.st_size)

    refreshed = json_io.load_json_cached(argument)
    assert refreshed == {"value": "new"}
    assert original == {"value": "old"}
    assert json_io.load_json_cached(argument) is refreshed


def test_load_json_cached_parses_once_per_stat(tmp_path, monkeypatch):
    from cja_auto_sdr.core import json_io

    p = tmp_path / "snap.json"
    p.write_text(json.dumps({"snapshot_version": 1, "hello": "world"}), encoding="utf-8")

    calls = {"n": 0}
    real_open = open

    def counting_open(file, *a, **k):
        if str(file) == str(p):
            calls["n"] += 1
        return real_open(file, *a, **k)

    monkeypatch.setattr("builtins.open", counting_open)
    json_io.load_json_cached.cache_clear()  # start clean
    a = json_io.load_json_cached(p)
    b = json_io.load_json_cached(p)
    assert a == {"snapshot_version": 1, "hello": "world"}
    assert a is b  # same cached object
    assert calls["n"] == 1  # second call served from cache
