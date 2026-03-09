"""Batch processing orchestration for SDR execution."""

# ruff: noqa: T201

from __future__ import annotations

import time
import uuid
from pathlib import Path
from typing import Any

from cja_auto_sdr.core.config import APITuningConfig, CircuitBreakerConfig
from cja_auto_sdr.pipeline.models import BatchConfig

__all__ = ["BatchProcessor"]


def _generator_module():
    from cja_auto_sdr import generator as _generator

    return _generator


class BatchProcessor:
    """
    Process multiple data views in parallel using multiprocessing.

    This implementation continues to route runtime dependencies through
    ``cja_auto_sdr.generator`` so generator-targeted patches remain valid.
    """

    def __init__(
        self,
        config_file: str = "config.json",
        output_dir: str = ".",
        workers: int = 4,
        continue_on_error: bool = False,
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
        shared_cache: bool = False,
        api_tuning_config: APITuningConfig | None = None,
        circuit_breaker_config: CircuitBreakerConfig | None = None,
        include_derived_inventory: bool = False,
        include_calculated_metrics: bool = False,
        include_segments_inventory: bool = False,
        inventory_only: bool = False,
        inventory_order: list[str] | None = None,
        quality_report_only: bool = False,
        allow_partial: bool = False,
        production_mode: bool = False,
        batch_config: BatchConfig | None = None,
    ):
        generator = _generator_module()

        if batch_config is None:
            batch_config = BatchConfig(
                config_file=config_file,
                output_dir=output_dir,
                workers=workers,
                continue_on_error=continue_on_error,
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
            )

        self.config_file = batch_config.config_file
        self.output_dir = batch_config.output_dir
        self.clear_cache = batch_config.clear_cache
        self.show_timings = batch_config.show_timings
        self.metrics_only = batch_config.metrics_only
        self.dimensions_only = batch_config.dimensions_only
        self.workers = batch_config.workers
        self.continue_on_error = batch_config.continue_on_error
        self.log_level = batch_config.log_level
        self.log_format = batch_config.log_format
        self.output_format = batch_config.output_format
        self.enable_cache = batch_config.enable_cache
        self.cache_size = batch_config.cache_size
        self.cache_ttl = batch_config.cache_ttl
        self.quiet = batch_config.quiet
        self.skip_validation = batch_config.skip_validation
        self.max_issues = batch_config.max_issues
        self.profile = batch_config.profile
        self.shared_cache_enabled = batch_config.shared_cache
        self.api_tuning_config = batch_config.api_tuning_config
        self.circuit_breaker_config = batch_config.circuit_breaker_config
        self.include_derived_inventory = batch_config.include_derived_inventory
        self.include_calculated_metrics = batch_config.include_calculated_metrics
        self.include_segments_inventory = batch_config.include_segments_inventory
        self.inventory_only = batch_config.inventory_only
        self.inventory_order = batch_config.inventory_order
        self.quality_report_only = batch_config.quality_report_only
        self.allow_partial = batch_config.allow_partial
        self.production_mode = batch_config.production_mode
        self.batch_id = str(uuid.uuid4())[:8]
        base_logger = generator.setup_logging(batch_mode=True, log_level=self.log_level, log_format=self.log_format)
        self.logger = generator.with_log_context(base_logger, run_mode="batch", batch_id=self.batch_id)
        self.logger.info(f"Batch ID: {self.batch_id}")

        self._shared_cache = None
        if self.shared_cache_enabled and self.enable_cache and not self.skip_validation:
            self._shared_cache = generator.SharedValidationCache(max_size=self.cache_size, ttl_seconds=self.cache_ttl)
            self.logger.info(f"[{self.batch_id}] Shared validation cache enabled (max_size={self.cache_size})")

        try:
            Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        except PermissionError as e:
            raise generator.OutputError(
                f"Permission denied creating output directory: {self.output_dir}. "
                "Check that you have write permissions for the parent directory.",
            ) from e
        except OSError as e:
            raise generator.OutputError(
                f"Cannot create output directory '{self.output_dir}': {e}. "
                "Verify the path is valid and the disk has available space.",
            ) from e

    def process_batch(self, data_view_ids: list[str]) -> dict[str, Any]:
        """Process multiple data views in parallel."""
        generator = _generator_module()

        self.logger.info("=" * generator.BANNER_WIDTH)
        self.logger.info(f"[{self.batch_id}] BATCH PROCESSING START")
        self.logger.info("=" * generator.BANNER_WIDTH)
        self.logger.info(f"[{self.batch_id}] Data views to process: {len(data_view_ids)}")
        self.logger.info(f"[{self.batch_id}] Parallel workers: {self.workers}")
        self.logger.info(f"[{self.batch_id}] Continue on error: {self.continue_on_error}")
        self.logger.info(f"[{self.batch_id}] Output directory: {self.output_dir}")
        self.logger.info(f"[{self.batch_id}] Output format: {self.output_format}")
        self.logger.info("=" * generator.BANNER_WIDTH)

        batch_start_time = time.time()
        results = {"successful": [], "failed": [], "total": len(data_view_ids), "total_duration": 0}

        worker_args = [
            generator.WorkerArgs(
                data_view_id=dv_id,
                config_file=self.config_file,
                output_dir=self.output_dir,
                log_level=self.log_level,
                log_format=self.log_format,
                output_format=self.output_format,
                enable_cache=self.enable_cache,
                cache_size=self.cache_size,
                cache_ttl=self.cache_ttl,
                quiet=self.quiet,
                skip_validation=self.skip_validation,
                max_issues=self.max_issues,
                clear_cache=self.clear_cache,
                show_timings=self.show_timings,
                metrics_only=self.metrics_only,
                dimensions_only=self.dimensions_only,
                profile=self.profile,
                shared_cache=self._shared_cache,
                api_tuning_config=self.api_tuning_config,
                circuit_breaker_config=self.circuit_breaker_config,
                include_derived_inventory=self.include_derived_inventory,
                include_calculated_metrics=self.include_calculated_metrics,
                include_segments_inventory=self.include_segments_inventory,
                inventory_only=self.inventory_only,
                inventory_order=self.inventory_order,
                quality_report_only=self.quality_report_only,
                allow_partial=self.allow_partial,
                production_mode=self.production_mode,
                batch_id=self.batch_id,
            )
            for dv_id in data_view_ids
        ]

        try:
            with generator.ProcessPoolExecutor(max_workers=self.workers) as executor:
                future_to_dv = {
                    executor.submit(generator.process_single_dataview_worker, wa): wa.data_view_id for wa in worker_args
                }

                with generator.tqdm(
                    total=len(data_view_ids),
                    desc="Processing data views",
                    unit="view",
                    bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} [{elapsed}<{remaining}, {rate_fmt}]",
                    disable=self.quiet,
                ) as pbar:
                    for future in generator.as_completed(future_to_dv):
                        dv_id = future_to_dv[future]
                        try:
                            result = future.result()

                            if result.success:
                                results["successful"].append(result)
                                pbar.set_postfix_str(f"✓ {dv_id[:20]}", refresh=True)
                                self.logger.info(f"[{self.batch_id}] ✓ {dv_id}: SUCCESS ({result.duration:.1f}s)")
                            else:
                                results["failed"].append(result)
                                pbar.set_postfix_str(f"✗ {dv_id[:20]}", refresh=True)
                                self.logger.error(f"[{self.batch_id}] ✗ {dv_id}: FAILED - {result.error_message}")

                                if not self.continue_on_error:
                                    self.logger.warning(
                                        f"[{self.batch_id}] Stopping batch processing due to error (use --continue-on-error to continue)",
                                    )
                                    for pending in future_to_dv:
                                        pending.cancel()
                                    break

                        except KeyboardInterrupt, SystemExit:
                            self.logger.warning(f"[{self.batch_id}] Interrupted - cancelling remaining tasks...")
                            for pending in future_to_dv:
                                pending.cancel()
                            raise
                        except Exception as e:  # Intentional: batch worker resilience boundary
                            is_expected = isinstance(e, generator.RECOVERABLE_BATCH_WORKER_EXCEPTIONS)
                            prefix = "EXCEPTION" if is_expected else "UNEXPECTED EXCEPTION"
                            self.logger.error(f"[{self.batch_id}] ✗ {dv_id}: {prefix} - {e!s}")
                            if not is_expected:
                                self.logger.debug("Unexpected batch worker error", exc_info=True)
                            results["failed"].append(
                                generator.ProcessingResult(
                                    data_view_id=dv_id,
                                    data_view_name="Unknown",
                                    success=False,
                                    duration=0,
                                    error_message=str(e),
                                    failure_code=generator.FAILURE_CODE_BATCH_WORKER_EXCEPTION,
                                    failure_reason=f"batch_worker_exception:{type(e).__name__}",
                                ),
                            )

                            if not self.continue_on_error:
                                self.logger.warning(f"[{self.batch_id}] Stopping batch processing due to error")
                                for pending in future_to_dv:
                                    pending.cancel()
                                break

                        pbar.update(1)
        finally:
            if self._shared_cache is not None:
                cache_stats = self._shared_cache.get_statistics()
                self.logger.info(
                    f"[{self.batch_id}] Shared cache stats: {cache_stats['hits']} hits, "
                    f"{cache_stats['misses']} misses ({cache_stats['hit_rate']:.1f}% hit rate)",
                )
                self._shared_cache.shutdown()
                self._shared_cache = None

        results["total_duration"] = time.time() - batch_start_time
        self.print_summary(results)
        return results

    def print_summary(self, results: dict[str, Any]) -> None:
        """Print detailed batch processing summary with color-coded output."""
        generator = _generator_module()

        total = results["total"]
        successful_count = len(results["successful"])
        failed_count = len(results["failed"])
        success_rate = (successful_count / total * 100) if total > 0 else 0
        total_duration = results["total_duration"]
        avg_duration = (total_duration / total) if total > 0 else 0
        total_file_size = sum(r.file_size_bytes for r in results["successful"])
        total_size_formatted = generator.format_file_size(total_file_size)

        self.logger.info("")
        self.logger.info("=" * generator.BANNER_WIDTH)
        self.logger.info(f"[{self.batch_id}] BATCH PROCESSING SUMMARY")
        self.logger.info("=" * generator.BANNER_WIDTH)
        self.logger.info(f"[{self.batch_id}] Total data views: {total}")
        self.logger.info(f"[{self.batch_id}] Successful: {successful_count}")
        self.logger.info(f"[{self.batch_id}] Failed: {failed_count}")
        self.logger.info(f"[{self.batch_id}] Success rate: {success_rate:.1f}%")
        self.logger.info(f"[{self.batch_id}] Total output size: {total_size_formatted}")
        self.logger.info(f"[{self.batch_id}] Total duration: {total_duration:.1f}s")
        self.logger.info(f"[{self.batch_id}] Average per data view: {avg_duration:.1f}s")
        if total_duration > 0:
            throughput = total / total_duration
            self.logger.info(f"[{self.batch_id}] Throughput: {throughput:.2f} views/second")
        self.logger.info("=" * generator.BANNER_WIDTH)

        print()
        print("=" * generator.BANNER_WIDTH)
        print(generator.ConsoleColors.bold("BATCH PROCESSING SUMMARY"))
        print("=" * generator.BANNER_WIDTH)
        print(f"Total data views: {total}")
        print(f"Successful: {generator.ConsoleColors.success(str(successful_count))}")
        if failed_count > 0:
            print(f"Failed: {generator.ConsoleColors.error(str(failed_count))}")
        else:
            print(f"Failed: {failed_count}")
        print(f"Success rate: {generator.ConsoleColors.status(success_rate == 100, f'{success_rate:.1f}%')}")
        print(f"Total output size: {total_size_formatted}")
        print(f"Total duration: {total_duration:.1f}s")
        print(f"Average per data view: {avg_duration:.1f}s")
        if total_duration > 0:
            throughput = total / total_duration
            print(f"Throughput: {throughput:.2f} views/second")
        print()

        if results["successful"]:
            print(generator.ConsoleColors.success("Successful Data Views:"))
            self.logger.info("")
            self.logger.info("Successful Data Views:")
            for result in results["successful"]:
                size_str = result.file_size_formatted
                line = f"  {result.data_view_id:20s}  {result.data_view_name:30s}  {size_str:>10s}  {result.duration:5.1f}s"
                print(generator.ConsoleColors.success("  ✓") + line[3:])
                self.logger.info(
                    f"  ✓ {result.data_view_id:20s}  {result.data_view_name:30s}  {size_str:>10s}  {result.duration:5.1f}s",
                )
            print()
            self.logger.info("")

        if results["failed"]:
            print(generator.ConsoleColors.error("Failed Data Views:"))
            self.logger.info("Failed Data Views:")
            for result in results["failed"]:
                line = f"  {result.data_view_id:20s}  {result.error_message}"
                print(generator.ConsoleColors.error("  ✗") + line[3:])
                self.logger.info(f"  ✗ {result.data_view_id:20s}  {result.error_message}")
            print()
            self.logger.info("")

        print("=" * generator.BANNER_WIDTH)
        self.logger.info("=" * generator.BANNER_WIDTH)

        if total > 0 and total_duration > 0:
            throughput = (total / total_duration) * 60
            print(f"Throughput: {throughput:.1f} data views per minute")
            print("=" * generator.BANNER_WIDTH)
            self.logger.info(f"Throughput: {throughput:.1f} data views per minute")
            self.logger.info("=" * generator.BANNER_WIDTH)
