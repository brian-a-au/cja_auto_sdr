"""Execution helpers for SDR and quality-report CLI modes."""

# ruff: noqa: T201

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

__all__ = [
    "dispatch_inventory_summary_mode",
    "execute_sdr_processing_modes",
    "prepare_sdr_execution_context",
    "resolve_inventory_mode_configuration",
]


def _generator_module():
    from cja_auto_sdr import generator as _generator

    return _generator


def resolve_inventory_mode_configuration(args: argparse.Namespace, *, argv: list[str]) -> list[str]:
    """Validate inventory CLI combinations and return CLI-order inventory ordering."""
    generator = _generator_module()

    has_inventory = any(
        (
            getattr(args, "include_derived_inventory", False),
            getattr(args, "include_calculated_metrics", False),
            getattr(args, "include_segments_inventory", False),
        ),
    )
    if getattr(args, "inventory_only", False) and not has_inventory:
        print(
            generator.ConsoleColors.error("ERROR: --inventory-only requires at least one inventory flag"),
            file=sys.stderr,
        )
        print("Use: --include-derived, --include-calculated, and/or --include-segments", file=sys.stderr)
        print("\nExample: cja_auto_sdr dv_12345 --include-segments --inventory-only", file=sys.stderr)
        sys.exit(1)

    inventory_order: list[str] = []
    if has_inventory:
        derived_pos = None
        calculated_pos = None
        segments_pos = None
        for index, arg in enumerate(argv):
            if arg == "--include-derived" and derived_pos is None:
                derived_pos = index
            elif arg == "--include-calculated" and calculated_pos is None:
                calculated_pos = index
            elif arg == "--include-segments" and segments_pos is None:
                segments_pos = index

        positions = []
        if derived_pos is not None:
            positions.append(("derived", derived_pos))
        if calculated_pos is not None:
            positions.append(("calculated", calculated_pos))
        if segments_pos is not None:
            positions.append(("segments", segments_pos))
        positions.sort(key=lambda item: item[1])
        inventory_order = [name for name, _ in positions]

    if getattr(args, "inventory_summary", False):
        if not has_inventory:
            print(
                generator.ConsoleColors.error("ERROR: --inventory-summary requires at least one inventory flag"),
                file=sys.stderr,
            )
            print("Use: --include-derived, --include-calculated, and/or --include-segments", file=sys.stderr)
            print("\nExample: cja_auto_sdr dv_12345 --include-segments --inventory-summary", file=sys.stderr)
            sys.exit(1)
        if getattr(args, "inventory_only", False):
            print(
                generator.ConsoleColors.error("ERROR: --inventory-summary cannot be used with --inventory-only"),
                file=sys.stderr,
            )
            print(
                "Use --inventory-summary alone for quick stats, or --inventory-only for inventory sheets without full SDR.",
                file=sys.stderr,
            )
            sys.exit(1)

    return inventory_order


def dispatch_inventory_summary_mode(
    args: argparse.Namespace,
    *,
    data_views: list[str],
    effective_log_level: str,
    inventory_order: list[str],
    run_state: dict[str, Any] | None = None,
) -> None:
    """Handle ``--inventory-summary`` mode and exit."""
    generator = _generator_module()

    summary_format = args.format if args.format in ("json", "all") else "console"
    if run_state is not None:
        run_state["output_format"] = summary_format
        run_state["details"] = {"operation_success": True}

    for index, dv_id in enumerate(data_views):
        generator.process_inventory_summary(
            data_view_id=dv_id,
            config_file=args.config_file,
            output_dir=args.output_dir,
            log_level=effective_log_level,
            log_format=args.log_format,
            output_format=summary_format,
            quiet=args.quiet,
            profile=getattr(args, "profile", None),
            include_derived=getattr(args, "include_derived_inventory", False),
            include_calculated=getattr(args, "include_calculated_metrics", False),
            include_segments=getattr(args, "include_segments_inventory", False),
            inventory_order=inventory_order,
        )
        if index < len(data_views) - 1:
            print()

    sys.exit(0)


