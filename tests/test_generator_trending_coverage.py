"""Tests targeting uncovered code paths in _build_org_report_trending_window()
in generator.py (lines ~8170-8248).

Covers:
1. Snapshot persistence failure (OSError from save_org_report_snapshot)
2. Extraction failure (current snapshot normalisation fails)
3. History exclusion: current snapshot not eligible for trending
4. Insufficient snapshots: build_trending returns None -> fewer-than-2 warning
5. Prune failure (OSError from prune_org_report_snapshots)

Note: _build_org_report_trending_window uses local (deferred) imports, so the
correct patch targets are the sub-module paths, e.g.
  'cja_auto_sdr.org.writers.build_org_report_json_data'
  'cja_auto_sdr.org.snapshot_utils.org_report_snapshot_history_assessment'
  'cja_auto_sdr.org.trending._extract_snapshot_from_json'
  'cja_auto_sdr.org.trending.build_trending'
"""

from __future__ import annotations

import logging
import typing
from pathlib import Path
from unittest.mock import MagicMock, patch

from cja_auto_sdr.generator import _build_org_report_trending_window
from cja_auto_sdr.org.models import (
    ComponentDistribution,
    ComponentInfo,
    DataViewSummary,
    OrgReportConfig,
    OrgReportResult,
    OrgReportTrending,
    TrendingSnapshot,
)
from cja_auto_sdr.org.snapshot_utils import OrgReportSnapshotHistoryAssessment

# ---------------------------------------------------------------------------
# Patch target constants
# ---------------------------------------------------------------------------

_PATCH_BUILD_JSON = "cja_auto_sdr.org.writers.build_org_report_json_data"
_PATCH_HISTORY_ASSESSMENT = "cja_auto_sdr.org.snapshot_utils.org_report_snapshot_history_assessment"
_PATCH_EXTRACT = "cja_auto_sdr.org.trending._extract_snapshot_from_json"
_PATCH_BUILD_TRENDING = "cja_auto_sdr.org.trending.build_trending"
_PATCH_DISCOVER_SNAPSHOTS = "cja_auto_sdr.org.trending.discover_snapshots"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_result(org_id: str = "test_org") -> OrgReportResult:
    return OrgReportResult(
        timestamp="2026-03-01T00:00:00Z",
        org_id=org_id,
        parameters=OrgReportConfig(),
        data_view_summaries=[
            DataViewSummary(data_view_id="dv1", data_view_name="Test DV 1", metric_count=10, dimension_count=5),
        ],
        component_index={
            "m1": ComponentInfo(component_id="m1", component_type="metric", data_views={"dv1"}),
        },
        distribution=ComponentDistribution(
            core_metrics=["m1"],
            isolated_metrics=[],
            core_dimensions=[],
            isolated_dimensions=[],
        ),
        similarity_pairs=[],
        recommendations=[],
        duration=0.5,
    )


def _history_assessment(reason: str | None) -> OrgReportSnapshotHistoryAssessment:
    return OrgReportSnapshotHistoryAssessment(
        eligible=reason is None,
        exclusion_reason=reason,
        fidelity_known=True,
    )


def _make_cache(
    *,
    save_side_effect=None,
    prune_side_effect=None,
    snapshot_root: str = "/tmp/fake_cache",
) -> MagicMock:
    cache = MagicMock()
    cache.get_org_report_snapshot_root_dir.return_value = snapshot_root
    if save_side_effect is not None:
        cache.save_org_report_snapshot.side_effect = save_side_effect
    else:
        cache.save_org_report_snapshot.return_value = "/tmp/fake_cache/snap.json"
    if prune_side_effect is not None:
        cache.prune_org_report_snapshots.side_effect = prune_side_effect
    return cache


def _make_logger() -> logging.Logger:
    return logging.getLogger("test_trending_coverage")


def _noop_status(*args, **kwargs):
    pass


def _call(result, cache, *, quiet=False, explicit_history_file=None, status_fn=None):
    """Convenience wrapper that calls _build_org_report_trending_window with common defaults."""
    return _build_org_report_trending_window(
        result=result,
        trending_window=5,
        cache=cache,
        explicit_history_file=explicit_history_file,
        logger=_make_logger(),
        quiet=quiet,
        status_print=status_fn or _noop_status,
    )


