"""SDR Registry database — schema + ensure/upsert helpers.

A Notion database that catalogs every SDR page published by cja_auto_sdr.
One row per data view, keyed by Data View ID. Re-runs upsert the row
in place; the registry file (.notion_pages.json) tracks the row ID alongside
the page ID so reruns avoid duplicating rows.

The schema is fixed in code (see DATABASE_SCHEMA). ensure_database can either:
  * Create a brand-new database under a parent page (when create_if_missing=True)
  * Validate that an existing database has all required properties

User-added extra properties in an existing DB are tolerated; missing required
properties cause a ValueError so we fail loudly rather than silently dropping
metadata.
"""

from __future__ import annotations

import datetime as _dt
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pandas as pd

__all__ = [
    "DATABASE_SCHEMA",
    "DATA_QUALITY_OPTIONS",
    "build_catalog_row_properties",
    "build_row_properties",
    "derive_data_quality_status",
    "ensure_database",
    "upsert_database_row",
]

DATA_QUALITY_OPTIONS = ["healthy", "degraded", "partial", "unknown"]

# Notion database property definitions (used at create time).
DATABASE_SCHEMA: dict[str, dict[str, Any]] = {
    "Name": {"title": {}},
    "Data View ID": {"rich_text": {}},
    "SDR Page": {"rich_text": {}},
    "Last Updated": {"date": {}},
    "Tool Version": {"rich_text": {}},
    "Captured At": {"date": {}},
    "Currency": {"rich_text": {}},
    "Timezone": {"rich_text": {}},
    "Metrics Count": {"number": {"format": "number"}},
    "Dimensions Count": {"number": {"format": "number"}},
    "Segments Count": {"number": {"format": "number"}},
    "Calculated Metrics Count": {"number": {"format": "number"}},
    "Derived Fields Count": {"number": {"format": "number"}},
    "Data Quality": {
        "select": {
            "options": [
                {"name": "healthy", "color": "green"},
                {"name": "degraded", "color": "red"},
                {"name": "partial", "color": "yellow"},
                {"name": "unknown", "color": "default"},
            ],
        },
    },
}


def _rt(content: str) -> list[dict]:
    return [{"type": "text", "text": {"content": str(content)[:2000]}}]


def _title(content: str) -> list[dict]:
    return [{"type": "text", "text": {"content": str(content)[:2000]}}]


def derive_data_quality_status(dq_df: pd.DataFrame | None) -> str:
    """Map the DQ DataFrame's worst severity to a Notion select option.

    Severity vocabulary (from core.constants.QUALITY_SEVERITY_ORDER):
      CRITICAL / HIGH / ERROR  → "degraded"
      MEDIUM / WARN / WARNING  → "partial"
      LOW / INFO / anything else → "healthy"

    An empty or None DataFrame returns "healthy". A DataFrame without a
    "Severity" column returns "unknown".
    """
    if dq_df is None or len(dq_df) == 0:
        return "healthy"
    if "Severity" not in dq_df.columns:
        return "unknown"
    severities = {str(s).upper() for s in dq_df["Severity"].tolist()}
    if severities & {"CRITICAL", "HIGH", "ERROR"}:
        return "degraded"
    if severities & {"MEDIUM", "WARN", "WARNING"}:
        return "partial"
    return "healthy"


def _count(df: pd.DataFrame | None) -> int:
    return 0 if df is None or len(df) == 0 else len(df)


def _iso_date_value(raw: str | None) -> dict | None:
    """Format a date string as Notion's ``{"start": iso}`` shape, or None.

    Handles ISO-8601 strings directly and also the ``"YYYY-MM-DD HH:MM:SS TZ"``
    shape produced by CJA metadata (e.g. ``"2026-06-19 14:20:00 PDT"``).
    Returns ``None`` for unparseable input so callers emit ``{"date": None}``.
    """
    if not raw:
        return None
    s = str(raw).strip()
    try:
        return {"start": _dt.datetime.fromisoformat(s).isoformat()}
    except ValueError:
        pass
    import re

    m = re.match(r"(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}:\d{2})", s)
    if m:
        return {"start": f"{m.group(1)}T{m.group(2)}"}
    m = re.match(r"(\d{4}-\d{2}-\d{2})", s)
    if m:
        return {"start": m.group(1)}
    return None


