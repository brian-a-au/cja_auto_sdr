"""Tests for data view name resolution functionality"""
import pytest
import sys
import os
import logging
from unittest.mock import patch, MagicMock
import pandas as pd


# Import the functions we're testing
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cja_sdr_generator import is_data_view_id, resolve_data_view_names, _data_view_cache


class TestDataViewIDDetection:
    """Test data view ID vs name detection"""

    def test_is_data_view_id_with_valid_id(self):
        """Test that valid data view IDs are detected"""
        assert is_data_view_id('dv_12345') is True
        assert is_data_view_id('dv_abc123def456') is True
        assert is_data_view_id('dv_677ea9291244fd082f02dd42') is True

    def test_is_data_view_id_with_name(self):
        """Test that names are not detected as IDs"""
        assert is_data_view_id('Production Analytics') is False
        assert is_data_view_id('Test Environment') is False
        assert is_data_view_id('my-dataview') is False
        assert is_data_view_id('dataview_123') is False  # Doesn't start with 'dv_'

    def test_is_data_view_id_with_edge_cases(self):
        """Test edge cases"""
        assert is_data_view_id('') is False
        assert is_data_view_id('dv') is False  # Too short
        assert is_data_view_id('DV_12345') is False  # Wrong case


class TestDataViewNameResolution:
    """Test data view name to ID resolution"""

    def setup_method(self):
        """Set up test fixtures"""
        self.logger = logging.getLogger('test')
        self.logger.setLevel(logging.DEBUG)

        # Clear the cache to ensure tests are isolated
        _data_view_cache.clear()

        # Mock data views
        self.mock_dataviews = [
            {'id': 'dv_prod123', 'name': 'Production Analytics'},
            {'id': 'dv_test456', 'name': 'Test Environment'},
            {'id': 'dv_stage789', 'name': 'Staging'},
            {'id': 'dv_dup001', 'name': 'Duplicate Name'},
            {'id': 'dv_dup002', 'name': 'Duplicate Name'},  # Intentional duplicate
            {'id': 'dv_dup003', 'name': 'Duplicate Name'},  # Three with same name
        ]

    @patch('cja_sdr_generator.cjapy')
    def test_resolve_single_id(self, mock_cjapy):
        """Test resolving a single data view ID (should pass through)"""
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = self.mock_dataviews
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(['dv_prod123'], 'config.json', self.logger)

        assert ids == ['dv_prod123']
        assert name_map == {}  # No name resolution needed

    @patch('cja_sdr_generator.cjapy')
    def test_resolve_single_name(self, mock_cjapy):
        """Test resolving a single data view name"""
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = self.mock_dataviews
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(['Production Analytics'], 'config.json', self.logger)

        assert ids == ['dv_prod123']
        assert name_map == {'Production Analytics': ['dv_prod123']}

    @patch('cja_sdr_generator.cjapy')
    def test_resolve_duplicate_name(self, mock_cjapy):
        """Test resolving a name that matches multiple data views"""
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = self.mock_dataviews
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(['Duplicate Name'], 'config.json', self.logger)

        assert len(ids) == 3
        assert set(ids) == {'dv_dup001', 'dv_dup002', 'dv_dup003'}
        assert 'Duplicate Name' in name_map
        assert len(name_map['Duplicate Name']) == 3

    @patch('cja_sdr_generator.cjapy')
    def test_resolve_mixed_ids_and_names(self, mock_cjapy):
        """Test resolving a mix of IDs and names"""
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = self.mock_dataviews
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(
            ['dv_prod123', 'Test Environment', 'dv_stage789'],
            'config.json',
            self.logger
        )

        assert len(ids) == 3
        assert 'dv_prod123' in ids
        assert 'dv_test456' in ids
        assert 'dv_stage789' in ids
        assert name_map == {'Test Environment': ['dv_test456']}

    @patch('cja_sdr_generator.cjapy')
    def test_resolve_nonexistent_name(self, mock_cjapy):
        """Test resolving a name that doesn't exist"""
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = self.mock_dataviews
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(['Nonexistent View'], 'config.json', self.logger)

        assert ids == []  # Name not found, not added to results
        assert name_map == {}

    @patch('cja_sdr_generator.cjapy')
    def test_resolve_nonexistent_id(self, mock_cjapy):
        """Test resolving an ID that doesn't exist (should still pass through with warning)"""
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = self.mock_dataviews
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(['dv_nonexistent'], 'config.json', self.logger)

        # ID not found but still added - will fail during processing
        assert ids == ['dv_nonexistent']
        assert name_map == {}

    @patch('cja_sdr_generator.cjapy')
    def test_resolve_with_dataframe_response(self, mock_cjapy):
        """Test resolving when API returns a DataFrame"""
        mock_cja_instance = MagicMock()
        mock_df = pd.DataFrame(self.mock_dataviews)
        mock_cja_instance.getDataViews.return_value = mock_df
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(['Production Analytics'], 'config.json', self.logger)

        assert ids == ['dv_prod123']
        assert name_map == {'Production Analytics': ['dv_prod123']}

    @patch('cja_sdr_generator.cjapy')
    def test_resolve_with_empty_response(self, mock_cjapy):
        """Test resolving when no data views are available"""
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = []
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(['Production Analytics'], 'config.json', self.logger)

        assert ids == []
        assert name_map == {}

    @patch('cja_sdr_generator.cjapy')
    def test_resolve_with_none_response(self, mock_cjapy):
        """Test resolving when API returns None"""
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = None
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(['Production Analytics'], 'config.json', self.logger)

        assert ids == []
        assert name_map == {}

    @patch('cja_sdr_generator.cjapy')
    def test_resolve_with_config_error(self, mock_cjapy):
        """Test resolving when config file is not found"""
        mock_cjapy.importConfigFile.side_effect = FileNotFoundError("Config not found")

        ids, name_map = resolve_data_view_names(['Production Analytics'], 'config.json', self.logger)

        assert ids == []
        assert name_map == {}

    @patch('cja_sdr_generator.cjapy')
    def test_resolve_with_api_error(self, mock_cjapy):
        """Test resolving when API call fails"""
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.side_effect = Exception("API error")
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(['Production Analytics'], 'config.json', self.logger)

        assert ids == []
        assert name_map == {}

    @patch('cja_sdr_generator.cjapy')
    def test_resolve_case_sensitive(self, mock_cjapy):
        """Test that name resolution is case-sensitive"""
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = self.mock_dataviews
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        # Exact case match
        ids1, _ = resolve_data_view_names(['Production Analytics'], 'config.json', self.logger)
        assert len(ids1) == 1

        # Different case - should not match
        ids2, _ = resolve_data_view_names(['production analytics'], 'config.json', self.logger)
        assert len(ids2) == 0

        # Another case variation
        ids3, _ = resolve_data_view_names(['PRODUCTION ANALYTICS'], 'config.json', self.logger)
        assert len(ids3) == 0

    @patch('cja_sdr_generator.cjapy')
    def test_resolve_multiple_names_all_duplicate(self, mock_cjapy):
        """Test resolving multiple names where all have duplicates"""
        mock_dataviews_multi = [
            {'id': 'dv_a1', 'name': 'View A'},
            {'id': 'dv_a2', 'name': 'View A'},
            {'id': 'dv_b1', 'name': 'View B'},
            {'id': 'dv_b2', 'name': 'View B'},
        ]
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = mock_dataviews_multi
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(['View A', 'View B'], 'config.json', self.logger)

        assert len(ids) == 4
        assert set(ids) == {'dv_a1', 'dv_a2', 'dv_b1', 'dv_b2'}
        assert len(name_map['View A']) == 2
        assert len(name_map['View B']) == 2
