# Adobe Customer Journey Analytics SDR Generator

<img width="1024" height="572" alt="image" src="https://github.com/user-attachments/assets/54a43474-3fc6-4379-909c-452c19cdeac2" />

A production-ready Python tool that automates the creation of Solution Design Reference (SDR) documents from your Adobe Customer Journey Analytics implementation.

## What It Is

A **Solution Design Reference (SDR)** is the essential documentation that bridges your business requirements and your analytics implementation. It catalogs every metric and dimension in your CJA Data View, serving as the single source of truth for what data you're collecting and how it's configured.

**The Problem:** Manually documenting CJA implementations is time-consuming, error-prone, and quickly becomes outdated. Teams waste hours exporting data, formatting spreadsheets, and cross-referencing configurations—only to repeat the process when things change.

**The Solution:** This tool connects directly to the CJA API, extracts your complete Data View configuration, validates data quality, and generates professionally formatted documentation in seconds. It also tracks changes between data views over time with built-in diff comparison and snapshot capabilities.

> **Origin:** This project evolved from a [Jupyter notebook proof-of-concept](https://github.com/pitchmuc/CJA_Summit_2025/blob/main/notebooks/06.%20CJA%20Data%20View%20Solution%20Design%20Reference%20Generator.ipynb) into a production-ready CLI. The notebook remains excellent for learning; this tool is for teams needing automation, change tracking, and enterprise-grade reliability.

### How It Works

1. **Connects** to your CJA instance via the Adobe API
2. **Extracts** all metrics, dimensions, and configuration from your Data View(s)
3. **Validates** data quality with 8+ automated checks (duplicates, missing fields, null values)
4. **Generates** formatted documentation with color-coded quality indicators

### Key Features

| Category | Feature | Benefit |
|----------|---------|---------|
| **Performance** | Parallel Batch Processing | Process multiple Data Views simultaneously (3-4x faster) |
| | Validation Caching | 50-90% faster on repeated runs with intelligent result caching |
| | Optimized Validation | Single-pass DataFrame scanning (30-50% faster) |
| | Configurable Workers | Scale from 1-256 parallel workers based on your infrastructure |
| **Quality** | 8+ Validation Checks | Detect duplicates, missing fields, null values, invalid IDs |
| | Severity Classification | CRITICAL, HIGH, MEDIUM, LOW with color-coded Excel formatting |
| | Quality Dashboard | Dedicated sheet with filtering, sorting, and actionable insights |
| **Output** | Multiple Formats | Excel, CSV, JSON, HTML, Markdown—or generate all at once |
| | Professional Excel | 5 formatted sheets with conditional formatting, frozen headers, auto-filtering |
| | Stdout Support | Pipe JSON/CSV output directly to other tools with `--output -` |
| | Auto-Open Files | Open generated files immediately with `--open` flag |
| **Reliability** | Automatic Retry | Exponential backoff with jitter for transient network failures |
| | Continue-on-Error | Batch processing continues even if individual Data Views fail |
| | Pre-flight Validation | Validates config and connectivity before processing |
| **Comparison** | Data View Diff | Compare two data views to identify added, removed, and modified components |
| | Snapshot Support | Save and compare against baseline snapshots for change tracking |
| | Snapshot-to-Snapshot | Compare two snapshot files directly without API calls |
| | Auto-Snapshot on Diff | Automatically save timestamped snapshots during comparisons for audit trails |
| | CI/CD Integration | Exit codes for pipeline automation (2=changes found, 3=threshold exceeded) |
| | Smart Name Resolution | Fuzzy matching suggestions for typos, interactive disambiguation for duplicates |
| **Git Integration** | Version-Controlled Snapshots | Save SDR snapshots in Git-friendly format with auto-commit |
| | Audit Trail | Full history of every data view configuration change |
| | Team Collaboration | Share snapshots via Git repositories with PR-based review workflows |
| **Developer UX** | Quick Stats Mode | Get metrics/dimensions count instantly with `--stats` (no full report) |
| | Machine-Readable Discovery | `--list-dataviews --format json` for scripting integration |
| | Dry-Run Mode | Test configuration without generating reports |
| | Color-Coded Output | Green/yellow/red console feedback for instant status |
| | Enhanced Error Messages | Contextual error messages with actionable fix suggestions |
| | Comprehensive Logging | Timestamped logs with rotation for audit trails |

### Who It's For

- **Analytics Teams** needing up-to-date implementation documentation
- **Consultants** managing multiple client implementations
- **Data Governance** teams requiring audit trails and quality tracking
- **DevOps Engineers** automating CJA audits in CI/CD pipelines

## Quick Start

### 1. Clone the Repository

```bash
# Clone the repository
git clone https://github.com/your-org/cja_auto_sdr.git
cd cja_auto_sdr
```

### 2. Install Dependencies

**macOS/Linux:**
```bash
# Install uv package manager (if not already installed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install project dependencies
uv sync
```

**Windows (PowerShell):**
```powershell
# Install uv package manager
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Install project dependencies
uv sync
```

If uv doesn't work, use native Python instead (recommended for Windows):
```text
python -m venv .venv
.venv\Scripts\activate
pip install -e .
```

> **Windows Users:** If you encounter issues with `uv run` or NumPy import errors on Windows, we recommend using Python directly. See the [Windows-Specific Issues](docs/TROUBLESHOOTING.md#windows-specific-issues) section in the troubleshooting guide for detailed solutions.

> **Running commands:** You have three equivalent options:
> - `uv run cja_auto_sdr ...` — works immediately on macOS/Linux, may have issues on Windows
> - `cja_auto_sdr ...` — after activating the venv: `source .venv/bin/activate` (Unix) or `.venv\Scripts\activate` (Windows)
> - `python cja_sdr_generator.py ...` — run the script directly (most reliable on Windows)
>
> This guide uses `uv run`. Windows users should substitute with `python cja_sdr_generator.py`. The [Common Use Cases](#common-use-cases) table omits the prefix for brevity.

### 3. Configure Credentials

Get your credentials from [Adobe Developer Console](https://developer.adobe.com/console/) (see [QUICKSTART_GUIDE](docs/QUICKSTART_GUIDE.md) for detailed steps).

**Option A: Configuration File (Quickest)**

Create a `config.json` file with your Adobe credentials:

```bash
# Copy the example template
cp config.json.example config.json

# Or generate a template (creates config.sample.json)
uv run cja_auto_sdr --sample-config

# Edit config.json with your credentials
```

> **Note:** The configuration file must be named `config.json` and placed in the project root directory.

```json
{
  "org_id": "YOUR_ORG_ID@AdobeOrg",
  "client_id": "YOUR_CLIENT_ID",
  "secret": "YOUR_CLIENT_SECRET",
  "scopes": "openid, AdobeID, additional_info.projectedProductContext"
}
```

**Option B: Environment Variables (Recommended for CI/CD)**

Use a `.env` file (copy from `.env.example`) or export directly:

```bash
ORG_ID=your_org_id@AdobeOrg
CLIENT_ID=your_client_id
SECRET=your_client_secret
SCOPES=openid, AdobeID, additional_info.projectedProductContext
```

> **Note:** Environment variables take precedence over `config.json`.

### 4. Verify Setup & Run

**macOS/Linux:**
```bash
# Verify configuration and list available data views
uv run cja_auto_sdr --validate-config
uv run cja_auto_sdr --list-dataviews

# Generate SDR for a data view (by ID)
uv run cja_auto_sdr dv_YOUR_DATA_VIEW_ID

# Or by name (quotes recommended for names with spaces)
uv run cja_auto_sdr "Production Analytics"
```

**Windows (if uv run doesn't work):**
```powershell
# Activate virtual environment first
.venv\Scripts\activate

# Verify configuration and list available data views
python cja_sdr_generator.py --validate-config
python cja_sdr_generator.py --list-dataviews

# Generate SDR for a data view (by ID or name)
python cja_sdr_generator.py dv_YOUR_DATA_VIEW_ID
python cja_sdr_generator.py "Production Analytics"
```

> **Tip:** You can specify Data Views by **name** in addition to ID. If multiple data views share the same name, all matching views will be processed.

### 5. Review Output

- Generated Excel file: `CJA_DataView_[Name]_[ID]_SDR.xlsx`
- Logs: `logs/` directory

## Common Use Cases

**Note:** Commands below omit the `uv run` or `python cja_sdr_generator.py` prefix for brevity:
- **macOS/Linux:** Add `uv run` before each command (e.g., `uv run cja_auto_sdr dv_12345`)
- **Windows:** Use `python cja_sdr_generator.py` instead (e.g., `python cja_sdr_generator.py dv_12345`)

| Task | Command |
|------|---------|
| **SDR Generation** | |
| Single Data View (by ID) | `cja_auto_sdr dv_12345` |
| Single Data View (by name) | `cja_auto_sdr "Production Analytics"` |
| Generate and open file | `cja_auto_sdr dv_12345 --open` |
| Batch processing | `cja_auto_sdr dv_1 dv_2 dv_3` |
| Custom output location | `cja_auto_sdr dv_12345 --output-dir ./reports` |
| Skip validation (faster) | `cja_auto_sdr dv_12345 --skip-validation` |
| **Output Formats** | |
| Export as Excel (default) | `cja_auto_sdr dv_12345 --format excel` |
| Export as CSV | `cja_auto_sdr dv_12345 --format csv` |
| Export as JSON | `cja_auto_sdr dv_12345 --format json` |
| Export as HTML | `cja_auto_sdr dv_12345 --format html` |
| Export as Markdown | `cja_auto_sdr dv_12345 --format markdown` |
| Generate all formats | `cja_auto_sdr dv_12345 --format all` |
| **Quick Stats & Discovery** | |
| Quick stats (no full report) | `cja_auto_sdr dv_12345 --stats` |
| Stats as JSON | `cja_auto_sdr dv_12345 --stats --format json` |
| List data views | `cja_auto_sdr --list-dataviews` |
| List as JSON (for scripting) | `cja_auto_sdr --list-dataviews --format json` |
| Pipe to other tools | `cja_auto_sdr --list-dataviews --output - \| jq '.dataViews[]'` |
| Validate config only | `cja_auto_sdr --validate-config` |
| **Diff Comparison** (default: console output) | |
| Compare two Data Views | `cja_auto_sdr --diff dv_1 dv_2` |
| Compare by name | `cja_auto_sdr --diff "Production" "Staging"` |
| Diff as Markdown | `cja_auto_sdr --diff dv_1 dv_2 --format markdown` |
| Diff as JSON | `cja_auto_sdr --diff dv_1 dv_2 --format json` |
| Save snapshot | `cja_auto_sdr dv_12345 --snapshot ./baseline.json` |
| Compare to snapshot | `cja_auto_sdr dv_12345 --diff-snapshot ./baseline.json` |
| Compare two snapshots | `cja_auto_sdr --compare-snapshots ./old.json ./new.json` |
| Auto-save snapshots | `cja_auto_sdr --diff dv_1 dv_2 --auto-snapshot` |
| With retention policy | `cja_auto_sdr --diff dv_1 dv_2 --auto-snapshot --keep-last 10` |
| **Git Integration** | |
| Initialize Git repo | `cja_auto_sdr --git-init --git-dir ./sdr-snapshots` |
| Generate and commit | `cja_auto_sdr dv_12345 --git-commit` |
| Commit with custom message | `cja_auto_sdr dv_12345 --git-commit --git-message "Weekly audit"` |
| Commit and push | `cja_auto_sdr dv_12345 --git-commit --git-push` |

## Documentation

| Guide | Description |
|-------|-------------|
| [Quick Reference](docs/QUICK_REFERENCE.md) | Single-page command cheat sheet |
| [Extended Quick Start](docs/QUICKSTART_GUIDE.md) | Complete walkthrough from zero to first SDR |
| [Installation Guide](docs/INSTALLATION.md) | Detailed setup instructions, authentication options |
| [CLI Reference](docs/CLI_REFERENCE.md) | Complete command-line options and examples |
| [Data Quality](docs/DATA_QUALITY.md) | Validation checks, severity levels, understanding issues |
| [Performance](docs/PERFORMANCE.md) | Optimization options, caching, batch processing |
| [Troubleshooting](docs/TROUBLESHOOTING.md) | Common errors and solutions |
| [Use Cases & Best Practices](docs/USE_CASES.md) | Automation, scheduling, workflows |
| [Output Formats](docs/OUTPUT_FORMATS.md) | Format specifications and examples |
| [Batch Processing](docs/BATCH_PROCESSING_GUIDE.md) | Multi-data view processing guide |
| [Data View Names](docs/DATA_VIEW_NAMES.md) | Using Data View names instead of IDs |
| [Data View Comparison](docs/DIFF_COMPARISON.md) | Compare data views, snapshots, CI/CD integration |
| [Git Integration](docs/GIT_INTEGRATION.md) | Version-controlled snapshots, audit trails, team collaboration |
| [Testing](tests/README.md) | Running and writing tests |

## Requirements

- Python 3.14+
- Adobe I/O integration with CJA API access
- Network connectivity to Adobe APIs

## Project Structure

```
cja_auto_sdr/
├── cja_sdr_generator.py     # Main script (single-file application)
├── pyproject.toml           # Project configuration and dependencies
├── uv.lock                  # Dependency lock file for reproducible builds
├── README.md                # This file
├── CHANGELOG.md             # Version history and release notes
├── LICENSE                  # License file
├── config.json              # Your credentials (DO NOT COMMIT)
├── config.json.example      # Config file template
├── .env.example             # Environment variable template
├── docs/                    # Documentation (15 guides)
│   ├── QUICKSTART_GUIDE.md  # Getting started guide
│   ├── CLI_REFERENCE.md     # Command-line reference
│   ├── DIFF_COMPARISON.md   # Data view comparison guide
│   ├── GIT_INTEGRATION.md   # Git integration guide
│   ├── INSTALLATION.md      # Setup instructions
│   └── ...                  # Additional guides
├── tests/                   # Test suite (651 tests)
├── sample_outputs/          # Example output files
│   ├── excel/               # Sample Excel SDR
│   ├── csv/                 # Sample CSV output
│   ├── json/                # Sample JSON output
│   ├── html/                # Sample HTML output
│   ├── markdown/            # Sample Markdown output
│   ├── diff/                # Sample diff comparison outputs
│   └── git-snapshots/       # Sample Git integration snapshots
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
