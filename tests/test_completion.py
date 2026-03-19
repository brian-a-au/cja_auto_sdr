"""Tests for --completion bash/zsh/fish flag.

Covers:
- Fast-path detection in __main__.py for each supported shell
- Correct activation script output on stdout for bash, zsh, fish
- Missing argcomplete triggers stderr message and exit 1
- Fast-path defers malformed or mixed completion argv to generator/argparse flow
- Safety-net dispatch from generator._main_impl()
"""

from __future__ import annotations

import json
import sys
from unittest.mock import patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_entrypoint_main(argv: list[str]):
    """Call __main__.main() with the given argv and capture SystemExit."""
    from cja_auto_sdr import __main__ as entrypoint

    with patch.object(sys, "argv", argv):
        with pytest.raises(SystemExit) as exc_info:
            entrypoint.main()
    return exc_info


# ---------------------------------------------------------------------------
# _handle_completion unit tests
# ---------------------------------------------------------------------------


class TestHandleCompletion:
    """Unit tests for _handle_completion()."""

    @pytest.mark.parametrize(
        ("shell", "argv0", "expected_command", "expected_fragment"),
        [
            ("bash", "cja_auto_sdr", "cja_auto_sdr", 'eval "$(register-python-argcomplete cja_auto_sdr)"'),
            ("bash", "cja-auto-sdr", "cja-auto-sdr", "register-python-argcomplete cja-auto-sdr"),
            ("zsh", "/usr/local/bin/cja-auto-sdr", "cja-auto-sdr", "autoload -U bashcompinit && bashcompinit"),
            ("fish", "__main__.py", "cja_auto_sdr", "register-python-argcomplete --shell fish cja_auto_sdr | source"),
        ],
    )
    def test_prints_activation_script_to_stdout(self, shell, argv0, expected_command, expected_fragment, capsys):
        """Each shell produces the correct activation snippet on stdout."""
        from cja_auto_sdr.__main__ import _handle_completion

        with patch.dict("sys.modules", {"argcomplete": type(sys)("argcomplete")}):
            with pytest.raises(SystemExit) as exc_info:
                _handle_completion(shell, argv0=argv0)

        assert int(exc_info.value.code) == 0
        stdout = capsys.readouterr().out
        assert expected_fragment in stdout
        assert expected_command in stdout

    def test_missing_argcomplete_prints_install_instructions(self, capsys):
        """When argcomplete is missing, print install instructions to stderr and exit 1."""
        from cja_auto_sdr.__main__ import _handle_completion

        with patch.dict("sys.modules", {"argcomplete": None}):
            with pytest.raises(SystemExit) as exc_info:
                _handle_completion("bash")

        assert int(exc_info.value.code) == 1
        captured = capsys.readouterr()
        assert captured.out == ""  # nothing on stdout
        assert "argcomplete is not installed" in captured.err
        assert "pip install argcomplete" in captured.err

    def test_invalid_shell_prints_error_and_exits_1(self, capsys):
        from cja_auto_sdr.__main__ import _handle_completion

        with pytest.raises(SystemExit) as exc_info:
            _handle_completion("powershell", argv0="cja_auto_sdr")

        assert int(exc_info.value.code) == 1
        captured = capsys.readouterr()
        assert captured.out == ""
        assert "unsupported shell 'powershell'" in captured.err

    def test_stdout_contains_no_stderr_content(self, capsys):
        """Verify script goes to stdout and nothing leaks to stderr on success."""
        from cja_auto_sdr.__main__ import _handle_completion

        with patch.dict("sys.modules", {"argcomplete": type(sys)("argcomplete")}):
            with pytest.raises(SystemExit):
                _handle_completion("bash", argv0="cja-auto-sdr")

        captured = capsys.readouterr()
        assert captured.err == ""
        assert "register-python-argcomplete cja-auto-sdr" in captured.out


# ---------------------------------------------------------------------------
# Fast-path integration tests (via __main__.main)
# ---------------------------------------------------------------------------


