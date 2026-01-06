# Adobe Customer Journey Analytics Solution Design Reference Generator with Data Quality Validation

**Version 3.0** - A production-ready Python tool for auditing your Customer Journey Analytics (CJA) implementation by generating comprehensive Solution Design Reference (SDR) documents with enterprise-grade data quality validation, error handling, and modern dependency management.

## What Makes Version 3.0 Different

This tool evolved from a Jupyter notebook proof-of-concept into a production-ready, enterprise-grade automation solution. Building on the foundation established in the [CJA Summit 2025 notebook](https://github.com/pitchmuc/CJA_Summit_2025/blob/main/notebooks/06.%20CJA%20Data%20View%20Solution%20Design%20Reference%20Generator.ipynb), Version 3.0 introduces significant architectural improvements:

### Modern Python Tooling with UV

**From Jupyter Notebook to Production Application**
- **Reproducible Builds**: Lock file (`uv.lock`) ensures identical dependency versions across all environments
- **Lightning-Fast Installation**: UV's Rust-based resolver installs packages 10-100x faster than pip
- **Standardized Configuration**: `pyproject.toml` follows PEP 518/621 standards for modern Python projects
- **Zero Configuration Conflicts**: UV's advanced resolver eliminates dependency hell
- **Professional Project Structure**: Clear separation of concerns with proper package management

**Why UV Over Traditional pip?**
- **Speed**: Package resolution in milliseconds vs seconds/minutes
- **Reliability**: Deterministic builds with cryptographic lock files  
- **Simplicity**: One command (`uv sync`) replaces multiple pip operations
- **Modern**: Built for Python 3.14+ with future-proof architecture
- **Developer Experience**: Better error messages, faster iteration cycles

### Enterprise-Grade Reliability (New in v3.0)

**Comprehensive Error Handling & Validation**
- Pre-flight configuration validation before API calls
- Graceful degradation when partial data is unavailable  
- Detailed error messages with actionable troubleshooting steps
- Automatic data view existence verification
- API connection health checks with retry logic
- Safe filename generation and permission handling

**Production Logging System**
- Timestamped log files with rotation in dedicated `logs/` directory
- Dual output streams (console + file) for real-time monitoring and audit trails
- Structured logging with severity levels (INFO, WARNING, ERROR, CRITICAL)
- Performance metrics tracking for optimization
- Complete execution summaries for reporting

### Advanced Data Quality Validation (New in v3.0)

**Automated Quality Assurance**
Unlike the original notebook's simple data retrieval, v3.0 includes a comprehensive data quality framework:

- **8+ Validation Checks**: Duplicates, missing fields, null values, invalid IDs, empty datasets
- **Severity Classification**: CRITICAL, HIGH, MEDIUM, LOW with color-coded Excel formatting
- **Actionable Insights**: Detailed issue descriptions with affected component lists
- **Quality Dashboard**: Dedicated "Data Quality" sheet with filtering and sorting
- **Trend Analysis Ready**: Consistent reporting format for tracking quality over time

**Quality Checks Include:**
1. Duplicate component name detection across metrics and dimensions
2. Required field validation (id, name, type)
3. Critical field null value identification
4. Missing description detection for documentation completeness
5. Invalid or malformed ID detection
6. Empty dataset handling and reporting
7. API response structure validation
8. Cross-referential integrity checks

### From Script to Application

**Architectural Improvements**

| Aspect | Original Notebook | Version 3.0 |
|--------|------------------|-------------|
| **Execution Model** | Interactive cells | Standalone application |
| **Error Handling** | Basic try-catch | Multi-layer defensive programming |
| **Logging** | Print statements | Professional logging framework |
| **Dependencies** | Manual installation | Managed via pyproject.toml + uv |
| **Data Quality** | None | 8+ automated checks |
| **Configuration** | Hardcoded values | Validated external config |
| **Reliability** | Single-run, manual | Production-ready with retries |
| **Maintainability** | Notebook-based | Modular Python classes |
| **Scalability** | Single data view | Batch processing ready |
| **Output** | Basic Excel | Formatted with conditional styling |

### Enhanced Output & Documentation

**Professional Excel Workbooks**
- **5 Formatted Sheets**: Metadata, Data Quality, DataView details, Metrics, Dimensions
- **Conditional Formatting**: Severity-based color coding for instant issue identification
- **Auto-filtering**: Every sheet has sortable, filterable columns
- **Frozen Headers**: Easy navigation through large datasets
- **Text Wrapping**: Readable long descriptions and JSON content
- **Alternating Rows**: Improved visual scanning

**Comprehensive Metadata**
- Generation timestamp with timezone
- Component type distributions and breakdowns  
- Data quality summary with issue counts by severity
- Version tracking for audit compliance
- API response metadata for troubleshooting

### Operational Excellence

**Built for Automation**
- Command-line friendly (batch scripts, cron jobs, CI/CD pipelines)
- Exit codes for monitoring and alerting systems
- Structured logs for log aggregation tools (Splunk, ELK, Datadog)
- Reproducible builds for containerization (Docker, Kubernetes)
- Environment variable support for secure credential management

**DevOps Ready**
```bash
# Single command deployment
uv sync && uv run python cja_sdr_generator.py

# Scheduled execution (cron)
0 9 * * 1 cd /path/to/project && uv run python cja_sdr_generator.py

# CI/CD pipeline integration
- name: Generate SDR
  run: |
    uv sync
    uv run python cja_sdr_generator.py
```

### Documentation & Support

**Comprehensive README**
- Detailed installation instructions for all platforms
- Troubleshooting guide with common error solutions
- Best practices for production usage
- Security guidelines for credential management
- Performance optimization tips
- Multiple usage examples and scenarios

### Who Should Use Version 3.0?

**Ideal For:**
- **Analytics Teams** requiring regular SDR documentation
- **DevOps Engineers** automating CJA audits in CI/CD pipelines
- **Data Governance** teams needing audit trails and quality tracking
- **Consultants** managing multiple client CJA implementations
- **Enterprise Organizations** with compliance and documentation requirements

**Migration Path from Notebook:**
The notebook version is excellent for learning and ad-hoc exploration. Version 3.0 is designed for teams that need:
- Scheduled, automated SDR generation
- Data quality monitoring over time
- Reliable execution in production environments
- Professional documentation for stakeholders
- Audit trails for compliance purposes

---

## Table of Contents

* **1. Overview**
  * 1.1 What the Script Does
  * 1.2 Key Features
  * 1.3 What's New in This Version
* **2. Pre-requisites**
  * 2.1 System Requirements
  * 2.2 Required Libraries
  * 2.3 Authentication Setup
* **3. Installation**
  * 3.1 Installing uv Package Manager
  * 3.2 Project Setup
  * 3.3 Configuration File Setup
* **4. Usage**
  * 4.1 Basic Usage
  * 4.2 Configuration
  * 4.3 Running the Script
  * 4.4 Output Files
* **5. Output Structure**
  * 5.1 Excel Workbook Sheets
  * 5.2 Log Files
* **6. Data Quality Validation**
  * 6.1 Validation Checks
  * 6.2 Severity Levels
  * 6.3 Understanding Issues
* **7. Error Handling**
  * 7.1 Connection Errors
  * 7.2 Authentication Issues
  * 7.3 Data View Problems
  * 7.4 Troubleshooting Guide
* **8. Use Cases**
* **9. Best Practices**
* **10. Support and Logging**

---

## 1. Overview

### 1.1 What the Script Does

This enterprise-grade script audits your Customer Journey Analytics implementation by:

1. **Connecting to CJA**: Establishes secure API connection with comprehensive validation
2. **Validating Data Views**: Verifies data view existence and accessibility before processing
3. **Fetching Components**: Retrieves all metrics and dimensions from your specified Data View
4. **Quality Validation**: Performs 8+ automated data quality checks on your components
5. **Generating Documentation**: Creates a professionally formatted Excel workbook with multiple sheets
6. **Comprehensive Logging**: Tracks all operations with detailed logs for auditing and troubleshooting

### 1.2 Key Features

**Enterprise-Grade Error Handling**
- Validates configuration files before connection attempts
- Graceful failure handling with actionable error messages
- Automatic retry logic for transient failures
- Comprehensive logging to both console and file

**Advanced Data Quality Validation**
- Duplicate detection across metrics and dimensions
- Required field validation
- Null value identification in critical fields
- Missing description detection
- Invalid ID detection
- Empty dataset handling
- Color-coded severity levels (CRITICAL, HIGH, MEDIUM, LOW)

**Professional Excel Output**
- Six formatted sheets with color-coded data quality issues
- Alternating row colors for readability
- Auto-filtering and frozen headers on all sheets
- Automatic column width adjustment
- Text wrapping for long content
- Severity-based conditional formatting

**Robust Logging System**
- Timestamped log files in dedicated `logs/` directory
- Dual output to console and file
- Detailed operation tracking
- Error diagnosis information
- Execution summaries

### 1.3 What's New in This Version

**Version 3.0 Enhancements:**

✅ **Modern Dependency Management**
- Uses `uv` for fast, reliable package management
- `pyproject.toml` for standardized project configuration
- Reproducible builds with lock files
- Python 3.14+ compatibility

✅ **Comprehensive Error Handling**
- Pre-flight validation of configuration files
- API connection testing before data operations
- Graceful handling of network failures
- Detailed error messages with troubleshooting steps

✅ **Data Quality Validation**
- Automated quality checks with detailed reporting
- New "Data Quality" sheet with color-coded issues
- Severity-based prioritization
- Actionable recommendations

✅ **Advanced Logging**
- Timestamped log files with rotation
- Progress tracking for long operations
- Error diagnosis and stack traces
- Execution summary reporting

✅ **Improved Reliability**
- Validates data view existence before processing
- Handles empty datasets gracefully
- Continues processing despite partial failures
- Safe filename generation

---

## 2. Pre-requisites

### 2.1 System Requirements

- **Python**: Version 3.14 or higher
- **uv**: Modern Python package manager (recommended)
- **Operating System**: Windows, macOS, or Linux
- **Disk Space**: Minimum 100MB for logs and output files
- **Network**: Internet connectivity to Adobe CJA APIs

### 2.2 Required Libraries

All dependencies are managed through `pyproject.toml`:

```toml
[project]
name = "cja-auto-sdr-2026"
version = "0.1.0"
description = "Customer Journey Analytics SDR Generator with Data Quality Validation"
readme = "README.md"
requires-python = ">=3.14"
dependencies = [
    "cjapy>=0.2.4.post2",
    "pandas>=2.3.3",
    "xlsxwriter>=3.2.9",
]
```

**Core Dependencies:**
- `cjapy>=0.2.4.post2` - Customer Journey Analytics API wrapper
- `pandas>=2.3.3` - Data manipulation and analysis
- `xlsxwriter>=3.2.9` - Excel file generation with formatting
- `pytz` - Timezone handling (included with pandas)

### 2.3 Authentication Setup

You need a valid Adobe I/O integration with CJA API access:
- Organization ID
- Client ID (API Key)
- Technical Account ID
- Client Secret
- Private Key file

---

## 3. Installation

### 3.1 Installing uv Package Manager

`uv` is a fast Python package installer and resolver written in Rust. It's significantly faster than pip and provides better dependency resolution.

**macOS and Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows (PowerShell):**
```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**Alternative (using pip):**
```bash
pip install uv
```

**Verify installation:**
```bash
uv --version
```

### 3.2 Project Setup

#### Option 1: Clone/Download Project (Recommended)

If you have the project directory with `pyproject.toml`:

```bash
# Navigate to project directory
cd cja-auto-sdr-2026

# Create virtual environment and install dependencies
uv sync

# Activate the virtual environment
# On macOS/Linux:
source .venv/bin/activate

# On Windows:
.venv\Scripts\activate
```

The `uv sync` command will:
- Create a virtual environment in `.venv/`
- Install all dependencies from `pyproject.toml`
- Generate a `uv.lock` file for reproducible builds

#### Option 2: Start from Scratch

If starting a new project:

```bash
# Create new project
uv init cja-auto-sdr-2026
cd cja-auto-sdr-2026

# Add dependencies
uv add cjapy>=0.2.4.post2
uv add pandas>=2.3.3
uv add xlsxwriter>=3.2.9

# Copy your script into the project directory
# Copy myconfig.json into the project directory
```

#### Option 3: Legacy pip Installation

If you prefer traditional pip:

```bash
# Create virtual environment
python -m venv .venv

# Activate virtual environment
# On macOS/Linux:
source .venv/bin/activate
# On Windows:
.venv\Scripts\activate

# Install dependencies
pip install cjapy>=0.2.4.post2 pandas>=2.3.3 xlsxwriter>=3.2.9
```

### 3.3 Configuration File Setup

Create a `myconfig.json` file in the project root directory:

```json
{
  "org_id": "your_org_id@AdobeOrg",
  "client_id": "your_client_id",
  "tech_id": "your_tech_account_id@techacct.adobe.com",
  "secret": "your_client_secret",
  "private_key": "path/to/private.key"
}
```

**Configuration Fields:**
- `org_id`: Your Adobe Organization ID (found in Adobe I/O Console)
- `client_id`: API Key / Client ID from your integration
- `tech_id`: Technical Account ID (email format)
- `secret`: Client Secret from your integration
- `private_key`: Path to your private key file (.key or .pem)

**Project Structure:**
```
cja-auto-sdr-2026/
├── .venv/                    # Virtual environment (created by uv)
├── logs/                     # Log files (created automatically)
├── pyproject.toml           # Project configuration
├── uv.lock                  # Dependency lock file (created by uv)
├── myconfig.json            # Your CJA credentials (DO NOT COMMIT)
├── private.key              # Your private key (DO NOT COMMIT)
├── cja_sdr_generator.py     # Main script
└── README.md                # This file
```

**Security Note:** Keep `myconfig.json` and `private.key` secure and never commit them to version control. Add them to your `.gitignore` file:

```gitignore
# .gitignore
myconfig.json
*.key
*.pem
.venv/
logs/
*.xlsx
```

---

## 4. Usage

### 4.1 Basic Usage

1. **Prepare Configuration**: Ensure `myconfig.json` is properly configured
2. **Activate Virtual Environment**: Run `source .venv/bin/activate` (or Windows equivalent)
3. **Set Data View ID**: Edit the script to specify your target data view
4. **Run the Script**: Execute using Python or uv
5. **Review Output**: Check the generated Excel file and log file

### 4.2 Configuration

Edit these variables in the script:

```python
# Set your target Data View ID
data_view = "dv_677ea9291244fd082f02dd42"

# Optional: Change config file location
config_file = "myconfig.json"
```

### 4.3 Running the Script

**Using uv (Recommended):**
```bash
# Make sure you're in the project directory
cd cja-auto-sdr-2026

# Run with uv (automatically uses project's virtual environment)
uv run python cja_sdr_generator.py
```

**Using Python directly:**
```bash
# Make sure virtual environment is activated first
source .venv/bin/activate  # macOS/Linux
# or
.venv\Scripts\activate     # Windows

# Run the script
python cja_sdr_generator.py
```

**Adding Script as a Command:**

You can add the script as a project command in `pyproject.toml`:

```toml
[project.scripts]
generate-sdr = "cja_sdr_generator:main"
```

Then run with:
```bash
uv run generate-sdr
```

**Expected Console Output:**
```
2025-01-05 10:30:15 - INFO - Logging initialized. Log file: logs/SDR_Generation_dv_677ea9291244fd082f02dd42_20250105_103015.log
============================================================
INITIALIZING CJA CONNECTION
============================================================
2025-01-05 10:30:16 - INFO - Validating configuration file: myconfig.json
2025-01-05 10:30:16 - INFO - Configuration file structure validated successfully
2025-01-05 10:30:17 - INFO - CJA instance created successfully
2025-01-05 10:30:17 - INFO - Testing API connection...
2025-01-05 10:30:18 - INFO - ✓ API connection successful! Found 5 data view(s)
============================================================
VALIDATING DATA VIEW
============================================================
2025-01-05 10:30:19 - INFO - ✓ Data view validated successfully!
2025-01-05 10:30:19 - INFO -   Name: Production Analytics
2025-01-05 10:30:19 - INFO -   ID: dv_677ea9291244fd082f02dd42
============================================================
Starting data fetch operations
============================================================
2025-01-05 10:30:20 - INFO - Successfully fetched 150 metrics
2025-01-05 10:30:22 - INFO - Successfully fetched 75 dimensions
============================================================
Starting data quality validation
============================================================
2025-01-05 10:30:23 - INFO - Data quality checks complete. Found 3 issue(s)
============================================================
GENERATING EXCEL FILE
============================================================
2025-01-05 10:30:25 - INFO - ✓ SDR generation complete! File saved as: CJA_DataView_Production_Analytics_dv_677ea9291244fd082f02dd42_SDR.xlsx
```

### 4.4 Output Files

**Excel Workbook:**
- Filename: `CJA_DataView_[Name]_[ID]_SDR.xlsx`
- Location: Project root directory
- Size: Typically 1-10 MB depending on data view size

**Log File:**
- Filename: `SDR_Generation_[DataViewID]_[Timestamp].log`
- Location: `logs/` subdirectory (created automatically)
- Contains: Complete execution trace with timestamps

---

## 5. Output Structure

### 5.1 Excel Workbook Sheets

#### **Sheet 1: Metadata**
Summary information about the data view and generation process:
- Generation timestamp with timezone
- Data View ID and name
- Total metrics and dimensions count
- Component type breakdown
- Data quality issue summary
- Severity distribution

#### **Sheet 2: Data Quality** (NEW in v3.0)
Comprehensive data quality report with color-coded severity:
- **CRITICAL** (Red): Issues requiring immediate attention
- **HIGH** (Yellow): Important issues affecting functionality
- **MEDIUM** (Green): Moderate issues to address
- **LOW** (Blue): Minor improvements recommended

Columns:
- Severity level
- Category (Duplicates, Missing Fields, Null Values, etc.)
- Type (Metrics/Dimensions)
- Item Name (affected component)
- Issue description
- Detailed explanation

#### **Sheet 3: DataView**
Complete data view configuration details:
- Data view metadata
- Configuration settings
- Applied filters/segments
- Date range settings
- All JSON-formatted for technical reference

#### **Sheet 4: Metrics**
All metrics with full details:
- Metric ID and name
- Type (calculated, standard, currency, etc.)
- Title and description
- Data type
- Formatting rules
- Attribution settings
- Additional metadata (JSON formatted)

#### **Sheet 5: Dimensions**
All dimensions with comprehensive information:
- Dimension ID and name
- Type (string, numeric, time-based, etc.)
- Title and description
- Data type
- Classification settings
- Persistence settings
- Additional metadata (JSON formatted)

### 5.2 Log Files

Log files are stored in the `logs/` directory with detailed information:

```
logs/
└── SDR_Generation_dv_677ea9291244fd082f02dd42_20250105_103015.log
```

**Log Content Includes:**
- Timestamp for each operation
- Success/failure status
- Error messages and stack traces
- API response times
- Data quality findings
- File generation progress
- Execution summary

---

## 6. Data Quality Validation

### 6.1 Validation Checks

The script performs the following automated checks:

1. **Duplicate Detection**
   - Identifies metrics/dimensions with identical names
   - Severity: HIGH
   - Impact: Causes confusion in reporting

2. **Required Fields Validation**
   - Ensures `id`, `name`, and `type` fields are present
   - Severity: CRITICAL
   - Impact: Missing fields prevent proper component usage

3. **Null Value Detection**
   - Finds missing values in critical fields (id, name, title, description)
   - Severity: MEDIUM
   - Impact: Incomplete metadata affects discoverability

4. **Missing Descriptions**
   - Identifies components without descriptions
   - Severity: LOW
   - Impact: Reduces documentation quality

5. **Empty Dataset Check**
   - Detects if API returns no data
   - Severity: CRITICAL
   - Impact: No components available for analysis

6. **Invalid ID Check**
   - Finds components with missing or malformed IDs
   - Severity: HIGH
   - Impact: Components cannot be referenced properly

7. **Field Existence Validation**
   - Verifies expected columns are present in API response
   - Severity: CRITICAL
   - Impact: May indicate API changes or permissions issues

8. **Data Completeness**
   - Overall assessment of data quality
   - Multiple severity levels
   - Impact: Varies by specific issue

### 6.2 Severity Levels

**CRITICAL (Red Background)**
- Requires immediate attention
- Blocks core functionality
- Examples: Missing required fields, empty datasets, API errors

**HIGH (Yellow Background)**
- Important issues affecting reliability
- Should be addressed soon
- Examples: Duplicate names, invalid IDs, authentication warnings

**MEDIUM (Green Background)**
- Moderate quality issues
- Address when convenient
- Examples: Null values in secondary fields, minor inconsistencies

**LOW (Blue Background)**
- Minor improvements recommended
- Does not affect functionality
- Examples: Missing descriptions, formatting suggestions

### 6.3 Understanding Issues

Each data quality issue includes:
- **Category**: Type of problem (Duplicates, Missing Fields, etc.)
- **Type**: Whether it affects Metrics or Dimensions
- **Item Name**: Specific component(s) affected
- **Issue**: Clear description of the problem
- **Details**: Additional context and affected items

**Example Issues:**

```
Severity: HIGH
Category: Duplicates
Type: Metrics
Item Name: Page Views
Issue: Duplicate name found 2 times
Details: This metrics name appears 2 times in the data view
```

```
Severity: MEDIUM
Category: Null Values
Type: Dimensions
Item Name: 5 items
Issue: Null values in "description" field
Details: 5 item(s) missing description. Items: eVar1, eVar5, prop3...
```

---

## 7. Error Handling

### 7.1 Connection Errors

**Problem**: Cannot connect to CJA API

**Possible Causes:**
- Invalid credentials in `myconfig.json`
- Network connectivity issues
- Adobe service outage
- Expired authentication tokens

**Solutions:**
1. Verify all fields in `myconfig.json` are correct
2. Check network connectivity
3. Confirm private key file exists and is readable
4. Check Adobe Status page for service issues
5. Regenerate credentials in Adobe I/O Console

**Log Output:**
```
CRITICAL - CJA INITIALIZATION FAILED
CRITICAL - Failed to initialize CJA connection: Authentication failed
CRITICAL - Troubleshooting steps:
CRITICAL - 1. Verify your configuration file exists and is valid JSON
CRITICAL - 2. Check that all authentication credentials are correct
```

### 7.2 Authentication Issues

**Problem**: Authentication fails with valid credentials

**Possible Causes:**
- Incorrect organization ID
- Private key doesn't match integration
- Insufficient API permissions
- Integration not enabled for CJA

**Solutions:**
1. Verify `org_id` matches Adobe I/O Console
2. Re-download private key from integration
3. Check integration has "Customer Journey Analytics" API enabled
4. Verify product profile includes CJA access

### 7.3 Data View Problems

**Problem**: Data view validation fails

**Error Messages:**
```
ERROR - Data view 'dv_12345' returned empty response
INFO - You have access to 5 data view(s):
INFO -   1. Production Analytics (ID: dv_abc123)
INFO -   2. Development Analytics (ID: dv_def456)
```

**Solutions:**
1. Copy the correct data view ID from the log output
2. Verify you have access permissions to the data view
3. Confirm the data view exists in your organization
4. Check with admin if you need access granted

### 7.4 Troubleshooting Guide

#### Script Won't Start

**Check Python Version:**
```bash
python --version  # Should be 3.14 or higher
```

**Check uv Installation:**
```bash
uv --version
```

**Verify Virtual Environment:**
```bash
# List installed packages
uv pip list

# Should show cjapy, pandas, xlsxwriter
```

**Check Configuration File:**
```bash
# Verify file exists
ls myconfig.json

# Validate JSON syntax
python -c "import json; json.load(open('myconfig.json'))"
```

#### Dependency Issues

**Problem**: Module not found errors

**Solutions:**
```bash
# Reinstall all dependencies
uv sync --reinstall

# Or manually install missing package
uv add package-name

# Verify installation
uv pip list | grep package-name
```

**Problem**: Version conflicts

**Solutions:**
```bash
# Check for conflicts
uv pip check

# Update specific package
uv add --upgrade package-name

# Regenerate lock file
rm uv.lock
uv sync
```

#### Virtual Environment Issues

**Problem**: Wrong Python version or packages

**Solutions:**
```bash
# Remove and recreate virtual environment
rm -rf .venv
uv sync

# Or specify Python version
uv venv --python 3.14
uv sync
```

#### Empty Output File

**Check Log File For:**
- "No metrics returned from API"
- "No dimensions returned from API"
- Possible data view has no components configured

**Solutions:**
- Verify data view has components
- Check API permissions include read access
- Try different data view

#### File Permission Errors

**Error:** `PermissionError: [Errno 13] Permission denied`

**Cause:** Output file is open in Excel or locked

**Solution:** Close the Excel file and re-run script

#### Slow Performance

**Normal Duration:** 30-60 seconds for typical data view

**If Slower:**
- Large data views (200+ components) take longer
- Network latency affects API calls
- Check log file for which operation is slow

**Performance Tips:**
```bash
# Run with Python optimization
uv run python -O cja_sdr_generator.py

# Check network latency
ping adobe.io
```

---

## 8. Use Cases

### Comprehensive Implementation Audit
Quickly understand the breadth and depth of your CJA setup:
- Total metrics and dimensions available
- Component type distribution
- Configuration completeness
- Data quality status

**Best For:** Quarterly reviews, new team member onboarding

### Implementation Verification
Ensure your CJA implementation matches planning documents:
- Compare against original SDR
- Validate naming conventions
- Verify all planned metrics exist
- Identify configuration drift

**Best For:** Post-implementation validation, compliance audits

### Data Quality Assurance
Maintain high-quality analytics configuration:
- Identify duplicate components
- Find missing descriptions
- Validate metadata completeness
- Track quality trends over time

**Best For:** Ongoing maintenance, quality improvement initiatives

### Team Onboarding
Assist new team members in understanding CJA setup:
- Provide complete component reference
- Document available metrics/dimensions
- Share data view configuration
- Explain component relationships

**Best For:** Training, documentation, knowledge transfer

### Change Management
Document configuration before and after changes:
- Baseline current configuration
- Compare versions over time
- Track component additions/removals
- Audit change impact

**Best For:** Release management, change control processes

### Multi-Environment Comparison
Compare configurations across environments:
- Generate SDRs for dev, staging, production
- Identify configuration differences
- Ensure consistency across environments
- Plan promotion strategies

**Best For:** DevOps, environment management

### Compliance Documentation
Generate audit-ready documentation:
- Complete component inventory
- Metadata completeness tracking
- Data quality reporting
- Timestamped generation logs

**Best For:** SOC2, ISO, internal audit requirements

### Migration Planning
Prepare for migrations or upgrades:
- Document current state comprehensively
- Identify components to migrate
- Plan migration sequence
- Validate post-migration configuration

**Best For:** Platform migrations, major version upgrades

---

## 9. Best Practices

### Dependency Management with uv

**Lock File Management**
- Commit `uv.lock` to version control for reproducible builds
- Update dependencies regularly: `uv sync --upgrade`
- Test updates in development before production

**Virtual Environment**
- Always use the project's virtual environment
- Don't install packages globally
- Use `uv run` to automatically activate environment

**Adding New Dependencies**
```bash
# Add new package
uv add package-name

# Add with version constraint
uv add "package-name>=1.0.0"

# Add development dependency
uv add --dev pytest
```

### Regular Execution
- Generate SDRs monthly for trending
- Run after significant configuration changes
- Schedule quarterly comprehensive audits
- Maintain version history of output files

**Automated Scheduling:**

**Linux/macOS (cron):**
```bash
# Edit crontab
crontab -e

# Run every Monday at 9 AM
0 9 * * 1 cd /path/to/cja-auto-sdr-2026 && /path/to/uv run python cja_sdr_generator.py
```

**Windows (Task Scheduler):**
```powershell
# Create scheduled task
$action = New-ScheduledTaskAction -Execute "uv" -Argument "run python cja_sdr_generator.py" -WorkingDirectory "C:\path\to\cja-auto-sdr-2026"
$trigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At 9am
Register-ScheduledTask -Action $action -Trigger $trigger -TaskName "CJA SDR Generation"
```

### Data Quality Management
- Review and address CRITICAL issues immediately
- Create tickets for HIGH severity items
- Schedule MEDIUM/LOW items for maintenance windows
- Track resolution of recurring issues

### Documentation
- Store SDR files in shared documentation repository
- Include generation date in version control
- Link to relevant project documentation
- Share with stakeholders and team members

### Version Control
- Keep log files for audit trails
- Archive historical SDRs
- Track changes between versions
- Document reasons for configuration changes

**Git Best Practices:**
```bash
# Add to .gitignore
echo "myconfig.json" >> .gitignore
echo "*.key" >> .gitignore
echo "*.pem" >> .gitignore
echo "logs/" >> .gitignore
echo "*.xlsx" >> .gitignore

# Commit project files
git add pyproject.toml uv.lock
git commit -m "Update dependencies"
```

### Security
- Never commit `myconfig.json` to version control
- Rotate credentials periodically
- Use service accounts for automated runs
- Restrict access to sensitive data views
- Store private keys securely (use key management systems)

### Performance Optimization
- Run during off-peak hours if possible
- Use caching for development/testing
- Process multiple data views in batch
- Monitor execution time trends

### Automation with uv

**Create Automation Scripts:**

Create `scripts/generate_sdr.sh`:
```bash
#!/bin/bash
cd "$(dirname "$0")/.."
uv run python cja_sdr_generator.py
```

Or `scripts/generate_sdr.ps1`:
```powershell
Set-Location $PSScriptRoot\..
uv run python cja_sdr_generator.py
```

Make executable:
```bash
chmod +x scripts/generate_sdr.sh
```

**Multiple Data Views:**

Create a batch script `generate_all_sdrs.py`:
```python
import subprocess
import sys

data_views = [
    "dv_production_12345",
    "dv_staging_67890",
    "dv_development_abcde"
]

for dv in data_views:
    print(f"Generating SDR for {dv}...")
    subprocess.run([sys.executable, "cja_sdr_generator.py", dv])
```

Run with:
```bash
uv run python generate_all_sdrs.py
```

---

## 10. Support and Logging

### Log File Location

All logs are stored in the `logs/` directory:
```
logs/
├── SDR_Generation_dv_677ea9291244fd082f02dd42_20250105_103015.log
├── SDR_Generation_dv_677ea9291244fd082f02dd42_20250105_140522.log
└── SDR_Generation_dv_abc123def456_20250105_160330.log
```

### Log Levels

- **INFO**: Normal operations and progress updates
- **WARNING**: Non-critical issues that don't stop execution
- **ERROR**: Errors that may affect output quality
- **CRITICAL**: Fatal errors that stop execution

### Getting Help

If you encounter issues:

1. **Check the log file** in `logs/` directory for detailed error information
2. **Review the Data Quality sheet** for configuration issues
3. **Verify configuration** in `myconfig.json`
4. **Check prerequisites** are met (Python version, uv installation, libraries)
5. **Consult troubleshooting guide** above

### Reporting Issues

When reporting issues, include:
- Complete error message from console
- Relevant log file entries
- Python version: `python --version`
- uv version: `uv --version`
- Dependency versions: `uv pip list`
- Project info: `cat pyproject.toml`
- Anonymized configuration (remove sensitive data)
- Steps to reproduce

### Environment Information

**Quick diagnostic script:**
```bash
#!/bin/bash
echo "=== System Information ==="
python --version
uv --version
echo ""
echo "=== Project Dependencies ==="
uv pip list
echo ""
echo "=== Project Configuration ==="
cat pyproject.toml
echo ""
echo "=== Recent Logs ==="
ls -lh logs/ | tail -5
```

Save as `diagnose.sh` and run:
```bash
chmod +x diagnose.sh
./diagnose.sh > diagnostic_report.txt
```

### Common Error Solutions

**Error: `ModuleNotFoundError: No module named 'cjapy'`**
```bash
# Solution: Sync dependencies
uv sync

# Or reinstall
uv sync --reinstall
```

**Error: `uv: command not found`**
```bash
# Solution: Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Then sync project
uv sync
```

**Error: `Python version mismatch`**
```bash
# Solution: Recreate with correct Python version
rm -rf .venv
uv venv --python 3.14
uv sync
```

**Error: `Could not find a version that satisfies the requirement`**
```bash
# Solution: Update package index
uv pip install --upgrade pip
uv sync --reinstall
```

---

## 11. Additional Resources

### uv Documentation
- Official uv Documentation: https://github.com/astral-sh/uv
- uv Installation Guide: https://astral.sh/uv
- Python Packaging Guide: https://packaging.python.org/

### CJA API Resources
- Adobe Analytics API Documentation: https://developer.adobe.com/cja-apis/docs/
- cjapy Library Documentation: https://github.com/pitchmuc/cjapy
- Adobe I/O Console: https://console.adobe.io/

### Python Resources
- Python 3.14 Documentation: https://docs.python.org/3.14/
- pandas Documentation: https://pandas.pydata.org/docs/
- xlsxwriter Documentation: https://xlsxwriter.readthedocs.io/

### Project Updates

**Check for Updates:**
```bash
# Update all dependencies
uv sync --upgrade

# Update specific package
uv add --upgrade cjapy
```

**View Dependency Tree:**
```bash
uv pip show cjapy
```

**Export Dependencies:**
```bash
# Export for pip compatibility
uv pip compile pyproject.toml -o requirements.txt
```

---

## Conclusion

This enhanced CJA SDR Generator provides enterprise-grade reliability, comprehensive data quality validation, and detailed logging to ensure your Customer Journey Analytics implementation is well-documented, maintainable, and audit-ready. 

With modern dependency management via `uv` and `pyproject.toml`, the project offers:
- **Fast, reliable installations** with uv's Rust-powered package resolution
- **Reproducible builds** through lock files
- **Easy updates** with simple commands
- **Professional project structure** following Python best practices

The automated quality checks help maintain high standards while the robust error handling ensures reliable execution even in challenging environments.

By automating what could be a time-consuming manual process, you can spend more time on analysis and less on administration, while maintaining confidence in your analytics configuration quality.

### Quick Start Reminder

```bash
# 1. Clone/download project
cd cja-auto-sdr-2026

# 2. Install uv (if needed)
curl -LsSf https://astral.sh/uv/install.sh | sh

# 3. Setup project
uv sync

# 4. Configure credentials
# Create myconfig.json with your Adobe credentials

# 5. Run the generator
uv run python cja_sdr_generator.py

# 6. Review output
# Check the generated Excel file and logs/ directory
```

**Happy auditing! 🚀**