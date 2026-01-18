# CJA SDR Generator - Test Suite

This directory contains automated tests for the CJA SDR Generator.

## Test Structure

```
tests/
├── __init__.py                      # Test package initialization
├── conftest.py                      # Pytest fixtures and configuration
├── test_batch_processor.py          # Batch processor tests
├── test_cja_initialization.py       # CJA initialization and validation tests
├── test_cli.py                      # Command-line interface tests
├── test_data_quality.py             # Data quality validation tests
├── test_dry_run.py                  # Dry-run mode tests
├── test_early_exit.py               # Early exit optimization tests
├── test_env_credentials.py          # Environment variable credentials tests
├── test_error_messages.py           # Enhanced error message tests
├── test_excel_formatting.py         # Excel formatting tests
├── test_logging_optimization.py     # Logging optimization tests
├── test_name_resolution.py          # Data view name resolution tests
├── test_optimized_validation.py     # Optimized validation tests
├── test_output_formats.py           # Output format tests
├── test_parallel_api_fetcher.py     # Parallel API fetcher tests
├── test_parallel_validation.py      # Parallel validation tests
├── test_process_single_dataview.py  # Single data view processing tests
├── test_retry.py                    # Retry with exponential backoff tests
├── test_utils.py                    # Utility function tests
├── test_validation_cache.py         # Validation caching tests
├── test_diff_comparison.py          # Data view diff comparison tests
├── test_edge_cases.py               # Edge cases and configuration tests
└── README.md                        # This file
```

**Total: 596 comprehensive tests**

### Test Count Breakdown

| Test File | Tests | Coverage Area |
|-----------|-------|---------------|
| `test_diff_comparison.py` | 139 | Data view diff comparison feature |
| `test_cli.py` | 76 | Command-line interface and argument parsing |
| `test_edge_cases.py` | 39 | Edge cases, configuration dataclasses, custom exceptions |
| `test_output_formats.py` | 32 | CSV, JSON, HTML, Markdown output generation |
| `test_cja_initialization.py` | 32 | CJA connection and configuration validation |
| `test_utils.py` | 27 | Utility functions and helpers |
| `test_excel_formatting.py` | 25 | Excel sheet formatting and styling |
| `test_parallel_api_fetcher.py` | 24 | Parallel API data fetching |
| `test_error_messages.py` | 23 | Enhanced error messages and guidance |
| `test_retry.py` | 21 | Retry with exponential backoff |
| `test_batch_processor.py` | 20 | Batch processing of multiple data views |
| `test_validation_cache.py` | 19 | Validation result caching |
| `test_process_single_dataview.py` | 18 | End-to-end single data view processing |
| `test_optimized_validation.py` | 16 | Optimized data quality validation |
| `test_name_resolution.py` | 16 | Data view name to ID resolution |
| `test_logging_optimization.py` | 15 | Logging performance optimizations |
| `test_env_credentials.py` | 13 | Environment variable credentials |
| `test_dry_run.py` | 12 | Dry-run mode functionality |
| `test_early_exit.py` | 11 | Early exit optimizations |
| `test_data_quality.py` | 10 | Data quality validation logic |
| `test_parallel_validation.py` | 8 | Parallel validation operations |
| **Total** | **596** | **100% pass rate** |

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
uv run pytest --cov=cja_sdr_generator --cov-report=html --cov-report=term
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
   python --version  # Should be 3.14 or higher
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

## Completed Enhancements

- [x] Performance benchmarking tests (implemented in test_optimized_validation.py)
- [x] Tests for output formats including Excel (test_output_formats.py)
- [x] Tests for batch processing functionality (test_batch_processor.py)
- [x] Comprehensive test coverage (596 tests total)
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
- [x] Data view diff comparison tests (test_diff_comparison.py) - 139 tests covering snapshots, comparison logic, output formats, CLI arguments, name resolution
- [x] Edge case tests (test_edge_cases.py) - 39 tests covering custom exceptions, configuration dataclasses, OutputWriter Protocol, boundary conditions

## Future Enhancements

- [ ] Add integration tests with actual CJA API (optional, requires credentials)
- [ ] Add end-to-end tests with real data views (optional)
- [ ] Add load testing for batch processing at scale (50+ data views)
- [ ] Add memory profiling tests for large datasets
- [ ] Add network failure simulation tests
