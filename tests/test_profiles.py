"""Tests for profile management functionality"""

import json
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cja_auto_sdr.generator import (
    ProfileConfigError,
    ProfileError,
    ProfileNotFoundError,
    _read_profile_org_id,
    get_cja_home,
    get_profile_path,
    get_profiles_dir,
    import_profile_non_interactive,
    list_profiles,
    load_profile_config_json,
    load_profile_credentials,
    load_profile_dotenv,
    load_profile_import_source,
    mask_sensitive_value,
    resolve_active_profile,
    show_profile,
    validate_profile_name,
)


class TestGetCjaHome:
    """Test CJA home directory resolution"""

    def test_default_home(self):
        """Test default ~/.cja path when CJA_HOME not set"""
        with patch.dict(os.environ, {}, clear=True):
            # Clear CJA_HOME if it exists
            os.environ.pop("CJA_HOME", None)
            home = get_cja_home()
            assert home == Path.home() / ".cja"

    def test_custom_home_from_env(self):
        """Test custom path from CJA_HOME environment variable"""
        with patch.dict(os.environ, {"CJA_HOME": "/custom/path"}, clear=False):
            home = get_cja_home()
            assert home == Path("/custom/path")

    def test_home_with_tilde_expansion(self):
        """Test that ~ is expanded in CJA_HOME"""
        with patch.dict(os.environ, {"CJA_HOME": "~/my-cja"}, clear=False):
            home = get_cja_home()
            assert str(home).startswith(str(Path.home()))


class TestGetProfilesDir:
    """Test profiles directory resolution"""

    def test_profiles_dir(self):
        """Test profiles directory is under CJA home"""
        with patch("cja_auto_sdr.generator.get_cja_home", return_value=Path("/home/test/.cja")):
            profiles = get_profiles_dir()
            assert profiles == Path("/home/test/.cja/orgs")


class TestGetProfilePath:
    """Test profile path resolution"""

    def test_profile_path(self):
        """Test profile path includes profile name"""
        with patch("cja_auto_sdr.generator.get_profiles_dir", return_value=Path("/home/test/.cja/orgs")):
            path = get_profile_path("client-a")
            assert path == Path("/home/test/.cja/orgs/client-a")


class TestValidateProfileName:
    """Test profile name validation"""

    def test_valid_simple_name(self):
        """Test valid simple profile name"""
        is_valid, error = validate_profile_name("client")
        assert is_valid is True
        assert error is None

    def test_valid_name_with_dashes(self):
        """Test valid name with dashes"""
        is_valid, error = validate_profile_name("client-a")
        assert is_valid is True
        assert error is None

    def test_valid_name_with_underscores(self):
        """Test valid name with underscores"""
        is_valid, error = validate_profile_name("client_a")
        assert is_valid is True
        assert error is None

    def test_valid_name_with_numbers(self):
        """Test valid name with numbers"""
        is_valid, error = validate_profile_name("client1")
        assert is_valid is True
        assert error is None

    def test_empty_name_invalid(self):
        """Test empty name is invalid"""
        is_valid, error = validate_profile_name("")
        assert is_valid is False
        assert "empty" in error.lower()

    def test_name_starting_with_dash_invalid(self):
        """Test name starting with dash is invalid"""
        is_valid, error = validate_profile_name("-client")
        assert is_valid is False
        assert "invalid" in error.lower()

    def test_name_with_spaces_invalid(self):
        """Test name with spaces is invalid"""
        is_valid, error = validate_profile_name("client a")
        assert is_valid is False
        assert "invalid" in error.lower()

    def test_name_with_special_chars_invalid(self):
        """Test name with special characters is invalid"""
        is_valid, error = validate_profile_name("client@org")
        assert is_valid is False
        assert "invalid" in error.lower()

    def test_name_too_long_invalid(self):
        """Test name longer than 64 chars is invalid"""
        long_name = "a" * 65
        is_valid, error = validate_profile_name(long_name)
        assert is_valid is False
        assert "too long" in error.lower()


