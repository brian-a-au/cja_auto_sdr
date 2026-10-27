"""Data module - Data structures and comparison logic.

This module provides future-facing imports for the modular structure.
Currently, all symbols should be imported from cja_auto_sdr.generator
to avoid circular import issues.

Example usage:
    # Current (use this)
    from cja_auto_sdr.generator import ProcessingResult, DiffSummary

    # Future (when extraction is complete)
    from cja_auto_sdr.data import ProcessingResult, DiffSummary
"""

from __future__ import annotations

# Deferred imports to avoid circular import with generator.py
# Will be populated when code is fully extracted
from cja_auto_sdr.core.lazy import make_getattr

__all__: list[str] = []

_LAZY_EXPORTS = [
    "ProcessingResult",
    "DiffSummary",
]

__getattr__ = make_getattr(__name__, _LAZY_EXPORTS, target_module="cja_auto_sdr.generator")
