# CJA SDR Generator - Test Suite

This directory contains automated tests for the CJA SDR Generator.

## Test Structure

```
tests/
├── __init__.py                      # Test package initialization
├── conftest.py                      # Pytest fixtures and configuration
├── test_api_tuning.py               # API worker auto-tuning tests
├── test_backwards_compat.py         # Backwards compatibility tests
├── test_batch_processor.py          # Batch processor tests
├── test_calculated_metrics_inventory.py  # Calculated metrics inventory tests
├── test_circuit_breaker.py          # Circuit breaker pattern tests
├── test_cja_initialization.py       # CJA initialization and validation tests
├── test_cli.py                      # Command-line interface tests
├── test_data_quality.py             # Data quality validation tests
├── test_derived_inventory.py        # Derived fields inventory tests
├── test_diff_comparison.py          # Data view diff comparison tests
├── test_discovery_formatters.py     # Discovery formatters and WorkerArgs tests
├── test_discovery_normalization.py  # Discovery normalization helpers tests
├── test_discovery_payloads.py       # Discovery payload classification tests
├── test_discovery_component_consistency.py  # Discovery component consistency tests
├── test_dry_run.py                  # Dry-run mode tests
├── test_early_exit.py               # Early exit optimization tests
├── test_edge_cases.py               # Edge cases and configuration tests
├── test_env_credentials.py          # Environment variable credentials tests
├── test_error_messages.py           # Enhanced error message tests
├── test_excel_formatting.py         # Excel formatting tests
├── test_git_integration.py          # Git integration and snapshot tests
├── test_inventory_utils.py          # Inventory utilities tests
├── test_logging_optimization.py     # Logging optimization tests
├── test_name_resolution.py          # Data view name resolution tests
├── test_optimized_validation.py     # Optimized validation tests
├── test_org_report.py               # Org-wide analysis tests
├── test_org_report_integration.py   # Org-wide analysis integration tests
├── test_output_formats.py           # Output format tests
├── test_parallel_api_fetcher.py     # Parallel API fetcher tests
├── test_parallel_validation.py      # Parallel validation tests
├── test_process_single_dataview.py  # Single data view processing tests
├── test_profiles.py                 # Multi-organization profile tests
├── test_retry.py                    # Retry with exponential backoff tests
├── test_segments_inventory.py       # Segments inventory tests
├── test_shared_cache.py             # Shared validation cache tests
├── test_update_test_counts.py       # Test count validation tests
├── test_utils.py                    # Utility function tests
├── test_ux_features.py              # UX enhancement features tests
├── test_validation_cache.py         # Validation caching tests
├── test_e2e_integration.py          # End-to-end integration tests
├── test_main_entry_points.py        # main() and _main_impl() entry point tests
├── test_malformed_api_responses.py  # Negative tests for malformed API data
├── test_output_content_validation.py # Output format content validation tests
├── test_quality_policy_and_run_summary.py # Quality policy and run summary tests
├── test_api_client.py               # API client exception path tests
├── test_config_validation.py        # Configuration validation tests
├── test_credentials.py              # Credential resolution tests
├── test_perf.py                     # Performance utilities tests
├── test_snapshot.py                 # Diff snapshot tests
├── test_colors.py                   # Console color formatting tests
├── test_exceptions.py               # Custom exception class tests
├── test_logging_redaction.py        # Logging and sensitive data redaction tests
├── test_config_dataclasses.py       # Config dataclasses and constants tests
├── test_lock_manager.py             # Lock manager tests
├── test_lazy_forwarding.py          # Lazy-forwarding infrastructure tests
├── test_api_coverage.py             # API module coverage (cache, quality, fetch, resilience)
├── test_diff_coverage.py            # Diff module coverage (comparator, models, git)
├── test_generator_coverage.py       # Generator utility function coverage
├── test_segments_coverage.py        # Segments module coverage (operators, containers)
├── test_small_module_coverage.py    # Small module coverage (logging, utils, calc metrics)
├── test_diff_inventory_output.py   # Inventory diff output across all formats
├── test_cli_command_handlers.py    # CLI dispatch (--stats, --org-report, --list-snapshots, discovery inspection)
├── test_profile_management.py      # Interactive profile creation, import, test, show
├── test_snapshot_commands.py        # Snapshot creation, comparison, name resolution
├── test_config_and_resolution.py    # Config status, validation, stats, name resolution
├── test_derived_fields_edge_cases.py  # Derived fields edge cases and coverage
├── test_diff_command_coverage.py    # Diff command edge cases and coverage
├── test_generator_interactive_and_console.py  # Generator interactive and console tests
├── test_generator_remaining_coverage.py  # Generator remaining coverage edge cases
├── test_interactive_discovery_coverage.py  # Interactive discovery and helpers coverage
├── test_lock_backends.py            # Lock backends edge cases and coverage
├── test_main_impl_cli_coverage.py   # _main_impl CLI path coverage
├── test_main_impl_coverage.py       # _main_impl coverage edge cases
├── test_near_100_coverage.py        # Near-100% coverage gap tests
├── test_org_cache_branches.py       # Org cache branch coverage
├── test_org_writer_coverage.py      # Org writer edge cases and coverage
├── test_output_writer_coverage.py   # Output writer edge cases and coverage
├── test_exception_contracts.py      # Exception boundary contract tests
├── test_parallel_validation.py      # Parallel validation operations
├── test_cli_smoke_modes.py          # CLI smoke tests for core command modes
├── test_generator_mock_contract.py  # Generator mock symbol contract tests
├── test_exception_narrowing.py     # Exception narrowing boundary tests
├── test_coverage_hardening.py      # Coverage hardening tests
├── test_trending_models.py         # Trending dataclass construction and bridge tests
├── test_trending_discovery.py      # Snapshot cache discovery, deltas, drift scoring
├── test_trending_cli.py            # --trending-window CLI flag parsing
├── test_trending_output.py         # Trending output across all 6 formats
├── test_trending_integration.py    # Trending backwards compatibility and integration
└── README.md                        # This file
```

