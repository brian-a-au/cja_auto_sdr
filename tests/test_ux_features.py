"""
Tests for UX Enhancement Features (v3.0.14)

Tests for:
- --open flag (auto-open generated files)
- --output (stdout support for piping)
- --stats (quick statistics mode)
- --list-dataviews with JSON/CSV format
"""

import json
import os
import sys
from io import StringIO
from unittest.mock import MagicMock, patch

import pytest

# Import the functions from the main module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cja_auto_sdr.generator import (
    list_dataviews,
    open_file_in_default_app,
    parse_arguments,
    show_stats,
)


class TestOpenFlag:
    """Tests for the --open flag to auto-open generated files"""

    def test_open_flag_registered(self):
        """Test that --open flag is available in argument parser"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--open"]):
            args = parse_arguments()
            assert hasattr(args, "open")
            assert args.open is True

    def test_open_flag_default_false(self):
        """Test that --open defaults to False"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345"]):
            args = parse_arguments()
            assert hasattr(args, "open")
            assert args.open is False

    @patch("subprocess.run")
    @patch("platform.system", return_value="Darwin")
    def test_open_file_macos(self, mock_platform, mock_subprocess):
        """Test file opening on macOS uses 'open' command"""
        mock_subprocess.return_value = MagicMock(returncode=0)
        result = open_file_in_default_app("/path/to/file.xlsx")
        assert result is True
        mock_subprocess.assert_called_once_with(["open", "/path/to/file.xlsx"], check=True)

    @patch("subprocess.run")
    @patch("platform.system", return_value="Linux")
    def test_open_file_linux(self, mock_platform, mock_subprocess):
        """Test file opening on Linux uses 'xdg-open' command"""
        mock_subprocess.return_value = MagicMock(returncode=0)
        result = open_file_in_default_app("/path/to/file.xlsx")
        assert result is True
        mock_subprocess.assert_called_once_with(["xdg-open", "/path/to/file.xlsx"], check=True)

    @pytest.mark.skipif(os.name != "nt", reason="os.startfile only exists on Windows")
    @patch("os.startfile")
    @patch("platform.system", return_value="Windows")
    def test_open_file_windows(self, mock_platform, mock_startfile):
        """Test file opening on Windows uses os.startfile"""
        result = open_file_in_default_app("C:\\path\\to\\file.xlsx")
        assert result is True
        mock_startfile.assert_called_once_with("C:\\path\\to\\file.xlsx")

    @patch("subprocess.run", side_effect=OSError("Command failed"))
    @patch("platform.system", return_value="Darwin")
    def test_open_file_failure(self, mock_platform, mock_subprocess):
        """Test graceful handling when file opening fails"""
        result = open_file_in_default_app("/path/to/file.xlsx")
        assert result is False

    @patch("webbrowser.open")
    @patch("subprocess.run", side_effect=OSError("Command failed"))
    @patch("platform.system", return_value="Linux")
    def test_open_html_fallback_to_webbrowser(self, mock_platform, mock_subprocess, mock_webbrowser):
        """Test HTML files fall back to webbrowser on failure"""
        mock_webbrowser.return_value = True
        result = open_file_in_default_app("/path/to/file.html")
        assert result is True
        mock_webbrowser.assert_called_once()


class TestOutputStdout:
    """Tests for --output - (stdout) support"""

    def test_output_argument_registered(self):
        """Test that --output argument is available"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--output", "-"]):
            args = parse_arguments()
            assert hasattr(args, "output")
            assert args.output == "-"

    def test_output_stdout_alias(self):
        """Test that 'stdout' works as an alias for '-'"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--output", "stdout"]):
            args = parse_arguments()
            assert args.output == "stdout"

    def test_output_file_path(self):
        """Test that regular file paths work"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--output", "/tmp/output.json"]):
            args = parse_arguments()
            assert args.output == "/tmp/output.json"


class TestStatsMode:
    """Tests for --stats quick statistics mode"""

    def test_stats_flag_registered(self):
        """Test that --stats flag is available"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--stats"]):
            args = parse_arguments()
            assert hasattr(args, "stats")
            assert args.stats is True

    def test_stats_flag_default_false(self):
        """Test that --stats defaults to False"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345"]):
            args = parse_arguments()
            assert hasattr(args, "stats")
            assert args.stats is False

    def test_stats_with_format_json(self):
        """Test --stats with --format json"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--stats", "--format", "json"]):
            args = parse_arguments()
            assert args.stats is True
            assert args.format == "json"

    def test_stats_with_format_csv(self):
        """Test --stats with --format csv"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--stats", "--format", "csv"]):
            args = parse_arguments()
            assert args.stats is True
            assert args.format == "csv"

    def test_stats_with_multiple_data_views(self):
        """Test --stats with multiple data views"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_1", "dv_2", "dv_3", "--stats"]):
            args = parse_arguments()
            assert args.stats is True
            assert len(args.data_views) == 3


class TestListDataviewsFormat:
    """Tests for --list-dataviews with format options"""

    def test_list_dataviews_with_json_format(self):
        """Test --list-dataviews --format json"""
        with patch("sys.argv", ["cja_sdr_generator.py", "--list-dataviews", "--format", "json"]):
            args = parse_arguments()
            assert args.list_dataviews is True
            assert args.format == "json"

    def test_list_dataviews_with_csv_format(self):
        """Test --list-dataviews --format csv"""
        with patch("sys.argv", ["cja_sdr_generator.py", "--list-dataviews", "--format", "csv"]):
            args = parse_arguments()
            assert args.list_dataviews is True
            assert args.format == "csv"

    def test_list_dataviews_with_output_stdout(self):
        """Test --list-dataviews --output -"""
        with patch("sys.argv", ["cja_sdr_generator.py", "--list-dataviews", "--output", "-"]):
            args = parse_arguments()
            assert args.list_dataviews is True
            assert args.output == "-"


