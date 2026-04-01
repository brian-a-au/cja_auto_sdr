"""Tests for the centralised agent-output contract resolver.

These tests validate the single authoritative runtime interpretation of the
agent-facing output contract introduced by v3.5.1.  They cover:

* Capability table completeness and immutability
* ``resolve_agent_output_path`` for each command family
* ``resolve_agent_quiet`` recomputation from resolved output state
* ``is_stdout_path`` alias handling
"""

from __future__ import annotations

import argparse
from unittest.mock import patch

from cja_auto_sdr.cli.agent_output import (
    DIFF_STDOUT_FORMATS,
    DISCOVERY_STDOUT_FORMATS,
    ORG_REPORT_STDOUT_FORMATS,
    is_stdout_path,
    resolve_agent_output_path,
    resolve_agent_quiet,
)

# ---------------------------------------------------------------------------
# Capability table tests
# ---------------------------------------------------------------------------


class TestCapabilityTables:
    """Verify command-family stdout capability definitions."""

    def test_diff_stdout_formats_contains_json(self):
        assert "json" in DIFF_STDOUT_FORMATS

    def test_diff_stdout_formats_excludes_file_only(self):
        for fmt in ("csv", "html", "markdown", "excel", "console"):
            assert fmt not in DIFF_STDOUT_FORMATS

    def test_org_report_stdout_formats_contains_json_and_console(self):
        assert "json" in ORG_REPORT_STDOUT_FORMATS
        assert "console" in ORG_REPORT_STDOUT_FORMATS

    def test_org_report_stdout_formats_excludes_file_only(self):
        for fmt in ("csv", "html", "markdown", "excel"):
            assert fmt not in ORG_REPORT_STDOUT_FORMATS

    def test_discovery_stdout_formats_covers_all_known_formats(self):
        for fmt in ("json", "csv", "table", "console"):
            assert fmt in DISCOVERY_STDOUT_FORMATS

    def test_tables_are_frozensets(self):
        assert isinstance(DIFF_STDOUT_FORMATS, frozenset)
        assert isinstance(ORG_REPORT_STDOUT_FORMATS, frozenset)
        assert isinstance(DISCOVERY_STDOUT_FORMATS, frozenset)


# ---------------------------------------------------------------------------
# is_stdout_path tests
# ---------------------------------------------------------------------------


class TestIsStdoutPath:
    """Verify stdout alias recognition."""

    def test_dash_is_stdout(self):
        assert is_stdout_path("-") is True

    def test_stdout_literal_is_stdout(self):
        assert is_stdout_path("stdout") is True

    def test_none_is_not_stdout(self):
        assert is_stdout_path(None) is False

    def test_file_path_is_not_stdout(self):
        assert is_stdout_path("/tmp/report.json") is False

    def test_empty_string_is_not_stdout(self):
        assert is_stdout_path("") is False


# ---------------------------------------------------------------------------
# resolve_agent_output_path tests
# ---------------------------------------------------------------------------


def _make_args(
    *,
    agent_mode: bool = False,
    output: str | None = None,
    format_: str = "json",
) -> argparse.Namespace:
    """Build a minimal Namespace for testing."""
    return argparse.Namespace(
        agent_mode=agent_mode,
        output=output,
        format=format_,
    )


