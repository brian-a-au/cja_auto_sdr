"""Characterization and regression tests for org pairwise Jaccard similarity."""

import logging
from copy import deepcopy
from unittest.mock import MagicMock

import pytest

from cja_auto_sdr.org.analyzer import OrgComponentAnalyzer
from cja_auto_sdr.org.models import DataViewSummary, OrgReportConfig


def _dv(dv_id, metrics, dims):
    return DataViewSummary(
        data_view_id=dv_id,
        data_view_name=f"DV {dv_id}",
        metric_ids=set(metrics),
        dimension_ids=set(dims),
    )


def test_pairwise_jaccard_values_are_stable():
    summaries = [
        _dv("a", ["m1", "m2", "m3"], ["d1", "d2"]),
        _dv("b", ["m2", "m3", "m4"], ["d2", "d3"]),
        _dv("c", ["m9"], ["d9"]),
    ]
    # OrgComponentAnalyzer.__init__ requires (cja, config, logger); _compute_pairwise_jaccard
    # never touches self.cja, so a MagicMock stands in for the API client.
    analyzer = OrgComponentAnalyzer(cja=MagicMock(), config=OrgReportConfig(), logger=logging.getLogger("t"))
    valid, pairwise = analyzer._compute_pairwise_jaccard(summaries)
    # intersection(a, b) = {m2,m3,d2} = 3 ; union(a, b) = {m1,m2,m3,m4,d1,d2,d3} = 7
    assert pairwise[(0, 1)] == 3 / 7
    assert pairwise[(0, 2)] == 0.0
    assert pairwise[(1, 2)] == 0.0
    assert [s.data_view_id for s in valid] == ["a", "b", "c"]


def test_pairwise_filters_preserve_order_and_evaluate_components_once(monkeypatch):
    summaries = [
        _dv("z", ["shared", "m1"], ["shared", "d1"]),
        _dv("empty", [], []),
        _dv("failed", [], []),
        _dv("a", ["shared", "m1"], ["shared", "d1"]),
        _dv("blank_error", [], []),
        _dv("disjoint", [], ["d2"]),
    ]
    summaries[2].error = "API failure"
    summaries[4].error = ""  # Even an empty error string excludes the summary.
    original = deepcopy(summaries)
    calls = []
    getter = DataViewSummary.all_component_ids.fget

    def tracked_getter(summary):
        calls.append(summary.data_view_id)
        return getter(summary)

    monkeypatch.setattr(DataViewSummary, "all_component_ids", property(tracked_getter))
    analyzer = OrgComponentAnalyzer(MagicMock(), OrgReportConfig(), logging.getLogger("t"))
    valid, pairwise = analyzer._compute_pairwise_jaccard(summaries)

    assert calls == ["z", "empty", "a", "disjoint"]
    assert len(valid) == 3
    assert all(actual is expected for actual, expected in zip(valid, [summaries[0], summaries[3], summaries[5]]))
    assert list(pairwise.items()) == [((0, 1), 1.0), ((0, 2), 0.0), ((1, 2), 0.0)]
    assert summaries == original
    assert analyzer.cja.mock_calls == []


@pytest.mark.parametrize("size", [0, 1, 3, 40])
def test_pairwise_matches_direct_set_definition(size):
    summaries = [
        _dv(str(i), [f"m{j}" for j in range(i, i + 100)], [f"d{j}" for j in range(i, i + 50)]) for i in range(size)
    ]
    analyzer = OrgComponentAnalyzer(MagicMock(), OrgReportConfig(), logging.getLogger("t"))
    valid, pairwise = analyzer._compute_pairwise_jaccard(summaries)
    expected = {}
    for i, left in enumerate(summaries):
        for j in range(i + 1, size):
            right = summaries[j]
            left_ids = left.metric_ids | left.dimension_ids
            right_ids = right.metric_ids | right.dimension_ids
            expected[(i, j)] = len(left_ids & right_ids) / len(left_ids | right_ids)
    assert valid == summaries
    assert list(pairwise.items()) == list(expected.items())


def test_pairwise_observes_mutation_between_calls():
    summaries = [_dv("a", ["m1"], []), _dv("b", [], [])]
    analyzer = OrgComponentAnalyzer(MagicMock(), OrgReportConfig(), logging.getLogger("t"))
    assert analyzer._compute_pairwise_jaccard(summaries) == ([summaries[0]], {})
    summaries[1].dimension_ids.add("m1")
    assert analyzer._compute_pairwise_jaccard(summaries) == (summaries, {(0, 1): 1.0})
    summaries[0].metric_ids.add("m2")
    assert analyzer._compute_pairwise_jaccard(summaries) == (summaries, {(0, 1): 0.5})


@pytest.mark.parametrize("error", [None, "", "API failure"])
def test_pairwise_invalid_components_keep_failure_behavior(error):
    summary = _dv("invalid", [], [])
    summary.metric_ids = None
    summary.error = error
    analyzer = OrgComponentAnalyzer(MagicMock(), OrgReportConfig(), logging.getLogger("t"))
    if error is None:
        with pytest.raises(TypeError, match="unsupported operand type"):
            analyzer._compute_pairwise_jaccard([summary])
    else:
        assert analyzer._compute_pairwise_jaccard([summary]) == ([], {})
