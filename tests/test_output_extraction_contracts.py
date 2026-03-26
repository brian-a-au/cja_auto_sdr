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
def test_org_json_builder_respects_legacy_severity_helper_patch(module_name, rich_org_report_result):
    """Legacy severity helper patches must still reach nested recommendation normalization."""
    mod = importlib.import_module(module_name)

    with patch(f"{module_name}._normalize_recommendation_severity", return_value="high") as severity_mock:
        data = mod.build_org_report_json_data(rich_org_report_result)

    assert [rec["severity"] for rec in data["recommendations"]] == ["high", "high"]
    assert severity_mock.call_count == len(rich_org_report_result.recommendations)


@pytest.mark.parametrize(
    "module_name",
    ["cja_auto_sdr.org.writers", "cja_auto_sdr.generator"],
    ids=["org.writers", "generator"],
)
def test_org_json_builder_respects_legacy_context_helper_patch(module_name, rich_org_report_result):
    """Legacy context formatter patches must still reach nested recommendation normalization."""
    mod = importlib.import_module(module_name)
    patched_value = f"patched context via {module_name}"

    with patch(
        f"{module_name}._format_recommendation_context_entries",
        return_value=[("Patched", patched_value)],
    ) as context_mock:
        data = mod.build_org_report_json_data(rich_org_report_result)

    assert [rec["context"] for rec in data["recommendations"]] == [
        [{"label": "Patched", "value": patched_value}],
        [{"label": "Patched", "value": patched_value}],
    ]
    assert context_mock.call_count == len(rich_org_report_result.recommendations)


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
    ("writer_name", "suffix"),
    [
        ("write_org_report_markdown", ".md"),
        ("write_org_report_html", ".html"),
    ],
    ids=["markdown", "html"],
)
@pytest.mark.parametrize(
    "module_name",
    ["cja_auto_sdr.org.writers", "cja_auto_sdr.generator"],
    ids=["org.writers", "generator"],
)
def test_org_file_writers_respect_legacy_context_helper_patch(
    writer_name,
    suffix,
    module_name,
    tmp_path,
    rich_org_report_result,
):
    """Legacy context helper patches must flow into every recommendation-rendering file writer."""
    mod = importlib.import_module(module_name)
    logger = logging.getLogger(f"test.{module_name}.{writer_name}.context")
    patched_label = "Patched Context"
    patched_value = f"patched context via {module_name}"

    with patch(
        f"{module_name}._format_recommendation_context_entries",
        return_value=[(patched_label, patched_value)],
    ) as context_mock:
        output_path = Path(
            getattr(mod, writer_name)(
                rich_org_report_result,
                tmp_path / f"org_report{suffix}",
                str(tmp_path),
                logger,
            ),
        )

    output = output_path.read_text(encoding="utf-8")
    assert patched_label in output
    assert patched_value in output
    assert context_mock.call_count >= len(rich_org_report_result.recommendations)


def test_org_markdown_writer_respects_package_root_timestamp_helper_patch(
    tmp_path,
    rich_org_report_result,
):
    """Package-root timestamp formatter patches must still flow into markdown trending output."""
    mod = importlib.import_module("cja_auto_sdr.org.writers")
    logger = logging.getLogger("test.cja_auto_sdr.org.writers.write_org_report_markdown.trending")
    trending = _make_trending()

    with patch(
        "cja_auto_sdr.org.writers._format_trending_timestamp_short",
        side_effect=lambda ts: f"patched:{ts[5:7]}",
    ) as timestamp_mock:
        output_path = Path(
            mod.write_org_report_markdown(
                rich_org_report_result,
                tmp_path / "org_report_trending.md",
                str(tmp_path),
                logger,
                trending=trending,
            ),
        )

    output = output_path.read_text(encoding="utf-8")
    assert "patched:01" in output
    assert "patched:02" in output
    assert timestamp_mock.call_count >= 4


