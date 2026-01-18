# Data View Comparison Guide

Compare two CJA data views to identify differences in metrics, dimensions, and metadata. This feature enables environment validation, migration verification, and change tracking over time.

## Overview

The diff comparison feature allows you to:
- **Compare two live data views** (e.g., Production vs Staging)
- **Compare against a saved snapshot** (track changes over time)
- **Generate diff reports** in all supported output formats
- **Integrate with CI/CD pipelines** using exit codes

## How Comparison Works

### Component Matching

Components (metrics and dimensions) are matched between source and target data views using their **unique ID** (e.g., `metrics/pageviews`, `dimensions/page`). This ID-based matching ensures accurate comparison even when display names change.

### Change Detection

For each component, the comparison identifies one of four states:

| Change Type | Symbol | Description |
|-------------|--------|-------------|
| **Added** | `+` | Component exists in target but not in source |
| **Removed** | `-` | Component exists in source but not in target |
| **Modified** | `~` | Component exists in both, but field values differ |
| **Unchanged** | | Component exists in both with identical field values |

### Fields Compared

By default, the following fields are compared to detect modifications:

| Field | Description |
|-------|-------------|
| `name` | Display name of the component |
| `title` | Title/label shown in UI |
| `description` | Component description text |
| `type` | Data type (string, int, decimal, etc.) |
| `schemaPath` | Schema mapping path |

Use `--ignore-fields` to exclude specific fields from comparison (e.g., ignore description changes).

### Extended Fields

Use `--extended-fields` to include additional fields in comparison:

| Field | Description |
|-------|-------------|
| `hidden` | Whether the component is hidden |
| `hideFromReporting` | Hide from reporting UI |
| `precision` | Decimal precision for numeric values |
| `format` | Display format configuration |
| `segmentable` | Can be used in segments |
| `reportable` | Can be used in reports |
| `componentType` | Component classification |
| `attribution` | Attribution settings object |
| `attributionModel` | Attribution model type |
| `lookbackWindow` | Attribution lookback period |
| `dataType` | Underlying data type |
| `hasData` | Whether component has data |
| `approved` | Approval status |
| `bucketing` | Bucketing configuration |
| `bucketingSetting` | Bucketing settings object |
| `persistence` | Persistence configuration |
| `persistenceSetting` | Persistence settings object |
| `allocation` | Allocation method |
| `formula` | Calculated metric formula |
| `isCalculated` | Whether metric is calculated |
| `derivedFieldId` | Linked derived field ID |

### Metadata Comparison

In addition to components, the comparison tracks data view metadata changes:
- **Data view name** - Display name of the data view
- **Owner** - Owner/creator of the data view
- **Description** - Data view description

### Comparison Logic Example

```
Source Data View (Production)          Target Data View (Staging)
================================       ================================
metrics/pageviews (Page Views)    -->  metrics/pageviews (Page Views)     = UNCHANGED
metrics/visits (Visits)           -->  (not present)                      = REMOVED
metrics/bounce_rate (Bounce Rate) -->  metrics/bounce_rate (Bounce %)     = MODIFIED (name changed)
(not present)                     -->  metrics/new_metric (New Metric)    = ADDED
```

## Quick Start

### Compare Two Live Data Views

```bash
# By ID
cja_auto_sdr --diff dv_prod_12345 dv_staging_67890

# By name
cja_auto_sdr --diff "Production Analytics" "Staging Analytics"

# Mix IDs and names (both supported)
cja_auto_sdr --diff dv_prod_12345 "Staging Analytics"
cja_auto_sdr --diff "Production Analytics" dv_staging_67890
```

### Save and Compare Against Snapshots

```bash
# Save a baseline snapshot (by ID or name)
cja_auto_sdr dv_12345 --snapshot ./snapshots/baseline.json
cja_auto_sdr "Production Analytics" --snapshot ./snapshots/baseline.json

# Later, compare against the baseline (by ID or name)
cja_auto_sdr dv_12345 --diff-snapshot ./snapshots/baseline.json
cja_auto_sdr "Production Analytics" --diff-snapshot ./snapshots/baseline.json
```

