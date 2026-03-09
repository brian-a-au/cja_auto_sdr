"""Snapshot and diff CLI dispatch helpers extracted from generator.py."""

# ruff: noqa: T201

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path
from typing import Any

__all__ = ["dispatch_cross_data_view_diff_cli_mode", "dispatch_snapshot_cli_modes"]


def _generator_module():
    from cja_auto_sdr import generator as _generator

    return _generator


def _exit_with_diff_result(
    *,
    success: bool,
    has_changes: bool,
    exit_code_override: int | None,
) -> None:
    """Exit using the standard diff-family exit-code contract."""
    if success:
        if exit_code_override is not None:
            sys.exit(exit_code_override)
        sys.exit(2 if has_changes else 0)
    sys.exit(1)


def _resolve_single_data_view_id_or_exit(
    data_view_inputs: list[str],
    *,
    args: argparse.Namespace,
    command_name: str,
    usage: str,
) -> list[str]:
    """Resolve one data view input to exactly one ID or exit with the existing UX."""
    generator = _generator_module()

    if len(data_view_inputs) != 1:
        print(
            generator.ConsoleColors.error(f"ERROR: {command_name} requires exactly 1 data view ID or name"),
            file=sys.stderr,
        )
        print(usage, file=sys.stderr)
        sys.exit(1)

    temp_logger = logging.getLogger("name_resolution")
    temp_logger.setLevel(logging.WARNING)
    resolved_ids, _ = generator.resolve_data_view_names(
        data_view_inputs,
        args.config_file,
        temp_logger,
        profile=getattr(args, "profile", None),
        match_mode=getattr(args, "name_match", "exact"),
    )

    if not resolved_ids:
        print(
            generator.ConsoleColors.error(f"ERROR: Could not resolve data view: '{data_view_inputs[0]}'"),
            file=sys.stderr,
        )
        sys.exit(1)

    if len(resolved_ids) > 1:
        dv_name = data_view_inputs[0]
        options = [(dv_id, f"{dv_name} ({dv_id})") for dv_id in resolved_ids]
        selected = generator.prompt_for_selection(
            options,
            f"Name '{dv_name}' matches {len(resolved_ids)} data views. Please select one:",
        )
        if selected:
            return [selected]

        print(
            generator.ConsoleColors.error(
                f"ERROR: Name '{dv_name}' is ambiguous - matches {len(resolved_ids)} data views:",
            ),
            file=sys.stderr,
        )
        for dv_id in resolved_ids:
            print(f"  • {dv_id}", file=sys.stderr)
        print("\nPlease specify the exact data view ID instead of the name.", file=sys.stderr)
        sys.exit(1)

    return [resolved_ids[0]]


def _resolve_diff_input_or_exit(
    data_view_input: str,
    *,
    args: argparse.Namespace,
    role: str,
) -> str:
    """Resolve one cross-data-view diff operand to a single data view ID or exit."""
    generator = _generator_module()

    temp_logger = logging.getLogger("name_resolution")
    temp_logger.setLevel(logging.WARNING)
    resolved_ids, _ = generator.resolve_data_view_names(
        [data_view_input],
        args.config_file,
        temp_logger,
        profile=getattr(args, "profile", None),
        match_mode=getattr(args, "name_match", "exact"),
    )

    if not resolved_ids:
        print(
            generator.ConsoleColors.error(f"ERROR: Could not resolve {role} data view: '{data_view_input}'"),
            file=sys.stderr,
        )
        sys.exit(1)

    if len(resolved_ids) == 1:
        return resolved_ids[0]

    options = [(dv_id, f"{data_view_input} ({dv_id})") for dv_id in resolved_ids]
    selected = generator.prompt_for_selection(
        options,
        f"{role.capitalize()} name '{data_view_input}' matches {len(resolved_ids)} data views. Please select one:",
    )
    if selected:
        return selected

    print(
        generator.ConsoleColors.error(
            f"ERROR: {role.capitalize()} name '{data_view_input}' is ambiguous - matches {len(resolved_ids)} data views:",
        ),
        file=sys.stderr,
    )
    for dv_id in resolved_ids:
        print(f"  • {dv_id}", file=sys.stderr)
    print("\nPlease specify the exact data view ID instead of the name.", file=sys.stderr)
    sys.exit(1)


