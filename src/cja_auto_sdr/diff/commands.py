"""Snapshot and diff command handlers extracted from generator.py."""

# ruff: noqa: T201

from __future__ import annotations

import logging
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

__all__ = [
    "handle_compare_snapshots_command",
    "handle_diff_command",
    "handle_diff_snapshot_command",
    "handle_snapshot_command",
]


def _generator_module():
    from cja_auto_sdr import generator as _generator

    return _generator


def handle_snapshot_command(
    data_view_id: str,
    snapshot_file: str,
    config_file: str = "config.json",
    quiet: bool = False,
    profile: str | None = None,
    include_calculated_metrics: bool = False,
    include_segments: bool = False,
) -> bool:
    """Handle the --snapshot command to save a data view snapshot."""
    generator = _generator_module()
    try:
        inventory_info = []
        if include_calculated_metrics:
            inventory_info.append("calculated metrics")
        if include_segments:
            inventory_info.append("segments")

        if not quiet:
            print()
            print("=" * generator.BANNER_WIDTH)
            print("CREATING DATA VIEW SNAPSHOT")
            print("=" * generator.BANNER_WIDTH)
            print(f"Data View: {data_view_id}")
            print(f"Output: {snapshot_file}")
            if inventory_info:
                print(f"Including: {', '.join(inventory_info)} inventory")
            print()

        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO if not quiet else logging.WARNING)

        success, source, _ = generator.configure_cjapy(profile=profile, config_file=config_file, logger=logger)
        if not success:
            print(generator.ConsoleColors.error(f"ERROR: Configuration failed: {source}"), file=sys.stderr)
            return False
        cja = generator.cjapy.CJA()

        snapshot_manager = generator.SnapshotManager(logger)
        snapshot = snapshot_manager.create_snapshot(
            cja,
            data_view_id,
            quiet,
            include_calculated_metrics=include_calculated_metrics,
            include_segments=include_segments,
        )
        saved_path = snapshot_manager.save_snapshot(snapshot, snapshot_file)

        if not quiet:
            print()
            print("=" * generator.BANNER_WIDTH)
            print(generator.ConsoleColors.success("SNAPSHOT CREATED SUCCESSFULLY"))
            print("=" * generator.BANNER_WIDTH)
            print(f"Data View: {snapshot.data_view_name} ({snapshot.data_view_id})")
            print(f"Metrics: {len(snapshot.metrics)}")
            print(f"Dimensions: {len(snapshot.dimensions)}")
            if snapshot.calculated_metrics_inventory is not None:
                print(f"Calculated Metrics: {len(snapshot.calculated_metrics_inventory)}")
            if snapshot.segments_inventory is not None:
                print(f"Segments: {len(snapshot.segments_inventory)}")
            print(f"Snapshot Version: {snapshot.snapshot_version}")
            print(f"Saved to: {saved_path}")
            print("=" * generator.BANNER_WIDTH)

        return True
    except KeyboardInterrupt, SystemExit:
        raise
    except generator.RECOVERABLE_COMMAND_HANDLER_EXCEPTIONS as e:
        print(generator.ConsoleColors.error(f"ERROR: Failed to create snapshot: {e!s}"), file=sys.stderr)
        return False


