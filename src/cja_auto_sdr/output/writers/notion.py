"""Notion output writer: block builder + Notion API layer.

Credentials (env vars required, not stored in config.json):
  NOTION_TOKEN            — Notion internal integration token
  NOTION_PARENT_PAGE_ID   — Parent page under which SDR child pages are created

Install the optional dep: uv pip install 'cja-auto-sdr[notion]'

The pages this writer publishes are auto-regenerated on every run. Manual edits
made inside Notion will be overwritten on the next sync — the page is cleared
and rewritten in place. Use --notion-force-new to break that link and produce
a fresh page (the old one is left untouched, becoming an orphan).
"""

from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import pandas as pd

from cja_auto_sdr.core.version import __version__
from cja_auto_sdr.output.notion_registry import (
    get_registry_path,
    lookup_page_id,
    store_page_id,
)

__all__ = [
    "NotionAPIError",
    "NotionConfigurationError",
    "NotionDependencyError",
    "write_notion_output",
]

_SECTION_ORDER = [
    "Data Quality",
    "Metrics",
    "Dimensions",
    "Segments",
    "Calculated Metrics",
    "Derived Fields",
]
_SECTION_ICONS = {
    "Metrics": "📐",
    "Dimensions": "📏",
    "Segments": "🔖",
    "Calculated Metrics": "🧮",
    "Derived Fields": "🔬",
}
_DQ_HEADING_ICON = "🛡️"
# Keys cover the CJA quality engine vocabulary (core.constants.QUALITY_SEVERITY_ORDER:
# CRITICAL/HIGH/MEDIUM/LOW/INFO) plus the generic ERROR/WARN logging vocabulary for
# safety. Unmapped severities fall back to the info icon in _dq_callout_blocks.
_DQ_SEVERITY_ICONS = {
    "CRITICAL": "🔴",
    "HIGH": "🔴",
    "ERROR": "🔴",
    "MEDIUM": "⚠️",
    "WARN": "⚠️",
    "WARNING": "⚠️",
    "LOW": "ℹ️",
    "INFO": "ℹ️",
}

# Notion's API caps the ``children`` array of a single block (including a
# ``table`` block's row children) at 100 entries per request. Reserve one slot
# for the header row and cap data rows at 99 so each emitted table fits in a
# single append call. Sections larger than this are split into multiple
# sibling tables under the same heading.
_MAX_TABLE_DATA_ROWS = 99

# Concurrent block-deletes on update. Notion's API does not support bulk
# delete, so an N-block page costs N round-trips. Keep the pool small to stay
# well clear of Notion's per-integration rate limit (~3 rps default).
_DELETE_WORKER_COUNT = 4

# 429 retry budget. Notion returns 429 with a ``Retry-After`` header in
# seconds; we honour it when present, otherwise fall back to exponential
# backoff. Total wall time worst-case: ~1+2+4 = 7s on top of any Retry-After.
_RATE_LIMIT_MAX_ATTEMPTS = 3
_RATE_LIMIT_BASE_DELAY_SECONDS = 1.0


# ---------------------------------------------------------------------------
# Exceptions (raised from this module; CLI dispatch converts to exit codes)
# ---------------------------------------------------------------------------


class NotionConfigurationError(Exception):
    """Required Notion configuration (env vars) is missing or invalid."""


class NotionDependencyError(Exception):
    """The ``notion-client`` optional extra is not installed."""


class NotionAPIError(Exception):
    """A Notion API call failed in a way the user can act on (auth, perms, rate-limit)."""


# ---------------------------------------------------------------------------
# Block builder helpers (pure functions, no API calls)
# ---------------------------------------------------------------------------


def _rich_text(content: str) -> list[dict]:
    return [{"type": "text", "text": {"content": str(content)[:2000]}}]


def _heading2_block(content: str) -> dict:
    return {
        "object": "block",
        "type": "heading_2",
        "heading_2": {"rich_text": _rich_text(content)},
    }


def _divider_block() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def _paragraph_block(content: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": _rich_text(content)},
    }


def _callout_block(content: str, emoji: str = "📋", color: str = "default") -> dict:
    return {
        "object": "block",
        "type": "callout",
        "callout": {
            "rich_text": _rich_text(content),
            "icon": {"type": "emoji", "emoji": emoji},
            "color": color,
        },
    }


def _table_row_block(cells: list[str]) -> dict:
    return {
        "object": "block",
        "type": "table_row",
        "table_row": {
            "cells": [[{"type": "text", "text": {"content": str(c)[:2000]}}] for c in cells],
        },
    }


