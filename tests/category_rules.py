"""Shared test-category rules for pytest auto-marking and reporting."""

from __future__ import annotations

_INTEGRATION_TEST_FILES = frozenset(
    {
        "test_git_integration.py",
        "test_org_report_integration.py",
        "test_trending_integration.py",
    },
)
_E2E_TEST_FILES = frozenset(
    {
        "test_cli_color_policy_e2e.py",
        "test_e2e_integration.py",
    },
)
_SMOKE_TEST_FILES = frozenset({"test_cli_smoke_modes.py"})
_SLOW_TEST_FILES = frozenset({"test_perf.py"})

PRIMARY_TEST_MARKERS = ("unit", "integration", "e2e", "smoke")
ALL_TEST_MARKERS = (*PRIMARY_TEST_MARKERS, "slow")


def file_scoped_test_markers(module_name: str) -> tuple[str, ...]:
    """Return explicit file-level markers for a collected test module."""
    markers: list[str] = []
    if module_name in _INTEGRATION_TEST_FILES:
        markers.append("integration")
    if module_name in _E2E_TEST_FILES:
        markers.append("e2e")
    if module_name in _SMOKE_TEST_FILES:
        markers.append("smoke")
    if module_name in _SLOW_TEST_FILES:
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