def _collector(warnings: list) -> typing.Callable[[str], None]:
    """Return a status_print callable that appends messages to warnings."""

    def _append(msg):
        warnings.append(msg)

    return _append


# ---------------------------------------------------------------------------
# 1. Snapshot persistence failure: OSError from save_org_report_snapshot
# ---------------------------------------------------------------------------


class TestSnapshotPersistenceFailure:
    """OSError from save_org_report_snapshot should log a warning and continue gracefully."""

    def test_warning_emitted_on_oserror(self):
        result = _make_result()
        cache = _make_cache(save_side_effect=OSError("disk full"))
        warnings: list = []

        with (
            patch(_PATCH_BUILD_JSON, return_value={"report_type": "org"}),
            patch(_PATCH_HISTORY_ASSESSMENT, return_value=_history_assessment(None)),
            patch(_PATCH_EXTRACT, return_value=MagicMock()),
            patch(_PATCH_BUILD_TRENDING, return_value=MagicMock()),
        ):
            _call(result, cache, quiet=False, status_fn=_collector(warnings))

        assert any("persist" in w.lower() for w in warnings), (
            f"Expected a persistence-failure warning but got: {warnings}"
        )

    def test_returns_none_gracefully_on_persistence_failure(self):
        """When save fails AND build_trending returns None, function still returns None without raising."""
        result = _make_result()
        cache = _make_cache(save_side_effect=OSError("no space"))

        with (
            patch(_PATCH_BUILD_JSON, return_value={}),
            patch(_PATCH_HISTORY_ASSESSMENT, return_value=_history_assessment(None)),
            patch(_PATCH_EXTRACT, return_value=MagicMock()),
            patch(_PATCH_BUILD_TRENDING, return_value=None),
        ):
            return_value = _call(result, cache, quiet=True)

        assert return_value is None

    def test_quiet_suppresses_persistence_warning(self):
        result = _make_result()
        cache = _make_cache(save_side_effect=OSError("disk full"))
        warnings: list = []

        with (
            patch(_PATCH_BUILD_JSON, return_value={}),
            patch(_PATCH_HISTORY_ASSESSMENT, return_value=_history_assessment(None)),
            patch(_PATCH_EXTRACT, return_value=MagicMock()),
            patch(_PATCH_BUILD_TRENDING, return_value=MagicMock()),
        ):
            _call(result, cache, quiet=True, status_fn=_collector(warnings))

        assert warnings == [], f"Expected no warnings in quiet mode but got: {warnings}"


# ---------------------------------------------------------------------------
# 2. Extraction failure: _extract_snapshot_from_json returns None
# ---------------------------------------------------------------------------


class TestExtractionFailure:
    """When _extract_snapshot_from_json returns None a warning should be emitted."""

    def test_warning_emitted_when_snapshot_cannot_be_normalised(self):
        result = _make_result()
        cache = _make_cache()
        warnings: list = []

        with (
            patch(_PATCH_BUILD_JSON, return_value={}),
            patch(_PATCH_HISTORY_ASSESSMENT, return_value=_history_assessment(None)),
            patch(_PATCH_EXTRACT, return_value=None),  # normalisation fails
            patch(_PATCH_BUILD_TRENDING, return_value=MagicMock()),
        ):
            _call(result, cache, quiet=False, status_fn=_collector(warnings))

        assert any("normaliz" in w.lower() or "trending" in w.lower() for w in warnings), (
            f"Expected normalisation warning but got: {warnings}"
        )

    def test_quiet_suppresses_extraction_warning(self):
        result = _make_result()
        cache = _make_cache()
        warnings: list = []

        with (
            patch(_PATCH_BUILD_JSON, return_value={}),
            patch(_PATCH_HISTORY_ASSESSMENT, return_value=_history_assessment(None)),
            patch(_PATCH_EXTRACT, return_value=None),
            patch(_PATCH_BUILD_TRENDING, return_value=MagicMock()),
        ):
            _call(result, cache, quiet=True, status_fn=_collector(warnings))

        assert warnings == []


