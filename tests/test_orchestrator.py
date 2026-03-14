import json
from types import SimpleNamespace

import pytest
from scripts import orchestrator


def test_run_targets_repo_project_without_overriding_caller_cwd(monkeypatch):
    calls = []

    def _fake_run(*args, **kwargs):
        calls.append((args[0], kwargs.get("cwd")))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.setattr(orchestrator.subprocess, "run", _fake_run)

    result = orchestrator._run(["--validate-config"])

    assert result["success"] is True
    assert calls == [
        (
            [
                "uv",
                "run",
                "--project",
                str(orchestrator.PROJECT_ROOT),
                "cja_auto_sdr",
                "--validate-config",
            ],
            None,
        )
    ]


def test_run_normalizes_signal_exit_codes(monkeypatch):
    def _fake_run(*args, **kwargs):
        return SimpleNamespace(returncode=-2, stdout="", stderr="")

    monkeypatch.setattr(orchestrator.subprocess, "run", _fake_run)

    result = orchestrator._run(["dv_123", "--format", "json", "--output", "-"])

    assert result["success"] is False
    assert result["raw_exit_code"] == -2
    assert result["exit_code"] == 130


def test_run_returns_structured_interrupt_result_when_wrapper_is_interrupted(monkeypatch):
    def _fake_run(*args, **kwargs):
        raise KeyboardInterrupt

    monkeypatch.setattr(orchestrator.subprocess, "run", _fake_run)

    result = orchestrator._run(["dv_123", "--format", "json", "--output", "-"])

    assert result["success"] is False
    assert result["exit_code"] == 130
    assert result["error_type"] == "interrupted"
    assert result["interrupted"] is True
    assert "interrupted" in result["stderr"].lower()


def test_path_args_remain_caller_relative_when_subprocesses_run_from_project_root(monkeypatch, tmp_path):
    commands = []

    def _fake_run(*args, **kwargs):
        commands.append((args[0], kwargs.get("cwd")))
        return SimpleNamespace(returncode=0, stdout="{}", stderr="")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(orchestrator.subprocess, "run", _fake_run)

    parser = orchestrator._build_parser()
    parsed = parser.parse_args(["--config-file", "./config.json", "dv_123"])
    shared_args = orchestrator._build_shared_args(parsed)

    orchestrator.run_sdr("dv_123", output_dir="./reports", shared_args=shared_args)
    orchestrator.run_diff("dv_123", "./snapshots/base.json", shared_args=shared_args)
    orchestrator.run_snapshot("dv_123", "./snapshots/new.json", shared_args=shared_args)

    expected_config = str((tmp_path / "config.json").resolve())
    expected_output_dir = str((tmp_path / "reports").resolve())
    expected_diff_snapshot = str((tmp_path / "snapshots" / "base.json").resolve())
    expected_new_snapshot = str((tmp_path / "snapshots" / "new.json").resolve())

    assert commands == [
        (
            [
                "uv",
                "run",
                "--project",
                str(orchestrator.PROJECT_ROOT),
                "cja_auto_sdr",
                "--config-file",
                expected_config,
                "dv_123",
                "--format",
                "json",
                "--output-dir",
                expected_output_dir,
                "--output",
                "-",
            ],
            None,
        ),
        (
            [
                "uv",
                "run",
                "--project",
                str(orchestrator.PROJECT_ROOT),
                "cja_auto_sdr",
                "--config-file",
                expected_config,
                "dv_123",
                "--diff-snapshot",
                expected_diff_snapshot,
                "--format",
                "json",
                "--output",
                "-",
            ],
            None,
        ),
        (
            [
                "uv",
                "run",
                "--project",
                str(orchestrator.PROJECT_ROOT),
                "cja_auto_sdr",
                "--config-file",
                expected_config,
                "dv_123",
                "--snapshot",
                expected_new_snapshot,
            ],
            None,
        ),
    ]


def test_run_sdr_file_formats_keep_caller_default_output_directory(monkeypatch, tmp_path):
    calls = []

    def _fake_run(*args, **kwargs):
        calls.append((args[0], kwargs.get("cwd")))
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(orchestrator.subprocess, "run", _fake_run)

    result = orchestrator.run_sdr("dv_123", fmt="excel")

    assert result["success"] is True
    assert calls == [
        (
            [
                "uv",
                "run",
                "--project",
                str(orchestrator.PROJECT_ROOT),
                "cja_auto_sdr",
                "dv_123",
                "--format",
                "excel",
            ],
            None,
        )
    ]


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


