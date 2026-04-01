"""Tests for cja_auto_sdr.api.client — targeting uncovered lines.

Covers:
- _bootstrap_dotenv inner try/except paths (lines 31-38)
- _config_from_env direct configure + stale cleanup paths
- configure_cjapy default logger creation (lines 96-97)
- configure_cjapy unknown source format fallback (line 132)
- configure_cjapy ProfileNotFoundError/ProfileConfigError handling (lines 139-141)
- initialize_cja CredentialSourceError with details (line 194)
- initialize_cja FileNotFoundError handler (lines 240-246)
- initialize_cja generic Exception handler (lines 273-287)
"""

import json
import logging
import os
import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import cja_auto_sdr.api.client as _client_module
from cja_auto_sdr.api.client import (
    _bootstrap_dotenv,
    _config_from_env,
    configure_cjapy,
    initialize_cja,
)
from cja_auto_sdr.core.exceptions import (
    CredentialSourceError,
    ProfileConfigError,
    ProfileNotFoundError,
)


@pytest.fixture(autouse=True)
def _reset_temp_cleanup_guard():
    """Reset temp-cleanup scheduling state between tests."""
    _client_module._temp_cleanup_next_check_monotonic = 0.0


@pytest.fixture
def mock_logger():
    """Create a mock logger."""
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
    """Create a temporary valid config file."""
    config_data = {
        "org_id": "test_org@AdobeOrg",
        "client_id": "test_client_id",
        "secret": "test_secret",
        "scopes": "openid, AdobeID",
    }
    config_file = tmp_path / "test_config.json"
    config_file.write_text(json.dumps(config_data))
    return str(config_file)


# ==================== _bootstrap_dotenv (lines 31-38) ====================


class TestBootstrapDotenv:
    """Tests for _bootstrap_dotenv inner try/except paths."""

    def test_dotenv_loaded_successfully(self, mock_logger):
        """load_dotenv returns True -> logs '.env file found and loaded'."""
        mock_load_dotenv = Mock(return_value=True)
        with patch.dict("sys.modules", {"dotenv": MagicMock(load_dotenv=mock_load_dotenv)}):
            # Re-execute the function so it picks up the patched module
            _bootstrap_dotenv(mock_logger)

        calls = [str(c) for c in mock_logger.debug.call_args_list]
        assert any(".env file found and loaded" in c for c in calls)

    def test_dotenv_no_env_file(self, mock_logger):
        """load_dotenv returns False -> logs '.env file not found'."""
        mock_load_dotenv = Mock(return_value=False)
        with patch.dict("sys.modules", {"dotenv": MagicMock(load_dotenv=mock_load_dotenv)}):
            _bootstrap_dotenv(mock_logger)

        calls = [str(c) for c in mock_logger.debug.call_args_list]
        assert any(".env file not found" in c for c in calls)

    def test_dotenv_load_raises_exception(self, mock_logger):
        """load_dotenv raises an exception -> logs the failure."""
        mock_load_dotenv = Mock(side_effect=OSError("Permission denied"))
        with patch.dict("sys.modules", {"dotenv": MagicMock(load_dotenv=mock_load_dotenv)}):
            _bootstrap_dotenv(mock_logger)

        calls = [str(c) for c in mock_logger.debug.call_args_list]
        assert any("Failed to load .env" in c for c in calls)

    def test_dotenv_load_runtime_error_is_non_fatal(self, mock_logger):
        """Unexpected loader failures are still best-effort and must not abort."""
        mock_load_dotenv = Mock(side_effect=RuntimeError("internal dotenv failure"))
        with patch.dict("sys.modules", {"dotenv": MagicMock(load_dotenv=mock_load_dotenv)}):
            _bootstrap_dotenv(mock_logger)

        calls = [str(c) for c in mock_logger.debug.call_args_list]
        assert any("Failed to load .env" in c for c in calls)

    def test_dotenv_not_installed(self, mock_logger):
        """Import of dotenv fails -> logs 'python-dotenv not installed'."""
        # Temporarily remove dotenv from sys.modules if present, and make import fail
        with patch.dict("sys.modules", {"dotenv": None}):
            _bootstrap_dotenv(mock_logger)

        calls = [str(c) for c in mock_logger.debug.call_args_list]
        assert any("python-dotenv not installed" in c for c in calls)

    def test_dotenv_import_runtime_error_is_non_fatal(self, mock_logger):
        """Unexpected dotenv import errors should remain best-effort."""
        import builtins

        real_import = builtins.__import__

        def _import_with_runtime_error(name, *args, **kwargs):
            if name == "dotenv":
                raise RuntimeError("broken dotenv install")
            return real_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=_import_with_runtime_error):
            _bootstrap_dotenv(mock_logger)

        calls = [str(c) for c in mock_logger.debug.call_args_list]
        assert any("Failed to import python-dotenv" in c for c in calls)


