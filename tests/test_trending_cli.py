"""Tests for --trending-window CLI flag integration."""

from cja_auto_sdr.cli.parser import parse_arguments


class TestTrendingWindowArgParsing:
    def _parse(self, *args):
        """Parse arguments using the real parser."""
        parser = parse_arguments(return_parser=True, enable_autocomplete=False)
        return parser.parse_args(list(args))

    def test_trending_window_not_set_by_default(self):
        ns = self._parse("--org-report")
        assert ns.trending_window is None

    def test_trending_window_with_value(self):
        ns = self._parse("--org-report", "--trending-window", "5")
        assert ns.trending_window == 5

    def test_trending_window_without_value_uses_default(self):
        ns = self._parse("--org-report", "--trending-window")
        assert ns.trending_window == 10

    def test_trending_window_large_value(self):
        ns = self._parse("--org-report", "--trending-window", "50")
        assert ns.trending_window == 50

    def test_trending_window_coexists_with_compare_org_report(self):
        ns = self._parse("--org-report", "--trending-window", "5", "--compare-org-report", "prev.json")
        assert ns.trending_window == 5
        assert ns.org_compare_report == "prev.json"

    def test_trending_window_without_org_report_parses(self):
        """The flag parses even without --org-report; validation is at runtime."""
        ns = self._parse("--trending-window", "5")
        assert ns.trending_window == 5