**Total: 5,672 comprehensive tests**

### Test Count Breakdown

| Test File | Tests | Coverage Area |
|-----------|-------|---------------|
| `test_diff_comparison.py` | 169 | Data view diff comparison feature with inventory support |
| `test_ux_features.py` | 123 | UX features: --open, --stats, --output, --list-dataviews formats, inventory validation, inventory summary, include-all-inventory |
| `test_org_report.py` | 175 | Org-wide component analysis: config, distribution, similarity, output formats, large org scaling, output path aliases |
| `test_org_report_integration.py` | 17 | Org-wide analysis integration tests: end-to-end flows, caching, filtering, governance |
| `test_cli.py` | 431 | Command-line interface and argument parsing |
| `test_profiles.py` | 77 | Multi-organization profile support |
| `test_derived_inventory.py` | 62 | Derived fields inventory feature |
| `test_inventory_utils.py` | 47 | Inventory utilities and helpers |
| `test_segments_inventory.py` | 48 | Segments inventory feature |
| `test_edge_cases.py` | 39 | Edge cases, configuration dataclasses, custom exceptions |
| `test_calculated_metrics_inventory.py` | 285 | Calculated metrics inventory feature |
| `test_git_integration.py` | 40 | Git integration, snapshot management, inventory snapshots |
| `test_output_formats.py` | 37 | CSV, JSON, HTML, Markdown output generation |
| `test_cja_initialization.py` | 48 | CJA connection and configuration validation |
| `test_utils.py` | 50 | Utility functions and helpers |
| `test_excel_formatting.py` | 25 | Excel sheet formatting and styling |
| `test_parallel_api_fetcher.py` | 35 | Parallel API data fetching |
| `test_api_tuning.py` | 23 | API worker auto-tuning |
| `test_error_messages.py` | 23 | Enhanced error messages and guidance |
| `test_circuit_breaker.py` | 22 | Circuit breaker pattern |
| `test_retry.py` | 25 | Retry with exponential backoff |
| `test_batch_processor.py` | 26 | Batch processing of multiple data views |
| `test_validation_cache.py` | 24 | Validation result caching |
| `test_process_single_dataview.py` | 44 | End-to-end single data view processing |
| `test_optimized_validation.py` | 16 | Optimized data quality validation |
| `test_name_resolution.py` | 24 | Data view name to ID resolution |
| `test_shared_cache.py` | 22 | Shared validation cache |
| `test_logging_optimization.py` | 17 | Logging performance optimizations |
| `test_env_credentials.py` | 15 | Environment variable credentials |
| `test_dry_run.py` | 14 | Dry-run mode functionality |
| `test_early_exit.py` | 11 | Early exit optimizations |
| `test_data_quality.py` | 10 | Data quality validation logic |
| `test_parallel_validation.py` | 9 | Parallel validation operations |
| `test_discovery_formatters.py` | 32 | Shared discovery formatters, WorkerArgs dataclass, _exit_error, BANNER_WIDTH |
| `test_discovery_normalization.py` | 17 | Discovery normalization helpers (missing values, owner extraction, tags) |
| `test_discovery_payloads.py` | 60 | Discovery payload classification (error detection, component extraction) |
| `test_discovery_component_consistency.py` | 7 | Discovery component retrieval consistency |
| `test_output_content_validation.py` | 29 | Output format content validation (CSV, JSON, HTML, Excel, Markdown roundtrip) |
| `test_malformed_api_responses.py` | 20 | Negative tests for malformed/unexpected API responses |
| `test_main_entry_points.py` | 21 | main() and _main_impl() entry points, dispatch, run_state, run summary |
| `test_quality_policy_and_run_summary.py` | 87 | Quality policy functions and run summary/status inference |
| `test_e2e_integration.py` | 16 | End-to-end integration tests with real pipeline, mocked API boundary |
| `test_api_client.py` | 29 | API client exception paths and error handling |
| `test_config_validation.py` | 55 | Configuration validation logic |
| `test_credentials.py` | 70 | Credential resolution and source selection |
| `test_perf.py` | 7 | Performance utilities (cache eviction, statistics) |
| `test_snapshot.py` | 74 | Diff snapshot creation and comparison |
| `test_colors.py` | 122 | Console color formatting, themes, TTY detection |
| `test_exceptions.py` | 64 | Custom exception classes construction and formatting |
| `test_logging_redaction.py` | 158 | Logging, sensitive data redaction, JSON formatter |
| `test_config_dataclasses.py` | 88 | Config dataclasses and constants functions |
| `test_lock_manager.py` | 48 | Lock manager acquire/release/heartbeat lifecycle |
| `test_lazy_forwarding.py` | 71 | Lazy-forwarding infrastructure and make_getattr() |
| `test_lock_backend_edge_cases.py` | 165 | Lock backend metadata I/O, stale detection, legacy parsing |
| `test_derived_fields_coverage.py` | 161 | Derived field complexity scoring, logic summary, predicates |
| `test_org_analyzer_coverage.py` | 157 | Org analyzer governance, naming audit, sampling, memory, drift, clustering |
| `test_api_coverage.py` | 94 | API cache, quality, fetch, resilience exception paths |
| `test_diff_coverage.py` | 61 | Diff comparator, models, git integration edge cases |
| `test_generator_coverage.py` | 143 | Generator utility functions — coercion, normalization, diff formatting |
| `test_segments_coverage.py` | 78 | Segment comparison operators, container types, sequence variants |
| `test_small_module_coverage.py` | 113 | Logging, utils, calculated metrics, constants, lazy, tuning, locks, org cache |
| `test_diff_inventory_output.py` | 88 | Inventory diff output across all formats (console, JSON, HTML, Excel, MD, CSV) |
| `test_cli_command_handlers.py` | 146 | CLI dispatch for --stats, --org-report, --list-snapshots, discovery inspection, diff config unpacking |
| `test_profile_management.py` | 46 | Interactive profile creation, import, test, show |
| `test_snapshot_commands.py` | 58 | Snapshot creation, comparison, name resolution |
| `test_config_and_resolution.py` | 108 | Config status, validation, stats, name resolution |
| `test_derived_fields_edge_cases.py` | 34 | Derived fields edge cases and coverage |
| `test_diff_command_coverage.py` | 45 | Diff command edge cases and coverage |
| `test_generator_interactive_and_console.py` | 35 | Generator interactive and console tests |
| `test_generator_remaining_coverage.py` | 82 | Generator remaining coverage edge cases |
| `test_interactive_discovery_coverage.py` | 112 | Interactive discovery and helpers coverage |
| `test_lock_backends.py` | 46 | Lock backends edge cases and coverage |
| `test_main_impl_cli_coverage.py` | 90 | _main_impl CLI path coverage |
| `test_main_impl_coverage.py` | 57 | _main_impl coverage edge cases |
| `test_near_100_coverage.py` | 4 | Near-100% coverage gap tests |
| `test_org_cache_branches.py` | 40 | Org cache branch coverage |
| `test_org_writer_coverage.py` | 102 | Org writer edge cases and coverage |
| `test_output_writer_coverage.py` | 36 | Output writer edge cases and coverage |
| `test_backwards_compat.py` | 34 | Backwards compatibility tests |
| `test_exception_contracts.py` | 19 | Exception boundary contract tests |
| `test_parallel_validation.py` | 9 | Parallel validation operations |
| `test_update_test_counts.py` | 2 | Test count validation tests |
| `test_cli_smoke_modes.py` | 10 | CLI smoke tests for core command modes |
| `test_generator_mock_contract.py` | 2 | Generator mock symbol contract tests |
| `test_completion.py` | 43 | Shell completion flag (--completion bash/zsh/fish) |
| `test_exception_narrowing.py` | 50 | Exception narrowing boundary tests |
| `test_coverage_hardening.py` | 108 | Coverage hardening tests |
| `test_trending_models.py` | 18 | Trending dataclass construction and bridge tests |
| `test_trending_discovery.py` | 70 | Snapshot cache discovery, deltas, drift scoring |
| `test_trending_cli.py` | 9 | --trending-window CLI flag parsing |
| `test_trending_output.py` | 22 | Trending output across all 6 formats |
| `test_trending_integration.py` | 15 | Trending backwards compatibility and integration |
| **Total** | **5,672** | **Collected via pytest --collect-only** |

