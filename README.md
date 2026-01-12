# Adobe Customer Journey Analytics SDR Generator

<img width="1024" height="572" alt="image" src="https://github.com/user-attachments/assets/54a43474-3fc6-4379-909c-452c19cdeac2" />

**Version 3.0.7** - A production-ready Python tool for generating Solution Design Reference (SDR) documents from your Customer Journey Analytics implementation with data quality validation.

## What It Is

This tool audits your CJA implementation by:
- **Connecting** to your CJA instance via the API
- **Fetching** all metrics and dimensions from your Data View(s)
- **Validating** data quality with 8+ automated checks
- **Generating** professionally formatted Excel workbooks

**Key Features:**
- High-performance batch processing (3-4x faster with parallel execution)
- Comprehensive data quality validation with severity-based reporting
- Multiple output formats (Excel, CSV, JSON, HTML)
- Enterprise-grade error handling with automatic retry
- Modern dependency management with `uv`

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