## Command Options

| Option | Description |
|--------|-------------|
| `--diff` | Compare two data views. Requires exactly 2 data view IDs/names. |
| `--snapshot FILE` | Save a data view snapshot to a JSON file. |
| `--diff-snapshot FILE` | Compare a data view against a saved snapshot. |
| `--changes-only` | Only show changed items (hide unchanged components). |
| `--summary` | Show summary statistics only (no detailed changes). |
| `--ignore-fields FIELDS` | Comma-separated fields to ignore during comparison. |
| `--diff-labels A B` | Custom labels for source and target sides. |
| `--show-only TYPES` | Filter by change type: added, removed, modified (comma-separated). |
| `--metrics-only` | Only compare metrics (exclude dimensions). |
| `--dimensions-only` | Only compare dimensions (exclude metrics). |
| `--extended-fields` | Include extended fields (attribution, format, bucketing, etc.). |
| `--side-by-side` | Show side-by-side comparison view for modified items. |
| `--no-color` | Disable ANSI color codes in diff console output. |
| `--quiet-diff` | Suppress output, only return exit code (0=no changes, 2=changes, 3=threshold). |
| `--reverse-diff` | Swap source and target comparison direction. |
| `--warn-threshold PERCENT` | Exit with code 3 if change percentage exceeds threshold. |
| `--group-by-field` | Group changes by field name instead of by component. |
| `--diff-output FILE` | Write diff output directly to file instead of stdout. |
| `--format-pr-comment` | Output in GitHub/GitLab PR comment format with collapsible details. |

## Output Formats

All existing output formats are supported for diff reports:

```bash
# Console output (default for diff)
cja_auto_sdr --diff dv_A dv_B

# HTML report
cja_auto_sdr --diff dv_A dv_B --format html --output-dir ./reports

# JSON (for CI/CD integration)
cja_auto_sdr --diff dv_A dv_B --format json

# Markdown (for documentation/PRs)
cja_auto_sdr --diff dv_A dv_B --format markdown

# Excel workbook
cja_auto_sdr --diff dv_A dv_B --format excel

# CSV files
cja_auto_sdr --diff dv_A dv_B --format csv

# All formats at once
cja_auto_sdr --diff dv_A dv_B --format all
```

## Console Output Example

```
================================================================================
DATA VIEW COMPARISON REPORT
================================================================================
Source: Production Analytics (dv_prod_12345)
Target: Staging Analytics (dv_staging_67890)
Generated: 2025-01-17 14:30:00
================================================================================

SUMMARY
                          Source       Target      Added    Removed   Modified
--------------------------------------------------------------------------------
Metrics                      150          148         +3         -5         ~7
Dimensions                    75           78         +5         -2         ~4
--------------------------------------------------------------------------------

METRICS CHANGES (15)
  [+] metrics/new_conversion_rate            "New Conversion Rate"
  [-] metrics/legacy_bounce_rate             "Legacy Bounce Rate"
  [~] metrics/pageviews                      description: 'Old desc' -> 'New desc'

DIMENSIONS CHANGES (11)
  [+] dimensions/user_segment                "User Segment"
  [-] dimensions/old_campaign                "Old Campaign"
  [~] dimensions/device_type                 type: 'string' -> 'enum'

================================================================================
```

## Snapshot Format

Snapshots are saved as JSON files with the following structure:

```json
{
  "snapshot_version": "1.0",
  "created_at": "2025-01-17T14:30:00.000000",
  "data_view_id": "dv_12345",
  "data_view_name": "Production Analytics",
  "owner": "admin@example.com",
  "description": "Main production data view",
  "metrics": [
    { "id": "metrics/pageviews", "name": "Page Views", "type": "int", ... }
  ],
  "dimensions": [
    { "id": "dimensions/page", "name": "Page", "type": "string", ... }
  ],
  "metadata": {
    "tool_version": "3.0.9",
    "metrics_count": 150,
    "dimensions_count": 75
  }
}
```

