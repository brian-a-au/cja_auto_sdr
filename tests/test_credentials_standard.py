"""Tests for the work on the Adobe credentials standard, version 1.

They cover the client ID mask, the notice and warning lines, the file modes,
the sign-in request, the config check (``--show-config``) and the live test
(``--profile-test``). Every test runs in a temporary home and working folder.
No test calls Adobe.
"""

from __future__ import annotations

import json
import logging
import os
import stat
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from cja_auto_sdr import generator
from cja_auto_sdr.api import client as api_client
from cja_auto_sdr.api import sign_in
from cja_auto_sdr.cli.commands import show_config as show_config_module
from cja_auto_sdr.cli.commands.show_config import build_config_check, render_config_check
from cja_auto_sdr.core import credential_notices, profiles
from cja_auto_sdr.core.credential_notices import (
    DotenvSnapshot,
    dotenv_snapshot,
    emit_notice,
    emit_warning,
    environment_field_origins,
    make_private_dirs,
    mask_client_id,
    note_file_keys,
    readable_by_others,
    record_dotenv_load,
    reset_credential_notice_state,
    warn_if_readable_by_others,
)
from cja_auto_sdr.core.credentials import CredentialResolver, dotenv_and_config_differ
from tests.test_standard_cases import assert_matches_schema, run_cli

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
posix_only = pytest.mark.skipif(os.name == "nt", reason="File modes do not describe access on Windows")


@pytest.fixture
def workdir(tmp_path, monkeypatch):
    """A temporary working folder inside a temporary home."""
    home = tmp_path / "home"
    work = home / "projects" / "work"
    work.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.chdir(work)
    return work


def _without(cred: dict[str, str], *fields: str) -> dict[str, str]:
    return {key: value for key, value in cred.items() if key not in fields}


def _set_env(monkeypatch, cred: dict[str, str]) -> None:
    for key, value in cred.items():
        monkeypatch.setenv(ENV_NAMES[key], value)


def _write_private(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)
    return path


def _write_config(path: Path, payload: dict) -> Path:
    return _write_private(path, json.dumps(payload))


def _write_dotenv(folder: Path, cred: dict[str, str], extra: str = "") -> Path:
    lines = [f"{ENV_NAMES[key]}={value}" for key, value in cred.items()]
    return _write_private(folder / ".env", "\n".join(lines) + "\n" + extra)


def _profile_folder(name: str) -> Path:
    return Path.home() / ".cja" / "orgs" / name


def _lookup(profile: str | None = None, config_file: str = "config.json"):
    with patch.object(api_client.cjapy, "configure"):
        return api_client.configure_cjapy(profile, config_file, logging.getLogger("test_credentials_standard"))


def _codes(items: list[dict]) -> list[str]:
    return [item["code"] for item in items]


# ==================== THE CLIENT ID MASK ====================


class TestMaskClientId:
    @pytest.mark.parametrize(
        ("client_id", "shown"),
        [
            ("aaaa1111bbbb2222cccc3333dddd4444", "aaaa****4444"),
            ("abcdefghi", "abcd****fghi"),
            ("abcdefgh", "****"),
            ("a", "****"),
            ("", "****"),
            (None, "****"),
            (12345678901234, "****"),
        ],
    )
    def test_mask(self, client_id, shown):
        assert mask_client_id(client_id) == shown

    def test_every_command_shows_the_client_id_the_same_way(self, workdir, capsys):
        _write_config(_profile_folder("prod") / "config.json", CRED_A)
        _write_config(workdir / "config.json", CRED_A)

        assert profiles.show_profile("prod") is True
        assert generator.show_config_status("config.json") is True
        assert generator.show_config("config.json") is True
        output = capsys.readouterr().out

        assert output.count("aaaa****4444") == 3
        assert CRED_A["client_id"] not in output
        assert "aaaa" + "*" * 24 not in output

    def test_config_json_shows_the_fixed_mask(self, workdir, capsys):
        _write_config(workdir / "config.json", CRED_A)

        assert generator.show_config_status("config.json", output_json=True) is True
        status = json.loads(capsys.readouterr().out)

        assert status["credentials"]["client_id"]["value"] == "aaaa****4444"
        assert status["credentials"]["secret"]["value"] == "****"
        assert set(status) == {"source", "source_type", "profile", "config_file", "credentials", "valid"}

    def test_mask_sensitive_value_keeps_its_behaviour(self):
        assert profiles.mask_sensitive_value("abcdefghijkl") == "abcd****ijkl"
        assert profiles.mask_sensitive_value("abcdefghijklmnop") == "abcd********mnop"
        assert profiles.mask_sensitive_value("short") == "*****"
        assert profiles.mask_sensitive_value("") == "(empty)"


# ==================== NOTICE AND WARNING LINES ====================


class TestMessageLines:
    def test_a_notice_is_one_line_on_stderr_and_is_shown_once(self, capsys):
        assert emit_notice("mixed_sources", "The message.") is True
        assert emit_notice("mixed_sources", "The message.") is False

        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err == "Notice [mixed_sources]: The message.\n"

    def test_a_different_key_is_shown_again(self, capsys):
        assert emit_warning("upper_case_key", "First.", dedupe_key="a") is True
        assert emit_warning("upper_case_key", "Second.", dedupe_key="b") is True
        assert emit_warning("upper_case_key", "Third.", dedupe_key="a") is False

        assert capsys.readouterr().err == "Warning [upper_case_key]: First.\nWarning [upper_case_key]: Second.\n"

    def test_child_processes_inherit_the_lines_already_shown(self):
        emit_notice("mixed_sources", "The message.")

        assert os.environ[credential_notices.SHOWN_MESSAGES_VARIABLE]

    def test_reset_forgets_the_lines_and_the_dotenv_record(self, capsys):
        emit_notice("mixed_sources", "The message.")
        record_dotenv_load("/x/.env", {"ORG_ID"})

        reset_credential_notice_state()

        assert credential_notices._dotenv_record is None
        assert emit_notice("mixed_sources", "The message.") is True


# ==================== FILE AND FOLDER MODES ====================