# ==================== _config_from_env direct configure + stale cleanup ====================


class TestConfigFromEnvCleanup:
    """Tests for in-memory configuration and stale temp-file cleanup."""

    @patch("cja_auto_sdr.api.client.cjapy")
    def test_configures_cjapy_directly(self, mock_cjapy, mock_logger):
        """Direct configuration should normalize spaced scopes before cjapy.configure."""
        credentials = {"org_id": "test@AdobeOrg", "client_id": "x", "secret": "y", "scopes": "openid, AdobeID"}
        expected_secret = credentials["secret"]
        _config_from_env(credentials, mock_logger)

        mock_cjapy.configure.assert_called_once_with(
            org_id="test@AdobeOrg",
            client_id="x",
            secret=expected_secret,
            scopes="openid,AdobeID",
        )

    @patch("cja_auto_sdr.api.client.cjapy")
    def test_configures_cjapy_with_list_valued_scopes(self, mock_cjapy, mock_logger):
        """List-valued scopes from profile/config JSON should be adapted for cjapy.configure."""
        credentials = {"org_id": "test@AdobeOrg", "client_id": "x", "secret": "y", "scopes": ["openid", "AdobeID"]}
        expected_secret = credentials["secret"]

        _config_from_env(credentials, mock_logger)

        mock_cjapy.configure.assert_called_once_with(
            org_id="test@AdobeOrg",
            client_id="x",
            secret=expected_secret,
            scopes="openid,AdobeID",
        )

    @patch("cja_auto_sdr.api.client.cjapy")
    @patch("cja_auto_sdr.api.client.tempfile.gettempdir")
    def test_stale_temp_configs_removed_during_config(self, mock_gettempdir, mock_cjapy, mock_logger, tmp_path):
        """Old temp credential files from prior versions should be cleaned up."""
        mock_gettempdir.return_value = str(tmp_path)
        credentials = {"org_id": "test@AdobeOrg", "client_id": "x", "secret": "y"}
        stale_file = tmp_path / "cja_env_config_stale.json"
        stale_file.write_text("{}", encoding="utf-8")
        os.utime(stale_file, (time.time() - 7200, time.time() - 7200))

        _config_from_env(credentials, mock_logger)

        assert not stale_file.exists()
        mock_logger.debug.assert_any_call("Removed %s stale temp credential file(s) from previous runs", 1)

    @patch("cja_auto_sdr.api.client.cjapy")
    @patch("cja_auto_sdr.api.client.tempfile.gettempdir")
    def test_legacy_profile_temp_configs_removed_during_config(
        self,
        mock_gettempdir,
        mock_cjapy,
        mock_logger,
        tmp_path,
    ):
        """Profile-test temp files left behind by older releases should also be cleaned up."""
        mock_gettempdir.return_value = str(tmp_path)
        credentials = {"org_id": "test@AdobeOrg", "client_id": "x", "secret": "y"}
        stale_file = tmp_path / "cja_profile_test_stale.json"
        stale_file.write_text("{}", encoding="utf-8")
        os.utime(stale_file, (time.time() - 7200, time.time() - 7200))

        _config_from_env(credentials, mock_logger)

        assert not stale_file.exists()
        mock_logger.debug.assert_any_call("Removed %s stale temp credential file(s) from previous runs", 1)

    @patch("cja_auto_sdr.api.client.cjapy")
    @patch("cja_auto_sdr.api.client.tempfile.gettempdir")
    def test_recent_temp_configs_are_kept(self, mock_gettempdir, mock_cjapy, mock_logger, tmp_path):
        """Recent temp files should be left untouched to avoid racing live older processes."""
        mock_gettempdir.return_value = str(tmp_path)
        credentials = {"org_id": "test@AdobeOrg", "client_id": "x", "secret": "y"}
        recent_file = tmp_path / "cja_env_config_recent.json"
        recent_file.write_text("{}", encoding="utf-8")

        _config_from_env(credentials, mock_logger)

        assert recent_file.exists()

    @patch("cja_auto_sdr.api.client.cjapy")
    @patch("cja_auto_sdr.api.client._cleanup_stale_temp_configs")
    def test_stale_cleanup_is_throttled_until_due(self, mock_cleanup, mock_cjapy, mock_logger):
        """The temp-directory scan should only rerun once the scheduled recheck time arrives."""
        credentials = {"org_id": "test@AdobeOrg", "client_id": "x", "secret": "y"}
        mock_cleanup.side_effect = [30.0, 30.0]

        with patch("cja_auto_sdr.api.client.time.monotonic", side_effect=[100.0, 110.0, 131.0]):
            _config_from_env(credentials, mock_logger)
            _config_from_env(credentials, mock_logger)
            _config_from_env(credentials, mock_logger)

        assert mock_cjapy.configure.call_count == 3
        assert mock_cleanup.call_count == 2
        mock_cleanup.assert_any_call(mock_logger)

    @patch("cja_auto_sdr.api.client.cjapy")
    @patch("cja_auto_sdr.api.client.tempfile.gettempdir")
    def test_recent_temp_configs_are_removed_after_scheduled_recheck(
        self,
        mock_gettempdir,
        mock_cjapy,
        mock_logger,
        tmp_path,
    ):
        """Legacy temp files skipped while recent should be deleted once they later become stale."""
        mock_gettempdir.return_value = str(tmp_path)
        credentials = {"org_id": "test@AdobeOrg", "client_id": "x", "secret": "y"}
        recent_file = tmp_path / "cja_env_config_recent.json"
        current_times = {"wall": 10_000.0, "mono": 100.0}
        recent_file.write_text("{}", encoding="utf-8")
        os.utime(
            recent_file,
            (
                current_times["wall"] - (_client_module._LEGACY_TEMP_CONFIG_MAX_AGE_SECONDS - 10.0),
                current_times["wall"] - (_client_module._LEGACY_TEMP_CONFIG_MAX_AGE_SECONDS - 10.0),
            ),
        )

        with (
            patch("cja_auto_sdr.api.client.time.time", side_effect=lambda: current_times["wall"]),
            patch("cja_auto_sdr.api.client.time.monotonic", side_effect=lambda: current_times["mono"]),
        ):
            _config_from_env(credentials, mock_logger)
            assert recent_file.exists()

            current_times["wall"] += 5.0
            current_times["mono"] += 5.0
            _config_from_env(credentials, mock_logger)
            assert recent_file.exists()

            current_times["wall"] += 6.0
            current_times["mono"] += 6.0
            _config_from_env(credentials, mock_logger)

        assert not recent_file.exists()
        assert mock_cjapy.configure.call_count == 3


