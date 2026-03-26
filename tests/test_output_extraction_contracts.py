"""Contract tests for output subpackage extraction.

These tests verify that symbols extracted from generator.py into the
output subpackages (output.diff, output.run_summary, output.inventory)
and org.writers subpackages are importable from their canonical locations,
remain callable with the expected signatures, and preserve public keyword
names and argument ordering across all export surfaces.
"""

from __future__ import annotations

import importlib
import json
import logging
import threading
from inspect import signature
from pathlib import Path
from unittest.mock import patch

import pytest


def _make_diff_result():
    from cja_auto_sdr.diff.models import ChangeType, ComponentDiff, DiffResult, DiffSummary, MetadataDiff

    return DiffResult(
        summary=DiffSummary(
            source_metrics_count=1,
            target_metrics_count=2,
            metrics_added=1,
        ),
        metadata_diff=MetadataDiff(
            source_name="Before",
            target_name="After",
            source_id="dv_before",
            target_id="dv_after",
        ),
        metric_diffs=[ComponentDiff(id="metric_1", name="Metric 1", change_type=ChangeType.ADDED)],
        dimension_diffs=[],
        source_label="Before",
        target_label="After",
        generated_at="2025-01-15 12:00:00",
        tool_version="3.2.8",
    )


def _recommendation_reasons(result) -> list[str]:
    return [str(rec.get("reason", "")) for rec in result.recommendations]


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


# ---------------------------------------------------------------------------
# output.diff top-level imports
# ---------------------------------------------------------------------------


def test_output_diff_text_renderers_importable():
    """Public text-oriented diff renderers are importable from output.diff."""
    from cja_auto_sdr.output.diff import (
        detect_breaking_changes,
        write_diff_console_output,
        write_diff_grouped_by_field_output,
        write_diff_markdown_output,
        write_diff_pr_comment_output,
    )

    assert callable(write_diff_console_output)
    assert callable(write_diff_grouped_by_field_output)
    assert callable(write_diff_markdown_output)
    assert callable(write_diff_pr_comment_output)
    assert callable(detect_breaking_changes)


# ---------------------------------------------------------------------------
# output.diff.console sub-module
# ---------------------------------------------------------------------------


def test_output_diff_console_importable():
    """Console diff renderer and helpers are importable from output.diff.console."""
    from cja_auto_sdr.output.diff.console import (
        _format_side_by_side,
        _get_colored_symbol,
        write_diff_console_output,
    )

    assert callable(write_diff_console_output)
    assert callable(_format_side_by_side)
    assert callable(_get_colored_symbol)


# ---------------------------------------------------------------------------
# output.diff.markdown sub-module
# ---------------------------------------------------------------------------


def test_output_diff_markdown_importable():
    """Markdown diff renderer and helpers are importable from output.diff.markdown."""
    from cja_auto_sdr.output.diff.markdown import (
        _format_markdown_side_by_side,
        write_diff_markdown_output,
    )

    assert callable(write_diff_markdown_output)
    assert callable(_format_markdown_side_by_side)


# ---------------------------------------------------------------------------
# output.diff.common sub-module
# ---------------------------------------------------------------------------


def test_output_diff_common_importable():
    """Shared diff helpers are importable from output.diff.common."""
    from cja_auto_sdr.output.diff.common import (
        _format_diff_value,
        _get_change_detail,
        _get_change_emoji,
        _get_change_symbol,
        _get_inventory_change_detail,
        detect_breaking_changes,
    )

    assert callable(_format_diff_value)
    assert callable(_get_change_detail)
    assert callable(_get_change_emoji)
    assert callable(_get_change_symbol)
    assert callable(_get_inventory_change_detail)
    assert callable(detect_breaking_changes)


# ---------------------------------------------------------------------------
# output.diff.grouped sub-module
# ---------------------------------------------------------------------------


def test_output_diff_grouped_importable():
    """Grouped-by-field diff renderer is importable from output.diff.grouped."""
    from cja_auto_sdr.output.diff.grouped import write_diff_grouped_by_field_output

    assert callable(write_diff_grouped_by_field_output)


