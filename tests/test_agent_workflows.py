from __future__ import annotations

import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS_DIR = PROJECT_ROOT / "examples" / "agent-workflows"

_WORKFLOW_SCRIPTS = ["_common.sh", "audit_and_report.sh", "onboard_dataview.sh", "quarterly_governance.sh"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _install_fake_uv(tmp_path: Path, responses: dict[str, tuple[int, str]] | None = None) -> Path:
    """Install a fake `uv` binary that records calls and returns canned responses.

    *responses* maps argument-substring → (exit_code, stdout).
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)

    # Build the response dispatch table as inline shell
    dispatch_lines = []
    for pattern, (code, out) in (responses or {}).items():
        escaped_out = out.replace("'", "'\\''")
        dispatch_lines.append(
            f"if [[ \"$args\" == *{pattern!r}* ]]; then printf '%s\\n' '{escaped_out}'; exit {code}; fi"
        )

    dispatch_block = "\n".join(dispatch_lines)

    fake_uv = bin_dir / "uv"
    fake_uv.write_text(
        textwrap.dedent(
            rf"""\
            #!/usr/bin/env bash
            set -euo pipefail

            args="$*"
            printf '%s\n' "$args" >> "$FAKE_UV_LOG"

            if [[ "$args" == *"--run-summary-json"* && -n "${{FAKE_UV_RUN_SUMMARY_JSON:-}}" ]]; then
                summary_path=""
                prev=""
                for arg in "$@"; do
                    if [[ "$prev" == "--run-summary-json" ]]; then
                        summary_path="$arg"
                        break
                    fi
                    prev="$arg"
                done

                if [[ -n "$summary_path" ]]; then
                    printf '%s\n' "$FAKE_UV_RUN_SUMMARY_JSON" > "$summary_path"
                fi
            fi

            {dispatch_block}

            exit "${{FAKE_UV_DEFAULT_EXIT:-0}}"
            """
        ),
        encoding="utf-8",
    )
    fake_uv.chmod(0o755)
    return fake_uv


def _base_env(tmp_path: Path, responses: dict[str, tuple[int, str]] | None = None) -> tuple[dict[str, str], Path]:
    log_path = tmp_path / "uv_calls.log"
    log_path.write_text("", encoding="utf-8")
    _install_fake_uv(tmp_path, responses)

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
            "FAKE_UV_DEFAULT_EXIT": "0",
            "PATH": f"{tmp_path / 'bin'}{os.pathsep}{env['PATH']}",
        },
    )
    return env, log_path


def _read_calls(log_path: Path) -> list[str]:
    return log_path.read_text(encoding="utf-8").splitlines()


# ---------------------------------------------------------------------------
# File existence and permissions
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("script_name", _WORKFLOW_SCRIPTS)
def test_script_files_exist(script_name: str) -> None:
    assert (WORKFLOWS_DIR / script_name).is_file(), f"{script_name} not found in {WORKFLOWS_DIR}"


@pytest.mark.parametrize(
    "script_name",
    ["audit_and_report.sh", "onboard_dataview.sh", "quarterly_governance.sh"],
)
def test_scripts_are_executable(script_name: str) -> None:
    path = WORKFLOWS_DIR / script_name
    assert os.access(path, os.X_OK), f"{script_name} is not executable"


# ---------------------------------------------------------------------------
# _common.sh — sourcing and helper contract
# ---------------------------------------------------------------------------


def test_common_sh_sources_without_error(tmp_path: Path) -> None:
    """Sourcing _common.sh in a minimal bash script must not produce errors."""
    harness = tmp_path / "harness.sh"
    harness.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            # shellcheck source=/dev/null
            source "{WORKFLOWS_DIR}/_common.sh"
            echo "ok"
            """
        ),
        encoding="utf-8",
    )
    harness.chmod(0o755)
    result = subprocess.run(["bash", str(harness)], capture_output=True, text=True)
    assert result.returncode == 0
    assert "ok" in result.stdout


@pytest.mark.parametrize(
    ("exit_code", "expected_rc", "expect_stderr"),
    [
        (0, 0, False),
        (1, 1, True),
        (2, 0, False),
        (3, 0, False),
        (130, 130, True),
        (4, 1, True),  # synthetic — must be rejected
        (5, 1, True),  # synthetic — must be rejected
        (99, 1, True),  # unknown — must be rejected
    ],
)
def test_common_handle_exit_code_behaviour(
    tmp_path: Path, exit_code: int, expected_rc: int, expect_stderr: bool
) -> None:
    """handle_exit_code() must only pass 0, 1, 2, 3 and 130; all others exit 1."""
    harness = tmp_path / "harness.sh"
    harness.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            # shellcheck source=/dev/null
            source "{WORKFLOWS_DIR}/_common.sh"
            handle_exit_code {exit_code} "test"
            """
        ),
        encoding="utf-8",
    )
    harness.chmod(0o755)
    result = subprocess.run(["bash", str(harness)], capture_output=True, text=True)
    assert result.returncode == expected_rc
    if expect_stderr:
        assert result.stderr.strip() != ""


def test_common_handle_exit_code_labels_warning_threshold_for_exit_3(tmp_path: Path) -> None:
    harness = tmp_path / "harness.sh"
    harness.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            # shellcheck source=/dev/null
            source "{WORKFLOWS_DIR}/_common.sh"
            handle_exit_code 3 "diff"
            """
        ),
        encoding="utf-8",
    )
    harness.chmod(0o755)
    result = subprocess.run(["bash", str(harness)], capture_output=True, text=True)

    assert result.returncode == 0
    assert "[diff] Warning threshold exceeded" in result.stdout
    assert result.stderr == ""


