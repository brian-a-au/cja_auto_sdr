# Calculated Metrics Inventory

The CJA SDR Generator includes a calculated metrics inventory feature that provides a comprehensive summary of all calculated metrics associated with a Data View. Unlike derived fields (which appear in the standard Metrics/Dimensions SDR sheets), calculated metrics are **not included in standard SDR output**, making this inventory the primary and only source for calculated metric documentation.

This inventory surfaces formula logic, complexity scores, governance metadata (approval status, tags, sharing), timestamps, and all available API fields for complete SDR documentation.

## Quick Start

```bash
# Include calculated metrics inventory in SDR output
cja_auto_sdr dv_12345 --include-calculated
```

This adds a "Calculated Metrics" sheet/section to your SDR output with details about each calculated metric.

## CLI Option

| Option                 | Description                                                           |
|------------------------|-----------------------------------------------------------------------|
| `--include-calculated` | Include calculated metrics inventory in SDR output. Adds a "Calculated Metrics" sheet/section with complexity scores, formula summaries, and metric references |

## Combining with Derived Fields

You can include both inventories in the same SDR output. The sheets appear at the end of the output in the order specified on the command line:

```bash
# Derived Fields tab first, then Calculated Metrics
cja_auto_sdr dv_12345 --include-derived --include-calculated

# Calculated Metrics tab first, then Derived Fields
cja_auto_sdr dv_12345 --include-calculated --include-derived
```

## Output Columns

The calculated metrics inventory includes the following information for each metric:

| Column             | Description                                              |
|--------------------|----------------------------------------------------------|
| name               | Calculated metric name                                   |
| id                 | Full metric identifier                                   |
| description        | Metric description                                       |
| owner              | Owner name (who created the metric)                      |
| approved           | Approval status (Yes/No)                                 |
| tags               | Organizational tags applied to the metric                |
| complexity_score   | 0-100 score indicating formula complexity                |
| functions_used     | Human-readable list of functions (e.g., "Division, Segment Filter") |
| metric_references  | List of referenced metrics (e.g., "revenue, orders")     |
| segment_references | List of referenced segments/filters                      |
| formula_summary    | Brief description of what the metric calculates          |
| summary            | Alias for `formula_summary` (for cross-module consistency) |
| polarity           | Positive, Negative, or Neutral                           |
| format             | Output format, as the raw lowercase API value: `decimal`, `percent`, `currency`, `integer`, `time` |
| created            | Creation timestamp                                       |
| modified           | Last modified timestamp                                  |
| shared_to          | Number of users/groups the metric is shared with         |
| definition_json    | Raw `definition` JSON for full fidelity                  |

### Additional Fields (JSON output only)

The JSON output includes additional fields not shown in tabular formats:

| Field              | Description                                              |
|--------------------|----------------------------------------------------------|
| owner_id           | Owner's user ID                                          |
| favorite           | Whether the metric is marked as a favorite               |
| shares             | Full sharing details (recipients, permissions)           |
| data_view_id       | Associated data view ID                                  |
| site_title         | Site/company title                                       |

## Complexity Score

The complexity score (0-100) helps identify calculated metrics that may need review or simplification. It's calculated from weighted factors:

| Factor         | Weight | Max Value | Description                           |
|----------------|--------|-----------|---------------------------------------|
| Operators      | 25%    | 50        | Arithmetic operations count           |
| Metric refs    | 25%    | 10        | Number of metrics referenced          |
| Nesting        | 20%    | 8         | Nesting depth of formula              |
| Functions      | 15%    | 15        | Number of unique functions used       |
| Segments       | 10%    | 5         | Number of segment filters applied     |
| Conditionals   | 5%     | 5         | Number of conditional operations      |

**Score interpretation:**
- **0-25**: Simple calculated metric (e.g., single ratio)
- **25-50**: Moderate complexity (e.g., filtered ratio)
- **50-75**: Elevated complexity - consider review
- **75-100**: High complexity - may benefit from simplification

## Formula Summary

The formula summary provides a detailed human-readable description of what each calculated metric does, showing actual formula expressions where possible:

### Arithmetic Operations
Shows the actual formula with metric names:
- `'revenue / orders'` - Division
- `'sessions × conversionRate'` - Multiplication
- `'clicks + views + impressions'` - Addition (multiple operands)
- `'revenue - cost'` - Subtraction

### Segmented Metrics
Shows the metric with segment filter in bracket notation:
- `'orders[mobile_visitors]'` - Single filtered metric
- `'revenue / visits[paid_traffic]'` - Ratio with filtered denominator

