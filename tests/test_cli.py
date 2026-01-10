"""Tests for command-line interface"""
import pytest
import sys
import os
import json
import tempfile
from unittest.mock import patch
import argparse


# Import the function we're testing
sys.path.insert(0, '/Users/bau/DEV/cja_auto_sdr_2026')
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
