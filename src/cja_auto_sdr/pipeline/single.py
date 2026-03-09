"""Single data view processing wrapper."""

from __future__ import annotations

from typing import Any

from cja_auto_sdr.pipeline.models import ProcessingConfig, ProcessingResult

__all__ = ["process_single_dataview"]


def _generator_module():
    from cja_auto_sdr import generator as _generator

    return _generator


def process_single_dataview(
    data_view_id: str,
    *,
    config_file: str = "config.json",
    output_dir: str = ".",
    log_level: str = "INFO",
    log_format: str = "text",
    output_format: str = "excel",
    enable_cache: bool = False,
    cache_size: int = 1000,
    cache_ttl: int = 3600,
    quiet: bool = False,
    skip_validation: bool = False,
    max_issues: int = 0,
    clear_cache: bool = False,
    show_timings: bool = False,
    metrics_only: bool = False,
    dimensions_only: bool = False,
    profile: str | None = None,
    shared_cache: Any = None,
    api_tuning_config: Any = None,
    circuit_breaker_config: Any = None,
    include_derived_inventory: bool = False,
    include_calculated_metrics: bool = False,
    include_segments_inventory: bool = False,
    inventory_only: bool = False,
    inventory_order: list[str] | None = None,
    quality_report_only: bool = False,
    allow_partial: bool = False,
    production_mode: bool = False,
    batch_id: str | None = None,
    processing_config: ProcessingConfig | None = None,
) -> ProcessingResult:
    """Delegate to the generator implementation with a preserved call signature."""
    generator = _generator_module()

    return generator.process_single_dataview(
        data_view_id,
        config_file=config_file,
        output_dir=output_dir,
        log_level=log_level,
        log_format=log_format,
        output_format=output_format,
        enable_cache=enable_cache,
        cache_size=cache_size,
        cache_ttl=cache_ttl,
        quiet=quiet,
        skip_validation=skip_validation,
        max_issues=max_issues,
        clear_cache=clear_cache,
        show_timings=show_timings,
        metrics_only=metrics_only,
        dimensions_only=dimensions_only,
        profile=profile,
        shared_cache=shared_cache,
        api_tuning_config=api_tuning_config,
        circuit_breaker_config=circuit_breaker_config,
        include_derived_inventory=include_derived_inventory,
        include_calculated_metrics=include_calculated_metrics,
        include_segments_inventory=include_segments_inventory,
        inventory_only=inventory_only,
        inventory_order=inventory_order,
        quality_report_only=quality_report_only,
        allow_partial=allow_partial,
        production_mode=production_mode,
        batch_id=batch_id,
        processing_config=processing_config,
    )
