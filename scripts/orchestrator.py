"""Orchestrator for programmatic cja_auto_sdr automation.

Wraps the CLI via subprocess for use in CI/CD pipelines,
AI agent frameworks, and custom automation scripts.

Usage:
    python scripts/orchestrator.py --profile client-a dv_abc123
    python scripts/orchestrator.py --profile client-a --discover
    python scripts/orchestrator.py              # Run with DATA_VIEWS env var
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASE_CMD = ["uv", "run", "--project", str(PROJECT_ROOT), "cja_auto_sdr"]


DEFAULT_TIMEOUT = 300  # 5 minutes; override per-call for long-running commands


class OrchestratorError(RuntimeError):
    """Raised when a wrapped cja_auto_sdr command fails unexpectedly."""

    def __init__(self, message: str, *, result: dict | None = None):
        super().__init__(message)
        self.result = result or {}


class OrchestratorArgumentError(ValueError):
    """Raised when the wrapper receives unsupported arguments."""


class _ArgumentParser(argparse.ArgumentParser):
    """ArgumentParser variant that raises instead of exiting on invalid input."""

    def error(self, message: str) -> None:
        raise OrchestratorArgumentError(message)


def _run(
    args: list[str],
    *,
    parse_json: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    shared_args: list[str] | None = None,
) -> dict:
    """Run a cja_auto_sdr command and return structured result."""
    command = [*BASE_CMD, *(shared_args or []), *args]
    try:
        # check is intentionally omitted; exit codes are inspected by callers
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired:
        return {
            "exit_code": 1,
            "success": False,
            "stdout": "",
            "stderr": f"Command timed out after {timeout}s",
            "timed_out": True,
            "command": command,
        }
    output: dict = {
        "exit_code": result.returncode,
        "success": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "command": command,
    }
    if parse_json and result.stdout.strip():
        try:
            output["data"] = json.loads(result.stdout)
        except json.JSONDecodeError:
            output["data"] = None
            output["parse_error"] = True
    return output


def _build_parser() -> _ArgumentParser:
    """Create the standalone orchestrator CLI parser."""
    parser = _ArgumentParser(
        description=(
            "Run cja_auto_sdr across one or more data views and emit a consolidated JSON report. "
            "This wrapper forwards only auth/config options; use the direct CLI for broader flag coverage."
        ),
        allow_abbrev=False,
    )
    parser.add_argument(
        "data_views",
        nargs="*",
        help="Data view IDs to process. If omitted, DATA_VIEWS is used or --discover can auto-discover.",
    )
    parser.add_argument(
        "-p",
        "--profile",
        help="Named profile to forward to cja_auto_sdr for credentials.",
    )
    parser.add_argument(
        "--config-file",
        help="Configuration file to forward to cja_auto_sdr.",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Discover data views with --list-dataviews when no IDs are supplied.",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT,
        help=f"Per-command timeout in seconds (default: {DEFAULT_TIMEOUT}).",
    )
    return parser


def _build_shared_args(args: argparse.Namespace) -> list[str]:
    """Translate wrapper options into cja_auto_sdr flags."""
    shared_args: list[str] = []
    if args.profile:
        shared_args.extend(["--profile", args.profile])
    if args.config_file:
        shared_args.extend(["--config-file", _resolve_caller_path(args.config_file)])
    return shared_args


def _extract_error_text(result: dict) -> str:
    """Normalize stderr into a concise error message."""
    if result.get("timed_out"):
        return result.get("stderr", "Command timed out")

    stderr = (result.get("stderr") or "").strip()
    if not stderr:
        return "Command failed without diagnostic output"

    try:
        payload = json.loads(stderr)
    except json.JSONDecodeError:
        return stderr

    if isinstance(payload, dict) and payload.get("error"):
        return str(payload["error"])
    return stderr


def _unwrap_collection(data: object, key: str) -> list[dict] | None:
    """Normalize list-style CLI JSON payloads with optional metadata envelopes."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        items = data.get(key)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return None


