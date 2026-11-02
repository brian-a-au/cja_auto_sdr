"""Execution helpers for SDR and quality-report CLI modes."""

# ruff: noqa: T201

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any

from cja_auto_sdr.cli.option_resolution import resolve_long_option_token

__all__ = [
    "dispatch_inventory_summary_mode",
    "execute_sdr_processing_modes",
    "prepare_sdr_execution_context",
    "resolve_inventory_mode_configuration",
    "validate_json_typed_format",
]


def _generator_module():
    from cja_auto_sdr import generator as _generator

    return _generator


def validate_json_typed_format(args: argparse.Namespace, *, output_format: str | None = None) -> None:
    """Reject --json-typed unless the effective SDR format is exactly json.

    Runs before any CJA client setup or API call. Quality-report runs write
    their own report rather than SDR JSON, so the flag is ignored there.
    """
    if not getattr(args, "json_typed", False) or getattr(args, "quality_report", None):
        return
    effective_format = output_format if output_format is not None else getattr(args, "format", None)
    if (str(effective_format or "").strip().lower() or "excel") != "json":
        from cja_auto_sdr.core.colors import ConsoleColors

        print(ConsoleColors.error("ERROR: --json-typed requires --format json"), file=sys.stderr)
        sys.exit(1)


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
        # Imported directly: tests replace _generator_module() with a stub.
        from cja_auto_sdr.generator import _known_long_options

        known_long_options = _known_long_options()
        option_types = {
            "--include-derived": "derived",
            "--include-calculated": "calculated",
            "--include-segments": "segments",
        }
        enabled = {
            "derived": getattr(args, "include_derived_inventory", False),
            "calculated": getattr(args, "include_calculated_metrics", False),
            "segments": getattr(args, "include_segments_inventory", False),
        }
        for arg in argv:
            canonical = resolve_long_option_token(arg, known_long_options).canonical_option
            inv_type = option_types.get(canonical or "")
            if inv_type is not None and inv_type not in inventory_order:
                inventory_order.append(inv_type)

        # Flags enabled without their own token (for example by --include-all-inventory)
        # still need a place once the user gave an explicit order.
        if inventory_order:
            inventory_order.extend(
                inv_type
                for inv_type in ("derived", "calculated", "segments")
                if enabled[inv_type] and inv_type not in inventory_order
            )

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


# Imports generator directly: tests stub the generator module and its attributes.
def _warn_output_ignored(output_file: str | None, *, scope: str, hint: str) -> None:
    from cja_auto_sdr.generator import _warn_output_ignored as _impl

    _impl(output_file, scope=scope, hint=hint)


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

    output_file = getattr(args, "output", None)
    if output_file and len(data_views) > 1:
        print(
            generator.ConsoleColors.error(
                "ERROR: --output with --inventory-summary takes one data view; use --output-dir for several."
            ),
            file=sys.stderr,
        )
        sys.exit(1)

    if output_file and args.format not in ("json", "all"):
        _warn_output_ignored(
            output_file,
            scope=f"with --inventory-summary --format {args.format or 'console'}",
            hint="use --format json to write the summary to a file",
        )

    # Stdout output is always the JSON summary.
    if output_file in ("-", "stdout"):
        summary_format = "json"
    else:
        summary_format = args.format if args.format in ("json", "all") else "console"
    if run_state is not None:
        run_state["output_format"] = summary_format
        run_state["details"] = {"operation_success": True}

    failed = False
    for index, dv_id in enumerate(data_views):
        summary = generator.process_inventory_summary(
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
            output_file=output_file,
            log_to_stderr=bool(getattr(args, "agent_mode", False)),
        )
        if isinstance(summary, dict) and "error" in summary:
            failed = True
        if index < len(data_views) - 1:
            print()

    if failed and run_state is not None:
        run_state["details"] = {"operation_success": False}
    sys.exit(1 if failed else 0)


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
    except (EOFError, KeyboardInterrupt):
        print("\nCancelled.")
        sys.exit(0)


def _resolve_sdr_processing_mode(
    args: argparse.Namespace,
    *,
    data_views: list[str],
    quality_report_only: bool,
) -> str:
    """Return the effective SDR execution path for the current invocation."""
    if quality_report_only:
        return "quality_report"
    if getattr(args, "batch", False) or len(data_views) > 1:
        return "batch"
    return "single"