def test_org_writers_trending_helper_reexports_respect_package_root_timestamp_patch():
    """Package-root trending helper re-exports must preserve nested timestamp monkeypatches."""
    mod = importlib.import_module("cja_auto_sdr.org.writers")
    trending = _make_trending()

    with patch(
        "cja_auto_sdr.org.writers._format_trending_timestamp_short",
        side_effect=lambda ts: f"patched:{ts[5:7]}",
    ) as timestamp_mock:
        snapshot_specs = mod._trending_snapshot_column_specs(trending.snapshots)
        period_label = mod._format_trending_period_label(
            trending.deltas[0].from_timestamp,
            trending.deltas[0].to_timestamp,
        )
        delta_specs = mod._trending_delta_column_specs(trending.deltas)

    assert [label for _key, label in snapshot_specs] == ["patched:01", "patched:02"]
    assert period_label == "patched:01 -> patched:02"
    assert [label for _key, label in delta_specs] == ["patched:01 -> patched:02"]
    assert timestamp_mock.call_count == 6


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
# org.writers __all__ export consistency
# ---------------------------------------------------------------------------


_ORG_WRITERS_SUBMODULES = [
    "cja_auto_sdr.org.writers.compat",
    "cja_auto_sdr.org.writers.console",
    "cja_auto_sdr.org.writers.json",
    "cja_auto_sdr.org.writers.csv",
    "cja_auto_sdr.org.writers.excel",
    "cja_auto_sdr.org.writers.html",
    "cja_auto_sdr.org.writers.markdown",
    "cja_auto_sdr.org.writers.trending",
]

# compat.py exports are internal plumbing, not re-exported by the parent __init__.py
_ORG_WRITERS_REEXPORTED_SUBMODULES = [m for m in _ORG_WRITERS_SUBMODULES if m != "cja_auto_sdr.org.writers.compat"]


class TestOrgWritersAllExportConsistency:
    """Verify __all__ declarations in org/writers submodules are consistent with parent re-exports."""

    @pytest.mark.parametrize(
        "submodule", _ORG_WRITERS_SUBMODULES, ids=[m.rsplit(".", 1)[-1] for m in _ORG_WRITERS_SUBMODULES]
    )
    def test_submodule_has_all(self, submodule):
        """Each org/writers submodule must declare __all__."""
        mod = importlib.import_module(submodule)
        assert hasattr(mod, "__all__"), f"{submodule} is missing __all__"

    @pytest.mark.parametrize(
        "submodule", _ORG_WRITERS_SUBMODULES, ids=[m.rsplit(".", 1)[-1] for m in _ORG_WRITERS_SUBMODULES]
    )
    def test_all_names_exist_on_submodule(self, submodule):
        """Every name in a submodule's __all__ must exist as an attribute on that submodule."""
        mod = importlib.import_module(submodule)
        for name in mod.__all__:
            assert hasattr(mod, name), f"{submodule}.__all__ declares {name!r} but it is not an attribute"

    @pytest.mark.parametrize(
        "submodule",
        _ORG_WRITERS_REEXPORTED_SUBMODULES,
        ids=[m.rsplit(".", 1)[-1] for m in _ORG_WRITERS_REEXPORTED_SUBMODULES],
    )
    def test_all_names_importable_from_parent(self, submodule):
        """Every name in a submodule's __all__ must be importable from cja_auto_sdr.org.writers."""
        sub_mod = importlib.import_module(submodule)
        parent_mod = importlib.import_module("cja_auto_sdr.org.writers")
        for name in sub_mod.__all__:
            assert hasattr(parent_mod, name), (
                f"{submodule}.__all__ declares {name!r} but it is not importable from cja_auto_sdr.org.writers"
            )


# ---------------------------------------------------------------------------
# output.diff __all__ export consistency
# ---------------------------------------------------------------------------


_OUTPUT_DIFF_SUBMODULES = [
    "cja_auto_sdr.output.diff.common",
    "cja_auto_sdr.output.diff.console",
    "cja_auto_sdr.output.diff.csv",
    "cja_auto_sdr.output.diff.json",
    "cja_auto_sdr.output.diff.excel",
    "cja_auto_sdr.output.diff.html",
    "cja_auto_sdr.output.diff.markdown",
    "cja_auto_sdr.output.diff.grouped",
    "cja_auto_sdr.output.diff.pr_comment",
]