@posix_only
class TestFileModes:
    def test_a_file_that_the_group_can_read_gives_one_warning(self, tmp_path, capsys):
        path = tmp_path / "config.json"
        path.write_text("{}")
        path.chmod(0o640)

        assert warn_if_readable_by_others(path) is True
        assert warn_if_readable_by_others(path) is True

        err = capsys.readouterr().err
        assert err.count("Warning [file_readable_by_others]") == 1
        assert f"chmod 600 {path}" in err

    def test_a_private_file_gives_no_warning(self, tmp_path, capsys):
        path = tmp_path / "config.json"
        path.write_text("{}")
        path.chmod(0o600)

        assert warn_if_readable_by_others(path) is False
        assert capsys.readouterr().err == ""

    def test_the_target_of_a_symlink_is_checked(self, tmp_path):
        target = tmp_path / "real.json"
        target.write_text("{}")
        target.chmod(0o644)
        link = tmp_path / "config.json"
        link.symlink_to(target)

        assert readable_by_others(link) is True

    def test_a_missing_file_gives_no_warning(self, tmp_path):
        assert readable_by_others(tmp_path / "missing.json") is False

    def test_the_check_is_skipped_on_windows(self, tmp_path, monkeypatch):
        path = tmp_path / "config.json"
        path.write_text("{}")
        path.chmod(0o644)
        monkeypatch.setattr(credential_notices, "_file_modes_apply", lambda: False)

        assert readable_by_others(path) is False

    def test_new_folders_are_private_and_existing_folders_keep_their_mode(self, tmp_path):
        existing = tmp_path / "existing"
        existing.mkdir()
        existing.chmod(0o755)

        make_private_dirs(existing / "orgs" / "prod")

        assert stat.S_IMODE(existing.stat().st_mode) == 0o755
        assert stat.S_IMODE((existing / "orgs").stat().st_mode) == 0o700
        assert stat.S_IMODE((existing / "orgs" / "prod").stat().st_mode) == 0o700

    def test_no_mode_is_set_on_windows(self, tmp_path, monkeypatch):
        monkeypatch.setattr(credential_notices, "_file_modes_apply", lambda: False)
        with patch.object(credential_notices.os, "chmod") as chmod:
            make_private_dirs(tmp_path / "orgs" / "prod")

        chmod.assert_not_called()
        assert (tmp_path / "orgs" / "prod").is_dir()

    def test_a_folder_that_exists_is_left_alone(self, tmp_path):
        folder = tmp_path / "prod"
        folder.mkdir()
        folder.chmod(0o755)

        make_private_dirs(folder)

        assert stat.S_IMODE(folder.stat().st_mode) == 0o755

    def test_profile_import_creates_private_folders_and_a_private_file(self, workdir, capsys):
        source = _write_config(workdir / "import.json", CRED_A)

        assert profiles.import_profile_non_interactive("prod", source) is True

        folder = _profile_folder("prod")
        assert stat.S_IMODE(folder.stat().st_mode) == 0o700
        assert stat.S_IMODE(folder.parent.stat().st_mode) == 0o700
        assert stat.S_IMODE((folder / "config.json").stat().st_mode) == 0o600

    def test_profile_add_creates_a_private_folder(self, workdir, capsys):
        answers = iter([CRED_A["org_id"], CRED_A["client_id"], CRED_A["scopes"]])
        with (
            patch("builtins.input", lambda _prompt="": next(answers)),
            patch("getpass.getpass", return_value=CRED_A["secret"]),
        ):
            assert profiles.add_profile_interactive("prod") is True

        assert stat.S_IMODE(_profile_folder("prod").stat().st_mode) == 0o700
        assert CRED_A["secret"] not in capsys.readouterr().out

    def test_a_readable_profile_file_warns_during_a_real_lookup(self, workdir, capsys):
        path = _write_config(_profile_folder("prod") / "config.json", CRED_A)
        path.chmod(0o644)

        success, _source, _credentials = _lookup(profile="prod")

        assert success is True
        assert capsys.readouterr().err.count("Warning [file_readable_by_others]") == 1

    def test_a_readable_config_file_warns_during_a_real_lookup(self, workdir, capsys):
        _write_config(workdir / "config.json", CRED_A).chmod(0o644)

        success, _source, _credentials = _lookup()

        assert success is True
        assert capsys.readouterr().err.count("Warning [file_readable_by_others]") == 1

    def test_a_readable_profile_dotenv_warns(self, workdir, capsys):
        _write_dotenv(_profile_folder("prod"), CRED_A).chmod(0o644)

        success, _source, _credentials = _lookup(profile="prod")

        assert success is True
        assert capsys.readouterr().err.count("Warning [file_readable_by_others]") == 1


# ==================== PROFILE NAMES ====================


class TestProfileNames:
    @pytest.mark.parametrize("name", ["prod2", "client-a.eu_west", "a.b", "a" * 64])
    def test_valid(self, name):
        assert profiles.validate_profile_name(name) == (True, None)

    @pytest.mark.parametrize("name", ["", "..", ".hidden", "../other", "a/b", "a\\b", "my profile", "a" * 65])
    def test_invalid(self, name):
        assert profiles.validate_profile_name(name)[0] is False

    def test_a_name_with_a_dot_can_be_used(self, workdir):
        _write_config(_profile_folder("client-a.eu_west") / "config.json", CRED_A)

        success, source, credentials = _lookup(profile="client-a.eu_west")

        assert success is True
        assert source == "Profile: client-a.eu_west"
        assert credentials == CRED_A


# ==================== FILE KEYS ====================


class TestFileKeys:
    def test_an_unknown_key_gives_one_debug_line_that_names_it(self, tmp_path, caplog, capsys):
        with caplog.at_level(logging.DEBUG):
            note_file_keys({**CRED_A, "note": "x"}, tmp_path / "config.json", logging.getLogger("keys"))

        lines = [record.getMessage() for record in caplog.records]
        assert lines == [f"Ignoring unknown key 'note' in {tmp_path / 'config.json'}"]
        assert capsys.readouterr().err == ""

    def test_an_upper_case_key_gives_a_warning(self, tmp_path, caplog, capsys):
        path = tmp_path / "config.json"
        with caplog.at_level(logging.DEBUG):
            note_file_keys({"ORG_ID": "x", "Client_Id": "y", 7: "z"}, path, logging.getLogger("keys"))

        err = capsys.readouterr().err
        assert err.count("Warning [upper_case_key]") == 2
        assert "holds the key ORG_ID" in err
        assert "Rename it to org_id." in err
        assert "Rename it to client_id." in err
        assert len(caplog.records) == 3

    def test_a_real_lookup_reports_the_keys_of_the_config_file(self, workdir, caplog, capsys):
        _write_config(workdir / "config.json", {**CRED_A, "note": "x", "SANDBOX": "dev"})

        with caplog.at_level(logging.DEBUG):
            success, _source, credentials = _lookup()

        assert success is True
        assert credentials == CRED_A
        assert any("Ignoring unknown key 'note'" in record.getMessage() for record in caplog.records)
        assert "Warning [upper_case_key]" in capsys.readouterr().err

    def test_a_real_lookup_reports_the_keys_of_a_profile(self, workdir, caplog, capsys):
        _write_config(_profile_folder("prod") / "config.json", {**CRED_A, "note": "x", "SCOPES": "openid"})

        with caplog.at_level(logging.DEBUG):
            success, _source, _credentials = _lookup(profile="prod")

        assert success is True
        assert any("Ignoring unknown key 'note'" in record.getMessage() for record in caplog.records)
        assert "holds the key SCOPES" in capsys.readouterr().err


# ==================== THE .ENV RECORD ====================


class TestDotenvRecord:
    def test_the_bootstrap_records_the_file_and_the_variables_it_set(self, workdir, monkeypatch):
        monkeypatch.setenv("ORG_ID", CRED_B["org_id"])
        path = _write_dotenv(workdir, CRED_A)

        api_client._bootstrap_dotenv(logging.getLogger("dotenv"))
        snapshot = dotenv_snapshot()

        assert Path(snapshot.path) == path
        assert snapshot.loaded_names == frozenset({"CLIENT_ID", "SECRET", "SCOPES"})
        assert snapshot.credential_fields() == ["org_id", "client_id", "secret", "scopes"]
        assert environment_field_origins(snapshot) == {
            "org_id": "environment",
            "client_id": "dotenv",
            "secret": "dotenv",
            "scopes": "dotenv",
        }

    def test_a_second_bootstrap_keeps_the_first_record(self, workdir):
        _write_dotenv(workdir, CRED_A)

        api_client._bootstrap_dotenv(logging.getLogger("dotenv"))
        api_client._bootstrap_dotenv(logging.getLogger("dotenv"))

        assert dotenv_snapshot().loaded_names == frozenset({"ORG_ID", "CLIENT_ID", "SECRET", "SCOPES"})

    def test_a_new_file_replaces_the_record(self):
        record_dotenv_load("/a/.env", {"ORG_ID"})
        record_dotenv_load("/b/.env", {"SECRET"})

        assert credential_notices._dotenv_record == ("/b/.env", frozenset({"SECRET"}))

    def test_without_a_record_the_values_are_compared(self, workdir, monkeypatch):
        # A worker process inherits the environment and has no record of its own.
        _write_dotenv(workdir, CRED_A)
        _set_env(monkeypatch, {**CRED_A, "org_id": CRED_B["org_id"]})

        snapshot = dotenv_snapshot()

        assert snapshot.loaded_names is None
        assert snapshot.supplied("SECRET") is True
        assert snapshot.supplied("ORG_ID") is False
        assert snapshot.supplied("SANDBOX") is False

    def test_no_file_gives_an_empty_snapshot(self, workdir):
        assert dotenv_snapshot() == DotenvSnapshot()
        assert environment_field_origins() == {}

    def test_a_disabled_python_dotenv_gives_an_empty_snapshot(self, workdir, monkeypatch):
        _write_dotenv(workdir, CRED_A)
        monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")

        assert dotenv_snapshot() == DotenvSnapshot()

    def test_a_missing_python_dotenv_gives_an_empty_snapshot(self, workdir, monkeypatch):
        _write_dotenv(workdir, CRED_A)
        monkeypatch.setitem(sys.modules, "dotenv", None)

        assert dotenv_snapshot() == DotenvSnapshot()

    def test_a_file_that_cannot_be_read_gives_an_empty_snapshot(self, workdir):
        record_dotenv_load(str(workdir / ".env"), set())
        with patch("dotenv.dotenv_values", side_effect=OSError("no access")):
            assert dotenv_snapshot() == DotenvSnapshot()

    def test_python_dotenv_is_a_required_dependency(self):
        import importlib.metadata

        requirements = importlib.metadata.requires("cja-auto-sdr") or []
        required = [item for item in requirements if item.startswith("python-dotenv") and "extra ==" not in item]
        in_extras = [item for item in requirements if item.startswith("python-dotenv") and "extra ==" in item]

        assert required
        assert any('extra == "env"' in item or "extra == 'env'" in item for item in in_extras)
        assert any('extra == "full"' in item or "extra == 'full'" in item for item in in_extras)


