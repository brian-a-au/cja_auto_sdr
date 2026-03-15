"""Helpers for the example GitHub Actions SDR audit workflow."""

# ruff: noqa: T201

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cja_auto_sdr.core.exit_codes import (
    INTERRUPT_EXIT_CODE as _INTERRUPT_EXIT_CODE,
)
from cja_auto_sdr.core.exit_codes import (
    combine_wrapper_exit_codes as _combine_exit_codes,
)
from cja_auto_sdr.core.exit_codes import (
    is_signal_exit_code as _is_signal_exit_code,
)
from cja_auto_sdr.core.exit_codes import (
    normalize_subprocess_exit_code as _normalize_exit_code,
)
from cja_auto_sdr.core.json_io import write_json_atomic

# Match the orchestrator's explicit project anchoring so this helper resolves
# the checked-out package predictably even when invoked from another cwd.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
_BASE_CMD = ["uv", "run", "--project", str(PROJECT_ROOT), "cja_auto_sdr"]
DEFAULT_TIMEOUT = 300
_MANIFEST_KEY = "successful_snapshots"


@dataclass
class CommandResult:
    exit_code: int
    stdout: str = ""
    stderr: str = ""
    command: tuple[str, ...] = ()
    interrupted: bool = False


@dataclass
class AuditOutcome:
    audit_exit_code: int
    publish_ready: bool
    successful_snapshot_manifest: str
    interrupted: bool
    successful_snapshots: list[str]


def _emit_annotation(level: str, title: str, message: str) -> None:
    print(f"::{level} title={title}::{message}")


def _write_github_output(name: str, value: str) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT", "").strip()
    if not output_path:
        return
    with open(output_path, "a", encoding="utf-8") as f:
        f.write(f"{name}={value}\n")


def run_cja_command(
    args: Sequence[str],
    *,
    forward_stdout: bool = True,
    forward_stderr: bool = True,
    timeout: int = DEFAULT_TIMEOUT,
) -> CommandResult:
    command = [*_BASE_CMD, *args]
    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=timeout)
    except subprocess.TimeoutExpired:
        return CommandResult(
            exit_code=1,
            stderr=f"Command timed out after {timeout}s",
            command=tuple(command),
        )
    except KeyboardInterrupt:
        return CommandResult(
            exit_code=_INTERRUPT_EXIT_CODE,
            stderr="Command interrupted while waiting for subprocess completion",
            command=tuple(command),
            interrupted=True,
        )

    exit_code = _normalize_exit_code(result.returncode)
    if forward_stdout and result.stdout:
        sys.stdout.write(result.stdout)
    if forward_stderr and result.stderr:
        sys.stderr.write(result.stderr)
    return CommandResult(
        exit_code=exit_code,
        stdout=result.stdout,
        stderr=result.stderr,
        command=tuple(command),
        interrupted=_is_signal_exit_code(exit_code),
    )


def _parse_discovered_data_views(stdout: str) -> list[str]:
    payload = json.loads(stdout)
    if isinstance(payload, list):
        views = payload
    elif isinstance(payload, dict):
        views = payload.get("dataViews", [])
    else:
        raise ValueError("Discovery returned an unexpected JSON payload")

    return [str(view["id"]).strip() for view in views if isinstance(view, dict) and view.get("id")]


def _write_manifest(manifest_path: Path, successful_snapshots: list[str]) -> Path:
    write_json_atomic(
        manifest_path,
        {_MANIFEST_KEY: successful_snapshots},
        indent=2,
        ensure_ascii=False,
    )
    return manifest_path


