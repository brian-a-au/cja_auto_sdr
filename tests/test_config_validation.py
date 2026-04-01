"""Tests for cja_auto_sdr.core.config_validation module.

Targets uncovered lines: 30, 38, 47, 67, 83, 107, 156, 184, 186, 202,
257-258, 273-274, 281, 288, 300, 308, 310, 325, 340-344, 348-350, 355-361.
"""

import json
import os
import sys
from unittest.mock import MagicMock, patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from cja_auto_sdr.core.config_validation import (
    ConfigValidator,
    validate_config_file,
    validate_credentials,
)

# ==================== ConfigValidator.validate_org_id ====================


class TestValidateOrgId:
    """Tests for ConfigValidator.validate_org_id targeting lines 30, 38, 47."""

    def test_empty_string_returns_error(self):
        """Line 30: empty org_id returns error."""
        valid, error = ConfigValidator.validate_org_id("")
        assert valid is False
        assert error == "ORG_ID cannot be empty"

    def test_none_returns_error(self):
        """Line 30: None org_id returns error."""
        valid, error = ConfigValidator.validate_org_id(None)
        assert valid is False
        assert error == "ORG_ID cannot be empty"

    def test_whitespace_only_returns_error(self):
        """Line 30: whitespace-only org_id returns error."""
        valid, error = ConfigValidator.validate_org_id("   ")
        assert valid is False
        assert error == "ORG_ID cannot be empty"

    def test_wrong_at_suffix(self):
        """Line 38: org_id with @ but wrong suffix gives specific error."""
        valid, error = ConfigValidator.validate_org_id("myorg@WrongSuffix")
        assert valid is False
        assert "incorrect suffix" in error
        assert "WrongSuffix" in error

    def test_just_adobe_org_suffix(self):
        """Line 47: org_id that is just '@AdobeOrg' with no prefix."""
        valid, error = ConfigValidator.validate_org_id("@AdobeOrg")
        assert valid is False
        assert "cannot be just '@AdobeOrg'" in error

    def test_missing_adobe_org_suffix_no_at(self):
        """org_id with no @ sign at all gives missing suffix error."""
        valid, error = ConfigValidator.validate_org_id("myorg")
        assert valid is False
        assert "missing '@AdobeOrg' suffix" in error
        assert "myorg@AdobeOrg" in error

    def test_valid_org_id(self):
        """Valid org_id passes."""
        valid, error = ConfigValidator.validate_org_id("ABC123@AdobeOrg")
        assert valid is True
        assert error is None

    def test_valid_org_id_with_whitespace_stripped(self):
        """Whitespace around a valid org_id is stripped."""
        valid, error = ConfigValidator.validate_org_id("  ABC123@AdobeOrg  ")
        assert valid is True
        assert error is None


# ==================== ConfigValidator.validate_scopes ====================


class TestValidateScopes:
    """Tests for ConfigValidator.validate_scopes targeting line 67."""

    def test_empty_scopes_returns_error(self):
        """Line 67: empty scopes returns error."""
        valid, error, missing = ConfigValidator.validate_scopes("")
        assert valid is False
        assert "cannot be empty" in error
        assert missing == []

    def test_none_scopes_returns_error(self):
        """Line 67: None scopes returns error."""
        valid, error, _missing = ConfigValidator.validate_scopes(None)
        assert valid is False
        assert "cannot be empty" in error

    def test_whitespace_only_scopes_returns_error(self):
        """Line 67: whitespace-only scopes returns error."""
        valid, error, _missing = ConfigValidator.validate_scopes("   ")
        assert valid is False
        assert "cannot be empty" in error

    def test_valid_scopes(self):
        """Valid scopes string passes."""
        valid, error, missing = ConfigValidator.validate_scopes("openid, AdobeID")
        assert valid is True
        assert error is None
        assert missing == []


# ==================== ConfigValidator.validate_client_id ====================


