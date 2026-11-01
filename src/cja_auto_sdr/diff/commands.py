"""Snapshot and diff command handlers extracted from generator.py."""

# ruff: noqa: T201

from __future__ import annotations

import logging
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from cja_auto_sdr.core.colors import ConsoleColors
from cja_auto_sdr.core.exceptions import OutputError
from cja_auto_sdr.core.json_io import write_text_atomic_compatible
from cja_auto_sdr.diff.snapshot import _annotate_snapshot_failure

if TYPE_CHECKING:
    from cja_auto_sdr.diff.models import DiffResult

__all__ = [
    "handle_compare_snapshots_command",
    "handle_diff_command",
    "handle_diff_snapshot_command",
    "handle_snapshot_command",
]


def _generator_module():
    from cja_auto_sdr import generator as _generator

    return _generator


# Diff formats that render exactly one file, so --diff-output can name it.
_SINGLE_FILE_DIFF_FORMATS = frozenset({"json", "markdown", "html", "excel"})


def _write_diff_report(
    render: Callable[[str | Path], str | None],
    *,
    output_format: str,
    output_dir: str | Path,
    diff_output: str | None,
    quiet: bool,
    output_to_stdout: bool,
) -> None:
    """Render a diff report, honoring ``--diff-output`` for every format that can.

    Console and PR-comment output is text and is copied to ``diff_output``.
    Single-file reports render into a staging directory beside ``diff_output``
    and move into place, so the requested path is used even when its
    extension differs from the format. Multi-file formats keep auto-named
    output under ``output_dir`` and say so on stderr.
    """
    if diff_output and not output_to_stdout and output_format in _SINGLE_FILE_DIFF_FORMATS:
        destination = Path(diff_output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        staging_dir = Path(tempfile.mkdtemp(prefix=".diff-", dir=destination.parent))
        try:
            render(staging_dir)
            rendered = [path for path in staging_dir.iterdir() if path.is_file()]
            if len(rendered) != 1:
                raise OutputError(f"Expected one {output_format} diff report, found {len(rendered)}")
            os.replace(rendered[0], destination)
        finally:
            shutil.rmtree(staging_dir, ignore_errors=True)
        if not quiet:
            print(f"Diff output written to: {diff_output}")
        return

    output_content = render(output_dir)
    if diff_output and output_content and output_format != "all":
        # Terminal color codes are for stdout; the file gets plain text.
        write_text_atomic_compatible(diff_output, ConsoleColors.ANSI_ESCAPE.sub("", output_content))
        if not quiet:
            print(f"Diff output written to: {diff_output}")
    elif diff_output and not output_to_stdout:
        print(
            f"Warning: --diff-output does not apply to --format {output_format} (it produces multiple files); "
            f"wrote the report under {output_dir} instead.",
            file=sys.stderr,
        )


def _print_cross_data_view_inventory_error(
    generator: Any,
    source_snapshot: Any,
    target_name: str | None,
    target_id: str,
    *,
    output_format: str = "console",
) -> None:
    """Explain why inventory comparison needs both sides to be the same data view."""
    if output_format == "json":
        generator._emit_discovery_error(
            "Inventory comparison requires snapshots from the same data view",
            is_machine_readable=True,
            error_type="comparison_error",
        )
        return
    print(
        generator.ConsoleColors.error("ERROR: Inventory comparison requires snapshots from the same data view."),
        file=sys.stderr,
    )
    print(f"  Source: {source_snapshot.data_view_name} ({source_snapshot.data_view_id})", file=sys.stderr)
    target_text = f"{target_name} ({target_id})" if target_name else target_id
    print(f"  Target: {target_text}", file=sys.stderr)
    print(file=sys.stderr)
    print("Inventory IDs are data-view-scoped and cannot be matched across different data views.", file=sys.stderr)
    print(
        "Remove --include-segments, --include-calculated, --include-derived for cross-data-view comparison.",
        file=sys.stderr,
    )


def _populate_diff_advisory_rollup(
    runtime_details: dict[str, Any] | None,
    diff_result: DiffResult,
    *,
    changes_only: bool,
) -> None:
    """Compute diff advisory rollup and store it in *runtime_details* if provided.

    This is a best-effort helper — failures are silently ignored so that
    advisory computation never breaks the diff flow.
    """
    if runtime_details is None:
        return
    try:
        from cja_auto_sdr.core.advisory_builders import build_advisory_rollup, build_diff_advisories

        advisory_summary = build_diff_advisories(diff_result, changes_only=changes_only)
        runtime_details["advisory_rollup"] = build_advisory_rollup(advisory_summary)
    except Exception:
        logging.getLogger("diff").debug("Advisory rollup computation failed", exc_info=True)


def _emit_api_failure_hint(generator: Any, exc: Exception) -> None:
    """Print a diff/snapshot API hint to stderr when one is available."""
    generator._print_api_hint(exc, file=sys.stderr)


def _emit_requested_inventory_failure(generator: Any, exc: Exception) -> bool:
    stage = getattr(exc, "_cja_snapshot_failure_stage", None)
    if stage not in {"calculated_metrics_inventory", "segments_inventory", "requested_inventory_validation"}:
        return False
    hint = generator.api_connection_hint(exc)
    generator._emit_discovery_error(
        str(exc),
        is_machine_readable=True,
        error_type="comparison_error",
        additional_fields={"hint": hint} if hint else None,
    )
    return True


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
        try:
            snapshot = snapshot_manager.create_snapshot(
                cja,
                data_view_id,
                quiet,
                include_calculated_metrics=include_calculated_metrics,
                include_segments=include_segments,
            )
        except generator.RECOVERABLE_COMMAND_HANDLER_EXCEPTIONS as e:
            if _emit_requested_inventory_failure(generator, e):
                return False
            print(generator.ConsoleColors.error(f"ERROR: Failed to create snapshot: {e!s}"), file=sys.stderr)
            _emit_api_failure_hint(generator, e)
            return False
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
    except (KeyboardInterrupt, SystemExit):
        raise
    except generator.RECOVERABLE_COMMAND_HANDLER_EXCEPTIONS as e:
        print(generator.ConsoleColors.error(f"ERROR: Failed to create snapshot: {e!s}"), file=sys.stderr)
        _emit_api_failure_hint(generator, e)
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
    include_metadata: bool = False,
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
    output_to_stdout: bool = False,
    runtime_details: dict[str, Any] | None = None,
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
            include_metadata=include_metadata,
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
    include_metadata = diff_config.include_metadata
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
        try:
            if not quiet and not quiet_diff:
                print("Fetching source data view...")
            source_snapshot = snapshot_manager.create_snapshot(cja, source_id, quiet or quiet_diff)
            if not quiet and not quiet_diff:
                print("Fetching target data view...")
            target_snapshot = snapshot_manager.create_snapshot(cja, target_id, quiet or quiet_diff)
        except generator.RECOVERABLE_COMMAND_HANDLER_EXCEPTIONS as e:
            print(generator.ConsoleColors.error(f"ERROR: Failed to compare data views: {e!s}"), file=sys.stderr)
            _emit_api_failure_hint(generator, e)
            logger.debug("Diff comparison failed during data view fetch", exc_info=True)
            return False, False, None

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
            include_metadata=include_metadata,
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
            _write_diff_report(
                lambda directory: generator.write_diff_output(
                    diff_result,
                    effective_format,
                    base_filename,
                    directory,
                    logger,
                    changes_only,
                    summary_only,
                    side_by_side,
                    use_color=generator.ConsoleColors.is_enabled() and not no_color,
                    group_by_field=group_by_field,
                    group_by_field_limit=group_by_field_limit,
                    output_to_stdout=output_to_stdout,
                ),
                output_format=effective_format,
                output_dir=output_dir,
                diff_output=diff_output,
                quiet=quiet,
                output_to_stdout=output_to_stdout,
            )
            if not quiet and output_format != "console" and not output_to_stdout:
                print()
                print(generator.ConsoleColors.success("Diff report generated successfully"))

        generator.append_github_step_summary(generator.build_diff_step_summary(diff_result), logger)
        _populate_diff_advisory_rollup(runtime_details, diff_result, changes_only=changes_only)
        return True, diff_result.summary.has_changes, exit_code_override
    except (KeyboardInterrupt, SystemExit):
        raise
    except generator.RECOVERABLE_COMMAND_HANDLER_EXCEPTIONS as e:
        print(generator.ConsoleColors.error(f"ERROR: Failed to compare data views: {e!s}"), file=sys.stderr)
        _emit_api_failure_hint(generator, e)
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
    include_metadata: bool = False,
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
    output_to_stdout: bool = False,
    runtime_details: dict[str, Any] | None = None,
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
            include_metadata=include_metadata,
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
    include_metadata = diff_snapshot_config.include_metadata
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

        if (include_calc_metrics or include_segments) and source_snapshot.data_view_id != data_view_id:
            _print_cross_data_view_inventory_error(
                generator, source_snapshot, None, data_view_id, output_format=output_format
            )
            return False, False, None

        missing_inventory = []
        if include_calc_metrics and not source_snapshot.has_calculated_metrics_inventory:
            missing_inventory.append("calculated metrics")
        if include_segments and not source_snapshot.has_segments_inventory:
            missing_inventory.append("segments")

        if missing_inventory:
            if output_format == "json":
                generator._emit_discovery_error(
                    f"Missing requested {', '.join(missing_inventory)} inventory on source snapshot",
                    is_machine_readable=True,
                    error_type="comparison_error",
                )
                return False, False, None
            inv_summary = source_snapshot.get_inventory_summary()
            print(
                generator.ConsoleColors.error(
                    "ERROR: Cannot perform inventory diff - source snapshot missing requested data."
                ),
                file=sys.stderr,
            )
            print(file=sys.stderr)
            print(f"Snapshot '{snapshot_file}' contains:", file=sys.stderr)
            print(
                f"  {'✓' if source_snapshot.metrics else '✗'} Metrics ({len(source_snapshot.metrics)} items)",
                file=sys.stderr,
            )
            print(
                f"  {'✓' if source_snapshot.dimensions else '✗'} Dimensions ({len(source_snapshot.dimensions)} items)",
                file=sys.stderr,
            )
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
            print(
                f"  cja_auto_sdr {data_view_id} --snapshot ./snapshots/baseline.json {' '.join(flags)}", file=sys.stderr
            )
            return False, False, None

        success, source, _ = generator.configure_cjapy(profile=profile, config_file=config_file, logger=logger)
        if not success:
            if not quiet and not quiet_diff:
                print(generator.ConsoleColors.error(f"ERROR: Configuration failed: {source}"), file=sys.stderr)
            return False, False, None
        cja = generator.cjapy.CJA()

        try:
            if not quiet and not quiet_diff:
                print("Fetching current data view state...")
            target_snapshot = snapshot_manager.create_snapshot(cja, data_view_id, quiet or quiet_diff)
        except generator.RECOVERABLE_COMMAND_HANDLER_EXCEPTIONS as e:
            print(generator.ConsoleColors.error(f"ERROR: Failed to compare against snapshot: {e!s}"), file=sys.stderr)
            _emit_api_failure_hint(generator, e)
            logger.debug("Diff-snapshot comparison failed during data view fetch", exc_info=True)
            return False, False, None

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
                    raise _annotate_snapshot_failure(e, stage="calculated_metrics_inventory") from e

            if include_segments:
                try:
                    from cja_auto_sdr.inventory.segments import SegmentsInventoryBuilder

                    builder = SegmentsInventoryBuilder(logger=logger)
                    inventory = builder.build(cja, data_view_id, target_snapshot.data_view_name)
                    target_snapshot.segments_inventory = [s.to_full_dict() for s in inventory.segments]
                    if not quiet and not quiet_diff:
                        print(f"  Segments: {len(target_snapshot.segments_inventory)} items")
                except generator.RECOVERABLE_OPTIONAL_INVENTORY_EXCEPTIONS as e:
                    raise _annotate_snapshot_failure(e, stage="segments_inventory") from e

            if not quiet and not quiet_diff:
                print()

        comparator = generator.DataViewComparator(
            logger,
            ignore_fields=ignore_fields,
            use_extended_fields=extended_fields,
            include_metadata=include_metadata,
            show_only=show_only,
            metrics_only=metrics_only,
            dimensions_only=dimensions_only,
            include_calc_metrics=include_calc_metrics,
            include_segments=include_segments,
        )
        comparator.validate_requested_inventories(source_snapshot, target_snapshot)

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

        # Default labels belong to the roles before the swap: the saved snapshot is
        # the source and the live data view is the target. They swap with the snapshots.
        source_label = f"Snapshot ({source_snapshot.created_at[:10]})"
        target_label = "Current"
        if reverse_diff:
            source_snapshot, target_snapshot = target_snapshot, source_snapshot
            source_label, target_label = target_label, source_label
        if labels:
            source_label, target_label = labels
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
            _write_diff_report(
                lambda directory: generator.write_diff_output(
                    diff_result,
                    effective_format,
                    base_filename,
                    directory,
                    logger,
                    changes_only,
                    summary_only,
                    side_by_side,
                    use_color=generator.ConsoleColors.is_enabled() and not no_color,
                    group_by_field=group_by_field,
                    group_by_field_limit=group_by_field_limit,
                    output_to_stdout=output_to_stdout,
                ),
                output_format=effective_format,
                output_dir=output_dir,
                diff_output=diff_output,
                quiet=quiet,
                output_to_stdout=output_to_stdout,
            )
            if not quiet and output_format != "console" and not output_to_stdout:
                print()
                print(generator.ConsoleColors.success("Diff report generated successfully"))

        generator.append_github_step_summary(generator.build_diff_step_summary(diff_result), logger)
        _populate_diff_advisory_rollup(runtime_details, diff_result, changes_only=changes_only)
        return True, diff_result.summary.has_changes, exit_code_override
    except FileNotFoundError as e:
        if _emit_requested_inventory_failure(generator, e):
            return False, False, None
        print(generator.ConsoleColors.error(f"ERROR: Snapshot file not found: {snapshot_file}"), file=sys.stderr)
        return False, False, None
    except ValueError as e:
        if _emit_requested_inventory_failure(generator, e):
            return False, False, None
        print(generator.ConsoleColors.error(f"ERROR: Invalid snapshot file: {e!s}"), file=sys.stderr)
        return False, False, None
    except (KeyboardInterrupt, SystemExit):
        raise
    except generator.RECOVERABLE_COMMAND_HANDLER_EXCEPTIONS as e:
        if _emit_requested_inventory_failure(generator, e):
            return False, False, None
        print(generator.ConsoleColors.error(f"ERROR: Failed to compare against snapshot: {e!s}"), file=sys.stderr)
        _emit_api_failure_hint(generator, e)
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
    include_metadata: bool = False,
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
    output_to_stdout: bool = False,
    runtime_details: dict[str, Any] | None = None,
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
            _print_cross_data_view_inventory_error(
                generator,
                source_snapshot,
                target_snapshot.data_view_name,
                target_snapshot.data_view_id,
                output_format=output_format,
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
            include_metadata=include_metadata,
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
            _write_diff_report(
                lambda directory: generator.write_diff_output(
                    diff_result,
                    effective_format,
                    base_filename,
                    directory,
                    logger,
                    changes_only,
                    summary_only,
                    side_by_side,
                    use_color=generator.ConsoleColors.is_enabled() and not no_color,
                    group_by_field=group_by_field,
                    group_by_field_limit=group_by_field_limit,
                    output_to_stdout=output_to_stdout,
                ),
                output_format=effective_format,
                output_dir=output_dir,
                diff_output=diff_output,
                quiet=quiet,
                output_to_stdout=output_to_stdout,
            )
            if not quiet and output_format != "console" and not output_to_stdout:
                print()
                print(generator.ConsoleColors.success("Diff report generated successfully"))

        generator.append_github_step_summary(generator.build_diff_step_summary(diff_result), logger)
        _populate_diff_advisory_rollup(runtime_details, diff_result, changes_only=changes_only)
        return True, diff_result.summary.has_changes, exit_code_override
    except FileNotFoundError as e:
        detail = str(e)
        message = detail if detail.startswith("Snapshot file not found") else f"Snapshot file not found: {detail}"
        print(generator.ConsoleColors.error(f"ERROR: {message}"), file=sys.stderr)
        return False, False, None
    except ValueError as e:
        if _emit_requested_inventory_failure(generator, e):
            return False, False, None
        print(generator.ConsoleColors.error(f"ERROR: Invalid snapshot file: {e!s}"), file=sys.stderr)
        return False, False, None
    except (KeyboardInterrupt, SystemExit):
        raise
    except (generator.CJASDRError, OSError) as e:
        print(generator.ConsoleColors.error(f"ERROR: Failed to compare snapshots: {e!s}"), file=sys.stderr)
        logger.debug("Snapshot comparison failed", exc_info=True)
        return False, False, None
    except Exception as e:
        print(generator.ConsoleColors.error(f"ERROR: Failed to compare snapshots (unexpected): {e!s}"), file=sys.stderr)
        logger.debug("Unexpected snapshot comparison error", exc_info=True)
        return False, False, None
