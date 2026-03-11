# v3.4.0 Implementation Plan

Local implementation checklist for v3.4.0: org-report temporal trending + generator.py decomposition.

## Status snapshot

Implemented on the current PR branch:

- Persistent org-report snapshot history keyed by org, including console/default workflows.
- `TrendingSnapshot` / `TrendingDelta` / `OrgReportTrending` data model and backwards-compatible comparison bridge.
- Drift scoring implementation with normalized weighted scoring and regression coverage.
- `--trending-window` parser + runtime validation + org-report dispatch wiring.
- Trending-aware org-report output in console, JSON, Excel, Markdown, HTML, and CSV.
- `org/writers/` extraction and `output/sdr/` extraction with generator lazy forwarding preserved.
- Profile management extraction to `core/profiles.py` with generator forwarding preserved for existing imports/tests.
- Interactive CLI extraction to `cli/interactive.py` with generator forwarding preserved for existing imports/tests.
- Config/status/sample-config extraction to `cli/commands/config.py` with generator-compatible patch/import behavior preserved.
- Stats and name-resolution extraction to `cli/commands/stats.py` with generator-compatible patch/import behavior preserved.
- Diff/snapshot handler extraction to `diff/commands.py` with generator-level compatibility wrappers preserved.
- Snapshot/diff CLI dispatch extraction to `diff/cli.py` for snapshot listing/pruning, compare-snapshots, snapshot, compare-with-prev, and diff-snapshot orchestration.
- Cross-data-view `--diff` CLI dispatch extraction to `diff/cli.py` with generator-compatible forwarding preserved.
- Quality-report, batch, and single-data-view SDR execution extraction to `cli/execution.py` with generator-compatible forwarding preserved.
- Inventory-order resolution plus `--inventory-summary` validation/dispatch extraction to `cli/execution.py` with generator-compatible forwarding preserved.
- Remaining SDR preflight/setup orchestration extraction to `cli/execution.py`, including large-batch confirmation, dry-run dispatch, output/format validation, API tuning/circuit-breaker setup, and inventory-summary preflight dispatch, with generator-compatible forwarding preserved.
- Pipeline models and batch orchestration activation:
  - `ProcessingResult`, `WorkerArgs`, `ProcessingConfig`, and `BatchConfig` now live in `pipeline/models.py`
  - `process_single_dataview_worker()` now lives in `pipeline/workers.py`
  - `BatchProcessor` now lives in `pipeline/batch.py`
  - `pipeline/single.py` and `pipeline/dry_run.py` now provide real wrapper modules so the `pipeline` package imports resolve without generator-owned lazy stubs
- `_main_impl()` reduced further by moving config/status, interactive, stats, and org-report branch orchestration into `_dispatch_post_validation_report_modes()`.
- Follow-up PR maintenance commits landed for continued decomposition and CI stabilization:
  - `6e78359` Continue generator decomposition for v3.4.0
  - `06e0c04` Fix generator formatting check
  - `b3ba3d9` Continue generator decomposition for CLI command handlers
  - `9b7f302` Extract snapshot and diff CLI dispatch
  - `838653b` Extract SDR execution preflight orchestration
  - `823f04e` Sync documented test counts
  - `c4fbdb0` Update plan status for latest CI state
- v3.4.0 version/doc updates already landed in repo docs and changelog.
- Earlier local validation was green on pushed commit (`9b7f302`) during the diff/snapshot extraction:
  - `ruff check` on the touched files
  - targeted snapshot/diff CLI dispatch pytest slice:
    `tests/test_cli_command_handlers.py`, `tests/test_snapshot_commands.py`,
    `tests/test_generator_remaining_coverage.py`
- Current working tree validation is green for the ongoing diff CLI extraction:
  - `uv run ruff check src/cja_auto_sdr/diff/cli.py src/cja_auto_sdr/generator.py tests/test_main_impl_cli_coverage.py tests/test_ux_features.py`
  - `PYTHONPATH=src uv run pytest -q tests/test_main_impl_cli_coverage.py tests/test_ux_features.py tests/test_cli_smoke_modes.py -q`
