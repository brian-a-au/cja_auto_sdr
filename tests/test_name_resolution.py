"""Tests for data view name resolution functionality"""

import logging
import os
import sys
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

# Import the functions we're testing
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cja_auto_sdr.generator import NameResolutionDiagnostics, _data_view_cache, is_data_view_id, resolve_data_view_names


class TestDataViewIDDetection:
    """Test data view ID vs name detection"""

    def test_is_data_view_id_with_valid_id(self):
        """Test that valid data view IDs are detected"""
        assert is_data_view_id("dv_12345") is True
        assert is_data_view_id("dv_abc123def456") is True
        assert is_data_view_id("dv_677ea9291244fd082f02dd42") is True

    def test_is_data_view_id_with_name(self):
        """Test that names are not detected as IDs"""
        assert is_data_view_id("Production Analytics") is False
        assert is_data_view_id("Test Environment") is False
        assert is_data_view_id("my-dataview") is False
        assert is_data_view_id("dataview_123") is False  # Doesn't start with 'dv_'

    def test_is_data_view_id_with_edge_cases(self):
        """Test edge cases"""
        assert is_data_view_id("") is False
        assert is_data_view_id("dv") is False  # Too short
        assert is_data_view_id("DV_12345") is False  # Wrong case


class TestDataViewNameResolution:
    """Test data view name to ID resolution"""

    def setup_method(self):
        """Set up test fixtures"""
        self.logger = logging.getLogger("test")
        self.logger.setLevel(logging.DEBUG)

        # Clear the cache to ensure tests are isolated
        _data_view_cache.clear()

        # Unit tests in this module mock cjapy interactions and should not depend
        # on environment/config credential availability.
        self._configure_patch = patch(
            "cja_auto_sdr.generator.configure_cjapy",
            return_value=(True, "mock", None),
        )
        self._configure_patch.start()

        # Mock data views
        self.mock_dataviews = [
            {"id": "dv_prod123", "name": "Production Analytics"},
            {"id": "dv_test456", "name": "Test Environment"},
            {"id": "dv_stage789", "name": "Staging"},
            {"id": "dv_dup001", "name": "Duplicate Name"},
            {"id": "dv_dup002", "name": "Duplicate Name"},  # Intentional duplicate
            {"id": "dv_dup003", "name": "Duplicate Name"},  # Three with same name
        ]

    def teardown_method(self):
        """Clean up test patches."""
        self._configure_patch.stop()

    @patch("cja_auto_sdr.generator.cjapy")
    def test_resolve_single_id(self, mock_cjapy):
        """Test resolving a single data view ID (should pass through)"""
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = self.mock_dataviews
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(["dv_prod123"], "config.json", self.logger)

        assert ids == ["dv_prod123"]
        assert name_map == {}  # No name resolution needed

    @patch("cja_auto_sdr.generator.cjapy")
    def test_resolve_single_name(self, mock_cjapy):
        """Test resolving a single data view name"""
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = self.mock_dataviews
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(["Production Analytics"], "config.json", self.logger)

        assert ids == ["dv_prod123"]
        assert name_map == {"Production Analytics": ["dv_prod123"]}

    @patch("cja_auto_sdr.generator.cjapy")
    def test_resolve_duplicate_name(self, mock_cjapy):
        """Test resolving a name that matches multiple data views"""
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = self.mock_dataviews
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(["Duplicate Name"], "config.json", self.logger)

        assert len(ids) == 3
        assert set(ids) == {"dv_dup001", "dv_dup002", "dv_dup003"}
        assert "Duplicate Name" in name_map
        assert len(name_map["Duplicate Name"]) == 3

    @patch("cja_auto_sdr.generator.cjapy")
    def test_resolve_mixed_ids_and_names(self, mock_cjapy):
        """Test resolving a mix of IDs and names"""
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = self.mock_dataviews
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(
            ["dv_prod123", "Test Environment", "dv_stage789"],
            "config.json",
            self.logger,
        )

        assert len(ids) == 3
        assert "dv_prod123" in ids
        assert "dv_test456" in ids
        assert "dv_stage789" in ids
        assert name_map == {"Test Environment": ["dv_test456"]}

    @patch("cja_auto_sdr.generator.cjapy")
    def test_resolve_nonexistent_name(self, mock_cjapy):
        """Test resolving a name that doesn't exist"""
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = self.mock_dataviews
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(["Nonexistent View"], "config.json", self.logger)

        assert ids == []  # Name not found, not added to results
        assert name_map == {}

    @patch("cja_auto_sdr.generator.cjapy")
    def test_resolve_nonexistent_id(self, mock_cjapy):
        """Test resolving an ID that doesn't exist (should still pass through with warning)"""
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = self.mock_dataviews
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(["dv_nonexistent"], "config.json", self.logger)

        # ID not found but still added - will fail during processing
        assert ids == ["dv_nonexistent"]
        assert name_map == {}

    @patch("cja_auto_sdr.generator.cjapy")
    def test_resolve_with_dataframe_response(self, mock_cjapy):
        """Test resolving when API returns a DataFrame"""
        mock_cja_instance = MagicMock()
        mock_df = pd.DataFrame(self.mock_dataviews)
        mock_cja_instance.getDataViews.return_value = mock_df
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(["Production Analytics"], "config.json", self.logger)

        assert ids == ["dv_prod123"]
        assert name_map == {"Production Analytics": ["dv_prod123"]}

    @patch("cja_auto_sdr.generator.cjapy")
    def test_cache_isolated_by_credential_context(self, mock_cjapy):
        """Cache should not leak data views across different credential contexts."""
        mock_cja_profile_a = MagicMock()
        mock_cja_profile_a.getDataViews.return_value = [{"id": "dv_alpha", "name": "Alpha View"}]

        mock_cja_profile_b = MagicMock()
        mock_cja_profile_b.getDataViews.return_value = [{"id": "dv_beta", "name": "Beta View"}]

        mock_cjapy.CJA.side_effect = [mock_cja_profile_a, mock_cja_profile_b]
        mock_cjapy.importConfigFile.return_value = None

        with patch(
            "cja_auto_sdr.generator.configure_cjapy",
            side_effect=[
                (
                    True,
                    "Profile: alpha",
                    {
                        "org_id": "alpha@AdobeOrg",
                        "client_id": "alpha_client_1234567890",
                        "secret": "alpha_secret_1234567890",
                    },
                ),
                (
                    True,
                    "Profile: beta",
                    {
                        "org_id": "beta@AdobeOrg",
                        "client_id": "beta_client_1234567890",
                        "secret": "beta_secret_1234567890",
                    },
                ),
            ],
        ):
            ids_a, _ = resolve_data_view_names(["Alpha View"], "config.json", self.logger, profile="alpha")
            ids_b, _ = resolve_data_view_names(["Beta View"], "config.json", self.logger, profile="beta")

        assert ids_a == ["dv_alpha"]
        assert ids_b == ["dv_beta"]
        assert mock_cja_profile_a.getDataViews.call_count == 1
        assert mock_cja_profile_b.getDataViews.call_count == 1

    @patch("cja_auto_sdr.generator.cjapy")
    def test_resolve_with_empty_response(self, mock_cjapy):
        """Test resolving when no data views are available"""
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = []
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(["Production Analytics"], "config.json", self.logger)

        assert ids == []
        assert name_map == {}

    @patch("cja_auto_sdr.generator.cjapy")
    def test_resolve_with_none_response(self, mock_cjapy):
        """Test resolving when API returns None"""
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = None
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(["Production Analytics"], "config.json", self.logger)

        assert ids == []
        assert name_map == {}

    @patch("cja_auto_sdr.generator.cjapy")
    def test_resolve_with_config_error(self, mock_cjapy):
        """Test resolving when config file is not found"""
        mock_cjapy.importConfigFile.side_effect = FileNotFoundError("Config not found")

        ids, name_map = resolve_data_view_names(["Production Analytics"], "config.json", self.logger)

        assert ids == []
        assert name_map == {}

    @patch("cja_auto_sdr.generator.cjapy")
    def test_resolve_with_api_error(self, mock_cjapy):
        """Test resolving when API call fails"""
        from cja_auto_sdr.core.exceptions import APIError

        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.side_effect = APIError("API error")
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(["Production Analytics"], "config.json", self.logger)

        assert ids == []
        assert name_map == {}

    @patch("cja_auto_sdr.generator.cjapy")
    def test_resolve_with_unexpected_exception(self, mock_cjapy):
        """RuntimeError from cjapy bootstrap should return controlled failure."""
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.side_effect = RuntimeError("unexpected auth failure")
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(["Production Analytics"], "config.json", self.logger)

        assert ids == []
        assert name_map == {}

    @patch("cja_auto_sdr.generator.cjapy")
    def test_resolve_with_runtime_error(self, mock_cjapy):
        """RuntimeError from client plumbing should return controlled failure."""
        mock_cjapy.CJA.side_effect = RuntimeError("bootstrap failed")
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(["Test DV"], "config.json", self.logger)

        assert ids == []
        assert name_map == {}

    @patch("cja_auto_sdr.generator.cjapy")
    def test_resolve_case_sensitive(self, mock_cjapy):
        """Test that name resolution is case-sensitive"""
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = self.mock_dataviews
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        # Exact case match
        ids1, _ = resolve_data_view_names(["Production Analytics"], "config.json", self.logger)
        assert len(ids1) == 1

        # Different case - should not match
        ids2, _ = resolve_data_view_names(["production analytics"], "config.json", self.logger)
        assert len(ids2) == 0

        # Another case variation
        ids3, _ = resolve_data_view_names(["PRODUCTION ANALYTICS"], "config.json", self.logger)
        assert len(ids3) == 0

    @patch("cja_auto_sdr.generator.cjapy")
    def test_resolve_case_insensitive_mode(self, mock_cjapy):
        """Test case-insensitive mode resolves mismatched case names."""
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = self.mock_dataviews
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(
            ["production analytics"],
            "config.json",
            self.logger,
            match_mode="insensitive",
        )

        assert ids == ["dv_prod123"]
        assert name_map == {"production analytics": ["dv_prod123"]}

    @patch("cja_auto_sdr.generator.cjapy")
    def test_resolve_fuzzy_mode(self, mock_cjapy):
        """Test fuzzy mode resolves near matches."""
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = self.mock_dataviews
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(
            ["Production Analytic"],
            "config.json",
            self.logger,
            match_mode="fuzzy",
        )

        assert ids == ["dv_prod123"]
        assert name_map == {"Production Analytic": ["dv_prod123"]}

    @patch("cja_auto_sdr.generator.cjapy")
    def test_resolve_include_diagnostics_exposes_canonical_name_map(self, mock_cjapy):
        """Diagnostics should expose canonical names keyed by resolved data view ID."""
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = self.mock_dataviews
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map, diagnostics = resolve_data_view_names(
            ["production analytics"],
            "config.json",
            self.logger,
            match_mode="insensitive",
            include_diagnostics=True,
        )

        assert ids == ["dv_prod123"]
        assert name_map == {"production analytics": ["dv_prod123"]}
        assert isinstance(diagnostics, NameResolutionDiagnostics)
        assert diagnostics.error_type is None
        assert diagnostics.error_message is None
        assert diagnostics.resolved_name_by_id == {"dv_prod123": "Production Analytics"}

    @patch("cja_auto_sdr.generator.cjapy")
    def test_resolve_include_diagnostics_returns_empty_name_map_for_unknown_id(self, mock_cjapy):
        """IDs not present in accessible views should not produce canonical-name mappings."""
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = self.mock_dataviews
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map, diagnostics = resolve_data_view_names(
            ["dv_unknown"],
            "config.json",
            self.logger,
            include_diagnostics=True,
        )

        assert ids == ["dv_unknown"]
        assert name_map == {}
        assert isinstance(diagnostics, NameResolutionDiagnostics)
        assert diagnostics.resolved_name_by_id == {}

    def test_resolve_invalid_match_mode(self):
        """Invalid match mode should raise ValueError."""
        with pytest.raises(ValueError):
            resolve_data_view_names(["Production Analytics"], "config.json", self.logger, match_mode="invalid")

    @patch("cja_auto_sdr.generator.cjapy")
    def test_resolve_multiple_names_all_duplicate(self, mock_cjapy):
        """Test resolving multiple names where all have duplicates"""
        mock_dataviews_multi = [
            {"id": "dv_a1", "name": "View A"},
            {"id": "dv_a2", "name": "View A"},
            {"id": "dv_b1", "name": "View B"},
            {"id": "dv_b2", "name": "View B"},
        ]
        mock_cja_instance = MagicMock()
        mock_cja_instance.getDataViews.return_value = mock_dataviews_multi
        mock_cjapy.CJA.return_value = mock_cja_instance
        mock_cjapy.importConfigFile.return_value = None

        ids, name_map = resolve_data_view_names(["View A", "View B"], "config.json", self.logger)

        assert len(ids) == 4
        assert set(ids) == {"dv_a1", "dv_a2", "dv_b1", "dv_b2"}
        assert len(name_map["View A"]) == 2
        assert len(name_map["View B"]) == 2


