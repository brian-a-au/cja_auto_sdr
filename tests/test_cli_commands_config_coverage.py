"""Edge-case coverage tests for cja_auto_sdr.cli.commands.config.

Targets lines missed at 94% coverage:
  63-65   generate_sample_config: OSError/PermissionError on file write
  78-80   _read_config_status_file: TypeError/ValueError on json.load
  222-223 _resolve_output_dir_path: OSError/RuntimeError/ValueError fallback
  246     _check_output_dir_access: no_existing_parent sentinel return
  284-285 display_credentials (inner): missing required field output
  295-296 display_credentials (inner): missing-required-fields summary + False return
  315-316 validate_config_only: non-Darwin platform label
  339     validate_config_only: optional pkg metadata found and printed
  365     validate_config_only: profile credentials fail display_credentials check
  408     validate_config_only: file-based credentials fail display_credentials check
  456-458 validate_config_only: KeyboardInterrupt/SystemExit re-raised
  483     validate_config_only: parent_not_directory output message
  490     validate_config_only: parent_not_writable output message
  496     validate_config_only: no_existing_parent output message
"""

from __future__ import annotations

import importlib.metadata
import json
import logging
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_generator_mock(
    *,
    banner_width: int = 60,
    platform_system: str = "Linux",
    platform_release: str = "5.15.0",
    sys_platform: str = "linux",
    python_version_info: tuple = (3, 14, 0),
    recoverable_exceptions=None,
    config_error_cls=None,
    profile_not_found_cls=None,
    profile_config_error_cls=None,
):
    """Return a minimal mock of the generator module used inside config.py."""
    gen = MagicMock()
    gen.BANNER_WIDTH = banner_width

    # ConsoleColors helpers
    gen.ConsoleColors.error = lambda msg: f"ERROR:{msg}"
    gen.ConsoleColors.success = lambda msg: f"OK:{msg}"
    gen.ConsoleColors.info = lambda msg: f"INFO:{msg}"
    gen.ConsoleColors.warning = lambda msg: f"WARN:{msg}"

    # sys / platform
    vi = MagicMock()
    vi.major, vi.minor, vi.micro = python_version_info
    vi.__ge__ = lambda self, other: (self.major, self.minor, self.micro) >= other
    gen.sys.version_info = vi
    gen.sys.platform = sys_platform
    gen.platform.system.return_value = platform_system
    gen.platform.release.return_value = platform_release
    gen.platform.mac_ver.return_value = ("", ("", "", ""), "")

    # Exception classes
    class _ConfigError(Exception):
        pass

    class _ProfileNotFound(Exception):
        pass

    class _ProfileConfigError(Exception):
        pass

    gen.ConfigurationError = config_error_cls or _ConfigError
    gen.ProfileNotFoundError = profile_not_found_cls or _ProfileNotFound
    gen.ProfileConfigError = profile_config_error_cls or _ProfileConfigError

    # RECOVERABLE_CONFIG_API_EXCEPTIONS
    gen.RECOVERABLE_CONFIG_API_EXCEPTIONS = recoverable_exceptions or (IOError,)

    # _CORE_DEPENDENCIES — empty list keeps step [2/5] trivial
    gen._CORE_DEPENDENCIES = []

    # env credentials helpers
    gen.load_credentials_from_env.return_value = None
    gen.validate_env_credentials.return_value = False

    # profile helpers
    gen.load_profile_credentials.return_value = None

    # _config_from_env, cjapy stubs
    gen.cjapy = MagicMock()
    gen._config_from_env = MagicMock()

    return gen


# ---------------------------------------------------------------------------
# generate_sample_config — L63-65: OSError / PermissionError on write
# ---------------------------------------------------------------------------


