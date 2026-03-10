# Quick Reference Card

Single-page command cheat sheet for CJA SDR Generator v3.4.0.

## Four Main Modes

| Mode | Purpose | Output |
|------|---------|--------|
| **SDR Generation** | Document a data view's dimensions, metrics, and calculated metrics | Excel (default), CSV, JSON, HTML, Markdown |
| **Diff Comparison** | Compare two data views or snapshots to identify changes | Console (default), Excel, CSV, JSON, HTML, Markdown |
| **Org-Wide Analysis** | Analyze component usage across all data views in an organization | Console (default), Excel, CSV, JSON, HTML, Markdown |
| **Discovery** | List data views, connections, and datasets in your CJA org | Console (default), CSV, JSON |
| **Discovery Inspection** | Drill into a data view's metrics, dimensions, segments, and calculated metrics | Console (default), CSV, JSON |

**SDR Generation** creates a Solution Design Reference—a comprehensive inventory of all components in a data view. Use this for documentation, audits, and onboarding.

**Diff Comparison** identifies what changed between two data views or between a current state and a saved snapshot. Use this for change tracking, QA validation, and migration verification.

**Org-Wide Analysis** examines all accessible data views to identify core components, detect duplicates, and provide governance insights. Use this for audits, standardization, and understanding your analytics landscape.

**Discovery** lists the CJA infrastructure: data views, connections, and their backing datasets. Use this for onboarding, infrastructure audits, and understanding the data pipeline before generating SDRs.

**Discovery Inspection** drills into a single data view's components without generating a full SDR. Use this for quick audits, pre-SDR exploration, and verifying component availability.

## Running Commands

You have three equivalent options:

| Method | Command | Notes |
|--------|---------|-------|
| **uv run** | `uv run cja_auto_sdr ...` | Works immediately on macOS/Linux, may have issues on Windows |
| **Activated venv** | `cja_auto_sdr ...` | After activating: `source .venv/bin/activate` (Unix) or `.venv\Scripts\activate` (Windows) |
| **Direct script** | `cja_auto_sdr ...` | Most reliable on Windows |

This guide uses `uv run`. Windows users should substitute with `cja_auto_sdr`. The command examples below omit the prefix for brevity.

## Interactive Mode (Recommended for New Users)

```bash
# Launch interactive mode - walks through all options step by step
cja_auto_sdr --interactive
# or
cja_auto_sdr -i
```

Interactive mode guides you through:
1. **Data View Selection** - Shows list of accessible data views
2. **Output Format** - Excel, JSON, CSV, HTML, Markdown, or all
3. **Inventory Options** - Segments, calculated metrics, derived fields

## Essential Commands (SDR Generation)

```bash
# Generate SDR for a single data view
cja_auto_sdr dv_12345

# Generate and open file immediately
cja_auto_sdr dv_12345 --open

# Process multiple data views in parallel
cja_auto_sdr dv_12345 dv_67890 dv_abcde

# Use data view names instead of IDs
cja_auto_sdr "Production Analytics"

# Quick stats (no full report)
cja_auto_sdr dv_12345 --stats

# List all accessible data views
cja_auto_sdr --list-dataviews

# List data views as JSON (for scripting)
cja_auto_sdr --list-dataviews --format json

# List all connections with their datasets
cja_auto_sdr --list-connections

# List all data views with their backing datasets
cja_auto_sdr --list-datasets

# Filter, exclude, sort, and limit discovery results
cja_auto_sdr --list-dataviews --filter "Prod.*"
cja_auto_sdr --list-dataviews --exclude "Test|Dev" --sort name
cja_auto_sdr --list-connections --limit 10 --sort=-id

# Interactively select data views from a list
cja_auto_sdr --interactive

# Validate config without processing
cja_auto_sdr --validate-config

# Fail on quality issues at or above HIGH severity
cja_auto_sdr dv_12345 --fail-on-quality HIGH

# Generate standalone quality report only (JSON or CSV)
cja_auto_sdr dv_12345 --quality-report json --output quality_issues.json
```

> **Quality constraints:** `--fail-on-quality` and `--quality-report` are SDR-only and cannot be used with `--skip-validation`.

