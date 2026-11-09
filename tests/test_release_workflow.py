"""Contract tests for .github/workflows/release.yml, codeql.yml, and action pins.

The PyPI trusted publisher is registered for the file name release.yml and
the environment pypi, so these tests pin both names, the tag trigger, and the
rule that only a tag push can publish. PyYAML is not a dependency, so the
workflow is split into blocks by indentation. That is enough for the flat
layout these files use.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

WORKFLOWS = Path(__file__).resolve().parents[1] / ".github" / "workflows"
RELEASE = WORKFLOWS / "release.yml"
CODEQL = WORKFLOWS / "codeql.yml"
TAG_PUSH_ONLY = "github.event_name == 'push' && startsWith(github.ref, 'refs/tags/v')"


def _blocks(lines: list[str], indent: int) -> dict[str, list[str]]:
    """Split lines into ``key -> body lines`` at one indent level."""
    pattern = re.compile(rf"^ {{{indent}}}([A-Za-z][\w-]*):(.*)$")
    blocks: dict[str, list[str]] = {}
    current: str | None = None
    for line in lines:
        match = pattern.match(line)
        if match:
            current = match.group(1)
            blocks[current] = [match.group(2).strip()] if match.group(2).strip() else []
        elif current is not None and line.strip() and not line.lstrip().startswith("#"):
            blocks[current].append(line)
    return blocks


def _scalar(block: list[str], key: str, indent: int) -> str | None:
    for line in block:
        match = re.match(rf"^ {{{indent}}}{re.escape(key)}:\s*(.*)$", line)
        if match:
            return match.group(1).strip()
    return None


def _mapping(block: list[str], key: str, indent: int) -> dict[str, str]:
    inner = _blocks(block, indent)
    return {
        name: _scalar([f"{' ' * (indent + 2)}{line.strip()}"], name, indent + 2) or ""
        for line in inner.get(key, [])
        if (name := line.strip().split(":", 1)[0])
    }


@pytest.fixture(scope="module")
def release() -> dict[str, list[str]]:
    return _blocks(RELEASE.read_text(encoding="utf-8").splitlines(), 0)


@pytest.fixture(scope="module")
def jobs(release) -> dict[str, list[str]]:
    return _blocks(release["jobs"], 2)


def test_trusted_publisher_file_name_is_release_yml() -> None:
    assert RELEASE.is_file()


def test_trigger_is_a_version_tag_push_or_a_manual_dry_run(release) -> None:
    triggers = _blocks(release["on"], 2)

    assert set(triggers) == {"push", "workflow_dispatch"}
    push = _blocks(triggers["push"], 4)
    assert set(push) == {"tags"}
    assert [line.strip() for line in push["tags"]] == ["- 'v*.*.*'"]
    assert triggers["workflow_dispatch"] == []


def test_workflow_default_permissions_are_read_only(release) -> None:
    assert [line.strip() for line in release["permissions"]] == ["contents: read"]


def test_jobs_are_build_publish_and_github_release(jobs) -> None:
    assert list(jobs) == ["build", "publish", "github-release"]


def test_build_runs_for_every_trigger_with_read_only_contents(jobs) -> None:
    build = jobs["build"]

    assert _scalar(build, "if", 4) is None
    assert _mapping(build, "permissions", 4) == {"contents": "read"}


def test_publish_uses_the_pypi_environment_and_oidc_only_on_a_tag_push(jobs) -> None:
    publish = jobs["publish"]

    assert _scalar(publish, "needs", 4) == "build"
    assert _scalar(publish, "if", 4) == TAG_PUSH_ONLY
    assert _scalar(publish, "environment", 4) == "pypi"
    assert _mapping(publish, "permissions", 4) == {"id-token": "write"}


def test_github_release_runs_after_publish_only_on_a_tag_push(jobs) -> None:
    github_release = jobs["github-release"]

    assert _scalar(github_release, "needs", 4) == "publish"
    assert _scalar(github_release, "if", 4) == TAG_PUSH_ONLY
    assert _mapping(github_release, "permissions", 4) == {"contents": "write"}
    assert _scalar(github_release, "environment", 4) is None


def test_only_publish_requests_an_id_token(jobs) -> None:
    holders = [name for name, block in jobs.items() if "id-token" in _mapping(block, "permissions", 4)]

    assert holders == ["publish"]


def test_build_checks_the_tag_changelog_and_installed_wheel(jobs) -> None:
    build = "\n".join(jobs["build"])

    assert "check_version_sync.py --require-tag" in build
    assert '"$GITHUB_REF_NAME" != "v$PKG_VERSION"' in build
    assert "scripts/release_notes.py" in build
    assert "update_test_counts.py --check" in build
    assert "check_pypi_readme_links.py README.md" in build
    assert "check_pypi_readme_links.py dist/packages/*" in build
    assert "twine==7.0.0 check" in build
    assert "--cov-fail-under=95" in build
    assert "uv build --out-dir dist/packages" in build
    assert "--help" in build
    assert "sha256sum -- *.whl *.tar.gz > ../SHA256SUMS" in build


def test_downstream_jobs_verify_digests_before_use(jobs) -> None:
    for name in ("publish", "github-release"):
        assert "sha256sum -c ../SHA256SUMS" in "\n".join(jobs[name]), name


def test_publish_uploads_the_packages_dir(jobs) -> None:
    publish = "\n".join(jobs["publish"])

    assert "uses: pypa/gh-action-pypi-publish@" in publish
    assert "packages-dir: dist/packages/" in publish


def test_github_release_attaches_packages_sums_and_changelog_notes(jobs) -> None:
    github_release = "\n".join(jobs["github-release"])

    assert "uses: softprops/action-gh-release@" in github_release
    assert "body_path: dist/RELEASE_NOTES.md" in github_release
    for asset in ("dist/packages/*.whl", "dist/packages/*.tar.gz", "dist/SHA256SUMS"):
        assert asset in github_release


@pytest.mark.parametrize("workflow", sorted(WORKFLOWS.glob("*.yml")), ids=lambda path: path.name)
def test_every_action_is_pinned_to_a_commit(workflow: Path) -> None:
    uses = re.findall(r"uses:\s*(\S+)", workflow.read_text(encoding="utf-8"))

    assert uses
    unpinned = [ref for ref in uses if not re.fullmatch(r"[\w.-]+/[\w./-]+@[0-9a-f]{40}", ref)]
    assert unpinned == []
    # Dependabot keeps the version comment in step with the SHA; a pin without one is hard to review.
    uncommented = re.findall(r"uses:\s*\S+@[0-9a-f]{40}[ \t]*$", workflow.read_text(encoding="utf-8"), re.MULTILINE)
    assert uncommented == []


def test_codeql_analyzes_python_and_actions_with_security_and_quality() -> None:
    codeql = CODEQL.read_text(encoding="utf-8")

    assert re.findall(r"- language: (\S+)", codeql) == ["python", "actions"]
    assert "security-events: write" in codeql
    assert "queries: security-and-quality" in codeql
