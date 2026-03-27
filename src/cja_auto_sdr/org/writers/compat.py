"""Compatibility routing helpers for extracted org writer implementations."""

from __future__ import annotations

import importlib
from collections.abc import Callable, Iterable, Mapping
from contextlib import ExitStack, contextmanager, nullcontext
from contextvars import ContextVar
from functools import wraps
from types import MappingProxyType, ModuleType

_OVERRIDE_KEY = tuple[str, str]
_OVERRIDE_STACK = tuple[object, ...]
_OVERRIDES: ContextVar[dict[_OVERRIDE_KEY, _OVERRIDE_STACK] | None] = ContextVar(
    "org_writer_compat_overrides",
    default=None,
)
_MASKED_MODULE_ATTRS: ContextVar[dict[_OVERRIDE_KEY, int] | None] = ContextVar(
    "org_writer_compat_masked_module_attrs",
    default=None,
)
_MISSING = object()
EMPTY_OVERRIDE_MAPPING: Mapping[str, str] = MappingProxyType({})
# Legacy monkeypatch compatibility needs same-symbol delegation to reveal the
# previously bound source-layer callable without mutating the caller's patch.
_MASKED_MODULE_BASELINES: dict[_OVERRIDE_KEY, object] = {}
_MODULE_ATTR_BINDING_STACKS: dict[_OVERRIDE_KEY, list[object]] = {}
_MASKING_MODULE_TYPES: dict[type[ModuleType], type[ModuleType]] = {}


class _ProjectedSourceOverride:
    """Marker wrapper for source-scope overrides projected into target keys."""

    __slots__ = ("override", "source_attr_name", "source_module_name")

    def __init__(
        self,
        override: object,
        *,
        source_module_name: str | None = None,
        source_attr_name: str | None = None,
    ):
        self.override = override
        self.source_module_name = source_module_name
        self.source_attr_name = source_attr_name

    def __call__(self, *args, **kwargs):
        source_mask = nullcontext()
        if self.source_module_name is not None and self.source_attr_name is not None:
            source_mask = _mask_module_attrs(self.source_module_name, (self.source_attr_name,))
        with source_mask:
            return self.override(*args, **kwargs)


class _MaskedModuleAttrProxy:
    """Callable proxy that reveals one more shadowed source layer while running."""

    __slots__ = ("attr_name", "module_name", "value")

    def __init__(self, module_name: str, attr_name: str, value: object):
        self.module_name = module_name
        self.attr_name = attr_name
        self.value = value

    def __call__(self, *args, **kwargs):
        with _mask_module_attrs(self.module_name, (self.attr_name,)):
            return self.value(*args, **kwargs)

    def __getattr__(self, attr_name: str):
        return getattr(self.value, attr_name)


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


def _current_masked_module_attrs() -> dict[_OVERRIDE_KEY, int]:
    return _MASKED_MODULE_ATTRS.get() or {}


def _peek_override(
    overrides: Mapping[_OVERRIDE_KEY, _OVERRIDE_STACK],
    key: _OVERRIDE_KEY,
    default: object,
) -> object:
    stack = overrides.get(key)
    if not stack:
        return default
    return stack[-1]


def _peek_masked_module_attr(module_name: str, attr_name: str) -> object:
    key = _compat_key(module_name, attr_name)
    stack = _MODULE_ATTR_BINDING_STACKS.get(key)
    depth = _current_masked_module_attrs().get(key, 0)
    if not stack or not depth:
        return _MISSING
    effective_index = max(0, len(stack) - 1 - depth)
    masked = stack[effective_index]
    if effective_index == len(stack) - 1 or not callable(masked):
        return masked
    return _MaskedModuleAttrProxy(module_name, attr_name, masked)


def _effective_module_attr_binding(module_name: str, attr_name: str) -> object:
    key = _compat_key(module_name, attr_name)
    stack = _MODULE_ATTR_BINDING_STACKS.get(key)
    if not stack:
        module = importlib.import_module(module_name)
        return getattr(module, attr_name, _MISSING)

    depth = _current_masked_module_attrs().get(key, 0)
    return stack[max(0, len(stack) - 1 - depth)]


