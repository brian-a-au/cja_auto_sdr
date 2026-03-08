"""Excel formatting helpers (implementation in output/sdr/)."""

__all__ = ["ExcelFormatCache", "apply_excel_formatting"]

from cja_auto_sdr.core.lazy import make_getattr

__getattr__ = make_getattr(__name__, __all__, target_module="cja_auto_sdr.output.sdr")
