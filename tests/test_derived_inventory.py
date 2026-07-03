"""
Test suite for CJA Derived Field Inventory

Tests cover:
- Parsing derived field definitions
- Inventory generation
- Complexity score calculation
- Logic summary generation
- DataFrame output
"""

import json

import pandas as pd
import pytest

from cja_auto_sdr.inventory.derived_fields import (
    DerivedFieldInventory,
    DerivedFieldInventoryBuilder,
)

# ==================== FIXTURES ====================


@pytest.fixture
def sample_derived_field_definition():
    """Sample derived field definition JSON string"""
    return json.dumps(
        [
            {"func": "raw-field", "id": "productListItems.priceTotal", "label": "price_field"},
            {
                "func": "match",
                "field": "price_field",
                "case-sensitive": False,
                "branches": [
                    {"pred": {"func": "lt", "field": "price_field", "value": 100}, "map-to": "Low"},
                    {"pred": {"func": "lte", "field": "price_field", "value": 500}, "map-to": "Medium"},
                    {"pred": {"func": "true"}, "map-to": "High"},
                ],
                "#rule_name": "Price Bucket",
                "#rule_description": "Categorize products by price range",
                "#rule_id": "rule-0",
                "#rule_type": "caseWhen",
            },
        ],
    )


@pytest.fixture
def sample_complex_derived_field():
    """Complex derived field with many functions"""
    functions = [
        {"func": "raw-field", "id": f"field_{i}", "label": f"label_{i}"} for i in range(12)
    ]  # Many field references

    functions.append(
        {
            "func": "match",
            "field": "label_0",
            "branches": [
                {
                    "pred": {
                        "func": "and",
                        "preds": [
                            {"func": "isset", "field": "label_0"},
                            {"func": "isset", "field": "label_1"},
                            {
                                "func": "and",
                                "preds": [  # Nested
                                    {"func": "eq", "field": "label_2", "value": "test"},
                                    {"func": "ne", "field": "label_3", "value": "exclude"},
                                ],
                            },
                        ],
                    },
                    "map-to": 1,
                }
                for _ in range(25)  # Many branches
            ],
        },
    )

    return json.dumps(functions)


@pytest.fixture
def sample_marketing_channel_field():
    """Marketing channel derived field"""
    return json.dumps(
        [
            {"func": "raw-field", "id": "web.referringDomain", "label": "referrer"},
            {"func": "raw-field", "id": "marketing.campaignId", "label": "campaign"},
            {
                "func": "match",
                "field": "referrer",
                "branches": [
                    {"pred": {"func": "contains", "field": "campaign", "value": "paid"}, "map-to": "Paid Search"},
                    {"pred": {"func": "contains", "field": "referrer", "value": "google"}, "map-to": "Organic Search"},
                    {"pred": {"func": "contains", "field": "referrer", "value": "facebook"}, "map-to": "Social"},
                    {"pred": {"func": "true"}, "map-to": "Other"},
                ],
                "#rule_name": "Marketing Channel",
                "#rule_type": "caseWhen",
            },
        ],
    )


@pytest.fixture
def sample_lookup_field():
    """Derived field with lookup"""
    return json.dumps(
        [
            {"func": "raw-field", "id": "campaign_code", "label": "campaign_key"},
            {
                "func": "classify",
                "label": "campaign_name",
                "mapping": {
                    "func": "external-multi-value",
                    "key-field": "lookup_table_id",
                    "value-selector-field": "campaign_key",
                },
                "source-field": "campaign_key",
            },
        ],
    )


@pytest.fixture
def sample_math_only_field():
    """Derived field with pure math operations"""
    return json.dumps(
        [
            {"func": "raw-field", "id": "revenue", "label": "rev"},
            {"func": "raw-field", "id": "cost", "label": "cost"},
            {"func": "subtract", "fields": ["rev", "cost"], "label": "profit"},
            {"func": "divide", "dividend": "profit", "divisor": "rev"},
        ],
    )


@pytest.fixture
def sample_simple_lowercase_field():
    """Derived field that only does lowercase"""
    return json.dumps(
        [{"func": "raw-field", "id": "pageName", "label": "page"}, {"func": "lowercase", "field": "page"}],
    )


@pytest.fixture
def sample_metrics_df(sample_derived_field_definition, sample_math_only_field):
    """Sample metrics DataFrame with derived fields"""
    return pd.DataFrame(
        [
            {
                "id": "metrics/bounces",
                "name": "Bounces",
                "description": "Bounce count",
                "sourceFieldType": "derived",
                "type": "int",
                "fieldDefinition": sample_derived_field_definition,
                "dataSetType": "event",
            },
            {
                "id": "metrics/profit",
                "name": "Profit Margin",
                "description": "Revenue minus cost",
                "sourceFieldType": "derived",
                "type": "decimal",
                "fieldDefinition": sample_math_only_field,
                "dataSetType": "event",
            },
            {
                "id": "metrics/visitors",
                "name": "People",
                "description": "Unique visitors",
                "sourceFieldType": "standard",
                "type": "int",
                "fieldDefinition": pd.NA,
                "dataSetType": "event",
            },
        ],
    )


