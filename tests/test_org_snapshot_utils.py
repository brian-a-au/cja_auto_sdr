"""Direct unit tests for org snapshot helper utilities."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path

import pytest

from cja_auto_sdr.org.snapshot_utils import (
    chronological_snapshot_sort_fields,
    coerce_snapshot_bool,
    coerce_snapshot_float,
    coerce_snapshot_int,
    effective_org_report_data_view_count,
    is_org_report_snapshot_payload,
    newest_first_snapshot_sort_fields,
    normalized_similarity_pair_ids,
    org_report_component_count,
    org_report_core_count,
    org_report_data_view_row_id,
    org_report_data_view_row_raw_id,
    org_report_high_similarity_pairs,
    org_report_isolated_count,
    org_report_snapshot_comparison_assessment,
    org_report_snapshot_comparison_eligible,
    org_report_snapshot_comparison_input,
    org_report_snapshot_content_hash,
    org_report_snapshot_data_view_assessment,
    org_report_snapshot_data_view_stats,
    org_report_snapshot_dedupe_key,
    org_report_snapshot_dir_candidates,
    org_report_snapshot_dir_key,
    org_report_snapshot_dir_paths,
    org_report_snapshot_has_complete_data_view_coverage,
    org_report_snapshot_has_complete_data_view_ids,
    org_report_snapshot_history_assessment,
    org_report_snapshot_history_eligible,
    org_report_snapshot_history_exclusion_reason,
    org_report_snapshot_source_rank,
    parse_snapshot_timestamp,
    reported_org_report_data_view_count,
    snapshot_epoch,
    snapshot_identity_tokens,
    snapshot_path_text,
    snapshot_slug,
    successful_org_report_data_view_rows,
)


def test_parse_snapshot_timestamp_normalizes_common_cases():
    assert parse_snapshot_timestamp(None) is None
    assert parse_snapshot_timestamp("   ") is None
    assert parse_snapshot_timestamp("not-a-date") is None
    assert parse_snapshot_timestamp("2026-03-01T00:00:00Z").tzinfo is UTC
    assert parse_snapshot_timestamp("2026-03-01T00:00:00").tzinfo is UTC


def test_snapshot_epoch_and_sort_fields_handle_missing_timestamps():
    assert snapshot_epoch("invalid") is None
    assert chronological_snapshot_sort_fields("invalid")[0] is True
    assert newest_first_snapshot_sort_fields("invalid")[0] is True


def test_snapshot_path_text_and_slug_normalize_values(tmp_path: Path):
    relative = Path("tests") / ".." / "README.md"

    assert snapshot_path_text(None) == ""
    assert snapshot_path_text(relative) == str(relative.resolve(strict=False))
    assert snapshot_slug(None) == "unknown"
    assert snapshot_slug(":::") == "unknown"
    assert snapshot_slug("org@test.example") == "org_test_example"
    assert snapshot_slug(tmp_path.name, fallback="fallback") == tmp_path.name


def test_org_report_snapshot_dir_helpers_include_legacy_alias():
    key = org_report_snapshot_dir_key("org@test.example")
    candidates = org_report_snapshot_dir_candidates("org@test.example")

    assert key.startswith("org_test_example__")
    assert candidates == (key, "org_test_example")


def test_snapshot_identity_tokens_fall_back_when_no_primary_identity():
    assert snapshot_identity_tokens(snapshot_id="abc", content_hash="def") == (
        ("snapshot_id", "abc"),
        ("content_hash", "def"),
    )
    assert snapshot_identity_tokens(source_path="README.md")[0][0] == "source_path"
    assert snapshot_identity_tokens(fallback_parts=("org_a", 123)) == (("fallback", "org_a", "123"),)


def test_org_report_snapshot_history_eligible_accepts_non_mapping_summary():
    assert org_report_snapshot_history_eligible({"summary": []}) is True
    assert org_report_snapshot_history_eligible({"summary": {"is_sampled": True}}) is False


@pytest.mark.parametrize("payload", [([],), ("not-a-snapshot",), (0,), (None,)])
def test_org_report_snapshot_assessments_fail_closed_for_non_mapping_root(payload):
    history = org_report_snapshot_history_assessment(payload)
    comparison = org_report_snapshot_comparison_assessment(payload)

    assert history.eligible is False
    assert history.exclusion_reason == "invalid_snapshot_payload"
    assert history.fidelity_known is False
    assert org_report_snapshot_history_eligible(payload) is False
    assert org_report_snapshot_history_exclusion_reason(payload) == "invalid_snapshot_payload"

    assert comparison.eligible is False
    assert comparison.exclusion_reason == "invalid_snapshot_payload"
    assert comparison.complete_high_similarity_pairs is False


@pytest.mark.parametrize("payload", [([],), ("not-a-snapshot",), (0,), (None,)])
def test_org_report_snapshot_extractors_return_safe_defaults_for_non_mapping_root(payload):
    assessment = org_report_snapshot_data_view_assessment(payload)
    stats = org_report_snapshot_data_view_stats(payload)

    assert successful_org_report_data_view_rows(payload) == []
    assert assessment.rows_match_reported_total is False
    assert assessment.successful_rows_match_analyzed_total is False
    assert assessment.ids_complete is False
    assert assessment.coverage_complete is False
    assert assessment.duplicate_successful_raw_id_rows == 0
    assert assessment.comparison_complete is False
    assert assessment.history_complete is False
    assert stats.reported_total == 0
    assert stats.analyzed_total == 0
    assert stats.failed_total == 0
    assert stats.raw_total == 0
    assert stats.successful_row_total == 0
    assert effective_org_report_data_view_count(payload) == 0
    assert reported_org_report_data_view_count(payload) is None
    assert org_report_component_count(payload) == 0
    assert org_report_core_count(payload) == 0
    assert org_report_isolated_count(payload) == 0
    assert org_report_high_similarity_pairs(payload) == set()
    assert org_report_snapshot_has_complete_data_view_coverage(payload) is False
    assert org_report_snapshot_has_complete_data_view_ids(payload) is False


@pytest.mark.parametrize("blank_value", ["", "   ", None])
def test_org_report_data_view_row_extractors_fall_back_from_blank_legacy_aliases(blank_value):
    row = {"data_view_id": blank_value, "id": " dv1 "}

    assert org_report_data_view_row_id(row) == "dv1"
    assert org_report_data_view_row_raw_id(row) == " dv1 "


@pytest.mark.parametrize("row", [{"data_view_id": ""}, {"data_view_id": "   "}])
def test_org_report_data_view_row_raw_id_preserves_explicit_blank_ids_without_fallback(row):
    assert org_report_data_view_row_id(row) == ""
    assert org_report_data_view_row_raw_id(row) == ""


@pytest.mark.parametrize("row", [{"data_view_id": 0, "id": "dv1"}, {"data_view_id": False, "id": " dv2 "}])
def test_org_report_data_view_row_extractors_fall_back_from_invalid_scalar_aliases(row):
    expected_normalized = "dv1" if row["id"] == "dv1" else "dv2"

    assert org_report_data_view_row_id(row) == expected_normalized
    assert org_report_data_view_row_raw_id(row) == row["id"]


@pytest.mark.parametrize("row", [{"id": 0}, {"id": False}, {"data_view_id": 1}, {"data_view_id": True}])
def test_org_report_data_view_row_extractors_treat_non_string_scalars_as_missing(row):
    assert org_report_data_view_row_id(row) == ""
    assert org_report_data_view_row_raw_id(row) is None


def test_org_report_snapshot_history_eligible_rejects_similarity_incomplete_payloads():
    assert (
        org_report_snapshot_history_eligible(
            {
                "summary": {
                    "similarity_analysis_complete": False,
                    "similarity_analysis_mode": "org_stats_only",
                }
            }
        )
        is False
    )
    assert (
        org_report_snapshot_history_exclusion_reason(
            {
                "summary": {
                    "similarity_analysis_complete": False,
                    "similarity_analysis_mode": "org_stats_only",
                }
            }
        )
        == "org_stats_only"
    )
    assert (
        org_report_snapshot_history_eligible(
            {
                "parameters": {"skip_similarity": True},
                "similarity_pairs": [],
            }
        )
        is False
    )


def test_org_report_snapshot_history_persisted_meta_can_tighten_derived_fidelity():
    explicitly_ineligible = {
        "_snapshot_meta": {
            "history_eligible": False,
            "history_exclusion_reason": "manual_override",
        },
        "summary": {"similarity_analysis_complete": True},
    }

    assert org_report_snapshot_history_eligible(explicitly_ineligible) is False
    assert org_report_snapshot_history_exclusion_reason(explicitly_ineligible) == "manual_override"


def test_org_report_snapshot_history_persisted_meta_cannot_widen_payload_exclusions():
    explicitly_eligible = {
        "_snapshot_meta": {
            "history_eligible": True,
            "history_exclusion_reason": "sampled",
        },
        "summary": {"is_sampled": True},
    }

    assert org_report_snapshot_history_eligible(explicitly_eligible) is False
    assert org_report_snapshot_history_exclusion_reason(explicitly_eligible) == "sampled"


def test_org_report_snapshot_history_coerces_legacy_string_flags():
    sampled_payload = {"summary": {"is_sampled": "yes"}}
    complete_payload = {"summary": {"similarity_analysis_complete": "complete"}}
    skipped_payload = {
        "parameters": {"skip_similarity": "on"},
    }

    assert org_report_snapshot_history_exclusion_reason(sampled_payload) == "sampled"
    assert org_report_snapshot_history_eligible(complete_payload) is True
    assert org_report_snapshot_history_exclusion_reason(skipped_payload) == "skip_similarity"


def test_org_report_snapshot_comparison_honors_persisted_manual_override():
    payload = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "test_org",
        "report_type": "org_analysis",
        "_snapshot_meta": {
            "history_eligible": False,
            "history_exclusion_reason": "manual_override",
        },
        "summary": {
            "data_views_total": 2,
            "data_views_analyzed": 2,
            "total_unique_components": 0,
            "similarity_analysis_complete": True,
        },
        "distribution": {"core": {"total": 0}, "isolated": {"total": 0}},
        "data_views": [
            {"id": "dv1", "error": None},
            {"id": "dv2", "error": None},
        ],
        "similarity_pairs": [],
    }

    assessment = org_report_snapshot_comparison_assessment(payload)
    assert assessment.eligible is False
    assert assessment.exclusion_reason == "manual_override"
    assert assessment.complete_high_similarity_pairs is False

    with pytest.raises(ValueError, match="manual_override"):
        org_report_snapshot_comparison_input(
            payload,
            require_history_eligible=False,
            require_comparison_eligible=True,
        )


def test_org_report_snapshot_comparison_ignores_persisted_skip_similarity_restating_payload():
    payload = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "test_org",
        "report_type": "org_analysis",
        "_snapshot_meta": {
            "history_eligible": False,
            "history_exclusion_reason": "skip_similarity",
        },
        "summary": {
            "data_views_total": 2,
            "data_views_analyzed": 2,
            "total_unique_components": 0,
            "similarity_analysis_complete": False,
            "similarity_analysis_mode": "skip_similarity",
        },
        "distribution": {"core": {"total": 0}, "isolated": {"total": 0}},
        "data_views": [
            {"id": "dv1", "error": None},
            {"id": "dv2", "error": None},
        ],
        "similarity_pairs": [],
    }

    assessment = org_report_snapshot_comparison_assessment(payload)
    assert assessment.eligible is True
    assert assessment.exclusion_reason is None
    assert assessment.complete_high_similarity_pairs is False

    result = org_report_snapshot_comparison_input(
        payload,
        require_history_eligible=False,
        require_comparison_eligible=True,
    )
    assert result.data_view_ids == {"dv1", "dv2"}
    assert result.complete_high_similarity_pairs is False


@pytest.mark.parametrize("blank_value", ["", "   "])
def test_org_report_snapshot_comparison_allows_blank_legacy_aliases_when_id_fallbacks_are_unique(blank_value):
    payload = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "test_org",
        "report_type": "org_analysis",
        "summary": {
            "data_views_total": 2,
            "data_views_analyzed": 2,
            "total_unique_components": 4,
            "similarity_analysis_complete": True,
        },
        "distribution": {"core": {"total": 1}, "isolated": {"total": 0}},
        "data_views": [
            {"data_view_id": blank_value, "id": "dv1", "data_view_name": "Data View 1", "error": None},
            {"data_view_id": blank_value, "id": "dv2", "data_view_name": "Data View 2", "error": None},
        ],
        "similarity_pairs": [],
    }

    assessment = org_report_snapshot_data_view_assessment(payload)
    assert assessment.ids_complete is True
    assert assessment.duplicate_successful_raw_id_rows == 0
    assert assessment.comparison_complete is True
    assert assessment.history_complete is True
    assert org_report_snapshot_history_eligible(payload) is True
    assert org_report_snapshot_comparison_eligible(payload) is True

    result = org_report_snapshot_comparison_input(payload, require_comparison_eligible=True)
    assert result.data_view_ids == {"dv1", "dv2"}
    assert result.complete_data_view_ids is True
    assert result.complete_high_similarity_pairs is True


@pytest.mark.parametrize(
    ("data_views", "expected_ids"),
    [
        (
            [
                {"id": "dv1", "data_view_name": "Healthy", "error": None},
                {"data_view_name": "Missing ID", "error": None},
            ],
            {"dv1"},
        ),
        (
            [
                {"id": "dv1", "data_view_name": "Healthy", "error": None},
                {"data_view_id": " dv1 ", "data_view_name": "Duplicate", "error": None},
            ],
            {"dv1"},
        ),
        (
            [
                {"id": "dv1", "data_view_name": "Healthy", "error": None},
                {"id": 0, "data_view_name": "Scalar ID", "error": None},
            ],
            {"dv1"},
        ),
    ],
)
def test_org_report_snapshot_comparison_allows_complete_rows_with_incomplete_dv_ids(
    data_views,
    expected_ids,
):
    payload = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "test_org",
        "report_type": "org_analysis",
        "summary": {
            "data_views_total": 2,
            "data_views_analyzed": 2,
            "total_unique_components": 4,
            "similarity_analysis_complete": True,
        },
        "distribution": {"core": {"total": 1}, "isolated": {"total": 0}},
        "data_views": data_views,
        "similarity_pairs": [{"dv1_id": "dv1", "dv2_id": "dv2", "jaccard_similarity": 0.95}],
    }

    assert org_report_snapshot_history_eligible(payload) is False
    assert org_report_snapshot_comparison_eligible(payload) is True

    assessment = org_report_snapshot_comparison_assessment(payload)
    assert assessment.eligible is True
    assert assessment.exclusion_reason is None
    assert assessment.complete_high_similarity_pairs is False

    result = org_report_snapshot_comparison_input(
        payload,
        require_history_eligible=False,
        require_comparison_eligible=True,
    )
    assert result.data_view_ids == expected_ids
    assert result.complete_data_view_ids is False
    assert result.data_view_count == 2
    assert result.comparison_data_view_count == 2
    assert result.complete_high_similarity_pairs is False


@pytest.mark.parametrize(
    "data_views",
    [
        [
            {"id": "", "data_view_name": "Blank 1", "error": None},
            {"id": "", "data_view_name": "Blank 2", "error": None},
        ],
        [
            {"id": "dv1", "data_view_name": "First", "error": None},
            {"data_view_id": "dv1", "data_view_name": "Second", "error": None},
        ],
    ],
)
def test_org_report_snapshot_comparison_rejects_complete_rows_with_raw_id_collisions(data_views):
    payload = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "test_org",
        "report_type": "org_analysis",
        "summary": {
            "data_views_total": 2,
            "data_views_analyzed": 2,
            "total_unique_components": 4,
            "similarity_analysis_complete": True,
        },
        "distribution": {"core": {"total": 1}, "isolated": {"total": 0}},
        "data_views": data_views,
        "similarity_pairs": [],
    }

    assessment = org_report_snapshot_data_view_assessment(payload)
    assert assessment.coverage_complete is True
    assert assessment.duplicate_successful_raw_id_rows == 1
    assert assessment.comparison_complete is False
    assert org_report_snapshot_comparison_eligible(payload) is False

    with pytest.raises(ValueError, match="incomplete_data_views"):
        org_report_snapshot_comparison_input(
            payload,
            require_history_eligible=False,
            require_comparison_eligible=True,
        )


def test_org_report_snapshot_history_excludes_explicit_incomplete_data_views():
    payload = {
        "summary": {
            "data_views_total": 3,
            "data_views_analyzed": 2,
            "similarity_analysis_complete": True,
        },
        "data_views": [
            {"id": "dv1", "error": None},
            {"id": "dv2", "error": None},
            {"id": "dv3", "error": "timeout"},
        ],
    }

    assert org_report_snapshot_history_eligible(payload) is False
    assert org_report_snapshot_history_exclusion_reason(payload) == "incomplete_data_views"


def test_org_report_snapshot_history_excludes_missing_analyzed_count_when_totals_disagree():
    payload = {
        "summary": {
            "data_views_total": 3,
            "similarity_analysis_complete": True,
        },
        "data_views": [
            {"id": "dv1", "error": None},
            {"id": "dv2", "error": None},
        ],
    }

    assert org_report_snapshot_history_eligible(payload) is False
    assert org_report_snapshot_history_exclusion_reason(payload) == "incomplete_data_views"


def test_org_report_snapshot_history_excludes_analyzed_counts_that_exceed_rows():
    payload = {
        "summary": {
            "data_views_total": 3,
            "data_views_analyzed": 3,
            "similarity_analysis_complete": True,
        },
        "data_views": [
            {"id": "dv1", "error": None},
            {"id": "dv2", "error": None},
        ],
    }

    assert org_report_snapshot_has_complete_data_view_coverage(payload) is False
    assert org_report_snapshot_history_eligible(payload) is False
    assert org_report_snapshot_history_exclusion_reason(payload) == "incomplete_data_views"


def test_org_report_snapshot_history_excludes_rows_that_exceed_reported_total():
    payload = {
        "summary": {
            "data_views_total": 2,
            "data_views_analyzed": 2,
            "similarity_analysis_complete": True,
        },
        "data_views": [
            {"id": "dv1", "error": None},
            {"id": "dv2", "error": None},
            {"id": "dv3", "error": None},
        ],
    }

    assert org_report_snapshot_has_complete_data_view_coverage(payload) is False
    assert org_report_snapshot_history_eligible(payload) is False
    assert org_report_snapshot_history_exclusion_reason(payload) == "incomplete_data_views"


def test_org_report_snapshot_history_excludes_missing_data_view_ids_when_counts_match():
    payload = {
        "summary": {
            "data_views_total": 2,
            "data_views_analyzed": 2,
            "similarity_analysis_complete": True,
        },
        "data_views": [
            {"id": "dv1", "error": None},
            {"data_view_name": "Missing ID", "error": None},
        ],
    }

    assert org_report_snapshot_has_complete_data_view_coverage(payload) is True
    assert org_report_snapshot_has_complete_data_view_ids(payload) is False
    assert org_report_snapshot_history_eligible(payload) is False
    assert org_report_snapshot_history_exclusion_reason(payload) == "incomplete_data_views"


def test_org_report_snapshot_history_excludes_duplicate_data_view_ids_when_counts_match():
    payload = {
        "summary": {
            "data_views_total": 2,
            "data_views_analyzed": 2,
            "similarity_analysis_complete": True,
        },
        "data_views": [
            {"id": "dv1", "error": None},
            {"data_view_id": " dv1 ", "error": None},
        ],
    }

    assert org_report_snapshot_has_complete_data_view_coverage(payload) is True
    assert org_report_snapshot_has_complete_data_view_ids(payload) is False
    assert org_report_snapshot_history_eligible(payload) is False
    assert org_report_snapshot_history_exclusion_reason(payload) == "incomplete_data_views"


def test_org_report_snapshot_history_legacy_payload_without_fidelity_fields_is_ineligible():
    legacy_payload = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "test_org",
        "report_type": "org_analysis",
        "summary": {"data_views_total": 3, "total_unique_components": 6},
        "similarity_pairs": [],
    }

    assert org_report_snapshot_history_eligible(legacy_payload) is False
    assert org_report_snapshot_history_exclusion_reason(legacy_payload) == "legacy_missing_fidelity_markers"


def test_org_report_snapshot_history_reclassifies_markerless_cached_payloads_with_stale_meta():
    legacy_cached_payload = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "test_org",
        "_snapshot_meta": {
            "snapshot_id": "persisted-123",
            "history_eligible": True,
            "history_exclusion_reason": None,
        },
        "summary": {"data_views_total": 3, "total_unique_components": 6},
        "distribution": {"core": {"total": 4}, "isolated": {"total": 2}},
        "data_views": [],
        "component_index": {},
        "similarity_pairs": [],
    }

    assert org_report_snapshot_history_eligible(legacy_cached_payload) is False
    assert org_report_snapshot_history_exclusion_reason(legacy_cached_payload) == "legacy_missing_fidelity_markers"


def test_org_report_snapshot_data_view_stats_preserve_reported_total_and_successful_subset():
    stats = org_report_snapshot_data_view_stats(
        {
            "summary": {
                "data_views_total": 5,
                "data_views_analyzed": 3,
            },
            "data_views": [
                {"id": "dv_1", "error": None},
                {"id": "dv_2", "error": None},
                {"id": "dv_3", "error": None},
                {"id": "dv_4", "error": "timeout"},
                {"id": "dv_5", "error": "forbidden"},
            ],
        }
    )

    assert stats.reported_total == 5
    assert stats.analyzed_total == 3
    assert stats.failed_total == 2
    assert stats.successful_row_total == 3


def test_org_report_snapshot_data_view_stats_treat_blank_error_rows_as_failed():
    stats = org_report_snapshot_data_view_stats(
        {
            "summary": {"data_views_total": 2},
            "data_views": [
                {"id": "dv_ok", "error": None},
                {"id": "dv_blank", "error": ""},
            ],
        }
    )

    assert stats.reported_total == 2
    assert stats.analyzed_total == 1
    assert stats.failed_total == 1


def test_org_report_snapshot_content_hash_ignores_trending_and_snapshot_meta():
    base_payload = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "test_org",
        "report_type": "org_analysis",
        "summary": {"data_views_total": 3, "similarity_analysis_complete": True},
        "similarity_pairs": [],
    }
    enriched_payload = {
        **base_payload,
        "_snapshot_meta": {"snapshot_id": "persisted-123"},
        "trending": {"window_size": 2, "snapshots": [{"timestamp": "2026-02-01T00:00:00Z"}]},
    }

    assert org_report_snapshot_content_hash(base_payload) == org_report_snapshot_content_hash(enriched_payload)


def test_org_report_snapshot_content_hash_is_order_insensitive_for_equivalent_collections():
    base_payload = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "test_org",
        "report_type": "org_analysis",
        "summary": {"data_views_total": 2, "total_unique_components": 3},
        "distribution": {
            "core": {
                "metrics_count": 2,
                "dimensions_count": 0,
                "metrics": ["metric_b", "metric_a"],
                "dimensions": [],
            },
        },
        "data_views": [
            {"id": "dv_b", "name": "B", "error": None},
            {"id": "dv_a", "name": "A", "error": None},
        ],
        "component_index": {
            "metric_b": {"type": "metric", "data_views": ["dv_b", "dv_a"]},
            "metric_a": {"type": "metric", "data_views": ["dv_a"]},
        },
        "similarity_pairs": [
            {
                "data_view_1": {"id": "dv_b", "name": "B"},
                "data_view_2": {"id": "dv_a", "name": "A"},
                "jaccard_similarity": 0.95,
                "shared_components": 2,
                "union_size": 3,
            },
        ],
        "naming_audit": {
            "stale_patterns": [
                {"component_id": "metric_b", "data_views": ["dv_b", "dv_a"]},
            ],
        },
        "owner_summary": {
            "by_owner": {
                "Alice": {
                    "data_view_ids": ["dv_b", "dv_a"],
                    "data_view_names": ["B", "A"],
                },
            },
            "owners_sorted_by_dv_count": ["Alice"],
        },
        "stale_components": [
            {"component_id": "metric_b", "data_views": ["dv_b", "dv_a"]},
            {"component_id": "metric_a", "data_views": ["dv_a"]},
        ],
    }
    reordered_payload = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "test_org",
        "report_type": "org_analysis",
        "summary": {"data_views_total": 2, "total_unique_components": 3},
        "distribution": {
            "core": {
                "metrics_count": 2,
                "dimensions_count": 0,
                "metrics": ["metric_a", "metric_b"],
                "dimensions": [],
            },
        },
        "data_views": [
            {"id": "dv_a", "name": "A", "error": None},
            {"id": "dv_b", "name": "B", "error": None},
        ],
        "component_index": {
            "metric_a": {"type": "metric", "data_views": ["dv_a"]},
            "metric_b": {"type": "metric", "data_views": ["dv_a", "dv_b"]},
        },
        "similarity_pairs": [
            {
                "data_view_1": {"id": "dv_b", "name": "B"},
                "data_view_2": {"id": "dv_a", "name": "A"},
                "jaccard_similarity": 0.95,
                "shared_components": 2,
                "union_size": 3,
            },
        ],
        "naming_audit": {
            "stale_patterns": [
                {"component_id": "metric_b", "data_views": ["dv_a", "dv_b"]},
            ],
        },
        "owner_summary": {
            "by_owner": {
                "Alice": {
                    "data_view_ids": ["dv_a", "dv_b"],
                    "data_view_names": ["A", "B"],
                },
            },
            "owners_sorted_by_dv_count": ["Alice"],
        },
        "stale_components": [
            {"component_id": "metric_a", "data_views": ["dv_a"]},
            {"component_id": "metric_b", "data_views": ["dv_a", "dv_b"]},
        ],
    }

    assert org_report_snapshot_content_hash(base_payload) == org_report_snapshot_content_hash(reordered_payload)


# ---------------------------------------------------------------------------
# L128: org_report_snapshot_dir_candidates — single tuple when slug == key
# ---------------------------------------------------------------------------


def test_org_report_snapshot_dir_candidates_returns_single_when_slug_equals_key():
    # For an org_id whose slug is already the full key (no special characters),
    # preferred and legacy are the same value, so only one entry is returned.
    # We fabricate a value where snapshot_slug produces the same string as
    # org_report_snapshot_dir_key by using a pre-hashed key directly.
    from cja_auto_sdr.org.snapshot_utils import org_report_snapshot_dir_key

    org_id = "plain"
    key = org_report_snapshot_dir_key(org_id)
    # key includes a SHA digest suffix so they differ for normal inputs;
    # to exercise L128 we need a value where legacy == key, which happens when
    # snapshot_slug(value) == org_report_snapshot_dir_key(value).
    # We can test this indirectly by patching, but a cleaner approach is to
    # create a mock org_id equal to the key itself (so slug of key == key).
    candidates = org_report_snapshot_dir_candidates(key)
    # key contains "__<hex>" so slug of key preserves it; org_report_snapshot_dir_key(key)
    # recomputes a new digest — they are NOT equal, so we get two candidates.
    # To actually hit L128 we need preferred == legacy.  The only way that happens
    # is if org_report_snapshot_dir_key(x) == snapshot_slug(x).  We verify the
    # two-tuple path is the normal case, then use monkeypatching to hit the branch.
    assert len(candidates) == 2  # normal case: preferred != legacy


def test_org_report_snapshot_dir_candidates_single_when_preferred_equals_legacy(monkeypatch):
    """L128: when preferred slug == legacy slug, return a single-element tuple."""
    import cja_auto_sdr.org.snapshot_utils as su

    monkeypatch.setattr(su, "org_report_snapshot_dir_key", lambda org_id: "same_slug")
    monkeypatch.setattr(su, "snapshot_slug", lambda org_id, **kw: "same_slug")

    candidates = su.org_report_snapshot_dir_candidates("anything")
    assert candidates == ("same_slug",)


# ---------------------------------------------------------------------------
# L147: _dedupe_paths — skip already-seen path
# ---------------------------------------------------------------------------


def test_dedupe_paths_skips_duplicate_paths(tmp_path):
    """L147: duplicate paths (same resolved location) are skipped."""
    from cja_auto_sdr.org.snapshot_utils import _dedupe_paths

    p = tmp_path / "file.json"
    p.touch()
    # Pass the same path twice — second occurrence should be dropped.
    result = _dedupe_paths([p, p])
    assert len(result) == 1


# ---------------------------------------------------------------------------
# L160: org_report_snapshot_dir_paths — non-existent root returns ()
# ---------------------------------------------------------------------------


def test_org_report_snapshot_dir_paths_returns_empty_for_nonexistent_root(tmp_path):
    """L160: when snapshot_root does not exist, return empty tuple."""
    nonexistent = tmp_path / "no_such_dir"
    result = org_report_snapshot_dir_paths(nonexistent)
    assert result == ()


def test_org_report_snapshot_dir_paths_returns_empty_for_file_root(tmp_path):
    """L160: when snapshot_root is a file (not a dir), return empty tuple."""
    file_root = tmp_path / "not_a_dir.txt"
    file_root.write_text("x")
    result = org_report_snapshot_dir_paths(file_root)
    assert result == ()


# ---------------------------------------------------------------------------
# L181-183: org_report_snapshot_dedupe_key — snapshot_id and fallback modes
# ---------------------------------------------------------------------------


def test_org_report_snapshot_dedupe_key_snapshot_id_mode():
    """L181-182: when content_hash is absent but snapshot_id is present."""
    key = org_report_snapshot_dedupe_key(org_id="org1", snapshot_id="snap-42")
    assert key[0] == "snapshot_id"
    assert key[2] == "snap-42"


def test_org_report_snapshot_dedupe_key_fallback_mode():
    """L183: when both content_hash and snapshot_id are absent."""
    key = org_report_snapshot_dedupe_key(org_id="org1", generated_at="2026-01-01T00:00:00Z")
    assert key[0] == "fallback"
    assert "2026-01-01T00:00:00Z" in key


# ---------------------------------------------------------------------------
# L190: org_report_snapshot_source_rank — empty path returns 0
# ---------------------------------------------------------------------------


def test_org_report_snapshot_source_rank_empty_path_returns_zero():
    """L190: when source_path is None/empty, rank is 0."""
    assert org_report_snapshot_source_rank(None) == 0
    assert org_report_snapshot_source_rank("") == 0


# ---------------------------------------------------------------------------
# L246: iter_org_report_snapshot_files — glob loop skips seen paths
# ---------------------------------------------------------------------------


def test_iter_org_report_snapshot_files_deduplicates_across_dirs(tmp_path, monkeypatch):
    """L246: the same JSON file path seen twice is only returned once."""
    import cja_auto_sdr.org.snapshot_utils as su

    snapshot_dir = tmp_path / "snap_dir"
    snapshot_dir.mkdir()
    snap_file = snapshot_dir / "report.json"
    snap_file.write_text("{}")

    # Return the same directory twice from search_dirs to trigger the dedup branch.
    monkeypatch.setattr(su, "org_report_snapshot_search_dirs", lambda *a, **kw: (snapshot_dir, snapshot_dir))

    result = su.iter_org_report_snapshot_files(tmp_path)
    assert result.count(snap_file.resolve()) == 1


# ---------------------------------------------------------------------------
# L282, L287-288: coerce_snapshot_bool — numeric and string false variants
# ---------------------------------------------------------------------------


def test_coerce_snapshot_bool_int_and_float():
    """L282: int/float values are coerced to bool."""
    assert coerce_snapshot_bool(1) is True
    assert coerce_snapshot_bool(0) is False
    assert coerce_snapshot_bool(3.14) is True
    assert coerce_snapshot_bool(0.0) is False


def test_coerce_snapshot_bool_string_false_variants():
    """L287-288: string false variants return False."""
    for val in ("0", "false", "no", "n", "off", "skipped", "partial", "incomplete"):
        assert coerce_snapshot_bool(val) is False, f"Expected False for {val!r}"
    # True variants still work
    for val in ("1", "true", "yes", "y", "on", "complete", "full"):
        assert coerce_snapshot_bool(val) is True, f"Expected True for {val!r}"


# ---------------------------------------------------------------------------
# L336: _derived_org_report_snapshot_history_assessment — similarity_analysis_mode="partial"
# ---------------------------------------------------------------------------


def test_derived_history_assessment_similarity_analysis_mode_non_complete():
    """L336: when similarity_analysis_mode is set but complete flag absent, use mode."""
    # Mode "partial" is not "complete", so eligible=False, exclusion_reason="partial"
    result = org_report_snapshot_history_exclusion_reason(
        {
            "summary": {
                "similarity_analysis_mode": "partial",
            }
        }
    )
    assert result == "partial"


def test_derived_history_assessment_similarity_analysis_mode_complete():
    """L336-340: when similarity_analysis_mode is 'complete', eligible=True."""
    assert (
        org_report_snapshot_history_eligible(
            {
                "summary": {
                    "similarity_analysis_mode": "complete",
                }
            }
        )
        is True
    )


# ---------------------------------------------------------------------------
# L344: _derived — org_stats_only=True
# ---------------------------------------------------------------------------


def test_derived_history_assessment_org_stats_only():
    """L344: when parameters.org_stats_only is True, ineligible with org_stats_only reason."""
    result = org_report_snapshot_history_exclusion_reason(
        {
            "parameters": {"org_stats_only": True},
        }
    )
    assert result == "org_stats_only"


# ---------------------------------------------------------------------------
# L357: _derived — similarity_pairs explicitly null
# ---------------------------------------------------------------------------


def test_derived_history_assessment_similarity_pairs_explicitly_null():
    """L357: when 'similarity_pairs' key exists but is None, ineligible."""
    result = org_report_snapshot_history_exclusion_reason(
        {
            "similarity_pairs": None,
        }
    )
    assert result == "similarity_incomplete"


# ---------------------------------------------------------------------------
# L407-420: coerce_snapshot_int — bool/float/string/ValueError
# ---------------------------------------------------------------------------


def test_coerce_snapshot_int_bool_to_int():
    """L407: bool values convert to int (True->1, False->0)."""
    assert coerce_snapshot_int(True) == 1
    assert coerce_snapshot_int(False) == 0


def test_coerce_snapshot_int_float_to_int():
    """L410-411: float values are truncated to int."""
    assert coerce_snapshot_int(3.9) == 3
    assert coerce_snapshot_int(0.0) == 0


def test_coerce_snapshot_int_string_valid():
    """L412-417: string digits coerce to int."""
    assert coerce_snapshot_int("42") == 42
    assert coerce_snapshot_int("  7  ") == 7


def test_coerce_snapshot_int_string_invalid_returns_none():
    """L418-419: non-numeric string returns None."""
    assert coerce_snapshot_int("abc") is None
    assert coerce_snapshot_int("") is None


# ---------------------------------------------------------------------------
# L426-437: coerce_snapshot_float — bool/string/ValueError
# ---------------------------------------------------------------------------


def test_coerce_snapshot_float_bool_to_float():
    """L425-426: bool converts to float."""
    assert coerce_snapshot_float(True) == 1.0
    assert coerce_snapshot_float(False) == 0.0


def test_coerce_snapshot_float_string_valid():
    """L429-434: string floats coerce correctly."""
    assert coerce_snapshot_float("3.14") == pytest.approx(3.14)
    assert coerce_snapshot_float("  2  ") == pytest.approx(2.0)


def test_coerce_snapshot_float_string_invalid_returns_none():
    """L435-436: non-numeric string returns None."""
    assert coerce_snapshot_float("nope") is None
    assert coerce_snapshot_float("") is None


# ---------------------------------------------------------------------------
# L477: is_org_report_snapshot_payload — non-Mapping returns False
# ---------------------------------------------------------------------------


def test_is_org_report_snapshot_payload_non_mapping_returns_false():
    """L477: list, string, int, None all return False."""
    assert is_org_report_snapshot_payload([]) is False
    assert is_org_report_snapshot_payload("string") is False
    assert is_org_report_snapshot_payload(42) is False
    assert is_org_report_snapshot_payload(None) is False


# ---------------------------------------------------------------------------
# L598: normalized_similarity_pair_ids — no valid dv1/dv2 IDs
# ---------------------------------------------------------------------------


def test_normalized_similarity_pair_ids_returns_none_when_ids_missing():
    """L598: when neither dv1_id nor nested data_view_1.id are present, return None."""
    assert normalized_similarity_pair_ids({}) is None
    assert normalized_similarity_pair_ids({"dv1_id": "", "dv2_id": ""}) is None
    assert normalized_similarity_pair_ids({"dv1_id": "a"}) is None  # dv2 missing


@pytest.mark.parametrize("blank_value", ["", "   ", None])
def test_normalized_similarity_pair_ids_fall_back_from_blank_flat_ids_to_nested_ids(blank_value):
    assert normalized_similarity_pair_ids(
        {
            "dv1_id": blank_value,
            "dv2_id": blank_value,
            "data_view_1": {"id": " dv1 "},
            "data_view_2": {"id": "dv2"},
        }
    ) == ("dv1", "dv2")


@pytest.mark.parametrize(
    "pair",
    [
        {"dv1_id": "dv1", "dv2_id": " dv1 "},
        {
            "dv1_id": "",
            "dv2_id": "   ",
            "data_view_1": {"id": "dv1"},
            "data_view_2": {"id": " dv1 "},
        },
    ],
)
def test_normalized_similarity_pair_ids_rejects_collapsed_self_pairs(pair):
    assert normalized_similarity_pair_ids(pair) is None


def test_org_report_high_similarity_pairs_ignores_collapsed_self_pairs():
    payload = {
        "similarity_pairs": [
            {
                "dv1_id": "",
                "dv2_id": "   ",
                "data_view_1": {"id": "dv1"},
                "data_view_2": {"id": " dv1 "},
                "jaccard_similarity": 0.97,
            }
        ]
    }

    assert org_report_high_similarity_pairs(payload) == set()


# ---------------------------------------------------------------------------
# L604: effective_org_report_data_view_count — fallback when no raw data_views
# ---------------------------------------------------------------------------


def test_effective_org_report_data_view_count_fallback_no_data_views():
    """L604: when no summary count and no data_views array, returns 0."""
    assert effective_org_report_data_view_count({}) == 0


# ---------------------------------------------------------------------------
# L617: reported_org_report_data_view_count — no count summary and no array
# ---------------------------------------------------------------------------


def test_reported_org_report_data_view_count_returns_none_when_absent():
    """L617: no summary totals and no data_views list returns None."""
    assert reported_org_report_data_view_count({}) is None
    assert reported_org_report_data_view_count({"summary": {}}) is None


def test_reported_org_report_data_view_count_returns_len_when_array_present():
    """L614-616: when data_views list present, returns its length."""
    data = {"data_views": [{"id": "dv1"}, {"id": "dv2"}]}
    assert reported_org_report_data_view_count(data) == 2


# ---------------------------------------------------------------------------
# L659: org_report_high_similarity_pairs — non-Mapping pair skipped
# ---------------------------------------------------------------------------


def test_org_report_high_similarity_pairs_skips_non_mapping_entries():
    """L659: items in similarity_pairs that are not Mapping are silently skipped."""
    data = {
        "similarity_pairs": [
            "not_a_dict",
            42,
            None,
            {"dv1_id": "a", "dv2_id": "b", "jaccard_similarity": 0.95},
        ]
    }
    result = org_report_high_similarity_pairs(data)
    assert result == {("a", "b")}


# ---------------------------------------------------------------------------
# L676: org_report_snapshot_comparison_input — missing metadata raises ValueError
# ---------------------------------------------------------------------------


def test_org_report_snapshot_comparison_input_raises_for_non_snapshot():
    """L676: data that is not an org-report payload raises ValueError."""
    with pytest.raises(ValueError, match="expected org-report snapshot payload"):
        org_report_snapshot_comparison_input({})


@pytest.mark.parametrize("payload", [([1, 2, 3],), ("snapshot",), (7,), (None,)])
def test_org_report_snapshot_comparison_input_raises_for_non_mapping_root(payload):
    with pytest.raises(ValueError, match="expected org-report snapshot payload"):
        org_report_snapshot_comparison_input(payload)


# ---------------------------------------------------------------------------
# L687: org_report_snapshot_comparison_input — data view missing id fields skipped
# ---------------------------------------------------------------------------


def test_org_report_snapshot_comparison_input_skips_dv_rows_with_no_id():
    """L687: data-view rows without id or data_view_id are silently skipped."""
    payload = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "test_org",
        "report_type": "org_analysis",
        "summary": {
            "data_views_total": 2,
            "data_views_analyzed": 1,
            "total_unique_components": 0,
            "similarity_analysis_complete": True,
        },
        "distribution": {
            "core": {"total": 0},
            "isolated": {"total": 0},
        },
        "data_views": [
            {"data_view_name": "No ID row"},  # missing id and data_view_id
            {"id": "dv_ok", "data_view_name": "Has ID"},
        ],
        "similarity_pairs": [],
    }
    result = org_report_snapshot_comparison_input(payload, require_history_eligible=False)
    assert "dv_ok" in result.data_view_ids
    assert len(result.data_view_ids) == 1
    assert result.complete_data_view_ids is False


def test_org_report_snapshot_comparison_input_allows_skip_similarity_payloads():
    payload = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "test_org",
        "report_type": "org_analysis",
        "summary": {
            "data_views_total": 2,
            "data_views_analyzed": 2,
            "total_unique_components": 4,
            "similarity_analysis_complete": False,
            "similarity_analysis_mode": "skip_similarity",
        },
        "distribution": {
            "core": {"total": 1},
            "isolated": {"total": 0},
        },
        "data_views": [
            {"id": "dv_1", "data_view_name": "DV 1", "error": None},
            {"id": "dv_2", "data_view_name": "DV 2", "error": None},
        ],
        "similarity_pairs": [],
    }

    result = org_report_snapshot_comparison_input(
        payload,
        require_history_eligible=False,
        require_comparison_eligible=True,
    )

    assert result.data_view_ids == {"dv_1", "dv_2"}
    assert result.complete_data_view_ids is True
    assert result.complete_high_similarity_pairs is False


# ---------------------------------------------------------------------------
# Additional coverage for remaining uncovered branches
# ---------------------------------------------------------------------------

# L134-137: sorted_snapshot_strings with limit
# ---------------------------------------------------------------------------


def test_sorted_snapshot_strings_with_limit():
    """L134-137: sorted_snapshot_strings respects the limit parameter."""
    from cja_auto_sdr.org.snapshot_utils import sorted_snapshot_strings

    result = sorted_snapshot_strings(["c", "a", "b"], limit=2)
    assert result == ["a", "b"]

    result_no_limit = sorted_snapshot_strings(["c", "a", "b"])
    assert result_no_limit == ["a", "b", "c"]


# L157: org_report_snapshot_dir_paths with org_id specified
# ---------------------------------------------------------------------------


def test_org_report_snapshot_dir_paths_with_org_id(tmp_path):
    """L157: when org_id is provided, return candidate directories under root."""
    result = org_report_snapshot_dir_paths(tmp_path, org_id="myorg")
    assert len(result) >= 1
    # All returned paths should be under tmp_path
    for path in result:
        assert str(path).startswith(str(tmp_path))


# L161: org_report_snapshot_dir_paths — iterdir listing
# ---------------------------------------------------------------------------


def test_org_report_snapshot_dir_paths_lists_subdirs(tmp_path):
    """L161: existing root directory returns sorted subdirectory paths."""
    sub1 = tmp_path / "aaa"
    sub2 = tmp_path / "bbb"
    sub1.mkdir()
    sub2.mkdir()
    (tmp_path / "file.json").write_text("{}")  # files should be excluded

    result = org_report_snapshot_dir_paths(tmp_path)
    assert sub1 in result
    assert sub2 in result
    # Files not included
    assert all(p.is_dir() for p in result)


# L166: is_org_report_snapshot_root_dir
# ---------------------------------------------------------------------------


def test_is_org_report_snapshot_root_dir():
    """L166: identifies the canonical snapshot root dir by name."""
    from cja_auto_sdr.org.snapshot_utils import (
        ORG_REPORT_SNAPSHOT_ROOT_DIRNAME,
        is_org_report_snapshot_root_dir,
    )

    assert is_org_report_snapshot_root_dir(f"/some/path/{ORG_REPORT_SNAPSHOT_ROOT_DIRNAME}") is True
    assert is_org_report_snapshot_root_dir("/some/other/path") is False


# L180: org_report_snapshot_dedupe_key with content_hash
# ---------------------------------------------------------------------------


def test_org_report_snapshot_dedupe_key_content_hash_mode():
    """L180: when content_hash is present, use content_hash mode."""
    key = org_report_snapshot_dedupe_key(org_id="org1", content_hash="abc123")
    assert key[0] == "content_hash"
    assert key[2] == "abc123"


# L192-197: org_report_snapshot_source_rank with path that matches a candidate
# ---------------------------------------------------------------------------


def test_org_report_snapshot_source_rank_matching_path(tmp_path):
    """L192-197: path whose parent matches the preferred candidate gets a non-zero rank."""
    from cja_auto_sdr.org.snapshot_utils import org_report_snapshot_dir_key

    org_id = "myorg"
    dir_key = org_report_snapshot_dir_key(org_id)
    candidate_dir = tmp_path / dir_key
    candidate_dir.mkdir()
    snap_file = candidate_dir / "report.json"
    snap_file.touch()

    rank = org_report_snapshot_source_rank(snap_file, org_id)
    assert rank > 0


def test_org_report_snapshot_source_rank_non_matching_path(tmp_path):
    """L197: path whose parent does not match any candidate returns 0."""
    snap_file = tmp_path / "some_other_dir" / "report.json"
    rank = org_report_snapshot_source_rank(snap_file, "myorg")
    assert rank == 0


# L207: org_report_snapshot_preference_key
# ---------------------------------------------------------------------------


def test_org_report_snapshot_preference_key():
    """L207: preference key combines source rank and snapshot_id presence."""
    from cja_auto_sdr.org.snapshot_utils import org_report_snapshot_preference_key

    key_with_id = org_report_snapshot_preference_key(snapshot_id="snap-1")
    key_without_id = org_report_snapshot_preference_key()
    assert key_with_id[1] == 1
    assert key_without_id[1] == 0


# L221-232: org_report_snapshot_search_dirs various branches
# ---------------------------------------------------------------------------


def test_org_report_snapshot_search_dirs_generic_dir_no_org_id(tmp_path):
    """L225: cache dir without root-dir name and no org_id → returns (cache_path,)."""
    from cja_auto_sdr.org.snapshot_utils import org_report_snapshot_search_dirs

    result = org_report_snapshot_search_dirs(tmp_path)
    assert result == (tmp_path,)


def test_org_report_snapshot_search_dirs_snapshot_root_no_org_id(tmp_path):
    """L223-224: when cache dir is the snapshot root dir and org_id is None, list subdirs."""
    from cja_auto_sdr.org.snapshot_utils import (
        ORG_REPORT_SNAPSHOT_ROOT_DIRNAME,
        org_report_snapshot_search_dirs,
    )

    root = tmp_path / ORG_REPORT_SNAPSHOT_ROOT_DIRNAME
    root.mkdir()
    sub = root / "org_dir"
    sub.mkdir()

    result = org_report_snapshot_search_dirs(root)
    assert sub in result


def test_org_report_snapshot_search_dirs_snapshot_root_with_org_id(tmp_path):
    """L228-229: snapshot root + org_id → returns per-org candidate dirs."""
    from cja_auto_sdr.org.snapshot_utils import (
        ORG_REPORT_SNAPSHOT_ROOT_DIRNAME,
        org_report_snapshot_search_dirs,
    )

    root = tmp_path / ORG_REPORT_SNAPSHOT_ROOT_DIRNAME
    root.mkdir()

    result = org_report_snapshot_search_dirs(root, org_id="myorg")
    assert len(result) >= 1
    for p in result:
        assert str(p).startswith(str(root))


def test_org_report_snapshot_search_dirs_candidate_dir_with_org_id(tmp_path):
    """L230-231: when cache dir is a candidate name dir, dedupe and return siblings."""
    from cja_auto_sdr.org.snapshot_utils import (
        org_report_snapshot_dir_key,
        org_report_snapshot_search_dirs,
    )

    org_id = "myorg"
    dir_key = org_report_snapshot_dir_key(org_id)
    candidate_dir = tmp_path / dir_key
    candidate_dir.mkdir()

    result = org_report_snapshot_search_dirs(candidate_dir, org_id=org_id)
    assert len(result) >= 1


def test_org_report_snapshot_search_dirs_generic_dir_with_org_id(tmp_path):
    """L232: non-root, non-candidate dir with org_id → returns (cache_path,)."""
    from cja_auto_sdr.org.snapshot_utils import org_report_snapshot_search_dirs

    plain_dir = tmp_path / "plain_cache"
    plain_dir.mkdir()

    result = org_report_snapshot_search_dirs(plain_dir, org_id="myorg")
    assert result == (plain_dir,)


# L242: iter_org_report_snapshot_files skips non-dir entries
# ---------------------------------------------------------------------------


def test_iter_org_report_snapshot_files_skips_nonexistent_dirs(tmp_path, monkeypatch):
    """L242: search dirs that don't exist are skipped silently."""
    import cja_auto_sdr.org.snapshot_utils as su

    nonexistent = tmp_path / "does_not_exist"
    # Return a non-existent dir — should be skipped without error
    monkeypatch.setattr(su, "org_report_snapshot_search_dirs", lambda *a, **kw: (nonexistent,))

    result = su.iter_org_report_snapshot_files(tmp_path)
    assert result == ()


