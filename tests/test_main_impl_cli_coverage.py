"""Tests for uncovered lines in _main_impl() in generator.py.

Targets the following uncovered blocks:
  - Block 1:  Worker validation (lines 13656-13679)
  - Block 2:  --interactive with args warning (lines 13913-13919)
  - Block 3:  --include-all-inventory flags (lines 14095, 14100, 14106, 14116)
  - Block 4:  --diff mode validation (lines 14329-14336)
  - Block 5:  Diff source/target name resolution ambiguity (lines 14410-14465)
  - Block 6:  --snapshot name resolution ambiguity (lines 14549-14571)
  - Block 7:  --compare-with-prev name resolution ambiguity (lines 14619-14641)
  - Block 8:  Data view name resolution display (lines 14808-14839)
  - Block 9:  Large batch confirmation (lines 14884-14904)
  - Block 10: Production mode log level (line 14915)
  - Block 11: Inventory summary display in single mode (lines 15329-15354)
  - Block 12: Git commit integration (lines 15362-15442)
  - Block 13: Open file in batch mode (lines 15250-15262)
  - Block 14: --validate-config color policy (--no-color vs FORCE_COLOR)
"""

import argparse
from unittest.mock import MagicMock, patch

import pytest

from cja_auto_sdr.core.exceptions import APIError
from cja_auto_sdr.generator import (
    MAX_BATCH_WORKERS,
    ProcessingResult,
    _main_impl,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mock_cli_option_specified(option_name, argv=None):
    """Stub that always returns False — prevents real sys.argv inspection."""
    return False


def _make_args(**overrides):
    """Build a complete argparse.Namespace for _main_impl.

    Provides sensible defaults for every attribute that _main_impl reads so
    that tests only need to override the attributes relevant to the code path
    under test.
    """
    defaults = {
        # Core args
        "data_views": [],
        "config_file": "config.json",
        "format": None,
        "output_dir": "/tmp/output",
        "output": None,
        "quiet": False,
        "workers": "1",
        "log_level": "INFO",
        "log_format": "default",
        "skip_validation": False,
        "production": False,
        "cache_size": 100,
        "cache_ttl": 300,
        "max_issues": 0,
        "max_retries": 3,
        "retry_base_delay": 1.0,
        "retry_max_delay": 30.0,
        "assume_yes": False,
        "dry_run": False,
        "validate_config": False,
        "show_config": False,
        "sample_config": False,
        "include_derived_inventory": False,
        "include_calculated_metrics": False,
        "include_segments_inventory": False,
        "include_all_inventory": False,
        "inventory_only": False,
        "inventory_order": None,
        "inventory_summary": False,
        "metrics_only": False,
        "dimensions_only": False,
        "interactive": False,
        "open": False,
        "git_commit": False,
        "git_push": False,
        "git_dir": "/tmp/sdr-snapshots",
        "git_message": None,
        "git_init": False,
        "run_summary": None,
        "run_summary_json": None,
        "quality_policy": None,
        "no_color": False,
        "color_theme": "default",
        "exit_codes": False,
        "profile": None,
        "profile_list": False,
        "profile_add": None,
        "profile_test": None,
        "profile_import": None,
        "profile_show": None,
        "profile_overwrite": False,
        "list_dataviews": False,
        "list_connections": False,
        "list_datasets": False,
        "config_status": False,
        "config_json": False,
        "diff": False,
        "snapshot": None,
        "diff_snapshot": None,
        "compare_snapshots": None,
        "compare_with_prev": False,
        "batch": False,
        "enable_cache": True,
        "clear_cache": False,
        "show_timings": False,
        "continue_on_error": False,
        "shared_cache": False,
        "name_match": "exact",
        "fail_on_quality": None,
        "quality_report": None,
        "auto_prune": False,
        "auto_snapshot": False,
        "prune_snapshots": False,
        "list_snapshots": False,
        "snapshot_dir": "/tmp/snapshots",
        "keep_last": 0,
        "keep_since": None,
        "org_sample_size": None,
        "stats": False,
        "org_report": False,
        "api_auto_tune": False,
        "circuit_breaker": False,
        "changes_only": False,
        "summary": False,
        "ignore_fields": None,
        "label_source": None,
        "label_target": None,
        "show_only": None,
        "extended_fields": False,
        "side_by_side": False,
        "quiet_diff": False,
        "reverse_diff": False,
        "warn_threshold": None,
        "group_by_field": False,
        "group_by_field_limit": 10,
        "diff_output": None,
        "format_pr_comment": False,
    }
    defaults.update(overrides)
    return argparse.Namespace(**defaults)


# Common patches applied to every test via the _impl helper.
_COMMON_PATCHES = {
    "cja_auto_sdr.generator._cli_option_specified": _mock_cli_option_specified,
}


def _run_main_impl(args, run_state=None, extra_patches=None):
    """Run _main_impl with common mocks already applied.

    Returns (exit_code_or_None, stdout, stderr).
    """
    patches = dict(_COMMON_PATCHES)
    if extra_patches:
        patches.update(extra_patches)

    stack = []
    for target, replacement in patches.items():
        p = patch(target, replacement)
        stack.append(p)

    for p in stack:
        p.start()

    try:
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl(run_state=run_state)
                return None  # Did not exit
            except SystemExit as exc:
                return exc.code
    finally:
        for p in stack:
            p.stop()


# =========================================================================
# Block 1 — Worker validation  (lines 13656-13679)
# =========================================================================


class TestWorkerValidation:
    """Tests for --workers value parsing and bounds checks."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_workers_non_integer_exits_1(self, capsys):
        """Line 13656-13659: non-integer --workers value."""
        args = _make_args(workers="abc")
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--workers must be 'auto' or an integer" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_workers_float_string_exits_1(self, capsys):
        """Line 13656-13659: float string is not a valid integer."""
        args = _make_args(workers="3.5")
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "got '3.5'" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_workers_zero_exits_1(self, capsys):
        """Line 13662-13663: --workers 0 is below minimum."""
        args = _make_args(workers="0")
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--workers must be at least 1" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_workers_negative_exits_1(self, capsys):
        """Line 13662-13663: negative --workers value."""
        args = _make_args(workers="-2")
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--workers must be at least 1" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_workers_exceeds_max_exits_1(self, capsys):
        """Line 13664-13665: --workers above MAX_BATCH_WORKERS."""
        args = _make_args(workers=str(MAX_BATCH_WORKERS + 1))
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert f"--workers cannot exceed {MAX_BATCH_WORKERS}" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_cache_size_zero_exits_1(self, capsys):
        """Line 13666-13667: --cache-size < 1."""
        args = _make_args(cache_size=0)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--cache-size must be at least 1" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_cache_ttl_zero_exits_1(self, capsys):
        """Line 13668-13669: --cache-ttl < 1."""
        args = _make_args(cache_ttl=0)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--cache-ttl must be at least 1 second" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_max_issues_negative_exits_1(self, capsys):
        """Line 13670-13671: --max-issues < 0."""
        args = _make_args(max_issues=-1)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--max-issues cannot be negative" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_max_retries_negative_exits_1(self, capsys):
        """Line 13672-13673: --max-retries < 0."""
        args = _make_args(max_retries=-1)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--max-retries cannot be negative" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_retry_base_delay_negative_exits_1(self, capsys):
        """Line 13674-13675: --retry-base-delay < 0."""
        args = _make_args(retry_base_delay=-0.5)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--retry-base-delay cannot be negative" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_retry_max_delay_less_than_base_exits_1(self, capsys):
        """Line 13676-13677: --retry-max-delay < --retry-base-delay."""
        args = _make_args(retry_base_delay=10.0, retry_max_delay=5.0)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--retry-max-delay must be >= --retry-base-delay" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_org_sample_size_zero_exits_1(self, capsys):
        """Line 13678-13679: --sample < 1."""
        args = _make_args(org_report=True, org_sample_size=0)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--sample must be at least 1" in capsys.readouterr().err


# =========================================================================
# Block 2 — --interactive with args warning (lines 13913-13919)
# =========================================================================


class TestInteractiveMode:
    """Tests for --interactive mode argument handling."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.interactive_wizard")
    def test_interactive_with_data_views_prints_warning(self, mock_wizard, capsys):
        """Line 13913-13914: warning when --interactive given with data views."""
        mock_wizard.return_value = None  # User cancels wizard

        args = _make_args(interactive=True, data_views=["dv_123"])
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()

        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "--interactive mode ignores positional data view arguments" in out
        assert "Cancelled. Exiting." in out

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.interactive_wizard")
    def test_interactive_wizard_cancelled_exits_0(self, mock_wizard, capsys):
        """Line 13917-13919: wizard returns None → cancelled."""
        mock_wizard.return_value = None

        args = _make_args(interactive=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()

        assert exc_info.value.code == 0
        assert "Cancelled. Exiting." in capsys.readouterr().out

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.interactive_wizard")
    def test_interactive_no_data_views_no_warning(self, mock_wizard, capsys):
        """Line 13913: no warning when --interactive given without data views."""
        mock_wizard.return_value = None

        args = _make_args(interactive=True, data_views=[])
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()

        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "--interactive mode ignores positional data view arguments" not in out


class TestValidateConfigColorPolicy:
    """Tests for color-policy wiring in --validate-config path."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.validate_config_only")
    def test_validate_config_no_color_overrides_force_color_env(self, mock_validate, capsys):
        """--no-color should disable ANSI output even when FORCE_COLOR is set."""
        from cja_auto_sdr.core.colors import ConsoleColors

        def _emit_validate_output(*_args, **_kwargs):
            print(ConsoleColors.success("validate-config color check"))
            return True

        mock_validate.side_effect = _emit_validate_output
        args = _make_args(validate_config=True, no_color=True, output_dir="/tmp/reports")
        previous_enabled = ConsoleColors.is_enabled()
        try:
            with patch.dict("os.environ", {"FORCE_COLOR": "1"}, clear=False):
                with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
                    with pytest.raises(SystemExit) as exc_info:
                        _main_impl()
        finally:
            ConsoleColors.set_enabled(previous_enabled)

        assert exc_info.value.code == 0
        assert "\x1b[" not in capsys.readouterr().out
        mock_validate.assert_called_once_with("config.json", profile=None, output_dir="/tmp/reports")


# =========================================================================
# Block 3 — --include-all-inventory flags (lines 14095, 14100)
# =========================================================================


class TestIncludeAllInventory:
    """Tests for --include-all-inventory auto-expansion."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    def test_include_all_inventory_non_snapshot_enables_derived(self, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys):
        """Line 14094-14095: non-snapshot mode → include_derived_inventory = True."""
        result = ProcessingResult(
            data_view_id="dv_123",
            data_view_name="Test DV",
            success=True,
            duration=1.0,
            metrics_count=5,
            dimensions_count=3,
            output_file="/tmp/out.xlsx",
            file_size_bytes=1024,
        )
        mock_proc.return_value = result

        args = _make_args(
            data_views=["dv_123"],
            include_all_inventory=True,
            snapshot=None,
            git_commit=False,
            diff_snapshot=None,
            compare_snapshots=None,
            compare_with_prev=False,
        )
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        # After expansion args should have derived enabled
        assert args.include_derived_inventory is True
        assert args.include_segments_inventory is True
        assert args.include_calculated_metrics is True

        out = capsys.readouterr().out
        assert "--include-derived" in out

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    @patch("cja_auto_sdr.generator.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.generator.save_git_friendly_snapshot")
    @patch("cja_auto_sdr.generator.git_commit_snapshot", return_value=(True, "abc123"))
    def test_include_all_inventory_snapshot_mode_excludes_derived(
        self, _commit, _save, _is_git, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys
    ):
        """Line 14087-14095: snapshot-like mode → include_derived_inventory stays False."""
        result = ProcessingResult(
            data_view_id="dv_123",
            data_view_name="Test DV",
            success=True,
            duration=1.0,
            metrics_count=5,
            dimensions_count=3,
            output_file="/tmp/out.xlsx",
            file_size_bytes=1024,
        )
        mock_proc.return_value = result

        args = _make_args(
            data_views=["dv_123"],
            include_all_inventory=True,
            git_commit=True,
        )
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        assert args.include_derived_inventory is False
        out = capsys.readouterr().out
        assert "--include-derived" not in out

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    def test_include_all_inventory_quiet_suppresses_message(self, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys):
        """Line 14097: quiet mode suppresses the '--include-all-inventory enabled' message."""
        result = ProcessingResult(
            data_view_id="dv_123",
            data_view_name="Test DV",
            success=True,
            duration=1.0,
            metrics_count=5,
            dimensions_count=3,
            output_file="/tmp/out.xlsx",
            file_size_bytes=1024,
        )
        mock_proc.return_value = result

        args = _make_args(
            data_views=["dv_123"],
            include_all_inventory=True,
            quiet=True,
        )
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        out = capsys.readouterr().out
        assert "--include-all-inventory enabled" not in out


# =========================================================================
# Block 4 — --diff mode validation (lines 14328-14336)
# =========================================================================


class TestDiffModeValidation:
    """Tests for --diff argument validation."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_diff_wrong_arg_count_exits_1(self, capsys):
        """Line 14328-14331: --diff with != 2 data views."""
        args = _make_args(diff=True, data_views=["dv_1"])
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--diff requires exactly 2 data view IDs" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_diff_zero_args_exits_1(self, capsys):
        """Line 14328-14331: --diff with 0 data views."""
        args = _make_args(diff=True, data_views=[])
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--diff requires exactly 2" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_diff_three_args_exits_1(self, capsys):
        """Line 14328-14331: --diff with 3 data views."""
        args = _make_args(diff=True, data_views=["dv_1", "dv_2", "dv_3"])
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--diff requires exactly 2" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_diff_metrics_and_dimensions_only_conflict_exits_1(self, capsys):
        """Line 14334-14336: both --metrics-only and --dimensions-only."""
        args = _make_args(diff=True, data_views=["dv_1", "dv_2"], metrics_only=True, dimensions_only=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "Cannot use both --metrics-only and --dimensions-only" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_diff_include_derived_exits_1(self, capsys):
        """Line 14340-14353: --include-derived with --diff."""
        args = _make_args(diff=True, data_views=["dv_1", "dv_2"], include_derived_inventory=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--include-derived cannot be used with --diff" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_diff_include_calculated_exits_1(self, capsys):
        """Line 14354-14369: --include-calculated with --diff."""
        args = _make_args(diff=True, data_views=["dv_1", "dv_2"], include_calculated_metrics=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--include-calculated cannot be used with --diff" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_diff_include_segments_exits_1(self, capsys):
        """Line 14370-14385: --include-segments with --diff."""
        args = _make_args(diff=True, data_views=["dv_1", "dv_2"], include_segments_inventory=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--include-segments cannot be used with --diff" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_diff_inventory_only_exits_1(self, capsys):
        """Line 14386-14391: --inventory-only with --diff."""
        args = _make_args(diff=True, data_views=["dv_1", "dv_2"], inventory_only=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--inventory-only is only available in SDR mode" in capsys.readouterr().err


# =========================================================================
# Block 5 — Diff source/target name resolution ambiguity (lines 14410-14465)
# =========================================================================


class TestDiffNameResolutionAmbiguity:
    """Tests for ambiguous name resolution in --diff source/target."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_diff_source_not_resolved_exits_1(self, mock_resolve, capsys):
        """Line 14409-14411: source name resolves to nothing."""
        mock_resolve.return_value = ([], {})
        args = _make_args(diff=True, data_views=["MySource", "dv_target"])
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "Could not resolve source data view" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.prompt_for_selection", return_value=None)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_diff_source_ambiguous_cancelled_exits_1(self, mock_resolve, _mock_prompt, capsys):
        """Line 14412-14432: source ambiguous, user cancels selection."""
        mock_resolve.return_value = (["dv_1", "dv_2"], {})
        args = _make_args(diff=True, data_views=["AmbiguousName", "dv_target"])
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "is ambiguous" in err
        assert "dv_1" in err
        assert "dv_2" in err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.handle_diff_command", return_value=(True, False, None))
    @patch("cja_auto_sdr.generator.prompt_for_selection", return_value="dv_selected")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_diff_source_ambiguous_user_selects(self, mock_resolve, _mock_prompt, mock_diff, capsys):
        """Line 14419-14420: source ambiguous, user selects one → proceeds."""
        # First call is for source, second call is for target
        mock_resolve.side_effect = [
            (["dv_1", "dv_2"], {}),  # source: ambiguous
            (["dv_target"], {}),  # target: resolved
        ]
        args = _make_args(diff=True, data_views=["AmbiguousName", "dv_target"])
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        # Should succeed (diff returns True, no changes → exit 0)
        assert exc_info.value.code == 0
        mock_diff.assert_called_once()

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_diff_target_not_resolved_exits_1(self, mock_resolve, capsys):
        """Line 14442-14444: target name resolves to nothing."""
        mock_resolve.side_effect = [
            (["dv_source"], {}),  # source resolved OK
            ([], {}),  # target not resolved
        ]
        args = _make_args(diff=True, data_views=["dv_source", "MissingTarget"])
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "Could not resolve target data view" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.prompt_for_selection", return_value=None)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_diff_target_ambiguous_cancelled_exits_1(self, mock_resolve, _mock_prompt, capsys):
        """Line 14445-14465: target ambiguous, user cancels → exit 1."""
        mock_resolve.side_effect = [
            (["dv_source"], {}),  # source OK
            (["dv_t1", "dv_t2"], {}),  # target ambiguous
        ]
        args = _make_args(diff=True, data_views=["dv_source", "AmbiguousTarget"])
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "is ambiguous" in err
        assert "dv_t1" in err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.handle_diff_command", return_value=(True, True, None))
    @patch("cja_auto_sdr.generator.prompt_for_selection")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_diff_target_ambiguous_user_selects(self, mock_resolve, mock_prompt, mock_diff, capsys):
        """Line 14452-14453: target ambiguous, user selects → proceeds."""
        mock_resolve.side_effect = [
            (["dv_source"], {}),  # source OK
            (["dv_t1", "dv_t2"], {}),  # target ambiguous
        ]
        mock_prompt.return_value = "dv_t1"
        args = _make_args(diff=True, data_views=["dv_source", "AmbiguousTarget"])
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        # has_changes=True → exit 2
        assert exc_info.value.code == 2
        mock_diff.assert_called_once()


# =========================================================================
# Block 6 — --snapshot name resolution ambiguity (lines 14549-14571)
# =========================================================================


class TestSnapshotNameResolutionAmbiguity:
    """Tests for ambiguous name resolution in --snapshot mode."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=([], {}))
    def test_snapshot_name_not_resolved_exits_1(self, _resolve, capsys):
        """Line 14548-14550: snapshot data view name not found."""
        args = _make_args(snapshot="/tmp/snap.json", data_views=["MissingDV"])
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "Could not resolve data view" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.prompt_for_selection", return_value=None)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_1", "dv_2"], {}))
    def test_snapshot_ambiguous_cancelled_exits_1(self, _resolve, _prompt, capsys):
        """Line 14551-14571: ambiguous snapshot name, user cancels."""
        args = _make_args(snapshot="/tmp/snap.json", data_views=["AmbiguousName"])
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "is ambiguous" in err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.handle_snapshot_command", return_value=True)
    @patch("cja_auto_sdr.generator.prompt_for_selection", return_value="dv_1")
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_1", "dv_2"], {}))
    def test_snapshot_ambiguous_user_selects(self, _resolve, _prompt, mock_snap, capsys):
        """Line 14559-14560: ambiguous snapshot name, user selects one → proceeds."""
        args = _make_args(snapshot="/tmp/snap.json", data_views=["AmbiguousName"])
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 0
        mock_snap.assert_called_once()


# =========================================================================
# Block 7 — --compare-with-prev name resolution ambiguity (lines 14619-14641)
# =========================================================================


class TestCompareWithPrevNameResolutionAmbiguity:
    """Tests for ambiguous name resolution in --compare-with-prev mode."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=([], {}))
    def test_compare_with_prev_not_resolved_exits_1(self, _resolve, capsys):
        """Line 14618-14620: data view name not found for compare-with-prev."""
        args = _make_args(compare_with_prev=True, data_views=["MissingDV"])
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "Could not resolve data view" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.prompt_for_selection", return_value=None)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_1", "dv_2"], {}))
    def test_compare_with_prev_ambiguous_cancelled_exits_1(self, _resolve, _prompt, capsys):
        """Line 14621-14641: ambiguous name, user cancels."""
        args = _make_args(compare_with_prev=True, data_views=["AmbigName"])
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "is ambiguous" in err
        assert "dv_1" in err
        assert "dv_2" in err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.prompt_for_selection", return_value="dv_1")
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_1", "dv_2"], {}))
    def test_compare_with_prev_ambiguous_user_selects(self, _resolve, _prompt, mock_sm_cls, capsys):
        """Line 14629-14630: ambiguous name, user selects → proceeds to snapshot lookup."""
        mock_sm = MagicMock()
        mock_sm.get_most_recent_snapshot.return_value = None
        mock_sm_cls.return_value = mock_sm

        args = _make_args(compare_with_prev=True, data_views=["AmbigName"])
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        # No previous snapshot found → exit 1
        assert exc_info.value.code == 1
        assert "No previous snapshots found" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_compare_with_prev_wrong_arg_count_exits_1(self, capsys):
        """Line 14589-14595: --compare-with-prev with != 1 data view."""
        args = _make_args(compare_with_prev=True, data_views=["dv_1", "dv_2"])
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--compare-with-prev requires exactly 1" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_compare_with_prev_inventory_only_exits_1(self, capsys):
        """Line 14598-14605: --inventory-only with --compare-with-prev."""
        args = _make_args(compare_with_prev=True, data_views=["dv_1"], inventory_only=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--inventory-only is only available in SDR mode" in capsys.readouterr().err


# =========================================================================
# Block 8 — Data view name resolution display (lines 14808-14839)
# =========================================================================


class TestDataViewNameResolutionDisplay:
    """Tests for resolution progress display and failure messaging."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=([], {}))
    def test_no_valid_data_views_found_exits_1(self, _resolve, capsys):
        """Line 14823-14839: no data views resolved → error message."""
        args = _make_args(data_views=["NonExistentDV"])
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "No valid data views found" in err
        assert "Possible issues" in err
        assert "Try running: cja_auto_sdr --list-dataviews" in err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_name_resolution_display_shown_when_not_quiet(self, mock_resolve, capsys):
        """Line 14807-14809: resolution progress printed when names provided and not quiet."""
        mock_resolve.return_value = ([], {})  # Still fails, but we check the message
        args = _make_args(data_views=["My Analytics View"], quiet=False)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit):
                _main_impl()
        out = capsys.readouterr().out
        assert "Resolving 1 data view name(s)" in out

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_name_resolution_display_hidden_when_quiet(self, mock_resolve, capsys):
        """Line 14807: resolution progress NOT printed when quiet=True."""
        mock_resolve.return_value = ([], {})
        args = _make_args(data_views=["My Analytics View"], quiet=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit):
                _main_impl()
        out = capsys.readouterr().out
        assert "Resolving" not in out

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_resolution_summary_shown_for_names(self, mock_resolve, capsys):
        """Line 14842-14852: resolution summary shown when names resolved successfully."""
        mock_resolve.return_value = (
            ["dv_resolved_1"],
            {"My DV": ["dv_resolved_1"]},
        )
        args = _make_args(data_views=["My DV"], quiet=False)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            # Will proceed to SDR processing which needs more mocks
            with (
                patch("cja_auto_sdr.generator.process_single_dataview") as mock_proc,
                patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[]),
                patch("cja_auto_sdr.generator.append_github_step_summary"),
                patch("cja_auto_sdr.generator.build_quality_step_summary", return_value=""),
            ):
                result = ProcessingResult(
                    data_view_id="dv_resolved_1",
                    data_view_name="My DV",
                    success=True,
                    duration=1.0,
                    metrics_count=5,
                    dimensions_count=3,
                    output_file="/tmp/out.xlsx",
                    file_size_bytes=1024,
                )
                mock_proc.return_value = result
                try:
                    _main_impl()
                except SystemExit:
                    pass
        out = capsys.readouterr().out
        assert "Data view name resolution:" in out
        assert "'My DV'" in out
        assert "dv_resolved_1" in out


# =========================================================================
# Block 9 — Large batch confirmation (lines 14884-14904)
# =========================================================================


class TestLargeBatchConfirmation:
    """Tests for large batch confirmation prompt."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("sys.stdin")
    def test_large_batch_user_declines_exits_0(self, mock_stdin, mock_resolve, capsys):
        """Line 14896-14900: user says 'n' to large batch → exit 0."""
        dv_ids = [f"dv_{i:05d}" for i in range(25)]
        mock_resolve.return_value = (dv_ids, {})
        mock_stdin.isatty.return_value = True

        args = _make_args(data_views=dv_ids, quiet=False, assume_yes=False, dry_run=False)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with patch("builtins.input", return_value="n"):
                with pytest.raises(SystemExit) as exc_info:
                    _main_impl()
        assert exc_info.value.code == 0
        out = capsys.readouterr().out
        assert "Large batch detected" in out
        assert "Cancelled" in out

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("sys.stdin")
    def test_large_batch_user_accepts(self, mock_stdin, mock_resolve, capsys):
        """Line 14896-14901: user says 'y' → processing continues."""
        dv_ids = [f"dv_{i:05d}" for i in range(20)]
        mock_resolve.return_value = (dv_ids, {})
        mock_stdin.isatty.return_value = True

        args = _make_args(data_views=dv_ids, quiet=False, assume_yes=False, dry_run=False, batch=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with patch("builtins.input", return_value="y"):
                with patch("cja_auto_sdr.generator.BatchProcessor") as mock_bp:
                    mock_bp.return_value.process_batch.return_value = {"successful": [], "failed": []}
                    with patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[]):
                        with patch("cja_auto_sdr.generator.append_github_step_summary"):
                            with patch("cja_auto_sdr.generator.build_quality_step_summary", return_value=""):
                                # Should not exit due to cancellation
                                try:
                                    _main_impl()
                                except SystemExit:
                                    pass  # May exit for other reasons
        out = capsys.readouterr().out
        assert "Large batch detected" in out

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("sys.stdin")
    def test_large_batch_eof_exits_0(self, mock_stdin, mock_resolve, capsys):
        """Line 14902-14904: EOFError on input → exit 0."""
        dv_ids = [f"dv_{i:05d}" for i in range(25)]
        mock_resolve.return_value = (dv_ids, {})
        mock_stdin.isatty.return_value = True

        args = _make_args(data_views=dv_ids, quiet=False, assume_yes=False, dry_run=False)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with patch("builtins.input", side_effect=EOFError):
                with pytest.raises(SystemExit) as exc_info:
                    _main_impl()
        assert exc_info.value.code == 0

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("sys.stdin")
    def test_large_batch_keyboard_interrupt_exits_0(self, mock_stdin, mock_resolve, capsys):
        """Line 14902-14904: KeyboardInterrupt on input → exit 0."""
        dv_ids = [f"dv_{i:05d}" for i in range(25)]
        mock_resolve.return_value = (dv_ids, {})
        mock_stdin.isatty.return_value = True

        args = _make_args(data_views=dv_ids, quiet=False, assume_yes=False, dry_run=False)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with patch("builtins.input", side_effect=KeyboardInterrupt):
                with pytest.raises(SystemExit) as exc_info:
                    _main_impl()
        assert exc_info.value.code == 0

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("sys.stdin")
    def test_large_batch_empty_input_cancels(self, mock_stdin, mock_resolve, capsys):
        """Line 14898-14900: empty response defaults to 'no' → cancelled."""
        dv_ids = [f"dv_{i:05d}" for i in range(25)]
        mock_resolve.return_value = (dv_ids, {})
        mock_stdin.isatty.return_value = True

        args = _make_args(data_views=dv_ids, quiet=False, assume_yes=False, dry_run=False)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with patch("builtins.input", return_value=""):
                with pytest.raises(SystemExit) as exc_info:
                    _main_impl()
        assert exc_info.value.code == 0
        assert "Cancelled" in capsys.readouterr().out

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_large_batch_skipped_when_assume_yes(self, mock_resolve, capsys):
        """Line 14879: --assume-yes bypasses the large batch prompt."""
        dv_ids = [f"dv_{i:05d}" for i in range(25)]
        mock_resolve.return_value = (dv_ids, {})

        args = _make_args(data_views=dv_ids, assume_yes=True, batch=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with patch("cja_auto_sdr.generator.BatchProcessor") as mock_bp:
                mock_bp.return_value.process_batch.return_value = {"successful": [], "failed": []}
                with patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[]):
                    with patch("cja_auto_sdr.generator.append_github_step_summary"):
                        with patch("cja_auto_sdr.generator.build_quality_step_summary", return_value=""):
                            try:
                                _main_impl()
                            except SystemExit:
                                pass
        out = capsys.readouterr().out
        assert "Large batch detected" not in out

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_large_batch_skipped_when_quiet(self, mock_resolve, capsys):
        """Line 14880: --quiet bypasses the large batch prompt."""
        dv_ids = [f"dv_{i:05d}" for i in range(25)]
        mock_resolve.return_value = (dv_ids, {})

        args = _make_args(data_views=dv_ids, quiet=True, batch=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with patch("cja_auto_sdr.generator.BatchProcessor") as mock_bp:
                mock_bp.return_value.process_batch.return_value = {"successful": [], "failed": []}
                with patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[]):
                    with patch("cja_auto_sdr.generator.append_github_step_summary"):
                        with patch("cja_auto_sdr.generator.build_quality_step_summary", return_value=""):
                            try:
                                _main_impl()
                            except SystemExit:
                                pass
        out = capsys.readouterr().out
        assert "Large batch detected" not in out


# =========================================================================
# Block 10 — Production mode log level (line 14915)
# =========================================================================


class TestProductionModeLogLevel:
    """Tests for production mode log level override."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    def test_production_mode_sets_warning_log_level(self, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys):
        """Line 14914-14915: --production sets effective log level to WARNING."""
        result = ProcessingResult(
            data_view_id="dv_123",
            data_view_name="Test DV",
            success=True,
            duration=1.0,
            metrics_count=5,
            dimensions_count=3,
            output_file="/tmp/out.xlsx",
            file_size_bytes=1024,
        )
        mock_proc.return_value = result

        args = _make_args(data_views=["dv_123"], production=True, quiet=False)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        # Verify process_single_dataview was called with WARNING log level
        call_kwargs = mock_proc.call_args
        assert call_kwargs[1]["log_level"] == "WARNING" or call_kwargs.kwargs.get("log_level") == "WARNING"


# =========================================================================
# Block 11 — Inventory summary display in single mode (lines 15329-15358)
# =========================================================================


class TestInventorySummaryDisplay:
    """Tests for inventory summary display in single SDR mode."""

    def _make_result_with_inventory(self, **overrides):
        """Create a successful ProcessingResult with inventory data."""
        defaults = {
            "data_view_id": "dv_123",
            "data_view_name": "Test DV",
            "success": True,
            "duration": 1.0,
            "metrics_count": 10,
            "dimensions_count": 5,
            "output_file": "/tmp/out.xlsx",
            "file_size_bytes": 2048,
            "segments_count": 8,
            "segments_high_complexity": 2,
            "calculated_metrics_count": 12,
            "calculated_metrics_high_complexity": 3,
            "derived_fields_count": 4,
            "derived_fields_high_complexity": 1,
        }
        defaults.update(overrides)
        return ProcessingResult(**defaults)

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    def test_inventory_segments_displayed(self, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys):
        """Line 15333-15337: segment inventory shown with high-complexity count."""
        mock_proc.return_value = self._make_result_with_inventory()

        args = _make_args(data_views=["dv_123"], include_segments_inventory=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        out = capsys.readouterr().out
        assert "Segments: 8" in out
        assert "2 high-complexity" in out

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    def test_inventory_calculated_metrics_displayed(self, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys):
        """Line 15338-15342: calculated metrics inventory shown."""
        mock_proc.return_value = self._make_result_with_inventory()

        args = _make_args(data_views=["dv_123"], include_calculated_metrics=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        out = capsys.readouterr().out
        assert "Calculated Metrics: 12" in out
        assert "3 high-complexity" in out

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    def test_inventory_derived_fields_displayed(self, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys):
        """Line 15343-15347: derived fields inventory shown."""
        mock_proc.return_value = self._make_result_with_inventory()

        args = _make_args(data_views=["dv_123"], include_derived_inventory=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        out = capsys.readouterr().out
        assert "Derived Fields: 4" in out
        assert "1 high-complexity" in out

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    def test_inventory_high_complexity_warning(self, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys):
        """Line 15352-15358: total high-complexity warning shown."""
        mock_proc.return_value = self._make_result_with_inventory()

        args = _make_args(
            data_views=["dv_123"],
            include_segments_inventory=True,
            include_calculated_metrics=True,
            include_derived_inventory=True,
        )
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        out = capsys.readouterr().out
        # total_high_complexity = 2+3+1 = 6
        assert "6 high-complexity items" in out
        assert "review recommended" in out

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    def test_inventory_no_high_complexity_no_warning(self, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys):
        """Line 15352-15358: no warning when no high-complexity items."""
        mock_proc.return_value = self._make_result_with_inventory(
            segments_high_complexity=0,
            calculated_metrics_high_complexity=0,
            derived_fields_high_complexity=0,
        )

        args = _make_args(data_views=["dv_123"], include_segments_inventory=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        out = capsys.readouterr().out
        assert "high-complexity items" not in out

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    def test_inventory_all_three_types_displayed(self, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys):
        """Lines 15329-15350: all three inventory types displayed in single line."""
        mock_proc.return_value = self._make_result_with_inventory()

        args = _make_args(
            data_views=["dv_123"],
            include_segments_inventory=True,
            include_calculated_metrics=True,
            include_derived_inventory=True,
        )
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        out = capsys.readouterr().out
        assert "Inventory:" in out
        assert "Segments: 8" in out
        assert "Calculated Metrics: 12" in out
        assert "Derived Fields: 4" in out


# =========================================================================
# Block 12 — Git commit integration (lines 15362-15442)
# =========================================================================


class TestGitCommitIntegration:
    """Tests for --git-commit workflow in single SDR mode."""

    def _make_success_result(self, **overrides):
        defaults = {
            "data_view_id": "dv_123",
            "data_view_name": "Test DV",
            "success": True,
            "duration": 1.0,
            "metrics_count": 10,
            "dimensions_count": 5,
            "output_file": "/tmp/out.xlsx",
            "file_size_bytes": 2048,
            "dq_issues_count": 0,
        }
        defaults.update(overrides)
        return ProcessingResult(**defaults)

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    @patch("cja_auto_sdr.generator.is_git_repository", return_value=False)
    @patch("cja_auto_sdr.generator.git_init_snapshot_repo", return_value=(True, "Initialized"))
    @patch("cja_auto_sdr.generator.save_git_friendly_snapshot")
    @patch("cja_auto_sdr.generator.git_commit_snapshot", return_value=(True, "abc1234"))
    def test_git_commit_init_and_commit_success(
        self, mock_commit, mock_save, mock_init, mock_is_git, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys
    ):
        """Line 15362-15438: full git-commit workflow — init + save + commit."""
        mock_proc.return_value = self._make_success_result()

        args = _make_args(data_views=["dv_123"], git_commit=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        out = capsys.readouterr().out
        assert "Initializing Git repository" in out
        assert "Repository initialized" in out
        assert "Committed: abc1234" in out
        mock_save.assert_called_once()
        mock_commit.assert_called_once()

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    @patch("cja_auto_sdr.generator.is_git_repository", return_value=False)
    @patch("cja_auto_sdr.generator.git_init_snapshot_repo", return_value=(False, "Permission denied"))
    @patch("cja_auto_sdr.generator.save_git_friendly_snapshot")
    @patch("cja_auto_sdr.generator.git_commit_snapshot", return_value=(True, "abc1234"))
    def test_git_commit_init_failure(
        self, _commit, _save, _init, _is_git, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys
    ):
        """Line 15369-15370: git init fails → error message printed."""
        mock_proc.return_value = self._make_success_result()

        args = _make_args(data_views=["dv_123"], git_commit=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        out = capsys.readouterr().out
        assert "Git init failed" in out

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    @patch("cja_auto_sdr.generator.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.generator.save_git_friendly_snapshot")
    @patch("cja_auto_sdr.generator.git_commit_snapshot", return_value=(True, "no_changes"))
    def test_git_commit_no_changes(self, _commit, _save, _is_git, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys):
        """Line 15435-15436: commit with no_changes result."""
        mock_proc.return_value = self._make_success_result()

        args = _make_args(data_views=["dv_123"], git_commit=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        out = capsys.readouterr().out
        assert "No changes to commit" in out

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    @patch("cja_auto_sdr.generator.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.generator.save_git_friendly_snapshot")
    @patch("cja_auto_sdr.generator.git_commit_snapshot", return_value=(False, "merge conflict"))
    def test_git_commit_failure(self, _commit, _save, _is_git, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys):
        """Line 15441-15442: commit fails → error printed."""
        mock_proc.return_value = self._make_success_result()

        args = _make_args(data_views=["dv_123"], git_commit=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        out = capsys.readouterr().out
        assert "Git commit failed" in out

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    @patch("cja_auto_sdr.generator.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.generator.save_git_friendly_snapshot")
    @patch("cja_auto_sdr.generator.git_commit_snapshot", return_value=(True, "def5678"))
    def test_git_commit_with_push(self, mock_commit, _save, _is_git, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys):
        """Line 15439-15440: --git-push flag results in 'Pushed to remote' message."""
        mock_proc.return_value = self._make_success_result()

        args = _make_args(data_views=["dv_123"], git_commit=True, git_push=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        out = capsys.readouterr().out
        assert "Committed: def5678" in out
        assert "Pushed to remote" in out
        # Verify push=True was passed
        assert mock_commit.call_args[1].get("push") is True or mock_commit.call_args.kwargs.get("push") is True

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    @patch("cja_auto_sdr.generator.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.generator.initialize_cja", return_value=MagicMock())
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.save_git_friendly_snapshot")
    @patch("cja_auto_sdr.generator.git_commit_snapshot", return_value=(True, "abc123"))
    def test_git_commit_fetches_inventory_when_needed(
        self, _commit, _save, mock_sm_cls, mock_init_cja, _is_git, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys
    ):
        """Line 15388-15407: needs_inventory triggers re-fetch."""
        mock_proc.return_value = self._make_success_result()
        mock_sm = MagicMock()
        mock_sm_cls.return_value = mock_sm

        args = _make_args(
            data_views=["dv_123"],
            git_commit=True,
            include_calculated_metrics=True,
        )
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        out = capsys.readouterr().out
        assert "Fetching inventory for Git snapshot" in out or "Fetching data for Git snapshot" in out

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    @patch("cja_auto_sdr.generator.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.generator.initialize_cja", side_effect=OSError("API Error"))
    @patch("cja_auto_sdr.generator.save_git_friendly_snapshot")
    @patch("cja_auto_sdr.generator.git_commit_snapshot", return_value=(True, "abc123"))
    def test_git_commit_fetch_failure_continues(
        self, _commit, _save, _init_cja, _is_git, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys
    ):
        """Line 15408-15409: snapshot fetch fails → warning, commit still attempted."""
        mock_proc.return_value = self._make_success_result()

        args = _make_args(
            data_views=["dv_123"],
            git_commit=True,
            include_segments_inventory=True,
        )
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        out = capsys.readouterr().out
        assert "Could not fetch snapshot data" in out

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    @patch("cja_auto_sdr.generator.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.generator.initialize_cja", return_value=MagicMock())
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.save_git_friendly_snapshot")
    @patch("cja_auto_sdr.generator.git_commit_snapshot", return_value=(True, "abc123"))
    def test_git_commit_refetch_value_error_continues(
        self, mock_commit, mock_save, mock_sm_cls, _init_cja, _is_git, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys
    ):
        """ValueError during snapshot re-fetch should warn and continue commit flow."""
        mock_proc.return_value = self._make_success_result()
        mock_sm = MagicMock()
        mock_sm.create_snapshot.side_effect = ValueError("data view not found")
        mock_sm_cls.return_value = mock_sm

        args = _make_args(
            data_views=["dv_123"],
            git_commit=True,
            include_segments_inventory=True,
        )
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        out = capsys.readouterr().out
        assert "Could not fetch snapshot data" in out
        mock_save.assert_called_once()
        mock_commit.assert_called_once()

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    @patch("cja_auto_sdr.generator.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.generator.initialize_cja", return_value=MagicMock())
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.save_git_friendly_snapshot")
    @patch("cja_auto_sdr.generator.git_commit_snapshot", return_value=(True, "abc123"))
    def test_git_commit_refetch_api_error_continues(
        self, mock_commit, mock_save, mock_sm_cls, _init_cja, _is_git, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys
    ):
        """APIError during snapshot re-fetch should warn and continue commit flow."""
        mock_proc.return_value = self._make_success_result()
        mock_sm = MagicMock()
        mock_sm.create_snapshot.side_effect = APIError("transient api failure")
        mock_sm_cls.return_value = mock_sm

        args = _make_args(
            data_views=["dv_123"],
            git_commit=True,
            include_segments_inventory=True,
        )
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        out = capsys.readouterr().out
        assert "Could not fetch snapshot data" in out
        mock_save.assert_called_once()
        mock_commit.assert_called_once()

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    @patch("cja_auto_sdr.generator.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.generator.initialize_cja", return_value=MagicMock())
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.save_git_friendly_snapshot")
    @patch("cja_auto_sdr.generator.git_commit_snapshot", return_value=(True, "abc123"))
    def test_git_commit_refetch_runtime_error_continues(
        self, mock_commit, mock_save, mock_sm_cls, _init_cja, _is_git, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys
    ):
        """RuntimeError during snapshot re-fetch should warn and continue commit flow."""
        mock_proc.return_value = self._make_success_result()
        mock_sm = MagicMock()
        mock_sm.create_snapshot.side_effect = RuntimeError("unexpected internal error")
        mock_sm_cls.return_value = mock_sm

        args = _make_args(
            data_views=["dv_123"],
            git_commit=True,
            include_segments_inventory=True,
        )
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        out = capsys.readouterr().out
        assert "Could not fetch snapshot data" in out
        mock_save.assert_called_once()
        mock_commit.assert_called_once()

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    @patch("cja_auto_sdr.generator.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.generator.initialize_cja", return_value=MagicMock())
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.save_git_friendly_snapshot")
    @patch("cja_auto_sdr.generator.git_commit_snapshot", return_value=(True, "abc123"))
    def test_git_commit_refetch_type_error_continues_with_fallback_snapshot(
        self, mock_commit, mock_save, mock_sm_cls, _init_cja, _is_git, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys
    ):
        """TypeError during re-fetch should preserve fallback snapshot and continue."""
        result = self._make_success_result()
        result.metrics_data = [{"id": "m1"}]
        result.dimensions_data = [{"id": "d1"}]
        mock_proc.return_value = result

        mock_sm = MagicMock()
        mock_sm.create_snapshot.side_effect = TypeError("metrics payload missing empty")
        mock_sm_cls.return_value = mock_sm

        args = _make_args(
            data_views=["dv_123"],
            git_commit=True,
            include_segments_inventory=True,
        )
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        out = capsys.readouterr().out
        assert "Could not fetch snapshot data" in out
        mock_save.assert_called_once()
        saved_snapshot = mock_save.call_args.kwargs["snapshot"]
        assert saved_snapshot.metrics == result.metrics_data
        assert saved_snapshot.dimensions == result.dimensions_data
        mock_commit.assert_called_once()

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    @patch("cja_auto_sdr.generator.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.generator.initialize_cja", return_value=MagicMock())
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.save_git_friendly_snapshot")
    @patch("cja_auto_sdr.generator.git_commit_snapshot", return_value=(True, "abc123"))
    def test_git_commit_refetch_attribute_error_continues_with_fallback_snapshot(
        self, mock_commit, mock_save, mock_sm_cls, _init_cja, _is_git, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys
    ):
        """AttributeError during re-fetch should preserve fallback snapshot and continue."""
        result = self._make_success_result()
        result.metrics_data = [{"id": "m1"}]
        result.dimensions_data = [{"id": "d1"}]
        mock_proc.return_value = result

        mock_sm = MagicMock()
        mock_sm.create_snapshot.side_effect = AttributeError("metrics payload missing empty")
        mock_sm_cls.return_value = mock_sm

        args = _make_args(
            data_views=["dv_123"],
            git_commit=True,
            include_segments_inventory=True,
        )
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        out = capsys.readouterr().out
        assert "Could not fetch snapshot data" in out
        mock_save.assert_called_once()
        saved_snapshot = mock_save.call_args.kwargs["snapshot"]
        assert saved_snapshot.metrics == result.metrics_data
        assert saved_snapshot.dimensions == result.dimensions_data
        mock_commit.assert_called_once()


# =========================================================================
# Block 13 — Open file in batch mode (lines 15250-15262)
# =========================================================================


class TestOpenFileInBatchMode:
    """Tests for --open flag in batch mode."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.BatchProcessor")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    @patch("cja_auto_sdr.generator.open_file_in_default_app", return_value=True)
    def test_open_flag_batch_mode_opens_successful_files(
        self, mock_open, _bqs, _aghs, _aqi, mock_bp_cls, mock_resolve, capsys
    ):
        """Line 15249-15262: --open in batch mode opens all successful output files."""
        dv_ids = ["dv_1", "dv_2"]
        mock_resolve.return_value = (dv_ids, {})

        successful = [
            {"output_file": "/tmp/out1.xlsx", "data_view_id": "dv_1"},
            {"output_file": "/tmp/out2.xlsx", "data_view_id": "dv_2"},
        ]
        mock_bp_cls.return_value.process_batch.return_value = {
            "successful": successful,
            "failed": [],
        }

        args = _make_args(data_views=dv_ids, open=True, batch=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        out = capsys.readouterr().out
        assert "Opening 2 file(s)" in out
        assert mock_open.call_count == 2

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.BatchProcessor")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    @patch("cja_auto_sdr.generator.open_file_in_default_app", return_value=False)
    def test_open_flag_batch_mode_warns_on_failure(
        self, mock_open, _bqs, _aghs, _aqi, mock_bp_cls, mock_resolve, capsys
    ):
        """Line 15262: warns when file cannot be opened."""
        dv_ids = ["dv_1"]
        mock_resolve.return_value = (dv_ids, {})

        successful = [{"output_file": "/tmp/broken.xlsx"}]
        mock_bp_cls.return_value.process_batch.return_value = {
            "successful": successful,
            "failed": [],
        }

        args = _make_args(data_views=dv_ids, open=True, batch=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        out = capsys.readouterr().out
        assert "Could not open" in out

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.BatchProcessor")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    @patch("cja_auto_sdr.generator.open_file_in_default_app")
    def test_open_flag_batch_mode_no_successful_results(
        self, mock_open, _bqs, _aghs, _aqi, mock_bp_cls, mock_resolve, capsys
    ):
        """Line 15249: --open with no successful results → nothing opened."""
        dv_ids = ["dv_1"]
        mock_resolve.return_value = (dv_ids, {})

        mock_bp_cls.return_value.process_batch.return_value = {
            "successful": [],
            "failed": [{"error_message": "failed"}],
        }

        args = _make_args(data_views=dv_ids, open=True, batch=True, continue_on_error=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        mock_open.assert_not_called()

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    @patch("cja_auto_sdr.generator.open_file_in_default_app", return_value=True)
    def test_open_flag_single_mode(self, mock_open, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys):
        """Line 15445-15449: --open in single mode opens the output file."""
        result = ProcessingResult(
            data_view_id="dv_123",
            data_view_name="Test DV",
            success=True,
            duration=1.0,
            metrics_count=5,
            dimensions_count=3,
            output_file="/tmp/out.xlsx",
            file_size_bytes=1024,
        )
        mock_proc.return_value = result

        args = _make_args(data_views=["dv_123"], open=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        out = capsys.readouterr().out
        assert "Opening file" in out
        mock_open.assert_called_once_with("/tmp/out.xlsx")

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    @patch("cja_auto_sdr.generator.open_file_in_default_app", return_value=False)
    def test_open_flag_single_mode_failure_warns(self, mock_open, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys):
        """Line 15448-15449: --open in single mode warns on failure."""
        result = ProcessingResult(
            data_view_id="dv_123",
            data_view_name="Test DV",
            success=True,
            duration=1.0,
            metrics_count=5,
            dimensions_count=3,
            output_file="/tmp/out.xlsx",
            file_size_bytes=1024,
        )
        mock_proc.return_value = result

        args = _make_args(data_views=["dv_123"], open=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            try:
                _main_impl()
            except SystemExit:
                pass

        out = capsys.readouterr().out
        assert "Could not open" in out


# =========================================================================
# Additional edge cases
# =========================================================================


class TestAdditionalValidation:
    """Additional _main_impl validation paths."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_auto_prune_without_auto_snapshot_exits_1(self, capsys):
        """Line 13690-13695: --auto-prune without --auto-snapshot or --prune-snapshots."""
        args = _make_args(auto_prune=True, auto_snapshot=False, prune_snapshots=False)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--auto-prune requires --auto-snapshot or --prune-snapshots" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_fail_on_quality_non_sdr_mode_exits_1(self, capsys):
        """Line 13687-13688: --fail-on-quality in non-SDR mode."""
        args = _make_args(fail_on_quality="WARNING", diff=True, data_views=["dv_1", "dv_2"])
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--fail-on-quality is only supported in SDR generation mode" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_fail_on_quality_with_skip_validation_exits_1(self, capsys):
        """Line 13696-13697: --fail-on-quality + --skip-validation conflict."""
        args = _make_args(fail_on_quality="WARNING", skip_validation=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--fail-on-quality cannot be used with --skip-validation" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_quality_report_with_skip_validation_exits_1(self, capsys):
        """Line 13698-13699: --quality-report + --skip-validation conflict."""
        args = _make_args(quality_report="json", skip_validation=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--quality-report cannot be used with --skip-validation" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_quality_report_in_non_sdr_mode_exits_1(self, capsys):
        """Line 13700-13701: --quality-report in non-SDR mode."""
        args = _make_args(quality_report="json", diff=True, data_views=["dv_1", "dv_2"])
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--quality-report is only supported in SDR generation mode" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_list_snapshots_and_prune_snapshots_conflict(self, capsys):
        """Line 13703-13704: --list-snapshots + --prune-snapshots conflict."""
        args = _make_args(list_snapshots=True, prune_snapshots=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "Use either --list-snapshots or --prune-snapshots" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_profile_overwrite_without_profile_import_exits_1(self, capsys):
        """Line 13705-13706: --profile-overwrite without --profile-import."""
        args = _make_args(profile_overwrite=True, profile_import=None)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--profile-overwrite requires --profile-import" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_git_push_without_git_commit_exits_1(self, capsys):
        """Line 13850-13852: --git-push without --git-commit."""
        args = _make_args(git_push=True, git_commit=False)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--git-push requires --git-commit" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_git_commit_with_include_derived_exits_1(self, capsys):
        """Line 13856-13860: --git-commit + --include-derived conflict."""
        args = _make_args(git_commit=True, include_derived_inventory=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "--include-derived cannot be used with --git-commit" in err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    def test_console_format_for_sdr_exits_1(self, _bqs, _aghs, _aqi, _proc, _resolve, capsys):
        """Line 14938-14952: console format is only valid for diff."""
        args = _make_args(data_views=["dv_123"], format="console")
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        err = capsys.readouterr().err
        assert "Console format is only supported for diff comparison" in err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    def test_sdr_metrics_and_dimensions_only_conflict(self, _bqs, _aghs, _aqi, _proc, _resolve, capsys):
        """Line 14955-14957: --metrics-only + --dimensions-only conflict in SDR mode."""
        args = _make_args(data_views=["dv_123"], metrics_only=True, dimensions_only=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "Cannot use both --metrics-only and --dimensions-only" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_snapshot_requires_one_data_view(self, capsys):
        """Line 14524-14527: --snapshot with != 1 data view."""
        args = _make_args(snapshot="/tmp/snap.json", data_views=["dv_1", "dv_2"])
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--snapshot requires exactly 1" in capsys.readouterr().err

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    def test_snapshot_with_include_derived_exits_1(self, capsys):
        """Line 14531-14535: --snapshot + --include-derived conflict."""
        args = _make_args(snapshot="/tmp/snap.json", data_views=["dv_1"], include_derived_inventory=True)
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        assert "--include-derived cannot be used with --snapshot" in capsys.readouterr().err


class TestSingleModeFailure:
    """Tests for single mode processing failure."""

    @patch("cja_auto_sdr.generator._cli_option_specified", _mock_cli_option_specified)
    @patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_123"], {}))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.aggregate_quality_issues", return_value=[])
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary", return_value="")
    def test_single_mode_failure_exits_1(self, _bqs, _aghs, _aqi, mock_proc, _resolve, capsys):
        """Line 15450-15453: failed single result → error + exit 1."""
        result = ProcessingResult(
            data_view_id="dv_123",
            data_view_name="Test DV",
            success=False,
            duration=1.0,
            error_message="API connection failed",
        )
        mock_proc.return_value = result

        args = _make_args(data_views=["dv_123"])
        with patch("cja_auto_sdr.generator.parse_arguments", return_value=args):
            with pytest.raises(SystemExit) as exc_info:
                _main_impl()
        assert exc_info.value.code == 1
        out = capsys.readouterr().out
        assert "FAILED" in out
        assert "API connection failed" in out
