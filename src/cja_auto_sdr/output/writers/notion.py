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