def _resolve_shared_cache_active(
    args: argparse.Namespace,
    *,
    processing_mode: str,
) -> bool:
    """Report shared-cache activation only when the batch executor can instantiate it."""
    return bool(
        processing_mode == "batch"
        and getattr(args, "shared_cache", False)
        and getattr(args, "enable_cache", True)
        and not getattr(args, "skip_validation", False)
    )


def _build_run_summary_execution_settings(
    *,
    processing_mode: str,
    workers_requested_value: str | int | None,
    effective_workers: int | None,
    api_auto_tune_requested: bool,
    circuit_breaker_enabled: bool,
    shared_cache_active: bool,
) -> dict[str, Any]:
    """Build execution_settings using effective runtime behavior, not raw CLI intent."""
    execution_settings: dict[str, Any] = {
        "api_auto_tune_requested": api_auto_tune_requested,
        "circuit_breaker_enabled": circuit_breaker_enabled,
    }

    if processing_mode == "batch":
        if workers_requested_value is not None:
            execution_settings["batch_workers_requested"] = workers_requested_value
        if effective_workers is not None:
            execution_settings["batch_workers_effective"] = int(effective_workers)
        execution_settings["shared_cache_active"] = shared_cache_active

    return execution_settings


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
    validate_json_typed_format(args, output_format=sdr_format)

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
                generator.ConsoleColors.error(f"ERROR: Output directory {resolved_output_dir}: not a directory"),
                file=sys.stderr,
            )
        elif access_reason == "parent_not_directory" and parent_dir is not None:
            print(
                generator.ConsoleColors.error(
                    f"ERROR: Output directory {resolved_output_dir}: cannot create — parent {parent_dir} is not a directory"
                ),
                file=sys.stderr,
            )
        elif access_reason == "parent_not_writable" and parent_dir is not None:
            print(
                generator.ConsoleColors.error(
                    f"ERROR: Output directory {resolved_output_dir}: cannot create — parent {parent_dir} is not writable"
                ),
                file=sys.stderr,
            )
        else:
            print(
                generator.ConsoleColors.error(
                    f"ERROR: Output directory {resolved_output_dir}: not writable. Check permissions and try again"
                ),
                file=sys.stderr,
            )
        sys.exit(1)

    processing_start_time = time.monotonic()

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

    # --- Execution metadata for run-summary enrichment ---
    # shared-cache activation must follow the effective processing path, not
    # just raw CLI intent. Quality-report mode stays sequential even when
    # multiple data views are supplied, so it cannot activate the shared cache.
    processing_mode = _resolve_sdr_processing_mode(
        args,
        data_views=data_views,
        quality_report_only=quality_report_only,
    )
    shared_cache_active = _resolve_shared_cache_active(args, processing_mode=processing_mode)

    return {
        "effective_log_level": effective_log_level,
        "quality_report_format": quality_report_format,
        "quality_report_only": quality_report_only,
        "sdr_format": sdr_format,
        "processing_start_time": processing_start_time,
        "api_tuning_config": api_tuning_config,
        "circuit_breaker_config": circuit_breaker_config,
        "inventory_order": inventory_order,
        "api_auto_tune_requested": api_tuning_config is not None,
        "circuit_breaker_enabled": circuit_breaker_config is not None,
        "shared_cache_active": shared_cache_active,
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
            notion_force_new=getattr(args, "notion_force_new", False),
            notion_database_id=getattr(args, "notion_database_id", None) or os.environ.get("NOTION_DATABASE_ID"),
            notion_create_database=getattr(args, "notion_create_database", False),
            log_to_stderr=bool(getattr(args, "agent_mode", False)),
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
        total_runtime = time.monotonic() - processing_start_time
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

    _warn_output_ignored(
        getattr(args, "output", None),
        scope="with --batch",
        hint="use --output-dir to choose the folder for batch output",
    )

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
        notion_force_new=getattr(args, "notion_force_new", False),
        notion_database_id=getattr(args, "notion_database_id", None) or os.environ.get("NOTION_DATABASE_ID"),
        notion_create_database=getattr(args, "notion_create_database", False),
        json_typed=getattr(args, "json_typed", False),
        fail_on_quality=getattr(args, "fail_on_quality", None),
        log_to_stderr=bool(getattr(args, "agent_mode", False)),
    )

    results = processor.process_batch(data_views)
    successful_results = list(results.get("successful", []))
    processed_results = successful_results + list(results.get("failed", []))

    total_runtime = time.monotonic() - processing_start_time
    if not args.quiet:
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
        # --continue-on-error keeps processing the remaining data views, but it
        # never hides failures: any failed data view makes the batch exit 1.
        "overall_failure": bool(results.get("failed")),
        "processing_failures_detected": bool(results.get("failed")),
        "effective_workers": int(args.workers),
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


