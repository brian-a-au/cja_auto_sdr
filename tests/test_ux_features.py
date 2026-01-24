"""
Tests for UX Enhancement Features (v3.0.14)

Tests for:
- --open flag (auto-open generated files)
- --output (stdout support for piping)
- --stats (quick statistics mode)
- --list-dataviews with JSON/CSV format
"""

import pytest
import json
import sys
import os
from unittest.mock import patch, MagicMock
from io import StringIO

# Import the functions from the main module
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cja_sdr_generator import (
    parse_arguments,
    open_file_in_default_app,
    list_dataviews,
    show_stats,
)


class TestOpenFlag:
    """Tests for the --open flag to auto-open generated files"""

    def test_open_flag_registered(self):
        """Test that --open flag is available in argument parser"""
        with patch('sys.argv', ['cja_sdr_generator.py', 'dv_12345', '--open']):
            args = parse_arguments()
            assert hasattr(args, 'open')
            assert args.open is True

    def test_open_flag_default_false(self):
        """Test that --open defaults to False"""
        with patch('sys.argv', ['cja_sdr_generator.py', 'dv_12345']):
            args = parse_arguments()
            assert hasattr(args, 'open')
            assert args.open is False

    @patch('subprocess.run')
    @patch('platform.system', return_value='Darwin')
    def test_open_file_macos(self, mock_platform, mock_subprocess):
        """Test file opening on macOS uses 'open' command"""
        mock_subprocess.return_value = MagicMock(returncode=0)
        result = open_file_in_default_app('/path/to/file.xlsx')
        assert result is True
        mock_subprocess.assert_called_once_with(['open', '/path/to/file.xlsx'], check=True)

    @patch('subprocess.run')
    @patch('platform.system', return_value='Linux')
    def test_open_file_linux(self, mock_platform, mock_subprocess):
        """Test file opening on Linux uses 'xdg-open' command"""
        mock_subprocess.return_value = MagicMock(returncode=0)
        result = open_file_in_default_app('/path/to/file.xlsx')
        assert result is True
        mock_subprocess.assert_called_once_with(['xdg-open', '/path/to/file.xlsx'], check=True)

    @pytest.mark.skipif(os.name != 'nt', reason="os.startfile only exists on Windows")
    @patch('os.startfile')
    @patch('platform.system', return_value='Windows')
    def test_open_file_windows(self, mock_platform, mock_startfile):
        """Test file opening on Windows uses os.startfile"""
        result = open_file_in_default_app('C:\\path\\to\\file.xlsx')
        assert result is True
        mock_startfile.assert_called_once_with('C:\\path\\to\\file.xlsx')

    @patch('subprocess.run', side_effect=Exception("Command failed"))
    @patch('platform.system', return_value='Darwin')
    def test_open_file_failure(self, mock_platform, mock_subprocess):
        """Test graceful handling when file opening fails"""
        result = open_file_in_default_app('/path/to/file.xlsx')
        assert result is False

    @patch('webbrowser.open')
    @patch('subprocess.run', side_effect=Exception("Command failed"))
    @patch('platform.system', return_value='Linux')
    def test_open_html_fallback_to_webbrowser(self, mock_platform, mock_subprocess, mock_webbrowser):
        """Test HTML files fall back to webbrowser on failure"""
        mock_webbrowser.return_value = True
        result = open_file_in_default_app('/path/to/file.html')
        assert result is True
        mock_webbrowser.assert_called_once()


class TestOutputStdout:
    """Tests for --output - (stdout) support"""

    def test_output_argument_registered(self):
        """Test that --output argument is available"""
        with patch('sys.argv', ['cja_sdr_generator.py', 'dv_12345', '--output', '-']):
            args = parse_arguments()
            assert hasattr(args, 'output')
            assert args.output == '-'

    def test_output_stdout_alias(self):
        """Test that 'stdout' works as an alias for '-'"""
        with patch('sys.argv', ['cja_sdr_generator.py', 'dv_12345', '--output', 'stdout']):
            args = parse_arguments()
            assert args.output == 'stdout'

    def test_output_file_path(self):
        """Test that regular file paths work"""
        with patch('sys.argv', ['cja_sdr_generator.py', 'dv_12345', '--output', '/tmp/output.json']):
            args = parse_arguments()
            assert args.output == '/tmp/output.json'