class TestLoadProfileConfigJson:
    """Test loading credentials from config.json"""

    def test_load_valid_config(self, tmp_path):
        """Test loading valid config.json"""
        config = {"org_id": "test@AdobeOrg", "client_id": "test_client_id", "secret": "test_secret", "scopes": "openid"}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config))

        result = load_profile_config_json(tmp_path)
        assert result is not None
        assert result["org_id"] == "test@AdobeOrg"
        assert result["client_id"] == "test_client_id"

    def test_load_nonexistent_config(self, tmp_path):
        """Test loading nonexistent config.json returns None"""
        result = load_profile_config_json(tmp_path)
        assert result is None

    def test_load_invalid_json(self, tmp_path):
        """Test loading invalid JSON returns None"""
        config_file = tmp_path / "config.json"
        config_file.write_text("not valid json")

        result = load_profile_config_json(tmp_path)
        assert result is None

    def test_strips_whitespace(self, tmp_path):
        """Test that values are stripped of whitespace"""
        config = {"org_id": "  test@AdobeOrg  "}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config))

        result = load_profile_config_json(tmp_path)
        assert result["org_id"] == "test@AdobeOrg"

    def test_normalizes_list_scopes(self, tmp_path):
        """List-valued scopes in profile JSON should stay usable for cjapy.configure."""
        config = {"org_id": "test@AdobeOrg", "scopes": ["openid", "AdobeID"]}
        config_file = tmp_path / "config.json"
        config_file.write_text(json.dumps(config))

        result = load_profile_config_json(tmp_path)
        assert result is not None
        assert result["scopes"] == "openid,AdobeID"

    def test_returns_none_on_oserror(self, tmp_path):
        """OSError while opening an existing config.json returns None."""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"org_id": "test@AdobeOrg"}')

        with patch("cja_auto_sdr.core.profiles.open", side_effect=OSError("read denied")):
            result = load_profile_config_json(tmp_path)

        assert result is None


class TestLoadProfileDotenv:
    """Test loading credentials from .env file"""

    def test_load_valid_env(self, tmp_path):
        """Test loading valid .env file"""
        env_content = """
ORG_ID=test@AdobeOrg
CLIENT_ID=test_client_id
SECRET=test_secret
SCOPES=openid
"""
        env_file = tmp_path / ".env"
        env_file.write_text(env_content)

        result = load_profile_dotenv(tmp_path)
        assert result is not None
        assert result["org_id"] == "test@AdobeOrg"
        assert result["client_id"] == "test_client_id"

    def test_load_nonexistent_env(self, tmp_path):
        """Test loading nonexistent .env returns None"""
        result = load_profile_dotenv(tmp_path)
        assert result is None

    def test_ignores_comments(self, tmp_path):
        """Test that comments are ignored"""
        env_content = """
# This is a comment
ORG_ID=test@AdobeOrg
# CLIENT_ID=commented_out
"""
        env_file = tmp_path / ".env"
        env_file.write_text(env_content)

        result = load_profile_dotenv(tmp_path)
        assert result["org_id"] == "test@AdobeOrg"
        assert "client_id" not in result

    def test_strips_quotes(self, tmp_path):
        """Test that quotes are stripped from values"""
        env_content = """
ORG_ID="test@AdobeOrg"
CLIENT_ID='test_client_id'
"""
        env_file = tmp_path / ".env"
        env_file.write_text(env_content)

        result = load_profile_dotenv(tmp_path)
        assert result["org_id"] == "test@AdobeOrg"
        assert result["client_id"] == "test_client_id"

    def test_malformed_non_utf8_env_returns_none(self, tmp_path):
        """Malformed/non-UTF8 .env should be treated as unreadable."""
        (tmp_path / ".env").write_bytes(b"\xff\xfe\x00invalid")
        result = load_profile_dotenv(tmp_path)
        assert result is None