class TestCompletionFastPath:
    """Integration tests verifying --completion is handled in the fast path."""

    @pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
    def test_fast_path_does_not_import_generator(self, shell, capsys):
        """--completion should not fall through to generator.main()."""
        from cja_auto_sdr import __main__ as entrypoint

        with (
            patch.object(sys, "argv", ["cja_auto_sdr", "--completion", shell]),
            patch.dict("sys.modules", {"argcomplete": type(sys)("argcomplete")}),
            patch("cja_auto_sdr.generator.main") as mock_generator_main,
        ):
            with pytest.raises(SystemExit) as exc_info:
                entrypoint.main()

        assert int(exc_info.value.code) == 0
        mock_generator_main.assert_not_called()

    @pytest.mark.parametrize(
        ("argv0", "expected_command"),
        [
            ("cja_auto_sdr", "cja_auto_sdr"),
            ("cja-auto-sdr", "cja-auto-sdr"),
            ("/usr/local/bin/cja-auto-sdr", "cja-auto-sdr"),
            ("__main__.py", "cja_auto_sdr"),
            ("", "cja_auto_sdr"),
        ],
    )
    def test_fast_path_bash_output_uses_invoked_command(self, argv0, expected_command, capsys):
        """Completion script should target the invoked command entrypoint."""
        from cja_auto_sdr.__main__ import _render_completion_script

        with (
            patch.object(sys, "argv", [argv0, "--completion", "bash"]),
            patch.dict("sys.modules", {"argcomplete": type(sys)("argcomplete")}),
        ):
            with pytest.raises(SystemExit) as exc_info:
                from cja_auto_sdr import __main__ as entrypoint

                entrypoint.main()

        assert int(exc_info.value.code) == 0
        stdout = capsys.readouterr().out.strip()
        assert stdout == _render_completion_script("bash", expected_command)

    def test_fast_path_zsh_output(self, capsys):
        """--completion zsh prints the zsh activation script."""
        from cja_auto_sdr.__main__ import _COMPLETION_SCRIPTS

        with (
            patch.object(sys, "argv", ["cja_auto_sdr", "--completion", "zsh"]),
            patch.dict("sys.modules", {"argcomplete": type(sys)("argcomplete")}),
        ):
            with pytest.raises(SystemExit) as exc_info:
                from cja_auto_sdr import __main__ as entrypoint

                entrypoint.main()

        assert int(exc_info.value.code) == 0
        stdout = capsys.readouterr().out.strip()
        assert stdout == _COMPLETION_SCRIPTS["zsh"]

    def test_fast_path_fish_output(self, capsys):
        """--completion fish prints the fish activation script."""
        from cja_auto_sdr.__main__ import _COMPLETION_SCRIPTS

        with (
            patch.object(sys, "argv", ["cja_auto_sdr", "--completion", "fish"]),
            patch.dict("sys.modules", {"argcomplete": type(sys)("argcomplete")}),
        ):
            with pytest.raises(SystemExit) as exc_info:
                from cja_auto_sdr import __main__ as entrypoint

                entrypoint.main()

        assert int(exc_info.value.code) == 0
        stdout = capsys.readouterr().out.strip()
        assert stdout == _COMPLETION_SCRIPTS["fish"]

    def test_fast_path_missing_shell_falls_through_to_generator(self):
        """Invalid standalone completion requests must defer to argparse path."""
        from cja_auto_sdr import __main__ as entrypoint

        with (
            patch.object(sys, "argv", ["cja_auto_sdr", "--completion"]),
            patch("cja_auto_sdr.generator.main") as mock_generator_main,
        ):
            entrypoint.main()

        mock_generator_main.assert_called_once()

    def test_fast_path_invalid_shell_falls_through_to_generator(self):
        """Unsupported completion shells must defer to argparse path."""
        from cja_auto_sdr import __main__ as entrypoint

        with (
            patch.object(sys, "argv", ["cja_auto_sdr", "--completion", "ksh"]),
            patch("cja_auto_sdr.generator.main") as mock_generator_main,
        ):
            entrypoint.main()

        mock_generator_main.assert_called_once()

    def test_fast_path_mixed_completion_with_missing_option_value_falls_through_to_generator(self):
        """Mixed malformed argv must not bypass argparse validation."""
        from cja_auto_sdr import __main__ as entrypoint

        with (
            patch.object(sys, "argv", ["cja_auto_sdr", "--profile", "--completion", "bash"]),
            patch("cja_auto_sdr.generator.main") as mock_generator_main,
        ):
            entrypoint.main()

        mock_generator_main.assert_called_once()

    def test_fast_path_version_precedence_over_invalid_completion_shell(self, capsys):
        """Version action precedence must win over malformed completion tokens."""
        from cja_auto_sdr import __main__ as entrypoint
        from cja_auto_sdr.core.version import __version__

        with (
            patch.object(sys, "argv", ["cja_auto_sdr", "--version", "--completion", "ksh"]),
            patch("cja_auto_sdr.generator.main") as mock_generator_main,
        ):
            with pytest.raises(SystemExit) as exc_info:
                entrypoint.main()

        assert int(exc_info.value.code) == 0
        mock_generator_main.assert_not_called()
        captured = capsys.readouterr()
        assert captured.out.strip() == f"cja_auto_sdr {__version__}"
        assert "unsupported shell" not in captured.err

    @pytest.mark.parametrize(
        "argv_tail",
        [
            ["--completion", "bash", "--run-summary-json", "stdout"],
            ["--run-summary-json", "stdout", "--completion", "bash"],
        ],
    )
    def test_completion_with_run_summary_routes_through_generator_contract(self, argv_tail, capsys):
        """Run-summary contract must bypass completion fast-path and emit JSON summary."""
        from cja_auto_sdr import __main__ as entrypoint

        argv = ["cja_auto_sdr", *argv_tail]
        fake_argcomplete = type(sys)("argcomplete")
        fake_argcomplete.autocomplete = lambda *_args, **_kwargs: None
        with (
            patch.object(sys, "argv", argv),
            patch.dict("sys.modules", {"argcomplete": fake_argcomplete}),
        ):
            with pytest.raises(SystemExit) as exc_info:
                entrypoint.main()

        assert int(exc_info.value.code) == 0
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["summary_version"] == "1.1"
        assert payload["exit_code"] == 0
        assert payload["command"]["argv"] == argv
        assert "register-python-argcomplete" in captured.err
        assert "register-python-argcomplete" not in captured.out

    def test_completion_with_run_summary_ignores_unrelated_workers_validation(self, capsys):
        """Completion should still succeed when mixed with invalid non-completion options."""
        from cja_auto_sdr import __main__ as entrypoint

        argv = ["cja_auto_sdr", "--completion", "bash", "--workers", "0", "--run-summary-json", "stdout"]
        fake_argcomplete = type(sys)("argcomplete")
        fake_argcomplete.autocomplete = lambda *_args, **_kwargs: None
        with (
            patch.object(sys, "argv", argv),
            patch.dict("sys.modules", {"argcomplete": fake_argcomplete}),
        ):
            with pytest.raises(SystemExit) as exc_info:
                entrypoint.main()

        assert int(exc_info.value.code) == 0
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["mode"] == "completion"
        assert payload["exit_code"] == 0
        assert "--workers must be at least 1" not in captured.err
        assert "register-python-argcomplete" in captured.err