class TestGenerateSampleConfigIOError:
    """Lines 63-65: permission/OS failure during file write."""

    def test_permission_error_returns_false(self, capsys):
        from cja_auto_sdr.cli.commands.config import generate_sample_config

        with patch("builtins.open", side_effect=PermissionError("read-only filesystem")):
            with patch("cja_auto_sdr.cli.commands.config._generator_module") as mock_mod:
                gen = _make_generator_mock()
                mock_mod.return_value = gen
                result = generate_sample_config("config.sample.json")

        assert result is False
        captured = capsys.readouterr()
        assert "read-only filesystem" in captured.out

    def test_os_error_returns_false(self, capsys):
        from cja_auto_sdr.cli.commands.config import generate_sample_config

        with patch("builtins.open", side_effect=OSError("disk full")):
            with patch("cja_auto_sdr.cli.commands.config._generator_module") as mock_mod:
                gen = _make_generator_mock()
                mock_mod.return_value = gen
                result = generate_sample_config("config.sample.json")

        assert result is False
        captured = capsys.readouterr()
        assert "disk full" in captured.out


# ---------------------------------------------------------------------------
# _read_config_status_file — L78-80: TypeError / ValueError on json.load
# ---------------------------------------------------------------------------


class TestReadConfigStatusFileUnexpectedErrors:
    """Lines 78-80: TypeError/ValueError from json.load are caught and returned as error message."""

    def _call(self, exc):
        from cja_auto_sdr.cli.commands.config import _read_config_status_file

        logger = logging.getLogger("test")
        with patch("builtins.open", MagicMock()):
            with patch("json.load", side_effect=exc):
                return _read_config_status_file("myconfig.json", logger)

    def test_type_error_returns_controlled_message(self):
        payload, err = self._call(TypeError("bad type"))
        assert payload is None
        assert err is not None
        assert "myconfig.json" in err
        assert "bad type" in err

    def test_value_error_returns_controlled_message(self):
        payload, err = self._call(ValueError("encoding issue"))
        assert payload is None
        assert err is not None
        assert "encoding issue" in err


# ---------------------------------------------------------------------------
# _resolve_output_dir_path — L222-223: OSError/RuntimeError/ValueError fallback
# ---------------------------------------------------------------------------


class TestResolveOutputDirPathFallback:
    """Lines 222-223: resolve(strict=False) raises, so abspath fallback is used."""

    def test_oserror_falls_back_to_abspath(self, tmp_path):
        from cja_auto_sdr.cli.commands.config import _resolve_output_dir_path

        target = str(tmp_path / "subdir")
        with patch("pathlib.Path.resolve", side_effect=OSError("resolve failed")):
            result = _resolve_output_dir_path(target)
        # Result should be a Path that contains the subdir name
        assert isinstance(result, Path)
        assert "subdir" in str(result)

    def test_runtime_error_falls_back_to_abspath(self, tmp_path):
        from cja_auto_sdr.cli.commands.config import _resolve_output_dir_path

        target = str(tmp_path / "subdir2")
        with patch("pathlib.Path.resolve", side_effect=RuntimeError("loop")):
            result = _resolve_output_dir_path(target)
        assert isinstance(result, Path)

    def test_value_error_falls_back_to_abspath(self, tmp_path):
        from cja_auto_sdr.cli.commands.config import _resolve_output_dir_path

        target = str(tmp_path / "subdir3")
        with patch("pathlib.Path.resolve", side_effect=ValueError("bad path")):
            result = _resolve_output_dir_path(target)
        assert isinstance(result, Path)


# ---------------------------------------------------------------------------
# _check_output_dir_access — L246: no_existing_parent
# ---------------------------------------------------------------------------


class TestCheckOutputDirAccessNoExistingParent:
    """Line 246: all parents iterated without finding an existing one."""

    def test_no_existing_parent_returns_sentinel(self, tmp_path):
        from cja_auto_sdr.cli.commands.config import _check_output_dir_access

        # Construct a deep path under a non-existing root so all parents are missing
        non_existing_root = tmp_path / "ghost" / "deep" / "path" / "target"

        # Patch .exists() to always return False for all paths
        with patch("pathlib.Path.exists", return_value=False):
            ok, _resolved, reason, parent = _check_output_dir_access(str(non_existing_root))

        assert ok is False
        assert reason == "no_existing_parent"
        assert parent is None


