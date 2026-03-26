"""Compatibility routing helpers for extracted org writer implementations."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Collection, Mapping
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
_SUPPRESSED_COMPAT_TARGETS: ContextVar[set[_OVERRIDE_KEY] | None] = ContextVar(
    "org_writer_suppressed_compat_targets",
    default=None,
)
_MISSING = object()
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
    "TRENDING_HELPER_OVERRIDE_MAPPING",
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
_TRENDING_PACKAGE_ROOT_HELPERS = (
    "_build_trending_metric_rows",
    "_escape_markdown_table_cell",
    "_format_signed_trending_value",
    "_format_trending_dv_label",
    "_format_trending_period_label",
    "_format_trending_timestamp_short",
    "_print_trending_console_section",
    "_ranked_drift_entries",
    "_render_console_trending_table",
    "_render_html_trending_table",
    "_render_markdown_trending_table",
    "_render_trending_console",
    "_render_trending_html",
    "_render_trending_markdown",
    "_resolve_trending_dv_name",
    "_sorted_drift_score_items",
    "_stringify_trending_value",
    "_top_drift_scores",
    "_trending_date_range",
    "_trending_delta_column_specs",
    "_trending_delta_csv_rows",
    "_trending_delta_metric_rows",
    "_trending_matrix_rows",
    "_trending_snapshot_column_specs",
    "_trending_snapshot_csv_rows",
    "_trending_snapshot_metric_rows",
    "_trending_snapshots_to_dicts",
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


def _validate_override_destination(
    destination: _OVERRIDE_DESTINATION,
    *,
    tuple_error_message: str = "override_mapping tuple keys must be (target_module_name, attr_name) string pairs",
    key_error_message: str = "override_mapping keys must be strings or (module, attr) tuples",
) -> None:
    """Validate a public override destination key before collection or normalization."""
    if isinstance(destination, str):
        return
    if isinstance(destination, tuple):
        if len(destination) != 2 or not all(isinstance(part, str) for part in destination):
            raise TypeError(tuple_error_message)
        return
    raise TypeError(key_error_message)


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
TRENDING_HELPER_OVERRIDE_MAPPING = freeze_override_mapping(
    {helper_name: helper_name for helper_name in _TRENDING_PACKAGE_ROOT_HELPERS},
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


def _current_suppressed_compat_targets() -> set[_OVERRIDE_KEY]:
    return _SUPPRESSED_COMPAT_TARGETS.get() or set()


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
        if active is default:
            return default(*args, **kwargs)
        with _suppress_override(target_module_name, attr_name):
            return active(*args, **kwargs)

    proxy.__module__ = target_module_name
    return proxy


def _collect_source_overrides[K](
    source_module_name: str,
    override_mapping: Mapping[K, str],
    *,
    baselines: Mapping[str, object] | None = None,
    always_include_legacy_attrs: Collection[str] = (),
) -> dict[K, object]:
    """Collect override objects from a source module for a pre-shaped mapping."""
    source_module = importlib.import_module(source_module_name)
    collected: dict[K, object] = {}
    for target_key, legacy_attr_name in override_mapping.items():
        if not hasattr(source_module, legacy_attr_name):
            continue
        override = getattr(source_module, legacy_attr_name)
        if legacy_attr_name in always_include_legacy_attrs:
            collected[target_key] = override
            continue
        if baselines is not None and override is baselines.get(legacy_attr_name):
            continue
        collected[target_key] = override
    return collected


def _collect_active_source_scope_overrides[K](
    source_module_name: str,
    override_mapping: Mapping[K, str],
) -> dict[K, object]:
    """Project active source-surface override_scope entries into a target mapping."""
    current = _current_overrides()
    if not current:
        return {}

    projected: dict[K, object] = {}
    for target_key, legacy_attr_name in override_mapping.items():
        source_key = _compat_key(source_module_name, legacy_attr_name)
        if source_key in current:
            projected[target_key] = current[source_key]
    return projected


def _collect_normalized_legacy_overrides(
    source_module_name: str,
    override_mapping: Mapping[_OVERRIDE_DESTINATION, str],
    *,
    default_target_module_name: str,
    baselines: Mapping[str, object] | None = None,
    always_include_legacy_attrs: Collection[str] = (),
) -> dict[_OVERRIDE_KEY, object]:
    """Collect normalized tuple-key overrides for internal compat wrapper routing."""
    return _collect_source_overrides(
        source_module_name,
        _normalize_override_mapping(
            override_mapping,
            default_target_module_name=default_target_module_name,
        ),
        baselines=baselines,
        always_include_legacy_attrs=always_include_legacy_attrs,
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
def _override_scope_normalized(
    overrides: Mapping[_OVERRIDE_KEY, object],
    *,
    preserve_existing: bool = False,
):
    """Apply normalized tuple-key overrides to the current execution context."""
    current = _current_overrides()
    updated = current.copy()
    if preserve_existing:
        for key, override in overrides.items():
            updated.setdefault(key, override)
    else:
        updated.update(overrides)
    token = _OVERRIDES.set(updated)
    try:
        yield
    finally:
        _OVERRIDES.reset(token)


@contextmanager
def _suppress_override(target_module_name: str, attr_name: str):
    """Temporarily mask one override key while preserving the rest of the current context."""
    key = _compat_key(target_module_name, attr_name)
    current = _current_overrides()
    if key not in current:
        yield
        return

    updated = current.copy()
    updated.pop(key, None)
    token = _OVERRIDES.set(updated)
    try:
        yield
    finally:
        _OVERRIDES.reset(token)


def _is_compat_target_suppressed(source_module_name: str, attr_name: str) -> bool:
    return _compat_key(source_module_name, attr_name) in _current_suppressed_compat_targets()


@contextmanager
def _suppress_compat_target(source_module_name: str, attr_name: str):
    """Temporarily force one compat wrapper to call its baseline target on re-entry."""
    key = _compat_key(source_module_name, attr_name)
    current = _current_suppressed_compat_targets()
    if key in current:
        yield
        return

    updated = current.copy()
    updated.add(key)
    token = _SUPPRESSED_COMPAT_TARGETS.set(updated)
    try:
        yield
    finally:
        _SUPPRESSED_COMPAT_TARGETS.reset(token)


def _routes_to_compat_wrapper(
    candidate: object,
    reference: object,
    *,
    seen: set[int] | None = None,
) -> bool:
    """Return True when a callable eventually delegates back into one compat wrapper."""
    if candidate is reference:
        return True

    if seen is None:
        seen = set()
    candidate_id = id(candidate)
    if candidate_id in seen:
        return False
    seen.add(candidate_id)

    for attr_name in ("_mock_wraps", "__wrapped__"):
        wrapped = getattr(candidate, attr_name, _MISSING)
        if wrapped is _MISSING:
            continue
        if _routes_to_compat_wrapper(wrapped, reference, seen=seen):
            return True
    return False


def _resolve_scoped_self_target(
    current_scoped_overrides: Mapping[_OVERRIDE_KEY, object],
    *,
    target_self_key: _OVERRIDE_KEY,
    source_self_key: _OVERRIDE_KEY,
) -> object:
    """Prefer explicit self overrides and let the recursion guard handle safe re-entry."""
    if target_self_key in current_scoped_overrides:
        return current_scoped_overrides[target_self_key]
    if source_self_key in current_scoped_overrides:
        return current_scoped_overrides[source_self_key]
    return _MISSING


def _resolve_suppressed_compat_target(
    *,
    target_module_name: str,
    target_attr_name: str,
    default_target: object,
    reference: object,
) -> object:
    """Prefer the live canonical target unless it still routes back into the compat wrapper."""
    live_target = getattr(importlib.import_module(target_module_name), target_attr_name)
    if _routes_to_compat_wrapper(live_target, reference):
        return default_target
    return live_target


@contextmanager
def override_scope(
    target_module_name: str,
    overrides: Mapping[_OVERRIDE_DESTINATION, object],
):
    """Apply compatibility overrides to the current execution context only.

    String keys are scoped to ``target_module_name`` for the legacy 3.4.7
    flat override contract. Explicit ``(module, attr)`` tuple keys are also
    accepted so callers can apply mixed-key mappings collected from the
    exported 3.4.8 writer override maps without re-normalizing them.
    """
    normalized_overrides: dict[_OVERRIDE_KEY, object] = {}
    for destination, override in overrides.items():
        _validate_override_destination(
            destination,
            tuple_error_message="override_scope() tuple override keys must be (target_module_name, attr_name) string pairs",
            key_error_message="override_scope() override keys must be strings or (target_module_name, attr_name) tuples",
        )
        if isinstance(destination, str):
            normalized_overrides[_compat_key(target_module_name, destination)] = override
            continue
        normalized_overrides[destination] = override
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
    return _make_compat_wrapper_with_options(
        source_module_name,
        target,
        target_module_name=target_module_name,
        override_mapping=override_mapping,
    )


def _make_compat_wrapper_with_options[**P, R](
    source_module_name: str,
    target: Callable[P, R],
    *,
    target_module_name: str,
    override_mapping: Mapping[_OVERRIDE_DESTINATION, str],
    baselines: Mapping[str, object] | None = None,
    exclude_self_override: bool = False,
    always_include_legacy_attrs: Collection[str] = (),
) -> Callable[P, R]:
    """Internal helper for batched wrapper installs that need shared baselines or self-exclusion."""
    collected = dict(
        _normalize_override_mapping(
            override_mapping,
            default_target_module_name=target_module_name,
        )
    )
    source_module = importlib.import_module(source_module_name)
    baseline_source_values = (
        baselines
        if baselines is not None
        else {
            legacy_attr_name: getattr(source_module, legacy_attr_name)
            for legacy_attr_name in collected.values()
            if hasattr(source_module, legacy_attr_name)
        }
    )
    target_attr_name = target.__name__
    source_self_key = _compat_key(source_module_name, target_attr_name)
    target_self_key = _compat_key(target_module_name, target_attr_name)
    self_override_key = _compat_key(target_module_name, target_attr_name)

    @wraps(target)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        current_scoped_overrides = _current_overrides()
        if _is_compat_target_suppressed(source_module_name, target_attr_name):
            current_target = _resolve_suppressed_compat_target(
                target_module_name=target_module_name,
                target_attr_name=target_attr_name,
                default_target=target,
                reference=wrapper,
            )
        else:
            current_target = _resolve_scoped_self_target(
                current_scoped_overrides,
                target_self_key=target_self_key,
                source_self_key=source_self_key,
            )
            if current_target is _MISSING:
                current_target = getattr(importlib.import_module(target_module_name), target_attr_name)
        monkeypatch_overrides = _collect_normalized_legacy_overrides(
            source_module_name,
            collected,
            default_target_module_name=target_module_name,
            baselines=baseline_source_values,
            always_include_legacy_attrs=always_include_legacy_attrs,
        )
        overrides = monkeypatch_overrides
        overrides.update(_collect_active_source_scope_overrides(source_module_name, collected))
        if exclude_self_override:
            overrides.pop(self_override_key, None)

        if _routes_to_compat_wrapper(current_target, wrapper):
            with _suppress_compat_target(source_module_name, target_attr_name):
                if not overrides:
                    return current_target(*args, **kwargs)
                with _override_scope_normalized(overrides, preserve_existing=True):
                    return current_target(*args, **kwargs)

        if not overrides:
            return current_target(*args, **kwargs)
        with _override_scope_normalized(overrides, preserve_existing=True):
            return current_target(*args, **kwargs)

    wrapper.__module__ = source_module_name
    return wrapper