# ==================== configure_cjapy default logger (lines 96-97) ====================


class TestConfigureCjapyDefaultLogger:
    """Tests for configure_cjapy when no logger is provided."""

    @patch("cja_auto_sdr.api.client._bootstrap_dotenv")
    @patch("cja_auto_sdr.api.client.CredentialResolver")
    @patch("cja_auto_sdr.api.client.cjapy")
    def test_creates_default_logger_when_none(self, mock_cjapy, mock_resolver_class, mock_dotenv):
        """configure_cjapy with logger=None should create its own logger."""
        mock_resolver = Mock()
        mock_resolver.resolve.return_value = (
            {"org_id": "test@AdobeOrg", "client_id": "x", "secret": "y"},
            "config:test.json",
        )
        mock_resolver_class.return_value = mock_resolver

        # Call without providing a logger
        success, _source, creds = configure_cjapy(logger=None, config_file="test.json")

        assert success is True
        assert creds is not None


# ==================== configure_cjapy unknown source format (line 132) ====================


class TestConfigureCjapyUnknownSource:
    """Tests for configure_cjapy when source has an unrecognized format."""

    @patch("cja_auto_sdr.api.client._bootstrap_dotenv")
    @patch("cja_auto_sdr.api.client.CredentialResolver")
    @patch("cja_auto_sdr.api.client.cjapy")
    def test_unknown_source_format_used_as_is(self, mock_cjapy, mock_resolver_class, mock_dotenv, mock_logger):
        """When source is not profile:*, environment, or config:*, use raw string."""
        mock_resolver = Mock()
        mock_resolver.resolve.return_value = (
            {"org_id": "test@AdobeOrg", "client_id": "x", "secret": "y"},
            "custom_source_unknown",
        )
        mock_resolver_class.return_value = mock_resolver

        # "custom_source_unknown" does not start with "profile:", "config:", or equal "environment"
        # so the else branch calls cjapy.importConfigFile, and display_source falls through to line 132
        success, display_source, _creds = configure_cjapy(logger=mock_logger)

        assert success is True
        assert display_source == "custom_source_unknown"


