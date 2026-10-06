#!/usr/bin/env python3
"""Review lockfile updates without installing or executing PR dependencies.

The write-capable caller must run this file from the default branch. Normal
PR checks run the base-branch copy. Only --apply submits a review and merges
after required checks pass; branch protection remains the final authority.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit
from urllib.request import urlopen

ALLOWED_PACKAGES = frozenset({"ruff", "pytest", "pytest-cov"})
REQUIRED_CHECKS = frozenset(
    {
        "dependabot-policy",
        "build",
        "ruff",
        "actionlint",
        "shellcheck",
        "lockfile",
        "version-sync",
        "ci-gate",
        "dependency-review",
    }
)
REPOSITORY = "brian-a-au/cja_auto_sdr"


def gh_json(endpoint: str, payload: dict[str, Any] | None = None) -> Any:
    command = ["gh", "api", endpoint]
    if payload is not None:
        command.extend(["--method", "POST", "--input", "-"])
    result = subprocess.run(
        command,
        input=json.dumps(payload) if payload is not None else None,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    return json.loads(result.stdout)


def pr_identity(pr: dict[str, Any], repo: str) -> bool:
    return (
        repo == REPOSITORY
        and pr["user"]["login"] == "dependabot[bot]"
        and pr["user"]["type"] == "Bot"
        and pr["state"] == "open"
        and not pr["draft"]
        and pr["base"]["ref"] == "main"
        and pr["base"]["repo"]["full_name"] == repo
        and pr["head"].get("repo") is not None
        and pr["head"]["repo"]["full_name"] == repo
        and pr["head"]["ref"].startswith("dependabot/uv/")
    )


def _packages(lock: dict[str, Any]) -> dict[str, list[dict[str, Any]]]:
    packages: dict[str, list[dict[str, Any]]] = {}
    for package in lock["package"]:
        packages.setdefault(package["name"], []).append(package)
    for resolutions in packages.values():
        resolutions.sort(key=lambda package: json.dumps(package, sort_keys=True))
        if len({json.dumps(package, sort_keys=True) for package in resolutions}) != len(resolutions):
            raise ValueError("Duplicate package resolution")
    return packages


def _runtime_packages(packages: dict[str, list[dict[str, Any]]]) -> set[str]:
    roots = packages["cja-auto-sdr"]
    if len(roots) != 1:
        raise ValueError("Project has multiple resolutions")
    root = roots[0]
    dependencies = list(root.get("dependencies", []))
    for optional in root.get("optional-dependencies", {}).values():
        dependencies.extend(optional)
    pending = [dependency["name"] for dependency in dependencies]
    visited: set[str] = set()
    while pending:
        name = pending.pop()
        if name not in visited:
            visited.add(name)
            # Conservatively consider every platform/Python resolution.
            for package in packages[name]:
                pending.extend(dependency["name"] for dependency in package.get("dependencies", []))
                for optional in package.get("optional-dependencies", {}).values():
                    pending.extend(dependency["name"] for dependency in optional)
    return visited


def _valid_artifact(artifact: dict[str, Any], name: str, version: str, *, wheel: bool) -> bool:
    url = urlsplit(artifact["url"])
    filename = unquote(url.path.rsplit("/", 1)[-1])
    prefix = f"{name.replace('-', '_')}-{version}"
    valid_filename = (
        filename.startswith(f"{prefix}-") and filename.endswith(".whl")
        if wheel
        else filename in {f"{prefix}.tar.gz", f"{prefix}.zip", f"{name}-{version}.tar.gz"}
    )
    return (
        url.scheme == "https"
        and url.netloc == "files.pythonhosted.org"
        and not url.query
        and not url.fragment
        and valid_filename
        and re.fullmatch(r"sha256:[a-f0-9]{64}", artifact["hash"]) is not None
        and isinstance(artifact["size"], int)
        and artifact["size"] > 0
    )


def review_locks(before: dict[str, Any], after: dict[str, Any]) -> tuple[bool, str]:
    """Conservatively approve only direct dev patches with no other changes."""
    if {key: value for key, value in before.items() if key != "package"} != {
        key: value for key, value in after.items() if key != "package"
    }:
        return False, "Lockfile settings changed"
    old, new = _packages(before), _packages(after)
    if old.keys() != new.keys():
        return False, "Packages were added or removed"
    changed = sorted(name for name in old if old[name] != new[name])
    if not changed or not set(changed) <= ALLOWED_PACKAGES:
        return False, "Changes are outside the development-tool allowlist"
    dev = {item["name"] for item in old["cja-auto-sdr"][0]["dev-dependencies"]["dev"]}
    runtime = _runtime_packages(old)
    updates = []
    for name in changed:
        if len(old[name]) != 1 or len(new[name]) != 1:
            return False, f"{name} has multiple resolutions; manual review required"
        previous, updated = old[name][0], new[name][0]
        if name not in dev or name in runtime:
            return False, f"{name} is not exclusively a direct development dependency"
        versions = [re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", package["version"]) for package in (previous, updated)]
        if any(match is None for match in versions):
            return False, f"{name} has a prerelease, postrelease, or nonstandard version"
        old_version, new_version = [tuple(map(int, match.groups())) for match in versions if match is not None]
        if old_version[:2] != new_version[:2] or new_version[2] <= old_version[2]:
            return False, f"{name} is not a forward patch update"
        allowed_fields = {"version", "sdist", "wheels"}
        if {key: value for key, value in previous.items() if key not in allowed_fields} != {
            key: value for key, value in updated.items() if key not in allowed_fields
        }:
            return False, f"{name} dependency metadata changed"
        if updated["source"] != {"registry": "https://pypi.org/simple"}:
            return False, f"{name} is not from PyPI"
        if "sdist" not in updated or not updated.get("wheels"):
            return False, f"{name} is missing distribution artifacts"
        if not _valid_artifact(updated["sdist"], name, updated["version"], wheel=False) or not all(
            _valid_artifact(artifact, name, updated["version"], wheel=True) for artifact in updated["wheels"]
        ):
            return False, f"{name} has unexpected artifact URLs or hashes"
        updates.append(f"{name} {previous['version']} → {updated['version']}")
    return True, "; ".join(updates)


def read_lock(repo: str, sha: str) -> dict[str, Any]:
    content = gh_json(f"repos/{repo}/contents/uv.lock?ref={sha}")
    if content["encoding"] != "base64" or content["size"] > 1_000_000:
        raise ValueError("Unsupported lockfile size or encoding")
    return tomllib.loads(base64.b64decode(content["content"]).decode("utf-8"))


def verify_pypi_artifacts(before: dict[str, Any], after: dict[str, Any]) -> None:
    """Compare every changed artifact with the registry's published metadata."""
    old, new = _packages(before), _packages(after)
    for name, resolutions in new.items():
        if resolutions == old[name]:
            continue
        package = resolutions[0]
        # Called only after review_locks: name is allowlisted and version is
        # numeric, so PR data cannot select another host or endpoint.
        with urlopen(f"https://pypi.org/pypi/{name}/{package['version']}/json", timeout=30) as response:
            published = json.load(response)
        artifacts = {item["url"]: item for item in published["urls"]}
        for artifact in [package["sdist"], *package["wheels"]]:
            match = artifacts.get(artifact["url"])
            if (
                match is None
                or match["yanked"]
                or artifact["hash"] != f"sha256:{match['digests']['sha256']}"
                or artifact["size"] != match["size"]
            ):
                raise ValueError("Artifact differs from PyPI metadata or has been yanked")


