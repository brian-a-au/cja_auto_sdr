"""Shared exit-code helpers and reference output.

Lightweight — safe to import from ``__main__.py`` or wrapper scripts without
triggering heavyweight dependencies (pandas, cjapy, tqdm).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from typing import TextIO

SIGNAL_EXIT_BASE = 128
MAX_SIGNAL_NUMBER = 64
INTERRUPT_EXIT_CODE = SIGNAL_EXIT_BASE + 2


def normalize_subprocess_exit_code(code: int) -> int:
    """Convert negative subprocess signal exits into shell-style codes."""
    if code < 0:
        return SIGNAL_EXIT_BASE + abs(code)
    return code


def is_signal_exit_code(code: int) -> bool:
    """Return True when a code represents shell-style signal termination."""
    # 128 is the shell's signal-exit base marker; actual signal exits start at 129.
    return SIGNAL_EXIT_BASE < code <= (SIGNAL_EXIT_BASE + MAX_SIGNAL_NUMBER)


def combine_wrapper_exit_codes(current: int, new_code: int) -> int:
    """Preserve policy/warn exits while failing closed on unexpected wrapper codes."""
    current = normalize_subprocess_exit_code(current)
    new_code = normalize_subprocess_exit_code(new_code)

    if is_signal_exit_code(current):
        return current
    if is_signal_exit_code(new_code):
        return new_code

    if current not in (0, 1, 2, 3):
        current = 1
    if new_code not in (0, 1, 2, 3):
        new_code = 1

    if current == 1 or new_code == 1:
        return 1
    if current == 2 or new_code == 2:
        return 2
    if current == 3 or new_code == 3:
        return 3
    return 0


def _signal_name(signal_number: int) -> str | None:
    """Return a human-readable signal name for *signal_number*, or None."""
    import signal as _signal_module

    try:
        return _signal_module.Signals(signal_number).name
    except ValueError, AttributeError:
        return None


_KNOWN_EXIT_CODES: dict[int, tuple[str, str, list[str], str]] = {
    0: (
        "Success",
        "The CLI completed without errors or policy violations.",
        [
            "SDR generated successfully",
            "Diff comparison found no changes",
            "Validation or inspection command completed normally",
        ],
        "No action required.",
    ),
    1: (
        "Error occurred",
        "The CLI encountered a runtime or configuration error.",
        [
            "Configuration error (invalid credentials, missing file)",
            "API error (network, authentication, rate limit)",
            "Validation failed",
            "File I/O error",
        ],
        "Check stderr output or --run-summary-json for diagnostics.",
    ),
    2: (
        "Policy threshold exceeded",
        "A policy or governance condition failed, but the CLI did not crash.",
        [
            "Diff mode found changes",
            "--fail-on-quality threshold was reached",
            "--fail-on-threshold was reached in org-report mode",
        ],
        (
            "Treat as actionable, not as an infrastructure failure.\n"
            "  Parse --run-summary-json for structured context when available."
        ),
    ),
    3: (
        "Warning threshold exceeded",
        "A diff warning threshold was crossed, but the hard policy limit was not.",
        [
            "Triggered by --warn-threshold PERCENT in diff mode",
            "Change percentage exceeded the warning boundary",
        ],
        (
            "Decide whether this is acceptable for your workflow.\n"
            "  Use --run-summary-json to inspect exact change metrics."
        ),
    ),
    130: (
        "Interrupted (SIGINT)",
        "The process was interrupted by the user or a controlling script.",
        [
            "Ctrl+C pressed during execution",
            "Process received SIGINT from a CI runner or wrapper",
        ],
        "Re-run the command if the interruption was unintentional.",
    ),
}


def explain_exit_code(code: int, file: TextIO | None = None) -> None:
    """Print a human-readable explanation of *code* to *file* (default stdout).

    This is the shared explainer used by both the fast-path ``__main__.py``
    interception and the deferred ``generator.py`` dispatch.
    """
    import sys as _sys

    dest = file if file is not None else _sys.stdout

    entry = _KNOWN_EXIT_CODES.get(code)

    if entry is not None:
        title, meaning, causes, guidance = entry
        print(f"Exit code {code}: {title}", file=dest)
        print(file=dest)
        print("Meaning:", file=dest)
        print(f"  {meaning}", file=dest)
        print(file=dest)
        print("Common causes:", file=dest)
        for cause in causes:
            print(f"  - {cause}", file=dest)
        print(file=dest)
        print("Automation guidance:", file=dest)
        print(f"  {guidance}", file=dest)
        return

    # Signal-exit codes (129-192) — use existing helpers
    if is_signal_exit_code(code):
        signal_number = code - SIGNAL_EXIT_BASE
        sig_name = _signal_name(signal_number)
        label = sig_name or f"signal {signal_number}"
        print(f"Exit code {code}: Killed by {label}", file=dest)
        print(file=dest)
        print("Meaning:", file=dest)
        print(f"  The process was terminated by {label} (128 + {signal_number}).", file=dest)
        print(file=dest)
        print("Common causes:", file=dest)
        print(f"  - The operating system or a supervisor sent {label}", file=dest)
        print("  - OOM killer, timeout wrapper, or CI job cancellation", file=dest)
        print(file=dest)
        print("Automation guidance:", file=dest)
        print("  Investigate the execution environment rather than the CLI itself.", file=dest)
        print("  Parse --run-summary-json for partial results when available.", file=dest)
        return

    # Unknown code
    print(f"Exit code {code}: Unknown", file=dest)
    print(file=dest)
    print("Meaning:", file=dest)
    print(f"  Exit code {code} is not a recognized CJA Auto SDR exit code.", file=dest)
    print(file=dest)
    print("Automation guidance:", file=dest)
    print("  Inspect --run-summary-json for structured diagnostics.", file=dest)
    print("  Known exit codes: 0 (success), 1 (error), 2 (policy), 3 (warning),", file=dest)
    print("  130 (SIGINT), 129-192 (signal termination).", file=dest)


def print_exit_codes(banner_width: int = 60) -> None:
    """Print the exit-code reference table to stdout."""
    print("=" * banner_width)
    print("EXIT CODE REFERENCE")
    print("=" * banner_width)
    print()
    print("  Code  Meaning")
    print("  ----  " + "-" * 50)
    print("    0   Success")
    print("        - SDR generated successfully")
    print("        - Diff comparison: no changes found")
    print("        - Validation passed")
    print()
    print("    1   Error occurred")
    print("        - Configuration error (invalid credentials, missing file)")
    print("        - API error (network, authentication, rate limit)")
    print("        - Validation failed")
    print("        - File I/O error")
    print()
    print("    2   Policy threshold exceeded (not a runtime error)")
    print("        - Diff mode: changes found")
    print("        - SDR mode: quality gate failed (--fail-on-quality)")
    print("        - Org mode: governance threshold failed (--fail-on-threshold)")
    print()
    print("    3   Diff: Warning threshold exceeded")
    print("        - Triggered by --warn-threshold PERCENT")
    print("        - Example: cja_auto_sdr --diff dv_A dv_B --warn-threshold 10")
    print("        - Exits 3 if change percentage > threshold")
    print()
    print("=" * banner_width)
    print("CI/CD Examples:")
    print("=" * banner_width)
    print()
    print("  # Fail CI if any changes detected")
    print("  cja_auto_sdr --diff dv_prod dv_staging --quiet")
    print("  if [ $? -eq 2 ]; then echo 'Changes detected!'; exit 1; fi")
    print()
    print("  # Fail CI only if >10% changes")
    print("  cja_auto_sdr --diff dv_A dv_B --warn-threshold 10 --quiet")
    print()