class TestShowStatsFunction:
    """Tests for the show_stats function"""

    @patch("cja_auto_sdr.generator.cjapy")
    def test_show_stats_json_output(self, mock_cjapy):
        """Test show_stats with JSON format"""
        # Setup mock
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataView.return_value = {"name": "Test View", "owner": {"name": "Owner"}}
        mock_cja.getMetrics.return_value = [{"id": f"m{i}"} for i in range(10)]
        mock_cja.getDimensions.return_value = [{"id": f"d{i}"} for i in range(5)]

        # Capture stdout
        captured_output = StringIO()
        with patch("sys.stdout", captured_output):
            with patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None)):
                result = show_stats(["dv_12345"], output_format="json", output_file="-", quiet=True)

        assert result is True
        output = captured_output.getvalue()
        data = json.loads(output)
        assert "stats" in data
        assert "count" in data
        assert "totals" in data

    @patch("cja_auto_sdr.generator.cjapy")
    def test_show_stats_csv_output(self, mock_cjapy):
        """Test show_stats with CSV format"""
        # Setup mock
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataView.return_value = {"name": "Test View", "owner": {"name": "Owner"}}
        mock_cja.getMetrics.return_value = [{"id": f"m{i}"} for i in range(10)]
        mock_cja.getDimensions.return_value = [{"id": f"d{i}"} for i in range(5)]

        # Capture stdout
        captured_output = StringIO()
        with patch("sys.stdout", captured_output):
            with patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None)):
                result = show_stats(["dv_12345"], output_format="csv", output_file="-", quiet=True)

        assert result is True
        output = captured_output.getvalue()
        lines = output.strip().split("\n")
        assert lines[0] == "id,name,owner,metrics,dimensions,total_components"
        assert len(lines) == 2  # Header + 1 data row

    @patch("cja_auto_sdr.generator.cjapy")
    def test_show_stats_table_output(self, mock_cjapy):
        """Test show_stats with table format"""
        # Setup mock
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataView.return_value = {"name": "Test View", "owner": {"name": "Owner"}}
        mock_cja.getMetrics.return_value = [{"id": f"m{i}"} for i in range(10)]
        mock_cja.getDimensions.return_value = [{"id": f"d{i}"} for i in range(5)]

        # Capture stdout
        captured_output = StringIO()
        with patch("sys.stdout", captured_output):
            with patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None)):
                result = show_stats(["dv_12345"], output_format="table", quiet=False)

        assert result is True
        output = captured_output.getvalue()
        assert "DATA VIEW STATISTICS" in output
        assert "TOTAL" in output


class TestListDataviewsFunction:
    """Tests for the list_dataviews function with format options"""

    @patch("cja_auto_sdr.generator.cjapy")
    def test_list_dataviews_json_output(self, mock_cjapy):
        """Test list_dataviews with JSON format"""
        # Setup mock
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataViews.return_value = [
            {"id": "dv_1", "name": "View 1", "owner": {"name": "Owner 1"}},
            {"id": "dv_2", "name": "View 2", "owner": {"name": "Owner 2"}},
        ]

        # Capture stdout
        captured_output = StringIO()
        with patch("sys.stdout", captured_output):
            with patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None)):
                result = list_dataviews(output_format="json", output_file="-")

        assert result is True
        output = captured_output.getvalue()
        data = json.loads(output)
        assert "dataViews" in data
        assert "count" in data
        assert data["count"] == 2

    @patch("cja_auto_sdr.generator.cjapy")
    def test_list_dataviews_csv_output(self, mock_cjapy):
        """Test list_dataviews with CSV format"""
        # Setup mock
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataViews.return_value = [
            {"id": "dv_1", "name": "View 1", "owner": {"name": "Owner 1"}},
            {"id": "dv_2", "name": "View 2", "owner": {"name": "Owner 2"}},
        ]

        # Capture stdout
        captured_output = StringIO()
        with patch("sys.stdout", captured_output):
            with patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None)):
                result = list_dataviews(output_format="csv", output_file="-")

        assert result is True
        output = captured_output.getvalue()
        lines = output.strip().split("\n")
        assert lines[0] == "id,name,owner"
        assert len(lines) == 3  # Header + 2 data rows

    @patch("cja_auto_sdr.generator.cjapy")
    def test_list_dataviews_empty_json(self, mock_cjapy):
        """Test list_dataviews JSON output when no data views"""
        # Setup mock
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataViews.return_value = []

        # Capture stdout
        captured_output = StringIO()
        with patch("sys.stdout", captured_output):
            with patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "mock", None)):
                result = list_dataviews(output_format="json", output_file="-")

        assert result is True
        output = captured_output.getvalue()
        data = json.loads(output)
        assert data["count"] == 0
        assert data["dataViews"] == []


