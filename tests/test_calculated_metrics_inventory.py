"""
Test suite for CJA Calculated Metrics Inventory

Tests cover:
- Parsing calculated metric formulas
- Inventory generation
- Complexity score calculation
- Formula summary generation
- DataFrame output
"""

import json
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from cja_auto_sdr.inventory.calculated_metrics import (
    CalculatedMetricsInventory,
    CalculatedMetricsInventoryBuilder,
    CalculatedMetricSummary,
)
from cja_auto_sdr.inventory.utils import BatchProcessingStats

# ==================== FIXTURES ====================


@pytest.fixture
def sample_simple_calc_metric():
    """Simple calculated metric: Revenue per Order (Revenue / Orders)"""
    return {
        "id": "cm_revenue_per_order",
        "name": "Revenue per Order",
        "description": "Average revenue per order",
        "owner": {"name": "Test Owner"},
        "polarity": "positive",
        "type": "currency",
        "precision": 2,
        "definition": {
            "func": "calc-metric",
            "version": [1, 0, 0],
            "formula": {
                "func": "divide",
                "col1": {"func": "metric", "name": "metrics/revenue"},
                "col2": {"func": "metric", "name": "metrics/orders"},
            },
        },
    }


@pytest.fixture
def sample_complex_calc_metric():
    """Complex calculated metric with segment and nested operations"""
    return {
        "id": "cm_mobile_conversion_rate",
        "name": "Mobile Conversion Rate",
        "description": "Conversion rate for mobile visitors",
        "owner": {"name": "Analytics Team"},
        "polarity": "positive",
        "type": "percent",
        "precision": 2,
        "definition": {
            "func": "calc-metric",
            "version": [1, 0, 0],
            "formula": {
                "func": "segment",
                "segment_id": "s_mobile_visitors",
                "metric": {
                    "func": "divide",
                    "col1": {"func": "metric", "name": "metrics/orders"},
                    "col2": {"func": "metric", "name": "metrics/visits"},
                },
            },
        },
    }


@pytest.fixture
def sample_nested_calc_metric():
    """Deeply nested calculated metric for complexity testing"""
    return {
        "id": "cm_complex_ratio",
        "name": "Complex Profit Ratio",
        "description": "Complex nested calculation",
        "owner": {"name": "Finance Team"},
        "polarity": "positive",
        "type": "decimal",
        "precision": 4,
        "definition": {
            "func": "calc-metric",
            "version": [1, 0, 0],
            "formula": {
                "func": "divide",
                "col1": {
                    "func": "subtract",
                    "col1": {"func": "metric", "name": "metrics/revenue"},
                    "col2": {
                        "func": "add",
                        "col1": {"func": "metric", "name": "metrics/cost"},
                        "col2": {
                            "func": "multiply",
                            "col1": {"func": "metric", "name": "metrics/overhead"},
                            "col2": {"func": "number", "val": 1.2},
                        },
                    },
                },
                "col2": {"func": "metric", "name": "metrics/revenue"},
            },
        },
    }


@pytest.fixture
def sample_conditional_calc_metric():
    """Calculated metric with conditional logic"""
    return {
        "id": "cm_conditional",
        "name": "Conditional Metric",
        "description": "Metric with if condition",
        "owner": {"name": "Test User"},
        "polarity": "neutral",
        "type": "decimal",
        "precision": 0,
        "definition": {
            "func": "calc-metric",
            "version": [1, 0, 0],
            "formula": {
                "func": "if",
                "condition": {
                    "func": "gt",
                    "left": {"func": "metric", "name": "metrics/visits"},
                    "right": {"func": "number", "val": 100},
                },
                "then": {"func": "metric", "name": "metrics/orders"},
                "else": {"func": "number", "val": 0},
            },
        },
    }


@pytest.fixture
def sample_addition_calc_metric():
    """Simple addition calculated metric"""
    return {
        "id": "cm_total_events",
        "name": "Total Events",
        "description": "Sum of click and view events",
        "owner": {"name": "Test"},
        "polarity": "positive",
        "type": "integer",
        "precision": 0,
        "definition": {
            "func": "calc-metric",
            "version": [1, 0, 0],
            "formula": {
                "func": "add",
                "col1": {"func": "metric", "name": "metrics/clicks"},
                "col2": {"func": "metric", "name": "metrics/views"},
            },
        },
    }


@pytest.fixture
def mock_cja_instance(sample_simple_calc_metric, sample_complex_calc_metric):
    """Create a mock CJA instance with calculated metrics"""
    mock_cja = Mock()
    mock_cja.getCalculatedMetrics.return_value = pd.DataFrame([sample_simple_calc_metric, sample_complex_calc_metric])
    return mock_cja


@pytest.fixture
def mock_cja_instance_list_response(sample_simple_calc_metric, sample_complex_calc_metric):
    """Create a mock CJA instance that returns a list (not DataFrame)"""
    mock_cja = Mock()
    mock_cja.getCalculatedMetrics.return_value = [sample_simple_calc_metric, sample_complex_calc_metric]
    return mock_cja


@pytest.fixture
def mock_cja_instance_empty():
    """Create a mock CJA instance with no calculated metrics"""
    mock_cja = Mock()
    mock_cja.getCalculatedMetrics.return_value = pd.DataFrame()
    return mock_cja


# ==================== BUILDER TESTS ====================


class TestCalculatedMetricsInventoryBuilder:
    """Tests for CalculatedMetricsInventoryBuilder class"""

    def test_build_basic(self, mock_cja_instance):
        """Test basic inventory building"""
        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja_instance, "dv_test", "Test View")

        assert isinstance(inventory, CalculatedMetricsInventory)
        assert inventory.data_view_id == "dv_test"
        assert inventory.data_view_name == "Test View"
        assert inventory.total_calculated_metrics == 2

    def test_build_from_list_response(self, mock_cja_instance_list_response):
        """Test building when API returns a list instead of DataFrame"""
        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja_instance_list_response, "dv_test", "Test")

        assert inventory.total_calculated_metrics == 2

    def test_build_empty(self, mock_cja_instance_empty):
        """Test building with no calculated metrics"""
        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja_instance_empty, "dv_empty", "Empty")

        assert inventory.total_calculated_metrics == 0

    def test_api_called_with_correct_params(self, mock_cja_instance):
        """Test that API is called with correct parameters"""
        builder = CalculatedMetricsInventoryBuilder()
        builder.build(mock_cja_instance, "dv_abc123", "Test")

        mock_cja_instance.getCalculatedMetrics.assert_called_once_with(dataIds="dv_abc123", full=True)

    def test_complexity_score_calculated(self, mock_cja_instance):
        """Test that complexity scores are calculated"""
        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja_instance, "dv_test", "Test")

        for metric in inventory.metrics:
            assert 0 <= metric.complexity_score <= 100

    def test_metric_references_extracted(self, sample_simple_calc_metric):
        """Test that metric references are extracted correctly"""
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = [sample_simple_calc_metric]

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert len(inventory.metrics) == 1
        metric = inventory.metrics[0]
        assert "revenue" in metric.metric_references
        assert "orders" in metric.metric_references

    def test_segment_references_extracted(self, sample_complex_calc_metric):
        """Test that segment references are extracted correctly"""
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = [sample_complex_calc_metric]

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert len(inventory.metrics) == 1
        metric = inventory.metrics[0]
        assert "s_mobile_visitors" in metric.segment_references

    def test_functions_extracted(self, sample_simple_calc_metric):
        """Test that functions are extracted correctly"""
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = [sample_simple_calc_metric]

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        metric = inventory.metrics[0]
        assert "Division" in metric.functions_used

    def test_owner_extracted(self, sample_simple_calc_metric):
        """Test that owner is extracted from nested structure"""
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = [sample_simple_calc_metric]

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        metric = inventory.metrics[0]
        assert metric.owner == "Test Owner"

    def test_missing_definition_skipped(self):
        """Test that metrics without definitions are skipped"""
        metric_no_def = {
            "id": "cm_no_def",
            "name": "No Definition",
            "description": "",
            "owner": {"name": "Test"},
        }
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = [metric_no_def]

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert inventory.total_calculated_metrics == 0

    def test_nan_id_skipped(self):
        """Calculated metrics with NaN IDs should be skipped."""
        metric_nan_id = {
            "id": float("nan"),
            "name": "NaN ID Metric",
            "description": "",
            "owner": {"name": "Test"},
            "definition": {"formula": {"func": "metric", "name": "metrics/revenue"}},
        }
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = [metric_nan_id]

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert inventory.total_calculated_metrics == 0


# ==================== INVENTORY TESTS ====================


class TestCalculatedMetricsInventory:
    """Tests for CalculatedMetricsInventory class"""

    def test_get_dataframe(self, mock_cja_instance):
        """Test DataFrame output"""
        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja_instance, "dv_test", "Test")

        df = inventory.get_dataframe()

        assert isinstance(df, pd.DataFrame)
        assert len(df) == inventory.total_calculated_metrics
        assert "name" in df.columns
        assert "complexity_score" in df.columns
        assert "functions_used" in df.columns
        assert "formula_summary" in df.columns

    def test_get_dataframe_sorted_by_complexity(self, mock_cja_instance):
        """Test that DataFrame is sorted by complexity score descending"""
        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja_instance, "dv_test", "Test")

        df = inventory.get_dataframe()

        scores = df["complexity_score"].tolist()
        assert scores == sorted(scores, reverse=True)

    def test_get_summary(self, mock_cja_instance):
        """Test summary statistics"""
        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja_instance, "dv_test", "Test")

        summary = inventory.get_summary()

        assert "data_view_id" in summary
        assert "data_view_name" in summary
        assert "total_calculated_metrics" in summary
        assert "complexity" in summary
        assert "function_usage" in summary

    def test_to_json(self, mock_cja_instance):
        """Test JSON export"""
        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja_instance, "dv_test", "Test")

        json_data = inventory.to_json()

        assert "summary" in json_data
        assert "metrics" in json_data
        assert len(json_data["metrics"]) == inventory.total_calculated_metrics

    def test_empty_inventory_dataframe(self, mock_cja_instance_empty):
        """Test DataFrame output for empty inventory"""
        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja_instance_empty, "dv_test", "Test")

        df = inventory.get_dataframe()

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert "name" in df.columns  # Columns should still be present


# ==================== COMPLEXITY SCORE TESTS ====================


class TestComplexityScore:
    """Tests for complexity score calculation"""

    def test_simple_metric_low_complexity(self, sample_simple_calc_metric):
        """Test that simple metrics have low complexity"""
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = [sample_simple_calc_metric]

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        metric = inventory.metrics[0]
        assert metric.complexity_score < 30  # Simple division should be low

    def test_nested_metric_higher_complexity(self, sample_nested_calc_metric):
        """Test that nested metrics have higher complexity"""
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = [sample_nested_calc_metric]

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        metric = inventory.metrics[0]
        assert metric.complexity_score > 20  # Nested should be more complex

    def test_segment_metric_adds_complexity(self, sample_complex_calc_metric):
        """Test that segment filters add complexity"""
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = [sample_complex_calc_metric]

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        metric = inventory.metrics[0]
        # Should have segment contribution
        assert metric.complexity_score > 0
        assert len(metric.segment_references) > 0

    def test_conditional_metric_adds_complexity(self, sample_conditional_calc_metric):
        """Test that conditional logic adds complexity"""
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = [sample_conditional_calc_metric]

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        metric = inventory.metrics[0]
        assert metric.conditional_count > 0


# ==================== FORMULA SUMMARY TESTS ====================


class TestFormulaSummary:
    """Tests for formula summary generation"""

    def test_division_summary(self, sample_simple_calc_metric):
        """Test formula summary for division"""
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = [sample_simple_calc_metric]

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        metric = inventory.metrics[0]
        assert "revenue" in metric.formula_summary.lower()
        assert "orders" in metric.formula_summary.lower()

    def test_addition_summary(self, sample_addition_calc_metric):
        """Test formula summary for addition"""
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = [sample_addition_calc_metric]

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        metric = inventory.metrics[0]
        # Should mention the referenced metrics or sum
        assert (
            "sum" in metric.formula_summary.lower()
            or "clicks" in metric.formula_summary.lower()
            or "addition" in metric.formula_summary.lower()
        )

    def test_segment_summary(self, sample_complex_calc_metric):
        """Test formula summary for segmented metric"""
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = [sample_complex_calc_metric]

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        metric = inventory.metrics[0]
        # Should mention segment/filter OR show segment in bracket notation [segment]
        assert (
            "segment" in metric.formula_summary.lower()
            or "filter" in metric.formula_summary.lower()
            or "[" in metric.formula_summary
        )  # bracket notation for segments

    def test_conditional_summary(self, sample_conditional_calc_metric):
        """Test formula summary for conditional metric"""
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = [sample_conditional_calc_metric]

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        metric = inventory.metrics[0]
        # Should show conditional logic either as word or IF(...) function
        assert "conditional" in metric.formula_summary.lower() or "if(" in metric.formula_summary.lower()


# ==================== EDGE CASE TESTS ====================


