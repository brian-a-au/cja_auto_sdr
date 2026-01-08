"""Tests for command-line interface"""
import pytest
import sys
from unittest.mock import patch
import argparse


# Import the function we're testing
sys.path.insert(0, '/Users/bau/DEV/cja_auto_sdr_2026')
from cja_sdr_generator import parse_arguments


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
        """Test that missing data view ID raises error"""
        test_args = ['cja_sdr_generator.py']
        with patch.object(sys, 'argv', test_args):
            with pytest.raises(SystemExit):
                parse_arguments()

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
