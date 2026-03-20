"""Shared mode-scoped CLI option metadata.

This module stays lightweight so both standalone fast-path code and generator
validation can share one declarative definition of mode-scoped options.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

_ModeScopedValueErrorFactory = Callable[[Any], str | None]


@dataclass(frozen=True)
class ModeScopedOptionSpec:
    """Declarative metadata for one mode-scoped CLI option."""

    option_name: str
    dest: str
    default: Any
    mode_error: str | None = None
    value_errors: tuple[_ModeScopedValueErrorFactory, ...] = field(default_factory=tuple)

    def is_configured(self, args: object, *, option_specified: Callable[[str], bool]) -> bool:
        """Return True when the option is explicitly configured for the current argv."""
        if option_specified(self.option_name):
            return True

        current_value = getattr(args, self.dest, self.default)
        if isinstance(self.default, bool):
            return bool(current_value) is not self.default
        return current_value != self.default

    def resolve_value_errors(self, args: object) -> tuple[str | None, ...]:
        """Return any configured value-error messages for the current args."""
        current_value = getattr(args, self.dest, None)
        return tuple(factory(current_value) for factory in self.value_errors)


def _min_int_error(minimum: int, message: str) -> _ModeScopedValueErrorFactory:
    """Return a validator that enforces a minimum integer value when configured."""

    def _validator(value: Any) -> str | None:
        if value is None:
            return None
        return message if value < minimum else None

    return _validator


ORG_REPORT_MODE_SCOPED_OPTION_SPECS: tuple[ModeScopedOptionSpec, ...] = (
    ModeScopedOptionSpec("--core-threshold", "core_threshold", 0.5),
    ModeScopedOptionSpec("--core-min-count", "core_min_count", None),
    ModeScopedOptionSpec("--overlap-threshold", "overlap_threshold", 0.8),
    ModeScopedOptionSpec("--skip-similarity", "skip_similarity", False),
    ModeScopedOptionSpec("--similarity-max-dvs", "org_similarity_max_dvs", 250),
    ModeScopedOptionSpec("--force-similarity", "org_force_similarity", False),
    ModeScopedOptionSpec("--include-names", "org_include_names", False),
    ModeScopedOptionSpec("--org-summary", "org_summary", False),
    ModeScopedOptionSpec("--org-verbose", "org_verbose", False),
    ModeScopedOptionSpec("--no-component-types", "no_component_types", False),
    ModeScopedOptionSpec("--include-metadata", "org_include_metadata", False),
    ModeScopedOptionSpec("--include-drift", "org_include_drift", False),
    ModeScopedOptionSpec("--org-shared-client", "org_shared_client", False),
    ModeScopedOptionSpec(
        "--sample",
        "org_sample_size",
        None,
        value_errors=(_min_int_error(1, "--sample must be at least 1"),),
    ),
    ModeScopedOptionSpec("--sample-seed", "org_sample_seed", None),
    ModeScopedOptionSpec("--sample-stratified", "org_sample_stratified", False),
    ModeScopedOptionSpec("--use-cache", "org_use_cache", False),
    ModeScopedOptionSpec("--cache-max-age", "org_cache_max_age", 24),
    ModeScopedOptionSpec("--refresh-cache", "org_clear_cache", False),
    ModeScopedOptionSpec("--validate-cache", "org_validate_cache", False),
    ModeScopedOptionSpec("--memory-warning", "org_memory_warning", 100),
    ModeScopedOptionSpec("--memory-limit", "org_memory_limit", None),
    ModeScopedOptionSpec("--cluster", "org_cluster", False),
    ModeScopedOptionSpec("--cluster-method", "org_cluster_method", "average"),
    ModeScopedOptionSpec("--duplicate-threshold", "org_duplicate_threshold", None),
    ModeScopedOptionSpec("--isolated-threshold", "org_isolated_threshold", None),
    ModeScopedOptionSpec("--fail-on-threshold", "org_fail_on_threshold", False),
    ModeScopedOptionSpec("--org-stats", "org_stats_only", False),
    ModeScopedOptionSpec("--audit-naming", "org_audit_naming", False),
    ModeScopedOptionSpec("--compare-org-report", "org_compare_report", None),
    ModeScopedOptionSpec(
        "--trending-window",
        "trending_window",
        None,
        mode_error="--trending-window is only supported with --org-report",
        value_errors=(_min_int_error(2, "--trending-window must be >= 2"),),
    ),
    ModeScopedOptionSpec("--owner-summary", "org_owner_summary", False),
    ModeScopedOptionSpec("--flag-stale", "org_flag_stale", False),
    ModeScopedOptionSpec(
        "--lock-stale-threshold",
        "org_lock_stale_threshold",
        3600,
        mode_error="--lock-stale-threshold is only valid with --org-report",
        value_errors=(_min_int_error(1, "--lock-stale-threshold must be greater than 0"),),
    ),
)


def org_report_mode_scoped_option_specs() -> tuple[ModeScopedOptionSpec, ...]:
    """Return the declarative org-report-only option specs."""
    return ORG_REPORT_MODE_SCOPED_OPTION_SPECS


def org_report_mode_scoped_dests() -> frozenset[str]:
    """Return argparse dest names that are valid only for org-report mode."""
    return frozenset(spec.dest for spec in ORG_REPORT_MODE_SCOPED_OPTION_SPECS)


def org_report_mode_scoped_option_names() -> tuple[str, ...]:
    """Return CLI option strings that are valid only for org-report mode."""
    return tuple(spec.option_name for spec in ORG_REPORT_MODE_SCOPED_OPTION_SPECS)