def test_common_exit_on_signal_exit_only_propagates_documented_interrupt(tmp_path: Path) -> None:
    harness = tmp_path / "harness.sh"
    harness.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            # shellcheck source=/dev/null
            source "{WORKFLOWS_DIR}/_common.sh"
            exit_on_signal_exit 143 "terminated"
            echo "continued"
            """
        ),
        encoding="utf-8",
    )
    harness.chmod(0o755)
    result = subprocess.run(["bash", str(harness)], capture_output=True, text=True)

    assert result.returncode == 0
    assert "continued" in result.stdout
    assert "terminated" not in result.stderr


def test_common_exit_on_signal_exit_propagates_documented_interrupt(tmp_path: Path) -> None:
    harness = tmp_path / "harness.sh"
    harness.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            # shellcheck source=/dev/null
            source "{WORKFLOWS_DIR}/_common.sh"
            exit_on_signal_exit 130 "interrupted"
            echo "unreachable"
            """
        ),
        encoding="utf-8",
    )
    harness.chmod(0o755)
    result = subprocess.run(["bash", str(harness)], capture_output=True, text=True)

    assert result.returncode == 130
    assert "interrupted (exit 130)" in result.stderr
    assert "unreachable" not in result.stdout


def test_common_extract_dataview_ids(tmp_path: Path) -> None:
    """extract_dataview_ids() must parse the real dataViews JSON shape."""
    harness = tmp_path / "harness.sh"
    harness.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            # shellcheck source=/dev/null
            source "{WORKFLOWS_DIR}/_common.sh"
            JSON='{{"dataViews":[{{"id":"dv_abc"}},{{"id":"dv_xyz"}}]}}'
            extract_dataview_ids "$JSON"
            """
        ),
        encoding="utf-8",
    )
    harness.chmod(0o755)
    result = subprocess.run(["bash", str(harness)], capture_output=True, text=True)
    assert result.returncode == 0
    assert "dv_abc" in result.stdout
    assert "dv_xyz" in result.stdout


def test_common_require_env_exits_when_unset(tmp_path: Path) -> None:
    harness = tmp_path / "harness.sh"
    harness.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            unset MISSING_VAR || true
            # shellcheck source=/dev/null
            source "{WORKFLOWS_DIR}/_common.sh"
            require_env MISSING_VAR
            """
        ),
        encoding="utf-8",
    )
    harness.chmod(0o755)
    result = subprocess.run(["bash", str(harness)], capture_output=True, text=True)
    assert result.returncode == 1
    assert "MISSING_VAR" in result.stderr


def test_common_load_auth_from_project_dotenv_preserves_injected_values(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".env").write_text(
        textwrap.dedent(
            """\
            ORG_ID=file-org
            CLIENT_ID=file-client
            SECRET=file-secret
            SCOPES=file-scopes
            """
        ),
        encoding="utf-8",
    )

    harness = tmp_path / "harness.sh"
    harness.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            export ORG_ID="injected-org"
            unset CLIENT_ID SECRET SCOPES || true
            # shellcheck source=/dev/null
            source "{WORKFLOWS_DIR}/_common.sh"
            load_auth_from_project_dotenv "{project_root}"
            printf 'ORG_ID=%s\n' "$ORG_ID"
            printf 'CLIENT_ID=%s\n' "$CLIENT_ID"
            printf 'SECRET=%s\n' "$SECRET"
            printf 'SCOPES=%s\n' "$SCOPES"
            """
        ),
        encoding="utf-8",
    )
    harness.chmod(0o755)

    result = subprocess.run(["bash", str(harness)], capture_output=True, text=True)

    assert result.returncode == 0
    assert "ORG_ID=injected-org" in result.stdout
    assert "CLIENT_ID=file-client" in result.stdout
    assert "SECRET=file-secret" in result.stdout
    assert "SCOPES=file-scopes" in result.stdout


def test_common_load_auth_from_project_dotenv_short_circuits_when_auth_is_complete(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".env").write_text(
        textwrap.dedent(
            """\
            ORG_ID=file-org
            CLIENT_ID=file-client
            SECRET=file-secret
            SCOPES=file-scopes
            """
        ),
        encoding="utf-8",
    )

    harness = tmp_path / "harness.sh"
    harness.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            export ORG_ID="injected-org"
            export CLIENT_ID="injected-client"
            export SECRET="injected-secret"
            export SCOPES="injected-scopes"
            # shellcheck source=/dev/null
            source "{WORKFLOWS_DIR}/_common.sh"
            load_auth_from_project_dotenv "{project_root}"
            printf 'ORG_ID=%s\n' "$ORG_ID"
            printf 'CLIENT_ID=%s\n' "$CLIENT_ID"
            printf 'SECRET=%s\n' "$SECRET"
            printf 'SCOPES=%s\n' "$SCOPES"
            """
        ),
        encoding="utf-8",
    )
    harness.chmod(0o755)

    result = subprocess.run(["bash", str(harness)], capture_output=True, text=True)

    assert result.returncode == 0
    assert "ORG_ID=injected-org" in result.stdout
    assert "CLIENT_ID=injected-client" in result.stdout
    assert "SECRET=injected-secret" in result.stdout
    assert "SCOPES=injected-scopes" in result.stdout