## Discovery Inspection Commands

```bash
# Inspect a data view (metadata, component counts, owner, dates)
cja_auto_sdr --describe-dataview dv_abc123

# Browse metrics (with filter)
cja_auto_sdr --list-metrics dv_abc123 --filter revenue

# Export dimensions to CSV
cja_auto_sdr --list-dimensions dv_abc123 --format csv --output dims.csv

# List segments as JSON
cja_auto_sdr --list-segments dv_abc123 --format json

# Find calculated metrics by pattern
cja_auto_sdr --list-calculated-metrics dv_abc123 --filter percent

# Sort and limit results
cja_auto_sdr --list-metrics dv_abc123 --sort name --limit 20

# Pipe to jq for scripting
cja_auto_sdr --list-dimensions dv_abc123 --format json --output - | jq '.[].name'

# Use a data view name instead of ID
cja_auto_sdr --describe-dataview "Production Web Data"

# Name with fuzzy matching
cja_auto_sdr --list-metrics "Prod Web" --name-match fuzzy
```

## Diff Comparison Commands (Diff Mode)

```bash
# Compare two data views
cja_auto_sdr --diff dv_12345 dv_67890

# Compare using names
cja_auto_sdr --diff "Production" "Staging"

# Save snapshot for later comparison
cja_auto_sdr dv_12345 --snapshot ./baseline.json

# Compare current state to snapshot
cja_auto_sdr dv_12345 --diff-snapshot ./baseline.json

# Compare against most recent snapshot (auto-finds it)
cja_auto_sdr dv_12345 --compare-with-prev

# Compare two snapshots (no API calls)
cja_auto_sdr --compare-snapshots ./old.json ./new.json

# Auto-save snapshots during diff
cja_auto_sdr --diff dv_12345 dv_67890 --auto-snapshot

# Show only changes (hide unchanged)
cja_auto_sdr --diff dv_12345 dv_67890 --changes-only

# Custom labels in diff output
cja_auto_sdr --diff dv_12345 dv_67890 --diff-labels "Before" "After"

# List saved snapshots
cja_auto_sdr --list-snapshots

# List snapshots for a specific data view
cja_auto_sdr --list-snapshots dv_12345

# Prune snapshots without running diff
cja_auto_sdr --prune-snapshots --keep-last 20
cja_auto_sdr --prune-snapshots --keep-since 30d
```

## Org-Wide Analysis Commands

> **Windows Users:** All `cja_auto_sdr` commands below work identically on Windows.
> For clustering extras, use double quotes: `uv pip install "cja-auto-sdr[clustering]"`.

```bash
# Analyze all data views in organization (console output)
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

# Custom thresholds
cja_auto_sdr --org-report --core-threshold 0.7 --overlap-threshold 0.9

# Export to Excel
cja_auto_sdr --org-report --format excel

# Export all formats
cja_auto_sdr --org-report --format all --output-dir ./reports

# Quick stats mode (fast overview, no similarity/clustering)
cja_auto_sdr --org-report --org-stats

# Quick health check with sampling
cja_auto_sdr --org-report --org-stats --sample 10
```

### Advanced Org-Wide Options

