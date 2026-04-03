"""Tests verifying command-boundary exception handling in generator.py.

These tests enforce a strict CLI boundary contract:
  - recoverable API/bootstrap failures (including ConfigurationError) are
    surfaced as controlled user-facing failures.
  - non-recoverable failures outside the configured tuples still propagate.
"""

import logging
from unittest.mock import MagicMock, PropertyMock, patch

import pytest

from cja_auto_sdr import generator
from cja_auto_sdr.api.quality import DataQualityChecker
from cja_auto_sdr.core.exceptions import ConfigurationError
from cja_auto_sdr.core.logging import _safe_format_exception, _safe_record_message, _safe_str
from cja_auto_sdr.generator import (
    _require_accessible_dataview,
    validate_data_view,
)
from cja_auto_sdr.generator import test_profile as run_test_profile

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_logger() -> logging.Logger:
    """Return a quiet logger for test use."""
    logger = logging.getLogger("test_exception_narrowing")
    logger.setLevel(logging.CRITICAL)
    return logger


# ===========================================================================
# Group B: test_profile  (catches RECOVERABLE_CONFIG_API_EXCEPTIONS + plain Exception fallback)
# ===========================================================================


class TestTestProfileExceptionNarrowing:
    """Verify test_profile catches recoverable/bootstrap failures and propagates others."""

    def _run_with_side_effect(self, exc, tmp_path, capsys):
        """Helper: invoke test_profile with in-memory cjapy configuration raising *exc*."""
        profile_dir = tmp_path / "orgs" / "narrowing"
        profile_dir.mkdir(parents=True)
        (profile_dir / "config.json").write_text('{"client_id":"x","secret":"s","org_id":"o@AdobeOrg"}')

        with (
            patch("cja_auto_sdr.generator.get_profile_path", return_value=profile_dir),
            patch("cja_auto_sdr.generator.cjapy"),
            patch("cja_auto_sdr.generator._config_from_env", side_effect=exc),
            patch("cja_auto_sdr.generator.ConfigValidator") as mock_validator,
        ):
            mock_validator.validate_all.return_value = []
            return run_test_profile("narrowing")

    def test_os_error_caught(self, tmp_path, capsys):
        """OSError (in RECOVERABLE_API_EXCEPTIONS) is caught -> returns False."""
        result = self._run_with_side_effect(OSError("network down"), tmp_path, capsys)
        assert result is False
        assert "FAILED" in capsys.readouterr().err

    def test_value_error_caught(self, tmp_path, capsys):
        """ValueError (in RECOVERABLE_API_EXCEPTIONS) is caught -> returns False."""
        result = self._run_with_side_effect(ValueError("bad token"), tmp_path, capsys)
        assert result is False

    def test_configuration_error_caught(self, tmp_path, capsys):
        """ConfigurationError should return a controlled failure, not a traceback."""
        result = self._run_with_side_effect(ConfigurationError("invalid profile credentials"), tmp_path, capsys)
        assert result is False
        assert "FAILED" in capsys.readouterr().err

    def test_runtime_error_caught(self, tmp_path, capsys):
        """RuntimeError in the fallback tuple should return a controlled failure."""
        result = self._run_with_side_effect(RuntimeError("should not escape"), tmp_path, capsys)
        assert result is False
        assert "FAILED" in capsys.readouterr().err

    def test_attribute_error_caught(self, tmp_path, capsys):
        """AttributeError in the fallback tuple should return a controlled failure."""
        result = self._run_with_side_effect(AttributeError("missing bootstrap field"), tmp_path, capsys)
        assert result is False

    def test_plain_exception_caught(self, tmp_path, capsys):
        """Bare Exception from bootstrap should return a controlled failure."""
        result = self._run_with_side_effect(Exception("auth bootstrap failed"), tmp_path, capsys)
        assert result is False
        assert "FAILED" in capsys.readouterr().err

    def test_system_error_propagates(self, tmp_path, capsys):
        """SystemError is NOT in RECOVERABLE_API_EXCEPTIONS -> propagates."""
        with pytest.raises(SystemError, match="should escape"):
            self._run_with_side_effect(SystemError("should escape"), tmp_path, capsys)