def test_common_load_auth_from_project_dotenv_does_not_override_non_auth_vars(tmp_path: Path) -> None:
    project_root = tmp_path / "project"
    project_root.mkdir()
    (project_root / ".env").write_text(
        textwrap.dedent(
            """\
            ORG_ID=file-org
            CLIENT_ID=file-client
            SECRET=file-secret
            SCOPES=file-scopes
            REPORT_DIR=file-reports
            """
        ),
        encoding="utf-8",
    )

    harness = tmp_path / "harness.sh"
    harness.write_text(
        textwrap.dedent(
            f"""\
            #!/usr/bin/env bash
            set -euo pipefail
            export REPORT_DIR="injected-reports"
            unset ORG_ID CLIENT_ID SECRET SCOPES || true
            # shellcheck source=/dev/null
            source "{WORKFLOWS_DIR}/_common.sh"
            load_auth_from_project_dotenv "{project_root}"
            printf 'REPORT_DIR=%s\n' "$REPORT_DIR"
            printf 'ORG_ID=%s\n' "$ORG_ID"
            """
        ),
        encoding="utf-8",
    )
    harness.chmod(0o755)

    result = subprocess.run(["bash", str(harness)], capture_output=True, text=True)

    assert result.returncode == 0
    assert "REPORT_DIR=injected-reports" in result.stdout
    assert "ORG_ID=file-org" in result.stdout


# ---------------------------------------------------------------------------
# audit_and_report.sh
# ---------------------------------------------------------------------------


def _audit_env(tmp_path: Path, **extra: str) -> tuple[dict[str, str], Path]:
    discovery_json = '{"dataViews":[{"id":"dv_1"},{"id":"dv_2"}]}'
    responses: dict[str, tuple[int, str]] = {
        "--list-dataviews --agent-mode": (0, discovery_json),
        "--org-report --agent-mode": (0, '{"status":"ok"}'),
    }
    env, log_path = _base_env(tmp_path, responses)
    env.update(extra)
    return env, log_path


def test_audit_runs_to_completion(tmp_path: Path) -> None:
    env, _log_path = _audit_env(tmp_path)

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "audit_and_report.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_audit_calls_list_dataviews_with_agent_mode(tmp_path: Path) -> None:
    env, log_path = _audit_env(tmp_path)

    subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "audit_and_report.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = _read_calls(log_path)
    assert any("--list-dataviews" in c and "--agent-mode" in c for c in calls)


def test_audit_calls_org_report_with_agent_mode(tmp_path: Path) -> None:
    env, log_path = _audit_env(tmp_path)

    subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "audit_and_report.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = _read_calls(log_path)
    assert any("--org-report" in c and "--agent-mode" in c for c in calls)


def test_audit_first_run_creates_baseline_without_compare_with_prev(tmp_path: Path) -> None:
    """On first run (no prior snapshots), must use --snapshot, not --compare-with-prev."""
    # --list-snapshots returns empty list → first run
    discovery_json = '{"dataViews":[{"id":"dv_1"}]}'
    responses: dict[str, tuple[int, str]] = {
        "--list-dataviews --agent-mode": (0, discovery_json),
        "--list-snapshots": (0, '{"snapshots":[]}'),
        "--org-report --agent-mode": (0, '{"status":"ok"}'),
    }
    env, log_path = _base_env(tmp_path, responses)

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "audit_and_report.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = _read_calls(log_path)

    assert result.returncode == 0
    # Must not call --compare-with-prev on first run
    assert all("--compare-with-prev" not in c for c in calls), "Must not call --compare-with-prev on first run"
    # Must create a baseline snapshot instead
    assert any("--snapshot " in c and "dv_1" in c for c in calls), "Must create baseline snapshot on first run"