# ---------------------------------------------------------------------------
# output.diff.pr_comment sub-module
# ---------------------------------------------------------------------------


def test_output_diff_pr_comment_importable():
    """PR comment diff renderer is importable from output.diff.pr_comment."""
    from cja_auto_sdr.output.diff.pr_comment import write_diff_pr_comment_output

    assert callable(write_diff_pr_comment_output)


def test_output_diff_pr_comment_signature_preserves_public_keyword():
    """PR comment renderer should expose `changes_only`, not `_changes_only`."""
    from cja_auto_sdr.output.diff.pr_comment import write_diff_pr_comment_output

    assert list(signature(write_diff_pr_comment_output).parameters) == ["diff_result", "changes_only"]


@pytest.mark.parametrize(
    "module_name",
    [
        "cja_auto_sdr.generator",
        "cja_auto_sdr.output.diff",
        "cja_auto_sdr.diff.writers",
    ],
)
def test_pr_comment_accepts_public_keyword_across_export_surfaces(module_name):
    write_diff_pr_comment_output = getattr(importlib.import_module(module_name), "write_diff_pr_comment_output")

    output = write_diff_pr_comment_output(_make_diff_result(), changes_only=True)

    assert "Data View Comparison" in output


@pytest.mark.parametrize(
    "module_name",
    [
        "cja_auto_sdr.generator",
        "cja_auto_sdr.output.diff",
        "cja_auto_sdr.diff.writers",
    ],
)
def test_pr_comment_rejects_private_keyword_across_export_surfaces(module_name):
    write_diff_pr_comment_output = getattr(importlib.import_module(module_name), "write_diff_pr_comment_output")

    with pytest.raises(TypeError, match="unexpected keyword argument '_changes_only'"):
        write_diff_pr_comment_output(_make_diff_result(), _changes_only=True)


# ---------------------------------------------------------------------------
# output.diff file-based writers
# ---------------------------------------------------------------------------


def test_output_diff_file_writers_importable():
    """File-based diff writers are importable from output.diff."""
    from cja_auto_sdr.output.diff import (
        write_diff_csv_output,
        write_diff_excel_output,
        write_diff_html_output,
        write_diff_json_output,
        write_diff_output,
    )

    assert callable(write_diff_json_output)
    assert callable(write_diff_html_output)
    assert callable(write_diff_excel_output)
    assert callable(write_diff_csv_output)
    assert callable(write_diff_output)


# ---------------------------------------------------------------------------
# output.diff.json sub-module
# ---------------------------------------------------------------------------


def test_output_diff_json_importable():
    """JSON diff writer is importable from output.diff.json."""
    from cja_auto_sdr.output.diff.json import write_diff_json_output

    assert callable(write_diff_json_output)


# ---------------------------------------------------------------------------
# output.diff.html sub-module
# ---------------------------------------------------------------------------


def test_output_diff_html_importable():
    """HTML diff writer is importable from output.diff.html."""
    from cja_auto_sdr.output.diff.html import write_diff_html_output

    assert callable(write_diff_html_output)


# ---------------------------------------------------------------------------
# output.diff.excel sub-module
# ---------------------------------------------------------------------------


def test_output_diff_excel_importable():
    """Excel diff writer is importable from output.diff.excel."""
    from cja_auto_sdr.output.diff.excel import write_diff_excel_output

    assert callable(write_diff_excel_output)


# ---------------------------------------------------------------------------
# output.diff.csv sub-module
# ---------------------------------------------------------------------------


def test_output_diff_csv_importable():
    """CSV diff writer is importable from output.diff.csv."""
    from cja_auto_sdr.output.diff.csv import write_diff_csv_output

    assert callable(write_diff_csv_output)


# ---------------------------------------------------------------------------
# diff.writers wrapper routing
# ---------------------------------------------------------------------------