```bash
# --- Clustering & Similarity ---
# Requires: uv pip install 'cja-auto-sdr[clustering]'  (macOS/Linux)
#           uv pip install "cja-auto-sdr[clustering]"   (Windows PowerShell)

# Cluster similar data views into families
cja_auto_sdr --org-report --cluster

# Cluster with specific method (average recommended, complete also valid)
cja_auto_sdr --org-report --cluster --cluster-method complete

# --- Caching (for large orgs) ---
# Use cached data (refresh if stale)
cja_auto_sdr --org-report --use-cache

# Force cache refresh
cja_auto_sdr --org-report --use-cache --refresh-cache

# Custom cache max age (hours, default: 24)
cja_auto_sdr --org-report --use-cache --cache-max-age 48

# --- Sampling (for very large orgs) ---
# Random sample 50 data views
cja_auto_sdr --org-report --sample 50

# Reproducible sample with seed
cja_auto_sdr --org-report --sample 50 --sample-seed 42

# Stratified sampling by data view name prefix
cja_auto_sdr --org-report --sample 50 --sample-stratified

# --- Trending & Comparison ---
# Show trending across last 10 cached snapshots (default)
cja_auto_sdr --org-report --trending-window

# Show trending across last 5 cached snapshots
cja_auto_sdr --org-report --trending-window 5 --format json

# Compare against previous org report
cja_auto_sdr --org-report --compare-org-report ./previous.json

# List cached org-report snapshots
cja_auto_sdr --list-org-report-snapshots

# Inspect one cached org-report snapshot
cja_auto_sdr --inspect-org-report-snapshot ./org_report_test_org_AdobeOrg_2026_03_01T00_00_00Z.json

# Prune cached org-report snapshots
cja_auto_sdr --prune-org-report-snapshots --org-report-keep-last 10

# Review snapshot history eligibility metadata before pruning
cja_auto_sdr --inspect-org-report-snapshot ./org_report_test_org_AdobeOrg_2026_03_01T00_00_00Z.json --format json

# --- Naming Audit ---
# Audit naming conventions
cja_auto_sdr --org-report --audit-naming

# Flag potentially stale components
cja_auto_sdr --org-report --flag-stale

# --- Governance & CI/CD ---
# CI/CD with governance thresholds
cja_auto_sdr --org-report --fail-on-threshold

# Custom thresholds (duplicate-threshold is max allowed high-similarity pairs as int)
cja_auto_sdr --org-report --fail-on-threshold \
  --duplicate-threshold 5 \
  --isolated-threshold 0.25

# --- Component Types & Metadata ---
# Disable component type breakdown
cja_auto_sdr --org-report --no-component-types

# Include owner/team summary
cja_auto_sdr --org-report --owner-summary

# Include metadata in output
cja_auto_sdr --org-report --include-metadata
```

## Profile Management (Multi-Org)

```bash
# Create a profile for each organization
cja_auto_sdr --profile-add client-a
cja_auto_sdr --profile-add client-b

# List all profiles (shows org_id from each profile config)
cja_auto_sdr --profile-list

# Use a specific profile
cja_auto_sdr --profile client-a --list-dataviews
cja_auto_sdr -p client-b "Main Data View" --format excel

# Test profile connectivity
cja_auto_sdr --profile-test client-a

# Import a profile non-interactively from JSON or .env file
cja_auto_sdr --profile-import client-c ./client-c.env
cja_auto_sdr --profile-import client-c ./client-c.json --profile-overwrite

# Set default profile
export CJA_PROFILE=client-a
cja_auto_sdr --list-dataviews  # Uses client-a
```

## Common Options

| Option | Purpose | Mode |
|--------|---------|------|
| `-V, --version` | Show program version and exit | All modes |
| `--profile NAME`, `-p` | Use named profile from `~/.cja/orgs/` | All modes |
| `--output-dir PATH` | Save output to specific directory | All modes |
| `--output PATH` | Output file path; use `-` for stdout (JSON/CSV) | All modes |
| `--format FORMAT` | Output format (see note below) | All modes |
| `--open` | Open generated file(s) in default application | SDR only |
| `--stats` | Quick statistics only (no full report) | SDR only |
| `--interactive`, `-i` | Interactively select data views from a numbered list | SDR only |
| `--config-file PATH` | Use custom config file (default: config.json) | All modes |
| `--log-level LEVEL` | Set logging: `DEBUG`, `INFO`, `WARNING`, `ERROR` | All modes |
| `--log-format FORMAT` | Log output: `text` (default) or `json` (structured) | All modes |
| `--workers N` | Parallel workers: `auto` (default) or `1-256` | SDR only |
| `--skip-validation` | Skip data quality checks (faster) | SDR only |
| `--metrics-only` | Include/compare metrics only (exclude dimensions) | SDR + Diff |
| `--dimensions-only` | Include/compare dimensions only (exclude metrics) | SDR + Diff |
| `--continue-on-error` | Don't stop on failures in batch mode | SDR only |
| `--fail-on-quality SEVERITY` | Exit with code 2 when quality issues at or above severity are found (requires validation; incompatible with `--skip-validation`) | SDR only |
| `--quality-report FORMAT` | Generate standalone quality issues report (`json` or `csv`) without SDR files (requires validation; incompatible with `--skip-validation`) | SDR only |
| `--allow-partial` | Opt-in exploratory SDR mode: continue on required component fetch or validation runtime failures (not supported with `--quality-report` or `--fail-on-quality`) | SDR only |
| `--quality-policy PATH` | Load quality defaults from JSON (`fail_on_quality`, `quality_report`, `max_issues`, `allow_partial`); explicit CLI flags take precedence | SDR only |
| `--run-summary-json PATH` | Write machine-readable run summary JSON; use `-` for stdout | All modes |
| `--name-match MODE` | Data view name matching: `exact` (default), `insensitive`, or `fuzzy` | All modes |
| `--include-segments` | Add segments inventory sheet/section | SDR + Snapshot Diff |
| `--include-derived` | Add derived field inventory sheet/section | SDR only |
| `--include-calculated` | Add calculated metrics inventory sheet/section | SDR + Snapshot Diff |
| `--include-all-inventory` | Enable all inventory options (smart mode: auto-excludes derived in snapshot/diff modes) | SDR + Snapshot Diff |
| `--inventory-only` | Output only inventory sheets (requires `--include-*`) | SDR only |
| `--inventory-summary` | Quick stats without full output (requires `--include-*`) | SDR only |

