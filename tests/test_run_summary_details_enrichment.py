"""Tests for run summary details enrichment (Task 4 — v3.4.3).

Covers: _merge_run_details helper, execution_settings keys from
prepare_sdr_execution_context, org-report lock block reshaping,
and additive merge semantics.
"""

from __future__ import annotations

import argparse
from typing import Any
from unittest.mock import MagicMock, patch

from cja_auto_sdr.generator import (
    RUN_SUMMARY_SCHEMA_VERSION,
    _merge_run_details,
)

# ==================== RUN_SUMMARY_SCHEMA_VERSION ====================


class TestSchemaVersionUnchanged:
    """Guard that the summary version stays at 1.1 for v3.4.3."""

    def test_version_is_1_1(self):
        assert RUN_SUMMARY_SCHEMA_VERSION == "1.1"


# ==================== _merge_run_details ====================


class TestMergeRunDetails:
    """Test the additive details merge helper."""

    def test_adds_new_key(self):
        run_state: dict[str, Any] = {"details": {}}
        _merge_run_details(run_state, execution_settings={"a": 1})
        assert run_state["details"]["execution_settings"] == {"a": 1}

    def test_does_not_overwrite_existing_key(self):
        run_state: dict[str, Any] = {"details": {"execution_settings": {"original": True}}}
        _merge_run_details(run_state, execution_settings={"replaced": True})
        assert run_state["details"]["execution_settings"] == {"original": True}

    def test_preserves_operation_success(self):
        run_state: dict[str, Any] = {"details": {"operation_success": True}}
        _merge_run_details(run_state, execution_settings={"a": 1})
        assert run_state["details"]["operation_success"] is True
        assert "execution_settings" in run_state["details"]

    def test_creates_details_if_missing(self):
        run_state: dict[str, Any] = {}
        _merge_run_details(run_state, lock={"acquired": True})
        assert run_state["details"]["lock"] == {"acquired": True}

    def test_none_run_state_is_noop(self):
        # Should not raise
        _merge_run_details(None, execution_settings={"a": 1})

    def test_multiple_keys_merged(self):
        run_state: dict[str, Any] = {"details": {}}
        _merge_run_details(run_state, execution_settings={"a": 1}, lock={"b": 2})
        assert run_state["details"]["execution_settings"] == {"a": 1}
        assert run_state["details"]["lock"] == {"b": 2}

    def test_mixed_existing_and_new(self):
        run_state: dict[str, Any] = {"details": {"lock": {"existing": True}}}
        _merge_run_details(run_state, lock={"new": True}, execution_settings={"x": 1})
        # lock should NOT be overwritten
        assert run_state["details"]["lock"] == {"existing": True}
        # execution_settings is new, so it IS added
        assert run_state["details"]["execution_settings"] == {"x": 1}


# ==================== prepare_sdr_execution_context metadata ====================


