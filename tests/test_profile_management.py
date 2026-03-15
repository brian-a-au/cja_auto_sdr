"""Tests for profile management operations: interactive creation, import, test, show.

Covers uncovered lines in generator.py:
- add_profile_interactive (lines 1378-1465)
- import_profile / load_profile_import_source (lines 1524-1543, 1565-1579, 1606-1611)
- profile operations (lines 1662-1664, 1681)
- test_profile (lines 1713-1789)
- show_profile extended paths (lines 1880-1928)
"""

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cja_auto_sdr.generator import (
    add_profile_interactive,
    import_profile_non_interactive,
    load_profile_import_source,
    show_profile,
)
from cja_auto_sdr.generator import test_profile as run_test_profile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

VALID_CREDENTIALS = {
    "org_id": "ABC123@AdobeOrg",
    "client_id": "1234567890abcdef1234567890abcdef",
    "secret": "abcdefghijklmnop1234567890abcdef",
    "scopes": "openid,AdobeID,read_organizations",
}


def _write_config_json(profile_dir: Path, config: dict | None = None) -> None:
    """Write a config.json inside *profile_dir* (creating dirs as needed)."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / "config.json").write_text(json.dumps(config or VALID_CREDENTIALS))


def _write_dotenv(profile_dir: Path, content: str) -> None:
    """Write a .env inside *profile_dir* (creating dirs as needed)."""
    profile_dir.mkdir(parents=True, exist_ok=True)
    (profile_dir / ".env").write_text(content)


# ===========================================================================
# add_profile_interactive
# ===========================================================================


class TestAddProfileInteractive:
    """Tests for the interactive profile creation wizard."""

    def test_invalid_profile_name(self, capsys):
        """Invalid profile name should return False immediately."""
        result = add_profile_interactive("bad name!")
        assert result is False
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_existing_profile_overwrite_declined(self, tmp_path, capsys):
        """Declining overwrite of existing profile returns False."""
        profile_dir = tmp_path / "orgs" / "existing"
        _write_config_json(profile_dir)

        with (
            patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir),
            patch("builtins.input", return_value="n"),
        ):
            result = add_profile_interactive("existing")

        assert result is False
        captured = capsys.readouterr()
        assert "already exists" in captured.out
        assert "Aborted" in captured.out

    def test_existing_profile_overwrite_accepted(self, tmp_path, capsys):
        """Accepting overwrite proceeds with profile creation flow."""
        profile_dir = tmp_path / "orgs" / "existing"
        _write_config_json(profile_dir)

        inputs = iter(["y", "NewOrg@AdobeOrg", "new_client_id", "openid,AdobeID"])

        with (
            patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir),
            patch("builtins.input", side_effect=inputs),
            patch("getpass.getpass", return_value="new_secret_value"),
        ):
            result = add_profile_interactive("existing")

        assert result is True
        captured = capsys.readouterr()
        assert "created successfully" in captured.out

        # Verify config written
        config = json.loads((profile_dir / "config.json").read_text())
        assert config["org_id"] == "NewOrg@AdobeOrg"
        assert config["client_id"] == "new_client_id"
        assert config["secret"] == "new_secret_value"
        assert config["scopes"] == "openid,AdobeID"
        assert (profile_dir / "config.json").stat().st_mode & 0o777 == 0o600

    def test_successful_creation_new_profile(self, tmp_path, capsys):
        """Full happy-path creation of a brand new profile."""
        profile_dir = tmp_path / "orgs" / "new-profile"

        inputs = iter(["MyOrg@AdobeOrg", "my_client_id", "openid"])

        with (
            patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir),
            patch("builtins.input", side_effect=inputs),
            patch("getpass.getpass", return_value="my_secret"),
        ):
            result = add_profile_interactive("new-profile")

        assert result is True
        captured = capsys.readouterr()
        assert "CREATING PROFILE: new-profile" in captured.out
        assert "created successfully" in captured.out
        assert "profile-test" in captured.out

        config = json.loads((profile_dir / "config.json").read_text())
        assert config["org_id"] == "MyOrg@AdobeOrg"
        assert (profile_dir / "config.json").stat().st_mode & 0o777 == 0o600

    def test_empty_org_id_aborts(self, tmp_path, capsys):
        """Empty organization ID causes early exit."""
        profile_dir = tmp_path / "orgs" / "empty-org"

        with (
            patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir),
            patch("builtins.input", return_value=""),
        ):
            result = add_profile_interactive("empty-org")

        assert result is False
        captured = capsys.readouterr()
        assert "Organization ID is required" in captured.err

    def test_empty_client_id_aborts(self, tmp_path, capsys):
        """Empty client ID causes early exit."""
        profile_dir = tmp_path / "orgs" / "empty-cid"
        inputs = iter(["MyOrg@AdobeOrg", ""])

        with (
            patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir),
            patch("builtins.input", side_effect=inputs),
        ):
            result = add_profile_interactive("empty-cid")

        assert result is False
        captured = capsys.readouterr()
        assert "Client ID is required" in captured.err

    def test_empty_secret_aborts(self, tmp_path, capsys):
        """Empty client secret causes early exit."""
        profile_dir = tmp_path / "orgs" / "empty-secret"
        inputs = iter(["MyOrg@AdobeOrg", "my_client_id"])

        with (
            patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir),
            patch("builtins.input", side_effect=inputs),
            patch("getpass.getpass", return_value=""),
        ):
            result = add_profile_interactive("empty-secret")

        assert result is False
        captured = capsys.readouterr()
        assert "Client Secret is required" in captured.err

    def test_empty_scopes_aborts(self, tmp_path, capsys):
        """Empty scopes causes early exit."""
        profile_dir = tmp_path / "orgs" / "empty-scopes"
        inputs = iter(["MyOrg@AdobeOrg", "my_client_id", ""])

        with (
            patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir),
            patch("builtins.input", side_effect=inputs),
            patch("getpass.getpass", return_value="my_secret"),
        ):
            result = add_profile_interactive("empty-scopes")

        assert result is False
        captured = capsys.readouterr()
        assert "OAuth Scopes are required" in captured.err

    def test_keyboard_interrupt_aborts(self, tmp_path, capsys):
        """KeyboardInterrupt during input aborts gracefully."""
        profile_dir = tmp_path / "orgs" / "interrupted"

        with (
            patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir),
            patch("builtins.input", side_effect=KeyboardInterrupt),
        ):
            result = add_profile_interactive("interrupted")

        assert result is False
        captured = capsys.readouterr()
        assert "Aborted" in captured.out

    def test_eoferror_aborts(self, tmp_path, capsys):
        """EOFError during input aborts gracefully."""
        profile_dir = tmp_path / "orgs" / "eof"

        with (
            patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir),
            patch("builtins.input", side_effect=EOFError),
        ):
            result = add_profile_interactive("eof")

        assert result is False
        captured = capsys.readouterr()
        assert "Aborted" in captured.out

    def test_getpass_warning_aborts(self, tmp_path, capsys):
        """GetPassWarning should cause graceful abort with guidance."""
        import getpass

        profile_dir = tmp_path / "orgs" / "no-tty"
        inputs = iter(["MyOrg@AdobeOrg", "my_client_id"])

        with (
            patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir),
            patch("builtins.input", side_effect=inputs),
            patch("getpass.getpass", side_effect=getpass.GetPassWarning("no tty")),
        ):
            result = add_profile_interactive("no-tty")

        assert result is False
        captured = capsys.readouterr()
        assert "Cannot securely read secret" in captured.err

    def test_mkdir_failure(self, tmp_path, capsys):
        """OSError during directory creation returns False."""
        profile_dir = tmp_path / "orgs" / "bad-dir"

        with (
            patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir),
            patch.object(Path, "exists", return_value=False),
            patch.object(Path, "mkdir", side_effect=OSError("Permission denied")),
        ):
            result = add_profile_interactive("bad-dir")

        assert result is False
        captured = capsys.readouterr()
        assert "Error creating profile directory" in captured.err

    def test_config_write_failure(self, tmp_path, capsys):
        """OSError during config.json write returns False."""
        profile_dir = tmp_path / "orgs" / "write-fail"
        # Do NOT create the directory — let the function create it, so it
        # does not trigger the "already exists" overwrite prompt.

        inputs = iter(["MyOrg@AdobeOrg", "my_client_id", "openid"])

        with (
            patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir),
            patch("builtins.input", side_effect=inputs),
            patch("getpass.getpass", return_value="my_secret"),
            patch("cja_auto_sdr.core.profiles.write_json_atomic", side_effect=OSError("Disk full")),
        ):
            result = add_profile_interactive("write-fail")

        assert result is False
        captured = capsys.readouterr()
        assert "Error writing config file" in captured.err


# ===========================================================================
# load_profile_import_source — directory mode
# ===========================================================================


class TestLoadProfileImportSourceDirectory:
    """Tests for importing from a directory containing config.json / .env files."""

    def test_directory_with_config_json_only(self, tmp_path):
        """Directory with only config.json should load credentials."""
        source_dir = tmp_path / "source"
        _write_config_json(source_dir, VALID_CREDENTIALS)

        result = load_profile_import_source(source_dir)
        assert result["org_id"] == VALID_CREDENTIALS["org_id"]
        assert result["client_id"] == VALID_CREDENTIALS["client_id"]

    def test_directory_with_dotenv_only(self, tmp_path):
        """Directory with only .env should load credentials."""
        source_dir = tmp_path / "source"
        source_dir.mkdir(parents=True)
        _write_dotenv(
            source_dir,
            "ORG_ID=Test@AdobeOrg\nCLIENT_ID=abcd1234\nSECRET=secret_val\nSCOPES=openid",
        )

        result = load_profile_import_source(source_dir)
        assert result["org_id"] == "Test@AdobeOrg"
        assert result["client_id"] == "abcd1234"

    def test_directory_with_both_config_and_env(self, tmp_path):
        """.env values should override config.json when both present."""
        source_dir = tmp_path / "source"
        _write_config_json(source_dir, VALID_CREDENTIALS)
        _write_dotenv(source_dir, "ORG_ID=Override@AdobeOrg")

        result = load_profile_import_source(source_dir)
        assert result["org_id"] == "Override@AdobeOrg"
        # Other fields from config.json should still be present
        assert result["client_id"] == VALID_CREDENTIALS["client_id"]

    def test_directory_empty_raises_valueerror(self, tmp_path):
        """Empty directory should raise ValueError."""
        source_dir = tmp_path / "empty_source"
        source_dir.mkdir(parents=True)

        with pytest.raises(ValueError, match="No credentials found"):
            load_profile_import_source(source_dir)

    def test_directory_not_found_raises_filenotfounderror(self, tmp_path):
        """Non-existent directory should raise FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Source not found"):
            load_profile_import_source(tmp_path / "nonexistent")

    def test_directory_with_nested_credentials_key(self, tmp_path):
        """config.json with top-level 'credentials' dict should be unwrapped."""
        source_dir = tmp_path / "nested"
        source_dir.mkdir(parents=True)
        config = {"credentials": VALID_CREDENTIALS}
        (source_dir / "config.json").write_text(json.dumps(config))

        result = load_profile_import_source(source_dir)
        assert result["org_id"] == VALID_CREDENTIALS["org_id"]

    def test_directory_config_json_invalid_type(self, tmp_path):
        """config.json that's not a dict should raise ValueError."""
        source_dir = tmp_path / "bad_config"
        source_dir.mkdir(parents=True)
        (source_dir / "config.json").write_text(json.dumps(["not", "a", "dict"]))

        with pytest.raises(ValueError, match="expected JSON object"):
            load_profile_import_source(source_dir)

    def test_json_file_with_credentials_key(self, tmp_path):
        """JSON file with 'credentials' key should unwrap."""
        source = tmp_path / "wrapped.json"
        source.write_text(json.dumps({"credentials": VALID_CREDENTIALS}))

        result = load_profile_import_source(source)
        assert result["org_id"] == VALID_CREDENTIALS["org_id"]

    def test_json_file_invalid_type(self, tmp_path):
        """JSON file that's not a dict should raise ValueError."""
        source = tmp_path / "bad.json"
        source.write_text(json.dumps("just a string"))

        with pytest.raises(ValueError, match="must be an object"):
            load_profile_import_source(source)

    def test_env_file_with_no_recognized_fields(self, tmp_path):
        """Env file with no recognized fields should raise ValueError."""
        source = tmp_path / "empty.env"
        source.write_text("# only a comment\n")

        with pytest.raises(ValueError, match="No supported credential fields"):
            load_profile_import_source(source)


