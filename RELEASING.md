# Releasing

How to cut a release of `cja-auto-sdr` and publish it to [PyPI](https://pypi.org/project/cja-auto-sdr/).

> A maintainer starts every release by pushing a version tag, and then approves the `pypi` deployment. Agent and unattended runs never publish. See [AGENTS.md](AGENTS.md#releasing).

## How publishing works

`.github/workflows/release.yml` runs when a tag that matches `v*.*.*` is pushed. It has three jobs.

1. `build` runs on every trigger. It does these checks and steps:
   - Checks that the tag is `v` plus the version in `src/cja_auto_sdr/core/version.py`.
   - Runs `scripts/check_version_sync.py --require-tag`. This checks the version references in the 8 tracked files, checks that the tag exists, and checks that the tag ref matches the version.
   - Runs `scripts/release_notes.py`, which fails when `CHANGELOG.md` has no section, or an empty section, for the version. The section becomes the GitHub release notes.
   - Runs `scripts/update_test_counts.py --check` and `scripts/check_pypi_readme_links.py README.md`.
   - Runs Ruff, the unit tests with the 95% coverage gate, and the integration, end-to-end, slow, and smoke tests.
   - Builds the wheel and the source package with `uv build`, then runs `twine check` and the README link check on the built files.
   - Checks that the built file names match the version.
   - Installs the wheel into a new environment and runs `cja_auto_sdr --help` and `--version`.
   - Writes `SHA256SUMS` and stores the packages, the sums, and the release notes as the `dist` artifact.
2. `publish` runs only for a tag push. It uses the `pypi` environment, which waits for a maintainer to approve it. It checks the sums and uploads the packages with Trusted Publishing (OIDC).
3. `github-release` runs after `publish`. It checks the sums again and creates the GitHub release. The release has the `CHANGELOG.md` section as its body, and the wheel, the source package, and `SHA256SUMS` as its files.

There are no stored API tokens. GitHub Actions makes a short-lived OIDC token, and PyPI checks it against the registered trusted publisher. The publisher is registered for owner `brian-a-au`, repository `cja_auto_sdr`, workflow `release.yml`, and environment `pypi`. Do not rename the workflow file or the environment, or PyPI rejects the upload.

## Runbook

### 1. Open a PR with the version bump

Update `src/cja_auto_sdr/core/version.py` and add a `CHANGELOG.md` section for the version. Then update the other version references. The full list is the [Version Bump Checklist](CLAUDE.md#version-bump-checklist), and `scripts/check_version_sync.py` checks all 8 files. Run these checks before you open the PR:

```bash
uv run python scripts/check_version_sync.py
uv run python scripts/release_notes.py
uv run python scripts/update_test_counts.py --check
uv build
uvx twine check dist/*
uv run python scripts/check_pypi_readme_links.py dist/*
```

### 2. Merge the PR

`main` is protected, so merge through the PR once all required checks pass:

```bash
gh pr merge <number> --merge
```

### 3. Optional dry run

In GitHub, open Actions, pick the `release` workflow, and click "Run workflow" on `main`. The dry run does every check in `build`, including the build and the installed-wheel smoke test. It skips the tag checks, `publish`, and `github-release`, so it uploads nothing.

```bash
gh workflow run release.yml --ref main
```

### 4. Tag the merged commit

```bash
git switch main && git pull
git tag v<version>            # e.g. git tag v3.13.11
git push origin v<version>
```

Pushing the tag starts `release.yml`.

### 5. Approve the `pypi` deployment

When `build` passes, `publish` waits for approval. Open the run in Actions, click "Review deployments", select `pypi`, and approve it. You can also watch the run from the terminal:

```bash
gh run watch --workflow release.yml
```

### 6. Check PyPI and the GitHub release

- Check that the new version is on <https://pypi.org/project/cja-auto-sdr/>.
- Check that `gh release view v<version>` shows the CHANGELOG notes, the wheel, the source package, and `SHA256SUMS`.

## Notes

- **No tokens.** Publishing uses OIDC Trusted Publishing. There are no PyPI API tokens in the repository or in Actions secrets.
- **Protected tags.** The "Protect release tags" ruleset blocks deleting or moving a `v*` tag.
- **Tag and version guard.** The `build` job fails when the tag does not match the version in `version.py`, so a wrong tag cannot publish.
- **PyPI is immutable.** You can never upload a version again or overwrite it, and you cannot reuse a deleted version number. Bump the version for every publish, and never move an existing tag.
- **A failed run.** If `build` fails, nothing is uploaded. Fix the problem in a new PR with a new version, because the old tag cannot move. If `github-release` fails after `publish` passed, the version is already on PyPI. Rerun the failed job from the run page.
- **Docs and CI-only changes need no release.** Changes that do not affect the published package, e.g. a workflow change, ship by merging to `main` with no version bump, tag, or publish.
