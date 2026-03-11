# Org-Wide Component Analysis Guide

> **New in v3.2.0** - Comprehensive org-wide analysis with governance features

Analyze component usage patterns across all data views in your CJA organization. This feature provides governance insights, identifies duplication, and helps standardize your analytics implementation.

## Overview

The org-wide analysis feature allows you to:
- **Analyze all data views** in your organization simultaneously
- **Identify core components** used across multiple data views
- **Detect duplicate data views** using Jaccard similarity
- **Generate governance recommendations** based on usage patterns
- **Export reports** in all supported output formats (console, JSON, Excel, HTML, Markdown, CSV)
- **Track trends** by comparing reports over time
- **Audit naming conventions** for consistency
- **Group data views** into clusters based on component similarity
- **Integrate with CI/CD** using governance threshold exit codes

> **Windows Users:** Most commands in this guide work identically on all platforms. Where shell-specific
> syntax is needed (scripts, date formatting, piping), both **bash** (macOS/Linux) and **PowerShell**
> (Windows) variants are shown. On Windows, use double quotes for extras installation:
> `uv pip install "cja-auto-sdr[clustering]"` instead of single quotes.

## Quick Start

```bash
# Basic org-wide report (console output)
cja_auto_sdr --org-report

# With filtering
cja_auto_sdr --org-report --filter "Prod.*" --exclude "Test|Dev"

# Export to Excel
cja_auto_sdr --org-report --format excel

# Export all formats
cja_auto_sdr --org-report --format all
```

## Quick Health Check

For a fast overview without detailed analysis:

```bash
# Fastest: Quick stats only (no similarity, no clustering)
cja_auto_sdr --org-report --org-stats

# Fast with sampling: Analyze 10 random data views
cja_auto_sdr --org-report --org-stats --sample 10

# Fast with limit: Analyze first 10 data views
cja_auto_sdr --org-report --org-stats --limit 10
```

**Performance comparison (100 DVs):**
| Mode | Time |
|------|------|
| Full analysis | ~2 min |
| `--org-stats` | ~30 sec |
| `--org-stats --sample 10` | ~5 sec |

## How It Works

### 1. Data View Discovery

The analyzer fetches all accessible data views from your CJA organization, applying optional filters:

```bash
# Include only data views matching pattern
cja_auto_sdr --org-report --filter "Production.*"

# Exclude data views matching pattern
cja_auto_sdr --org-report --exclude "Test|Sandbox|Dev"

# Limit to first N data views (useful for testing)
cja_auto_sdr --org-report --limit 10
```

### 2. Component Indexing

For each data view, the analyzer fetches all metrics and dimensions, building a global index that tracks:
- **Component ID** - Unique identifier (e.g., `metrics/pageviews`)
- **Component Type** - Metric or Dimension
- **Name** - Display name (with `--include-names`)
- **Data Views** - Which data views contain this component

### 3. Distribution Classification

Components are classified into four buckets based on how many data views contain them:

| Bucket | Criteria | Description |
|--------|----------|-------------|
| **Core** | >= 50% of DVs | Foundation components used organization-wide |
| **Common** | 25-49% of DVs | Shared across multiple teams/use cases |
| **Limited** | 2+ DVs, < 25% | Used in a subset of data views |
| **Isolated** | 1 DV only | Unique to a single data view |

Customize the core threshold:

```bash
# Components in 70%+ of data views are "core"
cja_auto_sdr --org-report --core-threshold 0.7

# Or use absolute count: components in 5+ DVs are "core"
cja_auto_sdr --org-report --core-min-count 5
```

### 4. Similarity Matrix

The analyzer computes pairwise Jaccard similarity between data views:

```
Jaccard Similarity = |Components in Both| / |Components in Either|
```

This identifies:
- **Duplicate data views** (90%+ similarity)
- **Prod/staging pairs** (high overlap with minor differences)
- **Related data views** that share common components

Note: For governance checks, pairs with >= 90% similarity are always included.
If `--overlap-threshold` is set above 0.9, the effective similarity threshold is capped at 0.9
and reports will note the configured vs. effective threshold.

