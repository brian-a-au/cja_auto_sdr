"""Tests targeting diff output with inventory sections across all formats.

Covers uncovered lines in generator.py related to diff output when inventory
diffs (calc_metrics_diffs, segments_diffs) are populated, and inventory summary
display functions.
"""

from __future__ import annotations

import json
import logging
import os
from unittest.mock import MagicMock

from cja_auto_sdr.diff.models import (
    ChangeType,
    ComponentDiff,
    DiffResult,
    DiffSummary,
    InventoryItemDiff,
    MetadataDiff,
)
from cja_auto_sdr.generator import (
    _get_inventory_change_detail,
    display_inventory_summary,
    write_diff_console_output,
    write_diff_csv_output,
    write_diff_excel_output,
    write_diff_html_output,
    write_diff_json_output,
    write_diff_markdown_output,
    write_diff_output,
    write_diff_pr_comment_output,
)

# ==================== Helpers ====================


def _make_metadata(**overrides) -> MetadataDiff:
    """Build a minimal MetadataDiff with sensible defaults."""
    defaults = {
        "source_name": "Source DV",
        "target_name": "Target DV",
        "source_id": "dv_source",
        "target_id": "dv_target",
    }
    defaults.update(overrides)
    return MetadataDiff(**defaults)


def _make_summary_with_inventory(**overrides) -> DiffSummary:
    """Build a DiffSummary that includes inventory counts."""
    defaults = {
        "source_metrics_count": 10,
        "target_metrics_count": 12,
        "source_dimensions_count": 20,
        "target_dimensions_count": 22,
        "metrics_added": 2,
        "metrics_removed": 0,
        "metrics_modified": 1,
        "metrics_unchanged": 9,
        "dimensions_added": 3,
        "dimensions_removed": 1,
        "dimensions_modified": 2,
        "dimensions_unchanged": 16,
        # Inventory counts
        "source_calc_metrics_count": 5,
        "target_calc_metrics_count": 7,
        "calc_metrics_added": 2,
        "calc_metrics_removed": 0,
        "calc_metrics_modified": 1,
        "calc_metrics_unchanged": 4,
        "source_segments_count": 8,
        "target_segments_count": 9,
        "segments_added": 1,
        "segments_removed": 0,
        "segments_modified": 2,
        "segments_unchanged": 6,
    }
    defaults.update(overrides)
    return DiffSummary(**defaults)


def _make_component_diffs() -> list[ComponentDiff]:
    """Build a list of ComponentDiff entries for metrics or dimensions."""
    return [
        ComponentDiff(
            id="m1",
            name="Revenue",
            change_type=ChangeType.ADDED,
        ),
        ComponentDiff(
            id="m2",
            name="Conversions",
            change_type=ChangeType.MODIFIED,
            changed_fields={"description": ("old desc", "new desc")},
        ),
        ComponentDiff(
            id="m3",
            name="PageViews",
            change_type=ChangeType.UNCHANGED,
        ),
    ]


def _make_inventory_diffs(inv_type: str = "calculated_metric") -> list[InventoryItemDiff]:
    """Build a list of InventoryItemDiff entries."""
    return [
        InventoryItemDiff(
            id="cm1",
            name="Revenue Per Visit",
            change_type=ChangeType.ADDED,
            inventory_type=inv_type,
        ),
        InventoryItemDiff(
            id="cm2",
            name="Conversion Rate",
            change_type=ChangeType.MODIFIED,
            inventory_type=inv_type,
            changed_fields={"formula": ("A/B", "A/(B+C)"), "description": ("old", "new")},
        ),
        InventoryItemDiff(
            id="cm3",
            name="Bounce Rate",
            change_type=ChangeType.UNCHANGED,
            inventory_type=inv_type,
        ),
        InventoryItemDiff(
            id="cm4",
            name="Obsolete Metric",
            change_type=ChangeType.REMOVED,
            inventory_type=inv_type,
        ),
    ]


def _make_segment_diffs() -> list[InventoryItemDiff]:
    """Build segment inventory diffs."""
    return [
        InventoryItemDiff(
            id="s1",
            name="High Value Users",
            change_type=ChangeType.ADDED,
            inventory_type="segment",
        ),
        InventoryItemDiff(
            id="s2",
            name="Mobile Visitors",
            change_type=ChangeType.MODIFIED,
            inventory_type="segment",
            changed_fields={"definition_summary": ("visits > 5", "visits > 10")},
        ),
        InventoryItemDiff(
            id="s3",
            name="Existing Segment",
            change_type=ChangeType.UNCHANGED,
            inventory_type="segment",
        ),
    ]


def _make_diff_result_with_inventory(**overrides) -> DiffResult:
    """Build a DiffResult with populated inventory diffs."""
    defaults = {
        "summary": _make_summary_with_inventory(),
        "metadata_diff": _make_metadata(),
        "metric_diffs": _make_component_diffs(),
        "dimension_diffs": _make_component_diffs(),
        "source_label": "Before",
        "target_label": "After",
        "generated_at": "2025-01-15 12:00:00",
        "tool_version": "3.2.8",
        "calc_metrics_diffs": _make_inventory_diffs("calculated_metric"),
        "segments_diffs": _make_segment_diffs(),
    }
    defaults.update(overrides)
    return DiffResult(**defaults)


def _make_logger() -> logging.Logger:
    """Create a test logger that does not write to stdout."""
    logger = logging.getLogger("test_diff_inventory_output")
    logger.setLevel(logging.DEBUG)
    logger.handlers = []  # Remove all handlers
    logger.addHandler(logging.NullHandler())
    return logger


# ==================== Console output with inventory ====================


