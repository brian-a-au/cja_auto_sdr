# Using Data View Names

**New in v3.0.9:** You can now specify data views by their **name** instead of just their ID.

## Overview

Previously, you had to use data view IDs like `dv_677ea9291244fd082f02dd42`. Now you can use the data view name directly:

```bash
# Before (still works)
cja_auto_sdr dv_677ea9291244fd082f02dd42

# Now (new feature)
cja_auto_sdr "Production Analytics"
```

## Benefits

- **Easier to remember** - Names are more meaningful than long IDs
- **More readable** - Scripts and documentation are clearer
- **Flexible** - Mix IDs and names in the same command

## How It Works

When you provide a data view name:

1. The tool connects to CJA and fetches all accessible data views
2. It searches for data views with an **exact name match** (case-sensitive)
3. If one data view matches, it's processed
4. If multiple data views match, **all are processed**
5. If no data views match, an error is shown

## Usage Examples

### Single Data View by Name

```bash
# macOS/Linux
uv run cja_auto_sdr "Production Analytics"

# Windows
python cja_sdr_generator.py "Production Analytics"
```

### Multiple Data Views by Name

```bash
cja_auto_sdr "Production" "Staging" "Test Environment"
```

### Mix IDs and Names

```bash
cja_auto_sdr dv_12345 "Production Analytics" dv_67890 "Test"
```

### Names with Special Characters

```bash
# Use quotes for names with spaces or special characters
cja_auto_sdr "Production - North America"
cja_auto_sdr "Test (v2.0)"
```

## Handling Duplicate Names

If multiple data views share the same name, all matching views will be processed:

```bash
$ cja_auto_sdr "Production"

Resolving 1 data view name(s)...
INFO - Name 'Production' matched 3 data views: ['dv_prod001', 'dv_prod002', 'dv_prod003']

Data view name resolution:
  ✓ 'Production' → 3 matching data views:
      - dv_prod001
      - dv_prod002
      - dv_prod003

Processing 3 data view(s) total...
```

This is useful when you have multiple environments with the same name (e.g., different sandboxes) and want to process all of them at once.

## Listing Available Names

To see all accessible data view names and IDs:

```bash
# macOS/Linux
uv run cja_auto_sdr --list-dataviews

# Windows
python cja_sdr_generator.py --list-dataviews
```

Output:
```
Found 5 accessible data view(s):

ID                                            Name                                     Owner
----------------------------------------------------------------------------------------------------
dv_677ea9291244fd082f02dd42                   Production Analytics                     admin@company.com
dv_789bcd123456ef7890ab                       Test Environment                         admin@company.com
dv_abc123def456789                            Staging                                  admin@company.com
```

## Important Notes

### Case Sensitivity

Name matching is **case-sensitive**. These are different:
- `Production Analytics` ✓
- `production analytics` ✗ (will not match)
- `PRODUCTION ANALYTICS` ✗ (will not match)

### Exact Match Required

Names must match **exactly**:
- `Production Analytics` ✓
- `Production` ✗ (will not match "Production Analytics")
- `Analytics` ✗ (will not match "Production Analytics")

### Quotes Recommended

Always use quotes around names to avoid shell interpretation issues:

```bash
# Good
cja_auto_sdr "Production Analytics"

# May fail if name has spaces
cja_auto_sdr Production Analytics  # Shell interprets as two separate arguments
```

## Error Handling

### Name Not Found

```bash
$ cja_auto_sdr "NonexistentView"

ERROR: No valid data views found

Possible issues:
  - Data view name(s) not found or you don't have access
  - Configuration issue preventing data view lookup

Try running: python cja_sdr_generator.py --list-dataviews
  to see all accessible data views
```

**Solution:** Run `--list-dataviews` to see available names and ensure exact spelling.

### Configuration Error

If the tool can't connect to CJA to resolve names, you'll see connection errors. Ensure your `config.json` is set up correctly.

## Batch Processing with Names

Names work seamlessly with batch processing:

```bash
# Process multiple environments by name
cja_auto_sdr "Production" "Staging" "Test" --workers 4

# Mix with IDs
cja_auto_sdr dv_prod123 "Staging Analytics" dv_test456 --batch
```

## Dry Run with Names

Test name resolution without generating reports:

```bash
cja_auto_sdr "Production Analytics" --dry-run
```

Output:
```
Resolving 1 data view name(s)...
INFO - Name 'Production Analytics' resolved to ID: dv_677ea9291244fd082f02dd42

Data view name resolution:
  ✓ 'Production Analytics' → dv_677ea9291244fd082f02dd42

Processing 1 data view(s) total...

============================================================
DRY RUN MODE - No files will be generated
============================================================
✓ Configuration valid
✓ API connection successful
✓ Data view "Production Analytics" found and accessible
✓ All pre-flight checks passed

Dry run complete. Remove --dry-run to generate the SDR.
```

## API Considerations

Name resolution requires an additional API call to fetch all data views. This adds minimal overhead:
- ~1-2 seconds for the initial lookup
- Results can be cached with `--enable-cache` for repeated runs

## Backward Compatibility

Using data view IDs still works exactly as before. This feature is purely additive:

```bash
# Old way - still works perfectly
cja_auto_sdr dv_677ea9291244fd082f02dd42

# New way - also works
cja_auto_sdr "Production Analytics"
```

## Use Cases

### Scheduled Reports

More readable cron jobs:

```bash
# Before
0 2 * * * cd /path/to/cja_auto_sdr && uv run cja_auto_sdr dv_677ea9291244fd082f02dd42

# After (more maintainable)
0 2 * * * cd /path/to/cja_auto_sdr && uv run cja_auto_sdr "Production Analytics"
```

### CI/CD Pipelines

Clearer pipeline configurations:

```yaml
# .github/workflows/sdr-generation.yml
jobs:
  generate:
    steps:
      - name: Generate SDRs
        run: |
          cja_auto_sdr "Production" "Staging"
```

### Documentation

More understandable scripts:

```bash
#!/bin/bash
# Generate SDRs for all environments
cja_auto_sdr "Production - North America" \
             "Production - Europe" \
             "Production - APAC"
```

## See Also

- [CLI Reference](CLI_REFERENCE.md) - Complete command-line options
- [Batch Processing Guide](BATCH_PROCESSING_GUIDE.md) - Processing multiple data views
- [Quick Start Guide](QUICKSTART_GUIDE.md) - Getting started
