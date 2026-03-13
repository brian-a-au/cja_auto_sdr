"""Tests for org-report trending dataclasses (v3.4.0)."""

from cja_auto_sdr.org.models import (
    OrgReportComparison,
    OrgReportTrending,
    TrendingDelta,
    TrendingSnapshot,
    _safe_non_negative_int,
    _snapshot_comparison_input,
)


class TestTrendingSnapshot:
    def test_default_construction(self):
        snap = TrendingSnapshot(timestamp="2026-01-01T00:00:00Z")
        assert snap.timestamp == "2026-01-01T00:00:00Z"
        assert snap.data_view_count == 0
        assert snap.component_count == 0
        assert snap.core_count == 0
        assert snap.isolated_count == 0
        assert snap.high_sim_pair_count == 0
        assert snap.dv_component_counts == {}
        assert snap.dv_core_ratios == {}
        assert snap.dv_max_similarity == {}
        assert snap.dv_ids == set()
        assert snap.complete_data_view_ids is False
        assert snap.complete_high_similarity_pairs is False

    def test_full_construction(self):
        snap = TrendingSnapshot(
            timestamp="2026-03-08T12:00:00Z",
            data_view_count=15,
            component_count=395,
            core_count=315,
            isolated_count=80,
            high_sim_pair_count=4,
            dv_component_counts={"dv1": 100, "dv2": 200},
            dv_core_ratios={"dv1": 0.8, "dv2": 0.6},
            dv_max_similarity={"dv1": 0.95, "dv2": 0.7},
            dv_ids={"dv1", "dv2"},
        )
        assert snap.data_view_count == 15
        assert snap.component_count == 395
        assert snap.dv_ids == {"dv1", "dv2"}

    def test_complete_data_view_ids_defaults_false_when_counts_exceed_observed_ids(self):
        snap = TrendingSnapshot(
            timestamp="2026-03-08T12:00:00Z",
            data_view_count=5,
            analyzed_data_view_count=4,
            dv_ids={"a", "b", "c", "d"},
        )

        assert snap.has_data_view_ids is True
        assert snap.complete_data_view_ids is False

    def test_complete_data_view_ids_defaults_false_when_only_analyzed_count_matches(self):
        snap = TrendingSnapshot(
            timestamp="2026-03-08T12:00:00Z",
            data_view_count=0,
            analyzed_data_view_count=4,
            dv_ids={"a", "b", "c", "d"},
        )

        assert snap.has_data_view_ids is True
        assert snap.complete_data_view_ids is False

    def test_complete_data_view_ids_defaults_true_for_exact_id_only_manual_snapshots_without_totals(self):
        snap = TrendingSnapshot(
            timestamp="2026-03-08T12:00:00Z",
            dv_ids={"a", "b"},
        )

        assert snap.data_view_count == 2
        assert snap.has_data_view_ids is True
        assert snap.complete_data_view_ids is True

    def test_data_view_count_falls_back_to_analyzed_total_when_snapshot_total_is_absent_and_ids_are_incomplete(self):
        snap = TrendingSnapshot(
            timestamp="2026-03-08T12:00:00Z",
            analyzed_data_view_count=4,
            dv_ids={"a", "b", "c"},
        )

        assert snap.data_view_count == 4
        assert snap.complete_data_view_ids is False

    def test_complete_data_view_ids_defaults_false_when_zero_total_is_omitted(self):
        snap = TrendingSnapshot(
            timestamp="2026-03-08T12:00:00Z",
            analyzed_data_view_count=0,
        )

        assert snap.data_view_count == 0
        assert snap.has_data_view_ids is False
        assert snap.complete_data_view_ids is False

    def test_complete_data_view_ids_defaults_true_for_explicit_empty_zero_count_snapshots(self):
        snap = TrendingSnapshot(
            timestamp="2026-03-08T12:00:00Z",
            data_view_count=0,
        )

        assert snap.has_data_view_ids is False
        assert snap.complete_data_view_ids is True

    def test_complete_data_view_ids_defaults_false_for_ambiguous_normalized_ids(self):
        snap = TrendingSnapshot(
            timestamp="2026-03-08T12:00:00Z",
            data_view_count=1,
            dv_ids={"dv1", " dv1 "},
        )

        assert snap.has_data_view_ids is True
        assert snap.complete_data_view_ids is False

    def test_snapshot_comparison_input_filters_auxiliary_name_only_ids_when_explicit_dv_ids_exist(self):
        snap = TrendingSnapshot(
            timestamp="2026-03-08T12:00:00Z",
            dv_ids={"dv1"},
            dv_names={"dv1": "Primary", "dv_extra": "Stale metadata"},
        )

        result = _snapshot_comparison_input(snap)

        assert result.data_view_ids == {"dv1"}
        assert result.data_view_names == {"dv1": "Primary"}
        assert result.data_view_count == 1
        assert result.complete_data_view_ids is True

    def test_snapshot_comparison_input_ignores_dirty_name_keys_when_explicit_dv_ids_are_complete(self):
        snap = TrendingSnapshot(
            timestamp="2026-03-08T12:00:00Z",
            dv_ids={"dv1"},
            dv_names={"dv1": "Primary", " dv1 ": "Duplicate metadata"},
        )

        result = _snapshot_comparison_input(snap)

        assert result.data_view_ids == {"dv1"}
        assert result.complete_data_view_ids is True

    def test_snapshot_comparison_input_uses_analyzed_total_when_snapshot_total_is_absent(self):
        snap = TrendingSnapshot(
            timestamp="2026-03-08T12:00:00Z",
            analyzed_data_view_count=4,
            dv_ids={"a", "b", "c"},
        )

        result = _snapshot_comparison_input(snap)

        assert result.data_view_ids == {"a", "b", "c"}
        assert result.data_view_count == 4
        assert result.complete_data_view_ids is False

    def test_complete_high_similarity_pairs_defaults_false_for_manual_snapshots(self):
        snap = TrendingSnapshot(
            timestamp="2026-03-08T12:00:00Z",
            high_sim_pair_count=1,
            high_similarity_pairs={("a", "b")},
        )

        assert snap.complete_high_similarity_pairs is False