# ===========================================================================
# import_profile_non_interactive — extended paths
# ===========================================================================


class TestImportProfileNonInteractiveExtended:
    """Extended tests for non-interactive import covering validation, errors."""

    def test_invalid_name_rejects(self, capsys):
        """Invalid profile name should be rejected."""
        result = import_profile_non_interactive("bad name!", "/some/file.json")
        assert result is False
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_source_file_not_found(self, tmp_path, capsys):
        """Non-existent source file returns False with error message."""
        profile_dir = tmp_path / "orgs" / "test-profile"

        with patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir):
            result = import_profile_non_interactive("test-profile", tmp_path / "missing.json")

        assert result is False
        captured = capsys.readouterr()
        assert "Error loading profile import source" in captured.err

    def test_overwrite_existing_profile(self, tmp_path, capsys):
        """Overwrite=True should replace an existing profile."""
        source = tmp_path / "credentials.json"
        source.write_text(json.dumps(VALID_CREDENTIALS))

        profile_dir = tmp_path / "orgs" / "existing"
        _write_config_json(profile_dir, {"org_id": "Old@AdobeOrg", "client_id": "old", "secret": "old"})

        with patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir):
            result = import_profile_non_interactive("existing", source, overwrite=True)

        assert result is True
        config = json.loads((profile_dir / "config.json").read_text())
        assert config["org_id"] == VALID_CREDENTIALS["org_id"]
        assert (profile_dir / "config.json").stat().st_mode & 0o777 == 0o600

    def test_overwrite_warns_about_existing_dotenv(self, tmp_path, capsys):
        """Overwrite with existing .env should warn about potential conflicts."""
        source = tmp_path / "credentials.json"
        source.write_text(json.dumps(VALID_CREDENTIALS))

        profile_dir = tmp_path / "orgs" / "with-env"
        _write_config_json(profile_dir, {"org_id": "Old@AdobeOrg", "client_id": "old", "secret": "old"})
        _write_dotenv(profile_dir, "ORG_ID=EnvOrg@AdobeOrg")

        with patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir):
            result = import_profile_non_interactive("with-env", source, overwrite=True)

        assert result is True
        captured = capsys.readouterr()
        assert "Warning" in captured.out
        assert ".env" in captured.out

    def test_write_oserror(self, tmp_path, capsys):
        """OSError during config write returns False."""
        source = tmp_path / "credentials.json"
        source.write_text(json.dumps(VALID_CREDENTIALS))

        profile_dir = tmp_path / "orgs" / "bad-write"

        with (
            patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir),
            patch("cja_auto_sdr.core.profiles.write_json_atomic", side_effect=OSError("Permission denied")),
        ):
            result = import_profile_non_interactive("bad-write", source)

        assert result is False
        captured = capsys.readouterr()
        assert "Error writing profile config" in captured.err

    def test_overwrite_rejects_symlink_destination(self, tmp_path, capsys):
        """Existing config.json symlinks are rejected instead of being replaced."""
        source = tmp_path / "credentials.json"
        source.write_text(json.dumps(VALID_CREDENTIALS))

        profile_dir = tmp_path / "orgs" / "linked-profile"
        profile_dir.mkdir(parents=True)
        target_file = tmp_path / "real-config.json"
        target_file.write_text(json.dumps({"org_id": "ORIGINAL@AdobeOrg"}))
        (profile_dir / "config.json").symlink_to(target_file)

        with patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir):
            result = import_profile_non_interactive("linked-profile", source, overwrite=True)

        assert result is False
        captured = capsys.readouterr()
        assert "symlink" in captured.err.lower()
        assert json.loads(target_file.read_text())["org_id"] == "ORIGINAL@AdobeOrg"
        assert (profile_dir / "config.json").is_symlink()

    def test_validation_failure(self, tmp_path, capsys):
        """Credentials that fail strict validation should be rejected."""
        source = tmp_path / "credentials.json"
        source.write_text(
            json.dumps(
                {
                    "org_id": "not_adobe_format",
                    "client_id": "x",
                    "secret": "y",
                    "scopes": "openid",
                },
            ),
        )

        profile_dir = tmp_path / "orgs" / "bad-creds"

        with patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir):
            result = import_profile_non_interactive("bad-creds", source)

        assert result is False
        captured = capsys.readouterr()
        assert "failed validation" in captured.err

    def test_validation_failure_details_stay_on_stderr(self, tmp_path, capsys):
        """Validation issue detail lines should stay on stderr with the error header."""
        source = tmp_path / "credentials.json"
        source.write_text(json.dumps(VALID_CREDENTIALS))

        profile_dir = tmp_path / "orgs" / "bad-creds"
        expected_issues = ["org_id: invalid format", "client_id: too short"]

        with (
            patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir),
            patch("cja_auto_sdr.generator.validate_credentials", return_value=(False, expected_issues)),
        ):
            result = import_profile_non_interactive("bad-creds", source)

        assert result is False
        captured = capsys.readouterr()
        assert "Imported credentials failed validation" in captured.err
        assert "org_id: invalid format" in captured.err
        assert "client_id: too short" in captured.err
        assert "org_id: invalid format" not in captured.out
        assert "client_id: too short" not in captured.out

    def test_success_message_includes_source_and_location(self, tmp_path, capsys):
        """Successful import prints source path and profile location."""
        source = tmp_path / "credentials.json"
        source.write_text(json.dumps(VALID_CREDENTIALS))

        profile_dir = tmp_path / "orgs" / "new-import"

        with patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir):
            result = import_profile_non_interactive("new-import", source)

        assert result is True
        captured = capsys.readouterr()
        assert "imported successfully" in captured.out
        assert "Source:" in captured.out
        assert "Location:" in captured.out
        assert "profile-test" in captured.out


