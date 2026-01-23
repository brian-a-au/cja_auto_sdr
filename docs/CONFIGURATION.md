# Configuration Guide

Complete reference for configuring CJA SDR Generator authentication and settings.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Configuration Methods](#configuration-methods)
3. [config.json Reference](#configjson-reference)
4. [Environment Variables Reference](#environment-variables-reference)
5. [OAuth Scopes Explained](#oauth-scopes-explained)
6. [Validation Rules](#validation-rules)
7. [Configuration Precedence](#configuration-precedence)
8. [Multi-Environment Setup](#multi-environment-setup)
9. [Security Best Practices](#security-best-practices)
10. [Troubleshooting](#troubleshooting)

---

## Quick Start

Choose your configuration method:

```
┌─────────────────────────────────────────────────────────────────┐
│                   Which method should I use?                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Local development, single user?                                 │
│  ────────────────────────────────                               │
│  → Use config.json (simpler setup)                              │
│                                                                  │
│  CI/CD, Docker, shared environments?                            │
│  ────────────────────────────────────                           │
│  → Use environment variables (more secure)                      │
│                                                                  │
│  Both configured?                                                │
│  ────────────────                                               │
│  → Environment variables take precedence                        │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Minimum Required Configuration

You need these four values for OAuth authentication:

| Field | Where to Find It |
|-------|------------------|
| **Organization ID** | Developer Console → Project → Credentials → Organization ID |
| **Client ID** | Developer Console → Project → Credentials → Client ID |
| **Client Secret** | Developer Console → Project → Credentials → Client Secret |
| **Scopes** | Use: `openid, AdobeID, additional_info.projectedProductContext` |

---

## Configuration Methods

### Method 1: config.json File

Create a `config.json` file in your working directory:

```json
{
  "org_id": "ABC123DEF456@AdobeOrg",
  "client_id": "1234567890abcdef1234567890abcdef",
  "secret": "p8e-XXX...",
  "scopes": "openid, AdobeID, additional_info.projectedProductContext"
}
```

**Pros:**
- Simple to set up
- Easy to version control (with `.gitignore`)
- Portable across terminals

**Cons:**
- Risk of accidental commit to version control
- Single environment only

### Method 2: Environment Variables

Set variables in your shell or `.env` file:

```bash
export ORG_ID="ABC123DEF456@AdobeOrg"
export CLIENT_ID="1234567890abcdef1234567890abcdef"
export SECRET="p8e-XXX..."
export SCOPES="openid, AdobeID, additional_info.projectedProductContext"
```

Or create a `.env` file (requires `python-dotenv`):

```bash
# Install dotenv support
uv add python-dotenv
# or: pip install python-dotenv
```

```bash
# .env file
ORG_ID=ABC123DEF456@AdobeOrg
CLIENT_ID=1234567890abcdef1234567890abcdef
SECRET=p8e-XXX...
SCOPES=openid, AdobeID, additional_info.projectedProductContext
```

**Pros:**
- Never accidentally committed (`.env` is gitignored)
- Easy to switch between environments
- Standard practice for CI/CD
- Secrets stay out of files

**Cons:**
- Slightly more setup
- Terminal-session specific (unless using `.env`)

---

## config.json Reference

### Complete Field Reference

```json
{
  "org_id": "ABC123DEF456@AdobeOrg",
  "client_id": "1234567890abcdef1234567890abcdef",
  "secret": "p8e-XXX...",
  "scopes": "openid, AdobeID, additional_info.projectedProductContext",
  "sandbox": "prod"
}
```

### Field Details

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `org_id` | **Yes** | string | Adobe Organization ID. Must end with `@AdobeOrg`. |
| `client_id` | **Yes** | string | OAuth Client ID from Developer Console. Typically 32 characters. |
| `secret` | **Yes** | string | Client Secret from Developer Console. Keep confidential. |
| `scopes` | **Yes**† | string | OAuth scopes for API access. Comma or space-separated. |
| `sandbox` | No | string | Sandbox name for non-production environments. |

> †**Note on scopes:** While the config validator only warns if scopes are missing, OAuth authentication **will fail** without proper scopes. Always include them.

### Example with All Fields

```json
{
  "org_id": "ABC123DEF456789@AdobeOrg",
  "client_id": "1234567890abcdef1234567890abcdef",
  "secret": "p8e-XXXXXXXXXXXXXXXXXXXXXXXXXXXX",
  "scopes": "openid, AdobeID, additional_info.projectedProductContext",
  "sandbox": "dev"
}
```

### Generate a Template

Generate a sample config file:

```bash
cja_auto_sdr --sample-config
# Creates: config.sample.json
```

---

## Environment Variables Reference

### Variable Mapping

| Environment Variable | Maps To | Required |
|---------------------|---------|----------|
| `ORG_ID` | `org_id` | **Yes** |
| `CLIENT_ID` | `client_id` | **Yes** |
| `SECRET` | `secret` | **Yes** |
| `SCOPES` | `scopes` | **Yes**† |
| `SANDBOX` | `sandbox` | No |

> †**Note on scopes:** OAuth authentication requires proper scopes. See [OAuth Scopes Explained](#oauth-scopes-explained).

### Additional Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `LOG_LEVEL` | Logging verbosity: DEBUG, INFO, WARNING, ERROR | INFO |
| `OUTPUT_DIR` | Default output directory for generated files | Current directory |

### Setting Environment Variables

**macOS/Linux (current session):**
```bash
export ORG_ID="ABC123DEF456@AdobeOrg"
export CLIENT_ID="your_client_id"
export SECRET="your_secret"
export SCOPES="openid, AdobeID, additional_info.projectedProductContext"
```

**macOS/Linux (persistent - add to ~/.bashrc or ~/.zshrc):**
```bash
echo 'export ORG_ID="ABC123DEF456@AdobeOrg"' >> ~/.zshrc
source ~/.zshrc
```

**Windows PowerShell (current session):**
```powershell
$env:ORG_ID = "ABC123DEF456@AdobeOrg"
$env:CLIENT_ID = "your_client_id"
$env:SECRET = "your_secret"
$env:SCOPES = "openid, AdobeID, additional_info.projectedProductContext"
```

**Windows Command Prompt:**
```cmd
set ORG_ID=ABC123DEF456@AdobeOrg
set CLIENT_ID=your_client_id
set SECRET=your_secret
```

### .env File Format

Create a `.env` file in your project directory:

```bash
# Adobe OAuth Server-to-Server Authentication
ORG_ID=ABC123DEF456@AdobeOrg
CLIENT_ID=1234567890abcdef1234567890abcdef
SECRET=p8e-XXXXXXXXXXXXXXXXXXXXXXXXXXXX
SCOPES=openid, AdobeID, additional_info.projectedProductContext

# Optional
# SANDBOX=dev
# LOG_LEVEL=DEBUG
```

**Important:** The `.env` file requires `python-dotenv` to be installed:
```bash
uv add python-dotenv
```

---

## OAuth Scopes Explained

### Required Scopes

The CJA API requires these three OAuth scopes:

| Scope | Purpose |
|-------|---------|
| `openid` | OpenID Connect authentication. Required for OAuth flow. |
| `AdobeID` | Adobe Identity authentication. Validates your Adobe account. |
| `additional_info.projectedProductContext` | Access to product-specific APIs including CJA. |

### Recommended Scopes String

```
openid, AdobeID, additional_info.projectedProductContext
```

Both comma-separated and space-separated formats are accepted:
```
openid,AdobeID,additional_info.projectedProductContext
openid AdobeID additional_info.projectedProductContext
```

### What Happens Without Proper Scopes

| Missing Scope | Error |
|---------------|-------|
| `openid` | Authentication fails at token request |
| `AdobeID` | Identity verification fails |
| `additional_info.projectedProductContext` | API returns 403 Forbidden |

---

## Validation Rules

The tool validates your configuration before connecting to the API. Understanding these rules helps you fix issues quickly.

### org_id Validation

| Rule | Valid Example | Invalid Example |
|------|---------------|-----------------|
| Must end with `@AdobeOrg` | `ABC123@AdobeOrg` | `ABC123@adobe.com` |
| Cannot be empty before `@` | `ABC123@AdobeOrg` | `@AdobeOrg` |
| Case-sensitive suffix | `ABC123@AdobeOrg` | `ABC123@adobeorg` |

**Common Mistakes:**
```
# Wrong suffix
ABC123@adobe.com     → Should be: ABC123@AdobeOrg
ABC123@AdobeOrg.com  → Should be: ABC123@AdobeOrg

# Missing suffix
ABC123               → Should be: ABC123@AdobeOrg
```

### client_id Validation

| Rule | Description |
|------|-------------|
| Minimum length | Must be at least 16 characters |
| Typical format | 32 hexadecimal characters |

**Example:**
```
Valid:   1234567890abcdef1234567890abcdef (32 chars)
Invalid: abc123 (too short)
```

### secret Validation

| Rule | Description |
|------|-------------|
| Minimum length | Must be at least 16 characters |
| Cannot be empty | Must contain actual secret value |

### scopes Validation

| Rule | Description |
|------|-------------|
| Required scopes | Must include: `openid`, `AdobeID`, `additional_info.projectedProductContext` |
| Separator | Comma or space-separated |

### Validate Before Running

Test your configuration without making API calls:

```bash
# Validate config file
cja_auto_sdr --validate-config

# Validate with specific config file
cja_auto_sdr --config-file /path/to/config.json --validate-config

# Dry run (validates and shows what would happen)
cja_auto_sdr --dry-run
```

---

## Configuration Precedence

When both config.json and environment variables are present:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Configuration Precedence                      │
│                    (highest to lowest)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Environment Variables (ORG_ID, CLIENT_ID, etc.)             │
│     ↓ (if not set, falls back to...)                            │
│                                                                  │
│  2. .env file (loaded via python-dotenv)                        │
│     ↓ (if not set, falls back to...)                            │
│                                                                  │
│  3. config.json in current directory                            │
│     ↓ (if not set, falls back to...)                            │
│                                                                  │
│  4. --config-file PATH (explicit path)                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**Practical Example:**

```bash
# config.json has ORG_ID=ABC@AdobeOrg
# Environment has ORG_ID=XYZ@AdobeOrg

cja_auto_sdr --list-dataviews
# Uses: XYZ@AdobeOrg (environment wins)
```

### Checking Active Configuration

See which configuration source is being used:

```bash
cja_auto_sdr --list-dataviews --verbose
# Output shows: "Using credentials from environment variables" or
#              "Using credentials from config.json"
```

---

## Multi-Environment Setup

### Development / Staging / Production

Create separate configuration files:

```
project/
├── config.json           # Local development (gitignored)
├── config.dev.json       # Development environment
├── config.staging.json   # Staging environment
└── config.prod.json      # Production environment
```

Use with `--config-file`:

```bash
# Development
cja_auto_sdr --config-file config.dev.json --list-dataviews

# Staging
cja_auto_sdr --config-file config.staging.json --list-dataviews

# Production
cja_auto_sdr --config-file config.prod.json --list-dataviews
```

### CI/CD Pipeline Configuration

**GitHub Actions:**
```yaml
env:
  ORG_ID: ${{ secrets.ADOBE_ORG_ID }}
  CLIENT_ID: ${{ secrets.ADOBE_CLIENT_ID }}
  SECRET: ${{ secrets.ADOBE_SECRET }}
  SCOPES: "openid, AdobeID, additional_info.projectedProductContext"

steps:
  - name: Generate SDR
    run: cja_auto_sdr "My Data View" --output-dir ./reports
```

**GitLab CI:**
```yaml
variables:
  ORG_ID: $ADOBE_ORG_ID
  CLIENT_ID: $ADOBE_CLIENT_ID
  SECRET: $ADOBE_SECRET
  SCOPES: "openid, AdobeID, additional_info.projectedProductContext"

generate_sdr:
  script:
    - cja_auto_sdr "My Data View" --output-dir ./reports
```

**Docker:**
```dockerfile
# Pass at runtime
docker run -e ORG_ID -e CLIENT_ID -e SECRET -e SCOPES cja-sdr-generator
```

```bash
# Or use env file
docker run --env-file .env cja-sdr-generator
```

### Shell Profile Setup

Add to `~/.bashrc`, `~/.zshrc`, or equivalent:

```bash
# CJA SDR Generator - Development
alias cja-dev='ORG_ID="dev-org@AdobeOrg" CLIENT_ID="dev-id" SECRET="dev-secret" cja_auto_sdr'

# CJA SDR Generator - Production
alias cja-prod='ORG_ID="prod-org@AdobeOrg" CLIENT_ID="prod-id" SECRET="prod-secret" cja_auto_sdr'
```

Usage:
```bash
cja-dev --list-dataviews    # Uses dev credentials
cja-prod --list-dataviews   # Uses prod credentials
```

---

## Security Best Practices

### Do

- **Use environment variables** for production and CI/CD
- **Add config.json to .gitignore** (already done by default)
- **Use .env files** for local development (already gitignored)
- **Rotate secrets** periodically in Adobe Developer Console
- **Limit API scope** to only what's needed
- **Use separate credentials** for dev/staging/prod

### Don't

- **Never commit secrets** to version control
- **Never share config.json** files via email/chat
- **Never log secrets** (the tool masks them automatically)
- **Never use production credentials** for development
- **Never store secrets** in command history

### Checking for Exposed Secrets

Before committing, verify no secrets are staged:

```bash
# Check if config.json is tracked
git status | grep config.json

# Search for potential secrets in staged files
git diff --cached | grep -i "secret\|client_id\|org_id"
```

### Revoking Compromised Credentials

If credentials are exposed:

1. Go to [Adobe Developer Console](https://developer.adobe.com/console)
2. Open your project
3. Navigate to Credentials
4. Generate new Client Secret (old one becomes invalid immediately)
5. Update your config.json or environment variables

---

## Troubleshooting

### Common Errors and Solutions

#### "Config file not found"

```
Error: Config file not found: config.json
```

**Solutions:**
1. Create config.json in your current directory
2. Use `--config-file` to specify the path
3. Set environment variables instead

```bash
# Option 1: Create from template
cp config.json.example config.json
# Edit config.json with your credentials

# Option 2: Specify path
cja_auto_sdr --config-file /path/to/config.json --list-dataviews

# Option 3: Use environment variables
export ORG_ID="your_org@AdobeOrg"
export CLIENT_ID="your_client_id"
export SECRET="your_secret"
```

#### "ORG_ID is missing '@AdobeOrg' suffix"

```
Error: ORG_ID 'ABC123' is missing '@AdobeOrg' suffix
```

**Solution:** Add the `@AdobeOrg` suffix:
```json
{
  "org_id": "ABC123@AdobeOrg"
}
```

#### "CLIENT_ID appears too short"

```
Warning: CLIENT_ID 'abc123...' appears too short
```

**Solution:** Verify you copied the complete Client ID from Adobe Developer Console. It should be 32 characters.

#### "Missing required OAuth scopes"

```
Warning: Missing required OAuth scopes: AdobeID
```

**Solution:** Add all required scopes:
```json
{
  "scopes": "openid, AdobeID, additional_info.projectedProductContext"
}
```

#### "Invalid JSON"

```
Error: Invalid JSON syntax at line 3
```

**Common causes:**
- Missing comma between fields
- Trailing comma after last field
- Unquoted strings
- Single quotes instead of double quotes

**Validate your JSON:**
```bash
# macOS/Linux
python3 -c "import json; json.load(open('config.json'))"

# Or use an online validator
```

#### "Authentication failed" (401/403 errors)

```
Error: API authentication failed (401 Unauthorized)
```

**Solutions:**
1. Verify credentials are correct (no extra spaces)
2. Check that Client Secret hasn't expired
3. Verify OAuth scopes are set correctly
4. Ensure the API project has CJA permissions

```bash
# Test authentication
cja_auto_sdr --validate-config
cja_auto_sdr --list-dataviews
```

### Validation Commands

```bash
# Validate configuration only
cja_auto_sdr --validate-config

# Dry run (validate + simulate)
cja_auto_sdr --dry-run

# Verbose mode (see credential source)
cja_auto_sdr --list-dataviews --verbose

# Test connection
cja_auto_sdr --list-dataviews
```

### Debug Logging

Enable debug logging to see detailed configuration loading:

```bash
# Via environment variable
LOG_LEVEL=DEBUG cja_auto_sdr --list-dataviews

# Via command line
cja_auto_sdr --list-dataviews --log-level DEBUG
```

---

## Quick Reference

### Minimum config.json
```json
{
  "org_id": "YOUR_ORG_ID@AdobeOrg",
  "client_id": "YOUR_CLIENT_ID",
  "secret": "YOUR_SECRET",
  "scopes": "openid, AdobeID, additional_info.projectedProductContext"
}
```

### Minimum Environment Variables
```bash
export ORG_ID="YOUR_ORG_ID@AdobeOrg"
export CLIENT_ID="YOUR_CLIENT_ID"
export SECRET="YOUR_SECRET"
export SCOPES="openid, AdobeID, additional_info.projectedProductContext"
```

### Validation Checklist

- [ ] `org_id` ends with `@AdobeOrg`
- [ ] `client_id` is 32 characters
- [ ] `secret` is not empty
- [ ] `scopes` includes all three required scopes
- [ ] JSON syntax is valid (no trailing commas)
- [ ] File is not committed to version control

---

## See Also

- [Quick Start Guide](QUICKSTART_GUIDE.md) - First-time setup walkthrough
- [Installation Guide](INSTALLATION.md) - Installation methods
- [CLI Reference](CLI_REFERENCE.md) - All command-line options
- [Troubleshooting Guide](TROUBLESHOOTING.md) - Error messages and solutions
