"""Shared normalization helpers for discovery and inspection command payloads."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

import pandas as pd

_NULL_LIKE_TEXT_VALUES = frozenset({"<na>", "n/a", "nan", "none", "null"})
_OWNER_FIELD_PRIORITY = ("name", "fullName", "full_name", "ownerFullName", "login", "email", "imsUserId", "id")
_OWNER_ALIAS_FIELDS = ("ownerFullName", "ownerName", "owner_name", "owner_full_name")
_TAG_NAME_FIELDS = ("name", "label", "title", "id")


def _is_na_like(value: Any) -> bool:
    """Return True when pandas recognizes the value as missing."""
    try:
        is_na = pd.isna(value)
    except TypeError, ValueError:
        return False

    if isinstance(is_na, bool):
        return is_na
    if hasattr(is_na, "all"):
        try:
            return bool(is_na.all())
        except TypeError, ValueError:
            return False
    return False


def is_missing_value(
    value: Any,
    *,
    treat_blank_string: bool = False,
    treat_null_like_strings: bool = False,
) -> bool:
    """Return True when a value should be treated as missing for display logic."""
    if value is None or _is_na_like(value):
        return True

    if isinstance(value, str):
        text = value.strip()
        if treat_blank_string and not text:
            return True
        if treat_null_like_strings and text.casefold() in _NULL_LIKE_TEXT_VALUES:
            return True

    return False


def normalize_display_text(
    value: Any,
    *,
    default: str = "",
    treat_null_like_strings: bool = False,
) -> str:
    """Normalize arbitrary values to display-safe text."""
    if is_missing_value(
        value,
        treat_blank_string=True,
        treat_null_like_strings=treat_null_like_strings,
    ):
        return default
    text = str(value).strip()
    if treat_null_like_strings and text.casefold() in _NULL_LIKE_TEXT_VALUES:
        return default
    return text or default


def pick_first_present_value(
    candidates: Iterable[Any],
    *,
    treat_blank_string: bool = True,
    treat_null_like_strings: bool = False,
) -> Any | None:
    """Return the first non-missing candidate value."""
    for candidate in candidates:
        if is_missing_value(
            candidate,
            treat_blank_string=treat_blank_string,
            treat_null_like_strings=treat_null_like_strings,
        ):
            continue
        return candidate
    return None


def pick_first_present_text(
    candidates: Iterable[Any],
    *,
    default: str = "",
    treat_null_like_strings: bool = False,
) -> str:
    """Return normalized text for the first non-missing candidate."""
    candidate = pick_first_present_value(
        candidates,
        treat_blank_string=True,
        treat_null_like_strings=treat_null_like_strings,
    )
    if candidate is None:
        return default
    return normalize_display_text(
        candidate,
        default=default,
        treat_null_like_strings=treat_null_like_strings,
    )


def extract_owner_name(
    owner_data: Any,
    *,
    default: str = "N/A",
) -> str:
    """Extract a displayable owner name from heterogenous API owner payloads."""
    if isinstance(owner_data, Mapping):
        for key in _OWNER_FIELD_PRIORITY:
            owner_name = normalize_display_text(
                owner_data.get(key),
                default="",
                treat_null_like_strings=True,
            )
            if owner_name:
                return owner_name
        return default
    return normalize_display_text(
        owner_data,
        default=default,
        treat_null_like_strings=True,
    )


def extract_owner_name_from_record(
    record: Mapping[str, Any],
    *,
    default: str = "N/A",
) -> str:
    """Extract owner name from record-level aliases used by API endpoints."""
    owner_name = extract_owner_name(record.get("owner"), default=default)
    if owner_name != default:
        return owner_name

    for key in _OWNER_ALIAS_FIELDS:
        alias_name = normalize_display_text(
            record.get(key),
            default="",
            treat_null_like_strings=True,
        )
        if alias_name:
            return alias_name
    return default


def extract_tags(tags_data: Any) -> list[str]:
    """Extract normalized tag names from API tags payloads."""
    if is_missing_value(tags_data):
        return []

    if isinstance(tags_data, Mapping):
        raw_tags: list[Any] = [tags_data]
    elif isinstance(tags_data, (list, tuple, set)):
        raw_tags = list(tags_data)
    else:
        raw_tags = [tags_data]

    tags: list[str] = []
    for tag in raw_tags:
        if is_missing_value(tag):
            continue

        if isinstance(tag, Mapping):
            normalized = pick_first_present_text(
                (tag.get(key) for key in _TAG_NAME_FIELDS),
                default="",
                treat_null_like_strings=True,
            )
        else:
            normalized = normalize_display_text(
                tag,
                default="",
                treat_null_like_strings=True,
            )

        if normalized:
            tags.append(normalized)
    return tags