def evaluate_pr(repo: str, pr: dict[str, Any]) -> tuple[bool, str]:
    if not pr_identity(pr, repo):
        return False, "PR identity or branch is outside the automated policy"
    # A single-file response cannot be truncated by GitHub's file-list limit.
    if pr["changed_files"] != 1:
        return False, "Only uv.lock may change"
    files = gh_json(f"repos/{repo}/pulls/{pr['number']}/files")
    if len(files) != 1 or files[0]["filename"] != "uv.lock" or files[0]["status"] != "modified":
        return False, "Only an existing uv.lock may be modified"
    before, after = read_lock(repo, pr["base"]["sha"]), read_lock(repo, pr["head"]["sha"])
    eligible, reason = review_locks(before, after)
    if eligible:
        verify_pypi_artifacts(before, after)
    return eligible, reason


def verify_merge_gates(repo: str) -> None:
    # Detailed protection settings (REST and GraphQL) need Administration
    # permission, which GITHUB_TOKEN cannot request. The branch endpoint
    # exposes check contexts, app bindings, and administrator enforcement
    # using Contents: read. Check ancestry separately before any write.
    metadata = gh_json(f"repos/{repo}")
    branch = gh_json(f"repos/{repo}/branches/main")
    protection = branch["protection"]
    checks = protection["required_status_checks"]
    if (
        not metadata["allow_auto_merge"]
        or metadata["default_branch"] != "main"
        or not branch["protected"]
        or not protection["enabled"]
        or not set(checks["contexts"]) >= REQUIRED_CHECKS
        or checks["enforcement_level"] != "everyone"
        or not {check["context"] for check in checks["checks"] if check["app_id"] == 15368} >= REQUIRED_CHECKS
    ):
        raise ValueError("Required auto-merge protections are not configured")


