# v3.0.9 - Markdown Export & Enhanced Error Messages

**🎯 What's New in 3.0.9:**

- **Markdown Output Format** - Export SDRs as GitHub/Confluence-compatible markdown with tables, TOC, and collapsible sections
- **Enhanced Error Messages** - Contextual, actionable error messages with step-by-step fix guidance and documentation links
- **33 New Tests** - Comprehensive test coverage for both features (262 total tests)

This release focuses on improving **documentation workflows** (markdown export) and **user experience** (helpful error messages).

---

## 📝 Markdown Output Format

Export your CJA Solution Design Reference as markdown for seamless integration with documentation platforms.

```bash
cja_auto_sdr dv_12345 --format markdown
```

### Features

- ✅ GitHub-flavored markdown tables
- ✅ Auto-generated table of contents with anchor links
- ✅ Collapsible sections for large tables (>50 rows)
- ✅ Visual issue summary: 🔴 CRITICAL, 🟠 HIGH, 🟡 MEDIUM, ⚪ LOW, 🔵 INFO
- ✅ Full Unicode support
- ✅ Version control friendly

### Use Cases

- Paste directly into GitHub README, issues, or wiki pages
- Copy to Confluence pages for team documentation
- Track SDR changes over time in Git
- Lightweight alternative to Excel/HTML

---

## 🛠️ Enhanced Error Messages

Get contextual, actionable guidance when errors occur.

### Before vs After

**Before:**

```text
Error: HTTP 401
Troubleshooting: Check network connectivity, verify API credentials
```

**After:**

```text
============================================================
HTTP 401: Authentication Failed
============================================================
Operation: getDataViews

Why this happened:
  Your credentials are invalid or have expired

How to fix it:
  1. Verify CLIENT_ID and SECRET in myconfig.json
  2. Check that your ORG_ID ends with '@AdobeOrg'
  3. Ensure SCOPES includes: 'openid, AdobeID, additional_info.projectedProductContext'
  4. Regenerate credentials at https://developer.adobe.com/console/
  5. See authentication setup: docs/QUICKSTART_GUIDE.md

For more help: docs/TROUBLESHOOTING.md
```

### Coverage

- **HTTP Errors:** 400, 401, 403, 404, 429, 500, 502, 503, 504
- **Network Errors:** ConnectionError, TimeoutError, SSLError
- **Config Errors:** File not found, invalid JSON, missing credentials
- **Data View Errors:** Not found with list of available alternatives

---

## 📊 By the Numbers

- **33 New Tests** (21 error messages + 12 markdown output)
- **262 Total Tests** (100% passing)
- **0 Breaking Changes** (fully backward compatible)

---

## 🚀 Quick Start

### Update to v3.0.9

```bash
cd cja_auto_sdr
git pull origin main
uv sync
```

### Try the New Features

```bash
# Export as markdown
cja_auto_sdr dv_12345 --format markdown

# Generate all formats including markdown
cja_auto_sdr dv_12345 --format all

# Enhanced error messages work automatically (no config needed)
```

---

## 📚 Documentation

All documentation has been updated:

- ✅ README.md
- ✅ CHANGELOG.md
- ✅ CLI_REFERENCE.md
- ✅ tests/README.md

---

## 🔗 Resources

- **Full Changelog:** [CHANGELOG.md](https://github.com/your-org/cja_auto_sdr/blob/main/CHANGELOG.md)
- **Documentation:** [docs/](https://github.com/your-org/cja_auto_sdr/tree/main/docs)
- **Troubleshooting:** [TROUBLESHOOTING.md](https://github.com/your-org/cja_auto_sdr/blob/main/docs/TROUBLESHOOTING.md)

---

## ⬇️ Installation

### New Installation

```bash
git clone https://github.com/your-org/cja_auto_sdr.git
cd cja_auto_sdr
uv sync
```

### Upgrade from v3.0.8

```bash
cd cja_auto_sdr
git pull origin main
uv sync
```

No configuration changes required!

---

## 🙏 What's Next

Have feedback or feature requests? [Open an issue](https://github.com/your-org/cja_auto_sdr/issues)!

Planned for future releases:

- Quality score/grade calculation
- `--diff` mode for comparing SDR reports
- `--diagnose` command for automated troubleshooting