## Running Tests

### Run All Tests

```bash
# Using uv (recommended)
uv run pytest

# Or with activated virtual environment
pytest
```

### Run Specific Test Files

```bash
# Test CLI functionality
uv run pytest tests/test_cli.py

# Test data quality validation
uv run pytest tests/test_data_quality.py

# Test optimized validation
uv run pytest tests/test_optimized_validation.py

# Test output formats
uv run pytest tests/test_output_formats.py

# Test utility functions
uv run pytest tests/test_utils.py

# Test early exit optimization
uv run pytest tests/test_early_exit.py

# Test logging optimization
uv run pytest tests/test_logging_optimization.py

# Test parallel validation
uv run pytest tests/test_parallel_validation.py

# Test validation caching
uv run pytest tests/test_validation_cache.py

# Test dry-run mode
uv run pytest tests/test_dry_run.py

# Test retry with exponential backoff
uv run pytest tests/test_retry.py

# Test environment variable credentials
uv run pytest tests/test_env_credentials.py

# Test enhanced error messages
uv run pytest tests/test_error_messages.py

# Test diff comparison feature
uv run pytest tests/test_diff_comparison.py

# Test edge cases, configuration dataclasses, and custom exceptions
uv run pytest tests/test_edge_cases.py
```

### Run Specific Test Classes or Functions

