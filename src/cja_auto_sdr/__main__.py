"""Fast-path entry point for CJA Auto SDR.

Lightweight flags (``--version``, ``--help``, ``--exit-codes``,
``--completion``) are handled here *before* any heavyweight imports
(pandas, cjapy, tqdm) so that simple informational queries return in
under 100 ms.

All other invocations fall through to the full ``generator.main()`` path.

Used by both ``python -m cja_auto_sdr`` and the console-script entry points.
"""

from __future__ import annotations

import os
import shlex
import sys
import types
from collections.abc import Mapping
from functools import lru_cache
from typing import NamedTuple

from cja_auto_sdr.cli.option_resolution import resolve_long_option_token as _resolve_long_option_token
from cja_auto_sdr.cli.standalone_policy import standalone_prevalidation_policy

_VERSION_OPTION = "--version"
_VERSION_SHORT_OPTION = "-V"

_COMPLETION_OPTION = "--completion"
_RUN_SUMMARY_OPTION = "--run-summary-json"
_ARGCOMPLETE_ENV_VAR = "_ARGCOMPLETE"
_FALSEY_ENV_VALUES = frozenset({"", "0", "false", "no", "off"})
_DEFAULT_COMPLETION_COMMAND = "cja_auto_sdr"

_SUPPORTED_SHELLS = frozenset({"bash", "zsh", "fish"})

_COMPLETION_SCRIPT_TEMPLATES: dict[str, str] = {
    "bash": 'eval "$(register-python-argcomplete {command})"',
    "zsh": ('autoload -U bashcompinit && bashcompinit\neval "$(register-python-argcomplete {command})"'),
    "fish": "register-python-argcomplete --shell fish {command} | source",
}


class _OptionSpec(NamedTuple):
    """Minimal option metadata needed for fast-path token scanning."""

    dest: str
    min_arity: int
    accepts_inline_value: bool


class _OptionScanResult(NamedTuple):
    """Fast-path parse outcome: recognized options plus parse validity."""

    options: tuple[str, ...]
    has_parse_error: bool


class _ArgparseProbeExit(Exception):
    """Internal sentinel used to capture argparse exits without emitting output."""

    def __init__(self, status: int = 0, message: str | None = None) -> None:
        super().__init__(status, message)
        self.status = status
        self.message = message


class _ArgparseProbeResult(NamedTuple):
    """Result of a lightweight argparse probe parse."""

    status: int
    output: str | None


class _ArgparseProbeParseResult(NamedTuple):
    """Result of probing argparse parse success/termination."""

    namespace: object | None
    termination: _ArgparseProbeResult | None


class _FastPathRequest(NamedTuple):
    """Resolved fast-path request payload."""

    flag: str
    completion_shell: str | None = None
    explain_exit_code: int | None = None


_STANDALONE_FAST_PATH_MODE_NAMES: Mapping[str, str] = {
    _COMPLETION_OPTION: "completion",
    "--exit-codes": "exit_codes",
    "--explain-exit-code": "explain_exit_code",
}


def _is_argcomplete_completion_active(environ: Mapping[str, str] | None = None) -> bool:
    """Return True when argcomplete shell-completion invocation is active."""
    env = os.environ if environ is None else environ
    raw_value = env.get(_ARGCOMPLETE_ENV_VAR)
    if raw_value is None:
        return False
    return raw_value.strip().lower() not in _FALSEY_ENV_VALUES


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
def _fast_path_option_spec() -> tuple[frozenset[str], dict[str, _OptionSpec]]:
    """Return (known_long_options, option_specs) from the configured CLI parser."""
    from cja_auto_sdr.cli.parser import parse_arguments

    parser = parse_arguments(return_parser=True, enable_autocomplete=False)
    option_specs: dict[str, _OptionSpec] = {}
    known_long_options: set[str] = set()

    # CPython argparse internals: `_actions` is intentionally used as the
    # canonical source of configured option metadata for fast-path scanning.
    for action in parser._actions:
        if not action.option_strings:
            continue
        action_nargs = getattr(action, "nargs", None)
        option_spec = _OptionSpec(
            dest=getattr(action, "dest", ""),
            min_arity=_minimum_option_arity(action_nargs),
            accepts_inline_value=_accepts_inline_option_value(action_nargs),
        )
        for option in action.option_strings:
            option_specs[option] = option_spec
            if option.startswith("--"):
                known_long_options.add(option)

    return frozenset(known_long_options), option_specs


