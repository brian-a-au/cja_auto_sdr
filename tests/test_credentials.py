"""Tests for cja_auto_sdr.core.credentials module.

Covers: normalize_credential_value, filter_credentials, CredentialLoader subclasses
(JsonFileCredentialLoader, DotenvCredentialLoader, EnvironmentCredentialLoader),
CredentialResolver, and legacy helper functions.
"""

import json
import logging
import os
from unittest.mock import MagicMock, patch

import pytest

from cja_auto_sdr.core.credentials import (
    CredentialResolver,
    DotenvCredentialLoader,
    EnvironmentCredentialLoader,
    JsonFileCredentialLoader,
    filter_credentials,
    load_credentials_from_env,
    normalize_credential_value,
    normalize_scopes_value,
    validate_env_credentials,
)
from cja_auto_sdr.core.exceptions import (
    CredentialSourceError,
    ProfileConfigError,
    ProfileNotFoundError,
)

# ==================== normalize_credential_value ====================


class TestNormalizeCredentialValue:
    """Test normalize_credential_value helper."""

    def test_none_returns_empty_string(self):
        """None should return empty string (line 35)."""
        assert normalize_credential_value(None) == ""

    def test_strips_whitespace(self):
        """Whitespace-padded strings should be stripped."""
        assert normalize_credential_value("  hello  ") == "hello"

    def test_strips_double_quotes(self):
        """Surrounding double quotes should be removed (line 39)."""
        assert normalize_credential_value('"my_value"') == "my_value"

    def test_strips_single_quotes(self):
        """Surrounding single quotes should be removed (line 39)."""
        assert normalize_credential_value("'my_value'") == "my_value"

    def test_does_not_strip_mismatched_quotes(self):
        """Mismatched quotes should not be stripped."""
        assert normalize_credential_value("\"my_value'") == "\"my_value'"

    def test_single_char_not_stripped(self):
        """Single character strings should not be treated as quotes."""
        assert normalize_credential_value('"') == '"'

    def test_empty_string_returns_empty(self):
        """Empty string should stay empty."""
        assert normalize_credential_value("") == ""

    def test_integer_converted_to_string(self):
        """Non-string types are converted via str()."""
        assert normalize_credential_value(42) == "42"

    def test_strips_whitespace_then_quotes(self):
        """Whitespace is stripped first, then quotes."""
        assert normalize_credential_value('  "value"  ') == "value"

    def test_empty_quoted_string(self):
        """Empty double-quoted string becomes empty."""
        assert normalize_credential_value('""') == ""


# ==================== filter_credentials ====================


class TestNormalizeScopesValue:
    """Test scopes-specific normalization helpers."""

    def test_list_values_become_comma_delimited_string(self):
        assert normalize_scopes_value(["openid", "AdobeID"]) == "openid,AdobeID"

    def test_compact_mode_normalizes_delimiters_for_cjapy(self):
        assert normalize_scopes_value("openid, AdobeID read_organizations", compact=True) == (
            "openid,AdobeID,read_organizations"
        )


class TestFilterCredentials:
    """Test filter_credentials function."""

    def test_filters_to_known_fields(self):
        """Only known credential fields should survive filtering."""
        raw = {
            "org_id": "test@AdobeOrg",
            "client_id": "abc",
            "unknown_field": "should be removed",
        }
        result = filter_credentials(raw)
        assert "org_id" in result
        assert "client_id" in result
        assert "unknown_field" not in result

    def test_removes_falsy_values(self):
        """Keys with falsy values should be excluded."""
        raw = {
            "org_id": "test@AdobeOrg",
            "client_id": "",
            "secret": None,
        }
        result = filter_credentials(raw)
        assert "org_id" in result
        assert "client_id" not in result
        assert "secret" not in result

    def test_normalizes_values(self):
        """Values should be normalized (stripped, unquoted)."""
        raw = {"org_id": '  "test@AdobeOrg"  '}
        result = filter_credentials(raw)
        assert result["org_id"] == "test@AdobeOrg"

    def test_empty_dict_returns_empty(self):
        """Empty input returns empty output."""
        assert filter_credentials({}) == {}

    def test_all_known_fields_pass_through(self):
        """All five known credential fields should pass through."""
        raw = {
            "org_id": "o",
            "client_id": "c",
            "secret": "s",
            "scopes": "sc",
            "sandbox": "sb",
        }
        result = filter_credentials(raw)
        assert len(result) == 5

    def test_normalizes_list_valued_scopes(self):
        """List-valued JSON scopes should be preserved as a usable string."""
        raw = {
            "org_id": "o",
            "scopes": ["openid", "AdobeID"],
        }
        result = filter_credentials(raw)
        assert result["scopes"] == "openid,AdobeID"