- Current working tree validation is also green for the SDR execution extraction:
  - `uv run ruff check src/cja_auto_sdr/cli/execution.py src/cja_auto_sdr/diff/cli.py src/cja_auto_sdr/generator.py tests/test_main_impl_cli_coverage.py tests/test_ux_features.py tests/test_cli_smoke_modes.py tests/test_generator_remaining_coverage.py tests/test_quality_policy_and_run_summary.py`
  - `PYTHONPATH=src uv run pytest -q tests/test_main_impl_cli_coverage.py tests/test_ux_features.py tests/test_cli_smoke_modes.py tests/test_generator_remaining_coverage.py tests/test_quality_policy_and_run_summary.py -q`
- Current working tree validation remains green after the inventory-summary extraction:
  - `uv run ruff check src/cja_auto_sdr/cli/execution.py src/cja_auto_sdr/diff/cli.py src/cja_auto_sdr/generator.py tests/test_main_impl_cli_coverage.py tests/test_ux_features.py tests/test_cli_smoke_modes.py tests/test_generator_remaining_coverage.py tests/test_quality_policy_and_run_summary.py tests/test_cli.py`
  - `PYTHONPATH=src uv run pytest -q tests/test_main_impl_cli_coverage.py tests/test_ux_features.py tests/test_cli_smoke_modes.py tests/test_generator_remaining_coverage.py tests/test_quality_policy_and_run_summary.py tests/test_cli.py -q`
- Current working tree validation is green after the SDR preflight/setup extraction:
  - `uv run ruff check src/cja_auto_sdr/cli/execution.py src/cja_auto_sdr/generator.py tests/test_cli_execution.py tests/test_main_impl_cli_coverage.py tests/test_cli.py tests/test_quality_policy_and_run_summary.py`
  - `uv run ruff format --check src/cja_auto_sdr/cli/execution.py src/cja_auto_sdr/generator.py tests/test_cli_execution.py`
  - `PYTHONPATH=src uv run pytest -q tests/test_cli_execution.py tests/test_main_impl_cli_coverage.py tests/test_cli.py tests/test_quality_policy_and_run_summary.py`
  - `PYTHONPATH=src uv run pytest tests/ -q`
- Current working tree validation is green after the pipeline batch/models extraction:
  - `uv run ruff check src/cja_auto_sdr/pipeline/models.py src/cja_auto_sdr/pipeline/workers.py src/cja_auto_sdr/pipeline/batch.py src/cja_auto_sdr/pipeline/single.py src/cja_auto_sdr/pipeline/dry_run.py src/cja_auto_sdr/generator.py`
  - `uv run ruff format --check src/cja_auto_sdr/pipeline/models.py src/cja_auto_sdr/pipeline/workers.py src/cja_auto_sdr/pipeline/batch.py src/cja_auto_sdr/pipeline/single.py src/cja_auto_sdr/pipeline/dry_run.py src/cja_auto_sdr/generator.py`
  - `PYTHONPATH=src uv run pytest -q tests/test_batch_processor.py tests/test_process_single_dataview.py tests/test_discovery_formatters.py tests/test_lazy_forwarding.py tests/test_main_impl_coverage.py tests/test_generator_remaining_coverage.py`
  - `PYTHONPATH=src uv run pytest -q tests/test_cli.py tests/test_main_impl_cli_coverage.py tests/test_cli_execution.py tests/test_quality_policy_and_run_summary.py tests/test_cli_smoke_modes.py tests/test_ux_features.py`
  - `PYTHONPATH=src uv run pytest tests/ -q`