def _require_collection(result: dict, *, key: str, action: str) -> list[dict]:
    """Extract a collection payload or raise an orchestrator error."""
    if not result["success"]:
        raise OrchestratorError(
            f"{action} failed with exit code {result.get('exit_code', 1)}: {_extract_error_text(result)}",
            result=result,
        )
    if result.get("parse_error"):
        raise OrchestratorError(f"{action} returned invalid JSON output", result=result)
    if "data" not in result:
        raise OrchestratorError(f"{action} returned no JSON payload", result=result)

    items = _unwrap_collection(result.get("data"), key)
    if items is None:
        raise OrchestratorError(f"{action} returned unexpected JSON shape", result=result)
    return items


def _validate_config_result(
    *,
    shared_args: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """Run validation and preserve CLI diagnostics for callers that need them."""
    return _run(["--validate-config"], shared_args=shared_args, timeout=timeout)


def _resolve_caller_path(path_str: str) -> str:
    """Resolve relative paths against the caller's working directory."""
    if path_str == "-":
        return path_str

    path = Path(path_str).expanduser()
    if path.is_absolute():
        return str(path)
    return str((Path.cwd() / path).resolve(strict=False))


def _resolve_data_views(
    args: argparse.Namespace,
    *,
    shared_args: list[str] | None = None,
) -> tuple[list[str], str]:
    """Resolve data view IDs from argv, environment, or discovery."""
    if args.data_views:
        return args.data_views, "argv"

    if args.discover:
        discovered_rows = list_dataviews(shared_args=shared_args, timeout=args.timeout)
        data_views: list[str] = []
        for index, row in enumerate(discovered_rows, start=1):
            data_view_id = row.get("id")
            if not data_view_id:
                raise OrchestratorError(f"Data view discovery row {index} did not include an 'id' field")
            data_views.append(str(data_view_id))
        return data_views, "discover"

    env_data_views = [dv.strip() for dv in os.environ.get("DATA_VIEWS", "").split(",") if dv.strip()]
    if env_data_views:
        return env_data_views, "env"

    return [], "none"


def _combine_exit_codes(current: int, new_code: int) -> int:
    """Preserve policy/warn exit codes while failing closed on hard errors."""
    if new_code not in (0, 1, 2, 3):
        new_code = 1

    if current == 1 or new_code == 1:
        return 1
    if current == 2 or new_code == 2:
        return 2
    if current == 3 or new_code == 3:
        return 3
    return 0


def _emit_error(message: str, *, stage: str, result: dict | None = None) -> None:
    """Emit machine-readable orchestrator failures."""
    payload: dict[str, object] = {
        "error": message,
        "stage": stage,
    }
    if result is not None and "exit_code" in result:
        payload["exit_code"] = result["exit_code"]
    print(json.dumps(payload))


def validate_config(*, shared_args: list[str] | None = None, timeout: int = DEFAULT_TIMEOUT) -> bool:
    """Pre-flight credential and connectivity check.

    Returns True if validation passes (exit code 0).
    Note: --validate-config does not produce JSON output;
    this function relies on exit code only.
    """
    result = _validate_config_result(shared_args=shared_args, timeout=timeout)
    return result["success"]


def list_dataviews(
    *,
    shared_args: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[dict]:
    """Discover available data views as structured data."""
    result = _run(
        ["--list-dataviews", "--format", "json", "--output", "-"],
        parse_json=True,
        shared_args=shared_args,
        timeout=timeout,
    )
    return _require_collection(result, key="dataViews", action="Data view discovery")


def list_snapshots(
    snapshot_dir: str = "./snapshots",
    *,
    shared_args: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[dict]:
    """List existing snapshots for baseline management."""
    resolved_snapshot_dir = _resolve_caller_path(snapshot_dir)
    result = _run(
        ["--list-snapshots", "--snapshot-dir", resolved_snapshot_dir, "--format", "json", "--output", "-"],
        parse_json=True,
        shared_args=shared_args,
        timeout=timeout,
    )
    return _require_collection(result, key="snapshots", action="Snapshot discovery")


def run_sdr(
    data_view: str,
    fmt: str = "json",
    output_dir: str | None = None,
    extra_args: list[str] | None = None,
    *,
    shared_args: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """Generate SDR and return structured result."""
    args = [data_view, "--format", fmt]
    if output_dir:
        args.extend(["--output-dir", _resolve_caller_path(output_dir)])
    if fmt in ("json", "csv"):
        args.extend(["--output", "-"])
    if extra_args:
        args.extend(extra_args)
    result = _run(args, parse_json=(fmt == "json"), shared_args=shared_args, timeout=timeout)
    result["data_view"] = data_view
    return result


def run_diff(
    data_view: str,
    snapshot_path: str,
    *,
    shared_args: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """Drift detection against a baseline snapshot.

    Exit codes:
        0 = no changes
        1 = error
        2 = policy threshold exceeded (changes found)
        3 = warning threshold exceeded (--warn-threshold)
    """
    resolved_snapshot_path = _resolve_caller_path(snapshot_path)
    result = _run(
        [data_view, "--diff-snapshot", resolved_snapshot_path, "--format", "json", "--output", "-"],
        parse_json=True,
        shared_args=shared_args,
        timeout=timeout,
    )
    result["data_view"] = data_view
    result["snapshot_path"] = resolved_snapshot_path
    result["has_changes"] = result["exit_code"] in (2, 3)
    result["threshold_exceeded"] = result["exit_code"] == 2
    return result


def run_snapshot(
    data_view: str,
    snapshot_path: str | None = None,
    *,
    shared_args: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """Save a baseline snapshot.

    Args:
        data_view: Data view ID.
        snapshot_path: Output file path. Defaults to ./snapshots/<data_view>_baseline.json.
    """
    if snapshot_path is None:
        snapshot_path = f"./snapshots/{data_view}_baseline.json"
    resolved_snapshot_path = _resolve_caller_path(snapshot_path)
    Path(resolved_snapshot_path).parent.mkdir(parents=True, exist_ok=True)
    result = _run([data_view, "--snapshot", resolved_snapshot_path], shared_args=shared_args, timeout=timeout)
    result["data_view"] = data_view
    result["snapshot_path"] = resolved_snapshot_path
    return result


def main(argv: list[str] | None = None) -> int:
    """Standalone entry point: validate config, process data views, output JSON results."""
    parser = _build_parser()
    raw_argv = sys.argv[1:] if argv is None else argv

    try:
        args = parser.parse_args(raw_argv)
    except OrchestratorArgumentError as exc:
        _emit_error(f"Invalid orchestrator arguments: {exc}", stage="arguments")
        return 1
    except SystemExit as exc:
        return int(exc.code)

    shared_args = _build_shared_args(args)
    try:
        data_views, source = _resolve_data_views(args, shared_args=shared_args)
    except OrchestratorError as exc:
        _emit_error(str(exc), stage="data_view_resolution", result=exc.result)
        return int(exc.result.get("exit_code", 1))

    if not data_views:
        if source == "discover":
            print(
                json.dumps(
                    {
                        "data_views_source": source,
                        "data_views_processed": 0,
                        "overall_exit_code": 0,
                        "results": [],
                    },
                    indent=2,
                )
            )
            return 0
        _emit_error(
            "No data views specified. Pass IDs as args, set DATA_VIEWS, or use --discover.",
            stage="arguments",
        )
        return 1

    # Pre-flight check
    validation_result = _validate_config_result(shared_args=shared_args, timeout=args.timeout)
    if not validation_result["success"]:
        _emit_error(
            f"Configuration validation failed: {_extract_error_text(validation_result)}",
            stage="validation",
            result=validation_result,
        )
        return 1

    results = []
    overall_exit = 0
    for dv in data_views:
        result = run_sdr(dv, fmt="json", shared_args=shared_args, timeout=args.timeout)
        results.append(result)
        overall_exit = _combine_exit_codes(overall_exit, int(result.get("exit_code", 1)))

    print(
        json.dumps(
            {
                "data_views_source": source,
                "data_views_processed": len(results),
                "overall_exit_code": overall_exit,
                "results": results,
            },
            indent=2,
        )
    )
    return overall_exit


if __name__ == "__main__":
    raise SystemExit(main())