# ---------------------------------------------------------------------------
# 3. History exclusion: org_report_snapshot_history_assessment returns a reason
# ---------------------------------------------------------------------------


class TestHistoryExclusion:
    """When a history exclusion reason exists, the current snapshot is excluded
    and a warning note is displayed (with or without available cached trending)."""

    def test_exclusion_warning_with_trending_available(self):
        result = _make_result()
        cache = _make_cache()
        warnings: list = []

        with (
            patch(_PATCH_BUILD_JSON, return_value={}),
            patch(_PATCH_HISTORY_ASSESSMENT, return_value=_history_assessment("sampled")),
            patch(_PATCH_EXTRACT, return_value=MagicMock()),
            patch(_PATCH_BUILD_TRENDING, return_value=MagicMock()),  # trending available
        ):
            _call(result, cache, quiet=False, status_fn=_collector(warnings))

        assert any("sampled" in w.lower() or "excluded" in w.lower() or "history" in w.lower() for w in warnings), (
            f"Expected exclusion warning but got: {warnings}"
        )

    def test_exclusion_warning_without_trending(self):
        result = _make_result()
        cache = _make_cache()
        warnings: list = []

        with (
            patch(_PATCH_BUILD_JSON, return_value={}),
            patch(_PATCH_HISTORY_ASSESSMENT, return_value=_history_assessment("sampled")),
            patch(_PATCH_EXTRACT, return_value=MagicMock()),
            patch(_PATCH_BUILD_TRENDING, return_value=None),  # no trending available
        ):
            _call(result, cache, quiet=False, status_fn=_collector(warnings))

        # Should mention "fewer than 2" or no eligible snapshots
        all_warnings = " ".join(w.lower() for w in warnings)
        assert "fewer" in all_warnings or "skip" in all_warnings or "eligib" in all_warnings, (
            f"Expected insufficient-snapshots note but got: {warnings}"
        )

    def test_exclusion_non_sampled_reason(self):
        """A non-'sampled' exclusion reason also generates a warning."""
        result = _make_result()
        cache = _make_cache()
        warnings: list = []

        with (
            patch(_PATCH_BUILD_JSON, return_value={}),
            patch(_PATCH_HISTORY_ASSESSMENT, return_value=_history_assessment("no_similarity")),
            patch(_PATCH_EXTRACT, return_value=MagicMock()),
            patch(_PATCH_BUILD_TRENDING, return_value=MagicMock()),
        ):
            _call(result, cache, quiet=False, status_fn=_collector(warnings))

        assert len(warnings) > 0

    def test_exclusion_suppressed_when_quiet(self):
        result = _make_result()
        cache = _make_cache()
        warnings: list = []

        with (
            patch(_PATCH_BUILD_JSON, return_value={}),
            patch(_PATCH_HISTORY_ASSESSMENT, return_value=_history_assessment("sampled")),
            patch(_PATCH_EXTRACT, return_value=MagicMock()),
            patch(_PATCH_BUILD_TRENDING, return_value=None),
        ):
            _call(result, cache, quiet=True, status_fn=_collector(warnings))

        assert warnings == []


# ---------------------------------------------------------------------------
# 4. Insufficient snapshots: build_trending returns None (no exclusion reason)
# ---------------------------------------------------------------------------


class TestInsufficientSnapshots:
    """When there is no exclusion reason but build_trending returns None,
    the function should warn about fewer than 2 snapshots."""

    def test_fewer_than_2_warning_emitted(self):
        result = _make_result()
        cache = _make_cache()
        warnings: list = []

        with (
            patch(_PATCH_BUILD_JSON, return_value={}),
            patch(_PATCH_HISTORY_ASSESSMENT, return_value=_history_assessment(None)),
            patch(_PATCH_EXTRACT, return_value=MagicMock()),
            patch(_PATCH_BUILD_TRENDING, return_value=None),  # no trending available
        ):
            _call(result, cache, quiet=False, status_fn=_collector(warnings))

        assert any("fewer" in w.lower() or "2" in w for w in warnings), (
            f"Expected 'fewer than 2' warning but got: {warnings}"
        )

    def test_fewer_than_2_suppressed_when_quiet(self):
        result = _make_result()
        cache = _make_cache()
        warnings: list = []

        with (
            patch(_PATCH_BUILD_JSON, return_value={}),
            patch(_PATCH_HISTORY_ASSESSMENT, return_value=_history_assessment(None)),
            patch(_PATCH_EXTRACT, return_value=MagicMock()),
            patch(_PATCH_BUILD_TRENDING, return_value=None),
        ):
            _call(result, cache, quiet=True, status_fn=_collector(warnings))

        assert warnings == []