@pytest.fixture
def sample_dimensions_df(sample_marketing_channel_field, sample_lookup_field, sample_simple_lowercase_field):
    """Sample dimensions DataFrame with derived fields"""
    return pd.DataFrame(
        [
            {
                "id": "dimensions/marketing_channel",
                "name": "Marketing Channel",
                "description": "Traffic source classification",
                "sourceFieldType": "derived",
                "type": "string",
                "fieldDefinition": sample_marketing_channel_field,
                "dataSetType": "event",
            },
            {
                "id": "dimensions/campaign_name",
                "name": "Campaign Name",
                "description": "Lookup-based campaign name",
                "sourceFieldType": "derived",
                "type": "string",
                "fieldDefinition": sample_lookup_field,
                "dataSetType": "event",
            },
            {
                "id": "dimensions/page_lower",
                "name": "Page Name (Lower)",
                "description": "Lowercase page name",
                "sourceFieldType": "derived",
                "type": "string",
                "fieldDefinition": sample_simple_lowercase_field,
                "dataSetType": "event",
            },
            {
                "id": "dimensions/page",
                "name": "Page Name",
                "description": "Raw page name",
                "sourceFieldType": "custom",
                "type": "string",
                "fieldDefinition": pd.NA,
                "dataSetType": "event",
            },
        ],
    )


# ==================== BUILDER TESTS ====================


class TestDerivedFieldInventoryBuilder:
    """Tests for DerivedFieldInventoryBuilder class"""

    def test_build_basic(self, sample_metrics_df, sample_dimensions_df):
        """Test basic inventory building"""
        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(sample_metrics_df, sample_dimensions_df, "dv_test", "Test View")

        assert isinstance(inventory, DerivedFieldInventory)
        assert inventory.data_view_id == "dv_test"
        assert inventory.data_view_name == "Test View"
        assert inventory.total_derived_fields > 0

    def test_build_empty_dataframes(self):
        """Test building with empty DataFrames"""
        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(pd.DataFrame(), pd.DataFrame(), "dv_empty", "Empty")

        assert inventory.total_derived_fields == 0
        assert inventory.metrics_count == 0
        assert inventory.dimensions_count == 0

    def test_counts_correct(self, sample_metrics_df, sample_dimensions_df):
        """Test that metric/dimension counts are correct"""
        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(sample_metrics_df, sample_dimensions_df, "dv_test", "Test")

        # 2 derived metrics, 3 derived dimensions
        assert inventory.metrics_count == 2
        assert inventory.dimensions_count == 3
        assert inventory.total_derived_fields == 5

    def test_complexity_score_calculated(self, sample_metrics_df, sample_dimensions_df):
        """Test that complexity scores are calculated"""
        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(sample_metrics_df, sample_dimensions_df, "dv_test", "Test")

        for field in inventory.fields:
            assert 0 <= field.complexity_score <= 100

    def test_functions_extracted(self, sample_marketing_channel_field):
        """Test that functions are extracted correctly"""
        builder = DerivedFieldInventoryBuilder()
        df = pd.DataFrame(
            [
                {
                    "id": "dim/channel",
                    "name": "Channel",
                    "sourceFieldType": "derived",
                    "fieldDefinition": sample_marketing_channel_field,
                    "dataSetType": "event",
                },
            ],
        )

        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        assert len(inventory.fields) == 1
        field = inventory.fields[0]
        assert "Case When" in field.functions_used

    def test_rule_names_extracted(self, sample_derived_field_definition):
        """Test that rule names from definition are extracted"""
        builder = DerivedFieldInventoryBuilder()
        df = pd.DataFrame(
            [
                {
                    "id": "metrics/test",
                    "name": "Test",
                    "sourceFieldType": "derived",
                    "fieldDefinition": sample_derived_field_definition,
                    "dataSetType": "event",
                },
            ],
        )

        inventory = builder.build(df, pd.DataFrame(), "dv_test", "Test")

        assert len(inventory.fields) == 1
        field = inventory.fields[0]
        assert "Price Bucket" in field.rule_names

    def test_schema_fields_extracted(self, sample_marketing_channel_field):
        """Test that schema field references are extracted"""
        builder = DerivedFieldInventoryBuilder()
        df = pd.DataFrame(
            [
                {
                    "id": "dim/channel",
                    "name": "Channel",
                    "sourceFieldType": "derived",
                    "fieldDefinition": sample_marketing_channel_field,
                    "dataSetType": "event",
                },
            ],
        )

        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        field = inventory.fields[0]
        assert field.schema_field_count == 2
        assert "web.referringDomain" in field.schema_fields
        assert "marketing.campaignId" in field.schema_fields

    def test_lookup_references_extracted(self, sample_lookup_field):
        """Test that lookup references are extracted"""
        builder = DerivedFieldInventoryBuilder()
        df = pd.DataFrame(
            [
                {
                    "id": "dim/campaign",
                    "name": "Campaign",
                    "sourceFieldType": "derived",
                    "fieldDefinition": sample_lookup_field,
                    "dataSetType": "event",
                },
            ],
        )

        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        field = inventory.fields[0]
        assert len(field.lookup_references) > 0

    def test_branch_count_correct(self, sample_marketing_channel_field):
        """Test that branch count is calculated correctly"""
        builder = DerivedFieldInventoryBuilder()
        df = pd.DataFrame(
            [
                {
                    "id": "dim/channel",
                    "name": "Channel",
                    "sourceFieldType": "derived",
                    "fieldDefinition": sample_marketing_channel_field,
                    "dataSetType": "event",
                },
            ],
        )

        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        field = inventory.fields[0]
        assert field.branch_count == 4  # 4 branches in the marketing channel field