def test_diff_writers_wrapper_resolves_to_output_diff():
    from cja_auto_sdr.diff.writers import write_diff_output

    assert write_diff_output.__module__ == "cja_auto_sdr.output.diff"


def test_diff_writers_pr_comment_signature_preserves_public_keyword():
    from cja_auto_sdr.diff.writers import write_diff_pr_comment_output

    assert list(signature(write_diff_pr_comment_output).parameters) == ["diff_result", "changes_only"]


# ---------------------------------------------------------------------------
# output.inventory top-level imports
# ---------------------------------------------------------------------------


def test_output_inventory_summary_importable():
    """display_inventory_summary is importable from output.inventory."""
    from cja_auto_sdr.output.inventory import display_inventory_summary

    assert callable(display_inventory_summary)


# ---------------------------------------------------------------------------
# output.inventory.summary sub-module
# ---------------------------------------------------------------------------


def test_output_inventory_summary_submodule_importable():
    """display_inventory_summary is importable from output.inventory.summary."""
    from cja_auto_sdr.output.inventory.summary import display_inventory_summary

    assert callable(display_inventory_summary)


# ---------------------------------------------------------------------------
# inventory.summary wrapper routing
# ---------------------------------------------------------------------------


def test_inventory_summary_wrapper_resolves_to_output_inventory():
    from cja_auto_sdr.inventory.summary import display_inventory_summary

    assert display_inventory_summary.__module__ == "cja_auto_sdr.output.inventory.summary"


# ---------------------------------------------------------------------------
# output.writers canonical imports
# ---------------------------------------------------------------------------


_OUTPUT_WRITER_SIGNATURES = {
    "write_csv_output": ["data_dict", "base_filename", "output_dir", "logger"],
    "write_excel_output": ["data_dict", "base_filename", "output_dir", "logger"],
    "write_html_output": ["data_dict", "metadata_dict", "base_filename", "output_dir", "logger"],
    "write_json_output": ["data_dict", "metadata_dict", "base_filename", "output_dir", "logger", "inventory_objects"],
    "write_markdown_output": ["data_dict", "metadata_dict", "base_filename", "output_dir", "logger"],
}

_OUTPUT_WRITER_MODULE_CASES = [
    ("cja_auto_sdr.output.writers", "write_csv_output"),
    ("cja_auto_sdr.output.writers", "write_excel_output"),
    ("cja_auto_sdr.output.writers", "write_html_output"),
    ("cja_auto_sdr.output.writers", "write_json_output"),
    ("cja_auto_sdr.output.writers", "write_markdown_output"),
    ("cja_auto_sdr.output.writers.csv", "write_csv_output"),
    ("cja_auto_sdr.output.writers.excel", "write_excel_output"),
    ("cja_auto_sdr.output.writers.html", "write_html_output"),
    ("cja_auto_sdr.output.writers.json", "write_json_output"),
    ("cja_auto_sdr.output.writers.markdown", "write_markdown_output"),
]


def test_output_writers_package_exports_are_importable():
    """Canonical output.writers exports should resolve as callables."""
    from cja_auto_sdr.output.writers import (
        write_csv_output,
        write_excel_output,
        write_html_output,
        write_json_output,
        write_markdown_output,
    )

    assert callable(write_csv_output)
    assert callable(write_excel_output)
    assert callable(write_html_output)
    assert callable(write_json_output)
    assert callable(write_markdown_output)


@pytest.mark.parametrize(
    ("module_name", "func_name"),
    _OUTPUT_WRITER_MODULE_CASES,
    ids=[f"{module_name}.{func_name}" for module_name, func_name in _OUTPUT_WRITER_MODULE_CASES],
)
def test_output_writers_resolve_to_output_sdr(module_name, func_name):
    """Canonical output.writers surfaces should forward to output.sdr implementations."""
    func = getattr(importlib.import_module(module_name), func_name)

    assert func.__module__ == "cja_auto_sdr.output.sdr"