# ---------------------------------------------------------------------------
# 5. Prune failure: OSError from prune_org_report_snapshots
# ---------------------------------------------------------------------------


class TestPruneFailure:
    """OSError from prune_org_report_snapshots should log a warning and not raise."""

    def test_prune_oserror_emits_warning(self):
        result = _make_result()
        cache = _make_cache(prune_side_effect=OSError("permission denied"))
        warnings: list = []

        with (
            patch(_PATCH_BUILD_JSON, return_value={}),
            patch(_PATCH_HISTORY_ASSESSMENT, return_value=_history_assessment(None)),
            patch(_PATCH_EXTRACT, return_value=MagicMock()),
            patch(_PATCH_BUILD_TRENDING, return_value=MagicMock()),
        ):
            _call(result, cache, quiet=False, status_fn=_collector(warnings))

        assert any("prune" in w.lower() or "snapshot" in w.lower() for w in warnings), (
            f"Expected prune warning but got: {warnings}"
        )

    def test_prune_oserror_quiet_suppresses_warning(self):
        result = _make_result()
        cache = _make_cache(prune_side_effect=OSError("permission denied"))
        warnings: list = []

        with (
            patch(_PATCH_BUILD_JSON, return_value={}),
            patch(_PATCH_HISTORY_ASSESSMENT, return_value=_history_assessment(None)),
            patch(_PATCH_EXTRACT, return_value=MagicMock()),
            patch(_PATCH_BUILD_TRENDING, return_value=MagicMock()),
        ):
            _call(result, cache, quiet=True, status_fn=_collector(warnings))

        assert warnings == []

    def test_prune_not_called_when_save_failed(self):
        """Prune is only called when saved_snapshot_path is not None.
        If save raises, prune should not be attempted."""
        result = _make_result()
        cache = _make_cache(save_side_effect=OSError("no space"))

        with (
            patch(_PATCH_BUILD_JSON, return_value={}),
            patch(_PATCH_HISTORY_ASSESSMENT, return_value=_history_assessment(None)),
            patch(_PATCH_EXTRACT, return_value=MagicMock()),
            patch(_PATCH_BUILD_TRENDING, return_value=MagicMock()),
        ):
            _call(result, cache, quiet=True)

        cache.prune_org_report_snapshots.assert_not_called()


# ---------------------------------------------------------------------------
# 6. Explicit history file included in preserved paths for prune
# ---------------------------------------------------------------------------


class TestExplicitHistoryFile:
    """When explicit_history_file is provided, it is included in preserved paths for prune."""

    def test_explicit_history_file_in_prune_call(self):
        result = _make_result()
        cache = _make_cache()

        with (
            patch(_PATCH_BUILD_JSON, return_value={}),
            patch(_PATCH_HISTORY_ASSESSMENT, return_value=_history_assessment(None)),
            patch(_PATCH_EXTRACT, return_value=MagicMock()),
            patch(_PATCH_BUILD_TRENDING, return_value=MagicMock()),
        ):
            _call(result, cache, quiet=True, explicit_history_file="/some/history.json")

        prune_call = cache.prune_org_report_snapshots.call_args
        assert prune_call is not None
        preserved = prune_call.kwargs.get("preserved_snapshot_paths") or (prune_call.args[0] if prune_call.args else [])
        assert any(str(p) == "/some/history.json" for p in preserved)