# ===========================================================================
# test_profile — connectivity test
# ===========================================================================


class TestTestProfile:
    """Tests for the profile connectivity test function."""

    def test_profile_not_found(self, tmp_path, capsys):
        """Non-existent profile should fail with ERROR message."""
        nonexistent = tmp_path / "orgs" / "nonexistent"

        with patch("cja_auto_sdr.generator.get_profile_path", return_value=nonexistent):
            result = run_test_profile("nonexistent")

        assert result is False
        captured = capsys.readouterr()
        assert "ERROR" in captured.err

    def test_profile_config_error(self, tmp_path, capsys):
        """Profile with config error should fail with ERROR message."""
        profile_dir = tmp_path / "orgs" / "bad-config"
        profile_dir.mkdir(parents=True)
        # Empty directory = no config files => ProfileConfigError

        with patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir):
            result = run_test_profile("bad-config")

        assert result is False
        captured = capsys.readouterr()
        assert "ERROR" in captured.err

    def test_successful_api_connection(self, tmp_path, capsys):
        """Successful API test should return True with SUCCESS."""
        profile_dir = tmp_path / "orgs" / "good"
        _write_config_json(profile_dir)

        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = [
            {"id": "dv1", "name": "DataView 1"},
            {"id": "dv2", "name": "DataView 2"},
        ]

        with (
            patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir),
            patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
            patch("cja_auto_sdr.generator.ConfigValidator") as mock_validator,
            patch("cja_auto_sdr.generator._config_from_env") as mock_config_from_env,
        ):
            mock_cjapy.CJA.return_value = mock_cja_instance
            mock_validator.validate_all.return_value = []
            result = run_test_profile("good")

        assert result is True
        mock_config_from_env.assert_called_once()
        captured = capsys.readouterr()
        assert "TESTING PROFILE: good" in captured.out
        assert "Profile found and loaded" in captured.out
        assert "Credential validation: OK" in captured.out
        assert "API connection: SUCCESS" in captured.out
        assert "Data views accessible: 2" in captured.out
        assert "Profile test: PASSED" in captured.out

    def test_api_connection_with_none_dataviews(self, tmp_path, capsys):
        """API returning None for data views should still pass."""
        profile_dir = tmp_path / "orgs" / "none-dv"
        _write_config_json(profile_dir)

        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = None

        with (
            patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir),
            patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
            patch("cja_auto_sdr.generator.ConfigValidator") as mock_validator,
            patch("cja_auto_sdr.generator._config_from_env") as mock_config_from_env,
        ):
            mock_cjapy.CJA.return_value = mock_cja_instance
            mock_validator.validate_all.return_value = []
            result = run_test_profile("none-dv")

        assert result is True
        mock_config_from_env.assert_called_once()
        captured = capsys.readouterr()
        assert "no data views found" in captured.out
        assert "Profile test: PASSED" in captured.out

    def test_api_connection_failure(self, tmp_path, capsys):
        """API connection failure should return False with helpful message."""
        profile_dir = tmp_path / "orgs" / "api-fail"
        _write_config_json(profile_dir)

        with (
            patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir),
            patch("cja_auto_sdr.generator.cjapy"),
            patch("cja_auto_sdr.generator.ConfigValidator") as mock_validator,
            patch("cja_auto_sdr.generator._config_from_env", side_effect=OSError("Connection refused")),
        ):
            mock_validator.validate_all.return_value = []
            result = run_test_profile("api-fail")

        assert result is False
        captured = capsys.readouterr()
        assert "API connection: FAILED" in captured.err
        assert "Connection refused" in captured.err
        assert "Profile test: FAILED" in captured.err
        assert "Common issues:" in captured.out

    def test_validation_warnings_displayed(self, tmp_path, capsys):
        """Validation warnings should be displayed but not block the test."""
        profile_dir = tmp_path / "orgs" / "warnings"
        _write_config_json(profile_dir)

        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = []

        with (
            patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir),
            patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
            patch("cja_auto_sdr.generator.ConfigValidator") as mock_validator,
            patch("cja_auto_sdr.generator._config_from_env") as mock_config_from_env,
        ):
            mock_cjapy.CJA.return_value = mock_cja_instance
            mock_validator.validate_all.return_value = ["org_id format looks unusual"]
            result = run_test_profile("warnings")

        assert result is True
        mock_config_from_env.assert_called_once()
        captured = capsys.readouterr()
        assert "Credential validation: WARNINGS" in captured.out
        assert "org_id format looks unusual" in captured.out

    def test_cja_constructor_failure(self, tmp_path, capsys):
        """CJA() constructor exception should be caught."""
        profile_dir = tmp_path / "orgs" / "cja-fail"
        _write_config_json(profile_dir)

        with (
            patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir),
            patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
            patch("cja_auto_sdr.generator.ConfigValidator") as mock_validator,
            patch("cja_auto_sdr.generator._config_from_env") as mock_config_from_env,
        ):
            mock_cjapy.CJA.side_effect = OSError("Auth failed: invalid credentials")
            mock_validator.validate_all.return_value = []
            result = run_test_profile("cja-fail")

        assert result is False
        mock_config_from_env.assert_called_once()
        captured = capsys.readouterr()
        assert "FAILED" in captured.err
        assert "invalid credentials" in captured.err

    def test_profile_test_uses_in_memory_config_path(self, tmp_path):
        """Profile test should configure cjapy in memory instead of creating temp files."""
        profile_dir = tmp_path / "orgs" / "cleanup"
        _write_config_json(profile_dir)

        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = [{"id": "dv1"}]

        with (
            patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir),
            patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
            patch("cja_auto_sdr.generator.ConfigValidator") as mock_validator,
            patch("cja_auto_sdr.generator._config_from_env") as mock_config_from_env,
        ):
            mock_cjapy.CJA.return_value = mock_cja_instance
            mock_validator.validate_all.return_value = []
            run_test_profile("cleanup")

        mock_config_from_env.assert_called_once()


