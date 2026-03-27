"""Compatibility routing helpers for extracted org writer implementations."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from types import MappingProxyType

_OVERRIDE_KEY = tuple[str, str]
_OVERRIDE_STACK = tuple[object, ...]
_OVERRIDES: ContextVar[dict[_OVERRIDE_KEY, _OVERRIDE_STACK] | None] = ContextVar(
    "org_writer_compat_overrides",
    default=None,
)
_MISSING = object()
EMPTY_OVERRIDE_MAPPING: Mapping[str, str] = MappingProxyType({})


def freeze_override_mapping(mapping: Mapping[str, str]) -> Mapping[str, str]:
    """Copy and freeze an override mapping so wrapper definitions stay immutable."""
    return MappingProxyType(dict(mapping))


def compose_override_mapping(*mappings: Mapping[str, str]) -> Mapping[str, str]:
    """Merge override mappings so writer wrappers inherit helper dependencies centrally."""
    combined: dict[str, str] = {}
    for mapping in mappings:
        combined.update(mapping)
    return freeze_override_mapping(combined)


# Centralized compatibility dependency maps keep legacy re-export wrappers aligned
# with the canonical writer modules they delegate to.
CONSOLE_WRITER_OVERRIDE_MAPPING = freeze_override_mapping(
    {
        "_render_distribution_bar": "_render_distribution_bar",
        "_print_trending_console_section": "_print_trending_console_section",
    },
)
CONSOLE_STATS_ONLY_OVERRIDE_MAPPING = freeze_override_mapping(
    {
        "_print_trending_console_section": "_print_trending_console_section",
    },
)
JSON_BUILDER_OVERRIDE_MAPPING = freeze_override_mapping(
    {
        "_normalize_recommendation_for_json": "_normalize_recommendation_for_json",
        "_trending_snapshots_to_dicts": "_trending_snapshots_to_dicts",
    },
)
JSON_WRITER_OVERRIDE_MAPPING = compose_override_mapping(
    {"build_org_report_json_data": "build_org_report_json_data"},
    JSON_BUILDER_OVERRIDE_MAPPING,
)
EXCEL_WRITER_OVERRIDE_MAPPING = freeze_override_mapping(
    {
        "_flatten_recommendation_for_tabular": "_flatten_recommendation_for_tabular",
        "_normalize_recommendation_for_json": "_normalize_recommendation_for_json",
        "_ranked_drift_entries": "_ranked_drift_entries",
        "_trending_delta_column_specs": "_trending_delta_column_specs",
        "_trending_delta_metric_rows": "_trending_delta_metric_rows",
        "_trending_matrix_rows": "_trending_matrix_rows",
        "_trending_snapshot_column_specs": "_trending_snapshot_column_specs",
        "_trending_snapshot_metric_rows": "_trending_snapshot_metric_rows",
    },
)
MARKDOWN_WRITER_OVERRIDE_MAPPING = freeze_override_mapping(
    {
        "_format_recommendation_context_entries": "_format_recommendation_context_entries",
        "_normalize_recommendation_for_json": "_normalize_recommendation_for_json",
        "_render_trending_markdown": "_render_trending_markdown",
    },
)
HTML_WRITER_OVERRIDE_MAPPING = freeze_override_mapping(
    {
        "_format_recommendation_context_entries": "_format_recommendation_context_entries",
        "_normalize_recommendation_for_json": "_normalize_recommendation_for_json",
        "_render_trending_html": "_render_trending_html",
    },
)
CSV_WRITER_OVERRIDE_MAPPING = freeze_override_mapping(
    {
        "_flatten_recommendation_for_tabular": "_flatten_recommendation_for_tabular",
        "_normalize_recommendation_for_json": "_normalize_recommendation_for_json",
        "_ranked_drift_entries": "_ranked_drift_entries",
        "_trending_delta_csv_rows": "_trending_delta_csv_rows",
        "_trending_snapshot_csv_rows": "_trending_snapshot_csv_rows",
    },
)


def _compat_key(target_module_name: str, attr_name: str) -> _OVERRIDE_KEY:
    return (target_module_name, attr_name)


def _current_overrides() -> dict[_OVERRIDE_KEY, _OVERRIDE_STACK]:
    return _OVERRIDES.get() or {}


def _peek_override(
    overrides: Mapping[_OVERRIDE_KEY, _OVERRIDE_STACK],
    key: _OVERRIDE_KEY,
    default: object,
) -> object:
    stack = overrides.get(key)
    if not stack:
        return default
    return stack[-1]


@contextmanager
def _override_scope_normalized(
    overrides: Mapping[_OVERRIDE_KEY, object],
    *,
    preserve_existing: bool = False,
):
    """Push normalized overrides onto the current context."""
    current = _current_overrides()
    updated = current.copy()
    if preserve_existing:
        for key, override in overrides.items():
            updated.setdefault(key, (override,))
    else:
        for key, override in overrides.items():
            updated[key] = (*updated.get(key, ()), override)
    token = _OVERRIDES.set(updated)
    try:
        yield
    finally:
        _OVERRIDES.reset(token)


@contextmanager
def _suppress_override(target_module_name: str, attr_name: str):
    """Temporarily hide only the active override layer for one key."""
    key = _compat_key(target_module_name, attr_name)
    current = _current_overrides()
    stack = current.get(key)
    if not stack:
        yield
        return

    updated = current.copy()
    if len(stack) == 1:
        updated.pop(key, None)
    else:
        updated[key] = stack[:-1]
    token = _OVERRIDES.set(updated)
    try:
        yield
    finally:
        _OVERRIDES.reset(token)


def _normalize_module_overrides(
    target_module_name: str,
    overrides: Mapping[str, object],
) -> dict[_OVERRIDE_KEY, object]:
    return {_compat_key(target_module_name, attr_name): override for attr_name, override in overrides.items()}


def resolve_override(target_module_name: str, attr_name: str, default: object) -> object:
    """Resolve a compatibility override for a target module attribute."""
    return _peek_override(_current_overrides(), _compat_key(target_module_name, attr_name), default)


def call_override[**P, R](
    target_module_name: str,
    attr_name: str,
    default: Callable[P, R],
    *args: P.args,
    **kwargs: P.kwargs,
) -> R:
    """Call a possibly overridden target attribute using the current context."""
    active = resolve_override(target_module_name, attr_name, default)
    return active(*args, **kwargs)


def make_override_proxy[**P, R](
    target_module_name: str,
    attr_name: str,
    default: Callable[P, R],
) -> Callable[P, R]:
    """Create a callable proxy that resolves overrides from the current context only."""

    @wraps(default)
    def proxy(*args: P.args, **kwargs: P.kwargs) -> R:
        active = resolve_override(target_module_name, attr_name, default)
        if active is default:
            return default(*args, **kwargs)
        with _suppress_override(target_module_name, attr_name):
            return active(*args, **kwargs)

    proxy.__module__ = target_module_name
    return proxy


def collect_legacy_overrides(
    source_module_name: str,
    override_mapping: Mapping[str, str],
    *,
    baselines: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Collect override callables from a legacy compatibility module."""
    source_module = importlib.import_module(source_module_name)
    return {
        target_attr_name: getattr(source_module, legacy_attr_name)
        for target_attr_name, legacy_attr_name in override_mapping.items()
        if hasattr(source_module, legacy_attr_name)
        and (baselines is None or getattr(source_module, legacy_attr_name) is not baselines.get(legacy_attr_name))
    }


