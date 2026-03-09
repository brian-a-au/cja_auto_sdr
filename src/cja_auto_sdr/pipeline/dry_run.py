"""Dry-run wrapper."""

from __future__ import annotations

import logging

__all__ = ["run_dry_run"]


def _generator_module():
    from cja_auto_sdr import generator as _generator

    return _generator


def run_dry_run(data_views: list[str], config_file: str, logger: logging.Logger, profile: str | None = None) -> bool:
    """Delegate dry-run validation to the generator implementation."""
    return _generator_module().run_dry_run(data_views, config_file, logger, profile=profile)