> ⚠️ **Performance Note:** Similarity calculation has **O(n²) complexity** - for N data views,
> it computes N×(N-1)/2 pairwise comparisons. This is fast for small orgs but scales quadratically:
>
> | Data Views | Comparisons | Approximate Time |
> |------------|-------------|------------------|
> | 50 | 1,225 | ~1 second |
> | 100 | 4,950 | ~4 seconds |
> | 250 | 31,125 | ~25 seconds |
> | 500 | 124,750 | ~2 minutes |
>
> The default guardrail (`--similarity-max-dvs 250`) automatically skips similarity when
> data views exceed this threshold. Use `--force-similarity` to override, or `--skip-similarity`
> to disable entirely.

```bash
# Flag pairs with 90%+ similarity (default: 80%)
cja_auto_sdr --org-report --overlap-threshold 0.9

# Skip similarity calculation for large orgs
cja_auto_sdr --org-report --skip-similarity
```

> **Tip:** To check the exit code after running with `--fail-on-threshold`:
> - **bash:** `echo $?`
> - **PowerShell:** `echo $LASTEXITCODE`

### 5. Recommendations

Based on the analysis, the tool generates governance recommendations:

| Type | Severity | Description |
|------|----------|-------------|
| `review_isolated` | Medium | Data views with many unique components |
| `review_overlap` | High | Near-duplicate data view pairs (90%+ similarity) |
| `standardization_opportunity` | Low | Components in 70-99% of DVs (near-universal) |
| `fetch_errors` | High | Data views that couldn't be analyzed |
| `high_derived_ratio` | Low | Data views with >50% derived components |
| `stale_data_view` | Low | Data views not modified in 6+ months |
| `missing_descriptions` | Low | Data views lacking descriptions |

## Command Reference

### Basic Options

| Option | Description |
|--------|-------------|
| `--org-report` | Enable org-wide analysis mode |
| `--filter PATTERN` | Include data views matching regex |
| `--exclude PATTERN` | Exclude data views matching regex |
| `--limit N` | Analyze only first N data views |
| `--include-names` | Fetch and display component names |
| `--quiet` | Suppress progress output |

### Threshold Options

| Option | Default | Description |
|--------|---------|-------------|
| `--core-threshold` | 0.5 | Fraction of DVs for "core" classification |
| `--core-min-count` | - | Absolute count for "core" (overrides threshold) |
| `--overlap-threshold` | 0.8 | Minimum similarity to flag as "high overlap" (capped at 0.9 for governance checks) |

### Component Type Breakdown

| Option | Default | Description |
|--------|---------|-------------|
| `--no-component-types` | Off | Disable standard/derived field breakdown |

When enabled (default), tracks:
- **Standard metrics/dimensions** - Native XDM-based components
- **Derived metrics/dimensions** - Components created via derived fields

```bash
# View component type distribution
cja_auto_sdr --org-report --format excel
# Columns: Standard Metrics, Derived Metrics, Standard Dimensions, Derived Dimensions
```

### Metadata Options

| Option | Description |
|--------|-------------|
| `--include-metadata` | Include owner, dates, descriptions for each data view |

When enabled:
- Shows data view owner name and ID
- Shows creation and modification dates
- Tracks description completeness
- Generates `stale_data_view` and `missing_descriptions` recommendations

```bash
# Include metadata in report
cja_auto_sdr --org-report --include-metadata --format excel
```

### Drift Detection

| Option | Description |
|--------|-------------|
| `--include-drift` | Show exact component differences between similar DV pairs |

When enabled, high-overlap pairs include:
- Components only in DV1
- Components only in DV2
- Component names (when `--include-names` also used)

```bash
# Detailed drift analysis between similar data views
cja_auto_sdr --org-report --include-drift --include-names --format excel
```

### Sampling Options

For very large organizations, use sampling to analyze a representative subset:

