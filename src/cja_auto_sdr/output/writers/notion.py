"""Notion output writer: block builder + Notion API layer.

Credentials (env vars required, not stored in config.json):
  NOTION_TOKEN            — Notion internal integration token
  NOTION_PARENT_PAGE_ID   — Parent page under which SDR child pages are created

Install the optional dep: uv pip install 'cja-auto-sdr[notion]'
"""
from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

import pandas as pd

from cja_auto_sdr.core.version import __version__
from cja_auto_sdr.output.notion_registry import (
    get_registry_path,
    lookup_page_id,
    store_page_id,
)

__all__ = ["write_notion_output"]

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
    "Data Quality": "🛡️",
}
_DQ_SEVERITY_ICONS = {
    "ERROR": "🔴",
    "CRITICAL": "🔴",
    "WARN": "⚠️",
    "WARNING": "⚠️",
    "INFO": "ℹ️",
}


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
            "cells": [
                [{"type": "text", "text": {"content": str(c)[:2000]}}] for c in cells
            ],
        },
    }


def _table_block(df: pd.DataFrame) -> dict:
    cols = list(df.columns)
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
    if df is None or df.empty:
        return []
    icon = _SECTION_ICONS.get(section_name, "📄")
    return [
        _heading2_block(f"{icon} {section_name}"),
        _table_block(df),
    ]


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
    lines = []
    for key in priority_keys:
        if key in metadata_dict:
            lines.append(f"{key}: {metadata_dict[key]}")
    for key, val in metadata_dict.items():
        if key not in set(priority_keys):
            lines.append(f"{key}: {val}")
    return _callout_block("\n".join(lines), emoji="📋")


def build_sdr_blocks(
    data_dict: dict[str, pd.DataFrame], metadata_dict: dict,
) -> list[dict]:
    blocks: list[dict] = [_metadata_callout_block(metadata_dict), _divider_block()]

    dq_df = data_dict.get("Data Quality")
    if dq_df is not None and not dq_df.empty:
        blocks.append(_heading2_block("🛡️ Data Quality"))
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
# Credential resolution
# ---------------------------------------------------------------------------

def resolve_notion_credentials() -> tuple[str, str]:
    """Return (NOTION_TOKEN, NOTION_PARENT_PAGE_ID) from env / .env file."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    token = os.environ.get("NOTION_TOKEN")
    parent_page_id = os.environ.get("NOTION_PARENT_PAGE_ID")

    if not token:
        print(
            "ERROR: NOTION_TOKEN is not set. "
            "Set it as an environment variable or add it to a .env file.",
            file=sys.stderr,
        )
        sys.exit(1)

    if not parent_page_id:
        print(
            "ERROR: NOTION_PARENT_PAGE_ID is not set. "
            "Set it as an environment variable or add it to a .env file.",
            file=sys.stderr,
        )
        sys.exit(1)

    return token, parent_page_id


def _require_notion_client():
    """Return notion_client.Client class or exit with install instructions."""
    try:
        from notion_client import Client
        return Client
    except ImportError:
        print(
            "ERROR: Notion output requires the notion extra.\n"
            "Install it with: uv pip install 'cja-auto-sdr[notion]'",
            file=sys.stderr,
        )
        sys.exit(1)


# ---------------------------------------------------------------------------
# Notion API operations
# ---------------------------------------------------------------------------

def _clear_page_blocks(client: Any, page_id: str) -> None:
    """Delete all child blocks from a Notion page (no bulk-clear API exists)."""
    cursor = None
    while True:
        kwargs: dict[str, Any] = {"block_id": page_id}
        if cursor:
            kwargs["start_cursor"] = cursor
        response = client.blocks.children.list(**kwargs)
        for block in response.get("results", []):
            client.blocks.delete(block_id=block["id"])
        if not response.get("has_more"):
            break
        cursor = response.get("next_cursor")


def _append_blocks(
    client: Any, page_id: str, blocks: list[dict], batch_size: int = 100,
) -> None:
    """Append blocks to a Notion page in batches (API limit: 100 per call)."""
    for i in range(0, len(blocks), batch_size):
        client.blocks.children.append(
            block_id=page_id, children=blocks[i:i + batch_size],
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

    Returns the Notion page ID. Registry entry is written only after a
    successful block append.
    """
    existing_page_id = (
        None if force_new else lookup_page_id(registry_path, data_view_id)
    )

    if existing_page_id:
        _clear_page_blocks(client, existing_page_id)
        _append_blocks(client, existing_page_id, blocks)
        store_page_id(registry_path, data_view_id, existing_page_id)
        return existing_page_id

    page = client.pages.create(
        parent={"page_id": parent_page_id},
        properties={"title": [{"type": "text", "text": {"content": page_title}}]},
    )
    page_id = page["id"]
    _append_blocks(client, page_id, blocks)
    store_page_id(registry_path, data_view_id, page_id)
    return page_id