# ==================== CredentialLoader base class ====================


class TestCredentialLoaderBase:
    """Test the CredentialLoader.load() error-handling wrapper."""

    def test_load_returns_none_on_os_error(self, tmp_path):
        """OSError during _load_impl should be caught and return None (lines 84-86)."""
        loader = JsonFileCredentialLoader(tmp_path / "config.json")
        logger = MagicMock()

        # Force an OSError by patching _load_impl
        with patch.object(loader, "_load_impl", side_effect=OSError("disk error")):
            result = loader.load(logger)

        assert result is None
        logger.debug.assert_called()

    def test_load_returns_none_on_json_decode_error(self, tmp_path):
        """JSONDecodeError during _load_impl should be caught and return None (lines 84-86)."""
        loader = JsonFileCredentialLoader(tmp_path / "config.json")
        logger = MagicMock()

        with patch.object(
            loader,
            "_load_impl",
            side_effect=json.JSONDecodeError("bad json", "", 0),
        ):
            result = loader.load(logger)

        assert result is None
        logger.debug.assert_called()

    def test_load_filters_credentials(self, tmp_path):
        """Successful load should filter through filter_credentials."""
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"org_id": "test@AdobeOrg", "extra_key": "should_be_removed"}))
        loader = JsonFileCredentialLoader(config_path)
        logger = MagicMock()

        result = loader.load(logger)
        assert result is not None
        assert "org_id" in result
        assert "extra_key" not in result

    def test_load_returns_none_when_impl_returns_none(self, tmp_path):
        """When _load_impl returns None, load should return None."""
        loader = JsonFileCredentialLoader(tmp_path / "nonexistent.json")
        logger = MagicMock()

        result = loader.load(logger)
        assert result is None

    def test_load_returns_none_when_impl_returns_empty(self, tmp_path):
        """When _load_impl returns empty dict, load should return None."""
        loader = JsonFileCredentialLoader(tmp_path / "config.json")
        logger = MagicMock()

        # _load_impl returns {} which is falsy -> load returns None
        with patch.object(loader, "_load_impl", return_value={}):
            result = loader.load(logger)

        assert result is None


# ==================== JsonFileCredentialLoader ====================


class TestJsonFileCredentialLoader:
    """Test JSON file credential loading."""

    def test_source_name(self, tmp_path):
        """source_name should include file name (line 109)."""
        loader = JsonFileCredentialLoader(tmp_path / "config.json")
        assert loader.source_name == "json:config.json"

    def test_load_valid_json(self, tmp_path):
        """Valid JSON config should be loaded successfully."""
        config = {"org_id": "test@AdobeOrg", "client_id": "abc", "secret": "xyz"}
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps(config))

        loader = JsonFileCredentialLoader(config_path)
        logger = MagicMock()
        result = loader._load_impl(logger)

        assert result is not None
        assert result["org_id"] == "test@AdobeOrg"

    def test_nonexistent_file_returns_none(self, tmp_path):
        """Missing file should return None (line 113)."""
        loader = JsonFileCredentialLoader(tmp_path / "missing.json")
        logger = MagicMock()
        result = loader._load_impl(logger)
        assert result is None

    def test_non_dict_json_returns_none(self, tmp_path):
        """JSON that is not a dict should return None (line 120)."""
        config_path = tmp_path / "config.json"
        config_path.write_text('["not", "a", "dict"]')

        loader = JsonFileCredentialLoader(config_path)
        logger = MagicMock()
        result = loader._load_impl(logger)
        assert result is None

    def test_malformed_json_raises(self, tmp_path):
        """Malformed JSON should raise JSONDecodeError (caught by load())."""
        config_path = tmp_path / "config.json"
        config_path.write_text("not valid json {{{")

        loader = JsonFileCredentialLoader(config_path)
        logger = MagicMock()

        # _load_impl will raise, but load() catches it
        result = loader.load(logger)
        assert result is None


