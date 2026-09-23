# Segments Inventory

The Segments Inventory feature provides comprehensive documentation of all segments (filters) associated with a CJA data view. Since many calculated metrics use segment filters, this inventory complements the Calculated Metrics and Derived Fields inventories to provide complete component documentation.

## Quick Start

Add the `--include-segments` flag to include a segments inventory in your SDR output:

```bash
# Generate SDR with segments inventory
cja_auto_sdr dv_12345 --include-segments

# Combine with other inventories
cja_auto_sdr dv_12345 --include-segments --include-calculated --include-derived

# Output in multiple formats
cja_auto_sdr dv_12345 --include-segments --format all

# Generate ONLY segments inventory (no standard SDR content)
cja_auto_sdr dv_12345 --include-segments --inventory-only

# Multiple inventories only
cja_auto_sdr dv_12345 --include-segments --include-calculated --inventory-only
```

## CLI Options

| Option | Description |
|--------|-------------|
| `--include-segments` | Include segments inventory in SDR output. Adds a "Segments" sheet/section with complexity scores, definition summaries, and dimension/metric references. |
| `--inventory-only` | Output only inventory sheets (Segments, Calculated Metrics, Derived Fields). Skips standard SDR sheets (Metadata, Data Quality, DataView Details, Metrics, Dimensions). Requires at least one `--include-*` flag. |

## Output Columns

The Segments inventory includes the following columns:

| Column | Description |
|--------|-------------|
| `name` | Segment display name |
| `id` | Unique segment identifier |
| `description` | Segment description (if provided) |
| `owner` | Segment owner name |
| `approved` | Approval status (Yes/No) |
| `tags` | Organizational tags |
| `complexity_score` | Complexity score (0-100) |
| `container_type` | Container context from the segment definition, lowercased and then title-cased in tabular output (`Hits`, `Visits`, `Visitors`; custom contexts such as `Containers/Productlistitems` are also possible). The JSON export keeps the lowercase value (`hits`, `visits`, `visitors`). |
| `functions_used` | Functions used in definition |
| `dimension_references` | Referenced dimensions |
| `metric_references` | Referenced metrics |
| `segment_references` | Referenced segments (for nested segments) |
| `definition_summary` | Human-readable summary of segment logic |
| `summary` | Alias for `definition_summary` (for cross-module consistency) |
| `created` | Creation timestamp |
| `modified` | Last modified timestamp |
| `shared_to` | Number of users/groups shared with |
| `definition_json` | Raw JSON definition (for advanced analysis) |

## Complexity Score

The complexity score (0-100) is calculated based on weighted factors:

| Factor | Weight | Max Value | Description |
|--------|--------|-----------|-------------|
| Predicates | 30% | 50 | Comparison operations (equals, contains, etc.) |
| Logic Operators | 20% | 20 | Boolean operators (AND, OR, NOT) |
| Nesting Depth | 20% | 8 | Maximum nesting level |
| Dimension References | 10% | 15 | Unique dimensions referenced |
| Metric References | 10% | 5 | Unique metrics referenced |
| Regex Patterns | 10% | 5 | Regular expression patterns |

### Complexity Interpretation

| Score | Complexity | Typical Characteristics |
|-------|------------|------------------------|
| 0-25 | Low | Single condition, basic comparison |
| 26-50 | Moderate | Multiple conditions with AND/OR logic |
| 51-75 | Elevated | Nested logic, multiple references |
| 76-100 | High | Complex sequential or exclusion logic |

## Definition Summary Examples

The definition summary provides a human-readable description of segment logic:

| Segment Type | Summary Example |
|--------------|-----------------|
| Simple contains | `Hit where pageURL contains 'checkout'` |
| Multiple conditions | `Visit where channel = 'paid' AND pageviews > 5` |
| Person-level | `Person with revenue > 100 AND orders >= 3` |
| Existence check | `Hit where purchaseID exists` |
| Exclusion | `Hit excluding internal IP conditions` |
| Sequential | `Person with sequential pattern with 3 steps` |

## Container Types

Segments operate at different scope levels. The `container_type` field reports the container context from the segment definition, lowercased. Tabular output (Excel, CSV, HTML, Markdown) title-cases the value, and the JSON export keeps the lowercase value. Segments may also use custom containers, which appear with their context path (for example `Containers/Productlistitems`).

| Tabular value | JSON value | Scope |
|---------------|------------|-------|
| Hits | hits | Individual page view or event |
| Visits | visits | Session-level scope |
| Visitors | visitors | Cross-session, person-level scope |

> **Note:** The friendly `Hit` / `Visit` / `Person` wording is used only in the `definition_summary` field (for example `Person where revenue > 100`), not in `container_type`.

## Output Formats

The segments inventory is included in all supported output formats:

### Excel
- Adds a "Segments" sheet
- Sorted by complexity score (highest first)
- Sheet position follows CLI argument order

### JSON
- Adds a `segments` object with:
  - `summary`: Statistics including total count, complexity metrics, container type distribution
  - `segments`: Array of detailed segment objects

### CSV
- Creates a `_Segments.csv` file
- All columns included with proper escaping

### HTML
- Adds a styled "Segments" section
- Interactive table with all columns

### Markdown
- Adds a "Segments" section
- Formatted as a markdown table

## Use Cases

### Governance Audit
```bash
# Find all unapproved segments (inventory JSON is written to a file, not stdout)
cja_auto_sdr dv_12345 --include-segments --inventory-only --format json --output-dir ./inventory
jq '.segments.segments[] | select(.approved == false) | .segment_name' ./inventory/*_SDR.json
```

