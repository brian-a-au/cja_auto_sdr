# Changelog

All notable changes to the CJA SDR Generator project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [3.0.10] - 2026-01-18

### Highlights
- **Data View Diff Comparison (New)** - Compare data views to identify added, removed, and modified components with 20+ CLI options
- **Snapshot-to-Snapshot Comparison** - Compare two snapshot files directly without API calls
- **Auto-Snapshot on Diff** - Automatically save timestamped snapshots during diff comparisons for audit trails
- **Smart Name Resolution** - Fuzzy matching suggestions for typos, interactive disambiguation for duplicates
- **UX Quick Wins** - `--open` flag, `--stats` mode, `--output -` for stdout, machine-readable `--list-dataviews`
- **Comprehensive Type Hints** - Full type annotations for improved IDE support and static analysis
- **Configuration Dataclasses** - Centralized, testable configuration with `SDRConfig`, `RetryConfig`, `CacheConfig`, `LogConfig`, `WorkerConfig`
- **Custom Exception Hierarchy** - Better error handling with `CJASDRError`, `ConfigurationError`, `APIError`, `ValidationError`, `OutputError`
- **OutputWriter Protocol** - Standardized interface for output format writers
- **Expanded Test Coverage** - 623 total tests (+210 new: 139 diff comparison + 39 edge cases + 5 format validation + 27 UX features)

This release introduces the **Data View Diff Comparison** feature for change tracking and CI/CD integration, **Auto-Snapshot** for automatic audit trails, **UX Quick Wins** for better developer experience, plus **code maintainability** improvements (type hints, centralized configuration) and **developer experience** enhancements (better exceptions, standardized interfaces) while maintaining full backward compatibility.

### Added

#### Auto-Snapshot on Diff (New Feature)
Automatically save timestamped snapshots during diff comparisons—no extra commands needed.

- **`--auto-snapshot`**: Enable automatic snapshot saving during `--diff` or `--diff-snapshot` operations
- **`--snapshot-dir DIR`**: Directory for auto-saved snapshots (default: `./snapshots`)
- **`--keep-last N`**: Retention policy to keep only the last N snapshots per data view (0 = keep all)
- **Timestamped Filenames**: Snapshots saved with format `DataViewName_dv_id_YYYYMMDD_HHMMSS.json`
- **Audit Trail**: Every comparison automatically documents the "before" state
- **CI/CD Friendly**: Scheduled diffs build history automatically without manual intervention
- **Zero Friction**: Transparent operation—just add `--auto-snapshot` to existing commands

**Usage Examples:**
```bash
# Auto-save snapshots during diff comparison
cja_auto_sdr --diff dv_A dv_B --auto-snapshot

# Custom snapshot directory
cja_auto_sdr --diff dv_A dv_B --auto-snapshot --snapshot-dir ./history

# With retention policy (keep last 10 per data view)
cja_auto_sdr --diff dv_A dv_B --auto-snapshot --keep-last 10

# Works with diff-snapshot too (saves current state)
cja_auto_sdr dv_123 --diff-snapshot baseline.json --auto-snapshot
```

**New SnapshotManager Methods:**
- `generate_snapshot_filename()`: Creates timestamped, sanitized filenames
- `apply_retention_policy()`: Deletes old snapshots beyond retention limit

**16 New Tests** for auto-snapshot functionality:
- Filename generation (4 tests): with/without name, special chars, truncation
- Retention policy (5 tests): keep all, delete old, per-data-view, empty/nonexistent dirs
- CLI arguments (7 tests): defaults, custom values, all flags together

#### UX Quick Wins (Developer Experience)
Four new features to improve daily workflows and scripting integration.

##### Auto-Open Generated Files (`--open`)
Open generated SDR files automatically in the default application after creation.

- **Cross-Platform Support**: Works on macOS (`open`), Linux (`xdg-open`), and Windows (`os.startfile`)
- **Batch Mode Support**: Opens all successfully generated files when processing multiple data views
- **Graceful Fallback**: HTML files fall back to `webbrowser` module if system commands fail

```bash
# Generate SDR and open immediately
cja_auto_sdr dv_12345 --open

# Batch processing - opens all successful files
cja_auto_sdr dv_1 dv_2 dv_3 --open
```

##### Stdout Output for Piping (`--output -`)
Write JSON or CSV output directly to stdout for Unix-style piping and scripting.

- **`--output -`** or **`--output stdout`**: Write to standard output instead of a file
- **Implicit Quiet Mode**: Automatically suppresses decorative output when writing to stdout
- **Pipeline Friendly**: Enables `cja_auto_sdr ... | jq ...` workflows

```bash
# Pipe data view list to jq for processing
cja_auto_sdr --list-dataviews --output - | jq '.dataViews[].id'

# Get stats as JSON to stdout
cja_auto_sdr dv_12345 --stats --output -

# CSV output for spreadsheet import
cja_auto_sdr --list-dataviews --format csv --output - > dataviews.csv
```

##### Quick Statistics Mode (`--stats`)
Get quick metrics and dimension counts without generating full SDR reports.

- **Fast Overview**: Shows metrics count, dimensions count, and totals for each data view
- **Multiple Data Views**: Process multiple data views in one command with aggregated totals
- **Multiple Formats**: Table (default), JSON, or CSV output

```bash
# Quick stats for a single data view
cja_auto_sdr dv_12345 --stats

# Stats for multiple data views with JSON output
cja_auto_sdr dv_1 dv_2 dv_3 --stats --format json
```

##### Machine-Readable `--list-dataviews`
Enhanced `--list-dataviews` with JSON and CSV output formats for scripting.

- **`--format json`**: Output data views as JSON with `dataViews` array and `count`
- **`--format csv`**: Output as CSV with `id,name,owner` columns
- **Stdout Support**: Use `--output -` to pipe to other tools

```bash
# JSON output for scripting
cja_auto_sdr --list-dataviews --format json

# JSON to stdout for piping
cja_auto_sdr --list-dataviews --output - | jq '.dataViews[] | select(.name | contains("Prod"))'
```

**27 New Tests** for UX features in `tests/test_ux_features.py`:
- `--open` flag registration and cross-platform behavior (7 tests)
- `--output` argument handling (3 tests)
- `--stats` mode CLI parsing (5 tests)
- `--list-dataviews` format options (3 tests)
- `show_stats()` function with JSON/CSV/table output (3 tests)
- `list_dataviews()` function with JSON/CSV output (3 tests)
- Combined feature usage (3 tests)

#### Comprehensive Type Hints
- **Function Signatures**: All key functions now have complete type annotations
- **Return Types**: Explicit return types for better IDE autocompletion
- **Complex Types**: Uses `typing` module for `Optional`, `Union`, `List`, `Dict`, `Callable`, `TypeVar`
- **Path Types**: `Union[str, Path]` for flexible path handling
- **Benefits**:
  - Better IDE support (autocompletion, type checking)
  - Catch bugs at development time
  - Self-documenting code

