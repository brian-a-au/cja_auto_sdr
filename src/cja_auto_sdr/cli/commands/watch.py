# ruff: noqa: T201
"""Watch mode command entry point.

Owns: signal handler installation, the outer loop (cycle pacing via time.monotonic),
the stdout NDJSON writer, and the three structured-log events
(`watch_loop_start`, `watch_cycle_complete`, `watch_loop_stop`).
"""

from __future__ import annotations

import logging
import os
import signal
import sys
import threading
import time
from typing import Any

from cja_auto_sdr.core.logging import emit_diagnostic, setup_logging
from cja_auto_sdr.diff.comparator import DataViewComparator
from cja_auto_sdr.diff.snapshot import SnapshotManager, parse_duration_seconds
from cja_auto_sdr.output.watch_event import ErrorEvent, serialize_event
from cja_auto_sdr.pipeline.watch import WatchCycleRunner

_logger = logging.getLogger(__name__)
_stop_requested = threading.Event()
# Module-scope holder for the signal reason. Mutated by the signal handler closure
# inside `_install_signal_handlers`; read by `run_watch` after the loop exits.
_stop_reason_holder: dict[str, str] = {}


def _install_signal_handlers() -> None:
    """Install SIGINT/SIGTERM handlers that set _stop_requested + record the reason."""

    def _handler(signum, _frame):
        _stop_reason_holder["reason"] = "sigint" if signum == signal.SIGINT else "sigterm"
        _stop_requested.set()

    signal.signal(signal.SIGINT, _handler)
    signal.signal(signal.SIGTERM, _handler)


class _LoggingEmitter:
    """Bridges loop lifecycle events to the structured-log diagnostic channel."""

    def __init__(self, *, logger: logging.Logger) -> None:
        self._logger = logger

    def loop_start(self, *, data_view_count: int, interval_seconds: int, watch_threshold: int) -> None:
        emit_diagnostic(
            self._logger,
            "watch_loop_start",
            "watch",
            data_view_count=data_view_count,
            interval_seconds=interval_seconds,
            watch_threshold=watch_threshold,
        )

    def cycle_complete(self, *, cycle: int, data_view_id: str, total_changes: int) -> None:
        emit_diagnostic(
            self._logger,
            "watch_cycle_complete",
            "watch",
            cycle=cycle,
            data_view_id=data_view_id,
            total_changes=total_changes,
        )

    def loop_stop(self, *, reason: str, cycles_completed: int) -> None:
        emit_diagnostic(
            self._logger,
            "watch_loop_stop",
            "watch",
            reason=reason,
            cycles_completed=cycles_completed,
        )


def _sleep_with_stop(seconds: int) -> None:
    """Sleep up to *seconds* but wake immediately on _stop_requested."""
    deadline = time.monotonic() + seconds
    while not _stop_requested.is_set():
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            return
        _stop_requested.wait(timeout=min(remaining, 1.0))


class _NullCja:
    """Test-mode stub that causes snapshot fetch to fail fast without real creds."""

    def getDataView(self, _dv_id):
        raise ConnectionError("test mode: no real CJA client")


def _resolve_cja_client(args: Any) -> Any:
    """Resolve a configured cja client for the watch loop.

    Mirrors the two-step pattern used by cli/commands/list.py:150-163:
    `configure_cjapy(profile=..., config_file=...)` then `cjapy.CJA()`.
    Test-mode bail-out via env var lets tests/test_watch_signals.py exercise the
    loop without real credentials.
    """
    if os.environ.get("CJA_AUTO_SDR_WATCH_TEST_MODE") == "1":
        return _NullCja()
    from cja_auto_sdr import generator  # import generator to use its already-bound cjapy
    from cja_auto_sdr.api.client import configure_cjapy

    success, _source, _meta = configure_cjapy(
        profile=getattr(args, "profile", None),
        config_file=getattr(args, "config_file", "config.json"),
        logger=_logger,
    )
    if not success:
        raise RuntimeError("Failed to configure CJA credentials for watch mode")
    return generator.cjapy.CJA()


def run_watch(args: Any, *, cja: Any | None = None) -> int:
    """Run the watch loop. Returns the process exit code (always 0 on clean exit)."""
    interval_seconds = parse_duration_seconds(args.watch_interval)
    if interval_seconds is None:
        print(f"ERROR: Invalid --interval value: {args.watch_interval}", file=sys.stderr)
        return 1

    # Initialize logging so the three structured-log events (watch_loop_start,
    # watch_cycle_complete, watch_loop_stop) actually reach handlers. _main_impl's
    # `sys.exit(run_watch(args))` bypasses the SDR-path setup_logging() call, so
    # without this the diagnostics get dropped at INFO level — particularly
    # breaking --log-format json for watch mode.
    global _logger  # noqa: PLW0603 — module-scope logger refresh after setup_logging
    _logger = setup_logging(
        data_view_id=None,
        batch_mode=True,
        log_level=getattr(args, "log_level", None),
        log_format=getattr(args, "log_format", "text"),
    )

    if cja is None:
        try:
            cja = _resolve_cja_client(args)
        except RuntimeError as exc:
            print(f"ERROR: {exc}", file=sys.stderr)
            return 1

    snapshot_manager = SnapshotManager(logger=_logger)
    # `include_calc_metrics=True, include_segments=True` ensures the diff result populates
    # calc_metrics_* and segments_* counters. Without these, `_watch_total_changes` would
    # always read zero for inventory deltas (see DataViewComparator.__init__ defaults at
    # diff/comparator.py:116-117).
    comparator = DataViewComparator(
        logger=_logger,
        include_calc_metrics=True,
        include_segments=True,
    )
    runner = WatchCycleRunner(
        snapshot_manager=snapshot_manager,
        comparator=comparator,
        threshold=args.watch_threshold,
    )
    emitter = _LoggingEmitter(logger=_logger)

    _install_signal_handlers()
    emitter.loop_start(
        data_view_count=len(args.watch_data_views),
        interval_seconds=interval_seconds,
        watch_threshold=args.watch_threshold,
    )

    cycle = 0
    stop_reason = "fatal"  # overwritten if signal handler runs
    try:
        while True:
            cycle += 1
            for event in runner.run_cycle(cja=cja, data_view_ids=args.watch_data_views, cycle=cycle):
                sys.stdout.write(serialize_event(event))
                sys.stdout.flush()
                # cycle_complete fires per emitted NDJSON event but NOT for error events
                # (the error event itself is the signal).
                if not isinstance(event, ErrorEvent):
                    emitter.cycle_complete(
                        cycle=cycle,
                        data_view_id=event.data_view_id,
                        total_changes=getattr(event, "total_changes", 0),
                    )
            if _stop_requested.is_set():
                break
            _sleep_with_stop(interval_seconds)
            # Catch signals that arrived DURING sleep so we don't run a phantom cycle
            # before observing the stop flag.
            if _stop_requested.is_set():
                break
        stop_reason = _stop_reason_holder.get("reason", "fatal")
    finally:
        emitter.loop_stop(reason=stop_reason, cycles_completed=cycle)
        _stop_reason_holder.clear()

    return 0
