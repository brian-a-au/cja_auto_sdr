"""Shared helpers for argparse-compatible long-option token resolution."""

from __future__ import annotations

import sys
from typing import NamedTuple


class LongOptionResolution(NamedTuple):
    """Resolution outcome for a long-option token."""

    canonical_option: str | None
    is_ambiguous: bool


def resolve_long_option_token(option_text: str, known_long_options: frozenset[str]) -> LongOptionResolution:
    """Resolve a token to a canonical long option if argparse would accept it.

    Returns ``is_ambiguous=True`` when an abbreviation matches multiple options.
    """
    option_name = option_text.split("=", 1)[0]
    if not option_name.startswith("--") or option_name == "--":
        return LongOptionResolution(canonical_option=None, is_ambiguous=False)
    if option_name in known_long_options:
        return LongOptionResolution(canonical_option=option_name, is_ambiguous=False)

    matches = [option for option in known_long_options if option.startswith(option_name)]
    if len(matches) == 1:
        return LongOptionResolution(canonical_option=matches[0], is_ambiguous=False)
    if len(matches) > 1:
        return LongOptionResolution(canonical_option=None, is_ambiguous=True)
    return LongOptionResolution(canonical_option=None, is_ambiguous=False)


def explicit_long_option_dests(
    argv: list[str] | None,
    *,
    tracked_options: set[str],
    known_long_options: frozenset[str],
) -> set[str]:
    """Return argparse dest names for explicitly provided long options.

    Only checks options in tracked_options. Resolves abbreviations against
    the full known_long_options set. When argv is None, falls back to sys.argv[1:].
    """
    tokens = argv if argv is not None else sys.argv[1:]
    found_dests: set[str] = set()
    for token in tokens:
        resolution = resolve_long_option_token(token, known_long_options)
        if resolution.canonical_option is not None and resolution.canonical_option in tracked_options:
            # Convert --log-format to log_format
            dest = resolution.canonical_option.lstrip("-").replace("-", "_")
            found_dests.add(dest)
    return found_dests
