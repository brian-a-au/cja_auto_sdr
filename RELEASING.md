# Releasing

How to cut a release of `cja-auto-sdr` and publish it to [PyPI](https://pypi.org/project/cja-auto-sdr/).

> Releasing is **human-initiated**. A publish happens only when a maintainer publishes a GitHub Release; agent and unattended runs never publish. See [AGENTS.md](AGENTS.md#releasing).

## How publishing works

`.github/workflows/release.yml` runs on the `release: published` event. It builds the sdist and wheel with `uv build`, validates metadata with `twine check`, verifies the release tag matches the built version, then uploads to PyPI using **Trusted Publishing (OIDC)**. There are no stored API tokens: GitHub Actions mints a short-lived OIDC token that PyPI verifies against the registered publisher (owner `brian-a-au`, repo `cja_auto_sdr`, workflow `release.yml`, environment `pypi`).

## Runbook

### 1. Bump the version

Update `src/cja_auto_sdr/core/version.py` and add a `CHANGELOG.md` entry, then sync the remaining version references. The complete list is the [Version Bump Checklist](CLAUDE.md#version-bump-checklist) — 8 files, validated by `scripts/check_version_sync.py`. Verify locally before opening the PR:

```bash
uv run python scripts/check_version_sync.py
uv run python scripts/update_test_counts.py --check
```

### 2. Merge to `main`

Open a PR with the version bump and merge it once CI is green. The release tag must point at the merged commit on `main`.

### 3. Tag the release

```bash
git tag v<version>            # e.g. git tag v3.11.6
git push origin v<version>
```

Pushing the tag triggers `patch-release-gate.yml`, which re-runs `check_version_sync.py --require-tag` and confirms the tag ref matches the canonical version.

### 4. Publish the GitHub Release

```bash
gh release create v<version> --latest --title "v<version> — <summary>" --notes "..."
```

Publishing the Release fires `release.yml`, which builds and uploads to PyPI. Watch it complete:

```bash
gh run watch --workflow release.yml
```

`gh release create` creates the tag if it does not already exist, so step 3 is optional when you release straight from `main`.

## Notes

- **No tokens.** Publishing uses OIDC Trusted Publishing; there are no PyPI API tokens in the repo or in Actions secrets.
- **Tag/version guard.** `release.yml` fails the build if the release tag does not match the version built from `version.py`, so a mistagged release cannot publish.
- **PyPI is immutable.** A version can never be re-uploaded or overwritten, and a deleted version number cannot be reused. Bump the version for every publish; never retag an existing one.
- **Docs and CI-only changes need no release.** Changes that do not affect the published package (documentation, workflows, tests) ship by merging to `main` — no version bump, tag, or PyPI publish.
- **First publish.** The inaugural release (v3.11.5) created the project on PyPI and converted the pending Trusted Publisher to active; every release since is fully automatic.