## CI/CD Integration

The diff command uses exit codes for CI/CD integration:

| Exit Code | Meaning |
|-----------|---------|
| 0 | Success, no differences found |
| 1 | Error occurred |
| 2 | Success, differences found |
| 3 | Threshold exceeded (`--warn-threshold` triggered) |

### Example: GitHub Actions

```yaml
- name: Check for Data View Drift
  run: |
    cja_auto_sdr --diff dv_prod dv_staging --changes-only --format json
    if [ $? -eq 2 ]; then
      echo "Warning: Production and Staging data views differ!"
      exit 1  # Fail the build
    fi
```

### Example: Pre-deployment Validation

```bash
#!/bin/bash
# Validate staging matches expected baseline before deployment

cja_auto_sdr dv_staging --diff-snapshot ./expected_baseline.json --changes-only

if [ $? -eq 2 ]; then
    echo "ERROR: Staging environment has unexpected changes!"
    echo "Review the diff report before proceeding."
    exit 1
fi

echo "Validation passed. Proceeding with deployment..."
```

### Example: Threshold-Based CI/CD

```bash
#!/bin/bash
# Fail the build if more than 5% of components changed

cja_auto_sdr --diff dv_prod dv_staging --warn-threshold 5 --quiet-diff
exit_code=$?

if [ $exit_code -eq 3 ]; then
    echo "ERROR: Too many changes detected (>5%)!"
    echo "Run without --quiet-diff to see details."
    exit 1
elif [ $exit_code -eq 2 ]; then
    echo "Changes detected, but within acceptable threshold."
fi
```

### Example: Generate PR Comment

```bash
# Generate markdown optimized for GitHub/GitLab PR comments
cja_auto_sdr --diff dv_prod dv_staging --format-pr-comment --diff-output pr-comment.md

# Post as PR comment (GitHub CLI)
gh pr comment --body-file pr-comment.md
```

## Use Cases

### 1. Environment Validation

Ensure Production and Staging environments are synchronized:

```bash
cja_auto_sdr --diff "Production" "Staging" --format html --output-dir ./validation-reports
```

### 2. Migration Verification

Before and after a migration, verify no unintended changes occurred:

```bash
# Before migration
cja_auto_sdr dv_12345 --snapshot ./pre-migration.json

# Run migration...

# After migration
cja_auto_sdr dv_12345 --diff-snapshot ./pre-migration.json --format all
```

### 3. Change Tracking

Track changes to a data view over time:

```bash
# Create weekly snapshots
cja_auto_sdr dv_12345 --snapshot ./snapshots/week-$(date +%Y%m%d).json

# Compare with previous week
cja_auto_sdr dv_12345 --diff-snapshot ./snapshots/week-20250110.json
```

### 4. Documentation

Generate diff reports for stakeholder review:

```bash
# Create HTML report for review
cja_auto_sdr --diff dv_old dv_new --format html --diff-labels "Before" "After"

# Create Markdown for PR description
cja_auto_sdr --diff dv_old dv_new --format markdown --changes-only > pr-changes.md
```

### 5. Audit Trail

Maintain an audit trail of data view changes:

```bash
# Save snapshot after each approved change
cja_auto_sdr dv_12345 --snapshot ./audit/$(date +%Y%m%d_%H%M%S).json

# Generate comparison reports
cja_auto_sdr --diff ./audit/20250101.json ./audit/20250115.json
```

## Filtering Options

### Show Only Changes

Hide unchanged components to focus on differences:

```bash
cja_auto_sdr --diff dv_A dv_B --changes-only
```

### Summary Only

Show only summary statistics without detailed changes:

```bash
cja_auto_sdr --diff dv_A dv_B --summary
```