def _record_module_attr_binding(module_name: str, attr_name: str, value: object) -> None:
    stack = _MODULE_ATTR_BINDING_STACKS.get(_compat_key(module_name, attr_name))
    if not stack:
        return

    if stack[-1] is value:
        return

    for index in range(len(stack) - 2, -1, -1):
        if stack[index] is value:
            del stack[index + 1 :]
            return

    stack.append(value)


def _build_masking_module_type(base_cls: type[ModuleType]) -> type[ModuleType]:
    class _CompatMaskingModule(base_cls):
        def __getattribute__(self, attr_name: str):
            module_name = base_cls.__getattribute__(self, "__name__")
            masked = _peek_masked_module_attr(module_name, attr_name)
            if masked is not _MISSING:
                return masked
            return base_cls.__getattribute__(self, attr_name)

        def __setattr__(self, attr_name: str, value: object):
            module_name = base_cls.__getattribute__(self, "__name__")
            _record_module_attr_binding(module_name, attr_name, value)
            base_cls.__setattr__(self, attr_name, value)

    _CompatMaskingModule.__name__ = f"_CompatMasking{base_cls.__name__}"
    _CompatMaskingModule._cja_org_writer_compat_masking = True
    return _CompatMaskingModule


def _install_module_attr_masking(module: ModuleType) -> None:
    module_cls = module.__class__
    if getattr(module_cls, "_cja_org_writer_compat_masking", False):
        return

    masking_cls = _MASKING_MODULE_TYPES.get(module_cls)
    if masking_cls is None:
        masking_cls = _build_masking_module_type(module_cls)
        _MASKING_MODULE_TYPES[module_cls] = masking_cls
    module.__class__ = masking_cls


def _register_module_attr_baselines(module_name: str, baselines: Mapping[str, object]) -> None:
    if not baselines:
        return

    module = importlib.import_module(module_name)
    _install_module_attr_masking(module)
    for attr_name, baseline in baselines.items():
        key = _compat_key(module_name, attr_name)
        _MASKED_MODULE_BASELINES.setdefault(key, baseline)
        _MODULE_ATTR_BINDING_STACKS.setdefault(key, [baseline])


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


@contextmanager
def _suppress_overrides(target_module_name: str, attr_names: Iterable[str]):
    """Temporarily hide the active override layer for each named key."""
    unique_attr_names = tuple(dict.fromkeys(attr_names))
    if not unique_attr_names:
        yield
        return

    with ExitStack() as stack:
        for attr_name in unique_attr_names:
            stack.enter_context(_suppress_override(target_module_name, attr_name))
        yield


@contextmanager
def _mask_module_attrs(
    module_name: str,
    attr_names: Iterable[str],
):
    """Temporarily expose registered baseline module bindings for one context."""
    unique_attr_names = tuple(dict.fromkeys(attr_names))
    if not unique_attr_names:
        yield
        return

    current = _current_masked_module_attrs()
    updated = current.copy()
    applied_keys: list[_OVERRIDE_KEY] = []
    for attr_name in unique_attr_names:
        key = _compat_key(module_name, attr_name)
        if key not in _MASKED_MODULE_BASELINES:
            continue

        updated[key] = updated.get(key, 0) + 1
        applied_keys.append(key)
    if not applied_keys:
        yield
        return

    token = _MASKED_MODULE_ATTRS.set(updated)
    try:
        yield
    finally:
        _MASKED_MODULE_ATTRS.reset(token)


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
) -> tuple[dict[str, object], tuple[str, ...]]:
    """Collect override callables from a legacy compatibility module."""
    source_module = importlib.import_module(source_module_name)
    collected: dict[str, object] = {}
    legacy_attr_names: list[str] = []
    for target_attr_name, legacy_attr_name in override_mapping.items():
        if not hasattr(source_module, legacy_attr_name):
            continue

        current = _effective_module_attr_binding(source_module_name, legacy_attr_name)
        if baselines is not None and current is baselines.get(legacy_attr_name):
            continue

        collected[target_attr_name] = current
        legacy_attr_names.append(legacy_attr_name)

    return collected, tuple(legacy_attr_names)