class TestLoadProfileCredentials:
    """Test loading and merging profile credentials"""

    def test_load_from_config_json_only(self, tmp_path):
        """Test loading from config.json when no .env exists"""
        # Create profile directory
        profile_dir = tmp_path / "orgs" / "test-profile"
        profile_dir.mkdir(parents=True)

        config = {"org_id": "test@AdobeOrg", "client_id": "test_client_id", "secret": "test_secret", "scopes": "openid"}
        (profile_dir / "config.json").write_text(json.dumps(config))

        logger = MagicMock()
        with patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir):
            result = load_profile_credentials("test-profile", logger)

        assert result["org_id"] == "test@AdobeOrg"
        assert result["client_id"] == "test_client_id"

    def test_env_overrides_json(self, tmp_path):
        """Test that .env values override config.json"""
        # Create profile directory
        profile_dir = tmp_path / "orgs" / "test-profile"
        profile_dir.mkdir(parents=True)

        # config.json with one value
        config = {"org_id": "json@AdobeOrg", "client_id": "json_client"}
        (profile_dir / "config.json").write_text(json.dumps(config))

        # .env with different org_id
        (profile_dir / ".env").write_text("ORG_ID=env@AdobeOrg")

        logger = MagicMock()
        with patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir):
            result = load_profile_credentials("test-profile", logger)

        # .env should override config.json
        assert result["org_id"] == "env@AdobeOrg"
        # client_id from config.json should still be present
        assert result["client_id"] == "json_client"

    def test_profile_not_found_raises_error(self, tmp_path):
        """Test that missing profile raises ProfileNotFoundError"""
        logger = MagicMock()
        nonexistent_path = tmp_path / "orgs" / "nonexistent"

        with patch("cja_auto_sdr.generator.get_profile_path", return_value=nonexistent_path):
            with pytest.raises(ProfileNotFoundError):
                load_profile_credentials("nonexistent", logger)

    def test_empty_profile_raises_error(self, tmp_path):
        """Test that profile with no config raises ProfileConfigError"""
        # Create empty profile directory
        profile_dir = tmp_path / "orgs" / "empty-profile"
        profile_dir.mkdir(parents=True)

        logger = MagicMock()
        with patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir):
            with pytest.raises(ProfileConfigError):
                load_profile_credentials("empty-profile", logger)

    def test_invalid_profile_name_raises_error(self):
        """Test that invalid profile name raises ProfileConfigError"""
        logger = MagicMock()
        with pytest.raises(ProfileConfigError):
            load_profile_credentials("invalid name", logger)


class TestResolveActiveProfile:
    """Test profile resolution priority"""

    def test_cli_profile_takes_precedence(self):
        """Test that CLI profile overrides environment variable"""
        with patch.dict(os.environ, {"CJA_PROFILE": "env-profile"}):
            result = resolve_active_profile("cli-profile")
            assert result == "cli-profile"

    def test_env_profile_used_when_no_cli(self):
        """Test that environment variable is used when no CLI profile"""
        with patch.dict(os.environ, {"CJA_PROFILE": "env-profile"}):
            result = resolve_active_profile(None)
            assert result == "env-profile"

    def test_returns_none_when_no_profile(self):
        """Test that None is returned when no profile specified"""
        # Clear CJA_PROFILE from environment
        env = os.environ.copy()
        env.pop("CJA_PROFILE", None)
        with patch.dict(os.environ, env, clear=True):
            result = resolve_active_profile(None)
            assert result is None


class TestMaskSensitiveValue:
    """Test sensitive value masking"""

    def test_mask_normal_value(self):
        """Test masking a normal length value"""
        result = mask_sensitive_value("abcdefghij", show_chars=2)
        assert result == "ab******ij"

    def test_mask_short_value(self):
        """Test masking a value shorter than show_chars*2"""
        result = mask_sensitive_value("abc", show_chars=2)
        assert result == "***"

    def test_mask_empty_value(self):
        """Test masking empty value"""
        result = mask_sensitive_value("")
        assert result == "(empty)"

    def test_mask_default_chars(self):
        """Test default show_chars value (4)"""
        result = mask_sensitive_value("1234567890abcdef")
        assert result.startswith("1234")
        assert result.endswith("cdef")