# L420: coerce_snapshot_int non-matching type returns None
# ---------------------------------------------------------------------------


def test_coerce_snapshot_int_non_matching_type_returns_none():
    """L420: types other than bool/int/float/str return None."""
    assert coerce_snapshot_int([1, 2]) is None
    assert coerce_snapshot_int({"v": 1}) is None
    assert coerce_snapshot_int(None) is None


# L437: coerce_snapshot_float non-matching type returns None
# ---------------------------------------------------------------------------


def test_coerce_snapshot_float_non_matching_type_returns_none():
    """L437: types other than bool/int/float/str return None."""
    assert coerce_snapshot_float([1.0]) is None
    assert coerce_snapshot_float(None) is None


# L462: snapshot_mapping_list non-list returns []
# ---------------------------------------------------------------------------


def test_snapshot_mapping_list_returns_empty_for_non_list():
    """L462: non-list values return an empty list."""
    from cja_auto_sdr.org.snapshot_utils import snapshot_mapping_list

    assert snapshot_mapping_list(None) == []
    assert snapshot_mapping_list({}) == []
    assert snapshot_mapping_list("string") == []


# L535: org_report_data_view_row_has_error non-dict returns True
# ---------------------------------------------------------------------------


def test_org_report_data_view_row_has_error_non_dict_returns_true():
    """L535: non-dict values are treated as error rows."""
    from cja_auto_sdr.org.snapshot_utils import org_report_data_view_row_has_error

    assert org_report_data_view_row_has_error("not_a_dict") is True
    assert org_report_data_view_row_has_error(42) is True
    assert org_report_data_view_row_has_error(None) is True


