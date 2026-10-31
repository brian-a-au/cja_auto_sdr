"""
Test suite for CJA Segments Inventory

Tests cover:
- Parsing segment definitions
- Inventory generation
- Complexity score calculation
- Definition summary generation
- DataFrame output
"""

import json
import os
import subprocess
import sys
import textwrap
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest

from cja_auto_sdr.inventory.segments import (
    SegmentsInventory,
    SegmentsInventoryBuilder,
    SegmentSummary,
)

# ==================== FIXTURES ====================


@pytest.fixture
def sample_simple_segment():
    """Simple segment: Page URL contains 'checkout'"""
    return {
        "id": "s_checkout_pages",
        "name": "Checkout Pages",
        "description": "Pages in the checkout funnel",
        "owner": {"name": "Test Owner"},
        "definition": {
            "func": "container",
            "context": "hits",
            "pred": {"func": "contains", "dimension": "variables/pageurl", "val": "checkout"},
        },
    }


@pytest.fixture
def sample_complex_segment():
    """Complex segment with multiple conditions"""
    return {
        "id": "s_high_value_mobile",
        "name": "High Value Mobile Visitors",
        "description": "Mobile visitors with revenue > 100 and orders >= 3",
        "owner": {"name": "Analytics Team"},
        "definition": {
            "func": "container",
            "context": "visitors",
            "pred": {
                "func": "and",
                "preds": [
                    {"func": "eq", "dimension": "variables/mobiledevicetype", "val": "Mobile Phone"},
                    {"func": "gt", "metric": "metrics/revenue", "val": 100},
                    {"func": "gte", "metric": "metrics/orders", "val": 3},
                ],
            },
        },
    }


@pytest.fixture
def sample_nested_segment():
    """Deeply nested segment for complexity testing"""
    return {
        "id": "s_complex_nested",
        "name": "Complex Nested Segment",
        "description": "Complex nested conditions",
        "owner": {"name": "Data Team"},
        "definition": {
            "func": "container",
            "context": "visits",
            "pred": {
                "func": "and",
                "preds": [
                    {
                        "func": "or",
                        "preds": [
                            {"func": "eq", "dimension": "variables/channel", "val": "paid"},
                            {"func": "eq", "dimension": "variables/channel", "val": "organic"},
                        ],
                    },
                    {
                        "func": "and",
                        "preds": [
                            {"func": "gt", "metric": "metrics/pageviews", "val": 5},
                            {"func": "exists", "dimension": "variables/purchaseid"},
                        ],
                    },
                ],
            },
        },
    }


@pytest.fixture
def sample_sequence_segment():
    """Segment with sequential conditions"""
    return {
        "id": "s_checkout_sequence",
        "name": "Checkout Funnel Sequence",
        "description": "Users who went through checkout steps in order",
        "owner": {"name": "Test User"},
        "definition": {
            "func": "container",
            "context": "visitors",
            "pred": {
                "func": "sequence",
                "checkpoints": [
                    {
                        "func": "container",
                        "context": "hits",
                        "pred": {"func": "eq", "dimension": "variables/pagename", "val": "Cart"},
                    },
                    {
                        "func": "container",
                        "context": "hits",
                        "pred": {"func": "eq", "dimension": "variables/pagename", "val": "Checkout"},
                    },
                    {
                        "func": "container",
                        "context": "hits",
                        "pred": {"func": "eq", "dimension": "variables/pagename", "val": "Thank You"},
                    },
                ],
            },
        },
    }


@pytest.fixture
def sample_exclude_segment():
    """Segment with exclusion logic"""
    return {
        "id": "s_non_internal",
        "name": "Non-Internal Traffic",
        "description": "All traffic excluding internal IPs",
        "owner": {"name": "Test"},
        "definition": {
            "func": "container",
            "context": "hits",
            "pred": {
                "func": "and",
                "preds": [
                    {"func": "exists", "dimension": "variables/pageurl"},
                    {
                        "func": "exclude",
                        "container": {"func": "contains", "dimension": "variables/ipaddress", "val": "192.168"},
                    },
                ],
            },
        },
    }


@pytest.fixture
def sample_regex_segment():
    """Segment with regex pattern matching"""
    return {
        "id": "s_product_pages",
        "name": "Product Detail Pages",
        "description": "Pages matching product URL pattern",
        "owner": {"name": "Test"},
        "definition": {
            "func": "container",
            "context": "hits",
            "pred": {"func": "matches", "dimension": "variables/pageurl", "val": "^/products/[a-z0-9-]+$"},
        },
    }


