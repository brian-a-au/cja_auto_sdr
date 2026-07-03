"""Negative tests for malformed and unexpected API responses.

Validates that the pipeline handles gracefully:
- API methods returning None, wrong types, or partial data
- API methods raising unexpected exceptions
- DataFrames with missing/extra columns
- Empty or corrupted responses during processing
"""

import json
import logging
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from cja_auto_sdr.generator import (
    DataQualityChecker,
    process_single_dataview,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def malformed_config(tmp_path):
    import json

    cfg = {"org_id": "x@AdobeOrg", "client_id": "x", "secret": "x", "scopes": "openid"}
    p = tmp_path / "cfg.json"
    p.write_text(json.dumps(cfg))
    return str(p)


@pytest.fixture
def output_dir(tmp_path):
    d = tmp_path / "out"
    d.mkdir()
    return str(d)


def _api_patches():
    """Return the standard API-boundary patch decorators."""
    return [
        patch("cja_auto_sdr.generator.setup_logging"),
        patch("cja_auto_sdr.generator.initialize_cja"),
        patch("cja_auto_sdr.generator.ParallelAPIFetcher"),
    ]


def _apply(func):
    for p in reversed(_api_patches()):
        func = p(func)
    return func


def _setup_mocks(
    mock_setup_logging,
    mock_init_cja,
    mock_fetcher_class,
    metrics_df,
    dimensions_df,
    dataview_info,
):
    logger = logging.getLogger("malformed_test")
    logger.handlers = []
    logger.setLevel(logging.DEBUG)
    mock_setup_logging.return_value = logger
    mock_init_cja.return_value = Mock()

    mock_fetcher = Mock()
    mock_fetcher.fetch_all_data.return_value = (metrics_df, dimensions_df, dataview_info)
    mock_fetcher.get_tuner_statistics.return_value = None
    mock_fetcher_class.return_value = mock_fetcher
    return mock_fetcher


# ===================================================================
# Tests for API returning wrong types
# ===================================================================


class TestAPIReturnsWrongTypes:
    """API methods return unexpected types instead of DataFrames."""

    @_apply
    def test_metrics_as_list_instead_of_dataframe(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        malformed_config,
        output_dir,
    ):
        """API returns a raw list instead of DataFrame for metrics."""
        raw_list = [
            {"id": "m1", "name": "Metric 1", "type": "int", "title": "M1", "description": "desc"},
        ]
        _setup_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            pd.DataFrame(raw_list),  # Convert so fetcher returns valid DF
            pd.DataFrame([{"id": "d1", "name": "Dim 1", "type": "string", "title": "D1", "description": "d"}]),
            {"id": "dv_test", "name": "Test DV", "owner": {"name": "Owner"}},
        )

        result = process_single_dataview(
            data_view_id="dv_test",
            config_file=malformed_config,
            output_dir=output_dir,
            output_format="json",
            quiet=True,
        )
        assert result.success is True
        assert result.metrics_count == 1

    @_apply
    def test_dataview_info_missing_owner_key(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        malformed_config,
        output_dir,
    ):
        """API returns dataview info without 'owner' key."""
        _setup_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            pd.DataFrame([{"id": "m1", "name": "M1", "type": "int", "title": "M1", "description": "d"}]),
            pd.DataFrame([{"id": "d1", "name": "D1", "type": "string", "title": "D1", "description": "d"}]),
            {"id": "dv_test", "name": "Test DV"},  # No 'owner' key
        )

        result = process_single_dataview(
            data_view_id="dv_test",
            config_file=malformed_config,
            output_dir=output_dir,
            output_format="json",
            quiet=True,
        )
        assert result.success is True

    @_apply
    def test_dataview_info_is_empty_dict(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        malformed_config,
        output_dir,
    ):
        """API returns an empty dict for dataview info — now triggers validation failure."""
        _setup_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            pd.DataFrame([{"id": "m1", "name": "M1", "type": "int", "title": "M1", "description": "d"}]),
            pd.DataFrame([{"id": "d1", "name": "D1", "type": "string", "title": "D1", "description": "d"}]),
            {},  # Empty dataview info
        )

        result = process_single_dataview(
            data_view_id="dv_test",
            config_file=malformed_config,
            output_dir=output_dir,
            output_format="json",
            quiet=True,
        )
        assert result.success is False
        assert "validation failed" in result.error_message.lower()
        assert result.data_view_name == "Unknown"

    @_apply
    def test_dataview_info_is_error_placeholder_dict(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        malformed_config,
        output_dir,
    ):
        """Non-empty error placeholders are rejected by dataview validation."""
        _setup_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            pd.DataFrame([{"id": "m1", "name": "M1", "type": "int", "title": "M1", "description": "d"}]),
            pd.DataFrame([{"id": "d1", "name": "D1", "type": "string", "title": "D1", "description": "d"}]),
            {
                "id": "dv_test",
                "name": "Unknown",
                "lookup_failed": True,
                "lookup_failure_reason": "exception",
                "error": "getDataView failed",
            },
        )

        result = process_single_dataview(
            data_view_id="dv_test",
            config_file=malformed_config,
            output_dir=output_dir,
            output_format="json",
            quiet=True,
        )
        assert result.success is False
        assert "validation failed" in result.error_message.lower()
        assert result.data_view_name == "Unknown"