# L632, L644: org_report_core_count / org_report_isolated_count fallback paths
# ---------------------------------------------------------------------------


def test_org_report_core_count_fallback_metrics_and_dimensions():
    """L632: when 'total' key absent, sum metrics_count + dimensions_count."""
    from cja_auto_sdr.org.snapshot_utils import org_report_core_count

    data = {"distribution": {"core": {"metrics_count": 3, "dimensions_count": 2}}}
    assert org_report_core_count(data) == 5


def test_org_report_isolated_count_fallback_metrics_and_dimensions():
    """L644: when 'total' key absent, sum metrics_count + dimensions_count."""
    from cja_auto_sdr.org.snapshot_utils import org_report_isolated_count

    data = {"distribution": {"isolated": {"metrics_count": 1, "dimensions_count": 4}}}
    assert org_report_isolated_count(data) == 5


# L661: org_report_high_similarity_pairs below-threshold pairs are skipped
# ---------------------------------------------------------------------------


def test_org_report_high_similarity_pairs_skips_below_threshold():
    """L661: pairs with jaccard_similarity below threshold are not included."""
    data = {
        "similarity_pairs": [
            {"dv1_id": "a", "dv2_id": "b", "jaccard_similarity": 0.5},
            {"dv1_id": "c", "dv2_id": "d", "jaccard_similarity": 0.95},
        ]
    }
    result = org_report_high_similarity_pairs(data, threshold=0.9)
    assert ("c", "d") in result
    assert ("a", "b") not in result


