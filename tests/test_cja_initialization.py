"""Tests for CJA initialization and validation functions"""
import pytest
import json
import logging
import sys
import os
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cja_sdr_generator import (
    initialize_cja,
    validate_data_view,
    list_dataviews,
    validate_config_only,
    CredentialResolver,
    CredentialSourceError,
)


@pytest.fixture
def mock_logger():
    """Create a mock logger"""
    logger = Mock(spec=logging.Logger)
    logger.info = Mock()
    logger.debug = Mock()
    logger.warning = Mock()
    logger.error = Mock()
    logger.critical = Mock()
    logger.exception = Mock()
    return logger


@pytest.fixture
def mock_config_file(tmp_path):
    """Create a temporary valid config file"""
    config_data = {
        "org_id": "test_org@AdobeOrg",
        "client_id": "test_client_id",
        "secret": "test_secret",
        "scopes": "openid, AdobeID, additional_info.projectedProductContext"
    }
    config_file = tmp_path / "test_config.json"
    config_file.write_text(json.dumps(config_data))
    return str(config_file)


@pytest.fixture
def invalid_config_file(tmp_path):
    """Create a config file with invalid JSON"""
    config_file = tmp_path / "invalid_config.json"
    config_file.write_text("{ invalid json }")
    return str(config_file)


@pytest.fixture
def incomplete_config_file(tmp_path):
    """Create a config file with missing required fields"""
    config_data = {
        "org_id": "test_org@AdobeOrg"
        # Missing client_id and secret
    }
    config_file = tmp_path / "incomplete_config.json"
    config_file.write_text(json.dumps(config_data))
    return str(config_file)


class TestInitializeCjaSuccess:
    """Tests for successful CJA initialization"""

    @patch('cja_sdr_generator.CredentialResolver')
    @patch('cja_sdr_generator.cjapy')
    @patch('cja_sdr_generator.make_api_call_with_retry')
    def test_init_with_config_file(self, mock_api_call, mock_cjapy, mock_resolver_class,
                                    mock_logger, mock_config_file):
        """Test successful initialization with config file"""
        # Mock CredentialResolver to return config file as source
        mock_resolver = Mock()
        mock_resolver.resolve.return_value = (
            {
                'org_id': 'test_org@AdobeOrg',
                'client_id': 'test_client_id',
                'secret': 'test_secret',
                'scopes': 'openid'
            },
            f'config:{Path(mock_config_file).name}'
        )
        mock_resolver_class.return_value = mock_resolver

        mock_cja = Mock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_api_call.return_value = [{"id": "dv_1", "name": "Test"}]

        result = initialize_cja(mock_config_file, mock_logger)

        assert result is not None
        mock_cjapy.importConfigFile.assert_called_once_with(mock_config_file)

    @patch('cja_sdr_generator.CredentialResolver')
    @patch('cja_sdr_generator._config_from_env')
    @patch('cja_sdr_generator.cjapy')
    @patch('cja_sdr_generator.make_api_call_with_retry')
    def test_init_with_env_credentials(self, mock_api_call, mock_cjapy, mock_config_env,
                                        mock_resolver_class, mock_logger, mock_config_file):
        """Test successful initialization with environment credentials"""
        # Mock CredentialResolver to return env credentials
        mock_resolver = Mock()
        mock_resolver.resolve.return_value = (
            {
                'org_id': 'test_org@AdobeOrg',
                'client_id': 'test_client',
                'secret': 'test_secret'
            },
            'environment'
        )
        mock_resolver_class.return_value = mock_resolver

        mock_cja = Mock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_api_call.return_value = [{"id": "dv_1"}]

        result = initialize_cja(mock_config_file, mock_logger)

        assert result is not None
        mock_config_env.assert_called_once()  # _config_from_env should be called for env credentials

    @patch('cja_sdr_generator.CredentialResolver')
    @patch('cja_sdr_generator.cjapy')
    @patch('cja_sdr_generator.make_api_call_with_retry')
    def test_init_logs_connection_success(self, mock_api_call, mock_cjapy, mock_resolver_class,
                                           mock_logger, mock_config_file):
        """Test that successful connection is logged"""
        # Mock CredentialResolver
        mock_resolver = Mock()
        mock_resolver.resolve.return_value = (
            {'org_id': 'test@AdobeOrg', 'client_id': 'x', 'secret': 'y'},
            f'config:{Path(mock_config_file).name}'
        )
        mock_resolver_class.return_value = mock_resolver

        mock_cja = Mock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_api_call.return_value = [{"id": "dv_1"}, {"id": "dv_2"}]

        initialize_cja(mock_config_file, mock_logger)

        # Check that success was logged
        calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("success" in c.lower() for c in calls)