# ===========================================================================
# Group B: validate_data_view  (outer guard catches RECOVERABLE_CONFIG_API_EXCEPTIONS)
# ===========================================================================


class TestValidateDataViewExceptionNarrowing:
    """Verify validate_data_view catches recoverable failures and propagates others."""

    def test_type_error_caught(self):
        """TypeError (in RECOVERABLE_API_EXCEPTIONS) is caught -> returns False."""
        mock_cja = MagicMock()
        mock_cja.getDataView.side_effect = TypeError("bad payload")
        assert validate_data_view(mock_cja, "dv_test", _make_logger()) is False

    def test_key_error_caught(self):
        """KeyError (in RECOVERABLE_API_EXCEPTIONS) is caught -> returns False."""
        mock_cja = MagicMock()
        mock_cja.getDataView.side_effect = KeyError("missing key")
        assert validate_data_view(mock_cja, "dv_test", _make_logger()) is False

    def test_runtime_error_propagates(self):
        """RuntimeError is NOT in RECOVERABLE_API_EXCEPTIONS -> propagates."""
        mock_cja = MagicMock()
        mock_cja.getDataView.side_effect = RuntimeError("should escape")
        with pytest.raises(RuntimeError, match="should escape"):
            validate_data_view(mock_cja, "dv_test", _make_logger())

    def test_system_error_propagates(self):
        """SystemError is NOT in RECOVERABLE_API_EXCEPTIONS -> propagates."""
        mock_cja = MagicMock()
        mock_cja.getDataView.side_effect = SystemError("should escape")
        with pytest.raises(SystemError, match="should escape"):
            validate_data_view(mock_cja, "dv_test", _make_logger())

    def test_configuration_error_while_listing_available_views_caught(self):
        """ConfigurationError from fallback list call should not escape."""
        mock_cja = MagicMock()
        mock_cja.getDataView.return_value = None
        mock_cja.getDataViews.side_effect = ConfigurationError("token bootstrap failed")
        assert validate_data_view(mock_cja, "dv_test", _make_logger()) is False


# ===========================================================================
# Group B: _require_accessible_dataview  (centralized dataview lookup classification)
# ===========================================================================


class TestRequireAccessibleDataviewExceptionNarrowing:
    """Verify _require_accessible_dataview maps inaccessible lookups and re-raises others."""

    def test_os_error_reraises(self):
        """OSError (in RECOVERABLE_API_EXCEPTIONS) is caught and re-raised."""
        mock_cja = MagicMock()
        mock_cja.getDataView.side_effect = OSError("connection reset")
        # The handler re-raises if _is_inaccessible_dataview_lookup_error returns False
        with pytest.raises(OSError, match="connection reset"):
            _require_accessible_dataview(mock_cja, "dv_test")

    def test_value_error_reraises(self):
        """ValueError (in RECOVERABLE_API_EXCEPTIONS) is caught and re-raised."""
        mock_cja = MagicMock()
        mock_cja.getDataView.side_effect = ValueError("bad id")
        with pytest.raises(ValueError, match="bad id"):
            _require_accessible_dataview(mock_cja, "dv_test")

    def test_runtime_error_propagates(self):
        """RuntimeError without lookup metadata should propagate unchanged."""
        mock_cja = MagicMock()
        mock_cja.getDataView.side_effect = RuntimeError("should escape")
        with pytest.raises(RuntimeError, match="should escape"):
            _require_accessible_dataview(mock_cja, "dv_test")

    def test_runtime_error_with_404_metadata_maps_to_not_found(self):
        """Non-whitelisted wrappers with 403/404 metadata must still map to not_found."""
        mock_cja = MagicMock()
        lookup_error = RuntimeError("wrapped lookup failure")
        lookup_error.response = {"error": {"statusCode": "404"}}  # type: ignore[attr-defined]
        mock_cja.getDataView.side_effect = lookup_error

        with pytest.raises(generator.DiscoveryNotFoundError, match="Data view 'dv_test' not found"):
            _require_accessible_dataview(mock_cja, "dv_test")

    def test_os_error_with_404_metadata_maps_to_not_found(self):
        """OSError wrappers carrying lookup metadata must normalize to not_found."""
        mock_cja = MagicMock()
        lookup_error = OSError("wrapped lookup failure")
        lookup_error.response = {"error": {"statusCode": "404"}}  # type: ignore[attr-defined]
        mock_cja.getDataView.side_effect = lookup_error

        with pytest.raises(generator.DiscoveryNotFoundError, match="Data view 'dv_test' not found"):
            _require_accessible_dataview(mock_cja, "dv_test")