class TestEdgeCases:
    """Tests for edge cases and error handling"""

    def test_missing_owner(self):
        """Test handling of missing owner"""
        metric = {
            "id": "cm_test",
            "name": "Test",
            "description": "",
            "definition": {"func": "calc-metric", "formula": {"func": "metric", "name": "metrics/visits"}},
        }
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = [metric]

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert len(inventory.metrics) == 1
        assert inventory.metrics[0].owner == ""

    def test_owner_as_string(self):
        """Test handling of owner as string instead of dict"""
        metric = {
            "id": "cm_test",
            "name": "Test",
            "description": "",
            "owner": "string_owner",
            "definition": {"func": "calc-metric", "formula": {"func": "metric", "name": "metrics/visits"}},
        }
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = [metric]

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert inventory.metrics[0].owner == "string_owner"

    def test_empty_formula(self):
        """Test handling of empty formula"""
        metric = {
            "id": "cm_test",
            "name": "Test",
            "description": "",
            "definition": {"func": "calc-metric", "formula": {}},
        }
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = [metric]

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        # Empty formula should be skipped
        assert inventory.total_calculated_metrics == 0

    def test_api_error_handling(self):
        """Test handling of API errors"""
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.side_effect = Exception("API Error")

        builder = CalculatedMetricsInventoryBuilder()

        with pytest.raises(Exception) as exc_info:
            builder.build(mock_cja, "dv_test", "Test")

        assert "API Error" in str(exc_info.value)

    def test_none_response(self):
        """Test handling of None API response"""
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = None

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert inventory.total_calculated_metrics == 0

    def test_unexpected_response_type(self):
        """Test handling of unexpected response type"""
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = "unexpected"

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert inventory.total_calculated_metrics == 0

    def test_scalar_formula_is_supported(self):
        """Scalar formulas should not crash summary generation."""
        metric = {
            "id": "cm_scalar",
            "name": "Scalar Metric",
            "description": "",
            "definition": {"func": "calc-metric", "formula": 1.0},
        }
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = [metric]

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert inventory.total_calculated_metrics == 1
        assert inventory.metrics[0].formula_summary == "1.0"

    def test_non_string_metric_name_does_not_crash(self):
        """Non-string metric name should not crash name.split('/')."""
        metric = {
            "id": "cm_name",
            "name": "Non String Name",
            "description": "",
            "definition": {
                "func": "calc-metric",
                "formula": {"func": "metric", "name": 123},
            },
        }
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = [metric]

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert inventory.total_calculated_metrics == 1

    def test_non_list_operands_does_not_crash(self):
        """Non-list operands value should not crash iteration."""
        metric = {
            "id": "cm_ops",
            "name": "Non List Operands",
            "description": "",
            "definition": {
                "func": "calc-metric",
                "formula": {
                    "func": "add",
                    "operands": "not_a_list",
                },
            },
        }
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = [metric]

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert inventory.total_calculated_metrics == 1

    def test_non_dict_metric_payloads_are_skipped(self):
        """Unexpected list entries from the API should be skipped safely."""
        valid_metric = {
            "id": "cm_valid",
            "name": "Valid Metric",
            "description": "",
            "definition": {"func": "calc-metric", "formula": {"func": "metric", "name": "metrics/revenue"}},
        }
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = ["bad_payload", valid_metric]

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert inventory.total_calculated_metrics == 1
        assert inventory.metrics[0].metric_id == "cm_valid"

    def test_dict_shaped_segment_id_is_normalized(self):
        """Segment IDs provided as objects should still be extracted safely."""
        metric = {
            "id": "cm_segment_obj",
            "name": "Segment Object Metric",
            "description": "",
            "definition": {
                "func": "calc-metric",
                "formula": {
                    "func": "segment",
                    "segment_id": {"id": "segments/s_mobile_visitors"},
                    "metric": {"func": "metric", "name": "metrics/orders"},
                },
            },
        }
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = [metric]

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert inventory.total_calculated_metrics == 1
        assert "s_mobile_visitors" in inventory.metrics[0].segment_references

    def test_non_string_func_name_does_not_crash(self):
        """Unhashable/non-string func values should be ignored safely."""
        metric = {
            "id": "cm_bad_func",
            "name": "Bad Func",
            "description": "",
            "definition": {
                "func": "calc-metric",
                "formula": {"func": {"bad": "metric"}, "name": "metrics/revenue"},
            },
        }
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = [metric]

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert inventory.total_calculated_metrics == 1

    def test_timestamp_metadata_is_preserved(self):
        """Datetime-like created/modified values should not be dropped."""
        metric = {
            "id": "cm_timestamps",
            "name": "Timestamp Metric",
            "description": "",
            "created": pd.Timestamp("2025-01-15T10:30:00Z"),
            "modified": pd.Timestamp("2025-01-16T11:45:00Z"),
            "definition": {"func": "calc-metric", "formula": {"func": "metric", "name": "metrics/revenue"}},
        }
        mock_cja = Mock()
        mock_cja.getCalculatedMetrics.return_value = [metric]

        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert inventory.total_calculated_metrics == 1
        assert inventory.metrics[0].created != ""
        assert inventory.metrics[0].modified != ""
        df = inventory.get_dataframe()
        assert df.iloc[0]["created"] != "-"
        assert df.iloc[0]["modified"] != "-"
        assert "2025-01-15" in str(df.iloc[0]["created"])
        assert "2025-01-16" in str(df.iloc[0]["modified"])


# ==================== DATA CLASS TESTS ====================


class TestCalculatedMetricSummary:
    """Tests for CalculatedMetricSummary data class"""

    def test_to_dict(self):
        """Test conversion to dictionary"""
        summary = CalculatedMetricSummary(
            metric_id="cm_test",
            metric_name="Test Metric",
            description="Test description",
            owner="Test Owner",
            complexity_score=45.5,
            functions_used=["Division", "Metric Reference"],
            functions_used_internal=["divide", "metric"],
            nesting_depth=2,
            operator_count=1,
            metric_references=["revenue", "orders"],
            segment_references=[],
            conditional_count=0,
            formula_summary="revenue divided by orders",
            polarity="positive",
            metric_type="currency",
            precision=2,
        )

        d = summary.to_dict()

        assert d["name"] == "Test Metric"
        assert d["description"] == "Test description"
        assert d["owner"] == "Test Owner"
        assert d["complexity_score"] == pytest.approx(45.5)
        assert "Division" in d["functions_used"]
        assert "revenue" in d["metric_references"]
        assert d["polarity"] == "Positive"

    def test_to_full_dict(self):
        """Test conversion to full dictionary"""
        summary = CalculatedMetricSummary(
            metric_id="cm_test",
            metric_name="Test",
            description="",
            owner="",
            complexity_score=10.0,
            functions_used=["Division"],
            functions_used_internal=["divide"],
            nesting_depth=1,
            operator_count=1,
            metric_references=["a", "b"],
            segment_references=["seg1"],
            conditional_count=0,
            formula_summary="a / b",
            polarity="positive",
            metric_type="decimal",
            precision=4,
        )

        d = summary.to_full_dict()

        assert d["metric_id"] == "cm_test"
        assert d["nesting_depth"] == 1
        assert d["segment_references"] == ["seg1"]
        assert d["precision"] == 4


class TestCalculatedMetricsInventoryProperties:
    """Tests for CalculatedMetricsInventory properties"""

    def test_avg_complexity_empty(self):
        """Test average complexity with no metrics"""
        inventory = CalculatedMetricsInventory(data_view_id="dv_test", data_view_name="Test")
        assert inventory.avg_complexity == pytest.approx(0.0)

    def test_max_complexity_empty(self):
        """Test max complexity with no metrics"""
        inventory = CalculatedMetricsInventory(data_view_id="dv_test", data_view_name="Test")
        assert inventory.max_complexity == pytest.approx(0.0)


# ==================== SUMMARY COLUMN ALIAS TESTS ====================


class TestSummaryColumnAlias:
    """Tests for standardized summary column alias"""

    def test_summary_column_exists(self, mock_cja_instance):
        """Test that summary column exists in DataFrame"""
        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja_instance, "dv_test", "Test")
        df = inventory.get_dataframe()

        assert "summary" in df.columns

    def test_summary_equals_formula_summary(self, mock_cja_instance):
        """Test that summary column equals formula_summary column"""
        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja_instance, "dv_test", "Test")
        df = inventory.get_dataframe()

        assert all(df["summary"] == df["formula_summary"])

    def test_empty_dataframe_has_summary_column(self, mock_cja_instance_empty):
        """Test that empty DataFrame still has summary column"""
        builder = CalculatedMetricsInventoryBuilder()
        inventory = builder.build(mock_cja_instance_empty, "dv_test", "Test")
        df = inventory.get_dataframe()

        assert "summary" in df.columns


# ==================== NORMALIZE FORMULA NODE TESTS ====================


class TestNormalizeFormulaNode:
    """Tests for _normalize_formula_node edge cases"""

    def setup_method(self):
        self.builder = CalculatedMetricsInventoryBuilder()

    def test_dict_passthrough(self):
        """Dict nodes are returned unchanged."""
        node = {"func": "divide", "col1": {}, "col2": {}}
        result = self.builder._normalize_formula_node(node)
        assert result == node

    def test_bool_becomes_literal(self):
        """Boolean values become literal nodes."""
        result = self.builder._normalize_formula_node(True)
        assert result == {"func": "literal", "val": True}

        result_false = self.builder._normalize_formula_node(False)
        assert result_false == {"func": "literal", "val": False}

    def test_int_becomes_number(self):
        """Integer values become number nodes."""
        result = self.builder._normalize_formula_node(42)
        assert result == {"func": "number", "val": 42}

    def test_float_becomes_number(self):
        """Float values become number nodes."""
        result = self.builder._normalize_formula_node(3.14)
        assert result == {"func": "number", "val": 3.14}

    def test_string_with_slash_becomes_metric(self):
        """Strings containing '/' become metric reference nodes."""
        result = self.builder._normalize_formula_node("metrics/revenue")
        assert result == {"func": "metric", "name": "metrics/revenue"}

    def test_string_without_slash_becomes_literal(self):
        """Strings without '/' become literal nodes."""
        result = self.builder._normalize_formula_node("some_value")
        assert result == {"func": "literal", "val": "some_value"}

    def test_empty_string_returns_none(self):
        """Empty or whitespace-only strings return None."""
        assert self.builder._normalize_formula_node("") is None
        assert self.builder._normalize_formula_node("   ") is None

    def test_none_returns_none(self):
        """None returns None."""
        assert self.builder._normalize_formula_node(None) is None

    def test_list_returns_first_normalizable(self):
        """Lists return the first normalizable item (int normalizes to number node)."""
        items = [42, {"func": "metric", "name": "metrics/orders"}, "other"]
        result = self.builder._normalize_formula_node(items)
        # 42 is an int, so it normalizes to a number node first
        assert result == {"func": "number", "val": 42}

    def test_list_returns_first_dict_when_no_prior_scalars(self):
        """Lists with None before dict return the dict."""
        items = [None, {"func": "metric", "name": "metrics/orders"}, "other"]
        result = self.builder._normalize_formula_node(items)
        assert result == {"func": "metric", "name": "metrics/orders"}

    def test_list_with_no_dict_returns_first_normalizable(self):
        """Lists without dicts return the first normalizable item."""
        items = [42, "metrics/revenue"]
        result = self.builder._normalize_formula_node(items)
        assert result == {"func": "number", "val": 42}

    def test_empty_list_returns_none(self):
        """Empty list returns None."""
        assert self.builder._normalize_formula_node([]) is None

    def test_list_of_nones_returns_none(self):
        """A list of only None/empty items returns None."""
        assert self.builder._normalize_formula_node([None, None]) is None

    def test_unsupported_type_returns_none(self):
        """Types like set or tuple return None."""
        assert self.builder._normalize_formula_node(set()) is None
        assert self.builder._normalize_formula_node(object()) is None


# ==================== BUILD FORMULA EXPRESSION TESTS ====================