class TestConsoleOutputWithInventory:
    """Tests for write_diff_console_output when inventory diffs are populated."""

    def test_console_output_includes_inventory_header(self):
        result = _make_diff_result_with_inventory()
        output = write_diff_console_output(result, use_color=False)

        assert "INVENTORY" in output

    def test_console_output_includes_calc_metrics_summary_row(self):
        result = _make_diff_result_with_inventory()
        output = write_diff_console_output(result, use_color=False)

        assert "Calc Metrics" in output

    def test_console_output_includes_segments_summary_row(self):
        result = _make_diff_result_with_inventory()
        output = write_diff_console_output(result, use_color=False)

        assert "Segments" in output

    def test_console_output_includes_inventory_changes_section(self):
        result = _make_diff_result_with_inventory()
        output = write_diff_console_output(result, use_color=False)

        assert "INVENTORY CHANGES" in output

    def test_console_output_includes_calculated_metrics_changes(self):
        result = _make_diff_result_with_inventory()
        output = write_diff_console_output(result, use_color=False)

        assert "CALCULATED METRICS" in output
        assert "Revenue Per Visit" in output
        assert "Conversion Rate" in output

    def test_console_output_includes_segments_changes(self):
        result = _make_diff_result_with_inventory()
        output = write_diff_console_output(result, use_color=False)

        assert "SEGMENTS" in output
        assert "High Value Users" in output
        assert "Mobile Visitors" in output

    def test_console_output_inventory_change_detail_for_modified(self):
        result = _make_diff_result_with_inventory()
        output = write_diff_console_output(result, use_color=False)

        # Modified calc metric should show field changes
        assert "formula" in output
        assert "A/B" in output
        assert "A/(B+C)" in output

    def test_console_output_inventory_footer_includes_inventory_counts(self):
        result = _make_diff_result_with_inventory()
        output = write_diff_console_output(result, use_color=False)

        # Footer should include inventory summary lines
        assert "Calc Metrics: 2 added, 0 removed, 1 modified" in output
        assert "Segments: 1 added, 0 removed, 2 modified" in output

    def test_console_output_with_color_enabled(self):
        result = _make_diff_result_with_inventory()
        output = write_diff_console_output(result, use_color=True)

        # Should still contain the key text (with ANSI codes around it)
        assert "INVENTORY" in output
        assert "Calc Metrics" in output

    def test_console_output_summary_only_with_inventory(self):
        result = _make_diff_result_with_inventory()
        output = write_diff_console_output(result, summary_only=True, use_color=False)

        # Summary-only should still show the summary table with inventory rows
        assert "Calc Metrics" in output

    def test_console_output_changes_only_filters_unchanged_inventory(self):
        result = _make_diff_result_with_inventory()
        output = write_diff_console_output(result, changes_only=True, use_color=False)

        # "Existing Segment" and "Bounce Rate" are UNCHANGED, should not appear in changes section
        # But they may still appear in the summary table counts
        assert "INVENTORY CHANGES" in output

    def test_console_output_only_calc_metrics_no_segments(self):
        """Test output when only calc_metrics_diffs is present, no segments."""
        result = _make_diff_result_with_inventory(
            segments_diffs=None,
            summary=_make_summary_with_inventory(
                source_segments_count=0,
                target_segments_count=0,
                segments_added=0,
                segments_removed=0,
                segments_modified=0,
                segments_unchanged=0,
            ),
        )
        output = write_diff_console_output(result, use_color=False)

        assert "CALCULATED METRICS" in output
        # Should not have SEGMENTS section when segments_diffs is None
        assert "SEGMENTS" not in output

    def test_console_output_only_segments_no_calc_metrics(self):
        """Test output when only segments_diffs is present, no calc metrics."""
        result = _make_diff_result_with_inventory(
            calc_metrics_diffs=None,
            summary=_make_summary_with_inventory(
                source_calc_metrics_count=0,
                target_calc_metrics_count=0,
                calc_metrics_added=0,
                calc_metrics_removed=0,
                calc_metrics_modified=0,
                calc_metrics_unchanged=0,
            ),
        )
        output = write_diff_console_output(result, use_color=False)

        # Should have segments section
        assert "High Value Users" in output

    def test_console_inventory_no_changes_shows_no_changes_message(self):
        """When inventory diffs exist but all are UNCHANGED, show 'No changes'."""
        unchanged_calc = [
            InventoryItemDiff(id="cm1", name="X", change_type=ChangeType.UNCHANGED, inventory_type="calculated_metric"),
        ]
        unchanged_seg = [
            InventoryItemDiff(id="s1", name="Y", change_type=ChangeType.UNCHANGED, inventory_type="segment"),
        ]
        summary = _make_summary_with_inventory(
            calc_metrics_added=0,
            calc_metrics_removed=0,
            calc_metrics_modified=0,
            segments_added=0,
            segments_removed=0,
            segments_modified=0,
        )
        result = _make_diff_result_with_inventory(
            calc_metrics_diffs=unchanged_calc,
            segments_diffs=unchanged_seg,
            summary=summary,
        )
        output = write_diff_console_output(result, use_color=False)

        assert "No changes" in output


# ==================== JSON output with inventory ====================


