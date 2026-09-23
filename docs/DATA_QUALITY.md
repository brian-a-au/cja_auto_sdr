# Data Quality Validation

Comprehensive guide to the automated data quality checks performed by the CJA SDR Generator.

## Overview

The generator performs six core automated validation checks on your CJA components, identifying issues before they impact your analytics. Each issue is classified by severity and includes actionable recommendations.

## Validation Checks

### 1. Duplicate Detection

**What it checks**: Identifies metrics or dimensions with identical names within the data view.

| Aspect | Details |
|--------|---------|
| Severity | HIGH |
| Impact | Causes confusion in reporting, makes it difficult to identify correct component |
| Example | Two metrics named "Page Views" with different IDs |

### 2. Required Fields Validation

**What it checks**: Ensures `id`, `name`, and `type` fields are present on all components.

| Aspect | Details |
|--------|---------|
| Severity | CRITICAL |
| Impact | Missing fields prevent proper component usage |
| Example | A metric without an ID cannot be referenced |

### 3. Null Value Detection

**What it checks**: Finds missing values in critical fields (id, name, title, description).

| Aspect | Details |
|--------|---------|
| Severity | MEDIUM |
| Impact | Incomplete metadata affects discoverability |
| Example | Dimension with null title field |

### 4. Missing Descriptions

**What it checks**: Identifies components without descriptions.

| Aspect | Details |
|--------|---------|
| Severity | LOW |
| Impact | Reduces documentation quality and team understanding |
| Example | Metric without explanation of what it measures |

### 5. Empty Dataset Check

**What it checks**: Detects if API returns no data for metrics or dimensions.

| Aspect | Details |
|--------|---------|
| Severity | CRITICAL |
| Impact | No components available for analysis |
| Example | Data view returns 0 metrics |

### 6. Invalid ID Check

**What it checks**: Finds components with missing or malformed IDs.

| Aspect | Details |
|--------|---------|
| Severity | HIGH |
| Impact | Components cannot be referenced properly in reports |
| Example | ID field is empty or contains invalid characters |

### No-Issue Summary Row

When no issues are detected, the report includes an informational summary row:

| Aspect | Details |
|--------|---------|
| Severity | INFO |
| Category | Data Quality |
| Issue | No data quality issues detected |
| Details | All validation checks passed successfully |

## Severity Levels

### CRITICAL (Red Background)

- **Requires immediate attention**
- Blocks core functionality
- Examples: Missing required fields, empty datasets, API errors
- **Action**: Stop and fix before continuing

### HIGH (Yellow Background)

- **Important issues affecting reliability**
- Should be addressed soon
- Examples: Duplicate names, invalid IDs
- **Action**: Plan remediation within sprint

### MEDIUM (Green Background)

- **Moderate quality issues**
- Address when convenient
- Examples: Null values in secondary fields
- **Action**: Add to backlog

### LOW (Blue Background)

- **Minor improvements recommended**
- Does not affect functionality
- Examples: Missing descriptions
- **Action**: Address during maintenance windows

### INFO (Green Background)

- **Informational status**
- Indicates validation passed with no issues found
- Example: "No data quality issues detected"
- **Action**: No remediation required

## Understanding the Data Quality Sheet

The Excel output includes a dedicated "Data Quality" sheet with these columns:

| Column | Description |
|--------|-------------|
| Severity | Issue severity level (CRITICAL, HIGH, MEDIUM, LOW, INFO) |
| Category | Type of issue (Duplicates, Missing Fields, etc.) |
| Type | Whether it affects Metrics or Dimensions |
| Item Name | Specific component(s) affected |
| Issue | Clear description of the problem |
| Details | Additional context and affected items |

## Example Issues

### Duplicate Detection

```
Severity:  HIGH
Category:  Duplicates
Type:      Metrics
Item Name: Page Views
Issue:     Duplicate name found 2 times
Details:   This metrics name appears 2 times in the data view
```

### Null Values

```
Severity:  MEDIUM
Category:  Null Values
Type:      Dimensions
Item Name: 5 items
Issue:     Null values in "description" field
Details:   5 item(s) missing description. Items: eVar1, eVar5, prop3...
```