### Aggregation Functions
Shows function name with the inner metric:
- `'SUM(daily_revenue)'` - Column sum
- `'CUM(orders)'` - Cumulative
- `'MEDIAN(session_duration)'` - Statistical median
- `'P90(load_time)'` - 90th percentile

### Conditional Logic
Shows the IF structure with then/else values:
- `'IF(..., orders, 0)'` - Conditional with metric and fallback
- `'IF(visits > 0, revenue / visits, 0)'` - Full condition when parseable

### Math Functions
- `'SQRT(variance)'`
- `'ABS(difference)'`
- `'LOG(growth_rate)'`
- `'base^exponent'` - Power operations

### Complex Formulas
For deeply nested formulas, shows a simplified expression:
- `'(revenue - cost) / orders'` - Nested with parentheses
- `'Ratio: orders / sessions'` - Fallback for complex ratios
- `'Combines revenue, orders, sessions'` - When formula is too complex

## Output Formats

The calculated metrics inventory is included in all SDR output formats when `--include-calculated` is specified:

### Excel
Adds a "Calculated Metrics" sheet to the SDR workbook, sorted by complexity score (highest first).

**Sheet Order:**
1. Metadata
2. Data Quality
3. DataView Details
4. Metrics
5. Dimensions
6. Derived Fields (if `--include-derived`)
7. Calculated Metrics (if `--include-calculated`)

> **Note:** Inventory sheets appear at the end in CLI argument order. Use `--include-calculated --include-derived` to place Calculated Metrics before Derived Fields.

### JSON
Adds a `calculated_metrics` section to the output:

```json
{
  "calculated_metrics": {
    "summary": {
      "data_view_id": "dv_12345",
      "data_view_name": "My Data View",
      "total_calculated_metrics": 12,
      "governance": {
        "approved_count": 8,
        "unapproved_count": 4,
        "shared_count": 6,
        "tagged_count": 10
      },
      "complexity": {
        "average": 28.5,
        "max": 65.3,
        "high_complexity_count": 1,
        "elevated_complexity_count": 3
      },
      "function_usage": {
        "Division": 8,
        "Metric Reference": 12,
        "Segment Filter": 4
      },
      "tag_usage": {
        "KPI": 5,
        "Revenue": 3,
        "Conversion": 2
      }
    },
    "metrics": [
      {
        "metric_id": "cm_12345",
        "metric_name": "Revenue per Order",
        "description": "Average revenue per order",
        "owner": "Analytics Team",
        "owner_id": "user123@example.com",
        "approved": true,
        "favorite": false,
        "tags": ["KPI", "Revenue"],
        "created": "2024-01-15T10:30:00Z",
        "modified": "2024-06-20T14:45:00Z",
        "shares": [{"type": "group", "name": "All Users"}],
        "shared_to_count": 1,
        "data_view_id": "dv_12345",
        "site_title": "My Company",
        "complexity_score": 18.5,
        "functions_used": ["Division", "Metric Reference"],
        "functions_used_internal": ["divide", "metric"],
        "nesting_depth": 1,
        "operator_count": 1,
        "metric_references": ["revenue", "orders"],
        "segment_references": [],
        "conditional_count": 0,
        "formula_summary": "revenue / orders",
        "polarity": "positive",
        "metric_type": "currency",
        "precision": 2,
        "definition_json": "{\"formula\":{\"func\":\"divide\",\"col1\":{...},\"col2\":{...}}}"
      },
      {
        "metric_id": "cm_67890",
        "metric_name": "Mobile Conversion Rate",
        "description": "Conversion rate for mobile visitors",
        "owner": "Analytics Team",
        "owner_id": "user456@example.com",
        "approved": false,
        "favorite": true,
        "tags": ["Conversion", "Mobile"],
        "created": "2024-03-01T09:00:00Z",
        "modified": "2024-07-15T16:20:00Z",
        "shares": [],
        "shared_to_count": 0,
        "data_view_id": "dv_12345",
        "site_title": "My Company",
        "complexity_score": 25.3,
        "functions_used": ["Division", "Metric Reference", "Segment Filter"],
        "functions_used_internal": ["divide", "metric", "segment"],
        "nesting_depth": 2,
        "operator_count": 1,
        "metric_references": ["orders", "visits"],
        "segment_references": ["s_mobile_visitors"],
        "conditional_count": 0,
        "formula_summary": "orders / visits[mobile_visitors]",
        "polarity": "positive",
        "metric_type": "percent",
        "precision": 2,
        "definition_json": "{\"formula\":{\"func\":\"divide\",\"col1\":{...},\"col2\":{\"func\":\"segment\",...}}}"
      }
    ]
  }
}
```