class TestExecutionContextMetadata:
    """Test that prepare_sdr_execution_context returns execution metadata keys."""

    def _make_args(self, **overrides) -> argparse.Namespace:
        defaults = {
            "quiet": True,
            "production": False,
            "log_level": "INFO",
            "dry_run": False,
            "format": "excel",
            "workers": 4,
            "batch": False,
            "shared_cache": False,
            "enable_cache": True,
            "skip_validation": False,
            "api_auto_tune": False,
            "circuit_breaker": False,
            "metrics_only": False,
            "dimensions_only": False,
            "output_dir": "/tmp/test",
            "log_format": "text",
            "inventory_summary": False,
            "include_derived_inventory": False,
            "include_calculated_metrics": False,
            "include_segments_inventory": False,
            "assume_yes": False,
            "config_file": None,
            "profile": None,
            "cache_size": 100,
            "cache_ttl": 300,
            "continue_on_error": False,
            "clear_cache": False,
            "show_timings": False,
            "max_issues": 100,
            "inventory_only": False,
            "allow_partial": False,
            "open": False,
            "quality_report": None,
        }
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    @patch("cja_auto_sdr.cli.execution._generator_module")
    def test_returns_api_auto_tune_requested_false(self, mock_gen):
        mock_gen.return_value = MagicMock()
        mock_gen.return_value._check_output_dir_access.return_value = (True, "/tmp/test", None, None)
        from cja_auto_sdr.cli.execution import prepare_sdr_execution_context

        args = self._make_args()
        ctx = prepare_sdr_execution_context(args, data_views=["dv_1"])
        assert ctx["api_auto_tune_requested"] is False

    @patch("cja_auto_sdr.cli.execution._generator_module")
    def test_returns_circuit_breaker_enabled_false(self, mock_gen):
        mock_gen.return_value = MagicMock()
        mock_gen.return_value._check_output_dir_access.return_value = (True, "/tmp/test", None, None)
        from cja_auto_sdr.cli.execution import prepare_sdr_execution_context

        args = self._make_args()
        ctx = prepare_sdr_execution_context(args, data_views=["dv_1"])
        assert ctx["circuit_breaker_enabled"] is False

    @patch("cja_auto_sdr.cli.execution._generator_module")
    def test_shared_cache_active_false_single_mode(self, mock_gen):
        mock_gen.return_value = MagicMock()
        mock_gen.return_value._check_output_dir_access.return_value = (True, "/tmp/test", None, None)
        from cja_auto_sdr.cli.execution import prepare_sdr_execution_context

        args = self._make_args(shared_cache=True)
        ctx = prepare_sdr_execution_context(args, data_views=["dv_1"])
        # Single data view, not batch mode → shared_cache_active is False
        assert ctx["shared_cache_active"] is False

    @patch("cja_auto_sdr.cli.execution._generator_module")
    def test_shared_cache_active_true_batch(self, mock_gen):
        mock_gen.return_value = MagicMock()
        mock_gen.return_value._check_output_dir_access.return_value = (True, "/tmp/test", None, None)
        from cja_auto_sdr.cli.execution import prepare_sdr_execution_context

        args = self._make_args(shared_cache=True, batch=True, enable_cache=True, skip_validation=False)
        ctx = prepare_sdr_execution_context(args, data_views=["dv_1", "dv_2"])
        assert ctx["shared_cache_active"] is True

    @patch("cja_auto_sdr.cli.execution._generator_module")
    def test_shared_cache_inactive_when_validation_skipped(self, mock_gen):
        mock_gen.return_value = MagicMock()
        mock_gen.return_value._check_output_dir_access.return_value = (True, "/tmp/test", None, None)
        from cja_auto_sdr.cli.execution import prepare_sdr_execution_context

        args = self._make_args(shared_cache=True, batch=True, enable_cache=True, skip_validation=True)
        ctx = prepare_sdr_execution_context(args, data_views=["dv_1", "dv_2"])
        assert ctx["shared_cache_active"] is False

    @patch("cja_auto_sdr.cli.execution._generator_module")
    def test_shared_cache_inactive_when_cache_disabled(self, mock_gen):
        mock_gen.return_value = MagicMock()
        mock_gen.return_value._check_output_dir_access.return_value = (True, "/tmp/test", None, None)
        from cja_auto_sdr.cli.execution import prepare_sdr_execution_context

        args = self._make_args(shared_cache=True, batch=True, enable_cache=False, skip_validation=False)
        ctx = prepare_sdr_execution_context(args, data_views=["dv_1", "dv_2"])
        assert ctx["shared_cache_active"] is False

    @patch("cja_auto_sdr.cli.execution._generator_module")
    def test_api_auto_tune_requested_true(self, mock_gen):
        mock_gen.return_value = MagicMock()
        mock_gen.return_value._check_output_dir_access.return_value = (True, "/tmp/test", None, None)
        mock_gen.return_value.APITuningConfig.return_value = MagicMock(min_workers=1, max_workers=10)
        from cja_auto_sdr.cli.execution import prepare_sdr_execution_context

        args = self._make_args(api_auto_tune=True, api_min_workers=1, api_max_workers=10)
        ctx = prepare_sdr_execution_context(args, data_views=["dv_1"])
        assert ctx["api_auto_tune_requested"] is True

    @patch("cja_auto_sdr.cli.execution._generator_module")
    def test_circuit_breaker_enabled_true(self, mock_gen):
        mock_gen.return_value = MagicMock()
        mock_gen.return_value._check_output_dir_access.return_value = (True, "/tmp/test", None, None)
        mock_gen.return_value.CircuitBreakerConfig.return_value = MagicMock(failure_threshold=5, timeout_seconds=30.0)
        from cja_auto_sdr.cli.execution import prepare_sdr_execution_context

        args = self._make_args(circuit_breaker=True, circuit_failure_threshold=5, circuit_timeout=30.0)
        ctx = prepare_sdr_execution_context(args, data_views=["dv_1"])
        assert ctx["circuit_breaker_enabled"] is True


# ==================== Org-report lock block reshaping ====================