class TestValidateClientId:
    """Tests for ConfigValidator.validate_client_id targeting line 83."""

    def test_empty_client_id_returns_error(self):
        """Line 83: empty client_id returns error."""
        valid, error = ConfigValidator.validate_client_id("")
        assert valid is False
        assert error == "CLIENT_ID cannot be empty"

    def test_none_client_id_returns_error(self):
        """Line 83: None client_id returns error."""
        valid, error = ConfigValidator.validate_client_id(None)
        assert valid is False
        assert error == "CLIENT_ID cannot be empty"

    def test_whitespace_only_client_id_returns_error(self):
        """Line 83: whitespace-only client_id returns error."""
        valid, error = ConfigValidator.validate_client_id("   ")
        assert valid is False
        assert error == "CLIENT_ID cannot be empty"

    def test_short_client_id_returns_error(self):
        """Short client_id (< 16 chars) gives a warning."""
        valid, error = ConfigValidator.validate_client_id("short123")
        assert valid is False
        assert "appears too short" in error

    def test_valid_client_id(self):
        """Valid long client_id passes."""
        valid, error = ConfigValidator.validate_client_id("a" * 32)
        assert valid is True
        assert error is None


# ==================== ConfigValidator.validate_secret ====================


class TestValidateSecret:
    """Tests for ConfigValidator.validate_secret targeting line 107."""

    def test_empty_secret_returns_error(self):
        """Line 107: empty secret returns error."""
        valid, error = ConfigValidator.validate_secret("")
        assert valid is False
        assert error == "SECRET cannot be empty"

    def test_none_secret_returns_error(self):
        """Line 107: None secret returns error."""
        valid, error = ConfigValidator.validate_secret(None)
        assert valid is False
        assert error == "SECRET cannot be empty"

    def test_whitespace_only_secret_returns_error(self):
        """Line 107: whitespace-only secret returns error."""
        valid, error = ConfigValidator.validate_secret("   ")
        assert valid is False
        assert error == "SECRET cannot be empty"

    def test_short_secret_returns_error(self):
        """Short secret (< 16 chars) gives a warning."""
        valid, error = ConfigValidator.validate_secret("tiny")
        assert valid is False
        assert "appears too short" in error

    def test_valid_secret(self):
        """Valid long secret passes."""
        valid, error = ConfigValidator.validate_secret("s" * 32)
        assert valid is True
        assert error is None


# ==================== ConfigValidator.validate_all ====================


class TestValidateAll:
    """Tests for ConfigValidator.validate_all targeting line 156."""

    def test_invalid_scopes_logs_warning_but_not_in_issues(self):
        """Line 156: invalid scopes trigger a warning log but don't appear in issues."""
        logger = MagicMock()
        credentials = {
            "org_id": "ABC123@AdobeOrg",
            "client_id": "a" * 32,
            "secret": "s" * 32,
            "scopes": "",  # empty scopes
        }
        issues = ConfigValidator.validate_all(credentials, logger)
        assert issues == []  # scopes warning not added to issues
        logger.warning.assert_called()  # but a warning was logged
        warning_msg = logger.warning.call_args[0][0]
        assert "warning" in warning_msg.lower() or "scopes" in warning_msg.lower()

    def test_all_invalid_fields_returns_all_issues(self):
        """Multiple invalid fields all appear in issues."""
        logger = MagicMock()
        credentials = {
            "org_id": "",
            "client_id": "",
            "secret": "",
            "scopes": "",
        }
        issues = ConfigValidator.validate_all(credentials, logger)
        assert len(issues) == 3  # org_id, client_id, secret (not scopes)

    def test_no_credentials_returns_no_issues(self):
        """Empty credentials dict produces no issues (no fields to validate)."""
        logger = MagicMock()
        issues = ConfigValidator.validate_all({}, logger)
        assert issues == []

    def test_valid_credentials_returns_empty_issues(self):
        """All valid credentials produce empty issues."""
        logger = MagicMock()
        credentials = {
            "org_id": "ABC123@AdobeOrg",
            "client_id": "a" * 32,
            "secret": "s" * 32,
            "scopes": "openid",
        }
        issues = ConfigValidator.validate_all(credentials, logger)
        assert issues == []


# ==================== validate_credentials ====================