- Full local CI-equivalent validation is green on the current working tree:
  - `uv run ruff check src/ tests/ scripts/check_version_sync.py scripts/update_test_counts.py`
  - `uv run ruff format --check src/ tests/ scripts/check_version_sync.py scripts/update_test_counts.py`
  - `uv run python scripts/check_version_sync.py`
  - `uv run python scripts/update_test_counts.py --check`
  - `uv run pytest tests/ -v --tb=short --cov=cja_auto_sdr --cov-report=term --cov-fail-under=95`
  - `uv build`
  - clean-wheel install verification for `dist/cja_auto_sdr-3.4.0-py3-none-any.whl`
  - CLI smoke commands: `python -m cja_auto_sdr --version`, `--exit-codes`, `--help`
- Remote PR checks are green on the latest pushed commit (`c4fbdb0`), after the follow-up `test-counts` repair on `823f04e` and the subsequent plan sync commit.

Still open or only partially covered:

- Broader `generator.py` decomposition beyond the writer/list/quality-policy/profile/interactive/config/stats/diff-handler extractions already landed on this branch.
- `generator.py` is still ~9.9k LOC after the current extractions, so the decomposition goal is only partially complete.
- Most of the remaining bulk is still concentrated in:
  - single-data-view processing (`process_single_dataview()`)
  - dry-run orchestration (`run_dry_run()`)
  - compatibility wrappers still living in `generator.py`

## Endgame for the open PR

Current position:

- Local CI-equivalent validation is green on the latest pushed commit (`7384003`).
- The org-report trending history review findings have been addressed with centralized snapshot history policy and regression coverage.
- The main remaining risk is widening scope again before merge, not an identified defect in the current trending patch set.

What to do on this PR before merge:

- Keep scope frozen to merge-hardening work only. Do not continue broad `generator.py` decomposition here unless a real regression or CI failure requires it.
- Add a small operator-facing note in docs or release notes that early v3.4.0 org-report trending caches may need manual pruning if they were generated before the snapshot history hardening landed.
- Add the last defensive tests around snapshot history compatibility:
  - `_snapshot_meta.history_eligible` / `history_exclusion_reason` override precedence
  - string-typed legacy boolean/fidelity values in serialized snapshots
  - round-trip persistence/list/inspect coverage for `history_eligible` and `history_exclusion_reason`
  - one compatibility fixture for older persisted snapshot payloads without the newer fidelity fields
- Let GitHub CI on the open PR be the final gate and respond only to concrete failures in lint, full tests/coverage, smoke tests, build/install, or test-count/version-sync workflows.

What not to do on this PR:

- Do not resume large structural extraction work in `generator.py`, `pipeline/`, or CLI dispatch just because that decomposition remains incomplete.
- Do not expand drift scoring semantics or component-level drift explanations in this branch.
- Do not add automatic migration or cleanup heuristics for already-persisted pre-hardening caches unless a safe discriminator is identified first.

Merge gate for this PR:

- GitHub workflows are green on the latest pushed ref.
- No new review findings appear against the final patch set.
- The branch remains limited to trending hardening, compatibility, and merge-readiness changes.

## Pending / open to do

- [x] Extract config/status/sample-config helpers from `generator.py`:
  - [x] `generate_sample_config()`
  - [x] `show_config_status()`
  - [x] `validate_config_only()`
- [x] Extract stats/name-resolution helpers from `generator.py`:
  - [x] `resolve_data_view_names()`
  - [x] `show_stats()`
  - [x] tightly-coupled stats/name-resolution helpers needed to preserve behavior
- [x] Extract diff/snapshot command handlers from `generator.py`:
  - [x] `handle_snapshot_command()`
  - [x] `handle_diff_command()`
  - [x] `handle_diff_snapshot_command()`
  - [x] `handle_compare_snapshots_command()`
