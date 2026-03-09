# Changelog

<!-- markdownlint-disable -->

All notable changes to the CJA SDR Generator project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.4.0] - 2026-03-08

### Added
- **Org-report temporal trending**: `--trending-window N` computes metrics across the last N cached org-report snapshots, with per-data-view drift scoring (weighted composite: component change 0.4, core/isolated ratio 0.2, similarity shift 0.2, presence change 0.2).
- **Trending output in all 6 formats**: trending snapshots, deltas, and drift scores render in console, JSON, Excel, Markdown, HTML, and CSV output formats.
- **OrgReportTrending data model**: new `TrendingSnapshot`, `TrendingDelta`, and `OrgReportTrending` dataclasses with backwards-compatible `to_comparison()` bridge to existing `OrgReportComparison`.
- **Org-report snapshot maintenance commands**: `--list-org-report-snapshots`, `--inspect-org-report-snapshot`, and `--prune-org-report-snapshots` expose the persistent trending history directly for inspection and cleanup.

### Changed
- **Structural decomposition**: extracted ~2,980 LOC from `generator.py` into subpackages (`org/writers/`, `output/sdr/`, `api/quality_policy.py`) with full lazy-forwarding re-exports preserving all existing imports.
- **Bounded org-report history retention**: runs using `--trending-window` now prune persisted org-report snapshots automatically after saving the current run, preventing unbounded cache growth while preserving a useful recent window.

## [3.3.9] - 2026-03-06

### Fixed
- **Normalized SDR artifact reporting**: single-format SDR runs now return the actual emitted artifact path for CSV, JSON, HTML, and Markdown instead of a synthesized Excel-style filename.
- **Multi-artifact open behavior**: `--format all` and other multi-artifact SDR runs now preserve the full emitted artifact list and `--open` consumes that normalized contract instead of a guessed primary path.
- **Partial artifact visibility**: exploratory `--allow-partial` SDRs now embed `Partial Output` and `Partial Reasons` markers directly in generated Excel, JSON, HTML, and Markdown metadata.

### Changed
- **Additive run summary artifact contract**: run-summary result entries now include additive `output_files` alongside the compatibility `output_file` field, while keeping `summary_version` at `1.1`.
- **Output/result finalization hardening**: SDR output-path selection, run-summary serialization, and batch result propagation now share normalized helper paths to reduce drift without changing CLI mode behavior.
- **CI script quality baseline**: CI-executed utility scripts remain under Ruff coverage in the main lint workflow, aligning repository quality gates with executed automation paths.

### Added
- **Artifact contract regressions**: expanded tests for single-format output selection, multi-artifact run summaries, `--open` handling, partial metadata propagation, and batch artifact reporting.

## [3.3.8] - 2026-03-05

### Fixed
- **Fail-closed SDR generation on partial fetch failures**: `process_single_dataview()` now refuses to generate partial SDRs when metrics or dimensions fetches fail unexpectedly, instead of treating transport/runtime failures as empty component sets.
- **Fail-closed validation runtime failures**: data-quality validator/runtime failures now abort SDR generation for standard runs, aligning normal SDR behavior with `quality_report_only` failure semantics.
- **Inventory summary module drift**: `process_inventory_summary()` now uses the in-repo calculated-metrics and segments inventory builders instead of undeclared external compatibility modules.
- **Profile test secret handling**: `test_profile()` now uses in-memory `cjapy` configuration instead of writing profile credentials to a temporary config file.

### Changed
- **Per-endpoint fetch outcome tracking**: `ParallelAPIFetcher` now records explicit success/empty/failed statuses for metrics, dimensions, and dataview lookups so callers can distinguish empty results from fetch failures.
- **In-memory cjapy configuration**: env/profile credentials now configure `cjapy` directly, and startup performs best-effort cleanup of stale temp credential files left by older releases.
- **Run summary schema contract**: `summary_version` is now `1.1`; result entries include additive `partial_output` and `partial_reasons` fields for `--allow-partial` observability.
- **Quality policy defaults**: policy files now support optional `allow_partial` (boolean, default `false`) with explicit CLI flags retaining precedence.

### Added
- **Regression coverage for fail-closed behavior**: Added tests covering partial fetch failure aborts, validation-runtime aborts, direct `cjapy` credential configuration, stale temp-file cleanup, and in-repo inventory summary imports.
- **Failure code registry doc**: added `docs/FAILURE_CODES.md` as the public registry for stable run-summary `failure_code` values.

## [3.3.7] - 2026-03-05

### Fixed
- **Exception narrowing (batch 4)**: 30+ broad `except Exception` handlers narrowed across `api/quality.py` (6), `diff/git.py` (2), `locks/backends.py` (3), `diff/snapshot.py` (2), `core/logging.py` (3), `api/cache.py` (2), `api/client.py` (2), `core/config_validation.py`, `core/colors.py`, `org/cache.py`, and `generator.py` (3) to specific exception types
- **Intentional boundary annotations**: 12 remaining broad `except Exception` handlers annotated with `# Intentional:` rationale at resilience boundaries (dotenv bootstrap, dataview lookup, open-file helpers, lock metadata, connection tests)

### Changed
- **Centralized error policies**: New `core/error_policies.py` module defines named exception tuples (`RECOVERABLE_GIT_SUBPROCESS_EXCEPTIONS`, `RECOVERABLE_LOCK_METADATA_PARSE_EXCEPTIONS`, etc.) for consistent use across resilience boundaries
- **Centralized resilient lock and git error boundaries**: Lock and git helpers now reference shared exception policy tuples instead of inline exception lists
- **Hardened logging safety boundaries**: Logging initialization and helper functions use narrowed exception types with clearer fallback behavior
- **Hardened dotenv/bootstrap fallbacks**: Bootstrap and dataview error normalization paths use explicit exception policies

### Added
- **Exception narrowing regression tests**: Expanded `test_exception_narrowing.py` with tests verifying narrowed boundaries catch expected types and propagate unexpected ones across all batch 4 modules
- **Exception contract tests**: New `test_exception_contracts.py` validating error policy tuple contents and boundary annotation consistency
- **Logging redaction tests**: New `test_logging_redaction.py` with tests for logging safety boundary edge cases
- **Git integration tests**: Expanded `test_git_integration.py` with narrowed exception boundary coverage
- **Snapshot tests**: Expanded `test_snapshot.py` with narrowed exception boundary coverage

### Docs
- **Quick Reference consistency**: Standardized Output column in Four Main Modes table to list supported file formats consistently across all modes

## [3.3.6] - 2026-03-04

### Fixed
- **Validate-config color behavior**: `validate_config_only` status lines now route through `ConsoleColors.success/error/warning/info` so `--no-color` and `NO_COLOR` are consistently honored.
- **Org failure accounting consistency**: Org-report writers and JSON aggregations now consistently treat `error is not None` as fetch failure (including empty error strings) so failure counts and non-unique totals cannot drift.
- **Analyzer failure contract hardening**: `OrgComponentAnalyzer` now uses explicit failure semantics (`has_error`) for indexing, recommendations, caching, owner summaries, and distribution pre-processing so blank error messages cannot be misclassified as success.
- **Org report failure diagnostics**: Org-report data-view rows now emit `Unknown error` for blank failure messages instead of an empty cell, in both CSV and Excel outputs.

### Changed
- **Type hygiene**: `ProcessingConfig.shared_cache` and `WorkerArgs.shared_cache` narrowed from `Any` to `SharedValidationCache | None` for safer typing without API changes.
- **Docstring modernization**: `OutputWriter` protocol example updated to modern type syntax (`list[dict[str, Any]] | None`).
- **Exception intent clarity**: Remaining broad `except Exception` handlers in `org/analyzer.py` are now explicitly documented with `# Intentional:` rationale comments at resilience boundaries.
- **Interactive warning clarity**: `--interactive` warning now explicitly states that positional data view arguments are ignored.
- **Release gate hardening**: `check_version_sync.py --require-tag` now also verifies `GITHUB_REF` exactly matches `refs/tags/v<canonical>` when running under tag CI refs.
- **Version-gate diagnostics**: `check_version_sync.py` now reads files as UTF-8 explicitly and provides clearer release-tag diagnostics for non-git contexts and missing local tags (including `git fetch --tags` guidance).
- **Version-sync coverage**: `check_version_sync.py` now validates the `CLAUDE.md` "Current version" reference as part of canonical version checks.
- **Manual release-gate safety**: `patch-release-gate.yml` now supports manual dispatch with optional `require_tag` strictness to avoid accidental false failures when no local tag context exists.

### Added
- **CLI docs coverage**: Added `--metrics-only` and `--dimensions-only` coverage to README, quick reference, quickstart, and CLI reference.
- **CLI color-policy regression test**: Added `_main_impl` coverage proving `--validate-config --no-color` suppresses ANSI output even when `FORCE_COLOR=1`.
- **Org JSON failure telemetry detail**: Added `data_view_fetch_failures.failure_reason_counts` as an additive field for fetch-failure reason rollups.

## [3.3.5] - 2026-03-03

### Fixed
- **Profile error routing**: 19 bare `print()` error calls in profile management now route through `ConsoleColors.error()` to stderr with color styling
- **CLI help text**: Parser description corrected from "System Design Records" to "Solution Design Reference"; exit code 3 added to epilog
- **Format fallback warnings**: Discovery and profile-list commands now warn when an unsupported format falls back to console output
- **Console format error routing**: Console format error messages now go to stderr instead of stdout
- **Validate-config next-step hint**: `--validate-config` now suggests next steps on success
- **LRU overwrite behavior**: `ValidationCache.put()` correctly handles insert and overwrite cases with `move_to_end()` after assignment
- **Discovery stdout CSV format**: CSV output preserved on stdout for discovery commands; format resolver hardened

### Changed
- **Exception narrowing (batch 3)**: 9 broad `except Exception` catches narrowed — 6 to `(RuntimeError, AttributeError)` and 3 to `RECOVERABLE_API_EXCEPTIONS`; plus 4 broad handlers in `api/fetch.py` explicitly retained with `# Intentional:` boundary annotations
- **Config/bootstrap exception boundaries**: `_load_cja_config` and `_bootstrap_cja` narrowed from bare `Exception` to `(FileNotFoundError, KeyError, ValueError, TypeError)`
- **Redundant API call eliminated**: Removed `validate_data_view()` call from `process_single_dataview`; validation now occurs post-fetch via `assess_dataview_lookup_payload`, saving one API round-trip per data view
- **Dataview lookup validation unification**: Runtime and dry-run paths now share `assess_dataview_lookup_payload`, eliminating duplicated validation logic
- **Error classification extraction**: Dataview not-found detection extracted from `generator.py` into new `core/discovery_exceptions.py` module with `coerce_http_status_code()`, `iter_error_chain_nodes()`, `extract_http_status_codes()` helpers
- **Cache capacity extraction**: Inline eviction logic in `put()` and `SharedValidationCache` extracted into dedicated methods (`_ensure_capacity_for_new_entry`, `_remove_entry`) for clarity and testability
- **Parallel inventory builds**: Inventory construction in `process_single_dataview` now uses `ThreadPoolExecutor` for concurrent builds
- **O(1) LRU eviction**: `ValidationCache` refactored from dict + access-times to `OrderedDict` with O(1) eviction
- **Vectorized column widths**: Excel column-width calculation uses pandas vectorized string operations instead of Python loops

### Added
- **Dataview lookup validation**: New `DataViewLookupAssessment` dataclass with multi-layered validation — failure flags, error shape detection, missing identity, ID mismatch, unknown placeholders (`core/discovery_payloads.py`)
- **Dataview error classification**: New `core/discovery_exceptions.py` module — robust HTTP status-code extraction from nested error chains, `is_dataview_lookup_not_found_error()` for 403/404 detection
- **Dataview payload error detection**: `DATAVIEW_EXPLICIT_ERROR_KEYS` + `is_dataview_error_payload` for structured error classification
- **Placeholder detection**: `_unknown_lookup_placeholder_reason` + legacy placeholder detection for backwards compatibility
- **Cache capacity maintenance**: `_ensure_capacity_for_new_entry()` with defensive eviction bound and fallback clear; `_remove_entry()` helper for consistent cache+metadata cleanup; `_evict_lru()` returns success indicator with fallback eviction when access metadata drifts; shutdown race condition fixed
- **Cache and inventory concurrency**: `SharedValidationCache._reconcile_access_times()` handles metadata drift between Manager dicts; inventory parallelization with safe main-thread assignment
- **Profile format fallback diagnostics**: `_resolve_command_output_format` with warning emissions for unsupported format fallbacks
- **Optional component count fallbacks**: Component count extraction in `process_single_dataview` hardened with safe `int` coercion and fallback defaults
- **Exception narrowing tests**: New `test_exception_narrowing.py` with 26 tests verifying narrowed boundaries catch expected types and propagate unexpected ones, including config/bootstrap and component count fallbacks
- **Coverage hardening tests**: New `test_coverage_hardening.py` with 108 tests covering previously-missed branches (output-dir access, lazy forwarding, logging init, discovery helpers, short-option clusters, config validation)
- **Discovery payload tests**: New `test_discovery_payloads.py` with 60 tests — edge cases including exotic types, ID validation, canonicalization, metadata presence, failure-flag precedence
- **Discovery exception tests**: New `test_discovery_exceptions.py` with 5 tests — HTTP status code extraction from nested error chains, not-found classification
- **Dry-run hardening tests**: 14 expanded tests in `test_dry_run.py` for dataview lookup validation in dry-run mode
- **Shared cache tests**: Additional tests for eviction, overwrite, cross-process recovery, and capacity-maintenance regression guards
- **Process single dataview tests**: Expanded with post-fetch validation cases (empty lookup, None lookup, unknown placeholders, error placeholders, legacy unknown placeholders, ID mismatch)
- **CLI integration tests**: Expanded with dataview lookup error routing, canonicalization fallbacks, and payload shape validation end-to-end

## [3.3.4] - 2026-02-25

### Added
- **Shell completion setup**: New `--completion bash/zsh/fish` flag prints activation scripts for shell tab-completion. Fast-path — no heavyweight imports needed. Prints install instructions if argcomplete is not installed.
- **Run summary environment metadata**: `--run-summary-json` output now includes an `environment` block with Python version, platform, and dependency versions (cjapy, pandas, numpy, xlsxwriter, tqdm) for CI/CD diagnostics
- **Startup dependency versions**: Startup diagnostics now log core dependency versions at INFO level (e.g. `Dependencies: cjapy=0.2.4, pandas=2.3.3, ...`) alongside the existing Python/platform line
- **Profile list org_id display**: `--profile-list` now reads and displays the `org_id` from each profile's configuration, making it easy to distinguish profiles for multi-org users. Follows `.env` overrides `config.json` precedence.
- **Enhanced config validation**: `--validate-config` expanded from 3-step to 5-step process — now checks Python version compatibility, core/optional dependency versions, output directory write permissions in addition to credentials and API connectivity

### Changed
- **Narrowed exception handling (batch 2)**: 13 broad `except Exception` catches in generator.py replaced with specific exception types (`OSError`, `KeyError`, `TypeError`, `ValueError`). 15 remaining intentional boundaries annotated with `# Intentional:` comments documenting why they remain broad.

## [3.3.3] - 2026-02-23

### Fixed
- **Pager hardening**: `$PAGER` values containing arguments (e.g. `less -F -X`) are now parsed correctly via `shlex.split`; malformed values fall back to `less -R` instead of crashing
- **Machine-readable error envelopes**: All discovery and `--stats` error paths now include a stable `error_type` field (`configuration_error`, `connectivity_error`) in JSON error output for programmatic consumers
- **Org-report stdout validation message**: Error message now correctly states that `--output stdout` supports both `--format json` and `--format console`, matching actual validation behavior
- **stderr/stdout contract**: `show_stats` machine-readable errors now consistently route to stderr (previously some paths wrote to stdout)

### Changed
- **Explicit UTF-8 encoding**: All command output file writes (`open()`, `to_csv()`, `Popen.communicate()`) now specify `encoding="utf-8"` to remove locale-dependent behavior
- **Discovery filter efficiency**: Filter/exclude operations in `_apply_discovery_filters_and_sort` now compute searchable text blobs once instead of separately per filter pass
- **CI release gates**: Version-sync check (`check_version_sync.py`) now runs as part of the main test workflow; version-sync workflow path filters removed so it runs on all PRs

### Added
- **Generator mock contract tests**: New `test_generator_mock_contract.py` freezes key symbols relied on by test mocks, catching silent breakage during future modularization
- **CLI smoke tests**: New `test_cli_smoke_modes.py` validates top-level dispatch for SDR, diff, discovery, org-report, and profile modes plus fast-path `--version`/`--exit-codes` regression protection

## [3.3.2] - 2026-02-20

### Added
- **Discovery Inspection Commands**: Five new commands for drilling into individual data view resources without generating a full SDR:
  - `--describe-dataview <ID_OR_NAME>` — Show detailed metadata and component counts (metrics, dimensions, segments, calculated metrics)
  - `--list-metrics <ID_OR_NAME>` — List all metrics in a data view with `--filter`/`--exclude`/`--sort`/`--limit` support
  - `--list-dimensions <ID_OR_NAME>` — List all dimensions in a data view with `--filter`/`--exclude`/`--sort`/`--limit` support
  - `--list-segments <ID_OR_NAME>` — List all segments/filters scoped to a data view with owner and governance fields
  - `--list-calculated-metrics <ID_OR_NAME>` — List all calculated metrics with type, polarity, and governance fields
- **Data View Name Resolution**: All five inspection commands accept data view names in addition to IDs (`dv_...`), matching the diff mode pattern. Names are resolved via the API with `--name-match` support (exact, insensitive, fuzzy). Ambiguous names prompt for interactive disambiguation.
- All five commands support `--format console/json/csv`, `--output`, and `--profile` for multi-org workflows
- Graceful degradation: `--describe-dataview` shows "N/A" for component counts when API permissions are limited
- **Terminal-aware text wrapping**: All five discovery inspection commands now wrap long text (e.g. descriptions) at the terminal width instead of overflowing horizontally
- **Shared discovery normalization helpers**: Extracted common owner/date/component normalization into reusable core utilities

### Fixed
- **Name resolution efficiency**: `--describe-dataview` now calls `getDataView()` (single) instead of `getDataViews()` (all) to avoid an expensive API round-trip
- **Not-found exit code**: `--describe-dataview` returns exit code 1 with a machine-readable `error_type=not_found` on stderr when the requested resource is missing
- **NaN/NA identity handling**: Discovery inspection commands no longer crash on `pd.NA`, `pd.NaT`, or `float('nan')` values in API payloads; these are coerced to display-safe placeholders
- **Table wrapping edge cases**: Fixed column-width calculation when non-last columns already exceed terminal width
- **Hidden component consistency**: Component counts now consistently exclude hidden items across all five inspection commands
- **Ignored-option warnings**: Commands that don't support `--filter`/`--sort`/`--limit` now warn when those flags are passed instead of silently ignoring them

### Changed
- **Canonical data view names**: Inspection output now uses the API-returned data view name rather than the user-supplied input, ensuring consistent display
- **Owner/date alias normalization**: List commands normalize variant field names (e.g. `ownerFullName` vs `owner`) to stable column headers across different API response shapes
- **JSON output contracts**: Hardened JSON envelopes across discovery and snapshot commands to guarantee consistent key ordering and type contracts
- **Typed error handling**: Dataview lookup errors now raise typed exceptions with structured diagnostics instead of generic strings

## [3.3.1] - 2026-02-18

### Added
- **Startup fast-path**: `--version` / `-V` and `--exit-codes` now resolve in under
  100 ms by bypassing heavyweight imports (pandas, cjapy, tqdm) via lightweight
  `__main__.py` entry point
- **`-V` short flag**: Added `-V` as a convenience alias for `--version`
- **CLI parser extraction**: Extracted `parse_arguments()` into `cli/parser.py` module
  for better code organization (~1,280 lines moved out of generator.py)
- **CLI option resolution**: Extracted `cli/option_resolution.py` with
  `resolve_long_option_token()` for argparse-compatible abbreviation handling
- **Exit-code deduplication**: Extracted `print_exit_codes()` into `core/exit_codes.py`
  to keep fast-path and full-path output in sync
- **Exception policy constants**: 10 named `RECOVERABLE_*_EXCEPTIONS` tuples
  centralising error-boundary definitions across all command handlers
- **Exception contract tests**: `test_exception_contracts.py` with 10 tests verifying
  error-boundary behaviour across CLI command handlers
- **CI smoke tests**: Added Windows and macOS smoke-test jobs for fast-path commands
  and parser/contract tests
- **Startup performance benchmarks**: Added benchmarks to `docs/PERFORMANCE.md`

### Fixed
- **Typed exception handling**: Replaced ~35 broad `except Exception` catches with
  specific typed exception tuples (`RECOVERABLE_API_EXCEPTIONS`,
  `RECOVERABLE_CONFIG_API_EXCEPTIONS`, etc.) for better error diagnostics
- **Transport failure handling**: Graceful handling of `ConnectionError`,
  `BrokenProcessPool`, and other transport failures across all discovery commands,
  interactive flows, org-reports, inventory lookups, diff/snapshot flows, and
  dry-run validation
- **Data view description coercion**: Non-string `description` payloads from the API
  now coerce safely instead of crashing on string-slicing operations
- **Stats command resilience**: One broken data view no longer aborts the entire
  `--stats` command; error rows are returned per-item instead
- **Git-commit snapshot re-fetch**: Snapshot re-fetch in `--git-commit` flow is now
  non-fatal — prints a warning and continues instead of aborting
- **Run-summary prefix matching**: Fixed false-positive detection triggered by `--run`
  alone; now requires `--run-summary-` prefix
- **Argcomplete bypass**: Fast-path correctly defers during tab-completion mode
- **Version banner consistency**: Fast-path version banner now matches the program
  name argparse would use (e.g. `python -m cja_auto_sdr` vs `cja_auto_sdr`)

## [3.3.0] - 2026-02-17

### Added
- **Coverage push to 99%**: Added ~650 tests across 13 new test files covering
  generator.py edge cases, diff commands, org writers, interactive discovery,
  CLI paths, and remaining uncovered lines
