# Project Notes for Claude

## Python Version

This project requires **Python 3.14+**. This is intentional and correct — Python 3.14 exists and is the minimum supported version for this project.

> **Note:** Ruff's `target-version` is set to `py313` in `pyproject.toml` because a few forward-annotation sites still trigger py314-only rewrites. The *runtime* floor is 3.14.

## Project Overview

CJA SDR Generator — a CLI tool for generating Solution Design Reference (SDR) documentation from Adobe Customer Journey Analytics data views. Supports single data view SDR generation, batch processing, org-wide analysis, diff comparison, inventory extraction, and discovery commands.

## Key Details

- Package manager: **uv**
- Build system: **hatchling** (dynamic version from `src/cja_auto_sdr/core/version.py`)
- Entry points: `cja_auto_sdr` and `cja-auto-sdr` (both via `__main__:main`)
- Current version: v3.4.8
- Tests: **7,012** across 115 files at **95% coverage gate**
- Dependencies: cjapy, numpy, pandas, xlsxwriter, tqdm
- Optional deps: scipy (clustering), python-dotenv (env), argcomplete (completion)

---

## Source Architecture

### Package Layout

```
src/cja_auto_sdr/
├── __init__.py              # Lazy forwarding (__version__, main → generator)
├── __main__.py              # Fast-path entry point (~550 lines)
├── generator.py             # Main orchestrator (~7K lines, monolithic workhorse)
│
├── api/                     # API client, resilience & caching
│   ├── client.py            # CJA API wrapper + .env bootstrap
│   ├── resilience.py        # Circuit breaker, retry with jitter, batching
│   ├── cache.py             # Response caching with TTL + size limits
│   ├── fetch.py             # Parallel fetching with worker optimization
│   ├── quality.py           # Core data quality validation engine
│   ├── quality_policy.py    # Quality policy metadata
│   └── tuning.py            # API worker auto-tuning
│
├── cli/                     # Argument parsing & command dispatch
│   ├── parser.py            # Complete argparse configuration
│   ├── execution.py         # CLI execution path coordination
│   ├── interactive.py       # Interactive profile/discovery helpers
│   ├── option_resolution.py # Long-option resolution (fast-path)
│   ├── standalone_policy.py # Prevalidation for fast-path flags
│   ├── mode_scoped_options.py # Mode-scoped option validation
│   ├── main.py              # Thin dispatcher
│   └── commands/
│       ├── discovery.py     # Central discovery extraction (canonical source)
│       ├── list.py          # List commands (backwards-compat re-exports)
│       ├── config.py        # --config, --show-config, --stats
│       └── stats.py         # Stats and diagnostics
│
├── core/                    # Utilities, constants & configuration
│   ├── version.py           # __version__ (single source of truth)
│   ├── constants.py         # CLI defaults (BANNER_WIDTH=80, worker limits, cache TTL)
│   ├── config.py            # SDR generation config dataclass
│   ├── config_validation.py # Config validation helpers
│   ├── colors.py            # Console color formatting
│   ├── credentials.py       # API credential resolution
│   ├── exit_codes.py        # Exit code definitions + explainer
│   ├── exceptions.py        # Custom exception hierarchy
│   ├── discovery_exceptions.py  # Discovery-specific exceptions
│   ├── discovery_payloads.py    # Discovery payload classification
│   ├── discovery_normalization.py # Normalization helpers
│   ├── error_policies.py    # Error handling policies
│   ├── json_io.py           # Atomic JSON read/write
│   ├── lazy.py              # make_getattr() factory for lazy forwarding
│   ├── logging.py           # Structured logging with emit_diagnostic()
│   ├── perf.py              # Performance timing utilities
│   ├── profiles.py          # Multi-org profile management
│   └── locks/               # Concurrent org-report locking
│       ├── manager.py       # Lock manager
│       └── backends.py      # File/process lock backends
│
├── diff/                    # Snapshot comparison
│   ├── cli.py               # Diff CLI argument handling
│   ├── commands.py          # Diff command orchestration
│   ├── comparator.py        # Component-level diff engine
│   ├── models.py            # Diff result models
│   ├── snapshot.py          # Snapshot CRUD
│   ├── git.py               # Git integration for snapshots
│   └── writers.py           # Thin delegator → output.diff
│
├── inventory/               # Component inventory extraction
│   ├── calculated_metrics.py # CM extraction & complexity scoring
│   ├── derived_fields.py    # DF extraction with logic summary
│   ├── segments.py          # Segment extraction with complexity
│   ├── utils.py             # Shared inventory utilities
│   └── summary.py           # Delegator
│
├── org/                     # Organization-wide analysis
│   ├── analyzer.py          # Core org report engine
│   ├── models.py            # Org report data models
│   ├── cache.py             # Org report caching
│   ├── snapshot_utils.py    # Org snapshot helpers
│   ├── trending.py          # Drift detection & window queries
│   ├── identifiers.py       # Component ID helpers
│   └── writers/             # Org report renderers
│       ├── __init__.py      # Re-export layer (backwards compat)
│       ├── compat.py        # Override stacking & legacy compat routing
│       ├── common.py        # Shared writer helpers
│       ├── trending.py      # Trending/drift renderers
│       ├── console.py       # Console output writer
│       ├── json.py          # JSON output writer
│       ├── excel.py         # Excel output writer
│       ├── markdown.py      # Markdown output writer
│       ├── html.py          # HTML output writer
│       └── csv.py           # CSV output writer
│
├── output/                  # Output generation
│   ├── protocols.py         # Writer protocol definitions
│   ├── registry.py          # Format registry
│   ├── run_summary.py       # Run summary output helpers
│   ├── writers/             # Format writers (csv, excel, json, html, markdown)
│   ├── sdr/                 # SDR document generators
│   ├── diff/                # Diff renderers (console, grouped, csv, json, html, excel, markdown, pr_comment)
│   └── inventory/           # Inventory summary display
│
└── pipeline/                # Batch processing
    ├── batch.py             # Worker pool coordination
    ├── single.py            # Single data view wrapper
    ├── dry_run.py           # Dry-run mode
    ├── models.py            # Pipeline result models
    └── workers.py           # Worker pool management
```