class TestOutputDiffAllExportConsistency:
    """Verify __all__ declarations in output/diff submodules are consistent with parent re-exports."""

    @pytest.mark.parametrize(
        "submodule", _OUTPUT_DIFF_SUBMODULES, ids=[m.rsplit(".", 1)[-1] for m in _OUTPUT_DIFF_SUBMODULES]
    )
    def test_submodule_has_all(self, submodule):
        """Each output/diff submodule must declare __all__."""
        mod = importlib.import_module(submodule)
        assert hasattr(mod, "__all__"), f"{submodule} is missing __all__"

    @pytest.mark.parametrize(
        "submodule", _OUTPUT_DIFF_SUBMODULES, ids=[m.rsplit(".", 1)[-1] for m in _OUTPUT_DIFF_SUBMODULES]
    )
    def test_all_names_exist_on_submodule(self, submodule):
        """Every name in a submodule's __all__ must exist as an attribute on that submodule."""
        mod = importlib.import_module(submodule)
        for name in mod.__all__:
            assert hasattr(mod, name), f"{submodule}.__all__ declares {name!r} but it is not an attribute"

    @pytest.mark.parametrize(
        "submodule", _OUTPUT_DIFF_SUBMODULES, ids=[m.rsplit(".", 1)[-1] for m in _OUTPUT_DIFF_SUBMODULES]
    )
    def test_all_names_importable_from_parent(self, submodule):
        """Every name in a submodule's __all__ must be importable from cja_auto_sdr.output.diff."""
        sub_mod = importlib.import_module(submodule)
        parent_mod = importlib.import_module("cja_auto_sdr.output.diff")
        for name in sub_mod.__all__:
            assert hasattr(parent_mod, name), (
                f"{submodule}.__all__ declares {name!r} but it is not importable from cja_auto_sdr.output.diff"
            )


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


# ---------------------------------------------------------------------------
# org.writers.compat contract surface
# ---------------------------------------------------------------------------


class TestCompatSignatureContinuity:
    """Verify function signatures for all public/exported functions in compat.py."""

    _COMPAT_PUBLIC_SIGNATURES = {
        "freeze_override_mapping": {
            "params": ["mapping"],
        },
        "compose_override_mapping": {
            "params": ["mappings"],
        },
        "resolve_override": {
            "params": ["target_module_name", "attr_name", "default"],
        },
        "call_override": {
            "params": ["target_module_name", "attr_name", "default", "args", "kwargs"],
        },
        "make_override_proxy": {
            "params": ["target_module_name", "attr_name", "default"],
        },
        "collect_legacy_overrides": {
            "params": ["source_module_name", "override_mapping", "baselines"],
        },
        "override_scope": {
            "params": ["target_module_name", "overrides"],
        },
        "make_compat_wrapper": {
            "params": ["source_module_name", "target", "target_module_name", "override_mapping"],
        },
    }

    @pytest.mark.parametrize(
        ("func_name", "contract"),
        list(_COMPAT_PUBLIC_SIGNATURES.items()),
        ids=list(_COMPAT_PUBLIC_SIGNATURES.keys()),
    )
    def test_compat_function_signatures(self, func_name, contract):
        """Public compat functions must preserve parameter names and ordering."""
        mod = importlib.import_module("cja_auto_sdr.org.writers.compat")
        func = getattr(mod, func_name)
        assert list(signature(func).parameters) == contract["params"]

    def test_freeze_override_mapping_annotation(self):
        """freeze_override_mapping must accept and return a Mapping."""
        from cja_auto_sdr.org.writers.compat import freeze_override_mapping

        sig = signature(freeze_override_mapping)
        assert sig.return_annotation is not sig.empty

    def test_compose_override_mapping_is_variadic(self):
        """compose_override_mapping must accept variadic positional mappings."""
        import inspect

        from cja_auto_sdr.org.writers.compat import compose_override_mapping

        sig = signature(compose_override_mapping)
        mappings_param = sig.parameters["mappings"]
        assert mappings_param.kind == inspect.Parameter.VAR_POSITIONAL

    def test_collect_legacy_overrides_has_keyword_only_baselines(self):
        """collect_legacy_overrides must keep baselines as a keyword-only parameter."""
        import inspect

        from cja_auto_sdr.org.writers.compat import collect_legacy_overrides

        sig = signature(collect_legacy_overrides)
        param = sig.parameters["baselines"]
        assert param.kind == inspect.Parameter.KEYWORD_ONLY

    def test_collect_legacy_overrides_baselines_defaults_to_none(self):
        """collect_legacy_overrides baselines parameter must default to None."""
        from cja_auto_sdr.org.writers.compat import collect_legacy_overrides

        sig = signature(collect_legacy_overrides)
        param = sig.parameters["baselines"]
        assert param.default is None

    def test_make_compat_wrapper_has_keyword_only_params(self):
        """make_compat_wrapper must have target_module_name and override_mapping as keyword-only."""
        import inspect

        from cja_auto_sdr.org.writers.compat import make_compat_wrapper

        sig = signature(make_compat_wrapper)
        assert sig.parameters["target_module_name"].kind == inspect.Parameter.KEYWORD_ONLY
        assert sig.parameters["override_mapping"].kind == inspect.Parameter.KEYWORD_ONLY