class TestTrendingDelta:
    def test_default_construction(self):
        delta = TrendingDelta(
            from_timestamp="2026-01-01T00:00:00Z",
            to_timestamp="2026-02-01T00:00:00Z",
        )
        assert delta.data_view_delta == 0
        assert delta.component_delta == 0
        assert delta.core_delta == 0
        assert delta.isolated_delta == 0
        assert delta.high_sim_pair_delta == 0

    def test_with_values(self):
        delta = TrendingDelta(
            from_timestamp="2026-01-01",
            to_timestamp="2026-02-01",
            data_view_delta=2,
            component_delta=50,
            core_delta=30,
            isolated_delta=20,
            high_sim_pair_delta=1,
        )
        assert delta.data_view_delta == 2
        assert delta.component_delta == 50


class TestOrgReportTrending:
    def _make_snapshot(
        self,
        timestamp,
        dv_count=10,
        analyzed_dv_count=None,
        comp_count=100,
        core=80,
        iso=20,
        sim=2,
        dv_ids=None,
        has_data_view_ids=None,
        complete_data_view_ids=None,
        complete_high_similarity_pairs=None,
        component_ids=None,
        high_similarity_pairs=None,
    ):
        return TrendingSnapshot(
            timestamp=timestamp,
            data_view_count=dv_count,
            analyzed_data_view_count=analyzed_dv_count,
            component_count=comp_count,
            core_count=core,
            isolated_count=iso,
            high_sim_pair_count=sim,
            dv_ids=set() if dv_ids is None else dv_ids,
            has_data_view_ids=(dv_ids is not None) if has_data_view_ids is None else has_data_view_ids,
            complete_data_view_ids=complete_data_view_ids,
            complete_high_similarity_pairs=complete_high_similarity_pairs,
            component_ids=component_ids,
            high_similarity_pairs=high_similarity_pairs or set(),
        )

    def test_empty_construction(self):
        trending = OrgReportTrending()
        assert trending.snapshots == []
        assert trending.deltas == []
        assert trending.drift_scores == {}
        assert trending.window_size == 0

    def test_single_snapshot(self):
        snap = self._make_snapshot("2026-01-01")
        trending = OrgReportTrending(snapshots=[snap], window_size=1)
        assert trending.window_size == 1
        assert len(trending.snapshots) == 1

    def test_multiple_snapshots(self):
        snaps = [
            self._make_snapshot("2026-01-01", dv_count=10, comp_count=100),
            self._make_snapshot("2026-02-01", dv_count=12, comp_count=120),
            self._make_snapshot("2026-03-01", dv_count=15, comp_count=150),
        ]
        deltas = [
            TrendingDelta("2026-01-01", "2026-02-01", data_view_delta=2, component_delta=20),
            TrendingDelta("2026-02-01", "2026-03-01", data_view_delta=3, component_delta=30),
        ]
        trending = OrgReportTrending(
            snapshots=snaps,
            deltas=deltas,
            drift_scores={"dv1": 0.8, "dv2": 0.3},
            window_size=3,
        )
        assert trending.window_size == 3
        assert len(trending.deltas) == 2
        assert trending.drift_scores["dv1"] == 0.8

    def test_to_comparison_with_zero_snapshots(self):
        trending = OrgReportTrending()
        assert trending.to_comparison() is None

    def test_to_comparison_with_one_snapshot(self):
        trending = OrgReportTrending(
            snapshots=[self._make_snapshot("2026-01-01")],
            window_size=1,
        )
        assert trending.to_comparison() is None

    def test_to_comparison_with_two_snapshots(self):
        snaps = [
            self._make_snapshot("2026-01-01", dv_count=2, comp_count=100, core=80, iso=20, dv_ids={"a", "b"}),
            self._make_snapshot("2026-02-01", dv_count=3, comp_count=120, core=95, iso=25, dv_ids={"a", "b", "c"}),
        ]
        trending = OrgReportTrending(snapshots=snaps, window_size=2)
        comparison = trending.to_comparison()

        assert isinstance(comparison, OrgReportComparison)
        assert comparison.current_timestamp == "2026-02-01"
        assert comparison.previous_timestamp == "2026-01-01"
        assert comparison.data_views_added == ["c"]
        assert comparison.data_views_removed == []
        assert comparison.components_added == 20
        assert comparison.components_removed == 0
        assert comparison.core_delta == 15
        assert comparison.isolated_delta == 5
        assert comparison.summary["data_views_delta"] == 1
        assert comparison.summary["components_delta"] == 20

    def test_to_comparison_uses_last_two_snapshots(self):
        snaps = [
            self._make_snapshot("2026-01-01", dv_count=1, comp_count=100, dv_ids={"a"}),
            self._make_snapshot("2026-02-01", dv_count=2, comp_count=120, dv_ids={"a", "b"}),
            self._make_snapshot("2026-03-01", dv_count=3, comp_count=150, dv_ids={"a", "b", "c"}),
        ]
        trending = OrgReportTrending(snapshots=snaps, window_size=3)
        comparison = trending.to_comparison()

        # Should compare last two: Feb vs Mar
        assert comparison.previous_timestamp == "2026-02-01"
        assert comparison.current_timestamp == "2026-03-01"
        assert comparison.data_views_added == ["c"]

    def test_to_comparison_with_removals(self):
        snaps = [
            self._make_snapshot("2026-01-01", dv_count=3, comp_count=300, dv_ids={"a", "b", "c"}),
            self._make_snapshot("2026-02-01", dv_count=2, comp_count=200, dv_ids={"a", "c"}),
        ]
        trending = OrgReportTrending(snapshots=snaps, window_size=2)
        comparison = trending.to_comparison()

        assert comparison.data_views_removed == ["b"]
        assert comparison.components_removed == 100
        assert comparison.summary["components_delta"] == -100

    def test_to_comparison_uses_reported_count_when_snapshot_ids_are_unavailable(self):
        snaps = [
            self._make_snapshot("2026-01-01", dv_count=10, analyzed_dv_count=8, dv_ids=None),
            self._make_snapshot("2026-02-01", dv_count=10, analyzed_dv_count=6, dv_ids=None),
        ]

        comparison = OrgReportTrending(snapshots=snaps, window_size=2).to_comparison()

        assert comparison is not None
        assert comparison.data_views_added == []
        assert comparison.data_views_removed == []
        assert comparison.summary["data_views_delta"] == 0

    def test_to_comparison_suppresses_exact_dv_lists_when_only_one_side_has_ids(self):
        snaps = [
            self._make_snapshot("2026-01-01", dv_count=8, analyzed_dv_count=8, dv_ids=None),
            self._make_snapshot(
                "2026-02-01",
                dv_count=9,
                analyzed_dv_count=9,
                dv_ids={f"dv_{index}" for index in range(9)},
            ),
        ]

        comparison = OrgReportTrending(snapshots=snaps, window_size=2).to_comparison()

        assert comparison is not None
        assert comparison.data_views_added == []
        assert comparison.data_views_removed == []
        assert comparison.summary["data_views_delta"] == 1

    def test_to_comparison_suppresses_exact_dv_lists_during_partial_failures(self):
        snaps = [
            self._make_snapshot(
                "2026-01-01",
                dv_count=5,
                analyzed_dv_count=5,
                dv_ids={"a", "b", "c", "d", "e"},
                complete_data_view_ids=True,
            ),
            self._make_snapshot(
                "2026-02-01",
                dv_count=5,
                analyzed_dv_count=4,
                dv_ids={"a", "c", "d", "e"},
                complete_data_view_ids=False,
            ),
        ]

        comparison = OrgReportTrending(snapshots=snaps, window_size=2).to_comparison()

        assert comparison is not None
        assert comparison.data_views_removed == []
        assert comparison.summary["data_views_delta"] == 0

    def test_to_comparison_infers_incomplete_manual_snapshot_ids_from_count_mismatch(self):
        snaps = [
            self._make_snapshot(
                "2026-01-01",
                dv_count=5,
                analyzed_dv_count=5,
                dv_ids={"a", "b", "c", "d", "e"},
            ),
            self._make_snapshot(
                "2026-02-01",
                dv_count=5,
                analyzed_dv_count=4,
                dv_ids={"a", "c", "d", "e"},
            ),
        ]

        comparison = OrgReportTrending(snapshots=snaps, window_size=2).to_comparison()

        assert comparison is not None
        assert comparison.data_views_removed == []
        assert comparison.summary["data_views_delta"] == 0

    def test_to_comparison_suppresses_exact_dv_lists_when_only_analyzed_count_matches(self):
        snaps = [
            self._make_snapshot(
                "2026-01-01",
                dv_count=5,
                analyzed_dv_count=5,
                dv_ids={"a", "b", "c", "d", "e"},
            ),
            self._make_snapshot(
                "2026-02-01",
                dv_count=0,
                analyzed_dv_count=4,
                dv_ids={"a", "c", "d", "e"},
            ),
        ]

        comparison = OrgReportTrending(snapshots=snaps, window_size=2).to_comparison()

        assert comparison is not None
        assert comparison.data_views_added == []
        assert comparison.data_views_removed == []
        assert comparison.summary["data_views_delta"] == -1

    def test_to_comparison_preserves_exact_dv_diffs_for_id_only_manual_snapshots_without_totals(self):
        previous = TrendingSnapshot(
            timestamp="2026-01-01",
            dv_ids={"a", "b"},
            dv_names={"a": "Alpha", "b": "Beta"},
        )
        current = TrendingSnapshot(
            timestamp="2026-02-01",
            dv_ids={"a", "c"},
            dv_names={"a": "Alpha", "c": "Gamma"},
        )

        comparison = OrgReportTrending(snapshots=[previous, current], window_size=2).to_comparison()

        assert comparison is not None
        assert comparison.data_views_added == ["c"]
        assert comparison.data_views_removed == ["b"]
        assert comparison.data_views_added_names == ["Gamma"]
        assert comparison.data_views_removed_names == ["Beta"]
        assert comparison.summary["data_views_delta"] == 0

    def test_to_comparison_ignores_dirty_auxiliary_name_keys_when_explicit_dv_ids_are_complete(self):
        previous = TrendingSnapshot(
            timestamp="2026-01-01",
            dv_ids={"dv1"},
            dv_names={"dv1": "Data View 1", " dv1 ": "Duplicate metadata"},
        )
        current = TrendingSnapshot(
            timestamp="2026-02-01",
            dv_ids={"dv1", "dv2"},
            dv_names={"dv1": "Data View 1", "dv2": "Data View 2", " dv1 ": "Duplicate metadata"},
        )

        comparison = OrgReportTrending(snapshots=[previous, current], window_size=2).to_comparison()

        assert comparison is not None
        assert comparison.data_views_added == ["dv2"]
        assert comparison.data_views_removed == []
        assert comparison.summary["data_views_delta"] == 1

    def test_to_comparison_suppresses_exact_dv_lists_when_zero_total_is_omitted(self):
        previous = self._make_snapshot(
            "2026-01-01",
            dv_count=1,
            analyzed_dv_count=1,
            dv_ids={"a"},
        )
        current = TrendingSnapshot(
            timestamp="2026-02-01",
            analyzed_data_view_count=0,
        )

        comparison = OrgReportTrending(snapshots=[previous, current], window_size=2).to_comparison()

        assert comparison is not None
        assert comparison.data_views_added == []
        assert comparison.data_views_removed == []
        assert comparison.summary["data_views_delta"] == -1

    def test_to_comparison_tracks_exact_dv_removals_for_explicit_empty_zero_count_snapshots(self):
        snaps = [
            self._make_snapshot(
                "2026-01-01",
                dv_count=1,
                analyzed_dv_count=1,
                dv_ids={"a"},
            ),
            self._make_snapshot(
                "2026-02-01",
                dv_count=0,
                analyzed_dv_count=0,
                dv_ids=set(),
            ),
        ]

        comparison = OrgReportTrending(snapshots=snaps, window_size=2).to_comparison()

        assert comparison is not None
        assert comparison.data_views_added == []
        assert comparison.data_views_removed == ["a"]
        assert comparison.summary["data_views_delta"] == -1

    def test_to_comparison_recomputes_zero_total_inference_after_manual_mutation(self):
        previous = self._make_snapshot(
            "2026-01-01",
            dv_count=1,
            analyzed_dv_count=1,
            dv_ids={"a"},
        )
        current = TrendingSnapshot(
            timestamp="2026-02-01",
            analyzed_data_view_count=0,
        )

        current.data_view_count = 0

        comparison = OrgReportTrending(snapshots=[previous, current], window_size=2).to_comparison()

        assert comparison is not None
        assert comparison.data_views_added == []
        assert comparison.data_views_removed == ["a"]
        assert comparison.summary["data_views_delta"] == -1

    def test_to_comparison_recomputes_inferred_snapshot_fidelity_after_manual_mutation(self):
        previous = self._make_snapshot(
            "2026-01-01",
            dv_count=1,
            analyzed_dv_count=1,
            dv_ids={"a"},
        )
        current = self._make_snapshot(
            "2026-02-01",
            dv_count=1,
            analyzed_dv_count=1,
            dv_ids={"a"},
        )

        current.dv_ids.clear()

        comparison = OrgReportTrending(snapshots=[previous, current], window_size=2).to_comparison()

        assert comparison is not None
        assert comparison.data_views_added == []
        assert comparison.data_views_removed == []
        assert comparison.summary["data_views_delta"] == 0

    def test_to_comparison_honors_post_init_manual_completeness_override(self):
        previous = self._make_snapshot(
            "2026-01-01",
            dv_count=1,
            analyzed_dv_count=1,
            dv_ids={"a"},
        )
        current = self._make_snapshot(
            "2026-02-01",
            dv_count=1,
            analyzed_dv_count=1,
            dv_ids=set(),
        )

        current.complete_data_view_ids = True

        comparison = OrgReportTrending(snapshots=[previous, current], window_size=2).to_comparison()

        assert comparison is not None
        assert comparison.data_views_added == []
        assert comparison.data_views_removed == ["a"]
        assert comparison.summary["data_views_delta"] == -1

    def test_identical_snapshots_produce_zero_deltas(self):
        snap = self._make_snapshot("2026-01-01", dv_count=10, comp_count=100, core=80, iso=20, dv_ids={"a"})
        snap2 = self._make_snapshot("2026-02-01", dv_count=10, comp_count=100, core=80, iso=20, dv_ids={"a"})
        trending = OrgReportTrending(snapshots=[snap, snap2], window_size=2)
        comparison = trending.to_comparison()

        assert comparison.data_views_added == []
        assert comparison.data_views_removed == []
        assert comparison.components_added == 0
        assert comparison.components_removed == 0
        assert comparison.core_delta == 0
        assert comparison.isolated_delta == 0
        assert comparison.summary["data_views_delta"] == 0

    def test_to_comparison_preserves_component_replacements_with_exact_ids(self):
        snaps = [
            self._make_snapshot(
                "2026-01-01",
                comp_count=2,
                component_ids={"A", "B"},
            ),
            self._make_snapshot(
                "2026-02-01",
                comp_count=3,
                component_ids={"B", "C", "D"},
            ),
        ]

        comparison = OrgReportTrending(snapshots=snaps, window_size=2).to_comparison()

        assert comparison is not None
        assert comparison.components_added == 2
        assert comparison.components_removed == 1
        assert comparison.summary["components_delta"] == 1

    def test_to_comparison_tracks_high_similarity_pair_changes(self):
        snaps = [
            self._make_snapshot(
                "2026-01-01",
                high_similarity_pairs={("dv1", "dv2")},
                complete_high_similarity_pairs=True,
            ),
            self._make_snapshot(
                "2026-02-01",
                high_similarity_pairs={("dv1", "dv3")},
                complete_high_similarity_pairs=True,
            ),
        ]

        comparison = OrgReportTrending(snapshots=snaps, window_size=2).to_comparison()

        assert comparison is not None
        assert comparison.new_high_similarity_pairs == [{"dv1_id": "dv1", "dv2_id": "dv3"}]
        assert comparison.resolved_pairs == [{"dv1_id": "dv1", "dv2_id": "dv2"}]
        assert comparison.summary["new_duplicates"] == 1
        assert comparison.summary["resolved_duplicates"] == 1

    def test_to_comparison_suppresses_manual_pair_deltas_without_completeness_flag(self):
        snaps = [
            self._make_snapshot(
                "2026-01-01",
                high_similarity_pairs={("dv1", "dv2")},
            ),
            self._make_snapshot(
                "2026-02-01",
                high_similarity_pairs={("dv1", "dv3")},
            ),
        ]

        comparison = OrgReportTrending(snapshots=snaps, window_size=2).to_comparison()

        assert comparison is not None
        assert comparison.new_high_similarity_pairs == []
        assert comparison.resolved_pairs == []
        assert comparison.summary["new_duplicates"] == 0
        assert comparison.summary["resolved_duplicates"] == 0