# ---------------------------------------------------------------------------
# validate_config_only — display_credentials inner helper: L284-285, L295-296
# These are exercised by calling validate_config_only with a profile that has
# missing required credentials.
# ---------------------------------------------------------------------------


class TestValidateConfigDisplayCredentialsMissingRequired:
    """Lines 284-285 and 295-296: display_credentials shows missing fields and returns False."""

    def _run(self, profile_creds, capsys):
        from cja_auto_sdr.cli.commands.config import validate_config_only

        gen = _make_generator_mock(python_version_info=(3, 14, 0))
        # Make load_profile_credentials return creds missing required fields
        gen.load_profile_credentials.return_value = profile_creds

        with patch("cja_auto_sdr.cli.commands.config._generator_module", return_value=gen):
            with patch("cja_auto_sdr.cli.commands.config._check_output_dir_access"):
                result = validate_config_only(profile="myprofile")

        return result, capsys.readouterr()

    def test_missing_org_id_shows_error_line_and_returns_false(self, capsys):
        # org_id missing
        creds = {"client_id": "cid_12345678", "secret": "sec_12345678", "scopes": "openid"}
        result, captured = self._run(creds, capsys)
        assert result is False
        # The "not set (required)" line should appear (line 284-285)
        assert "org_id" in captured.out
        assert "not set (required)" in captured.out
        # Summary line with "Missing required fields" (line 295)
        assert "Missing required fields" in captured.out

    def test_all_required_missing_returns_false(self, capsys):
        # Provide sandbox only — none of the required fields present
        creds = {"sandbox": "prod"}
        result, captured = self._run(creds, capsys)
        assert result is False
        assert "Missing required fields" in captured.out


# ---------------------------------------------------------------------------
# validate_config_only — L315-316: non-Darwin platform_system fallback
# ---------------------------------------------------------------------------


class TestValidateConfigPlatformNonDarwin:
    """Lines 315-316: non-Darwin, non-empty platform_system uses generic label."""

    def test_linux_platform_label(self, capsys):
        from cja_auto_sdr.cli.commands.config import validate_config_only

        gen = _make_generator_mock(
            platform_system="Linux",
            platform_release="5.15.0",
            sys_platform="linux",
            python_version_info=(3, 14, 0),
        )
        # Make credentials available so we skip further checks
        gen.load_credentials_from_env.return_value = {
            "org_id": "org@AdobeOrg",
            "client_id": "cid12345678",
            "secret": "sec12345678",
            "scopes": "openid",
        }
        gen.validate_env_credentials.return_value = True

        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = []
        gen.cjapy.CJA.return_value = mock_cja

        with patch("cja_auto_sdr.cli.commands.config._generator_module", return_value=gen):
            with patch(
                "cja_auto_sdr.cli.commands.config._check_output_dir_access",
                return_value=(True, Path("."), "writable", None),
            ):
                validate_config_only()

        captured = capsys.readouterr()
        assert "Linux" in captured.out
        assert "5.15.0" in captured.out

    def test_windows_platform_label(self, capsys):
        from cja_auto_sdr.cli.commands.config import validate_config_only

        gen = _make_generator_mock(
            platform_system="Windows",
            platform_release="10",
            sys_platform="win32",
            python_version_info=(3, 14, 0),
        )
        gen.load_credentials_from_env.return_value = {
            "org_id": "org@AdobeOrg",
            "client_id": "cid12345678",
            "secret": "sec12345678",
            "scopes": "openid",
        }
        gen.validate_env_credentials.return_value = True

        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = []
        gen.cjapy.CJA.return_value = mock_cja

        with patch("cja_auto_sdr.cli.commands.config._generator_module", return_value=gen):
            with patch(
                "cja_auto_sdr.cli.commands.config._check_output_dir_access",
                return_value=(True, Path("."), "writable", None),
            ):
                validate_config_only()

        captured = capsys.readouterr()
        assert "Windows" in captured.out


