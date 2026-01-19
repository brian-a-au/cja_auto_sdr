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

## Modified Detection In-Depth

The "modified" change type requires special attention as it indicates components that exist in both data views but have different field values. This section explains the detection logic, output formats, and how to interpret modifications.

### How Modified Detection Works

A component is classified as **modified** when:
1. The component exists in **both** source and target (matched by unique ID)
2. At least **one compared field** has a different value between source and target

The detection follows this process:

```
1. Match components by ID (e.g., "metrics/pageviews")
   ├── ID exists only in source → REMOVED
   ├── ID exists only in target → ADDED
   └── ID exists in both → Compare fields
                            ├── All fields identical → UNCHANGED
                            └── Any field differs → MODIFIED
```

### Field Comparison Algorithm

For each matched component, the tool compares field values using this logic:

```python
# Pseudocode for modification detection
for each field in compare_fields:
    if field in ignore_fields:
        skip  # User excluded this field

    source_value = source_component.get(field)
    target_value = target_component.get(field)

    # Normalize values for accurate comparison
    source_normalized = normalize(source_value)
    target_normalized = normalize(target_value)

    if source_normalized != target_normalized:
        mark as changed: field → (source_value, target_value)

if any fields changed:
    component is MODIFIED with list of changed_fields
else:
    component is UNCHANGED
```

### Value Normalization

Before comparison, values are normalized to ensure accurate detection:

| Original Value | Normalized Value | Purpose |
|---------------|------------------|---------|
| `None` | `""` (empty string) | Treat null and empty consistently |
| `NaN` (float/pandas) | `""` (empty string) | Treat NaN values as empty |
| `"  text  "` | `"text"` | Ignore leading/trailing whitespace |
| `{"b": 2, "a": 1}` | `{"a": 1, "b": 2}` | Sort dict keys for consistent comparison |
| `[item1, item2]` | Recursively normalized | Handle nested arrays |

This normalization ensures that:
- `description: null` equals `description: ""`
- `description: NaN` equals `description: ""` (both are treated as empty)
- `name: "Page Views "` equals `name: "Page Views"`
- Nested objects with different key ordering compare correctly

**Display Format:** Empty/null/NaN values are displayed as `(empty)` in diff output for clarity.

### Modified Output Formats

#### Console Output (Default)

Modified items display the changed field with before/after values:

```
METRICS CHANGES (4)
  [~] metrics/pageviews                    description: 'Old description' -> 'New description'
  [~] metrics/bounce_rate                  name: 'Bounce Rate' -> 'Bounce %'; type: 'decimal' -> 'int'
  [~] metrics/conversion                   title: 'Conv Rate' -> 'Conversion Rate'
  [~] metrics/sessions                     description: '(empty)' -> 'Session count metric'
```

Key elements:
- `[~]` - Modified indicator (yellow in colored output)
- Component ID and name
- Changed fields with `'old value' -> 'new value'` format
- Multiple field changes shown semicolon-separated
- Empty/null/NaN values displayed as `(empty)`

#### Side-by-Side Output (`--side-by-side`)

For detailed inspection of modifications:

```
┌─────────────────────────────────────┬─────────────────────────────────────┐
│ Production                          │ Staging                             │
├─────────────────────────────────────┼─────────────────────────────────────┤
│ name: Bounce Rate                   │ name: Bounce %                      │
│ description: The bounce rate metric │ description: Percentage of bounces  │
│ type: decimal                       │ type: int                           │
└─────────────────────────────────────┴─────────────────────────────────────┘
```

This view:
- Shows only fields that differ
- Presents source (left) and target (right) side by side
- Uses custom labels from `--diff-labels` if provided
- Available in console and markdown formats

#### JSON Output

Modified items include full `changed_fields` details:

```json
{
  "id": "metrics/bounce_rate",
  "name": "Bounce %",
  "change_type": "modified",
  "changed_fields": {
    "name": ["Bounce Rate", "Bounce %"],
    "type": ["decimal", "int"]
  },
  "source_data": { /* full source component */ },
  "target_data": { /* full target component */ }
}
```

The `changed_fields` object maps each changed field to a tuple of `[source_value, target_value]`.

### Filtering to Modified Only

Use `--show-only modified` to focus exclusively on modifications:

```bash
cja_auto_sdr --diff dv_12345 dv_67890 --show-only modified
```

This hides added, removed, and unchanged items—useful for reviewing what changed without the noise of new or deleted components.

### Modified with Extended Fields

With `--extended-fields`, modification detection expands to 20+ additional fields:

```bash
cja_auto_sdr --diff dv_12345 dv_67890 --extended-fields --show-only modified
```

Example output showing attribution changes:

```
METRICS CHANGES (2)
  [~] metrics/revenue    attribution: {'model': 'lastTouch'} -> {'model': 'linear'}
  [~] metrics/orders     lookbackWindow: '30' -> '90'
```

### Nested Structure Comparison

Extended fields like `attribution`, `bucketing`, and `persistence` contain nested objects. The comparison handles these recursively:

```
Source attribution:                    Target attribution:
{                                      {
  "model": "lastTouch",        →         "model": "linear",
  "lookbackWindow": 30                   "lookbackWindow": 30
}                                      }

Result: attribution field marked as MODIFIED
        Shows: {'model': 'lastTouch', ...} -> {'model': 'linear', ...}
```

### Ignoring Specific Field Modifications

Use `--ignore-fields` to exclude certain fields from modification detection:

```bash
# Ignore description changes (only detect name, type, etc. changes)
cja_auto_sdr --diff dv_12345 dv_67890 --ignore-fields description

# Ignore multiple fields
cja_auto_sdr --diff dv_12345 dv_67890 --ignore-fields description,title
```

This is useful when:
- Description updates are frequent but not meaningful
- Title formatting differs between environments
- You want to focus on structural changes (type, schemaPath)

### Breaking Change Detection

Certain modifications are flagged as "breaking changes" in the output:

| Field | Why Breaking |
|-------|--------------|
| `type` | Data type change may break downstream reports |
| `schemaPath` | Schema mapping change affects data collection |

These appear with warnings in console/markdown output:

```
⚠️ BREAKING CHANGES DETECTED
  - metrics/pageviews: type changed from 'int' to 'string'
  - dimensions/page: schemaPath changed
```

### Practical Examples

**Example 1: Name standardization between environments**

```text
$ cja_auto_sdr --diff "Production" "Staging" --show-only modified

METRICS CHANGES (3)
  [~] metrics/page_views    name: 'Page Views' -> 'Pageviews'
  [~] metrics/bounce_rate   name: 'Bounce Rate' -> 'Bounce %'
  [~] metrics/avg_time      name: 'Avg. Time on Page' -> 'Average Time on Page'
```

**Example 2: Schema migration changes**

```text
$ cja_auto_sdr --diff "Before Migration" "After Migration" --extended-fields --show-only modified

METRICS CHANGES (5)
  [~] metrics/revenue       attribution: {'model': 'lastTouch'} -> {'model': 'linear'}
  [~] metrics/orders        type: 'int' -> 'decimal', precision: '0' -> '2'

⚠️ BREAKING CHANGES DETECTED
  - metrics/orders: type changed from 'int' to 'decimal'
```

**Example 3: Detailed side-by-side review**

```text
$ cja_auto_sdr --diff dv_12345 dv_67890 --side-by-side --show-only modified

[~] metrics/conversion_rate "Conversion Rate"
┌─────────────────────────────────────┬─────────────────────────────────────┐
│ Production                          │ Staging                             │
├─────────────────────────────────────┼─────────────────────────────────────┤
│ description: Conversion rate for    │ description: Rate of conversions    │
│   all visitors                      │   from qualified traffic            │
│ type: decimal                       │ type: percentage                    │
│ precision: 2                        │ precision: 1                        │
└─────────────────────────────────────┴─────────────────────────────────────┘
```

**Example 4: Empty/null value changes**

When descriptions or other fields change from empty/null to having a value (or vice versa), the diff clearly shows `(empty)`:

```text
$ cja_auto_sdr --diff "Production" "Staging" --show-only modified

METRICS CHANGES (2)
  [~] metrics/first_time_sessions    description: '(empty)' -> 'n/a'
  [~] metrics/return_sessions        description: '(empty)' -> 'Returning visitor sessions'

DIMENSIONS CHANGES (1)
  [~] variables/session_type         description: '(empty)' -> 'First-time vs Return'
```

This makes it clear when fields are being populated with values that were previously undefined, which is common during documentation improvements or environment synchronization.

## Quick Start

### Compare Two Live Data Views

```bash
# By ID
cja_auto_sdr --diff dv_12345 dv_67890

# By name
cja_auto_sdr --diff "Production Analytics" "Staging Analytics"

# Mix IDs and names (both supported)
cja_auto_sdr --diff dv_12345 "Staging Analytics"
cja_auto_sdr --diff "Production Analytics" dv_67890
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

### Compare Two Snapshots Directly

Compare two previously saved snapshot files without any API calls—useful for offline analysis, historical comparisons, or when API access is unavailable:

```bash
# Compare two snapshot files directly
cja_auto_sdr --compare-snapshots ./snapshots/before.json ./snapshots/after.json