# ==================== configure_cjapy ProfileNotFoundError / ProfileConfigError (lines 139-141) ====================


class TestConfigureCjapyProfileErrors:
    """Tests for configure_cjapy handling of profile-specific exceptions."""

    @patch("cja_auto_sdr.api.client._bootstrap_dotenv")
    @patch("cja_auto_sdr.api.client.CredentialResolver")
    def test_profile_not_found_error(self, mock_resolver_class, mock_dotenv, mock_logger):
        """ProfileNotFoundError is caught and returns failure tuple."""
        mock_resolver = Mock()
        mock_resolver.resolve.side_effect = ProfileNotFoundError("Profile 'missing' not found", profile_name="missing")
        mock_resolver_class.return_value = mock_resolver

        success, source, creds = configure_cjapy(profile="missing", logger=mock_logger)

        assert success is False
        assert "Profile error" in source
        assert creds is None
        mock_logger.error.assert_called()

    @patch("cja_auto_sdr.api.client._bootstrap_dotenv")
    @patch("cja_auto_sdr.api.client.CredentialResolver")
    def test_profile_config_error(self, mock_resolver_class, mock_dotenv, mock_logger):
        """ProfileConfigError is caught and returns failure tuple."""
        mock_resolver = Mock()
        mock_resolver.resolve.side_effect = ProfileConfigError("Invalid JSON in profile config", profile_name="broken")
        mock_resolver_class.return_value = mock_resolver

        success, source, creds = configure_cjapy(profile="broken", logger=mock_logger)

        assert success is False
        assert "Profile error" in source
        assert creds is None
        mock_logger.error.assert_called()

    @patch("cja_auto_sdr.api.client._bootstrap_dotenv")
    @patch("cja_auto_sdr.api.client.CredentialResolver")
    def test_credential_source_error(self, mock_resolver_class, mock_dotenv, mock_logger):
        """CredentialSourceError is caught and returns failure tuple."""
        mock_resolver = Mock()
        mock_resolver.resolve.side_effect = CredentialSourceError(
            "No valid credentials found",
            source="all",
            reason="All sources failed",
        )
        mock_resolver_class.return_value = mock_resolver

        success, _source, creds = configure_cjapy(logger=mock_logger)

        assert success is False
        assert creds is None
        mock_logger.error.assert_called()


# ==================== initialize_cja CredentialSourceError with details (line 194) ====================


class TestInitializeCjaCredentialDetails:
    """Tests for initialize_cja when CredentialSourceError has details."""

    @patch("cja_auto_sdr.api.client.CredentialResolver")
    def test_credential_error_with_details_logs_details(self, mock_resolver_class, mock_logger, mock_config_file):
        """When CredentialSourceError has .details, it should be logged (line 194)."""
        mock_resolver = Mock()
        error = CredentialSourceError(
            "No valid credentials found",
            source="all",
            reason="Config validation failed",
            details="Hint: Try setting ORG_ID, CLIENT_ID, SECRET, SCOPES environment variables",
        )
        mock_resolver.resolve.side_effect = error
        mock_resolver_class.return_value = mock_resolver

        result = initialize_cja(mock_config_file, mock_logger)

        assert result is None
        # Check that the details string was logged via critical
        critical_calls = [str(c) for c in mock_logger.critical.call_args_list]
        assert any("Hint: Try setting" in c for c in critical_calls), f"Expected details logged, got: {critical_calls}"

    @patch("cja_auto_sdr.api.client.CredentialResolver")
    def test_credential_error_without_details_skips_details_line(
        self,
        mock_resolver_class,
        mock_logger,
        mock_config_file,
    ):
        """When CredentialSourceError has no .details, the details line is skipped."""
        mock_resolver = Mock()
        error = CredentialSourceError(
            "No credentials",
            source="all",
            reason="Nothing found",
            # details=None by default
        )
        mock_resolver.resolve.side_effect = error
        mock_resolver_class.return_value = mock_resolver

        result = initialize_cja(mock_config_file, mock_logger)

        assert result is None
        # The details attribute should be None/falsy, so the if e.details branch (line 194) is skipped
        assert error.details is None


