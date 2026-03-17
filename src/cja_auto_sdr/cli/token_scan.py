"""Shared token-level CLI scanning helpers.

These helpers inspect argv using the configured parser's option metadata
without coercing typed values. The entrypoint fast path uses the tolerant
default so argparse actions like ``--version`` can still win over unrelated
unknown flags, while generator-side standalone prevalidation can opt into a
strict fail-closed mode.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal, NamedTuple

from cja_auto_sdr.cli.option_resolution import resolve_long_option_token as _resolve_long_option_token


class OptionSpec(NamedTuple):
    """Minimal option metadata needed for token scanning."""

    min_arity: int
    accepts_inline_value: bool
    dest: str


class OptionScanResult(NamedTuple):
    """Token scan outcome: resolved options, positionals, and parse validity."""

    options: tuple[str, ...]
    positionals: tuple[str, ...]
    has_parse_error: bool


class OptionOccurrence(NamedTuple):
    """A recognized option occurrence with canonical argv tokens."""

    canonical_option: str
    argv_tokens: tuple[str, ...]


class OptionOccurrenceScanResult(NamedTuple):
    """Token scan outcome with canonicalized option occurrences."""

    occurrences: tuple[OptionOccurrence, ...]
    positionals: tuple[str, ...]
    has_parse_error: bool

    @property
    def options(self) -> tuple[str, ...]:
        """Return canonical option names in encounter order."""
        return tuple(occurrence.canonical_option for occurrence in self.occurrences)


class OptionScanSpec(NamedTuple):
    """Cached parser metadata used by token scanning."""

    known_long_options: frozenset[str]
    option_specs: dict[str, OptionSpec]
    options_by_dest: dict[str, frozenset[str]]
    negative_number_matcher: Any
    has_negative_number_optionals: bool


class _ResolvedOptionToken(NamedTuple):
    """Internal classification for a single CLI token."""

    kind: Literal["recognized", "unknown", "ambiguous", "not_option"]
    occurrences: tuple[OptionOccurrence, ...] = ()
    pending_values: int = 0
    has_parse_error: bool = False

    @property
    def options(self) -> tuple[str, ...]:
        """Return canonical option names for recognized occurrences."""
        return tuple(occurrence.canonical_option for occurrence in self.occurrences)


def _accepts_inline_option_value(nargs: object) -> bool:
    """Return True when an option can legally consume explicit inline values."""
    return nargs != 0


def _minimum_option_arity(nargs: object) -> int:
    """Return the minimum positional values an option must consume."""
    if nargs is None:
        return 1
    if isinstance(nargs, int):
        return max(nargs, 0)
    if nargs == "+":
        return 1
    # Includes 0, "?", "*", argparse.REMAINDER, argparse.PARSER.
    return 0


@lru_cache(maxsize=1)
def option_scan_spec() -> OptionScanSpec:
    """Return parser-derived option metadata for token scanning."""
    from cja_auto_sdr.cli.parser import parse_arguments

    parser = parse_arguments(return_parser=True, enable_autocomplete=False)
    option_specs: dict[str, OptionSpec] = {}
    known_long_options: set[str] = set()
    options_by_dest: dict[str, set[str]] = {}

    # CPython argparse internals: `_actions` is the canonical source of
    # configured option metadata and keeps scanning aligned with argparse.
    for action in parser._actions:
        if not action.option_strings:
            continue
        action_nargs = getattr(action, "nargs", None)
        option_spec = OptionSpec(
            min_arity=_minimum_option_arity(action_nargs),
            accepts_inline_value=_accepts_inline_option_value(action_nargs),
            dest=action.dest,
        )
        for option in action.option_strings:
            option_specs[option] = option_spec
            options_by_dest.setdefault(action.dest, set()).add(option)
            if option.startswith("--"):
                known_long_options.add(option)

    return OptionScanSpec(
        known_long_options=frozenset(known_long_options),
        option_specs=option_specs,
        options_by_dest={dest: frozenset(options) for dest, options in options_by_dest.items()},
        negative_number_matcher=getattr(parser, "_negative_number_matcher", None),
        has_negative_number_optionals=bool(getattr(parser, "_has_negative_number_optionals", ())),
    )


def _is_negative_number_token(arg: str, scan_spec: OptionScanSpec) -> bool:
    """Return True when argparse would treat *arg* as a negative numeric value."""
    if scan_spec.has_negative_number_optionals:
        return False
    matcher = scan_spec.negative_number_matcher
    return bool(matcher and matcher.match(arg))


def _normalize_short_attached_value(attached_value: str) -> str:
    """Normalize argparse-style short-option attached values.

    ``-pVALUE`` passes ``VALUE`` through unchanged, while ``-p=VALUE`` treats
    the first ``=`` as a separator rather than as part of the value.
    """
    if attached_value.startswith("="):
        return attached_value[1:]
    return attached_value


def _resolve_option_token(arg: str, scan_spec: OptionScanSpec) -> _ResolvedOptionToken:
    """Resolve *arg* against argparse option metadata without coercing values."""
    if arg.startswith("--"):
        option_name, has_equals, _inline_value = arg.partition("=")
        long_resolution = _resolve_long_option_token(option_name, scan_spec.known_long_options)
        if long_resolution.is_ambiguous:
            return _ResolvedOptionToken(kind="ambiguous")

        canonical_option = long_resolution.canonical_option
        if canonical_option is None:
            return _ResolvedOptionToken(kind="unknown")

        option_spec = scan_spec.option_specs.get(canonical_option)
        if option_spec is None:
            return _ResolvedOptionToken(kind="unknown")
        if has_equals and not option_spec.accepts_inline_value:
            return _ResolvedOptionToken(kind="recognized", has_parse_error=True)

        inline_values = 1 if has_equals and option_spec.accepts_inline_value else 0
        occurrence_tokens = (canonical_option, _inline_value) if has_equals else (canonical_option,)
        return _ResolvedOptionToken(
            kind="recognized",
            occurrences=(OptionOccurrence(canonical_option, occurrence_tokens),),
            pending_values=max(option_spec.min_arity - inline_values, 0),
        )

    if arg.startswith("-") and arg != "-":
        option_spec = scan_spec.option_specs.get(arg)
        if option_spec is not None:
            return _ResolvedOptionToken(
                kind="recognized",
                occurrences=(OptionOccurrence(arg, (arg,)),),
                pending_values=option_spec.min_arity,
            )

        if _is_negative_number_token(arg, scan_spec):
            return _ResolvedOptionToken(kind="not_option")

        if len(arg) == 2:
            return _ResolvedOptionToken(kind="unknown")

        resolved_occurrences: list[OptionOccurrence] = []
        cluster = arg[1:]
        for short_index, short_name in enumerate(cluster):
            short_option = f"-{short_name}"
            option_spec = scan_spec.option_specs.get(short_option)
            if option_spec is None:
                return _ResolvedOptionToken(kind="unknown", occurrences=tuple(resolved_occurrences))

            attached_value = cluster[short_index + 1 :]
            if option_spec.min_arity > 0:
                normalized_value = _normalize_short_attached_value(attached_value)
                occurrence_tokens = (short_option, normalized_value) if attached_value else (short_option,)
                resolved_occurrences.append(OptionOccurrence(short_option, occurrence_tokens))
                return _ResolvedOptionToken(
                    kind="recognized",
                    occurrences=tuple(resolved_occurrences),
                    pending_values=max(option_spec.min_arity - 1, 0) if attached_value else option_spec.min_arity,
                )
            resolved_occurrences.append(OptionOccurrence(short_option, (short_option,)))
            if attached_value.startswith(("=", "-")):
                return _ResolvedOptionToken(
                    kind="recognized",
                    occurrences=tuple(resolved_occurrences),
                    has_parse_error=True,
                )

        return _ResolvedOptionToken(kind="recognized", occurrences=tuple(resolved_occurrences))

    return _ResolvedOptionToken(kind="not_option")


def _value_token_starts_new_option(
    arg: str,
    scan_spec: OptionScanSpec,
) -> bool:
    """Return True when *arg* should terminate value consumption as a new option."""
    if arg == "--":
        return True

    resolution = _resolve_option_token(arg, scan_spec)
    return resolution.kind in {"recognized", "ambiguous", "unknown"}


def scan_option_occurrences(
    args: list[str],
    *,
    reject_unknown_options: bool = False,
) -> OptionOccurrenceScanResult:
    """Scan argv tokens argparse-style and retain canonical option/value tokens."""
    scan_spec = option_scan_spec()
    pending_option_values = 0
    resolved_occurrences: list[OptionOccurrence] = []
    positionals: list[str] = []

    index = 0
    while index < len(args):
        arg = args[index]

        if pending_option_values > 0:
            if _value_token_starts_new_option(arg, scan_spec):
                return OptionOccurrenceScanResult(
                    occurrences=tuple(resolved_occurrences),
                    positionals=tuple(positionals),
                    has_parse_error=True,
                )
            last_occurrence = resolved_occurrences[-1]
            resolved_occurrences[-1] = OptionOccurrence(
                canonical_option=last_occurrence.canonical_option,
                argv_tokens=(*last_occurrence.argv_tokens, arg),
            )
            pending_option_values -= 1
            index += 1
            continue

        if arg == "--":
            positionals.extend(args[index + 1 :])
            break

        resolution = _resolve_option_token(arg, scan_spec)
        if resolution.kind == "ambiguous" or resolution.has_parse_error:
            return OptionOccurrenceScanResult(
                occurrences=tuple(resolved_occurrences),
                positionals=tuple(positionals),
                has_parse_error=True,
            )

        if resolution.kind == "recognized":
            resolved_occurrences.extend(resolution.occurrences)
            pending_option_values = resolution.pending_values
            index += 1
            continue

        if resolution.kind == "unknown":
            resolved_occurrences.extend(resolution.occurrences)
            if reject_unknown_options:
                return OptionOccurrenceScanResult(
                    occurrences=tuple(resolved_occurrences),
                    positionals=tuple(positionals),
                    has_parse_error=True,
                )
            index += 1
            continue

        positionals.append(arg)
        index += 1

    return OptionOccurrenceScanResult(
        occurrences=tuple(resolved_occurrences),
        positionals=tuple(positionals),
        has_parse_error=pending_option_values > 0,
    )


def scan_option_tokens(args: list[str], *, reject_unknown_options: bool = False) -> OptionScanResult:
    """Scan argv tokens argparse-style without coercing typed option values."""
    scan = scan_option_occurrences(args, reject_unknown_options=reject_unknown_options)
    return OptionScanResult(
        options=scan.options,
        positionals=scan.positionals,
        has_parse_error=scan.has_parse_error,
    )