class TestListProfiles:
    """Test profile listing functionality"""

    def test_list_no_profiles_dir(self, tmp_path, capsys):
        """Test listing when profiles directory doesn't exist"""
        with patch("cja_auto_sdr.generator.get_profiles_dir", return_value=tmp_path / "nonexistent"):
            result = list_profiles()
            assert result is True
            captured = capsys.readouterr()
            assert "No profiles directory" in captured.out

    def test_list_empty_profiles_dir(self, tmp_path, capsys):
        """Test listing when profiles directory is empty"""
        profiles_dir = tmp_path / "orgs"
        profiles_dir.mkdir()

        with patch("cja_auto_sdr.generator.get_profiles_dir", return_value=profiles_dir):
            result = list_profiles()
            assert result is True
            captured = capsys.readouterr()
            assert "No profiles found" in captured.out

    def test_list_profiles_table_format(self, tmp_path, capsys):
        """Test listing profiles in table format"""
        profiles_dir = tmp_path / "orgs"
        profiles_dir.mkdir()

        # Create a profile
        profile = profiles_dir / "client-a"
        profile.mkdir()
        (profile / "config.json").write_text('{"org_id": "test@AdobeOrg"}')

        with patch("cja_auto_sdr.generator.get_profiles_dir", return_value=profiles_dir):
            result = list_profiles(output_format="table")
            assert result is True
            captured = capsys.readouterr()
            assert "client-a" in captured.out

    def test_list_profiles_json_format(self, tmp_path, capsys):
        """Test listing profiles in JSON format"""
        profiles_dir = tmp_path / "orgs"
        profiles_dir.mkdir()

        # Create a profile
        profile = profiles_dir / "client-a"
        profile.mkdir()
        (profile / "config.json").write_text('{"org_id": "test@AdobeOrg"}')

        with patch("cja_auto_sdr.generator.get_profiles_dir", return_value=profiles_dir):
            result = list_profiles(output_format="json")
            assert result is True
            captured = capsys.readouterr()
            output = json.loads(captured.out)
            assert output["count"] == 1
            assert output["profiles"][0]["name"] == "client-a"


class TestShowProfile:
    """Test profile display functionality"""

    def test_show_existing_profile(self, tmp_path, capsys):
        """Test showing an existing profile"""
        # Create profile directory
        profile_dir = tmp_path / "orgs" / "test-profile"
        profile_dir.mkdir(parents=True)

        config = {
            "org_id": "test@AdobeOrg",
            "client_id": "test_client_id_12345678",
            "secret": "test_secret_12345678",
            "scopes": "openid",
        }
        (profile_dir / "config.json").write_text(json.dumps(config))

        with patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir):
            result = show_profile("test-profile")
            assert result is True
            captured = capsys.readouterr()
            assert "test-profile" in captured.out
            assert "test@AdobeOrg" in captured.out
            # Secret should be masked
            assert "test_secret_12345678" not in captured.out

    def test_show_nonexistent_profile(self, tmp_path, capsys):
        """Test showing a nonexistent profile"""
        nonexistent_path = tmp_path / "orgs" / "nonexistent"

        with patch("cja_auto_sdr.generator.get_profile_path", return_value=nonexistent_path):
            result = show_profile("nonexistent")
            assert result is False
            captured = capsys.readouterr()
            assert "Error" in captured.err