```bash
# Run a specific test class
uv run pytest tests/test_cli.py::TestCLIArguments

# Run a specific test function
uv run pytest tests/test_cli.py::TestCLIArguments::test_parse_single_data_view
```

### Run Tests with Verbose Output

```bash
uv run pytest -v
```

### Run Tests with Coverage Report

```bash
# Install pytest-cov first
uv add --dev pytest-cov

# Run with coverage
uv run pytest --cov=cja_auto_sdr --cov-report=html --cov-report=term
```

## Test Categories

### CLI Tests (`test_cli.py`)
- **Argument parsing**: Tests command-line argument parsing
- **Data view validation**: Tests data view ID format validation
- **Flag handling**: Tests --version, --quiet, --dry-run, --validate-only, --list-dataviews, --skip-validation, --sample-config, --max-issues flags
- **Cache flags**: Tests --enable-cache, --clear-cache, --cache-size, --cache-ttl flags
- **Constants validation**: Tests that CLI defaults match module constants
- **Sample config generation**: Tests generate_sample_config function
- **UX improvements**: Tests file size formatting and new flags
- **Error handling**: Tests error cases and edge conditions

### Data Quality Tests (`test_data_quality.py`)
- **Duplicate detection**: Tests detection of duplicate component names
- **Missing field detection**: Tests detection of missing required fields
- **Null value detection**: Tests detection of null values in critical fields
- **Severity classification**: Tests proper severity level assignment
- **Clean data handling**: Tests that clean data produces minimal issues

