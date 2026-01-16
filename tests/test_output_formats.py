"""Tests for output format flexibility (CSV, JSON, HTML, Excel)

This test suite validates that all output formats generate correctly
and contain the expected data structures.
"""
import pytest
import sys
import pandas as pd
import logging
import json
import os
from pathlib import Path

# Import the functions we're testing
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cja_sdr_generator import (
    write_csv_output,
    write_json_output,
    write_html_output,
    write_markdown_output
)


class TestCSVOutput:
    """Test CSV output format generation"""

    def test_csv_output_creates_directory(self, tmp_path, sample_data_dict):
        """Test that CSV output creates a directory with individual files"""
        logger = logging.getLogger("test")

        output_path = write_csv_output(
            sample_data_dict,
            "test_dataview",
            str(tmp_path),
            logger
        )

        # Check directory was created
        assert os.path.exists(output_path)
        assert os.path.isdir(output_path)

    def test_csv_output_creates_all_files(self, tmp_path, sample_data_dict):
        """Test that CSV output creates a file for each sheet"""
        logger = logging.getLogger("test")

        output_path = write_csv_output(
            sample_data_dict,
            "test_dataview",
            str(tmp_path),
            logger
        )

        # Check all expected CSV files were created
        expected_files = [
            "metadata.csv",
            "data_quality.csv",
            "dataview_details.csv",
            "metrics.csv",
            "dimensions.csv"
        ]

        for expected_file in expected_files:
            file_path = os.path.join(output_path, expected_file)
            assert os.path.exists(file_path), f"Missing file: {expected_file}"

    def test_csv_files_contain_correct_data(self, tmp_path, sample_data_dict):
        """Test that CSV files contain the correct data"""
        logger = logging.getLogger("test")

        output_path = write_csv_output(
            sample_data_dict,
            "test_dataview",
            str(tmp_path),
            logger
        )

        # Read and verify metrics CSV
        metrics_csv = pd.read_csv(os.path.join(output_path, "metrics.csv"))
        assert len(metrics_csv) == len(sample_data_dict['Metrics'])
        assert 'name' in metrics_csv.columns
        assert 'id' in metrics_csv.columns

    def test_csv_handles_special_characters(self, tmp_path):
        """Test that CSV output handles special characters correctly"""
        logger = logging.getLogger("test")

        data_dict = {
            'Test Data': pd.DataFrame([
                {'name': 'Test, with comma', 'value': 'Line\nbreak'},
                {'name': 'Quote "test"', 'value': 'Normal'}
            ])
        }

        output_path = write_csv_output(data_dict, "test", str(tmp_path), logger)

        # Read back and verify
        test_csv = pd.read_csv(os.path.join(output_path, "test_data.csv"))
        assert len(test_csv) == 2
        assert 'Test, with comma' in test_csv['name'].values


