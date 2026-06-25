"""Focused compatibility contracts for org writer alias routing."""

from __future__ import annotations

import csv
import importlib
import json
import logging
import threading
from pathlib import Path
from unittest.mock import patch

import pytest

from cja_auto_sdr.org.writers.compat import override_scope

_IMPORT_ONLY_COMMON_HELPER_ALIASES = (
    "_render_distribution_bar",
    "_format_recommendation_context_entries",
    "_normalize_recommendation_severity",
    "_normalize_recommendation_for_json",
    "_flatten_recommendation_for_tabular",
    "_normalize_org_report_output_format",
    "_validate_org_report_output_request",
)
_WRAPPED_LEGACY_EXPORTS = (
    "write_org_report_console",
    "write_org_report_stats_only",
    "write_org_report_comparison_console",
    "build_org_report_json_data",
    "write_org_report_json",
    "write_org_report_excel",
    "write_org_report_markdown",
    "write_org_report_html",
    "write_org_report_csv",
)
_PACKAGE_ROOT_IMPORT_ONLY_TRENDING_ALIASES = (
    "_format_trending_timestamp_short",
    "_build_trending_metric_rows",
    "_trending_snapshot_metric_rows",
    "_trending_delta_metric_rows",
    "_trending_snapshot_column_specs",
    "_format_trending_period_label",
    "_trending_delta_column_specs",
    "_format_signed_trending_value",
    "_stringify_trending_value",
    "_sorted_drift_score_items",
    "_resolve_trending_dv_name",
    "_format_trending_dv_label",
    "_ranked_drift_entries",
    "_top_drift_scores",
    "_trending_date_range",
    "_render_console_trending_table",
    "_render_markdown_trending_table",
    "_escape_markdown_table_cell",
    "_render_html_trending_table",
    "_trending_matrix_rows",
    "_trending_snapshot_csv_rows",
    "_trending_delta_csv_rows",
    "_render_trending_console",
    "_render_trending_markdown",
    "_render_trending_html",
    "_print_trending_console_section",
    "_trending_snapshots_to_dicts",
)


def _recommendation_reasons(data) -> list[str]:
    recommendations = data["recommendations"] if isinstance(data, dict) else data.recommendations
    return [str(rec.get("reason", "")) for rec in recommendations]


def _make_trending():
    from cja_auto_sdr.org.models import OrgReportTrending, TrendingDelta, TrendingSnapshot

    snapshots = [
        TrendingSnapshot(
            timestamp="2025-01-01T00:00:00",
            data_view_count=3,
            component_count=10,
            core_count=5,
            isolated_count=1,
            high_sim_pair_count=0,
        ),
        TrendingSnapshot(
            timestamp="2025-02-01T00:00:00",
            data_view_count=4,
            component_count=14,
            core_count=6,
            isolated_count=2,
            high_sim_pair_count=1,
        ),
    ]
    return OrgReportTrending(
        snapshots=snapshots,
        deltas=[
            TrendingDelta(
                from_timestamp=snapshots[0].timestamp,
                to_timestamp=snapshots[1].timestamp,
                data_view_delta=1,
                component_delta=4,
                core_delta=1,
                isolated_delta=1,
                high_sim_pair_delta=1,
            ),
        ],
        drift_scores={"dv_001": 0.8},
        window_size=2,
    )


@pytest.mark.parametrize(
    "module_name",
    ["cja_auto_sdr.org.writers", "cja_auto_sdr.generator"],
    ids=["org.writers", "generator"],
)
@pytest.mark.parametrize("attr_name", _WRAPPED_LEGACY_EXPORTS, ids=_WRAPPED_LEGACY_EXPORTS)
def test_wrapped_legacy_exports_are_the_only_runtime_compat_shims(module_name, attr_name):
    """Legacy writer entrypoints remain wrapped runtime shims on the alias surfaces."""
    mod = importlib.import_module(module_name)
    value = getattr(mod, attr_name)

    assert value.__module__ == module_name
    assert hasattr(value, "__wrapped__")


@pytest.mark.parametrize(
    "module_name",
    ["cja_auto_sdr.org.writers", "cja_auto_sdr.generator"],
    ids=["org.writers", "generator"],
)
@pytest.mark.parametrize(
    "attr_name",
    _IMPORT_ONLY_COMMON_HELPER_ALIASES,
    ids=_IMPORT_ONLY_COMMON_HELPER_ALIASES,
)
def test_common_helper_aliases_remain_import_only(module_name, attr_name):
    """Common helper aliases stay as identity re-exports instead of runtime compat wrappers."""
    mod = importlib.import_module(module_name)
    common_mod = importlib.import_module("cja_auto_sdr.org.writers.common")
    value = getattr(mod, attr_name)
    canonical = getattr(common_mod, attr_name)

    assert value is canonical
    assert value.__module__ == common_mod.__name__
    assert not hasattr(value, "__wrapped__")