# ---------------------------------------------------------------------------
# Argparse integration (parser recognizes --completion)
# ---------------------------------------------------------------------------


class TestCompletionArgparse:
    """Tests that the argparse parser recognizes --completion."""

    def test_parser_accepts_completion_bash(self):
        from cja_auto_sdr.cli.parser import parse_arguments

        args = parse_arguments(["--completion", "bash", "dv_test"])
        assert args.completion == "bash"

    def test_parser_accepts_completion_zsh(self):
        from cja_auto_sdr.cli.parser import parse_arguments

        args = parse_arguments(["--completion", "zsh", "dv_test"])
        assert args.completion == "zsh"

    def test_parser_accepts_completion_fish(self):
        from cja_auto_sdr.cli.parser import parse_arguments

        args = parse_arguments(["--completion", "fish", "dv_test"])
        assert args.completion == "fish"

    def test_parser_rejects_invalid_shell(self):
        from cja_auto_sdr.cli.parser import parse_arguments

        with pytest.raises(SystemExit):
            parse_arguments(["--completion", "powershell", "dv_test"])

    def test_parser_completion_default_is_none(self):
        from cja_auto_sdr.cli.parser import parse_arguments

        args = parse_arguments(["dv_test"])
        assert args.completion is None


# ---------------------------------------------------------------------------
# Completion script content validation
# ---------------------------------------------------------------------------


