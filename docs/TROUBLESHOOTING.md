# Troubleshooting Guide

Solutions for common issues with the CJA SDR Generator.

## Quick Diagnostics

Run this script to gather system information:

```bash
#!/bin/bash
echo "=== System Information ==="
python --version
uv --version
echo ""
echo "=== Project Dependencies ==="
uv pip list
echo ""
echo "=== Recent Logs ==="
ls -lh logs/ | tail -5
```

Save as `diagnose.sh` and run:
```bash
chmod +x diagnose.sh
./diagnose.sh > diagnostic_report.txt
```

## Connection Errors

### Cannot Connect to CJA API

**Symptoms:**
```
CRITICAL - CJA INITIALIZATION FAILED
CRITICAL - Failed to initialize CJA connection: Authentication failed
```

**Possible Causes:**
- Invalid credentials in `myconfig.json`
- Network connectivity issues
- Adobe service outage
- Expired authentication tokens

**Solutions:**
1. Verify all fields in `myconfig.json` are correct
2. Check network connectivity: `ping adobe.io`
3. Confirm private key file exists and is readable
4. Check [Adobe Status](https://status.adobe.com) for service issues
5. Regenerate credentials in Adobe I/O Console

### Authentication Fails with Valid Credentials

**Possible Causes:**
- Incorrect organization ID
- Private key doesn't match integration
- Insufficient API permissions
- Integration not enabled for CJA

**Solutions:**
1. Verify `org_id` matches Adobe I/O Console exactly
2. Re-download private key from integration
3. Check integration has "Customer Journey Analytics" API enabled
4. Verify product profile includes CJA access

## Data View Errors

### Data View Not Found

**Symptoms:**
```
ERROR - Data view 'dv_12345' returned empty response
INFO - You have access to 5 data view(s):
INFO -   1. Production Analytics (ID: dv_abc123)
```

**Solutions:**
1. Copy the correct data view ID from the log output
2. Verify you have access permissions to the data view
3. Use `--list-dataviews` to see available data views:
   ```bash
   uv run python cja_sdr_generator.py --list-dataviews
   ```
4. Check with admin if you need access granted

### Invalid Data View ID Format

**Symptoms:**
```
Invalid data view ID format: invalid_id, test123
```

**Solution:**
Data view IDs must start with `dv_`:
```bash
# Wrong
uv run python cja_sdr_generator.py 12345

# Correct
uv run python cja_sdr_generator.py dv_12345
```

## CLI Argument Errors

### Missing Data View ID

**Symptoms:**
```
error: the following arguments are required: DATA_VIEW_ID
```

**Solution:**
Provide at least one data view ID:
```bash
uv run python cja_sdr_generator.py dv_12345

# For help
uv run python cja_sdr_generator.py --help
```

### Unknown Argument

**Solution:**
Check available options:
```bash
uv run python cja_sdr_generator.py --help
```

## Dependency Issues

### Module Not Found

**Symptoms:**
```
ModuleNotFoundError: No module named 'cjapy'
```

**Solutions:**
```bash
# Sync dependencies
uv sync

# Or reinstall everything
uv sync --reinstall

# Verify installation
uv pip list | grep cjapy
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

## Virtual Environment Issues

### Wrong Python Version

**Solution:**
```bash
# Remove and recreate
rm -rf .venv
uv venv --python 3.14
uv sync
```

### Packages Not Available

**Solution:**
```bash
# Ensure using project's venv
source .venv/bin/activate  # macOS/Linux
.venv\Scripts\activate     # Windows

# Or use uv run (handles venv automatically)
uv run python cja_sdr_generator.py dv_12345
```

## File Errors

### Permission Denied

**Symptoms:**
```
PermissionError: [Errno 13] Permission denied: 'output.xlsx'
```

**Cause:** Output file is open in Excel or locked

**Solution:** Close the Excel file and re-run

### Output Directory Not Found

**Solution:**
```bash
# Create directory first
mkdir -p ./reports

# Then run
uv run python cja_sdr_generator.py dv_12345 --output-dir ./reports
```

### Empty Output File

**Possible Causes:**
- Data view has no components configured
- API permissions don't include read access

**Solutions:**
1. Check log file for: "No metrics returned from API"
2. Verify data view has components in CJA UI
3. Check API permissions include read access
4. Try a different data view

## Batch Processing Issues

### Slower Than Expected

**Possible Causes:**
- Too many workers causing API rate limiting
- Network bottleneck

**Solutions:**
```bash
# Reduce workers
uv run python cja_sdr_generator.py --batch dv_* --workers 2

# Check logs for rate limiting
grep "rate limit" logs/*.log
```

### Some Data Views Fail

**Solution:**
Use `--continue-on-error`:
```bash
uv run python cja_sdr_generator.py --batch dv_1 dv_2 dv_3 --continue-on-error
```

Check batch summary to see which failed and why.

## Performance Issues

### Slow Processing

**Normal Duration:** 30-60 seconds for typical data view

**If Slower:**
- Large data views (200+ components) take longer
- Network latency affects API calls
- Check log file for which operation is slow

**Solutions:**
```bash
# Skip validation if not needed
uv run python cja_sdr_generator.py dv_12345 --skip-validation

# Use production mode
uv run python cja_sdr_generator.py dv_12345 --production

# Check network latency
ping adobe.io
```

## Configuration Validation

### Validate Config Without Running

```bash
uv run python cja_sdr_generator.py dv_12345 --dry-run
```

### Check JSON Syntax

```bash
python -c "import json; json.load(open('myconfig.json'))"
```

### Generate Sample Config

```bash
uv run python cja_sdr_generator.py --sample-config
```

## Log File Analysis

### Finding Log Files

```bash
# List recent logs
ls -lt logs/ | head -10

# View latest log
cat logs/$(ls -t logs/ | head -1)
```

### Searching Logs

```bash
# Find errors
grep -i error logs/*.log

# Find warnings
grep -i warning logs/*.log

# Find specific data view
grep "dv_12345" logs/*.log
```

## Common Error Solutions Summary

| Error | Solution |
|-------|----------|
| `ModuleNotFoundError` | `uv sync --reinstall` |
| `uv: command not found` | Install uv, then `uv sync` |
| `Python version mismatch` | `rm -rf .venv && uv venv --python 3.14 && uv sync` |
| `Permission denied` | Close Excel file |
| `Authentication failed` | Verify `myconfig.json` credentials |
| `Data view not found` | Use `--list-dataviews` to find correct ID |
| `Invalid data view ID` | IDs must start with `dv_` |

## Getting Help

If you encounter issues not covered here:

1. Check the log file in `logs/` directory
2. Review the Data Quality sheet for configuration issues
3. Run diagnostic script and save output
4. Include when reporting:
   - Complete error message
   - Relevant log entries
   - Python version: `python --version`
   - uv version: `uv --version`
   - Anonymized configuration

## See Also

- [Installation Guide](INSTALLATION.md) - Setup instructions
- [CLI Reference](CLI_REFERENCE.md) - Command options
- [Performance Guide](PERFORMANCE.md) - Optimization options