# ==================== NOTICES OF A REAL LOOKUP ====================


class TestLookupNotices:
    def test_a_partial_environment_is_skipped_with_the_missing_names(self, workdir, monkeypatch, capsys):
        _set_env(monkeypatch, _without(CRED_A, "secret", "scopes"))
        _write_config(workdir / "config.json", CRED_B)

        success, source, credentials = _lookup()

        assert success is True
        assert source.startswith("Config file: ")
        assert credentials == CRED_B
        captured = capsys.readouterr()
        assert captured.out == ""
        assert captured.err.count("Notice [partial_source_skipped]") == 1
        assert "Missing: SECRET, SCOPES." in captured.err
        assert "reads the config file" in captured.err
        assert "Release 4.0 will stop with an error instead." in captured.err

    def test_the_notice_is_shown_once_for_several_lookups(self, workdir, monkeypatch, capsys):
        _set_env(monkeypatch, _without(CRED_A, "secret"))
        _write_config(workdir / "config.json", CRED_B)

        _lookup()
        _lookup()

        assert capsys.readouterr().err.count("Notice [partial_source_skipped]") == 1

    def test_only_the_sandbox_variable_gives_no_notice(self, workdir, monkeypatch, capsys):
        monkeypatch.setenv("SANDBOX", "dev")
        _write_config(workdir / "config.json", CRED_B)

        success, _source, credentials = _lookup()

        assert success is True
        assert credentials == CRED_B
        assert "Notice [" not in capsys.readouterr().err

    def test_a_complete_environment_with_a_bad_value_gives_no_partial_notice(self, workdir, monkeypatch, capsys):
        _set_env(monkeypatch, {**CRED_A, "client_id": "short"})
        _write_config(workdir / "config.json", CRED_B)

        success, _source, credentials = _lookup()

        assert success is True
        assert credentials == CRED_B
        assert "Notice [partial_source_skipped]" not in capsys.readouterr().err

    def test_environment_mixed_with_dotenv_gives_a_notice(self, workdir, monkeypatch, capsys):
        _set_env(monkeypatch, _without(CRED_A, "secret", "scopes"))
        dotenv_path = _write_dotenv(workdir, _without(CRED_B, "org_id", "client_id"))

        success, source, credentials = _lookup()

        assert success is True
        assert source == "Environment variables"
        assert credentials == {**CRED_A, "secret": CRED_B["secret"], "scopes": CRED_B["scopes"]}
        err = capsys.readouterr().err
        assert err.count("Notice [mixed_sources]") == 1
        assert "(ORG_ID, CLIENT_ID)" in err
        assert f"{dotenv_path} (SECRET, SCOPES)" in err
        assert CRED_B["secret"] not in err

    def test_a_profile_that_mixes_its_two_files_gives_a_notice(self, workdir, capsys):
        folder = _profile_folder("prod")
        _write_config(folder / "config.json", CRED_A)
        _write_private(folder / ".env", f"ORG_ID={CRED_B['org_id']}\n")

        success, _source, credentials = _lookup(profile="prod")

        assert success is True
        assert credentials == {**CRED_A, "org_id": CRED_B["org_id"]}
        err = capsys.readouterr().err
        assert err.count("Notice [mixed_sources]") == 1
        assert "config.json (client_id, secret, scopes) with .env (org_id)" in err

    def test_a_profile_dotenv_that_holds_all_four_fields_gives_no_notice(self, workdir, capsys):
        folder = _profile_folder("prod")
        _write_config(folder / "config.json", CRED_A)
        _write_dotenv(folder, CRED_B)

        success, _source, credentials = _lookup(profile="prod")

        assert success is True
        assert credentials == CRED_B
        assert "Notice [" not in capsys.readouterr().err

    def test_dotenv_and_config_that_differ_give_a_notice_that_names_the_source(self, workdir, capsys):
        dotenv_path = _write_dotenv(workdir, CRED_A)
        config_path = _write_config(workdir / "config.json", CRED_B)

        success, source, credentials = _lookup()

        assert success is True
        assert source == "Environment variables"
        assert credentials == CRED_A
        err = capsys.readouterr().err
        assert err.count("Notice [dotenv_and_config_differ]") == 1
        assert f"{dotenv_path} and {config_path.resolve()} hold different credentials." in err
        assert f"This run uses the .env file ({dotenv_path})." in err

    def test_the_notice_names_the_environment_when_it_wins(self, workdir, monkeypatch, capsys):
        _set_env(monkeypatch, CRED_A)
        _write_dotenv(workdir, CRED_A)
        _write_config(workdir / "config.json", CRED_B)

        _lookup()

        assert "This run uses the environment variables." in capsys.readouterr().err

    def test_the_notice_names_a_mix_of_environment_and_dotenv(self, workdir, monkeypatch, capsys):
        monkeypatch.setenv("ORG_ID", CRED_B["org_id"])
        _write_dotenv(workdir, CRED_A)
        _write_config(workdir / "config.json", CRED_B)

        _lookup()

        assert "This run uses the environment variables together with the .env file" in capsys.readouterr().err

    def test_the_notice_names_the_profile_when_it_wins(self, workdir, capsys):
        _write_config(_profile_folder("prod") / "config.json", CRED_A)
        _write_dotenv(workdir, CRED_A)
        _write_config(workdir / "config.json", CRED_B)

        _lookup(profile="prod")

        assert "This run uses the profile prod." in capsys.readouterr().err

    def test_the_notice_names_the_config_file_when_it_wins(self, workdir, monkeypatch, capsys):
        # python-dotenv does not override a variable that is set, even to an empty value.
        monkeypatch.setenv("SECRET", " ")
        _write_dotenv(workdir, CRED_A)
        config_path = _write_config(workdir / "config.json", CRED_B)

        success, _source, credentials = _lookup()

        assert success is True
        assert credentials == CRED_B
        assert f"This run uses the config file ({config_path.resolve()})." in capsys.readouterr().err

    def test_the_same_credential_in_both_files_gives_no_notice(self, workdir, capsys):
        _write_dotenv(workdir, CRED_A)
        _write_config(
            workdir / "config.json", {**CRED_A, "scopes": "openid, AdobeID, additional_info.projectedProductContext"}
        )

        _lookup()

        assert "Notice [" not in capsys.readouterr().err

    def test_a_dotenv_in_a_parent_folder_is_compared_too(self, workdir, capsys):
        dotenv_path = _write_dotenv(workdir.parent, CRED_A)
        _write_config(workdir / "config.json", CRED_B)

        success, _source, credentials = _lookup()

        assert success is True
        assert credentials == CRED_A
        err = capsys.readouterr().err
        assert err.count("Notice [dotenv_and_config_differ]") == 1
        assert f"This run uses the .env file ({dotenv_path})." in err
        assert "Release 4.0 will read a .env file in the working folder only." in err

    def test_a_dotenv_in_the_working_folder_has_no_parent_folder_sentence(self, workdir, capsys):
        _write_dotenv(workdir, CRED_A)
        _write_config(workdir / "config.json", CRED_B)

        _lookup()

        assert "in the working folder only" not in capsys.readouterr().err

    def test_a_partial_file_gives_no_differ_notice(self, workdir):
        _write_dotenv(workdir, _without(CRED_A, "secret"))
        _write_config(workdir / "config.json", CRED_B)
        api_client._bootstrap_dotenv(logging.getLogger("dotenv"))

        assert dotenv_and_config_differ("config.json") == (False, None)

    def test_a_config_file_that_is_not_json_gives_no_differ_notice(self, workdir):
        _write_dotenv(workdir, CRED_A)
        _write_private(workdir / "config.json", "not json")
        api_client._bootstrap_dotenv(logging.getLogger("dotenv"))

        assert dotenv_and_config_differ("config.json") == (False, None)

    def test_a_failed_lookup_gives_no_differ_notice(self, workdir, capsys):
        resolver = CredentialResolver(logging.getLogger("resolver"))
        with patch.object(resolver, "_resolve", return_value=({}, "other")):
            assert resolver.resolve() == ({}, "other")
        assert capsys.readouterr().err == ""