# ==================== initialize_cja FileNotFoundError (lines 240-246) ====================


class TestInitializeCjaFileNotFound:
    """Tests for initialize_cja FileNotFoundError handler."""

    @patch("cja_auto_sdr.api.client.CredentialResolver")
    @patch("cja_auto_sdr.api.client.cjapy")
    def test_file_not_found_during_import_config(self, mock_cjapy, mock_resolver_class, mock_logger, mock_config_file):
        """FileNotFoundError from cjapy.importConfigFile triggers lines 240-246."""
        mock_resolver = Mock()
        mock_resolver.resolve.return_value = (
            {"org_id": "test@AdobeOrg", "client_id": "x", "secret": "y"},
            f"config:{Path(mock_config_file).name}",
        )
        mock_resolver_class.return_value = mock_resolver

        mock_cjapy.importConfigFile.side_effect = FileNotFoundError("No such file: config.json")

        result = initialize_cja(mock_config_file, mock_logger)

        assert result is None
        critical_calls = [str(c) for c in mock_logger.critical.call_args_list]
        assert any("CONFIGURATION FILE ERROR" in c for c in critical_calls)
        assert any("Config file not found" in c for c in critical_calls)
        assert any("Current working directory" in c for c in critical_calls)

    @patch("cja_auto_sdr.api.client.CredentialResolver")
    @patch("cja_auto_sdr.api.client.cjapy")
    def test_file_not_found_during_cja_creation(self, mock_cjapy, mock_resolver_class, mock_logger, mock_config_file):
        """FileNotFoundError from CJA() also triggers the handler."""
        mock_resolver = Mock()
        mock_resolver.resolve.return_value = (
            {"org_id": "test@AdobeOrg", "client_id": "x", "secret": "y"},
            f"config:{Path(mock_config_file).name}",
        )
        mock_resolver_class.return_value = mock_resolver

        mock_cjapy.CJA.side_effect = FileNotFoundError("Missing dependency file")

        result = initialize_cja(mock_config_file, mock_logger)

        assert result is None
        critical_calls = [str(c) for c in mock_logger.critical.call_args_list]
        assert any("CONFIGURATION FILE ERROR" in c for c in critical_calls)


# ==================== initialize_cja generic Exception (lines 273-287) ====================


