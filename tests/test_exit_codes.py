from __future__ import annotations

import pytest

from cja_auto_sdr.core.exit_codes import combine_wrapper_exit_codes, is_signal_exit_code, normalize_subprocess_exit_code


@pytest.mark.parametrize(
    ("current", "new_code", "expected"),
    [
        (0, 0, 0),
        (0, 3, 3),
        (3, 2, 2),
        (2, 1, 1),
        (99, 0, 1),
        (0, 99, 1),
        (-2, 0, 130),
        (0, -15, 143),
        (130, 0, 130),
    ],
)
def test_combine_wrapper_exit_codes_preserves_priority_and_fails_closed(current, new_code, expected):
    assert combine_wrapper_exit_codes(current, new_code) == expected


def test_is_signal_exit_code_excludes_signal_base_marker():
    assert is_signal_exit_code(128) is False
    assert is_signal_exit_code(129) is True


def test_normalize_subprocess_exit_code_converts_negative_signals():
    assert normalize_subprocess_exit_code(-2) == 130
    assert normalize_subprocess_exit_code(2) == 2
