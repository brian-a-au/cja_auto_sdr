"""
Edge-case tests for cja_auto_sdr.org.analyzer to boost coverage from ~75% to ~85%.

Targets untested branches in:
  _validate_regex_pattern, _list_and_filter_data_views, _stratified_sample,
  _check_memory_warning, _compute_distribution, _check_governance_thresholds,
  _audit_naming_conventions, _detect_stale_components.
"""

from __future__ import annotations

import logging
import re
from unittest.mock import Mock

import pandas as pd
import pytest

from cja_auto_sdr.core.exceptions import MemoryLimitExceeded
from cja_auto_sdr.org.analyzer import OrgComponentAnalyzer
from cja_auto_sdr.org.models import (
    ComponentDistribution,
    ComponentInfo,
    DataViewSummary,
    OrgReportConfig,
    SimilarityPair,
)


def _has_scipy() -> bool:
    try:
        import scipy  # noqa: F401

        return True
    except ImportError:
        return False


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def logger():
    return logging.getLogger("test_analyzer_coverage")


@pytest.fixture
def mock_cja():
    return Mock()


def _make_analyzer(
    mock_cja,
    logger,
    *,
    config: OrgReportConfig | None = None,
) -> OrgComponentAnalyzer:
    """Shorthand to create an analyzer with defaults suitable for unit tests."""
    cfg = config or OrgReportConfig(skip_lock=True, cja_per_thread=False)
    return OrgComponentAnalyzer(mock_cja, cfg, logger, org_id="unit@AdobeOrg")


def _make_component(
    comp_id: str,
    comp_type: str = "metric",
    name: str | None = None,
    data_views: set[str] | None = None,
) -> ComponentInfo:
    return ComponentInfo(
        component_id=comp_id,
        component_type=comp_type,
        name=name,
        data_views=data_views or {"dv1"},
    )


# ===================================================================
# 1. _validate_regex_pattern
# ===================================================================


class TestValidateRegexPattern:
    """Tests for _validate_regex_pattern ReDoS guard and compilation."""

    @pytest.mark.parametrize(
        "pattern",
        [
            r"(?:a+b+c+)+",  # nested +
            r"(?:x*y*z*)*",  # nested *
            r".*.*.*",  # multiple .* in sequence
            r".+.+.+",  # multiple .+ in sequence
        ],
        ids=["nested_plus", "nested_star", "triple_dotstar", "triple_dotplus"],
    )
    def test_dangerous_redos_patterns_rejected(self, pattern, mock_cja, logger):
        analyzer = _make_analyzer(mock_cja, logger)
        result = analyzer._validate_regex_pattern(pattern, "filter")
        assert result is None

    @pytest.mark.parametrize(
        "pattern",
        [
            r"[invalid",
            r"(?P<oops",
            r"*leading_quantifier",
        ],
        ids=["unclosed_bracket", "unclosed_group", "leading_quantifier"],
    )
    def test_invalid_regex_returns_none(self, pattern, mock_cja, logger):
        analyzer = _make_analyzer(mock_cja, logger)
        result = analyzer._validate_regex_pattern(pattern, "exclude")
        assert result is None

    @pytest.mark.parametrize(
        "pattern",
        [
            r"^prod_.*",
            r"DV\s+\d+",
            r"(?i)staging",
            r"analytics|reporting",
        ],
        ids=["anchored_prefix", "dv_number", "case_insensitive_group", "alternation"],
    )
    def test_valid_patterns_compile_successfully(self, pattern, mock_cja, logger):
        analyzer = _make_analyzer(mock_cja, logger)
        result = analyzer._validate_regex_pattern(pattern, "filter")
        assert isinstance(result, re.Pattern)

    def test_valid_pattern_is_case_insensitive(self, mock_cja, logger):
        analyzer = _make_analyzer(mock_cja, logger)
        compiled = analyzer._validate_regex_pattern("prod", "filter")
        assert compiled is not None
        assert compiled.search("Production") is not None


# ===================================================================
# 2. _list_and_filter_data_views
# ===================================================================