# ==================== THE SIGN-IN REQUEST ====================


def _answer(status: int, body: object):
    return lambda _fields: (status, body)


class TestSignIn:
    def test_a_token_is_ok(self, monkeypatch):
        seen = {}

        def _post(fields):
            seen.update(fields)
            return 200, {"access_token": "stub-token", "expires_in": 86399}

        monkeypatch.setattr(sign_in, "post_token_request", _post)

        result = sign_in.request_token({**CRED_A, "scopes": "openid,AdobeID"})

        assert result == sign_in.SignInResult(True)
        assert result.as_dict() == {"ok": True, "code": None, "message": None}
        assert seen == {
            "grant_type": "client_credentials",
            "client_id": CRED_A["client_id"],
            "client_secret": CRED_A["secret"],
            "scope": "openid,AdobeID",
        }

    @pytest.mark.parametrize(
        ("status", "body", "code"),
        [
            (200, {"page": "login"}, "unreachable"),
            (200, None, "unreachable"),
            (200, {"access_token": ""}, "unreachable"),
            (400, {"error": "invalid_client", "error_description": "invalid client_id parameter"}, "bad_client_id"),
            (401, {"error": "invalid_client", "error_description": "invalid client_secret parameter"}, "bad_secret"),
            (400, {"error": "invalid_scope", "error_description": "scope is not allowed"}, "scopes_rejected"),
            (400, {"error": "unauthorized_client", "error_description": "not allowed"}, "sign_in_failed"),
            (503, None, "sign_in_failed"),
            (500, ["not", "an", "object"], "sign_in_failed"),
        ],
    )
    def test_codes(self, monkeypatch, status, body, code):
        monkeypatch.setattr(sign_in, "post_token_request", _answer(status, body))

        result = sign_in.request_token(CRED_A)

        assert result.ok is False
        assert result.code == code
        assert result.message
        assert CRED_A["secret"] not in result.message

    @pytest.mark.parametrize(
        "error",
        [requests.ConnectionError("down"), requests.Timeout("slow"), OSError("down"), TimeoutError()],
    )
    def test_a_network_error_is_unreachable(self, monkeypatch, error):
        def _post(_fields):
            raise error

        monkeypatch.setattr(sign_in, "post_token_request", _post)

        assert sign_in.request_token(CRED_A).code == "unreachable"

    def test_adobes_message_is_kept_and_cut_to_200_characters(self, monkeypatch):
        monkeypatch.setattr(
            sign_in, "post_token_request", _answer(400, {"error": "other", "error_description": "x" * 500})
        )

        assert sign_in.request_token(CRED_A).message == "x" * 200

    def test_a_secret_in_adobes_message_is_removed(self, monkeypatch):
        description = f"client_secret {CRED_A['secret']} is not valid for this client"
        monkeypatch.setattr(
            sign_in, "post_token_request", _answer(400, {"error": "other", "error_description": description})
        )

        result = sign_in.request_token(CRED_A)

        assert result.message == "client_secret **** is not valid for this client"

    def test_a_full_client_id_in_adobes_message_is_masked(self, monkeypatch):
        description = f"The client {CRED_A['client_id']} may not use this grant"
        monkeypatch.setattr(
            sign_in, "post_token_request", _answer(400, {"error": "other", "error_description": description})
        )

        result = sign_in.request_token(CRED_A)

        assert CRED_A["client_id"] not in result.message
        assert result.message == f"The client {mask_client_id(CRED_A['client_id'])} may not use this grant"

    def test_an_answer_with_no_text_names_the_error_or_the_status(self, monkeypatch):
        monkeypatch.setattr(sign_in, "post_token_request", _answer(400, {"error": "access_denied"}))
        assert sign_in.request_token(CRED_A).message == "access_denied"

        monkeypatch.setattr(sign_in, "post_token_request", _answer(502, None))
        assert sign_in.request_token(CRED_A).message == "Adobe answered HTTP 502."


class TestPostTokenRequest:
    """The one function that uses the network, run against a stubbed ``requests.post``."""

    @pytest.fixture(autouse=True)
    def _real_function(self, monkeypatch):
        # conftest blocks post_token_request for every test. Put the real one back here.
        monkeypatch.setattr(sign_in, "post_token_request", self.real)

    real = staticmethod(sign_in.post_token_request)

    def test_it_posts_a_form_to_adobes_sign_in_service(self):
        response = MagicMock(status_code=200)
        response.json.return_value = {"access_token": "stub-token"}
        with patch.object(sign_in.requests, "post", return_value=response) as post:
            status, body = sign_in.post_token_request({"grant_type": "client_credentials", "scope": "a,b"})

        assert (status, body) == (200, {"access_token": "stub-token"})
        args, kwargs = post.call_args
        assert args == ("https://ims-na1.adobelogin.com/ims/token/v3",)
        # requests encodes a dict as a form, as it does for the token request of cjapy.
        assert kwargs["data"] == {"grant_type": "client_credentials", "scope": "a,b"}
        assert kwargs["timeout"] == (10.0, 60.0)

    def test_an_answer_that_is_not_json_has_no_body(self):
        response = MagicMock(status_code=503)
        response.json.side_effect = requests.exceptions.JSONDecodeError("no json", "<html>busy</html>", 0)
        with patch.object(sign_in.requests, "post", return_value=response):
            assert sign_in.post_token_request({}) == (503, None)

    def test_the_request_uses_the_proxy_of_the_environment(self, monkeypatch):
        # cjapy signs in through requests, which reads HTTPS_PROXY. The live test must take
        # the same road, or it reports "unreachable" on a network where cjapy can sign in.
        seen = {}

        def _send(_session, request, **kwargs):
            seen["url"], seen["proxies"] = request.url, dict(kwargs["proxies"])
            raise requests.ConnectionError("stopped before any connection")

        monkeypatch.setenv("HTTPS_PROXY", "http://proxy.invalid:3128")
        monkeypatch.delenv("NO_PROXY", raising=False)
        monkeypatch.delenv("no_proxy", raising=False)
        monkeypatch.setattr(requests.Session, "send", _send)

        assert sign_in.request_token(CRED_A).code == "unreachable"
        assert seen["url"] == sign_in.IMS_SIGN_IN_URL
        assert seen["proxies"]["https"] == "http://proxy.invalid:3128"


# ==================== THE CONFIG CHECK ====================