class TestResolveAgentOutputPath:
    """Verify output-path resolution for all command families."""

    # -- Non-agent-mode passthrough --

    def test_non_agent_mode_returns_output_unchanged(self):
        args = _make_args(output="/tmp/report.json")
        result = resolve_agent_output_path(args, output_format="json", stdout_formats=DIFF_STDOUT_FORMATS)
        assert result == "/tmp/report.json"

    def test_non_agent_mode_returns_none_when_no_output(self):
        args = _make_args()
        result = resolve_agent_output_path(args, output_format="json", stdout_formats=DIFF_STDOUT_FORMATS)
        assert result is None

    # -- Agent-mode with explicit --output --

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_explicit_output_wins_over_agent_mode(self, mock_fn):
        mock_fn.return_value = lambda opt, **kw: opt == "--output"
        args = _make_args(agent_mode=True, output="/custom/path.csv")
        result = resolve_agent_output_path(args, output_format="csv", stdout_formats=DIFF_STDOUT_FORMATS)
        assert result == "/custom/path.csv"

    # -- Agent-mode stdout-capable format --

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_agent_mode_json_diff_keeps_stdout(self, mock_fn):
        mock_fn.return_value = lambda opt, **kw: False
        args = _make_args(agent_mode=True, output="-")
        result = resolve_agent_output_path(args, output_format="json", stdout_formats=DIFF_STDOUT_FORMATS)
        assert result == "-"

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_agent_mode_json_org_report_keeps_stdout(self, mock_fn):
        mock_fn.return_value = lambda opt, **kw: False
        args = _make_args(agent_mode=True, output="-")
        result = resolve_agent_output_path(args, output_format="json", stdout_formats=ORG_REPORT_STDOUT_FORMATS)
        assert result == "-"

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_agent_mode_console_org_report_keeps_stdout(self, mock_fn):
        mock_fn.return_value = lambda opt, **kw: False
        args = _make_args(agent_mode=True, output="-")
        result = resolve_agent_output_path(args, output_format="console", stdout_formats=ORG_REPORT_STDOUT_FORMATS)
        assert result == "-"

    # -- Agent-mode file-only format suppression --

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_agent_mode_markdown_diff_suppresses_stdout(self, mock_fn):
        mock_fn.return_value = lambda opt, **kw: False
        args = _make_args(agent_mode=True, output="-")
        result = resolve_agent_output_path(args, output_format="markdown", stdout_formats=DIFF_STDOUT_FORMATS)
        assert result is None

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_agent_mode_excel_diff_suppresses_stdout(self, mock_fn):
        mock_fn.return_value = lambda opt, **kw: False
        args = _make_args(agent_mode=True, output="-")
        result = resolve_agent_output_path(args, output_format="excel", stdout_formats=DIFF_STDOUT_FORMATS)
        assert result is None

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_agent_mode_html_org_report_suppresses_stdout(self, mock_fn):
        mock_fn.return_value = lambda opt, **kw: False
        args = _make_args(agent_mode=True, output="-")
        result = resolve_agent_output_path(args, output_format="html", stdout_formats=ORG_REPORT_STDOUT_FORMATS)
        assert result is None

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_agent_mode_csv_org_report_suppresses_stdout(self, mock_fn):
        mock_fn.return_value = lambda opt, **kw: False
        args = _make_args(agent_mode=True, output="-")
        result = resolve_agent_output_path(args, output_format="csv", stdout_formats=ORG_REPORT_STDOUT_FORMATS)
        assert result is None

    # -- Discovery (all formats allowed) --

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_agent_mode_discovery_csv_keeps_stdout(self, mock_fn):
        mock_fn.return_value = lambda opt, **kw: False
        args = _make_args(agent_mode=True, output="-")
        result = resolve_agent_output_path(args, output_format="csv", stdout_formats=DISCOVERY_STDOUT_FORMATS)
        assert result == "-"

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_agent_mode_discovery_table_keeps_stdout(self, mock_fn):
        mock_fn.return_value = lambda opt, **kw: False
        args = _make_args(agent_mode=True, output="-")
        result = resolve_agent_output_path(args, output_format="table", stdout_formats=DISCOVERY_STDOUT_FORMATS)
        assert result == "-"

    # -- stdout alias --

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_agent_mode_stdout_alias_treated_like_dash(self, mock_fn):
        mock_fn.return_value = lambda opt, **kw: False
        args = _make_args(agent_mode=True, output="stdout")
        result = resolve_agent_output_path(args, output_format="json", stdout_formats=DIFF_STDOUT_FORMATS)
        assert result == "stdout"


# ---------------------------------------------------------------------------
# resolve_agent_quiet tests
# ---------------------------------------------------------------------------