class TestCompatOverrideMappingCompleteness:
    """Verify all exported *_OVERRIDE_MAPPING constants exist and are expected types."""

    _EXPECTED_OVERRIDE_MAPPINGS = [
        "EMPTY_OVERRIDE_MAPPING",
        "COMMON_RECOMMENDATION_OVERRIDE_MAPPING",
        "TRENDING_LABEL_OVERRIDE_MAPPING",
        "CONSOLE_WRITER_OVERRIDE_MAPPING",
        "CONSOLE_STATS_ONLY_OVERRIDE_MAPPING",
        "JSON_BUILDER_OVERRIDE_MAPPING",
        "JSON_WRITER_OVERRIDE_MAPPING",
        "EXCEL_WRITER_OVERRIDE_MAPPING",
        "MARKDOWN_WRITER_OVERRIDE_MAPPING",
        "HTML_WRITER_OVERRIDE_MAPPING",
        "CSV_WRITER_OVERRIDE_MAPPING",
    ]

    @pytest.mark.parametrize("name", _EXPECTED_OVERRIDE_MAPPINGS, ids=_EXPECTED_OVERRIDE_MAPPINGS)
    def test_override_mapping_exists(self, name):
        """Override mapping constant must be importable from compat module."""
        mod = importlib.import_module("cja_auto_sdr.org.writers.compat")
        assert hasattr(mod, name)

    @pytest.mark.parametrize("name", _EXPECTED_OVERRIDE_MAPPINGS, ids=_EXPECTED_OVERRIDE_MAPPINGS)
    def test_override_mapping_is_mapping(self, name):
        """Override mapping constant must be a Mapping."""
        from collections.abc import Mapping

        mod = importlib.import_module("cja_auto_sdr.org.writers.compat")
        obj = getattr(mod, name)
        assert isinstance(obj, Mapping)

    @pytest.mark.parametrize("name", _EXPECTED_OVERRIDE_MAPPINGS, ids=_EXPECTED_OVERRIDE_MAPPINGS)
    def test_override_mapping_is_frozen(self, name):
        """Override mapping constant must be immutable (MappingProxyType)."""
        from types import MappingProxyType

        mod = importlib.import_module("cja_auto_sdr.org.writers.compat")
        obj = getattr(mod, name)
        assert isinstance(obj, MappingProxyType)

    def test_empty_override_mapping_is_empty(self):
        """EMPTY_OVERRIDE_MAPPING must have zero entries."""
        from cja_auto_sdr.org.writers.compat import EMPTY_OVERRIDE_MAPPING

        assert len(EMPTY_OVERRIDE_MAPPING) == 0

    def test_common_recommendation_mapping_fans_out_context_helper_to_proxy_modules(self):
        """Context helper overrides must reach every canonical proxy that renders recommendations."""
        from cja_auto_sdr.org.writers.compat import COMMON_RECOMMENDATION_OVERRIDE_MAPPING

        context_targets = {
            key
            for key, legacy_attr in COMMON_RECOMMENDATION_OVERRIDE_MAPPING.items()
            if legacy_attr == "_format_recommendation_context_entries"
        }
        assert context_targets == {
            ("cja_auto_sdr.org.writers.common", "_format_recommendation_context_entries"),
            ("cja_auto_sdr.org.writers.markdown", "_format_recommendation_context_entries"),
            ("cja_auto_sdr.org.writers.html", "_format_recommendation_context_entries"),
        }

    def test_common_recommendation_mapping_scopes_severity_helper_to_common_module(self):
        """Severity helper overrides should stay scoped to the common normalizer."""
        from cja_auto_sdr.org.writers.compat import COMMON_RECOMMENDATION_OVERRIDE_MAPPING

        severity_targets = {
            key
            for key, legacy_attr in COMMON_RECOMMENDATION_OVERRIDE_MAPPING.items()
            if legacy_attr == "_normalize_recommendation_severity"
        }
        assert severity_targets == {
            ("cja_auto_sdr.org.writers.common", "_normalize_recommendation_severity"),
        }

    def test_trending_label_mapping_targets_trending_module(self):
        """TRENDING_LABEL_OVERRIDE_MAPPING keys must target the trending module."""
        from cja_auto_sdr.org.writers.compat import TRENDING_LABEL_OVERRIDE_MAPPING

        for key in TRENDING_LABEL_OVERRIDE_MAPPING:
            assert isinstance(key, tuple)
            module_name, _attr = key
            assert module_name == "cja_auto_sdr.org.writers.trending"

    def test_composed_mappings_inherit_base_entries(self):
        """Composed mappings must contain all entries from their base mappings."""
        from cja_auto_sdr.org.writers.compat import (
            COMMON_RECOMMENDATION_OVERRIDE_MAPPING,
            CONSOLE_WRITER_OVERRIDE_MAPPING,
            JSON_BUILDER_OVERRIDE_MAPPING,
            TRENDING_LABEL_OVERRIDE_MAPPING,
        )

        for base_key in TRENDING_LABEL_OVERRIDE_MAPPING:
            assert base_key in CONSOLE_WRITER_OVERRIDE_MAPPING
        for base_key in COMMON_RECOMMENDATION_OVERRIDE_MAPPING:
            assert base_key in JSON_BUILDER_OVERRIDE_MAPPING

    def test_override_mapping_values_are_strings(self):
        """All override mapping values must be string attribute names."""
        mod = importlib.import_module("cja_auto_sdr.org.writers.compat")
        for name in self._EXPECTED_OVERRIDE_MAPPINGS:
            mapping = getattr(mod, name)
            for value in mapping.values():
                assert isinstance(value, str), f"{name}[...] = {value!r} is not a string"

    def test_composed_mappings_no_string_tuple_attr_collision(self):
        """No composed mapping should have a bare string key whose attr duplicates a tuple key's attr."""
        mod = importlib.import_module("cja_auto_sdr.org.writers.compat")
        for name in self._EXPECTED_OVERRIDE_MAPPINGS:
            mapping = getattr(mod, name)
            tuple_attrs = {attr for key in mapping if isinstance(key, tuple) for _, attr in [key]}
            string_keys = {key for key in mapping if isinstance(key, str)}
            collision = string_keys & tuple_attrs
            assert not collision, f"{name} has string key(s) {collision} that duplicate tuple key attr names"