def _table_block(df: pd.DataFrame) -> dict | None:
    cols = list(df.columns)
    # Notion rejects table blocks with table_width == 0. A DataFrame with no
    # columns has nothing to render — return None and let the caller skip it.
    if not cols:
        return None
    rows = [_table_row_block(cols)]
    for _, row in df.iterrows():
        rows.append(
            _table_row_block(
                [str(row[c]) if not pd.isna(row[c]) else "" for c in cols],
            ),
        )
    return {
        "object": "block",
        "type": "table",
        "table": {
            "table_width": len(cols),
            "has_column_header": True,
            "has_row_header": False,
            "children": rows,
        },
    }


def _section_blocks(section_name: str, df: pd.DataFrame) -> list[dict]:
    if df is None or df.empty or not list(df.columns):
        return []
    icon = _SECTION_ICONS.get(section_name, "📄")
    blocks: list[dict] = [_heading2_block(f"{icon} {section_name}")]
    # Split sections larger than the per-table cap into sibling tables under
    # the same heading so each table stays within Notion's 100-children limit.
    for start in range(0, len(df), _MAX_TABLE_DATA_ROWS):
        chunk = df.iloc[start : start + _MAX_TABLE_DATA_ROWS]
        table = _table_block(chunk)
        if table is not None:
            blocks.append(table)
    # If every chunk degenerated (shouldn't happen given the column guard
    # above), drop the orphan heading so we don't render a bare section title.
    if len(blocks) == 1:
        return []
    return blocks


def _dq_callout_blocks(dq_df: pd.DataFrame) -> list[dict]:
    if dq_df is None or dq_df.empty:
        return []
    blocks = []
    for _, row in dq_df.iterrows():
        severity = str(row.get("Severity", "INFO")).upper()
        emoji = _DQ_SEVERITY_ICONS.get(severity, "ℹ️")
        parts = [f"[{severity}]"]
        for col in dq_df.columns:
            if col != "Severity":
                val = row.get(col, "")
                if val and not pd.isna(val):
                    parts.append(f"{col}: {val}")
        blocks.append(_callout_block(" | ".join(parts), emoji=emoji))
    return blocks


def _metadata_callout_block(metadata_dict: dict) -> dict:
    priority_keys = [
        "Data View Name",
        "Data View ID",
        "Generated Date & timestamp and timezone",
    ]
    priority_set = set(priority_keys)
    lines = [f"{key}: {metadata_dict[key]}" for key in priority_keys if key in metadata_dict]
    lines.extend(f"{key}: {val}" for key, val in metadata_dict.items() if key not in priority_set)
    return _callout_block("\n".join(lines), emoji="📋")


def build_sdr_blocks(
    data_dict: dict[str, pd.DataFrame],
    metadata_dict: dict,
) -> list[dict]:
    blocks: list[dict] = [_metadata_callout_block(metadata_dict), _divider_block()]

    dq_df = data_dict.get("Data Quality")
    if dq_df is not None and not dq_df.empty:
        blocks.append(_heading2_block(f"{_DQ_HEADING_ICON} Data Quality"))
        blocks.extend(_dq_callout_blocks(dq_df))

    for section_name in _SECTION_ORDER:
        if section_name == "Data Quality":
            continue
        df = data_dict.get(section_name)
        blocks.extend(_section_blocks(section_name, df))

    blocks.extend(
        [
            _divider_block(),
            _paragraph_block(f"Generated by cja_auto_sdr v{__version__}"),
        ],
    )
    return blocks


# ---------------------------------------------------------------------------
# Credential resolution + optional-dep loader
# ---------------------------------------------------------------------------


def resolve_notion_credentials() -> tuple[str, str]:
    """Return (NOTION_TOKEN, NOTION_PARENT_PAGE_ID) from env / .env file.

    Raises NotionConfigurationError if either env var is missing.
    """
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except ImportError:
        pass

    token = os.environ.get("NOTION_TOKEN")
    parent_page_id = os.environ.get("NOTION_PARENT_PAGE_ID")

    if not token:
        raise NotionConfigurationError(
            "NOTION_TOKEN is not set. Set it as an environment variable or add it to a .env file.",
        )

    if not parent_page_id:
        raise NotionConfigurationError(
            "NOTION_PARENT_PAGE_ID is not set. Set it as an environment variable or add it to a .env file.",
        )

    return token, parent_page_id


def _require_notion_client():
    """Return notion_client.Client class.

    Raises NotionDependencyError if the optional extra is not installed.
    """
    try:
        from notion_client import Client

        return Client
    except ImportError as exc:
        raise NotionDependencyError(
            "Notion output requires the notion extra.\nInstall it with: uv pip install 'cja-auto-sdr[notion]'",
        ) from exc


# ---------------------------------------------------------------------------
# Notion API operations
# ---------------------------------------------------------------------------


