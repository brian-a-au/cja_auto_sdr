"""Tests for DataViewComparator._normalize_value method

Validates that _normalize_value correctly normalizes various input types
for consistent diff comparison.
"""

import numpy as np


class TestNormalizeValue:
    """Tests for _normalize_value method of DataViewComparator"""

    def test_normalize_value_stable_across_types(self):
        """Test that _normalize_value produces expected outputs for all supported types.

        Validates:
        - None → ""
        - NaN (float) → ""
        - NaN (numpy) → ""
        - Strings are stripped
        - Numbers pass through
        - Booleans pass through
        - Lists are normalized element-wise
        - Dicts are normalized recursively
        - Tuples pass through
        """
        from cja_auto_sdr.diff.comparator import DataViewComparator

        cmp = DataViewComparator()  # confirmed: all constructor args are optional

        # None and NaN values normalize to ""
        assert cmp._normalize_value(None) == ""
        assert cmp._normalize_value(float("nan")) == ""
        assert cmp._normalize_value(np.nan) == ""

        # Strings are stripped of leading/trailing whitespace
        assert cmp._normalize_value("  s  ") == "s"
        assert cmp._normalize_value("") == ""

        # Numbers pass through unchanged
        assert cmp._normalize_value(0) == 0
        assert cmp._normalize_value(1) == 1
        assert cmp._normalize_value(2.5) == 2.5

        # Booleans pass through unchanged (identity check)
        assert cmp._normalize_value(True) is True
        assert cmp._normalize_value(False) is False

        # Lists are normalized element-wise, order preserved by default
        assert cmp._normalize_value([1, 2]) == [1, 2]
        assert cmp._normalize_value(["  a  ", "  b  "]) == ["a", "b"]

        # Dicts are normalized recursively (keys sorted, empty values removed)
        assert cmp._normalize_value({"a": 1}) == {"a": 1}
        assert cmp._normalize_value({"a": "  s  "}) == {"a": "s"}

        # Tuples fall through to `return value` (pass through unchanged)
        assert cmp._normalize_value((1,)) == (1,)
        assert cmp._normalize_value(("a", "b")) == ("a", "b")


class TestInventoryDefinitions:
    @staticmethod
    def compare(source, target, kind="segment", ignores=()):
        from cja_auto_sdr.diff.comparator import DataViewComparator

        return DataViewComparator(ignore_fields=list(ignores))._find_inventory_changed_fields(
            {"id": "one", "definition_json": source}, {"id": "one", "definition_json": target}, kind
        )

    def test_json_types_order_and_whitespace(self):
        assert not self.compare('{"b": 2, "a": [true, 1]}', '{ "a": [true,1], "b":2}')
        for left, right in (("true", "1"), ("false", "0"), ("[1,2]", "[2,1]"), ('"a"', '"b"')):
            assert set(self.compare(left, right)) == {"definition_json"}

    def test_missing_empty_and_ignored_do_not_parse(self, caplog):
        for missing in (None, ""):
            assert not self.compare(missing, "invalid")
        assert "missing or empty definition_json" in caplog.text
        assert not self.compare("invalid", "also invalid", ignores=("definition_json",))

    def test_invalid_compared_pair_fails(self):
        import pytest

        with pytest.raises(ValueError, match="Invalid target segment definition_json"):
            self.compare("{}", "invalid")

    def test_only_shared_items_parse_definitions(self):
        from cja_auto_sdr.diff.comparator import DataViewComparator
        from cja_auto_sdr.diff.models import ChangeType

        diffs = DataViewComparator()._compare_inventory_items(
            [{"segment_id": "old", "definition_json": "invalid"}],
            [{"segment_id": "new", "definition_json": "invalid"}],
            "segment",
            id_field="segment_id",
        )
        assert {item.change_type for item in diffs} == {ChangeType.ADDED, ChangeType.REMOVED}

    def test_reference_masks_preserve_unrelated_fields_and_shape(self):
        import json
        from copy import deepcopy

        cases = [
            (
                "segment",
                "segment_references",
                {"pred": {"segment": {"id": "old", "name": "untouched"}, "val": 4}},
                ("pred", "segment", "id"),
            ),
            (
                "segment",
                "dimension_references",
                {"pred": {"dim": [None, {"name": "old", "id": None}], "val": 4}},
                ("pred", "dim", 1, "name"),
            ),
            ("segment", "metric_references", {"pred": {"metric": "old", "val": 4}}, ("pred", "metric")),
            (
                "calculated_metric",
                "metric_references",
                {"formula": {"func": " metric ", "name": {"metric": "old", "extra": 4}, "value": 4}},
                ("formula", "name", "metric"),
            ),
            (
                "calculated_metric",
                "segment_references",
                {"formula": {"func": "segment", "id": "old", "value": 4}},
                ("formula", "id"),
            ),
            (
                "calculated_metric",
                "segment_references",
                {
                    "formula": {
                        "func": "segment",
                        "segment_id": [None, {"segment_id": "old", "name": "untouched"}],
                        "value": 4,
                    }
                },
                ("formula", "segment_id", 1, "segment_id"),
            ),
        ]
        for kind, ignore, source, path in cases:
            target = deepcopy(source)
            parent = target
            for key in path[:-1]:
                parent = parent[key]
            parent[path[-1]] = "new"
            before = deepcopy((source, target))
            assert not self.compare(json.dumps(source), json.dumps(target), kind, (ignore,))
            assert self.compare(json.dumps(source), json.dumps(target), kind)
            assert (source, target) == before
            node = target["pred" if kind == "segment" else "formula"]
            node["val" if kind == "segment" else "value"] = 5
            assert self.compare(json.dumps(source), json.dumps(target), kind, (ignore,))
            node["unknown"] = {"id": "different", "name": "different", "segment": "different"}
            assert self.compare(json.dumps(source), json.dumps(target), kind, (ignore,))

    def test_unknown_traversal_nodes_are_not_masked(self):
        assert self.compare(
            '{"unknown":{"segment":"old"}}', '{"unknown":{"segment":"new"}}', ignores=("segment_references",)
        )
        assert self.compare(
            '{"formula":{"func":"other","name":"old","id":"old"}}',
            '{"formula":{"func":"other","name":"new","id":"new"}}',
            "calculated_metric",
            ("metric_references", "segment_references"),
        )