# ===========================================================================
# Group A: process_inventory_summary  (fallback -> plain Exception, except SystemError)
# ===========================================================================


class TestProcessInventorySummaryExceptionNarrowing:
    """Verify process_inventory_summary fallback catches third-party Exception failures."""

    def _run_with_side_effect(self, exc):
        """Mock CJA init + getDataView raising *exc*."""
        mock_cja = MagicMock()
        mock_cja.getDataView.side_effect = exc

        with (
            patch("cja_auto_sdr.generator.initialize_cja", return_value=mock_cja),
            patch("cja_auto_sdr.generator.setup_logging", return_value=_make_logger()),
            patch("cja_auto_sdr.generator.with_log_context", return_value=_make_logger()),
        ):
            return generator.process_inventory_summary(
                data_view_id="dv_test",
                config_file="config.json",
            )

    def test_runtime_error_caught(self):
        """RuntimeError (in fallback tuple) is caught -> returns error dict."""
        result = self._run_with_side_effect(RuntimeError("cjapy internal"))
        assert "error" in result

    def test_attribute_error_caught(self):
        """AttributeError (in fallback tuple) is caught -> returns error dict."""
        result = self._run_with_side_effect(AttributeError("no attribute"))
        # AttributeError is in BOTH tuples — first handler catches it
        assert "error" in result

    def test_configuration_error_caught(self):
        """ConfigurationError should be returned as structured summary error payload."""
        result = self._run_with_side_effect(ConfigurationError("invalid auth bootstrap"))
        assert "error" in result
        assert "invalid auth bootstrap" in result["error"]

    def test_plain_exception_caught(self):
        """Bare Exception from cjapy bootstrap should return a controlled error payload."""
        result = self._run_with_side_effect(Exception("auth bootstrap failed"))
        assert "error" in result
        assert "auth bootstrap failed" in result["error"]

    def test_system_error_propagates(self):
        """SystemError is NOT in either handler -> propagates."""
        with pytest.raises(SystemError, match="should escape"):
            self._run_with_side_effect(SystemError("should escape"))


# ===========================================================================
# Group A: validate_config_only  (fallback -> plain Exception, except SystemError)
# ===========================================================================


class TestValidateConfigOnlyExceptionNarrowing:
    """Verify validate_config_only fallback catches third-party Exception failures."""

    def _run_with_cja_side_effect(self, exc):
        """Mock credential resolution + cjapy.CJA() raising *exc*."""
        fake_creds = {"org_id": "X@AdobeOrg", "client_id": "cid", "secret": "sec"}
        with (
            patch("cja_auto_sdr.generator.load_credentials_from_env", return_value=fake_creds),
            patch("cja_auto_sdr.generator.validate_env_credentials", return_value=True),
            patch("cja_auto_sdr.generator._config_from_env"),
            patch("cja_auto_sdr.generator.cjapy") as mock_cjapy,
            patch("cja_auto_sdr.generator._check_output_dir_access", return_value=(True, ".", None, None)),
        ):
            mock_cjapy.CJA.side_effect = exc
            return generator.validate_config_only(config_file="config.json")

    def test_runtime_error_caught(self):
        """RuntimeError (in fallback tuple) is caught -> returns False."""
        result = self._run_with_cja_side_effect(RuntimeError("cjapy init failed"))
        assert result is False

    def test_attribute_error_caught(self):
        """AttributeError (in fallback tuple) is caught -> returns False."""
        result = self._run_with_cja_side_effect(AttributeError("missing method"))
        # AttributeError is in BOTH RECOVERABLE_API and fallback; first handler catches
        assert result is False

    def test_configuration_error_caught(self):
        """ConfigurationError should return False (controlled validation failure)."""
        result = self._run_with_cja_side_effect(ConfigurationError("invalid oauth configuration"))
        assert result is False

    def test_plain_exception_caught(self):
        """Bare Exception from CJA bootstrap should return False."""
        result = self._run_with_cja_side_effect(Exception("auth bootstrap failed"))
        assert result is False

    def test_system_error_propagates(self):
        """SystemError is NOT in either handler -> propagates."""
        with pytest.raises(SystemError, match="should escape"):
            self._run_with_cja_side_effect(SystemError("should escape"))