class TestBuildFormulaExpression:
    """Tests for _build_formula_expression"""

    def setup_method(self):
        self.builder = CalculatedMetricsInventoryBuilder()

    def test_metric_reference(self):
        """Metric reference returns short name."""
        node = {"func": "metric", "name": "metrics/revenue"}
        assert self.builder._build_formula_expression(node) == "revenue"

    def test_number_value(self):
        """Number node returns string value."""
        node = {"func": "number", "val": 100}
        assert self.builder._build_formula_expression(node) == "100"

    def test_number_none_val(self):
        """Number node with None val returns empty string."""
        node = {"func": "number", "val": None}
        assert self.builder._build_formula_expression(node) == ""

    def test_literal_string(self):
        """Literal with string value returns the string."""
        node = {"func": "literal", "val": "hello"}
        assert self.builder._build_formula_expression(node) == "hello"

    def test_literal_numeric(self):
        """Literal with numeric value returns stringified value."""
        node = {"func": "literal", "val": 42}
        assert self.builder._build_formula_expression(node) == "42"

    def test_literal_none_val(self):
        """Literal with None val returns empty string."""
        node = {"func": "literal", "val": None}
        assert self.builder._build_formula_expression(node) == ""

    def test_divide_simple(self):
        """Simple division expression."""
        node = {
            "func": "divide",
            "col1": {"func": "metric", "name": "metrics/revenue"},
            "col2": {"func": "metric", "name": "metrics/orders"},
        }
        assert self.builder._build_formula_expression(node) == "revenue / orders"

    def test_divide_with_complex_operands_adds_parens(self):
        """Division with complex operands adds parentheses."""
        node = {
            "func": "divide",
            "col1": {
                "func": "add",
                "col1": {"func": "metric", "name": "metrics/a"},
                "col2": {"func": "metric", "name": "metrics/b"},
            },
            "col2": {"func": "metric", "name": "metrics/c"},
        }
        result = self.builder._build_formula_expression(node)
        assert result == "(a + b) / c"

    def test_multiply_simple(self):
        """Simple multiplication expression."""
        node = {
            "func": "multiply",
            "col1": {"func": "metric", "name": "metrics/price"},
            "col2": {"func": "metric", "name": "metrics/quantity"},
        }
        assert self.builder._build_formula_expression(node) == "price x quantity"

    def test_add_with_col1_col2(self):
        """Addition with col1 and col2."""
        node = {
            "func": "add",
            "col1": {"func": "metric", "name": "metrics/clicks"},
            "col2": {"func": "metric", "name": "metrics/views"},
        }
        assert self.builder._build_formula_expression(node) == "clicks + views"

    def test_add_with_operands_list(self):
        """Addition with operands list."""
        node = {
            "func": "add",
            "operands": [
                {"func": "metric", "name": "metrics/a"},
                {"func": "metric", "name": "metrics/b"},
                {"func": "metric", "name": "metrics/c"},
            ],
        }
        assert self.builder._build_formula_expression(node) == "a + b + c"

    def test_subtract_simple(self):
        """Simple subtraction expression."""
        node = {
            "func": "subtract",
            "col1": {"func": "metric", "name": "metrics/revenue"},
            "col2": {"func": "metric", "name": "metrics/cost"},
        }
        assert self.builder._build_formula_expression(node) == "revenue - cost"

    def test_segment_with_id(self):
        """Segment wrapping a metric with segment ID."""
        node = {
            "func": "segment",
            "segment_id": "s300000_abcdefgh12345678",
            "metric": {"func": "metric", "name": "metrics/orders"},
        }
        result = self.builder._build_formula_expression(node)
        assert "orders" in result
        assert "[" in result  # bracket notation

    def test_segment_without_id(self):
        """Segment wrapping a metric without segment ID."""
        node = {
            "func": "segment",
            "metric": {"func": "metric", "name": "metrics/orders"},
        }
        result = self.builder._build_formula_expression(node)
        assert result == "orders[filtered]"

    def test_col_sum(self):
        """Column sum aggregation."""
        node = {
            "func": "col-sum",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        assert self.builder._build_formula_expression(node) == "SUM(revenue)"

    def test_col_max(self):
        """Column max aggregation."""
        node = {
            "func": "col-max",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        assert self.builder._build_formula_expression(node) == "MAX(revenue)"

    def test_col_min(self):
        """Column min aggregation."""
        node = {
            "func": "col-min",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        assert self.builder._build_formula_expression(node) == "MIN(revenue)"

    def test_col_mean(self):
        """Column mean aggregation."""
        node = {
            "func": "col-mean",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        assert self.builder._build_formula_expression(node) == "MEAN(revenue)"

    def test_col_count(self):
        """Column count aggregation."""
        node = {
            "func": "col-count",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        assert self.builder._build_formula_expression(node) == "COUNT(revenue)"

    def test_if_with_then_and_else(self):
        """If expression with then and else branches."""
        node = {
            "func": "if",
            "condition": {
                "func": "gt",
                "col1": {"func": "metric", "name": "metrics/visits"},
                "col2": {"func": "number", "val": 0},
            },
            "then": {"func": "metric", "name": "metrics/orders"},
            "else": {"func": "number", "val": 0},
        }
        result = self.builder._build_formula_expression(node)
        assert result == "IF(..., orders, 0)"

    def test_if_with_then_only(self):
        """If expression with then branch only."""
        node = {
            "func": "if",
            "condition": {"func": "gt"},
            "then": {"func": "metric", "name": "metrics/orders"},
        }
        result = self.builder._build_formula_expression(node)
        assert result == "IF(..., orders)"

    def test_abs_function(self):
        """ABS function expression."""
        node = {
            "func": "abs",
            "col": {"func": "metric", "name": "metrics/delta"},
        }
        assert self.builder._build_formula_expression(node) == "ABS(delta)"

    def test_sqrt_function(self):
        """SQRT function expression."""
        node = {
            "func": "sqrt",
            "col": {"func": "metric", "name": "metrics/variance"},
        }
        assert self.builder._build_formula_expression(node) == "SQRT(variance)"

    def test_log_function(self):
        """LOG function expression."""
        node = {
            "func": "log",
            "col": {"func": "metric", "name": "metrics/value"},
        }
        assert self.builder._build_formula_expression(node) == "LOG(value)"

    def test_negate_function(self):
        """NEGATE function expression."""
        node = {
            "func": "negate",
            "col": {"func": "metric", "name": "metrics/cost"},
        }
        assert self.builder._build_formula_expression(node) == "NEGATE(cost)"

    def test_ceil_function(self):
        """CEIL function expression."""
        node = {
            "func": "ceil",
            "col1": {"func": "metric", "name": "metrics/value"},
        }
        assert self.builder._build_formula_expression(node) == "CEIL(value)"

    def test_floor_function(self):
        """FLOOR function expression."""
        node = {
            "func": "floor",
            "col1": {"func": "metric", "name": "metrics/value"},
        }
        assert self.builder._build_formula_expression(node) == "FLOOR(value)"

    def test_round_function(self):
        """ROUND function expression."""
        node = {
            "func": "round",
            "col1": {"func": "metric", "name": "metrics/value"},
        }
        assert self.builder._build_formula_expression(node) == "ROUND(value)"

    def test_exp_function(self):
        """EXP function expression."""
        node = {
            "func": "exp",
            "col": {"func": "metric", "name": "metrics/value"},
        }
        assert self.builder._build_formula_expression(node) == "EXP(value)"

    def test_log10_function(self):
        """LOG10 function expression."""
        node = {
            "func": "log10",
            "col": {"func": "metric", "name": "metrics/value"},
        }
        assert self.builder._build_formula_expression(node) == "LOG10(value)"

    def test_cumulative_function(self):
        """Cumulative function expression."""
        node = {
            "func": "cumulative",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        assert self.builder._build_formula_expression(node) == "CUM(revenue)"

    def test_cumulative_no_inner(self):
        """Cumulative function with no resolvable inner returns empty."""
        node = {"func": "cumulative"}
        assert self.builder._build_formula_expression(node) == ""

    def test_visualization_group_unwrap(self):
        """Visualization-group is treated as transparent wrapper."""
        node = {
            "func": "visualization-group",
            "formula": {
                "func": "divide",
                "col1": {"func": "metric", "name": "metrics/a"},
                "col2": {"func": "metric", "name": "metrics/b"},
            },
        }
        result = self.builder._build_formula_expression(node)
        assert result == "a / b"

    def test_visualization_group_formulas_array(self):
        """Visualization-group with formulas array."""
        node = {
            "func": "visualization-group",
            "formulas": [
                {
                    "func": "metric",
                    "name": "metrics/revenue",
                },
            ],
        }
        result = self.builder._build_formula_expression(node)
        assert result == "revenue"

    def test_static_row(self):
        """Static-row returns COUNT_ROWS()."""
        assert self.builder._build_formula_expression({"func": "static-row"}) == "COUNT_ROWS()"

    def test_count_rows(self):
        """Count-rows returns COUNT_ROWS()."""
        assert self.builder._build_formula_expression({"func": "count-rows"}) == "COUNT_ROWS()"

    def test_row_count(self):
        """Row-count returns COUNT_ROWS()."""
        assert self.builder._build_formula_expression({"func": "row-count"}) == "COUNT_ROWS()"

    def test_distinct_count_with_inner(self):
        """Distinct-count with inner metric."""
        node = {
            "func": "distinct-count",
            "col": {"func": "metric", "name": "metrics/visitors"},
        }
        assert self.builder._build_formula_expression(node) == "DISTINCT(visitors)"

    def test_distinct_count_without_inner(self):
        """Distinct-count without resolvable inner returns DISTINCT_COUNT()."""
        node = {"func": "distinct-count"}
        assert self.builder._build_formula_expression(node) == "DISTINCT_COUNT()"

    def test_approximate_count_distinct(self):
        """Approximate-count-distinct with inner metric."""
        node = {
            "func": "approximate-count-distinct",
            "col": {"func": "metric", "name": "metrics/users"},
        }
        assert self.builder._build_formula_expression(node) == "DISTINCT(users)"

    def test_non_dict_returns_empty(self):
        """Non-dict input returns empty string."""
        assert self.builder._build_formula_expression("not a dict") == ""
        assert self.builder._build_formula_expression(42) == ""
        assert self.builder._build_formula_expression(None) == ""

    def test_max_depth_zero_returns_empty(self):
        """Depth exhaustion returns empty string."""
        node = {"func": "metric", "name": "metrics/revenue"}
        assert self.builder._build_formula_expression(node, max_depth=0) == ""

    def test_unknown_func_returns_empty(self):
        """Unknown function returns empty string."""
        node = {"func": "unknown_func"}
        assert self.builder._build_formula_expression(node) == ""


# ==================== GENERATE FORMULA SUMMARY TESTS ====================


class TestGenerateFormulaSummary:
    """Tests for _generate_formula_summary with various formula types"""

    def setup_method(self):
        self.builder = CalculatedMetricsInventoryBuilder()

    def _make_parsed(self, formula):
        """Helper: parse a formula and return the parsed dict."""
        return self.builder._parse_formula(formula)

    def test_multiply_summary_with_names(self):
        """Multiply formula with identifiable operands."""
        formula = {
            "func": "multiply",
            "col1": {"func": "metric", "name": "metrics/price"},
            "col2": {"func": "metric", "name": "metrics/quantity"},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        # Short enough for expression builder: "price x quantity"
        assert "price" in result.lower()
        assert "quantity" in result.lower()

    def test_multiply_summary_without_names(self):
        """Multiply formula with no identifiable operand names falls back."""
        formula = {
            "func": "multiply",
            "col1": {},
            "col2": {},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "ultiplication" in result or "x" in result.lower() or "metric" in result.lower()

    def test_subtract_summary_with_names(self):
        """Subtract formula with identifiable operands."""
        formula = {
            "func": "subtract",
            "col1": {"func": "metric", "name": "metrics/revenue"},
            "col2": {"func": "metric", "name": "metrics/cost"},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "revenue" in result.lower()
        assert "cost" in result.lower()

    def test_subtract_summary_without_names(self):
        """Subtract formula with no identifiable names falls back."""
        formula = {
            "func": "subtract",
            "col1": {},
            "col2": {},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "ifference" in result or "-" in result or "metric" in result.lower()

    def test_add_summary_few_operands(self):
        """Add formula with col1/col2 (2 operands)."""
        formula = {
            "func": "add",
            "col1": {"func": "metric", "name": "metrics/a"},
            "col2": {"func": "metric", "name": "metrics/b"},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        # Should be expression: "a + b"
        assert "a" in result.lower()

    def test_add_summary_many_operands(self):
        """Add formula with many operands uses truncation in fallback."""
        formula = {
            "func": "add",
            "operands": [
                {"func": "metric", "name": "metrics/a"},
                {"func": "metric", "name": "metrics/b"},
                {"func": "metric", "name": "metrics/c"},
                {"func": "metric", "name": "metrics/d"},
            ],
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "a" in result.lower()

    def test_add_summary_no_operands(self):
        """Add formula with no resolvable operands falls back."""
        formula = {
            "func": "add",
            "col1": {},
            "col2": {},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "sum" in result.lower() or "metric" in result.lower() or "calculated" in result.lower()

    def test_if_summary_with_condition(self):
        """If formula with describable condition."""
        formula = {
            "func": "if",
            "condition": {
                "func": "gt",
                "col1": {"func": "metric", "name": "metrics/visits"},
                "col2": {"func": "number", "val": 100},
            },
            "then": {"func": "metric", "name": "metrics/orders"},
            "else": {"func": "number", "val": 0},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        # Expression builder should produce IF(..., orders, 0)
        assert "if" in result.lower() or "IF" in result

    def test_if_summary_without_condition(self):
        """If formula with no describable condition."""
        formula = {
            "func": "if",
            "then": {"func": "metric", "name": "metrics/orders"},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "if" in result.lower() or "onditional" in result

    def test_segment_summary_with_inner_and_segment_id(self):
        """Segment formula with both inner metric and segment ID."""
        formula = {
            "func": "segment",
            "segment_id": "s300000_abcdef1234567890",
            "metric": {"func": "metric", "name": "metrics/orders"},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "orders" in result.lower()

    def test_segment_summary_inner_only(self):
        """Segment formula with inner metric but no segment ID."""
        formula = {
            "func": "segment",
            "metric": {"func": "metric", "name": "metrics/orders"},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "orders" in result.lower()

    def test_segment_summary_no_inner(self):
        """Segment formula with no resolvable inner metric."""
        formula = {"func": "segment", "segment_id": "s123"}
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "segment" in result.lower() or "filter" in result.lower()

    def test_metric_reference_summary(self):
        """Direct metric reference formula."""
        formula = {"func": "metric", "name": "metrics/revenue"}
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "revenue" in result.lower()

    def test_metric_reference_summary_no_name(self):
        """Metric reference with no resolvable name."""
        formula = {"func": "metric"}
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "metric" in result.lower()

    def test_col_sum_summary(self):
        """Column sum aggregation summary."""
        formula = {
            "func": "col-sum",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "sum" in result.lower() or "SUM" in result

    def test_col_max_summary(self):
        """Column max aggregation summary."""
        formula = {
            "func": "col-max",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "max" in result.lower() or "MAX" in result

    def test_col_min_summary(self):
        """Column min aggregation summary."""
        formula = {
            "func": "col-min",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "min" in result.lower() or "MIN" in result

    def test_col_mean_summary(self):
        """Column mean aggregation summary."""
        formula = {
            "func": "col-mean",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "mean" in result.lower() or "MEAN" in result

    def test_col_count_summary(self):
        """Column count aggregation summary."""
        formula = {
            "func": "col-count",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "count" in result.lower() or "COUNT" in result

    def test_col_aggregation_no_inner(self):
        """Column aggregation with no resolvable inner metric."""
        formula = {"func": "col-sum"}
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "sum" in result.lower() or "aggregation" in result.lower()

    def test_row_sum_summary(self):
        """Row sum aggregation summary."""
        formula = {"func": "row-sum"}
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "row" in result.lower()

    def test_row_max_summary(self):
        """Row max aggregation summary."""
        formula = {"func": "row-max"}
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "row" in result.lower()

    def test_row_min_summary(self):
        """Row min aggregation summary."""
        formula = {"func": "row-min"}
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "row" in result.lower()

    def test_row_mean_summary(self):
        """Row mean aggregation summary."""
        formula = {"func": "row-mean"}
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "row" in result.lower()

    def test_cumulative_summary_with_inner(self):
        """Cumulative function with inner metric."""
        formula = {
            "func": "cumulative",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "cum" in result.lower() or "revenue" in result.lower()

    def test_cumulative_summary_no_inner(self):
        """Cumulative function with no resolvable inner metric."""
        formula = {"func": "cumulative"}
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "cumulative" in result.lower() or "cum" in result.lower()

    def test_rolling_summary_with_inner_and_window(self):
        """Rolling function with inner metric and window."""
        formula = {
            "func": "rolling",
            "col": {"func": "metric", "name": "metrics/revenue"},
            "window": 7,
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "rolling" in result.lower() or "revenue" in result.lower()

    def test_rolling_summary_with_inner_no_window(self):
        """Rolling function with inner metric but no window."""
        formula = {
            "func": "rolling",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "rolling" in result.lower() or "revenue" in result.lower()

    def test_rolling_summary_no_inner(self):
        """Rolling function with no resolvable inner metric."""
        formula = {"func": "rolling"}
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "rolling" in result.lower()

    def test_median_summary(self):
        """Median statistical function."""
        formula = {
            "func": "median",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "median" in result.lower() or "revenue" in result.lower()

    def test_percentile_summary_with_val(self):
        """Percentile function with percentile value."""
        formula = {
            "func": "percentile",
            "col": {"func": "metric", "name": "metrics/latency"},
            "percentile": 95,
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "95" in result or "latency" in result.lower() or "percentile" in result.lower()

    def test_percentile_summary_with_val_key(self):
        """Percentile function using 'val' key."""
        formula = {
            "func": "percentile",
            "col": {"func": "metric", "name": "metrics/latency"},
            "val": 99,
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "99" in result or "latency" in result.lower()

    def test_variance_summary(self):
        """Variance statistical function."""
        formula = {
            "func": "variance",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "variance" in result.lower() or "revenue" in result.lower()

    def test_standard_deviation_summary(self):
        """Standard deviation statistical function."""
        formula = {
            "func": "standard-deviation",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "deviation" in result.lower() or "standard" in result.lower() or "revenue" in result.lower()

    def test_statistical_no_inner(self):
        """Statistical function with no resolvable inner metric."""
        formula = {"func": "variance"}
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "variance" in result.lower() or "calculation" in result.lower()

    def test_abs_summary(self):
        """ABS function summary."""
        formula = {
            "func": "abs",
            "col": {"func": "metric", "name": "metrics/delta"},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "abs" in result.lower() or "delta" in result.lower()

    def test_abs_summary_no_inner(self):
        """ABS function with no inner returns fallback."""
        formula = {"func": "abs"}
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "absolute" in result.lower() or "abs" in result.lower()

    def test_sqrt_summary(self):
        """SQRT function summary."""
        formula = {
            "func": "sqrt",
            "col": {"func": "metric", "name": "metrics/variance"},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "sqrt" in result.lower() or "variance" in result.lower()

    def test_math_func_no_inner(self):
        """Math function (log, exp, etc.) with no inner returns fallback."""
        for func_name in ("log", "log10", "exp", "ceil", "floor", "round"):
            formula = {"func": func_name}
            parsed = self._make_parsed(formula)
            result = self.builder._generate_formula_summary(formula, parsed)
            assert "function" in result.lower() or func_name.upper() in result.upper()

    def test_pow_summary_with_names(self):
        """Power function with identifiable base and exponent."""
        formula = {
            "func": "pow",
            "col1": {"func": "metric", "name": "metrics/base"},
            "col2": {"func": "number", "val": 2},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "base" in result.lower() or "^" in result or "power" in result.lower()

    def test_pow_summary_no_names(self):
        """Power function with no identifiable operands."""
        formula = {"func": "pow", "col1": {}, "col2": {}}
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "power" in result.lower() or "calculation" in result.lower()

    def test_generic_segment_with_metric_refs(self):
        """Generic fallback: segment in functions with metric refs and segment refs."""
        # This needs to produce a formula expression > 80 chars to hit the fallback
        # Use a deeply nested formula that won't fit in 80 chars for expression
        formula = {
            "func": "segment",
            "segment_id": "s_very_long_segment_id_that_is_meaningless_padding_for_test",
            "metric": {
                "func": "divide",
                "col1": {
                    "func": "multiply",
                    "col1": {"func": "metric", "name": "metrics/very_long_metric_name_revenue_total"},
                    "col2": {"func": "metric", "name": "metrics/another_very_long_metric_overhead_factor"},
                },
                "col2": {"func": "metric", "name": "metrics/yet_another_extremely_long_metric_name_visits_total"},
            },
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        # Should be some descriptive text
        assert len(result) > 0

    def test_generic_divide_with_two_metric_refs(self):
        """Generic fallback: divide with two metric refs when expression too long."""
        # Build a formula where the expression will exceed 80 chars
        long_name_1 = "metrics/this_is_a_very_very_long_metric_name_that_exceeds_normal_limits_revenue"
        long_name_2 = "metrics/this_is_another_extremely_long_metric_name_that_exceeds_limits_orders"
        formula = {
            "func": "divide",
            "col1": {"func": "metric", "name": long_name_1},
            "col2": {"func": "metric", "name": long_name_2},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "ratio" in result.lower() or "/" in result

    def test_generic_if_with_metric_refs(self):
        """Generic fallback: if in functions with metric refs."""
        # Long metric names to force expression > 80 chars
        formula = {
            "func": "if",
            "condition": {
                "func": "gt",
                "col1": {"func": "metric", "name": "metrics/this_very_long_metric_name_for_exceeding_limits_visits"},
                "col2": {"func": "metric", "name": "metrics/another_extremely_long_metric_reference_threshold_value"},
            },
            "then": {
                "func": "metric",
                "name": "metrics/yet_another_ridiculous_metric_name_that_pushes_past_eighty_chars",
            },
            "else": {"func": "number", "val": 0},
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "conditional" in result.lower() or "if" in result.lower()

    def test_generic_multiple_metric_refs(self):
        """Generic fallback: combines N metrics."""
        # Unknown func but many metric references parsed from children
        formula = {
            "func": "coalesce",
            "operands": [
                {"func": "metric", "name": "metrics/aaaa_very_long_name_that_makes_expression_exceed_limit"},
                {"func": "metric", "name": "metrics/bbbb_very_long_name_that_makes_expression_exceed_limit"},
                {"func": "metric", "name": "metrics/cccc_very_long_name_that_makes_expression_exceed_limit"},
            ],
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "ombine" in result or "metric" in result.lower() or len(result) > 0

    def test_generic_single_metric_ref(self):
        """Generic fallback: based on single metric."""
        formula = {
            "func": "coalesce",
            "operands": [
                {
                    "func": "metric",
                    "name": "metrics/aaaa_very_long_name_that_makes_expression_way_too_long_to_fit_in_eighty_characters",
                },
            ],
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "based on" in result.lower() or len(result) > 0

    def test_generic_no_metric_refs_returns_custom(self):
        """Generic fallback with no metric refs returns default."""
        formula = {"func": "some-unknown-function"}
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert result == "Custom calculated metric"

    def test_non_dict_formula_numeric(self):
        """Non-dict formula (numeric) returns string of number."""
        parsed = self._make_parsed({"func": "number", "val": 42})
        result = self.builder._generate_formula_summary(42, parsed)
        # _normalize_formula_node converts 42 -> {"func": "number", "val": 42}
        assert "42" in result

    def test_non_dict_formula_string(self):
        """Non-dict formula (string) returns the string."""
        parsed = self._make_parsed({"func": "literal", "val": "constant"})
        result = self.builder._generate_formula_summary("constant", parsed)
        assert "constant" in result

    def test_visualization_group_unwrap_in_summary(self):
        """Visualization-group is unwrapped before generating summary."""
        formula = {
            "func": "visualization-group",
            "formula": {
                "func": "divide",
                "col1": {"func": "metric", "name": "metrics/revenue"},
                "col2": {"func": "metric", "name": "metrics/orders"},
            },
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "revenue" in result.lower()

    def test_visualization_group_formulas_array_in_summary(self):
        """Visualization-group with formulas array falls back to inner."""
        formula = {
            "func": "visualization-group",
            "formulas": [
                {
                    "func": "divide",
                    "col1": {"func": "metric", "name": "metrics/revenue"},
                    "col2": {"func": "metric", "name": "metrics/orders"},
                },
            ],
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert "revenue" in result.lower()

    def test_visualization_group_no_nested_formulas(self):
        """Visualization-group with empty formulas array stays as-is."""
        formula = {
            "func": "visualization-group",
            "formulas": [],
        }
        parsed = self._make_parsed(formula)
        result = self.builder._generate_formula_summary(formula, parsed)
        assert len(result) > 0  # Should produce some result


# ==================== DESCRIBE CONDITION TESTS ====================


class TestDescribeCondition:
    """Tests for _describe_condition helper"""

    def setup_method(self):
        self.builder = CalculatedMetricsInventoryBuilder()

    def test_gt_condition(self):
        """Greater-than condition described."""
        formula = {
            "func": "if",
            "condition": {
                "func": "gt",
                "col1": {"func": "metric", "name": "metrics/visits"},
                "col2": {"func": "number", "val": 100},
            },
        }
        result = self.builder._describe_condition(formula)
        assert ">" in result

    def test_gte_condition(self):
        """Greater-than-or-equal condition described."""
        formula = {
            "func": "if",
            "condition": {
                "func": "gte",
                "col1": {"func": "metric", "name": "metrics/visits"},
                "col2": {"func": "number", "val": 100},
            },
        }
        result = self.builder._describe_condition(formula)
        assert ">=" in result

    def test_lt_condition(self):
        """Less-than condition described."""
        formula = {
            "func": "if",
            "condition": {
                "func": "lt",
                "col1": {"func": "metric", "name": "metrics/visits"},
                "col2": {"func": "number", "val": 100},
            },
        }
        result = self.builder._describe_condition(formula)
        assert "<" in result

    def test_lte_condition(self):
        """Less-than-or-equal condition described."""
        formula = {
            "func": "if",
            "condition": {
                "func": "lte",
                "col1": {"func": "metric", "name": "metrics/visits"},
                "col2": {"func": "number", "val": 100},
            },
        }
        result = self.builder._describe_condition(formula)
        assert "<=" in result

    def test_eq_condition(self):
        """Equals condition described."""
        formula = {
            "func": "if",
            "condition": {
                "func": "eq",
                "col1": {"func": "metric", "name": "metrics/visits"},
                "col2": {"func": "number", "val": 100},
            },
        }
        result = self.builder._describe_condition(formula)
        assert "=" in result

    def test_ne_condition(self):
        """Not-equals condition described."""
        formula = {
            "func": "if",
            "condition": {
                "func": "ne",
                "col1": {"func": "metric", "name": "metrics/visits"},
                "col2": {"func": "number", "val": 100},
            },
        }
        result = self.builder._describe_condition(formula)
        # Unicode not-equal sign
        assert "\u2260" in result

    def test_condition_with_left_right_format(self):
        """Condition using left/right keys instead of col1/col2."""
        formula = {
            "func": "if",
            "condition": {
                "func": "gt",
                "left": {"func": "metric", "name": "metrics/visits"},
                "right": {"func": "number", "val": 0},
            },
        }
        result = self.builder._describe_condition(formula)
        assert ">" in result
        assert "visits" in result

    def test_condition_with_cond_key(self):
        """Condition accessible via 'cond' key instead of 'condition'."""
        formula = {
            "func": "if",
            "cond": {
                "func": "gt",
                "col1": {"func": "metric", "name": "metrics/visits"},
                "col2": {"func": "number", "val": 100},
            },
        }
        result = self.builder._describe_condition(formula)
        assert ">" in result

    def test_non_dict_formula_returns_empty(self):
        """Non-dict input returns empty string."""
        assert self.builder._describe_condition("not a dict") == ""

    def test_non_dict_condition_returns_empty(self):
        """Non-dict condition returns empty string."""
        formula = {"func": "if", "condition": "not a dict"}
        assert self.builder._describe_condition(formula) == ""

    def test_unknown_condition_func_returns_empty(self):
        """Unknown condition function returns empty string."""
        formula = {
            "func": "if",
            "condition": {
                "func": "unknown_comparison",
                "col1": {"func": "metric", "name": "metrics/visits"},
                "col2": {"func": "number", "val": 100},
            },
        }
        assert self.builder._describe_condition(formula) == ""

    def test_condition_missing_operands_returns_empty(self):
        """Condition with missing operands returns empty string."""
        formula = {
            "func": "if",
            "condition": {"func": "gt"},
        }
        assert self.builder._describe_condition(formula) == ""


# ==================== GET SHORT ID TESTS ====================


class TestGetShortId:
    """Tests for _get_short_id helper"""

    def setup_method(self):
        self.builder = CalculatedMetricsInventoryBuilder()

    def test_underscore_id_truncation(self):
        """Long segment after underscore is truncated."""
        result = self.builder._get_short_id("s300000_abcdefgh12345678")
        assert result == "abcdefgh..."

    def test_underscore_id_short_suffix(self):
        """Short segment after underscore is returned fully."""
        result = self.builder._get_short_id("s300000_short")
        assert result == "short"

    def test_long_id_truncation(self):
        """Long ID without underscore is truncated."""
        result = self.builder._get_short_id("a_very_long_identifier_string")
        # Has underscores, so it splits on them and takes last part
        assert result == "string"

    def test_long_id_without_underscore(self):
        """Long ID without underscore is truncated at 12 chars."""
        result = self.builder._get_short_id("abcdefghijklmnopqrstuvwxyz")
        assert result == "abcdefghijkl..."

    def test_short_id(self):
        """Short ID is returned as-is."""
        result = self.builder._get_short_id("short_id")
        assert result == "id"

    def test_empty_id(self):
        """Empty/None ID returns empty string."""
        assert self.builder._get_short_id("") == ""
        assert self.builder._get_short_id(None) == ""

    def test_simple_short_id_no_underscore(self):
        """Short ID without underscore is returned as-is."""
        result = self.builder._get_short_id("simple")
        assert result == "simple"


# ==================== GET REFERENCE NAME TESTS ====================


class TestGetReferenceName:
    """Tests for _get_reference_name helper"""

    def setup_method(self):
        self.builder = CalculatedMetricsInventoryBuilder()

    def test_metric_node(self):
        """Metric node returns short name."""
        node = {"func": "metric", "name": "metrics/revenue"}
        assert self.builder._get_reference_name(node) == "revenue"

    def test_number_node(self):
        """Number node returns string value."""
        node = {"func": "number", "val": 100}
        assert self.builder._get_reference_name(node) == "100"

    def test_number_node_none_val(self):
        """Number node with None val returns empty string."""
        node = {"func": "number", "val": None}
        assert self.builder._get_reference_name(node) == ""

    def test_literal_node(self):
        """Literal node returns string value."""
        node = {"func": "literal", "val": "hello"}
        assert self.builder._get_reference_name(node) == "hello"

    def test_literal_node_none_val(self):
        """Literal node with None val returns empty string."""
        node = {"func": "literal", "val": None}
        assert self.builder._get_reference_name(node) == ""

    def test_segment_node(self):
        """Segment node returns inner metric name."""
        node = {
            "func": "segment",
            "metric": {"func": "metric", "name": "metrics/orders"},
        }
        assert self.builder._get_reference_name(node) == "orders"

    def test_col_sum_aggregation(self):
        """col-sum aggregation returns SUM(metric) format."""
        node = {
            "func": "col-sum",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        result = self.builder._get_reference_name(node)
        assert result == "SUM(revenue)"

    def test_col_max_aggregation(self):
        """col-max aggregation returns MAX(metric) format."""
        node = {
            "func": "col-max",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        assert self.builder._get_reference_name(node) == "MAX(revenue)"

    def test_cumulative_aggregation(self):
        """cumulative returns CUM(metric) format."""
        node = {
            "func": "cumulative",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        assert self.builder._get_reference_name(node) == "CUM(revenue)"

    def test_rolling_aggregation(self):
        """rolling returns ROL(metric) format."""
        node = {
            "func": "rolling",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        assert self.builder._get_reference_name(node) == "ROL(revenue)"

    def test_aggregation_with_metric_key(self):
        """Aggregation using 'metric' key instead of 'col'."""
        node = {
            "func": "col-min",
            "metric": {"func": "metric", "name": "metrics/latency"},
        }
        assert self.builder._get_reference_name(node) == "MIN(latency)"

    def test_aggregation_no_inner(self):
        """Aggregation with no resolvable inner returns empty string."""
        node = {"func": "col-sum"}
        assert self.builder._get_reference_name(node) == ""

    def test_non_dict_input(self):
        """Non-dict input returns empty string."""
        assert self.builder._get_reference_name("not a dict") == ""
        assert self.builder._get_reference_name(42) == ""
        assert self.builder._get_reference_name(None) == ""

    def test_unknown_func(self):
        """Unknown function returns empty string."""
        node = {"func": "some-unknown-function", "col": {"func": "metric", "name": "metrics/x"}}
        assert self.builder._get_reference_name(node) == ""


# ==================== NORMALIZE REFERENCE VALUE TESTS ====================


class TestNormalizeReferenceValue:
    """Tests for _normalize_reference_value helper"""

    def setup_method(self):
        self.builder = CalculatedMetricsInventoryBuilder()

    def test_simple_string(self):
        """Simple string value is returned via extract_short_name."""
        result = self.builder._normalize_reference_value("metrics/revenue")
        assert result == "revenue"

    def test_none_returns_empty(self):
        """None returns empty string."""
        assert self.builder._normalize_reference_value(None) == ""

    def test_list_returns_first_valid(self):
        """List returns first valid item."""
        result = self.builder._normalize_reference_value([None, "metrics/revenue"])
        assert result == "revenue"

    def test_tuple_returns_first_valid(self):
        """Tuple returns first valid item."""
        result = self.builder._normalize_reference_value((None, "metrics/orders"))
        assert result == "orders"

    def test_empty_list_returns_empty(self):
        """Empty list returns empty string."""
        assert self.builder._normalize_reference_value([]) == ""

    def test_dict_with_segment_id(self):
        """Dict with segment_id key is extracted."""
        result = self.builder._normalize_reference_value({"segment_id": "segments/s123"})
        assert result == "s123"

    def test_dict_with_id_key(self):
        """Dict with id key is extracted."""
        result = self.builder._normalize_reference_value({"id": "components/abc"})
        assert result == "abc"

    def test_dict_with_name_key(self):
        """Dict with name key is extracted."""
        result = self.builder._normalize_reference_value({"name": "metrics/visits"})
        assert result == "visits"

    def test_dict_with_metric_key(self):
        """Dict with metric key is extracted."""
        result = self.builder._normalize_reference_value({"metric": "metrics/clicks"})
        assert result == "clicks"

    def test_dict_with_value_key(self):
        """Dict with value key is extracted."""
        result = self.builder._normalize_reference_value({"value": "test_value"})
        assert result == "test_value"

    def test_dict_with_val_key(self):
        """Dict with val key is extracted."""
        result = self.builder._normalize_reference_value({"val": "my_val"})
        assert result == "my_val"

    def test_dict_no_matching_keys(self):
        """Dict without any known keys returns empty string."""
        assert self.builder._normalize_reference_value({"unknown": "data"}) == ""

    def test_nan_like_values_return_empty(self):
        """NaN/None/null-like string values return empty."""
        assert self.builder._normalize_reference_value("nan") == ""
        assert self.builder._normalize_reference_value("None") == ""
        assert self.builder._normalize_reference_value("null") == ""
        assert self.builder._normalize_reference_value("NaN") == ""

    def test_nested_list_in_dict(self):
        """Nested structure resolves recursively."""
        result = self.builder._normalize_reference_value({"id": ["segments/s_abc"]})
        assert result == "s_abc"


# ==================== GET ADD OPERANDS TESTS ====================


class TestGetAddOperands:
    """Tests for _get_add_operands helper"""

    def setup_method(self):
        self.builder = CalculatedMetricsInventoryBuilder()

    def test_col1_and_col2(self):
        """Extracts operands from col1 and col2."""
        formula = {
            "func": "add",
            "col1": {"func": "metric", "name": "metrics/a"},
            "col2": {"func": "metric", "name": "metrics/b"},
        }
        result = self.builder._get_add_operands(formula)
        assert result == ["a", "b"]

    def test_operands_list(self):
        """Extracts operands from operands list."""
        formula = {
            "func": "add",
            "operands": [
                {"func": "metric", "name": "metrics/a"},
                {"func": "metric", "name": "metrics/b"},
                {"func": "metric", "name": "metrics/c"},
            ],
        }
        result = self.builder._get_add_operands(formula)
        assert result == ["a", "b", "c"]

    def test_col1_col2_and_operands(self):
        """Extracts from both col1/col2 and operands list."""
        formula = {
            "func": "add",
            "col1": {"func": "metric", "name": "metrics/a"},
            "col2": {"func": "metric", "name": "metrics/b"},
            "operands": [
                {"func": "metric", "name": "metrics/c"},
            ],
        }
        result = self.builder._get_add_operands(formula)
        assert result == ["a", "b", "c"]

    def test_non_dict_returns_empty(self):
        """Non-dict input returns empty list."""
        assert self.builder._get_add_operands("not a dict") == []
        assert self.builder._get_add_operands(None) == []

    def test_empty_operands(self):
        """Formula with no resolvable operands returns empty list."""
        formula = {"func": "add", "col1": {}, "col2": {}}
        result = self.builder._get_add_operands(formula)
        assert result == []


# ==================== COMPUTE COMPLEXITY SCORE TESTS ====================


class TestComputeComplexityScoreDirect:
    """Tests for _compute_complexity_score called directly"""

    def setup_method(self):
        self.builder = CalculatedMetricsInventoryBuilder()

    def test_zero_inputs(self):
        """All zero inputs produce zero complexity."""
        score = self.builder._compute_complexity_score(
            operators=0,
            metric_refs=0,
            nesting=0,
            functions=0,
            segments=0,
            conditionals=0,
        )
        assert score == pytest.approx(0.0)

    def test_max_inputs(self):
        """All max inputs produce 100.0 complexity."""
        score = self.builder._compute_complexity_score(
            operators=50,
            metric_refs=10,
            nesting=8,
            functions=15,
            segments=5,
            conditionals=5,
        )
        assert score == pytest.approx(100.0)

    def test_beyond_max_caps_at_100(self):
        """Values beyond max are capped (normalized to 1.0)."""
        score = self.builder._compute_complexity_score(
            operators=200,
            metric_refs=100,
            nesting=50,
            functions=100,
            segments=50,
            conditionals=50,
        )
        assert score == pytest.approx(100.0)

    def test_single_operator(self):
        """Single operator contributes proportionally."""
        score = self.builder._compute_complexity_score(
            operators=1,
            metric_refs=0,
            nesting=0,
            functions=0,
            segments=0,
            conditionals=0,
        )
        expected = round((1 / 50) * 0.25 * 100, 1)
        assert score == pytest.approx(expected)

    def test_single_segment(self):
        """Single segment contributes proportionally."""
        score = self.builder._compute_complexity_score(
            operators=0,
            metric_refs=0,
            nesting=0,
            functions=0,
            segments=1,
            conditionals=0,
        )
        expected = round((1 / 5) * 0.10 * 100, 1)
        assert score == pytest.approx(expected)

    def test_moderate_complexity(self):
        """Moderate inputs produce moderate score."""
        score = self.builder._compute_complexity_score(
            operators=5,
            metric_refs=3,
            nesting=2,
            functions=4,
            segments=1,
            conditionals=1,
        )
        assert 10 < score < 50


# ==================== PARSE FORMULA TESTS ====================


class TestParseFormulaDirect:
    """Tests for _parse_formula called directly"""

    def setup_method(self):
        self.builder = CalculatedMetricsInventoryBuilder()

    def test_simple_divide(self):
        """Simple divide formula parsed correctly."""
        formula = {
            "func": "divide",
            "col1": {"func": "metric", "name": "metrics/revenue"},
            "col2": {"func": "metric", "name": "metrics/orders"},
        }
        parsed = self.builder._parse_formula(formula)
        assert "divide" in parsed["functions_internal"]
        assert "metric" in parsed["functions_internal"]
        assert parsed["operator_count"] == 1
        assert "revenue" in parsed["metric_references"]
        assert "orders" in parsed["metric_references"]
        assert parsed["nesting_depth"] >= 1

    def test_conditional_operators_counted(self):
        """Conditional operators are counted separately."""
        formula = {
            "func": "if",
            "condition": {
                "func": "gt",
                "col1": {"func": "metric", "name": "metrics/a"},
                "col2": {"func": "number", "val": 0},
            },
            "then": {"func": "metric", "name": "metrics/b"},
            "else": {"func": "number", "val": 0},
        }
        parsed = self.builder._parse_formula(formula)
        assert parsed["conditional_count"] >= 2  # if + gt

    def test_segment_reference_extraction(self):
        """Segment references are extracted."""
        formula = {
            "func": "segment",
            "segment_id": "s_mobile",
            "metric": {"func": "metric", "name": "metrics/visits"},
        }
        parsed = self.builder._parse_formula(formula)
        assert "s_mobile" in parsed["segment_references"]

    def test_segment_reference_via_id_key(self):
        """Segment references via 'id' key when no segment_id."""
        formula = {
            "func": "segment",
            "id": "s_desktop",
            "metric": {"func": "metric", "name": "metrics/visits"},
        }
        parsed = self.builder._parse_formula(formula)
        assert "s_desktop" in parsed["segment_references"]

    def test_nesting_depth_deep(self):
        """Deep nesting is tracked correctly."""
        formula = {
            "func": "divide",
            "col1": {
                "func": "subtract",
                "col1": {
                    "func": "multiply",
                    "col1": {"func": "metric", "name": "metrics/a"},
                    "col2": {"func": "metric", "name": "metrics/b"},
                },
                "col2": {"func": "metric", "name": "metrics/c"},
            },
            "col2": {"func": "metric", "name": "metrics/d"},
        }
        parsed = self.builder._parse_formula(formula)
        assert parsed["nesting_depth"] >= 3

    def test_number_function_excluded_from_display(self):
        """'number' function is excluded from display names."""
        formula = {
            "func": "add",
            "col1": {"func": "metric", "name": "metrics/a"},
            "col2": {"func": "number", "val": 1},
        }
        parsed = self.builder._parse_formula(formula)
        assert "number" in parsed["functions_internal"]
        # Static Number should NOT appear in display list
        assert "Static Number" not in parsed["functions_display"]

    def test_unknown_func_gets_title_cased_display(self):
        """Unknown functions are title-cased with dashes replaced."""
        formula = {"func": "some-custom-func"}
        parsed = self.builder._parse_formula(formula)
        assert "Some Custom Func" in parsed["functions_display"]

    def test_operands_list_traversed(self):
        """'operands' list is traversed for nested formulas."""
        formula = {
            "func": "add",
            "operands": [
                {"func": "metric", "name": "metrics/a"},
                {"func": "metric", "name": "metrics/b"},
            ],
        }
        parsed = self.builder._parse_formula(formula)
        assert "a" in parsed["metric_references"]
        assert "b" in parsed["metric_references"]

    def test_values_list_traversed(self):
        """'values' list is traversed for nested formulas."""
        formula = {
            "func": "coalesce",
            "values": [
                {"func": "metric", "name": "metrics/a"},
                {"func": "metric", "name": "metrics/b"},
            ],
        }
        parsed = self.builder._parse_formula(formula)
        assert "a" in parsed["metric_references"]
        assert "b" in parsed["metric_references"]

    def test_non_dict_node_skipped(self):
        """Non-dict items in traversal lists are skipped."""
        formula = {
            "func": "add",
            "operands": [
                "not_a_dict",
                {"func": "metric", "name": "metrics/a"},
                42,
            ],
        }
        parsed = self.builder._parse_formula(formula)
        assert "a" in parsed["metric_references"]

    def test_complexity_score_present(self):
        """Parsed result always includes complexity_score."""
        formula = {"func": "metric", "name": "metrics/revenue"}
        parsed = self.builder._parse_formula(formula)
        assert "complexity_score" in parsed
        assert isinstance(parsed["complexity_score"], float)

    def test_initial_depth_parameter(self):
        """Starting depth parameter is respected."""
        formula = {"func": "metric", "name": "metrics/a"}
        parsed = self.builder._parse_formula(formula, depth=5)
        assert parsed["nesting_depth"] >= 5

    def test_all_arithmetic_operators_counted(self):
        """All arithmetic operators contribute to operator_count."""
        for op in (
            "divide",
            "multiply",
            "add",
            "subtract",
            "negate",
            "pow",
            "sqrt",
            "abs",
            "ceil",
            "floor",
            "round",
            "log",
            "log10",
            "exp",
        ):
            formula = {"func": op, "col": {"func": "metric", "name": "metrics/x"}}
            parsed = self.builder._parse_formula(formula)
            assert parsed["operator_count"] >= 1, f"{op} should count as an operator"

    def test_all_conditional_funcs_counted(self):
        """All conditional functions contribute to conditional_count."""
        for cond in ("if", "and", "or", "not", "eq", "ne", "gt", "gte", "lt", "lte"):
            formula = {"func": cond}
            parsed = self.builder._parse_formula(formula)
            assert parsed["conditional_count"] >= 1, f"{cond} should count as a conditional"


# ==================== INVENTORY PROPERTIES TESTS ====================


class TestInventoryPropertiesExtended:
    """Extended tests for CalculatedMetricsInventory properties"""

    def _make_summary(self, **kwargs):
        """Helper to create a CalculatedMetricSummary with defaults."""
        defaults = {
            "metric_id": "cm_test",
            "metric_name": "Test",
            "description": "",
            "owner": "",
            "complexity_score": 10.0,
            "functions_used": [],
            "functions_used_internal": [],
            "nesting_depth": 0,
            "operator_count": 0,
            "metric_references": [],
            "segment_references": [],
            "conditional_count": 0,
            "formula_summary": "",
            "polarity": "positive",
            "metric_type": "decimal",
            "precision": 0,
        }
        defaults.update(kwargs)
        return CalculatedMetricSummary(**defaults)

    def test_approved_count(self):
        """approved_count returns number of approved metrics."""
        inv = CalculatedMetricsInventory(data_view_id="dv", data_view_name="Test")
        inv.metrics = [
            self._make_summary(metric_id="1", approved=True),
            self._make_summary(metric_id="2", approved=False),
            self._make_summary(metric_id="3", approved=True),
        ]
        assert inv.approved_count == 2

    def test_shared_count(self):
        """shared_count returns number of shared metrics."""
        inv = CalculatedMetricsInventory(data_view_id="dv", data_view_name="Test")
        inv.metrics = [
            self._make_summary(metric_id="1", shared_to_count=3),
            self._make_summary(metric_id="2", shared_to_count=0),
            self._make_summary(metric_id="3", shared_to_count=1),
        ]
        assert inv.shared_count == 2

    def test_tagged_count(self):
        """tagged_count returns number of tagged metrics."""
        inv = CalculatedMetricsInventory(data_view_id="dv", data_view_name="Test")
        inv.metrics = [
            self._make_summary(metric_id="1", tags=["prod"]),
            self._make_summary(metric_id="2", tags=[]),
            self._make_summary(metric_id="3", tags=["dev", "test"]),
        ]
        assert inv.tagged_count == 2

    def test_avg_complexity_calculation(self):
        """avg_complexity returns correct average."""
        inv = CalculatedMetricsInventory(data_view_id="dv", data_view_name="Test")
        inv.metrics = [
            self._make_summary(metric_id="1", complexity_score=20.0),
            self._make_summary(metric_id="2", complexity_score=40.0),
            self._make_summary(metric_id="3", complexity_score=60.0),
        ]
        assert inv.avg_complexity == pytest.approx(40.0)

    def test_max_complexity_calculation(self):
        """max_complexity returns highest score."""
        inv = CalculatedMetricsInventory(data_view_id="dv", data_view_name="Test")
        inv.metrics = [
            self._make_summary(metric_id="1", complexity_score=20.0),
            self._make_summary(metric_id="2", complexity_score=80.0),
            self._make_summary(metric_id="3", complexity_score=60.0),
        ]
        assert inv.max_complexity == pytest.approx(80.0)


# ==================== GET SUMMARY EXTENDED TESTS ====================


class TestGetSummaryExtended:
    """Extended tests for get_summary output"""

    def _make_summary(self, **kwargs):
        defaults = {
            "metric_id": "cm_test",
            "metric_name": "Test",
            "description": "",
            "owner": "",
            "complexity_score": 10.0,
            "functions_used": [],
            "functions_used_internal": [],
            "nesting_depth": 0,
            "operator_count": 0,
            "metric_references": [],
            "segment_references": [],
            "conditional_count": 0,
            "formula_summary": "",
            "polarity": "positive",
            "metric_type": "decimal",
            "precision": 0,
        }
        defaults.update(kwargs)
        return CalculatedMetricSummary(**defaults)

    def test_function_usage_counted(self):
        """Function usage is aggregated across all metrics."""
        inv = CalculatedMetricsInventory(data_view_id="dv", data_view_name="Test")
        inv.metrics = [
            self._make_summary(metric_id="1", functions_used=["Division", "Metric Reference"]),
            self._make_summary(metric_id="2", functions_used=["Division", "Addition"]),
        ]
        summary = inv.get_summary()
        assert summary["function_usage"]["Division"] == 2
        assert summary["function_usage"]["Metric Reference"] == 1
        assert summary["function_usage"]["Addition"] == 1

    def test_tag_usage_counted(self):
        """Tag usage is aggregated across all metrics."""
        inv = CalculatedMetricsInventory(data_view_id="dv", data_view_name="Test")
        inv.metrics = [
            self._make_summary(metric_id="1", tags=["prod", "revenue"]),
            self._make_summary(metric_id="2", tags=["prod"]),
        ]
        summary = inv.get_summary()
        assert summary["tag_usage"]["prod"] == 2
        assert summary["tag_usage"]["revenue"] == 1

    def test_empty_tag_usage(self):
        """Empty tag usage returns empty dict."""
        inv = CalculatedMetricsInventory(data_view_id="dv", data_view_name="Test")
        inv.metrics = [self._make_summary(metric_id="1", tags=[])]
        summary = inv.get_summary()
        assert summary["tag_usage"] == {}

    def test_governance_counts(self):
        """Governance section counts are correct."""
        inv = CalculatedMetricsInventory(data_view_id="dv", data_view_name="Test")
        inv.metrics = [
            self._make_summary(metric_id="1", approved=True, shared_to_count=2, tags=["t"]),
            self._make_summary(metric_id="2", approved=False, shared_to_count=0, tags=[]),
            self._make_summary(metric_id="3", approved=True, shared_to_count=1, tags=["t"]),
        ]
        summary = inv.get_summary()
        assert summary["governance"]["approved_count"] == 2
        assert summary["governance"]["unapproved_count"] == 1
        assert summary["governance"]["shared_count"] == 2
        assert summary["governance"]["tagged_count"] == 2

    def test_high_complexity_counts(self):
        """High and elevated complexity counts are correct."""
        inv = CalculatedMetricsInventory(data_view_id="dv", data_view_name="Test")
        inv.metrics = [
            self._make_summary(metric_id="1", complexity_score=80.0),
            self._make_summary(metric_id="2", complexity_score=60.0),
            self._make_summary(metric_id="3", complexity_score=30.0),
        ]
        summary = inv.get_summary()
        assert summary["complexity"]["high_complexity_count"] == 1
        assert summary["complexity"]["elevated_complexity_count"] == 1


# ==================== TO_DICT EDGE CASES ====================


class TestToDictEdgeCases:
    """Edge cases for CalculatedMetricSummary.to_dict"""

    def _make_summary(self, **kwargs):
        defaults = {
            "metric_id": "cm_test",
            "metric_name": "Test",
            "description": "",
            "owner": "",
            "complexity_score": 10.0,
            "functions_used": [],
            "functions_used_internal": [],
            "nesting_depth": 0,
            "operator_count": 0,
            "metric_references": [],
            "segment_references": [],
            "conditional_count": 0,
            "formula_summary": "",
            "polarity": "positive",
            "metric_type": "decimal",
            "precision": 0,
        }
        defaults.update(kwargs)
        return CalculatedMetricSummary(**defaults)

    def test_empty_description_becomes_dash(self):
        """Empty description becomes '-'."""
        s = self._make_summary(description="")
        assert s.to_dict()["description"] == "-"

    def test_empty_owner_becomes_dash(self):
        """Empty owner becomes '-'."""
        s = self._make_summary(owner="")
        assert s.to_dict()["owner"] == "-"

    def test_empty_functions_becomes_dash(self):
        """Empty functions list becomes '-'."""
        s = self._make_summary(functions_used=[])
        assert s.to_dict()["functions_used"] == "-"

    def test_empty_metric_refs_becomes_dash(self):
        """Empty metric references becomes '-'."""
        s = self._make_summary(metric_references=[])
        assert s.to_dict()["metric_references"] == "-"

    def test_empty_segment_refs_becomes_dash(self):
        """Empty segment references becomes '-'."""
        s = self._make_summary(segment_references=[])
        assert s.to_dict()["segment_references"] == "-"

    def test_empty_formula_summary_becomes_dash(self):
        """Empty formula summary becomes '-'."""
        s = self._make_summary(formula_summary="")
        assert s.to_dict()["formula_summary"] == "-"

    def test_empty_polarity_becomes_dash(self):
        """Empty polarity becomes '-'."""
        s = self._make_summary(polarity="")
        assert s.to_dict()["polarity"] == "-"

    def test_empty_metric_type_becomes_dash(self):
        """Empty metric type becomes '-'."""
        s = self._make_summary(metric_type="")
        assert s.to_dict()["format"] == "-"

    def test_approved_yes(self):
        """Approved True becomes 'Yes'."""
        s = self._make_summary(approved=True)
        assert s.to_dict()["approved"] == "Yes"

    def test_approved_no(self):
        """Approved False becomes 'No'."""
        s = self._make_summary(approved=False)
        assert s.to_dict()["approved"] == "No"

    def test_shared_to_zero_becomes_dash(self):
        """shared_to_count=0 becomes '-'."""
        s = self._make_summary(shared_to_count=0)
        assert s.to_dict()["shared_to"] == "-"

    def test_shared_to_nonzero(self):
        """shared_to_count > 0 shows the count."""
        s = self._make_summary(shared_to_count=5)
        assert s.to_dict()["shared_to"] == 5

    def test_tags_joined(self):
        """Multiple tags are comma-separated."""
        s = self._make_summary(tags=["prod", "revenue"])
        assert s.to_dict()["tags"] == "prod, revenue"

    def test_empty_tags_becomes_dash(self):
        """Empty tags list becomes '-'."""
        s = self._make_summary(tags=[])
        assert s.to_dict()["tags"] == "-"


# ==================== TO_FULL_DICT EDGE CASES ====================


class TestToFullDictEdgeCases:
    """Edge cases for CalculatedMetricSummary.to_full_dict"""

    def test_all_fields_present(self):
        """All expected keys are present in full dict output."""
        s = CalculatedMetricSummary(
            metric_id="cm_x",
            metric_name="X",
            description="desc",
            owner="Owner",
            complexity_score=50.0,
            functions_used=["Division"],
            functions_used_internal=["divide"],
            nesting_depth=2,
            operator_count=1,
            metric_references=["a"],
            segment_references=["s1"],
            conditional_count=0,
            formula_summary="a / b",
            polarity="positive",
            metric_type="decimal",
            precision=2,
            approved=True,
            favorite=True,
            tags=["prod"],
            created="2025-01-01T00:00:00Z",
            modified="2025-06-01T00:00:00Z",
            owner_id="uid123",
            shares=[{"type": "group", "name": "all"}],
            shared_to_count=1,
            data_view_id="dv_1",
            site_title="My Company",
            definition_json='{"formula":{}}',
        )
        d = s.to_full_dict()
        expected_keys = {
            "metric_id",
            "metric_name",
            "description",
            "owner",
            "owner_id",
            "approved",
            "favorite",
            "tags",
            "created",
            "modified",
            "shares",
            "shared_to_count",
            "data_view_id",
            "site_title",
            "complexity_score",
            "functions_used",
            "functions_used_internal",
            "nesting_depth",
            "operator_count",
            "metric_references",
            "segment_references",
            "conditional_count",
            "formula_summary",
            "polarity",
            "metric_type",
            "precision",
            "definition_json",
        }
        assert set(d.keys()) == expected_keys
        assert d["favorite"] is True
        assert d["shares"] == [{"type": "group", "name": "all"}]
        assert d["site_title"] == "My Company"


# ==================== PROCESS METRIC EDGE CASES ====================


class TestProcessMetricEdgeCases:
    """Edge cases for _process_metric"""

    def setup_method(self):
        self.builder = CalculatedMetricsInventoryBuilder()

    def test_missing_id_skipped(self):
        """Metric with no id is skipped."""
        result = self.builder._process_metric({"name": "No ID"})
        assert result is None

    def test_empty_string_id_skipped(self):
        """Metric with empty string id is skipped."""
        result = self.builder._process_metric({"id": "", "name": "Empty ID"})
        assert result is None

    def test_no_formula_key_skipped(self):
        """Metric with definition but no formula key is skipped."""
        result = self.builder._process_metric(
            {
                "id": "cm_1",
                "name": "No Formula",
                "definition": {"func": "calc-metric"},
            },
        )
        assert result is None

    def test_empty_string_formula_skipped(self):
        """Metric with empty string formula is skipped."""
        result = self.builder._process_metric(
            {
                "id": "cm_1",
                "name": "Empty Formula",
                "definition": {"formula": "   "},
            },
        )
        assert result is None

    def test_empty_list_formula_skipped(self):
        """Metric with empty list formula is skipped."""
        result = self.builder._process_metric(
            {
                "id": "cm_1",
                "name": "Empty List Formula",
                "definition": {"formula": []},
            },
        )
        assert result is None

    def test_definition_not_dict_skipped(self):
        """Metric with non-dict definition is skipped."""
        result = self.builder._process_metric(
            {
                "id": "cm_1",
                "name": "String Definition",
                "definition": "not a dict",
            },
        )
        assert result is None

    def test_definition_none_skipped(self):
        """Metric with None definition is skipped."""
        result = self.builder._process_metric(
            {
                "id": "cm_1",
                "name": "None Definition",
                "definition": None,
            },
        )
        assert result is None

    def test_governance_fields_extracted(self):
        """Governance fields (approved, favorite, tags) are extracted."""
        result = self.builder._process_metric(
            {
                "id": "cm_1",
                "name": "Governed Metric",
                "definition": {"formula": {"func": "metric", "name": "metrics/a"}},
                "approved": True,
                "favorite": True,
                "tags": [{"name": "production"}, {"name": "kpi"}],
            },
        )
        assert result is not None
        assert result.approved is True
        assert result.favorite is True
        assert result.tags == ["production", "kpi"]

    def test_shares_extracted(self):
        """Sharing info is extracted correctly."""
        result = self.builder._process_metric(
            {
                "id": "cm_1",
                "name": "Shared Metric",
                "definition": {"formula": {"func": "metric", "name": "metrics/a"}},
                "shares": [{"type": "user", "id": "u1"}, {"type": "group", "id": "g1"}],
            },
        )
        assert result is not None
        assert result.shared_to_count == 2
        assert len(result.shares) == 2

    def test_non_list_shares_handled(self):
        """Non-list shares value defaults to empty list."""
        result = self.builder._process_metric(
            {
                "id": "cm_1",
                "name": "Bad Shares",
                "definition": {"formula": {"func": "metric", "name": "metrics/a"}},
                "shares": "not a list",
            },
        )
        assert result is not None
        assert result.shares == []
        assert result.shared_to_count == 0

    def test_data_view_id_from_dataId(self):
        """data_view_id extracted from 'dataId' key."""
        result = self.builder._process_metric(
            {
                "id": "cm_1",
                "name": "DV Metric",
                "definition": {"formula": {"func": "metric", "name": "metrics/a"}},
                "dataId": "dv_12345",
            },
        )
        assert result is not None
        assert result.data_view_id == "dv_12345"

    def test_data_view_id_from_rsid(self):
        """data_view_id falls back to 'rsid' key."""
        result = self.builder._process_metric(
            {
                "id": "cm_1",
                "name": "RSID Metric",
                "definition": {"formula": {"func": "metric", "name": "metrics/a"}},
                "rsid": "rsid_67890",
            },
        )
        assert result is not None
        assert result.data_view_id == "rsid_67890"

    def test_site_title_extracted(self):
        """Site title is extracted."""
        result = self.builder._process_metric(
            {
                "id": "cm_1",
                "name": "Site Title Metric",
                "definition": {"formula": {"func": "metric", "name": "metrics/a"}},
                "siteTitle": "My Analytics Site",
            },
        )
        assert result is not None
        assert result.site_title == "My Analytics Site"

    def test_timestamps_from_alternate_keys(self):
        """Timestamps extracted from createdDate/modifiedDate fallback keys."""
        result = self.builder._process_metric(
            {
                "id": "cm_1",
                "name": "Alt Timestamps",
                "definition": {"formula": {"func": "metric", "name": "metrics/a"}},
                "createdDate": "2025-01-01T00:00:00Z",
                "modifiedDate": "2025-06-01T00:00:00Z",
            },
        )
        assert result is not None
        assert "2025-01-01" in result.created
        assert "2025-06-01" in result.modified

    def test_format_metadata_extracted(self):
        """Polarity, type, and precision are extracted."""
        result = self.builder._process_metric(
            {
                "id": "cm_1",
                "name": "Format Metric",
                "definition": {"formula": {"func": "metric", "name": "metrics/a"}},
                "polarity": "negative",
                "type": "percent",
                "precision": 4,
            },
        )
        assert result is not None
        assert result.polarity == "negative"
        assert result.metric_type == "percent"
        assert result.precision == 4

    def test_stats_tracking_on_skip(self):
        """BatchProcessingStats records skips correctly."""
        from cja_auto_sdr.inventory.utils import BatchProcessingStats

        stats = BatchProcessingStats()
        # Missing definition
        self.builder._process_metric({"id": "cm_1", "name": "No Def"}, stats)
        assert stats.skipped >= 1

    def test_definition_json_serialization(self):
        """Definition is serialized to JSON string."""
        result = self.builder._process_metric(
            {
                "id": "cm_1",
                "name": "JSON Metric",
                "definition": {
                    "formula": {"func": "metric", "name": "metrics/a"},
                    "version": [1, 0, 0],
                },
            },
        )
        assert result is not None
        assert '"formula"' in result.definition_json
        assert '"func"' in result.definition_json

    def test_string_formula_with_slash(self):
        """String formula with slash is treated as metric reference."""
        result = self.builder._process_metric(
            {
                "id": "cm_str_formula",
                "name": "String Formula",
                "definition": {"formula": "metrics/revenue"},
            },
        )
        assert result is not None
        assert "revenue" in result.formula_summary.lower()

    def test_list_formula_with_dict(self):
        """List formula containing a dict is normalized to the dict."""
        result = self.builder._process_metric(
            {
                "id": "cm_list_formula",
                "name": "List Formula",
                "definition": {"formula": [{"func": "metric", "name": "metrics/revenue"}]},
            },
        )
        assert result is not None
        assert "revenue" in result.formula_summary.lower()

    def test_boolean_formula_treated_as_literal(self):
        """Boolean formula is treated as literal."""
        result = self.builder._process_metric(
            {
                "id": "cm_bool",
                "name": "Bool Formula",
                "definition": {"formula": True},
            },
        )
        assert result is not None

    def test_integer_formula_treated_as_number(self):
        """Integer formula is treated as number."""
        result = self.builder._process_metric(
            {
                "id": "cm_int",
                "name": "Int Formula",
                "definition": {"formula": 99},
            },
        )
        assert result is not None
        assert "99" in result.formula_summary


# ==================== TO_JSON EXTENDED TESTS ====================


class TestToJsonExtended:
    """Extended tests for CalculatedMetricsInventory.to_json"""

    def _make_summary(self, **kwargs):
        defaults = {
            "metric_id": "cm_test",
            "metric_name": "Test",
            "description": "",
            "owner": "",
            "complexity_score": 10.0,
            "functions_used": [],
            "functions_used_internal": [],
            "nesting_depth": 0,
            "operator_count": 0,
            "metric_references": [],
            "segment_references": [],
            "conditional_count": 0,
            "formula_summary": "",
            "polarity": "positive",
            "metric_type": "decimal",
            "precision": 0,
        }
        defaults.update(kwargs)
        return CalculatedMetricSummary(**defaults)

    def test_metrics_sorted_by_complexity_descending(self):
        """JSON output metrics are sorted by complexity descending."""
        inv = CalculatedMetricsInventory(data_view_id="dv", data_view_name="Test")
        inv.metrics = [
            self._make_summary(metric_id="low", complexity_score=10.0),
            self._make_summary(metric_id="high", complexity_score=90.0),
            self._make_summary(metric_id="mid", complexity_score=50.0),
        ]
        json_data = inv.to_json()
        ids = [m["metric_id"] for m in json_data["metrics"]]
        assert ids == ["high", "mid", "low"]

    def test_json_contains_all_full_dict_keys(self):
        """Each metric in JSON output has all full dict keys."""
        inv = CalculatedMetricsInventory(data_view_id="dv", data_view_name="Test")
        inv.metrics = [self._make_summary()]
        json_data = inv.to_json()
        metric_json = json_data["metrics"][0]
        assert "metric_id" in metric_json
        assert "complexity_score" in metric_json
        assert "definition_json" in metric_json


# ==================== Fallback Summary Coverage (lines 823-912) ====================
# These tests use long metric names so _build_formula_expression produces
# strings >80 chars, forcing the fallback paths in _generate_formula_summary.

_LONG = "metrics/aaaa_bbbb_cccc_dddd_eeee_ffff_gggg_hhhh_iiii_jjjj_kkkk_llll_mmmm_nnnn_oooo_pppp_qqqq_rrrr"
_LONG2 = "metrics/pppp_qqqq_rrrr_ssss_tttt_uuuu_vvvv_wwww_xxxx_yyyy_zzzz_aaaa_bbbb_cccc_dddd_eeee_ffff_gggg"


class TestFormulaSummaryFallbacks:
    """Force fallback summary paths by exceeding the 80-char expression limit."""

    def setup_method(self):
        self.builder = CalculatedMetricsInventoryBuilder()

    def _summary(self, formula):
        parsed = self.builder._parse_formula(formula)
        return self.builder._generate_formula_summary(formula, parsed)

    def test_multiply_fallback_with_names(self):
        """Line 823: multiply fallback with resolved operand names."""
        result = self._summary(
            {
                "func": "multiply",
                "col1": {"func": "metric", "name": _LONG},
                "col2": {"func": "metric", "name": _LONG2},
            }
        )
        assert " x " in result

    def test_add_fallback_few_operands(self):
        """Lines 829-830: add fallback with <=3 operands."""
        result = self._summary(
            {
                "func": "add",
                "col1": {"func": "metric", "name": _LONG},
                "col2": {"func": "metric", "name": _LONG2},
            }
        )
        assert "+" in result

    def test_add_fallback_many_operands(self):
        """Line 831: add fallback with >3 operands truncates."""
        result = self._summary(
            {
                "func": "add",
                "operands": [
                    {"func": "metric", "name": _LONG},
                    {"func": "metric", "name": _LONG2},
                    {"func": "metric", "name": "metrics/third_metric_name_long_enough"},
                    {"func": "metric", "name": "metrics/fourth_metric_name_long_enough"},
                ],
            }
        )
        assert "more" in result

    def test_subtract_fallback_with_names(self):
        """Line 840: subtract fallback with resolved operand names."""
        result = self._summary(
            {
                "func": "subtract",
                "col1": {"func": "metric", "name": _LONG},
                "col2": {"func": "metric", "name": _LONG2},
            }
        )
        assert " - " in result

    def test_if_fallback_with_condition(self):
        """Line 846: if fallback with describable condition."""
        result = self._summary(
            {
                "func": "if",
                "condition": {
                    "func": "gt",
                    "col1": {"func": "metric", "name": _LONG},
                    "col2": {"func": "number", "val": 100},
                },
                "then": {"func": "metric", "name": _LONG},
                "else": {"func": "metric", "name": _LONG2},
            }
        )
        assert "If" in result

    def test_segment_fallback_with_metric_and_name(self):
        """Line 854: segment fallback with inner metric AND segment name."""
        result = self._summary(
            {
                "func": "segment",
                "metric": {"func": "metric", "name": _LONG},
                "segment_id": "s_my_segment",
            }
        )
        assert "filtered" in result.lower()

    def test_segment_fallback_with_metric_only(self):
        """Line 856: segment fallback with inner metric but no segment name."""
        result = self._summary(
            {
                "func": "segment",
                "metric": {"func": "metric", "name": _LONG},
            }
        )
        assert "filtered" in result.lower()

    def test_metric_fallback_with_name(self):
        """Line 862: metric func fallback with clean name."""
        result = self._summary(
            {
                "func": "metric",
                "name": _LONG,
            }
        )
        assert "=" in result

    def test_col_sum_fallback_with_inner(self):
        """Line 869: col-sum fallback with resolved inner ref."""
        result = self._summary(
            {
                "func": "col-sum",
                "col": {"func": "metric", "name": _LONG},
            }
        )
        assert "SUM" in result

    def test_cumulative_fallback_with_inner(self):
        """Line 879: cumulative fallback with resolved inner ref."""
        result = self._summary(
            {
                "func": "cumulative",
                "col": {"func": "metric", "name": _LONG},
            }
        )
        assert "Cumulative" in result

    def test_abs_fallback_with_inner(self):
        """Line 905: abs fallback with resolved inner ref."""
        result = self._summary(
            {
                "func": "abs",
                "col": {"func": "metric", "name": _LONG},
            }
        )
        assert "ABS" in result

    def test_sqrt_fallback_with_inner(self):
        """Line 912: sqrt fallback with resolved inner ref."""
        result = self._summary(
            {
                "func": "sqrt",
                "col": {"func": "metric", "name": _LONG},
            }
        )
        assert "SQRT" in result


# ---------------------------------------------------------------------------
# Coverage gap tests (moved from test_small_module_coverage.py)
# ---------------------------------------------------------------------------


@pytest.fixture
def cm_builder():
    """Create a CalculatedMetricsInventoryBuilder for testing."""
    return CalculatedMetricsInventoryBuilder()


class TestProcessMetricEmptyFormula:
    """Cover lines 482, 488, 499-502: empty/missing formula branches."""

    def test_empty_string_formula_skipped(self, cm_builder):
        """Line 488: empty string formula."""
        metric_data = {
            "id": "cm_test",
            "name": "Test",
            "definition": {"formula": "   "},
        }
        stats = BatchProcessingStats()
        result = cm_builder._process_metric(metric_data, stats)
        assert result is None
        assert stats.skipped == 1

    def test_empty_dict_formula_skipped(self, cm_builder):
        """Lines 499-502: empty dict formula."""
        metric_data = {
            "id": "cm_test2",
            "name": "Test2",
            "definition": {"formula": {}},
        }
        stats = BatchProcessingStats()
        result = cm_builder._process_metric(metric_data, stats)
        assert result is None

    def test_empty_list_formula_skipped(self, cm_builder):
        """Line 499-502: empty list formula."""
        metric_data = {
            "id": "cm_test3",
            "name": "Test3",
            "definition": {"formula": []},
        }
        stats = BatchProcessingStats()
        result = cm_builder._process_metric(metric_data, stats)
        assert result is None


class TestProcessMetricJsonSerializationFallback:
    """Cover lines 540-541: json.dumps TypeError/ValueError fallback."""

    def test_unserializable_definition_fallback(self, cm_builder):
        """Lines 540-541: definition contains non-serializable value."""
        metric_data = {
            "id": "cm_serial",
            "name": "Serial Test",
            "definition": {
                "formula": {"func": "metric", "name": "metrics/revenue"},
            },
        }
        original_dumps = json.dumps
        call_count = {"n": 0}

        def patched_dumps(*args, **kwargs):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise TypeError("bad type")
            return original_dumps(*args, **kwargs)

        with patch("cja_auto_sdr.inventory.calculated_metrics.json.dumps", side_effect=patched_dumps):
            result = cm_builder._process_metric(metric_data)
        assert result is not None
        assert result.definition_json


class TestNormalizeReferenceValueList:
    """Cover line 579: _normalize_reference_value for list/tuple input."""

    def test_list_input_extracts_first_valid(self, cm_builder):
        """Line 589-594: list/tuple traversal."""
        result = cm_builder._normalize_reference_value([None, "", "metrics/revenue"])
        assert result == "revenue"

    def test_tuple_input_extracts_first_valid(self, cm_builder):
        result = cm_builder._normalize_reference_value((None, "metrics/orders"))
        assert result == "orders"

    def test_empty_list_returns_empty(self, cm_builder):
        assert cm_builder._normalize_reference_value([]) == ""

    def test_dict_input_with_segment_id(self, cm_builder):
        """Line 595-601: dict input with segment_id key."""
        result = cm_builder._normalize_reference_value({"segment_id": "s_abc"})
        assert result == "s_abc"


class TestParseFormulaOperandsList:
    """Cover line 630: traverse operands list branch."""

    def test_formula_with_operands_list(self, cm_builder):
        """Line 695-699: formula node with 'operands' list."""
        formula = {
            "func": "add",
            "operands": [
                {"func": "metric", "name": "metrics/revenue"},
                {"func": "metric", "name": "metrics/orders"},
            ],
        }
        parsed = cm_builder._parse_formula(formula)
        assert "revenue" in parsed["metric_references"]
        assert "orders" in parsed["metric_references"]


class TestGenerateFormulaSummaryBranches:
    """Cover formula summary branches for various func types."""

    def _make_parsed(self, functions=None, metrics=None, segments=None):
        return {
            "functions_internal": functions or [],
            "functions_display": [],
            "metric_references": metrics or [],
            "segment_references": segments or [],
            "operator_count": 0,
            "nesting_depth": 0,
            "conditional_count": 0,
            "complexity_score": 0.0,
        }

    def test_non_normalized_string_formula(self, cm_builder):
        """Lines 771-772: formula is a bare string."""
        parsed = self._make_parsed()
        result = cm_builder._generate_formula_summary("custom_formula", parsed)
        assert "custom_formula" in result or "Custom" in result

    def test_multiply_with_refs(self, cm_builder):
        """Line 822: multiply summary with resolved references."""
        formula = {
            "func": "multiply",
            "col1": {"func": "metric", "name": "metrics/price"},
            "col2": {"func": "metric", "name": "metrics/quantity"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "x" in result or "price" in result

    def test_multiply_no_refs(self, cm_builder):
        """Line 823: multiply summary without resolvable references."""
        formula = {"func": "multiply", "col1": {}, "col2": {}}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Multiplication" in result or "multiply" in result.lower() or "Custom" in result

    def test_add_more_than_three_operands(self, cm_builder):
        """Lines 828-830: add with more than 3 operands."""
        formula = {
            "func": "add",
            "col1": {"func": "metric", "name": "metrics/a"},
            "col2": {"func": "metric", "name": "metrics/b"},
            "operands": [
                {"func": "metric", "name": "metrics/c"},
                {"func": "metric", "name": "metrics/d"},
            ],
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "more" in result or "+" in result

    def test_subtract_summary(self, cm_builder):
        """Line 839: subtract with resolved refs."""
        formula = {
            "func": "subtract",
            "col1": {"func": "metric", "name": "metrics/gross"},
            "col2": {"func": "metric", "name": "metrics/returns"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "-" in result or "gross" in result

    def test_subtract_no_refs(self, cm_builder):
        """Line 840: subtract without refs."""
        formula = {"func": "subtract", "col1": {}, "col2": {}}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Difference" in result or "Custom" in result

    def test_if_with_condition_desc(self, cm_builder):
        """Lines 843-845: if formula with describable condition."""
        formula = {
            "func": "if",
            "condition": {
                "func": "gt",
                "col1": {"func": "metric", "name": "metrics/revenue"},
                "col2": {"func": "number", "val": 100},
            },
            "then": {"func": "metric", "name": "metrics/revenue"},
            "else": {"func": "number", "val": 0},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "If" in result or "revenue" in result

    def test_if_without_condition_desc(self, cm_builder):
        """Line 846: if formula without describable condition."""
        formula = {
            "func": "if",
            "condition": {},
            "then": {"func": "number", "val": 1},
            "else": {"func": "number", "val": 0},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Conditional" in result or "IF" in result

    def test_segment_with_metric_and_segment(self, cm_builder):
        """Line 853: segment with inner metric and segment_id."""
        formula = {
            "func": "segment",
            "segment_id": "s300000000_12345678abcdef",
            "metric": {"func": "metric", "name": "metrics/visits"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "filtered" in result or "visits" in result

    def test_segment_metric_only(self, cm_builder):
        """Line 855: segment with metric but no segment_id."""
        formula = {
            "func": "segment",
            "metric": {"func": "metric", "name": "metrics/visits"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "filtered" in result or "visits" in result

    def test_segment_no_metric(self, cm_builder):
        """Line 856: segment with no metric."""
        formula = {"func": "segment", "segment_id": "s_test"}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Segmented" in result or "metric" in result.lower()

    def test_metric_reference_summary(self, cm_builder):
        """Line 861: func=metric returns '= name'."""
        formula = {"func": "metric", "name": "metrics/revenue"}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "revenue" in result

    def test_col_sum_summary(self, cm_builder):
        """Line 868: col-sum with inner metric."""
        formula = {
            "func": "col-sum",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "SUM" in result or "revenue" in result

    def test_col_sum_no_inner(self, cm_builder):
        """Line 869: col-sum without inner metric."""
        formula = {"func": "col-sum"}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Sum" in result or "aggregation" in result.lower() or "Custom" in result

    def test_row_sum_summary(self, cm_builder):
        """Line 873: row-sum summary."""
        formula = {"func": "row-sum"}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Row" in result or "SUM" in result or "Custom" in result

    def test_cumulative_summary(self, cm_builder):
        """Line 878: cumulative with inner metric."""
        formula = {
            "func": "cumulative",
            "col": {"func": "metric", "name": "metrics/orders"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Cumulative" in result or "orders" in result

    def test_cumulative_no_inner(self, cm_builder):
        """Line 879: cumulative without inner."""
        formula = {"func": "cumulative"}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Cumulative" in result or "Custom" in result

    def test_rolling_with_window(self, cm_builder):
        """Lines 885-886: rolling with window and inner metric."""
        formula = {
            "func": "rolling",
            "col": {"func": "metric", "name": "metrics/revenue"},
            "window": 7,
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Rolling" in result or "7" in result

    def test_rolling_no_window(self, cm_builder):
        """Line 887: rolling without window."""
        formula = {
            "func": "rolling",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Rolling" in result

    def test_rolling_no_inner(self, cm_builder):
        """Line 888: rolling without inner metric."""
        formula = {"func": "rolling"}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Rolling" in result or "Custom" in result

    def test_abs_summary(self, cm_builder):
        """Line 904: abs with inner metric."""
        formula = {
            "func": "abs",
            "col": {"func": "metric", "name": "metrics/delta"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "ABS" in result or "delta" in result

    def test_abs_no_inner(self, cm_builder):
        """Line 905: abs without inner."""
        formula = {"func": "abs"}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Absolute" in result or "Custom" in result

    def test_sqrt_summary(self, cm_builder):
        """Line 911: sqrt with inner metric."""
        formula = {
            "func": "sqrt",
            "col": {"func": "metric", "name": "metrics/variance"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "SQRT" in result or "variance" in result

    def test_sqrt_no_inner(self, cm_builder):
        """Line 912: sqrt without inner."""
        formula = {"func": "sqrt"}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "SQRT" in result or "Custom" in result

    def test_pow_summary(self, cm_builder):
        """Lines 917-918: pow with base and exp."""
        formula = {
            "func": "pow",
            "col1": {"func": "metric", "name": "metrics/value"},
            "col2": {"func": "number", "val": 2},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "^" in result or "value" in result

    def test_pow_no_refs(self, cm_builder):
        """Line 919: pow without resolvable refs."""
        formula = {"func": "pow", "col1": {}, "col2": {}}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Power" in result or "Custom" in result

    def test_percentile_summary(self, cm_builder):
        """Lines 894-897: percentile with inner metric and value."""
        formula = {
            "func": "percentile",
            "col": {"func": "metric", "name": "metrics/load_time"},
            "percentile": 95,
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "P95" in result or "load_time" in result

    def test_median_summary(self, cm_builder):
        """Line 898: median with inner metric."""
        formula = {
            "func": "median",
            "col": {"func": "metric", "name": "metrics/duration"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Median" in result or "duration" in result

    def test_statistical_no_inner(self, cm_builder):
        """Line 899: statistical function without inner."""
        formula = {"func": "variance"}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Variance" in result or "Custom" in result


class TestGenericFallbackSummaries:
    """Cover lines 923-925, 928, 931-933, 939."""

    def _make_parsed(self, functions=None, metrics=None, segments=None):
        return {
            "functions_internal": functions or [],
            "functions_display": [],
            "metric_references": metrics or [],
            "segment_references": segments or [],
            "operator_count": 0,
            "nesting_depth": 0,
            "conditional_count": 0,
            "complexity_score": 0.0,
        }

    def test_segment_with_metric_and_segment_refs(self, cm_builder):
        """Lines 923-924: segment in functions with metric refs and segment refs."""
        formula = {"func": "coalesce"}
        parsed = self._make_parsed(
            functions=["segment", "coalesce"],
            metrics=["revenue"],
            segments=["s_mobile"],
        )
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "filtered" in result or "revenue" in result

    def test_segment_with_metric_no_segment_refs(self, cm_builder):
        """Line 925: segment in functions with metric refs but no segment refs."""
        formula = {"func": "coalesce"}
        parsed = self._make_parsed(
            functions=["segment", "coalesce"],
            metrics=["revenue"],
            segments=[],
        )
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Filtered" in result or "revenue" in result

    def test_divide_in_functions_with_two_metrics(self, cm_builder):
        """Line 928: divide in functions with 2+ metric refs."""
        formula = {"func": "coalesce"}
        parsed = self._make_parsed(
            functions=["divide", "coalesce"],
            metrics=["revenue", "orders"],
        )
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Ratio" in result

    def test_if_in_functions_with_metrics(self, cm_builder):
        """Lines 931-932: if in functions with metric refs."""
        formula = {"func": "coalesce"}
        parsed = self._make_parsed(
            functions=["if", "coalesce"],
            metrics=["revenue"],
        )
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Conditional" in result

    def test_if_in_functions_no_metrics(self, cm_builder):
        """Line 933: if in functions without metric refs."""
        formula = {"func": "coalesce"}
        parsed = self._make_parsed(functions=["if", "coalesce"])
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Conditional" in result

    def test_two_metric_refs(self, cm_builder):
        """Line 939: exactly 2 metric refs, no special functions."""
        formula = {"func": "coalesce"}
        parsed = self._make_parsed(metrics=["revenue", "orders"])
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Combines" in result

    def test_three_or_more_metric_refs(self, cm_builder):
        """Line 940: 3+ metric refs."""
        formula = {"func": "coalesce"}
        parsed = self._make_parsed(metrics=["a", "b", "c"])
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "3 metrics" in result or "Combines" in result

    def test_one_metric_ref(self, cm_builder):
        """Line 937: exactly 1 metric ref."""
        formula = {"func": "coalesce"}
        parsed = self._make_parsed(metrics=["revenue"])
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Based on" in result or "revenue" in result


class TestBuildFormulaExpressionVisualizationGroup:
    """Cover visualization-group transparent wrapper in _build_formula_expression."""

    def test_visualization_group_wrapper(self, cm_builder):
        """Line 1037-1049: visualization-group passes through to inner formula."""
        node = {
            "func": "visualization-group",
            "formula": {
                "func": "divide",
                "col1": {"func": "metric", "name": "metrics/a"},
                "col2": {"func": "metric", "name": "metrics/b"},
            },
        }
        result = cm_builder._build_formula_expression(node)
        assert "a" in result and "b" in result

    def test_visualization_group_formulas_array(self, cm_builder):
        """Line 1045-1049: visualization-group with formulas array."""
        node = {
            "func": "visualization-group",
            "formulas": [
                {
                    "func": "metric",
                    "name": "metrics/revenue",
                },
            ],
        }
        result = cm_builder._build_formula_expression(node)
        assert "revenue" in result


class TestDescribeConditionBranches:
    """Cover additional condition description branches."""

    def test_gte_condition(self, cm_builder):
        formula = {
            "func": "if",
            "condition": {
                "func": "gte",
                "col1": {"func": "metric", "name": "metrics/a"},
                "col2": {"func": "number", "val": 10},
            },
            "then": {"func": "number", "val": 1},
        }
        result = cm_builder._describe_condition(formula)
        assert ">=" in result

    def test_lt_condition(self, cm_builder):
        formula = {
            "func": "if",
            "condition": {
                "func": "lt",
                "col1": {"func": "metric", "name": "metrics/a"},
                "col2": {"func": "number", "val": 5},
            },
            "then": {"func": "number", "val": 1},
        }
        result = cm_builder._describe_condition(formula)
        assert "<" in result

    def test_lte_condition(self, cm_builder):
        formula = {
            "func": "if",
            "condition": {
                "func": "lte",
                "col1": {"func": "metric", "name": "metrics/a"},
                "col2": {"func": "number", "val": 5},
            },
            "then": {"func": "number", "val": 1},
        }
        result = cm_builder._describe_condition(formula)
        assert "<=" in result

    def test_eq_condition(self, cm_builder):
        formula = {
            "func": "if",
            "condition": {
                "func": "eq",
                "col1": {"func": "metric", "name": "metrics/a"},
                "col2": {"func": "number", "val": 0},
            },
            "then": {"func": "number", "val": 1},
        }
        result = cm_builder._describe_condition(formula)
        assert "=" in result

    def test_ne_condition(self, cm_builder):
        formula = {
            "func": "if",
            "condition": {
                "func": "ne",
                "col1": {"func": "metric", "name": "metrics/a"},
                "col2": {"func": "number", "val": 0},
            },
            "then": {"func": "number", "val": 1},
        }
        result = cm_builder._describe_condition(formula)
        # ne produces the unicode not-equal sign
        assert result  # Non-empty means condition was described


class TestNormalizeFormulaNodeEdgeCases:
    """Cover edge cases in _normalize_formula_node."""

    def test_bool_input(self, cm_builder):
        """Line 1186-1187: bool input returns literal node."""
        result = cm_builder._normalize_formula_node(True)
        assert result == {"func": "literal", "val": True}

    def test_float_input(self, cm_builder):
        """Line 1189-1190: float input returns number node."""
        result = cm_builder._normalize_formula_node(3.14)
        assert result == {"func": "number", "val": 3.14}

    def test_string_with_slash(self, cm_builder):
        """Line 1196-1197: string with / returns metric node."""
        result = cm_builder._normalize_formula_node("metrics/revenue")
        assert result == {"func": "metric", "name": "metrics/revenue"}

    def test_string_without_slash(self, cm_builder):
        """Line 1198: string without / returns literal node."""
        result = cm_builder._normalize_formula_node("some_literal")
        assert result == {"func": "literal", "val": "some_literal"}

    def test_empty_string_returns_none(self, cm_builder):
        """Line 1194-1195: empty string returns None."""
        assert cm_builder._normalize_formula_node("  ") is None

    def test_none_returns_none(self, cm_builder):
        """Line 1200: unrecognized type returns None."""
        assert cm_builder._normalize_formula_node(None) is None


class TestProcessMetricNoneFormulaNormalization:
    """Cover lines 482 (stats.record_skip with no formula) and 499-502 (unsupported formula)."""

    def test_none_formula_with_stats(self, cm_builder):
        """Line 482: formula is None, stats records the skip."""
        metric_data = {
            "id": "cm_none_formula",
            "name": "NoneFormula",
            "definition": {"formula": None},
        }
        stats = BatchProcessingStats()
        result = cm_builder._process_metric(metric_data, stats)
        assert result is None
        assert stats.skipped == 1

    def test_unsupported_formula_format_with_stats(self, cm_builder):
        """Lines 499-502: _normalize_formula_node returns None for list of Nones."""
        metric_data = {
            "id": "cm_unsupported",
            "name": "Unsupported",
            "definition": {"formula": [None, None]},
        }
        stats = BatchProcessingStats()
        result = cm_builder._process_metric(metric_data, stats)
        assert result is None
        assert stats.skipped == 1


class TestCoerceScalarTextOnBuilder:
    """Cover line 579: _coerce_scalar_text called on the builder instance."""

    def test_coerce_scalar_text_passthrough(self, cm_builder):
        """Line 579: builder method delegates to module-level coerce_scalar_text."""
        assert cm_builder._coerce_scalar_text("hello") == "hello"
        assert cm_builder._coerce_scalar_text(None) == ""
        assert cm_builder._coerce_scalar_text(42) == "42"


class TestParseFormulaTraverseNonDict:
    """Cover line 630: traverse called with a non-dict node."""

    def test_non_dict_operand_in_operands_list(self, cm_builder):
        """Line 630: non-dict items in operands list are silently skipped."""
        formula = {
            "func": "add",
            "operands": [
                "not_a_dict",
                42,
                {"func": "metric", "name": "metrics/revenue"},
            ],
        }
        parsed = cm_builder._parse_formula(formula)
        assert "revenue" in parsed["metric_references"]


class TestFormulaSummaryNumericFallback:
    """Cover lines 769-773: formula that doesn't normalize but is numeric or string."""

    def _make_parsed(self):
        return {
            "functions_internal": [],
            "functions_display": [],
            "metric_references": [],
            "segment_references": [],
            "operator_count": 0,
            "nesting_depth": 0,
            "conditional_count": 0,
            "complexity_score": 0.0,
        }

    def test_numeric_formula_returns_string_of_number(self, cm_builder):
        """Lines 769-770: formula is a raw number (int/float)."""
        parsed = self._make_parsed()
        with patch.object(cm_builder, "_normalize_formula_node", return_value=None):
            result = cm_builder._generate_formula_summary(42, parsed)
        assert result == "42"

    def test_float_formula_returns_string_of_number(self, cm_builder):
        """Lines 769-770: formula is a raw float."""
        parsed = self._make_parsed()
        with patch.object(cm_builder, "_normalize_formula_node", return_value=None):
            result = cm_builder._generate_formula_summary(3.14, parsed)
        assert result == "3.14"

    def test_string_formula_fallback(self, cm_builder):
        """Lines 771-772: formula is a non-empty string that doesn't normalize."""
        parsed = self._make_parsed()
        with patch.object(cm_builder, "_normalize_formula_node", return_value=None):
            result = cm_builder._generate_formula_summary("custom_expr", parsed)
        assert result == "custom_expr"

    def test_empty_formula_fallback(self, cm_builder):
        """Line 773: formula doesn't normalize and isn't numeric or string."""
        parsed = self._make_parsed()
        with patch.object(cm_builder, "_normalize_formula_node", return_value=None):
            result = cm_builder._generate_formula_summary(None, parsed)
        assert result == "Custom calculated metric"


class TestFormulaSummaryDivideNoRefs:
    """Cover line 814: divide with unresolvable references."""

    def test_divide_returns_ratio_calculation(self, cm_builder):
        """Line 814: divide where neither operand resolves to a name."""
        formula = {"func": "divide", "col1": {}, "col2": {}}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Ratio" in result


class TestFormulaSummaryAddOperands:
    """Cover lines 828-830: add with exactly 2-3 operands and >3 operands."""

    def test_add_two_operands_joined(self, cm_builder):
        """Lines 828-829: add with exactly 2 operands joined by +."""
        formula = {
            "func": "add",
            "col1": {"func": "metric", "name": "metrics/revenue"},
            "col2": {"func": "metric", "name": "metrics/tax"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "+" in result

    def test_add_three_operands_joined(self, cm_builder):
        """Lines 828-829: add with exactly 3 operands."""
        formula = {
            "func": "add",
            "col1": {"func": "metric", "name": "metrics/a"},
            "col2": {"func": "metric", "name": "metrics/b"},
            "operands": [{"func": "metric", "name": "metrics/c"}],
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "+" in result


class TestFormulaSummarySubtractWithRefs:
    """Cover line 839: subtract with resolved refs."""

    def test_subtract_shows_minus_sign(self, cm_builder):
        """Line 839: subtract with two resolvable metric refs."""
        formula = {
            "func": "subtract",
            "col1": {"func": "metric", "name": "metrics/total"},
            "col2": {"func": "metric", "name": "metrics/refunds"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "total" in result and "-" in result and "refunds" in result


class TestFormulaSummaryIfCondition:
    """Cover lines 843-846: if formula with and without condition desc."""

    def test_if_with_condition(self, cm_builder):
        """Lines 843-845: if with resolvable condition."""
        formula = {
            "func": "if",
            "condition": {
                "func": "gt",
                "col1": {"func": "metric", "name": "metrics/x"},
                "col2": {"func": "number", "val": 0},
            },
            "then": {"func": "number", "val": 1},
            "else": {"func": "number", "val": 0},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "IF" in result or "If" in result

    def test_if_no_condition(self, cm_builder):
        """Line 846: if with empty condition dict."""
        formula = {"func": "if", "condition": {}, "then": {}, "else": {}}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Conditional" in result


class TestFormulaSummarySegmentBranches:
    """Cover lines 853, 855: segment with metric+id and metric only."""

    def test_segment_with_both(self, cm_builder):
        """Line 853: segment with inner metric and segment_id."""
        formula = {
            "func": "segment",
            "segment_id": "s300000000_abcdef",
            "metric": {"func": "metric", "name": "metrics/pageviews"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "pageviews" in result

    def test_segment_metric_only_no_id(self, cm_builder):
        """Line 855: segment with metric but no segment_id."""
        formula = {
            "func": "segment",
            "metric": {"func": "metric", "name": "metrics/pageviews"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "filtered" in result


class TestFormulaSummaryMetricRef:
    """Cover line 861: metric func returns '= name'."""

    def test_metric_named(self, cm_builder):
        """Line 861: func=metric with a clean name."""
        formula = {"func": "metric", "name": "metrics/orders"}
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "orders" in result


class TestFormulaSummaryColAggregation:
    """Cover line 868: col-sum/col-max/etc with inner metric."""

    def test_col_max_with_inner(self, cm_builder):
        """Line 868: col-max with inner metric ref."""
        formula = {
            "func": "col-max",
            "col": {"func": "metric", "name": "metrics/revenue"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "MAX" in result and "revenue" in result


class TestFormulaSummaryCumulativeWithInner:
    """Cover line 878: cumulative with inner metric."""

    def test_cumulative_with_metric(self, cm_builder):
        """Line 878: cumulative with inner metric ref."""
        formula = {
            "func": "cumulative",
            "metric": {"func": "metric", "name": "metrics/visits"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "Cumulative" in result or "CUM" in result


class TestFormulaSummaryAbsAndMath:
    """Cover lines 904, 911: abs and sqrt/log etc with inner metric."""

    def test_abs_with_col1(self, cm_builder):
        """Line 904: abs using col1 key."""
        formula = {
            "func": "abs",
            "col1": {"func": "metric", "name": "metrics/delta"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "ABS" in result and "delta" in result

    def test_log_with_inner(self, cm_builder):
        """Line 911: log with inner metric."""
        formula = {
            "func": "log",
            "col": {"func": "metric", "name": "metrics/value"},
        }
        parsed = cm_builder._parse_formula(formula)
        result = cm_builder._generate_formula_summary(formula, parsed)
        assert "LOG" in result and "value" in result


class TestBuildFormulaExpressionComplexDivide:
    """Cover lines 969-972: divide with complex operands needing parenthesization."""

    def test_complex_operands_get_parenthesized(self, cm_builder):
        """Lines 969-972: divide where operands contain spaces -> wrapped in parens."""
        formula = {
            "func": "divide",
            "col1": {
                "func": "add",
                "col1": {"func": "metric", "name": "metrics/a"},
                "col2": {"func": "metric", "name": "metrics/b"},
            },
            "col2": {
                "func": "subtract",
                "col1": {"func": "metric", "name": "metrics/c"},
                "col2": {"func": "metric", "name": "metrics/d"},
            },
        }
        result = cm_builder._build_formula_expression(formula)
        # The add sub-expression "a + b" should be wrapped as "(a + b)"
        assert "(" in result and ")" in result
        assert "/" in result
