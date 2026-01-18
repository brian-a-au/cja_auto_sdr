# Quick Reference Card

Single-page command cheat sheet for CJA SDR Generator v3.0.10.

## Essential Commands

```bash
# Generate SDR for a single data view
cja_auto_sdr dv_12345

# Process multiple data views in parallel
cja_auto_sdr dv_12345 dv_67890 dv_abcde

# Use data view names instead of IDs
cja_auto_sdr "Production Analytics"

# List all accessible data views
cja_auto_sdr --list-dataviews

# Validate config without processing
cja_auto_sdr --validate-config
```

## Diff Comparison Commands

```bash
# Compare two data views
cja_auto_sdr --diff dv_12345 dv_67890

# Compare using names
cja_auto_sdr --diff "Production" "Staging"

# Save snapshot for later comparison
cja_auto_sdr dv_12345 --snapshot ./baseline.json

# Compare current state to snapshot
cja_auto_sdr dv_12345 --diff-snapshot ./baseline.json

# Compare two snapshots (no API calls)
cja_auto_sdr --compare-snapshots ./old.json ./new.json

# Auto-save snapshots during diff
cja_auto_sdr --diff dv_12345 dv_67890 --auto-snapshot

# Show only changes (hide unchanged)
cja_auto_sdr --diff dv_12345 dv_67890 --changes-only

# Custom labels in diff output
cja_auto_sdr --diff dv_12345 dv_67890 --diff-labels "Before" "After"
```

## Common Options

| Option | Purpose |
|--------|---------|
| `--output-dir PATH` | Save output to specific directory |
| `--format FORMAT` | Output format: `excel`, `csv`, `json`, `html`, `all` |
| `--config-file PATH` | Use custom config file (default: config.json) |
| `--log-level LEVEL` | Set logging: `DEBUG`, `INFO`, `WARNING`, `ERROR` |
| `--skip-validation` | Skip data quality checks (faster) |
| `--continue-on-error` | Don't stop on failures in batch mode |

## Quick Recipes

```bash
# Fast processing (skip validation)
cja_auto_sdr dv_12345 --skip-validation

# All output formats
cja_auto_sdr dv_12345 --format all

# Debug mode (verbose logging)
cja_auto_sdr dv_12345 --log-level DEBUG

# Dry run (validate only, no output)
cja_auto_sdr dv_12345 --dry-run

# Batch with custom parallelism
cja_auto_sdr dv_* --workers 8 --continue-on-error

# Production mode (minimal logging)
cja_auto_sdr dv_12345 --production

# Custom output directory
cja_auto_sdr dv_12345 --output-dir ./reports/$(date +%Y%m%d)
```

## Environment Variables

```bash
# Credentials (override config file)
export ORG_ID=your_org_id@AdobeOrg
export CLIENT_ID=your_client_id
export SECRET=your_client_secret
export SCOPES="openid,AdobeID,read_organizations"

# Optional settings
export OUTPUT_DIR=./reports
export LOG_LEVEL=INFO
```

## Setup Commands

```bash
# Generate sample config file
cja_auto_sdr --sample-config

# Validate configuration and API connection
cja_auto_sdr --validate-config

# Test specific data views without generating
cja_auto_sdr dv_12345 --dry-run
```

## Output Files

| Format | File Pattern | Description |
|--------|--------------|-------------|
| Excel | `SDR_<name>_<date>.xlsx` | Full report with Data Quality sheet |
| CSV | `SDR_<name>_<date>.csv` | Flat component list |
| JSON | `SDR_<name>_<date>.json` | Machine-readable format |
| HTML | `SDR_<name>_<date>.html` | Browser-viewable report |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (diff: no changes found) |
| 1 | Error (config, API, or processing failure) |
| 2 | Diff: changes found |
| 3 | Diff: changes exceeded threshold |

## More Information

- Full CLI docs: [CLI_REFERENCE.md](CLI_REFERENCE.md)
- Diff comparison: [DIFF_COMPARISON.md](DIFF_COMPARISON.md)
- Troubleshooting: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- Batch processing: [BATCH_PROCESSING_GUIDE.md](BATCH_PROCESSING_GUIDE.md)
- Data quality: [DATA_QUALITY.md](DATA_QUALITY.md)
