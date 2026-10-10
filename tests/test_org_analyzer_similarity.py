"""Characterization and regression tests for org pairwise Jaccard similarity."""

import logging
from copy import deepcopy
from unittest.mock import MagicMock, patch

import pytest

from cja_auto_sdr.org.analyzer import OrgComponentAnalyzer
from cja_auto_sdr.org.models import ComponentDistribution, DataViewSummary, OrgReportConfig


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


@pytest.mark.parametrize("threshold", [0, 0.5, 0.6667, 0.9, 0.95])
@pytest.mark.parametrize(("drift", "names"), [(False, False), (True, False), (True, True)])
def test_similarity_stream_matches_precomputed_output(threshold, drift, names):
    summaries = [
        _dv("z", ["shared", "a"], []),
        _dv("empty", [], []),
        _dv("failed", ["shared"], []),
        _dv("b", ["shared", "a", "b"], []),
        _dv("a", ["shared", "a"], []),
        _dv("disjoint", ["x"], []),
    ]
    summaries[2].error = ""
    for summary in summaries:
        summary.metric_names = {item: f"Name {item}" for item in summary.metric_ids}
    analyzer = OrgComponentAnalyzer(
        MagicMock(),
        OrgReportConfig(overlap_threshold=threshold, include_drift=drift, include_names=names),
        logging.getLogger("t"),
    )
    precomputed = analyzer._compute_pairwise_jaccard(summaries)
    expected = analyzer._compute_similarity_matrix(summaries, precomputed=precomputed)
    assert analyzer._compute_similarity_matrix(summaries) == expected
    if threshold == 0.6667:
        assert [(pair.dv1_id, pair.dv2_id) for pair in expected] == [("z", "a")]
    elif threshold == 0.5:
        assert [(pair.dv1_id, pair.dv2_id) for pair in expected] == [("z", "a"), ("z", "b"), ("b", "a")]


def test_similarity_only_does_not_materialize_rejected_distances(monkeypatch):
    analyzer = OrgComponentAnalyzer(MagicMock(), OrgReportConfig(), logging.getLogger("t"))
    summaries = [_dv(str(i), [f"unique_{i}"], []) for i in range(40)]

    def unexpected_materialization(*args, **kwargs):
        pytest.fail("similarity-only analysis retained the full pairwise dictionary")

    monkeypatch.setattr(analyzer, "_compute_pairwise_jaccard", unexpected_materialization)
    assert analyzer._compute_similarity_matrix(summaries) == []


@pytest.mark.parametrize("threshold", [0.9, 0.95, 1.0])
def test_similarity_governance_floor_filters_raw_scores(threshold):
    shared = {f"m{i}" for i in range(18000)}
    summaries = [
        _dv("base", shared, []),
        _dv("exact", shared | {f"extra{i}" for i in range(2000)}, []),
        _dv("below", (shared - {"m0"}) | {f"extra{i}" for i in range(2000)}, []),
    ]
    analyzer = OrgComponentAnalyzer(
        MagicMock(),
        OrgReportConfig(overlap_threshold=threshold, duplicate_threshold=0),
        logging.getLogger("t"),
    )
    pairs = analyzer._compute_similarity_matrix(summaries)
    expected = analyzer._compute_similarity_matrix(summaries, precomputed=analyzer._compute_pairwise_jaccard(summaries))
    assert pairs == expected
    assert ("base", "exact") in [(pair.dv1_id, pair.dv2_id) for pair in pairs]
    assert ("base", "below") not in [(pair.dv1_id, pair.dv2_id) for pair in pairs]
    assert round(17999 / 20000, 4) == 0.9  # Rounded eligibility would incorrectly include this pair.
    assert analyzer._check_governance_thresholds(
        pairs, ComponentDistribution(), 0
    ) == analyzer._check_governance_thresholds(expected, ComponentDistribution(), 0)


@pytest.mark.parametrize(
    ("options", "expect_similarity", "expect_clustering"),
    [
        ({}, True, False),
        ({"enable_clustering": True}, True, True),
        ({"skip_similarity": True}, False, False),
        ({"enable_clustering": True, "skip_similarity": True}, False, True),
        ({"org_stats_only": True, "enable_clustering": True}, False, False),
        ({"similarity_max_dvs": 1}, False, False),
        ({"similarity_max_dvs": 1, "enable_clustering": True}, False, True),
        ({"similarity_max_dvs": 1, "force_similarity": True}, True, False),
        ({"similarity_max_dvs": 1, "force_similarity": True, "enable_clustering": True}, True, True),
    ],
)
def test_run_analysis_similarity_dispatch(options, expect_similarity, expect_clustering):
    pytest.importorskip("scipy")
    summaries = [_dv("z", ["shared", "a"], []), _dv("b", ["shared", "a"], []), _dv("x", ["x"], [])]
    analyzer = OrgComponentAnalyzer(
        MagicMock(),
        OrgReportConfig(skip_lock=True, cja_per_thread=False, duplicate_threshold=0, **options),
        logging.getLogger("t"),
    )
    precomputed = analyzer._compute_pairwise_jaccard(summaries)
    expected_pairs = (
        analyzer._compute_similarity_matrix(summaries, precomputed=precomputed) if expect_similarity else None
    )
    expected_clusters = analyzer._compute_clusters(summaries, precomputed=precomputed) if expect_clustering else None
    with (
        patch.object(
            analyzer,
            "_list_and_filter_data_views",
            return_value=([{"id": s.data_view_id} for s in summaries], False, 3),
        ),
        patch.object(analyzer, "_fetch_all_data_views", return_value=summaries),
        patch.object(analyzer, "_compute_pairwise_jaccard", wraps=analyzer._compute_pairwise_jaccard) as materialize,
    ):
        result = analyzer._run_analysis_impl()
    assert materialize.call_count == int(expect_clustering)
    assert result.similarity_pairs == expected_pairs
    assert result.clusters == expected_clusters
    expected_recommendations = analyzer._generate_recommendations(
        summaries, result.component_index, result.distribution, expected_pairs
    )
    assert result.recommendations == expected_recommendations
    expected_violations, expected_exceeded = analyzer._check_governance_thresholds(
        expected_pairs, result.distribution, len(result.component_index)
    )
    assert result.governance_violations == expected_violations
    assert result.thresholds_exceeded == expected_exceeded


def test_similarity_order_is_stable_for_scores_that_round_to_a_tie():
    shared = {f"m{i}" for i in range(5000)}
    extra = {f"extra{i}" for i in range(5000)}
    summaries = [
        _dv("base", shared, []),
        _dv("lower", shared | extra | {"last"}, []),
        _dv("higher", shared | extra, []),
    ]
    analyzer = OrgComponentAnalyzer(MagicMock(), OrgReportConfig(overlap_threshold=0.49), logging.getLogger("t"))
    pairs = analyzer._compute_similarity_matrix(summaries)
    assert [(pair.dv1_id, pair.dv2_id, pair.jaccard_similarity) for pair in pairs] == [
        ("lower", "higher", 0.9999),
        ("base", "lower", 0.5),
        ("base", "higher", 0.5),
    ]
    assert pairs == analyzer._compute_similarity_matrix(
        summaries, precomputed=analyzer._compute_pairwise_jaccard(summaries)
    )
