# Troubleshooting Guide

Comprehensive solutions for issues with the CJA SDR Generator.

## Table of Contents

- [Quick Diagnostics](#quick-diagnostics)
- [Exit Codes Reference](#exit-codes-reference)
- [Configuration Errors](#configuration-errors)
- [Authentication & Connection Errors](#authentication--connection-errors)
- [Data View Errors](#data-view-errors)
- [Diff Comparison & Snapshot Errors](#diff-comparison--snapshot-errors)
- [API & Network Errors](#api--network-errors)
- [Retry Mechanism & Rate Limiting](#retry-mechanism--rate-limiting)
- [Data Quality Issues](#data-quality-issues)
- [Output & File Errors](#output--file-errors)
- [Batch Processing Issues](#batch-processing-issues)
- [Validation Cache Issues](#validation-cache-issues)
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
python --version
uv --version
echo ""
echo "=== Project Dependencies ==="
uv pip list | grep -E "cjapy|pandas|openpyxl"
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
| `2` | Diff: Changes Found | Diff comparison succeeded but differences were detected |
| `3` | Diff: Threshold Exceeded | Changes exceeded `--warn-threshold` percentage |

**Diff-specific exit codes** are designed for CI/CD integration:

```bash
# Check exit code after diff
cja_auto_sdr --diff dv_12345 dv_67890 --quiet-diff
case $? in
  0) echo "No differences found" ;;
  1) echo "Error occurred" ;;
  2) echo "Differences detected (review needed)" ;;
  3) echo "Too many changes (threshold exceeded)" ;;
esac
```

---

## Configuration Errors

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
  "scopes": "openid, AdobeID, additional_info.projectedProductContext"
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
export SCOPES='openid, AdobeID, additional_info.projectedProductContext'
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
     "scopes": "openid, AdobeID, additional_info.projectedProductContext"
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

# Check logs for rate limiting
grep "429\|rate limit" logs/*.log
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

### Module Not Found

**Symptoms:**
```
ModuleNotFoundError: No module named 'cjapy'
ModuleNotFoundError: No module named 'pandas'
ModuleNotFoundError: No module named 'openpyxl'
```

**Solutions:**
```bash
# Sync all dependencies
uv sync

# Or reinstall everything
uv sync --reinstall

# Verify installation
uv pip list | grep -E "cjapy|pandas|openpyxl"
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
python cja_sdr_generator.py --version
python cja_sdr_generator.py dv_YOUR_DATA_VIEW_ID
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
pip install cjapy>=0.2.4.post2 pandas>=2.3.3 xlsxwriter>=3.2.9 tqdm>=4.66.0

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

```powershell
# Activate virtual environment first
.venv\Scripts\activate

# Then run commands without uv
cja_auto_sdr --version
cja_auto_sdr dv_12345

# Or run the script directly
python cja_sdr_generator.py --version
python cja_sdr_generator.py dv_12345
```

**Option 2: Use full Python path**

```powershell
# Without activating venv
.venv\Scripts\python.exe cja_sdr_generator.py --version
.venv\Scripts\python.exe cja_sdr_generator.py dv_12345
```

**Option 3: Fix uv PATH (if you prefer using uv)**

```powershell
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

```powershell
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
   ```powershell
   python cja_sdr_generator.py --version
   python cja_sdr_generator.py dv_12345
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

### Log File Locations

| Mode | Log File Pattern |
|------|------------------|
| Single data view | `logs/SDR_Generation_dv_{id}_{timestamp}.log` |
| Batch processing | `logs/SDR_Batch_Generation_{timestamp}.log` |

### Searching Logs

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
   - Python version: `python --version`
   - uv version: `uv --version`
   - cjapy version: `uv pip show cjapy`

---

## See Also

- [Installation Guide](INSTALLATION.md) - Setup instructions
- [CLI Reference](CLI_REFERENCE.md) - Complete command options
- [Data View Comparison Guide](DIFF_COMPARISON.md) - Diff, snapshots, and CI/CD integration
- [Performance Guide](PERFORMANCE.md) - Optimization options
- [Data Quality Guide](DATA_QUALITY.md) - Understanding validation
- [Batch Processing Guide](BATCH_PROCESSING_GUIDE.md) - Multi-data view processing
- [Data View Names Guide](DATA_VIEW_NAMES.md) - Using data view names instead of IDs