def handle_diff_command(
    source_id: str,
    target_id: str,
    config_file: str = "config.json",
    output_format: str = "console",
    output_dir: str = ".",
    changes_only: bool = False,
    summary_only: bool = False,
    ignore_fields: list[str] | None = None,
    labels: tuple[str, str] | None = None,
    quiet: bool = False,
    show_only: list[str] | None = None,
    metrics_only: bool = False,
    dimensions_only: bool = False,
    extended_fields: bool = False,
    side_by_side: bool = False,
    no_color: bool = False,
    quiet_diff: bool = False,
    reverse_diff: bool = False,
    warn_threshold: float | None = None,
    group_by_field: bool = False,
    group_by_field_limit: int = 10,
    diff_output: str | None = None,
    format_pr_comment: bool = False,
    auto_snapshot: bool = False,
    auto_prune: bool = False,
    snapshot_dir: str = "./snapshots",
    keep_last: int = 0,
    keep_since: str | None = None,
    keep_last_specified: bool = False,
    keep_since_specified: bool = False,
    profile: str | None = None,
    diff_config=None,
) -> tuple[bool, bool, int | None]:
    """Handle the --diff command to compare two data views."""
    generator = _generator_module()
    if diff_config is None:
        diff_config = generator.DiffConfig(
            source_id=source_id,
            target_id=target_id,
            config_file=config_file,
            output_format=output_format,
            output_dir=output_dir,
            changes_only=changes_only,
            summary_only=summary_only,
            ignore_fields=ignore_fields,
            labels=labels,
            quiet=quiet,
            show_only=show_only,
            metrics_only=metrics_only,
            dimensions_only=dimensions_only,
            extended_fields=extended_fields,
            side_by_side=side_by_side,
            no_color=no_color,
            quiet_diff=quiet_diff,
            reverse_diff=reverse_diff,
            warn_threshold=warn_threshold,
            group_by_field=group_by_field,
            group_by_field_limit=group_by_field_limit,
            diff_output=diff_output,
            format_pr_comment=format_pr_comment,
            auto_snapshot=auto_snapshot,
            auto_prune=auto_prune,
            snapshot_dir=snapshot_dir,
            keep_last=keep_last,
            keep_since=keep_since,
            keep_last_specified=keep_last_specified,
            keep_since_specified=keep_since_specified,
            profile=profile,
        )

    source_id = diff_config.source_id
    target_id = diff_config.target_id
    config_file = diff_config.config_file
    output_format = diff_config.output_format
    output_dir = diff_config.output_dir
    changes_only = diff_config.changes_only
    summary_only = diff_config.summary_only
    ignore_fields = diff_config.ignore_fields
    labels = diff_config.labels
    quiet = diff_config.quiet
    show_only = diff_config.show_only
    metrics_only = diff_config.metrics_only
    dimensions_only = diff_config.dimensions_only
    extended_fields = diff_config.extended_fields
    side_by_side = diff_config.side_by_side
    no_color = diff_config.no_color
    quiet_diff = diff_config.quiet_diff
    reverse_diff = diff_config.reverse_diff
    warn_threshold = diff_config.warn_threshold
    group_by_field = diff_config.group_by_field
    group_by_field_limit = diff_config.group_by_field_limit
    diff_output = diff_config.diff_output
    format_pr_comment = diff_config.format_pr_comment
    auto_snapshot = diff_config.auto_snapshot
    auto_prune = diff_config.auto_prune
    snapshot_dir = diff_config.snapshot_dir
    keep_last = diff_config.keep_last
    keep_since = diff_config.keep_since
    keep_last_specified = diff_config.keep_last_specified
    keep_since_specified = diff_config.keep_since_specified
    profile = diff_config.profile

    try:
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO if not quiet else logging.WARNING)

        if reverse_diff:
            source_id, target_id = target_id, source_id

        if not quiet and not quiet_diff:
            print()
            print("=" * generator.BANNER_WIDTH)
            print("COMPARING DATA VIEWS")
            print("=" * generator.BANNER_WIDTH)
            print(f"Source: {source_id}")
            print(f"Target: {target_id}")
            if reverse_diff:
                print("(Reversed comparison)")
            print()

        success, source, _ = generator.configure_cjapy(profile=profile, config_file=config_file, logger=logger)
        if not success:
            if not quiet and not quiet_diff:
                print(generator.ConsoleColors.error(f"ERROR: Configuration failed: {source}"), file=sys.stderr)
            return False, False, None
        cja = generator.cjapy.CJA()

        snapshot_manager = generator.SnapshotManager(logger)
        if not quiet and not quiet_diff:
            print("Fetching source data view...")
        source_snapshot = snapshot_manager.create_snapshot(cja, source_id, quiet or quiet_diff)
        if not quiet and not quiet_diff:
            print("Fetching target data view...")
        target_snapshot = snapshot_manager.create_snapshot(cja, target_id, quiet or quiet_diff)

        if auto_snapshot:
            os.makedirs(snapshot_dir, exist_ok=True)
            effective_keep_last, effective_keep_since = generator.resolve_auto_prune_retention(
                keep_last=keep_last,
                keep_since=keep_since,
                auto_prune=auto_prune,
                keep_last_specified=keep_last_specified,
                keep_since_specified=keep_since_specified,
            )

            source_filename = snapshot_manager.generate_snapshot_filename(source_id, source_snapshot.data_view_name)
            target_filename = snapshot_manager.generate_snapshot_filename(target_id, target_snapshot.data_view_name)
            snapshot_manager.save_snapshot(source_snapshot, os.path.join(snapshot_dir, source_filename))
            snapshot_manager.save_snapshot(target_snapshot, os.path.join(snapshot_dir, target_filename))

            if not quiet and not quiet_diff:
                print(f"Auto-saved snapshots to: {snapshot_dir}/")
                print(f"  - {source_filename}")
                print(f"  - {target_filename}")

            total_deleted = 0
            if effective_keep_last > 0:
                total_deleted += len(
                    snapshot_manager.apply_retention_policy(snapshot_dir, source_id, effective_keep_last)
                )
                total_deleted += len(
                    snapshot_manager.apply_retention_policy(snapshot_dir, target_id, effective_keep_last)
                )
            if effective_keep_since:
                days = generator.parse_retention_period(effective_keep_since)
                if days:
                    total_deleted += len(
                        snapshot_manager.apply_date_retention_policy(snapshot_dir, source_id, keep_since_days=days)
                    )
                    total_deleted += len(
                        snapshot_manager.apply_date_retention_policy(snapshot_dir, target_id, keep_since_days=days)
                    )
            if total_deleted > 0 and not quiet and not quiet_diff:
                print(f"  Retention policy: Deleted {total_deleted} old snapshot(s)")
            if not quiet and not quiet_diff:
                print()

        source_label = labels[0] if labels else "Source"
        target_label = labels[1] if labels else "Target"
        comparator = generator.DataViewComparator(
            logger,
            ignore_fields=ignore_fields,
            use_extended_fields=extended_fields,
            show_only=show_only,
            metrics_only=metrics_only,
            dimensions_only=dimensions_only,
        )
        diff_result = comparator.compare(source_snapshot, target_snapshot, source_label, target_label)

        exit_code_override = None
        if warn_threshold is not None:
            max_change_pct = max(
                diff_result.summary.metrics_change_percent,
                diff_result.summary.dimensions_change_percent,
            )
            if max_change_pct > warn_threshold:
                exit_code_override = 3
                if not quiet_diff:
                    print(
                        generator.ConsoleColors.warning(
                            f"WARNING: Change threshold exceeded! {max_change_pct:.1f}% > {warn_threshold}%"
                        ),
                        file=sys.stderr,
                    )

        if not quiet_diff:
            effective_format = "pr-comment" if format_pr_comment else output_format
            base_filename = f"diff_{source_id}_{target_id}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
            output_content = generator.write_diff_output(
                diff_result,
                effective_format,
                base_filename,
                output_dir,
                logger,
                changes_only,
                summary_only,
                side_by_side,
                use_color=generator.ConsoleColors.is_enabled() and not no_color,
                group_by_field=group_by_field,
                group_by_field_limit=group_by_field_limit,
            )
            if diff_output and output_content:
                with open(diff_output, "w", encoding="utf-8") as f:
                    f.write(output_content)
                if not quiet:
                    print(f"Diff output written to: {diff_output}")
            if not quiet and output_format != "console":
                print()
                print(generator.ConsoleColors.success("Diff report generated successfully"))

        generator.append_github_step_summary(generator.build_diff_step_summary(diff_result), logger)
        return True, diff_result.summary.has_changes, exit_code_override
    except KeyboardInterrupt, SystemExit:
        raise
    except generator.RECOVERABLE_COMMAND_HANDLER_EXCEPTIONS as e:
        print(generator.ConsoleColors.error(f"ERROR: Failed to compare data views: {e!s}"), file=sys.stderr)
        logger.debug("Diff comparison failed", exc_info=True)
        return False, False, None