# L680: org_report_snapshot_comparison_input raises when history ineligible
# ---------------------------------------------------------------------------


def test_org_report_snapshot_comparison_input_raises_when_history_ineligible():
    """L680: when require_history_eligible=True and snapshot is excluded, raise ValueError."""
    payload = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "test_org",
        "report_type": "org_analysis",
        "summary": {
            "data_views_total": 1,
            "data_views_analyzed": 1,
            "total_unique_components": 0,
            "is_sampled": True,
        },
        "distribution": {"core": {"total": 0}, "isolated": {"total": 0}},
        "data_views": [],
        "similarity_pairs": [],
    }
    with pytest.raises(ValueError, match="snapshot is not eligible for comparison"):
        org_report_snapshot_comparison_input(payload, require_history_eligible=True)


# L694: org_report_snapshot_comparison_input with component_index
# ---------------------------------------------------------------------------


def test_org_report_snapshot_comparison_input_extracts_component_ids():
    """L694: when component_index is a dict, extract component_ids."""
    payload = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "test_org",
        "report_type": "org_analysis",
        "summary": {
            "data_views_total": 1,
            "data_views_analyzed": 1,
            "total_unique_components": 2,
            "similarity_analysis_complete": True,
        },
        "distribution": {"core": {"total": 1}, "isolated": {"total": 1}},
        "data_views": [{"id": "dv1", "data_view_name": "DV One"}],
        "component_index": {"comp_a": {}, "comp_b": {}},
        "similarity_pairs": [],
    }
    result = org_report_snapshot_comparison_input(payload, require_history_eligible=False)
    assert result.component_ids == {"comp_a", "comp_b"}


