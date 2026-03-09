"""Tests for command-line interface"""

import argparse
import json
import os
import subprocess
import sys
import tempfile
import textwrap
from unittest.mock import MagicMock, Mock, patch

import pytest

# Import the function we're testing
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cja_auto_sdr.core.exceptions import APIError
from cja_auto_sdr.generator import (
    _emit_output,
    _extract_dataset_info,
    describe_dataview,
    generate_sample_config,
    list_calculated_metrics,
    list_connections,
    list_datasets,
    list_dataviews,
    list_dimensions,
    list_metrics,
    list_segments,
    parse_arguments,
)


class TestCLIArguments:
    """Test command-line argument parsing"""

    def test_parse_single_data_view(self):
        """Test parsing a single data view ID"""
        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.data_views == ["dv_12345"]
            assert args.batch is False
            assert args.workers == "auto"  # Default is now 'auto' for automatic detection

    def test_parse_multiple_data_views(self):
        """Test parsing multiple data view IDs"""
        test_args = ["cja_sdr_generator.py", "dv_12345", "dv_67890", "dv_abcde"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.data_views == ["dv_12345", "dv_67890", "dv_abcde"]
            assert len(args.data_views) == 3

    def test_parse_batch_flag(self):
        """Test parsing with --batch flag"""
        test_args = ["cja_sdr_generator.py", "--batch", "dv_12345", "dv_67890"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.batch is True
            assert args.data_views == ["dv_12345", "dv_67890"]

    def test_parse_custom_workers(self):
        """Test parsing with custom worker count"""
        test_args = ["cja_sdr_generator.py", "--workers", "8", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.workers == "8"  # Now a string, parsed to int in main()

    def test_name_match_default_exact(self):
        """Test --name-match defaults to exact."""
        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.name_match == "exact"

    def test_name_match_flag(self):
        """Test --name-match parses accepted values."""
        test_args = ["cja_sdr_generator.py", "--name-match", "fuzzy", "Production Analytics"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.name_match == "fuzzy"

    def test_parse_output_dir(self):
        """Test parsing with custom output directory"""
        test_args = ["cja_sdr_generator.py", "--output-dir", "./reports", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.output_dir == "./reports"

    def test_parse_continue_on_error(self):
        """Test parsing with --continue-on-error flag"""
        test_args = ["cja_sdr_generator.py", "--continue-on-error", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.continue_on_error is True

    def test_parse_log_level(self):
        """Test parsing with custom log level"""
        test_args = ["cja_sdr_generator.py", "--log-level", "DEBUG", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.log_level == "DEBUG"

    def test_parse_missing_data_view(self):
        """Test that missing data view ID returns empty list (validated in main)"""
        test_args = ["cja_sdr_generator.py"]
        with patch.object(sys, "argv", test_args):
            # With nargs='*', empty data_views is allowed at parse time
            # Validation is done in main() to support --version flag
            args = parse_arguments()
            assert args.data_views == []

    def test_parse_config_file(self):
        """Test parsing with custom config file"""
        test_args = ["cja_sdr_generator.py", "--config-file", "custom_config.json", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.config_file == "custom_config.json"

    def test_default_values(self):
        """Test that default values are set correctly"""
        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.workers == "auto"  # Default is now 'auto' for automatic detection
            assert args.output_dir == "."
            assert args.config_file == "config.json"
            assert args.continue_on_error is False
            assert args.log_level == "INFO"
            assert args.production is False

    def test_production_flag(self):
        """Test parsing with --production flag"""
        test_args = ["cja_sdr_generator.py", "--production", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.production is True

    def test_production_with_log_level(self):
        """Test that production and log-level can be specified together"""
        test_args = ["cja_sdr_generator.py", "--production", "--log-level", "DEBUG", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.production is True
            assert args.log_level == "DEBUG"  # Both parsed, main() decides priority

    def test_dry_run_flag(self):
        """Test parsing with --dry-run flag"""
        test_args = ["cja_sdr_generator.py", "--dry-run", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.dry_run is True

    def test_dry_run_default_false(self):
        """Test that dry-run is False by default"""
        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.dry_run is False

    def test_dry_run_with_multiple_data_views(self):
        """Test dry-run with multiple data views"""
        test_args = ["cja_sdr_generator.py", "--dry-run", "dv_12345", "dv_67890"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.dry_run is True
            assert args.data_views == ["dv_12345", "dv_67890"]

    def test_quiet_flag(self):
        """Test parsing with --quiet flag"""
        test_args = ["cja_sdr_generator.py", "--quiet", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.quiet is True

    def test_quiet_short_flag(self):
        """Test parsing with -q short flag"""
        test_args = ["cja_sdr_generator.py", "-q", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.quiet is True

    def test_quiet_default_false(self):
        """Test that quiet is False by default"""
        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.quiet is False

    def test_version_flag_exits(self):
        """Test that --version flag causes SystemExit"""
        test_args = ["cja_sdr_generator.py", "--version"]
        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                parse_arguments()
            assert exc_info.value.code == 0  # Clean exit

    def test_list_dataviews_flag(self):
        """Test parsing with --list-dataviews flag"""
        test_args = ["cja_sdr_generator.py", "--list-dataviews"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.list_dataviews is True

    def test_list_dataviews_default_false(self):
        """Test that list-dataviews is False by default"""
        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.list_dataviews is False

    def test_skip_validation_flag(self):
        """Test parsing with --skip-validation flag"""
        test_args = ["cja_sdr_generator.py", "--skip-validation", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.skip_validation is True

    def test_skip_validation_default_false(self):
        """Test that skip-validation is False by default"""
        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.skip_validation is False

    def test_skip_validation_with_batch(self):
        """Test skip-validation with batch mode"""
        test_args = ["cja_sdr_generator.py", "--batch", "--skip-validation", "dv_12345", "dv_67890"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.skip_validation is True
            assert args.batch is True
            assert args.data_views == ["dv_12345", "dv_67890"]

    def test_sample_config_flag(self):
        """Test parsing with --sample-config flag"""
        test_args = ["cja_sdr_generator.py", "--sample-config"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.sample_config is True

    def test_sample_config_default_false(self):
        """Test that sample-config is False by default"""
        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.sample_config is False


class TestSampleConfig:
    """Test sample configuration file generation"""

    def test_generate_sample_config_creates_file(self):
        """Test that generate_sample_config creates a file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_config.json")
            result = generate_sample_config(output_path)
            assert result is True
            assert os.path.exists(output_path)

    def test_generate_sample_config_valid_json(self):
        """Test that generated config is valid JSON"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_config.json")
            generate_sample_config(output_path)
            with open(output_path) as f:
                config = json.load(f)
            assert "org_id" in config
            assert "client_id" in config
            assert "secret" in config

    def test_generate_sample_config_has_oauth_fields(self):
        """Test that generated config has OAuth S2S fields"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, "test_config.json")
            generate_sample_config(output_path)
            with open(output_path) as f:
                config = json.load(f)
            # OAuth S2S fields
            assert "org_id" in config
            assert "client_id" in config
            assert "secret" in config
            assert "scopes" in config


class TestUXImprovements:
    """Test UX improvement features"""

    def test_validate_only_flag(self):
        """Test parsing with --validate-only flag (alias for --dry-run)"""
        test_args = ["cja_sdr_generator.py", "--validate-only", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.dry_run is True

    def test_max_issues_flag(self):
        """Test parsing with --max-issues flag"""
        test_args = ["cja_sdr_generator.py", "--max-issues", "10", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.max_issues == 10

    def test_max_issues_default_zero(self):
        """Test that max-issues defaults to 0 (show all)"""
        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.max_issues == 0

    def test_max_issues_with_skip_validation(self):
        """Test max-issues with skip-validation"""
        test_args = ["cja_sdr_generator.py", "--max-issues", "5", "--skip-validation", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.max_issues == 5
            assert args.skip_validation is True

    def test_fail_on_quality_flag(self):
        """Test parsing with --fail-on-quality flag (case-insensitive input)."""
        test_args = ["cja_sdr_generator.py", "--fail-on-quality", "high", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.fail_on_quality == "HIGH"

    def test_quality_report_flag(self):
        """Test parsing with --quality-report flag."""
        test_args = ["cja_sdr_generator.py", "--quality-report", "json", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.quality_report == "json"

    def test_allow_partial_flag(self):
        """Test parsing with --allow-partial flag."""
        test_args = ["cja_sdr_generator.py", "--allow-partial", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.allow_partial is True

    def test_run_summary_json_flag(self):
        """Test parsing with --run-summary-json flag."""
        test_args = ["cja_sdr_generator.py", "--run-summary-json", "run_summary.json", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.run_summary_json == "run_summary.json"

    def test_quality_policy_flag(self):
        """Test parsing with --quality-policy flag."""
        test_args = ["cja_sdr_generator.py", "--quality-policy", "quality_policy.json", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.quality_policy == "quality_policy.json"

    def test_quality_policy_help_lists_allow_partial_key(self):
        """Quality policy help should advertise the current supported key set."""
        parser = parse_arguments(return_parser=True, enable_autocomplete=False)
        help_text = " ".join(parser.format_help().split())

        assert "supported keys: fail_on_quality, quality_report, max_issues, allow_partial" in help_text

    def test_profile_import_flags(self):
        """Test parsing with --profile-import and --profile-overwrite flags."""
        test_args = [
            "cja_sdr_generator.py",
            "--profile-import",
            "client-a",
            "credentials.json",
            "--profile-overwrite",
        ]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.profile_import == ["client-a", "credentials.json"]
            assert args.profile_overwrite is True


class TestProcessingResult:
    """Test ProcessingResult dataclass"""

    def test_file_size_formatted_bytes(self):
        """Test file size formatting for bytes"""
        from cja_auto_sdr.generator import ProcessingResult

        result = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test",
            success=True,
            duration=1.0,
            file_size_bytes=500,
        )
        assert result.file_size_formatted == "500 B"

    def test_file_size_formatted_kilobytes(self):
        """Test file size formatting for kilobytes"""
        from cja_auto_sdr.generator import ProcessingResult

        result = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test",
            success=True,
            duration=1.0,
            file_size_bytes=2048,
        )
        assert result.file_size_formatted == "2.0 KB"

    def test_file_size_formatted_megabytes(self):
        """Test file size formatting for megabytes"""
        from cja_auto_sdr.generator import ProcessingResult

        result = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test",
            success=True,
            duration=1.0,
            file_size_bytes=1048576,
        )
        assert result.file_size_formatted == "1.0 MB"

    def test_file_size_formatted_zero(self):
        """Test file size formatting for zero bytes"""
        from cja_auto_sdr.generator import ProcessingResult

        result = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test",
            success=True,
            duration=1.0,
            file_size_bytes=0,
        )
        assert result.file_size_formatted == "0 B"


class TestCacheFlags:
    """Test cache-related CLI flags"""

    def test_enable_cache_flag(self):
        """Test parsing with --enable-cache flag"""
        test_args = ["cja_sdr_generator.py", "--enable-cache", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.enable_cache is True

    def test_enable_cache_default_false(self):
        """Test that enable-cache defaults to False"""
        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.enable_cache is False

    def test_clear_cache_flag(self):
        """Test parsing with --clear-cache flag"""
        test_args = ["cja_sdr_generator.py", "--enable-cache", "--clear-cache", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.clear_cache is True
            assert args.enable_cache is True

    def test_clear_cache_default_false(self):
        """Test that clear-cache defaults to False"""
        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.clear_cache is False

    def test_cache_size_flag(self):
        """Test parsing with --cache-size flag"""
        test_args = ["cja_sdr_generator.py", "--cache-size", "5000", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.cache_size == 5000

    def test_cache_size_default(self):
        """Test that cache-size defaults to 1000"""
        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.cache_size == 1000

    def test_cache_ttl_flag(self):
        """Test parsing with --cache-ttl flag"""
        test_args = ["cja_sdr_generator.py", "--cache-ttl", "7200", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.cache_ttl == 7200

    def test_cache_ttl_default(self):
        """Test that cache-ttl defaults to 3600"""
        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.cache_ttl == 3600

    def test_all_cache_flags_combined(self):
        """Test all cache flags together"""
        test_args = [
            "cja_sdr_generator.py",
            "--enable-cache",
            "--clear-cache",
            "--cache-size",
            "2000",
            "--cache-ttl",
            "1800",
            "dv_12345",
        ]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.enable_cache is True
            assert args.clear_cache is True
            assert args.cache_size == 2000
            assert args.cache_ttl == 1800


class TestConstants:
    """Test that constants are properly used in defaults"""

    def test_workers_default_uses_auto(self):
        """Test that workers default is 'auto' for automatic detection"""
        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.workers == "auto"  # Default is now 'auto' for automatic detection

    def test_cache_size_default_uses_constant(self):
        """Test that cache_size default matches DEFAULT_CACHE_SIZE constant"""
        from cja_auto_sdr.generator import DEFAULT_CACHE_SIZE

        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.cache_size == DEFAULT_CACHE_SIZE

    def test_cache_ttl_default_uses_constant(self):
        """Test that cache_ttl default matches DEFAULT_CACHE_TTL constant"""
        from cja_auto_sdr.generator import DEFAULT_CACHE_TTL

        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.cache_ttl == DEFAULT_CACHE_TTL


class TestConsoleScriptEntryPoints:
    """Test console script entry point configuration"""

    def test_main_function_is_importable(self):
        """Test that main function can be imported from cja_sdr_generator"""
        from cja_auto_sdr.generator import main

        assert callable(main)

    def test_main_function_with_version_flag(self):
        """Test that main function handles --version flag correctly"""
        from cja_auto_sdr.generator import main

        test_args = ["cja_auto_sdr", "--version"]
        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_main_function_with_help_flag(self):
        """Test that main function handles --help flag correctly"""
        from cja_auto_sdr.generator import main

        test_args = ["cja_auto_sdr", "--help"]
        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

    def test_main_function_with_sample_config_flag(self):
        """Test that main function handles --sample-config flag"""
        from cja_auto_sdr.generator import main

        with tempfile.TemporaryDirectory() as tmpdir:
            os.path.join(tmpdir, "sample_config.json")
            test_args = ["cja_auto_sdr", "--sample-config"]
            with patch.object(sys, "argv", test_args):
                with patch("cja_auto_sdr.generator.generate_sample_config") as mock_gen:
                    mock_gen.return_value = True
                    with pytest.raises(SystemExit) as exc_info:
                        main()
                    assert exc_info.value.code == 0
                    mock_gen.assert_called_once()

    def test_entry_point_defined_in_pyproject(self):
        """Test that console script entry points are defined in pyproject.toml"""
        pyproject_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pyproject.toml")
        with open(pyproject_path) as f:
            content = f.read()

        # Verify both entry point variants exist with correct targets
        assert 'cja_auto_sdr = "cja_auto_sdr.__main__:main"' in content
        assert 'cja-auto-sdr = "cja_auto_sdr.__main__:main"' in content

        # Verify [project.scripts] section exists
        assert "[project.scripts]" in content

    def test_entry_point_builds_correctly(self):
        """Test that the package build system is configured"""
        pyproject_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pyproject.toml")
        with open(pyproject_path) as f:
            content = f.read()

        # Check build system is defined
        assert "[build-system]" in content
        assert "hatchling" in content
        assert 'build-backend = "hatchling.build"' in content

    def test_parse_arguments_works_with_console_script_name(self):
        """Test that argument parsing works with console script names"""
        # Test with underscore variant
        test_args = ["cja_auto_sdr", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.data_views == ["dv_12345"]

        # Test with hyphen variant
        test_args = ["cja-auto-sdr", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.data_views == ["dv_12345"]

    def test_version_output_format(self):
        """Test that version output follows expected format"""
        import subprocess

        from cja_auto_sdr.generator import __version__

        result = subprocess.run(
            ["uv", "run", "cja_auto_sdr", "--version"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        assert result.returncode == 0
        assert __version__ in result.stdout

        hyphen_result = subprocess.run(
            ["uv", "run", "cja-auto-sdr", "--version"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )
        assert hyphen_result.returncode == 0
        assert hyphen_result.stdout.strip().startswith("cja-auto-sdr ")
        assert __version__ in hyphen_result.stdout


class TestFastPathEntryPoint:
    """Tests for the __main__.py fast-path that avoids heavyweight imports."""

    def test_is_fast_path_flag_version(self):
        from cja_auto_sdr.__main__ import _is_fast_path_flag

        assert _is_fast_path_flag(["prog", "--version"]) == "--version"
        assert _is_fast_path_flag(["prog", "-V"]) == "--version"
        assert _is_fast_path_flag(["prog", "--profile", "client-a", "--version"]) == "--version"
        assert _is_fast_path_flag(["prog", "dv_12345", "--version"]) == "--version"
        assert _is_fast_path_flag(["prog", "--vers"]) == "--version"

    def test_is_fast_path_flag_version_respects_option_value_consumption(self):
        from cja_auto_sdr.__main__ import _is_fast_path_flag

        assert _is_fast_path_flag(["prog", "--profile", "--version"]) is None
        assert _is_fast_path_flag(["prog", "--profile-import", "client-a", "--version"]) is None
        assert _is_fast_path_flag(["prog", "--profile-import", "client-a", "source.json", "--version"]) == "--version"
        assert _is_fast_path_flag(["prog", "--", "--version"]) is None
        assert _is_fast_path_flag(["prog", "--v"]) is None

    def test_is_fast_path_flag_rejects_ambiguous_prefix_before_version(self):
        from cja_auto_sdr.__main__ import _is_fast_path_flag

        assert _is_fast_path_flag(["prog", "--v", "--version"]) is None

    def test_is_fast_path_flag_rejects_explicit_value_for_version_option(self):
        from cja_auto_sdr.__main__ import _is_fast_path_flag

        assert _is_fast_path_flag(["prog", "--version=foo"]) is None
        assert _is_fast_path_flag(["prog", "-V=foo"]) is None

    def test_is_fast_path_flag_rejects_explicit_value_for_zero_arity_option(self):
        from cja_auto_sdr.__main__ import _is_fast_path_flag

        assert _is_fast_path_flag(["prog", "--quiet=1", "--version"]) is None

    def test_is_fast_path_flag_help_precedes_version(self):
        from cja_auto_sdr.__main__ import _is_fast_path_flag

        assert _is_fast_path_flag(["prog", "--help", "--version"]) is None

    def test_is_fast_path_flag_rejects_missing_value_before_version(self):
        from cja_auto_sdr.__main__ import _is_fast_path_flag

        assert _is_fast_path_flag(["prog", "--profile", "--quiet", "--version"]) is None

    def test_is_fast_path_flag_rejects_mutex_conflict_before_version(self):
        from cja_auto_sdr.__main__ import _is_fast_path_flag

        assert _is_fast_path_flag(["prog", "--list-dataviews", "--list-connections", "--version"]) is None

    def test_is_fast_path_flag_version_handles_unknown_options_like_argparse(self):
        from cja_auto_sdr.__main__ import _is_fast_path_flag

        assert _is_fast_path_flag(["prog", "--unknown-option", "--version"]) == "--version"

    def test_is_fast_path_flag_version_takes_precedence_over_later_parse_errors(self):
        from cja_auto_sdr.__main__ import _is_fast_path_flag

        assert _is_fast_path_flag(["prog", "--version", "--v"]) == "--version"
        assert _is_fast_path_flag(["prog", "--version", "--quiet=1"]) == "--version"

    def test_is_fast_path_flag_exit_codes(self):
        from cja_auto_sdr.__main__ import _is_fast_path_flag

        assert _is_fast_path_flag(["prog", "--exit-codes"]) == "--exit-codes"

    def test_is_fast_path_flag_none_for_regular_args(self):
        from cja_auto_sdr.__main__ import _is_fast_path_flag

        assert _is_fast_path_flag(["prog", "dv_12345"]) is None
        assert _is_fast_path_flag(["prog"]) is None
        assert _is_fast_path_flag(["prog", "--exit-codes", "extra"]) is None

    def test_is_fast_path_flag_none_when_run_summary_requested(self):
        from cja_auto_sdr.__main__ import _is_fast_path_flag

        assert _is_fast_path_flag(["prog", "--version", "--run-summary-json", "stdout"]) is None
        assert _is_fast_path_flag(["prog", "--version", "--profile", "--run-summary-json", "stdout"]) is None
        assert _is_fast_path_flag(["prog", "--exit-codes", "--run-summary-j", "stdout"]) is None

    def test_has_run_summary_contract_flag_ignores_value_consumption_ordering(self):
        from cja_auto_sdr.__main__ import _has_run_summary_contract_flag

        assert _has_run_summary_contract_flag(["--version", "--profile", "--run-summary-json", "stdout"]) is True
        assert _has_run_summary_contract_flag(["--profile-import", "client-a", "--run-summary-json"]) is True

    def test_is_argcomplete_completion_active_detection(self):
        from cja_auto_sdr.__main__ import _is_argcomplete_completion_active

        assert _is_argcomplete_completion_active({}) is False
        assert _is_argcomplete_completion_active({"_ARGCOMPLETE": "1"}) is True
        assert _is_argcomplete_completion_active({"_ARGCOMPLETE": "true"}) is True
        assert _is_argcomplete_completion_active({"_ARGCOMPLETE": "0"}) is False
        assert _is_argcomplete_completion_active({"_ARGCOMPLETE": "off"}) is False
        assert _is_argcomplete_completion_active({"_ARGCOMPLETE": ""}) is False

    def test_has_run_summary_flag_rejects_ambiguous_prefixes(self):
        """Ambiguous prefixes must not falsely match --run-summary-json."""
        from cja_auto_sdr.__main__ import _has_run_summary_flag

        assert _has_run_summary_flag(["--r"]) is False
        assert _has_run_summary_flag(["--re"]) is False
        assert _has_run_summary_flag(["--retry"]) is False

    def test_has_run_summary_flag_accepts_unambiguous_prefixes(self):
        """Unambiguous argparse-style prefixes should match."""
        from cja_auto_sdr.__main__ import _has_run_summary_flag

        assert _has_run_summary_flag(["--ru"]) is True
        assert _has_run_summary_flag(["--run"]) is True
        assert _has_run_summary_flag(["--run-s"]) is True
        assert _has_run_summary_flag(["--run-summary"]) is True
        assert _has_run_summary_flag(["--run-summary-json"]) is True
        assert _has_run_summary_flag(["--run-summary-j"]) is True
        assert _has_run_summary_flag(["--run-summary-js"]) is True
        assert _has_run_summary_flag(["--run-summary-json=stdout"]) is True

    def test_has_run_summary_flag_ignores_tokens_consumed_as_option_values(self):
        from cja_auto_sdr.__main__ import _has_run_summary_flag

        assert _has_run_summary_flag(["--profile-import", "client-a", "--run-summary-json"]) is False
        assert _has_run_summary_flag(["--profile-import", "client-a", "--run-summary-json", "--version"]) is False

    @pytest.mark.parametrize(
        ("argv", "expected_shell"),
        [
            (["prog", "--completion", "bash"], "bash"),
            (["prog", "--completion=zsh"], "zsh"),
            (["prog", "--completion"], None),
            (["prog", "--completion", "ksh"], None),
            (["prog", "--profile", "--completion", "bash"], None),
            (["prog", "--version", "--completion", "ksh"], None),
            (["prog", "--completion", "bash", "dv_test"], None),
            (["prog", "--completion", "bash", "--run-summary-json", "stdout"], None),
        ],
    )
    def test_completion_fast_path_shell_only_allows_parse_valid_standalone_requests(self, argv, expected_shell):
        from cja_auto_sdr.__main__ import _completion_fast_path_shell

        assert _completion_fast_path_shell(argv) == expected_shell

    def test_fast_path_version_output(self, capsys):
        from cja_auto_sdr.__main__ import _print_version
        from cja_auto_sdr.core.version import __version__

        _print_version()
        captured = capsys.readouterr()
        assert captured.out.strip() == f"cja_auto_sdr {__version__}"

    def test_fast_path_resolve_program_name(self):
        import os
        import sys

        from cja_auto_sdr.__main__ import _resolve_program_name

        assert _resolve_program_name("cja_auto_sdr") == "cja_auto_sdr"
        assert _resolve_program_name("/usr/local/bin/cja-auto-sdr") == "cja-auto-sdr"
        expected_module_prog = f"{os.path.basename(sys.executable)} -m cja_auto_sdr"
        assert _resolve_program_name("/tmp/cja_auto_sdr/__main__.py", "cja_auto_sdr.__main__") == expected_module_prog
        assert (
            _resolve_program_name("/tmp/cja_auto_sdr/__main__.py", "cja_auto_sdr.__main__", "python3")
            == "python3 -m cja_auto_sdr"
        )
        assert _resolve_program_name("") == "cja_auto_sdr"

    def test_resolve_completion_command_name(self):
        from cja_auto_sdr.__main__ import _resolve_completion_command_name

        assert _resolve_completion_command_name("cja_auto_sdr") == "cja_auto_sdr"
        assert _resolve_completion_command_name("cja-auto-sdr") == "cja-auto-sdr"
        assert _resolve_completion_command_name("/usr/local/bin/cja-auto-sdr") == "cja-auto-sdr"
        assert _resolve_completion_command_name("__main__.py") == "cja_auto_sdr"
        assert _resolve_completion_command_name("") == "cja_auto_sdr"
        assert _resolve_completion_command_name(None) == "cja_auto_sdr"

    def test_render_completion_script_quotes_command_names(self):
        from cja_auto_sdr.__main__ import _render_completion_script

        script = _render_completion_script("bash", "cja auto sdr")
        assert "register-python-argcomplete 'cja auto sdr'" in script

    def test_fast_path_version_output_uses_program_name(self, capsys):
        from cja_auto_sdr.__main__ import _print_version
        from cja_auto_sdr.core.version import __version__

        _print_version("cja-auto-sdr")
        captured = capsys.readouterr()
        assert captured.out.strip() == f"cja-auto-sdr {__version__}"

    def test_fast_path_exit_codes_output(self, capsys):
        from cja_auto_sdr.__main__ import _print_exit_codes
        from cja_auto_sdr.core.constants import BANNER_WIDTH

        _print_exit_codes()
        captured = capsys.readouterr()
        assert "EXIT CODE REFERENCE" in captured.out
        assert "CI/CD Examples:" in captured.out
        assert captured.out.splitlines()[0] == "=" * BANNER_WIDTH

    def test_fast_path_main_version_exits_zero(self):
        from cja_auto_sdr.__main__ import main as fast_main

        with patch.object(sys, "argv", ["cja_auto_sdr", "--version"]):
            with pytest.raises(SystemExit) as exc_info:
                fast_main()
            assert exc_info.value.code == 0

    def test_fast_path_main_version_after_other_option_exits_zero(self, capsys):
        from cja_auto_sdr.__main__ import main as fast_main
        from cja_auto_sdr.core.version import __version__

        with patch.object(sys, "argv", ["cja_auto_sdr", "--profile", "client-a", "--version"]):
            with pytest.raises(SystemExit) as exc_info:
                fast_main()
            assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert captured.out.strip() == f"cja_auto_sdr {__version__}"

    def test_fast_path_main_version_like_value_token_falls_through_to_generator(self):
        from cja_auto_sdr.__main__ import main as fast_main

        with patch.object(sys, "argv", ["cja_auto_sdr", "--profile", "--version"]):
            with patch("cja_auto_sdr.generator.main") as mock_gen_main:
                fast_main()
                mock_gen_main.assert_called_once()

    def test_fast_path_main_malformed_version_invocations_fall_through_to_generator(self):
        from cja_auto_sdr.__main__ import main as fast_main

        malformed_argv = [
            ["cja_auto_sdr", "--v", "--version"],
            ["cja_auto_sdr", "--version=foo"],
            ["cja_auto_sdr", "-V=foo"],
            ["cja_auto_sdr", "--quiet=1", "--version"],
            ["cja_auto_sdr", "--profile", "--quiet", "--version"],
            ["cja_auto_sdr", "--list-dataviews", "--list-connections", "--version"],
        ]
        for argv in malformed_argv:
            with patch.object(sys, "argv", argv):
                with patch("cja_auto_sdr.generator.main") as mock_gen_main:
                    fast_main()
                    mock_gen_main.assert_called_once()

    def test_fast_path_main_version_takes_precedence_over_later_parse_errors(self):
        from cja_auto_sdr.__main__ import main as fast_main

        valid_version_argv = [
            ["cja_auto_sdr", "--version", "--v"],
            ["cja_auto_sdr", "--version", "--quiet=1"],
        ]
        for argv in valid_version_argv:
            with patch.object(sys, "argv", argv):
                with patch("cja_auto_sdr.generator.main") as mock_gen_main:
                    with pytest.raises(SystemExit) as exc_info:
                        fast_main()
                    assert exc_info.value.code == 0
                    mock_gen_main.assert_not_called()

    def test_fast_path_main_version_uses_invoked_program_name(self, capsys):
        from cja_auto_sdr.__main__ import main as fast_main
        from cja_auto_sdr.core.version import __version__

        with patch.object(sys, "argv", ["/tmp/cja-auto-sdr", "--version"]):
            with pytest.raises(SystemExit) as exc_info:
                fast_main()
            assert exc_info.value.code == 0

        captured = capsys.readouterr()
        assert captured.out.strip() == f"cja-auto-sdr {__version__}"

    def test_fast_path_main_version_module_invocation_name(self, capsys):
        import os
        import sys

        from cja_auto_sdr.__main__ import main as fast_main
        from cja_auto_sdr.core.version import __version__

        with patch.object(sys, "argv", ["/tmp/cja_auto_sdr/__main__.py", "--version"]):
            with pytest.raises(SystemExit) as exc_info:
                fast_main()
            assert exc_info.value.code == 0

        captured = capsys.readouterr()
        expected_prefix = f"{os.path.basename(sys.executable)} -m cja_auto_sdr"
        assert captured.out.strip() == f"{expected_prefix} {__version__}"

    def test_fast_path_main_exit_codes_exits_zero(self):
        from cja_auto_sdr.__main__ import main as fast_main

        with patch.object(sys, "argv", ["cja_auto_sdr", "--exit-codes"]):
            with pytest.raises(SystemExit) as exc_info:
                fast_main()
            assert exc_info.value.code == 0

    def test_fast_path_main_version_falls_through_when_argcomplete_active(self):
        from cja_auto_sdr.__main__ import main as fast_main

        with patch.dict(os.environ, {"_ARGCOMPLETE": "1"}):
            with patch.object(sys, "argv", ["cja_auto_sdr", "--version"]):
                with patch("cja_auto_sdr.generator.main") as mock_gen_main:
                    fast_main()
                    mock_gen_main.assert_called_once()

    def test_fast_path_main_exit_codes_falls_through_when_argcomplete_active(self):
        from cja_auto_sdr.__main__ import main as fast_main

        with patch.dict(os.environ, {"_ARGCOMPLETE": "1"}):
            with patch.object(sys, "argv", ["cja_auto_sdr", "--exit-codes"]):
                with patch("cja_auto_sdr.generator.main") as mock_gen_main:
                    fast_main()
                    mock_gen_main.assert_called_once()

    def test_fast_path_main_version_uses_fast_path_when_argcomplete_disabled(self):
        from cja_auto_sdr.__main__ import main as fast_main

        with patch.dict(os.environ, {"_ARGCOMPLETE": "0"}):
            with patch.object(sys, "argv", ["cja_auto_sdr", "--version"]):
                with pytest.raises(SystemExit) as exc_info:
                    fast_main()
                assert exc_info.value.code == 0

    def test_fast_path_falls_through_to_generator(self):
        from cja_auto_sdr.__main__ import main as fast_main

        with patch.object(sys, "argv", ["cja_auto_sdr", "dv_test"]):
            with patch("cja_auto_sdr.generator.main") as mock_gen_main:
                fast_main()
                mock_gen_main.assert_called_once()

    def test_fast_path_version_with_run_summary_falls_through_to_generator(self):
        from cja_auto_sdr.__main__ import main as fast_main

        with patch.object(sys, "argv", ["cja_auto_sdr", "--version", "--run-summary-json", "stdout"]):
            with patch("cja_auto_sdr.generator.main") as mock_gen_main:
                fast_main()
                mock_gen_main.assert_called_once()

    def test_fast_path_version_with_run_summary_after_option_needing_value_falls_through_to_generator(self):
        from cja_auto_sdr.__main__ import main as fast_main

        with patch.object(sys, "argv", ["cja_auto_sdr", "--version", "--profile", "--run-summary-json", "stdout"]):
            with patch("cja_auto_sdr.generator.main") as mock_gen_main:
                fast_main()
                mock_gen_main.assert_called_once()

    def test_fast_path_short_version_with_run_summary_falls_through_to_generator(self):
        from cja_auto_sdr.__main__ import main as fast_main

        with patch.object(sys, "argv", ["cja_auto_sdr", "-V", "--run-summary-json", "stdout"]):
            with patch("cja_auto_sdr.generator.main") as mock_gen_main:
                fast_main()
                mock_gen_main.assert_called_once()

    def test_fast_path_version_with_abbrev_run_summary_falls_through_to_generator(self):
        from cja_auto_sdr.__main__ import main as fast_main

        with patch.object(sys, "argv", ["cja_auto_sdr", "--version", "--run", "stdout"]):
            with patch("cja_auto_sdr.generator.main") as mock_gen_main:
                fast_main()
                mock_gen_main.assert_called_once()

    @pytest.mark.parametrize(
        ("argv_tail", "stderr_substring"),
        [
            (["--v", "--version"], "ambiguous option"),
            (["--version=foo"], "ignored explicit argument"),
            (["-V=foo"], "ignored explicit argument"),
            (["--profile", "--quiet", "--version"], "expected one argument"),
            (["--list-dataviews", "--list-connections", "--version"], "not allowed with argument"),
        ],
    )
    def test_fast_path_malformed_version_invocations_preserve_argparse_error_exit(self, argv_tail, stderr_substring):
        import subprocess

        result = subprocess.run(
            ["uv", "run", "cja_auto_sdr", *argv_tail],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )

        assert result.returncode == 2
        assert stderr_substring in result.stderr

    def test_fast_path_malformed_completion_with_missing_option_value_preserves_argparse_error_exit(self):
        result = subprocess.run(
            ["uv", "run", "cja_auto_sdr", "--profile", "--completion", "bash"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )

        assert result.returncode == 2
        assert "expected one argument" in result.stderr

    def test_fast_path_version_with_invalid_completion_shell_preserves_version_precedence(self):
        from cja_auto_sdr.core.version import __version__

        result = subprocess.run(
            ["uv", "run", "cja_auto_sdr", "--version", "--completion", "ksh"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )

        assert result.returncode == 0
        assert result.stdout.strip() == f"cja_auto_sdr {__version__}"
        assert "unsupported shell" not in result.stderr

    def test_fast_path_help_before_version_preserves_help_precedence(self):
        import subprocess

        result = subprocess.run(
            ["uv", "run", "cja_auto_sdr", "--help", "--version"],
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        )

        assert result.returncode == 0
        assert "usage:" in result.stdout
        assert "show this help message and exit" in result.stdout


class TestQualityGateAndReport:
    """Tests for quality gate/report behavior in main()."""

    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_fail_on_quality_exits_with_code_2(self, mock_resolve, mock_process):
        """Exit code should be 2 when threshold severity issues are found."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_test"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=True,
            duration=0.1,
            metrics_count=1,
            dimensions_count=1,
            dq_issues_count=1,
            dq_issues=[{"Severity": "HIGH", "Issue": "Duplicate component"}],
            dq_severity_counts={"HIGH": 1},
        )

        with patch.object(sys, "argv", ["cja_auto_sdr", "dv_test", "--fail-on-quality", "HIGH"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 2

    @patch("cja_auto_sdr.generator.write_quality_report_output")
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_quality_report_mode_uses_standalone_writer(self, mock_resolve, mock_process, mock_write_report):
        """Quality report mode should bypass SDR files and emit standalone report."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_test"], {})
        mock_write_report.return_value = "stdout"
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=True,
            duration=0.1,
            dq_issues_count=1,
            dq_issues=[{"Severity": "LOW", "Issue": "Missing description"}],
            dq_severity_counts={"LOW": 1},
        )

        with patch.object(sys, "argv", ["cja_auto_sdr", "dv_test", "--quality-report", "json", "--output", "-"]):
            main()

        assert mock_process.call_args.kwargs["quality_report_only"] is True
        mock_write_report.assert_called_once()

    def test_quality_report_rejects_skip_validation(self):
        """Quality report mode should reject --skip-validation."""
        from cja_auto_sdr.generator import main

        with patch.object(sys, "argv", ["cja_auto_sdr", "dv_test", "--quality-report", "json", "--skip-validation"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1

    def test_allow_partial_rejects_quality_report_mode(self):
        """Exploratory partial mode should not be combined with standalone quality-report mode."""
        from cja_auto_sdr.generator import main

        with patch.object(sys, "argv", ["cja_auto_sdr", "dv_test", "--quality-report", "json", "--allow-partial"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1

    def test_fail_on_quality_rejects_skip_validation(self):
        """Quality gate should reject --skip-validation to avoid silent policy bypass."""
        from cja_auto_sdr.generator import main

        with patch.object(sys, "argv", ["cja_auto_sdr", "dv_test", "--fail-on-quality", "HIGH", "--skip-validation"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1

    def test_allow_partial_rejects_fail_on_quality(self):
        """Exploratory partial mode should not be combined with strict fail-on-quality policy gates."""
        from cja_auto_sdr.generator import main

        with patch.object(sys, "argv", ["cja_auto_sdr", "dv_test", "--fail-on-quality", "HIGH", "--allow-partial"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1

    @patch("cja_auto_sdr.generator.show_config_status")
    def test_fail_on_quality_rejects_non_sdr_config_json_mode(self, mock_show_config_status):
        """Quality gate should fail fast for --config-json (non-SDR mode)."""
        from cja_auto_sdr.generator import main

        with patch.object(sys, "argv", ["cja_auto_sdr", "--config-json", "--fail-on-quality", "HIGH"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        mock_show_config_status.assert_not_called()

    @patch("cja_auto_sdr.generator.handle_diff_command")
    def test_fail_on_quality_rejects_non_sdr_diff_mode(self, mock_handle_diff):
        """Quality gate should fail fast in non-SDR modes instead of being silently ignored."""
        from cja_auto_sdr.generator import main

        with patch.object(sys, "argv", ["cja_auto_sdr", "--diff", "dv_a", "dv_b", "--fail-on-quality", "HIGH"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        mock_handle_diff.assert_not_called()

    @patch("cja_auto_sdr.generator.handle_diff_command")
    def test_allow_partial_rejects_non_sdr_diff_mode(self, mock_handle_diff):
        """--allow-partial should fail fast in non-SDR modes."""
        from cja_auto_sdr.generator import main

        with patch.object(sys, "argv", ["cja_auto_sdr", "--diff", "dv_a", "dv_b", "--allow-partial"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        mock_handle_diff.assert_not_called()

    @patch("cja_auto_sdr.generator.generate_sample_config")
    def test_quality_report_rejects_non_sdr_sample_config_mode(self, mock_generate_sample_config):
        """Quality report should fail fast for sample-config mode instead of being ignored."""
        from cja_auto_sdr.generator import main

        with patch.object(sys, "argv", ["cja_auto_sdr", "--sample-config", "--quality-report", "json"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        mock_generate_sample_config.assert_not_called()

    @patch("cja_auto_sdr.generator.write_quality_report_output")
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_quality_report_continue_on_error_still_exits_1_on_processing_failure(
        self,
        mock_resolve,
        mock_process,
        mock_write_report,
    ):
        """--continue-on-error should continue processing but still fail on processing errors."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_fail", "dv_ok"], {})
        mock_write_report.return_value = "stdout"
        mock_process.side_effect = [
            ProcessingResult(
                data_view_id="dv_fail",
                data_view_name="Failing View",
                success=False,
                duration=0.1,
                error_message="mock failure",
            ),
            ProcessingResult(
                data_view_id="dv_ok",
                data_view_name="Healthy View",
                success=True,
                duration=0.1,
                dq_issues_count=1,
                dq_issues=[{"Severity": "LOW", "Issue": "Minor"}],
                dq_severity_counts={"LOW": 1},
            ),
        ]

        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "dv_fail", "dv_ok", "--quality-report", "json", "--output", "-", "--continue-on-error"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        mock_write_report.assert_called_once()

    @patch("cja_auto_sdr.generator.write_quality_report_output")
    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary")
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_quality_report_summary_includes_failed_and_successful_results(
        self,
        mock_resolve,
        mock_process,
        mock_build_summary,
        mock_append_summary,
        mock_write_report,
    ):
        """GitHub quality summary should include all processed data views."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_fail", "dv_ok"], {})
        mock_build_summary.return_value = "summary"
        mock_append_summary.return_value = True
        mock_write_report.return_value = "stdout"
        mock_process.side_effect = [
            ProcessingResult(
                data_view_id="dv_fail",
                data_view_name="Failing View",
                success=False,
                duration=0.1,
                error_message="mock failure",
            ),
            ProcessingResult(
                data_view_id="dv_ok",
                data_view_name="Healthy View",
                success=True,
                duration=0.1,
                dq_issues_count=1,
                dq_issues=[{"Severity": "LOW", "Issue": "Minor"}],
                dq_severity_counts={"LOW": 1},
            ),
        ]

        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "dv_fail", "dv_ok", "--quality-report", "json", "--output", "-", "--continue-on-error"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        mock_build_summary.assert_called_once()
        summary_results = mock_build_summary.call_args.args[0]
        assert [r.data_view_id for r in summary_results] == ["dv_fail", "dv_ok"]
        assert summary_results[0].success is False
        assert summary_results[1].success is True

    @patch("cja_auto_sdr.generator.write_quality_report_output", side_effect=OSError("permission denied"))
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_quality_report_write_error_exits_cleanly_with_code_1(
        self,
        mock_resolve,
        mock_process,
        mock_write_report,
        capsys,
    ):
        """Quality report write failures should be handled with a clean exit code 1."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_ok"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_ok",
            data_view_name="Healthy View",
            success=True,
            duration=0.1,
            dq_issues_count=0,
            dq_issues=[],
            dq_severity_counts={},
        )

        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "dv_ok", "--quality-report", "json", "--output", "report.json"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        captured = capsys.readouterr()
        assert "Failed to write quality report" in captured.err
        mock_write_report.assert_called_once()

    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_quality_policy_applies_default_fail_on_quality(self, mock_resolve, mock_process, tmp_path):
        """Quality policy should supply fail_on_quality when CLI flag is omitted."""
        from cja_auto_sdr.generator import ProcessingResult, main

        policy_path = tmp_path / "quality_policy.json"
        policy_path.write_text(json.dumps({"fail_on_quality": "HIGH"}), encoding="utf-8")

        mock_resolve.return_value = (["dv_test"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=True,
            duration=0.1,
            dq_issues_count=1,
            dq_issues=[{"Severity": "HIGH", "Issue": "Threshold issue"}],
            dq_severity_counts={"HIGH": 1},
        )

        with patch.object(sys, "argv", ["cja_auto_sdr", "dv_test", "--quality-policy", str(policy_path)]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 2

    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_quality_policy_can_enable_allow_partial(self, mock_resolve, mock_process, tmp_path):
        """Quality policy should support allow_partial as an opt-in default."""
        from cja_auto_sdr.generator import ProcessingResult, main

        policy_path = tmp_path / "quality_policy.json"
        policy_path.write_text(json.dumps({"allow_partial": True}), encoding="utf-8")

        mock_resolve.return_value = (["dv_test"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=True,
            duration=0.1,
            dq_issues_count=0,
            dq_issues=[],
            dq_severity_counts={},
        )

        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "dv_test", "--quality-policy", str(policy_path)],
        ):
            main()

        assert mock_process.call_args.kwargs["allow_partial"] is True

    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_cli_fail_on_quality_overrides_quality_policy(self, mock_resolve, mock_process, tmp_path):
        """Explicit --fail-on-quality should override policy defaults."""
        from cja_auto_sdr.generator import ProcessingResult, main

        policy_path = tmp_path / "quality_policy.json"
        policy_path.write_text(json.dumps({"fail_on_quality": "HIGH"}), encoding="utf-8")

        mock_resolve.return_value = (["dv_test"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=True,
            duration=0.1,
            dq_issues_count=1,
            dq_issues=[{"Severity": "HIGH", "Issue": "Threshold issue"}],
            dq_severity_counts={"HIGH": 1},
        )

        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "dv_test", "--quality-policy", str(policy_path), "--fail-on-quality", "CRITICAL"],
        ):
            main()

    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_cli_fail_on_quality_prevents_policy_allow_partial_default(self, mock_resolve, mock_process, tmp_path):
        """Explicit fail-on-quality should prevent policy allow_partial from being applied."""
        from cja_auto_sdr.generator import ProcessingResult, main

        policy_path = tmp_path / "quality_policy.json"
        policy_path.write_text(json.dumps({"allow_partial": True}), encoding="utf-8")

        mock_resolve.return_value = (["dv_test"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=True,
            duration=0.1,
            dq_issues_count=0,
            dq_issues=[],
            dq_severity_counts={},
        )

        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "dv_test", "--quality-policy", str(policy_path), "--fail-on-quality", "HIGH"],
        ):
            main()

        assert mock_process.call_args.kwargs["allow_partial"] is False

    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_cli_abbreviated_quality_flags_override_quality_policy(self, mock_resolve, mock_process, tmp_path):
        """Argparse-accepted long-option abbreviations should retain CLI precedence over policy defaults."""
        from cja_auto_sdr.generator import ProcessingResult, main

        policy_path = tmp_path / "quality_policy.json"
        policy_path.write_text(json.dumps({"fail_on_quality": "HIGH", "max_issues": 7}), encoding="utf-8")

        mock_resolve.return_value = (["dv_test"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=True,
            duration=0.1,
            dq_issues_count=1,
            dq_issues=[{"Severity": "HIGH", "Issue": "Threshold issue"}],
            dq_severity_counts={"HIGH": 1},
        )

        with patch.object(
            sys,
            "argv",
            [
                "cja_auto_sdr",
                "dv_test",
                "--quality-policy",
                str(policy_path),
                "--fail-on-q",
                "CRITICAL",
                "--max-i",
                "0",
            ],
        ):
            main()

        assert mock_process.call_args.kwargs["max_issues"] == 0

    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_invalid_quality_policy_fails_fast(self, mock_resolve, tmp_path):
        """Invalid quality policy should exit before data view resolution."""
        from cja_auto_sdr.generator import main

        policy_path = tmp_path / "quality_policy_invalid.json"
        policy_path.write_text(json.dumps({"fail_on_quality": "NOT_A_LEVEL"}), encoding="utf-8")

        with patch.object(sys, "argv", ["cja_auto_sdr", "dv_test", "--quality-policy", str(policy_path)]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        mock_resolve.assert_not_called()

    @pytest.mark.parametrize("invalid_max_issues", [True, 1.9, "10"])
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_invalid_quality_policy_max_issues_type_fails_fast(self, mock_resolve, invalid_max_issues, tmp_path):
        """max_issues must be a JSON integer; bool/float/string values should fail fast."""
        from cja_auto_sdr.generator import main

        policy_path = tmp_path / "quality_policy_invalid_max_issues.json"
        policy_path.write_text(json.dumps({"max_issues": invalid_max_issues}), encoding="utf-8")

        with patch.object(sys, "argv", ["cja_auto_sdr", "dv_test", "--quality-policy", str(policy_path)]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        mock_resolve.assert_not_called()

    @patch("cja_auto_sdr.generator.list_dataviews")
    def test_quality_policy_defaults_deferred_for_non_sdr_mode(self, mock_list_dataviews, tmp_path):
        """Non-SDR commands should not inherit SDR-only defaults from shared quality policy files."""
        from cja_auto_sdr.generator import main

        policy_path = tmp_path / "quality_policy.json"
        policy_path.write_text(
            json.dumps({"fail_on_quality": "HIGH", "quality_report": "csv", "max_issues": 5}),
            encoding="utf-8",
        )
        mock_list_dataviews.return_value = True

        with patch.object(sys, "argv", ["cja_auto_sdr", "--list-dataviews", "--quality-policy", str(policy_path)]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        mock_list_dataviews.assert_called_once()

    def test_quality_report_csv_empty_writes_header_row(self, tmp_path):
        """CSV quality reports should include headers even when there are no issues."""
        from cja_auto_sdr.generator import write_quality_report_output

        output_path = tmp_path / "quality_report.csv"
        write_quality_report_output([], report_format="csv", output=str(output_path), output_dir=tmp_path)

        header = output_path.read_text(encoding="utf-8").splitlines()[0]
        assert header == "Data View ID,Data View Name,Severity,Category,Type,Item Name,Issue,Details"

    @patch("cja_auto_sdr.generator.BatchProcessor")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_batch_failures_take_precedence_over_quality_gate_with_continue_on_error(
        self,
        mock_resolve,
        mock_batch_cls,
    ):
        """Batch processing failures should keep exit code 1 precedence over quality gate exit 2."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_fail", "dv_ok"], {})
        mock_batch = mock_batch_cls.return_value
        mock_batch.process_batch.return_value = {
            "successful": [
                ProcessingResult(
                    data_view_id="dv_ok",
                    data_view_name="Healthy View",
                    success=True,
                    duration=0.1,
                    dq_issues_count=1,
                    dq_issues=[{"Severity": "HIGH", "Issue": "Threshold issue"}],
                    dq_severity_counts={"HIGH": 1},
                ),
            ],
            "failed": [
                ProcessingResult(
                    data_view_id="dv_fail",
                    data_view_name="Failing View",
                    success=False,
                    duration=0.1,
                    error_message="mock failure",
                ),
            ],
            "total": 2,
            "total_duration": 0.2,
        }

        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "dv_fail", "dv_ok", "--continue-on-error", "--fail-on-quality", "HIGH"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1

    @patch("cja_auto_sdr.generator.append_github_step_summary")
    @patch("cja_auto_sdr.generator.build_quality_step_summary")
    @patch("cja_auto_sdr.generator.BatchProcessor")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_batch_summary_includes_failed_views_in_standard_mode(
        self,
        mock_resolve,
        mock_batch_cls,
        mock_build_summary,
        mock_append_summary,
    ):
        """Quality summary should include failed views in normal SDR batch mode."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_fail", "dv_ok"], {})
        mock_build_summary.return_value = "summary"
        mock_append_summary.return_value = True
        mock_batch = mock_batch_cls.return_value
        mock_batch.process_batch.return_value = {
            "successful": [
                ProcessingResult(
                    data_view_id="dv_ok",
                    data_view_name="Healthy View",
                    success=True,
                    duration=0.1,
                    dq_issues_count=0,
                    dq_issues=[],
                    dq_severity_counts={},
                ),
            ],
            "failed": [
                ProcessingResult(
                    data_view_id="dv_fail",
                    data_view_name="Failing View",
                    success=False,
                    duration=0.1,
                    error_message="mock failure",
                ),
            ],
            "total": 2,
            "total_duration": 0.2,
        }

        with patch.object(sys, "argv", ["cja_auto_sdr", "dv_fail", "dv_ok", "--continue-on-error"]):
            main()

        mock_build_summary.assert_called_once()
        summary_results = mock_build_summary.call_args.args[0]
        assert len(summary_results) == 2
        assert {result.data_view_id for result in summary_results} == {"dv_fail", "dv_ok"}
        assert any(not result.success for result in summary_results)

    def test_auto_prune_requires_auto_snapshot(self):
        """--auto-prune should fail fast without --auto-snapshot."""
        from cja_auto_sdr.generator import main

        with patch.object(sys, "argv", ["cja_auto_sdr", "--diff", "dv_a", "dv_b", "--auto-prune"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1

    @patch("cja_auto_sdr.generator.SnapshotManager")
    def test_auto_prune_allowed_for_prune_snapshots_mode(self, mock_snapshot_cls):
        """--prune-snapshots should allow --auto-prune without --auto-snapshot."""
        from cja_auto_sdr.generator import main

        mock_snapshot = mock_snapshot_cls.return_value
        mock_snapshot.list_snapshots.return_value = []
        mock_snapshot.apply_retention_policy.return_value = []
        mock_snapshot.apply_date_retention_policy.return_value = []

        with patch.object(sys, "argv", ["cja_auto_sdr", "--prune-snapshots", "--auto-prune"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        mock_snapshot.apply_date_retention_policy.assert_called_once()

    def test_auto_prune_defaults_apply_only_when_retention_flags_omitted(self):
        """Auto-prune defaults should only apply when neither retention flag is provided."""
        from cja_auto_sdr.generator import (
            DEFAULT_AUTO_PRUNE_KEEP_LAST,
            DEFAULT_AUTO_PRUNE_KEEP_SINCE,
            resolve_auto_prune_retention,
        )

        keep_last, keep_since = resolve_auto_prune_retention(
            keep_last=0,
            keep_since=None,
            auto_prune=True,
            keep_last_specified=False,
            keep_since_specified=False,
        )
        assert keep_last == DEFAULT_AUTO_PRUNE_KEEP_LAST
        assert keep_since == DEFAULT_AUTO_PRUNE_KEEP_SINCE

        keep_last, keep_since = resolve_auto_prune_retention(
            keep_last=0,
            keep_since=None,
            auto_prune=True,
            keep_last_specified=True,
            keep_since_specified=False,
        )
        assert keep_last == 0
        assert keep_since is None

    @patch("cja_auto_sdr.generator.handle_diff_command")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_keep_last_equals_syntax_counts_as_explicit_for_auto_prune(self, mock_resolve, mock_handle_diff):
        """--keep-last=0 should be treated as explicitly provided retention."""
        from cja_auto_sdr.generator import main

        mock_resolve.side_effect = [(["dv_a"], {}), (["dv_b"], {})]
        mock_handle_diff.return_value = (True, False, None)

        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "--diff", "dv_a", "dv_b", "--auto-snapshot", "--auto-prune", "--keep-last=0"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        assert mock_handle_diff.call_args.kwargs["keep_last_specified"] is True
        assert mock_handle_diff.call_args.kwargs["keep_since_specified"] is False

    @patch("cja_auto_sdr.generator.handle_diff_command")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_keep_since_equals_syntax_counts_as_explicit_for_auto_prune(self, mock_resolve, mock_handle_diff):
        """--keep-since=90d should be treated as explicitly provided retention."""
        from cja_auto_sdr.generator import main

        mock_resolve.side_effect = [(["dv_a"], {}), (["dv_b"], {})]
        mock_handle_diff.return_value = (True, False, None)

        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "--diff", "dv_a", "dv_b", "--auto-snapshot", "--auto-prune", "--keep-since=90d"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        assert mock_handle_diff.call_args.kwargs["keep_last_specified"] is False
        assert mock_handle_diff.call_args.kwargs["keep_since_specified"] is True


class TestRetryArguments:
    """Test retry-related CLI arguments"""

    def test_max_retries_flag(self):
        """Test parsing with --max-retries flag"""
        test_args = ["cja_sdr_generator.py", "--max-retries", "5", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.max_retries == 5

    def test_max_retries_default(self):
        """Test that max-retries uses default from DEFAULT_RETRY_CONFIG"""
        from cja_auto_sdr.generator import DEFAULT_RETRY_CONFIG

        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.max_retries == DEFAULT_RETRY_CONFIG["max_retries"]

    def test_retry_base_delay_flag(self):
        """Test parsing with --retry-base-delay flag"""
        test_args = ["cja_sdr_generator.py", "--retry-base-delay", "2.5", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.retry_base_delay == 2.5

    def test_retry_base_delay_default(self):
        """Test that retry-base-delay uses default from DEFAULT_RETRY_CONFIG"""
        from cja_auto_sdr.generator import DEFAULT_RETRY_CONFIG

        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.retry_base_delay == DEFAULT_RETRY_CONFIG["base_delay"]

    def test_retry_max_delay_flag(self):
        """Test parsing with --retry-max-delay flag"""
        test_args = ["cja_sdr_generator.py", "--retry-max-delay", "60.0", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.retry_max_delay == 60.0

    def test_retry_max_delay_default(self):
        """Test that retry-max-delay uses default from DEFAULT_RETRY_CONFIG"""
        from cja_auto_sdr.generator import DEFAULT_RETRY_CONFIG

        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.retry_max_delay == DEFAULT_RETRY_CONFIG["max_delay"]

    def test_all_retry_flags_combined(self):
        """Test all retry flags together"""
        test_args = [
            "cja_sdr_generator.py",
            "--max-retries",
            "10",
            "--retry-base-delay",
            "0.5",
            "--retry-max-delay",
            "120",
            "dv_12345",
        ]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.max_retries == 10
            assert args.retry_base_delay == 0.5
            assert args.retry_max_delay == 120.0

    def test_retry_env_var_max_retries(self):
        """Test that MAX_RETRIES env var sets default"""
        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.dict(os.environ, {"MAX_RETRIES": "7"}):
            with patch.object(sys, "argv", test_args):
                args = parse_arguments()
                assert args.max_retries == 7

    def test_retry_env_var_base_delay(self):
        """Test that RETRY_BASE_DELAY env var sets default"""
        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.dict(os.environ, {"RETRY_BASE_DELAY": "3.5"}):
            with patch.object(sys, "argv", test_args):
                args = parse_arguments()
                assert args.retry_base_delay == 3.5

    def test_retry_env_var_max_delay(self):
        """Test that RETRY_MAX_DELAY env var sets default"""
        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.dict(os.environ, {"RETRY_MAX_DELAY": "90.0"}):
            with patch.object(sys, "argv", test_args):
                args = parse_arguments()
                assert args.retry_max_delay == 90.0

    def test_retry_cli_overrides_env_var(self):
        """Test that CLI arguments override environment variables"""
        test_args = ["cja_sdr_generator.py", "--max-retries", "2", "dv_12345"]
        with patch.dict(os.environ, {"MAX_RETRIES": "10"}):
            with patch.object(sys, "argv", test_args):
                args = parse_arguments()
                assert args.max_retries == 2

    def test_dotenv_bootstrap_applies_env_backed_defaults(self):
        """Parser defaults should honor values loaded from dotenv bootstrap."""
        test_args = ["cja_sdr_generator.py", "dv_12345"]

        def _bootstrap_side_effect(_logger):
            os.environ["OUTPUT_DIR"] = "./dotenv-output"
            os.environ["LOG_LEVEL"] = "WARNING"
            os.environ["MAX_RETRIES"] = "9"
            os.environ["CJA_PROFILE"] = "dotenv-profile"

        with (
            patch.dict(os.environ, {}, clear=True),
            patch("cja_auto_sdr.api.client._bootstrap_dotenv", side_effect=_bootstrap_side_effect) as mock_bootstrap,
            patch.object(sys, "argv", test_args),
        ):
            args = parse_arguments()

        assert args.output_dir == "./dotenv-output"
        assert args.log_level == "WARNING"
        assert args.max_retries == 9
        assert args.profile == "dotenv-profile"
        mock_bootstrap.assert_called_once()

    def test_return_parser_mode_skips_dotenv_bootstrap(self):
        """Parser-metadata mode should not trigger dotenv/bootstrap side effects."""
        with patch("cja_auto_sdr.api.client._bootstrap_dotenv") as mock_bootstrap:
            parser = parse_arguments(return_parser=True, enable_autocomplete=False)

        assert isinstance(parser, argparse.ArgumentParser)
        mock_bootstrap.assert_not_called()

    def test_invalid_retry_env_max_retries_falls_back_to_default(self):
        """Invalid MAX_RETRIES env values should not crash argument parsing."""
        from cja_auto_sdr.generator import DEFAULT_RETRY_CONFIG

        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.dict(os.environ, {"MAX_RETRIES": "invalid"}):
            with patch.object(sys, "argv", test_args):
                args = parse_arguments()
                assert args.max_retries == DEFAULT_RETRY_CONFIG["max_retries"]

    def test_invalid_retry_env_base_delay_falls_back_to_default(self):
        """Invalid RETRY_BASE_DELAY env values should fall back cleanly."""
        from cja_auto_sdr.generator import DEFAULT_RETRY_CONFIG

        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.dict(os.environ, {"RETRY_BASE_DELAY": "invalid"}):
            with patch.object(sys, "argv", test_args):
                args = parse_arguments()
                assert args.retry_base_delay == DEFAULT_RETRY_CONFIG["base_delay"]

    def test_invalid_retry_env_max_delay_falls_back_to_default(self):
        """Invalid RETRY_MAX_DELAY env values should fall back cleanly."""
        from cja_auto_sdr.generator import DEFAULT_RETRY_CONFIG

        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.dict(os.environ, {"RETRY_MAX_DELAY": "invalid"}):
            with patch.object(sys, "argv", test_args):
                args = parse_arguments()
                assert args.retry_max_delay == DEFAULT_RETRY_CONFIG["max_delay"]


class TestValidateConfigFlag:
    """Test --validate-config flag"""

    def test_validate_config_flag(self):
        """Test parsing with --validate-config flag"""
        test_args = ["cja_sdr_generator.py", "--validate-config"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.validate_config is True
            assert args.data_views == []

    def test_validate_config_default_false(self):
        """Test that validate-config is False by default"""
        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.validate_config is False

    def test_validate_config_no_dataview_required(self):
        """Test that --validate-config doesn't require data view argument"""
        test_args = ["cja_sdr_generator.py", "--validate-config"]
        with patch.object(sys, "argv", test_args):
            # Should parse without error even though no data view is provided
            args = parse_arguments()
            assert args.validate_config is True


class TestFormatValidation:
    """Test output format validation"""

    def test_format_console_valid_for_diff(self):
        """Test that console format is accepted for diff mode"""
        test_args = ["cja_sdr_generator.py", "--diff", "dv_A", "dv_B", "--format", "console"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.format == "console"
            assert args.diff is True

    def test_format_console_parsed_for_sdr(self):
        """Test that console format is parsed (validation happens at runtime)"""
        test_args = ["cja_sdr_generator.py", "dv_12345", "--format", "console"]
        with patch.object(sys, "argv", test_args):
            # Argparse allows console as a choice, runtime validation catches it
            args = parse_arguments()
            assert args.format == "console"

    def test_format_excel_valid_for_sdr(self):
        """Test that excel format is valid for SDR"""
        test_args = ["cja_sdr_generator.py", "dv_12345", "--format", "excel"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.format == "excel"

    def test_format_all_valid_for_sdr(self):
        """Test that all format is valid for SDR"""
        test_args = ["cja_sdr_generator.py", "dv_12345", "--format", "all"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.format == "all"

    def test_format_json_valid_for_both(self):
        """Test that json format is valid for both SDR and diff"""
        # SDR mode
        test_args = ["cja_sdr_generator.py", "dv_12345", "--format", "json"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.format == "json"

        # Diff mode
        test_args = ["cja_sdr_generator.py", "--diff", "dv_A", "dv_B", "--format", "json"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.format == "json"


class TestListConnectionsArgs:
    """Test --list-connections argument parsing"""

    def test_list_connections_flag(self):
        """Test parsing with --list-connections flag"""
        test_args = ["cja_sdr_generator.py", "--list-connections"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.list_connections is True

    def test_list_connections_default_false(self):
        """Test that list-connections is False by default"""
        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.list_connections is False

    def test_list_connections_with_format(self):
        """Test --list-connections with --format json"""
        test_args = ["cja_sdr_generator.py", "--list-connections", "--format", "json"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.list_connections is True
            assert args.format == "json"

    def test_list_connections_with_csv_output(self):
        """Test --list-connections with --format csv and --output"""
        test_args = ["cja_sdr_generator.py", "--list-connections", "--format", "csv", "--output", "conns.csv"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.list_connections is True
            assert args.format == "csv"
            assert args.output == "conns.csv"

    def test_list_connections_with_discovery_filters(self):
        """Test discovery filter/sort/limit flags parse with list-connections."""
        test_args = [
            "cja_sdr_generator.py",
            "--list-connections",
            "--filter",
            "prod",
            "--exclude",
            "staging",
            "--limit",
            "5",
            "--sort=-name",
        ]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.list_connections is True
            assert args.org_filter == "prod"
            assert args.org_exclude == "staging"
            assert args.org_limit == 5
            assert args.discovery_sort == "-name"


class TestListDatasetsArgs:
    """Test --list-datasets argument parsing"""

    def test_list_datasets_flag(self):
        """Test parsing with --list-datasets flag"""
        test_args = ["cja_sdr_generator.py", "--list-datasets"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.list_datasets is True

    def test_list_datasets_default_false(self):
        """Test that list-datasets is False by default"""
        test_args = ["cja_sdr_generator.py", "dv_12345"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.list_datasets is False

    def test_list_datasets_with_format(self):
        """Test --list-datasets with --format csv"""
        test_args = ["cja_sdr_generator.py", "--list-datasets", "--format", "csv"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.list_datasets is True
            assert args.format == "csv"

    def test_list_datasets_with_profile(self):
        """Test --list-datasets with --profile"""
        test_args = ["cja_sdr_generator.py", "--list-datasets", "--profile", "client-a"]
        with patch.object(sys, "argv", test_args):
            args = parse_arguments()
            assert args.list_datasets is True
            assert args.profile == "client-a"


class TestDiscoveryMutualExclusivity:
    """Test that discovery commands are mutually exclusive"""

    def test_list_dataviews_and_connections_rejected(self):
        """Test that --list-dataviews and --list-connections cannot be combined"""
        test_args = ["cja_sdr_generator.py", "--list-dataviews", "--list-connections"]
        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit):
                parse_arguments()

    def test_list_dataviews_and_datasets_rejected(self):
        """Test that --list-dataviews and --list-datasets cannot be combined"""
        test_args = ["cja_sdr_generator.py", "--list-dataviews", "--list-datasets"]
        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit):
                parse_arguments()

    def test_list_connections_and_datasets_rejected(self):
        """Test that --list-connections and --list-datasets cannot be combined"""
        test_args = ["cja_sdr_generator.py", "--list-connections", "--list-datasets"]
        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit):
                parse_arguments()

    def test_all_three_rejected(self):
        """Test that all three discovery flags cannot be combined"""
        test_args = ["cja_sdr_generator.py", "--list-dataviews", "--list-connections", "--list-datasets"]
        with patch.object(sys, "argv", test_args):
            with pytest.raises(SystemExit):
                parse_arguments()


class TestExtractDatasetInfo:
    """Test _extract_dataset_info() helper"""

    def test_standard_fields(self):
        """Test extraction with standard id/name fields"""
        result = _extract_dataset_info({"id": "ds_123", "name": "Web Events"})
        assert result == {"id": "ds_123", "name": "Web Events"}

    def test_alternate_id_field(self):
        """Test extraction with datasetId field"""
        result = _extract_dataset_info({"datasetId": "ds_456", "name": "Mobile Events"})
        assert result == {"id": "ds_456", "name": "Mobile Events"}

    def test_alternate_name_field_title(self):
        """Test extraction with title field"""
        result = _extract_dataset_info({"id": "ds_789", "title": "Product Catalog"})
        assert result == {"id": "ds_789", "name": "Product Catalog"}

    def test_alternate_name_field_datasetName(self):
        """Test extraction with datasetName field"""
        result = _extract_dataset_info({"id": "ds_111", "datasetName": "Test Dataset"})
        assert result == {"id": "ds_111", "name": "Test Dataset"}

    def test_missing_fields(self):
        """Test extraction with empty dict"""
        result = _extract_dataset_info({})
        assert result == {"id": "N/A", "name": "N/A"}

    def test_non_dict_input(self):
        """Test extraction with non-dict input"""
        result = _extract_dataset_info("ds_string_id")
        assert result == {"id": "ds_string_id", "name": "N/A"}

    def test_none_input(self):
        """Test extraction with None input"""
        result = _extract_dataset_info(None)
        assert result == {"id": "N/A", "name": "N/A"}

    def test_dataSetId_field(self):
        """Test extraction with dataSetId (camelCase) field"""
        result = _extract_dataset_info({"dataSetId": "ds_222", "dataSetName": "Events"})
        assert result == {"id": "ds_222", "name": "Events"}

    def test_snake_case_fields(self):
        """Test extraction with snake_case dataset fields"""
        result = _extract_dataset_info({"dataset_id": "ds_333", "dataset_name": "Legacy Events"})
        assert result == {"id": "ds_333", "name": "Legacy Events"}

    def test_pd_na_fields_fallback_to_na(self):
        """Pandas missing scalars in id/name fields should not raise and should normalize to N/A."""
        import pandas as pd

        result = _extract_dataset_info({"id": pd.NA, "name": pd.NA})
        assert result == {"id": "N/A", "name": "N/A"}

    def test_pd_na_prefers_alternate_fields(self):
        """Missing primary dataset fields should fall back to alternate aliases."""
        import pandas as pd

        result = _extract_dataset_info({"id": pd.NA, "datasetId": "ds_999", "name": pd.NA, "datasetName": "Alt Name"})
        assert result == {"id": "ds_999", "name": "Alt Name"}


class TestListDataviewsFunction:
    """Test list_dataviews() function with mocks"""

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_dataviews_null_owner_shows_na(self, mock_profile, mock_configure, mock_cjapy):
        """Test list_dataviews shows N/A when owner is null (not the string 'None')"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getDataViews.return_value = [{"id": "dv_1", "name": "Test View", "owner": None}]

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_dataviews(output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["dataViews"][0]["owner"] == "N/A"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_dataviews_null_owner_table(self, mock_profile, mock_configure, mock_cjapy):
        """Test list_dataviews table output shows N/A for null owner"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getDataViews.return_value = [{"id": "dv_1", "name": "Test View", "owner": None}]

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_dataviews(output_format="table")

        assert result is True
        output = f.getvalue()
        assert "N/A" in output
        assert "Owner: None" not in output

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_dataviews_owner_dict_with_null_name_shows_na(self, mock_profile, mock_configure, mock_cjapy):
        """Test list_dataviews shows N/A when owner is {'name': None}"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getDataViews.return_value = [{"id": "dv_1", "name": "Test View", "owner": {"name": None}}]

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_dataviews(output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["dataViews"][0]["owner"] == "N/A"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_dataviews_owner_dict_with_null_name_table(self, mock_profile, mock_configure, mock_cjapy):
        """Test list_dataviews table output shows N/A when owner is {'name': None}"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getDataViews.return_value = [{"id": "dv_1", "name": "Test View", "owner": {"name": None}}]

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_dataviews(output_format="table")

        assert result is True
        output = f.getvalue()
        assert "N/A" in output
        assert "None" not in output

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_dataviews_owner_scalar_nan_shows_na(self, mock_profile, mock_configure, mock_cjapy):
        """NaN scalar owner values should normalize to N/A."""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getDataViews.return_value = [{"id": "dv_1", "name": "Test View", "owner": float("nan")}]

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_dataviews(output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["dataViews"][0]["owner"] == "N/A"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_dataviews_owner_dict_pd_na_name_falls_back(self, mock_profile, mock_configure, mock_cjapy):
        """Owner dict fields should skip pd.NA values and fall back to populated aliases."""
        import pandas as pd

        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getDataViews.return_value = [
            {"id": "dv_1", "name": "Test View", "owner": {"name": pd.NA, "email": "owner@example.com"}},
        ]

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_dataviews(output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["dataViews"][0]["owner"] == "owner@example.com"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_dataviews_missing_owner_shows_na(self, mock_profile, mock_configure, mock_cjapy):
        """Test list_dataviews shows N/A when owner key is absent"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getDataViews.return_value = [{"id": "dv_1", "name": "Test View"}]

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_dataviews(output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["dataViews"][0]["owner"] == "N/A"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_dataviews_filter_sort_limit(self, mock_profile, mock_configure, mock_cjapy):
        """Test discovery filter/sort/limit for list_dataviews."""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getDataViews.return_value = [
            {"id": "dv_1", "name": "Prod Alpha", "owner": {"name": "A"}},
            {"id": "dv_2", "name": "Dev Beta", "owner": {"name": "B"}},
            {"id": "dv_3", "name": "Prod Zeta", "owner": {"name": "C"}},
        ]

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_dataviews(
                output_format="json",
                filter_pattern="prod",
                limit=1,
                sort_expression="-id",
            )

        assert result is True
        output = json.loads(f.getvalue())
        assert output["count"] == 1
        assert output["dataViews"][0]["id"] == "dv_3"


class TestListConnectionsFunction:
    """Test list_connections() function with mocks"""

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_connections_json(self, mock_profile, mock_configure, mock_cjapy):
        """Test list_connections with JSON output"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {
            "content": [
                {
                    "id": "conn_123",
                    "name": "Production Connection",
                    "ownerFullName": "John Doe",
                    "dataSets": [{"id": "ds_456", "name": "Web Events"}, {"id": "ds_789", "name": "Mobile Events"}],
                },
            ],
        }

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_connections(output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["count"] == 1
        assert output["connections"][0]["id"] == "conn_123"
        assert len(output["connections"][0]["datasets"]) == 2

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_connections_filter_exclude(self, mock_profile, mock_configure, mock_cjapy):
        """Test discovery filter/exclude for list_connections."""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {
            "content": [
                {"id": "conn_1", "name": "Prod Connection", "ownerFullName": "Owner A", "dataSets": []},
                {"id": "conn_2", "name": "Staging Connection", "ownerFullName": "Owner B", "dataSets": []},
            ],
        }

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_connections(
                output_format="json",
                filter_pattern="connection",
                exclude_pattern="staging",
            )

        assert result is True
        output = json.loads(f.getvalue())
        assert output["count"] == 1
        assert output["connections"][0]["id"] == "conn_1"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_connections_empty(self, mock_profile, mock_configure, mock_cjapy):
        """Test list_connections with no connections and no data views"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {"content": []}
        mock_cja_instance.getDataViews.return_value = []

        result = list_connections(output_format="table")
        assert result is True

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_connections_empty_json_prints_stdout(self, mock_profile, mock_configure, mock_cjapy):
        """Test list_connections prints empty JSON payload to stdout when genuinely empty"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {"content": []}
        mock_cja_instance.getDataViews.return_value = []

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_connections(output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output == {"connections": [], "count": 0}

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_connections_empty_csv_prints_stdout(self, mock_profile, mock_configure, mock_cjapy):
        """Test list_connections prints empty CSV payload to stdout when genuinely empty"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {"content": []}
        mock_cja_instance.getDataViews.return_value = []

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_connections(output_format="csv")

        assert result is True
        assert f.getvalue() == "connection_id,connection_name,owner,dataset_id,dataset_name\n"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_connections_csv(self, mock_profile, mock_configure, mock_cjapy):
        """Test list_connections with CSV output"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {
            "content": [
                {
                    "id": "conn_1",
                    "name": "Test Conn",
                    "ownerFullName": "Owner",
                    "dataSets": [{"id": "ds_1", "name": "Dataset One"}],
                },
            ],
        }

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_connections(output_format="csv")

        assert result is True
        lines = f.getvalue().strip().split("\n")
        assert lines[0] == "connection_id,connection_name,owner,dataset_id,dataset_name"
        assert "conn_1" in lines[1]
        assert "ds_1" in lines[1]

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_connections_null_owner_shows_na(self, mock_profile, mock_configure, mock_cjapy):
        """Test list_connections shows N/A when ownerFullName is null (not the string 'None')"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {
            "content": [
                {
                    "id": "conn_1",
                    "name": "Test Conn",
                    "ownerFullName": None,
                    "dataSets": [{"id": "ds_1", "name": "Dataset One"}],
                },
            ],
        }

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_connections(output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["connections"][0]["owner"] == "N/A"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_connections_pd_na_owner_full_name_falls_back_to_owner(
        self,
        mock_profile,
        mock_configure,
        mock_cjapy,
    ):
        """pd.NA ownerFullName should not error and should fall back to owner object aliases."""
        import pandas as pd

        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {
            "content": [
                {
                    "id": "conn_1",
                    "name": "Test Conn",
                    "ownerFullName": pd.NA,
                    "owner": {"name": "Fallback Owner"},
                    "dataSets": [],
                },
            ],
        }

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_connections(output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["connections"][0]["owner"] == "Fallback Owner"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_connections_null_owner_table(self, mock_profile, mock_configure, mock_cjapy):
        """Test list_connections table output shows N/A for null ownerFullName"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {
            "content": [{"id": "conn_1", "name": "Test Conn", "ownerFullName": None, "dataSets": []}],
        }

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_connections(output_format="table")

        assert result is True
        output = f.getvalue()
        assert "Owner: N/A" in output
        assert "Owner: None" not in output

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_connections_missing_owner_shows_na(self, mock_profile, mock_configure, mock_cjapy):
        """Test list_connections shows N/A when owner key is absent"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {
            "content": [{"id": "conn_1", "name": "Test Conn", "dataSets": []}],
        }

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_connections(output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["connections"][0]["owner"] == "N/A"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_connections_owner_dict_with_null_name_shows_na(self, mock_profile, mock_configure, mock_cjapy):
        """Test list_connections shows N/A when ownerFullName is empty string"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {
            "content": [
                {
                    "id": "conn_1",
                    "name": "Test Conn",
                    "ownerFullName": "",
                    "dataSets": [{"id": "ds_1", "name": "Dataset One"}],
                },
            ],
        }

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_connections(output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["connections"][0]["owner"] == "N/A"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_connections_owner_dict_with_null_name_table(self, mock_profile, mock_configure, mock_cjapy):
        """Test list_connections table output shows N/A when ownerFullName is empty"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {
            "content": [{"id": "conn_1", "name": "Test Conn", "ownerFullName": "", "dataSets": []}],
        }

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_connections(output_format="table")

        assert result is True
        output = f.getvalue()
        assert "Owner: N/A" in output
        assert "Owner: None" not in output

    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_connections_config_failure(self, mock_profile, mock_configure):
        """Test list_connections when configuration fails"""
        mock_configure.return_value = (False, "Missing credentials", None)

        import io
        from contextlib import redirect_stderr

        f = io.StringIO()
        with redirect_stderr(f):
            result = list_connections(output_format="json")

        assert result is False
        error = json.loads(f.getvalue())
        assert error == {
            "error": "Configuration error: Missing credentials",
            "error_type": "configuration_error",
        }

    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_connections_config_failure_csv_emits_json_error(self, mock_profile, mock_configure):
        """Test list_connections emits machine-readable error in CSV mode on config failure"""
        mock_configure.return_value = (False, "Missing credentials", None)

        import io
        from contextlib import redirect_stderr

        f = io.StringIO()
        with redirect_stderr(f):
            result = list_connections(output_format="csv")

        assert result is False
        error = json.loads(f.getvalue())
        assert error == {
            "error": "Configuration error: Missing credentials",
            "error_type": "configuration_error",
        }


class TestListDatasetsFunction:
    """Test list_datasets() function with mocks"""

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_datasets_json(self, mock_profile, mock_configure, mock_cjapy):
        """Test list_datasets with JSON output"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {
            "content": [
                {
                    "id": "conn_456",
                    "name": "Production Connection",
                    "dataSets": [{"id": "ds_789", "name": "Web Events"}],
                },
            ],
        }
        mock_cja_instance.getDataViews.return_value = [
            {"id": "dv_123", "name": "Web Data View", "parentDataGroupId": "conn_456"},
        ]

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_datasets(output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["count"] == 1
        assert output["dataViews"][0]["connection"]["id"] == "conn_456"
        assert len(output["dataViews"][0]["datasets"]) == 1
        mock_cja_instance.getDataView.assert_not_called()

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_datasets_filter_and_limit(self, mock_profile, mock_configure, mock_cjapy):
        """Test discovery filter and limit for list_datasets."""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {"content": []}
        mock_cja_instance.getDataViews.return_value = [
            {"id": "dv_1", "name": "Prod Main", "parentDataGroupId": "conn_1"},
            {"id": "dv_2", "name": "Prod Secondary", "parentDataGroupId": "conn_2"},
            {"id": "dv_3", "name": "Dev Sandbox", "parentDataGroupId": "conn_3"},
        ]

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_datasets(
                output_format="json",
                filter_pattern="prod",
                limit=1,
                sort_expression="name",
            )

        assert result is True
        output = json.loads(f.getvalue())
        assert output["count"] == 1
        assert output["dataViews"][0]["id"] == "dv_1"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_datasets_unknown_connection(self, mock_profile, mock_configure, mock_cjapy):
        """Test list_datasets when data view has no parentDataGroupId"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {"content": []}
        mock_cja_instance.getDataViews.return_value = [{"id": "dv_orphan", "name": "Orphan View"}]

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_datasets(output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["dataViews"][0]["connection"]["name"] is None
        assert output["dataViews"][0]["connection"]["id"] == "N/A"
        mock_cja_instance.getDataView.assert_not_called()

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_datasets_nan_parent_connection_id_json(self, mock_profile, mock_configure, mock_cjapy):
        """Test list_datasets normalizes NaN parentDataGroupId in JSON output"""
        import pandas as pd

        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {"content": []}
        mock_cja_instance.getDataViews.return_value = pd.DataFrame(
            [{"id": "dv_orphan_nan", "name": "Orphan NaN", "parentDataGroupId": float("nan")}],
        )

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_datasets(output_format="json")

        assert result is True
        output_text = f.getvalue()
        assert '"id": NaN' not in output_text
        output = json.loads(output_text)
        assert output["dataViews"][0]["connection"]["id"] == "N/A"
        mock_cja_instance.getDataView.assert_not_called()

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_datasets_csv(self, mock_profile, mock_configure, mock_cjapy):
        """Test list_datasets with CSV output"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {
            "content": [{"id": "conn_1", "name": "Conn One", "dataSets": [{"id": "ds_1", "name": "Dataset"}]}],
        }
        mock_cja_instance.getDataViews.return_value = [
            {"id": "dv_1", "name": "View One", "parentDataGroupId": "conn_1"},
        ]

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_datasets(output_format="csv")

        assert result is True
        lines = f.getvalue().strip().split("\n")
        assert lines[0] == "dataview_id,dataview_name,connection_id,connection_name,dataset_id,dataset_name"
        assert "dv_1" in lines[1]
        assert "conn_1" in lines[1]
        assert "ds_1" in lines[1]
        mock_cja_instance.getDataView.assert_not_called()

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_datasets_empty_dataviews(self, mock_profile, mock_configure, mock_cjapy):
        """Test list_datasets with no data views"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {"content": []}
        mock_cja_instance.getDataViews.return_value = []

        result = list_datasets(output_format="table")
        assert result is True

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_datasets_empty_json_prints_stdout(self, mock_profile, mock_configure, mock_cjapy):
        """Test list_datasets prints empty JSON payload to stdout"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {"content": []}
        mock_cja_instance.getDataViews.return_value = []

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_datasets(output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output == {"dataViews": [], "count": 0}
        mock_cja_instance.getDataView.assert_not_called()

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_datasets_empty_csv_prints_stdout(self, mock_profile, mock_configure, mock_cjapy):
        """Test list_datasets prints empty CSV payload to stdout"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {"content": []}
        mock_cja_instance.getDataViews.return_value = []

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_datasets(output_format="csv")

        assert result is True
        assert f.getvalue() == "dataview_id,dataview_name,connection_id,connection_name,dataset_id,dataset_name\n"
        mock_cja_instance.getDataView.assert_not_called()

    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_datasets_config_failure_json_emits_json_error(self, mock_profile, mock_configure):
        """Test list_datasets emits machine-readable error in JSON mode on config failure"""
        mock_configure.return_value = (False, "Missing credentials", None)

        import io
        from contextlib import redirect_stderr

        f = io.StringIO()
        with redirect_stderr(f):
            result = list_datasets(output_format="json")

        assert result is False
        error = json.loads(f.getvalue())
        assert error == {
            "error": "Configuration error: Missing credentials",
            "error_type": "configuration_error",
        }

    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_datasets_config_failure_csv_emits_json_error(self, mock_profile, mock_configure):
        """Test list_datasets emits machine-readable error in CSV mode on config failure"""
        mock_configure.return_value = (False, "Missing credentials", None)

        import io
        from contextlib import redirect_stderr

        f = io.StringIO()
        with redirect_stderr(f):
            result = list_datasets(output_format="csv")

        assert result is False
        error = json.loads(f.getvalue())
        assert error == {
            "error": "Configuration error: Missing credentials",
            "error_type": "configuration_error",
        }


class TestDiscoveryArgumentValidation:
    """Validate discovery argument errors are handled as local input failures."""

    @pytest.mark.parametrize("list_fn", [list_dataviews, list_connections, list_datasets])
    def test_invalid_regex_reports_invalid_arguments_json(self, list_fn):
        """Invalid --filter regex should not be mislabeled as an API connectivity failure."""
        import io
        from contextlib import redirect_stderr

        with (
            patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None),
            patch("cja_auto_sdr.generator.configure_cjapy") as mock_configure,
        ):
            f = io.StringIO()
            with redirect_stderr(f):
                result = list_fn(output_format="json", filter_pattern="[invalid")

        assert result is False
        payload = json.loads(f.getvalue())
        assert payload["error_type"] == "invalid_arguments"
        assert payload["error"].startswith("Invalid --filter regex")
        assert "Failed to connect to CJA API" not in payload["error"]
        mock_configure.assert_not_called()

    @pytest.mark.parametrize("list_fn", [list_dataviews, list_connections, list_datasets])
    def test_negative_limit_reports_invalid_arguments_json(self, list_fn):
        """Negative --limit should fail fast as invalid input before any API/config call."""
        import io
        from contextlib import redirect_stderr

        with (
            patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None),
            patch("cja_auto_sdr.generator.configure_cjapy") as mock_configure,
        ):
            f = io.StringIO()
            with redirect_stderr(f):
                result = list_fn(output_format="json", limit=-1)

        assert result is False
        payload = json.loads(f.getvalue())
        assert payload == {"error": "--limit cannot be negative", "error_type": "invalid_arguments"}
        mock_configure.assert_not_called()

    @pytest.mark.parametrize("list_fn", [list_dataviews, list_connections, list_datasets])
    @pytest.mark.parametrize(
        ("scenario", "call_kwargs", "expected_error_type"),
        [
            ("invalid_regex", {"filter_pattern": "[invalid"}, "invalid_arguments"),
            ("config_failure", {}, "configuration_error"),
            ("file_not_found", {}, "configuration_error"),
            ("connectivity_failure", {}, "connectivity_error"),
        ],
    )
    def test_machine_readable_error_envelope_schema(self, list_fn, scenario, call_kwargs, expected_error_type):
        """Discovery machine-readable failures should always emit error + error_type."""
        import io
        from contextlib import redirect_stderr

        with (
            patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None),
            patch("cja_auto_sdr.generator.configure_cjapy") as mock_configure,
            patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
        ):
            # Configure mocks per scenario so each parametrized path can assert
            # the same machine-readable envelope contract.
            if scenario == "config_failure":
                mock_configure.return_value = (False, "Missing credentials", None)
            elif scenario == "file_not_found":
                mock_configure.side_effect = FileNotFoundError("missing")
            elif scenario == "connectivity_failure":
                mock_configure.return_value = (True, "config", None)
                mock_cjapy.CJA.side_effect = RuntimeError("boom")

            f = io.StringIO()
            with redirect_stderr(f):
                result = list_fn(output_format="json", **call_kwargs)

        assert result is False
        payload = json.loads(f.getvalue())
        assert {"error", "error_type"}.issubset(payload)
        assert payload["error_type"] == expected_error_type
        assert payload["error"]
        if scenario == "invalid_regex":
            mock_configure.assert_not_called()

    def test_invalid_regex_reports_local_error_in_table_mode(self):
        """Table-mode errors should still be classified as local argument issues."""
        import io
        from contextlib import redirect_stdout

        with (
            patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None),
            patch("cja_auto_sdr.generator.configure_cjapy") as mock_configure,
        ):
            f = io.StringIO()
            with redirect_stdout(f):
                result = list_dataviews(output_format="table", filter_pattern="[invalid")

        assert result is False
        output = f.getvalue()
        assert "ERROR: Invalid --filter regex" in output
        assert "Failed to connect to CJA API" not in output
        mock_configure.assert_not_called()


class TestFileOutput:
    """Test that list commands write output to disk via --output."""

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_connections_json_file(self, mock_profile, mock_configure, mock_cjapy, tmp_path):
        """Test list_connections writes JSON to a file via --output"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {
            "content": [
                {
                    "id": "conn_1",
                    "name": "Test Conn",
                    "ownerFullName": "Owner",
                    "dataSets": [{"id": "ds_1", "name": "Dataset One"}],
                },
            ],
        }

        out_file = str(tmp_path / "connections.json")
        result = list_connections(output_format="json", output_file=out_file)

        assert result is True
        with open(out_file) as f:
            output = json.load(f)
        assert output["count"] == 1
        assert output["connections"][0]["id"] == "conn_1"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_connections_csv_file(self, mock_profile, mock_configure, mock_cjapy, tmp_path):
        """Test list_connections writes CSV to a file via --output"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {
            "content": [
                {
                    "id": "conn_1",
                    "name": "Test Conn",
                    "ownerFullName": "Owner",
                    "dataSets": [{"id": "ds_1", "name": "Dataset One"}],
                },
            ],
        }

        out_file = str(tmp_path / "connections.csv")
        result = list_connections(output_format="csv", output_file=out_file)

        assert result is True
        with open(out_file) as f:
            content = f.read()
        lines = content.strip().split("\n")
        assert lines[0] == "connection_id,connection_name,owner,dataset_id,dataset_name"
        assert "conn_1" in lines[1]

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_datasets_json_file(self, mock_profile, mock_configure, mock_cjapy, tmp_path):
        """Test list_datasets writes JSON to a file via --output"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {
            "content": [{"id": "conn_1", "name": "Conn One", "dataSets": [{"id": "ds_1", "name": "Dataset"}]}],
        }
        mock_cja_instance.getDataViews.return_value = [
            {"id": "dv_1", "name": "View One", "parentDataGroupId": "conn_1"},
        ]

        out_file = str(tmp_path / "datasets.json")
        result = list_datasets(output_format="json", output_file=out_file)

        assert result is True
        with open(out_file) as f:
            output = json.load(f)
        assert output["count"] == 1
        assert output["dataViews"][0]["connection"]["id"] == "conn_1"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_dataviews_json_file(self, mock_profile, mock_configure, mock_cjapy, tmp_path):
        """Test list_dataviews writes JSON to a file via --output"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getDataViews.return_value = [
            {"id": "dv_1", "name": "My View", "owner": {"name": "Test User"}},
        ]

        out_file = str(tmp_path / "dataviews.json")
        result = list_dataviews(output_format="json", output_file=out_file)

        assert result is True
        with open(out_file) as f:
            output = json.load(f)
        assert output["count"] == 1
        assert output["dataViews"][0]["id"] == "dv_1"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_connections_table_file(self, mock_profile, mock_configure, mock_cjapy, tmp_path):
        """Test list_connections writes table output to a file via --output"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {
            "content": [
                {
                    "id": "conn_1",
                    "name": "Test Conn",
                    "ownerFullName": "Owner",
                    "dataSets": [{"id": "ds_1", "name": "Dataset One"}],
                },
            ],
        }

        out_file = str(tmp_path / "connections.txt")
        result = list_connections(output_format="table", output_file=out_file)

        assert result is True
        with open(out_file) as f:
            content = f.read()
        assert "conn_1" in content
        assert "Test Conn" in content

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_connections_creates_parent_dirs(self, mock_profile, mock_configure, mock_cjapy, tmp_path):
        """Test that --output creates parent directories if needed"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {
            "content": [{"id": "conn_1", "name": "Test", "ownerFullName": "Owner", "dataSets": []}],
        }

        out_file = str(tmp_path / "subdir" / "nested" / "connections.json")
        result = list_connections(output_format="json", output_file=out_file)

        assert result is True
        with open(out_file) as f:
            output = json.load(f)
        assert output["count"] == 1

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_datasets_csv_file(self, mock_profile, mock_configure, mock_cjapy, tmp_path):
        """Test list_datasets writes CSV (6-column join) to a file via --output"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {
            "content": [
                {
                    "id": "conn_1",
                    "name": "Conn One",
                    "dataSets": [{"id": "ds_1", "name": "Dataset A"}, {"id": "ds_2", "name": "Dataset B"}],
                },
            ],
        }
        mock_cja_instance.getDataViews.return_value = [
            {"id": "dv_1", "name": "View One", "parentDataGroupId": "conn_1"},
        ]

        out_file = str(tmp_path / "datasets.csv")
        result = list_datasets(output_format="csv", output_file=out_file)

        assert result is True
        with open(out_file) as f:
            content = f.read()
        lines = content.strip().split("\n")
        assert lines[0] == "dataview_id,dataview_name,connection_id,connection_name,dataset_id,dataset_name"
        # One row per dataset (2 datasets under the same data view)
        assert len(lines) == 3
        assert "ds_1" in lines[1]
        assert "ds_2" in lines[2]
        assert "dv_1" in lines[1]
        assert "conn_1" in lines[1]


class TestEmitOutputPager:
    """Test _emit_output auto-pager behaviour for long console output."""

    def test_uses_pager_when_output_exceeds_terminal(self):
        """Test that _emit_output invokes a pager when output is taller than terminal"""
        long_text = "\n".join(f"line {i}" for i in range(200))
        mock_proc = MagicMock()
        mock_proc.communicate = MagicMock()

        with (
            patch("sys.stdout") as mock_stdout,
            patch("os.get_terminal_size", return_value=os.terminal_size((80, 24))),
            patch.dict(os.environ, {"PAGER": "less"}),
            patch("shutil.which", return_value="/usr/bin/less"),
            patch("subprocess.Popen", return_value=mock_proc) as mock_popen,
        ):
            mock_stdout.isatty.return_value = True
            _emit_output(long_text, None, False)

        mock_popen.assert_called_once_with(["less", "-R"], stdin=subprocess.PIPE)
        mock_proc.communicate.assert_called_once_with(long_text.rstrip("\n").encode("utf-8"), timeout=300)

    def test_no_pager_when_output_fits_terminal(self):
        """Test that _emit_output prints normally when output fits in terminal"""
        short_text = "\n".join(f"line {i}" for i in range(5))

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()

        with patch("os.get_terminal_size", return_value=os.terminal_size((80, 24))), redirect_stdout(f):
            _emit_output(short_text, None, False)

        assert "line 0" in f.getvalue()
        assert "line 4" in f.getvalue()

    def test_no_pager_when_not_tty(self):
        """Test that _emit_output does not page when stdout is not a TTY (piped)"""
        long_text = "\n".join(f"line {i}" for i in range(200))

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()

        with redirect_stdout(f):
            # StringIO.isatty() returns False, so no pager should be used
            _emit_output(long_text, None, False)

        assert "line 0" in f.getvalue()
        assert "line 199" in f.getvalue()

    def test_no_pager_for_stdout_pipe_mode(self):
        """Test that _emit_output does not page when is_stdout=True (--output -)"""
        long_text = "\n".join(f"line {i}" for i in range(200))

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()

        with redirect_stdout(f):
            _emit_output(long_text, None, True)

        assert "line 0" in f.getvalue()

    def test_pager_respects_PAGER_env(self):
        """Test that _emit_output uses $PAGER when set"""
        long_text = "\n".join(f"line {i}" for i in range(200))
        mock_proc = MagicMock()
        mock_proc.communicate = MagicMock()

        with (
            patch("sys.stdout") as mock_stdout,
            patch("os.get_terminal_size", return_value=os.terminal_size((80, 24))),
            patch.dict(os.environ, {"PAGER": "more"}),
            patch("shutil.which", return_value="/usr/bin/more"),
            patch("subprocess.Popen", return_value=mock_proc) as mock_popen,
        ):
            mock_stdout.isatty.return_value = True
            _emit_output(long_text, None, False)

        mock_popen.assert_called_once_with(["more"], stdin=subprocess.PIPE)

    def test_pager_supports_pager_args(self):
        """Test that _emit_output parses PAGER values that include command arguments."""
        long_text = "\n".join(f"line {i}" for i in range(200))
        mock_proc = MagicMock()
        mock_proc.communicate = MagicMock()

        with (
            patch("sys.stdout") as mock_stdout,
            patch("os.get_terminal_size", return_value=os.terminal_size((80, 24))),
            patch.dict(os.environ, {"PAGER": "less -F -X"}),
            patch("shutil.which", return_value="/usr/bin/less"),
            patch("subprocess.Popen", return_value=mock_proc) as mock_popen,
        ):
            mock_stdout.isatty.return_value = True
            _emit_output(long_text, None, False)

        mock_popen.assert_called_once_with(["less", "-F", "-X", "-R"], stdin=subprocess.PIPE)

    def test_pager_does_not_duplicate_less_R_flag(self):
        """If PAGER already includes -R, _emit_output should not append another one."""
        long_text = "\n".join(f"line {i}" for i in range(200))
        mock_proc = MagicMock()
        mock_proc.communicate = MagicMock()

        with (
            patch("sys.stdout") as mock_stdout,
            patch("os.get_terminal_size", return_value=os.terminal_size((80, 24))),
            patch.dict(os.environ, {"PAGER": "less -R -F"}),
            patch("shutil.which", return_value="/usr/bin/less"),
            patch("subprocess.Popen", return_value=mock_proc) as mock_popen,
        ):
            mock_stdout.isatty.return_value = True
            _emit_output(long_text, None, False)

        mock_popen.assert_called_once_with(["less", "-R", "-F"], stdin=subprocess.PIPE)

    def test_pager_malformed_env_falls_back_to_less(self):
        """Malformed PAGER values should fall back to less -R."""
        long_text = "\n".join(f"line {i}" for i in range(200))
        mock_proc = MagicMock()
        mock_proc.communicate = MagicMock()

        with (
            patch("sys.stdout") as mock_stdout,
            patch("os.get_terminal_size", return_value=os.terminal_size((80, 24))),
            patch.dict(os.environ, {"PAGER": '"'}),
            patch("shutil.which", return_value="/usr/bin/less"),
            patch("subprocess.Popen", return_value=mock_proc) as mock_popen,
        ):
            mock_stdout.isatty.return_value = True
            _emit_output(long_text, None, False)

        mock_popen.assert_called_once_with(["less", "-R"], stdin=subprocess.PIPE)

    def test_pager_empty_env_falls_back_to_less(self):
        """Empty $PAGER should fall back to less -R."""
        long_text = "\n".join(f"line {i}" for i in range(200))
        mock_proc = MagicMock()
        mock_proc.communicate = MagicMock()

        with (
            patch("sys.stdout") as mock_stdout,
            patch("os.get_terminal_size", return_value=os.terminal_size((80, 24))),
            patch.dict(os.environ, {"PAGER": ""}),
            patch("shutil.which", return_value="/usr/bin/less"),
            patch("subprocess.Popen", return_value=mock_proc) as mock_popen,
        ):
            mock_stdout.isatty.return_value = True
            _emit_output(long_text, None, False)

        mock_popen.assert_called_once_with(["less", "-R"], stdin=subprocess.PIPE)

    def test_pager_fallback_on_error(self):
        """Test that _emit_output falls back to print when pager is unavailable"""
        long_text = "\n".join(f"line {i}" for i in range(200))

        with (
            patch("sys.stdout") as mock_stdout,
            patch("os.get_terminal_size", return_value=os.terminal_size((80, 24))),
            patch("shutil.which", return_value="/usr/bin/less"),
            patch("subprocess.Popen", side_effect=FileNotFoundError),
        ):
            mock_stdout.isatty.return_value = True
            # When pager fails, should fall through to print() — we need
            # to verify it doesn't raise.  Since stdout is mocked, check
            # that write was called as a fallback.
            _emit_output(long_text, None, False)
            mock_stdout.write.assert_called()


class TestConnectionsPermissionsFallback:
    """Test fallback behaviour when getConnections returns empty due to missing admin privileges."""

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_connections_fallback_from_dataviews(self, mock_profile, mock_configure, mock_cjapy):
        """getConnections empty + data views with parentDataGroupId → derived IDs + warning"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {"content": []}
        mock_cja_instance.getDataViews.return_value = [
            {"id": "dv_1", "name": "View A", "parentDataGroupId": "dg_abc"},
            {"id": "dv_2", "name": "View B", "parentDataGroupId": "dg_abc"},
            {"id": "dv_3", "name": "View C", "parentDataGroupId": "dg_xyz"},
        ]

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_connections(output_format="table")

        assert result is True
        output = f.getvalue()
        assert "product-admin" in output.lower() or "product-admin" in output
        assert "dg_abc" in output
        assert "dg_xyz" in output
        assert "2 data view(s)" in output  # dg_abc has 2
        assert "1 data view(s)" in output  # dg_xyz has 1

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_connections_fallback_json(self, mock_profile, mock_configure, mock_cjapy):
        """getConnections empty + data views → JSON includes warning and derived connections"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {"content": []}
        mock_cja_instance.getDataViews.return_value = [
            {"id": "dv_1", "name": "View A", "parentDataGroupId": "dg_abc"},
            {"id": "dv_2", "name": "View B", "parentDataGroupId": "dg_xyz"},
        ]

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_connections(output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert "warning" in output
        assert output["count"] == 2
        ids = [c["id"] for c in output["connections"]]
        assert "dg_abc" in ids
        assert "dg_xyz" in ids
        # name should be null for derived connections
        for conn in output["connections"]:
            assert conn["name"] is None

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_connections_fallback_csv(self, mock_profile, mock_configure, mock_cjapy):
        """getConnections empty + data views → CSV includes derived connections with dataview_count"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {"content": []}
        mock_cja_instance.getDataViews.return_value = [
            {"id": "dv_1", "name": "View A", "parentDataGroupId": "dg_abc"},
        ]

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_connections(output_format="csv")

        assert result is True
        lines = f.getvalue().strip().split("\n")
        assert "dataview_count" in lines[0]
        assert "dg_abc" in lines[1]

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_connections_fallback_sort_numeric_ascending(self, mock_profile, mock_configure, mock_cjapy):
        """Derived connection sorting by dataview_count should be numeric ascending, not lexicographic."""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {"content": []}
        mock_cja_instance.getDataViews.return_value = [
            *[{"id": f"dv_big_{i}", "name": "Big", "parentDataGroupId": "dg_big"} for i in range(10)],
            {"id": "dv_small_1", "name": "Small", "parentDataGroupId": "dg_small"},
            {"id": "dv_small_2", "name": "Small", "parentDataGroupId": "dg_small"},
        ]

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_connections(output_format="json", sort_expression="dataview_count")

        assert result is True
        output = json.loads(f.getvalue())
        sorted_ids = [c["id"] for c in output["connections"]]
        assert sorted_ids == ["dg_small", "dg_big"]
        sorted_counts = [c["dataview_count"] for c in output["connections"]]
        assert sorted_counts == [2, 10]

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_connections_fallback_sort_numeric_descending(self, mock_profile, mock_configure, mock_cjapy):
        """Derived connection sorting by dataview_count should be numeric descending with --sort -dataview_count."""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {"content": []}
        mock_cja_instance.getDataViews.return_value = [
            *[{"id": f"dv_big_{i}", "name": "Big", "parentDataGroupId": "dg_big"} for i in range(10)],
            {"id": "dv_small_1", "name": "Small", "parentDataGroupId": "dg_small"},
            {"id": "dv_small_2", "name": "Small", "parentDataGroupId": "dg_small"},
        ]

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_connections(output_format="json", sort_expression="-dataview_count")

        assert result is True
        output = json.loads(f.getvalue())
        sorted_ids = [c["id"] for c in output["connections"]]
        assert sorted_ids == ["dg_big", "dg_small"]
        sorted_counts = [c["dataview_count"] for c in output["connections"]]
        assert sorted_counts == [10, 2]


class TestDatasetsPermissionsFallback:
    """Test list_datasets behaviour when connection details are unavailable."""

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_datasets_no_connection_details_table(self, mock_profile, mock_configure, mock_cjapy):
        """conn_map empty + data views with parentDataGroupId → show ID without 'Unknown'"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {"content": []}
        mock_cja_instance.getDataViews.return_value = [
            {"id": "dv_1", "name": "View A", "parentDataGroupId": "dg_abc"},
        ]

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_datasets(output_format="table")

        assert result is True
        output = f.getvalue()
        assert "Connection: dg_abc" in output
        assert "Unknown" not in output
        assert "Datasets: (none)" not in output
        assert "product-admin" in output.lower() or "product-admin" in output

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_datasets_no_connection_details_json(self, mock_profile, mock_configure, mock_cjapy):
        """conn_map empty + data views with parentDataGroupId → JSON uses null for connection_name"""
        mock_configure.return_value = (True, "config", None)
        mock_cja_instance = mock_cjapy.CJA.return_value
        mock_cja_instance.getConnections.return_value = {"content": []}
        mock_cja_instance.getDataViews.return_value = [
            {"id": "dv_1", "name": "View A", "parentDataGroupId": "dg_abc"},
        ]

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_datasets(output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert "warning" in output
        assert output["dataViews"][0]["connection"]["name"] is None
        assert output["dataViews"][0]["connection"]["id"] == "dg_abc"
        assert output["dataViews"][0]["datasets"] == []


class TestRunSummaryOutput:
    """Tests for --run-summary-json output."""

    @staticmethod
    def _assert_run_summary_schema(payload):
        """Validate run summary payload contract used by automation."""
        required_keys = {
            "summary_version",
            "tool_version",
            "started_at",
            "ended_at",
            "duration_seconds",
            "exit_code",
            "status",
            "mode",
            "profile",
            "config_file",
            "output_format",
            "allow_partial",
            "command",
            "inputs",
            "results",
            "result_counts",
            "failure_rollups",
            "quality_gate_failed",
            "quality_policy",
            "details",
        }
        assert required_keys.issubset(payload)
        assert payload["summary_version"] == "1.1"
        assert isinstance(payload["tool_version"], str)
        assert isinstance(payload["started_at"], str)
        assert isinstance(payload["ended_at"], str)
        assert isinstance(payload["duration_seconds"], (int, float))
        assert isinstance(payload["exit_code"], int)
        assert payload["status"] in {"success", "error", "policy_exit"}
        assert isinstance(payload["mode"], str)
        assert payload["profile"] is None or isinstance(payload["profile"], str)
        assert payload["config_file"] is None or isinstance(payload["config_file"], str)
        assert payload["output_format"] is None or isinstance(payload["output_format"], str)
        assert isinstance(payload["allow_partial"], bool)

        command = payload["command"]
        assert isinstance(command, dict)
        assert isinstance(command.get("argv"), list)
        assert all(isinstance(arg, str) for arg in command["argv"])
        assert isinstance(command.get("cwd"), str)

        inputs = payload["inputs"]
        assert isinstance(inputs, dict)
        assert isinstance(inputs.get("data_view_inputs"), list)
        assert isinstance(inputs.get("resolved_data_views"), list)

        result_counts = payload["result_counts"]
        assert isinstance(result_counts, dict)
        assert isinstance(result_counts.get("total"), int)
        assert isinstance(result_counts.get("successful"), int)
        assert isinstance(result_counts.get("failed"), int)
        assert isinstance(result_counts.get("quality_issues"), int)
        assert result_counts["total"] == result_counts["successful"] + result_counts["failed"]

        assert isinstance(payload["results"], list)
        result_required_keys = {
            "data_view_id",
            "data_view_name",
            "success",
            "duration_seconds",
            "metrics_count",
            "dimensions_count",
            "dq_issues_count",
            "dq_severity_counts",
            "output_file",
            "output_files",
            "error_message",
            "failure_code",
            "failure_reason",
            "partial_output",
            "partial_reasons",
            "file_size_bytes",
            "segments_count",
            "segments_high_complexity",
            "calculated_metrics_count",
            "calculated_metrics_high_complexity",
            "derived_fields_count",
            "derived_fields_high_complexity",
        }
        for result in payload["results"]:
            assert isinstance(result, dict)
            assert result_required_keys.issubset(result)
            assert isinstance(result["data_view_id"], str)
            assert isinstance(result["data_view_name"], str)
            assert isinstance(result["success"], bool)
            assert isinstance(result["duration_seconds"], (int, float))
            assert isinstance(result["dq_severity_counts"], dict)
            assert isinstance(result["output_file"], str)
            assert isinstance(result["output_files"], list)
            assert all(isinstance(path, str) for path in result["output_files"])
            assert isinstance(result["failure_code"], str)
            assert isinstance(result["failure_reason"], str)
            assert isinstance(result["partial_output"], bool)
            assert isinstance(result["partial_reasons"], list)
            assert all(isinstance(reason, str) for reason in result["partial_reasons"])

        failure_rollups = payload["failure_rollups"]
        assert isinstance(failure_rollups, dict)
        assert isinstance(failure_rollups.get("by_code"), dict)
        assert isinstance(failure_rollups.get("by_reason"), dict)

        assert isinstance(payload["quality_gate_failed"], bool)

        quality_policy = payload["quality_policy"]
        if quality_policy is not None:
            assert isinstance(quality_policy, dict)
            assert isinstance(quality_policy.get("path"), str)
            assert isinstance(quality_policy.get("applied"), dict)

        assert isinstance(payload["details"], dict)

    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_run_summary_written_for_sdr_success(self, mock_resolve, mock_process, tmp_path):
        """Successful SDR run should write run summary with result details."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_test"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=True,
            duration=0.25,
            metrics_count=10,
            dimensions_count=12,
            dq_issues_count=0,
            dq_issues=[],
            dq_severity_counts={},
            output_file="report.xlsx",
            file_size_bytes=2048,
        )

        summary_file = tmp_path / "run_summary.json"
        with patch.object(sys, "argv", ["cja_auto_sdr", "dv_test", "--run-summary-json", str(summary_file)]):
            main()

        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "sdr"
        assert payload["exit_code"] == 0
        assert payload["output_format"] == "excel"
        assert payload["result_counts"]["total"] == 1
        assert payload["result_counts"]["successful"] == 1
        assert payload["results"][0]["data_view_id"] == "dv_test"
        assert payload["results"][0]["output_file"] == "report.xlsx"
        assert payload["results"][0]["output_files"] == ["report.xlsx"]

    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_run_summary_serializes_additive_output_files(self, mock_resolve, mock_process, tmp_path):
        """Run summary should carry additive multi-artifact output data."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_test"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=True,
            duration=0.25,
            metrics_count=10,
            dimensions_count=12,
            dq_issues_count=0,
            dq_issues=[],
            dq_severity_counts={},
            output_file="report.xlsx",
            output_files=["report.xlsx", "report.json", "report.html"],
            file_size_bytes=2048,
        )

        summary_file = tmp_path / "run_summary_outputs.json"
        with patch.object(sys, "argv", ["cja_auto_sdr", "dv_test", "--run-summary-json", str(summary_file)]):
            main()

        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["results"][0]["output_file"] == "report.xlsx"
        assert payload["results"][0]["output_files"] == ["report.xlsx", "report.json", "report.html"]

    def test_run_summary_all_format_subprocess_preserves_output_files(self, tmp_path):
        """E2E: subprocess run-summary contract should preserve additive output_files for --format all."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        summary_file = tmp_path / "run_summary_all_subprocess.json"
        script = textwrap.dedent(
            f"""
            import sys
            from unittest.mock import patch

            from cja_auto_sdr.generator import ProcessingResult, main

            summary_file = {str(summary_file)!r}
            result = ProcessingResult(
                data_view_id="dv_test",
                data_view_name="Test View",
                success=True,
                duration=0.25,
                metrics_count=10,
                dimensions_count=12,
                dq_issues_count=0,
                dq_issues=[],
                dq_severity_counts={{}},
                output_file="report.xlsx",
                output_files=["report.xlsx", "report.json", "report.html"],
                file_size_bytes=2048,
            )

            with (
                patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_test"], {{}})),
                patch("cja_auto_sdr.generator.process_single_dataview", return_value=result),
                patch.object(
                    sys,
                    "argv",
                    ["cja_auto_sdr", "dv_test", "--format", "all", "--run-summary-json", summary_file],
                ),
            ):
                main()
            """,
        )

        result = subprocess.run(
            ["uv", "run", "python", "-c", script],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )

        assert result.returncode == 0, result.stderr
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["output_format"] == "all"
        assert payload["results"][0]["output_file"] == "report.xlsx"
        assert payload["results"][0]["output_files"] == ["report.xlsx", "report.json", "report.html"]


class TestOpenOutputArtifacts(TestRunSummaryOutput):
    """Tests for opening normalized emitted artifact paths."""

    @patch("cja_auto_sdr.generator.open_file_in_default_app")
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_single_mode_open_uses_all_emitted_output_files(self, mock_resolve, mock_process, mock_open):
        """Single-mode --open should consume additive output_files when present."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_test"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=True,
            duration=0.25,
            metrics_count=10,
            dimensions_count=12,
            dq_issues_count=0,
            dq_issues=[],
            dq_severity_counts={},
            output_file="report.xlsx",
            output_files=["report.xlsx", "report.json", "report.html"],
            file_size_bytes=2048,
        )
        mock_open.return_value = True

        with patch.object(sys, "argv", ["cja_auto_sdr", "dv_test", "--open", "--format", "all"]):
            main()

        assert mock_open.call_count == 3
        assert [call.args[0] for call in mock_open.call_args_list] == ["report.xlsx", "report.json", "report.html"]

    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_run_summary_written_for_policy_exit(self, mock_resolve, mock_process, tmp_path):
        """Policy exits should still write run summary with quality gate status."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_test"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=True,
            duration=0.1,
            dq_issues_count=1,
            dq_issues=[{"Severity": "HIGH", "Issue": "Duplicate component"}],
            dq_severity_counts={"HIGH": 1},
        )

        summary_file = tmp_path / "run_summary_policy.json"
        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "dv_test", "--fail-on-quality", "HIGH", "--run-summary-json", str(summary_file)],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 2
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["exit_code"] == 2
        assert payload["status"] == "policy_exit"
        assert payload["quality_gate_failed"] is True

    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_run_summary_includes_stable_failure_identity(self, mock_resolve, mock_process, tmp_path):
        """Failed SDR results should expose stable failure code/reason and rollups."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_test"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=False,
            duration=0.2,
            error_message="Component fetch failed: metrics: timeout",
            failure_code="COMPONENT_FETCH_FAILED",
            failure_reason="required_endpoints_failed:metrics",
        )

        summary_file = tmp_path / "run_summary_failure_identity.json"
        with patch.object(sys, "argv", ["cja_auto_sdr", "dv_test", "--run-summary-json", str(summary_file)]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["status"] == "error"
        assert payload["result_counts"]["failed"] == 1
        assert payload["results"][0]["failure_code"] == "COMPONENT_FETCH_FAILED"
        assert payload["results"][0]["failure_reason"] == "required_endpoints_failed:metrics"
        assert payload["failure_rollups"]["by_code"] == {"COMPONENT_FETCH_FAILED": 1}
        assert payload["failure_rollups"]["by_reason"] == {"required_endpoints_failed:metrics": 1}

    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_run_summary_includes_partial_output_fields(self, mock_resolve, mock_process, tmp_path):
        """Allow-partial SDR outputs should surface partial_output and partial_reasons per result."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_test"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=True,
            duration=0.2,
            partial_output=True,
            partial_reasons=[
                "required_endpoints_failed:metrics",
                "data_quality_validation_runtime_failed",
            ],
        )

        summary_file = tmp_path / "run_summary_partial_output.json"
        with patch.object(
            sys,
            "argv",
            [
                "cja_auto_sdr",
                "dv_test",
                "--allow-partial",
                "--run-summary-json",
                str(summary_file),
            ],
        ):
            main()

        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["allow_partial"] is True
        assert payload["results"][0]["partial_output"] is True
        assert payload["results"][0]["partial_reasons"] == [
            "required_endpoints_failed:metrics",
            "data_quality_validation_runtime_failed",
        ]

    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.BatchProcessor.print_summary")
    @patch("cja_auto_sdr.generator.ProcessPoolExecutor")
    @patch("cja_auto_sdr.generator.tqdm")
    def test_run_summary_batch_failure_rollups_mixed_results_under_concurrent_completion(
        self,
        mock_tqdm,
        mock_executor_cls,
        _mock_print_summary,
        mock_resolve,
        tmp_path,
    ):
        """Batch-mode run summary should aggregate failure_rollups with mixed out-of-order future completion."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_ok", "dv_fetch_fail", "dv_validation_fail"], {})

        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        future_ok = Mock()
        future_fetch_fail = Mock()
        future_validation_fail = Mock()

        future_ok.result.return_value = ProcessingResult(
            data_view_id="dv_ok",
            data_view_name="Healthy View",
            success=True,
            duration=0.2,
            dq_issues_count=1,
            dq_issues=[{"Severity": "HIGH", "Issue": "threshold"}],
            dq_severity_counts={"HIGH": 1},
        )
        future_fetch_fail.result.return_value = ProcessingResult(
            data_view_id="dv_fetch_fail",
            data_view_name="Fetch Fail View",
            success=False,
            duration=0.3,
            error_message="Component fetch failed: metrics: timeout",
            failure_code="COMPONENT_FETCH_FAILED",
            failure_reason="required_endpoints_failed:metrics",
        )
        future_validation_fail.result.return_value = ProcessingResult(
            data_view_id="dv_validation_fail",
            data_view_name="Validation Fail View",
            success=False,
            duration=0.3,
            error_message="Data quality validation failed: threadpool failure",
            failure_code="DQ_VALIDATION_RUNTIME_FAILED",
            failure_reason="data_quality_validation_runtime_failed",
        )

        mock_executor = MagicMock()
        mock_executor.__enter__ = Mock(return_value=mock_executor)
        mock_executor.__exit__ = Mock(return_value=False)
        mock_executor.submit.side_effect = [future_ok, future_fetch_fail, future_validation_fail]
        mock_executor_cls.return_value = mock_executor

        summary_file = tmp_path / "run_summary_batch_rollups.json"
        with (
            patch(
                "cja_auto_sdr.generator.as_completed",
                return_value=[future_validation_fail, future_ok, future_fetch_fail],
            ),
            patch("cja_auto_sdr.generator.setup_logging", return_value=Mock()),
            patch.object(
                sys,
                "argv",
                [
                    "cja_auto_sdr",
                    "dv_ok",
                    "dv_fetch_fail",
                    "dv_validation_fail",
                    "--batch",
                    "--workers",
                    "2",
                    "--continue-on-error",
                    "--fail-on-quality",
                    "HIGH",
                    "--run-summary-json",
                    str(summary_file),
                ],
            ),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["result_counts"]["failed"] == 2
        assert payload["failure_rollups"]["by_code"] == {
            "COMPONENT_FETCH_FAILED": 1,
            "DQ_VALIDATION_RUNTIME_FAILED": 1,
        }
        assert payload["failure_rollups"]["by_reason"] == {
            "data_quality_validation_runtime_failed": 1,
            "required_endpoints_failed:metrics": 1,
        }

    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.BatchProcessor.print_summary")
    @patch("cja_auto_sdr.generator.ProcessPoolExecutor")
    @patch("cja_auto_sdr.generator.tqdm")
    def test_run_summary_batch_mixed_results_preserves_success_output_files(
        self,
        mock_tqdm,
        mock_executor_cls,
        _mock_print_summary,
        mock_resolve,
        tmp_path,
    ):
        """Batch-mode run summary should preserve additive output_files for successful entries even when failures exist."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_ok", "dv_fail"], {})

        mock_pbar = MagicMock()
        mock_tqdm.return_value.__enter__ = Mock(return_value=mock_pbar)
        mock_tqdm.return_value.__exit__ = Mock(return_value=False)

        future_ok = Mock()
        future_fail = Mock()

        future_ok.result.return_value = ProcessingResult(
            data_view_id="dv_ok",
            data_view_name="Healthy View",
            success=True,
            duration=0.2,
            metrics_count=10,
            dimensions_count=12,
            dq_issues_count=0,
            dq_issues=[],
            dq_severity_counts={},
            output_file="ok.xlsx",
            output_files=["ok.json", "ok.xlsx", "ok.html", "ok.json"],
            file_size_bytes=2048,
        )
        future_fail.result.return_value = ProcessingResult(
            data_view_id="dv_fail",
            data_view_name="Fail View",
            success=False,
            duration=0.3,
            error_message="Component fetch failed: metrics: timeout",
            failure_code="COMPONENT_FETCH_FAILED",
            failure_reason="required_endpoints_failed:metrics",
        )

        mock_executor = MagicMock()
        mock_executor.__enter__ = Mock(return_value=mock_executor)
        mock_executor.__exit__ = Mock(return_value=False)
        mock_executor.submit.side_effect = [future_ok, future_fail]
        mock_executor_cls.return_value = mock_executor

        summary_file = tmp_path / "run_summary_batch_outputs.json"
        with (
            patch("cja_auto_sdr.generator.as_completed", return_value=[future_fail, future_ok]),
            patch("cja_auto_sdr.generator.setup_logging", return_value=Mock()),
            patch.object(
                sys,
                "argv",
                [
                    "cja_auto_sdr",
                    "dv_ok",
                    "dv_fail",
                    "--batch",
                    "--workers",
                    "2",
                    "--continue-on-error",
                    "--run-summary-json",
                    str(summary_file),
                ],
            ),
        ):
            main()

        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        results_by_id = {result["data_view_id"]: result for result in payload["results"]}
        assert results_by_id["dv_ok"]["output_file"] == "ok.xlsx"
        assert results_by_id["dv_ok"]["output_files"] == ["ok.xlsx", "ok.json", "ok.html"]
        assert results_by_id["dv_fail"]["output_files"] == []

    @patch("cja_auto_sdr.generator.list_dataviews")
    def test_run_summary_written_for_discovery_mode(self, mock_list_dataviews, tmp_path):
        """Discovery mode should write summary even when exiting via SystemExit."""
        from cja_auto_sdr.generator import main

        mock_list_dataviews.return_value = True
        summary_file = tmp_path / "run_summary_discovery.json"

        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "--list-dataviews", "--run-summary-json", str(summary_file)],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "discovery"
        assert payload["exit_code"] == 0
        assert payload["details"]["discovery_command"] == "list_dataviews"

    @patch("cja_auto_sdr.generator.list_dataviews")
    def test_run_summary_non_sdr_quality_policy_is_not_applied(self, mock_list_dataviews, tmp_path):
        """Run summary should record quality policy path but keep applied defaults empty in non-SDR modes."""
        from cja_auto_sdr.generator import main

        policy_path = tmp_path / "quality_policy.json"
        policy_path.write_text(
            json.dumps({"fail_on_quality": "HIGH", "quality_report": "csv", "max_issues": 5}),
            encoding="utf-8",
        )
        mock_list_dataviews.return_value = True
        summary_file = tmp_path / "run_summary_discovery_quality_policy.json"

        with patch.object(
            sys,
            "argv",
            [
                "cja_auto_sdr",
                "--list-dataviews",
                "--quality-policy",
                str(policy_path),
                "--run-summary-json",
                str(summary_file),
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "discovery"
        assert payload["quality_policy"]["path"] == str(policy_path)
        assert payload["quality_policy"]["applied"] == {}

    @patch("cja_auto_sdr.generator.run_org_report")
    @patch("cja_auto_sdr.generator.list_dataviews")
    def test_run_summary_mode_precedence_matches_dispatch_order(
        self,
        mock_list_dataviews,
        mock_run_org_report,
        tmp_path,
    ):
        """When multiple mode flags are present, summary mode should match the first dispatch branch."""
        from cja_auto_sdr.generator import main

        mock_list_dataviews.return_value = True
        summary_file = tmp_path / "run_summary_mode_precedence.json"

        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "--list-dataviews", "--org-report", "--run-summary-json", str(summary_file)],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "discovery"
        assert payload["details"]["discovery_command"] == "list_dataviews"
        mock_list_dataviews.assert_called_once()
        mock_run_org_report.assert_not_called()

    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_run_summary_stdout_is_json_only(self, mock_resolve, mock_process, capsys):
        """--run-summary-json stdout should emit parseable JSON on stdout."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_test"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=True,
            duration=0.1,
            metrics_count=1,
            dimensions_count=1,
            dq_issues_count=0,
            dq_issues=[],
            dq_severity_counts={},
        )

        with patch.object(sys, "argv", ["cja_auto_sdr", "dv_test", "--run-summary-json", "stdout"]):
            main()

        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "sdr"
        assert payload["exit_code"] == 0

    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    @patch("cja_auto_sdr.generator.interactive_wizard")
    def test_run_summary_interactive_refreshes_data_view_inputs(
        self,
        mock_wizard,
        mock_resolve,
        mock_process,
        tmp_path,
    ):
        """Interactive runs should record wizard-selected data view inputs in run summary."""
        from cja_auto_sdr.generator import ProcessingResult, WizardConfig, main

        mock_wizard.return_value = WizardConfig(
            data_view_ids=["dv_wizard_selected"],
            output_format="excel",
            include_segments=False,
            include_calculated=False,
            include_derived=False,
            inventory_only=False,
        )
        mock_resolve.return_value = (["dv_wizard_selected"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_wizard_selected",
            data_view_name="Wizard Selected",
            success=True,
            duration=0.1,
            metrics_count=1,
            dimensions_count=1,
            dq_issues_count=0,
            dq_issues=[],
            dq_severity_counts={},
        )

        summary_file = tmp_path / "run_summary_interactive_inputs.json"
        with patch.object(sys, "argv", ["cja_auto_sdr", "--interactive", "--run-summary-json", str(summary_file)]):
            main()

        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "sdr"
        assert payload["inputs"]["data_view_inputs"] == ["dv_wizard_selected"]

    @patch("cja_auto_sdr.generator.list_dataviews")
    def test_run_summary_stdout_with_abbreviated_flag_is_json_only(self, mock_list_dataviews, capsys):
        """Abbreviated --run-summary-json should still redirect normal stdout chatter."""
        from cja_auto_sdr.generator import main

        def _mock_list_dataviews(*args, **kwargs):
            print("discovery table output")
            return True

        mock_list_dataviews.side_effect = _mock_list_dataviews

        with patch.object(sys, "argv", ["cja_auto_sdr", "--list-dataviews", "--run-summary-j", "stdout"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "discovery"
        assert payload["exit_code"] == 0
        assert "discovery table output" not in captured.out
        assert "discovery table output" in captured.err

    def test_run_summary_stdout_json_only_subprocess_exit_codes_full_flag(self):
        """E2E: full flag should keep stdout as JSON-only in chatty exit-codes mode."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        result = subprocess.run(
            ["uv", "run", "cja_auto_sdr", "--exit-codes", "--run-summary-json", "stdout"],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "exit_codes"
        assert "EXIT CODE REFERENCE" not in result.stdout
        assert "EXIT CODE REFERENCE" in result.stderr

    def test_run_summary_stdout_json_only_subprocess_exit_codes_abbreviated_flag(self):
        """E2E: abbreviated flag should keep stdout as JSON-only in chatty exit-codes mode."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        result = subprocess.run(
            ["uv", "run", "cja_auto_sdr", "--exit-codes", "--run-summary-j", "stdout"],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        assert result.returncode == 0
        payload = json.loads(result.stdout)
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "exit_codes"
        assert "EXIT CODE REFERENCE" not in result.stdout
        assert "EXIT CODE REFERENCE" in result.stderr

    def test_run_summary_completion_mode_classification(self, tmp_path):
        """Completion runs should emit run summary mode=completion."""
        from cja_auto_sdr.generator import main

        summary_file = tmp_path / "run_summary_completion.json"
        fake_argcomplete = type(sys)("argcomplete")

        with (
            patch.object(
                sys,
                "argv",
                ["cja_auto_sdr", "--completion", "bash", "--run-summary-json", str(summary_file)],
            ),
            patch.dict("sys.modules", {"argcomplete": fake_argcomplete}),
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "completion"
        assert payload["exit_code"] == 0
        assert payload["status"] == "success"

    def test_run_summary_exit_codes_precedes_completion_mode_classification(self, tmp_path):
        """Mixed --exit-codes/--completion should preserve exit-codes summary mode."""
        from cja_auto_sdr.generator import main

        summary_file = tmp_path / "run_summary_exit_codes_precedes_completion.json"
        with (
            patch.object(
                sys,
                "argv",
                [
                    "cja_auto_sdr",
                    "--exit-codes",
                    "--completion",
                    "bash",
                    "--run-summary-json",
                    str(summary_file),
                ],
            ),
            patch("cja_auto_sdr.core.exit_codes.print_exit_codes") as mock_print_exit_codes,
            patch("cja_auto_sdr.generator._handle_completion_prevalidation") as mock_completion_prevalidation,
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "exit_codes"
        assert payload["exit_code"] == 0
        assert payload["status"] == "success"
        mock_print_exit_codes.assert_called_once()
        mock_completion_prevalidation.assert_not_called()

    def test_run_summary_stdout_subprocess_version_is_order_independent(self):
        """E2E: --version should still emit run summary JSON regardless of flag order."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        commands = [
            ["uv", "run", "cja_auto_sdr", "--version", "--run-summary-json", "stdout"],
            ["uv", "run", "cja_auto_sdr", "--run-summary-json", "stdout", "--version"],
            ["uv", "run", "cja_auto_sdr", "-V", "--run-summary-json", "stdout"],
            ["uv", "run", "cja_auto_sdr", "--run-summary-json", "stdout", "-V"],
            ["uv", "run", "cja_auto_sdr", "--version", "--profile", "--run-summary-json", "stdout"],
        ]

        for cmd in commands:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=repo_root,
            )
            assert result.returncode == 0
            payload = json.loads(result.stdout)
            self._assert_run_summary_schema(payload)
            assert payload["exit_code"] == 0
            assert payload["mode"] == "unknown"
            assert "cja_auto_sdr " not in result.stdout
            assert "cja_auto_sdr " in result.stderr

    def test_module_invocation_version_banner_consistent_with_and_without_run_summary(self):
        """`python -m cja_auto_sdr --version` should keep the same banner prefix across paths."""
        repo_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        fast_path = subprocess.run(
            ["uv", "run", "python", "-m", "cja_auto_sdr", "--version"],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        assert fast_path.returncode == 0
        assert " -m cja_auto_sdr " in fast_path.stdout
        fast_prefix = fast_path.stdout.strip().split(" -m cja_auto_sdr ")[0]

        fallback = subprocess.run(
            ["uv", "run", "python", "-m", "cja_auto_sdr", "--version", "--run-summary-json", "stdout"],
            capture_output=True,
            text=True,
            cwd=repo_root,
        )
        assert fallback.returncode == 0
        payload = json.loads(fallback.stdout)
        self._assert_run_summary_schema(payload)
        assert payload["exit_code"] == 0
        assert f"{fast_prefix} -m cja_auto_sdr " in fallback.stderr

    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_run_summary_records_inferred_output_format(self, mock_resolve, mock_process, tmp_path):
        """Run summary should capture format inferred from --output extension."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_test"], {})
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=True,
            duration=0.1,
            metrics_count=1,
            dimensions_count=1,
            dq_issues_count=0,
            dq_issues=[],
            dq_severity_counts={},
            output_file="report.csv",
        )

        summary_file = tmp_path / "run_summary_inferred.json"
        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "dv_test", "--output", "report.csv", "--run-summary-json", str(summary_file)],
        ):
            main()

        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["output_format"] == "csv"

    @patch("cja_auto_sdr.generator.write_quality_report_output")
    @patch("cja_auto_sdr.generator.process_single_dataview")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_run_summary_quality_report_uses_quality_report_format(
        self,
        mock_resolve,
        mock_process,
        mock_write_report,
        tmp_path,
    ):
        """Run summary output_format should reflect --quality-report format, not internal SDR writer format."""
        from cja_auto_sdr.generator import ProcessingResult, main

        mock_resolve.return_value = (["dv_test"], {})
        mock_write_report.return_value = "stdout"
        mock_process.return_value = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test View",
            success=True,
            duration=0.1,
            dq_issues_count=1,
            dq_issues=[{"Severity": "LOW", "Issue": "Minor"}],
            dq_severity_counts={"LOW": 1},
        )

        summary_file = tmp_path / "run_summary_quality_report_format.json"
        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "dv_test", "--quality-report", "csv", "--run-summary-json", str(summary_file)],
        ):
            main()

        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "sdr"
        assert payload["output_format"] == "csv"

    @patch("cja_auto_sdr.generator.process_inventory_summary")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_run_summary_inventory_summary_mode_and_output_format(self, mock_resolve, mock_inventory_summary, tmp_path):
        """Inventory summary runs should report mode=inventory_summary with effective summary output format."""
        from cja_auto_sdr.generator import main

        mock_resolve.return_value = (["dv_test"], {})
        mock_inventory_summary.return_value = {}
        summary_file = tmp_path / "run_summary_inventory_summary.json"

        with patch.object(
            sys,
            "argv",
            [
                "cja_auto_sdr",
                "dv_test",
                "--include-segments",
                "--inventory-summary",
                "--run-summary-json",
                str(summary_file),
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "inventory_summary"
        assert payload["output_format"] == "console"

    @patch("cja_auto_sdr.generator.process_inventory_summary")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_inventory_summary_propagates_log_format(self, mock_resolve, mock_inventory_summary):
        """Inventory summary mode should pass --log-format to process_inventory_summary."""
        from cja_auto_sdr.generator import main

        mock_resolve.return_value = (["dv_test"], {})
        mock_inventory_summary.return_value = {}

        with patch.object(
            sys,
            "argv",
            [
                "cja_auto_sdr",
                "dv_test",
                "--include-segments",
                "--inventory-summary",
                "--log-format",
                "json",
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        assert mock_inventory_summary.call_count == 1
        assert mock_inventory_summary.call_args.kwargs["log_format"] == "json"

    @patch("cja_auto_sdr.generator.git_init_snapshot_repo")
    def test_run_summary_git_init_mode(self, mock_git_init, tmp_path):
        """Run summary should classify --git-init runs with git_init mode."""
        from cja_auto_sdr.generator import main

        mock_git_init.return_value = (True, "initialized")
        summary_file = tmp_path / "run_summary_git_init.json"

        with patch.object(
            sys,
            "argv",
            [
                "cja_auto_sdr",
                "--git-init",
                "--git-dir",
                str(tmp_path / "repo"),
                "--run-summary-json",
                str(summary_file),
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "git_init"
        assert payload["status"] == "success"

    def test_run_summary_invalid_cli_status_is_error(self, tmp_path):
        """Argparse usage errors (exit 2) should be reported as status=error, not policy_exit."""
        from cja_auto_sdr.generator import main

        summary_file = tmp_path / "run_summary_cli_error.json"
        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "--definitely-invalid-flag", "--run-summary-json", str(summary_file)],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 2
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["status"] == "error"
        assert payload["exit_code"] == 2

    def test_run_summary_invalid_quality_policy_preserves_inferred_mode(self, tmp_path):
        """Policy-load failures should still emit run summary with inferred mode metadata."""
        from cja_auto_sdr.generator import main

        summary_file = tmp_path / "run_summary_quality_policy_error.json"
        missing_policy = tmp_path / "missing_quality_policy.json"

        with patch.object(
            sys,
            "argv",
            [
                "cja_auto_sdr",
                "--list-dataviews",
                "--quality-policy",
                str(missing_policy),
                "--run-summary-json",
                str(summary_file),
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "discovery"
        assert payload["status"] == "error"
        assert payload["quality_policy"]["path"] == str(missing_policy)
        assert payload["quality_policy"]["applied"] == {}

    def test_run_summary_policy_applied_allow_partial_survives_early_validation_exit(self, tmp_path):
        """Policy-mutated allow_partial should be synced before later CLI validation exits."""
        from cja_auto_sdr.generator import main

        summary_file = tmp_path / "run_summary_policy_allow_partial_validation_error.json"
        policy_file = tmp_path / "quality_policy.json"
        policy_file.write_text(json.dumps({"allow_partial": True}), encoding="utf-8")

        with patch.object(
            sys,
            "argv",
            [
                "cja_auto_sdr",
                "dv_test",
                "--quality-policy",
                str(policy_file),
                "--workers",
                "0",
                "--run-summary-json",
                str(summary_file),
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "sdr"
        assert payload["status"] == "error"
        assert payload["allow_partial"] is True
        assert payload["quality_policy"]["path"] == str(policy_file)
        assert payload["quality_policy"]["applied"] == {"allow_partial": True}

    def test_run_summary_profile_overwrite_validation_error_mode(self, tmp_path):
        """Profile overwrite validation failures should still be classified as profile_management mode."""
        from cja_auto_sdr.generator import main

        summary_file = tmp_path / "run_summary_profile_overwrite_error.json"
        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "--profile-overwrite", "--run-summary-json", str(summary_file)],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "profile_management"
        assert payload["status"] == "error"

    def test_run_summary_non_sdr_allow_partial_validation_preserves_flag(self, tmp_path):
        """Early non-SDR validation errors should preserve allow_partial telemetry."""
        from cja_auto_sdr.generator import main

        summary_file = tmp_path / "run_summary_non_sdr_allow_partial_error.json"
        with patch.object(
            sys,
            "argv",
            [
                "cja_auto_sdr",
                "--list-dataviews",
                "--allow-partial",
                "--run-summary-json",
                str(summary_file),
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "discovery"
        assert payload["status"] == "error"
        assert payload["allow_partial"] is True

    def test_run_summary_argparse_error_preserves_allow_partial_flag(self, tmp_path):
        """Argparse failures should still preserve allow_partial telemetry from argv."""
        from cja_auto_sdr.generator import main

        summary_file = tmp_path / "run_summary_argparse_allow_partial_error.json"
        with patch.object(
            sys,
            "argv",
            [
                "cja_auto_sdr",
                "--allow-partial",
                "--definitely-invalid-flag",
                "--run-summary-json",
                str(summary_file),
            ],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 2
        payload = json.loads(summary_file.read_text())
        self._assert_run_summary_schema(payload)
        assert payload["mode"] == "unknown"
        assert payload["status"] == "error"
        assert payload["allow_partial"] is True

    def test_run_summary_missing_value_does_not_write_flag_named_file(self, tmp_path, monkeypatch):
        """Malformed --run-summary-json should not treat the next flag as an output path."""
        from cja_auto_sdr.generator import main

        bad_output_name = "--list-dataviews"
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["cja_auto_sdr", "--run-summary-json", "--list-dataviews"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 2
        assert not (tmp_path / bad_output_name).exists()

    def test_cli_option_value_uses_last_valid_occurrence(self):
        """Raw option helper should align with argparse 'last value wins' behavior."""
        from cja_auto_sdr.generator import _cli_option_value

        value = _cli_option_value(
            "--run-summary-json",
            [
                "--run-summary-json",
                "stdout",
                "--run-summary-json",
                "summary.json",
            ],
        )
        assert value == "summary.json"

    def test_cli_option_value_accepts_unambiguous_long_option_abbreviation(self):
        """Raw option helper should resolve argparse-accepted long-option abbreviations."""
        from cja_auto_sdr.generator import _cli_option_value

        value = _cli_option_value("--run-summary-json", ["--run-summary-j", "stdout"])
        assert value == "stdout"

    @pytest.mark.parametrize(
        ("argv", "expected"),
        [
            (["--run-summary-json", "stdout"], "stdout"),
            (["--run-summary-j", "stdout"], "stdout"),
            (["--run-summary-j=stdout"], "stdout"),
            (["--run-summary-json", "--list-dataviews"], None),
            (["--run-summary-j", "--list-dataviews"], None),
            (["--run-summary-json", "stdout", "--run-summary-j", "summary.json"], "summary.json"),
            (["--run-summary-json=stdout", "--run-summary-j=summary.json"], "summary.json"),
            (["--run-summary-json", "stdout", "--run-summary-json"], "stdout"),
        ],
    )
    def test_cli_option_value_permutations(self, argv, expected):
        """Raw option helper should stay aligned with argparse-style option permutations."""
        from cja_auto_sdr.generator import _cli_option_value

        assert _cli_option_value("--run-summary-json", argv) == expected

    @pytest.mark.parametrize(
        ("option_name", "argv", "expected"),
        [
            ("--run-summary-json", ["--run-summary-j", "stdout"], True),
            ("--max-issues", ["--max-i=10"], True),
            ("--fail-on-quality", ["--fail-on-q", "HIGH"], True),
            ("--profile", ["--pro"], False),
            ("--run-summary-json", ["-q"], False),
        ],
    )
    def test_cli_option_specified_permutations(self, option_name, argv, expected):
        """Explicit option detection should follow argparse abbreviation semantics."""
        from cja_auto_sdr.generator import _cli_option_specified

        assert _cli_option_specified(option_name, argv) is expected


class TestRunModeInference:
    """Tests that run-mode inference remains aligned with dispatch precedence."""

    @pytest.mark.parametrize(
        ("argv", "expected_mode"),
        [
            (["cja_auto_sdr", "--exit-codes", "--completion", "bash"], "exit_codes"),
            (["cja_auto_sdr", "--completion", "bash", "--sample-config"], "completion"),
            (["cja_auto_sdr", "--list-dataviews", "--org-report"], "discovery"),
            (["cja_auto_sdr", "--describe-dataview", "dv_1"], "discovery"),
            (["cja_auto_sdr", "--list-metrics", "dv_1"], "discovery"),
            (["cja_auto_sdr", "--config-status", "--validate-config"], "config_status"),
            (["cja_auto_sdr", "--diff", "dv_a", "dv_b", "--dry-run"], "diff"),
            (["cja_auto_sdr", "dv_test", "--snapshot", "baseline.json", "--compare-with-prev"], "snapshot"),
            (["cja_auto_sdr", "dv_test", "--include-segments", "--inventory-summary", "--dry-run"], "dry_run"),
            (["cja_auto_sdr", "--profile-overwrite"], "profile_management"),
        ],
    )
    def test_infer_run_mode_precedence_matches_dispatch(self, argv, expected_mode):
        """_infer_run_mode should classify modes with the same precedence as _main_impl dispatch."""
        from cja_auto_sdr.generator import _infer_run_mode, parse_arguments

        with patch.object(sys, "argv", argv):
            args = parse_arguments()

        assert _infer_run_mode(args) == expected_mode


class TestOrgReportArgumentValidation:
    """Tests for org-report-specific numeric validation in main()."""

    @patch("cja_auto_sdr.generator.run_org_report")
    def test_org_report_rejects_negative_sample_size(self, mock_run_org_report):
        """--sample should fail fast for negative values before org-report execution."""
        from cja_auto_sdr.generator import main

        with patch.object(sys, "argv", ["cja_auto_sdr", "--org-report", "--sample", "-1"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        mock_run_org_report.assert_not_called()

    @patch("cja_auto_sdr.generator.run_org_report")
    def test_org_report_rejects_trending_window_zero(self, mock_run_org_report):
        """--trending-window 0 should fail before org-report execution."""
        from cja_auto_sdr.generator import main

        with patch.object(sys, "argv", ["cja_auto_sdr", "--org-report", "--trending-window", "0"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        mock_run_org_report.assert_not_called()

    @patch("cja_auto_sdr.generator.run_org_report")
    def test_org_report_rejects_trending_window_below_two(self, mock_run_org_report):
        """--trending-window must be at least 2 before org-report execution."""
        from cja_auto_sdr.generator import main

        with patch.object(sys, "argv", ["cja_auto_sdr", "--org-report", "--trending-window", "1"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        mock_run_org_report.assert_not_called()

    @patch("cja_auto_sdr.generator.list_dataviews")
    def test_trending_window_requires_org_report_mode(self, mock_list_dataviews, capsys):
        """--trending-window should fail fast outside org-report mode."""
        from cja_auto_sdr.generator import main

        with patch.object(sys, "argv", ["cja_auto_sdr", "--list-dataviews", "--trending-window", "5"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1
        assert "--trending-window is only supported with --org-report" in capsys.readouterr().err
        mock_list_dataviews.assert_not_called()


class TestProfileImportCLI:
    """Tests for non-interactive --profile-import CLI flow."""

    @patch("cja_auto_sdr.generator.import_profile_non_interactive")
    def test_profile_import_dispatches_without_data_views(self, mock_import):
        """--profile-import should run profile import command without requiring data views."""
        from cja_auto_sdr.generator import main

        mock_import.return_value = True

        with patch.object(sys, "argv", ["cja_auto_sdr", "--profile-import", "client-a", "creds.json"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        mock_import.assert_called_once_with("client-a", "creds.json", overwrite=False)

    @patch("cja_auto_sdr.generator.import_profile_non_interactive")
    def test_profile_import_respects_overwrite_flag(self, mock_import):
        """--profile-overwrite should be forwarded to import handler."""
        from cja_auto_sdr.generator import main

        mock_import.return_value = True

        with patch.object(
            sys,
            "argv",
            ["cja_auto_sdr", "--profile-import", "client-a", "creds.json", "--profile-overwrite"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 0
        mock_import.assert_called_once_with("client-a", "creds.json", overwrite=True)

    def test_profile_overwrite_requires_profile_import(self):
        """--profile-overwrite without --profile-import should fail fast."""
        from cja_auto_sdr.generator import main

        with patch.object(sys, "argv", ["cja_auto_sdr", "--profile-overwrite"]):
            with pytest.raises(SystemExit) as exc_info:
                main()

        assert exc_info.value.code == 1


class TestDiscoveryInspectionParsing:
    """Tests for new discovery inspection CLI arguments."""

    def test_describe_dataview_stores_id(self):
        args = parse_arguments(["--describe-dataview", "dv_abc123"])
        assert args.describe_dataview == "dv_abc123"

    def test_list_metrics_stores_id(self):
        args = parse_arguments(["--list-metrics", "dv_abc123"])
        assert args.list_metrics == "dv_abc123"

    def test_list_dimensions_stores_id(self):
        args = parse_arguments(["--list-dimensions", "dv_abc123"])
        assert args.list_dimensions == "dv_abc123"

    def test_list_segments_stores_id(self):
        args = parse_arguments(["--list-segments", "dv_abc123"])
        assert args.list_segments == "dv_abc123"

    def test_list_calculated_metrics_stores_id(self):
        args = parse_arguments(["--list-calculated-metrics", "dv_abc123"])
        assert args.list_calculated_metrics == "dv_abc123"

    def test_new_flags_mutual_exclusivity_with_existing(self):
        """New flags are mutually exclusive with existing discovery commands."""
        with pytest.raises(SystemExit):
            parse_arguments(["--list-dataviews", "--describe-dataview", "dv_1"])

    def test_new_flags_mutual_exclusivity_with_each_other(self):
        """New flags are mutually exclusive with each other."""
        with pytest.raises(SystemExit):
            parse_arguments(["--describe-dataview", "dv_1", "--list-metrics", "dv_1"])


class TestDescribeDataview:
    """Tests for --describe-dataview command."""

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_describe_dataview_json(self, mock_profile, mock_configure, mock_cjapy):
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {
            "id": "dv_1",
            "name": "Test View",
            "owner": {"name": "Jane"},
            "description": "A test view",
            "parentDataGroupId": "conn_1",
            "created": "2025-01-01",
            "modified": "2025-06-01",
        }
        cja.getMetrics.return_value = [{"id": f"m{i}"} for i in range(5)]
        cja.getDimensions.return_value = [{"id": f"d{i}"} for i in range(3)]
        cja.getFilters.return_value = [{"id": f"s{i}"} for i in range(2)]
        cja.getCalculatedMetrics.return_value = [{"id": f"cm{i}"} for i in range(1)]

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = describe_dataview("dv_1", output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        dv = output["dataView"]
        assert dv["id"] == "dv_1"
        assert dv["name"] == "Test View"
        assert dv["owner"] == "Jane"
        assert dv["components"]["metrics"] == 5
        assert dv["components"]["dimensions"] == 3
        assert dv["components"]["segments"] == 2
        assert dv["components"]["calculatedMetrics"] == 1
        assert dv["components"]["total"] == 11
        cja.getMetrics.assert_called_once_with("dv_1", inclType="hidden", full=True)
        cja.getDimensions.assert_called_once_with("dv_1", inclType="hidden", full=True)
        cja.getFilters.assert_called_once_with(dataIds="dv_1", full=True)
        cja.getCalculatedMetrics.assert_called_once_with(dataIds="dv_1", full=True)

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_describe_dataview_json_mixed_case_lookup_payload_fields_are_canonicalized(
        self,
        mock_profile,
        mock_configure,
        mock_cjapy,
    ):
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {
            "ID": "dv_1",
            "Name": "Test View",
            "Owner": {"NAME": "Jane"},
            "Description": "A test view",
            "ParentDataGroupID": "conn_1",
            "CreatedDATE": "2025-01-01",
            "MODIFIEDAT": "2025-06-01",
        }
        cja.getMetrics.return_value = [{"id": "m1"}]
        cja.getDimensions.return_value = [{"id": "d1"}]
        cja.getFilters.return_value = []
        cja.getCalculatedMetrics.return_value = []

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = describe_dataview("dv_1", output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        dv = output["dataView"]
        assert dv["id"] == "dv_1"
        assert dv["name"] == "Test View"
        assert dv["owner"] == "Jane"
        assert dv["description"] == "A test view"
        assert dv["connectionId"] == "conn_1"
        assert dv["created"] == "2025-01-01"
        assert dv["modified"] == "2025-06-01"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_describe_dataview_json_counts_hidden_metrics_and_dimensions(
        self,
        mock_profile,
        mock_configure,
        mock_cjapy,
    ):
        """describe_dataview component counts should include hidden metrics and dimensions."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {
            "id": "dv_1",
            "name": "Test View",
            "owner": {"name": "Jane"},
            "description": "A test view",
            "parentDataGroupId": "conn_1",
            "created": "2025-01-01",
            "modified": "2025-06-01",
        }

        def _get_metrics(_data_view_id, **kwargs):
            if kwargs.get("inclType") == "hidden" and kwargs.get("full") is True:
                return [{"id": "m_visible"}, {"id": "m_hidden"}]
            return [{"id": "m_visible"}]

        def _get_dimensions(_data_view_id, **kwargs):
            if kwargs.get("inclType") == "hidden" and kwargs.get("full") is True:
                return [{"id": "d_visible"}, {"id": "d_hidden"}]
            return [{"id": "d_visible"}]

        cja.getMetrics.side_effect = _get_metrics
        cja.getDimensions.side_effect = _get_dimensions
        cja.getFilters.return_value = []
        cja.getCalculatedMetrics.return_value = []

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = describe_dataview("dv_1", output_format="json")

        assert result is True
        components = json.loads(f.getvalue())["dataView"]["components"]
        assert components["metrics"] == 2
        assert components["dimensions"] == 2
        assert components["total"] == 4
        cja.getMetrics.assert_called_once_with("dv_1", inclType="hidden", full=True)
        cja.getDimensions.assert_called_once_with("dv_1", inclType="hidden", full=True)

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_describe_dataview_csv(self, mock_profile, mock_configure, mock_cjapy):
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {
            "id": "dv_1",
            "name": "Test",
            "owner": {"name": "Jane"},
            "description": "",
            "parentDataGroupId": "conn_1",
            "created": "2025-01-01",
            "modified": "2025-06-01",
        }
        cja.getMetrics.return_value = [{"id": "m1"}]
        cja.getDimensions.return_value = [{"id": "d1"}]
        cja.getFilters.return_value = []
        cja.getCalculatedMetrics.return_value = []

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = describe_dataview("dv_1", output_format="csv")

        assert result is True
        lines = f.getvalue().strip().split("\n")
        assert "id" in lines[0]
        assert "dv_1" in lines[1]

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_describe_dataview_table(self, mock_profile, mock_configure, mock_cjapy):
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {
            "id": "dv_1",
            "name": "Test View",
            "owner": {"name": "Jane"},
            "description": "Desc",
            "parentDataGroupId": "conn_1",
            "created": "2025-01-01",
            "modified": "2025-06-01",
        }
        cja.getMetrics.return_value = [{"id": "m1"}, {"id": "m2"}]
        cja.getDimensions.return_value = [{"id": "d1"}]
        cja.getFilters.return_value = [{"id": "s1"}]
        cja.getCalculatedMetrics.return_value = []

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = describe_dataview("dv_1", output_format="table")

        assert result is True
        output = f.getvalue()
        assert "Test View" in output
        assert "Jane" in output
        assert "Dimensions" in output
        assert "Metrics" in output

    @patch("cja_auto_sdr.generator.shutil.get_terminal_size", return_value=os.terminal_size((80, 24)))
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_describe_dataview_long_description_wraps(self, mock_profile, mock_configure, mock_cjapy, _mock_term):
        """Long description text wraps within terminal width."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        long_desc = "This is a very long description. " * 10
        cja.getDataView.return_value = {
            "id": "dv_1",
            "name": "Test View",
            "owner": {"name": "Jane"},
            "description": long_desc,
            "parentDataGroupId": "conn_1",
            "created": "2025-01-01",
            "modified": "2025-06-01",
        }
        cja.getMetrics.return_value = [{"id": "m1"}]
        cja.getDimensions.return_value = [{"id": "d1"}]
        cja.getFilters.return_value = []
        cja.getCalculatedMetrics.return_value = []

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = describe_dataview("dv_1", output_format="table")

        assert result is True
        output = f.getvalue()
        # Description should be split across multiple lines
        desc_lines = [
            line
            for line in output.split("\n")
            if "Description" in line or (line.startswith("                 ") and "long" in line)
        ]
        assert len(desc_lines) > 1, "Long description should wrap to multiple lines"
        # No line should exceed terminal width (80 columns)
        for line in output.split("\n"):
            if line.strip():
                assert len(line) <= 80, f"Line too long ({len(line)}): {line[:50]}..."

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_describe_dataview_table_dataframe_nan_description(self, mock_profile, mock_configure, mock_cjapy):
        """DataFrame-shaped getDataView payload with NaN description should render safely."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value

        import pandas as pd

        cja.getDataView.return_value = pd.DataFrame(
            [
                {
                    "id": "dv_1",
                    "name": "Test View",
                    "owner": {"name": "Jane"},
                    "description": float("nan"),
                    "parentDataGroupId": "conn_1",
                    "created": "2025-01-01",
                    "modified": "2025-06-01",
                }
            ]
        )
        cja.getMetrics.return_value = [{"id": "m1"}]
        cja.getDimensions.return_value = [{"id": "d1"}]
        cja.getFilters.return_value = []
        cja.getCalculatedMetrics.return_value = []

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = describe_dataview("dv_1", output_format="table")

        assert result is True
        output = f.getvalue()
        assert "Description:   (none)" in output

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_describe_dataview_json_dataframe_nan_description_normalized(
        self,
        mock_profile,
        mock_configure,
        mock_cjapy,
    ):
        """DataFrame payload null-like description should serialize as empty string."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value

        import pandas as pd

        cja.getDataView.return_value = pd.DataFrame(
            [
                {
                    "id": "dv_1",
                    "name": "Test View",
                    "ownerName": "Jane",
                    "description": pd.NA,
                    "connectionId": "conn_alias",
                    "createdDate": "2025-01-01",
                    "modifiedDate": "2025-06-01",
                }
            ]
        )
        cja.getMetrics.return_value = [{"id": "m1"}]
        cja.getDimensions.return_value = [{"id": "d1"}]
        cja.getFilters.return_value = []
        cja.getCalculatedMetrics.return_value = []

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = describe_dataview("dv_1", output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["dataView"]["description"] == ""
        assert output["dataView"]["owner"] == "Jane"
        assert output["dataView"]["connectionId"] == "conn_alias"
        assert output["dataView"]["created"] == "2025-01-01"
        assert output["dataView"]["modified"] == "2025-06-01"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_describe_dataview_csv_dataframe_nan_description_normalized(
        self,
        mock_profile,
        mock_configure,
        mock_cjapy,
    ):
        """CSV output should not emit literal nan for null-like descriptions."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value

        import csv
        import io
        from contextlib import redirect_stdout

        import pandas as pd

        cja.getDataView.return_value = pd.DataFrame(
            [
                {
                    "id": "dv_1",
                    "name": "Test View",
                    "owner": {"name": "Jane"},
                    "description": float("nan"),
                    "parentDataGroupId": "conn_1",
                    "created": "2025-01-01",
                    "modified": "2025-06-01",
                }
            ]
        )
        cja.getMetrics.return_value = [{"id": "m1"}]
        cja.getDimensions.return_value = [{"id": "d1"}]
        cja.getFilters.return_value = []
        cja.getCalculatedMetrics.return_value = []

        f = io.StringIO()
        with redirect_stdout(f):
            result = describe_dataview("dv_1", output_format="csv")

        assert result is True
        rows = list(csv.DictReader(io.StringIO(f.getvalue())))
        assert len(rows) == 1
        assert rows[0]["description"] == ""

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_describe_dataview_graceful_segment_failure(self, mock_profile, mock_configure, mock_cjapy):
        """If getFilters fails, segments count shows as N/A."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {
            "id": "dv_1",
            "name": "Test",
            "owner": {"name": "Jane"},
            "description": "",
            "parentDataGroupId": "conn_1",
            "created": "2025-01-01",
            "modified": "2025-06-01",
        }
        cja.getMetrics.return_value = [{"id": "m1"}]
        cja.getDimensions.return_value = [{"id": "d1"}]
        cja.getFilters.side_effect = Exception("API error")
        cja.getCalculatedMetrics.return_value = []

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = describe_dataview("dv_1", output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["dataView"]["components"]["segments"] == "N/A"
        assert output["dataView"]["components"]["total"] == "N/A"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_describe_dataview_not_found(self, mock_profile, mock_configure, mock_cjapy):
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = None

        import io
        from contextlib import redirect_stderr, redirect_stdout

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = describe_dataview("dv_nonexistent", output_format="json")

        assert result is False
        output = json.loads(err.getvalue())
        assert "error" in output
        assert output["error_type"] == "not_found"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_describe_dataview_unknown_placeholder_with_error_diagnostic_treated_as_not_found(
        self,
        mock_profile,
        mock_configure,
        mock_cjapy,
    ):
        """Unknown lookup placeholders with diagnostics must fail as not_found."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_missing", "name": "Unknown", "error": "not found"}

        import io
        from contextlib import redirect_stderr, redirect_stdout

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = describe_dataview("dv_missing", output_format="json")

        assert result is False
        payload = json.loads(err.getvalue())
        assert payload["error_type"] == "not_found"
        assert "dv_missing" in payload["error"]

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_describe_dataview_id_plus_error_only_payload_treated_as_not_found(
        self,
        mock_profile,
        mock_configure,
        mock_cjapy,
    ):
        """id+error-only lookup payloads must fail as not_found."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_missing", "error": "not found"}

        import io
        from contextlib import redirect_stderr, redirect_stdout

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = describe_dataview("dv_missing", output_format="json")

        assert result is False
        payload = json.loads(err.getvalue())
        assert payload["error_type"] == "not_found"
        assert "dv_missing" in payload["error"]
        cja.getMetrics.assert_not_called()
        cja.getDimensions.assert_not_called()
        cja.getFilters.assert_not_called()
        cja.getCalculatedMetrics.assert_not_called()

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_describe_dataview_id_only_payload_treated_as_not_found(
        self,
        mock_profile,
        mock_configure,
        mock_cjapy,
    ):
        """id-only lookup payloads must fail as not_found due missing metadata."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_missing"}

        import io
        from contextlib import redirect_stderr, redirect_stdout

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = describe_dataview("dv_missing", output_format="json")

        assert result is False
        payload = json.loads(err.getvalue())
        assert payload["error_type"] == "not_found"
        assert "dv_missing" in payload["error"]
        cja.getMetrics.assert_not_called()
        cja.getDimensions.assert_not_called()
        cja.getFilters.assert_not_called()
        cja.getCalculatedMetrics.assert_not_called()

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_describe_dataview_error_payload_treated_as_not_found(self, mock_profile, mock_configure, mock_cjapy):
        """API error-shaped payloads from getDataView should fail as not_found."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {
            "statusCode": 404,
            "errorCode": "resource_not_found",
            "errorDescription": "Data view was not found",
        }

        import io
        from contextlib import redirect_stderr, redirect_stdout

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = describe_dataview("dv_missing", output_format="json")

        assert result is False
        payload = json.loads(err.getvalue())
        assert payload["error_type"] == "not_found"
        assert "dv_missing" in payload["error"]

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_describe_dataview_apierror_status_not_found(self, mock_profile, mock_configure, mock_cjapy):
        """Raised getDataView APIError(403/404) should preserve not_found contract."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.side_effect = APIError("Forbidden", status_code=403, operation="getDataView")

        import io
        from contextlib import redirect_stderr, redirect_stdout

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = describe_dataview("dv_hidden", output_format="json")

        assert result is False
        payload = json.loads(err.getvalue())
        assert payload["error_type"] == "not_found"
        assert payload["error"] == "Data view 'dv_hidden' not found"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_describe_dataview_apierror_message_not_found(self, mock_profile, mock_configure, mock_cjapy):
        """Message-only APIError markers from getDataView should map to not_found."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.side_effect = APIError("resource_not_found for data view lookup")

        import io
        from contextlib import redirect_stderr, redirect_stdout

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = describe_dataview("dv_missing", output_format="json")

        assert result is False
        payload = json.loads(err.getvalue())
        assert payload["error_type"] == "not_found"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_describe_dataview_apierror_5xx_remains_connectivity_error(self, mock_profile, mock_configure, mock_cjapy):
        """Non-not-found API errors should remain connectivity failures."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.side_effect = APIError("Backend unavailable", status_code=503, operation="getDataView")

        import io
        from contextlib import redirect_stderr, redirect_stdout

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = describe_dataview("dv_flaky", output_format="json")

        assert result is False
        payload = json.loads(err.getvalue())
        assert payload["error_type"] == "connectivity_error"
        assert "Failed to connect to CJA API" in payload["error"]

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_describe_dataview_na_identity_fields_treated_as_not_found(self, mock_profile, mock_configure, mock_cjapy):
        """NA-like id/name payloads should fail as not_found, not generic command failures."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value

        import pandas as pd

        cja.getDataView.return_value = {"id": pd.NA, "name": pd.NA, "description": "missing identity"}

        import io
        from contextlib import redirect_stderr, redirect_stdout

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = describe_dataview("dv_missing", output_format="json")

        assert result is False
        payload = json.loads(err.getvalue())
        assert payload["error_type"] == "not_found"
        cja.getMetrics.assert_not_called()
        cja.getDimensions.assert_not_called()
        cja.getFilters.assert_not_called()
        cja.getCalculatedMetrics.assert_not_called()

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_describe_dataview_component_error_payload_reports_na(self, mock_profile, mock_configure, mock_cjapy):
        """Error-shaped component payloads should degrade to N/A counts, not numeric zero."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {
            "id": "dv_1",
            "name": "Test View",
            "owner": {"name": "Jane"},
            "description": "Desc",
            "parentDataGroupId": "conn_1",
            "created": "2025-01-01",
            "modified": "2025-06-01",
        }
        cja.getMetrics.return_value = {"statusCode": 500, "message": "backend timeout"}
        cja.getDimensions.return_value = [{"id": "d1"}]
        cja.getFilters.return_value = []
        cja.getCalculatedMetrics.return_value = []

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = describe_dataview("dv_1", output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        components = output["dataView"]["components"]
        assert components["metrics"] == "N/A"
        assert components["dimensions"] == 1
        assert components["total"] == "N/A"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_describe_dataview_empty_typed_component_tables_count_as_zero(
        self,
        mock_profile,
        mock_configure,
        mock_cjapy,
    ):
        """Empty typed DataFrames are valid no-result responses and should count as zero."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {
            "id": "dv_1",
            "name": "Test View",
            "owner": {"name": "Jane"},
            "description": "Desc",
            "parentDataGroupId": "conn_1",
            "created": "2025-01-01",
            "modified": "2025-06-01",
        }
        import pandas as pd

        cja.getMetrics.return_value = pd.DataFrame(columns=["id", "name", "type"])
        cja.getDimensions.return_value = pd.DataFrame(columns=["id", "name", "type"])
        cja.getFilters.return_value = pd.DataFrame(columns=["id", "name", "type"])
        cja.getCalculatedMetrics.return_value = pd.DataFrame(columns=["id", "name", "type"])

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = describe_dataview("dv_1", output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        components = output["dataView"]["components"]
        assert components["metrics"] == 0
        assert components["dimensions"] == 0
        assert components["segments"] == 0
        assert components["calculatedMetrics"] == 0
        assert components["total"] == 0


@pytest.mark.parametrize(
    ("command", "component_method"),
    [
        (list_metrics, "getMetrics"),
        (list_dimensions, "getDimensions"),
        (list_segments, "getFilters"),
        (list_calculated_metrics, "getCalculatedMetrics"),
    ],
)
@patch("cja_auto_sdr.generator.cjapy")
@patch("cja_auto_sdr.generator.configure_cjapy")
@patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
def test_list_inspection_commands_na_identity_fields_treated_as_not_found(
    mock_profile,
    mock_configure,
    mock_cjapy,
    command,
    component_method,
):
    """All list inspection commands should reject NA-like dataview identity payloads as not_found."""
    mock_configure.return_value = (True, "config", None)
    cja = mock_cjapy.CJA.return_value

    import pandas as pd

    cja.getDataView.return_value = {"id": pd.NA, "name": pd.NA}
    getattr(cja, component_method).return_value = []

    import io
    from contextlib import redirect_stderr, redirect_stdout

    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        result = command("dv_missing", output_format="json")

    assert result is False
    payload = json.loads(err.getvalue())
    assert payload["error_type"] == "not_found"
    assert getattr(cja, component_method).call_count == 0


@pytest.mark.parametrize(
    ("command", "component_method"),
    [
        (list_metrics, "getMetrics"),
        (list_dimensions, "getDimensions"),
        (list_segments, "getFilters"),
        (list_calculated_metrics, "getCalculatedMetrics"),
    ],
)
@patch("cja_auto_sdr.generator.cjapy")
@patch("cja_auto_sdr.generator.configure_cjapy")
@patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
def test_list_inspection_commands_get_dataview_apierror_status_treated_as_not_found(
    mock_profile,
    mock_configure,
    mock_cjapy,
    command,
    component_method,
):
    """Raised getDataView APIError(403/404) should fail with not_found for all list inspection commands."""
    mock_configure.return_value = (True, "config", None)
    cja = mock_cjapy.CJA.return_value
    cja.getDataView.side_effect = APIError("Forbidden", status_code=403, operation="getDataView")
    getattr(cja, component_method).return_value = []

    import io
    from contextlib import redirect_stderr, redirect_stdout

    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        result = command("dv_hidden", output_format="json")

    assert result is False
    payload = json.loads(err.getvalue())
    assert payload["error_type"] == "not_found"
    assert getattr(cja, component_method).call_count == 0


@pytest.mark.parametrize(
    ("command", "component_method"),
    [
        (list_metrics, "getMetrics"),
        (list_dimensions, "getDimensions"),
        (list_segments, "getFilters"),
        (list_calculated_metrics, "getCalculatedMetrics"),
    ],
)
@patch("cja_auto_sdr.generator.cjapy")
@patch("cja_auto_sdr.generator.configure_cjapy")
@patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
def test_list_inspection_commands_get_dataview_non_api_wrapper_404_treated_as_not_found(
    mock_profile,
    mock_configure,
    mock_cjapy,
    command,
    component_method,
):
    """Non-API wrappers with 403/404 metadata should still fail as not_found."""
    mock_configure.return_value = (True, "config", None)
    cja = mock_cjapy.CJA.return_value

    class WrappedLookupFailure(RuntimeError):
        pass

    lookup_error = WrappedLookupFailure("wrapped cjapy failure")
    lookup_error.response = {"error": {"statusCode": "404"}}  # type: ignore[attr-defined]
    cja.getDataView.side_effect = lookup_error
    getattr(cja, component_method).return_value = []

    import io
    from contextlib import redirect_stderr, redirect_stdout

    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        result = command("dv_hidden", output_format="json")

    assert result is False
    payload = json.loads(err.getvalue())
    assert payload["error_type"] == "not_found"
    assert getattr(cja, component_method).call_count == 0


@pytest.mark.parametrize(
    ("command", "component_method"),
    [
        (list_metrics, "getMetrics"),
        (list_dimensions, "getDimensions"),
        (list_segments, "getFilters"),
        (list_calculated_metrics, "getCalculatedMetrics"),
    ],
)
@patch("cja_auto_sdr.generator.cjapy")
@patch("cja_auto_sdr.generator.configure_cjapy")
@patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
def test_list_inspection_commands_get_dataview_apierror_message_treated_as_not_found(
    mock_profile,
    mock_configure,
    mock_cjapy,
    command,
    component_method,
):
    """Message-only not_found APIError from getDataView should preserve not_found typing."""
    mock_configure.return_value = (True, "config", None)
    cja = mock_cjapy.CJA.return_value
    cja.getDataView.side_effect = APIError("resource_not_found while resolving data view")
    getattr(cja, component_method).return_value = []

    import io
    from contextlib import redirect_stderr, redirect_stdout

    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        result = command("dv_missing", output_format="json")

    assert result is False
    payload = json.loads(err.getvalue())
    assert payload["error_type"] == "not_found"
    assert getattr(cja, component_method).call_count == 0


@pytest.mark.parametrize(
    ("command", "component_method", "component_key", "component_payload"),
    [
        (
            list_metrics,
            "getMetrics",
            "metrics",
            [{"id": "m1", "name": "Metric One", "type": "decimal", "description": ""}],
        ),
        (
            list_dimensions,
            "getDimensions",
            "dimensions",
            [{"id": "d1", "name": "Dimension One", "type": "string", "description": ""}],
        ),
        (
            list_segments,
            "getFilters",
            "segments",
            [{"id": "s1", "name": "Segment One"}],
        ),
        (
            list_calculated_metrics,
            "getCalculatedMetrics",
            "calculatedMetrics",
            [{"id": "cm1", "name": "Calc One"}],
        ),
    ],
)
@patch("cja_auto_sdr.generator.cjapy")
@patch("cja_auto_sdr.generator.configure_cjapy")
@patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
def test_list_inspection_commands_use_canonical_dataview_name_over_preferred_query(
    mock_profile,
    mock_configure,
    mock_cjapy,
    command,
    component_method,
    component_key,
    component_payload,
):
    """Inspection list output should use the canonical API name, not raw query text."""
    mock_configure.return_value = (True, "config", None)
    cja = mock_cjapy.CJA.return_value
    cja.getDataView.return_value = {"id": "dv_1", "name": "Production Web"}
    getattr(cja, component_method).return_value = component_payload

    import io
    from contextlib import redirect_stdout

    out = io.StringIO()
    with redirect_stdout(out):
        result = command("dv_1", output_format="json", data_view_name="Prod Web")

    assert result is True
    payload = json.loads(out.getvalue())
    assert payload["dataViewId"] == "dv_1"
    assert payload["dataViewName"] == "Production Web"
    assert payload["count"] == 1
    assert len(payload[component_key]) == 1


class TestListMetrics:
    """Tests for --list-metrics command."""

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_metrics_json(self, mock_profile, mock_configure, mock_cjapy):
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getMetrics.return_value = pd.DataFrame(
            [
                {"id": "metrics/pageviews", "name": "Page Views", "type": "decimal", "description": "Total views"},
                {"id": "metrics/visits", "name": "Visits", "type": "decimal", "description": "Unique visits"},
            ]
        )

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_metrics("dv_1", output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["dataViewId"] == "dv_1"
        assert output["count"] == 2
        assert output["metrics"][0]["id"] in ("metrics/pageviews", "metrics/visits")
        cja.getMetrics.assert_called_once_with("dv_1", inclType="hidden", full=True)

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_metrics_json_normalizes_nullable_fields(self, mock_profile, mock_configure, mock_cjapy):
        """Null-like metric type/description values should normalize for strict JSON output."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getMetrics.return_value = pd.DataFrame(
            [
                {
                    "id": "metrics/revenue",
                    "name": "Revenue",
                    "type": float("nan"),
                    "description": pd.NA,
                },
            ]
        )

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_metrics("dv_1", output_format="json")

        assert result is True
        output_text = f.getvalue()
        assert '"type": NaN' not in output_text
        assert '"description": NaN' not in output_text
        output = json.loads(output_text)
        assert output["metrics"][0]["type"] == "N/A"
        assert output["metrics"][0]["description"] == ""

    @patch("cja_auto_sdr.generator._build_metric_display_row")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_metrics_json_output_contract_failure_emits_structured_error(
        self,
        mock_profile,
        mock_configure,
        mock_cjapy,
        mock_row_builder,
    ):
        """Unexpected non-JSON values should fail with output_contract errors."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        cja.getMetrics.return_value = [{"id": "metrics/raw", "name": "Raw Metric"}]
        mock_row_builder.return_value = {
            "id": "metrics/raw",
            "name": "Raw Metric",
            "type": float("nan"),
            "description": "",
        }

        import io
        from contextlib import redirect_stderr, redirect_stdout

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = list_metrics("dv_1", output_format="json")

        assert result is False
        payload = json.loads(err.getvalue())
        assert payload["error_type"] == "output_contract"
        assert "non-JSON-compliant" in payload["error"]

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_metrics_csv(self, mock_profile, mock_configure, mock_cjapy):
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getMetrics.return_value = pd.DataFrame(
            [
                {"id": "metrics/pageviews", "name": "Page Views", "type": "decimal", "description": ""},
            ]
        )

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_metrics("dv_1", output_format="csv")

        assert result is True
        lines = f.getvalue().strip().split("\n")
        assert lines[0] == "id,name,type,description"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_metrics_empty(self, mock_profile, mock_configure, mock_cjapy):
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getMetrics.return_value = pd.DataFrame()

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_metrics("dv_1", output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["count"] == 0

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_metrics_empty_typed_dataframe_is_not_error(self, mock_profile, mock_configure, mock_cjapy):
        """A zero-row metrics table with standard columns is a valid empty result."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getMetrics.return_value = pd.DataFrame(columns=["id", "name", "type", "description"])

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_metrics("dv_1", output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["count"] == 0
        assert output["metrics"] == []

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_metrics_invalid_dataview_fails_not_found(self, mock_profile, mock_configure, mock_cjapy):
        """Invalid/inaccessible data views should fail instead of returning empty metrics."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"statusCode": 404, "errorCode": "not_found"}
        import pandas as pd

        cja.getMetrics.return_value = pd.DataFrame()

        import io
        from contextlib import redirect_stderr, redirect_stdout

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = list_metrics("dv_bad", output_format="json")

        assert result is False
        payload = json.loads(err.getvalue())
        assert payload["error_type"] == "not_found"
        cja.getMetrics.assert_not_called()

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_metrics_component_error_payload_fails_not_found(self, mock_profile, mock_configure, mock_cjapy):
        """Error-shaped metrics payloads should fail, not produce count=0 success."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        cja.getMetrics.return_value = {"statusCode": 403, "errorCode": "forbidden"}

        import io
        from contextlib import redirect_stderr, redirect_stdout

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = list_metrics("dv_1", output_format="json")

        assert result is False
        payload = json.loads(err.getvalue())
        assert payload["error_type"] == "not_found"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_metrics_with_filter(self, mock_profile, mock_configure, mock_cjapy):
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getMetrics.return_value = pd.DataFrame(
            [
                {"id": "metrics/pageviews", "name": "Page Views", "type": "decimal", "description": ""},
                {"id": "metrics/revenue", "name": "Revenue", "type": "currency", "description": ""},
            ]
        )

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_metrics("dv_1", output_format="json", filter_pattern="revenue")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["count"] == 1
        assert output["metrics"][0]["name"] == "Revenue"


class TestListDimensions:
    """Tests for --list-dimensions command."""

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_dimensions_json(self, mock_profile, mock_configure, mock_cjapy):
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getDimensions.return_value = pd.DataFrame(
            [
                {"id": "variables/page", "name": "Page", "type": "string", "description": "Page URL"},
                {"id": "variables/browser", "name": "Browser", "type": "string", "description": ""},
            ]
        )

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_dimensions("dv_1", output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["dataViewId"] == "dv_1"
        assert output["count"] == 2
        assert "dimensions" in output
        cja.getDimensions.assert_called_once_with("dv_1", inclType="hidden", full=True)

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_dimensions_json_normalizes_nullable_fields(self, mock_profile, mock_configure, mock_cjapy):
        """Null-like dimension type/description values should normalize for strict JSON output."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getDimensions.return_value = pd.DataFrame(
            [
                {
                    "id": "variables/browser",
                    "name": "Browser",
                    "type": pd.NA,
                    "description": float("nan"),
                },
            ]
        )

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_dimensions("dv_1", output_format="json")

        assert result is True
        output_text = f.getvalue()
        assert '"type": NaN' not in output_text
        assert '"description": NaN' not in output_text
        output = json.loads(output_text)
        assert output["dimensions"][0]["type"] == "N/A"
        assert output["dimensions"][0]["description"] == ""

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_dimensions_csv(self, mock_profile, mock_configure, mock_cjapy):
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getDimensions.return_value = pd.DataFrame(
            [
                {"id": "variables/page", "name": "Page", "type": "string", "description": ""},
            ]
        )

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_dimensions("dv_1", output_format="csv")

        assert result is True
        lines = f.getvalue().strip().split("\n")
        assert lines[0] == "id,name,type,description"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_dimensions_empty(self, mock_profile, mock_configure, mock_cjapy):
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getDimensions.return_value = pd.DataFrame()

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_dimensions("dv_1", output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["count"] == 0

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_dimensions_empty_typed_dataframe_is_not_error(self, mock_profile, mock_configure, mock_cjapy):
        """A zero-row dimensions table with standard columns is a valid empty result."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getDimensions.return_value = pd.DataFrame(columns=["id", "name", "type", "description"])

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_dimensions("dv_1", output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["count"] == 0
        assert output["dimensions"] == []

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_dimensions_invalid_dataview_fails_not_found(self, mock_profile, mock_configure, mock_cjapy):
        """Invalid/inaccessible data views should fail instead of returning empty dimensions."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"statusCode": 403, "message": "forbidden"}
        import pandas as pd

        cja.getDimensions.return_value = pd.DataFrame()

        import io
        from contextlib import redirect_stderr, redirect_stdout

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = list_dimensions("dv_bad", output_format="json")

        assert result is False
        payload = json.loads(err.getvalue())
        assert payload["error_type"] == "not_found"
        cja.getDimensions.assert_not_called()

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_dimensions_component_error_payload_fails_not_found(self, mock_profile, mock_configure, mock_cjapy):
        """Error-shaped dimensions payloads should fail, not produce count=0 success."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        cja.getDimensions.return_value = {"statusCode": 403, "message": "forbidden"}

        import io
        from contextlib import redirect_stderr, redirect_stdout

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = list_dimensions("dv_1", output_format="json")

        assert result is False
        payload = json.loads(err.getvalue())
        assert payload["error_type"] == "not_found"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_dimensions_with_filter(self, mock_profile, mock_configure, mock_cjapy):
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getDimensions.return_value = pd.DataFrame(
            [
                {"id": "variables/page", "name": "Page", "type": "string", "description": ""},
                {"id": "variables/browser", "name": "Browser", "type": "string", "description": ""},
            ]
        )

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_dimensions("dv_1", output_format="json", filter_pattern="browser")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["count"] == 1
        assert output["dimensions"][0]["name"] == "Browser"


class TestListSegments:
    """Tests for --list-segments command."""

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_segments_json(self, mock_profile, mock_configure, mock_cjapy):
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getFilters.return_value = pd.DataFrame(
            [
                {
                    "id": "s1",
                    "name": "Mobile",
                    "owner": {"name": "Jane"},
                    "description": "Mobile visitors",
                    "approved": True,
                    "tags": [{"name": "prod"}],
                    "created": "2025-01-01",
                    "modified": "2025-06-01",
                },
            ]
        )

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_segments("dv_1", output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["dataViewId"] == "dv_1"
        assert output["count"] == 1
        seg = output["segments"][0]
        assert seg["name"] == "Mobile"
        assert seg["owner"] == "Jane"
        assert seg["approved"] is True
        assert seg["tags"] == ["prod"]
        cja.getFilters.assert_called_once_with(dataIds="dv_1", full=True)

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_segments_owner_and_date_aliases_json(self, mock_profile, mock_configure, mock_cjapy):
        """ownerFullName/createdDate/modifiedDate aliases should populate governance fields."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getFilters.return_value = pd.DataFrame(
            [
                {
                    "id": "s1",
                    "name": "Mobile",
                    "ownerFullName": "Alias Owner",
                    "description": "Alias metadata segment",
                    "approved": True,
                    "tags": [],
                    "createdDate": "2025-02-01",
                    "modifiedDate": "2025-07-15",
                },
            ]
        )

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_segments("dv_1", output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        seg = output["segments"][0]
        assert seg["owner"] == "Alias Owner"
        assert seg["created"] == "2025-02-01"
        assert seg["modified"] == "2025-07-15"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_segments_json_normalizes_nullable_description(self, mock_profile, mock_configure, mock_cjapy):
        """Null-like segment descriptions should be normalized before JSON serialization."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getFilters.return_value = pd.DataFrame(
            [
                {
                    "id": "s1",
                    "name": "Nullable Description Segment",
                    "description": float("nan"),
                    "approved": True,
                    "tags": [],
                },
            ]
        )

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_segments("dv_1", output_format="json")

        assert result is True
        output_text = f.getvalue()
        assert '"description": NaN' not in output_text
        output = json.loads(output_text)
        assert output["segments"][0]["description"] == ""

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_segments_mixed_tags_and_missing_owner_values(self, mock_profile, mock_configure, mock_cjapy):
        """Mixed tagged/untagged rows with NaN/pd.NA values should normalize without errors."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getFilters.return_value = pd.DataFrame(
            [
                {
                    "id": "s1",
                    "name": "Tagged Segment",
                    "owner": {"name": "Owner One"},
                    "approved": True,
                    "tags": [{"name": "prod"}],
                    "created": "2025-01-01",
                    "modified": "2025-01-02",
                },
                {
                    "id": "s2",
                    "name": "Untagged Segment",
                    "owner": float("nan"),
                    "ownerFullName": "Alias Owner",
                    "approved": False,
                    "tags": float("nan"),
                    "createdDate": "2025-01-03",
                    "modifiedDate": "2025-01-04",
                },
                {
                    "id": "s3",
                    "name": "NA Owner Segment",
                    "owner": pd.NA,
                    "ownerFullName": "Alias Owner NA",
                    "approved": False,
                    "tags": pd.NA,
                    "createdDate": "2025-01-05",
                    "modifiedDate": "2025-01-06",
                },
            ]
        )

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_segments("dv_1", output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        segments_by_id = {segment["id"]: segment for segment in output["segments"]}
        assert segments_by_id["s1"]["tags"] == ["prod"]
        assert segments_by_id["s2"]["tags"] == []
        assert segments_by_id["s3"]["tags"] == []
        assert segments_by_id["s2"]["owner"] == "Alias Owner"
        assert segments_by_id["s3"]["owner"] == "Alias Owner NA"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_segments_owner_and_date_aliases_table(self, mock_profile, mock_configure, mock_cjapy):
        """Alias-based governance metadata should also appear in table output."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getFilters.return_value = pd.DataFrame(
            [
                {
                    "id": "s1",
                    "name": "Mobile",
                    "ownerFullName": "Alias Owner",
                    "description": "Alias metadata segment",
                    "approved": True,
                    "tags": [],
                    "createdDate": "2025-02-01",
                    "modifiedDate": "2025-07-15",
                },
            ]
        )

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_segments("dv_1", output_format="table")

        assert result is True
        output = f.getvalue()
        assert "Alias Owner" in output

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_segments_csv(self, mock_profile, mock_configure, mock_cjapy):
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getFilters.return_value = pd.DataFrame(
            [
                {
                    "id": "s1",
                    "name": "Mobile",
                    "owner": {"name": "Jane"},
                    "description": "",
                    "approved": False,
                    "tags": [],
                    "created": "2025-01-01",
                    "modified": "2025-06-01",
                },
            ]
        )

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_segments("dv_1", output_format="csv")

        assert result is True
        lines = f.getvalue().strip().split("\n")
        assert "id" in lines[0] and "approved" in lines[0]

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_segments_table_approved_rendering(self, mock_profile, mock_configure, mock_cjapy):
        """approved renders as Yes/No in table mode."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getFilters.return_value = pd.DataFrame(
            [
                {
                    "id": "s1",
                    "name": "Approved Seg",
                    "owner": {"name": "Jane"},
                    "description": "",
                    "approved": True,
                    "tags": [],
                    "created": "",
                    "modified": "",
                },
                {
                    "id": "s2",
                    "name": "Unapproved Seg",
                    "owner": {"name": "Bob"},
                    "description": "",
                    "approved": False,
                    "tags": [],
                    "created": "",
                    "modified": "",
                },
            ]
        )

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_segments("dv_1", output_format="table")

        assert result is True
        output = f.getvalue()
        assert "Yes" in output
        assert "No" in output

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_segments_empty(self, mock_profile, mock_configure, mock_cjapy):
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getFilters.return_value = pd.DataFrame()

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_segments("dv_1", output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["count"] == 0

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_segments_empty_typed_dataframe_is_not_error(self, mock_profile, mock_configure, mock_cjapy):
        """A zero-row segments table with typed columns is a valid empty result."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getFilters.return_value = pd.DataFrame(columns=["id", "name", "type"])

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_segments("dv_1", output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["count"] == 0
        assert output["segments"] == []

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_segments_invalid_dataview_fails_not_found(self, mock_profile, mock_configure, mock_cjapy):
        """Invalid/inaccessible data views should fail instead of returning empty segments."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"errorCode": "not_found", "errorDescription": "missing"}
        import pandas as pd

        cja.getFilters.return_value = pd.DataFrame()

        import io
        from contextlib import redirect_stderr, redirect_stdout

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = list_segments("dv_bad", output_format="json")

        assert result is False
        payload = json.loads(err.getvalue())
        assert payload["error_type"] == "not_found"
        cja.getFilters.assert_not_called()

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_segments_component_error_payload_fails_not_found(self, mock_profile, mock_configure, mock_cjapy):
        """Error-shaped segments payloads should fail, not produce count=0 success."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        cja.getFilters.return_value = {"statusCode": 403, "errorCode": "forbidden"}

        import io
        from contextlib import redirect_stderr, redirect_stdout

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = list_segments("dv_1", output_format="json")

        assert result is False
        payload = json.loads(err.getvalue())
        assert payload["error_type"] == "not_found"


class TestListCalculatedMetrics:
    """Tests for --list-calculated-metrics command."""

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_calc_metrics_json(self, mock_profile, mock_configure, mock_cjapy):
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getCalculatedMetrics.return_value = pd.DataFrame(
            [
                {
                    "id": "cm1",
                    "name": "Bounce Rate",
                    "owner": {"name": "Jane"},
                    "description": "Bounce rate calc",
                    "type": "percent",
                    "polarity": "negative",
                    "precision": 2,
                    "approved": True,
                    "tags": [],
                    "created": "2025-01-01",
                    "modified": "2025-06-01",
                },
            ]
        )

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_calculated_metrics("dv_1", output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["dataViewId"] == "dv_1"
        assert output["count"] == 1
        cm = output["calculatedMetrics"][0]
        assert cm["name"] == "Bounce Rate"
        assert cm["polarity"] == "negative"
        assert cm["type"] == "percent"
        assert cm["precision"] == 2
        cja.getCalculatedMetrics.assert_called_once_with(dataIds="dv_1", full=True)

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_calc_metrics_owner_and_date_aliases_json(self, mock_profile, mock_configure, mock_cjapy):
        """Alias owner/date fields should be normalized in calculated metrics JSON output."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getCalculatedMetrics.return_value = pd.DataFrame(
            [
                {
                    "id": "cm1",
                    "name": "Bounce Rate",
                    "ownerFullName": "Alias Owner",
                    "description": "Bounce rate calc",
                    "type": "percent",
                    "polarity": "negative",
                    "precision": 2,
                    "approved": True,
                    "tags": [],
                    "createdDate": "2025-01-01",
                    "modifiedDate": "2025-06-01",
                },
            ]
        )

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_calculated_metrics("dv_1", output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        cm = output["calculatedMetrics"][0]
        assert cm["owner"] == "Alias Owner"
        assert cm["created"] == "2025-01-01"
        assert cm["modified"] == "2025-06-01"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_calc_metrics_json_normalizes_nullable_fields(self, mock_profile, mock_configure, mock_cjapy):
        """Null-like calculated metric fields should be normalized before JSON emission."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getCalculatedMetrics.return_value = pd.DataFrame(
            [
                {
                    "id": "cm_nullable",
                    "name": "Nullable Metric",
                    "description": float("nan"),
                    "type": pd.NA,
                    "polarity": float("nan"),
                    "precision": float("nan"),
                    "approved": True,
                    "tags": [],
                },
            ]
        )

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_calculated_metrics("dv_1", output_format="json")

        assert result is True
        output_text = f.getvalue()
        assert '"description": NaN' not in output_text
        assert '"type": NaN' not in output_text
        assert '"polarity": NaN' not in output_text
        assert '"precision": NaN' not in output_text
        output = json.loads(output_text)
        row = output["calculatedMetrics"][0]
        assert row["description"] == ""
        assert row["type"] == ""
        assert row["polarity"] == ""
        assert row["precision"] == 0

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_calc_metrics_mixed_tags_and_missing_owner_values(self, mock_profile, mock_configure, mock_cjapy):
        """Mixed tags and missing owner scalars should normalize without raising TypeError."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getCalculatedMetrics.return_value = pd.DataFrame(
            [
                {
                    "id": "cm1",
                    "name": "Tagged Metric",
                    "owner": {"name": "Owner One"},
                    "description": "Tagged metric",
                    "type": "percent",
                    "polarity": "negative",
                    "precision": 2,
                    "approved": True,
                    "tags": [{"name": "prod"}],
                    "created": "2025-01-01",
                    "modified": "2025-01-02",
                },
                {
                    "id": "cm2",
                    "name": "Untagged Metric",
                    "owner": float("nan"),
                    "ownerFullName": "Alias Metric Owner",
                    "description": "Untagged metric",
                    "type": "number",
                    "polarity": "positive",
                    "precision": 0,
                    "approved": False,
                    "tags": float("nan"),
                    "createdDate": "2025-01-03",
                    "modifiedDate": "2025-01-04",
                },
                {
                    "id": "cm3",
                    "name": "NA Owner Metric",
                    "owner": pd.NA,
                    "ownerFullName": "Alias Metric Owner NA",
                    "description": "pd.NA owner",
                    "type": "number",
                    "polarity": "positive",
                    "precision": 0,
                    "approved": False,
                    "tags": pd.NA,
                    "createdDate": "2025-01-05",
                    "modifiedDate": "2025-01-06",
                },
            ]
        )

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_calculated_metrics("dv_1", output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        metrics_by_id = {metric["id"]: metric for metric in output["calculatedMetrics"]}
        assert metrics_by_id["cm1"]["tags"] == ["prod"]
        assert metrics_by_id["cm2"]["tags"] == []
        assert metrics_by_id["cm3"]["tags"] == []
        assert metrics_by_id["cm2"]["owner"] == "Alias Metric Owner"
        assert metrics_by_id["cm3"]["owner"] == "Alias Metric Owner NA"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_calc_metrics_owner_and_date_aliases_csv(self, mock_profile, mock_configure, mock_cjapy):
        """Alias owner/date fields should propagate into calculated metrics CSV output."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getCalculatedMetrics.return_value = pd.DataFrame(
            [
                {
                    "id": "cm1",
                    "name": "Bounce Rate",
                    "ownerFullName": "Alias Owner",
                    "description": "Bounce rate calc",
                    "type": "percent",
                    "polarity": "negative",
                    "precision": 2,
                    "approved": True,
                    "tags": [],
                    "createdDate": "2025-01-01",
                    "modifiedDate": "2025-06-01",
                },
            ]
        )

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_calculated_metrics("dv_1", output_format="csv")

        assert result is True
        lines = f.getvalue().strip().split("\n")
        assert "Alias Owner" in lines[1]
        assert "2025-01-01" in lines[1]
        assert "2025-06-01" in lines[1]

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_calc_metrics_csv(self, mock_profile, mock_configure, mock_cjapy):
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getCalculatedMetrics.return_value = pd.DataFrame(
            [
                {
                    "id": "cm1",
                    "name": "Bounce Rate",
                    "owner": {"name": "Jane"},
                    "description": "",
                    "type": "percent",
                    "polarity": "negative",
                    "precision": 2,
                    "approved": True,
                    "tags": [],
                    "created": "2025-01-01",
                    "modified": "2025-06-01",
                },
            ]
        )

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_calculated_metrics("dv_1", output_format="csv")

        assert result is True
        lines = f.getvalue().strip().split("\n")
        assert "polarity" in lines[0] and "precision" in lines[0]

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_calc_metrics_table_omits_precision(self, mock_profile, mock_configure, mock_cjapy):
        """Table output omits precision column to save width."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getCalculatedMetrics.return_value = pd.DataFrame(
            [
                {
                    "id": "cm1",
                    "name": "Bounce Rate",
                    "owner": {"name": "Jane"},
                    "description": "",
                    "type": "percent",
                    "polarity": "negative",
                    "precision": 2,
                    "approved": True,
                    "tags": [],
                    "created": "",
                    "modified": "",
                },
            ]
        )

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_calculated_metrics("dv_1", output_format="table")

        assert result is True
        output = f.getvalue()
        assert "Bounce Rate" in output
        # Table should show polarity and approved but NOT precision
        assert "Precision" not in output

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_calc_metrics_empty(self, mock_profile, mock_configure, mock_cjapy):
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getCalculatedMetrics.return_value = pd.DataFrame()

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_calculated_metrics("dv_1", output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["count"] == 0

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_calc_metrics_empty_typed_dataframe_is_not_error(self, mock_profile, mock_configure, mock_cjapy):
        """A zero-row calculated metrics table with standard columns is valid empty data."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        import pandas as pd

        cja.getCalculatedMetrics.return_value = pd.DataFrame(columns=["id", "name", "type", "description"])

        import io
        from contextlib import redirect_stdout

        f = io.StringIO()
        with redirect_stdout(f):
            result = list_calculated_metrics("dv_1", output_format="json")

        assert result is True
        output = json.loads(f.getvalue())
        assert output["count"] == 0
        assert output["calculatedMetrics"] == []

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_calc_metrics_invalid_dataview_fails_not_found(self, mock_profile, mock_configure, mock_cjapy):
        """Invalid/inaccessible data views should fail instead of returning empty calculated metrics."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"statusCode": 403, "message": "forbidden"}
        import pandas as pd

        cja.getCalculatedMetrics.return_value = pd.DataFrame()

        import io
        from contextlib import redirect_stderr, redirect_stdout

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = list_calculated_metrics("dv_bad", output_format="json")

        assert result is False
        payload = json.loads(err.getvalue())
        assert payload["error_type"] == "not_found"
        cja.getCalculatedMetrics.assert_not_called()

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    @patch("cja_auto_sdr.generator.resolve_active_profile", return_value=None)
    def test_list_calc_metrics_component_error_payload_fails_not_found(
        self,
        mock_profile,
        mock_configure,
        mock_cjapy,
    ):
        """Error-shaped calculated metrics payloads should fail, not produce count=0 success."""
        mock_configure.return_value = (True, "config", None)
        cja = mock_cjapy.CJA.return_value
        cja.getDataView.return_value = {"id": "dv_1", "name": "Test View"}
        cja.getCalculatedMetrics.return_value = {"statusCode": 403, "message": "forbidden"}

        import io
        from contextlib import redirect_stderr, redirect_stdout

        out = io.StringIO()
        err = io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            result = list_calculated_metrics("dv_1", output_format="json")

        assert result is False
        payload = json.loads(err.getvalue())
        assert payload["error_type"] == "not_found"