class TestProfileImport:
    """Test non-interactive profile import helpers."""

    def test_load_profile_import_source_json(self, tmp_path):
        """JSON source should normalize credential keys."""
        source = tmp_path / "credentials.json"
        source.write_text(
            json.dumps(
                {
                    "ORG_ID": "test@AdobeOrg",
                    "clientId": "1234567890abcdef1234567890abcdef",
                    "client_secret": "abcdefghijklmnop1234567890",
                    "scopes": "openid,AdobeID,read_organizations",
                },
            ),
        )

        credentials = load_profile_import_source(source)
        assert credentials["org_id"] == "test@AdobeOrg"
        assert credentials["client_id"] == "1234567890abcdef1234567890abcdef"
        assert credentials["secret"] == "abcdefghijklmnop1234567890"

    def test_load_profile_import_source_env(self, tmp_path):
        """Env source should map uppercase env vars to config fields."""
        source = tmp_path / "credentials.env"
        source.write_text(
            "\n".join(
                [
                    "ORG_ID=test@AdobeOrg",
                    "CLIENT_ID=1234567890abcdef1234567890abcdef",
                    "SECRET=abcdefghijklmnop1234567890",
                    "SCOPES=openid,AdobeID",
                ],
            ),
        )

        credentials = load_profile_import_source(source)
        assert credentials["org_id"] == "test@AdobeOrg"
        assert credentials["client_id"] == "1234567890abcdef1234567890abcdef"
        assert credentials["secret"] == "abcdefghijklmnop1234567890"
        assert credentials["scopes"] == "openid,AdobeID"

    def test_import_profile_non_interactive_from_json(self, tmp_path):
        """Import should write config.json for the target profile."""
        source = tmp_path / "credentials.json"
        source.write_text(
            json.dumps(
                {
                    "org_id": "test@AdobeOrg",
                    "client_id": "1234567890abcdef1234567890abcdef",
                    "secret": "abcdefghijklmnop1234567890",
                    "scopes": "openid,AdobeID",
                },
            ),
        )

        profile_dir = tmp_path / "orgs" / "client-a"
        with patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir):
            result = import_profile_non_interactive("client-a", source)

        assert result is True
        config_path = profile_dir / "config.json"
        assert config_path.exists()
        config = json.loads(config_path.read_text())
        assert config["org_id"] == "test@AdobeOrg"
        assert config["client_id"] == "1234567890abcdef1234567890abcdef"
        assert config["secret"] == "abcdefghijklmnop1234567890"

    def test_import_profile_non_interactive_rejects_existing_without_overwrite(self, tmp_path):
        """Existing profile should not be replaced without overwrite."""
        source = tmp_path / "credentials.json"
        source.write_text(
            json.dumps(
                {
                    "org_id": "new@AdobeOrg",
                    "client_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                    "secret": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                },
            ),
        )

        profile_dir = tmp_path / "orgs" / "client-a"
        profile_dir.mkdir(parents=True)
        existing_config = profile_dir / "config.json"
        existing_config.write_text(
            json.dumps(
                {
                    "org_id": "existing@AdobeOrg",
                    "client_id": "existing_client",
                    "secret": "existing_secret",
                },
            ),
        )

        with patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir):
            result = import_profile_non_interactive("client-a", source, overwrite=False)

        assert result is False
        assert json.loads(existing_config.read_text())["org_id"] == "existing@AdobeOrg"

    def test_import_profile_non_interactive_rejects_invalid_credential_format(self, tmp_path):
        """Import should fail when credentials fail strict format validation."""
        source = tmp_path / "credentials.json"
        source.write_text(
            json.dumps(
                {
                    "org_id": "not_adobe_org",
                    "client_id": "1234567890abcdef1234567890abcdef",
                    "secret": "abcdefghijklmnop1234567890",
                    "scopes": "openid,AdobeID",
                },
            ),
        )

        profile_dir = tmp_path / "orgs" / "client-a"
        with patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir):
            result = import_profile_non_interactive("client-a", source)

        assert result is False
        assert not (profile_dir / "config.json").exists()


class TestProfileExceptions:
    """Test profile exception classes"""

    def test_profile_error_with_name(self):
        """Test ProfileError includes profile name"""
        error = ProfileError("Test error", profile_name="test-profile")
        assert error.profile_name == "test-profile"

    def test_profile_not_found_error(self):
        """Test ProfileNotFoundError is a ProfileError"""
        error = ProfileNotFoundError("Not found", profile_name="missing")
        assert isinstance(error, ProfileError)

    def test_profile_config_error(self):
        """Test ProfileConfigError is a ProfileError"""
        error = ProfileConfigError("Invalid config", profile_name="bad")
        assert isinstance(error, ProfileError)