def _collect_active_source_scope_overrides(
    source_module_name: str,
    override_mapping: Mapping[str, str],
) -> dict[str, object]:
    """Project active legacy source-surface overrides into canonical target keys."""
    current = _current_overrides()
    if not current:
        return {}

    projected: dict[str, object] = {}
    for target_attr_name, legacy_attr_name in override_mapping.items():
        source_key = _compat_key(source_module_name, legacy_attr_name)
        active = _peek_override(current, source_key, _MISSING)
        if active is not _MISSING:
            projected[target_attr_name] = active
    return projected


@contextmanager
def override_scope(target_module_name: str, overrides: Mapping[str, object]):
    """Apply compatibility overrides to the current execution context only."""
    with _override_scope_normalized(_normalize_module_overrides(target_module_name, overrides)):
        yield


def make_compat_wrapper[**P, R](
    source_module_name: str,
    target: Callable[P, R],
    *,
    target_module_name: str,
    override_mapping: Mapping[str, str],
) -> Callable[P, R]:
    """Wrap a legacy export so monkeypatches apply only within that call context."""
    collected = dict(override_mapping)
    source_module = importlib.import_module(source_module_name)
    baseline_source_values = {
        legacy_attr_name: getattr(source_module, legacy_attr_name)
        for legacy_attr_name in collected.values()
        if hasattr(source_module, legacy_attr_name)
    }
    target_attr_name = target.__name__

    @wraps(target)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        overrides = collect_legacy_overrides(
            source_module_name,
            collected,
            baselines=baseline_source_values,
        )
        overrides.update(_collect_active_source_scope_overrides(source_module_name, collected))
        source_override = resolve_override(source_module_name, target_attr_name, _MISSING)
        current_target = getattr(importlib.import_module(target_module_name), target_attr_name)

        if source_override is not _MISSING:
            with _suppress_override(source_module_name, target_attr_name):
                if not overrides:
                    return source_override(*args, **kwargs)
                with _override_scope_normalized(
                    _normalize_module_overrides(target_module_name, overrides),
                    preserve_existing=True,
                ):
                    return source_override(*args, **kwargs)

        if not overrides:
            return current_target(*args, **kwargs)
        with _override_scope_normalized(
            _normalize_module_overrides(target_module_name, overrides),
            preserve_existing=True,
        ):
            return current_target(*args, **kwargs)

    wrapper.__module__ = source_module_name
    return wrapper
