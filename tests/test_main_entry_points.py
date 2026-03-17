"""Tests for main() and _main_impl() entry points.

Validates that the CLI entry points correctly dispatch to different modes,
handle exit codes, track run_state, and emit run summary JSON.
"""

import json
import logging
import os
import sys
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from unittest.mock import patch

import pytest

from cja_auto_sdr.generator import _main_impl, main, parse_arguments


def _mock_cli_option_specified(option_name, argv=None):
    """Stub that always returns False — prevents _known_long_options() from
    calling parse_arguments(return_parser=True) while it is mocked."""
    return False


class TestMainImplDiscoveryDispatch:
    """Test _main_impl dispatches discovery commands correctly."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_dataviews")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_list_dataviews_dispatches_and_exits_zero(self, _mock_conf, mock_list_dv):
        mock_list_dv.return_value = True
        run_state = {"mode": "unknown", "details": {}}

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--list-dataviews"])
                _main_impl(run_state=run_state)

        assert exc_info.value.code == 0
        mock_list_dv.assert_called_once()
        assert run_state["mode"] == "discovery"
        assert run_state["details"]["discovery_command"] == "list_dataviews"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_connections")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_list_connections_dispatches_and_exits_zero(self, _mock_conf, mock_list_conn):
        mock_list_conn.return_value = True
        run_state = {"mode": "unknown", "details": {}}

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--list-connections"])
                _main_impl(run_state=run_state)

        assert exc_info.value.code == 0
        mock_list_conn.assert_called_once()

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_dataviews")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_discovery_failure_exits_one(self, _mock_conf, mock_list_dv):
        mock_list_dv.return_value = False  # Simulate failure

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--list-dataviews"])
                _main_impl()

        assert exc_info.value.code == 1


class TestMainImplExitCodes:
    """Test _main_impl --exit-codes mode."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_exit_codes_prints_reference_and_exits_zero(self):
        stdout = StringIO()

        with pytest.raises(SystemExit) as exc_info:
            with redirect_stdout(stdout):
                with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                    mock_pa.return_value = parse_arguments(["--exit-codes"])
                    _main_impl()

        assert exc_info.value.code == 0
        output = stdout.getvalue()
        assert "EXIT CODE REFERENCE" in output
        assert "0" in output and "Success" in output
        assert "1" in output and "Error" in output
        assert "2" in output

    @patch("cja_auto_sdr.core.exit_codes.print_exit_codes")
    def test_help_takes_precedence_over_raw_exit_codes_dispatch(self, mock_print_exit_codes, capsys):
        with patch.object(sys, "argv", ["cja_auto_sdr", "--exit-codes", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()

        assert int(exc_info.value.code) == 0
        assert "usage:" in capsys.readouterr().out.lower()
        mock_print_exit_codes.assert_not_called()


class TestMainImplSampleConfig:
    """Test _main_impl --sample-config mode."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.generate_sample_config")
    def test_sample_config_success_exits_zero(self, mock_gen):
        mock_gen.return_value = True
        run_state = {"mode": "unknown", "details": {}}

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--sample-config"])
                _main_impl(run_state=run_state)

        assert exc_info.value.code == 0
        assert run_state["details"]["operation_success"] is True

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.generate_sample_config")
    def test_sample_config_failure_exits_one(self, mock_gen):
        mock_gen.return_value = False

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--sample-config"])
                _main_impl()

        assert exc_info.value.code == 1

    @patch("cja_auto_sdr.generator.generate_sample_config")
    def test_invalid_unknown_flag_falls_through_to_argparse_error(self, mock_gen, capsys):
        with patch.object(sys, "argv", ["cja_auto_sdr", "--sample-config", "--bogus"]):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()

        assert exc_info.value.code == 2
        mock_gen.assert_not_called()
        assert "unrecognized arguments: --bogus" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator.generate_sample_config")
    def test_missing_passthrough_value_does_not_dispatch_sample_config(self, mock_gen, capsys):
        with patch.object(sys, "argv", ["cja_auto_sdr", "--sample-config", "--workers", "--profile"]):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()

        assert exc_info.value.code == 2
        mock_gen.assert_not_called()
        assert "expected one argument" in capsys.readouterr().err


class TestMainImplProfileManagement:
    """Test _main_impl profile management commands."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_profiles")
    def test_profile_list_dispatches(self, mock_list):
        mock_list.return_value = True

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--profile-list"])
                _main_impl()

        assert exc_info.value.code == 0
        mock_list.assert_called_once()

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_profiles")
    def test_profile_list_excel_warns_and_falls_back_to_table(self, mock_list, caplog):
        """Unsupported --profile-list formats should warn and route to table output."""
        mock_list.return_value = True

        with caplog.at_level(logging.WARNING, logger="cja_auto_sdr.generator"):
            with pytest.raises(SystemExit) as exc_info:
                with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                    mock_pa.return_value = parse_arguments(["--profile-list", "--format", "excel"])
                    _main_impl()

        assert exc_info.value.code == 0
        mock_list.assert_called_once_with(output_format="table")
        assert "--profile-list" in caplog.text
        assert "using table" in caplog.text

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.test_profile")
    def test_profile_test_dispatches(self, mock_test):
        mock_test.return_value = True

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--profile-test", "myprofile"])
                _main_impl()

        assert exc_info.value.code == 0
        mock_test.assert_called_once_with("myprofile")

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.show_profile")
    def test_profile_show_dispatches(self, mock_show):
        mock_show.return_value = True

        with pytest.raises(SystemExit) as exc_info:
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--profile-show", "myprofile"])
                _main_impl()

        assert exc_info.value.code == 0
        mock_show.assert_called_once_with("myprofile")


class TestMainImplRunState:
    """Test that _main_impl populates run_state correctly."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_run_state_mode_set_for_exit_codes(self):
        run_state = {"mode": "unknown", "details": {}}

        with pytest.raises(SystemExit):
            with redirect_stdout(StringIO()):
                with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                    mock_pa.return_value = parse_arguments(["--exit-codes"])
                    _main_impl(run_state=run_state)

        assert run_state["mode"] == "exit_codes"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.__main__._handle_completion")
    def test_run_state_mode_set_for_completion(self, mock_handle_completion):
        run_state = {"mode": "unknown", "details": {}}
        mock_handle_completion.side_effect = SystemExit(0)

        with pytest.raises(SystemExit):
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--completion", "bash"])
                _main_impl(run_state=run_state)

        assert run_state["mode"] == "completion"
        mock_handle_completion.assert_called_once()

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_profiles")
    def test_run_state_mode_set_for_profile_management(self, mock_list):
        mock_list.return_value = True
        run_state = {"mode": "unknown", "details": {}}

        with pytest.raises(SystemExit):
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--profile-list"])
                _main_impl(run_state=run_state)

        assert run_state["mode"] == "profile_management"

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.list_dataviews")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_run_state_captures_discovery_format(self, _mock_conf, mock_list_dv):
        mock_list_dv.return_value = True
        run_state = {"mode": "unknown", "details": {}}

        with pytest.raises(SystemExit):
            with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                mock_pa.return_value = parse_arguments(["--list-dataviews", "--format", "json"])
                _main_impl(run_state=run_state)

        assert run_state["output_format"] == "json"

    def test_raw_standalone_run_summary_syncs_profile_and_config_metadata(self, capsys):
        """Standalone early exits should still emit parser-derived run-summary metadata."""
        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "--exit-codes", "--profile", "demo", "--run-summary-json", "stdout"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert int(exc_info.value.code) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["mode"] == "exit_codes"
        assert payload["profile"] == "demo"
        assert payload["config_file"] == "config.json"

    def test_raw_standalone_run_summary_normalizes_attached_short_profile_values(self, capsys):
        """Standalone reparse should preserve argparse semantics for -p=VALUE."""
        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "--exit-codes", "-p=demo", "--run-summary-json", "stdout"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert int(exc_info.value.code) == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["mode"] == "exit_codes"
        assert payload["profile"] == "demo"

    def test_raw_standalone_ignores_typed_runtime_flags_across_parser_groups(self, capsys):
        """Standalone run-summary dispatch should ignore unrelated typed parser options."""
        with patch.object(
            sys,
            "argv",
            [
                "cja_auto_sdr",
                "--exit-codes",
                "--run-summary-json",
                "stdout",
                "--cache-size",
                "oops",
                "--max-issues",
                "nope",
                "--api-min-workers",
                "bad",
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert int(exc_info.value.code) == 0
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["mode"] == "exit_codes"
        assert payload["exit_code"] == 0
        assert "EXIT CODE REFERENCE" in captured.err
        assert "--cache-size" not in captured.err
        assert "--max-issues" not in captured.err
        assert "--api-min-workers" not in captured.err

    def test_raw_standalone_run_summary_honors_output_dir_for_relative_summary_files(self, tmp_path, monkeypatch):
        """Relative run-summary targets should resolve under explicit --output-dir."""
        monkeypatch.chdir(tmp_path)
        reports_dir = tmp_path / "reports"
        summary_path = reports_dir / "summary.json"

        with patch.object(
            sys,
            "argv",
            [
                "cja_auto_sdr",
                "--exit-codes",
                "--run-summary-json",
                "summary.json",
                "--output-dir",
                "reports",
                "--format",
                "json",
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert int(exc_info.value.code) == 0
        assert summary_path.exists()
        assert not (tmp_path / "summary.json").exists()
        payload = json.loads(summary_path.read_text(encoding="utf-8"))
        assert payload["mode"] == "exit_codes"
        assert payload["output_format"] == "json"

    def test_raw_standalone_version_still_wins_with_run_summary_stdout(self, capsys):
        """Argparse version action should beat raw standalone dispatch when summary output is requested."""
        from cja_auto_sdr.core.version import __version__

        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "--exit-codes", "--version", "--run-summary-json", "stdout"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert int(exc_info.value.code) == 0
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert payload["mode"] == "unknown"
        assert payload["exit_code"] == 0
        assert "EXIT CODE REFERENCE" not in captured.err
        assert __version__ in captured.err


class TestMainWrapper:
    """Test the main() wrapper function."""

    def test_main_normal_completion_no_system_exit(self):
        """Normal completion of _main_impl should not raise SystemExit."""
        with patch("cja_auto_sdr.generator._main_impl") as mock_impl:
            mock_impl.return_value = None  # Normal completion
            with patch("cja_auto_sdr.generator._cli_option_value", return_value=None):
                # Should not raise — main() returns normally when _main_impl succeeds
                main()

    def test_main_captures_keyboard_interrupt(self):
        with patch("cja_auto_sdr.generator._main_impl") as mock_impl:
            mock_impl.side_effect = KeyboardInterrupt()
            with pytest.raises(KeyboardInterrupt):
                with patch("cja_auto_sdr.generator._cli_option_value", return_value=None):
                    main()

    def test_main_captures_system_exit(self):
        with patch("cja_auto_sdr.generator._main_impl") as mock_impl:
            mock_impl.side_effect = SystemExit(2)
            with pytest.raises(SystemExit) as exc_info:
                with patch("cja_auto_sdr.generator._cli_option_value", return_value=None):
                    main()
            assert exc_info.value.code == 2

    def test_main_emits_run_summary_json(self, tmp_path):
        summary_file = str(tmp_path / "summary.json")
        with patch("cja_auto_sdr.generator._main_impl") as mock_impl:
            mock_impl.return_value = None
            with patch("cja_auto_sdr.generator._cli_option_value", return_value=summary_file):
                main()

        # Verify the summary file was created and is valid JSON
        assert os.path.isfile(summary_file)
        with open(summary_file) as f:
            summary = json.load(f)

        assert "summary_version" in summary
        assert "tool_version" in summary
        assert "exit_code" in summary
        assert summary["exit_code"] == 0
        assert "started_at" in summary
        assert "ended_at" in summary
        assert "duration_seconds" in summary
        assert summary["duration_seconds"] >= 0

    def test_main_emits_run_summary_on_failure(self, tmp_path):
        summary_file = str(tmp_path / "fail_summary.json")
        with patch("cja_auto_sdr.generator._main_impl") as mock_impl:
            mock_impl.side_effect = SystemExit(1)
            with pytest.raises(SystemExit):
                with patch("cja_auto_sdr.generator._cli_option_value", return_value=summary_file):
                    main()

        assert os.path.isfile(summary_file)
        with open(summary_file) as f:
            summary = json.load(f)
        assert summary["exit_code"] == 1

    def test_main_restores_sys_exit(self):
        """main() must restore the original sys.exit even on failure."""
        original_exit = sys.exit
        with patch("cja_auto_sdr.generator._main_impl") as mock_impl:
            mock_impl.side_effect = SystemExit(0)
            with pytest.raises(SystemExit):
                with patch("cja_auto_sdr.generator._cli_option_value", return_value=None):
                    main()
        # sys.exit should be restored to original
        assert sys.exit is original_exit


class TestMainImplNoDataViews:
    """Test _main_impl when no data views are provided for SDR mode."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_no_data_views_exits_with_error(self):
        stderr = StringIO()

        with pytest.raises(SystemExit) as exc_info:
            with redirect_stderr(stderr):
                with patch("cja_auto_sdr.generator.parse_arguments") as mock_pa:
                    # No data views, no special flags — should trigger the
                    # "no data views provided" error path
                    args = parse_arguments([])
                    # Override data_views to be empty
                    args.data_views = []
                    mock_pa.return_value = args
                    _main_impl()

        # Should exit with error code
        assert exc_info.value.code != 0
