# Data Quality Validation

Comprehensive guide to the automated data quality checks performed by the CJA SDR Generator.

## Overview

The generator performs 8+ automated validation checks on your CJA components, identifying issues before they impact your analytics. Each issue is classified by severity and includes actionable recommendations.

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

### 7. Field Existence Validation

**What it checks**: Verifies expected columns are present in API response.

| Aspect | Details |
|--------|---------|
| Severity | CRITICAL |
| Impact | May indicate API changes or permissions issues |
| Example | Expected "attribution" field missing from response |

### 8. Data Completeness

**What it checks**: Overall assessment of data quality across all checks.

| Aspect | Details |
|--------|---------|
| Severity | Multiple levels |
| Impact | Varies by specific issue |
| Example | 15% of components missing descriptions |

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

## Understanding the Data Quality Sheet

The Excel output includes a dedicated "Data Quality" sheet with these columns:

| Column | Description |
|--------|-------------|
| Severity | Issue severity level (CRITICAL, HIGH, MEDIUM, LOW) |
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
Item Name: metrics_undefined
Issue:     Missing required field: name
Details:   Component cannot be properly identified without a name
```

## Limiting Issues Output

For large data views with many issues, you can limit the output:

```bash
# Show only top 10 issues by severity
uv run python cja_sdr_generator.py dv_12345 --max-issues 10

# Show only top 5 critical/high issues
uv run python cja_sdr_generator.py dv_12345 --max-issues 5
```

Issues are sorted by severity (CRITICAL first) before limiting.

## Skipping Validation

For faster processing when validation isn't needed:

```bash
# Skip all validation checks (20-30% faster)
uv run python cja_sdr_generator.py dv_12345 --skip-validation
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

## Performance Considerations

The validation engine is optimized for performance:

- **Single-pass validation**: 89% fewer DataFrame scans
- **Vectorized operations**: 30-50% faster for large datasets
- **Optional caching**: 50-90% faster for repeated validations
- **Parallel processing**: Metrics and dimensions validated concurrently

See [Performance Guide](PERFORMANCE.md) for optimization options.

## See Also

- [CLI Reference](CLI_REFERENCE.md) - Validation-related options
- [Performance Guide](PERFORMANCE.md) - Validation caching
- [Output Formats](OUTPUT_FORMATS.md) - Data Quality sheet format
