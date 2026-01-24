# Configuration Guide

Complete reference for configuring CJA SDR Generator authentication and settings.

---

## Table of Contents

1. [Quick Start](#quick-start)
2. [Configuration Methods](#configuration-methods)
3. [Profile Management](#profile-management) ← **Recommended for multiple organizations**
4. [config.json Reference](#configjson-reference)
5. [Environment Variables Reference](#environment-variables-reference)
6. [OAuth Scopes Explained](#oauth-scopes-explained)
7. [Validation Rules](#validation-rules)
8. [Configuration Precedence](#configuration-precedence)
9. [Multi-Environment Setup](#multi-environment-setup)
10. [Security Best Practices](#security-best-practices)
11. [Troubleshooting](#troubleshooting)

---

## Quick Start

Choose your configuration method:

```
┌─────────────────────────────────────────────────────────────────┐
│                   Which method should I use?                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Multiple organizations? (agencies, multi-client, regional)     │
│  ────────────────────────────────────────────────────────────   │
│  → Use PROFILES (recommended) - see Profile Management section  │
│    $ cja_auto_sdr --profile client-a --list-dataviews           │
│                                                                  │
│  Single organization, local development?                        │
│  ─────────────────────────────────────────                      │
│  → Use config.json (simpler setup)                              │
│                                                                  │
│  CI/CD, Docker, shared environments?                            │
│  ────────────────────────────────────                           │
│  → Use environment variables (more secure)                      │
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
| **Scopes** | Developer Console → Project → Credentials → Scopes (copy from your project) |

---

## Configuration Methods

There are three main ways to configure credentials:

| Method | Best For | Multiple Orgs |
|--------|----------|---------------|
| **Profiles** | Agencies, consultants, multi-org enterprises | **Recommended** |
| **config.json** | Single org, simple local development | No |
| **Environment Variables** | CI/CD, containers, automation | Via separate configs |

### Method 1: Profiles (Recommended for Multiple Organizations)

If you work with multiple Adobe Organizations, profiles are the recommended approach. Each profile is a named directory under `~/.cja/orgs/` containing credentials that can be activated via CLI or environment variable.

```bash
# Create a profile interactively
cja_auto_sdr --profile-add client-a

# Use a profile
cja_auto_sdr --profile client-a --list-dataviews

# Or set as default
export CJA_PROFILE=client-a
cja_auto_sdr --list-dataviews
```

See [Profile Management](#profile-management) for full documentation.

### Method 2: config.json File

Create a `config.json` file in your working directory:

```json
{
  "org_id": "ABC123DEF456@AdobeOrg",
  "client_id": "1234567890abcdef1234567890abcdef",
  "secret": "p8e-XXX...",
  "scopes": "your_scopes_from_developer_console"
}
```

**Pros:**
- Simple to set up
- Easy to version control (with `.gitignore`)
- Portable across terminals

**Cons:**
- Risk of accidental commit to version control
- Single environment only

### Method 3: Environment Variables

Set variables in your shell or `.env` file:

```bash
export ORG_ID="ABC123DEF456@AdobeOrg"
export CLIENT_ID="1234567890abcdef1234567890abcdef"
export SECRET="p8e-XXX..."
export SCOPES="your_scopes_from_developer_console"
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
SCOPES=your_scopes_from_developer_console
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
  "scopes": "your_scopes_from_developer_console"
}
```

### Field Details

| Field | Required | Type | Description |
|-------|----------|------|-------------|
| `org_id` | **Yes** | string | Adobe Organization ID. Must end with `@AdobeOrg`. |
| `client_id` | **Yes** | string | OAuth Client ID from Developer Console. Typically 32 characters. |
| `secret` | **Yes** | string | Client Secret from Developer Console. Keep confidential. |
| `scopes` | **Yes**† | string | OAuth scopes for API access. Comma or space-separated. |
| `sandbox` | No | string | Reserved for future use. Not currently utilized by cjapy or the CJA API. |

> †**Note on scopes:** While the config validator only warns if scopes are missing, OAuth authentication **will fail** without proper scopes. Always include them.

### Example with All Fields

```json
{
  "org_id": "ABC123DEF456789@AdobeOrg",
  "client_id": "1234567890abcdef1234567890abcdef",
  "secret": "p8e-XXXXXXXXXXXXXXXXXXXXXXXXXXXX",
  "scopes": "your_scopes_from_developer_console"
}
```

> **Note:** The `sandbox` field is reserved for future use. The CJA API (`cja.adobe.io`) does not use the `x-sandbox-name` header that other AEP APIs use—CJA resources are scoped at the organization level.

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
export SCOPES="your_scopes_from_developer_console"
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
$env:SCOPES = "your_scopes_from_developer_console"
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
SCOPES=your_scopes_from_developer_console

# Optional
# SANDBOX=dev
# LOG_LEVEL=DEBUG
```

**Important:** The `.env` file requires `python-dotenv` to be installed:
```bash
uv add python-dotenv
```

---

## OAuth Scopes

OAuth scopes control which APIs your integration can access. The required scopes vary based on your Adobe Developer Console project configuration.

**To find your scopes:**

1. Go to [Adobe Developer Console](https://developer.adobe.com/console/)
2. Open your project
3. Navigate to **Credentials** → **OAuth Server-to-Server**
4. Copy the scopes listed under **Scopes**

For more information on OAuth authentication, see the [Adobe Developer Authentication Guide](https://developer.adobe.com/developer-console/docs/guides/authentication/).

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
| Not empty | Must contain scopes from your Adobe Developer Console project |
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

## Profile Management

> **This is the recommended approach for managing multiple Adobe Organizations.** Whether you're an agency managing client accounts, an enterprise with regional organizations, or a consultant working with multiple clients, profiles provide a clean, built-in solution.

Profiles provide a built-in way to manage credentials for multiple Adobe Organizations. Each profile is a named directory containing credentials that can be activated via CLI or environment variable.

### Profile Directory Structure

Profiles are stored in your **user home directory** (not the project directory):

```text
~/.cja/orgs/
├── client-a/
│   ├── config.json     # JSON credentials
│   └── .env            # ENV format (optional, overrides JSON)
├── client-b/
│   └── config.json
└── internal/
    └── .env
```

**Expanded paths by platform:**

| Platform | Path |
|----------|------|
| macOS | `/Users/username/.cja/orgs/` |
| Linux | `/home/username/.cja/orgs/` |
| Windows | `C:\Users\username\.cja\orgs\` |

> **Why the home directory?** Credentials are user-specific (not project-specific), can be shared across multiple projects, and storing them outside project directories prevents accidental commits to version control.

**Custom location:** Set `CJA_HOME` to override the default `~/.cja` directory:

```bash
export CJA_HOME=/custom/path
# Profiles will be at: /custom/path/orgs/
```

### Creating Profiles

**Interactive creation:**

```bash
cja_auto_sdr --profile-add client-a
# Prompts for: Organization ID, Client ID, Secret, Scopes
```

**Manual creation:**

```bash
mkdir -p ~/.cja/orgs/client-a
cat > ~/.cja/orgs/client-a/config.json << 'EOF'
{
  "org_id": "YOUR_ORG_ID@AdobeOrg",
  "client_id": "YOUR_CLIENT_ID",
  "secret": "YOUR_SECRET",
  "scopes": "your_scopes_from_developer_console"
}
EOF
chmod 600 ~/.cja/orgs/client-a/config.json
```

### Using Profiles

**CLI flag (highest priority):**

```bash
cja_auto_sdr --profile client-a --list-dataviews
cja_auto_sdr -p client-a "My Data View" --format excel
```

**Environment variable:**

```bash
export CJA_PROFILE=client-a
cja_auto_sdr --list-dataviews
```

**In batch scripts:**

```bash
CJA_PROFILE=client-a cja_auto_sdr --list-dataviews
CJA_PROFILE=client-b cja_auto_sdr --list-dataviews
```

### Managing Profiles

| Command | Description |
|---------|-------------|
| `--profile-list` | List all available profiles |
| `--profile-add NAME` | Create a new profile interactively |
| `--profile-show NAME` | Show profile configuration (secrets masked) |
| `--profile-test NAME` | Test profile credentials and API connectivity |

**Examples:**

```bash
# List all profiles
cja_auto_sdr --profile-list

# Show profile details (secrets masked)
cja_auto_sdr --profile-show client-a

# Test profile connectivity
cja_auto_sdr --profile-test client-a
```

### Profile Credential Precedence

Within a profile, credentials are loaded in this order:

1. `.env` file values (if present)
2. `config.json` values (base)

The `.env` file overrides any matching values from `config.json`, allowing you to:
- Store base configuration in `config.json`
- Override specific values via `.env` for environment-specific settings

### Environment Variables for Profiles

| Variable | Description |
|----------|-------------|
| `CJA_PROFILE` | Default profile (overridden by `--profile`) |
| `CJA_HOME` | Override default `~/.cja` directory |

### Profile Naming Rules

Profile names must:
- Start with a letter or number
- Contain only letters, numbers, dashes (`-`), and underscores (`_`)
- Be 64 characters or less

**Valid names:** `client-a`, `prod_org`, `acme2024`, `my_client`
**Invalid names:** `-invalid`, `has spaces`, `special@chars`

### Updated Configuration Precedence

When profiles are enabled, the complete credential loading order is:

```
┌─────────────────────────────────────────────────────────────────┐
│                    Configuration Precedence                      │
│                    (highest to lowest)                          │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Profile credentials (if --profile or CJA_PROFILE)           │
│     ↓ (if not set, falls back to...)                            │
│                                                                  │
│  2. Environment Variables (ORG_ID, CLIENT_ID, etc.)             │
│     ↓ (if not set, falls back to...)                            │
│                                                                  │
│  3. .env file (loaded via python-dotenv)                        │
│     ↓ (if not set, falls back to...)                            │
│                                                                  │
│  4. config.json in current directory                            │
│     ↓ (if not set, falls back to...)                            │
│                                                                  │
│  5. --config-file PATH (explicit path)                          │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Backwards Compatibility

The profile feature is fully backwards compatible:
- Existing `config.json` files work when no profile is specified
- Existing environment variables work when no profile is active
- The `--config-file` flag still works as a fallback

---

## Multi-Environment Setup

This section covers managing configurations for multiple Adobe Organizations and deployment scenarios.

> **Recommended Approach:** For most multi-organization use cases, use the built-in **Profile Management** feature described above. Profiles provide a clean, built-in way to manage and switch between organizations without manual shell scripts or symlinks.
>
> The techniques below are provided for advanced scenarios, legacy setups, or cases where profiles don't fit your workflow.

### Understanding Adobe CJA Architecture

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                     Adobe CJA Organization Structure                        │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Adobe Organization (@AdobeOrg)                                             │
│  ──────────────────────────────                                             │
│  The top-level container for all Adobe resources. Each org has its own:    │
│  • Users and permissions                                                    │
│  • Product licenses and entitlements                                        │
│  • CJA connections, data views, and projects                               │
│  • API credentials (Developer Console projects)                             │
│                                                                              │
│  Key Points:                                                                │
│  • API credential access is controlled by assigned product profiles        │
│  • Multiple data views can exist within a single org                       │
│  • Product profiles can restrict which data views a credential can access  │
│  • For complete data isolation, separate Adobe Organizations are used      │
│                                                                              │
│  Note: Unlike some AEP APIs, the CJA API (cja.adobe.io) does not use the  │
│  x-sandbox-name header. CJA resources are scoped to the organization.      │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Common Multi-Org Scenarios

| Scenario | Description | Recommended Solution |
|----------|-------------|---------------------|
| **Agency Model** | Managing multiple client organizations, each with separate credentials | Use **Profiles** |
| **Regional Separation** | Enterprise with distinct orgs per region (NA, EMEA, APAC) for data residency | Use **Profiles** |
| **Business Unit Isolation** | Separate orgs for divisions, brands, or subsidiaries | Use **Profiles** |
| **Dev/Staging/Prod Separation** | Separate orgs provisioned for each environment | Use **Profiles** |

**Quick start for these scenarios:**

```bash
# Create profiles for each organization
cja_auto_sdr --profile-add client-a
cja_auto_sdr --profile-add client-b
cja_auto_sdr --profile-add internal

# Switch between organizations easily
cja_auto_sdr --profile client-a --list-dataviews
cja_auto_sdr --profile client-b --list-dataviews

# Or set a default
export CJA_PROFILE=client-a
```

> **Note:** The CJA API does not currently support the AEP sandbox model (`x-sandbox-name` header). All CJA resources (connections, data views, projects) are scoped to the organization level. For environment or data isolation, you need separate Adobe Organizations with distinct API credentials. The `sandbox` field in this tool's configuration is reserved for potential future use but is not currently utilized.

---

### CI/CD Pipeline Configuration

For CI/CD pipelines, use environment variables to pass credentials securely:

**GitHub Actions example:**

```yaml
name: Generate SDR Reports

on:
  schedule:
    - cron: '0 6 * * 1'  # Weekly on Monday
  workflow_dispatch:

jobs:
  generate-sdr:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: '3.14'
      - run: pip install uv && uv sync
      - name: Generate SDR
        env:
          ORG_ID: ${{ secrets.ADOBE_ORG_ID }}
          CLIENT_ID: ${{ secrets.ADOBE_CLIENT_ID }}
          SECRET: ${{ secrets.ADOBE_SECRET }}
          SCOPES: ${{ secrets.ADOBE_SCOPES }}
        run: cja_auto_sdr "Production Data View" --output-dir ./reports --format excel
      - uses: actions/upload-artifact@v4
        with:
          name: sdr-reports
          path: ./reports/
```

**Docker example:**

```bash
# Pass environment variables at runtime
docker run -e ORG_ID -e CLIENT_ID -e SECRET -e SCOPES \
  cja-sdr-generator "My Data View" --format excel

# Or use an env file
docker run --env-file .env.production \
  cja-sdr-generator "My Data View" --format excel
```

---

## Security Best Practices

### Do

- **Use environment variables** for production and CI/CD
- **Add config.json to .gitignore** (already done by default)
- **Use .env files** for local development (already gitignored)
- **Rotate secrets** periodically in Adobe Developer Console
- **Limit API scope** to only what's needed

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

```text
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

```text
Error: ORG_ID 'ABC123' is missing '@AdobeOrg' suffix
```

**Solution:** Add the `@AdobeOrg` suffix:

```json
{
  "org_id": "ABC123@AdobeOrg"
}
```

#### "CLIENT_ID appears too short"

```text
Warning: CLIENT_ID 'abc123...' appears too short
```

**Solution:** Verify you copied the complete Client ID from Adobe Developer Console. It should be 32 characters.

#### "Missing OAuth scopes"

```text
Warning: OAuth scopes not configured
```

**Solution:** Copy scopes from your Adobe Developer Console project:

```json
{
  "scopes": "your_scopes_from_developer_console"
}
```

#### "Invalid JSON"

```text
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

```text
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
  "scopes": "your_scopes_from_developer_console"
}
```

### Minimum Environment Variables

```bash
export ORG_ID="YOUR_ORG_ID@AdobeOrg"
export CLIENT_ID="YOUR_CLIENT_ID"
export SECRET="YOUR_SECRET"
export SCOPES="your_scopes_from_developer_console"
```

### Validation Checklist

- [ ] `org_id` ends with `@AdobeOrg`
- [ ] `client_id` is 32 characters
- [ ] `secret` is not empty
- [ ] `scopes` copied from Adobe Developer Console
- [ ] JSON syntax is valid (no trailing commas)
- [ ] File is not committed to version control

---

## See Also

- [Quick Start Guide](QUICKSTART_GUIDE.md) - First-time setup walkthrough
- [Installation Guide](INSTALLATION.md) - Installation methods
- [CLI Reference](CLI_REFERENCE.md) - All command-line options
- [Troubleshooting Guide](TROUBLESHOOTING.md) - Error messages and solutions