@pytest.mark.parametrize(
    "attr_name",
    _PACKAGE_ROOT_IMPORT_ONLY_TRENDING_ALIASES,
    ids=_PACKAGE_ROOT_IMPORT_ONLY_TRENDING_ALIASES,
)
def test_package_root_trending_helper_aliases_remain_import_only(attr_name):
    """Package-root trending helpers stay as identity re-exports of the canonical module."""
    mod = importlib.import_module("cja_auto_sdr.org.writers")
    trending_mod = importlib.import_module("cja_auto_sdr.org.writers.trending")
    value = getattr(mod, attr_name)
    canonical = getattr(trending_mod, attr_name)

    assert value is canonical
    assert value.__module__ == trending_mod.__name__
    assert not hasattr(value, "__wrapped__")


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


def test_canonical_json_builder_helper_proxy_nested_override_scope_layers_compose(
    rich_org_report_result,
):
    """Nested same-symbol canonical helper overrides must reveal outer layers when delegating."""
    mod = importlib.import_module("cja_auto_sdr.org.writers.json")
    calls: list[str] = []

    def outer(rec):
        reason = str(rec.get("reason", ""))
        calls.append(f"outer:{reason}")
        return {"severity": "low", "reason": f"outer:{reason}"}

    def inner(rec):
        reason = str(rec.get("reason", ""))
        calls.append(f"inner:{reason}")
        normalized = mod._normalize_recommendation_for_json(rec)
        return {"severity": normalized["severity"], "reason": f"inner:{normalized['reason']}"}

    with override_scope(
        mod.__name__,
        {
            "_normalize_recommendation_for_json": outer,
        },
    ):
        with override_scope(
            mod.__name__,
            {
                "_normalize_recommendation_for_json": inner,
            },
        ):
            payload = mod.build_org_report_json_data(rich_org_report_result)

    assert _recommendation_reasons(payload) == [
        "inner:outer:A data view has many isolated components",
        "inner:outer:Two data views are highly similar",
    ]
    assert calls == [
        "inner:A data view has many isolated components",
        "outer:A data view has many isolated components",
        "inner:Two data views are highly similar",
        "outer:Two data views are highly similar",
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


@pytest.mark.parametrize(
    "module_name",
    ["cja_auto_sdr.org.writers", "cja_auto_sdr.generator"],
    ids=["org.writers", "generator"],
)
def test_legacy_json_builder_nested_override_scope_layers_compose(module_name, rich_org_report_result):
    """Nested same-symbol legacy wrapped overrides must reveal outer layers when delegating."""
    mod = importlib.import_module(module_name)
    calls: list[str] = []

    def outer(result, trending=None):
        calls.append("outer")
        payload = dict(mod.build_org_report_json_data(result, trending=trending))
        payload["report_type"] = f"outer:{payload['report_type']}"
        return payload

    def inner(result, trending=None):
        calls.append("inner")
        payload = dict(mod.build_org_report_json_data(result, trending=trending))
        payload["report_type"] = f"inner:{payload['report_type']}"
        return payload

    with override_scope(
        mod.__name__,
        {
            "build_org_report_json_data": outer,
        },
    ):
        with override_scope(
            mod.__name__,
            {
                "build_org_report_json_data": inner,
            },
        ):
            payload = mod.build_org_report_json_data(rich_org_report_result)

    assert payload["report_type"] == "inner:outer:org_analysis"
    assert calls == ["inner", "outer"]


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


@pytest.mark.parametrize(
    "module_name",
    ["cja_auto_sdr.org.writers", "cja_auto_sdr.generator"],
    ids=["org.writers", "generator"],
)
def test_canonical_json_builder_patch_wins_over_projected_legacy_builder_patch_in_writer(
    module_name,
    tmp_path,
    rich_org_report_result,
):
    """Explicit canonical builder monkeypatches must win over projected legacy builder patches."""
    mod = importlib.import_module(module_name)
    canonical_mod = importlib.import_module("cja_auto_sdr.org.writers.json")
    logger = logging.getLogger(f"test.{module_name}.write_org_report_json.canonical_builder_patch")
    source_payload = {
        "report_type": "source",
        "org_id": rich_org_report_result.org_id,
    }
    canonical_payload = {
        "report_type": "canonical",
        "org_id": rich_org_report_result.org_id,
    }

    with patch.object(mod, "build_org_report_json_data", return_value=source_payload):
        with patch.object(canonical_mod, "build_org_report_json_data", return_value=canonical_payload) as build_mock:
            output_path = Path(
                mod.write_org_report_json(
                    rich_org_report_result,
                    tmp_path / "org_report_canonical_patch.json",
                    str(tmp_path),
                    logger,
                ),
            )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload == canonical_payload
    build_mock.assert_called_once_with(rich_org_report_result, trending=None)


@pytest.mark.parametrize(
    "module_name",
    ["cja_auto_sdr.org.writers", "cja_auto_sdr.generator"],
    ids=["org.writers", "generator"],
)
def test_legacy_json_writer_nested_builder_monkeypatch_layers_compose(
    module_name,
    tmp_path,
    rich_org_report_result,
):
    """Stacked same-symbol legacy builder monkeypatches must reveal outer layers when delegating."""
    mod = importlib.import_module(module_name)
    logger = logging.getLogger(f"test.{module_name}.write_org_report_json.nested_builder_monkeypatch")
    calls: list[str] = []

    def outer(result, trending=None):
        calls.append("outer")
        payload = dict(mod.build_org_report_json_data(result, trending=trending))
        payload["report_type"] = f"outer:{payload['report_type']}"
        return payload

    def inner(result, trending=None):
        calls.append("inner")
        payload = dict(mod.build_org_report_json_data(result, trending=trending))
        payload["report_type"] = f"inner:{payload['report_type']}"
        return payload

    with patch.object(mod, "build_org_report_json_data", side_effect=outer):
        with patch.object(mod, "build_org_report_json_data", side_effect=inner):
            output_path = Path(
                mod.write_org_report_json(
                    rich_org_report_result,
                    tmp_path / "org_report_nested_patch.json",
                    str(tmp_path),
                    logger,
                ),
            )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["report_type"] == "inner:outer:org_analysis"
    assert calls == ["inner", "outer"]


@pytest.mark.parametrize(
    "module_name",
    ["cja_auto_sdr.org.writers", "cja_auto_sdr.generator"],
    ids=["org.writers", "generator"],
)
def test_legacy_json_writer_self_delegating_builder_monkeypatch_runs_once(
    module_name,
    tmp_path,
    rich_org_report_result,
):
    """Self-delegating legacy builder monkeypatches must not recurse through the JSON writer."""
    mod = importlib.import_module(module_name)
    logger = logging.getLogger(f"test.{module_name}.write_org_report_json.builder_monkeypatch")
    calls: list[str] = []

    def custom(result, trending=None):
        calls.append("custom")
        payload = dict(mod.build_org_report_json_data(result, trending=trending))
        payload["report_type"] = f"custom:{payload['report_type']}"
        return payload

    with patch.object(mod, "build_org_report_json_data", side_effect=custom):
        output_path = Path(
            mod.write_org_report_json(
                rich_org_report_result,
                tmp_path / "org_report_patched.json",
                str(tmp_path),
                logger,
            ),
        )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["report_type"] == "custom:org_analysis"
    assert calls == ["custom"]


@pytest.mark.parametrize(
    "module_name",
    ["cja_auto_sdr.org.writers", "cja_auto_sdr.generator"],
    ids=["org.writers", "generator"],
)
def test_legacy_json_writer_source_scoped_builder_override_runs_once(
    module_name,
    tmp_path,
    rich_org_report_result,
):
    """Projected source-scope builder overrides must not re-apply through the JSON writer."""
    mod = importlib.import_module(module_name)
    logger = logging.getLogger(f"test.{module_name}.write_org_report_json.source_builder_scope")
    calls: list[str] = []

    def custom(result, trending=None):
        calls.append("custom")
        payload = dict(mod.build_org_report_json_data(result, trending=trending))
        payload["report_type"] = f"custom:{payload['report_type']}"
        return payload

    with override_scope(
        mod.__name__,
        {
            "build_org_report_json_data": custom,
        },
    ):
        output_path = Path(
            mod.write_org_report_json(
                rich_org_report_result,
                tmp_path / "org_report.json",
                str(tmp_path),
                logger,
            ),
        )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["report_type"] == "custom:org_analysis"
    assert calls == ["custom"]


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


@pytest.mark.parametrize(
    "module_name",
    ["cja_auto_sdr.org.writers", "cja_auto_sdr.generator"],
    ids=["org.writers", "generator"],
)
def test_direct_legacy_builder_call_respects_explicit_canonical_override_scope(
    module_name,
    rich_org_report_result,
):
    """Legacy direct builder calls must forward through explicit canonical override_scope values."""
    mod = importlib.import_module(module_name)
    canonical_mod = importlib.import_module("cja_auto_sdr.org.writers.json")

    def canonical(result, trending=None):
        payload = dict(canonical_mod.build_org_report_json_data(result, trending=trending))
        payload["report_type"] = f"canonical:{payload['report_type']}"
        return payload

    with override_scope(
        canonical_mod.__name__,
        {
            "build_org_report_json_data": canonical,
        },
    ):
        payload = mod.build_org_report_json_data(rich_org_report_result)

    assert payload["report_type"] == "canonical:org_analysis"


@pytest.mark.parametrize(
    "module_name",
    ["cja_auto_sdr.org.writers", "cja_auto_sdr.generator"],
    ids=["org.writers", "generator"],
)
def test_explicit_canonical_json_builder_override_wins_over_projected_legacy_builder_scope(
    module_name,
    rich_org_report_result,
):
    """Explicit canonical builder overrides must win over projected legacy same-symbol overrides."""
    mod = importlib.import_module(module_name)
    canonical_mod = importlib.import_module("cja_auto_sdr.org.writers.json")
    calls: list[str] = []

    def source(result, trending=None):
        calls.append("source")
        payload = dict(mod.build_org_report_json_data(result, trending=trending))
        payload["report_type"] = f"source:{payload['report_type']}"
        return payload

    def canonical(result, trending=None):
        calls.append("canonical")
        payload = dict(canonical_mod.build_org_report_json_data(result, trending=trending))
        payload["report_type"] = f"canonical:{payload['report_type']}"
        return payload

    with override_scope(
        mod.__name__,
        {
            "build_org_report_json_data": source,
        },
    ):
        with override_scope(
            canonical_mod.__name__,
            {
                "build_org_report_json_data": canonical,
            },
        ):
            payload = mod.build_org_report_json_data(rich_org_report_result)

    assert payload["report_type"] == "canonical:org_analysis"
    assert calls == ["canonical"]


@pytest.mark.parametrize(
    "module_name",
    ["cja_auto_sdr.org.writers", "cja_auto_sdr.generator"],
    ids=["org.writers", "generator"],
)
def test_org_json_builder_respects_legacy_helper_patch(module_name, rich_org_report_result):
    """Legacy helper patches must still affect the extracted JSON builder."""
    mod = importlib.import_module(module_name)
    patched_reason = f"patched recommendation via {module_name}"

    with patch(
        f"{module_name}._normalize_recommendation_for_json",
        return_value={"severity": "low", "reason": patched_reason},
    ) as normalize_mock:
        data = mod.build_org_report_json_data(rich_org_report_result)

    assert _recommendation_reasons(data) == [
        patched_reason,
        patched_reason,
    ]
    assert normalize_mock.call_count == len(rich_org_report_result.recommendations)


@pytest.mark.parametrize(
    "module_name",
    ["cja_auto_sdr.org.writers", "cja_auto_sdr.generator"],
    ids=["org.writers", "generator"],
)
def test_org_json_writer_respects_legacy_builder_patch(module_name, tmp_path, rich_org_report_result):
    """Legacy builder patches must still affect the extracted JSON writer."""
    mod = importlib.import_module(module_name)
    logger = logging.getLogger(f"test.{module_name}.write_org_report_json")
    payload = {
        "report_type": "patched",
        "version": "test",
        "org_id": rich_org_report_result.org_id,
    }

    with patch(f"{module_name}.build_org_report_json_data", return_value=payload) as build_mock:
        output_path = Path(
            mod.write_org_report_json(
                rich_org_report_result,
                tmp_path / "org_report.json",
                str(tmp_path),
                logger,
            ),
        )

    build_mock.assert_called_once_with(rich_org_report_result, trending=None)
    assert json.loads(output_path.read_text(encoding="utf-8")) == payload


@pytest.mark.parametrize(
    "module_name",
    ["cja_auto_sdr.org.writers", "cja_auto_sdr.generator"],
    ids=["org.writers", "generator"],
)
def test_org_json_writer_respects_legacy_helper_patch(module_name, tmp_path, rich_org_report_result):
    """Legacy helper patches must still flow through the JSON writer re-exports."""
    mod = importlib.import_module(module_name)
    logger = logging.getLogger(f"test.{module_name}.write_org_report_json.helper")
    patched_reason = f"patched writer recommendation via {module_name}"

    with patch(
        f"{module_name}._normalize_recommendation_for_json",
        return_value={"severity": "low", "reason": patched_reason},
    ) as normalize_mock:
        output_path = Path(
            mod.write_org_report_json(
                rich_org_report_result,
                tmp_path / "org_report.json",
                str(tmp_path),
                logger,
            ),
        )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert _recommendation_reasons(payload) == [
        patched_reason,
        patched_reason,
    ]
    assert normalize_mock.call_count == len(rich_org_report_result.recommendations)


def test_org_json_writer_respects_package_root_trending_helper_patch(tmp_path, rich_org_report_result):
    """Package-root trending helper patches must still reach the JSON writer."""
    mod = importlib.import_module("cja_auto_sdr.org.writers")
    logger = logging.getLogger("test.cja_auto_sdr.org.writers.write_org_report_json.trending")
    trending = _make_trending()
    patched_trending = {
        "window_size": 99,
        "snapshots": [{"timestamp": "patched"}],
        "deltas": [],
        "drift_scores": {"dv_999": 1.0},
        "drift_details": [{"data_view_id": "dv_999", "score": 1.0}],
    }

    with patch(
        "cja_auto_sdr.org.writers._trending_snapshots_to_dicts",
        return_value=patched_trending,
    ) as trending_mock:
        output_path = Path(
            mod.write_org_report_json(
                rich_org_report_result,
                tmp_path / "org_report_trending.json",
                str(tmp_path),
                logger,
                trending=trending,
            ),
        )

    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["trending"] == patched_trending
    trending_mock.assert_called_once_with(trending)


@pytest.mark.parametrize(
    "writer_module_name",
    [
        "cja_auto_sdr.org.writers.json",
        "cja_auto_sdr.org.writers",
        "cja_auto_sdr.generator",
    ],
    ids=["org.writers.json", "org.writers", "generator"],
)
def test_canonical_json_builder_patch_flows_through_writer_exports(
    writer_module_name,
    tmp_path,
    rich_org_report_result,
):
    """Patching the canonical extracted builder must still affect every writer surface."""
    writer_mod = importlib.import_module(writer_module_name)
    logger = logging.getLogger(f"test.{writer_module_name}.canonical_builder_patch")
    payload = {
        "report_type": "canonical-patched",
        "version": "test",
        "org_id": rich_org_report_result.org_id,
    }

    with patch("cja_auto_sdr.org.writers.json.build_org_report_json_data", return_value=payload) as build_mock:
        output_path = Path(
            writer_mod.write_org_report_json(
                rich_org_report_result,
                tmp_path / "canonical_patched.json",
                str(tmp_path),
                logger,
            ),
        )

    build_mock.assert_called_once_with(rich_org_report_result, trending=None)
    assert json.loads(output_path.read_text(encoding="utf-8")) == payload


@pytest.mark.parametrize(
    "module_name",
    ["cja_auto_sdr.org.writers", "cja_auto_sdr.generator"],
    ids=["org.writers", "generator"],
)
def test_canonical_json_builder_patch_flows_through_builder_reexports(module_name, rich_org_report_result):
    """Legacy builder re-exports must defer to the current canonical builder when unpatched."""
    mod = importlib.import_module(module_name)
    payload = {
        "report_type": "canonical-builder-patched",
        "org_id": rich_org_report_result.org_id,
    }

    with patch("cja_auto_sdr.org.writers.json.build_org_report_json_data", return_value=payload) as build_mock:
        returned = mod.build_org_report_json_data(rich_org_report_result)

    build_mock.assert_called_once_with(rich_org_report_result)
    assert returned == payload


@pytest.mark.parametrize(
    "module_name",
    ["cja_auto_sdr.org.writers", "cja_auto_sdr.generator"],
    ids=["org.writers", "generator"],
)
def test_org_console_writer_respects_legacy_helper_patch(module_name, capsys, rich_org_report_result):
    """Legacy helper patches must still affect the extracted console writer."""
    mod = importlib.import_module(module_name)

    with patch(f"{module_name}._render_distribution_bar", return_value="[patched-bar]") as render_mock:
        mod.write_org_report_console(rich_org_report_result, rich_org_report_result.parameters, quiet=False)

    output = capsys.readouterr().out
    assert "[patched-bar]" in output
    assert render_mock.call_count >= 8


@pytest.mark.parametrize(
    "module_name",
    ["cja_auto_sdr.org.writers", "cja_auto_sdr.generator"],
    ids=["org.writers", "generator"],
)
def test_org_markdown_writer_respects_legacy_helper_patch(module_name, tmp_path, rich_org_report_result):
    """Legacy helper patches must still affect extracted file-format writers."""
    mod = importlib.import_module(module_name)
    logger = logging.getLogger(f"test.{module_name}.write_org_report_markdown")
    patched_reason = f"patched markdown recommendation via {module_name}"

    with patch(
        f"{module_name}._normalize_recommendation_for_json",
        return_value={"severity": "low", "reason": patched_reason},
    ) as normalize_mock:
        output_path = Path(
            mod.write_org_report_markdown(
                rich_org_report_result,
                tmp_path / "org_report.md",
                str(tmp_path),
                logger,
            ),
        )

    assert patched_reason in output_path.read_text(encoding="utf-8")
    assert normalize_mock.call_count == len(rich_org_report_result.recommendations)


@pytest.mark.parametrize(
    "module_name",
    ["cja_auto_sdr.org.writers", "cja_auto_sdr.generator"],
    ids=["org.writers", "generator"],
)
def test_org_csv_writer_respects_legacy_flatten_helper_patch(module_name, tmp_path, rich_org_report_result):
    """Legacy tabular helper patches must still affect the extracted CSV writer."""
    mod = importlib.import_module(module_name)
    logger = logging.getLogger(f"test.{module_name}.write_org_report_csv.flatten")
    patched_reason = f"patched csv recommendation via {module_name}"

    with patch(
        f"{module_name}._flatten_recommendation_for_tabular",
        side_effect=lambda rec: {
            "Severity": rec["severity"],
            "Reason": patched_reason,
            "Source": module_name,
        },
    ) as flatten_mock:
        output_dir = Path(
            mod.write_org_report_csv(
                rich_org_report_result,
                tmp_path / "org_report.csv",
                str(tmp_path),
                logger,
            ),
        )

    recommendations_path = output_dir / "org_report_recommendations.csv"
    with recommendations_path.open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))

    assert [row["Reason"] for row in rows] == [patched_reason] * len(rich_org_report_result.recommendations)
    assert [row["Source"] for row in rows] == [module_name] * len(rich_org_report_result.recommendations)
    assert flatten_mock.call_count == len(rich_org_report_result.recommendations)


