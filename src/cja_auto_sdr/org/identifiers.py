"""Shared identifier normalization helpers for org snapshot/trending flows."""

from __future__ import annotations

from typing import Any


def normalize_org_report_data_view_id(value: Any) -> str:
    """Normalize a serialized org-report identifier for stable comparisons."""
    if value is None:
        return ""
    return str(value).strip()
