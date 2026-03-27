"""Focused compatibility contracts for org writer alias routing."""

from __future__ import annotations

import importlib

from cja_auto_sdr.org.writers.compat import override_scope


def _recommendation_reasons(data: dict[str, object]) -> list[str]:
    return [str(rec.get("reason", "")) for rec in data["recommendations"]]


def test_canonical_json_builder_helper_proxy_supports_self_delegating_override_scope(
    rich_org_report_result,
):
    """Canonical writer-module helper proxies must allow wrapper-style self overrides."""
    mod = importlib.import_module("cja_auto_sdr.org.writers.json")
    calls: list[str] = []

    def custom(rec):
        calls.append(str(rec.get("reason", "")))
        return mod._normalize_recommendation_for_json(rec)

    with override_scope(
        mod.__name__,
        {
            "_normalize_recommendation_for_json": custom,
        },
    ):
        payload = mod.build_org_report_json_data(rich_org_report_result)

    assert payload["org_id"] == rich_org_report_result.org_id
    assert calls == [
        "A data view has many isolated components",
        "Two data views are highly similar",
    ]


def test_generator_json_builder_supports_self_delegating_override_scope(rich_org_report_result):
    """Generator wrapped writer exports must allow wrapper-style self overrides."""
    mod = importlib.import_module("cja_auto_sdr.generator")
    calls: list[str] = []

    def custom(result, trending=None):
        calls.append(result.org_id)
        return mod.build_org_report_json_data(result, trending=trending)

    with override_scope(
        mod.__name__,
        {
            "build_org_report_json_data": custom,
        },
    ):
        payload = mod.build_org_report_json_data(rich_org_report_result)

    assert payload["org_id"] == rich_org_report_result.org_id
    assert calls == [rich_org_report_result.org_id]


def test_org_writers_json_builder_supports_self_delegating_override_scope(rich_org_report_result):
    """Legacy package-root writer exports must allow wrapper-style self overrides."""
    mod = importlib.import_module("cja_auto_sdr.org.writers")
    calls: list[str] = []

    def custom(result, trending=None):
        calls.append(result.org_id)
        return mod.build_org_report_json_data(result, trending=trending)

    with override_scope(
        mod.__name__,
        {
            "build_org_report_json_data": custom,
        },
    ):
        payload = mod.build_org_report_json_data(rich_org_report_result)

    assert payload["org_id"] == rich_org_report_result.org_id
    assert calls == [rich_org_report_result.org_id]


def test_generator_json_builder_supports_source_scope_helper_projection(rich_org_report_result):
    """Generator helper override_scope values must project into canonical JSON builder calls."""
    mod = importlib.import_module("cja_auto_sdr.generator")

    with override_scope(
        mod.__name__,
        {
            "_normalize_recommendation_for_json": lambda _rec: {
                "severity": "low",
                "reason": "generator-scoped recommendation",
            },
        },
    ):
        payload = mod.build_org_report_json_data(rich_org_report_result)

    assert _recommendation_reasons(payload) == [
        "generator-scoped recommendation",
        "generator-scoped recommendation",
    ]


def test_org_writers_json_builder_supports_source_scope_helper_projection(rich_org_report_result):
    """Package-root helper override_scope values must project into canonical JSON builder calls."""
    mod = importlib.import_module("cja_auto_sdr.org.writers")

    with override_scope(
        mod.__name__,
        {
            "_normalize_recommendation_for_json": lambda _rec: {
                "severity": "low",
                "reason": "package-root recommendation",
            },
        },
    ):
        payload = mod.build_org_report_json_data(rich_org_report_result)

    assert _recommendation_reasons(payload) == [
        "package-root recommendation",
        "package-root recommendation",
    ]


def test_explicit_canonical_override_scope_wins_over_projected_generator_scope(rich_org_report_result):
    """Projected legacy overrides must not clobber explicit target-module override_scope values."""
    generator_mod = importlib.import_module("cja_auto_sdr.generator")

    with override_scope(
        generator_mod.__name__,
        {
            "_normalize_recommendation_for_json": lambda _rec: {
                "severity": "low",
                "reason": "legacy-source recommendation",
            },
        },
    ):
        with override_scope(
            "cja_auto_sdr.org.writers.json",
            {
                "_normalize_recommendation_for_json": lambda _rec: {
                    "severity": "high",
                    "reason": "canonical-target recommendation",
                },
            },
        ):
            payload = generator_mod.build_org_report_json_data(rich_org_report_result)

    assert _recommendation_reasons(payload) == [
        "canonical-target recommendation",
        "canonical-target recommendation",
    ]