@pytest.fixture
def mock_cja_instance(sample_simple_segment, sample_complex_segment):
    """Create a mock CJA instance with segments"""
    mock_cja = Mock()
    mock_cja.getFilters.return_value = pd.DataFrame([sample_simple_segment, sample_complex_segment])
    return mock_cja


@pytest.fixture
def mock_cja_instance_list_response(sample_simple_segment, sample_complex_segment):
    """Create a mock CJA instance that returns a list (not DataFrame)"""
    mock_cja = Mock()
    mock_cja.getFilters.return_value = [sample_simple_segment, sample_complex_segment]
    return mock_cja


@pytest.fixture
def mock_cja_instance_empty():
    """Create a mock CJA instance with no segments"""
    mock_cja = Mock()
    mock_cja.getFilters.return_value = pd.DataFrame()
    return mock_cja


# ==================== BUILDER TESTS ====================


class TestSegmentsInventoryBuilder:
    """Tests for SegmentsInventoryBuilder class"""

    def test_build_basic(self, mock_cja_instance):
        """Test basic inventory building"""
        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja_instance, "dv_test", "Test View")

        assert isinstance(inventory, SegmentsInventory)
        assert inventory.data_view_id == "dv_test"
        assert inventory.data_view_name == "Test View"
        assert inventory.total_segments == 2

    def test_build_from_list_response(self, mock_cja_instance_list_response):
        """Test building when API returns a list instead of DataFrame"""
        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja_instance_list_response, "dv_test", "Test")

        assert inventory.total_segments == 2

    def test_build_empty(self, mock_cja_instance_empty):
        """Test building with no segments"""
        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja_instance_empty, "dv_empty", "Empty")

        assert inventory.total_segments == 0

    def test_api_called_with_correct_params(self, mock_cja_instance):
        """Test that API is called with correct parameters"""
        builder = SegmentsInventoryBuilder()
        builder.build(mock_cja_instance, "dv_abc123", "Test")

        mock_cja_instance.getFilters.assert_called_once_with(dataIds="dv_abc123", full=True)

    def test_complexity_score_calculated(self, mock_cja_instance):
        """Test that complexity scores are calculated"""
        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja_instance, "dv_test", "Test")

        for segment in inventory.segments:
            assert 0 <= segment.complexity_score <= 100

    def test_dimension_references_extracted(self, sample_simple_segment):
        """Test that dimension references are extracted correctly"""
        mock_cja = Mock()
        mock_cja.getFilters.return_value = [sample_simple_segment]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert len(inventory.segments) == 1
        segment = inventory.segments[0]
        assert "pageurl" in segment.dimension_references

    def test_metric_references_extracted(self, sample_complex_segment):
        """Test that metric references are extracted correctly"""
        mock_cja = Mock()
        mock_cja.getFilters.return_value = [sample_complex_segment]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert len(inventory.segments) == 1
        segment = inventory.segments[0]
        assert "revenue" in segment.metric_references
        assert "orders" in segment.metric_references

    def test_functions_extracted(self, sample_simple_segment):
        """Test that functions are extracted correctly"""
        mock_cja = Mock()
        mock_cja.getFilters.return_value = [sample_simple_segment]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        segment = inventory.segments[0]
        assert "Contains" in segment.functions_used

    def test_owner_extracted(self, sample_simple_segment):
        """Test that owner is extracted from nested structure"""
        mock_cja = Mock()
        mock_cja.getFilters.return_value = [sample_simple_segment]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        segment = inventory.segments[0]
        assert segment.owner == "Test Owner"

    def test_container_type_extracted(self, sample_simple_segment):
        """Test that container type (context) is extracted"""
        mock_cja = Mock()
        mock_cja.getFilters.return_value = [sample_simple_segment]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        segment = inventory.segments[0]
        assert segment.container_type == "hits"

    def test_missing_definition_skipped(self):
        """Test that segments without definitions are skipped"""
        segment_no_def = {
            "id": "s_no_def",
            "name": "No Definition",
            "description": "",
            "owner": {"name": "Test"},
        }
        mock_cja = Mock()
        mock_cja.getFilters.return_value = [segment_no_def]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert inventory.total_segments == 0

    def test_nan_id_skipped(self):
        """Segments with NaN IDs should be skipped."""
        segment_nan_id = {
            "id": float("nan"),
            "name": "NaN ID Segment",
            "description": "",
            "owner": {"name": "Test"},
            "definition": {"func": "segment", "container": {}},
        }
        mock_cja = Mock()
        mock_cja.getFilters.return_value = [segment_nan_id]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert inventory.total_segments == 0


