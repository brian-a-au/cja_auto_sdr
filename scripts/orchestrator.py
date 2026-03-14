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

# Resolve the repository root once so every subprocess invocation can point uv
# at the checked-out project, even when callers run this wrapper from elsewhere.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
# Anchor uv to this checkout so the wrapper can be invoked from any cwd
# without changing how relative file paths are interpreted by the caller.
BASE_CMD = ["uv", "run", "--project", str(PROJECT_ROOT), "cja_auto_sdr"]


# Keep the default timeout conservative for CI and agent use, but allow callers
# to override it for especially large organizations or slow API responses.
DEFAULT_TIMEOUT = 300  # 5 minutes; override per-call for long-running commands
_SIGNAL_EXIT_BASE = 128
_MAX_SIGNAL_NUMBER = 64
_INTERRUPT_EXIT_CODE = _SIGNAL_EXIT_BASE + 2


class OrchestratorError(RuntimeError):
    """Raised when a wrapped cja_auto_sdr command fails unexpectedly."""

    def __init__(self, message: str, *, stage: str = "orchestrator", result: dict | None = None):
        super().__init__(message)
        self.stage = stage
        self.result = result or {}


class OrchestratorArgumentError(ValueError):
    """Raised when the wrapper receives unsupported arguments."""


class _ArgumentParser(argparse.ArgumentParser):
    """ArgumentParser variant that raises instead of exiting on invalid input."""

    # Raising keeps orchestration code in control of the JSON error envelope
    # instead of letting argparse print directly to stderr and terminate.

    def error(self, message: str) -> None:
        raise OrchestratorArgumentError(message)


def _normalize_exit_code(code: int) -> int:
    """Translate subprocess signal return codes into shell-style exit codes."""
    # subprocess reports signal exits as negative numbers. Converting to
    # 128+signal keeps the wrapper aligned with the documented CLI contract.
    if code < 0:
        return _SIGNAL_EXIT_BASE + abs(code)
    return code


def _is_signal_exit_code(code: int) -> bool:
    """Return True when an exit code represents signal termination."""
    return _SIGNAL_EXIT_BASE < code <= (_SIGNAL_EXIT_BASE + _MAX_SIGNAL_NUMBER)


def _interrupted_result(command: list[str], *, message: str) -> dict:
    """Return a synthetic result for wrapper-side interruption paths."""
    return {
        "exit_code": _INTERRUPT_EXIT_CODE,
        "success": False,
        "stdout": "",
        "stderr": message,
        "command": command,
        "error_type": "interrupted",
        "interrupted": True,
    }


def _run(
    args: list[str],
    *,
    parse_json: bool = False,
    timeout: int = DEFAULT_TIMEOUT,
    shared_args: list[str] | None = None,
) -> dict:
    """Run a cja_auto_sdr command and return structured result."""
    # Build one flat argv list so the returned payload can echo the exact child
    # command back to CI logs or agent runtimes for debugging.
    command = [*BASE_CMD, *(shared_args or []), *args]
    try:
        # check is intentionally omitted; policy and warning exits are valid
        # outcomes that callers need to inspect instead of treating as errors.
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
    except KeyboardInterrupt:
        return _interrupted_result(
            command,
            message="Command interrupted while waiting for subprocess completion",
        )

    # Normalize the subprocess result into a single payload shape so every
    # helper can enrich the same structure without special casing raw CompletedProcess.
    exit_code = _normalize_exit_code(result.returncode)
    output: dict = {
        "exit_code": exit_code,
        "raw_exit_code": result.returncode,
        "success": exit_code == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "command": command,
    }
    if parse_json and result.stdout.strip():
        try:
            # Most automation paths expect machine-readable stdout, so decode it
            # eagerly and attach the parsed payload alongside the raw text.
            output["data"] = json.loads(result.stdout)
        except json.JSONDecodeError:
            # Keep the raw stdout so callers can surface a better error while
            # still distinguishing "command failed" from "JSON contract broke".
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
    # Keep the CLI surface intentionally narrow: this wrapper exists to provide
    # stable orchestration behavior, not to mirror every direct CLI flag.
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
    # Only forward wrapper-supported auth/config flags here; this script is
    # intentionally narrow and leaves broader CLI coverage to direct usage.
    shared_args: list[str] = []
    if args.profile:
        shared_args.extend(["--profile", args.profile])
    if args.config_file:
        shared_args.extend(["--config-file", _resolve_caller_path(args.config_file)])
    return shared_args