class TestJsonOutputWithInventory:
    """Tests for write_diff_json_output when inventory diffs are populated."""

    def test_json_output_includes_inventory_summary(self, tmp_path):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        json_file = write_diff_json_output(result, "test_diff", str(tmp_path), logger)

        assert os.path.exists(json_file)
        with open(json_file) as f:
            data = json.load(f)

        assert "inventory_summary" in data
        assert "calculated_metrics" in data["inventory_summary"]
        assert "segments" in data["inventory_summary"]

    def test_json_output_inventory_summary_counts(self, tmp_path):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        json_file = write_diff_json_output(result, "test_diff", str(tmp_path), logger)

        with open(json_file) as f:
            data = json.load(f)

        calc = data["inventory_summary"]["calculated_metrics"]
        assert calc["source_count"] == 5
        assert calc["target_count"] == 7
        assert calc["added"] == 2
        assert calc["removed"] == 0
        assert calc["modified"] == 1

        seg = data["inventory_summary"]["segments"]
        assert seg["source_count"] == 8
        assert seg["target_count"] == 9
        assert seg["added"] == 1

    def test_json_output_includes_calc_metrics_diffs(self, tmp_path):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        json_file = write_diff_json_output(result, "test_diff", str(tmp_path), logger)

        with open(json_file) as f:
            data = json.load(f)

        assert "calculated_metrics_diffs" in data
        # Should include all diffs (not changes_only by default)
        assert len(data["calculated_metrics_diffs"]) == 4

    def test_json_output_includes_segments_diffs(self, tmp_path):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        json_file = write_diff_json_output(result, "test_diff", str(tmp_path), logger)

        with open(json_file) as f:
            data = json.load(f)

        assert "segments_diffs" in data
        assert len(data["segments_diffs"]) == 3

    def test_json_output_changes_only_filters_unchanged(self, tmp_path):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        json_file = write_diff_json_output(result, "test_diff", str(tmp_path), logger, changes_only=True)

        with open(json_file) as f:
            data = json.load(f)

        # Calc metrics: 4 total, 1 UNCHANGED = 3 remaining
        assert len(data["calculated_metrics_diffs"]) == 3
        # Segments: 3 total, 1 UNCHANGED = 2 remaining
        assert len(data["segments_diffs"]) == 2

    def test_json_output_inventory_diff_serialization(self, tmp_path):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        json_file = write_diff_json_output(result, "test_diff", str(tmp_path), logger)

        with open(json_file) as f:
            data = json.load(f)

        # Check that modified calc metric has changed_fields serialized
        modified_diffs = [d for d in data["calculated_metrics_diffs"] if d["change_type"] == "modified"]
        assert len(modified_diffs) == 1
        assert "formula" in modified_diffs[0]["changed_fields"]
        assert modified_diffs[0]["changed_fields"]["formula"]["source"] == "A/B"
        assert modified_diffs[0]["changed_fields"]["formula"]["target"] == "A/(B+C)"

    def test_json_output_no_inventory_when_not_present(self, tmp_path):
        result = _make_diff_result_with_inventory(
            calc_metrics_diffs=None,
            segments_diffs=None,
        )
        # Also zero out the summary counts
        result.summary = _make_summary_with_inventory(
            source_calc_metrics_count=0,
            target_calc_metrics_count=0,
            calc_metrics_added=0,
            calc_metrics_removed=0,
            calc_metrics_modified=0,
            calc_metrics_unchanged=0,
            source_segments_count=0,
            target_segments_count=0,
            segments_added=0,
            segments_removed=0,
            segments_modified=0,
            segments_unchanged=0,
        )
        logger = _make_logger()

        json_file = write_diff_json_output(result, "test_diff", str(tmp_path), logger)

        with open(json_file) as f:
            data = json.load(f)

        assert "inventory_summary" not in data
        assert "calculated_metrics_diffs" not in data
        assert "segments_diffs" not in data


# ==================== Markdown output with inventory ====================


class TestMarkdownOutputWithInventory:
    """Tests for write_diff_markdown_output when inventory diffs are populated."""

    def test_markdown_output_includes_inventory_summary_rows(self, tmp_path):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        md_file = write_diff_markdown_output(result, "test_diff", str(tmp_path), logger)

        assert os.path.exists(md_file)
        with open(md_file) as f:
            content = f.read()

        assert "**Calc Metrics**" in content
        assert "**Segments**" in content

    def test_markdown_output_includes_inventory_changes_section(self, tmp_path):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        md_file = write_diff_markdown_output(result, "test_diff", str(tmp_path), logger)

        with open(md_file) as f:
            content = f.read()

        assert "# Inventory Changes" in content
        assert "## Calculated Metrics Changes" in content
        assert "## Segments Changes" in content

    def test_markdown_output_inventory_change_details(self, tmp_path):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        md_file = write_diff_markdown_output(result, "test_diff", str(tmp_path), logger)

        with open(md_file) as f:
            content = f.read()

        assert "Revenue Per Visit" in content
        assert "Conversion Rate" in content
        assert "High Value Users" in content

    def test_markdown_output_inventory_no_changes_shows_message(self, tmp_path):
        unchanged_calc = [
            InventoryItemDiff(id="cm1", name="X", change_type=ChangeType.UNCHANGED, inventory_type="calculated_metric"),
        ]
        summary = _make_summary_with_inventory(
            calc_metrics_added=0,
            calc_metrics_removed=0,
            calc_metrics_modified=0,
            segments_added=0,
            segments_removed=0,
            segments_modified=0,
        )
        result = _make_diff_result_with_inventory(
            calc_metrics_diffs=unchanged_calc,
            segments_diffs=[
                InventoryItemDiff(id="s1", name="Y", change_type=ChangeType.UNCHANGED, inventory_type="segment"),
            ],
            summary=summary,
        )
        logger = _make_logger()

        md_file = write_diff_markdown_output(result, "test_diff", str(tmp_path), logger)

        with open(md_file) as f:
            content = f.read()

        assert "*No changes*" in content

    def test_markdown_output_changes_only_with_inventory(self, tmp_path):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        md_file = write_diff_markdown_output(result, "test_diff", str(tmp_path), logger, changes_only=True)

        assert os.path.exists(md_file)
        with open(md_file) as f:
            content = f.read()

        # Inventory changes section should exist
        assert "# Inventory Changes" in content

    def test_markdown_side_by_side_with_inventory(self, tmp_path):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        md_file = write_diff_markdown_output(result, "test_diff", str(tmp_path), logger, side_by_side=True)

        assert os.path.exists(md_file)
        with open(md_file) as f:
            content = f.read()

        # Side-by-side should show modified metrics detail
        assert "Modified Metrics - Side by Side" in content

    def test_markdown_side_by_side_escapes_pipe_and_empty_values(self):
        from cja_auto_sdr.output.diff.markdown import _format_markdown_side_by_side

        diff = ComponentDiff(
            id="m1",
            name="Escaping Test",
            change_type=ChangeType.MODIFIED,
            changed_fields={"description": (None, "new | value")},
        )

        content = "\n".join(_format_markdown_side_by_side(diff, "Before", "After"))

        assert "*(empty)*" in content
        assert "new \\| value" in content


# ==================== HTML output with inventory ====================


