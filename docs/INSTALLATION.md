# Installation Guide

Complete setup instructions for the CJA SDR Generator.

## System Requirements

- **Python**: Version 3.14 or higher
- **uv**: Modern Python package manager (recommended)
- **Operating System**: Windows, macOS, or Linux
- **Disk Space**: Minimum 100MB for logs and output files
- **Network**: Internet connectivity to Adobe CJA APIs

## Installing uv Package Manager

`uv` is a fast Python package installer written in Rust. It's significantly faster than pip and provides better dependency resolution.

### macOS and Linux

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### Windows (PowerShell)

```powershell
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"
```

### Alternative (using pip)

```bash
pip install uv
```

### Verify Installation

```bash
uv --version
```

## Project Setup

### Option 1: Clone from Git (Recommended)

**Step 1: Choose an installation location**

```bash
# Examples of where to install:
cd ~/projects          # A projects folder in your home directory
cd ~/Documents         # Your documents folder
cd /opt                # System-wide location (may need sudo)
```

**Step 2: Clone the repository**

```bash
git clone https://github.com/your-org/cja_auto_sdr.git
cd cja_auto_sdr
```

**Step 3: Install dependencies**

```bash
uv sync
```

The `uv sync` command will:
- Create a virtual environment in `.venv/`
- Install all dependencies from `pyproject.toml`
- Generate a `uv.lock` file for reproducible builds
- Install the `cja_auto_sdr` console script

**Step 4: Verify installation**

```bash
# Using uv run (no venv activation needed)
uv run cja_auto_sdr --version

# Or activate the venv first, then run directly
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows
cja_auto_sdr --version
```

> **Note:** All subsequent commands assume you're in the `cja_auto_sdr` directory.

### Option 2: Download ZIP

If you don't have git installed:

1. Download the repository as a ZIP file
2. Extract to your preferred location
3. Open terminal and navigate to the extracted folder:
   ```bash
   cd ~/Downloads/cja_auto_sdr-main  # adjust path as needed
   ```
4. Install dependencies:
   ```bash
   uv sync
   ```

### Option 3: Global Installation (pip)

For system-wide installation without cloning:

```bash
# Clone first
git clone https://github.com/your-org/cja_auto_sdr.git
cd cja_auto_sdr

# Install globally (no venv needed after this)
pip install .

# Now usable from anywhere
cja_auto_sdr --version
```

### Option 4: Legacy pip with Virtual Environment

```bash
# Clone the repository
git clone https://github.com/your-org/cja_auto_sdr.git
cd cja_auto_sdr

# Create virtual environment
python -m venv .venv

# Activate
source .venv/bin/activate  # macOS/Linux
# .venv\Scripts\activate   # Windows PowerShell

# Install dependencies
pip install -r requirements.txt
# Or manually:
pip install cjapy>=0.2.4.post2 pandas>=2.3.3 xlsxwriter>=3.2.9 tqdm>=4.66.0
```

### Option 5: Windows Native Setup (Recommended for Windows Users)

If you encounter issues with `uv` on Windows (especially NumPy import errors), use this native Python approach:

**Step 1: Verify Python Installation**

```text
# Check Python version (must be 3.14+)
python --version

# Verify Python is from python.org, not Microsoft Store
python -c "import sys; print(sys.executable)"
# Should show: C:\Users\YourName\AppData\Local\Programs\Python\...
# NOT: C:\Users\YourName\AppData\Local\Microsoft\WindowsApps\...
```

