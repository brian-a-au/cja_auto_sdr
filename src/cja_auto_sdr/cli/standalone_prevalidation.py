"""Wrapper-aware standalone argv sanitization for generator prevalidation.

This module is intentionally narrow: it only supports the generator's
standalone informational prevalidation flow. Generic raw option helpers must
stay aligned with argparse on the original argv and must not import this
behavior.
"""

from __future__ import annotations

import contextlib
import re
from collections.abc import Collection
from dataclasses import dataclass
from typing import Any

from cja_auto_sdr.cli.option_resolution import resolve_long_option_token as _resolve_long_option_token
from cja_auto_sdr.cli.token_scan import OptionOccurrence, _resolve_option_token
from cja_auto_sdr.cli.token_scan import option_scan_spec as _option_scan_spec
from cja_auto_sdr.cli.token_scan import scan_option_occurrences as _scan_option_occurrences

_IGNORED_UNKNOWN_LONG_OPTION_PREFIXES: tuple[str, ...] = ("--agent-", "--wrapper-")
_BOOLEAN_WRAPPER_VALUE_LITERALS = frozenset({"0", "1", "false", "no", "off", "on", "true", "yes"})
_IDENTIFIER_WRAPPER_OPTION_SUFFIX = "-id"
_FLAGLIKE_WRAPPER_OPTION_TAILS = frozenset(
    {
        "debug",
        "disable",
        "disabled",
        "dry-run",
        "enable",
        "enabled",
        "quiet",
        "trace",
        "verbose",
    },
)


def resolve_wrapper_aware_standalone_occurrences(
    argv: list[str],
    *,
    standalone_mode_options: Collection[str],
    metadata_options: Collection[str],
) -> tuple[OptionOccurrence, ...] | None:
    """Return a strict option scan after wrapper-aware standalone sanitization."""
    scan_spec = _option_scan_spec()
    standalone_option_set = frozenset(standalone_mode_options)
    metadata_option_set = frozenset(metadata_options)
    sanitization = _scan_standalone_sanitization(
        argv,
        scan_spec=scan_spec,
        standalone_mode_options=standalone_option_set,
        metadata_options=metadata_option_set,
    )
    if not all(
        _ignored_option_is_safe(
            ignored_option,
            scan_spec=scan_spec,
            standalone_mode_options=standalone_option_set,
            metadata_options=metadata_option_set,
        )
        for ignored_option in sanitization.ignored_options
    ):
        return None

    scan = _scan_option_occurrences(list(sanitization.filtered_argv), reject_unknown_options=True)
    if scan.has_parse_error or scan.positionals:
        return None
    return scan.occurrences


def resolve_wrapper_aware_metadata_occurrences(
    argv: list[str],
    *,
    metadata_options: Collection[str],
) -> tuple[OptionOccurrence, ...]:
    """Return metadata occurrences after wrapper-aware sanitization.

    Unlike standalone prevalidation, this recovery path tolerates unrelated
    argv ambiguity so run-summary metadata can still be primed for invalid
    invocations. It remains fail-closed for wrappers that could be mistaken
    for metadata values.
    """
    scan_spec = _option_scan_spec()
    metadata_option_set = frozenset(metadata_options)
    sanitization = _scan_standalone_sanitization(
        argv,
        scan_spec=scan_spec,
        standalone_mode_options=frozenset(),
        metadata_options=metadata_option_set,
    )
    if not all(
        _ignored_option_is_safe_for_metadata_priming(
            ignored_option,
            scan_spec=scan_spec,
            metadata_options=metadata_option_set,
        )
        for ignored_option in sanitization.ignored_options
    ):
        return ()

    return _collect_metadata_occurrences(
        list(sanitization.filtered_argv),
        scan_spec=scan_spec,
        metadata_options=metadata_option_set,
    )


def _token_starts_new_option(arg: str, *, scan_spec: Any) -> bool:
    """Return True when *arg* should terminate ignored wrapper-value consumption."""
    if arg == "--":
        return True
    if not arg.startswith("-") or arg == "-":
        return False

    negative_number_matcher = getattr(scan_spec, "negative_number_matcher", None)
    return not (
        not getattr(scan_spec, "has_negative_number_optionals", False)
        and negative_number_matcher
        and negative_number_matcher.match(arg)
    )


