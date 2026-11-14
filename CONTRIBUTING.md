# Contributing to cja_auto_sdr

Thanks for your interest. This project has a narrow scope on purpose. It
generates Solution Design Reference (SDR) documents from Adobe Customer Journey
Analytics data views, and it tracks how those documents change over time.

Please open an issue to discuss a new feature before you write code for it.
Small fixes and documentation corrections can go straight to a pull request.

By taking part, you agree to follow the [Code of Conduct](CODE_OF_CONDUCT.md).
Report security issues privately as described in [SECURITY.md](SECURITY.md). Do
not put a vulnerability, Adobe credentials, or customer data view data in a
public issue or pull request.

The rest of this guide explains how to set up the project, what checks a change
must pass, and how to open a pull request.

## Before you start

Never include real credentials, `config.json`, `.env` files, profile contents,
or output from a real Adobe organization in an issue, a pull request, or a test
fixture. Use made up IDs and names instead.

## Set up

The project uses [uv](https://github.com/astral-sh/uv) and supports Python 3.11
and newer.

```bash
git clone https://github.com/brian-a-au/cja_auto_sdr.git
cd cja_auto_sdr
uv sync --all-extras
```

You do not need Adobe credentials to run the test suite. The tests mock the API.

## Code rules

- Code in `src/`, `tests/`, and `scripts/` must run on Python 3.11. Do not use
  syntax or standard library features added after 3.11.
- Every module under `src/` starts with `from __future__ import annotations`.
- Keep a change focused on one problem. A pull request that fixes one thing is
  easier to review than one that fixes several.

[AGENTS.md](AGENTS.md) describes the CLI contract that automation and coding
agents depend on, e.g., exit codes and output formats. If your change touches
that contract, update AGENTS.md in the same pull request.

## Checks to run

Run these before you open a pull request. CI runs the same checks.

```bash
uv run ruff check src/ tests/ scripts/ examples/
uv run ruff format --check src/ tests/ scripts/ examples/
uv run pytest tests/ -x -q
```

The unit suite must keep at least 95% coverage. Add tests for new behavior and
for each bug you fix.

If you add or remove tests, refresh the test counts in the README files:

```bash
uv run python scripts/update_test_counts.py
```

If you add a new test file, also add a row for it to the table in
[tests/README.md](tests/README.md).

## Documentation

If you add or change a CLI flag, update the docs that describe it. The usual
places are:

- `docs/CLI_REFERENCE.md`
- `docs/QUICK_REFERENCE.md`
- `README.md`
- The guide for that feature, e.g., `docs/DIFF_COMPARISON.md`

Add a short entry for user facing changes under the `[Unreleased]` heading in
[CHANGELOG.md](CHANGELOG.md).

## Pull requests

1. Create a branch from `main`, e.g., `feature/short-name`.
2. Make your change and run the checks above.
3. Open a pull request against `main`. Describe what you changed, why you
   changed it, and how you tested it.

The `main` branch is protected. A pull request can merge only after the
required checks pass and the branch is up to date with `main`.

## Releases

The maintainer handles version bumps and releases to PyPI. Contributors do not
need to change the version number. The full process is in
[RELEASING.md](RELEASING.md).