# ==================== INVENTORY TESTS ====================


class TestSegmentsInventory:
    """Tests for SegmentsInventory class"""

    def test_get_dataframe(self, mock_cja_instance):
        """Test DataFrame output"""
        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja_instance, "dv_test", "Test")

        df = inventory.get_dataframe()

        assert isinstance(df, pd.DataFrame)
        assert len(df) == inventory.total_segments
        assert "name" in df.columns
        assert "complexity_score" in df.columns
        assert "functions_used" in df.columns
        assert "definition_summary" in df.columns
        assert "container_type" in df.columns

    def test_get_dataframe_sorted_by_complexity(self, mock_cja_instance):
        """Test that DataFrame is sorted by complexity score descending"""
        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja_instance, "dv_test", "Test")

        df = inventory.get_dataframe()

        scores = df["complexity_score"].tolist()
        assert scores == sorted(scores, reverse=True)

    def test_get_summary(self, mock_cja_instance):
        """Test summary statistics"""
        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja_instance, "dv_test", "Test")

        summary = inventory.get_summary()

        assert "data_view_id" in summary
        assert "data_view_name" in summary
        assert "total_segments" in summary
        assert "complexity" in summary
        assert "function_usage" in summary
        assert "container_types" in summary

    def test_to_json(self, mock_cja_instance):
        """Test JSON export"""
        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja_instance, "dv_test", "Test")

        json_data = inventory.to_json()

        assert "summary" in json_data
        assert "segments" in json_data
        assert len(json_data["segments"]) == inventory.total_segments

    def test_empty_inventory_dataframe(self, mock_cja_instance_empty):
        """Test DataFrame output for empty inventory"""
        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja_instance_empty, "dv_test", "Test")

        df = inventory.get_dataframe()

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert "name" in df.columns  # Columns should still be present


# ==================== COMPLEXITY SCORE TESTS ====================


class TestComplexityScore:
    """Tests for complexity score calculation"""

    def test_simple_segment_low_complexity(self, sample_simple_segment):
        """Test that simple segments have low complexity"""
        mock_cja = Mock()
        mock_cja.getFilters.return_value = [sample_simple_segment]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        segment = inventory.segments[0]
        assert segment.complexity_score < 30  # Simple contains should be low

    def test_nested_segment_higher_complexity(self, sample_nested_segment):
        """Test that nested segments have higher complexity"""
        mock_cja = Mock()
        mock_cja.getFilters.return_value = [sample_nested_segment]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        segment = inventory.segments[0]
        assert segment.complexity_score > 10  # Nested should be more complex

    def test_sequence_segment_adds_complexity(self, sample_sequence_segment):
        """Test that sequential segments add complexity"""
        mock_cja = Mock()
        mock_cja.getFilters.return_value = [sample_sequence_segment]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        segment = inventory.segments[0]
        # Should have multiple predicates from sequence checkpoints
        assert segment.predicate_count >= 3

    def test_regex_segment_adds_complexity(self, sample_regex_segment):
        """Test that regex patterns add complexity"""
        mock_cja = Mock()
        mock_cja.getFilters.return_value = [sample_regex_segment]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        segment = inventory.segments[0]
        # Regex should be detected in functions
        assert "Matches Regex" in segment.functions_used

    def test_logic_operators_counted(self, sample_complex_segment):
        """Test that logic operators are counted"""
        mock_cja = Mock()
        mock_cja.getFilters.return_value = [sample_complex_segment]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        segment = inventory.segments[0]
        assert segment.logic_operator_count >= 1  # Has "and" operator


# ==================== DEFINITION SUMMARY TESTS ====================


