from __future__ import annotations

import json
import logging
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from cja_auto_sdr.core.error_policies import RECOVERABLE_GIT_SUBPROCESS_EXCEPTIONS
from cja_auto_sdr.core.version import __version__
from cja_auto_sdr.diff.models import DataViewSnapshot, DiffResult


def _snapshot_pathspecs_for_data_view(snapshot_dir: Path, data_view_id: str) -> list[str]:
    """Return repo-relative snapshot paths for a specific data view."""
    suffix = f"_{data_view_id}"
    try:
        return sorted(child.name for child in snapshot_dir.iterdir() if child.is_dir() and child.name.endswith(suffix))
    except OSError:
        return []


def _run_git_command(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout: int,
    text: bool = True,
) -> tuple[subprocess.CompletedProcess | None, Exception | None]:
    """Run a git command behind a non-throwing boundary."""
    try:
        return (
            subprocess.run(
                args,
                cwd=str(cwd) if cwd is not None else None,
                capture_output=True,
                text=text,
                timeout=timeout,
            ),
            None,
        )
    except RECOVERABLE_GIT_SUBPROCESS_EXCEPTIONS as exc:
        return None, exc


def _format_git_boundary_error(exc: Exception, *, timeout_message: str, generic_prefix: str) -> str:
    if isinstance(exc, subprocess.TimeoutExpired):
        return timeout_message
    if isinstance(exc, FileNotFoundError):
        return "Git not found - ensure Git is installed and in PATH"
    return f"{generic_prefix}: {exc!s}"


def is_git_repository(path: Path) -> bool:
    """Check if the given path is inside a Git repository."""
    result, error = _run_git_command(["git", "rev-parse", "--git-dir"], cwd=path, timeout=10, text=True)
    if error is not None or result is None:
        return False
    return result.returncode == 0


def git_get_user_info() -> tuple[str, str]:
    """Get Git user name and email from config."""
    name = "CJA SDR Generator"
    email = ""

    result, error = _run_git_command(["git", "config", "user.name"], timeout=5, text=True)
    if error is None and result is not None and result.returncode == 0 and result.stdout.strip():
        name = result.stdout.strip()

    result, error = _run_git_command(["git", "config", "user.email"], timeout=5, text=True)
    if error is None and result is not None and result.returncode == 0 and result.stdout.strip():
        email = result.stdout.strip()

    return name, email


