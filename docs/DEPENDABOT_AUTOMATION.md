# Dependabot review and auto-merge

The repository automatically reviews and merges **patch updates to `ruff`,
`pytest`, and `pytest-cov`** when all required CI checks pass on an up-to-date
branch. Other dependency updates remain available for manual review and merge.
This is a deterministic policy review; it does not claim to review arbitrary
upstream source code or to provide an AI review.

## Review policy

`scripts/dependabot_review.py` checks the PR author is the Dependabot bot, both
branches belong to this repository, the target is `main`, and the source is a
`dependabot/uv/` branch. Only an existing `uv.lock` may change.

The reviewer parses the base and head lockfiles and requires:

- Only allowlisted, direct development dependencies change. A dependency
  reachable from the runtime or any optional extra is excluded.
- Versions move forward within the same major and minor version. Prereleases,
  postreleases, downgrades, and nonstandard versions are excluded.
- Dependency metadata, all other packages, and lockfile settings are unchanged.
  Transitive updates, new packages, and ambiguous multiple resolutions require
  manual review.
- Artifacts use the expected PyPI URLs and filenames with SHA-256 hashes. Every
  URL, hash, and size must match PyPI's release metadata; yanked files are rejected.

Malformed lockfiles and API failures fail the check. A well-formed PR outside
the policy passes the check with a **manual merge required** decision and receives
no automatic approval or merge request. SDK updates and GitHub Actions updates
are outside the allowlist.

## Workflow and trust boundary

`dependabot-policy.yml` runs on every PR with a read-only token and checks out
the **base commit's** review script. It reads PR lockfiles as data through the
GitHub API; it never installs PR dependencies or executes PR code.

After a successful required CI workflow run, `dependabot-auto-merge.yml` runs the **main-branch**
script with narrowly scoped write permissions. It resolves the current PR from
the triggering head SHA and repeats the review, including registry verification.
Stale events are ignored. Before approving, it verifies required branch gates, confirms every required
check succeeded, rechecks both base and head SHAs, and verifies the reviewed
head contains current main through the comparison API. The review is attached
to the reviewed commit; `gh pr merge --squash --match-head-commit` uses no
administrator bypass. GitHub enforces the required tests and up-to-date-branch
rule. A pending or failed check causes no write; the next successful workflow
completion retries the review. The bot does not leave a persistent auto-merge
request that could apply to a subsequently changed PR.

The privileged workflow does not consume PR artifacts or caches. Both workflows
use only the Python standard library and pinned actions. No additional secret,
Adobe credential, or external review service is needed.

## Repository settings

The deployment enables **Allow auto-merge** and adds `dependabot-policy` to the
existing required checks, with the GitHub Actions app as the check source:

`build`, `ruff`, `actionlint`, `shellcheck`, `lockfile`, `version-sync`,
`ci-gate`, `dependency-review`, `dependabot-policy`.

Branch protection continues to require up-to-date branches and enforce the
requirements for administrators. Existing review requirements are preserved;
this setup does not introduce a second-maintainer requirement for human PRs.
The dependency-review check rejects newly introduced vulnerabilities of moderate
severity or higher. The test gate covers unit tests with a 95% coverage requirement, integration
and contract tests, Linux/macOS/Windows smoke tests, and builds that smoke-install
the package. CI sync and run commands use `--locked`.

Install the workflow through a normal PR before requiring its new check. Its
first installation PR is explicitly treated as a manual bootstrap because the
trusted base does not contain the review script yet.

## Existing PRs and maintenance

To evaluate an existing PR without changes:

```bash
uv run --no-project --python 3.14 python scripts/dependabot_review.py \
  --repo brian-a-au/cja_auto_sdr --pr 157
```

After installation, dispatch the workflow to review an existing PR under the
same policy and merge if eligible and all required checks have passed:

```bash
gh workflow run dependabot-auto-merge.yml --ref main -f pr=157
```

An old PR must also receive the new required `dependabot-policy` check before
it can merge. Updating its branch through GitHub or a Dependabot rebase triggers
fresh PR checks. If another PR merges first, GitHub requires the remaining PR
to update and retest; automation never bypasses that requirement.

The built-in `GITHUB_TOKEN` does not trigger ordinary push workflows when it
merges a PR. Validation therefore happens before merging; main-branch badge
refresh workflows may need a manual dispatch. Use a separately configured GitHub
App if triggering those downstream workflows becomes necessary.

To pause automatic merging, disable `dependabot-auto-merge.yml`. Keep the policy and existing required CI checks.
Change the allowlist only through a reviewed repository PR.

## Alignment with aa_auto_sdr

Both repositories use the same workflow names, `scripts/dependabot_review.py`,
patch-only allowlist (`ruff`, `pytest`, `pytest-cov`), artifact verification,
trusted-base review, and exact-commit merge behavior. Repository names, root
lockfile package names, required CI contexts, and pytest layouts differ.
AA's runtime `aanalytics2` and CJA's runtime `cjapy` updates stay on the manual
path, along with GitHub Actions updates. The AA setup is managed separately.

Detailed branch-protection reads through REST or GraphQL need administrator
permission and fail with the built-in workflow token. Both implementations use
`GET /repos/{repo}/branches/main`, which exposes protected status, required check
contexts, app bindings, and administrator enforcement using Contents: read.
They also compare base/head ancestry before approving or merging, independently
confirming the PR contains current main. No administrator token is introduced.
CJA additionally traverses downstream optional dependencies when excluding
runtime packages; keep that conservative traversal aligned in AA.

Copilot review is supplementary and requested on new PRs and each new push by
CJA's repository ruleset, subject to Copilot availability and quota. It does not
replace the deterministic policy or CI, and no preview Copilot approval-counting
feature is required. See
[Copilot configuration](https://docs.github.com/en/copilot/how-tos/copilot-on-github/set-up-copilot/configure-code-review).