- [x] Reduce `_main_impl()` by pushing branch-specific command orchestration into smaller dispatch helpers/modules.
  - [x] Move config/status, interactive, stats, and org-report branching into `_dispatch_post_validation_report_modes()`
  - [x] Extract snapshot list/prune, compare-snapshots, snapshot, compare-with-prev, and diff-snapshot orchestration out of `_main_impl()` into `diff/cli.py`
  - [x] Extract cross-data-view `--diff` orchestration out of `_main_impl()` into `diff/cli.py`
  - [x] Extract remaining SDR-mode orchestration out of `_main_impl()`
  - [x] Extract quality-report, batch, and single-data-view execution branches to `cli/execution.py`
  - [x] Extract inventory-order resolution plus `--inventory-summary` validation/dispatch to `cli/execution.py`
  - [x] Extract remaining SDR preflight validation and setup orchestration out of `_main_impl()`
- [x] After the next extraction slice, rerun a broader local validation pass (`ruff`, format check, targeted pytest slices, then full pytest if changes touch shared dispatch paths).
- [x] Run/monitor remote PR CI on the latest pushed refactor commit and fix any failures if branch-only issues appear.
- [ ] Continue decomposing single-data-view processing and dry-run orchestration out of `generator.py` while preserving generator-level import/test compatibility.
- [ ] Reduce remaining `generator.py` compatibility wrappers where safe, without breaking the v3.4.0 public surface.

Should add to the backlog:

- Consider upgrading drift scoring from current first/last window-edge comparison to richer first/last appearance or full-window scoring if explanations need to become more precise.
- Consider expanding drift explanations beyond score + data-view-name ranking into component-level narratives if output precision needs to improve further.

## Immediate remediation scope

These items are in scope now based on review feedback against the current implementation.

- [x] Change org-report trending history to read/write a persistent snapshot cache, not `output_dir`.
- [x] Persist the current org-report snapshot even when the selected output format is `console`.
- [x] Align trending snapshot extraction with the actual `build_org_report_json_data()` schema:
  - [x] Use `summary.data_views_total` instead of legacy `total_data_views`.
  - [x] Use per-data-view `metrics_count` / `dimensions_count`.
  - [x] Use distribution `metrics` / `dimensions` lists instead of legacy `core_metrics` / `core_dimensions`.
  - [x] Derive per-data-view core ratios from emitted JSON structures that actually exist.
- [x] Carry `org_id` through `TrendingSnapshot` and filter discovered snapshots to the active org before building the window.
- [x] Preserve data-view added/removed names when bridging `OrgReportTrending` to `OrgReportComparison`, so console comparison output remains populated.
- [x] Add regression coverage for:
  - [x] Default console workflow accumulating trending history across runs.
  - [x] Snapshot extraction from real org-report JSON payloads.
  - [x] Mixed-org snapshot directories/caches.
  - [x] Comparison console output from `OrgReportTrending.to_comparison()`.
  - [x] `--trending-window` validation in org-report vs non-org-report CLI flows.
  - [x] `--org-report` output remaining unchanged when `--trending-window` is omitted.

## Follow-up beyond this patch

These are worth addressing next, but they are not required to resolve the current review findings.

- [x] Add retention/pruning for persisted org-report trending snapshots so history does not grow without bounds.
- [x] Add a dedicated listing/inspection/pruning command set for org-report trending snapshots, separate from diff snapshots.
- [x] Decide whether trending should persist richer per-data-view metadata (names, component IDs, or both) for better drift explanations in output formats.
  - [x] Use persisted/recovered data-view names in drift renderers across console, JSON, Excel, Markdown, HTML, and CSV.
  - [x] Defer component-ID-level drift explanation expansion beyond score/name ranking to a later patch.
- [x] Tighten snapshot deduplication/persistence beyond timestamp-only matching:
  - [x] Avoid same-timestamp filename collisions when persisting org-report snapshots.
  - [x] Stop collapsing distinct cached snapshots solely because `(org_id, timestamp)` matches.
  - [x] Use persisted snapshot IDs plus content hashing as the stronger snapshot identity.