def test_org_report_snapshot_comparison_input_uses_all_known_data_view_ids():
    payload = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "test_org",
        "report_type": "org_analysis",
        "summary": {
            "data_views_total": 2,
            "data_views_analyzed": 1,
            "total_unique_components": 0,
            "similarity_analysis_complete": True,
        },
        "distribution": {"core": {"total": 0}, "isolated": {"total": 0}},
        "data_views": [
            {"id": "dv_ok", "data_view_name": "Healthy", "error": None},
            {"id": "dv_err", "data_view_name": "Errored", "error": "timeout"},
        ],
        "similarity_pairs": [],
    }

    result = org_report_snapshot_comparison_input(payload, require_history_eligible=False)
    assert result.data_view_ids == {"dv_ok", "dv_err"}
    assert result.complete_data_view_ids is True


def test_org_report_snapshot_comparison_input_normalizes_whitespace_data_view_ids():
    payload = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "test_org",
        "report_type": "org_analysis",
        "summary": {
            "data_views_total": 1,
            "data_views_analyzed": 1,
            "total_unique_components": 0,
            "similarity_analysis_complete": True,
        },
        "distribution": {"core": {"total": 0}, "isolated": {"total": 0}},
        "data_views": [{"id": " dv_ok ", "data_view_name": "Healthy", "error": None}],
        "similarity_pairs": [],
    }

    result = org_report_snapshot_comparison_input(payload, require_history_eligible=False)
    assert result.data_view_ids == {"dv_ok"}
    assert result.data_view_names == {"dv_ok": "Healthy"}