def test_audit_subsequent_run_uses_compare_with_prev(tmp_path: Path) -> None:
    """When prior snapshots exist, must use --compare-with-prev, not --snapshot."""
    discovery_json = '{"dataViews":[{"id":"dv_1"}]}'
    snapshots_json = '{"snapshots":[{"id":"snap_001"}]}'
    responses: dict[str, tuple[int, str]] = {
        "--list-dataviews --agent-mode": (0, discovery_json),
        "--list-snapshots": (0, snapshots_json),
        "--org-report --agent-mode": (0, '{"status":"ok"}'),
    }
    env, log_path = _base_env(tmp_path, responses)

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "audit_and_report.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = _read_calls(log_path)

    assert result.returncode == 0
    assert any("--compare-with-prev" in c for c in calls), "Must use --compare-with-prev when snapshots exist"


def test_audit_passes_snapshot_dir_to_snapshot_inventory(tmp_path: Path) -> None:
    discovery_json = '{"dataViews":[{"id":"dv_1"}]}'
    snapshots_json = '{"snapshots":[{"id":"snap_001"}]}'
    responses: dict[str, tuple[int, str]] = {
        "--list-dataviews --agent-mode": (0, discovery_json),
        "--list-snapshots": (0, snapshots_json),
        "--org-report --agent-mode": (0, '{"status":"ok"}'),
    }
    env, log_path = _base_env(tmp_path, responses)
    env["SNAPSHOT_DIR"] = str(tmp_path / "custom-snapshots")

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "audit_and_report.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = _read_calls(log_path)
    snapshot_calls = [c for c in calls if "--list-snapshots" in c]

    assert result.returncode == 0
    assert len(snapshot_calls) == 1
    assert f"--snapshot-dir {env['SNAPSHOT_DIR']}" in snapshot_calls[0]


def test_audit_first_run_writes_baseline_to_configured_snapshot_dir(tmp_path: Path) -> None:
    discovery_json = '{"dataViews":[{"id":"dv_1"}]}'
    responses: dict[str, tuple[int, str]] = {
        "--list-dataviews --agent-mode": (0, discovery_json),
        "--list-snapshots": (0, '{"snapshots":[]}'),
        "--org-report --agent-mode": (0, '{"status":"ok"}'),
    }
    env, log_path = _base_env(tmp_path, responses)
    env["SNAPSHOT_DIR"] = str(tmp_path / "custom-snapshots")

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "audit_and_report.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = _read_calls(log_path)
    snapshot_calls = [c for c in calls if "--snapshot " in c]

    assert result.returncode == 0
    assert len(snapshot_calls) == 1
    assert f"--snapshot {env['SNAPSHOT_DIR']}/dv_1_baseline.json" in snapshot_calls[0]


def test_audit_compare_with_prev_reuses_configured_snapshot_dir(tmp_path: Path) -> None:
    discovery_json = '{"dataViews":[{"id":"dv_1"}]}'
    responses: dict[str, tuple[int, str]] = {
        "--list-dataviews --agent-mode": (0, discovery_json),
        "--list-snapshots": (0, '{"snapshots":[{"id":"snap_001"}]}'),
        "--org-report --agent-mode": (0, '{"status":"ok"}'),
    }
    env, log_path = _base_env(tmp_path, responses)
    env["SNAPSHOT_DIR"] = str(tmp_path / "custom-snapshots")

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "audit_and_report.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = _read_calls(log_path)
    compare_calls = [c for c in calls if "--compare-with-prev" in c]

    assert result.returncode == 0
    assert len(compare_calls) == 1
    assert f"--snapshot-dir {env['SNAPSHOT_DIR']}" in compare_calls[0]


def test_audit_snapshot_inventory_failure_does_not_create_baseline(tmp_path: Path) -> None:
    discovery_json = '{"dataViews":[{"id":"dv_1"}]}'
    responses: dict[str, tuple[int, str]] = {
        "--list-dataviews --agent-mode": (0, discovery_json),
        "--list-snapshots": (1, ""),
        "--org-report --agent-mode": (0, '{"status":"ok"}'),
    }
    env, log_path = _base_env(tmp_path, responses)

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "audit_and_report.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = _read_calls(log_path)

    assert result.returncode == 1
    assert all("--snapshot " not in c for c in calls), "Must not create baseline when snapshot inventory fails"
    assert "Snapshot list failed for dv_1" in result.stderr


def test_audit_persists_org_report_artifact(tmp_path: Path) -> None:
    env, _log_path = _audit_env(tmp_path)

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "audit_and_report.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    org_reports = list((tmp_path / "reports").glob("audit-*/org_report.json"))
    assert len(org_reports) == 1
    assert json.loads(org_reports[0].read_text(encoding="utf-8")) == {"status": "ok"}