class TestMakeCompatWrapperBehavior:
    """Test that make_compat_wrapper returns a callable with correct behavior."""

    def test_returns_callable(self):
        """make_compat_wrapper must return a callable."""
        from cja_auto_sdr.org.writers.compat import EMPTY_OVERRIDE_MAPPING, make_compat_wrapper

        def dummy_target():
            return "original"

        wrapper = make_compat_wrapper(
            "cja_auto_sdr.org.writers.compat",
            dummy_target,
            target_module_name="cja_auto_sdr.org.writers.compat",
            override_mapping=EMPTY_OVERRIDE_MAPPING,
        )
        assert callable(wrapper)

    def test_preserves_wrapped_function_name(self):
        """make_compat_wrapper must preserve the target function's __name__."""
        from cja_auto_sdr.org.writers.compat import EMPTY_OVERRIDE_MAPPING, make_compat_wrapper

        def my_special_function():
            return "value"

        wrapper = make_compat_wrapper(
            "cja_auto_sdr.org.writers.compat",
            my_special_function,
            target_module_name="cja_auto_sdr.org.writers.compat",
            override_mapping=EMPTY_OVERRIDE_MAPPING,
        )
        assert wrapper.__name__ == "my_special_function"

    def test_sets_module_to_source(self):
        """make_compat_wrapper must set __module__ to the source module name."""
        from cja_auto_sdr.org.writers.compat import EMPTY_OVERRIDE_MAPPING, make_compat_wrapper

        def dummy():
            pass

        wrapper = make_compat_wrapper(
            "cja_auto_sdr.org.writers",
            dummy,
            target_module_name="cja_auto_sdr.org.writers.compat",
            override_mapping=EMPTY_OVERRIDE_MAPPING,
        )
        assert wrapper.__module__ == "cja_auto_sdr.org.writers"

    def test_override_scope_applies_and_restores(self):
        """override_scope must apply overrides and restore state afterwards."""
        from cja_auto_sdr.org.writers.compat import _current_overrides, override_scope

        key = ("test.module", "test_attr")
        assert key not in _current_overrides()

        with override_scope("test.module", {"test_attr": "patched_value"}):
            assert _current_overrides()[key] == "patched_value"

        assert key not in _current_overrides()

    def test_collect_legacy_overrides_preserves_flat_result_contract(self):
        """collect_legacy_overrides must return the legacy flat attr->override mapping."""
        from cja_auto_sdr.org.writers.compat import collect_legacy_overrides, compose_override_mapping

        overrides = collect_legacy_overrides(
            "cja_auto_sdr.org.writers.compat",
            {"compose": "compose_override_mapping"},
        )

        assert overrides == {"compose": compose_override_mapping}

    def test_collect_legacy_overrides_rejects_tuple_keys(self):
        """collect_legacy_overrides public surface must reject normalized tuple-key mappings."""
        from cja_auto_sdr.org.writers.compat import collect_legacy_overrides

        with pytest.raises(TypeError, match="public override_mapping keys must be strings"):
            collect_legacy_overrides(
                "cja_auto_sdr.org.writers.compat",
                {("test.module", "compose"): "compose_override_mapping"},
            )

    def test_resolve_override_returns_default_without_scope(self):
        """resolve_override must return the default when no override is active."""
        from cja_auto_sdr.org.writers.compat import resolve_override

        sentinel = object()
        result = resolve_override("nonexistent.module", "nonexistent_attr", sentinel)
        assert result is sentinel

    def test_resolve_override_returns_override_within_scope(self):
        """resolve_override must return the overridden value inside an override_scope."""
        from cja_auto_sdr.org.writers.compat import override_scope, resolve_override

        sentinel = object()
        override_val = object()
        key_module = "test.resolve.module"
        key_attr = "test_resolve_attr"

        with override_scope(key_module, {key_attr: override_val}):
            result = resolve_override(key_module, key_attr, sentinel)
            assert result is override_val

    def test_make_override_proxy_delegates_through_scope(self):
        """make_override_proxy must call overridden function within an override_scope."""
        from cja_auto_sdr.org.writers.compat import make_override_proxy, override_scope

        def default_fn(x):
            return f"default:{x}"

        proxy = make_override_proxy("test.proxy.module", "test_fn", default_fn)
        assert proxy("hello") == "default:hello"

        def override_fn(x):
            return f"override:{x}"

        with override_scope("test.proxy.module", {"test_fn": override_fn}):
            assert proxy("hello") == "override:hello"

        assert proxy("hello") == "default:hello"

    def test_call_override_invokes_default(self):
        """call_override must invoke the default callable when no override is active."""
        from cja_auto_sdr.org.writers.compat import call_override

        def default_fn(a, b):
            return a + b

        result = call_override("test.call.module", "test_fn", default_fn, 3, 4)
        assert result == 7

    def test_call_override_invokes_override_within_scope(self):
        """call_override must invoke the overridden callable inside an override_scope."""
        from cja_auto_sdr.org.writers.compat import call_override, override_scope

        def default_fn(a, b):
            return a + b

        def override_fn(a, b):
            return a * b

        with override_scope("test.call.module", {"test_fn": override_fn}):
            result = call_override("test.call.module", "test_fn", default_fn, 3, 4)
            assert result == 12

    def test_call_override_forwards_kwargs(self):
        """call_override must forward keyword arguments to both default and overridden callables."""
        from cja_auto_sdr.org.writers.compat import call_override, override_scope

        def default_fn(*, x, y):
            return f"default:{x},{y}"

        def override_fn(*, x, y):
            return f"override:{x},{y}"

        assert call_override("test.kw.module", "test_fn", default_fn, x=1, y=2) == "default:1,2"

        with override_scope("test.kw.module", {"test_fn": override_fn}):
            assert call_override("test.kw.module", "test_fn", default_fn, x=3, y=4) == "override:3,4"

    def test_override_scope_nesting_preserves_outer_keys(self):
        """Nested override_scope must not clobber outer scope's unrelated keys."""
        from cja_auto_sdr.org.writers.compat import _current_overrides, override_scope

        key_a = ("test.nest.module", "attr_a")
        key_b = ("test.nest.module", "attr_b")

        with override_scope("test.nest.module", {"attr_a": "outer_a"}):
            with override_scope("test.nest.module", {"attr_b": "inner_b"}):
                overrides = _current_overrides()
                assert overrides[key_a] == "outer_a"
                assert overrides[key_b] == "inner_b"

    def test_override_scope_nesting_inner_shadows_same_key(self):
        """Inner override_scope must shadow the outer scope for the same key."""
        from cja_auto_sdr.org.writers.compat import _current_overrides, override_scope

        key = ("test.shadow.module", "attr")

        with override_scope("test.shadow.module", {"attr": "outer"}):
            assert _current_overrides()[key] == "outer"
            with override_scope("test.shadow.module", {"attr": "inner"}):
                assert _current_overrides()[key] == "inner"

    def test_override_scope_nesting_exit_restores_outer(self):
        """Exiting inner override_scope must restore outer scope's original values."""
        from cja_auto_sdr.org.writers.compat import _current_overrides, override_scope

        key = ("test.restore.module", "attr")

        with override_scope("test.restore.module", {"attr": "outer"}):
            with override_scope("test.restore.module", {"attr": "inner"}):
                pass
            assert _current_overrides()[key] == "outer"

        assert key not in _current_overrides()

    def test_override_scope_rejects_non_string_keys(self):
        """override_scope public surface must reject normalized tuple-key mappings."""
        from cja_auto_sdr.org.writers.compat import override_scope

        with pytest.raises(TypeError, match="override keys must be strings"):
            with override_scope("test.invalid.module", {("test.invalid.module", "attr"): "value"}):
                pass