# With output format
cja_auto_sdr --compare-snapshots ./prod.json ./staging.json --format html

# All diff options work with snapshot comparison
cja_auto_sdr --compare-snapshots ./old.json ./new.json --changes-only --side-by-side
```

### Auto-Snapshot on Diff

Automatically save timestamped snapshots during any diff comparison—no extra commands needed. This creates an audit trail without manual snapshot management.

```bash
# Auto-save snapshots during diff comparison
cja_auto_sdr --diff dv_12345 dv_67890 --auto-snapshot

# Snapshots saved to: ./snapshots/
#   - DataViewName_dv_12345_20260118_143022.json
#   - DataViewName_dv_67890_20260118_143022.json

# Custom snapshot directory
cja_auto_sdr --diff dv_12345 dv_67890 --auto-snapshot --snapshot-dir ./history

# With retention policy (keep only last 10 snapshots per data view)
cja_auto_sdr --diff dv_12345 dv_67890 --auto-snapshot --keep-last 10

# Works with diff-snapshot too (saves current state)
cja_auto_sdr dv_12345 --diff-snapshot ./baseline.json --auto-snapshot
```

**Benefits:**
- **Audit Trail**: Every comparison automatically documents the "before" state
- **Rollback Reference**: Can always see what changed when
- **Zero Friction**: No extra commands; happens transparently
- **CI/CD Friendly**: Scheduled diffs build history automatically

**Retention Policy:**
- `--keep-last 0` (default): Keep all snapshots forever
- `--keep-last N`: Keep only the N most recent snapshots per data view
- Old snapshots are deleted automatically after new ones are saved

## Smart Name Resolution

When you specify data views by name, the tool provides intelligent features to help resolve ambiguities and typos.

### Fuzzy Name Matching

If you mistype a data view name, the tool suggests similar names using fuzzy matching:

```
No data view found with name 'Prodction Analytics'
Did you mean one of these?
  - Production Analytics (edit distance: 1)
  - Production Analytics v2 (edit distance: 4)
```

### Interactive Disambiguation

When a name matches multiple data views (which requires exactly one match for diff operations), you'll be prompted to choose:

```
Multiple data views found with name 'Analytics':
  1. dv_12345 - Analytics (Production)
  2. dv_67890 - Analytics (Staging)
  3. dv_abcde - Analytics (Test)
Enter number to select, or 'q' to quit:
```

> **Note:** Interactive prompts only appear when running in an interactive terminal (TTY). In non-interactive contexts (CI/CD, scripts), the tool will report the ambiguity and exit with an error.

### API Response Caching

To minimize API calls during name resolution, data view listings are cached for 5 minutes. This significantly improves performance when processing multiple data views by name or retrying after errors.

## Command Options

| Option | Description |
|--------|-------------|
| `--diff` | Compare two data views. Requires exactly 2 data view IDs/names. |
| `--snapshot FILE` | Save a data view snapshot to a JSON file. |
| `--diff-snapshot FILE` | Compare a data view against a saved snapshot. |
| `--compare-snapshots A B` | Compare two snapshot files directly (no API calls needed). |
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
| `--auto-snapshot` | Automatically save snapshots during diff for audit trail. |
| `--snapshot-dir DIR` | Directory for auto-saved snapshots (default: ./snapshots). |
| `--keep-last N` | Retention: keep only last N snapshots per data view (0 = keep all). |

## Output Formats

All existing output formats are supported for diff reports:

```bash
# Console output (default for diff)
cja_auto_sdr --diff dv_12345 dv_67890

# HTML report
cja_auto_sdr --diff dv_12345 dv_67890 --format html --output-dir ./reports

# JSON (for CI/CD integration)
cja_auto_sdr --diff dv_12345 dv_67890 --format json

# Markdown (for documentation/PRs)
cja_auto_sdr --diff dv_12345 dv_67890 --format markdown

# Excel workbook
cja_auto_sdr --diff dv_12345 dv_67890 --format excel

# CSV files
cja_auto_sdr --diff dv_12345 dv_67890 --format csv

# All formats at once
cja_auto_sdr --diff dv_12345 dv_67890 --format all
```

## Console Output Example

```
================================================================================
DATA VIEW COMPARISON REPORT
================================================================================
Source: Production Analytics (dv_12345)
Target: Staging Analytics (dv_67890)
Generated: 2025-01-17 14:30:00
================================================================================

SUMMARY
                          Source       Target      Added    Removed   Modified   Unchanged     Changed