def run_audit(
    *,
    input_data_view: str = "",
    data_view_ids: str = "",
    reports_dir: str = "reports",
    snapshot_dir: str = "snapshots",
    manifest_path: str | None = None,
    runner: Callable[..., CommandResult] = run_cja_command,
) -> AuditOutcome:
    reports_path = Path(reports_dir)
    snapshot_path = Path(snapshot_dir)
    reports_path.mkdir(parents=True, exist_ok=True)
    snapshot_path.mkdir(parents=True, exist_ok=True)

    successful_snapshots: list[str] = []
    overall_exit = 0
    interrupted = False
    resolved_manifest_path = (
        Path(manifest_path) if manifest_path else reports_path / "successful_snapshots_manifest.json"
    )

    stripped_input = input_data_view.strip()
    stripped_data_view_ids = data_view_ids.strip()
    if stripped_input:
        data_views = [stripped_input]
    elif stripped_data_view_ids:
        data_views = [item.strip() for item in stripped_data_view_ids.split(",") if item.strip()]
    else:
        discovery = runner(
            ["--list-dataviews", "--format", "json", "--output", "-"],
            forward_stdout=False,
        )
        if discovery.exit_code != 0:
            interrupted = _is_signal_exit_code(discovery.exit_code)
            _emit_annotation(
                "error",
                "Data view discovery failed",
                f"Unable to resolve data views automatically (exit {discovery.exit_code}).",
            )
            manifest = _write_manifest(resolved_manifest_path, successful_snapshots)
            return AuditOutcome(
                audit_exit_code=discovery.exit_code if interrupted else 1,
                publish_ready=False,
                successful_snapshot_manifest=str(manifest),
                interrupted=interrupted,
                successful_snapshots=successful_snapshots,
            )
        try:
            data_views = _parse_discovered_data_views(discovery.stdout)
        except (ValueError, json.JSONDecodeError) as exc:
            _emit_annotation(
                "error",
                "Data view discovery failed",
                f"Unable to parse discovered data views: {exc}",
            )
            manifest = _write_manifest(resolved_manifest_path, successful_snapshots)
            return AuditOutcome(
                audit_exit_code=1,
                publish_ready=False,
                successful_snapshot_manifest=str(manifest),
                interrupted=False,
                successful_snapshots=successful_snapshots,
            )

    for data_view_id in data_views:
        print(f"::group::Processing {data_view_id}")
        try:
            sdr_result = runner(
                [data_view_id, "--format", "reports", "--output-dir", str(reports_path)],
            )
            if sdr_result.exit_code == 2:
                _emit_annotation(
                    "warning",
                    "Policy threshold exceeded",
                    f"{data_view_id} returned exit code 2 while generating SDR output.",
                )
                overall_exit = _combine_exit_codes(overall_exit, 2)
            elif sdr_result.exit_code == 3:
                _emit_annotation(
                    "warning",
                    "Warning threshold exceeded",
                    f"{data_view_id} returned exit code 3 while generating SDR output.",
                )
                overall_exit = _combine_exit_codes(overall_exit, 3)
            elif sdr_result.exit_code != 0:
                if _is_signal_exit_code(sdr_result.exit_code):
                    interrupted = True
                    overall_exit = _combine_exit_codes(overall_exit, sdr_result.exit_code)
                    _emit_annotation(
                        "error",
                        "Processing interrupted",
                        f"{data_view_id} generation was interrupted (exit {sdr_result.exit_code}).",
                    )
                    break
                overall_exit = _combine_exit_codes(overall_exit, 1)
                _emit_annotation(
                    "error",
                    "SDR generation failed",
                    f"{data_view_id} generation failed with exit {sdr_result.exit_code}.",
                )
                continue

            baseline_path = snapshot_path / f"{data_view_id}_baseline.json"
            drift_report_path = reports_path / f"{data_view_id}_drift.json"
            if baseline_path.exists():
                diff_result = runner(
                    [
                        data_view_id,
                        "--diff-snapshot",
                        str(baseline_path),
                        "--format",
                        "json",
                        "--output",
                        "-",
                    ],
                    forward_stdout=False,
                    forward_stderr=False,
                )
                if diff_result.exit_code in (0, 2, 3):
                    drift_report_path.write_text(diff_result.stdout, encoding="utf-8")
                    if diff_result.exit_code == 2:
                        _emit_annotation(
                            "warning",
                            "Drift detected",
                            f"{data_view_id} diff exited 2. See {drift_report_path.name}.",
                        )
                        overall_exit = _combine_exit_codes(overall_exit, 2)
                    elif diff_result.exit_code == 3:
                        _emit_annotation(
                            "warning",
                            "Drift warning",
                            f"{data_view_id} diff exited 3. See {drift_report_path.name}.",
                        )
                        overall_exit = _combine_exit_codes(overall_exit, 3)
                else:
                    drift_report_path.unlink(missing_ok=True)
                    if _is_signal_exit_code(diff_result.exit_code):
                        interrupted = True
                        overall_exit = _combine_exit_codes(overall_exit, diff_result.exit_code)
                        _emit_annotation(
                            "error",
                            "Processing interrupted",
                            f"{data_view_id} drift check was interrupted (exit {diff_result.exit_code}).",
                        )
                        break
                    overall_exit = _combine_exit_codes(overall_exit, 1)
                    _emit_annotation(
                        "error",
                        "Drift comparison failed",
                        f"{data_view_id} drift check failed with exit {diff_result.exit_code}. Baseline preserved.",
                    )
                    continue

            snapshot_result = runner([data_view_id, "--snapshot", str(baseline_path)])
            if snapshot_result.exit_code == 0:
                successful_snapshots.append(str(baseline_path))
                continue
            if _is_signal_exit_code(snapshot_result.exit_code):
                interrupted = True
                overall_exit = _combine_exit_codes(overall_exit, snapshot_result.exit_code)
                _emit_annotation(
                    "error",
                    "Processing interrupted",
                    f"{data_view_id} snapshot update was interrupted (exit {snapshot_result.exit_code}).",
                )
                break
            overall_exit = _combine_exit_codes(overall_exit, 1)
            _emit_annotation(
                "error",
                "Snapshot update failed",
                f"{data_view_id} snapshot refresh failed with exit {snapshot_result.exit_code}.",
            )
        finally:
            print("::endgroup::")

    manifest = _write_manifest(resolved_manifest_path, successful_snapshots)
    return AuditOutcome(
        audit_exit_code=overall_exit,
        publish_ready=bool(successful_snapshots) and not interrupted,
        successful_snapshot_manifest=str(manifest),
        interrupted=interrupted,
        successful_snapshots=successful_snapshots,
    )


