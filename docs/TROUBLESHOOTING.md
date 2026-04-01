# Troubleshooting Guide

Comprehensive solutions for issues with the CJA SDR Generator.

## Table of Contents

- [Quick Diagnostics](#quick-diagnostics)
- [Exit Codes Reference](#exit-codes-reference)
- [Configuration Errors](#configuration-errors)
- [Authentication & Connection Errors](#authentication--connection-errors)
- [API Permission Errors](#api-permission-errors)
- [Data View Errors](#data-view-errors)
- [Diff Comparison & Snapshot Errors](#diff-comparison--snapshot-errors)
- [Profile Errors](#profile-errors)
- [API & Network Errors](#api--network-errors)
- [Retry Mechanism & Rate Limiting](#retry-mechanism--rate-limiting)
- [Data Quality Issues](#data-quality-issues)
- [Output & File Errors](#output--file-errors)
- [Batch Processing Issues](#batch-processing-issues)
- [Validation Cache Issues](#validation-cache-issues)
- [Inventory Feature Issues](#inventory-feature-issues)
- [Git & Repository Issues](#git--repository-issues)
- [Performance Issues](#performance-issues)
- [Dependency Issues](#dependency-issues)
- [Debug Mode & Logging](#debug-mode--logging)
- [Common Error Messages Reference](#common-error-messages-reference)
- [Getting Help](#getting-help)

---

## Quick Diagnostics

Run this script to gather system information:

```bash
#!/bin/bash
echo "=== System Information ==="
python3 --version
uv --version
echo ""
echo "=== Project Dependencies ==="
uv pip list | grep -E "cjapy|pandas|xlsxwriter"
echo ""
echo "=== Configuration Check ==="
if [ -f config.json ]; then
    echo "config.json exists"
    python -c "import json; json.load(open('config.json')); print('JSON syntax: valid')" 2>&1 || echo "JSON syntax: INVALID"
else
    echo "config.json NOT FOUND"
fi
echo ""
echo "=== Environment Variables ==="
[ -n "$ORG_ID" ] && echo "ORG_ID: set" || echo "ORG_ID: not set"
[ -n "$CLIENT_ID" ] && echo "CLIENT_ID: set" || echo "CLIENT_ID: not set"
[ -n "$SECRET" ] && echo "SECRET: set" || echo "SECRET: not set"
[ -n "$SCOPES" ] && echo "SCOPES: set" || echo "SCOPES: not set"
echo ""
echo "=== Recent Logs ==="
ls -lh logs/ 2>/dev/null | tail -5 || echo "No logs directory"
```

Save as `diagnose.sh` and run:
```bash
chmod +x diagnose.sh
./diagnose.sh > diagnostic_report.txt
```

> **Windows Users:** See the [Windows Diagnostic Script](#windows-diagnostic-script) section for a PowerShell equivalent.

### Quick Validation Commands

```bash
# Validate configuration without processing
uv run cja_auto_sdr --validate-config

# Test with dry run (validates but doesn't generate output)
uv run cja_auto_sdr dv_12345 --dry-run

# List accessible data views
uv run cja_auto_sdr --list-dataviews

# Generate sample config
uv run cja_auto_sdr --sample-config
```

---

## Exit Codes Reference

| Exit Code | Meaning | Common Causes |
|-----------|---------|---------------|
| `0` | Success | Command completed successfully (diff: no changes found) |
| `1` | General Error | Configuration errors, missing arguments, validation failures |
| `2` | Policy Threshold Exceeded | Diff changes found, quality gate failed (`--fail-on-quality`), or org governance threshold failed (`--fail-on-threshold`) |
| `3` | Diff: Threshold Exceeded | Changes exceeded `--warn-threshold` percentage |

**Policy-aware exit codes** are designed for CI/CD integration:

```bash
# Check exit code after diff
cja_auto_sdr --diff dv_12345 dv_67890 --quiet-diff
case $? in
  0) echo "No differences found" ;;
  1) echo "Error occurred" ;;
  2) echo "Policy threshold exceeded (review needed)" ;;
  3) echo "Too many changes (threshold exceeded)" ;;
esac
```

---

## Configuration Errors

> For complete configuration reference, see the [Configuration Guide](CONFIGURATION.md).

### Configuration File Not Found

**Symptoms:**
```
CRITICAL - Configuration file not found: config.json
FileNotFoundError: Config file not found: config.json
```

**Solutions:**
1. Generate a sample configuration:
   ```bash
   uv run cja_auto_sdr --sample-config
   ```
2. Or use environment variables (see [Environment Variable Configuration](#environment-variable-configuration))

### Invalid JSON Syntax

**Symptoms:**
```
CRITICAL - Configuration file is not valid JSON: Expecting ',' delimiter: line 5 column 3
```

**Solutions:**
1. Validate JSON syntax:
   ```bash
   python -c "import json; json.load(open('config.json'))"
   ```
2. Common JSON issues:
   - Missing commas between fields
   - Trailing commas after last field (not allowed in JSON)
   - Unquoted strings
   - Single quotes instead of double quotes

### Missing Required Fields

**Symptoms:**
```
CRITICAL - Missing required field: 'org_id'
CRITICAL - Empty value for required field: 'client_id'
```

**Required fields in config.json:**
| Field | Type | Description |
|-------|------|-------------|
| `org_id` | string | Adobe Organization ID (ends with @AdobeOrg) |
| `client_id` | string | OAuth Client ID from Adobe Developer Console |
| `secret` | string | Client Secret from Adobe Developer Console |

**Optional fields:**
| Field | Type | Description |
|-------|------|-------------|
| `scopes` | string | OAuth scopes (recommended) |
| `sandbox` | string | Sandbox name |

**Solution:**
```json
{
  "org_id": "YOUR_ORG_ID@AdobeOrg",
  "client_id": "YOUR_CLIENT_ID",
  "secret": "YOUR_CLIENT_SECRET",
  "scopes": "your_scopes_from_developer_console"
}
```

### Unknown Fields Warning

**Symptoms:**
```
WARNING - Unknown fields in config (possible typos): ['orgid', 'clientid']
```

**Common typos:**
| Wrong | Correct |
|-------|---------|
| `orgid` | `org_id` |
| `clientid` | `client_id` |
| `client_secret` | `secret` |
| `scope` | `scopes` |

### Configuration File Permission Error

**Symptoms:**
```
PermissionError: Cannot read configuration file: Permission denied
```

**Solutions:**
```bash
# Check permissions
ls -la config.json

# Fix permissions
chmod 600 config.json
```

### Environment Variable Configuration

**Supported environment variables:**

| Environment Variable | Maps To | Required |
|---------------------|---------|----------|
| `ORG_ID` | org_id | Yes |
| `CLIENT_ID` | client_id | Yes |
| `SECRET` | secret | Yes |
| `SCOPES` | scopes | No (recommended) |
| `SANDBOX` | sandbox | No |
| `LOG_LEVEL` | log_level | No (default: INFO) |
| `OUTPUT_DIR` | output_dir | No (default: current dir) |

**Symptoms when missing:**
```
ERROR - Missing required environment variable: ORG_ID
WARNING - Environment credentials missing OAuth scopes - recommend setting SCOPES
```

**Solutions:**

Option 1: Export directly
```bash
export ORG_ID=your_org_id@AdobeOrg
export CLIENT_ID=your_client_id
export SECRET=your_client_secret
export SCOPES='your_scopes_from_developer_console'
```

Option 2: Use .env file (copy from .env.example)
```bash
cp .env.example .env
# Edit .env with your values
```

> **Note:** Environment variables take precedence over config.json

---

## Authentication & Connection Errors

### CJA Initialization Failed

**Symptoms:**
```
CRITICAL - CJA INITIALIZATION FAILED
CRITICAL - Failed to initialize CJA connection
Configuration error: Authentication failed
```

**Troubleshooting steps displayed:**
```
1. Verify your configuration file exists and is valid JSON
2. Check that all authentication credentials are correct
3. Ensure your API credentials have the necessary permissions
4. Verify you have network connectivity to Adobe services
5. Check if cjapy library is up to date: pip install --upgrade cjapy
```

**Solutions:**
1. Verify credentials match Adobe Developer Console exactly
2. Ensure the integration has CJA API enabled
3. Check network connectivity:
   ```bash
   ping adobe.io
   curl -I https://analytics.adobe.io
   ```
4. Upgrade cjapy:
   ```bash
   uv add --upgrade cjapy
   ```

### OAuth Token Retrieval Failed (v3.1.0+)

**Symptoms:**
```
Exception: OAuth response missing required fields. Response: {"error": "invalid_client", "error_description": "..."}
```
or
```
Exception: OAuth response missing required fields. Response: {"error": "invalid_scope", "error_description": "..."}
```

**Cause:** The OAuth token request to Adobe's authentication server failed. As of v3.1.0 (cjapy 0.2.4.post3), you now receive the actual OAuth error response, making it much easier to diagnose credential issues.

**Common OAuth error responses and solutions:**

| Error Response | Cause | Solution |
|----------------|-------|----------|
| `invalid_client` | Client ID or secret is incorrect | Verify `client_id` and `secret` match Developer Console exactly |
| `invalid_scope` | Scopes are incorrect or not authorized | Copy scopes exactly from Developer Console |
| `unauthorized_client` | Client not authorized for this grant type | Ensure OAuth Server-to-Server is enabled in Developer Console |
| `invalid_grant` | Credentials expired or revoked | Generate new credentials in Developer Console |

**Debugging steps:**
1. The error response shows exactly what Adobe's auth server rejected
2. Go to [Adobe Developer Console](https://developer.adobe.com/console/)
3. Open your project and check OAuth Server-to-Server credentials
4. Verify each field matches your `config.json` exactly:
   - `client_id` - OAuth Client ID
   - `secret` - Client Secret
   - `scopes` - Copy the exact scopes string
5. Test configuration:
   ```bash
   uv run cja_auto_sdr --validate-config
   ```

> **Note:** Prior to v3.1.0, OAuth failures could result in confusing downstream errors like `TypeError: expected str, got NoneType`. The improved error handling now shows the actual OAuth response immediately.

### JWT Authentication Deprecated

**Symptoms:**
```
WARNING - DEPRECATED: JWT authentication was removed in v3.0.8.
Found JWT fields: 'tech_acct', 'private_key'...
```

**Cause:** Your configuration file contains JWT authentication fields that are no longer supported.

**Solution:** Migrate to OAuth Server-to-Server authentication:

1. Create new OAuth credentials in [Adobe Developer Console](https://developer.adobe.com/console/)
2. Update your config file to use only these fields:
   ```json
   {
     "org_id": "YOUR_ORG_ID@AdobeOrg",
     "client_id": "YOUR_CLIENT_ID",
     "secret": "YOUR_CLIENT_SECRET",
     "scopes": "your_scopes_from_developer_console"
   }
   ```
3. Remove deprecated fields: `tech_acct`, `private_key`, `pathToKey`

See [Adobe's migration guide](https://developer.adobe.com/developer-console/docs/guides/authentication/ServerToServerAuthentication/migration/) for detailed instructions.

### API Connection Test Failed

**Symptoms:**
```
WARNING - API connection test returned None
WARNING - Could not verify connection with test call
```

**Causes:**
- Network issues
- Invalid credentials
- API permissions not configured

**Solutions:**
1. Run with debug logging:
   ```bash
   uv run cja_auto_sdr dv_12345 --log-level DEBUG
   ```
2. Check Adobe Status: https://status.adobe.com
3. Verify product profile includes CJA access

### Import Error for cjapy

**Symptoms:**
```
CRITICAL - Failed to import cjapy module: No module named 'cjapy'
ImportError: cjapy not found
```

**Solutions:**
```bash
# Install cjapy
uv add cjapy

# Or upgrade existing
uv add --upgrade cjapy

# Verify installation
uv pip list | grep cjapy
```

---

## `--validate-config` Errors

The `--validate-config` command runs 5 checks. If Step [4/5] (API connection) fails, the error message comes directly from the API response and can be cryptic. Here are the most common ones:

### `API connection failed: 'content'`

**Cause:** The API returned an empty or malformed response. This almost always means the Developer Console project is missing the AEP API, or the service account has not been granted product profile access.

**Solution:**

1. Verify **both** the CJA API and AEP API are added to your project (see [Quickstart Guide — Step 1.5](QUICKSTART_GUIDE.md#15-add-the-adobe-experience-platform-aep-api))
2. Verify the service account is assigned to the correct product profiles for both APIs
3. Wait 5-10 minutes after making permission changes, then re-run `--validate-config`

### `API connection failed: HTTP 401` or `HTTP 403`

**Cause:** Authentication or authorization failed — invalid credentials or insufficient permissions.

**Solution:**

1. Re-check your `client_id` and `client_secret` against the Developer Console
2. Verify your OAuth scopes match the Developer Console exactly (copy scopes **after** adding both APIs)
3. Ensure the service account has product profile access in [Admin Console](https://adminconsole.adobe.com/)

### `API connection failed (unexpected): ...`

**Cause:** An unexpected error during the API connection test — could be a network issue, proxy misconfiguration, or internal library error.

**Solution:**

1. Check your network connectivity
2. Re-run with `--log-level DEBUG` to see the full traceback
3. If the issue persists, try `--config-status` first to validate credentials without an API call

---

## API Permission Errors

### Missing AEP API Integration

**Symptoms:**
```
✗ API connection failed: 'content'
ERROR - Failed to fetch segments: 403 Forbidden
ERROR - Unable to retrieve calculated metrics
WARNING - Inventory features may be unavailable
```

**Cause:** Your Adobe Developer Console project only has the CJA API added, but is missing the **AEP (Adobe Experience Platform) API**. The AEP API associates your service account with an Experience Platform product profile, which is required for CJA API authentication.

**Solution:**

1. Go to [Adobe Developer Console](https://developer.adobe.com/console/)
2. Open your existing project
3. Click **"Add API"**
4. Search for **"Experience Platform API"**
5. Select **"Experience Platform API"** and click **"Next"**
6. Choose **"OAuth Server-to-Server"**
7. Select appropriate product profiles with AEP permissions
8. Click **"Save configured API"**

See the [Quickstart Guide](QUICKSTART_GUIDE.md#15-add-the-adobe-experience-platform-aep-api) for detailed instructions.

### Insufficient AEP Permissions

**Symptoms:**
```
ERROR - 403 Forbidden
WARNING - Cannot access sandbox 'prod'
```

**Cause:** Your user or service account is not associated with an Experience Platform product profile.

**Solution:**

1. Contact your Adobe Admin Console administrator
2. Request to be added to AEP product profiles
3. After permissions are granted, wait 5-10 minutes for propagation
4. Test with:
   ```bash
   uv run cja_auto_sdr --validate-config
   ```

### CJA Product Admin Rights Not Configured

**Symptoms:**
```
ERROR - Data view not accessible
WARNING - Limited data view access
ERROR - Cannot list metrics or dimensions
```

**Cause:** The API credentials don't have CJA Product Admin rights assigned.

**Solution:**

1. Go to [Adobe Admin Console](https://adminconsole.adobe.com/)
2. Navigate to **Products** → **Customer Journey Analytics**
3. Select the appropriate **Product Profile**
4. Add your service account or user to the profile
5. Ensure the profile has access to the required Data Views

### Connections API Returns Empty Results

**Symptoms:**
```
Note: The GET /connections API requires product-admin privileges.
Connection details are unavailable. Showing connection IDs derived
from data views instead.
```

Or `--list-connections` shows `dg_...` IDs instead of connection names.

**Cause:** The API **service account** (technical account) is not a CJA Product Admin. This is a common gotcha — even if **you** are a CJA Product Admin, the API authenticates as the technical account, which has separate permissions. The connections API returns 200 OK with an empty list instead of a 403 error, making this hard to diagnose.

**Solution:**

1. Go to [Adobe Developer Console](https://developer.adobe.com/console/)
2. Open your project → click **OAuth Server-to-Server** in the left sidebar
3. Copy the **Technical Account Email** (format: `<uuid>@techacct.adobe.com`)
4. Go to [Adobe Admin Console](https://adminconsole.adobe.com/)
5. Navigate to **Products** → **Customer Journey Analytics (Custom)** → **Admins** tab
6. Click **"Add admin"** and paste the Technical Account Email
7. Wait 5-10 minutes for permission propagation
8. Re-run `--list-connections` — you should now see full connection names and details

> **Key insight:** Your user account permissions and the API service account permissions are completely separate. Being a CJA Product Admin yourself does not grant the same access to the API's technical account.

### OAuth Scopes Missing or Incorrect

**Symptoms:**
```
ERROR - Authentication failed: insufficient_scope
WARNING - Token missing required scopes
```

**Cause:** The OAuth scopes in your configuration don't match what's configured in Adobe Developer Console.

**Solution:**

1. Go to [Adobe Developer Console](https://developer.adobe.com/console/)
2. Open your project and navigate to **OAuth Server-to-Server** credentials
3. Copy the **Scopes** value exactly as shown
4. Update your `config.json`:
   ```json
   {
     "org_id": "YOUR_ORG_ID@AdobeOrg",
     "client_id": "YOUR_CLIENT_ID",
     "secret": "YOUR_CLIENT_SECRET",
     "scopes": "paste_exact_scopes_from_console"
   }
   ```
5. Test the connection:
   ```bash
   uv run cja_auto_sdr --validate-config
   ```

### Verifying API Permissions

To diagnose permission issues, run with debug logging:

```bash
# Check basic CJA access
uv run cja_auto_sdr --list-dataviews --log-level DEBUG

# Check inventory access
uv run cja_auto_sdr dv_12345 --include-segments --log-level DEBUG 2>&1 | grep -i "403\|forbidden\|permission"
```

**Checklist for proper API setup:**

- [ ] CJA API added to Developer Console project
- [ ] AEP API added to Developer Console project
- [ ] OAuth Server-to-Server authentication configured
- [ ] Correct product profile(s) selected for both APIs
- [ ] User/service account added to CJA product profile in Admin Console
- [ ] Technical account email added as CJA Product Admin (required for `--list-connections` full details)
- [ ] User/service account added to AEP product profile(s) in Admin Console
- [ ] Scopes in config.json match Developer Console exactly

---

## Data View Errors

### Data View Not Found

**Symptoms:**
```
ERROR - Data view 'dv_12345' returned empty response
ERROR - Data view returned empty response
INFO - You have access to 5 data view(s):
INFO -   1. Production Analytics (ID: dv_abc123)
```

**Solutions:**
1. List available data views:
   ```bash
   uv run cja_auto_sdr --list-dataviews
   ```
2. Copy the exact ID from the output
3. Verify you have access permissions in CJA

### Invalid Data View ID Format

**Symptoms:**
```
ERROR: Invalid data view ID format: invalid_id, test123
WARNING - Data view ID does not follow standard format (dv_...)
```

**Requirements:**
- Data view IDs must start with `dv_`
- Must be non-empty strings

**Solutions:**
```bash
# Wrong
uv run cja_auto_sdr 12345
uv run cja_auto_sdr invalid_id

# Correct
uv run cja_auto_sdr dv_12345
```

### Data View Name Resolution Errors

You can use data view **names** instead of IDs. However, name resolution has strict requirements.

#### Name Not Found

**Symptoms:**
```text
ERROR - Data view name 'Production Analytics' not found in accessible data views
  → Remember: Name matching is CASE-SENSITIVE and requires EXACT match
  → Run 'cja_auto_sdr --list-dataviews' to see all available names

ERROR: No valid data views found

Possible issues:
  - Data view ID(s) or name(s) not found or you don't have access
  - Data view name is not an EXACT match (names are case-sensitive)
  - Configuration issue preventing data view lookup
```

**Common Causes:**

1. **Case Sensitivity** - Names must match exactly (case-sensitive)
   ```bash
   # If actual name is "Production Analytics":
   cja_auto_sdr "Production Analytics"    # ✅ Works
   cja_auto_sdr "production analytics"    # ❌ Fails
   cja_auto_sdr "PRODUCTION ANALYTICS"    # ❌ Fails
   cja_auto_sdr "Production analytics"    # ❌ Fails
   ```

2. **Partial Name** - Must match the complete name
   ```bash
   # If actual name is "Production Analytics - North America":
   cja_auto_sdr "Production Analytics - North America"  # ✅ Works
   cja_auto_sdr "Production Analytics"                  # ❌ Fails
   cja_auto_sdr "Production"                            # ❌ Fails
   ```

3. **Missing Quotes** - Names with spaces require quotes
   ```bash
   cja_auto_sdr Production Analytics      # ❌ Shell treats as 2 arguments
   cja_auto_sdr "Production Analytics"    # ✅ Works
   ```

**Solutions:**

1. List all accessible data views to see exact names:
   ```bash
   uv run cja_auto_sdr --list-dataviews
   ```

2. Copy the exact name from the output (including case and spacing)

3. Always use quotes around names:
   ```bash
   uv run cja_auto_sdr "Production Analytics"
   ```

#### Mixing IDs and Names

You can mix data view IDs and names in the same command:

```bash
# This works
uv run cja_auto_sdr dv_12345 "Production Analytics" dv_67890

# IDs start with 'dv_', everything else is treated as a name
uv run cja_auto_sdr "Test Environment" dv_12345 "Staging"
```

**Important:** If an identifier doesn't start with `dv_`, it's treated as a **name** and must:
- Match exactly (case-sensitive)
- Match the complete name (no partial matches)
- Be enclosed in quotes if it contains spaces

#### Name Resolution Performance

Name resolution requires an additional API call to fetch all data views:

**Impact:**
- Adds ~1-2 seconds to startup time
- Minimal impact on overall processing time

**Optimization:**
```bash
# Use caching for repeated runs
uv run cja_auto_sdr "Production Analytics" --enable-cache

# Or use IDs directly if you know them (no lookup needed)
uv run cja_auto_sdr dv_677ea9291244fd082f02dd42
```

#### Duplicate Names

If multiple data views share the same name, **all matching views will be processed**:

```text
$ uv run cja_auto_sdr "Production"

Resolving 1 data view name(s)...
INFO - Name 'Production' matched 3 data views: ['dv_12345', 'dv_67890', 'dv_abcde']

Data view name resolution:
  ✓ 'Production' → 3 matching data views:
      - dv_12345
      - dv_67890
      - dv_abcde

Processing 3 data view(s) total...
```

**This is by design** - useful when you have multiple environments with the same name.

**To process only one:**
1. Use the specific data view ID instead:
   ```bash
   uv run cja_auto_sdr dv_12345
   ```

2. Or use `--list-dataviews` to find unique identifiers

### No Access to Data Views

**Symptoms:**
```
WARNING - No data views found - no access to any data views
ERROR - Could not list available data views
```

**Solutions:**
1. Verify API credentials have CJA read permissions
2. Check product profile in Adobe Admin Console
3. Contact your Adobe administrator

### API Method Not Available

**Symptoms:**
```
ERROR - API method 'getDataView' not available
AttributeError: API method error - getMetrics may not be available
```

**Cause:** Outdated cjapy library

**Solution:**
```bash
uv add --upgrade cjapy
```

---

## Diff Comparison & Snapshot Errors

### Snapshot File Not Found

**Symptoms:**
```
ERROR - Snapshot file not found: ./snapshots/baseline.json
FileNotFoundError: Snapshot file not found
```

**Solutions:**
1. Check the file path is correct:
   ```bash
   ls -la ./snapshots/baseline.json
   ```
2. Verify you created a snapshot first:
   ```bash
   cja_auto_sdr dv_12345 --snapshot ./snapshots/baseline.json
   ```

### Invalid Snapshot File

**Symptoms:**
```
ERROR - Invalid snapshot file: missing 'snapshot_version' field
ERROR - Failed to parse snapshot JSON: Expecting value
```

**Causes:**
- File is not a valid JSON
- File was not created by this tool
- File was corrupted or manually edited incorrectly

**Solutions:**
1. Verify the file is valid JSON:
   ```bash
   python -c "import json; json.load(open('./snapshots/baseline.json'))"
   ```
2. Create a fresh snapshot:
   ```bash
   cja_auto_sdr dv_12345 --snapshot ./snapshots/baseline.json
   ```

### Ambiguous Name Resolution in Diff Mode

**Symptoms:**
```
ERROR - Ambiguous data view name 'Analytics' matches multiple data views
ERROR - Diff operations require exactly one match per identifier
```

**Cause:** When using `--diff`, each identifier must resolve to exactly one data view. Unlike batch SDR generation (where duplicate names process all matches), diff requires unambiguous identifiers.

**Solutions:**
1. Use data view IDs instead of names:
   ```bash
   cja_auto_sdr --diff dv_12345 dv_67890
   ```
2. Run `--list-dataviews` to find unique identifiers:
   ```bash
   cja_auto_sdr --list-dataviews
   ```

### Fuzzy Name Suggestions

**Symptoms:**
```
No data view found with name 'Prodction Analytics'
Did you mean one of these?
  - Production Analytics (edit distance: 1)
  - Production Analytics v2 (edit distance: 4)
```

**Cause:** Name not found, but similar names exist. This suggests a typo.

**Solution:** Check the suggested names and use the correct spelling with quotes:
```bash
cja_auto_sdr --diff "Production Analytics" "Staging Analytics"
```

### Compare-Snapshots File Errors

**Symptoms:**
```
ERROR - First snapshot file not found: ./old.json
ERROR - Second snapshot file not found: ./new.json
```

**Solution:** Verify both snapshot files exist before comparing:
```bash
ls -la ./old.json ./new.json
cja_auto_sdr --compare-snapshots ./old.json ./new.json
```

### Auto-Snapshot Directory Errors

**Symptoms:**
```
ERROR - Cannot create snapshot directory: Permission denied
ERROR - Failed to save auto-snapshot: ./snapshots/DataView_dv_123_20260118.json
```

**Solutions:**
1. Ensure the snapshot directory is writable:
   ```bash
   mkdir -p ./snapshots
   chmod 755 ./snapshots
   ```
2. Use a different directory:
   ```bash
   cja_auto_sdr --diff dv_12345 dv_67890 --auto-snapshot --snapshot-dir ~/tmp/snapshots
   ```

### Retention Policy Not Deleting Old Snapshots

**Symptoms:** Old snapshots accumulate even with `--keep-last N` set.

**Cause:** Retention applies per data view, not globally. If you have 10 data views, `--keep-last 5` keeps 5 snapshots *per data view* (up to 50 total).

**Tip:** If you want retention applied automatically on every diff run, use `--auto-prune` with `--auto-snapshot` (defaults to `--keep-last 20` and `--keep-since 30d` unless explicit retention flags are provided).

**Verification:**
```bash
# Check snapshot counts per data view
ls -la ./snapshots/ | grep "dv_12345" | wc -l
ls -la ./snapshots/ | grep "dv_67890" | wc -l
```

### Diff Output File Errors

**Symptoms:**
```
ERROR - Cannot write diff output: ./reports/diff.md
PermissionError: Permission denied
```

**Solutions:**
1. Ensure the output directory exists and is writable
2. Check if the file is open in another application
3. Use a different output path:
   ```bash
   cja_auto_sdr --diff dv_12345 dv_67890 --diff-output ~/Desktop/diff-report.md
   ```

---

## Profile Errors

> **Note:** Profiles are stored in your user home directory at `~/.cja/orgs/`, not in the project directory. This location can be customized with the `CJA_HOME` environment variable. See [Profile Management](CONFIGURATION.md#profile-management) for details.

### Profile Not Found

**Symptoms:**
```
ERROR - Profile 'client-a' not found
ProfileNotFoundError: Profile directory does not exist: ~/.cja/orgs/client-a
```

**Solutions:**
1. List available profiles:
   ```bash
   cja_auto_sdr --profile-list
   ```
2. Create the profile:
   ```bash
   cja_auto_sdr --profile-add client-a
   ```
3. Check profile directory exists:
   ```bash
   ls -la ~/.cja/orgs/
   ```

### Invalid Profile Name

**Symptoms:**
```
ERROR - Invalid profile name: 'my profile'
Profile names must contain only letters, numbers, dashes, and underscores
```

**Valid profile names:**
- `client-a` ✓
- `prod_org` ✓
- `acme2024` ✓
- `my_client` ✓

**Invalid profile names:**
- `my profile` ✗ (contains space)
- `-invalid` ✗ (starts with dash)
- `special@chars` ✗ (contains special characters)

### Profile Configuration Error

**Symptoms:**
```
ERROR - Profile 'client-a' has invalid configuration
ProfileConfigError: Missing required field 'org_id' in config.json
```

**Solutions:**
1. Check profile configuration:
   ```bash
   cja_auto_sdr --profile-show client-a
   ```
2. Verify config.json in profile directory:
   ```bash
   cat ~/.cja/orgs/client-a/config.json
   ```
3. Ensure all required fields are present:
   ```json
   {
     "org_id": "YOUR_ORG_ID@AdobeOrg",
     "client_id": "YOUR_CLIENT_ID",
     "secret": "YOUR_CLIENT_SECRET",
     "scopes": "your_scopes_from_developer_console"
   }
   ```

### Profile Test Failed

**Symptoms:**
```
ERROR - Profile 'client-a' failed connectivity test
Authentication failed with provided credentials
```

**Solutions:**
1. Verify credentials are correct:
   ```bash
   cja_auto_sdr --profile-show client-a
   ```
2. Check that credentials haven't expired in Adobe Developer Console
3. Verify OAuth scopes are correct
4. Test with debug logging:
   ```bash
   cja_auto_sdr --profile client-a --list-dataviews --log-level DEBUG
   ```

### CJA_PROFILE Environment Variable Not Working

**Symptoms:**
```bash
export CJA_PROFILE=client-a
cja_auto_sdr --list-dataviews
# Still uses default config.json instead of profile
```

**Solutions:**
1. Verify environment variable is set:
   ```bash
   echo $CJA_PROFILE
   ```
2. Check for typos in profile name
3. Use `--profile` flag explicitly to verify the profile works:
   ```bash
   cja_auto_sdr --profile client-a --list-dataviews
   ```

### Profile Directory Permission Issues

**Symptoms:**
```
PermissionError: Cannot read profile configuration
ERROR - Permission denied accessing ~/.cja/orgs/client-a/config.json
```

**Solutions:**
```bash
# Check permissions
ls -la ~/.cja/orgs/client-a/

# Fix permissions
chmod 700 ~/.cja/orgs/client-a
chmod 600 ~/.cja/orgs/client-a/config.json
```

### CJA_HOME Not Recognized

**Symptoms:**
```bash
export CJA_HOME=/custom/path
cja_auto_sdr --profile-list
# Still looks in ~/.cja/orgs/
```

**Solutions:**
1. Ensure the custom directory exists:
   ```bash
   mkdir -p /custom/path/orgs
   ```
2. Verify CJA_HOME is exported (not just set):
   ```bash
   export CJA_HOME=/custom/path
   echo $CJA_HOME
   ```
3. Check spelling (case-sensitive):
   ```bash
   # Correct
   export CJA_HOME=/custom/path

   # Wrong
   export cja_home=/custom/path
   export CJA_Home=/custom/path
   ```

---

## API & Network Errors

### HTTP Status Code Errors

**Retryable errors (automatic retry):**

| Status Code | Meaning | Action |
|-------------|---------|--------|
| 408 | Request Timeout | Auto-retry with backoff |
| 429 | Too Many Requests | Auto-retry with backoff (rate limited) |
| 500 | Internal Server Error | Auto-retry with backoff |
| 502 | Bad Gateway | Auto-retry with backoff |
| 503 | Service Unavailable | Auto-retry with backoff |
| 504 | Gateway Timeout | Auto-retry with backoff |

**Non-retryable errors:**

| Status Code | Meaning | Action |
|-------------|---------|--------|
| 400 | Bad Request | Check request parameters |
| 401 | Unauthorized | Check credentials |
| 403 | Forbidden | Check permissions |
| 404 | Not Found | Verify data view ID |

### Connection and Timeout Errors

**Symptoms:**
```
ConnectionError: Failed to connect to Adobe API
TimeoutError: Request timed out
OSError: Network unreachable
```

**These are automatically retried.** If all retries fail:

```
ERROR - All 3 attempts failed for fetch_metrics: Connection timed out
```

**Solutions:**
1. Check network connectivity
2. Increase retry parameters:
   ```bash
   uv run cja_auto_sdr dv_12345 --max-retries 5 --retry-base-delay 2.0 --retry-max-delay 60.0
   ```

---

## Retry Mechanism & Rate Limiting

### Understanding the Retry System

The tool automatically retries failed API calls with exponential backoff:

**Default retry configuration:**
| Parameter | Default | CLI Flag |
|-----------|---------|----------|
| Max retries | 3 | `--max-retries` |
| Base delay | 1.0s | `--retry-base-delay` |
| Max delay | 30.0s | `--retry-max-delay` |

**Backoff formula:**
```
delay = min(base_delay * (2 ^ attempt), max_delay) * random(0.5, 1.5)
```

**Example progression:**
- Attempt 1 fails → wait ~1s (0.5-1.5s with jitter)
- Attempt 2 fails → wait ~2s (1-3s with jitter)
- Attempt 3 fails → wait ~4s (2-6s with jitter)
- All attempts exhausted → error raised

### Retry Log Messages

**During retries:**
```
WARNING - fetch_metrics attempt 1/3 failed: Connection timed out. Retrying in 1.2s...
WARNING - fetch_metrics attempt 2/3 failed: HTTP 503. Retrying in 2.8s...
```

**After successful retry:**
```
INFO - fetch_metrics succeeded on attempt 3/3
```

**All retries failed:**
```
ERROR - All 3 attempts failed for fetch_metrics: HTTP 503: Service Unavailable
```

### Rate Limiting (HTTP 429)

**Symptoms:**
```
WARNING - fetch_metrics attempt 1/3 failed: HTTP 429. Retrying in 1.5s...
```

**Solutions:**
1. Reduce parallel workers in batch mode:
   ```bash
   uv run cja_auto_sdr dv_1 dv_2 dv_3 --workers 2
   ```
2. Increase delays:
   ```bash
   uv run cja_auto_sdr dv_12345 --retry-base-delay 2.0 --retry-max-delay 60.0
   ```

### Customizing Retry Behavior

```bash
# More aggressive retrying for flaky networks
uv run cja_auto_sdr dv_12345 --max-retries 5 --retry-base-delay 2.0 --retry-max-delay 120.0

# Minimal retries for fast-fail scenarios
uv run cja_auto_sdr dv_12345 --max-retries 1

# No retries (fail immediately)
uv run cja_auto_sdr dv_12345 --max-retries 0
```

---

## Data Quality Issues

### No Metrics or Dimensions

**Symptoms:**
```
ERROR - No metrics or dimensions fetched. Cannot generate SDR.
WARNING - No metrics returned from API
WARNING - No dimensions returned from API
```

**Causes:**
- Data view has no components configured
- API permissions don't include component read access
- Data view is newly created and empty

**Solutions:**
1. Verify data view has components in CJA UI
2. Check API permissions include read access
3. Run dry-run to validate:
   ```bash
   uv run cja_auto_sdr dv_12345 --dry-run
   ```

### Data Quality Validation Issues

**Severity levels:**

| Severity | Color | Meaning |
|----------|-------|---------|
| CRITICAL | Red | Blocking issues (empty data, missing required fields) |
| HIGH | Orange | Serious issues (missing IDs, duplicates) |
| MEDIUM | Yellow | Notable issues (null values in critical fields) |
| LOW | Blue | Minor issues (missing descriptions) |
| INFO | Gray | Informational |

**Common validation issues:**

| Issue | Severity | Message |
|-------|----------|---------|
| Empty data | CRITICAL | "No {item_type} found in data view" |
| Missing fields | CRITICAL | "Missing required fields: {fields}" |
| Invalid IDs | HIGH | "{count} items with missing IDs" |
| Duplicates | HIGH | "Item '{name}' appears {count} times" |
| Null values | MEDIUM | "{count} items missing {field}" |
| No descriptions | LOW | "{count} items without descriptions" |

**Skip validation if not needed:**
```bash
# 20-30% faster processing
uv run cja_auto_sdr dv_12345 --skip-validation
```

---

## Output & File Errors

### Permission Denied Writing Output

**Symptoms:**
```
PermissionError: [Errno 13] Permission denied: 'SDR_Analytics_2024-01-15.xlsx'
ERROR - Permission denied writing to SDR_Analytics_2024-01-15.xlsx
```

**Causes:**
- File is open in Excel or another program
- Insufficient write permissions to directory

**Solutions:**
1. Close the Excel file
2. Specify a different output directory:
   ```bash
   uv run cja_auto_sdr dv_12345 --output-dir ./reports
   ```

### Output Directory Does Not Exist

**Symptoms:**
```
ERROR - Permission denied creating output directory: /nonexistent/path
ERROR - Cannot create output directory '/path/to/dir': Permission denied
```

**Solutions:**
```bash
# Create directory first
mkdir -p ./reports

# Then run
uv run cja_auto_sdr dv_12345 --output-dir ./reports
```

### Excel Generation Failures

**Symptoms:**
```
ERROR - Failed to generate Excel file: {error}
ERROR - Error formatting JSON cell: {error}
```

**Solutions:**
1. Try a different format:
   ```bash
   uv run cja_auto_sdr dv_12345 --format csv
   uv run cja_auto_sdr dv_12345 --format json
   ```
2. Check disk space:
   ```bash
   df -h .
   ```

### Empty Output File

**Possible Causes:**
- Data view has no components configured
- API permissions don't include read access

**Solutions:**
1. Check log file for "No metrics returned from API"
2. Verify data view has components in CJA UI
3. Run with debug logging:
   ```bash
   uv run cja_auto_sdr dv_12345 --log-level DEBUG
   ```

---

## Batch Processing Issues

### Batch Initialization Errors

**Symptoms:**
```
CRITICAL - Permission denied creating output directory: ./reports
CRITICAL - Cannot create output directory './reports': {error}
```

**Solution:** Ensure you have write permissions to the output directory.

### Individual Data View Failures

**Symptoms:**
```
[batch_abc123] dv_12345: FAILED - Data view not found
[batch_abc123] dv_67890: EXCEPTION - Connection timeout
```

**Continue processing despite failures:**
```bash
uv run cja_auto_sdr dv_1 dv_2 dv_3 --continue-on-error
```

### Batch Processing Slower Than Expected

**Causes:**
- Too many workers causing rate limiting
- Network bottleneck
- Large data views

**Solutions:**
```bash
# Reduce workers (default: 4)
uv run cja_auto_sdr dv_1 dv_2 dv_3 --workers 2

# Check logs for rate limiting (macOS/Linux)
grep "429\|rate limit" logs/*.log

# Check logs for rate limiting (Windows PowerShell)
# Select-String -Path logs\*.log -Pattern "429|rate limit"
```

### Worker Count Validation Errors

**Symptoms:**
```
ERROR: --workers must be at least 1
ERROR: --workers cannot exceed 256
```

**Valid range:** 1-256 workers

---

## Validation Cache Issues

### Understanding the Cache

The validation cache stores data quality check results to avoid redundant processing:

**Cache parameters:**
| Parameter | Default | CLI Flag |
|-----------|---------|----------|
| Enable cache | Off | `--enable-cache` |
| Cache size | 1000 entries | `--cache-size` |
| Cache TTL | 3600s (1 hour) | `--cache-ttl` |

### Cache Log Messages

**Debug-level cache messages:**
```
DEBUG - Cache HIT: metrics (age: 45s)
DEBUG - Cache MISS: dimensions
DEBUG - Cache EXPIRED: metrics (age: 3700s)
```

### Cache Issues

**Cache not helping performance:**
- TTL too short
- Cache size too small
- Data changing frequently

**Solutions:**
```bash
# Increase cache TTL for stable data
uv run cja_auto_sdr dv_12345 --enable-cache --cache-ttl 7200

# Increase cache size for many data views
uv run cja_auto_sdr dv_1 dv_2 dv_3 --enable-cache --cache-size 5000
```

**Clear cache before processing:**
```bash
uv run cja_auto_sdr dv_12345 --enable-cache --clear-cache
```

### Cache Parameter Validation Errors

**Symptoms:**
```
ERROR: --cache-size must be at least 1
ERROR: --cache-ttl must be at least 1 second
```

---

## Inventory Feature Issues

The inventory features (`--include-segments`, `--include-calculated`, `--include-derived`) document CJA components beyond the standard SDR output. These features work in both SDR mode and snapshot diff mode (same data view over time).

> **Note:** `--include-derived` is for SDR generation only, not snapshot diff. Derived fields are already included in the standard metrics/dimensions API output, so changes are automatically captured in the Metrics/Dimensions diff sections.

### Using --include-all-inventory

The `--include-all-inventory` flag uses smart mode detection:

```bash
# Shorthand for all inventories (SDR mode)
cja_auto_sdr dv_12345 --include-all-inventory

# Equivalent to:
cja_auto_sdr dv_12345 --include-segments --include-calculated --include-derived
```

When used with snapshot/diff modes, it automatically excludes `--include-derived`:

```bash
# In snapshot mode, --include-all-inventory enables only segments and calculated metrics
cja_auto_sdr dv_12345 --snapshot ./baseline.json --include-all-inventory
# Equivalent to: --include-segments --include-calculated (no --include-derived)

# In diff-snapshot mode, same behavior
cja_auto_sdr dv_12345 --diff-snapshot ./baseline.json --include-all-inventory
```

### Using --inventory-summary

The `--inventory-summary` flag provides quick inventory statistics without generating full output files:

```bash
# Quick stats for all inventories
cja_auto_sdr dv_12345 --include-all-inventory --inventory-summary

# Quick stats for specific inventory
cja_auto_sdr dv_12345 --include-segments --inventory-summary
```

**Symptoms when misused:**
```
ERROR: --inventory-summary requires at least one of: --include-segments, --include-derived, --include-calculated
```

**Solution:** Add at least one inventory flag:
```bash
cja_auto_sdr dv_12345 --include-segments --inventory-summary
# Or use the shorthand:
cja_auto_sdr dv_12345 --include-all-inventory --inventory-summary
```

### Inventory Options Not Compatible with Cross-DV Diff

**Symptoms:**
```
ERROR: --include-segments cannot be used with --diff (cross-data-view comparisons)
```

**Cause:** Inventory options are not supported for cross-data-view diff (`--diff`) because calculated metrics, segments, and derived fields use data-view-scoped IDs that cannot be matched across different data views.

**Solutions:**
1. For cross-DV diff, remove the inventory flag:
   ```bash
   # Wrong - inventory with cross-DV diff
   cja_auto_sdr --diff dv_12345 dv_67890 --include-segments

   # Correct - cross-DV diff only
   cja_auto_sdr --diff dv_12345 dv_67890
   ```

2. For same-data-view comparisons over time, use snapshot diff with inventory:
   ```bash
   # Create baseline snapshot with inventory
   cja_auto_sdr dv_12345 --snapshot ./baseline.json --include-segments

   # Compare current state against baseline (inventory diff supported)
   cja_auto_sdr dv_12345 --diff-snapshot ./baseline.json --include-segments
   ```

### Inventory-Only Not Compatible with Diff Modes

**Symptoms:**
```
ERROR: --inventory-only is only available in SDR mode, not with --diff-snapshot
ERROR: --inventory-only is only available in SDR mode, not with --compare-snapshots
```

**Cause:** The `--inventory-only` flag is for SDR generation only. In diff mode, you compare inventories as part of the diff output, not as standalone sheets.

**Solution:** Remove `--inventory-only` when using diff modes:
```bash
# Wrong - inventory-only with diff
cja_auto_sdr dv_12345 --diff-snapshot ./baseline.json --include-segments --inventory-only

# Correct - inventory diff without --inventory-only
cja_auto_sdr dv_12345 --diff-snapshot ./baseline.json --include-segments
```

### Inventory-Only Requires Include Flag

**Symptoms:**
```
ERROR: --inventory-only requires at least one of: --include-segments, --include-derived, --include-calculated
```

**Cause:** The `--inventory-only` flag skips standard SDR sheets but requires at least one inventory type to generate.

**Solutions:**
```bash
# Wrong - inventory-only without include flag
cja_auto_sdr dv_12345 --inventory-only

# Correct - specify which inventories to include
cja_auto_sdr dv_12345 --include-segments --inventory-only
cja_auto_sdr dv_12345 --include-calculated --include-derived --inventory-only
cja_auto_sdr dv_12345 --include-segments --include-calculated --include-derived --inventory-only
```

### No Segments Found

**Symptoms:**
```
INFO - No segments found for data view dv_12345
WARNING - Segments inventory is empty
```

**Causes:**
- No segments are associated with the data view
- API credentials don't have permission to read segments
- The `getFilters` API endpoint is not accessible

**Solutions:**
1. Verify segments exist in CJA UI for the data view
2. Check API permissions include segment read access
3. Test API connectivity:
   ```bash
   uv run cja_auto_sdr dv_12345 --include-segments --log-level DEBUG
   ```

### No Derived Fields Found

**Symptoms:**
```
INFO - No derived fields found in data view dv_12345
WARNING - Derived fields inventory is empty
```

**Causes:**
- Data view has no derived fields configured
- Derived fields are not exposed in the API response

**Solutions:**
1. Verify derived fields exist in CJA data view settings
2. Check that derived fields are included in the data view's component list

### No Calculated Metrics Found

**Symptoms:**
```
INFO - No calculated metrics found for data view dv_12345
WARNING - Calculated metrics inventory is empty
```

**Causes:**
- No calculated metrics are associated with the data view
- API credentials don't have permission to read calculated metrics

**Solutions:**
1. Verify calculated metrics exist and are associated with the data view in CJA
2. Check API permissions include calculated metrics read access

### Complexity Score Appears Incorrect

**Symptoms:** Complexity scores seem too high or too low for certain components.

**Understanding complexity scores:**
- Scores range from 0-100
- Factors vary by inventory type (see documentation for weights)
- Scores are relative, not absolute measures

**Complexity Score Factors:**

| Inventory | Key Factors |
|-----------|-------------|
| Segments | Predicates (30%), logic operators (20%), nesting (20%), references (20%), regex (10%) |
| Derived Fields | Operators (30%), branches (25%), nesting (20%), functions (10%), schema fields (10%), regex (5%) |
| Calculated Metrics | Operators (25%), metric refs (25%), nesting (20%), functions (15%), segments (10%), conditionals (5%) |

**Interpreting scores:**
| Score | Complexity | Typical Characteristics |
|-------|------------|------------------------|
| 0-25 | Low | Simple, single operation |
| 26-50 | Moderate | Multiple conditions or references |
| 51-75 | Elevated | Nested logic, multiple components |
| 76-100 | High | Complex sequential or multi-layered logic |

### Inventory Sheet Missing from Output

**Symptoms:** Requested inventory sheet doesn't appear in output.

**Causes:**
- No components of that type exist
- API returned empty data
- Output format doesn't support the inventory type

**Solutions:**
1. Check logs for "No {type} found" messages
2. Verify the component type exists in the data view
3. Run with debug logging:
   ```bash
   cja_auto_sdr dv_12345 --include-segments --log-level DEBUG
   ```

### Inventory Processing Slow

**Symptoms:** Adding inventory flags significantly increases processing time.

**Cause:** Each inventory type requires additional API calls to fetch component data.

**Solutions:**
1. Only include inventories you need:
   ```bash
   # Instead of all three (or --include-all-inventory)
   cja_auto_sdr dv_12345 --include-segments --include-calculated --include-derived

   # Include only what you need
   cja_auto_sdr dv_12345 --include-segments
   ```

2. Use `--inventory-summary` for quick stats without full output (v3.1.0):
   ```bash
   # Quick check of inventory counts and complexity
   cja_auto_sdr dv_12345 --include-all-inventory --inventory-summary
   ```

3. Use `--inventory-only` for focused inventory output:
   ```bash
   # Skip standard SDR sheets for faster inventory-only output
   cja_auto_sdr dv_12345 --include-all-inventory --inventory-only
   ```

---

## Git & Repository Issues

### GitHub Authentication Failed When Cloning

**Symptoms:**
```
remote: Invalid username or token. Password authentication is not supported for Git operations.
```

**Cause:** GitHub removed support for password authentication in August 2021. You cannot use your GitHub account password to clone repositories over HTTPS.

**Solutions:**

**Option 1: Use a Personal Access Token (PAT) — Recommended**

1. Go to GitHub → Settings → Developer settings → Personal access tokens → Tokens (classic)
2. Click "Generate new token (classic)"
3. Give it a name and select the `repo` scope
4. Copy the generated token
5. When cloning, use the token as your password:
   ```bash
   git clone https://github.com/brian-a-au/cja_auto_sdr.git
   # Username: your-github-username
   # Password: paste-your-token-here
   ```

**Option 2: Use SSH instead of HTTPS**

1. Generate an SSH key if you don't have one:
   ```bash
   ssh-keygen -t ed25519 -C "your_email@example.com"
   ```
2. Add the public key to GitHub (Settings → SSH and GPG keys)
3. Clone using SSH URL:
   ```bash
   git clone git@github.com:brian-a-au/cja_auto_sdr.git
   ```

**Option 3: Use GitHub CLI**

1. Install GitHub CLI: https://cli.github.com/
2. Authenticate:
   ```bash
   gh auth login
   ```
3. Clone the repository:
   ```bash
   gh repo clone brian-a-au/cja_auto_sdr
   ```

**Windows-specific note:** If using Git Credential Manager, it should prompt you for authentication automatically and can store your PAT securely.

---

## Performance Issues

### Normal Processing Times

| Data View Size | Expected Time |
|----------------|---------------|
| Small (<50 components) | 15-30 seconds |
| Medium (50-200 components) | 30-60 seconds |
| Large (200+ components) | 60-120 seconds |

### Slow Processing Solutions

```bash
# Skip validation (20-30% faster)
uv run cja_auto_sdr dv_12345 --skip-validation

# Use production mode (reduces logging)
uv run cja_auto_sdr dv_12345 --production

# Enable caching for repeated runs (50-90% faster on cache hits)
uv run cja_auto_sdr dv_12345 --enable-cache

# Use quiet mode (minimal output)
uv run cja_auto_sdr dv_12345 --quiet
```

### Batch Processing Performance

```bash
# Optimal batch processing
uv run cja_auto_sdr dv_1 dv_2 dv_3 --workers 4 --enable-cache

# Balance speed vs. rate limiting
uv run cja_auto_sdr dv_1 dv_2 dv_3 --workers 2 --retry-base-delay 1.5
```

---

## Dependency Issues

> **Recommended cjapy version:** v3.2.7 requires cjapy 0.2.4.post3 or later for improved OAuth error handling. Users on older versions may see confusing errors when authentication fails. Upgrade with: `uv add --upgrade cjapy`

### Module Not Found

**Symptoms:**
```
ModuleNotFoundError: No module named 'cjapy'
ModuleNotFoundError: No module named 'pandas'
ModuleNotFoundError: No module named 'xlsxwriter'
```

**Solutions:**
```bash
# Sync all dependencies
uv sync

# Or reinstall everything
uv sync --reinstall

# Verify installation
uv pip list | grep -E "cjapy|pandas|xlsxwriter"
```

### Version Conflicts

**Solutions:**
```bash
# Check for conflicts
uv pip check

# Update specific package
uv add --upgrade cjapy

# Regenerate lock file
rm uv.lock
uv sync
```

### uv Command Not Found

**Solutions:**
```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh

# Verify
uv --version

# Then sync project
uv sync
```

### Wrong Python Version

**Solution:**
```bash
# Remove and recreate venv
rm -rf .venv
uv venv --python 3.14
uv sync
```

---

## Windows-Specific Issues

### NumPy ImportError on Windows

**Symptoms:**
```
ImportError: Unable to import required dependencies:
numpy:

IMPORTANT: PLEASE READ THIS FOR ADVICE ON HOW TO SOLVE THIS ISSUE!

Importing the numpy C-extensions failed. This error can happen for
many reasons, often due to issues with your setup or how NumPy was
installed.
```

**Cause:** NumPy's C-extensions require compatible binary wheels for Windows. This commonly occurs when:
- Python was installed from the Microsoft Store
- The virtual environment was created with an incompatible Python version
- NumPy was installed without proper Windows build tools

**Solutions:**

**Solution 1: Use Python directly instead of uv (Recommended for Windows)**

If `uv run` doesn't work, use Python directly:

```text
# Activate the virtual environment
.venv\Scripts\activate

# Install dependencies with pip
pip install -e .

# Run the tool directly
cja_auto_sdr --version
cja_auto_sdr dv_YOUR_DATA_VIEW_ID
```

**Solution 2: Reinstall Python and dependencies**

```text
# Remove existing virtual environment
Remove-Item -Recurse -Force .venv

# Create new virtual environment with Python 3.14 or higher
python -m venv .venv

# Activate it
.venv\Scripts\activate

# Upgrade pip
python -m pip install --upgrade pip

# Install numpy with pip (not uv)
pip install numpy>=2.2.0

# Install other dependencies
pip install cjapy>=0.2.4.post3 pandas>=2.3.3 xlsxwriter>=3.2.9 tqdm>=4.66.0

# Verify numpy works
python -c "import numpy; print(numpy.__version__)"

# Install the tool
pip install -e .
```

**Solution 3: Use pre-built binary wheels**

```text
# Download and install from PyPI with explicit binary wheel
pip install --only-binary :all: numpy

# Then install other dependencies
pip install -e .
```

**Solution 4: Install Microsoft C++ Build Tools (if needed)**

For some packages, you may need:
1. Download [Microsoft C++ Build Tools](https://visualstudio.microsoft.com/visual-cpp-build-tools/)
2. Install "Desktop development with C++"
3. Restart terminal and reinstall dependencies

### uv run Command Not Working on Windows

**Symptoms:**
```text
PS> uv run cja_auto_sdr --version
# Command fails or doesn't recognize the script
```

**Cause:** The `uv` package manager may have issues with Windows PATH configuration or virtual environment activation.

**Solutions:**

**Option 1: Use Python directly (Most Reliable)**

```text
# Activate virtual environment first
.venv\Scripts\activate

# Then run commands without uv
cja_auto_sdr --version
cja_auto_sdr dv_12345

# Or run the script directly
cja_auto_sdr --version
cja_auto_sdr dv_12345
```

**Option 2: Use full Python path**

```text
# Without activating venv
.venv\Scripts\cja_auto_sdr.exe --version
.venv\Scripts\cja_auto_sdr.exe dv_12345
```

**Option 3: Fix uv PATH (if you prefer using uv)**

```text
# Check if uv is in PATH
where.exe uv

# If not found, add to PATH manually:
# 1. Press Win + X, select "System"
# 2. Click "Advanced system settings"
# 3. Click "Environment Variables"
# 4. Add uv installation directory to PATH

# Then restart PowerShell and try again
uv --version
uv run cja_auto_sdr --version
```

### PowerShell Execution Policy Issues

**Symptoms:**
```text
.\install.ps1 : File cannot be loaded because running scripts is disabled on this system.
```

**Solution:**
```powershell
# Check current execution policy
Get-ExecutionPolicy

# Set execution policy (run as Administrator)
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Or bypass for a single session
powershell -ExecutionPolicy Bypass -File .\script.ps1
```

### Path Separator Issues

**Issue:** Documentation examples use Unix path separators `/` which may cause issues on Windows.

**Solution:** Windows PowerShell and Command Prompt understand both forward slashes `/` and backslashes `\`. However, for consistency:

```text
# These all work on Windows:
--output-dir ./reports     # Works
--output-dir .\reports     # Works
--output-dir C:\reports    # Works
--output-dir C:/reports    # Works
```

### Virtual Environment Activation on Windows

**Different shells require different activation:**

**PowerShell:**
```powershell
.venv\Scripts\Activate.ps1
# Or simply:
.venv\Scripts\activate
```

**Command Prompt (cmd.exe):**
```cmd
.venv\Scripts\activate.bat
```

**Git Bash (on Windows):**
```bash
source .venv/Scripts/activate
```

### Windows Diagnostic Script

The main diagnostic script in the troubleshooting guide is bash-only. Here's a Windows PowerShell equivalent:

**Save as `diagnose.ps1`:**

```powershell
Write-Host "=== System Information ===" -ForegroundColor Cyan
python --version
uv --version 2>$null
if ($LASTEXITCODE -ne 0) { Write-Host "uv: not installed" -ForegroundColor Yellow }

Write-Host "`n=== Project Dependencies ===" -ForegroundColor Cyan
if (Test-Path .venv\Scripts\python.exe) {
    & .venv\Scripts\python.exe -m pip list | Select-String -Pattern "cjapy|pandas|numpy|xlsxwriter"
} else {
    Write-Host "Virtual environment not found" -ForegroundColor Red
}

Write-Host "`n=== Configuration Check ===" -ForegroundColor Cyan
if (Test-Path config.json) {
    Write-Host "config.json: exists" -ForegroundColor Green
    try {
        $config = Get-Content config.json | ConvertFrom-Json
        Write-Host "JSON syntax: valid" -ForegroundColor Green
    } catch {
        Write-Host "JSON syntax: INVALID" -ForegroundColor Red
    }
} else {
    Write-Host "config.json: NOT FOUND" -ForegroundColor Yellow
}

Write-Host "`n=== Environment Variables ===" -ForegroundColor Cyan
if ($env:ORG_ID) { Write-Host "ORG_ID: set" -ForegroundColor Green } else { Write-Host "ORG_ID: not set" }
if ($env:CLIENT_ID) { Write-Host "CLIENT_ID: set" -ForegroundColor Green } else { Write-Host "CLIENT_ID: not set" }
if ($env:SECRET) { Write-Host "SECRET: set" -ForegroundColor Green } else { Write-Host "SECRET: not set" }
if ($env:SCOPES) { Write-Host "SCOPES: set" -ForegroundColor Green } else { Write-Host "SCOPES: not set" }

Write-Host "`n=== Recent Logs ===" -ForegroundColor Cyan
if (Test-Path logs) {
    Get-ChildItem logs -File | Sort-Object LastWriteTime -Descending | Select-Object -First 5 | Format-Table Name, Length, LastWriteTime
} else {
    Write-Host "No logs directory" -ForegroundColor Yellow
}

Write-Host "`n=== Python Installation Check ===" -ForegroundColor Cyan
python -c "import sys; print(f'Python executable: {sys.executable}')"
python -c "import sys; print(f'Python version: {sys.version}')"

Write-Host "`n=== NumPy Check ===" -ForegroundColor Cyan
python -c "import numpy; print(f'NumPy version: {numpy.__version__}'); print(f'NumPy location: {numpy.__file__}')" 2>&1
if ($LASTEXITCODE -ne 0) {
    Write-Host "NumPy: Import failed - See Windows-Specific Issues section" -ForegroundColor Red
}
```

**Run the diagnostic:**
```powershell
.\diagnose.ps1 > diagnostic_report.txt
Get-Content diagnostic_report.txt
```

### Common Windows Commands Reference

| Task | Unix/Mac | Windows PowerShell | Windows CMD |
|------|----------|-------------------|-------------|
| List files | `ls -la` | `Get-ChildItem` or `ls` | `dir` |
| Change directory | `cd /path` | `cd C:\path` | `cd C:\path` |
| Create directory | `mkdir -p dir` | `New-Item -ItemType Directory -Force dir` | `mkdir dir` |
| Remove directory | `rm -rf dir` | `Remove-Item -Recurse -Force dir` | `rmdir /s /q dir` |
| View file | `cat file.txt` | `Get-Content file.txt` or `cat file.txt` | `type file.txt` |
| Find string | `grep pattern` | `Select-String pattern` | `findstr pattern` |
| Environment variable | `export VAR=value` | `$env:VAR="value"` | `set VAR=value` |
| Activate venv | `source .venv/bin/activate` | `.venv\Scripts\activate` | `.venv\Scripts\activate.bat` |

### Recommended Windows Setup

For the most reliable Windows experience:

1. **Install Python from python.org (not Microsoft Store)**
   - Download from [python.org/downloads](https://www.python.org/downloads/)
   - During installation, check "Add Python to PATH"

2. **Use PowerShell 7+ (not Windows PowerShell 5.1)**
   - Download from [GitHub](https://github.com/PowerShell/PowerShell/releases)
   - More Unix-like experience

3. **Use Python virtual environments directly instead of uv**
   ```text
   python -m venv .venv
   .venv\Scripts\activate
   pip install -e .
   ```

4. **Run the tool using Python directly**
   ```text
   cja_auto_sdr --version
   cja_auto_sdr dv_12345
   ```

---

## Debug Mode & Logging

### Log Levels

| Level | Flag | Description |
|-------|------|-------------|
| DEBUG | `--log-level DEBUG` | Detailed operation tracking |
| INFO | (default) | General progress information |
| WARNING | `--production` | Important notices only |
| ERROR | `--quiet` | Errors only |

### Enabling Debug Mode

```bash
# Maximum verbosity
uv run cja_auto_sdr dv_12345 --log-level DEBUG
```

**Debug mode shows:**
- Cache operations (hits, misses, expirations)
- Individual validation checks
- API call details
- Performance timing
- File operation failures (e.g., `--open` flag issues)

### Structured JSON Logging

For enterprise environments or automated log analysis, use JSON format:

```bash
# JSON structured logging for Splunk, ELK, CloudWatch
uv run cja_auto_sdr dv_12345 --log-format json

# Combine with debug level for maximum detail
uv run cja_auto_sdr dv_12345 --log-level DEBUG --log-format json
```

**JSON output format:**
```json
{"timestamp": "2026-01-23T15:11:50", "level": "INFO", "logger": "cja_auto_sdr.generator", "message": "Processing data view", "module": "generator", "function": "process_single_dataview", "line": 6683}
```

**Benefits:**
- Machine-parseable for automated analysis
- Easy filtering by level, module, or function
- Stack traces in `exception` field for errors
- Compatible with log aggregation systems

### Log File Locations

| Mode | Log File Pattern |
|------|------------------|
| Single data view | `logs/SDR_Generation_dv_{id}_{timestamp}.log` |
| Batch processing | `logs/SDR_Batch_Generation_{timestamp}.log` |

### Searching Logs

**macOS/Linux:**
```bash
# Find all errors
grep -i "error\|critical" logs/*.log

# Find warnings
grep -i warning logs/*.log

# Find specific data view
grep "dv_12345" logs/*.log

# Find rate limiting issues
grep -i "429\|rate limit\|retry" logs/*.log

# View latest log
cat logs/$(ls -t logs/ | head -1)
```

**Windows (PowerShell):**
```powershell
# Find all errors
Select-String -Path logs\*.log -Pattern "error|critical"

# Find warnings
Select-String -Path logs\*.log -Pattern "warning"

# Find specific data view
Select-String -Path logs\*.log -Pattern "dv_12345"

# Find rate limiting issues
Select-String -Path logs\*.log -Pattern "429|rate limit|retry"

# View latest log
Get-Content (Get-ChildItem logs\*.log | Sort-Object LastWriteTime -Descending | Select-Object -First 1)
```

---

## Common Error Messages Reference

### Configuration Errors

| Error Message | Cause | Solution |
|---------------|-------|----------|
| `Configuration file not found: {path}` | Config file missing | Run `--sample-config` |
| `Configuration file is not valid JSON: {error}` | Invalid JSON syntax | Check JSON formatting |
| `Configuration file must contain a JSON object` | Config is array, not object | Wrap in `{}` |
| `Missing required field: '{field}'` | Required field absent | Add field to config |
| `Empty value for required field: '{field}'` | Field is empty/whitespace | Provide value |
| `Invalid type for '{field}': expected {type}` | Wrong data type | Fix field type |
| `Unknown fields in config (possible typos)` | Unexpected fields | Check field names |

### API Errors

| Error Message | Cause | Solution |
|---------------|-------|----------|
| `API method 'getDataView' not available` | Outdated cjapy | Upgrade cjapy |
| `API call failed: {error}` | General API error | Check logs |
| `All {N} attempts failed for {operation}` | Retries exhausted | Check network/credentials |
| `HTTP 429: Too Many Requests` | Rate limited | Reduce workers, increase delays |
| `OAuth response missing required fields. Response: {...}` | OAuth authentication failed (v3.1.0+) | Check the response error - see [OAuth Token Retrieval Failed](#oauth-token-retrieval-failed-v310) |

### API Permission Errors

| Error Message | Cause | Solution |
|---------------|-------|----------|
| `403 Forbidden when accessing segments` | Missing AEP API for auth | Add AEP API to Developer Console project |
| `Failed to fetch calculated metrics` | Missing AEP API for auth | Add AEP API to Developer Console project |
| `Cannot access sandbox` | Sandbox permission denied | Add sandbox access to product profile |
| `Authentication failed: insufficient_scope` | Wrong OAuth scopes | Copy scopes exactly from Developer Console |
| `Permission denied for schema access` | Missing AEP API for auth | Add AEP API to Developer Console project |
| `Connection details are unavailable` | Technical account not a CJA Product Admin | Add technical account email as CJA Product Admin in Admin Console |
| `Showing connection IDs derived from data views` | Connections API returns empty (not a 403) | Add technical account as CJA Product Admin — see [Connections API Returns Empty Results](#connections-api-returns-empty-results) |

### Data View Errors

| Error Message | Cause | Solution |
|---------------|-------|----------|
| `Invalid data view ID format` | ID doesn't start with `dv_` | Use correct format |
| `Data view returned empty response` | Not found or no access | Use `--list-dataviews` |
| `No data views found` | No access to any data views | Check permissions |
| `Data view name '{name}' not found` | Name not found or no access | Check exact spelling (case-sensitive) |
| `Name matching is CASE-SENSITIVE` | Name case doesn't match | Copy exact name from `--list-dataviews` |
| `No valid data views found` (with names) | Name resolution failed | Check case, quotes, and exact match |

### Output Errors

| Error Message | Cause | Solution |
|---------------|-------|----------|
| `Permission denied writing to {path}` | File locked or no permissions | Close file, check permissions |
| `No metrics or dimensions fetched` | Empty data view | Check CJA configuration |
| `Cannot create output directory` | Permission issue | Create directory manually |

### CLI Argument Errors

| Error Message | Cause | Solution |
|---------------|-------|----------|
| `At least one data view ID is required` | No data view provided | Add data view ID |
| `--workers must be at least 1` | Invalid worker count | Use 1-256 |
| `--cache-size must be at least 1` | Invalid cache size | Use positive integer |
| `--cache-ttl must be at least 1 second` | Invalid TTL | Use positive integer |
| `--max-retries cannot be negative` | Invalid retry count | Use 0 or positive |
| `--retry-max-delay must be >= --retry-base-delay` | Invalid delay config | Ensure max >= base |

### Diff Comparison Errors

| Error Message | Cause | Solution |
|---------------|-------|----------|
| `Snapshot file not found: {path}` | Snapshot doesn't exist | Create snapshot first with `--snapshot` |
| `Invalid snapshot file` | File not valid snapshot JSON | Recreate snapshot or check file |
| `Ambiguous data view name` | Name matches multiple views | Use ID instead or be more specific |
| `Did you mean one of these?` | Name typo detected | Check spelling, use suggested name |
| `Diff requires exactly 2 data views` | Wrong number of args to `--diff` | Provide exactly 2 identifiers |
| `Cannot create snapshot directory` | Permission denied | Check directory permissions |
| `--format console` not supported for SDR | Console is diff-only | Use excel, csv, json, html, or markdown |

### Inventory Errors

| Error Message | Cause | Solution |
|---------------|-------|----------|
| `--include-segments cannot be used with --diff` | Inventory not supported for cross-DV diff | Use snapshot diff for same DV, or remove flag |
| `--inventory-only requires at least one of: --include-*` | No inventory type specified | Add `--include-segments`, `--include-derived`, `--include-calculated`, or `--include-all-inventory` |
| `--inventory-only is only available in SDR mode` | Inventory-only is SDR feature | Remove `--inventory-only` in diff mode |
| `--inventory-summary requires at least one of: --include-*` | No inventory type specified | Add an inventory flag or use `--include-all-inventory` |
| `No segments found for data view` | No segments in data view | Verify segments exist in CJA UI |
| `No derived fields found in data view` | No derived fields configured | Check data view settings |
| `No calculated metrics found for data view` | No calculated metrics | Verify metrics are associated with data view |

### Profile Errors

| Error Message | Cause | Solution |
|---------------|-------|----------|
| `Profile '{name}' not found` | Profile directory doesn't exist | Create with `--profile-add` |
| `Invalid profile name: '{name}'` | Name contains invalid characters | Use only letters, numbers, dashes, underscores |
| `Profile has invalid configuration` | Missing or invalid config.json | Check with `--profile-show` |
| `Profile failed connectivity test` | Invalid credentials | Verify credentials in Developer Console |
| `Permission denied accessing profile` | File permissions issue | Fix with `chmod 600` |
| `Missing required field in profile` | config.json incomplete | Add missing field to config.json |

---

## Getting Help

If you encounter issues not covered here:

1. **Enable debug logging:**
   ```bash
   uv run cja_auto_sdr dv_12345 --log-level DEBUG
   ```

2. **Check the log file** in `logs/` directory

3. **Run diagnostics:**
   ```bash
   ./diagnose.sh > diagnostic_report.txt
   ```

4. **Validate configuration:**
   ```bash
   uv run cja_auto_sdr --validate-config
   ```

5. **When reporting issues, include:**
   - Complete error message
   - Relevant log entries (anonymize credentials)
   - Python version: `python3 --version`
   - uv version: `uv --version`
   - cjapy version: `uv pip show cjapy`

---

## Org-Wide Analysis Issues

For detailed org-wide analysis troubleshooting, see the [Troubleshooting section](ORG_WIDE_ANALYSIS.md#troubleshooting) in the Org-Wide Analysis Guide.

### Common Issues

| Error | Cause | Solution |
|-------|-------|----------|
| "No data views found matching criteria" | Filter/exclude patterns too restrictive | Check regex patterns, run `--list-dataviews` to see available names |
| Some data views show ERROR | Permission denied for specific DVs | Check API credentials have access to those data views |
| Similarity matrix is slow | O(n²) calculation with many DVs | Use `--skip-similarity` or `--sample N` for large orgs |
| "scipy not available" with `--cluster` | Optional dependency not installed | Install with: `uv pip install 'cja-auto-sdr[clustering]'` |
| Cache not working | Cache directory permissions | Check `~/.cja_auto_sdr/cache/` (macOS/Linux) or `%USERPROFILE%\.cja_auto_sdr\cache\` (Windows) is writable |
| `--owner-summary` shows nothing | Missing metadata | Add `--include-metadata` flag |
| Exit code 2 unexpectedly in `--org-report` | Governance threshold exceeded | Check `--duplicate-threshold` and `--isolated-threshold` values |
| "Another --org-report is already running" | Concurrent run prevention | Wait for other run to finish, or check if a previous run crashed (lock auto-expires after 1 hour) |

### Clustering Issues

**"scipy not available - skipping clustering":**

scipy is an optional dependency for the `--cluster` feature. Install it with:
```bash
# macOS/Linux
uv pip install 'cja-auto-sdr[clustering]'
uv pip install 'cja-auto-sdr[full]'          # or install all extras

# Windows PowerShell (double quotes required)
uv pip install "cja-auto-sdr[clustering]"
uv pip install "cja-auto-sdr[full]"
```

Without scipy, the `--cluster` flag is silently skipped and a warning is logged.

**Cluster results seem incorrect:**
- Use `--cluster-method average` (default) for Jaccard distances
- The `complete` method is also valid and produces tighter clusters

### Caching Issues

**Cache not being used:**
```bash
# macOS/Linux: Verify cache exists
ls -la ~/.cja_auto_sdr/cache/org_report_cache.json

# Windows PowerShell: Verify cache exists
Get-Item "$env:USERPROFILE\.cja_auto_sdr\cache\org_report_cache.json"

# Force refresh and rebuild cache (all platforms)
cja_auto_sdr --org-report --use-cache --refresh-cache
```

**Cache too old:**
```bash
# Adjust cache max age (default: 24 hours)
cja_auto_sdr --org-report --use-cache --cache-max-age 48
```

### CI/CD Integration Issues

**Exit code 2 when expecting 0:**
- Check if `--fail-on-threshold` is enabled
- Verify `--duplicate-threshold` and `--isolated-threshold` values are appropriate
- Run without thresholds first to see actual values

```bash
# macOS/Linux: Debug with jq
cja_auto_sdr --org-report --format json --output - | jq '.summary'

# Windows PowerShell: Debug with ConvertFrom-Json
cja_auto_sdr --org-report --format json --output - | ConvertFrom-Json | Select-Object -ExpandProperty summary
```

### Performance Issues

**Analysis taking too long:**
```bash
# Quick options for large orgs:
cja_auto_sdr --org-report --skip-similarity --org-stats
cja_auto_sdr --org-report --sample 20 --sample-seed 42
cja_auto_sdr --org-report --use-cache  # Faster on repeat runs
```

---

## See Also

- [Configuration Guide](CONFIGURATION.md) - config.json, environment variables, validation rules
- [Installation Guide](INSTALLATION.md) - Setup instructions
- [CLI Reference](CLI_REFERENCE.md) - Complete command options
- [Data View Comparison Guide](DIFF_COMPARISON.md) - Diff, snapshots, and CI/CD integration
- [Org-Wide Analysis Guide](ORG_WIDE_ANALYSIS.md) - Cross-data-view component analysis
- [Segments Inventory](SEGMENTS_INVENTORY.md) - Segment filter inventory documentation
- [Derived Fields Inventory](DERIVED_FIELDS_INVENTORY.md) - Derived field inventory documentation
- [Calculated Metrics Inventory](CALCULATED_METRICS_INVENTORY.md) - Calculated metrics inventory documentation
- [Performance Guide](PERFORMANCE.md) - Optimization options
- [Data Quality Guide](DATA_QUALITY.md) - Understanding validation
- [Batch Processing Guide](BATCH_PROCESSING_GUIDE.md) - Multi-data view processing
- [Data View Names Guide](DATA_VIEW_NAMES.md) - Using data view names instead of IDs
