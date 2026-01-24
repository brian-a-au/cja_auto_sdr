# Quick Reference Card

Single-page command cheat sheet for CJA SDR Generator v3.0.14.

## Two Main Modes

| Mode | Purpose | Output |
|------|---------|--------|
| **SDR Generation** | Document a data view's dimensions, metrics, and calculated metrics | Excel, CSV, JSON, HTML, Markdown reports |
| **Diff Comparison** | Compare two data views or snapshots to identify changes | Side-by-side comparison showing added, removed, and modified components |

**SDR Generation** creates a Solution Design Reference—a comprehensive inventory of all components in a data view. Use this for documentation, audits, and onboarding.

**Diff Comparison** identifies what changed between two data views or between a current state and a saved snapshot. Use this for change tracking, QA validation, and migration verification.

## Running Commands

You have three equivalent options:

| Method | Command | Notes |
|--------|---------|-------|
| **uv run** | `uv run cja_auto_sdr ...` | Works immediately on macOS/Linux, may have issues on Windows |
| **Activated venv** | `cja_auto_sdr ...` | After activating: `source .venv/bin/activate` (Unix) or `.venv\Scripts\activate` (Windows) |
| **Direct script** | `python cja_sdr_generator.py ...` | Most reliable on Windows |

This guide uses `uv run`. Windows users should substitute with `python cja_sdr_generator.py`. The command examples below omit the prefix for brevity.

## Essential Commands (SDR Generation)

```bash
# Generate SDR for a single data view
cja_auto_sdr dv_12345

# Generate and open file immediately
cja_auto_sdr dv_12345 --open

# Process multiple data views in parallel
cja_auto_sdr dv_12345 dv_67890 dv_abcde

# Use data view names instead of IDs
cja_auto_sdr "Production Analytics"

# Quick stats (no full report)
cja_auto_sdr dv_12345 --stats

# List all accessible data views
cja_auto_sdr --list-dataviews

# List data views as JSON (for scripting)
cja_auto_sdr --list-dataviews --format json

# Interactively select data views from a list
cja_auto_sdr --interactive

# Validate config without processing
cja_auto_sdr --validate-config
```

## Diff Comparison Commands (Diff Mode)

```bash
# Compare two data views
cja_auto_sdr --diff dv_12345 dv_67890

# Compare using names
cja_auto_sdr --diff "Production" "Staging"

# Save snapshot for later comparison
cja_auto_sdr dv_12345 --snapshot ./baseline.json

# Compare current state to snapshot
cja_auto_sdr dv_12345 --diff-snapshot ./baseline.json

# Compare against most recent snapshot (auto-finds it)
cja_auto_sdr dv_12345 --compare-with-prev

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

| Option | Purpose | Mode |
|--------|---------|------|
| `--output-dir PATH` | Save output to specific directory | Both |
| `--output PATH` | Output file path; use `-` for stdout (JSON/CSV) | Both |
| `--format FORMAT` | Output format (see note below) | Both |
| `--open` | Open generated file(s) in default application | SDR |
| `--stats` | Quick statistics only (no full report) | SDR |
| `--interactive`, `-i` | Interactively select data views from a numbered list | Both |
| `--config-file PATH` | Use custom config file (default: config.json) | Both |
| `--log-level LEVEL` | Set logging: `DEBUG`, `INFO`, `WARNING`, `ERROR` | Both |
| `--log-format FORMAT` | Log output: `text` (default) or `json` (structured) | Both |
| `--workers N` | Parallel workers: `auto` (default) or `1-256` | SDR only |
| `--skip-validation` | Skip data quality checks (faster) | SDR only |
| `--continue-on-error` | Don't stop on failures in batch mode | SDR only |

### Diff-Specific Options

| Option | Purpose |
|--------|---------|
| `--changes-only` | Hide unchanged components, show only differences |
| `--compare-with-prev` | Compare against most recent snapshot in --snapshot-dir |
| `--diff-labels A B` | Custom labels for comparison columns (default: data view names) |
| `--auto-snapshot` | Automatically save snapshots during diff for future comparisons |
| `--warn-threshold PERCENT` | Exit with code 3 if change % exceeds threshold (for CI/CD) |
| `--no-color` | Disable ANSI color codes in console output |
| `--format-pr-comment` | Output in GitHub/GitLab PR comment format |

### Format Support by Mode

| Format | SDR | Diff | Description |
|--------|-----|------|-------------|
| `excel` | ✅ (default) | ✅ | Excel workbook |
| `csv` | ✅ | ✅ | Comma-separated values |
| `json` | ✅ | ✅ | JSON for integrations |
| `html` | ✅ | ✅ | Browser-viewable |
| `markdown` | ✅ | ✅ | Documentation-ready |
| `console` | ❌ | ✅ (default) | Terminal output |
| `all` | ✅ | ✅ | All formats |

### Format Aliases (Shortcuts)

| Alias | Generates | Use Case |
|-------|-----------|----------|
| `reports` | excel + markdown | Documentation and sharing |
| `data` | csv + json | Data pipelines and integrations |
| `ci` | json + markdown | CI/CD logs and PR comments |

## Quick Recipes

```bash
# Fast processing (skip validation)
cja_auto_sdr dv_12345 --skip-validation

