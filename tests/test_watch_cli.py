import pytest

from cja_auto_sdr.cli.parser import parse_arguments


def test_watch_accepts_single_data_view():
    args = parse_arguments(["--watch", "dv_abc", "--interval", "1h"])
    assert args.watch_data_views == ["dv_abc"]
    assert args.watch_interval == "1h"
    assert args.watch_threshold == 1  # default


def test_watch_accepts_multiple_data_views():
    args = parse_arguments(["--watch", "dv_abc", "dv_def", "dv_ghi", "--interval", "6h"])
    assert args.watch_data_views == ["dv_abc", "dv_def", "dv_ghi"]


def test_watch_threshold_accepts_zero_for_heartbeat():
    args = parse_arguments(["--watch", "dv_abc", "--interval", "1d", "--watch-threshold", "0"])
    assert args.watch_threshold == 0


def test_watch_threshold_accepts_positive():
    args = parse_arguments(["--watch", "dv_abc", "--interval", "1d", "--watch-threshold", "5"])
    assert args.watch_threshold == 5


@pytest.mark.parametrize("interval", ["1h", "6h", "24h", "1d", "7d", "1w"])
def test_interval_accepts_hour_day_week(interval):
    args = parse_arguments(["--watch", "dv_abc", "--interval", interval])
    assert args.watch_interval == interval


def test_watch_args_default_to_none_when_absent():
    # Sanity check: existing modes must not see spurious watch_data_views=None drift.
    args = parse_arguments(["dv_abc"])
    assert args.watch_data_views is None
    assert args.watch_interval is None
    assert args.watch_threshold == 1