- [x] Normalize snapshot ordering to parsed UTC datetimes before trimming/building the trending window.
- [x] Fix Excel trending column formatting for windows larger than 25 snapshots (`AA`, `AB`, etc. instead of ASCII arithmetic).
- [x] Add targeted regression coverage for:
  - [x] Same-timestamp snapshot persistence and discovery.
  - [x] Mixed ISO timestamp/timezone-offset ordering.
  - [x] Excel trending windows larger than 25 snapshots.
- [x] Extract profile management helpers/import flow to `core/profiles.py` while preserving generator-level patch/import compatibility.
- [x] Extract interactive CLI selection/wizard flows to `cli/interactive.py` while preserving generator-level patch/import compatibility.
- [x] Fix the PR Ruff format failure after the latest decomposition commits and restore green CI.
- [ ] Revisit the broader generator.py extraction beyond the writer/list/quality-policy/profile/interactive/config/stats/diff-handler splits.

## Scope

- Add count-based windowed trending over cached org-report snapshots.
- Render trending output in all 6 formats (console, Excel, JSON, Markdown, HTML, CSV).
- Compute per-data-view drift scores across the trending window.
- Extract ~3,200 LOC from generator.py into subpackages via lazy forwarding.
- Preserve full backwards compatibility.

## Constraints

- Minor release: no breaking changes to CLI, output contracts, or public API surface.
- Trending is additive — org reports without `--trending-window` are unchanged.
- Structural extractions use lazy forwarding re-exports from generator.py.
- Extraction #4 (SDR output writers) defers to v3.4.1 if diff.models coupling is too deep.

## Phase 1: Structural Extractions

### Commit 1: Extract data quality policy helpers

- [x] Move `load_quality_policy()`, `apply_quality_policy_defaults()`, `normalize_quality_severity()`, and related helpers (~180 LOC) to `api/quality/policy.py`.
- [x] Add lazy forwarding re-exports in `generator.py`.
- [x] Verify all existing tests pass without modification.

Acceptance:
- All imports from `generator.py` continue to resolve.
- No behavioral change.

### Commit 2: Extract discovery/list commands

- [x] Move `_run_list_command()` and all 7 `list_*` commands + helpers (~500 LOC) to `cli/commands/list.py`.
  - [x] Move `_run_list_command()` and the public `list_*` / `describe_dataview()` entrypoints to `cli/commands/list.py`.
  - [x] Move the lower-level discovery/list helper functions into `cli/commands/list.py` so the extracted module owns the discovery execution path.
- [x] Add lazy forwarding re-exports in `generator.py`.
- [x] Verify all existing tests pass without modification.

Acceptance:
- All discovery commands work identically.
- All imports from `generator.py` continue to resolve.

### Commit 3: Extract org report writers

- [x] Create `org/writers/` subpackage.
- [x] Move `write_org_report_console`, `write_org_report_json`, `write_org_report_excel`, `write_org_report_markdown`, `write_org_report_html`, `write_org_report_csv`, `write_org_report_stats_only`, `write_org_report_comparison_console`, and all supporting helpers (~1,600 LOC) to `org/writers/`.
- [x] Add lazy forwarding re-exports in `generator.py`.
- [x] Verify all existing tests pass without modification.

Acceptance:
- All org report output formats render identically.
- All imports from `generator.py` continue to resolve.

### Commit 4: Extract SDR output writers

- [x] Audit `diff.models` dependency in SDR output writers.
- [x] Move `apply_excel_formatting()`, `write_html_output()`, `write_markdown_output()`, and related helpers (~900 LOC) to `output/sdr/`.
- [x] Add lazy forwarding re-exports in `generator.py`.
- [x] Verify all existing tests pass without modification.

Acceptance:
- All SDR output formats render identically (or commit is cleanly deferred).
- All imports from `generator.py` continue to resolve.

## Phase 2: Trending Data Model

### Commit 5: Add TrendingSnapshot and TrendingDelta dataclasses

