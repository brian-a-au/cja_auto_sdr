# Extended Quick Start Guide

A step-by-step walkthrough to generate your first SDR document from Adobe Customer Journey Analytics.

This guide assumes you're starting from scratch and walks through every step with explanations. By the end, you'll have a professionally formatted Excel document cataloging your entire CJA Data View configuration.

**Time required:** 15-20 minutes (mostly Adobe Developer Console setup)

---

## Table of Contents

1. [Prerequisites Checklist](#prerequisites-checklist)
2. [Step 1: Set Up Adobe Developer Console](#step-1-set-up-adobe-developer-console)
3. [Step 2: Install the Tool](#step-2-install-the-tool)
4. [Step 3: Configure Authentication](#step-3-configure-authentication)
5. [Step 4: Verify Your Setup](#step-4-verify-your-setup)
6. [Step 5: Generate Your First SDR](#step-5-generate-your-first-sdr)
7. [Step 6: Understand the Output](#step-6-understand-the-output)
8. [Next Steps](#next-steps)
9. [Common First-Run Issues](#common-first-run-issues)

---

## Prerequisites Checklist

Before starting, ensure you have:

- [ ] **Adobe CJA Access** - Access to Adobe CJA with at least one Data View configured
- [ ] **Adobe Developer Console Access** - Permission to create API integrations
- [ ] **Python 3.14+** - Check with `python3 --version` ([download Python](https://www.python.org/downloads/) if needed)
- [ ] **Terminal/Command Line** - Basic familiarity with running commands ([terminal basics guide](https://developer.mozilla.org/en-US/docs/Learn/Tools_and_testing/Understanding_client-side_tools/Command_line))
- [ ] **20 minutes** - Most time is spent on Adobe Developer Console setup

### Verify Python Installation

**macOS/Linux:**
```bash
$ python3 --version
Python 3.14.x
```

**Windows (PowerShell):**
```powershell
> python --version
Python 3.14.x
```

> **Note:** On macOS and Linux, use `python3` to ensure you're using Python 3. On Windows, the command is typically just `python`. You can also use `py --version` on Windows if the Python Launcher is installed.

If Python isn't installed or is an older version, visit [python.org](https://www.python.org/downloads/) to download the latest version.

---

## Step 1: Set Up Adobe Developer Console

The tool connects to CJA through Adobe's official API. You need to create an API integration to get authentication credentials.

### 1.1 Access the Developer Console

1. Go to [Adobe Developer Console](https://developer.adobe.com/console/)
2. Sign in with your Adobe ID (the one with CJA access)
3. Ensure you're in the correct organization (check top-right dropdown)

### 1.2 Create a New Project

1. Click **"Create new project"** (or use an existing project)
2. Give your project a descriptive name: `CJA SDR Generator`
3. Click **"Save"**

### 1.3 Add the CJA API

1. In your project, click **"Add API"**
2. Filter by **"Adobe Experience Platform"** or search for **"Customer Journey Analytics"**
3. Select **"Customer Journey Analytics"**
4. Click **"Next"**

### 1.4 Configure CJA Authentication

Choose **OAuth Server-to-Server** (recommended):

1. Select **"OAuth Server-to-Server"**
2. Click **"Next"**
3. Select a product profile that has access to your Data Views
4. Click **"Save configured API"**

### 1.5 Add the Adobe Experience Platform (AEP) API

> **Important:** The [Adobe Experience Platform API](https://developer.adobe.com/experience-platform-apis/) must be added to your project. This associates your service account with an Experience Platform product profile, which is required for CJA API authentication.

1. In your project, click **"Add API"** again
2. Search for **"Experience Platform API"** (under Adobe Experience Platform)
3. Select **"Experience Platform API"**
4. Click **"Next"**

### 1.6 Configure AEP Authentication

1. Select **"OAuth Server-to-Server"** (same as CJA)
2. Click **"Next"**
3. Select a product profile (this associates your service account with Experience Platform)
4. Click **"Save configured API"**

> **Note:** If you don't see any product profiles, contact your Adobe Admin Console administrator to ensure your user has been added to an AEP product profile.

### 1.7 Verify Both APIs Are Added

Your project should now show **two APIs** configured:
- Customer Journey Analytics
- Experience Platform API

Both APIs will share the same OAuth credentials (Client ID and Secret).

### 1.8 Collect Your Credentials

After setup, you'll see your credentials. You need these four values:

| Field | Where to Find It | Example |
|-------|------------------|---------|
| **Organization ID** | Top-right of console, or project overview | `ABC123@AdobeOrg` |
| **Client ID** | OAuth Server-to-Server > Credentials | `cm12345abcdef...` |
| **Client Secret** | Click "Retrieve client secret" | `p8e-ABC123...` |
| **Scopes** | OAuth Server-to-Server > Scopes | Usually pre-filled |

> **Important:** Keep these credentials secure. Never commit them to version control.

---

## Step 2: Install the Tool

### 2.1 Install uv Package Manager

[`uv`](https://docs.astral.sh/uv/) is a modern Python package manager that's faster and more reliable than pip. ([What's a package manager?](https://realpython.com/what-is-pip/) - pip concepts apply to uv)

**macOS/Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Restart your terminal, then verify:
```bash
$ uv --version
uv 0.x.x
```

### 2.2 Clone the Repository

Choose where you want to install the tool (e.g., your home directory, a projects folder, etc.):

```bash
# Navigate to your preferred location
cd ~/projects  # or any directory you prefer

# Clone the repository
git clone https://github.com/brian-a-au/cja_auto_sdr.git

# Enter the project directory
cd cja_auto_sdr
```

**Alternative: Download ZIP**

If you don't have [git](https://guides.github.com/introduction/git-handbook/) or prefer a download:
1. Download the ZIP from the repository
2. Extract to your preferred location
3. Open terminal and navigate to the extracted folder:
   ```bash
   cd ~/Downloads/cja_auto_sdr-main  # adjust path as needed
   ```

### 2.3 Install Dependencies

From inside the `cja_auto_sdr` directory, run:

```bash
uv sync
```

**Expected output:**
```
Resolved 15 packages in 0.5s
Downloaded 15 packages in 2.3s
Installed 15 packages in 0.8s
 + cjapy==0.2.4.post3
 + pandas==2.3.3
 + xlsxwriter==3.2.9
 + tqdm==4.66.0
 ...
```

This command:
- Creates a [virtual environment](https://realpython.com/python-virtual-environments-a-primer/) in `.venv/` (isolates project dependencies)
- Installs all required packages
- Installs the `cja_auto_sdr` command

### 2.4 Verify Installation

`uv run` automatically uses the project's virtual environment—no activation needed:

```bash
$ uv run cja_auto_sdr -V
cja_auto_sdr 3.4.0
```

> **Important:** All commands in this guide assume you're in the `cja_auto_sdr` directory. If you see "command not found", make sure you're in the right directory and have run `uv sync`.

### Running Commands

You have three equivalent options:

| Method | Command | Notes |
|--------|---------|-------|
| **uv run** | `uv run cja_auto_sdr ...` | Works immediately on macOS/Linux, may have issues on Windows |
| **Activated venv** | `cja_auto_sdr ...` | After activating: `source .venv/bin/activate` (Unix) or `.venv\Scripts\activate` (Windows) |
| **Direct script** | `cja_auto_sdr ...` | Most reliable on Windows |

This guide uses `uv run`. Windows users should substitute with `cja_auto_sdr`. The command examples below omit the prefix for brevity.

**Alternative: Manual activation**

If you prefer traditional virtual environment activation:

```bash
# macOS/Linux
source .venv/bin/activate
cja_auto_sdr -V  # same as --version

# Windows PowerShell
.venv\Scripts\activate
cja_auto_sdr -V  # same as --version
```

> **Windows Users:** If `uv run` doesn't work, use `cja_auto_sdr` instead. This is the most reliable method on Windows. See [Windows-Specific Issues](TROUBLESHOOTING.md#windows-specific-issues) for troubleshooting.

---

## Step 3: Configure Authentication

You have two options for configuring credentials:

### Option A: Configuration File (Quickest)

Create a `config.json` file in your current working directory (default path), or use `--config-file` to point to a different location:

```bash
# Copy the example template (recommended)
cp config.json.example config.json

# Or generate a template
uv run cja_auto_sdr --sample-config
```

Or create it manually ([JSON syntax guide](https://developer.mozilla.org/en-US/docs/Learn/JavaScript/Objects/JSON) - use double quotes, no trailing commas):

```json
{
  "org_id": "YOUR_ORG_ID@AdobeOrg",
  "client_id": "YOUR_CLIENT_ID",
  "secret": "YOUR_CLIENT_SECRET",
  "scopes": "your_scopes_from_developer_console"
}
```

Replace the placeholder values with the credentials from Step 1.8:

```json
{
  "org_id": "ABC123DEF456@AdobeOrg",
  "client_id": "cm12345abcdef67890",
  "secret": "p8e-ABC123XYZ789_your_actual_secret",
  "scopes": "your_scopes_from_developer_console"
}
```

> **Security:** The `config.json` file is already in `.gitignore`—it won't be committed to version control.

### Option B: Environment Variables (Recommended for CI/CD)

For automated pipelines or shared environments, use a `.env` file ([what are environment variables?](https://www.twilio.com/en-us/blog/how-to-set-environment-variables-html)):

```bash
ORG_ID=YOUR_ORG_ID@AdobeOrg
CLIENT_ID=YOUR_CLIENT_ID
SECRET=YOUR_CLIENT_SECRET
SCOPES=your_scopes_from_developer_console
```

To enable `.env` file loading:

```bash
uv add python-dotenv
```

> **Note:** Environment variables take precedence over `config.json` if both are set.

### Option C: Profiles (Recommended for Multiple Organizations)

If you manage multiple Adobe Organizations, use profiles to store credentials separately:

```bash
# Create a profile interactively
cja_auto_sdr --profile-add my-org

# Use the profile
cja_auto_sdr --profile my-org --list-dataviews
```

Profiles are stored in `~/.cja/orgs/` (your home directory, not the project). See [Profile Management](CONFIGURATION.md#profile-management) for full details.

For advanced configuration options, see [CONFIGURATION.md](CONFIGURATION.md).

### Managing Multiple Organizations

If you work with multiple Adobe Organizations (agencies, consultants, enterprises with regional orgs), use **profiles** instead of manually switching config files:

```bash
# Create profiles for each organization
cja_auto_sdr --profile-add client-a
cja_auto_sdr --profile-add client-b

# Switch between organizations easily
cja_auto_sdr --profile client-a --list-dataviews
cja_auto_sdr --profile client-b --list-dataviews
```

See the [Profile Management](CONFIGURATION.md#profile-management) section for full documentation.

---

## Step 4: Verify Your Setup

Before generating reports, verify everything is configured correctly.

### 4.1 Validate Configuration

First, check that your credentials are valid:

```bash
uv run cja_auto_sdr --validate-config
```

This verifies your configuration without making API calls.

### 4.2 Test API Connection

List your accessible Data Views to confirm the API connection works:

```bash
uv run cja_auto_sdr --list-dataviews
```

> **Windows Users:** If `uv run` doesn't work, use `cja_auto_sdr --list-dataviews` instead.

**Successful output:**
```
============================================================
LISTING ACCESSIBLE DATA VIEWS
============================================================
✓ API connection successful! Found 12 data view(s)

Available Data Views:
------------------------------------------------------------
1. Production Analytics
   ID: dv_677ea9291244fd082f02dd42
   Owner: admin@company.com

2. Staging Environment
   ID: dv_789bcd123456ef7890ab
   Owner: admin@company.com
...
```

**What this tells you:**
- Your credentials are valid
- The API connection works
- You can see which Data Views you have access to
- You have the Data View IDs needed for the next step

> **Tip:** For scripting, use `--format json` or `--output -` to get machine-readable output:
> ```bash
> uv run cja_auto_sdr --list-dataviews --format json
> uv run cja_auto_sdr --list-dataviews --output - | jq '.dataViews[].id'
> ```

### 4.2a Explore Connections and Datasets (Optional)

You can also explore the CJA infrastructure behind your data views:

```bash
# List all connections with their datasets
uv run cja_auto_sdr --list-connections

# List all data views with their backing connections and datasets
uv run cja_auto_sdr --list-datasets
```

This is useful for understanding which datasets feed into which data views before generating an SDR.

You can also drill into individual data view components without generating a full SDR:

```bash
# Inspect a data view's metadata and component counts
uv run cja_auto_sdr --describe-dataview dv_677ea9291244fd082f02dd42

# Browse metrics, dimensions, segments, or calculated metrics
uv run cja_auto_sdr --list-metrics dv_677ea9291244fd082f02dd42 --filter "revenue"
uv run cja_auto_sdr --list-segments dv_677ea9291244fd082f02dd42
```

See [CLI Reference](CLI_REFERENCE.md#discovery-inspection) for the full set of inspection commands.

> **Note:** Full connection details require the API service account to be a CJA Product Admin. If you only see connection IDs (like `dg_...`) instead of names, see [Troubleshooting](TROUBLESHOOTING.md#connections-api-returns-empty-results) for how to grant the technical account admin rights.

### 4.3 Choose a Data View

From the list above, note the **ID** of the Data View you want to document. It looks like:
```
dv_677ea9291244fd082f02dd42
```

### 4.4 Quick Stats (Optional)

Before generating a full report, you can quickly check what's in a data view:

```bash
uv run cja_auto_sdr dv_677ea9291244fd082f02dd42 --stats
```

This shows the number of metrics and dimensions without generating any files—useful for verifying access and checking data view size.

### 4.5 Dry Run (Optional)

Test the full process without generating a report:

```bash
uv run cja_auto_sdr dv_YOUR_DATA_VIEW_ID --dry-run
```

**Expected output:**
```
============================================================
DRY RUN MODE - No files will be generated
============================================================
✓ Configuration valid
✓ API connection successful
✓ Data view "Production Analytics" found and accessible
✓ All pre-flight checks passed

Dry run complete. Remove --dry-run to generate the SDR.
```

---

## Step 5: Generate Your First SDR

### 5.1 Option A: Interactive Mode (Recommended for First-Time Users)

The easiest way to generate your first SDR is with interactive mode:

```bash
uv run cja_auto_sdr --interactive
```

Interactive mode guides you through:
1. **Data View Selection** - Shows a numbered list of your accessible data views
2. **Output Format** - Choose Excel, JSON, CSV, HTML, Markdown, or all formats
3. **Inventory Options** - Optionally include segments, calculated metrics, or derived fields
4. **Confirmation** - Review your selections before generating

Selection syntax:
- Single: `3` (selects item #3)
- Multiple: `1,3,5` (selects items #1, #3, #5)
- Range: `1-5` (selects items #1 through #5)
- All: `all` or `a` (selects everything)
- Cancel: `q` or `quit` (exit without generating)

### 5.2 Option B: Direct Command

If you prefer direct commands, replace `dv_YOUR_DATA_VIEW_ID` with your actual Data View ID:

**macOS/Linux:**
```bash
uv run cja_auto_sdr dv_677ea9291244fd082f02dd42
```

**Windows (PowerShell):**
```powershell
cja_auto_sdr dv_677ea9291244fd082f02dd42
```

### 5.2.1 Scoped Component Output (Optional)

Use these flags to focus output on one component type in either SDR or diff mode:

```bash
# SDR mode: metrics only (exclude dimensions)
uv run cja_auto_sdr dv_677ea9291244fd082f02dd42 --metrics-only

# SDR mode: dimensions only (exclude metrics)
uv run cja_auto_sdr dv_677ea9291244fd082f02dd42 --dimensions-only

# Diff mode: compare metrics only
uv run cja_auto_sdr --diff dv_12345 dv_67890 --metrics-only

# Diff mode: compare dimensions only
uv run cja_auto_sdr --diff dv_12345 dv_67890 --dimensions-only
```

### 5.3 Watch the Progress

The tool displays real-time progress:

```
Processing data view: dv_677ea9291244fd082f02dd42

✓ CJA connection established successfully
✓ Data view validation complete - proceeding with data fetch

============================================================
Starting optimized data fetch operations
============================================================
Data fetch operations completed successfully

============================================================
Starting data quality validation (optimized)
============================================================
✓ Duplicate ID check: PASSED
✓ Missing name check: PASSED (2 warnings)
✓ Null value check: PASSED
...

============================================================
Generating output in format: excel
============================================================
Generating Excel file...

============================================================
✓ SDR generation complete! File saved as:
  CJA_DataView_Production_Analytics_dv_677ea9291244fd082f02dd42_SDR.xlsx
  Size: 2.5 MB
  Time: 18.3 seconds
============================================================
```

### 5.3 Locate Your Output

The generated file is in the current directory:

**macOS/Linux:**
```bash
$ ls -la *.xlsx
CJA_DataView_Production_Analytics_dv_677ea9291244fd082f02dd42_SDR.xlsx
```

**Windows (PowerShell):**
```powershell
> Get-ChildItem *.xlsx
CJA_DataView_Production_Analytics_dv_677ea9291244fd082f02dd42_SDR.xlsx
```

> **Tip:** Use `--open` to automatically open the file after generation:
> ```bash
> uv run cja_auto_sdr dv_677ea9291244fd082f02dd42 --open
> ```

---

## Step 6: Understand the Output

Open the generated Excel file. It contains 5 sheets:

### Sheet 1: Metadata

High-level information about the SDR generation in a key-value format:

| Property | Description |
|----------|-------------|
| Generated At | When this SDR was created |
| Data View ID | The unique identifier |
| Data View Name | The display name in CJA |
| Total Metrics | Count of metrics in the Data View |
| Metrics Summary | Breakdown of metric types |
| Total Dimensions | Count of dimensions |
| Dimensions Summary | Breakdown of dimension types |
| Data Quality Summary | Count of issues found |

### Sheet 2: Data Quality

Results of automated validation checks:

| Column | Description |
|--------|-------------|
| Severity | CRITICAL, HIGH, MEDIUM, LOW, or INFO |
| Category | Type of check (Duplicates, Missing Fields, etc.) |
| Type | Component type (Metrics, Dimensions) |
| Item Name | Name of the affected component |
| Issue | Description of the problem |
| Details | Additional context or information |

**Color coding:**
- **Red rows:** Critical issues
- **Orange rows:** High severity issues
- **Yellow rows:** Medium severity warnings
- **Gray rows:** Low severity notes
- **Blue rows:** Informational items

### Sheet 3: DataView Details

Data view-level configuration properties in a key-value format:

| Property | Description |
|----------|-------------|
| Name | Data view display name |
| ID | Unique data view identifier (dv_...) |
| Owner | Email of the data view owner |
| Description | Data view description text |
| Parent Connection | Associated connection ID |
| Sandbox | AEP sandbox name |
| Created | Creation timestamp |
| Modified | Last modification timestamp |
| ... | Additional data view settings |

### Sheet 4: Metrics

All metrics in the Data View with their configuration:

| Column | Description |
|--------|-------------|
| id | Unique metric identifier |
| name | Display name in CJA |
| type | Metric type (e.g., calculated, standard) |
| title | Title text |
| description | Documentation text |
| schemaPath | XDM schema location |
| format | Display format (number, currency, percent) |
| precision | Decimal places |
| attribution | Attribution model settings |
| ... | Additional metric configuration |

### Sheet 5: Dimensions

All dimensions in the Data View with their configuration:

| Column | Description |
|--------|-------------|
| id | Unique dimension identifier |
| name | Display name in CJA |
| type | Dimension type (e.g., string, numeric) |
| title | Title text |
| description | Documentation text |
| schemaPath | XDM schema location |
| persistence | Persistence setting (hit, visit, person) |
| allocation | Value allocation (first, last, most recent) |
| bucketing | Bucketing configuration |
| ... | Additional dimension configuration |

---

## Next Steps

Now that you've generated your first SDR, here are common next steps:

### Process Multiple Data Views

```bash
# Process all your Data Views at once
uv run cja_auto_sdr dv_id1 dv_id2 dv_id3
```

### Generate All Formats

```bash
# Excel, CSV, JSON, and HTML
uv run cja_auto_sdr dv_12345 --format all
```

### Set Up Automation

See the [Use Cases Guide](USE_CASES.md) for:
- Scheduled cron jobs
- CI/CD integration
- Automated reporting workflows

### Improve Performance

For large Data Views, see the [Performance Guide](PERFORMANCE.md):
- Enable caching for repeated runs
- Skip validation when not needed
- Configure parallel workers

### Compare Data Views

Track changes between environments or over time with diff comparison:
```bash
# Compare two data views
uv run cja_auto_sdr --diff dv_12345 dv_67890

# Save a baseline snapshot
uv run cja_auto_sdr dv_12345 --snapshot ./baseline.json
```

See [Data View Comparison](DIFF_COMPARISON.md) for more details.

### Analyze Org-Wide Component Usage

Understand component usage patterns across all data views in your organization:
```bash
# Basic org-wide analysis
uv run cja_auto_sdr --org-report

# Filter to specific data views and export to Excel
uv run cja_auto_sdr --org-report --filter "Prod.*" --format excel
```

See [Org-Wide Analysis](ORG_WIDE_ANALYSIS.md) for governance insights and duplicate detection.

### Document Component Inventories

Generate detailed documentation for segments, derived fields, and calculated metrics:
```bash
# Include segments inventory
uv run cja_auto_sdr dv_12345 --include-segments

# Include all component inventories
uv run cja_auto_sdr dv_12345 --include-segments --include-derived --include-calculated

# Generate only inventories (no standard SDR)
uv run cja_auto_sdr dv_12345 --include-segments --inventory-only
```

See [Segments Inventory](SEGMENTS_INVENTORY.md), [Derived Fields Inventory](DERIVED_FIELDS_INVENTORY.md), and [Calculated Metrics Inventory](CALCULATED_METRICS_INVENTORY.md) for details.

### Quick Reference

Keep the [Quick Reference Card](QUICK_REFERENCE.md) handy for common commands and options.

---

## Common First-Run Issues

### "Configuration file not found"

```
Error: Configuration file 'config.json' not found
```

**Solution:** Ensure your config file exists at the path you're using. By default this is `./config.json` in your current directory, or pass an explicit path with `--config-file`.

```bash
ls config.json
```

### "Authentication failed"

```
Error: Authentication failed - invalid credentials
```

**Solutions:**
1. Double-check your `client_id` and `secret` in `config.json`
2. Ensure there are no extra spaces or quotes
3. Verify the integration is active in Adobe Developer Console
4. Check that OAuth scopes match exactly

### "Data view not found"

```
Error: Data view 'dv_12345' not found or not accessible
```

**Solutions:**
1. Run `--list-dataviews` to see accessible Data Views
2. Verify the ID starts with `dv_` and is complete
3. Check that your integration has permission to access this Data View
4. Confirm you're in the correct Adobe organization

### "Connection timeout"

```
Error: Connection timed out after 30 seconds
```

**Solutions:**
1. Check your internet connection
2. Try again (transient network issues)
3. Check [Adobe Status](https://status.adobe.com/) for API outages
4. If behind a proxy, configure proxy settings

### "Permission denied" on output

```
Error: Permission denied writing to ./output.xlsx
```

**Solutions:**
1. Check directory write permissions
2. Close the Excel file if it's open
3. Specify a different output directory: `--output-dir ~/Desktop`

### Windows: "uv run" command doesn't work

**Symptoms (Windows):**
```text
PS> uv run cja_auto_sdr --version
# Command fails, hangs, or shows errors
```

**Solution:** Use Python directly instead:

```text
# Activate virtual environment
.venv\Scripts\activate

# Run with Python
cja_auto_sdr --version
cja_auto_sdr --list-dataviews
cja_auto_sdr dv_12345
```

### Windows: NumPy ImportError

**Symptoms (Windows):**
```
ImportError: Unable to import required dependencies:
numpy:
Importing the numpy C-extensions failed.
```

**Cause:** Common on Windows with Microsoft Store Python or incompatible binary wheels.

**Solution:**

1. Ensure Python is from [python.org](https://www.python.org/downloads/), not Microsoft Store
2. Reinstall NumPy with binary wheels:

```text
# Activate virtual environment
.venv\Scripts\activate

# Reinstall NumPy
pip uninstall numpy
pip install --only-binary :all: numpy>=2.2.0

# Verify
python -c "import numpy; print(numpy.__version__)"

# Then run the tool
cja_auto_sdr --version
```

**See also:** [Windows-Specific Issues](TROUBLESHOOTING.md#windows-specific-issues) for comprehensive Windows troubleshooting.

### Rate Limiting

```
Warning: Rate limited by API, retrying in 30 seconds...
```

**This is normal.** The tool automatically retries with exponential backoff. Large Data Views or batch processing may trigger rate limits. Wait for completion.

---

## Getting Help

If you're still stuck:

1. **Check the logs:** `logs/SDR_Generation_*.log` contains detailed error information
2. **Enable debug mode:** Add `--log-level DEBUG` for verbose output
3. **Review documentation:**
   - [Configuration Guide](CONFIGURATION.md) - Detailed config.json and environment variable reference
   - [Troubleshooting Guide](TROUBLESHOOTING.md) - Comprehensive error reference
   - [CLI Reference](CLI_REFERENCE.md) - All command options
4. **Topic-specific troubleshooting:**
   - [Windows Issues](TROUBLESHOOTING.md#windows-specific-issues) - NumPy, uv, PowerShell
   - [Data View Names](DATA_VIEW_NAMES.md#error-handling) - Case sensitivity, name resolution
   - [Output Formats](OUTPUT_FORMATS.md#troubleshooting) - CSV encoding, large JSON files
   - [Batch Processing](BATCH_PROCESSING_GUIDE.md#troubleshooting) - Rate limiting, worker issues
   - [Git Integration](GIT_INTEGRATION.md#troubleshooting) - Push failures, repository setup
   - [Diff Comparison](DIFF_COMPARISON.md#troubleshooting) - Snapshot errors
5. **Report issues:** [GitHub Issues](https://github.com/brian-a-au/cja_auto_sdr/issues)

---

## Summary

You've successfully:

1. Created Adobe API credentials
2. Installed and configured the tool
3. Verified your setup
4. Generated your first SDR document
5. Learned to interpret the output

Your SDR document is now ready to share with your team, include in documentation, or use for data governance audits.
