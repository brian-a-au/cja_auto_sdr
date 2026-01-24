"""Tests for circuit breaker pattern implementation

Validates that circuit breaker:
1. Starts in CLOSED state (allowing requests)
2. Opens after failure threshold exceeded
3. Transitions to HALF_OPEN after timeout
4. Closes again after successful requests in HALF_OPEN
5. Reopens immediately on failure in HALF_OPEN
6. Is thread-safe under concurrent access
7. Provides accurate statistics
8. Works as a decorator
"""
import pytest
import time
import threading
from concurrent.futures import ThreadPoolExecutor
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cja_sdr_generator import (
    CircuitBreaker, CircuitBreakerConfig, CircuitState, CircuitBreakerOpen
)


class TestCircuitBreakerBasics:
    """Test basic circuit breaker functionality"""

    def test_initial_state_is_closed(self):
        """Circuit breaker should start in CLOSED state"""
        breaker = CircuitBreaker()
        assert breaker.state == CircuitState.CLOSED

    def test_allows_requests_when_closed(self):
        """CLOSED circuit should allow all requests"""
        breaker = CircuitBreaker()

        for _ in range(10):
            assert breaker.allow_request() is True

    def test_opens_after_failure_threshold(self):
        """Circuit should open after failure threshold exceeded"""
        config = CircuitBreakerConfig(failure_threshold=3)
        breaker = CircuitBreaker(config=config)

        # Record failures up to threshold
        for i in range(3):
            breaker.record_failure(Exception(f"Failure {i+1}"))

        assert breaker.state == CircuitState.OPEN

    def test_does_not_open_below_threshold(self):
        """Circuit should not open before reaching threshold"""
        config = CircuitBreakerConfig(failure_threshold=5)
        breaker = CircuitBreaker(config=config)

        # Record failures below threshold
        for i in range(4):
            breaker.record_failure(Exception(f"Failure {i+1}"))

        assert breaker.state == CircuitState.CLOSED

    def test_rejects_requests_when_open(self):
        """OPEN circuit should reject requests"""
        config = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=60)
        breaker = CircuitBreaker(config=config)

        breaker.record_failure(Exception("Failure"))
        assert breaker.state == CircuitState.OPEN
        assert breaker.allow_request() is False

    def test_success_resets_failure_count(self):
        """Success in CLOSED state should reset failure count"""
        config = CircuitBreakerConfig(failure_threshold=3)
        breaker = CircuitBreaker(config=config)

        # Record some failures
        breaker.record_failure(Exception("Failure 1"))
        breaker.record_failure(Exception("Failure 2"))

        # Record success
        breaker.record_success()

        # Should need 3 more failures to open
        breaker.record_failure(Exception("Failure 3"))
        breaker.record_failure(Exception("Failure 4"))
        assert breaker.state == CircuitState.CLOSED

        breaker.record_failure(Exception("Failure 5"))
        assert breaker.state == CircuitState.OPEN


class TestCircuitBreakerRecovery:
    """Test circuit breaker recovery mechanisms"""

    def test_transitions_to_half_open_after_timeout(self):
        """Circuit should transition OPEN -> HALF_OPEN after timeout"""
        config = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=0.1)
        breaker = CircuitBreaker(config=config)

        breaker.record_failure(Exception("Failure"))
        assert breaker.state == CircuitState.OPEN

        # Wait for timeout
        time.sleep(0.15)

        # Next allow_request should transition to HALF_OPEN
        assert breaker.allow_request() is True
        assert breaker.state == CircuitState.HALF_OPEN

    def test_closes_after_success_threshold_in_half_open(self):
        """Circuit should close after success threshold in HALF_OPEN"""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=2,
            timeout_seconds=0.1
        )
        breaker = CircuitBreaker(config=config)

        # Open the circuit
        breaker.record_failure(Exception("Failure"))
        time.sleep(0.15)
        breaker.allow_request()  # Transition to HALF_OPEN
        assert breaker.state == CircuitState.HALF_OPEN

        # Record successes
        breaker.record_success()
        assert breaker.state == CircuitState.HALF_OPEN

        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED

    def test_reopens_on_failure_in_half_open(self):
        """Circuit should immediately reopen on failure in HALF_OPEN"""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=3,
            timeout_seconds=0.1
        )
        breaker = CircuitBreaker(config=config)

        # Open the circuit
        breaker.record_failure(Exception("Failure"))
        time.sleep(0.15)
        breaker.allow_request()  # Transition to HALF_OPEN
        assert breaker.state == CircuitState.HALF_OPEN

        # Record success then failure
        breaker.record_success()
        breaker.record_failure(Exception("Another failure"))

        assert breaker.state == CircuitState.OPEN