@pytest.mark.parametrize(
    "module_name",
    ["cja_auto_sdr.org.writers", "cja_auto_sdr.generator"],
    ids=["org.writers", "generator"],
)
def test_org_html_writer_respects_legacy_context_helper_patch(module_name, tmp_path, rich_org_report_result):
    """Legacy context helper patches must still affect the extracted HTML writer."""
    mod = importlib.import_module(module_name)
    logger = logging.getLogger(f"test.{module_name}.write_org_report_html.context")
    patched_label = "Patched Context"
    patched_value = f"legacy html context via {module_name}"

    with patch(
        f"{module_name}._format_recommendation_context_entries",
        return_value=[(patched_label, patched_value)],
    ) as context_mock:
        output_path = Path(
            mod.write_org_report_html(
                rich_org_report_result,
                tmp_path / "org_report.html",
                str(tmp_path),
                logger,
            ),
        )

    html_output = output_path.read_text(encoding="utf-8")
    assert patched_label in html_output
    assert patched_value in html_output
    assert context_mock.call_count == len(rich_org_report_result.recommendations)


@pytest.mark.parametrize(
    "legacy_module_name",
    ["cja_auto_sdr.org.writers", "cja_auto_sdr.generator"],
    ids=["org.writers", "generator"],
)
def test_legacy_json_patch_context_does_not_leak_to_canonical_submodule(
    legacy_module_name,
    rich_org_report_result,
):
    """Legacy compatibility patches must stay local to the calling context."""
    legacy_mod = importlib.import_module(legacy_module_name)
    canonical_mod = importlib.import_module("cja_auto_sdr.org.writers.json")
    legacy_thread_ready = threading.Event()
    release_legacy_thread = threading.Event()
    legacy_thread_id: dict[str, int] = {}
    leaked_call_thread_ids: list[int] = []
    patched_reason = f"patched concurrent recommendation via {legacy_module_name}"
    legacy_result: dict[str, object] = {}

    def patched_normalize(rec):
        del rec
        current_thread_id = threading.get_ident()
        if current_thread_id == legacy_thread_id.get("value"):
            legacy_thread_ready.set()
            assert release_legacy_thread.wait(timeout=5)
            return {"severity": "low", "reason": patched_reason}

        leaked_call_thread_ids.append(current_thread_id)
        return {"severity": "low", "reason": "unexpected cross-thread leak"}

    def run_legacy_call():
        legacy_thread_id["value"] = threading.get_ident()
        legacy_result["data"] = legacy_mod.build_org_report_json_data(rich_org_report_result)

    with patch(f"{legacy_module_name}._normalize_recommendation_for_json", side_effect=patched_normalize):
        worker = threading.Thread(target=run_legacy_call)
        worker.start()

        assert legacy_thread_ready.wait(timeout=5)
        canonical_data = canonical_mod.build_org_report_json_data(rich_org_report_result)
        release_legacy_thread.set()
        worker.join(timeout=5)
        assert not worker.is_alive()

    assert leaked_call_thread_ids == []
    assert _recommendation_reasons(canonical_data) == _recommendation_reasons(rich_org_report_result)
    assert _recommendation_reasons(legacy_result["data"]) == [
        patched_reason,
        patched_reason,
    ]


