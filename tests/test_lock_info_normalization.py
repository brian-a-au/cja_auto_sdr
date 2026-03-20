"""Direct unit tests for OrgComponentAnalyzer lock-info normalization classmethods."""

from cja_auto_sdr.generator import OrgComponentAnalyzer


class TestNormalizeLockInfoInt:
    """Tests for _normalize_lock_info_int shared helper."""

    def test_int_passthrough(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int(42, "pid") == 42

    def test_zero_passthrough(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int(0, "version") == 0

    def test_negative_int_passthrough(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int(-1, "pid") == -1

    def test_string_parsed_to_int(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int("123", "pid") == 123

    def test_string_with_whitespace_parsed(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int("  42  ", "pid") == 42

    def test_bool_true_rejected(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int(True, "pid") is None

    def test_bool_false_rejected(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int(False, "version") is None

    def test_non_numeric_string_returns_none(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int("abc", "pid") is None

    def test_empty_string_returns_none(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int("", "pid") is None

    def test_whitespace_only_string_returns_none(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int("   ", "version") is None

    def test_none_returns_none(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int(None, "pid") is None

    def test_float_returns_none(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int(3.14, "pid") is None

    def test_list_returns_none(self):
        assert OrgComponentAnalyzer._normalize_lock_info_int([1], "pid") is None


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