class TestOrgReportLockBlockReshaping:
    """Test that flat lock_details from run_org_report() are reshaped into spec's lock block."""

    def _simulate_org_report_details_merge(
        self,
        lock_details: dict[str, Any],
        *,
        success: bool = True,
        thresholds_exceeded: bool = False,
        lock_stale_threshold_seconds: int = 3600,
    ) -> dict[str, Any]:
        """Reproduce the org-report details merge logic from generator.py."""
        run_state: dict[str, Any] = {"details": {}}
        run_state["details"] = {
            "operation_success": success,
            "thresholds_exceeded": thresholds_exceeded,
            "fail_on_threshold": False,
        }

        lock_block: dict[str, Any] = {}
        if "lock_acquired" in lock_details:
            lock_block["acquired"] = lock_details["lock_acquired"]
        if "lock_stale_threshold_seconds" in lock_details:
            lock_block["stale_threshold_seconds"] = lock_details["lock_stale_threshold_seconds"]
        if "lock_contention" in lock_details:
            lock_block["contention_observed"] = lock_details["lock_contention"]
        if "lock_ownership_lost" in lock_details:
            lock_block["lost_during_run"] = lock_details["lock_ownership_lost"]
        else:
            if "lock_acquired" in lock_details:
                lock_block["lost_during_run"] = False
        if "lock_backend" in lock_details:
            lock_block["backend"] = lock_details["lock_backend"]
        if lock_details.get("lock_ownership_lost"):
            lock_block["loss_reason"] = "ownership_lost_during_execution"

        if lock_block:
            _merge_run_details(run_state, lock=lock_block)

        org_exec_settings: dict[str, Any] = {
            "org_lock_stale_threshold_seconds": lock_stale_threshold_seconds,
        }
        _merge_run_details(run_state, execution_settings=org_exec_settings)

        return run_state["details"]

    def test_successful_lock_acquisition(self):
        lock_details = {
            "lock_acquired": True,
            "lock_contention": False,
            "lock_stale_threshold_seconds": 3600,
        }
        details = self._simulate_org_report_details_merge(lock_details)
        assert details["lock"]["acquired"] is True
        assert details["lock"]["contention_observed"] is False
        assert details["lock"]["stale_threshold_seconds"] == 3600
        assert details["lock"]["lost_during_run"] is False
        assert "loss_reason" not in details["lock"]

    def test_contention_lock_details(self):
        lock_details = {
            "lock_acquired": False,
            "lock_contention": True,
            "lock_stale_threshold_seconds": 3600,
            "lock_holder_pid": 12345,
            "lock_holder_owner": "user@host",
            "lock_backend": "filesystem",
            "lock_started_at": "2026-03-15T10:00:00",
        }
        details = self._simulate_org_report_details_merge(lock_details, success=False)
        assert details["lock"]["acquired"] is False
        assert details["lock"]["contention_observed"] is True
        assert details["lock"]["backend"] == "filesystem"
        assert details["lock"]["lost_during_run"] is False

    def test_ownership_lost_lock_details(self):
        lock_details = {
            "lock_acquired": True,
            "lock_contention": False,
            "lock_ownership_lost": True,
            "lock_stale_threshold_seconds": 3600,
        }
        details = self._simulate_org_report_details_merge(lock_details, success=False)
        assert details["lock"]["acquired"] is True
        assert details["lock"]["lost_during_run"] is True
        assert details["lock"]["loss_reason"] == "ownership_lost_during_execution"

    def test_org_lock_stale_threshold_in_execution_settings(self):
        lock_details = {
            "lock_acquired": True,
            "lock_contention": False,
            "lock_stale_threshold_seconds": 7200,
        }
        details = self._simulate_org_report_details_merge(lock_details, lock_stale_threshold_seconds=7200)
        assert details["execution_settings"]["org_lock_stale_threshold_seconds"] == 7200

    def test_preserves_operation_success(self):
        lock_details = {"lock_acquired": True, "lock_contention": False, "lock_stale_threshold_seconds": 3600}
        details = self._simulate_org_report_details_merge(lock_details, success=True, thresholds_exceeded=True)
        assert details["operation_success"] is True
        assert details["thresholds_exceeded"] is True

    def test_empty_lock_details(self):
        """When run_org_report sets no lock_details, no lock block is added."""
        details = self._simulate_org_report_details_merge({})
        assert "lock" not in details
        # But execution_settings is still present
        assert "execution_settings" in details


# ==================== SDR mode execution_settings shape ====================


class TestSdrModeExecutionSettings:
    """Test execution_settings shape for SDR processing modes."""

    def test_execution_settings_keys(self):
        """Verify the expected keys in execution_settings for SDR mode."""
        run_state: dict[str, Any] = {"details": {}}
        execution_settings = {
            "batch_workers_requested": "auto",
            "batch_workers_effective": 4,
            "api_auto_tune_requested": False,
            "circuit_breaker_enabled": False,
            "shared_cache_active": False,
        }
        _merge_run_details(run_state, execution_settings=execution_settings)

        es = run_state["details"]["execution_settings"]
        assert es["batch_workers_requested"] == "auto"
        assert es["batch_workers_effective"] == 4
        assert es["api_auto_tune_requested"] is False
        assert es["circuit_breaker_enabled"] is False
        assert es["shared_cache_active"] is False

    def test_execution_settings_with_int_workers(self):
        run_state: dict[str, Any] = {"details": {}}
        execution_settings = {
            "batch_workers_requested": 8,
            "batch_workers_effective": 8,
            "api_auto_tune_requested": True,
            "circuit_breaker_enabled": True,
            "shared_cache_active": True,
        }
        _merge_run_details(run_state, execution_settings=execution_settings)

        es = run_state["details"]["execution_settings"]
        assert es["batch_workers_requested"] == 8
        assert es["batch_workers_effective"] == 8
        assert es["api_auto_tune_requested"] is True
        assert es["circuit_breaker_enabled"] is True
        assert es["shared_cache_active"] is True

    def test_non_org_report_has_no_lock_block(self):
        """Non-org-report SDR runs should not have a lock block."""
        run_state: dict[str, Any] = {"details": {}}
        execution_settings = {
            "batch_workers_requested": 4,
            "batch_workers_effective": 4,
            "api_auto_tune_requested": False,
            "circuit_breaker_enabled": False,
            "shared_cache_active": False,
        }
        _merge_run_details(run_state, execution_settings=execution_settings)
        assert "lock" not in run_state["details"]