class TestDefinitionSummary:
    """Tests for definition summary generation"""

    def test_contains_summary(self, sample_simple_segment):
        """Test definition summary for contains condition"""
        mock_cja = Mock()
        mock_cja.getFilters.return_value = [sample_simple_segment]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        segment = inventory.segments[0]
        # Should mention the dimension or contain keyword
        assert (
            "pageurl" in segment.definition_summary.lower()
            or "contains" in segment.definition_summary.lower()
            or "checkout" in segment.definition_summary.lower()
        )

    def test_visitor_context_summary(self, sample_complex_segment):
        """Test definition summary for visitor-level segment"""
        mock_cja = Mock()
        mock_cja.getFilters.return_value = [sample_complex_segment]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        segment = inventory.segments[0]
        # Should use Person/Visitor for visitor context
        assert (
            "person" in segment.definition_summary.lower()
            or "visitor" in segment.definition_summary.lower()
            or segment.container_type == "visitors"
        )

    def test_sequence_summary(self, sample_sequence_segment):
        """Test definition summary for sequential segment"""
        mock_cja = Mock()
        mock_cja.getFilters.return_value = [sample_sequence_segment]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        segment = inventory.segments[0]
        # Should mention sequence or steps
        assert (
            "sequential" in segment.definition_summary.lower()
            or "sequence" in segment.definition_summary.lower()
            or "steps" in segment.definition_summary.lower()
        )

    def test_exclude_summary(self, sample_exclude_segment):
        """Test definition summary for exclusion segment"""
        mock_cja = Mock()
        mock_cja.getFilters.return_value = [sample_exclude_segment]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        segment = inventory.segments[0]
        # Should mention exclusion or contain relevant keywords
        assert (
            "exclud" in segment.definition_summary.lower()
            or "exist" in segment.definition_summary.lower()
            or len(segment.definition_summary) > 0
        )


# ==================== EDGE CASE TESTS ====================