def test_org_report_snapshot_has_complete_data_view_ids_rejects_missing_ids():
    payload = {
        "summary": {"data_views_total": 2},
        "data_views": [{"id": "dv1"}, {"data_view_name": "Missing ID"}],
    }

    assert org_report_snapshot_has_complete_data_view_ids(payload) is False


def test_org_report_snapshot_has_complete_data_view_ids_rejects_count_contradictions():
    payload = {
        "summary": {"data_views_total": 3, "data_views_analyzed": 3},
        "data_views": [{"id": "dv1"}, {"id": "dv2"}],
    }

    assert org_report_snapshot_has_complete_data_view_ids(payload) is False


def test_org_report_snapshot_has_complete_data_view_ids_rejects_normalized_duplicates():
    payload = {
        "summary": {"data_views_total": 2, "data_views_analyzed": 2},
        "data_views": [{"id": "dv1"}, {"data_view_id": " dv1 "}],
    }

    assert org_report_snapshot_has_complete_data_view_ids(payload) is False


# L752-760: org_report_snapshot_metadata with include_data_views=True
# ---------------------------------------------------------------------------


def test_org_report_snapshot_metadata_include_data_views():
    """L752-760: include_data_views=True adds data_view_names_preview and related keys."""
    from cja_auto_sdr.org.snapshot_utils import org_report_snapshot_metadata

    payload = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "test_org",
        "report_type": "org_analysis",
        "summary": {
            "data_views_total": 2,
            "total_unique_components": 3,
            "similarity_analysis_complete": True,
        },
        "distribution": {"core": {"total": 2}, "isolated": {"total": 1}},
        "data_views": [
            {"id": "dv1", "name": "DV One"},
            {"id": "dv2", "data_view_name": "DV Two"},
        ],
        "similarity_pairs": [],
    }
    metadata = org_report_snapshot_metadata(payload, include_data_views=True)
    assert metadata is not None
    assert "data_view_names_preview" in metadata
    assert "data_view_names_total" in metadata
    assert "data_view_names_truncated" in metadata
    assert metadata["data_view_names_total"] == 2
    assert metadata["data_view_names_truncated"] is False


