"""Inventory summary mode (canonical implementation in output.inventory)."""

__all__ = ["display_inventory_summary"]

from cja_auto_sdr.core.lazy import make_getattr

__getattr__ = make_getattr(__name__, __all__, target_module="cja_auto_sdr.output.inventory")