### Ignore Specific Fields

Exclude certain fields from comparison (e.g., ignore description changes):

```bash
cja_auto_sdr --diff dv_A dv_B --ignore-fields description,title
```

### Custom Labels

Use custom labels instead of data view names:

```bash
cja_auto_sdr --diff dv_A dv_B --diff-labels "Production" "Staging"
```

### Filter by Change Type

Show only specific types of changes:

```bash
# Show only added components
cja_auto_sdr --diff dv_A dv_B --show-only added

# Show only removed components
cja_auto_sdr --diff dv_A dv_B --show-only removed

# Show only modified components
cja_auto_sdr --diff dv_A dv_B --show-only modified

# Combine multiple types
cja_auto_sdr --diff dv_A dv_B --show-only added,modified
```

### Filter by Component Type

Compare only metrics or only dimensions:

```bash
# Compare only metrics
cja_auto_sdr --diff dv_A dv_B --metrics-only

# Compare only dimensions
cja_auto_sdr --diff dv_A dv_B --dimensions-only
```

### Side-by-Side View

Display modified items in a side-by-side format for easier comparison:

```bash
# Console side-by-side view
cja_auto_sdr --diff dv_A dv_B --side-by-side

# Markdown side-by-side (creates comparison tables)
cja_auto_sdr --diff dv_A dv_B --side-by-side --format markdown
```

Example side-by-side console output:
```
┌─────────────────────────────────────┬─────────────────────────────────────┐
│ Production                          │ Staging                             │
├─────────────────────────────────────┼─────────────────────────────────────┤
│ name: Page Views                    │ name: Page Views (Updated)          │
│ description: Total page views       │ description: All page views tracked │
└─────────────────────────────────────┴─────────────────────────────────────┘
```

### Extended Field Comparison

Compare additional fields including attribution, format, and bucketing settings:

```bash
# Include extended fields in comparison
cja_auto_sdr --diff dv_A dv_B --extended-fields

# Combine with other options
cja_auto_sdr --diff dv_A dv_B --extended-fields --side-by-side --changes-only
```

## Comparison Fields

By default, the following fields are compared for changes:
- `name` - Component display name
- `title` - Component title
- `description` - Component description
- `type` - Data type
- `schemaPath` - Schema mapping

With `--extended-fields`, additional fields are compared:
- `attribution`, `attributionModel`, `lookbackWindow` - Attribution settings
- `format`, `precision` - Display formatting
- `hidden`, `hideFromReporting` - Visibility settings
- `bucketing`, `bucketingSetting` - Bucketing configuration
- `persistence`, `persistenceSetting`, `allocation` - Persistence settings
- `formula`, `isCalculated`, `derivedFieldId` - Calculated metric settings
- `segmentable`, `reportable`, `componentType` - Component capabilities
- `dataType`, `hasData`, `approved` - Data and status fields

Use `--ignore-fields` to exclude any of these from comparison.

## Best Practices

1. **Create baseline snapshots** before making changes to data views
2. **Use meaningful labels** with `--diff-labels` for clearer reports
3. **Integrate with CI/CD** to catch unintended changes early
4. **Store snapshots in version control** for audit trails
5. **Use `--changes-only`** for cleaner output in large data views
6. **Generate multiple formats** with `--format all` for different audiences

## Troubleshooting

### "Snapshot file not found"

Ensure the snapshot file path is correct and accessible:

```bash
ls -la ./snapshots/baseline.json
```

### "Invalid snapshot file"

The file may not be a valid snapshot. Snapshots must contain `snapshot_version` field.

### "Could not resolve data view identifier"

Check that the data view ID or name is correct:

```bash
cja_auto_sdr --list-dataviews
```

## Testing

The diff comparison feature includes comprehensive unit tests in `tests/test_diff_comparison.py`.

### Test Coverage