def dispatch_cross_data_view_diff_cli_mode(
    args: argparse.Namespace,
    *,
    data_view_inputs: list[str],
    ignore_fields: list[str] | None,
    labels: tuple[str, str] | None,
    show_only: list[str] | None,
    keep_last_specified: bool,
    keep_since_specified: bool,
    run_state: dict[str, Any] | None = None,
) -> None:
    """Handle the cross-data-view ``--diff`` CLI branch and exit."""
    generator = _generator_module()

    if len(data_view_inputs) != 2:
        print(generator.ConsoleColors.error("ERROR: --diff requires exactly 2 data view IDs or names"), file=sys.stderr)
        print("Usage: cja_auto_sdr --diff DATA_VIEW_A DATA_VIEW_B", file=sys.stderr)
        sys.exit(1)

    if getattr(args, "metrics_only", False) and getattr(args, "dimensions_only", False):
        print(
            generator.ConsoleColors.error("ERROR: Cannot use both --metrics-only and --dimensions-only"),
            file=sys.stderr,
        )
        sys.exit(1)

    inventory_flag_errors = (
        (
            getattr(args, "include_derived_inventory", False),
            "ERROR: --include-derived cannot be used with --diff (cross-data-view comparison)",
        ),
        (
            getattr(args, "include_calculated_metrics", False),
            "ERROR: --include-calculated cannot be used with --diff (cross-data-view comparison)",
        ),
        (
            getattr(args, "include_segments_inventory", False),
            "ERROR: --include-segments cannot be used with --diff (cross-data-view comparison)",
        ),
    )
    for enabled, message in inventory_flag_errors:
        if enabled:
            print(generator.ConsoleColors.error(message), file=sys.stderr)
            print(
                "Inventory IDs are data-view-scoped and cannot be matched across different data views.",
                file=sys.stderr,
            )
            print(
                "For same-data-view comparisons, use: --diff-snapshot, --compare-snapshots, or --compare-with-prev",
                file=sys.stderr,
            )
            sys.exit(1)

    if getattr(args, "inventory_only", False):
        print(
            generator.ConsoleColors.error("ERROR: --inventory-only is only available in SDR mode, not with --diff"),
            file=sys.stderr,
        )
        sys.exit(1)

    resolved_ids = [
        _resolve_diff_input_or_exit(data_view_inputs[0], args=args, role="source"),
        _resolve_diff_input_or_exit(data_view_inputs[1], args=args, role="target"),
    ]
    if run_state is not None:
        run_state["resolved_data_views"] = list(resolved_ids)

    diff_format = args.format or "console"
    success, has_changes, exit_code_override = generator.handle_diff_command(
        source_id=resolved_ids[0],
        target_id=resolved_ids[1],
        config_file=args.config_file,
        output_format=diff_format,
        output_dir=args.output_dir,
        changes_only=getattr(args, "changes_only", False),
        summary_only=getattr(args, "summary", False),
        ignore_fields=ignore_fields,
        labels=labels,
        quiet=args.quiet,
        show_only=show_only,
        metrics_only=getattr(args, "metrics_only", False),
        dimensions_only=getattr(args, "dimensions_only", False),
        extended_fields=getattr(args, "extended_fields", False),
        side_by_side=getattr(args, "side_by_side", False),
        no_color=getattr(args, "no_color", False),
        quiet_diff=getattr(args, "quiet_diff", False),
        reverse_diff=getattr(args, "reverse_diff", False),
        warn_threshold=getattr(args, "warn_threshold", None),
        group_by_field=getattr(args, "group_by_field", False),
        group_by_field_limit=getattr(args, "group_by_field_limit", 10),
        diff_output=getattr(args, "diff_output", None),
        format_pr_comment=getattr(args, "format_pr_comment", False),
        auto_snapshot=getattr(args, "auto_snapshot", False),
        auto_prune=getattr(args, "auto_prune", False),
        snapshot_dir=getattr(args, "snapshot_dir", "./snapshots"),
        keep_last=getattr(args, "keep_last", 0),
        keep_since=getattr(args, "keep_since", None),
        keep_last_specified=keep_last_specified,
        keep_since_specified=keep_since_specified,
        profile=getattr(args, "profile", None),
    )
    if run_state is not None:
        run_state["output_format"] = diff_format
        run_state["details"] = {
            "operation_success": success,
            "has_changes": has_changes,
            "warn_threshold_exit_code": exit_code_override,
        }

    _exit_with_diff_result(
        success=success,
        has_changes=has_changes,
        exit_code_override=exit_code_override,
    )


