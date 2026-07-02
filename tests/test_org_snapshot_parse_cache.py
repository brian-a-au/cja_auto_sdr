from __future__ import annotations

import json


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