class TestReadProfileOrgId:
    """Test _read_profile_org_id() helper — reads org_id from config.json or .env."""

    def test_org_id_from_config_json(self, tmp_path):
        """org_id is read from config.json when present"""
        (tmp_path / "config.json").write_text('{"org_id": "ABC123@AdobeOrg"}')
        assert _read_profile_org_id(tmp_path) == "ABC123@AdobeOrg"

    def test_org_id_from_dotenv(self, tmp_path):
        """org_id is read from .env when config.json has no org_id"""
        (tmp_path / ".env").write_text("ORG_ID=DEF456@AdobeOrg\n")
        assert _read_profile_org_id(tmp_path) == "DEF456@AdobeOrg"

    def test_org_id_from_dotenv_lowercase_key(self, tmp_path):
        """Lowercase .env org_id key should be parsed like profile credential loading."""
        (tmp_path / ".env").write_text("org_id=lower@AdobeOrg\n")
        assert _read_profile_org_id(tmp_path) == "lower@AdobeOrg"

    def test_org_id_from_dotenv_with_key_whitespace(self, tmp_path):
        """Whitespace around .env keys should be normalized like profile credential loading."""
        (tmp_path / ".env").write_text("  org_id = spaced@AdobeOrg\n")
        assert _read_profile_org_id(tmp_path) == "spaced@AdobeOrg"

    def test_dotenv_overrides_config_json(self, tmp_path):
        """.env ORG_ID takes precedence over config.json, matching load_profile_credentials"""
        (tmp_path / "config.json").write_text('{"org_id": "FROM_JSON@AdobeOrg"}')
        (tmp_path / ".env").write_text("ORG_ID=FROM_ENV@AdobeOrg\n")
        assert _read_profile_org_id(tmp_path) == "FROM_ENV@AdobeOrg"

    def test_falls_back_to_env_when_json_missing_org_id(self, tmp_path):
        """Falls back to .env when config.json exists but has no org_id key"""
        (tmp_path / "config.json").write_text('{"client_id": "x"}')
        (tmp_path / ".env").write_text("ORG_ID=FALLBACK@AdobeOrg\n")
        assert _read_profile_org_id(tmp_path) == "FALLBACK@AdobeOrg"

    def test_returns_none_when_no_org_id_anywhere(self, tmp_path):
        """Returns None when neither config.json nor .env has org_id"""
        (tmp_path / "config.json").write_text('{"client_id": "x"}')
        (tmp_path / ".env").write_text("CLIENT_ID=y\n")
        assert _read_profile_org_id(tmp_path) is None

    def test_returns_none_for_empty_directory(self, tmp_path):
        """Returns None when profile directory has no config files"""
        assert _read_profile_org_id(tmp_path) is None

    def test_handles_corrupt_config_json(self, tmp_path):
        """Returns None gracefully when config.json is corrupt"""
        (tmp_path / "config.json").write_text("{not valid json!!!")
        assert _read_profile_org_id(tmp_path) is None

    def test_handles_corrupt_json_falls_back_to_env(self, tmp_path):
        """Falls back to .env when config.json is corrupt"""
        (tmp_path / "config.json").write_text("{bad json")
        (tmp_path / ".env").write_text("ORG_ID=RESCUE@AdobeOrg\n")
        assert _read_profile_org_id(tmp_path) == "RESCUE@AdobeOrg"

    def test_handles_unreadable_config_json(self, tmp_path):
        """Returns None gracefully when config.json is unreadable"""
        config_file = tmp_path / "config.json"
        config_file.write_text('{"org_id": "test@AdobeOrg"}')
        config_file.chmod(0o000)
        try:
            # Should not raise — falls back gracefully
            result = _read_profile_org_id(tmp_path)
            # May be None (unreadable) — the key point is no exception
            assert result is None or isinstance(result, str)
        finally:
            config_file.chmod(0o644)

    def test_handles_unreadable_env_file(self, tmp_path):
        """Returns None gracefully when .env is unreadable"""
        env_file = tmp_path / ".env"
        env_file.write_text("ORG_ID=test@AdobeOrg\n")
        env_file.chmod(0o000)
        try:
            result = _read_profile_org_id(tmp_path)
            assert result is None or isinstance(result, str)
        finally:
            env_file.chmod(0o644)

    def test_malformed_dotenv_falls_back_to_config_json(self, tmp_path):
        """Malformed .env should not crash and should preserve JSON fallback."""
        (tmp_path / "config.json").write_text('{"org_id": "SAFE@AdobeOrg"}')
        (tmp_path / ".env").write_bytes(b"\xff\xfe\x00ORG_ID=bad")
        assert _read_profile_org_id(tmp_path) == "SAFE@AdobeOrg"

    def test_strips_whitespace_from_org_id(self, tmp_path):
        """Whitespace is stripped from org_id values"""
        (tmp_path / "config.json").write_text('{"org_id": "  ABC@AdobeOrg  "}')
        assert _read_profile_org_id(tmp_path) == "ABC@AdobeOrg"

    def test_env_strips_quotes(self, tmp_path):
        """Quotes are stripped from .env ORG_ID values"""
        (tmp_path / ".env").write_text('ORG_ID="QUOTED@AdobeOrg"\n')
        assert _read_profile_org_id(tmp_path) == "QUOTED@AdobeOrg"

    def test_ignores_non_string_org_id(self, tmp_path):
        """Returns None when org_id is not a string (e.g. integer)"""
        (tmp_path / "config.json").write_text('{"org_id": 12345}')
        assert _read_profile_org_id(tmp_path) is None

    def test_ignores_empty_org_id(self, tmp_path):
        """Returns None when org_id is an empty string"""
        (tmp_path / "config.json").write_text('{"org_id": ""}')
        assert _read_profile_org_id(tmp_path) is None

    def test_ignores_empty_env_org_id(self, tmp_path):
        """Returns None when .env ORG_ID has empty value"""
        (tmp_path / ".env").write_text("ORG_ID=\n")
        assert _read_profile_org_id(tmp_path) is None

    def test_json_array_not_dict(self, tmp_path):
        """Returns None when config.json is a JSON array instead of object"""
        (tmp_path / "config.json").write_text('[{"org_id": "test@AdobeOrg"}]')
        assert _read_profile_org_id(tmp_path) is None

    def test_handles_plain_valueerror_from_json_load(self, tmp_path):
        """A bare ValueError (not JSONDecodeError) from json.load is swallowed."""
        (tmp_path / "config.json").write_text('{"org_id": "test@AdobeOrg"}')

        # json.load can raise ValueError subtypes other than JSONDecodeError;
        # the dedicated ValueError branch must keep _read_profile_org_id quiet.
        with patch("cja_auto_sdr.core.profiles.json.load", side_effect=ValueError("bad value")):
            result = _read_profile_org_id(tmp_path)

        assert result is None


