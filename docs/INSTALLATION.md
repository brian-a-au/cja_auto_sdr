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

### Option 1: Clone/Download (Recommended)

```bash
# Navigate to project directory
cd cja_auto_sdr

# Create virtual environment and install dependencies
uv sync

# Activate the virtual environment (optional - uv run handles this)
# macOS/Linux:
source .venv/bin/activate
# Windows:
.venv\Scripts\activate
```

The `uv sync` command will:
- Create a virtual environment in `.venv/`
- Install all dependencies from `pyproject.toml`
- Generate a `uv.lock` file for reproducible builds

### Option 2: Start from Scratch

```bash
# Create new project
uv init cja_auto_sdr
cd cja_auto_sdr

# Add dependencies
uv add cjapy>=0.2.4.post2
uv add pandas>=2.3.3
uv add xlsxwriter>=3.2.9
uv add tqdm>=4.66.0

# Copy script and config files into the project
```

### Option 3: Legacy pip Installation

```bash
# Create virtual environment
python -m venv .venv

# Activate
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate     # Windows

# Install dependencies
pip install cjapy>=0.2.4.post2 pandas>=2.3.3 xlsxwriter>=3.2.9 tqdm>=4.66.0
```

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

Create a `myconfig.json` file in the project root directory:

```json
{
  "org_id": "your_org_id@AdobeOrg",
  "client_id": "your_client_id",
  "secret": "your_client_secret",
  "scopes": "openid, AdobeID, additional_info.projectedProductContext"
}
```

### Generate Sample Config

```bash
uv run python cja_sdr_generator.py --sample-config
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
├── myconfig.json             # Your CJA credentials (DO NOT COMMIT)
├── .env                      # Environment variables (DO NOT COMMIT)
├── cja_sdr_generator.py      # Main script
└── README.md
```

## Security Best Practices

### Files to Never Commit

Add to your `.gitignore`:

```gitignore
# Credentials
myconfig.json
.env

# Generated files
.venv/
logs/
*.xlsx
```

### Credential Security

- Never commit `myconfig.json` or `.env` to version control
- Use service accounts for automated runs
- Rotate credentials periodically
- Restrict access to sensitive data views

## Dependencies

All dependencies are managed through `pyproject.toml`:

```toml
[project]
name = "cja_auto_sdr"
version = "3.0.8"
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
python --version  # Should be 3.14+
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
# Dry-run to test config and connectivity
uv run python cja_sdr_generator.py dv_test --dry-run
```

### List Available Data Views

```bash
uv run python cja_sdr_generator.py --list-dataviews
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
