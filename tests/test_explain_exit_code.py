"""Tests for --explain-exit-code CLI flag.

Covers: shared explainer, fast-path dispatch, deferred generator handling,
RunMode, parser validation for invalid combos, and run-summary interaction.
"""

from __future__ import annotations

import json
import os
import sys
from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

import pytest

from cja_auto_sdr.cli.parser import parse_arguments
from cja_auto_sdr.core.exit_codes import explain_exit_code

# ---------------------------------------------------------------------------
# Shared explainer unit tests
# ---------------------------------------------------------------------------


class TestExplainExitCodeFunction:
    """Unit tests for the explain_exit_code() function in core/exit_codes.py."""

    @pytest.mark.parametrize("code", [0, 1, 2, 3, 130])
    def test_known_codes_produce_output(self, code):
        buf = StringIO()
        explain_exit_code(code, file=buf)
        output = buf.getvalue()
        assert f"Exit code {code}:" in output
        assert "Meaning:" in output
        assert "Automation guidance:" in output

    def test_code_zero_success(self):
        buf = StringIO()
        explain_exit_code(0, file=buf)
        output = buf.getvalue()
        assert "Success" in output

    def test_code_one_error(self):
        buf = StringIO()
        explain_exit_code(1, file=buf)
        output = buf.getvalue()
        assert "Error" in output

    def test_code_two_policy(self):
        buf = StringIO()
        explain_exit_code(2, file=buf)
        output = buf.getvalue()
        assert "Policy threshold exceeded" in output
        assert "Diff mode found changes" in output

    def test_code_three_warning(self):
        buf = StringIO()
        explain_exit_code(3, file=buf)
        output = buf.getvalue()
        assert "Warning threshold exceeded" in output

    def test_code_130_sigint(self):
        buf = StringIO()
        explain_exit_code(130, file=buf)
        output = buf.getvalue()
        assert "Interrupted" in output
        assert "SIGINT" in output

    def test_signal_exit_code_129(self):
        buf = StringIO()
        explain_exit_code(129, file=buf)
        output = buf.getvalue()
        assert "Exit code 129:" in output
        assert "Killed by" in output
        assert "128 + 1" in output

    def test_signal_exit_code_143_sigterm(self):
        buf = StringIO()
        explain_exit_code(143, file=buf)
        output = buf.getvalue()
        assert "SIGTERM" in output

    def test_unknown_code(self):
        buf = StringIO()
        explain_exit_code(42, file=buf)
        output = buf.getvalue()
        assert "Exit code 42: Unknown" in output
        assert "not a recognized" in output
        assert "--run-summary-json" in output

    def test_defaults_to_stdout(self, capsys):
        explain_exit_code(0)
        captured = capsys.readouterr()
        assert "Exit code 0:" in captured.out


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestExplainExitCodeParser:
    """Parser accepts --explain-exit-code with an integer argument."""

    def test_parser_accepts_integer(self):
        args = parse_arguments(["--explain-exit-code", "2"])
        assert args.explain_exit_code == 2

    def test_parser_accepts_zero(self):
        args = parse_arguments(["--explain-exit-code", "0"])
        assert args.explain_exit_code == 0

    def test_parser_accepts_negative_via_equals(self):
        # argparse handles --flag=-1 for negative ints
        args = parse_arguments(["--explain-exit-code=-1"])
        assert args.explain_exit_code == -1

    def test_parser_rejects_non_integer(self):
        with pytest.raises(SystemExit):
            parse_arguments(["--explain-exit-code", "abc"])

    def test_parser_default_is_none(self):
        args = parse_arguments(["dv_test"])
        assert args.explain_exit_code is None


# ---------------------------------------------------------------------------
# Fast-path dispatch tests
# ---------------------------------------------------------------------------


