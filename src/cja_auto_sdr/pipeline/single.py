"""Single data view processing wrapper."""

from __future__ import annotations

import inspect
from functools import lru_cache
from typing import Any

from cja_auto_sdr.pipeline.models import ProcessingResult

__all__ = ["process_single_dataview"]


def _generator_module():
    from cja_auto_sdr import generator as _generator

    return _generator


@lru_cache(maxsize=1)
def _process_single_dataview_signature() -> inspect.Signature:
    generator = _generator_module()
    return inspect.signature(generator.process_single_dataview)


def process_single_dataview(*args: Any, **kwargs: Any) -> ProcessingResult:
    """Delegate to the generator implementation while preserving its call contract."""
    generator = _generator_module()
    bound_args = _process_single_dataview_signature().bind(*args, **kwargs)
    return generator.process_single_dataview(*bound_args.args, **bound_args.kwargs)