def _scan_option_tokens(args: list[str]) -> _OptionScanResult:
    """Scan CLI tokens argparse-style for fast-path decisions.

    Unknown options are tolerated (argparse's version action can still exit
    before unknown-argument failures), but ambiguous long-option prefixes and
    explicit values for zero-arity options are treated as parse errors.
    """
    known_long_options, option_specs = _fast_path_option_spec()
    pending_option_values = 0
    resolved_options: list[str] = []

    for arg in args:
        if arg == "--":
            break

        if pending_option_values > 0:
            pending_option_values -= 1
            continue

        if arg.startswith("--"):
            option_name, has_equals, _inline_value = arg.partition("=")
            long_resolution = _resolve_long_option_token(option_name, known_long_options)
            if long_resolution.is_ambiguous:
                return _OptionScanResult(options=tuple(resolved_options), has_parse_error=True)
            canonical_option = long_resolution.canonical_option
            if canonical_option is None:
                continue

            option_spec = option_specs.get(canonical_option)
            if option_spec is None:
                continue
            if has_equals and not option_spec.accepts_inline_value:
                return _OptionScanResult(options=tuple(resolved_options), has_parse_error=True)

            resolved_options.append(canonical_option)

            inline_values = 1 if has_equals and option_spec.accepts_inline_value else 0
            if option_spec.min_arity > inline_values:
                pending_option_values = option_spec.min_arity - inline_values
            continue

        if arg.startswith("-") and arg != "-":
            option_spec = option_specs.get(arg)
            if option_spec is not None:
                resolved_options.append(arg)
                if option_spec.min_arity > 0:
                    pending_option_values = option_spec.min_arity
                continue

            # Support short-option clusters like -qV and attached values like -pVALUE.
            if len(arg) > 2:
                cluster = arg[1:]
                for index, short_name in enumerate(cluster):
                    short_option = f"-{short_name}"
                    option_spec = option_specs.get(short_option)
                    if option_spec is None:
                        break
                    resolved_options.append(short_option)
                    attached_value = cluster[index + 1 :]
                    if option_spec.min_arity > 0:
                        pending_option_values = (
                            max(option_spec.min_arity - 1, 0) if attached_value else option_spec.min_arity
                        )
                        break
                    if attached_value.startswith(("=", "-")):
                        return _OptionScanResult(options=tuple(resolved_options), has_parse_error=True)
            continue

    return _OptionScanResult(options=tuple(resolved_options), has_parse_error=False)


def _has_run_summary_contract_flag(args: list[str]) -> bool:
    """Return True when argv explicitly requests run-summary output.

    This token-level detector intentionally ignores option-value consumption so
    run-summary handling remains order-independent (e.g., `--version` followed
    by flags that would otherwise consume later tokens).
    """
    known_long_options, _ = _fast_path_option_spec()

    for arg in args:
        if arg == "--":
            break
        if not arg.startswith("--"):
            continue

        option_name, _, _inline_value = arg.partition("=")
        long_resolution = _resolve_long_option_token(option_name, known_long_options)
        if long_resolution.canonical_option == _RUN_SUMMARY_OPTION:
            return True

    return False


def _has_run_summary_flag(args: list[str]) -> bool:
    """Return True when argparse-style scan resolves --run-summary-json."""
    scan = _scan_option_tokens(args)
    if scan.has_parse_error:
        return False
    return any(option == _RUN_SUMMARY_OPTION for option in scan.options)


def _probe_argparse_termination(args: list[str], argv0: str | None = None) -> _ArgparseProbeResult | None:
    """Return argparse termination info for *args* without printing output.

    This uses the real parser as the source of truth for precedence and
    validation (help/version actions, missing values, and mutex conflicts).
    """
    return _probe_argparse_parse(args, argv0).termination


def _probe_argparse_parse(args: list[str], argv0: str | None = None) -> _ArgparseProbeParseResult:
    """Probe argparse parse result for *args* without emitting output."""
    from cja_auto_sdr.cli.parser import parse_arguments

    parser = parse_arguments(return_parser=True, enable_autocomplete=False)
    parser.prog = _resolve_program_name(argv0)
    captured_output: list[str] = []

    def _probe_exit(_self, status: int = 0, message: str | None = None) -> None:
        raise _ArgparseProbeExit(status, message)

    def _capture_output(_self, message: str | None, _file=None) -> None:
        if message:
            captured_output.append(message)

    parser.exit = types.MethodType(_probe_exit, parser)
    # CPython argparse internals: `_print_message` is overridden so probe parses
    # can capture output without emitting to real stdio.
    parser._print_message = types.MethodType(_capture_output, parser)

    try:
        namespace = parser.parse_args(args)
    except _ArgparseProbeExit as probe_exit:
        rendered_output = probe_exit.message or "".join(captured_output) or None
        return _ArgparseProbeParseResult(
            namespace=None,
            termination=_ArgparseProbeResult(status=probe_exit.status, output=rendered_output),
        )
    return _ArgparseProbeParseResult(namespace=namespace, termination=None)