> **Note:** `--include-derived` is for SDR generation only. Derived fields are already included in the standard metrics/dimensions output, so changes are captured in the Metrics/Dimensions diff.
>
> **Snapshot/Diff inventory:** `--include-all-inventory` automatically enables `--include-segments` and `--include-calculated`, and excludes `--include-derived`.

### Fail-Closed Matrix

| Scenario | SDR (default) | SDR + `--allow-partial` | `--quality-report` | `--inventory-only` (no derived) | `--inventory-only --include-derived` |
|--------|----------------|--------------------------|--------------------|----------------------------------|--------------------------------------|
| Required component fetch failure (`metrics`/`dimensions`) | Block | Continue | Block | Non-blocking if section not emitted | Continue / block by default |
| Required components both empty | Block | Continue | Block | Non-blocking if section not emitted | Continue / block by default |
| Data-quality validation runtime failure | Block | Continue | Block | Validation skipped when not emitted | Validation skipped when not emitted |
| Invalid data view lookup payload | Block | Block | Block | Block | Block |

> Failed SDR results in `--run-summary-json` include stable `failure_code` / `failure_reason`, aggregate `failure_rollups`, additive `output_files` alongside compatibility `output_file`, and per-result `partial_output` / `partial_reasons` for `--allow-partial` runs.
>
> When `output_files` is present, `output_file` remains the primary artifact for backward compatibility and appears first in emitted artifact order.
>
> Run summary contract is currently `summary_version: "1.1"` and follows additive forward compatibility (ignore unknown keys).

### Diff-Specific Options

| Option | Purpose |
|--------|---------|
| `--changes-only` | Hide unchanged components, show only differences |
| `--compare-with-prev` | Compare against most recent snapshot in --snapshot-dir |
| `--list-snapshots` | List snapshots from `--snapshot-dir` (optionally filtered by data view ID) |
| `--prune-snapshots` | Apply retention policies (`--keep-last`/`--keep-since`) without running diff |
| `--diff-labels A B` | Custom labels for comparison columns (default: data view names) |
| `--auto-snapshot` | Automatically save snapshots during diff for future comparisons |
| `--auto-prune` | With `--auto-snapshot`, apply default retention (`--keep-last 20` + `--keep-since 30d`) only when both retention flags are omitted |
| `--keep-last N` | Retention: keep last N snapshots per data view (`0` keeps all) |
| `--keep-since PERIOD` | Date retention: delete snapshots older than `7d`, `2w`, `1m`, or days (`30`) |
| `--warn-threshold PERCENT` | Exit with code 3 if change % exceeds threshold (for CI/CD) |
| `--no-color` | Disable ANSI color codes in console output (global) |
| `--format-pr-comment` | Output in GitHub/GitLab PR comment format |