@pytest.mark.parametrize(
    "legacy_module_name",
    ["cja_auto_sdr.org.writers", "cja_auto_sdr.generator"],
    ids=["org.writers", "generator"],
)
def test_legacy_json_helper_patch_remains_visible_to_concurrent_legacy_calls(
    legacy_module_name,
    rich_org_report_result,
):
    """Legacy helper patches must stay visible to concurrent legacy compat calls."""
    legacy_mod = importlib.import_module(legacy_module_name)
    legacy_thread_ready = threading.Event()
    release_legacy_thread = threading.Event()
    legacy_thread_id: dict[str, int] = {}
    patched_call_thread_ids: list[int] = []
    patched_reason = f"patched concurrent legacy recommendation via {legacy_module_name}"
    legacy_results: dict[str, object] = {}

    def patched_normalize(rec):
        del rec
        current_thread_id = threading.get_ident()
        patched_call_thread_ids.append(current_thread_id)
        if current_thread_id == legacy_thread_id.get("value"):
            legacy_thread_ready.set()
            assert release_legacy_thread.wait(timeout=5)
        return {"severity": "low", "reason": patched_reason}

    def run_legacy_call(slot: str):
        if slot == "thread":
            legacy_thread_id["value"] = threading.get_ident()
        legacy_results[slot] = legacy_mod.build_org_report_json_data(rich_org_report_result)

    with patch(f"{legacy_module_name}._normalize_recommendation_for_json", side_effect=patched_normalize):
        worker = threading.Thread(target=run_legacy_call, args=("thread",))
        worker.start()

        assert legacy_thread_ready.wait(timeout=5)
        run_legacy_call("main")
        release_legacy_thread.set()
        worker.join(timeout=5)
        assert not worker.is_alive()

    assert len(patched_call_thread_ids) == len(rich_org_report_result.recommendations) * 2
    assert _recommendation_reasons(legacy_results["thread"]) == [
        patched_reason,
        patched_reason,
    ]
    assert _recommendation_reasons(legacy_results["main"]) == [
        patched_reason,
        patched_reason,
    ]