class TestValidateCredentials:
    """Tests for validate_credentials targeting lines 184, 186, 202."""

    def test_missing_required_field_adds_issue(self):
        """Line 184: missing required field adds 'Missing required field' issue."""
        logger = MagicMock()
        credentials = {
            "org_id": "ABC123@AdobeOrg",
            "client_id": "a" * 32,
            # missing 'secret'
        }
        is_valid, issues = validate_credentials(credentials, logger, strict=False, source="test")
        assert is_valid is False
        assert any("Missing required field: 'secret'" in i for i in issues)

    def test_empty_required_field_adds_issue(self):
        """Line 186: empty required field adds 'Empty value' issue."""
        logger = MagicMock()
        credentials = {
            "org_id": "ABC123@AdobeOrg",
            "client_id": "a" * 32,
            "secret": "   ",  # whitespace only
        }
        is_valid, issues = validate_credentials(credentials, logger, strict=False, source="test")
        assert is_valid is False
        assert any("Empty value for required field: 'secret'" in i for i in issues)

    def test_unknown_fields_logged_at_debug(self):
        """Line 202: unknown fields are logged at debug level."""
        logger = MagicMock()
        credentials = {
            "org_id": "ABC123@AdobeOrg",
            "client_id": "a" * 32,
            "secret": "s" * 32,
            "scopes": "openid",
            "unknown_field": "value",
            "another_unknown": "value2",
        }
        _is_valid, _issues = validate_credentials(credentials, logger, strict=False, source="test")
        logger.debug.assert_called()
        debug_call_args = logger.debug.call_args[0]
        debug_msg = debug_call_args[0] % debug_call_args[1:]
        assert "unknown_field" in debug_msg or "another_unknown" in debug_msg

    def test_strict_mode_fails_on_validation_issues(self):
        """Strict mode: any issue makes is_valid False."""
        logger = MagicMock()
        credentials = {
            "org_id": "bad_org",  # missing @AdobeOrg
            "client_id": "a" * 32,
            "secret": "s" * 32,
            "scopes": "openid",
        }
        is_valid, _issues = validate_credentials(credentials, logger, strict=True, source="test")
        assert is_valid is False

    def test_non_strict_mode_passes_with_format_issues_only(self):
        """Non-strict mode: format issues pass if no missing/empty fields."""
        logger = MagicMock()
        credentials = {
            "org_id": "bad_org",  # missing @AdobeOrg suffix
            "client_id": "a" * 32,
            "secret": "s" * 32,
            "scopes": "openid",
        }
        is_valid, issues = validate_credentials(credentials, logger, strict=False, source="test")
        # There are issues but is_valid is True because no missing/empty required fields
        assert is_valid is True
        assert len(issues) > 0

    def test_missing_scopes_logs_warning(self):
        """Missing scopes triggers a warning log."""
        logger = MagicMock()
        credentials = {
            "org_id": "ABC123@AdobeOrg",
            "client_id": "a" * 32,
            "secret": "s" * 32,
            # no scopes
        }
        validate_credentials(credentials, logger, strict=False, source="env")
        warning_calls = [str(c) for c in logger.warning.call_args_list]
        assert any("scopes" in w.lower() for w in warning_calls)


# ==================== validate_config_file ====================