class TestStatsMode:
    """Tests for --stats quick statistics mode"""

    def test_stats_flag_registered(self):
        """Test that --stats flag is available"""
        with patch('sys.argv', ['cja_sdr_generator.py', 'dv_12345', '--stats']):
            args = parse_arguments()
            assert hasattr(args, 'stats')
            assert args.stats is True

    def test_stats_flag_default_false(self):
        """Test that --stats defaults to False"""
        with patch('sys.argv', ['cja_sdr_generator.py', 'dv_12345']):
            args = parse_arguments()
            assert hasattr(args, 'stats')
            assert args.stats is False

    def test_stats_with_format_json(self):
        """Test --stats with --format json"""
        with patch('sys.argv', ['cja_sdr_generator.py', 'dv_12345', '--stats', '--format', 'json']):
            args = parse_arguments()
            assert args.stats is True
            assert args.format == 'json'

    def test_stats_with_format_csv(self):
        """Test --stats with --format csv"""
        with patch('sys.argv', ['cja_sdr_generator.py', 'dv_12345', '--stats', '--format', 'csv']):
            args = parse_arguments()
            assert args.stats is True
            assert args.format == 'csv'

    def test_stats_with_multiple_data_views(self):
        """Test --stats with multiple data views"""
        with patch('sys.argv', ['cja_sdr_generator.py', 'dv_1', 'dv_2', 'dv_3', '--stats']):
            args = parse_arguments()
            assert args.stats is True
            assert len(args.data_views) == 3


class TestListDataviewsFormat:
    """Tests for --list-dataviews with format options"""

    def test_list_dataviews_with_json_format(self):
        """Test --list-dataviews --format json"""
        with patch('sys.argv', ['cja_sdr_generator.py', '--list-dataviews', '--format', 'json']):
            args = parse_arguments()
            assert args.list_dataviews is True
            assert args.format == 'json'

    def test_list_dataviews_with_csv_format(self):
        """Test --list-dataviews --format csv"""
        with patch('sys.argv', ['cja_sdr_generator.py', '--list-dataviews', '--format', 'csv']):
            args = parse_arguments()
            assert args.list_dataviews is True
            assert args.format == 'csv'

    def test_list_dataviews_with_output_stdout(self):
        """Test --list-dataviews --output -"""
        with patch('sys.argv', ['cja_sdr_generator.py', '--list-dataviews', '--output', '-']):
            args = parse_arguments()
            assert args.list_dataviews is True
            assert args.output == '-'


class TestShowStatsFunction:
    """Tests for the show_stats function"""

    @patch('cja_sdr_generator.cjapy')
    def test_show_stats_json_output(self, mock_cjapy):
        """Test show_stats with JSON format"""
        # Setup mock
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataView.return_value = {'name': 'Test View', 'owner': {'name': 'Owner'}}
        mock_cja.getMetrics.return_value = MagicMock(empty=False, __len__=lambda x: 10)
        mock_cja.getDimensions.return_value = MagicMock(empty=False, __len__=lambda x: 5)

        # Capture stdout
        captured_output = StringIO()
        with patch('sys.stdout', captured_output):
            result = show_stats(['dv_12345'], output_format='json', output_file='-', quiet=True)

        assert result is True
        output = captured_output.getvalue()
        data = json.loads(output)
        assert 'stats' in data
        assert 'count' in data
        assert 'totals' in data

    @patch('cja_sdr_generator.cjapy')
    def test_show_stats_csv_output(self, mock_cjapy):
        """Test show_stats with CSV format"""
        # Setup mock
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataView.return_value = {'name': 'Test View', 'owner': {'name': 'Owner'}}
        mock_cja.getMetrics.return_value = MagicMock(empty=False, __len__=lambda x: 10)
        mock_cja.getDimensions.return_value = MagicMock(empty=False, __len__=lambda x: 5)

        # Capture stdout
        captured_output = StringIO()
        with patch('sys.stdout', captured_output):
            result = show_stats(['dv_12345'], output_format='csv', output_file='-', quiet=True)

        assert result is True
        output = captured_output.getvalue()
        lines = output.strip().split('\n')
        assert lines[0] == 'id,name,owner,metrics,dimensions,total_components'
        assert len(lines) == 2  # Header + 1 data row

    @patch('cja_sdr_generator.cjapy')
    def test_show_stats_table_output(self, mock_cjapy):
        """Test show_stats with table format"""
        # Setup mock
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataView.return_value = {'name': 'Test View', 'owner': {'name': 'Owner'}}
        mock_cja.getMetrics.return_value = MagicMock(empty=False, __len__=lambda x: 10)
        mock_cja.getDimensions.return_value = MagicMock(empty=False, __len__=lambda x: 5)

        # Capture stdout
        captured_output = StringIO()
        with patch('sys.stdout', captured_output):
            result = show_stats(['dv_12345'], output_format='table', quiet=False)

        assert result is True
        output = captured_output.getvalue()
        assert 'DATA VIEW STATISTICS' in output
        assert 'TOTAL' in output