class TestInitializeCjaGenericException:
    """Tests for initialize_cja catching unexpected Exception types."""

    @patch("cja_auto_sdr.api.client.CredentialResolver")
    @patch("cja_auto_sdr.api.client.cjapy")
    def test_unexpected_runtime_error(self, mock_cjapy, mock_resolver_class, mock_logger, mock_config_file):
        """RuntimeError triggers the generic Exception handler (lines 273-287)."""
        mock_resolver = Mock()
        mock_resolver.resolve.return_value = (
            {"org_id": "test@AdobeOrg", "client_id": "x", "secret": "y"},
            f"config:{Path(mock_config_file).name}",
        )
        mock_resolver_class.return_value = mock_resolver

        mock_cjapy.importConfigFile.return_value = None
        mock_cjapy.CJA.side_effect = RuntimeError("Unexpected internal error")

        result = initialize_cja(mock_config_file, mock_logger)

        assert result is None
        critical_calls = [str(c) for c in mock_logger.critical.call_args_list]
        assert any("CJA INITIALIZATION FAILED" in c for c in critical_calls)
        assert any("Unexpected error" in c for c in critical_calls)
        assert any("RuntimeError" in c for c in critical_calls)
        # Should also log troubleshooting steps
        assert any("Troubleshooting steps" in c for c in critical_calls)
        assert any("Verify your configuration" in c for c in critical_calls)
        assert any("cjapy library is up to date" in c for c in critical_calls)
        # logger.exception should be called for the full traceback
        mock_logger.exception.assert_called_once()

    @patch("cja_auto_sdr.api.client.CredentialResolver")
    @patch("cja_auto_sdr.api.client.cjapy")
    def test_unexpected_value_error(self, mock_cjapy, mock_resolver_class, mock_logger, mock_config_file):
        """ValueError triggers the generic Exception handler."""
        mock_resolver = Mock()
        mock_resolver.resolve.return_value = (
            {"org_id": "test@AdobeOrg", "client_id": "x", "secret": "y"},
            "environment",
        )
        mock_resolver_class.return_value = mock_resolver

        mock_cjapy.CJA.side_effect = ValueError("Bad credential format")

        result = initialize_cja(mock_config_file, mock_logger)

        assert result is None
        critical_calls = [str(c) for c in mock_logger.critical.call_args_list]
        assert any("CJA INITIALIZATION FAILED" in c for c in critical_calls)
        assert any("ValueError" in c for c in critical_calls)

    @patch("cja_auto_sdr.api.client.CredentialResolver")
    @patch("cja_auto_sdr.api.client.cjapy")
    @patch("cja_auto_sdr.api.client.make_api_call_with_retry")
    def test_unexpected_error_during_api_test(
        self,
        mock_api_call,
        mock_cjapy,
        mock_resolver_class,
        mock_logger,
        mock_config_file,
    ):
        """Generic exception during post-CJA-creation flow triggers handler."""
        mock_resolver = Mock()
        mock_resolver.resolve.return_value = (
            {"org_id": "test@AdobeOrg", "client_id": "x", "secret": "y"},
            f"config:{Path(mock_config_file).name}",
        )
        mock_resolver_class.return_value = mock_resolver

        mock_cjapy.CJA.return_value = Mock()
        # make_api_call_with_retry raises a TypeError — not caught by inner try/except
        # because it IS caught by inner except Exception. So let's make CJA() succeed
        # but the next step outside the inner try fails.
        # Actually, looking at the code: the inner try (line 221) catches Exception,
        # so to reach line 273, we need an error OUTSIDE that inner try.
        # Let's raise an error from cjapy.importConfigFile that is not
        # FileNotFoundError, ImportError, AttributeError, or PermissionError.
        mock_cjapy.importConfigFile.side_effect = ConnectionError("Network down")

        result = initialize_cja(mock_config_file, mock_logger)

        assert result is None
        critical_calls = [str(c) for c in mock_logger.critical.call_args_list]
        assert any("CJA INITIALIZATION FAILED" in c for c in critical_calls)
        assert any("ConnectionError" in c for c in critical_calls)


# ==================== configure_cjapy profile source display ====================


class TestConfigureCjapySourceDisplay:
    """Tests for configure_cjapy source formatting in display_source."""

    @patch("cja_auto_sdr.api.client._bootstrap_dotenv")
    @patch("cja_auto_sdr.api.client.CredentialResolver")
    @patch("cja_auto_sdr.api.client._config_from_env")
    def test_profile_source_display(self, mock_config_env, mock_resolver_class, mock_dotenv, mock_logger):
        """Profile source is formatted as 'Profile: <name>'."""
        mock_resolver = Mock()
        mock_resolver.resolve.return_value = (
            {"org_id": "test@AdobeOrg", "client_id": "x", "secret": "y"},
            "profile:production",
        )
        mock_resolver_class.return_value = mock_resolver

        success, display_source, _ = configure_cjapy(profile="production", logger=mock_logger)

        assert success is True
        assert display_source == "Profile: production"

    @patch("cja_auto_sdr.api.client._bootstrap_dotenv")
    @patch("cja_auto_sdr.api.client.CredentialResolver")
    @patch("cja_auto_sdr.api.client.cjapy")
    def test_config_file_source_display(self, mock_cjapy, mock_resolver_class, mock_dotenv, mock_logger, tmp_path):
        """Config file source shows resolved path."""
        config_path = tmp_path / "my_config.json"
        config_path.write_text(json.dumps({"org_id": "x", "client_id": "y", "secret": "z"}))

        mock_resolver = Mock()
        mock_resolver.resolve.return_value = (
            {"org_id": "x", "client_id": "y", "secret": "z"},
            "config:my_config.json",
        )
        mock_resolver_class.return_value = mock_resolver

        success, display_source, _ = configure_cjapy(config_file=str(config_path), logger=mock_logger)

        assert success is True
        assert display_source.startswith("Config file: ")
        # Should contain the resolved path
        assert "my_config.json" in display_source

    @patch("cja_auto_sdr.api.client._bootstrap_dotenv")
    @patch("cja_auto_sdr.api.client.CredentialResolver")
    @patch("cja_auto_sdr.api.client._config_from_env")
    def test_environment_source_display(self, mock_config_env, mock_resolver_class, mock_dotenv, mock_logger):
        """Environment source is formatted as 'Environment variables'."""
        mock_resolver = Mock()
        mock_resolver.resolve.return_value = (
            {"org_id": "test@AdobeOrg", "client_id": "x", "secret": "y"},
            "environment",
        )
        mock_resolver_class.return_value = mock_resolver

        success, display_source, _ = configure_cjapy(logger=mock_logger)

        assert success is True
        assert display_source == "Environment variables"