def _primary_fast_path_option_dest(primary_option: str) -> str | None:
    """Return the argparse dest for the primary fast-path option."""
    _, option_specs = _fast_path_option_spec()
    option_spec = option_specs.get(primary_option)
    if option_spec is None:
        return None
    return option_spec.dest


def _fast_path_allowed_option_dests(primary_option: str) -> frozenset[str]:
    """Return option dests that may accompany *primary_option* on the fast path."""
    allowed_dests: set[str] = set()
    primary_dest = _primary_fast_path_option_dest(primary_option)
    if primary_dest:
        allowed_dests.add(primary_dest)

    mode_name = _STANDALONE_FAST_PATH_MODE_NAMES.get(primary_option)
    if mode_name is None:
        return frozenset(allowed_dests)

    policy = standalone_prevalidation_policy(mode_name)
    if policy is not None:
        allowed_dests.update(policy.tolerated_fast_path_dests())

    return frozenset(allowed_dests)


def _fast_path_options_fit_policy(options: tuple[str, ...], primary_option: str) -> bool:
    """Return True when all resolved options are tolerated by the standalone policy."""
    allowed_dests = _fast_path_allowed_option_dests(primary_option)
    if not allowed_dests:
        return False

    _, option_specs = _fast_path_option_spec()
    for option in options:
        option_spec = option_specs.get(option)
        if option_spec is None or option_spec.dest not in allowed_dests:
            return False
    return True


def _resolve_non_version_fast_path_request(
    scan: _OptionScanResult,
    namespace: object | None,
) -> _FastPathRequest | None:
    """Resolve non-version standalone fast-path requests from a probe parse."""
    if namespace is None:
        return None

    if getattr(namespace, "explain_exit_code", None) is not None:
        if getattr(namespace, "data_views", []):
            return None
        if not _fast_path_options_fit_policy(scan.options, "--explain-exit-code"):
            return None
        return _FastPathRequest(flag="--explain-exit-code", explain_exit_code=int(namespace.explain_exit_code))

    if getattr(namespace, "exit_codes", False):
        if getattr(namespace, "data_views", []):
            return None
        if not _fast_path_options_fit_policy(scan.options, "--exit-codes"):
            return None
        return _FastPathRequest(flag="--exit-codes")

    completion_shell = getattr(namespace, "completion", None)
    if completion_shell is not None:
        if getattr(namespace, "data_views", []):
            return None
        if not _fast_path_options_fit_policy(scan.options, _COMPLETION_OPTION):
            return None
        return _FastPathRequest(flag=_COMPLETION_OPTION, completion_shell=str(completion_shell).lower())

    return None


def _resolve_fast_path_request(argv: list[str]) -> _FastPathRequest | None:
    """Return the resolved fast-path request for *argv*, or ``None``."""
    args = argv[1:]
    if not args:
        return None

    if _has_run_summary_contract_flag(args):
        return None

    scan = _scan_option_tokens(args)

    has_version_candidate = any(option in (_VERSION_OPTION, _VERSION_SHORT_OPTION) for option in scan.options)
    if has_version_candidate:
        probe = _probe_argparse_termination(args, argv[0] if argv else None)
        if probe is not None:
            probe_text = (probe.output or "").lower()
            if probe.status == 0 and probe_text and "usage:" not in probe_text:
                return _FastPathRequest(flag=_VERSION_OPTION)
        return None

    if scan.has_parse_error:
        return None

    probe = _probe_argparse_parse(args, argv[0] if argv else None)
    if probe.termination is not None:
        return None

    return _resolve_non_version_fast_path_request(scan, probe.namespace)


def _is_fast_path_flag(argv: list[str]) -> str | None:
    """Return the fast-path flag present in *argv*, or ``None``."""
    request = _resolve_fast_path_request(argv)
    if request is None:
        return None
    return request.flag