### Optimized Validation Tests (`test_optimized_validation.py`)
- **Single-pass validation**: Tests optimized validation correctness
- **Performance comparison**: Tests performance improvements vs original
- **Vectorized operations**: Tests vectorized pandas operations
- **Edge cases**: Tests handling of special characters, empty data, missing columns

### Output Format Tests (`test_output_formats.py`)
- **CSV output**: Tests CSV file generation and structure
- **JSON output**: Tests JSON format and validity
- **HTML output**: Tests HTML generation and styling
- **Markdown output**: Tests GitHub/Confluence-compatible markdown generation
  - Table formatting and escaping
  - Collapsible sections for large tables
  - Table of contents with anchor links
  - Issue summary with emoji indicators
  - Unicode support
- **Cross-format consistency**: Tests data consistency across formats
- **Unicode handling**: Tests special characters and encoding

### Utility Tests (`test_utils.py`)
- **Logging setup**: Tests log file creation and configuration
- **Config validation**: Tests configuration file validation
- **Filename sanitization**: Tests filename helper functions
- **Performance tracking**: Tests performance measurement utilities

### Early Exit Tests (`test_early_exit.py`)
- **Empty DataFrame handling**: Tests early exit on empty data
- **Missing required fields**: Tests early exit when fields missing
- **Performance impact**: Tests that early exit improves performance

### Environment Credentials Tests (`test_env_credentials.py`)
- **Environment variable loading**: Tests loading credentials from environment variables
- **Priority handling**: Tests that env vars take precedence over config file
- **Partial credentials**: Tests handling of incomplete credentials
- **Missing credentials**: Tests error handling for missing required credentials

### Logging Optimization Tests (`test_logging_optimization.py`)
- **Production mode**: Tests minimal logging in production mode
- **Log level filtering**: Tests conditional logging based on severity
- **Summary logging**: Tests aggregated issue logging
- **Performance impact**: Tests logging overhead reduction

### Parallel Validation Tests (`test_parallel_validation.py`)
- **Concurrent execution**: Tests parallel validation correctness
- **Thread safety**: Tests lock-protected operations
- **Performance benchmarking**: Tests parallel speedup
- **Error handling**: Tests error handling in parallel mode

### Validation Caching Tests (`test_validation_cache.py`)
- **Cache operations**: Tests cache hit/miss behavior
- **LRU eviction**: Tests least recently used eviction
- **TTL expiration**: Tests time-to-live functionality
- **Thread safety**: Tests concurrent cache access
- **Performance**: Tests cache performance improvements

### Retry Tests (`test_retry.py`)
- **Decorator behavior**: Tests retry_with_backoff decorator
- **Exponential backoff**: Tests delay calculation and progression
- **Jitter**: Tests randomization of delays
- **Retryable exceptions**: Tests which exceptions trigger retry
- **Non-retryable exceptions**: Tests immediate failure for non-retryable errors
- **Max retries**: Tests retry limit enforcement
- **Function wrapper**: Tests make_api_call_with_retry function
- **Metadata preservation**: Tests functools.wraps behavior

