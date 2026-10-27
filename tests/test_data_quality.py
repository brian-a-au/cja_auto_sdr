"""Tests for data quality validation"""

import logging
import os
import sys

import pandas as pd

# Import the class we're testing
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from cja_auto_sdr.generator import DataQualityChecker


class TestDataQualityValidation:
    """Test data quality validation functions"""

    def test_duplicate_detection_metrics(self, sample_metrics_df):
        """Test detection of duplicate metric names"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        # Add a duplicate
        duplicate_df = pd.concat(
            [
                sample_metrics_df,
                pd.DataFrame(
                    [
                        {
                            "id": "metric3",
                            "name": "Test Metric 1",  # Duplicate name
                            "type": "calculated",
                            "title": "Duplicate Metric",
                            "description": "Duplicate",
                        },
                    ],
                ),
            ],
            ignore_index=True,
        )

        validator.check_duplicates(duplicate_df, "Metrics")
        issues_df = validator.get_issues_dataframe()

        # Should detect duplicate names
        assert len(issues_df) > 0
        assert any("duplicate" in str(row["Issue"]).lower() for _, row in issues_df.iterrows())

    def test_duplicate_detection_dimensions(self, sample_dimensions_df):
        """Test detection of duplicate dimension names"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        validator.check_duplicates(sample_dimensions_df, "Dimensions")
        issues_df = validator.get_issues_dataframe()

        # sample_dimensions_df already has duplicates
        assert len(issues_df) > 0

    def test_missing_description_detection(self, sample_metrics_df):
        """Test detection of missing descriptions"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        validator.check_missing_descriptions(sample_metrics_df, "Metrics")
        issues_df = validator.get_issues_dataframe()

        # Should detect missing description in metric2
        assert len(issues_df) > 0

    def test_null_value_detection(self, sample_metrics_df):
        """Test detection of null values in critical fields"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        validator.check_null_values(sample_metrics_df, "Metrics", ["id", "name", "description"])
        issues_df = validator.get_issues_dataframe()

        # Should detect null values
        assert len(issues_df) > 0

    def test_empty_dataset_detection(self):
        """Test detection of empty datasets"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        empty_df = pd.DataFrame()
        validator.check_empty_dataframe(empty_df, "Metrics")
        issues_df = validator.get_issues_dataframe()

        # Should detect empty dataset
        assert len(issues_df) > 0
        assert any(
            "empty" in str(row["Issue"]).lower() or "no" in str(row["Issue"]).lower() for _, row in issues_df.iterrows()
        )

    def test_severity_levels(self, sample_metrics_df):
        """Test that severity levels are assigned correctly"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        validator.check_missing_descriptions(sample_metrics_df, "Metrics")
        issues_df = validator.get_issues_dataframe()

        # Check that severity levels are valid
        valid_severities = ["CRITICAL", "HIGH", "MEDIUM", "LOW", "INFO"]
        for _, issue in issues_df.iterrows():
            assert issue["Severity"] in valid_severities

    def test_issue_structure(self, sample_metrics_df):
        """Test that issues have required fields"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        validator.check_missing_descriptions(sample_metrics_df, "Metrics")
        issues_df = validator.get_issues_dataframe()

        required_fields = ["Severity", "Category", "Type", "Item Name", "Issue", "Details"]
        for field in required_fields:
            assert field in issues_df.columns

    def test_required_field_validation(self):
        """Test validation of required fields"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        # Create DataFrame with missing required fields
        incomplete_df = pd.DataFrame(
            [
                {
                    "id": "metric1",
                    "name": None,  # Missing required field
                    "type": "calculated",
                },
            ],
        )

        validator.check_required_fields(incomplete_df, "Metrics", ["id", "name", "type"])
        issues_df = validator.get_issues_dataframe()

        # Should detect missing required fields
        assert len(issues_df) > 0

    def test_id_validity_check(self):
        """Test ID validity checking"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        # Create DataFrame with invalid IDs
        df_with_invalid_ids = pd.DataFrame(
            [
                {"id": None, "name": "Test 1", "type": "metric"},
                {"id": "", "name": "Test 2", "type": "metric"},
                {"id": "valid_id", "name": "Test 3", "type": "metric"},
            ],
        )

        validator.check_id_validity(df_with_invalid_ids, "Metrics")
        issues_df = validator.get_issues_dataframe()

        # Should detect invalid IDs
        assert len(issues_df) > 0

    def test_multiple_checks_combined(self, sample_metrics_df, sample_dimensions_df):
        """Test running multiple validation checks"""
        logger = logging.getLogger("test")
        validator = DataQualityChecker(logger)

        # Run multiple checks
        validator.check_duplicates(sample_metrics_df, "Metrics")
        validator.check_missing_descriptions(sample_metrics_df, "Metrics")
        validator.check_null_values(sample_metrics_df, "Metrics", ["description"])
        validator.check_duplicates(sample_dimensions_df, "Dimensions")

        issues_df = validator.get_issues_dataframe()

        # Should have issues from multiple checks
        assert len(issues_df) > 0
        # Should have both Metrics and Dimensions issues
        assert "Metrics" in issues_df["Type"].values
        assert "Dimensions" in issues_df["Type"].values


# ==================== Rule identity and component membership ====================

import pytest  # noqa: E402

from cja_auto_sdr.api.cache import ValidationCache  # noqa: E402
from cja_auto_sdr.api.quality import (  # noqa: E402
    CUSTOM_RULE_ID,
    QUALITY_RULE_IDS,
    partition_component_ids,
)

REQ = ["id", "name"]
CRIT = ["id", "name"]


def _identity_checker(cache=None):
    return DataQualityChecker(logging.getLogger("test_identity"), validation_cache=cache, quiet=True)


def _metrics_df(n=30, description="", names=None):
    return pd.DataFrame(
        {
            "id": [f"metrics/m{i:02d}" for i in range(n)],
            "name": names or [f"Metric {i}" for i in range(n)],
            "description": [description] * n,
        },
    )


def _by_category(checker, category):
    return [i for i in checker.issues if i["Category"] == category]


def test_missing_descriptions_lists_all_ids_in_one_issue():
    df = _metrics_df(n=30)
    checker = _identity_checker()
    checker.check_all_quality_issues_optimized(df, "Metrics", REQ, CRIT)
    [issue] = _by_category(checker, "Missing Descriptions")
    assert issue["Rule ID"] == "dq.missing_description.v1"
    assert issue["Component IDs"] == sorted(df["id"])
    assert issue["Occurrences"] == 30
    assert issue["Unaddressable IDs"] == 0


def test_rename_preserves_rule_and_component_identity():
    a = _identity_checker()
    b = _identity_checker()
    a.check_all_quality_issues_optimized(_metrics_df(n=5), "Metrics", REQ, CRIT)
    renamed = _metrics_df(n=5, names=[f"Renamed {i}" for i in range(5)])
    b.check_all_quality_issues_optimized(renamed, "Metrics", REQ, CRIT)
    [ia] = _by_category(a, "Missing Descriptions")
    [ib] = _by_category(b, "Missing Descriptions")
    assert ia["Rule ID"] == ib["Rule ID"]
    assert ia["Component IDs"] == ib["Component IDs"]


def test_row_order_does_not_change_membership():
    df = _metrics_df(n=10)
    shuffled = df.sample(frac=1, random_state=3).reset_index(drop=True)
    a, b = _identity_checker(), _identity_checker()
    a.check_all_quality_issues_optimized(df, "Metrics", REQ, CRIT)
    b.check_all_quality_issues_optimized(shuffled, "Metrics", REQ, CRIT)
    assert (
        _by_category(a, "Missing Descriptions")[0]["Component IDs"]
        == _by_category(b, "Missing Descriptions")[0]["Component IDs"]
    )


def test_partition_component_ids_counts_unaddressable():
    assert partition_component_ids(["b", "a", "a", None, "", "  ", float("nan"), {"x": 1}]) == (["a", "b"], 5)


def test_partition_component_ids_bool_unaddressable_and_ints_stringified():
    assert partition_component_ids([True, 7, False, pd.NA]) == (["7"], 3)


def test_legacy_and_optimized_paths_agree_on_rules():
    df = pd.DataFrame(
        {
            "id": ["a", "b", "c", None],
            "name": ["Dup", "Dup", None, "Solo"],
            "description": ["", "ok", "ok", None],
        },
    )
    opt = _identity_checker()
    opt.check_all_quality_issues_optimized(df, "Metrics", REQ, CRIT)
    legacy = _identity_checker()
    legacy.check_duplicates(df, "Metrics")
    legacy.check_null_values(df, "Metrics", CRIT)
    legacy.check_missing_descriptions(df, "Metrics")
    legacy.check_id_validity(df, "Metrics")

    def key(issue):
        return (
            issue["Category"],
            issue["Item Name"],
            issue["Rule ID"],
            tuple(issue["Component IDs"]),
            issue["Occurrences"],
            issue["Unaddressable IDs"],
        )

    assert sorted(map(key, opt.issues)) == sorted(map(key, legacy.issues))
    [invalid] = _by_category(opt, "Invalid IDs")
    assert invalid["Component IDs"] == [] and invalid["Occurrences"] == 1 and invalid["Unaddressable IDs"] == 1
    [dup] = _by_category(opt, "Duplicates")
    assert dup["Component IDs"] == ["a", "b"] and dup["Rule ID"] == QUALITY_RULE_IDS["Duplicates"]


def test_null_values_membership_and_unaddressable():
    df = pd.DataFrame({"id": ["a", None, "c"], "name": ["x", "y", None], "description": ["d"] * 3})
    checker = _identity_checker()
    checker.check_all_quality_issues_optimized(df, "Metrics", REQ, CRIT)
    nulls = {i["Item Name"]: i for i in _by_category(checker, "Null Values")}
    by_desc = {i["Issue"]: i for i in _by_category(checker, "Null Values")}
    assert len(nulls) == 2
    assert by_desc['Null values in "name" field']["Component IDs"] == ["c"]
    assert by_desc['Null values in "id" field']["Unaddressable IDs"] == 1


def test_empty_and_missing_fields_have_no_components():
    checker = _identity_checker()
    checker.check_all_quality_issues_optimized(pd.DataFrame(), "Metrics", REQ, CRIT)
    checker.check_all_quality_issues_optimized(pd.DataFrame({"id": ["a"]}), "Dimensions", REQ, CRIT)
    for issue in checker.issues:
        assert issue["Component IDs"] == [] and issue["Occurrences"] == 1 and issue["Unaddressable IDs"] == 0
    assert checker.issues[0]["Rule ID"] == "dq.empty_data.v1"
    assert checker.issues[1]["Rule ID"] == "dq.missing_required_fields.v1"


def test_custom_add_issue_gets_custom_rule():
    checker = _identity_checker()
    assert checker.add_issue("LOW", "My Check", "Metrics", "x", "d")["Rule ID"] == CUSTOM_RULE_ID == "dq.custom.unknown"
    explicit = checker.add_issue("LOW", "My Check", "Metrics", "x", "d", rule_id="dq.mine.v1", component_ids=["a", 3])
    assert explicit["Rule ID"] == "dq.mine.v1"
    assert explicit["Component IDs"] == ["3", "a"] and explicit["Occurrences"] == 2


def test_cached_issue_without_rule_id_is_normalized():
    cache = ValidationCache()
    df = _metrics_df(n=3)
    _, key = cache.get(df, "Metrics", REQ, CRIT)
    legacy = {
        "Severity": "LOW",
        "Category": "Missing Descriptions",
        "Type": "Metrics",
        "Item Name": "3 items",
        "Issue": "3 items without descriptions",
        "Details": "x",
    }
    cache._cache[key] = ([legacy], __import__("time").monotonic())
    checker = _identity_checker(cache)
    checker.check_all_quality_issues_optimized(df, "Metrics", REQ, CRIT)
    [issue] = checker.issues
    assert issue["Rule ID"] == "dq.missing_description.v1"
    assert issue["Component IDs"] == [] and issue["Occurrences"] == 1 and issue["Unaddressable IDs"] == 0
    assert "Rule ID" not in legacy


def test_cache_returns_independent_component_id_lists():
    cache = ValidationCache()
    df = _metrics_df(n=3)
    _identity_checker(cache).check_all_quality_issues_optimized(df, "Metrics", REQ, CRIT)
    second = _identity_checker(cache)
    second.check_all_quality_issues_optimized(df, "Metrics", REQ, CRIT)  # cache hit
    assert cache._hits == 1
    second.issues[0]["Component IDs"].append("mutated")
    third = _identity_checker(cache)
    third.check_all_quality_issues_optimized(df, "Metrics", REQ, CRIT)
    assert "mutated" not in _by_category(third, "Missing Descriptions")[0]["Component IDs"]


def test_data_quality_columns_identical_for_clean_and_issue_runs():
    from cja_auto_sdr.generator import DATA_QUALITY_COLUMNS, build_json_payload

    clean = _identity_checker()
    clean_df = clean.get_issues_dataframe()
    issue = _identity_checker()
    issue.check_all_quality_issues_optimized(_metrics_df(n=3), "Metrics", REQ, CRIT)
    issue_df = issue.get_issues_dataframe()
    assert list(clean_df.columns) == list(issue_df.columns) == list(DATA_QUALITY_COLUMNS)
    assert clean_df.iloc[0]["Component IDs"] == [] and clean_df.iloc[0]["Occurrences"] == 0
    assert clean_df.iloc[0]["Rule ID"] is None
    keys = []
    for frame in (clean_df, issue_df):
        payload = build_json_payload({"Data Quality": frame}, {})
        keys.append(list(payload["data_quality"][0].keys()))
    assert keys[0] == keys[1] == list(DATA_QUALITY_COLUMNS)


def test_severity_counts_unchanged_for_grouped_issue():
    from cja_auto_sdr.api.quality_policy import count_quality_issues_by_severity

    checker = _identity_checker()
    checker.check_all_quality_issues_optimized(_metrics_df(n=30), "Metrics", REQ, CRIT)
    assert count_quality_issues_by_severity(checker.issues)["LOW"] == 1


def test_parallel_path_yields_identity_fields():
    checker = _identity_checker()
    checker.check_all_parallel(_metrics_df(n=4), _metrics_df(n=2), REQ, REQ, CRIT)
    assert all(i["Rule ID"] == "dq.missing_description.v1" for i in checker.issues)
    assert sorted(len(i["Component IDs"]) for i in checker.issues) == [2, 4]


def test_issues_dataframe_column_order():
    checker = _identity_checker()
    checker.check_all_quality_issues_optimized(_metrics_df(n=3), "Metrics", REQ, CRIT)
    assert list(checker.get_issues_dataframe().columns) == [
        "Severity",
        "Category",
        "Type",
        "Item Name",
        "Issue",
        "Details",
        "Rule ID",
        "Component IDs",
        "Occurrences",
        "Unaddressable IDs",
    ]


@pytest.mark.parametrize("bad", [True, 1.5, {"a": 1}])
def test_partition_rejects_non_str_int(bad):
    assert partition_component_ids([bad]) == ([], 1)