def test_list_dataviews_raises_on_cli_failure(monkeypatch):
    monkeypatch.setattr(
        orchestrator,
        "_run",
        lambda *args, **kwargs: {
            "success": False,
            "exit_code": 1,
            "stderr": '{"error": "Configuration error: Missing credentials"}',
        },
    )

    with pytest.raises(orchestrator.OrchestratorError, match="Missing credentials"):
        orchestrator.list_dataviews()


def test_list_snapshots_raises_on_cli_failure(monkeypatch):
    monkeypatch.setattr(
        orchestrator,
        "_run",
        lambda *args, **kwargs: {
            "success": False,
            "exit_code": 1,
            "stderr": '{"error": "Snapshot listing failed"}',
        },
    )

    with pytest.raises(orchestrator.OrchestratorError, match="Snapshot listing failed"):
        orchestrator.list_snapshots()


def test_main_forwards_profile_without_treating_it_as_data_view(monkeypatch, capsys):
    validation_calls = []
    run_calls = []

    def _fake_validate(*, shared_args=None, timeout=orchestrator.DEFAULT_TIMEOUT):
        validation_calls.append((shared_args, timeout))
        return {"success": True, "exit_code": 0, "stderr": "", "stdout": ""}

    def _fake_run_sdr(data_view, fmt="json", output_dir=None, extra_args=None, *, shared_args=None, timeout=0):
        run_calls.append((data_view, fmt, shared_args, timeout))
        return {"data_view": data_view, "exit_code": 0, "success": True}

    monkeypatch.setattr(orchestrator, "_validate_config_result", _fake_validate)
    monkeypatch.setattr(orchestrator, "run_sdr", _fake_run_sdr)

    exit_code = orchestrator.main(["--profile", "client-a", "dv_123"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["data_views_processed"] == 1
    assert payload["data_views_source"] == "argv"
    assert validation_calls == [(["--profile", "client-a"], orchestrator.DEFAULT_TIMEOUT)]
    assert run_calls == [("dv_123", "json", ["--profile", "client-a"], orchestrator.DEFAULT_TIMEOUT)]


def test_main_rejects_unknown_wrapper_options(capsys):
    exit_code = orchestrator.main(["--batch", "dv_123"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["stage"] == "arguments"
    assert "unrecognized arguments: --batch" in payload["error"]


def test_main_discovers_data_views_and_preserves_policy_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(
        orchestrator,
        "_validate_config_result",
        lambda *, shared_args=None, timeout=orchestrator.DEFAULT_TIMEOUT: {
            "success": True,
            "exit_code": 0,
            "stderr": "",
            "stdout": "",
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "list_dataviews",
        lambda *, shared_args=None, timeout=orchestrator.DEFAULT_TIMEOUT: [
            {"id": "dv_1"},
            {"id": "dv_2"},
        ],
    )
    run_results = iter(
        [
            {"data_view": "dv_1", "exit_code": 0, "success": True},
            {"data_view": "dv_2", "exit_code": 2, "success": False},
        ]
    )
    monkeypatch.setattr(
        orchestrator,
        "run_sdr",
        lambda data_view, fmt="json", output_dir=None, extra_args=None, *, shared_args=None, timeout=0: next(
            run_results
        ),
    )

    exit_code = orchestrator.main(["--profile", "client-a", "--discover"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 2
    assert payload["data_views_source"] == "discover"
    assert payload["overall_exit_code"] == 2
    assert payload["data_views_processed"] == 2


def test_main_stops_batch_and_preserves_interrupt_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(
        orchestrator,
        "_validate_config_result",
        lambda *, shared_args=None, timeout=orchestrator.DEFAULT_TIMEOUT: {
            "success": True,
            "exit_code": 0,
            "stderr": "",
            "stdout": "",
        },
    )
    run_calls = []
    run_results = {
        "dv_1": {"data_view": "dv_1", "exit_code": 0, "success": True},
        "dv_2": {"data_view": "dv_2", "exit_code": 130, "success": False},
    }

    def _fake_run_sdr(data_view, fmt="json", output_dir=None, extra_args=None, *, shared_args=None, timeout=0):
        run_calls.append(data_view)
        return run_results[data_view]

    monkeypatch.setattr(orchestrator, "run_sdr", _fake_run_sdr)

    exit_code = orchestrator.main(["dv_1", "dv_2", "dv_3"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 130
    assert payload["overall_exit_code"] == 130
    assert payload["data_views_processed"] == 2
    assert run_calls == ["dv_1", "dv_2"]


def test_main_discover_overrides_data_views_environment(monkeypatch, capsys):
    monkeypatch.setenv("DATA_VIEWS", "stale_dv")
    monkeypatch.setattr(
        orchestrator,
        "_validate_config_result",
        lambda *, shared_args=None, timeout=orchestrator.DEFAULT_TIMEOUT: {
            "success": True,
            "exit_code": 0,
            "stderr": "",
            "stdout": "",
        },
    )
    monkeypatch.setattr(
        orchestrator,
        "list_dataviews",
        lambda *, shared_args=None, timeout=orchestrator.DEFAULT_TIMEOUT: [{"id": "fresh_dv"}],
    )
    run_calls = []
    monkeypatch.setattr(
        orchestrator,
        "run_sdr",
        lambda data_view, fmt="json", output_dir=None, extra_args=None, *, shared_args=None, timeout=0: (
            run_calls.append(data_view) or {"data_view": data_view, "exit_code": 0, "success": True}
        ),
    )

    exit_code = orchestrator.main(["--discover"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["data_views_source"] == "discover"
    assert run_calls == ["fresh_dv"]


def test_main_validation_failure_preserves_interrupt_exit_code(monkeypatch, capsys):
    monkeypatch.setattr(
        orchestrator,
        "_validate_config_result",
        lambda *, shared_args=None, timeout=orchestrator.DEFAULT_TIMEOUT: {
            "success": False,
            "exit_code": 130,
            "stderr": "Interrupted",
            "stdout": "",
        },
    )

    exit_code = orchestrator.main(["dv_123"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 130
    assert payload["stage"] == "validation"
    assert payload["exit_code"] == 130
    assert payload["error_type"] == "interrupted"
    assert payload["interrupted"] is True


def test_main_emits_json_interrupt_when_keyboard_interrupt_escapes_run_path(monkeypatch, capsys):
    def _raise_keyboard_interrupt(args):
        raise KeyboardInterrupt

    monkeypatch.setattr(orchestrator, "_build_shared_args", _raise_keyboard_interrupt)

    exit_code = orchestrator.main(["dv_123"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 130
    assert payload["stage"] == "interrupted"
    assert payload["exit_code"] == 130
    assert payload["error_type"] == "interrupted"
    assert payload["interrupted"] is True


def test_main_discover_reports_empty_org_without_error(monkeypatch, capsys):
    monkeypatch.setattr(
        orchestrator,
        "list_dataviews",
        lambda *, shared_args=None, timeout=orchestrator.DEFAULT_TIMEOUT: [],
    )

    exit_code = orchestrator.main(["--discover"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert payload["data_views_source"] == "discover"
    assert payload["data_views_processed"] == 0
    assert payload["overall_exit_code"] == 0


def test_main_discover_emits_json_error_on_discovery_failure(monkeypatch, capsys):
    monkeypatch.setattr(
        orchestrator,
        "list_dataviews",
        lambda *, shared_args=None, timeout=orchestrator.DEFAULT_TIMEOUT: (_ for _ in ()).throw(
            orchestrator.OrchestratorError(
                "Data view discovery failed with exit code 1: bad credentials",
                stage="data_view_resolution",
                result={"exit_code": 1},
            )
        ),
    )

    exit_code = orchestrator.main(["--discover"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["stage"] == "data_view_resolution"
    assert "bad credentials" in payload["error"]


def test_main_preserves_orchestrator_error_stage(monkeypatch, capsys):
    monkeypatch.setattr(
        orchestrator,
        "_build_shared_args",
        lambda args: (_ for _ in ()).throw(
            orchestrator.OrchestratorError(
                "Synthetic staged failure",
                stage="custom_stage",
                result={"exit_code": 1},
            )
        ),
    )

    exit_code = orchestrator.main(["dv_123"])
    payload = json.loads(capsys.readouterr().out)

    assert exit_code == 1
    assert payload["stage"] == "custom_stage"
    assert payload["error"] == "Synthetic staged failure"