### Missing Required Field

```
Severity:  CRITICAL
Category:  Missing Fields
Type:      Metrics
Item Name: N/A
Issue:     Required fields missing from API response
Details:   Missing fields: name
```

## Limiting Issues Output

For large data views with many issues, you can limit the output:

```bash
# Show only top 10 issues by severity
cja_auto_sdr dv_12345 --max-issues 10

# Show only top 5 critical/high issues
cja_auto_sdr dv_12345 --max-issues 5
```

Issues are sorted by severity (CRITICAL first) before limiting.

## Quality Policy File

Load quality defaults from a JSON file with `--quality-policy PATH`. This is useful for standardizing quality settings across teams or CI/CD pipelines:

```bash
cja_auto_sdr dv_12345 --quality-policy ./quality_policy.json
```

The policy file supports these keys:

```json
{
  "fail_on_quality": "HIGH",
  "quality_report": "json",
  "max_issues": 50,
  "allow_partial": false
}
```

`allow_partial` is optional and defaults to `false`.

Explicit CLI flags (`--fail-on-quality`, `--quality-report`, `--max-issues`, `--allow-partial`) always take precedence over policy file values.

`allow_partial` cannot be combined with `fail_on_quality` or `quality_report` in the same policy file.

## Production Mode

Use `--production` to reduce data quality log noise while still running all validation checks:

```bash
cja_auto_sdr dv_12345 --production
```

In production mode, individual per-issue HIGH and CRITICAL warnings are suppressed from log output. Instead, an aggregated severity summary is logged once at the end — for example, `3 HIGH and 1 CRITICAL issues detected`. The full issue details remain available in the Data Quality sheet and quality report output.

This is useful for:
- CI/CD pipelines where per-issue log lines create excessive noise
- Batch runs across many data views
- Any context where the report file is the primary output, not the log stream

To combine with a non-zero exit on quality failures:

```bash
cja_auto_sdr dv_12345 --production --fail-on-quality HIGH
```

## Skipping Validation

For faster processing when validation isn't needed:

```bash
# Skip all validation checks (20-30% faster)
cja_auto_sdr dv_12345 --skip-validation
```

Use cases for skipping validation:
- Quick documentation generation
- Automated exports where quality was previously verified
- Performance-critical batch operations

## Best Practices

### Regular Audits

- Run weekly/monthly quality checks
- Track trends over time
- Set quality thresholds for new deployments

### Addressing Issues by Severity

1. **CRITICAL**: Fix immediately before using reports
2. **HIGH**: Schedule fixes within current sprint
3. **MEDIUM**: Add to backlog, fix opportunistically
4. **LOW**: Address during documentation updates

### Quality Improvement Process

1. Generate SDR with validation
2. Export Data Quality sheet
3. Prioritize by severity
4. Create tickets for fixes
5. Re-run to verify fixes
6. Track improvement over time

## Inventory Parsing Resilience

The inventory parsers for derived fields, segments, and calculated metrics are hardened against unexpected API payload shapes. If the CJA API returns malformed or unusual data — such as non-dict list entries, non-string field values, dict-shaped arguments, non-list operands, or non-finite split indexes — the parsers handle these gracefully without crashing. Datetime metadata (`pd.Timestamp` values in created/modified fields) is coerced via `isoformat()` so timestamps are preserved rather than silently dropped.

This means inventory sheets will still be generated even when individual component definitions contain unexpected structures; malformed entries are normalized to safe defaults rather than aborting the entire run.

## Performance Considerations

The validation engine is optimized for performance:

- **Single-pass validation**: 89% fewer DataFrame scans
- **Vectorized operations**: 30-50% faster for large datasets
- **Optional caching**: 50-90% faster for repeated validations
- **Parallel processing**: Metrics and dimensions validated concurrently

See [Performance Guide](PERFORMANCE.md) for optimization options.

## See Also

- [Configuration Guide](CONFIGURATION.md) - Setup and validation commands
- [CLI Reference](CLI_REFERENCE.md) - Validation-related options
- [Performance Guide](PERFORMANCE.md) - Validation caching
- [Output Formats](OUTPUT_FORMATS.md) - Data Quality sheet format