class TestHtmlOutputWithInventory:
    """Tests for write_diff_html_output when inventory diffs are populated."""

    def test_html_output_includes_inventory_summary_rows(self, tmp_path):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        html_file = write_diff_html_output(result, "test_diff", str(tmp_path), logger)

        assert os.path.exists(html_file)
        with open(html_file) as f:
            content = f.read()

        assert "<strong>Calc Metrics</strong>" in content
        assert "<strong>Segments</strong>" in content

    def test_html_output_includes_inventory_diff_tables(self, tmp_path):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        html_file = write_diff_html_output(result, "test_diff", str(tmp_path), logger)

        with open(html_file) as f:
            content = f.read()

        assert "Inventory Changes" in content
        assert "Calculated Metrics Changes" in content
        assert "Segments Changes" in content

    def test_html_output_inventory_diff_table_rows(self, tmp_path):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        html_file = write_diff_html_output(result, "test_diff", str(tmp_path), logger)

        with open(html_file) as f:
            content = f.read()

        # Check that inventory item names appear in the HTML
        assert "Revenue Per Visit" in content
        assert "Conversion Rate" in content
        assert "High Value Users" in content

    def test_html_output_inventory_badge_classes(self, tmp_path):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        html_file = write_diff_html_output(result, "test_diff", str(tmp_path), logger)

        with open(html_file) as f:
            content = f.read()

        # Badge classes should be present for inventory diff rows
        assert "badge-added" in content
        assert "badge-modified" in content
        assert "badge-removed" in content

    def test_html_output_changes_only_filters_inventory(self, tmp_path):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        html_file = write_diff_html_output(result, "test_diff", str(tmp_path), logger, changes_only=True)

        assert os.path.exists(html_file)

    def test_html_output_no_inventory_changes_shows_no_changes(self, tmp_path):
        unchanged_calc = [
            InventoryItemDiff(id="cm1", name="X", change_type=ChangeType.UNCHANGED, inventory_type="calculated_metric"),
        ]
        summary = _make_summary_with_inventory(
            calc_metrics_added=0,
            calc_metrics_removed=0,
            calc_metrics_modified=0,
            segments_added=0,
            segments_removed=0,
            segments_modified=0,
        )
        result = _make_diff_result_with_inventory(
            calc_metrics_diffs=unchanged_calc,
            segments_diffs=[
                InventoryItemDiff(id="s1", name="Y", change_type=ChangeType.UNCHANGED, inventory_type="segment"),
            ],
            summary=summary,
        )
        logger = _make_logger()

        html_file = write_diff_html_output(result, "test_diff", str(tmp_path), logger)

        with open(html_file) as f:
            content = f.read()

        assert "No changes" in content

    def test_html_output_escapes_metadata_and_diff_details(self, tmp_path):
        logger = _make_logger()
        result = DiffResult(
            summary=DiffSummary(
                source_metrics_count=1,
                target_metrics_count=1,
                source_dimensions_count=0,
                target_dimensions_count=0,
                metrics_modified=1,
                source_calc_metrics_count=1,
                target_calc_metrics_count=1,
                calc_metrics_modified=1,
            ),
            metadata_diff=_make_metadata(
                source_name="Source <script>",
                target_name="Target & Co",
                source_id="<src>",
                target_id="t&1",
            ),
            metric_diffs=[
                ComponentDiff(
                    id="m<script>",
                    name="Metric <unsafe>",
                    change_type=ChangeType.MODIFIED,
                    changed_fields={"description": ("old <b>", "new & better")},
                ),
            ],
            dimension_diffs=[],
            generated_at="2025-01-15 12:00:00",
            tool_version="3.2.8",
            calc_metrics_diffs=[
                InventoryItemDiff(
                    id="cm&1",
                    name="Calc <unsafe>",
                    change_type=ChangeType.MODIFIED,
                    inventory_type="calculated_metric",
                    changed_fields={"formula": ("old <expr>", "new & expr")},
                ),
            ],
            segments_diffs=None,
        )

        html_file = write_diff_html_output(result, "test_diff", str(tmp_path), logger)

        with open(html_file, encoding="utf-8") as f:
            content = f.read()

        assert "Source &lt;script&gt;" in content
        assert "Target &amp; Co" in content
        assert "<code>&lt;src&gt;</code>" in content
        assert "Metric &lt;unsafe&gt;" in content
        assert "Calc &lt;unsafe&gt;" in content
        assert "&lt;b&gt;" in content
        assert "new &amp; better" in content
        assert "old &lt;expr&gt;" in content
        assert "new &amp; expr" in content
        assert "Metric <unsafe>" not in content
        assert "Calc <unsafe>" not in content


# ==================== Excel output with inventory ====================


class TestExcelOutputWithInventory:
    """Tests for write_diff_excel_output when inventory diffs are populated."""

    def test_excel_output_creates_inventory_sheets(self, tmp_path):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        excel_file = write_diff_excel_output(result, "test_diff", str(tmp_path), logger)

        assert os.path.exists(excel_file)
        assert excel_file.endswith(".xlsx")

    def test_excel_output_changes_only_with_inventory(self, tmp_path):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        excel_file = write_diff_excel_output(result, "test_diff", str(tmp_path), logger, changes_only=True)

        assert os.path.exists(excel_file)

    def test_excel_output_summary_includes_inventory_rows(self, tmp_path):
        """Verify Excel summary sheet includes inventory component rows."""
        import pandas as pd

        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        excel_file = write_diff_excel_output(result, "test_diff", str(tmp_path), logger)

        summary_df = pd.read_excel(excel_file, sheet_name="Summary")
        components = summary_df["Component"].tolist()
        assert "Calc Metrics" in components
        assert "Segments" in components

    def test_excel_output_has_calc_metrics_diff_sheet(self, tmp_path):
        """Verify calc metrics diff sheet is created."""
        import pandas as pd

        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        excel_file = write_diff_excel_output(result, "test_diff", str(tmp_path), logger)

        calc_df = pd.read_excel(excel_file, sheet_name="Calc Metrics Diff")
        assert len(calc_df) > 0
        assert "ID" in calc_df.columns
        assert "Status" in calc_df.columns

    def test_excel_output_has_segments_diff_sheet(self, tmp_path):
        """Verify segments diff sheet is created."""
        import pandas as pd

        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        excel_file = write_diff_excel_output(result, "test_diff", str(tmp_path), logger)

        seg_df = pd.read_excel(excel_file, sheet_name="Segments Diff")
        assert len(seg_df) > 0

    def test_excel_output_inventory_empty_when_no_changes(self, tmp_path):
        """When all inventory items are unchanged and changes_only=True, sheet should show 'No changes'."""
        import pandas as pd

        unchanged_calc = [
            InventoryItemDiff(id="cm1", name="X", change_type=ChangeType.UNCHANGED, inventory_type="calculated_metric"),
        ]
        result = _make_diff_result_with_inventory(calc_metrics_diffs=unchanged_calc)
        logger = _make_logger()

        excel_file = write_diff_excel_output(result, "test_diff", str(tmp_path), logger, changes_only=True)

        calc_df = pd.read_excel(excel_file, sheet_name="Calc Metrics Diff")
        # When changes_only and all unchanged, should get "No changes" message
        assert "No changes" in str(calc_df.values)


