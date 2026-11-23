"""List data views without losing any to cjapy's first-page-only paging.

This module imports only the standard library and ``core.constants`` so that any
caller can use it without joining the ``api.client`` import cycle.
"""

from __future__ import annotations

import logging
from typing import Any

from cja_auto_sdr.core.constants import DATA_VIEW_LIST_LIMIT

_module_logger = logging.getLogger(__name__)


def list_data_views(cja: Any, logger: logging.Logger | None = None) -> Any:
    """Return ``cja.getDataViews()`` with every data view on one page.

    cjapy 0.3.2 and earlier read a ``last`` key that the data views endpoint does
    not send, so they return only the first page (pitchmuc/cjapy#34). With the
    default limit of 100, an org with more data views silently loses the rest.
    Asking for ``DATA_VIEW_LIST_LIMIT`` rows keeps every data view on one page.

    The payload is returned unchanged, so callers keep their own normalization
    and error handling. When the listing fills the whole page, a warning says
    that data views may be missing.
    """
    payload = cja.getDataViews(limit=DATA_VIEW_LIST_LIMIT)
    is_listing = type(payload).__name__ == "DataFrame" or isinstance(payload, (list, tuple))
    if is_listing and len(payload) >= DATA_VIEW_LIST_LIMIT:
        (logger or _module_logger).warning(
            "The data view listing returned %d data views, the most one page holds. "
            "Data views beyond the first %d may be missing.",
            len(payload),
            DATA_VIEW_LIST_LIMIT,
        )
    return payload