class TestConfigCheck:
    def test_nothing_set(self, workdir):
        report = build_config_check()

        assert_matches_schema(report, "config-check-v1")
        assert report["ok"] is False
        assert report["source"] is None
        assert report["sources"] == []
        assert report["credential"] == {
            "org_id": None,
            "client_id": None,
            "secret_set": False,
            "scopes": None,
            "sandbox": None,
        }
        assert _codes(report["problems"]) == ["no_credential"]
        assert "No source gave a credential." in report["problems"][0]["message"]

    def test_a_profile_names_both_of_its_files(self, workdir):
        folder = _profile_folder("prod")
        _write_config(folder / "config.json", {**CRED_A, "sandbox": "dev"})
        _write_private(folder / ".env", f"ORG_ID={CRED_B['org_id']}\n")

        report = build_config_check(profile_flag="prod")

        assert_matches_schema(report, "config-check-v1")
        assert report["ok"] is True
        assert report["profile"] == "prod"
        assert report["source"] == {
            "kind": "flag_profile",
            "name": "profile prod config.json",
            "path": str(folder / "config.json"),
        }
        assert [(entry["name"], entry["path"], entry["used"]) for entry in report["sources"]] == [
            ("profile prod config.json", str(folder / "config.json"), True),
            ("profile prod .env", str(folder / ".env"), True),
        ]
        assert report["sources"][0]["fields"] == ["org_id", "client_id", "secret", "scopes", "sandbox"]
        assert report["sources"][1]["fields"] == ["org_id"]
        assert report["credential"]["org_id"] == CRED_B["org_id"]
        assert report["credential"]["sandbox"] == "dev"
        assert _codes(report["notices"]) == ["mixed_sources"]

    def test_a_profile_whose_dotenv_overrides_every_field(self, workdir):
        folder = _profile_folder("prod")
        _write_config(folder / "config.json", CRED_A)
        _write_dotenv(folder, CRED_B)

        report = build_config_check(profile_flag="prod")

        assert report["ok"] is True
        assert report["source"]["name"] == "profile prod .env"
        assert [(entry["used"], entry["skipped"]) for entry in report["sources"]] == [
            (False, "lower_priority"),
            (True, None),
        ]
        assert report["notices"] == []

    def test_a_profile_with_only_a_dotenv_file(self, workdir):
        _write_dotenv(_profile_folder("prod"), CRED_A)

        report = build_config_check(profile_flag="prod")

        assert report["ok"] is True
        assert [entry["name"] for entry in report["sources"]] == ["profile prod .env"]

    def test_the_profile_variable_is_named(self, workdir, monkeypatch):
        _write_config(_profile_folder("prod") / "config.json", CRED_A)
        monkeypatch.setenv("CJA_PROFILE", "prod")

        report = build_config_check()

        assert report["source"]["kind"] == "profile_variable"
        assert report["sources"][0]["variable"] == "CJA_PROFILE"
        assert "variable_set_by" not in report["sources"][0]

    def test_a_profile_variable_set_by_dotenv_names_the_file(self, workdir):
        _write_config(_profile_folder("other") / "config.json", CRED_B)
        dotenv_path = _write_dotenv(workdir, CRED_A, extra="CJA_PROFILE=other\n")

        report = build_config_check()

        assert report["profile"] == "other"
        assert report["sources"][0]["variable_set_by"] == str(dotenv_path)
        assert f"CJA_PROFILE was set by: {dotenv_path}" in render_config_check(report)
        kinds = [(entry["kind"], entry["skipped"]) for entry in report["sources"]]
        assert kinds == [("profile_variable", None), ("dotenv", "lower_priority")]

    def test_an_invalid_profile_name(self, workdir):
        report = build_config_check(profile_flag="../other")

        assert report["ok"] is False
        assert _codes(report["problems"]) == ["invalid_profile_name"]

    def test_a_missing_profile_does_not_fall_back(self, workdir, monkeypatch):
        _set_env(monkeypatch, CRED_B)
        _write_config(workdir / "config.json", CRED_B)

        report = build_config_check(profile_flag="missing")

        assert report["ok"] is False
        assert report["source"] is None
        assert _codes(report["problems"]) == ["profile_not_found"]
        assert [(entry["kind"], entry["skipped"]) for entry in report["sources"]] == [
            ("environment", "lower_priority"),
            ("default_config", "lower_priority"),
        ]

    def test_an_empty_profile_folder(self, workdir):
        _profile_folder("prod").mkdir(parents=True)

        report = build_config_check(profile_flag="prod")

        assert _codes(report["problems"]) == ["no_credential"]
        assert "has no credential" in report["problems"][0]["message"]

    def test_a_partial_profile(self, workdir, monkeypatch):
        _write_config(_profile_folder("prod") / "config.json", _without(CRED_A, "secret"))
        _set_env(monkeypatch, CRED_B)

        report = build_config_check(profile_flag="prod")

        assert_matches_schema(report, "config-check-v1")
        assert report["ok"] is False
        assert report["problems"][0]["code"] == "partial_source"
        assert report["problems"][0]["missing"] == ["secret"]
        assert report["sources"][0]["skipped"] == "partial"
        assert report["credential"]["client_id"] == "aaaa****4444"
        assert report["credential"]["secret_set"] is False

    def test_environment_and_dotenv_are_named_apart(self, workdir, monkeypatch):
        _set_env(monkeypatch, _without(CRED_A, "secret", "scopes"))
        dotenv_path = _write_dotenv(workdir, CRED_B)
        _write_config(workdir / "config.json", CRED_B)

        report = build_config_check()

        assert_matches_schema(report, "config-check-v1")
        assert report["ok"] is True
        assert report["source"]["kind"] == "environment"
        summary = [(entry["kind"], entry["path"], entry["used"], entry["fields"]) for entry in report["sources"][:2]]
        assert summary == [
            ("environment", None, True, ["org_id", "client_id"]),
            ("dotenv", str(dotenv_path), True, ["org_id", "client_id", "secret", "scopes"]),
        ]
        assert report["sources"][2]["skipped"] == "lower_priority"
        assert set(_codes(report["notices"])) == {"mixed_sources"}

    def test_a_dotenv_in_a_parent_folder_is_named_with_its_path(self, workdir):
        dotenv_path = _write_dotenv(workdir.parent, CRED_A)

        report = build_config_check()

        assert report["ok"] is True
        assert report["source"] == {"kind": "dotenv", "name": ".env file", "path": str(dotenv_path)}

    def test_a_dotenv_that_the_environment_fully_overrides(self, workdir, monkeypatch):
        _set_env(monkeypatch, CRED_A)
        _write_dotenv(workdir, CRED_B)

        report = build_config_check()

        assert report["source"]["kind"] == "environment"
        assert [(entry["kind"], entry["used"], entry["skipped"]) for entry in report["sources"]] == [
            ("environment", True, None),
            ("dotenv", False, "lower_priority"),
        ]

    def test_a_dotenv_that_is_not_loaded_is_listed_as_not_used(self, workdir, monkeypatch):
        _write_dotenv(workdir, CRED_A)
        monkeypatch.setenv("PYTHON_DOTENV_DISABLED", "1")
        record_dotenv_load(str(workdir / ".env"), set())

        report = build_config_check()

        assert report["ok"] is False
        assert [(entry["kind"], entry["skipped"]) for entry in report["sources"]] == [("dotenv", "lower_priority")]

    def test_a_partial_environment_falls_back_to_the_config_file(self, workdir, monkeypatch):
        _set_env(monkeypatch, _without(CRED_A, "secret"))
        _write_config(workdir / "config.json", CRED_B)

        report = build_config_check()

        assert report["ok"] is True
        assert report["source"]["kind"] == "default_config"
        assert report["sources"][0] == {
            "kind": "environment",
            "name": "environment variables",
            "path": None,
            "used": False,
            "fields": ["org_id", "client_id", "scopes"],
            "skipped": "partial",
            "missing": ["secret"],
        }
        assert report["notices"][0]["code"] == "partial_source_skipped"
        assert report["notices"][0]["missing"] == ["secret"]
        assert "reads the config file" in report["notices"][0]["message"]

    def test_a_partial_environment_with_nothing_below_it(self, workdir, monkeypatch):
        _set_env(monkeypatch, _without(CRED_A, "secret"))

        report = build_config_check()

        assert report["ok"] is False
        assert _codes(report["problems"]) == ["no_credential"]
        assert "finds no other credential" in report["notices"][0]["message"]

    def test_a_partial_environment_does_not_blame_a_dotenv_that_set_nothing(self, workdir, monkeypatch):
        _set_env(monkeypatch, {"org_id": CRED_A["org_id"]})
        monkeypatch.setenv("CLIENT_ID", " ")
        monkeypatch.setenv("SECRET", " ")
        monkeypatch.setenv("SCOPES", " ")
        _write_dotenv(workdir, _without(CRED_B, "org_id"))

        report = build_config_check()

        assert [(entry["kind"], entry["skipped"]) for entry in report["sources"]] == [
            ("environment", "partial"),
            ("dotenv", "lower_priority"),
        ]

    def test_an_environment_without_scopes_stops_the_run(self, workdir, monkeypatch):
        _set_env(monkeypatch, _without(CRED_A, "scopes"))
        _write_dotenv(workdir.parent, {"org_id": CRED_A["org_id"]})
        _write_config(workdir / "config.json", CRED_B)

        report = build_config_check()

        assert report["ok"] is False
        assert report["problems"][0]["code"] == "partial_source"
        assert report["problems"][0]["missing"] == ["scopes"]
        assert [(entry["kind"], entry["skipped"]) for entry in report["sources"]] == [
            ("environment", "partial"),
            ("dotenv", "lower_priority"),
            ("default_config", "lower_priority"),
        ]

    def test_an_environment_with_a_bad_value_is_skipped_with_a_reason(self, workdir, monkeypatch):
        _set_env(monkeypatch, {**CRED_A, "client_id": "short"})
        _write_config(workdir / "config.json", CRED_B)

        report = build_config_check()

        assert report["source"]["kind"] == "default_config"
        assert report["sources"][0]["skipped"] is None
        assert "not valid" in report["sources"][0]["reason"]
        assert "not valid" in render_config_check(report)
        assert report["notices"] == []

    def test_only_the_sandbox_variable_is_not_a_partial_source(self, workdir, monkeypatch):
        monkeypatch.setenv("SANDBOX", "dev")
        _write_config(workdir / "config.json", CRED_B)

        report = build_config_check()

        assert report["ok"] is True
        assert report["sources"][0] == {
            "kind": "environment",
            "name": "environment variables",
            "path": None,
            "used": False,
            "fields": ["sandbox"],
            "skipped": None,
        }
        assert report["notices"] == []

    def test_an_explicit_config_file(self, workdir):
        path = _write_config(workdir / "other.json", CRED_A)

        report = build_config_check(config_file=str(path), config_file_given=True)

        assert report["source"] == {
            "kind": "flag_config",
            "name": "config file other.json",
            "path": str(path.resolve()),
        }

    def test_an_explicit_config_file_that_is_missing(self, workdir):
        report = build_config_check(config_file="missing.json", config_file_given=True)

        assert _codes(report["problems"]) == ["no_credential"]
        assert "missing.json was not found" in report["problems"][0]["message"]

    def test_a_partial_config_file(self, workdir):
        _write_config(workdir / "config.json", _without(CRED_A, "scopes"))

        report = build_config_check()

        assert report["ok"] is False
        assert report["problems"][0]["missing"] == ["scopes"]
        assert report["sources"][0]["skipped"] == "partial"

    @pytest.mark.parametrize("text", ["not json", "[1, 2]", "{}", '{"ORG_ID": "x"}'])
    def test_a_config_file_with_no_credential(self, workdir, text):
        _write_private(workdir / "config.json", text)

        report = build_config_check()

        assert report["ok"] is False
        assert report["sources"] == []
        assert _codes(report["problems"]) == ["no_credential"]
        assert "holds no credential field" in report["problems"][0]["message"]

    def test_profile_flag_and_config_flag_give_a_notice(self, workdir):
        _write_config(_profile_folder("prod") / "config.json", CRED_A)
        path = _write_config(workdir / "other.json", CRED_B)

        report = build_config_check(profile_flag="prod", config_file=str(path), config_file_given=True)

        assert report["ok"] is True
        assert report["source"]["kind"] == "flag_profile"
        assert _codes(report["notices"]) == ["profile_and_config_both_given"]
        assert "Release 4.0 will stop with an error instead." in report["notices"][0]["message"]

    def test_profile_variable_and_config_flag_give_a_notice(self, workdir, monkeypatch):
        _write_config(_profile_folder("prod") / "config.json", CRED_A)
        monkeypatch.setenv("CJA_PROFILE", "prod")
        path = _write_config(workdir / "other.json", CRED_B)

        report = build_config_check(config_file=str(path), config_file_given=True)

        assert report["source"]["kind"] == "profile_variable"
        assert "Release 4.0 will use the config file instead." in report["notices"][0]["message"]

    def test_dotenv_and_config_that_differ_give_a_notice(self, workdir):
        _write_dotenv(workdir, CRED_A)
        _write_config(workdir / "config.json", CRED_B)

        report = build_config_check()

        assert _codes(report["notices"]) == ["dotenv_and_config_differ"]
        assert "This run uses the .env file" in report["notices"][0]["message"]

    @posix_only
    def test_files_that_others_can_read_are_listed_as_warnings(self, workdir, capsys):
        _write_dotenv(workdir, CRED_A).chmod(0o644)
        _write_config(workdir / "config.json", CRED_A).chmod(0o640)

        report = build_config_check()

        assert _codes(report["warnings"]) == ["file_readable_by_others", "file_readable_by_others"]
        assert [Path(item["path"]).name for item in report["warnings"]] == [".env", "config.json"]
        assert capsys.readouterr().err.count("Warning [file_readable_by_others]") == 2

    def test_the_check_makes_no_log_line_at_warning_level(self, workdir, monkeypatch, caplog):
        _set_env(monkeypatch, _without(CRED_A, "secret"))

        with caplog.at_level(logging.WARNING):
            build_config_check()

        assert caplog.records == []

    @pytest.mark.parametrize(
        ("build", "kind"),
        [
            (lambda work, mp: _write_config(_profile_folder("prod") / "config.json", CRED_A), "flag_profile"),
            (lambda work, mp: _set_env(mp, CRED_A), "environment"),
            (lambda work, mp: _write_dotenv(work, CRED_A), "dotenv"),
            (lambda work, mp: _write_config(work / "config.json", CRED_A), "default_config"),
        ],
    )
    def test_the_check_agrees_with_the_real_lookup(self, workdir, monkeypatch, build, kind):
        build(workdir, monkeypatch)
        profile = "prod" if kind == "flag_profile" else None

        report = build_config_check(profile_flag=profile)
        success, _source, credentials = _lookup(profile=profile)

        assert report["ok"] is True
        assert success is True
        assert report["source"]["kind"] == kind
        assert credentials == CRED_A