class TestResolveDataViewNamesExceptionBoundary:
    """Verify resolve_data_view_names handles recoverable bootstrap failures."""

    def test_configuration_error_returns_connectivity_diagnostics(self):
        """ConfigurationError should produce controlled connectivity diagnostics."""
        with patch("cja_auto_sdr.generator.configure_cjapy", side_effect=ConfigurationError("bad org credentials")):
            ids, name_map, diagnostics = generator.resolve_data_view_names(
                ["My DV"],
                include_diagnostics=True,
            )

        assert ids == []
        assert name_map == {}
        assert diagnostics.error_type == "connectivity_error"
        assert "bad org credentials" in diagnostics.error_message

    def test_plain_exception_returns_connectivity_diagnostics(self):
        """Bare Exception from cjapy bootstrap should produce controlled diagnostics."""
        with patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "env", {})):
            with patch("cja_auto_sdr.generator.cjapy") as mock_cjapy:
                mock_cjapy.CJA.side_effect = Exception("auth bootstrap failed")
                ids, name_map, diagnostics = generator.resolve_data_view_names(
                    ["My DV"],
                    include_diagnostics=True,
                )

        assert ids == []
        assert name_map == {}
        assert diagnostics.error_type == "connectivity_error"
        assert "auth bootstrap failed" in diagnostics.error_message


# ===========================================================================
# Group A: _count_component_items_for_fetch_spec_with_retry (best-effort)
# ===========================================================================


class TestComponentCountRetryExceptionBoundary:
    """Verify retry-based component counting degrades recoverable optional failures."""

    def _run_count_with_retry_side_effect(self, exc):
        """Run component count helper with a patched retry call that raises *exc*."""
        with patch("cja_auto_sdr.cli.commands.discovery.make_api_call_with_retry", side_effect=exc):
            return generator._count_component_items_for_fetch_spec_with_retry(
                MagicMock(),
                "dv_test",
                generator._METRICS_COMPONENT_FETCH_SPEC,
                logger=_make_logger(),
            )

    def test_discovery_not_found_error_degrades_to_zero(self):
        """Missing component methods should degrade to zero instead of raising."""
        result = self._run_count_with_retry_side_effect(
            generator.DiscoveryNotFoundError("missing getMetrics"),
        )
        assert result == 0

    def test_runtime_error_degrades_to_zero(self):
        """Unexpected runtime errors in optional count collection should degrade to zero."""
        result = self._run_count_with_retry_side_effect(RuntimeError("cjapy internal bug"))
        assert result == 0

    def test_keyboard_interrupt_propagates(self):
        """BaseException subclasses must still propagate through the helper."""
        with pytest.raises(KeyboardInterrupt):
            self._run_count_with_retry_side_effect(KeyboardInterrupt())


# ===========================================================================
# Group C: DataQualityChecker — narrowed handlers in api/quality.py
# ===========================================================================