class TestInitializeCjaFailures:
    """Tests for CJA initialization failures"""

    @patch('cja_sdr_generator.CredentialResolver')
    def test_init_fails_with_invalid_config(self, mock_resolver_class,
                                             mock_logger, mock_config_file):
        """Test that initialization fails with invalid config"""
        # Mock CredentialResolver to raise CredentialSourceError
        mock_resolver = Mock()
        mock_resolver.resolve.side_effect = CredentialSourceError(
            "No valid credentials found",
            source="all",
            reason="Config validation failed"
        )
        mock_resolver_class.return_value = mock_resolver

        result = initialize_cja(mock_config_file, mock_logger)

        assert result is None
        mock_logger.critical.assert_called()

    @patch('cja_sdr_generator.CredentialResolver')
    def test_init_fails_with_missing_config_file(self, mock_resolver_class,
                                                  mock_logger):
        """Test that initialization fails when config file is missing"""
        # Mock CredentialResolver to raise CredentialSourceError
        mock_resolver = Mock()
        mock_resolver.resolve.side_effect = CredentialSourceError(
            "No valid credentials found",
            source="all",
            reason="Config file not found"
        )
        mock_resolver_class.return_value = mock_resolver

        result = initialize_cja("nonexistent.json", mock_logger)

        assert result is None
        mock_logger.critical.assert_called()

    @patch('cja_sdr_generator.CredentialResolver')
    @patch('cja_sdr_generator.cjapy')
    def test_init_fails_on_import_error(self, mock_cjapy, mock_resolver_class,
                                         mock_logger, mock_config_file):
        """Test handling of import errors"""
        # Mock CredentialResolver to return valid credentials
        mock_resolver = Mock()
        mock_resolver.resolve.return_value = (
            {'org_id': 'test@AdobeOrg', 'client_id': 'x', 'secret': 'y'},
            f'config:{Path(mock_config_file).name}'
        )
        mock_resolver_class.return_value = mock_resolver

        mock_cjapy.importConfigFile.side_effect = ImportError("Module not found")

        result = initialize_cja(mock_config_file, mock_logger)

        assert result is None
        mock_logger.critical.assert_called()

    @patch('cja_sdr_generator.CredentialResolver')
    @patch('cja_sdr_generator.cjapy')
    def test_init_fails_on_attribute_error(self, mock_cjapy, mock_resolver_class,
                                            mock_logger, mock_config_file):
        """Test handling of attribute errors (bad credentials)"""
        # Mock CredentialResolver to return valid credentials
        mock_resolver = Mock()
        mock_resolver.resolve.return_value = (
            {'org_id': 'test@AdobeOrg', 'client_id': 'x', 'secret': 'y'},
            f'config:{Path(mock_config_file).name}'
        )
        mock_resolver_class.return_value = mock_resolver

        mock_cjapy.CJA.side_effect = AttributeError("Invalid config")

        result = initialize_cja(mock_config_file, mock_logger)

        assert result is None
        mock_logger.critical.assert_called()

    @patch('cja_sdr_generator.load_credentials_from_env')
    @patch('cja_sdr_generator.validate_config_file')
    @patch('cja_sdr_generator.cjapy')
    def test_init_fails_on_permission_error(self, mock_cjapy, mock_validate_config,
                                             mock_load_env, mock_logger, mock_config_file):
        """Test handling of permission errors"""
        mock_load_env.return_value = None
        mock_validate_config.return_value = True
        mock_cjapy.importConfigFile.side_effect = PermissionError("Access denied")

        result = initialize_cja(mock_config_file, mock_logger)

        assert result is None
        mock_logger.critical.assert_called()