def save_git_friendly_snapshot(
    snapshot: DataViewSnapshot,
    output_dir: Path,
    quality_issues: list[dict] | None = None,
    logger: logging.Logger | None = None,
) -> dict[str, Path]:
    """Save snapshot in Git-friendly format (separate JSON files)."""
    logger = logger or logging.getLogger(__name__)

    safe_name = "".join(c if c.isalnum() or c in "-_" else "_" for c in snapshot.data_view_name)
    safe_name = safe_name[:50] if safe_name else snapshot.data_view_id
    dv_dir = output_dir / f"{safe_name}_{snapshot.data_view_id}"
    dv_dir.mkdir(parents=True, exist_ok=True)

    saved_files = {}

    metrics_sorted = sorted(snapshot.metrics, key=lambda x: x.get("id", ""))
    metrics_file = dv_dir / "metrics.json"
    with open(metrics_file, "w", encoding="utf-8") as f:
        json.dump(metrics_sorted, f, indent=2, ensure_ascii=False, default=str)
    saved_files["metrics"] = metrics_file
    logger.debug(f"Saved {len(metrics_sorted)} metrics to {metrics_file}")

    dimensions_sorted = sorted(snapshot.dimensions, key=lambda x: x.get("id", ""))
    dimensions_file = dv_dir / "dimensions.json"
    with open(dimensions_file, "w", encoding="utf-8") as f:
        json.dump(dimensions_sorted, f, indent=2, ensure_ascii=False, default=str)
    saved_files["dimensions"] = dimensions_file
    logger.debug(f"Saved {len(dimensions_sorted)} dimensions to {dimensions_file}")

    if snapshot.calculated_metrics_inventory is not None:
        calc_metrics_sorted = sorted(
            snapshot.calculated_metrics_inventory,
            key=lambda x: x.get("id", x.get("metric_id", "")),
        )
        calc_metrics_file = dv_dir / "calculated-metrics.json"
        with open(calc_metrics_file, "w", encoding="utf-8") as f:
            json.dump(calc_metrics_sorted, f, indent=2, ensure_ascii=False, default=str)
        saved_files["calculated_metrics"] = calc_metrics_file
        logger.debug(f"Saved {len(calc_metrics_sorted)} calculated metrics to {calc_metrics_file}")

    if snapshot.segments_inventory is not None:
        segments_sorted = sorted(snapshot.segments_inventory, key=lambda x: x.get("id", x.get("segment_id", "")))
        segments_file = dv_dir / "segments.json"
        with open(segments_file, "w", encoding="utf-8") as f:
            json.dump(segments_sorted, f, indent=2, ensure_ascii=False, default=str)
        saved_files["segments"] = segments_file
        logger.debug(f"Saved {len(segments_sorted)} segments to {segments_file}")

    metadata = {
        "snapshot_version": snapshot.snapshot_version,
        "created_at": snapshot.created_at,
        "data_view_id": snapshot.data_view_id,
        "data_view_name": snapshot.data_view_name,
        "owner": snapshot.owner,
        "description": snapshot.description,
        "tool_version": __version__,
        "summary": {
            "metrics_count": len(snapshot.metrics),
            "dimensions_count": len(snapshot.dimensions),
            "total_components": len(snapshot.metrics) + len(snapshot.dimensions),
        },
    }

    if snapshot.calculated_metrics_inventory is not None or snapshot.segments_inventory is not None:
        metadata["inventory"] = {}
        if snapshot.calculated_metrics_inventory is not None:
            metadata["inventory"]["calculated_metrics_count"] = len(snapshot.calculated_metrics_inventory)
        if snapshot.segments_inventory is not None:
            metadata["inventory"]["segments_count"] = len(snapshot.segments_inventory)

    if quality_issues:
        severity_counts = {}
        for issue in quality_issues:
            sev = issue.get("Severity", "UNKNOWN")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1
        metadata["quality"] = {"total_issues": len(quality_issues), "by_severity": severity_counts}

    metadata_file = dv_dir / "metadata.json"
    with open(metadata_file, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False, default=str)
    saved_files["metadata"] = metadata_file
    logger.debug(f"Saved metadata to {metadata_file}")

    return saved_files


def generate_git_commit_message(
    data_view_id: str,
    data_view_name: str,
    metrics_count: int,
    dimensions_count: int,
    quality_issues: list[dict] | None = None,
    diff_result: DiffResult = None,
    custom_message: str | None = None,
) -> str:
    """Generate a descriptive Git commit message for SDR snapshot."""
    timestamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M")

    if custom_message:
        subject = f"[{data_view_id}] {custom_message}"
    else:
        subject = f"[{data_view_id}] SDR snapshot {timestamp}"

    lines = [subject, ""]

    lines.append(f"Data View: {data_view_name}")
    lines.append(f"ID: {data_view_id}")
    lines.append(f"Components: {metrics_count} metrics, {dimensions_count} dimensions")
    lines.append("")

    if diff_result and diff_result.summary.has_changes:
        summary = diff_result.summary
        lines.append("Changes:")
        if summary.metrics_added > 0:
            lines.append(f"  + {summary.metrics_added} metrics added")
        if summary.metrics_removed > 0:
            lines.append(f"  - {summary.metrics_removed} metrics removed")
        if summary.metrics_modified > 0:
            lines.append(f"  ~ {summary.metrics_modified} metrics modified")
        if summary.dimensions_added > 0:
            lines.append(f"  + {summary.dimensions_added} dimensions added")
        if summary.dimensions_removed > 0:
            lines.append(f"  - {summary.dimensions_removed} dimensions removed")
        if summary.dimensions_modified > 0:
            lines.append(f"  ~ {summary.dimensions_modified} dimensions modified")
        lines.append("")

    if quality_issues:
        severity_counts = {}
        for issue in quality_issues:
            sev = issue.get("Severity", "UNKNOWN")
            severity_counts[sev] = severity_counts.get(sev, 0) + 1

        lines.append("Quality:")
        for sev in ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]:
            count = severity_counts.get(sev, 0)
            if count > 0:
                lines.append(f"  {sev}: {count}")
        lines.append("")

    lines.append(f"Generated by CJA SDR Generator v{__version__}")

    return "\n".join(lines)