def _extract_api_error_code(err: Exception) -> str | None:
    """Return the Notion API error ``code`` attribute when present."""
    code = getattr(err, "code", None)
    if isinstance(code, str):
        return code
    # APIResponseError stringifies its code via str(.code) in some SDK versions.
    if code is not None:
        return str(code)
    return None


def _extract_retry_after_seconds(err: Exception) -> float | None:
    """Return the Retry-After value (in seconds) for a 429 if the SDK exposes it."""
    headers = getattr(err, "headers", None) or {}
    raw = headers.get("Retry-After") or headers.get("retry-after")
    if raw is None:
        return None
    try:
        return float(raw)
    except TypeError, ValueError:
        return None


def _is_notion_api_error(err: Exception) -> bool:
    """Best-effort check for a notion_client APIResponseError without forcing import."""
    if err.__class__.__name__ in {"APIResponseError", "HTTPResponseError"}:
        return True
    # Walk the MRO by class name so we don't depend on notion_client being
    # importable at module-load time.
    return any(c.__name__ in {"APIResponseError", "HTTPResponseError"} for c in type(err).__mro__)


def _friendly_notion_error_message(err: Exception) -> str:
    """Map a Notion API error to a friendly, actionable message."""
    code = _extract_api_error_code(err)
    if code in {"unauthorized", "restricted_resource"}:
        return (
            "Notion API rejected the request: the integration token is missing, invalid, "
            "or does not have access to NOTION_PARENT_PAGE_ID. Verify NOTION_TOKEN and "
            "confirm the parent page is shared with the integration."
        )
    if code == "object_not_found":
        return (
            "Notion API could not find the target page. The page may have been deleted "
            "or the integration was removed from it. Re-run with --notion-force-new to "
            "create a fresh page, or share the parent page with the integration again."
        )
    if code == "rate_limited":
        return "Notion API rate limit exceeded after retries. Try again later or reduce concurrency."
    if code == "validation_error":
        return f"Notion API rejected the payload: {err}"
    return f"Notion API call failed ({code or 'unknown error'}): {err}"


def _call_with_rate_limit_retry(func, *args, **kwargs):
    """Invoke a Notion SDK call, retrying with backoff on 429 rate-limit errors.

    Non-rate-limit API errors are re-raised immediately for the caller to map
    to a friendly message; this helper only owns the 429 retry policy.
    """
    delay = _RATE_LIMIT_BASE_DELAY_SECONDS
    last_exc: Exception | None = None
    for attempt in range(1, _RATE_LIMIT_MAX_ATTEMPTS + 1):
        try:
            return func(*args, **kwargs)
        except Exception as exc:
            if not _is_notion_api_error(exc) or _extract_api_error_code(exc) != "rate_limited":
                raise
            last_exc = exc
            if attempt == _RATE_LIMIT_MAX_ATTEMPTS:
                break
            retry_after = _extract_retry_after_seconds(exc)
            time.sleep(retry_after if retry_after is not None else delay)
            delay *= 2
    # All retries exhausted. Re-raise the last 429 so the caller maps it to
    # a friendly message via _friendly_notion_error_message.
    assert last_exc is not None
    raise last_exc


def _list_all_child_block_ids(client: Any, page_id: str) -> list[str]:
    """Return every direct child block ID of ``page_id`` across all pages.

    Collect first, delete second: cursors returned by Notion are content-based,
    so iterating list-then-delete-in-loop produces undefined behaviour once
    the page changes mid-iteration.
    """
    block_ids: list[str] = []
    cursor: str | None = None
    while True:
        kwargs: dict[str, Any] = {"block_id": page_id}
        if cursor:
            kwargs["start_cursor"] = cursor
        response = _call_with_rate_limit_retry(client.blocks.children.list, **kwargs)
        for block in response.get("results", []):
            block_id = block.get("id")
            if block_id:
                block_ids.append(block_id)
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")
        if cursor is None:
            break
    return block_ids


def _clear_page_blocks(client: Any, page_id: str) -> None:
    """Delete all child blocks from a Notion page (no bulk-clear API exists).

    Listing and deletion are split into two phases so the pagination cursor
    cannot drift, and the per-block DELETE calls are issued from a small
    thread pool to keep update time tolerable for large pages.
    """
    block_ids = _list_all_child_block_ids(client, page_id)
    if not block_ids:
        return

    def _delete_one(block_id: str) -> None:
        _call_with_rate_limit_retry(client.blocks.delete, block_id=block_id)

    if len(block_ids) == 1:
        _delete_one(block_ids[0])
        return

    with ThreadPoolExecutor(max_workers=_DELETE_WORKER_COUNT) as pool:
        futures = [pool.submit(_delete_one, bid) for bid in block_ids]
        for fut in as_completed(futures):
            # Re-raise the first delete failure; remaining futures complete
            # naturally as the pool unwinds.
            fut.result()


