"""Output writer protocol (current implementation lives in generator for compatibility)."""

from __future__ import annotations

__all__ = ["OutputWriter"]

from cja_auto_sdr.core.lazy import make_getattr

__getattr__ = make_getattr(__name__, __all__, target_module="cja_auto_sdr.generator")
