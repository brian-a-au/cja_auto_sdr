# Performance Guide

Technical details and optimization options for the CJA SDR Generator.

> **Note:** Performance benchmarks in this guide were measured with v3.0.15. Actual performance may vary based on network conditions, API rate limits, and data view size.

## Performance Overview

The generator includes multiple optimization features:

| Feature | Performance Gain |
|---------|------------------|
| Parallel batch processing | 3-4x faster |
| Optimized validation | 30-50% faster |
| Validation caching | 50-90% faster on cache hits |
| Skip validation mode | 20-30% faster |
| Production logging mode | 5-10% faster |
| Name resolution caching | 5-minute API cache for data view listings |
| Snapshot comparison | No API calls (instant for large datasets) |

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
# Default (auto-detect based on CPU cores and workload)
cja_auto_sdr dv_1 dv_2 dv_3
# Shows: "Auto-detected workers: 4 (based on 8 CPU cores, 3 data views)"

# Conservative (shared API, rate limits)
cja_auto_sdr --batch dv_* --workers 2

# Aggressive (dedicated infrastructure)
cja_auto_sdr --batch dv_* --workers 8
```

> **Note:** The default `--workers auto` intelligently selects worker count based on CPU cores, number of data views, and component complexity. It automatically reduces workers for large data views (>5000 components) to prevent memory exhaustion.

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
cja_auto_sdr dv_12345 --enable-cache

# Custom cache size
cja_auto_sdr dv_12345 --enable-cache --cache-size 5000

# Custom TTL (2 hours)
cja_auto_sdr dv_12345 --enable-cache --cache-ttl 7200

# Clear cache before processing
cja_auto_sdr dv_12345 --enable-cache --clear-cache
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
cja_auto_sdr dv_12345 --skip-validation
```

**Impact**: 20-30% faster overall

### Production Mode

Minimal logging for maximum performance:

```bash
cja_auto_sdr dv_12345 --production
```

**Impact**: 5-10% faster

### Quiet Mode

Suppress console output:

```bash
cja_auto_sdr dv_12345 --quiet
```

### Combined Optimization

```bash
# Maximum performance
cja_auto_sdr dv_12345 \
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

## Diff Comparison Performance

### Comparison Types

| Operation | API Calls | Performance |
|-----------|-----------|-------------|
| `--diff dv_12345 dv_67890` | 2 (fetch both data views) | ~5-10s |
| `--diff-snapshot baseline.json` | 1 (fetch current state) | ~3-5s |
| `--compare-snapshots A.json B.json` | 0 (pure file comparison) | <1s |

### Snapshot-to-Snapshot Comparison

The `--compare-snapshots` option requires **no API calls**, making it ideal for:
- Offline historical analysis
- CI/CD pipelines without API credentials
- Comparing archived states
- Batch comparisons of many snapshot pairs

```bash
# Instant comparison of two 500+ component data views
cja_auto_sdr --compare-snapshots ./q1.json ./q2.json  # <1 second
```

### Name Resolution Caching

When using data view names (instead of IDs), the tool caches the data view listing from the API for 5 minutes:

**Benefits:**
- Subsequent name lookups don't require API calls
- Faster batch operations with names
- Reduced API quota usage

**Cache behavior:**
```
First call:   API call to fetch data view list → cache for 5 min
Second call:  Cache hit (no API call)
After 5 min:  Cache expired → fresh API call
```

**Optimization:** If processing many data views by name, run them together:
```bash
# Single API call for name resolution (cached)
cja_auto_sdr "Prod" "Staging" "Test" "Dev"
```

### Auto-Snapshot Performance

Auto-snapshot has minimal overhead:
- Writes JSON files asynchronously after comparison
- Retention policy cleanup is file-system only
- No impact on comparison speed

```bash
# Same performance as regular diff
cja_auto_sdr --diff dv_12345 dv_67890 --auto-snapshot --keep-last 10
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
```
```
⏱️  Data Quality Validation completed in 1.23s
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

### Enterprise Logging (JSON Format)

For log aggregation systems (Splunk, ELK, CloudWatch), use structured JSON logging:

```bash
# Enable JSON logging
cja_auto_sdr dv_12345 --log-format json

# Output format (one JSON object per line):
{"timestamp": "2026-01-23T15:11:50", "level": "INFO", "logger": "cja_sdr_generator", "message": "Processing data view", "module": "cja_sdr_generator", "function": "process_single_dataview", "line": 6683}
```

**Benefits:**
- Machine-parseable log entries
- Structured fields for filtering and alerting
- Exception stack traces in dedicated `exception` field
- Compatible with all major log aggregation platforms

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

- [Configuration Guide](CONFIGURATION.md) - Environment variables for CI/CD optimization
- [CLI Reference](CLI_REFERENCE.md) - Performance-related flags
- [Data View Comparison Guide](DIFF_COMPARISON.md) - Diff, snapshots, and CI/CD integration
- [Batch Processing Guide](BATCH_PROCESSING_GUIDE.md) - Detailed batch documentation