def _extract_error_text(result: dict) -> str:
    """Normalize stderr into a concise error message."""
    # Timeouts do not necessarily produce stderr, so handle them before any
    # stderr-based parsing and preserve the explicit timeout wording.
    if result.get("timed_out"):
        return result.get("stderr", "Command timed out")

    stderr = (result.get("stderr") or "").strip()
    if not stderr:
        return "Command failed without diagnostic output"

    try:
        # The CLI emits JSON error envelopes on failure; unwrap them when
        # possible so upstream tooling gets a stable, concise message.
        payload = json.loads(stderr)
    except json.JSONDecodeError:
        return stderr

    if isinstance(payload, dict) and payload.get("error"):
        return str(payload["error"])
    return stderr


def _unwrap_collection(data: object, key: str) -> list[dict] | None:
    """Normalize list-style CLI JSON payloads with optional metadata envelopes."""
    # Some commands return a bare list while others wrap the list in a top-level
    # object. This helper accepts either form and filters to dict rows only.
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        items = data.get(key)
        if isinstance(items, list):
            return [item for item in items if isinstance(item, dict)]
    return None


def _require_collection(result: dict, *, key: str, action: str, stage: str = "orchestrator") -> list[dict]:
    """Extract a collection payload or raise an orchestrator error."""
    # Collection-style helpers share the same success criteria: the subprocess
    # must complete cleanly, stdout must parse as JSON, and the payload shape
    # must match the expected list-or-envelope contract.
    if not result["success"]:
        raise OrchestratorError(
            f"{action} failed with exit code {result.get('exit_code', 1)}: {_extract_error_text(result)}",
            stage=stage,
            result=result,
        )
    if result.get("parse_error"):
        raise OrchestratorError(f"{action} returned invalid JSON output", stage=stage, result=result)
    if "data" not in result:
        raise OrchestratorError(f"{action} returned no JSON payload", stage=stage, result=result)

    items = _unwrap_collection(result.get("data"), key)
    if items is None:
        raise OrchestratorError(f"{action} returned unexpected JSON shape", stage=stage, result=result)
    return items


