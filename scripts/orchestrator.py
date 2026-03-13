"""Orchestrator for programmatic cja_auto_sdr automation.

Wraps the CLI via subprocess for use in CI/CD pipelines,
AI agent frameworks, and custom automation scripts.

Usage:
    python scripts/orchestrator.py              # Run with DATA_VIEWS env var
    python scripts/orchestrator.py dv_abc123    # Run with explicit data view IDs
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BASE_CMD = ["uv", "run", "cja_auto_sdr"]


def _run(args: list[str], *, parse_json: bool = False) -> dict:
    """Run a cja_auto_sdr command and return structured result."""
    result = subprocess.run(
        [*BASE_CMD, *args],
        capture_output=True,
        text=True,
    )
    output: dict = {
        "exit_code": result.returncode,
        "success": result.returncode == 0,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    if parse_json and result.stdout.strip():
        try:
            output["data"] = json.loads(result.stdout)
        except json.JSONDecodeError:
            output["data"] = None
            output["parse_error"] = True
    return output


def validate_config() -> bool:
    """Pre-flight credential and connectivity check.

    Returns True if validation passes (exit code 0).
    Note: --validate-config does not produce JSON output;
    this function relies on exit code only.
    """
    result = _run(["--validate-config"])
    return result["success"]


def list_dataviews() -> list[dict]:
    """Discover available data views as structured data."""
    result = _run(["--list-dataviews", "--format", "json", "--output", "-"], parse_json=True)
    if result["success"] and result.get("data"):
        return result["data"] if isinstance(result["data"], list) else [result["data"]]
    return []


def list_snapshots(snapshot_dir: str = "./snapshots") -> list[dict]:
    """List existing snapshots for baseline management."""
    result = _run(
        ["--list-snapshots", "--snapshot-dir", snapshot_dir, "--format", "json", "--output", "-"],
        parse_json=True,
    )
    if result["success"] and result.get("data"):
        return result["data"] if isinstance(result["data"], list) else [result["data"]]
    return []


def run_sdr(
    data_view: str,
    fmt: str = "json",
    output_dir: str | None = None,
    extra_args: list[str] | None = None,
) -> dict:
    """Generate SDR and return structured result."""
    args = [data_view, "--format", fmt]
    if output_dir:
        args.extend(["--output-dir", output_dir])
    if fmt in ("json", "csv"):
        args.extend(["--output", "-"])
    if extra_args:
        args.extend(extra_args)
    result = _run(args, parse_json=(fmt == "json"))
    result["data_view"] = data_view
    return result


def run_diff(data_view: str, snapshot_path: str) -> dict:
    """Drift detection against a baseline snapshot.

    Exit codes:
        0 = no changes
        1 = error
        2 = policy threshold exceeded (changes found)
        3 = warning threshold exceeded (--warn-threshold)
    """
    result = _run(
        [data_view, "--diff-snapshot", snapshot_path, "--format", "json", "--output", "-"],
        parse_json=True,
    )
    result["data_view"] = data_view
    result["has_changes"] = result["exit_code"] == 2
    result["threshold_exceeded"] = result["exit_code"] in (2, 3)
    return result


def run_snapshot(data_view: str, snapshot_path: str | None = None) -> dict:
    """Save a baseline snapshot.

    Args:
        data_view: Data view ID.
        snapshot_path: Output file path. Defaults to ./snapshots/<data_view>_baseline.json.
    """
    if snapshot_path is None:
        snapshot_path = f"./snapshots/{data_view}_baseline.json"
    Path(snapshot_path).parent.mkdir(parents=True, exist_ok=True)
    result = _run([data_view, "--snapshot", snapshot_path])
    result["data_view"] = data_view
    return result


def main() -> int:
    """Standalone entry point: validate config, process data views, output JSON results."""
    # Get data views from args or environment
    data_views = sys.argv[1:] or [
        dv.strip() for dv in (__import__("os").environ.get("DATA_VIEWS", "")).split(",") if dv.strip()
    ]

    if not data_views:
        print(json.dumps({"error": "No data views specified. Pass as args or set DATA_VIEWS env var."}))
        return 1

    # Pre-flight check
    if not validate_config():
        print(json.dumps({"error": "Configuration validation failed. Check credentials."}))
        return 1

    results = []
    for dv in data_views:
        result = run_sdr(dv, fmt="json")
        results.append(result)

    print(json.dumps({"data_views_processed": len(results), "results": results}, indent=2))
    return 0 if all(r["success"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
