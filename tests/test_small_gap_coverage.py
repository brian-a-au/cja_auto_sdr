from __future__ import annotations

import argparse
import errno
import logging
from unittest.mock import MagicMock, patch

import pytest

import cja_auto_sdr.core.json_io as json_io
import cja_auto_sdr.pipeline.dry_run as pipeline_dry_run
import cja_auto_sdr.pipeline.single as pipeline_single
from cja_auto_sdr.api.cache import SharedValidationCache, ValidationCache
from cja_auto_sdr.cli.mode_scoped_options import (
    ORG_REPORT_MODE_SCOPED_OPTION_SPECS,
    org_report_mode_scoped_option_names,
)
from cja_auto_sdr.core.logging import (
    SensitiveDataFilter,
    _LOG_FORMAT_ERROR,
    _LOG_REDACTION_ERROR,
    _format_diagnostic_text_value,
    _safe_json_dumps,
    _safe_redact_extra_fields,
    _safe_redact_message,
    _safe_redact_value,
)
from cja_auto_sdr.org.identifiers import normalize_org_report_data_view_id


def test_pipeline_dry_run_wrapper_uses_real_generator_module() -> None:
    logger = logging.getLogger("test_pipeline_dry_run_wrapper")

    with patch("cja_auto_sdr.generator.run_dry_run", return_value=True) as mock_run:
        result = pipeline_dry_run.run_dry_run(["dv_1"], "config.json", logger, profile="team-a")

    assert result is True
    mock_run.assert_called_once_with(["dv_1"], "config.json", logger, profile="team-a")


def test_pipeline_single_wrapper_uses_real_generator_module_and_signature_binding() -> None:
    pipeline_single._process_single_dataview_signature.cache_clear()
    expected = object()

    try:
        with patch("cja_auto_sdr.generator.process_single_dataview", return_value=expected) as mock_process:
            result = pipeline_single.process_single_dataview("dv_1", "config.json", "/tmp/out")
    finally:
        pipeline_single._process_single_dataview_signature.cache_clear()

    assert result is expected
    mock_process.assert_called_once_with("dv_1", "config.json", "/tmp/out")


def test_normalize_org_report_data_view_id_none_returns_empty_string() -> None:
    assert normalize_org_report_data_view_id(None) == ""
    assert normalize_org_report_data_view_id("  dv_1  ") == "dv_1"


def test_org_report_mode_scoped_option_names_returns_option_strings() -> None:
    option_names = org_report_mode_scoped_option_names()

    assert option_names == tuple(spec.option_name for spec in ORG_REPORT_MODE_SCOPED_OPTION_SPECS)
    assert "--trending-window" in option_names
    assert "--lock-stale-threshold" in option_names


def test_json_io_fsync_directory_suppresses_best_effort_errors(tmp_path) -> None:
    with patch("cja_auto_sdr.core.json_io.os.open", side_effect=OSError(errno.EPERM, "no dir fsync")):
        json_io._fsync_directory(tmp_path)


def test_json_io_fsync_directory_reraises_unexpected_errors(tmp_path) -> None:
    with (
        patch("cja_auto_sdr.core.json_io.os.open", side_effect=OSError(errno.ENOENT, "missing")),
        pytest.raises(OSError, match="missing"),
    ):
        json_io._fsync_directory(tmp_path)


def test_write_json_atomic_closes_fd_when_fdopen_fails(tmp_path) -> None:
    output_path = tmp_path / "payload.json"

    with (
        patch("cja_auto_sdr.core.json_io.os.open", return_value=123),
        patch("cja_auto_sdr.core.json_io.os.fdopen", side_effect=OSError("fdopen boom")),
        patch("cja_auto_sdr.core.json_io.os.close") as mock_close,
        pytest.raises(OSError, match="fdopen boom"),
    ):
        json_io.write_json_atomic(output_path, {"key": "value"})

    mock_close.assert_called_with(123)


def test_validation_cache_capacity_clear_fallback_warns_and_clears_cache() -> None:
    logger = MagicMock()
    cache = ValidationCache(max_size=1, ttl_seconds=3600, logger=logger)
    cache._cache["existing"] = ([{"issue": "old"}], 1.0)

    with patch.object(cache, "_evict_lru", side_effect=lambda debug_enabled=False: None):
        with cache._lock:
            cache._ensure_capacity_for_new_entry(now=2.0)

    logger.warning.assert_called_once()
    assert not cache._cache


def test_shared_cache_reconcile_access_times_removes_stale_and_backfills_missing() -> None:
    cache = SharedValidationCache(max_size=2, ttl_seconds=3600)

    try:
        cache._cache["live"] = ([{"issue": "new"}], 1.0)
        cache._access_times["stale"] = 0.5

        with cache._lock:
            cache._reconcile_access_times(now=5.0)

        assert "stale" not in cache._access_times
        assert cache._access_times["live"] == 5.0
    finally:
        cache.shutdown()


def test_shared_cache_capacity_fallback_removes_entry_when_evict_lru_stalls() -> None:
    cache = SharedValidationCache(max_size=1, ttl_seconds=3600)

    try:
        cache._cache["old"] = ([{"issue": "old"}], 1.0)
        cache._access_times["old"] = 1.0

        with patch.object(cache, "_evict_lru", return_value=False):
            with cache._lock:
                cache._ensure_capacity_for_new_entry(now=2.0)

        assert dict(cache._cache) == {}
        assert cache.get_statistics()["evictions"] == 1
    finally:
        cache.shutdown()