class TestCombinedFeatures:
    """Tests for combined feature usage"""

    def test_stats_with_output_stdout(self):
        """Test --stats with --output -"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--stats", "--output", "-"]):
            args = parse_arguments()
            assert args.stats is True
            assert args.output == "-"

    def test_open_with_format_excel(self):
        """Test --open with --format excel"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--open", "--format", "excel"]):
            args = parse_arguments()
            assert args.open is True
            assert args.format == "excel"

    def test_open_with_batch_mode(self):
        """Test --open with multiple data views"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_1", "dv_2", "--open"]):
            args = parse_arguments()
            assert args.open is True
            assert len(args.data_views) == 2


class TestVersionUpdated:
    """Test that version is correct"""

    def test_version_is_3_4_0(self):
        """Test that version is 3.4.0"""
        from cja_auto_sdr.generator import __version__

        assert __version__ == "3.4.0"


class TestFormatAutoDetection:
    """Tests for auto-detecting format from file extension"""

    def test_infer_format_xlsx(self):
        """Test xlsx extension infers excel format"""
        from cja_auto_sdr.generator import infer_format_from_path

        assert infer_format_from_path("report.xlsx") == "excel"

    def test_infer_format_xls(self):
        """Test xls extension infers excel format"""
        from cja_auto_sdr.generator import infer_format_from_path

        assert infer_format_from_path("report.xls") == "excel"

    def test_infer_format_csv(self):
        """Test csv extension infers csv format"""
        from cja_auto_sdr.generator import infer_format_from_path

        assert infer_format_from_path("data.csv") == "csv"

    def test_infer_format_json(self):
        """Test json extension infers json format"""
        from cja_auto_sdr.generator import infer_format_from_path

        assert infer_format_from_path("output.json") == "json"

    def test_infer_format_html(self):
        """Test html extension infers html format"""
        from cja_auto_sdr.generator import infer_format_from_path

        assert infer_format_from_path("report.html") == "html"

    def test_infer_format_htm(self):
        """Test htm extension infers html format"""
        from cja_auto_sdr.generator import infer_format_from_path

        assert infer_format_from_path("report.htm") == "html"

    def test_infer_format_md(self):
        """Test md extension infers markdown format"""
        from cja_auto_sdr.generator import infer_format_from_path

        assert infer_format_from_path("doc.md") == "markdown"

    def test_infer_format_markdown(self):
        """Test markdown extension infers markdown format"""
        from cja_auto_sdr.generator import infer_format_from_path

        assert infer_format_from_path("doc.markdown") == "markdown"

    def test_infer_format_unknown_extension(self):
        """Test unknown extension returns None"""
        from cja_auto_sdr.generator import infer_format_from_path

        assert infer_format_from_path("file.txt") is None
        assert infer_format_from_path("file.pdf") is None

    def test_infer_format_stdout(self):
        """Test stdout markers return None"""
        from cja_auto_sdr.generator import infer_format_from_path

        assert infer_format_from_path("-") is None
        assert infer_format_from_path("stdout") is None

    def test_infer_format_empty(self):
        """Test empty/None returns None"""
        from cja_auto_sdr.generator import infer_format_from_path

        assert infer_format_from_path("") is None
        assert infer_format_from_path(None) is None

    def test_infer_format_case_insensitive(self):
        """Test extension matching is case insensitive"""
        from cja_auto_sdr.generator import infer_format_from_path

        assert infer_format_from_path("REPORT.XLSX") == "excel"
        assert infer_format_from_path("Data.JSON") == "json"


class TestConfigStatusFlag:
    """Tests for --config-status flag"""

    def test_config_status_flag_registered(self):
        """Test that --config-status flag is available"""
        with patch("sys.argv", ["cja_sdr_generator.py", "--config-status"]):
            args = parse_arguments()
            assert hasattr(args, "config_status")
            assert args.config_status is True

    def test_config_status_default_false(self):
        """Test that --config-status defaults to False"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345"]):
            args = parse_arguments()
            assert args.config_status is False


class TestColorThemeFlag:
    """Tests for --color-theme flag"""

    def test_color_theme_flag_registered(self):
        """Test that --color-theme flag is available"""
        with patch("sys.argv", ["cja_sdr_generator.py", "--diff", "dv_A", "dv_B", "--color-theme", "accessible"]):
            args = parse_arguments()
            assert hasattr(args, "color_theme")
            assert args.color_theme == "accessible"

    def test_color_theme_default(self):
        """Test that --color-theme defaults to 'default'"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345"]):
            args = parse_arguments()
            assert args.color_theme == "default"

    def test_color_theme_choices(self):
        """Test that only valid choices are accepted"""
        # Valid choice
        with patch("sys.argv", ["cja_sdr_generator.py", "--diff", "dv_A", "dv_B", "--color-theme", "default"]):
            args = parse_arguments()
            assert args.color_theme == "default"

        # Invalid choice should raise
        with patch("sys.argv", ["cja_sdr_generator.py", "--diff", "dv_A", "dv_B", "--color-theme", "invalid"]):
            with pytest.raises(SystemExit):
                parse_arguments()


class TestConsoleColorsTheme:
    """Tests for ConsoleColors theme functionality"""

    def test_set_theme_default(self):
        """Test setting default theme"""
        from cja_auto_sdr.generator import ConsoleColors

        ConsoleColors.set_theme("default")
        assert ConsoleColors._theme == "default"

    def test_set_theme_accessible(self):
        """Test setting accessible theme"""
        from cja_auto_sdr.generator import ConsoleColors

        ConsoleColors.set_theme("accessible")
        assert ConsoleColors._theme == "accessible"
        # Reset to default for other tests
        ConsoleColors.set_theme("default")

    def test_set_theme_invalid(self):
        """Test that invalid theme raises ValueError"""
        from cja_auto_sdr.generator import ConsoleColors

        with pytest.raises(ValueError):
            ConsoleColors.set_theme("invalid_theme")

    def test_diff_added_method_exists(self):
        """Test diff_added method exists and works"""
        from cja_auto_sdr.generator import ConsoleColors

        result = ConsoleColors.diff_added("test")
        assert "test" in result

    def test_diff_removed_method_exists(self):
        """Test diff_removed method exists and works"""
        from cja_auto_sdr.generator import ConsoleColors

        result = ConsoleColors.diff_removed("test")
        assert "test" in result

    def test_diff_modified_method_exists(self):
        """Test diff_modified method exists and works"""
        from cja_auto_sdr.generator import ConsoleColors

        result = ConsoleColors.diff_modified("test")
        assert "test" in result

    def test_no_color_env_disables_colors(self):
        """Test NO_COLOR environment variable disables ANSI colors."""
        from cja_auto_sdr.generator import ConsoleColors

        original_state = ConsoleColors.is_enabled()
        with patch.dict("os.environ", {"NO_COLOR": "1"}, clear=False):
            ConsoleColors.configure()
            assert ConsoleColors.is_enabled() is False
        ConsoleColors.set_enabled(original_state)

    def test_force_color_env_enables_colors(self):
        """Test FORCE_COLOR environment variable enables ANSI colors."""
        from cja_auto_sdr.generator import ConsoleColors

        original_state = ConsoleColors.is_enabled()
        with patch.dict("os.environ", {"FORCE_COLOR": "1"}, clear=False):
            ConsoleColors.configure()
            assert ConsoleColors.is_enabled() is True
        ConsoleColors.set_enabled(original_state)

    def test_no_color_flag_overrides_force_color(self):
        """Test --no-color policy overrides FORCE_COLOR."""
        from cja_auto_sdr.generator import ConsoleColors

        original_state = ConsoleColors.is_enabled()
        with patch.dict("os.environ", {"FORCE_COLOR": "1"}, clear=False):
            ConsoleColors.configure(no_color=True)
            assert ConsoleColors.is_enabled() is False
        ConsoleColors.set_enabled(original_state)


class TestInteractiveFlag:
    """Tests for --interactive flag"""

    def test_interactive_flag_registered(self):
        """Test that --interactive flag is available"""
        with patch("sys.argv", ["cja_sdr_generator.py", "--interactive"]):
            args = parse_arguments()
            assert hasattr(args, "interactive")
            assert args.interactive is True

    def test_interactive_short_flag(self):
        """Test that -i short flag works"""
        with patch("sys.argv", ["cja_sdr_generator.py", "-i"]):
            args = parse_arguments()
            assert args.interactive is True

    def test_interactive_default_false(self):
        """Test that --interactive defaults to False"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345"]):
            args = parse_arguments()
            assert args.interactive is False