def build_row_properties(
    data_dict: dict[str, pd.DataFrame],
    metadata_dict: dict[str, Any],
    page_id: str,
    *,
    tool_version: str,
    now: _dt.datetime | None = None,
) -> dict[str, dict]:
    """Build the Notion ``properties`` payload for one database row."""
    now = now or _dt.datetime.now(_dt.UTC)
    dv_name = str(metadata_dict.get("Data View Name", ""))
    dv_id = str(metadata_dict.get("Data View ID", ""))
    captured_at = metadata_dict.get("Generated Date & timestamp and timezone")

    return {
        "Name": {"title": _title(dv_name)},
        "Data View ID": {"rich_text": _rt(dv_id)},
        "SDR Page": {"rich_text": _rt(f"notion://pages/{page_id}")},
        "Last Updated": {"date": {"start": now.isoformat()}},
        "Tool Version": {"rich_text": _rt(tool_version)},
        "Captured At": {"date": _iso_date_value(captured_at)},
        "Currency": {"rich_text": _rt(metadata_dict.get("Currency", ""))},
        "Timezone": {"rich_text": _rt(metadata_dict.get("Timezone", ""))},
        "Metrics Count": {"number": _count(data_dict.get("Metrics"))},
        "Dimensions Count": {"number": _count(data_dict.get("Dimensions"))},
        "Segments Count": {"number": _count(data_dict.get("Segments"))},
        "Calculated Metrics Count": {"number": _count(data_dict.get("Calculated Metrics"))},
        "Derived Fields Count": {"number": _count(data_dict.get("Derived Fields"))},
        "Data Quality": {
            "select": {"name": derive_data_quality_status(data_dict.get("Data Quality"))},
        },
    }


def build_catalog_row_properties(
    *,
    data_view_name: str,
    data_view_id: str,
    metrics_count: int,
    dimensions_count: int,
    page_id: str | None = None,
    tool_version: str,
    captured_at: str | None = None,
    now: _dt.datetime | None = None,
) -> dict[str, dict]:
    """Build the Notion ``properties`` payload for an org-report catalog row.

    Unlike ``build_row_properties``, this version accepts pre-counted metric and
    dimension counts directly (from the org-report summary), leaving unmeasured
    columns (Segments, Calculated Metrics, Derived Fields) as ``None`` and
    Data Quality as "unknown".
    """
    now = now or _dt.datetime.now(_dt.UTC)
    sdr_page_url = f"notion://pages/{page_id}" if page_id else ""
    return {
        "Name": {"title": _title(data_view_name)},
        "Data View ID": {"rich_text": _rt(data_view_id)},
        "SDR Page": {"rich_text": _rt(sdr_page_url)},
        "Last Updated": {"date": {"start": now.isoformat()}},
        "Tool Version": {"rich_text": _rt(tool_version)},
        "Captured At": {"date": _iso_date_value(captured_at)},
        "Currency": {"rich_text": _rt("")},
        "Timezone": {"rich_text": _rt("")},
        "Metrics Count": {"number": metrics_count},
        "Dimensions Count": {"number": dimensions_count},
        "Segments Count": {"number": None},
        "Calculated Metrics Count": {"number": None},
        "Derived Fields Count": {"number": None},
        "Data Quality": {"select": {"name": "unknown"}},
    }


def ensure_database(
    client: Any,
    *,
    parent_page_id: str,
    database_id: str | None,
    create_if_missing: bool,
) -> tuple[str, str]:
    """Return ``(database_id, data_source_id)`` for the SDR Registry database.

    * If ``database_id`` is given, retrieve it and verify the data source has
      all required properties; raise ``ValueError`` listing the missing ones if not.
    * If ``database_id`` is ``None`` and ``create_if_missing`` is True,
      create a fresh database under ``parent_page_id`` and return both IDs.
    * Otherwise raise ``ValueError`` instructing the user to pass
      ``--notion-create-database`` or ``NOTION_DATABASE_ID``.
    """
    if database_id is not None:
        db = client.databases.retrieve(database_id=database_id)
        data_sources = db.get("data_sources") or []
        if not data_sources:
            raise ValueError(f"Database {database_id} has no data sources")
        ds_id = str(data_sources[0]["id"])
        ds = client.data_sources.retrieve(data_source_id=ds_id)
        existing_props = set((ds.get("properties") or {}).keys())
        missing = set(DATABASE_SCHEMA) - existing_props
        if missing:
            raise ValueError(
                f"Database {database_id} is missing required properties: {sorted(missing)}",
            )
        return str(db["id"]), ds_id

    if not create_if_missing:
        raise ValueError(
            "NOTION_DATABASE_ID is not set and --notion-create-database was not "
            "passed. Re-run with --notion-create-database to bootstrap a new "
            "SDR Registry database under NOTION_PARENT_PAGE_ID.",
        )

    created = client.databases.create(
        parent={"type": "page_id", "page_id": parent_page_id},
        title=[{"type": "text", "text": {"content": "CJA SDR Registry"}}],
        initial_data_source={"properties": DATABASE_SCHEMA},
    )
    data_sources = created.get("data_sources") or []
    if not data_sources:
        raise ValueError("Notion did not return a data source for the created database")
    return str(created["id"]), str(data_sources[0]["id"])


def upsert_database_row(
    client: Any,
    *,
    data_source_id: str,
    existing_row_id: str | None,
    properties: dict[str, dict],
) -> str:
    """Create or update a database row; return its page ID."""
    if existing_row_id:
        return str(client.pages.update(page_id=existing_row_id, properties=properties)["id"])
    created = client.pages.create(
        parent={"type": "data_source_id", "data_source_id": data_source_id},
        properties=properties,
    )
    return str(created["id"])