class TestValidateConfigFile:
    """Tests for validate_config_file targeting lines 257-258, 273-274, 281, 288,
    300, 308, 310, 325, 340-344, 348-350, 355-361."""

    def test_file_not_found(self, tmp_path):
        """Lines 248-253: non-existent file returns False."""
        logger = MagicMock()
        result = validate_config_file(tmp_path / "nonexistent.json", logger)
        assert result is False
        logger.error.assert_called()

    def test_not_a_file(self, tmp_path):
        """Lines 257-258: path exists but is a directory returns False."""
        logger = MagicMock()
        dir_path = tmp_path / "adir"
        dir_path.mkdir()
        result = validate_config_file(dir_path, logger)
        assert result is False
        logger.error.assert_called()

    def test_invalid_json(self, tmp_path):
        """Lines 264-269: malformed JSON returns False."""
        logger = MagicMock()
        config_file = tmp_path / "bad.json"
        config_file.write_text("{not valid json")
        result = validate_config_file(config_file, logger)
        assert result is False

    def test_json_is_not_a_dict(self, tmp_path):
        """Lines 273-274: JSON that is a list (not dict) returns False."""
        logger = MagicMock()
        config_file = tmp_path / "list.json"
        config_file.write_text(json.dumps(["not", "a", "dict"]))
        result = validate_config_file(config_file, logger)
        assert result is False
        error_calls = [str(c) for c in logger.error.call_args_list]
        assert any("JSON object" in e for e in error_calls)

    def test_wrong_type_for_required_field(self, tmp_path):
        """Line 281: required field has wrong type (e.g., int instead of str)."""
        logger = MagicMock()
        config_data = {
            "org_id": 12345,  # should be str
            "client_id": "a" * 32,
            "secret": "s" * 32,
            "scopes": "openid",
        }
        config_file = tmp_path / "wrongtype.json"
        config_file.write_text(json.dumps(config_data))
        result = validate_config_file(config_file, logger)
        assert result is False

    def test_empty_required_field(self, tmp_path):
        """Line 288: required field with empty string."""
        logger = MagicMock()
        config_data = {
            "org_id": "",
            "client_id": "a" * 32,
            "secret": "s" * 32,
            "scopes": "openid",
        }
        config_file = tmp_path / "empty.json"
        config_file.write_text(json.dumps(config_data))
        result = validate_config_file(config_file, logger)
        assert result is False

    def test_whitespace_only_required_field(self, tmp_path):
        """Line 288: required field with whitespace-only string."""
        logger = MagicMock()
        config_data = {
            "org_id": "   ",
            "client_id": "a" * 32,
            "secret": "s" * 32,
            "scopes": "openid",
        }
        config_file = tmp_path / "whitespace.json"
        config_file.write_text(json.dumps(config_data))
        result = validate_config_file(config_file, logger)
        assert result is False

    def test_wrong_type_for_optional_field(self, tmp_path):
        """Line 300: optional field with wrong type triggers warning."""
        logger = MagicMock()
        config_data = {
            "org_id": "ABC123@AdobeOrg",
            "client_id": "a" * 32,
            "secret": "s" * 32,
            "scopes": "openid",
            "sandbox": 12345,  # should be str -- use sandbox to avoid scopes-specific logic
        }
        config_file = tmp_path / "optbad.json"
        config_file.write_text(json.dumps(config_data))
        result = validate_config_file(config_file, logger)
        # Should still pass (warnings only for optional fields) if required fields are valid
        assert result is True
        warning_calls = [str(c) for c in logger.warning.call_args_list]
        assert any("optional field" in w.lower() or "Invalid type" in w for w in warning_calls)

    def test_scopes_with_wrong_type_causes_exception(self, tmp_path):
        """scopes as int triggers AttributeError at line 291 (.strip() on int), caught at line 359."""
        logger = MagicMock()
        config_data = {
            "org_id": "ABC123@AdobeOrg",
            "client_id": "a" * 32,
            "secret": "s" * 32,
            "scopes": 12345,  # int has no .strip() -> AttributeError
        }
        config_file = tmp_path / "scopeint.json"
        config_file.write_text(json.dumps(config_data))
        result = validate_config_file(config_file, logger)
        assert result is False
        error_calls = [str(c) for c in logger.error.call_args_list]
        assert any("Unexpected error" in e or "AttributeError" in e for e in error_calls)

    def test_deprecated_jwt_fields_trigger_warning(self, tmp_path):
        """Lines 308, 310: deprecated JWT fields trigger deprecation warning."""
        logger = MagicMock()
        config_data = {
            "org_id": "ABC123@AdobeOrg",
            "client_id": "a" * 32,
            "secret": "s" * 32,
            "scopes": "openid",
            "tech_acct": "some_tech_account",
            "private_key": "/path/to/key",
        }
        config_file = tmp_path / "jwt.json"
        config_file.write_text(json.dumps(config_data))
        result = validate_config_file(config_file, logger)
        assert result is True  # warnings don't fail
        warning_calls = [str(c) for c in logger.warning.call_args_list]
        assert any("DEPRECATED" in w or "JWT" in w for w in warning_calls)

    def test_unknown_fields_trigger_warning(self, tmp_path):
        """Line 325: unknown fields (potential typos) produce a warning."""
        logger = MagicMock()
        config_data = {
            "org_id": "ABC123@AdobeOrg",
            "client_id": "a" * 32,
            "secret": "s" * 32,
            "scopes": "openid",
            "typo_field": "oops",
        }
        config_file = tmp_path / "typo.json"
        config_file.write_text(json.dumps(config_data))
        result = validate_config_file(config_file, logger)
        assert result is True
        warning_calls = [str(c) for c in logger.warning.call_args_list]
        assert any("typo_field" in w for w in warning_calls)

    def test_missing_required_field_shows_enhanced_error(self, tmp_path):
        """Lines 340-344: missing required field triggers enhanced error message."""
        logger = MagicMock()
        config_data = {
            "org_id": "ABC123@AdobeOrg",
            # missing client_id and secret
            "scopes": "openid",
        }
        config_file = tmp_path / "missing.json"
        config_file.write_text(json.dumps(config_data))
        result = validate_config_file(config_file, logger)
        assert result is False
        error_calls = [str(c) for c in logger.error.call_args_list]
        assert any("Missing required field" in e for e in error_calls)

    def test_empty_value_error_shows_invalid_format_message(self, tmp_path):
        """Lines 340-344: empty values (without missing fields) show invalid_format error."""
        logger = MagicMock()
        config_data = {
            "org_id": "",
            "client_id": "",
            "secret": "",
            "scopes": "openid",
        }
        config_file = tmp_path / "allempty.json"
        config_file.write_text(json.dumps(config_data))
        result = validate_config_file(config_file, logger)
        assert result is False
        error_calls = [str(c) for c in logger.error.call_args_list]
        # Should have "Empty value" errors and enhanced message
        assert any("Empty value" in e for e in error_calls)

    def test_validation_warnings_are_logged(self, tmp_path):
        """Lines 348-350: warnings are logged when present."""
        logger = MagicMock()
        config_data = {
            "org_id": "ABC123@AdobeOrg",
            "client_id": "a" * 32,
            "secret": "s" * 32,
            # no scopes -> triggers scopes warning
            "weird_unknown_field": "value",  # -> triggers unknown field warning
        }
        config_file = tmp_path / "warnings.json"
        config_file.write_text(json.dumps(config_data))
        result = validate_config_file(config_file, logger)
        assert result is True
        warning_calls = [str(c) for c in logger.warning.call_args_list]
        assert any("warning" in w.lower() for w in warning_calls)

    def test_permission_error(self, tmp_path):
        """Lines 355-358: PermissionError is caught and returns False."""
        logger = MagicMock()
        config_file = tmp_path / "noperm.json"
        config_file.write_text(json.dumps({"org_id": "test@AdobeOrg"}))

        with patch("builtins.open", side_effect=PermissionError("Permission denied")):
            result = validate_config_file(config_file, logger)
        assert result is False
        error_calls = [str(c) for c in logger.error.call_args_list]
        assert any("Permission denied" in e for e in error_calls)

    def test_unexpected_exception(self, tmp_path):
        """Lines 359-361: unexpected exceptions are caught and return False."""
        logger = MagicMock()
        config_file = tmp_path / "crash.json"
        config_file.write_text(json.dumps({"org_id": "test@AdobeOrg"}))

        with patch("builtins.open", side_effect=OSError("Something broke")):
            result = validate_config_file(config_file, logger)
        assert result is False
        error_calls = [str(c) for c in logger.error.call_args_list]
        assert any("Unexpected error" in e or "OSError" in e for e in error_calls)

    def test_valid_config_file_passes(self, tmp_path):
        """Valid config file passes all validation."""
        logger = MagicMock()
        config_data = {
            "org_id": "ABC123@AdobeOrg",
            "client_id": "a" * 32,
            "secret": "s" * 32,
            "scopes": "openid",
        }
        config_file = tmp_path / "good.json"
        config_file.write_text(json.dumps(config_data))
        result = validate_config_file(config_file, logger)
        assert result is True
        logger.info.assert_called()

    def test_missing_scopes_in_config_file_warns(self, tmp_path):
        """Missing scopes in config file triggers a warning."""
        logger = MagicMock()
        config_data = {
            "org_id": "ABC123@AdobeOrg",
            "client_id": "a" * 32,
            "secret": "s" * 32,
            # no scopes
        }
        config_file = tmp_path / "noscopes.json"
        config_file.write_text(json.dumps(config_data))
        result = validate_config_file(config_file, logger)
        assert result is True
        warning_calls = [str(c) for c in logger.warning.call_args_list]
        assert any("scopes" in w.lower() for w in warning_calls)

    def test_empty_scopes_string_in_config_file_warns(self, tmp_path):
        """Empty scopes string in config file triggers a warning."""
        logger = MagicMock()
        config_data = {
            "org_id": "ABC123@AdobeOrg",
            "client_id": "a" * 32,
            "secret": "s" * 32,
            "scopes": "   ",  # whitespace only
        }
        config_file = tmp_path / "emptyscopes.json"
        config_file.write_text(json.dumps(config_data))
        result = validate_config_file(config_file, logger)
        assert result is True
        warning_calls = [str(c) for c in logger.warning.call_args_list]
        assert any("scopes" in w.lower() for w in warning_calls)

    def test_only_empty_value_errors_no_missing_field(self, tmp_path):
        """When all required fields present but empty, triggers 'invalid_format' enhanced error."""
        logger = MagicMock()
        # All required fields present but with empty values
        config_data = {
            "org_id": "ABC123@AdobeOrg",
            "client_id": "a" * 32,
            "secret": "   ",  # whitespace-only
            "scopes": "openid",
        }
        config_file = tmp_path / "empty_vals.json"
        config_file.write_text(json.dumps(config_data))
        result = validate_config_file(config_file, logger)
        assert result is False
        error_calls = [str(c) for c in logger.error.call_args_list]
        assert any("Empty value" in e for e in error_calls)

    def test_path_as_string(self, tmp_path):
        """validate_config_file works when passed a string path."""
        logger = MagicMock()
        config_data = {
            "org_id": "ABC123@AdobeOrg",
            "client_id": "a" * 32,
            "secret": "s" * 32,
            "scopes": "openid",
        }
        config_file = tmp_path / "strpath.json"
        config_file.write_text(json.dumps(config_data))
        result = validate_config_file(str(config_file), logger)
        assert result is True

    def test_multiple_deprecated_jwt_fields(self, tmp_path):
        """Multiple deprecated JWT fields are all listed in warning."""
        logger = MagicMock()
        config_data = {
            "org_id": "ABC123@AdobeOrg",
            "client_id": "a" * 32,
            "secret": "s" * 32,
            "scopes": "openid",
            "tech_acct": "tech_account_value",
            "private_key": "/path/to/key.pem",
            "pathToKey": "/another/path",
        }
        config_file = tmp_path / "multijwt.json"
        config_file.write_text(json.dumps(config_data))
        result = validate_config_file(config_file, logger)
        assert result is True
        warning_calls = [str(c) for c in logger.warning.call_args_list]
        jwt_warnings = [w for w in warning_calls if "DEPRECATED" in w or "JWT" in w]
        assert len(jwt_warnings) > 0
        # All three deprecated fields should be mentioned
        combined = " ".join(jwt_warnings)
        assert "tech_acct" in combined
        assert "private_key" in combined
        assert "pathToKey" in combined

    def test_sandbox_optional_field_with_wrong_type(self, tmp_path):
        """sandbox field with wrong type triggers optional field warning."""
        logger = MagicMock()
        config_data = {
            "org_id": "ABC123@AdobeOrg",
            "client_id": "a" * 32,
            "secret": "s" * 32,
            "scopes": "openid",
            "sandbox": 42,  # should be str
        }
        config_file = tmp_path / "badsandbox.json"
        config_file.write_text(json.dumps(config_data))
        result = validate_config_file(config_file, logger)
        assert result is True
        warning_calls = [str(c) for c in logger.warning.call_args_list]
        assert any("sandbox" in w.lower() for w in warning_calls)
