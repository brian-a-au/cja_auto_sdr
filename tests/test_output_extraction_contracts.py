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
