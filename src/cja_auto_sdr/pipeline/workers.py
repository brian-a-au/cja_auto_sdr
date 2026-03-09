"""Worker functions for multiprocessing SDR execution."""

from __future__ import annotations

from cja_auto_sdr.pipeline.models import ProcessingConfig, ProcessingResult, WorkerArgs

__all__ = ["process_single_dataview_worker"]


def _generator_module():
    from cja_auto_sdr import generator as _generator

    return _generator


def process_single_dataview_worker(args: WorkerArgs) -> ProcessingResult:
    """Process a single data view from a multiprocessing worker."""
    generator = _generator_module()

    return generator.process_single_dataview(
        args.data_view_id,
        processing_config=ProcessingConfig(
            config_file=args.config_file,
            output_dir=args.output_dir,
            log_level=args.log_level,
            log_format=args.log_format,
            output_format=args.output_format,
            enable_cache=args.enable_cache,
            cache_size=args.cache_size,
            cache_ttl=args.cache_ttl,
            quiet=args.quiet,
            skip_validation=args.skip_validation,
            max_issues=args.max_issues,
            clear_cache=args.clear_cache,
            show_timings=args.show_timings,
            metrics_only=args.metrics_only,
            dimensions_only=args.dimensions_only,
            profile=args.profile,
            shared_cache=args.shared_cache,
            api_tuning_config=args.api_tuning_config,
            circuit_breaker_config=args.circuit_breaker_config,
            include_derived_inventory=args.include_derived_inventory,
            include_calculated_metrics=args.include_calculated_metrics,
            include_segments_inventory=args.include_segments_inventory,
            inventory_only=args.inventory_only,
            inventory_order=args.inventory_order,
            quality_report_only=args.quality_report_only,
            allow_partial=args.allow_partial,
            production_mode=args.production_mode,
            batch_id=args.batch_id,
        ),
    )
