"""Tests for utility functions"""
import pytest
import sys
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
import logging


# Import the functions and classes we're testing
sys.path.insert(0, '/Users/bau/DEV/cja_auto_sdr_2026')
from cja_sdr_generator import (
    setup_logging,
    validate_config_file,
    PerformanceTracker
)


class TestLoggingSetup:
    """Test logging configuration"""

    def test_logging_creates_log_directory(self, tmp_path, monkeypatch):
        """Test that logging creates the logs directory"""
        # Change to temp directory
        monkeypatch.chdir(tmp_path)

        setup_logging("dv_test_12345", batch_mode=False, log_level="INFO")

        # Check that logs directory was created
        log_dir = tmp_path / "logs"
        assert log_dir.exists()
        assert log_dir.is_dir()

    def test_logging_creates_log_file(self, tmp_path, monkeypatch):
        """Test that logging creates a log file"""
        monkeypatch.chdir(tmp_path)

        setup_logging("dv_test_12345", batch_mode=False, log_level="INFO")

        # Check that a log file was created
        log_dir = tmp_path / "logs"
        log_files = list(log_dir.glob("*.log"))
        assert len(log_files) > 0

    def test_batch_mode_log_filename(self, tmp_path, monkeypatch):
        """Test that batch mode creates correctly named log file"""
        monkeypatch.chdir(tmp_path)

        setup_logging(batch_mode=True, log_level="INFO")

        log_dir = tmp_path / "logs"
        log_files = list(log_dir.glob("SDR_Batch_Generation_*.log"))
        assert len(log_files) > 0

    def test_log_level_configuration(self, tmp_path, monkeypatch):
        """Test that log level is configured correctly"""
        monkeypatch.chdir(tmp_path)

        logger = setup_logging("dv_test", batch_mode=False, log_level="DEBUG")

        assert logger.level == logging.DEBUG or logging.root.level == logging.DEBUG


class TestConfigValidation:
    """Test configuration file validation"""

    def test_valid_config_file(self, mock_config_file):
        """Test validation of valid config file"""
        logger = logging.getLogger("test")
        # Should not raise an exception
        result = validate_config_file(mock_config_file, logger)
        assert result is True

    def test_missing_config_file(self):
        """Test validation with missing config file"""
        logger = logging.getLogger("test")
        result = validate_config_file("nonexistent_config.json", logger)
        # Should return False for missing file
        assert result is False

    def test_invalid_json_config(self, tmp_path):
        """Test validation with invalid JSON"""
        logger = logging.getLogger("test")
        invalid_config = tmp_path / "invalid_config.json"
        invalid_config.write_text("{ invalid json }")

        result = validate_config_file(str(invalid_config), logger)
        # Should return False for invalid JSON
        assert result is False

    def test_missing_required_fields(self, tmp_path):
        """Test validation with missing required fields"""
        logger = logging.getLogger("test")
        incomplete_config = tmp_path / "incomplete_config.json"
        incomplete_config.write_text(json.dumps({
            "org_id": "test_org",
            "client_id": "test_client"
            # Missing other required fields
        }))

        # Should log warnings but still return True
        result = validate_config_file(str(incomplete_config), logger)
        assert result is True


class TestPerformanceTracker:
    """Test performance tracking functionality"""

    def test_performance_tracker_tracks_operations(self):
        """Test that performance tracker records operations"""
        logger = logging.getLogger("test")
        tracker = PerformanceTracker(logger)

        tracker.start("test_operation")
        tracker.end("test_operation")

        assert "test_operation" in tracker.metrics
        assert tracker.metrics["test_operation"] >= 0  # Allow 0 for very fast operations

    def test_performance_tracker_multiple_operations(self):
        """Test tracking multiple operations"""
        logger = logging.getLogger("test")
        tracker = PerformanceTracker(logger)

        operations = ["op1", "op2", "op3"]
        for op in operations:
            tracker.start(op)
            tracker.end(op)

        assert len(tracker.metrics) == 3
        for op in operations:
            assert op in tracker.metrics

    def test_performance_tracker_summary(self):
        """Test that summary is generated correctly"""
        logger = logging.getLogger("test")
        tracker = PerformanceTracker(logger)

        tracker.start("test_op")
        tracker.end("test_op")

        summary = tracker.get_summary()
        assert "PERFORMANCE SUMMARY" in summary
        assert "test_op" in summary

    def test_performance_tracker_no_metrics(self):
        """Test summary with no metrics collected"""
        logger = logging.getLogger("test")
        tracker = PerformanceTracker(logger)

        summary = tracker.get_summary()
        assert "No performance metrics collected" in summary

    def test_performance_tracker_timing_accuracy(self):
        """Test that tracker measures time accurately"""
        import time
        logger = logging.getLogger("test")
        tracker = PerformanceTracker(logger)

        tracker.start("timed_op")
        time.sleep(0.1)  # Sleep for 100ms
        tracker.end("timed_op")

        # Should be at least 0.1 seconds
        assert tracker.metrics["timed_op"] >= 0.1

    def test_performance_tracker_nested_operations(self):
        """Test tracking nested/overlapping operations"""
        logger = logging.getLogger("test")
        tracker = PerformanceTracker(logger)

        tracker.start("outer_op")
        tracker.start("inner_op")
        tracker.end("inner_op")
        tracker.end("outer_op")

        assert "outer_op" in tracker.metrics
        assert "inner_op" in tracker.metrics
        # Outer operation should take longer
        assert tracker.metrics["outer_op"] >= tracker.metrics["inner_op"]
