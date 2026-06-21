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
from cja_auto_sdr.org.writers.compat import (
    CONSOLE_STATS_ONLY_OVERRIDE_MAPPING as _CONSOLE_STATS_ONLY_OVERRIDE_MAPPING,
)
from cja_auto_sdr.org.writers.compat import CONSOLE_WRITER_OVERRIDE_MAPPING as _CONSOLE_WRITER_OVERRIDE_MAPPING
from cja_auto_sdr.org.writers.compat import CSV_WRITER_OVERRIDE_MAPPING as _CSV_WRITER_OVERRIDE_MAPPING
from cja_auto_sdr.org.writers.compat import EMPTY_OVERRIDE_MAPPING as _EMPTY_OVERRIDE_MAPPING
from cja_auto_sdr.org.writers.compat import EXCEL_WRITER_OVERRIDE_MAPPING as _EXCEL_WRITER_OVERRIDE_MAPPING
from cja_auto_sdr.org.writers.compat import HTML_WRITER_OVERRIDE_MAPPING as _HTML_WRITER_OVERRIDE_MAPPING
from cja_auto_sdr.org.writers.compat import JSON_BUILDER_OVERRIDE_MAPPING as _JSON_BUILDER_OVERRIDE_MAPPING
from cja_auto_sdr.org.writers.compat import JSON_WRITER_OVERRIDE_MAPPING as _JSON_WRITER_OVERRIDE_MAPPING
from cja_auto_sdr.org.writers.compat import (
    MARKDOWN_WRITER_OVERRIDE_MAPPING as _MARKDOWN_WRITER_OVERRIDE_MAPPING,
)
from cja_auto_sdr.org.writers.compat import NOTION_WRITER_OVERRIDE_MAPPING as _NOTION_WRITER_OVERRIDE_MAPPING
from cja_auto_sdr.org.writers.compat import make_compat_wrapper as _make_compat_wrapper
from cja_auto_sdr.org.writers.console import (
    write_org_report_comparison_console as _write_org_report_comparison_console_impl,
)
from cja_auto_sdr.org.writers.console import write_org_report_console as _write_org_report_console_impl
from cja_auto_sdr.org.writers.console import write_org_report_stats_only as _write_org_report_stats_only_impl

# ---------------------------------------------------------------------------
# Re-exports from csv.py
# ---------------------------------------------------------------------------
from cja_auto_sdr.org.writers.csv import write_org_report_csv as _write_org_report_csv_impl

# ---------------------------------------------------------------------------
# Re-exports from excel.py
# ---------------------------------------------------------------------------
from cja_auto_sdr.org.writers.excel import write_org_report_excel as _write_org_report_excel_impl

# ---------------------------------------------------------------------------
# Re-exports from html.py
# ---------------------------------------------------------------------------
from cja_auto_sdr.org.writers.html import write_org_report_html as _write_org_report_html_impl

# ---------------------------------------------------------------------------
# Re-exports from json.py
# ---------------------------------------------------------------------------
from cja_auto_sdr.org.writers.json import (
    build_org_report_json_data as _build_org_report_json_data_impl,
)
from cja_auto_sdr.org.writers.json import (
    write_org_report_json as _write_org_report_json_impl,
)

# ---------------------------------------------------------------------------
# Re-exports from markdown.py
# ---------------------------------------------------------------------------
from cja_auto_sdr.org.writers.markdown import write_org_report_markdown as _write_org_report_markdown_impl
from cja_auto_sdr.org.writers.notion import write_org_report_notion as _write_org_report_notion_impl

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

_CONSOLE_MODULE = "cja_auto_sdr.org.writers.console"
_CSV_MODULE = "cja_auto_sdr.org.writers.csv"
_EXCEL_MODULE = "cja_auto_sdr.org.writers.excel"
_HTML_MODULE = "cja_auto_sdr.org.writers.html"
_JSON_MODULE = "cja_auto_sdr.org.writers.json"
_MARKDOWN_MODULE = "cja_auto_sdr.org.writers.markdown"
_NOTION_MODULE = "cja_auto_sdr.org.writers.notion"

write_org_report_console = _make_compat_wrapper(
    __name__,
    _write_org_report_console_impl,
    target_module_name=_CONSOLE_MODULE,
    override_mapping=_CONSOLE_WRITER_OVERRIDE_MAPPING,
)
write_org_report_stats_only = _make_compat_wrapper(
    __name__,
    _write_org_report_stats_only_impl,
    target_module_name=_CONSOLE_MODULE,
    override_mapping=_CONSOLE_STATS_ONLY_OVERRIDE_MAPPING,
)
write_org_report_comparison_console = _make_compat_wrapper(
    __name__,
    _write_org_report_comparison_console_impl,
    target_module_name=_CONSOLE_MODULE,
    override_mapping=_EMPTY_OVERRIDE_MAPPING,
)
build_org_report_json_data = _make_compat_wrapper(
    __name__,
    _build_org_report_json_data_impl,
    target_module_name=_JSON_MODULE,
    override_mapping=_JSON_BUILDER_OVERRIDE_MAPPING,
)
write_org_report_json = _make_compat_wrapper(
    __name__,
    _write_org_report_json_impl,
    target_module_name=_JSON_MODULE,
    override_mapping=_JSON_WRITER_OVERRIDE_MAPPING,
)
write_org_report_excel = _make_compat_wrapper(
    __name__,
    _write_org_report_excel_impl,
    target_module_name=_EXCEL_MODULE,
    override_mapping=_EXCEL_WRITER_OVERRIDE_MAPPING,
)
write_org_report_markdown = _make_compat_wrapper(
    __name__,
    _write_org_report_markdown_impl,
    target_module_name=_MARKDOWN_MODULE,
    override_mapping=_MARKDOWN_WRITER_OVERRIDE_MAPPING,
)
write_org_report_html = _make_compat_wrapper(
    __name__,
    _write_org_report_html_impl,
    target_module_name=_HTML_MODULE,
    override_mapping=_HTML_WRITER_OVERRIDE_MAPPING,
)
write_org_report_csv = _make_compat_wrapper(
    __name__,
    _write_org_report_csv_impl,
    target_module_name=_CSV_MODULE,
    override_mapping=_CSV_WRITER_OVERRIDE_MAPPING,
)
write_org_report_notion = _make_compat_wrapper(
    __name__,
    _write_org_report_notion_impl,
    target_module_name=_NOTION_MODULE,
    override_mapping=_NOTION_WRITER_OVERRIDE_MAPPING,
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
    "write_org_report_notion",
    "write_org_report_stats_only",
]
