"""Tests for config status, validation, stats, data view resolution, and misc helpers.

Covers uncovered lines in generator.py:
- show_config_status (lines 9894-10027)
- validate_config_only (lines 10035-10220)
- show_stats (lines 10226-10410)
- resolve_data_view_names (lines 8208-8361)
- prompt_for_selection (lines 8165-8205)
- DataViewCache (lines 8046-8088)
- _format_diff_value (lines 3262-3263)
- _safe_env_number (line 6707)
- levenshtein_distance (lines 7947-7977)
- is_data_view_id (line 7934)
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pandas as pd
import pytest

from cja_auto_sdr.core.exceptions import APIError, ConfigurationError

logger = logging.getLogger("test_config_and_resolution")


# ---------------------------------------------------------------------------
# 1. show_config_status — lines 9894-10027
# ---------------------------------------------------------------------------


class TestShowConfigStatusProfile:
    """Lines 9894-9907: profile credential loading paths."""

    @patch("cja_auto_sdr.generator.load_profile_credentials")
    def test_profile_found_complete(self, mock_load, capsys: pytest.CaptureFixture) -> None:
        from cja_auto_sdr.generator import show_config_status

        mock_load.return_value = {"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}
        result = show_config_status(profile="myprofile")
        assert result is True
        output = capsys.readouterr().out
        assert "Profile: myprofile" in output

    @patch("cja_auto_sdr.generator.load_profile_credentials")
    def test_profile_not_found_error(self, mock_load) -> None:
        from cja_auto_sdr.generator import ProfileNotFoundError, show_config_status

        mock_load.side_effect = ProfileNotFoundError("not found", profile_name="bad")
        result = show_config_status(profile="bad")
        assert result is False

    @patch("cja_auto_sdr.generator.load_profile_credentials")
    def test_profile_not_found_json(self, mock_load, capsys: pytest.CaptureFixture) -> None:
        from cja_auto_sdr.generator import ProfileNotFoundError, show_config_status

        mock_load.side_effect = ProfileNotFoundError("not found", profile_name="bad")
        result = show_config_status(profile="bad", output_json=True)
        assert result is False
        data = json.loads(capsys.readouterr().out)
        assert data["valid"] is False


class TestShowConfigStatusEnvVars:
    """Lines 9910-9915: environment variable credential detection."""

    @patch("cja_auto_sdr.generator.load_credentials_from_env")
    @patch("cja_auto_sdr.generator.validate_env_credentials", return_value=True)
    def test_env_vars_detected(self, _mock_validate, mock_load_env, capsys: pytest.CaptureFixture) -> None:
        from cja_auto_sdr.generator import show_config_status

        mock_load_env.return_value = {"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}
        result = show_config_status()
        assert result is True
        output = capsys.readouterr().out
        assert "Environment variables" in output


class TestShowConfigStatusFile:
    """Lines 9918-9954: config file loading and error paths."""

    def test_config_file_valid(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        from cja_auto_sdr.generator import show_config_status

        config = tmp_path / "config.json"
        config.write_text(
            json.dumps({"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}),
        )
        result = show_config_status(config_file=str(config))
        assert result is True

    def test_config_file_invalid_json(self, tmp_path: Path) -> None:
        from cja_auto_sdr.generator import show_config_status

        config = tmp_path / "config.json"
        config.write_text("{bad json")
        result = show_config_status(config_file=str(config))
        assert result is False

    def test_config_file_invalid_json_output_json(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        from cja_auto_sdr.generator import show_config_status

        config = tmp_path / "config.json"
        config.write_text("{bad json")
        result = show_config_status(config_file=str(config), output_json=True)
        assert result is False
        data = json.loads(capsys.readouterr().out)
        assert data["valid"] is False

    @pytest.mark.parametrize("output_json", [True, False])
    def test_config_file_non_utf8_bytes_returns_controlled_error(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture,
        output_json: bool,
    ) -> None:
        """Non-UTF8 config bytes should not escape as traceback in --config-status."""
        from cja_auto_sdr.generator import show_config_status

        config = tmp_path / "config.json"
        config.write_bytes(b"\xff\xfe\xfd")

        result = show_config_status(config_file=str(config), output_json=output_json)

        assert result is False
        output = capsys.readouterr().out
        if output_json:
            payload = json.loads(output)
            assert payload["valid"] is False
            assert "Cannot read" in payload["error"]
        else:
            assert "Cannot read" in output

    def test_config_file_not_found(self, tmp_path: Path) -> None:
        from cja_auto_sdr.generator import show_config_status

        result = show_config_status(config_file=str(tmp_path / "nonexistent.json"))
        assert result is False

    def test_config_file_not_found_json(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        from cja_auto_sdr.generator import show_config_status

        result = show_config_status(config_file=str(tmp_path / "nonexistent.json"), output_json=True)
        assert result is False
        data = json.loads(capsys.readouterr().out)
        assert data["valid"] is False


class TestShowConfigStatusJsonOutput:
    """Lines 9988-9997: JSON output format."""

    def test_json_output_all_fields(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        from cja_auto_sdr.generator import show_config_status

        config = tmp_path / "config.json"
        config.write_text(
            json.dumps({"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}),
        )
        result = show_config_status(config_file=str(config), output_json=True)
        assert result is True
        data = json.loads(capsys.readouterr().out)
        assert data["valid"] is True
        assert data["source_type"] == "file"

    def test_missing_required_field(self, tmp_path: Path) -> None:
        from cja_auto_sdr.generator import show_config_status

        config = tmp_path / "config.json"
        config.write_text(json.dumps({"org_id": "org@Adobe"}))
        result = show_config_status(config_file=str(config))
        assert result is False


# ---------------------------------------------------------------------------
# 2. validate_config_only — lines 10035-10220
# ---------------------------------------------------------------------------


class TestValidateConfigOnly:
    """Lines 10100-10220: profile/env/file validation + API test."""

    @patch("cja_auto_sdr.generator._config_from_env")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.load_profile_credentials")
    def test_profile_valid_api_success(
        self, mock_load, mock_cjapy, _mock_config_env, capsys: pytest.CaptureFixture
    ) -> None:
        from cja_auto_sdr.generator import validate_config_only

        mock_load.return_value = {"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [{"id": "dv1"}]
        mock_cjapy.CJA.return_value = mock_cja
        result = validate_config_only(profile="myprofile")
        assert result is True
        assert "VALIDATION PASSED" in capsys.readouterr().out

    @patch("cja_auto_sdr.generator._config_from_env")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.load_profile_credentials")
    def test_no_color_env_disables_validate_config_ansi(
        self, mock_load, mock_cjapy, _mock_config_env, capsys: pytest.CaptureFixture
    ) -> None:
        """NO_COLOR should suppress ANSI styling in validate_config_only output."""
        from cja_auto_sdr.core.colors import ConsoleColors
        from cja_auto_sdr.generator import validate_config_only

        mock_load.return_value = {"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [{"id": "dv1"}]
        mock_cjapy.CJA.return_value = mock_cja

        previous_enabled = ConsoleColors.is_enabled()
        try:
            with patch.dict("os.environ", {"NO_COLOR": "1", "FORCE_COLOR": ""}, clear=False):
                ConsoleColors.configure(no_color=False)
                result = validate_config_only(profile="myprofile")
            assert result is True
            output = capsys.readouterr().out
            assert "\x1b[" not in output
        finally:
            ConsoleColors.set_enabled(previous_enabled)

    @patch("cja_auto_sdr.generator._config_from_env")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.load_profile_credentials")
    def test_force_color_env_enables_validate_config_ansi(
        self, mock_load, mock_cjapy, _mock_config_env, capsys: pytest.CaptureFixture
    ) -> None:
        """FORCE_COLOR should enable ANSI styling in validate_config_only output."""
        from cja_auto_sdr.core.colors import ConsoleColors
        from cja_auto_sdr.generator import validate_config_only

        mock_load.return_value = {"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [{"id": "dv1"}]
        mock_cjapy.CJA.return_value = mock_cja

        previous_enabled = ConsoleColors.is_enabled()
        try:
            with patch.dict("os.environ", {"FORCE_COLOR": "1"}, clear=False):
                ConsoleColors.configure(no_color=False)
                result = validate_config_only(profile="myprofile")
            assert result is True
            output = capsys.readouterr().out
            assert "\x1b[" in output
        finally:
            ConsoleColors.set_enabled(previous_enabled)

    @patch("cja_auto_sdr.generator._config_from_env")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.load_profile_credentials")
    def test_no_color_policy_overrides_force_color_for_validate_config(
        self, mock_load, mock_cjapy, _mock_config_env, capsys: pytest.CaptureFixture
    ) -> None:
        """Explicit no-color policy should beat FORCE_COLOR for validate_config_only output."""
        from cja_auto_sdr.core.colors import ConsoleColors
        from cja_auto_sdr.generator import validate_config_only

        mock_load.return_value = {"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [{"id": "dv1"}]
        mock_cjapy.CJA.return_value = mock_cja

        previous_enabled = ConsoleColors.is_enabled()
        try:
            with patch.dict("os.environ", {"FORCE_COLOR": "1"}, clear=False):
                ConsoleColors.configure(no_color=True)
                result = validate_config_only(profile="myprofile")
            assert result is True
            output = capsys.readouterr().out
            assert "\x1b[" not in output
        finally:
            ConsoleColors.set_enabled(previous_enabled)

    @patch("cja_auto_sdr.generator.load_profile_credentials")
    def test_profile_not_found(self, mock_load) -> None:
        from cja_auto_sdr.generator import ProfileNotFoundError, validate_config_only

        mock_load.side_effect = ProfileNotFoundError("not found", profile_name="bad")
        result = validate_config_only(profile="bad")
        assert result is False

    @patch("cja_auto_sdr.generator.load_profile_credentials")
    def test_profile_config_error(self, mock_load) -> None:
        from cja_auto_sdr.generator import ProfileConfigError, validate_config_only

        mock_load.side_effect = ProfileConfigError("invalid config", profile_name="bad")
        result = validate_config_only(profile="bad")
        assert result is False

    def test_no_config_file_no_env(self, tmp_path: Path) -> None:
        from cja_auto_sdr.generator import validate_config_only

        with patch("cja_auto_sdr.generator.load_credentials_from_env", return_value=None):
            result = validate_config_only(config_file=str(tmp_path / "nonexistent.json"))
        assert result is False

    @patch("cja_auto_sdr.generator.cjapy")
    def test_api_connection_failure(self, mock_cjapy, tmp_path: Path) -> None:
        from cja_auto_sdr.generator import validate_config_only

        config = tmp_path / "config.json"
        config.write_text(
            json.dumps({"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}),
        )
        mock_cja = MagicMock()
        mock_cja.getDataViews.side_effect = APIError("connection refused")
        mock_cjapy.CJA.return_value = mock_cja
        with patch("cja_auto_sdr.generator.load_credentials_from_env", return_value=None):
            result = validate_config_only(config_file=str(config))
        assert result is False

    @patch("cja_auto_sdr.generator.cjapy")
    def test_api_connection_missing_method_failure(self, mock_cjapy, tmp_path: Path) -> None:
        """Missing client methods (AttributeError) should degrade gracefully."""
        from cja_auto_sdr.generator import validate_config_only

        config = tmp_path / "config.json"
        config.write_text(
            json.dumps({"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}),
        )
        mock_cjapy.CJA.return_value = object()  # no getDataViews attribute
        with patch("cja_auto_sdr.generator.load_credentials_from_env", return_value=None):
            result = validate_config_only(config_file=str(config))
        assert result is False

    @patch("cja_auto_sdr.generator.cjapy")
    def test_api_connection_transport_failure(self, mock_cjapy, tmp_path: Path) -> None:
        """Transport failures (OSError subclasses) should be handled gracefully."""
        from cja_auto_sdr.generator import validate_config_only

        config = tmp_path / "config.json"
        config.write_text(
            json.dumps({"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}),
        )
        mock_cja = MagicMock()
        mock_cja.getDataViews.side_effect = ConnectionError("timeout")
        mock_cjapy.CJA.return_value = mock_cja
        with patch("cja_auto_sdr.generator.load_credentials_from_env", return_value=None):
            result = validate_config_only(config_file=str(config))
        assert result is False

    @patch("cja_auto_sdr.generator.cjapy")
    def test_api_connection_unexpected_exception(
        self, mock_cjapy, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """RuntimeError from cjapy.CJA()/getDataViews() should return False, not traceback."""
        from cja_auto_sdr.generator import validate_config_only

        config = tmp_path / "config.json"
        config.write_text(
            json.dumps({"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}),
        )
        mock_cja = MagicMock()
        mock_cja.getDataViews.side_effect = RuntimeError("unexpected auth bootstrap failure")
        mock_cjapy.CJA.return_value = mock_cja
        with patch("cja_auto_sdr.generator.load_credentials_from_env", return_value=None):
            result = validate_config_only(config_file=str(config))
        assert result is False
        captured = capsys.readouterr()
        assert "API connection failed (unexpected)" in captured.out

    @patch("cja_auto_sdr.generator.cjapy")
    def test_api_cja_init_unexpected_exception(self, mock_cjapy, tmp_path: Path) -> None:
        """RuntimeError from CJA() constructor should return False, not traceback."""
        from cja_auto_sdr.generator import validate_config_only

        config = tmp_path / "config.json"
        config.write_text(
            json.dumps({"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}),
        )
        mock_cjapy.CJA.side_effect = RuntimeError("bootstrap crash")
        with patch("cja_auto_sdr.generator.load_credentials_from_env", return_value=None):
            result = validate_config_only(config_file=str(config))
        assert result is False

    @patch("cja_auto_sdr.generator.cjapy")
    def test_api_cja_init_plain_exception(self, mock_cjapy, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Bare constructor Exception from CJA() should return False, not traceback."""
        from cja_auto_sdr.generator import validate_config_only

        config = tmp_path / "config.json"
        config.write_text(
            json.dumps({"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}),
        )
        mock_cjapy.CJA.side_effect = Exception("auth bootstrap failed")
        with patch("cja_auto_sdr.generator.load_credentials_from_env", return_value=None):
            result = validate_config_only(config_file=str(config))
        assert result is False
        assert "API connection failed (unexpected)" in capsys.readouterr().out

    @patch("cja_auto_sdr.generator._config_from_env")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.load_credentials_from_env")
    @patch("cja_auto_sdr.generator.validate_env_credentials", return_value=True)
    def test_env_credentials_api_returns_none(
        self, _mock_validate, mock_load_env, mock_cjapy, _mock_config_env, capsys: pytest.CaptureFixture
    ) -> None:
        """Line 10201: API returns None response."""
        from cja_auto_sdr.generator import validate_config_only

        mock_load_env.return_value = {"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = None
        mock_cjapy.CJA.return_value = mock_cja
        validate_config_only()
        output = capsys.readouterr().out
        assert "empty response" in output or "unstable" in output

    def test_config_file_invalid_json(self, tmp_path: Path) -> None:
        from cja_auto_sdr.generator import validate_config_only

        config = tmp_path / "config.json"
        config.write_text("{bad json")
        with patch("cja_auto_sdr.generator.load_credentials_from_env", return_value=None):
            result = validate_config_only(config_file=str(config))
        assert result is False

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.load_credentials_from_env")
    @patch("cja_auto_sdr.generator.validate_env_credentials", return_value=True)
    def test_env_credentials_incomplete_then_file(
        self, _mock_validate, mock_load_env, mock_cjapy, tmp_path: Path
    ) -> None:
        """Line 10131: env creds incomplete, fallback to file."""
        from cja_auto_sdr.generator import validate_config_only

        # Return creds that look present but validate_env_credentials returns True
        # but display_credentials says missing fields
        mock_load_env.return_value = {"org_id": "org@Adobe"}  # missing client_id, secret
        _mock_validate.return_value = False  # Actually fail env validation
        config = tmp_path / "config.json"
        config.write_text(
            json.dumps({"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}),
        )
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [{"id": "dv1"}]
        mock_cjapy.CJA.return_value = mock_cja
        validate_config_only(config_file=str(config))
        # Should fall through to config file and pass


# ---------------------------------------------------------------------------
# 2b. validate_config_only — new steps (environment, dependencies, output)
# ---------------------------------------------------------------------------


class TestValidateConfigOnlyEnvironmentStep:
    """Step [1/5]: environment check (Python version, platform)."""

    @patch("cja_auto_sdr.generator._config_from_env")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.load_profile_credentials")
    def test_environment_step_shows_python_version(
        self, mock_load, mock_cjapy, _mock_config_env, capsys: pytest.CaptureFixture
    ) -> None:
        from cja_auto_sdr.generator import validate_config_only

        mock_load.return_value = {"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [{"id": "dv1"}]
        mock_cjapy.CJA.return_value = mock_cja
        validate_config_only(profile="myprofile")
        output = capsys.readouterr().out
        assert "[1/5] Checking environment..." in output
        assert "Python" in output
        assert "(minimum: 3.14)" in output

    @patch("cja_auto_sdr.generator._config_from_env")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.load_profile_credentials")
    def test_environment_step_shows_platform(
        self, mock_load, mock_cjapy, _mock_config_env, capsys: pytest.CaptureFixture
    ) -> None:
        from cja_auto_sdr.generator import validate_config_only

        mock_load.return_value = {"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [{"id": "dv1"}]
        mock_cjapy.CJA.return_value = mock_cja
        validate_config_only(profile="myprofile")
        output = capsys.readouterr().out
        assert "Platform:" in output

    def test_python_version_too_low_fails(self, capsys: pytest.CaptureFixture) -> None:
        """Python version below 3.14 should fail validation."""
        import sys as _sys

        from cja_auto_sdr.generator import validate_config_only

        # sys.version_info is a named tuple that supports >= comparison with
        # a plain tuple. We create a subclass of tuple with attribute access.
        class FakeVersionInfo(tuple):
            __slots__ = ()
            major = 3
            minor = 12
            micro = 0

        fake_version_info = FakeVersionInfo((3, 12, 0))

        with patch("cja_auto_sdr.generator.sys") as mock_sys:
            mock_sys.version_info = fake_version_info
            mock_sys.platform = _sys.platform
            result = validate_config_only()
        assert result is False
        output = capsys.readouterr().out
        assert "Python 3.12.0" in output
        assert "VALIDATION FAILED" in output


class TestValidateConfigOnlyDependenciesStep:
    """Step [2/5]: dependency check (core + optional)."""

    @patch("cja_auto_sdr.generator._config_from_env")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.load_profile_credentials")
    def test_dependencies_step_shows_core_deps(
        self, mock_load, mock_cjapy, _mock_config_env, capsys: pytest.CaptureFixture
    ) -> None:
        from cja_auto_sdr.generator import validate_config_only

        mock_load.return_value = {"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [{"id": "dv1"}]
        mock_cjapy.CJA.return_value = mock_cja
        validate_config_only(profile="myprofile")
        output = capsys.readouterr().out
        assert "[2/5] Checking dependencies..." in output
        # Core deps should all show with checkmark
        for pkg in ("cjapy", "pandas", "numpy", "xlsxwriter", "tqdm"):
            assert pkg in output

    @patch("cja_auto_sdr.generator._config_from_env")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.load_profile_credentials")
    def test_dependencies_step_shows_optional_deps(
        self, mock_load, mock_cjapy, _mock_config_env, capsys: pytest.CaptureFixture
    ) -> None:
        from cja_auto_sdr.generator import validate_config_only

        mock_load.return_value = {"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [{"id": "dv1"}]
        mock_cjapy.CJA.return_value = mock_cja
        validate_config_only(profile="myprofile")
        output = capsys.readouterr().out
        # Optional deps show with dash, regardless of installed status
        assert "optional" in output
        assert "--org-report clustering" in output or "org-report" in output
        assert "shell tab-completion" in output
        assert ".env file loading" in output

    def test_missing_core_dependency_fails(self, capsys: pytest.CaptureFixture) -> None:
        """Missing core dependency should fail validation."""
        import importlib.metadata

        from cja_auto_sdr.generator import validate_config_only

        original_version = importlib.metadata.version

        def mock_version(pkg):
            if pkg == "pandas":
                raise importlib.metadata.PackageNotFoundError(pkg)
            return original_version(pkg)

        with patch("cja_auto_sdr.generator.importlib.metadata.version", side_effect=mock_version):
            result = validate_config_only()
        assert result is False
        output = capsys.readouterr().out
        assert "pandas (not installed)" in output
        assert "VALIDATION FAILED" in output

    def test_missing_optional_dependency_does_not_fail(self, capsys: pytest.CaptureFixture) -> None:
        """Missing optional dependency should NOT fail validation."""
        import importlib.metadata

        from cja_auto_sdr.generator import validate_config_only

        original_version = importlib.metadata.version

        def mock_version(pkg):
            if pkg in ("scipy", "argcomplete", "python-dotenv"):
                raise importlib.metadata.PackageNotFoundError(pkg)
            return original_version(pkg)

        with patch("cja_auto_sdr.generator.importlib.metadata.version", side_effect=mock_version):
            with patch("cja_auto_sdr.generator.load_credentials_from_env", return_value=None):
                validate_config_only()
        # Fails for credentials, not for optional deps
        output = capsys.readouterr().out
        assert "scipy not installed (optional" in output
        assert "argcomplete not installed (optional" in output
        assert "python-dotenv not installed (optional" in output
        # Should NOT fail at step 2 — it should proceed to step 3
        assert "[3/5]" in output

    def test_malformed_metadata_on_core_dep_fails_validation(self, capsys: pytest.CaptureFixture) -> None:
        """Non-PackageNotFoundError on core dep should fail validation with diagnostic."""
        import importlib.metadata

        from cja_auto_sdr.generator import validate_config_only

        original_version = importlib.metadata.version

        def mock_version(pkg):
            if pkg == "pandas":
                raise ValueError("malformed metadata")
            return original_version(pkg)

        with patch("cja_auto_sdr.generator.importlib.metadata.version", side_effect=mock_version):
            result = validate_config_only()
        assert result is False
        output = capsys.readouterr().out
        assert "pandas" in output
        assert "metadata error" in output
        assert "VALIDATION FAILED" in output

    def test_oserror_on_core_dep_fails_validation(self, capsys: pytest.CaptureFixture) -> None:
        """OSError on core dep metadata should fail validation with diagnostic."""
        import importlib.metadata

        from cja_auto_sdr.generator import validate_config_only

        original_version = importlib.metadata.version

        def mock_version(pkg):
            if pkg == "numpy":
                raise OSError("corrupt dist-info")
            return original_version(pkg)

        with patch("cja_auto_sdr.generator.importlib.metadata.version", side_effect=mock_version):
            result = validate_config_only()
        assert result is False
        output = capsys.readouterr().out
        assert "numpy" in output
        assert "metadata error" in output

    def test_malformed_metadata_on_optional_dep_does_not_fail(self, capsys: pytest.CaptureFixture) -> None:
        """Non-PackageNotFoundError on optional dep should show diagnostic but not fail."""
        import importlib.metadata

        from cja_auto_sdr.generator import validate_config_only

        original_version = importlib.metadata.version

        def mock_version(pkg):
            if pkg == "scipy":
                raise ValueError("corrupt metadata")
            return original_version(pkg)

        with patch("cja_auto_sdr.generator.importlib.metadata.version", side_effect=mock_version):
            with patch("cja_auto_sdr.generator.load_credentials_from_env", return_value=None):
                validate_config_only()
        output = capsys.readouterr().out
        assert "scipy" in output
        assert "metadata error" in output
        # Should proceed past step 2 — optional deps never fail validation
        assert "[3/5]" in output

    def test_all_core_deps_metadata_errors_fails_validation(self, capsys: pytest.CaptureFixture) -> None:
        """If all core deps raise non-PackageNotFoundError, validation fails with diagnostics."""
        from cja_auto_sdr.generator import validate_config_only

        def all_broken(pkg):
            raise OSError(f"metadata backend unavailable for {pkg}")

        with patch("cja_auto_sdr.generator.importlib.metadata.version", side_effect=all_broken):
            result = validate_config_only()
        assert result is False
        output = capsys.readouterr().out
        for pkg in ("cjapy", "pandas", "numpy", "xlsxwriter", "tqdm"):
            assert pkg in output
            assert "metadata error" in output
        assert "VALIDATION FAILED" in output


class TestValidateConfigOnlyOutputPermissionsStep:
    """Step [5/5]: output permissions check."""

    @patch("cja_auto_sdr.generator._config_from_env")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.load_profile_credentials")
    def test_output_permissions_shown_on_success(
        self, mock_load, mock_cjapy, _mock_config_env, capsys: pytest.CaptureFixture
    ) -> None:
        from cja_auto_sdr.generator import validate_config_only

        mock_load.return_value = {"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [{"id": "dv1"}]
        mock_cjapy.CJA.return_value = mock_cja
        validate_config_only(profile="myprofile")
        output = capsys.readouterr().out
        assert "[5/5] Checking output permissions..." in output
        assert "Output directory writable" in output

    @patch("cja_auto_sdr.generator._config_from_env")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.load_profile_credentials")
    def test_output_permissions_not_writable_fails(
        self, mock_load, mock_cjapy, _mock_config_env, capsys: pytest.CaptureFixture
    ) -> None:
        from cja_auto_sdr.generator import validate_config_only

        mock_load.return_value = {"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [{"id": "dv1"}]
        mock_cjapy.CJA.return_value = mock_cja
        with patch("cja_auto_sdr.generator.os.access", return_value=False):
            result = validate_config_only(profile="myprofile")
        assert result is False
        output = capsys.readouterr().out
        assert "Output directory not writable" in output
        assert "VALIDATION FAILED" in output

    @patch("cja_auto_sdr.generator._config_from_env")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.load_profile_credentials")
    def test_output_permissions_uses_output_dir_param(
        self, mock_load, mock_cjapy, _mock_config_env, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Step 5 should check the output_dir passed as argument, not hard-coded '.'."""
        from cja_auto_sdr.generator import validate_config_only

        mock_load.return_value = {"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [{"id": "dv1"}]
        mock_cjapy.CJA.return_value = mock_cja
        validate_config_only(profile="myprofile", output_dir=str(tmp_path))
        output = capsys.readouterr().out
        assert str(tmp_path) in output
        assert "Output directory writable" in output

    @patch("cja_auto_sdr.generator._config_from_env")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.load_profile_credentials")
    def test_output_permissions_missing_dir_uses_parent_writability(
        self, mock_load, mock_cjapy, _mock_config_env, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Step 5 should pass when output_dir does not exist but parent is writable."""
        from cja_auto_sdr.generator import validate_config_only

        mock_load.return_value = {"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [{"id": "dv1"}]
        mock_cjapy.CJA.return_value = mock_cja
        new_output_dir = tmp_path / "nested" / "new-output"
        result = validate_config_only(profile="myprofile", output_dir=str(new_output_dir))
        assert result is True
        output = capsys.readouterr().out
        assert "Output directory creatable" in output
        assert str(new_output_dir.resolve()) in output

    @patch("cja_auto_sdr.generator._config_from_env")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.load_profile_credentials")
    def test_output_permissions_existing_file_fails(
        self, mock_load, mock_cjapy, _mock_config_env, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Step 5 should fail when output_dir points to a file path."""
        from cja_auto_sdr.generator import validate_config_only

        mock_load.return_value = {"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [{"id": "dv1"}]
        mock_cjapy.CJA.return_value = mock_cja
        output_file = tmp_path / "not-a-directory.txt"
        output_file.write_text("x", encoding="utf-8")
        result = validate_config_only(profile="myprofile", output_dir=str(output_file))
        assert result is False
        output = capsys.readouterr().out
        assert "Output path is not a directory" in output
        assert "VALIDATION FAILED" in output

    @patch("cja_auto_sdr.generator.cjapy")
    def test_output_permissions_skipped_when_api_fails(
        self, mock_cjapy, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Step 5 should not run when step 4 (API) fails."""
        from cja_auto_sdr.generator import validate_config_only

        config = tmp_path / "config.json"
        config.write_text(
            json.dumps({"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}),
        )
        mock_cja = MagicMock()
        mock_cja.getDataViews.side_effect = APIError("connection refused")
        mock_cjapy.CJA.return_value = mock_cja
        with patch("cja_auto_sdr.generator.load_credentials_from_env", return_value=None):
            result = validate_config_only(config_file=str(config))
        assert result is False
        output = capsys.readouterr().out
        assert "[5/5]" not in output


class TestValidateConfigOnlyStepNumbering:
    """Verify the 5-step numbering is correct across the full flow."""

    @patch("cja_auto_sdr.generator._config_from_env")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.load_profile_credentials")
    def test_all_five_steps_appear(
        self, mock_load, mock_cjapy, _mock_config_env, capsys: pytest.CaptureFixture
    ) -> None:
        from cja_auto_sdr.generator import validate_config_only

        mock_load.return_value = {"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [{"id": "dv1"}]
        mock_cjapy.CJA.return_value = mock_cja
        result = validate_config_only(profile="myprofile")
        assert result is True
        output = capsys.readouterr().out
        assert "[1/5]" in output
        assert "[2/5]" in output
        assert "[3/5]" in output
        assert "[4/5]" in output
        assert "[5/5]" in output

    @patch("cja_auto_sdr.generator._config_from_env")
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.load_profile_credentials")
    def test_no_old_step_numbers(self, mock_load, mock_cjapy, _mock_config_env, capsys: pytest.CaptureFixture) -> None:
        """Old step numbering [X/3] should no longer appear."""
        from cja_auto_sdr.generator import validate_config_only

        mock_load.return_value = {"org_id": "org@Adobe", "client_id": "abcd1234efgh", "secret": "secret12345678"}
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [{"id": "dv1"}]
        mock_cjapy.CJA.return_value = mock_cja
        validate_config_only(profile="myprofile")
        output = capsys.readouterr().out
        assert "/3]" not in output


# ---------------------------------------------------------------------------
# 3. show_stats — lines 10226-10410
# ---------------------------------------------------------------------------


class TestShowStats:
    """Lines 10248-10410: stats command output formats and error handling."""

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_table_format(self, mock_config, mock_cjapy, capsys: pytest.CaptureFixture) -> None:
        from cja_auto_sdr.generator import show_stats

        mock_config.return_value = (True, "file", None)
        mock_cja = MagicMock()
        mock_cja.getDataView.return_value = {"name": "Test DV", "owner": {"name": "Alice"}, "description": "Desc"}
        mock_cja.getMetrics.return_value = pd.DataFrame({"id": ["m1", "m2"]})
        mock_cja.getDimensions.return_value = pd.DataFrame({"id": ["d1"]})
        mock_cjapy.CJA.return_value = mock_cja
        result = show_stats(["dv_test"])
        assert result is True
        assert "Test DV" in capsys.readouterr().out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_json_format(self, mock_config, mock_cjapy, capsys: pytest.CaptureFixture) -> None:
        from cja_auto_sdr.generator import show_stats

        mock_config.return_value = (True, "file", None)
        mock_cja = MagicMock()
        mock_cja.getDataView.return_value = {"name": "Test DV", "owner": {"name": "Alice"}, "description": ""}
        mock_cja.getMetrics.return_value = pd.DataFrame({"id": ["m1"]})
        mock_cja.getDimensions.return_value = pd.DataFrame({"id": ["d1"]})
        mock_cjapy.CJA.return_value = mock_cja
        result = show_stats(["dv_test"], output_format="json")
        assert result is True
        data = json.loads(capsys.readouterr().out)
        assert data["count"] == 1
        mock_cja.getMetrics.assert_called_once_with("dv_test", inclType="hidden", full=True)
        mock_cja.getDimensions.assert_called_once_with("dv_test", inclType="hidden", full=True)

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_json_format_counts_hidden_components(self, mock_config, mock_cjapy, capsys: pytest.CaptureFixture) -> None:
        """show_stats should include hidden metrics/dimensions for parity with discovery commands."""
        from cja_auto_sdr.generator import show_stats

        mock_config.return_value = (True, "file", None)
        mock_cja = MagicMock()
        mock_cja.getDataView.return_value = {"name": "Test DV", "owner": {"name": "Alice"}, "description": ""}

        def _get_metrics(_dv_id: str, **kwargs):
            if kwargs.get("inclType") == "hidden" and kwargs.get("full") is True:
                return pd.DataFrame({"id": ["m_visible", "m_hidden"]})
            return pd.DataFrame({"id": ["m_visible"]})

        def _get_dimensions(_dv_id: str, **kwargs):
            if kwargs.get("inclType") == "hidden" and kwargs.get("full") is True:
                return pd.DataFrame({"id": ["d_visible", "d_hidden"]})
            return pd.DataFrame({"id": ["d_visible"]})

        mock_cja.getMetrics.side_effect = _get_metrics
        mock_cja.getDimensions.side_effect = _get_dimensions
        mock_cjapy.CJA.return_value = mock_cja

        result = show_stats(["dv_test"], output_format="json")
        assert result is True
        data = json.loads(capsys.readouterr().out)
        assert data["stats"][0]["metrics"] == 2
        assert data["stats"][0]["dimensions"] == 2
        assert data["stats"][0]["total_components"] == 4
        assert data["totals"]["metrics"] == 2
        assert data["totals"]["dimensions"] == 2
        assert data["totals"]["components"] == 4

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_csv_format(self, mock_config, mock_cjapy, capsys: pytest.CaptureFixture) -> None:
        from cja_auto_sdr.generator import show_stats

        mock_config.return_value = (True, "file", None)
        mock_cja = MagicMock()
        mock_cja.getDataView.return_value = {"name": "Test DV", "owner": {"name": "Alice"}, "description": ""}
        mock_cja.getMetrics.return_value = pd.DataFrame({"id": ["m1"]})
        mock_cja.getDimensions.return_value = pd.DataFrame({"id": ["d1"]})
        mock_cjapy.CJA.return_value = mock_cja
        result = show_stats(["dv_test"], output_format="csv")
        assert result is True
        assert "id,name" in capsys.readouterr().out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_json_to_stdout(self, mock_config, mock_cjapy) -> None:
        from cja_auto_sdr.generator import show_stats

        mock_config.return_value = (True, "file", None)
        mock_cja = MagicMock()
        mock_cja.getDataView.return_value = {"name": "DV", "owner": {}, "description": ""}
        mock_cja.getMetrics.return_value = pd.DataFrame()
        mock_cja.getDimensions.return_value = pd.DataFrame()
        mock_cjapy.CJA.return_value = mock_cja
        assert show_stats(["dv_test"], output_file="-") is True

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_json_to_file(self, mock_config, mock_cjapy, tmp_path: Path) -> None:
        from cja_auto_sdr.generator import show_stats

        mock_config.return_value = (True, "file", None)
        mock_cja = MagicMock()
        mock_cja.getDataView.return_value = {"name": "DV", "owner": {}, "description": ""}
        mock_cja.getMetrics.return_value = pd.DataFrame()
        mock_cja.getDimensions.return_value = pd.DataFrame()
        mock_cjapy.CJA.return_value = mock_cja
        outfile = str(tmp_path / "stats.json")
        assert show_stats(["dv_test"], output_format="json", output_file=outfile) is True
        assert Path(outfile).exists()

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_csv_to_file(self, mock_config, mock_cjapy, tmp_path: Path) -> None:
        from cja_auto_sdr.generator import show_stats

        mock_config.return_value = (True, "file", None)
        mock_cja = MagicMock()
        mock_cja.getDataView.return_value = {"name": "DV", "owner": {}, "description": ""}
        mock_cja.getMetrics.return_value = pd.DataFrame()
        mock_cja.getDimensions.return_value = pd.DataFrame()
        mock_cjapy.CJA.return_value = mock_cja
        outfile = str(tmp_path / "stats.csv")
        assert show_stats(["dv_test"], output_format="csv", output_file=outfile) is True
        assert Path(outfile).exists()

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_per_dv_exception(self, mock_config, mock_cjapy, capsys: pytest.CaptureFixture) -> None:
        """Lines 10301-10312: exception per data view caught gracefully."""
        from cja_auto_sdr.generator import show_stats

        mock_config.return_value = (True, "file", None)
        mock_cja = MagicMock()
        mock_cja.getDataView.side_effect = APIError("API error")
        mock_cjapy.CJA.return_value = mock_cja
        result = show_stats(["dv_test"], output_format="json")
        assert result is True
        data = json.loads(capsys.readouterr().out)
        assert data["stats"][0]["name"] == "ERROR"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_per_dv_transport_exception_continues(self, mock_config, mock_cjapy, capsys: pytest.CaptureFixture) -> None:
        """Transport failure for one data view should not abort remaining IDs."""
        from cja_auto_sdr.generator import show_stats

        mock_config.return_value = (True, "file", None)
        mock_cja = MagicMock()
        mock_cja.getDataView.side_effect = [
            ConnectionError("network issue"),
            {"name": "Healthy DV", "owner": {"name": "Alice"}, "description": ""},
        ]
        mock_cja.getMetrics.return_value = pd.DataFrame({"id": ["m1"]})
        mock_cja.getDimensions.return_value = pd.DataFrame({"id": ["d1"]})
        mock_cjapy.CJA.return_value = mock_cja

        result = show_stats(["dv_bad", "dv_ok"], output_format="json")
        assert result is True
        data = json.loads(capsys.readouterr().out)
        assert data["count"] == 2
        assert data["stats"][0]["name"] == "ERROR"
        assert data["stats"][1]["name"] == "Healthy DV"

    @pytest.mark.parametrize(
        "failure_stage",
        ["getDataView", "getMetrics", "getDimensions"],
    )
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_per_dv_unexpected_runtime_exception_continues(
        self,
        mock_config,
        mock_cjapy,
        capsys: pytest.CaptureFixture,
        failure_stage: str,
    ) -> None:
        """Unexpected runtime failures for one DV should not abort remaining stats rows."""
        from cja_auto_sdr.generator import show_stats

        mock_config.return_value = (True, "file", None)
        mock_cja = MagicMock()

        def _get_dv(dv_id: str):
            if failure_stage == "getDataView" and dv_id == "dv_bad":
                raise RuntimeError("unexpected dv lookup failure")
            return {"name": "Healthy DV", "owner": {"name": "Alice"}, "description": "ok"}

        def _get_metrics(dv_id: str, **_kwargs):
            if failure_stage == "getMetrics" and dv_id == "dv_bad":
                raise RuntimeError("unexpected metrics failure")
            return pd.DataFrame({"id": ["m1"]})

        def _get_dimensions(dv_id: str, **_kwargs):
            if failure_stage == "getDimensions" and dv_id == "dv_bad":
                raise RuntimeError("unexpected dimensions failure")
            return pd.DataFrame({"id": ["d1"]})

        mock_cja.getDataView.side_effect = _get_dv
        mock_cja.getMetrics.side_effect = _get_metrics
        mock_cja.getDimensions.side_effect = _get_dimensions
        mock_cjapy.CJA.return_value = mock_cja

        result = show_stats(["dv_bad", "dv_ok"], output_format="json")
        assert result is True
        data = json.loads(capsys.readouterr().out)
        assert data["count"] == 2
        assert data["stats"][0]["name"] == "ERROR"
        assert data["stats"][1]["name"] == "Healthy DV"

    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(False, "Config error", None))
    def test_config_failure(self, _mock_config) -> None:
        from cja_auto_sdr.generator import show_stats

        assert show_stats(["dv_test"]) is False

    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(False, "Config error", None))
    def test_config_failure_machine_readable_emits_stderr_json(
        self,
        _mock_config,
        capsys: pytest.CaptureFixture,
    ) -> None:
        from cja_auto_sdr.generator import show_stats

        assert show_stats(["dv_test"], output_format="json") is False
        captured = capsys.readouterr()
        assert captured.out == ""
        payload = json.loads(captured.err)
        assert payload == {"error": "Configuration error: Config error", "error_type": "configuration_error"}

    @pytest.mark.parametrize(
        ("scenario", "expected_error_type", "expected_prefix"),
        [
            ("config_failure", "configuration_error", "Configuration error:"),
            ("file_not_found", "configuration_error", "Configuration file 'config.json' not found"),
            ("connectivity_failure", "connectivity_error", "Failed to get stats:"),
        ],
    )
    def test_machine_readable_error_envelope_schema(
        self,
        capsys: pytest.CaptureFixture,
        scenario: str,
        expected_error_type: str,
        expected_prefix: str,
    ) -> None:
        """Machine-readable stats failures should always emit error + error_type."""
        from cja_auto_sdr.generator import show_stats

        if scenario == "config_failure":
            patcher = patch("cja_auto_sdr.generator.configure_cjapy", return_value=(False, "Config error", None))
        elif scenario == "file_not_found":
            patcher = patch("cja_auto_sdr.generator.configure_cjapy", side_effect=FileNotFoundError("not found"))
        else:
            patcher = patch("cja_auto_sdr.generator.configure_cjapy", side_effect=ConfigurationError("boom"))

        with patcher:
            assert show_stats(["dv_test"], output_format="json") is False

        captured = capsys.readouterr()
        assert captured.out == ""
        payload = json.loads(captured.err)
        assert {"error", "error_type"}.issubset(payload)
        assert payload["error_type"] == expected_error_type
        assert payload["error"].startswith(expected_prefix)

    @patch("cja_auto_sdr.generator.configure_cjapy", side_effect=FileNotFoundError("not found"))
    def test_file_not_found(self, _mock_config) -> None:
        """Lines 10390-10396: FileNotFoundError handler."""
        from cja_auto_sdr.generator import show_stats

        assert show_stats(["dv_test"]) is False

    @patch("cja_auto_sdr.generator.configure_cjapy", side_effect=FileNotFoundError("not found"))
    def test_file_not_found_machine_readable(self, _mock_config, capsys: pytest.CaptureFixture) -> None:
        """Lines 10391-10393: FileNotFoundError with JSON output."""
        from cja_auto_sdr.generator import show_stats

        assert show_stats(["dv_test"], output_format="json") is False
        captured = capsys.readouterr()
        assert captured.out == ""
        payload = json.loads(captured.err)
        assert payload == {
            "error": "Configuration file 'config.json' not found",
            "error_type": "configuration_error",
        }

    @patch("cja_auto_sdr.generator.configure_cjapy", side_effect=ConfigurationError("boom"))
    def test_generic_exception(self, _mock_config) -> None:
        """Lines 10404-10410: generic exception handler."""
        from cja_auto_sdr.generator import show_stats

        assert show_stats(["dv_test"]) is False

    @patch("cja_auto_sdr.generator.configure_cjapy", side_effect=ConfigurationError("boom"))
    def test_generic_exception_machine_readable(self, _mock_config, capsys: pytest.CaptureFixture) -> None:
        """Lines 10405-10407: generic exception with JSON output."""
        from cja_auto_sdr.generator import show_stats

        assert show_stats(["dv_test"], output_format="json") is False
        captured = capsys.readouterr()
        assert captured.out == ""
        payload = json.loads(captured.err)
        assert payload["error"] == "Failed to get stats: boom"
        assert payload["error_type"] == "connectivity_error"

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_cja_constructor_hint_shows_on_human_stdout(
        self,
        mock_config,
        mock_cjapy,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Hint-bearing exact-ID stats failures should keep the error and hint on stdout."""
        from cja_auto_sdr.generator import show_stats

        mock_config.return_value = (True, "file", None)
        mock_cjapy.CJA.side_effect = KeyError("content")

        assert show_stats(["dv_test"]) is False
        captured = capsys.readouterr()
        assert "Failed to get stats: 'content'" in captured.out
        assert "AEP API" in captured.out
        assert captured.err == ""

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_cja_constructor_hint_suppressed_for_machine_readable(
        self,
        mock_config,
        mock_cjapy,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Machine-readable stats failures must keep stderr as JSON only."""
        from cja_auto_sdr.generator import show_stats

        mock_config.return_value = (True, "file", None)
        mock_cjapy.CJA.side_effect = KeyError("content")

        assert show_stats(["dv_test"], output_format="json") is False
        captured = capsys.readouterr()
        assert captured.out == ""
        payload = json.loads(captured.err)
        assert payload["error"] == "Failed to get stats: 'content'"
        assert payload["error_type"] == "connectivity_error"

    @patch("cja_auto_sdr.cli.commands.stats._collect_stats_row_with_fallback", side_effect=KeyError("name"))
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_local_stats_key_error_does_not_emit_api_hint(
        self,
        mock_config,
        mock_cjapy,
        _mock_collect,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Local stats-processing KeyErrors should not claim an auth/config issue."""
        from cja_auto_sdr.generator import show_stats

        mock_config.return_value = (True, "file", None)
        mock_cjapy.CJA.return_value = Mock()

        assert show_stats(["dv_test"]) is False
        captured = capsys.readouterr()
        assert "Failed to get stats: 'name'" in captured.out
        assert "AEP API" not in captured.out
        assert "OAuth credentials" not in captured.out

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_cja_constructor_exception_returns_controlled_failure(
        self,
        mock_config,
        mock_cjapy,
        capsys: pytest.CaptureFixture,
    ) -> None:
        """Bare constructor failures from cjapy should be handled without traceback."""
        from cja_auto_sdr.generator import show_stats

        mock_config.return_value = (True, "file", None)
        mock_cjapy.CJA.side_effect = Exception("auth bootstrap failed")

        assert show_stats(["dv_test"]) is False
        assert "Failed to get stats: auth bootstrap failed" in capsys.readouterr().out


# ---------------------------------------------------------------------------
# 4. resolve_data_view_names — lines 8208-8361
# ---------------------------------------------------------------------------


class TestResolveDataViewNames:
    """Lines 8252-8360: resolution modes, name matching, suggestions."""

    @pytest.fixture(autouse=True)
    def _clear_dv_cache(self):
        """Clear global DataViewCache before each test."""
        from cja_auto_sdr.generator import _data_view_cache

        _data_view_cache.clear()

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_exact_match(self, mock_config, mock_cjapy) -> None:
        from cja_auto_sdr.generator import resolve_data_view_names

        mock_config.return_value = (True, "file", None)
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [{"id": "dv_1", "name": "My DV"}]
        mock_cjapy.CJA.return_value = mock_cja
        ids, name_map = resolve_data_view_names(["My DV"], match_mode="exact")
        assert ids == ["dv_1"]
        assert "My DV" in name_map

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_insensitive_match(self, mock_config, mock_cjapy) -> None:
        from cja_auto_sdr.generator import resolve_data_view_names

        mock_config.return_value = (True, "file", None)
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [{"id": "dv_1", "name": "My DV"}]
        mock_cjapy.CJA.return_value = mock_cja
        ids, _ = resolve_data_view_names(["my dv"], match_mode="insensitive")
        assert ids == ["dv_1"]

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_fuzzy_match_nearest(self, mock_config, mock_cjapy) -> None:
        from cja_auto_sdr.generator import resolve_data_view_names

        mock_config.return_value = (True, "file", None)
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [{"id": "dv_1", "name": "My Data View"}]
        mock_cjapy.CJA.return_value = mock_cja
        ids, _ = resolve_data_view_names(["My Dta View"], match_mode="fuzzy")
        assert len(ids) >= 1

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_name_not_found_with_suggestions(self, mock_config, mock_cjapy) -> None:
        """Lines 8334-8342: suggestions when exact match fails."""
        from cja_auto_sdr.generator import resolve_data_view_names

        mock_config.return_value = (True, "file", None)
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [{"id": "dv_1", "name": "Production DV"}]
        mock_cjapy.CJA.return_value = mock_cja
        ids, _ = resolve_data_view_names(["Productin DV"], match_mode="exact")
        assert len(ids) == 0

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_id_passthrough(self, mock_config, mock_cjapy) -> None:
        from cja_auto_sdr.generator import resolve_data_view_names

        mock_config.return_value = (True, "file", None)
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [{"id": "dv_test", "name": "Test"}]
        mock_cjapy.CJA.return_value = mock_cja
        ids, _ = resolve_data_view_names(["dv_test"])
        assert ids == ["dv_test"]

    @patch("cja_auto_sdr.generator.configure_cjapy", return_value=(False, "Error", None))
    def test_config_failure(self, _mock_config) -> None:
        from cja_auto_sdr.generator import resolve_data_view_names

        ids, _ = resolve_data_view_names(["dv_test"])
        assert ids == []

    @patch("cja_auto_sdr.generator.configure_cjapy", side_effect=FileNotFoundError("not found"))
    def test_file_not_found(self, _mock_config) -> None:
        """Line 8355-8357: FileNotFoundError handler."""
        from cja_auto_sdr.generator import resolve_data_view_names

        ids, _ = resolve_data_view_names(["dv_test"])
        assert ids == []

    @patch("cja_auto_sdr.generator.configure_cjapy", side_effect=APIError("unexpected"))
    def test_generic_exception(self, _mock_config) -> None:
        """Lines 8358-8360: generic exception handler."""
        from cja_auto_sdr.generator import resolve_data_view_names

        ids, _ = resolve_data_view_names(["dv_test"])
        assert ids == []

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_transport_exception_returns_empty(self, mock_config, mock_cjapy) -> None:
        """Transport failures while listing data views should return controlled failure."""
        from cja_auto_sdr.generator import resolve_data_view_names

        mock_config.return_value = (True, "file", None)
        mock_cja = MagicMock()
        mock_cja.getDataViews.side_effect = ConnectionError("timed out")
        mock_cjapy.CJA.return_value = mock_cja

        ids, name_map = resolve_data_view_names(["My DV"])
        assert ids == []
        assert name_map == {}

    def test_invalid_match_mode(self) -> None:
        from cja_auto_sdr.generator import resolve_data_view_names

        with pytest.raises(ValueError, match="Invalid match_mode"):
            resolve_data_view_names(["dv_test"], match_mode="invalid")

    @patch("cja_auto_sdr.generator.get_cached_data_views", return_value=[])
    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_no_data_views_available(self, mock_config, mock_cjapy, _mock_cache) -> None:
        """Line 8267: no data views accessible."""
        from cja_auto_sdr.generator import resolve_data_view_names

        mock_config.return_value = (True, "file", None)
        mock_cjapy.CJA.return_value = MagicMock()
        ids, _ = resolve_data_view_names(["My DV"])
        assert ids == []

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_insensitive_no_match(self, mock_config, mock_cjapy) -> None:
        """Lines 8346-8347: insensitive mode error message."""
        from cja_auto_sdr.generator import resolve_data_view_names

        mock_config.return_value = (True, "file", None)
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [{"id": "dv_1", "name": "Other DV"}]
        mock_cjapy.CJA.return_value = mock_cja
        ids, _ = resolve_data_view_names(["nonexistent"], match_mode="insensitive")
        assert len(ids) == 0

    @patch("cja_auto_sdr.generator.cjapy")
    @patch("cja_auto_sdr.generator.configure_cjapy")
    def test_multiple_ids_for_name(self, mock_config, mock_cjapy) -> None:
        """Lines 8329-8330: multiple data views with same name."""
        from cja_auto_sdr.generator import resolve_data_view_names

        mock_config.return_value = (True, "file", None)
        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [
            {"id": "dv_1", "name": "My DV"},
            {"id": "dv_2", "name": "My DV"},
        ]
        mock_cjapy.CJA.return_value = mock_cja
        ids, name_map = resolve_data_view_names(["My DV"], match_mode="exact")
        assert len(ids) == 2
        assert len(name_map["My DV"]) == 2


# ---------------------------------------------------------------------------
# 5. prompt_for_selection — lines 8165-8205
# ---------------------------------------------------------------------------


class TestPromptForSelection:
    """Lines 8177-8205: interactive selection, non-TTY, cancel, input."""

    def test_non_tty_returns_none(self) -> None:
        from cja_auto_sdr.generator import prompt_for_selection

        with patch("sys.stdin") as mock_stdin:
            mock_stdin.isatty.return_value = False
            result = prompt_for_selection([("dv_1", "DV 1")], "Select:")
        assert result is None

    @patch("sys.stdin")
    @patch("builtins.input", return_value="1")
    def test_valid_selection(self, _mock_input, mock_stdin) -> None:
        from cja_auto_sdr.generator import prompt_for_selection

        mock_stdin.isatty.return_value = True
        result = prompt_for_selection([("dv_1", "DV 1"), ("dv_2", "DV 2")], "Select:")
        assert result == "dv_1"

    @patch("sys.stdin")
    @patch("builtins.input", return_value="0")
    def test_cancel_selection(self, _mock_input, mock_stdin) -> None:
        from cja_auto_sdr.generator import prompt_for_selection

        mock_stdin.isatty.return_value = True
        assert prompt_for_selection([("dv_1", "DV 1")], "Select:") is None

    @patch("sys.stdin")
    @patch("builtins.input", return_value="quit")
    def test_quit_selection(self, _mock_input, mock_stdin) -> None:
        from cja_auto_sdr.generator import prompt_for_selection

        mock_stdin.isatty.return_value = True
        assert prompt_for_selection([("dv_1", "DV 1")], "Select:") is None

    @patch("sys.stdin")
    @patch("builtins.input", side_effect=["abc", "1"])
    def test_invalid_then_valid(self, _mock_input, mock_stdin) -> None:
        """Line 8201-8202: ValueError on non-numeric input."""
        from cja_auto_sdr.generator import prompt_for_selection

        mock_stdin.isatty.return_value = True
        assert prompt_for_selection([("dv_1", "DV 1")], "Select:") == "dv_1"

    @patch("sys.stdin")
    @patch("builtins.input", side_effect=["99", "1"])
    def test_out_of_range_then_valid(self, _mock_input, mock_stdin) -> None:
        """Line 8200: out-of-range number."""
        from cja_auto_sdr.generator import prompt_for_selection

        mock_stdin.isatty.return_value = True
        assert prompt_for_selection([("dv_1", "DV 1")], "Select:") == "dv_1"

    @patch("sys.stdin")
    @patch("builtins.input", side_effect=EOFError)
    def test_eof_returns_none(self, _mock_input, mock_stdin) -> None:
        """Line 8203-8205: EOFError handler."""
        from cja_auto_sdr.generator import prompt_for_selection

        mock_stdin.isatty.return_value = True
        assert prompt_for_selection([("dv_1", "DV 1")], "Select:") is None


# ---------------------------------------------------------------------------
# 6. DataViewCache — lines 8046-8088
# ---------------------------------------------------------------------------


class TestDataViewCache:
    """Lines 8046-8088: cache hit/miss, TTL expiration."""

    def test_cache_set_and_get(self) -> None:
        from cja_auto_sdr.generator import DataViewCache

        cache = DataViewCache.__new__(DataViewCache)
        cache._initialized = False
        cache.__init__()
        cache.set("key1", [{"id": "dv1"}])
        assert cache.get("key1") == [{"id": "dv1"}]

    def test_cache_miss(self) -> None:
        from cja_auto_sdr.generator import DataViewCache

        cache = DataViewCache.__new__(DataViewCache)
        cache._initialized = False
        cache.__init__()
        assert cache.get("nonexistent") is None

    def test_cache_clear(self) -> None:
        from cja_auto_sdr.generator import DataViewCache

        cache = DataViewCache.__new__(DataViewCache)
        cache._initialized = False
        cache.__init__()
        cache.set("key1", [{"id": "dv1"}])
        cache.clear()
        assert cache.get("key1") is None

    def test_cache_ttl_expiry(self) -> None:
        """Line 8088: set_ttl then expiry."""
        import time

        from cja_auto_sdr.generator import DataViewCache

        cache = DataViewCache.__new__(DataViewCache)
        cache._initialized = False
        cache.__init__()
        cache.set_ttl(1)
        cache.set("key1", [{"id": "dv1"}])
        # Manually set timestamp to past to simulate expiry (monotonic clock)
        cache._cache["key1"] = (cache._cache["key1"][0], time.monotonic() - 2)
        assert cache.get("key1") is None

    def test_cache_ttl_hit_before_expiry(self) -> None:
        """Cache returns data when TTL has not expired."""
        from cja_auto_sdr.generator import DataViewCache

        cache = DataViewCache.__new__(DataViewCache)
        cache._initialized = False
        cache.__init__()
        cache.set_ttl(300)
        cache.set("key1", [{"id": "dv1"}])
        assert cache.get("key1") == [{"id": "dv1"}]

    def test_cache_ttl_uses_monotonic_clock(self) -> None:
        """Cache expiry is immune to wall-clock rollback."""
        import time
        from unittest.mock import patch

        from cja_auto_sdr.generator import DataViewCache

        cache = DataViewCache.__new__(DataViewCache)
        cache._initialized = False
        cache.__init__()
        cache.set_ttl(10)

        # Store with a known monotonic baseline
        mono_base = 1000.0
        with patch("cja_auto_sdr.generator.time") as mock_time:
            mock_time.monotonic.return_value = mono_base
            mock_time.perf_counter = time.perf_counter
            cache.set("key1", [{"id": "dv1"}])

        # 5 seconds later (within TTL) — should hit
        with patch("cja_auto_sdr.generator.time") as mock_time:
            mock_time.monotonic.return_value = mono_base + 5
            mock_time.perf_counter = time.perf_counter
            assert cache.get("key1") == [{"id": "dv1"}]

        # 11 seconds later (past TTL) — should miss
        with patch("cja_auto_sdr.generator.time") as mock_time:
            mock_time.monotonic.return_value = mono_base + 11
            mock_time.perf_counter = time.perf_counter
            assert cache.get("key1") is None


# ---------------------------------------------------------------------------
# 7. _format_diff_value — line 3262-3263
# ---------------------------------------------------------------------------


class TestFormatDiffValueTypeError:
    """Line 3262: pd.isna raises TypeError for unhashable types like list."""

    def test_list_value(self) -> None:
        from cja_auto_sdr.generator import _format_diff_value

        assert _format_diff_value([1, 2, 3]) == "[1, 2, 3]"

    def test_dict_value(self) -> None:
        from cja_auto_sdr.generator import _format_diff_value

        result = _format_diff_value({"key": "value"})
        assert "key" in result

    def test_none_value(self) -> None:
        from cja_auto_sdr.generator import _format_diff_value

        assert _format_diff_value(None) == "(empty)"

    def test_long_value_truncated(self) -> None:
        from cja_auto_sdr.generator import _format_diff_value

        long_str = "x" * 200
        result = _format_diff_value(long_str, truncate=True)
        assert len(result) <= 100


# ---------------------------------------------------------------------------
# 8. _safe_env_number — line 6707
# ---------------------------------------------------------------------------


class TestSafeEnvNumber:
    """Line 6707: except TypeError, ValueError fallback."""

    def test_valid_int(self) -> None:
        from cja_auto_sdr.generator import _safe_env_number

        with patch.dict("os.environ", {"TEST_VAR": "42"}):
            assert _safe_env_number("TEST_VAR", 10, int) == 42

    def test_invalid_value_returns_default(self) -> None:
        from cja_auto_sdr.generator import _safe_env_number

        with patch.dict("os.environ", {"TEST_VAR": "not_a_number"}):
            assert _safe_env_number("TEST_VAR", 10, int) == 10

    def test_missing_env_var_returns_default(self) -> None:
        from cja_auto_sdr.generator import _safe_env_number

        with patch.dict("os.environ", {}, clear=True):
            assert _safe_env_number("MISSING_VAR", 99, int) == 99


# ---------------------------------------------------------------------------
# 9. levenshtein_distance + find_similar_names — lines 7947-7977
# ---------------------------------------------------------------------------


class TestLevenshteinDistance:
    def test_identical_strings(self) -> None:
        from cja_auto_sdr.generator import levenshtein_distance

        assert levenshtein_distance("abc", "abc") == 0

    def test_empty_string(self) -> None:
        from cja_auto_sdr.generator import levenshtein_distance

        assert levenshtein_distance("", "abc") == 3

    def test_single_substitution(self) -> None:
        from cja_auto_sdr.generator import levenshtein_distance

        assert levenshtein_distance("abc", "axc") == 1

    def test_different_strings(self) -> None:
        from cja_auto_sdr.generator import levenshtein_distance

        assert levenshtein_distance("kitten", "sitting") == 3


class TestFindSimilarNames:
    def test_find_close_match(self) -> None:
        from cja_auto_sdr.generator import find_similar_names

        names = ["Production DV", "Staging DV", "Dev DV"]
        similar = find_similar_names("Productin DV", names)
        assert len(similar) > 0
        assert similar[0][0] == "Production DV"


# ---------------------------------------------------------------------------
# 10. is_data_view_id — line 7934
# ---------------------------------------------------------------------------


class TestIsDataViewId:
    def test_valid_id(self) -> None:
        from cja_auto_sdr.generator import is_data_view_id

        assert is_data_view_id("dv_abc123") is True

    def test_name_not_id(self) -> None:
        from cja_auto_sdr.generator import is_data_view_id

        assert is_data_view_id("My Data View") is False

    def test_empty_string(self) -> None:
        from cja_auto_sdr.generator import is_data_view_id

        assert is_data_view_id("") is False
