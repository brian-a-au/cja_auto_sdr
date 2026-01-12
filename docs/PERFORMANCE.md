# Performance Guide

Technical details and optimization options for the CJA SDR Generator.

## Performance Overview

The generator includes multiple optimization features:

| Feature | Performance Gain |
|---------|------------------|
| Parallel batch processing | 3-4x faster |
| Optimized validation | 30-50% faster |
| Validation caching | 50-90% faster on cache hits |
| Skip validation mode | 20-30% faster |
| Production logging mode | 5-10% faster |

## Batch Processing

### How It Works

When processing multiple data views, the generator uses `ProcessPoolExecutor` for true parallel processing:

```
Sequential: 10 data views × 35s = 350 seconds (5.8 minutes)
Parallel:   10 data views / 4 workers × 35s = ~87.5 seconds (1.5 minutes)
Result:     4x faster (75% time savings)
```

### Configuring Workers

```bash
# Default (4 workers)
uv run python cja_sdr_generator.py dv_1 dv_2 dv_3

# Conservative (shared API, rate limits)
uv run python cja_sdr_generator.py --batch dv_* --workers 2

# Aggressive (dedicated infrastructure)
uv run python cja_sdr_generator.py --batch dv_* --workers 8
```

### Worker Optimization Guide

| Workers | Throughput (10 views) | Best For |
|---------|----------------------|----------|
| 1 | ~350s (sequential) | Testing, debugging |
| 2 | ~175s (2x faster) | Shared API, conservative |
| 4 | ~87s (4x faster) | Default, balanced |
| 8 | ~44s (8x faster) | Dedicated infrastructure |

### Batch Processing Tips

- Use `--continue-on-error` for resilient batch operations
- Monitor worker utilization - too many workers may hit API rate limits
- Run during off-peak hours for large batches
- Check batch summary for performance metrics

## Optimized Validation

### Architecture

The validation engine uses single-pass DataFrame scanning with vectorized operations:

**Before optimization (v1.0):**
```python
# 9 separate DataFrame scans
check_empty_dataframe(metrics)      # Scan 1
check_required_fields(metrics)      # Scan 2
check_duplicates(metrics)           # Scan 3
check_null_values(metrics)          # Scans 4-7
check_missing_descriptions(metrics) # Scan 8
check_id_validity(metrics)          # Scan 9
```

**After optimization (v3.0):**
```python
# Single optimized scan
check_all_quality_issues_optimized(metrics, 'Metrics', ...)
# 89% reduction in DataFrame scans
```

### Performance by Dataset Size

| Dataset Size | Before | After | Improvement |
|--------------|--------|-------|-------------|
| Small (50 components) | 0.5s | 0.5s | Marginal |
| Medium (150 components) | 1.8s | 1.0s | 44% faster |
| Large (225+ components) | 2.5s | 1.2s | 52% faster |
| Enterprise (500+) | 5.2s | 2.8s | 46% faster |

## Validation Caching

### Overview

Validation caching stores results in memory, eliminating redundant validation when processing identical data.

### Enabling Cache

```bash
# Basic (defaults: 1000 entries, 1 hour TTL)
uv run python cja_sdr_generator.py dv_12345 --enable-cache

# Custom cache size
uv run python cja_sdr_generator.py dv_12345 --enable-cache --cache-size 5000

# Custom TTL (2 hours)
uv run python cja_sdr_generator.py dv_12345 --enable-cache --cache-ttl 7200

# Clear cache before processing
uv run python cja_sdr_generator.py dv_12345 --enable-cache --clear-cache
```

### Cache Performance

| Validation Type | Without Cache | With Cache (Hit) | Improvement |
|-----------------|---------------|------------------|-------------|
| Small (50) | 0.5s | 0.05s | 90% faster |
| Medium (150) | 1.0s | 0.10s | 90% faster |
| Large (225) | 1.2s | 0.12s | 90% faster |
| Enterprise (500+) | 2.8s | 0.28s | 90% faster |

### When to Use Caching

**Ideal scenarios:**
- Development iterations with same data
- Batch processing similar data views
- CI/CD pipelines on unchanged data
- Regression testing

