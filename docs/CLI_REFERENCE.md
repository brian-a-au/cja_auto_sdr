# CLI Reference

Complete command-line interface documentation for the CJA SDR Generator.

## Basic Syntax

```bash
cja_auto_sdr [OPTIONS] DATA_VIEW_ID_OR_NAME [DATA_VIEW_ID_OR_NAME ...]
```

> **Running commands:** You have three equivalent options:
> - `uv run cja_auto_sdr ...` — works immediately on macOS/Linux, may have issues on Windows
> - `cja_auto_sdr ...` — after activating the venv: `source .venv/bin/activate` (Unix) or `.venv\Scripts\activate` (Windows)
> - `python cja_sdr_generator.py ...` — run the script directly (most reliable on Windows)
>
> This guide uses `cja_auto_sdr` for brevity. Windows users should substitute with `python cja_sdr_generator.py`.

### Alternative Invocations

```bash
# Hyphenated version (identical functionality)
cja-auto-sdr [OPTIONS] DATA_VIEW_ID_OR_NAME [...]
```

## Arguments

### Required

| Argument | Description |
|----------|-------------|
| `DATA_VIEW_ID_OR_NAME` | One or more data view IDs (e.g., `dv_12345`) or exact names (e.g., `"Production Analytics"`). If a name matches multiple data views, all will be processed. Use quotes for names with spaces. |

## Options

### General

| Option | Description | Default |
|--------|-------------|---------|
| `-h, --help` | Show help message and exit | - |
| `--version` | Show program version and exit | - |
| `-q, --quiet` | Suppress output except errors | False |
| `--open` | Open generated file(s) in default application after creation | False |

### Processing

| Option | Description | Default |
|--------|-------------|---------|
| `--batch` | Enable parallel batch processing | Auto-detected |
| `--workers N` | Number of parallel workers (1-256), or `auto` for automatic detection based on CPU cores and workload complexity | auto |
| `--continue-on-error` | Continue if a data view fails | False |
| `--skip-validation` | Skip data quality validation (20-30% faster) | False |

### Output

| Option | Description | Default |
|--------|-------------|---------|
| `--output-dir PATH` | Output directory for generated files | Current directory |
| `--output PATH` | Output file path. Use `-` or `stdout` to write to stdout (JSON/CSV only). Implies `--quiet` for stdout | - |
| `--format FORMAT` | Output format (see table below) | excel (SDR), console (diff) |
| `--stats` | Show quick statistics (metrics/dimensions count) without generating full SDR report | False |
| `--max-issues N` | Limit issues to top N by severity (0=all) | 0 |

**Format Availability by Mode:**

| Format | SDR Generation | Diff Comparison |
|--------|----------------|-----------------|
| `excel` | ✓ (default) | ✓ |
| `csv` | ✓ | ✓ |
| `json` | ✓ | ✓ |
| `html` | ✓ | ✓ |
| `markdown` | ✓ | ✓ |
| `console` | ✗ | ✓ (default) |
| `all` | ✓ | ✓ |

> **Note:** Console format is only supported for diff comparison. Using `--format console` with SDR generation will show an error with suggested alternatives.

### Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `--config-file PATH` | Path to configuration file | config.json |
| `--log-level LEVEL` | DEBUG, INFO, WARNING, ERROR, CRITICAL | INFO |
| `--log-format FORMAT` | Log output format: `text` (human-readable) or `json` (structured logging for Splunk, ELK, CloudWatch) | text |
| `--production` | Minimal logging for performance | False |

> See the [Configuration Guide](CONFIGURATION.md) for details on config.json format, environment variables, and validation rules.

### Validation & Testing

| Option | Description | Default |
|--------|-------------|---------|
| `--dry-run` | Validate config without generating reports | False |
| `--validate-only` | Alias for --dry-run | False |
| `--validate-config` | Validate config and API connectivity (no data view required) | False |
| `--list-dataviews` | List accessible data views and exit. Supports `--format json/csv` and `--output -` for machine-readable output | False |
| `-i, --interactive` | Interactively select data views from a numbered list. Supports single selection, ranges (1-5), or "all" | False |
| `--sample-config` | Generate sample config file and exit | False |