def test_shared_cache_evict_lru_uses_cache_iteration_when_access_times_missing() -> None:
    cache = SharedValidationCache(max_size=1, ttl_seconds=3600)

    try:
        cache._cache["real"] = ([{"issue": "kept"}], 1.0)

        with cache._lock:
            removed = cache._evict_lru(now=2.0, access_times_reconciled=True)

        assert removed is True
        assert dict(cache._cache) == {}
        assert cache.get_statistics()["evictions"] == 1
    finally:
        cache.shutdown()


def test_shared_cache_evict_lru_falls_back_after_stale_access_metadata() -> None:
    cache = SharedValidationCache(max_size=1, ttl_seconds=3600)

    try:
        cache._cache["real"] = ([{"issue": "kept"}], 1.0)
        cache._access_times["ghost"] = 0.0

        with cache._lock:
            removed = cache._evict_lru(now=2.0, access_times_reconciled=True)

        assert removed is True
        assert dict(cache._cache) == {}
        assert "ghost" not in cache._access_times
        assert cache.get_statistics()["evictions"] == 1
    finally:
        cache.shutdown()


def test_safe_redaction_helpers_return_fallbacks_on_recoverable_errors() -> None:
    with patch("cja_auto_sdr.core.logging._redact_message", side_effect=RuntimeError("boom")):
        assert _safe_redact_message("secret=value") == _LOG_REDACTION_ERROR

    with patch("cja_auto_sdr.core.logging._redact_value", side_effect=RuntimeError("boom")):
        assert _safe_redact_value({"secret": "value"}) == _LOG_REDACTION_ERROR
        assert _safe_redact_value({"secret": "value"}, fallback={"safe": True}) == {"safe": True}

    with patch("cja_auto_sdr.core.logging._redact_extra_fields", side_effect=RuntimeError("boom")):
        assert _safe_redact_extra_fields({"api_key": "secret", "endpoint": "/v1"}) == {
            "api_key": "[REDACTED]",
            "endpoint": _LOG_REDACTION_ERROR,
        }


def test_safe_json_dumps_falls_back_to_format_error_payload() -> None:
    calls = {"count": 0}

    def flaky_json_dumps(payload, default=None):  # noqa: ANN001
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("boom")
        return '{"message":"[log-format-error]"}'

    with patch("cja_auto_sdr.core.logging.json.dumps", side_effect=flaky_json_dumps):
        assert _safe_json_dumps({"value": "boom"}) == '{"message":"[log-format-error]"}'


def test_sensitive_data_filter_recovers_from_redaction_failures() -> None:
    record = logging.LogRecord(
        name="test.logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="password=secret",
        args=(),
        exc_info=None,
    )

    with patch("cja_auto_sdr.core.logging._safe_redact_message", side_effect=RuntimeError("boom")):
        assert SensitiveDataFilter().filter(record) is True

    assert record.msg == _LOG_REDACTION_ERROR
    assert record.args == ()


def test_format_diagnostic_text_value_falls_back_to_safe_str_for_unserializable_values() -> None:
    with patch("cja_auto_sdr.core.logging.json.dumps", side_effect=RuntimeError("boom")):
        assert _format_diagnostic_text_value({"alpha": 1}) == "{'alpha': 1}"


def test_dispatch_snapshot_cli_modes_prune_stdout_forces_json_output() -> None:
    args = argparse.Namespace(
        list_snapshots=False,
        prune_snapshots=True,
        format="table",
        output="-",
        snapshot_dir="./snapshots",
        keep_last=1,
        keep_since=None,
        auto_prune=False,
    )
    run_state: dict[str, object] = {}
    snapshot_manager = MagicMock()
    snapshot_manager.list_snapshots.return_value = [{"data_view_id": "dv_1"}]
    snapshot_manager.apply_retention_policy.return_value = ["/tmp/a.json"]
    snapshot_manager.apply_date_retention_policy.return_value = []

    with (
        patch("cja_auto_sdr.diff.cli._generator_module") as mock_generator_module,
        pytest.raises(SystemExit) as exc_info,
    ):
        generator_mod = mock_generator_module.return_value
        generator_mod.is_data_view_id.return_value = True
        generator_mod.SnapshotManager.return_value = snapshot_manager
        generator_mod.resolve_auto_prune_retention.return_value = (1, None)
        generator_mod._emit_json_output = MagicMock()
        generator_mod._emit_output = MagicMock()

        from cja_auto_sdr.diff.cli import dispatch_snapshot_cli_modes

        dispatch_snapshot_cli_modes(
            args,
            data_view_inputs=[],
            output_to_stdout=True,
            ignore_fields=None,
            labels=None,
            show_only=None,
            keep_last_specified=True,
            keep_since_specified=False,
            run_state=run_state,
        )

    assert exc_info.value.code == 0
    generator_mod._emit_json_output.assert_called_once()
    generator_mod._emit_output.assert_not_called()
    assert run_state["output_format"] == "json"


def test_safe_json_dumps_fallback_payload_is_valid_json() -> None:
    calls = {"count": 0}

    def flaky_json_dumps(payload, default=None):  # noqa: ANN001
        calls["count"] += 1
        if calls["count"] == 1:
            raise RuntimeError("boom")
        return '{"message":"[log-format-error]","level":"ERROR"}'

    with patch("cja_auto_sdr.core.logging.json.dumps", side_effect=flaky_json_dumps):
        assert _LOG_FORMAT_ERROR in _safe_json_dumps({"value": "boom"})