class TestEdgeCases:
    """Tests for edge cases and error handling"""

    def test_missing_owner(self):
        """Test handling of missing owner"""
        segment = {
            "id": "s_test",
            "name": "Test",
            "description": "",
            "definition": {
                "func": "container",
                "context": "hits",
                "pred": {"func": "exists", "dimension": "variables/pageurl"},
            },
        }
        mock_cja = Mock()
        mock_cja.getFilters.return_value = [segment]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert len(inventory.segments) == 1
        assert inventory.segments[0].owner == ""

    def test_owner_as_string(self):
        """Test handling of owner as string instead of dict"""
        segment = {
            "id": "s_test",
            "name": "Test",
            "description": "",
            "owner": "string_owner",
            "definition": {
                "func": "container",
                "context": "hits",
                "pred": {"func": "exists", "dimension": "variables/pageurl"},
            },
        }
        mock_cja = Mock()
        mock_cja.getFilters.return_value = [segment]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert inventory.segments[0].owner == "string_owner"

    def test_empty_definition(self):
        """Test handling of empty definition"""
        segment = {"id": "s_test", "name": "Test", "description": "", "definition": {}}
        mock_cja = Mock()
        mock_cja.getFilters.return_value = [segment]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        # Empty definition should be skipped
        assert inventory.total_segments == 0

    def test_api_error_handling(self):
        """Test handling of API errors"""
        mock_cja = Mock()
        mock_cja.getFilters.side_effect = Exception("API Error")

        builder = SegmentsInventoryBuilder()

        with pytest.raises(Exception) as exc_info:
            builder.build(mock_cja, "dv_test", "Test")

        assert "API Error" in str(exc_info.value)

    def test_none_response(self):
        """Test handling of None API response"""
        mock_cja = Mock()
        mock_cja.getFilters.return_value = None

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert inventory.total_segments == 0

    def test_unexpected_response_type(self):
        """Test handling of unexpected response type"""
        mock_cja = Mock()
        mock_cja.getFilters.return_value = "unexpected"

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert inventory.total_segments == 0

    def test_dict_references_are_normalized(self):
        """Dict-shaped references in definitions should not crash parsing."""
        segment = {
            "id": "s_dict_refs",
            "name": "Dict Refs",
            "description": "",
            "definition": {
                "func": "container",
                "context": "hits",
                "pred": {
                    "func": "and",
                    "preds": [
                        {"func": "segment", "segment": {"id": "segments/s_reference"}},
                        {"func": "eq", "dimension": {"id": "variables/pageurl"}, "val": "checkout"},
                    ],
                },
            },
        }
        mock_cja = Mock()
        mock_cja.getFilters.return_value = [segment]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert inventory.total_segments == 1
        assert "s_reference" in inventory.segments[0].other_segment_references
        assert "pageurl" in inventory.segments[0].dimension_references

    def test_non_string_context_does_not_crash(self):
        """Non-string context value should not crash parsing."""
        segment = {
            "id": "s_ctx",
            "name": "Non String Context",
            "description": "",
            "definition": {
                "func": "container",
                "context": 123,
                "pred": {"func": "exists", "dimension": "variables/pageurl"},
            },
        }
        mock_cja = Mock()
        mock_cja.getFilters.return_value = [segment]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert inventory.total_segments == 1

    def test_non_list_preds_does_not_crash(self):
        """Non-list preds value should not crash describe_definition."""
        segment = {
            "id": "s_preds",
            "name": "Non List Preds",
            "description": "",
            "definition": {
                "func": "and",
                "preds": "not_a_list",
            },
        }
        mock_cja = Mock()
        mock_cja.getFilters.return_value = [segment]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert inventory.total_segments == 1

    def test_non_dict_segment_payloads_are_skipped(self):
        """Unexpected list entries from the API should be skipped safely."""
        valid_segment = {
            "id": "s_valid",
            "name": "Valid Segment",
            "description": "",
            "definition": {
                "func": "container",
                "context": "hits",
                "pred": {"func": "exists", "dimension": "variables/pageurl"},
            },
        }
        mock_cja = Mock()
        mock_cja.getFilters.return_value = ["bad_payload", valid_segment]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert inventory.total_segments == 1
        assert inventory.segments[0].segment_id == "s_valid"

    def test_non_string_func_values_do_not_crash(self):
        """Unhashable/non-string func values should not break parser traversal."""
        segment = {
            "id": "s_bad_func",
            "name": "Bad Func",
            "description": "",
            "definition": {
                "func": {"name": "container"},
                "context": "hits",
                "pred": {"func": "exists", "dimension": "variables/pageurl"},
            },
        }
        mock_cja = Mock()
        mock_cja.getFilters.return_value = [segment]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert inventory.total_segments == 1

    def test_timestamp_metadata_is_preserved(self):
        """Datetime-like created/modified values should not be dropped."""
        segment = {
            "id": "s_timestamps",
            "name": "Timestamp Segment",
            "description": "",
            "created": pd.Timestamp("2025-01-15T10:30:00Z"),
            "modified": pd.Timestamp("2025-01-16T11:45:00Z"),
            "definition": {
                "func": "container",
                "context": "hits",
                "pred": {"func": "exists", "dimension": "variables/pageurl"},
            },
        }
        mock_cja = Mock()
        mock_cja.getFilters.return_value = [segment]

        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja, "dv_test", "Test")

        assert inventory.total_segments == 1
        assert inventory.segments[0].created != ""
        assert inventory.segments[0].modified != ""
        df = inventory.get_dataframe()
        assert df.iloc[0]["created"] != "-"
        assert df.iloc[0]["modified"] != "-"
        assert "2025-01-15" in str(df.iloc[0]["created"])
        assert "2025-01-16" in str(df.iloc[0]["modified"])


# ==================== DATA CLASS TESTS ====================


class TestSegmentSummary:
    """Tests for SegmentSummary data class"""

    def test_to_dict(self):
        """Test conversion to dictionary"""
        summary = SegmentSummary(
            segment_id="s_test",
            segment_name="Test Segment",
            description="Test description",
            owner="Test Owner",
            complexity_score=45.5,
            functions_used=["Contains", "And"],
            functions_used_internal=["contains", "and"],
            predicate_count=3,
            logic_operator_count=1,
            nesting_depth=2,
            container_count=1,
            dimension_references=["pageurl", "channel"],
            metric_references=["revenue"],
            other_segment_references=[],
            definition_summary="Hit where pageurl contains 'checkout'",
            container_type="hits",
        )

        d = summary.to_dict()

        assert d["name"] == "Test Segment"
        assert d["description"] == "Test description"
        assert d["owner"] == "Test Owner"
        assert d["complexity_score"] == pytest.approx(45.5)
        assert "Contains" in d["functions_used"]
        assert "pageurl" in d["dimension_references"]
        assert d["container_type"] == "Hits"

    def test_to_full_dict(self):
        """Test conversion to full dictionary"""
        summary = SegmentSummary(
            segment_id="s_test",
            segment_name="Test",
            description="",
            owner="",
            complexity_score=10.0,
            functions_used=["Contains"],
            functions_used_internal=["contains"],
            predicate_count=1,
            logic_operator_count=0,
            nesting_depth=1,
            container_count=1,
            dimension_references=["pageurl"],
            metric_references=[],
            other_segment_references=["s_other"],
            definition_summary="test",
            container_type="hits",
        )

        d = summary.to_full_dict()

        assert d["segment_id"] == "s_test"
        assert d["nesting_depth"] == 1
        assert d["other_segment_references"] == ["s_other"]
        assert d["container_type"] == "hits"


