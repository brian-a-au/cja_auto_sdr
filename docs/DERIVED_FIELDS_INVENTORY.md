# Derived Field Inventory

The CJA SDR Generator includes a derived field inventory feature that provides a summary of all derived fields within a Data View. This inventory surfaces derived field logic, complexity scores, and metadata, making SDR documentation reviews more efficient.

## Quick Start

```bash
# Include derived field inventory in SDR output
cja_auto_sdr dv_12345 --include-derived
```

This adds a "Derived Fields" sheet/section to your SDR output with details about each derived field.

## CLI Option

| Option              | Description                                                           |
|---------------------|-----------------------------------------------------------------------|
| `--include-derived` | Include derived field inventory in SDR output. Adds a "Derived Fields" sheet/section with complexity scores, functions used, and logic summaries |

## Output Columns

The derived field inventory includes the following information for each derived field:

| Column            | Description                                              |
|-------------------|----------------------------------------------------------|
| name              | Component name                                           |
| type              | Metric or Dimension                                      |
| id                | Full component identifier                                |
| description       | Component description (if available in data view)        |
| complexity_score  | 0-100 score indicating logic complexity                  |
| functions_used    | Human-readable list of functions (e.g., "Case When, Lowercase") |
| branch_count      | Number of branches for Case When logic                   |
| schema_fields     | Count of schema fields referenced                        |
| schema_field_list | List of referenced field IDs (truncated if many)         |
| lookup_references | External lookup/classify references                      |
| rule_names        | Metadata from the field definition (#rule_name values)   |
| logic_summary     | Brief description of what the field does                 |
| summary           | Alias for `logic_summary` (for cross-module consistency) |
| output_type       | Inferred output type (Numeric, String, Unknown)          |
| definition_json   | Raw `fieldDefinition` JSON for full fidelity             |

## Complexity Score

The complexity score (0-100) helps identify derived fields that may need review or simplification. It's calculated from weighted factors:

| Factor         | Weight | Max Value | Description                     |
|----------------|--------|-----------|--------------------------------|
| Operators      | 30%    | 200       | Total operators in predicates   |
| Branches       | 25%    | 50        | Case When branch count          |
| Nesting        | 20%    | 5         | Nesting depth of conditions     |
| Functions      | 10%    | 20        | Number of unique functions used |
| Schema fields  | 10%    | 10        | Number of schema fields referenced |
| Regex patterns | 5%     | 5         | Number of regex patterns        |

**Score interpretation:**
- **0-25**: Simple derived field
- **25-50**: Moderate complexity
- **50-75**: Elevated complexity - consider review
- **75-100**: High complexity - may benefit from simplification

## Logic Summary

The logic summary provides a detailed human-readable description of what each derived field does, including actual conditions, values, and field names:

### Case When Fields
Shows example condition→value pairs and default values:
- `'Case When: channel="email"→"Email"; channel="paid"→"Paid"; ..., else: "Other"'`
- `'Case When (12): eVar1 contains "promo"→"Promotion"; eVar1 starts "aff"→"Affiliate"; ...'`

### Lookup Fields
Shows the key-to-value mapping and dataset:
- `'Lookup: productId → productName from products_lookup'`
- `'Lookup by sku'`

### Math Operations
Shows the actual formula with field names:
- `'Math: revenue / sessions'`
- `'Math: unitPrice × quantity'`

### URL Parsing
Shows which component is extracted and from which field:
- `'URL parse: extract hostname from pageURL'`
- `'URL parse: extract query param "campaign" from referrer'`

### String Operations
- **Concatenate**: `'Concat 3 fields with " | "'`
- **Split**: `'Split pageURL by "/", get part 3'`
- **Regex**: `'Regex: /^https?:\/\// → ""'` (pattern with replacement)
- **Merge**: `'Merge: eVar1, eVar2, eVar3'`

### Sequential Values
- `'Next value of purchaseId (session)'`
- `'Previous value of pageCategory'`

### Deduplication
- `'Deduplicate orderId per session'`
- `'Deduplicate visitorId per person'`

### Transformations
Appended to other summaries when applied:
- `'URL parse: extract path from pageURL → lowercase'`
- `'Merge: field1, field2 → trim'`

### Type Conversion
- `'Converts stringField to integer'`
- `'Converts to decimal'`

### Date/Time Operations
- `'Buckets timestamp by week'`
- `'Extracts hour from eventTime'`
- `'Shifts timestamp from UTC to America/New_York'`

### Find and Replace
- `'Replaces "www." with "" in pageURL'`
- `'Removes "/index.html" from pagePath'`

### Path Analysis
- `'Counts depth of pagePath'`

### Profile Attributes
- `'References profile attribute loyaltyTier'`
- `'References profile attribute customer/segment'`

### Simple References
- `'References eVar15'`
- `'Combines 4 fields'`

## Output Formats

The derived field inventory is included in all SDR output formats when `--include-derived` is specified:

### Excel
Adds a "Derived Fields" sheet to the SDR workbook, sorted by complexity score (highest first).

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
Adds a `derived_fields` section to the output:

```json
{
  "derived_fields": {
    "summary": {
      "data_view_id": "dv_12345",
      "data_view_name": "My Data View",
      "total_derived_fields": 15,
      "metrics_count": 8,
      "dimensions_count": 7,
      "complexity": {
        "average": 32.5,
        "max": 78.3,
        "high_complexity_count": 2,
        "elevated_complexity_count": 4
      },
      "function_usage": {
        "Case When": 10,
        "Lowercase": 5,
        "Lookup/Classify": 3
      }
    },
    "fields": [
      {
        "component_id": "dv_12345/derived/marketing_channel",
        "component_name": "Marketing Channel",
        "component_type": "Dimension",
        "complexity_score": 45.2,
        "functions_used": ["Case When"],
        "functions_used_internal": ["match"],
        "branch_count": 12,
        "nesting_depth": 2,
        "operator_count": 8,
        "schema_field_count": 2,
        "schema_fields": ["web.referringDomain", "marketing.campaignId"],
        "lookup_references": [],
        "component_references": [],
        "rule_names": ["Channel Classification"],
        "rule_descriptions": ["Categorizes traffic by channel"],
        "logic_summary": "Case When (12): referringDomain contains \"google\"→\"Organic Search\"; ...",
        "inferred_output_type": "string",
        "definition_json": "[{\"func\":\"match\",\"field\":\"1\",\"branches\":[...]}]"
      },
      {
        "component_id": "dv_12345/derived/product_category",
        "component_name": "Product Category",
        "component_type": "Dimension",
        "complexity_score": 22.5,
        "functions_used": ["Lookup/Classify"],
        "functions_used_internal": ["classify"],
        "branch_count": 0,
        "nesting_depth": 1,
        "operator_count": 0,
        "schema_field_count": 1,
        "schema_fields": ["product.sku"],
        "lookup_references": ["product_catalog"],
        "component_references": [],
        "rule_names": [],
        "rule_descriptions": [],
        "logic_summary": "Lookup: sku → categoryName from product_catalog",
        "inferred_output_type": "string",
        "definition_json": "[{\"func\":\"classify\",\"mapping\":{...}}]"
      }
    ]
  }
}
```

### CSV
Creates a separate `*_derived_fields.csv` file with all inventory columns.

### HTML
Adds a "Derived Fields" section to the HTML report with a sortable table.

### Markdown
Adds a "## Derived Fields" section with a formatted table.

## Use Cases

### SDR Documentation
Include derived field details in your SDR to provide complete documentation of data view logic.

### Complexity Review
Sort by complexity score to identify derived fields that may need:
- Simplification
- Splitting into multiple fields
- Migration to lookup datasets

### Function Audit
The function usage summary helps identify:
- Which functions are most commonly used
- Potential opportunities for standardization

### Logic Documentation
Rule names and logic summaries provide documentation for derived field configurations.

## CJA Function Reference

The inventory translates internal function names to human-readable display names:

| Internal Name       | Display Name          |
|--------------------|-----------------------|
| match              | Case When             |
| classify           | Lookup/Classify       |
| divide             | Math (Division)       |
| multiply           | Math (Multiplication) |
| add                | Math (Addition)       |
| subtract           | Math (Subtraction)    |
| lowercase          | Lowercase             |
| uppercase          | Uppercase             |
| trim               | Trim                  |
| concatenate        | Concatenate           |
| url-parse          | URL Parse             |
| regex-replace      | Regex Replace         |
| next               | Next Value            |
| previous           | Previous Value        |
| summarize          | Summarize             |
| merge              | Merge Fields          |
| deduplicate        | Deduplicate           |
| field-def-reference| Component Reference   |
| typecast           | Typecast              |
| datetime-bucket    | Date Bucket           |
| datetime-slice     | Date Slice            |
| timezone-shift     | Timezone Shift        |
| find-replace       | Find & Replace        |
| depth              | Depth                 |
| profile            | Profile Field         |
| split              | Split                 |

## Snapshot Diff Support

> **Important:** The derived fields inventory is for **SDR generation only**—it is NOT included in snapshot diff comparisons.
>
> **Why?** Derived fields are already included in the standard CJA metrics and dimensions API outputs. When you compare snapshots or data views, derived field changes are automatically captured in the **Metrics/Dimensions diff sections**. Including them again in a separate inventory diff would produce duplicate output.

### How Derived Field Changes Are Tracked

Derived field changes are tracked through the standard Metrics/Dimensions diff:

- **Standard diff**: compares `name`, `title`, `description`, `type`, `schemaPath`
- **Extended diff** (`--extended-fields`): adds `hidden`, `format`, `precision`, `attribution`, `persistence`, `bucketing`, `derivedFieldId`, etc.

### Example: Tracking Derived Field Changes

```bash
# Create baseline snapshot (derived fields are captured automatically)
cja_auto_sdr dv_12345 --snapshot ./baseline.json

# Later, compare against baseline
cja_auto_sdr dv_12345 --diff-snapshot ./baseline.json

# Derived field changes appear in METRICS CHANGES or DIMENSIONS CHANGES:
# [+] dv_12345/derived/new_channel    "New Marketing Channel"
# [~] dv_12345/derived/channel        description: 'Old desc' -> 'New desc'
```

### SDR-Only Usage

Use `--include-derived` to add logic analysis to your SDR output:

```bash
# Include derived fields inventory in SDR
cja_auto_sdr dv_12345 --include-derived

# The inventory provides complexity scores, function usage, and logic summaries
# that help document your derived field implementations
```

### Inventory Diff Alternatives

For snapshot diff comparisons, use these inventory options instead:

| Inventory | Diff Support | Why |
|-----------|--------------|-----|
| `--include-segments` | ✅ Yes | Segments are separate components not in standard Metrics/Dimensions |
| `--include-calculated` | ✅ Yes | Calculated metrics are separate components not in standard Metrics/Dimensions |
| `--include-derived` | ❌ SDR only | Derived fields are already in standard Metrics/Dimensions |

See [Diff Comparison Guide](DIFF_COMPARISON.md#inventory-diff-snapshot-only) for complete documentation on inventory diff support.

## Limitations

- **Per-data-view only**: The inventory is generated per data view, not across multiple data views
- **Snapshot in time**: The inventory reflects the data view state at generation time
- **No real-time updates**: Re-run SDR generation to capture changes
- **Diff scope**: Inventory diff only works for same-data-view snapshot comparisons

## Troubleshooting

### "Could not import derived field inventory"

The inventory module is not available. Ensure you have the latest version:

```bash
uv pip install --upgrade cja-auto-sdr
```

### No derived fields found

The inventory only includes fields where:
- `sourceFieldType = "derived"`
- A valid `fieldDefinition` JSON array exists

Standard and custom fields are not included.

### Empty inventory

If your data view has no derived fields, the inventory section will be empty but still present in the output.

## Related Documentation

- [Inventory Overview](INVENTORY_OVERVIEW.md) - Unified guide to all inventory modules
- [Calculated Metrics Inventory](CALCULATED_METRICS_INVENTORY.md) - Document calculated metrics
- [Segments Inventory](SEGMENTS_INVENTORY.md) - Document segment filters
- [Diff Comparison Guide](DIFF_COMPARISON.md) - Snapshot diff documentation
- [CLI Reference](CLI_REFERENCE.md) - Full CLI documentation