# ==================== DotenvCredentialLoader ====================


class TestDotenvCredentialLoader:
    """Test .env file credential loading."""

    def test_source_name(self, tmp_path):
        """source_name should include file name (line 131)."""
        loader = DotenvCredentialLoader(tmp_path / ".env")
        assert loader.source_name == "dotenv:.env"

    def test_nonexistent_file_returns_none(self, tmp_path):
        """Missing .env file should return None (line 134)."""
        loader = DotenvCredentialLoader(tmp_path / ".env")
        logger = MagicMock()
        result = loader._load_impl(logger)
        assert result is None

    def test_load_valid_dotenv(self, tmp_path):
        """Valid .env file with key=value lines should be parsed (lines 134-160)."""
        env_path = tmp_path / ".env"
        env_path.write_text("ORG_ID=test@AdobeOrg\nCLIENT_ID=my_client\nSECRET=my_secret\n")

        loader = DotenvCredentialLoader(env_path)
        logger = MagicMock()
        result = loader._load_impl(logger)

        assert result is not None
        assert result["org_id"] == "test@AdobeOrg"
        assert result["client_id"] == "my_client"
        assert result["secret"] == "my_secret"

    def test_ignores_comments_and_blank_lines(self, tmp_path):
        """Comments and blank lines should be skipped."""
        env_path = tmp_path / ".env"
        env_path.write_text("# This is a comment\n\n   \nORG_ID=test@AdobeOrg\n")

        loader = DotenvCredentialLoader(env_path)
        logger = MagicMock()
        result = loader._load_impl(logger)

        assert result is not None
        assert result["org_id"] == "test@AdobeOrg"
        assert len(result) == 1

    def test_strips_double_quotes(self, tmp_path):
        """Double-quoted values should be unquoted (lines 148-156)."""
        env_path = tmp_path / ".env"
        env_path.write_text('ORG_ID="test@AdobeOrg"\n')

        loader = DotenvCredentialLoader(env_path)
        logger = MagicMock()
        result = loader._load_impl(logger)

        assert result["org_id"] == "test@AdobeOrg"

    def test_strips_single_quotes(self, tmp_path):
        """Single-quoted values should be unquoted (lines 148-156)."""
        env_path = tmp_path / ".env"
        env_path.write_text("ORG_ID='test@AdobeOrg'\n")

        loader = DotenvCredentialLoader(env_path)
        logger = MagicMock()
        result = loader._load_impl(logger)

        assert result["org_id"] == "test@AdobeOrg"

    def test_empty_values_skipped(self, tmp_path):
        """Lines with empty values after the = should be skipped (line 157)."""
        env_path = tmp_path / ".env"
        env_path.write_text("ORG_ID=\nCLIENT_ID=my_client\n")

        loader = DotenvCredentialLoader(env_path)
        logger = MagicMock()
        result = loader._load_impl(logger)

        assert "org_id" not in result
        assert result["client_id"] == "my_client"

    def test_empty_file_returns_none(self, tmp_path):
        """A file with only comments/blank lines returns None (line 160)."""
        env_path = tmp_path / ".env"
        env_path.write_text("# comment only\n\n")

        loader = DotenvCredentialLoader(env_path)
        logger = MagicMock()
        result = loader._load_impl(logger)

        assert result is None

    def test_keys_lowercased(self, tmp_path):
        """Keys should be lowercased (line 145)."""
        env_path = tmp_path / ".env"
        env_path.write_text("ORG_ID=test@AdobeOrg\n")

        loader = DotenvCredentialLoader(env_path)
        logger = MagicMock()
        result = loader._load_impl(logger)

        assert "org_id" in result

    def test_lines_without_equals_skipped(self, tmp_path):
        """Lines without '=' should be skipped (line 143)."""
        env_path = tmp_path / ".env"
        env_path.write_text("no_equals_here\nORG_ID=test@AdobeOrg\n")

        loader = DotenvCredentialLoader(env_path)
        logger = MagicMock()
        result = loader._load_impl(logger)

        assert result is not None
        assert result["org_id"] == "test@AdobeOrg"
        assert len(result) == 1

    def test_value_with_equals_sign(self, tmp_path):
        """Values containing '=' should be preserved via partition."""
        env_path = tmp_path / ".env"
        env_path.write_text("SECRET=abc=def=ghi\n")

        loader = DotenvCredentialLoader(env_path)
        logger = MagicMock()
        result = loader._load_impl(logger)

        assert result["secret"] == "abc=def=ghi"

    def test_empty_key_skipped(self, tmp_path):
        """Lines with empty key (e.g. '=value') should be skipped (line 157)."""
        env_path = tmp_path / ".env"
        env_path.write_text("=some_value\nORG_ID=test@AdobeOrg\n")

        loader = DotenvCredentialLoader(env_path)
        logger = MagicMock()
        result = loader._load_impl(logger)

        assert len(result) == 1
        assert result["org_id"] == "test@AdobeOrg"

    def test_whitespace_around_key_and_value(self, tmp_path):
        """Whitespace around keys and values should be stripped."""
        env_path = tmp_path / ".env"
        env_path.write_text("  ORG_ID  =  test@AdobeOrg  \n")

        loader = DotenvCredentialLoader(env_path)
        logger = MagicMock()
        result = loader._load_impl(logger)

        assert result["org_id"] == "test@AdobeOrg"

    def test_quoted_empty_string_skipped(self, tmp_path):
        """A quoted empty string should be empty after unquoting and skipped."""
        env_path = tmp_path / ".env"
        env_path.write_text('ORG_ID=""\nCLIENT_ID=test\n')

        loader = DotenvCredentialLoader(env_path)
        logger = MagicMock()
        result = loader._load_impl(logger)

        # After removing quotes, value is empty, so key/value skipped
        assert "org_id" not in result
        assert result["client_id"] == "test"