class TestSegmentsInventoryProperties:
    """Tests for SegmentsInventory properties"""

    def test_avg_complexity_empty(self):
        """Test average complexity with no segments"""
        inventory = SegmentsInventory(data_view_id="dv_test", data_view_name="Test")
        assert inventory.avg_complexity == pytest.approx(0.0)

    def test_max_complexity_empty(self):
        """Test max complexity with no segments"""
        inventory = SegmentsInventory(data_view_id="dv_test", data_view_name="Test")
        assert inventory.max_complexity == pytest.approx(0.0)

    def test_approved_count(self):
        """Test approved count property"""
        inventory = SegmentsInventory(data_view_id="dv_test", data_view_name="Test")
        # Add some test segments manually
        summary1 = SegmentSummary(
            segment_id="s1",
            segment_name="S1",
            description="",
            owner="",
            complexity_score=10.0,
            functions_used=[],
            functions_used_internal=[],
            predicate_count=1,
            logic_operator_count=0,
            nesting_depth=1,
            container_count=1,
            dimension_references=[],
            metric_references=[],
            other_segment_references=[],
            definition_summary="",
            container_type="hits",
            approved=True,
        )
        summary2 = SegmentSummary(
            segment_id="s2",
            segment_name="S2",
            description="",
            owner="",
            complexity_score=10.0,
            functions_used=[],
            functions_used_internal=[],
            predicate_count=1,
            logic_operator_count=0,
            nesting_depth=1,
            container_count=1,
            dimension_references=[],
            metric_references=[],
            other_segment_references=[],
            definition_summary="",
            container_type="hits",
            approved=False,
        )
        inventory.segments = [summary1, summary2]

        assert inventory.approved_count == 1

    def test_shared_count(self):
        """Test shared count property"""
        inventory = SegmentsInventory(data_view_id="dv_test", data_view_name="Test")
        summary1 = SegmentSummary(
            segment_id="s1",
            segment_name="S1",
            description="",
            owner="",
            complexity_score=10.0,
            functions_used=[],
            functions_used_internal=[],
            predicate_count=1,
            logic_operator_count=0,
            nesting_depth=1,
            container_count=1,
            dimension_references=[],
            metric_references=[],
            other_segment_references=[],
            definition_summary="",
            container_type="hits",
            shared_to_count=2,
        )
        summary2 = SegmentSummary(
            segment_id="s2",
            segment_name="S2",
            description="",
            owner="",
            complexity_score=10.0,
            functions_used=[],
            functions_used_internal=[],
            predicate_count=1,
            logic_operator_count=0,
            nesting_depth=1,
            container_count=1,
            dimension_references=[],
            metric_references=[],
            other_segment_references=[],
            definition_summary="",
            container_type="hits",
            shared_to_count=0,
        )
        inventory.segments = [summary1, summary2]

        assert inventory.shared_count == 1

    def test_tagged_count(self):
        """Test tagged count property"""
        inventory = SegmentsInventory(data_view_id="dv_test", data_view_name="Test")
        summary1 = SegmentSummary(
            segment_id="s1",
            segment_name="S1",
            description="",
            owner="",
            complexity_score=10.0,
            functions_used=[],
            functions_used_internal=[],
            predicate_count=1,
            logic_operator_count=0,
            nesting_depth=1,
            container_count=1,
            dimension_references=[],
            metric_references=[],
            other_segment_references=[],
            definition_summary="",
            container_type="hits",
            tags=["KPI", "Revenue"],
        )
        summary2 = SegmentSummary(
            segment_id="s2",
            segment_name="S2",
            description="",
            owner="",
            complexity_score=10.0,
            functions_used=[],
            functions_used_internal=[],
            predicate_count=1,
            logic_operator_count=0,
            nesting_depth=1,
            container_count=1,
            dimension_references=[],
            metric_references=[],
            other_segment_references=[],
            definition_summary="",
            container_type="hits",
            tags=[],
        )
        inventory.segments = [summary1, summary2]

        assert inventory.tagged_count == 1


