"""HTML diff file output writer.

Extracted from generator.py. Provides:
- write_diff_html_output: Write diff comparison to HTML format with professional styling
"""

from __future__ import annotations

import html
import logging
import os
from pathlib import Path
from typing import Any

from cja_auto_sdr.core.colors import _format_error_msg
from cja_auto_sdr.diff.models import (
    ChangeType,
    ComponentDiff,
    DiffResult,
    InventoryItemDiff,
)
from cja_auto_sdr.output.diff.common import (
    _get_change_detail,
    _get_inventory_change_detail,
)

__all__ = [
    "write_diff_html_output",
]


def write_diff_html_output(
    diff_result: DiffResult,
    base_filename: str,
    output_dir: str | Path,
    logger: logging.Logger,
    changes_only: bool = False,
) -> str:
    """
    Write diff comparison to HTML format with professional styling.

    Args:
        diff_result: The DiffResult to output
        base_filename: Base filename without extension
        output_dir: Output directory path
        logger: Logger instance
        changes_only: Only include changed items

    Returns:
        Path to HTML output file
    """
    try:
        logger.info("Generating diff HTML output...")

        _html_escape = html.escape  # Capture before nested functions shadow 'html'

        def _safe_html_escape(value: Any) -> str:
            """Escape arbitrary values safely for HTML rendering."""
            return _html_escape("" if value is None else str(value))

        summary = diff_result.summary
        meta = diff_result.metadata_diff
        html_parts = []

        # HTML header with CSS
        html_parts.append("""
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Data View Comparison Report</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            margin: 0;
            padding: 20px;
            background-color: #f5f5f5;
            color: #333;
        }
        .container {
            max-width: 1400px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            box-shadow: 0 0 10px rgba(0,0,0,0.1);
            border-radius: 8px;
        }
        h1 {
            color: #2c3e50;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }
        h2 {
            color: #34495e;
            margin-top: 30px;
            border-left: 4px solid #3498db;
            padding-left: 15px;
        }
        .metadata {
            background-color: #ecf0f1;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }
        .summary-table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }
        .summary-table th, .summary-table td {
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }
        .summary-table th {
            background-color: #3498db;
            color: white;
        }
        .diff-table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            font-size: 14px;
        }
        .diff-table th {
            background-color: #34495e;
            color: white;
            padding: 12px;
            text-align: left;
        }
        .diff-table td {
            padding: 10px 12px;
            border-bottom: 1px solid #ddd;
        }
        .row-added {
            background-color: #d4edda !important;
        }
        .row-removed {
            background-color: #f8d7da !important;
        }
        .row-modified {
            background-color: #fff3cd !important;
        }
        .badge {
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 12px;
        }
        .badge-added { background-color: #28a745; color: white; }
        .badge-removed { background-color: #dc3545; color: white; }
        .badge-modified { background-color: #ffc107; color: black; }
        .no-changes {
            color: #28a745;
            font-weight: bold;
            font-size: 18px;
            text-align: center;
            padding: 20px;
        }
        .total-changes {
            font-size: 18px;
            font-weight: bold;
            margin: 20px 0;
        }
        .footer {
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #ddd;
            text-align: center;
            color: #7f8c8d;
            font-size: 12px;
        }
        code {
            background-color: #f8f9fa;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: 'Consolas', monospace;
            font-size: 13px;
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Data View Comparison Report</h1>
""")

        # Metadata section
        html_parts.append(f"""
        <div class="metadata">
            <p><strong>{_safe_html_escape(diff_result.source_label)}:</strong> {_safe_html_escape(meta.source_name)} (<code>{_safe_html_escape(meta.source_id)}</code>)</p>
            <p><strong>{_safe_html_escape(diff_result.target_label)}:</strong> {_safe_html_escape(meta.target_name)} (<code>{_safe_html_escape(meta.target_id)}</code>)</p>
            <p><strong>Generated:</strong> {_safe_html_escape(diff_result.generated_at)}</p>
        </div>
""")

        # Summary table
        html_parts.append(f"""
        <h2>Summary</h2>
        <table class="summary-table">
            <tr>
                <th>Component</th>
                <th>{_safe_html_escape(diff_result.source_label)}</th>
                <th>{_safe_html_escape(diff_result.target_label)}</th>
                <th>Added</th>
                <th>Removed</th>
                <th>Modified</th>
                <th>Unchanged</th>
                <th>Changed</th>
            </tr>
            <tr>
                <td>Metrics</td>
                <td>{summary.source_metrics_count}</td>
                <td>{summary.target_metrics_count}</td>
                <td><span class="badge badge-added">+{summary.metrics_added}</span></td>
                <td><span class="badge badge-removed">-{summary.metrics_removed}</span></td>
                <td><span class="badge badge-modified">~{summary.metrics_modified}</span></td>
                <td>{summary.metrics_unchanged}</td>
                <td>{summary.metrics_change_percent:.1f}%</td>
            </tr>
            <tr>
                <td>Dimensions</td>
                <td>{summary.source_dimensions_count}</td>
                <td>{summary.target_dimensions_count}</td>
                <td><span class="badge badge-added">+{summary.dimensions_added}</span></td>
                <td><span class="badge badge-removed">-{summary.dimensions_removed}</span></td>
                <td><span class="badge badge-modified">~{summary.dimensions_modified}</span></td>
                <td>{summary.dimensions_unchanged}</td>
                <td>{summary.dimensions_change_percent:.1f}%</td>
            </tr>
        </table>
""")

        # Add inventory rows to summary if present
        if diff_result.has_inventory_diffs:
            inv_rows = []
            if summary.source_calc_metrics_count > 0 or summary.target_calc_metrics_count > 0:
                inv_rows.append(f"""
            <tr>
                <td><strong>Calc Metrics</strong></td>
                <td>{summary.source_calc_metrics_count}</td>
                <td>{summary.target_calc_metrics_count}</td>
                <td><span class="badge badge-added">+{summary.calc_metrics_added}</span></td>
                <td><span class="badge badge-removed">-{summary.calc_metrics_removed}</span></td>
                <td><span class="badge badge-modified">~{summary.calc_metrics_modified}</span></td>
                <td>{summary.calc_metrics_unchanged}</td>
                <td>-</td>
            </tr>""")
            if summary.source_segments_count > 0 or summary.target_segments_count > 0:
                inv_rows.append(f"""
            <tr>
                <td><strong>Segments</strong></td>
                <td>{summary.source_segments_count}</td>
                <td>{summary.target_segments_count}</td>
                <td><span class="badge badge-added">+{summary.segments_added}</span></td>
                <td><span class="badge badge-removed">-{summary.segments_removed}</span></td>
                <td><span class="badge badge-modified">~{summary.segments_modified}</span></td>
                <td>{summary.segments_unchanged}</td>
                <td>-</td>
            </tr>""")
            if inv_rows:
                # Insert inventory rows before the closing </table> tag
                html_parts[-1] = html_parts[-1].replace("</table>", "".join(inv_rows) + "\n        </table>")

        if not summary.has_changes:
            html_parts.append('<p class="no-changes">No differences found.</p>')
        else:
            html_parts.append(f'<p class="total-changes">Total changes: {summary.total_changes}</p>')

        # Helper function to generate diff table
        def generate_diff_table(diffs: list[ComponentDiff], title: str):
            changes = [d for d in diffs if d.change_type != ChangeType.UNCHANGED]
            if not changes and changes_only:
                return ""

            html_out = f"<h2>{title}</h2>\n"
            if not changes:
                html_out += "<p><em>No changes</em></p>\n"
                return html_out

            html_out += """<table class="diff-table">
                <tr>
                    <th>Status</th>
                    <th>ID</th>
                    <th>Name</th>
                    <th>Details</th>
                </tr>"""

            for diff in changes:
                row_class = f"row-{diff.change_type.value}"
                badge_class = f"badge-{diff.change_type.value}"
                badge_text = diff.change_type.value.upper()
                detail = _get_change_detail(diff)
                detail_escaped = _html_escape(detail)

                html_out += f"""
                <tr class="{row_class}">
                    <td><span class="badge {badge_class}">{badge_text}</span></td>
                    <td><code>{_html_escape(str(diff.id))}</code></td>
                    <td>{_html_escape(str(diff.name))}</td>
                    <td>{detail_escaped}</td>
                </tr>"""

            html_out += "</table>\n"
            return html_out

        html_parts.append(generate_diff_table(diff_result.metric_diffs, "Metrics Changes"))
        html_parts.append(generate_diff_table(diff_result.dimension_diffs, "Dimensions Changes"))

        # Inventory diff sections (if present)
        if diff_result.has_inventory_diffs:

            def generate_inventory_diff_table(diffs: list[InventoryItemDiff] | None, title: str):
                if diffs is None:
                    return ""
                changes = [d for d in diffs if d.change_type != ChangeType.UNCHANGED]
                if not changes and changes_only:
                    return ""

                html_out = f"<h2>{title}</h2>\n"
                if not changes:
                    html_out += "<p><em>No changes</em></p>\n"
                    return html_out

                html_out += """<table class="diff-table">
                    <tr>
                        <th>Status</th>
                        <th>ID</th>
                        <th>Name</th>
                        <th>Details</th>
                    </tr>"""

                for diff in changes:
                    row_class = f"row-{diff.change_type.value}"
                    badge_class = f"badge-{diff.change_type.value}"
                    badge_text = diff.change_type.value.upper()
                    detail = _get_inventory_change_detail(diff)
                    detail_escaped = _html_escape(detail)

                    html_out += f"""
                    <tr class="{row_class}">
                        <td><span class="badge {badge_class}">{badge_text}</span></td>
                        <td><code>{_html_escape(str(diff.id))}</code></td>
                        <td>{_html_escape(str(diff.name))}</td>
                        <td>{detail_escaped}</td>
                    </tr>"""

                html_out += "</table>\n"
                return html_out

            html_parts.append(
                "<h2 style='border-top: 2px solid #3498db; padding-top: 20px; margin-top: 30px;'>Inventory Changes</h2>",
            )
            html_parts.append(
                generate_inventory_diff_table(diff_result.calc_metrics_diffs, "Calculated Metrics Changes"),
            )
            html_parts.append(generate_inventory_diff_table(diff_result.segments_diffs, "Segments Changes"))

        # Footer
        html_parts.append(f"""
        <div class="footer">
            <p>Generated by CJA SDR Generator v{diff_result.tool_version}</p>
        </div>
    </div>
</body>
</html>
""")

        html_file = os.path.join(output_dir, f"{base_filename}.html")
        with open(html_file, "w", encoding="utf-8") as f:
            f.write("\n".join(html_parts))

        logger.info(f"Diff HTML file created: {html_file}")
        return html_file

    except (OSError, KeyError, TypeError, ValueError) as e:
        logger.error(_format_error_msg("creating diff HTML file", error=e))
        raise