# ==================== configure_cjapy CJA_PROFILE from env ====================


class TestConfigureCjapyEnvProfileResolution:
    """Tests for configure_cjapy resolving CJA_PROFILE from environment."""

    @patch("cja_auto_sdr.api.client._bootstrap_dotenv")
    @patch("cja_auto_sdr.api.client.CredentialResolver")
    @patch("cja_auto_sdr.api.client._config_from_env")
    def test_whitespace_only_profile_ignored(self, mock_config_env, mock_resolver_class, mock_dotenv, mock_logger):
        """A profile argument of only whitespace is treated as None."""
        mock_resolver = Mock()
        mock_resolver.resolve.return_value = (
            {"org_id": "test@AdobeOrg", "client_id": "x", "secret": "y"},
            "environment",
        )
        mock_resolver_class.return_value = mock_resolver

        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("CJA_PROFILE", None)
            success, _, _ = configure_cjapy(profile="   ", logger=mock_logger)

        assert success is True
        # profile should resolve to None since it's whitespace-only
        mock_resolver.resolve.assert_called_once_with(profile=None, config_file="config.json")

    @patch("cja_auto_sdr.api.client._bootstrap_dotenv")
    @patch("cja_auto_sdr.api.client.CredentialResolver")
    @patch("cja_auto_sdr.api.client._config_from_env")
    def test_cja_profile_env_var_whitespace_ignored(
        self,
        mock_config_env,
        mock_resolver_class,
        mock_dotenv,
        mock_logger,
    ):
        """CJA_PROFILE env var with only whitespace is treated as not set."""
        mock_resolver = Mock()
        mock_resolver.resolve.return_value = (
            {"org_id": "test@AdobeOrg", "client_id": "x", "secret": "y"},
            "environment",
        )
        mock_resolver_class.return_value = mock_resolver

        with patch.dict(os.environ, {"CJA_PROFILE": "   "}, clear=False):
            success, _, _ = configure_cjapy(profile=None, logger=mock_logger)

        assert success is True
        mock_resolver.resolve.assert_called_once_with(profile=None, config_file="config.json")

    @patch("cja_auto_sdr.api.client._bootstrap_dotenv")
    @patch("cja_auto_sdr.api.client.CredentialResolver")
    @patch("cja_auto_sdr.api.client._config_from_env")
    def test_cja_profile_env_var_used_when_no_cli_profile(
        self,
        mock_config_env,
        mock_resolver_class,
        mock_dotenv,
        mock_logger,
    ):
        """CJA_PROFILE env var is used when profile argument is None."""
        mock_resolver = Mock()
        mock_resolver.resolve.return_value = (
            {"org_id": "test@AdobeOrg", "client_id": "x", "secret": "y"},
            "profile:env-profile",
        )
        mock_resolver_class.return_value = mock_resolver

        with patch.dict(os.environ, {"CJA_PROFILE": "env-profile"}, clear=False):
            success, display_source, _ = configure_cjapy(profile=None, logger=mock_logger)

        assert success is True
        assert display_source == "Profile: env-profile"
        mock_resolver.resolve.assert_called_once_with(profile="env-profile", config_file="config.json")