# ==================== INVENTORY TESTS ====================


class TestDerivedFieldInventory:
    """Tests for DerivedFieldInventory class"""

    def test_get_dataframe(self, sample_metrics_df, sample_dimensions_df):
        """Test DataFrame output"""
        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(sample_metrics_df, sample_dimensions_df, "dv_test", "Test")

        df = inventory.get_dataframe()

        assert isinstance(df, pd.DataFrame)
        assert len(df) == inventory.total_derived_fields
        assert "name" in df.columns
        assert "type" in df.columns
        assert "complexity_score" in df.columns
        assert "functions_used" in df.columns
        assert "logic_summary" in df.columns

    def test_get_dataframe_sorted_by_complexity(self, sample_metrics_df, sample_dimensions_df):
        """Test that DataFrame is sorted by complexity score descending"""
        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(sample_metrics_df, sample_dimensions_df, "dv_test", "Test")

        df = inventory.get_dataframe()

        # Check that complexity scores are in descending order
        scores = df["complexity_score"].tolist()
        assert scores == sorted(scores, reverse=True)

    def test_get_summary(self, sample_metrics_df, sample_dimensions_df):
        """Test summary statistics"""
        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(sample_metrics_df, sample_dimensions_df, "dv_test", "Test")

        summary = inventory.get_summary()

        assert "data_view_id" in summary
        assert "data_view_name" in summary
        assert "total_derived_fields" in summary
        assert "metrics_count" in summary
        assert "dimensions_count" in summary
        assert "complexity" in summary
        assert "function_usage" in summary

    def test_to_json(self, sample_metrics_df, sample_dimensions_df):
        """Test JSON export"""
        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(sample_metrics_df, sample_dimensions_df, "dv_test", "Test")

        json_data = inventory.to_json()

        assert "summary" in json_data
        assert "fields" in json_data
        assert len(json_data["fields"]) == inventory.total_derived_fields

    def test_empty_inventory_dataframe(self):
        """Test DataFrame output for empty inventory"""
        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(pd.DataFrame(), pd.DataFrame(), "dv_test", "Test")

        df = inventory.get_dataframe()

        assert isinstance(df, pd.DataFrame)
        assert len(df) == 0
        assert "name" in df.columns  # Columns should still be present


# ==================== COMPLEXITY SCORE TESTS ====================


class TestComplexityScore:
    """Tests for complexity score calculation"""

    def test_simple_field_low_complexity(self, sample_simple_lowercase_field):
        """Test that simple fields have low complexity"""
        builder = DerivedFieldInventoryBuilder()
        df = pd.DataFrame(
            [
                {
                    "id": "dim/page",
                    "name": "Page Lower",
                    "sourceFieldType": "derived",
                    "fieldDefinition": sample_simple_lowercase_field,
                    "dataSetType": "event",
                },
            ],
        )

        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        field = inventory.fields[0]
        assert field.complexity_score < 20  # Simple field should be low complexity

    def test_complex_field_high_complexity(self, sample_complex_derived_field):
        """Test that complex fields have high complexity"""
        builder = DerivedFieldInventoryBuilder()
        df = pd.DataFrame(
            [
                {
                    "id": "metrics/complex",
                    "name": "Complex Field",
                    "sourceFieldType": "derived",
                    "fieldDefinition": sample_complex_derived_field,
                    "dataSetType": "event",
                },
            ],
        )

        inventory = builder.build(df, pd.DataFrame(), "dv_test", "Test")

        field = inventory.fields[0]
        assert field.complexity_score > 30  # Complex field should have elevated complexity


# ==================== LOGIC SUMMARY TESTS ====================


class TestLogicSummary:
    """Tests for logic summary generation"""

    def test_case_when_summary(self, sample_marketing_channel_field):
        """Test logic summary for Case When"""
        builder = DerivedFieldInventoryBuilder()
        df = pd.DataFrame(
            [
                {
                    "id": "dim/channel",
                    "name": "Channel",
                    "sourceFieldType": "derived",
                    "fieldDefinition": sample_marketing_channel_field,
                    "dataSetType": "event",
                },
            ],
        )

        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        field = inventory.fields[0]
        # Should mention classification or rules
        assert (
            "rules" in field.logic_summary.lower()
            or "classif" in field.logic_summary.lower()
            or "case" in field.logic_summary.lower()
        )

    def test_math_summary(self, sample_math_only_field):
        """Test logic summary for math operations"""
        builder = DerivedFieldInventoryBuilder()
        df = pd.DataFrame(
            [
                {
                    "id": "metrics/profit",
                    "name": "Profit",
                    "sourceFieldType": "derived",
                    "fieldDefinition": sample_math_only_field,
                    "dataSetType": "event",
                },
            ],
        )

        inventory = builder.build(df, pd.DataFrame(), "dv_test", "Test")

        field = inventory.fields[0]
        assert "math" in field.logic_summary.lower()

    def test_lookup_summary(self, sample_lookup_field):
        """Test logic summary for lookup"""
        builder = DerivedFieldInventoryBuilder()
        df = pd.DataFrame(
            [
                {
                    "id": "dim/campaign",
                    "name": "Campaign",
                    "sourceFieldType": "derived",
                    "fieldDefinition": sample_lookup_field,
                    "dataSetType": "event",
                },
            ],
        )

        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        field = inventory.fields[0]
        assert "lookup" in field.logic_summary.lower()

    def test_lowercase_summary(self, sample_simple_lowercase_field):
        """Test logic summary for simple transformation"""
        builder = DerivedFieldInventoryBuilder()
        df = pd.DataFrame(
            [
                {
                    "id": "dim/page",
                    "name": "Page Lower",
                    "sourceFieldType": "derived",
                    "fieldDefinition": sample_simple_lowercase_field,
                    "dataSetType": "event",
                },
            ],
        )

        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        field = inventory.fields[0]
        assert "lowercase" in field.logic_summary.lower()


