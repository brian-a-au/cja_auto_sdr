"""Run the shared cases of the Adobe credentials standard, version 1.

This module is the adapter of ``cja_auto_sdr``. It reads the case files in
``tests/standard_cases/``, builds each case in a temporary home and working
folder, runs the lookup or the command, and checks ``expect``.

``known-differences.json`` at the repo root lists the cases that this tool
does not pass yet. Exactly those cases must fail here. A listed case that
passes fails the run, so the list can only get shorter.

No case calls Adobe. The sign-in request and the product call are stubbed.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
import requests

from cja_auto_sdr.api import client as api_client
from cja_auto_sdr.api import sign_in
from cja_auto_sdr.cli.commands.show_config import build_config_check
from cja_auto_sdr.core import profiles
from cja_auto_sdr.core.constants import HIDDEN_VALUE_DISPLAY
from cja_auto_sdr.core.credential_notices import mask_client_id
from cja_auto_sdr.core.exceptions import APIError
from cja_auto_sdr.pipeline.models import WorkerArgs

REPO_ROOT = Path(__file__).resolve().parent.parent
CASES_DIR = Path(__file__).resolve().parent / "standard_cases"
TOOL = "cja_auto_sdr"
PRODUCT = "cja"
PROFILE_VARIABLE = "CJA_PROFILE"
ENV_NAMES = {"org_id": "ORG_ID", "client_id": "CLIENT_ID", "secret": "SECRET", "scopes": "SCOPES"}
FOUR_FIELDS = tuple(ENV_NAMES)
NOT_CASE_FILES = {"fixtures.json", "codes-v1.json", "SOURCE.json"}


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


FIXTURES = _load_json(CASES_DIR / "fixtures.json")["credentials"]
KNOWN_DIFFERENCES = _load_json(REPO_ROOT / "known-differences.json")
EXPECTED_TO_FAIL = {case_id for item in KNOWN_DIFFERENCES["differences"] for case_id in item.get("cases", [])}


def _all_cases() -> list[dict[str, Any]]:
    cases: list[dict[str, Any]] = []
    for path in sorted(CASES_DIR.glob("*.json")):
        if path.name in NOT_CASE_FILES or path.name.endswith(".schema.json"):
            continue
        cases.extend(_load_json(path)["cases"])
    return cases


ALL_CASES = _all_cases()


def _applies(case: dict[str, Any]) -> bool:
    if "products" in case and PRODUCT not in case["products"]:
        return False
    return "tools" not in case or TOOL in case["tools"]


# ==================== A SMALL JSON SCHEMA CHECK ====================

_JSON_TYPES: dict[str, tuple[type, ...]] = {
    "object": (dict,),
    "array": (list,),
    "string": (str,),
    "boolean": (bool,),
    "null": (type(None),),
}


def schema_errors(instance: Any, schema: dict[str, Any], where: str = "$") -> list[str]:
    """Check *instance* against the parts of JSON Schema that the two shapes use."""
    errors: list[str] = []
    if "const" in schema and instance != schema["const"]:
        errors.append(f"{where}: expected {schema['const']!r}")
    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{where}: {instance!r} is not one of {schema['enum']}")
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(isinstance(instance, _JSON_TYPES[name]) for name in names):
            errors.append(f"{where}: expected type {names}, got {type(instance).__name__}")
            return errors
    if isinstance(instance, dict):
        errors.extend(f"{where}: missing key {key!r}" for key in schema.get("required", []) if key not in instance)
        for key, sub_schema in schema.get("properties", {}).items():
            if key in instance:
                errors.extend(schema_errors(instance[key], sub_schema, f"{where}.{key}"))
        forbidden = schema.get("not", {}).get("required", [])
        if forbidden and all(key in instance for key in forbidden):
            errors.append(f"{where}: must not have the keys {forbidden}")
    if isinstance(instance, list) and "items" in schema:
        for index, item in enumerate(instance):
            errors.extend(schema_errors(item, schema["items"], f"{where}[{index}]"))
    return errors


def assert_matches_schema(instance: Any, schema_name: str) -> None:
    schema = _load_json(CASES_DIR / f"{schema_name}.schema.json")
    errors = schema_errors(instance, schema)
    assert not errors, "\n".join(errors)


# ==================== BUILDING A CASE ====================


@dataclasses.dataclass
class Built:
    """A case built on disk: the folders, the command line, and the credential of each source."""

    home: Path
    work: Path
    argv: list[str] = dataclasses.field(default_factory=list)
    profile_flag: str | None = None
    config_file: str = "config.json"
    config_file_given: bool = False
    secrets: list[str] = dataclasses.field(default_factory=list)


def _credential(spec: dict[str, Any]) -> dict[str, str]:
    """The fields of a source: the named fixture, minus ``omit``, with ``override`` applied."""
    if "credential" not in spec:
        return {}
    fields = dict(FIXTURES[spec["credential"]])
    for name in spec.get("omit", []):
        fields.pop(name, None)
    fields.update(spec.get("override", {}))
    return fields


def _write_json_file(path: Path, spec: dict[str, Any]) -> None:
    payload = {**_credential(spec), **spec.get("extra_keys", {})}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")
    path.chmod(int(spec.get("file_mode", "0600"), 8))


def _write_profile(home: Path, spec: dict[str, Any]) -> None:
    if "credential" in spec:
        _write_json_file(home / ".cja" / "orgs" / spec["name"] / "config.json", spec)


def build_case(case: dict[str, Any], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Built:
    home = tmp_path / "home"
    work = home / "projects" / "work"
    work.mkdir(parents=True)
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.chdir(work)
    built = Built(home=home, work=work)

    sources = case["given"].get("sources", {})
    for kind, spec in sources.items():
        if "secret" in _credential(spec):
            built.secrets.append(_credential(spec)["secret"])
        if kind == "flag_profile":
            _write_profile(home, spec)
            built.profile_flag = spec["name"]
            built.argv += ["--profile", spec["name"]]
        elif kind == "flag_config":
            path = work / "given" / "credential.json"
            _write_json_file(path, spec)
            built.config_file, built.config_file_given = str(path), True
            built.argv += ["--config", str(path)]
        elif kind == "profile_variable":
            _write_profile(home, spec)
            monkeypatch.setenv(PROFILE_VARIABLE, spec["name"])
        elif kind == "profile_variable_target":
            _write_profile(home, spec)
        elif kind == "environment":
            for name, value in _credential(spec).items():
                monkeypatch.setenv(ENV_NAMES[name], value)
            if spec.get("other_settings"):
                monkeypatch.setenv("SANDBOX", "dev")
                monkeypatch.setenv("LOG_LEVEL", "WARNING")
        elif kind == "dotenv":
            folder = work.parent if spec.get("location") == "parent_folder" else work
            lines = [f"{ENV_NAMES[name]}={value}" for name, value in _credential(spec).items()]
            for key, value in spec.get("extra_keys", {}).items():
                lines.append(f"{PROFILE_VARIABLE if key == 'PROFILE_VARIABLE' else key}={value}")
            (folder / ".env").write_text("\n".join(lines) + "\n", encoding="utf-8")
            (folder / ".env").chmod(0o600)
        elif kind == "default_config":
            if spec.get("through_symlink"):
                target = work / "real" / "credential.json"
                _write_json_file(target, spec)
                (work / "config.json").symlink_to(target)
            else:
                _write_json_file(work / "config.json", spec)
        else:
            raise AssertionError(f"The adapter does not know the source {kind!r}")
    return built


# ==================== RUNNING THE TOOL ====================


def run_cli(argv: list[str], capsys: pytest.CaptureFixture[str]) -> tuple[int, str, str]:
    """Run the command line in this process. Returns the exit code, stdout and stderr."""
    from cja_auto_sdr.generator import main

    capsys.readouterr()
    code = 0
    try:
        with patch.object(sys, "argv", ["cja_auto_sdr", *argv]):
            main()
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def _strict_configure(org_id=None, secret=None, client_id=None, scopes=None, **_kwargs):
    # cjapy.configure needs all four fields, so a credential without one stops the run.
    if not (org_id and secret and client_id and scopes):
        raise ValueError("a field is missing in the configuration")


def real_lookup(built: Built) -> tuple[bool, dict[str, str] | None]:
    """Run the lookup that real runs use. Returns whether it worked, and the credential."""
    with patch.object(api_client.cjapy, "configure", side_effect=_strict_configure):
        try:
            success, _source, credentials = api_client.configure_cjapy(
                built.profile_flag, built.config_file, logging.getLogger("test_standard_cases")
            )
        except ValueError:
            return False, None
    return success, credentials


# The shapes of the standard put the key "secret_set" and the schema name
# "adobe-credentials/v1/..." in the output, and the made-up secrets hold the words
# "secret" and "-credential". Runs of 4 characters inside those two terms are
# therefore not counted as a leak. Every other run of 4 characters is.
_WORDS_THE_OUTPUT_NEEDS = ("secret", "adobe-credentials")


def secret_runs(secret: str) -> set[str]:
    runs = {secret[index : index + 4] for index in range(len(secret) - 3)}
    return {run for run in runs if not any(run in word for word in _WORDS_THE_OUTPUT_NEEDS)}


def assert_no_secret_in(output: str, secrets: list[str]) -> None:
    for secret in secrets:
        leaked = sorted(run for run in secret_runs(secret) if run in output)
        assert not leaked, f"The output holds part of a secret: {leaked}"


# ==================== THE KINDS OF CASE ====================


def run_pure_case(case: dict[str, Any], tmp_path, monkeypatch, capsys) -> None:
    """Cases with no sources: masking, profile names and folder modes."""
    given, expect = case["given"], case["expect"]
    if "client_id" in given:
        assert mask_client_id(given["client_id"]) == expect["masked"]
    elif "secret" in given:
        # The secret is shown through the constant, never through the mask of the client ID.
        assert expect["masked"] == HIDDEN_VALUE_DISPLAY
        built = build_case({"given": {}}, tmp_path, monkeypatch)
        _write_json_file(
            built.home / ".cja" / "orgs" / "prod" / "config.json",
            {"credential": "A", "override": {"secret": given["secret"]}},
        )
        assert profiles.show_profile("prod") is True
        output = capsys.readouterr().out
        assert f"secret: {HIDDEN_VALUE_DISPLAY}\n" in output
        assert given["secret"] not in output
    elif "profile_name" in given and "action" not in given:
        assert profiles.validate_profile_name(given["profile_name"])[0] is expect["valid"]
    elif given.get("action") == "create_profile":
        if os.name == "nt":
            pytest.skip("File modes do not describe access on Windows")
        built = build_case({"given": {}}, tmp_path, monkeypatch)
        orgs = built.home / ".cja" / "orgs"
        if "existing_folder_mode" in given:
            orgs.mkdir(parents=True)
            orgs.chmod(int(given["existing_folder_mode"], 8))
        source = built.work / "import.json"
        source.write_text(json.dumps(FIXTURES[given["credential"]]), encoding="utf-8")
        assert profiles.import_profile_non_interactive(given["profile_name"], source) is True
        folder = orgs / given["profile_name"]
        if "folder_mode" in expect:
            assert oct(folder.stat().st_mode & 0o777) == oct(int(expect["folder_mode"], 8))
        if "file_mode" in expect:
            assert oct((folder / "config.json").stat().st_mode & 0o777) == oct(int(expect["file_mode"], 8))
        if "existing_folder_mode" in expect:
            assert oct(orgs.stat().st_mode & 0o777) == oct(int(expect["existing_folder_mode"], 8))
    else:
        raise AssertionError(f"The adapter does not know the case {case['id']}")


def run_lookup_case(case: dict[str, Any], tmp_path, monkeypatch) -> None:
    """A case with no command: which source wins, or which error stops the run."""
    expect = case["expect"]
    built = build_case(case, tmp_path, monkeypatch)
    report = build_config_check(
        profile_flag=built.profile_flag,
        config_file=built.config_file,
        config_file_given=built.config_file_given,
    )
    worked, credentials = real_lookup(built)

    if "error" in expect:
        codes = [problem["code"] for problem in report["problems"]]
        assert expect["error"] in codes, f"expected the error {expect['error']}, got {codes}"
        assert report["ok"] is False
        assert worked is False, "the config check reports an error, but the lookup gave a credential"
        if "missing" in expect:
            problem = next(item for item in report["problems"] if item["code"] == expect["error"])
            assert problem.get("missing") == expect["missing"]
        return

    assert report["ok"] is True, report["problems"]
    assert worked is True
    assert report["source"]["kind"] == expect["source"]
    wanted = FIXTURES[expect["credential"]]
    assert {name: (credentials or {}).get(name) for name in FOUR_FIELDS} == wanted
    assert report["credential"]["client_id"] == mask_client_id(wanted["client_id"])


def run_config_check_case(case: dict[str, Any], tmp_path, monkeypatch, capsys, caplog) -> None:
    given, expect = case["given"], case["expect"]
    built = build_case(case, tmp_path, monkeypatch)
    if given.get("network") == "blocked":
        monkeypatch.setattr(requests.Session, "send", MagicMock(side_effect=AssertionError("network call")))
        monkeypatch.setattr(api_client.cjapy, "CJA", MagicMock(side_effect=AssertionError("network call")))

    with caplog.at_level(logging.DEBUG):
        code, out, err = run_cli([*built.argv, "--show-config", "--format", "json"], capsys)
    report = json.loads(out)
    assert code == (0 if report["ok"] else 1)
    assert_matches_schema(report, "config-check-v1")
    problem_codes = [problem["code"] for problem in report["problems"]]
    notices = {notice["code"]: notice for notice in report["notices"]}

    if "ok" in expect:
        assert report["ok"] is expect["ok"]
    if "source" in expect:
        assert report["source"]["kind"] == expect["source"]
    if "profile" in expect:
        assert report["profile"] == expect["profile"]
    if "client_id" in expect:
        assert report["credential"]["client_id"] == expect["client_id"]
    if "secret_set" in expect:
        assert report["credential"]["secret_set"] is expect["secret_set"]
    if expect.get("has_no_secret_field"):
        assert "secret" not in report["credential"]
        assert '"secret":' not in out
    if "scopes" in expect:
        assert report["credential"]["scopes"] == expect["scopes"]
    if "skipped_source" in expect:
        skipped = [entry for entry in report["sources"] if entry["kind"] == expect["skipped_source"]]
        assert skipped, report["sources"]
        assert skipped[0]["skipped"] == "partial"
        assert skipped[0]["missing"] == expect["missing"]
    if "problem" in expect:
        assert expect["problem"] in problem_codes
    if "error" in expect:
        assert report["ok"] is False
        assert expect["error"] in problem_codes
    if "notice" in expect:
        assert expect["notice"] in notices, list(notices)
        if "missing" in expect:
            assert notices[expect["notice"]]["missing"] == expect["missing"]
    if "notice_one_of" in expect:
        assert set(expect["notice_one_of"]) & set(notices), list(notices)
    if expect.get("debug") == "unknown_key":
        unknown = list(given["sources"]["default_config"]["extra_keys"])
        debug_lines = [record.getMessage() for record in caplog.records if record.levelno == logging.DEBUG]
        for key in unknown:
            assert any(f"unknown key '{key}'" in line for line in debug_lines), debug_lines
    if "profile_folder" in expect:
        folder = Path(os.path.expanduser(expect["profile_folder"]))
        paths = [entry["path"] for entry in report["sources"] if entry["kind"] == "flag_profile"]
        assert paths
        assert all(Path(path).parent == folder for path in paths)
    if "warning_count" in expect:
        if os.name == "nt":
            pytest.skip("File modes do not describe access on Windows")
        warning_lines = [line for line in err.splitlines() if line.startswith("Warning [")]
        assert len(warning_lines) == expect["warning_count"], warning_lines
        if "warning" in expect:
            assert warning_lines[0].startswith(f"Warning [{expect['warning']}]")
            assert [warning["code"] for warning in report["warnings"]] == [expect["warning"]]
    if expect.get("output_excludes_secret"):
        _code, text_out, text_err = run_cli([*built.argv, "--show-config"], capsys)
        assert_no_secret_in(out + err + text_out + text_err, built.secrets)


def _stub_sign_in(answer: Any):
    def _post(_fields):
        if answer == "connection_error":
            raise requests.ConnectionError("stubbed connection error")
        return answer["status"], answer["body"]

    return _post


def _stub_product(answer: str | None) -> MagicMock:
    cja = MagicMock()
    if answer == "has_access":
        cja.getDataViews.return_value = [{"id": "dv_stub", "name": "Stub"}]
    elif answer == "no_access":
        cja.getDataViews.side_effect = APIError("Forbidden", status_code=403, operation="getDataViews")
    elif answer == "connection_error":
        cja.getDataViews.side_effect = ConnectionError("stubbed connection error")
    else:
        cja.getDataViews.side_effect = AssertionError("the product call must not run when sign-in failed")
    return cja


def run_live_test_case(case: dict[str, Any], tmp_path, monkeypatch, capsys) -> None:
    """The live test of this tool is ``--profile-test``, so the credential goes into a profile."""
    given, expect = case["given"], case["expect"]
    spec = next(iter(given.get("sources", {}).values()), {"credential": "A"})
    built = build_case({"given": {}}, tmp_path, monkeypatch)
    for name in ENV_NAMES.values():
        monkeypatch.delenv(name, raising=False)
    _write_profile(built.home, {**spec, "name": "prod"})
    secret = _credential(spec)["secret"]

    monkeypatch.setattr(sign_in, "post_token_request", _stub_sign_in(given["sign_in_answer"]))
    cja = _stub_product(given.get("product_answer"))
    with (
        patch("cja_auto_sdr.generator.cjapy") as cjapy_module,
        patch("cja_auto_sdr.generator._config_from_env"),
    ):
        cjapy_module.CJA.return_value = cja
        code, out, err = run_cli(["--profile-test", "prod", "--format", "json"], capsys)
        _text_code, text_out, text_err = run_cli(["--profile-test", "prod"], capsys)
    result = json.loads(out)
    assert_matches_schema(result, "live-test-v1")
    assert code == (0 if result["ok"] else 1)
    assert result["ok"] is (result["sign_in"]["ok"] is True and result["product_access"]["ok"] is True)
    assert result["source"] == {"kind": "flag_profile", "name": "profile prod"}

    for step in ("sign_in", "product_access"):
        wanted = expect.get(step, {})
        if "ok" in wanted:
            assert result[step]["ok"] is wanted["ok"]
        if "code" in wanted:
            assert result[step]["code"] == wanted["code"]
        if "message_contains" in wanted:
            assert wanted["message_contains"] in result[step]["message"]
        if "message_excludes" in wanted:
            assert wanted["message_excludes"] not in result[step]["message"]
        if "message_contains_by_product" in wanted:
            assert wanted["message_contains_by_product"][PRODUCT] in result[step]["message"]
    if expect.get("output_excludes_secret"):
        assert_no_secret_in(out + err + text_out + text_err, [secret])


def run_child_case(case: dict[str, Any]) -> None:
    """A batch worker gets the profile name and the config file path, and does its own lookup."""
    assert case["expect"]["child_arguments_exclude_secret"] is True
    worker_fields = {item.name for item in dataclasses.fields(WorkerArgs)}
    assert {"config_file", "profile"} <= worker_fields
    assert not worker_fields & {"secret", "client_id", "org_id", "scopes", "credentials"}


def run_case(case: dict[str, Any], tmp_path, monkeypatch, capsys, caplog) -> None:
    given = case["given"]
    command = given.get("command")
    if command == "config_check":
        run_config_check_case(case, tmp_path, monkeypatch, capsys, caplog)
    elif command == "live_test":
        run_live_test_case(case, tmp_path, monkeypatch, capsys)
    elif command == "run_child":
        run_child_case(case)
    elif "sources" in given:
        run_lookup_case(case, tmp_path, monkeypatch)
    else:
        run_pure_case(case, tmp_path, monkeypatch, capsys)


# ==================== THE TESTS ====================


@pytest.mark.parametrize("case", ALL_CASES, ids=[case["id"] for case in ALL_CASES])
def test_shared_case(case, tmp_path, monkeypatch, capsys, caplog, clean_root_logging):
    if not _applies(case):
        pytest.skip("The case is for another product or another tool")

    if case["id"] not in EXPECTED_TO_FAIL:
        run_case(case, tmp_path, monkeypatch, capsys, caplog)
        return

    try:
        run_case(case, tmp_path, monkeypatch, capsys, caplog)
    except AssertionError:
        return
    pytest.fail(f"{case['id']} is listed in known-differences.json, but it passes. Remove it from the list.")


def test_case_ids_are_unique():
    ids = [case["id"] for case in ALL_CASES]
    assert len(ids) == len(set(ids))


def test_known_differences_matches_its_shape():
    assert_matches_schema(KNOWN_DIFFERENCES, "known-differences-v1")
    assert KNOWN_DIFFERENCES["tool"] == TOOL
    allowed_keys = {"spec", "tool", "tool_version", "not_applicable", "differences"}
    assert set(KNOWN_DIFFERENCES) <= allowed_keys


def test_known_differences_lists_only_real_cases_of_this_tool():
    applicable = {case["id"] for case in ALL_CASES if _applies(case)}
    assert applicable >= EXPECTED_TO_FAIL


def test_known_differences_lists_only_level_3_cases():
    levels = {case["id"]: case["level"] for case in ALL_CASES}
    assert {levels[case_id] for case_id in EXPECTED_TO_FAIL} <= {3}


def test_copied_cases_match_their_checksums():
    import hashlib

    source = _load_json(CASES_DIR / "SOURCE.json")
    assert source["spec"] == "adobe-credentials/v1"
    for name, digest in source["files"].items():
        assert hashlib.sha256((CASES_DIR / name).read_bytes()).hexdigest() == digest, name


def test_schema_check_rejects_a_wrong_shape():
    schema = _load_json(CASES_DIR / "config-check-v1.schema.json")
    wrong = {"schema": "other", "credential": {"secret": "x", "secret_set": "yes"}, "sources": [{"kind": "file"}]}
    errors = "\n".join(schema_errors(wrong, schema))
    assert "$.schema: expected" in errors
    assert "missing key 'tool'" in errors
    assert "$.credential.secret_set: expected type" in errors
    assert "must not have the keys ['secret']" in errors
    assert "$.sources[0].kind" in errors