def _handle_single_mode_git_commit(args: argparse.Namespace, result: Any) -> bool:
    """Run the optional --git-commit step.

    Returns False when the Git step failed and must fail the run (inconclusive
    repository probe, failed init, failed snapshot re-fetch, or failed commit);
    True otherwise, including when --git-commit was not requested.
    """
    generator = _generator_module()

    if not getattr(args, "git_commit", False):
        return True

    print()
    git_dir = Path(getattr(args, "git_dir", "./sdr-snapshots"))

    repo_state = generator.git_repository_state(git_dir)
    if repo_state == "unknown":
        print(
            generator.ConsoleColors.error(
                f"  Git commit failed: Could not determine whether {git_dir} is a Git repository "
                "(git probe failed or timed out); not initializing or committing.",
            ),
        )
        return False

    if repo_state != "repo":
        print(f"Initializing Git repository at: {git_dir}")
        init_success, init_msg = generator.git_init_snapshot_repo(git_dir)
        if not init_success:
            print(generator.ConsoleColors.error(f"Git init failed: {init_msg}"))
            return False
        print(generator.ConsoleColors.success("  Repository initialized"))

    snapshot = generator.DataViewSnapshot(
        data_view_id=result.data_view_id,
        data_view_name=result.data_view_name,
        metrics=result.metrics_data if hasattr(result, "metrics_data") else [],
        dimensions=result.dimensions_data if hasattr(result, "dimensions_data") else [],
    )

    refetched = generator._refetch_git_snapshot_for_commit(
        snapshot=snapshot,
        data_view_id=result.data_view_id,
        config_file=args.config_file,
        profile=getattr(args, "profile", None),
        include_calculated_metrics=getattr(args, "include_calculated_metrics", False),
        include_segments_inventory=getattr(args, "include_segments_inventory", False),
    )
    if refetched is None:
        print(
            generator.ConsoleColors.error(
                "  Git snapshot not saved: component data could not be fetched, and committing an "
                "empty snapshot would record every metric and dimension as removed.",
            ),
        )
        return False
    snapshot = refetched

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
            push_marker = " (push failed: "
            sha, _, push_tail = commit_result.partition(push_marker)
            print(generator.ConsoleColors.success(f"  Committed: {sha}"))
            if getattr(args, "git_push", False):
                if push_marker in commit_result:
                    push_reason = push_tail.removesuffix(")").strip() or "unknown error"
                    print(generator.ConsoleColors.warning(f"  Push failed: {push_reason}"))
                else:
                    print(generator.ConsoleColors.success("  Pushed to remote"))
    else:
        print(generator.ConsoleColors.error(f"  Git commit failed: {commit_result}"))
        return False
    return True


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

    # When streaming the SDR JSON to stdout (--output stdout/- with --format json),
    # keep stdout clean by routing all human-facing output to stderr.
    stdout_mode = str(getattr(args, "output", None)) in ("-", "stdout") and sdr_format == "json"
    report_stream = sys.stderr if stdout_mode else sys.stdout

    def _note(*print_args: Any, **print_kwargs: Any) -> None:
        print_kwargs.setdefault("file", report_stream)
        print(*print_args, **print_kwargs)

    if not args.quiet:
        _note(generator.ConsoleColors.info(f"Processing data view: {data_views[0]}"))
        _note()

    result = generator.process_single_dataview(
        data_views[0],
        config_file=args.config_file,
        output_dir=args.output_dir,
        output_file=getattr(args, "output", None),
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
        notion_force_new=getattr(args, "notion_force_new", False),
        notion_database_id=getattr(args, "notion_database_id", None) or os.environ.get("NOTION_DATABASE_ID"),
        notion_create_database=getattr(args, "notion_create_database", False),
        json_typed=getattr(args, "json_typed", False),
        fail_on_quality=getattr(args, "fail_on_quality", None),
        log_to_stderr=bool(getattr(args, "agent_mode", False)),
    )
    processed_results = [result]
    git_step_ok = True

    total_runtime = time.monotonic() - processing_start_time

    # --quiet (implied by --output -) suppresses the success summary; failures still print.
    def _summary(*print_args: Any, **print_kwargs: Any) -> None:
        if not args.quiet:
            _note(*print_args, **print_kwargs)

    _summary()
    if result.success:
        successful_results = [result]
        if quality_report_only:
            _summary(
                generator.ConsoleColors.success(f"SUCCESS: Quality validation completed for {result.data_view_name}")
            )
            _summary(f"  Metrics: {result.metrics_count}, Dimensions: {result.dimensions_count}")
            _summary(f"  Data Quality Issues: {result.dq_issues_count}")
        else:
            _summary(generator.ConsoleColors.success(f"SUCCESS: SDR generated for {result.data_view_name}"))
            if len(result.emitted_output_files) > 1:
                _summary(f"  Outputs: {len(result.emitted_output_files)} files")
                for file_path in result.emitted_output_files:
                    _summary(f"    - {file_path}")
            else:
                _summary(f"  Output: {result.output_file}")
            _summary(f"  Size: {result.file_size_formatted}")
            _summary(f"  Metrics: {result.metrics_count}, Dimensions: {result.dimensions_count}")
            if result.dq_issues_count > 0:
                _summary(generator.ConsoleColors.warning(f"  Data Quality Issues: {result.dq_issues_count}"))

            # Skip human-oriented post-actions when streaming to stdout so the
            # JSON payload on stdout stays clean (there is also no file to open).
            if not stdout_mode:
                if not args.quiet:
                    _print_single_mode_inventory_summary(
                        result,
                        inventory_order=inventory_order,
                        include_segments=getattr(args, "include_segments_inventory", False),
                        include_calculated=getattr(args, "include_calculated_metrics", False),
                        include_derived=getattr(args, "include_derived_inventory", False),
                    )
                git_step_ok = _handle_single_mode_git_commit(args, result)
                _handle_single_mode_open(args, result)
    else:
        successful_results = []
        _note(generator.ConsoleColors.error(f"FAILED: {result.error_message}"))

    _summary(generator.ConsoleColors.bold(f"Total runtime: {total_runtime:.1f}s"))

    return {
        "successful_results": successful_results,
        "quality_report_results": [],
        "processed_results": processed_results,
        "overall_failure": not result.success or not git_step_ok,
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
    workers_requested_value: str | int | None = None,
    api_auto_tune_requested: bool = False,
    circuit_breaker_enabled: bool = False,
) -> dict[str, Any]:
    """Execute the remaining SDR/quality-report processing branches for ``_main_impl()``."""
    processing_mode = _resolve_sdr_processing_mode(
        args,
        data_views=data_views,
        quality_report_only=quality_report_only,
    )

    if processing_mode == "quality_report":
        result = _run_quality_report_mode(
            args,
            data_views=data_views,
            effective_log_level=effective_log_level,
            sdr_format=sdr_format,
            processing_start_time=processing_start_time,
            api_tuning_config=api_tuning_config,
            circuit_breaker_config=circuit_breaker_config,
        )
    elif processing_mode == "batch":
        result = _run_batch_mode(
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
    else:
        result = _run_single_mode(
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

    result["processing_mode"] = processing_mode
    result["execution_settings"] = _build_run_summary_execution_settings(
        processing_mode=processing_mode,
        workers_requested_value=workers_requested_value,
        effective_workers=result.get("effective_workers"),
        api_auto_tune_requested=api_auto_tune_requested,
        circuit_breaker_enabled=circuit_breaker_enabled,
        shared_cache_active=_resolve_shared_cache_active(args, processing_mode=processing_mode),
    )
    return result
