"""Tests for environment variable credential loading"""

import json
import logging
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cja_auto_sdr.core.config_validation import validate_credentials
from cja_auto_sdr.core.credentials import CredentialResolver
from cja_auto_sdr.generator import (
    ENV_VAR_MAPPING,
    _config_from_env,
    load_credentials_from_env,
    validate_env_credentials,
)


class TestLoadCredentialsFromEnv:
    """Test environment variable credential loading"""

    def test_load_all_oauth_credentials(self, mock_env_credentials, clean_env):
        """Test loading complete OAuth S2S credentials from environment"""
        with patch.dict(os.environ, mock_env_credentials, clear=False):
            credentials = load_credentials_from_env()
            assert credentials is not None
            assert credentials["org_id"] == "test_org@AdobeOrg"
            assert credentials["client_id"] == "test_client_id"
            assert credentials["secret"] == "test_secret"
            assert credentials["scopes"] == "openid, AdobeID, additional_info.projectedProductContext"

    def test_returns_none_when_no_env_vars(self, clean_env):
        """Test that None is returned when no credential env vars are set"""
        credentials = load_credentials_from_env()
        assert credentials is None

    def test_partial_credentials(self, clean_env):
        """Test loading partial credentials returns what's available"""
        env_vars = {"ORG_ID": "test_org@AdobeOrg", "CLIENT_ID": "test_client_id"}
        with patch.dict(os.environ, env_vars, clear=False):
            credentials = load_credentials_from_env()
            assert credentials is not None
            assert "org_id" in credentials
            assert "client_id" in credentials
            assert "secret" not in credentials

    def test_strips_whitespace(self, clean_env):
        """Test that whitespace is stripped from values"""
        env_vars = {"ORG_ID": "  test_org@AdobeOrg  ", "CLIENT_ID": "\ttest_client_id\n", "SECRET": " test_secret "}
        with patch.dict(os.environ, env_vars, clear=False):
            credentials = load_credentials_from_env()
            assert credentials["org_id"] == "test_org@AdobeOrg"
            assert credentials["client_id"] == "test_client_id"
            assert credentials["secret"] == "test_secret"

    def test_ignores_empty_values(self, clean_env):
        """Test that empty or whitespace-only values are ignored"""
        env_vars = {"ORG_ID": "test_org@AdobeOrg", "CLIENT_ID": "", "SECRET": "   "}
        with patch.dict(os.environ, env_vars, clear=False):
            credentials = load_credentials_from_env()
            assert credentials is not None
            assert "org_id" in credentials
            assert "client_id" not in credentials
            assert "secret" not in credentials


class TestValidateEnvCredentials:
    """Test environment credential validation"""

    def test_valid_oauth_credentials(self):
        """Test validation passes for complete OAuth credentials"""
        credentials = {
            "org_id": "test_org@AdobeOrg",
            "client_id": "test_client_id",
            "secret": "test_secret",
            "scopes": "openid, AdobeID",
        }
        logger = MagicMock()
        assert validate_env_credentials(credentials, logger) is True

    def test_missing_required_field(self):
        """Test validation fails when required field is missing"""
        credentials = {
            "org_id": "test_org@AdobeOrg",
            "client_id": "test_client_id",
            # missing 'secret'
        }
        logger = MagicMock()
        assert validate_env_credentials(credentials, logger) is False

    def test_empty_required_field(self):
        """Test validation fails when required field is empty"""
        credentials = {
            "org_id": "test_org@AdobeOrg",
            "client_id": "test_client_id",
            "secret": "   ",  # whitespace only
        }
        logger = MagicMock()
        assert validate_env_credentials(credentials, logger) is False

    def test_base_credentials_only_warns(self):
        """Test validation passes with warning when only base credentials present"""
        credentials = {
            "org_id": "test_org@AdobeOrg",
            "client_id": "test_client_id",
            "secret": "test_secret",
            # No scopes specified
        }
        logger = MagicMock()
        result = validate_env_credentials(credentials, logger)
        assert result is True
        # Should log a warning about missing auth method
        logger.warning.assert_called()

    def test_validate_credentials_strict_rejects_malformed_required_values(self):
        """Strict validation should reject malformed required credential values."""
        logger = logging.getLogger("test_validate_credentials")
        credentials = {
            "org_id": "not_an_adobe_org",
            "client_id": "short",
            "secret": "tiny",
            "scopes": "openid",
        }

        is_valid, issues = validate_credentials(credentials, logger, strict=True, source="environment")

        assert is_valid is False
        assert any("ORG_ID" in issue for issue in issues)
        assert any("CLIENT_ID" in issue for issue in issues)
        assert any("SECRET" in issue for issue in issues)