def checks_ready(repo: str, number: int) -> bool:
    result = subprocess.run(
        ["gh", "pr", "checks", str(number), "--repo", repo, "--required", "--json", "name,state"],
        capture_output=True,
        text=True,
        check=False,
        timeout=60,
    )
    # gh returns 1 for failing checks and 8 for pending checks. Invalid API
    # responses still raise; missing required check names never count as ready.
    checks = json.loads(result.stdout)
    return (
        result.returncode == 0
        and {check["name"] for check in checks} >= REQUIRED_CHECKS
        and all(check["state"] == "SUCCESS" for check in checks)
    )


def apply_review(repo: str, pr: dict[str, Any], reason: str) -> None:
    verify_merge_gates(repo)
    if not checks_ready(repo, pr["number"]):
        print("Required CI checks are not all successful; a later completion will retry")
        return
    current = gh_json(f"repos/{repo}/pulls/{pr['number']}")
    if current["head"]["sha"] != pr["head"]["sha"] or current["base"]["sha"] != pr["base"]["sha"]:
        raise ValueError("PR changed during review; wait for a fresh policy run")
    if not pr_identity(current, repo):
        raise ValueError("PR identity changed during review")
    comparison = gh_json(f"repos/{repo}/compare/{pr['base']['sha']}...{pr['head']['sha']}")
    if comparison["behind_by"] != 0 or comparison["status"] != "ahead":
        print("PR does not contain current main; wait for a branch update and fresh CI")
        return
    gh_json(
        f"repos/{repo}/pulls/{pr['number']}/reviews",
        {
            "commit_id": pr["head"]["sha"],
            "event": "APPROVE",
            "body": (
                f"Automatic policy review: {reason}.\n\n"
                "Verified a lockfile-only update of exclusively direct development dependencies, "
                "unchanged dependency metadata, forward patch versions, and PyPI artifact URLs and hashes. "
                "All required CI checks passed. GitHub must also enforce an up-to-date branch at merge time."
            ),
        },
    )
    subprocess.run(
        [
            "gh",
            "pr",
            "merge",
            str(pr["number"]),
            "--repo",
            repo,
            "--squash",
            "--match-head-commit",
            pr["head"]["sha"],
        ],
        check=True,
        timeout=60,
    )


def resolve_pr(repo: str, event: dict[str, Any]) -> tuple[int | None, str | None]:
    if "workflow_run" in event:
        run = event["workflow_run"]
        if (
            run["event"] != "pull_request"
            or run["conclusion"] != "success"
            or run["head_repository"]["full_name"] != repo
        ):
            return None, None
        sha = run["head_sha"]
        matches = [
            pr
            for pr in gh_json(f"repos/{repo}/commits/{sha}/pulls")
            if pr["state"] == "open" and pr["head"]["sha"] == sha and pr["base"]["ref"] == "main"
        ]
        return (matches[0]["number"], sha) if len(matches) == 1 else (None, None)
    if "pull_request" in event:
        return event["pull_request"]["number"], event["pull_request"]["head"]["sha"]
    return None, None


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", required=True, choices=[REPOSITORY])
    parser.add_argument("--pr", type=int)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    expected_sha = None
    number = args.pr
    if number is None:
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text())
        number, expected_sha = resolve_pr(args.repo, event)
    if number is None:
        print("No current PR matches this event; no action")
        return 0
    pr = gh_json(f"repos/{args.repo}/pulls/{number}")
    if expected_sha is not None and pr["head"]["sha"] != expected_sha:
        print("Stale event; wait for a fresh policy run")
        return 0
    eligible, reason = evaluate_pr(args.repo, pr)
    result = {"pr": number, "head_sha": pr["head"]["sha"], "eligible": eligible, "reason": reason}
    print(json.dumps(result))
    if summary := os.environ.get("GITHUB_STEP_SUMMARY"):
        with Path(summary).open("a") as stream:
            stream.write(
                f"### Dependabot policy review\n\nPR #{number}: {'eligible for auto-merge' if eligible else 'manual merge required'}.\n\n{reason}\n"
            )
    if eligible and args.apply:
        apply_review(args.repo, pr, reason)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (KeyError, ValueError, TypeError, OSError, subprocess.SubprocessError) as error:
        # API/parse errors fail closed rather than silently falling back.
        print(f"Dependabot review failed: {type(error).__name__}", file=sys.stderr)
        if isinstance(error, subprocess.CalledProcessError):
            # Commands contain endpoints and public SHAs, never the token.
            print(f"Failed command: {' '.join(error.cmd[:3])} (exit {error.returncode})", file=sys.stderr)
        sys.exit(1)
