"""
Tests that exercise pragma-guarded defensive code paths in inventory modules.

v3.5.12: Coverage hardening — removes pragma: no cover from 5 lines across
calculated_metrics.py, segments.py, and derived_fields.py by crafting payloads
that bypass upstream isinstance filters.

Note: ``except TypeError, ValueError:`` in the source uses PEP 758 bare-comma
syntax (Python 3.14+), not the legacy Python 2 form — no parentheses required.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pandas as pd

from cja_auto_sdr.inventory.calculated_metrics import (
    CalculatedMetricsInventoryBuilder,
)
from cja_auto_sdr.inventory.derived_fields import DerivedFieldInventoryBuilder
from cja_auto_sdr.inventory.segments import SegmentsInventoryBuilder

# ==================== HELPERS ====================


def _cm_builder():
    return CalculatedMetricsInventoryBuilder()


# ==================== Task 1: calculated_metrics traverse() non-dict guard ====================


class TestCalcMetricsTraverseNonDict:
    """Exercise line 630: `if not isinstance(node, dict)` inside traverse().

    _parse_formula() calls traverse(formula, depth) at line 702 without any
    isinstance guard. Passing a non-dict as the formula argument hits line 630
    directly, causing an early return with zero-valued defaults.
    """

    def test_string_formula_returns_empty_result(self):
        """String formula hits the guard; returns dict with empty/zero fields."""
        builder = _cm_builder()
        result = builder._parse_formula("not_a_dict")
        assert result["functions_internal"] == []
        assert result["metric_references"] == []
        assert result["operator_count"] == 0
        assert result["nesting_depth"] == 0

    def test_int_formula_returns_empty_result(self):
        """Integer formula hits the guard."""
        builder = _cm_builder()
        result = builder._parse_formula(42)
        assert result["functions_internal"] == []
        assert result["operator_count"] == 0

    def test_none_formula_returns_empty_result(self):
        """None formula hits the guard."""
        builder = _cm_builder()
        result = builder._parse_formula(None)
        assert result["functions_internal"] == []
        assert result["operator_count"] == 0

    def test_list_formula_returns_empty_result(self):
        """List formula hits the guard (list is not a dict)."""
        builder = _cm_builder()
        result = builder._parse_formula([{"func": "add"}])
        assert result["functions_internal"] == []
        assert result["operator_count"] == 0


def _seg_builder():
    return SegmentsInventoryBuilder()


# ==================== Task 2: segments traverse() non-dict guard ====================


class TestSegmentsTraverseNonDict:
    """Exercise line 594: `if not isinstance(node, dict)` inside traverse().

    _parse_definition() calls traverse(definition, depth) at line 701 without
    a guard. Passing a non-dict as definition hits line 594 directly.
    """

    def test_string_definition_returns_zero_counts(self):
        """String definition hits the guard; all counters stay at zero."""
        builder = _seg_builder()
        result = builder._parse_definition("not_a_dict")
        assert result["predicate_count"] == 0
        assert result["nesting_depth"] == 0
        assert result["logic_operator_count"] == 0
        assert result["container_count"] == 0

    def test_none_definition_returns_zero_counts(self):
        """None definition hits the guard."""
        builder = _seg_builder()
        result = builder._parse_definition(None)
        assert result["predicate_count"] == 0

    def test_int_definition_returns_zero_counts(self):
        """Integer definition hits the guard."""
        builder = _seg_builder()
        result = builder._parse_definition(42)
        assert result["predicate_count"] == 0

    def test_list_definition_returns_zero_counts(self):
        """List definition hits the guard (list is not a dict)."""
        builder = _seg_builder()
        result = builder._parse_definition([{"func": "eq"}])
        assert result["predicate_count"] == 0


def _df_builder():
    return DerivedFieldInventoryBuilder()


def _build_one_df(definition):
    """Build a single derived field from a definition and return the inventory."""
    builder = _df_builder()
    field_def = json.dumps(definition) if isinstance(definition, list) else definition
    df = pd.DataFrame(
        [
            {
                "id": "dimensions/test_field",
                "name": "Test Field",
                "sourceFieldType": "derived",
                "fieldDefinition": field_def,
                "dataSetType": "event",
            }
        ]
    )
    return builder.build(pd.DataFrame(), df, "dv_test", "Test")


# ==================== Task 3: pd.isna TypeError/ValueError guard ====================


class TestParseDefinitionIsnaGuard:
    """Exercise line 376: except TypeError, ValueError around pd.isna().

    pd.isna() can raise TypeError on objects that define __len__ in ways
    that conflict with pandas internals. We mock pd.isna to force the
    exception and verify the fallback path treats the value as non-null.
    """

    def test_isna_typeerror_falls_back_to_none_check(self):
        """When pd.isna raises TypeError, field_def is treated as non-null."""
        definition = [{"func": "raw-field", "id": "test.field", "label": "f"}]
        field_def_str = json.dumps(definition)

        builder = _df_builder()
        row = pd.Series(
            {
                "id": "dimensions/test",
                "name": "Test",
                "sourceFieldType": "derived",
                "fieldDefinition": field_def_str,
                "dataSetType": "event",
            }
        )

        with patch("cja_auto_sdr.inventory.derived_fields.pd.isna", side_effect=TypeError("mock")):
            result = builder._process_row(row, "event", stats=None)

        assert result is not None
        assert result.component_name == "Test"

    def test_isna_valueerror_falls_back_to_none_check(self):
        """When pd.isna raises ValueError, field_def is treated as non-null."""
        definition = [{"func": "raw-field", "id": "test.field", "label": "f"}]
        field_def_str = json.dumps(definition)

        builder = _df_builder()
        row = pd.Series(
            {
                "id": "dimensions/test",
                "name": "Test",
                "sourceFieldType": "derived",
                "fieldDefinition": field_def_str,
                "dataSetType": "event",
            }
        )

        with patch("cja_auto_sdr.inventory.derived_fields.pd.isna", side_effect=ValueError("mock")):
            result = builder._process_row(row, "event", stats=None)

        assert result is not None

    def test_isna_exception_with_none_field_def_returns_none(self):
        """When pd.isna raises and field_def IS None, fallback detects it."""
        builder = _df_builder()
        row = pd.Series(
            {
                "id": "dimensions/test",
                "name": "Test",
                "sourceFieldType": "derived",
                "fieldDefinition": None,
                "dataSetType": "event",
            }
        )

        with patch("cja_auto_sdr.inventory.derived_fields.pd.isna", side_effect=TypeError("mock")):
            result = builder._process_row(row, "event", stats=None)

        # field_def is None → is_na fallback sets True → returns None
        assert result is None


# ==================== Task 4: _coerce_int_index overflow guard ====================


class TestCoerceIntIndexOverflowGuard:
    """Exercise line 617: except TypeError, ValueError, OverflowError on int().

    The isfinite() check at line 613 catches inf/nan, but a float subclass
    that passes isfinite yet fails int() exercises the guard directly.
    """

    def test_normal_float_converts(self):
        """Baseline: normal float converts correctly."""
        builder = _df_builder()
        assert builder._coerce_int_index(3.0) == 3

    def test_inf_returns_default(self):
        """math.inf caught by isfinite check, returns default."""
        import math

        builder = _df_builder()
        assert builder._coerce_int_index(math.inf) == 0
        assert builder._coerce_int_index(math.inf, default=99) == 99

    def test_nan_returns_default(self):
        """NaN caught by isfinite check, returns default."""
        import math

        builder = _df_builder()
        assert builder._coerce_int_index(math.nan) == 0

    def test_neg_inf_returns_default(self):
        """Negative infinity returns default."""
        import math

        builder = _df_builder()
        assert builder._coerce_int_index(-math.inf, default=-1) == -1

    def test_int_conversion_exception_returns_default(self):
        """Force the guard path via a float subclass that fails int()."""
        builder = _df_builder()

        class BadFloat(float):
            """A float subclass that passes isfinite but fails int()."""

            def __int__(self):
                raise OverflowError("cannot convert")

        val = BadFloat(1.0)
        result = builder._coerce_int_index(val, default=42)
        assert result == 42


# ==================== Task 5: classify lookup_references fallback ====================


class TestClassifyLookupReferencesFallback:
    """Exercise line 788: `elif parsed['lookup_references']` branch.

    This branch fires when:
    1. functions_internal contains 'classify'
    2. _describe_lookup_logic() returns '' (no truthy key-field)
    3. parsed['rule_names'] is empty
    4. parsed['lookup_references'] is non-empty

    The edge case: key-field=0 passes str() normalization in _parse_definition
    but fails the truthiness check in _describe_lookup_logic.
    """

    def test_classify_with_falsy_key_field_hits_lookup_refs_fallback(self):
        """classify with key-field=0 populates lookup_references but not lookup details."""
        definition = [
            {"func": "raw-field", "id": "test.field", "label": "base"},
            {
                "func": "classify",
                "mapping": {"key-field": 0, "value-field": "result", "dataset": "lookup/my_dataset"},
            },
        ]
        summary = _build_one_df(definition)
        assert summary.total_derived_fields == 1
        field = summary.fields[0]
        # Line 789 produces: "Lookup from {parsed['lookup_references'][0]}"
        assert "Lookup from" in field.logic_summary

    def test_classify_with_false_key_field_hits_fallback(self):
        """classify with key-field=False: same divergence pattern."""
        definition = [
            {"func": "raw-field", "id": "test.field", "label": "base"},
            {
                "func": "classify",
                "mapping": {"key-field": False, "value-field": "result"},
            },
        ]
        summary = _build_one_df(definition)
        assert summary.total_derived_fields == 1
        field = summary.fields[0]
        # "False" is truthy as a string, so lookup_references gets ["False"]
        assert "Lookup from" in field.logic_summary