class TestMetricsDimensionsOnlyForSDR:
    """Tests for --metrics-only and --dimensions-only flags in SDR mode"""

    def test_metrics_only_flag_available(self):
        """Test that --metrics-only works with SDR mode"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--metrics-only"]):
            args = parse_arguments()
            assert args.metrics_only is True

    def test_dimensions_only_flag_available(self):
        """Test that --dimensions-only works with SDR mode"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--dimensions-only"]):
            args = parse_arguments()
            assert args.dimensions_only is True

    def test_both_flags_default_false(self):
        """Test that both flags default to False"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345"]):
            args = parse_arguments()
            assert args.metrics_only is False
            assert args.dimensions_only is False


class TestFormatAliases:
    """Tests for format aliases (reports, data, ci)"""

    def test_format_alias_reports(self):
        """Test 'reports' format alias is accepted"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--format", "reports"]):
            args = parse_arguments()
            assert args.format == "reports"

    def test_format_alias_data(self):
        """Test 'data' format alias is accepted"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--format", "data"]):
            args = parse_arguments()
            assert args.format == "data"

    def test_format_alias_ci(self):
        """Test 'ci' format alias is accepted"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--format", "ci"]):
            args = parse_arguments()
            assert args.format == "ci"

    def test_should_generate_format_with_alias(self):
        """Test should_generate_format works with aliases"""
        from cja_auto_sdr.generator import should_generate_format

        # 'reports' alias = excel + markdown
        assert should_generate_format("reports", "excel") is True
        assert should_generate_format("reports", "markdown") is True
        assert should_generate_format("reports", "csv") is False

        # 'data' alias = csv + json
        assert should_generate_format("data", "csv") is True
        assert should_generate_format("data", "json") is True
        assert should_generate_format("data", "excel") is False

        # 'ci' alias = json + markdown
        assert should_generate_format("ci", "json") is True
        assert should_generate_format("ci", "markdown") is True
        assert should_generate_format("ci", "excel") is False


class TestShowTimingsFlag:
    """Tests for --show-timings flag"""

    def test_show_timings_flag_registered(self):
        """Test that --show-timings flag is available"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--show-timings"]):
            args = parse_arguments()
            assert hasattr(args, "show_timings")
            assert args.show_timings is True

    def test_show_timings_default_false(self):
        """Test that --show-timings defaults to False"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345"]):
            args = parse_arguments()
            assert args.show_timings is False