def _ignored_unknown_option_name(arg: str, *, scan_spec: Any) -> str | None:
    """Return the unknown wrapper/agent option name for ignored standalone scanning."""
    option_name, _has_equals, _inline_value = arg.partition("=")
    if not (arg.startswith("--") and option_name.startswith(_IGNORED_UNKNOWN_LONG_OPTION_PREFIXES)):
        return None

    long_resolution = _resolve_long_option_token(option_name, scan_spec.known_long_options)
    if long_resolution.canonical_option is not None or long_resolution.is_ambiguous:
        return None
    return option_name


def _wrapper_option_is_flaglike(option_name: str) -> bool:
    """Return True for wrapper flags that are conventionally valueless markers."""
    for prefix in _IGNORED_UNKNOWN_LONG_OPTION_PREFIXES:
        if option_name.startswith(prefix):
            return option_name.removeprefix(prefix) in _FLAGLIKE_WRAPPER_OPTION_TAILS
    return False


def _wrapper_value_is_boolean_literal(value_token: str) -> bool:
    """Return True when *value_token* is an explicit wrapper boolean payload."""
    return value_token.strip().lower() in _BOOLEAN_WRAPPER_VALUE_LITERALS


@dataclass(frozen=True)
class _IgnoredOption:
    """Ignored wrapper/agent option span captured during standalone sanitization."""

    option_name: str
    value_token: str | None
    value_attached: bool
    pending_option: str | None
    standalone_request_complete: bool


@dataclass(frozen=True)
class _StandaloneSanitizationScan:
    """Sanitized argv plus ignored wrapper spans that need safety validation."""

    filtered_argv: tuple[str, ...]
    ignored_options: tuple[_IgnoredOption, ...]


def _wrapper_option_tail(option_name: str) -> str:
    """Return the normalized wrapper/agent option tail without its prefix."""
    for prefix in _IGNORED_UNKNOWN_LONG_OPTION_PREFIXES:
        if option_name.startswith(prefix):
            return option_name.removeprefix(prefix)
    return option_name.removeprefix("--")


def _wrapper_option_expects_identifier(option_name: str) -> bool:
    """Return True when a wrapper option conventionally carries an opaque identifier."""
    option_tail = _wrapper_option_tail(option_name)
    return option_tail == "id" or option_tail.endswith(_IDENTIFIER_WRAPPER_OPTION_SUFFIX)


def _value_looks_like_dataview_identifier(value_token: str) -> bool:
    """Return True when *value_token* resembles a data-view identifier token."""
    normalized = value_token.strip().lower()
    return bool(re.fullmatch(r"dv(?:_|[0-9])[a-z0-9_-]*", normalized))


def _wrapper_value_is_machine_identifier(value_token: str) -> bool:
    """Return True for conservative machine-style IDs accepted after standalone commands."""
    normalized = value_token.strip()
    if not normalized or _value_looks_like_dataview_identifier(normalized):
        return False

    has_alpha = any(char.isalpha() for char in normalized)
    has_digit = any(char.isdigit() for char in normalized)
    if not (has_alpha and has_digit):
        return False

    return bool(re.fullmatch(r"[A-Za-z0-9_-]+", normalized))


def _wrapper_value_is_safe_post_request(value_token: str, *, option_name: str) -> bool:
    """Return True when a post-command wrapper value is clearly machine metadata."""
    normalized = value_token.strip()
    if not normalized:
        return False
    if _wrapper_value_is_boolean_literal(normalized):
        return True

    with contextlib.suppress(ValueError):
        float(normalized)
        return True

    if any(marker in normalized for marker in ":/.=@"):
        return True

    if _wrapper_option_expects_identifier(option_name):
        return _wrapper_value_is_machine_identifier(normalized)

    return bool(
        re.fullmatch(
            r"[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4,}-[0-9A-Fa-f-]{4,}",
            normalized,
        )
    )