def test_audit_logs_org_report_advisories_and_actions(tmp_path: Path) -> None:
    advisory_json = json.dumps(
        {
            "status": "ok",
            "advisories": {
                "severity": "warning",
                "findings": [{"type": "high_overlap", "severity": "warning"}],
                "recommended_actions": ["review_overlap_pairs", "verify_intentional_duplicates"],
            },
        }
    )
    responses: dict[str, tuple[int, str]] = {
        "--list-dataviews --agent-mode": (0, '{"dataViews":[{"id":"dv_1"}]}'),
        "--list-snapshots": (0, '{"snapshots":[]}'),
        "--org-report --agent-mode": (0, advisory_json),
    }
    env, _log_path = _base_env(tmp_path, responses)

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "audit_and_report.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Advisories for org report: count=1 severity=warning" in result.stdout
    assert "Recommended actions for org report: review_overlap_pairs,verify_intentional_duplicates" in result.stdout


def test_audit_critical_org_report_advisory_is_logged_without_changing_exit(tmp_path: Path) -> None:
    advisory_json = json.dumps(
        {
            "status": "ok",
            "advisories": {
                "severity": "critical",
                "findings": [{"type": "governance_threshold_breach", "severity": "critical"}],
                "recommended_actions": ["review_governance_thresholds", "remediate_threshold_breach"],
            },
        }
    )
    responses: dict[str, tuple[int, str]] = {
        "--list-dataviews --agent-mode": (0, '{"dataViews":[{"id":"dv_1"}]}'),
        "--list-snapshots": (0, '{"snapshots":[]}'),
        "--org-report --agent-mode": (0, advisory_json),
    }
    env, _log_path = _base_env(tmp_path, responses)

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "audit_and_report.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Advisories for org report: count=1 severity=critical" in result.stdout


def test_audit_persists_diff_artifact_when_compare_with_prev_runs(tmp_path: Path) -> None:
    discovery_json = '{"dataViews":[{"id":"dv_1"}]}'
    snapshots_json = '{"snapshots":[{"id":"snap_001"}]}'
    diff_json = '{"summary":{"has_changes":true,"total_changes":1},"advisories":{"severity":"warning"}}'
    responses: dict[str, tuple[int, str]] = {
        "--list-dataviews --agent-mode": (0, discovery_json),
        "--list-snapshots": (0, snapshots_json),
        "--compare-with-prev --agent-mode": (2, diff_json),
        "--org-report --agent-mode": (0, '{"status":"ok"}'),
    }
    env, _log_path = _base_env(tmp_path, responses)

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "audit_and_report.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    diff_reports = list((tmp_path / "reports").glob("audit-*/dv_1_diff.json"))
    assert len(diff_reports) == 1
    payload = json.loads(diff_reports[0].read_text(encoding="utf-8"))
    assert payload["summary"]["has_changes"] is True


def test_audit_logs_diff_advisories_when_compare_with_prev_runs(tmp_path: Path) -> None:
    diff_json = json.dumps(
        {
            "summary": {"has_changes": False, "total_changes": 0},
            "advisories": {
                "severity": "warning",
                "findings": [{"type": "schema_changes", "severity": "warning"}],
                "recommended_actions": ["review_schema_changes", "validate_mappings"],
            },
        }
    )
    responses: dict[str, tuple[int, str]] = {
        "--list-dataviews --agent-mode": (0, '{"dataViews":[{"id":"dv_1"}]}'),
        "--list-snapshots": (0, '{"snapshots":[{"id":"snap_001"}]}'),
        "--compare-with-prev --agent-mode": (0, diff_json),
        "--org-report --agent-mode": (0, '{"status":"ok"}'),
    }
    env, _log_path = _base_env(tmp_path, responses)

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "audit_and_report.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    assert "Advisories for diff dv_1: count=1 severity=warning" in result.stdout
    assert "Recommended actions for diff dv_1: review_schema_changes,validate_mappings" in result.stdout


def test_audit_never_combines_run_summary_json_with_output_dash(tmp_path: Path) -> None:
    """Must never emit --run-summary-json - combined with --output -."""
    env, log_path = _audit_env(tmp_path)

    subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "audit_and_report.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = _read_calls(log_path)
    for call in calls:
        assert not ("--run-summary-json -" in call and "--output -" in call), (
            f"Invalid combination --run-summary-json - + --output - in: {call}"
        )


def test_audit_signal_exit_stops_workflow(tmp_path: Path) -> None:
    """A signal exit from discovery must propagate and stop subsequent commands."""
    discovery_json = '{"dataViews":[{"id":"dv_1"}]}'
    responses: dict[str, tuple[int, str]] = {
        "--list-dataviews --agent-mode": (130, discovery_json),
    }
    env, log_path = _base_env(tmp_path, responses)

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "audit_and_report.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 130
    calls = _read_calls(log_path)
    # Org report must NOT have been called after signal exit
    assert all("--org-report" not in c for c in calls)