# ==================== EnvironmentCredentialLoader ====================


class TestEnvironmentCredentialLoader:
    """Test environment variable credential loading."""

    def test_source_name(self):
        """source_name should be 'environment' (line 168)."""
        loader = EnvironmentCredentialLoader()
        assert loader.source_name == "environment"

    def test_loads_from_env_vars(self, clean_env):
        """Should load credentials from environment variables."""
        env = {
            "ORG_ID": "test@AdobeOrg",
            "CLIENT_ID": "my_client",
            "SECRET": "my_secret",
            "SCOPES": "openid",
        }
        with patch.dict(os.environ, env, clear=False):
            loader = EnvironmentCredentialLoader()
            logger = MagicMock()
            result = loader._load_impl(logger)

        assert result is not None
        assert result["org_id"] == "test@AdobeOrg"
        assert result["client_id"] == "my_client"

    def test_no_env_vars_returns_none(self, clean_env):
        """Returns None when no credential env vars are set."""
        loader = EnvironmentCredentialLoader()
        logger = MagicMock()
        result = loader._load_impl(logger)
        assert result is None

    def test_ignores_whitespace_only_env_vars(self, clean_env):
        """Whitespace-only env vars should be ignored."""
        with patch.dict(os.environ, {"ORG_ID": "   ", "CLIENT_ID": ""}, clear=False):
            loader = EnvironmentCredentialLoader()
            logger = MagicMock()
            result = loader._load_impl(logger)

        assert result is None


# ==================== CredentialResolver ====================