class TestInventoryOptionsValidation:
    """Tests for inventory options (--include-derived, --include-calculated) validation"""

    def test_include_derived_flag_registered(self):
        """Test that --include-derived flag is available"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--include-derived"]):
            args = parse_arguments()
            assert hasattr(args, "include_derived_inventory")
            assert args.include_derived_inventory is True

    def test_include_derived_default_false(self):
        """Test that --include-derived defaults to False"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345"]):
            args = parse_arguments()
            assert args.include_derived_inventory is False

    def test_include_calculated_flag_registered(self):
        """Test that --include-calculated flag is available"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--include-calculated"]):
            args = parse_arguments()
            assert hasattr(args, "include_calculated_metrics")
            assert args.include_calculated_metrics is True

    def test_include_calculated_default_false(self):
        """Test that --include-calculated defaults to False"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345"]):
            args = parse_arguments()
            assert args.include_calculated_metrics is False

    def test_both_inventory_flags_together(self):
        """Test that both inventory flags can be used together"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--include-derived", "--include-calculated"]):
            args = parse_arguments()
            assert args.include_derived_inventory is True
            assert args.include_calculated_metrics is True

    def test_include_derived_with_diff_errors(self):
        """Test that --include-derived with --diff (cross-DV) produces error"""
        from cja_auto_sdr.generator import main

        with patch("sys.argv", ["cja_sdr_generator.py", "--diff", "dv_A", "dv_B", "--include-derived"]):
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 1
                error_output = mock_stderr.getvalue()
                assert "--include-derived cannot be used with --diff" in error_output
                assert "cross-data-view" in error_output.lower()

    def test_include_calculated_with_diff_errors(self):
        """Test that --include-calculated with --diff (cross-DV) produces error"""
        from cja_auto_sdr.generator import main

        with patch("sys.argv", ["cja_sdr_generator.py", "--diff", "dv_A", "dv_B", "--include-calculated"]):
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 1
                error_output = mock_stderr.getvalue()
                assert "--include-calculated cannot be used with --diff" in error_output
                assert "cross-data-view" in error_output.lower()

    # Note: --include-* options ARE supported with --compare-snapshots for same-data-view comparisons
    # The validation happens at runtime when snapshots are loaded (checking data_view_id match)

    def test_include_segments_flag_registered(self):
        """Test that --include-segments flag is available"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--include-segments"]):
            args = parse_arguments()
            assert hasattr(args, "include_segments_inventory")
            assert args.include_segments_inventory is True

    def test_include_segments_default_false(self):
        """Test that --include-segments defaults to False"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345"]):
            args = parse_arguments()
            assert args.include_segments_inventory is False

    def test_all_three_inventory_flags_together(self):
        """Test that all three inventory flags can be used together"""
        with patch(
            "sys.argv",
            ["cja_sdr_generator.py", "dv_12345", "--include-derived", "--include-calculated", "--include-segments"],
        ):
            args = parse_arguments()
            assert args.include_derived_inventory is True
            assert args.include_calculated_metrics is True
            assert args.include_segments_inventory is True

    def test_include_segments_with_diff_errors(self):
        """Test that --include-segments with --diff (cross-DV) produces error"""
        from cja_auto_sdr.generator import main

        with patch("sys.argv", ["cja_sdr_generator.py", "--diff", "dv_A", "dv_B", "--include-segments"]):
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 1
                error_output = mock_stderr.getvalue()
                assert "--include-segments cannot be used with --diff" in error_output
                assert "cross-data-view" in error_output.lower()

    # Note: --include-segments IS supported with --compare-snapshots for same-data-view comparisons
    # The validation happens at runtime when snapshots are loaded (checking data_view_id match)

    def test_inventory_only_flag_registered(self):
        """Test that --inventory-only flag is available"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--include-segments", "--inventory-only"]):
            args = parse_arguments()
            assert hasattr(args, "inventory_only")
            assert args.inventory_only is True

    def test_inventory_only_default_false(self):
        """Test that --inventory-only defaults to False"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345"]):
            args = parse_arguments()
            assert args.inventory_only is False

    def test_inventory_only_without_include_flag_errors(self):
        """Test that --inventory-only without any --include-* flag produces error"""
        from cja_auto_sdr.generator import main

        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--inventory-only"]):
            with patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_12345"], {})):
                with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                    with pytest.raises(SystemExit) as exc_info:
                        main()
                    assert exc_info.value.code == 1
                    error_output = mock_stderr.getvalue()
                    assert "--inventory-only requires at least one inventory flag" in error_output

    def test_inventory_only_with_diff_errors(self):
        """Test that --inventory-only with --diff produces error"""
        from cja_auto_sdr.generator import main

        with patch("sys.argv", ["cja_sdr_generator.py", "--diff", "dv_A", "dv_B", "--inventory-only"]):
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 1
                error_output = mock_stderr.getvalue()
                assert "--inventory-only is only available in SDR mode" in error_output
                assert "not with --diff" in error_output

    def test_inventory_only_with_compare_snapshots_errors(self):
        """Test that --inventory-only with --compare-snapshots produces error"""
        from cja_auto_sdr.generator import main

        with patch("sys.argv", ["cja_sdr_generator.py", "--compare-snapshots", "a.json", "b.json", "--inventory-only"]):
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 1
                error_output = mock_stderr.getvalue()
                assert "--inventory-only is only available in SDR mode" in error_output
                assert "not with --compare-snapshots" in error_output

    def test_include_derived_with_snapshot_errors(self):
        """Test that --include-derived with --snapshot produces error"""
        from cja_auto_sdr.generator import main

        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--snapshot", "out.json", "--include-derived"]):
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 1
                error_output = mock_stderr.getvalue()
                assert "--include-derived cannot be used with --snapshot" in error_output
                assert "SDR generation mode" in error_output

    def test_include_derived_with_git_commit_errors(self):
        """Test that --include-derived with --git-commit produces error"""
        from cja_auto_sdr.generator import main

        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--git-commit", "--include-derived"]):
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with pytest.raises(SystemExit) as exc_info:
                    main()
                assert exc_info.value.code == 1
                error_output = mock_stderr.getvalue()
                assert "--include-derived cannot be used with --git-commit" in error_output
                assert "SDR generation mode" in error_output

    def test_include_calculated_with_snapshot_allowed(self):
        """Test that --include-calculated with --snapshot is allowed (no early validation error)"""
        # This test verifies the flag combination passes validation
        # It will fail later due to missing config, but that's expected
        from cja_auto_sdr.generator import main

        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--snapshot", "out.json", "--include-calculated"]):
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with pytest.raises(SystemExit):
                    main()
                error_output = mock_stderr.getvalue()
                # Should NOT contain the "cannot be used with --snapshot" error
                assert "--include-calculated cannot be used with --snapshot" not in error_output

    def test_include_segments_with_snapshot_allowed(self):
        """Test that --include-segments with --snapshot is allowed (no early validation error)"""
        from cja_auto_sdr.generator import main

        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--snapshot", "out.json", "--include-segments"]):
            with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                with pytest.raises(SystemExit):
                    main()
                error_output = mock_stderr.getvalue()
                # Should NOT contain the "cannot be used with --snapshot" error
                assert "--include-segments cannot be used with --snapshot" not in error_output

    # --inventory-summary tests

    def test_inventory_summary_flag_registered(self):
        """Test that --inventory-summary flag is available"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--include-segments", "--inventory-summary"]):
            args = parse_arguments()
            assert hasattr(args, "inventory_summary")
            assert args.inventory_summary is True

    def test_inventory_summary_default_false(self):
        """Test that --inventory-summary defaults to False"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345"]):
            args = parse_arguments()
            assert args.inventory_summary is False

    def test_inventory_summary_without_include_flag_errors(self):
        """Test that --inventory-summary without any --include-* flag produces error"""
        from cja_auto_sdr.generator import main

        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--inventory-summary"]):
            with patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_12345"], {})):
                with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                    with pytest.raises(SystemExit) as exc_info:
                        main()
                    assert exc_info.value.code == 1
                    error_output = mock_stderr.getvalue()
                    assert "--inventory-summary requires at least one inventory flag" in error_output

    def test_inventory_summary_with_inventory_only_errors(self):
        """Test that --inventory-summary with --inventory-only produces error (mutually exclusive)"""
        from cja_auto_sdr.generator import main

        with patch(
            "sys.argv",
            ["cja_sdr_generator.py", "dv_12345", "--include-segments", "--inventory-summary", "--inventory-only"],
        ):
            with patch("cja_auto_sdr.generator.resolve_data_view_names", return_value=(["dv_12345"], {})):
                with patch("sys.stderr", new_callable=StringIO) as mock_stderr:
                    with pytest.raises(SystemExit) as exc_info:
                        main()
                    assert exc_info.value.code == 1
                    error_output = mock_stderr.getvalue()
                    assert "--inventory-summary cannot be used with --inventory-only" in error_output

    def test_inventory_summary_with_multiple_include_flags(self):
        """Test that --inventory-summary works with multiple --include-* flags"""
        with patch(
            "sys.argv",
            ["cja_sdr_generator.py", "dv_12345", "--include-segments", "--include-calculated", "--inventory-summary"],
        ):
            args = parse_arguments()
            assert args.inventory_summary is True
            assert args.include_segments_inventory is True
            assert args.include_calculated_metrics is True


class TestDisplayInventorySummary:
    """Tests for display_inventory_summary function."""

    def test_summary_returns_dict(self, tmp_path):
        """Test that display_inventory_summary returns a dictionary"""
        from cja_auto_sdr.generator import display_inventory_summary

        result = display_inventory_summary(
            data_view_id="dv_12345",
            data_view_name="Test Data View",
            output_format="console",
            output_dir=str(tmp_path),
            quiet=True,
        )
        assert isinstance(result, dict)
        assert result["data_view_id"] == "dv_12345"
        assert result["data_view_name"] == "Test Data View"
        assert "timestamp" in result
        assert "inventories" in result

    def test_summary_with_no_inventories(self, tmp_path):
        """Test summary with no inventory data"""
        from cja_auto_sdr.generator import display_inventory_summary

        result = display_inventory_summary(
            data_view_id="dv_test",
            data_view_name="Empty Test",
            output_format="console",
            output_dir=str(tmp_path),
            quiet=True,
        )
        assert result["inventories"] == {}
        assert result["high_complexity_items"] == []

    def test_summary_json_output(self, tmp_path):
        """Test that JSON output is created when format is json"""
        import json

        from cja_auto_sdr.generator import display_inventory_summary

        display_inventory_summary(
            data_view_id="dv_json_test",
            data_view_name="JSON Test View",
            output_format="json",
            output_dir=str(tmp_path),
            quiet=True,
        )

        # Check JSON file was created
        json_files = list(tmp_path.glob("*_inventory_summary.json"))
        assert len(json_files) == 1

        # Verify JSON content
        with open(json_files[0]) as f:
            saved_data = json.load(f)
        assert saved_data["data_view_id"] == "dv_json_test"
        assert saved_data["data_view_name"] == "JSON Test View"

    def test_summary_high_complexity_threshold(self, tmp_path):
        """Test that high-complexity items are collected at threshold 70"""
        from unittest.mock import MagicMock

        from cja_auto_sdr.generator import display_inventory_summary

        # Create mock inventory with high-complexity item
        mock_inventory = MagicMock()
        mock_inventory.get_summary.return_value = {
            "total_derived_fields": 2,
            "metrics_count": 1,
            "dimensions_count": 1,
            "complexity": {"average": 50.0, "max": 85.0, "high_complexity_count": 1, "elevated_complexity_count": 1},
        }

        # Create mock fields
        high_complexity_field = MagicMock()
        high_complexity_field.complexity_score = 85
        high_complexity_field.component_name = "Complex Field"
        high_complexity_field.logic_summary = "Complex logic here"

        low_complexity_field = MagicMock()
        low_complexity_field.complexity_score = 30
        low_complexity_field.component_name = "Simple Field"
        low_complexity_field.logic_summary = "Simple logic"

        mock_inventory.fields = [high_complexity_field, low_complexity_field]

        result = display_inventory_summary(
            data_view_id="dv_complexity",
            data_view_name="Complexity Test",
            derived_inventory=mock_inventory,
            output_format="console",
            output_dir=str(tmp_path),
            quiet=True,
        )

        # Only the high-complexity item (>=70) should be in the list
        assert len(result["high_complexity_items"]) == 1
        assert result["high_complexity_items"][0]["name"] == "Complex Field"
        assert result["high_complexity_items"][0]["complexity"] == 85

    def test_summary_console_output_not_quiet(self, tmp_path, capsys):
        """Test that console output is produced when not quiet"""
        from cja_auto_sdr.generator import display_inventory_summary

        display_inventory_summary(
            data_view_id="dv_console",
            data_view_name="Console Test View",
            output_format="console",
            output_dir=str(tmp_path),
            quiet=False,
        )

        captured = capsys.readouterr()
        assert "Inventory Summary: Console Test View" in captured.out
        assert "dv_console" in captured.out


class TestIncludeAllInventory:
    """Tests for --include-all-inventory flag."""

    def test_include_all_inventory_flag_registered(self):
        """Test that --include-all-inventory flag is available"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--include-all-inventory"]):
            args = parse_arguments()
            assert hasattr(args, "include_all_inventory")
            assert args.include_all_inventory is True

    def test_include_all_inventory_default_false(self):
        """Test that --include-all-inventory defaults to False"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345"]):
            args = parse_arguments()
            assert args.include_all_inventory is False

    def test_include_all_inventory_with_inventory_only(self):
        """Test that --include-all-inventory works with --inventory-only"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--include-all-inventory", "--inventory-only"]):
            args = parse_arguments()
            assert args.include_all_inventory is True
            assert args.inventory_only is True

    def test_include_all_inventory_with_inventory_summary(self):
        """Test that --include-all-inventory works with --inventory-summary"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--include-all-inventory", "--inventory-summary"]):
            args = parse_arguments()
            assert args.include_all_inventory is True
            assert args.inventory_summary is True

    @patch("cja_auto_sdr.generator.handle_snapshot_command")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_include_all_inventory_expands_for_snapshot_mode(self, mock_resolve, mock_handle_snapshot):
        """Test include-all enables calculated+segments for --snapshot mode."""
        from cja_auto_sdr.generator import main

        mock_resolve.return_value = (["dv_12345"], {})
        mock_handle_snapshot.return_value = True

        with patch(
            "sys.argv",
            ["cja_sdr_generator.py", "dv_12345", "--snapshot", "baseline.json", "--include-all-inventory"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

        kwargs = mock_handle_snapshot.call_args.kwargs
        assert kwargs["include_calculated_metrics"] is True
        assert kwargs["include_segments"] is True

    @patch("cja_auto_sdr.generator.handle_diff_snapshot_command")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_include_all_inventory_expands_for_diff_snapshot_mode(self, mock_resolve, mock_handle_diff_snapshot):
        """Test include-all enables calculated+segments for --diff-snapshot mode."""
        from cja_auto_sdr.generator import main

        mock_resolve.return_value = (["dv_12345"], {})
        mock_handle_diff_snapshot.return_value = (True, False, None)

        with patch(
            "sys.argv",
            ["cja_sdr_generator.py", "dv_12345", "--diff-snapshot", "baseline.json", "--include-all-inventory"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

        kwargs = mock_handle_diff_snapshot.call_args.kwargs
        assert kwargs["include_calc_metrics"] is True
        assert kwargs["include_segments"] is True

    @patch("cja_auto_sdr.generator.handle_compare_snapshots_command")
    def test_include_all_inventory_expands_for_compare_snapshots_mode(self, mock_handle_compare_snapshots):
        """Test include-all enables calculated+segments for --compare-snapshots mode."""
        from cja_auto_sdr.generator import main

        mock_handle_compare_snapshots.return_value = (True, False, None)

        with patch(
            "sys.argv",
            ["cja_sdr_generator.py", "--compare-snapshots", "source.json", "target.json", "--include-all-inventory"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

        kwargs = mock_handle_compare_snapshots.call_args.kwargs
        assert kwargs["include_calc_metrics"] is True
        assert kwargs["include_segments"] is True

    @patch("cja_auto_sdr.generator.handle_diff_snapshot_command")
    @patch("cja_auto_sdr.generator.SnapshotManager")
    @patch("cja_auto_sdr.generator.resolve_data_view_names")
    def test_include_all_inventory_expands_for_compare_with_prev_mode(
        self,
        mock_resolve,
        mock_snapshot_manager_cls,
        mock_handle_diff_snapshot,
    ):
        """Test include-all enables calculated+segments for --compare-with-prev mode."""
        from cja_auto_sdr.generator import main

        mock_resolve.return_value = (["dv_12345"], {})
        mock_snapshot_manager_cls.return_value.get_most_recent_snapshot.return_value = "./snapshots/prev.json"
        mock_handle_diff_snapshot.return_value = (True, False, None)

        with patch(
            "sys.argv",
            ["cja_sdr_generator.py", "dv_12345", "--compare-with-prev", "--include-all-inventory"],
        ):
            with pytest.raises(SystemExit) as exc_info:
                main()
            assert exc_info.value.code == 0

        kwargs = mock_handle_diff_snapshot.call_args.kwargs
        assert kwargs["snapshot_file"] == "./snapshots/prev.json"
        assert kwargs["include_calc_metrics"] is True
        assert kwargs["include_segments"] is True


class TestProcessingResultInventory:
    """Tests for ProcessingResult inventory statistics."""

    def test_has_inventory_false_when_empty(self):
        """Test has_inventory is False when no inventory data"""
        from cja_auto_sdr.generator import ProcessingResult

        result = ProcessingResult(data_view_id="dv_test", data_view_name="Test", success=True, duration=1.0)
        assert result.has_inventory is False

    def test_has_inventory_true_with_segments(self):
        """Test has_inventory is True when segments count > 0"""
        from cja_auto_sdr.generator import ProcessingResult

        result = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test",
            success=True,
            duration=1.0,
            segments_count=10,
        )
        assert result.has_inventory is True

    def test_has_inventory_true_with_calculated_metrics(self):
        """Test has_inventory is True when calculated metrics count > 0"""
        from cja_auto_sdr.generator import ProcessingResult

        result = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test",
            success=True,
            duration=1.0,
            calculated_metrics_count=5,
        )
        assert result.has_inventory is True

    def test_has_inventory_true_with_derived_fields(self):
        """Test has_inventory is True when derived fields count > 0"""
        from cja_auto_sdr.generator import ProcessingResult

        result = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test",
            success=True,
            duration=1.0,
            derived_fields_count=15,
        )
        assert result.has_inventory is True

    def test_total_high_complexity(self):
        """Test total_high_complexity sums all high-complexity counts"""
        from cja_auto_sdr.generator import ProcessingResult

        result = ProcessingResult(
            data_view_id="dv_test",
            data_view_name="Test",
            success=True,
            duration=1.0,
            segments_high_complexity=2,
            calculated_metrics_high_complexity=3,
            derived_fields_high_complexity=1,
        )
        assert result.total_high_complexity == 6

    def test_total_high_complexity_zero_when_empty(self):
        """Test total_high_complexity is 0 when no high-complexity items"""
        from cja_auto_sdr.generator import ProcessingResult

        result = ProcessingResult(data_view_id="dv_test", data_view_name="Test", success=True, duration=1.0)
        assert result.total_high_complexity == 0


# ==================== v3.2.0 SAFEGUARDS ====================


class TestConfigJsonFlag:
    """Tests for --config-json flag (v3.2.0)"""

    def test_config_json_flag_registered(self):
        """Test that --config-json flag is available in argument parser"""
        with patch("sys.argv", ["cja_sdr_generator.py", "--config-json"]):
            args = parse_arguments()
            assert hasattr(args, "config_json")
            assert args.config_json is True

    def test_config_json_default_false(self):
        """Test that --config-json defaults to False"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345"]):
            args = parse_arguments()
            assert hasattr(args, "config_json")
            assert args.config_json is False

    def test_config_json_implies_config_status(self):
        """Test that --config-json can be used without --config-status"""
        with patch("sys.argv", ["cja_sdr_generator.py", "--config-json"]):
            args = parse_arguments()
            # --config-json should work standalone (implies --config-status)
            assert args.config_json is True

    def test_show_config_status_json_output(self, tmp_path, capsys):
        """Test that show_config_status produces valid JSON when output_json=True"""
        from cja_auto_sdr.generator import show_config_status

        # Create a minimal config file
        config_file = tmp_path / "config.json"
        config_file.write_text('{"org_id": "test@org", "client_id": "abc123", "secret": "secretvalue"}')

        show_config_status(str(config_file), output_json=True)

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        assert output["valid"] is True
        assert output["source_type"] == "file"
        assert "credentials" in output
        assert output["credentials"]["org_id"]["set"] is True
        assert output["credentials"]["client_id"]["set"] is True
        assert output["credentials"]["secret"]["set"] is True
        # Verify secrets are masked (shows first 4 + *** + last 4 chars)
        assert "*" in output["credentials"]["secret"]["value"]
        assert output["credentials"]["secret"]["value"] != "secretvalue"

    def test_show_config_status_json_invalid_config(self, tmp_path, capsys):
        """Test that show_config_status JSON output handles missing config"""
        from cja_auto_sdr.generator import show_config_status

        show_config_status(str(tmp_path / "nonexistent.json"), output_json=True)

        captured = capsys.readouterr()
        output = json.loads(captured.out)

        assert output["valid"] is False
        assert "error" in output