- [x] Add `TrendingSnapshot` dataclass to `org/models.py`: timestamp, dv_count, component_count, core_count, isolated_count, high_sim_pair_count.
- [x] Add `TrendingDelta` dataclass to `org/models.py`: same fields as delta values between consecutive snapshots.
- [x] Add `OrgReportTrending` dataclass to `org/models.py`: snapshots list, deltas list, drift_scores dict, window_size int.
- [x] Add method on `OrgReportTrending` to produce an `OrgReportComparison` for the most recent pair (backwards compatibility bridge).

Tests:
- [x] Construction from 0, 1, 2, N snapshots.
- [x] Delta computation accuracy between consecutive snapshots.
- [x] `OrgReportComparison` bridge produces correct output.
- [x] Edge case: identical snapshots produce zero deltas.

### Commit 6: Implement snapshot cache discovery

- [x] Add function to walk a persistent org-report snapshot cache directory, load JSONs, sort by timestamp, trim to window size.
- [x] Scope discovered snapshots to the active `org_id`.
- [x] Handle fewer snapshots than window (truncate, emit note).
- [x] Handle corrupt/malformed JSON (skip with warning).
- [x] Support folding an explicit `--compare-org-report` file into the snapshot list.
- [x] Persist the current run into the snapshot cache even when the main output format is not JSON.

Tests:
- [x] Mock cache directory with N JSON files: correct loading and ordering.
- [x] Mixed-org cache directory: only active-org snapshots are included.
- [x] Fewer snapshots than window: graceful truncation.
- [x] Corrupt JSON: skipped with warning, no crash.
- [x] Explicit comparison file folded into window correctly.
- [x] Empty cache directory: trending skipped with note.

### Commit 7: Implement drift scoring

- [x] Compute per-DV absolute change dimensions across the window using first/last snapshot values plus presence-change handling for adds/removals.
- [x] Normalize each delta dimension to 0-1 across all DVs in the window.
- [x] Weighted average: component count change (0.4), core/isolated shift (0.2), similarity shift (0.2), presence change (0.2).
- [x] DVs added mid-window score high. Unchanged DVs score 0.0.

Tests:
- [x] All-static window: all scores 0.0.
- [x] Single DV added mid-window: high score.
- [x] Known delta inputs: exact expected scores (deterministic).
- [x] Single-snapshot window: trending skipped.

## Phase 3: CLI Integration

### Commit 8: Add --trending-window flag

- [x] Add `--trending-window` argument to org report argument group in `cli/parser.py`.
- [x] Default value: 10. Type: int. Minimum: 2.
- [x] Validation: error if used without `--org-report`.
- [x] Wire into org-report dispatch in main: when present, run cache discovery + trending computation after org report generation.
- [x] Pass `OrgReportTrending` (or `None`) to org report writers.

Tests:
- [x] `--trending-window` without `--org-report`: error.
- [x] `--trending-window 0`: validation error.
- [x] `--trending-window 1`: validation error.
- [x] `--trending-window` with no value: uses default 10.
- [x] Coexistence with `--compare-org-report`.

## Phase 4: Output Writers

### Commit 9: Console trending output

- [x] Extend `write_org_report_console` (now in `org/writers/`) with optional `trending` parameter.
- [x] Render multi-period table with snapshot columns and metric rows.
- [x] Render "Top Drift" ranked list below the table.
- [x] `trending=None`: no change to existing output.

Tests:
- [x] Trending table renders with correct columns and values.
- [x] Drift scores listed in descending order.
- [x] `trending=None`: output unchanged (regression).

### Commit 10: JSON trending output

- [x] Extend `write_org_report_json` with optional `trending` parameter.
- [x] Add `"trending"` top-level key with `snapshots`, `deltas`, `drift_scores`.
- [x] Existing keys untouched.

Tests:
- [x] `trending` key present with correct schema.
- [x] Existing JSON structure unchanged.
- [x] `trending=None`: no `trending` key in output.

### Commit 11: Excel trending output