#### Configuration Dataclasses
- **`RetryConfig`**: Retry settings (max_retries, base_delay, max_delay, exponential_base, jitter) with `to_dict()` method
- **`CacheConfig`**: Cache settings (enabled, max_size, ttl_seconds)
- **`LogConfig`**: Logging settings (level, file_max_bytes, file_backup_count)
- **`WorkerConfig`**: Worker settings (api_fetch_workers, validation_workers, batch_workers, max_batch_workers)
- **`SDRConfig`**: Master configuration combining all above with `from_args()` factory method
- **Default Instances**: `DEFAULT_RETRY`, `DEFAULT_CACHE`, `DEFAULT_LOG`, `DEFAULT_WORKERS` for easy access
- **Benefits**:
  - Single source of truth for configuration
  - Easy to pass configuration around
  - Testable configuration
  - Self-documenting with dataclass field defaults

#### Custom Exception Hierarchy
- **`CJASDRError`**: Base exception for all SDR errors with message and details
- **`ConfigurationError`**: Invalid config, missing credentials (includes config_file, field context)
- **`APIError`**: API communication failures (includes status_code, operation, original_error)
- **`ValidationError`**: Data quality validation failures (includes item_type, issue_count)
- **`OutputError`**: File writing failures (includes output_path, output_format, original_error)
- **Benefits**:
  - Catch specific error types for targeted handling
  - Better error messages with context
  - Cleaner exception handling code

#### OutputWriter Protocol
- **`OutputWriter`**: Runtime-checkable Protocol defining the interface for output format writers
- **Standard Interface**: `write(metrics_df, dimensions_df, dataview_info, output_path, quality_results) -> str`
- **Benefits**:
  - Easy to add new output formats
  - Improved testability with mock writers
  - Clear contract for writer implementations

#### Data View Diff Comparison (New Feature)

Compare two data views or track changes over time with snapshots. This feature is entirely new in v3.0.10.

**Core Functionality:**
- **`--diff`**: Compare two live data views side-by-side
- **`--snapshot`**: Save a data view state to JSON for later comparison
- **`--diff-snapshot`**: Compare current data view against a saved snapshot
- **`--compare-snapshots A B`**: Compare two snapshot files directly without API calls (offline analysis)
- **Identified Changes**: Added, removed, and modified metrics/dimensions with field-level details
- **Multiple Output Formats**: Console (default), JSON, HTML, Markdown, Excel, CSV
- **CI/CD Integration**: Exit code 2 when differences found, exit code 3 when threshold exceeded

**Smart Name Resolution:**
- **Fuzzy Name Matching**: Suggests similar data view names when exact match not found (Levenshtein distance)
- **Interactive Disambiguation**: Prompts user to select when name matches multiple data views (TTY mode only)
- **API Response Caching**: 5-minute TTL cache for data view listings reduces API calls

**Display Options:**
- **ANSI Color-Coded Diff Output**: Green for added `[+]`, red for removed `[-]`, yellow for modified `[~]`; use `--no-color` to disable
- **Percentage Stats**: Shows change percentage for metrics and dimensions (e.g., "10.5% changed")
- **Natural Language Summary**: Copy-paste friendly (e.g., "Metrics: 3 added, 2 removed; Dimensions: 1 modified")
- **Side-by-Side View**: `--side-by-side` flag for visual comparison in console and markdown
- **`--changes-only`**: Hide unchanged items, show only differences
- **`--summary`**: Show summary statistics only

**Filtering Options:**
- **`--show-only TYPES`**: Filter by change type (added, removed, modified)
- **`--metrics-only`**: Compare only metrics
- **`--dimensions-only`**: Compare only dimensions
- **`--ignore-fields FIELDS`**: Exclude specific fields from comparison
- **`--extended-fields`**: Include 20+ additional fields (attribution, bucketing, persistence, etc.)

**Advanced Options:**
- **`--quiet-diff`**: Suppress all output, return only exit code (0=no changes, 2=changes, 3=threshold exceeded)
- **`--reverse-diff`**: Swap source and target without reordering arguments
- **`--warn-threshold PERCENT`**: Exit with code 3 if change percentage exceeds threshold
- **Breaking Change Detection**: Automatically flags type/schemaPath changes and component removals
- **`--group-by-field`**: Group changes by field name instead of component
- **`--diff-output FILE`**: Write output directly to file instead of stdout
- **`--format-pr-comment`**: GitHub/GitLab PR comment format with collapsible details
- **`--diff-labels A B`**: Custom labels for source and target

**Extended Field Comparison**: `--extended-fields` flag to compare 20+ additional fields:
  - Attribution: `attribution`, `attributionModel`, `lookbackWindow`
  - Formatting: `format`, `precision`
  - Visibility: `hidden`, `hideFromReporting`
  - Bucketing: `bucketing`, `bucketingSetting`
  - Persistence: `persistence`, `persistenceSetting`, `allocation`
  - Calculated: `formula`, `isCalculated`, `derivedFieldId`
  - Other: `segmentable`, `reportable`, `componentType`, `dataType`, `hasData`, `approved`
- **Filter by Change Type**: `--show-only` flag to filter results (added, removed, modified)
- **Filter by Component Type**: `--metrics-only` and `--dimensions-only` flags
- **Side-by-Side View**: `--side-by-side` flag for visual comparison in console and markdown
- **New CLI Arguments**:
  - `--show-only TYPES` - Filter by change type (comma-separated)
  - `--metrics-only` - Compare only metrics
  - `--dimensions-only` - Compare only dimensions
  - `--extended-fields` - Use extended field comparison
  - `--side-by-side` - Show side-by-side comparison view
  - `--compare-snapshots A B` - Compare two snapshot files directly (no API calls)

#### Edge Case Tests
- **39 New Tests** in `tests/test_edge_cases.py`:
  - Custom exception hierarchy (9 tests)
  - Configuration dataclasses (9 tests)
  - Default configuration instances (5 tests)
  - OutputWriter Protocol (3 tests)
  - Retry edge cases (3 tests)
  - Empty DataFrame handling (3 tests)
  - Cache edge cases (3 tests)
  - DataFrame column handling (2 tests)
  - Concurrent access edge cases (1 test)

#### Diff Comparison Tests (New)
- **123 New Tests** in `tests/test_diff_comparison.py`:
  - Core comparison logic (12 tests)
  - DiffSummary dataclass (8 tests)
  - Console output formatting (6 tests)
  - JSON/HTML/Markdown output (9 tests)
  - Snapshot save/load (5 tests)
  - CLI argument parsing (12 tests)
  - Extended field comparison (3 tests)
  - Show-only filter (3 tests)
  - Metrics-only and dimensions-only (2 tests)
  - Side-by-side output (3 tests)
  - Large dataset performance (3 tests)
  - Unicode edge cases (4 tests)
  - Deeply nested structures (3 tests)
  - Concurrent comparison thread safety (1 test)
  - Snapshot version migration (3 tests)
  - Percentage stats (5 tests)
  - Colored console output (2 tests)
  - Group-by-field output (1 test)
  - PR comment output (2 tests)
  - Breaking change detection (3 tests)
  - New CLI flags (7 tests)
  - Ambiguous name resolution (6 tests)
  - Levenshtein distance algorithm (4 tests)
  - Fuzzy name matching (5 tests)
  - Data view cache (4 tests)
  - Snapshot-to-snapshot comparison (4 tests)
  - Interactive selection prompts (4 tests)
  - New feature CLI arguments (2 tests)