# ==================== SUMMARY COLUMN ALIAS TESTS ====================


class TestSummaryColumnAlias:
    """Tests for standardized summary column alias"""

    def test_summary_column_exists(self, mock_cja_instance):
        """Test that summary column exists in DataFrame"""
        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja_instance, "dv_test", "Test")
        df = inventory.get_dataframe()

        assert "summary" in df.columns

    def test_summary_equals_definition_summary(self, mock_cja_instance):
        """Test that summary column equals definition_summary column"""
        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja_instance, "dv_test", "Test")
        df = inventory.get_dataframe()

        assert all(df["summary"] == df["definition_summary"])

    def test_empty_dataframe_has_summary_column(self, mock_cja_instance_empty):
        """Test that empty DataFrame still has summary column"""
        builder = SegmentsInventoryBuilder()
        inventory = builder.build(mock_cja_instance_empty, "dv_test", "Test")
        df = inventory.get_dataframe()

        assert "summary" in df.columns


def test_functions_used_order_is_stable_across_hash_seeds():
    """functions_used must not depend on per-process string hash randomization."""
    script = textwrap.dedent("""
        import json
        from unittest.mock import Mock
        from cja_auto_sdr.inventory.segments import SegmentsInventoryBuilder
        seg = {"id": "s1", "name": "S", "description": "", "owner": {"name": "O"},
               "definition": {"func": "container", "context": "visitors", "pred": {"func": "and", "preds": [
                   {"func": "eq", "dimension": "variables/mobiledevicetype", "val": "Mobile Phone"},
                   {"func": "gt", "metric": "metrics/revenue", "val": 100},
                   {"func": "gte", "metric": "metrics/orders", "val": 3}]}}}
        cja = Mock()
        cja.getFilters.return_value = [seg]
        s = SegmentsInventoryBuilder().build(cja, "dv_test", "Test").segments[0]
        print(json.dumps([s.functions_used, s.functions_used_internal, s.to_dict()["functions_used"]]))
    """)
    outs = {
        subprocess.run(
            [sys.executable, "-c", script],
            env={**os.environ, "PYTHONHASHSEED": seed},
            cwd=Path(__file__).resolve().parent.parent,
            capture_output=True,
            text=True,
            check=True,
        ).stdout
        for seed in ("1", "2", "3")
    }
    assert len(outs) == 1, outs
    _display, internal, _dict_used = json.loads(outs.pop())
    assert len(internal) >= 4
    assert internal == sorted(internal)


# ==================== CJA PAYLOAD SHAPES ====================
# Real CJA segment definitions wrap the rule as {"func": "segment", "container": ...}
# and wrap operands in reference nodes: val={"func": "attr"} for dimensions and
# evt={"func": "event"} (or val={"func": "total", "evt": ...}) for metrics.


def _attr(name: str) -> dict:
    return {"func": "attr", "name": f"variables/{name}"}


def _event(name: str) -> dict:
    return {"func": "event", "name": f"metrics/{name}"}


def _segment(context: str, pred: dict) -> dict:
    return {
        "func": "segment",
        "version": [1, 0, 0],
        "container": {"func": "container", "context": context, "pred": pred},
    }