@pytest.mark.parametrize(
    ("module_name", "func_name"),
    _OUTPUT_WRITER_MODULE_CASES,
    ids=[f"{module_name}.{func_name}" for module_name, func_name in _OUTPUT_WRITER_MODULE_CASES],
)
def test_output_writers_signatures(module_name, func_name):
    """Canonical output.writers surfaces must preserve public argument names and ordering."""
    func = getattr(importlib.import_module(module_name), func_name)

    assert list(signature(func).parameters) == _OUTPUT_WRITER_SIGNATURES[func_name]


# ---------------------------------------------------------------------------
# output.run_summary direct imports
# ---------------------------------------------------------------------------


def test_output_run_summary_aggregate_quality_issues_importable():
    """aggregate_quality_issues is importable from output.run_summary."""
    from cja_auto_sdr.output.run_summary import aggregate_quality_issues

    assert callable(aggregate_quality_issues)


def test_output_run_summary_write_run_summary_output_importable():
    """write_run_summary_output is importable from output.run_summary."""
    from cja_auto_sdr.output.run_summary import write_run_summary_output

    assert callable(write_run_summary_output)


def test_output_run_summary_append_github_step_summary_importable():
    """append_github_step_summary is importable from output.run_summary."""
    from cja_auto_sdr.output.run_summary import append_github_step_summary

    assert callable(append_github_step_summary)


def test_output_run_summary_build_quality_step_summary_importable():
    """build_quality_step_summary is importable from output.run_summary."""
    from cja_auto_sdr.output.run_summary import build_quality_step_summary

    assert callable(build_quality_step_summary)


def test_output_run_summary_build_diff_step_summary_importable():
    """build_diff_step_summary is importable from output.run_summary."""
    from cja_auto_sdr.output.run_summary import build_diff_step_summary

    assert callable(build_diff_step_summary)


def test_output_run_summary_build_org_step_summary_importable():
    """build_org_step_summary is importable from output.run_summary."""
    from cja_auto_sdr.output.run_summary import build_org_step_summary

    assert callable(build_org_step_summary)


# ---------------------------------------------------------------------------
# output.run_summary signature contracts
# ---------------------------------------------------------------------------


_RUN_SUMMARY_SIGNATURES = {
    "aggregate_quality_issues": ["results"],
    "write_run_summary_output": ["summary", "output", "output_dir"],
    "append_github_step_summary": ["markdown", "logger"],
    "build_quality_step_summary": ["results"],
    "build_diff_step_summary": ["diff_result"],
    "build_org_step_summary": ["result"],
}


@pytest.mark.parametrize(
    ("func_name", "expected_params"),
    list(_RUN_SUMMARY_SIGNATURES.items()),
    ids=list(_RUN_SUMMARY_SIGNATURES.keys()),
)
def test_output_run_summary_signatures(func_name, expected_params):
    """Public argument names and ordering must remain unchanged."""
    mod = importlib.import_module("cja_auto_sdr.output.run_summary")
    func = getattr(mod, func_name)
    assert list(signature(func).parameters) == expected_params


@pytest.mark.parametrize(
    ("func_name", "expected_params"),
    list(_RUN_SUMMARY_SIGNATURES.items()),
    ids=list(_RUN_SUMMARY_SIGNATURES.keys()),
)
def test_generator_run_summary_signatures(func_name, expected_params):
    """Generator-level names must remain patchable with matching signatures."""
    mod = importlib.import_module("cja_auto_sdr.generator")
    func = getattr(mod, func_name)
    assert list(signature(func).parameters) == expected_params


# ---------------------------------------------------------------------------
# generator-level patch surface compatibility
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "func_name",
    list(_RUN_SUMMARY_SIGNATURES.keys()),
    ids=list(_RUN_SUMMARY_SIGNATURES.keys()),
)
def test_generator_run_summary_names_are_callable(func_name):
    """Generator-level run-summary names must remain callable."""
    mod = importlib.import_module("cja_auto_sdr.generator")
    assert callable(getattr(mod, func_name))


# ---------------------------------------------------------------------------
# org.writers.common sub-module
# ---------------------------------------------------------------------------