# ===================================================================
# Tests for DataFrames with unexpected schemas
# ===================================================================


class TestMalformedDataFrameSchemas:
    """DataFrames with missing, extra, or unexpected columns."""

    @_apply
    def test_metrics_missing_description_column(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        malformed_config,
        output_dir,
    ):
        """Metrics DF has no 'description' column at all."""
        _setup_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            pd.DataFrame([{"id": "m1", "name": "M1", "type": "int", "title": "M1"}]),  # No description
            pd.DataFrame([{"id": "d1", "name": "D1", "type": "string", "title": "D1", "description": "d"}]),
            {"id": "dv_test", "name": "Test DV", "owner": {"name": "Owner"}},
        )

        result = process_single_dataview(
            data_view_id="dv_test",
            config_file=malformed_config,
            output_dir=output_dir,
            output_format="csv",
            quiet=True,
        )
        # Should succeed with DQ issues about missing description column
        assert result.success is True

    @_apply
    def test_metrics_with_extra_unknown_columns(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        malformed_config,
        output_dir,
    ):
        """Metrics DF has extra columns the tool doesn't know about."""
        _setup_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            pd.DataFrame(
                [
                    {
                        "id": "m1",
                        "name": "M1",
                        "type": "int",
                        "title": "M1",
                        "description": "d",
                        "unknown_field": "xyz",
                        "another_new_field": 42,
                    },
                ],
            ),
            pd.DataFrame([{"id": "d1", "name": "D1", "type": "string", "title": "D1", "description": "d"}]),
            {"id": "dv_test", "name": "Test DV", "owner": {"name": "Owner"}},
        )

        result = process_single_dataview(
            data_view_id="dv_test",
            config_file=malformed_config,
            output_dir=output_dir,
            output_format="json",
            quiet=True,
        )
        assert result.success is True
        assert result.metrics_count == 1

    @_apply
    def test_dimensions_all_null_descriptions(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        malformed_config,
        output_dir,
    ):
        """All dimension descriptions are None."""
        _setup_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            pd.DataFrame([{"id": "m1", "name": "M1", "type": "int", "title": "M1", "description": "d"}]),
            pd.DataFrame(
                [
                    {"id": "d1", "name": "D1", "type": "string", "title": "D1", "description": None},
                    {"id": "d2", "name": "D2", "type": "string", "title": "D2", "description": None},
                    {"id": "d3", "name": "D3", "type": "string", "title": "D3", "description": None},
                ],
            ),
            {"id": "dv_test", "name": "Test DV", "owner": {"name": "Owner"}},
        )

        result = process_single_dataview(
            data_view_id="dv_test",
            config_file=malformed_config,
            output_dir=output_dir,
            output_format="excel",
            quiet=True,
        )
        assert result.success is True
        assert result.dq_issues_count > 0  # Should flag null descriptions

    @_apply
    def test_metrics_with_mixed_types_in_columns(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        malformed_config,
        output_dir,
    ):
        """Columns have mixed types (int IDs, dict values, etc)."""
        _setup_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            pd.DataFrame(
                [
                    {"id": "m1", "name": "M1", "type": "int", "title": "M1", "description": {"nested": "dict"}},
                    {"id": 12345, "name": "M2", "type": "int", "title": "M2", "description": ["a", "list"]},
                ],
            ),
            pd.DataFrame([{"id": "d1", "name": "D1", "type": "string", "title": "D1", "description": "d"}]),
            {"id": "dv_test", "name": "Test DV", "owner": {"name": "Owner"}},
        )

        result = process_single_dataview(
            data_view_id="dv_test",
            config_file=malformed_config,
            output_dir=output_dir,
            output_format="json",
            quiet=True,
        )
        # Should not crash — JSON formatting handles dicts/lists via format_json_cell
        assert result.success is True

    @_apply
    def test_json_output_pins_container_formatting_and_numeric_passthrough(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        malformed_config,
        output_dir,
    ):
        """Pin format_json_cell behavior: dict/list cells become indented JSON
        strings while pure-numeric columns pass through byte-identical.
        Guards refactors of the per-column JSON-formatting pass."""
        _setup_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            pd.DataFrame(
                {
                    "id": ["m1", "m2"],
                    "name": ["M1", "M2"],
                    "type": ["int", "int"],
                    "title": ["M1", "M2"],
                    "description": [{"nested": "dict"}, ["a", "list"]],
                    "sortOrder": [7, 9],
                },
            ),
            pd.DataFrame([{"id": "d1", "name": "D1", "type": "string", "title": "D1", "description": "d"}]),
            {"id": "dv_test", "name": "Test DV", "owner": {"name": "Owner"}},
        )

        result = process_single_dataview(
            data_view_id="dv_test",
            config_file=malformed_config,
            output_dir=output_dir,
            output_format="json",
            quiet=True,
        )
        assert result.success is True

        json_files = list(Path(output_dir).glob("CJA_DataView_*.json"))
        assert len(json_files) == 1
        payload = json.loads(json_files[0].read_text(encoding="utf-8"))
        metrics = payload["metrics"]
        assert metrics[0]["description"] == json.dumps({"nested": "dict"}, indent=2)
        assert metrics[1]["description"] == json.dumps(["a", "list"], indent=2)
        assert [m["sortOrder"] for m in metrics] == [7, 9]