### Key Architectural Patterns

**Fast-path entry (`__main__.py`):** Handles lightweight flags (`--version`, `--help`, `--exit-codes`, `--completion`, `--explain-exit-code`) in <100ms without importing heavy dependencies (pandas, cjapy, tqdm). Uses `_scan_option_tokens()` to detect flags before full argparse. Falls through to `generator.main()` for everything else.

**Lazy forwarding (`core/lazy.py`):** `make_getattr()` factory creates `__getattr__` handlers for subpackage `__init__.py` files. Avoids import cycles by deferring imports until attribute access. Used throughout all subpackages.

**Discovery system:** Centralized in `cli/commands/discovery.py` (canonical source). `cli/commands/list.py` re-exports for backwards compatibility. Discovery commands (`--list-dataviews`, `--list-connections`, `--list-datasets`) are mutually exclusive via `add_mutually_exclusive_group()`.

**CLI dispatch:** `main()` in generator.py uses a dict loop for discovery dispatch: `_discovery_commands = {'list_dataviews': list_dataviews, ...}`. All discovery/list commands share `_run_list_command()` boilerplate.

**Output routing:** `_emit_output()` handles file, stdout pipe, or console. Machine-readable errors go to stderr as JSON.

### CLI Modes

| Mode | Flag | Description |
|------|------|-------------|
| Single | `cja_auto_sdr <dv_id>` | Generate SDR for one data view |
| Batch | `--batch <ids...>` | Process multiple data views in parallel |
| Org-wide | `--org-report` | Analyze all data views in organization |
| Diff | `--diff <source> <target>` | Compare snapshots |
| Trending | `--trending-window N` | Drift detection over time window |
| Discovery | `--list-dataviews` etc. | List available resources |
| Config | `--config`, `--show-config` | Profile/config management |
| Stats | `--stats` | Diagnostics and statistics |

Fast-path flags (no heavy imports): `--version`/`-V`, `--help`/`-h`, `--exit-codes`, `--explain-exit-code CODE`, `--completion {bash,zsh,fish}`

---

## CI & Quality

### Commands

```bash
uv run pytest tests/                    # Full test suite
uv run pytest tests/ -x -q              # Quick fail-fast run
uv run ruff check src/ tests/           # Lint (41 active rule sets)
uv run ruff format src/ tests/          # Format check
uv run pytest tests/ --collect-only -q  # Get accurate test count
```

### CI Workflows (`.github/workflows/`)

| Workflow | Purpose |
|----------|---------|
| `tests.yml` | Unit tests (95% coverage gate, `-n auto` xdist), integration/e2e/slow tests, run-summary contracts, cross-platform smoke tests, package build |
| `lint.yml` | Ruff check + format, actionlint, shellcheck |
| `version-sync.yml` | `scripts/check_version_sync.py` — single source of truth for version consistency |
| `patch-release-gate.yml` | Release validation (version, changelog, docs, tag ref, test counts) |
| `test-counts.yml` | Validates README test count inventory is current |

### Test Organization