- **CI coverage threshold**: Raised `--cov-fail-under` from 90% → 95%

### Fixed
- **Metadata fallback bug**: Fixed `process_single_dataview` metadata fallback
  DataFrame using 1-column structure when downstream code expected 2 columns
  (Property/Value)

### Changed
- Marked unreachable code with `pragma: no cover` (optional argcomplete import,
  dead inventory imports, regex-guarded ValueError)

## [3.2.9] - 2026-02-16

### Added
- **Ruff rule expansion**: Enabled 16 new rule sets — FLY, FA, YTT, PD, SLOT,
  ICN, EXE, INT, NPY, AIR, ASYNC, INP, ERA, Q, COM, TCH — bringing total
  from 25 → 41 active rule sets; auto-fixed ~938 trailing comma violations
- **CI coverage threshold**: Raised `--cov-fail-under` from 85% → 90%

### Tests
- Added ~258 tests across 4 new test files:
  - `test_diff_inventory_output.py`: Inventory diff output across all formats
    (console, JSON, HTML, Excel, Markdown, CSV, PR comment)
  - `test_cli_command_handlers.py`: CLI dispatch for --stats, --org-report,
    --list-snapshots, --prune-snapshots, inventory summary, diff config unpacking
  - `test_profile_management.py`: Interactive profile creation, import, test, show
  - `test_snapshot_commands.py`: Snapshot creation, comparison, name resolution

## [3.2.8] - 2026-02-16

### Added
- **Ruff rule expansion**: Enabled 4 new rule sets — T (flake8-print),
  LOG (flake8-logging), ARG (unused arguments), FURB (refurb) — with targeted
  per-file suppressions for intentional CLI print output and test fixtures
  (21 → 25 active rule sets)
- **CI coverage threshold**: Raised `--cov-fail-under` from 80% → 85%

### Tests
- Added ~900 tests across 8 new/expanded test files:
  - `test_lock_backend_edge_cases.py`: Metadata I/O failures, stale lock
    reclamation, legacy format parsing, process detection edge cases
  - `test_derived_fields_coverage.py`: Complexity scoring, logic summary
    handlers, predicate description, type inference
  - `test_org_analyzer_coverage.py`: Governance thresholds, stale detection,
    naming audit, stratified sampling, memory warnings, drift computation,
    feature flags, recommendations, clustering, owner summary
  - `test_diff_coverage.py`: Diff comparator, models, and git integration
    edge cases
  - `test_segments_coverage.py`: Segment comparison operators, container
    types, predicate counting, sequence variants
  - `test_api_coverage.py`: API cache, quality, fetch, and resilience
    exception paths
  - `test_small_module_coverage.py`: Logging, utils, calculated metrics,
    constants, lazy forwarding, tuning, lock manager, org cache
  - `test_generator_coverage.py`: Generator utility functions — coercion,
    normalization, diff formatting, name resolution

## [3.2.7] - 2026-02-15

### Changed
- **Lazy-forwarding standardization**: Converted 4 hand-rolled `__getattr__` implementations (`cli/`, `git/`, `data/`, `output/`) to use the centralized `make_getattr()` helper from `core/lazy.py`, narrowing open `hasattr()` catch-alls to explicit name lists
- **Phantom export cleanup**: Removed 4 stale lazy exports (`DiffChange`, `format_output`, `OUTPUT_FORMATS`, `generate_output_files`) that referenced symbols never defined in `generator.py`
- **Compatibility note**: The removed lazy exports were stale placeholders and not functional public APIs; supported import paths are unchanged

### Added
- **Ruff rule expansion**: Enabled ISC (implicit string concat), TID (tidy imports), A (builtins), PLE (pylint errors), RSE (unnecessary parens on raise), PLW (pylint warnings) — 6 new rule sets with targeted suppressions
- **CI coverage threshold**: Raised `--cov-fail-under` from 73% to 80%

### Fixed
- **Documentation accuracy**: Corrected output filename patterns in `QUICK_REFERENCE.md` from `SDR_<name>_<date>` to actual `CJA_DataView_<Name>_<ID>_SDR` pattern; updated `PERFORMANCE.md` stale version reference
- **PLW3301**: Flattened 5 nested `max()` calls to use star-unpacking
- **RSE102**: Removed unnecessary parentheses on 2 bare `raise` statements

### Tests
- Added 55 tests in `test_lazy_forwarding.py`:
  - 9 direct unit tests for `core/lazy.py` `make_getattr()` helper (target module, mapping, error cases, iterable types)
  - 34 parametrized positive tests across all 12 lazy-forwarding modules
  - 12 negative tests verifying `AttributeError` for unknown attributes

## [3.2.6] - 2026-02-14

### Changed
- **Exception handler normalization**: Audited `except` clauses across 12 source files; unparenthesized `except A, B:` form is valid and idiomatic per PEP 758 (Python 3.14+), enforced by ruff formatter
- **Silent exception handlers**: Added debug logging to 6 bare `except Exception:` handlers for improved debuggability
- **Performance micro-optimizations**: Cached redundant `len()`, `df.iloc[]`, and `str()` calls in hot paths; converted list to set for O(1) membership checks

### Added
- **CI: Coverage threshold gate** (`--cov-fail-under=73`) prevents coverage regression
- **CI: Package build verification** job validates wheel builds, installs, and version imports correctly
- **CI: Version sync check** (`scripts/check_version_sync.py`) catches version string drift across docs, tests, and source
- **Ruff rule sets**: Enabled S (bandit), C4 (comprehensions), PT (pytest-style), PIE with targeted suppressions

### Fixed
- **Ruff violations**: `usedforsecurity=False` on md5 cache hashing, `dict.fromkeys()` for constant-value dicts, removed unnecessary `list()` in `sorted()`, merged `endswith()` calls, replaced `pass` with `...` in abstract methods
- **Test robustness**: `pytest.approx()` for all computed float assertions; split compound `assert a and b` into separate assertions
- **Missed exception handlers**: Fixed 3 `except subprocess.TimeoutExpired, FileNotFoundError:` clauses in `diff/git.py` that the initial regex sweep missed (dotted exception names)

### Tests
- Added 912 tests across 10 new test files for core module coverage:
  - `test_colors.py` (121): ConsoleColors formatting, themes, TTY detection
  - `test_exceptions.py` (64): All 13 custom exception classes
  - `test_logging_redaction.py` (136): Sensitive data redaction, JSON formatter
  - `test_config_dataclasses.py` (88): Config dataclasses and constants
  - `test_lock_manager.py` (48): Lock acquire/release/heartbeat lifecycle
  - `test_api_client.py` (25): API client exception paths
  - `test_config_validation.py` (55): Configuration validation logic
  - `test_credentials.py` (67): Credential resolution and sources
  - `test_perf.py` (7): Performance utilities
  - `test_snapshot.py` (72): Diff snapshot creation and comparison
- Expanded `test_calculated_metrics_inventory.py` from 44 to 273 tests
- **2,651 tests** (2,649 passing, 2 skipped) — up from 1,739

## [3.2.5] - 2026-02-13

### Fixed
- **Inventory parsing hardening**: All three inventory parsers (derived fields, segments, calculated metrics) now handle unexpected API payload shapes — non-dict list entries, non-string func/name/context values, dict-shaped args, non-list operands/preds/checkpoints, non-finite split indexes, and non-string delimiters/patterns — without crashing
- **Datetime metadata preservation**: `pd.Timestamp` values in created/modified fields are now coerced via `isoformat()` instead of being silently dropped to empty strings
- **Split index coercion**: Non-finite float indexes (`NaN`, `Inf`, `-Inf`) in derived field split definitions now fall back to the default index instead of raising `OverflowError`

### Changed
- **Centralized normalization helpers**: Extracted `normalize_func_name`, `coerce_scalar_text`, and `coerce_display_text` into `inventory/utils.py` so all three builders share identical coercion logic, eliminating implementation drift
- **Enhanced startup logging**: Log initialization now emits Python version, platform, active log level, and inferred run mode (batch/single/discovery) alongside the tool version for easier troubleshooting

### Documentation
- **DATA_QUALITY.md**: Added Inventory Parsing Resilience section documenting how parsers handle malformed API payloads
- **CONFIGURATION.md**: Added Startup Diagnostics section documenting the enhanced startup log line

### Tests
- Added edge-case tests for non-dict payloads, non-string func names, non-list operands/preds, dict-shaped args, non-finite split indexes, non-string delimiters/patterns/datasets, non-dict branch items, datetime metadata preservation, and timestamp description coercion
- **1,739 tests** (1,737 passing, 2 skipped) — up from 1,712

## [3.2.4] - 2026-02-13

### Security
- **Sensitive data redaction in logs**: Added `SensitiveDataFilter` that automatically redacts API keys, client secrets, access tokens, refresh tokens, passwords, and Bearer tokens from all log output — covers both snake_case and camelCase field names, quoted/unquoted key-value pairs, and exception payloads
- **Exception payload redaction**: Formatted exception stack traces are filtered through the same redaction patterns, protecting credentials that appear in error messages

### Fixed
- **Inventory-summary `--log-format` propagation**: `--log-format json` was silently ignored in inventory-summary mode; now propagated correctly
- **Handler flush on error paths**: Early-exit flush loops only touched `logger.handlers`, missing propagated root handlers; replaced with `flush_logging_handlers()` helper that flushes both
- **Derived field inventory parsing resilience**: Pandas NaN/NA checks on tuple/array edge cases could raise `ValueError`; broadened exception handling to prevent crashes on malformed field definitions
- **Derived field URL parse dict-component handling**: `url-parse` definitions where `component` is an object (for example `{"func":"query","param":"utm_campaign"}`) no longer trigger `TypeError: cannot use 'dict' as a dict key`; parser now normalizes dict-shaped component payloads safely
- **Runtime version observability in logs**: Log initialization now records `CJA SDR Generator version: <version>` so run logs clearly show which build executed

### Changed
- **Structured JSON logging**: New `JSONFormatter` emits ISO-timestamped, machine-readable log records with process/thread metadata and custom extra fields when `--log-format json` is used
- **Structured logging context**: Added `with_log_context()` helper that enriches loggers with persistent contextual fields (`run_mode`, `data_view_id`, `batch_id`) for correlation-friendly telemetry
- **Production DQ log noise reduction**: Individual per-issue HIGH/CRITICAL data quality warnings suppressed in `--production` mode; replaced with an aggregated high-severity summary signal

### Tests
- Added redaction filter tests for Bearer tokens, API keys, quoted/unquoted secrets, camelCase variants, exception payloads, and idempotent double-processing
- Added JSON formatter tests for ISO timestamps, process/thread metadata, and custom record fields
- Added inventory-summary log-format propagation and handler-flush regression tests
- Added structured log context injection tests
- Added production-mode DQ warning suppression and summary signal tests
- Added derived field inventory parsing hardening tests for malformed payloads
- Added derived inventory regression test for dict-shaped `url-parse.component` payloads
- Added logging setup regression test to assert emitted SDR tool version line
- **1,712 tests** (1,710 passing, 2 skipped) — up from 1,686

### Release Notes
- Backport note: This patch set is suitable for `v3.2.4` maintenance branches without a version bump, including the `url-parse` dict-component derived-field fix and startup log version stamping.

## [3.2.3] - 2026-02-12

### Fixed
- **HTML diff severity styling**: Severity styling was applied to the header row instead of data rows, and the last data row was silently dropped from output
- **SharedValidationCache pickle failure**: Added `__getstate__`/`__setstate__` so cache survives `ProcessPoolExecutor` round-trips with `--shared-cache --workers > 1`
- **retry_with_backoff implicit None return**: Wrapper could implicitly return `None` if the retry loop exited without returning or raising; now raises `RuntimeError`
- **Heartbeat TOCTOU race**: Race between heartbeat and `release()` could cause spurious "lock lost" events when a lock was intentionally released
- **HTML diff null metadata handling**: Diff output no longer crashes when metadata fields are `None`
- **DST snapshot parsing**: Snapshot timestamp parsing now handles DST-ambiguous timestamps correctly
- **Dotenv bootstrap ordering**: `load_dotenv()` now runs before CLI env-default parsing, ensuring `.env` values are available for argparse defaults
- **Dotenv profile resolution**: Restored correct dotenv loading during profile resolution
- **Snapshot timestamp normalization**: Snapshot retention now normalizes timestamps consistently for age-based pruning
- **Inventory parsing hardening**: Calculated metrics, derived fields, and segments inventory parsers now handle mixed API payload shapes (missing keys, unexpected types) without crashing
- **Stale metadata recommendations**: Restored stale metadata recommendation output in relevant contexts
- **Parallel validation cache bleed**: `_run_optimized_validation` used a shared-list slice to collect issues for caching; under concurrent execution two threads could capture each other's issues. Replaced with a per-call `local_issues` list so cache writes are isolated
- **Environment credential strict validation**: `CredentialResolver` now applies strict validation to environment credentials, preventing malformed values (e.g. invalid org ID, too-short secrets) from being silently accepted — falls back to config file instead
- **Diff false-positive on list ordering**: Inventory list fields (`functions_used`, `metric_references`, `segment_references`, `dimension_references`, `tags`) are now compared order-insensitively, eliminating false modifications when the API returns elements in a different order
- **Snapshot version upgrade for empty inventories**: `DataViewSnapshot` now upgrades to v2.0 when inventory fields are explicitly present but empty (`[]`), not only when truthy
- **`format_iso_date` non-string input**: Handles non-string API payload values (int, dict, list) by coercing to string instead of raising `TypeError`
- **Org report description recommendation denominator**: Missing-description threshold now excludes errored data view fetches from the denominator, preventing inflated thresholds that suppressed valid recommendations

### Security
- **HTML diff output escaping**: Added `html.escape()` to all diff HTML output — `diff.id`, `diff.name`, metadata names/IDs, and summary table headers were previously inserted as raw HTML
- **Credential file permissions**: Temp credential file in `test_profile()` now created with `0o600` permissions instead of default umask

### Performance
- **Deferred dotenv loading**: `load_dotenv()` moved from import-time to lazy `_bootstrap_dotenv()` call, eliminating filesystem I/O during module import
- **Vectorized org analyzer**: Replaced `iterrows()` with vectorized pandas operations for metric/dimension name capture and derived/standard counting (10-100x faster for large data views)

### Changed
- Enforced timezone-aware datetimes across all modules (DTZ ruff rule); all `datetime.now()` calls use `datetime.now(UTC)`
- Cleaned up 52 unnecessary else-after-return patterns (RET ruff rule)
- Enriched `pyproject.toml` with license, classifiers, and `[project.urls]` metadata

### Tests
- Added 57 new unit tests for quality policy functions (`normalize_quality_severity`, `count_quality_issues_by_severity`, `has_quality_issues_at_or_above`, `aggregate_quality_issues`, `load_quality_policy`, `apply_quality_policy_defaults`) and run summary inference (`_normalize_exit_code`, `_infer_run_status`, `_coerce_run_mode`)
- Added `ProcessPoolExecutor` round-trip test for `SharedValidationCache` pickle support
- Added CJA initialization tests for `configure_cjapy` and dotenv bootstrap
- Added diff comparison tests for HTML null metadata handling and DST snapshot parsing
- Added inventory parsing tests for calculated metrics, derived fields, and segments with mixed API payloads
- Added output format tests for HTML severity row styling
- Added org report vectorized analyzer tests
- Added parallel validation cache isolation test with interleaving coverage
- Added strict credential validation and resolver fallback tests
- Added diff order-insensitive list comparison test for inventory fields
- Added snapshot v2.0 upgrade test for empty inventory arrays
- Added `format_iso_date` non-string input test
- Added org report description recommendation denominator test
- **1,686 tests** (1,684 passing, 2 skipped) — up from 1,668

## [3.2.2] - 2026-02-08

### Added
- New `--run-summary-json PATH` output for machine-readable run metadata across all CLI modes (supports file or stdout)
- Discovery enhancements for `--list-dataviews`, `--list-connections`, and `--list-datasets`:
  - shared `--filter`, `--exclude`, `--limit`, and `--sort` behavior
- New data view resolution mode flag `--name-match` with `exact`, `insensitive`, and `fuzzy` strategies
- Snapshot lifecycle commands:
  - `--list-snapshots` to inspect snapshot inventory from `--snapshot-dir`
  - `--prune-snapshots` to run retention-only cleanup without diff execution
- New `--quality-policy PATH` to load quality defaults from JSON (`fail_on_quality`, `quality_report`, `max_issues`) with explicit CLI flags taking precedence
- New non-interactive profile onboarding flow:
  - `--profile-import NAME FILE`
  - `--profile-overwrite` for controlled replacement of existing profiles

### Fixed
- **HTML escaping**: Replaced manual `.replace("<", "&lt;").replace(">", "&gt;")` with `html.escape()` in 3 locations (metadata values, diff tables, inventory diff tables), properly handling `&`, `"`, and `'` in addition to `<` and `>`
- **DataFrame HTML escaping**: Changed `df.to_html(escape=False)` to `escape=True` so metric/dimension values containing HTML entities are rendered safely
- **Credential file race condition**: Profile creation and import now use atomic `os.open()` with `0o600` permissions instead of `open()` followed by `chmod()`, closing the window where credentials were world-readable
- **SharedValidationCache resource leak**: Added `atexit.register(self.shutdown)` so the multiprocessing manager is cleaned up even if `shutdown()` is never called explicitly
- **Secret echo on headless systems**: Removed `getpass` fallback that silently used `input()` (echoing secrets to terminal); now prints an error and returns `False` when no TTY is available
- **Git snapshot commit safety**: `git_commit_snapshot()` now stages only snapshot paths for the targeted data view ID instead of `git add .`, preventing unrelated repository changes from being committed
- **Git init false-success path**: `git_init_snapshot_repo()` now checks and propagates `git add` / `git commit` failures instead of reporting initialization success when either command fails
- **Org-report lock liveness**: `OrgReportLock._is_process_running()` now treats `PermissionError`/EPERM as process-alive to avoid stale-lock takeover of active runs
- **Org-report lock architecture hardening**: lock coordination now routes through `cja_auto_sdr.core.locks` with `LockManager`/`LockInfo` backend orchestration (`fcntl` preferred, `lease` fallback) and optional backend override via `CJA_LOCK_BACKEND`
- **Org-report lock ownership model**: moved lock ownership semantics to backend primitives (OS advisory lock or lease ownership) instead of JSON parse state
- **Scoped lock refactor (v3.2.2 hardening)**: lock primitive state and metadata persistence are now separated (`*.lock` + atomic `*.lock.info` sidecar), preventing metadata corruption/write failures from changing lock ownership semantics
- **Typed acquisition outcomes**: backend acquisition now uses explicit outcomes (`acquired`, `contended`, `backend_unavailable`, `metadata_error`) to prevent non-contention runtime failures from being misreported as lock contention
- **Manager write-failure safety**: removed lock-path unlink cleanup from metadata write-failure handling; manager now releases backend handles without mutating ownership path state, avoiding cross-process unlink races
- **Lease unknown-probe stale recovery**: when `flock` probing is unavailable (e.g., non-`fcntl` platforms), lease acquisition now allows stale marker recovery for missing metadata instead of permanent contention lockout
- **Legacy metadata parse safety**: lock parsing now guards non-finite/out-of-range legacy timestamps and integer coercions (`pid`/`version`), preventing malformed lock payloads from crashing acquisition
- **Ownership-guarded sidecar cleanup**: sidecar deletion now requires lock-id and inode consistency checks in lease release/reclaim paths, and fcntl unsupported fallback no longer unlinks sidecars opportunistically
- **Missing-metadata race hardening**: both `lease` and `fcntl` now treat fresh metadata-missing lock files as transient contention and only reclaim after a bounded stale grace window, preventing startup races from creating concurrent owners
- **Lease bootstrap ownership verification**: lease acquire now verifies lock-path inode identity after marker+sidecar writes and retries when ownership changed mid-bootstrap, ensuring only one contender can complete acquisition
- **Fcntl write-failure recovery marker**: failed initial metadata writes now emit a best-effort stale tombstone sidecar before release to avoid prolonged false contention from fresh metadata-missing residues
- **Lease fallback race handling**: fresh unreadable lock files now use bounded retry + immediate reclamation, avoiding long stale-timeout blocks while preventing takeover during transient write windows
- **Lease fallback crash recovery**: same-host dead PID detection now reclaims stale holders immediately instead of waiting full stale timeout
- **Runtime flock compatibility fallback**: when `fcntl.flock()` is available at import time but unsupported by the target filesystem at runtime (`ENOTSUP` / `EOPNOTSUPP` / `ENOSYS`), lock acquisition now downgrades to the lease backend instead of being misreported as active contention
- **Lease heartbeat split-brain protection**: lease metadata updates are now file-descriptor-bound to the original lock inode, preventing stale holders from overwriting a newer owner’s lock metadata after reclamation
- **Fail-closed lock ownership handling**: heartbeat metadata write failures now mark lock ownership as lost and force backend release, preventing long-running local work from continuing after remote contenders can legally reclaim
- **Analyzer lock-health enforcement**: org-report analysis now performs lock-health checks between major phases and during parallel fetch completion, aborting immediately if ownership is lost mid-run
- **Fail-closed parallel fetch shutdown**: when lock ownership is lost during org-report DV fetch, pending executor futures are cancelled and the pool is torn down with `wait=False, cancel_futures=True` to stop unlocked work promptly
- **Lock-loss wait polling**: org-report parallel fetch now polls lock health on timed future waits (`wait(..., FIRST_COMPLETED)`) so ownership loss is detected even when no futures have completed yet
- **PID liveness probe hardening**: same-host stale checks now reject invalid/special PID values (`<=0`, bools, overflow cases) before probing, preventing malformed lock metadata from causing crashes or false contention
- **Boolean PID parse hardening**: lock metadata parsing now rejects boolean `pid` values in both modern and legacy payloads, avoiding accidental coercion to `0/1` that can create false non-reclaimable lock ownership
- **Cross-backend lock exclusivity**: `fcntl` acquisition now honors active non-`fcntl` lock metadata (including `lease` holders), preventing concurrent takeover when processes use different lock backends
- **Local PID stale-age protection**: same-host live PIDs no longer expire solely due age thresholds, preventing active lock takeover when timestamps become old
- **Mixed-backend open-race hardening**: `fcntl` lock acquisition now uses atomic create/open semantics and always validates pre-existing lock metadata after open, preventing `lease`/`fcntl` concurrent holders under create-time races
- **Metadata-write failure lockout prevention**: failed lock metadata writes now trigger best-effort lock-file cleanup to avoid leaving fresh unreadable artifacts that cause long false lock contention windows
- **Path-disappearance race hardening**: `fcntl` acquisition now verifies lock-path/inode identity and retries when the lock path disappears or is replaced mid-acquire, preventing handles on unlinked inodes
- **Inode-safe write-failure cleanup**: lock-file cleanup after metadata write failure now only unlinks when the path still matches the failed handle’s inode, preventing deletion of a new owner’s lock file
- **Stale unreadable fcntl lock recovery**: stale/unreadable pre-existing lock files are now reclaimed in-place by the current holder instead of looping into persistent false contention
- **Remote fcntl takeover protection in lease mode**: lease staleness checks now probe active `flock` state for remote `fcntl` owners, blocking takeover while an active remote lock is still held
- **Local fcntl-to-lease handoff correctness**: staleness checks now evaluate `fcntl` lock state before same-host PID liveness so released `fcntl` metadata from long-lived processes does not block lease acquisition indefinitely
- **Legacy lock metadata compatibility**: lock-file parsing now accepts legacy `{pid,timestamp,started_at}` payloads, preserving stale-lock recovery behavior after upgrade
- **Legacy metadata parse hardening**: malformed legacy `version` values are now safely defaulted instead of raising parsing exceptions during lock acquisition
- **Windows lease release reliability**: lease release now closes file descriptors before unlink attempts and retries path removal, preventing stuck lock files on platforms that disallow unlink of open files
- **Lease release recovery fallback**: if path unlink repeatedly fails, release writes an explicit stale tombstone marker so contenders can recover without waiting for process exit
- **Main entrypoint global side effects**: Removed global `sys.exit` monkeypatching in `main()` while preserving `--run-summary-json stdout` JSON-only output behavior
- **Retry env parsing and backoff bounds**: Invalid, negative, or non-finite `MAX_RETRIES` / `RETRY_BASE_DELAY` / `RETRY_MAX_DELAY` values now safely fall back to defaults, and invalid delay windows are clamped to prevent negative sleep durations or skipped retries
- **Batch early-stop cleanup**: Batch processor now cancels remaining futures on exception stop paths and guarantees shared-cache shutdown via `finally`
- **Org cache observability**: `OrgReportCache` now logs warnings on cache load/save failures instead of silently swallowing I/O errors
- **Snapshot diff guidance typo**: Corrected invalid remediation command shown for missing inventory snapshot data (removed nonexistent `--sdr` flag)
- **Data view cache isolation by credential context**: Data view name-resolution cache keys now include credential/profile context, preventing stale cache reuse across different profiles using the same config path
- **Org-report sample bound validation**: `--sample` now requires values of at least `1` with fast validation in both CLI argument handling and analyzer execution
- **Strict profile import validation**: Non-interactive `--profile-import` now enforces strict credential format checks and reports full validation issues before writing profile config
- **Org-report recommendation output fidelity**: Recommendation context is now normalized and preserved across HTML, Markdown, JSON, CSV, and Excel outputs, including data view pair details and non-primitive context values
- **Org-report stdout preflight validation**: Unsupported `--org-report --output -` format combinations and unknown formats are now rejected before org analysis starts, preventing expensive fail-late execution
- **Derived field depth logic summary**: `_describe_depth_logic` now includes the delimiter in its output instead of silently discarding the fetched value
- **Lock metadata retry safety**: `_read_info_with_retries` now initializes `legacy_candidate` before the retry loop, preventing a potential `UnboundLocalError` if the loop body is refactored
- **Lock backend fallback AttributeError masking**: `LockManager._acquire_with_result` now uses `hasattr` instead of a broad `except AttributeError`, preventing internal backend bugs from being silently swallowed as missing-method fallback
- **Lock backend swap thread safety**: `LockManager.acquire()` now assigns the fallback backend under `_state_lock`, preventing concurrent readers from seeing a partially swapped backend reference
- **Lock sidecar atomic-write cleanup**: `_write_info_path` now cleans up the temp file when `os.replace` fails, preventing orphaned temp files on cross-device or permission errors
- **Org cache atomic write**: `OrgReportCache._save_cache` now writes to a temp file and atomically renames, preventing truncated/corrupt cache files from mid-write crashes