class TestInitializeCjaConnectionTest:
    """Tests for connection testing during initialization"""

    @patch('cja_sdr_generator.load_credentials_from_env')
    @patch('cja_sdr_generator.validate_config_file')
    @patch('cja_sdr_generator.cjapy')
    @patch('cja_sdr_generator.make_api_call_with_retry')
    def test_connection_test_returns_none(self, mock_api_call, mock_cjapy, mock_validate_config,
                                           mock_load_env, mock_logger, mock_config_file):
        """Test handling when connection test returns None"""
        mock_load_env.return_value = None
        mock_validate_config.return_value = True
        mock_cja = Mock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_api_call.return_value = None

        result = initialize_cja(mock_config_file, mock_logger)

        # Should still return the CJA instance
        assert result is not None
        mock_logger.warning.assert_called()

    @patch('cja_sdr_generator.load_credentials_from_env')
    @patch('cja_sdr_generator.validate_config_file')
    @patch('cja_sdr_generator.cjapy')
    @patch('cja_sdr_generator.make_api_call_with_retry')
    def test_connection_test_raises_exception(self, mock_api_call, mock_cjapy, mock_validate_config,
                                               mock_load_env, mock_logger, mock_config_file):
        """Test handling when connection test raises exception"""
        mock_load_env.return_value = None
        mock_validate_config.return_value = True
        mock_cja = Mock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_api_call.side_effect = Exception("Connection failed")

        result = initialize_cja(mock_config_file, mock_logger)

        # Should still return the CJA instance with warning
        assert result is not None
        mock_logger.warning.assert_called()


class TestValidateDataView:
    """Tests for validate_data_view function"""

    def test_validates_valid_data_view(self, mock_logger):
        """Test validation of valid data view"""
        mock_cja = Mock()
        mock_cja.getDataView.return_value = {
            "id": "dv_test_12345",
            "name": "Test Data View",
            "owner": {"name": "Test Owner"}
        }

        result = validate_data_view(mock_cja, "dv_test_12345", mock_logger)

        assert result is True

    def test_fails_for_empty_data_view_id(self, mock_logger):
        """Test that empty data view ID fails validation"""
        mock_cja = Mock()

        result = validate_data_view(mock_cja, "", mock_logger)

        assert result is False
        mock_logger.error.assert_called()

    def test_fails_for_none_data_view_id(self, mock_logger):
        """Test that None data view ID fails validation"""
        mock_cja = Mock()

        result = validate_data_view(mock_cja, None, mock_logger)

        assert result is False

    def test_warns_for_non_standard_format(self, mock_logger):
        """Test warning for non-standard data view ID format"""
        mock_cja = Mock()
        mock_cja.getDataView.return_value = {
            "id": "custom_id",
            "name": "Test",
            "owner": {"name": "Owner"}
        }

        result = validate_data_view(mock_cja, "custom_id", mock_logger)

        assert result is True
        mock_logger.warning.assert_called()

    def test_fails_when_api_returns_none(self, mock_logger):
        """Test failure when API returns None"""
        mock_cja = Mock()
        mock_cja.getDataView.return_value = None
        mock_cja.getDataViews.return_value = []

        result = validate_data_view(mock_cja, "dv_test_12345", mock_logger)

        assert result is False
        mock_logger.error.assert_called()

    def test_fails_on_api_exception(self, mock_logger):
        """Test failure when API raises exception"""
        mock_cja = Mock()
        mock_cja.getDataView.side_effect = Exception("API Error")

        result = validate_data_view(mock_cja, "dv_test_12345", mock_logger)

        assert result is False
        mock_logger.error.assert_called()

    def test_fails_on_attribute_error(self, mock_logger):
        """Test failure when API method not available"""
        mock_cja = Mock()
        mock_cja.getDataView.side_effect = AttributeError("Method not found")

        result = validate_data_view(mock_cja, "dv_test_12345", mock_logger)

        assert result is False
        mock_logger.error.assert_called()

    def test_logs_data_view_details(self, mock_logger):
        """Test that data view details are logged"""
        mock_cja = Mock()
        mock_cja.getDataView.return_value = {
            "id": "dv_test_12345",
            "name": "Test Data View",
            "owner": {"name": "Test Owner"},
            "description": "Test description"
        }

        validate_data_view(mock_cja, "dv_test_12345", mock_logger)

        calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("Test Data View" in c for c in calls)

    def test_shows_available_data_views_on_failure(self, mock_logger):
        """Test that available data views are shown when validation fails"""
        mock_cja = Mock()
        mock_cja.getDataView.return_value = None
        mock_cja.getDataViews.return_value = [
            {"id": "dv_other1", "name": "Other DV 1"},
            {"id": "dv_other2", "name": "Other DV 2"}
        ]

        validate_data_view(mock_cja, "dv_invalid", mock_logger)

        calls = [str(c) for c in mock_logger.info.call_args_list]
        assert any("access to" in c.lower() for c in calls)