class TestCircuitBreakerStatistics:
    """Test circuit breaker statistics tracking"""

    def test_tracks_total_requests(self):
        """Should track total request count"""
        breaker = CircuitBreaker()

        for _ in range(5):
            breaker.allow_request()

        stats = breaker.get_statistics()
        assert stats['total_requests'] == 5

    def test_tracks_total_failures(self):
        """Should track total failure count"""
        config = CircuitBreakerConfig(failure_threshold=10)
        breaker = CircuitBreaker(config=config)

        for i in range(3):
            breaker.record_failure(Exception(f"Failure {i}"))

        stats = breaker.get_statistics()
        assert stats['total_failures'] == 3

    def test_tracks_rejections(self):
        """Should track rejected requests"""
        config = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=60)
        breaker = CircuitBreaker(config=config)

        breaker.record_failure(Exception("Failure"))

        # Try to make requests while open
        for _ in range(3):
            breaker.allow_request()

        stats = breaker.get_statistics()
        assert stats['total_rejections'] == 3

    def test_tracks_trip_count(self):
        """Should track how many times circuit has opened"""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            success_threshold=1,
            timeout_seconds=0.1
        )
        breaker = CircuitBreaker(config=config)

        # Trip the circuit twice
        breaker.record_failure(Exception("Failure 1"))
        assert breaker.state == CircuitState.OPEN

        time.sleep(0.15)
        breaker.allow_request()
        breaker.record_success()
        assert breaker.state == CircuitState.CLOSED

        breaker.record_failure(Exception("Failure 2"))
        assert breaker.state == CircuitState.OPEN

        stats = breaker.get_statistics()
        assert stats['trips'] == 2

    def test_tracks_time_until_retry(self):
        """Should track time remaining until retry"""
        config = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=1.0)
        breaker = CircuitBreaker(config=config)

        breaker.record_failure(Exception("Failure"))

        stats = breaker.get_statistics()
        assert 0 < stats['time_until_retry_seconds'] <= 1.0


class TestCircuitBreakerDecorator:
    """Test circuit breaker as decorator"""

    def test_decorator_allows_successful_calls(self):
        """Decorator should allow successful function calls"""
        breaker = CircuitBreaker()

        @breaker
        def successful_function():
            return "success"

        result = successful_function()
        assert result == "success"

    def test_decorator_raises_on_open_circuit(self):
        """Decorator should raise CircuitBreakerOpen when circuit is open"""
        config = CircuitBreakerConfig(failure_threshold=1, timeout_seconds=60)
        breaker = CircuitBreaker(config=config)

        @breaker
        def failing_function():
            raise ValueError("Simulated failure")

        # First call trips the circuit
        with pytest.raises(ValueError):
            failing_function()

        # Second call should be rejected by circuit breaker
        with pytest.raises(CircuitBreakerOpen):
            failing_function()

    def test_decorator_records_success(self):
        """Decorator should record success automatically"""
        config = CircuitBreakerConfig(failure_threshold=5)
        breaker = CircuitBreaker(config=config)

        @breaker
        def successful_function():
            return "success"

        # Record some failures first
        breaker.record_failure(Exception("Manual failure 1"))
        breaker.record_failure(Exception("Manual failure 2"))

        # Call successful function - should reset counter
        successful_function()

        # Circuit should still be closed
        assert breaker.state == CircuitState.CLOSED


class TestCircuitBreakerThreadSafety:
    """Test circuit breaker thread safety"""

    def test_concurrent_requests(self):
        """Circuit breaker should be thread-safe under concurrent access"""
        config = CircuitBreakerConfig(failure_threshold=100)
        breaker = CircuitBreaker(config=config)

        def make_requests():
            for _ in range(100):
                if breaker.allow_request():
                    if threading.current_thread().name.endswith('0'):
                        breaker.record_failure(Exception("Failure"))
                    else:
                        breaker.record_success()

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(make_requests) for _ in range(10)]
            for future in futures:
                future.result()

        stats = breaker.get_statistics()
        assert stats['total_requests'] == 1000

    def test_concurrent_state_transitions(self):
        """State transitions should be atomic under concurrent access"""
        config = CircuitBreakerConfig(
            failure_threshold=5,
            success_threshold=3,
            timeout_seconds=0.05
        )
        breaker = CircuitBreaker(config=config)

        errors = []

        def stress_test():
            try:
                for _ in range(50):
                    breaker.allow_request()
                    if breaker.state in (CircuitState.CLOSED, CircuitState.HALF_OPEN):
                        breaker.record_failure(Exception("Failure"))
                    time.sleep(0.01)
                    breaker.allow_request()
                    if breaker.state == CircuitState.HALF_OPEN:
                        breaker.record_success()
            except Exception as e:
                errors.append(e)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(stress_test) for _ in range(5)]
            for future in futures:
                future.result()

        assert len(errors) == 0, f"Thread safety errors: {errors}"


class TestCircuitBreakerReset:
    """Test circuit breaker reset functionality"""

    def test_reset_clears_state(self):
        """Reset should restore circuit to initial state"""
        config = CircuitBreakerConfig(failure_threshold=1)
        breaker = CircuitBreaker(config=config)

        breaker.record_failure(Exception("Failure"))
        assert breaker.state == CircuitState.OPEN

        breaker.reset()

        assert breaker.state == CircuitState.CLOSED
        stats = breaker.get_statistics()
        assert stats['failure_count'] == 0
        assert stats['success_count'] == 0


class TestCircuitBreakerException:
    """Test CircuitBreakerOpen exception"""

    def test_exception_contains_message(self):
        """Exception should contain descriptive message"""
        exc = CircuitBreakerOpen("Test message", time_until_retry=5.0)

        assert "Test message" in str(exc)
        assert exc.time_until_retry == 5.0

    def test_exception_default_values(self):
        """Exception should have sensible defaults"""
        exc = CircuitBreakerOpen()

        assert "open" in str(exc).lower()
        assert exc.time_until_retry == 0