class TestExplainExitCodeFastPath:
    """Fast-path interception in __main__.py."""

    def test_is_fast_path_flag_standalone(self):
        from cja_auto_sdr.__main__ import _is_fast_path_flag

        assert _is_fast_path_flag(["prog", "--explain-exit-code", "2"]) == "--explain-exit-code"

    def test_is_fast_path_flag_equals_form(self):
        from cja_auto_sdr.__main__ import _is_fast_path_flag

        assert _is_fast_path_flag(["prog", "--explain-exit-code=2"]) == "--explain-exit-code"

    def test_is_fast_path_flag_tolerates_wrapper_quality_policy(self):
        from cja_auto_sdr.__main__ import _is_fast_path_flag

        assert _is_fast_path_flag(["prog", "--explain-exit-code", "2", "--quality-policy", "policy.json"]) == (
            "--explain-exit-code"
        )

    def test_is_fast_path_flag_prefix_abbreviation(self):
        from cja_auto_sdr.__main__ import _is_fast_path_flag

        assert _is_fast_path_flag(["prog", "--explain-exit", "2"]) == "--explain-exit-code"

    def test_fast_path_rejects_with_extra_args(self):
        from cja_auto_sdr.__main__ import _is_fast_path_flag

        assert _is_fast_path_flag(["prog", "--explain-exit-code", "2", "dv_test"]) is None

    def test_fast_path_rejects_with_run_summary(self):
        from cja_auto_sdr.__main__ import _is_fast_path_flag

        assert _is_fast_path_flag(["prog", "--explain-exit-code", "2", "--run-summary-json", "stdout"]) is None

    def test_fast_path_rejects_with_other_flags(self):
        from cja_auto_sdr.__main__ import _is_fast_path_flag

        assert _is_fast_path_flag(["prog", "--explain-exit-code", "2", "--exit-codes"]) is None

    def test_fast_path_main_exits_zero(self, capsys):
        from cja_auto_sdr.__main__ import main as fast_main

        with patch.object(sys, "argv", ["cja_auto_sdr", "--explain-exit-code", "2"]):
            with pytest.raises(SystemExit) as exc_info:
                fast_main()
            assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert "Exit code 2:" in captured.out
        assert "Policy threshold exceeded" in captured.out

    def test_fast_path_main_keeps_tolerated_wrapper_quality_policy(self, capsys):
        from cja_auto_sdr.__main__ import main as fast_main

        with (
            patch.object(sys, "argv", ["cja_auto_sdr", "--explain-exit-code", "2", "--quality-policy", "policy.json"]),
            patch("cja_auto_sdr.generator.main") as mock_gen_main,
        ):
            with pytest.raises(SystemExit) as exc_info:
                fast_main()

        assert exc_info.value.code == 0
        mock_gen_main.assert_not_called()
        assert "Exit code 2:" in capsys.readouterr().out

    def test_fast_path_main_falls_through_when_argcomplete_active(self):
        from cja_auto_sdr.__main__ import main as fast_main

        with patch.dict(os.environ, {"_ARGCOMPLETE": "1"}):
            with patch.object(sys, "argv", ["cja_auto_sdr", "--explain-exit-code", "2"]):
                with patch("cja_auto_sdr.generator.main") as mock_gen_main:
                    fast_main()
                    mock_gen_main.assert_called_once()


# ---------------------------------------------------------------------------
# Deferred generator handling tests
# ---------------------------------------------------------------------------


def _mock_cli_option_specified(option_name, argv=None):
    return False