class TestListDataviews:
    """Tests for list_dataviews function"""

    @patch('cja_sdr_generator.cjapy')
    @patch('builtins.print')
    def test_lists_available_dataviews(self, mock_print, mock_cjapy, mock_config_file):
        """Test listing available data views"""
        mock_cja = Mock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataViews.return_value = [
            {"id": "dv_1", "name": "Data View 1", "owner": {"name": "Owner 1"}},
            {"id": "dv_2", "name": "Data View 2", "owner": {"name": "Owner 2"}}
        ]

        result = list_dataviews(mock_config_file)

        assert result is True
        # Should print data view information
        mock_print.assert_called()

    @patch('cja_sdr_generator.cjapy')
    @patch('builtins.print')
    def test_handles_empty_dataviews_list(self, mock_print, mock_cjapy, mock_config_file):
        """Test handling of empty data views list"""
        mock_cja = Mock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataViews.return_value = []

        result = list_dataviews(mock_config_file)

        assert result is True
        # Should print no data views message
        mock_print.assert_called()

    @patch('cja_sdr_generator.cjapy')
    @patch('builtins.print')
    def test_handles_dataframe_response(self, mock_print, mock_cjapy, mock_config_file):
        """Test handling of DataFrame response"""
        import pandas as pd
        mock_cja = Mock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataViews.return_value = pd.DataFrame([
            {"id": "dv_1", "name": "Data View 1", "owner": {"name": "Owner 1"}}
        ])

        result = list_dataviews(mock_config_file)

        assert result is True

    @patch('cja_sdr_generator.cjapy')
    @patch('builtins.print')
    def test_handles_config_not_found(self, mock_print, mock_cjapy):
        """Test handling of missing config file"""
        mock_cjapy.importConfigFile.side_effect = FileNotFoundError("Not found")

        result = list_dataviews("nonexistent.json")

        assert result is False
        mock_print.assert_called()

    @patch('cja_sdr_generator.cjapy')
    @patch('builtins.print')
    def test_handles_api_error(self, mock_print, mock_cjapy, mock_config_file):
        """Test handling of API errors"""
        mock_cja = Mock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataViews.side_effect = Exception("API Error")

        result = list_dataviews(mock_config_file)

        assert result is False


