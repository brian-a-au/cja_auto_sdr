# Release Notes: v3.0.9

**Release Date:** January 15, 2026

## 🎯 What's New

Version 3.0.9 introduces two major improvements focused on **documentation workflows** and **user experience**:

1. **Markdown Output Format** - Export SDRs as GitHub/Confluence-compatible markdown
2. **Enhanced Error Messages** - Get actionable guidance when things go wrong

## ✨ Key Features

### 📝 Markdown Output Format

Export your CJA Solution Design Reference as markdown for seamless integration with documentation platforms.

```bash
# Export as markdown
cja_auto_sdr dv_12345 --format markdown

# Generate all formats including markdown
cja_auto_sdr dv_12345 --format all
```

**Features:**
- ✅ GitHub-flavored markdown tables with proper formatting
- ✅ Auto-generated table of contents with anchor links
- ✅ Collapsible sections for large tables (>50 rows)
- ✅ Special character escaping (pipes, backticks, etc.)
- ✅ Visual issue summary with emoji severity indicators
  - 🔴 CRITICAL
  - 🟠 HIGH
  - 🟡 MEDIUM
  - ⚪ LOW
  - 🔵 INFO
- ✅ Full Unicode support for international characters
- ✅ Version control friendly (perfect for Git)

**Use Cases:**
- Paste directly into GitHub README files, issues, or wiki pages
- Copy to Confluence pages for team documentation
- Track SDR changes over time in version control
- Lightweight alternative to Excel/HTML for documentation workflows

**Example Output:**
```markdown
# 📊 CJA Solution Design Reference

## 📑 Table of Contents
- [Metrics](#metrics)
- [Dimensions](#dimensions)
- [Data Quality](#data-quality)

## Metrics
| name | type | id | description |
| --- | --- | --- | --- |
| Page Views | metric | metrics/pageviews | Count of page views |

*Total Metrics: 25 items*

## Data Quality
### Issue Summary
| Severity | Count |
| --- | --- |
| 🔴 CRITICAL | 0 |
| 🟠 HIGH | 2 |
| 🟡 MEDIUM | 5 |

<details>
<summary>View 100 rows (click to expand)</summary>
[Large tables automatically collapse for better readability]
</details>
```

### 🛠️ Enhanced Error Messages

Get contextual, actionable error messages that help you fix problems quickly.

**Before:**
```
Error: HTTP 401
Troubleshooting: Check network connectivity, verify API credentials, or try again later
```

**After:**
```
============================================================
HTTP 401: Authentication Failed
============================================================
Operation: getDataViews

Why this happened:
  Your credentials are invalid or have expired

How to fix it:
  1. Verify CLIENT_ID and SECRET in myconfig.json or environment variables
  2. Check that your ORG_ID ends with '@AdobeOrg'
  3. Ensure SCOPES includes: 'openid, AdobeID, additional_info.projectedProductContext'
  4. Regenerate credentials at https://developer.adobe.com/console/
  5. See authentication setup: docs/QUICKSTART_GUIDE.md#configure-credentials

For more help: docs/TROUBLESHOOTING.md
```

**Coverage:**
- ✅ **HTTP Errors:** 400, 401, 403, 404, 429, 500, 502, 503, 504
- ✅ **Network Errors:** ConnectionError, TimeoutError, SSLError, ConnectionResetError
- ✅ **Configuration Errors:** File not found, invalid JSON, missing credentials, invalid format
- ✅ **Data View Errors:** Not found with list of available data views

**Benefits:**
- Self-service troubleshooting reduces support burden
- Direct links to relevant documentation
- Multi-level suggestions (3-10 actionable steps)
- Context-aware messages include operation name

## 📊 Statistics

- **33 New Tests** (21 error message + 12 markdown output)
- **Total Test Count:** 262 (increased from 229)
- **Test Coverage:** 100% of new functionality
- **All Tests Passing:** ✅

## 🔄 Breaking Changes

None. This release is fully backward compatible with v3.0.8.

## 🐛 Bug Fixes

None. This is a feature-focused release.

## 📚 Documentation Updates

All documentation has been updated to reflect the new features:

- ✅ **README.md** - Added markdown format to key features and common use cases
- ✅ **CHANGELOG.md** - Comprehensive documentation of all changes
- ✅ **CLI_REFERENCE.md** - Added markdown format examples
- ✅ **tests/README.md** - Documented new test coverage

## 🚀 Upgrade Guide

### From v3.0.8 to v3.0.9

No action required. Simply update to the latest version:

```bash
cd cja_auto_sdr
git pull origin main
uv sync
```

All existing commands and configurations continue to work without modification.

### New Features Available Immediately

After updating, you can start using the new features:

```bash
# Export as markdown
cja_auto_sdr dv_12345 --format markdown

# Error messages are automatically enhanced (no config needed)
```

## 💡 Usage Examples

### Markdown for Documentation Workflows

```bash
# Generate markdown for GitHub wiki
cja_auto_sdr dv_production --format markdown --output-dir ./docs/sdr

# Generate all formats including markdown
cja_auto_sdr dv_12345 --format all

# Track changes in Git
git diff SDR_MyDataView_*.md
```

### Error Message Examples

When errors occur, you'll automatically get enhanced guidance:

**Config File Not Found:**
```
============================================================
Configuration File Not Found
============================================================
Details: Looking for: /path/to/myconfig.json

Why this happened:
  The myconfig.json file does not exist

How to fix it:
  1. Create a configuration file:
    Option 1: cja_auto_sdr --sample-config
    Option 2: cp .myconfig.json.example myconfig.json

  2. Or use environment variables instead:
    export ORG_ID='your_org_id@AdobeOrg'
    export CLIENT_ID='your_client_id'
    export SECRET='your_client_secret'
```

**Data View Not Found:**
```
============================================================
Data View Not Found
============================================================
Requested Data View: dv_invalid_id

You have access to 5 data view(s):
  1. Production Data View (ID: dv_prod_12345)
  2. Staging Data View (ID: dv_staging_67890)
  3. Development Data View (ID: dv_dev_abcde)

How to fix it:
  1. Check for typos in the data view ID
  2. Verify the ID format (should start with 'dv_')
  3. List available data views:
       cja_auto_sdr --list-dataviews
```

## 🙏 Credits

Special thanks to the Adobe CJA team for their continued support and feedback on error messaging improvements.

## 📞 Support

- **Documentation:** [docs/](docs/)
- **Issues:** [GitHub Issues](https://github.com/your-org/cja_auto_sdr/issues)
- **Troubleshooting:** [docs/TROUBLESHOOTING.md](docs/TROUBLESHOOTING.md)

## 🔗 Full Changelog

See [CHANGELOG.md](CHANGELOG.md) for complete version history and detailed changes.

---

**Previous Release:** [v3.0.8](https://github.com/your-org/cja_auto_sdr/releases/tag/v3.0.8) - Console script entry points and environment variable support

**Next Planned Features:** Stay tuned for future releases!
- Quality score/grade calculation
- `--diff` mode for comparing SDR reports
- `--diagnose` command for automated troubleshooting
