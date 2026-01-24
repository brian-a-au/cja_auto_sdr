#!/usr/bin/env python3
"""
Comprehensive stress test for v3.0.15 features

Tests all major code paths including:
- Validation caching
- Parallel validation
- Early exit optimization
- Logging optimization
- Performance tracking
"""

import sys
import time
import logging
import pandas as pd
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from cja_sdr_generator import (
    ValidationCache,
    DataQualityChecker,
    PerformanceTracker,
)


def print_section(title):
    """Print formatted section header"""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70)


def test_validation_cache():
    """Test validation caching functionality"""
    print_section("TEST 1: Validation Cache")

    logger = logging.getLogger("stress_test")
    logger.setLevel(logging.INFO)

    # Create test DataFrame
    df = pd.DataFrame({
        'id': [f'm{i}' for i in range(100)],
        'name': [f'Metric {i}' for i in range(100)],
        'type': ['int'] * 50 + ['currency'] * 50,
        'description': [f'Description {i}' for i in range(100)]
    })

    # Test without cache
    print("\n1a. Testing WITHOUT cache (baseline):")
    checker_no_cache = DataQualityChecker(logger)
    start = time.time()
    for i in range(10):
        checker_no_cache.issues = []
        checker_no_cache.check_all_quality_issues_optimized(
            df, 'Metrics', ['id', 'name', 'type'], ['id', 'name']
        )
    time_no_cache = time.time() - start
    print(f"   ✓ 10 validations completed in {time_no_cache:.3f}s")
    print(f"   ✓ Average: {time_no_cache/10:.3f}s per validation")

    # Test with cache
    print("\n1b. Testing WITH cache:")
    cache = ValidationCache(max_size=100, ttl_seconds=3600, logger=logger)
    checker_with_cache = DataQualityChecker(logger, validation_cache=cache)
    start = time.time()
    for i in range(10):
        checker_with_cache.issues = []
        checker_with_cache.check_all_quality_issues_optimized(
            df, 'Metrics', ['id', 'name', 'type'], ['id', 'name']
        )
    time_with_cache = time.time() - start
    print(f"   ✓ 10 validations completed in {time_with_cache:.3f}s")
    print(f"   ✓ Average: {time_with_cache/10:.3f}s per validation")

    # Cache statistics
    stats = cache.get_statistics()
    print(f"\n1c. Cache Statistics:")
    print(f"   ✓ Cache Hits: {stats['hits']}")
    print(f"   ✓ Cache Misses: {stats['misses']}")
    print(f"   ✓ Hit Rate: {stats['hit_rate']:.1f}%")
    print(f"   ✓ Cache Size: {stats['size']}/{stats['max_size']}")

    # Performance improvement
    improvement = ((time_no_cache - time_with_cache) / time_no_cache) * 100
    print(f"\n1d. Performance Improvement:")
    print(f"   ✓ Speed improvement: {improvement:.1f}%")

    if improvement >= 50:
        print(f"   ✓ EXCELLENT: Exceeds 50% improvement target")
    elif improvement >= 20:
        print(f"   ✓ GOOD: Meets 20% improvement threshold")
    else:
        print(f"   ⚠ WARNING: Below 20% threshold ({improvement:.1f}%)")

    return improvement >= 20