### Caching

| Option | Description | Default |
|--------|-------------|---------|
| `--enable-cache` | Enable validation result caching | False |
| `--clear-cache` | Clear cache before processing | False |
| `--cache-size N` | Maximum cached entries | 1000 |
| `--cache-ttl N` | Cache time-to-live in seconds | 3600 |

### Retry Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `--max-retries N` | Maximum API retry attempts | 3 |
| `--retry-base-delay N` | Initial retry delay in seconds | 1.0 |
| `--retry-max-delay N` | Maximum retry delay in seconds | 30.0 |

### Diff Comparison

| Option | Description | Default |
|--------|-------------|---------|
| `--diff` | Compare two data views. Requires exactly 2 data view IDs/names | False |
| `--snapshot FILE` | Save a data view snapshot to JSON file | - |
| `--diff-snapshot FILE` | Compare data view against a saved snapshot | - |
| `--compare-with-prev` | Compare data view against its most recent snapshot in --snapshot-dir | False |
| `--compare-snapshots A B` | Compare two snapshot files directly (no API calls) | - |
| `--changes-only` | Only show changed items (hide unchanged) | False |
| `--summary` | Show summary statistics only | False |
| `--ignore-fields FIELDS` | Comma-separated fields to ignore in comparison | - |
| `--diff-labels A B` | Custom labels for the two sides | Data view names |
| `--show-only TYPES` | Filter by change type: added, removed, modified (comma-separated) | All types |
| `--metrics-only` | Only compare metrics (exclude dimensions) | False |
| `--dimensions-only` | Only compare dimensions (exclude metrics) | False |
| `--extended-fields` | Include extended fields (attribution, format, bucketing, etc.) | False |
| `--side-by-side` | Show side-by-side comparison view for modified items | False |
| `--no-color` | Disable ANSI color codes in diff console output | False |
| `--quiet-diff` | Suppress output, only return exit code | False |
| `--reverse-diff` | Swap source and target comparison direction | False |
| `--warn-threshold PERCENT` | Exit with code 3 if change % exceeds threshold | - |
| `--group-by-field` | Group changes by field name instead of component | False |
| `--group-by-field-limit N` | Max items per section in --group-by-field output (0=unlimited) | 10 |
| `--diff-output FILE` | Write output to file instead of stdout | - |
| `--format-pr-comment` | Output in GitHub/GitLab PR comment format | False |
| `--auto-snapshot` | Automatically save snapshots during diff for audit trail | False |
| `--snapshot-dir DIR` | Directory for auto-saved snapshots | ./snapshots |
| `--keep-last N` | Retention: keep only last N snapshots per data view (0=all) | 0 |

### Git Integration

| Option | Description | Default |
|--------|-------------|---------|
| `--git-init` | Initialize a new Git repository for snapshots | - |
| `--git-commit` | Save snapshot and commit to Git after SDR generation | False |
| `--git-push` | Push to remote repository after committing | False |
| `--git-message MSG` | Custom commit message (auto-generated if not provided) | - |
| `--git-dir DIR` | Directory for Git snapshots | ./sdr-snapshots |

### Environment Variables

**Credentials (take precedence over config.json):**

| Variable | Description |
|----------|-------------|
| `ORG_ID` | Adobe Organization ID |
| `CLIENT_ID` | OAuth Client ID |
| `SECRET` | Client Secret |
| `SCOPES` | OAuth scopes |
| `SANDBOX` | Sandbox name (optional) |

**Configuration:**

| Variable | Description |
|----------|-------------|
| `LOG_LEVEL` | Default log level (overridden by --log-level) |
| `OUTPUT_DIR` | Default output directory (overridden by --output-dir) |

## Usage Examples

### Single Data View

```bash
# By ID
cja_auto_sdr dv_677ea9291244fd082f02dd42

# By name
cja_auto_sdr "Production Analytics"

# With custom output directory
cja_auto_sdr dv_12345 --output-dir ./reports
cja_auto_sdr "Test Environment" --output-dir ./reports

# With custom config file
cja_auto_sdr "Production Analytics" --config-file ./prod_config.json

# With debug logging
cja_auto_sdr "Staging" --log-level DEBUG
```