### Enhanced Error Message Tests (`test_error_messages.py`)
- **HTTP error messages**: Tests all HTTP status code error messages (400, 401, 403, 404, 429, 500, 502, 503, 504)
- **Network error messages**: Tests ConnectionError, TimeoutError, SSLError messages
- **Configuration error messages**: Tests file not found, invalid JSON, missing credentials, invalid format
- **Data view error messages**: Tests not found errors with and without available count
- **Message formatting**: Tests error message structure, sections, and suggestions
- **Documentation links**: Tests that all error messages include help links
- **Integration**: Tests ErrorMessageHelper integration with retry mechanism and validation

### Parallel API Fetcher Tests (`test_parallel_api_fetcher.py`)
- **Initialization**: Tests ParallelAPIFetcher class initialization and configuration
- **fetch_all_data**: Tests parallel data fetching from CJA API
- **_fetch_metrics**: Tests metrics retrieval with error handling
- **_fetch_dimensions**: Tests dimensions retrieval with error handling
- **_fetch_dataview_info**: Tests data view info retrieval with fallback handling
- **Error handling**: Tests graceful handling of API failures and empty responses
- **Logging**: Tests proper logging of fetch operations and errors

### Batch Processor Tests (`test_batch_processor.py`)
- **Initialization**: Tests BatchProcessor class initialization and worker configuration
- **process_batch**: Tests batch processing workflow with multiple data views
- **print_summary**: Tests summary output formatting and statistics
- **Worker coordination**: Tests parallel worker execution and result collection
- **Error handling**: Tests continue-on-error behavior and failure tracking
- **Result aggregation**: Tests collection and reporting of processing results

### Process Single Dataview Tests (`test_process_single_dataview.py`)
- **Success scenarios**: Tests end-to-end processing with valid configuration
- **Output formats**: Tests CSV, JSON, HTML, and Markdown output generation
- **File naming**: Tests output file naming with data view names and IDs
- **Caching**: Tests cache enable/disable configuration
- **Skip validation**: Tests processing with validation disabled
- **Error handling**: Tests handling of API errors and invalid data views
- **Logger configuration**: Tests proper logger setup and teardown

### Excel Formatting Tests (`test_excel_formatting.py`)
- **Metrics sheet**: Tests Metrics sheet formatting and column widths
- **Dimensions sheet**: Tests Dimensions sheet formatting and styles
- **Data Quality sheet**: Tests severity color-coding and formatting
- **Metadata sheet**: Tests key-value pair formatting
- **Column widths**: Tests auto-width calculation and limits
- **Row heights**: Tests row height configuration
- **Multiple sheets**: Tests formatting across all sheet types
- **Error handling**: Tests graceful handling of formatting errors

### CJA Initialization Tests (`test_cja_initialization.py`)
- **initialize_cja**: Tests CJA client initialization with config file and env vars
- **validate_data_view**: Tests data view validation and existence checking
- **list_dataviews**: Tests data view listing and output formatting
- **validate_config_only**: Tests configuration validation without processing
- **Config file loading**: Tests JSON config file parsing and validation
- **Environment credentials**: Tests loading credentials from environment variables
- **Connection testing**: Tests API connection verification
- **Error scenarios**: Tests handling of invalid configs, missing credentials, and API failures

### Diff Comparison Tests (`test_diff_comparison.py`)
- **DataViewSnapshot**: Tests snapshot creation, serialization (to_dict), deserialization (from_dict)
- **SnapshotManager**: Tests save, load, list snapshots, and error handling for invalid files
- **DataViewComparator**: Tests comparison logic, change detection, custom labels, ignore fields
- **DiffSummary**: Tests has_changes property, total_changes calculation
- **DiffOutputWriters**: Tests all output formats (Console, JSON, Markdown, HTML, Excel, CSV)
- **ComparisonFields**: Tests default field comparison (name, title, description, type, schemaPath)
- **ID-based matching**: Tests that components are matched by ID, not by name
- **Metadata comparison**: Tests data view metadata change tracking
- **CLI arguments**: Tests parsing of --diff, --snapshot, --diff-snapshot, --changes-only, --summary, --ignore-fields, --diff-labels
- **Edge cases**: Tests empty snapshots, all added/removed, special characters in names

