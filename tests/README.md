# CJA SDR Generator - Test Suite

This directory contains automated tests for the CJA SDR Generator.

## Test Structure

```
tests/
├── __init__.py                      # Test package initialization
├── conftest.py                      # Pytest fixtures and configuration
├── test_cli.py                      # Command-line interface tests (29 tests)
├── test_data_quality.py             # Data quality validation tests (10 tests)
├── test_dry_run.py                  # Dry-run mode tests (12 tests)
├── test_early_exit.py               # Early exit optimization tests (11 tests)
├── test_logging_optimization.py     # Logging optimization tests (15 tests)
├── test_optimized_validation.py     # Optimized validation tests (16 tests)
├── test_output_formats.py           # Output format tests (22 tests)
├── test_parallel_validation.py      # Parallel validation tests (8 tests)
├── test_retry.py                    # Retry with exponential backoff tests (21 tests)
├── test_utils.py                    # Utility function tests (14 tests)
├── test_validation_cache.py         # Validation caching tests (15 tests)
└── README.md                        # This file
```

**Total: 171 comprehensive tests**

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

### CLI Tests (`test_cli.py` - 29 tests)
- **Argument parsing**: Tests command-line argument parsing
- **Data view validation**: Tests data view ID format validation
- **Flag handling**: Tests --version, --quiet, --dry-run, --list-dataviews, --skip-validation, --sample-config flags
- **Sample config generation**: Tests generate_sample_config function
- **Error handling**: Tests error cases and edge conditions

### Data Quality Tests (`test_data_quality.py` - 10 tests)
- **Duplicate detection**: Tests detection of duplicate component names
- **Missing field detection**: Tests detection of missing required fields
- **Null value detection**: Tests detection of null values in critical fields
- **Severity classification**: Tests proper severity level assignment
- **Clean data handling**: Tests that clean data produces minimal issues

### Optimized Validation Tests (`test_optimized_validation.py` - 16 tests)
- **Single-pass validation**: Tests optimized validation correctness
- **Performance comparison**: Tests performance improvements vs original
- **Vectorized operations**: Tests vectorized pandas operations
- **Edge cases**: Tests handling of special characters, empty data, missing columns

### Output Format Tests (`test_output_formats.py` - 22 tests)
- **CSV output**: Tests CSV file generation and structure
- **JSON output**: Tests JSON format and validity
- **HTML output**: Tests HTML generation and styling
- **Cross-format consistency**: Tests data consistency across formats
- **Unicode handling**: Tests special characters and encoding

### Utility Tests (`test_utils.py` - 14 tests)
- **Logging setup**: Tests log file creation and configuration
- **Config validation**: Tests configuration file validation
- **Filename sanitization**: Tests filename helper functions
- **Performance tracking**: Tests performance measurement utilities

### Early Exit Tests (`test_early_exit.py` - 11 tests)
- **Empty DataFrame handling**: Tests early exit on empty data
- **Missing required fields**: Tests early exit when fields missing
- **Performance impact**: Tests that early exit improves performance

### Logging Optimization Tests (`test_logging_optimization.py` - 15 tests)
- **Production mode**: Tests minimal logging in production mode
- **Log level filtering**: Tests conditional logging based on severity
- **Summary logging**: Tests aggregated issue logging
- **Performance impact**: Tests logging overhead reduction

### Parallel Validation Tests (`test_parallel_validation.py` - 8 tests)
- **Concurrent execution**: Tests parallel validation correctness
- **Thread safety**: Tests lock-protected operations
- **Performance benchmarking**: Tests parallel speedup
- **Error handling**: Tests error handling in parallel mode

### Validation Caching Tests (`test_validation_cache.py` - 15 tests)
- **Cache operations**: Tests cache hit/miss behavior
- **LRU eviction**: Tests least recently used eviction
- **TTL expiration**: Tests time-to-live functionality
- **Thread safety**: Tests concurrent cache access
- **Performance**: Tests cache performance improvements

### Retry Tests (`test_retry.py` - 21 tests)
- **Decorator behavior**: Tests retry_with_backoff decorator
- **Exponential backoff**: Tests delay calculation and progression
- **Jitter**: Tests randomization of delays
- **Retryable exceptions**: Tests which exceptions trigger retry
- **Non-retryable exceptions**: Tests immediate failure for non-retryable errors
- **Max retries**: Tests retry limit enforcement
- **Function wrapper**: Tests make_api_call_with_retry function
- **Metadata preservation**: Tests functools.wraps behavior

## Test Fixtures

Test fixtures are defined in `conftest.py`:

- **`mock_config_file`**: Creates a temporary mock configuration file
- **`mock_cja_instance`**: Provides a mocked CJA API instance
- **`sample_metrics_df`**: Sample metrics DataFrame for testing
- **`sample_dimensions_df`**: Sample dimensions DataFrame with test data
- **`temp_output_dir`**: Temporary directory for test outputs

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
   python --version  # Should be 3.14+
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
- [x] Tests for batch processing functionality (covered in CLI tests)
- [x] Comprehensive test coverage (161 tests total)
- [x] Parallel validation tests (test_parallel_validation.py)
- [x] Validation caching tests (test_validation_cache.py)
- [x] Early exit optimization tests (test_early_exit.py)
- [x] Logging optimization tests (test_logging_optimization.py)
- [x] Retry with exponential backoff tests (test_retry.py)
- [x] CLI quick wins tests: --version, --quiet flags (test_cli.py)

## Future Enhancements

- [ ] Add integration tests with actual CJA API (optional, requires credentials)
- [ ] Add end-to-end tests with real data views (optional)
- [ ] Add load testing for batch processing at scale (50+ data views)
- [ ] Add memory profiling tests for large datasets
- [ ] Add network failure simulation tests