def _ignored_option_consumed_width(
    argv: list[str],
    index: int,
    *,
    option_name: str,
    pending_option: str | None,
    has_equals: bool,
    scan_spec: Any,
    standalone_mode_options: frozenset[str],
    metadata_options: frozenset[str],
) -> int:
    """Return how many argv tokens an ignored wrapper/agent option should consume."""
    if has_equals:
        return 1

    next_index = index + 1
    if next_index >= len(argv):
        return 1

    next_arg = argv[next_index]
    if _token_starts_new_option(next_arg, scan_spec=scan_spec):
        return 1

    pending_category = _pending_option_category(
        pending_option,
        scan_spec=scan_spec,
        standalone_mode_options=standalone_mode_options,
        metadata_options=metadata_options,
    )
    if _wrapper_option_is_flaglike(option_name):
        if pending_category == "metadata":
            return 2
        return 2 if _wrapper_value_is_boolean_literal(next_arg) else 1
    return 2


def _build_ignored_option(
    argv: list[str],
    index: int,
    *,
    pending_option: str | None,
    standalone_request_complete: bool,
    scan_spec: Any,
    standalone_mode_options: frozenset[str],
    metadata_options: frozenset[str],
) -> tuple[_IgnoredOption, int] | None:
    """Return ignored wrapper metadata plus its consumed token width."""
    arg = argv[index]
    ignored_option_name = _ignored_unknown_option_name(arg, scan_spec=scan_spec)
    if ignored_option_name is None:
        return None

    option_name, has_equals, inline_value = arg.partition("=")
    consumed_width = _ignored_option_consumed_width(
        argv,
        index,
        option_name=option_name,
        pending_option=pending_option,
        has_equals=has_equals,
        scan_spec=scan_spec,
        standalone_mode_options=standalone_mode_options,
        metadata_options=metadata_options,
    )
    value_token: str | None = None
    if has_equals:
        value_token = inline_value
    elif consumed_width == 2:
        value_token = argv[index + 1]

    return (
        _IgnoredOption(
            option_name=option_name,
            value_token=value_token,
            value_attached=has_equals,
            pending_option=pending_option,
            standalone_request_complete=standalone_request_complete,
        ),
        consumed_width,
    )


def _ignored_option_replacement_tokens(ignored_option: _IgnoredOption) -> tuple[str, ...]:
    """Return tokens that remain visible after removing an ignored wrapper option.

    Flaglike wrappers only consume explicit boolean payloads. Attached
    non-boolean values therefore behave like the split form and stay visible as
    the next token in the sanitized argv only when a known option is already
    pending a value. They must not become fresh top-level tokens.
    """
    value_token = ignored_option.value_token
    if value_token is None or not ignored_option.value_attached:
        return ()
    if ignored_option.pending_option is None:
        return ()
    if not _wrapper_option_is_flaglike(ignored_option.option_name):
        return ()
    if _wrapper_value_is_boolean_literal(value_token):
        return ()
    return (value_token,)


def _pending_option_could_consume_value(
    value_token: str,
    *,
    pending_option: str | None,
    scan_spec: Any,
) -> bool:
    """Return True when *value_token* could satisfy the current pending known option."""
    if pending_option is None:
        return False

    option_spec = scan_spec.option_specs.get(pending_option)
    if option_spec is None:
        return False

    dest = option_spec.dest
    if dest == "completion":
        return value_token.strip().lower() in {"bash", "fish", "zsh"}
    if dest == "explain_exit_code":
        with contextlib.suppress(ValueError):
            int(value_token)
            return True
        return False

    return True


def _pending_option_category(
    pending_option: str | None,
    *,
    scan_spec: Any,
    standalone_mode_options: frozenset[str],
    metadata_options: frozenset[str],
) -> str | None:
    """Return the standalone-sanitization category for a pending known option."""
    if pending_option is None:
        return None

    option_spec = scan_spec.option_specs.get(pending_option)
    if option_spec is None:
        return None

    if pending_option in standalone_mode_options:
        return "standalone"
    if pending_option in metadata_options:
        return "metadata"
    return "other"