@pytest.mark.parametrize(
    "legacy_module_name",
    ["cja_auto_sdr.org.writers", "cja_auto_sdr.generator"],
    ids=["org.writers", "generator"],
)
def test_legacy_json_writer_builder_patch_remains_visible_to_concurrent_legacy_calls(
    legacy_module_name,
    tmp_path,
    rich_org_report_result,
):
    """Projected legacy builder patches must remain visible to concurrent writer calls."""
    legacy_mod = importlib.import_module(legacy_module_name)
    legacy_thread_ready = threading.Event()
    release_legacy_thread = threading.Event()
    legacy_thread_id: dict[str, int] = {}
    patched_calls: list[int] = []
    output_paths: dict[str, Path] = {}
    logger = logging.getLogger(f"test.{legacy_module_name}.write_org_report_json.concurrent_builder_patch")

    def patched_builder(result, trending=None):
        current_thread_id = threading.get_ident()
        patched_calls.append(current_thread_id)
        if current_thread_id == legacy_thread_id.get("value"):
            legacy_thread_ready.set()
            assert release_legacy_thread.wait(timeout=5)

        payload = dict(legacy_mod.build_org_report_json_data(result, trending=trending))
        payload["report_type"] = f"patched:{payload['report_type']}"
        return payload

    def run_writer(slot: str):
        if slot == "thread":
            legacy_thread_id["value"] = threading.get_ident()
        output_paths[slot] = Path(
            legacy_mod.write_org_report_json(
                rich_org_report_result,
                tmp_path / f"{slot}_org_report.json",
                str(tmp_path),
                logger,
            ),
        )

    with patch.object(legacy_mod, "build_org_report_json_data", side_effect=patched_builder):
        worker = threading.Thread(target=run_writer, args=("thread",))
        worker.start()

        assert legacy_thread_ready.wait(timeout=5)
        run_writer("main")
        release_legacy_thread.set()
        worker.join(timeout=5)
        assert not worker.is_alive()

    assert len(patched_calls) == 2
    assert json.loads(output_paths["thread"].read_text(encoding="utf-8"))["report_type"] == "patched:org_analysis"
    assert json.loads(output_paths["main"].read_text(encoding="utf-8"))["report_type"] == "patched:org_analysis"