### Tests
- Added `test_e2e_integration.py` — 16 end-to-end integration tests that mock only the API boundary and exercise the full pipeline (output writers, DQ checker, special character handling)
- Added `test_main_entry_points.py` — 19 tests for `main()` and `_main_impl()` dispatch, exit codes, run_state tracking, and run summary JSON emission
- Added `test_malformed_api_responses.py` — 19 negative tests for malformed API data (wrong types, missing columns, exceptions, partial responses)
- Added `test_output_content_validation.py` — 26 tests validating output file content across CSV, JSON, HTML, Excel, and Markdown formats (roundtrip correctness, escaping, cross-format consistency)
- Fixed flaky `test_cache_ttl_expiration` — replaced `time.sleep(1.5)` with mocked `time.time()` for deterministic TTL testing
- Added `tests/test_lock_backends.py` coverage for lease bootstrap metadata, transient unreadable-file handling, persistent corrupt-file recovery, and heartbeat refresh behavior
- Added lock regression coverage for runtime `flock` unsupported fallback and stale-holder metadata overwrite prevention in lease mode
- Added lock regression coverage for mixed-backend contention (`lease` vs `fcntl`) and same-host live-PID stale-age protection
- Added lock regression coverage for mixed-backend create-time race handling and metadata-write failure cleanup behavior
- Added lock regression coverage for mid-acquire path disappearance retries and inode-safe cleanup guards after metadata write failures
- Added lock regression coverage for stale unreadable `fcntl` metadata reclamation and remote active-`fcntl` takeover prevention in lease mode
- Added lock regression coverage for same-host `fcntl` handoff to lease and legacy lock-metadata stale recovery
- Added lock regression coverage for malformed legacy-version parsing and write-failure release safety
- Added lock regression coverage for lease release close-before-unlink ordering and unlink-failure recovery behavior
- Added lock refactor coverage for sidecar metadata semantics and release-on-write-failure behavior without manager unlink cleanup
- Added lock regression coverage for stale/fresh missing-metadata behavior when flock probing is unavailable in lease mode
- Added lock regression coverage for malformed legacy numeric metadata (`NaN`/`Infinity`/out-of-range epochs) to ensure acquisition fails safe instead of raising
- Added lock regression coverage for release/reclaim sidecar cleanup races to verify new-owner metadata is preserved under contention
- Added lock regression coverage to ensure fcntl unsupported fallback preserves pre-existing sidecar metadata
- Added lock regression coverage for fresh-vs-stale missing-metadata behavior in both `lease` and `fcntl` acquisition paths
- Added lock regression coverage for fail-closed heartbeat ownership loss in `LockManager` and analyzer-level abort-on-lock-loss behavior
- Added lock regression coverage for immediate executor cancellation when lock ownership is lost during parallel DV fetch loops
- Added lock regression coverage for invalid/special PID metadata handling to ensure stale-lock recovery remains safe and reclaimable
- Added lock regression coverage for timeout-based lock-loss detection while fetch futures are still running (no-completion window)
- Added lock regression coverage for rejecting boolean `pid` lock metadata and reclaiming stale malformed sidecars safely
- Expanded `tests/test_org_report.py` with multi-process contention and crash-recovery tests for both default and `lease` lock backends
- Added targeted regression tests for:
  - Git init failure propagation and data-view-scoped staging behavior
  - Org lock PermissionError liveness semantics
  - Org cache save warning visibility
  - Invalid retry env var fallback behavior (CLI + runtime)
  - Batch cancellation/shutdown behavior on exception and interrupt paths
  - Data view cache isolation by credential context during name resolution
  - `--org-report --sample` negative value rejection in both CLI and analyzer paths
  - Strict non-interactive profile import rejection for invalid credential formats
  - Retry config guards for negative env values and invalid delay windows
  - Org-report recommendation context/serialization coverage across HTML, Markdown, JSON, CSV, and Excel outputs
  - Org-report stdout/output-format preflight validation (including fail-fast no-analysis assertions)
- **1,668 tests** (1,666 passing, 2 skipped) — up from 1,607

### Changed
- Removed `.python-version` from repo; `requires-python` in `pyproject.toml` is sufficient

## [3.2.1] - 2026-02-06

### Highlights
- **Connection Discovery** - List all accessible CJA connections with their datasets using `--list-connections`
- **Dataset Discovery** - List all data views with their backing connections and datasets using `--list-datasets`
- **Permissions Fallback** - When the API service account lacks product-admin privileges, both commands gracefully fall back to deriving connection IDs from data views instead of failing
- **Mutually Exclusive Discovery** - `--list-dataviews`, `--list-connections`, and `--list-datasets` are now mutually exclusive at the CLI level
- **CI Quality Gates & Reports** - Added quality policy exits via `--fail-on-quality` and standalone issue exports via `--quality-report`
- **GitHub Step Summaries** - Added automatic Markdown summaries for diff, quality, and org-report output in GitHub Actions
- **Snapshot Auto-Prune Defaults** - Added default retention behavior for `--auto-prune` with explicit-flag precedence

### Added

#### Connection & Dataset Discovery
- New `--list-connections` flag to list all accessible connections with their datasets
- New `--list-datasets` flag to list all data views with their backing connections and dataset details
- Both commands support `--format json/csv` and `--output` for machine-readable output
- Both commands support `--profile` for multi-org credential selection
- Permissions fallback: when `GET /data/connections` returns empty (service account not a CJA Product Admin), connection IDs are derived from data view `parentDataGroupId` fields with an informative warning
- Shared `_run_list_command()` boilerplate for all discovery commands (profile resolution, CJA config, banner, error handling)
- Output routing via `_emit_output()` — handles file, stdout pipe, or console output

#### CLI Improvements
- Discovery commands (`--list-dataviews`, `--list-connections`, `--list-datasets`) are now mutually exclusive via argparse `add_mutually_exclusive_group()`

#### CI, Quality & Snapshot Controls
- Added global ANSI color controls across all output paths via `--no-color`, `NO_COLOR`, and `FORCE_COLOR`
- Added `--fail-on-quality SEVERITY` for SDR mode to return exit code `2` when quality thresholds are exceeded
- Added standalone quality issues reporting with `--quality-report json|csv` (file or stdout)
- Added automatic GitHub Actions step summaries for diff, quality, and org-report output when `GITHUB_STEP_SUMMARY` is set
- Added `--auto-prune` defaults for diff auto-snapshot flows (`--keep-last 20` + `--keep-since 30d` when retention flags are omitted)

### Fixed
- Rejected unsupported quality gate combinations: `--fail-on-quality` now errors outside SDR mode and when combined with `--skip-validation`
- Corrected quality-report failure semantics: processing failures now still exit `1` even with `--continue-on-error`, and write failures are reported as clean CLI errors instead of uncaught tracebacks
- Corrected GitHub quality summaries to include failed and successful data views in processed counts
- Corrected diff GitHub summary totals to include inventory-only changes (calculated metrics and segments)
- Corrected auto-prune retention precedence: explicit values are preserved, including `--keep-last 0`, `--keep-last=0`, `--keep-since 90d`, and `--keep-since=90d`
- Corrected empty CSV quality reports to emit a stable header row for zero-issue runs

### Testing
- Added tests for `--list-connections` table, JSON, CSV output and no-results handling
- Added tests for `--list-datasets` table, JSON, CSV output with multi-dataset connections
- Added tests for permissions fallback paths (empty connections with data view derivation)
- Added tests for mutual exclusivity of discovery commands
- Test count: 1,275

---

## [3.2.0] - 2026-02-01

### Highlights
- **Org-Wide Component Analysis** - Analyze component usage patterns across all data views in your organization with `--org-report`
- **Component Distribution** - Classify components into Core (50%+ of DVs), Common (25-49%), Limited (2+), and Isolated (1 DV only) buckets
- **Duplicate Detection** - Identify near-duplicate data views using Jaccard similarity scoring
- **Data View Clustering** - Group related data views using hierarchical clustering with `--cluster`
- **Governance Exit Codes** - CI/CD integration with threshold-based exit codes using `--fail-on-threshold`
- **Trending & Drift Analysis** - Compare reports over time with `--compare-org-report`
- **Naming Audit** - Detect naming convention inconsistencies with `--audit-naming`
- **All Output Formats** - Org-wide reports support console (default), JSON, Excel, HTML, Markdown, CSV, and format aliases

This release introduces **org-wide component analysis** for governance and standardization. The new `--org-report` mode analyzes all accessible data views to identify core components used organization-wide, detect duplicate data views, and provide governance recommendations. Use filtering (`--filter`, `--exclude`) to focus on specific data view groups. Advanced features include data view clustering, trend analysis, naming audits, and CI/CD governance checks with configurable thresholds.

### Added

#### Org-Wide Analysis Feature
- New `--org-report` flag to enable org-wide analysis mode
- New `--filter PATTERN` flag to include only data views matching regex pattern
- New `--exclude PATTERN` flag to exclude data views matching regex pattern
- New `--limit N` flag to analyze only first N data views (for testing)
- New `--include-names` flag to fetch and display component names (slower but more readable)
- New `--skip-similarity` flag to skip O(n²) pairwise similarity calculation (faster for large orgs)
- New `--core-threshold FLOAT` flag to customize core component classification threshold (default: 0.5)
- New `--core-min-count N` flag to use absolute count for core classification (overrides threshold)
- New `--overlap-threshold FLOAT` flag to customize high-overlap detection threshold (default: 0.8)
- New `--org-summary` flag to show only summary statistics
- New `--org-verbose` flag to include full component lists and detailed breakdowns

#### Component Type & Metadata Options
- New `--no-component-types` flag to disable component type breakdown (standard vs derived)
- New `--include-metadata` flag to include data view metadata (owner, dates, descriptions)
- New `--include-drift` flag to include component drift details between similar DV pairs

#### Sampling Options
- New `--sample N` flag to randomly sample N data views (useful for very large orgs)
- New `--sample-seed SEED` flag for reproducible random sampling
- New `--sample-stratified` flag to stratify sample by data view name prefix

#### Caching Options
- New `--use-cache` flag to enable caching of data view components for faster repeat runs
- New `--cache-max-age HOURS` flag to set maximum cache age (default: 24)
- New `--refresh-cache` flag to clear cache and fetch fresh data
- Cache stored in `~/.cja_auto_sdr/cache/org_report_cache.json`

#### Clustering Options
- New `--cluster` flag to enable hierarchical clustering of related data views
- New `--cluster-method METHOD` flag to select linkage method: `average` (default) or `complete`

#### Governance & CI/CD Options
- New `--duplicate-threshold N` flag to set maximum allowed high-similarity pairs
- New `--isolated-threshold PERCENT` flag to set maximum isolated component percentage
- New `--fail-on-threshold` flag to enable exit code 2 when thresholds exceeded

#### Advanced Analysis Options
- New `--org-stats` flag for quick summary stats without similarity matrix or clustering
- New `--audit-naming` flag to detect naming pattern inconsistencies (snake_case vs camelCase, stale prefixes)
- New `--compare-org-report PREV.json` flag to compare current report to previous for trending/drift analysis
- New `--owner-summary` flag to group statistics by data view owner (requires `--include-metadata`)
- New `--flag-stale` flag to flag components with stale naming patterns (test, old, temp, deprecated, version suffixes, date patterns)

#### Format Aliases
- New `reports` format alias (expands to excel + markdown) for documentation
- New `data` format alias (expands to csv + json) for data pipelines
- New `ci` format alias (expands to json + markdown) for CI/CD integration

#### Safeguards & UX Enhancements
- New `--config-json` flag to output `--config-status` as machine-readable JSON for CI/CD and scripting
- New `--yes` / `-y` flag to skip confirmation prompts (for large batch operations)
- **Duplicate data view detection**: Automatically detects and removes duplicate data view IDs in batch mode with warning
- **Proactive output directory write check**: Validates output directory permissions before making API calls (fail fast)
- **Large batch confirmation**: Prompts for confirmation when processing 20+ data views (bypass with `--yes` or `--quiet`)

#### Data Structures
- `OrgReportConfig` dataclass for org-wide analysis configuration (all options)
- `ComponentInfo` dataclass for component metadata with data view membership
- `DataViewSummary` dataclass for per-data-view component summary with type breakdowns
- `SimilarityPair` dataclass for pairwise Jaccard similarity results with drift details
- `ComponentDistribution` dataclass for bucket classification results
- `OrgReportResult` dataclass for complete analysis results with clusters
- `DataViewCluster` dataclass for hierarchical clustering results
- `OrgReportCache` class for persistent caching of component data
- `OrgReportComparison` dataclass for trending/drift analysis between reports

#### Output Writers
- `write_org_report_console()` - ASCII-formatted console output with distribution bars
- `write_org_report_json()` - Structured JSON for programmatic processing
- `write_org_report_excel()` - Multi-sheet Excel workbook with Summary, Data Views, Core Components, Isolated by DV, Similarity, Clusters, and Recommendations sheets
- `write_org_report_markdown()` - GitHub-flavored markdown with tables
- `write_org_report_html()` - Styled HTML report with cards, tables, and progress bars
- `write_org_report_csv()` - Multiple CSV files in a directory
- `write_org_report_stats_only()` - Minimal stats output for `--org-stats` mode
- `write_org_report_comparison_console()` - Trending/drift comparison output
- `compare_org_reports()` - Compare two org-reports for trending analysis

#### Core Implementation
- `OrgComponentAnalyzer` class with parallel ThreadPoolExecutor for concurrent data view fetching
- `_fetch_data_view_components()` method for per-DV component extraction
- `_build_component_index()` method for global component indexing
- `_compute_distribution_buckets()` method for component classification
- `_compute_similarity_matrix()` method for pairwise Jaccard similarity
- `_generate_recommendations()` method for governance insights
- `run_org_report()` orchestration function

### Documentation
- New `docs/ORG_WIDE_ANALYSIS.md` - Comprehensive org-wide analysis guide (780 lines)
- Updated `docs/QUICK_REFERENCE.md` - Added Org-Wide Analysis mode, commands section, format table update
- Updated `docs/CLI_REFERENCE.md` - Added Org-Wide Analysis options section and examples
- Updated `docs/USE_CASES.md` - Added 3 new use cases: Org-Wide Governance, Data View Consolidation, Cross-Team Component Sharing
- Updated `docs/OUTPUT_FORMATS.md` - Added console format and format availability by mode table
- Updated `docs/QUICKSTART_GUIDE.md` - Added org-wide analysis to Next Steps
- Updated `docs/TROUBLESHOOTING.md` - Added Org-Wide Analysis Issues section
- Updated `README.md` - Added Org-Wide Analysis to features and documentation tables

### Testing
- New `tests/test_org_report.py` with 75 comprehensive tests covering:
  - `TestOrgReportConfig` - Configuration dataclass validation (4 tests)
  - `TestComponentInfo` - Component metadata handling (3 tests)
  - `TestDataViewSummary` - Data view summary with component names (4 tests)
  - `TestSimilarityPair` - Jaccard similarity calculations (2 tests)
  - `TestComponentDistribution` - Bucket classification (3 tests)
  - `TestOrgReportResult` - Result aggregation (3 tests)
  - `TestDistributionBar` - ASCII progress bar rendering (4 tests)
  - `TestOrgComponentAnalyzer` - Core analyzer functionality (5 tests)
  - `TestOutputWriters` - All output format writers (4 tests)
  - `TestIncludeNames` - Component name fetching (3 tests)
  - `TestEdgeCases` - Empty org, all failures, invalid regex (5 tests)
  - `TestNewOrgReportConfig` - Component types, metadata, drift, sampling, caching, clustering options (7 tests)
  - `TestDataViewCluster` - Cluster size and naming (2 tests)
  - `TestSimilarityPairDrift` - Drift detection fields (2 tests)
  - `TestDataViewSummaryEnhancements` - Component type counts, metadata fields (2 tests)
  - `TestSampling` - Sampling applied, reproducible, below threshold (3 tests)
  - `TestOrgReportCache` - Cache put/get, invalidation, miss handling (4 tests)
  - `TestLargeOrgScaling` - Large org runtime behavior: 100+ DVs, 500+ components, O(n²) similarity (5 tests)
  - `TestOutputPathWithFormatAliases` - Output path handling with format aliases (reports, data, ci) (13 tests)
- **1,206 tests** (1,205 passing, 1 skipped) - up from 1,017 in v3.1.0
- New tests for v3.2.0 safeguards: `TestConfigJsonFlag`, `TestYesFlag`, `TestDuplicateDataViewWarning`, `TestOutputDirectoryWriteCheck` (13 tests)

### Changed
- Updated version to 3.2.0
- **Package restructuring**: Migrated to `src/cja_auto_sdr/` layout with modular subpackages
- **Entry point**: Changed from `cja_sdr_generator:main` to `cja_auto_sdr.generator:main`
- **Dynamic versioning**: Version now read from `src/cja_auto_sdr/core/version.py`

### Dependencies
- **scipy** is an optional dependency for clustering features - install with `uv pip install 'cja-auto-sdr[clustering]'`
- New `clustering` extra for scipy dependency
- New `full` extra that bundles clustering, env, and completion extras

### Breaking Changes

**Entry Point Change**

The internal module structure has been reorganized. If you have custom integrations that import directly from the module:

```python
# Old (v3.1.0 and earlier)
from cja_sdr_generator import main

# New (v3.2.0)
from cja_auto_sdr.generator import main
# Or use the package-level import:
from cja_auto_sdr import main
```

**CLI commands are unchanged** - `cja_auto_sdr` and `cja-auto-sdr` work exactly as before.

**scipy now optional** - The `--cluster` flag requires scipy, which is no longer installed by default. Install with:
```bash
uv pip install 'cja-auto-sdr[clustering]'
```

---

## [3.1.0] - 2026-01-30