| Option | Description |
|--------|-------------|
| `--sample N` | Randomly sample N data views |
| `--sample-seed SEED` | Random seed for reproducible sampling |
| `--sample-stratified` | Stratify sample by data view name prefix |

```bash
# Analyze a random sample of 20 data views
cja_auto_sdr --org-report --sample 20 --sample-seed 42

# Stratified sampling (proportional by name prefix)
cja_auto_sdr --org-report --sample 30 --sample-stratified
```

### Caching Options

Cache data view components for faster repeat runs:

| Option | Default | Description |
|--------|---------|-------------|
| `--use-cache` | Off | Enable caching of fetched components |
| `--cache-max-age HOURS` | 24 | Maximum cache age before refresh |
| `--refresh-cache` | Off | Clear cache and fetch fresh data |

```bash
# First run - fetches and caches
cja_auto_sdr --org-report --use-cache

# Second run - uses cache (much faster)
cja_auto_sdr --org-report --use-cache

# Force refresh
cja_auto_sdr --org-report --use-cache --refresh-cache
```

> **Note:** Smart cache validation (`--validate-cache`) compares modification
> timestamps. If the CJA API doesn't return a modification timestamp for a
> data view, the cached entry is treated as valid (optimistic caching). Use
> `--refresh-cache` to force a full refresh when in doubt.

Cache is stored in:
- **macOS/Linux:** `~/.cja_auto_sdr/cache/org_report_cache.json`
- **Windows:** `%USERPROFILE%\.cja_auto_sdr\cache\org_report_cache.json`

### Clustering Options

Group related data views into clusters using hierarchical clustering:

| Option | Default | Description |
|--------|---------|-------------|
| `--cluster` | Off | Enable hierarchical clustering |
| `--cluster-method METHOD` | average | Linkage method: `average` (recommended) or `complete` |

```bash
# Identify data view families
cja_auto_sdr --org-report --cluster --format excel

# Use complete linkage for tighter clusters
cja_auto_sdr --org-report --cluster --cluster-method complete
```

Generates a "Clusters" sheet showing:
- Cluster ID and inferred name
- Member data views
- Cohesion score (within-cluster similarity)

**Note:** Clustering requires the optional `scipy` dependency. Install with:

```bash
# macOS/Linux
uv pip install 'cja-auto-sdr[clustering]'

# Windows PowerShell
uv pip install "cja-auto-sdr[clustering]"
```

If `scipy` is not installed and `--cluster` is used, a warning is logged and clustering is skipped gracefully.

**Why `average` is recommended:** The clustering algorithm uses Jaccard distances (1 - similarity) to measure how different data views are. The `average` linkage method works correctly with any distance metric. The `complete` method is also valid and produces tighter, more distinct clusters.

### Performance Options

| Option | Description |
|--------|-------------|
| `--skip-similarity` | Skip O(n²) pairwise similarity calculation |
| `--similarity-max-dvs N` | Guardrail to skip similarity when data views exceed N (default: 250) |
| `--force-similarity` | Force similarity even if guardrails would skip it |

### Concurrency Options

| Option | Description |
|--------|-------------|
| `--org-shared-client` | Use a single shared cjapy client across threads (faster, but may be unsafe if cjapy is not thread-safe) |

### Output Options

| Option | Description |
|--------|-------------|
| `--format FORMAT` | Output format: `console`, `json`, `excel`, `markdown`, `html`, `csv`, `all`, or aliases |
| `--output PATH` | Specific output file path |
| `--output-dir DIR` | Output directory (default: current) |

**Format Aliases:**
| Alias | Expands To | Use Case |
|-------|------------|----------|
| `reports` | excel + markdown | Documentation and sharing |
| `data` | csv + json | Data pipelines and analysis |
| `ci` | json + markdown | CI/CD integration |

```bash
# Generate Excel + Markdown for documentation
cja_auto_sdr --org-report --format reports

# Generate CSV + JSON for data pipelines
cja_auto_sdr --org-report --format data
```

## Output Formats

### Console (Default)

ASCII-formatted report with distribution bars:

```
==============================================================================================================
ORG-WIDE COMPONENT ANALYSIS REPORT: ABC123DEF456GHI789@AdobeOrg
==============================================================================================================
Generated: 2026-02-01T10:30:00
Data Views Analyzed: 12 / 12
Analysis Duration: 8.45s

----------------------------------------------------------------------
DISTRIBUTION
----------------------------------------------------------------------
Metrics by data view coverage:
  Core:     ████████░░░░░░░░░░░░░░░░░░░░░░  27% (45)
  Common:   ██████░░░░░░░░░░░░░░░░░░░░░░░░  19% (32)
  Limited:  ████░░░░░░░░░░░░░░░░░░░░░░░░░░  14% (24)
  Isolated: ████████████░░░░░░░░░░░░░░░░░░  40% (67)
```

### JSON

Structured JSON for programmatic processing:

```json
{
  "report_type": "org_analysis",
  "org_id": "ABC123DEF456GHI789@AdobeOrg",
  "summary": {
    "data_views_total": 12,
    "data_views_analyzed": 12,
    "total_unique_metrics": 168,
    "total_unique_dimensions": 94
  },
  "distribution": {
    "core": {"metrics_count": 45, "dimensions_count": 28},
    "common": {...},
    "limited": {...},
    "isolated": {...}
  },
  "component_index": {...},
  "similarity_pairs": [...],
  "recommendations": [...]
}
```

### Excel

Multi-sheet workbook with:
- **Summary** - Overview statistics
- **Data Views** - List of all analyzed data views
- **Core Components** - Components in 50%+ of data views
- **Isolated by DV** - Isolated component counts per data view
- **Similarity** - High-overlap pairs
- **Recommendations** - Actionable governance items

### Markdown

GitHub-flavored markdown with tables:

```markdown
# Org-Wide Component Analysis Report

## Summary
| Metric | Value |
|--------|-------|
| Data Views Analyzed | 12 / 12 |
| Total Unique Metrics | 168 |
...
```

### HTML

Styled HTML report with:
- Interactive statistics cards
- Progress bar visualizations
- Sortable tables
- Color-coded severity badges

### CSV

Multiple CSV files in a directory:
- `org_report_summary.csv`
- `org_report_data_views.csv`
- `org_report_components.csv`
- `org_report_distribution.csv`
- `org_report_similarity.csv`
- `org_report_recommendations.csv`

## Use Cases

### 1. Governance Audit

Identify data view sprawl and standardization opportunities:

```bash
cja_auto_sdr --org-report --format excel --output-dir ./audit
```

Review the Excel report for:
- Data views with many isolated components (specialized or orphaned?)
- Near-duplicate pairs that could be consolidated
- Components used in 70-99% of DVs (candidates for standardization)

### 2. Pre-Migration Analysis

Before migrating or consolidating data views:

```bash
cja_auto_sdr --org-report --include-names --format json
```

The JSON output provides a complete component inventory for planning.

If you want to stream JSON to another tool, send it to stdout and pipe it:

```bash
# macOS/Linux
cja_auto_sdr --org-report --format json --output - | jq '.summary'

# Windows PowerShell
cja_auto_sdr --org-report --format json --output - | ConvertFrom-Json | Select-Object -ExpandProperty summary
```

### 3. Environment Validation

Verify prod/staging parity:

```bash
cja_auto_sdr --org-report --filter "Prod|Staging" --overlap-threshold 0.95
```

High-overlap pairs (>95%) indicate proper synchronization.

### 4. Quick Health Check

Fast summary without detailed analysis:

```bash
cja_auto_sdr --org-report --skip-similarity --org-summary
```

### 5. CI/CD Integration

Automated governance checks:

```bash
cja_auto_sdr --org-report --format json --quiet --output ./reports/org-audit.json
```

## Performance Considerations

### Large Organizations

For organizations with many data views (50+):

1. **Use `--skip-similarity`** to avoid O(n²) pairwise comparison
2. **Use `--limit`** to test with a subset first
3. **Use filters** to focus on specific data view groups