# ---------------------------------------------------------------------------
# Advisories additive-compat contract
# ---------------------------------------------------------------------------


_EXPECTED_CORE_JSON_KEYS = frozenset(
    [
        "report_type",
        "version",
        "generated_at",
        "org_id",
        "parameters",
        "summary",
        "data_view_fetch_failures",
        "distribution",
        "data_views",
        "component_index",
        "similarity_pairs",
        "clusters",
        "recommendations",
        "governance_violations",
        "thresholds_exceeded",
        "naming_audit",
        "owner_summary",
        "stale_components",
    ]
)


def test_advisories_key_is_additive_does_not_remove_existing_keys(rich_org_report_result):
    """Adding the advisories block must not drop any pre-existing top-level JSON keys."""
    from cja_auto_sdr.org.writers.json import build_org_report_json_data

    data = build_org_report_json_data(rich_org_report_result)

    # All pre-existing keys must still be present
    missing = _EXPECTED_CORE_JSON_KEYS - data.keys()
    assert not missing, f"Keys removed after advisories injection: {missing}"

    # The new key must also be present
    assert "advisories" in data


def test_format_trending_dv_label_falls_back_to_id_when_name_is_absent_or_matches():
    """writers/trending L264: bare id is returned when no distinct display name exists."""
    from cja_auto_sdr.org.writers.trending import _format_trending_dv_label

    # No name available -> just the id.
    assert _format_trending_dv_label("dv_001", None) == "dv_001"
    # Empty name -> still just the id.
    assert _format_trending_dv_label("dv_001", "") == "dv_001"
    # Name identical to id -> avoid the redundant "name (id)" form.
    assert _format_trending_dv_label("dv_001", "dv_001") == "dv_001"
    # A genuinely distinct name keeps the compact "name (id)" label.
    assert _format_trending_dv_label("dv_001", "Production") == "Production (dv_001)"