def test_org_writers_common_importable():
    """Shared normalization/validation helpers are importable from org.writers.common."""
    from cja_auto_sdr.org.writers.common import (
        _flatten_recommendation_for_tabular,
        _format_recommendation_context_entries,
        _normalize_org_report_output_format,
        _normalize_recommendation_for_json,
        _normalize_recommendation_severity,
        _render_distribution_bar,
        _validate_org_report_output_request,
    )

    assert callable(_flatten_recommendation_for_tabular)
    assert callable(_format_recommendation_context_entries)
    assert callable(_normalize_org_report_output_format)
    assert callable(_normalize_recommendation_for_json)
    assert callable(_normalize_recommendation_severity)
    assert callable(_render_distribution_bar)
    assert callable(_validate_org_report_output_request)


# ---------------------------------------------------------------------------
# org.writers.trending sub-module
# ---------------------------------------------------------------------------


_TRENDING_HELPERS = [
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
]


@pytest.mark.parametrize("name", _TRENDING_HELPERS, ids=_TRENDING_HELPERS)
def test_org_writers_trending_helpers_importable(name):
    """Trending helpers are importable from org.writers.trending."""
    mod = importlib.import_module("cja_auto_sdr.org.writers.trending")
    assert callable(getattr(mod, name))


@pytest.mark.parametrize("name", _TRENDING_HELPERS, ids=_TRENDING_HELPERS)
def test_org_writers_trending_helpers_reexported_at_package_root(name):
    """Trending helpers remain importable from the org.writers package root."""
    mod = importlib.import_module("cja_auto_sdr.org.writers")
    assert callable(getattr(mod, name))


# ---------------------------------------------------------------------------
# org.writers.console sub-module
# ---------------------------------------------------------------------------


def test_org_writers_console_importable():
    """Console org-report renderers are importable from org.writers.console."""
    from cja_auto_sdr.org.writers.console import (
        write_org_report_comparison_console,
        write_org_report_console,
        write_org_report_stats_only,
    )

    assert callable(write_org_report_console)
    assert callable(write_org_report_stats_only)
    assert callable(write_org_report_comparison_console)


# ---------------------------------------------------------------------------
# org.writers.json sub-module
# ---------------------------------------------------------------------------


def test_org_writers_json_importable():
    """JSON org-report builder/writer are importable from org.writers.json."""
    from cja_auto_sdr.org.writers.json import (
        build_org_report_json_data,
        write_org_report_json,
    )

    assert callable(build_org_report_json_data)
    assert callable(write_org_report_json)


# ---------------------------------------------------------------------------
# org.writers package-root continuity (console + JSON)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "write_org_report_console",
        "write_org_report_stats_only",
        "write_org_report_comparison_console",
        "build_org_report_json_data",
        "write_org_report_json",
    ],
)
def test_org_writers_package_root_continuity(name):
    """Console/JSON writers remain importable from the org.writers package root."""
    mod = importlib.import_module("cja_auto_sdr.org.writers")
    assert callable(getattr(mod, name))


# ---------------------------------------------------------------------------
# generator-level org-writer patch surface
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "_render_distribution_bar",
        "_format_recommendation_context_entries",
        "_normalize_recommendation_for_json",
        "_flatten_recommendation_for_tabular",
        "_validate_org_report_output_request",
    ],
)
def test_generator_org_writer_helpers_are_callable(name):
    """Generator-level org-writer helper re-exports must remain callable."""
    mod = importlib.import_module("cja_auto_sdr.generator")
    assert callable(getattr(mod, name))