```bash
# Analyze only production data views, skip similarity
cja_auto_sdr --org-report --filter "^Prod" --skip-similarity
```

### API Rate Limits

The analyzer fetches components in parallel (up to 10 concurrent requests). For very large orgs, you may see rate limiting. The tool handles this gracefully with automatic retries.

### Memory Usage

Component indices are held in memory. For orgs with 100+ data views and 10,000+ unique components, ensure adequate memory (4GB+ recommended).

**Memory controls:**

```bash
# Warn if component index exceeds 100MB (default)
cja_auto_sdr --org-report --memory-warning 100

# Abort if component index exceeds 500MB
cja_auto_sdr --org-report --memory-limit 500

# Disable memory warning
cja_auto_sdr --org-report --memory-warning 0
```

For very large organizations (1000+ DVs), consider:
1. Use `--sample` to analyze a representative subset
2. Use `--filter` to focus on specific data view groups
3. Use `--limit` to cap the number of data views
4. Use `--memory-limit` to abort before exhausting memory

## Troubleshooting

### "No data views found matching criteria"

- Check your filter/exclude patterns (they're case-insensitive regex)
- Verify API credentials have access to data views
- Run `cja_auto_sdr --list-dataviews` to see available data views

### Some data views show ERROR

- Check the `fetch_errors` recommendation for details
- Verify permissions for those specific data views
- Data views may be in an invalid state

### Similarity matrix is slow

For N data views, similarity requires N×(N-1)/2 comparisons. With 50 DVs, that's 1,225 comparisons. Use `--skip-similarity` for faster results.

### "Another --org-report is already running"

The tool prevents concurrent `--org-report` runs for the same organization to avoid:
- Duplicate API calls and wasted resources
- Rate limit exhaustion
- Inconsistent results

If you see this error:
1. Check if another terminal/process is running an org-report
2. Wait for the existing run to complete
3. If the previous run crashed, the lock is reclaimed automatically:
   - Default backend (`fcntl` on POSIX): lock is released by the OS when the process exits
   - If `flock` is unsupported on the lock filesystem at runtime, lock handling automatically falls back to the lease backend
   - Fallback backend (`lease`): same-host dead PIDs are reclaimed immediately; otherwise stale leases expire based on threshold

The lock file is stored in:
- **macOS/Linux:** `~/.cja_auto_sdr/locks/`
- **Windows:** `%USERPROFILE%\.cja_auto_sdr\locks\`

Optional backend override (advanced/debug):

```bash
# auto (default), fcntl, or lease
export CJA_LOCK_BACKEND=auto
```

To force bypass the lock (for testing only):
```bash
# Use skip_lock in your config (not recommended for production)
# The lock exists to protect against accidental concurrent runs
```

## Advanced Features

### Governance Exit Codes

Integrate org-report into CI/CD pipelines with threshold-based exit codes.

```bash
# Exit with code 2 if more than 5 high-similarity pairs exist
cja_auto_sdr --org-report --duplicate-threshold 5 --fail-on-threshold
echo $?              # bash: 0 = pass, 2 = threshold exceeded
$LASTEXITCODE        # PowerShell equivalent

# Exit with code 2 if isolated components exceed 30%
cja_auto_sdr --org-report --isolated-threshold 0.3 --fail-on-threshold

# Combine thresholds for comprehensive governance checks
cja_auto_sdr --org-report \
  --duplicate-threshold 3 \
  --isolated-threshold 0.4 \
  --fail-on-threshold \
  --format json --output governance-report.json
```

| Option | Description |
|--------|-------------|
| `--duplicate-threshold N` | Max allowed high-similarity pairs (>=90%) |
| `--isolated-threshold PERCENT` | Max isolated component percentage (0.0-1.0) |
| `--fail-on-threshold` | Enable exit code 2 when thresholds exceeded |

### Org Summary Stats Mode

Quick stats-only mode for fast health checks - skips similarity and clustering computation.

```bash
# Fast summary (no similarity matrix or clustering)
cja_auto_sdr --org-report --org-stats

# Output:
# ORG STATS: ABC123@AdobeOrg
# Data Views: 25 analyzed
# Components: 450 unique
#   Metrics:    280
#   Dimensions: 170
# Distribution:
#   Core:      85 (18.9%)
#   Common:   120 (26.7%)
#   Limited:   95 (21.1%)
#   Isolated: 150 (33.3%)
```

### Naming Convention Audit

Detect inconsistent naming patterns across components.

```bash
# Run naming audit
cja_auto_sdr --org-report --audit-naming

# Detects:
# - Mixed case styles (snake_case vs camelCase vs PascalCase)
# - Common prefix groupings
# - Stale patterns (test, old, temp, dates)
```

### Trending/Drift Report

Compare org-reports over time to detect changes.

```bash
# Save baseline
cja_auto_sdr --org-report --format json --output baseline.json

# Later, compare to baseline
cja_auto_sdr --org-report --compare-org-report baseline.json

# Shows:
# - Data views added/removed
# - Component count changes (↑ / ↓)
# - New high-similarity pairs
# - Resolved pairs
```

`--compare-org-report` expects a full-fidelity baseline. Pre-v3.4 JSON reports that do not include
snapshot-fidelity markers are treated as ineligible because the old format cannot distinguish full
similarity runs from `--skip-similarity`/`--org-stats` baselines reliably.

#### CI/CD Trending Example

Track changes between org-report runs with GitHub Actions:

```yaml
name: Weekly Governance Check
on:
  schedule:
    - cron: '0 9 * * 1'  # Every Monday 9 AM

jobs:
  governance:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Setup Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.14'

      - name: Install cja-auto-sdr
        run: pip install cja-auto-sdr

      - name: Download previous report
        uses: actions/download-artifact@v4
        with:
          name: org-report-baseline
          path: ./baseline/
        continue-on-error: true  # First run won't have baseline

      - name: Run org-report
        env:
          ORG_ID: ${{ secrets.CJA_ORG_ID }}
          CLIENT_ID: ${{ secrets.CJA_CLIENT_ID }}
          SECRET: ${{ secrets.CJA_CLIENT_SECRET }}
          SCOPES: ${{ secrets.CJA_SCOPES }}
        run: |
          cja_auto_sdr --org-report --format json --output current.json

      - name: Compare with baseline
        if: hashFiles('baseline/org-report.json') != ''
        run: |
          cja_auto_sdr --org-report --compare-org-report baseline/org-report.json

      - name: Upload as new baseline
        uses: actions/upload-artifact@v4
        with:
          name: org-report-baseline
          path: current.json
```

#### Local Trending Example

**macOS/Linux (bash):**
```bash
# Save baseline with date
cja_auto_sdr --org-report --format json --output baseline-$(date +%Y%m%d).json

# Later, compare to baseline
cja_auto_sdr --org-report --compare-org-report baseline-20260115.json
```

**Windows (PowerShell):**
```powershell
# Save baseline with date
cja_auto_sdr --org-report --format json --output "baseline-$(Get-Date -Format yyyyMMdd).json"

# Later, compare to baseline
cja_auto_sdr --org-report --compare-org-report baseline-20260115.json
```

### Owner/Team Summary

Group statistics by data view owner.

```bash
# Requires --include-metadata
cja_auto_sdr --org-report --include-metadata --owner-summary

# Shows:
# Owner              DVs    Metrics    Dimensions    Avg/DV
# Alice              5      450        280           146.0
# Bob                3      210        150           120.0
# Unknown            2       80         50            65.0
```

### Stale Component Heuristics

Flag components with cleanup candidate naming patterns.

```bash
cja_auto_sdr --org-report --flag-stale

# Detects:
# - Stale keywords: test, old, temp, backup, copy, deprecated
# - Version suffixes: _v1, _v2
# - Date patterns: _20240101, _2024-01-01
```

### Complete Governance CI/CD Example

**macOS/Linux (bash):**
```bash
#!/bin/bash
# governance-check.sh

cja_auto_sdr --org-report \
  --duplicate-threshold 5 \
  --isolated-threshold 0.35 \
  --fail-on-threshold \
  --audit-naming \
  --flag-stale \
  --format json \
  --output governance-report.json \
  --quiet

EXIT_CODE=$?

if [ $EXIT_CODE -eq 2 ]; then
  echo "GOVERNANCE CHECK FAILED: Thresholds exceeded"
  exit 1
elif [ $EXIT_CODE -ne 0 ]; then
  echo "GOVERNANCE CHECK ERROR"
  exit 1
fi

echo "GOVERNANCE CHECK PASSED"
```

**Windows (PowerShell):**
```powershell
# governance-check.ps1

cja_auto_sdr --org-report `
  --duplicate-threshold 5 `
  --isolated-threshold 0.35 `
  --fail-on-threshold `
  --audit-naming `
  --flag-stale `
  --format json `
  --output governance-report.json `
  --quiet

if ($LASTEXITCODE -eq 2) {
    Write-Host "GOVERNANCE CHECK FAILED: Thresholds exceeded"
    exit 1
} elseif ($LASTEXITCODE -ne 0) {
    Write-Host "GOVERNANCE CHECK ERROR"
    exit 1
}

Write-Host "GOVERNANCE CHECK PASSED"
```

### Temporal Trending

Track how your org's data views and components change over time using cached org-report snapshots.

```bash
# Show trending across last 10 cached snapshots (default window)
cja_auto_sdr --org-report --trending-window

# Show trending across last 5 snapshots in JSON format
cja_auto_sdr --org-report --trending-window 5 --format json

# Combine trending with comparison for full context
cja_auto_sdr --org-report --trending-window 10 --compare-org-report ./baseline.json

# List cached org-report snapshots used for trending
cja_auto_sdr --list-org-report-snapshots

# Inspect one cached org-report snapshot
cja_auto_sdr --inspect-org-report-snapshot ./org_report_test_org_AdobeOrg_2026_03_01T00_00_00Z.json

# Prune old cached org-report snapshots
cja_auto_sdr --prune-org-report-snapshots --org-report-keep-last 10
```

Trending output includes:
- **Snapshot table**: data view count, component count, core/isolated counts, and high-similarity pairs across each cached run.
- **Deltas**: period-over-period changes between consecutive snapshots.
- **Drift scores**: per-data-view weighted score (0.0-1.0) highlighting which data views changed most by accumulating period-over-period churn across the full window, based on component count change (40%), core/isolated ratio shift (20%), similarity change (20%), and presence change (20%).

Trending renders in all 6 output formats (console, JSON, Excel, Markdown, HTML, CSV).
The persisted history lives under `~/.cja_auto_sdr/cache/org_report_snapshots/<ORG_ID>/`. When `--trending-window`
is used, the current run is saved there even for console output, and older entries are pruned automatically to keep
the cache bounded.

If you created local trending history with early v3.4.0 builds before snapshot-fidelity hardening landed and later
see suspicious deltas, prune that cache and rebuild it from fresh full-fidelity org reports. Legacy markerless
snapshots are now treated as ineligible rather than guessed as complete. Use
`cja_auto_sdr --inspect-org-report-snapshot <FILE> --format json` to review `history_eligible` and
`history_exclusion_reason` for current snapshots, and `cja_auto_sdr --prune-org-report-snapshots ...` to remove
older entries.

## Related Documentation

- [CLI Reference](CLI_REFERENCE.md) - Complete command-line options
- [Output Formats](OUTPUT_FORMATS.md) - Format-specific details
- [Configuration Guide](CONFIGURATION.md) - Credential and profile setup
- [Batch Processing Guide](BATCH_PROCESSING_GUIDE.md) - Processing multiple data views
- [Use Cases & Best Practices](USE_CASES.md) - Governance workflows and automation examples
- [Quick Reference](QUICK_REFERENCE.md) - Single-page command cheat sheet
- [Troubleshooting](TROUBLESHOOTING.md) - Common issues and solutions