def _confirm_large_batch(args: argparse.Namespace, *, data_views: list[str]) -> None:
    generator = _generator_module()

    large_batch_threshold = 20
    if (
        len(data_views) < large_batch_threshold
        or getattr(args, "assume_yes", False)
        or args.quiet
        or getattr(args, "dry_run", False)
        or not sys.stdin.isatty()
    ):
        return

    print(generator.ConsoleColors.warning(f"Large batch detected: {len(data_views)} data views"))
    print()
    print("Estimated processing:")
    print(f"  • API calls: ~{len(data_views) * 3} requests (metrics, dimensions, info per DV)")
    print(f"  • Duration: ~{len(data_views) * 2}-{len(data_views) * 5} seconds")
    print()
    print("Tips:")
    print("  • Use --filter to narrow scope: --filter 'prod*'")
    print("  • Use --limit N to process only first N data views")
    print("  • Use --yes to skip this prompt in CI/CD")
    print()

    try:
        response = input("Continue? [y/N]: ").strip().lower()
        if response not in ("y", "yes"):
            print("Cancelled.")
            sys.exit(0)
        print()
    except EOFError, KeyboardInterrupt:
        print("\nCancelled.")
        sys.exit(0)


def prepare_sdr_execution_context(
    args: argparse.Namespace,
    *,
    data_views: list[str],
    show_processing_count: bool = False,
    run_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Prepare validated SDR execution settings and dispatch early execution-only exits."""
    generator = _generator_module()

    _confirm_large_batch(args, data_views=data_views)

    if not args.quiet and show_processing_count:
        print(generator.ConsoleColors.info(f"Processing {len(data_views)} data view(s) total..."))
        print()

    if args.quiet:
        effective_log_level = "ERROR"
    elif args.production:
        effective_log_level = "WARNING"
    else:
        effective_log_level = args.log_level

    if args.dry_run:
        logger = generator.setup_logging(batch_mode=True, log_level="WARNING", log_format=args.log_format)
        success = generator.run_dry_run(data_views, args.config_file, logger, profile=getattr(args, "profile", None))
        if run_state is not None:
            run_state["details"] = {"operation_success": success}
        sys.exit(0 if success else 1)

    quality_report_format = getattr(args, "quality_report", None)
    quality_report_only = quality_report_format is not None

    sdr_format = args.format or "excel"
    if quality_report_only:
        sdr_format = "json"
    if run_state is not None:
        run_state["output_format"] = quality_report_format if quality_report_only else sdr_format

    if sdr_format == "console" and not quality_report_only:
        print(
            generator.ConsoleColors.error("Error: Console format is only supported for diff comparison."),
            file=sys.stderr,
        )
        print(file=sys.stderr)
        print("For SDR generation, use one of these formats:", file=sys.stderr)
        print("  --format excel     Excel workbook with multiple sheets (default)", file=sys.stderr)
        print("  --format csv       CSV files (one per data type)", file=sys.stderr)
        print("  --format json      JSON file with all data", file=sys.stderr)
        print("  --format html      HTML report", file=sys.stderr)
        print("  --format markdown  Markdown document", file=sys.stderr)
        print("  --format all       Generate all formats", file=sys.stderr)
        print(file=sys.stderr)
        print("For diff comparison, console is the default:", file=sys.stderr)
        print("  cja_auto_sdr --diff dv_A dv_B              # Console output", file=sys.stderr)
        print("  cja_auto_sdr --diff dv_A dv_B --format json  # JSON output", file=sys.stderr)
        sys.exit(1)

    if getattr(args, "metrics_only", False) and getattr(args, "dimensions_only", False):
        print(
            generator.ConsoleColors.error("ERROR: Cannot use both --metrics-only and --dimensions-only"),
            file=sys.stderr,
        )
        sys.exit(1)

    output_access_ok, resolved_output_dir, access_reason, parent_dir = generator._check_output_dir_access(
        args.output_dir
    )
    if not output_access_ok:
        if access_reason == "not_directory":
            print(
                generator.ConsoleColors.error(f"ERROR: Output path is not a directory: {resolved_output_dir}"),
                file=sys.stderr,
            )
        elif access_reason == "parent_not_directory" and parent_dir is not None:
            print(
                generator.ConsoleColors.error(f"ERROR: Cannot create output directory: {resolved_output_dir}"),
                file=sys.stderr,
            )
            print(f"Path component is not a directory: {parent_dir}", file=sys.stderr)
        elif access_reason == "parent_not_writable" and parent_dir is not None:
            print(
                generator.ConsoleColors.error(f"ERROR: Cannot create output directory: {resolved_output_dir}"),
                file=sys.stderr,
            )
            print(f"Parent directory {parent_dir} is not writable.", file=sys.stderr)
        else:
            print(
                generator.ConsoleColors.error(f"ERROR: Cannot write to output directory: {resolved_output_dir}"),
                file=sys.stderr,
            )
            print("Check permissions and try again.", file=sys.stderr)
        sys.exit(1)

    processing_start_time = time.time()

    api_tuning_config = None
    if getattr(args, "api_auto_tune", False):
        api_tuning_config = generator.APITuningConfig(
            min_workers=getattr(args, "api_min_workers", 1),
            max_workers=getattr(args, "api_max_workers", 10),
        )
        if not args.quiet:
            print(
                generator.ConsoleColors.info(
                    f"API auto-tuning enabled (workers: {api_tuning_config.min_workers}-{api_tuning_config.max_workers})",
                ),
            )

    circuit_breaker_config = None
    if getattr(args, "circuit_breaker", False):
        circuit_breaker_config = generator.CircuitBreakerConfig(
            failure_threshold=getattr(args, "circuit_failure_threshold", 5),
            timeout_seconds=getattr(args, "circuit_timeout", 30.0),
        )
        if not args.quiet:
            print(
                generator.ConsoleColors.info(
                    f"Circuit breaker enabled (threshold: {circuit_breaker_config.failure_threshold}, timeout: {circuit_breaker_config.timeout_seconds}s)",
                ),
            )

    inventory_order = resolve_inventory_mode_configuration(args, argv=list(sys.argv))
    if getattr(args, "inventory_summary", False):
        dispatch_inventory_summary_mode(
            args,
            data_views=data_views,
            effective_log_level=effective_log_level,
            inventory_order=inventory_order,
            run_state=run_state,
        )

    return {
        "effective_log_level": effective_log_level,
        "quality_report_format": quality_report_format,
        "quality_report_only": quality_report_only,
        "sdr_format": sdr_format,
        "processing_start_time": processing_start_time,
        "api_tuning_config": api_tuning_config,
        "circuit_breaker_config": circuit_breaker_config,
        "inventory_order": inventory_order,
    }


def _run_quality_report_mode(
    args: argparse.Namespace,
    *,
    data_views: list[str],
    effective_log_level: str,
    sdr_format: str,
    processing_start_time: float,
    api_tuning_config: Any,
    circuit_breaker_config: Any,
) -> dict[str, Any]:
    generator = _generator_module()

    successful_results: list[Any] = []
    quality_report_results: list[Any] = []
    processed_results: list[Any] = []
    overall_failure = False
    processing_failures_detected = False

    if not args.quiet:
        print(generator.ConsoleColors.info(f"Validating data quality for {len(data_views)} data view(s)..."))
        print()

    for dv_id in data_views:
        result = generator.process_single_dataview(
            dv_id,
            config_file=args.config_file,
            output_dir=args.output_dir,
            log_level=effective_log_level,
            log_format=args.log_format,
            output_format=sdr_format,
            enable_cache=args.enable_cache,
            cache_size=args.cache_size,
            cache_ttl=args.cache_ttl,
            quiet=args.quiet,
            skip_validation=args.skip_validation,
            max_issues=args.max_issues,
            clear_cache=args.clear_cache,
            show_timings=args.show_timings,
            metrics_only=getattr(args, "metrics_only", False),
            dimensions_only=getattr(args, "dimensions_only", False),
            profile=getattr(args, "profile", None),
            api_tuning_config=api_tuning_config,
            circuit_breaker_config=circuit_breaker_config,
            include_derived_inventory=False,
            include_calculated_metrics=False,
            include_segments_inventory=False,
            inventory_only=False,
            inventory_order=None,
            quality_report_only=True,
            allow_partial=getattr(args, "allow_partial", False),
            production_mode=args.production,
        )
        quality_report_results.append(result)
        processed_results.append(result)

        if result.success:
            successful_results.append(result)
            if not args.quiet:
                print(
                    generator.ConsoleColors.success(
                        f"✓ {result.data_view_name} ({result.data_view_id}): {result.dq_issues_count} issues",
                    ),
                )
        else:
            overall_failure = True
            processing_failures_detected = True
            print(
                generator.ConsoleColors.error(f"FAILED: {result.data_view_id} - {result.error_message}"),
                file=sys.stderr,
            )
            if not args.continue_on_error:
                break

    if not args.quiet:
        total_runtime = time.time() - processing_start_time
        print()
        print(generator.ConsoleColors.bold(f"Total runtime: {total_runtime:.1f}s"))

    return {
        "successful_results": successful_results,
        "quality_report_results": quality_report_results,
        "processed_results": processed_results,
        "overall_failure": overall_failure,
        "processing_failures_detected": processing_failures_detected,
    }


def _run_batch_mode(
    args: argparse.Namespace,
    *,
    data_views: list[str],
    effective_log_level: str,
    sdr_format: str,
    processing_start_time: float,
    workers_auto: bool,
    quality_report_only: bool,
    inventory_order: list[str],
    api_tuning_config: Any,
    circuit_breaker_config: Any,
) -> dict[str, Any]:
    generator = _generator_module()

    if workers_auto:
        args.workers = generator.auto_detect_workers(num_data_views=len(data_views))
        if not args.quiet:
            cpu_count = os.cpu_count() or 4
            print(
                generator.ConsoleColors.info(
                    f"Auto-detected workers: {args.workers} (based on {cpu_count} CPU cores, {len(data_views)} data views)",
                ),
            )

    if not args.quiet:
        print(
            generator.ConsoleColors.info(
                f"Processing {len(data_views)} data view(s) in batch mode with {args.workers} workers...",
            ),
        )
        print()

    processor = generator.BatchProcessor(
        config_file=args.config_file,
        output_dir=args.output_dir,
        workers=args.workers,
        continue_on_error=args.continue_on_error,
        log_level=effective_log_level,
        log_format=args.log_format,
        output_format=sdr_format,
        enable_cache=args.enable_cache,
        cache_size=args.cache_size,
        cache_ttl=args.cache_ttl,
        quiet=args.quiet,
        skip_validation=args.skip_validation,
        max_issues=args.max_issues,
        clear_cache=args.clear_cache,
        show_timings=args.show_timings,
        metrics_only=getattr(args, "metrics_only", False),
        dimensions_only=getattr(args, "dimensions_only", False),
        profile=getattr(args, "profile", None),
        shared_cache=getattr(args, "shared_cache", False),
        api_tuning_config=api_tuning_config,
        circuit_breaker_config=circuit_breaker_config,
        include_derived_inventory=getattr(args, "include_derived_inventory", False),
        include_calculated_metrics=getattr(args, "include_calculated_metrics", False),
        include_segments_inventory=getattr(args, "include_segments_inventory", False),
        inventory_only=getattr(args, "inventory_only", False),
        inventory_order=inventory_order or None,
        quality_report_only=quality_report_only,
        allow_partial=getattr(args, "allow_partial", False),
        production_mode=args.production,
    )

    results = processor.process_batch(data_views)
    successful_results = list(results.get("successful", []))
    processed_results = successful_results + list(results.get("failed", []))

    total_runtime = time.time() - processing_start_time
    print()
    print(generator.ConsoleColors.bold(f"Total runtime: {total_runtime:.1f}s"))

    if getattr(args, "open", False) and results.get("successful") and not quality_report_only:
        files_to_open = []
        for success_info in results["successful"]:
            files_to_open.extend(generator._result_output_paths(success_info))

        if files_to_open:
            print()
            print(f"Opening {len(files_to_open)} file(s)...")
            for file_path in files_to_open:
                if not generator.open_file_in_default_app(file_path):
                    print(generator.ConsoleColors.warning(f"  Could not open: {file_path}"))

    return {
        "successful_results": successful_results,
        "quality_report_results": [],
        "processed_results": processed_results,
        "overall_failure": bool(results["failed"] and not args.continue_on_error),
        "processing_failures_detected": bool(results.get("failed")),
    }


def _print_single_mode_inventory_summary(
    result: Any,
    *,
    inventory_order: list[str],
    include_segments: bool,
    include_calculated: bool,
    include_derived: bool,
) -> None:
    generator = _generator_module()

    if not (include_segments or include_calculated or include_derived):
        return

    inv_parts: list[str] = []
    inv_order = inventory_order or ["segments", "calculated", "derived"]
    for inv_type in inv_order:
        if inv_type == "segments" and include_segments:
            seg_str = f"Segments: {result.segments_count}"
            if result.segments_high_complexity > 0:
                seg_str += f" ({result.segments_high_complexity} high-complexity)"
            inv_parts.append(seg_str)
        elif inv_type == "calculated" and include_calculated:
            calc_str = f"Calculated Metrics: {result.calculated_metrics_count}"
            if result.calculated_metrics_high_complexity > 0:
                calc_str += f" ({result.calculated_metrics_high_complexity} high-complexity)"
            inv_parts.append(calc_str)
        elif inv_type == "derived" and include_derived:
            derived_str = f"Derived Fields: {result.derived_fields_count}"
            if result.derived_fields_high_complexity > 0:
                derived_str += f" ({result.derived_fields_high_complexity} high-complexity)"
            inv_parts.append(derived_str)

    if inv_parts:
        print(f"  Inventory: {', '.join(inv_parts)}")

    if result.total_high_complexity > 0:
        print(
            generator.ConsoleColors.warning(
                f"  ⚠ {result.total_high_complexity} high-complexity items (≥75) - review recommended",
            ),
        )


def _handle_single_mode_git_commit(args: argparse.Namespace, result: Any) -> None:
    generator = _generator_module()

    if not getattr(args, "git_commit", False):
        return

    print()
    git_dir = Path(getattr(args, "git_dir", "./sdr-snapshots"))

    if not generator.is_git_repository(git_dir):
        print(f"Initializing Git repository at: {git_dir}")
        init_success, init_msg = generator.git_init_snapshot_repo(git_dir)
        if not init_success:
            print(generator.ConsoleColors.error(f"Git init failed: {init_msg}"))
        else:
            print(generator.ConsoleColors.success("  Repository initialized"))

    snapshot = generator.DataViewSnapshot(
        data_view_id=result.data_view_id,
        data_view_name=result.data_view_name,
        metrics=result.metrics_data if hasattr(result, "metrics_data") else [],
        dimensions=result.dimensions_data if hasattr(result, "dimensions_data") else [],
    )

    snapshot = generator._refetch_git_snapshot_for_commit(
        snapshot=snapshot,
        data_view_id=result.data_view_id,
        config_file=args.config_file,
        profile=getattr(args, "profile", None),
        include_calculated_metrics=getattr(args, "include_calculated_metrics", False),
        include_segments_inventory=getattr(args, "include_segments_inventory", False),
    )

    print(f"Saving snapshot to: {git_dir}")
    generator.save_git_friendly_snapshot(
        snapshot=snapshot,
        output_dir=git_dir,
        quality_issues=result.dq_issues if hasattr(result, "dq_issues") else None,
    )

    commit_success, commit_result = generator.git_commit_snapshot(
        snapshot_dir=git_dir,
        data_view_id=result.data_view_id,
        data_view_name=result.data_view_name,
        metrics_count=result.metrics_count,
        dimensions_count=result.dimensions_count,
        quality_issues=result.dq_issues if hasattr(result, "dq_issues") else None,
        custom_message=getattr(args, "git_message", None),
        push=getattr(args, "git_push", False),
    )

    if commit_success:
        if commit_result == "no_changes":
            print(generator.ConsoleColors.info("  No changes to commit (snapshot unchanged)"))
        else:
            print(generator.ConsoleColors.success(f"  Committed: {commit_result}"))
            if getattr(args, "git_push", False):
                print(generator.ConsoleColors.success("  Pushed to remote"))
    else:
        print(generator.ConsoleColors.error(f"  Git commit failed: {commit_result}"))


def _handle_single_mode_open(args: argparse.Namespace, result: Any) -> None:
    generator = _generator_module()

    if not (getattr(args, "open", False) and result.emitted_output_files):
        return

    print()
    if len(result.emitted_output_files) == 1:
        print("Opening file...")
    else:
        print(f"Opening {len(result.emitted_output_files)} file(s)...")
    for file_path in result.emitted_output_files:
        if not generator.open_file_in_default_app(file_path):
            print(generator.ConsoleColors.warning(f"  Could not open: {file_path}"))


def _run_single_mode(
    args: argparse.Namespace,
    *,
    data_views: list[str],
    effective_log_level: str,
    sdr_format: str,
    processing_start_time: float,
    quality_report_only: bool,
    inventory_order: list[str],
    api_tuning_config: Any,
    circuit_breaker_config: Any,
) -> dict[str, Any]:
    generator = _generator_module()

    if not args.quiet:
        print(generator.ConsoleColors.info(f"Processing data view: {data_views[0]}"))
        print()

    result = generator.process_single_dataview(
        data_views[0],
        config_file=args.config_file,
        output_dir=args.output_dir,
        log_level=effective_log_level,
        log_format=args.log_format,
        output_format=sdr_format,
        enable_cache=args.enable_cache,
        cache_size=args.cache_size,
        cache_ttl=args.cache_ttl,
        quiet=args.quiet,
        skip_validation=args.skip_validation,
        max_issues=args.max_issues,
        clear_cache=args.clear_cache,
        show_timings=args.show_timings,
        metrics_only=getattr(args, "metrics_only", False),
        dimensions_only=getattr(args, "dimensions_only", False),
        profile=getattr(args, "profile", None),
        api_tuning_config=api_tuning_config,
        circuit_breaker_config=circuit_breaker_config,
        include_derived_inventory=getattr(args, "include_derived_inventory", False),
        include_calculated_metrics=getattr(args, "include_calculated_metrics", False),
        include_segments_inventory=getattr(args, "include_segments_inventory", False),
        inventory_only=getattr(args, "inventory_only", False),
        inventory_order=inventory_order or None,
        quality_report_only=quality_report_only,
        allow_partial=getattr(args, "allow_partial", False),
        production_mode=args.production,
    )
    processed_results = [result]

    total_runtime = time.time() - processing_start_time
    print()
    if result.success:
        successful_results = [result]
        if quality_report_only:
            print(generator.ConsoleColors.success(f"SUCCESS: Quality validation completed for {result.data_view_name}"))
            print(f"  Metrics: {result.metrics_count}, Dimensions: {result.dimensions_count}")
            print(f"  Data Quality Issues: {result.dq_issues_count}")
        else:
            print(generator.ConsoleColors.success(f"SUCCESS: SDR generated for {result.data_view_name}"))
            if len(result.emitted_output_files) > 1:
                print(f"  Outputs: {len(result.emitted_output_files)} files")
                for file_path in result.emitted_output_files:
                    print(f"    - {file_path}")
            else:
                print(f"  Output: {result.output_file}")
            print(f"  Size: {result.file_size_formatted}")
            print(f"  Metrics: {result.metrics_count}, Dimensions: {result.dimensions_count}")
            if result.dq_issues_count > 0:
                print(generator.ConsoleColors.warning(f"  Data Quality Issues: {result.dq_issues_count}"))

            _print_single_mode_inventory_summary(
                result,
                inventory_order=inventory_order,
                include_segments=getattr(args, "include_segments_inventory", False),
                include_calculated=getattr(args, "include_calculated_metrics", False),
                include_derived=getattr(args, "include_derived_inventory", False),
            )
            _handle_single_mode_git_commit(args, result)
            _handle_single_mode_open(args, result)
    else:
        successful_results = []
        print(generator.ConsoleColors.error(f"FAILED: {result.error_message}"))

    print(generator.ConsoleColors.bold(f"Total runtime: {total_runtime:.1f}s"))

    return {
        "successful_results": successful_results,
        "quality_report_results": [],
        "processed_results": processed_results,
        "overall_failure": not result.success,
        "processing_failures_detected": not result.success,
    }


def execute_sdr_processing_modes(
    args: argparse.Namespace,
    *,
    data_views: list[str],
    effective_log_level: str,
    sdr_format: str,
    processing_start_time: float,
    workers_auto: bool,
    quality_report_only: bool,
    inventory_order: list[str],
    api_tuning_config: Any,
    circuit_breaker_config: Any,
) -> dict[str, Any]:
    """Execute the remaining SDR/quality-report processing branches for ``_main_impl()``."""
    if quality_report_only:
        return _run_quality_report_mode(
            args,
            data_views=data_views,
            effective_log_level=effective_log_level,
            sdr_format=sdr_format,
            processing_start_time=processing_start_time,
            api_tuning_config=api_tuning_config,
            circuit_breaker_config=circuit_breaker_config,
        )

    if args.batch or len(data_views) > 1:
        return _run_batch_mode(
            args,
            data_views=data_views,
            effective_log_level=effective_log_level,
            sdr_format=sdr_format,
            processing_start_time=processing_start_time,
            workers_auto=workers_auto,
            quality_report_only=quality_report_only,
            inventory_order=inventory_order,
            api_tuning_config=api_tuning_config,
            circuit_breaker_config=circuit_breaker_config,
        )

    return _run_single_mode(
        args,
        data_views=data_views,
        effective_log_level=effective_log_level,
        sdr_format=sdr_format,
        processing_start_time=processing_start_time,
        quality_report_only=quality_report_only,
        inventory_order=inventory_order,
        api_tuning_config=api_tuning_config,
        circuit_breaker_config=circuit_breaker_config,
    )