@pytest.mark.parametrize(
    "module_name",
    ["cja_auto_sdr.org.writers", "cja_auto_sdr.generator"],
    ids=["org.writers", "generator"],
)
def test_org_json_builder_respects_legacy_helper_patch(module_name, rich_org_report_result):
    """Legacy module helper patches must still affect the extracted JSON builder."""
    mod = importlib.import_module(module_name)
    patched_reason = f"patched recommendation via {module_name}"

    with patch(
        f"{module_name}._normalize_recommendation_for_json",
        return_value={"severity": "low", "reason": patched_reason},
    ) as normalize_mock:
        data = mod.build_org_report_json_data(rich_org_report_result)

    assert [rec["reason"] for rec in data["recommendations"]] == [
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
    assert [rec["reason"] for rec in payload["recommendations"]] == [
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
    """Legacy module helper patches must still affect the extracted console writer."""
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
    """Legacy module helper patches must still affect extracted file-format writers."""
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
    assert [rec["reason"] for rec in canonical_data["recommendations"]] == _recommendation_reasons(
        rich_org_report_result,
    )
    assert [rec["reason"] for rec in legacy_result["data"]["recommendations"]] == [
        patched_reason,
        patched_reason,
    ]


# ---------------------------------------------------------------------------
# org.writers.excel sub-module
# ---------------------------------------------------------------------------


def test_org_writers_excel_importable():
    """Excel org-report writer is importable from org.writers.excel."""
    from cja_auto_sdr.org.writers.excel import write_org_report_excel

    assert callable(write_org_report_excel)


# ---------------------------------------------------------------------------
# org.writers.markdown sub-module
# ---------------------------------------------------------------------------


def test_org_writers_markdown_importable():
    """Markdown org-report writer is importable from org.writers.markdown."""
    from cja_auto_sdr.org.writers.markdown import write_org_report_markdown

    assert callable(write_org_report_markdown)


# ---------------------------------------------------------------------------
# org.writers.html sub-module
# ---------------------------------------------------------------------------


def test_org_writers_html_importable():
    """HTML org-report writer is importable from org.writers.html."""
    from cja_auto_sdr.org.writers.html import write_org_report_html

    assert callable(write_org_report_html)


# ---------------------------------------------------------------------------
# org.writers.csv sub-module
# ---------------------------------------------------------------------------


def test_org_writers_csv_importable():
    """CSV org-report writer is importable from org.writers.csv."""
    from cja_auto_sdr.org.writers.csv import write_org_report_csv

    assert callable(write_org_report_csv)


# ---------------------------------------------------------------------------
# org.writers package-root continuity (file writers)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "write_org_report_excel",
        "write_org_report_markdown",
        "write_org_report_html",
        "write_org_report_csv",
    ],
)
def test_org_writers_file_writer_package_root_continuity(name):
    """File-format writers remain importable from the org.writers package root."""
    mod = importlib.import_module("cja_auto_sdr.org.writers")
    assert callable(getattr(mod, name))


# ---------------------------------------------------------------------------
# output.diff signature contracts
# ---------------------------------------------------------------------------


_DIFF_WRITER_SIGNATURES = {
    "write_diff_console_output": ["diff_result", "changes_only", "summary_only", "side_by_side", "use_color"],
    "write_diff_grouped_by_field_output": ["diff_result", "use_color", "limit"],
    "write_diff_markdown_output": [
        "diff_result",
        "base_filename",
        "output_dir",
        "logger",
        "changes_only",
        "side_by_side",
    ],
    "write_diff_pr_comment_output": ["diff_result", "changes_only"],
    "write_diff_json_output": ["diff_result", "base_filename", "output_dir", "logger", "changes_only"],
    "write_diff_html_output": ["diff_result", "base_filename", "output_dir", "logger", "changes_only"],
    "write_diff_excel_output": ["diff_result", "base_filename", "output_dir", "logger", "changes_only"],
    "write_diff_csv_output": ["diff_result", "base_filename", "output_dir", "logger", "changes_only"],
    "detect_breaking_changes": ["diff_result"],
    "write_diff_output": [
        "diff_result",
        "output_format",
        "base_filename",
        "output_dir",
        "logger",
        "changes_only",
        "summary_only",
        "side_by_side",
        "use_color",
        "group_by_field",
        "group_by_field_limit",
    ],
}