class TestValidateConfigOnly:
    """Tests for validate_config_only function"""

    @patch('cja_sdr_generator.load_credentials_from_env')
    @patch('cja_sdr_generator.cjapy')
    @patch('builtins.print')
    def test_validates_valid_config(self, mock_print, mock_cjapy, mock_load_env, mock_config_file):
        """Test validation of valid configuration"""
        mock_load_env.return_value = None
        mock_cja = Mock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataViews.return_value = [{"id": "dv_1"}]

        result = validate_config_only(mock_config_file)

        assert result is True

    @patch('cja_sdr_generator.load_credentials_from_env')
    @patch('cja_sdr_generator.validate_env_credentials')
    @patch('cja_sdr_generator._config_from_env')
    @patch('cja_sdr_generator.cjapy')
    @patch('builtins.print')
    def test_validates_env_credentials(self, mock_print, mock_cjapy, mock_config_env,
                                        mock_validate_env, mock_load_env, mock_config_file):
        """Test validation with environment credentials"""
        mock_load_env.return_value = {
            'org_id': 'test@AdobeOrg',
            'client_id': 'test_client',
            'secret': 'test_secret'
        }
        mock_validate_env.return_value = True
        mock_cja = Mock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataViews.return_value = [{"id": "dv_1"}]

        result = validate_config_only(mock_config_file)

        assert result is True

    @patch('cja_sdr_generator.load_credentials_from_env')
    @patch('builtins.print')
    def test_fails_with_missing_config(self, mock_print, mock_load_env):
        """Test failure with missing config file"""
        mock_load_env.return_value = None

        result = validate_config_only("nonexistent.json")

        assert result is False

    @patch('cja_sdr_generator.load_credentials_from_env')
    @patch('cja_sdr_generator.cjapy')
    @patch('builtins.print')
    def test_fails_on_api_connection_error(self, mock_print, mock_cjapy,
                                            mock_load_env, mock_config_file):
        """Test failure when API connection fails"""
        mock_load_env.return_value = None
        mock_cja = Mock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataViews.side_effect = Exception("Connection failed")

        result = validate_config_only(mock_config_file)

        assert result is False

    @patch('cja_sdr_generator.load_credentials_from_env')
    @patch('builtins.print')
    def test_shows_credential_status(self, mock_print, mock_load_env, mock_config_file):
        """Test that credential status is shown"""
        mock_load_env.return_value = None

        # Even if validation fails, it should print status
        validate_config_only(mock_config_file)

        mock_print.assert_called()

    @patch('cja_sdr_generator.load_credentials_from_env')
    @patch('cja_sdr_generator.cjapy')
    @patch('builtins.print')
    def test_shows_data_view_count(self, mock_print, mock_cjapy,
                                    mock_load_env, mock_config_file):
        """Test that data view count is shown on success"""
        mock_load_env.return_value = None
        mock_cja = Mock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataViews.return_value = [{"id": "dv_1"}, {"id": "dv_2"}, {"id": "dv_3"}]

        validate_config_only(mock_config_file)

        calls = [str(c) for c in mock_print.call_args_list]
        assert any("3" in c for c in calls)


class TestInitializeCjaEnvFallback:
    """Tests for environment to config file fallback"""

    @patch('cja_sdr_generator.load_credentials_from_env')
    @patch('cja_sdr_generator.validate_env_credentials')
    @patch('cja_sdr_generator.validate_config_file')
    @patch('cja_sdr_generator.cjapy')
    @patch('cja_sdr_generator.make_api_call_with_retry')
    def test_falls_back_to_config_when_env_incomplete(self, mock_api_call, mock_cjapy,
                                                       mock_validate_config, mock_validate_env,
                                                       mock_load_env, mock_logger, mock_config_file):
        """Test fallback to config file when env credentials incomplete"""
        mock_load_env.return_value = {'org_id': 'test'}  # Incomplete
        mock_validate_env.return_value = False
        mock_validate_config.return_value = True
        mock_cja = Mock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_api_call.return_value = [{"id": "dv_1"}]

        result = initialize_cja(mock_config_file, mock_logger)

        assert result is not None
        mock_cjapy.importConfigFile.assert_called_once()

    @patch('cja_sdr_generator.load_credentials_from_env')
    @patch('cja_sdr_generator.validate_env_credentials')
    @patch('cja_sdr_generator.validate_config_file')
    def test_fails_when_both_env_and_config_invalid(self, mock_validate_config, mock_validate_env,
                                                     mock_load_env, mock_logger, mock_config_file):
        """Test failure when both env and config are invalid"""
        mock_load_env.return_value = {'org_id': 'test'}
        mock_validate_env.return_value = False
        mock_validate_config.return_value = False

        result = initialize_cja(mock_config_file, mock_logger)

        assert result is None
        mock_logger.critical.assert_called()