def _collect_active_source_scope_overrides(
    source_module_name: str,
    override_mapping: Mapping[str, str],
) -> tuple[dict[str, object], tuple[str, ...]]:
    """Project active legacy source-surface overrides into canonical target keys."""
    current = _current_overrides()
    if not current:
        return {}, ()

    projected: dict[str, object] = {}
    projected_source_attrs: list[str] = []
    for target_attr_name, legacy_attr_name in override_mapping.items():
        source_key = _compat_key(source_module_name, legacy_attr_name)
        active = _peek_override(current, source_key, _MISSING)
        if active is not _MISSING:
            projected[target_attr_name] = active
            projected_source_attrs.append(legacy_attr_name)
    return projected, tuple(projected_source_attrs)


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
    target_module = importlib.import_module(target_module_name)
    baseline_source_values = {
        legacy_attr_name: getattr(source_module, legacy_attr_name)
        for legacy_attr_name in collected.values()
        if hasattr(source_module, legacy_attr_name)
    }
    _register_module_attr_baselines(source_module_name, baseline_source_values)
    baseline_target_values = {
        attr_name: getattr(target_module, attr_name)
        for attr_name in {target.__name__, *collected.keys()}
        if hasattr(target_module, attr_name)
    }
    target_attr_name = target.__name__

    @wraps(target)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> R:
        monkeypatch_overrides, _ = collect_legacy_overrides(
            source_module_name,
            collected,
            baselines=baseline_source_values,
        )
        monkeypatch_target_attrs = set(monkeypatch_overrides)
        source_scope_overrides, projected_source_attrs = _collect_active_source_scope_overrides(
            source_module_name,
            collected,
        )
        overrides = dict(monkeypatch_overrides)
        overrides.update(source_scope_overrides)
        source_override = resolve_override(source_module_name, target_attr_name, _MISSING)
        current_target = getattr(target_module, target_attr_name)
        suppressed_source_attrs = list(projected_source_attrs)

        if source_override is not _MISSING:
            suppressed_source_attrs.append(target_attr_name)
            overrides[target_attr_name] = _ProjectedSourceOverride(source_override)

        for projected_attr_name, projected_override in tuple(overrides.items()):
            baseline_target = baseline_target_values.get(projected_attr_name, _MISSING)
            current_projected_target = getattr(target_module, projected_attr_name, _MISSING)
            if baseline_target is not _MISSING and current_projected_target is not baseline_target:
                overrides.pop(projected_attr_name, None)
                continue
            if not isinstance(projected_override, _ProjectedSourceOverride):
                source_attr_name = None
                if (
                    projected_attr_name in monkeypatch_target_attrs
                    and projected_attr_name not in source_scope_overrides
                ):
                    source_attr_name = collected.get(projected_attr_name)
                overrides[projected_attr_name] = _ProjectedSourceOverride(
                    projected_override,
                    source_module_name=source_module_name if source_attr_name is not None else None,
                    source_attr_name=source_attr_name,
                )

        target_override_scope = nullcontext()
        if overrides:
            target_override_scope = _override_scope_normalized(
                _normalize_module_overrides(target_module_name, overrides),
                preserve_existing=True,
            )

        target_self_suppression = nullcontext()
        if isinstance(
            resolve_override(target_module_name, target_attr_name, _MISSING),
            _ProjectedSourceOverride,
        ):
            target_self_suppression = _suppress_override(target_module_name, target_attr_name)

        with (
            _suppress_overrides(source_module_name, suppressed_source_attrs),
            target_self_suppression,
            target_override_scope,
        ):
            active_target = resolve_override(target_module_name, target_attr_name, current_target)
            return active_target(*args, **kwargs)

    wrapper.__module__ = source_module_name
    return wrapper