### Highlights
- **Segments Inventory** - Document segment filters, complexity scores, and definition summaries with `--include-segments`
- **Derived Fields Inventory** - Document derived field logic, complexity scores, and schema references with `--include-derived` (SDR only)
- **Calculated Metrics Inventory** - Document calculated metric formulas, complexity, and references with `--include-calculated`
- **Include All Inventory Shorthand** - Enable all inventory options with a single `--include-all-inventory` flag
- **Inventory Diff Support** - Track calculated metrics and segments changes over time with snapshot comparisons for the same data view
- **Inventory-Only Mode** - Generate only inventory sheets without standard SDR content with `--inventory-only`
- **Inventory Summary Mode** - Quick inventory statistics without full output with `--inventory-summary`
- **Inventory Output Ordering** - Inventory sections appear at the end of all SDR output formats, ordered by CLI argument order
- **Snapshot Inventory Support** - Include calculated metrics and segments inventory in snapshots with `--snapshot --include-calculated --include-segments`
- **Complexity Warnings at Completion** - SDR completion message now shows inventory statistics and warns about high-complexity items
- **Inventory Statistics in Metadata** - Metadata sheet includes inventory counts and complexity statistics when inventory is enabled

This release introduces **component inventory features** for SDR generation and snapshot diff comparisons. These features provide comprehensive documentation of segments, derived fields, and calculated metrics with complexity scoring for governance and review. Calculated metrics and segments inventory options work in both SDR mode and snapshot diff mode (for tracking changes to the same data view over time). Derived fields inventory is for SDR generation only since derived fields are already included in the standard metrics/dimensions output. The new `--inventory-only` flag allows generating focused inventory documentation without standard SDR sheets.

Snapshots created with `--snapshot` or `--git-commit` can now optionally include calculated metrics and segments inventory data. This enables comprehensive change tracking when comparing snapshots over time. Git snapshots store inventory in separate files (`calculated-metrics.json`, `segments.json`) for clean diffs.

> **Note:** Inventory diff is supported for calculated metrics (`--include-calculated`) and segments (`--include-segments`) for snapshot comparisons of the **same data view** only. Derived fields inventory (`--include-derived`) is for SDR generation only—derived field changes are captured in the standard Metrics/Dimensions diff. Cross-data-view comparisons (`--diff dv_A dv_B`) do not support inventory options because inventory IDs are data-view-scoped.

### Added

#### Segments Inventory (NEW)
Document all segments (filters) associated with a Data View, including definition logic, complexity scores, and component references. Supports both SDR generation and snapshot diff comparisons.

```bash
# Include segments inventory in SDR output
cja_auto_sdr dv_12345 --include-segments

# Combine with other inventories
cja_auto_sdr dv_12345 --include-segments --include-calculated --include-derived
```

**Output Columns:**
| Column | Description |
|--------|-------------|
| `segment_name` | Segment display name |
| `segment_id` | Unique segment identifier |
| `description` | User-provided description |
| `owner` | Owner display name |
| `owner_id` | Owner user ID |
| `complexity_score` | Calculated complexity (0-100) |
| `container_type` | Scope: hit, visit, or visitor |
| `functions_used` | Human-readable function names (And, Or, Contains, etc.) |
| `functions_used_internal` | Internal function identifiers |
| `predicate_count` | Number of filter predicates |
| `logic_operator_count` | Number of AND/OR operators |
| `nesting_depth` | Maximum nesting level |
| `container_count` | Number of container contexts |
| `dimension_references` | Referenced dimension IDs |
| `metric_references` | Referenced metric IDs |
| `other_segment_references` | Referenced segment IDs |
| `definition_summary` | Human-readable logic description |
| `approved` | Approval status |
| `favorite` | User favorite status |
| `tags` | Organizational tags |
| `created` | ISO 8601 creation timestamp |
| `modified` | ISO 8601 last modified timestamp |
| `shares` | Share recipient details |
| `shared_to_count` | Number of users/groups shared with |
| `data_view_id` | Associated data view ID |
| `site_title` | Site/company title |
| `definition_json` | Raw definition JSON for advanced analysis |
| `summary` | Alias for `definition_summary` (cross-module compatibility) |

**Complexity Score Factors:**
| Factor | Weight | Max |
|--------|--------|-----|
| Predicates | 30% | 50 |
| Logic operators | 20% | 20 |
| Nesting depth | 20% | 8 |
| Dimension refs | 10% | 15 |
| Metric refs | 10% | 5 |
| Regex patterns | 10% | 5 |

**New CLI Argument:**
- `--include-segments` - Include segments inventory in output (SDR and snapshot diff)

#### Derived Fields Inventory (NEW)
Document all derived fields within a Data View, including logic definitions, complexity scores, and schema field references. **For SDR generation only** (not snapshot diff, since derived fields are already included in the standard metrics/dimensions output).

```bash
# Include derived fields inventory in SDR output
cja_auto_sdr dv_12345 --include-derived
```

**Output Columns:**
| Column | Description |
|--------|-------------|
| `component_name` | Derived field display name |
| `component_id` | Unique component identifier |
| `component_type` | Type: Metric or Dimension |
| `description` | User-provided description |
| `complexity_score` | Calculated complexity (0-100) |
| `functions_used` | Human-readable function names (Case When, Lowercase, etc.) |
| `functions_used_internal` | Internal function identifiers |
| `branch_count` | Number of conditional branches |
| `nesting_depth` | Maximum nesting level |
| `operator_count` | Number of operators in logic |
| `schema_field_count` | Number of schema fields referenced |
| `schema_fields` | Referenced schema field IDs |
| `lookup_references` | Referenced lookup datasets |
| `component_references` | Referenced component IDs |
| `rule_names` | Named rules from definition |
| `rule_descriptions` | Rule description annotations |
| `logic_summary` | Human-readable logic description |
| `inferred_output_type` | Output type: numeric, string, boolean, unknown |
| `definition_json` | Raw fieldDefinition JSON for advanced analysis |
| `summary` | Alias for `logic_summary` (cross-module compatibility) |

**Complexity Score Factors:**
| Factor | Weight | Max |
|--------|--------|-----|
| Operators | 30% | 200 |
| Branches | 25% | 50 |
| Nesting | 20% | 5 |
| Functions | 10% | 20 |
| Schema fields | 10% | 10 |
| Regex patterns | 5% | 5 |

**New CLI Argument:**
- `--include-derived` - Include derived fields inventory in output (SDR only)

#### Calculated Metrics Inventory (NEW)
Document all calculated metrics associated with a Data View, including formula logic, complexity scores, and metric references. Supports both SDR generation and snapshot diff comparisons.

```bash
# Include calculated metrics inventory in SDR output
cja_auto_sdr dv_12345 --include-calculated

# Include both inventories (sheets appear in CLI argument order)
cja_auto_sdr dv_12345 --include-derived --include-calculated
```

**Output Columns:**
| Column | Description |
|--------|-------------|
| `metric_name` | Calculated metric display name |
| `metric_id` | Unique metric identifier |
| `description` | User-provided description |
| `owner` | Owner display name |
| `owner_id` | Owner user ID |
| `complexity_score` | Calculated complexity (0-100) |
| `functions_used` | Human-readable function names (Division, Segment Filter, etc.) |
| `functions_used_internal` | Internal function identifiers |
| `nesting_depth` | Maximum formula nesting level |
| `operator_count` | Number of operators in formula |
| `metric_references` | Referenced metric IDs |
| `segment_references` | Referenced segment IDs |
| `conditional_count` | Number of conditional expressions |
| `formula_summary` | Human-readable formula description |
| `polarity` | Value direction: positive, negative, neutral |
| `metric_type` | Format: decimal, percent, currency, time, integer |
| `precision` | Decimal precision |
| `approved` | Approval status |
| `favorite` | User favorite status |
| `tags` | Organizational tags |
| `created` | ISO 8601 creation timestamp |
| `modified` | ISO 8601 last modified timestamp |
| `shares` | Share recipient details |
| `shared_to_count` | Number of users/groups shared with |
| `data_view_id` | Associated data view ID |
| `site_title` | Site/company title |
| `definition_json` | Raw definition JSON for advanced analysis |
| `summary` | Alias for `formula_summary` (cross-module compatibility) |

**Complexity Score Factors:**
| Factor | Weight | Max |
|--------|--------|-----|
| Operators | 25% | 50 |
| Metric refs | 25% | 10 |
| Nesting depth | 20% | 8 |
| Functions | 15% | 15 |
| Segments | 10% | 5 |
| Conditionals | 5% | 5 |

**New CLI Argument:**
- `--include-calculated` - Include calculated metrics inventory in output (SDR and snapshot diff)

#### Inventory-Only Mode (NEW)
Generate output containing only inventory sheets, without standard SDR content (Metadata, Data Quality, DataView, Metrics, Dimensions).

```bash
# Generate ONLY segments inventory
cja_auto_sdr dv_12345 --include-segments --inventory-only

# Generate multiple inventories only
cja_auto_sdr dv_12345 --include-segments --include-calculated --include-derived --inventory-only

# Output in multiple formats
cja_auto_sdr dv_12345 --include-segments --inventory-only -f all
```

**Use Cases:**
- Focused component documentation without full SDR overhead
- Governance audits targeting specific component types
- Lightweight exports for dependency analysis
- Quick inventory snapshots for review

**New CLI Argument:**
- `--inventory-only` - Output only inventory sheets; requires at least one `--include-*` flag

#### Inventory Summary Mode (NEW)
Display quick inventory statistics without generating full output files. Shows counts, complexity distribution, governance metadata, and highlights high-complexity items that may need review.

```bash
# Quick stats for all inventories
cja_auto_sdr dv_12345 --include-segments --include-calculated --include-derived --inventory-summary

# Summary for segments only
cja_auto_sdr dv_12345 --include-segments --inventory-summary

# Save summary to JSON
cja_auto_sdr dv_12345 --include-segments --include-calculated --inventory-summary --format json
```

**Output includes:**
- Total counts per inventory type
- Governance stats (approved, shared, tagged counts)
- Complexity distribution (average, max, high/elevated counts)
- Container type breakdown (for segments)
- High-complexity items list (complexity >= 70) with warnings

**Example Console Output:**
```
Inventory Summary: Production Analytics
Data View ID: dv_12345

Derived Fields
  Total:       42
  Metrics:     15
  Dimensions:  27
  Complexity:  avg=35.2, max=82.0
  High (>=75): 3

Calculated Metrics
  Total:       28
  Approved:    18
  Shared:      12
  Tagged:      22
  Complexity:  avg=28.5, max=65.0

Segments
  Total:       35
  Approved:    25
  Shared:      15
  Tagged:      30
  Containers:  visitor: 12, visit: 18, hit: 5
  Complexity:  avg=32.1, max=78.0
  High (>=75): 2

High-Complexity Items (5):
   82 Derived Field      Complex Attribution Logic
       Case When with 12 branches...
   78 Segment            Multi-Touch Attribution
       visitor where (Page Views And...)
   ...
```

**New CLI Argument:**
- `--inventory-summary` - Display quick stats without full output; requires at least one `--include-*` flag; cannot be used with `--inventory-only`

#### Include All Inventory Shorthand (NEW)
Enable all applicable inventory options with a single flag. Automatically adjusts based on the mode.

```bash
# SDR mode: enables all three inventory options
cja_auto_sdr dv_12345 --include-all-inventory

# Equivalent to:
cja_auto_sdr dv_12345 --include-segments --include-calculated --include-derived

# With snapshots: enables only segments and calculated metrics (derived not supported)
cja_auto_sdr dv_12345 --snapshot ./snap.json --include-all-inventory

# Equivalent to:
cja_auto_sdr dv_12345 --snapshot ./snap.json --include-segments --include-calculated

# Works with other inventory modes
cja_auto_sdr dv_12345 --include-all-inventory --inventory-only
cja_auto_sdr dv_12345 --include-all-inventory --inventory-summary
```

**Smart Behavior:**
- In SDR mode: enables `--include-segments`, `--include-calculated`, and `--include-derived`
- With `--snapshot`, `--git-commit`, or snapshot diff modes: enables only `--include-segments` and `--include-calculated` (derived fields are not supported in snapshots)

**New CLI Argument:**
- `--include-all-inventory` - Enable all applicable inventory options

#### Complexity Warnings at SDR Completion (NEW)
When generating SDR with inventory options enabled, the completion message now includes inventory statistics and warns about high-complexity items.

**Example Output:**
```
SUCCESS: SDR generated for Production Analytics
  Output: ./Production_Analytics_SDR.xlsx
  Size: 2.4 MB
  Metrics: 150, Dimensions: 85
  Data Quality Issues: 12
  Inventory: Segments: 35 (2 high-complexity), Calculated Metrics: 28, Derived Fields: 42 (3 high-complexity)
  ⚠ 5 high-complexity items (≥75) - review recommended
```

This surfaces governance insights without requiring `--inventory-summary`, alerting users to potential issues at a glance.

#### Inventory Statistics in Metadata Sheet (NEW)
When inventory options are enabled, the Metadata sheet now includes inventory counts and complexity statistics.

**Additional Metadata Properties:**
| Property | Example Value |
|----------|---------------|
| --- Inventory Statistics --- | |
| Segments Count | 35 |
| Segments Complexity (Avg / Max) | 32.1 / 78.0 |
| Segments High Complexity (≥75) | 2 |
| Segments Elevated Complexity (50-74) | 5 |
| Calculated Metrics Count | 28 |
| Calculated Metrics Complexity (Avg / Max) | 28.5 / 65.0 |
| Calculated Metrics High Complexity (≥75) | 0 |
| Calculated Metrics Elevated Complexity (50-74) | 3 |
| Derived Fields Count | 42 |
| Derived Fields Breakdown | Metrics: 15, Dimensions: 27 |
| Derived Fields Complexity (Avg / Max) | 35.2 / 82.0 |
| Derived Fields High Complexity (≥75) | 3 |
| Derived Fields Elevated Complexity (50-74) | 8 |

This enables single-sheet summary for automated reporting and dashboards.

#### Inventory Diff Support (NEW)
Track changes to calculated metrics and segments over time using snapshot comparisons. This feature is limited to comparing the **same data view** across different points in time.

> **Note:** Derived fields inventory (`--include-derived`) is for SDR generation only. Derived field changes are automatically captured in the standard Metrics/Dimensions diff since they're included in the metrics/dimensions API output.

```bash
# Create snapshot with inventory data
cja_auto_sdr dv_12345 --snapshot ./baseline.json \
  --include-calculated --include-segments

# Compare against baseline (same data view)
cja_auto_sdr dv_12345 --diff-snapshot ./baseline.json \
  --include-calculated --include-segments

# Compare two snapshots directly
cja_auto_sdr --compare-snapshots ./before.json ./after.json \
  --include-calculated --include-segments

# Quick comparison against most recent snapshot
cja_auto_sdr dv_12345 --compare-with-prev --include-calculated
```

**Why Same Data View Only? (Design Choice)**
Calculated metrics and segments use data-view-scoped IDs that cannot be reliably matched across different data views.

**CJA Auto SDR intentionally does not attempt name-based or formula-based fuzzy matching** for calculated metrics or segments across data views. This avoids false positives where two components with the same name or similar formula actually represent different business logic. ID-based matching within the same data view over time is reliable and meaningful.

**Supported Scenarios:**
| Scenario | Inventory Diff |
|----------|----------------|
| `--diff-snapshot` (same DV) | ✓ IDs match reliably |
| `--compare-snapshots` (same DV) | ✓ IDs match reliably |
| `--compare-with-prev` (same DV) | ✓ IDs match reliably |
| `--diff dv_A dv_B` (cross-DV) | ✗ IDs cannot match meaningfully |

**Output includes:**
- Summary table with inventory change counts and percentages
- Detailed change lists for each inventory type (added/removed/modified)
- Changed field details showing before/after values
- All output formats supported: Console, JSON, Markdown, HTML, Excel, CSV

**Snapshot Version 2.0:**
Snapshots with inventory data use version 2.0 format, which includes `calculated_metrics_inventory` and `segments_inventory` arrays. Derived fields inventory is not included in snapshots—derived field changes are captured in the standard Metrics/Dimensions diff.

**Why No Derived Fields in Snapshots?**
Derived fields already appear in the Metrics/Dimensions output, so their changes are captured automatically:
- **Standard diff**: `name`, `title`, `description`, `type`, `schemaPath`
- **Extended diff** (`--extended-fields`): `hidden`, `format`, `attribution`, `persistence`, `bucketing`, `derivedFieldId`, etc.

Use `--include-derived` with SDR generation to get the full Derived Fields Inventory sheet with logic analysis, complexity scores, and schema field references.

#### Inventory Output Ordering
Inventory sections (Segments, Derived Fields, Calculated Metrics) appear at the end of all output formats in the order specified on the command line. This applies to both SDR generation and diff comparison outputs.

**Format-Specific Placement:**
| Format | Placement |
|--------|-----------|
| Excel | Additional sheets at end of workbook |
| JSON | Additional sections in output object |
| CSV | Separate `*_Segments.csv`, `*_derived_fields.csv`, `*_calculated_metrics.csv` files |
| HTML | Additional sections at end of report |
| Markdown | Additional `## Segments` / `## Derived Fields` / `## Calculated Metrics` sections |

**Excel Sheet Order (Standard SDR Mode):**
1. Metadata
2. Data Quality
3. DataView
4. Metrics
5. Dimensions
6. Segments (if `--include-segments`)
7. Derived Fields (if `--include-derived`)
8. Calculated Metrics (if `--include-calculated`)

**Excel Sheet Order (Inventory-Only Mode):**
Only inventory sheets appear, in CLI argument order.

**Note:** The order of inventory sections depends on CLI argument order:
- `--include-segments --include-derived --include-calculated` → Segments, Derived Fields, Calculated Metrics
- `--include-calculated --include-segments` → Calculated Metrics, Segments

#### Snapshot Inventory Support (NEW)
Snapshots created with `--snapshot` or `--git-commit` now support optional inclusion of calculated metrics and segments inventory data. This enables comprehensive change tracking when comparing snapshots over time.

```bash
# Create snapshot with calculated metrics inventory
cja_auto_sdr dv_12345 --snapshot ./baseline.json --include-calculated

# Create snapshot with segments inventory
cja_auto_sdr dv_12345 --snapshot ./baseline.json --include-segments

# Create snapshot with both inventories
cja_auto_sdr dv_12345 --snapshot ./baseline.json --include-calculated --include-segments

# Git commit with inventory data
cja_auto_sdr dv_12345 --git-commit --include-calculated --include-segments
```

**Git-Friendly Snapshot Structure (Extended):**
When inventory is included, Git snapshots store inventory in separate files for clean diffs:

```
sdr-snapshots/
└── ProductionAnalytics_dv_12345/
    ├── metrics.json              # All metrics, sorted by ID
    ├── dimensions.json           # All dimensions, sorted by ID
    ├── metadata.json             # Data view info, quality summary, inventory counts
    ├── calculated-metrics.json   # Optional: calculated metrics inventory
    └── segments.json             # Optional: segments inventory
```

**Snapshot Version:**
Snapshots with inventory data are automatically upgraded to version 2.0 format.

**Important: Derived Fields Not Supported in Snapshots or Snapshot Diffs**
The `--include-derived` flag is only for SDR generation mode:
- Derived fields inventory is computed from metrics/dimensions data
- Use `--include-derived` with SDR generation to output the Derived Fields sheet
- Derived field **changes** are captured in the standard Metrics/Dimensions diff (no special flag needed)

```bash
# This works: SDR generation with derived fields inventory
cja_auto_sdr dv_12345 --include-derived

# This errors: not supported with snapshots
cja_auto_sdr dv_12345 --snapshot ./snap.json --include-derived
# ERROR: --include-derived cannot be used with --snapshot
```

#### Derived Fields Description Support (NEW)
Derived fields now include the `description` field from data view components when available. This field appears in both DataFrame output and JSON export, maintaining consistency with calculated metrics and segments which already included descriptions from their respective APIs.

#### Additional Logic Summary Handlers (NEW)
Derived fields inventory now generates detailed logic summaries for 7 additional function types:

| Function | Summary Example |
|----------|-----------------|
| `typecast` | "Converts {field} to {target_type}" |
| `datetime-bucket` | "Buckets {field} by {interval}" |
| `datetime-slice` | "Extracts {component} from {field}" |
| `timezone-shift` | "Shifts {field} from {src_tz} to {dst_tz}" |
| `find-replace` | "Replaces {pattern} with {replacement} in {field}" |
| `depth` | "Counts depth of {field}" |
| `profile` | "References profile attribute {name}" |

#### Standardized Summary Column (NEW)
All three inventory modules now include a standardized `summary` column that aliases the module-specific summary column for cross-module queries:

| Module | Original Column | Standard Alias |
|--------|-----------------|----------------|
| Calculated Metrics | `formula_summary` | `summary` |
| Segments | `definition_summary` | `summary` |
| Derived Fields | `logic_summary` | `summary` |

This enables consistent queries across inventory types:
```python
# Find components mentioning "revenue" across all inventories
for df in [calc_metrics_df, segments_df, derived_df]:
    matches = df[df['summary'].str.contains('revenue', case=False, na=False)]
```

### New Files
- `cja_segments_inventory.py` - Segments inventory module
- `cja_derived_fields_inventory.py` - Derived fields inventory module
- `cja_calculated_metrics_inventory.py` - Calculated metrics inventory module
- `tests/test_segments_inventory.py` - 41 tests for segments inventory
- `tests/test_derived_inventory.py` - 43 tests for derived fields inventory
- `tests/test_calculated_metrics_inventory.py` - 36 tests for calculated metrics inventory
- `docs/SEGMENTS_INVENTORY.md` - Segments inventory documentation
- `docs/DERIVED_FIELDS_INVENTORY.md` - Derived fields documentation
- `docs/CALCULATED_METRICS_INVENTORY.md` - Calculated metrics documentation
- `docs/INVENTORY_OVERVIEW.md` - Unified inventory guide covering all three modules