def dispatch_snapshot_cli_modes(
    args: argparse.Namespace,
    *,
    data_view_inputs: list[str],
    output_to_stdout: bool,
    ignore_fields: list[str] | None,
    labels: tuple[str, str] | None,
    show_only: list[str] | None,
    keep_last_specified: bool,
    keep_since_specified: bool,
    run_state: dict[str, Any] | None = None,
) -> list[str]:
    """Handle snapshot/diff CLI branches that still exit directly from main."""
    generator = _generator_module()

    if getattr(args, "list_snapshots", False):
        if data_view_inputs and any(not generator.is_data_view_id(dv) for dv in data_view_inputs):
            generator._exit_error("--list-snapshots filters only support DATA_VIEW_ID values (e.g., dv_12345)")

        snapshot_manager = generator.SnapshotManager()
        snapshots = snapshot_manager.list_snapshots(getattr(args, "snapshot_dir", "./snapshots"))
        if data_view_inputs:
            selected_ids = set(data_view_inputs)
            snapshots = [s for s in snapshots if s.get("data_view_id") in selected_ids]

        list_output_format = args.format if args.format in ("json", "csv") else "table"
        if output_to_stdout and list_output_format == "table":
            list_output_format = "json"

        if list_output_format == "json":
            payload = {
                "snapshot_dir": str(getattr(args, "snapshot_dir", "./snapshots")),
                "count": len(snapshots),
                "snapshots": snapshots,
            }
            generator._emit_json_output(
                payload,
                output_file=getattr(args, "output", None),
                is_stdout=output_to_stdout,
                contract_label="Snapshot listing output",
            )
        elif list_output_format == "csv":
            rows = [
                {
                    "data_view_id": s.get("data_view_id", ""),
                    "data_view_name": s.get("data_view_name", ""),
                    "created_at": s.get("created_at", ""),
                    "metrics_count": s.get("metrics_count", 0),
                    "dimensions_count": s.get("dimensions_count", 0),
                    "filepath": s.get("filepath", ""),
                }
                for s in snapshots
            ]
            generator._emit_output(
                generator._format_as_csv(
                    ["data_view_id", "data_view_name", "created_at", "metrics_count", "dimensions_count", "filepath"],
                    rows,
                ),
                getattr(args, "output", None),
                output_to_stdout,
            )
        else:
            if snapshots:
                table_rows = [
                    {
                        "data_view_id": s.get("data_view_id", ""),
                        "data_view_name": s.get("data_view_name", ""),
                        "created_at": s.get("created_at", ""),
                        "filepath": Path(str(s.get("filepath", ""))).name,
                    }
                    for s in snapshots
                ]
                table_text = generator._format_as_table(
                    f"Found {len(table_rows)} snapshot(s) in {getattr(args, 'snapshot_dir', './snapshots')}:",
                    table_rows,
                    columns=["data_view_id", "data_view_name", "created_at", "filepath"],
                    col_labels=["Data View ID", "Data View Name", "Created", "File"],
                )
            else:
                table_text = f"\nNo snapshots found in {getattr(args, 'snapshot_dir', './snapshots')}.\n"
            generator._emit_output(table_text, getattr(args, "output", None), output_to_stdout)

        if run_state is not None:
            run_state["output_format"] = list_output_format
            run_state["details"] = {"operation_success": True, "snapshot_count": len(snapshots)}
            if data_view_inputs:
                run_state["resolved_data_views"] = list(data_view_inputs)
        sys.exit(0)

    if getattr(args, "prune_snapshots", False):
        if data_view_inputs and any(not generator.is_data_view_id(dv) for dv in data_view_inputs):
            generator._exit_error("--prune-snapshots filters only support DATA_VIEW_ID values (e.g., dv_12345)")

        snapshot_dir = getattr(args, "snapshot_dir", "./snapshots")
        snapshot_manager = generator.SnapshotManager()
        existing_snapshots = snapshot_manager.list_snapshots(snapshot_dir)
        available_ids = sorted({s.get("data_view_id", "") for s in existing_snapshots if s.get("data_view_id")})
        target_ids = list(data_view_inputs) if data_view_inputs else available_ids

        effective_keep_last, effective_keep_since = generator.resolve_auto_prune_retention(
            keep_last=getattr(args, "keep_last", 0),
            keep_since=getattr(args, "keep_since", None),
            auto_prune=getattr(args, "auto_prune", False),
            keep_last_specified=keep_last_specified,
            keep_since_specified=keep_since_specified,
        )
        if effective_keep_last <= 0 and not effective_keep_since:
            generator._exit_error(
                "--prune-snapshots requires --keep-last and/or --keep-since (or use --auto-prune for defaults)"
            )

        keep_since_days = None
        if effective_keep_since:
            keep_since_days = generator.parse_retention_period(effective_keep_since)
            if keep_since_days is None:
                generator._exit_error(f"Invalid --keep-since value: {effective_keep_since}")

        deleted_paths: list[str] = []
        if effective_keep_last > 0:
            for dv_id in target_ids:
                deleted_paths.extend(snapshot_manager.apply_retention_policy(snapshot_dir, dv_id, effective_keep_last))

        if keep_since_days is not None:
            if target_ids:
                for dv_id in target_ids:
                    deleted_paths.extend(
                        snapshot_manager.apply_date_retention_policy(
                            snapshot_dir,
                            dv_id,
                            keep_since_days=keep_since_days,
                        ),
                    )
            else:
                deleted_paths.extend(
                    snapshot_manager.apply_date_retention_policy(snapshot_dir, "*", keep_since_days=keep_since_days),
                )

        unique_deleted = sorted(set(deleted_paths))
        prune_output_format = args.format if args.format in ("json", "csv") else "table"
        if output_to_stdout and prune_output_format == "table":
            prune_output_format = "json"

        if prune_output_format == "json":
            payload = {
                "snapshot_dir": str(snapshot_dir),
                "deleted_count": len(unique_deleted),
                "deleted_files": unique_deleted,
                "target_data_view_ids": target_ids,
                "retention": {"keep_last": effective_keep_last, "keep_since": effective_keep_since},
            }
            generator._emit_json_output(
                payload,
                output_file=getattr(args, "output", None),
                is_stdout=output_to_stdout,
                contract_label="Snapshot prune output",
            )
        elif prune_output_format == "csv":
            rows = [{"filepath": path} for path in unique_deleted]
            generator._emit_output(
                generator._format_as_csv(["filepath"], rows),
                getattr(args, "output", None),
                output_to_stdout,
            )
        else:
            lines = [
                "",
                f"Snapshot prune complete for {snapshot_dir}",
                f"Deleted files: {len(unique_deleted)}",
                f"Retention keep_last: {effective_keep_last}",
                f"Retention keep_since: {effective_keep_since or '-'}",
            ]
            if target_ids:
                lines.append(f"Target data views: {', '.join(target_ids)}")
            if unique_deleted:
                lines.extend(["", "Deleted files:"])
                lines.extend([f"  - {Path(path).name}" for path in unique_deleted])
            lines.append("")
            generator._emit_output("\n".join(lines), getattr(args, "output", None), output_to_stdout)

        if run_state is not None:
            run_state["output_format"] = prune_output_format
            run_state["details"] = {
                "operation_success": True,
                "deleted_count": len(unique_deleted),
                "retention": {"keep_last": effective_keep_last, "keep_since": effective_keep_since},
            }
            run_state["resolved_data_views"] = list(target_ids)
        sys.exit(0)

    if hasattr(args, "compare_snapshots") and args.compare_snapshots:
        source_file, target_file = args.compare_snapshots

        if getattr(args, "metrics_only", False) and getattr(args, "dimensions_only", False):
            print(
                generator.ConsoleColors.error("ERROR: Cannot use both --metrics-only and --dimensions-only"),
                file=sys.stderr,
            )
            sys.exit(1)

        if getattr(args, "inventory_only", False):
            print(
                generator.ConsoleColors.error(
                    "ERROR: --inventory-only is only available in SDR mode, not with --compare-snapshots",
                ),
                file=sys.stderr,
            )
            sys.exit(1)

        diff_format = args.format or "console"
        success, has_changes, exit_code_override = generator.handle_compare_snapshots_command(
            source_file=source_file,
            target_file=target_file,
            output_format=diff_format,
            output_dir=args.output_dir,
            changes_only=getattr(args, "changes_only", False),
            summary_only=getattr(args, "summary", False),
            ignore_fields=ignore_fields,
            labels=labels,
            quiet=args.quiet,
            show_only=show_only,
            metrics_only=getattr(args, "metrics_only", False),
            dimensions_only=getattr(args, "dimensions_only", False),
            extended_fields=getattr(args, "extended_fields", False),
            side_by_side=getattr(args, "side_by_side", False),
            no_color=getattr(args, "no_color", False),
            quiet_diff=getattr(args, "quiet_diff", False),
            reverse_diff=getattr(args, "reverse_diff", False),
            warn_threshold=getattr(args, "warn_threshold", None),
            group_by_field=getattr(args, "group_by_field", False),
            group_by_field_limit=getattr(args, "group_by_field_limit", 10),
            diff_output=getattr(args, "diff_output", None),
            format_pr_comment=getattr(args, "format_pr_comment", False),
            include_calc_metrics=getattr(args, "include_calculated_metrics", False),
            include_segments=getattr(args, "include_segments_inventory", False),
        )
        if run_state is not None:
            run_state["output_format"] = diff_format
            run_state["details"] = {
                "operation_success": success,
                "has_changes": has_changes,
                "warn_threshold_exit_code": exit_code_override,
            }
        _exit_with_diff_result(
            success=success,
            has_changes=has_changes,
            exit_code_override=exit_code_override,
        )

    if getattr(args, "snapshot", None):
        if getattr(args, "include_derived_inventory", False):
            print(
                generator.ConsoleColors.error("ERROR: --include-derived cannot be used with --snapshot"),
                file=sys.stderr,
            )
            print("Derived fields inventory is only available in SDR generation mode.", file=sys.stderr)
            print("Derived field changes are captured in the standard Metrics/Dimensions diff.", file=sys.stderr)
            sys.exit(1)

        resolved_ids = _resolve_single_data_view_id_or_exit(
            data_view_inputs,
            args=args,
            command_name="--snapshot",
            usage="Usage: cja_auto_sdr DATA_VIEW --snapshot ./snapshots/baseline.json",
        )

        success = generator.handle_snapshot_command(
            data_view_id=resolved_ids[0],
            snapshot_file=args.snapshot,
            config_file=args.config_file,
            quiet=args.quiet,
            profile=getattr(args, "profile", None),
            include_calculated_metrics=getattr(args, "include_calculated_metrics", False),
            include_segments=getattr(args, "include_segments_inventory", False),
        )
        if run_state is not None:
            run_state["resolved_data_views"] = list(resolved_ids)
            run_state["details"] = {"operation_success": success}
        sys.exit(0 if success else 1)

    if getattr(args, "compare_with_prev", False):
        if getattr(args, "inventory_only", False):
            print(
                generator.ConsoleColors.error(
                    "ERROR: --inventory-only is only available in SDR mode, not with --compare-with-prev",
                ),
                file=sys.stderr,
            )
            sys.exit(1)

        data_view_inputs = _resolve_single_data_view_id_or_exit(
            data_view_inputs,
            args=args,
            command_name="--compare-with-prev",
            usage="Usage: cja_auto_sdr DATA_VIEW --compare-with-prev",
        )

        snapshot_dir = getattr(args, "snapshot_dir", "./snapshots")
        snapshot_mgr = generator.SnapshotManager()
        prev_snapshot = snapshot_mgr.get_most_recent_snapshot(snapshot_dir, data_view_inputs[0])

        if not prev_snapshot:
            print(
                generator.ConsoleColors.error(
                    f"ERROR: No previous snapshots found for data view '{data_view_inputs[0]}' in {snapshot_dir}",
                ),
                file=sys.stderr,
            )
            print(
                f"Create a snapshot first with: cja_auto_sdr {data_view_inputs[0]} --snapshot {snapshot_dir}/baseline.json",
                file=sys.stderr,
            )
            print("Or use --auto-snapshot with --diff to automatically save snapshots.", file=sys.stderr)
            sys.exit(1)

        if not args.quiet:
            print(f"Comparing against previous snapshot: {prev_snapshot}")

        args.diff_snapshot = prev_snapshot

    if hasattr(args, "diff_snapshot") and args.diff_snapshot:
        if getattr(args, "metrics_only", False) and getattr(args, "dimensions_only", False):
            print(
                generator.ConsoleColors.error("ERROR: Cannot use both --metrics-only and --dimensions-only"),
                file=sys.stderr,
            )
            sys.exit(1)

        if getattr(args, "inventory_only", False):
            print(
                generator.ConsoleColors.error(
                    "ERROR: --inventory-only is only available in SDR mode, not with --diff-snapshot"
                ),
                file=sys.stderr,
            )
            sys.exit(1)

        include_calc_metrics = getattr(args, "include_calculated_metrics", False)
        include_segments = getattr(args, "include_segments_inventory", False)
        resolved_ids = _resolve_single_data_view_id_or_exit(
            data_view_inputs,
            args=args,
            command_name="--diff-snapshot",
            usage="Usage: cja_auto_sdr DATA_VIEW --diff-snapshot ./snapshots/baseline.json",
        )

        diff_format = args.format or "console"
        success, has_changes, exit_code_override = generator.handle_diff_snapshot_command(
            data_view_id=resolved_ids[0],
            snapshot_file=args.diff_snapshot,
            config_file=args.config_file,
            output_format=diff_format,
            output_dir=args.output_dir,
            changes_only=getattr(args, "changes_only", False),
            summary_only=getattr(args, "summary", False),
            ignore_fields=ignore_fields,
            labels=labels,
            quiet=args.quiet,
            show_only=show_only,
            metrics_only=getattr(args, "metrics_only", False),
            dimensions_only=getattr(args, "dimensions_only", False),
            extended_fields=getattr(args, "extended_fields", False),
            side_by_side=getattr(args, "side_by_side", False),
            no_color=getattr(args, "no_color", False),
            quiet_diff=getattr(args, "quiet_diff", False),
            reverse_diff=getattr(args, "reverse_diff", False),
            warn_threshold=getattr(args, "warn_threshold", None),
            group_by_field=getattr(args, "group_by_field", False),
            group_by_field_limit=getattr(args, "group_by_field_limit", 10),
            diff_output=getattr(args, "diff_output", None),
            format_pr_comment=getattr(args, "format_pr_comment", False),
            auto_snapshot=getattr(args, "auto_snapshot", False),
            auto_prune=getattr(args, "auto_prune", False),
            snapshot_dir=getattr(args, "snapshot_dir", "./snapshots"),
            keep_last=getattr(args, "keep_last", 0),
            keep_since=getattr(args, "keep_since", None),
            keep_last_specified=keep_last_specified,
            keep_since_specified=keep_since_specified,
            profile=getattr(args, "profile", None),
            include_calc_metrics=include_calc_metrics,
            include_segments=include_segments,
        )
        if run_state is not None:
            run_state["output_format"] = diff_format
            run_state["resolved_data_views"] = list(resolved_ids)
            run_state["details"] = {
                "operation_success": success,
                "has_changes": has_changes,
                "warn_threshold_exit_code": exit_code_override,
            }
        _exit_with_diff_result(
            success=success,
            has_changes=has_changes,
            exit_code_override=exit_code_override,
        )

    return data_view_inputs