class TestListDataviewsFunction:
    """Tests for the list_dataviews function with format options"""

    @patch('cja_sdr_generator.cjapy')
    def test_list_dataviews_json_output(self, mock_cjapy):
        """Test list_dataviews with JSON format"""
        # Setup mock
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataViews.return_value = [
            {'id': 'dv_1', 'name': 'View 1', 'owner': {'name': 'Owner 1'}},
            {'id': 'dv_2', 'name': 'View 2', 'owner': {'name': 'Owner 2'}},
        ]

        # Capture stdout
        captured_output = StringIO()
        with patch('sys.stdout', captured_output):
            result = list_dataviews(output_format='json', output_file='-')

        assert result is True
        output = captured_output.getvalue()
        data = json.loads(output)
        assert 'dataViews' in data
        assert 'count' in data
        assert data['count'] == 2

    @patch('cja_sdr_generator.cjapy')
    def test_list_dataviews_csv_output(self, mock_cjapy):
        """Test list_dataviews with CSV format"""
        # Setup mock
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataViews.return_value = [
            {'id': 'dv_1', 'name': 'View 1', 'owner': {'name': 'Owner 1'}},
            {'id': 'dv_2', 'name': 'View 2', 'owner': {'name': 'Owner 2'}},
        ]

        # Capture stdout
        captured_output = StringIO()
        with patch('sys.stdout', captured_output):
            result = list_dataviews(output_format='csv', output_file='-')

        assert result is True
        output = captured_output.getvalue()
        lines = output.strip().split('\n')
        assert lines[0] == 'id,name,owner'
        assert len(lines) == 3  # Header + 2 data rows

    @patch('cja_sdr_generator.cjapy')
    def test_list_dataviews_empty_json(self, mock_cjapy):
        """Test list_dataviews JSON output when no data views"""
        # Setup mock
        mock_cja = MagicMock()
        mock_cjapy.CJA.return_value = mock_cja
        mock_cja.getDataViews.return_value = []

        # Capture stdout
        captured_output = StringIO()
        with patch('sys.stdout', captured_output):
            result = list_dataviews(output_format='json', output_file='-')

        assert result is True
        output = captured_output.getvalue()
        data = json.loads(output)
        assert data['count'] == 0
        assert data['dataViews'] == []


class TestCombinedFeatures:
    """Tests for combined feature usage"""

    def test_stats_with_output_stdout(self):
        """Test --stats with --output -"""
        with patch('sys.argv', ['cja_sdr_generator.py', 'dv_12345', '--stats', '--output', '-']):
            args = parse_arguments()
            assert args.stats is True
            assert args.output == '-'

    def test_open_with_format_excel(self):
        """Test --open with --format excel"""
        with patch('sys.argv', ['cja_sdr_generator.py', 'dv_12345', '--open', '--format', 'excel']):
            args = parse_arguments()
            assert args.open is True
            assert args.format == 'excel'

    def test_open_with_batch_mode(self):
        """Test --open with multiple data views"""
        with patch('sys.argv', ['cja_sdr_generator.py', 'dv_1', 'dv_2', '--open']):
            args = parse_arguments()
            assert args.open is True
            assert len(args.data_views) == 2


class TestVersionUpdated:
    """Test that version is correct"""

    def test_version_is_3_0_16(self):
        """Test that version is 3.0.16"""
        from cja_sdr_generator import __version__
        assert __version__ == "3.0.16"


