"""Exercise the auto-merge trust boundary with synthetic PRs and lockfiles."""

from __future__ import annotations

import importlib.util
import io
import json
from copy import deepcopy
from pathlib import Path
from unittest.mock import Mock

import pytest

pytestmark = pytest.mark.unit

_spec = importlib.util.spec_from_file_location(
    "dependabot_review", Path(__file__).parents[1] / "scripts" / "dependabot_review.py"
)
assert _spec is not None
assert _spec.loader is not None
review = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(review)


def artifact(name: str, version: str, *, wheel: bool) -> dict:
    suffix = "-py3-none-any.whl" if wheel else ".tar.gz"
    return {
        "url": f"https://files.pythonhosted.org/packages/example/{name.replace('-', '_')}-{version}{suffix}",
        "hash": "sha256:" + "a" * 64,
        "size": 100,
    }


def package(name: str, version: str) -> dict:
    return {
        "name": name,
        "version": version,
        "source": {"registry": "https://pypi.org/simple"},
        "sdist": artifact(name, version, wheel=False),
        "wheels": [artifact(name, version, wheel=True)],
    }


@pytest.fixture
def locks() -> tuple[dict, dict]:
    before = {
        "version": 1,
        "requires-python": ">=3.14",
        "package": [
            {
                "name": "cja-auto-sdr",
                "dependencies": [{"name": "cjapy"}],
                "dev-dependencies": {"dev": [{"name": "ruff"}, {"name": "pytest"}, {"name": "pytest-cov"}]},
            },
            package("ruff", "0.16.8"),
            package("cjapy", "0.5.5"),
            package("pytest", "9.1.0"),
            package("pytest-cov", "7.1.0"),
        ],
    }
    after = deepcopy(before)
    after["package"][1] = package("ruff", "0.16.9")
    return before, after


@pytest.fixture
def pr() -> dict:
    return {
        "number": 122,
        "user": {"login": "dependabot[bot]", "type": "Bot"},
        "state": "open",
        "draft": False,
        "changed_files": 1,
        "base": {"ref": "main", "sha": "base", "repo": {"full_name": review.REPOSITORY}},
        "head": {
            "ref": "dependabot/uv/ruff-0.16.9",
            "sha": "head",
            "repo": {"full_name": review.REPOSITORY},
        },
    }


@pytest.mark.parametrize(("name", "version"), [("ruff", "0.16.9"), ("pytest", "9.1.1"), ("pytest-cov", "7.1.1")])
def test_allowlisted_dev_patches(locks, name, version):
    before, after = locks
    after = deepcopy(before)
    index = next(i for i, item in enumerate(after["package"]) if item["name"] == name)
    after["package"][index] = package(name, version)
    assert review.review_locks(before, after)[0]


@pytest.mark.parametrize("version", ["0.16.8", "0.16.7", "0.17.0", "1.0.0", "0.16.9rc1", "0.16.9.post1"])
def test_reject_non_patch_versions(locks, version):
    before, after = locks
    after["package"][1] = package("ruff", version)
    assert not review.review_locks(before, after)[0]


def test_reject_runtime_sdk_even_with_patch(locks):
    before, after = locks
    after["package"][2] = package("cjapy", "0.5.6")
    assert not review.review_locks(before, after)[0]


@pytest.mark.parametrize("runtime_path", ["direct", "transitive", "optional", "optional-transitive"])
def test_reject_allowlisted_package_if_used_at_runtime(locks, runtime_path):
    before, after = locks
    for lock in (before, after):
        root, _, sdk, *_ = lock["package"]
        if runtime_path == "direct":
            root["dependencies"].append({"name": "ruff"})
        elif runtime_path == "transitive":
            sdk["dependencies"] = [{"name": "ruff"}]
        elif runtime_path == "optional":
            root["optional-dependencies"] = {"extra": [{"name": "ruff"}]}
        else:
            sdk["optional-dependencies"] = {"extra": [{"name": "ruff"}]}
    assert not review.review_locks(before, after)[0]


@pytest.mark.parametrize("change", ["settings", "addition", "removal", "dependencies", "registry"])
def test_reject_other_lockfile_changes(locks, change):
    before, after = locks
    if change == "settings":
        after["requires-python"] = ">=3.15"
    elif change == "addition":
        after["package"].append(package("surprise", "1.0.0"))
    elif change == "removal":
        after["package"].pop()
    elif change == "dependencies":
        after["package"][1]["dependencies"] = [{"name": "surprise"}]
    else:
        after["package"][1]["source"] = {"registry": "https://example.com/simple"}
    assert not review.review_locks(before, after)[0]