- **Markers:** `unit` (default, auto-applied), `integration`, `e2e`, `slow`, `smoke`, `run_summary_contract`
- **Auto-classification:** `conftest.py` applies markers from `category_rules.py` to all tests automatically
- **Parallelism:** Unit CI slice uses `pytest-xdist` (`-n auto`); no global xdist in `pytest.ini`
- **Coverage:** 95% gate on unit slice (`--cov-fail-under=95`)

### Test Conventions

- Mock pattern: `@patch('cja_auto_sdr.generator.cjapy')`, `@patch('cja_auto_sdr.generator.configure_cjapy')`
- Output capture: `capsys` (pytest built-in) for stdout/stderr
- File tests: `tmp_path` fixture for temporary directories
- Org fixtures: `rich_org_report_result()` in `conftest.py` for renderer/CLI tests

---

## Patch Release Gate (Recommended)

Run this verification sequence before tagging:

```bash
uv run pytest tests/ --collect-only -q                                            # 1. Verify test collection
uv run pytest -q tests/test_generator_mock_contract.py tests/test_backwards_compat.py tests/test_lazy_forwarding.py  # 2. Contract tests
uv run pytest tests/ -x -q                                                        # 3. Full suite
uv run ruff check src/ tests/                                                     # 4. Lint clean
```

---

## Version Bump Checklist

Canonical source: `src/cja_auto_sdr/core/version.py`

All of these files must be updated (validated by `scripts/check_version_sync.py` in CI):

1. `src/cja_auto_sdr/core/version.py` — `__version__` string
2. `tests/test_ux_features.py` — `test_version_is_X_Y_Z` assertion
3. `tests/test_output_content_validation.py` — version references in test fixtures
4. `CLAUDE.md` — "Current version" above
5. `docs/QUICK_REFERENCE.md` — version string in header
6. `docs/QUICKSTART_GUIDE.md` — version string in output example
7. `docs/CONFIGURATION.md` — startup diagnostics version example
8. `CHANGELOG.md` — new version entry (first `## [x.y.z]` heading)

### Release Process

```bash
# After updating all version files:
git tag v<version>
gh release create v<version> --latest
```

---

## Test Count Tracking

Test counts appear in **3 places** and are validated by `test_update_test_counts.py` and CI workflow `test-counts.yml`:

1. `README.md` — tree listing comment
2. `tests/README.md` — "Total: N comprehensive tests" line
3. `tests/README.md` — test count breakdown table total row

Always run `uv run pytest tests/ --collect-only -q` to get the accurate count before updating. The script `scripts/update_test_counts.py` can automate this (use `--check` for validation only).

---

## Documentation Sync Checklist

When adding new CLI flags, update these docs:

- `docs/CLI_REFERENCE.md` — options tables and usage examples
- `docs/QUICK_REFERENCE.md` — common options table and quick recipes
- `README.md` — common use cases table
- Feature-specific docs (e.g. `DATA_QUALITY.md`, `DIFF_COMPARISON.md`, `CONFIGURATION.md`)
- `tests/README.md` — tree listing and test count table (if new test files added)

### Documentation Inventory (`docs/`)

22 files covering: quickstart, CLI reference, quick reference, configuration, installation, use cases, agent automation, org-wide analysis, diff comparison, data quality, batch processing, output formats, performance, git integration, shell completion, troubleshooting, failure codes, data view names, inventory overview, calculated metrics inventory, derived fields inventory, segments inventory.

---

## Scripts (`scripts/`)

| Script | Purpose |
|--------|---------|
| `check_version_sync.py` | Validates version consistency across 8 files against canonical source |
| `update_test_counts.py` | Updates/validates test counts in README files (`--check` for CI) |
| `orchestrator.py` | Subprocess orchestration for programmatic automation |
| `github_actions_audit.py` | GitHub Actions workflow audit helper |
| `create_sample_outputs.py` | Generate sample output files |
| `stress_test.py` | Load/performance testing utilities |

---

## Ruff Configuration

- **41 active rule sets** including: pycodestyle, pyflakes, isort, pyupgrade, bugbear, simplify, bandit (security), pytest-style, pandas-vet, numpy, perflint, and more
- **Line length:** 120
- **Key ignores:** E501 (formatter handles), S101 (assert ok), PT011/PT012 (pytest flexibility), COM812 (formatter conflict)
- **Per-file ignores:** Extensive — see `pyproject.toml [tool.ruff.lint.per-file-ignores]`
  - `generator.py`: F401 (re-exports), T201 (CLI output), RUF001/3 (Unicode symbols)
  - `tests/**`: Relaxed B, SIM, PERF, security, and print rules
  - `*/__init__.py` in subpackages: F822 (lazy forwarding `__getattr__`)