def test_org_report_snapshot_metadata_reuses_provided_state(monkeypatch):
    import cja_auto_sdr.org.snapshot_utils as snapshot_utils

    payload = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "test_org",
        "report_type": "org_analysis",
        "summary": {
            "data_views_total": 2,
            "total_unique_components": 3,
            "similarity_analysis_complete": True,
        },
        "distribution": {"core": {"total": 2}, "isolated": {"total": 1}},
        "data_views": [
            {"id": "dv1", "name": "DV One"},
            {"id": "dv2", "data_view_name": "DV Two"},
        ],
        "similarity_pairs": [],
    }
    state = snapshot_utils._org_report_snapshot_state(payload)

    def fail_if_rebuilt(_data, **_kwargs):
        raise AssertionError("org_report_snapshot_metadata rebuilt snapshot state")

    monkeypatch.setattr(snapshot_utils, "_org_report_snapshot_state", fail_if_rebuilt)

    metadata = snapshot_utils.org_report_snapshot_metadata(payload, state=state, include_data_views=True)

    assert metadata is not None
    assert metadata["generated_at"] == "2026-03-01T00:00:00Z"
    assert metadata["data_view_names_preview"] == ["DV One", "DV Two"]


def test_org_report_snapshot_history_assessment_skips_heavy_extractors(monkeypatch):
    import cja_auto_sdr.org.snapshot_utils as snapshot_utils

    payload = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "test_org",
        "report_type": "org_analysis",
        "summary": {
            "data_views_total": 2,
            "total_unique_components": 3,
            "similarity_analysis_complete": False,
            "similarity_analysis_mode": "org_stats_only",
        },
        "distribution": {"core": {"total": 2}, "isolated": {"total": 1}},
        "component_index": {
            "comp_1": {"data_views": ["dv1"]},
            "comp_2": {"data_views": ["dv2"]},
        },
        "similarity_pairs": [
            {"dv1_id": "dv1", "dv2_id": "dv2", "jaccard_similarity": 0.99},
        ],
    }

    def fail_component_ids(_raw_component_index):
        raise AssertionError("history assessment extracted component ids")

    def fail_similarity_pairs(_rows, *, threshold=0.9):
        raise AssertionError(f"history assessment extracted similarity pairs at threshold {threshold}")

    monkeypatch.setattr(snapshot_utils, "_snapshot_component_ids", fail_component_ids)
    monkeypatch.setattr(snapshot_utils, "_org_report_high_similarity_pairs_from_rows", fail_similarity_pairs)

    history = snapshot_utils.org_report_snapshot_history_assessment(payload)

    assert history.eligible is False
    assert history.exclusion_reason == "org_stats_only"


