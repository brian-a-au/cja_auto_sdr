"""End-to-end dispatch tests for --watch routing in _main_impl.

These tests intentionally exercise the dispatch wiring without running the
actual watch loop, by patching run_watch and asserting the call shape.
"""

import sys
from unittest.mock import MagicMock, patch


@patch("cja_auto_sdr.cli.commands.watch.run_watch")
@patch("cja_auto_sdr.cli.commands.watch._resolve_cja_client", return_value=MagicMock())
def test_main_dispatches_to_run_watch_when_watch_arg_set(_mock_resolve, mock_run_watch):
    """--watch routes through _main_impl into run_watch."""
    from cja_auto_sdr import generator

    mock_run_watch.return_value = 0

    with patch.object(sys, "argv", ["cja_auto_sdr", "--watch", "dv_abc", "--interval", "1h"]):
        try:
            generator.main()
        except SystemExit as exc:
            assert exc.code == 0

    assert mock_run_watch.called
    args = mock_run_watch.call_args.args[0]
    assert args.watch_data_views == ["dv_abc"]
    assert args.watch_interval == "1h"


@patch("cja_auto_sdr.cli.commands.watch.run_watch")
def test_main_does_not_call_run_watch_when_watch_arg_absent(mock_run_watch):
    """Non-watch invocation does not touch run_watch.

    Uses --config-status rather than --version because --version is fast-path
    and exits in __main__.py before _main_impl runs — we need an invocation
    that actually reaches _main_impl so the absence of run_watch is meaningful.
    --config-status dumps the resolved config and exits cleanly without
    contacting the API, so it works in the test environment without creds.
    """
    from cja_auto_sdr import generator

    with patch.object(sys, "argv", ["cja_auto_sdr", "--config-status"]):
        try:
            generator.main()
        except SystemExit:
            pass

    assert not mock_run_watch.called