### CSV
Creates a separate `*_calculated_metrics.csv` file with all inventory columns.

### HTML
Adds a "Calculated Metrics" section to the HTML report with a sortable table.

### Markdown
Adds a "## Calculated Metrics" section with a formatted table.

## Use Cases

### SDR Documentation
Include calculated metrics details in your SDR to provide complete documentation of metric definitions. Since calculated metrics are not in standard SDR output, this inventory is essential for comprehensive documentation.

### Governance Review
Use governance fields to audit your calculated metrics:
- **Approval status**: Identify unapproved metrics that need review
- **Tags**: Ensure consistent categorization across metrics
- **Sharing**: Review who has access to each metric
- **Timestamps**: Identify stale metrics that haven't been updated

### Complexity Review
Sort by complexity score to identify calculated metrics that may need:
- Simplification
- Splitting into multiple metrics
- Documentation updates

### Dependency Mapping
The metric and segment references help identify:
- Which base metrics are used most frequently
- Which segments are commonly applied
- Dependencies between calculated metrics

### Owner Audit
Track metric ownership across your organization to:
- Identify orphaned metrics (owner no longer with company)
- Consolidate duplicates
- Assign maintenance responsibility

### Change Tracking
Use timestamps to:
- Identify recently modified metrics for review
- Find metrics that haven't been updated in a long time
- Track metric creation patterns over time

## CJA Function Reference

The inventory translates internal formula functions to human-readable display names:

### Arithmetic Operations
| Internal Name | Display Name     |
|---------------|------------------|
| divide        | Division         |
| multiply      | Multiplication   |
| add           | Addition         |
| subtract      | Subtraction      |
| negate        | Negation         |
| abs           | Absolute Value   |
| pow           | Power            |
| sqrt          | Square Root      |
| ceil          | Ceiling          |
| floor         | Floor            |
| round         | Round            |
| log           | Logarithm        |
| exp           | Exponential      |

### References
| Internal Name | Display Name       |
|---------------|--------------------|
| metric        | Metric Reference   |
| segment       | Segment Filter     |
| calc-metric   | Calculated Metric  |
| number        | Static Number      |

### Aggregations
| Internal Name | Display Name   |
|---------------|----------------|
| col-sum       | Column Sum     |
| col-max       | Column Max     |
| col-min       | Column Min     |
| col-mean      | Column Mean    |
| row-sum       | Row Sum        |
| row-max       | Row Max        |
| row-min       | Row Min        |
| row-mean      | Row Mean       |

### Conditional
| Internal Name | Display Name          |
|---------------|-----------------------|
| if            | Conditional (If)      |
| and           | Logical And           |
| or            | Logical Or            |
| not           | Logical Not           |
| eq            | Equals                |
| ne            | Not Equals            |
| gt            | Greater Than          |
| gte           | Greater Than or Equal |
| lt            | Less Than             |
| lte           | Less Than or Equal    |

### Statistical
| Internal Name       | Display Name       |
|--------------------|--------------------|
| median             | Median             |
| percentile         | Percentile         |
| variance           | Variance           |
| standard-deviation | Standard Deviation |
| correlation        | Correlation        |
| regression         | Regression         |

### Time Functions
| Internal Name   | Display Name    |
|-----------------|-----------------|
| time-comparison | Time Comparison |
| cumulative      | Cumulative      |
| rolling         | Rolling Window  |

## Key Differences from Derived Fields

| Aspect              | Derived Fields                     | Calculated Metrics                 |
|---------------------|------------------------------------|------------------------------------|
| **In Standard SDR** | Yes (Metrics/Dimensions sheets)    | **No** - inventory is only source  |
| Inventory Role      | Supplementary analysis view        | **Primary/comprehensive** source   |
| Scope               | Per data view                      | Global (filtered by data view)     |
| Data Source         | `fieldDefinition` in DataFrames    | `cja.getCalculatedMetrics()` API   |
| Definition          | `fieldDefinition` JSON array       | `definition.formula` nested object |
| References          | Schema fields                      | Other metrics (`metrics/visits`)   |
| Governance Fields   | N/A (in standard SDR)              | Approved, tags, shares, timestamps |
| Additional Data     | Rule names                         | Owner, polarity, precision, type   |