> **Retention precedence:** Explicit values are preserved in both forms: `--keep-last 0` / `--keep-last=0` and `--keep-since 90d` / `--keep-since=90d`.

### Format Support by Mode

| Format | SDR | Diff | Org-Report | Discovery | Description |
|--------|-----|------|------------|-----------|-------------|
| `excel` | ✅ (default) | ✅ | ✅ | ❌ | Excel workbook |
| `csv` | ✅ | ✅ | ✅ | ✅ | Comma-separated values |
| `json` | ✅ | ✅ | ✅ | ✅ | JSON for integrations |
| `html` | ✅ | ✅ | ✅ | ❌ | Browser-viewable |
| `markdown` | ✅ | ✅ | ✅ | ❌ | Documentation-ready |
| `console` | ❌ | ✅ (default) | ✅ (default) | ✅ (default) | Terminal output |
| `all` | ✅ | ✅ | ✅ | ❌ | All formats |

> Discovery column covers both discovery commands (`--list-dataviews`, etc.) and inspection commands (`--describe-dataview`, `--list-metrics`, etc.).

### Format Aliases (Shortcuts)

| Alias | Generates | Use Case |
|-------|-----------|----------|
| `reports` | excel + markdown | Documentation and sharing |
| `data` | csv + json | Data pipelines and integrations |
| `ci` | json + markdown | CI/CD logs and PR comments |

## Quick Recipes

```bash
# Fast processing (skip validation)
cja_auto_sdr dv_12345 --skip-validation

# Generate and open immediately
cja_auto_sdr dv_12345 --open

# Quick stats check before full generation
cja_auto_sdr dv_12345 --stats

# Stats as JSON to stdout (for scripting)
cja_auto_sdr dv_12345 --stats --output -

# List data views and pipe to jq
cja_auto_sdr --list-dataviews --output - | jq '.dataViews[].name'

# All output formats
cja_auto_sdr dv_12345 --format all

# Debug mode (verbose logging)
cja_auto_sdr dv_12345 --log-level DEBUG

# JSON logging (for Splunk, ELK, CloudWatch)
cja_auto_sdr dv_12345 --log-format json

# Dry run (validate only, no output)
cja_auto_sdr dv_12345 --dry-run

# Name matching modes
cja_auto_sdr "production" --name-match insensitive
cja_auto_sdr "Prodction" --name-match fuzzy

# Machine-readable run summary (all modes)
cja_auto_sdr dv_12345 --run-summary-json ./summary.json

# Quality policy from file
cja_auto_sdr dv_12345 --quality-policy ./quality_policy.json

# Batch with custom parallelism (default: auto-detect)
cja_auto_sdr dv_* --workers 8 --continue-on-error

# Production mode (minimal logging)
cja_auto_sdr dv_12345 --production

# Custom output directory (macOS/Linux)
cja_auto_sdr dv_12345 --output-dir ./reports/$(date +%Y%m%d)

# Custom output directory (Windows PowerShell)
cja_auto_sdr dv_12345 --output-dir ./reports/$(Get-Date -Format "yyyyMMdd")

# Include segments inventory
cja_auto_sdr dv_12345 --include-segments

# Include derived field inventory
cja_auto_sdr dv_12345 --include-derived

# Include calculated metrics inventory
cja_auto_sdr dv_12345 --include-calculated

# All three inventories (longhand)
cja_auto_sdr dv_12345 --include-segments --include-derived --include-calculated

# All inventories (shorthand - same as above)
cja_auto_sdr dv_12345 --include-all-inventory

# All inventories with inventory-only mode
cja_auto_sdr dv_12345 --include-all-inventory --inventory-only

# All inventories with quick summary
cja_auto_sdr dv_12345 --include-all-inventory --inventory-summary

# Inventory-only mode (no standard SDR sheets)
cja_auto_sdr dv_12345 --include-segments --inventory-only

# Multiple inventories only
cja_auto_sdr dv_12345 --include-segments --include-calculated --inventory-only

# Quick inventory stats (no file output)
cja_auto_sdr dv_12345 --include-segments --include-calculated --inventory-summary

# Save summary to JSON
cja_auto_sdr dv_12345 --include-segments --inventory-summary --format json

# --- Inventory Diff (same data view over time) ---

# Create snapshot with inventory (smart shorthand)
cja_auto_sdr dv_12345 --snapshot ./baseline.json --include-all-inventory
# Equivalent to: --include-calculated --include-segments

# Compare against snapshot with inventory (same behavior)
cja_auto_sdr dv_12345 --diff-snapshot ./baseline.json --include-all-inventory
```