def git_commit_snapshot(
    snapshot_dir: Path,
    data_view_id: str,
    data_view_name: str,
    metrics_count: int,
    dimensions_count: int,
    quality_issues: list[dict] | None = None,
    diff_result: DiffResult = None,
    custom_message: str | None = None,
    push: bool = False,
    logger: logging.Logger | None = None,
) -> tuple[bool, str]:
    """Commit snapshot files to Git with auto-generated message."""
    logger = logger or logging.getLogger(__name__)

    if not is_git_repository(snapshot_dir):
        return False, f"Not a Git repository: {snapshot_dir}"

    logger.info(f"Staging snapshot files in {snapshot_dir}")
    pathspecs = _snapshot_pathspecs_for_data_view(snapshot_dir, data_view_id)
    if not pathspecs:
        return False, f"No snapshot directory found for data view '{data_view_id}' in {snapshot_dir}"

    result, error = _run_git_command(["git", "add", "-A", "--", *pathspecs], cwd=snapshot_dir, timeout=30, text=True)
    if error is not None:
        return False, _format_git_boundary_error(
            error, timeout_message="Git operation timed out", generic_prefix="Git error"
        )
    if result is None:
        return False, "Git error: unknown subprocess failure"
    if result.returncode != 0:
        return False, f"git add failed: {result.stderr}"

    result, error = _run_git_command(["git", "diff", "--cached", "--quiet"], cwd=snapshot_dir, timeout=10, text=False)
    if error is not None:
        return False, _format_git_boundary_error(
            error, timeout_message="Git operation timed out", generic_prefix="Git error"
        )
    if result is None:
        return False, "Git error: unknown subprocess failure"
    if result.returncode == 0:
        logger.info("No changes to commit (snapshot unchanged)")
        return True, "no_changes"

    commit_message = generate_git_commit_message(
        data_view_id=data_view_id,
        data_view_name=data_view_name,
        metrics_count=metrics_count,
        dimensions_count=dimensions_count,
        quality_issues=quality_issues,
        diff_result=diff_result,
        custom_message=custom_message,
    )

    logger.info("Committing snapshot to Git")
    result, error = _run_git_command(["git", "commit", "-m", commit_message], cwd=snapshot_dir, timeout=30, text=True)
    if error is not None:
        return False, _format_git_boundary_error(
            error, timeout_message="Git operation timed out", generic_prefix="Git error"
        )
    if result is None:
        return False, "Git error: unknown subprocess failure"
    if result.returncode != 0:
        return False, f"git commit failed: {result.stderr}"

    result, error = _run_git_command(["git", "rev-parse", "HEAD"], cwd=snapshot_dir, timeout=10, text=True)
    if error is not None:
        return False, _format_git_boundary_error(
            error, timeout_message="Git operation timed out", generic_prefix="Git error"
        )
    if result is None:
        return False, "Git error: unknown subprocess failure"
    commit_sha = result.stdout.strip()[:8] if result.returncode == 0 else "unknown"

    logger.info(f"Committed snapshot: {commit_sha}")

    if push:
        logger.info("Pushing to remote")
        result, error = _run_git_command(["git", "push"], cwd=snapshot_dir, timeout=60, text=True)
        if error is not None:
            logger.warning(
                "git push failed: %s",
                _format_git_boundary_error(
                    error, timeout_message="Git operation timed out", generic_prefix="Git error"
                ),
            )
            return True, f"{commit_sha} (push failed: {error!s})"
        if result is None:
            logger.warning("git push failed: unknown subprocess failure")
            return True, f"{commit_sha} (push failed: unknown subprocess failure)"
        if result.returncode != 0:
            logger.warning(f"git push failed: {result.stderr}")
            return True, f"{commit_sha} (push failed: {result.stderr.strip()})"
        logger.info("Pushed to remote successfully")

    return True, commit_sha


