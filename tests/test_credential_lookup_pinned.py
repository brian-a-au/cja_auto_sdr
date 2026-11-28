"""Pin which credential the lookup returns for the main combinations of sources.

These tests were written against v3.13.13, before the work for the Adobe
credentials standard. They must give the same result before and after that
work, so they prove that the lookup result did not change.

Every test runs in a temporary home and working folder with the credential
variables cleared. No test calls Adobe.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from cja_auto_sdr.api import client as api_client

# The made-up credentials of the shared cases (fixtures.json). None of them is real.
CRED_A = {
    "org_id": "A1B2C3D4E5F6A7B8C9D0E1F2@AdobeOrg",
    "client_id": "aaaa1111bbbb2222cccc3333dddd4444",
    "secret": "fake-secret-A-not-a-credential-0001",
    "scopes": "openid,AdobeID,additional_info.projectedProductContext",
}
CRED_B = {
    "org_id": "B9B8B7B6B5B4B3B2B1B0BABB@AdobeOrg",
    "client_id": "bbbb5555cccc6666dddd7777eeee8888",
    "secret": "fake-secret-B-not-a-credential-0002",
    "scopes": "openid,AdobeID,read_organizations",
}
ENV_NAMES = {"org_id": "ORG_ID", "client_id": "CLIENT_ID", "secret": "SECRET", "scopes": "SCOPES"}
ALL_VARIABLES = ("ORG_ID", "CLIENT_ID", "SECRET", "SCOPES", "SANDBOX", "CJA_PROFILE", "CJA_HOME")


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """A temporary working folder inside a temporary home, with no credential variable set.

    monkeypatch.delenv records each variable, so a value that python-dotenv loads
    during the test is removed again when the test ends.
    """
    home = tmp_path / "home"
    work = home / "projects" / "work"
    work.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    for name in ALL_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(work)
    return work


def _without(cred: dict[str, str], *fields: str) -> dict[str, str]:
    return {key: value for key, value in cred.items() if key not in fields}


def _set_env(monkeypatch, cred: dict[str, str]) -> None:
    for key, value in cred.items():
        monkeypatch.setenv(ENV_NAMES[key], value)


def _write_dotenv(folder: Path, cred: dict[str, str], extra: dict[str, str] | None = None) -> Path:
    lines = [f"{ENV_NAMES[key]}={value}" for key, value in cred.items()]
    lines += [f"{key}={value}" for key, value in (extra or {}).items()]
    path = folder / ".env"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _write_config(path: Path, cred: dict[str, str]) -> Path:
    path.write_text(json.dumps(cred), encoding="utf-8")
    return path


def _write_profile(name: str, cred: dict[str, str], dotenv: dict[str, str] | None = None) -> Path:
    folder = Path.home() / ".cja" / "orgs" / name
    folder.mkdir(parents=True)
    if cred:
        _write_config(folder / "config.json", cred)
    if dotenv:
        _write_dotenv(folder, dotenv)
    return folder


def _lookup(profile: str | None = None, config_file: str = "config.json"):
    """Run the real lookup. Returns (success, source text, credential or None)."""
    logger = logging.getLogger("test_credential_lookup_pinned")
    with patch.object(api_client.cjapy, "configure") as configure:
        success, source, credentials = api_client.configure_cjapy(profile, config_file, logger)
    if success:
        configure.assert_called_once()
    return success, source, credentials


class TestProfileFirst:
    def test_profile_flag_beats_environment_and_config_file(self, workdir, monkeypatch):
        _write_profile("prod", CRED_A)
        _set_env(monkeypatch, CRED_B)
        _write_config(workdir / "config.json", CRED_B)

        success, source, credentials = _lookup(profile="prod")

        assert success is True
        assert source == "Profile: prod"
        assert credentials == CRED_A

    def test_profile_variable_beats_environment_and_config_file(self, workdir, monkeypatch):
        _write_profile("prod", CRED_A)
        monkeypatch.setenv("CJA_PROFILE", "prod")
        _set_env(monkeypatch, CRED_B)
        _write_config(workdir / "config.json", CRED_B)

        success, source, credentials = _lookup()

        assert success is True
        assert source == "Profile: prod"
        assert credentials == CRED_A

    def test_profile_flag_beats_profile_variable(self, workdir, monkeypatch):
        _write_profile("prod", CRED_A)
        _write_profile("other", CRED_B)
        monkeypatch.setenv("CJA_PROFILE", "other")

        success, source, credentials = _lookup(profile="prod")

        assert success is True
        assert source == "Profile: prod"
        assert credentials == CRED_A

    def test_profile_beats_an_explicit_config_file(self, workdir):
        _write_profile("prod", CRED_A)
        explicit = _write_config(workdir / "other.json", CRED_B)

        success, source, credentials = _lookup(profile="prod", config_file=str(explicit))

        assert success is True
        assert source == "Profile: prod"
        assert credentials == CRED_A

    def test_missing_profile_fails_with_no_fall_back(self, workdir, monkeypatch):
        _set_env(monkeypatch, CRED_B)
        _write_config(workdir / "config.json", CRED_B)

        success, source, credentials = _lookup(profile="missing")

        assert success is False
        assert credentials is None
        assert "not found" in source

    def test_profile_dotenv_overrides_profile_config_json_key_by_key(self, workdir):
        _write_profile("prod", CRED_A, dotenv={"org_id": CRED_B["org_id"]})

        success, source, credentials = _lookup(profile="prod")

        assert success is True
        assert source == "Profile: prod"
        assert credentials == {**CRED_A, "org_id": CRED_B["org_id"]}

    def test_profile_without_scopes_is_returned_with_no_fall_back(self, workdir, monkeypatch):
        _write_profile("prod", _without(CRED_A, "scopes"))
        _set_env(monkeypatch, CRED_B)

        success, source, credentials = _lookup(profile="prod")

        assert success is True
        assert source == "Profile: prod"
        assert credentials == _without(CRED_A, "scopes")

    def test_profile_without_secret_fails_with_no_fall_back(self, workdir, monkeypatch):
        _write_profile("prod", _without(CRED_A, "secret"))
        _set_env(monkeypatch, CRED_B)

        success, _source, credentials = _lookup(profile="prod")

        assert success is False
        assert credentials is None


class TestEnvironmentSecond:
    def test_environment_beats_default_config_file(self, workdir, monkeypatch):
        _set_env(monkeypatch, CRED_A)
        _write_config(workdir / "config.json", CRED_B)

        success, source, credentials = _lookup()

        assert success is True
        assert source == "Environment variables"
        assert credentials == CRED_A

    def test_environment_beats_an_explicit_config_file(self, workdir, monkeypatch):
        _set_env(monkeypatch, CRED_A)
        explicit = _write_config(workdir / "other.json", CRED_B)

        success, source, credentials = _lookup(config_file=str(explicit))

        assert success is True
        assert source == "Environment variables"
        assert credentials == CRED_A

    def test_environment_without_secret_is_skipped_for_the_config_file(self, workdir, monkeypatch):
        _set_env(monkeypatch, _without(CRED_A, "secret"))
        _write_config(workdir / "config.json", CRED_B)

        success, source, credentials = _lookup()

        assert success is True
        assert source.startswith("Config file: ")
        assert credentials == CRED_B

    def test_environment_without_secret_and_scopes_is_skipped_for_the_config_file(self, workdir, monkeypatch):
        _set_env(monkeypatch, _without(CRED_A, "secret", "scopes"))
        _write_config(workdir / "config.json", CRED_B)

        success, source, credentials = _lookup()

        assert success is True
        assert source.startswith("Config file: ")
        assert credentials == CRED_B

    def test_environment_without_scopes_is_used_whole(self, workdir, monkeypatch):
        _set_env(monkeypatch, _without(CRED_A, "scopes"))
        _write_config(workdir / "config.json", CRED_B)

        success, source, credentials = _lookup()

        assert success is True
        assert source == "Environment variables"
        assert credentials == _without(CRED_A, "scopes")

    def test_environment_with_a_short_client_id_is_skipped_for_the_config_file(self, workdir, monkeypatch):
        _set_env(monkeypatch, {**CRED_A, "client_id": "short"})
        _write_config(workdir / "config.json", CRED_B)

        success, source, credentials = _lookup()

        assert success is True
        assert source.startswith("Config file: ")
        assert credentials == CRED_B


class TestConfigFileLast:
    def test_default_config_file_alone(self, workdir):
        _write_config(workdir / "config.json", CRED_A)

        success, source, credentials = _lookup()

        assert success is True
        assert source == f"Config file: {(workdir / 'config.json').resolve()}"
        assert credentials == CRED_A

    def test_explicit_config_file_alone(self, workdir):
        explicit = _write_config(workdir / "other.json", CRED_A)
        _write_config(workdir / "config.json", CRED_B)

        success, source, credentials = _lookup(config_file=str(explicit))

        assert success is True
        assert source == f"Config file: {explicit.resolve()}"
        assert credentials == CRED_A

    def test_config_file_without_scopes_is_returned(self, workdir):
        _write_config(workdir / "config.json", _without(CRED_A, "scopes"))

        success, _source, credentials = _lookup()

        assert success is True
        assert credentials == _without(CRED_A, "scopes")

    def test_config_file_without_secret_fails(self, workdir):
        _write_config(workdir / "config.json", _without(CRED_A, "secret"))

        success, _source, credentials = _lookup()

        assert success is False
        assert credentials is None

    def test_nothing_set_fails(self, workdir):
        success, source, credentials = _lookup()

        assert success is False
        assert credentials is None
        assert "No valid credentials found" in source


class TestDotenvWithPythonDotenv:
    """What .env does when python-dotenv is installed."""

    @pytest.fixture(autouse=True)
    def _needs_python_dotenv(self):
        pytest.importorskip("dotenv")

    def test_dotenv_in_working_folder_beats_config_file(self, workdir):
        _write_dotenv(workdir, CRED_A)
        _write_config(workdir / "config.json", CRED_B)

        success, source, credentials = _lookup()

        assert success is True
        assert source == "Environment variables"
        assert credentials == CRED_A

    def test_dotenv_in_a_parent_folder_is_read(self, workdir):
        _write_dotenv(workdir.parent, CRED_A)
        _write_config(workdir / "config.json", CRED_B)

        success, source, credentials = _lookup()

        assert success is True
        assert source == "Environment variables"
        assert credentials == CRED_A

    def test_nearest_dotenv_wins_over_one_in_a_parent_folder(self, workdir):
        _write_dotenv(workdir, CRED_A)
        _write_dotenv(workdir.parent, CRED_B)

        success, _source, credentials = _lookup()

        assert success is True
        assert credentials == CRED_A

    def test_environment_variables_beat_dotenv(self, workdir, monkeypatch):
        _set_env(monkeypatch, CRED_A)
        _write_dotenv(workdir, CRED_B)
        _write_config(workdir / "config.json", CRED_B)

        success, source, credentials = _lookup()

        assert success is True
        assert source == "Environment variables"
        assert credentials == CRED_A

    def test_dotenv_fills_the_fields_the_environment_lacks(self, workdir, monkeypatch):
        _set_env(monkeypatch, _without(CRED_A, "secret", "scopes"))
        _write_dotenv(workdir, CRED_B)
        _write_config(workdir / "config.json", CRED_B)

        success, source, credentials = _lookup()

        assert success is True
        assert source == "Environment variables"
        assert credentials == {**CRED_B, "org_id": CRED_A["org_id"], "client_id": CRED_A["client_id"]}

    def test_dotenv_can_set_the_profile_variable(self, workdir):
        _write_profile("other", CRED_B)
        _write_dotenv(workdir, CRED_A, extra={"CJA_PROFILE": "other"})

        success, source, credentials = _lookup()

        assert success is True
        assert source == "Profile: other"
        assert credentials == CRED_B

    def test_partial_dotenv_is_skipped_for_the_config_file(self, workdir):
        _write_dotenv(workdir, _without(CRED_A, "org_id"))
        _write_config(workdir / "config.json", CRED_B)

        success, source, credentials = _lookup()

        assert success is True
        assert source.startswith("Config file: ")
        assert credentials == CRED_B

    def test_profile_beats_dotenv(self, workdir):
        _write_profile("prod", CRED_A)
        _write_dotenv(workdir, CRED_B)

        success, source, credentials = _lookup(profile="prod")

        assert success is True
        assert source == "Profile: prod"
        assert credentials == CRED_A


class TestDotenvWithoutPythonDotenv:
    """What .env did in v3.13.13 for an install without python-dotenv: nothing."""

    def test_dotenv_is_not_read_when_python_dotenv_cannot_be_imported(self, workdir, monkeypatch):
        monkeypatch.setitem(sys.modules, "dotenv", None)
        _write_dotenv(workdir, CRED_A)
        _write_config(workdir / "config.json", CRED_B)

        success, source, credentials = _lookup()

        assert success is True
        assert source.startswith("Config file: ")
        assert credentials == CRED_B
