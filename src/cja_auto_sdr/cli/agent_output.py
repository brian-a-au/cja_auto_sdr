"""Centralized agent-mode output contract resolution.

This module is the **single authoritative source** for translating parser-era
``--agent-mode`` defaults into runtime-effective output state.  Every command
family that participates in the agent-output contract should call through here
rather than re-deriving stdout suppression and ``quiet`` rules locally.

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
from typing import TYPE_CHECKING

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

DISCOVERY_STDOUT_FORMATS: frozenset[str] = frozenset({"json", "csv", "table", "console"})
"""Discovery formats that may emit directly to stdout (effectively all)."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_STDOUT_ALIASES: frozenset[str] = frozenset({"-", "stdout"})


def is_stdout_path(path: str | None) -> bool:
    """Return whether *path* represents an explicit stdout destination."""
    return path in _STDOUT_ALIASES


def _cli_option_specified_fn():
    """Lazy import of ``_cli_option_specified`` from generator."""
    from cja_auto_sdr.generator import _cli_option_specified

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