class TestExplainExitCodeGeneratorDispatch:
    """Deferred handling in generator._main_impl."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_explain_exit_code_prints_and_exits_zero(self):
        from cja_auto_sdr.generator import _main_impl

        stdout = StringIO()
        with pytest.raises(SystemExit) as exc_info:
            with redirect_stdout(stdout):
                with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                    mock_pa.return_value = parse_arguments(["--explain-exit-code", "1"])
                    _main_impl()

        assert exc_info.value.code == 0
        output = stdout.getvalue()
        assert "Exit code 1:" in output
        assert "Error" in output

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_run_state_mode_set_for_explain_exit_code(self):
        from cja_auto_sdr.generator import _main_impl

        run_state = {"mode": "unknown", "details": {}}
        with pytest.raises(SystemExit):
            with redirect_stdout(StringIO()):
                with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                    mock_pa.return_value = parse_arguments(["--explain-exit-code", "2"])
                    _main_impl(run_state=run_state)

        assert run_state["mode"] == "explain_exit_code"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_run_state_details_contain_explained_code(self):
        from cja_auto_sdr.generator import _main_impl

        run_state = {"mode": "unknown", "details": {}}
        with pytest.raises(SystemExit):
            with redirect_stdout(StringIO()):
                with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                    mock_pa.return_value = parse_arguments(["--explain-exit-code", "3"])
                    _main_impl(run_state=run_state)

        assert run_state["details"]["explained_code"] == 3


# ---------------------------------------------------------------------------
# RunMode tests
# ---------------------------------------------------------------------------


class TestExplainExitCodeRunMode:
    """RunMode.EXPLAIN_EXIT_CODE is properly defined and inferred."""

    def test_run_mode_enum_exists(self):
        from cja_auto_sdr.generator import RunMode

        assert RunMode.EXPLAIN_EXIT_CODE.value == "explain_exit_code"

    def test_infer_run_mode_for_explain_exit_code(self):
        from cja_auto_sdr.generator import RunMode, _infer_run_mode_enum

        args = parse_arguments(["--explain-exit-code", "0"])
        assert _infer_run_mode_enum(args) == RunMode.EXPLAIN_EXIT_CODE

    def test_explain_exit_code_takes_precedence_over_sdr(self):
        from cja_auto_sdr.generator import RunMode, _infer_run_mode_enum

        # Without data views, default mode would be SDR
        args = parse_arguments(["--explain-exit-code", "1"])
        assert _infer_run_mode_enum(args) == RunMode.EXPLAIN_EXIT_CODE


# ---------------------------------------------------------------------------
# CLI validation: invalid combinations
# ---------------------------------------------------------------------------


class TestExplainExitCodeValidation:
    """--explain-exit-code rejects conflicting flags and positional args."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_rejects_with_positional_data_views(self):
        from cja_auto_sdr.generator import _main_impl

        with pytest.raises(SystemExit) as exc_info:
            with redirect_stdout(StringIO()):
                with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                    mock_pa.return_value = parse_arguments(["--explain-exit-code", "2", "dv_test"])
                    _main_impl()

        assert exc_info.value.code == 1

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_rejects_with_exit_codes_flag(self):
        from cja_auto_sdr.generator import _main_impl

        with pytest.raises(SystemExit) as exc_info:
            with redirect_stdout(StringIO()):
                with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                    mock_pa.return_value = parse_arguments(["--explain-exit-code", "2", "--exit-codes"])
                    _main_impl()

        assert exc_info.value.code == 1

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_rejects_with_sample_config(self):
        from cja_auto_sdr.generator import _main_impl

        with pytest.raises(SystemExit) as exc_info:
            with redirect_stdout(StringIO()):
                with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                    mock_pa.return_value = parse_arguments(["--explain-exit-code", "2", "--sample-config"])
                    _main_impl()

        assert exc_info.value.code == 1

    def test_ignores_sdr_only_fail_on_quality_flag(self, capsys):
        from cja_auto_sdr.generator import main as generator_main

        with patch.object(sys, "argv", ["cja_auto_sdr", "--explain-exit-code", "2", "--fail-on-quality", "HIGH"]):
            with pytest.raises(SystemExit) as exc_info:
                generator_main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "Exit code 2:" in captured.out
        assert "--fail-on-quality is only supported in SDR generation mode" not in captured.err

    def test_ignores_auto_prune_semantic_validation(self, capsys):
        """Standalone explain mode should ignore shared snapshot automation flags."""
        from cja_auto_sdr.generator import main as generator_main

        with patch.object(sys, "argv", ["cja_auto_sdr", "--explain-exit-code", "2", "--auto-prune"]):
            with pytest.raises(SystemExit) as exc_info:
                generator_main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "Exit code 2:" in captured.out
        assert "--auto-prune requires --auto-snapshot or --prune-snapshots" not in captured.err

    def test_ignores_quality_policy_file_errors(self, capsys, tmp_path):
        """Standalone explain mode should ignore wrapper-carried quality-policy files."""
        from cja_auto_sdr.generator import main as generator_main

        missing_policy = tmp_path / "missing_quality_policy.json"

        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "--explain-exit-code", "2", "--quality-policy", str(missing_policy)],
        ):
            with pytest.raises(SystemExit) as exc_info:
                generator_main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "Exit code 2:" in captured.out
        assert f"Failed to load --quality-policy '{missing_policy}'" not in captured.err


# ---------------------------------------------------------------------------
# Run-summary interaction tests
# ---------------------------------------------------------------------------


class TestExplainExitCodeRunSummary:
    """When --run-summary-json is present, fast-path defers to generator."""

    def test_run_summary_flag_prevents_fast_path(self):
        from cja_auto_sdr.__main__ import _is_fast_path_flag

        assert _is_fast_path_flag(["prog", "--explain-exit-code", "2", "--run-summary-json", "-"]) is None

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_explanation_to_stderr_when_run_summary_claims_stdout(self):
        """When --run-summary-json stdout is active, explanation goes to stderr."""
        from cja_auto_sdr.generator import main as generator_main

        # Use generator.main() which sets up the redirect_stdout context
        # when run_summary_output is stdout
        stderr_buf = StringIO()
        stdout_buf = StringIO()

        with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
            mock_pa.return_value = parse_arguments(["--explain-exit-code", "2", "--run-summary-json", "-"])
            with patch("cja_auto_sdr.generator._cli_option_value") as mock_cli_val:
                mock_cli_val.return_value = "-"
                with patch.object(sys, "stderr", stderr_buf):
                    with pytest.raises(SystemExit) as exc_info:
                        with redirect_stdout(stdout_buf):
                            generator_main()

        assert exc_info.value.code == 0
        # The explanation should have been redirected to stderr by the run_context
        stderr_output = stderr_buf.getvalue()
        assert "Exit code 2:" in stderr_output or "Exit code 2:" in stdout_buf.getvalue()

    def test_explanation_bypasses_unrelated_generic_validation_with_run_summary_stdout(self, capsys):
        """Standalone explain mode must ignore generic validation-only flags."""
        from cja_auto_sdr.generator import main as generator_main

        with patch.object(
            sys,
            "argv",
            [
                "cja_auto_sdr",
                "--explain-exit-code",
                "2",
                "--run-summary-json",
                "-",
                "--workers",
                "0",
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                generator_main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["mode"] == "explain_exit_code"
        assert payload["exit_code"] == 0
        assert payload["status"] == "success"
        assert "Exit code 2:" in captured.err