- **5 New Tests** for format validation in `tests/test_cli.py`:
  - Console format for diff mode
  - Console format parsing for SDR (runtime validation)
  - Excel/JSON/all format validation
- **16 New Tests** for auto-snapshot functionality:
  - Filename generation tests (4 tests)
  - Retention policy tests (5 tests)
  - CLI argument parsing tests (7 tests)
- **Total Test Count**: 413 (v3.0.9) → 623 (v3.0.10) = +210 tests (100% pass rate)

### Fixed

#### Diff Comparison NaN Handling
- **False Positive Fix**: Components with identical null/NaN values no longer incorrectly flagged as "modified"
- **Proper NaN Detection**: Added `pd.isna()` check in value normalization to treat NaN same as null/empty
- **Clearer Display**: Empty/null/NaN values now display as `(empty)` instead of `nan` in diff output
- **Consistent Formatting**: Applied across console, markdown, side-by-side, and breaking changes output

#### Ambiguous Name Resolution in Diff Mode
- **Separate Resolution**: Source and target identifiers are now resolved independently for diff operations
- **Exact Match Validation**: Diff operations (`--diff`, `--snapshot`, `--diff-snapshot`) now require exactly one data view match per identifier
- Previously, both identifiers were combined and resolved together, which could lead to incorrect comparisons when data view names matched multiple entries

### Changed
- **DEFAULT_RETRY_CONFIG**: Now uses `DEFAULT_RETRY.to_dict()` for backward compatibility
- **Type Annotations**: Added to all writer functions, core processing functions, retry functions
- **Import Section**: Extended to include `TypeVar`, `Protocol`, `runtime_checkable`, `field`
- **Format Validation**: `--format console` now shows clear error for SDR generation (console is diff-only)

### Backward Compatibility
- **Full Backward Compatibility**: All existing code continues to work unchanged
- **No Breaking Changes**: All 623 tests pass
- **DEFAULT_RETRY_CONFIG Dict**: Still available as a dict for legacy code
- **Configuration Migration**: Existing configurations work without changes

---

## [3.0.9] - 2026-01-16

### Highlights
- **Data View Names** - Use human-readable names instead of IDs (e.g., `"Production Analytics"` vs `dv_12345`)
- **Shell Tab-Completion** - Optional bash/zsh tab-completion for all CLI flags and values via argcomplete
- **Windows Support Improvements** - Comprehensive Windows-specific documentation and troubleshooting
- **Config File Rename** - Clearer naming: `config.json` instead of `myconfig.json`
- **Markdown Output Format** - Export SDRs as GitHub/Confluence-compatible markdown with tables, TOC, and collapsible sections
- **Enhanced Error Messages** - Contextual, actionable error messages with step-by-step fix guidance and documentation links
- **Comprehensive Test Coverage** - 413 total tests covering all core processing components
- **UX Enhancements** - Quiet mode progress bar suppression, retry env vars, improved help text

This release focuses on **ease of use** (name support, Windows compatibility), **documentation workflows** (markdown export), and **user experience** (helpful error messages, better CLI).

### Added

#### Data View Name Support
- **Use Names Instead of IDs**: Specify data views by their human-readable name (e.g., `"Production Analytics"`) instead of ID (e.g., `dv_677ea9291244fd082f02dd42`)
- **Automatic Name Resolution**: Tool automatically resolves names to IDs by fetching available data views
- **Duplicate Name Handling**: If multiple data views share the same name, all matching views are processed
- **Mixed Input Support**: Combine IDs and names in the same command (e.g., `cja_auto_sdr dv_12345 "Staging" "Test"`)
- **Case-Sensitive Exact Matching**: Names must match exactly as they appear in CJA
- **Enhanced CLI Help**: Updated command-line help to show both ID and name options
- **Name Resolution Feedback**: Shows which names resolved to which IDs before processing
- **16 New Tests**: Comprehensive test coverage for name resolution (`tests/test_name_resolution.py`)
- **New Documentation**: Complete guide in `docs/DATA_VIEW_NAMES.md`
- **Benefits**:
  - Easier to remember and use
  - More readable scripts and documentation
  - Better for scheduled reports and CI/CD pipelines
  - Reduces copy-paste errors with long IDs

#### Windows Support Improvements
- **Windows-Specific Troubleshooting**: New comprehensive section in `docs/TROUBLESHOOTING.md` covering:
  - NumPy ImportError solutions (4 different approaches)
  - `uv run` command alternatives for Windows
  - PowerShell execution policy issues
  - Path separator guidance
  - Virtual environment activation for PowerShell, CMD, and Git Bash
  - Windows diagnostic script (PowerShell equivalent)
  - Common Windows commands reference table
  - Recommended Windows setup with step-by-step guidance
- **Windows Native Setup Guide**: New "Option 5" in `docs/INSTALLATION.md` for pure Python installation without `uv`
- **Platform-Specific Examples**: All documentation now includes separate Windows PowerShell examples
- **README Updates**: Windows-specific notes and alternatives throughout Quick Start section

#### Configuration File Rename
- **Clearer Naming**: Renamed `myconfig.json` to `config.json` for better clarity
- **Updated Example File**: Renamed `myconfig.json.example` to `config.json.example`
- **Consistent Documentation**: All documentation and error messages updated to use `config.json`
- **Sample Config Generator**: Updated to generate `config.sample.json` with clear instructions
- **Benefits**:
  - More standard naming convention
  - Less confusion about whether "myconfig" is a placeholder
  - Clearer intent as the configuration file

#### Markdown Output Format
- **New `--format markdown` option**: Export SDR as GitHub/Confluence-compatible markdown
- **GitHub-Flavored Markdown Tables**: Properly formatted tables with pipe separators
- **Table of Contents**: Auto-generated TOC with section anchor links
- **Collapsible Sections**: Large tables (>50 rows) automatically use `<details>` tags for better readability
- **Special Character Escaping**: Proper escaping of pipes, backticks, and other markdown syntax
- **Issue Summary for Data Quality**: Severity counts with emoji indicators (🔴 CRITICAL, 🟠 HIGH, 🟡 MEDIUM, ⚪ LOW, 🔵 INFO)
- **Row Counts**: Each section shows total item counts
- **Unicode Support**: Full support for international characters
- **Metadata Section**: Formatted key-value pairs for document information
- **Professional Footer**: Generated by CJA Auto SDR Generator attribution
- **Use Cases**:
  - Paste directly into GitHub README files, issues, or wiki pages
  - Copy to Confluence pages for team documentation
  - Version control friendly format for tracking changes
  - Lightweight alternative to Excel/HTML for documentation workflows