## Environment Variables

```bash
# Credentials (override config file)
export ORG_ID=your_org_id@AdobeOrg
export CLIENT_ID=your_client_id
export SECRET=your_client_secret
export SCOPES="your_scopes_from_developer_console"

# Optional settings
export OUTPUT_DIR=./reports
export LOG_LEVEL=INFO

# Console color policy
export NO_COLOR=1            # disable ANSI colors globally
export FORCE_COLOR=1         # force-enable ANSI colors (FORCE_COLOR=0 disables)

# GitHub Actions job summary (usually set by GitHub Actions automatically)
export GITHUB_STEP_SUMMARY=/path/to/summary.md
```

## Setup Commands

```bash
# Generate sample config file
cja_auto_sdr --sample-config

# Validate configuration and API connection (5-step: environment,
# dependencies, credentials, API connectivity, output permissions)
cja_auto_sdr --validate-config

# Test specific data views without generating
cja_auto_sdr dv_12345 --dry-run

# Enable shell tab-completion
cja_auto_sdr --completion bash >> ~/.bashrc
cja_auto_sdr --completion zsh >> ~/.zshrc
```

See [CONFIGURATION.md](CONFIGURATION.md) for detailed setup of `config.json` and environment variables.

## Output Files

| Format | File Pattern | Description |
|--------|--------------|-------------|
| Excel | `CJA_DataView_<Name>_<ID>_SDR.xlsx` | Full report with Data Quality sheet |
| CSV | `CJA_DataView_<Name>_<ID>_SDR_csv/` | Directory with per-sheet CSV files |
| JSON | `CJA_DataView_<Name>_<ID>_SDR.json` | Machine-readable format |
| HTML | `CJA_DataView_<Name>_<ID>_SDR.html` | Browser-viewable report |
| Markdown | `CJA_DataView_<Name>_<ID>_SDR.md` | Documentation-ready format |

**Excel Sheet Order:**
1. Metadata
2. Data Quality
3. DataView Details
4. Metrics
5. Dimensions
6. Segments (if `--include-segments`)
7. Derived Fields (if `--include-derived`)
8. Calculated Metrics (if `--include-calculated`)

> **Note:** Inventory sheets appear at the end in CLI argument order. With `--inventory-only`, only sheets 6-8 are generated.

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (SDR/diff/org command completed) |
| 1 | Error (config, API, validation, or processing failure) |
| 2 | Policy threshold exceeded (diff changes found, `--fail-on-quality`, or `--fail-on-threshold`) |
| 3 | Diff warning threshold exceeded (`--warn-threshold`) |

> **CI/CD Tip:** Use exit code 2 gates with `--fail-on-quality` and/or `--fail-on-threshold`.
> If processing fails, exit code `1` takes precedence over policy exit code `2`.

## More Information

- Configuration: [CONFIGURATION.md](CONFIGURATION.md) - config.json, environment variables
- Full CLI docs: [CLI_REFERENCE.md](CLI_REFERENCE.md)
- Diff comparison: [DIFF_COMPARISON.md](DIFF_COMPARISON.md)
- Org-wide analysis: [ORG_WIDE_ANALYSIS.md](ORG_WIDE_ANALYSIS.md) - Cross-DV governance
- Troubleshooting: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- Batch processing: [BATCH_PROCESSING_GUIDE.md](BATCH_PROCESSING_GUIDE.md)
- Data quality: [DATA_QUALITY.md](DATA_QUALITY.md)
- Derived fields: [DERIVED_FIELDS_INVENTORY.md](DERIVED_FIELDS_INVENTORY.md)
- Calculated metrics: [CALCULATED_METRICS_INVENTORY.md](CALCULATED_METRICS_INVENTORY.md)