class TestCredentialResolver:
    """Test the CredentialResolver class."""

    def _make_resolver(self):
        """Create a resolver with a mock logger."""
        logger = logging.getLogger("test_credential_resolver")
        return CredentialResolver(logger)

    def test_resolve_from_profile(self, clean_env):
        """Profile credentials should take highest priority (lines 214-217)."""
        resolver = self._make_resolver()
        fake_creds = {
            "org_id": "profile@AdobeOrg",
            "client_id": "a" * 32,
            "secret": "b" * 32,
            "scopes": "openid",
        }

        with patch(
            "cja_auto_sdr.core.credentials.CredentialResolver._try_profile",
            return_value=(fake_creds, "profile:test"),
        ):
            creds, source = resolver.resolve(profile="test")

        assert source == "profile:test"
        assert creds["org_id"] == "profile@AdobeOrg"

    def test_resolve_from_env_warns_about_config_file(self, tmp_path, clean_env):
        """When env creds are valid and config file exists, warn (lines 223-226)."""
        resolver = self._make_resolver()
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"org_id": "x@AdobeOrg"}))

        valid_creds = {
            "org_id": "env@AdobeOrg",
            "client_id": "a" * 32,
            "secret": "b" * 32,
            "scopes": "openid",
        }

        with (
            patch.object(resolver, "_try_environment", return_value=(valid_creds, "environment")),
            patch.object(resolver, "_warn_multiple_sources") as mock_warn,
        ):
            _creds, source = resolver.resolve(config_file=config_path)

        assert source == "environment"
        mock_warn.assert_called_once_with(config_path)

    def test_resolve_from_env_no_warn_without_config_file(self, tmp_path, clean_env):
        """When env creds are valid but config file does NOT exist, no warn."""
        resolver = self._make_resolver()
        config_path = tmp_path / "nonexistent.json"

        valid_creds = {
            "org_id": "env@AdobeOrg",
            "client_id": "a" * 32,
            "secret": "b" * 32,
            "scopes": "openid",
        }

        with (
            patch.object(resolver, "_try_environment", return_value=(valid_creds, "environment")),
            patch.object(resolver, "_warn_multiple_sources") as mock_warn,
        ):
            _creds, source = resolver.resolve(config_file=config_path)

        assert source == "environment"
        mock_warn.assert_not_called()

    def test_resolve_no_credentials_raises(self, tmp_path, clean_env):
        """When no source has credentials, raise CredentialSourceError."""
        resolver = self._make_resolver()
        config_path = tmp_path / "nonexistent.json"

        with pytest.raises(CredentialSourceError) as exc_info:
            resolver.resolve(config_file=config_path)

        assert "No valid credentials found" in str(exc_info.value)

    def test_resolve_falls_back_to_config_file(self, tmp_path, clean_env):
        """When env has no creds, falls back to config file."""
        resolver = self._make_resolver()
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "org_id": "config@AdobeOrg",
                    "client_id": "a" * 32,
                    "secret": "b" * 32,
                    "scopes": "openid",
                },
            ),
        )

        creds, source = resolver.resolve(config_file=config_path)

        assert source == "config:config.json"
        assert creds["org_id"] == "config@AdobeOrg"


class TestCredentialResolverTryProfile:
    """Test CredentialResolver._try_profile method."""

    def _make_resolver(self):
        logger = logging.getLogger("test_try_profile")
        return CredentialResolver(logger)

    def test_profile_valid_credentials(self, clean_env):
        """Valid profile credentials should be returned (lines 254-265)."""
        resolver = self._make_resolver()
        valid_creds = {
            "org_id": "profile@AdobeOrg",
            "client_id": "a" * 32,
            "secret": "b" * 32,
            "scopes": "openid",
        }

        with patch(
            "cja_auto_sdr.generator.load_profile_credentials",
            return_value=valid_creds,
        ):
            creds, source = resolver._try_profile("my-profile")

        assert creds is not None
        assert source == "profile:my-profile"

    def test_profile_invalid_credentials_returns_none(self, clean_env):
        """Profile with invalid credentials should return (None, '') (line 276)."""
        resolver = self._make_resolver()
        # Missing required fields triggers is_valid=False in non-strict mode
        invalid_creds = {
            "org_id": "bad_org",
        }

        with patch(
            "cja_auto_sdr.generator.load_profile_credentials",
            return_value=invalid_creds,
        ):
            creds, source = resolver._try_profile("my-profile")

        assert creds is None
        assert source == ""

    def test_profile_not_found_raises_credential_source_error(self, clean_env):
        """ProfileNotFoundError should be wrapped in CredentialSourceError (lines 267-270)."""
        resolver = self._make_resolver()

        with patch(
            "cja_auto_sdr.generator.load_profile_credentials",
            side_effect=ProfileNotFoundError("not found", profile_name="missing", details="check path"),
        ):
            with pytest.raises(CredentialSourceError) as exc_info:
                resolver._try_profile("missing")

        assert "missing" in str(exc_info.value)

    def test_profile_config_error_raises_credential_source_error(self, clean_env):
        """ProfileConfigError should be wrapped in CredentialSourceError (lines 271-274)."""
        resolver = self._make_resolver()

        with patch(
            "cja_auto_sdr.generator.load_profile_credentials",
            side_effect=ProfileConfigError("bad config", profile_name="broken", details="invalid JSON"),
        ):
            with pytest.raises(CredentialSourceError) as exc_info:
                resolver._try_profile("broken")

        assert "broken" in str(exc_info.value)

    def test_profile_returns_none_when_load_returns_none(self, clean_env):
        """When load_profile_credentials returns None, _try_profile returns (None, '')."""
        resolver = self._make_resolver()

        with patch(
            "cja_auto_sdr.generator.load_profile_credentials",
            return_value=None,
        ):
            creds, source = resolver._try_profile("empty")

        assert creds is None
        assert source == ""