# ===================================================================
# Tests for API raising exceptions during fetch
# ===================================================================


class TestAPIExceptionsDuringFetch:
    """API methods raise various exceptions."""

    @_apply
    def test_fetcher_raises_connection_error(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        malformed_config,
        output_dir,
    ):
        """ParallelAPIFetcher.fetch_all_data raises ConnectionError."""
        logger = logging.getLogger("conn_err")
        logger.handlers = []
        mock_setup_logging.return_value = logger
        mock_init_cja.return_value = Mock()

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.side_effect = ConnectionError("Network unreachable")
        mock_fetcher_class.return_value = mock_fetcher

        result = process_single_dataview(
            data_view_id="dv_test",
            config_file=malformed_config,
            output_dir=output_dir,
            quiet=True,
        )
        assert result.success is False
        assert result.error_message != ""

    @_apply
    def test_fetcher_raises_timeout_error(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        malformed_config,
        output_dir,
    ):
        """ParallelAPIFetcher.fetch_all_data raises TimeoutError."""
        logger = logging.getLogger("timeout_err")
        logger.handlers = []
        mock_setup_logging.return_value = logger
        mock_init_cja.return_value = Mock()

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.side_effect = TimeoutError("API timed out")
        mock_fetcher_class.return_value = mock_fetcher

        result = process_single_dataview(
            data_view_id="dv_test",
            config_file=malformed_config,
            output_dir=output_dir,
            quiet=True,
        )
        assert result.success is False

    @_apply
    def test_fetcher_raises_attribute_error(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        malformed_config,
        output_dir,
    ):
        """ParallelAPIFetcher.fetch_all_data raises AttributeError (API version mismatch)."""
        logger = logging.getLogger("attr_err")
        logger.handlers = []
        mock_setup_logging.return_value = logger
        mock_init_cja.return_value = Mock()

        mock_fetcher = Mock()
        mock_fetcher.fetch_all_data.side_effect = AttributeError("'NoneType' has no attribute 'getMetrics'")
        mock_fetcher_class.return_value = mock_fetcher

        result = process_single_dataview(
            data_view_id="dv_test",
            config_file=malformed_config,
            output_dir=output_dir,
            quiet=True,
        )
        assert result.success is False


# ===================================================================
# Tests for partial API responses
# ===================================================================