# ===========================================================================
# show_profile — extended paths
# ===========================================================================


class TestShowProfileExtended:
    """Extended show_profile tests covering error branches and display details."""

    def test_show_profile_config_error(self, tmp_path, capsys):
        """ProfileConfigError path should print error and return False."""
        profile_dir = tmp_path / "orgs" / "bad-config"
        profile_dir.mkdir(parents=True)
        # Empty dir triggers ProfileConfigError

        with patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir):
            result = show_profile("bad-config")

        assert result is False
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_show_profile_not_found(self, tmp_path, capsys):
        """ProfileNotFoundError path should print error and return False."""
        nonexistent = tmp_path / "orgs" / "missing"

        with patch("cja_auto_sdr.generator.get_profile_path", return_value=nonexistent):
            result = show_profile("missing")

        assert result is False
        captured = capsys.readouterr()
        assert "Error" in captured.err

    def test_show_profile_with_both_sources(self, tmp_path, capsys):
        """Profile with config.json and .env should list both sources."""
        profile_dir = tmp_path / "orgs" / "both-sources"
        _write_config_json(profile_dir)
        _write_dotenv(profile_dir, "ORG_ID=Test@AdobeOrg")

        with patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir):
            result = show_profile("both-sources")

        assert result is True
        captured = capsys.readouterr()
        assert "config.json" in captured.out
        assert ".env" in captured.out
        assert "Sources:" in captured.out

    def test_show_profile_masks_sensitive_fields(self, tmp_path, capsys):
        """Sensitive fields (client_id, secret) should be masked in output."""
        profile_dir = tmp_path / "orgs" / "masked"
        _write_config_json(
            profile_dir,
            {
                "org_id": "ShowOrg@AdobeOrg",
                "client_id": "1234567890abcdef1234567890abcdef",
                "secret": "secret_value_that_is_long_enough",
                "scopes": "openid,AdobeID",
            },
        )

        with patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir):
            result = show_profile("masked")

        assert result is True
        captured = capsys.readouterr()
        # org_id is NOT sensitive, should appear in full
        assert "ShowOrg@AdobeOrg" in captured.out
        # scopes is NOT sensitive, should appear in full
        assert "openid,AdobeID" in captured.out
        # The full secret should NOT appear
        assert "secret_value_that_is_long_enough" not in captured.out
        # The full client_id should NOT appear
        assert "1234567890abcdef1234567890abcdef" not in captured.out
        # But partial display should appear (first 4 chars)
        assert "1234" in captured.out

    def test_show_profile_displays_banner(self, tmp_path, capsys):
        """show_profile should display a banner with profile name."""
        profile_dir = tmp_path / "orgs" / "banner-test"
        _write_config_json(profile_dir)

        with patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir):
            result = show_profile("banner-test")

        assert result is True
        captured = capsys.readouterr()
        assert "PROFILE: banner-test" in captured.out
        assert "Location:" in captured.out
        assert "Credentials:" in captured.out

    def test_show_profile_with_sandbox(self, tmp_path, capsys):
        """Profile with sandbox field should display it."""
        profile_dir = tmp_path / "orgs" / "sandbox-test"
        creds = dict(VALID_CREDENTIALS)
        creds["sandbox"] = "prod"
        _write_config_json(profile_dir, creds)

        with patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir):
            result = show_profile("sandbox-test")

        assert result is True
        captured = capsys.readouterr()
        assert "sandbox" in captured.out
        assert "prod" in captured.out

    def test_show_profile_env_only(self, tmp_path, capsys):
        """Profile with only .env should list only .env as source."""
        profile_dir = tmp_path / "orgs" / "env-only"
        profile_dir.mkdir(parents=True)
        _write_dotenv(
            profile_dir,
            "ORG_ID=Env@AdobeOrg\nCLIENT_ID=env_client_1234567890ab\nSECRET=env_secret_1234567890ab\nSCOPES=openid",
        )

        with patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir):
            result = show_profile("env-only")

        assert result is True
        captured = capsys.readouterr()
        assert ".env" in captured.out
        # Should NOT mention config.json in sources
        # (It may mention it elsewhere as "Sources: .env")
        assert "Env@AdobeOrg" in captured.out
