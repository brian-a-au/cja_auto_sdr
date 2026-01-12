# CJA SDR Generator - Batch Processing Guide

## Overview

The CJA SDR Generator now supports high-performance batch processing with **3-4x throughput improvement** through parallel multiprocessing.

## Quick Start

### Single Data View

```bash
# Process a single data view
uv run python cja_sdr_generator.py dv_677ea9291244fd082f02dd42
```

### Multiple Data Views (Automatic Batch Mode)

```bash
# Automatically triggers parallel batch processing
uv run python cja_sdr_generator.py dv_12345 dv_67890 dv_abcde
```

**Note:** When you provide multiple data view IDs, the script automatically enables parallel processing with 4 workers by default. The `--batch` flag is optional.

### Batch Processing with Custom Configuration

```bash
# Explicitly use batch mode with custom settings
uv run python cja_sdr_generator.py --batch dv_12345 dv_67890 dv_abcde dv_11111 --workers 8
```

## Command-Line Arguments

### Required Arguments

- `DATA_VIEW_ID [DATA_VIEW_ID ...]` - One or more data view IDs (must start with `dv_`)

### Optional Arguments

| Argument | Description | Default |
|----------|-------------|---------|
| `--batch` | Explicitly enable batch mode (optional with multiple data views) | Auto-detect (parallel if multiple data views) |
| `--workers N` | Number of parallel workers (1-256) | 4 |
| `--output-dir PATH` | Output directory for generated files | Current directory |
| `--config-file PATH` | Path to CJA configuration file | myconfig.json |
| `--continue-on-error` | Continue processing if one data view fails | Stop on first error |
| `--log-level LEVEL` | Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL) | INFO |
| `--enable-cache` | Enable validation result caching | Disabled |
| `--clear-cache` | Clear cache before processing (use with --enable-cache) | - |
| `--cache-size N` | Maximum cached entries (>= 1) | 1000 |
| `--cache-ttl N` | Cache time-to-live in seconds (>= 1) | 3600 |
| `-h, --help` | Show help message and exit | - |

## Usage Examples

### Basic Examples

```bash
# Single data view
uv run python cja_sdr_generator.py dv_12345

# Multiple data views (automatically triggers parallel batch processing)
uv run python cja_sdr_generator.py dv_12345 dv_67890 dv_abcde

# Explicitly use batch mode (same result as above when multiple data views)
uv run python cja_sdr_generator.py --batch dv_12345 dv_67890 dv_abcde
```

### Advanced Examples

```bash
# Custom number of workers (conservative for shared API)
uv run python cja_sdr_generator.py --batch dv_12345 dv_67890 --workers 2

# Custom output directory
uv run python cja_sdr_generator.py dv_12345 --output-dir ./reports

# Continue processing even if some data views fail
uv run python cja_sdr_generator.py --batch dv_12345 dv_67890 dv_abcde --continue-on-error

# Batch processing with custom log level
uv run python cja_sdr_generator.py --batch dv_* --log-level WARNING

# Full production example
uv run python cja_sdr_generator.py --batch \
  dv_prod_12345 dv_staging_67890 dv_dev_abcde \
  --workers 4 \
  --output-dir ./sdr_reports \
  --continue-on-error \
  --log-level INFO
```

### Reading Data Views from a File

```bash
# Create a file with data view IDs (one per line)
cat > dataviews.txt <<EOF
dv_production_12345
dv_staging_67890
dv_development_abcde
dv_testing_99999
EOF

# Process all data views from file
uv run python cja_sdr_generator.py --batch $(cat dataviews.txt)

# With continue-on-error
uv run python cja_sdr_generator.py --batch \
  $(cat dataviews.txt) \
  --continue-on-error \
  --output-dir ./batch_reports
```

## Error Handling

### No Arguments Provided

```bash
$ uv run python cja_sdr_generator.py

usage: cja_sdr_generator.py [-h] [--batch] ... DATA_VIEW_ID [DATA_VIEW_ID ...]
cja_sdr_generator.py: error: the following arguments are required: DATA_VIEW_ID
```

### Invalid Data View ID Format

```bash
$ uv run python cja_sdr_generator.py invalid_id test123

ERROR: Invalid data view ID format: invalid_id, test123
       Data view IDs should start with 'dv_'
       Example: dv_677ea9291244fd082f02dd42
```

### Help Output

```bash
$ uv run python cja_sdr_generator.py --help

# Displays full help with all options and examples
```

## Performance Comparison

### Single Data View Processing
```
1 data view × 35s = 35 seconds per data view
```

### Multiple Data Views (Automatic Parallel Batch Processing with 4 Workers)
```
10 data views / 4 workers × 35s = ~87.5 seconds (1.5 minutes)
Improvement: 4x faster than processing individually (75% time savings)
```

**Note:** Multiple data views automatically trigger parallel batch processing for optimal performance.

### Worker Optimization

| Workers | Best For | Performance |
|---------|----------|-------------|
| 1 | Testing, debugging | Baseline (100%) |
| 2 | Shared API, conservative | ~2x faster |
| 4 | Default, balanced | ~4x faster |
| 8 | Dedicated infrastructure | ~8x faster |

**Note:** Actual performance depends on API rate limits, network latency, and system resources.

## Batch Processing Output

### Console Output