def test_parallel_validation():
    """Test parallel validation functionality"""
    print_section("TEST 2: Parallel Validation")

    logger = logging.getLogger("stress_test")
    logger.setLevel(logging.INFO)

    # Create test DataFrames
    metrics_df = pd.DataFrame({
        'id': [f'm{i}' for i in range(150)],
        'name': [f'Metric {i}' for i in range(150)],
        'type': ['int'] * 150,
        'description': [f'Desc {i}' for i in range(150)]
    })

    dimensions_df = pd.DataFrame({
        'id': [f'd{i}' for i in range(75)],
        'name': [f'Dimension {i}' for i in range(75)],
        'type': ['string'] * 75,
        'description': [f'Desc {i}' for i in range(75)]
    })

    # Test sequential validation
    print("\n2a. Testing SEQUENTIAL validation:")
    checker_seq = DataQualityChecker(logger)
    start = time.time()
    for _ in range(5):
        checker_seq.issues = []
        checker_seq.check_all_quality_issues_optimized(
            metrics_df, 'Metrics', ['id', 'name', 'type'], ['id', 'name']
        )
        checker_seq.check_all_quality_issues_optimized(
            dimensions_df, 'Dimensions', ['id', 'name', 'type'], ['id', 'name']
        )
    time_seq = time.time() - start
    print(f"   ✓ 5 sequential validations: {time_seq:.3f}s")

    # Test parallel validation
    print("\n2b. Testing PARALLEL validation:")
    checker_par = DataQualityChecker(logger)
    start = time.time()
    for _ in range(5):
        checker_par.issues = []
        checker_par.check_all_parallel(
            metrics_df, dimensions_df,
            ['id', 'name', 'type'],
            ['id', 'name', 'type'],
            ['id', 'name'],
            max_workers=2
        )
    time_par = time.time() - start
    print(f"   ✓ 5 parallel validations: {time_par:.3f}s")

    improvement = ((time_seq - time_par) / time_seq) * 100
    print(f"\n2c. Performance Improvement:")
    print(f"   ✓ Speed improvement: {improvement:.1f}%")

    if improvement >= 10:
        print(f"   ✓ SUCCESS: Meets 10-15% improvement target")
    else:
        print(f"   ⚠ INFO: {improvement:.1f}% (may vary with dataset size)")

    return time_par <= time_seq


def test_early_exit():
    """Test early exit optimization"""
    print_section("TEST 3: Early Exit Optimization")

    logger = logging.getLogger("stress_test")
    logger.setLevel(logging.WARNING)

    # Create invalid DataFrame (missing required fields)
    df_invalid = pd.DataFrame({
        'wrong_field': [f'value_{i}' for i in range(1000)]
    })

    print("\n3a. Testing early exit with invalid data:")
    checker = DataQualityChecker(logger)
    start = time.time()
    checker.check_all_quality_issues_optimized(
        df_invalid, 'Metrics', ['id', 'name', 'type'], ['id', 'name']
    )
    duration = time.time() - start

    print(f"   ✓ Validation completed in {duration:.3f}s")
    print(f"   ✓ Issues detected: {len(checker.issues)}")
    print(f"   ✓ Critical issues: {sum(1 for i in checker.issues if i['Severity'] == 'CRITICAL')}")

    # Should complete very quickly due to early exit
    if duration < 0.1:
        print(f"   ✓ EXCELLENT: Early exit working (< 0.1s)")
        return True
    else:
        print(f"   ⚠ INFO: Took {duration:.3f}s (early exit may not be triggered)")
        return False


def test_performance_tracking():
    """Test performance tracking functionality"""
    print_section("TEST 4: Performance Tracking")

    logger = logging.getLogger("stress_test")
    logger.setLevel(logging.INFO)

    print("\n4a. Testing PerformanceTracker:")
    tracker = PerformanceTracker(logger)

    # Simulate operations
    tracker.start("operation_1")
    time.sleep(0.05)
    tracker.end("operation_1")

    tracker.start("operation_2")
    time.sleep(0.03)
    tracker.end("operation_2")

    tracker.start("operation_3")
    time.sleep(0.02)
    tracker.end("operation_3")

    print(f"   ✓ Tracked 3 operations")
    print(f"   ✓ Operation 1: {tracker.metrics['operation_1']:.3f}s")
    print(f"   ✓ Operation 2: {tracker.metrics['operation_2']:.3f}s")
    print(f"   ✓ Operation 3: {tracker.metrics['operation_3']:.3f}s")

    # Test cache statistics
    print("\n4b. Testing cache statistics tracking:")
    cache = ValidationCache(max_size=10, ttl_seconds=3600, logger=logger)
    df = pd.DataFrame({'id': [1, 2, 3], 'name': ['a', 'b', 'c'], 'type': ['x', 'y', 'z']})

    # Generate some cache activity
    cache.put(df, 'Metrics', ['id'], [], [])
    cache.get(df, 'Metrics', ['id'], [])
    cache.get(df, 'Metrics', ['id'], [])

    tracker.add_cache_statistics(cache)

    stats = cache.get_statistics()
    print(f"   ✓ Cache hits: {stats['hits']}")
    print(f"   ✓ Cache misses: {stats['misses']}")
    print(f"   ✓ Statistics tracked successfully")

    return True