# ---------------------------------------------------------------------------
# Direct unit coverage for org writer compat internal binding/masking helpers
# ---------------------------------------------------------------------------


def test_masked_module_attr_proxy_getattr_delegates_to_wrapped_value():
    """compat L70: attribute access on the proxy is forwarded to the wrapped callable."""
    from cja_auto_sdr.org.writers import compat

    def wrapped():
        return "ok"

    wrapped.custom_marker = "delegated"

    proxy = compat._MaskedModuleAttrProxy("some.module", "wrapped", wrapped)
    # __getattr__ only fires for attributes not in __slots__, e.g. arbitrary attrs.
    assert proxy.custom_marker == "delegated"
    assert proxy.__name__ == "wrapped"


def test_peek_masked_module_attr_returns_non_callable_baseline_directly():
    """compat L179: a non-callable masked baseline is returned without proxy wrapping."""
    from cja_auto_sdr.org.writers import compat

    module_name = "cja_auto_sdr.test_compat_peek_module"
    attr_name = "value"
    key = compat._compat_key(module_name, attr_name)

    non_callable_baseline = "baseline-string"

    def callable_top():
        return "top"

    compat._MODULE_ATTR_BINDING_STACKS[key] = [non_callable_baseline, callable_top]
    token = compat._MASKED_MODULE_ATTRS.set({key: 1})
    try:
        # depth=1 -> effective_index=0 -> masked is the non-callable baseline.
        result = compat._peek_masked_module_attr(module_name, attr_name)
        assert result == non_callable_baseline
    finally:
        compat._MASKED_MODULE_ATTRS.reset(token)
        compat._MODULE_ATTR_BINDING_STACKS.pop(key, None)