### Edge Cases Tests (`test_edge_cases.py`)
- **Custom Exception Hierarchy**: Tests CJASDRError, ConfigurationError, APIError, ValidationError, OutputError
- **Configuration Dataclasses**: Tests RetryConfig, CacheConfig, LogConfig, WorkerConfig, SDRConfig
- **SDRConfig.from_args**: Tests configuration creation from command-line arguments
- **Default Configuration Instances**: Tests DEFAULT_RETRY, DEFAULT_CACHE, DEFAULT_LOG, DEFAULT_WORKERS
- **OutputWriter Protocol**: Tests Protocol implementation and runtime checking
- **Retry Edge Cases**: Tests zero retries, zero delay, large exponential base
- **Empty DataFrame Handling**: Tests validation cache and quality checker with empty DataFrames
- **Cache Edge Cases**: Tests size=1, short TTL, identical DataFrame with different item types
- **DataFrame Column Handling**: Tests missing/extra columns in validation
- **Concurrent Access**: Tests cache operations under concurrent load

### Inventory Utils Tests (`test_inventory_utils.py`)
- **Utility functions**: Tests shared utility functions for inventory modules
- **ID extraction**: Tests component ID extraction from various formats
- **Field formatting**: Tests field formatting and normalization
- **Error handling**: Tests graceful handling of invalid inputs
- **Type validation**: Tests type checking and validation utilities

## Test Fixtures

Test fixtures are defined in `conftest.py`:

- **`mock_config_file`**: Creates a temporary mock configuration file
- **`mock_cja_instance`**: Provides a mocked CJA API instance
- **`sample_metrics_df`**: Sample metrics DataFrame for testing
- **`sample_dimensions_df`**: Sample dimensions DataFrame with test data
- **`temp_output_dir`**: Temporary directory for test outputs
- **`large_sample_dataframe`**: Large DataFrame (500 rows) for performance testing
- **`sample_data_dict`**: Complete data dictionary for output format testing
- **`sample_metadata_dict`**: Metadata dictionary for output format testing
- **`large_metrics_df`**: Large metrics DataFrame (1000 rows) for performance testing
- **`large_dimensions_df`**: Large dimensions DataFrame (1000 rows) for performance testing
- **`mock_env_credentials`**: Mock OAuth environment credentials
- **`clean_env`**: Temporarily clears credential environment variables

## Writing New Tests

### Test Naming Conventions

- Test files: `test_*.py`
- Test classes: `Test*`
- Test functions: `test_*`

### Example Test

```python
def test_example_functionality():
    """Test description"""
    # Arrange
    input_data = "test_input"

    # Act
    result = function_under_test(input_data)

    # Assert
    assert result == expected_output
```

### Using Fixtures

```python
def test_with_fixture(mock_config_file):
    """Test using a fixture"""
    result = validate_config_file(mock_config_file)
    assert result is not None
```

## Continuous Integration

These tests can be integrated into CI/CD pipelines:

### GitHub Actions Example

```yaml
name: Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: '3.14'
      - name: Install dependencies
        run: |
          pip install uv
          uv sync
      - name: Run tests
        run: uv run pytest
```

## Test Coverage Goals

- **CLI tests**: 100% coverage of argument parsing and validation
- **Data quality tests**: 90%+ coverage of validation logic
- **Optimized validation**: 95%+ coverage of performance-critical paths
- **Output formats**: 90%+ coverage of all export formats
- **Utility tests**: 80%+ coverage of helper functions
- **Performance tests**: All optimization features benchmarked
- **Thread safety**: Concurrent operations tested under load
- **Overall target**: 85%+ code coverage across all modules

## Troubleshooting

### Tests Failing Locally

1. **Ensure dependencies are installed**:

   ```bash
   uv sync
   ```