def test_audit_uses_ids_not_names(tmp_path: Path) -> None:
    """Data view processing must use IDs from dataViews, not display names."""
    # Discovery returns IDs only (no 'name' fields used in commands)
    discovery_json = '{"dataViews":[{"id":"dv_abc123","name":"My View"}]}'
    responses: dict[str, tuple[int, str]] = {
        "--list-dataviews --agent-mode": (0, discovery_json),
        "--org-report --agent-mode": (0, '{"status":"ok"}'),
    }
    env, log_path = _base_env(tmp_path, responses)

    subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "audit_and_report.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = _read_calls(log_path)
    # Any per-DV call must use the ID, not the display name
    dv_calls = [c for c in calls if "dv_abc123" in c or "My View" in c]
    assert all("My View" not in c for c in dv_calls), "Must use IDs not display names"


# ---------------------------------------------------------------------------
# onboard_dataview.sh
# ---------------------------------------------------------------------------


def _onboard_env(tmp_path: Path, **extra: str) -> tuple[dict[str, str], Path]:
    describe_json = '{"id":"dv_new","name":"New View"}'
    responses: dict[str, tuple[int, str]] = {
        "--validate-config": (0, ""),
        "--describe-dataview": (0, describe_json),
        "--fail-on-quality": (0, ""),
    }
    env, log_path = _base_env(tmp_path, responses)
    env["DATA_VIEW_ID"] = "dv_new"
    env["FAKE_UV_RUN_SUMMARY_JSON"] = json.dumps(
        {
            "summary_version": "1.1",
            "quality_gate_failed": False,
            "results": [{"dq_severity_counts": {"INFO": 1}}],
        }
    )
    env.update(extra)
    return env, log_path


def test_onboard_runs_to_completion(tmp_path: Path) -> None:
    env, _log_path = _onboard_env(tmp_path)

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "onboard_dataview.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_onboard_calls_validate_config_first(tmp_path: Path) -> None:
    env, log_path = _onboard_env(tmp_path)

    subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "onboard_dataview.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = _read_calls(log_path)
    assert calls, "No calls were recorded"
    assert "--validate-config" in calls[0], "validate-config must be first call"


def test_onboard_calls_describe_dataview(tmp_path: Path) -> None:
    env, log_path = _onboard_env(tmp_path)

    subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "onboard_dataview.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = _read_calls(log_path)
    assert any("--describe-dataview" in c and "dv_new" in c for c in calls)


def test_onboard_calls_sdr_with_agent_mode_quality_gate_and_run_summary(tmp_path: Path) -> None:
    env, log_path = _onboard_env(tmp_path)

    subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "onboard_dataview.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = _read_calls(log_path)
    assert any(
        "dv_new" in c
        and "--agent-mode" in c
        and "--fail-on-quality" in c
        and "--run-summary-json" in c
        and "--output-dir" in c
        for c in calls
    ), "SDR generation must use --agent-mode, --fail-on-quality, --output-dir, and --run-summary-json"


def test_onboard_saves_baseline_snapshot(tmp_path: Path) -> None:
    env, log_path = _onboard_env(tmp_path)

    subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "onboard_dataview.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = _read_calls(log_path)
    assert any("--snapshot " in c and "dv_new" in c for c in calls), "Must save baseline snapshot"


def test_onboard_exits_2_on_quality_gate_breach(tmp_path: Path) -> None:
    describe_json = '{"id":"dv_new"}'
    responses: dict[str, tuple[int, str]] = {
        "--validate-config": (0, ""),
        "--describe-dataview": (0, describe_json),
        "--fail-on-quality": (2, ""),
    }
    env, log_path = _base_env(tmp_path, responses)
    env["DATA_VIEW_ID"] = "dv_new"
    env["FAKE_UV_RUN_SUMMARY_JSON"] = json.dumps(
        {
            "summary_version": "1.1",
            "quality_gate_failed": True,
            "results": [{"dq_severity_counts": {"HIGH": 1}}],
        }
    )

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "onboard_dataview.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    calls = _read_calls(log_path)
    # Snapshot must NOT be saved on quality gate breach
    assert all("--snapshot " not in c for c in calls), "Must not save snapshot when quality gate is breached"
    assert "severity=HIGH" in result.stdout
    assert (tmp_path / "reports" / "dv_new_run_summary.json").exists()