def _ignored_option_can_interrupt_pending_value(
    ignored_option: _IgnoredOption,
    *,
    scan_spec: Any,
    standalone_mode_options: frozenset[str],
    metadata_options: frozenset[str],
) -> bool:
    """Return True when ignoring a wrapper is still safe with a pending known option."""
    pending_option = ignored_option.pending_option
    pending_category = _pending_option_category(
        pending_option,
        scan_spec=scan_spec,
        standalone_mode_options=standalone_mode_options,
        metadata_options=metadata_options,
    )
    if pending_category is None:
        return True

    if pending_category == "metadata":
        return _ignored_option_is_safe_metadata_interruption(ignored_option)

    replacement_tokens = _ignored_option_replacement_tokens(ignored_option)
    if replacement_tokens:
        return pending_category == "standalone"

    if pending_category == "other":
        return False

    value_token = ignored_option.value_token
    if _wrapper_option_is_flaglike(ignored_option.option_name):
        if value_token is None:
            return True
        if not _wrapper_value_is_boolean_literal(value_token):
            return False
        return not _pending_option_could_consume_value(
            value_token,
            pending_option=pending_option,
            scan_spec=scan_spec,
        )

    if value_token is None:
        return False
    return not _pending_option_could_consume_value(
        value_token,
        pending_option=pending_option,
        scan_spec=scan_spec,
    )


def _ignored_option_has_valid_shape(ignored_option: _IgnoredOption) -> bool:
    """Return True when an ignored wrapper span is structurally valid metadata."""
    value_token = ignored_option.value_token
    if value_token is not None:
        return bool(value_token)
    return _wrapper_option_is_flaglike(ignored_option.option_name)


def _ignored_option_is_safe_metadata_interruption(ignored_option: _IgnoredOption) -> bool:
    """Return True when a wrapper safely interrupts a pending metadata option."""
    value_token = ignored_option.value_token
    if _wrapper_option_is_flaglike(ignored_option.option_name):
        if value_token is None:
            return True
        return _wrapper_value_is_boolean_literal(value_token)

    if value_token is None:
        return False
    return _wrapper_value_is_safe_post_request(
        value_token,
        option_name=ignored_option.option_name,
    )


def _advance_pending_value_state(
    *,
    consumed_values: int,
    pending_values: int,
    pending_option: str | None,
    pending_standalone_option: str | None,
    standalone_request_complete: bool,
) -> tuple[int, str | None, str | None, bool]:
    """Advance pending-option scan state after consuming real or synthetic values."""
    if consumed_values <= 0 or pending_values <= 0:
        return pending_values, pending_option, pending_standalone_option, standalone_request_complete

    pending_values = max(pending_values - consumed_values, 0)
    if pending_values == 0:
        if pending_standalone_option is not None:
            standalone_request_complete = True
            pending_standalone_option = None
        pending_option = None

    return pending_values, pending_option, pending_standalone_option, standalone_request_complete


def _ignored_option_is_safe_for_metadata_priming(
    ignored_option: _IgnoredOption,
    *,
    scan_spec: Any,
    metadata_options: frozenset[str],
) -> bool:
    """Return True when an ignored wrapper span cannot corrupt metadata recovery."""
    pending_option = ignored_option.pending_option
    if pending_option not in metadata_options:
        return True
    if not _ignored_option_has_valid_shape(ignored_option):
        return False
    return _ignored_option_can_interrupt_pending_value(
        ignored_option,
        scan_spec=scan_spec,
        standalone_mode_options=frozenset(),
        metadata_options=metadata_options,
    )


def _collect_metadata_occurrences(
    argv: list[str],
    *,
    scan_spec: Any,
    metadata_options: frozenset[str],
) -> tuple[OptionOccurrence, ...]:
    """Collect metadata occurrences while tolerating unrelated parse failures."""
    occurrences: list[OptionOccurrence] = []
    pending_values = 0
    pending_metadata_index: int | None = None

    index = 0
    while index < len(argv):
        arg = argv[index]

        if pending_values > 0:
            if _token_starts_new_option(arg, scan_spec=scan_spec):
                if pending_metadata_index is not None:
                    occurrences.pop()
                    pending_metadata_index = None
                pending_values = 0
                continue

            if pending_metadata_index is not None:
                last_occurrence = occurrences[pending_metadata_index]
                occurrences[pending_metadata_index] = OptionOccurrence(
                    canonical_option=last_occurrence.canonical_option,
                    argv_tokens=(*last_occurrence.argv_tokens, arg),
                )

            pending_values -= 1
            if pending_values == 0:
                pending_metadata_index = None
            index += 1
            continue

        if arg == "--":
            break

        resolution = _resolve_option_token(arg, scan_spec)
        if resolution.kind == "recognized":
            occurrences.extend(
                occurrence for occurrence in resolution.occurrences if occurrence.canonical_option in metadata_options
            )

            if resolution.pending_values > 0 and resolution.occurrences:
                pending_values = resolution.pending_values
                last_occurrence = resolution.occurrences[-1]
                if last_occurrence.canonical_option in metadata_options:
                    pending_metadata_index = len(occurrences) - 1
                else:
                    pending_metadata_index = None
            else:
                pending_values = 0
                pending_metadata_index = None

        index += 1

    if pending_values > 0 and pending_metadata_index is not None:
        occurrences.pop()

    return tuple(occurrences)