### Multiple Data Views

```bash
# By IDs - automatic batch processing
cja_auto_sdr dv_12345 dv_67890 dv_abcde

# By names
cja_auto_sdr "Production" "Staging" "Test Environment"

# Mix IDs and names
cja_auto_sdr dv_12345 "Staging Analytics" dv_67890

# Explicit batch mode
cja_auto_sdr --batch dv_12345 dv_67890 dv_abcde

# Custom worker count
cja_auto_sdr --batch "Production" "Staging" --workers 8

# Continue on errors
cja_auto_sdr --batch "Prod" "Stage" "Test" --continue-on-error
```

### Discovery Commands

```bash
# Validate configuration and API connectivity (no data view needed)
cja_auto_sdr --validate-config

# List all accessible data views
cja_auto_sdr --list-dataviews

# List data views in JSON format (for scripting)
cja_auto_sdr --list-dataviews --format json

# List data views to stdout for piping
cja_auto_sdr --list-dataviews --output - | jq '.dataViews[].id'

# Generate sample configuration
cja_auto_sdr --sample-config

# Validate config without generating report
cja_auto_sdr dv_12345 --dry-run
```

### Quick Statistics

```bash
# Quick stats for a single data view (no full report generated)
cja_auto_sdr dv_12345 --stats

# Stats for multiple data views
cja_auto_sdr dv_1 dv_2 dv_3 --stats

# Stats in JSON format
cja_auto_sdr dv_12345 --stats --format json

# Stats to stdout for scripting
cja_auto_sdr dv_12345 --stats --output -

# Stats in CSV format to file
cja_auto_sdr dv_12345 --stats --format csv --output stats.csv
```

### Interactive Data View Selection

```bash
# Launch interactive selection mode
cja_auto_sdr --interactive

# Interactive selection with custom output format
cja_auto_sdr --interactive --format markdown

# Interactive selection with specific output directory
cja_auto_sdr --interactive --output-dir ./reports
```