def test_effective_module_attr_binding_imports_module_when_no_stack():
    """compat L187-188: with no recorded stack, the live module attribute is read."""
    from cja_auto_sdr.org.writers import compat

    # core.version has a stable, real attribute and no compat binding stack.
    result = compat._effective_module_attr_binding("cja_auto_sdr.core.version", "__version__")
    import cja_auto_sdr.core.version as version_mod

    assert result == version_mod.__version__


def test_effective_module_attr_binding_missing_attr_returns_sentinel():
    """compat L187-188: a missing attribute on an unstacked module yields the sentinel."""
    from cja_auto_sdr.org.writers import compat

    result = compat._effective_module_attr_binding(
        "cja_auto_sdr.core.version",
        "definitely_not_a_real_attribute",
    )
    assert result is compat._MISSING


def test_record_module_attr_binding_noop_when_value_unchanged():
    """compat L200: re-recording the current top-of-stack value leaves the stack intact."""
    from cja_auto_sdr.org.writers import compat

    module_name = "cja_auto_sdr.test_compat_record_module"
    attr_name = "value"
    key = compat._compat_key(module_name, attr_name)

    sentinel = object()
    compat._MODULE_ATTR_BINDING_STACKS[key] = [sentinel]
    try:
        compat._record_module_attr_binding(module_name, attr_name, sentinel)
        # Stack must be untouched (no duplicate push).
        assert compat._MODULE_ATTR_BINDING_STACKS[key] == [sentinel]
    finally:
        compat._MODULE_ATTR_BINDING_STACKS.pop(key, None)


def test_suppress_override_is_noop_without_active_override():
    """compat L282-283: suppressing an unset override key simply yields."""
    from cja_auto_sdr.org.writers import compat

    entered = False
    with compat._suppress_override("cja_auto_sdr.test_compat_suppress", "missing_attr"):
        entered = True
    assert entered is True


def test_mask_module_attrs_is_noop_with_empty_attr_names():
    """compat L319-320: an empty attr-name iterable short-circuits to a plain yield."""
    from cja_auto_sdr.org.writers import compat

    entered = False
    with compat._mask_module_attrs("cja_auto_sdr.test_compat_mask", []):
        entered = True
    assert entered is True


def test_mask_module_attrs_skips_unregistered_keys_and_yields():
    """compat L328 + L333-334: attrs without a registered baseline are skipped, then yield."""
    from cja_auto_sdr.org.writers import compat

    before = compat._current_masked_module_attrs().copy()
    entered = False
    # Neither attr name is present in _MASKED_MODULE_BASELINES for this module, so
    # every key is skipped (L328) and applied_keys stays empty (L333-334).
    with compat._mask_module_attrs(
        "cja_auto_sdr.test_compat_mask_unregistered",
        ["attr_one", "attr_two"],
    ):
        entered = True
        # No masking should have been applied to the active context.
        assert compat._current_masked_module_attrs() == before
    assert entered is True
