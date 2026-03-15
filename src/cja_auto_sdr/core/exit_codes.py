"""Shared exit-code helpers and reference output.

Lightweight — safe to import from ``__main__.py`` or wrapper scripts without
triggering heavyweight dependencies (pandas, cjapy, tqdm).
"""

from __future__ import annotations

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
    return SIGNAL_EXIT_BASE < code <= (SIGNAL_EXIT_BASE + MAX_SIGNAL_NUMBER)


def combine_wrapper_exit_codes(current: int, new_code: int) -> int:
    """Preserve policy/warn exits while failing closed on unexpected wrapper codes."""
    current = normalize_subprocess_exit_code(current)
    new_code = normalize_subprocess_exit_code(new_code)

    if is_signal_exit_code(current):
        return current
    if is_signal_exit_code(new_code):
        return new_code

    if new_code not in (0, 1, 2, 3):
        new_code = 1

    if current == 1 or new_code == 1:
        return 1
    if current == 2 or new_code == 2:
        return 2
    if current == 3 or new_code == 3:
        return 3
    return 0


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