class TestFormatAutoDetection:
    """Tests for auto-detecting format from file extension"""

    def test_infer_format_xlsx(self):
        """Test xlsx extension infers excel format"""
        from cja_sdr_generator import infer_format_from_path
        assert infer_format_from_path('report.xlsx') == 'excel'

    def test_infer_format_xls(self):
        """Test xls extension infers excel format"""
        from cja_sdr_generator import infer_format_from_path
        assert infer_format_from_path('report.xls') == 'excel'

    def test_infer_format_csv(self):
        """Test csv extension infers csv format"""
        from cja_sdr_generator import infer_format_from_path
        assert infer_format_from_path('data.csv') == 'csv'

    def test_infer_format_json(self):
        """Test json extension infers json format"""
        from cja_sdr_generator import infer_format_from_path
        assert infer_format_from_path('output.json') == 'json'

    def test_infer_format_html(self):
        """Test html extension infers html format"""
        from cja_sdr_generator import infer_format_from_path
        assert infer_format_from_path('report.html') == 'html'

    def test_infer_format_htm(self):
        """Test htm extension infers html format"""
        from cja_sdr_generator import infer_format_from_path
        assert infer_format_from_path('report.htm') == 'html'

    def test_infer_format_md(self):
        """Test md extension infers markdown format"""
        from cja_sdr_generator import infer_format_from_path
        assert infer_format_from_path('doc.md') == 'markdown'

    def test_infer_format_markdown(self):
        """Test markdown extension infers markdown format"""
        from cja_sdr_generator import infer_format_from_path
        assert infer_format_from_path('doc.markdown') == 'markdown'

    def test_infer_format_unknown_extension(self):
        """Test unknown extension returns None"""
        from cja_sdr_generator import infer_format_from_path
        assert infer_format_from_path('file.txt') is None
        assert infer_format_from_path('file.pdf') is None

    def test_infer_format_stdout(self):
        """Test stdout markers return None"""
        from cja_sdr_generator import infer_format_from_path
        assert infer_format_from_path('-') is None
        assert infer_format_from_path('stdout') is None

    def test_infer_format_empty(self):
        """Test empty/None returns None"""
        from cja_sdr_generator import infer_format_from_path
        assert infer_format_from_path('') is None
        assert infer_format_from_path(None) is None

    def test_infer_format_case_insensitive(self):
        """Test extension matching is case insensitive"""
        from cja_sdr_generator import infer_format_from_path
        assert infer_format_from_path('REPORT.XLSX') == 'excel'
        assert infer_format_from_path('Data.JSON') == 'json'


class TestConfigStatusFlag:
    """Tests for --config-status flag"""

    def test_config_status_flag_registered(self):
        """Test that --config-status flag is available"""
        with patch('sys.argv', ['cja_sdr_generator.py', '--config-status']):
            args = parse_arguments()
            assert hasattr(args, 'config_status')
            assert args.config_status is True

    def test_config_status_default_false(self):
        """Test that --config-status defaults to False"""
        with patch('sys.argv', ['cja_sdr_generator.py', 'dv_12345']):
            args = parse_arguments()
            assert args.config_status is False


class TestColorThemeFlag:
    """Tests for --color-theme flag"""

    def test_color_theme_flag_registered(self):
        """Test that --color-theme flag is available"""
        with patch('sys.argv', ['cja_sdr_generator.py', '--diff', 'dv_A', 'dv_B', '--color-theme', 'accessible']):
            args = parse_arguments()
            assert hasattr(args, 'color_theme')
            assert args.color_theme == 'accessible'

    def test_color_theme_default(self):
        """Test that --color-theme defaults to 'default'"""
        with patch('sys.argv', ['cja_sdr_generator.py', 'dv_12345']):
            args = parse_arguments()
            assert args.color_theme == 'default'

    def test_color_theme_choices(self):
        """Test that only valid choices are accepted"""
        # Valid choice
        with patch('sys.argv', ['cja_sdr_generator.py', '--diff', 'dv_A', 'dv_B', '--color-theme', 'default']):
            args = parse_arguments()
            assert args.color_theme == 'default'

        # Invalid choice should raise
        with patch('sys.argv', ['cja_sdr_generator.py', '--diff', 'dv_A', 'dv_B', '--color-theme', 'invalid']):
            with pytest.raises(SystemExit):
                parse_arguments()


class TestConsoleColorsTheme:
    """Tests for ConsoleColors theme functionality"""

    def test_set_theme_default(self):
        """Test setting default theme"""
        from cja_sdr_generator import ConsoleColors
        ConsoleColors.set_theme('default')
        assert ConsoleColors._theme == 'default'

    def test_set_theme_accessible(self):
        """Test setting accessible theme"""
        from cja_sdr_generator import ConsoleColors
        ConsoleColors.set_theme('accessible')
        assert ConsoleColors._theme == 'accessible'
        # Reset to default for other tests
        ConsoleColors.set_theme('default')

    def test_set_theme_invalid(self):
        """Test that invalid theme raises ValueError"""
        from cja_sdr_generator import ConsoleColors
        with pytest.raises(ValueError):
            ConsoleColors.set_theme('invalid_theme')

    def test_diff_added_method_exists(self):
        """Test diff_added method exists and works"""
        from cja_sdr_generator import ConsoleColors
        result = ConsoleColors.diff_added('test')
        assert 'test' in result

    def test_diff_removed_method_exists(self):
        """Test diff_removed method exists and works"""
        from cja_sdr_generator import ConsoleColors
        result = ConsoleColors.diff_removed('test')
        assert 'test' in result

    def test_diff_modified_method_exists(self):
        """Test diff_modified method exists and works"""
        from cja_sdr_generator import ConsoleColors
        result = ConsoleColors.diff_modified('test')
        assert 'test' in result


