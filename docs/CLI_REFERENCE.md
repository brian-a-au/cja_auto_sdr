# CLI Reference

Complete command-line interface documentation for the CJA SDR Generator.

## Table of Contents

- [Basic Syntax](#basic-syntax)
  - [Alternative Invocations](#alternative-invocations)
- [Arguments](#arguments)
  - [Required](#required)
- [Options](#options)
  - [General](#general)
  - [Processing](#processing)
  - [Output](#output)
  - [Configuration](#configuration)
  - [Profile Management](#profile-management)
  - [Validation & Testing](#validation--testing)
  - [Discovery Inspection](#discovery-inspection)
  - [Caching](#caching)
  - [Retry Configuration](#retry-configuration)
  - [Diff Comparison](#diff-comparison)
  - [Org-Wide Analysis](#org-wide-analysis)
  - [Git Integration](#git-integration)
  - [Reliability & Auto-Tuning](#reliability--auto-tuning)
  - [Inventory Options](#inventory-options)
  - [Environment Variables](#environment-variables)
- [Usage Examples](#usage-examples)
  - [Single Data View](#single-data-view)
  - [Multiple Data Views](#multiple-data-views)
  - [Discovery Commands](#discovery-commands)
  - [Discovery Inspection Commands](#discovery-inspection-commands)
  - [Quick Statistics](#quick-statistics)
  - [Interactive Data View Selection](#interactive-data-view-selection)
  - [Auto-Open Generated Files](#auto-open-generated-files)
  - [Performance Optimization](#performance-optimization)
  - [Output Formats](#output-formats)
  - [Production Examples](#production-examples)
  - [Data View Comparison (Diff)](#data-view-comparison-diff)
  - [Org-Wide Analysis Examples](#org-wide-analysis-1)
  - [Git Integration Examples](#git-integration)
  - [Inventory Options Examples](#inventory-options-1)
- [Output Files](#output-files)
  - [Excel Workbook](#excel-workbook)
  - [Log Files](#log-files)
- [Expected Output](#expected-output)
  - [Single Data View](#single-data-view-1)
  - [Batch Mode](#batch-mode)
- [Exit Codes](#exit-codes)
- [Shell Tab-Completion](#shell-tab-completion)
  - [Installation](#installation)
  - [Activation](#activation)
  - [Usage](#usage)
- [See Also](#see-also)

---

## Basic Syntax

```bash
cja_auto_sdr [OPTIONS] DATA_VIEW_ID_OR_NAME [DATA_VIEW_ID_OR_NAME ...]
```

> **Running commands:** You have three equivalent options:
> - `uv run cja_auto_sdr ...` — works immediately on macOS/Linux, may have issues on Windows
> - `cja_auto_sdr ...` — after activating the venv: `source .venv/bin/activate` (Unix) or `.venv\Scripts\activate` (Windows)
> - `cja_auto_sdr ...` — run the script directly (most reliable on Windows)
>
> This guide uses `uv run cja_auto_sdr` for macOS/Linux examples. **Windows users** should omit the `uv run` prefix and use `cja_auto_sdr` directly after activating the virtual environment.

### Alternative Invocations

```bash
# Hyphenated version (identical functionality)
cja-auto-sdr [OPTIONS] DATA_VIEW_ID_OR_NAME [...]
```

## Arguments

### Required

| Argument | Description |
|----------|-------------|
| `DATA_VIEW_ID_OR_NAME` | One or more data view IDs (e.g., `dv_12345`) or exact names (e.g., `"Production Analytics"`). If a name matches multiple data views, all will be processed. Use quotes for names with spaces. |

## Options

### General

| Option | Description | Default |
|--------|-------------|---------|
| `-h, --help` | Show help message and exit | - |
| `-V, --version` | Show program version and exit | - |
| `--exit-codes` | Display exit code reference and exit | - |
| `-q, --quiet` | Suppress output except errors | False |
| `--open` | Open generated file(s) in default application after creation | False |
| `--show-timings` | Display performance timing breakdown after processing | False |
| `--config-json` | Output `--config-status` as machine-readable JSON (for scripting and CI/CD) | False |
| `--yes, -y` | Skip confirmation prompts (e.g., for large batch operations) | False |
| `--completion {bash,zsh,fish}` | Generate shell completion activation script for the specified shell and exit. Prints install instructions if argcomplete is not installed | - |

### Processing

| Option | Description | Default |
|--------|-------------|---------|
| `--batch` | Enable parallel batch processing | Auto-detected |
| `--workers N` | Number of parallel workers (1-256), or `auto` for automatic detection based on CPU cores and workload complexity | auto |
| `--continue-on-error` | Continue if a data view fails | False |
| `--skip-validation` | Skip data quality validation (20-30% faster) | False |

### Output

| Option | Description | Default |
|--------|-------------|---------|
| `--output-dir PATH` | Output directory for generated files | Current directory |
| `--output PATH` | Output file path. Use `-` or `stdout` to write to stdout (JSON/CSV only). Implies `--quiet` for stdout | - |
| `--format FORMAT` | Output format (see table below) | excel (SDR), console (diff) |
| `--stats` | Show quick statistics (metrics/dimensions count) without generating full SDR report | False |
| `--metrics-only` | Restrict output to metrics (exclude dimensions). Applies to SDR generation and diff comparison | False |
| `--dimensions-only` | Restrict output to dimensions (exclude metrics). Applies to SDR generation and diff comparison | False |
| `--max-issues N` | Limit issues to top N by severity (0=all) | 0 |
| `--run-summary-json PATH` | Write a machine-readable run summary JSON (all modes). Use `-` or `stdout` for stdout | - |
| `--name-match MODE` | Data view name matching mode: `exact` (default), `insensitive` (case-insensitive), or `fuzzy` (nearest match) | exact |
| `--fail-on-quality SEVERITY` | Exit with code 2 when quality issues at or above severity are found (`CRITICAL`, `HIGH`, `MEDIUM`, `LOW`, `INFO`). SDR mode only; cannot be combined with `--skip-validation` | - |
| `--quality-report FORMAT` | Generate standalone quality issues report only (`json` or `csv`) without SDR files. SDR mode only; cannot be combined with `--skip-validation` | - |
| `--allow-partial` | Opt-in exploratory SDR mode that allows partial output when required component fetches or validation runtime fail. Disabled by default; not supported with `--quality-report` or `--fail-on-quality` | False |
| `--quality-policy PATH` | Load quality defaults from JSON file (`fail_on_quality`, `quality_report`, `max_issues`, `allow_partial`). Explicit CLI flags override policy values | - |

> **Quality Gate & Report Constraints:** `--fail-on-quality` and `--quality-report` are only supported in SDR generation mode and cannot be combined with `--skip-validation`.
>
> **Quality Report CSV Stability:** `--quality-report csv` always emits a header row, even when no issues are found.

### Fail-Closed Matrix

| Scenario | SDR (default) | SDR + `--allow-partial` | `--quality-report` | `--inventory-only` (no derived) | `--inventory-only --include-derived` |
|--------|----------------|--------------------------|--------------------|----------------------------------|--------------------------------------|
| Required component fetch failure (`metrics`/`dimensions`) | Block | Continue (exploratory) | Block | Non-blocking if section not emitted | Continue (exploratory) / block by default |
| Required components both empty | Block | Continue (exploratory) | Block | Non-blocking if section not emitted | Continue (exploratory) / block by default |
| Data-quality validation runtime failure | Block | Continue (exploratory) | Block | Validation skipped when not emitted | Validation skipped when not emitted |
| Invalid data view lookup payload | Block | Block | Block | Block | Block |

> **Run summary observability:** Failed SDR results include stable `failure_code` and `failure_reason` fields, top-level `failure_rollups.by_code` / `failure_rollups.by_reason` counts, additive `output_files` alongside compatibility `output_file`, and per-result `partial_output` / `partial_reasons` for `--allow-partial` runs.
>
> **Artifact compatibility:** When `output_files` is present, `output_file` remains the primary artifact for backward compatibility and is listed first in the emitted artifact order.
>
> **Run summary contract (v1.1):** `summary_version` is currently `1.1`. Consumers should treat unknown keys as additive/forward-compatible and only rely on documented stable fields.
>
> **Failure code registry:** Stable `failure_code` values are documented in [FAILURE_CODES.md](FAILURE_CODES.md).

**Format Availability by Mode:**

| Format | SDR Generation | Diff Comparison | Org-Wide Analysis | Discovery |
|--------|----------------|-----------------|-------------------|-----------|
| `excel` | ✓ (default) | ✓ | ✓ | ✗ |
| `csv` | ✓ | ✓ | ✓ | ✓ |
| `json` | ✓ | ✓ | ✓ | ✓ |
| `html` | ✓ | ✓ | ✓ | ✗ |
| `markdown` | ✓ | ✓ | ✓ | ✗ |
| `console` | ✗ | ✓ (default) | ✓ (default) | ✓ (default) |
| `all` | ✓ | ✓ | ✓ | ✗ |

> **Note:** The Discovery column covers both discovery commands (`--list-dataviews`, `--list-connections`, `--list-datasets`) and discovery inspection commands (`--describe-dataview`, `--list-metrics`, `--list-dimensions`, `--list-segments`, `--list-calculated-metrics`). All share the same format support.
>
> **Note:** Console format is supported for diff comparison, org-wide analysis, and discovery. Using `--format console` with SDR generation will show an error with suggested alternatives.
>
> **Note:** In diff and org-wide modes, `--format all` includes console output (displayed in terminal) in addition to all file formats.

### Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `--config-file PATH` | Path to configuration file | config.json |
| `--config-status` | Show configuration status (source, fields, masked credentials) without API call. Faster than `--validate-config` for quick troubleshooting | - |
| `--log-level LEVEL` | DEBUG, INFO, WARNING, ERROR, CRITICAL | INFO |
| `--log-format FORMAT` | Log output format: `text` (human-readable) or `json` (structured logging for Splunk, ELK, CloudWatch) | text |
| `--production` | Minimal logging for performance | False |

> See the [Configuration Guide](CONFIGURATION.md) for details on config.json format, environment variables, and validation rules.

### Profile Management

Manage credentials for multiple Adobe Organizations. Profiles are stored in `~/.cja/orgs/<name>/`.

| Option | Description | Default |
|--------|-------------|---------|
| `--profile NAME`, `-p NAME` | Use named profile from `~/.cja/orgs/<NAME>/` | `$CJA_PROFILE` |
| `--profile-list` | List all available profiles with their org_id | - |
| `--profile-add NAME` | Create a new profile interactively | - |
| `--profile-show NAME` | Show profile configuration (secrets masked) | - |
| `--profile-test NAME` | Test profile credentials and API connectivity | - |
| `--profile-import NAME FILE` | Import profile non-interactively from JSON/.env file or a profile directory | - |
| `--profile-overwrite` | With `--profile-import`, allow replacing an existing profile | False |

**Environment Variables:**

| Variable | Description |
|----------|-------------|
| `CJA_PROFILE` | Default profile (overridden by `--profile`) |
| `CJA_HOME` | Override default `~/.cja` directory |

**Examples:**

```bash
# Create a profile interactively
cja_auto_sdr --profile-add client-a

# List all profiles
cja_auto_sdr --profile-list

# Use a profile
cja_auto_sdr --profile client-a --list-dataviews
cja_auto_sdr -p client-a "My Data View" --format excel

# Test profile connectivity
cja_auto_sdr --profile-test client-a

# Import a profile from JSON/.env without prompts
cja_auto_sdr --profile-import client-b ./client-b.env
cja_auto_sdr --profile-import client-b ./client-b.json --profile-overwrite

# Set default profile via environment
export CJA_PROFILE=client-a
cja_auto_sdr --list-dataviews
```

> See the [Profile Management section](CONFIGURATION.md#profile-management) in the Configuration Guide for full documentation.

### Validation & Testing

| Option | Description | Default |
|--------|-------------|---------|
| `--dry-run` | Validate config without generating reports | False |
| `--validate-only` | Alias for --dry-run | False |
| `--validate-config` | Validate config and API connectivity (no data view required). Runs 5 steps: environment check, dependency check, credentials check, API connectivity test, and output permissions check | False |
| `--list-dataviews` | List accessible data views and exit. Supports `--format json/csv` and `--output -` for machine-readable output | False |
| `--list-connections` | List all accessible connections with their datasets. Falls back to connection IDs derived from data views if the service account lacks product-admin privileges. Supports `--format json/csv` and `--output` | False |
| `--list-datasets` | List all data views with their backing connections and dataset details. Shows connection names when available, IDs when not. Supports `--format json/csv` and `--output` | False |
| `--filter PATTERN` | Filter discovery results by regex pattern (also applies to `--org-report`) | - |
| `--exclude PATTERN` | Exclude discovery results matching regex pattern (also applies to `--org-report`) | - |
| `--limit N` | Limit discovery results to first N items (also applies to `--org-report`) | - |
| `--sort FIELD` | Sort discovery output by field (prefix `-` for descending), e.g. `--sort name` or `--sort=-id` | - |
| `-i, --interactive` | Launch interactive mode for guided SDR generation. Walks through: data view selection, output format, and inventory options. Ideal for new users | False |
| `--sample-config` | Generate sample config file and exit | False |

> **Machine-readable error contract (discovery + `--stats`):** In JSON/CSV machine-readable flows (for example `--format json` or `--output -`), failures are emitted on `stderr` as JSON containing `error` and `error_type`, while successful payloads continue to use `stdout`.
>
> Example error envelope (`stderr`):
> `{"error":"Configuration error: Missing credentials","error_type":"configuration_error"}`

### Discovery Inspection

Drill into individual data view resources. These commands let you inspect a single data view's metadata, metrics, dimensions, segments, and calculated metrics without generating a full SDR report.

| Option | Argument | Description |
|--------|----------|-------------|
| `--describe-dataview` | `DATA_VIEW_ID_OR_NAME` | Show detailed metadata and component counts for a single data view |
| `--list-metrics` | `DATA_VIEW_ID_OR_NAME` | List all metrics in a data view |
| `--list-dimensions` | `DATA_VIEW_ID_OR_NAME` | List all dimensions in a data view |
| `--list-segments` | `DATA_VIEW_ID_OR_NAME` | List all segments/filters scoped to a data view |
| `--list-calculated-metrics` | `DATA_VIEW_ID_OR_NAME` | List all calculated metrics for a data view |

> **Name resolution:** These commands accept a data view ID (`dv_...`) or a data view name. When a name is provided, it is resolved via the API. Use `--name-match` to control matching (exact, insensitive, or fuzzy). If a name matches multiple data views, you will be prompted to select one interactively.
>
> **Mutual exclusivity:** These commands are mutually exclusive with each other and with all other discovery commands (`--list-dataviews`, `--list-connections`, `--list-datasets`).
>
> **Filter/Sort/Limit/Exclude:** `--list-metrics`, `--list-dimensions`, `--list-segments`, and `--list-calculated-metrics` support `--filter`, `--exclude`, `--sort`, and `--limit` for filtering, ordering, and limiting results. `--describe-dataview` does not support these options (it returns a single resource).

### Caching

| Option | Description | Default |
|--------|-------------|---------|
| `--enable-cache` | Enable validation result caching | False |
| `--clear-cache` | Clear cache before processing | False |
| `--cache-size N` | Maximum cached entries | 1000 |
| `--cache-ttl N` | Cache time-to-live in seconds | 3600 |

### Retry Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `--max-retries N` | Maximum API retry attempts | 3 |
| `--retry-base-delay N` | Initial retry delay in seconds | 1.0 |
| `--retry-max-delay N` | Maximum retry delay in seconds | 30.0 |

### Diff Comparison

| Option | Description | Default |
|--------|-------------|---------|
| `--diff` | Compare two data views. Requires exactly 2 data view IDs/names | False |
| `--snapshot FILE` | Save a data view snapshot to JSON file | - |
| `--list-snapshots` | List snapshots from `--snapshot-dir` (optionally filtered by DATA_VIEW_ID positional args) | False |
| `--prune-snapshots` | Apply retention policies (`--keep-last`/`--keep-since`) in `--snapshot-dir` without running diff | False |
| `--diff-snapshot FILE` | Compare data view against a saved snapshot | - |
| `--compare-with-prev` | Compare data view against its most recent snapshot in --snapshot-dir | False |
| `--compare-snapshots A B` | Compare two snapshot files directly (no API calls) | - |
| `--changes-only` | Only show changed items (hide unchanged) | False |
| `--summary` | Show summary statistics only | False |
| `--ignore-fields FIELDS` | Comma-separated fields to ignore in comparison | - |
| `--diff-labels A B` | Custom labels for the two sides | Data view names |
| `--show-only TYPES` | Filter by change type: added, removed, modified, unchanged (comma-separated) | All types |
| `--metrics-only` | Only compare metrics (exclude dimensions) | False |
| `--dimensions-only` | Only compare dimensions (exclude metrics) | False |
| `--extended-fields` | Include extended fields (attribution, format, bucketing, etc.) | False |
| `--side-by-side` | Show side-by-side comparison view for modified items | False |
| `--no-color` | Disable ANSI color codes in console output (global) | False |
| `--color-theme THEME` | Color theme for diff output: `default` (green/red) or `accessible` (blue/orange) | default |
| `--quiet-diff` | Suppress output, only return exit code | False |
| `--reverse-diff` | Swap source and target comparison direction | False |
| `--warn-threshold PERCENT` | Exit with code 3 if change % exceeds threshold | - |
| `--group-by-field` | Group changes by field name instead of component | False |
| `--group-by-field-limit N` | Max items per section in --group-by-field output (0=unlimited) | 10 |
| `--diff-output FILE` | Write output to file instead of stdout | - |
| `--format-pr-comment` | Output in GitHub/GitLab PR comment format | False |
| `--auto-snapshot` | Automatically save snapshots during diff for audit trail | False |
| `--auto-prune` | With `--auto-snapshot`, apply default retention (`--keep-last 20` + `--keep-since 30d`) only when both retention flags are omitted | False |
| `--snapshot-dir DIR` | Directory for auto-saved snapshots | ./snapshots |
| `--keep-last N` | Retention: keep only last N snapshots per data view (0=all) | 0 |
| `--keep-since PERIOD` | Date-based retention: delete snapshots older than PERIOD. Formats: `7d`, `2w`, `1m`, `30` (days) | - |

> **Retention precedence:** Explicit values are preserved, including `--keep-last 0` / `--keep-last=0` and `--keep-since 90d` / `--keep-since=90d`.

### Org-Wide Analysis

Analyze component usage patterns across all data views in your organization.

#### Basic Options

| Option | Description | Default |
|--------|-------------|---------|
| `--org-report` | Enable org-wide analysis mode. Analyzes all accessible data views and generates a governance report | False |
| `--filter PATTERN` | Include only data views matching regex pattern (case-insensitive) | - |
| `--exclude PATTERN` | Exclude data views matching regex pattern (case-insensitive) | - |
| `--limit N` | Analyze only the first N data views (useful for testing) | - |
| `--include-names` | Fetch and display component names (slower but more readable) | False |
| `--skip-similarity` | Skip O(n²) pairwise similarity calculation (faster for large orgs) | False |
| `--similarity-max-dvs N` | Guardrail to skip similarity when data views exceed N. Similarity has O(n²) complexity—250 DVs means ~31K comparisons. Use `--force-similarity` to override | 250 |
| `--force-similarity` | Force similarity matrix even if guardrails would skip it | False |
| `--memory-warning MB` | Warn if component index estimated memory exceeds this threshold in MB (0 to disable) | 100 |
| `--memory-limit MB` | Abort if component index exceeds this size in MB. Protects against OOM for very large orgs | - |
| `--org-summary` | Show only summary statistics, suppress detailed component lists | False |
| `--org-verbose` | Include full component lists and detailed breakdowns in output | False |

#### Threshold Options

| Option | Description | Default |
|--------|-------------|---------|
| `--core-threshold FLOAT` | Fraction of data views for "core" classification (0.0-1.0) | 0.5 |
| `--core-min-count N` | Absolute count for "core" classification (overrides threshold) | - |
| `--overlap-threshold FLOAT` | Minimum Jaccard similarity to flag as "high overlap" (0.0-1.0; capped at 0.9 for governance checks) | 0.8 |

#### Component Type & Metadata Options

| Option | Description | Default |
|--------|-------------|---------|
| `--no-component-types` | Disable component type breakdown (standard vs derived metrics/dimensions) | False |
| `--include-metadata` | Include data view metadata (owner, creation/modification dates, descriptions) | False |
| `--include-drift` | Include component drift details showing exact differences between similar DV pairs | False |

#### Sampling Options

| Option | Description | Default |
|--------|-------------|---------|
| `--sample N` | Randomly sample N data views (useful for very large orgs) | - |
| `--sample-seed SEED` | Random seed for reproducible sampling | - |
| `--sample-stratified` | Stratify sample by data view name prefix | False |

#### Caching Options

| Option | Description | Default |
|--------|-------------|---------|
| `--use-cache` | Enable caching of data view components for faster repeat runs | False |
| `--cache-max-age HOURS` | Maximum cache age before refresh | 24 |
| `--refresh-cache` | Clear the org-report cache and fetch fresh data | False |
| `--validate-cache` | Validate cached entries against data view modification timestamps before using | False |

Cache is stored in `~/.cja_auto_sdr/cache/org_report_cache.json`.

#### Concurrency Options

| Option | Description | Default |
|--------|-------------|---------|
| `--org-shared-client` | Use a single shared cjapy client across threads (faster, but may be unsafe if cjapy is not thread-safe) | False |

#### Clustering Options

| Option | Description | Default |
|--------|-------------|---------|
| `--cluster` | Enable hierarchical clustering to group related data views | False |
| `--cluster-method METHOD` | Clustering linkage method: `average` (recommended) or `complete` | average |

> **Requires:** The `clustering` extra must be installed: `uv pip install 'cja-auto-sdr[clustering]'` (macOS/Linux) or `uv pip install "cja-auto-sdr[clustering]"` (Windows PowerShell)
>
> **Note:** The `average` method is recommended because it works correctly with Jaccard distances (which measure component overlap). The `complete` method is also valid and produces tighter clusters.

#### Governance & CI/CD Options

| Option | Description | Default |
|--------|-------------|---------|
| `--duplicate-threshold N` | Maximum allowed high-similarity pairs (>=90%). Exit code 2 if exceeded with `--fail-on-threshold` | - |
| `--isolated-threshold PERCENT` | Maximum isolated component percentage (0.0-1.0). Exit code 2 if exceeded with `--fail-on-threshold` | - |
| `--fail-on-threshold` | Enable exit code 2 when governance thresholds are exceeded (for CI/CD integration) | False |

#### Advanced Analysis Options

| Option | Description | Default |
|--------|-------------|---------|
| `--org-stats` | Quick summary stats only - skips similarity matrix and clustering for faster results | False |
| `--audit-naming` | Detect naming pattern inconsistencies (snake_case vs camelCase, stale prefixes, etc.) | False |
| `--compare-org-report PREV.json` | Compare current org-report to a previous JSON report for trending/drift analysis | - |
| `--trending-window [N]` | Show trending across the last N cached org-report snapshots (default: 10). Renders in all output formats. | None |
| `--list-org-report-snapshots` | List cached org-report snapshots from the persistent trending history store | False |
| `--inspect-org-report-snapshot FILE` | Inspect one cached org-report snapshot JSON, including history eligibility metadata, without running a fresh org-report | - |
| `--prune-org-report-snapshots` | Apply retention policies to cached org-report snapshots in the persistent trending history store | False |
| `--org-report-snapshot-org ORG_ID` | Filter org-report snapshot listing/pruning to one org ID | - |
| `--org-report-keep-last N` | For `--prune-org-report-snapshots`, keep only the last N snapshots per org (0 = keep all) | 0 |
| `--org-report-keep-since PERIOD` | For `--prune-org-report-snapshots`, delete org-report snapshots older than PERIOD | - |
| `--owner-summary` | Group statistics by data view owner (requires `--include-metadata`) | False |
| `--flag-stale` | Flag components with stale naming patterns (test, old, temp, deprecated, version suffixes, date patterns) | False |

**Format Support:** All formats are supported (`console`, `json`, `excel`, `markdown`, `html`, `csv`, `all`). Default is `console`.

**Format Aliases:**
| Alias | Expands To | Use Case |
|-------|------------|----------|
| `reports` | excel + markdown | Documentation and sharing |
| `data` | csv + json | Data pipelines and analysis |
| `ci` | json + markdown | CI/CD integration |

**Output Structure:**
- **Summary**: Data views analyzed, unique metrics/dimensions, analysis duration
- **Distribution**: Component distribution across Core/Common/Limited/Isolated buckets
- **Component Index**: Full index of all components with data view membership
- **Similarity Pairs**: Data view pairs with high overlap (potential duplicates)
- **Recommendations**: Governance recommendations based on analysis
- **Clusters**: Related data view groups (when `--cluster` is enabled)
- **Owner Summary**: Stats grouped by owner (when `--owner-summary` is enabled)

> **Org JSON telemetry contract:** The `data_view_fetch_failures` block is always present and includes `count`, `data_view_ids`, and `failure_reason_counts` (an additive reason-to-count map that may be empty). Consumers should ignore unknown future keys in this block.

### Git Integration

| Option | Description | Default |
|--------|-------------|---------|
| `--git-init` | Initialize a new Git repository for snapshots | - |
| `--git-commit` | Save snapshot and commit to Git after SDR generation | False |
| `--git-push` | Push to remote repository after committing | False |
| `--git-message MSG` | Custom commit message (auto-generated if not provided) | - |
| `--git-dir DIR` | Directory for Git snapshots | ./sdr-snapshots |

### Reliability & Auto-Tuning

| Option | Description | Default |
|--------|-------------|---------|
| `--api-auto-tune` | Enable automatic API worker tuning based on response times | False |
| `--api-min-workers N` | Minimum workers for auto-tuning | 1 |
| `--api-max-workers N` | Maximum workers for auto-tuning | 10 |
| `--circuit-breaker` | Enable circuit breaker pattern for API calls | False |
| `--circuit-failure-threshold N` | Consecutive failures before opening circuit | 5 |
| `--circuit-timeout SECONDS` | Recovery timeout before retrying (OPEN → HALF_OPEN) | 30 |
| `--shared-cache` | Share validation cache across batch workers (multiprocessing) | False |

### Inventory Options

| Option | Description | Default |
|--------|-------------|---------|
| `--include-segments` | Include segments inventory in output. Adds a "Segments" sheet/section with complexity scores, container types, definition summaries, and component references. Works in SDR and snapshot diff modes (same data view only—see note). | False |
| `--include-derived` | Include derived field inventory in output. Adds a "Derived Fields" sheet/section with complexity scores, functions used, and logic summaries. **SDR mode only** (not diff—see note below). | False |
| `--include-calculated` | Include calculated metrics inventory in output. Adds a "Calculated Metrics" sheet/section with complexity scores, formula summaries, and metric references. Works in SDR and snapshot diff modes (same data view only—see note). | False |
| `--inventory-only` | Output only inventory sheets (Segments, Derived Fields, Calculated Metrics). Skips standard SDR sheets (Metadata, Data Quality, DataView Details, Metrics, Dimensions). Requires at least one `--include-*` flag. SDR mode only. | False |
| `--inventory-summary` | Display quick inventory statistics without generating full output files. Shows counts, complexity distribution, governance metadata, and high-complexity warnings. Requires at least one `--include-*` flag. Cannot be used with `--inventory-only`. | False |
| `--include-all-inventory` | Enable all inventory options with smart mode detection. SDR mode enables `--include-segments`, `--include-calculated`, and `--include-derived`. Snapshot/diff modes (`--snapshot`, `--diff-snapshot`, `--compare-snapshots`, `--compare-with-prev`) enable only `--include-segments` and `--include-calculated`. | False |

> **Sheet Ordering:** Inventory sheets appear at the end of the output. When multiple are enabled, they appear in the order specified on the command line. For example, `--include-calculated --include-segments` places Calculated Metrics before Segments.
>
> **Diff Mode Support:** `--include-calculated` and `--include-segments` work with snapshot diff modes (`--diff-snapshot`, `--compare-snapshots`, `--compare-with-prev`) for comparing the **same data view** over time. Cross-data-view comparison (`--diff dv_A dv_B`) does not support inventory options because inventory IDs are data-view-scoped. **Design choice:** CJA Auto SDR intentionally does not attempt name-based or formula-based fuzzy matching for calculated metrics or segments across data views, to avoid false positives where identically-named components represent different business logic.
>
> **Derived Fields:** `--include-derived` is for **SDR generation only**, not diff. Derived fields are already included in the standard metrics/dimensions API output, so changes to derived fields are automatically captured in the Metrics/Dimensions diff sections. The `--include-derived` flag provides additional logic analysis (complexity scores, functions used, branch counts) that is valuable for SDR documentation but would be duplicative in diff mode.
>
> **Snapshot/Diff Tip:** `--include-all-inventory` automatically excludes `--include-derived` in `--snapshot`, `--diff-snapshot`, `--compare-snapshots`, and `--compare-with-prev` modes.

### Environment Variables

**Credentials (take precedence over config.json):**

| Variable | Description |
|----------|-------------|
| `ORG_ID` | Adobe Organization ID |
| `CLIENT_ID` | OAuth Client ID |
| `SECRET` | Client Secret |
| `SCOPES` | OAuth scopes |
| `SANDBOX` | Sandbox name (optional) |

**Configuration:**

| Variable | Description |
|----------|-------------|
| `LOG_LEVEL` | Default log level (overridden by --log-level) |
| `OUTPUT_DIR` | Default output directory (overridden by --output-dir) |
| `MAX_RETRIES` | Maximum API retry attempts (overridden by --max-retries) |
| `RETRY_BASE_DELAY` | Initial retry delay in seconds (overridden by --retry-base-delay) |
| `RETRY_MAX_DELAY` | Maximum retry delay in seconds (overridden by --retry-max-delay) |

**Console & CI Integration:**

| Variable | Description |
|----------|-------------|
| `NO_COLOR` | Disable ANSI colors globally when set to a non-empty value (unless `FORCE_COLOR` is explicitly set) |
| `FORCE_COLOR` | Force ANSI color behavior (`0` disables; any non-empty/non-`0` value enables) |
| `GITHUB_STEP_SUMMARY` | When set by GitHub Actions, appends Markdown summaries for diff, quality, and org-report output |

## Usage Examples

### Single Data View

```bash
# By ID
cja_auto_sdr dv_677ea9291244fd082f02dd42

# By name
cja_auto_sdr "Production Analytics"

# With custom output directory
cja_auto_sdr dv_12345 --output-dir ./reports
cja_auto_sdr "Test Environment" --output-dir ./reports

# With custom config file
cja_auto_sdr "Production Analytics" --config-file ./prod_config.json

# With debug logging
cja_auto_sdr "Staging" --log-level DEBUG

# Fail CI on quality issues at or above HIGH severity
cja_auto_sdr dv_12345 --fail-on-quality HIGH

# Generate standalone quality report only (no SDR files)
cja_auto_sdr dv_12345 --quality-report json --output quality_issues.json

# Generate metrics-only SDR output
cja_auto_sdr dv_12345 --metrics-only

# Generate dimensions-only SDR output
cja_auto_sdr dv_12345 --dimensions-only
```

### Multiple Data Views

```bash
# By IDs - automatic batch processing
cja_auto_sdr dv_12345 dv_67890 dv_abcde

# By names
cja_auto_sdr "Production" "Staging" "Test Environment"

# Mix IDs and names
cja_auto_sdr dv_12345 "Staging Analytics" dv_67890

# Explicit batch mode
cja_auto_sdr --batch dv_12345 dv_67890 dv_abcde

# Custom worker count
cja_auto_sdr --batch "Production" "Staging" --workers 8

# Continue on errors
cja_auto_sdr --batch "Prod" "Stage" "Test" --continue-on-error
```

### Discovery Commands

```bash
# Quick check of configuration status (no API call, fast)
cja_auto_sdr --config-status

# Validate configuration and API connectivity (no data view needed)
cja_auto_sdr --validate-config

# List all accessible data views
cja_auto_sdr --list-dataviews

# List data views in JSON format (for scripting)
cja_auto_sdr --list-dataviews --format json

# List data views to stdout for piping
cja_auto_sdr --list-dataviews --output - | jq '.dataViews[].id'

# List all accessible connections with their datasets
cja_auto_sdr --list-connections

# List connections in JSON format
cja_auto_sdr --list-connections --format json

# List connections in CSV and save to file
cja_auto_sdr --list-connections --format csv --output connections.csv

# List all data views with their backing connections and datasets
cja_auto_sdr --list-datasets

# List datasets in JSON format for scripting
cja_auto_sdr --list-datasets --format json

# Save dataset inventory to file
cja_auto_sdr --list-datasets --format csv --output datasets.csv

# Filter discovery results by name pattern
cja_auto_sdr --list-dataviews --filter "Prod.*"

# Exclude test/dev data views from listing
cja_auto_sdr --list-dataviews --exclude "Test|Dev"

# Sort discovery output by name (ascending) or ID (descending)
cja_auto_sdr --list-dataviews --sort name
cja_auto_sdr --list-connections --sort=-id

# Limit discovery results
cja_auto_sdr --list-dataviews --limit 10

# Use a specific profile for discovery
cja_auto_sdr --profile client-a --list-connections

# Generate sample configuration
cja_auto_sdr --sample-config

# Show exit code reference
cja_auto_sdr --exit-codes

# Validate config without generating report
cja_auto_sdr dv_12345 --dry-run
```

> **Note:** `--list-dataviews`, `--list-connections`, and `--list-datasets` are mutually exclusive — only one can be used at a time.
>
> **Note:** `--list-connections` requires the API service account to be a CJA Product Admin for full connection details (names, owners, datasets). Without admin privileges, the tool falls back to showing connection IDs derived from data views.
>
> **Discovery Filters:** `--list-dataviews`, `--list-connections`, and `--list-datasets` support `--filter`, `--exclude`, `--limit`, and `--sort` for filtering, limiting, and ordering results.

### Discovery Inspection Commands

```bash
# Inspect a single data view (metadata, component counts, owner, dates)
cja_auto_sdr --describe-dataview dv_abc123

# Describe data view as JSON (for scripting)
cja_auto_sdr --describe-dataview dv_abc123 --format json

# List all metrics in a data view
cja_auto_sdr --list-metrics dv_abc123

# Filter metrics by name pattern
cja_auto_sdr --list-metrics dv_abc123 --filter "revenue"

# Sort metrics by name (descending)
cja_auto_sdr --list-metrics dv_abc123 --sort=-name

# List all dimensions in a data view
cja_auto_sdr --list-dimensions dv_abc123

# Export dimensions to CSV file
cja_auto_sdr --list-dimensions dv_abc123 --format csv --output dims.csv

# List first 20 dimensions
cja_auto_sdr --list-dimensions dv_abc123 --limit 20

# List all segments/filters scoped to a data view
cja_auto_sdr --list-segments dv_abc123

# List segments as JSON
cja_auto_sdr --list-segments dv_abc123 --format json

# List calculated metrics for a data view
cja_auto_sdr --list-calculated-metrics dv_abc123

# Find calculated metrics matching a pattern
cja_auto_sdr --list-calculated-metrics dv_abc123 --filter "percent"

# Use with a profile
cja_auto_sdr --profile client-a --list-metrics dv_abc123

# Use a data view name instead of ID
cja_auto_sdr --describe-dataview "Production Web Data"

# Name with fuzzy matching
cja_auto_sdr --list-metrics "Prod Web" --name-match fuzzy
```

> **Note:** Discovery inspection commands are mutually exclusive with each other and with `--list-dataviews`, `--list-connections`, and `--list-datasets`.
>
> **Name resolution:** You can pass a data view name instead of an ID. Use `--name-match` to control matching mode (exact, insensitive, fuzzy). If a name matches multiple views, you'll be prompted to choose one interactively.
>
> **Filter/Sort/Limit/Exclude:** All list commands (`--list-metrics`, `--list-dimensions`, `--list-segments`, `--list-calculated-metrics`) support `--filter`, `--exclude`, `--sort`, and `--limit`. `--describe-dataview` does not (it returns a single resource).
>
> **Table column scope:** For readability, table output for `--list-segments` omits `tags`, `created`, and `modified`; table output for `--list-calculated-metrics` omits `precision`, `tags`, `created`, and `modified`. Use JSON/CSV for the full field set.

### Quick Statistics

```bash
# Quick stats for a single data view (no full report generated)
cja_auto_sdr dv_12345 --stats

# Stats for multiple data views
cja_auto_sdr dv_1 dv_2 dv_3 --stats

# Stats in JSON format
cja_auto_sdr dv_12345 --stats --format json

# Stats to stdout for scripting
cja_auto_sdr dv_12345 --stats --output -

# Stats in CSV format to file
cja_auto_sdr dv_12345 --stats --format csv --output stats.csv
```

### Interactive Data View Selection

```bash
# Launch interactive selection mode
cja_auto_sdr --interactive

# Interactive selection with a specific profile
cja_auto_sdr --interactive --profile client-a

# Interactive selection with specific output directory
cja_auto_sdr --interactive --output-dir ./reports
```

> **Note:** In `--interactive` mode, the wizard prompts you to choose output format and inventory options.

**Selection Syntax:**
- Single: `3` (selects #3)
- Multiple: `1,3,5` (selects #1, #3, #5)
- Range: `1-5` (selects #1 through #5)
- Combined: `1,3-5,7` (selects #1, #3, #4, #5, #7)
- All: `all` or `a` (selects all data views)
- Cancel: `q` or `quit` (exit without selection)

### Auto-Open Generated Files

```bash
# Generate SDR and open immediately in default app
cja_auto_sdr dv_12345 --open

# Generate Excel and open
cja_auto_sdr dv_12345 --format excel --open

# Batch processing - opens all successful files
cja_auto_sdr dv_1 dv_2 dv_3 --open
```

### Performance Optimization

```bash
# Production mode (minimal logging)
cja_auto_sdr dv_12345 --production

# Skip validation for faster processing
cja_auto_sdr dv_12345 --skip-validation

# Enable caching for repeated runs
cja_auto_sdr dv_12345 --enable-cache

# Quiet mode
cja_auto_sdr dv_12345 --quiet

# Show performance timing breakdown
cja_auto_sdr dv_12345 --show-timings
```

### Output Formats

```bash
# Excel (default)
cja_auto_sdr dv_12345 --format excel

# CSV files
cja_auto_sdr dv_12345 --format csv

# JSON
cja_auto_sdr dv_12345 --format json

# HTML report
cja_auto_sdr dv_12345 --format html

# Markdown (GitHub/Confluence compatible)
cja_auto_sdr dv_12345 --format markdown

# All formats
cja_auto_sdr dv_12345 --format all
```

### Production Examples

```bash
# Full production batch
cja_auto_sdr --batch \
  dv_12345 dv_67890 dv_abcde \
  --workers 4 \
  --output-dir ./sdr_reports \
  --continue-on-error \
  --log-level WARNING

# Optimized run with caching
cja_auto_sdr dv_12345 \
  --production \
  --enable-cache \
  --skip-validation

# Read data views from file
cja_auto_sdr --batch $(cat dataviews.txt)
```

### Data View Comparison (Diff)

```bash
# Compare two live data views (by ID)
cja_auto_sdr --diff dv_12345 dv_67890

# Compare by name
cja_auto_sdr --diff "Production Analytics" "Staging Analytics"

# Mix IDs and names (both supported)
cja_auto_sdr --diff dv_12345 "Staging Analytics"
cja_auto_sdr --diff "Production Analytics" dv_67890

# Save a snapshot for later comparison (ID or name)
cja_auto_sdr dv_12345 --snapshot ./snapshots/baseline.json
cja_auto_sdr "Production Analytics" --snapshot ./snapshots/baseline.json

# Compare current state against a saved snapshot (ID or name)
cja_auto_sdr dv_12345 --diff-snapshot ./snapshots/baseline.json
cja_auto_sdr "Production Analytics" --diff-snapshot ./snapshots/baseline.json

# Compare two snapshot files directly (no API calls needed)
cja_auto_sdr --compare-snapshots ./snapshots/before.json ./snapshots/after.json
cja_auto_sdr --compare-snapshots ./snapshots/prod.json ./snapshots/staging.json --format html

# Diff with different output formats
cja_auto_sdr --diff dv_12345 dv_67890 --format html --output-dir ./reports
cja_auto_sdr --diff dv_12345 dv_67890 --format all

# Show only changes (hide unchanged items)
cja_auto_sdr --diff dv_12345 dv_67890 --changes-only

# Show summary only (no detailed changes)
cja_auto_sdr --diff dv_12345 dv_67890 --summary

# Ignore specific fields during comparison
cja_auto_sdr --diff dv_12345 dv_67890 --ignore-fields description,title

# Custom labels for source and target
cja_auto_sdr --diff dv_12345 dv_67890 --diff-labels Production Staging

# CI/CD integration (policy exit codes)
cja_auto_sdr --diff dv_12345 dv_67890 --changes-only --format json
echo $?  # 0 = no differences, 2 = differences found, 3 = warn-threshold exceeded, 1 = error

# Filter by change type
cja_auto_sdr --diff dv_12345 dv_67890 --show-only added
cja_auto_sdr --diff dv_12345 dv_67890 --show-only removed,modified

# Filter by component type
cja_auto_sdr --diff dv_12345 dv_67890 --metrics-only
cja_auto_sdr --diff dv_12345 dv_67890 --dimensions-only

# Extended field comparison
cja_auto_sdr --diff dv_12345 dv_67890 --extended-fields

# Side-by-side view
cja_auto_sdr --diff dv_12345 dv_67890 --side-by-side
cja_auto_sdr --diff dv_12345 dv_67890 --side-by-side --format markdown

# Accessible color theme (colorblind-friendly)
cja_auto_sdr --diff dv_12345 dv_67890 --color-theme accessible

# Combined options
cja_auto_sdr --diff dv_12345 dv_67890 --extended-fields --side-by-side --show-only modified --changes-only

# Auto-snapshot: automatically save snapshots during diff for audit trail
cja_auto_sdr --diff dv_12345 dv_67890 --auto-snapshot

# Custom snapshot directory
cja_auto_sdr --diff dv_12345 dv_67890 --auto-snapshot --snapshot-dir ./history

# With retention policy (keep last 10 snapshots per data view)
cja_auto_sdr --diff dv_12345 dv_67890 --auto-snapshot --keep-last 10

# Time-based retention (delete snapshots older than 30 days)
cja_auto_sdr --diff dv_12345 dv_67890 --auto-snapshot --keep-since 30d

# Auto-prune defaults (when both retention flags are omitted)
cja_auto_sdr --diff dv_12345 dv_67890 --auto-snapshot --auto-prune

# Explicit retention values (including --arg=value forms) override defaults
cja_auto_sdr --diff dv_12345 dv_67890 --auto-snapshot --auto-prune --keep-last=0

# Auto-snapshot works with diff-snapshot too (saves current state)
cja_auto_sdr dv_12345 --diff-snapshot ./baseline.json --auto-snapshot
```

### Org-Wide Analysis

```bash
# Basic org-wide report (console output)
cja_auto_sdr --org-report

# Filter data views by name pattern
cja_auto_sdr --org-report --filter "Prod.*"

# Exclude test/dev data views
cja_auto_sdr --org-report --exclude "Test|Dev|Sandbox"

# Combine filter and exclude
cja_auto_sdr --org-report --filter "Analytics" --exclude "Test"

# Limit to first N data views (for testing)
cja_auto_sdr --org-report --limit 10

# Include component names (slower but more readable)
cja_auto_sdr --org-report --include-names

# Skip similarity matrix (faster for large orgs)
cja_auto_sdr --org-report --skip-similarity

# Custom classification thresholds
cja_auto_sdr --org-report --core-threshold 0.7 --overlap-threshold 0.9

# Export to Excel
cja_auto_sdr --org-report --format excel

# Export to JSON for programmatic processing
cja_auto_sdr --org-report --format json --output org_analysis.json

# Export all formats
cja_auto_sdr --org-report --format all --output-dir ./reports

# Use format aliases
cja_auto_sdr --org-report --format reports  # excel + markdown
cja_auto_sdr --org-report --format data     # csv + json
cja_auto_sdr --org-report --format ci       # json + markdown

# Full governance report with names
cja_auto_sdr --org-report --include-names --format excel --output-dir ./governance

# Quiet mode for scripting
cja_auto_sdr --org-report --format json --quiet --output ./reports/org.json

# --- Advanced Options ---

# Include data view metadata (owner, dates)
cja_auto_sdr --org-report --include-metadata

# Include drift details between similar data view pairs
cja_auto_sdr --org-report --include-drift --include-names

# Quick stats only (fast health check)
cja_auto_sdr --org-report --org-stats

# Sampling for very large orgs
cja_auto_sdr --org-report --sample 20 --sample-seed 42
cja_auto_sdr --org-report --sample 30 --sample-stratified

# Caching for faster repeat runs
cja_auto_sdr --org-report --use-cache
cja_auto_sdr --org-report --use-cache --refresh-cache  # Force refresh
cja_auto_sdr --org-report --use-cache --cache-max-age 48  # Custom TTL

# Clustering to find related data view groups
cja_auto_sdr --org-report --cluster --format excel
cja_auto_sdr --org-report --cluster --cluster-method complete

# Naming convention audit
cja_auto_sdr --org-report --audit-naming

# Flag stale components
cja_auto_sdr --org-report --flag-stale

# Owner/team summary (requires --include-metadata)
cja_auto_sdr --org-report --include-metadata --owner-summary

# Compare to previous report for trending/drift analysis
cja_auto_sdr --org-report --format json --output current.json
cja_auto_sdr --org-report --compare-org-report ./baseline.json

# Baseline must be a full-fidelity report; legacy markerless JSON baselines are rejected.

# --- CI/CD Governance Checks ---

# Exit with code 2 if more than 5 high-similarity pairs exist
cja_auto_sdr --org-report --duplicate-threshold 5 --fail-on-threshold

# Exit with code 2 if isolated components exceed 30%
cja_auto_sdr --org-report --isolated-threshold 0.3 --fail-on-threshold

# Combined governance thresholds
cja_auto_sdr --org-report \
  --duplicate-threshold 3 \
  --isolated-threshold 0.4 \
  --fail-on-threshold \
  --format json --output governance-report.json

# Full governance CI/CD check
cja_auto_sdr --org-report \
  --duplicate-threshold 5 \
  --isolated-threshold 0.35 \
  --fail-on-threshold \
  --audit-naming \
  --flag-stale \
  --format json --quiet

# --- Data Analysis Examples ---

# Find high-similarity pairs (potential duplicates)
cja_auto_sdr --org-report --overlap-threshold 0.9 --format json --output - | \
  jq '.similarity_pairs[] | select(.similarity >= 0.9)'

# Extract high-priority recommendations
cja_auto_sdr --org-report --format json --output - | \
  jq '.recommendations[] | select(.severity == "high")'

# List core components used across the org
cja_auto_sdr --org-report --include-names --format json --output - | \
  jq '.component_index | to_entries[] | select(.value.bucket == "core")'
```

### Git Integration

```bash
# Initialize a new Git repository for snapshots (one-time setup)
cja_auto_sdr --git-init
cja_auto_sdr --git-init --git-dir ./my-snapshots

# Generate SDR and commit to Git
cja_auto_sdr dv_12345 --git-commit

# Generate with custom commit message
cja_auto_sdr dv_12345 --git-commit --git-message "Pre-release snapshot"

# Generate, commit, and push to remote
cja_auto_sdr dv_12345 --git-commit --git-push

# Multiple data views with Git commits
cja_auto_sdr dv_prod dv_staging dv_dev --git-commit

# Custom Git directory
cja_auto_sdr dv_12345 --git-commit --git-dir ./my-snapshots
```

### Inventory Options

```bash
# Include segments inventory (SDR + Snapshot Diff)
cja_auto_sdr dv_12345 --include-segments

# Include derived field inventory (SDR only)
cja_auto_sdr dv_12345 --include-derived

# Include calculated metrics inventory (SDR + Snapshot Diff)
cja_auto_sdr dv_12345 --include-calculated

# Include all three inventories in SDR output
cja_auto_sdr dv_12345 --include-segments --include-calculated --include-derived

# Control sheet order (Calculated Metrics first, then Segments, then Derived Fields)
cja_auto_sdr dv_12345 --include-calculated --include-segments --include-derived

# Generate ONLY inventory sheets (no standard SDR content)
cja_auto_sdr dv_12345 --include-segments --inventory-only

# Multiple inventories only
cja_auto_sdr dv_12345 --include-segments --include-calculated --include-derived --inventory-only

# --- Include All Inventory Shorthand ---
# Enable all inventory options with one flag (SDR mode)
cja_auto_sdr dv_12345 --include-all-inventory

# Same as above - shorthand is equivalent to all three flags
# cja_auto_sdr dv_12345 --include-segments --include-calculated --include-derived

# With snapshot/diff modes, shorthand enables only supported inventories
cja_auto_sdr dv_12345 --snapshot ./snap.json --include-all-inventory
cja_auto_sdr dv_12345 --diff-snapshot ./snap.json --include-all-inventory

# Combine with inventory-only or inventory-summary
cja_auto_sdr dv_12345 --include-all-inventory --inventory-only
cja_auto_sdr dv_12345 --include-all-inventory --inventory-summary

# --- Inventory Summary (Quick Stats) ---
# Quick stats for all inventories (console output)
cja_auto_sdr dv_12345 --include-all-inventory --inventory-summary

# Summary for segments only
cja_auto_sdr dv_12345 --include-segments --inventory-summary

# Save summary to JSON file
cja_auto_sdr dv_12345 --include-segments --include-calculated --inventory-summary --format json

# Combine with output format options
cja_auto_sdr dv_12345 --include-segments --include-calculated --format all

# JSON output for programmatic analysis
cja_auto_sdr dv_12345 --include-segments -f json -o segments.json

# --- Inventory Diff (Snapshot Comparisons) ---
# Note: Only --include-calculated and --include-segments are supported for diff.
# Derived fields are already in metrics/dimensions output, so changes appear there.

# Create snapshot with inventory data
cja_auto_sdr dv_12345 --snapshot ./baseline.json \
  --include-calculated --include-segments

# Compare current state against baseline (same data view)
cja_auto_sdr dv_12345 --diff-snapshot ./baseline.json \
  --include-calculated --include-segments

# Compare two snapshots directly with inventory
cja_auto_sdr --compare-snapshots ./before.json ./after.json \
  --include-calculated --include-segments

# Quick comparison against most recent snapshot with inventory
cja_auto_sdr dv_12345 --compare-with-prev --include-calculated

# Inventory diff with specific output format
cja_auto_sdr dv_12345 --diff-snapshot ./baseline.json \
  --include-segments --format excel --changes-only
```

## Output Files

### Excel Workbook

- **Filename**: `CJA_DataView_[Name]_[ID]_SDR.xlsx`
- **Location**: Specified by `--output-dir`
- **Sheets** (in order):
  1. Metadata
  2. Data Quality
  3. DataView Details
  4. Metrics
  5. Dimensions
  6. Segments (if `--include-segments`)
  7. Derived Fields (if `--include-derived`)
  8. Calculated Metrics (if `--include-calculated`)

> **Note:** When using `--inventory-only`, only the inventory sheets (6-8) are generated, skipping sheets 1-5.

### Log Files

- **Single mode**: `logs/SDR_Generation_[DataViewID]_[Timestamp].log`
- **Batch mode**: `logs/SDR_Batch_Generation_[Timestamp].log`

## Expected Output

### Single Data View

```
Processing data view: dv_677ea9291244fd082f02dd42

============================================================
INITIALIZING CJA CONNECTION
============================================================
✓ API connection successful! Found 85 data view(s)
============================================================
VALIDATING DATA VIEW
============================================================
✓ Data view validated successfully!
  Name: Production Analytics
  ID: dv_677ea9291244fd082f02dd42
============================================================
✓ SDR generation complete! File saved as: CJA_DataView_Production_Analytics_dv_677ea9291244fd082f02dd42_SDR.xlsx (2.5 MB)
```

### Batch Mode

```
Processing 3 data view(s) in batch mode with 4 workers...

============================================================
BATCH PROCESSING START
============================================================
✓ dv_12345: SUCCESS (14.5s)
✓ dv_67890: SUCCESS (15.2s)
✓ dv_abcde: SUCCESS (16.1s)

============================================================
BATCH PROCESSING SUMMARY
============================================================
Total data views: 3
Successful: 3
Failed: 0
Success rate: 100.0%
Throughput: 9.7 data views per minute
============================================================
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (SDR generated, validation passed, or diff found no changes) |
| 1 | General error (authentication, data view not found, API/processing/file I/O failures) |
| 2 | Policy threshold exceeded (diff changes found, quality gate failed, or org governance threshold exceeded) |
| 3 | Diff warning threshold exceeded (`--warn-threshold`) |

> **Note:**
> - Exit code 2 is intentionally used for CI policy failures that are not runtime crashes.
> - Exit code 1 takes precedence if processing fails (even if a policy threshold is also exceeded).

## Shell Tab-Completion

Enable tab-completion for all CLI options using the `argcomplete` package.

**Quick setup (v3.3.4+):**

```bash
cja_auto_sdr --completion bash >> ~/.bashrc
cja_auto_sdr --completion zsh >> ~/.zshrc
cja_auto_sdr --completion fish > ~/.config/fish/completions/cja_auto_sdr.fish
```

### Installation

```bash
# Install the completion optional dependency (from project root)
pip install .[completion]

# Or with uv
uv add argcomplete

# Or install argcomplete directly
pip install argcomplete
```

### Activation

**Bash (one-time setup):**

```bash
# Add to ~/.bashrc
eval "$(register-python-argcomplete cja_auto_sdr)"
```

**Zsh (one-time setup):**

```bash
# Add to ~/.zshrc
autoload -U bashcompinit
bashcompinit
eval "$(register-python-argcomplete cja_auto_sdr)"
```

**Global activation (all argcomplete-enabled scripts):**

```bash
# Bash
activate-global-python-argcomplete

# Then add to ~/.bashrc:
source /etc/bash_completion.d/python-argcomplete
```

### Usage

After activation, press Tab to auto-complete:

```bash
# Complete flags
cja_auto_sdr --<TAB><TAB>
--batch  --config-file  --dry-run  --format  --help  ...

# Complete flag values
cja_auto_sdr --format <TAB><TAB>
excel  csv  json  html  markdown  all

cja_auto_sdr --log-level <TAB><TAB>
DEBUG  INFO  WARNING  ERROR  CRITICAL
```

## See Also

- [Quick Reference Card](QUICK_REFERENCE.md) - Single-page command cheat sheet
- [Shell Completion Guide](SHELL_COMPLETION.md) - Enable tab-completion for bash/zsh
- [Configuration Guide](CONFIGURATION.md) - config.json, environment variables, validation rules
- [Installation Guide](INSTALLATION.md)
- [Batch Processing Guide](BATCH_PROCESSING_GUIDE.md)
- [Output Formats](OUTPUT_FORMATS.md)
- [Performance Guide](PERFORMANCE.md)
- [Data View Comparison Guide](DIFF_COMPARISON.md)
- [Org-Wide Analysis Guide](ORG_WIDE_ANALYSIS.md) - Cross-data-view component analysis
- [Git Integration Guide](GIT_INTEGRATION.md)
- [Derived Field Inventory](DERIVED_FIELDS_INVENTORY.md) - Derived field analysis
- [Calculated Metrics Inventory](CALCULATED_METRICS_INVENTORY.md) - Calculated metrics analysis