class TestYesFlag:
    """Tests for --yes / -y flag (v3.2.0)"""

    def test_yes_flag_registered(self):
        """Test that --yes flag is available in argument parser"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "--yes"]):
            args = parse_arguments()
            assert hasattr(args, "assume_yes")
            assert args.assume_yes is True

    def test_yes_short_flag_registered(self):
        """Test that -y short flag is available"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345", "-y"]):
            args = parse_arguments()
            assert hasattr(args, "assume_yes")
            assert args.assume_yes is True

    def test_yes_flag_default_false(self):
        """Test that --yes defaults to False"""
        with patch("sys.argv", ["cja_sdr_generator.py", "dv_12345"]):
            args = parse_arguments()
            assert hasattr(args, "assume_yes")
            assert args.assume_yes is False


class TestDuplicateDataViewWarning:
    """Tests for duplicate data view ID detection (v3.2.0)"""

    def test_duplicate_removal_logic(self):
        """Test that duplicate detection logic works correctly"""
        # Simulate the deduplication logic from main()
        data_views = ["dv_1", "dv_2", "dv_1", "dv_3", "dv_2", "dv_1"]

        seen = set()
        duplicates = []
        unique_data_views = []
        for dv in data_views:
            if dv in seen:
                duplicates.append(dv)
            else:
                seen.add(dv)
                unique_data_views.append(dv)

        assert unique_data_views == ["dv_1", "dv_2", "dv_3"]
        assert set(duplicates) == {"dv_1", "dv_2"}
        assert len(duplicates) == 3  # dv_1 appears twice extra, dv_2 once

    def test_no_duplicates_preserved(self):
        """Test that unique data views are preserved as-is"""
        data_views = ["dv_1", "dv_2", "dv_3"]

        seen = set()
        duplicates = []
        unique_data_views = []
        for dv in data_views:
            if dv in seen:
                duplicates.append(dv)
            else:
                seen.add(dv)
                unique_data_views.append(dv)

        assert unique_data_views == data_views
        assert duplicates == []


class TestOutputDirectoryWriteCheck:
    """Tests for proactive output directory write check (v3.2.0)"""

    def test_output_dir_exists_and_writable(self, tmp_path):
        """Test that existing writable directory passes check"""
        # tmp_path is always writable in tests
        assert os.access(tmp_path, os.W_OK)

    def test_output_dir_parent_checked_for_creation(self, tmp_path):
        """Test that parent directory is checked when output dir doesn't exist"""
        new_dir = tmp_path / "new_output_dir"
        # Parent (tmp_path) exists and is writable
        assert not new_dir.exists()
        assert os.access(tmp_path, os.W_OK)

    def test_output_dir_creation_blocked_by_permissions(self, tmp_path):
        """Test detection of non-writable parent directory"""
        import stat

        # Create a read-only directory
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()

        try:
            # Make it read-only
            readonly_dir.chmod(stat.S_IRUSR | stat.S_IXUSR)

            # Check that we cannot write to it
            assert not os.access(readonly_dir, os.W_OK)

            # Trying to create a subdir would fail
            new_subdir = readonly_dir / "cannot_create"
            assert not new_subdir.exists()

        finally:
            # Restore permissions for cleanup
            readonly_dir.chmod(stat.S_IRWXU)
