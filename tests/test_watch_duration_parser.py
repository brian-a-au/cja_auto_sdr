import pytest

from cja_auto_sdr.diff.snapshot import parse_duration_seconds


@pytest.mark.parametrize(
    ("period_str", "expected"),
    [
        ("1h", 3600),
        ("6h", 21_600),
        ("24h", 86_400),
        ("1d", 86_400),
        ("7d", 604_800),
        ("1w", 604_800),
        ("2w", 1_209_600),
    ],
)
def test_parse_duration_seconds_valid(period_str, expected):
    assert parse_duration_seconds(period_str) == expected


@pytest.mark.parametrize(
    "period_str",
    ["", "0h", "0d", "0w", "1", "h", "1.5h", "-1h", "1m", "1y", "abc", " 1h", "1h "],
)
def test_parse_duration_seconds_invalid(period_str):
    assert parse_duration_seconds(period_str) is None


@pytest.mark.parametrize("period_str", ["²h", "①h", "١h"])  # noqa: RUF001 — deliberate ambiguous chars
def test_parse_duration_seconds_rejects_non_ascii_digits(period_str):
    # str.isdigit() admits superscripts and circled digits but int() rejects them.
    # str.isdecimal() admits Arabic-Indic digits int() accepts but the parser should
    # accept only ASCII 0-9 to keep the contract narrow and never raise.
    assert parse_duration_seconds(period_str) is None


def test_parse_retention_period_unchanged_by_new_parser():
    # Regression: parse_retention_period must still accept Nd/Nw only and reject Nh.
    from cja_auto_sdr.diff.snapshot import parse_retention_period

    assert parse_retention_period("30d") == 30
    assert parse_retention_period("12w") == 84
    assert parse_retention_period("1h") is None