class TestFreezeAndComposeOverrideMapping:
    """Test freeze_override_mapping and compose_override_mapping behavior."""

    def test_freeze_produces_immutable_mapping(self):
        """freeze_override_mapping must return an immutable MappingProxyType."""
        from types import MappingProxyType

        from cja_auto_sdr.org.writers.compat import freeze_override_mapping

        mutable = {("mod", "attr"): "value"}
        frozen = freeze_override_mapping(mutable)
        assert isinstance(frozen, MappingProxyType)
        with pytest.raises(TypeError):
            frozen[("mod", "new_attr")] = "new_value"

    def test_freeze_copies_source(self):
        """freeze_override_mapping must not be affected by mutations to the source dict."""
        from cja_auto_sdr.org.writers.compat import freeze_override_mapping

        mutable = {("mod", "attr"): "original"}
        frozen = freeze_override_mapping(mutable)
        mutable[("mod", "attr")] = "mutated"
        assert frozen[("mod", "attr")] == "original"

    def test_freeze_preserves_all_entries(self):
        """freeze_override_mapping must preserve all key-value pairs."""
        from cja_auto_sdr.org.writers.compat import freeze_override_mapping

        source = {("m1", "a1"): "v1", ("m2", "a2"): "v2"}
        frozen = freeze_override_mapping(source)
        assert dict(frozen) == source

    def test_compose_merges_multiple_mappings(self):
        """compose_override_mapping must merge entries from all provided mappings."""
        from cja_auto_sdr.org.writers.compat import compose_override_mapping

        m1 = {("mod1", "attr1"): "val1"}
        m2 = {("mod2", "attr2"): "val2"}
        composed = compose_override_mapping(m1, m2)
        assert ("mod1", "attr1") in composed
        assert ("mod2", "attr2") in composed
        assert len(composed) == 2

    def test_compose_returns_frozen_mapping(self):
        """compose_override_mapping must return an immutable MappingProxyType."""
        from types import MappingProxyType

        from cja_auto_sdr.org.writers.compat import compose_override_mapping

        composed = compose_override_mapping({"key": "val"})
        assert isinstance(composed, MappingProxyType)

    def test_compose_later_mappings_override_earlier(self):
        """compose_override_mapping must let later mappings override earlier ones."""
        from cja_auto_sdr.org.writers.compat import compose_override_mapping

        m1 = {("mod", "attr"): "first"}
        m2 = {("mod", "attr"): "second"}
        composed = compose_override_mapping(m1, m2)
        assert composed[("mod", "attr")] == "second"

    def test_compose_with_no_arguments_returns_empty(self):
        """compose_override_mapping with no arguments must return an empty frozen mapping."""
        from cja_auto_sdr.org.writers.compat import compose_override_mapping

        composed = compose_override_mapping()
        assert len(composed) == 0

    def test_compose_with_string_keys_preserves_them(self):
        """compose_override_mapping must handle string destination keys."""
        from cja_auto_sdr.org.writers.compat import compose_override_mapping

        m1 = {"simple_attr": "legacy_name"}
        composed = compose_override_mapping(m1)
        assert "simple_attr" in composed
        assert composed["simple_attr"] == "legacy_name"