# ==================== OUTPUT TYPE TESTS ====================


class TestInferredOutputType:
    """Tests for output type inference"""

    def test_math_produces_numeric(self, sample_math_only_field):
        """Test that math operations infer numeric type"""
        builder = DerivedFieldInventoryBuilder()
        df = pd.DataFrame(
            [
                {
                    "id": "metrics/profit",
                    "name": "Profit",
                    "sourceFieldType": "derived",
                    "fieldDefinition": sample_math_only_field,
                    "dataSetType": "event",
                },
            ],
        )

        inventory = builder.build(df, pd.DataFrame(), "dv_test", "Test")

        field = inventory.fields[0]
        assert field.inferred_output_type == "numeric"

    def test_case_when_with_strings_produces_string(self, sample_marketing_channel_field):
        """Test that Case When with string outputs infers string type"""
        builder = DerivedFieldInventoryBuilder()
        df = pd.DataFrame(
            [
                {
                    "id": "dim/channel",
                    "name": "Channel",
                    "sourceFieldType": "derived",
                    "fieldDefinition": sample_marketing_channel_field,
                    "dataSetType": "event",
                },
            ],
        )

        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        field = inventory.fields[0]
        assert field.inferred_output_type == "string"

    def test_lowercase_produces_string(self, sample_simple_lowercase_field):
        """Test that lowercase infers string type"""
        builder = DerivedFieldInventoryBuilder()
        df = pd.DataFrame(
            [
                {
                    "id": "dim/page",
                    "name": "Page",
                    "sourceFieldType": "derived",
                    "fieldDefinition": sample_simple_lowercase_field,
                    "dataSetType": "event",
                },
            ],
        )

        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        field = inventory.fields[0]
        assert field.inferred_output_type == "string"


# ==================== EDGE CASE TESTS ====================


