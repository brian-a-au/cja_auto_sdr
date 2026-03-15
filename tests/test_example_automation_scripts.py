from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
AUTOMATION_DIR = PROJECT_ROOT / "examples" / "automation"


def _install_fake_uv(tmp_path: Path) -> Path:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()

    fake_uv = bin_dir / "uv"
    fake_uv.write_text(
        textwrap.dedent(
            r"""\
            #!/usr/bin/env bash
            set -euo pipefail

            args="$*"
            printf '%s\n' "$args" >> "$FAKE_UV_LOG"

            if [[ "$args" == "run cja_auto_sdr --validate-config" ]]; then
                exit 0
            fi

            if [[ "$args" == "run cja_auto_sdr --list-dataviews --format json --output -" ]]; then
                printf '%s\n' '[{"id":"dv_1"},{"id":"dv_2"}]'
                exit 0
            fi

            if [[ "$args" == *"--org-report"* && "$args" == *"--format json --output -"* ]]; then
                printf '%s\n' '{"status":"ok"}'
                exit 0
            fi

            if [[ $args == run\ cja_auto_sdr\ dv_1\ * && $args == *\ --snapshot\ * ]]; then
                exit "${FAKE_UV_DV1_SNAPSHOT_EXIT:-0}"
            fi

            exit 0
            """,
        ),
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    return fake_uv


def _base_env(tmp_path: Path) -> tuple[dict[str, str], Path]:
    log_path = tmp_path / "uv_calls.log"
    _install_fake_uv(tmp_path)

    env = os.environ.copy()
    env.update(
        {
            "ORG_ID": "test-org",
            "CLIENT_ID": "test-client",
            "SECRET": "test-secret",
            "SCOPES": "test-scopes",
            "REPORT_DIR": str(tmp_path / "reports"),
            "SNAPSHOT_DIR": str(tmp_path / "snapshots"),
            "FAKE_UV_LOG": str(log_path),
            "FAKE_UV_DV1_SNAPSHOT_EXIT": "143",
            "PATH": f"{tmp_path / 'bin'}{os.pathsep}{env['PATH']}",
        },
    )
    return env, log_path


def _copy_standalone_script(tmp_path: Path, script_name: str) -> Path:
    standalone_dir = tmp_path / "standalone" / "examples" / "automation"
    standalone_dir.mkdir(parents=True)

    copied_script = standalone_dir / script_name
    copied_script.write_text((AUTOMATION_DIR / script_name).read_text(encoding="utf-8"), encoding="utf-8")
    copied_script.chmod(0o755)
    return copied_script


@pytest.mark.parametrize(
    ("script_name", "blocked_commands"),
    [
        (
            "weekly_sdr.sh",
            [
                "run cja_auto_sdr dv_2 --format excel",
            ],
        ),
        (
            "quarterly_maintenance.sh",
            [
                "run cja_auto_sdr dv_2 --format all",
                "run cja_auto_sdr --org-report",
                "run cja_auto_sdr --prune-snapshots",
                "run cja_auto_sdr dv_1 --format reports",
            ],
        ),
    ],
)
def test_snapshot_signal_exit_stops_automation_immediately(
    tmp_path: Path,
    script_name: str,
    blocked_commands: list[str],
) -> None:
    env, log_path = _base_env(tmp_path)

    result = subprocess.run(
        ["bash", str(AUTOMATION_DIR / script_name)],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 143
    assert "interrupted" in result.stderr
    assert "exit 143" in result.stderr

    calls = log_path.read_text(encoding="utf-8").splitlines()
    assert any("run cja_auto_sdr dv_1 --snapshot" in call for call in calls)
    for blocked_command in blocked_commands:
        assert all(blocked_command not in call for call in calls)


def test_weekly_script_remains_self_contained_without_common_helper(tmp_path: Path) -> None:
    env, log_path = _base_env(tmp_path)
    copied_script = _copy_standalone_script(tmp_path, "weekly_sdr.sh")

    result = subprocess.run(
        ["bash", str(copied_script)],
        cwd=tmp_path / "standalone",
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 143
    assert "_common.sh" not in result.stderr
    assert "interrupted" in result.stderr

    calls = log_path.read_text(encoding="utf-8").splitlines()
    assert any("run cja_auto_sdr dv_1 --snapshot" in call for call in calls)


def test_daily_drift_check_preserves_signal_exit_during_baseline_creation(tmp_path: Path) -> None:
    env, log_path = _base_env(tmp_path)
    env["DATA_VIEW_ID"] = "dv_1"

    result = subprocess.run(
        ["bash", str(AUTOMATION_DIR / "daily_drift_check.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 143
    assert "Baseline creation interrupted" in result.stderr
    assert "exit 143" in result.stderr

    calls = log_path.read_text(encoding="utf-8").splitlines()
    assert calls == [
        f"run cja_auto_sdr dv_1 --snapshot {tmp_path / 'snapshots' / 'dv_1_baseline.json'}",
    ]