# ==================== CSV output with inventory ====================


class TestCsvOutputWithInventory:
    """Tests for write_diff_csv_output when inventory diffs are populated."""

    def test_csv_output_creates_inventory_files(self, tmp_path):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        csv_dir = write_diff_csv_output(result, "test_diff", str(tmp_path), logger)

        assert os.path.isdir(csv_dir)
        assert os.path.exists(os.path.join(csv_dir, "calc_metrics_diff.csv"))
        assert os.path.exists(os.path.join(csv_dir, "segments_diff.csv"))

    def test_csv_output_summary_includes_inventory_rows(self, tmp_path):
        import pandas as pd

        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        csv_dir = write_diff_csv_output(result, "test_diff", str(tmp_path), logger)

        summary_df = pd.read_csv(os.path.join(csv_dir, "summary.csv"))
        components = summary_df["Component"].tolist()
        assert "Calc_Metrics" in components
        assert "Segments" in components

    def test_csv_output_calc_metrics_file_content(self, tmp_path):
        import pandas as pd

        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        csv_dir = write_diff_csv_output(result, "test_diff", str(tmp_path), logger)

        calc_df = pd.read_csv(os.path.join(csv_dir, "calc_metrics_diff.csv"))
        assert len(calc_df) == 4  # All 4 entries
        assert "status" in calc_df.columns
        assert "id" in calc_df.columns

    def test_csv_output_segments_file_content(self, tmp_path):
        import pandas as pd

        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        csv_dir = write_diff_csv_output(result, "test_diff", str(tmp_path), logger)

        seg_df = pd.read_csv(os.path.join(csv_dir, "segments_diff.csv"))
        assert len(seg_df) == 3

    def test_csv_output_changes_only_filters_unchanged(self, tmp_path):
        import pandas as pd

        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        csv_dir = write_diff_csv_output(result, "test_diff", str(tmp_path), logger, changes_only=True)

        calc_df = pd.read_csv(os.path.join(csv_dir, "calc_metrics_diff.csv"))
        # 4 total, 1 UNCHANGED = 3 remaining
        assert len(calc_df) == 3

        seg_df = pd.read_csv(os.path.join(csv_dir, "segments_diff.csv"))
        # 3 total, 1 UNCHANGED = 2 remaining
        assert len(seg_df) == 2

    def test_csv_output_no_inventory_files_when_not_present(self, tmp_path):
        result = _make_diff_result_with_inventory(calc_metrics_diffs=None, segments_diffs=None)
        logger = _make_logger()

        csv_dir = write_diff_csv_output(result, "test_diff", str(tmp_path), logger)

        assert not os.path.exists(os.path.join(csv_dir, "calc_metrics_diff.csv"))
        assert not os.path.exists(os.path.join(csv_dir, "segments_diff.csv"))

    def test_csv_output_inventory_change_percent(self, tmp_path):
        import pandas as pd

        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        csv_dir = write_diff_csv_output(result, "test_diff", str(tmp_path), logger)

        summary_df = pd.read_csv(os.path.join(csv_dir, "summary.csv"))
        calc_row = summary_df[summary_df["Component"] == "Calc_Metrics"]
        assert len(calc_row) == 1
        assert calc_row.iloc[0]["Added"] == 2


# ==================== PR comment output with inventory ====================


class TestPrCommentOutputWithInventory:
    """Tests for write_diff_pr_comment_output (PR comment format)."""

    def test_pr_comment_basic_structure(self):
        result = _make_diff_result_with_inventory()
        output = write_diff_pr_comment_output(result)

        assert "Data View Comparison" in output
        assert "**Before**" in output
        assert "**After**" in output

    def test_pr_comment_includes_summary_table(self):
        result = _make_diff_result_with_inventory()
        output = write_diff_pr_comment_output(result)

        assert "| Metrics |" in output
        assert "| Dimensions |" in output

    def test_pr_comment_includes_metric_changes_section(self):
        result = _make_diff_result_with_inventory()
        output = write_diff_pr_comment_output(result)

        # Metrics changes collapsible section
        assert "Metrics Changes" in output

    def test_pr_comment_includes_natural_language_summary(self):
        result = _make_diff_result_with_inventory()
        output = write_diff_pr_comment_output(result)

        # Natural language summary should include inventory info
        assert "**Summary:**" in output

    def test_pr_comment_includes_version_footer(self):
        result = _make_diff_result_with_inventory()
        output = write_diff_pr_comment_output(result)

        assert "CJA SDR Generator" in output


# ==================== _get_inventory_change_detail ====================


class TestGetInventoryChangeDetail:
    """Tests for the _get_inventory_change_detail helper."""

    def test_modified_with_changed_fields(self):
        diff = InventoryItemDiff(
            id="cm1",
            name="Test",
            change_type=ChangeType.MODIFIED,
            inventory_type="calculated_metric",
            changed_fields={"formula": ("old_f", "new_f"), "description": ("old_d", "new_d")},
        )
        detail = _get_inventory_change_detail(diff)

        assert "formula" in detail
        assert "old_f" in detail
        assert "new_f" in detail
        assert "description" in detail

    def test_added_returns_empty(self):
        diff = InventoryItemDiff(
            id="cm1",
            name="Test",
            change_type=ChangeType.ADDED,
            inventory_type="calculated_metric",
        )
        detail = _get_inventory_change_detail(diff)
        assert detail == ""

    def test_removed_returns_empty(self):
        diff = InventoryItemDiff(
            id="cm1",
            name="Test",
            change_type=ChangeType.REMOVED,
            inventory_type="calculated_metric",
        )
        detail = _get_inventory_change_detail(diff)
        assert detail == ""

    def test_unchanged_returns_empty(self):
        diff = InventoryItemDiff(
            id="cm1",
            name="Test",
            change_type=ChangeType.UNCHANGED,
            inventory_type="calculated_metric",
        )
        detail = _get_inventory_change_detail(diff)
        assert detail == ""

    def test_modified_no_changed_fields_returns_empty(self):
        diff = InventoryItemDiff(
            id="cm1",
            name="Test",
            change_type=ChangeType.MODIFIED,
            inventory_type="calculated_metric",
            changed_fields={},
        )
        detail = _get_inventory_change_detail(diff)
        assert detail == ""

    def test_truncation(self):
        long_val = "x" * 100
        diff = InventoryItemDiff(
            id="cm1",
            name="Test",
            change_type=ChangeType.MODIFIED,
            inventory_type="calculated_metric",
            changed_fields={"field": (long_val, "short")},
        )
        detail = _get_inventory_change_detail(diff, truncate=True)
        # Value should be truncated to max_len=30 — full 100-char value must not appear
        assert long_val not in detail
        assert "x" * 30 in detail

    def test_no_truncation(self):
        long_val = "x" * 100
        diff = InventoryItemDiff(
            id="cm1",
            name="Test",
            change_type=ChangeType.MODIFIED,
            inventory_type="calculated_metric",
            changed_fields={"field": (long_val, "short")},
        )
        detail = _get_inventory_change_detail(diff, truncate=False)
        assert long_val in detail


