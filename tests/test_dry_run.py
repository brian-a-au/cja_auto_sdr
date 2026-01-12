"""Tests for dry-run mode functionality"""
import pytest
import sys
import logging
from unittest.mock import patch, MagicMock
import tempfile
import json
import os

# Import the functions we're testing
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cja_sdr_generator import run_dry_run, validate_config_file


class TestDryRunMode:
    """Test dry-run mode functionality"""

    @pytest.fixture
    def logger(self):
        """Create a test logger"""
        return logging.getLogger("test_dry_run")

    @pytest.fixture
    def valid_config_file(self, tmp_path):
        """Create a valid config file for testing"""
        config = {
            "org_id": "test_org",
            "client_id": "test_client",
            "tech_id": "test_tech",
            "secret": "test_secret",
            "private_key": "test_key"
        }
        config_path = tmp_path / "test_config.json"
        with open(config_path, 'w') as f:
            json.dump(config, f)
        return str(config_path)

    @pytest.fixture
    def invalid_config_file(self, tmp_path):
        """Create an invalid config file for testing"""
        config_path = tmp_path / "invalid_config.json"
        with open(config_path, 'w') as f:
            f.write("not valid json {{{")
        return str(config_path)

    def test_dry_run_with_missing_config(self, logger):
        """Test dry-run fails gracefully with missing config file"""
        result = run_dry_run(
            data_views=['dv_12345'],
            config_file='nonexistent_config.json',
            logger=logger
        )
        assert result is False

    def test_dry_run_with_invalid_json_config(self, invalid_config_file, logger):
        """Test dry-run fails with invalid JSON config"""
        result = run_dry_run(
            data_views=['dv_12345'],
            config_file=invalid_config_file,
            logger=logger
        )
        assert result is False

    @patch('cja_sdr_generator.cjapy')
    def test_dry_run_with_api_connection_failure(self, mock_cjapy, valid_config_file, logger):
        """Test dry-run handles API connection failures"""
        # Mock CJA to raise an exception
        mock_cjapy.CJA.side_effect = Exception("API connection failed")

        result = run_dry_run(
            data_views=['dv_12345'],
            config_file=valid_config_file,
            logger=logger
        )
        assert result is False

    @patch('cja_sdr_generator.cjapy')
    def test_dry_run_success_with_valid_data_views(self, mock_cjapy, valid_config_file, logger):
        """Test dry-run succeeds with valid configuration and data views"""
        # Mock CJA instance
        mock_cja_instance = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja_instance

        # Mock getDataViews to return list of available views
        mock_cja_instance.getDataViews.return_value = [
            {'id': 'dv_12345', 'name': 'Test Data View 1'},
            {'id': 'dv_67890', 'name': 'Test Data View 2'}
        ]

        # Mock getDataView to return valid data view info
        mock_cja_instance.getDataView.return_value = {
            'id': 'dv_12345',
            'name': 'Test Data View 1'
        }

        result = run_dry_run(
            data_views=['dv_12345'],
            config_file=valid_config_file,
            logger=logger
        )
        assert result is True

    @patch('cja_sdr_generator.cjapy')
    def test_dry_run_fails_with_invalid_data_view(self, mock_cjapy, valid_config_file, logger):
        """Test dry-run fails when data view is not accessible"""
        # Mock CJA instance
        mock_cja_instance = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja_instance

        # Mock getDataViews
        mock_cja_instance.getDataViews.return_value = []

        # Mock getDataView to return None (not found)
        mock_cja_instance.getDataView.return_value = None

        result = run_dry_run(
            data_views=['dv_nonexistent'],
            config_file=valid_config_file,
            logger=logger
        )
        assert result is False

    @patch('cja_sdr_generator.cjapy')
    def test_dry_run_partial_success(self, mock_cjapy, valid_config_file, logger):
        """Test dry-run reports partial success when some data views fail"""
        # Mock CJA instance
        mock_cja_instance = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja_instance

        # Mock getDataViews
        mock_cja_instance.getDataViews.return_value = [
            {'id': 'dv_12345', 'name': 'Test Data View 1'}
        ]

        # Mock getDataView to succeed for one, fail for another
        def mock_get_data_view(dv_id):
            if dv_id == 'dv_12345':
                return {'id': 'dv_12345', 'name': 'Test Data View 1'}
            return None

        mock_cja_instance.getDataView.side_effect = mock_get_data_view

        result = run_dry_run(
            data_views=['dv_12345', 'dv_invalid'],
            config_file=valid_config_file,
            logger=logger
        )
        # Should fail because not all data views are valid
        assert result is False

    @patch('cja_sdr_generator.cjapy')
    def test_dry_run_handles_api_exception_for_data_view(self, mock_cjapy, valid_config_file, logger):
        """Test dry-run handles exceptions when checking individual data views"""
        # Mock CJA instance
        mock_cja_instance = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja_instance

        # Mock getDataViews
        mock_cja_instance.getDataViews.return_value = []

        # Mock getDataView to raise exception
        mock_cja_instance.getDataView.side_effect = Exception("API error")

        result = run_dry_run(
            data_views=['dv_12345'],
            config_file=valid_config_file,
            logger=logger
        )
        assert result is False

    @patch('cja_sdr_generator.cjapy')
    def test_dry_run_with_none_data_views_response(self, mock_cjapy, valid_config_file, logger):
        """Test dry-run handles None response from getDataViews"""
        # Mock CJA instance
        mock_cja_instance = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja_instance

        # Mock getDataViews to return None
        mock_cja_instance.getDataViews.return_value = None

        # Mock getDataView to return valid data
        mock_cja_instance.getDataView.return_value = {
            'id': 'dv_12345',
            'name': 'Test Data View'
        }

        result = run_dry_run(
            data_views=['dv_12345'],
            config_file=valid_config_file,
            logger=logger
        )
        assert result is True


class TestValidateConfigFile:
    """Test config file validation"""

    @pytest.fixture
    def logger(self):
        """Create a test logger"""
        return logging.getLogger("test_config")

    def test_validate_missing_config_file(self, logger):
        """Test validation fails for missing config file"""
        result = validate_config_file('nonexistent.json', logger)
        assert result is False

    def test_validate_invalid_json(self, tmp_path, logger):
        """Test validation fails for invalid JSON"""
        config_path = tmp_path / "invalid.json"
        with open(config_path, 'w') as f:
            f.write("not json")
        result = validate_config_file(str(config_path), logger)
        assert result is False

    def test_validate_valid_config(self, tmp_path, logger):
        """Test validation succeeds for valid config"""
        config = {
            "org_id": "test",
            "client_id": "test",
            "tech_id": "test",
            "secret": "test",
            "private_key": "test"
        }
        config_path = tmp_path / "valid.json"
        with open(config_path, 'w') as f:
            json.dump(config, f)
        result = validate_config_file(str(config_path), logger)
        assert result is True

    def test_validate_config_with_missing_fields(self, tmp_path, logger):
        """Test validation fails for config with missing required fields"""
        config = {"org_id": "test"}  # Missing other required fields
        config_path = tmp_path / "partial.json"
        with open(config_path, 'w') as f:
            json.dump(config, f)
        # Should fail when required fields are missing
        result = validate_config_file(str(config_path), logger)
        assert result is False