class TestRenderConfigCheck:
    def test_a_ready_credential(self, workdir):
        path = _write_config(workdir / "config.json", {**CRED_A, "sandbox": "dev"})

        text = render_config_check(build_config_check())

        assert "Result: ready" in text
        assert "Profile: (none)" in text
        assert "  - config file config.json (used)" in text
        assert f"      file: {path.resolve()}" in text
        assert "      fields: org_id, client_id, secret, scopes, sandbox" in text
        assert "  client_id: aaaa****4444" in text
        assert "  secret: ****" in text
        assert "  sandbox: dev" in text
        assert "cja_auto_sdr --validate-config" in text
        assert "Problems:" not in text
        assert CRED_A["secret"] not in text

    def test_no_credential(self, workdir):
        text = render_config_check(build_config_check())

        assert "Result: not ready" in text
        assert "  (no source holds a value)" in text
        assert "  secret: not set" in text
        assert "  sandbox: not set (optional)" in text
        assert "  - [no_credential] No source gave a credential." in text
        assert "--validate-config" not in text

    def test_skipped_sources_and_notices(self, workdir, monkeypatch):
        _set_env(monkeypatch, _without(CRED_A, "secret", "scopes"))
        _write_config(workdir / "config.json", CRED_B)

        text = render_config_check(build_config_check())

        assert "  - environment variables (skipped, missing secret, scopes)" in text
        assert "      variables: ORG_ID, CLIENT_ID" in text
        assert "Notices:" in text
        assert "  - [partial_source_skipped] The environment variables hold part of a credential." in text

    def test_a_lower_source(self, workdir, monkeypatch):
        _set_env(monkeypatch, CRED_A)
        _write_config(workdir / "config.json", CRED_B)

        text = render_config_check(build_config_check())

        assert "  - config file config.json (not used, a higher source won)" in text
        assert "Profile: (none)" in text