# ---------------------------------------------------------------------------
# validate_config_only — L339: optional package found/printed
# ---------------------------------------------------------------------------


class TestValidateConfigOptionalPackageFound:
    """Line 339: optional package metadata found — printed as available."""

    def test_optional_package_version_printed(self, capsys):
        from cja_auto_sdr.cli.commands.config import validate_config_only

        gen = _make_generator_mock(python_version_info=(3, 14, 0))
        gen._CORE_DEPENDENCIES = []

        gen.load_credentials_from_env.return_value = {
            "org_id": "org@AdobeOrg",
            "client_id": "cid12345678",
            "secret": "sec12345678",
            "scopes": "openid",
        }
        gen.validate_env_credentials.return_value = True

        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = []
        gen.cjapy.CJA.return_value = mock_cja

        # scipy is present with a real version string
        def mock_version(pkg):
            if pkg == "scipy":
                return "1.11.0"
            raise importlib.metadata.PackageNotFoundError(pkg)

        with patch("cja_auto_sdr.cli.commands.config._generator_module", return_value=gen):
            with patch("importlib.metadata.version", side_effect=mock_version):
                with patch(
                    "cja_auto_sdr.cli.commands.config._check_output_dir_access",
                    return_value=(True, Path("."), "writable", None),
                ):
                    validate_config_only()

        captured = capsys.readouterr()
        assert "scipy" in captured.out
        assert "1.11.0" in captured.out


# ---------------------------------------------------------------------------
# validate_config_only — L365: profile display_credentials returns False
# ---------------------------------------------------------------------------


class TestValidateConfigProfileCredentialDisplayFails:
    """Line 365: profile found but display_credentials returns False → all_passed=False."""

    def test_profile_missing_required_field_sets_all_passed_false(self, capsys):
        from cja_auto_sdr.cli.commands.config import validate_config_only

        gen = _make_generator_mock(python_version_info=(3, 14, 0))
        # Profile exists but is missing org_id (required)
        gen.load_profile_credentials.return_value = {
            "client_id": "cid12345678",
            "secret": "sec12345678",
        }

        with patch("cja_auto_sdr.cli.commands.config._generator_module", return_value=gen):
            result = validate_config_only(profile="badprofile")

        assert result is False
        captured = capsys.readouterr()
        assert "Missing required fields" in captured.out or "not set (required)" in captured.out


# ---------------------------------------------------------------------------
# validate_config_only — L408: file-based config display_credentials fails
# ---------------------------------------------------------------------------


class TestValidateConfigFileCredentialDisplayFails:
    """Line 408: config file valid JSON but missing required fields → all_passed=False."""

    def test_file_config_missing_required_field(self, tmp_path, capsys):
        from cja_auto_sdr.cli.commands.config import validate_config_only

        # Write a config file missing the required org_id
        config_path = tmp_path / "config.json"
        config_path.write_text(json.dumps({"client_id": "cid12345678", "secret": "sec12345678"}))

        gen = _make_generator_mock(python_version_info=(3, 14, 0))
        gen.load_credentials_from_env.return_value = None

        with patch("cja_auto_sdr.cli.commands.config._generator_module", return_value=gen):
            result = validate_config_only(config_file=str(config_path))

        assert result is False
        captured = capsys.readouterr()
        assert "not set (required)" in captured.out or "Missing required fields" in captured.out


# ---------------------------------------------------------------------------
# validate_config_only — L456-458: KeyboardInterrupt / SystemExit re-raised
# ---------------------------------------------------------------------------