#### Enhanced Error Messages with Actionable Suggestions
- **ErrorMessageHelper Class**: New comprehensive error message system providing contextual, actionable guidance
- **HTTP Status Code Messages**: Detailed error messages for all common HTTP errors:
  - **400 Bad Request**: Parameter validation and request structure guidance
  - **401 Authentication Failed**: Credential verification steps and setup links
  - **403 Access Forbidden**: Permission troubleshooting and admin contact guidance
  - **404 Resource Not Found**: Data view validation with `--list-dataviews` suggestion
  - **429 Rate Limit Exceeded**: Worker reduction, caching, and retry configuration suggestions
  - **500 Internal Server Error**: Adobe status page links and retry guidance
  - **502 Bad Gateway**: Network issue identification and retry suggestions
  - **503 Service Unavailable**: Maintenance detection and status page links
  - **504 Gateway Timeout**: Large data view handling and timeout configuration
- **Network Error Messages**: Contextual guidance for connection issues:
  - **ConnectionError**: Internet connectivity and firewall troubleshooting
  - **TimeoutError**: Network stability and retry configuration
  - **SSLError**: Certificate updates and system time verification
  - **ConnectionResetError**: Temporary network issue handling
- **Configuration Error Messages**: Step-by-step setup guidance:
  - **File Not Found**: Sample config generation and environment variable alternatives
  - **Invalid JSON**: Common JSON errors, validation tools, and syntax checking
  - **Missing Credentials**: Required fields list and Developer Console links
  - **Invalid Format**: Credential format validation and regeneration guidance
- **Data View Error Messages**: Targeted troubleshooting with context:
  - Shows available data view count when view not found
  - Lists accessible data views to help identify correct ID
  - Provides specific guidance when no data views are accessible
- **Documentation Links**: All error messages include relevant documentation URLs
- **Multi-Level Suggestions**: Errors provide 3-10 actionable steps to resolve issues
- **Error Context**: All error messages include operation name and failure context

#### Integration Points
- **Retry Mechanism**: Enhanced error messages automatically shown after all retry attempts fail
- **Configuration Validation**: Config file errors now show detailed setup instructions
- **Data View Validation**: Not found errors include list of available data views
- **Network Operations**: All API calls provide enhanced error context on failure

#### UX Enhancements
- **Progress Bars Respect Quiet Mode**: Progress bars in `ParallelAPIFetcher` and `DataQualityChecker` are now disabled when using `--quiet` flag for cleaner output in scripts and CI/CD pipelines
- **Retry Configuration via Environment Variables**: Configure retry behavior through environment variables:
  - `MAX_RETRIES` - Maximum API retry attempts (default: 3)
  - `RETRY_BASE_DELAY` - Initial retry delay in seconds (default: 1.0)
  - `RETRY_MAX_DELAY` - Maximum retry delay in seconds (default: 30.0)
- **Python 3.14 Requirement in Help**: `--help` now displays Python version requirement in the epilog
- **Improved --format Help Text**: Clarified that `--format all` generates all formats simultaneously
- **VALIDATION_SCHEMA Documentation**: Added detailed comments explaining the schema's purpose and usage
- **Enhanced Property Docstrings**: Improved `file_size_formatted` docstring with example output

#### Shell Tab-Completion Support
- **argcomplete Integration**: Optional shell tab-completion for all CLI flags and values
- **Bash/Zsh Support**: Works with both bash and zsh shells after one-time activation
- **Flag Completion**: Tab-complete all `--` flags (e.g., `--format`, `--log-level`, `--workers`)
- **Value Completion**: Tab-complete flag values (e.g., `--format <TAB>` shows `excel csv json html markdown all`)
- **Optional Dependency**: Install with `pip install cja-auto-sdr[completion]` or `pip install argcomplete`
- **Zero Overhead**: No performance impact if argcomplete is not installed
- **Documentation**: Full setup instructions in `docs/CLI_REFERENCE.md`

#### CLI Documentation Alignment
- **CLI_REFERENCE.md**: Updated to match README guidance with three invocation methods:
  - `uv run cja_auto_sdr ...` — works immediately on macOS/Linux, may have issues on Windows
  - `cja_auto_sdr ...` — after activating the venv
  - `python cja_sdr_generator.py ...` — run the script directly (most reliable on Windows)
- **Consistent Version References**: All documentation updated to reference v3.0.9

#### Testing
- **182 New Tests**: Comprehensive test coverage expansion
- **Name Resolution Tests** (`tests/test_name_resolution.py`): ID detection, single/multiple name resolution, duplicate handling, error scenarios
- **Parallel API Fetcher Tests** (`tests/test_parallel_api_fetcher.py`): Thread pool execution, API data fetching, error handling
- **Batch Processor Tests** (`tests/test_batch_processor.py`): Worker coordination, result aggregation, summary output
- **Process Single Dataview Tests** (`tests/test_process_single_dataview.py`): End-to-end processing, output formats, caching
- **Excel Formatting Tests** (`tests/test_excel_formatting.py`): Sheet formatting, severity colors, column/row sizing
- **CJA Initialization Tests** (`tests/test_cja_initialization.py`): Config loading, credential validation, connection testing
- **Integration Tests**: Verification of enhanced messages in retry and validation flows
- **Markdown Output Tests**: Full coverage of markdown generation, escaping, collapsible sections, Unicode, and more
- **CLI Tests** (`tests/test_cli.py`): Expanded with 14 new tests for retry arguments (11) and --validate-config flag (3)
- **Total Test Count**: 413 tests (100% pass rate)

### Improved
- **User Experience**:
  - Data views can now be referenced by memorable names instead of long IDs
  - Errors now provide clear "Why this happened" and "How to fix it" sections
  - Windows users have comprehensive platform-specific documentation
  - Configuration file naming is more intuitive
  - Progress bars no longer show when using `--quiet` flag
  - Retry settings can be configured via environment variables for CI/CD pipelines
- **Documentation**: More readable commands in scripts, CI/CD pipelines, and documentation
- **Troubleshooting Time**: Reduced with direct links to relevant documentation and platform-specific guides
- **Developer Onboarding**: Better guidance for common setup issues across all platforms
- **Support Burden**: Self-service error resolution and clear documentation reduce support requests
- **Cross-Platform Support**: Equal support quality for Windows, macOS, and Linux users

### Changed
- **Configuration File Name**: `myconfig.json` → `config.json` (users should rename their existing file)
- **Example Config File**: `myconfig.json.example` → `config.json.example`
- **Sample Config Output**: `myconfig.sample.json` → `config.sample.json`
- **CLI Help Text**: Updated to reflect ID or name support for data views
- **Documentation**: Updated throughout to use `config.json` naming

### Backward Compatibility
- **Full Backward Compatibility**: All existing commands and scripts continue to work
- **ID-Based Commands**: All existing ID-based data view specifications work unchanged
- **Config File Migration**: Users need to rename `myconfig.json` to `config.json` (simple `mv` command)
- **No Breaking Changes**: All tests pass, including legacy functionality