class TestCredentialResolverTryEnvironment:
    """Test CredentialResolver._try_environment method."""

    def _make_resolver(self):
        logger = logging.getLogger("test_try_env")
        return CredentialResolver(logger)

    def test_valid_env_credentials(self, clean_env):
        """Valid environment credentials should be returned (lines 290-291)."""
        resolver = self._make_resolver()
        env = {
            "ORG_ID": "env@AdobeOrg",
            "CLIENT_ID": "a" * 32,
            "SECRET": "b" * 32,
            "SCOPES": "openid",
        }
        with patch.dict(os.environ, env, clear=False):
            creds, source = resolver._try_environment()

        assert creds is not None
        assert source == "environment"

    def test_invalid_env_credentials_returns_none(self, clean_env):
        """Invalid env credentials should fall through and return (None, '')."""
        resolver = self._make_resolver()
        env = {
            "ORG_ID": "bad_org",  # Missing @AdobeOrg
            "CLIENT_ID": "short",
            "SECRET": "tiny",
            "SCOPES": "openid",
        }
        with patch.dict(os.environ, env, clear=False):
            creds, source = resolver._try_environment()

        assert creds is None
        assert source == ""

    def test_no_env_vars_returns_none(self, clean_env):
        """No env vars should return (None, '')."""
        resolver = self._make_resolver()
        creds, source = resolver._try_environment()

        assert creds is None
        assert source == ""


class TestCredentialResolverTryConfigFile:
    """Test CredentialResolver._try_config_file method."""

    def _make_resolver(self):
        logger = logging.getLogger("test_try_config")
        return CredentialResolver(logger)

    def test_valid_config_file(self, tmp_path):
        """Valid config.json should be loaded and returned."""
        resolver = self._make_resolver()
        config_path = tmp_path / "config.json"
        config_path.write_text(
            json.dumps(
                {
                    "org_id": "config@AdobeOrg",
                    "client_id": "a" * 32,
                    "secret": "b" * 32,
                    "scopes": "openid",
                },
            ),
        )

        creds, source = resolver._try_config_file(config_path)
        assert creds is not None
        assert source == "config:config.json"

    def test_nonexistent_config_file(self, tmp_path):
        """Missing config file should return (None, '') (lines 310-312)."""
        resolver = self._make_resolver()
        creds, source = resolver._try_config_file(tmp_path / "missing.json")
        assert creds is None
        assert source == ""

    def test_invalid_config_file_raises(self, tmp_path):
        """Config file with missing required fields should raise CredentialSourceError (lines 325-330)."""
        resolver = self._make_resolver()
        config_path = tmp_path / "config.json"
        # Missing 'secret' - a required field -> non-strict validation fails
        config_path.write_text(
            json.dumps(
                {
                    "org_id": "test@AdobeOrg",
                    "client_id": "a" * 32,
                    # secret is missing
                    "scopes": "openid",
                },
            ),
        )

        with pytest.raises(CredentialSourceError) as exc_info:
            resolver._try_config_file(config_path)

        assert "validation errors" in str(exc_info.value)

    def test_config_file_empty_json_object(self, tmp_path):
        """Config file with empty JSON object returns (None, '') (line 332)."""
        resolver = self._make_resolver()
        config_path = tmp_path / "config.json"
        config_path.write_text("{}")

        creds, source = resolver._try_config_file(config_path)
        assert creds is None
        assert source == ""

    def test_config_file_only_unknown_fields(self, tmp_path):
        """Config file with only unknown fields returns (None, '') after filtering."""
        resolver = self._make_resolver()
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"unknown_field": "value"}))

        creds, source = resolver._try_config_file(config_path)
        assert creds is None
        assert source == ""