```
Processing 10 data view(s) in batch mode with 4 workers...

2026-01-07 12:00:00 - INFO - ============================================================
2026-01-07 12:00:00 - INFO - BATCH PROCESSING START
2026-01-07 12:00:00 - INFO - ============================================================
2026-01-07 12:00:00 - INFO - Data views to process: 10
2026-01-07 12:00:00 - INFO - Parallel workers: 4
2026-01-07 12:00:00 - INFO - Continue on error: False
2026-01-07 12:00:00 - INFO - Output directory: .
2026-01-07 12:00:00 - INFO - ============================================================

2026-01-07 12:00:15 - INFO - ✓ dv_12345: SUCCESS (14.5s)
2026-01-07 12:00:16 - INFO - ✓ dv_67890: SUCCESS (15.2s)
2026-01-07 12:00:18 - ERROR - ✗ dv_abc123: FAILED - Data view validation failed
2026-01-07 12:00:20 - INFO - ✓ dv_def456: SUCCESS (16.1s)
...

============================================================
BATCH PROCESSING SUMMARY
============================================================
Total data views: 10
Successful: 8
Failed: 2
Success rate: 80.0%
Total duration: 125.3s
Average per data view: 15.7s

Successful Data Views:
  ✓ dv_12345         Production Analytics        14.5s
  ✓ dv_67890         Development Analytics       15.2s
  ✓ dv_def456        Testing Analytics           16.1s
  ...

Failed Data Views:
  ✗ dv_abc123        Data view validation failed
  ✗ dv_xyz789        No metrics or dimensions found

============================================================
Throughput: 4.8 data views per minute
============================================================
```

### Log Files

**Batch Mode:**

- `logs/SDR_Batch_Generation_YYYYMMDD_HHMMSS.log` - Main batch log

**Single Mode:**

- `logs/SDR_Generation_{DATA_VIEW_ID}_YYYYMMDD_HHMMSS.log` - Per data view log

## Scheduled Processing

### Cron Job Example

```bash
# Add to crontab (crontab -e)

# Process all data views nightly at 2 AM
0 2 * * * cd /path/to/project && uv run python cja_sdr_generator.py \
  --batch dv_prod_1 dv_prod_2 dv_prod_3 \
  --output-dir /reports/$(date +\%Y\%m\%d) \
  --continue-on-error \
  --log-level WARNING

# Process weekly on Sunday at midnight
0 0 * * 0 cd /path/to/project && uv run python cja_sdr_generator.py \
  --batch $(cat /path/to/dataviews.txt) \
  --workers 8 \
  --output-dir /weekly_reports/$(date +\%Y_week_\%V) \
  --continue-on-error
```

## Best Practices

### 1. Worker Configuration

```bash
# Conservative (shared API with rate limits)
--workers 2

# Balanced (default, works well for most cases)
--workers 4

# Aggressive (dedicated infrastructure)
--workers 8
```

### 2. Error Handling

```bash
# Stop on first error (default, good for testing)
uv run python cja_sdr_generator.py --batch dv_1 dv_2 dv_3

# Continue on error (good for production, get as many as possible)
uv run python cja_sdr_generator.py --batch dv_1 dv_2 dv_3 --continue-on-error
```

### 3. Output Organization

```bash
# Organize by date
--output-dir ./reports/$(date +%Y/%m/%d)

# Organize by environment
--output-dir ./reports/production
--output-dir ./reports/staging
```

### 4. Logging Levels

```bash
# Development/debugging
--log-level DEBUG

# Production (default)
--log-level INFO

# Production (quiet, only warnings/errors)
--log-level WARNING
```

## Troubleshooting

### Issue: "No module named 'cjapy'"

**Solution:** Use `uv run` to execute the script:

```bash
uv run python cja_sdr_generator.py dv_12345
```

### Issue: "error: the following arguments are required: DATA_VIEW_ID"

**Solution:** Provide at least one data view ID:

```bash
uv run python cja_sdr_generator.py dv_12345
```

### Issue: "Invalid data view ID format"

**Solution:** Ensure data view IDs start with `dv_`:

```bash
# Wrong
uv run python cja_sdr_generator.py 12345

# Correct
uv run python cja_sdr_generator.py dv_12345
```

### Issue: Permission denied writing Excel file

**Solution:** Close any open Excel files or specify a different output directory:

```bash
uv run python cja_sdr_generator.py dv_12345 --output-dir ./new_reports
```

### Issue: API rate limiting

**Solution:** Reduce the number of workers:

```bash
uv run python cja_sdr_generator.py --batch dv_1 dv_2 dv_3 --workers 2
```

## Migration from Old Version

### Before (Hardcoded Data View)

```python
# Old way: Edit script to change data view
data_view = "dv_677ea9291244fd082f02dd42"
python cja_sdr_generator.py
```

### After (Command-Line Arguments)

```bash
# New way: Specify data view(s) as arguments
uv run python cja_sdr_generator.py dv_677ea9291244fd082f02dd42

# Or multiple at once
uv run python cja_sdr_generator.py dv_12345 dv_67890
```

## Technical Details

### Multiprocessing Architecture

- **ProcessPoolExecutor:** True parallelism (separate processes)
- **No GIL limitations:** Full CPU utilization
- **Isolated processing:** Each data view runs in its own process
- **Fault tolerance:** One failure doesn't affect others

### Memory Management

- Each worker process has its own memory space
- No shared state between workers
- Automatic cleanup after completion
- Suitable for processing large datasets

### API Efficiency

- Parallel API calls to CJA endpoints
- ThreadPoolExecutor for I/O-bound API fetching within each process
- Optimized to minimize API call overhead
- Respects API rate limits (adjust workers as needed)

## Support

For issues, questions, or feature requests:

1. Check this guide first
2. Review error messages and logs
3. Try with `--log-level DEBUG` for detailed output
4. Use `--help` to see all available options