@pytest.mark.parametrize(
    "url",
    [
        "http://files.pythonhosted.org/ruff-0.16.9.tar.gz",
        "https://files.pythonhosted.org.example.com/ruff-0.16.9.tar.gz",
        "https://files.pythonhosted.org@evil.example/ruff-0.16.9.tar.gz",
        "https://files.pythonhosted.org/ruff-0.16.8.tar.gz",
        "https://files.pythonhosted.org/other-0.16.9.tar.gz",
        "https://files.pythonhosted.org/ruff-0.16.9.tar.gz?redirect=evil",
    ],
)
def test_reject_artifact_substitution(locks, url):
    before, after = locks
    after["package"][1]["sdist"]["url"] = url
    assert not review.review_locks(before, after)[0]


def test_reject_duplicate_resolution(locks):
    before, after = locks
    after["package"].append(deepcopy(after["package"][1]))
    with pytest.raises(ValueError, match="Multiple resolutions"):
        review.review_locks(before, after)


@pytest.mark.parametrize("change", ["author", "fork", "deleted_fork", "draft", "closed", "base", "actions"])
def test_reject_untrusted_pr_identity(pr, change):
    if change == "author":
        pr["user"] = {"login": "someone", "type": "User"}
    elif change == "fork":
        pr["head"]["repo"]["full_name"] = "someone/cja_auto_sdr"
    elif change == "deleted_fork":
        pr["head"]["repo"] = None
    elif change == "draft":
        pr["draft"] = True
    elif change == "closed":
        pr["state"] = "closed"
    elif change == "base":
        pr["base"]["ref"] = "release"
    else:
        pr["head"]["ref"] = "dependabot/github_actions/checkout"
    assert not review.pr_identity(pr, review.REPOSITORY)


def test_multiple_files_skip_without_fetching_code(pr, monkeypatch):
    pr["changed_files"] = 2
    api = Mock(side_effect=AssertionError("Must not fetch PR files"))
    monkeypatch.setattr(review, "gh_json", api)
    assert not review.evaluate_pr(review.REPOSITORY, pr)[0]
    api.assert_not_called()


@pytest.mark.parametrize("change", ["none", "hash", "size", "url", "yanked"])
def test_registry_provenance(locks, monkeypatch, change):
    before, after = locks
    changed = after["package"][1]
    urls = [
        {"url": item["url"], "digests": {"sha256": item["hash"][7:]}, "size": item["size"], "yanked": False}
        for item in [changed["sdist"], *changed["wheels"]]
    ]
    if change == "hash":
        urls[0]["digests"]["sha256"] = "b" * 64
    elif change == "size":
        urls[0]["size"] = 200
    elif change == "url":
        urls[0]["url"] = "https://example.com/other.tar.gz"
    elif change == "yanked":
        urls[0]["yanked"] = True
    monkeypatch.setattr(review, "urlopen", lambda *_args, **_kwargs: io.StringIO(json.dumps({"urls": urls})))
    if change == "none":
        review.verify_pypi_artifacts(before, after)
    else:
        with pytest.raises(ValueError, match="PyPI metadata"):
            review.verify_pypi_artifacts(before, after)


def gate_responses() -> tuple[dict, dict]:
    return (
        {"allow_auto_merge": True, "default_branch": "main"},
        {
            "protected": True,
            "protection": {
                "enabled": True,
                "required_status_checks": {
                    "contexts": sorted(review.REQUIRED_CHECKS),
                    "checks": [{"context": name, "app_id": 15368} for name in review.REQUIRED_CHECKS],
                    "enforcement_level": "everyone",
                },
            },
        },
    )


@pytest.mark.parametrize("change", ["none", "auto_merge", "unprotected", "admin", "missing_check", "wrong_app"])
def test_fail_closed_when_merge_gates_weakened(monkeypatch, change):
    metadata, branch = gate_responses()
    checks = branch["protection"]["required_status_checks"]
    if change == "auto_merge":
        metadata["allow_auto_merge"] = False
    elif change == "unprotected":
        branch["protected"] = False
    elif change == "admin":
        checks["enforcement_level"] = "non_admins"
    elif change == "missing_check":
        checks["contexts"].remove("ci-gate")
    elif change == "wrong_app":
        checks["checks"][0]["app_id"] = -1
    monkeypatch.setattr(review, "gh_json", Mock(side_effect=[metadata, branch]))
    if change == "none":
        review.verify_merge_gates(review.REPOSITORY)
    else:
        with pytest.raises(ValueError, match="protections"):
            review.verify_merge_gates(review.REPOSITORY)


@pytest.mark.parametrize("changed_ref", ["head", "base"])
def test_changed_commit_cannot_be_approved(pr, monkeypatch, changed_ref):
    current = deepcopy(pr)
    current[changed_ref]["sha"] = "changed"
    api = Mock(return_value=current)
    merge = Mock()
    monkeypatch.setattr(review, "verify_merge_gates", lambda *_args: None)
    monkeypatch.setattr(review, "checks_ready", lambda *_args: True)
    monkeypatch.setattr(review, "gh_json", api)
    monkeypatch.setattr(review.subprocess, "run", merge)
    with pytest.raises(ValueError, match="changed during review"):
        review.apply_review(review.REPOSITORY, pr, "approved")
    assert api.call_count == 1
    merge.assert_not_called()