def test_org_report_snapshot_metadata_uses_precomputed_similarity_pairs_from_state(monkeypatch):
    import cja_auto_sdr.org.snapshot_utils as snapshot_utils

    payload = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "test_org",
        "report_type": "org_analysis",
        "summary": {
            "data_views_total": 2,
            "total_unique_components": 3,
            "similarity_analysis_complete": True,
        },
        "distribution": {"core": {"total": 2}, "isolated": {"total": 1}},
        "data_views": [
            {"id": "dv1", "name": "DV One"},
            {"id": "dv2", "data_view_name": "DV Two"},
        ],
        "similarity_pairs": [
            {"dv1_id": "dv1", "dv2_id": "dv2", "jaccard_similarity": 0.99},
        ],
    }
    state = snapshot_utils._org_report_snapshot_state(payload, include_high_similarity_pairs=True)

    def fail_if_rescanned(_rows, *, threshold=0.9):
        raise AssertionError(f"metadata rescanned similarity pairs at threshold {threshold}")

    monkeypatch.setattr(snapshot_utils, "_org_report_high_similarity_pairs_from_rows", fail_if_rescanned)

    metadata = snapshot_utils.org_report_snapshot_metadata(payload, state=state)

    assert metadata is not None
    assert metadata["high_similarity_pairs"] == 1


def test_org_report_snapshot_metadata_include_data_views_truncates_long_list():
    """L760: when more than 10 data views, data_view_names_truncated is True."""
    from cja_auto_sdr.org.snapshot_utils import org_report_snapshot_metadata

    payload = {
        "generated_at": "2026-03-01T00:00:00Z",
        "org_id": "test_org",
        "report_type": "org_analysis",
        "summary": {
            "data_views_total": 12,
            "total_unique_components": 0,
            "similarity_analysis_complete": True,
        },
        "distribution": {"core": {"total": 0}, "isolated": {"total": 0}},
        "data_views": [{"id": f"dv{i}", "name": f"DV {i}"} for i in range(12)],
        "similarity_pairs": [],
    }
    metadata = org_report_snapshot_metadata(payload, include_data_views=True)
    assert metadata is not None
    assert metadata["data_view_names_truncated"] is True
    assert len(metadata["data_view_names_preview"]) == 10