class TestCjaPayloadShapes:
    @pytest.fixture
    def builder(self):
        return SegmentsInventoryBuilder()

    def _summary(self, builder, definition):
        parsed = builder._parse_definition(definition)
        return parsed, builder._generate_definition_summary(definition, parsed)

    def test_attr_and_event_references_are_extracted(self, builder):
        definition = _segment(
            "visitors",
            {
                "func": "and",
                "preds": [
                    {"func": "streq-in", "val": _attr("product_pages"), "list": ["a", "b"]},
                    {"func": "not-event-exists", "evt": _event("orders")},
                ],
            },
        )
        parsed, summary = self._summary(builder, definition)

        assert parsed["dimension_references"] == ["product_pages"]
        assert parsed["metric_references"] == ["orders"]
        assert parsed["container_type"] == "visitors"
        # streq-in with two values plus not-event-exists
        assert parsed["predicate_count"] == 3
        assert summary == "Person where product_pages in (a, b) AND orders does not exist"
        # Reference wrappers are operands, not functions the segment uses.
        assert "attr" not in parsed["functions_internal"]
        assert "event" not in parsed["functions_internal"]

    def test_total_wrapped_metric_comparison(self, builder):
        definition = _segment(
            "hits",
            {"func": "gt", "val": {"func": "total", "evt": _event("revenue")}, "num": 0},
        )
        parsed, summary = self._summary(builder, definition)

        assert parsed["metric_references"] == ["revenue"]
        assert parsed["dimension_references"] == []
        assert summary == "Hit where revenue > 0"

    @pytest.mark.parametrize(
        ("pred", "expected"),
        [
            ({"func": "streq", "val": _attr("browser"), "str": "Chrome"}, "browser = 'Chrome'"),
            ({"func": "not-streq", "val": _attr("browser"), "str": "Chrome"}, "browser != 'Chrome'"),
            ({"func": "contains", "val": _attr("page"), "str": "cart"}, "page contains 'cart'"),
            ({"func": "not-starts-with", "val": _attr("page"), "str": "/x"}, "page does not start with '/x'"),
            ({"func": "exists", "val": _attr("page")}, "page exists"),
            ({"func": "not-exists", "val": _attr("page")}, "page does not exist"),
            ({"func": "event-exists", "evt": _event("orders")}, "orders exists"),
            ({"func": "ge", "val": {"func": "total", "evt": _event("visits")}, "num": 2}, "visits >= 2"),
            (
                {"func": "without", "pred": {"func": "event-exists", "evt": _event("orders")}},
                "excluding (orders exists)",
            ),
        ],
    )
    def test_predicate_descriptions(self, builder, pred, expected):
        _, summary = self._summary(builder, _segment("visits", pred))
        assert summary == f"Visit where {expected}"

    def test_stream_sequence_steps_are_traversed_and_counted(self, builder):
        definition = _segment(
            "visitors",
            {
                "func": "sequence",
                "stream": [
                    {"func": "container", "context": "hits", "pred": {"func": "event-exists", "evt": _event("calls")}},
                    {"func": "time-restriction", "limit": "after", "count": 1, "unit": "week"},
                    {"func": "container", "context": "hits", "pred": {"func": "exists", "val": _attr("page")}},
                ],
            },
        )
        parsed, summary = self._summary(builder, definition)

        assert parsed["metric_references"] == ["calls"]
        assert parsed["dimension_references"] == ["page"]
        assert summary == "Person where sequential pattern with 2 steps"

    def test_legacy_dimension_shape_still_supported(self, builder):
        definition = {
            "func": "container",
            "context": "hits",
            "pred": {"func": "streq", "dimension": "variables/page", "val": "Home"},
        }
        parsed, summary = self._summary(builder, definition)

        assert parsed["dimension_references"] == ["page"]
        assert summary == "Hit where page = 'Home'"

    def test_reference_node_without_name_is_ignored(self, builder):
        definition = _segment("hits", {"func": "exists", "val": {"func": "attr"}})
        parsed = builder._parse_definition(definition)
        assert parsed["dimension_references"] == []


def test_build_retries_transient_connection_error(mock_cja_instance):
    """A transient ConnectionError on getFilters is retried, then the build succeeds."""
    good = mock_cja_instance.getFilters.return_value
    mock_cja_instance.getFilters.side_effect = [ConnectionError("reset"), good]

    with patch("cja_auto_sdr.api.resilience.time.sleep"):
        inventory = SegmentsInventoryBuilder().build(mock_cja_instance, "dv_test", "Test View")

    assert mock_cja_instance.getFilters.call_count == 2
    assert inventory.total_segments == 2


def test_build_does_not_retry_error_body_keyerror(mock_cja_instance):
    """cjapy error bodies raise KeyError('content'); that is not transient, so no retry and it fails closed."""
    mock_cja_instance.getFilters.side_effect = KeyError("content")

    with patch("cja_auto_sdr.api.resilience.time.sleep") as sleep, pytest.raises(KeyError):
        SegmentsInventoryBuilder().build(mock_cja_instance, "dv_test", "Test View")

    assert mock_cja_instance.getFilters.call_count == 1
    sleep.assert_not_called()
