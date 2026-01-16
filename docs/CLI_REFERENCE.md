# CLI Reference

Complete command-line interface documentation for the CJA SDR Generator.

## Basic Syntax

```bash
cja_auto_sdr [OPTIONS] DATA_VIEW_ID [DATA_VIEW_ID ...]
```

> **Running commands:** You have two equivalent options:
> - `uv run cja_auto_sdr ...` — works immediately, no activation needed
> - `cja_auto_sdr ...` — after activating the venv: `source .venv/bin/activate`
>
> Examples in this guide omit `uv run` for brevity.

### Alternative Invocations

```bash
# Hyphenated version (identical functionality)
cja-auto-sdr [OPTIONS] DATA_VIEW_ID [...]

# Direct Python invocation
python cja_sdr_generator.py [OPTIONS] DATA_VIEW_ID [...]
```

## Arguments

### Required

| Argument | Description |
|----------|-------------|
| `DATA_VIEW_ID` | One or more data view IDs (must start with `dv_`) |

## Options

### General

| Option | Description | Default |
|--------|-------------|---------|
| `-h, --help` | Show help message and exit | - |
| `--version` | Show program version and exit | - |
| `-q, --quiet` | Suppress output except errors | False |

### Processing

| Option | Description | Default |
|--------|-------------|---------|
| `--batch` | Enable parallel batch processing | Auto-detected |
| `--workers N` | Number of parallel workers (1-256) | 4 |
| `--continue-on-error` | Continue if a data view fails | False |
| `--skip-validation` | Skip data quality validation (20-30% faster) | False |

### Output

| Option | Description | Default |
|--------|-------------|---------|
| `--output-dir PATH` | Output directory for generated files | Current directory |
| `--format FORMAT` | Output format: excel, csv, json, html, markdown, all | excel |
| `--max-issues N` | Limit issues to top N by severity (0=all) | 0 |

### Configuration

| Option | Description | Default |
|--------|-------------|---------|
| `--config-file PATH` | Path to configuration file | myconfig.json |
| `--log-level LEVEL` | DEBUG, INFO, WARNING, ERROR, CRITICAL | INFO |
| `--production` | Minimal logging for performance | False |

### Validation & Testing

| Option | Description | Default |
|--------|-------------|---------|
| `--dry-run` | Validate config without generating reports | False |
| `--validate-only` | Alias for --dry-run | False |
| `--validate-config` | Validate config and API connectivity (no data view required) | False |
| `--list-dataviews` | List accessible data views and exit | False |
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

### Environment Variables

**Credentials (take precedence over myconfig.json):**

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
# Basic usage
cja_auto_sdr dv_677ea9291244fd082f02dd42

# With custom output directory
cja_auto_sdr dv_12345 --output-dir ./reports

# With custom config file
cja_auto_sdr dv_12345 --config-file ./prod_config.json

# With debug logging
cja_auto_sdr dv_12345 --log-level DEBUG
```

### Multiple Data Views

```bash
# Automatic batch processing (detected from multiple IDs)
cja_auto_sdr dv_12345 dv_67890 dv_abcde

# Explicit batch mode
cja_auto_sdr --batch dv_12345 dv_67890 dv_abcde

# Custom worker count
cja_auto_sdr --batch dv_12345 dv_67890 --workers 8

# Continue on errors
cja_auto_sdr --batch dv_* --continue-on-error
```

### Discovery Commands

```bash
# Validate configuration and API connectivity (no data view needed)
cja_auto_sdr --validate-config

# List all accessible data views
cja_auto_sdr --list-dataviews

# Generate sample configuration
cja_auto_sdr --sample-config

# Validate config without generating report
cja_auto_sdr dv_12345 --dry-run
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
  dv_prod_12345 dv_staging_67890 dv_dev_abcde \
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
| 0 | Success |
| 1 | General error |
| 2 | Configuration error |
| 3 | Authentication error |
| 4 | Data view not found |

## See Also

- [Installation Guide](INSTALLATION.md)
- [Batch Processing Guide](BATCH_PROCESSING_GUIDE.md)
- [Output Formats](OUTPUT_FORMATS.md)
- [Performance Guide](PERFORMANCE.md)