# ==================== THE COMMAND LINE ====================


@pytest.mark.usefixtures("clean_root_logging")
class TestShowConfigCommand:
    def test_text_output(self, workdir, capsys):
        _write_config(workdir / "config.json", CRED_A)

        code, out, err = run_cli(["--show-config"], capsys)

        assert code == 0
        assert "CREDENTIAL CONFIGURATION" in out
        assert "Result: ready" in out
        assert err == ""

    def test_json_output_with_format(self, workdir, capsys):
        _write_config(workdir / "config.json", CRED_A)

        code, out, _err = run_cli(["--show-config", "--format", "json"], capsys)

        assert code == 0
        assert_matches_schema(json.loads(out), "config-check-v1")

    def test_json_output_with_config_json(self, workdir, capsys):
        code, out, _err = run_cli(["--show-config", "--config-json"], capsys)

        report = json.loads(out)
        assert code == 1
        assert report["schema"] == "adobe-credentials/v1/config-check"
        assert report["ok"] is False

    def test_json_output_with_agent_mode(self, workdir, capsys):
        _write_config(workdir / "config.json", CRED_A)

        code, out, _err = run_cli(["--show-config", "--agent-mode"], capsys)

        assert code == 0
        assert json.loads(out)["ok"] is True

    def test_config_is_a_second_name_for_config_file(self, workdir, capsys):
        path = _write_config(workdir / "other.json", CRED_A)

        for flag in ("--config", "--config-file"):
            code, out, _err = run_cli([flag, str(path), "--show-config", "--format", "json"], capsys)
            assert code == 0
            assert json.loads(out)["source"]["kind"] == "flag_config"

        code, out, _err = run_cli([f"--config={path}", "--show-config", "--format", "json"], capsys)
        assert json.loads(out)["source"]["path"] == str(path.resolve())

    def test_the_short_profile_flag_counts_as_the_flag(self, workdir, capsys, monkeypatch):
        _write_config(_profile_folder("prod") / "config.json", CRED_A)
        monkeypatch.setenv("CJA_PROFILE", "prod")

        _code, out, _err = run_cli(["--show-config", "--format", "json"], capsys)
        assert json.loads(out)["source"]["kind"] == "profile_variable"

        _code, out, _err = run_cli(["-p", "prod", "--show-config", "--format", "json"], capsys)
        assert json.loads(out)["source"]["kind"] == "flag_profile"

        _code, out, _err = run_cli(["--profile=prod", "--show-config", "--format", "json"], capsys)
        assert json.loads(out)["source"]["kind"] == "flag_profile"

    def test_profile_and_config_file_are_reported_in_the_check_only(self, workdir, capsys):
        _write_config(_profile_folder("prod") / "config.json", CRED_A)
        path = _write_config(workdir / "other.json", CRED_B)

        code, out, err = run_cli(
            ["--profile", "prod", "--config-file", str(path), "--show-config", "--format", "json"], capsys
        )

        assert code == 0
        assert [notice["code"] for notice in json.loads(out)["notices"]] == ["profile_and_config_both_given"]
        assert "Notice [" not in err

    def test_output_is_ignored_with_a_warning(self, workdir, capsys):
        _write_config(workdir / "config.json", CRED_A)

        code, out, err = run_cli(["--show-config", "--format", "json", "--output", "report.json"], capsys)

        assert code == 0
        assert json.loads(out)["ok"] is True
        assert "--output is ignored with --show-config" in err
        assert not (workdir / "report.json").exists()

    def test_show_config_cannot_run_with_watch(self, workdir, capsys):
        code, _out, err = run_cli(["--watch", "dv_1", "--interval", "1h", "--show-config"], capsys)

        assert code == 1
        assert "--watch is incompatible with --show-config" in err

    def test_config_status_keeps_its_json_keys(self, workdir, capsys):
        _write_config(workdir / "config.json", CRED_A)

        code, out, _err = run_cli(["--config-status", "--config-json"], capsys)

        status = json.loads(out)
        assert code == 0
        assert set(status) == {"source", "source_type", "profile", "config_file", "credentials", "valid"}
        assert status["credentials"]["client_id"] == {"value": "aaaa****4444", "set": True, "required": True}


@pytest.mark.usefixtures("clean_root_logging")
class TestProfileAndConfigNotice:
    def test_both_flags_warn_and_the_profile_is_used(self, workdir, capsys):
        _write_config(_profile_folder("prod") / "config.json", CRED_A)
        path = _write_config(workdir / "other.json", CRED_B)

        code, out, err = run_cli(
            ["--profile", "prod", "--config-file", str(path), "--config-status", "--config-json"], capsys
        )

        status = json.loads(out)
        assert code == 0
        assert status["source"] == "Profile: prod"
        assert err.count("Notice [profile_and_config_both_given]") == 1
        assert "--profile and --config-file were both given." in err
        assert "This run uses the profile prod" in err

    def test_the_profile_variable_and_the_config_flag_warn(self, workdir, capsys, monkeypatch):
        _write_config(_profile_folder("prod") / "config.json", CRED_A)
        monkeypatch.setenv("CJA_PROFILE", "prod")
        path = _write_config(workdir / "other.json", CRED_B)

        code, _out, err = run_cli(["--config", str(path), "--config-status", "--config-json"], capsys)

        assert code == 0
        assert "CJA_PROFILE is set and --config-file was given." in err

    def test_a_config_file_alone_gives_no_notice(self, workdir, capsys):
        path = _write_config(workdir / "other.json", CRED_B)

        code, _out, err = run_cli(["--config-file", str(path), "--config-status", "--config-json"], capsys)

        assert code == 0
        assert "Notice [" not in err

    def test_a_profile_alone_gives_no_notice(self, workdir, capsys):
        _write_config(_profile_folder("prod") / "config.json", CRED_A)

        code, _out, err = run_cli(["--profile", "prod", "--config-status", "--config-json"], capsys)

        assert code == 0
        assert "Notice [" not in err


# ==================== THE LIVE TEST ====================


def _run_profile_test(capsys, *, product=None, output_format="table", name="prod"):
    cja = MagicMock()
    if isinstance(product, Exception):
        cja.getDataViews.side_effect = product
    else:
        cja.getDataViews.return_value = product
    with (
        patch("cja_auto_sdr.generator.cjapy") as cjapy_module,
        patch("cja_auto_sdr.generator._config_from_env"),
    ):
        cjapy_module.CJA.return_value = cja
        passed = profiles.test_profile(name, output_format=output_format)
    captured = capsys.readouterr()
    return passed, captured.out, captured.err, cja


