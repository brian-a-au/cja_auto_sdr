"""Contract tests for output subpackage extraction.

These tests verify that symbols extracted from generator.py into the
output.diff subpackage are importable from their new canonical locations
and remain callable with the expected signatures.
"""

from __future__ import annotations

import importlib
from inspect import signature

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