class TestResolveAgentQuiet:
    """Verify quiet recomputation from resolved output state."""

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_explicit_quiet_always_wins(self, mock_fn):
        mock_fn.return_value = lambda opt, **kw: opt == "--quiet"
        args = argparse.Namespace(run_summary_json=None)
        assert resolve_agent_quiet(args, output_path=None) is True

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_run_summary_json_stdout_implies_quiet(self, mock_fn):
        mock_fn.return_value = lambda opt, **kw: False
        args = argparse.Namespace(run_summary_json="-")
        assert resolve_agent_quiet(args, output_path=None) is True

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_run_summary_json_stdout_alias_implies_quiet(self, mock_fn):
        mock_fn.return_value = lambda opt, **kw: False
        args = argparse.Namespace(run_summary_json="stdout")
        assert resolve_agent_quiet(args, output_path=None) is True

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_output_path_stdout_implies_quiet(self, mock_fn):
        mock_fn.return_value = lambda opt, **kw: False
        args = argparse.Namespace(run_summary_json=None)
        assert resolve_agent_quiet(args, output_path="-") is True

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_output_path_stdout_alias_implies_quiet(self, mock_fn):
        mock_fn.return_value = lambda opt, **kw: False
        args = argparse.Namespace(run_summary_json=None)
        assert resolve_agent_quiet(args, output_path="stdout") is True

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_no_stdout_means_not_quiet(self, mock_fn):
        mock_fn.return_value = lambda opt, **kw: False
        args = argparse.Namespace(run_summary_json=None)
        assert resolve_agent_quiet(args, output_path=None) is False

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_file_output_means_not_quiet(self, mock_fn):
        mock_fn.return_value = lambda opt, **kw: False
        args = argparse.Namespace(run_summary_json=None)
        assert resolve_agent_quiet(args, output_path="/tmp/report.json") is False

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_suppressed_stdout_recomputes_quiet_to_false(self, mock_fn):
        """The key regression scenario: agent-mode set stdout, but output was
        suppressed for a file-only format — quiet must follow the suppressed
        (None) path, not the original preset."""
        mock_fn.return_value = lambda opt, **kw: False
        args = argparse.Namespace(run_summary_json=None)
        assert resolve_agent_quiet(args, output_path=None) is False

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_explicit_quiet_wins_even_when_stdout_suppressed(self, mock_fn):
        """Explicit --quiet must survive output-path suppression."""
        mock_fn.return_value = lambda opt, **kw: opt == "--quiet"
        args = argparse.Namespace(run_summary_json=None)
        assert resolve_agent_quiet(args, output_path=None) is True


# ---------------------------------------------------------------------------
# Integration: resolve_agent_output_path + resolve_agent_quiet together
# ---------------------------------------------------------------------------


class TestResolverPipeline:
    """End-to-end tests exercising both resolvers in sequence."""

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_agent_mode_json_diff_produces_stdout_and_quiet(self, mock_fn):
        mock_fn.return_value = lambda opt, **kw: False
        args = _make_args(agent_mode=True, output="-")
        args.run_summary_json = None
        output_path = resolve_agent_output_path(args, output_format="json", stdout_formats=DIFF_STDOUT_FORMATS)
        quiet = resolve_agent_quiet(args, output_path=output_path)
        assert output_path == "-"
        assert quiet is True

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_agent_mode_markdown_diff_suppresses_and_unquiets(self, mock_fn):
        mock_fn.return_value = lambda opt, **kw: False
        args = _make_args(agent_mode=True, output="-")
        args.run_summary_json = None
        output_path = resolve_agent_output_path(args, output_format="markdown", stdout_formats=DIFF_STDOUT_FORMATS)
        quiet = resolve_agent_quiet(args, output_path=output_path)
        assert output_path is None
        assert quiet is False

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_agent_mode_console_org_report_produces_stdout_and_quiet(self, mock_fn):
        mock_fn.return_value = lambda opt, **kw: False
        args = _make_args(agent_mode=True, output="-")
        args.run_summary_json = None
        output_path = resolve_agent_output_path(args, output_format="console", stdout_formats=ORG_REPORT_STDOUT_FORMATS)
        quiet = resolve_agent_quiet(args, output_path=output_path)
        assert output_path == "-"
        assert quiet is True

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_agent_mode_excel_org_report_suppresses_and_unquiets(self, mock_fn):
        mock_fn.return_value = lambda opt, **kw: False
        args = _make_args(agent_mode=True, output="-")
        args.run_summary_json = None
        output_path = resolve_agent_output_path(
            args, output_format="excel", stdout_formats=ORG_REPORT_STDOUT_FORMATS
        )
        quiet = resolve_agent_quiet(args, output_path=output_path)
        assert output_path is None
        assert quiet is False

    @patch("cja_auto_sdr.cli.agent_output._cli_option_specified_fn")
    def test_run_summary_json_stdout_forces_quiet_even_when_output_suppressed(self, mock_fn):
        mock_fn.return_value = lambda opt, **kw: False
        args = _make_args(agent_mode=True, output="-")
        args.run_summary_json = "-"
        output_path = resolve_agent_output_path(
            args, output_format="excel", stdout_formats=ORG_REPORT_STDOUT_FORMATS
        )
        quiet = resolve_agent_quiet(args, output_path=output_path)
        assert output_path is None
        assert quiet is True  # run_summary_json still targeting stdout