@pytest.mark.parametrize(
    ("func_name", "expected_params"),
    list(_DIFF_WRITER_SIGNATURES.items()),
    ids=list(_DIFF_WRITER_SIGNATURES.keys()),
)
def test_output_diff_writer_signatures(func_name, expected_params):
    """Diff writer keyword names and argument ordering must remain unchanged."""
    mod = importlib.import_module("cja_auto_sdr.output.diff")
    func = getattr(mod, func_name)
    assert list(signature(func).parameters) == expected_params


@pytest.mark.parametrize(
    ("func_name", "expected_params"),
    list(_DIFF_WRITER_SIGNATURES.items()),
    ids=list(_DIFF_WRITER_SIGNATURES.keys()),
)
def test_generator_diff_writer_signatures(func_name, expected_params):
    """Generator-level diff writers must preserve matching signatures."""
    mod = importlib.import_module("cja_auto_sdr.generator")
    func = getattr(mod, func_name)
    assert list(signature(func).parameters) == expected_params


# ---------------------------------------------------------------------------
# output.diff __all__ continuity
# ---------------------------------------------------------------------------


def test_output_diff_all_continuity():
    """output.diff __all__ must contain all public diff writer names."""
    mod = importlib.import_module("cja_auto_sdr.output.diff")
    expected = {
        "detect_breaking_changes",
        "write_diff_console_output",
        "write_diff_csv_output",
        "write_diff_excel_output",
        "write_diff_grouped_by_field_output",
        "write_diff_html_output",
        "write_diff_json_output",
        "write_diff_markdown_output",
        "write_diff_output",
        "write_diff_pr_comment_output",
    }
    assert expected.issubset(set(mod.__all__))


# ---------------------------------------------------------------------------
# org.writers helper signature contracts
# ---------------------------------------------------------------------------


_ORG_WRITER_HELPER_SIGNATURES = {
    "_render_distribution_bar": ["count", "total", "width"],
    "_format_recommendation_context_entries": ["rec"],
    "_normalize_recommendation_for_json": ["raw_rec"],
    "_flatten_recommendation_for_tabular": ["rec"],
    "_validate_org_report_output_request": ["output_format", "output_to_stdout", "status_print"],
}


@pytest.mark.parametrize(
    ("func_name", "expected_params"),
    list(_ORG_WRITER_HELPER_SIGNATURES.items()),
    ids=list(_ORG_WRITER_HELPER_SIGNATURES.keys()),
)
def test_org_writers_common_helper_signatures(func_name, expected_params):
    """Org writer helper keyword names and ordering must remain unchanged."""
    mod = importlib.import_module("cja_auto_sdr.org.writers.common")
    func = getattr(mod, func_name)
    assert list(signature(func).parameters) == expected_params


@pytest.mark.parametrize(
    ("func_name", "expected_params"),
    list(_ORG_WRITER_HELPER_SIGNATURES.items()),
    ids=list(_ORG_WRITER_HELPER_SIGNATURES.keys()),
)
def test_generator_org_writer_helper_signatures(func_name, expected_params):
    """Generator-level org-writer helpers must preserve matching signatures."""
    mod = importlib.import_module("cja_auto_sdr.generator")
    func = getattr(mod, func_name)
    assert list(signature(func).parameters) == expected_params


# ---------------------------------------------------------------------------
# org.writers format writer signature contracts
# ---------------------------------------------------------------------------


_ORG_FORMAT_WRITER_SIGNATURES = {
    "write_org_report_console": ["result", "config", "quiet", "trending"],
    "write_org_report_stats_only": ["result", "quiet", "trending"],
    "write_org_report_comparison_console": ["comparison", "quiet"],
    "build_org_report_json_data": ["result", "trending"],
    "write_org_report_json": ["result", "output_path", "output_dir", "logger", "trending"],
    "write_org_report_excel": ["result", "output_path", "output_dir", "logger", "trending"],
    "write_org_report_markdown": ["result", "output_path", "output_dir", "logger", "trending"],
    "write_org_report_html": ["result", "output_path", "output_dir", "logger", "trending"],
    "write_org_report_csv": ["result", "output_path", "output_dir", "logger", "trending"],
}