## [3.0.8] - 2026-01-15

### Added

#### Console Script Entry Points
- **`cja_auto_sdr` command**: Run the tool directly without `python` prefix
  - `cja_auto_sdr dv_12345` instead of `uv run python cja_sdr_generator.py dv_12345`
  - Also available as `cja-auto-sdr` (hyphenated version)
- **Proper packaging**: Added `[build-system]` with hatchling for standard Python packaging
- **Multiple installation options**:
  - `uv run cja_auto_sdr` - run within uv-managed environment
  - `pip install .` then `cja_auto_sdr` - install globally or in any virtualenv
  - Original `python cja_sdr_generator.py` continues to work

#### Environment Variable Credentials Support
- **Environment Variable Loading**: Credentials can now be loaded from environment variables
  - `ORG_ID`: Adobe Organization ID
  - `CLIENT_ID`: OAuth Client ID
  - `SECRET`: Client Secret
  - `SCOPES`: OAuth scopes
  - `SANDBOX`: Sandbox name (optional)
- **Priority Order**: Environment variables take precedence over `config.json`
- **Optional python-dotenv**: Install `python-dotenv` to enable automatic `.env` file loading
- **`.env.example`**: Template file for environment variable configuration
- **Full Backwards Compatibility**: Existing `config.json` configurations continue to work unchanged

#### Batch Processing Improvements
- **File Size in Batch Summary**: Each successful data view now shows its output file size
- **Total Output Size**: Batch summary includes total combined output size for all files
- **Correlation IDs**: Batch processing now includes 8-character correlation IDs in all log messages for easier log tracing

#### Data Quality Improvements
- **Complete Item Lists**: Data quality issues now show ALL affected item names
  - Previously limited to 5-20 items depending on issue type
  - Provides complete visibility for large data views with many issues

#### New CLI Commands
- **`--validate-config`**: Validate configuration and API connectivity without processing any data views
  - Tests environment variables or config file
  - Verifies API connection
  - Reports number of accessible data views

#### Configurable Retry Settings
- **`--max-retries`**: Maximum API retry attempts (default: 3)
- **`--retry-base-delay`**: Initial retry delay in seconds (default: 1.0)
- **`--retry-max-delay`**: Maximum retry delay in seconds (default: 30.0)

#### Environment Variable Enhancements
- **`OUTPUT_DIR`**: Output directory can now be set via environment variable
- **`.env` Loading Feedback**: Debug logging shows whether `.env` file was loaded

#### Test Infrastructure
- **Coverage Reporting**: pytest-cov integration with coverage threshold
- **pytest-cov Dependency**: Added as dev dependency for coverage reporting

#### Developer Experience
- **`config.json.example`**: New template file for config file setup (complements `.env.example`)
- **JWT Deprecation Warning**: Config validation now warns when deprecated JWT fields (`tech_acct`, `private_key`, `pathToKey`) are detected, with migration guidance

#### Error Handling Improvements
- **Specific File I/O Exceptions**: CSV, JSON, and HTML writers now catch `PermissionError` and `OSError` with actionable messages
- **JSON Serialization Errors**: JSON writer catches `TypeError`/`ValueError` with clear "non-serializable values" message
- **Retry Troubleshooting**: Failed API retries now include actionable troubleshooting hints

#### Code Quality
- **Logging Constants**: Extracted `LOG_FILE_MAX_BYTES` (10MB) and `LOG_FILE_BACKUP_COUNT` (5) to constants section
- **Cache Statistics Method**: Added `ValidationCache.log_statistics()` for compact cache performance logging

### Changed
- **pytest.ini**: Coverage flags now optional (removes pytest-cov as hard requirement for running tests)

### Fixed

#### Critical: Exception Handling
- **Graceful Ctrl+C**: Fixed overly broad exception handlers that prevented graceful shutdown
  - Batch processing now properly handles `KeyboardInterrupt` and `SystemExit`
  - Dry-run mode properly handles interruption
  - List data views command properly handles interruption
  - All operations now allow graceful cancellation with Ctrl+C

#### HTTP Status Code Retry
- **Status Code Handling**: `RETRYABLE_STATUS_CODES` (408, 429, 500, 502, 503, 504) now properly trigger retries
  - Previously defined but never used
  - Added `RetryableHTTPError` exception class
  - API calls now check response status codes and retry appropriately

#### Code Quality
- **Deduplicated File Size Formatting**: Consolidated duplicate `_format_file_size` implementations into single `format_file_size()` utility function

### Removed

