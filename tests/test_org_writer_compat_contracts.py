"""Focused compatibility contracts for org writer alias routing."""

from __future__ import annotations

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