class TestJSONOutput:
    """Test JSON output format generation"""

    def test_json_output_creates_file(self, tmp_path, sample_data_dict, sample_metadata_dict):
        """Test that JSON output creates a single JSON file"""
        logger = logging.getLogger("test")

        output_path = write_json_output(
            sample_data_dict,
            sample_metadata_dict,
            "test_dataview",
            str(tmp_path),
            logger
        )

        # Check file was created
        assert os.path.exists(output_path)
        assert output_path.endswith('.json')

    def test_json_has_correct_structure(self, tmp_path, sample_data_dict, sample_metadata_dict):
        """Test that JSON output has the correct hierarchical structure"""
        logger = logging.getLogger("test")

        output_path = write_json_output(
            sample_data_dict,
            sample_metadata_dict,
            "test_dataview",
            str(tmp_path),
            logger
        )

        # Read and parse JSON
        with open(output_path, 'r') as f:
            data = json.load(f)

        # Check top-level structure
        assert 'metadata' in data
        assert 'data_view' in data
        assert 'metrics' in data
        assert 'dimensions' in data
        assert 'data_quality' in data

    def test_json_contains_correct_data(self, tmp_path, sample_data_dict, sample_metadata_dict):
        """Test that JSON contains the correct data"""
        logger = logging.getLogger("test")

        output_path = write_json_output(
            sample_data_dict,
            sample_metadata_dict,
            "test_dataview",
            str(tmp_path),
            logger
        )

        with open(output_path, 'r') as f:
            data = json.load(f)

        # Check metrics
        assert isinstance(data['metrics'], list)
        assert len(data['metrics']) == len(sample_data_dict['Metrics'])

        # Check dimensions
        assert isinstance(data['dimensions'], list)
        assert len(data['dimensions']) == len(sample_data_dict['Dimensions'])

        # Check metadata
        assert isinstance(data['metadata'], dict)

    def test_json_is_valid_json(self, tmp_path, sample_data_dict, sample_metadata_dict):
        """Test that generated JSON is valid and parseable"""
        logger = logging.getLogger("test")

        output_path = write_json_output(
            sample_data_dict,
            sample_metadata_dict,
            "test_dataview",
            str(tmp_path),
            logger
        )

        # Should not raise any exceptions
        with open(output_path, 'r') as f:
            data = json.load(f)

        assert data is not None

    def test_json_handles_null_values(self, tmp_path, sample_metadata_dict):
        """Test that JSON output handles null values correctly"""
        logger = logging.getLogger("test")

        data_dict = {
            'Metrics': pd.DataFrame([
                {'id': '1', 'name': 'Test', 'description': None},
                {'id': '2', 'name': 'Test2', 'description': 'Valid'}
            ])
        }

        output_path = write_json_output(data_dict, sample_metadata_dict, "test", str(tmp_path), logger)

        with open(output_path, 'r') as f:
            data = json.load(f)

        # Null values should be present
        assert data['metrics'][0]['description'] is None
        assert data['metrics'][1]['description'] == 'Valid'


class TestHTMLOutput:
    """Test HTML output format generation"""

    def test_html_output_creates_file(self, tmp_path, sample_data_dict, sample_metadata_dict):
        """Test that HTML output creates a single HTML file"""
        logger = logging.getLogger("test")

        output_path = write_html_output(
            sample_data_dict,
            sample_metadata_dict,
            "test_dataview",
            str(tmp_path),
            logger
        )

        # Check file was created
        assert os.path.exists(output_path)
        assert output_path.endswith('.html')

    def test_html_contains_required_elements(self, tmp_path, sample_data_dict, sample_metadata_dict):
        """Test that HTML contains required HTML elements"""
        logger = logging.getLogger("test")

        output_path = write_html_output(
            sample_data_dict,
            sample_metadata_dict,
            "test_dataview",
            str(tmp_path),
            logger
        )

        with open(output_path, 'r') as f:
            html_content = f.read()

        # Check for HTML structure
        assert '<!DOCTYPE html>' in html_content
        assert '<html' in html_content
        assert '<head>' in html_content
        assert '<body>' in html_content
        assert '</html>' in html_content

    def test_html_includes_css_styling(self, tmp_path, sample_data_dict, sample_metadata_dict):
        """Test that HTML includes CSS styling"""
        logger = logging.getLogger("test")

        output_path = write_html_output(
            sample_data_dict,
            sample_metadata_dict,
            "test_dataview",
            str(tmp_path),
            logger
        )

        with open(output_path, 'r') as f:
            html_content = f.read()

        # Check for CSS
        assert '<style>' in html_content
        assert 'table' in html_content
        assert 'severity-CRITICAL' in html_content  # Severity styling

    def test_html_contains_data_tables(self, tmp_path, sample_data_dict, sample_metadata_dict):
        """Test that HTML contains data tables"""
        logger = logging.getLogger("test")

        output_path = write_html_output(
            sample_data_dict,
            sample_metadata_dict,
            "test_dataview",
            str(tmp_path),
            logger
        )

        with open(output_path, 'r') as f:
            html_content = f.read()

        # Check for table elements
        assert '<table' in html_content
        assert '<thead>' in html_content
        assert '<tbody>' in html_content
        assert '<th>' in html_content
        assert '<td>' in html_content

    def test_html_includes_metadata(self, tmp_path, sample_data_dict, sample_metadata_dict):
        """Test that HTML includes metadata section"""
        logger = logging.getLogger("test")

        output_path = write_html_output(
            sample_data_dict,
            sample_metadata_dict,
            "test_dataview",
            str(tmp_path),
            logger
        )

        with open(output_path, 'r') as f:
            html_content = f.read()

        # Check for metadata
        assert 'Metadata' in html_content or 'metadata' in html_content.lower()

    def test_html_escapes_special_characters(self, tmp_path, sample_metadata_dict):
        """Test that HTML handles special characters in metadata"""
        logger = logging.getLogger("test")

        # Test escaping in metadata section (which we control)
        metadata_dict_with_special = {
            'Test <tag>': 'Value <test>',
            'Normal': 'Value'
        }

        data_dict = {
            'Test Data': pd.DataFrame([
                {'name': 'Test Data', 'value': 'Safe&Sound'}
            ])
        }

        output_path = write_html_output(data_dict, metadata_dict_with_special, "test", str(tmp_path), logger)

        with open(output_path, 'r') as f:
            html_content = f.read()

        # Metadata values should be escaped (we control this)
        assert '&lt;' in html_content and '&gt;' in html_content

    def test_html_severity_styling(self, tmp_path, sample_metadata_dict):
        """Test that HTML applies severity-based styling to data quality issues"""
        logger = logging.getLogger("test")

        data_dict = {
            'Data Quality': pd.DataFrame([
                {'Severity': 'CRITICAL', 'Issue': 'Critical issue', 'Details': 'Test'},
                {'Severity': 'HIGH', 'Issue': 'High issue', 'Details': 'Test'},
                {'Severity': 'MEDIUM', 'Issue': 'Medium issue', 'Details': 'Test'}
            ])
        }

        output_path = write_html_output(data_dict, sample_metadata_dict, "test", str(tmp_path), logger)

        with open(output_path, 'r') as f:
            html_content = f.read()

        # Check for severity class applications
        assert 'severity-CRITICAL' in html_content
        assert 'severity-HIGH' in html_content
        assert 'severity-MEDIUM' in html_content