**Selection Syntax:**
- Single: `3` (selects #3)
- Multiple: `1,3,5` (selects #1, #3, #5)
- Range: `1-5` (selects #1 through #5)
- Combined: `1,3-5,7` (selects #1, #3, #4, #5, #7)
- All: `all` or `a` (selects all data views)
- Cancel: `q` or `quit` (exit without selection)

### Auto-Open Generated Files

```bash
# Generate SDR and open immediately in default app
cja_auto_sdr dv_12345 --open

# Generate Excel and open
cja_auto_sdr dv_12345 --format excel --open

# Batch processing - opens all successful files
cja_auto_sdr dv_1 dv_2 dv_3 --open
```

### Performance Optimization

```bash
# Production mode (minimal logging)
cja_auto_sdr dv_12345 --production

# Skip validation for faster processing
cja_auto_sdr dv_12345 --skip-validation

# Enable caching for repeated runs
cja_auto_sdr dv_12345 --enable-cache

# Quiet mode
cja_auto_sdr dv_12345 --quiet
```

### Output Formats

```bash
# Excel (default)
cja_auto_sdr dv_12345 --format excel

# CSV files
cja_auto_sdr dv_12345 --format csv

# JSON
cja_auto_sdr dv_12345 --format json

# HTML report
cja_auto_sdr dv_12345 --format html

# Markdown (GitHub/Confluence compatible)
cja_auto_sdr dv_12345 --format markdown

# All formats
cja_auto_sdr dv_12345 --format all
```

### Production Examples

```bash
# Full production batch
cja_auto_sdr --batch \
  dv_12345 dv_67890 dv_abcde \
  --workers 4 \
  --output-dir ./sdr_reports \
  --continue-on-error \
  --log-level WARNING

# Optimized run with caching
cja_auto_sdr dv_12345 \
  --production \
  --enable-cache \
  --skip-validation

# Read data views from file
cja_auto_sdr --batch $(cat dataviews.txt)
```

### Data View Comparison (Diff)

```bash
# Compare two live data views (by ID)
cja_auto_sdr --diff dv_12345 dv_67890

# Compare by name
cja_auto_sdr --diff "Production Analytics" "Staging Analytics"

# Mix IDs and names (both supported)
cja_auto_sdr --diff dv_12345 "Staging Analytics"
cja_auto_sdr --diff "Production Analytics" dv_67890

# Save a snapshot for later comparison (ID or name)
cja_auto_sdr dv_12345 --snapshot ./snapshots/baseline.json
cja_auto_sdr "Production Analytics" --snapshot ./snapshots/baseline.json

# Compare current state against a saved snapshot (ID or name)
cja_auto_sdr dv_12345 --diff-snapshot ./snapshots/baseline.json
cja_auto_sdr "Production Analytics" --diff-snapshot ./snapshots/baseline.json

# Compare two snapshot files directly (no API calls needed)
cja_auto_sdr --compare-snapshots ./snapshots/before.json ./snapshots/after.json
cja_auto_sdr --compare-snapshots ./snapshots/prod.json ./snapshots/staging.json --format html

# Diff with different output formats
cja_auto_sdr --diff dv_12345 dv_67890 --format html --output-dir ./reports
cja_auto_sdr --diff dv_12345 dv_67890 --format all

# Show only changes (hide unchanged items)
cja_auto_sdr --diff dv_12345 dv_67890 --changes-only

# Show summary only (no detailed changes)
cja_auto_sdr --diff dv_12345 dv_67890 --summary

# Ignore specific fields during comparison
cja_auto_sdr --diff dv_12345 dv_67890 --ignore-fields description,title

# Custom labels for source and target
cja_auto_sdr --diff dv_12345 dv_67890 --diff-labels Production Staging

# CI/CD integration (exit code 2 if differences found)
cja_auto_sdr --diff dv_12345 dv_67890 --changes-only --format json
echo $?  # 0 = no differences, 2 = differences found, 1 = error

# Filter by change type
cja_auto_sdr --diff dv_12345 dv_67890 --show-only added
cja_auto_sdr --diff dv_12345 dv_67890 --show-only removed,modified

# Filter by component type
cja_auto_sdr --diff dv_12345 dv_67890 --metrics-only
cja_auto_sdr --diff dv_12345 dv_67890 --dimensions-only

# Extended field comparison
cja_auto_sdr --diff dv_12345 dv_67890 --extended-fields

# Side-by-side view
cja_auto_sdr --diff dv_12345 dv_67890 --side-by-side
cja_auto_sdr --diff dv_12345 dv_67890 --side-by-side --format markdown

# Combined options
cja_auto_sdr --diff dv_12345 dv_67890 --extended-fields --side-by-side --show-only modified --changes-only

# Auto-snapshot: automatically save snapshots during diff for audit trail
cja_auto_sdr --diff dv_12345 dv_67890 --auto-snapshot

# Custom snapshot directory
cja_auto_sdr --diff dv_12345 dv_67890 --auto-snapshot --snapshot-dir ./history

# With retention policy (keep last 10 snapshots per data view)
cja_auto_sdr --diff dv_12345 dv_67890 --auto-snapshot --keep-last 10

# Auto-snapshot works with diff-snapshot too (saves current state)
cja_auto_sdr dv_12345 --diff-snapshot ./baseline.json --auto-snapshot
```

### Git Integration

```bash
# Initialize a new Git repository for snapshots (one-time setup)
cja_auto_sdr --git-init
cja_auto_sdr --git-init --git-dir ./my-snapshots

# Generate SDR and commit to Git
cja_auto_sdr dv_12345 --git-commit

# Generate with custom commit message
cja_auto_sdr dv_12345 --git-commit --git-message "Pre-release snapshot"

# Generate, commit, and push to remote
cja_auto_sdr dv_12345 --git-commit --git-push

# Multiple data views with Git commits
cja_auto_sdr dv_prod dv_staging dv_dev --git-commit

# Custom Git directory
cja_auto_sdr dv_12345 --git-commit --git-dir ./my-snapshots
```

## Output Files

### Excel Workbook

- **Filename**: `CJA_DataView_[Name]_[ID]_SDR.xlsx`
- **Location**: Specified by `--output-dir`
- **Sheets**: Metadata, Data Quality, DataView, Metrics, Dimensions

### Log Files

- **Single mode**: `logs/SDR_Generation_[DataViewID]_[Timestamp].log`
- **Batch mode**: `logs/SDR_Batch_Generation_[Timestamp].log`

## Expected Output

### Single Data View

```
Processing data view: dv_677ea9291244fd082f02dd42

============================================================
INITIALIZING CJA CONNECTION
============================================================
✓ API connection successful! Found 85 data view(s)
============================================================
VALIDATING DATA VIEW
============================================================
✓ Data view validated successfully!
  Name: Production Analytics
  ID: dv_677ea9291244fd082f02dd42
============================================================
✓ SDR generation complete! File saved as: CJA_DataView_Production_Analytics_dv_677ea9291244fd082f02dd42_SDR.xlsx (2.5 MB)
```

### Batch Mode

```
Processing 3 data view(s) in batch mode with 4 workers...

============================================================
BATCH PROCESSING START
============================================================
✓ dv_12345: SUCCESS (14.5s)
✓ dv_67890: SUCCESS (15.2s)
✓ dv_abcde: SUCCESS (16.1s)

============================================================
BATCH PROCESSING SUMMARY
============================================================
Total data views: 3
Successful: 3
Failed: 0
Success rate: 100.0%
Throughput: 9.7 data views per minute
============================================================
```

## Exit Codes

| Code | Meaning |
|------|---------|
| 0 | Success (diff: no differences found) |
| 1 | General error (authentication, data view not found, API errors, etc.) |
| 2 | Success with differences (diff mode only) - useful for CI/CD pipelines |
| 3 | Threshold exceeded (diff mode with `--warn-threshold`) |

> **Note:** In diff mode:
> - Exit code 2 indicates the comparison was successful but differences were found
> - Exit code 3 indicates differences exceeded the `--warn-threshold` percentage
> - This allows CI/CD pipelines to fail builds based on change magnitude

## Shell Tab-Completion

Enable tab-completion for all CLI options using the `argcomplete` package.

### Installation

```bash
# Install the completion optional dependency (from project root)
pip install .[completion]

# Or with uv
uv add argcomplete

# Or install argcomplete directly
pip install argcomplete
```

### Activation

**Bash (one-time setup):**

```bash
# Add to ~/.bashrc
eval "$(register-python-argcomplete cja_auto_sdr)"
```

**Zsh (one-time setup):**

```bash
# Add to ~/.zshrc
autoload -U bashcompinit
bashcompinit
eval "$(register-python-argcomplete cja_auto_sdr)"
```

**Global activation (all argcomplete-enabled scripts):**

```bash
# Bash
activate-global-python-argcomplete

# Then add to ~/.bashrc:
source /etc/bash_completion.d/python-argcomplete
```

### Usage

After activation, press Tab to auto-complete:

```bash
# Complete flags
cja_auto_sdr --<TAB><TAB>
--batch  --config-file  --dry-run  --format  --help  ...

# Complete flag values
cja_auto_sdr --format <TAB><TAB>
excel  csv  json  html  markdown  all

cja_auto_sdr --log-level <TAB><TAB>
DEBUG  INFO  WARNING  ERROR  CRITICAL
```

## See Also

- [Quick Reference Card](QUICK_REFERENCE.md) - Single-page command cheat sheet
- [Shell Completion Guide](SHELL_COMPLETION.md) - Enable tab-completion for bash/zsh
- [Configuration Guide](CONFIGURATION.md) - config.json, environment variables, validation rules
- [Installation Guide](INSTALLATION.md)
- [Batch Processing Guide](BATCH_PROCESSING_GUIDE.md)
- [Output Formats](OUTPUT_FORMATS.md)
- [Performance Guide](PERFORMANCE.md)
- [Data View Comparison Guide](DIFF_COMPARISON.md)
- [Git Integration Guide](GIT_INTEGRATION.md)