class TestDataQualityExceptionNarrowing:
    """Verify narrowed except clauses in DataQualityChecker methods."""

    def _make_checker(self) -> DataQualityChecker:
        return DataQualityChecker(logger=_make_logger())

    def _mock_df_raising_on_empty(self, exc_type: type[Exception]) -> MagicMock:
        """Return a MagicMock whose .empty property raises *exc_type*."""
        df = MagicMock()
        type(df).empty = PropertyMock(side_effect=exc_type("boom"))
        return df

    # -- check_duplicates: KeyError, TypeError, AttributeError, ValueError --

    def test_check_duplicates_catches_key_error(self):
        """KeyError on DataFrame access is caught by check_duplicates."""
        checker = self._make_checker()
        df = self._mock_df_raising_on_empty(KeyError)
        checker.check_duplicates(df, "Metrics")  # should not raise

    def test_check_duplicates_propagates_runtime_error(self):
        """RuntimeError is NOT in check_duplicates tuple -> propagates."""
        checker = self._make_checker()
        df = self._mock_df_raising_on_empty(RuntimeError)
        with pytest.raises(RuntimeError, match="boom"):
            checker.check_duplicates(df, "Metrics")

    # -- check_required_fields: TypeError, AttributeError --

    def test_check_required_fields_catches_type_error(self):
        """TypeError on DataFrame access is caught by check_required_fields."""
        checker = self._make_checker()
        df = self._mock_df_raising_on_empty(TypeError)
        checker.check_required_fields(df, "Metrics", ["name"])  # should not raise

    def test_check_required_fields_propagates_runtime_error(self):
        """RuntimeError is NOT in check_required_fields tuple -> propagates."""
        checker = self._make_checker()
        df = self._mock_df_raising_on_empty(RuntimeError)
        with pytest.raises(RuntimeError, match="boom"):
            checker.check_required_fields(df, "Metrics", ["name"])

    # -- check_null_values: KeyError, TypeError, AttributeError, ValueError --

    def test_check_null_values_catches_attribute_error(self):
        """AttributeError on DataFrame access is caught by check_null_values."""
        checker = self._make_checker()
        df = self._mock_df_raising_on_empty(AttributeError)
        checker.check_null_values(df, "Metrics", ["name"])  # should not raise

    def test_check_null_values_propagates_runtime_error(self):
        """RuntimeError is NOT in check_null_values tuple -> propagates."""
        checker = self._make_checker()
        df = self._mock_df_raising_on_empty(RuntimeError)
        with pytest.raises(RuntimeError, match="boom"):
            checker.check_null_values(df, "Metrics", ["name"])

    # -- check_missing_descriptions: KeyError, TypeError, AttributeError, ValueError --

    def test_check_missing_descriptions_catches_value_error(self):
        """ValueError on DataFrame access is caught by check_missing_descriptions."""
        checker = self._make_checker()
        df = self._mock_df_raising_on_empty(ValueError)
        checker.check_missing_descriptions(df, "Dimensions")  # should not raise

    def test_check_missing_descriptions_propagates_runtime_error(self):
        """RuntimeError is NOT in check_missing_descriptions tuple -> propagates."""
        checker = self._make_checker()
        df = self._mock_df_raising_on_empty(RuntimeError)
        with pytest.raises(RuntimeError, match="boom"):
            checker.check_missing_descriptions(df, "Dimensions")

    # -- check_empty_dataframe: AttributeError, TypeError --

    def test_check_empty_dataframe_catches_attribute_error(self):
        """AttributeError on DataFrame access is caught by check_empty_dataframe."""
        checker = self._make_checker()
        df = self._mock_df_raising_on_empty(AttributeError)
        checker.check_empty_dataframe(df, "Metrics")  # should not raise

    def test_check_empty_dataframe_propagates_runtime_error(self):
        """RuntimeError is NOT in check_empty_dataframe tuple -> propagates."""
        checker = self._make_checker()
        df = self._mock_df_raising_on_empty(RuntimeError)
        with pytest.raises(RuntimeError, match="boom"):
            checker.check_empty_dataframe(df, "Metrics")

    # -- check_id_validity: KeyError, TypeError, AttributeError, ValueError --

    def test_check_id_validity_catches_type_error(self):
        """TypeError on DataFrame access is caught by check_id_validity."""
        checker = self._make_checker()
        df = self._mock_df_raising_on_empty(TypeError)
        checker.check_id_validity(df, "Dimensions")  # should not raise

    def test_check_id_validity_propagates_runtime_error(self):
        """RuntimeError is NOT in check_id_validity tuple -> propagates."""
        checker = self._make_checker()
        df = self._mock_df_raising_on_empty(RuntimeError)
        with pytest.raises(RuntimeError, match="boom"):
            checker.check_id_validity(df, "Dimensions")


# ---------------------------------------------------------------------------
# core/logging.py helper narrowing
# ---------------------------------------------------------------------------