def git_init_snapshot_repo(directory: Path, logger: logging.Logger | None = None) -> tuple[bool, str]:
    """Initialize a new Git repository for snapshots."""
    logger = logger or logging.getLogger(__name__)

    try:
        directory.mkdir(parents=True, exist_ok=True)

        if is_git_repository(directory):
            return True, "Already a Git repository"

        logger.info(f"Initializing Git repository in {directory}")
        result, error = _run_git_command(["git", "init"], cwd=directory, timeout=30, text=True)
        if error is not None:
            return False, _format_git_boundary_error(
                error,
                timeout_message="Initialization timed out",
                generic_prefix="Initialization failed",
            )
        if result is None:
            return False, "Initialization failed: unknown subprocess failure"
        if result.returncode != 0:
            return False, f"git init failed: {result.stderr}"

        # Configure local identity to make initial commit deterministic.
        user_name, user_email = git_get_user_info()
        if not user_email:
            user_email = "cja-auto-sdr@local"

        result, error = _run_git_command(
            ["git", "config", "user.name", user_name],
            cwd=directory,
            timeout=30,
            text=True,
        )
        if error is not None:
            return False, _format_git_boundary_error(
                error,
                timeout_message="Initialization timed out",
                generic_prefix="Initialization failed",
            )
        if result is None:
            return False, "Initialization failed: unknown subprocess failure"
        if result.returncode != 0:
            return False, f"git config user.name failed: {result.stderr}"

        result, error = _run_git_command(
            ["git", "config", "user.email", user_email],
            cwd=directory,
            timeout=30,
            text=True,
        )
        if error is not None:
            return False, _format_git_boundary_error(
                error,
                timeout_message="Initialization timed out",
                generic_prefix="Initialization failed",
            )
        if result is None:
            return False, "Initialization failed: unknown subprocess failure"
        if result.returncode != 0:
            return False, f"git config user.email failed: {result.stderr}"

        gitignore = directory / ".gitignore"
        gitignore.write_text("# CJA SDR Snapshots\n*.log\n*.tmp\n.DS_Store\n")

        readme = directory / "README.md"
        readme.write_text(f"""# CJA SDR Snapshots

This repository contains Solution Design Reference (SDR) snapshots from Adobe Customer Journey Analytics.

## Structure

```
<data_view_name>_<data_view_id>/
├── metrics.json      # All metrics (sorted by ID)
├── dimensions.json   # All dimensions (sorted by ID)
└── metadata.json     # Data view info and quality summary
```

## Usage

View history:
```bash
git log --oneline
```

Compare versions:
```bash
git diff HEAD~1 HEAD -- <data_view_dir>/metrics.json
```

---
Generated by CJA SDR Generator v{__version__}
""")

        result, error = _run_git_command(["git", "add", "."], cwd=directory, timeout=30, text=True)
        if error is not None:
            return False, _format_git_boundary_error(
                error,
                timeout_message="Initialization timed out",
                generic_prefix="Initialization failed",
            )
        if result is None:
            return False, "Initialization failed: unknown subprocess failure"
        if result.returncode != 0:
            return False, f"git add failed: {result.stderr}"

        result, error = _run_git_command(
            ["git", "commit", "-m", "Initialize SDR snapshot repository"],
            cwd=directory,
            timeout=30,
            text=True,
        )
        if error is not None:
            return False, _format_git_boundary_error(
                error,
                timeout_message="Initialization timed out",
                generic_prefix="Initialization failed",
            )
        if result is None:
            return False, "Initialization failed: unknown subprocess failure"
        if result.returncode != 0:
            return False, f"git commit failed: {result.stderr}"

        logger.info(f"Initialized Git repository: {directory}")
        return True, "Repository initialized"

    except OSError as e:
        return False, f"Initialization failed: {e!s}"