### Documentation Updates
- Updated README.md with inventory commands and features
- Updated README.md with AEP API requirement clarification (Adobe Developer Console projects need both CJA API and AEP API enabled for authentication)
- Updated docs/QUICK_REFERENCE.md with inventory options
- Updated docs/CLI_REFERENCE.md with Inventory Options section
- Added table of contents navigation to docs/CLI_REFERENCE.md for easier reference
- Updated docs/OUTPUT_FORMATS.md with sheet ordering details
- Added docs/INVENTORY_OVERVIEW.md with unified inventory guide covering:
  - When to use each inventory module
  - Feature comparison table (governance metadata, complexity scoring, reference tracking)
  - Cross-module complexity score comparison
  - Combined workflows for governance audits and change tracking

### Testing
- **1,017 tests** (1,016 passing, 1 skipped) - up from 786 in v3.0.16
- New test file: `tests/test_inventory_utils.py` with 41 tests for shared utility functions
- New test file: `tests/test_segments_inventory.py` with 41 tests covering:
  - Builder basic functionality and API calls
  - Inventory dataframe/JSON output
  - Complexity score calculation
  - Definition summary generation
  - Edge cases (empty definition, missing owner, API errors)
  - Segment summary serialization
  - Inventory property calculations
- New test file: `tests/test_derived_inventory.py` with 43 tests for derived fields inventory
- New test file: `tests/test_calculated_metrics_inventory.py` with 36 tests covering:
  - Builder basic functionality
  - Metric reference extraction
  - Segment reference extraction
  - Complexity score calculation
  - Formula summary generation
  - Edge cases
- Updated `tests/test_process_single_dataview.py` for new parameters
- Updated `tests/conftest.py` with inventory fixtures
- Updated `tests/test_ux_features.py` with 103 tests (up from 83), including:
  - `TestInventoryOptionsValidation` - 19 tests for flag registration and diff mode validation
  - `TestIncludeAllInventory` - 4 tests for shorthand flag and smart mode detection
  - `TestProcessingResultInventory` - 6 tests for inventory statistics in ProcessingResult
  - `TestDisplayInventorySummary` - 5 tests for `--inventory-summary` output

### Internal Improvements

#### Inventory Code Consolidation
Refactored inventory modules to reduce code duplication and improve maintainability:

- **New shared utilities module** (`cja_inventory_utils.py`) consolidates common functionality:
  - `format_iso_date()` - Consistent date formatting across all inventories
  - `extract_owner()` - Standardized owner extraction from API responses
  - `extract_tags()` - Standardized tags extraction
  - `normalize_api_response()` - Unified DataFrame/list response handling
  - `extract_short_name()` - Consistent reference name cleaning (e.g., `metrics/revenue` → `revenue`)
  - `BatchProcessingStats` - Track processed/skipped items with visibility
  - `validate_required_id()` - Fail-fast validation for missing critical IDs

- **Improved logging visibility**:
  - Skipped items now logged at WARNING level (previously DEBUG) for better visibility
  - Batch processing summary shows processed vs. skipped counts with percentages
  - Exception logging includes full stack traces for debugging

- **Fail-fast ID validation**:
  - Calculated metrics, segments, and derived fields now validate IDs before processing
  - Missing or empty IDs are logged and skipped rather than creating invalid records

- **Enhanced console formatting**:
  - Added dim/gray text styling (`ConsoleColors.dim()`) for secondary information in inventory summary display
  - Improves visual hierarchy when displaying complexity statistics and high-complexity item details

#### Inventory Modules
- Added `SegmentSummary` dataclass for segment filter data
- Added `SegmentsInventory` class with DataFrame/JSON output
- Added `SegmentsInventoryBuilder` for parsing segment definitions via `getFilters` API
- Added `DerivedFieldSummary` dataclass for derived field data
- Added `DerivedFieldsInventory` class with DataFrame/JSON output
- Added `DerivedFieldsInventoryBuilder` for parsing field definitions
- Added `CalculatedMetricSummary` dataclass for metric data
- Added `CalculatedMetricsInventory` class with DataFrame/JSON output
- Added `CalculatedMetricsInventoryBuilder` for parsing API responses
- Added function display name constants for all inventory types (segments, derived fields, calculated metrics)
- Added `inventory_order` parameter through processing chain
- Added `inventory_only` parameter for focused inventory output
- Modified `process_single_dataview` signature for inventory support
- Modified Excel sheet writing to place inventories at end
- Added `"Segments": "🎯"` to HTML section icons
- Added validation and error messaging when inventory options are used with diff modes (`--diff`, `--diff-snapshot`, `--compare-snapshots`, `--compare-with-prev`)
- Added validation requiring `--inventory-only` to be used with at least one `--include-*` flag

#### Build Configuration
- Added inventory modules to wheel and sdist build targets to ensure proper package distribution

### API Impact
Each inventory option has different API requirements:

| Option | API Call | Impact |
|--------|----------|--------|
| `--include-segments` | `getFilters` | Additional API request |
| `--include-calculated` | `getCalculatedMetrics` | Additional API request |
| `--include-derived` | None | Parses existing data view response |

### Backwards Compatibility
- **Snapshot format v2.0** is fully backwards compatible with v1.0 snapshots
- Existing v1.0 snapshots (without inventory data) continue to work unchanged
- When loading a snapshot, the tool defaults to v1.0 if no version is specified
- v2.0 snapshots are only created when inventory data (`--include-segments` or `--include-calculated`) is included

### Upgrade Notes
- **No migration required** - existing snapshots and CI/CD pipelines work without changes
- Inventory diff features are additive; baseline snapshots without inventory data simply won't include inventory comparisons
- To track inventory changes over time, regenerate baseline snapshots with `--include-segments` or `--include-calculated`

