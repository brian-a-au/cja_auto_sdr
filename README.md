# Adobe Customer Journey Analytics SDR Generator

<img width="1024" height="572" alt="image" src="https://github.com/user-attachments/assets/54a43474-3fc6-4379-909c-452c19cdeac2" />

**Version 3.0.7** - A production-ready Python tool that automates the creation of Solution Design Reference (SDR) documents from your Adobe Customer Journey Analytics implementation.

## What It Is

A **Solution Design Reference (SDR)** is the essential documentation that bridges your business requirements and your analytics implementation. It catalogs every metric and dimension in your CJA Data View, serving as the single source of truth for what data you're collecting and how it's configured.

**The Problem:** Manually documenting CJA implementations is time-consuming, error-prone, and quickly becomes outdated. Teams waste hours exporting data, formatting spreadsheets, and cross-referencing configurations—only to repeat the process when things change.

**The Solution:** This tool connects directly to the CJA API, extracts your complete Data View configuration, validates data quality, and generates professionally formatted documentation in seconds.

### Version 3.0: From Notebook to Enterprise Tool

This project evolved from a [Jupyter notebook proof-of-concept](https://github.com/pitchmuc/CJA_Summit_2025/blob/main/notebooks/06.%20CJA%20Data%20View%20Solution%20Design%20Reference%20Generator.ipynb) into a production-ready CLI application. Version 3.0 represents a complete rewrite focused on enterprise needs:

| Aspect | Original Notebook | Version 3.0 |
|--------|------------------|-------------|
| Execution | Interactive cells | CLI with full argument parsing |
| Scale | Single Data View | Unlimited Data Views in parallel |
| Speed | Sequential (~35s each) | 3-4x faster with batch processing |
| Quality | Basic extraction | 8+ automated validation checks |
| Reliability | Manual retry | Automatic retry with exponential backoff |
| Output | Single Excel file | Excel, CSV, JSON, HTML formats |
| Automation | Copy-paste workflow | Cron, CI/CD, script-ready |

The notebook remains excellent for learning and ad-hoc exploration. Version 3.0 is for teams that need scheduled automation, multi-environment processing, and enterprise-grade reliability.

### How It Works

1. **Connects** to your CJA instance via the Adobe API
2. **Extracts** all metrics, dimensions, and configuration from your Data View(s)
3. **Validates** data quality with 8+ automated checks (duplicates, missing fields, null values)
4. **Generates** formatted documentation with color-coded quality indicators

### Key Features (v3.0)

| Category | Feature | Benefit |
|----------|---------|---------|
| **Performance** | Parallel Batch Processing | Process multiple Data Views simultaneously (3-4x faster) |
| | Validation Caching | 50-90% faster on repeated runs with intelligent result caching |
| | Optimized Validation | Single-pass DataFrame scanning (30-50% faster) |
| | Configurable Workers | Scale from 1-8+ parallel workers based on your infrastructure |
| **Quality** | 8+ Validation Checks | Detect duplicates, missing fields, null values, invalid IDs |
| | Severity Classification | CRITICAL, HIGH, MEDIUM, LOW with color-coded Excel formatting |
| | Quality Dashboard | Dedicated sheet with filtering, sorting, and actionable insights |
| **Output** | Multiple Formats | Excel, CSV, JSON, HTML—or generate all at once |
| | Professional Excel | 5 formatted sheets with conditional formatting, frozen headers, auto-filtering |
| | File Size Display | Human-readable output size (KB, MB) in success messages |
| **Reliability** | Automatic Retry | Exponential backoff with jitter for transient network failures |
| | Continue-on-Error | Batch processing continues even if individual Data Views fail |
| | Pre-flight Validation | Validates config and connectivity before processing |
| **Usability** | Dry-Run Mode | Test configuration without generating reports |
| | Discovery Commands | `--list-dataviews` and `--sample-config` for easy setup |
| | Color-Coded Output | Green/yellow/red console feedback for instant status |
| | Comprehensive Logging | Timestamped logs with rotation for audit trails |

### Who It's For

- **Analytics Teams** needing up-to-date implementation documentation
- **Consultants** managing multiple client implementations
- **Data Governance** teams requiring audit trails and quality tracking
- **DevOps Engineers** automating CJA audits in CI/CD pipelines

## Quick Start

### 1. Install Dependencies

```bash
# Install uv (if needed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Clone and setup
cd cja-auto-sdr-2026
uv sync
```

### 2. Configure Credentials

Create `myconfig.json` with your Adobe credentials:

```json
{
  "org_id": "your_org_id@AdobeOrg",
  "client_id": "your_client_id",
  "secret": "your_client_secret",
  "scopes": "openid, AdobeID, additional_info.projectedProductContext"
}
```

### 3. Run the Generator

```bash
# Single data view
uv run python cja_sdr_generator.py dv_YOUR_DATA_VIEW_ID

# Multiple data views (parallel processing)
uv run python cja_sdr_generator.py dv_ID1 dv_ID2 dv_ID3

# List available data views
uv run python cja_sdr_generator.py --list-dataviews
```

### 4. Review Output

- Check generated Excel file: `CJA_DataView_[Name]_[ID]_SDR.xlsx`
- Review logs in the `logs/` directory

## Common Use Cases

| Task | Command |
|------|---------|
| Single data view | `uv run python cja_sdr_generator.py dv_12345` |
| Batch processing | `uv run python cja_sdr_generator.py dv_1 dv_2 dv_3` |
| Custom output location | `uv run python cja_sdr_generator.py dv_12345 --output-dir ./reports` |
| Validate only (no report) | `uv run python cja_sdr_generator.py dv_12345 --dry-run` |
| Skip validation (faster) | `uv run python cja_sdr_generator.py dv_12345 --skip-validation` |
| Generate all formats | `uv run python cja_sdr_generator.py dv_12345 --format all` |

## Documentation

| Guide | Description |
|-------|-------------|
| [Installation Guide](docs/INSTALLATION.md) | Detailed setup instructions, authentication options |
| [CLI Reference](docs/CLI_REFERENCE.md) | Complete command-line options and examples |
| [Data Quality](docs/DATA_QUALITY.md) | Validation checks, severity levels, understanding issues |
| [Performance](docs/PERFORMANCE.md) | Optimization options, caching, batch processing |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common errors and solutions |
| [Use Cases & Best Practices](docs/USE_CASES.md) | Automation, scheduling, workflows |
| [Output Formats](docs/OUTPUT_FORMATS.md) | Format specifications and examples |
| [Batch Processing](docs/BATCH_PROCESSING_GUIDE.md) | Multi-data view processing guide |
| [Testing](tests/README.md) | Running and writing tests |

## Requirements

- Python 3.14+
- Adobe I/O integration with CJA API access
- Network connectivity to Adobe APIs

## Project Structure

```
cja-auto-sdr-2026/
├── cja_sdr_generator.py     # Main script
├── myconfig.json            # Your credentials (DO NOT COMMIT)
├── pyproject.toml           # Project configuration
├── docs/                    # Documentation
├── tests/                   # Test suite (208 tests)
├── logs/                    # Generated log files
└── *.xlsx                   # Generated SDR files
```

## License

See [LICENSE](LICENSE) for details.

## Additional Resources

- [CJA API Documentation](https://developer.adobe.com/cja-apis/docs/)
- [cjapy Library](https://github.com/pitchmuc/cjapy)
- [uv Package Manager](https://github.com/astral-sh/uv)
- [Changelog](CHANGELOG.md)