class TestLoggingHelperExceptionNarrowing:
    """Verify logging helper best-effort boundaries remain non-fatal."""

    # -- _safe_str --------------------------------------------------------

    def test_safe_str_catches_type_error(self):
        """TypeError from __str__ is caught -> '<unprintable>'."""

        class BadStr:
            def __str__(self):
                raise TypeError("boom")

        assert _safe_str(BadStr()) == "<unprintable>"

    def test_safe_str_catches_attribute_error(self):
        """AttributeError from __str__ is caught -> '<unprintable>'."""

        class BadStr:
            def __str__(self):
                raise AttributeError("boom")

        assert _safe_str(BadStr()) == "<unprintable>"

    def test_safe_str_catches_runtime_error(self):
        """RuntimeError should not escape logging stringification helpers."""

        class BadStr:
            def __str__(self):
                raise RuntimeError("boom")

        assert _safe_str(BadStr()) == "<unprintable>"

    # -- _safe_record_message ---------------------------------------------

    def test_safe_record_message_catches_type_error(self):
        """TypeError during getMessage() is caught gracefully."""
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="",
            lineno=0,
            msg="%d",
            args=("not-a-number",),
            exc_info=None,
        )
        result = _safe_record_message(record)
        assert isinstance(result, str)

    def test_safe_record_message_catches_runtime_error(self):
        """RuntimeError from getMessage() should not escape logging helpers."""
        record = MagicMock(spec=logging.LogRecord)
        record.getMessage.side_effect = RuntimeError("boom")
        record.msg = "msg-template"
        result = _safe_record_message(record)
        assert result.endswith("[log-message-format-error]")

    # -- _safe_format_exception -------------------------------------------

    def test_safe_format_exception_catches_type_error(self):
        """Malformed exc_info tuple that triggers TypeError -> error string."""
        result = _safe_format_exception((None, None, None))
        assert isinstance(result, str)

    def test_safe_format_exception_non_tuple_returns_unavailable(self):
        """Non-tuple input -> '<exception-unavailable>'."""
        assert _safe_format_exception("not-a-tuple") == "<exception-unavailable>"


# ===========================================================================
# Group D: LockInfo.from_dict — narrowed (KeyError, TypeError, ValueError, OverflowError)
# ===========================================================================


class TestLockBackendsExceptionNarrowing:
    """Verify narrowed except clauses in LockInfo.from_dict."""

    def test_from_dict_catches_key_error(self):
        """Empty dict triggers KeyError in modern parse -> returns None."""
        from cja_auto_sdr.core.locks.backends import LockInfo

        result = LockInfo.from_dict({})
        assert result is None

    def test_from_dict_catches_type_error(self):
        """Dict with None pid triggers TypeError in int() coercion -> returns None."""
        from cja_auto_sdr.core.locks.backends import LockInfo

        result = LockInfo.from_dict(
            {
                "lock_id": "abc",
                "pid": None,
                "host": "localhost",
                "started_at": "2024-01-01T00:00:00+00:00",
            }
        )
        assert result is None

    def test_from_dict_valid_dict_succeeds(self):
        """Valid dict round-trips through from_dict successfully."""
        from cja_auto_sdr.core.locks.backends import LockInfo

        info = LockInfo(
            lock_id="test-123",
            pid=12345,
            host="myhost",
            owner="tester",
            started_at="2024-01-01T00:00:00+00:00",
            updated_at="2024-01-01T00:00:00+00:00",
            backend="fcntl",
            version=1,
        )
        restored = LockInfo.from_dict(info.to_dict())
        assert restored is not None
        assert restored.pid == 12345
        assert restored.lock_id == "test-123"
        assert restored.host == "myhost"

    def test_from_dict_narrowing_preserves_happy_path(self):
        """Narrowed handlers do not break the normal code path."""
        from cja_auto_sdr.core.locks.backends import LockInfo

        data = {
            "lock_id": "round-trip",
            "pid": 99,
            "host": "h",
            "owner": "o",
            "started_at": "2024-06-01T12:00:00+00:00",
            "updated_at": "2024-06-01T12:00:00+00:00",
            "backend": "lease",
            "version": 1,
        }
        result = LockInfo.from_dict(data)
        assert result is not None
        assert result.pid == 99
        assert result.backend == "lease"