def _append_blocks(
    client: Any,
    page_id: str,
    blocks: list[dict],
    batch_size: int = 100,
) -> None:
    """Append blocks to a Notion page in batches (API limit: 100 per call)."""
    for i in range(0, len(blocks), batch_size):
        _call_with_rate_limit_retry(
            client.blocks.children.append,
            block_id=page_id,
            children=blocks[i : i + batch_size],
        )


def create_or_update_page(
    client: Any,
    parent_page_id: str,
    page_title: str,
    data_view_id: str,
    blocks: list[dict],
    registry_path: Path,
    *,
    force_new: bool = False,
) -> str:
    """Create a new Notion page or update the existing one for this data view.

    Returns the Notion page ID. On CREATE, the registry entry is written only
    after a successful block append, so a mid-flight failure leaves the
    registry unchanged and the next run creates a fresh page. On UPDATE the
    page ID does not change, so the registry is not rewritten.
    """
    existing_page_id = None if force_new else lookup_page_id(registry_path, data_view_id)

    if existing_page_id:
        _clear_page_blocks(client, existing_page_id)
        _append_blocks(client, existing_page_id, blocks)
        return existing_page_id

    page = _call_with_rate_limit_retry(
        client.pages.create,
        parent={"page_id": parent_page_id},
        properties={"title": [{"type": "text", "text": {"content": page_title}}]},
    )
    page_id = page["id"]
    _append_blocks(client, page_id, blocks)
    store_page_id(registry_path, data_view_id, page_id)
    return page_id


# ---------------------------------------------------------------------------
# Writer entry point (matches writer protocol)
# ---------------------------------------------------------------------------


def write_notion_output(
    data_dict: dict[str, pd.DataFrame],
    metadata_dict: dict[str, Any],
    base_filename: str,
    output_dir: str | Path,
    logger: logging.Logger,
    *,
    force_new: bool = False,
    database_id: str | None = None,
    create_database: bool = False,
) -> str:
    """Publish SDR data to a Notion page (and optionally a DB row).

    Returns a ``notion://pages/<page_id>`` identifier (not a file path).
    ``base_filename`` is accepted for writer-protocol parity with file-emitting
    writers and is used as a fallback when ``metadata_dict`` lacks
    ``Data View ID`` or ``Data View Name``.

    When ``database_id`` is provided (or ``create_database`` is True and the
    env var ``NOTION_DATABASE_ID`` is unset), also upserts a row in the SDR
    Registry database keyed by ``Data View ID``.

    Raises NotionConfigurationError / NotionDependencyError / NotionAPIError —
    callers (CLI dispatcher) are responsible for converting these to exit codes.
    """
    logger.info("✓ Publishing to Notion...")

    client_cls = _require_notion_client()
    token, parent_page_id = resolve_notion_credentials()

    data_view_id = str(metadata_dict.get("Data View ID", base_filename))
    dv_name = str(metadata_dict.get("Data View Name", base_filename))
    page_title = f"{dv_name} — SDR"

    blocks = build_sdr_blocks(data_dict, metadata_dict)
    registry_path = get_registry_path(output_dir)

    client = client_cls(auth=token)
    try:
        page_id = create_or_update_page(
            client,
            parent_page_id,
            page_title,
            data_view_id,
            blocks,
            registry_path,
            force_new=force_new,
        )

        if database_id is not None or create_database:
            from cja_auto_sdr.output.notion_database import (
                build_row_properties,
                ensure_database,
                upsert_database_row,
            )
            from cja_auto_sdr.output.notion_registry import (
                lookup_database_row_id,
                store_database_row_id,
            )

            db_id = ensure_database(
                client,
                parent_page_id=parent_page_id,
                database_id=database_id,
                create_if_missing=create_database,
            )
            properties = build_row_properties(
                data_dict,
                metadata_dict,
                page_id,
                tool_version=__version__,
            )
            existing_row_id = lookup_database_row_id(registry_path, data_view_id)
            row_id = upsert_database_row(
                client,
                database_id=db_id,
                existing_row_id=existing_row_id,
                properties=properties,
            )
            store_database_row_id(registry_path, data_view_id, row_id)
            logger.info("✓ Notion DB row upserted: %s", row_id)
    except Exception as exc:
        if _is_notion_api_error(exc):
            raise NotionAPIError(_friendly_notion_error_message(exc)) from exc
        raise

    logger.info("✓ Notion page published: notion://pages/%s", page_id)
    return f"notion://pages/{page_id}"