class TestCredentialResolverFallbacks:
    """Tests for source fallback ordering when credentials are malformed."""

    def test_invalid_environment_credentials_fall_back_to_config(self, tmp_path, clean_env):
        """Invalid env values should not block valid config.json credentials."""
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "org_id": "valid_org@AdobeOrg",
                    "client_id": "a" * 32,
                    "secret": "b" * 32,
                    "scopes": "openid",
                },
            ),
            encoding="utf-8",
        )
        logger = logging.getLogger("test_credential_resolver")
        resolver = CredentialResolver(logger)

        with patch.dict(
            os.environ,
            {
                "ORG_ID": "invalid_org",
                "CLIENT_ID": "short",
                "SECRET": "tiny",
                "SCOPES": "openid",
            },
            clear=False,
        ):
            credentials, source = resolver.resolve(config_file=config_path)

        assert source == "config:config.json"
        assert credentials["org_id"] == "valid_org@AdobeOrg"


class TestConfigFromEnv:
    """Test direct cjapy configuration from env credentials."""

    def test_configures_cjapy_directly(self):
        """Test that _config_from_env configures cjapy without writing temp files."""
        credentials = {
            "org_id": "test_org@AdobeOrg",
            "client_id": "test_client_id",
            "secret": "test_secret",
            "scopes": "openid",
        }
        logger = MagicMock()
        expected_secret = credentials["secret"]

        with patch("cja_auto_sdr.api.client.cjapy") as mock_cjapy:
            _config_from_env(credentials, logger)

            mock_cjapy.configure.assert_called_once_with(
                org_id="test_org@AdobeOrg",
                client_id="test_client_id",
                secret=expected_secret,
                scopes="openid",
            )


class TestEnvVarMapping:
    """Test the environment variable mapping constant"""

    def test_all_required_fields_mapped(self):
        """Test that all credential fields have env var mappings"""
        required_fields = ["org_id", "client_id", "secret"]
        for field in required_fields:
            assert field in ENV_VAR_MAPPING

    def test_optional_fields_mapped(self):
        """Test that optional fields have env var mappings"""
        optional_fields = ["scopes", "sandbox"]
        for field in optional_fields:
            assert field in ENV_VAR_MAPPING

    def test_mapping_follows_naming_convention(self):
        """Test that env var names follow uppercase convention"""
        for config_key, env_var in ENV_VAR_MAPPING.items():
            # Env var should be uppercase version of config key
            assert env_var == config_key.upper()


class TestBootstrapDotenvCwd:
    """CFG-1: .env discovery must start at the cwd, not at the installed package."""

    def test_bootstrap_dotenv_searches_from_cwd(self):
        from cja_auto_sdr.api.client import _bootstrap_dotenv

        mock_find = MagicMock(return_value="/work/proj/.env")
        mock_load = MagicMock(return_value=True)
        fake = MagicMock(find_dotenv=mock_find, load_dotenv=mock_load)
        with patch.dict("sys.modules", {"dotenv": fake}):
            _bootstrap_dotenv(logging.getLogger("test"))

        mock_find.assert_called_once_with(usecwd=True)
        mock_load.assert_called_once_with("/work/proj/.env")

    def test_bootstrap_dotenv_does_not_override_existing_env(self, tmp_path, monkeypatch):
        pytest.importorskip("dotenv")
        from cja_auto_sdr.api.client import _bootstrap_dotenv

        (tmp_path / ".env").write_text("ORG_ID=fromfile@AdobeOrg\nCJA_CFG1_ONLY=fromfile\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("ORG_ID", "fromshell@AdobeOrg")
        # Record the absent state so monkeypatch removes the var at teardown.
        monkeypatch.setenv("CJA_CFG1_ONLY", "x")
        monkeypatch.delenv("CJA_CFG1_ONLY")

        _bootstrap_dotenv(logging.getLogger("test"))

        assert os.environ["ORG_ID"] == "fromshell@AdobeOrg"
        assert os.environ["CJA_CFG1_ONLY"] == "fromfile"