> **Note:** If Python is from Microsoft Store, uninstall it and reinstall from [python.org](https://www.python.org/downloads/). Check "Add Python to PATH" during installation.

**Step 2: Clone and Setup**

```text
# Clone the repository
git clone https://github.com/your-org/cja_auto_sdr.git
cd cja_auto_sdr

# Create virtual environment
python -m venv .venv

# Activate virtual environment
.venv\Scripts\activate

# Upgrade pip
python -m pip install --upgrade pip

# Install dependencies
pip install cjapy>=0.2.4.post2 pandas>=2.3.3 xlsxwriter>=3.2.9 tqdm>=4.66.0 numpy>=2.2.0

# Install the tool in development mode
pip install -e .
```

**Step 3: Verify Installation**

```text
# Test imports
python -c "import numpy; print(f'NumPy: {numpy.__version__}')"
python -c "import pandas; print(f'Pandas: {pandas.__version__}')"
python -c "import cjapy; print('cjapy: OK')"

# Test the tool
python cja_sdr_generator.py --version
# Or if the console script was installed:
cja_auto_sdr --version
```

**Step 4: Run the Tool**

```text
# Option 1: Run the script directly (most reliable)
python cja_sdr_generator.py --list-dataviews
python cja_sdr_generator.py dv_YOUR_DATA_VIEW_ID

# Option 2: Use the console script (if installation succeeded)
cja_auto_sdr --list-dataviews
cja_auto_sdr dv_YOUR_DATA_VIEW_ID

# Option 3: Use full path to Python in venv
.venv\Scripts\python.exe cja_sdr_generator.py --version
```

**Common Windows Issues:**

| Issue | Solution |
|-------|----------|
| `uv run` doesn't work | Use `python cja_sdr_generator.py` instead |
| NumPy ImportError | Reinstall with `pip install --only-binary :all: numpy` |
| Permission denied | Run PowerShell as Administrator or use `Set-ExecutionPolicy RemoteSigned` |
| Module not found | Ensure venv is activated: `.venv\Scripts\activate` |
| Wrong Python version | Specify Python explicitly: `py -3.14 -m venv .venv` or higher |

## Credential Configuration

You have two options for configuring credentials:

### Option 1: Environment Variables (Recommended for Production)

Environment variables take precedence over configuration files. This is the recommended approach for:
- CI/CD pipelines
- Docker containers
- Production deployments
- Shared development environments

Create a `.env` file in the project root (or set environment variables directly):

```bash
# OAuth Server-to-Server Authentication (Required)
ORG_ID=your_org_id@AdobeOrg
CLIENT_ID=your_client_id
SECRET=your_client_secret
SCOPES=openid, AdobeID, additional_info.projectedProductContext

# Optional
# SANDBOX=your_sandbox_name
```

To enable `.env` file loading, install the optional dependency:

```bash
uv add python-dotenv
# or
pip install python-dotenv
```

See `.env.example` for a complete template.

### Option 2: Configuration File

Create a `config.json` file in the project root directory:

```bash
# Copy the example template
cp config.json.example config.json

# Or generate a sample config
uv run cja_auto_sdr --sample-config
```

Then edit with your credentials:

```json
{
  "org_id": "your_org_id@AdobeOrg",
  "client_id": "your_client_id",
  "secret": "your_client_secret",
  "scopes": "openid, AdobeID, additional_info.projectedProductContext"
}
```

### Configuration Fields

| Field | Description | Required |
|-------|-------------|----------|
| `org_id` | Adobe Organization ID (from Developer Console) | Yes |
| `client_id` | Client ID from your integration | Yes |
| `secret` | Client Secret from your integration | Yes |
| `scopes` | OAuth scopes | Recommended |
| `sandbox` | Sandbox name (optional) | No |

## Project Structure

```
cja_auto_sdr/
├── .venv/                    # Virtual environment (created by uv)
├── logs/                     # Log files (created automatically)
├── docs/                     # Documentation
├── tests/                    # Test suite
├── pyproject.toml            # Project configuration
├── uv.lock                   # Dependency lock file
├── config.json             # Your CJA credentials (DO NOT COMMIT)
├── .env                      # Environment variables (DO NOT COMMIT)
├── cja_sdr_generator.py      # Main script
└── README.md
```

## Security Best Practices

### Files to Never Commit

Add to your `.gitignore`:

```gitignore
# Credentials
config.json
.env

# Generated files
.venv/
logs/
*.xlsx
```

### Credential Security

- Never commit `config.json` or `.env` to version control
- Use service accounts for automated runs
- Rotate credentials periodically
- Restrict access to sensitive data views

## Dependencies

All dependencies are managed through `pyproject.toml`:

```toml
[project]
name = "cja_auto_sdr"
version = "3.0.11"
requires-python = ">=3.14"
dependencies = [
    "cjapy>=0.2.4.post2",
    "numpy>=2.2.0,!=2.4.0",
    "pandas>=2.3.3",
    "xlsxwriter>=3.2.9",
    "tqdm>=4.66.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.3.4",
]
env = [
    "python-dotenv>=1.0.0",
]
```

### Core Dependencies

| Package | Purpose |
|---------|---------|
| `cjapy` | CJA API wrapper |
| `pandas` | Data manipulation |
| `xlsxwriter` | Excel generation |
| `tqdm` | Progress bars |

## Verifying Installation

### Check Python Version

```bash
python3 --version  # Should be 3.14 or higher
```

### Check uv Installation

```bash
uv --version
```

### Verify Dependencies

```bash
uv pip list
# Should show cjapy, pandas, xlsxwriter, tqdm
```

### Validate Configuration

```bash
# Test config and API connectivity (no data view required)
uv run cja_auto_sdr --validate-config

# Or dry-run with a specific data view
uv run cja_auto_sdr dv_12345 --dry-run
```

### List Available Data Views

```bash
uv run cja_auto_sdr --list-dataviews
```

## Updating Dependencies

```bash
# Update all dependencies
uv sync --upgrade

# Update specific package
uv add --upgrade cjapy

# Reinstall everything
uv sync --reinstall
```

## Next Steps

- [CLI Reference](CLI_REFERENCE.md) - Learn all command-line options
- [Troubleshooting](TROUBLESHOOTING.md) - If you encounter issues
