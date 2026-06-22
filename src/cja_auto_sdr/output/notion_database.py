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
import os
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from cja_auto_sdr.output.writers.notion import _call_with_rate_limit_retry

if TYPE_CHECKING:
    import pandas as pd

__all__ = [
    "DATABASE_DEFAULT_TITLE",
    "DATABASE_SCHEMA",
    "DATA_QUALITY_OPTIONS",
    "SchemaRepairResult",
    "build_catalog_row_properties",
    "build_row_properties",
    "derive_data_quality_status",
    "describe_database_schema",
    "ensure_database",
    "find_existing_row_id",
    "repair_database_schema",
    "upsert_database_row",
]

DATA_QUALITY_OPTIONS = ["healthy", "degraded", "partial", "unknown"]
_DATA_QUALITY_OPTION_COLORS = {"healthy": "green", "degraded": "red", "partial": "yellow", "unknown": "default"}

# Default title for a freshly-created registry database. Overridable via the
# --notion-database-title flag or the NOTION_DATABASE_TITLE env var.
DATABASE_DEFAULT_TITLE = "CJA SDR Registry"

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
            "options": [{"name": name, "color": _DATA_QUALITY_OPTION_COLORS[name]} for name in DATA_QUALITY_OPTIONS],
        },
    },
}


def _schema_property_type(entry: dict) -> str:
    """Return the Notion property type for a DATABASE_SCHEMA entry (its single key)."""
    return next(iter(entry))


def describe_database_schema() -> str:
    """Render the canonical registry schema as a human-readable block for stdout."""
    lines = [f"CJA SDR Registry — database schema ({len(DATABASE_SCHEMA)} properties)", ""]
    for name, entry in DATABASE_SCHEMA.items():
        ptype = _schema_property_type(entry)
        if ptype == "select":
            options = ", ".join(o["name"] for o in entry["select"].get("options", []))
            lines.append(f"  {name:<26} {ptype} ({options})")
        else:
            lines.append(f"  {name:<26} {ptype}")
    return "\n".join(lines) + "\n"


@dataclass(frozen=True)
class SchemaRepairResult:
    to_add: list[str]
    conflicts: list[tuple[str, str, str]]  # (name, expected_type, actual_type)
    applied: bool


def repair_database_schema(client: Any, *, database_id: str, dry_run: bool = False) -> SchemaRepairResult:
    """Add canonical properties missing from an existing registry database.

    Add-only: never changes a property's type, never removes one, never adds a
    second title. Type mismatches are recorded as conflicts and left untouched.
    Raises ValueError if the database has no data source.
    """
    db = _call_with_rate_limit_retry(client.databases.retrieve, database_id=database_id)
    data_sources = db.get("data_sources") or []
    if not data_sources:
        raise ValueError(f"Database {database_id} has no data source")
    ds_id = str(data_sources[0]["id"])
    ds = _call_with_rate_limit_retry(client.data_sources.retrieve, data_source_id=ds_id)
    live = ds.get("properties") or {}

    to_add: list[str] = []
    conflicts: list[tuple[str, str, str]] = []
    payload: dict[str, Any] = {}
    for name, entry in DATABASE_SCHEMA.items():
        expected = _schema_property_type(entry)
        if expected == "title":
            # A database always has exactly one title, so repair never adds the
            # canonical title. Surface an absent/renamed title (or a wrong-typed
            # "Name") as a conflict for manual resolution — otherwise ensure_database
            # would later reject the database with no hint from repair.
            if name not in live:
                conflicts.append((name, expected, "missing"))
            elif live[name].get("type") != "title":
                conflicts.append((name, expected, str(live[name].get("type"))))
            continue
        if name not in live:
            to_add.append(name)
            payload[name] = entry
        elif live[name].get("type") != expected:
            conflicts.append((name, expected, str(live[name].get("type"))))

    applied = False
    if to_add and not dry_run:
        _call_with_rate_limit_retry(client.data_sources.update, data_source_id=ds_id, properties=payload)
        applied = True
    return SchemaRepairResult(to_add=to_add, conflicts=conflicts, applied=applied)


def _rt(content: str) -> list[dict]:
    return [{"type": "text", "text": {"content": str(content)[:2000]}}]


def _title(content: str) -> list[dict]:
    # Notion title property values use the same rich-text array shape as rich_text.
    return _rt(content)


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
        db = _call_with_rate_limit_retry(client.databases.retrieve, database_id=database_id)
        data_sources = db.get("data_sources") or []
        if not data_sources:
            raise ValueError(f"Database {database_id} has no data source")
        ds_id = str(data_sources[0]["id"])
        ds = _call_with_rate_limit_retry(client.data_sources.retrieve, data_source_id=ds_id)
        existing_props = set((ds.get("properties") or {}).keys())
        missing = set(DATABASE_SCHEMA) - existing_props
        if missing:
            raise ValueError(
                f"Database {database_id} is missing required properties: {sorted(missing)}. "
                "Run cja_auto_sdr --notion-repair-database to add them.",
            )
        return str(db["id"]), ds_id

    if not create_if_missing:
        raise ValueError(
            "NOTION_DATABASE_ID is not set and --notion-create-database was not "
            "passed. Re-run with --notion-create-database to bootstrap a new "
            "SDR Registry database under NOTION_PARENT_PAGE_ID.",
        )

    # Title resolves from NOTION_DATABASE_TITLE (which the --notion-database-title
    # flag populates) and falls back to the default. This runs after .env is
    # loaded by the calling writer, so a .env-configured title is honored too.
    title_text = os.environ.get("NOTION_DATABASE_TITLE") or DATABASE_DEFAULT_TITLE
    created = _call_with_rate_limit_retry(
        client.databases.create,
        parent={"type": "page_id", "page_id": parent_page_id},
        title=[{"type": "text", "text": {"content": title_text}}],
        initial_data_source={"properties": DATABASE_SCHEMA},
    )
    data_sources = created.get("data_sources") or []
    if not data_sources:
        raise ValueError("Notion did not return a data source for the created database")
    return str(created["id"]), str(data_sources[0]["id"])


def find_existing_row_id(
    client: Any,
    *,
    data_source_id: str,
    data_view_id: str,
) -> str | None:
    """Return the existing row (page) ID for ``data_view_id`` in the data source.

    Queries the data source by the ``Data View ID`` property so an upsert is keyed
    by data view ID even when the local registry has no record (fresh checkout,
    different ``--output-dir``, or a stale/missing ``.notion_pages.json``). Returns
    ``None`` when no matching row exists. Notion API errors propagate to the caller,
    which maps them to a friendly message.
    """
    response = _call_with_rate_limit_retry(
        client.data_sources.query,
        data_source_id=data_source_id,
        filter={"property": "Data View ID", "rich_text": {"equals": data_view_id}},
        page_size=1,
    )
    results = response.get("results") or []
    return str(results[0]["id"]) if results else None


def upsert_database_row(
    client: Any,
    *,
    data_source_id: str,
    existing_row_id: str | None,
    properties: dict[str, dict],
) -> str:
    """Create or update a database row; return its page ID."""
    if existing_row_id:
        updated = _call_with_rate_limit_retry(
            client.pages.update,
            page_id=existing_row_id,
            properties=properties,
        )
        return str(updated["id"])
    created = _call_with_rate_limit_retry(
        client.pages.create,
        parent={"type": "data_source_id", "data_source_id": data_source_id},
        properties=properties,
    )
    return str(created["id"])