class TestPrunePreservesEligibleHistoryWindow:
    """Pruning should preserve the eligible history window that informed the current run."""

    def test_preserves_source_paths_from_returned_trending_window(self):
        result = _make_result()
        cache = _make_cache()
        trending = OrgReportTrending(
            snapshots=[
                TrendingSnapshot(timestamp="2026-01-01T00:00:00Z", source_path="/tmp/older.json"),
                TrendingSnapshot(timestamp="2026-02-01T00:00:00Z", source_path="/tmp/newer.json"),
            ],
            window_size=2,
        )

        with (
            patch(_PATCH_BUILD_JSON, return_value={}),
            patch(_PATCH_HISTORY_ASSESSMENT, return_value=_history_assessment(None)),
            patch(_PATCH_EXTRACT, return_value=MagicMock()),
            patch(_PATCH_BUILD_TRENDING, return_value=trending),
        ):
            _call(result, cache, quiet=True)

        preserved = cache.prune_org_report_snapshots.call_args.kwargs["preserved_snapshot_paths"]
        normalized = {str(path) for path in preserved}
        assert str(Path("/tmp/fake_cache/snap.json").resolve(strict=False)) in normalized
        assert str(Path("/tmp/older.json").resolve(strict=False)) in normalized
        assert str(Path("/tmp/newer.json").resolve(strict=False)) in normalized

    def test_preserves_discovered_eligible_snapshots_even_when_trending_is_none(self):
        result = _make_result()
        cache = _make_cache()
        discovered = [TrendingSnapshot(timestamp="2026-02-01T00:00:00Z", source_path="/tmp/eligible.json")]

        with (
            patch(_PATCH_BUILD_JSON, return_value={}),
            patch(_PATCH_HISTORY_ASSESSMENT, return_value=_history_assessment("sampled")),
            patch(_PATCH_EXTRACT, return_value=MagicMock()),
            patch(_PATCH_BUILD_TRENDING, return_value=None),
            patch(_PATCH_DISCOVER_SNAPSHOTS, return_value=discovered) as mock_discover,
        ):
            _call(result, cache, quiet=True)

        mock_discover.assert_called_once_with(
            cache_dir="/tmp/fake_cache",
            window_size=5,
            explicit_file=None,
            org_id="test_org",
        )
        preserved = cache.prune_org_report_snapshots.call_args.kwargs["preserved_snapshot_paths"]
        normalized = {str(path) for path in preserved}
        assert str(Path("/tmp/fake_cache/snap.json").resolve(strict=False)) in normalized
        assert str(Path("/tmp/eligible.json").resolve(strict=False)) in normalized


# ---------------------------------------------------------------------------
# 7. Happy path: success returns the trending result
# ---------------------------------------------------------------------------


class TestHappyPath:
    """When everything succeeds, _build_org_report_trending_window returns trending."""

    def test_returns_trending_on_success(self):
        result = _make_result()
        cache = _make_cache()
        mock_trending = MagicMock()

        with (
            patch(_PATCH_BUILD_JSON, return_value={}),
            patch(_PATCH_HISTORY_ASSESSMENT, return_value=_history_assessment(None)),
            patch(_PATCH_EXTRACT, return_value=MagicMock()),
            patch(_PATCH_BUILD_TRENDING, return_value=mock_trending),
        ):
            returned = _call(result, cache)

        assert returned is mock_trending

    def test_no_cache_provided_creates_default(self):
        """When cache=None, an OrgReportCache is created internally."""
        result = _make_result()
        mock_trending = MagicMock()
        mock_cache_instance = _make_cache()

        with (
            patch("cja_auto_sdr.generator.OrgReportCache", return_value=mock_cache_instance) as mock_cache_cls,
            patch(_PATCH_BUILD_JSON, return_value={}),
            patch(_PATCH_HISTORY_ASSESSMENT, return_value=_history_assessment(None)),
            patch(_PATCH_EXTRACT, return_value=MagicMock()),
            patch(_PATCH_BUILD_TRENDING, return_value=mock_trending),
        ):
            returned = _build_org_report_trending_window(
                result=result,
                trending_window=3,
                cache=None,  # no cache provided
                explicit_history_file=None,
                logger=_make_logger(),
                quiet=True,
                status_print=_noop_status,
            )

        mock_cache_cls.assert_called_once()
        assert returned is mock_trending