### Complexity Analysis
```bash
# List high-complexity segments (score >= 75)
cja_auto_sdr dv_12345 --include-segments --inventory-only --format json --output-dir ./inventory
jq '.segments.segments[] | select(.complexity_score >= 75)' ./inventory/*_SDR.json
```

### Dependency Mapping
```bash
# Find segments using specific dimensions
cja_auto_sdr dv_12345 --include-segments --inventory-only --format json --output-dir ./inventory
jq '.segments.segments[] | select(.dimension_references | contains(["revenue"]))' ./inventory/*_SDR.json
```

### Documentation Export
```bash
# Export segment documentation in all formats
cja_auto_sdr dv_12345 --include-segments --format all
```

## Function Reference

The following functions are recognized and displayed with human-readable names:

### Logical Operators
| Internal | Display Name |
|----------|-------------|
| `and` | And |
| `or` | Or |
| `not` | Not |

### Comparison Operators
| Internal | Display Name |
|----------|-------------|
| `eq` | Equals |
| `ne` | Not Equals |
| `gt` | Greater Than |
| `gte` | Greater Than or Equal |
| `lt` | Less Than |
| `lte` | Less Than or Equal |

### String Operators
| Internal | Display Name |
|----------|-------------|
| `contains` | Contains |
| `not-contains` | Does Not Contain |
| `starts-with` | Starts With |
| `ends-with` | Ends With |
| `matches` | Matches Regex |
| `not-matches` | Does Not Match Regex |

### Existence Operators
| Internal | Display Name |
|----------|-------------|
| `exists` | Exists |
| `not-exists` | Does Not Exist |

### Container Functions
| Internal | Display Name |
|----------|-------------|
| `container` | Container |
| `sequence` | Sequential |
| `sequence-prefix` | Sequence Prefix |
| `sequence-suffix` | Sequence Suffix |
| `exclude` | Exclude |

## Snapshot Diff Support

Segments inventory can be included in snapshot-based diff comparisons to track changes over time for the **same data view**.

> **Important:** Inventory diff is only supported for snapshot comparisons of the same data view. Cross-data-view comparisons do not support inventory options because segment IDs are data-view-scoped.
>
> **Supported inventories for diff:** Only segments (`--include-segments`) and calculated metrics (`--include-calculated`) are included in diff comparisons. Derived fields inventory (`--include-derived`) is for SDR generation only—derived field changes are captured in the standard Metrics/Dimensions diff because derived fields appear in those API outputs.
>
> **Design choice:** CJA Auto SDR intentionally does not attempt name-based or definition-based fuzzy matching for segments across data views. Two segments named "High Value Customers" in different data views may use completely different criteria, and matching by definition structure could produce false positives if the underlying dimensions have different meanings. ID-based matching within the same data view is reliable and avoids these issues.

### Creating Snapshots with Segments

```bash
# Create a snapshot with segments inventory
cja_auto_sdr dv_12345 --snapshot ./baseline.json --include-segments

# Include with calculated metrics inventory (both support diff)
cja_auto_sdr dv_12345 --snapshot ./baseline.json \
  --include-segments --include-calculated
```

### Comparing Segments Over Time

```bash
# Compare current state against baseline
cja_auto_sdr dv_12345 --diff-snapshot ./baseline.json --include-segments

# Compare two snapshots directly
cja_auto_sdr --compare-snapshots ./before.json ./after.json --include-segments

# Quick comparison against most recent snapshot
cja_auto_sdr dv_12345 --compare-with-prev --include-segments
```

### Fields Compared

The following segment fields are compared for changes:

| Field | Description |
|-------|-------------|
| `name` | Segment display name |
| `description` | Segment description |
| `owner` | Owner name |
| `approved` | Approval status |
| `tags` | Organizational tags |
| `complexity_score` | Definition complexity (0-100) |
| `functions_used` | Operators/functions used |
| `definition_summary` | Human-readable definition |
| `dimension_references` | Referenced dimensions |
| `metric_references` | Referenced metrics |
| `segment_references` | Referenced nested segments |
| `nesting_depth` | Logic nesting level |

### Example Output

```
SEGMENTS CHANGES (5)
  [+] s_mobile_2025       "Mobile Visitors 2025"
  [-] s_legacy_campaign   "Old Campaign Segment"
  [~] s_paid_traffic      description: 'Paid traffic' -> 'All paid traffic sources'
  [~] s_high_value        complexity_score: 45 -> 52; approved: 'No' -> 'Yes'
```

See [Diff Comparison Guide](DIFF_COMPARISON.md#inventory-diff-snapshot-only) for complete documentation.

## Troubleshooting

### No Segments Found

If no segments appear in the inventory:

1. **Verify data view ID**: Ensure the data view ID is correct
2. **Check API permissions**: Your API credentials need access to read segments
3. **Segment association**: Segments must be associated with the data view

### Missing Segment Details

Some fields may show as "-" if:
- The segment has no description set
- The segment has no owner assigned
- The field is not applicable (e.g., no tags, no shares)

### API Errors

If you encounter API errors:
- Check your CJA API credentials are valid
- Verify network connectivity
- The `getFilters` API endpoint must be accessible

## Related Documentation

- [Inventory Overview](INVENTORY_OVERVIEW.md) - Unified guide to all inventory modules
- [Calculated Metrics Inventory](CALCULATED_METRICS_INVENTORY.md) - Document calculated metrics
- [Derived Fields Inventory](DERIVED_FIELDS_INVENTORY.md) - Document derived fields
- [Diff Comparison Guide](DIFF_COMPARISON.md) - Snapshot diff documentation
- [CLI Reference](CLI_REFERENCE.md) - Full CLI documentation