class TestNameResolutionLogFormat:
    """Name-resolution log records follow the resolved --log-format."""

    @pytest.fixture(autouse=True)
    def _reset_name_resolution_logger(self):
        resolution_logger = logging.getLogger("name_resolution")
        resolution_logger.handlers.clear()
        yield
        resolution_logger.handlers.clear()

    @pytest.mark.parametrize("argv", [["X", "--log-format", "json"], ["X", "--agent-mode"]])
    def test_name_resolution_logger_uses_json_formatter_for_json_log_format(self, argv, capsys):
        import json

        from cja_auto_sdr import generator

        def fake_resolve(identifiers, config_file, logger, **kwargs):
            logger.error("Data view name 'X' not found")
            return [], {}

        with (
            patch("sys.argv", ["cja_auto_sdr", *argv]),
            patch("cja_auto_sdr.generator.resolve_data_view_names", side_effect=fake_resolve),
            pytest.raises(SystemExit),
        ):
            generator.main()

        lines = [line for line in capsys.readouterr().err.splitlines() if "not found" in line]
        assert lines
        record = json.loads(lines[0])
        assert record["level"] == "ERROR"

    def test_name_resolution_logger_keeps_text_format_by_default(self, capsys):
        from cja_auto_sdr import generator

        def fake_resolve(identifiers, config_file, logger, **kwargs):
            logger.error("Data view name 'X' not found")
            return [], {}

        with (
            patch("sys.argv", ["cja_auto_sdr", "X"]),
            patch("cja_auto_sdr.generator.resolve_data_view_names", side_effect=fake_resolve),
            pytest.raises(SystemExit),
        ):
            generator.main()

        assert "ERROR - Data view name 'X' not found" in capsys.readouterr().err
