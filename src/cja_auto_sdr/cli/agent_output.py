"""Centralized agent-mode output contract resolution.

This module is the code-owned source of truth for agent-output capability
definitions and runtime-effective output state. Diff and org-report delegate
output-path and ``quiet`` recomputation here directly; discovery consumes the
same capability tables for its stdout normalization logic.

Design invariants
-----------------
* Explicit ``--output`` always wins — never suppress a user's explicit intent.
* Explicit ``--quiet`` always wins.
* ``quiet`` follows the **effective** stdout destination, not the parser-level
  preset that may have been suppressed for a file-only format.
* Each command family declares its own stdout-capable format set; the resolver
  is format-agnostic beyond that lookup.
"""

from __future__ import annotations

import argparse
import sys
from functools import lru_cache
from typing import TYPE_CHECKING

from cja_auto_sdr.cli.option_resolution import resolve_long_option_token

if TYPE_CHECKING:
    from collections.abc import Container

__all__ = [
    "DIFF_STDOUT_FORMATS",
    "DISCOVERY_STDOUT_FORMATS",
    "ORG_REPORT_STDOUT_FORMATS",
    "is_stdout_path",
    "resolve_agent_output_path",
    "resolve_agent_quiet",
]


# ---------------------------------------------------------------------------
# Command-family stdout capability tables
# ---------------------------------------------------------------------------

DIFF_STDOUT_FORMATS: frozenset[str] = frozenset({"json"})
"""Diff formats that may emit directly to stdout."""

ORG_REPORT_STDOUT_FORMATS: frozenset[str] = frozenset({"json", "console"})
"""Org-report formats that may emit directly to stdout."""

DISCOVERY_STDOUT_FORMATS: frozenset[str] = frozenset({"json", "csv"})
"""Discovery formats that remain stdout-capable under the agent-output contract."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STDOUT_ALIASES: frozenset[str] = frozenset({"-", "stdout"})


def is_stdout_path(path: str | None) -> bool:
    """Return whether *path* represents an explicit stdout destination."""
    return path in _STDOUT_ALIASES


@lru_cache(maxsize=1)
def _known_long_options() -> frozenset[str]:
    """Return canonical long-option strings from the configured CLI parser."""
    from cja_auto_sdr.cli.parser import parse_arguments

    parser = parse_arguments(return_parser=True, enable_autocomplete=False)
    return frozenset(
        option for action in parser._actions for option in action.option_strings if option.startswith("--")
    )


def _cli_option_specified(option_name: str, argv: list[str] | None = None) -> bool:
    """Return True if an option was explicitly provided via long-form token."""
    tokens = argv if argv is not None else sys.argv[1:]
    known_long_options = _known_long_options() if option_name.startswith("--") else frozenset()

    for token in tokens:
        if token == option_name or token.startswith(f"{option_name}="):
            return True

        if (
            option_name.startswith("--")
            and resolve_long_option_token(token, known_long_options).canonical_option == option_name
        ):
            return True

    return False


def _cli_option_specified_fn():
    """Indirection seam for tests patching explicit-option detection."""
    return _cli_option_specified


# ---------------------------------------------------------------------------
# Core resolvers
# ---------------------------------------------------------------------------


def resolve_agent_output_path(
    args: argparse.Namespace,
    *,
    output_format: str,
    stdout_formats: Container[str],
) -> str | None:
    """Resolve the effective output path after agent-mode default application.

    Returns the output path unchanged when:
    * ``--agent-mode`` is not active,
    * the caller explicitly passed ``--output``, or
    * the normalised format is in *stdout_formats*.

    Otherwise returns ``None``, signalling that the inherited agent-mode
    stdout default should be suppressed (file-only format).
    """
    output_path = getattr(args, "output", None)

    if not getattr(args, "agent_mode", False):
        return output_path

    if _cli_option_specified_fn()("--output"):
        return output_path

    if output_format in stdout_formats:
        return output_path

    return None


def resolve_agent_quiet(
    args: argparse.Namespace,
    *,
    output_path: str | None,
) -> bool:
    """Resolve the effective quiet flag from the **resolved** output path.

    Explicit ``--quiet`` always wins.  Otherwise quiet is derived solely from
    whether the effective output destination (after any agent-mode coercion)
    still targets stdout.
    """
    if _cli_option_specified_fn()("--quiet"):
        return True

    if is_stdout_path(getattr(args, "run_summary_json", None)):
        return True

    return is_stdout_path(output_path)
