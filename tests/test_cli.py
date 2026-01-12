"""Tests for command-line interface"""
import pytest
import sys
import os
import json
import tempfile
from unittest.mock import patch
import argparse


# Import the function we're testing
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cja_sdr_generator import parse_arguments, generate_sample_config


class TestCLIArguments:
    """Test command-line argument parsing"""

    def test_parse_single_data_view(self):
        """Test parsing a single data view ID"""
        test_args = ['cja_sdr_generator.py', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.data_views == ['dv_12345']
            assert args.batch is False
            assert args.workers == 4

    def test_parse_multiple_data_views(self):
        """Test parsing multiple data view IDs"""
        test_args = ['cja_sdr_generator.py', 'dv_12345', 'dv_67890', 'dv_abcde']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.data_views == ['dv_12345', 'dv_67890', 'dv_abcde']
            assert len(args.data_views) == 3

    def test_parse_batch_flag(self):
        """Test parsing with --batch flag"""
        test_args = ['cja_sdr_generator.py', '--batch', 'dv_12345', 'dv_67890']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.batch is True
            assert args.data_views == ['dv_12345', 'dv_67890']

    def test_parse_custom_workers(self):
        """Test parsing with custom worker count"""
        test_args = ['cja_sdr_generator.py', '--workers', '8', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.workers == 8

    def test_parse_output_dir(self):
        """Test parsing with custom output directory"""
        test_args = ['cja_sdr_generator.py', '--output-dir', './reports', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.output_dir == './reports'

    def test_parse_continue_on_error(self):
        """Test parsing with --continue-on-error flag"""
        test_args = ['cja_sdr_generator.py', '--continue-on-error', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.continue_on_error is True

    def test_parse_log_level(self):
        """Test parsing with custom log level"""
        test_args = ['cja_sdr_generator.py', '--log-level', 'DEBUG', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.log_level == 'DEBUG'

    def test_parse_missing_data_view(self):
        """Test that missing data view ID returns empty list (validated in main)"""
        test_args = ['cja_sdr_generator.py']
        with patch.object(sys, 'argv', test_args):
            # With nargs='*', empty data_views is allowed at parse time
            # Validation is done in main() to support --version flag
            args = parse_arguments()
            assert args.data_views == []

    def test_parse_config_file(self):
        """Test parsing with custom config file"""
        test_args = ['cja_sdr_generator.py', '--config-file', 'custom_config.json', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.config_file == 'custom_config.json'

    def test_default_values(self):
        """Test that default values are set correctly"""
        test_args = ['cja_sdr_generator.py', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.workers == 4
            assert args.output_dir == '.'
            assert args.config_file == 'myconfig.json'
            assert args.continue_on_error is False
            assert args.log_level == 'INFO'
            assert args.production is False

    def test_production_flag(self):
        """Test parsing with --production flag"""
        test_args = ['cja_sdr_generator.py', '--production', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.production is True

    def test_production_with_log_level(self):
        """Test that production and log-level can be specified together"""
        test_args = ['cja_sdr_generator.py', '--production', '--log-level', 'DEBUG', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.production is True
            assert args.log_level == 'DEBUG'  # Both parsed, main() decides priority

    def test_dry_run_flag(self):
        """Test parsing with --dry-run flag"""
        test_args = ['cja_sdr_generator.py', '--dry-run', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.dry_run is True

    def test_dry_run_default_false(self):
        """Test that dry-run is False by default"""
        test_args = ['cja_sdr_generator.py', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.dry_run is False

    def test_dry_run_with_multiple_data_views(self):
        """Test dry-run with multiple data views"""
        test_args = ['cja_sdr_generator.py', '--dry-run', 'dv_12345', 'dv_67890']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.dry_run is True
            assert args.data_views == ['dv_12345', 'dv_67890']

    def test_quiet_flag(self):
        """Test parsing with --quiet flag"""
        test_args = ['cja_sdr_generator.py', '--quiet', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.quiet is True

    def test_quiet_short_flag(self):
        """Test parsing with -q short flag"""
        test_args = ['cja_sdr_generator.py', '-q', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.quiet is True

    def test_quiet_default_false(self):
        """Test that quiet is False by default"""
        test_args = ['cja_sdr_generator.py', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.quiet is False

    def test_version_flag_exits(self):
        """Test that --version flag causes SystemExit"""
        test_args = ['cja_sdr_generator.py', '--version']
        with patch.object(sys, 'argv', test_args):
            with pytest.raises(SystemExit) as exc_info:
                parse_arguments()
            assert exc_info.value.code == 0  # Clean exit

    def test_list_dataviews_flag(self):
        """Test parsing with --list-dataviews flag"""
        test_args = ['cja_sdr_generator.py', '--list-dataviews']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.list_dataviews is True

    def test_list_dataviews_default_false(self):
        """Test that list-dataviews is False by default"""
        test_args = ['cja_sdr_generator.py', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.list_dataviews is False

    def test_skip_validation_flag(self):
        """Test parsing with --skip-validation flag"""
        test_args = ['cja_sdr_generator.py', '--skip-validation', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.skip_validation is True

    def test_skip_validation_default_false(self):
        """Test that skip-validation is False by default"""
        test_args = ['cja_sdr_generator.py', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.skip_validation is False

    def test_skip_validation_with_batch(self):
        """Test skip-validation with batch mode"""
        test_args = ['cja_sdr_generator.py', '--batch', '--skip-validation', 'dv_12345', 'dv_67890']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.skip_validation is True
            assert args.batch is True
            assert args.data_views == ['dv_12345', 'dv_67890']

    def test_sample_config_flag(self):
        """Test parsing with --sample-config flag"""
        test_args = ['cja_sdr_generator.py', '--sample-config']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.sample_config is True

    def test_sample_config_default_false(self):
        """Test that sample-config is False by default"""
        test_args = ['cja_sdr_generator.py', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.sample_config is False


class TestSampleConfig:
    """Test sample configuration file generation"""

    def test_generate_sample_config_creates_file(self):
        """Test that generate_sample_config creates a file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, 'test_config.json')
            result = generate_sample_config(output_path)
            assert result is True
            assert os.path.exists(output_path)

    def test_generate_sample_config_valid_json(self):
        """Test that generated config is valid JSON"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, 'test_config.json')
            generate_sample_config(output_path)
            with open(output_path) as f:
                config = json.load(f)
            assert 'org_id' in config
            assert 'client_id' in config
            assert 'secret' in config

    def test_generate_sample_config_has_both_auth_methods(self):
        """Test that generated config has both OAuth S2S and JWT fields"""
        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = os.path.join(tmpdir, 'test_config.json')
            generate_sample_config(output_path)
            with open(output_path) as f:
                config = json.load(f)
            # OAuth S2S fields
            assert 'scopes' in config
            # JWT fields
            assert 'tech_id' in config
            assert 'private_key' in config


class TestUXImprovements:
    """Test UX improvement features"""

    def test_validate_only_flag(self):
        """Test parsing with --validate-only flag (alias for --dry-run)"""
        test_args = ['cja_sdr_generator.py', '--validate-only', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.dry_run is True

    def test_max_issues_flag(self):
        """Test parsing with --max-issues flag"""
        test_args = ['cja_sdr_generator.py', '--max-issues', '10', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.max_issues == 10

    def test_max_issues_default_zero(self):
        """Test that max-issues defaults to 0 (show all)"""
        test_args = ['cja_sdr_generator.py', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.max_issues == 0

    def test_max_issues_with_skip_validation(self):
        """Test max-issues with skip-validation"""
        test_args = ['cja_sdr_generator.py', '--max-issues', '5', '--skip-validation', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.max_issues == 5
            assert args.skip_validation is True


class TestProcessingResult:
    """Test ProcessingResult dataclass"""

    def test_file_size_formatted_bytes(self):
        """Test file size formatting for bytes"""
        from cja_sdr_generator import ProcessingResult
        result = ProcessingResult(
            data_view_id='dv_test',
            data_view_name='Test',
            success=True,
            duration=1.0,
            file_size_bytes=500
        )
        assert result.file_size_formatted == '500 B'

    def test_file_size_formatted_kilobytes(self):
        """Test file size formatting for kilobytes"""
        from cja_sdr_generator import ProcessingResult
        result = ProcessingResult(
            data_view_id='dv_test',
            data_view_name='Test',
            success=True,
            duration=1.0,
            file_size_bytes=2048
        )
        assert result.file_size_formatted == '2.0 KB'

    def test_file_size_formatted_megabytes(self):
        """Test file size formatting for megabytes"""
        from cja_sdr_generator import ProcessingResult
        result = ProcessingResult(
            data_view_id='dv_test',
            data_view_name='Test',
            success=True,
            duration=1.0,
            file_size_bytes=1048576
        )
        assert result.file_size_formatted == '1.0 MB'

    def test_file_size_formatted_zero(self):
        """Test file size formatting for zero bytes"""
        from cja_sdr_generator import ProcessingResult
        result = ProcessingResult(
            data_view_id='dv_test',
            data_view_name='Test',
            success=True,
            duration=1.0,
            file_size_bytes=0
        )
        assert result.file_size_formatted == '0 B'


class TestCacheFlags:
    """Test cache-related CLI flags"""

    def test_enable_cache_flag(self):
        """Test parsing with --enable-cache flag"""
        test_args = ['cja_sdr_generator.py', '--enable-cache', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.enable_cache is True

    def test_enable_cache_default_false(self):
        """Test that enable-cache defaults to False"""
        test_args = ['cja_sdr_generator.py', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.enable_cache is False

    def test_clear_cache_flag(self):
        """Test parsing with --clear-cache flag"""
        test_args = ['cja_sdr_generator.py', '--enable-cache', '--clear-cache', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.clear_cache is True
            assert args.enable_cache is True

    def test_clear_cache_default_false(self):
        """Test that clear-cache defaults to False"""
        test_args = ['cja_sdr_generator.py', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.clear_cache is False

    def test_cache_size_flag(self):
        """Test parsing with --cache-size flag"""
        test_args = ['cja_sdr_generator.py', '--cache-size', '5000', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.cache_size == 5000

    def test_cache_size_default(self):
        """Test that cache-size defaults to 1000"""
        test_args = ['cja_sdr_generator.py', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.cache_size == 1000

    def test_cache_ttl_flag(self):
        """Test parsing with --cache-ttl flag"""
        test_args = ['cja_sdr_generator.py', '--cache-ttl', '7200', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.cache_ttl == 7200

    def test_cache_ttl_default(self):
        """Test that cache-ttl defaults to 3600"""
        test_args = ['cja_sdr_generator.py', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.cache_ttl == 3600

    def test_all_cache_flags_combined(self):
        """Test all cache flags together"""
        test_args = [
            'cja_sdr_generator.py',
            '--enable-cache', '--clear-cache',
            '--cache-size', '2000', '--cache-ttl', '1800',
            'dv_12345'
        ]
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.enable_cache is True
            assert args.clear_cache is True
            assert args.cache_size == 2000
            assert args.cache_ttl == 1800


class TestConstants:
    """Test that constants are properly used in defaults"""

    def test_workers_default_uses_constant(self):
        """Test that workers default matches DEFAULT_BATCH_WORKERS constant"""
        from cja_sdr_generator import DEFAULT_BATCH_WORKERS
        test_args = ['cja_sdr_generator.py', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.workers == DEFAULT_BATCH_WORKERS

    def test_cache_size_default_uses_constant(self):
        """Test that cache_size default matches DEFAULT_CACHE_SIZE constant"""
        from cja_sdr_generator import DEFAULT_CACHE_SIZE
        test_args = ['cja_sdr_generator.py', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.cache_size == DEFAULT_CACHE_SIZE

    def test_cache_ttl_default_uses_constant(self):
        """Test that cache_ttl default matches DEFAULT_CACHE_TTL constant"""
        from cja_sdr_generator import DEFAULT_CACHE_TTL
        test_args = ['cja_sdr_generator.py', 'dv_12345']
        with patch.object(sys, 'argv', test_args):
            args = parse_arguments()
            assert args.cache_ttl == DEFAULT_CACHE_TTL