> **Why the difference?** Derived fields appear in standard SDR output (Metrics/Dimensions sheets) with all their metadata, so the Derived Fields Inventory focuses on logic analysis. Calculated metrics are NOT in standard SDR output, so this inventory must capture ALL available API fields.

## Snapshot Diff Support

Calculated metrics inventory can be included in snapshot-based diff comparisons to track changes over time for the **same data view**.

> **Important:** Inventory diff is only supported for snapshot comparisons of the same data view. Cross-data-view comparisons do not support inventory options because calculated metric IDs are data-view-scoped.
>
> **Supported inventories for diff:** Only calculated metrics (`--include-calculated`) and segments (`--include-segments`) are included in diff comparisons. Derived fields inventory (`--include-derived`) is for SDR generation only—derived field changes are captured in the standard Metrics/Dimensions diff because derived fields appear in those API outputs.
>
> **Design choice:** CJA Auto SDR intentionally does not attempt name-based or formula-based fuzzy matching for calculated metrics across data views. Two metrics named "Conversion Rate" in different data views may calculate completely different things, and matching by formula structure could still produce false positives if the underlying metrics have different meanings. ID-based matching within the same data view is reliable and avoids these issues.

### Creating Snapshots with Calculated Metrics

```bash
# Create a snapshot with calculated metrics inventory
cja_auto_sdr dv_12345 --snapshot ./baseline.json --include-calculated

# Include with segments inventory (both support diff)
cja_auto_sdr dv_12345 --snapshot ./baseline.json \
  --include-calculated --include-segments
```

### Comparing Calculated Metrics Over Time

```bash
# Compare current state against baseline
cja_auto_sdr dv_12345 --diff-snapshot ./baseline.json --include-calculated

# Compare two snapshots directly
cja_auto_sdr --compare-snapshots ./before.json ./after.json --include-calculated

# Quick comparison against most recent snapshot
cja_auto_sdr dv_12345 --compare-with-prev --include-calculated
```

### Fields Compared

The following calculated metric fields are compared for changes:

| Field | Description |
|-------|-------------|
| `name` | Metric display name |
| `description` | Metric description |
| `owner` | Owner name |
| `approved` | Approval status |
| `tags` | Organizational tags |
| `complexity_score` | Formula complexity (0-100) |
| `functions_used` | Functions in formula |
| `formula_summary` | Human-readable formula |
| `metric_references` | Referenced base metrics |
| `segment_references` | Referenced segments |
| `nesting_depth` | Formula nesting level |

### Example Output

```
CALCULATED METRICS CHANGES (4)
  [+] cm_new_conv    "New Conversion Rate"
  [-] cm_legacy      "Legacy Bounce Metric"
  [~] cm_revenue     name: 'Revenue/Visit' -> 'RPV'; approved: 'No' -> 'Yes'
  [~] cm_orders      formula_summary changed; complexity_score: 25 -> 32
```

See [Diff Comparison Guide](DIFF_COMPARISON.md#inventory-diff-snapshot-only) for complete documentation.

## Limitations

- **API-dependent**: Requires access to the CJA calculated metrics API
- **Data view filter**: Only shows metrics associated with the specified data view
- **Snapshot in time**: The inventory reflects the metrics state at generation time
- **No cross-metric analysis**: Does not show which calculated metrics reference other calculated metrics
- **Diff scope**: Inventory diff only works for same-data-view snapshot comparisons

## Troubleshooting

### "Could not import calculated metrics inventory"

The inventory module is not available. Ensure you have the latest version:

```bash
uv pip install --upgrade cja-auto-sdr
```

### No calculated metrics found

The inventory only includes metrics where:
- The metric is associated with the specified data view ID
- A valid `definition.formula` object exists

### Empty inventory

If your data view has no associated calculated metrics, the inventory section will be empty but still present in the output.

### API errors

If the CJA API returns an error, the SDR generation continues without the calculated metrics inventory. Check the log output for details.

## Related Documentation

- [Inventory Overview](INVENTORY_OVERVIEW.md) - Unified guide to all inventory modules
- [Segments Inventory](SEGMENTS_INVENTORY.md) - Document segment filters
- [Derived Fields Inventory](DERIVED_FIELDS_INVENTORY.md) - Document derived fields
- [Diff Comparison Guide](DIFF_COMPARISON.md) - Snapshot diff documentation
- [CLI Reference](CLI_REFERENCE.md) - Full CLI documentation