class TestEdgeCases:
    """Tests for edge cases and error handling"""

    def test_array_like_field_definition(self):
        """Test handling of array-like values in fieldDefinition column"""
        df = pd.DataFrame(
            [
                {
                    "id": "metrics/test",
                    "name": "Test Metric",
                    "sourceFieldType": "derived",
                    "fieldDefinition": [{"func": "raw-field", "id": "test", "label": "test"}],
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(df, pd.DataFrame(), "dv_test", "Test")

        assert inventory.total_derived_fields == 1

    def test_empty_field_definition_list(self):
        """Test handling of empty list fieldDefinition"""
        df = pd.DataFrame(
            [
                {
                    "id": "metrics/test",
                    "name": "Test",
                    "sourceFieldType": "derived",
                    "fieldDefinition": [],
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(df, pd.DataFrame(), "dv_test", "Test")

        # Empty definition should not create a field entry
        assert inventory.total_derived_fields == 0

    def test_none_field_definition(self):
        """Test handling of None fieldDefinition"""
        df = pd.DataFrame(
            [
                {
                    "id": "metrics/test",
                    "name": "Test",
                    "sourceFieldType": "derived",
                    "fieldDefinition": None,
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(df, pd.DataFrame(), "dv_test", "Test")

        assert inventory.total_derived_fields == 0

    def test_invalid_json_definition(self):
        """Test handling of invalid JSON"""
        df = pd.DataFrame(
            [
                {
                    "id": "metrics/test",
                    "name": "Test",
                    "sourceFieldType": "derived",
                    "fieldDefinition": "not valid json",
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(df, pd.DataFrame(), "dv_test", "Test")

        assert inventory.total_derived_fields == 0

    def test_non_derived_fields_ignored(self):
        """Test that non-derived fields are ignored"""
        df = pd.DataFrame(
            [
                {
                    "id": "metrics/standard",
                    "name": "Standard Metric",
                    "sourceFieldType": "standard",
                    "fieldDefinition": pd.NA,
                    "dataSetType": "event",
                },
                {
                    "id": "metrics/custom",
                    "name": "Custom Metric",
                    "sourceFieldType": "custom",
                    "fieldDefinition": '[{"func": "raw-field", "id": "test"}]',
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(df, pd.DataFrame(), "dv_test", "Test")

        # Neither should be included - only sourceFieldType="derived" counts
        assert inventory.total_derived_fields == 0

    def test_list_shaped_source_field_type_is_supported(self):
        """sourceFieldType values provided as lists should still be recognized."""
        df = pd.DataFrame(
            [
                {
                    "id": "metrics/test_list_source_type",
                    "name": "List Source Type",
                    "sourceFieldType": ["derived"],
                    "fieldDefinition": json.dumps([{"func": "raw-field", "id": "test", "label": "test"}]),
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(df, pd.DataFrame(), "dv_test", "Test")

        assert inventory.total_derived_fields == 1

    def test_non_string_field_references_do_not_crash(self):
        """Numeric field reference IDs should be normalized without crashing."""
        df = pd.DataFrame(
            [
                {
                    "id": "metrics/test_numeric_ref",
                    "name": "Numeric Ref",
                    "sourceFieldType": "derived",
                    "fieldDefinition": json.dumps([{"func": "raw-field", "id": 123, "label": "num_field"}]),
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(df, pd.DataFrame(), "dv_test", "Test")

        assert inventory.total_derived_fields == 1
        result_df = inventory.get_dataframe()
        assert result_df.iloc[0]["schema_field_list"] == "123"

    def test_match_with_dict_field_references_does_not_crash(self):
        """Dict-based match field references should be normalized safely."""
        definition = json.dumps(
            [
                {"func": "raw-field", "id": "variables/pageName", "label": "page_label"},
                {
                    "func": "match",
                    "field": {"label": "page_label"},
                    "branches": [
                        {
                            "pred": {"func": "contains", "field": {"label": "page_label"}, "value": "home"},
                            "map-to": {"type": "field", "value": {"label": "page_label"}},
                        },
                        {"pred": {"func": "true"}, "map-to": "Other"},
                    ],
                },
            ],
        )
        df = pd.DataFrame(
            [
                {
                    "id": "dimensions/page_category",
                    "name": "Page Category",
                    "sourceFieldType": "derived",
                    "fieldDefinition": definition,
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        assert inventory.total_derived_fields == 1
        assert inventory.fields[0].logic_summary

    def test_non_string_func_names_do_not_crash(self):
        """Malformed non-string function names should be skipped safely."""
        definition = json.dumps(
            [
                {"func": "raw-field", "id": "variables/pageName", "label": "page_label"},
                {
                    "func": {"unexpected": "match"},
                    "field": "page_label",
                    "branches": [
                        {"pred": {"func": "contains", "field": "page_label", "value": "home"}, "map-to": "Home"},
                        {"pred": {"func": "true"}, "map-to": "Other"},
                    ],
                },
            ],
        )
        df = pd.DataFrame(
            [
                {
                    "id": "dimensions/page_category",
                    "name": "Page Category",
                    "sourceFieldType": "derived",
                    "fieldDefinition": definition,
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        assert inventory.total_derived_fields == 1
        assert inventory.fields[0].functions_used_internal == ["raw-field"]

    def test_url_parse_with_dict_component_does_not_crash(self):
        """Dict-shaped url-parse component payloads should be handled safely."""
        definition = json.dumps(
            [
                {"func": "raw-field", "id": "web.webPageDetails.URL", "label": "url"},
                {
                    "func": "url-parse",
                    "label": "utm_campaign",
                    "component": {"func": "query", "param": "utm_campaign"},
                    "args": [{"func": "raw-field", "id": "web.webPageDetails.URL"}],
                },
            ],
        )
        df = pd.DataFrame(
            [
                {
                    "id": "dimensions/utm_campaign",
                    "name": "UTM Campaign",
                    "sourceFieldType": "derived",
                    "fieldDefinition": definition,
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        assert inventory.total_derived_fields == 1
        assert "query param 'utm_campaign'" in inventory.fields[0].logic_summary

    def test_nan_component_id_is_skipped(self):
        """Rows with NaN component IDs should be rejected as invalid IDs."""
        df = pd.DataFrame(
            [
                {
                    "id": float("nan"),
                    "name": "Bad ID Metric",
                    "sourceFieldType": "derived",
                    "fieldDefinition": json.dumps([{"func": "raw-field", "id": "x", "label": "field"}]),
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(df, pd.DataFrame(), "dv_test", "Test")

        assert inventory.total_derived_fields == 0

    def test_dict_shaped_args_does_not_crash(self):
        """Dict-shaped args (instead of list) should not crash parsing."""
        definition = json.dumps(
            [
                {
                    "func": "url-parse",
                    "component": "hostname",
                    "args": {"func": "raw-field", "id": "test"},
                },
            ],
        )
        df = pd.DataFrame(
            [
                {
                    "id": "dimensions/test_dict_args",
                    "name": "Dict Args",
                    "sourceFieldType": "derived",
                    "fieldDefinition": definition,
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        assert inventory.total_derived_fields == 1

    def test_non_string_delimiter_in_concat_does_not_crash(self):
        """Non-string delimiter in concatenate should not crash."""
        definition = json.dumps(
            [
                {"func": "raw-field", "id": "field_a", "label": "a"},
                {"func": "raw-field", "id": "field_b", "label": "b"},
                {
                    "func": "concatenate",
                    "delimiter": 42,
                    "args": [
                        {"func": "raw-field", "id": "field_a"},
                        {"func": "raw-field", "id": "field_b"},
                    ],
                },
            ],
        )
        df = pd.DataFrame(
            [
                {
                    "id": "dimensions/test_delim",
                    "name": "Non String Delim",
                    "sourceFieldType": "derived",
                    "fieldDefinition": definition,
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        assert inventory.total_derived_fields == 1
        assert inventory.fields[0].logic_summary

    def test_non_string_pattern_in_regex_does_not_crash(self):
        """Non-string pattern/replacement in regex-replace should not crash."""
        definition = json.dumps(
            [
                {"func": "raw-field", "id": "field_a", "label": "a"},
                {
                    "func": "regex-replace",
                    "pattern": {"regex": "test"},
                    "replacement": 123,
                    "args": [{"func": "raw-field", "id": "field_a"}],
                },
            ],
        )
        df = pd.DataFrame(
            [
                {
                    "id": "dimensions/test_regex",
                    "name": "Non String Regex",
                    "sourceFieldType": "derived",
                    "fieldDefinition": definition,
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        assert inventory.total_derived_fields == 1
        assert inventory.fields[0].logic_summary

    def test_regex_null_replacement_is_reported_as_remove(self):
        """replacement: null should be treated as removal, not literal 'None' text."""
        definition = json.dumps(
            [
                {"func": "raw-field", "id": "field_a", "label": "a"},
                {
                    "func": "regex-replace",
                    "pattern": "foo",
                    "replacement": None,
                    "args": [{"func": "raw-field", "id": "field_a"}],
                },
            ],
        )
        df = pd.DataFrame(
            [
                {
                    "id": "dimensions/test_regex_null_replace",
                    "name": "Regex Null Replacement",
                    "sourceFieldType": "derived",
                    "fieldDefinition": definition,
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        assert inventory.total_derived_fields == 1
        assert "remove" in inventory.fields[0].logic_summary.lower()
        assert '"None"' not in inventory.fields[0].logic_summary

    def test_non_list_match_preds_do_not_crash(self):
        """Dict-shaped preds payloads in predicates should be ignored safely."""
        definition = json.dumps(
            [
                {"func": "raw-field", "id": "field_a", "label": "a"},
                {
                    "func": "match",
                    "field": "a",
                    "branches": [
                        {
                            "pred": {
                                "func": "and",
                                "preds": {"func": "eq", "field": "a", "value": "x"},
                            },
                            "map-to": "X",
                        },
                    ],
                },
            ],
        )
        df = pd.DataFrame(
            [
                {
                    "id": "dimensions/test_non_list_preds",
                    "name": "Non List Preds",
                    "sourceFieldType": "derived",
                    "fieldDefinition": definition,
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        assert inventory.total_derived_fields == 1

    def test_non_dict_function_entries_do_not_crash(self):
        """Unexpected non-dict entries in function lists should be ignored."""
        definition = json.dumps(
            [
                "invalid_function_entry",
                {"func": "raw-field", "id": "field_a", "label": "a"},
                {
                    "func": "regex-replace",
                    "pattern": "foo",
                    "replacement": "bar",
                    "args": [{"func": "raw-field", "id": "field_a"}],
                },
            ],
        )
        df = pd.DataFrame(
            [
                {
                    "id": "dimensions/test_mixed_function_entries",
                    "name": "Mixed Entries",
                    "sourceFieldType": "derived",
                    "fieldDefinition": definition,
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        assert inventory.total_derived_fields == 1

    @pytest.mark.parametrize("bad_index", [float("nan"), float("inf"), float("-inf")])
    def test_non_finite_split_index_does_not_crash(self, bad_index):
        """Non-finite split indexes should fall back safely instead of raising."""
        df = pd.DataFrame(
            [
                {
                    "id": "dimensions/test_split_bad_index",
                    "name": "Split Bad Index",
                    "sourceFieldType": "derived",
                    "fieldDefinition": [
                        {"func": "raw-field", "id": "field_a", "label": "a"},
                        {
                            "func": "split",
                            "delimiter": "/",
                            "index": bad_index,
                            "args": [{"func": "raw-field", "id": "field_a"}],
                        },
                    ],
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        assert inventory.total_derived_fields == 1
        assert "part 1" in inventory.fields[0].logic_summary

    def test_non_string_dataset_in_lookup_does_not_crash(self):
        """Non-string dataset in classify/lookup should not crash."""
        definition = json.dumps(
            [
                {"func": "raw-field", "id": "field_a", "label": "a"},
                {
                    "func": "classify",
                    "mapping": {
                        "key-field": "field_a",
                        "value-field": "field_b",
                        "dataset": {"id": 123},
                    },
                },
            ],
        )
        df = pd.DataFrame(
            [
                {
                    "id": "dimensions/test_lookup",
                    "name": "Non String Dataset",
                    "sourceFieldType": "derived",
                    "fieldDefinition": definition,
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        assert inventory.total_derived_fields == 1
        assert "lookup" in inventory.fields[0].logic_summary.lower()

    def test_non_dict_branch_items_do_not_crash(self):
        """Non-dict items in match branches should be skipped safely."""
        definition = json.dumps(
            [
                {"func": "raw-field", "id": "field_a", "label": "a"},
                {
                    "func": "match",
                    "field": "a",
                    "branches": ["string_branch", 123, {"pred": {"func": "true"}, "map-to": "OK"}],
                },
            ],
        )
        df = pd.DataFrame(
            [
                {
                    "id": "dimensions/test_branches",
                    "name": "Non Dict Branches",
                    "sourceFieldType": "derived",
                    "fieldDefinition": definition,
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        assert inventory.total_derived_fields == 1

    def test_except_valueerror_in_isna_check(self):
        """Values that trigger ValueError in pd.isna() should be handled."""
        df = pd.DataFrame(
            [
                {
                    "id": "metrics/test_ve",
                    "name": "ValueError Test",
                    "sourceFieldType": "derived",
                    "fieldDefinition": {"ambiguous": True},
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        # Should not raise — the except (TypeError, ValueError) handles it
        inventory = builder.build(df, pd.DataFrame(), "dv_test", "Test")
        assert inventory.total_derived_fields == 0


# ==================== DESCRIPTION EXTRACTION TESTS ====================


class TestDescriptionExtraction:
    """Tests for description field extraction from data view components"""

    def test_description_extracted_from_row(self):
        """Test that description is extracted from row data"""
        df = pd.DataFrame(
            [
                {
                    "id": "metrics/test",
                    "name": "Test Metric",
                    "description": "This is a test metric description",
                    "sourceFieldType": "derived",
                    "fieldDefinition": json.dumps([{"func": "raw-field", "id": "test", "label": "test"}]),
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(df, pd.DataFrame(), "dv_test", "Test")

        assert len(inventory.fields) == 1
        assert inventory.fields[0].description == "This is a test metric description"

    def test_description_in_to_dict(self):
        """Test that description appears in to_dict output"""
        df = pd.DataFrame(
            [
                {
                    "id": "metrics/test",
                    "name": "Test Metric",
                    "description": "A description",
                    "sourceFieldType": "derived",
                    "fieldDefinition": json.dumps([{"func": "raw-field", "id": "test", "label": "test"}]),
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(df, pd.DataFrame(), "dv_test", "Test")
        field_dict = inventory.fields[0].to_dict()

        assert "description" in field_dict
        assert field_dict["description"] == "A description"

    def test_empty_description_shows_dash(self):
        """Test that empty description shows dash in to_dict"""
        df = pd.DataFrame(
            [
                {
                    "id": "metrics/test",
                    "name": "Test Metric",
                    "description": "",
                    "sourceFieldType": "derived",
                    "fieldDefinition": json.dumps([{"func": "raw-field", "id": "test", "label": "test"}]),
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(df, pd.DataFrame(), "dv_test", "Test")
        field_dict = inventory.fields[0].to_dict()

        assert field_dict["description"] == "-"

    def test_nan_description_handled(self):
        """Test that NaN description is handled gracefully"""
        df = pd.DataFrame(
            [
                {
                    "id": "metrics/test",
                    "name": "Test Metric",
                    "description": pd.NA,
                    "sourceFieldType": "derived",
                    "fieldDefinition": json.dumps([{"func": "raw-field", "id": "test", "label": "test"}]),
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(df, pd.DataFrame(), "dv_test", "Test")

        assert inventory.fields[0].description == ""

    def test_timestamp_description_handled(self):
        """Datetime-like descriptions should be preserved via scalar coercion."""
        df = pd.DataFrame(
            [
                {
                    "id": "metrics/test",
                    "name": "Test Metric",
                    "description": pd.Timestamp("2025-01-15T10:30:00Z"),
                    "sourceFieldType": "derived",
                    "fieldDefinition": json.dumps([{"func": "raw-field", "id": "test", "label": "test"}]),
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(df, pd.DataFrame(), "dv_test", "Test")

        assert inventory.fields[0].description != ""
        assert "2025-01-15" in inventory.fields[0].description

    def test_description_in_dataframe(self):
        """Test that description column appears in DataFrame output"""
        df = pd.DataFrame(
            [
                {
                    "id": "metrics/test",
                    "name": "Test Metric",
                    "description": "Test description",
                    "sourceFieldType": "derived",
                    "fieldDefinition": json.dumps([{"func": "raw-field", "id": "test", "label": "test"}]),
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(df, pd.DataFrame(), "dv_test", "Test")
        result_df = inventory.get_dataframe()

        assert "description" in result_df.columns
        assert result_df.iloc[0]["description"] == "Test description"


# ==================== SUMMARY COLUMN ALIAS TESTS ====================


class TestSummaryColumnAlias:
    """Tests for standardized summary column alias"""

    def test_summary_column_exists(self, sample_metrics_df, sample_dimensions_df):
        """Test that summary column exists in DataFrame"""
        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(sample_metrics_df, sample_dimensions_df, "dv_test", "Test")
        df = inventory.get_dataframe()

        assert "summary" in df.columns

    def test_summary_equals_logic_summary(self, sample_metrics_df, sample_dimensions_df):
        """Test that summary column equals logic_summary column"""
        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(sample_metrics_df, sample_dimensions_df, "dv_test", "Test")
        df = inventory.get_dataframe()

        assert all(df["summary"] == df["logic_summary"])

    def test_empty_dataframe_has_summary_column(self):
        """Test that empty DataFrame still has summary column"""
        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(pd.DataFrame(), pd.DataFrame(), "dv_test", "Test")
        df = inventory.get_dataframe()

        assert "summary" in df.columns


# ==================== NEW LOGIC SUMMARY HANDLER TESTS ====================


class TestNewLogicSummaryHandlers:
    """Tests for newly added logic summary handlers"""

    def test_typecast_summary(self):
        """Test logic summary for typecast function"""
        definition = json.dumps(
            [
                {"func": "raw-field", "id": "stringValue", "label": "input"},
                {"func": "typecast", "field": "input", "type": "integer"},
            ],
        )
        df = pd.DataFrame(
            [
                {
                    "id": "metrics/converted",
                    "name": "Converted Value",
                    "sourceFieldType": "derived",
                    "fieldDefinition": definition,
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(df, pd.DataFrame(), "dv_test", "Test")

        field = inventory.fields[0]
        assert "convert" in field.logic_summary.lower() or "integer" in field.logic_summary.lower()

    def test_datetime_bucket_summary(self):
        """Test logic summary for datetime-bucket function"""
        definition = json.dumps(
            [
                {"func": "raw-field", "id": "timestamp", "label": "ts"},
                {"func": "datetime-bucket", "field": "ts", "bucket": "week"},
            ],
        )
        df = pd.DataFrame(
            [
                {
                    "id": "dim/week",
                    "name": "Week",
                    "sourceFieldType": "derived",
                    "fieldDefinition": definition,
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        field = inventory.fields[0]
        assert "bucket" in field.logic_summary.lower() or "week" in field.logic_summary.lower()

    def test_datetime_slice_summary(self):
        """Test logic summary for datetime-slice function"""
        definition = json.dumps(
            [
                {"func": "raw-field", "id": "timestamp", "label": "ts"},
                {"func": "datetime-slice", "field": "ts", "component": "hour"},
            ],
        )
        df = pd.DataFrame(
            [
                {
                    "id": "dim/hour",
                    "name": "Hour",
                    "sourceFieldType": "derived",
                    "fieldDefinition": definition,
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        field = inventory.fields[0]
        assert "extract" in field.logic_summary.lower() or "hour" in field.logic_summary.lower()

    def test_timezone_shift_summary(self):
        """Test logic summary for timezone-shift function"""
        definition = json.dumps(
            [
                {"func": "raw-field", "id": "timestamp", "label": "ts"},
                {"func": "timezone-shift", "field": "ts", "from": "UTC", "to": "America/New_York"},
            ],
        )
        df = pd.DataFrame(
            [
                {
                    "id": "dim/local_time",
                    "name": "Local Time",
                    "sourceFieldType": "derived",
                    "fieldDefinition": definition,
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        field = inventory.fields[0]
        assert "shift" in field.logic_summary.lower() or "timezone" in field.logic_summary.lower()

    def test_find_replace_summary(self):
        """Test logic summary for find-replace function"""
        definition = json.dumps(
            [
                {"func": "raw-field", "id": "pageName", "label": "page"},
                {"func": "find-replace", "field": "page", "find": "www.", "replace": ""},
            ],
        )
        df = pd.DataFrame(
            [
                {
                    "id": "dim/clean_page",
                    "name": "Clean Page",
                    "sourceFieldType": "derived",
                    "fieldDefinition": definition,
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        field = inventory.fields[0]
        assert "replace" in field.logic_summary.lower() or "remove" in field.logic_summary.lower()

    def test_depth_summary(self):
        """Test logic summary for depth function"""
        definition = json.dumps(
            [
                {"func": "raw-field", "id": "pagePath", "label": "path"},
                {"func": "depth", "field": "path", "delimiter": "/"},
            ],
        )
        df = pd.DataFrame(
            [
                {
                    "id": "dim/page_depth",
                    "name": "Page Depth",
                    "sourceFieldType": "derived",
                    "fieldDefinition": definition,
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        field = inventory.fields[0]
        assert "depth" in field.logic_summary.lower()
        assert "'/'" in field.logic_summary  # delimiter included in output

    def test_profile_summary(self):
        """Test logic summary for profile function"""
        definition = json.dumps([{"func": "profile", "attribute": "loyaltyTier", "namespace": "customer"}])
        df = pd.DataFrame(
            [
                {
                    "id": "dim/loyalty",
                    "name": "Loyalty Tier",
                    "sourceFieldType": "derived",
                    "fieldDefinition": definition,
                    "dataSetType": "event",
                },
            ],
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(pd.DataFrame(), df, "dv_test", "Test")

        field = inventory.fields[0]
        assert "profile" in field.logic_summary.lower() or "loyaltyTier" in field.logic_summary


# ==================== ROW ITERATION EQUIVALENCE ====================


class TestBuildRowIterationEquivalence:
    """Characterization tests pinning build() outputs for mixed-dtype frames.

    Guards row-iteration refactors (iterrows vs records): NA definitions are
    skipped silently, non-derived rows are ignored, NA descriptions coerce to
    empty string, and pure-numeric columns must not affect extraction.
    """

    def test_build_pins_field_values_with_mixed_dtypes_and_na(self, sample_derived_field_definition):
        metrics_df = pd.DataFrame(
            {
                "id": ["metrics/one", "metrics/two", "metrics/three"],
                "name": ["One", "Two", "Three"],
                "description": ["First metric", None, "Third metric"],
                "sourceFieldType": ["derived", "derived", "standard"],
                "type": ["int", "decimal", "int"],
                "fieldDefinition": [sample_derived_field_definition, pd.NA, pd.NA],
                "sortOrder": [1, 2, 3],
            },
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(metrics_df, pd.DataFrame(), "dv_pin", "Pin View")

        # Only the first row survives: NA definition and non-derived rows skip.
        assert inventory.metrics_count == 1
        assert inventory.dimensions_count == 0
        field = inventory.fields[0]
        assert field.component_id == "metrics/one"
        assert field.component_name == "One"
        assert field.component_type == "Metric"
        assert field.description == "First metric"
        assert field.definition_json == sample_derived_field_definition

    def test_build_coerces_na_description_to_empty_string(self, sample_math_only_field):
        metrics_df = pd.DataFrame(
            {
                "id": ["metrics/profit"],
                "name": ["Profit"],
                "description": [pd.NA],
                "sourceFieldType": ["derived"],
                "fieldDefinition": [sample_math_only_field],
            },
        )

        builder = DerivedFieldInventoryBuilder()
        inventory = builder.build(metrics_df, pd.DataFrame(), "dv_pin", "Pin View")

        assert inventory.metrics_count == 1
        assert inventory.fields[0].description == ""