class TestCredentialResolverWarnMultipleSources:
    """Test CredentialResolver._warn_multiple_sources method."""

    def test_warn_logs_banner(self, tmp_path):
        """Multiple source warning should log a banner (lines 336-345)."""
        logger = MagicMock()
        resolver = CredentialResolver(logger)
        config_path = tmp_path / "config.json"

        resolver._warn_multiple_sources(config_path)

        # Should have multiple warning calls
        assert logger.warning.call_count >= 8
        # Check key messages are present
        warning_messages = [str(call) for call in logger.warning.call_args_list]
        combined = " ".join(warning_messages)
        assert "NOTICE" in combined
        assert "Environment variables" in combined or "ENVIRONMENT VARIABLES" in combined
        assert str(config_path) in combined


# ==================== Legacy standalone functions ====================


class TestLoadCredentialsFromEnvLegacy:
    """Test the legacy load_credentials_from_env function (also in credentials.py)."""

    def test_loads_all_fields(self, clean_env):
        """All ENV_VAR_MAPPING fields should be loaded."""
        env = {
            "ORG_ID": "test@AdobeOrg",
            "CLIENT_ID": "my_client",
            "SECRET": "my_secret",
            "SCOPES": "openid",
            "SANDBOX": "prod",
        }
        with patch.dict(os.environ, env, clear=False):
            result = load_credentials_from_env()

        assert result is not None
        assert result["org_id"] == "test@AdobeOrg"
        assert result["sandbox"] == "prod"

    def test_no_env_vars_returns_none(self, clean_env):
        """No env vars should return None."""
        result = load_credentials_from_env()
        assert result is None


class TestValidateEnvCredentialsLegacy:
    """Test the legacy validate_env_credentials function."""

    def test_valid_credentials_pass(self):
        """Complete valid credentials should pass."""
        creds = {
            "org_id": "test@AdobeOrg",
            "client_id": "a" * 32,
            "secret": "b" * 32,
            "scopes": "openid",
        }
        logger = MagicMock()
        assert validate_env_credentials(creds, logger) is True

    def test_missing_required_field_fails(self):
        """Missing required field should return False."""
        creds = {
            "org_id": "test@AdobeOrg",
            "client_id": "a" * 32,
            # missing secret
        }
        logger = MagicMock()
        assert validate_env_credentials(creds, logger) is False

    def test_empty_required_field_fails(self):
        """Empty required field should return False."""
        creds = {
            "org_id": "test@AdobeOrg",
            "client_id": "a" * 32,
            "secret": "   ",
        }
        logger = MagicMock()
        assert validate_env_credentials(creds, logger) is False


# ---------------------------------------------------------------------------
# v3.4.5 coverage gap tests (moved from test_v345_coverage_gaps.py)
# ---------------------------------------------------------------------------


class TestNormalizeScopeTokensNonStringNonIterable:
    """Lines 63-64: non-string, non-iterable value falls through to normalize."""

    def test_integer_normalizes_to_token(self) -> None:
        from cja_auto_sdr.core.credentials import _normalize_scope_tokens

        result = _normalize_scope_tokens(42)
        assert result == ["42"]

    def test_zero_normalizes_to_token(self) -> None:
        from cja_auto_sdr.core.credentials import _normalize_scope_tokens

        result = _normalize_scope_tokens(0)
        assert result == ["0"]

    def test_false_normalizes_to_token(self) -> None:
        from cja_auto_sdr.core.credentials import _normalize_scope_tokens

        result = _normalize_scope_tokens(False)
        assert result == ["False"]