@pytest.mark.parametrize(
    ("func_name", "expected_params"),
    list(_ORG_FORMAT_WRITER_SIGNATURES.items()),
    ids=list(_ORG_FORMAT_WRITER_SIGNATURES.keys()),
)
def test_org_format_writer_signatures(func_name, expected_params):
    """Org format writer keyword names and ordering must remain unchanged."""
    mod = importlib.import_module("cja_auto_sdr.org.writers")
    func = getattr(mod, func_name)
    assert list(signature(func).parameters) == expected_params


@pytest.mark.parametrize(
    ("func_name", "expected_params"),
    list(_ORG_FORMAT_WRITER_SIGNATURES.items()),
    ids=list(_ORG_FORMAT_WRITER_SIGNATURES.keys()),
)
def test_generator_org_format_writer_signatures(func_name, expected_params):
    """Generator-level org format writers must preserve matching signatures."""
    mod = importlib.import_module("cja_auto_sdr.generator")
    func = getattr(mod, func_name)
    assert list(signature(func).parameters) == expected_params


# ---------------------------------------------------------------------------
# org.writers __all__ continuity
# ---------------------------------------------------------------------------


def test_org_writers_all_continuity():
    """org.writers __all__ must contain all public org writer names."""
    mod = importlib.import_module("cja_auto_sdr.org.writers")
    expected = {
        "_flatten_recommendation_for_tabular",
        "_format_recommendation_context_entries",
        "_normalize_org_report_output_format",
        "_normalize_recommendation_for_json",
        "_normalize_recommendation_severity",
        "_render_distribution_bar",
        "_validate_org_report_output_request",
        "build_org_report_json_data",
        "write_org_report_comparison_console",
        "write_org_report_console",
        "write_org_report_csv",
        "write_org_report_excel",
        "write_org_report_html",
        "write_org_report_json",
        "write_org_report_markdown",
        "write_org_report_stats_only",
    }
    assert set(mod.__all__) == expected


# ---------------------------------------------------------------------------
# trending helper signature contracts (task-specified subset)
# ---------------------------------------------------------------------------


_TRENDING_SIGNATURE_CONTRACTS = {
    "_format_trending_timestamp_short": ["ts"],
    "_render_console_trending_table": ["column_labels", "metric_rows", "value_formatter"],
    "_render_html_trending_table": ["column_labels", "metric_rows", "value_formatter"],
    "_render_markdown_trending_table": ["column_labels", "metric_rows", "value_formatter"],
    "_render_trending_console": ["trending"],
    "_render_trending_html": ["trending"],
    "_render_trending_markdown": ["trending"],
    "_ranked_drift_entries": ["trending", "limit"],
    "_top_drift_scores": ["drift_scores", "limit"],
    "_trending_date_range": ["snapshots"],
}


@pytest.mark.parametrize(
    ("func_name", "expected_params"),
    list(_TRENDING_SIGNATURE_CONTRACTS.items()),
    ids=list(_TRENDING_SIGNATURE_CONTRACTS.keys()),
)
def test_trending_helper_signatures(func_name, expected_params):
    """Trending helper keyword names and ordering must remain unchanged."""
    mod = importlib.import_module("cja_auto_sdr.org.writers.trending")
    func = getattr(mod, func_name)
    assert list(signature(func).parameters) == expected_params


@pytest.mark.parametrize(
    ("func_name", "expected_params"),
    list(_TRENDING_SIGNATURE_CONTRACTS.items()),
    ids=list(_TRENDING_SIGNATURE_CONTRACTS.keys()),
)
def test_trending_helper_signatures_via_package_root(func_name, expected_params):
    """Trending helpers at org.writers root must preserve matching signatures."""
    mod = importlib.import_module("cja_auto_sdr.org.writers")
    func = getattr(mod, func_name)
    assert list(signature(func).parameters) == expected_params