**Less effective for:**
- First-time processing of unique data
- Constantly changing datasets
- Single-run operations

### Cache Statistics

When enabled, statistics appear in output:

```
============================================================
VALIDATION CACHE STATISTICS
============================================================
Cache Hits:        9
Cache Misses:      3
Hit Rate:          75.0%
Cache Size:        3/1000
Evictions:         0
Estimated Time Saved: 0.44s
============================================================
```

### Interpreting Hit Rates

| Hit Rate | Effectiveness | Recommendation |
|----------|---------------|----------------|
| 80-100% | Excellent | Continue using cache |
| 50-80% | Good | Significant benefit |
| 20-50% | Moderate | Consider if worth it |
| 0-20% | Poor | Disable cache |

## Quick Performance Options

### Skip Validation

For fastest processing when quality checks aren't needed:

```bash
uv run python cja_sdr_generator.py dv_12345 --skip-validation
```

**Impact**: 20-30% faster overall

### Production Mode

Minimal logging for maximum performance:

```bash
uv run python cja_sdr_generator.py dv_12345 --production
```

**Impact**: 5-10% faster

### Quiet Mode

Suppress console output:

```bash
uv run python cja_sdr_generator.py dv_12345 --quiet
```

### Combined Optimization

```bash
# Maximum performance
uv run python cja_sdr_generator.py dv_12345 \
  --production \
  --skip-validation \
  --quiet
```

## Automatic Retry

The generator automatically retries on transient network errors:

### Retry Configuration

```
Max Retries:      3 attempts after initial failure
Base Delay:       1.0 seconds
Max Delay:        30.0 seconds (cap)
Backoff Formula:  delay = min(base_delay * 2^attempt, max_delay)
Jitter:           Enabled (±50% randomization)
```

### Retry Sequence Example

```
Attempt 1: API call fails (ConnectionError)
  → Wait ~1.0s (with jitter: 0.5-1.5s)
Attempt 2: API call fails (ConnectionError)
  → Wait ~2.0s (with jitter: 1.0-3.0s)
Attempt 3: API call fails (ConnectionError)
  → Wait ~4.0s (with jitter: 2.0-6.0s)
Attempt 4: API call fails
  → Error raised, processing stops
```

### Retryable vs Non-Retryable Errors

**Retryable** (automatic retry):
- `ConnectionError`
- `TimeoutError`
- `OSError` (network-related)

**Non-retryable** (fail immediately):
- `ValueError`
- `KeyError`
- `AttributeError`
- Authentication errors

## Performance Monitoring

### Log-Based Monitoring

Check validation timing:

```bash
grep "Data Quality Validation completed" logs/*.log
# Output: ⏱️  Data Quality Validation completed in 1.23s
```

### Performance Summary

Logs include detailed timing breakdown:

```
============================================================
PERFORMANCE SUMMARY
============================================================
Parallel API Fetch                 :   3.45s ( 32.1%)
Data Quality Validation            :   1.23s ( 11.4%)
Processing data for Excel export   :   2.87s ( 26.7%)
Generating Excel file              :   3.20s ( 29.8%)
============================================================
Total Execution Time               :  10.75s
============================================================
```

## Technical Details

### Parallel Processing

- Uses `ProcessPoolExecutor` for CPU-bound operations
- No Python GIL limitations
- Separate processes for each data view
- Thread-safe logging and file operations

### Vectorized Validation

- Uses pandas vectorized operations
- Single DataFrame traversal
- Reduced memory allocations
- Better CPU cache utilization

### Cache Implementation

- Content-based hashing using `pandas.util.hash_pandas_object`
- LRU eviction policy
- TTL expiration
- Thread-safe with `threading.Lock()`

## See Also

- [CLI Reference](CLI_REFERENCE.md) - Performance-related flags
- [Batch Processing Guide](BATCH_PROCESSING_GUIDE.md) - Detailed batch documentation
- [Optimization Summary](OPTIMIZATION_SUMMARY.md) - Technical implementation details
- [Stress Test Results](STRESS_TEST_RESULTS.md) - Benchmark data