class TestSafeNonNegativeInt:
    """Edge-case coverage for _safe_non_negative_int (L462-476)."""

    def test_bool_true_returns_one(self):
        # L462-463: isinstance(value, bool) → return int(value)
        assert _safe_non_negative_int(True) == 1

    def test_bool_false_returns_zero(self):
        assert _safe_non_negative_int(False) == 0

    def test_positive_int_passes_through(self):
        # L464-465: isinstance(value, int) → max(0, value)
        assert _safe_non_negative_int(42) == 42

    def test_negative_int_clamps_to_zero(self):
        assert _safe_non_negative_int(-5) == 0

    def test_positive_float_truncates(self):
        # L466-467: isinstance(value, float) → max(0, int(value))
        assert _safe_non_negative_int(3.9) == 3

    def test_negative_float_clamps_to_zero(self):
        assert _safe_non_negative_int(-2.5) == 0

    def test_string_integer_parses(self):
        # L468-473: isinstance(value, str) → strip + int()
        assert _safe_non_negative_int("  7  ") == 7

    def test_string_negative_clamps_to_zero(self):
        assert _safe_non_negative_int("-3") == 0

    def test_empty_string_returns_zero(self):
        # L470-471: stripped is empty → return 0
        assert _safe_non_negative_int("   ") == 0

    def test_non_numeric_string_returns_zero(self):
        # L474-475: ValueError branch → return 0
        assert _safe_non_negative_int("abc") == 0

    def test_none_returns_zero(self):
        # L476: fallback for unrecognised types
        assert _safe_non_negative_int(None) == 0

    def test_list_returns_zero(self):
        assert _safe_non_negative_int([1, 2, 3]) == 0

    def test_dict_returns_zero(self):
        assert _safe_non_negative_int({"count": 5}) == 0