| Test Class | Tests | Coverage |
|------------|-------|----------|
| `TestDataViewSnapshot` | 4 | Snapshot creation, serialization, deserialization |
| `TestSnapshotManager` | 5 | Save, load, list snapshots, error handling |
| `TestDataViewComparator` | 6 | Comparison logic, change detection, custom labels |
| `TestDiffSummary` | 3 | Summary statistics, has_changes, total_changes |
| `TestDiffOutputWriters` | 8 | Console, JSON, Markdown, HTML, Excel, CSV outputs |
| `TestEdgeCases` | 4 | Empty snapshots, all added/removed, special characters |
| `TestComparisonFields` | 5 | Default fields, ID matching, metadata, ignore fields |
| `TestCLIArguments` | 6 | Argument parsing for all diff-related flags |
| `TestOutputFormatVerification` | 3 | Output format accuracy and structure |
| `TestExtendedFieldComparison` | 3 | Extended fields, nested structures, attribution |
| `TestShowOnlyFilter` | 3 | Filter by added, removed, modified |
| `TestMetricsOnlyAndDimensionsOnly` | 2 | Component type filtering |
| `TestSideBySideOutput` | 3 | Console and markdown side-by-side views |
| `TestLargeDatasetPerformance` | 3 | 500+ components, memory efficiency |
| `TestUnicodeEdgeCases` | 4 | Emojis, RTL text, special characters |
| `TestDeeplyNestedStructures` | 3 | Attribution settings, format configs |
| `TestConcurrentComparison` | 1 | Thread safety with parallel comparisons |
| `TestSnapshotVersionMigration` | 3 | Version compatibility, future versions |
| `TestNewCLIArguments` | 5 | CLI flags |
| `TestDiffSummaryPercentages` | 5 | Percentage stats, natural language summary |
| `TestColoredConsoleOutput` | 2 | ANSI color codes, --no-color flag |
| `TestGroupByFieldOutput` | 1 | --group-by-field output mode |
| `TestPRCommentOutput` | 2 | --format-pr-comment output |
| `TestBreakingChangeDetection` | 3 | Type changes, removals detection |
| `TestNewCLIFlags` | 7 | All new CLI flags |

**Total: 94 tests**

### Running Tests

```bash
# Run all diff comparison tests
python -m pytest tests/test_diff_comparison.py -v

# Run specific diff comparison class tests
python -m pytest tests/test_diff_comparison.py::TestDataViewComparator -v
python -m pytest tests/test_diff_comparison.py::TestExtendedFieldComparison -v
python -m pytest tests/test_diff_comparison.py::TestSideBySideOutput -v
python -m pytest tests/test_diff_comparison.py::TestLargeDatasetPerformance -v

# Run with coverage
python -m pytest tests/test_diff_comparison.py --cov=cja_sdr_generator --cov-report=term-missing
```

### Key Test Scenarios

1. **Component Matching** - Verifies components are matched by ID, not name
2. **Change Detection** - Tests all four change types (added, removed, modified, unchanged)
3. **Field Comparison** - Validates all 5 default fields are compared
4. **Extended Fields** - Tests 20+ extended fields including attribution, format, bucketing
5. **Ignore Fields** - Tests `--ignore-fields` functionality
6. **Metadata Tracking** - Verifies data view metadata changes are tracked
7. **Output Formats** - Validates all output formats produce correct structure
8. **CLI Parsing** - Tests all diff-related command-line arguments
9. **Side-by-Side Output** - Tests console box-drawing and markdown table output
10. **Large Datasets** - Performance tests with 500+ components
11. **Unicode Handling** - Emojis, RTL text, special characters
12. **Concurrent Access** - Thread safety for parallel comparisons
13. **Version Migration** - Snapshot compatibility across versions

## See Also

- [CLI Reference](CLI_REFERENCE.md) - Complete command reference
- [Output Formats](OUTPUT_FORMATS.md) - Detailed format documentation
- [Troubleshooting](TROUBLESHOOTING.md) - Common issues and solutions