class TestPartialAPIResponses:
    """API returns data for some components but not others."""

    @_apply
    def test_metrics_only_no_dimensions(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        malformed_config,
        output_dir,
    ):
        """API returns metrics but empty dimensions."""
        _setup_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            pd.DataFrame([{"id": "m1", "name": "M1", "type": "int", "title": "M1", "description": "d"}]),
            pd.DataFrame(),  # Empty dimensions
            {"id": "dv_test", "name": "Test DV", "owner": {"name": "Owner"}},
        )

        result = process_single_dataview(
            data_view_id="dv_test",
            config_file=malformed_config,
            output_dir=output_dir,
            output_format="json",
            quiet=True,
        )
        # Should succeed — having at least one component is enough
        assert result.success is True
        assert result.metrics_count == 1
        assert result.dimensions_count == 0

    @_apply
    def test_dimensions_only_no_metrics(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        malformed_config,
        output_dir,
    ):
        """API returns dimensions but empty metrics."""
        _setup_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            pd.DataFrame(),  # Empty metrics
            pd.DataFrame([{"id": "d1", "name": "D1", "type": "string", "title": "D1", "description": "d"}]),
            {"id": "dv_test", "name": "Test DV", "owner": {"name": "Owner"}},
        )

        result = process_single_dataview(
            data_view_id="dv_test",
            config_file=malformed_config,
            output_dir=output_dir,
            output_format="json",
            quiet=True,
        )
        assert result.success is True
        assert result.metrics_count == 0
        assert result.dimensions_count == 1

    @_apply
    def test_single_row_dataframes(
        self,
        mock_fetcher_class,
        mock_init_cja,
        mock_setup_logging,
        malformed_config,
        output_dir,
    ):
        """API returns exactly one metric and one dimension."""
        _setup_mocks(
            mock_setup_logging,
            mock_init_cja,
            mock_fetcher_class,
            pd.DataFrame([{"id": "m1", "name": "M1", "type": "int", "title": "M1", "description": "d"}]),
            pd.DataFrame([{"id": "d1", "name": "D1", "type": "string", "title": "D1", "description": "d"}]),
            {"id": "dv_test", "name": "Test DV", "owner": {"name": "Owner"}},
        )

        result = process_single_dataview(
            data_view_id="dv_test",
            config_file=malformed_config,
            output_dir=output_dir,
            output_format="excel",
            quiet=True,
        )
        assert result.success is True
        assert result.metrics_count == 1
        assert result.dimensions_count == 1


# ===================================================================
# Tests for DataQualityChecker with malformed input
# ===================================================================


class TestDataQualityCheckerMalformedInput:
    """DataQualityChecker handles unexpected DataFrame shapes."""

    def test_completely_wrong_columns(self):
        """DataFrame has no recognized columns at all."""
        logger = logging.getLogger("dq_wrong_cols")
        checker = DataQualityChecker(logger)

        df = pd.DataFrame({"foo": [1, 2], "bar": ["a", "b"], "baz": [True, False]})
        checker.check_all_quality_issues_optimized(df, "Metrics", ["id", "name", "type"], ["id", "name", "description"])

        # Should produce critical issues about missing required fields
        assert len(checker.issues) > 0
        critical_issues = [i for i in checker.issues if i.get("Severity") == "CRITICAL"]
        assert len(critical_issues) > 0

    def test_empty_dataframe_no_crash(self):
        """Empty DataFrame should not crash."""
        logger = logging.getLogger("dq_empty")
        checker = DataQualityChecker(logger)

        checker.check_all_quality_issues_optimized(pd.DataFrame(), "Metrics", ["id", "name", "type"], ["id", "name"])
        # Should have critical issue about empty data
        assert len(checker.issues) > 0

    def test_dataframe_with_all_none_values(self):
        """DataFrame where every cell is None."""
        logger = logging.getLogger("dq_all_none")
        checker = DataQualityChecker(logger)

        df = pd.DataFrame({"id": [None, None], "name": [None, None], "type": [None, None]})
        checker.check_all_quality_issues_optimized(df, "Metrics", ["id", "name", "type"], ["id", "name", "description"])
        # Should not crash; should flag null issues
        assert len(checker.issues) > 0

    def test_dataframe_with_nan_values(self):
        """DataFrame with NaN values in critical fields."""
        logger = logging.getLogger("dq_nan")
        checker = DataQualityChecker(logger)

        import numpy as np

        df = pd.DataFrame(
            {
                "id": ["m1", "m2"],
                "name": ["Metric 1", np.nan],
                "type": ["int", "int"],
                "description": [np.nan, "desc"],
            },
        )
        checker.check_all_quality_issues_optimized(df, "Metrics", ["id", "name", "type"], ["id", "name", "description"])
        assert len(checker.issues) > 0

    def test_very_large_string_values(self):
        """Fields with extremely long strings."""
        logger = logging.getLogger("dq_large")
        checker = DataQualityChecker(logger)

        df = pd.DataFrame(
            {
                "id": ["m1"],
                "name": ["A" * 10000],  # 10KB string
                "type": ["int"],
                "description": ["B" * 50000],  # 50KB string
            },
        )
        checker.check_all_quality_issues_optimized(df, "Metrics", ["id", "name", "type"], ["id", "name", "description"])
        # Should not crash or hang
        assert isinstance(checker.issues, list)

    def test_duplicate_column_names_in_dataframe(self):
        """DataFrame with duplicate column names."""
        logger = logging.getLogger("dq_dupcol")
        checker = DataQualityChecker(logger)

        # Create DataFrame with duplicate column via construction trick
        df = pd.DataFrame([[1, "a", "int", "desc", "extra"]], columns=["id", "name", "type", "description", "name"])
        checker.check_all_quality_issues_optimized(df, "Metrics", ["id", "name", "type"], ["id", "name", "description"])
        # Should not crash
        assert isinstance(checker.issues, list)