class TestProfileTest:
    @pytest.fixture(autouse=True)
    def _profile(self, workdir):
        _write_config(_profile_folder("prod") / "config.json", CRED_A)

    @pytest.mark.usefixtures("sign_in_ok")
    def test_both_steps_pass(self, capsys):
        passed, out, err, _cja = _run_profile_test(capsys, product=[{"id": "dv_1"}, {"id": "dv_2"}])

        assert passed is True
        assert "3. Signing in to Adobe..." in out
        assert "   Sign-in: OK" in out
        assert "4. Asking Customer Journey Analytics for the data views (getDataViews)..." in out
        assert "   Data views: OK" in out
        assert "   Data views accessible: 2" in out
        assert "Profile test: PASSED" in out
        assert err == ""

    def test_sign_in_sends_the_values_that_cjapy_gets(self, capsys, monkeypatch):
        seen = {}

        def _post(fields):
            seen.update(fields)
            return 200, {"access_token": "stub-token"}

        monkeypatch.setattr(sign_in, "post_token_request", _post)
        _write_config(_profile_folder("spaced") / "config.json", {**CRED_A, "scopes": " openid, AdobeID "})

        passed, _out, _err, _cja = _run_profile_test(capsys, product=[], name="spaced")

        assert passed is True
        assert seen["scope"] == "openid,AdobeID"
        assert seen["client_id"] == CRED_A["client_id"]

    def test_empty_values_are_sent_as_empty_text(self, monkeypatch):
        seen = {}

        def _post(fields):
            seen.update(fields)
            return 400, {"error": "invalid_client", "error_description": "invalid client_id parameter"}

        monkeypatch.setattr(sign_in, "post_token_request", _post)

        assert sign_in.request_token({"client_id": None}).code == "bad_client_id"
        assert seen == {"grant_type": "client_credentials", "client_id": "", "client_secret": "", "scope": ""}

    @pytest.mark.usefixtures("sign_in_ok")
    def test_json_output_has_the_live_test_shape(self, capsys):
        passed, out, err, _cja = _run_profile_test(capsys, product=[{"id": "dv_1"}], output_format="json")

        result = json.loads(out)
        assert passed is True
        assert_matches_schema(result, "live-test-v1")
        assert result["ok"] is True
        assert result["source"] == {"kind": "flag_profile", "name": "profile prod"}
        assert result["sign_in"] == {"ok": True, "code": None, "message": None}
        assert result["product_access"] == {"ok": True, "code": None, "message": None, "data_views": 1}
        assert err == ""

    @pytest.mark.usefixtures("sign_in_ok")
    def test_no_data_views_still_passes(self, capsys):
        passed, out, _err, _cja = _run_profile_test(capsys, product=None, output_format="json")

        assert passed is True
        assert json.loads(out)["product_access"]["data_views"] == 0

    def test_a_rejected_secret_stops_before_the_product_call(self, capsys, monkeypatch):
        monkeypatch.setattr(
            sign_in,
            "post_token_request",
            _answer(401, {"error": "invalid_client", "error_description": "invalid client_secret parameter"}),
        )

        passed, out, err, cja = _run_profile_test(capsys, product=[{"id": "dv_1"}])

        assert passed is False
        cja.getDataViews.assert_not_called()
        assert "Sign-in: FAILED (bad_secret)" in err
        assert "Adobe knows the client ID and rejected the secret." in err
        assert "4. Data views (getDataViews): NOT RUN, because sign-in failed" in err
        assert "Profile test: FAILED" in err
        assert CRED_A["secret"] not in out + err

    def test_a_failed_sign_in_in_json(self, capsys, monkeypatch):
        monkeypatch.setattr(
            sign_in,
            "post_token_request",
            _answer(400, {"error": "invalid_client", "error_description": "invalid client_id parameter"}),
        )

        passed, out, _err, _cja = _run_profile_test(capsys, output_format="json")

        result = json.loads(out)
        assert passed is False
        assert_matches_schema(result, "live-test-v1")
        assert result["ok"] is False
        assert result["sign_in"]["ok"] is False
        assert result["sign_in"]["code"] == "bad_client_id"
        assert result["product_access"] == {"ok": None, "code": None, "message": None}

    @pytest.mark.usefixtures("sign_in_ok")
    def test_no_access_to_the_product(self, capsys):
        from cja_auto_sdr.core.exceptions import APIError

        error = APIError("Forbidden", status_code=403, operation="getDataViews")
        passed, out, err, _cja = _run_profile_test(capsys, product=error, output_format="json")

        result = json.loads(out)
        assert passed is False
        assert result["sign_in"]["ok"] is True
        assert result["product_access"]["ok"] is False
        assert result["product_access"]["code"] == "no_product_access"
        assert "CJA product profile" in result["product_access"]["message"]
        assert "Customer Journey Analytics API" in result["product_access"]["message"]
        assert "Data views: FAILED (no_product_access)" in err

    @pytest.mark.usefixtures("sign_in_ok")
    def test_an_empty_answer_from_the_product_is_no_access(self, capsys):
        passed, out, _err, _cja = _run_profile_test(capsys, product=KeyError("content"), output_format="json")

        assert passed is False
        assert json.loads(out)["product_access"]["code"] == "no_product_access"

    @pytest.mark.usefixtures("sign_in_ok")
    def test_a_product_that_cannot_be_reached(self, capsys):
        passed, out, err, _cja = _run_profile_test(capsys, product=ConnectionError("network down"))

        assert passed is False
        assert "Data views: FAILED (unreachable)" in err
        assert "The Customer Journey Analytics call failed: network down" in err
        assert "Common issues:" in out

    @pytest.mark.usefixtures("sign_in_ok")
    def test_a_long_product_error_is_cut(self, capsys):
        passed, out, _err, _cja = _run_profile_test(capsys, product=ConnectionError("y" * 500), output_format="json")

        message = json.loads(out)["product_access"]["message"]
        assert passed is False
        assert message == "The Customer Journey Analytics call failed: " + "y" * 200

    def test_a_missing_profile_in_json(self, capsys):
        passed, out, err, _cja = _run_profile_test(capsys, output_format="json", name="missing")

        result = json.loads(out)
        assert passed is False
        assert_matches_schema(result, "live-test-v1")
        assert result["problems"][0]["code"] == "profile_not_found"
        assert result["sign_in"]["ok"] is None
        assert "ERROR" in err

    def test_an_invalid_profile_name_in_json(self, capsys):
        passed, out, _err, _cja = _run_profile_test(capsys, output_format="json", name="../other")

        assert passed is False
        assert json.loads(out)["problems"][0]["code"] == "invalid_profile_name"

    def test_an_empty_profile_in_json(self, capsys):
        _profile_folder("empty").mkdir(parents=True)

        passed, out, _err, _cja = _run_profile_test(capsys, output_format="json", name="empty")

        assert passed is False
        assert json.loads(out)["problems"][0]["code"] == "no_credential"

    def test_a_profile_without_scopes_does_not_sign_in(self, capsys):
        _write_config(_profile_folder("partial") / "config.json", _without(CRED_A, "scopes"))

        passed, out, err, cja = _run_profile_test(capsys, output_format="json", name="partial")

        result = json.loads(out)
        assert passed is False
        cja.getDataViews.assert_not_called()
        assert result["problems"] == [
            {
                "code": "partial_source",
                "message": "The profile is missing: scopes. Sign-in needs all four fields.",
                "missing": ["scopes"],
            }
        ]
        assert result["sign_in"]["ok"] is None
        assert "3. Sign-in: NOT RUN." in err

    @pytest.mark.usefixtures("sign_in_ok", "clean_root_logging")
    def test_the_command_line_gives_json_with_format_json(self, capsys):
        with (
            patch("cja_auto_sdr.generator.cjapy") as cjapy_module,
            patch("cja_auto_sdr.generator._config_from_env"),
        ):
            cjapy_module.CJA.return_value.getDataViews.return_value = [{"id": "dv_1"}]
            code, out, _err = run_cli(["--profile-test", "prod", "--format", "json", "--output", "x.json"], capsys)

        assert code == 0
        assert json.loads(out)["schema"] == "adobe-credentials/v1/live-test"

    def test_the_command_line_exits_1_when_sign_in_fails(self, capsys, monkeypatch, clean_root_logging):
        monkeypatch.setattr(
            sign_in, "post_token_request", _answer(400, {"error": "invalid_scope", "error_description": "no"})
        )

        code, _out, err = run_cli(["--profile-test", "prod"], capsys)

        assert code == 1
        assert "Sign-in: FAILED (scopes_rejected)" in err


def test_the_new_command_is_reachable_from_the_generator_module(workdir, capsys):
    assert generator.show_config("config.json", output_json=True) is False
    assert json.loads(capsys.readouterr().out)["schema"] == "adobe-credentials/v1/config-check"
    assert show_config_module.show_config("config.json") is False
    assert "Result: not ready" in capsys.readouterr().out
