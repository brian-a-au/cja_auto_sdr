# Quick Reference Card

Single-page command cheat sheet for CJA SDR Generator v3.0.8.

## Essential Commands

```bash
# Generate SDR for a single data view
cja_auto_sdr dv_12345

# Process multiple data views in parallel
cja_auto_sdr dv_12345 dv_67890 dv_abcde

# List all accessible data views
cja_auto_sdr --list-dataviews

# Validate config without processing
cja_auto_sdr --validate-config
```

## Common Options

| Option | Purpose |
|--------|---------|
| `--output-dir PATH` | Save output to specific directory |
| `--format FORMAT` | Output format: `excel`, `csv`, `json`, `html`, `all` |
| `--config-file PATH` | Use custom config file (default: myconfig.json) |
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
| 0 | Success |
| 1 | Error (config, API, or processing failure) |

## More Information

- Full CLI docs: `docs/CLI_REFERENCE.md`
- Troubleshooting: `docs/TROUBLESHOOTING.md`
- Batch processing: `docs/BATCH_PROCESSING_GUIDE.md`
- Data quality: `docs/DATA_QUALITY.md`