# ==================== write_diff_output dispatcher with inventory ====================


class TestWriteDiffOutputDispatcher:
    """Tests for write_diff_output with inventory data across different formats."""

    def test_dispatch_console_with_inventory(self, capsys):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        output = write_diff_output(result, "console", "test", "/tmp/test_diff_out", logger, use_color=False)

        assert output is not None
        assert "INVENTORY" in output

    def test_dispatch_json_with_inventory(self, tmp_path):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        write_diff_output(result, "json", "test_diff", str(tmp_path), logger)

        json_file = os.path.join(str(tmp_path), "test_diff.json")
        assert os.path.exists(json_file)

    def test_dispatch_markdown_with_inventory(self, tmp_path):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        write_diff_output(result, "markdown", "test_diff", str(tmp_path), logger)

        md_file = os.path.join(str(tmp_path), "test_diff.md")
        assert os.path.exists(md_file)

    def test_dispatch_html_with_inventory(self, tmp_path):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        write_diff_output(result, "html", "test_diff", str(tmp_path), logger)

        html_file = os.path.join(str(tmp_path), "test_diff.html")
        assert os.path.exists(html_file)

    def test_dispatch_excel_with_inventory(self, tmp_path):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        write_diff_output(result, "excel", "test_diff", str(tmp_path), logger)

        excel_file = os.path.join(str(tmp_path), "test_diff.xlsx")
        assert os.path.exists(excel_file)

    def test_dispatch_csv_with_inventory(self, tmp_path):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        write_diff_output(result, "csv", "test_diff", str(tmp_path), logger)

        csv_dir = os.path.join(str(tmp_path), "test_diff_csv")
        assert os.path.isdir(csv_dir)

    def test_dispatch_pr_comment_with_inventory(self, capsys):
        result = _make_diff_result_with_inventory()
        logger = _make_logger()

        output = write_diff_output(result, "pr-comment", "test_diff", "/tmp/test_diff_out", logger)

        assert output is not None
        assert "Data View Comparison" in output


# ==================== display_inventory_summary ====================