def handle_diff_snapshot_command(
    data_view_id: str,
    snapshot_file: str,
    config_file: str = "config.json",
    output_format: str = "console",
    output_dir: str = ".",
    changes_only: bool = False,
    summary_only: bool = False,
    ignore_fields: list[str] | None = None,
    labels: tuple[str, str] | None = None,
    quiet: bool = False,
    show_only: list[str] | None = None,
    metrics_only: bool = False,
    dimensions_only: bool = False,
    extended_fields: bool = False,
    side_by_side: bool = False,
    no_color: bool = False,
    quiet_diff: bool = False,
    reverse_diff: bool = False,
    warn_threshold: float | None = None,
    group_by_field: bool = False,
    group_by_field_limit: int = 10,
    diff_output: str | None = None,
    format_pr_comment: bool = False,
    auto_snapshot: bool = False,
    auto_prune: bool = False,
    snapshot_dir: str = "./snapshots",
    keep_last: int = 0,
    keep_since: str | None = None,
    keep_last_specified: bool = False,
    keep_since_specified: bool = False,
    profile: str | None = None,
    include_calc_metrics: bool = False,
    include_segments: bool = False,
    diff_snapshot_config=None,
) -> tuple[bool, bool, int | None]:
    """Handle the --diff-snapshot command to compare a data view against a saved snapshot."""
    generator = _generator_module()
    if diff_snapshot_config is None:
        diff_snapshot_config = generator.DiffSnapshotConfig(
            data_view_id=data_view_id,
            snapshot_file=snapshot_file,
            config_file=config_file,
            output_format=output_format,
            output_dir=output_dir,
            changes_only=changes_only,
            summary_only=summary_only,
            ignore_fields=ignore_fields,
            labels=labels,
            quiet=quiet,
            show_only=show_only,
            metrics_only=metrics_only,
            dimensions_only=dimensions_only,
            extended_fields=extended_fields,
            side_by_side=side_by_side,
            no_color=no_color,
            quiet_diff=quiet_diff,
            reverse_diff=reverse_diff,
            warn_threshold=warn_threshold,
            group_by_field=group_by_field,
            group_by_field_limit=group_by_field_limit,
            diff_output=diff_output,
            format_pr_comment=format_pr_comment,
            auto_snapshot=auto_snapshot,
            auto_prune=auto_prune,
            snapshot_dir=snapshot_dir,
            keep_last=keep_last,
            keep_since=keep_since,
            keep_last_specified=keep_last_specified,
            keep_since_specified=keep_since_specified,
            profile=profile,
            include_calc_metrics=include_calc_metrics,
            include_segments=include_segments,
        )

    data_view_id = diff_snapshot_config.data_view_id
    snapshot_file = diff_snapshot_config.snapshot_file
    config_file = diff_snapshot_config.config_file
    output_format = diff_snapshot_config.output_format
    output_dir = diff_snapshot_config.output_dir
    changes_only = diff_snapshot_config.changes_only
    summary_only = diff_snapshot_config.summary_only
    ignore_fields = diff_snapshot_config.ignore_fields
    labels = diff_snapshot_config.labels
    quiet = diff_snapshot_config.quiet
    show_only = diff_snapshot_config.show_only
    metrics_only = diff_snapshot_config.metrics_only
    dimensions_only = diff_snapshot_config.dimensions_only
    extended_fields = diff_snapshot_config.extended_fields
    side_by_side = diff_snapshot_config.side_by_side
    no_color = diff_snapshot_config.no_color
    quiet_diff = diff_snapshot_config.quiet_diff
    reverse_diff = diff_snapshot_config.reverse_diff
    warn_threshold = diff_snapshot_config.warn_threshold
    group_by_field = diff_snapshot_config.group_by_field
    group_by_field_limit = diff_snapshot_config.group_by_field_limit
    diff_output = diff_snapshot_config.diff_output
    format_pr_comment = diff_snapshot_config.format_pr_comment
    auto_snapshot = diff_snapshot_config.auto_snapshot
    auto_prune = diff_snapshot_config.auto_prune
    snapshot_dir = diff_snapshot_config.snapshot_dir
    keep_last = diff_snapshot_config.keep_last
    keep_since = diff_snapshot_config.keep_since
    keep_last_specified = diff_snapshot_config.keep_last_specified
    keep_since_specified = diff_snapshot_config.keep_since_specified
    profile = diff_snapshot_config.profile
    include_calc_metrics = diff_snapshot_config.include_calc_metrics
    include_segments = diff_snapshot_config.include_segments

    try:
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO if not quiet else logging.WARNING)

        if not quiet and not quiet_diff:
            print()
            print("=" * generator.BANNER_WIDTH)
            print("COMPARING DATA VIEW AGAINST SNAPSHOT")
            print("=" * generator.BANNER_WIDTH)
            print(f"Data View: {data_view_id}")
            print(f"Snapshot: {snapshot_file}")
            if reverse_diff:
                print("(Reversed comparison)")
            if include_calc_metrics or include_segments:
                inv_types = []
                if include_calc_metrics:
                    inv_types.append("calculated metrics")
                if include_segments:
                    inv_types.append("segments")
                print(f"Including inventory: {', '.join(inv_types)}")
            print()

        snapshot_manager = generator.SnapshotManager(logger)
        source_snapshot = snapshot_manager.load_snapshot(snapshot_file)

        missing_inventory = []
        if include_calc_metrics and not source_snapshot.has_calculated_metrics_inventory:
            missing_inventory.append("calculated metrics")
        if include_segments and not source_snapshot.has_segments_inventory:
            missing_inventory.append("segments")

        if missing_inventory:
            inv_summary = source_snapshot.get_inventory_summary()
            print(
                generator.ConsoleColors.error(
                    "ERROR: Cannot perform inventory diff - snapshot missing requested data."
                ),
                file=sys.stderr,
            )
            print(file=sys.stderr)
            print(f"Snapshot '{snapshot_file}' contains:", file=sys.stderr)
            print(f"  {'✓' if True else '✗'} Metrics ({len(source_snapshot.metrics)} items)", file=sys.stderr)
            print(f"  {'✓' if True else '✗'} Dimensions ({len(source_snapshot.dimensions)} items)", file=sys.stderr)
            print(
                f"  {'✓' if inv_summary['calculated_metrics']['present'] else '✗'} Calculated Metrics Inventory ({inv_summary['calculated_metrics']['count']} items)",
                file=sys.stderr,
            )
            print(
                f"  {'✓' if inv_summary['segments']['present'] else '✗'} Segments Inventory ({inv_summary['segments']['count']} items)",
                file=sys.stderr,
            )
            print(file=sys.stderr)
            print(f"You requested: {', '.join(missing_inventory)}", file=sys.stderr)
            print(file=sys.stderr)
            print("To create a compatible snapshot:", file=sys.stderr)
            flags = []
            if include_calc_metrics:
                flags.append("--include-calculated")
            if include_segments:
                flags.append("--include-segments")
            print(f"  cja_auto_sdr {data_view_id} {' '.join(flags)} --auto-snapshot", file=sys.stderr)
            return False, False, None

        success, source, _ = generator.configure_cjapy(profile=profile, config_file=config_file, logger=logger)
        if not success:
            if not quiet and not quiet_diff:
                print(generator.ConsoleColors.error(f"ERROR: Configuration failed: {source}"), file=sys.stderr)
            return False, False, None
        cja = generator.cjapy.CJA()

        if not quiet and not quiet_diff:
            print("Fetching current data view state...")
        target_snapshot = snapshot_manager.create_snapshot(cja, data_view_id, quiet or quiet_diff)

        if include_calc_metrics or include_segments:
            if not quiet and not quiet_diff:
                print("Building inventory for current state...")

            if include_calc_metrics:
                try:
                    from cja_auto_sdr.inventory.calculated_metrics import CalculatedMetricsInventoryBuilder

                    builder = CalculatedMetricsInventoryBuilder(logger=logger)
                    inventory = builder.build(cja, data_view_id, target_snapshot.data_view_name)
                    target_snapshot.calculated_metrics_inventory = [m.to_full_dict() for m in inventory.metrics]
                    if not quiet and not quiet_diff:
                        print(f"  Calculated metrics: {len(target_snapshot.calculated_metrics_inventory)} items")
                except generator.RECOVERABLE_OPTIONAL_INVENTORY_EXCEPTIONS as e:
                    logger.warning(f"Failed to build calculated metrics inventory: {e}")

            if include_segments:
                try:
                    from cja_auto_sdr.inventory.segments import SegmentsInventoryBuilder

                    builder = SegmentsInventoryBuilder(logger=logger)
                    inventory = builder.build(cja, data_view_id, target_snapshot.data_view_name)
                    target_snapshot.segments_inventory = [s.to_full_dict() for s in inventory.segments]
                    if not quiet and not quiet_diff:
                        print(f"  Segments: {len(target_snapshot.segments_inventory)} items")
                except generator.RECOVERABLE_OPTIONAL_INVENTORY_EXCEPTIONS as e:
                    logger.warning(f"Failed to build segments inventory: {e}")

            if not quiet and not quiet_diff:
                print()

        if auto_snapshot:
            os.makedirs(snapshot_dir, exist_ok=True)
            effective_keep_last, effective_keep_since = generator.resolve_auto_prune_retention(
                keep_last=keep_last,
                keep_since=keep_since,
                auto_prune=auto_prune,
                keep_last_specified=keep_last_specified,
                keep_since_specified=keep_since_specified,
            )

            current_filename = snapshot_manager.generate_snapshot_filename(data_view_id, target_snapshot.data_view_name)
            snapshot_manager.save_snapshot(target_snapshot, os.path.join(snapshot_dir, current_filename))
            if not quiet and not quiet_diff:
                print(f"Auto-saved current state to: {snapshot_dir}/{current_filename}")

            total_deleted = 0
            if effective_keep_last > 0:
                total_deleted += len(
                    snapshot_manager.apply_retention_policy(snapshot_dir, data_view_id, effective_keep_last)
                )
            if effective_keep_since:
                days = generator.parse_retention_period(effective_keep_since)
                if days:
                    total_deleted += len(
                        snapshot_manager.apply_date_retention_policy(snapshot_dir, data_view_id, keep_since_days=days)
                    )
            if total_deleted > 0 and not quiet and not quiet_diff:
                print(f"  Retention policy: Deleted {total_deleted} old snapshot(s)")
            if not quiet and not quiet_diff:
                print()

        if reverse_diff:
            source_snapshot, target_snapshot = target_snapshot, source_snapshot

        source_label = labels[0] if labels else f"Snapshot ({source_snapshot.created_at[:10]})"
        target_label = labels[1] if labels else "Current"
        comparator = generator.DataViewComparator(
            logger,
            ignore_fields=ignore_fields,
            use_extended_fields=extended_fields,
            show_only=show_only,
            metrics_only=metrics_only,
            dimensions_only=dimensions_only,
            include_calc_metrics=include_calc_metrics,
            include_segments=include_segments,
        )
        diff_result = comparator.compare(source_snapshot, target_snapshot, source_label, target_label)

        exit_code_override = None
        if warn_threshold is not None:
            max_change_pct = max(
                diff_result.summary.metrics_change_percent,
                diff_result.summary.dimensions_change_percent,
            )
            if max_change_pct > warn_threshold:
                exit_code_override = 3
                if not quiet_diff:
                    print(
                        generator.ConsoleColors.warning(
                            f"WARNING: Change threshold exceeded! {max_change_pct:.1f}% > {warn_threshold}%"
                        ),
                        file=sys.stderr,
                    )

        if not quiet_diff:
            effective_format = "pr-comment" if format_pr_comment else output_format
            base_filename = f"diff_{data_view_id}_snapshot_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
            output_content = generator.write_diff_output(
                diff_result,
                effective_format,
                base_filename,
                output_dir,
                logger,
                changes_only,
                summary_only,
                side_by_side,
                use_color=generator.ConsoleColors.is_enabled() and not no_color,
                group_by_field=group_by_field,
                group_by_field_limit=group_by_field_limit,
            )
            if diff_output and output_content:
                with open(diff_output, "w", encoding="utf-8") as f:
                    f.write(output_content)
                if not quiet:
                    print(f"Diff output written to: {diff_output}")
            if not quiet and output_format != "console":
                print()
                print(generator.ConsoleColors.success("Diff report generated successfully"))

        generator.append_github_step_summary(generator.build_diff_step_summary(diff_result), logger)
        return True, diff_result.summary.has_changes, exit_code_override
    except FileNotFoundError:
        print(generator.ConsoleColors.error(f"ERROR: Snapshot file not found: {snapshot_file}"), file=sys.stderr)
        return False, False, None
    except ValueError as e:
        print(generator.ConsoleColors.error(f"ERROR: Invalid snapshot file: {e!s}"), file=sys.stderr)
        return False, False, None
    except KeyboardInterrupt, SystemExit:
        raise
    except generator.RECOVERABLE_COMMAND_HANDLER_EXCEPTIONS as e:
        print(generator.ConsoleColors.error(f"ERROR: Failed to compare against snapshot: {e!s}"), file=sys.stderr)
        logger.debug("Diff-snapshot comparison failed", exc_info=True)
        return False, False, None


