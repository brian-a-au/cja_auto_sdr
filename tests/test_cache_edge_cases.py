"""Edge-case tests for api/cache.py.

Covers: _validate_cache_params, hash truncation, error-path key
generation uniqueness, TTL boundaries, statistics accuracy, LRU
eviction, and constructor wiring to the shared validator.
"""

import time
from unittest.mock import patch

import pandas as pd
import pytest

from cja_auto_sdr.api.cache import (
    SharedValidationCache,
    ValidationCache,
    _validate_cache_params,
)
from cja_auto_sdr.core.constants import CACHE_KEY_HASH_LENGTH

# ==================== Shared Validator ====================


class TestValidateCacheParams:
    """Tests for the extracted _validate_cache_params function."""

    def test_minimum_valid_params(self):
        """max_size=1, ttl_seconds=1 — minimum valid."""
        _validate_cache_params(1, 1)  # Should not raise

    def test_max_size_zero_raises(self):
        with pytest.raises(ValueError, match="max_size must be >= 1"):
            _validate_cache_params(0, 1)

    def test_max_size_negative_raises(self):
        with pytest.raises(ValueError, match="max_size must be >= 1"):
            _validate_cache_params(-1, 1)

    def test_ttl_zero_raises(self):
        with pytest.raises(ValueError, match="ttl_seconds must be > 0"):
            _validate_cache_params(1, 0)

    def test_ttl_negative_raises(self):
        with pytest.raises(ValueError, match="ttl_seconds must be > 0"):
            _validate_cache_params(1, -1)

    def test_both_invalid_raises_max_size_first(self):
        """max_size checked first when both are invalid."""
        with pytest.raises(ValueError, match="max_size"):
            _validate_cache_params(-1, -1)

    def test_validation_cache_calls_shared_validator(self):
        with patch("cja_auto_sdr.api.cache._validate_cache_params") as mock_validate:
            ValidationCache(max_size=5, ttl_seconds=60)
        mock_validate.assert_called_once_with(5, 60)

    def test_shared_validation_cache_calls_shared_validator(self):
        cache = None
        with patch("cja_auto_sdr.api.cache._validate_cache_params") as mock_validate:
            cache = SharedValidationCache(max_size=5, ttl_seconds=60)
        mock_validate.assert_called_once_with(5, 60)
        if cache is not None:
            cache.shutdown()


# ==================== Hash Truncation ====================


class TestHashTruncation:
    """Verify cache key hash is exactly CACHE_KEY_HASH_LENGTH chars."""

    def test_config_hash_length(self):
        cache = ValidationCache(max_size=10, ttl_seconds=60)
        df = pd.DataFrame({"id": ["m1"], "name": ["Metric A"], "type": ["metric"]})
        key = cache._generate_cache_key(df, "Metrics", ["id", "name"], ["id"])
        # Key format: "{item_type}:{df_hash}:{config_hash}"
        parts = key.split(":")
        assert len(parts) == 3
        config_hash = parts[2]
        assert len(config_hash) == CACHE_KEY_HASH_LENGTH

    def test_different_configs_produce_different_hashes(self):
        cache = ValidationCache(max_size=10, ttl_seconds=60)
        df = pd.DataFrame({"id": ["m1"], "name": ["Metric A"], "type": ["metric"]})
        key1 = cache._generate_cache_key(df, "Metrics", ["id", "name"], ["id"])
        key2 = cache._generate_cache_key(df, "Metrics", ["id", "name", "type"], ["id", "name"])
        assert key1 != key2


# ==================== Error-Path Key Generation ====================


class TestErrorPathKeyGeneration:
    """Verify error-path cache keys start with 'error:' and stay unique."""

    def test_error_key_on_exception(self):
        cache = ValidationCache(max_size=10, ttl_seconds=60)
        # Pass a non-DataFrame to force an exception in _generate_cache_key
        key = cache._generate_cache_key("not_a_dataframe", "Metrics", ["id"], ["id"])
        assert key.startswith("error:")

    def test_successive_error_keys_do_not_collide(self):
        cache = ValidationCache(max_size=10, ttl_seconds=60)
        with (
            patch.object(cache.logger, "warning"),
            patch(
                "cja_auto_sdr.api.cache.time.time",
                side_effect=[1000.0, 1000.5],
            ) as mock_time,
        ):
            key1 = cache._generate_cache_key("not_a_dataframe", "Metrics", ["id"], ["id"])
            key2 = cache._generate_cache_key("not_a_dataframe", "Metrics", ["id"], ["id"])
        # Error-path keys intentionally embed the current timestamp so failures
        # cannot collide and accidentally turn into cache hits.
        assert key1 == "error:1000.0"
        assert key2 == "error:1000.5"
        assert mock_time.call_count == 2


# ==================== TTL Boundary ====================


