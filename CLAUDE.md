# Project Notes for Claude

## Python Version

This project requires **Python 3.14+**. This is intentional and correct - Python 3.14 exists and is the minimum supported version for this project.

## Project Overview

CJA SDR Generator - A tool for generating Solution Design Reference (SDR) documentation from Adobe Customer Journey Analytics data views.

## Key Details

- Package manager: uv
- Entry point: `cja_auto_sdr` command (via pyproject.toml scripts)
- Current version: v3.4.0
- Main script: `generator.py` (~10k lines) — subpackages use lazy forwarding via `make_getattr()` in `core/lazy.py`

## CI & Quality

- Run tests: `uv run pytest tests/`
- Coverage gate: **95%** (`--cov-fail-under=95` in `.github/workflows/tests.yml`)
- Linter: `uv run ruff check src/ tests/` (41 active rule sets)
- Formatter: `uv run ruff format src/ tests/`

## Patch Release Gate (Recommended)

For patch releases, run this verification sequence before tagging:

1. `uv run pytest tests/ --collect-only -q`
2. `uv run pytest -q tests/test_generator_mock_contract.py tests/test_backwards_compat.py tests/test_lazy_forwarding.py`
3. `uv run pytest tests/ -x -q`
4. `uv run ruff check src/ tests/`

## Version Bump Checklist

All of these files must be updated when bumping the version:

1. `src/cja_auto_sdr/core/version.py` — `__version__` string
2. `tests/test_ux_features.py` — `test_version_is_X_Y_Z` assertion
3. `tests/test_output_content_validation.py` — 3 version references in test fixtures
4. `CLAUDE.md` — "Current version" above
5. `docs/QUICK_REFERENCE.md` — version string in header
6. `docs/QUICKSTART_GUIDE.md` — version string in output example
7. `CHANGELOG.md` — new version entry

## Test Count Tracking

Test counts appear in **3 places** and are validated by `test_update_test_counts.py`:

1. `README.md` — tree listing comment
2. `tests/README.md` — "Total: N comprehensive tests" line
3. `tests/README.md` — test count breakdown table total row

Always run `uv run pytest tests/ --collect-only -q` to get the accurate count before updating.

## Documentation Sync Checklist

When adding new CLI flags, update these docs:

- `docs/CLI_REFERENCE.md` — options tables and usage examples
- `docs/QUICK_REFERENCE.md` — common options table and quick recipes
- `README.md` — common use cases table
- Feature-specific docs (e.g. `DATA_QUALITY.md`, `DIFF_COMPARISON.md`, `CONFIGURATION.md`)
- `tests/README.md` — tree listing and test count table (if new test files added)

## Test Conventions

- Mock pattern: `@patch('cja_auto_sdr.generator.cjapy')`, `@patch('cja_auto_sdr.generator.configure_cjapy')`
- Output capture: `capsys` (pytest built-in) for stdout/stderr
- File tests: `tmp_path` fixture for temporary directories
- Machine-readable errors go to stderr as JSON