# Generate and open immediately
cja_auto_sdr dv_12345 --open

# Quick stats check before full generation
cja_auto_sdr dv_12345 --stats

# Stats as JSON to stdout (for scripting)
cja_auto_sdr dv_12345 --stats --output -

# List data views and pipe to jq
cja_auto_sdr --list-dataviews --output - | jq '.dataViews[].name'

# All output formats
cja_auto_sdr dv_12345 --format all

# Debug mode (verbose logging)
cja_auto_sdr dv_12345 --log-level DEBUG

# JSON logging (for Splunk, ELK, CloudWatch)
cja_auto_sdr dv_12345 --log-format json

# Dry run (validate only, no output)
cja_auto_sdr dv_12345 --dry-run

# Batch with custom parallelism (default: auto-detect)
cja_auto_sdr dv_* --workers 8 --continue-on-error

# Production mode (minimal logging)
cja_auto_sdr dv_12345 --production

# Custom output directory (macOS/Linux)
cja_auto_sdr dv_12345 --output-dir ./reports/$(date +%Y%m%d)

# Custom output directory (Windows PowerShell)
cja_auto_sdr dv_12345 --output-dir ./reports/$(Get-Date -Format "yyyyMMdd")
```

## Environment Variables

```bash
# Credentials (override config file)
export ORG_ID=your_org_id@AdobeOrg
export CLIENT_ID=your_client_id
export SECRET=your_client_secret
export SCOPES="your_scopes_from_developer_console"

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

See [CONFIGURATION.md](CONFIGURATION.md) for detailed setup of `config.json` and environment variables.

## Output Files

| Format | File Pattern | Description |
|--------|--------------|-------------|
| Excel | `SDR_<name>_<date>.xlsx` | Full report with Data Quality sheet |
| CSV | `SDR_<name>_<date>.csv` | Flat component list |
| JSON | `SDR_<name>_<date>.json` | Machine-readable format |
| HTML | `SDR_<name>_<date>.html` | Browser-viewable report |
| Markdown | `SDR_<name>_<date>.md` | Documentation-ready format |

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (diff: no changes found) |
| 1 | Error (config, API, or processing failure) |
| 2 | Diff: changes found |
| 3 | Diff: changes exceeded threshold |

## More Information

- Configuration: [CONFIGURATION.md](CONFIGURATION.md) - config.json, environment variables
- Full CLI docs: [CLI_REFERENCE.md](CLI_REFERENCE.md)
- Diff comparison: [DIFF_COMPARISON.md](DIFF_COMPARISON.md)
- Troubleshooting: [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- Batch processing: [BATCH_PROCESSING_GUIDE.md](BATCH_PROCESSING_GUIDE.md)
- Data quality: [DATA_QUALITY.md](DATA_QUALITY.md)