def handle_compare_snapshots_command(
    source_file: str,
    target_file: str,
    output_format: str = "console",
    output_dir: str = ".",
    changes_only: bool = False,
    summary_only: bool = False,
    ignore_fields: list[str] | None = None,
    labels: tuple[str, str] | None = None,
    quiet: bool = False,
    show_only: list[str] | None = None,
    metrics_only: bool = False,
    dimensions_only: bool = False,
    extended_fields: bool = False,
    side_by_side: bool = False,
    no_color: bool = False,
    quiet_diff: bool = False,
    reverse_diff: bool = False,
    warn_threshold: float | None = None,
    group_by_field: bool = False,
    group_by_field_limit: int = 10,
    diff_output: str | None = None,
    format_pr_comment: bool = False,
    include_calc_metrics: bool = False,
    include_segments: bool = False,
) -> tuple[bool, bool, int | None]:
    """Handle the --compare-snapshots command to compare two snapshot files directly."""
    generator = _generator_module()
    try:
        logger = logging.getLogger(__name__)
        logger.setLevel(logging.INFO if not quiet else logging.WARNING)

        if not quiet and not quiet_diff:
            print()
            print("=" * generator.BANNER_WIDTH)
            print("COMPARING TWO SNAPSHOTS")
            print("=" * generator.BANNER_WIDTH)
            print(f"Source: {source_file}")
            print(f"Target: {target_file}")
            if reverse_diff:
                print("(Reversed comparison)")
            print()

        snapshot_manager = generator.SnapshotManager(logger)
        if not quiet and not quiet_diff:
            print("Loading source snapshot...")
        source_snapshot = snapshot_manager.load_snapshot(source_file)
        if not quiet and not quiet_diff:
            print("Loading target snapshot...")
        target_snapshot = snapshot_manager.load_snapshot(target_file)

        if (include_calc_metrics or include_segments) and source_snapshot.data_view_id != target_snapshot.data_view_id:
            print(
                generator.ConsoleColors.error(
                    "ERROR: Inventory comparison requires snapshots from the same data view."
                ),
                file=sys.stderr,
            )
            print(f"  Source: {source_snapshot.data_view_name} ({source_snapshot.data_view_id})", file=sys.stderr)
            print(f"  Target: {target_snapshot.data_view_name} ({target_snapshot.data_view_id})", file=sys.stderr)
            print(file=sys.stderr)
            print(
                "Inventory IDs are data-view-scoped and cannot be matched across different data views.", file=sys.stderr
            )
            print(
                "Remove --include-segments, --include-calculated, --include-derived for cross-data-view comparison.",
                file=sys.stderr,
            )
            return False, False, None

        if reverse_diff:
            source_snapshot, target_snapshot = target_snapshot, source_snapshot
            source_file, target_file = target_file, source_file

        if labels:
            source_label, target_label = labels
        else:
            source_label = f"{source_snapshot.data_view_name} ({source_snapshot.created_at[:10]})"
            target_label = f"{target_snapshot.data_view_name} ({target_snapshot.created_at[:10]})"

        if not quiet and not quiet_diff:
            print(f"Comparing: {source_label} vs {target_label}")
            print()
            print("Snapshot Details:")
            print("-" * 40)
            source_size = os.path.getsize(source_file)
            source_size_str = f"{source_size:,} bytes" if source_size < 1024 else f"{source_size / 1024:.1f} KB"
            print("  Source:")
            print(f"    File: {Path(source_file).name} ({source_size_str})")
            print(f"    Created: {source_snapshot.created_at}")
            print(f"    Data View: {source_snapshot.data_view_name} ({source_snapshot.data_view_id})")
            print(f"    Metrics: {len(source_snapshot.metrics):,} | Dimensions: {len(source_snapshot.dimensions):,}")
            target_size = os.path.getsize(target_file)
            target_size_str = f"{target_size:,} bytes" if target_size < 1024 else f"{target_size / 1024:.1f} KB"
            print("  Target:")
            print(f"    File: {Path(target_file).name} ({target_size_str})")
            print(f"    Created: {target_snapshot.created_at}")
            print(f"    Data View: {target_snapshot.data_view_name} ({target_snapshot.data_view_id})")
            print(f"    Metrics: {len(target_snapshot.metrics):,} | Dimensions: {len(target_snapshot.dimensions):,}")
            print("-" * 40)
            print()

        comparator = generator.DataViewComparator(
            logger,
            ignore_fields=ignore_fields,
            use_extended_fields=extended_fields,
            show_only=show_only,
            metrics_only=metrics_only,
            dimensions_only=dimensions_only,
            include_calc_metrics=include_calc_metrics,
            include_segments=include_segments,
        )
        diff_result = comparator.compare(source_snapshot, target_snapshot, source_label, target_label)

        exit_code_override = None
        if warn_threshold is not None:
            max_change_pct = max(
                diff_result.summary.metrics_change_percent,
                diff_result.summary.dimensions_change_percent,
            )
            if max_change_pct > warn_threshold:
                exit_code_override = 3
                if not quiet_diff:
                    print(
                        generator.ConsoleColors.warning(
                            f"WARNING: Change threshold exceeded! {max_change_pct:.1f}% > {warn_threshold}%"
                        ),
                        file=sys.stderr,
                    )

        if not quiet_diff:
            effective_format = "pr-comment" if format_pr_comment else output_format
            source_base = Path(source_file).stem
            target_base = Path(target_file).stem
            base_filename = f"diff_{source_base}_vs_{target_base}_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S')}"
            output_content = generator.write_diff_output(
                diff_result,
                effective_format,
                base_filename,
                output_dir,
                logger,
                changes_only,
                summary_only,
                side_by_side,
                use_color=generator.ConsoleColors.is_enabled() and not no_color,
                group_by_field=group_by_field,
                group_by_field_limit=group_by_field_limit,
            )
            if diff_output and output_content:
                with open(diff_output, "w", encoding="utf-8") as f:
                    f.write(output_content)
                if not quiet:
                    print(f"Diff output written to: {diff_output}")
            if not quiet and output_format != "console":
                print()
                print(generator.ConsoleColors.success("Diff report generated successfully"))

        generator.append_github_step_summary(generator.build_diff_step_summary(diff_result), logger)
        return True, diff_result.summary.has_changes, exit_code_override
    except FileNotFoundError as e:
        print(generator.ConsoleColors.error(f"ERROR: Snapshot file not found: {e!s}"), file=sys.stderr)
        return False, False, None
    except ValueError as e:
        print(generator.ConsoleColors.error(f"ERROR: Invalid snapshot file: {e!s}"), file=sys.stderr)
        return False, False, None
    except KeyboardInterrupt, SystemExit:
        raise
    except (generator.CJASDRError, OSError) as e:
        print(generator.ConsoleColors.error(f"ERROR: Failed to compare snapshots: {e!s}"), file=sys.stderr)
        logger.debug("Snapshot comparison failed", exc_info=True)
        return False, False, None
    except Exception as e:
        print(generator.ConsoleColors.error(f"ERROR: Failed to compare snapshots (unexpected): {e!s}"), file=sys.stderr)
        logger.debug("Unexpected snapshot comparison error", exc_info=True)
        return False, False, None
