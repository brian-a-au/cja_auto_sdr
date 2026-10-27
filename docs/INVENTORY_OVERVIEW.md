# Component Inventory Overview

This guide provides a unified view of the three component inventory modules available in CJA SDR Generator: **Calculated Metrics**, **Segments**, and **Derived Fields**.

## Introduction

Component inventories provide comprehensive documentation of CJA analytics components beyond what appears in the standard SDR output. Each inventory module analyzes component definitions, calculates complexity scores, and generates human-readable summaries to support governance, documentation, and maintenance workflows.

| Inventory | CLI Flag | Source | Diff Support |
|-----------|----------|--------|--------------|
| [Calculated Metrics](./CALCULATED_METRICS_INVENTORY.md) | `--include-calculated` | CJA API (`getCalculatedMetrics`) | Yes (same DV only)† |
| [Segments](./SEGMENTS_INVENTORY.md) | `--include-segments` | CJA API (`getFilters`) | Yes (same DV only)† |
| [Derived Fields](./DERIVED_FIELDS_INVENTORY.md) | `--include-derived` | Data View components | No* |
| **All Inventories** | `--include-all-inventory` | All sources | Yes (smart mode)‡ |

> *Derived fields appear in standard Metrics/Dimensions SDR output, so changes are captured in the standard diff. The inventory provides additional logic analysis not available elsewhere.
>
> †**Same Data View Only:** Inventory diff is only supported for snapshot comparisons of the **same data view** over time (`--diff-snapshot`, `--compare-snapshots`, `--compare-with-prev`). Cross-data-view comparison (`--diff dv_A dv_B`) does not support inventory options because calculated metric and segment IDs are data-view-scoped and cannot be reliably matched across different data views.
>
> ‡**Smart mode detection:** `--include-all-inventory` enables all three inventories in SDR mode, and enables only calculated metrics + segments in snapshot/diff modes (derived fields are excluded).

## When to Use Each Inventory

### [Calculated Metrics Inventory](./CALCULATED_METRICS_INVENTORY.md)

Use when you need to:

- Document metric formulas and their complexity
- Audit metric governance (owners, approval status, sharing)
- Identify metrics referencing specific base metrics or segments
- Track calculated metric changes over time (snapshot diff)

**Key features:**

- Formula expression reconstruction (`revenue / visits`)
- Metric and segment reference extraction
- Governance metadata (owner, tags, approved, shared)

```bash
cja_auto_sdr dv_12345 --include-calculated
```

→ See [Calculated Metrics Inventory](./CALCULATED_METRICS_INVENTORY.md) for output columns, formula summary examples, and CJA function reference.

### [Segments Inventory](./SEGMENTS_INVENTORY.md)

Use when you need to:

- Document segment filter logic and container types
- Audit segment governance across the organization
- Identify complex segments that may need review
- Track segment changes over time (snapshot diff)

**Key features:**

- Definition summary generation
- Container type identification (Hit/Visit/Person)
- Dimension and metric reference tracking
- Governance metadata (owner, tags, approved, shared)

```bash
cja_auto_sdr dv_12345 --include-segments
```

→ See [Segments Inventory](./SEGMENTS_INVENTORY.md) for output columns, definition summary examples, and function reference.

### [Derived Fields Inventory](./DERIVED_FIELDS_INVENTORY.md)

Use when you need to:

- Document derived field logic and transformations
- Identify complex Case When rules and lookup configurations
- Audit schema field dependencies
- Review field transformation chains

**Key features:**

- Logic summary generation for 20+ function types
- Schema field reference tracking
- Branch count and nesting depth analysis
- Rule name extraction from definitions

```bash
cja_auto_sdr dv_12345 --include-derived
```

→ See [Derived Fields Inventory](./DERIVED_FIELDS_INVENTORY.md) for output columns, logic summary examples, and CJA function reference.

## Feature Comparison

### Governance Metadata Support

| Field | Calculated Metrics | Segments | Derived Fields |
|-------|-------------------|----------|----------------|
| Description | Yes | Yes | Yes |
| Owner | Yes | Yes | No* |
| Owner ID | Yes | Yes | No |
| Approved | Yes | Yes | No |
| Tags | Yes | Yes | No |
| Created | Yes | Yes | No |
| Modified | Yes | Yes | No |
| Shares | Yes | Yes | No |
| Shared To Count | Yes | Yes | No |

> *Derived fields are extracted from data view components, which have different available metadata than the dedicated calculated metrics and segments APIs.

### Complexity Score Factors

Each inventory uses weighted factors to calculate a 0-100 complexity score:

#### [Calculated Metrics](./CALCULATED_METRICS_INVENTORY.md#complexity-score)

| Factor | Weight | Max Value |
|--------|--------|-----------|
| Operators | 25% | 50 |
| Metric references | 25% | 10 |
| Nesting depth | 20% | 8 |
| Functions | 15% | 15 |
| Segments | 10% | 5 |
| Conditionals | 5% | 5 |

#### [Segments](./SEGMENTS_INVENTORY.md#complexity-score)

| Factor | Weight | Max Value |
|--------|--------|-----------|
| Predicates | 30% | 50 |
| Logic operators | 20% | 20 |
| Nesting depth | 20% | 8 |
| Dimension refs | 10% | 15 |
| Metric refs | 10% | 5 |
| Regex patterns | 10% | 5 |

#### [Derived Fields](./DERIVED_FIELDS_INVENTORY.md#complexity-score)

| Factor | Weight | Max Value |
|--------|--------|-----------|
| Operators | 30% | 200 |
| Branches | 25% | 50 |
| Nesting depth | 20% | 5 |
| Functions | 10% | 20 |
| Schema fields | 10% | 10 |
| Regex patterns | 5% | 5 |