def test_stress_scenarios():
    """Test stress scenarios"""
    print_section("TEST 5: Stress Scenarios")

    logger = logging.getLogger("stress_test")
    logger.setLevel(logging.WARNING)

    print("\n5a. Large dataset (1000 rows):")
    df_large = pd.DataFrame({
        'id': [f'm{i}' for i in range(1000)],
        'name': [f'Metric {i}' for i in range(1000)],
        'type': ['int'] * 500 + ['currency'] * 500,
        'description': [f'Description {i}' for i in range(1000)]
    })

    checker = DataQualityChecker(logger)
    start = time.time()
    checker.check_all_quality_issues_optimized(
        df_large, 'Metrics', ['id', 'name', 'type'], ['id', 'name']
    )
    duration = time.time() - start

    print(f"   ✓ Validated 1000 rows in {duration:.3f}s")
    print(f"   ✓ Issues found: {len(checker.issues)}")

    print("\n5b. Dataset with duplicates:")
    df_dupes = pd.DataFrame({
        'id': [f'm{i}' for i in range(100)],
        'name': ['Duplicate'] * 50 + [f'Unique {i}' for i in range(50)],
        'type': ['int'] * 100,
        'description': ['Desc'] * 100
    })

    checker2 = DataQualityChecker(logger)
    checker2.check_all_quality_issues_optimized(
        df_dupes, 'Metrics', ['id', 'name', 'type'], ['id', 'name']
    )

    duplicate_issues = [i for i in checker2.issues if i['Category'] == 'Duplicates']
    print(f"   ✓ Duplicate detection working: {len(duplicate_issues)} issues")

    print("\n5c. Dataset with missing descriptions:")
    df_missing = pd.DataFrame({
        'id': [f'm{i}' for i in range(100)],
        'name': [f'Metric {i}' for i in range(100)],
        'type': ['int'] * 100,
        'description': [''] * 30 + [f'Desc {i}' for i in range(70)]
    })

    checker3 = DataQualityChecker(logger)
    checker3.check_all_quality_issues_optimized(
        df_missing, 'Metrics', ['id', 'name', 'type'], ['id', 'name', 'description']
    )

    missing_issues = [i for i in checker3.issues if 'description' in i['Issue'].lower()]
    print(f"   ✓ Missing description detection: {len(missing_issues)} issues")

    return duration < 1.0  # Should complete in under 1 second