class TestInteractiveFlag:
    """Tests for --interactive flag"""

    def test_interactive_flag_registered(self):
        """Test that --interactive flag is available"""
        with patch('sys.argv', ['cja_sdr_generator.py', '--interactive']):
            args = parse_arguments()
            assert hasattr(args, 'interactive')
            assert args.interactive is True

    def test_interactive_short_flag(self):
        """Test that -i short flag works"""
        with patch('sys.argv', ['cja_sdr_generator.py', '-i']):
            args = parse_arguments()
            assert args.interactive is True

    def test_interactive_default_false(self):
        """Test that --interactive defaults to False"""
        with patch('sys.argv', ['cja_sdr_generator.py', 'dv_12345']):
            args = parse_arguments()
            assert args.interactive is False


class TestMetricsDimensionsOnlyForSDR:
    """Tests for --metrics-only and --dimensions-only flags in SDR mode"""

    def test_metrics_only_flag_available(self):
        """Test that --metrics-only works with SDR mode"""
        with patch('sys.argv', ['cja_sdr_generator.py', 'dv_12345', '--metrics-only']):
            args = parse_arguments()
            assert args.metrics_only is True

    def test_dimensions_only_flag_available(self):
        """Test that --dimensions-only works with SDR mode"""
        with patch('sys.argv', ['cja_sdr_generator.py', 'dv_12345', '--dimensions-only']):
            args = parse_arguments()
            assert args.dimensions_only is True

    def test_both_flags_default_false(self):
        """Test that both flags default to False"""
        with patch('sys.argv', ['cja_sdr_generator.py', 'dv_12345']):
            args = parse_arguments()
            assert args.metrics_only is False
            assert args.dimensions_only is False


class TestFormatAliases:
    """Tests for format aliases (reports, data, ci)"""

    def test_format_alias_reports(self):
        """Test 'reports' format alias is accepted"""
        with patch('sys.argv', ['cja_sdr_generator.py', 'dv_12345', '--format', 'reports']):
            args = parse_arguments()
            assert args.format == 'reports'

    def test_format_alias_data(self):
        """Test 'data' format alias is accepted"""
        with patch('sys.argv', ['cja_sdr_generator.py', 'dv_12345', '--format', 'data']):
            args = parse_arguments()
            assert args.format == 'data'

    def test_format_alias_ci(self):
        """Test 'ci' format alias is accepted"""
        with patch('sys.argv', ['cja_sdr_generator.py', 'dv_12345', '--format', 'ci']):
            args = parse_arguments()
            assert args.format == 'ci'

    def test_should_generate_format_with_alias(self):
        """Test should_generate_format works with aliases"""
        from cja_sdr_generator import should_generate_format

        # 'reports' alias = excel + markdown
        assert should_generate_format('reports', 'excel') is True
        assert should_generate_format('reports', 'markdown') is True
        assert should_generate_format('reports', 'csv') is False

        # 'data' alias = csv + json
        assert should_generate_format('data', 'csv') is True
        assert should_generate_format('data', 'json') is True
        assert should_generate_format('data', 'excel') is False

        # 'ci' alias = json + markdown
        assert should_generate_format('ci', 'json') is True
        assert should_generate_format('ci', 'markdown') is True
        assert should_generate_format('ci', 'excel') is False


class TestShowTimingsFlag:
    """Tests for --show-timings flag"""

    def test_show_timings_flag_registered(self):
        """Test that --show-timings flag is available"""
        with patch('sys.argv', ['cja_sdr_generator.py', 'dv_12345', '--show-timings']):
            args = parse_arguments()
            assert hasattr(args, 'show_timings')
            assert args.show_timings is True

    def test_show_timings_default_false(self):
        """Test that --show-timings defaults to False"""
        with patch('sys.argv', ['cja_sdr_generator.py', 'dv_12345']):
            args = parse_arguments()
            assert args.show_timings is False