def _validate_config_result(
    *,
    shared_args: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> dict:
    """Run validation and preserve CLI diagnostics for callers that need them."""
    # Keep validation as a thin wrapper so callers can either consume the raw
    # diagnostics or collapse them into a simple bool with validate_config().
    return _run(["--validate-config"], shared_args=shared_args, timeout=timeout)


def _resolve_caller_path(path_str: str) -> str:
    """Resolve relative paths against the caller's working directory."""
    if path_str == "-":
        return path_str

    # The wrapped CLI runs with --project anchored to this repo, but file paths
    # should still behave as if the caller invoked the CLI directly from cwd.
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
    # Resolution order is explicit IDs first, then active discovery, then the
    # DATA_VIEWS environment fallback. Returning the source makes batch output
    # easier for CI and agents to explain upstream.
    if args.data_views:
        return args.data_views, "argv"

    if args.discover:
        discovered_rows = list_dataviews(shared_args=shared_args, timeout=args.timeout)
        data_views: list[str] = []
        for index, row in enumerate(discovered_rows, start=1):
            # Discovery is only useful if every returned row has a concrete ID;
            # fail fast so automation does not silently skip malformed entries.
            data_view_id = row.get("id")
            if not data_view_id:
                raise OrchestratorError(
                    f"Data view discovery row {index} did not include an 'id' field",
                    stage="data_view_resolution",
                )
            data_views.append(str(data_view_id))
        return data_views, "discover"

    # DATA_VIEWS is intentionally comma-delimited so it can be injected cleanly
    # from CI systems without needing shell array support.
    env_data_views = [dv.strip() for dv in os.environ.get("DATA_VIEWS", "").split(",") if dv.strip()]
    if env_data_views:
        return env_data_views, "env"

    return [], "none"


def _combine_exit_codes(current: int, new_code: int) -> int:
    """Preserve policy/warn exit codes while failing closed on hard errors."""
    current = _normalize_exit_code(current)
    new_code = _normalize_exit_code(new_code)

    # Signal-style exits should dominate the aggregate so cancellations are not
    # rewritten into generic failures during batch runs.
    if _is_signal_exit_code(current):
        return current
    if _is_signal_exit_code(new_code):
        return new_code

    # After cancellation handling, fail closed on anything outside the wrapper's
    # documented contract and then preserve the highest-severity non-zero state.
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
    # Print a single JSON object to stdout so callers can redirect one stream
    # and still treat failures as structured data instead of scraping text logs.
    exit_code = result.get("exit_code") if result is not None else None
    interrupted = (
        stage == "interrupted"
        or bool(result is not None and result.get("interrupted"))
        or (isinstance(exit_code, int) and _is_signal_exit_code(exit_code))
    )
    payload: dict[str, object] = {
        "error": message,
        "stage": stage,
    }
    if exit_code is not None:
        payload["exit_code"] = exit_code
    if interrupted:
        payload["error_type"] = "interrupted"
        payload["interrupted"] = True
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
    # Force JSON to stdout so discovery is deterministic and does not depend on
    # whatever default output mode the CLI might use interactively.
    result = _run(
        ["--list-dataviews", "--format", "json", "--output", "-"],
        parse_json=True,
        shared_args=shared_args,
        timeout=timeout,
    )
    return _require_collection(result, key="dataViews", action="Data view discovery", stage="data_view_resolution")


def list_snapshots(
    snapshot_dir: str = "./snapshots",
    *,
    shared_args: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[dict]:
    """List existing snapshots for baseline management."""
    # Resolve paths from the caller's cwd before invoking the CLI so the wrapper
    # behaves like a normal command-line tool rather than like a repo-relative script.
    resolved_snapshot_dir = _resolve_caller_path(snapshot_dir)
    result = _run(
        ["--list-snapshots", "--snapshot-dir", resolved_snapshot_dir, "--format", "json", "--output", "-"],
        parse_json=True,
        shared_args=shared_args,
        timeout=timeout,
    )
    return _require_collection(result, key="snapshots", action="Snapshot discovery", stage="snapshot_discovery")


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
    # Default to JSON because orchestrators and agent frameworks usually want
    # the payload inline; filesystem-oriented formats remain opt-in.
    args = [data_view, "--format", fmt]
    if output_dir:
        args.extend(["--output-dir", _resolve_caller_path(output_dir)])
    if fmt in ("json", "csv"):
        # Machine-readable formats are most useful when the wrapper captures the
        # payload directly instead of forcing callers to inspect filesystem output.
        args.extend(["--output", "-"])
    if extra_args:
        # Preserve caller ordering for extra flags so advanced automation can
        # control downstream behavior without this wrapper needing new options.
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
    # Snapshot paths are caller-facing inputs, so normalize them before passing
    # them through the repo-anchored uv invocation.
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
    # Match the example automation behavior by creating the parent folder before
    # invoking the CLI; the CLI itself should not need to care how the path was prepared.
    Path(resolved_snapshot_path).parent.mkdir(parents=True, exist_ok=True)
    result = _run([data_view, "--snapshot", resolved_snapshot_path], shared_args=shared_args, timeout=timeout)
    result["data_view"] = data_view
    result["snapshot_path"] = resolved_snapshot_path
    return result


def main(argv: list[str] | None = None) -> int:
    """Standalone entry point: validate config, process data views, output JSON results."""
    parser = _build_parser()
    # Accept injected argv for tests while preserving normal CLI behavior when
    # the module is executed directly.
    raw_argv = sys.argv[1:] if argv is None else argv

    try:
        args = parser.parse_args(raw_argv)
    except OrchestratorArgumentError as exc:
        _emit_error(f"Invalid orchestrator arguments: {exc}", stage="arguments")
        return 1
    except SystemExit as exc:
        return int(exc.code)

    try:
        shared_args = _build_shared_args(args)
        data_views, source = _resolve_data_views(args, shared_args=shared_args)

        if not data_views:
            if source == "discover":
                # Treat "discover found nothing" as a successful no-op so scheduled
                # automation can report emptiness without being marked as failed.
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

        # Validate once before batch work so auth/config problems fail fast and do
        # not leave the wrapper mixing infrastructure errors with per-view results.
        validation_result = _validate_config_result(shared_args=shared_args, timeout=args.timeout)
        if not validation_result["success"]:
            _emit_error(
                f"Configuration validation failed: {_extract_error_text(validation_result)}",
                stage="validation",
                result=validation_result,
            )
            return _combine_exit_codes(0, int(validation_result.get("exit_code", 1)))

        results = []
        overall_exit = 0
        for dv in data_views:
            # Process each data view independently and preserve every child payload
            # so callers can inspect mixed-success batches in a single JSON report.
            result = run_sdr(dv, fmt="json", shared_args=shared_args, timeout=args.timeout)
            results.append(result)
            result_exit = int(result.get("exit_code", 1))
            overall_exit = _combine_exit_codes(overall_exit, result_exit)
            # Stop once a child reports interruption so the wrapper mirrors user or
            # runner intent instead of continuing to start more work after cancel.
            if _is_signal_exit_code(result_exit):
                break

        # Emit one final batch envelope regardless of mixed result quality so CI,
        # scripts, and agent runtimes only need to parse a single JSON document.
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
    except OrchestratorError as exc:
        _emit_error(str(exc), stage=exc.stage, result=exc.result)
        return _combine_exit_codes(0, int(exc.result.get("exit_code", 1)))
    except KeyboardInterrupt:
        _emit_error(
            "Orchestration interrupted before batch completion",
            stage="interrupted",
            result={"exit_code": _INTERRUPT_EXIT_CODE, "interrupted": True},
        )
        return _INTERRUPT_EXIT_CODE


if __name__ == "__main__":
    raise SystemExit(main())