def _resolve_program_name(
    argv0: str | None,
    module_name: str | None = None,
    interpreter_name: str | None = None,
) -> str:
    """Return the display program name argparse would use for version output.

    For ``python -m cja_auto_sdr`` invocation, argparse reports
    ``python -m cja_auto_sdr`` rather than ``__main__.py``. Mirror that to keep
    fast-path and full-parser behavior consistent.
    """
    if not argv0:
        return "cja_auto_sdr"
    program_name = os.path.basename(argv0)
    if program_name == "__main__.py":
        resolved_module = module_name
        if resolved_module is None:
            spec = globals().get("__spec__")
            resolved_module = getattr(spec, "name", None) if spec else None
        if resolved_module:
            module_target = resolved_module.removesuffix(".__main__")
            resolved_interpreter = interpreter_name
            if resolved_interpreter is None:
                resolved_interpreter = os.path.basename(sys.executable)
            return f"{resolved_interpreter or 'python'} -m {module_target}"
    return program_name or "cja_auto_sdr"


def _resolve_completion_command_name(argv0: str | None) -> str:
    """Return the command name used in shell completion registration."""
    if not argv0:
        return _DEFAULT_COMPLETION_COMMAND

    command_name = os.path.basename(argv0).strip()
    if not command_name or command_name == "__main__.py":
        return _DEFAULT_COMPLETION_COMMAND

    return command_name


def _render_completion_script(shell: str, command_name: str) -> str:
    """Render shell completion script for *shell* and resolved *command_name*."""
    template = _COMPLETION_SCRIPT_TEMPLATES.get(shell)
    if template is None:
        raise ValueError(f"Unsupported shell: {shell}")

    quoted_command = shlex.quote(command_name)
    return template.format(command=quoted_command)


# Backward-compatible default snippets for tests and static validation.
_COMPLETION_SCRIPTS: dict[str, str] = {
    shell: _render_completion_script(shell, _DEFAULT_COMPLETION_COMMAND) for shell in _SUPPORTED_SHELLS
}


def _print_version(program_name: str = "cja_auto_sdr") -> None:
    from cja_auto_sdr.core.version import __version__

    print(f"{program_name} {__version__}")


def _print_exit_codes() -> None:
    from cja_auto_sdr.core.constants import BANNER_WIDTH
    from cja_auto_sdr.core.exit_codes import print_exit_codes

    print_exit_codes(banner_width=BANNER_WIDTH)


def _explain_exit_code(code: int) -> None:
    from cja_auto_sdr.core.exit_codes import explain_exit_code

    explain_exit_code(code)


def _handle_completion(shell: str, argv0: str | None = None) -> None:
    """Print the shell completion activation script and exit.

    Exits 0 on success, 1 if argcomplete is not installed.
    """
    if shell not in _SUPPORTED_SHELLS:
        print(
            f"error: unsupported shell '{shell}'. Supported shells: {', '.join(sorted(_SUPPORTED_SHELLS))}",
            file=sys.stderr,
        )
        raise SystemExit(1)

    try:
        import argcomplete as _argcomplete  # noqa: F401
    except ImportError:
        print(
            "error: argcomplete is not installed. Install it with:\n  pip install argcomplete",
            file=sys.stderr,
        )
        raise SystemExit(1) from None

    command_name = _resolve_completion_command_name(argv0)
    print(_render_completion_script(shell, command_name))
    raise SystemExit(0)


def _completion_fast_path_shell(argv: list[str]) -> str | None:
    """Return completion shell for standalone, parse-valid fast-path requests.

    Any mixed flags, parse errors, or argparse action precedence cases fall
    through to ``generator.main()`` to preserve parser behavior.
    """
    request = _resolve_fast_path_request(argv)
    if request is None or request.flag != _COMPLETION_OPTION:
        return None
    return request.completion_shell


def main() -> None:
    """Entry point with fast-path for lightweight flags."""
    # Argcomplete shell completion relies on parser-side hooks in
    # parse_arguments(); do not short-circuit fast-path in that mode.
    if _is_argcomplete_completion_active():
        from cja_auto_sdr.generator import main as _generator_main

        _generator_main()
        return

    request = _resolve_fast_path_request(sys.argv)

    if request is not None and request.flag == "--version":
        _print_version(_resolve_program_name(sys.argv[0] if sys.argv else None))
        raise SystemExit(0)

    if request is not None and request.flag == _COMPLETION_OPTION:
        _handle_completion(request.completion_shell or "", sys.argv[0] if sys.argv else None)
        return  # pragma: no cover

    if request is not None and request.flag == "--exit-codes":
        _print_exit_codes()
        raise SystemExit(0)

    if request is not None and request.flag == "--explain-exit-code" and request.explain_exit_code is not None:
        _explain_exit_code(request.explain_exit_code)
        raise SystemExit(0)

    # All other invocations need the full generator
    from cja_auto_sdr.generator import main as _generator_main

    _generator_main()


if __name__ == "__main__":
    main()