class TestValidateConfigKeyboardInterruptRaised:
    """Lines 456-458: KeyboardInterrupt and SystemExit inside the API block are re-raised."""

    def _setup_gen_with_env_creds(self):
        gen = _make_generator_mock(python_version_info=(3, 14, 0))
        gen.load_credentials_from_env.return_value = {
            "org_id": "org@AdobeOrg",
            "client_id": "cid12345678",
            "secret": "sec12345678",
            "scopes": "openid",
        }
        gen.validate_env_credentials.return_value = True
        return gen

    def test_keyboard_interrupt_is_re_raised(self, capsys):
        from cja_auto_sdr.cli.commands.config import validate_config_only

        gen = self._setup_gen_with_env_creds()
        gen.cjapy.CJA.side_effect = KeyboardInterrupt

        with patch("cja_auto_sdr.cli.commands.config._generator_module", return_value=gen):
            with pytest.raises(KeyboardInterrupt):
                validate_config_only()

        captured = capsys.readouterr()
        assert "cancelled" in captured.out.lower()

    def test_system_exit_is_re_raised(self, capsys):
        from cja_auto_sdr.cli.commands.config import validate_config_only

        gen = self._setup_gen_with_env_creds()
        gen.cjapy.CJA.side_effect = SystemExit(2)

        with patch("cja_auto_sdr.cli.commands.config._generator_module", return_value=gen):
            with pytest.raises(SystemExit) as exc_info:
                validate_config_only()

        assert exc_info.value.code == 2


# ---------------------------------------------------------------------------
# validate_config_only — L483, L490, L496: output dir error messages
# These are reached when all_passed=True after API check, but output dir fails.
# ---------------------------------------------------------------------------


def _run_validate_with_output_dir_result(gen, access_result, capsys):
    """Helper: run validate_config_only with mocked output dir result."""
    from cja_auto_sdr.cli.commands.config import validate_config_only

    gen.load_credentials_from_env.return_value = {
        "org_id": "org@AdobeOrg",
        "client_id": "cid12345678",
        "secret": "sec12345678",
        "scopes": "openid",
    }
    gen.validate_env_credentials.return_value = True
    mock_cja = MagicMock()
    mock_cja.getDataViews.return_value = []
    gen.cjapy.CJA.return_value = mock_cja

    with patch("cja_auto_sdr.cli.commands.config._generator_module", return_value=gen):
        with patch(
            "cja_auto_sdr.cli.commands.config._check_output_dir_access",
            return_value=access_result,
        ):
            result = validate_config_only(output_dir="/some/output/dir")

    return result, capsys.readouterr()


class TestValidateConfigOutputDirErrorMessages:
    """Lines 483, 490, 496: parent_not_directory, parent_not_writable, no_existing_parent messages."""

    def test_parent_not_directory_message(self, capsys):
        gen = _make_generator_mock(python_version_info=(3, 14, 0))
        parent = Path("/some/file.txt")
        resolved = Path("/some/file.txt/output")
        access = (False, resolved, "parent_not_directory", parent)

        result, captured = _run_validate_with_output_dir_result(gen, access, capsys)

        assert result is False
        assert "path component is not a directory" in captured.out
        assert str(parent) in captured.out

    def test_parent_not_writable_message(self, capsys):
        gen = _make_generator_mock(python_version_info=(3, 14, 0))
        parent = Path("/read-only-dir")
        resolved = Path("/read-only-dir/output")
        access = (False, resolved, "parent_not_writable", parent)

        result, captured = _run_validate_with_output_dir_result(gen, access, capsys)

        assert result is False
        assert "parent not writable" in captured.out
        assert str(parent) in captured.out

    def test_no_existing_parent_message(self, capsys):
        gen = _make_generator_mock(python_version_info=(3, 14, 0))
        resolved = Path("/ghost/deep/output")
        access = (False, resolved, "no_existing_parent", None)

        result, captured = _run_validate_with_output_dir_result(gen, access, capsys)

        assert result is False
        assert "Cannot determine writable parent" in captured.out