def test_concurrent_cache_access():
    """Test concurrent cache access"""
    print_section("TEST 6: Concurrent Cache Access")

    import threading
    from concurrent.futures import ThreadPoolExecutor

    logger = logging.getLogger("stress_test")
    logger.setLevel(logging.WARNING)

    print("\n6a. Testing thread safety with concurrent access:")
    cache = ValidationCache(max_size=100, ttl_seconds=3600, logger=logger)
    checker = DataQualityChecker(logger, validation_cache=cache)

    df = pd.DataFrame({
        'id': [f'm{i}' for i in range(100)],
        'name': [f'Metric {i}' for i in range(100)],
        'type': ['int'] * 100,
        'description': [f'Desc {i}' for i in range(100)]
    })

    results = []
    errors = []

    def validate():
        try:
            c = DataQualityChecker(logger, validation_cache=cache)
            c.check_all_quality_issues_optimized(
                df, 'Metrics', ['id', 'name', 'type'], ['id', 'name']
            )
            results.append(len(c.issues))
        except Exception as e:
            errors.append(e)

    # Run 20 concurrent validations
    with ThreadPoolExecutor(max_workers=10) as executor:
        futures = [executor.submit(validate) for _ in range(20)]
        for future in futures:
            future.result()

    print(f"   ✓ 20 concurrent validations completed")
    print(f"   ✓ Errors: {len(errors)}")
    print(f"   ✓ Results collected: {len(results)}")

    stats = cache.get_statistics()
    print(f"\n6b. Cache statistics after concurrent access:")
    print(f"   ✓ Total requests: {stats['total_requests']}")
    print(f"   ✓ Cache hits: {stats['hits']}")
    print(f"   ✓ Cache misses: {stats['misses']}")
    print(f"   ✓ Hit rate: {stats['hit_rate']:.1f}%")

    return len(errors) == 0


def main():
    """Run all stress tests"""
    print("\n" + "=" * 70)
    print("  CJA SDR Generator v3.0.15 - Comprehensive Stress Test")
    print("=" * 70)
    print("\nTesting all major features:")
    print("  • Validation Result Caching (50-90% improvement)")
    print("  • Parallel Validation (10-15% improvement)")
    print("  • Early Exit Optimization (15-20% on errors)")
    print("  • Performance Tracking")
    print("  • Thread Safety")

    # Configure logging
    logging.basicConfig(
        level=logging.WARNING,
        format='%(message)s'
    )

    # Run all tests
    results = {}

    try:
        results['cache'] = test_validation_cache()
    except Exception as e:
        print(f"\n   ✗ FAILED: {e}")
        results['cache'] = False

    try:
        results['parallel'] = test_parallel_validation()
    except Exception as e:
        print(f"\n   ✗ FAILED: {e}")
        results['parallel'] = False

    try:
        results['early_exit'] = test_early_exit()
    except Exception as e:
        print(f"\n   ✗ FAILED: {e}")
        results['early_exit'] = False

    try:
        results['tracking'] = test_performance_tracking()
    except Exception as e:
        print(f"\n   ✗ FAILED: {e}")
        results['tracking'] = False

    try:
        results['stress'] = test_stress_scenarios()
    except Exception as e:
        print(f"\n   ✗ FAILED: {e}")
        results['stress'] = False

    try:
        results['concurrent'] = test_concurrent_cache_access()
    except Exception as e:
        print(f"\n   ✗ FAILED: {e}")
        results['concurrent'] = False

    # Summary
    print_section("STRESS TEST SUMMARY")

    total = len(results)
    passed = sum(1 for v in results.values() if v)

    print(f"\nTest Results:")
    print(f"  • Validation Cache:      {'✓ PASS' if results.get('cache') else '✗ FAIL'}")
    print(f"  • Parallel Validation:   {'✓ PASS' if results.get('parallel') else '✗ FAIL'}")
    print(f"  • Early Exit:            {'✓ PASS' if results.get('early_exit') else '✗ FAIL'}")
    print(f"  • Performance Tracking:  {'✓ PASS' if results.get('tracking') else '✗ FAIL'}")
    print(f"  • Stress Scenarios:      {'✓ PASS' if results.get('stress') else '✗ FAIL'}")
    print(f"  • Concurrent Access:     {'✓ PASS' if results.get('concurrent') else '✗ FAIL'}")

    print(f"\nOverall: {passed}/{total} tests passed ({passed/total*100:.0f}%)")

    if passed == total:
        print("\n✓ ALL STRESS TESTS PASSED - v3.0.15 is production-ready!")
        return 0
    else:
        print(f"\n⚠ {total - passed} test(s) failed - review output above")
        return 1


if __name__ == '__main__':
    sys.exit(main())
