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
