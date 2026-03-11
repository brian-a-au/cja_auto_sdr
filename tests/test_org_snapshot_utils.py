"""Direct unit tests for org snapshot helper utilities."""

from __future__ import annotations

from datetime import UTC
from pathlib import Path

from cja_auto_sdr.org.snapshot_utils import (
    chronological_snapshot_sort_fields,
    newest_first_snapshot_sort_fields,
    org_report_snapshot_content_hash,
    org_report_snapshot_data_view_stats,
    org_report_snapshot_dir_candidates,
    org_report_snapshot_dir_key,
    org_report_snapshot_history_eligible,
    org_report_snapshot_history_exclusion_reason,
    parse_snapshot_timestamp,
    snapshot_epoch,
    snapshot_identity_tokens,
    snapshot_path_text,
    snapshot_slug,
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
