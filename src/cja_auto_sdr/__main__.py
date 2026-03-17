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
from typing import NamedTuple

from cja_auto_sdr.cli.option_resolution import resolve_long_option_token as _resolve_long_option_token
from cja_auto_sdr.cli.token_scan import (
    _accepts_inline_option_value,  # noqa: F401
    _minimum_option_arity,  # noqa: F401
)
from cja_auto_sdr.cli.token_scan import option_scan_spec as _fast_path_option_spec
from cja_auto_sdr.cli.token_scan import scan_option_tokens as _shared_scan_option_tokens

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


def _is_argcomplete_completion_active(environ: Mapping[str, str] | None = None) -> bool:
    """Return True when argcomplete shell-completion invocation is active."""
    env = os.environ if environ is None else environ
    raw_value = env.get(_ARGCOMPLETE_ENV_VAR)
    if raw_value is None:
        return False
    return raw_value.strip().lower() not in _FALSEY_ENV_VALUES


def _scan_option_tokens(args: list[str]) -> _OptionScanResult:
    """Scan CLI tokens argparse-style for fast-path decisions.

    Unknown options are tolerated (argparse's version action can still exit
    before unknown-argument failures), but ambiguous long-option prefixes and
    explicit values for zero-arity options are treated as parse errors.
    """
    scan = _shared_scan_option_tokens(args, reject_unknown_options=False)
    return _OptionScanResult(options=scan.options, has_parse_error=scan.has_parse_error)


def _has_run_summary_contract_flag(args: list[str]) -> bool:
    """Return True when argv explicitly requests run-summary output.

    This token-level detector intentionally ignores option-value consumption so
    run-summary handling remains order-independent (e.g., `--version` followed
    by flags that would otherwise consume later tokens).
    """
    scan_spec = _fast_path_option_spec()

    for arg in args:
        if arg == "--":
            break
        if not arg.startswith("--"):
            continue

        option_name, _, _inline_value = arg.partition("=")
        long_resolution = _resolve_long_option_token(option_name, scan_spec.known_long_options)
        if long_resolution.canonical_option == _RUN_SUMMARY_OPTION:
            return True

    return False


def _has_run_summary_flag(args: list[str]) -> bool:
    """Return True when argparse-style scan resolves --run-summary-json."""
    scan = _scan_option_tokens(args)
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


def _is_fast_path_flag(argv: list[str]) -> str | None:
    """Return the fast-path flag present in *argv*, or ``None``."""
    # Only consider real arguments (ignore argv[0] script/module path).
    args = argv[1:]
    if not args:
        return None

    # Preserve run-summary contract: when requested, always route through
    # generator.main() so summary emission is consistent and order-independent.
    if _has_run_summary_contract_flag(args):
        return None

    scan = _scan_option_tokens(args)

    has_version_candidate = any(option in (_VERSION_OPTION, _VERSION_SHORT_OPTION) for option in scan.options)
    if has_version_candidate:
        probe = _probe_argparse_termination(args, argv[0] if argv else None)
        if probe is not None:
            # argparse exits with status 0 for both help and version actions.
            # Treat non-help output as version-action termination.
            probe_text = (probe.output or "").lower()
            if probe.status == 0 and probe_text and "usage:" not in probe_text:
                return _VERSION_OPTION
        return None

    # For non-version requests, parse errors still disable fast-path.
    if scan.has_parse_error:
        return None

    # --help / -h — still needs the full parser for complete output,
    # so we don't intercept it here.

    # --exit-codes (standalone flag, no other args needed)
    if args == ["--exit-codes"]:
        return "--exit-codes"

    # --explain-exit-code CODE (standalone: flag + its consumed value only)
    if len(scan.options) == 1 and scan.options[0] == "--explain-exit-code":
        # --explain-exit-code=2  -> 1 token
        # --explain-exit-code 2  -> 2 tokens
        # Any extra tokens mean it's not standalone.
        has_inline_value = any("=" in a for a in args if a.startswith("--explain"))
        expected_token_count = 1 if has_inline_value else 2
        if len(args) == expected_token_count:
            return "--explain-exit-code"

    return None


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
    args = argv[1:] if len(argv) > 1 else []
    if not args:
        return None

    # Preserve run-summary contract: summary emission must route through
    # generator.main() regardless of option ordering.
    if _has_run_summary_contract_flag(args):
        return None

    scan = _scan_option_tokens(args)
    if scan.has_parse_error:
        return None

    if _COMPLETION_OPTION not in scan.options:
        return None

    # Completion fast-path is intentionally strict: only standalone completion
    # requests are intercepted; mixed option combinations defer to argparse.
    if any(option != _COMPLETION_OPTION for option in scan.options):
        return None

    probe = _probe_argparse_parse(args, argv[0] if argv else None)
    if probe.termination is not None or probe.namespace is None:
        return None

    completion_shell = getattr(probe.namespace, "completion", None)
    if completion_shell is None:
        return None

    if getattr(probe.namespace, "data_views", []):
        return None

    return str(completion_shell).lower()


def main() -> None:
    """Entry point with fast-path for lightweight flags."""
    # Argcomplete shell completion relies on parser-side hooks in
    # parse_arguments(); do not short-circuit fast-path in that mode.
    if _is_argcomplete_completion_active():
        from cja_auto_sdr.generator import main as _generator_main

        _generator_main()
        return

    # --completion fast-path: only standalone, parser-valid completion requests
    # are handled here. Mixed/invalid argv must defer to full argparse flow.
    completion_shell = _completion_fast_path_shell(sys.argv)
    if completion_shell is not None:
        _handle_completion(completion_shell, sys.argv[0] if sys.argv else None)
        # _handle_completion always raises SystemExit; this is a safety net.
        return  # pragma: no cover

    flag = _is_fast_path_flag(sys.argv)

    if flag == "--version":
        _print_version(_resolve_program_name(sys.argv[0] if sys.argv else None))
        raise SystemExit(0)

    if flag == "--exit-codes":
        _print_exit_codes()
        raise SystemExit(0)

    if flag == "--explain-exit-code":
        # Extract the integer code from argv. The probe parse gives us
        # the canonical value without re-implementing argparse int coercion.
        probe = _probe_argparse_parse(sys.argv[1:], sys.argv[0] if sys.argv else None)
        if probe.namespace is not None:
            code_value = getattr(probe.namespace, "explain_exit_code", None)
            if code_value is not None:
                _explain_exit_code(int(code_value))
                raise SystemExit(0)
        # If probe failed (shouldn't happen for a valid fast-path), fall through.

    # All other invocations need the full generator
    from cja_auto_sdr.generator import main as _generator_main

    _generator_main()


if __name__ == "__main__":
    main()