def test_approval_and_merge_are_bound_to_reviewed_commit(pr, monkeypatch):
    api = Mock(side_effect=[pr, {"behind_by": 0, "status": "ahead"}, {}])
    merge = Mock()
    monkeypatch.setattr(review, "verify_merge_gates", lambda *_args: None)
    monkeypatch.setattr(review, "checks_ready", lambda *_args: True)
    monkeypatch.setattr(review, "gh_json", api)
    monkeypatch.setattr(review.subprocess, "run", merge)
    review.apply_review(review.REPOSITORY, pr, "ruff patch")
    assert api.call_args.args[1]["commit_id"] == "head"
    command = merge.call_args.args[0]
    assert command[command.index("--match-head-commit") + 1] == "head"
    # No persistent auto-merge request can survive a changed, ineligible head.
    assert "--auto" not in command
    assert "--admin" not in command


def test_behind_branch_cannot_be_approved(pr, monkeypatch):
    api = Mock(side_effect=[pr, {"behind_by": 1, "status": "diverged"}])
    merge = Mock()
    monkeypatch.setattr(review, "verify_merge_gates", lambda *_args: None)
    monkeypatch.setattr(review, "checks_ready", lambda *_args: True)
    monkeypatch.setattr(review, "gh_json", api)
    monkeypatch.setattr(review.subprocess, "run", merge)
    review.apply_review(review.REPOSITORY, pr, "ruff patch")
    assert api.call_count == 2
    merge.assert_not_called()


@pytest.mark.parametrize("state", ["PENDING", "FAILURE", "SKIPPED", "CANCELLED"])
def test_incomplete_checks_cannot_merge(monkeypatch, state):
    checks = [{"name": name, "state": "SUCCESS"} for name in review.REQUIRED_CHECKS]
    checks[0]["state"] = state
    monkeypatch.setattr(review.subprocess, "run", Mock(return_value=Mock(returncode=0, stdout=json.dumps(checks))))
    assert not review.checks_ready(review.REPOSITORY, 122)


def test_missing_check_cannot_merge(monkeypatch):
    checks = [{"name": name, "state": "SUCCESS"} for name in review.REQUIRED_CHECKS if name != "ci-gate"]
    monkeypatch.setattr(review.subprocess, "run", Mock(return_value=Mock(returncode=0, stdout=json.dumps(checks))))
    assert not review.checks_ready(review.REPOSITORY, 122)


def test_waiting_for_ci_does_not_approve_or_queue(pr, monkeypatch):
    monkeypatch.setattr(review, "verify_merge_gates", lambda *_args: None)
    monkeypatch.setattr(review, "checks_ready", lambda *_args: False)
    api, merge = Mock(), Mock()
    monkeypatch.setattr(review, "gh_json", api)
    monkeypatch.setattr(review.subprocess, "run", merge)
    review.apply_review(review.REPOSITORY, pr, "ruff patch")
    api.assert_not_called()
    merge.assert_not_called()


def test_stale_workflow_event_ignored(pr, monkeypatch):
    event = {
        "workflow_run": {
            "event": "pull_request",
            "conclusion": "success",
            "head_sha": "old",
            "head_repository": {"full_name": review.REPOSITORY},
        }
    }
    monkeypatch.setattr(review, "gh_json", lambda *_args: [pr])
    assert review.resolve_pr(review.REPOSITORY, event) == (None, None)


def test_failed_workflow_never_fetches_pr(monkeypatch):
    event = {"workflow_run": {"event": "pull_request", "conclusion": "failure"}}
    api = Mock()
    monkeypatch.setattr(review, "gh_json", api)
    assert review.resolve_pr(review.REPOSITORY, event) == (None, None)
    api.assert_not_called()


def test_privileged_workflow_uses_trusted_main_and_check_permissions():
    import re

    workflow = (Path(__file__).parents[1] / ".github/workflows/dependabot-auto-merge.yml").read_text()
    block = re.search(r"    permissions:\n((?:      .+\n)+)", workflow)
    assert block is not None
    permissions = dict(line.strip().split(": ") for line in block[1].splitlines())
    assert permissions == {
        "contents": "write",
        "pull-requests": "write",
        "checks": "read",
        "actions": "read",
    }
    assert "          ref: main\n          persist-credentials: false" in workflow
    assert "          enable-cache: false" in workflow
    assert "uv run --no-project" in workflow
    assert '--apply "${args[@]}"' in workflow