2. **Check Python version**:

   ```bash
   python3 --version  # Should be 3.14 or higher
   ```

3. **Clear pytest cache**:

   ```bash
   rm -rf .pytest_cache __pycache__ tests/__pycache__
   ```

### Import Errors

If you see import errors, ensure the project root is in Python path:

```bash
export PYTHONPATH="${PYTHONPATH}:$(pwd)"
uv run pytest
```

## Best Practices

1. **Isolated tests**: Each test should be independent
2. **Mock external dependencies**: Use fixtures to mock API calls
3. **Clear assertions**: Use descriptive assertion messages
4. **Fast execution**: Keep unit tests fast (< 1 second each)
5. **Descriptive names**: Use clear, descriptive test function names

## Sync Test Counts

Regenerate test counts in docs after adding or removing tests:

```bash
.venv/bin/python scripts/update_test_counts.py
```

Check for drift (CI-friendly):

```bash
.venv/bin/python scripts/update_test_counts.py --check
```

## Completed Enhancements

- [x] Performance benchmarking tests (implemented in test_optimized_validation.py)
- [x] Tests for output formats including Excel (test_output_formats.py)
- [x] Tests for batch processing functionality (test_batch_processor.py)
- [x] Comprehensive test coverage (5,672 tests total)
- [x] Org-wide analysis tests (test_org_report.py) - 175 tests (including large org scaling, output path aliases, memory warnings, smart cache invalidation)
- [x] Org-wide analysis integration tests (test_org_report_integration.py) - 17 tests (end-to-end flows, caching, filtering, governance thresholds)
- [x] Profile management tests (test_profiles.py) - 77 tests
- [x] API worker auto-tuning tests (test_api_tuning.py) - 23 tests
- [x] Circuit breaker pattern tests (test_circuit_breaker.py) - 22 tests
- [x] Shared validation cache tests (test_shared_cache.py) - 22 tests
- [x] Calculated metrics inventory tests (test_calculated_metrics_inventory.py) - 285 tests
- [x] Segments inventory tests (test_segments_inventory.py) - 48 tests
- [x] Derived fields inventory tests (test_derived_inventory.py) - 62 tests
- [x] Inventory utilities tests (test_inventory_utils.py) - 47 tests
- [x] Git integration tests (test_git_integration.py) - 40 tests
- [x] Inventory diff support in snapshot comparisons (test_diff_comparison.py) - 169 tests
- [x] Inventory summary and include-all-inventory tests (test_ux_features.py) - 123 tests
- [x] Parallel validation tests (test_parallel_validation.py)
- [x] Validation caching tests (test_validation_cache.py)
- [x] Early exit optimization tests (test_early_exit.py)
- [x] Logging optimization tests (test_logging_optimization.py)
- [x] Retry with exponential backoff tests (test_retry.py)
- [x] CLI quick wins tests: --version, --quiet flags (test_cli.py)
- [x] Cache flags tests: --enable-cache, --clear-cache, --cache-size, --cache-ttl (test_cli.py)
- [x] Constants validation tests (test_cli.py)
- [x] Environment variable credentials tests (test_env_credentials.py)
- [x] Parallel API fetcher tests (test_parallel_api_fetcher.py)
- [x] Process single dataview tests (test_process_single_dataview.py)
- [x] Excel formatting tests (test_excel_formatting.py)
- [x] CJA initialization tests (test_cja_initialization.py)
- [x] Name resolution tests (test_name_resolution.py)
- [x] Data view diff comparison tests (test_diff_comparison.py) - 169 tests covering snapshots, comparison logic, output formats, CLI arguments, name resolution
- [x] Edge case tests (test_edge_cases.py) - 39 tests covering custom exceptions, configuration dataclasses, OutputWriter Protocol, boundary conditions

## Future Enhancements

- [ ] Add integration tests with actual CJA API (optional, requires credentials)
- [ ] Add end-to-end tests with real data views (optional)
- [ ] Add load testing for batch processing at scale (50+ data views)
- [ ] Add memory profiling tests for large datasets
- [ ] Add network failure simulation tests
