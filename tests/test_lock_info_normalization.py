"""Direct unit tests for OrgComponentAnalyzer lock-info normalization classmethods."""

from cja_auto_sdr.generator import OrgComponentAnalyzer


class TestNormalizeLockInfoInt:
    """Tests for _normalize_lock_info_int shared helper."""

    def test_int_passthrough(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int(42) == 42

    def test_zero_passthrough(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int(0) == 0

    def test_negative_int_passthrough(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int(-1) == -1

    def test_string_parsed_to_int(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int("123") == 123

    def test_string_with_whitespace_parsed(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int("  42  ") == 42

    def test_bool_true_rejected(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int(True) is None

    def test_bool_false_rejected(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int(False) is None

    def test_non_numeric_string_returns_none(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int("abc") is None

    def test_empty_string_returns_none(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int("") is None

    def test_whitespace_only_string_returns_none(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int("   ") is None

    def test_none_returns_none(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int(None) is None

    def test_float_returns_none(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int(3.14) is None

    def test_list_returns_none(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int([1]) is None

    def test_legacy_field_name_argument_is_ignored(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int("7", "pid") == 7


class TestSignalNameExceptionSyntax:
    """Verify _signal_name handles both ValueError and AttributeError from invalid signal numbers."""

    def test_valid_signal_returns_name(self):
        import signal

        from cja_auto_sdr.core.exit_codes import _signal_name

        # SIGTERM is universally available
        assert _signal_name(signal.SIGTERM.value) == "SIGTERM"

    def test_invalid_signal_number_returns_none(self):
        from cja_auto_sdr.core.exit_codes import _signal_name

        # 999 is not a valid signal number
        assert _signal_name(999) is None

    def test_zero_returns_none(self):
        from cja_auto_sdr.core.exit_codes import _signal_name

        assert _signal_name(0) is None


class TestNormalizeLockInfoPid:
    """Verify _normalize_lock_info_pid delegates to _normalize_lock_info_int."""

    def test_int_passthrough(self):
        assert OrgComponentAnalyzer._normalize_lock_info_pid(12345) == 12345

    def test_string_parsed(self):
        assert OrgComponentAnalyzer._normalize_lock_info_pid("999") == 999

    def test_bool_rejected(self):
        assert OrgComponentAnalyzer._normalize_lock_info_pid(True) is None

    def test_none_returns_none(self):
        assert OrgComponentAnalyzer._normalize_lock_info_pid(None) is None


class TestNormalizeLockInfoVersion:
    """Verify _normalize_lock_info_version delegates to _normalize_lock_info_int."""

    def test_int_passthrough(self):
        assert OrgComponentAnalyzer._normalize_lock_info_version(1) == 1

    def test_zero_passthrough(self):
        assert OrgComponentAnalyzer._normalize_lock_info_version(0) == 0

    def test_string_parsed(self):
        assert OrgComponentAnalyzer._normalize_lock_info_version("2") == 2

    def test_bool_rejected(self):
        assert OrgComponentAnalyzer._normalize_lock_info_version(False) is None


class TestIsLegacyContentionLockInfo:
    """Tests for legacy lock metadata detection."""

    def test_version_zero_is_legacy(self):
        assert OrgComponentAnalyzer._is_legacy_contention_lock_info({"version": 0}) is True

    def test_negative_version_is_legacy(self):
        assert OrgComponentAnalyzer._is_legacy_contention_lock_info({"version": -1}) is True

    def test_version_one_is_not_legacy(self):
        assert OrgComponentAnalyzer._is_legacy_contention_lock_info({"version": 1}) is False

    def test_version_string_zero_is_legacy(self):
        assert OrgComponentAnalyzer._is_legacy_contention_lock_info({"version": "0"}) is True

    def test_no_version_with_legacy_backend(self):
        assert OrgComponentAnalyzer._is_legacy_contention_lock_info({"backend": "legacy"}) is True

    def test_no_version_with_non_legacy_backend(self):
        assert OrgComponentAnalyzer._is_legacy_contention_lock_info({"backend": "lease"}) is False

    def test_no_version_no_backend(self):
        assert OrgComponentAnalyzer._is_legacy_contention_lock_info({}) is False

    def test_bool_version_falls_through_to_backend(self):
        """Bool version is rejected by normalizer, so backend determines legacy status."""
        assert OrgComponentAnalyzer._is_legacy_contention_lock_info({"version": True, "backend": "legacy"}) is True

    def test_version_takes_precedence_over_backend(self):
        """When version is present and valid, backend is ignored for legacy detection."""
        assert OrgComponentAnalyzer._is_legacy_contention_lock_info({"version": 1, "backend": "legacy"}) is False


class TestIsNonLiveContentionLockInfo:
    """Tests for non-live (tombstone/sentinel) lock metadata detection."""

    def test_released_host_is_non_live(self):
        assert (
            OrgComponentAnalyzer._is_non_live_contention_lock_info(
                holder_pid=123, started_at="2024-01-01T00:00:00", host_identity="released", owner_identity=None
            )
            is True
        )

    def test_owner_present_overrides_negative_pid(self):
        """Owner identity means the lock is considered live regardless of pid."""
        assert (
            OrgComponentAnalyzer._is_non_live_contention_lock_info(
                holder_pid=-1, started_at=None, host_identity=None, owner_identity="user@host"
            )
            is False
        )

    def test_negative_pid_without_owner_is_non_live(self):
        assert (
            OrgComponentAnalyzer._is_non_live_contention_lock_info(
                holder_pid=-1, started_at=None, host_identity=None, owner_identity=None
            )
            is True
        )

    def test_epoch_started_at_without_owner_is_non_live(self):
        assert (
            OrgComponentAnalyzer._is_non_live_contention_lock_info(
                holder_pid=None, started_at="1970-01-01T00:00:00+00:00", host_identity=None, owner_identity=None
            )
            is True
        )

    def test_normal_metadata_is_live(self):
        assert (
            OrgComponentAnalyzer._is_non_live_contention_lock_info(
                holder_pid=12345, started_at="2024-06-15T10:00:00", host_identity="prod-host", owner_identity=None
            )
            is False
        )

    def test_none_pid_normal_started_at_is_live(self):
        assert (
            OrgComponentAnalyzer._is_non_live_contention_lock_info(
                holder_pid=None, started_at="2024-06-15T10:00:00", host_identity=None, owner_identity=None
            )
            is False
        )


class TestSelectContentionHolderIdentity:
    """Tests for holder identity preference ordering."""

    def test_legacy_metadata_prefers_owner(self):
        """Legacy lock metadata should use owner, not host (host may be synthesized)."""
        result = OrgComponentAnalyzer._select_contention_holder_identity(
            {"version": 0}, host_identity="synthesized-host", owner_identity="real-owner"
        )
        assert result == "real-owner"

    def test_legacy_metadata_returns_none_when_no_owner(self):
        result = OrgComponentAnalyzer._select_contention_holder_identity(
            {"version": 0}, host_identity="synthesized-host", owner_identity=None
        )
        assert result is None

    def test_non_legacy_prefers_host(self):
        result = OrgComponentAnalyzer._select_contention_holder_identity(
            {"version": 1}, host_identity="real-host", owner_identity="owner"
        )
        assert result == "real-host"

    def test_non_legacy_falls_back_to_owner(self):
        result = OrgComponentAnalyzer._select_contention_holder_identity(
            {"version": 1}, host_identity=None, owner_identity="owner"
        )
        assert result == "owner"

    def test_non_legacy_no_identity_returns_none(self):
        result = OrgComponentAnalyzer._select_contention_holder_identity(
            {"version": 1}, host_identity=None, owner_identity=None
        )
        assert result is None


class TestExtractContentionLockInfo:
    """Tests for full lock metadata extraction with normalization."""

    def test_non_mapping_returns_all_none(self):
        assert OrgComponentAnalyzer._extract_contention_lock_info("not a dict") == (None, None, None, None)

    def test_none_returns_all_none(self):
        assert OrgComponentAnalyzer._extract_contention_lock_info(None) == (None, None, None, None)

    def test_empty_dict_returns_all_none(self):
        assert OrgComponentAnalyzer._extract_contention_lock_info({}) == (None, None, None, None)

    def test_full_non_legacy_metadata(self):
        pid, started, identity, backend = OrgComponentAnalyzer._extract_contention_lock_info(
            {
                "pid": 12345,
                "started_at": "2024-06-15T10:00:00",
                "host": "prod-host",
                "owner": "user@host",
                "backend": "lease",
                "version": 1,
            }
        )
        assert pid == 12345
        assert started == "2024-06-15T10:00:00"
        assert identity == "prod-host"  # non-legacy prefers host
        assert backend == "lease"

    def test_legacy_metadata_uses_owner_identity(self):
        pid, started, identity, backend = OrgComponentAnalyzer._extract_contention_lock_info(
            {
                "pid": 12345,
                "started_at": "2024-01-15T10:00:00",
                "host": "synthesized",
                "owner": "real-owner",
                "backend": "legacy",
                "version": 0,
            }
        )
        assert pid == 12345
        assert started == "2024-01-15T10:00:00"
        assert identity == "real-owner"  # legacy prefers owner
        assert backend == "legacy"

    def test_non_live_sentinel_clears_all_fields(self):
        pid, started, identity, backend = OrgComponentAnalyzer._extract_contention_lock_info(
            {
                "pid": -1,
                "started_at": "1970-01-01T00:00:00+00:00",
                "host": "released",
                "backend": "lease",
                "version": 1,
            }
        )
        assert pid is None
        assert started is None
        assert identity is None
        assert backend == "lease"  # backend is preserved

    def test_missing_optional_fields(self):
        pid, started, identity, backend = OrgComponentAnalyzer._extract_contention_lock_info(
            {
                "pid": 100,
                "version": 1,
            }
        )
        assert pid == 100
        assert started is None
        assert identity is None
        assert backend is None

    def test_nested_dict_pid_returns_none_pid(self):
        """Malformed pid (dict instead of int/str) should be safely ignored."""
        pid, _started, _identity, _backend = OrgComponentAnalyzer._extract_contention_lock_info(
            {
                "pid": {"nested": True},
                "version": 1,
            }
        )
        assert pid is None

    def test_list_value_returns_all_none(self):
        """A list is not a Mapping and should return all-None tuple."""
        assert OrgComponentAnalyzer._extract_contention_lock_info([1, 2, 3]) == (None, None, None, None)
