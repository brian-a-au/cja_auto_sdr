"""Characterization tests for OrgComponentAnalyzer Jaccard similarity helpers.

Pins the current (pre-optimization) numeric output of ``_compute_pairwise_jaccard``
so that hoisting component-set unions out of the O(n^2) loops (perf task A1)
cannot change the computed values.
"""

import logging
from unittest.mock import MagicMock

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
