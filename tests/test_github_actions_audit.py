from __future__ import annotations

import json
import subprocess
from types import SimpleNamespace

import pytest
from scripts import github_actions_audit


def _command_result(exit_code: int, *, stdout: str = "", stderr: str = "") -> github_actions_audit.CommandResult:
    return github_actions_audit.CommandResult(
        exit_code=exit_code,
        stdout=stdout,
        stderr=stderr,
        command=("uv", "run", "cja_auto_sdr"),
        interrupted=github_actions_audit._is_signal_exit_code(exit_code),
    )


def _write_snapshot(path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "snapshot_version": "1.0",
                "data_view_id": path.stem,
                "data_view_name": path.stem,
                "created_at": "2024-01-01T00:00:00+00:00",
                "metrics": [],
                "dimensions": [],
            },
        ),
        encoding="utf-8",
    )


def test_run_audit_sets_publish_ready_from_successful_manifest_even_after_later_failure(tmp_path):
    reports_dir = tmp_path / "reports"
    snapshot_dir = tmp_path / "snapshots"
    runner_calls = []

    def _runner(args, *, forward_stdout=True, forward_stderr=True):
        runner_calls.append(tuple(args))
        if args == ["dv_1", "--format", "reports", "--output-dir", str(reports_dir)]:
            return _command_result(0)
        if args == ["dv_1", "--snapshot", str(snapshot_dir / "dv_1_baseline.json")]:
            return _command_result(0)
        if args == ["dv_2", "--format", "reports", "--output-dir", str(reports_dir)]:
            return _command_result(1)
        raise AssertionError(f"Unexpected command: {args}")

    outcome = github_actions_audit.run_audit(
        data_view_ids="dv_1,dv_2",
        reports_dir=str(reports_dir),
        snapshot_dir=str(snapshot_dir),
        runner=_runner,
    )

    assert outcome.audit_exit_code == 1
    assert outcome.publish_ready is True
    assert outcome.interrupted is False
    manifest_payload = json.loads((reports_dir / "successful_snapshots_manifest.json").read_text(encoding="utf-8"))
    assert manifest_payload["successful_snapshots"] == [str(snapshot_dir / "dv_1_baseline.json")]
    assert runner_calls == [
        ("dv_1", "--format", "reports", "--output-dir", str(reports_dir)),
        ("dv_1", "--snapshot", str(snapshot_dir / "dv_1_baseline.json")),
        ("dv_2", "--format", "reports", "--output-dir", str(reports_dir)),
    ]


def test_run_audit_clears_publish_ready_when_interrupted(tmp_path):
    reports_dir = tmp_path / "reports"
    snapshot_dir = tmp_path / "snapshots"

    outcome = github_actions_audit.run_audit(
        data_view_ids="dv_1",
        reports_dir=str(reports_dir),
        snapshot_dir=str(snapshot_dir),
        runner=lambda args, *, forward_stdout=True, forward_stderr=True: _command_result(130),
    )

    assert outcome.audit_exit_code == 130
    assert outcome.publish_ready is False
    assert outcome.interrupted is True
    manifest_payload = json.loads((reports_dir / "successful_snapshots_manifest.json").read_text(encoding="utf-8"))
    assert manifest_payload["successful_snapshots"] == []


def test_stage_manifest_rejects_invalid_json_before_git_add(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    invalid_snapshot = tmp_path / "snapshots" / "broken.json"
    invalid_snapshot.parent.mkdir(parents=True, exist_ok=True)
    invalid_snapshot.write_text("{not-json", encoding="utf-8")
    manifest_path.write_text(
        json.dumps({"successful_snapshots": [str(invalid_snapshot)]}),
        encoding="utf-8",
    )

    git_calls = []

    with pytest.raises(json.JSONDecodeError):
        github_actions_audit.stage_manifest_snapshots(
            manifest_path,
            git_runner=lambda command: git_calls.append(command) or SimpleNamespace(returncode=0),
        )

    assert git_calls == []


def test_stage_manifest_stages_only_manifest_entries(tmp_path):
    manifest_path = tmp_path / "manifest.json"
    snapshot_a = tmp_path / "snapshots" / "a.json"
    snapshot_b = tmp_path / "snapshots" / "b.json"
    _write_snapshot(snapshot_a)
    _write_snapshot(snapshot_b)
    manifest_path.write_text(
        json.dumps({"successful_snapshots": [str(snapshot_a), str(snapshot_b)]}),
        encoding="utf-8",
    )

    git_calls = []

    exit_code = github_actions_audit.stage_manifest_snapshots(
        manifest_path,
        git_runner=lambda command: git_calls.append(command) or SimpleNamespace(returncode=0),
    )

    assert exit_code == 0
    assert git_calls == [["git", "add", "--", str(snapshot_a), str(snapshot_b)]]


def test_run_cja_command_returns_bounded_timeout_error(monkeypatch):
    calls = []

    def _fake_run(command, **kwargs):
        calls.append((command, kwargs["timeout"]))
        raise subprocess.TimeoutExpired(command, kwargs["timeout"])

    monkeypatch.setattr(github_actions_audit.subprocess, "run", _fake_run)

    result = github_actions_audit.run_cja_command(["--validate-config"], timeout=12)

    assert result.exit_code == 1
    assert result.stderr == "Command timed out after 12s"
    assert result.command == ("uv", "run", "cja_auto_sdr", "--validate-config")
    assert result.interrupted is False
    assert calls == [(["uv", "run", "cja_auto_sdr", "--validate-config"], 12)]
