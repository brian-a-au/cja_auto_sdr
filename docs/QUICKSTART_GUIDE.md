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

- [ ] **Adobe CJA Access** - An active CJA subscription with at least one Data View
- [ ] **Adobe Developer Console Access** - Permission to create API integrations
- [ ] **Python 3.14+** - Check with `python --version`
- [ ] **Terminal/Command Line** - Basic familiarity with running commands
- [ ] **20 minutes** - Most time is spent on Adobe Developer Console setup

### Verify Python Installation

```bash
python --version
# Output: Python 3.14.x or higher
```

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

### 1.4 Configure Authentication

Choose **OAuth Server-to-Server** (recommended):

1. Select **"OAuth Server-to-Server"**
2. Click **"Next"**
3. Select a product profile that has access to your Data Views
4. Click **"Save configured API"**

### 1.5 Collect Your Credentials

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

`uv` is a modern Python package manager that's faster and more reliable than pip.

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
uv --version
# Output: uv 0.x.x
```

### 2.2 Clone the Repository

Choose where you want to install the tool (e.g., your home directory, a projects folder, etc.):

```bash
# Navigate to your preferred location
cd ~/projects  # or any directory you prefer

# Clone the repository
git clone https://github.com/your-org/cja_auto_sdr.git

# Enter the project directory
cd cja_auto_sdr
```

**Alternative: Download ZIP**

If you don't have git or prefer a download:
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
 + cjapy==0.2.4.post2
 + pandas==2.3.3
 + xlsxwriter==3.2.9
 + tqdm==4.66.0
 ...
```

This command:
- Creates a virtual environment in `.venv/`
- Installs all required packages
- Installs the `cja_auto_sdr` command

### 2.4 Verify Installation

**macOS/Linux:**
```bash
# Using uv run (works without activating venv)
uv run cja_auto_sdr --version
# Output: cja_sdr_generator.py version 3.0.10

# Or activate the virtual environment first
source .venv/bin/activate
cja_auto_sdr --version
# Output: cja_sdr_generator.py version 3.0.10
```

**Windows (PowerShell):**
```powershell
# Try uv run first
uv run cja_auto_sdr --version

# If that doesn't work, activate virtual environment
.venv\Scripts\activate

# Then run directly
python cja_sdr_generator.py --version
# Output: cja_sdr_generator.py version 3.0.10

# Or use the console script if it was installed
cja_auto_sdr --version
```

> **Important:** All commands in this guide assume you're in the `cja_auto_sdr` directory. If you see "command not found", make sure you're in the right directory and have run `uv sync`.

> **Windows Users:** If `uv run` or the console script doesn't work, always use `python cja_sdr_generator.py` instead. This is the most reliable method on Windows. See [Windows-Specific Issues](TROUBLESHOOTING.md#windows-specific-issues) for troubleshooting.

---

## Step 3: Configure Authentication

You have two options for configuring credentials:

### Option A: Environment Variables (Recommended for CI/CD)

Create a `.env` file in the project root:

```bash
ORG_ID=YOUR_ORG_ID@AdobeOrg
CLIENT_ID=YOUR_CLIENT_ID
SECRET=YOUR_CLIENT_SECRET
SCOPES=openid, AdobeID, additional_info.projectedProductContext
```

To enable `.env` file loading:

```bash
uv add python-dotenv
```

### Option B: Configuration File

#### 3.1 Create Configuration File

Create a file named `config.json` in the project root directory:

```bash
# Copy the example template (recommended)
cp config.json.example config.json

# Or generate a template
uv run cja_auto_sdr --sample-config
```

Or create it manually:

```json
{
  "org_id": "YOUR_ORG_ID@AdobeOrg",
  "client_id": "YOUR_CLIENT_ID",
  "secret": "YOUR_CLIENT_SECRET",
  "scopes": "openid, AdobeID, additional_info.projectedProductContext"
}
```

#### 3.2 Fill In Your Credentials

Replace the placeholder values with the credentials from Step 1.5:

```json
{
  "org_id": "ABC123DEF456@AdobeOrg",
  "client_id": "cm12345abcdef67890",
  "secret": "p8e-ABC123XYZ789_your_actual_secret",
  "scopes": "openid, AdobeID, additional_info.projectedProductContext"
}
```

### 3.3 Secure Your Credentials