class TestListAndFilterDataViews:
    """Tests for _list_and_filter_data_views edge cases."""

    def test_sample_size_below_one_raises(self, mock_cja, logger):
        config = OrgReportConfig(sample_size=0, skip_lock=True, cja_per_thread=False)
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        with pytest.raises(ValueError, match="at least 1"):
            analyzer._list_and_filter_data_views()

    def test_sample_size_negative_raises(self, mock_cja, logger):
        config = OrgReportConfig(sample_size=-5, skip_lock=True, cja_per_thread=False)
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        with pytest.raises(ValueError, match="at least 1"):
            analyzer._list_and_filter_data_views()

    def test_api_failure_returns_empty(self, mock_cja, logger):
        mock_cja.getDataViews.side_effect = RuntimeError("network error")
        analyzer = _make_analyzer(mock_cja, logger)
        data_views, is_sampled, total = analyzer._list_and_filter_data_views()
        assert data_views == []
        assert is_sampled is False
        assert total == 0

    def test_dataframe_result_converted_to_list(self, mock_cja, logger):
        df = pd.DataFrame(
            [
                {"id": "dv1", "name": "Alpha"},
                {"id": "dv2", "name": "Beta"},
            ],
        )
        mock_cja.getDataViews.return_value = df
        analyzer = _make_analyzer(mock_cja, logger)
        data_views, _, total = analyzer._list_and_filter_data_views()
        assert isinstance(data_views, list)
        assert len(data_views) == 2
        assert total == 2

    def test_combined_filter_and_exclude(self, mock_cja, logger):
        dvs = [
            {"id": "dv1", "name": "Prod Analytics"},
            {"id": "dv2", "name": "Prod Test"},
            {"id": "dv3", "name": "Dev Analytics"},
        ]
        mock_cja.getDataViews.return_value = dvs
        config = OrgReportConfig(
            filter_pattern="Prod",
            exclude_pattern="Test",
            skip_lock=True,
            cja_per_thread=False,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        result, _, _total = analyzer._list_and_filter_data_views()
        assert len(result) == 1
        assert result[0]["name"] == "Prod Analytics"

    def test_none_return_treated_as_empty(self, mock_cja, logger):
        mock_cja.getDataViews.return_value = None
        analyzer = _make_analyzer(mock_cja, logger)
        data_views, _is_sampled, total = analyzer._list_and_filter_data_views()
        assert data_views == []
        assert total == 0

    def test_empty_list_return(self, mock_cja, logger):
        mock_cja.getDataViews.return_value = []
        analyzer = _make_analyzer(mock_cja, logger)
        data_views, _, total = analyzer._list_and_filter_data_views()
        assert data_views == []
        assert total == 0


# ===================================================================
# 3. _stratified_sample
# ===================================================================


class TestStratifiedSample:
    """Tests for _stratified_sample proportional allocation."""

    def _make_dvs(self, names: list[str]) -> list[dict]:
        return [{"id": f"dv_{i}", "name": n} for i, n in enumerate(names)]

    def test_proportional_allocation(self, mock_cja, logger):
        """Each prefix group should get proportional representation."""
        names = [f"GroupA Item {i}" for i in range(6)] + [f"GroupB Item {i}" for i in range(4)]
        dvs = self._make_dvs(names)
        config = OrgReportConfig(sample_size=5, sample_seed=42, skip_lock=True, cja_per_thread=False)
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        result = analyzer._stratified_sample(dvs, 5)
        assert len(result) == 5

    def test_over_sampling_trimmed(self, mock_cja, logger):
        """When many single-item groups exist, over-sampling is trimmed down."""
        # 10 unique prefixes, each with 1 item -- proportional = max(1, ...) = 1 each = 10
        names = [f"Prefix{i} Item" for i in range(10)]
        dvs = self._make_dvs(names)
        config = OrgReportConfig(sample_size=5, sample_seed=0, skip_lock=True, cja_per_thread=False)
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        result = analyzer._stratified_sample(dvs, 5)
        assert len(result) == 5

    def test_under_sampling_backfill(self, mock_cja, logger):
        """When proportional allocation yields fewer items, backfill kicks in."""
        # 2 groups with 50 items each -> proportional gives 2 * max(1, int(4*50/100))=2 each => 4
        # Needs to backfill 2 more to reach 6
        names = [f"Alpha Item {i}" for i in range(50)] + [f"Beta Item {i}" for i in range(50)]
        dvs = self._make_dvs(names)
        config = OrgReportConfig(sample_size=6, sample_seed=7, skip_lock=True, cja_per_thread=False)
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        result = analyzer._stratified_sample(dvs, 6)
        assert len(result) == 6

    def test_single_item_groups_all_included(self, mock_cja, logger):
        """Groups smaller than their proportional allocation are fully included."""
        names = ["Solo Item"] + [f"Big Group {i}" for i in range(9)]
        dvs = self._make_dvs(names)
        config = OrgReportConfig(sample_size=8, sample_seed=1, skip_lock=True, cja_per_thread=False)
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        result = analyzer._stratified_sample(dvs, 8)
        assert len(result) == 8
        # The solo item should always be included since its group has only 1 element
        solo_included = any(dv["name"] == "Solo Item" for dv in result)
        assert solo_included


# ===================================================================
# 4. _check_memory_warning
# ===================================================================


class TestCheckMemoryWarning:
    """Tests for _check_memory_warning thresholds and hard limit."""

    def _make_index(self, count: int = 5) -> dict[str, ComponentInfo]:
        return {f"c{i}": _make_component(f"c{i}", name=f"Component {i}") for i in range(count)}

    def test_below_threshold_no_warning(self, mock_cja, logger, caplog):
        config = OrgReportConfig(
            memory_warning_threshold_mb=100,
            memory_limit_mb=None,
            skip_lock=True,
            cja_per_thread=False,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        index = self._make_index(2)
        with caplog.at_level(logging.WARNING, logger="test_analyzer_coverage"):
            analyzer._check_memory_warning(index)
        assert "High memory usage" not in caplog.text

    def test_above_threshold_warning_logged(self, mock_cja, logger, caplog):
        config = OrgReportConfig(
            memory_warning_threshold_mb=1,  # very low threshold
            memory_limit_mb=None,
            skip_lock=True,
            cja_per_thread=False,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        index = self._make_index(5)
        # Fake the estimate to exceed threshold
        analyzer._estimate_component_index_memory = Mock(return_value=50.0)
        with caplog.at_level(logging.WARNING):
            analyzer._check_memory_warning(index)
        assert "High memory usage" in caplog.text

    def test_threshold_disabled_with_none(self, mock_cja, logger, caplog):
        config = OrgReportConfig(
            memory_warning_threshold_mb=None,
            memory_limit_mb=None,
            skip_lock=True,
            cja_per_thread=False,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        index = self._make_index(5)
        analyzer._estimate_component_index_memory = Mock(return_value=200.0)
        with caplog.at_level(logging.WARNING):
            analyzer._check_memory_warning(index)
        assert "High memory usage" not in caplog.text

    def test_threshold_disabled_with_zero(self, mock_cja, logger, caplog):
        config = OrgReportConfig(
            memory_warning_threshold_mb=0,
            memory_limit_mb=None,
            skip_lock=True,
            cja_per_thread=False,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        index = self._make_index(5)
        analyzer._estimate_component_index_memory = Mock(return_value=200.0)
        with caplog.at_level(logging.WARNING):
            analyzer._check_memory_warning(index)
        assert "High memory usage" not in caplog.text

    def test_hard_limit_exceeded_raises(self, mock_cja, logger):
        config = OrgReportConfig(
            memory_warning_threshold_mb=100,
            memory_limit_mb=10,
            skip_lock=True,
            cja_per_thread=False,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        index = self._make_index(5)
        analyzer._estimate_component_index_memory = Mock(return_value=50.0)
        with pytest.raises(MemoryLimitExceeded):
            analyzer._check_memory_warning(index)

    def test_hard_limit_none_does_not_raise(self, mock_cja, logger):
        config = OrgReportConfig(
            memory_warning_threshold_mb=100,
            memory_limit_mb=None,
            skip_lock=True,
            cja_per_thread=False,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        index = self._make_index(2)
        analyzer._estimate_component_index_memory = Mock(return_value=5.0)
        # Should not raise
        analyzer._check_memory_warning(index)

    def test_hard_limit_zero_does_not_raise(self, mock_cja, logger):
        """memory_limit_mb=0 should be treated as disabled."""
        config = OrgReportConfig(
            memory_warning_threshold_mb=100,
            memory_limit_mb=0,
            skip_lock=True,
            cja_per_thread=False,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        index = self._make_index(2)
        analyzer._estimate_component_index_memory = Mock(return_value=200.0)
        # Should not raise because limit is 0 (disabled)
        analyzer._check_memory_warning(index)


# ===================================================================
# 5. _compute_distribution
# ===================================================================


class TestComputeDistribution:
    """Tests for _compute_distribution bucket classification."""

    def test_zero_dvs_returns_empty(self, mock_cja, logger):
        analyzer = _make_analyzer(mock_cja, logger)
        index = {
            "m1": _make_component("m1", data_views={"dv1"}),
        }
        result = analyzer._compute_distribution(index, 0)
        assert isinstance(result, ComponentDistribution)
        assert result.total_core == 0
        assert result.total_isolated == 0

    def test_core_min_count_override(self, mock_cja, logger):
        config = OrgReportConfig(core_min_count=2, skip_lock=True, cja_per_thread=False)
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        index = {
            "m1": _make_component("m1", data_views={"dv1", "dv2", "dv3"}),
            "m2": _make_component("m2", data_views={"dv1"}),
        }
        result = analyzer._compute_distribution(index, 3)
        assert "m1" in result.core_metrics
        assert "m2" in result.isolated_metrics

    def test_core_min_count_one_does_not_misclassify_isolated(self, mock_cja, logger):
        """When core_min_count=1, everything should be core regardless of presence."""
        config = OrgReportConfig(core_min_count=1, skip_lock=True, cja_per_thread=False)
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        index = {
            "m1": _make_component("m1", data_views={"dv1"}),
            "d1": _make_component("d1", comp_type="dimension", data_views={"dv1"}),
        }
        result = analyzer._compute_distribution(index, 5)
        assert "m1" in result.core_metrics
        assert "d1" in result.core_dimensions
        assert result.total_isolated == 0

    def test_boundary_ceil_vs_floor(self, mock_cja, logger):
        """With 3 DVs and 50% threshold: ceil(1.5)=2, so 2+ is core, 1 is isolated."""
        config = OrgReportConfig(core_threshold=0.5, skip_lock=True, cja_per_thread=False)
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        index = {
            "core_m": _make_component("core_m", data_views={"dv1", "dv2"}),
            "iso_m": _make_component("iso_m", data_views={"dv1"}),
        }
        result = analyzer._compute_distribution(index, 3)
        assert "core_m" in result.core_metrics
        assert "iso_m" in result.isolated_metrics

    def test_isolated_equals_one_exactly(self, mock_cja, logger):
        """Component in exactly 1 DV should land in isolated bucket."""
        analyzer = _make_analyzer(mock_cja, logger)
        index = {
            "iso_d": _make_component("iso_d", comp_type="dimension", data_views={"dv1"}),
        }
        result = analyzer._compute_distribution(index, 10)
        assert "iso_d" in result.isolated_dimensions

    def test_limited_bucket_classification(self, mock_cja, logger):
        """Component in 2 DVs with 10 total DVs (< 25% = 3 for common) => limited."""
        analyzer = _make_analyzer(mock_cja, logger)
        index = {
            "lim_m": _make_component("lim_m", data_views={"dv1", "dv2"}),
        }
        result = analyzer._compute_distribution(index, 10)
        assert "lim_m" in result.limited_metrics

    def test_common_bucket_classification(self, mock_cja, logger):
        """Component in 3 DVs with 10 total DVs (25%=3 for common, core at 50%=5) => common."""
        analyzer = _make_analyzer(mock_cja, logger)
        index = {
            "com_d": _make_component("com_d", comp_type="dimension", data_views={"dv1", "dv2", "dv3"}),
        }
        result = analyzer._compute_distribution(index, 10)
        assert "com_d" in result.common_dimensions


# ===================================================================
# 6. _check_governance_thresholds
# ===================================================================


class TestCheckGovernanceThresholds:
    """Tests for _check_governance_thresholds violation detection."""

    def _sim_pair(self, similarity: float) -> SimilarityPair:
        return SimilarityPair(
            dv1_id="dv1",
            dv1_name="DV 1",
            dv2_id="dv2",
            dv2_name="DV 2",
            jaccard_similarity=similarity,
            shared_count=10,
            union_count=11,
        )

    def test_no_violations(self, mock_cja, logger):
        config = OrgReportConfig(
            duplicate_threshold=5,
            isolated_threshold=0.5,
            skip_lock=True,
            cja_per_thread=False,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        dist = ComponentDistribution()
        violations, exceeded = analyzer._check_governance_thresholds([], dist, 100)
        assert violations == []
        assert exceeded is False

    def test_duplicate_threshold_exceeded(self, mock_cja, logger):
        config = OrgReportConfig(
            duplicate_threshold=0,
            skip_lock=True,
            cja_per_thread=False,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        pairs = [self._sim_pair(0.95)]
        dist = ComponentDistribution()
        violations, exceeded = analyzer._check_governance_thresholds(pairs, dist, 10)
        assert exceeded is True
        assert any(v["type"] == "duplicate_threshold_exceeded" for v in violations)

    def test_isolated_threshold_exceeded(self, mock_cja, logger):
        config = OrgReportConfig(
            isolated_threshold=0.1,
            skip_lock=True,
            cja_per_thread=False,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        dist = ComponentDistribution(
            isolated_metrics=["m1", "m2", "m3"],
            isolated_dimensions=["d1", "d2"],
        )
        # 5 isolated / 10 total = 50% > 10%
        violations, exceeded = analyzer._check_governance_thresholds(None, dist, 10)
        assert exceeded is True
        assert any(v["type"] == "isolated_threshold_exceeded" for v in violations)

    def test_both_thresholds_exceeded(self, mock_cja, logger):
        config = OrgReportConfig(
            duplicate_threshold=0,
            isolated_threshold=0.1,
            skip_lock=True,
            cja_per_thread=False,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        pairs = [self._sim_pair(0.95)]
        dist = ComponentDistribution(isolated_metrics=["m1", "m2", "m3"])
        violations, exceeded = analyzer._check_governance_thresholds(pairs, dist, 5)
        assert exceeded is True
        types = [v["type"] for v in violations]
        assert "duplicate_threshold_exceeded" in types
        assert "isolated_threshold_exceeded" in types

    def test_no_similarity_pairs_passed(self, mock_cja, logger):
        """When similarity_pairs is None, duplicate check should be skipped gracefully."""
        config = OrgReportConfig(
            duplicate_threshold=0,
            isolated_threshold=None,
            skip_lock=True,
            cja_per_thread=False,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        dist = ComponentDistribution()
        violations, exceeded = analyzer._check_governance_thresholds(None, dist, 10)
        assert violations == []
        assert exceeded is False

    def test_isolated_threshold_not_exceeded(self, mock_cja, logger):
        config = OrgReportConfig(
            isolated_threshold=0.9,  # very permissive
            skip_lock=True,
            cja_per_thread=False,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        dist = ComponentDistribution(isolated_metrics=["m1"])
        _violations, exceeded = analyzer._check_governance_thresholds(None, dist, 100)
        assert exceeded is False


# ===================================================================
# 7. _audit_naming_conventions
# ===================================================================


class TestAuditNamingConventions:
    """Tests for _audit_naming_conventions detection logic."""

    def test_snake_case_detected(self, mock_cja, logger):
        analyzer = _make_analyzer(mock_cja, logger)
        index = {
            "my_metric": _make_component("my_metric", name="page_view_count"),
        }
        audit = analyzer._audit_naming_conventions(index)
        assert audit["case_styles"]["snake_case"] >= 1

    def test_camel_case_detected(self, mock_cja, logger):
        analyzer = _make_analyzer(mock_cja, logger)
        index = {
            "myMetric": _make_component("myMetric", name="pageViewCount"),
        }
        audit = analyzer._audit_naming_conventions(index)
        assert audit["case_styles"]["camelCase"] >= 1

    def test_pascal_case_detected(self, mock_cja, logger):
        analyzer = _make_analyzer(mock_cja, logger)
        index = {
            "MyMetric": _make_component("MyMetric", name="PageViewCount"),
        }
        audit = analyzer._audit_naming_conventions(index)
        assert audit["case_styles"]["PascalCase"] >= 1

    def test_stale_keyword_word_boundary(self, mock_cja, logger):
        """Stale keywords must match at word boundaries, not inside words."""
        analyzer = _make_analyzer(mock_cja, logger)
        index = {
            # Should match - stale keyword at word boundary
            "test_metric": _make_component("test_metric", name="test_metric"),
            # Should NOT match - 'test' is inside the word 'attestation'
            "attestation": _make_component("attestation", name="attestation"),
        }
        audit = analyzer._audit_naming_conventions(index)
        stale_ids = [s["component_id"] for s in audit["stale_patterns"]]
        assert "test_metric" in stale_ids
        assert "attestation" not in stale_ids

    def test_version_suffix_at_end_only(self, mock_cja, logger):
        """Version suffix _v1 should only match at end of string."""
        analyzer = _make_analyzer(mock_cja, logger)
        index = {
            "metric_v2": _make_component("metric_v2", name="metric_v2"),
            "v2_metric": _make_component("v2_metric", name="v2_metric"),
        }
        audit = analyzer._audit_naming_conventions(index)
        stale_ids = [s["component_id"] for s in audit["stale_patterns"]]
        assert "metric_v2" in stale_ids
        # v2_metric should NOT match the version suffix pattern (not at end)
        version_suffix_matches = [
            s for s in audit["stale_patterns"] if s["component_id"] == "v2_metric" and s["pattern"] == "version_suffix"
        ]
        assert len(version_suffix_matches) == 0

    def test_prefix_grouping(self, mock_cja, logger):
        analyzer = _make_analyzer(mock_cja, logger)
        index = {
            "evar/one": _make_component("evar/one", name="evar/one"),
            "evar/two": _make_component("evar/two", name="evar/two"),
            "prop_click": _make_component("prop_click", name="prop_click"),
        }
        audit = analyzer._audit_naming_conventions(index)
        assert "evar" in audit["prefix_groups"]
        assert audit["prefix_groups"]["evar"] == 2
        assert "prop" in audit["prefix_groups"]

    def test_naming_inconsistency_recommendation(self, mock_cja, logger):
        """When >5 non-dominant style components exist, a recommendation is generated."""
        analyzer = _make_analyzer(mock_cja, logger)
        index = {}
        # 10 snake_case
        for i in range(10):
            index[f"snake_{i}"] = _make_component(f"snake_{i}", name=f"page_view_{i}")
        # 6 camelCase (enough to trigger recommendation)
        for i in range(6):
            index[f"camel{i}"] = _make_component(f"camel{i}", name=f"pageView{chr(65 + i)}")
        audit = analyzer._audit_naming_conventions(index)
        rec_types = [r["type"] for r in audit["recommendations"]]
        assert "naming_inconsistency" in rec_types

    def test_stale_patterns_recommendation_generated(self, mock_cja, logger):
        analyzer = _make_analyzer(mock_cja, logger)
        index = {
            "old_metric": _make_component("old_metric", name="old_metric"),
        }
        audit = analyzer._audit_naming_conventions(index)
        rec_types = [r["type"] for r in audit["recommendations"]]
        assert "stale_naming_patterns" in rec_types

    def test_component_without_name_uses_id(self, mock_cja, logger):
        """When name is None, the component ID is used for analysis."""
        analyzer = _make_analyzer(mock_cja, logger)
        index = {
            "temp_data": _make_component("temp_data", name=None),
        }
        audit = analyzer._audit_naming_conventions(index)
        stale_ids = [s["component_id"] for s in audit["stale_patterns"]]
        assert "temp_data" in stale_ids

    def test_stale_pattern_data_views_are_sorted(self, mock_cja, logger):
        analyzer = _make_analyzer(mock_cja, logger)
        index = {
            "old_metric": _make_component(
                "old_metric",
                name="old_metric",
                data_views={"dv10", "dv2", "dv1"},
            ),
        }

        audit = analyzer._audit_naming_conventions(index)

        assert audit["stale_patterns"][0]["data_views"] == ["dv1", "dv10", "dv2"]


# ===================================================================
# 8. _detect_stale_components
# ===================================================================


class TestDetectStaleComponents:
    """Tests for _detect_stale_components heuristic matching."""

    @pytest.mark.parametrize(
        ("name", "expected_pattern"),
        [
            ("test_metric", "stale_keyword"),
            ("old_revenue", "stale_keyword"),
            ("temp_session", "stale_keyword"),
            ("tmp-count", "stale_keyword"),
            ("backup_data", "stale_keyword"),
            ("copy_of_metric", "stale_keyword"),
            ("deprecated_field", "stale_keyword"),
            ("legacy_evar", "stale_keyword"),
            ("archive-dim", "stale_keyword"),
            ("obsolete_prop", "stale_keyword"),
            ("unused_segment", "stale_keyword"),
        ],
        ids=[
            "test",
            "old",
            "temp",
            "tmp",
            "backup",
            "copy",
            "deprecated",
            "legacy",
            "archive",
            "obsolete",
            "unused",
        ],
    )
    def test_stale_keywords_detected(self, name, expected_pattern, mock_cja, logger):
        analyzer = _make_analyzer(mock_cja, logger)
        index = {name: _make_component(name, name=name)}
        result = analyzer._detect_stale_components(index)
        assert len(result) == 1
        assert result[0]["pattern"] == expected_pattern

    def test_version_suffix_detected(self, mock_cja, logger):
        analyzer = _make_analyzer(mock_cja, logger)
        index = {
            "metric_v3": _make_component("metric_v3", name="metric_v3"),
            "metric-V12": _make_component("metric-V12", name="metric-V12"),
        }
        result = analyzer._detect_stale_components(index)
        patterns = {r["component_id"]: r["pattern"] for r in result}
        assert patterns.get("metric_v3") == "version_suffix"
        assert patterns.get("metric-V12") == "version_suffix"

    def test_date_pattern_yyyymmdd(self, mock_cja, logger):
        analyzer = _make_analyzer(mock_cja, logger)
        index = {
            "metric_20240115": _make_component("metric_20240115", name="metric_20240115"),
        }
        result = analyzer._detect_stale_components(index)
        assert len(result) == 1
        assert result[0]["pattern"] == "date_pattern"

    def test_date_pattern_yyyy_mm_dd(self, mock_cja, logger):
        analyzer = _make_analyzer(mock_cja, logger)
        index = {
            "metric_2024-01-15": _make_component("metric_2024-01-15", name="metric_2024-01-15"),
        }
        result = analyzer._detect_stale_components(index)
        assert len(result) == 1
        assert result[0]["pattern"] == "date_pattern"

    def test_active_components_excluded(self, mock_cja, logger):
        """Normal component names should not be flagged."""
        analyzer = _make_analyzer(mock_cja, logger)
        index = {
            "page_views": _make_component("page_views", name="page_views"),
            "revenue_total": _make_component("revenue_total", name="revenue_total"),
            "conversion_rate": _make_component("conversion_rate", name="conversion_rate"),
        }
        result = analyzer._detect_stale_components(index)
        assert len(result) == 0

    def test_stale_component_includes_metadata(self, mock_cja, logger):
        """Stale entries should include component_id, name, type, pattern, presence_count, data_views."""
        analyzer = _make_analyzer(mock_cja, logger)
        index = {
            "old_field": _make_component(
                "old_field",
                comp_type="dimension",
                name="old_field",
                data_views={"dv1", "dv2"},
            ),
        }
        result = analyzer._detect_stale_components(index)
        assert len(result) == 1
        entry = result[0]
        assert entry["component_id"] == "old_field"
        assert entry["name"] == "old_field"
        assert entry["type"] == "dimension"
        assert entry["pattern"] == "stale_keyword"
        assert entry["presence_count"] == 2
        assert len(entry["data_views"]) <= 5

    def test_component_without_name_uses_id(self, mock_cja, logger):
        """When info.name is None, the component_id is used for detection."""
        analyzer = _make_analyzer(mock_cja, logger)
        index = {
            "temp_data": _make_component("temp_data", name=None),
        }
        result = analyzer._detect_stale_components(index)
        assert len(result) == 1
        assert result[0]["name"] == "temp_data"

    def test_data_views_capped_at_five(self, mock_cja, logger):
        """data_views list should be capped at 5 entries max."""
        analyzer = _make_analyzer(mock_cja, logger)
        many_dvs = {f"dv{i}" for i in range(10)}
        index = {
            "test_metric": _make_component("test_metric", name="test_metric", data_views=many_dvs),
        }
        result = analyzer._detect_stale_components(index)
        assert len(result) == 1
        assert len(result[0]["data_views"]) <= 5

    def test_stale_component_data_views_are_sorted_before_capping(self, mock_cja, logger):
        analyzer = _make_analyzer(mock_cja, logger)
        index = {
            "test_metric": _make_component(
                "test_metric",
                name="test_metric",
                data_views={"dv10", "dv2", "dv1", "dv3", "dv4", "dv5"},
            ),
        }

        result = analyzer._detect_stale_components(index)

        assert result[0]["data_views"] == ["dv1", "dv10", "dv2", "dv3", "dv4"]


# ===================================================================
# 9. _infer_cluster_name  (pure logic, 25 lines)
# ===================================================================


class TestInferClusterName:
    """Tests for _infer_cluster_name common-prefix inference."""

    def test_empty_list_returns_none(self, mock_cja, logger):
        analyzer = _make_analyzer(mock_cja, logger)
        assert analyzer._infer_cluster_name([]) is None

    def test_single_name_returns_itself(self, mock_cja, logger):
        analyzer = _make_analyzer(mock_cja, logger)
        assert analyzer._infer_cluster_name(["analytics"]) == "analytics"

    def test_common_prefix_extracted(self, mock_cja, logger):
        analyzer = _make_analyzer(mock_cja, logger)
        result = analyzer._infer_cluster_name(["prod_view_1", "prod_view_2"])
        assert result == "prod_view"

    def test_common_prefix_with_separator_stripped(self, mock_cja, logger):
        analyzer = _make_analyzer(mock_cja, logger)
        result = analyzer._infer_cluster_name(["prod-alpha", "prod-beta"])
        assert result == "prod"

    def test_no_common_prefix_falls_back_to_first_word(self, mock_cja, logger):
        """When no prefix >= 3 chars, try first-word match."""
        analyzer = _make_analyzer(mock_cja, logger)
        result = analyzer._infer_cluster_name(["Analytics Alpha", "Analytics Beta"])
        assert result == "Analytics"

    def test_no_common_prefix_no_first_word_match_returns_none(self, mock_cja, logger):
        analyzer = _make_analyzer(mock_cja, logger)
        result = analyzer._infer_cluster_name(["prod_a", "staging_b"])
        assert result is None

    def test_short_prefix_ignored(self, mock_cja, logger):
        """Common prefix shorter than 3 chars should not be returned directly."""
        analyzer = _make_analyzer(mock_cja, logger)
        result = analyzer._infer_cluster_name(["ab_one", "ac_two"])
        # Common prefix is "a" (len 1) -> falls to first word check, first words differ
        assert result is None

    def test_prefix_trailing_separators_stripped(self, mock_cja, logger):
        analyzer = _make_analyzer(mock_cja, logger)
        result = analyzer._infer_cluster_name(["reporting_east_1", "reporting_west_2"])
        # Common prefix is "reporting_" -> stripped to "reporting"
        assert result == "reporting"


# ===================================================================
# 10. Feature flag paths in _run_analysis_impl
# ===================================================================


class TestRunAnalysisImplFeatureFlags:
    """Tests for feature flag branches in _run_analysis_impl."""

    def _setup_analyzer_with_data(self, mock_cja, logger, **config_kwargs):
        """Create an analyzer whose _list_and_filter_data_views returns 2 DVs."""
        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, **config_kwargs)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        # Stub the heavy methods so we don't need real API calls
        summaries = [
            DataViewSummary(
                data_view_id="dv1",
                data_view_name="DV 1",
                metric_ids={"m1", "m2"},
                dimension_ids={"d1"},
                metric_count=2,
                dimension_count=1,
            ),
            DataViewSummary(
                data_view_id="dv2",
                data_view_name="DV 2",
                metric_ids={"m1", "m3"},
                dimension_ids={"d1", "d2"},
                metric_count=2,
                dimension_count=2,
            ),
        ]

        from unittest.mock import patch

        patches = [
            patch.object(
                analyzer,
                "_list_and_filter_data_views",
                return_value=([{"id": "dv1"}, {"id": "dv2"}], False, 2),
            ),
            patch.object(analyzer, "_fetch_all_data_views", return_value=summaries),
            patch.object(analyzer, "_check_memory_warning"),
        ]
        return analyzer, patches

    def test_audit_naming_flag_triggers_audit(self, mock_cja, logger):
        """audit_naming=True should call _audit_naming_conventions."""
        analyzer, patches = self._setup_analyzer_with_data(mock_cja, logger, audit_naming=True, skip_similarity=True)
        with patches[0], patches[1], patches[2]:
            result = analyzer.run_analysis()
        assert result.naming_audit is not None

    def test_flag_stale_triggers_stale_detection(self, mock_cja, logger):
        """flag_stale=True should populate stale_components."""
        analyzer, patches = self._setup_analyzer_with_data(mock_cja, logger, flag_stale=True, skip_similarity=True)
        with patches[0], patches[1], patches[2]:
            result = analyzer.run_analysis()
        # stale_components should be a list (possibly empty since component names are generic)
        assert result.stale_components is not None
        assert isinstance(result.stale_components, list)
        # naming_audit should also be populated because flag_stale triggers it too
        assert result.naming_audit is not None

    def test_owner_summary_without_metadata_warns(self, mock_cja, logger, caplog):
        """include_owner_summary=True without include_metadata=True should log warning."""
        analyzer, patches = self._setup_analyzer_with_data(
            mock_cja,
            logger,
            include_owner_summary=True,
            include_metadata=False,
            skip_similarity=True,
        )
        with patches[0], patches[1], patches[2], caplog.at_level(logging.WARNING):
            result = analyzer.run_analysis()
        assert result.owner_summary is None
        assert "--owner-summary requires --include-metadata" in caplog.text

    def test_owner_summary_with_metadata_populates(self, mock_cja, logger):
        """include_owner_summary=True with include_metadata=True should populate owner_summary."""
        analyzer, patches = self._setup_analyzer_with_data(
            mock_cja,
            logger,
            include_owner_summary=True,
            include_metadata=True,
            skip_similarity=True,
        )
        with patches[0], patches[1], patches[2]:
            result = analyzer.run_analysis()
        assert result.owner_summary is not None
        assert "by_owner" in result.owner_summary


# ===================================================================
# 11. _generate_recommendations branches
# ===================================================================


class TestGenerateRecommendations:
    """Tests for uncovered branches in _generate_recommendations."""

    def _make_summaries(self, count=5, include_error=False, **kwargs):
        """Create test summaries."""
        summaries = []
        for i in range(count):
            s = DataViewSummary(
                data_view_id=f"dv{i}",
                data_view_name=f"Data View {i}",
                metric_ids={f"m{i}"},
                dimension_ids={f"d{i}"},
                metric_count=1,
                dimension_count=1,
                **kwargs,
            )
            summaries.append(s)
        if include_error:
            summaries.append(DataViewSummary(data_view_id="dverr", data_view_name="Error DV", error="API failure"))
        return summaries

    def test_near_core_standardization_recommendation(self, mock_cja, logger):
        """Components in 70-99% of DVs should trigger standardization_opportunity."""
        config = OrgReportConfig(skip_lock=True, cja_per_thread=False)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        # 10 summaries - need >5 components in 70-99% of DVs
        summaries = self._make_summaries(10)
        # Build index with 6 components each in 8 out of 10 DVs (80%)
        index = {}
        for i in range(6):
            dvs = {f"dv{j}" for j in range(8)}
            index[f"near_core_{i}"] = _make_component(f"near_core_{i}", data_views=dvs)

        dist = ComponentDistribution()
        result = analyzer._generate_recommendations(summaries, index, dist, None)
        types = [r["type"] for r in result]
        assert "standardization_opportunity" in types

    def test_high_derived_ratio_recommendation(self, mock_cja, logger):
        """DV with >50% derived components should trigger high_derived_ratio."""
        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, include_component_types=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        summaries = [
            DataViewSummary(
                data_view_id="dv1",
                data_view_name="Heavy Derived DV",
                metric_ids={"m1", "m2"},
                dimension_ids={"d1"},
                metric_count=2,
                dimension_count=1,
                derived_metric_count=2,
                derived_dimension_count=1,
            ),
        ]
        index = {}
        dist = ComponentDistribution()
        result = analyzer._generate_recommendations(summaries, index, dist, None)
        types = [r["type"] for r in result]
        assert "high_derived_ratio" in types
        rec = next(r for r in result if r["type"] == "high_derived_ratio")
        assert rec["ratio"] == 1.0

    def test_stale_data_view_recommendation(self, mock_cja, logger):
        """DV modified >180 days ago should trigger stale_data_view."""
        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, include_metadata=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        old_date = "2024-01-01T00:00:00+00:00"
        summaries = [
            DataViewSummary(
                data_view_id="dv_old",
                data_view_name="Old DV",
                metric_ids={"m1"},
                dimension_ids={"d1"},
                metric_count=1,
                dimension_count=1,
                modified=old_date,
                has_description=True,
            ),
        ]
        index = {}
        dist = ComponentDistribution()
        result = analyzer._generate_recommendations(summaries, index, dist, None)
        types = [r["type"] for r in result]
        assert "stale_data_view" in types

    def test_stale_data_view_bad_date_exception_handled(self, mock_cja, logger):
        """Bad modified date string should not crash recommendations."""
        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, include_metadata=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        summaries = [
            DataViewSummary(
                data_view_id="dv_bad",
                data_view_name="Bad Date DV",
                metric_ids={"m1"},
                dimension_ids=set(),
                metric_count=1,
                dimension_count=0,
                modified="not-a-date",
                has_description=True,
            ),
        ]
        index = {}
        dist = ComponentDistribution()
        # Should not raise
        result = analyzer._generate_recommendations(summaries, index, dist, None)
        # No stale_data_view because the date is invalid
        types = [r["type"] for r in result]
        assert "stale_data_view" not in types

    def test_stale_data_view_naive_datetime_handled(self, mock_cja, logger):
        """Modified date without timezone should still be handled (tzinfo=None)."""
        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, include_metadata=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        # Naive datetime (no TZ info) in the far past
        old_date = "2023-06-01T00:00:00"
        summaries = [
            DataViewSummary(
                data_view_id="dv_naive",
                data_view_name="Naive TZ DV",
                metric_ids={"m1"},
                dimension_ids=set(),
                metric_count=1,
                dimension_count=0,
                modified=old_date,
                has_description=True,
            ),
        ]
        index = {}
        dist = ComponentDistribution()
        result = analyzer._generate_recommendations(summaries, index, dist, None)
        types = [r["type"] for r in result]
        assert "stale_data_view" in types

    def test_drift_injection_into_overlap_recommendations(self, mock_cja, logger):
        """With include_drift, high-similarity pairs should have drift_count added."""
        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, include_drift=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        sim_pairs = [
            SimilarityPair(
                dv1_id="dv1",
                dv1_name="DV 1",
                dv2_id="dv2",
                dv2_name="DV 2",
                jaccard_similarity=0.95,
                shared_count=95,
                union_count=100,
                only_in_dv1=["extra_1", "extra_2"],
                only_in_dv2=["extra_3"],
            ),
        ]

        summaries = self._make_summaries(2)
        index = {}
        dist = ComponentDistribution()
        result = analyzer._generate_recommendations(summaries, index, dist, sim_pairs)

        overlap_recs = [r for r in result if r["type"] == "review_overlap"]
        assert len(overlap_recs) == 1
        assert overlap_recs[0]["drift_count"] == 3
        assert "Differs by 3 components" in overlap_recs[0]["reason"]

    def test_missing_descriptions_recommendation(self, mock_cja, logger):
        """When >=30% of DVs lack descriptions, missing_descriptions should be recommended."""
        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, include_metadata=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        summaries = [
            DataViewSummary(
                data_view_id=f"dv{i}",
                data_view_name=f"DV {i}",
                metric_ids={f"m{i}"},
                dimension_ids=set(),
                metric_count=1,
                dimension_count=0,
                has_description=False,
            )
            for i in range(5)
        ]
        index = {}
        dist = ComponentDistribution()
        result = analyzer._generate_recommendations(summaries, index, dist, None)
        types = [r["type"] for r in result]
        assert "missing_descriptions" in types

    def test_fetch_errors_recommendation(self, mock_cja, logger):
        """Summaries with errors should trigger fetch_errors recommendation."""
        config = OrgReportConfig(skip_lock=True, cja_per_thread=False)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        summaries = self._make_summaries(3, include_error=True)
        index = {}
        dist = ComponentDistribution()
        result = analyzer._generate_recommendations(summaries, index, dist, None)
        types = [r["type"] for r in result]
        assert "fetch_errors" in types

    def test_empty_error_string_is_treated_as_failure_everywhere(self, mock_cja, logger):
        """Blank error text should still count as failure and be excluded from success-only checks."""
        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, include_component_types=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        summaries = [
            DataViewSummary(
                data_view_id="dv_ok",
                data_view_name="Healthy DV",
                metric_ids={"m1"},
                dimension_ids={"d1"},
                metric_count=1,
                dimension_count=1,
                derived_metric_count=0,
                derived_dimension_count=0,
            ),
            DataViewSummary(
                data_view_id="dv_err_blank",
                data_view_name="Blank Error DV",
                metric_ids={"m_bad_1", "m_bad_2"},
                dimension_ids={"d_bad_1"},
                metric_count=2,
                dimension_count=1,
                derived_metric_count=2,
                derived_dimension_count=1,
                error="",
            ),
        ]

        index = analyzer._build_component_index(summaries)
        assert "m_bad_1" not in index
        assert "d_bad_1" not in index

        recommendations = analyzer._generate_recommendations(summaries, index, ComponentDistribution(), None)
        fetch_error_rec = next(rec for rec in recommendations if rec["type"] == "fetch_errors")
        assert fetch_error_rec["count"] == 1
        assert all(
            not (rec["type"] == "high_derived_ratio" and rec.get("data_view") == "dv_err_blank")
            for rec in recommendations
        )


# ===================================================================
# 12. Exception handlers
# ===================================================================


class TestExceptionHandlers:
    """Tests for exception-handling paths."""

    def test_cancel_futures_best_effort_with_failing_futures(self, mock_cja, logger):
        """_cancel_futures_best_effort should not raise when cancel() throws."""
        from unittest.mock import MagicMock

        analyzer = _make_analyzer(mock_cja, logger)

        f1 = MagicMock()
        f1.cancel.side_effect = RuntimeError("cancel failed")
        f2 = MagicMock()
        f2.cancel.return_value = True
        f3 = MagicMock()
        f3.cancel.side_effect = OSError("os error")

        # Should not raise
        analyzer._cancel_futures_best_effort({f1: {}, f2: {}, f3: {}})
        f1.cancel.assert_called_once()
        f2.cancel.assert_called_once()
        f3.cancel.assert_called_once()

    def test_quick_check_empty_org_exception_path(self, mock_cja, logger, caplog):
        """_quick_check_empty_org should return None when API raises."""
        mock_cja.getDataViews.side_effect = ConnectionError("network down")
        analyzer = _make_analyzer(mock_cja, logger)
        with caplog.at_level(logging.DEBUG):
            result = analyzer._quick_check_empty_org()
        assert result is None
        assert "Quick empty-org check skipped" in caplog.text

    def test_quick_check_empty_org_returns_result_when_empty(self, mock_cja, logger):
        """_quick_check_empty_org should return OrgReportResult when no DVs."""
        mock_cja.getDataViews.return_value = []
        analyzer = _make_analyzer(mock_cja, logger)
        result = analyzer._quick_check_empty_org()
        assert result is not None
        assert result.data_view_summaries == []
        assert result.total_available_data_views == 0

    def test_quick_check_empty_org_returns_none_when_dvs_exist(self, mock_cja, logger):
        """_quick_check_empty_org returns None when data views exist."""
        mock_cja.getDataViews.return_value = [{"id": "dv1", "name": "DV 1"}]
        analyzer = _make_analyzer(mock_cja, logger)
        result = analyzer._quick_check_empty_org()
        assert result is None


# ===================================================================
# 13. Cache paths
# ===================================================================


class TestCachePaths:
    """Tests for cache hit/miss and validation paths."""

    def test_cache_hit_returns_cached_summary(self, mock_cja, logger):
        """When cache has a valid entry, it should be returned without fetching."""
        from unittest.mock import MagicMock

        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, use_cache=True, validate_cache=False)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        cached_summary = DataViewSummary(
            data_view_id="dv1",
            data_view_name="Cached DV",
            metric_count=5,
            dimension_count=3,
        )
        mock_cache = MagicMock()
        mock_cache.get.return_value = cached_summary
        analyzer.cache = mock_cache

        data_views = [{"id": "dv1", "name": "Cached DV"}]

        # Patch thread pool to avoid actual API calls for uncached items
        result = analyzer._fetch_all_data_views(data_views)
        assert len(result) == 1
        assert result[0].data_view_name == "Cached DV"
        mock_cache.get.assert_called_once()

    def test_cache_miss_triggers_fetch(self, mock_cja, logger):
        """When cache returns None, the DV should be fetched from API."""
        from unittest.mock import MagicMock

        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, use_cache=True, validate_cache=False, quiet=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        analyzer.cache = mock_cache

        # Mock the CJA API to return data for the fetch
        mock_cja.getMetrics.return_value = pd.DataFrame({"id": ["m1"], "name": ["Metric 1"]})
        mock_cja.getDimensions.return_value = pd.DataFrame({"id": ["d1"], "name": ["Dim 1"]})

        data_views = [{"id": "dv1", "name": "Uncached DV"}]
        result = analyzer._fetch_all_data_views(data_views)
        assert len(result) == 1
        assert result[0].metric_count == 1
        mock_cache.get.assert_called_once()

    def test_validate_cache_entries_no_cache(self, mock_cja, logger):
        """_validate_cache_entries with no cache returns all DVs to fetch."""
        config = OrgReportConfig(skip_lock=True, cja_per_thread=False)
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        analyzer.cache = None

        dvs = [{"id": "dv1"}, {"id": "dv2"}]
        to_fetch, valid, valid_count, stale_count = analyzer._validate_cache_entries(dvs)
        assert to_fetch == dvs
        assert valid == []
        assert valid_count == 0
        assert stale_count == 0

    def test_validate_cache_entries_no_modification_date(self, mock_cja, logger):
        """DVs without modification date should be treated as stale."""
        from unittest.mock import MagicMock

        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, use_cache=True, validate_cache=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        mock_cache = MagicMock()
        mock_cache.has_valid_entry.return_value = True
        analyzer.cache = mock_cache

        dvs = [{"id": "dv1", "name": "No Modified"}]  # no 'modified' key
        to_fetch, _valid, valid_count, stale_count = analyzer._validate_cache_entries(dvs)
        assert len(to_fetch) == 1
        assert stale_count == 1
        assert valid_count == 0

    def test_validate_cache_entries_valid_hit(self, mock_cja, logger):
        """DVs with valid cache entry and matching modification date should be a cache hit."""
        from unittest.mock import MagicMock

        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, use_cache=True, validate_cache=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        cached_summary = DataViewSummary(data_view_id="dv1", data_view_name="Cached DV")
        mock_cache = MagicMock()
        mock_cache.has_valid_entry.return_value = True
        mock_cache.get.return_value = cached_summary
        analyzer.cache = mock_cache

        dvs = [{"id": "dv1", "name": "Cached DV", "modified": "2025-01-01T00:00:00Z"}]
        to_fetch, valid, valid_count, stale_count = analyzer._validate_cache_entries(dvs)
        assert len(to_fetch) == 0
        assert len(valid) == 1
        assert valid_count == 1
        assert stale_count == 0

    def test_validate_cache_entries_stale_hit(self, mock_cja, logger):
        """DVs with expired cache (get returns None) should be counted as stale."""
        from unittest.mock import MagicMock

        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, use_cache=True, validate_cache=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        mock_cache = MagicMock()
        mock_cache.has_valid_entry.return_value = True
        mock_cache.get.return_value = None  # stale
        analyzer.cache = mock_cache

        dvs = [{"id": "dv1", "name": "Stale DV", "modified": "2025-06-01T00:00:00Z"}]
        to_fetch, _valid, valid_count, stale_count = analyzer._validate_cache_entries(dvs)
        assert len(to_fetch) == 1
        assert valid_count == 0
        assert stale_count == 1

    def test_validate_cache_entries_no_valid_entry(self, mock_cja, logger):
        """DVs without any valid cache entry should go straight to fetch."""
        from unittest.mock import MagicMock

        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, use_cache=True, validate_cache=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        mock_cache = MagicMock()
        mock_cache.has_valid_entry.return_value = False
        analyzer.cache = mock_cache

        dvs = [{"id": "dv1", "name": "No Cache"}]
        to_fetch, _valid, valid_count, stale_count = analyzer._validate_cache_entries(dvs)
        assert len(to_fetch) == 1
        assert valid_count == 0
        assert stale_count == 0

    def test_empty_to_fetch_returns_cached_only(self, mock_cja, logger):
        """When all DVs are cached, _fetch_all_data_views returns only cached summaries."""
        from unittest.mock import MagicMock

        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, use_cache=True, validate_cache=False)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        cached1 = DataViewSummary(data_view_id="dv1", data_view_name="Cached 1")
        cached2 = DataViewSummary(data_view_id="dv2", data_view_name="Cached 2")
        mock_cache = MagicMock()
        mock_cache.get.side_effect = [cached1, cached2]
        analyzer.cache = mock_cache

        data_views = [{"id": "dv1", "name": "DV1"}, {"id": "dv2", "name": "DV2"}]
        result = analyzer._fetch_all_data_views(data_views)
        assert len(result) == 2
        # No API calls should have been made
        mock_cja.getMetrics.assert_not_called()


# ===================================================================
# 14. Drift computation in similarity matrix
# ===================================================================


class TestDriftComputation:
    """Tests for include_drift=True in _compute_similarity_matrix."""

    def test_drift_populates_only_in_dv1_dv2(self, mock_cja, logger):
        """With include_drift=True, only_in_dv1 and only_in_dv2 should be populated."""
        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, include_drift=True, overlap_threshold=0.5)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        summaries = [
            DataViewSummary(
                data_view_id="dv1",
                data_view_name="DV 1",
                metric_ids={"m1", "m2", "m3"},
                dimension_ids={"d1"},
                metric_count=3,
                dimension_count=1,
            ),
            DataViewSummary(
                data_view_id="dv2",
                data_view_name="DV 2",
                metric_ids={"m1", "m2", "m4"},
                dimension_ids={"d1"},
                metric_count=3,
                dimension_count=1,
            ),
        ]
        pairs = analyzer._compute_similarity_matrix(summaries)
        assert len(pairs) >= 1
        pair = pairs[0]
        assert "m3" in pair.only_in_dv1
        assert "m4" in pair.only_in_dv2
        assert "m1" not in pair.only_in_dv1
        assert "m1" not in pair.only_in_dv2

    def test_drift_without_names(self, mock_cja, logger):
        """With include_drift=True but include_names=False, name dicts should be None."""
        config = OrgReportConfig(
            skip_lock=True,
            cja_per_thread=False,
            include_drift=True,
            include_names=False,
            overlap_threshold=0.1,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        # Jaccard = 5/7 = 0.714 (above 0.1 threshold)
        summaries = [
            DataViewSummary(
                data_view_id="dv1",
                data_view_name="DV 1",
                metric_ids={"m1", "m2", "m3", "m4", "m5", "m_only1"},
                dimension_ids=set(),
                metric_count=6,
                dimension_count=0,
            ),
            DataViewSummary(
                data_view_id="dv2",
                data_view_name="DV 2",
                metric_ids={"m1", "m2", "m3", "m4", "m5", "m_only2"},
                dimension_ids=set(),
                metric_count=6,
                dimension_count=0,
            ),
        ]
        pairs = analyzer._compute_similarity_matrix(summaries)
        assert len(pairs) >= 1
        pair = pairs[0]
        assert pair.only_in_dv1_names is None
        assert pair.only_in_dv2_names is None

    def test_drift_with_names(self, mock_cja, logger):
        """With include_drift=True and include_names=True, name dicts should be populated."""
        config = OrgReportConfig(
            skip_lock=True,
            cja_per_thread=False,
            include_drift=True,
            include_names=True,
            overlap_threshold=0.1,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        # Jaccard = 5/7 = 0.714 (above 0.1 threshold)
        summaries = [
            DataViewSummary(
                data_view_id="dv1",
                data_view_name="DV 1",
                metric_ids={"m1", "m2", "m3", "m4", "m5", "m_only1"},
                dimension_ids=set(),
                metric_count=6,
                dimension_count=0,
                metric_names={
                    "m1": "Shared 1",
                    "m2": "Shared 2",
                    "m3": "Shared 3",
                    "m4": "Shared 4",
                    "m5": "Shared 5",
                    "m_only1": "Only In DV1",
                },
            ),
            DataViewSummary(
                data_view_id="dv2",
                data_view_name="DV 2",
                metric_ids={"m1", "m2", "m3", "m4", "m5", "m_only2"},
                dimension_ids=set(),
                metric_count=6,
                dimension_count=0,
                metric_names={
                    "m1": "Shared 1",
                    "m2": "Shared 2",
                    "m3": "Shared 3",
                    "m4": "Shared 4",
                    "m5": "Shared 5",
                    "m_only2": "Only In DV2",
                },
            ),
        ]
        pairs = analyzer._compute_similarity_matrix(summaries)
        assert len(pairs) >= 1
        pair = pairs[0]
        assert pair.only_in_dv1_names is not None
        assert pair.only_in_dv2_names is not None
        assert pair.only_in_dv1_names.get("m_only1") == "Only In DV1"
        assert pair.only_in_dv2_names.get("m_only2") == "Only In DV2"


# ===================================================================
# 15. Owner summary
# ===================================================================


class TestComputeOwnerSummary:
    """Tests for _compute_owner_summary computation."""

    def test_owner_none_defaults_to_unknown(self, mock_cja, logger):
        """Summaries with owner=None should be grouped under 'Unknown'."""
        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, include_metadata=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        summaries = [
            DataViewSummary(
                data_view_id="dv1",
                data_view_name="DV 1",
                metric_ids={"m1"},
                dimension_ids=set(),
                metric_count=1,
                dimension_count=0,
                owner=None,
                owner_id=None,
            ),
        ]
        result = analyzer._compute_owner_summary(summaries)
        assert "Unknown" in result["by_owner"]
        assert result["by_owner"]["Unknown"]["data_view_count"] == 1

    def test_owner_summary_groups_by_owner(self, mock_cja, logger):
        """Multiple DVs from same owner should be grouped together."""
        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, include_metadata=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        summaries = [
            DataViewSummary(
                data_view_id="dv1",
                data_view_name="DV 1",
                metric_ids={"m1"},
                dimension_ids={"d1"},
                metric_count=1,
                dimension_count=1,
                owner="Alice",
                owner_id="alice123",
            ),
            DataViewSummary(
                data_view_id="dv2",
                data_view_name="DV 2",
                metric_ids={"m1", "m2"},
                dimension_ids=set(),
                metric_count=2,
                dimension_count=0,
                owner="Alice",
                owner_id="alice123",
            ),
            DataViewSummary(
                data_view_id="dv3",
                data_view_name="DV 3",
                metric_ids={"m3"},
                dimension_ids=set(),
                metric_count=1,
                dimension_count=0,
                owner="Bob",
                owner_id="bob456",
            ),
        ]
        result = analyzer._compute_owner_summary(summaries)
        assert result["total_owners"] == 2
        assert result["by_owner"]["Alice"]["data_view_count"] == 2
        assert result["by_owner"]["Alice"]["total_metrics"] == 3
        assert result["by_owner"]["Bob"]["data_view_count"] == 1
        # Check averages
        assert result["by_owner"]["Alice"]["avg_metrics_per_dv"] == 1.5

    def test_owner_summary_skips_error_summaries(self, mock_cja, logger):
        """Summaries with errors should be excluded from owner summary."""
        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, include_metadata=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        summaries = [
            DataViewSummary(
                data_view_id="dv1",
                data_view_name="DV 1",
                metric_count=1,
                dimension_count=0,
                owner="Alice",
            ),
            DataViewSummary(
                data_view_id="dv2",
                data_view_name="Error DV",
                error="API failure",
                owner="Alice",
            ),
        ]
        result = analyzer._compute_owner_summary(summaries)
        assert result["by_owner"]["Alice"]["data_view_count"] == 1

    def test_owner_summary_skips_empty_error_string_summaries(self, mock_cja, logger):
        """Legacy blank error messages should still be treated as failed summaries."""
        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, include_metadata=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        summaries = [
            DataViewSummary(
                data_view_id="dv1",
                data_view_name="DV 1",
                metric_count=1,
                dimension_count=0,
                owner="Alice",
            ),
            DataViewSummary(
                data_view_id="dv2",
                data_view_name="Blank Error DV",
                error="",
                owner="Alice",
            ),
        ]

        result = analyzer._compute_owner_summary(summaries)
        assert result["by_owner"]["Alice"]["data_view_count"] == 1

    def test_owner_summary_sorted_by_dv_count(self, mock_cja, logger):
        """owners_sorted_by_dv_count should be sorted descending."""
        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, include_metadata=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        summaries = [
            DataViewSummary(data_view_id=f"dv{i}", data_view_name=f"DV {i}", owner="Alice") for i in range(3)
        ] + [
            DataViewSummary(data_view_id="dv_bob", data_view_name="Bob DV", owner="Bob"),
        ]
        result = analyzer._compute_owner_summary(summaries)
        sorted_owners = result["owners_sorted_by_dv_count"]
        assert sorted_owners[0] == "Alice"
        assert sorted_owners[1] == "Bob"


# ===================================================================
# 16. Clustering (requires scipy — skip if unavailable)
# ===================================================================


class TestComputeClusters:
    """Tests for _compute_clusters hierarchical clustering."""

    def test_scipy_import_error_returns_none(self, mock_cja, logger, caplog):
        """When scipy is not importable, _compute_clusters should return None."""
        from unittest.mock import patch

        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, enable_clustering=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        summaries = [
            DataViewSummary(data_view_id="dv1", data_view_name="DV 1", metric_ids={"m1"}, dimension_ids=set()),
        ]

        with patch("builtins.__import__", side_effect=_make_scipy_import_error()):
            with caplog.at_level(logging.WARNING):
                result = analyzer._compute_clusters(summaries)
        assert result is None
        assert "scipy not available" in caplog.text

    def test_too_few_data_views_returns_none(self, mock_cja, logger, caplog):
        """With fewer than 2 valid DVs, clustering should return None."""
        scipy = pytest.importorskip("scipy")  # noqa: F841

        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, enable_clustering=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        summaries = [
            DataViewSummary(
                data_view_id="dv1",
                data_view_name="DV 1",
                metric_ids={"m1"},
                dimension_ids=set(),
                metric_count=1,
            ),
        ]
        with caplog.at_level(logging.INFO):
            result = analyzer._compute_clusters(summaries)
        assert result is None
        assert "Not enough data views" in caplog.text

    def test_full_clustering_with_precomputed(self, mock_cja, logger):
        """Full clustering path with precomputed pairwise distances."""
        scipy = pytest.importorskip("scipy")  # noqa: F841

        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, enable_clustering=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        summaries = [
            DataViewSummary(
                data_view_id="dv1",
                data_view_name="Prod View 1",
                metric_ids={"m1", "m2", "m3"},
                dimension_ids={"d1"},
                metric_count=3,
                dimension_count=1,
            ),
            DataViewSummary(
                data_view_id="dv2",
                data_view_name="Prod View 2",
                metric_ids={"m1", "m2", "m3"},
                dimension_ids={"d1", "d2"},
                metric_count=3,
                dimension_count=2,
            ),
            DataViewSummary(
                data_view_id="dv3",
                data_view_name="Dev Analytics",
                metric_ids={"m10", "m11"},
                dimension_ids={"d10"},
                metric_count=2,
                dimension_count=1,
            ),
        ]

        # Precompute pairwise
        precomputed = analyzer._compute_pairwise_jaccard(summaries)
        result = analyzer._compute_clusters(summaries, precomputed=precomputed)
        assert result is not None
        assert len(result) >= 1
        # Clusters should be sorted by size descending
        for i in range(len(result) - 1):
            assert result[i].size >= result[i + 1].size

    def test_clustering_without_precomputed(self, mock_cja, logger):
        """Clustering should work without precomputed data too."""
        scipy = pytest.importorskip("scipy")  # noqa: F841

        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, enable_clustering=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        summaries = [
            DataViewSummary(
                data_view_id="dv1",
                data_view_name="Alpha 1",
                metric_ids={"m1", "m2"},
                dimension_ids=set(),
                metric_count=2,
                dimension_count=0,
            ),
            DataViewSummary(
                data_view_id="dv2",
                data_view_name="Alpha 2",
                metric_ids={"m1", "m2", "m3"},
                dimension_ids=set(),
                metric_count=3,
                dimension_count=0,
            ),
        ]
        result = analyzer._compute_clusters(summaries, precomputed=None)
        assert result is not None
        assert len(result) >= 1

    def test_cluster_has_inferred_name(self, mock_cja, logger):
        """Clusters from similarly-named DVs should have an inferred name."""
        scipy = pytest.importorskip("scipy")  # noqa: F841

        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, enable_clustering=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        # Two very similar DVs with a common prefix
        summaries = [
            DataViewSummary(
                data_view_id="dv1",
                data_view_name="Production East",
                metric_ids={"m1", "m2", "m3", "m4", "m5"},
                dimension_ids={"d1"},
                metric_count=5,
                dimension_count=1,
            ),
            DataViewSummary(
                data_view_id="dv2",
                data_view_name="Production West",
                metric_ids={"m1", "m2", "m3", "m4", "m5"},
                dimension_ids={"d1"},
                metric_count=5,
                dimension_count=1,
            ),
        ]
        result = analyzer._compute_clusters(summaries)
        assert result is not None
        # They should be in the same cluster with inferred name
        cluster = result[0]
        assert cluster.size == 2
        assert cluster.cluster_name == "Production"


def _make_scipy_import_error():
    """Factory for a side_effect that blocks scipy imports but allows others."""
    _real_import = __builtins__.__import__ if hasattr(__builtins__, "__import__") else __import__

    def _fake_import(name, *args, **kwargs):
        if "scipy" in name or "numpy" in name:
            raise ImportError(f"No module named '{name}'")
        return _real_import(name, *args, **kwargs)

    return _fake_import


# ===================================================================
# 17. __init__ cache clear when config.clear_cache=True (lines 91-92)
# ===================================================================


class TestInitCacheClear:
    """Tests for __init__ cache clear when config.clear_cache=True."""

    def test_clear_cache_true_calls_invalidate(self, mock_cja, logger, caplog):
        """clear_cache=True should call cache.invalidate() and log info."""
        from unittest.mock import MagicMock

        config = OrgReportConfig(clear_cache=True, skip_lock=True, cja_per_thread=False)
        mock_cache = MagicMock()

        with caplog.at_level(logging.INFO):
            analyzer = OrgComponentAnalyzer(mock_cja, config, logger, org_id="test@Org", cache=mock_cache)

        mock_cache.invalidate.assert_called_once()
        assert "Cache cleared" in caplog.text
        assert analyzer.cache is mock_cache

    def test_clear_cache_true_no_cache_object_no_error(self, mock_cja, logger):
        """clear_cache=True with cache=None should not raise."""
        config = OrgReportConfig(clear_cache=True, skip_lock=True, cja_per_thread=False)
        # Should not raise even though cache is None
        analyzer = OrgComponentAnalyzer(mock_cja, config, logger, org_id="test@Org", cache=None)
        assert analyzer.cache is None

    def test_clear_cache_false_does_not_call_invalidate(self, mock_cja, logger):
        """clear_cache=False should not call cache.invalidate()."""
        from unittest.mock import MagicMock

        config = OrgReportConfig(clear_cache=False, skip_lock=True, cja_per_thread=False)
        mock_cache = MagicMock()

        OrgComponentAnalyzer(mock_cja, config, logger, org_id="test@Org", cache=mock_cache)
        mock_cache.invalidate.assert_not_called()


# ===================================================================
# 18. _run_analysis_impl - clustering success logging (lines 259-262)
# ===================================================================


class TestRunAnalysisImplClustering:
    """Tests for clustering success logging in _run_analysis_impl."""

    def _setup_analyzer_with_3_dvs(self, mock_cja, logger, **config_kwargs):
        """Create analyzer with 3 DVs suitable for clustering."""
        from unittest.mock import patch

        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, **config_kwargs)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        summaries = [
            DataViewSummary(
                data_view_id="dv1",
                data_view_name="Prod East",
                metric_ids={"m1", "m2", "m3"},
                dimension_ids={"d1"},
                metric_count=3,
                dimension_count=1,
            ),
            DataViewSummary(
                data_view_id="dv2",
                data_view_name="Prod West",
                metric_ids={"m1", "m2", "m3"},
                dimension_ids={"d1", "d2"},
                metric_count=3,
                dimension_count=2,
            ),
            DataViewSummary(
                data_view_id="dv3",
                data_view_name="Dev Analytics",
                metric_ids={"m10"},
                dimension_ids={"d10"},
                metric_count=1,
                dimension_count=1,
            ),
        ]

        patches = [
            patch.object(
                analyzer,
                "_list_and_filter_data_views",
                return_value=([{"id": "dv1"}, {"id": "dv2"}, {"id": "dv3"}], False, 3),
            ),
            patch.object(analyzer, "_fetch_all_data_views", return_value=summaries),
            patch.object(analyzer, "_check_memory_warning"),
        ]
        return analyzer, patches

    def test_clustering_success_logging(self, mock_cja, logger, caplog):
        """enable_clustering=True with 3+ DVs should log cluster count."""
        scipy = pytest.importorskip("scipy")  # noqa: F841

        analyzer, patches = self._setup_analyzer_with_3_dvs(
            mock_cja,
            logger,
            enable_clustering=True,
            skip_similarity=True,
        )
        with patches[0], patches[1], patches[2], caplog.at_level(logging.INFO):
            result = analyzer.run_analysis()
        assert result.clusters is not None
        assert "Found" in caplog.text and "clusters" in caplog.text

    def test_clustering_disabled_no_clusters(self, mock_cja, logger, caplog):
        """enable_clustering=False should result in no clusters."""
        analyzer, patches = self._setup_analyzer_with_3_dvs(
            mock_cja,
            logger,
            enable_clustering=False,
            skip_similarity=True,
        )
        with patches[0], patches[1], patches[2], caplog.at_level(logging.INFO):
            result = analyzer.run_analysis()
        assert result.clusters is None


# ===================================================================
# 19. _run_analysis_impl - stale components logging (line 303)
# ===================================================================


class TestRunAnalysisImplStaleLogging:
    """Tests for stale components logging in _run_analysis_impl."""

    def _setup_analyzer_with_stale_data(self, mock_cja, logger, **config_kwargs):
        """Create analyzer with data containing stale-named components."""
        from unittest.mock import patch

        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, **config_kwargs)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        # Components with stale naming patterns
        summaries = [
            DataViewSummary(
                data_view_id="dv1",
                data_view_name="DV 1",
                metric_ids={"test_metric", "old_metric"},
                dimension_ids={"temp_dim"},
                metric_count=2,
                dimension_count=1,
            ),
        ]

        patches = [
            patch.object(
                analyzer,
                "_list_and_filter_data_views",
                return_value=([{"id": "dv1"}], False, 1),
            ),
            patch.object(analyzer, "_fetch_all_data_views", return_value=summaries),
            patch.object(analyzer, "_check_memory_warning"),
        ]
        return analyzer, patches

    def test_stale_components_logging(self, mock_cja, logger, caplog):
        """flag_stale=True with stale components should log their count."""
        analyzer, patches = self._setup_analyzer_with_stale_data(
            mock_cja,
            logger,
            flag_stale=True,
            skip_similarity=True,
        )
        with patches[0], patches[1], patches[2], caplog.at_level(logging.INFO):
            result = analyzer.run_analysis()
        assert result.stale_components is not None
        assert len(result.stale_components) > 0
        assert "stale naming patterns" in caplog.text


# ===================================================================
# 20. _list_and_filter_data_views - stratified sampling path (line 406)
# ===================================================================


class TestListAndFilterStratified:
    """Tests for the stratified sampling path in _list_and_filter_data_views."""

    def test_stratified_sampling_triggered(self, mock_cja, logger):
        """sample_stratified=True should use _stratified_sample."""
        dvs = [{"id": f"dv{i}", "name": f"Group{i % 3} Item {i}"} for i in range(20)]
        mock_cja.getDataViews.return_value = dvs
        config = OrgReportConfig(
            sample_size=5,
            sample_stratified=True,
            sample_seed=42,
            skip_lock=True,
            cja_per_thread=False,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        result, is_sampled, total = analyzer._list_and_filter_data_views()
        assert len(result) == 5
        assert is_sampled is True
        assert total == 20

    def test_stratified_vs_random_may_differ(self, mock_cja, logger):
        """Stratified and random sampling should potentially select different items."""
        dvs = [{"id": f"a{i}", "name": f"Alpha Item {i}"} for i in range(15)] + [
            {"id": f"b{i}", "name": f"Beta Item {i}"} for i in range(5)
        ]
        mock_cja.getDataViews.return_value = dvs

        # Stratified
        config_strat = OrgReportConfig(
            sample_size=5,
            sample_stratified=True,
            sample_seed=0,
            skip_lock=True,
            cja_per_thread=False,
        )
        analyzer_strat = _make_analyzer(mock_cja, logger, config=config_strat)
        strat_result, _, _ = analyzer_strat._list_and_filter_data_views()

        # Random
        config_rand = OrgReportConfig(
            sample_size=5,
            sample_stratified=False,
            sample_seed=0,
            skip_lock=True,
            cja_per_thread=False,
        )
        analyzer_rand = _make_analyzer(mock_cja, logger, config=config_rand)
        rand_result, _, _ = analyzer_rand._list_and_filter_data_views()

        # Both should give 5 results
        assert len(strat_result) == 5
        assert len(rand_result) == 5


# ===================================================================
# 21. _stratified_sample - prefix separator splitting (lines 442-443)
# ===================================================================


class TestStratifiedSamplePrefixSeparator:
    """Tests for prefix separator splitting in _stratified_sample."""

    def _make_dvs(self, names: list[str]) -> list[dict]:
        return [{"id": f"dv_{i}", "name": n} for i, n in enumerate(names)]

    def test_hyphen_separator_splits_prefix(self, mock_cja, logger):
        """Names with hyphens should be split at the hyphen for grouping."""
        names = [f"prod-east-item{i}" for i in range(5)] + [f"dev-west-item{i}" for i in range(5)]
        dvs = self._make_dvs(names)
        config = OrgReportConfig(sample_size=4, sample_seed=1, skip_lock=True, cja_per_thread=False)
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        result = analyzer._stratified_sample(dvs, 4)
        assert len(result) == 4

    def test_underscore_separator_splits_prefix(self, mock_cja, logger):
        """Names with underscores should be split at the underscore for grouping."""
        names = [f"analytics_east_{i}" for i in range(6)] + [f"reporting_west_{i}" for i in range(4)]
        dvs = self._make_dvs(names)
        config = OrgReportConfig(sample_size=3, sample_seed=2, skip_lock=True, cja_per_thread=False)
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        result = analyzer._stratified_sample(dvs, 3)
        assert len(result) == 3

    def test_space_separator_splits_prefix(self, mock_cja, logger):
        """Names with spaces should be split at the space for grouping."""
        names = [f"Production View {i}" for i in range(4)] + [f"Staging View {i}" for i in range(4)]
        dvs = self._make_dvs(names)
        config = OrgReportConfig(sample_size=4, sample_seed=3, skip_lock=True, cja_per_thread=False)
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        result = analyzer._stratified_sample(dvs, 4)
        assert len(result) == 4


# ===================================================================
# 22. _stratified_sample - under-sampling adjustment backfill (lines 462-464)
# ===================================================================


class TestStratifiedSampleBackfill:
    """Tests for under-sampling adjustment backfill in _stratified_sample."""

    def _make_dvs(self, names: list[str]) -> list[dict]:
        return [{"id": f"dv_{i}", "name": n} for i, n in enumerate(names)]

    def test_backfill_from_remaining_when_proportional_underallocates(self, mock_cja, logger):
        """When proportional gives fewer than sample_size, backfill adds from remaining."""
        # Two large groups of 50 each. Proportional allocation for sample_size=10
        # gives max(1, int(10*50/100))=5 per group = 10 total.
        # But with sample_size=12, proportional gives max(1, int(12*50/100))=6 per group = 12.
        # With sample_size=15 proportional: max(1, int(15*50/100))=7 per group = 14 < 15 => backfill
        names = [f"Alpha DV {i}" for i in range(50)] + [f"Beta DV {i}" for i in range(50)]
        dvs = self._make_dvs(names)
        config = OrgReportConfig(sample_size=15, sample_seed=42, skip_lock=True, cja_per_thread=False)
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        result = analyzer._stratified_sample(dvs, 15)
        assert len(result) == 15

    def test_backfill_many_small_groups(self, mock_cja, logger):
        """Many single-item groups where proportional gives less than needed, triggering backfill."""
        # 20 unique single-word prefixes with 1 item each.
        # Proportional: max(1, int(8*1/20))=max(1,0)=1 each = 20 items > 8 => over-sampling trim.
        # But if each group has 2 items: max(1, int(8*2/20))=max(1,0)=1 each = 20 items > 8 => trim.
        # Actually need a case where proportional < sample.
        # 3 groups of 30 items. sample=10. Proportional: max(1, int(10*30/90))=3 each = 9 < 10 => backfill
        names = (
            [f"Alpha DV {i}" for i in range(30)]
            + [f"Beta DV {i}" for i in range(30)]
            + [f"Gamma DV {i}" for i in range(30)]
        )
        dvs = self._make_dvs(names)
        config = OrgReportConfig(sample_size=10, sample_seed=7, skip_lock=True, cja_per_thread=False)
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        result = analyzer._stratified_sample(dvs, 10)
        assert len(result) == 10


# ===================================================================
# 23. _fetch_all_data_views - future exception handling (lines 566-570)
# ===================================================================


class TestFetchAllDataViewsFutureException:
    """Tests for non-LockOwnershipLostError exception in _fetch_all_data_views futures."""

    def test_future_exception_creates_error_summary(self, mock_cja, logger):
        """When a future raises a non-lock exception, an error summary should be appended."""
        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, quiet=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        analyzer.cache = None

        # Make the fetch method raise an exception
        from unittest.mock import patch

        def failing_fetch(dv):
            raise RuntimeError("API connection lost")

        with patch.object(analyzer, "_fetch_data_view_components", side_effect=failing_fetch):
            result = analyzer._fetch_all_data_views([{"id": "dv1", "name": "Failing DV"}])

        assert len(result) == 1
        assert result[0].error is not None
        assert "API connection lost" in result[0].error

    def test_future_exception_with_empty_message(self, mock_cja, logger):
        """Exception with empty message should fallback to type name."""
        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, quiet=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        analyzer.cache = None

        from unittest.mock import patch

        def empty_msg_fetch(dv):
            raise ValueError("")

        with patch.object(analyzer, "_fetch_data_view_components", side_effect=empty_msg_fetch):
            result = analyzer._fetch_all_data_views([{"id": "dv2", "name": "Empty Error DV"}])

        assert len(result) == 1
        assert result[0].error is not None
        assert "ValueError" in result[0].error


# ===================================================================
# 24. _fetch_data_view_components - metric/dimension names with include_names (lines 637-638, 676-677)
# ===================================================================


class TestFetchDataViewComponentsNames:
    """Tests for metric/dimension name capture with include_names=True."""

    def test_include_names_populates_metric_names(self, mock_cja, logger):
        """include_names=True should populate metric_names dict."""
        config = OrgReportConfig(
            skip_lock=True,
            cja_per_thread=False,
            include_names=True,
            include_metadata=False,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        mock_cja.getMetrics.return_value = pd.DataFrame(
            {
                "id": ["m1", "m2"],
                "name": ["Revenue", "Page Views"],
            },
        )
        mock_cja.getDimensions.return_value = pd.DataFrame(
            {
                "id": ["d1"],
                "name": ["Browser"],
            },
        )

        dv = {"id": "dv_test", "name": "Test DV"}
        result = analyzer._fetch_data_view_components(dv)
        assert result.metric_names is not None
        assert result.metric_names["m1"] == "Revenue"
        assert result.metric_names["m2"] == "Page Views"

    def test_include_names_populates_dimension_names(self, mock_cja, logger):
        """include_names=True should populate dimension_names dict."""
        config = OrgReportConfig(
            skip_lock=True,
            cja_per_thread=False,
            include_names=True,
            include_metadata=False,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        mock_cja.getMetrics.return_value = pd.DataFrame({"id": ["m1"], "name": ["Revenue"]})
        mock_cja.getDimensions.return_value = pd.DataFrame(
            {
                "id": ["d1", "d2"],
                "name": ["Browser", "Country"],
            },
        )

        dv = {"id": "dv_test", "name": "Test DV"}
        result = analyzer._fetch_data_view_components(dv)
        assert result.dimension_names is not None
        assert result.dimension_names["d1"] == "Browser"
        assert result.dimension_names["d2"] == "Country"

    def test_include_names_false_leaves_names_none(self, mock_cja, logger):
        """include_names=False should leave metric_names and dimension_names as None."""
        config = OrgReportConfig(
            skip_lock=True,
            cja_per_thread=False,
            include_names=False,
            include_metadata=False,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        mock_cja.getMetrics.return_value = pd.DataFrame({"id": ["m1"], "name": ["Revenue"]})
        mock_cja.getDimensions.return_value = pd.DataFrame({"id": ["d1"], "name": ["Browser"]})

        dv = {"id": "dv_test", "name": "Test DV"}
        result = analyzer._fetch_data_view_components(dv)
        assert result.metric_names is None
        assert result.dimension_names is None


# ===================================================================
# 25. _fetch_data_view_components - metadata fetch (lines 713-729)
# ===================================================================


class TestFetchDataViewComponentsMetadata:
    """Tests for metadata fetch with include_metadata=True."""

    def test_include_metadata_extracts_owner_and_dates(self, mock_cja, logger):
        """include_metadata=True should extract owner, dates, and description."""
        config = OrgReportConfig(
            skip_lock=True,
            cja_per_thread=False,
            include_metadata=True,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        mock_cja.getMetrics.return_value = pd.DataFrame({"id": ["m1"]})
        mock_cja.getDimensions.return_value = pd.DataFrame({"id": ["d1"]})
        mock_cja.getDataView.return_value = {
            "owner": {"name": "Alice Smith", "id": "alice@example.com"},
            "created": "2025-01-15T10:00:00Z",
            "modified": "2025-06-01T12:00:00Z",
            "description": "Production analytics view",
        }

        dv = {"id": "dv_meta", "name": "Metadata DV"}
        result = analyzer._fetch_data_view_components(dv)
        assert result.owner == "Alice Smith"
        assert result.owner_id == "alice@example.com"
        assert result.created == "2025-01-15T10:00:00Z"
        assert result.modified == "2025-06-01T12:00:00Z"
        assert result.has_description is True

    def test_include_metadata_fallback_dates(self, mock_cja, logger):
        """Metadata should try createdDate/modifiedDate fallbacks."""
        config = OrgReportConfig(
            skip_lock=True,
            cja_per_thread=False,
            include_metadata=True,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        mock_cja.getMetrics.return_value = pd.DataFrame({"id": ["m1"]})
        mock_cja.getDimensions.return_value = pd.DataFrame({"id": ["d1"]})
        mock_cja.getDataView.return_value = {
            "createdDate": "2025-02-01T00:00:00Z",
            "modifiedDate": "2025-07-01T00:00:00Z",
            "description": "",
        }

        dv = {"id": "dv_fb", "name": "Fallback DV"}
        result = analyzer._fetch_data_view_components(dv)
        assert result.created == "2025-02-01T00:00:00Z"
        assert result.modified == "2025-07-01T00:00:00Z"
        assert result.has_description is False

    def test_include_metadata_exception_continues(self, mock_cja, logger):
        """Metadata fetch failure should not prevent the summary from being returned."""
        config = OrgReportConfig(
            skip_lock=True,
            cja_per_thread=False,
            include_metadata=True,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        mock_cja.getMetrics.return_value = pd.DataFrame({"id": ["m1"]})
        mock_cja.getDimensions.return_value = pd.DataFrame({"id": ["d1"]})
        mock_cja.getDataView.side_effect = ConnectionError("metadata API down")

        dv = {"id": "dv_err", "name": "Error Metadata DV"}
        result = analyzer._fetch_data_view_components(dv)
        # Should still return a valid summary with metrics/dimensions
        assert result.metric_count == 1
        assert result.dimension_count == 1
        assert result.owner is None
        assert result.error is None  # metadata failure should not set error

    def test_include_metadata_none_response(self, mock_cja, logger):
        """getDataView returning None should leave metadata fields as defaults."""
        config = OrgReportConfig(
            skip_lock=True,
            cja_per_thread=False,
            include_metadata=True,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        mock_cja.getMetrics.return_value = pd.DataFrame({"id": ["m1"]})
        mock_cja.getDimensions.return_value = pd.DataFrame({"id": ["d1"]})
        mock_cja.getDataView.return_value = None

        dv = {"id": "dv_none", "name": "None Response DV"}
        result = analyzer._fetch_data_view_components(dv)
        assert result.owner is None
        assert result.created is None
        assert result.modified is None
        assert result.has_description is False


# ===================================================================
# 26. run_analysis with lock: quick_check_empty_org returns early (line 123)
# ===================================================================


class TestRunAnalysisLockedQuickCheckExit:
    """Line 123: quick_check_empty_org returns non-None inside lock path."""

    def test_quick_check_exits_early_with_lock(self, mock_cja, logger):
        """skip_lock=False + empty org -> returns quick_check_result."""
        from unittest.mock import MagicMock, patch

        config = OrgReportConfig(skip_lock=False, cja_per_thread=False)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        mock_lock = MagicMock()
        mock_lock.acquired = True
        mock_lock.__enter__ = MagicMock(return_value=mock_lock)
        mock_lock.__exit__ = MagicMock(return_value=False)

        empty_result = MagicMock()
        with (
            patch("cja_auto_sdr.org.analyzer.OrgReportLock", return_value=mock_lock),
            patch.object(analyzer, "_assert_lock_healthy"),
            patch.object(analyzer, "_quick_check_empty_org", return_value=empty_result),
        ):
            result = analyzer.run_analysis()
        assert result is empty_result


# ===================================================================
# 27. Cache validation with validate_cache=True (lines 490-496)
# ===================================================================


class TestCacheValidation:
    """Lines 490-496: validate_cache=True with hits and stale entries."""

    def test_validate_cache_logging(self, mock_cja, logger, caplog):
        """validate_cache=True should log cache validation stats."""
        from unittest.mock import MagicMock, patch

        config = OrgReportConfig(
            skip_lock=True,
            cja_per_thread=False,
            use_cache=True,
            validate_cache=True,
            quiet=True,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        mock_cache = MagicMock()
        analyzer.cache = mock_cache

        valid_summary = DataViewSummary(
            data_view_id="dv1",
            data_view_name="Cached DV",
            metric_ids={"m1"},
            dimension_ids=set(),
            metric_count=1,
            dimension_count=0,
        )
        # _validate_cache_entries returns (to_fetch, valid_summaries, valid_count, stale_count)
        with (
            patch.object(analyzer, "_validate_cache_entries", return_value=([], [valid_summary], 1, 2)),
            caplog.at_level(logging.INFO),
        ):
            result = analyzer._fetch_all_data_views([{"id": "dv1", "name": "Cached DV"}])
        assert len(result) == 1
        assert "Cache validation: 1 valid, 2 stale" in caplog.text


# ===================================================================
# 28. Poll loop continue in _fetch_all_data_views (line 552)
# ===================================================================


class TestFetchAllPollLoopContinue:
    """Line 552: wait() timeout -> continue for lock health poll."""

    def test_poll_loop_timeout_continues(self, mock_cja, logger):
        """When wait() times out (no done futures), loop should continue."""
        from concurrent.futures import Future
        from unittest.mock import patch

        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, quiet=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        analyzer.cache = None

        summary = DataViewSummary(
            data_view_id="dv1",
            data_view_name="DV 1",
            metric_ids={"m1"},
            dimension_ids=set(),
            metric_count=1,
            dimension_count=0,
        )

        call_count = {"n": 0}
        future = Future()
        future.set_result(summary)

        def _mock_wait(fs, timeout=None, return_when=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                return set(), fs  # Timeout: no done futures
            return fs, set()  # All done

        with (
            patch("cja_auto_sdr.org.analyzer.wait", side_effect=_mock_wait),
            patch.object(analyzer, "_fetch_data_view_components", return_value=summary),
        ):
            result = analyzer._fetch_all_data_views([{"id": "dv1", "name": "DV 1"}])
        assert len(result) == 1
        assert call_count["n"] == 2  # wait called twice: timeout then done


# ===================================================================
# 29. LockOwnershipLostError re-raise (line 569)
# ===================================================================


class TestFetchAllLockOwnershipLost:
    """Line 569: future raising LockOwnershipLostError should re-raise."""

    def test_lock_ownership_lost_re_raised(self, mock_cja, logger):
        """LockOwnershipLostError from a future should propagate."""
        from unittest.mock import patch

        from cja_auto_sdr.core.exceptions import LockOwnershipLostError

        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, quiet=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        analyzer.cache = None

        def _fail_fetch(dv):
            raise LockOwnershipLostError("lock lost")

        with (
            patch.object(analyzer, "_fetch_data_view_components", side_effect=_fail_fetch),
            pytest.raises(LockOwnershipLostError, match="lock lost"),
        ):
            analyzer._fetch_all_data_views([{"id": "dv1", "name": "DV 1"}])


# ===================================================================
# 30. Thread-local CJA client (lines 605-611)
# ===================================================================


class TestGetThreadClient:
    """Lines 605-611: _get_thread_client with cja_per_thread=True."""

    def test_cja_per_thread_false_returns_shared(self, mock_cja, logger):
        """cja_per_thread=False should return shared client."""
        config = OrgReportConfig(skip_lock=True, cja_per_thread=False)
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        assert analyzer._get_thread_client() is mock_cja

    def test_cja_per_thread_true_creates_thread_local(self, mock_cja, logger):
        """cja_per_thread=True should create a new CJA client per thread."""
        from unittest.mock import MagicMock, patch

        config = OrgReportConfig(skip_lock=True, cja_per_thread=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        mock_cjapy = MagicMock()
        mock_client = MagicMock()
        mock_cjapy.CJA.return_value = mock_client

        with patch.dict("sys.modules", {"cjapy": mock_cjapy}):
            client = analyzer._get_thread_client()
        assert client is mock_client
        mock_cjapy.CJA.assert_called_once()

        # Second call on same thread should reuse cached client
        with patch.dict("sys.modules", {"cjapy": mock_cjapy}):
            client2 = analyzer._get_thread_client()
        assert client2 is mock_client
        # CJA() still called only once (cached in _thread_local)
        mock_cjapy.CJA.assert_called_once()


# ===================================================================
# 31. Limited dimensions classification (line 931)
# ===================================================================


class TestComputeDistributionLimitedDimensions:
    """Line 931: dimension with 2+ DVs but below common threshold -> limited."""

    def test_dimension_in_limited_bucket(self, mock_cja, logger):
        """Dimensions present in 2+ DVs but <25% should be limited."""
        config = OrgReportConfig(skip_lock=True, cja_per_thread=False)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        # 12 DVs: common_threshold = ceil(12*0.25) = 3
        # "limited" needs presence >= 2 AND < 3 => exactly 2
        index = {
            "d_limited": _make_component("d_limited", comp_type="dimension", data_views={"dv0", "dv1"}),
        }
        distribution = analyzer._compute_distribution(index, 12)
        assert "d_limited" in distribution.limited_dimensions


# ===================================================================
# 32. Clustering linkage exception (lines 1089-1091)
# ===================================================================


class TestClusteringLinkageFailure:
    """Lines 1089-1091: linkage() raises exception -> returns None."""

    def test_linkage_exception_returns_none(self, mock_cja, logger, caplog):
        """When linkage() raises, _compute_clusters should return None."""
        pytest.importorskip("scipy")
        from unittest.mock import patch

        config = OrgReportConfig(skip_lock=True, cja_per_thread=False, enable_clustering=True)
        analyzer = _make_analyzer(mock_cja, logger, config=config)

        summaries = [
            DataViewSummary(
                data_view_id="dv1",
                data_view_name="A",
                metric_ids={"m1"},
                dimension_ids=set(),
                metric_count=1,
                dimension_count=0,
            ),
            DataViewSummary(
                data_view_id="dv2",
                data_view_name="B",
                metric_ids={"m2"},
                dimension_ids=set(),
                metric_count=1,
                dimension_count=0,
            ),
        ]

        with (
            patch("scipy.cluster.hierarchy.linkage", side_effect=ValueError("bad input")),
            caplog.at_level(logging.WARNING),
        ):
            result = analyzer._compute_clusters(summaries)
        assert result is None
        assert "Clustering failed" in caplog.text


# ===================================================================
# 33. _infer_cluster_name first word match (line 1166)
# ===================================================================


class TestInferClusterNameFirstWordMatch:
    """Line 1166: first words match but no common prefix >= 3."""

    def test_first_word_match_returns_word(self, mock_cja, logger):
        """Names sharing first word but <3 char prefix -> returns first word."""
        config = OrgReportConfig(skip_lock=True, cja_per_thread=False)
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        # "Go" is only 2 chars, but first word "Go" matches
        result = analyzer._infer_cluster_name(["Go East", "Go West"])
        assert result == "Go"

    def test_no_common_prefix_or_word_returns_none(self, mock_cja, logger):
        """Names with no common prefix or first word -> returns None."""
        config = OrgReportConfig(skip_lock=True, cja_per_thread=False)
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        result = analyzer._infer_cluster_name(["Alpha 1", "Beta 2"])
        assert result is None


# ---------------------------------------------------------------------------
# _compute_clusters  (lines 1058, 1065-1133)
# ---------------------------------------------------------------------------


class TestComputeClustersPrecomputed:
    """Unit tests for _compute_clusters with precomputed pairwise data.

    Requires the ``clustering`` extra (scipy).  The class is collected
    unconditionally; individual tests skip themselves if scipy is absent.
    """

    pytestmark = pytest.mark.skipif(
        not _has_scipy(),
        reason="scipy not installed (install with: uv sync --extra clustering)",
    )

    @staticmethod
    def _make_summaries(n: int, prefix: str = "DV") -> list[DataViewSummary]:
        """Create n DataViewSummary objects with overlapping component sets."""
        summaries = []
        for i in range(n):
            summaries.append(
                DataViewSummary(
                    data_view_id=f"dv_{i}",
                    data_view_name=f"{prefix} {i}",
                    metric_ids={f"m{j}" for j in range(i, i + 5)},
                    dimension_ids={f"d{j}" for j in range(i, i + 3)},
                    metric_count=5,
                    dimension_count=3,
                )
            )
        return summaries

    def test_clusters_returned_with_precomputed_data(self, mock_cja, logger):
        """Happy path: 4 summaries with precomputed pairwise Jaccard similarities."""
        config = OrgReportConfig(
            skip_lock=True,
            cja_per_thread=False,
            enable_clustering=True,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        summaries = self._make_summaries(4)

        # Build precomputed pairwise: pair (0,1) and (2,3) are very similar,
        # cross-group pairs are dissimilar.
        pairwise = {
            (0, 1): 0.9,
            (0, 2): 0.1,
            (0, 3): 0.1,
            (1, 2): 0.1,
            (1, 3): 0.1,
            (2, 3): 0.9,
        }

        clusters = analyzer._compute_clusters(summaries, precomputed=(summaries, pairwise))

        assert clusters is not None
        assert len(clusters) == 2

        # Expected topology: two tight pairs with no cross-group similarity.
        member_sets = {frozenset(c.data_view_ids) for c in clusters}
        assert member_sets == {
            frozenset({"dv_0", "dv_1"}),
            frozenset({"dv_2", "dv_3"}),
        }

        # Pairwise similarity inside each cluster is 0.9 -> cohesion 0.9 after rounding.
        assert {c.cohesion_score for c in clusters} == {0.9}

        # Clusters are sorted by size descending
        sizes = [c.size for c in clusters]
        assert sizes == sorted(sizes, reverse=True)

    def test_cluster_cohesion_reflects_similarity(self, mock_cja, logger):
        """Cluster with high internal similarity should have high cohesion."""
        config = OrgReportConfig(
            skip_lock=True,
            cja_per_thread=False,
            enable_clustering=True,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        summaries = self._make_summaries(3)

        # All three are very similar -> single cluster with high cohesion
        pairwise = {
            (0, 1): 0.95,
            (0, 2): 0.90,
            (1, 2): 0.92,
        }

        clusters = analyzer._compute_clusters(summaries, precomputed=(summaries, pairwise))

        assert clusters is not None
        assert len(clusters) == 1
        assert clusters[0].data_view_ids == ["dv_0", "dv_1", "dv_2"]
        assert clusters[0].cohesion_score == 0.9233

    def test_fewer_than_two_summaries_returns_none(self, mock_cja, logger):
        """Clustering with <2 data views should return None."""
        config = OrgReportConfig(
            skip_lock=True,
            cja_per_thread=False,
            enable_clustering=True,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        summaries = self._make_summaries(1)
        pairwise: dict[tuple[int, int], float] = {}

        result = analyzer._compute_clusters(summaries, precomputed=(summaries, pairwise))

        assert result is None

    def test_singleton_clusters_have_zero_cohesion(self, mock_cja, logger):
        """A cluster with a single member should have cohesion 0.0."""
        config = OrgReportConfig(
            skip_lock=True,
            cja_per_thread=False,
            enable_clustering=True,
        )
        analyzer = _make_analyzer(mock_cja, logger, config=config)
        summaries = self._make_summaries(2)

        # Completely dissimilar -> each in its own cluster
        pairwise = {(0, 1): 0.0}

        clusters = analyzer._compute_clusters(summaries, precomputed=(summaries, pairwise))

        assert clusters is not None
        assert len(clusters) == 2
        singletons = [c for c in clusters if c.size == 1]
        assert len(singletons) == 2
        assert {frozenset(c.data_view_ids) for c in singletons} == {
            frozenset({"dv_0"}),
            frozenset({"dv_1"}),
        }
        for c in singletons:
            assert c.cohesion_score == 0.0


def test_compute_clusters_returns_none_when_scipy_unavailable(
    mock_cja,
    logger,
    monkeypatch,
    caplog,
):
    """Simulate scipy import failure and assert graceful fallback."""
    config = OrgReportConfig(
        skip_lock=True,
        cja_per_thread=False,
        enable_clustering=True,
    )
    analyzer = _make_analyzer(mock_cja, logger, config=config)
    summaries = [
        DataViewSummary(data_view_id="dv_0", data_view_name="DV 0", metric_count=1, dimension_count=1),
        DataViewSummary(data_view_id="dv_1", data_view_name="DV 1", metric_count=1, dimension_count=1),
    ]

    original_import = __import__

    def fake_import(name, global_ns=None, local_ns=None, fromlist=(), level=0):
        if name.startswith("scipy"):
            raise ImportError("simulated missing scipy")
        return original_import(name, global_ns, local_ns, fromlist, level)

    monkeypatch.setattr("builtins.__import__", fake_import)

    with caplog.at_level(logging.WARNING, logger=logger.name):
        result = analyzer._compute_clusters(
            summaries,
            precomputed=(summaries, {(0, 1): 0.9}),
        )

    assert result is None
    assert "scipy not available - skipping clustering" in caplog.text


def test_compute_clusters_returns_none_when_linkage_raises(
    mock_cja,
    logger,
    monkeypatch,
    caplog,
):
    """Linkage failures should be logged and return None (no hard failure)."""
    pytest.importorskip("scipy.cluster.hierarchy")
    import scipy.cluster.hierarchy as hierarchy

    config = OrgReportConfig(
        skip_lock=True,
        cja_per_thread=False,
        enable_clustering=True,
    )
    analyzer = _make_analyzer(mock_cja, logger, config=config)
    summaries = [
        DataViewSummary(data_view_id="dv_0", data_view_name="DV 0", metric_count=1, dimension_count=1),
        DataViewSummary(data_view_id="dv_1", data_view_name="DV 1", metric_count=1, dimension_count=1),
    ]

    def raising_linkage(*args, **kwargs):
        raise ValueError("simulated linkage failure")

    monkeypatch.setattr(hierarchy, "linkage", raising_linkage)

    with caplog.at_level(logging.WARNING, logger=logger.name):
        result = analyzer._compute_clusters(
            summaries,
            precomputed=(summaries, {(0, 1): 0.9}),
        )

    assert result is None
    assert "Clustering failed: simulated linkage failure" in caplog.text


def test_compute_clusters_uses_pairwise_computation_when_precomputed_missing(
    mock_cja,
    logger,
    monkeypatch,
):
    """When precomputed data is absent, _compute_pairwise_jaccard is used."""
    pytest.importorskip("scipy.cluster.hierarchy")

    config = OrgReportConfig(
        skip_lock=True,
        cja_per_thread=False,
        enable_clustering=True,
    )
    analyzer = _make_analyzer(mock_cja, logger, config=config)
    summaries = TestComputeClustersPrecomputed._make_summaries(3)

    captured: list[list[DataViewSummary]] = []

    def fake_compute_pairwise(
        input_summaries: list[DataViewSummary],
    ) -> tuple[list[DataViewSummary], dict[tuple[int, int], float]]:
        captured.append(input_summaries)
        pairwise = {
            (0, 1): 0.9,
            (0, 2): 0.1,
            (1, 2): 0.1,
        }
        return input_summaries, pairwise

    monkeypatch.setattr(analyzer, "_compute_pairwise_jaccard", fake_compute_pairwise)

    clusters = analyzer._compute_clusters(summaries, precomputed=None)

    assert len(captured) == 1
    assert captured[0] is summaries
    assert clusters is not None
    member_sets = {frozenset(c.data_view_ids) for c in clusters}
    assert member_sets == {
        frozenset({"dv_0", "dv_1"}),
        frozenset({"dv_2"}),
    }