def test_onboard_suppresses_inner_success_stdout_on_quality_gate_breach(tmp_path: Path) -> None:
    describe_json = '{"id":"dv_new"}'
    responses: dict[str, tuple[int, str]] = {
        "--validate-config": (0, ""),
        "--describe-dataview": (0, describe_json),
        "--fail-on-quality": (2, "SUCCESS: SDR generated for New View"),
    }
    env, _log_path = _base_env(tmp_path, responses)
    env["DATA_VIEW_ID"] = "dv_new"
    env["FAKE_UV_RUN_SUMMARY_JSON"] = json.dumps(
        {
            "summary_version": "1.1",
            "quality_gate_failed": True,
            "results": [{"dq_severity_counts": {"HIGH": 1}}],
        }
    )

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "onboard_dataview.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "SUCCESS: SDR generated" not in result.stdout
    assert "SUCCESS: SDR generated" not in result.stderr
    assert "severity=HIGH" in result.stdout


def test_onboard_exits_1_when_data_view_id_not_set(tmp_path: Path) -> None:
    env, _log_path = _base_env(tmp_path)
    env.pop("DATA_VIEW_ID", None)

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "onboard_dataview.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert "DATA_VIEW_ID" in result.stderr


def test_onboard_validate_config_failure_exits_1(tmp_path: Path) -> None:
    responses: dict[str, tuple[int, str]] = {
        "--validate-config": (1, ""),
    }
    env, log_path = _base_env(tmp_path, responses)
    env["DATA_VIEW_ID"] = "dv_new"

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "onboard_dataview.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Configuration validation failed (exit 1)" in result.stderr
    calls = _read_calls(log_path)
    assert all("--describe-dataview" not in c for c in calls)


def test_onboard_never_combines_run_summary_json_with_output_dash(tmp_path: Path) -> None:
    env, log_path = _onboard_env(tmp_path)

    subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "onboard_dataview.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = _read_calls(log_path)
    for call in calls:
        assert not ("--run-summary-json -" in call and "--output -" in call)


def test_onboard_signal_exit_stops_workflow(tmp_path: Path) -> None:
    """Signal exit from validate-config must propagate and stop subsequent commands."""
    responses: dict[str, tuple[int, str]] = {
        "--validate-config": (130, ""),
    }
    env, log_path = _base_env(tmp_path, responses)
    env["DATA_VIEW_ID"] = "dv_new"

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "onboard_dataview.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 130
    calls = _read_calls(log_path)
    # No SDR generation after validate-config signal exit
    assert all("--describe-dataview" not in c for c in calls)


# ---------------------------------------------------------------------------
# quarterly_governance.sh
# ---------------------------------------------------------------------------


def _governance_env(tmp_path: Path, org_exit: int = 0, **extra: str) -> tuple[dict[str, str], Path]:
    org_json = '{"status":"ok","thresholds_exceeded":false}'
    responses: dict[str, tuple[int, str]] = {
        "--org-report": (org_exit, org_json),
    }
    env, log_path = _base_env(tmp_path, responses)
    env.update(extra)
    return env, log_path


def test_governance_runs_to_completion(tmp_path: Path) -> None:
    env, _log_path = _governance_env(tmp_path)

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "quarterly_governance.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0


def test_governance_calls_org_report_with_trending_window(tmp_path: Path) -> None:
    env, log_path = _governance_env(tmp_path, TRENDING_WINDOW="6")

    subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "quarterly_governance.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = _read_calls(log_path)
    assert any("--org-report" in c and "--trending-window" in c and "6" in c for c in calls)


def test_governance_uses_default_trending_window_from_spec(tmp_path: Path) -> None:
    env, log_path = _governance_env(tmp_path)

    subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "quarterly_governance.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = [c for c in _read_calls(log_path) if "--org-report" in c]

    assert len(calls) >= 2
    assert all("--trending-window 10" in c for c in calls)


def test_governance_uses_agent_mode_for_machine_readable_pass(tmp_path: Path) -> None:
    env, log_path = _governance_env(tmp_path)

    subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "quarterly_governance.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = _read_calls(log_path)
    assert any("--org-report" in c and "--agent-mode" in c for c in calls)


def test_governance_uses_fail_on_threshold(tmp_path: Path) -> None:
    env, log_path = _governance_env(tmp_path)

    subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "quarterly_governance.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = _read_calls(log_path)
    assert any("--fail-on-threshold" in c for c in calls)


def test_governance_passes_concrete_threshold_flags(tmp_path: Path) -> None:
    env, log_path = _governance_env(
        tmp_path,
        DUPLICATE_THRESHOLD="7",
        ISOLATED_THRESHOLD="0.4",
    )

    subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "quarterly_governance.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = [c for c in _read_calls(log_path) if "--org-report" in c]

    assert len(calls) >= 2
    assert all("--duplicate-threshold 7" in c for c in calls)
    assert all("--isolated-threshold 0.4" in c for c in calls)