def _load_manifest(manifest_path: str | Path) -> list[str]:
    with open(manifest_path, encoding="utf-8") as f:
        payload = json.load(f)

    if isinstance(payload, list):
        candidates = payload
    elif isinstance(payload, dict):
        candidates = payload.get(_MANIFEST_KEY)
    else:
        raise ValueError(f"Manifest {manifest_path} has an unexpected JSON shape")

    if not isinstance(candidates, list):
        raise ValueError(f"Manifest {manifest_path} is missing a '{_MANIFEST_KEY}' list")
    return [str(candidate) for candidate in candidates if str(candidate).strip()]


def validate_manifest_snapshots(manifest_path: str | Path) -> list[str]:
    manifest_entries = _load_manifest(manifest_path)
    for entry in manifest_entries:
        candidate = Path(entry)
        if not candidate.is_file():
            raise FileNotFoundError(f"Manifest entry does not exist: {entry}")
        with open(candidate, encoding="utf-8") as f:
            payload = json.load(f)
        if not isinstance(payload, dict) or "snapshot_version" not in payload:
            raise ValueError(f"Manifest entry is not a valid snapshot JSON file: {entry}")
    return manifest_entries


def stage_manifest_snapshots(
    manifest_path: str | Path,
    *,
    git_runner: Callable[[Sequence[str]], subprocess.CompletedProcess[str] | Any] | None = None,
) -> int:
    snapshot_paths = validate_manifest_snapshots(manifest_path)
    if not snapshot_paths:
        return 0

    runner = git_runner or (lambda command: subprocess.run(command, check=False))
    result = runner(["git", "add", "--", *snapshot_paths])
    return _normalize_exit_code(int(getattr(result, "returncode", result)))


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit_parser = subparsers.add_parser("audit", help="Run the example audit workflow logic")
    audit_parser.add_argument("--input-data-view", default="")
    audit_parser.add_argument("--data-view-ids", default=os.environ.get("DATA_VIEW_IDS", ""))
    audit_parser.add_argument("--reports-dir", default="reports")
    audit_parser.add_argument("--snapshot-dir", default="snapshots")
    audit_parser.add_argument("--manifest-path", default="")

    stage_parser = subparsers.add_parser("stage-manifest", help="Validate and stage snapshot files from a manifest")
    stage_parser.add_argument("--manifest", required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)

    if args.command == "audit":
        outcome = run_audit(
            input_data_view=args.input_data_view,
            data_view_ids=args.data_view_ids,
            reports_dir=args.reports_dir,
            snapshot_dir=args.snapshot_dir,
            manifest_path=args.manifest_path or None,
        )
        _write_github_output("audit_exit_code", str(outcome.audit_exit_code))
        _write_github_output("publish_ready", str(outcome.publish_ready).lower())
        _write_github_output("successful_snapshot_manifest", outcome.successful_snapshot_manifest)
        _write_github_output("interrupted", str(outcome.interrupted).lower())
        print(
            json.dumps(
                {
                    "audit_exit_code": outcome.audit_exit_code,
                    "publish_ready": outcome.publish_ready,
                    "successful_snapshot_manifest": outcome.successful_snapshot_manifest,
                    "interrupted": outcome.interrupted,
                    "successful_snapshots": outcome.successful_snapshots,
                },
                indent=2,
            )
        )
        return 0

    try:
        return stage_manifest_snapshots(args.manifest)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