class TestDisplayInventorySummary:
    """Tests for display_inventory_summary function."""

    def _make_segments_inventory(self):
        """Create a mock segments inventory object."""
        inv = MagicMock()
        inv.segments = [
            MagicMock(segment_name="Seg A", complexity_score=80, definition_summary="visits > 5"),
            MagicMock(segment_name="Seg B", complexity_score=30, definition_summary="page = home"),
        ]
        inv.get_summary.return_value = {
            "total_segments": 2,
            "governance": {"approved_count": 1, "shared_count": 1, "tagged_count": 0},
            "container_types": {"visitor": 1, "visit": 1},
            "complexity": {
                "average": 55.0,
                "max": 80.0,
                "high_complexity_count": 1,
                "elevated_complexity_count": 0,
            },
        }
        return inv

    def _make_calculated_inventory(self):
        """Create a mock calculated metrics inventory object."""
        inv = MagicMock()
        inv.metrics = [
            MagicMock(metric_name="RPV", complexity_score=75, formula_summary="revenue / visits"),
            MagicMock(metric_name="CVR", complexity_score=40, formula_summary="conversions / visits"),
        ]
        inv.get_summary.return_value = {
            "total_calculated_metrics": 2,
            "governance": {"approved_count": 1, "shared_count": 2, "tagged_count": 1},
            "complexity": {
                "average": 57.5,
                "max": 75.0,
                "high_complexity_count": 1,
                "elevated_complexity_count": 0,
            },
        }
        return inv

    def _make_derived_inventory(self):
        """Create a mock derived fields inventory object."""
        inv = MagicMock()
        inv.fields = [
            MagicMock(component_name="DF1", complexity_score=90, logic_summary="if condition then A else B"),
            MagicMock(component_name="DF2", complexity_score=20, logic_summary="simple concat"),
        ]
        inv.get_summary.return_value = {
            "total_derived_fields": 2,
            "metrics_count": 1,
            "dimensions_count": 1,
            "complexity": {
                "average": 55.0,
                "max": 90.0,
                "high_complexity_count": 1,
                "elevated_complexity_count": 0,
            },
        }
        return inv

    def test_display_with_segments_inventory(self, capsys):
        seg_inv = self._make_segments_inventory()
        result = display_inventory_summary(
            data_view_id="dv_test",
            data_view_name="Test DV",
            segments_inventory=seg_inv,
            output_format="console",
        )

        assert "inventories" in result
        assert "segments" in result["inventories"]

        captured = capsys.readouterr()
        assert "Segments" in captured.out
        assert "Total:" in captured.out

    def test_display_with_calculated_inventory(self, capsys):
        calc_inv = self._make_calculated_inventory()
        result = display_inventory_summary(
            data_view_id="dv_test",
            data_view_name="Test DV",
            calculated_inventory=calc_inv,
            output_format="console",
        )

        assert "calculated_metrics" in result["inventories"]

        captured = capsys.readouterr()
        assert "Calculated Metrics" in captured.out

    def test_display_with_derived_inventory(self, capsys):
        derived_inv = self._make_derived_inventory()
        result = display_inventory_summary(
            data_view_id="dv_test",
            data_view_name="Test DV",
            derived_inventory=derived_inv,
            output_format="console",
        )

        assert "derived_fields" in result["inventories"]

        captured = capsys.readouterr()
        assert "Derived Fields" in captured.out

    def test_display_all_inventories(self, capsys):
        seg_inv = self._make_segments_inventory()
        calc_inv = self._make_calculated_inventory()
        derived_inv = self._make_derived_inventory()

        result = display_inventory_summary(
            data_view_id="dv_test",
            data_view_name="Test DV",
            segments_inventory=seg_inv,
            calculated_inventory=calc_inv,
            derived_inventory=derived_inv,
            output_format="console",
        )

        assert "segments" in result["inventories"]
        assert "calculated_metrics" in result["inventories"]
        assert "derived_fields" in result["inventories"]

    def test_display_high_complexity_items_collected(self, capsys):
        seg_inv = self._make_segments_inventory()
        calc_inv = self._make_calculated_inventory()
        derived_inv = self._make_derived_inventory()

        result = display_inventory_summary(
            data_view_id="dv_test",
            data_view_name="Test DV",
            segments_inventory=seg_inv,
            calculated_inventory=calc_inv,
            derived_inventory=derived_inv,
            output_format="console",
        )

        # High complexity items should be collected (score >= 70)
        assert len(result["high_complexity_items"]) == 3  # DF1=90, Seg A=80, RPV=75
        # Should be sorted by complexity descending
        scores = [item["complexity"] for item in result["high_complexity_items"]]
        assert scores == sorted(scores, reverse=True)

    def test_display_high_complexity_item_summary_is_truncated(self):
        calc_inv = MagicMock()
        calc_inv.metrics = [
            MagicMock(
                metric_name="Very Complex Metric",
                complexity_score=88,
                formula_summary="very long formula " * 8,
            ),
        ]
        calc_inv.get_summary.return_value = {
            "total_calculated_metrics": 1,
            "governance": {"approved_count": 0, "shared_count": 0, "tagged_count": 0},
            "complexity": {
                "average": 88.0,
                "max": 88.0,
                "high_complexity_count": 1,
                "elevated_complexity_count": 0,
            },
        }

        result = display_inventory_summary(
            data_view_id="dv_test",
            data_view_name="Test DV",
            calculated_inventory=calc_inv,
            output_format="console",
            quiet=True,
        )

        item = result["high_complexity_items"][0]
        assert item["summary"].endswith("...")
        assert len(item["summary"]) == 63

    def test_display_quiet_mode_suppresses_output(self, capsys):
        seg_inv = self._make_segments_inventory()

        result = display_inventory_summary(
            data_view_id="dv_test",
            data_view_name="Test DV",
            segments_inventory=seg_inv,
            output_format="console",
            quiet=True,
        )

        captured = capsys.readouterr()
        assert captured.out == ""

        # Result dict should still be populated
        assert "segments" in result["inventories"]

    def test_display_json_output(self, tmp_path, capsys):
        seg_inv = self._make_segments_inventory()

        summary = display_inventory_summary(
            data_view_id="dv_test",
            data_view_name="Test DV",
            segments_inventory=seg_inv,
            output_format="json",
            output_dir=str(tmp_path),
        )
        assert summary["data_view_id"] == "dv_test"

        # Should have created a JSON file
        json_files = [f for f in os.listdir(str(tmp_path)) if f.endswith(".json")]
        assert len(json_files) == 1

    def test_display_json_output_sanitizes_and_truncates_filename(self, tmp_path):
        import re

        seg_inv = self._make_segments_inventory()
        long_name = "Prod / Main: Segments? <Unsafe> " + ("x" * 80)

        display_inventory_summary(
            data_view_id="dv_test",
            data_view_name=long_name,
            segments_inventory=seg_inv,
            output_format="json",
            output_dir=str(tmp_path),
            quiet=True,
        )

        json_files = list(tmp_path.glob("*_inventory_summary.json"))
        assert len(json_files) == 1

        safe_name = json_files[0].name.removesuffix("_inventory_summary.json")
        assert len(safe_name) <= 50
        assert re.fullmatch(r"[\w-]+", safe_name)

    def test_display_all_format_creates_json_and_console(self, tmp_path, capsys):
        seg_inv = self._make_segments_inventory()

        summary = display_inventory_summary(
            data_view_id="dv_test",
            data_view_name="Test DV",
            segments_inventory=seg_inv,
            output_format="all",
            output_dir=str(tmp_path),
        )
        assert summary["data_view_id"] == "dv_test"

        captured = capsys.readouterr()
        assert "Segments" in captured.out

        json_files = [f for f in os.listdir(str(tmp_path)) if f.endswith(".json")]
        assert len(json_files) == 1

    def test_display_custom_inventory_order(self, capsys):
        seg_inv = self._make_segments_inventory()
        calc_inv = self._make_calculated_inventory()
        derived_inv = self._make_derived_inventory()

        summary = display_inventory_summary(
            data_view_id="dv_test",
            data_view_name="Test DV",
            segments_inventory=seg_inv,
            calculated_inventory=calc_inv,
            derived_inventory=derived_inv,
            output_format="console",
            inventory_order=["derived", "segments", "calculated"],
        )
        assert summary["data_view_id"] == "dv_test"

        captured = capsys.readouterr()
        # All three should be present
        assert "Derived Fields" in captured.out
        assert "Segments" in captured.out
        assert "Calculated Metrics" in captured.out

        # Check order: derived should appear before segments
        idx_derived = captured.out.index("Derived Fields")
        idx_segments = captured.out.index("Segments")
        idx_calc = captured.out.index("Calculated Metrics")
        assert idx_derived < idx_segments < idx_calc

    def test_display_no_inventories_returns_empty(self):
        result = display_inventory_summary(
            data_view_id="dv_test",
            data_view_name="Test DV",
            output_format="console",
            quiet=True,
        )

        assert result["inventories"] == {}
        assert result["high_complexity_items"] == []

    def test_display_segments_governance_fields(self, capsys):
        seg_inv = self._make_segments_inventory()

        result = display_inventory_summary(
            data_view_id="dv_test",
            data_view_name="Test DV",
            segments_inventory=seg_inv,
            output_format="console",
        )
        assert result is not None

        captured = capsys.readouterr()
        assert "Approved:" in captured.out
        assert "Shared:" in captured.out
        assert "Tagged:" in captured.out
        assert "Containers:" in captured.out

    def test_display_calculated_governance_fields(self, capsys):
        calc_inv = self._make_calculated_inventory()

        result = display_inventory_summary(
            data_view_id="dv_test",
            data_view_name="Test DV",
            calculated_inventory=calc_inv,
            output_format="console",
        )
        assert result is not None

        captured = capsys.readouterr()
        assert "Approved:" in captured.out
        assert "Shared:" in captured.out

    def test_display_complexity_warning_shown(self, capsys):
        seg_inv = self._make_segments_inventory()

        result = display_inventory_summary(
            data_view_id="dv_test",
            data_view_name="Test DV",
            segments_inventory=seg_inv,
            output_format="console",
        )
        assert result is not None

        captured = capsys.readouterr()
        # High complexity count >= 1 so warning should appear
        assert "High (>=75):" in captured.out

    def test_display_derived_metrics_dimensions_counts(self, capsys):
        derived_inv = self._make_derived_inventory()

        result = display_inventory_summary(
            data_view_id="dv_test",
            data_view_name="Test DV",
            derived_inventory=derived_inv,
            output_format="console",
        )
        assert result is not None

        captured = capsys.readouterr()
        assert "Metrics:" in captured.out
        assert "Dimensions:" in captured.out