### Reference Tracking

| Reference Type | Calculated Metrics | Segments | Derived Fields |
|----------------|-------------------|----------|----------------|
| Metrics | Yes | Yes | No |
| Segments | Yes | Yes | No |
| Dimensions | No | Yes | No |
| Schema fields | No | No | Yes |
| Lookup tables | No | No | Yes |
| Component refs | No | No | Yes |

### Summary Column

All three inventory modules provide a standardized `summary` column for cross-module queries:

| Module | Module-Specific Column | Standardized Alias | Details |
|--------|----------------------|-------------------|---------|
| Calculated Metrics | `formula_summary` | `summary` | [Formula examples](./CALCULATED_METRICS_INVENTORY.md#formula-summary) |
| Segments | `definition_summary` | `summary` | [Definition examples](./SEGMENTS_INVENTORY.md#definition-summary-examples) |
| Derived Fields | `logic_summary` | `summary` | [Logic examples](./DERIVED_FIELDS_INVENTORY.md#logic-summary) |

This enables queries like:
```python
# Find all components with "revenue" in their summary
for df in [calc_metrics_df, segments_df, derived_df]:
    matches = df[df['summary'].str.contains('revenue', case=False, na=False)]
```

## Combined Workflows

### Governance Audit

Generate a complete governance report across all component types:

```bash
# Full governance audit (shorthand)
cja_auto_sdr dv_12345 \
    --include-all-inventory \
    --format excel \
    --output governance_audit.xlsx

# Equivalent longhand
cja_auto_sdr dv_12345 \
    --include-calculated \
    --include-segments \
    --include-derived \
    --format excel \
    --output governance_audit.xlsx
```

Review the output for:
- Unapproved calculated metrics and segments
- Components without descriptions
- Components not shared with appropriate teams
- High complexity components that may need documentation

### Complexity Management

Identify components that may need simplification or documentation:

```bash
# Generate inventory with all components (shorthand)
cja_auto_sdr dv_12345 \
    --include-all-inventory \
    --format json \
    --output complexity_review.json

# Quick summary of complexity counts
cja_auto_sdr dv_12345 --include-all-inventory --inventory-summary
```

**Complexity Score Guidelines:**

| Score | Level | Recommendation |
|-------|-------|----------------|
| 0-25 | Low | Standard components, minimal documentation needed |
| 25-50 | Moderate | Consider adding description if missing |
| 50-75 | Elevated | Should have documentation and be reviewed periodically |
| 75-100 | High | Requires documentation, consider simplification |

**When High Complexity is Acceptable:**
- Marketing channel classification rules (many branches expected)
- Product taxonomy lookups (large lookup tables)
- Multi-metric calculations (e.g., weighted averages)

**When High Complexity is Concerning:**
- Simple calculations with unnecessary nesting
- Duplicate logic that could be consolidated
- Segments with regex patterns that could use simpler operators

### Change Tracking (Snapshot Diff)

Track changes to calculated metrics and segments over time. See [Diff Comparison Guide](./DIFF_COMPARISON.md#inventory-diff-snapshot-only) for complete details.

> **Important: Same Data View Only.** Inventory diff only works for snapshot comparisons of the **same data view** over time. Cross-data-view comparison (`--diff dv_A dv_B`) does not support inventory options because component IDs are data-view-scoped.

```bash
# Create baseline snapshot
cja_auto_sdr dv_12345 \
    --snapshot baseline_$(date +%Y%m%d).json \
    --include-all-inventory

# Later: compare against baseline
cja_auto_sdr dv_12345 \
    --diff-snapshot baseline_20260101.json \
    --include-all-inventory
```

This reveals:
- New calculated metrics and segments
- Removed components
- Modified formulas and definitions
- Changed governance settings (owner, approval, sharing)

> **Note:** Derived fields inventory does not support diff mode because derived field changes are already captured in the standard Metrics/Dimensions diff output. See [Derived Fields - Snapshot Diff Support](./DERIVED_FIELDS_INVENTORY.md#snapshot-diff-support) for details.

### Inventory-Only Mode

Generate focused inventory documentation without standard SDR sheets:

```bash
# Just the inventories (shorthand)
cja_auto_sdr dv_12345 --include-all-inventory --inventory-only

# Equivalent longhand
cja_auto_sdr dv_12345 \
    --inventory-only \
    --include-calculated \
    --include-segments \
    --include-derived
```

## Inventory Status in SDR Output

When an SDR run requests an optional inventory, the output records whether the operation finished:

- `completed`: the inventory operation finished. The result may be empty, in which case the sheet says "No ... found for this data view". `completed` does not mean every upstream record parsed; per-record completeness is not tracked yet.
- `failed`: collection failed (including a missing inventory module). The sheet or JSON section says "... inventory unavailable" with the note "Inventory collection failed; see logs. This is not an empty result." Treat the contents as unknown, not empty.

Status appears as `Derived Fields Inventory Status`, `Calculated Metrics Inventory Status` and `Segments Inventory Status` metadata rows (only for requested inventories) and as per-result `inventory_statuses` in the run summary. A failed optional inventory does not change partial reasons or exit codes.

## Quick Reference Links

- [Calculated Metrics Inventory](./CALCULATED_METRICS_INVENTORY.md)
- [Segments Inventory](./SEGMENTS_INVENTORY.md)
- [Derived Fields Inventory](./DERIVED_FIELDS_INVENTORY.md)
- [Diff Comparison Guide](./DIFF_COMPARISON.md)
- [CLI Reference](./CLI_REFERENCE.md)