Ensure credentials are not committed to version control:

```bash
# Check if it's ignored
git check-ignore config.json
# Should output: config.json

# If not, add it
echo "config.json" >> .gitignore
```

---

## Step 4: Verify Your Setup

Before generating reports, verify everything is configured correctly.

### 4.1 Test API Connection

**macOS/Linux:**
```bash
uv run cja_auto_sdr --list-dataviews
```

**Windows (PowerShell):**
```powershell
# If uv run works:
uv run cja_auto_sdr --list-dataviews

# If not, use Python directly:
python cja_sdr_generator.py --list-dataviews
```

**Successful output:**
```
============================================================
INITIALIZING CJA CONNECTION
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
> cja_auto_sdr --list-dataviews --format json
> cja_auto_sdr --list-dataviews --output - | jq '.dataViews[].id'
> ```

### 4.2 Choose a Data View

From the list above, note the **ID** of the Data View you want to document. It looks like:
```
dv_677ea9291244fd082f02dd42
```

### 4.3 Dry Run (Optional)

Test without generating a report:

**macOS/Linux:**
```bash
uv run cja_auto_sdr dv_YOUR_DATA_VIEW_ID --dry-run
```

**Windows (PowerShell):**
```powershell
python cja_sdr_generator.py dv_YOUR_DATA_VIEW_ID --dry-run
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

### 5.1 Run the Generator

Replace `dv_YOUR_DATA_VIEW_ID` with your actual Data View ID:

**macOS/Linux:**
```bash
uv run cja_auto_sdr dv_677ea9291244fd082f02dd42
```

**Windows (PowerShell):**
```powershell
python cja_sdr_generator.py dv_677ea9291244fd082f02dd42
```

### 5.2 Watch the Progress

The tool displays real-time progress:

```
Processing data view: dv_677ea9291244fd082f02dd42

============================================================
INITIALIZING CJA CONNECTION
============================================================
✓ API connection successful! Found 12 data view(s)

============================================================
VALIDATING DATA VIEW
============================================================
✓ Data view validated successfully!
  Name: Production Analytics
  ID: dv_677ea9291244fd082f02dd42

============================================================
EXTRACTING DATA VIEW CONFIGURATION
============================================================
Extracting metrics... ━━━━━━━━━━━━━━━━━━━━ 100% 0:00:02
Extracting dimensions... ━━━━━━━━━━━━━━━━━━━━ 100% 0:00:03

============================================================
RUNNING DATA QUALITY VALIDATION
============================================================
Running 8 validation checks...
✓ Duplicate ID check: PASSED
✓ Missing name check: PASSED (2 warnings)
✓ Null value check: PASSED
...

============================================================
GENERATING EXCEL REPORT
============================================================
Creating workbook...
Writing Metadata sheet...
Writing Data Quality sheet...
Writing DataView sheet...
Writing Metrics sheet (145 metrics)...
Writing Dimensions sheet (287 dimensions)...
Applying formatting...

============================================================
✓ SDR generation complete!
  File: CJA_DataView_Production_Analytics_dv_677ea9291244fd082f02dd42_SDR.xlsx
  Size: 2.5 MB
  Time: 18.3 seconds
============================================================
```

### 5.3 Locate Your Output

The generated file is in the current directory:

```bash
ls -la *.xlsx
# Output: CJA_DataView_Production_Analytics_dv_677ea9291244fd082f02dd42_SDR.xlsx
```

> **Tip:** Use `--open` to automatically open the file after generation:
> ```bash
> cja_auto_sdr dv_677ea9291244fd082f02dd42 --open
> ```

### 5.4 Quick Stats (Optional)

Before generating a full report, you can quickly check what's in a data view:

```bash
cja_auto_sdr dv_677ea9291244fd082f02dd42 --stats
```

**Output:**
```
============================================================
DATA VIEW STATISTICS
============================================================

ID                             Name                          Metrics     Dims    Total
------------------------------------------------------------------------------------------
dv_677ea9291244fd082f02dd42    Production Analytics               145      287      432
------------------------------------------------------------------------------------------
TOTAL                                                              145      287      432

