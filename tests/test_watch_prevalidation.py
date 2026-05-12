"""Prevalidation tests for watch-mode incompatible flag combinations.

These tests use subprocess to verify exit codes and stderr output — the
only reliable way to test _exit_error() (which calls sys.exit) and
argparse's own exit-2 behaviour in the same suite.
"""

import subprocess
import sys

import pytest


def _run(args):
    return subprocess.run(
        [sys.executable, "-m", "cja_auto_sdr", *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_interval_without_watch_exits_one():
    result = _run(["--interval", "1h"])
    assert result.returncode == 1
    assert "--watch" in result.stderr


def test_watch_threshold_without_watch_exits_one():
    result = _run(["--watch-threshold", "5"])
    assert result.returncode == 1
    assert "--watch" in result.stderr


def test_watch_without_interval_exits_one():
    result = _run(["--watch", "dv_abc"])
    assert result.returncode == 1
    assert "--interval" in result.stderr


@pytest.mark.parametrize(
    ("incompatible_flag", "flag_label"),
    [
        (["--format", "json"], "--format"),
        (["--output", "out.json"], "--output"),
        (["--org-report"], "--org-report"),
        (["--diff", "a.json", "b.json"], "--diff"),
        (["--quality-policy", "default"], "--quality-policy"),
        (["--fail-on-quality", "HIGH"], "--fail-on-quality"),
        (["--batch", "dv_x", "dv_y"], "--batch"),
        (["--list-dataviews"], "--list-dataviews"),
        (["--list-connections"], "--list-connections"),
        (["--list-datasets"], "--list-datasets"),
    ],
)
def test_watch_rejects_incompatible_flag(incompatible_flag, flag_label):
    result = _run(["--watch", "dv_abc", "--interval", "1h", *incompatible_flag])
    assert result.returncode == 1, f"expected exit 1 for {incompatible_flag}, got {result.returncode}"
    # Error message must name the conflicting flag.
    assert flag_label in result.stderr


def test_argparse_native_unknown_flag_still_exits_two():
    # Sanity check: the watch flag set does not include --on-change. Argparse rejects it
    # with the standard exit-2 unknown-flag error, distinct from our exit-1 semantic rejections.
    result = _run(["--watch", "dv_abc", "--interval", "1h", "--on-change", "ls"])
    assert result.returncode == 2


@pytest.mark.parametrize(
    ("incompatible_flag", "flag_label"),
    [
        (["--snapshot", "f.json"], "--snapshot"),
        (["--list-snapshots"], "--list-snapshots"),
        (["--prune-snapshots"], "--prune-snapshots"),
        (["--diff-snapshot", "f.json"], "--diff-snapshot"),
        (["--compare-with-prev"], "--compare-with-prev"),
        (["--compare-snapshots", "a.json", "b.json"], "--compare-snapshots"),
        (["--diff-labels", "A", "B"], "--diff-labels"),
        (["--inventory-summary"], "--inventory-summary"),
        (["--include-all-inventory"], "--include-all-inventory"),
        (["--git-init"], "--git-init"),
        (["--git-commit"], "--git-commit"),
        (["--git-push"], "--git-push"),
        (["--profile-list"], "--profile-list"),
        (["--profile-import", "foo", "foo.json"], "--profile-import"),
        (["--profile-add", "foo"], "--profile-add"),
        (["--profile-test", "foo"], "--profile-test"),
        (["--profile-show", "foo"], "--profile-show"),
        (["--stats"], "--stats"),
        (["--describe-dataview", "dv_x"], "--describe-dataview"),
        (["--list-metrics", "dv_x"], "--list-metrics"),
        (["--list-dimensions", "dv_x"], "--list-dimensions"),
        (["--list-segments", "dv_x"], "--list-segments"),
        (["--list-calculated-metrics", "dv_x"], "--list-calculated-metrics"),
        (["--trending-window", "5"], "--trending-window"),
    ],
)
def test_watch_rejects_snapshot_inventory_diff_profile_family(incompatible_flag, flag_label):
    """Each of these CLI modes has its own dispatcher upstream; without rejection
    rules they would silently take precedence over --watch instead of erroring."""
    result = _run(["--watch", "dv_abc", "--interval", "1h", *incompatible_flag])
    assert result.returncode == 1, f"expected exit 1 for {incompatible_flag}, got {result.returncode}"
    assert flag_label in result.stderr


def test_watch_rejects_data_view_name_input():
    """--watch values must be IDs (dv_*), not names — name resolution per cycle
    would be wasteful and produce confusing event payloads."""
    result = _run(["--watch", "Some Data View Name", "--interval", "1h"])
    assert result.returncode == 1
    assert "data view IDs" in result.stderr


def test_watch_rejects_numeric_only_input():
    """CJA data view IDs always have the dv_ prefix; numeric-only input is rejected
    (this differs from AA's RSID convention — the spec was corrected during implementation)."""
    result = _run(["--watch", "12345", "--interval", "1h"])
    assert result.returncode == 1
    assert "data view IDs" in result.stderr