class TestListProfilesOrgId:
    """Test that list_profiles() includes org_id in output."""

    def test_table_shows_org_id_column(self, tmp_path, capsys):
        """Table output includes Org ID column header and org_id values"""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        profile = profiles_dir / "client-a"
        profile.mkdir()
        (profile / "config.json").write_text('{"org_id": "ABC123@AdobeOrg"}')

        with patch("cja_auto_sdr.generator.get_profiles_dir", return_value=profiles_dir):
            list_profiles(output_format="table")
            captured = capsys.readouterr()
            assert "Org ID" in captured.out
            assert "ABC123@AdobeOrg" in captured.out

    def test_table_shows_dash_for_missing_org_id(self, tmp_path, capsys):
        """Table output shows em-dash for profiles without org_id"""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        profile = profiles_dir / "no-org"
        profile.mkdir()
        (profile / "config.json").write_text('{"client_id": "x"}')

        with patch("cja_auto_sdr.generator.get_profiles_dir", return_value=profiles_dir):
            list_profiles(output_format="table")
            captured = capsys.readouterr()
            assert "\u2014" in captured.out  # em-dash

    def test_json_includes_org_id(self, tmp_path, capsys):
        """JSON output includes org_id field with string value"""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        profile = profiles_dir / "client-a"
        profile.mkdir()
        (profile / "config.json").write_text('{"org_id": "ABC123@AdobeOrg"}')

        with patch("cja_auto_sdr.generator.get_profiles_dir", return_value=profiles_dir):
            list_profiles(output_format="json")
            captured = capsys.readouterr()
            data = json.loads(captured.out)
            assert data["profiles"][0]["org_id"] == "ABC123@AdobeOrg"

    def test_json_null_for_missing_org_id(self, tmp_path, capsys):
        """JSON output uses null (None) for profiles without org_id"""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        profile = profiles_dir / "no-org"
        profile.mkdir()
        (profile / "config.json").write_text('{"client_id": "x"}')

        with patch("cja_auto_sdr.generator.get_profiles_dir", return_value=profiles_dir):
            list_profiles(output_format="json")
            captured = capsys.readouterr()
            data = json.loads(captured.out)
            assert data["profiles"][0]["org_id"] is None

    def test_table_truncates_long_org_id(self, tmp_path, capsys):
        """Table output truncates excessively long org_id values"""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        profile = profiles_dir / "long-org"
        profile.mkdir()
        long_org = "A" * 60 + "@AdobeOrg"
        (profile / "config.json").write_text(json.dumps({"org_id": long_org}))

        with patch("cja_auto_sdr.generator.get_profiles_dir", return_value=profiles_dir):
            list_profiles(output_format="table")
            captured = capsys.readouterr()
            # Should contain ellipsis, not the full org_id
            assert "\u2026" in captured.out
            assert long_org not in captured.out

    def test_json_preserves_full_long_org_id(self, tmp_path, capsys):
        """JSON output preserves full org_id even when long"""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        profile = profiles_dir / "long-org"
        profile.mkdir()
        long_org = "A" * 60 + "@AdobeOrg"
        (profile / "config.json").write_text(json.dumps({"org_id": long_org}))

        with patch("cja_auto_sdr.generator.get_profiles_dir", return_value=profiles_dir):
            list_profiles(output_format="json")
            captured = capsys.readouterr()
            data = json.loads(captured.out)
            assert data["profiles"][0]["org_id"] == long_org

    def test_org_id_from_env_in_listing(self, tmp_path, capsys):
        """org_id sourced from .env appears in JSON listing"""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()
        profile = profiles_dir / "env-only"
        profile.mkdir()
        (profile / ".env").write_text("ORG_ID=ENV_ORG@AdobeOrg\n")

        with patch("cja_auto_sdr.generator.get_profiles_dir", return_value=profiles_dir):
            list_profiles(output_format="json")
            captured = capsys.readouterr()
            data = json.loads(captured.out)
            assert data["profiles"][0]["org_id"] == "ENV_ORG@AdobeOrg"

    def test_listing_continues_when_org_id_read_fails_for_one_profile(self, tmp_path, capsys):
        """A single unreadable/malformed profile should not abort --profile-list."""
        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()

        good = profiles_dir / "good"
        good.mkdir()
        (good / "config.json").write_text('{"org_id": "GOOD@AdobeOrg"}')

        bad = profiles_dir / "bad"
        bad.mkdir()
        (bad / ".env").write_bytes(b"\xff\xfe\x00malformed")

        with patch("cja_auto_sdr.generator.get_profiles_dir", return_value=profiles_dir):
            result = list_profiles(output_format="json")
            assert result is True

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        by_name = {profile["name"]: profile for profile in data["profiles"]}
        assert by_name["good"]["org_id"] == "GOOD@AdobeOrg"
        assert by_name["bad"]["org_id"] is None

    def test_listing_logs_debug_when_org_id_read_fails(self, tmp_path, caplog, capsys):
        """Debug log is emitted when org_id read fails for a profile."""
        import logging

        profiles_dir = tmp_path / "profiles"
        profiles_dir.mkdir()

        good = profiles_dir / "good"
        good.mkdir()
        (good / "config.json").write_text('{"org_id": "GOOD@AdobeOrg"}')

        bad = profiles_dir / "bad"
        bad.mkdir()
        (bad / "config.json").write_text('{"org_id": "BAD@AdobeOrg"}')

        original = _read_profile_org_id

        def side_effect(profile_path):
            if profile_path == bad:
                raise OSError("boom")
            return original(profile_path)

        with (
            patch("cja_auto_sdr.generator.get_profiles_dir", return_value=profiles_dir),
            patch("cja_auto_sdr.generator._read_profile_org_id", side_effect=side_effect),
            caplog.at_level(logging.DEBUG, logger="cja_auto_sdr.core.profiles"),
        ):
            result = list_profiles(output_format="json")

        assert result is True
        assert "Failed to read org_id from profile 'bad'" in caplog.text

        data = json.loads(capsys.readouterr().out)
        by_name = {profile["name"]: profile for profile in data["profiles"]}
        assert by_name["good"]["org_id"] == "GOOD@AdobeOrg"
        assert by_name["bad"]["org_id"] is None
