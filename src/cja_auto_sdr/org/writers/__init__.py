"""
Org report writer functions.

Renders OrgReportResult into various output formats (console, JSON,
Excel, Markdown, HTML, CSV).  Shared helpers (common.py), trending
renderers (trending.py), and per-format writers are split across
submodules; this package root re-exports everything for compatibility.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Re-exports from common.py
# ---------------------------------------------------------------------------
from cja_auto_sdr.org.writers.common import (
    _flatten_recommendation_for_tabular,
    _format_recommendation_context_entries,
    _normalize_org_report_output_format,
    _normalize_recommendation_for_json,
    _normalize_recommendation_severity,
    _render_distribution_bar,
    _validate_org_report_output_request,
)

# ---------------------------------------------------------------------------
# Re-exports from console.py
# ---------------------------------------------------------------------------
from cja_auto_sdr.org.writers.console import (
    write_org_report_comparison_console,
    write_org_report_console,
    write_org_report_stats_only,
)

# ---------------------------------------------------------------------------
# Re-exports from csv.py
# ---------------------------------------------------------------------------
from cja_auto_sdr.org.writers.csv import write_org_report_csv

# ---------------------------------------------------------------------------
# Re-exports from excel.py
# ---------------------------------------------------------------------------
from cja_auto_sdr.org.writers.excel import write_org_report_excel

# ---------------------------------------------------------------------------
# Re-exports from html.py
# ---------------------------------------------------------------------------
from cja_auto_sdr.org.writers.html import write_org_report_html

# ---------------------------------------------------------------------------
# Re-exports from json.py
# ---------------------------------------------------------------------------
from cja_auto_sdr.org.writers.json import (
    build_org_report_json_data,
    write_org_report_json,
)

# ---------------------------------------------------------------------------
# Re-exports from markdown.py
# ---------------------------------------------------------------------------
from cja_auto_sdr.org.writers.markdown import write_org_report_markdown

# ---------------------------------------------------------------------------
# Re-exports from trending.py  (private helpers that tests import directly)
# ---------------------------------------------------------------------------
from cja_auto_sdr.org.writers.trending import (
    _TRENDING_METRIC_SPECS,
    _build_trending_metric_rows,
    _escape_markdown_table_cell,
    _format_signed_trending_value,
    _format_trending_dv_label,
    _format_trending_period_label,
    _format_trending_timestamp_short,
    _print_trending_console_section,
    _ranked_drift_entries,
    _render_console_trending_table,
    _render_html_trending_table,
    _render_markdown_trending_table,
    _render_trending_console,
    _render_trending_html,
    _render_trending_markdown,
    _resolve_trending_dv_name,
    _sorted_drift_score_items,
    _stringify_trending_value,
    _top_drift_scores,
    _trending_date_range,
    _trending_delta_column_specs,
    _trending_delta_csv_rows,
    _trending_delta_metric_rows,
    _trending_matrix_rows,
    _trending_snapshot_column_specs,
    _trending_snapshot_csv_rows,
    _trending_snapshot_metric_rows,
    _trending_snapshots_to_dicts,
)

__all__ = [
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
]