class TestOutputFormatComparison:
    """Test that all output formats contain equivalent data"""

    def test_all_formats_contain_same_record_counts(self, tmp_path, sample_data_dict, sample_metadata_dict):
        """Test that all formats contain the same number of records"""
        logger = logging.getLogger("test")

        # Generate all formats
        csv_path = write_csv_output(sample_data_dict, "test", str(tmp_path), logger)
        json_path = write_json_output(sample_data_dict, sample_metadata_dict, "test", str(tmp_path), logger)
        html_path = write_html_output(sample_data_dict, sample_metadata_dict, "test", str(tmp_path), logger)

        # Count records in CSV
        metrics_csv = pd.read_csv(os.path.join(csv_path, "metrics.csv"))
        csv_metrics_count = len(metrics_csv)

        # Count records in JSON
        with open(json_path, 'r') as f:
            json_data = json.load(f)
        json_metrics_count = len(json_data['metrics'])

        # HTML should contain the same data (we can't easily count, but verify it exists)
        with open(html_path, 'r') as f:
            html_content = f.read()
        assert 'Metrics' in html_content

        # All should have same count
        assert csv_metrics_count == json_metrics_count
        assert csv_metrics_count == len(sample_data_dict['Metrics'])


class TestEdgeCases:
    """Test edge cases for output format generation"""

    def test_empty_dataframes(self, tmp_path):
        """Test that output formats handle empty DataFrames"""
        logger = logging.getLogger("test")

        data_dict = {
            'Empty': pd.DataFrame()
        }
        metadata_dict = {}

        # CSV should handle empty dataframes
        csv_path = write_csv_output(data_dict, "test", str(tmp_path), logger)
        assert os.path.exists(csv_path)

        # JSON should handle empty dataframes
        json_path = write_json_output(data_dict, metadata_dict, "test", str(tmp_path), logger)
        assert os.path.exists(json_path)

        # HTML should handle empty dataframes
        html_path = write_html_output(data_dict, metadata_dict, "test", str(tmp_path), logger)
        assert os.path.exists(html_path)

    def test_unicode_characters(self, tmp_path):
        """Test that output formats handle Unicode characters"""
        logger = logging.getLogger("test")

        data_dict = {
            'Unicode': pd.DataFrame([
                {'name': '测试数据', 'value': 'Tëst'},
                {'name': 'Тест', 'value': 'مرحبا'}
            ])
        }
        metadata_dict = {'key': '日本語'}

        # All formats should handle Unicode
        csv_path = write_csv_output(data_dict, "test", str(tmp_path), logger)
        json_path = write_json_output(data_dict, metadata_dict, "test", str(tmp_path), logger)
        html_path = write_html_output(data_dict, metadata_dict, "test", str(tmp_path), logger)

        # Verify files were created
        assert os.path.exists(csv_path)
        assert os.path.exists(json_path)
        assert os.path.exists(html_path)

        # Verify Unicode is preserved in JSON
        with open(json_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        assert '日本語' in json_data['metadata'].values()

    def test_large_datasets(self, tmp_path):
        """Test that output formats handle large datasets"""
        logger = logging.getLogger("test")

        # Create large dataset (1000 rows)
        large_df = pd.DataFrame({
            'id': [f'id_{i}' for i in range(1000)],
            'name': [f'Name {i}' for i in range(1000)],
            'value': list(range(1000))
        })

        data_dict = {'LargeData': large_df}
        metadata_dict = {}

        # All formats should handle large datasets
        csv_path = write_csv_output(data_dict, "test", str(tmp_path), logger)
        json_path = write_json_output(data_dict, metadata_dict, "test", str(tmp_path), logger)
        html_path = write_html_output(data_dict, metadata_dict, "test", str(tmp_path), logger)

        # Verify all records are present
        csv_df = pd.read_csv(os.path.join(csv_path, "largedata.csv"))
        assert len(csv_df) == 1000

        with open(json_path, 'r') as f:
            json_data = json.load(f)
        # JSON doesn't have 'LargeData' mapped to a specific key, check it exists somewhere
        assert json_data is not None


class TestMarkdownOutput:
    """Test Markdown output format generation"""

    def test_markdown_output_creates_file(self, tmp_path, sample_data_dict, sample_metadata_dict):
        """Test that Markdown output creates a file"""
        logger = logging.getLogger("test")

        output_path = write_markdown_output(
            sample_data_dict,
            sample_metadata_dict,
            "test_dataview",
            str(tmp_path),
            logger
        )

        # Check file was created
        assert os.path.exists(output_path)
        assert output_path.endswith('.md')

    def test_markdown_has_correct_structure(self, tmp_path, sample_data_dict, sample_metadata_dict):
        """Test that Markdown output has required sections"""
        logger = logging.getLogger("test")

        output_path = write_markdown_output(
            sample_data_dict,
            sample_metadata_dict,
            "test_dataview",
            str(tmp_path),
            logger
        )

        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for required sections
        assert '# 📊 CJA Solution Design Reference' in content
        assert '## 📋 Metadata' in content
        assert '## 📑 Table of Contents' in content
        assert '## Metrics' in content
        assert '## Dimensions' in content
        assert '## Data Quality' in content

    def test_markdown_tables_properly_formatted(self, tmp_path, sample_data_dict, sample_metadata_dict):
        """Test that Markdown tables are properly formatted"""
        logger = logging.getLogger("test")

        output_path = write_markdown_output(
            sample_data_dict,
            sample_metadata_dict,
            "test_dataview",
            str(tmp_path),
            logger
        )

        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for table structure (pipe separated)
        assert '|' in content
        assert '| ---' in content  # Table separator
        assert '| name |' in content or '| id |' in content

    def test_markdown_escapes_special_characters(self, tmp_path):
        """Test that Markdown escapes pipe characters and backticks"""
        logger = logging.getLogger("test")

        data_dict = {
            'Test Data': pd.DataFrame([
                {'name': 'Test | with pipe', 'value': 'Has `backtick`'},
                {'name': 'Normal', 'value': 'Normal'}
            ])
        }
        metadata_dict = {'key': 'value'}

        output_path = write_markdown_output(data_dict, metadata_dict, "test", str(tmp_path), logger)

        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check that special characters are escaped
        assert '\\|' in content  # Escaped pipe
        assert '\\`' in content  # Escaped backtick

    def test_markdown_issue_summary(self, tmp_path, sample_data_dict, sample_metadata_dict):
        """Test that Data Quality section includes issue summary"""
        logger = logging.getLogger("test")

        output_path = write_markdown_output(
            sample_data_dict,
            sample_metadata_dict,
            "test_dataview",
            str(tmp_path),
            logger
        )

        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for issue summary with severity counts
        assert '### Issue Summary' in content
        assert '| Severity | Count |' in content
        # Should have severity emojis
        assert any(emoji in content for emoji in ['🔴', '🟠', '🟡', '⚪', '🔵'])

    def test_markdown_collapsible_sections(self, tmp_path):
        """Test that large tables use collapsible sections"""
        logger = logging.getLogger("test")

        # Create large dataset (>50 rows)
        large_df = pd.DataFrame({
            'id': [f'id_{i}' for i in range(100)],
            'name': [f'Name {i}' for i in range(100)]
        })

        data_dict = {'Large Table': large_df}
        metadata_dict = {}

        output_path = write_markdown_output(data_dict, metadata_dict, "test", str(tmp_path), logger)

        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for collapsible sections
        assert '<details>' in content
        assert '<summary>View 100 rows (click to expand)</summary>' in content
        assert '</details>' in content

    def test_markdown_small_tables_not_collapsed(self, tmp_path, sample_data_dict, sample_metadata_dict):
        """Test that small tables are not collapsed"""
        logger = logging.getLogger("test")

        output_path = write_markdown_output(
            sample_data_dict,
            sample_metadata_dict,
            "test_dataview",
            str(tmp_path),
            logger
        )

        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Metrics and Dimensions should be small (2-3 rows), so shouldn't be collapsed
        # Check that they exist in content but not within details tags
        lines = content.split('\n')
        in_metrics_section = False
        found_metrics_table = False

        for i, line in enumerate(lines):
            if '## Metrics' in line:
                in_metrics_section = True
            elif in_metrics_section and '| id |' in line:
                found_metrics_table = True
                # Check nearby lines don't have <details>
                context = '\n'.join(lines[max(0,i-5):min(len(lines),i+10)])
                assert '<details>' not in context
                break

        assert found_metrics_table, "Metrics table not found in markdown output"

    def test_markdown_handles_unicode(self, tmp_path):
        """Test that Markdown handles Unicode characters"""
        logger = logging.getLogger("test")

        data_dict = {
            'Unicode': pd.DataFrame([
                {'name': '测试数据', 'value': 'Tëst'},
                {'name': 'Тест', 'value': 'مرحبا'}
            ])
        }
        metadata_dict = {'key': '日本語'}

        output_path = write_markdown_output(data_dict, metadata_dict, "test", str(tmp_path), logger)

        # Verify file was created and can be read
        assert os.path.exists(output_path)

        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Verify Unicode is preserved
        assert '测试数据' in content
        assert '日本語' in content

    def test_markdown_handles_empty_dataframes(self, tmp_path):
        """Test that Markdown handles empty DataFrames"""
        logger = logging.getLogger("test")

        data_dict = {
            'Empty Table': pd.DataFrame()
        }
        metadata_dict = {}

        output_path = write_markdown_output(data_dict, metadata_dict, "test", str(tmp_path), logger)

        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for empty table message
        assert '*No empty table found.*' in content or '*no empty table found.*' in content

    def test_markdown_table_of_contents_links(self, tmp_path, sample_data_dict, sample_metadata_dict):
        """Test that table of contents has working anchor links"""
        logger = logging.getLogger("test")

        output_path = write_markdown_output(
            sample_data_dict,
            sample_metadata_dict,
            "test_dataview",
            str(tmp_path),
            logger
        )

        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for TOC links
        assert '[Metrics](#metrics)' in content
        assert '[Dimensions](#dimensions)' in content
        assert '[Data Quality](#data-quality)' in content

    def test_markdown_footer(self, tmp_path, sample_data_dict, sample_metadata_dict):
        """Test that Markdown includes footer"""
        logger = logging.getLogger("test")

        output_path = write_markdown_output(
            sample_data_dict,
            sample_metadata_dict,
            "test_dataview",
            str(tmp_path),
            logger
        )

        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for footer
        assert '*Generated by CJA Auto SDR Generator*' in content

    def test_markdown_row_counts(self, tmp_path, sample_data_dict, sample_metadata_dict):
        """Test that Markdown shows row counts for each section"""
        logger = logging.getLogger("test")

        output_path = write_markdown_output(
            sample_data_dict,
            sample_metadata_dict,
            "test_dataview",
            str(tmp_path),
            logger
        )

        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()

        # Check for count messages
        assert '*Total Metrics: 2 items*' in content
        assert '*Total Dimensions: 3 items*' in content