============================================================
```

This is useful for:
- Quickly verifying you have access to a data view
- Checking the size before generating a full report
- Scripting (use `--format json --output -` for machine-readable output)

---

## Step 6: Understand the Output

Open the generated Excel file. It contains 5 sheets:

### Sheet 1: Metadata

High-level information about the Data View:

| Field | Description |
|-------|-------------|
| Data View Name | The display name in CJA |
| Data View ID | The unique identifier |
| Owner | Email of the Data View owner |
| Created Date | When the Data View was created |
| Last Modified | When it was last updated |
| Total Metrics | Count of metrics in the Data View |
| Total Dimensions | Count of dimensions |
| Generation Date | When this SDR was created |

### Sheet 2: Data Quality

Results of automated validation checks:

| Column | Description |
|--------|-------------|
| Check Name | The validation performed |
| Severity | CRITICAL, HIGH, MEDIUM, or LOW |
| Status | PASSED, WARNING, or FAILED |
| Details | Specific issues found |
| Affected Items | Count of items with issues |
| Recommendations | Suggested remediation |

**Color coding:**
- **Green rows:** Passed checks
- **Yellow rows:** Warnings (minor issues)
- **Red rows:** Failed (critical issues to address)

### Sheet 3: DataView

Complete configuration export:

| Column | Description |
|--------|-------------|
| Component Type | "metric" or "dimension" |
| ID | Unique component identifier |
| Name | Display name in CJA |
| Description | Documentation text |
| Schema Path | XDM schema location |
| Data Type | String, integer, etc. |
| ... | Additional configuration fields |

### Sheet 4: Metrics

All metrics in the Data View with full configuration:

| Column | Description |
|--------|-------------|
| ID | Metric identifier |
| Name | Display name |
| Description | Documentation |
| Type | Calculated, derived, etc. |
| Format | Number, currency, percent |
| Decimal Places | Precision setting |
| Attribution | Attribution model settings |
| Lookback Window | Time window configuration |

### Sheet 5: Dimensions

All dimensions with full configuration:

| Column | Description |
|--------|-------------|
| ID | Dimension identifier |
| Name | Display name |
| Description | Documentation |
| Schema Path | XDM field location |
| Persistence | Session, hit, etc. |
| Allocation | First, last, most recent |
| Expiration | When values expire |
| Classification | Classification settings |

---

## Next Steps

Now that you've generated your first SDR, here are common next steps:

### Process Multiple Data Views

```bash
# Process all your Data Views at once
cja_auto_sdr dv_id1 dv_id2 dv_id3
```

### Generate All Formats

```bash
# Excel, CSV, JSON, and HTML
cja_auto_sdr dv_12345 --format all
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
cja_auto_sdr --diff dv_12345 dv_67890

# Save a baseline snapshot
cja_auto_sdr dv_12345 --snapshot ./baseline.json
```

See [Data View Comparison](DIFF_COMPARISON.md) for more details.

### Quick Reference

Keep the [Quick Reference Card](QUICK_REFERENCE.md) handy for common commands and options.

---

## Common First-Run Issues

### "Configuration file not found"

```
Error: Configuration file 'config.json' not found
```

**Solution:** Ensure `config.json` exists in the project root directory, not in a subdirectory.

```bash
ls config.json  # Should show the file
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
```powershell
PS> uv run cja_auto_sdr --version
# Command fails, hangs, or shows errors
```

**Solution:** Use Python directly instead:

```powershell
# Activate virtual environment
.venv\Scripts\activate

# Run with Python
python cja_sdr_generator.py --version
python cja_sdr_generator.py --list-dataviews
python cja_sdr_generator.py dv_12345
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

```powershell
# Activate virtual environment
.venv\Scripts\activate

# Reinstall NumPy
pip uninstall numpy
pip install --only-binary :all: numpy>=2.2.0

# Verify
python -c "import numpy; print(numpy.__version__)"

# Then run the tool
python cja_sdr_generator.py --version
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
   - [Troubleshooting Guide](TROUBLESHOOTING.md)
   - [CLI Reference](CLI_REFERENCE.md)
4. **Report issues:** [GitHub Issues](https://github.com/brian-a-au/cja_auto_sdr/issues)

---

## Summary

You've successfully:

1. Created Adobe API credentials
2. Installed and configured the tool
3. Verified your setup
4. Generated your first SDR document
5. Learned to interpret the output

Your SDR document is now ready to share with your team, include in documentation, or use for data governance audits.