- [x] Extend `write_org_report_excel` with optional `trending` parameter.
- [x] Add "Trending" worksheet with snapshot columns and metric rows.
- [x] Add conditional formatting on delta cells or otherwise decide the intended Excel presentation.
- [x] Add drift scores table on the same sheet.
- [x] Follow-up: support worksheet formatting correctly when trending windows exceed 25 snapshots.

Tests:
- [x] "Trending" worksheet present with correct columns.
- [x] Conditional formatting applied to delta cells.
- [x] Drift scores table content asserted more directly.
- [x] `trending=None`: no "Trending" worksheet.
- [x] Add regression coverage for >25 snapshot windows to prevent invalid Excel column references.

### Commit 12: Markdown and HTML trending output

- [x] Extend `write_org_report_markdown` with optional `trending` parameter.
- [x] Extend `write_org_report_html` with optional `trending` parameter.
- [x] Trending summary table + drift scores ranked list in both formats.

Tests:
- [x] Markdown: trending table renders with correct formatting.
- [x] HTML: trending section present with correct structure.
- [x] Both: `trending=None` produces unchanged output.

### Commit 13: CSV trending output

- [x] Extend `write_org_report_csv` with optional `trending` parameter.
- [x] Flat rows: `snapshot_timestamp, metric_name, value`.
- [x] Drift scores emitted as separate CSV output alongside trending rows.

Tests:
- [x] CSV row content/schema asserted more directly.
- [x] Drift scores section present.
- [x] `trending=None`: output unchanged.

## Phase 5: Backwards Compatibility & Integration

### Commit 14: Backwards compatibility and integration tests

- [x] Verify `OrgReportComparison` producible from `OrgReportTrending`.
- [x] Verify `write_org_report_comparison_console` retains added/removed data view names when fed by `OrgReportTrending`.
- [x] Verify existing org-report JSON schema untouched when trending inactive.
- [x] End-to-end test: `--org-report --trending-window 5` with persistent snapshot cache produces correct output across all formats.
- [x] End-to-end test: default console output still accumulates trending history across repeated runs.
- [x] End-to-end test: `--org-report` without `--trending-window` is completely unchanged.
- [x] Add edge-case coverage for normalized timestamp ordering across mixed ISO/timezone forms.
- [x] Add edge-case coverage for same-timestamp cached snapshot persistence/discovery behavior.

## Phase 6: Release Prep

### Commit 15: Version bump and documentation

- [x] Bump version to 3.4.0 in the tracked repo locations (`version.py`, UX/content-validation tests, `CLAUDE.md`, `docs/QUICK_REFERENCE.md`, `docs/QUICKSTART_GUIDE.md`).
- [x] Update CHANGELOG.md with v3.4.0 entry.
- [x] Update docs/CLI_REFERENCE.md with `--trending-window` flag.
- [x] Update docs/QUICK_REFERENCE.md with trending recipes.
- [x] Update docs/ORG_WIDE_ANALYSIS.md with trending workflow.
- [x] Update test counts in README.md and tests/README.md.

### Validation pass before tagging

Note:
- A broad local CI-equivalent pass has already succeeded on this PR branch (`ruff`, format check, full pytest with coverage, build/install verification), but the final release-tag pass should still be rerun after the remaining open items are closed.
- The open PR CI is also green again after the March 9, 2026 formatting follow-up commit.

- [x] `uv run ruff check src/ tests/`
- [x] `uv run ruff format --check src/ tests/`
- [x] `uv run pytest tests/ --collect-only -q` (5648 collected)
- [x] `uv run pytest tests/ -x -q` (5647 passed, 1 skipped)
- [x] `uv run pytest --cov=src/cja_auto_sdr --cov-report=term -q` (96% total coverage)
- [x] Targeted trending contract tests
- [x] Targeted org-report backwards compatibility tests
- [x] Targeted profile extraction compatibility tests
- [x] Targeted interactive CLI extraction compatibility tests
- [x] Confirm docs and changelog match actual implementation