def test_governance_uses_default_threshold_values(tmp_path: Path) -> None:
    env, log_path = _governance_env(tmp_path)

    subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "quarterly_governance.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = [c for c in _read_calls(log_path) if "--org-report" in c]

    assert len(calls) >= 2
    assert all("--duplicate-threshold 5" in c for c in calls)
    assert all("--isolated-threshold 0.35" in c for c in calls)


def test_governance_prunes_snapshots_with_defaults(tmp_path: Path) -> None:
    env, log_path = _governance_env(tmp_path)

    subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "quarterly_governance.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = _read_calls(log_path)
    prune_calls = [c for c in calls if "--prune-snapshots" in c]

    assert len(prune_calls) == 1
    assert "--keep-last 4" in prune_calls[0]
    assert f"--snapshot-dir {env['SNAPSHOT_DIR']}" in prune_calls[0]


def test_governance_prunes_snapshots_with_overrides(tmp_path: Path) -> None:
    env, log_path = _governance_env(
        tmp_path,
        SNAPSHOT_DIR=str(tmp_path / "custom-snapshots"),
        KEEP_LAST="9",
    )

    subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "quarterly_governance.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = _read_calls(log_path)
    prune_calls = [c for c in calls if "--prune-snapshots" in c]

    assert len(prune_calls) == 1
    assert "--keep-last 9" in prune_calls[0]
    assert f"--snapshot-dir {env['SNAPSHOT_DIR']}" in prune_calls[0]


def test_governance_prune_failure_updates_overall_exit(tmp_path: Path) -> None:
    responses: dict[str, tuple[int, str]] = {
        "--org-report": (0, '{"status":"ok","thresholds_exceeded":false}'),
        "--prune-snapshots": (1, ""),
    }
    env, _log_path = _base_env(tmp_path, responses)

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "quarterly_governance.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Snapshot pruning failed" in result.stderr


def test_governance_markdown_failure_takes_precedence_over_threshold_exit(tmp_path: Path) -> None:
    responses: dict[str, tuple[int, str]] = {
        "--agent-mode": (2, '{"status":"ok","thresholds_exceeded":true}'),
        "--format markdown": (1, ""),
    }
    env, _log_path = _base_env(tmp_path, responses)

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "quarterly_governance.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Markdown export failed" in result.stderr


def test_governance_prune_failure_takes_precedence_over_threshold_exit(tmp_path: Path) -> None:
    responses: dict[str, tuple[int, str]] = {
        "--agent-mode": (2, '{"status":"ok","thresholds_exceeded":true}'),
        "--prune-snapshots": (1, ""),
    }
    env, _log_path = _base_env(tmp_path, responses)

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "quarterly_governance.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 1
    assert "Snapshot pruning failed" in result.stderr


def test_governance_generates_human_artifact_separately(tmp_path: Path) -> None:
    """Markdown report must be a separate uv call from the machine-readable pass."""
    env, log_path = _governance_env(tmp_path)

    subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "quarterly_governance.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = _read_calls(log_path)
    org_calls = [c for c in calls if "--org-report" in c]
    assert len(org_calls) >= 2, "Must have at least 2 org-report calls (machine + human)"
    # One must use --agent-mode, one must use --format markdown
    assert any("--agent-mode" in c for c in org_calls)
    assert any("--format markdown" in c for c in org_calls)


def test_governance_exits_2_when_threshold_exceeded(tmp_path: Path) -> None:
    env, _log_path = _governance_env(tmp_path, org_exit=2)

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "quarterly_governance.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2


def test_governance_never_invents_exit_code_4_or_5(tmp_path: Path) -> None:
    """Scripts must never exit with synthetic codes like 4 or 5."""
    for org_exit in [0, 1, 2, 3]:
        env, _log_path = _governance_env(tmp_path, org_exit=org_exit)
        result = subprocess.run(
            ["bash", str(WORKFLOWS_DIR / "quarterly_governance.sh")],
            cwd=PROJECT_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )
        assert result.returncode not in (4, 5), (
            f"Script must not emit exit code {result.returncode} for org_exit={org_exit}"
        )


def test_governance_signal_exit_stops_workflow(tmp_path: Path) -> None:
    responses: dict[str, tuple[int, str]] = {
        "--org-report": (130, ""),
    }
    env, _log_path = _base_env(tmp_path, responses)

    result = subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "quarterly_governance.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 130


def test_governance_never_combines_run_summary_json_with_output_dash(tmp_path: Path) -> None:
    env, log_path = _governance_env(tmp_path)

    subprocess.run(
        ["bash", str(WORKFLOWS_DIR / "quarterly_governance.sh")],
        cwd=PROJECT_ROOT,
        env=env,
        capture_output=True,
        text=True,
    )
    calls = _read_calls(log_path)
    for call in calls:
        assert not ("--run-summary-json -" in call and "--output -" in call)