-------------------------------------------------------------------------------------------------------
Metrics                      150          148         +3         -5         ~7         145     (10.0%)
Dimensions                    75           78         +5         -2         ~4          68     (14.7%)
-------------------------------------------------------------------------------------------------------

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

## Interpreting the Summary Table

The summary table provides a quick overview of differences between two data views. Here's how to interpret each column and the underlying logic:

### Summary Column Reference

| Column | Description |
|--------|-------------|
| **Source** | Total component count in the source (first) data view |
| **Target** | Total component count in the target (second) data view |
| **Added** | Components that exist in target but NOT in source (new items) |
| **Removed** | Components that exist in source but NOT in target (deleted items) |
| **Modified** | Components that exist in BOTH but have different field values |
| **Unchanged** | Components that are identical in both data views |
| **Changed** | Percentage of components affected by any change |

### Mathematical Relationships

The summary columns are mathematically related. Understanding these relationships helps validate diff results.

| Relationship | Formula | Explanation |
|--------------|---------|-------------|
| Target count | `Target = Source - Removed + Added` | The target has what source had, minus removals, plus additions |
| Unchanged count | `Unchanged = Source - Removed - Modified` | Source components that weren't removed or changed |
| Unchanged (alt) | `Unchanged = Target - Added - Modified` | Target components that weren't added or changed |
| Total changes | `Total Changes = Added + Removed + Modified` | Sum of all change types |
| Change percentage | `Changed % = (Total Changes / Source) × 100` | Changes relative to source size |

**Note:** Change percentage can exceed 100% when there are many additions combined with removals, indicating significant restructuring between the two data views.

### Example Interpretation

```
SUMMARY
                     Adobestore (Stitched)   Adobe Store - Prod      Added    Removed   Modified   Unchanged     Changed
-------------------------------------------------------------------------------------------------------------------------
Metrics                                 33                   28        +17        -22        ~10           6    (148.5%)
Dimensions                             120                   98        +48        -70        ~31          21    (124.2%)
```

**Reading the Metrics row:**
- **Source (33)**: The source data view has 33 metrics
- **Target (28)**: The target data view has 28 metrics
- **Added (+17)**: 17 metrics exist in target that don't exist in source
- **Removed (-22)**: 22 metrics exist in source that don't exist in target
- **Modified (~10)**: 10 metrics exist in both but have different values
- **Unchanged (6)**: 6 metrics are identical in both data views
- **Changed (148.5%)**: 49 total changes (17+22+10) relative to 33 source components

**Validation:**
- Target = Source - Removed + Added → 28 = 33 - 22 + 17 ✓
- Unchanged = Source - Removed - Modified → 6 = 33 - 22 - 10 ✓ (with 5 that became modified)

### Understanding High Change Percentages

A change percentage over 100% indicates significant restructuring:

- **>100%**: More changes than original components (heavy additions or both adds and removes)
- **~50-100%**: Substantial changes affecting half or more of components
- **<25%**: Minor changes, mostly stable

### Change Type Symbols

In detailed output, changes are marked with symbols:

| Symbol | Meaning | Color (console) |
|--------|---------|-----------------|
| `[+]` | Added | Green |
| `[-]` | Removed | Red |
| `[~]` | Modified | Yellow |

### Format-Specific Summary Display

The summary appears in all output formats with slight variations:

- **Console**: Colored symbols and percentages with ANSI codes (use `--no-color` to disable)
- **Markdown**: Plain text table suitable for documentation and PR comments
- **HTML**: Styled table with color-coded cells
- **Excel**: Dedicated Summary sheet with formatted columns
- **CSV**: `_summary.csv` file with numeric values
- **JSON**: `summary` object with all counts and percentages

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
    "tool_version": "3.0.10",
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
    cja_auto_sdr --diff dv_12345 dv_67890 --changes-only --format json
    if [ $? -eq 2 ]; then
      echo "Warning: Production and Staging data views differ!"
      exit 1  # Fail the build
    fi
```

### Example: Pre-deployment Validation

```bash
#!/bin/bash
# Validate staging matches expected baseline before deployment

cja_auto_sdr dv_67890 --diff-snapshot ./expected_baseline.json --changes-only

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

cja_auto_sdr --diff dv_12345 dv_67890 --warn-threshold 5 --quiet-diff
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
cja_auto_sdr --diff dv_12345 dv_67890 --format-pr-comment --diff-output pr-comment.md

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
cja_auto_sdr --diff dv_12345 dv_67890 --format html --diff-labels "Before" "After"