### Dependencies
- **cjapy** minimum version bumped from `>=0.2.4.post2` to `>=0.2.4.post3`
  - Improved OAuth error handling: authentication failures now show the actual OAuth response (e.g., `invalid_client`, `invalid_scope`) instead of confusing downstream errors
  - See [Troubleshooting: OAuth Token Retrieval Failed](docs/TROUBLESHOOTING.md#oauth-token-retrieval-failed-v310) for details

---

## [3.0.16] - 2026-01-24

### Highlights
- **API Worker Auto-Tuning** - Dynamically adjust API fetch workers based on response times
- **Circuit Breaker Pattern** - Prevent cascading failures with state-based protection
- **Batch Memory Pooling** - Share validation cache across batch processing workers

This release adds three **reliability and performance optimizations** for enterprise-scale deployments. All features are opt-in via CLI flags to maintain backward compatibility.

### Added

#### API Worker Auto-Tuning
Automatically adjust API worker count based on response time metrics.

```bash
# Enable auto-tuning with default settings
cja_auto_sdr dv_12345 --api-auto-tune

# Custom min/max worker bounds
cja_auto_sdr dv_12345 --api-auto-tune --api-min-workers 2 --api-max-workers 8
```

**Features:**
- Scales up workers when responses are fast (< 200ms default)
- Scales down workers when responses are slow (> 2000ms default)
- Rolling window sampling (5 requests) before adjustments
- Cooldown period (10s) between adjustments to prevent thrashing
- Thread-safe implementation with statistics tracking

**New CLI Arguments:**
- `--api-auto-tune` - Enable automatic API worker tuning
- `--api-min-workers N` - Minimum workers for auto-tuning (default: 1)
- `--api-max-workers N` - Maximum workers for auto-tuning (default: 10)

#### Circuit Breaker Pattern
Prevent cascading failures by automatically stopping requests to failing services.

```bash
# Enable circuit breaker with defaults
cja_auto_sdr dv_12345 --circuit-breaker

# Custom thresholds
cja_auto_sdr dv_12345 --circuit-breaker --circuit-failure-threshold 3 --circuit-timeout 60
```

**State Machine:**
- **CLOSED** - Normal operation, all requests allowed
- **OPEN** - Circuit tripped after failures, requests rejected immediately
- **HALF_OPEN** - Testing recovery, limited requests allowed

**Features:**
- Configurable failure threshold before opening (default: 5)
- Configurable success threshold to close (default: 2)
- Automatic timeout-based recovery (default: 30s)
- Thread-safe state transitions
- Statistics tracking (trips, rejections, failures)
- Decorator support for wrapping functions

**New CLI Arguments:**
- `--circuit-breaker` - Enable circuit breaker pattern
- `--circuit-failure-threshold N` - Failures before opening circuit (default: 5)
- `--circuit-timeout SECONDS` - Recovery timeout in seconds (default: 30)

#### Batch Memory Pooling (Shared Validation Cache)
Share validation cache across batch processing workers using multiprocessing.Manager.

```bash
# Enable shared cache in batch mode
cja_auto_sdr --batch dv_1 dv_2 dv_3 --shared-cache

# Combined with other cache settings
cja_auto_sdr --batch dv_1 dv_2 dv_3 --shared-cache --enable-cache --cache-size 2000
```

**Features:**
- Cross-process cache sharing via `multiprocessing.Manager`
- Same API as `ValidationCache` (drop-in replacement)
- LRU eviction and TTL expiration
- Process-safe locking
- Proper resource cleanup via `shutdown()` method

**New CLI Argument:**
- `--shared-cache` - Share validation cache across batch workers

### Testing
- **786 tests** (785 passing, 1 skipped) - up from 750 in v3.0.15
- New test file: `tests/test_api_tuning.py` with 29 tests covering:
  - Initial worker count and bounds (4 tests)
  - Scale up/down behavior (5 tests)
  - Cooldown enforcement (2 tests)
  - Statistics tracking (4 tests)
  - Thread safety (2 tests)
  - Reset functionality (4 tests)
  - Configuration dataclass (2 tests)
- New test file: `tests/test_circuit_breaker.py` with 27 tests covering:
  - Basic state transitions (6 tests)
  - Recovery mechanisms (3 tests)
  - Statistics tracking (5 tests)
  - Decorator usage (3 tests)
  - Thread safety (2 tests)
  - Reset and exception handling (4 tests)
- New test file: `tests/test_shared_cache.py` with 16 tests covering:
  - Cache hit/miss behavior (3 tests)
  - API compatibility with ValidationCache (3 tests)
  - LRU eviction (2 tests)
  - TTL expiration (1 test)
  - Statistics tracking (2 tests)
  - Shutdown and data integrity (5 tests)
- Updated `tests/test_process_single_dataview.py` for new function signatures

### Internal Improvements
- Added `APITuningConfig` dataclass for auto-tuning configuration
- Added `APIWorkerTuner` class with thread-safe response time tracking
- Added `CircuitBreakerConfig` dataclass for circuit breaker configuration
- Added `CircuitState` enum (CLOSED, OPEN, HALF_OPEN)
- Added `CircuitBreaker` class with full state machine implementation
- Added `CircuitBreakerOpen` exception for circuit breaker rejections
- Added `SharedValidationCache` class with multiprocessing.Manager support
- Modified `ParallelAPIFetcher` to support tuning_config and circuit_breaker
- Modified `BatchProcessor` to support shared_cache, api_tuning_config, circuit_breaker_config
- Modified `process_single_dataview` and `process_single_dataview_worker` for new parameters

---

## [3.0.15] - 2026-01-23

### Highlights
- **Profile Management** - Built-in support for managing multiple Adobe Organizations with `--profile`, `--profile-add`, `--profile-list`, `--profile-test`, and `--profile-show`

This release adds **multi-organization support** for agencies, consultants, and enterprises managing multiple Adobe CJA instances.

### Added

#### Profile Management for Multiple Organizations
Manage credentials for multiple Adobe Organizations without manual config file switching.

```bash
# Create profiles for your organizations
cja_auto_sdr --profile-add client-a
cja_auto_sdr --profile-add client-b

# List all profiles
cja_auto_sdr --profile-list

# Use a specific profile
cja_auto_sdr --profile client-a --list-dataviews
cja_auto_sdr -p client-b "Main Data View" --format excel

# Test profile connectivity
cja_auto_sdr --profile-test client-a

# Show profile config (secrets masked)
cja_auto_sdr --profile-show client-a

# Set default profile via environment
export CJA_PROFILE=client-a
```

**Profile directory structure:**
```
~/.cja/orgs/
├── client-a/
│   ├── config.json     # JSON credentials
│   └── .env            # Optional overrides
├── client-b/
│   └── config.json
└── internal/
    └── .env
```

**Environment variables:**
- `CJA_PROFILE` - Default profile (overridden by `--profile`)
- `CJA_HOME` - Override default `~/.cja` directory

See the [Profile Management documentation](docs/CONFIGURATION.md#profile-management) for full details.

### Testing
- **750 tests** (749 passing, 1 skipped) - up from 706 in v3.0.14
- New test file: `tests/test_profiles.py` with 43 tests covering:
  - Profile path resolution (3 tests)
  - Profile name validation (10 tests)
  - Config.json loading (4 tests)
  - .env file loading (4 tests)
  - Credential merging and precedence (5 tests)
  - Profile listing and display (6 tests)
  - Sensitive value masking (4 tests)
  - Exception hierarchy (3 tests)
  - Active profile resolution (4 tests)
- **66% code coverage** on cja_sdr_generator.py

### Internal Improvements

#### Credential Management Refactoring
Unified credential handling across profiles, environment variables, and config files:

- **Single Source of Truth**: Added `CREDENTIAL_FIELDS` constant derived from `CONFIG_SCHEMA`, eliminating 4 duplicate credential field definitions
- **Abstract Credential Loaders**: New `CredentialLoader` ABC with implementations:
  - `JsonFileCredentialLoader` - Loads from config.json files
  - `DotenvCredentialLoader` - Loads from .env files
  - `EnvironmentCredentialLoader` - Loads from environment variables
- **Unified Resolution**: `CredentialResolver` class is the single entry point for all credential loading (profile, environment, config file). The `configure_cjapy()` function uses `CredentialResolver` internally, eliminating duplicate priority logic
- **Complete Profile Integration**: All CJA-related functions now support profiles including `run_dry_run()`, `handle_snapshot_command()`, `handle_diff_command()`, and `handle_diff_snapshot_command()`
- **Standalone Profile Functions**: Profile operations (`list_profiles`, `add_profile_interactive`, `test_profile`, `show_profile`, `load_profile_credentials`) are standalone functions for simplicity
- **Standardized Validation**: `validate_credentials()` function provides consistent validation across all credential sources
- **New Exception**: `CredentialSourceError` provides detailed error context including source type and failure reason

These changes improve maintainability and make it easier to add new credential sources in the future.

---

## [3.0.14] - 2026-01-23

### Highlights
- **Format Auto-Detection** - Infer output format from file extension (`--output report.json` automatically uses JSON)
- **Quick Config Status** - New `--config-status` flag shows credentials and environment without API calls
- **Accessibility Color Theme** - `--color-theme accessible` uses blue/orange instead of green/red for colorblind users
- **Snapshot Metadata Display** - Diff comparisons show file sizes, dates, and component counts
- **Interactive Data View Selection** - New `--interactive` / `-i` flag to select data views from a numbered list
- **Format Aliases** - Shortcuts for common format combinations: `reports`, `data`, `ci`
- **Performance Timings** - New `--show-timings` flag displays detailed operation timing breakdown
- **SDR Component Filtering** - Extended `--metrics-only` / `--dimensions-only` to work with SDR generation

This release focuses on **developer experience**, **accessibility**, and **usability enhancements**.

### Added

#### Format Auto-Detection from File Extension
Automatically infer output format from the `--output` file path extension.

```bash
# Format inferred from extension - no --format needed
cja_auto_sdr dv_12345 --output report.json   # Uses JSON format
cja_auto_sdr dv_12345 --output report.xlsx   # Uses Excel format
cja_auto_sdr dv_12345 --output report.md     # Uses Markdown format

# Explicit --format still takes precedence
cja_auto_sdr dv_12345 --output data.txt --format csv  # Uses CSV despite .txt extension
```

**Supported Extensions:**
- `.xlsx`, `.xls` → Excel
- `.csv` → CSV
- `.json` → JSON
- `.html`, `.htm` → HTML
- `.md`, `.markdown` → Markdown

#### Quick Config Status (`--config-status`)
Display current configuration status without making API calls.

```bash
cja_auto_sdr --config-status
```

Output shows:
- Credential source (environment variables or config file)
- Which credentials are configured (ORG_ID, CLIENT_ID, SECRET, SCOPES)
- Masked credential values for verification
- Environment details (Python version, working directory)

Useful for debugging configuration issues without waiting for API authentication.

#### Accessibility Color Theme (`--color-theme`)
Choose between color themes for diff output to accommodate colorblind users.

```bash
# Default theme (green/red/yellow)
cja_auto_sdr --diff dv_1 dv_2

# Accessible theme (blue/orange/cyan)
cja_auto_sdr --diff dv_1 dv_2 --color-theme accessible
```

**Available Themes:**
- `default` - Green for added, red for removed, yellow for modified
- `accessible` - Blue for added, orange for removed, cyan for modified

#### Snapshot Metadata Display
When comparing snapshots, displays file metadata for context.

```bash
cja_auto_sdr --compare-snapshots old.json new.json
```

Output includes:
- File sizes (e.g., "42.5 KB")
- Last modified dates
- Component counts (metrics and dimensions)
- Data view names and IDs

#### Interactive Data View Selection (`--interactive` / `-i`)
Interactively select data views from a numbered list instead of specifying IDs.

```bash
cja_auto_sdr --interactive
# or
cja_auto_sdr -i
```

Displays available data views with numbers, allowing selection by entering the number. Supports selecting multiple data views by entering comma-separated numbers.

#### Format Aliases
Shortcuts for common format combinations.

```bash
# Generate Excel + Markdown (documentation use case)
cja_auto_sdr dv_12345 --format reports

# Generate CSV + JSON (data pipeline use case)
cja_auto_sdr dv_12345 --format data

# Generate JSON + Markdown (CI/CD use case)
cja_auto_sdr dv_12345 --format ci
```

**Alias Mappings:**
- `reports` → Excel + Markdown
- `data` → CSV + JSON
- `ci` → JSON + Markdown

#### Performance Timings (`--show-timings`)
Display detailed timing breakdown for each operation.

```bash
cja_auto_sdr dv_12345 --show-timings
```

Shows timing for:
- API calls (getDataView, getMetrics, getDimensions)
- Data validation
- Output file generation
- Total processing time

Useful for identifying performance bottlenecks with large data views.

#### SDR Component Filtering
Extended `--metrics-only` and `--dimensions-only` flags to work with SDR generation (previously diff-only).

```bash
# Generate SDR with only metrics
cja_auto_sdr dv_12345 --metrics-only

# Generate SDR with only dimensions
cja_auto_sdr dv_12345 --dimensions-only
```

### Tests
- **706 tests passing** (up from 671 in v3.0.12)
- 35 new tests covering all new features:
  - Format auto-detection tests (12 tests)
  - Config status flag tests (2 tests)
  - Color theme tests (9 tests)
  - Interactive flag tests (3 tests)
  - SDR component filtering tests (3 tests)
  - Format alias tests (4 tests)
  - Show timings flag tests (2 tests)

### Documentation
- Updated Quick Reference with new options
- Added format aliases and accessibility theme examples

---

## [3.0.13] - 2026-01-23

### Changed

#### Flexible OAuth Scopes
OAuth scope validation no longer enforces specific scope values. Scopes vary based on your Adobe Developer Console project configuration.

**Before:** The tool required specific scopes (`openid`, `AdobeID`, `additional_info.projectedProductContext`) and warned if any were missing.

**After:** The tool validates that scopes are provided but accepts any valid scopes from your Developer Console project.

```json
{
  "scopes": "your_scopes_from_developer_console"
}
```

- Copy scopes directly from Adobe Developer Console → Credentials → Scopes
- See [Adobe Authentication Guide](https://developer.adobe.com/developer-console/docs/guides/authentication/) for details
- Updated all documentation, example configs, and error messages

## [3.0.12] - 2026-01-23

### Highlights
- **Auto-detect Workers** - Automatic optimal worker count based on CPU cores and workload
- **JSON Structured Logging** - Enterprise-ready logging for Splunk, ELK, CloudWatch
- **Config Validation Helpers** - Better error messages with actionable fix suggestions
- **Exit Code Reference** - New `--exit-codes` flag for CI/CD documentation
- **Date-based Snapshot Retention** - New `--keep-since` option for time-based cleanup
- **Unified Color Classes** - Consolidated ANSI color handling
- **Conflicting Credentials Warning** - Alerts when both env vars and config.json exist

This release focuses on developer experience, enterprise observability, and CI/CD integration enhancements.

### Added

#### JSON Structured Logging (`--log-format json`)
Enterprise-ready structured logging for log aggregation systems.

```bash
# Enable JSON logging for Splunk, ELK, CloudWatch
cja_auto_sdr dv_12345 --log-format json

# Output format:
# {"timestamp": "2026-01-23T15:11:50", "level": "INFO", "logger": "cja_sdr_generator", "message": "Processing data view", "module": "cja_sdr_generator", "function": "process_single_dataview", "line": 6683}
```

- **Splunk/ELK/CloudWatch Compatible**: Each log line is valid JSON
- **Structured Fields**: timestamp, level, logger, message, module, function, line
- **Exception Support**: Stack traces included in `exception` field when errors occur
- **Default**: `text` format unchanged for human-readable output

#### Auto-detect Workers (`--workers auto`)
Automatically determines optimal parallel worker count based on system resources.

```bash
# Now the default - workers auto-detected based on CPU cores
cja_auto_sdr --batch dv_1 dv_2 dv_3

# Shows: "Auto-detected workers: 4 (based on 8 CPU cores, 3 data views)"
```

- **Smart Detection**: Uses CPU core count and data view complexity
- **Memory Aware**: Reduces workers for large data views (>5000 components)
- **Explicit Override**: Still supports `--workers N` for manual control

#### Exit Code Reference (`--exit-codes`)
New flag to display detailed exit code documentation for CI/CD integration.

```bash
cja_auto_sdr --exit-codes
```

Output includes:
- Exit code meanings (0=success, 1=error, 2=changes found, 3=threshold exceeded)
- CI/CD integration examples
- Usage patterns for automation scripts

#### Date-based Snapshot Retention (`--keep-since`)
Delete snapshots older than a specified time period.

```bash
# Keep only snapshots from the last 7 days
cja_auto_sdr --diff dv_A dv_B --auto-snapshot --keep-since 7d

# Keep snapshots from last 2 weeks
cja_auto_sdr --diff dv_A dv_B --auto-snapshot --keep-since 2w

# Keep snapshots from last month
cja_auto_sdr --diff dv_A dv_B --auto-snapshot --keep-since 1m
```

- **Flexible Formats**: `7d` (days), `2w` (weeks), `1m` (months), or plain number
- **Combinable**: Use with `--keep-last N` for both count and time-based retention
- **Compliance Friendly**: Better data governance for audit trails

#### Config Validation Helpers (`ConfigValidator` class)
Enhanced validation with actionable error messages.

**ORG_ID Validation:**
```
ORG_ID '123ABC' is missing '@AdobeOrg' suffix. Correct format: '123ABC@AdobeOrg'
```

**Scopes Validation:**
```
SCOPES cannot be empty - copy from Adobe Developer Console
```

- `ConfigValidator.validate_org_id()` - Detects missing `@AdobeOrg` suffix
- `ConfigValidator.validate_scopes()` - Validates scopes are provided (see v3.0.13 for flexible scopes)
- `ConfigValidator.validate_client_id()` - Format validation
- `ConfigValidator.validate_secret()` - Length validation

#### Conflicting Credentials Warning
Alerts users when both environment variables AND config.json exist.

```
NOTICE: Both environment variables AND config file detected
  Environment variables: ORG_ID, CLIENT_ID, SECRET, etc.
  Config file: config.json
  Using: ENVIRONMENT VARIABLES (takes precedence)

To avoid confusion:
  - Remove config.json if using environment variables
  - Or unset env vars: unset ORG_ID CLIENT_ID SECRET SCOPES
```

### Changed

#### Unified Color Classes
- Enhanced `ConsoleColors` with all features from `ANSIColors`
- `ANSIColors` now delegates to `ConsoleColors` to avoid code duplication
- Added `visible_len()`, `rjust()`, `ljust()` utility methods
- Better Windows terminal compatibility

#### Workers Default
- Default changed from `4` to `auto` for automatic detection
- Existing `--workers N` syntax still works for explicit control

#### Improved Debug Logging for File Operations
- `open_file_in_default_app()` now logs failures with `logger.debug()` instead of silently swallowing exceptions
- Helps troubleshoot `--open` flag issues on different platforms

#### Enhanced Help Text
- Improved `--workers` help text explaining auto-detection behavior
- Added `--workers auto` example showing intelligent worker detection
- Added JSON logging example in help epilog

### Fixed
- Fixed `--workers` default documented as `4` instead of `auto` in CLI_REFERENCE.md

### Tests
- **671 tests passing** (up from 643 in v3.0.11)
- New tests for `ConfigValidator` class
- New tests for `auto_detect_workers()` function
- New tests for `parse_retention_period()` function
- Updated tests for new `--workers auto` default

### Documentation
- Updated CLI reference with new `--exit-codes` and `--keep-since` flags
- Added CI/CD examples for exit code handling
- Updated troubleshooting guide with config validation suggestions

### Release Notes
See full release notes at: https://github.com/brian-a-au/cja_auto_sdr/releases/tag/v3.0.12

---

## [3.0.11] - 2026-01-20

### Highlights
- **Git Integration (New)** - Version-controlled SDR snapshots for audit trails, change tracking, and team collaboration
- **`--compare-with-prev` (New)** - One-command diff against most recent snapshot
- **Diff Summary Totals** - At-a-glance change counts in diff output
- **Performance Optimizations** - Vectorized markdown table generation, Excel format caching, lazy logging
- **`--group-by-field-limit`** - Control truncation in grouped diff output

This release introduces **Git Integration** for maintaining a version-controlled history of data view configurations, plus performance optimizations for markdown generation, Excel formatting, and logging.

### Added

#### Git Integration (New Feature)
Save SDR snapshots in a Git-friendly format and automatically commit them to a repository for version control.

**Core Functionality:**
- **`--git-init`**: Initialize a new Git repository for snapshots with README and .gitignore
- **`--git-commit`**: Save snapshot and commit to Git after SDR generation
- **`--git-push`**: Push to remote repository after committing
- **`--git-message MSG`**: Custom commit message (auto-generated if not provided)
- **`--git-dir DIR`**: Directory for Git snapshots (default: `./sdr-snapshots`)

**Git-Friendly Snapshot Format:**
```
sdr-snapshots/
├── .git/
├── .gitignore
├── README.md
└── DataViewName_dv_12345/
    ├── metrics.json      # All metrics, sorted by ID
    ├── dimensions.json   # All dimensions, sorted by ID
    └── metadata.json     # Data view info and quality summary
```

**Key Benefits:**
- **Audit Trail**: Full Git history of every data view configuration change
- **Change Detection**: Use `git diff` to see exactly what changed between snapshots
- **Team Collaboration**: Share snapshots via Git repositories (GitHub, GitLab, etc.)
- **PR-Based Review**: Review configuration changes through pull requests
- **Compliance**: Evidence of configuration state at any point in time

**Auto-Generated Commit Messages:**
```
[dv_12345] SDR snapshot 2026-01-19 10:30

Data View: Production Analytics
ID: dv_12345
Components: 145 metrics, 287 dimensions

Quality:
  HIGH: 1
  MEDIUM: 2

Generated by CJA SDR Generator v3.0.11
```

**Usage Examples:**
```bash
# Initialize Git repository (one-time setup)
cja_auto_sdr --git-init --git-dir ./sdr-snapshots

# Generate SDR and commit to Git
cja_auto_sdr dv_12345 --git-commit

# Generate with custom commit message
cja_auto_sdr dv_12345 --git-commit --git-message "Pre-release snapshot"

# Generate, commit, and push to remote
cja_auto_sdr dv_12345 --git-commit --git-push

# Multiple data views with Git commits
cja_auto_sdr dv_prod dv_staging dv_dev --git-commit
```

**New Functions:**
- `is_git_repository()`: Check if a directory is a Git repository
- `git_get_user_info()`: Get Git user name and email
- `save_git_friendly_snapshot()`: Save snapshot in Git-friendly format
- `generate_git_commit_message()`: Generate descriptive commit messages
- `git_commit_snapshot()`: Stage and commit snapshot changes
- `git_init_snapshot_repo()`: Initialize a new Git repository

**28 New Tests** in `tests/test_git_integration.py`:
- `is_git_repository` tests (5 tests)
- `save_git_friendly_snapshot` tests (7 tests)
- `generate_git_commit_message` tests (4 tests)
- `git_init_snapshot_repo` tests (4 tests)
- `git_commit_snapshot` tests (4 tests)
- CLI argument tests (4 tests)

**New Documentation:**
- [Git Integration Guide](docs/GIT_INTEGRATION.md) - Comprehensive guide with examples, best practices, CI/CD integration, and troubleshooting

#### Compare With Previous Snapshot (New Feature)

**`--compare-with-prev`**: Automatically find and compare against the most recent snapshot for a data view.

Instead of manually specifying snapshot paths:
```bash
# Before: Required knowing the exact snapshot path
cja_auto_sdr dv_12345 --diff-snapshot ./snapshots/dv_12345_20260120_103045.json
```

Now you can simply:
```bash
# After: Automatically finds the most recent snapshot
cja_auto_sdr dv_12345 --compare-with-prev
```

**Features:**
- Searches `--snapshot-dir` (default: `./snapshots`) for snapshots matching the data view ID
- Automatically selects the most recent snapshot by timestamp
- Works with both data view IDs and names
- Combines seamlessly with other diff options (`--changes-only`, `--format`, etc.)

**Usage Examples:**
```bash
# Compare against most recent snapshot in default directory
cja_auto_sdr dv_12345 --compare-with-prev

# Compare against most recent snapshot in custom directory
cja_auto_sdr dv_12345 --compare-with-prev --snapshot-dir ./my_snapshots

# With other diff options
cja_auto_sdr dv_12345 --compare-with-prev --changes-only --format markdown
```

**New Method:**
- `SnapshotManager.get_most_recent_snapshot()`: Find the most recent snapshot for a specific data view in a directory

**5 New Tests** for `--compare-with-prev`:
- `test_compare_with_prev_flag_default`: Verifies default is False
- `test_compare_with_prev_flag_enabled`: Verifies flag can be enabled
- `test_compare_with_prev_with_snapshot_dir`: Verifies works with custom snapshot directory
- `test_get_most_recent_snapshot_returns_latest`: Verifies correct snapshot selection
- `test_get_most_recent_snapshot_filters_by_data_view`: Verifies filtering by data view ID

#### Diff Summary Totals

Enhanced diff output now includes total change counts across all component types for quick at-a-glance summaries.

**Console Output:**
```
================================================================================
Total: 4 added, 6 removed, 3 modified
  Metrics: 3 added, 2 removed, 1 modified
  Dimensions: 1 added, 4 removed, 2 modified
================================================================================
```

**New `DiffSummary` Properties:**
- `total_added`: Sum of metrics_added + dimensions_added
- `total_removed`: Sum of metrics_removed + dimensions_removed
- `total_modified`: Sum of metrics_modified + dimensions_modified
- `total_summary`: Human-readable string (e.g., "4 added, 6 removed, 3 modified")

**Updated Output Formats:**
- **Console**: Color-coded totals in footer (green for added, red for removed, yellow for modified)
- **Markdown**: Uses `total_summary` in summary section
- **JSON**: Includes `total_added`, `total_removed`, `total_modified`, `total_summary` fields

**9 New Tests** for diff summary totals:
- `test_total_added`: Verifies total_added calculation
- `test_total_removed`: Verifies total_removed calculation
- `test_total_modified`: Verifies total_modified calculation
- `test_total_summary_with_changes`: Verifies formatted summary string
- `test_total_summary_no_changes`: Verifies "No changes" output
- `test_total_summary_partial_changes`: Verifies only non-zero values shown

#### Performance Optimizations

**Vectorized Markdown Table Generation:**
- Replaced `DataFrame.iterrows()` with vectorized `DataFrame.apply()` for markdown table generation
- 2-5x faster markdown generation for large data views

**Excel Format Caching:**
- Added `ExcelFormatCache` class to reuse format objects across Excel sheets
- Reduces memory allocation overhead and improves Excel generation performance

**Lazy Logging in Hot Paths:**
- Added `logger.isEnabledFor()` checks before expensive log message construction in `ValidationCache` methods
- Reduces logging overhead in production mode

#### Diff Output Control

**`--group-by-field-limit N`**: Control the number of items shown per section in `--group-by-field` output.
- Default is 10 items per section
- Use `--group-by-field-limit 0` for unlimited (no truncation)
- Applies to CHANGES BY FIELD, ADDED, and REMOVED sections

```bash
# Show all items (no truncation)
cja_auto_sdr --diff dv_12345 dv_67890 --group-by-field --group-by-field-limit 0

# Show first 25 items per section
cja_auto_sdr --diff dv_12345 dv_67890 --group-by-field --group-by-field-limit 25
```

**6 New Tests** for `--group-by-field-limit`:
- `test_grouped_by_field_limit_default`: Verifies default limit of 10 truncates output
- `test_grouped_by_field_limit_zero_shows_all`: Verifies limit=0 shows all items
- `test_grouped_by_field_limit_custom`: Verifies custom limit values work correctly
- `test_grouped_by_field_limit_added_removed`: Verifies limit applies to ADDED/REMOVED sections
- `test_parse_group_by_field_limit_flag`: CLI argument parsing test
- `test_parse_group_by_field_limit_default`: CLI default value test

### Changed
- **Test Count**: 623 → 672 tests (+28 Git integration tests, +6 group-by-field-limit tests, +14 compare-with-prev and diff summary tests)
- **Documentation**: 14 → 15 guides (new Git Integration guide)

### Backward Compatibility
- **Full Backward Compatibility**: All existing commands continue to work unchanged
- **No Breaking Changes**: All 672 tests pass
- **New Features Optional**: Git integration and `--compare-with-prev` are opt-in via CLI flags

---

## [3.0.10] - 2026-01-18

### Highlights
- **Data View Diff Comparison (New)** - Compare data views to identify added, removed, and modified components with 20+ CLI options
- **Snapshot-to-Snapshot Comparison** - Compare two snapshot files directly without API calls
- **Auto-Snapshot on Diff** - Automatically save timestamped snapshots during diff comparisons for audit trails
- **Smart Name Resolution** - Fuzzy matching suggestions for typos, interactive disambiguation for duplicates
- **UX Quick Wins** - `--open` flag, `--stats` mode, `--output -` for stdout, machine-readable `--list-dataviews`
- **Comprehensive Type Hints** - Full type annotations for improved IDE support and static analysis
- **Configuration Dataclasses** - Centralized, testable configuration with `SDRConfig`, `RetryConfig`, `CacheConfig`, `LogConfig`, `WorkerConfig`
- **Custom Exception Hierarchy** - Better error handling with `CJASDRError`, `ConfigurationError`, `APIError`, `ValidationError`, `OutputError`
- **OutputWriter Protocol** - Standardized interface for output format writers
- **Expanded Test Coverage** - 623 total tests (+210 new: 139 diff comparison + 39 edge cases + 5 format validation + 27 UX features)

This release introduces the **Data View Diff Comparison** feature for change tracking and CI/CD integration, **Auto-Snapshot** for automatic audit trails, **UX Quick Wins** for better developer experience, plus **code maintainability** improvements (type hints, centralized configuration) and **developer experience** enhancements (better exceptions, standardized interfaces) while maintaining full backward compatibility.

### Added

#### Auto-Snapshot on Diff (New Feature)
Automatically save timestamped snapshots during diff comparisons—no extra commands needed.

- **`--auto-snapshot`**: Enable automatic snapshot saving during `--diff` or `--diff-snapshot` operations
- **`--snapshot-dir DIR`**: Directory for auto-saved snapshots (default: `./snapshots`)
- **`--keep-last N`**: Retention policy to keep only the last N snapshots per data view (0 = keep all)
- **Timestamped Filenames**: Snapshots saved with format `DataViewName_dv_id_YYYYMMDD_HHMMSS.json`
- **Audit Trail**: Every comparison automatically documents the "before" state
- **CI/CD Friendly**: Scheduled diffs build history automatically without manual intervention
- **Zero Friction**: Transparent operation—just add `--auto-snapshot` to existing commands

**Usage Examples:**
```bash
# Auto-save snapshots during diff comparison
cja_auto_sdr --diff dv_A dv_B --auto-snapshot

# Custom snapshot directory
cja_auto_sdr --diff dv_A dv_B --auto-snapshot --snapshot-dir ./history

# With retention policy (keep last 10 per data view)
cja_auto_sdr --diff dv_A dv_B --auto-snapshot --keep-last 10

# Works with diff-snapshot too (saves current state)
cja_auto_sdr dv_123 --diff-snapshot baseline.json --auto-snapshot
```

**New SnapshotManager Methods:**
- `generate_snapshot_filename()`: Creates timestamped, sanitized filenames
- `apply_retention_policy()`: Deletes old snapshots beyond retention limit

**16 New Tests** for auto-snapshot functionality:
- Filename generation (4 tests): with/without name, special chars, truncation
- Retention policy (5 tests): keep all, delete old, per-data-view, empty/nonexistent dirs
- CLI arguments (7 tests): defaults, custom values, all flags together

#### UX Quick Wins (Developer Experience)
Four new features to improve daily workflows and scripting integration.

##### Auto-Open Generated Files (`--open`)
Open generated SDR files automatically in the default application after creation.

- **Cross-Platform Support**: Works on macOS (`open`), Linux (`xdg-open`), and Windows (`os.startfile`)
- **Batch Mode Support**: Opens all successfully generated files when processing multiple data views
- **Graceful Fallback**: HTML files fall back to `webbrowser` module if system commands fail

```bash
# Generate SDR and open immediately
cja_auto_sdr dv_12345 --open

# Batch processing - opens all successful files
cja_auto_sdr dv_1 dv_2 dv_3 --open
```

##### Stdout Output for Piping (`--output -`)
Write JSON or CSV output directly to stdout for Unix-style piping and scripting.

- **`--output -`** or **`--output stdout`**: Write to standard output instead of a file
- **Implicit Quiet Mode**: Automatically suppresses decorative output when writing to stdout
- **Pipeline Friendly**: Enables `cja_auto_sdr ... | jq ...` workflows

```bash
# Pipe data view list to jq for processing
cja_auto_sdr --list-dataviews --output - | jq '.dataViews[].id'

# Get stats as JSON to stdout
cja_auto_sdr dv_12345 --stats --output -

# CSV output for spreadsheet import
cja_auto_sdr --list-dataviews --format csv --output - > dataviews.csv
```

##### Quick Statistics Mode (`--stats`)
Get quick metrics and dimension counts without generating full SDR reports.

- **Fast Overview**: Shows metrics count, dimensions count, and totals for each data view
- **Multiple Data Views**: Process multiple data views in one command with aggregated totals
- **Multiple Formats**: Table (default), JSON, or CSV output

```bash
# Quick stats for a single data view
cja_auto_sdr dv_12345 --stats

# Stats for multiple data views with JSON output
cja_auto_sdr dv_1 dv_2 dv_3 --stats --format json
```

##### Machine-Readable `--list-dataviews`
Enhanced `--list-dataviews` with JSON and CSV output formats for scripting.

- **`--format json`**: Output data views as JSON with `dataViews` array and `count`
- **`--format csv`**: Output as CSV with `id,name,owner` columns
- **Stdout Support**: Use `--output -` to pipe to other tools

```bash
# JSON output for scripting
cja_auto_sdr --list-dataviews --format json

# JSON to stdout for piping
cja_auto_sdr --list-dataviews --output - | jq '.dataViews[] | select(.name | contains("Prod"))'
```

**27 New Tests** for UX features in `tests/test_ux_features.py`:
- `--open` flag registration and cross-platform behavior (7 tests)
- `--output` argument handling (3 tests)
- `--stats` mode CLI parsing (5 tests)
- `--list-dataviews` format options (3 tests)
- `show_stats()` function with JSON/CSV/table output (3 tests)
- `list_dataviews()` function with JSON/CSV output (3 tests)
- Combined feature usage (3 tests)

#### Comprehensive Type Hints
- **Function Signatures**: All key functions now have complete type annotations
- **Return Types**: Explicit return types for better IDE autocompletion
- **Complex Types**: Uses `typing` module for `Optional`, `Union`, `List`, `Dict`, `Callable`, `TypeVar`
- **Path Types**: `Union[str, Path]` for flexible path handling
- **Benefits**:
  - Better IDE support (autocompletion, type checking)
  - Catch bugs at development time
  - Self-documenting code

#### Configuration Dataclasses
- **`RetryConfig`**: Retry settings (max_retries, base_delay, max_delay, exponential_base, jitter) with `to_dict()` method
- **`CacheConfig`**: Cache settings (enabled, max_size, ttl_seconds)
- **`LogConfig`**: Logging settings (level, file_max_bytes, file_backup_count)
- **`WorkerConfig`**: Worker settings (api_fetch_workers, validation_workers, batch_workers, max_batch_workers)
- **`SDRConfig`**: Master configuration combining all above with `from_args()` factory method
- **Default Instances**: `DEFAULT_RETRY`, `DEFAULT_CACHE`, `DEFAULT_LOG`, `DEFAULT_WORKERS` for easy access
- **Benefits**:
  - Single source of truth for configuration
  - Easy to pass configuration around
  - Testable configuration
  - Self-documenting with dataclass field defaults

#### Custom Exception Hierarchy
- **`CJASDRError`**: Base exception for all SDR errors with message and details
- **`ConfigurationError`**: Invalid config, missing credentials (includes config_file, field context)
- **`APIError`**: API communication failures (includes status_code, operation, original_error)
- **`ValidationError`**: Data quality validation failures (includes item_type, issue_count)
- **`OutputError`**: File writing failures (includes output_path, output_format, original_error)
- **Benefits**:
  - Catch specific error types for targeted handling
  - Better error messages with context
  - Cleaner exception handling code

#### OutputWriter Protocol
- **`OutputWriter`**: Runtime-checkable Protocol defining the interface for output format writers
- **Standard Interface**: `write(metrics_df, dimensions_df, dataview_info, output_path, quality_results) -> str`
- **Benefits**:
  - Easy to add new output formats
  - Improved testability with mock writers
  - Clear contract for writer implementations

#### Data View Diff Comparison (New Feature)

Compare two data views or track changes over time with snapshots. This feature is entirely new in v3.0.10.

**Core Functionality:**
- **`--diff`**: Compare two live data views side-by-side
- **`--snapshot`**: Save a data view state to JSON for later comparison
- **`--diff-snapshot`**: Compare current data view against a saved snapshot
- **`--compare-snapshots A B`**: Compare two snapshot files directly without API calls (offline analysis)
- **Identified Changes**: Added, removed, and modified metrics/dimensions with field-level details
- **Multiple Output Formats**: Console (default), JSON, HTML, Markdown, Excel, CSV
- **CI/CD Integration**: Exit code 2 when differences found, exit code 3 when threshold exceeded

**Smart Name Resolution:**
- **Fuzzy Name Matching**: Suggests similar data view names when exact match not found (Levenshtein distance)
- **Interactive Disambiguation**: Prompts user to select when name matches multiple data views (TTY mode only)
- **API Response Caching**: 5-minute TTL cache for data view listings reduces API calls

**Display Options:**
- **ANSI Color-Coded Diff Output**: Green for added `[+]`, red for removed `[-]`, yellow for modified `[~]`; use `--no-color` to disable
- **Percentage Stats**: Shows change percentage for metrics and dimensions (e.g., "10.5% changed")
- **Natural Language Summary**: Copy-paste friendly (e.g., "Metrics: 3 added, 2 removed; Dimensions: 1 modified")
- **Side-by-Side View**: `--side-by-side` flag for visual comparison in console and markdown
- **`--changes-only`**: Hide unchanged items, show only differences
- **`--summary`**: Show summary statistics only

**Filtering Options:**
- **`--show-only TYPES`**: Filter by change type (added, removed, modified)
- **`--metrics-only`**: Compare only metrics
- **`--dimensions-only`**: Compare only dimensions
- **`--ignore-fields FIELDS`**: Exclude specific fields from comparison
- **`--extended-fields`**: Include 20+ additional fields (attribution, bucketing, persistence, etc.)

**Advanced Options:**
- **`--quiet-diff`**: Suppress all output, return only exit code (0=no changes, 2=changes, 3=threshold exceeded)
- **`--reverse-diff`**: Swap source and target without reordering arguments
- **`--warn-threshold PERCENT`**: Exit with code 3 if change percentage exceeds threshold
- **Breaking Change Detection**: Automatically flags type/schemaPath changes and component removals
- **`--group-by-field`**: Group changes by field name instead of component
- **`--diff-output FILE`**: Write output directly to file instead of stdout
- **`--format-pr-comment`**: GitHub/GitLab PR comment format with collapsible details
- **`--diff-labels A B`**: Custom labels for source and target

**Extended Field Comparison**: `--extended-fields` flag to compare 20+ additional fields:
  - Attribution: `attribution`, `attributionModel`, `lookbackWindow`
  - Formatting: `format`, `precision`
  - Visibility: `hidden`, `hideFromReporting`
  - Bucketing: `bucketing`, `bucketingSetting`
  - Persistence: `persistence`, `persistenceSetting`, `allocation`
  - Calculated: `formula`, `isCalculated`, `derivedFieldId`
  - Other: `segmentable`, `reportable`, `componentType`, `dataType`, `hasData`, `approved`
- **Filter by Change Type**: `--show-only` flag to filter results (added, removed, modified)
- **Filter by Component Type**: `--metrics-only` and `--dimensions-only` flags
- **Side-by-Side View**: `--side-by-side` flag for visual comparison in console and markdown
- **New CLI Arguments**:
  - `--show-only TYPES` - Filter by change type (comma-separated)
  - `--metrics-only` - Compare only metrics
  - `--dimensions-only` - Compare only dimensions
  - `--extended-fields` - Use extended field comparison
  - `--side-by-side` - Show side-by-side comparison view
  - `--compare-snapshots A B` - Compare two snapshot files directly (no API calls)

#### Edge Case Tests
- **39 New Tests** in `tests/test_edge_cases.py`:
  - Custom exception hierarchy (9 tests)
  - Configuration dataclasses (9 tests)
  - Default configuration instances (5 tests)
  - OutputWriter Protocol (3 tests)
  - Retry edge cases (3 tests)
  - Empty DataFrame handling (3 tests)
  - Cache edge cases (3 tests)
  - DataFrame column handling (2 tests)
  - Concurrent access edge cases (1 test)

#### Diff Comparison Tests (New)
- **123 New Tests** in `tests/test_diff_comparison.py`:
  - Core comparison logic (12 tests)
  - DiffSummary dataclass (8 tests)
  - Console output formatting (6 tests)
  - JSON/HTML/Markdown output (9 tests)
  - Snapshot save/load (5 tests)
  - CLI argument parsing (12 tests)
  - Extended field comparison (3 tests)
  - Show-only filter (3 tests)
  - Metrics-only and dimensions-only (2 tests)
  - Side-by-side output (3 tests)
  - Large dataset performance (3 tests)
  - Unicode edge cases (4 tests)
  - Deeply nested structures (3 tests)
  - Concurrent comparison thread safety (1 test)
  - Snapshot version migration (3 tests)
  - Percentage stats (5 tests)
  - Colored console output (2 tests)
  - Group-by-field output (1 test)
  - PR comment output (2 tests)
  - Breaking change detection (3 tests)
  - New CLI flags (7 tests)
  - Ambiguous name resolution (6 tests)
  - Levenshtein distance algorithm (4 tests)
  - Fuzzy name matching (5 tests)
  - Data view cache (4 tests)
  - Snapshot-to-snapshot comparison (4 tests)
  - Interactive selection prompts (4 tests)
  - New feature CLI arguments (2 tests)
- **5 New Tests** for format validation in `tests/test_cli.py`:
  - Console format for diff mode
  - Console format parsing for SDR (runtime validation)
  - Excel/JSON/all format validation
- **16 New Tests** for auto-snapshot functionality:
  - Filename generation tests (4 tests)
  - Retention policy tests (5 tests)
  - CLI argument parsing tests (7 tests)
- **Total Test Count**: 413 (v3.0.9) → 623 (v3.0.10) = +210 tests (100% pass rate)

### Fixed

#### Diff Comparison NaN Handling
- **False Positive Fix**: Components with identical null/NaN values no longer incorrectly flagged as "modified"
- **Proper NaN Detection**: Added `pd.isna()` check in value normalization to treat NaN same as null/empty
- **Clearer Display**: Empty/null/NaN values now display as `(empty)` instead of `nan` in diff output
- **Consistent Formatting**: Applied across console, markdown, side-by-side, and breaking changes output

#### Ambiguous Name Resolution in Diff Mode
- **Separate Resolution**: Source and target identifiers are now resolved independently for diff operations
- **Exact Match Validation**: Diff operations (`--diff`, `--snapshot`, `--diff-snapshot`) now require exactly one data view match per identifier
- Previously, both identifiers were combined and resolved together, which could lead to incorrect comparisons when data view names matched multiple entries

### Changed
- **DEFAULT_RETRY_CONFIG**: Now uses `DEFAULT_RETRY.to_dict()` for backward compatibility
- **Type Annotations**: Added to all writer functions, core processing functions, retry functions
- **Import Section**: Extended to include `TypeVar`, `Protocol`, `runtime_checkable`, `field`
- **Format Validation**: `--format console` now shows clear error for SDR generation (console is diff-only)

### Backward Compatibility
- **Full Backward Compatibility**: All existing code continues to work unchanged
- **No Breaking Changes**: All 623 tests pass
- **DEFAULT_RETRY_CONFIG Dict**: Still available as a dict for legacy code
- **Configuration Migration**: Existing configurations work without changes

---

## [3.0.9] - 2026-01-16

### Highlights
- **Data View Names** - Use human-readable names instead of IDs (e.g., `"Production Analytics"` vs `dv_12345`)
- **Shell Tab-Completion** - Optional bash/zsh tab-completion for all CLI flags and values via argcomplete
- **Windows Support Improvements** - Comprehensive Windows-specific documentation and troubleshooting
- **Config File Rename** - Clearer naming: `config.json` instead of `myconfig.json`
- **Markdown Output Format** - Export SDRs as GitHub/Confluence-compatible markdown with tables, TOC, and collapsible sections
- **Enhanced Error Messages** - Contextual, actionable error messages with step-by-step fix guidance and documentation links
- **Comprehensive Test Coverage** - 413 total tests covering all core processing components
- **UX Enhancements** - Quiet mode progress bar suppression, retry env vars, improved help text

This release focuses on **ease of use** (name support, Windows compatibility), **documentation workflows** (markdown export), and **user experience** (helpful error messages, better CLI).

### Added

#### Data View Name Support
- **Use Names Instead of IDs**: Specify data views by their human-readable name (e.g., `"Production Analytics"`) instead of ID (e.g., `dv_677ea9291244fd082f02dd42`)
- **Automatic Name Resolution**: Tool automatically resolves names to IDs by fetching available data views
- **Duplicate Name Handling**: If multiple data views share the same name, all matching views are processed
- **Mixed Input Support**: Combine IDs and names in the same command (e.g., `cja_auto_sdr dv_12345 "Staging" "Test"`)
- **Case-Sensitive Exact Matching**: Names must match exactly as they appear in CJA
- **Enhanced CLI Help**: Updated command-line help to show both ID and name options
- **Name Resolution Feedback**: Shows which names resolved to which IDs before processing
- **16 New Tests**: Comprehensive test coverage for name resolution (`tests/test_name_resolution.py`)
- **New Documentation**: Complete guide in `docs/DATA_VIEW_NAMES.md`
- **Benefits**:
  - Easier to remember and use
  - More readable scripts and documentation
  - Better for scheduled reports and CI/CD pipelines
  - Reduces copy-paste errors with long IDs

#### Windows Support Improvements
- **Windows-Specific Troubleshooting**: New comprehensive section in `docs/TROUBLESHOOTING.md` covering:
  - NumPy ImportError solutions (4 different approaches)
  - `uv run` command alternatives for Windows
  - PowerShell execution policy issues
  - Path separator guidance
  - Virtual environment activation for PowerShell, CMD, and Git Bash
  - Windows diagnostic script (PowerShell equivalent)
  - Common Windows commands reference table
  - Recommended Windows setup with step-by-step guidance
- **Windows Native Setup Guide**: New "Option 5" in `docs/INSTALLATION.md` for pure Python installation without `uv`
- **Platform-Specific Examples**: All documentation now includes separate Windows PowerShell examples
- **README Updates**: Windows-specific notes and alternatives throughout Quick Start section

#### Configuration File Rename
- **Clearer Naming**: Renamed `myconfig.json` to `config.json` for better clarity
- **Updated Example File**: Renamed `myconfig.json.example` to `config.json.example`
- **Consistent Documentation**: All documentation and error messages updated to use `config.json`
- **Sample Config Generator**: Updated to generate `config.sample.json` with clear instructions
- **Benefits**:
  - More standard naming convention
  - Less confusion about whether "myconfig" is a placeholder
  - Clearer intent as the configuration file

#### Markdown Output Format
- **New `--format markdown` option**: Export SDR as GitHub/Confluence-compatible markdown
- **GitHub-Flavored Markdown Tables**: Properly formatted tables with pipe separators
- **Table of Contents**: Auto-generated TOC with section anchor links
- **Collapsible Sections**: Large tables (>50 rows) automatically use `<details>` tags for better readability
- **Special Character Escaping**: Proper escaping of pipes, backticks, and other markdown syntax
- **Issue Summary for Data Quality**: Severity counts with emoji indicators (🔴 CRITICAL, 🟠 HIGH, 🟡 MEDIUM, ⚪ LOW, 🔵 INFO)
- **Row Counts**: Each section shows total item counts
- **Unicode Support**: Full support for international characters
- **Metadata Section**: Formatted key-value pairs for document information
- **Professional Footer**: Generated by CJA Auto SDR Generator attribution
- **Use Cases**:
  - Paste directly into GitHub README files, issues, or wiki pages
  - Copy to Confluence pages for team documentation
  - Version control friendly format for tracking changes
  - Lightweight alternative to Excel/HTML for documentation workflows

#### Enhanced Error Messages with Actionable Suggestions
- **ErrorMessageHelper Class**: New comprehensive error message system providing contextual, actionable guidance
- **HTTP Status Code Messages**: Detailed error messages for all common HTTP errors:
  - **400 Bad Request**: Parameter validation and request structure guidance
  - **401 Authentication Failed**: Credential verification steps and setup links
  - **403 Access Forbidden**: Permission troubleshooting and admin contact guidance
  - **404 Resource Not Found**: Data view validation with `--list-dataviews` suggestion
  - **429 Rate Limit Exceeded**: Worker reduction, caching, and retry configuration suggestions
  - **500 Internal Server Error**: Adobe status page links and retry guidance
  - **502 Bad Gateway**: Network issue identification and retry suggestions
  - **503 Service Unavailable**: Maintenance detection and status page links
  - **504 Gateway Timeout**: Large data view handling and timeout configuration
- **Network Error Messages**: Contextual guidance for connection issues:
  - **ConnectionError**: Internet connectivity and firewall troubleshooting
  - **TimeoutError**: Network stability and retry configuration
  - **SSLError**: Certificate updates and system time verification
  - **ConnectionResetError**: Temporary network issue handling
- **Configuration Error Messages**: Step-by-step setup guidance:
  - **File Not Found**: Sample config generation and environment variable alternatives
  - **Invalid JSON**: Common JSON errors, validation tools, and syntax checking
  - **Missing Credentials**: Required fields list and Developer Console links
  - **Invalid Format**: Credential format validation and regeneration guidance
- **Data View Error Messages**: Targeted troubleshooting with context:
  - Shows available data view count when view not found
  - Lists accessible data views to help identify correct ID
  - Provides specific guidance when no data views are accessible
- **Documentation Links**: All error messages include relevant documentation URLs
- **Multi-Level Suggestions**: Errors provide 3-10 actionable steps to resolve issues
- **Error Context**: All error messages include operation name and failure context

#### Integration Points
- **Retry Mechanism**: Enhanced error messages automatically shown after all retry attempts fail
- **Configuration Validation**: Config file errors now show detailed setup instructions
- **Data View Validation**: Not found errors include list of available data views
- **Network Operations**: All API calls provide enhanced error context on failure

#### UX Enhancements
- **Progress Bars Respect Quiet Mode**: Progress bars in `ParallelAPIFetcher` and `DataQualityChecker` are now disabled when using `--quiet` flag for cleaner output in scripts and CI/CD pipelines
- **Retry Configuration via Environment Variables**: Configure retry behavior through environment variables:
  - `MAX_RETRIES` - Maximum API retry attempts (default: 3)
  - `RETRY_BASE_DELAY` - Initial retry delay in seconds (default: 1.0)
  - `RETRY_MAX_DELAY` - Maximum retry delay in seconds (default: 30.0)
- **Python 3.14 Requirement in Help**: `--help` now displays Python version requirement in the epilog
- **Improved --format Help Text**: Clarified that `--format all` generates all formats simultaneously
- **VALIDATION_SCHEMA Documentation**: Added detailed comments explaining the schema's purpose and usage
- **Enhanced Property Docstrings**: Improved `file_size_formatted` docstring with example output

#### Shell Tab-Completion Support
- **argcomplete Integration**: Optional shell tab-completion for all CLI flags and values
- **Bash/Zsh Support**: Works with both bash and zsh shells after one-time activation
- **Flag Completion**: Tab-complete all `--` flags (e.g., `--format`, `--log-level`, `--workers`)
- **Value Completion**: Tab-complete flag values (e.g., `--format <TAB>` shows `excel csv json html markdown all`)
- **Optional Dependency**: Install with `pip install cja-auto-sdr[completion]` or `pip install argcomplete`
- **Zero Overhead**: No performance impact if argcomplete is not installed
- **Documentation**: Full setup instructions in `docs/CLI_REFERENCE.md`

#### CLI Documentation Alignment
- **CLI_REFERENCE.md**: Updated to match README guidance with three invocation methods:
  - `uv run cja_auto_sdr ...` — works immediately on macOS/Linux, may have issues on Windows
  - `cja_auto_sdr ...` — after activating the venv
  - `python cja_sdr_generator.py ...` — run the script directly (most reliable on Windows)
- **Consistent Version References**: All documentation updated to reference v3.0.9

#### Testing
- **182 New Tests**: Comprehensive test coverage expansion
- **Name Resolution Tests** (`tests/test_name_resolution.py`): ID detection, single/multiple name resolution, duplicate handling, error scenarios
- **Parallel API Fetcher Tests** (`tests/test_parallel_api_fetcher.py`): Thread pool execution, API data fetching, error handling
- **Batch Processor Tests** (`tests/test_batch_processor.py`): Worker coordination, result aggregation, summary output
- **Process Single Dataview Tests** (`tests/test_process_single_dataview.py`): End-to-end processing, output formats, caching
- **Excel Formatting Tests** (`tests/test_excel_formatting.py`): Sheet formatting, severity colors, column/row sizing
- **CJA Initialization Tests** (`tests/test_cja_initialization.py`): Config loading, credential validation, connection testing
- **Integration Tests**: Verification of enhanced messages in retry and validation flows
- **Markdown Output Tests**: Full coverage of markdown generation, escaping, collapsible sections, Unicode, and more
- **CLI Tests** (`tests/test_cli.py`): Expanded with 14 new tests for retry arguments (11) and --validate-config flag (3)
- **Total Test Count**: 413 tests (100% pass rate)

### Improved
- **User Experience**:
  - Data views can now be referenced by memorable names instead of long IDs
  - Errors now provide clear "Why this happened" and "How to fix it" sections
  - Windows users have comprehensive platform-specific documentation
  - Configuration file naming is more intuitive
  - Progress bars no longer show when using `--quiet` flag
  - Retry settings can be configured via environment variables for CI/CD pipelines
- **Documentation**: More readable commands in scripts, CI/CD pipelines, and documentation
- **Troubleshooting Time**: Reduced with direct links to relevant documentation and platform-specific guides
- **Developer Onboarding**: Better guidance for common setup issues across all platforms
- **Support Burden**: Self-service error resolution and clear documentation reduce support requests
- **Cross-Platform Support**: Equal support quality for Windows, macOS, and Linux users

### Changed
- **Configuration File Name**: `myconfig.json` → `config.json` (users should rename their existing file)
- **Example Config File**: `myconfig.json.example` → `config.json.example`
- **Sample Config Output**: `myconfig.sample.json` → `config.sample.json`
- **CLI Help Text**: Updated to reflect ID or name support for data views
- **Documentation**: Updated throughout to use `config.json` naming

### Backward Compatibility
- **Full Backward Compatibility**: All existing commands and scripts continue to work
- **ID-Based Commands**: All existing ID-based data view specifications work unchanged
- **Config File Migration**: Users need to rename `myconfig.json` to `config.json` (simple `mv` command)
- **No Breaking Changes**: All tests pass, including legacy functionality

## [3.0.8] - 2026-01-15

### Added

#### Console Script Entry Points
- **`cja_auto_sdr` command**: Run the tool directly without `python` prefix
  - `cja_auto_sdr dv_12345` instead of `uv run python cja_sdr_generator.py dv_12345`
  - Also available as `cja-auto-sdr` (hyphenated version)
- **Proper packaging**: Added `[build-system]` with hatchling for standard Python packaging
- **Multiple installation options**:
  - `uv run cja_auto_sdr` - run within uv-managed environment
  - `pip install .` then `cja_auto_sdr` - install globally or in any virtualenv
  - Original `python cja_sdr_generator.py` continues to work

#### Environment Variable Credentials Support
- **Environment Variable Loading**: Credentials can now be loaded from environment variables
  - `ORG_ID`: Adobe Organization ID
  - `CLIENT_ID`: OAuth Client ID
  - `SECRET`: Client Secret
  - `SCOPES`: OAuth scopes
  - `SANDBOX`: Sandbox name (optional)
- **Priority Order**: Environment variables take precedence over `config.json`
- **Optional python-dotenv**: Install `python-dotenv` to enable automatic `.env` file loading
- **`.env.example`**: Template file for environment variable configuration
- **Full Backwards Compatibility**: Existing `config.json` configurations continue to work unchanged

#### Batch Processing Improvements
- **File Size in Batch Summary**: Each successful data view now shows its output file size
- **Total Output Size**: Batch summary includes total combined output size for all files
- **Correlation IDs**: Batch processing now includes 8-character correlation IDs in all log messages for easier log tracing

#### Data Quality Improvements
- **Complete Item Lists**: Data quality issues now show ALL affected item names
  - Previously limited to 5-20 items depending on issue type
  - Provides complete visibility for large data views with many issues

#### New CLI Commands
- **`--validate-config`**: Validate configuration and API connectivity without processing any data views
  - Tests environment variables or config file
  - Verifies API connection
  - Reports number of accessible data views

#### Configurable Retry Settings
- **`--max-retries`**: Maximum API retry attempts (default: 3)
- **`--retry-base-delay`**: Initial retry delay in seconds (default: 1.0)
- **`--retry-max-delay`**: Maximum retry delay in seconds (default: 30.0)

#### Environment Variable Enhancements
- **`OUTPUT_DIR`**: Output directory can now be set via environment variable
- **`.env` Loading Feedback**: Debug logging shows whether `.env` file was loaded

#### Test Infrastructure
- **Coverage Reporting**: pytest-cov integration with coverage threshold
- **pytest-cov Dependency**: Added as dev dependency for coverage reporting

#### Developer Experience
- **`config.json.example`**: New template file for config file setup (complements `.env.example`)
- **JWT Deprecation Warning**: Config validation now warns when deprecated JWT fields (`tech_acct`, `private_key`, `pathToKey`) are detected, with migration guidance

#### Error Handling Improvements
- **Specific File I/O Exceptions**: CSV, JSON, and HTML writers now catch `PermissionError` and `OSError` with actionable messages
- **JSON Serialization Errors**: JSON writer catches `TypeError`/`ValueError` with clear "non-serializable values" message
- **Retry Troubleshooting**: Failed API retries now include actionable troubleshooting hints

#### Code Quality
- **Logging Constants**: Extracted `LOG_FILE_MAX_BYTES` (10MB) and `LOG_FILE_BACKUP_COUNT` (5) to constants section
- **Cache Statistics Method**: Added `ValidationCache.log_statistics()` for compact cache performance logging

### Changed
- **pytest.ini**: Coverage flags now optional (removes pytest-cov as hard requirement for running tests)

### Fixed

#### Critical: Exception Handling
- **Graceful Ctrl+C**: Fixed overly broad exception handlers that prevented graceful shutdown
  - Batch processing now properly handles `KeyboardInterrupt` and `SystemExit`
  - Dry-run mode properly handles interruption
  - List data views command properly handles interruption
  - All operations now allow graceful cancellation with Ctrl+C

#### HTTP Status Code Retry
- **Status Code Handling**: `RETRYABLE_STATUS_CODES` (408, 429, 500, 502, 503, 504) now properly trigger retries
  - Previously defined but never used
  - Added `RetryableHTTPError` exception class
  - API calls now check response status codes and retry appropriately

#### Code Quality
- **Deduplicated File Size Formatting**: Consolidated duplicate `_format_file_size` implementations into single `format_file_size()` utility function

### Removed

#### JWT Authentication Support
- **Removed JWT Authentication**: JWT (Service Account) authentication has been removed
  - Adobe has deprecated JWT credentials in favor of OAuth Server-to-Server
  - `tech_id` and `private_key` config fields are no longer supported
  - `TECH_ID` and `PRIVATE_KEY` environment variables are no longer supported
  - Users must migrate to OAuth Server-to-Server credentials
  - See [Adobe's migration guide](https://developer.adobe.com/developer-console/docs/guides/authentication/ServerToServerAuthentication/migration/) for details

### Changed
- Updated documentation with environment variable configuration instructions
- Batch summary output format now includes file size column for each data view
- Updated error messages to include environment variable configuration option
- Simplified configuration validation to OAuth-only fields

### Documentation
- Updated `README.md` with `.env` configuration option
- Updated `docs/INSTALLATION.md` with environment variable setup section (OAuth-only)
- Updated `docs/QUICKSTART_GUIDE.md` with dual configuration options
- Added `.env.example` template file

---

## [3.0.7] - 2026-01-11

### Added

#### Code Quality & Maintainability
- **Centralized Validation Schema (`VALIDATION_SCHEMA`)**: All field definitions consolidated into single module-level constant
  - `required_metric_fields`: Fields required for metrics validation
  - `required_dimension_fields`: Fields required for dimensions validation
  - `critical_fields`: Fields checked for null values
  - Single source of truth eliminates scattered field definitions
  - Easier to update validation rules across the codebase

- **Error Message Formatting Helper (`_format_error_msg`)**: Consistent error message formatting
  - Unified format: `"Error {operation} for {item_type}: {error}"`
  - Replaces 18 inconsistent inline error message formats
  - Easier to modify error format globally
  - Handles optional parameters gracefully

#### Performance Optimization
- **Cache Key Reuse Optimization**: Eliminates redundant DataFrame hashing
  - `ValidationCache.get()` now returns `(issues, cache_key)` tuple
  - `ValidationCache.put()` accepts optional `cache_key` parameter
  - Avoids rehashing same DataFrame on cache misses (5-10% faster)
  - Fully backward compatible - `cache_key` parameter is optional

#### Test Coverage Expansion
- **17 New Tests** added for new functionality:
  - Error message formatting tests (7 tests)
  - Validation schema tests (6 tests)
  - Cache key reuse optimization tests (4 tests)
- **Total test count**: 191 → 208 tests

### Changed
- `ValidationCache.get()` return type changed from `Optional[List[Dict]]` to `Tuple[Optional[List[Dict]], str]`
- Error logging calls throughout codebase now use `_format_error_msg()` helper
- Validation calls use `VALIDATION_SCHEMA` instead of inline field definitions

### Technical Details

**Cache Key Reuse Example:**
```python
# Before: DataFrame hashed twice on cache miss
result = cache.get(df, 'Metrics', required, critical)  # Hash 1
if result is None:
    # ... validation ...
    cache.put(df, 'Metrics', required, critical, issues)  # Hash 2

# After: Hash computed once, reused
result, cache_key = cache.get(df, 'Metrics', required, critical)  # Hash 1
if result is None:
    # ... validation ...
    cache.put(df, 'Metrics', required, critical, issues, cache_key)  # No rehash
```

---

## [3.0.6] - 2026-01-11

### Added

#### Robustness & Input Validation
- **CLI Parameter Bounds Checking**: All numeric CLI parameters now validated
  - `--workers`: Must be 1-256 (prevents crashes from invalid values)
  - `--cache-size`: Must be >= 1
  - `--cache-ttl`: Must be >= 1 second
  - `--max-issues`: Must be >= 0
- **Output Directory Error Handling**: Clear error messages for permission/disk issues when creating output directories
- **Log Directory Graceful Fallback**: If log directory can't be created, falls back to console-only logging instead of crashing

#### Logging Improvements
- **RotatingFileHandler**: Log files now rotate automatically at 10MB with 5 backups retained
  - Prevents unbounded disk usage during long-running automation/cron jobs
  - Total maximum log storage: ~60MB per session type

#### Configuration Validation
- **OAuth Scopes Warning**: Warns when OAuth Server-to-Server authentication is detected without `scopes` field
  - Provides example scopes string for proper API access
  - Helps catch common misconfiguration before authentication failures

#### Error Message Improvements
- **Empty Data View Diagnostics**: When no metrics/dimensions are returned, provides:
  - 4 possible causes (empty data view, permission issues, new data view, API issues)
  - 3 troubleshooting steps with actionable guidance
  - Improved error message text

#### New CLI Flag
- **`--clear-cache`**: Clear validation cache before processing
  - Use with `--enable-cache` for fresh validation when needed
  - Documents intent for cache clearing behavior

#### Code Quality
- **Extracted Constants**: Hardcoded worker counts replaced with named constants
  - `DEFAULT_API_FETCH_WORKERS = 3`
  - `DEFAULT_VALIDATION_WORKERS = 2`
  - `DEFAULT_BATCH_WORKERS = 4`
  - `MAX_BATCH_WORKERS = 256`
  - `DEFAULT_CACHE_SIZE = 1000`
  - `DEFAULT_CACHE_TTL = 3600`
- **Improved Docstrings**: Added parameter constraints and valid ranges to key functions
  - `process_single_dataview()`: Full parameter documentation
  - `BatchProcessor`: Comprehensive class docstring with all parameters
  - `ValidationCache`: Parameter constraints documented

### Changed
- Help text now shows parameter defaults and constraints from constants
- Log directory creation failures no longer crash the application

### Fixed
- Potential crash when `--workers 0` or negative values provided
- Potential crash when `--cache-size 0` provided
- Potential crash when `--cache-ttl 0` provided
- Cryptic error messages when output directory can't be created

---

## [3.0.5] - 2026-01-10

### Added

#### UX Improvements
- **File Size in Output**: Success message now displays output file size in human-readable format (B, KB, MB, GB)
- **`--validate-only`**: New alias for `--dry-run` with clearer semantics
- **`--max-issues N`**: Limit data quality issues to top N by severity (0 = show all)
  - Issues are sorted by severity (CRITICAL first) before limiting
  - Useful for data views with many issues to focus on most important ones
  - Works with all output formats

#### Test Coverage
- Added 8 new tests for UX improvements
- Total test count increased from 171 to 179

---

## [3.0.4] - 2026-01-10

### Added

#### CLI Usability Enhancements
- **`--list-dataviews`**: New flag to list all accessible data views without processing
  - Displays data view ID, name, and owner in a formatted table
  - Helps users discover available data view IDs before running reports
  - No data view ID argument required when using this flag
- **`--skip-validation`**: New flag to skip data quality validation for faster processing
  - Provides 20-30% performance improvement when validation is not needed
  - Useful for quick regeneration of reports when data quality is already known
  - Works with both single and batch processing modes
- **`--sample-config`**: New flag to generate a sample configuration file
  - Creates `myconfig.sample.json` with template for OAuth Server-to-Server authentication
  - Includes clear instructions for configuring credentials
  - No data view ID argument required when using this flag

#### Test Coverage Expansion
- Added 10 new CLI tests for new flags (--list-dataviews, --skip-validation, --sample-config)
- Added 3 new tests for sample config generation functionality
- Total test count increased from 161 to 171

---

## [3.0.3] - 2026-01-10

### Added

#### Retry with Exponential Backoff
- **Automatic Retry**: All API calls now automatically retry on transient network errors
- **Exponential Backoff**: Delay between retries increases exponentially (1s, 2s, 4s, etc.)
- **Jitter**: Random variation added to retry delays to prevent thundering herd problems
- **Configurable**: Default settings (3 retries, 1s base delay, 30s max delay) can be customized
- **Retryable Errors**: Handles ConnectionError, TimeoutError, and OSError automatically
- **Non-Blocking**: Non-retryable errors (ValueError, KeyError, etc.) fail immediately
- **Comprehensive Logging**: Warnings logged for each retry attempt with delay information

#### Retry Implementation Details
- `retry_with_backoff` decorator for wrapping functions with retry logic
- `make_api_call_with_retry` function for ad-hoc API calls with retry
- Applied to all CJA API calls: getDataViews, getDataView, getMetrics, getDimensions
- Applied to dry-run mode validation calls
- 21 new tests covering all retry scenarios

---

## [3.0.2] - 2026-01-10

### Added

#### CLI Quick Wins
- **Version Flag**: New `--version` flag to display program version (3.0.2)
- **Quiet Mode**: New `--quiet` / `-q` flag to suppress all output except errors and final summary
- **Color-Coded Output**: Console output now uses ANSI colors for better visual feedback
  - Green for success messages and successful data views
  - Red for error messages and failed data views
  - Yellow for warnings
  - Bold for headers and important information
- **Total Runtime Display**: Final summary now shows total runtime for all operations

#### Enhanced Config Validation
- **Schema-Based Validation**: Configuration file validation now uses a defined schema with type checking
- **Type Validation**: Validates that all config fields have the correct data types
- **Empty Value Detection**: Detects and reports empty values in required fields
- **Unknown Field Detection**: Warns about unrecognized fields (possible typos)
- **Private Key Validation**: Validates private key file path if provided as a file path

### Changed
- **Data View Validation**: Missing data views are now validated in main() instead of argparse, allowing `--version` flag to work without data view arguments
- **Config Validation Strictness**: Missing required config fields now causes validation to fail (previously only warned)
- **Test Count**: Expanded test suite from 136 to 140 tests

---

## [3.0.1] - 2026-01-09

### Added

#### Dry-Run Mode
- **Configuration Validation**: New `--dry-run` CLI flag to validate configuration and connectivity without generating reports
- **Three-Step Validation**: Validates config file, tests API connection, and verifies data view accessibility
- **Pre-Flight Checks**: Ideal for CI/CD pipelines and debugging connection issues before full processing
- **Actionable Output**: Clear success/failure indicators with suggested next steps

#### Progress Indicators
- **tqdm Integration**: Added progress bars for long-running operations with ETA and completion rate
- **Batch Processing Progress**: Visual progress tracking for multi-data-view batch operations
- **API Fetch Progress**: Progress indicators during parallel API data fetching
- **Validation Progress**: Progress bars for parallel validation operations

#### Excel Formatting Enhancements
- **Metrics/Dimensions Column Reordering**: Name column now appears first for better readability
- **Bold Name Column**: Name column in Metrics/Dimensions sheets styled bold for quick scanning
- **Optimized Column Widths**: Tighter column width limits (description: 55, name/title: 40) for better layout

### Changed
- **Dependencies**: Added `tqdm>=4.66.0` for progress bar support
- **Removed Unused Import**: Removed unused `asyncio` import from main module
- **Test Count**: Expanded test suite from 121 to 136 tests

### Fixed
- **Test Threshold Adjustment**: Updated parallel validation test threshold to account for progress bar overhead on small datasets

---

## [3.0.0] - 2026-01-08

### Added

#### Output Format Flexibility
- **Multiple Output Formats**: Support for Excel, CSV, JSON, HTML, and all formats simultaneously
- **CSV Output**: Individual CSV files for each section (metadata, data quality, metrics, dimensions)
- **JSON Output**: Hierarchical structured data with proper encoding and formatting
- **HTML Output**: Professional web-ready reports with embedded CSS and responsive design
- **Format Selection**: New `--format` CLI argument to choose output format (excel, csv, json, html, all)
- **Comprehensive Testing**: 20 new tests covering all output formats and edge cases

#### Performance Optimization

**Validation Result Caching (50-90% Performance Improvement on Cache Hits)**
- **ValidationCache Class**: Thread-safe LRU cache for validation results with configurable size and TTL
- **CLI Integration**: `--enable-cache`, `--cache-size`, and `--cache-ttl` flags for cache control
- **Cache Statistics**: Detailed performance metrics including hits, misses, hit rate, and time saved
- **Smart Cache Keys**: Content-based DataFrame hashing using `pandas.util.hash_pandas_object` combined with configuration hashing
- **LRU Eviction**: Automatic removal of least recently used entries when cache reaches maximum size
- **TTL Support**: Configurable time-to-live for cache entries (default: 1 hour = 3600 seconds)
- **Thread-Safe Design**: Lock-protected operations safe for concurrent validation with parallel execution
- **Zero Overhead**: No performance impact when cache is disabled (default behavior)

**Parallel Validation (10-15% Performance Improvement)**
- **Concurrent Validation**: Metrics and dimensions validation now run in parallel using ThreadPoolExecutor
- **Thread-Safe Design**: Lock-protected shared state for reliable concurrent operation
- **New Method**: `DataQualityChecker.check_all_parallel()` for parallel validation execution
- **Better CPU Utilization**: Better utilization of multi-core systems

**Optimized Single-Pass Validation (30-50% Performance Improvement)**
- **Single-Pass DataFrame Scanning**: Combined validation checks for 30-50% performance improvement
- **Vectorized Operations**: Replaced sequential scans with vectorized pandas operations
- **Reduced Memory Overhead**: 89% reduction in DataFrame scans (9 scans → 1 scan)
- **Better Scalability**: Improved performance for large data views (200+ components)

**Early Exit Optimization (1-2% Average, 15-20% Error Scenarios)**
- **DataFrame Pre-validation**: Validation exits immediately on critical errors
- **Fail-Fast Behavior**: Skips unnecessary checks when required fields are missing
- **Operation Reduction**: Prevents ~1600 unnecessary operations when required fields missing

**Logging Optimization (5-10% Performance Gain)**
- **Production Mode**: New `--production` CLI flag for minimal logging overhead
- **Environment Variable Support**: `LOG_LEVEL` environment variable for system-wide log level defaults
- **Conditional Logging**: Data quality issues logged selectively based on severity and log level
- **Summary Logging**: New `DataQualityChecker.log_summary()` method aggregates issues by severity
- **Log Entry Reduction**: 73-82% fewer log entries depending on dataset size

**Performance Tracking**
- **Built-in Metrics**: Built-in performance metrics and timing for validation operations
- **Operation Timing**: Individual operation timing (DEBUG level) and comprehensive summaries

#### Batch Processing
- **Parallel Multiprocessing**: Process multiple data views simultaneously with ProcessPoolExecutor
- **3-4x Throughput Improvement**: Parallel execution with configurable worker pools
- **Automatic Batch Mode**: Automatically enables parallel processing when multiple data views provided
- **Worker Configuration**: `--workers` flag to control parallelism (default: 4)
- **Continue on Error**: `--continue-on-error` flag to process all data views despite failures
- **Batch Summary Reports**: Detailed success/failure statistics and throughput metrics
- **Separate Logging**: Dedicated batch mode logs with comprehensive tracking

#### Testing Infrastructure
- **Comprehensive Test Suite**: 121 automated tests with 100% pass rate
- **Test Categories**:
  - CLI tests (10 tests)
  - Data quality tests (10 tests)
  - Optimized validation tests (16 tests)
  - Output format tests (20 tests)
  - Utility tests (14 tests)
  - Early exit tests (11 tests)
  - Logging optimization tests (15 tests)
  - Parallel validation tests (8 tests)
  - Validation caching tests (15 tests)
  - Output format tests (2 tests)
- **Performance Benchmarks**: Automated performance comparison tests
- **Thread Safety Tests**: Comprehensive concurrent execution validation
- **Edge Case Coverage**: Tests for Unicode, special characters, empty datasets, and large datasets
- **Test Fixtures**: Reusable mock configurations and sample data
- **pytest Integration**: Full pytest support with proper configuration

#### Documentation
- **CHANGELOG.md**: This comprehensive changelog (NEW)
- **OUTPUT_FORMATS.md**: Complete guide to all output formats with examples
- **BATCH_PROCESSING_GUIDE.md**: Detailed batch processing documentation
- **OPTIMIZATION_SUMMARY.md**: Performance optimization implementation details
- **tests/README.md**: Test suite documentation and usage guide
- **Improved README.md**: Updated with all new features and examples

### Changed

#### Dependency Management
- **Version Update**: Updated from 0.1.0 to 3.0.0
- **Modern Package Management**: Uses `uv` for fast, reliable dependency management
- **pyproject.toml**: Standardized project configuration
- **Python 3.14+ Required**: Updated to require latest Python version
- **Lock Files**: Reproducible builds with `uv.lock`
- **Optional Dev Dependencies**: pytest and testing tools as optional dev dependencies

#### Code Quality
- **Removed Unused Imports**: Removed unused `pytz` import
- **Better Error Handling**: Pre-flight validation and graceful error handling
- **Enhanced Logging**: Timestamped logs with rotation and detailed tracking
- **Improved Reliability**: Validates data view existence before processing
- **Safe Filename Generation**: Handles special characters and edge cases

#### Documentation Formatting
- **Markdown Standards Compliance**: All documentation follows MD031 and MD032 standards
- **Consistent Formatting**: Uniform style across all markdown files
- **Removed Checkmark Emojis**: Replaced with standard bullet points for better compatibility
- **Proper Spacing**: Blank lines around code blocks, lists, and headings
- **Professional Presentation**: Clean, readable documentation throughout

### Fixed

- **Version Mismatch**: Corrected version number from 0.1.0 to 3.0.0 in pyproject.toml
- **Missing Test Dependency**: Added pytest as optional dev dependency
- **Markdown Linting Warnings**: Fixed 100+ markdown formatting issues across all documentation
- **Import Errors**: Removed unused pytz dependency that was never actually used
- **Documentation Consistency**: Updated all examples to match actual implementation

### Performance

**Cumulative Performance Improvements:**
- **Validation Caching**: 50-90% faster on cache hits (70% average), 1-2% overhead on misses
- **Parallel Validation**: 10-15% faster data quality validation through concurrent processing
- **Single-Pass Validation**: 30-50% faster through vectorized operations (89% reduction in DataFrame scans)
- **Early Exit Optimization**: 15-20% faster on error scenarios, 1-2% average improvement
- **Logging Optimization**: 5-10% faster with production mode, 73-82% fewer log entries
- **Batch Processing**: 3-4x throughput improvement with parallel multiprocessing
- **Better CPU Utilization**: No GIL limitations with ProcessPoolExecutor
- **Reduced Memory Allocations**: Optimized memory access patterns

**Real-World Impact:**
```
Small Data View (50 components):
  Before: 0.5s validation
  After:  0.25s validation (50% faster)
  With cache hit: 0.05s (90% faster)

Medium Data View (150 components):
  Before: 1.8s validation
  After:  0.9s validation (50% faster)
  With cache hit: 0.09s (95% faster)

Large Data View (225+ components):
  Before: 2.5s validation
  After:  1.2s validation (52% faster)
  With cache hit: 0.12s (95% faster)

Batch Processing (10 data views):
  Sequential (old): 350s
  Parallel (4 workers): 87s (4x faster)
  With cache (70% hit rate): 30s (11x faster)
```

### Backward Compatibility

- **100% Backward Compatible**: All existing validation methods preserved
- **No Breaking Changes**: Existing scripts continue to work without modifications
- **Default Behavior Unchanged**: Excel output remains the default format
- **API Compatibility**: Same issue structure and format as previous versions
- **Dual Validation Options**: Both original and optimized validation available

### Testing

- **121 Tests Total**: Complete test coverage across all components
  - 10 CLI tests
  - 10 Data quality tests
  - 16 Optimized validation tests
  - 20 Output format tests
  - 14 Utility tests
  - 11 Early exit tests
  - 15 Logging optimization tests
  - 8 Parallel validation tests
  - 15 Validation caching tests
  - 2 Additional output format tests
- **100% Pass Rate**: All tests passing
- **Performance Validated**: All optimization improvements verified through automated benchmarks
- **Thread Safety Verified**: Concurrent execution tested under load
- **Fast Execution**: Complete suite runs in < 1 second
- **CI/CD Ready**: GitHub Actions examples provided

### Documentation

- **5 Major Documentation Files**: README, OUTPUT_FORMATS, BATCH_PROCESSING_GUIDE, OPTIMIZATION_SUMMARY, CHANGELOG
- **132+ Formatting Improvements**: Professional, consistent documentation
- **Code Examples**: Comprehensive examples for all features
- **Troubleshooting Guides**: Detailed error resolution steps
- **Use Case Recommendations**: Clear guidance on when to use each feature

---

## [0.1.0] - 2025 (Previous Version)

### Initial Features

- Basic Excel output generation
- CJA API integration using cjapy
- Data view metadata extraction
- Metrics and dimensions export
- Basic data quality validation
- Single data view processing
- Command-line interface
- Jupyter notebook origin

---

## Version Comparison

| Feature | v0.1.0 | v3.0.0 |
|---------|--------|--------|
| Output Formats | Excel only | Excel, CSV, JSON, HTML, All |
| Batch Processing | No | Yes (3-4x faster) |
| Data Quality Validation | Sequential | Optimized (30-50% faster) + Parallel (10-15% faster) |
| Validation Caching | No | Yes (50-90% faster on cache hits) |
| Early Exit Optimization | No | Yes (15-20% faster on errors) |
| Logging Optimization | No | Yes (5-10% faster with --production) |
| Tests | None | 929 comprehensive tests |
| Documentation | Basic | 13 detailed guides |
| Performance Tracking | No | Yes, built-in with cache statistics |
| Parallel Processing | No | Yes, configurable workers + concurrent validation |
| Error Handling | Basic | Comprehensive |
| Thread Safety | N/A | Yes, lock-protected concurrent operations |
| Python Version | 3.x | 3.14+ |
| Package Manager | pip | uv |

---

## Migration Guide from v0.1.0 to v3.0.0

### Breaking Changes
**None** - Version 3.0.0 is fully backward compatible.

### Recommended Updates

1. **Update Python version**:
   ```bash
   # Ensure Python 3.14+ is installed
   python3 --version  # Should be 3.14 or higher
   ```

2. **Install uv**:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. **Sync dependencies**:
   ```bash
   uv sync
   ```

4. **Update scripts** (optional but recommended):
   ```bash
   # Recommended (v3.0.8+): Console script
   cja_auto_sdr dv_12345

   # Alternative: Using uv run
   uv run cja_auto_sdr dv_12345

   # Legacy (still works)
   python cja_sdr_generator.py dv_12345
   ```

5. **Explore new features**:
   - Try different output formats: `--format csv`, `--format json`, `--format html`
   - Use batch processing: `cja_auto_sdr dv_1 dv_2 dv_3`
   - Review new documentation guides

---

## Links

- **Repository**: https://github.com/brian-a-au/cja_auto_sdr
- **Issues**: https://github.com/brian-a-au/cja_auto_sdr/issues
- **Original Notebook**: https://github.com/pitchmuc/CJA_Summit_2025

---

## Acknowledgments

Built on the foundation of the [CJA Summit 2025 notebook](https://github.com/pitchmuc/CJA_Summit_2025/blob/main/notebooks/06.%20CJA%20Data%20View%20Solution%20Design%20Reference%20Generator.ipynb) by pitchmuc.

Version 3.0.0 represents a comprehensive evolution from proof-of-concept to production-ready enterprise solution.
