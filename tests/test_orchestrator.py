from scripts import orchestrator


def test_list_dataviews_unwraps_data_views_envelope(monkeypatch):
    monkeypatch.setattr(
        orchestrator,
        "_run",
        lambda *args, **kwargs: {
            "success": True,
            "data": {
                "dataViews": [{"id": "dv_1"}, {"id": "dv_2"}],
                "count": 2,
            },
        },
    )

    assert orchestrator.list_dataviews() == [{"id": "dv_1"}, {"id": "dv_2"}]


def test_list_snapshots_unwraps_snapshots_envelope(monkeypatch):
    monkeypatch.setattr(
        orchestrator,
        "_run",
        lambda *args, **kwargs: {
            "success": True,
            "data": {
                "snapshots": [{"filepath": "/tmp/a.json"}, {"filepath": "/tmp/b.json"}],
                "count": 2,
            },
        },
    )

    assert orchestrator.list_snapshots("/tmp/snapshots") == [
        {"filepath": "/tmp/a.json"},
        {"filepath": "/tmp/b.json"},
    ]
