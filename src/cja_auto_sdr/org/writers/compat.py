"""Compatibility routing helpers for extracted org writer implementations."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Mapping
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from types import MappingProxyType

_OVERRIDE_KEY = tuple[str, str]
_OVERRIDE_DESTINATION = str | _OVERRIDE_KEY
_OVERRIDES: ContextVar[dict[_OVERRIDE_KEY, object] | None] = ContextVar(
    "org_writer_compat_overrides",
    default=None,
)
EMPTY_OVERRIDE_MAPPING: Mapping[_OVERRIDE_DESTINATION, str] = MappingProxyType({})

__all__ = [
    "COMMON_RECOMMENDATION_OVERRIDE_MAPPING",
    "CONSOLE_STATS_ONLY_OVERRIDE_MAPPING",
    "CONSOLE_WRITER_OVERRIDE_MAPPING",
    "CSV_WRITER_OVERRIDE_MAPPING",
    "EMPTY_OVERRIDE_MAPPING",
    "EXCEL_WRITER_OVERRIDE_MAPPING",
    "HTML_WRITER_OVERRIDE_MAPPING",
    "JSON_BUILDER_OVERRIDE_MAPPING",
    "JSON_WRITER_OVERRIDE_MAPPING",
    "MARKDOWN_WRITER_OVERRIDE_MAPPING",
    "TRENDING_LABEL_OVERRIDE_MAPPING",
    "call_override",
    "collect_legacy_overrides",
    "compose_override_mapping",
    "freeze_override_mapping",
    "make_compat_wrapper",
    "make_override_proxy",
    "override_scope",
    "resolve_override",
]

_COMMON_MODULE = "cja_auto_sdr.org.writers.common"
_HTML_MODULE = "cja_auto_sdr.org.writers.html"
_MARKDOWN_MODULE = "cja_auto_sdr.org.writers.markdown"
_TRENDING_MODULE = "cja_auto_sdr.org.writers.trending"
_RECOMMENDATION_CONTEXT_PROXY_MODULES = (
    _COMMON_MODULE,
    _MARKDOWN_MODULE,
    _HTML_MODULE,
)


def freeze_override_mapping(
    mapping: Mapping[_OVERRIDE_DESTINATION, str],
) -> Mapping[_OVERRIDE_DESTINATION, str]:
    """Copy and freeze an override mapping so wrapper definitions stay immutable."""
    return MappingProxyType(dict(mapping))


def compose_override_mapping(
    *mappings: Mapping[_OVERRIDE_DESTINATION, str],
) -> Mapping[_OVERRIDE_DESTINATION, str]:
    """Merge override mappings so writer wrappers inherit helper dependencies centrally."""
    combined: dict[_OVERRIDE_DESTINATION, str] = {}
    for mapping in mappings:
        combined.update(mapping)
    return freeze_override_mapping(combined)


def _validate_override_destination(destination: _OVERRIDE_DESTINATION) -> None:
    """Validate a public override destination key before collection or normalization."""
    if isinstance(destination, str):
        return
    if isinstance(destination, tuple):
        if len(destination) != 2 or not all(isinstance(part, str) for part in destination):
            raise TypeError("override_mapping tuple keys must be (target_module_name, attr_name) string pairs")
        return
    raise TypeError("override_mapping keys must be strings or (module, attr) tuples")


def _normalize_override_mapping(
    mapping: Mapping[_OVERRIDE_DESTINATION, str],
    *,
    default_target_module_name: str,
) -> dict[_OVERRIDE_KEY, str]:
    """Normalize mixed override destinations into explicit module/attribute keys."""
    normalized: dict[_OVERRIDE_KEY, str] = {}
    for destination, legacy_attr_name in mapping.items():
        _validate_override_destination(destination)
        if isinstance(destination, tuple):
            normalized[destination] = legacy_attr_name
            continue
        normalized[_compat_key(default_target_module_name, destination)] = legacy_attr_name
    return normalized


def _fanout_override_mapping(
    legacy_attr_name: str,
    *target_module_names: str,
) -> Mapping[_OVERRIDE_DESTINATION, str]:
    """Build tuple-key override mappings for one legacy attr across multiple proxy modules."""
    return freeze_override_mapping(
        {(target_module_name, legacy_attr_name): legacy_attr_name for target_module_name in target_module_names}
    )


# Centralized compatibility dependency maps keep legacy re-export wrappers aligned
# with the canonical writer modules they delegate to.
COMMON_RECOMMENDATION_OVERRIDE_MAPPING = compose_override_mapping(
    # Context entries are rendered directly by the canonical markdown/html writers
    # and nested under common.py JSON normalization.
    _fanout_override_mapping(
        "_format_recommendation_context_entries",
        *_RECOMMENDATION_CONTEXT_PROXY_MODULES,
    ),
    _fanout_override_mapping("_normalize_recommendation_severity", _COMMON_MODULE),
)
TRENDING_LABEL_OVERRIDE_MAPPING = compose_override_mapping(
    _fanout_override_mapping("_format_trending_period_label", _TRENDING_MODULE),
    _fanout_override_mapping("_format_trending_timestamp_short", _TRENDING_MODULE),
)
CONSOLE_WRITER_OVERRIDE_MAPPING = compose_override_mapping(
    {
        "_render_distribution_bar": "_render_distribution_bar",
        "_print_trending_console_section": "_print_trending_console_section",
    },
    TRENDING_LABEL_OVERRIDE_MAPPING,
)
CONSOLE_STATS_ONLY_OVERRIDE_MAPPING = compose_override_mapping(
    {
        "_print_trending_console_section": "_print_trending_console_section",
    },
    TRENDING_LABEL_OVERRIDE_MAPPING,
)
JSON_BUILDER_OVERRIDE_MAPPING = compose_override_mapping(
    {
        "_normalize_recommendation_for_json": "_normalize_recommendation_for_json",
        "_trending_snapshots_to_dicts": "_trending_snapshots_to_dicts",
    },
    COMMON_RECOMMENDATION_OVERRIDE_MAPPING,
)
JSON_WRITER_OVERRIDE_MAPPING = compose_override_mapping(
    {"build_org_report_json_data": "build_org_report_json_data"},
    JSON_BUILDER_OVERRIDE_MAPPING,
)
EXCEL_WRITER_OVERRIDE_MAPPING = compose_override_mapping(
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
    COMMON_RECOMMENDATION_OVERRIDE_MAPPING,
    TRENDING_LABEL_OVERRIDE_MAPPING,
)
MARKDOWN_WRITER_OVERRIDE_MAPPING = compose_override_mapping(
    {
        "_normalize_recommendation_for_json": "_normalize_recommendation_for_json",
        "_render_trending_markdown": "_render_trending_markdown",
    },
    COMMON_RECOMMENDATION_OVERRIDE_MAPPING,
    TRENDING_LABEL_OVERRIDE_MAPPING,
)
HTML_WRITER_OVERRIDE_MAPPING = compose_override_mapping(
    {
        "_normalize_recommendation_for_json": "_normalize_recommendation_for_json",
        "_render_trending_html": "_render_trending_html",
    },
    COMMON_RECOMMENDATION_OVERRIDE_MAPPING,
    TRENDING_LABEL_OVERRIDE_MAPPING,
)
CSV_WRITER_OVERRIDE_MAPPING = compose_override_mapping(
    {
        "_flatten_recommendation_for_tabular": "_flatten_recommendation_for_tabular",
        "_normalize_recommendation_for_json": "_normalize_recommendation_for_json",
        "_ranked_drift_entries": "_ranked_drift_entries",
        "_trending_delta_csv_rows": "_trending_delta_csv_rows",
        "_trending_snapshot_csv_rows": "_trending_snapshot_csv_rows",
    },
    COMMON_RECOMMENDATION_OVERRIDE_MAPPING,
    TRENDING_LABEL_OVERRIDE_MAPPING,
)


def _compat_key(target_module_name: str, attr_name: str) -> _OVERRIDE_KEY:
    return (target_module_name, attr_name)


def _current_overrides() -> dict[_OVERRIDE_KEY, object]:
    return _OVERRIDES.get() or {}


def resolve_override(target_module_name: str, attr_name: str, default: object) -> object:
    """Resolve a compatibility override for a target module attribute."""
    return _current_overrides().get(_compat_key(target_module_name, attr_name), default)


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
        return active(*args, **kwargs)

    proxy.__module__ = target_module_name
    return proxy


def _collect_source_overrides[K](
    source_module_name: str,
    override_mapping: Mapping[K, str],
    *,
    baselines: Mapping[str, object] | None = None,
) -> dict[K, object]:
    """Collect override objects from a source module for a pre-shaped mapping."""
    source_module = importlib.import_module(source_module_name)
    collected: dict[K, object] = {}
    for target_key, legacy_attr_name in override_mapping.items():
        if not hasattr(source_module, legacy_attr_name):
            continue
        override = getattr(source_module, legacy_attr_name)
        if baselines is not None and override is baselines.get(legacy_attr_name):
            continue
        collected[target_key] = override
    return collected


def _collect_normalized_legacy_overrides(
    source_module_name: str,
    override_mapping: Mapping[_OVERRIDE_DESTINATION, str],
    *,
    default_target_module_name: str,
    baselines: Mapping[str, object] | None = None,
) -> dict[_OVERRIDE_KEY, object]:
    """Collect normalized tuple-key overrides for internal compat wrapper routing."""
    return _collect_source_overrides(
        source_module_name,
        _normalize_override_mapping(
            override_mapping,
            default_target_module_name=default_target_module_name,
        ),
        baselines=baselines,
    )


def collect_legacy_overrides(
    source_module_name: str,
    override_mapping: Mapping[_OVERRIDE_DESTINATION, str],
    *,
    baselines: Mapping[str, object] | None = None,
) -> dict[_OVERRIDE_DESTINATION, object]:
    """Collect override callables from a legacy compatibility module.

    Flat string-key mappings keep the 3.4.7 ``{"target_attr": override}``
    result contract. Mixed and tuple-key mappings introduced for 3.4.8
    routing hardening are also accepted and preserve their explicit keys so
    exported shared mappings remain consumable by callers.
    """
    public_mapping: dict[_OVERRIDE_DESTINATION, str] = {}
    for target_key, legacy_attr_name in override_mapping.items():
        _validate_override_destination(target_key)
        public_mapping[target_key] = legacy_attr_name
    return _collect_source_overrides(
        source_module_name,
        public_mapping,
        baselines=baselines,
    )


@contextmanager
def _override_scope_normalized(overrides: Mapping[_OVERRIDE_KEY, object]):
    """Apply normalized tuple-key overrides to the current execution context."""
    current = _current_overrides()
    updated = current.copy()
    updated.update(overrides)
    token = _OVERRIDES.set(updated)
    try:
        yield
    finally:
        _OVERRIDES.reset(token)


@contextmanager
def override_scope(target_module_name: str, overrides: Mapping[str, object]):
    """Apply compatibility overrides to the current execution context only."""
    normalized_overrides: dict[_OVERRIDE_KEY, object] = {}
    for attr_name, override in overrides.items():
        if not isinstance(attr_name, str):
            raise TypeError("override_scope() override keys must be strings")
        normalized_overrides[_compat_key(target_module_name, attr_name)] = override
    with _override_scope_normalized(normalized_overrides):
        yield


def make_compat_wrapper[**P, R](
    source_module_name: str,
    target: Callable[P, R],
    *,
    target_module_name: str,
    override_mapping: Mapping[_OVERRIDE_DESTINATION, str],
) -> Callable[P, R]:
    """Wrap a legacy export so monkeypatches apply only within that call context."""
    collected = dict(
        _normalize_override_mapping(
            override_mapping,
            default_target_module_name=target_module_name,
        )
    )
    source_module = importlib.import_module(source_module_name)
    baseline_source_values = {
        legacy_attr_name: getattr(source_module, legacy_attr_name)
        for legacy_attr_name in collected.values()
        if hasattr(source_module, legacy_attr_name)
    }
    target_attr_name = target.__name__

    @wraps(target)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        current_target = getattr(importlib.import_module(target_module_name), target_attr_name)
        overrides = _collect_normalized_legacy_overrides(
            source_module_name,
            collected,
            default_target_module_name=target_module_name,
            baselines=baseline_source_values,
        )
        if not overrides:
            return current_target(*args, **kwargs)
        with _override_scope_normalized(overrides):
            return current_target(*args, **kwargs)

    wrapper.__module__ = source_module_name
    return wrapper
