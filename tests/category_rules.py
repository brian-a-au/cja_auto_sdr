"""Shared test-category rules for pytest auto-marking and reporting."""

from __future__ import annotations

from pathlib import Path

PRIMARY_TEST_MARKERS = ("unit", "integration", "e2e", "smoke")
ALL_TEST_MARKERS = (*PRIMARY_TEST_MARKERS, "slow")


def _module_name_tokens(module_name: str) -> frozenset[str]:
    return frozenset(token for token in Path(module_name).stem.split("_") if token)


def file_scoped_test_markers(module_name: str) -> tuple[str, ...]:
    """Return file-level markers inferred from stable test-module naming."""
    tokens = _module_name_tokens(module_name)
    markers: list[str] = []

    if "e2e" in tokens:
        markers.append("e2e")
    elif "smoke" in tokens:
        markers.append("smoke")
    elif "integration" in tokens:
        markers.append("integration")

    if "slow" in tokens or "perf" in tokens:
        markers.append("slow")

    return tuple(markers)


def auto_test_markers_for_file(module_name: str) -> tuple[str, ...]:
    """Return the effective auto-applied markers for one test module."""
    markers = list(file_scoped_test_markers(module_name))
    if not any(marker in PRIMARY_TEST_MARKERS for marker in markers):
        markers.insert(0, "unit")
    return tuple(markers)


def primary_test_category_for_file(module_name: str) -> str:
    """Return the primary mutually-exclusive test category for one module."""
    for marker in auto_test_markers_for_file(module_name):
        if marker in PRIMARY_TEST_MARKERS:
            return marker
    return "unit"