class TestCompletionScriptContent:
    """Validate the static content of each shell's activation script."""

    def test_bash_script_content(self):
        from cja_auto_sdr.__main__ import _COMPLETION_SCRIPTS

        script = _COMPLETION_SCRIPTS["bash"]
        assert "register-python-argcomplete" in script
        assert "cja_auto_sdr" in script
        assert "eval" in script

    def test_zsh_script_content(self):
        from cja_auto_sdr.__main__ import _COMPLETION_SCRIPTS

        script = _COMPLETION_SCRIPTS["zsh"]
        assert "bashcompinit" in script
        assert "autoload" in script
        assert "register-python-argcomplete" in script
        assert "cja_auto_sdr" in script

    def test_fish_script_content(self):
        from cja_auto_sdr.__main__ import _COMPLETION_SCRIPTS

        script = _COMPLETION_SCRIPTS["fish"]
        assert "--shell fish" in script
        assert "register-python-argcomplete" in script
        assert "cja_auto_sdr" in script
        assert "| source" in script

    def test_all_supported_shells_have_scripts(self):
        from cja_auto_sdr.__main__ import _COMPLETION_SCRIPTS, _SUPPORTED_SHELLS

        assert set(_COMPLETION_SCRIPTS.keys()) == _SUPPORTED_SHELLS

    @pytest.mark.parametrize(
        ("shell", "argv0", "expected_command"),
        [
            ("bash", "cja-auto-sdr", "cja-auto-sdr"),
            ("zsh", "/tmp/cja-auto-sdr", "cja-auto-sdr"),
            ("fish", "__main__.py", "cja_auto_sdr"),
        ],
    )
    def test_render_completion_script_uses_resolved_command_name(self, shell, argv0, expected_command):
        from cja_auto_sdr.__main__ import _render_completion_script, _resolve_completion_command_name

        script = _render_completion_script(shell, _resolve_completion_command_name(argv0))
        assert expected_command in script
        assert "register-python-argcomplete" in script


# ---------------------------------------------------------------------------
# Safety-net: generator._main_impl handles --completion
# ---------------------------------------------------------------------------


class TestCompletionSafetyNet:
    """Verify the generator._main_impl safety net for --completion."""

    @pytest.mark.parametrize("shell", ["bash", "zsh", "fish"])
    def test_generator_safety_net_handles_completion(self, shell, capsys):
        """If --completion reaches _main_impl, it should still be handled."""
        from cja_auto_sdr.generator import _main_impl

        with (
            patch.object(sys, "argv", ["cja_auto_sdr", "--completion", shell, "dv_test"]),
            patch.dict("sys.modules", {"argcomplete": type(sys)("argcomplete")}),
        ):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()

        assert int(exc_info.value.code) == 0
        stdout = capsys.readouterr().out
        assert "register-python-argcomplete" in stdout

    def test_generator_safety_net_uses_invoked_command_name(self, capsys):
        """Safety-net path should still register completion for the invoked entrypoint."""
        from cja_auto_sdr.generator import _main_impl

        with (
            patch.object(sys, "argv", ["cja-auto-sdr", "--completion", "bash", "dv_test"]),
            patch.dict("sys.modules", {"argcomplete": type(sys)("argcomplete")}),
        ):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()

        assert int(exc_info.value.code) == 0
        stdout = capsys.readouterr().out
        assert "register-python-argcomplete cja-auto-sdr" in stdout

    def test_generator_safety_net_bypasses_workers_validation(self, capsys):
        """Completion should run before unrelated global validation in _main_impl."""
        from cja_auto_sdr.generator import _main_impl

        with (
            patch.object(sys, "argv", ["cja_auto_sdr", "--completion", "bash", "--workers", "0"]),
            patch.dict("sys.modules", {"argcomplete": type(sys)("argcomplete")}),
        ):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()

        assert int(exc_info.value.code) == 0
        captured = capsys.readouterr()
        assert "--workers must be at least 1" not in captured.err
        assert "register-python-argcomplete" in captured.out

    def test_generator_safety_net_bypasses_quality_policy_loading(self, capsys):
        """Completion should not attempt to load quality-policy files."""
        from cja_auto_sdr.generator import _main_impl

        with (
            patch.object(
                sys,
                "argv",
                ["cja_auto_sdr", "--completion", "bash", "--quality-policy", "/tmp/does-not-exist-policy.json"],
            ),
            patch.dict("sys.modules", {"argcomplete": type(sys)("argcomplete")}),
        ):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()

        assert int(exc_info.value.code) == 0
        captured = capsys.readouterr()
        assert "Failed to load --quality-policy" not in captured.err
        assert "register-python-argcomplete" in captured.out

    def test_generator_safety_net_exit_codes_precedes_completion(self):
        """Mixed --exit-codes/--completion should dispatch exit-codes branch first."""
        from cja_auto_sdr.generator import _main_impl

        run_state: dict[str, object] = {}
        with (
            patch.object(sys, "argv", ["cja_auto_sdr", "--exit-codes", "--completion", "bash"]),
            patch("cja_auto_sdr.core.exit_codes.print_exit_codes") as mock_print_exit_codes,
            patch("cja_auto_sdr.generator._handle_completion_prevalidation") as mock_completion_prevalidation,
        ):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl(run_state=run_state)

        assert int(exc_info.value.code) == 0
        assert run_state["mode"] == "exit_codes"
        mock_print_exit_codes.assert_called_once()
        mock_completion_prevalidation.assert_not_called()