# ==================== Console output: inventory summary counts in SUMMARY ====================


class TestConsoleSummaryInventoryRows:
    """Test the SUMMARY table rows for inventory in console output (lines 3048-3097)."""

    def test_summary_table_calc_metrics_added_colored(self):
        """When calc_metrics_added > 0, it should appear in green (or plain with color off)."""
        result = _make_diff_result_with_inventory()
        output = write_diff_console_output(result, use_color=False)

        # Should contain the calc metrics line with counts
        assert "+2" in output  # calc_metrics_added
        assert "~1" in output  # calc_metrics_modified

    def test_summary_table_segments_row_present(self):
        result = _make_diff_result_with_inventory()
        output = write_diff_console_output(result, use_color=False)

        # Segments row should show counts
        lines = output.split("\n")
        segments_lines = [line for line in lines if "Segments" in line and "8" in line]
        assert len(segments_lines) >= 1  # At least the summary table row

    def test_summary_table_no_inventory_when_counts_zero(self):
        """When all inventory counts are 0, inventory section should not appear in summary."""
        summary = DiffSummary(
            source_metrics_count=5,
            target_metrics_count=5,
            metrics_unchanged=5,
            source_dimensions_count=3,
            target_dimensions_count=3,
            dimensions_unchanged=3,
        )
        result = DiffResult(
            summary=summary,
            metadata_diff=_make_metadata(),
            metric_diffs=[
                ComponentDiff(id="m1", name="M1", change_type=ChangeType.UNCHANGED),
            ],
            dimension_diffs=[
                ComponentDiff(id="d1", name="D1", change_type=ChangeType.UNCHANGED),
            ],
            generated_at="2025-01-15 12:00:00",
            tool_version="3.2.8",
        )
        output = write_diff_console_output(result, use_color=False)

        # INVENTORY header should not appear
        assert "INVENTORY CHANGES" not in output


# ==================== Side-by-side with inventory ====================


class TestSideBySideWithInventory:
    """Test side-by-side display mode with inventory data present."""

    def test_side_by_side_console_with_inventory(self):
        result = _make_diff_result_with_inventory()
        output = write_diff_console_output(result, side_by_side=True, use_color=False)

        # Should still contain inventory section
        assert "INVENTORY CHANGES" in output
        # Source/target labels should appear in side-by-side columns
        assert "Before" in output
        assert "After" in output


# ==================== Edge cases ====================


class TestInventoryEdgeCases:
    """Edge cases for inventory diff output."""

    def test_empty_inventory_lists(self):
        """Empty inventory diff lists (not None) with zero counts should not show inventory section."""
        summary = _make_summary_with_inventory(
            source_calc_metrics_count=0,
            target_calc_metrics_count=0,
            calc_metrics_added=0,
            calc_metrics_removed=0,
            calc_metrics_modified=0,
            calc_metrics_unchanged=0,
            source_segments_count=0,
            target_segments_count=0,
            segments_added=0,
            segments_removed=0,
            segments_modified=0,
            segments_unchanged=0,
        )
        result = _make_diff_result_with_inventory(
            calc_metrics_diffs=[],
            segments_diffs=[],
            summary=summary,
        )
        output = write_diff_console_output(result, use_color=False)

        # has_inventory_diffs should be False since both lists are empty
        # (empty list is falsy in Python, so has_inventory_diffs returns False)
        assert "INVENTORY CHANGES" not in output

    def test_inventory_with_none_changed_fields(self):
        """InventoryItemDiff with changed_fields=None for MODIFIED type."""
        diff = InventoryItemDiff(
            id="cm1",
            name="Test",
            change_type=ChangeType.MODIFIED,
            inventory_type="calculated_metric",
        )
        # __post_init__ sets changed_fields to {}
        detail = _get_inventory_change_detail(diff)
        assert detail == ""

    def test_large_number_of_inventory_diffs_json(self, tmp_path):
        """Test with many inventory diffs to ensure JSON handles them."""
        many_diffs = [
            InventoryItemDiff(
                id=f"cm{i}",
                name=f"Metric {i}",
                change_type=ChangeType.ADDED if i % 3 == 0 else ChangeType.MODIFIED,
                inventory_type="calculated_metric",
                changed_fields={"field": ("old", "new")} if i % 3 != 0 else None,
            )
            for i in range(50)
        ]
        result = _make_diff_result_with_inventory(calc_metrics_diffs=many_diffs)
        logger = _make_logger()

        json_file = write_diff_json_output(result, "test_diff", str(tmp_path), logger)

        with open(json_file) as f:
            data = json.load(f)

        assert len(data["calculated_metrics_diffs"]) == 50

    def test_inventory_diff_with_none_values_in_changed_fields(self):
        """Test that None values in changed_fields are handled gracefully."""
        diff = InventoryItemDiff(
            id="cm1",
            name="Test",
            change_type=ChangeType.MODIFIED,
            inventory_type="calculated_metric",
            changed_fields={"description": (None, "new desc")},
        )
        detail = _get_inventory_change_detail(diff)
        assert "(empty)" in detail
        assert "new desc" in detail

    def test_console_output_total_line_includes_inventory(self):
        """Total line at footer should account for inventory changes."""
        result = _make_diff_result_with_inventory()
        output = write_diff_console_output(result, use_color=False)

        # total_added from summary includes inventory
        # metrics_added=2, dims_added=3, calc_added=2, seg_added=1 = 8 total added
        assert "8 added" in output