#### JWT Authentication Support
- **Removed JWT Authentication**: JWT (Service Account) authentication has been removed
  - Adobe has deprecated JWT credentials in favor of OAuth Server-to-Server
  - `tech_id` and `private_key` config fields are no longer supported
  - `TECH_ID` and `PRIVATE_KEY` environment variables are no longer supported
  - Users must migrate to OAuth Server-to-Server credentials
  - See [Adobe's migration guide](https://developer.adobe.com/developer-console/docs/guides/authentication/ServerToServerAuthentication/migration/) for details

### Changed
- Updated documentation with environment variable configuration instructions
- Batch summary output format now includes file size column for each data view
- Updated error messages to include environment variable configuration option
- Simplified configuration validation to OAuth-only fields

### Documentation
- Updated `README.md` with `.env` configuration option
- Updated `docs/INSTALLATION.md` with environment variable setup section (OAuth-only)
- Updated `docs/QUICKSTART_GUIDE.md` with dual configuration options
- Added `.env.example` template file

---

## [3.0.7] - 2026-01-11

### Added

#### Code Quality & Maintainability
- **Centralized Validation Schema (`VALIDATION_SCHEMA`)**: All field definitions consolidated into single module-level constant
  - `required_metric_fields`: Fields required for metrics validation
  - `required_dimension_fields`: Fields required for dimensions validation
  - `critical_fields`: Fields checked for null values
  - Single source of truth eliminates scattered field definitions
  - Easier to update validation rules across the codebase

- **Error Message Formatting Helper (`_format_error_msg`)**: Consistent error message formatting
  - Unified format: `"Error {operation} for {item_type}: {error}"`
  - Replaces 18 inconsistent inline error message formats
  - Easier to modify error format globally
  - Handles optional parameters gracefully

#### Performance Optimization
- **Cache Key Reuse Optimization**: Eliminates redundant DataFrame hashing
  - `ValidationCache.get()` now returns `(issues, cache_key)` tuple
  - `ValidationCache.put()` accepts optional `cache_key` parameter
  - Avoids rehashing same DataFrame on cache misses (5-10% faster)
  - Fully backward compatible - `cache_key` parameter is optional

#### Test Coverage Expansion
- **17 New Tests** added for new functionality:
  - Error message formatting tests (7 tests)
  - Validation schema tests (6 tests)
  - Cache key reuse optimization tests (4 tests)
- **Total test count**: 191 → 208 tests

### Changed
- `ValidationCache.get()` return type changed from `Optional[List[Dict]]` to `Tuple[Optional[List[Dict]], str]`
- Error logging calls throughout codebase now use `_format_error_msg()` helper
- Validation calls use `VALIDATION_SCHEMA` instead of inline field definitions

### Technical Details

**Cache Key Reuse Example:**
```python
# Before: DataFrame hashed twice on cache miss
result = cache.get(df, 'Metrics', required, critical)  # Hash 1
if result is None:
    # ... validation ...
    cache.put(df, 'Metrics', required, critical, issues)  # Hash 2

# After: Hash computed once, reused
result, cache_key = cache.get(df, 'Metrics', required, critical)  # Hash 1
if result is None:
    # ... validation ...
    cache.put(df, 'Metrics', required, critical, issues, cache_key)  # No rehash
```

---

## [3.0.6] - 2026-01-11

### Added

#### Robustness & Input Validation
- **CLI Parameter Bounds Checking**: All numeric CLI parameters now validated
  - `--workers`: Must be 1-256 (prevents crashes from invalid values)
  - `--cache-size`: Must be >= 1
  - `--cache-ttl`: Must be >= 1 second
  - `--max-issues`: Must be >= 0
- **Output Directory Error Handling**: Clear error messages for permission/disk issues when creating output directories
- **Log Directory Graceful Fallback**: If log directory can't be created, falls back to console-only logging instead of crashing

#### Logging Improvements
- **RotatingFileHandler**: Log files now rotate automatically at 10MB with 5 backups retained
  - Prevents unbounded disk usage during long-running automation/cron jobs
  - Total maximum log storage: ~60MB per session type

#### Configuration Validation
- **OAuth Scopes Warning**: Warns when OAuth Server-to-Server authentication is detected without `scopes` field
  - Provides example scopes string for proper API access
  - Helps catch common misconfiguration before authentication failures

#### Error Message Improvements
- **Empty Data View Diagnostics**: When no metrics/dimensions are returned, provides:
  - 4 possible causes (empty data view, permission issues, new data view, API issues)
  - 3 troubleshooting steps with actionable guidance
  - Improved error message text

#### New CLI Flag
- **`--clear-cache`**: Clear validation cache before processing
  - Use with `--enable-cache` for fresh validation when needed
  - Documents intent for cache clearing behavior

#### Code Quality
- **Extracted Constants**: Hardcoded worker counts replaced with named constants
  - `DEFAULT_API_FETCH_WORKERS = 3`
  - `DEFAULT_VALIDATION_WORKERS = 2`
  - `DEFAULT_BATCH_WORKERS = 4`
  - `MAX_BATCH_WORKERS = 256`
  - `DEFAULT_CACHE_SIZE = 1000`
  - `DEFAULT_CACHE_TTL = 3600`
- **Improved Docstrings**: Added parameter constraints and valid ranges to key functions
  - `process_single_dataview()`: Full parameter documentation
  - `BatchProcessor`: Comprehensive class docstring with all parameters
  - `ValidationCache`: Parameter constraints documented

### Changed
- Help text now shows parameter defaults and constraints from constants
- Log directory creation failures no longer crash the application

### Fixed
- Potential crash when `--workers 0` or negative values provided
- Potential crash when `--cache-size 0` provided
- Potential crash when `--cache-ttl 0` provided
- Cryptic error messages when output directory can't be created

---

## [3.0.5] - 2026-01-10

### Added

#### UX Improvements
- **File Size in Output**: Success message now displays output file size in human-readable format (B, KB, MB, GB)
- **`--validate-only`**: New alias for `--dry-run` with clearer semantics
- **`--max-issues N`**: Limit data quality issues to top N by severity (0 = show all)
  - Issues are sorted by severity (CRITICAL first) before limiting
  - Useful for data views with many issues to focus on most important ones
  - Works with all output formats

#### Test Coverage
- Added 8 new tests for UX improvements
- Total test count increased from 171 to 179

---

## [3.0.4] - 2026-01-10

### Added

#### CLI Usability Enhancements
- **`--list-dataviews`**: New flag to list all accessible data views without processing
  - Displays data view ID, name, and owner in a formatted table
  - Helps users discover available data view IDs before running reports
  - No data view ID argument required when using this flag
- **`--skip-validation`**: New flag to skip data quality validation for faster processing
  - Provides 20-30% performance improvement when validation is not needed
  - Useful for quick regeneration of reports when data quality is already known
  - Works with both single and batch processing modes
- **`--sample-config`**: New flag to generate a sample configuration file
  - Creates `myconfig.sample.json` with template for OAuth Server-to-Server authentication
  - Includes clear instructions for configuring credentials
  - No data view ID argument required when using this flag

#### Test Coverage Expansion
- Added 10 new CLI tests for new flags (--list-dataviews, --skip-validation, --sample-config)
- Added 3 new tests for sample config generation functionality
- Total test count increased from 161 to 171

---

## [3.0.3] - 2026-01-10

### Added

#### Retry with Exponential Backoff
- **Automatic Retry**: All API calls now automatically retry on transient network errors
- **Exponential Backoff**: Delay between retries increases exponentially (1s, 2s, 4s, etc.)
- **Jitter**: Random variation added to retry delays to prevent thundering herd problems
- **Configurable**: Default settings (3 retries, 1s base delay, 30s max delay) can be customized
- **Retryable Errors**: Handles ConnectionError, TimeoutError, and OSError automatically
- **Non-Blocking**: Non-retryable errors (ValueError, KeyError, etc.) fail immediately
- **Comprehensive Logging**: Warnings logged for each retry attempt with delay information

#### Retry Implementation Details
- `retry_with_backoff` decorator for wrapping functions with retry logic
- `make_api_call_with_retry` function for ad-hoc API calls with retry
- Applied to all CJA API calls: getDataViews, getDataView, getMetrics, getDimensions
- Applied to dry-run mode validation calls
- 21 new tests covering all retry scenarios

---

## [3.0.2] - 2026-01-10

### Added

#### CLI Quick Wins
- **Version Flag**: New `--version` flag to display program version (3.0.2)
- **Quiet Mode**: New `--quiet` / `-q` flag to suppress all output except errors and final summary
- **Color-Coded Output**: Console output now uses ANSI colors for better visual feedback
  - Green for success messages and successful data views
  - Red for error messages and failed data views
  - Yellow for warnings
  - Bold for headers and important information
- **Total Runtime Display**: Final summary now shows total runtime for all operations

#### Enhanced Config Validation
- **Schema-Based Validation**: Configuration file validation now uses a defined schema with type checking
- **Type Validation**: Validates that all config fields have the correct data types
- **Empty Value Detection**: Detects and reports empty values in required fields
- **Unknown Field Detection**: Warns about unrecognized fields (possible typos)
- **Private Key Validation**: Validates private key file path if provided as a file path

### Changed
- **Data View Validation**: Missing data views are now validated in main() instead of argparse, allowing `--version` flag to work without data view arguments
- **Config Validation Strictness**: Missing required config fields now causes validation to fail (previously only warned)
- **Test Count**: Expanded test suite from 136 to 140 tests

---

## [3.0.1] - 2026-01-09

### Added

#### Dry-Run Mode
- **Configuration Validation**: New `--dry-run` CLI flag to validate configuration and connectivity without generating reports
- **Three-Step Validation**: Validates config file, tests API connection, and verifies data view accessibility
- **Pre-Flight Checks**: Ideal for CI/CD pipelines and debugging connection issues before full processing
- **Actionable Output**: Clear success/failure indicators with suggested next steps

#### Progress Indicators
- **tqdm Integration**: Added progress bars for long-running operations with ETA and completion rate
- **Batch Processing Progress**: Visual progress tracking for multi-data-view batch operations
- **API Fetch Progress**: Progress indicators during parallel API data fetching
- **Validation Progress**: Progress bars for parallel validation operations

#### Excel Formatting Enhancements
- **Metrics/Dimensions Column Reordering**: Name column now appears first for better readability
- **Bold Name Column**: Name column in Metrics/Dimensions sheets styled bold for quick scanning
- **Optimized Column Widths**: Tighter column width limits (description: 55, name/title: 40) for better layout

### Changed
- **Dependencies**: Added `tqdm>=4.66.0` for progress bar support
- **Removed Unused Import**: Removed unused `asyncio` import from main module
- **Test Count**: Expanded test suite from 121 to 136 tests

### Fixed
- **Test Threshold Adjustment**: Updated parallel validation test threshold to account for progress bar overhead on small datasets

---

## [3.0.0] - 2026-01-08

### Added

#### Output Format Flexibility
- **Multiple Output Formats**: Support for Excel, CSV, JSON, HTML, and all formats simultaneously
- **CSV Output**: Individual CSV files for each section (metadata, data quality, metrics, dimensions)
- **JSON Output**: Hierarchical structured data with proper encoding and formatting
- **HTML Output**: Professional web-ready reports with embedded CSS and responsive design
- **Format Selection**: New `--format` CLI argument to choose output format (excel, csv, json, html, all)
- **Comprehensive Testing**: 20 new tests covering all output formats and edge cases

#### Performance Optimization

**Validation Result Caching (50-90% Performance Improvement on Cache Hits)**
- **ValidationCache Class**: Thread-safe LRU cache for validation results with configurable size and TTL
- **CLI Integration**: `--enable-cache`, `--cache-size`, and `--cache-ttl` flags for cache control
- **Cache Statistics**: Detailed performance metrics including hits, misses, hit rate, and time saved
- **Smart Cache Keys**: Content-based DataFrame hashing using `pandas.util.hash_pandas_object` combined with configuration hashing
- **LRU Eviction**: Automatic removal of least recently used entries when cache reaches maximum size
- **TTL Support**: Configurable time-to-live for cache entries (default: 1 hour = 3600 seconds)
- **Thread-Safe Design**: Lock-protected operations safe for concurrent validation with parallel execution
- **Zero Overhead**: No performance impact when cache is disabled (default behavior)

**Parallel Validation (10-15% Performance Improvement)**
- **Concurrent Validation**: Metrics and dimensions validation now run in parallel using ThreadPoolExecutor
- **Thread-Safe Design**: Lock-protected shared state for reliable concurrent operation
- **New Method**: `DataQualityChecker.check_all_parallel()` for parallel validation execution
- **Better CPU Utilization**: Better utilization of multi-core systems

**Optimized Single-Pass Validation (30-50% Performance Improvement)**
- **Single-Pass DataFrame Scanning**: Combined validation checks for 30-50% performance improvement
- **Vectorized Operations**: Replaced sequential scans with vectorized pandas operations
- **Reduced Memory Overhead**: 89% reduction in DataFrame scans (9 scans → 1 scan)
- **Better Scalability**: Improved performance for large data views (200+ components)

**Early Exit Optimization (1-2% Average, 15-20% Error Scenarios)**
- **DataFrame Pre-validation**: Validation exits immediately on critical errors
- **Fail-Fast Behavior**: Skips unnecessary checks when required fields are missing
- **Operation Reduction**: Prevents ~1600 unnecessary operations when required fields missing

**Logging Optimization (5-10% Performance Gain)**
- **Production Mode**: New `--production` CLI flag for minimal logging overhead
- **Environment Variable Support**: `LOG_LEVEL` environment variable for system-wide log level defaults
- **Conditional Logging**: Data quality issues logged selectively based on severity and log level
- **Summary Logging**: New `DataQualityChecker.log_summary()` method aggregates issues by severity
- **Log Entry Reduction**: 73-82% fewer log entries depending on dataset size

**Performance Tracking**
- **Built-in Metrics**: Built-in performance metrics and timing for validation operations
- **Operation Timing**: Individual operation timing (DEBUG level) and comprehensive summaries

#### Batch Processing
- **Parallel Multiprocessing**: Process multiple data views simultaneously with ProcessPoolExecutor
- **3-4x Throughput Improvement**: Parallel execution with configurable worker pools
- **Automatic Batch Mode**: Automatically enables parallel processing when multiple data views provided
- **Worker Configuration**: `--workers` flag to control parallelism (default: 4)
- **Continue on Error**: `--continue-on-error` flag to process all data views despite failures
- **Batch Summary Reports**: Detailed success/failure statistics and throughput metrics
- **Separate Logging**: Dedicated batch mode logs with comprehensive tracking

#### Testing Infrastructure
- **Comprehensive Test Suite**: 121 automated tests with 100% pass rate
- **Test Categories**:
  - CLI tests (10 tests)
  - Data quality tests (10 tests)
  - Optimized validation tests (16 tests)
  - Output format tests (20 tests)
  - Utility tests (14 tests)
  - Early exit tests (11 tests)
  - Logging optimization tests (15 tests)
  - Parallel validation tests (8 tests)
  - Validation caching tests (15 tests)
  - Output format tests (2 tests)
- **Performance Benchmarks**: Automated performance comparison tests
- **Thread Safety Tests**: Comprehensive concurrent execution validation
- **Edge Case Coverage**: Tests for Unicode, special characters, empty datasets, and large datasets
- **Test Fixtures**: Reusable mock configurations and sample data
- **pytest Integration**: Full pytest support with proper configuration

#### Documentation
- **CHANGELOG.md**: This comprehensive changelog (NEW)
- **OUTPUT_FORMATS.md**: Complete guide to all output formats with examples
- **BATCH_PROCESSING_GUIDE.md**: Detailed batch processing documentation
- **OPTIMIZATION_SUMMARY.md**: Performance optimization implementation details
- **tests/README.md**: Test suite documentation and usage guide
- **Improved README.md**: Updated with all new features and examples

### Changed

#### Dependency Management
- **Version Update**: Updated from 0.1.0 to 3.0.0
- **Modern Package Management**: Uses `uv` for fast, reliable dependency management
- **pyproject.toml**: Standardized project configuration
- **Python 3.14+ Required**: Updated to require latest Python version
- **Lock Files**: Reproducible builds with `uv.lock`
- **Optional Dev Dependencies**: pytest and testing tools as optional dev dependencies

#### Code Quality
- **Removed Unused Imports**: Removed unused `pytz` import
- **Better Error Handling**: Pre-flight validation and graceful error handling
- **Enhanced Logging**: Timestamped logs with rotation and detailed tracking
- **Improved Reliability**: Validates data view existence before processing
- **Safe Filename Generation**: Handles special characters and edge cases

#### Documentation Formatting
- **Markdown Standards Compliance**: All documentation follows MD031 and MD032 standards
- **Consistent Formatting**: Uniform style across all markdown files
- **Removed Checkmark Emojis**: Replaced with standard bullet points for better compatibility
- **Proper Spacing**: Blank lines around code blocks, lists, and headings
- **Professional Presentation**: Clean, readable documentation throughout

### Fixed

- **Version Mismatch**: Corrected version number from 0.1.0 to 3.0.0 in pyproject.toml
- **Missing Test Dependency**: Added pytest as optional dev dependency
- **Markdown Linting Warnings**: Fixed 100+ markdown formatting issues across all documentation
- **Import Errors**: Removed unused pytz dependency that was never actually used
- **Documentation Consistency**: Updated all examples to match actual implementation

### Performance

**Cumulative Performance Improvements:**
- **Validation Caching**: 50-90% faster on cache hits (70% average), 1-2% overhead on misses
- **Parallel Validation**: 10-15% faster data quality validation through concurrent processing
- **Single-Pass Validation**: 30-50% faster through vectorized operations (89% reduction in DataFrame scans)
- **Early Exit Optimization**: 15-20% faster on error scenarios, 1-2% average improvement
- **Logging Optimization**: 5-10% faster with production mode, 73-82% fewer log entries
- **Batch Processing**: 3-4x throughput improvement with parallel multiprocessing
- **Better CPU Utilization**: No GIL limitations with ProcessPoolExecutor
- **Reduced Memory Allocations**: Optimized memory access patterns

**Real-World Impact:**
```
Small Data View (50 components):
  Before: 0.5s validation
  After:  0.25s validation (50% faster)
  With cache hit: 0.05s (90% faster)

Medium Data View (150 components):
  Before: 1.8s validation
  After:  0.9s validation (50% faster)
  With cache hit: 0.09s (95% faster)

Large Data View (225+ components):
  Before: 2.5s validation
  After:  1.2s validation (52% faster)
  With cache hit: 0.12s (95% faster)

Batch Processing (10 data views):
  Sequential (old): 350s
  Parallel (4 workers): 87s (4x faster)
  With cache (70% hit rate): 30s (11x faster)
```

### Backward Compatibility

- **100% Backward Compatible**: All existing validation methods preserved
- **No Breaking Changes**: Existing scripts continue to work without modifications
- **Default Behavior Unchanged**: Excel output remains the default format
- **API Compatibility**: Same issue structure and format as previous versions
- **Dual Validation Options**: Both original and optimized validation available

### Testing

- **121 Tests Total**: Complete test coverage across all components
  - 10 CLI tests
  - 10 Data quality tests
  - 16 Optimized validation tests
  - 20 Output format tests
  - 14 Utility tests
  - 11 Early exit tests
  - 15 Logging optimization tests
  - 8 Parallel validation tests
  - 15 Validation caching tests
  - 2 Additional output format tests
- **100% Pass Rate**: All tests passing
- **Performance Validated**: All optimization improvements verified through automated benchmarks
- **Thread Safety Verified**: Concurrent execution tested under load
- **Fast Execution**: Complete suite runs in < 1 second
- **CI/CD Ready**: GitHub Actions examples provided

### Documentation

- **5 Major Documentation Files**: README, OUTPUT_FORMATS, BATCH_PROCESSING_GUIDE, OPTIMIZATION_SUMMARY, CHANGELOG
- **132+ Formatting Improvements**: Professional, consistent documentation
- **Code Examples**: Comprehensive examples for all features
- **Troubleshooting Guides**: Detailed error resolution steps
- **Use Case Recommendations**: Clear guidance on when to use each feature

---

## [0.1.0] - 2025 (Previous Version)

### Initial Features

- Basic Excel output generation
- CJA API integration using cjapy
- Data view metadata extraction
- Metrics and dimensions export
- Basic data quality validation
- Single data view processing
- Command-line interface
- Jupyter notebook origin

---

## Version Comparison

| Feature | v0.1.0 | v3.0.0 |
|---------|--------|--------|
| Output Formats | Excel only | Excel, CSV, JSON, HTML, All |
| Batch Processing | No | Yes (3-4x faster) |
| Data Quality Validation | Sequential | Optimized (30-50% faster) + Parallel (10-15% faster) |
| Validation Caching | No | Yes (50-90% faster on cache hits) |
| Early Exit Optimization | No | Yes (15-20% faster on errors) |
| Logging Optimization | No | Yes (5-10% faster with --production) |
| Tests | None | 623 comprehensive tests |
| Documentation | Basic | 5 detailed guides |
| Performance Tracking | No | Yes, built-in with cache statistics |
| Parallel Processing | No | Yes, configurable workers + concurrent validation |
| Error Handling | Basic | Comprehensive |
| Thread Safety | N/A | Yes, lock-protected concurrent operations |
| Python Version | 3.x | 3.14+ |
| Package Manager | pip | uv |

---

## Migration Guide from v0.1.0 to v3.0.0

### Breaking Changes
**None** - Version 3.0.0 is fully backward compatible.

### Recommended Updates

1. **Update Python version**:
   ```bash
   # Ensure Python 3.14+ is installed
   python --version  # Should be 3.14 or higher
   ```

2. **Install uv**:
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

3. **Sync dependencies**:
   ```bash
   uv sync
   ```

4. **Update scripts** (optional but recommended):
   ```bash
   # Recommended (v3.0.8+): Console script
   cja_auto_sdr dv_12345

   # Alternative: Using uv run
   uv run cja_auto_sdr dv_12345

   # Legacy (still works)
   python cja_sdr_generator.py dv_12345
   ```

5. **Explore new features**:
   - Try different output formats: `--format csv`, `--format json`, `--format html`
   - Use batch processing: `cja_auto_sdr dv_1 dv_2 dv_3`
   - Review new documentation guides

---

## Links

- **Repository**: https://github.com/brian-a-au/cja_auto_sdr
- **Issues**: https://github.com/brian-a-au/cja_auto_sdr/issues
- **Original Notebook**: https://github.com/pitchmuc/CJA_Summit_2025

---

## Acknowledgments

Built on the foundation of the [CJA Summit 2025 notebook](https://github.com/pitchmuc/CJA_Summit_2025/blob/main/notebooks/06.%20CJA%20Data%20View%20Solution%20Design%20Reference%20Generator.ipynb) by pitchmuc.

Version 3.0.0 represents a comprehensive evolution from proof-of-concept to production-ready enterprise solution.