# Create Markdown for PR description
cja_auto_sdr --diff dv_12345 dv_67890 --format markdown --changes-only > pr-changes.md
```

### 5. Audit Trail

Maintain an audit trail of data view changes:

```bash
# Save snapshot after each approved change
cja_auto_sdr dv_12345 --snapshot ./audit/$(date +%Y%m%d_%H%M%S).json

# Generate comparison reports between any two snapshots
cja_auto_sdr --compare-snapshots ./audit/20250101.json ./audit/20250115.json
```

### 6. Offline Historical Comparison

Compare historical snapshots without API access:

```bash
# Compare snapshots from different time periods
cja_auto_sdr --compare-snapshots ./snapshots/q1-2025.json ./snapshots/q2-2025.json

# Generate all format reports for quarterly review
cja_auto_sdr --compare-snapshots ./q1.json ./q2.json --format all --output-dir ./quarterly-review
```

## Filtering Options

### Show Only Changes

Hide unchanged components to focus on differences:

```bash
cja_auto_sdr --diff dv_12345 dv_67890 --changes-only
```

### Summary Only

Show only summary statistics without detailed changes:

```bash
cja_auto_sdr --diff dv_12345 dv_67890 --summary
```

### Ignore Specific Fields

Exclude certain fields from comparison (e.g., ignore description changes):

```bash
cja_auto_sdr --diff dv_12345 dv_67890 --ignore-fields description,title
```

### Custom Labels

Use custom labels instead of data view names:

```bash
cja_auto_sdr --diff dv_12345 dv_67890 --diff-labels "Production" "Staging"
```

### Filter by Change Type

Show only specific types of changes:

```bash
# Show only added components
cja_auto_sdr --diff dv_12345 dv_67890 --show-only added

# Show only removed components
cja_auto_sdr --diff dv_12345 dv_67890 --show-only removed

# Show only modified components
cja_auto_sdr --diff dv_12345 dv_67890 --show-only modified

# Combine multiple types
cja_auto_sdr --diff dv_12345 dv_67890 --show-only added,modified
```

### Filter by Component Type

Compare only metrics or only dimensions:

```bash
# Compare only metrics
cja_auto_sdr --diff dv_12345 dv_67890 --metrics-only

# Compare only dimensions
cja_auto_sdr --diff dv_12345 dv_67890 --dimensions-only
```

### Side-by-Side View

Display modified items in a side-by-side format for easier comparison:

```bash
# Console side-by-side view
cja_auto_sdr --diff dv_12345 dv_67890 --side-by-side

# Markdown side-by-side (creates comparison tables)
cja_auto_sdr --diff dv_12345 dv_67890 --side-by-side --format markdown
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
cja_auto_sdr --diff dv_12345 dv_67890 --extended-fields

# Combine with other options
cja_auto_sdr --diff dv_12345 dv_67890 --extended-fields --side-by-side --changes-only
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
| `TestAmbiguousNameResolution` | 6 | Ambiguous name handling in diff mode |
| `TestLevenshteinDistance` | 4 | Edit distance algorithm accuracy |
| `TestFindSimilarNames` | 5 | Fuzzy name matching suggestions |
| `TestDataViewCache` | 4 | Cache singleton, TTL, thread safety |
| `TestSnapshotToSnapshotComparison` | 4 | Direct snapshot file comparison |
| `TestPromptForSelection` | 4 | Interactive selection prompts |
| `TestNewFeatureCLIArguments` | 2 | --compare-snapshots CLI argument |
| `TestAutoSnapshotFilenameGeneration` | 4 | Timestamped filename generation, sanitization |
| `TestRetentionPolicy` | 5 | Keep all, delete old, per-data-view filtering |
| `TestAutoSnapshotCLIArguments` | 7 | --auto-snapshot, --snapshot-dir, --keep-last |

**Total: 139 tests**

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
14. **Snapshot-to-Snapshot** - Direct comparison of two snapshot files
15. **Fuzzy Matching** - Levenshtein distance algorithm and similar name suggestions
16. **API Caching** - Thread-safe data view cache with TTL expiration
17. **Interactive Selection** - User prompts for disambiguation in TTY mode
18. **Ambiguous Names** - Proper handling when names match multiple data views
19. **Auto-Snapshot** - Automatic snapshot saving with timestamped filenames
20. **Retention Policy** - Configurable snapshot retention per data view

## See Also

- [CLI Reference](CLI_REFERENCE.md) - Complete command reference
- [Output Formats](OUTPUT_FORMATS.md) - Detailed format documentation
- [Troubleshooting](TROUBLESHOOTING.md) - Common issues and solutions