def _scan_standalone_sanitization(
    argv: list[str],
    *,
    scan_spec: Any,
    standalone_mode_options: frozenset[str],
    metadata_options: frozenset[str],
) -> _StandaloneSanitizationScan:
    """Return sanitized argv and ignored wrapper spans for fail-closed validation."""
    filtered_argv: list[str] = []
    ignored_options: list[_IgnoredOption] = []
    pending_option: str | None = None
    pending_standalone_option: str | None = None
    pending_values = 0
    standalone_request_complete = False

    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--":
            filtered_argv.extend(argv[index:])
            break

        ignored_resolution = _build_ignored_option(
            argv,
            index,
            pending_option=pending_option,
            standalone_request_complete=standalone_request_complete,
            scan_spec=scan_spec,
            standalone_mode_options=standalone_mode_options,
            metadata_options=metadata_options,
        )
        if ignored_resolution is not None:
            ignored_option, consumed_width = ignored_resolution
            ignored_options.append(ignored_option)
            replacement_tokens = _ignored_option_replacement_tokens(ignored_option)
            filtered_argv.extend(replacement_tokens)
            pending_values, pending_option, pending_standalone_option, standalone_request_complete = (
                _advance_pending_value_state(
                    consumed_values=len(replacement_tokens),
                    pending_values=pending_values,
                    pending_option=pending_option,
                    pending_standalone_option=pending_standalone_option,
                    standalone_request_complete=standalone_request_complete,
                )
            )
            index += consumed_width
            continue

        if pending_values > 0:
            filtered_argv.append(arg)
            pending_values, pending_option, pending_standalone_option, standalone_request_complete = (
                _advance_pending_value_state(
                    consumed_values=1,
                    pending_values=pending_values,
                    pending_option=pending_option,
                    pending_standalone_option=pending_standalone_option,
                    standalone_request_complete=standalone_request_complete,
                )
            )
            index += 1
            continue

        resolution = _resolve_option_token(arg, scan_spec)
        filtered_argv.append(arg)
        if resolution.kind == "recognized":
            pending_values = resolution.pending_values
            if pending_values > 0 and resolution.occurrences:
                pending_option = resolution.occurrences[-1].canonical_option
                pending_standalone_option = pending_option if pending_option in standalone_mode_options else None
            else:
                pending_option = None
                pending_standalone_option = None
                if any(occurrence.canonical_option in standalone_mode_options for occurrence in resolution.occurrences):
                    standalone_request_complete = True
        else:
            pending_option = None
            pending_standalone_option = None
        index += 1

    return _StandaloneSanitizationScan(
        filtered_argv=tuple(filtered_argv),
        ignored_options=tuple(ignored_options),
    )


def _ignored_option_is_safe(
    ignored_option: _IgnoredOption,
    *,
    scan_spec: Any,
    standalone_mode_options: frozenset[str],
    metadata_options: frozenset[str],
) -> bool:
    """Return True when ignoring a wrapper span preserves fail-closed semantics."""
    if not _ignored_option_has_valid_shape(ignored_option):
        return False

    if not _ignored_option_can_interrupt_pending_value(
        ignored_option,
        scan_spec=scan_spec,
        standalone_mode_options=standalone_mode_options,
        metadata_options=metadata_options,
    ):
        return False

    if ignored_option.standalone_request_complete:
        if _ignored_option_replacement_tokens(ignored_option):
            return True
        value_token = ignored_option.value_token
        if value_token is None:
            return True
        return _wrapper_value_is_safe_post_request(
            value_token,
            option_name=ignored_option.option_name,
        )

    return True