class TestTTLBoundary:
    """Verify TTL uses strict greater-than (>) for expiration."""

    def test_entry_at_ttl_minus_epsilon_is_valid(self):
        cache = ValidationCache(max_size=10, ttl_seconds=10)
        df = pd.DataFrame({"id": ["m1"], "name": ["A"], "type": ["metric"]})
        cache.put(df, "Metrics", ["id"], ["id"], [{"test": "issue"}])

        key = cache._generate_cache_key(df, "Metrics", ["id"], ["id"])
        now = time.time()
        with cache._lock:
            issues, _ts = cache._cache[key]
            cache._cache[key] = (issues, now - 9.999)  # TTL - epsilon

        with patch("cja_auto_sdr.api.cache.time.time", return_value=now):
            result, _key = cache.get(df, "Metrics", ["id"], ["id"])
            assert result is not None

    def test_entry_at_ttl_plus_epsilon_is_expired(self):
        cache = ValidationCache(max_size=10, ttl_seconds=10)
        df = pd.DataFrame({"id": ["m1"], "name": ["A"], "type": ["metric"]})
        cache.put(df, "Metrics", ["id"], ["id"], [{"test": "issue"}])

        key = cache._generate_cache_key(df, "Metrics", ["id"], ["id"])
        now = time.time()
        with cache._lock:
            issues, _ts = cache._cache[key]
            cache._cache[key] = (issues, now - 10.001)  # TTL + epsilon

        with patch("cja_auto_sdr.api.cache.time.time", return_value=now):
            result, _key = cache.get(df, "Metrics", ["id"], ["id"])
            assert result is None

    def test_entry_exactly_at_ttl_is_still_valid(self):
        """age > ttl_seconds — entry at exactly TTL age is still valid."""
        cache = ValidationCache(max_size=10, ttl_seconds=10)
        df = pd.DataFrame({"id": ["m1"], "name": ["A"], "type": ["metric"]})
        cache.put(df, "Metrics", ["id"], ["id"], [{"test": "issue"}])

        # Set timestamp to exactly TTL age
        key = cache._generate_cache_key(df, "Metrics", ["id"], ["id"])
        now = time.time()
        with cache._lock:
            issues, _ts = cache._cache[key]
            cache._cache[key] = (issues, now - 10)  # Exactly at TTL boundary

        # Patch time.time to return consistent value for the comparison
        with patch("cja_auto_sdr.api.cache.time.time", return_value=now):
            result, _key = cache.get(df, "Metrics", ["id"], ["id"])
            # age == ttl_seconds → NOT expired (uses > not >=)
            assert result is not None


# ==================== Statistics Accuracy ====================


class TestStatisticsAccuracy:
    """Verify cache statistics track correctly."""

    def _make_cache_and_df(self):
        cache = ValidationCache(max_size=10, ttl_seconds=60)
        df = pd.DataFrame({"id": ["m1"], "name": ["A"], "type": ["metric"]})
        return cache, df

    def test_miss_increments_on_cache_miss(self):
        cache, df = self._make_cache_and_df()
        cache.get(df, "Metrics", ["id"], ["id"])
        stats = cache.get_statistics()
        assert stats["misses"] == 1
        assert stats["hits"] == 0

    def test_hit_increments_on_cache_hit(self):
        cache, df = self._make_cache_and_df()
        cache.put(df, "Metrics", ["id"], ["id"], [{"test": "issue"}])
        cache.get(df, "Metrics", ["id"], ["id"])
        stats = cache.get_statistics()
        assert stats["hits"] == 1

    def test_eviction_increments_on_lru_eviction(self):
        cache = ValidationCache(max_size=1, ttl_seconds=60)
        df1 = pd.DataFrame({"id": ["m1"], "name": ["A"], "type": ["metric"]})
        df2 = pd.DataFrame({"id": ["m2"], "name": ["B"], "type": ["metric"]})

        cache.put(df1, "Metrics", ["id"], ["id"], [{"test": "issue1"}])
        cache.put(df2, "Metrics", ["id"], ["id"], [{"test": "issue2"}])

        stats = cache.get_statistics()
        assert stats["evictions"] >= 1

    def test_stats_keys_are_stable(self):
        cache, _df = self._make_cache_and_df()
        stats = cache.get_statistics()
        expected_keys = {"hits", "misses", "hit_rate", "size", "max_size", "evictions", "total_requests"}
        assert set(stats.keys()) == expected_keys

    def test_hit_rate_calculation(self):
        cache, df = self._make_cache_and_df()
        cache.put(df, "Metrics", ["id"], ["id"], [{"test": "issue"}])
        cache.get(df, "Metrics", ["id"], ["id"])  # hit
        cache.get(df, "Dimensions", ["id"], ["id"])  # miss (different item_type key)
        stats = cache.get_statistics()
        assert stats["hit_rate"] == pytest.approx(50.0)