class TestNormalizeOverrideMapping:
    """Direct unit tests for _normalize_override_mapping."""

    def test_string_keys_get_default_module(self):
        """Pure string keys must be normalized to (default_target_module_name, key)."""
        from cja_auto_sdr.org.writers.compat import _normalize_override_mapping

        result = _normalize_override_mapping(
            {"attr_a": "legacy_a", "attr_b": "legacy_b"},
            default_target_module_name="my.module",
        )
        assert result == {
            ("my.module", "attr_a"): "legacy_a",
            ("my.module", "attr_b"): "legacy_b",
        }

    def test_tuple_keys_pass_through(self):
        """Pure tuple keys must pass through unchanged."""
        from cja_auto_sdr.org.writers.compat import _normalize_override_mapping

        result = _normalize_override_mapping(
            {("explicit.mod", "attr_x"): "legacy_x"},
            default_target_module_name="default.mod",
        )
        assert result == {("explicit.mod", "attr_x"): "legacy_x"}

    def test_mixed_keys_normalize_correctly(self):
        """Mixed string and tuple keys must each normalize independently."""
        from cja_auto_sdr.org.writers.compat import _normalize_override_mapping

        result = _normalize_override_mapping(
            {
                "bare_attr": "legacy_bare",
                ("other.mod", "explicit_attr"): "legacy_explicit",
            },
            default_target_module_name="default.mod",
        )
        assert result == {
            ("default.mod", "bare_attr"): "legacy_bare",
            ("other.mod", "explicit_attr"): "legacy_explicit",
        }

    def test_empty_mapping_returns_empty(self):
        """Empty mapping must return empty dict."""
        from cja_auto_sdr.org.writers.compat import _normalize_override_mapping

        result = _normalize_override_mapping({}, default_target_module_name="any.mod")
        assert result == {}

    def test_tuple_key_ignores_default_module(self):
        """Tuple key's explicit module must take precedence over default_target_module_name."""
        from cja_auto_sdr.org.writers.compat import _normalize_override_mapping

        result = _normalize_override_mapping(
            {("specific.mod", "attr"): "legacy"},
            default_target_module_name="ignored.mod",
        )
        assert ("specific.mod", "attr") in result
        assert ("ignored.mod", "attr") not in result


def test_org_writers_trending_date_range_respects_package_root_timestamp_patch():
    """Package-root timestamp formatter patches must flow into _trending_date_range."""
    mod = importlib.import_module("cja_auto_sdr.org.writers")
    trending = _make_trending()

    with patch(
        "cja_auto_sdr.org.writers._format_trending_timestamp_short",
        side_effect=lambda ts: f"patched:{ts[5:7]}",
    ) as timestamp_mock:
        result = mod._trending_date_range(trending.snapshots)

    assert "patched:01" in result
    assert "patched:02" in result
    assert timestamp_mock.call_count == 2


def test_org_writers_trending_delta_csv_rows_respects_package_root_period_label_patch():
    """Package-root period label patches must flow into _trending_delta_csv_rows."""
    mod = importlib.import_module("cja_auto_sdr.org.writers")
    trending = _make_trending()

    with patch(
        "cja_auto_sdr.org.writers._format_trending_period_label",
        return_value="patched_period",
    ) as label_mock:
        rows = mod._trending_delta_csv_rows(trending.deltas)

    assert all(row["Period"] == "patched_period" for row in rows)
    assert label_mock.call_count == len(trending.deltas)
