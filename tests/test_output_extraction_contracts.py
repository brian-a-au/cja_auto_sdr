"""Contract tests for output subpackage extraction.

These tests verify that symbols extracted from generator.py into the
output.diff subpackage are importable from their new canonical locations
and remain callable with the expected signatures.
"""

from __future__ import annotations

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
