"""
Tests that exercise pragma-guarded defensive code paths in inventory modules.

v3.5.12: Coverage hardening — removes pragma: no cover from 5 lines across
calculated_metrics.py, segments.py, and derived_fields.py by crafting payloads
that bypass upstream isinstance filters.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pandas as pd

from cja_auto_sdr.inventory.calculated_metrics import (
    CalculatedMetricsInventoryBuilder,
)


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
