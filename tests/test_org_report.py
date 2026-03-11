"""
Tests for org-wide component analysis report functionality
"""

import json
import multiprocessing
import os
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pandas as pd
import pytest

sys.path.insert(0, ".")

import time

from cja_auto_sdr.core.exceptions import ConcurrentOrgReportError, LockOwnershipLostError
from cja_auto_sdr.generator import (
    ComponentDistribution,
    ComponentInfo,
    DataViewCluster,
    DataViewSummary,
    OrgComponentAnalyzer,
    OrgReportCache,
    OrgReportConfig,
    OrgReportResult,
    SimilarityPair,
    _render_distribution_bar,
    compare_org_reports,
    run_org_report,
    write_org_report_csv,
    write_org_report_excel,
    write_org_report_html,
    write_org_report_json,
    write_org_report_markdown,
)
from cja_auto_sdr.org.cache import OrgReportLock

XLSX_NS = {"x": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _mark_full_fidelity_baseline(payload):
    payload = dict(payload)
    parameters = dict(payload.get("parameters", {}))
    parameters.setdefault("skip_similarity", False)
    parameters.setdefault("org_stats_only", False)
    payload["parameters"] = parameters

    summary = dict(payload.get("summary", {}))
    summary.setdefault("similarity_analysis_complete", True)
    summary.setdefault("similarity_analysis_mode", "complete")
    payload["summary"] = summary

    payload.setdefault("similarity_pairs", [])
    return payload


def _write_signal(path: str, value: str) -> None:
    Path(path).write_text(value, encoding="utf-8")


def _read_signal(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8").strip()


def _org_lock_hold_worker(
    lock_dir: str,
    org_id: str,
    signal_file: str,
    hold_seconds: float,
    lock_backend: str | None = None,
) -> None:
    lock = OrgReportLock(org_id, lock_dir=Path(lock_dir), lock_backend=lock_backend)
    acquired = lock._try_acquire()
    _write_signal(signal_file, "1" if acquired else "0")
    if not acquired:
        return

    try:
        time.sleep(hold_seconds)
    finally:
        lock._release()


def _org_lock_crash_worker(
    lock_dir: str,
    org_id: str,
    signal_file: str,
    lock_backend: str | None = None,
) -> None:
    lock = OrgReportLock(org_id, lock_dir=Path(lock_dir), lock_backend=lock_backend)
    acquired = lock._try_acquire()
    _write_signal(signal_file, "1" if acquired else "0")
    if acquired:
        os._exit(1)
    os._exit(2)


def _get_excel_shared_strings(file_path: str) -> list[str]:
    """Extract shared strings from an XLSX file without openpyxl."""
    with zipfile.ZipFile(file_path) as archive:
        if "xl/sharedStrings.xml" not in archive.namelist():
            return []
        shared_strings_xml = archive.read("xl/sharedStrings.xml")

    root = ET.fromstring(shared_strings_xml)
    shared_strings: list[str] = []
    for entry in root.findall("x:si", XLSX_NS):
        fragments = [fragment.text or "" for fragment in entry.findall(".//x:t", XLSX_NS)]
        shared_strings.append("".join(fragments))
    return shared_strings


class TestOrgReportLock:
    """Test OrgReportLock for preventing concurrent runs"""

    def test_lock_acquired_when_no_existing_lock(self):
        """Test that lock is acquired when no existing lock"""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock = OrgReportLock("test_org@AdobeOrg", lock_dir=Path(tmpdir))
            with lock:
                assert lock.acquired is True
                # Lock file should exist
                assert lock.lock_file.exists()
            # File remains for metadata observability after release.
            assert lock.lock_file.exists()

    def test_lock_blocks_second_acquisition(self):
        """Test that second lock acquisition fails when first holds lock"""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock1 = OrgReportLock("test_org@AdobeOrg", lock_dir=Path(tmpdir))
            lock2 = OrgReportLock("test_org@AdobeOrg", lock_dir=Path(tmpdir))

            with lock1:
                assert lock1.acquired is True
                # Second lock should fail
                with lock2:
                    assert lock2.acquired is False

    def test_lock_allows_different_orgs(self):
        """Test that different orgs can run concurrently"""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock1 = OrgReportLock("org1@AdobeOrg", lock_dir=Path(tmpdir))
            lock2 = OrgReportLock("org2@AdobeOrg", lock_dir=Path(tmpdir))

            with lock1:
                assert lock1.acquired is True
                with lock2:
                    # Different org should succeed
                    assert lock2.acquired is True

    def test_stale_lock_is_taken_over(self):
        """Test that stale locks from dead processes are taken over"""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_dir = Path(tmpdir)
            lock_file = lock_dir / "org_report_test_org_at_AdobeOrg.lock"
            lock_dir.mkdir(parents=True, exist_ok=True)

            # Write a stale lock with a non-existent PID
            with open(lock_file, "w") as f:
                json.dump(
                    {
                        "pid": 999999999,  # Very unlikely to exist
                        "timestamp": time.time() - 7200,  # 2 hours ago
                        "started_at": "2024-01-01T00:00:00",
                    },
                    f,
                )

            # New lock should take over
            lock = OrgReportLock("test_org@AdobeOrg", lock_dir=lock_dir, stale_threshold_seconds=3600)
            with lock:
                assert lock.acquired is True

    def test_get_lock_info(self):
        """Test get_lock_info returns lock holder information"""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock = OrgReportLock("test_org@AdobeOrg", lock_dir=Path(tmpdir))

            # No lock initially
            assert lock.get_lock_info() is None

            with lock:
                info = lock.get_lock_info()
                assert info is not None
                assert info["pid"] == os.getpid()
                assert "started_at" in info

    def test_lock_sanitizes_org_id(self):
        """Test that org ID is sanitized for filename safety"""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock = OrgReportLock("test/org@AdobeOrg", lock_dir=Path(tmpdir))
            # Should not contain unsafe characters
            assert "@" not in lock.lock_file.name
            assert "/" not in lock.lock_file.name

    def test_process_running_treats_permission_error_as_running(self):
        """PermissionError should be treated as process alive (EPERM semantics)."""
        with patch("os.kill", side_effect=PermissionError):
            assert OrgReportLock._is_process_running(12345) is True

    @pytest.mark.parametrize("invalid_pid", [0, -1, 10**40, True])
    def test_process_running_rejects_invalid_pid_values(self, invalid_pid):
        assert OrgReportLock._is_process_running(invalid_pid) is False

    def test_corrupt_unlocked_lock_file_reclaimed_immediately(self):
        """Unreadable metadata must not block acquisition when no lock is held."""
        with tempfile.TemporaryDirectory() as tmpdir:
            lock_dir = Path(tmpdir)
            lock_file = lock_dir / "org_report_test_org_AdobeOrg.lock"
            lock_dir.mkdir(parents=True, exist_ok=True)
            lock_file.write_text("{bad json", encoding="utf-8")

            lock = OrgReportLock("test_org@AdobeOrg", lock_dir=lock_dir, lock_backend="lease")
            with lock:
                assert lock.acquired is True

    def test_lock_contention_multi_process(self):
        """Second process should fail acquisition while first process holds lock."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ready_file = Path(tmpdir) / "ready.txt"
            proc = multiprocessing.Process(
                target=_org_lock_hold_worker,
                args=(tmpdir, "test_org@AdobeOrg", str(ready_file), 1.5),
            )
            proc.start()

            deadline = time.time() + 3
            while _read_signal(ready_file) is None and time.time() < deadline:
                time.sleep(0.02)

            assert _read_signal(ready_file) == "1"

            contender = OrgReportLock("test_org@AdobeOrg", lock_dir=Path(tmpdir))
            with contender:
                assert contender.acquired is False

            proc.join(timeout=4)
            assert not proc.is_alive()

            # Once holder exits, acquisition should succeed immediately.
            follow_up = OrgReportLock("test_org@AdobeOrg", lock_dir=Path(tmpdir))
            with follow_up:
                assert follow_up.acquired is True

    def test_crash_recovery_is_immediate(self):
        """Crash of lock holder should release lock without stale-threshold waiting."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ready_file = Path(tmpdir) / "crash_ready.txt"
            proc = multiprocessing.Process(
                target=_org_lock_crash_worker,
                args=(tmpdir, "test_org@AdobeOrg", str(ready_file)),
            )
            proc.start()

            deadline = time.time() + 3
            while _read_signal(ready_file) is None and time.time() < deadline:
                time.sleep(0.02)

            assert _read_signal(ready_file) == "1"
            proc.join(timeout=3)
            assert not proc.is_alive()

            recovered = OrgReportLock("test_org@AdobeOrg", lock_dir=Path(tmpdir))
            with recovered:
                assert recovered.acquired is True

    def test_lock_contention_multi_process_lease_backend(self):
        """Lease backend should block contenders while holder is alive."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ready_file = Path(tmpdir) / "ready_lease.txt"
            proc = multiprocessing.Process(
                target=_org_lock_hold_worker,
                args=(tmpdir, "test_org@AdobeOrg", str(ready_file), 1.5, "lease"),
            )
            proc.start()

            deadline = time.time() + 3
            while _read_signal(ready_file) is None and time.time() < deadline:
                time.sleep(0.02)

            assert _read_signal(ready_file) == "1"

            contender = OrgReportLock("test_org@AdobeOrg", lock_dir=Path(tmpdir), lock_backend="lease")
            with contender:
                assert contender.acquired is False

            proc.join(timeout=4)
            assert not proc.is_alive()

            follow_up = OrgReportLock("test_org@AdobeOrg", lock_dir=Path(tmpdir), lock_backend="lease")
            with follow_up:
                assert follow_up.acquired is True

    def test_crash_recovery_is_immediate_lease_backend(self):
        """Lease backend should reclaim lock after holder crash without stale wait."""
        with tempfile.TemporaryDirectory() as tmpdir:
            ready_file = Path(tmpdir) / "crash_ready_lease.txt"
            proc = multiprocessing.Process(
                target=_org_lock_crash_worker,
                args=(tmpdir, "test_org@AdobeOrg", str(ready_file), "lease"),
            )
            proc.start()

            deadline = time.time() + 3
            while _read_signal(ready_file) is None and time.time() < deadline:
                time.sleep(0.02)

            assert _read_signal(ready_file) == "1"
            proc.join(timeout=3)
            assert not proc.is_alive()

            recovered = OrgReportLock("test_org@AdobeOrg", lock_dir=Path(tmpdir), lock_backend="lease")
            with recovered:
                assert recovered.acquired is True


class TestConcurrentOrgReportError:
    """Test ConcurrentOrgReportError exception"""

    def test_error_message(self):
        """Test error message formatting"""
        error = ConcurrentOrgReportError(
            org_id="test@AdobeOrg",
            lock_holder_pid=12345,
            started_at="2024-01-15T10:00:00",
        )
        assert "test@AdobeOrg" in str(error)
        assert "12345" in str(error)
        assert "2024-01-15T10:00:00" in str(error)

    def test_error_without_details(self):
        """Test error message without optional details"""
        error = ConcurrentOrgReportError(org_id="test@AdobeOrg")
        assert "test@AdobeOrg" in str(error)


class TestAnalyzerLockIntegration:
    """Test OrgComponentAnalyzer lock integration"""

    def test_analyzer_raises_on_concurrent_run(self):
        """Test that analyzer raises ConcurrentOrgReportError on concurrent run"""
        import logging

        mock_cja = Mock()
        logger = logging.getLogger("test_lock")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a lock that simulates another process
            lock_dir = Path(tmpdir)
            lock_file = lock_dir / "locks" / "org_report_test_org_at_AdobeOrg.lock"
            lock_file.parent.mkdir(parents=True, exist_ok=True)
            with open(lock_file, "w") as f:
                json.dump(
                    {
                        "pid": os.getpid(),  # Use current PID so it appears "running"
                        "timestamp": time.time(),
                        "started_at": datetime.now().isoformat(),
                    },
                    f,
                )

            config = OrgReportConfig(skip_lock=False)

            # Patch the lock to use our temp directory
            with patch("cja_auto_sdr.org.analyzer.OrgReportLock") as MockLock:
                mock_lock_instance = Mock()
                mock_lock_instance.acquired = False
                mock_lock_instance.get_lock_info.return_value = {
                    "pid": 12345,
                    "started_at": "2024-01-15T10:00:00",
                }
                mock_lock_instance.__enter__ = Mock(return_value=mock_lock_instance)
                mock_lock_instance.__exit__ = Mock(return_value=None)
                MockLock.return_value = mock_lock_instance

                analyzer = OrgComponentAnalyzer(mock_cja, config, logger, org_id="test_org@AdobeOrg")

                with pytest.raises(ConcurrentOrgReportError) as exc_info:
                    analyzer.run_analysis()

                assert "test_org@AdobeOrg" in str(exc_info.value)
                mock_cja.getDataViews.assert_not_called()

    def test_analyzer_skip_lock_option(self):
        """Test that skip_lock=True bypasses the lock"""
        import logging

        mock_cja = Mock()
        mock_cja.getDataViews.return_value = []  # Return empty list to end early
        logger = logging.getLogger("test_skip_lock")

        config = OrgReportConfig(skip_lock=True)
        analyzer = OrgComponentAnalyzer(mock_cja, config, logger, org_id="test_org@AdobeOrg")

        # Should not raise even if we don't mock the lock
        result = analyzer.run_analysis()
        assert result is not None

    def test_quick_check_empty_org_returns_empty_result(self):
        """Test that quick check returns empty OrgReportResult when no data views exist"""
        import logging

        mock_cja = Mock()
        mock_cja.getDataViews.return_value = []
        logger = logging.getLogger("test_quick_check_empty")

        analyzer = OrgComponentAnalyzer(mock_cja, OrgReportConfig(skip_lock=True), logger)

        result = analyzer._quick_check_empty_org()
        assert result is not None
        assert result.total_available_data_views == 0
        assert result.data_view_summaries == []

    def test_quick_check_non_empty_org_returns_none(self):
        """Test that quick check returns None when data views exist"""
        import logging

        mock_cja = Mock()
        mock_cja.getDataViews.return_value = [{"id": "dv_1", "name": "DV 1"}]
        logger = logging.getLogger("test_quick_check_non_empty")

        analyzer = OrgComponentAnalyzer(mock_cja, OrgReportConfig(skip_lock=True), logger)

        result = analyzer._quick_check_empty_org()
        assert result is None

    def test_analyzer_aborts_when_lock_ownership_is_lost_mid_run(self):
        """Analyzer must fail closed if lock ownership is lost during execution."""
        import logging

        mock_cja = Mock()
        logger = logging.getLogger("test_lock_lost")
        config = OrgReportConfig(skip_lock=False)

        with patch("cja_auto_sdr.org.analyzer.OrgReportLock") as MockLock:
            mock_lock_instance = Mock()
            mock_lock_instance.acquired = True
            mock_lock_instance.ensure_healthy.side_effect = [
                None,
                LockOwnershipLostError("/tmp/test.lock", reason="heartbeat metadata write failed"),
            ]
            mock_lock_instance.__enter__ = Mock(return_value=mock_lock_instance)
            mock_lock_instance.__exit__ = Mock(return_value=None)
            MockLock.return_value = mock_lock_instance

            analyzer = OrgComponentAnalyzer(mock_cja, config, logger, org_id="test_org@AdobeOrg")
            analyzer._quick_check_empty_org = Mock(return_value=None)

            with pytest.raises(LockOwnershipLostError):
                analyzer.run_analysis()

            analyzer._quick_check_empty_org.assert_called_once()
            mock_cja.getDataViews.assert_not_called()

    def test_fetch_cancels_executor_immediately_when_lock_is_lost(self):
        """Parallel fetch must not block on remaining futures after lock ownership loss."""
        import logging
        from concurrent.futures import FIRST_COMPLETED

        class _FakeFuture:
            def __init__(self, result_value: DataViewSummary):
                self._result_value = result_value
                self.cancel_called = False

            def result(self) -> DataViewSummary:
                return self._result_value

            def cancel(self) -> bool:
                self.cancel_called = True
                return True

        class _FakeExecutor:
            last_instance = None

            def __init__(self, *args, **kwargs):
                self.submitted = []
                self.shutdown_calls = []
                _FakeExecutor.last_instance = self

            def submit(self, fn, dv):  # type: ignore[no-untyped-def]
                summary = DataViewSummary(
                    data_view_id=dv.get("id", "unknown"),
                    data_view_name=dv.get("name", "Unknown"),
                )
                future = _FakeFuture(summary)
                self.submitted.append(future)
                return future

            def shutdown(self, wait=True, cancel_futures=False):  # type: ignore[no-untyped-def]
                self.shutdown_calls.append((wait, cancel_futures))

        mock_cja = Mock()
        logger = logging.getLogger("test_fetch_lock_loss_cancel")
        analyzer = OrgComponentAnalyzer(mock_cja, OrgReportConfig(quiet=True), logger)
        analyzer._assert_lock_healthy = Mock(
            side_effect=[
                None,
                LockOwnershipLostError("/tmp/test.lock", reason="heartbeat metadata write failed"),
            ],
        )

        data_views = [
            {"id": "dv_1", "name": "DV 1"},
            {"id": "dv_2", "name": "DV 2"},
        ]

        wait_calls = {"count": 0}

        def _fake_wait(remaining, timeout, return_when):  # type: ignore[no-untyped-def]
            wait_calls["count"] += 1
            assert return_when == FIRST_COMPLETED
            assert timeout == analyzer._lock_health_poll_seconds
            first = next(iter(remaining))
            rest = set(remaining)
            rest.remove(first)
            return {first}, rest

        with (
            patch("cja_auto_sdr.org.analyzer.ThreadPoolExecutor", _FakeExecutor),
            patch("cja_auto_sdr.org.analyzer.wait", side_effect=_fake_wait),
            pytest.raises(LockOwnershipLostError),
        ):
            analyzer._fetch_all_data_views(data_views)

        executor = _FakeExecutor.last_instance
        assert executor is not None
        assert wait_calls["count"] == 1
        assert executor.shutdown_calls == [(False, True)]
        assert len(executor.submitted) == 2
        assert all(future.cancel_called for future in executor.submitted)

    def test_fetch_detects_lock_loss_while_waiting_for_futures(self):
        """Lock loss should be detected during wait timeouts before any future completes."""
        import logging
        from concurrent.futures import FIRST_COMPLETED

        class _FakeFuture:
            def __init__(self):
                self.cancel_called = False

            def result(self) -> DataViewSummary:
                return DataViewSummary(data_view_id="dv_x", data_view_name="DV X")

            def cancel(self) -> bool:
                self.cancel_called = True
                return True

        class _FakeExecutor:
            last_instance = None

            def __init__(self, *args, **kwargs):
                self.submitted = []
                self.shutdown_calls = []
                _FakeExecutor.last_instance = self

            def submit(self, fn, dv):  # type: ignore[no-untyped-def]
                future = _FakeFuture()
                self.submitted.append(future)
                return future

            def shutdown(self, wait=True, cancel_futures=False):  # type: ignore[no-untyped-def]
                self.shutdown_calls.append((wait, cancel_futures))

        mock_cja = Mock()
        logger = logging.getLogger("test_fetch_lock_loss_waiting")
        analyzer = OrgComponentAnalyzer(mock_cja, OrgReportConfig(quiet=True), logger)
        analyzer._assert_lock_healthy = Mock(
            side_effect=[
                None,
                LockOwnershipLostError("/tmp/test.lock", reason="heartbeat metadata write failed"),
            ],
        )

        data_views = [
            {"id": "dv_1", "name": "DV 1"},
            {"id": "dv_2", "name": "DV 2"},
        ]

        wait_calls = {"count": 0}

        def _fake_wait(remaining, timeout, return_when):  # type: ignore[no-untyped-def]
            wait_calls["count"] += 1
            assert return_when == FIRST_COMPLETED
            assert timeout == analyzer._lock_health_poll_seconds
            return set(), set(remaining)

        with (
            patch("cja_auto_sdr.org.analyzer.ThreadPoolExecutor", _FakeExecutor),
            patch("cja_auto_sdr.org.analyzer.wait", side_effect=_fake_wait),
            pytest.raises(LockOwnershipLostError),
        ):
            analyzer._fetch_all_data_views(data_views)

        executor = _FakeExecutor.last_instance
        assert executor is not None
        assert wait_calls["count"] == 1
        assert executor.shutdown_calls == [(False, True)]
        assert all(future.cancel_called for future in executor.submitted)


class TestOrgReportConfig:
    """Test OrgReportConfig dataclass"""

    def test_defaults(self):
        """Test default configuration values"""
        config = OrgReportConfig()
        assert config.filter_pattern is None
        assert config.exclude_pattern is None
        assert config.limit is None
        assert config.core_threshold == 0.5
        assert config.core_min_count is None
        assert config.overlap_threshold == 0.8
        assert config.summary_only is False
        assert config.verbose is False
        assert config.include_names is False
        assert config.skip_similarity is False

    def test_custom_thresholds(self):
        """Test custom threshold values"""
        config = OrgReportConfig(core_threshold=0.7, overlap_threshold=0.9, core_min_count=5)
        assert config.core_threshold == 0.7
        assert config.overlap_threshold == 0.9
        assert config.core_min_count == 5

    def test_filter_patterns(self):
        """Test filter and exclude patterns"""
        config = OrgReportConfig(filter_pattern="Prod.*", exclude_pattern="Test|Dev")
        assert config.filter_pattern == "Prod.*"
        assert config.exclude_pattern == "Test|Dev"


class TestComponentInfo:
    """Test ComponentInfo dataclass"""

    def test_presence_count(self):
        """Test presence_count property"""
        info = ComponentInfo(component_id="metric/test", component_type="metric", data_views={"dv_1", "dv_2", "dv_3"})
        assert info.presence_count == 3

    def test_empty_data_views(self):
        """Test with no data views"""
        info = ComponentInfo(component_id="dim/test", component_type="dimension")
        assert info.presence_count == 0

    def test_name_optional(self):
        """Test name field is optional"""
        info = ComponentInfo(component_id="metric/test", component_type="metric")
        assert info.name is None

        info_with_name = ComponentInfo(component_id="metric/test", component_type="metric", name="Test Metric")
        assert info_with_name.name == "Test Metric"


class TestDataViewSummary:
    """Test DataViewSummary dataclass"""

    def test_total_components(self):
        """Test total_components property"""
        summary = DataViewSummary(
            data_view_id="dv_123",
            data_view_name="Test DV",
            metric_ids={"m1", "m2", "m3"},
            dimension_ids={"d1", "d2"},
            metric_count=3,
            dimension_count=2,
        )
        assert summary.total_components == 5

    def test_all_component_ids(self):
        """Test all_component_ids property"""
        summary = DataViewSummary(
            data_view_id="dv_123",
            data_view_name="Test DV",
            metric_ids={"m1", "m2"},
            dimension_ids={"d1", "d2", "d3"},
        )
        assert summary.all_component_ids == {"m1", "m2", "d1", "d2", "d3"}

    def test_error_state(self):
        """Test error state"""
        summary = DataViewSummary(data_view_id="dv_error", data_view_name="Error DV", error="API Error")
        assert summary.error == "API Error"
        assert summary.has_error is True
        assert summary.normalized_error_reason == "API Error"
        assert summary.total_components == 0

    def test_blank_error_is_failed_with_unknown_reason(self):
        """Empty-string error should still be treated as failure."""
        summary = DataViewSummary(data_view_id="dv_error_blank", data_view_name="Error DV", error="")
        assert summary.has_error is True
        assert summary.normalized_error_reason == "Unknown error"

    def test_success_summary_has_no_error_reason(self):
        """Successful summaries should not expose failure reason text."""
        summary = DataViewSummary(data_view_id="dv_ok", data_view_name="Healthy DV")
        assert summary.has_error is False
        assert summary.normalized_error_reason is None


class TestSimilarityPair:
    """Test SimilarityPair dataclass"""

    def test_similarity_values(self):
        """Test similarity pair values"""
        pair = SimilarityPair(
            dv1_id="dv_1",
            dv1_name="DV One",
            dv2_id="dv_2",
            dv2_name="DV Two",
            jaccard_similarity=0.85,
            shared_count=17,
            union_count=20,
        )
        assert pair.jaccard_similarity == pytest.approx(0.85)
        assert pair.shared_count == 17
        assert pair.union_count == 20


class TestComponentDistribution:
    """Test ComponentDistribution dataclass"""

    def test_total_properties(self):
        """Test total calculation properties"""
        dist = ComponentDistribution(
            core_metrics=["m1", "m2"],
            core_dimensions=["d1"],
            common_metrics=["m3", "m4", "m5"],
            common_dimensions=["d2", "d3"],
            limited_metrics=["m6"],
            limited_dimensions=["d4", "d5", "d6"],
            isolated_metrics=["m7", "m8", "m9", "m10"],
            isolated_dimensions=["d7"],
        )
        assert dist.total_core == 3
        assert dist.total_common == 5
        assert dist.total_limited == 4
        assert dist.total_isolated == 5

    def test_empty_distribution(self):
        """Test empty distribution"""
        dist = ComponentDistribution()
        assert dist.total_core == 0
        assert dist.total_common == 0
        assert dist.total_limited == 0
        assert dist.total_isolated == 0


class TestOrgReportResult:
    """Test OrgReportResult dataclass"""

    def test_computed_properties(self):
        """Test computed result properties"""
        result = OrgReportResult(
            timestamp="2024-01-15T10:30:00",
            org_id="org_123",
            parameters=OrgReportConfig(),
            data_view_summaries=[
                DataViewSummary("dv_1", "DV 1", metric_count=10, dimension_count=20),
                DataViewSummary("dv_2", "DV 2", metric_count=15, dimension_count=25),
                DataViewSummary("dv_3", "DV 3", error="Failed"),
            ],
            component_index={
                "m1": ComponentInfo("m1", "metric", data_views={"dv_1", "dv_2"}),
                "m2": ComponentInfo("m2", "metric", data_views={"dv_1"}),
                "d1": ComponentInfo("d1", "dimension", data_views={"dv_1", "dv_2"}),
            },
            distribution=ComponentDistribution(),
            similarity_pairs=None,
            recommendations=[],
            duration=5.5,
        )
        assert result.total_data_views == 3
        assert result.successful_data_views == 2
        assert result.failed_data_views == 1
        assert result.failed_data_view_ids == ["dv_3"]
        assert result.total_unique_metrics == 2
        assert result.total_unique_dimensions == 1
        assert result.total_unique_components == 3

    def test_failed_reason_rollups_normalize_whitespace_and_empty_error(self):
        """Failed reason rollups should normalize whitespace and classify empty messages."""
        result = OrgReportResult(
            timestamp="2024-01-15T10:30:00",
            org_id="org_123",
            parameters=OrgReportConfig(),
            data_view_summaries=[
                DataViewSummary("dv_1", "DV 1", error="Timeout   while\nfetching"),
                DataViewSummary("dv_2", "DV 2", error="Timeout while fetching"),
                DataViewSummary("dv_3", "DV 3", error=""),
                DataViewSummary("dv_4", "DV 4", metric_count=3, dimension_count=2),
            ],
            component_index={},
            distribution=ComponentDistribution(),
            similarity_pairs=None,
            recommendations=[],
            duration=1.2,
        )

        assert result.successful_data_views == 1
        assert result.failed_data_views == 3
        assert result.failed_data_view_ids == ["dv_1", "dv_2", "dv_3"]
        assert result.failed_data_view_reason_counts == {
            "Timeout while fetching": 2,
            "Unknown error": 1,
        }


class TestDistributionBar:
    """Test _render_distribution_bar utility function"""

    def test_full_bar(self):
        """Test 100% bar"""
        bar = _render_distribution_bar(100, 100, width=10)
        assert "100%" in bar
        assert bar.startswith("██████████")

    def test_half_bar(self):
        """Test 50% bar"""
        bar = _render_distribution_bar(50, 100, width=10)
        assert "50%" in bar

    def test_empty_bar(self):
        """Test 0% bar"""
        bar = _render_distribution_bar(0, 100, width=10)
        assert "0%" in bar
        assert "░░░░░░░░░░" in bar

    def test_zero_total(self):
        """Test with zero total"""
        bar = _render_distribution_bar(5, 0, width=10)
        assert "0%" in bar


class TestOrgComponentAnalyzer:
    """Test OrgComponentAnalyzer class"""

    @pytest.fixture
    def mock_cja(self):
        """Create mock CJA client"""
        return Mock()

    @pytest.fixture
    def mock_logger(self):
        """Create mock logger"""
        import logging

        return logging.getLogger("test")

    def test_compute_distribution_buckets(self, mock_cja, mock_logger):
        """Test component distribution bucket classification"""
        config = OrgReportConfig(core_threshold=0.5)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        # Create component index with 20 data views
        # Core: in 10+ DVs (50%)
        # Common: in 5-9 DVs (25-49%)
        # Limited: in 2-4 DVs (<25% but >=2)
        # Isolated: in 1 DV
        component_index = {
            "m_core": ComponentInfo("m_core", "metric", data_views={"dv_" + str(i) for i in range(12)}),
            "m_common": ComponentInfo("m_common", "metric", data_views={"dv_" + str(i) for i in range(6)}),
            "m_limited": ComponentInfo("m_limited", "metric", data_views={"dv_1", "dv_2", "dv_3"}),
            "m_isolated": ComponentInfo("m_isolated", "metric", data_views={"dv_1"}),
            "d_core": ComponentInfo("d_core", "dimension", data_views={"dv_" + str(i) for i in range(15)}),
            "d_isolated": ComponentInfo("d_isolated", "dimension", data_views={"dv_5"}),
        }

        distribution = analyzer._compute_distribution(component_index, total_dvs=20)

        assert "m_core" in distribution.core_metrics
        assert "d_core" in distribution.core_dimensions
        assert "m_common" in distribution.common_metrics
        assert "m_limited" in distribution.limited_metrics
        assert "m_isolated" in distribution.isolated_metrics
        assert "d_isolated" in distribution.isolated_dimensions

    def test_fetch_components_counts_derived_without_type_column(self, mock_cja, mock_logger):
        """sourceFieldType must still drive derived counts when type column is absent."""
        config = OrgReportConfig(include_component_types=True, cja_per_thread=False)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        mock_cja.getMetrics.return_value = pd.DataFrame(
            [
                {"id": "m_derived", "name": "Derived Metric", "sourceFieldType": "derived"},
                {"id": "m_standard", "name": "Standard Metric", "sourceFieldType": "field"},
            ],
        )
        mock_cja.getDimensions.return_value = pd.DataFrame(
            [
                {"id": "d_derived", "name": "Derived Dimension", "sourceFieldType": "derived"},
                {"id": "d_standard", "name": "Standard Dimension", "sourceFieldType": "custom"},
            ],
        )

        summary = analyzer._fetch_data_view_components({"id": "dv_1", "name": "DV 1"})

        assert summary.error is None
        assert summary.derived_metric_count == 1
        assert summary.standard_metric_count == 1
        assert summary.derived_dimension_count == 1
        assert summary.standard_dimension_count == 1

    def test_compute_distribution_with_min_count(self, mock_cja, mock_logger):
        """Test core_min_count overrides threshold"""
        config = OrgReportConfig(core_threshold=0.5, core_min_count=3)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        component_index = {
            "m1": ComponentInfo("m1", "metric", data_views={"dv_1", "dv_2", "dv_3"}),  # In 3 DVs
            "m2": ComponentInfo("m2", "metric", data_views={"dv_1", "dv_2"}),  # In 2 DVs
        }

        distribution = analyzer._compute_distribution(component_index, total_dvs=10)

        # m1 should be core (3 >= core_min_count of 3)
        assert "m1" in distribution.core_metrics
        # m2 should not be core
        assert "m2" not in distribution.core_metrics

    def test_compute_similarity_matrix(self, mock_cja, mock_logger):
        """Test Jaccard similarity calculation"""
        config = OrgReportConfig(overlap_threshold=0.5)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        summaries = [
            DataViewSummary("dv_1", "DV 1", metric_ids={"m1", "m2", "m3"}, dimension_ids={"d1", "d2"}),
            DataViewSummary("dv_2", "DV 2", metric_ids={"m1", "m2", "m4"}, dimension_ids={"d1", "d3"}),
        ]

        # DV1 components: {m1, m2, m3, d1, d2} = 5
        # DV2 components: {m1, m2, m4, d1, d3} = 5
        # Intersection: {m1, m2, d1} = 3
        # Union: {m1, m2, m3, m4, d1, d2, d3} = 7
        # Jaccard = 3/7 = 0.4286

        pairs = analyzer._compute_similarity_matrix(summaries)

        # Should return empty because 0.4286 < 0.5 threshold
        assert len(pairs) == 0

        # Lower threshold to include this pair
        config.overlap_threshold = 0.4
        pairs = analyzer._compute_similarity_matrix(summaries)
        assert len(pairs) == 1
        assert pairs[0].jaccard_similarity == pytest.approx(3 / 7, abs=0.01)

    def test_similarity_with_error_summaries(self, mock_cja, mock_logger):
        """Test similarity skips error summaries"""
        config = OrgReportConfig(overlap_threshold=0.0)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        summaries = [
            DataViewSummary("dv_1", "DV 1", metric_ids={"m1"}, dimension_ids=set()),
            DataViewSummary("dv_2", "DV 2", error="API Error"),
            DataViewSummary("dv_3", "DV 3", metric_ids={"m1"}, dimension_ids=set()),
        ]

        pairs = analyzer._compute_similarity_matrix(summaries)

        # Only dv_1 and dv_3 should be compared (dv_2 has error)
        assert len(pairs) == 1
        assert pairs[0].dv1_id == "dv_1"
        assert pairs[0].dv2_id == "dv_3"

    def test_similarity_includes_governance_threshold_pairs(self, mock_cja, mock_logger):
        """Test >=0.9 pairs are included even when overlap threshold is higher"""
        config = OrgReportConfig(overlap_threshold=0.95)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        summaries = [
            DataViewSummary(
                "dv_1",
                "DV 1",
                metric_ids={f"m{i}" for i in range(1, 11)},
                dimension_ids={"d1", "d2"},
            ),
            DataViewSummary(
                "dv_2",
                "DV 2",
                metric_ids={f"m{i}" for i in range(1, 11)},
                dimension_ids={"d1", "d2", "d3"},
            ),
        ]

        # Jaccard = 12 / 13 = 0.923..., below overlap_threshold 0.95 but above 0.9
        pairs = analyzer._compute_similarity_matrix(summaries)
        assert len(pairs) == 1
        assert pairs[0].jaccard_similarity == pytest.approx(12 / 13, abs=0.01)

    def test_similarity_excludes_below_governance_floor(self, mock_cja, mock_logger):
        """Test pairs below 0.9 remain excluded when overlap threshold is higher"""
        config = OrgReportConfig(overlap_threshold=0.95)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        summaries = [
            DataViewSummary(
                "dv_1",
                "DV 1",
                metric_ids={f"m{i}" for i in range(1, 9)},
                dimension_ids=set(),
            ),
            DataViewSummary(
                "dv_2",
                "DV 2",
                metric_ids={f"m{i}" for i in range(1, 10)},
                dimension_ids=set(),
            ),
        ]

        # Jaccard = 8 / 9 = 0.888..., below 0.9 and should be excluded
        pairs = analyzer._compute_similarity_matrix(summaries)
        assert len(pairs) == 0

    def test_similarity_drift_included_for_governance_pairs(self, mock_cja, mock_logger):
        """Test drift details are captured for >=0.9 pairs included via governance floor"""
        config = OrgReportConfig(overlap_threshold=0.95, include_drift=True)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        summaries = [
            DataViewSummary(
                "dv_1",
                "DV 1",
                metric_ids={f"m{i}" for i in range(1, 11)},
                dimension_ids=set(),
            ),
            DataViewSummary(
                "dv_2",
                "DV 2",
                metric_ids={f"m{i}" for i in range(1, 12)},
                dimension_ids=set(),
            ),
        ]

        # Jaccard = 10 / 11 = 0.909..., included by governance floor
        pairs = analyzer._compute_similarity_matrix(summaries)
        assert len(pairs) == 1
        assert pairs[0].only_in_dv1 == []
        assert pairs[0].only_in_dv2 == ["m11"]

    def test_similarity_logging_uses_effective_threshold(self, mock_cja):
        """Test run_analysis logs effective threshold when overlap threshold exceeds 0.9"""
        config = OrgReportConfig(overlap_threshold=0.95)
        mock_logger = Mock()
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        with (
            patch.object(
                analyzer,
                "_list_and_filter_data_views",
                return_value=([{"id": "dv_1", "name": "DV 1"}], False, 1),
            ),
            patch.object(
                analyzer,
                "_fetch_all_data_views",
                return_value=[DataViewSummary("dv_1", "DV 1", metric_ids={"m1"}, dimension_ids=set())],
            ),
            patch.object(analyzer, "_build_component_index", return_value={}),
            patch.object(analyzer, "_compute_distribution", return_value=ComponentDistribution()),
            patch.object(
                analyzer,
                "_compute_similarity_matrix",
                return_value=[SimilarityPair("dv_1", "DV 1", "dv_2", "DV 2", 0.91, 10, 11)],
            ),
            patch.object(analyzer, "_generate_recommendations", return_value=[]),
        ):
            analyzer.run_analysis()

        assert any("pairs above threshold (>= 0.9)" in str(call.args[0]) for call in mock_logger.info.call_args_list)

    def test_similarity_includes_exact_ninety_percent(self, mock_cja, mock_logger):
        """Test exact 0.9 similarity is included when overlap threshold is higher"""
        config = OrgReportConfig(overlap_threshold=0.95)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        summaries = [
            DataViewSummary(
                "dv_1",
                "DV 1",
                metric_ids={f"m{i}" for i in range(1, 10)},
                dimension_ids=set(),
            ),
            DataViewSummary(
                "dv_2",
                "DV 2",
                metric_ids={f"m{i}" for i in range(1, 10)} | {"m10"},
                dimension_ids=set(),
            ),
        ]

        # Jaccard = 9 / 10 = 0.9
        pairs = analyzer._compute_similarity_matrix(summaries)
        assert len(pairs) == 1
        assert pairs[0].jaccard_similarity == pytest.approx(0.9, abs=0.0001)

    def test_similarity_guardrail_skips_matrix(self, mock_cja, mock_logger):
        """Guardrail should skip similarity when DV count exceeds limit."""
        config = OrgReportConfig(similarity_max_dvs=1)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        data_views = [{"id": "dv_1", "name": "DV 1"}, {"id": "dv_2", "name": "DV 2"}]
        summaries = [
            DataViewSummary("dv_1", "DV 1", metric_ids={"m1"}, dimension_ids=set()),
            DataViewSummary("dv_2", "DV 2", metric_ids={"m2"}, dimension_ids=set()),
        ]

        with (
            patch.object(analyzer, "_list_and_filter_data_views", return_value=(data_views, False, 2)),
            patch.object(analyzer, "_fetch_all_data_views", return_value=summaries),
            patch.object(analyzer, "_build_component_index", return_value={}),
            patch.object(analyzer, "_compute_distribution", return_value=ComponentDistribution()),
            patch.object(analyzer, "_generate_recommendations", return_value=[]),
            patch.object(analyzer, "_compute_similarity_matrix") as compute_similarity,
        ):
            result = analyzer.run_analysis()

        assert result.similarity_pairs is None
        compute_similarity.assert_not_called()

    def test_similarity_guardrail_force_override(self, mock_cja, mock_logger):
        """Force flag should override similarity guardrail."""
        config = OrgReportConfig(similarity_max_dvs=1, force_similarity=True)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        data_views = [{"id": "dv_1", "name": "DV 1"}, {"id": "dv_2", "name": "DV 2"}]
        summaries = [
            DataViewSummary("dv_1", "DV 1", metric_ids={"m1"}, dimension_ids=set()),
            DataViewSummary("dv_2", "DV 2", metric_ids={"m2"}, dimension_ids=set()),
        ]

        with (
            patch.object(analyzer, "_list_and_filter_data_views", return_value=(data_views, False, 2)),
            patch.object(analyzer, "_fetch_all_data_views", return_value=summaries),
            patch.object(analyzer, "_build_component_index", return_value={}),
            patch.object(analyzer, "_compute_distribution", return_value=ComponentDistribution()),
            patch.object(analyzer, "_generate_recommendations", return_value=[]),
            patch.object(analyzer, "_compute_similarity_matrix", return_value=[]) as compute_similarity,
        ):
            result = analyzer.run_analysis()

        assert result.similarity_pairs == []
        compute_similarity.assert_called_once()

    def test_cache_put_many_used_for_batch(self, mock_cja, mock_logger):
        """Cache writes should batch via put_many to avoid per-DV disk writes."""
        config = OrgReportConfig(use_cache=True)
        cache = Mock()
        cache.get.return_value = None

        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger, cache=cache)

        data_views = [
            {"id": "dv_1", "name": "DV 1"},
            {"id": "dv_2", "name": "DV 2"},
        ]

        summaries = [
            DataViewSummary("dv_1", "DV 1", metric_ids={"m1"}, dimension_ids=set()),
            DataViewSummary("dv_2", "DV 2", metric_ids={"m2"}, dimension_ids=set()),
        ]

        with patch.object(analyzer, "_fetch_data_view_components", side_effect=summaries):
            analyzer._fetch_all_data_views(data_views)

        cache.put_many.assert_called_once()
        cache.put.assert_not_called()

    def test_run_analysis_recommends_high_overlap_from_floor(self, mock_cja, mock_logger):
        """Test run_analysis emits overlap recommendations from >=0.9 floor"""
        config = OrgReportConfig(overlap_threshold=0.95)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        summaries = [
            DataViewSummary(
                "dv_1",
                "DV 1",
                metric_ids={f"m{i}" for i in range(1, 11)},
                dimension_ids={"d1", "d2"},
            ),
            DataViewSummary(
                "dv_2",
                "DV 2",
                metric_ids={f"m{i}" for i in range(1, 11)},
                dimension_ids={"d1", "d2", "d3"},
            ),
        ]

        with (
            patch.object(
                analyzer,
                "_list_and_filter_data_views",
                return_value=([{"id": "dv_1", "name": "DV 1"}, {"id": "dv_2", "name": "DV 2"}], False, 2),
            ),
            patch.object(analyzer, "_fetch_all_data_views", return_value=summaries),
            patch.object(analyzer, "_build_component_index", return_value={}),
            patch.object(analyzer, "_compute_distribution", return_value=ComponentDistribution()),
        ):
            result = analyzer.run_analysis()

        overlap_recs = [r for r in result.recommendations if r.get("type") == "review_overlap"]
        assert len(overlap_recs) == 1
        assert overlap_recs[0]["data_view_1"] == "dv_1"
        assert overlap_recs[0]["data_view_2"] == "dv_2"

    def test_filter_data_views(self, mock_cja, mock_logger):
        """Test data view filtering with regex"""
        mock_cja.getDataViews.return_value = pd.DataFrame(
            [
                {"id": "dv_1", "name": "Production DV"},
                {"id": "dv_2", "name": "Test DV"},
                {"id": "dv_3", "name": "Prod Analytics"},
                {"id": "dv_4", "name": "Dev Sandbox"},
            ],
        )

        config = OrgReportConfig(filter_pattern="Prod.*")
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        result, is_sampled, _total_available = analyzer._list_and_filter_data_views()

        assert len(result) == 2
        assert is_sampled is False
        names = [dv["name"] for dv in result]
        assert "Production DV" in names
        assert "Prod Analytics" in names

    def test_exclude_data_views(self, mock_cja, mock_logger):
        """Test data view exclusion with regex"""
        mock_cja.getDataViews.return_value = pd.DataFrame(
            [
                {"id": "dv_1", "name": "Production DV"},
                {"id": "dv_2", "name": "Test DV"},
                {"id": "dv_3", "name": "Prod Analytics"},
                {"id": "dv_4", "name": "Dev Sandbox"},
            ],
        )

        config = OrgReportConfig(exclude_pattern="Test|Dev")
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        result, is_sampled, _total_available = analyzer._list_and_filter_data_views()

        assert len(result) == 2
        assert is_sampled is False
        names = [dv["name"] for dv in result]
        assert "Production DV" in names
        assert "Prod Analytics" in names
        assert "Test DV" not in names
        assert "Dev Sandbox" not in names

    def test_limit_data_views(self, mock_cja, mock_logger):
        """Test data view limit"""
        mock_cja.getDataViews.return_value = pd.DataFrame([{"id": f"dv_{i}", "name": f"DV {i}"} for i in range(10)])

        config = OrgReportConfig(limit=3)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        result, _is_sampled, total_available = analyzer._list_and_filter_data_views()

        assert len(result) == 3
        assert total_available == 10

    def test_generate_recommendations_isolated(self, mock_cja, mock_logger):
        """Test recommendations for isolated components"""
        config = OrgReportConfig()
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        summaries = [
            DataViewSummary("dv_1", "Specialized DV", metric_count=100, dimension_count=50),
            DataViewSummary("dv_2", "Normal DV", metric_count=20, dimension_count=30),
        ]

        # dv_1 has 25 isolated components
        component_index = {
            f"isolated_{i}": ComponentInfo(f"isolated_{i}", "metric", data_views={"dv_1"}) for i in range(25)
        }

        distribution = ComponentDistribution()
        recommendations = analyzer._generate_recommendations(summaries, component_index, distribution, None)

        # Should have recommendation about isolated components
        isolated_rec = [r for r in recommendations if r["type"] == "review_isolated"]
        assert len(isolated_rec) == 1
        assert isolated_rec[0]["data_view"] == "dv_1"
        assert isolated_rec[0]["isolated_count"] == 25

    def test_generate_recommendations_high_overlap(self, mock_cja, mock_logger):
        """Test recommendations for high overlap pairs"""
        config = OrgReportConfig()
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        summaries = []
        component_index = {}
        distribution = ComponentDistribution()

        similarity_pairs = [SimilarityPair("dv_1", "Prod DV", "dv_2", "Prod DV Copy", 0.95, 190, 200)]

        recommendations = analyzer._generate_recommendations(summaries, component_index, distribution, similarity_pairs)

        overlap_rec = [r for r in recommendations if r["type"] == "review_overlap"]
        assert len(overlap_rec) == 1
        assert overlap_rec[0]["similarity"] == pytest.approx(0.95)

    def test_generate_recommendations_stale_data_view_with_metadata(self, mock_cja, mock_logger):
        """Stale recommendation should be generated for old metadata timestamps."""
        config = OrgReportConfig(include_metadata=True)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        summaries = [
            DataViewSummary(
                "dv_stale",
                "Legacy DV",
                metric_count=10,
                dimension_count=5,
                modified="2000-01-01T00:00:00Z",
                has_description=True,
            ),
        ]

        recommendations = analyzer._generate_recommendations(
            summaries,
            {},
            ComponentDistribution(),
            None,
        )

        stale_recs = [rec for rec in recommendations if rec.get("type") == "stale_data_view"]
        assert len(stale_recs) == 1
        assert stale_recs[0]["data_view"] == "dv_stale"

    def test_missing_description_threshold_uses_successful_data_view_count(self, mock_cja, mock_logger):
        """Description recommendation denominator should exclude errored fetches."""
        config = OrgReportConfig(include_metadata=True)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        summaries = [
            DataViewSummary(
                "dv_1",
                "Healthy DV A",
                metric_count=10,
                dimension_count=5,
                has_description=False,
            ),
            DataViewSummary(
                "dv_2",
                "Healthy DV B",
                metric_count=10,
                dimension_count=5,
                has_description=True,
            ),
            DataViewSummary("dv_err_1", "Errored DV 1", error="permission denied"),
            DataViewSummary("dv_err_2", "Errored DV 2", error="timeout"),
            DataViewSummary("dv_err_3", "Errored DV 3", error="timeout"),
            DataViewSummary("dv_err_4", "Errored DV 4", error="timeout"),
        ]

        recommendations = analyzer._generate_recommendations(
            summaries,
            {},
            ComponentDistribution(),
            None,
        )

        missing_desc_recs = [rec for rec in recommendations if rec.get("type") == "missing_descriptions"]
        assert len(missing_desc_recs) == 1
        assert missing_desc_recs[0]["count"] == 1


class TestOutputWriters:
    """Test output writer functions"""

    @pytest.fixture
    def sample_result(self):
        """Create sample OrgReportResult for testing"""
        return OrgReportResult(
            timestamp="2024-01-15T10:30:00",
            org_id="org_123",
            parameters=OrgReportConfig(core_threshold=0.5, overlap_threshold=0.8),
            data_view_summaries=[
                DataViewSummary(
                    "dv_1",
                    "Production DV",
                    metric_ids={"m1", "m2"},
                    dimension_ids={"d1"},
                    metric_count=2,
                    dimension_count=1,
                ),
                DataViewSummary(
                    "dv_2",
                    "Staging DV",
                    metric_ids={"m1"},
                    dimension_ids={"d1", "d2"},
                    metric_count=1,
                    dimension_count=2,
                ),
            ],
            component_index={
                "m1": ComponentInfo("m1", "metric", data_views={"dv_1", "dv_2"}),
                "m2": ComponentInfo("m2", "metric", data_views={"dv_1"}),
                "d1": ComponentInfo("d1", "dimension", data_views={"dv_1", "dv_2"}),
                "d2": ComponentInfo("d2", "dimension", data_views={"dv_2"}),
            },
            distribution=ComponentDistribution(
                core_metrics=["m1"],
                core_dimensions=["d1"],
                isolated_metrics=["m2"],
                isolated_dimensions=["d2"],
            ),
            similarity_pairs=[SimilarityPair("dv_1", "Production DV", "dv_2", "Staging DV", 0.6, 2, 4)],
            recommendations=[{"type": "test_recommendation", "severity": "low", "reason": "Test reason"}],
            duration=1.5,
        )

    def test_json_output_structure(self, sample_result):
        """Test JSON output has correct structure"""
        import logging

        logger = logging.getLogger("test")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = write_org_report_json(sample_result, None, tmpdir, logger)

            with open(output_path) as f:
                data = json.load(f)

            # Check for required top-level keys (actual structure)
            assert "report_type" in data
            assert "summary" in data
            assert "data_views" in data
            assert "component_index" in data
            assert "distribution" in data
            assert "recommendations" in data

            assert data["generated_at"] == "2024-01-15T10:30:00"
            assert data["summary"]["data_views_total"] == 2
            assert data["summary"]["total_unique_components"] == 4

    def test_markdown_output_structure(self, sample_result):
        """Test Markdown output has correct sections"""
        import logging

        logger = logging.getLogger("test")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = write_org_report_markdown(sample_result, None, tmpdir, logger)

            with open(output_path) as f:
                content = f.read()

            # Check for required sections
            assert "# Org-Wide Component Analysis Report" in content
            assert "## Summary" in content
            assert "## Component Distribution" in content
            assert "## Data Views" in content
            assert "## Core Components" in content
            assert "## Recommendations" in content

            # Check for data
            assert "Production DV" in content
            assert "Staging DV" in content

    def test_html_output_structure(self, sample_result):
        """Test HTML output has correct structure"""
        import logging

        logger = logging.getLogger("test")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = write_org_report_html(sample_result, None, tmpdir, logger)

            with open(output_path) as f:
                content = f.read()

            # Check for required HTML elements
            assert "<!DOCTYPE html>" in content
            assert "Org-Wide Component Analysis Report" in content
            assert "Component Distribution" in content
            assert "Data Views" in content

            # Check for data
            assert "Production DV" in content
            assert "Staging DV" in content

            # Check for stats
            assert "Unique Metrics" in content
            assert "Unique Dimensions" in content

    def test_csv_output_structure(self, sample_result):
        """Test CSV output creates correct files"""
        import logging
        import os

        logger = logging.getLogger("test")

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_dir = write_org_report_csv(sample_result, None, tmpdir, logger)

            # Check directory was created
            assert os.path.isdir(csv_dir)

            # Check for required CSV files
            assert os.path.exists(os.path.join(csv_dir, "org_report_summary.csv"))
            assert os.path.exists(os.path.join(csv_dir, "org_report_data_views.csv"))
            assert os.path.exists(os.path.join(csv_dir, "org_report_components.csv"))
            assert os.path.exists(os.path.join(csv_dir, "org_report_distribution.csv"))

            # Check similarity file exists (since sample has similarity pairs)
            assert os.path.exists(os.path.join(csv_dir, "org_report_similarity.csv"))

            # Read and verify summary CSV content
            summary_df = pd.read_csv(os.path.join(csv_dir, "org_report_summary.csv"))
            assert summary_df["Total Data Views"].iloc[0] == 2
            assert summary_df["Total Unique Components"].iloc[0] == 4

            # Read and verify components CSV
            comp_df = pd.read_csv(os.path.join(csv_dir, "org_report_components.csv"))
            assert len(comp_df) == 4  # 4 components in sample
            assert "m1" in comp_df["Component ID"].values

    def test_html_recommendations_include_context_details(self, sample_result):
        """HTML recommendations should include full data-view and pair context."""
        import logging

        logger = logging.getLogger("test")
        sample_result.recommendations = [
            {
                "type": "review_isolated",
                "severity": "MEDIUM",
                "reason": "Investigate isolated components.",
                "data_view": "dv_1",
                "data_view_name": "Prod <Main>",
                "isolated_count": 42,
            },
            {
                "type": "review_overlap",
                "severity": "high",
                "reason": "Potential duplicate pair.",
                "data_view_1": "dv_1",
                "data_view_1_name": "Prod | Main",
                "data_view_2": "dv_2",
                "data_view_2_name": "Staging `Copy`",
                "similarity": 0.95,
                "drift_count": 7,
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = write_org_report_html(sample_result, None, tmpdir, logger)
            with open(output_path, encoding="utf-8") as f:
                content = f.read()

        assert "<strong>Data View:</strong> Prod &lt;Main&gt; (dv_1)" in content
        assert "<strong>Pair:</strong> Prod | Main (dv_1) ↔ Staging `Copy` (dv_2)" in content
        assert "<strong>Similarity:</strong> 95.0%" in content
        assert "<strong>Isolated Count:</strong> 42" in content
        assert "<strong>Drift Count:</strong> 7" in content

    def test_markdown_recommendations_include_context_details(self, sample_result):
        """Markdown recommendations should include IDs and escaped context values."""
        import logging

        logger = logging.getLogger("test")
        sample_result.recommendations = [
            {
                "type": "review_overlap",
                "severity": "high",
                "reason": "Potential duplicate pair.",
                "data_view_1": "dv_1",
                "data_view_1_name": "Prod | Main",
                "data_view_2": "dv_2",
                "data_view_2_name": "Staging `Copy`",
                "similarity": 0.95,
                "drift_count": 7,
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = write_org_report_markdown(sample_result, None, tmpdir, logger)
            with open(output_path, encoding="utf-8") as f:
                content = f.read()

        assert "- **Pair:** Prod \\| Main (dv_1) ↔ Staging \\`Copy\\` (dv_2)" in content
        assert "- **Similarity:** 95.0%" in content
        assert "- **Drift Count:** 7" in content

    def test_json_recommendations_include_context_payload(self, sample_result):
        """JSON recommendations should preserve structured context metadata."""
        import logging

        logger = logging.getLogger("test")
        sample_result.recommendations = [
            {
                "type": "review_isolated",
                "severity": "MEDIUM",
                "reason": "Investigate isolated components.",
                "data_view": "dv_1",
                "data_view_name": "Prod Main",
                "isolated_count": 42,
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = write_org_report_json(sample_result, None, tmpdir, logger)
            with open(output_path, encoding="utf-8") as f:
                payload = json.load(f)

        rec = payload["recommendations"][0]
        assert rec["severity"] == "medium"
        labels = {entry["label"]: entry["value"] for entry in rec.get("context", [])}
        assert labels["Data View"] == "Prod Main (dv_1)"
        assert labels["Isolated Count"] == "42"

    def test_json_recommendations_coerce_non_serializable_values(self, sample_result):
        """JSON recommendations should serialize odd value types safely."""
        import logging

        logger = logging.getLogger("test")
        sample_result.recommendations = [
            {
                "type": None,
                "severity": "CRITICAL",
                "reason": "Includes non-serializable value",
                "extra_timestamp": datetime(2024, 1, 15, 12, 0, 0),
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = write_org_report_json(sample_result, None, tmpdir, logger)
            with open(output_path, encoding="utf-8") as f:
                payload = json.load(f)

        rec = payload["recommendations"][0]
        assert rec["severity"] == "low"
        assert rec["type"] is None
        assert isinstance(rec["extra_timestamp"], str)

    def test_csv_recommendations_include_pair_columns(self, sample_result):
        """CSV recommendation export should include full pair context columns."""
        import logging

        logger = logging.getLogger("test")
        sample_result.recommendations = [
            {
                "type": "review_overlap",
                "severity": "high",
                "reason": "Potential duplicate pair.",
                "data_view_1": "dv_1",
                "data_view_1_name": "Production",
                "data_view_2": "dv_2",
                "data_view_2_name": "Staging",
                "similarity": 0.95,
                "drift_count": 7,
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            csv_dir = write_org_report_csv(sample_result, None, tmpdir, logger)
            rec_df = pd.read_csv(Path(csv_dir) / "org_report_recommendations.csv")

        assert "Data View 1 ID" in rec_df.columns
        assert "Data View 2 ID" in rec_df.columns
        assert "Extra Details" in rec_df.columns
        assert rec_df.iloc[0]["Data View 1 ID"] == "dv_1"
        assert rec_df.iloc[0]["Data View 2 ID"] == "dv_2"
        assert rec_df.iloc[0]["Drift Count"] == 7

    def test_excel_recommendations_include_context_headers(self, sample_result):
        """Excel recommendations sheet should include pair/context columns."""
        import logging

        logger = logging.getLogger("test")
        sample_result.recommendations = [
            {
                "type": "review_overlap",
                "severity": "high",
                "reason": "Potential duplicate pair.",
                "data_view_1": "dv_1",
                "data_view_1_name": "Production",
                "data_view_2": "dv_2",
                "data_view_2_name": "Staging",
                "similarity": 0.95,
            },
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = write_org_report_excel(sample_result, None, tmpdir, logger)
            shared_strings = _get_excel_shared_strings(output_path)

        assert "Data View 1 ID" in shared_strings
        assert "Data View 2 ID" in shared_strings
        assert "Similarity" in shared_strings
        assert "Extra Details" in shared_strings


class TestIncludeNames:
    """Test --include-names functionality"""

    def test_data_view_summary_with_names(self):
        """Test DataViewSummary stores component names"""
        summary = DataViewSummary(
            data_view_id="dv_1",
            data_view_name="Test DV",
            metric_ids={"m1", "m2"},
            dimension_ids={"d1"},
            metric_count=2,
            dimension_count=1,
            metric_names={"m1": "Page Views", "m2": "Visits"},
            dimension_names={"d1": "Page Name"},
        )
        assert summary.get_component_name("m1") == "Page Views"
        assert summary.get_component_name("d1") == "Page Name"
        assert summary.get_component_name("unknown") is None

    def test_component_index_captures_names(self):
        """Test _build_component_index includes names"""
        import logging

        mock_cja = Mock()
        mock_logger = logging.getLogger("test")

        config = OrgReportConfig(include_names=True)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        summaries = [
            DataViewSummary(
                "dv_1",
                "DV 1",
                metric_ids={"m1", "m2"},
                dimension_ids={"d1"},
                metric_names={"m1": "Page Views", "m2": "Visits"},
                dimension_names={"d1": "Page Name"},
            ),
            DataViewSummary(
                "dv_2",
                "DV 2",
                metric_ids={"m1"},
                dimension_ids={"d2"},
                metric_names={"m1": "Page Views"},  # Same name for m1
                dimension_names={"d2": "Browser"},
            ),
        ]

        index = analyzer._build_component_index(summaries)

        # Check names are populated
        assert index["m1"].name == "Page Views"
        assert index["m2"].name == "Visits"
        assert index["d1"].name == "Page Name"
        assert index["d2"].name == "Browser"

    def test_component_without_names(self):
        """Test index works without names"""
        import logging

        mock_cja = Mock()
        mock_logger = logging.getLogger("test")

        config = OrgReportConfig(include_names=False)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        summaries = [
            DataViewSummary(
                "dv_1",
                "DV 1",
                metric_ids={"m1"},
                dimension_ids={"d1"},
                # No names provided
            ),
        ]

        index = analyzer._build_component_index(summaries)

        assert index["m1"].name is None
        assert index["d1"].name is None


class TestEdgeCases:
    """Test edge cases and error handling"""

    @pytest.fixture
    def mock_cja(self):
        return Mock()

    @pytest.fixture
    def mock_logger(self):
        import logging

        return logging.getLogger("test")

    def test_empty_org(self, mock_cja, mock_logger):
        """Test handling of empty organization"""
        mock_cja.getDataViews.return_value = pd.DataFrame()

        config = OrgReportConfig()
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        result, _is_sampled, total_available = analyzer._list_and_filter_data_views()
        assert len(result) == 0
        assert total_available == 0

    def test_single_data_view(self, mock_cja, mock_logger):
        """Test with single data view (no similarity pairs)"""
        config = OrgReportConfig()
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        summaries = [DataViewSummary("dv_1", "Only DV", metric_ids={"m1", "m2"}, dimension_ids={"d1"})]

        pairs = analyzer._compute_similarity_matrix(summaries)
        assert len(pairs) == 0

    def test_all_fetches_fail(self, mock_cja, mock_logger):
        """Test when all data view fetches fail"""
        config = OrgReportConfig()
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        summaries = [
            DataViewSummary("dv_1", "DV 1", error="API Error 1"),
            DataViewSummary("dv_2", "DV 2", error="API Error 2"),
        ]

        component_index = analyzer._build_component_index(summaries)
        assert len(component_index) == 0

        distribution = analyzer._compute_distribution(component_index, total_dvs=2)
        assert distribution.total_core == 0
        assert distribution.total_isolated == 0

    def test_empty_data_views(self, mock_cja, mock_logger):
        """Test data views with no components"""
        config = OrgReportConfig()
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        summaries = [
            DataViewSummary("dv_1", "Empty DV 1", metric_ids=set(), dimension_ids=set()),
            DataViewSummary("dv_2", "Empty DV 2", metric_ids=set(), dimension_ids=set()),
        ]

        pairs = analyzer._compute_similarity_matrix(summaries)
        # Empty sets have undefined Jaccard similarity, should be skipped
        assert len(pairs) == 0

    def test_invalid_regex_filter(self, mock_cja, mock_logger):
        """Test handling of invalid regex pattern"""
        mock_cja.getDataViews.return_value = pd.DataFrame([{"id": "dv_1", "name": "Test DV"}])

        # Invalid regex (unclosed bracket)
        config = OrgReportConfig(filter_pattern="[invalid")
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        # Should handle gracefully and return all DVs
        result, _is_sampled, _total_available = analyzer._list_and_filter_data_views()
        assert len(result) == 1  # Falls back to unfiltered


class TestNewOrgReportConfig:
    """Test new OrgReportConfig options"""

    def test_component_types_default_enabled(self):
        """Test component types enabled by default"""
        config = OrgReportConfig()
        assert config.include_component_types is True

    def test_metadata_default_disabled(self):
        """Test metadata disabled by default"""
        config = OrgReportConfig()
        assert config.include_metadata is False

    def test_drift_default_disabled(self):
        """Test drift disabled by default"""
        config = OrgReportConfig()
        assert config.include_drift is False

    def test_sampling_options(self):
        """Test sampling options"""
        config = OrgReportConfig(sample_size=10, sample_seed=42, sample_stratified=True)
        assert config.sample_size == 10
        assert config.sample_seed == 42
        assert config.sample_stratified is True

    def test_caching_options(self):
        """Test caching options"""
        config = OrgReportConfig(use_cache=True, cache_max_age_hours=12, clear_cache=True)
        assert config.use_cache is True
        assert config.cache_max_age_hours == 12
        assert config.clear_cache is True

    def test_clustering_options(self):
        """Test clustering options"""
        config = OrgReportConfig(enable_clustering=True, cluster_method="average")
        assert config.enable_clustering is True
        assert config.cluster_method == "average"


class TestDataViewCluster:
    """Test DataViewCluster dataclass"""

    def test_cluster_size(self):
        """Test cluster size property"""
        cluster = DataViewCluster(
            cluster_id=1,
            cluster_name="Test Cluster",
            data_view_ids=["dv_1", "dv_2", "dv_3"],
            data_view_names=["DV 1", "DV 2", "DV 3"],
            cohesion_score=0.85,
        )
        assert cluster.size == 3
        assert cluster.cohesion_score == pytest.approx(0.85)

    def test_cluster_without_name(self):
        """Test cluster without inferred name"""
        cluster = DataViewCluster(
            cluster_id=1,
            data_view_ids=["dv_1"],
            data_view_names=["Single DV"],
        )
        assert cluster.cluster_name is None
        assert cluster.size == 1


class TestSimilarityPairDrift:
    """Test SimilarityPair drift detection fields"""

    def test_drift_fields(self):
        """Test drift detection fields in SimilarityPair"""
        pair = SimilarityPair(
            dv1_id="dv_1",
            dv1_name="DV One",
            dv2_id="dv_2",
            dv2_name="DV Two",
            jaccard_similarity=0.9,
            shared_count=90,
            union_count=100,
            only_in_dv1=["m1", "m2"],
            only_in_dv2=["d1", "d2", "d3"],
            only_in_dv1_names={"m1": "Metric 1", "m2": "Metric 2"},
            only_in_dv2_names={"d1": "Dim 1"},
        )
        assert len(pair.only_in_dv1) == 2
        assert len(pair.only_in_dv2) == 3
        assert pair.only_in_dv1_names["m1"] == "Metric 1"

    def test_empty_drift(self):
        """Test similarity pair with no drift"""
        pair = SimilarityPair(
            dv1_id="dv_1",
            dv1_name="DV One",
            dv2_id="dv_2",
            dv2_name="DV Two",
            jaccard_similarity=1.0,
            shared_count=100,
            union_count=100,
        )
        assert pair.only_in_dv1 == []
        assert pair.only_in_dv2 == []


class TestDataViewSummaryEnhancements:
    """Test DataViewSummary component type and metadata fields"""

    def test_component_type_counts(self):
        """Test component type breakdown fields"""
        summary = DataViewSummary(
            data_view_id="dv_1",
            data_view_name="Test DV",
            metric_ids={"m1", "m2", "m3"},
            dimension_ids={"d1", "d2"},
            metric_count=3,
            dimension_count=2,
            standard_metric_count=2,
            derived_metric_count=1,
            standard_dimension_count=1,
            derived_dimension_count=1,
        )
        assert summary.standard_metric_count == 2
        assert summary.derived_metric_count == 1
        assert summary.derived_dimension_count == 1

    def test_metadata_fields(self):
        """Test metadata fields"""
        summary = DataViewSummary(
            data_view_id="dv_1",
            data_view_name="Test DV",
            owner="John Doe",
            owner_id="user123",
            created="2024-01-01T10:00:00Z",
            modified="2024-06-01T15:30:00Z",
            description="Test data view description",
            has_description=True,
        )
        assert summary.owner == "John Doe"
        assert summary.created == "2024-01-01T10:00:00Z"
        assert summary.has_description is True


class TestSampling:
    """Test sampling functionality"""

    @pytest.fixture
    def mock_cja(self):
        return Mock()

    @pytest.fixture
    def mock_logger(self):
        import logging

        return logging.getLogger("test")

    def test_sampling_applied(self, mock_cja, mock_logger):
        """Test sampling when sample_size < available DVs"""
        mock_cja.getDataViews.return_value = pd.DataFrame([{"id": f"dv_{i}", "name": f"DV {i}"} for i in range(20)])

        config = OrgReportConfig(sample_size=5, sample_seed=42)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        result, is_sampled, total_available = analyzer._list_and_filter_data_views()

        assert len(result) == 5
        assert is_sampled is True
        assert total_available == 20

    def test_sampling_reproducible(self, mock_cja, mock_logger):
        """Test sampling is reproducible with same seed"""
        mock_cja.getDataViews.return_value = pd.DataFrame([{"id": f"dv_{i}", "name": f"DV {i}"} for i in range(20)])

        config = OrgReportConfig(sample_size=5, sample_seed=42)

        analyzer1 = OrgComponentAnalyzer(mock_cja, config, mock_logger)
        result1, _, _ = analyzer1._list_and_filter_data_views()

        analyzer2 = OrgComponentAnalyzer(mock_cja, config, mock_logger)
        result2, _, _ = analyzer2._list_and_filter_data_views()

        # Same seed should produce same sample
        assert [dv["id"] for dv in result1] == [dv["id"] for dv in result2]

    def test_no_sampling_when_below_threshold(self, mock_cja, mock_logger):
        """Test no sampling when available < sample_size"""
        mock_cja.getDataViews.return_value = pd.DataFrame([{"id": f"dv_{i}", "name": f"DV {i}"} for i in range(3)])

        config = OrgReportConfig(sample_size=10, sample_seed=42)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        result, is_sampled, _total_available = analyzer._list_and_filter_data_views()

        assert len(result) == 3
        assert is_sampled is False

    def test_negative_sample_size_rejected(self, mock_cja, mock_logger):
        """Sample size must be positive to avoid random.sample runtime errors."""
        mock_cja.getDataViews.return_value = pd.DataFrame([{"id": f"dv_{i}", "name": f"DV {i}"} for i in range(3)])

        config = OrgReportConfig(sample_size=-1, sample_seed=42)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        with pytest.raises(ValueError, match="--sample must be at least 1"):
            analyzer._list_and_filter_data_views()


class TestOrgReportCache:
    """Test OrgReportCache functionality"""

    def test_cache_put_and_get(self):
        """Test storing and retrieving from cache"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = OrgReportCache(cache_dir=Path(tmpdir))

            summary = DataViewSummary(
                data_view_id="dv_test",
                data_view_name="Test DV",
                metric_ids={"m1", "m2"},
                dimension_ids={"d1"},
                metric_count=2,
                dimension_count=1,
            )

            cache.put(summary)
            retrieved = cache.get("dv_test", max_age_hours=24)

            assert retrieved is not None
            assert retrieved.data_view_id == "dv_test"
            assert retrieved.metric_count == 2

    def test_cache_invalidation(self):
        """Test cache invalidation"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = OrgReportCache(cache_dir=Path(tmpdir))

            summary = DataViewSummary(
                data_view_id="dv_test",
                data_view_name="Test DV",
            )

            cache.put(summary)
            assert cache.get("dv_test") is not None

            cache.invalidate("dv_test")
            assert cache.get("dv_test") is None

    def test_cache_invalidate_all(self):
        """Test clearing entire cache"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = OrgReportCache(cache_dir=Path(tmpdir))

            cache.put(DataViewSummary("dv_1", "DV 1"))
            cache.put(DataViewSummary("dv_2", "DV 2"))

            cache.invalidate()

            assert cache.get("dv_1") is None
            assert cache.get("dv_2") is None

    def test_cache_miss_returns_none(self):
        """Test cache miss returns None"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = OrgReportCache(cache_dir=Path(tmpdir))
            assert cache.get("nonexistent") is None

    def test_cache_save_failure_logs_warning(self):
        """Test that cache write failures are visible via logger warnings."""
        logger = Mock()
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = OrgReportCache(cache_dir=Path(tmpdir), logger=logger)

            with patch("builtins.open", side_effect=OSError("disk full")):
                cache.put(DataViewSummary("dv_test", "Test DV"))

            logger.warning.assert_called()
            assert "Failed to save org report cache" in logger.warning.call_args[0][0]


class TestLargeOrgScaling:
    """
    Test runtime behavior with large organizations (hundreds of data views).

    These tests exercise memory and performance characteristics at scale.
    While mocked, they validate that the algorithms handle large inputs correctly.
    """

    @pytest.fixture
    def mock_cja(self):
        return Mock()

    @pytest.fixture
    def mock_logger(self):
        import logging

        return logging.getLogger("test")

    def test_large_component_index_building(self, mock_cja, mock_logger):
        """Test component index building with 100+ DVs and 1000+ unique components"""
        config = OrgReportConfig(include_names=True)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        # Simulate 100 data views with varying components
        # Each DV has 50-100 metrics and 30-50 dimensions
        # Creates overlapping component sets to test core/common/limited/isolated distribution
        num_dvs = 100
        summaries = []

        # Core components (in 80%+ of DVs)
        core_metrics = {f"metric/core_{i}" for i in range(10)}
        core_dims = {f"dim/core_{i}" for i in range(5)}

        # Common components (in 30-50% of DVs)
        common_metrics = {f"metric/common_{i}" for i in range(20)}
        common_dims = {f"dim/common_{i}" for i in range(15)}

        # Generate DVs with varying component sets
        for dv_idx in range(num_dvs):
            metrics = set(core_metrics)  # All DVs get core
            dims = set(core_dims)

            # Add common components to ~40% of DVs
            if dv_idx % 3 != 0:
                metrics.update(common_metrics)
                dims.update(common_dims)

            # Add unique isolated components per DV
            metrics.add(f"metric/unique_{dv_idx}")
            dims.add(f"dim/unique_{dv_idx}")

            # Create names dictionary
            metric_names = {m: f"Metric {m.split('/')[-1]}" for m in metrics}
            dim_names = {d: f"Dimension {d.split('/')[-1]}" for d in dims}

            summaries.append(
                DataViewSummary(
                    data_view_id=f"dv_{dv_idx}",
                    data_view_name=f"Data View {dv_idx}",
                    metric_ids=metrics,
                    dimension_ids=dims,
                    metric_count=len(metrics),
                    dimension_count=len(dims),
                    metric_names=metric_names,
                    dimension_names=dim_names,
                ),
            )

        # Build the index
        component_index = analyzer._build_component_index(summaries)

        # Verify index contains expected components
        # Core: 10 metrics + 5 dims = 15
        # Common: 20 metrics + 15 dims = 35
        # Isolated: 100 metrics + 100 dims = 200
        total_expected = 10 + 5 + 20 + 15 + 100 + 100
        assert len(component_index) == total_expected

        # Verify core components are in all DVs
        for core_id in core_metrics:
            assert core_id in component_index
            assert component_index[core_id].presence_count == num_dvs

        # Verify isolated components are in exactly 1 DV
        assert "metric/unique_0" in component_index
        assert component_index["metric/unique_0"].presence_count == 1

    def test_large_distribution_classification(self, mock_cja, mock_logger):
        """Test distribution bucket classification at scale"""
        config = OrgReportConfig(core_threshold=0.5)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        num_dvs = 200

        # Create component index with known distribution
        component_index = {}

        # Core: in 60% of DVs (120+ DVs)
        for i in range(25):
            component_index[f"m_core_{i}"] = ComponentInfo(
                f"m_core_{i}",
                "metric",
                data_views={f"dv_{j}" for j in range(120)},
            )

        # Common: in 30% of DVs (60 DVs)
        for i in range(50):
            component_index[f"d_common_{i}"] = ComponentInfo(
                f"d_common_{i}",
                "dimension",
                data_views={f"dv_{j}" for j in range(60)},
            )

        # Limited: in 5% of DVs (10 DVs)
        for i in range(100):
            component_index[f"m_limited_{i}"] = ComponentInfo(
                f"m_limited_{i}",
                "metric",
                data_views={f"dv_{j}" for j in range(10)},
            )

        # Isolated: in 1 DV each
        for i in range(200):
            component_index[f"d_isolated_{i}"] = ComponentInfo(f"d_isolated_{i}", "dimension", data_views={f"dv_{i}"})

        distribution = analyzer._compute_distribution(component_index, total_dvs=num_dvs)

        assert distribution.total_core == 25  # All core metrics
        assert distribution.total_common == 50  # All common dimensions
        assert distribution.total_limited == 100  # All limited metrics
        assert distribution.total_isolated == 200  # All isolated dimensions

    def test_similarity_matrix_scaling(self, mock_cja, mock_logger):
        """Test O(n²) similarity calculation with moderate DV count"""
        config = OrgReportConfig(overlap_threshold=0.95, skip_similarity=False)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        # Create 50 DVs - will generate 50*49/2 = 1225 comparisons
        num_dvs = 50
        summaries = []

        # Create base component set
        base_components = {f"m_{i}" for i in range(50)}
        base_dims = {f"d_{i}" for i in range(30)}

        for i in range(num_dvs):
            # Each DV has base components plus some unique ones
            metrics = set(base_components)
            dims = set(base_dims)

            # Add 10 unique components to each DV
            # Per DV: 50 + 10 = 60 metrics, 30 + 10 = 40 dims = 100 components
            # Shared: 80 components
            # Union of any two DVs: 80 shared + 20 unique from DV1 + 20 unique from DV2 = 120
            # Similarity = 80 / 120 = 0.667
            for j in range(10):
                metrics.add(f"m_unique_{i}_{j}")
                dims.add(f"d_unique_{i}_{j}")

            summaries.append(
                DataViewSummary(
                    data_view_id=f"dv_{i}",
                    data_view_name=f"DV {i}",
                    metric_ids=metrics,
                    dimension_ids=dims,
                ),
            )

        pairs = analyzer._compute_similarity_matrix(summaries)

        # With 20 unique components per DV, similarity = 80/120 = 0.667
        # This is below 0.95 threshold, so no pairs should match
        assert len(pairs) == 0

        # Lower threshold to see pairs
        config.overlap_threshold = 0.6
        pairs = analyzer._compute_similarity_matrix(summaries)

        # Now we should see many pairs (DVs have ~66.7% overlap > 60% threshold)
        expected_pairs = num_dvs * (num_dvs - 1) // 2
        assert len(pairs) == expected_pairs

    def test_similarity_varies_with_threshold(self, mock_cja, mock_logger):
        """Test similarity results change based on threshold"""
        config = OrgReportConfig(overlap_threshold=1.0)  # Impossible threshold
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        # Create DVs with known similarity
        # DV1: {a, b, c, d, e} - 5 components
        # DV2: {a, b, c, f, g} - 5 components
        # Shared: {a, b, c} = 3
        # Union: {a, b, c, d, e, f, g} = 7
        # Similarity = 3/7 = 0.4286
        summaries = [
            DataViewSummary("dv_1", "DV 1", metric_ids={"a", "b", "c", "d", "e"}, dimension_ids=set()),
            DataViewSummary("dv_2", "DV 2", metric_ids={"a", "b", "c", "f", "g"}, dimension_ids=set()),
            DataViewSummary("dv_3", "DV 3", metric_ids={"a", "b", "c", "d", "e"}, dimension_ids=set()),  # Same as DV1
        ]

        # Threshold 1.0 - only exact matches
        pairs = analyzer._compute_similarity_matrix(summaries)
        assert len(pairs) == 1  # Only DV1-DV3 match (identical)
        assert pairs[0].dv1_id == "dv_1"
        assert pairs[0].dv2_id == "dv_3"

        # Lower threshold to include DV1-DV2 and DV2-DV3
        config.overlap_threshold = 0.4
        pairs = analyzer._compute_similarity_matrix(summaries)
        assert len(pairs) == 3  # DV1-DV2, DV1-DV3, DV2-DV3 all match

    def test_large_output_generation(self):
        """Test output writers handle large result sets"""
        import logging
        import os

        logger = logging.getLogger("test")

        # Create result with 100 DVs and 500+ components
        summaries = [
            DataViewSummary(
                f"dv_{i}",
                f"Production Data View {i}",
                metric_ids={f"m_{j}" for j in range(50)},
                dimension_ids={f"d_{j}" for j in range(30)},
                metric_count=50,
                dimension_count=30,
            )
            for i in range(100)
        ]

        component_index = {}
        for i in range(300):
            component_index[f"metric_{i}"] = ComponentInfo(
                f"metric_{i}",
                "metric",
                name=f"Metric Name {i}",
                data_views={f"dv_{j}" for j in range(min(i + 1, 100))},
            )
        for i in range(200):
            component_index[f"dim_{i}"] = ComponentInfo(
                f"dim_{i}",
                "dimension",
                name=f"Dimension Name {i}",
                data_views={f"dv_{j}" for j in range(min(i + 1, 100))},
            )

        result = OrgReportResult(
            timestamp="2024-01-15T10:30:00",
            org_id="large_org_test@AdobeOrg",
            parameters=OrgReportConfig(),
            data_view_summaries=summaries,
            component_index=component_index,
            distribution=ComponentDistribution(
                core_metrics=[f"metric_{i}" for i in range(50, 300)],
                core_dimensions=[f"dim_{i}" for i in range(50, 200)],
                isolated_metrics=[f"metric_{i}" for i in range(50)],
                isolated_dimensions=[f"dim_{i}" for i in range(50)],
            ),
            similarity_pairs=[
                SimilarityPair(f"dv_{i}", f"DV {i}", f"dv_{i + 1}", f"DV {i + 1}", 0.85, 70, 80)
                for i in range(0, 50, 2)
            ],
            recommendations=[{"type": "test", "severity": "low", "reason": f"Reason {i}"} for i in range(10)],
            duration=25.5,
        )

        assert result.total_data_views == 100
        assert result.total_unique_components == 500

        # Test JSON output handles large data
        with tempfile.TemporaryDirectory() as tmpdir:
            json_path_str = write_org_report_json(result, None, tmpdir, logger)
            assert os.path.exists(json_path_str)

            with open(json_path_str) as f:
                data = json.load(f)
            assert data["summary"]["data_views_total"] == 100
            assert len(data["component_index"]) == 500

        # Test Markdown output handles large data
        with tempfile.TemporaryDirectory() as tmpdir:
            md_path_str = write_org_report_markdown(result, None, tmpdir, logger)
            assert os.path.exists(md_path_str)

            with open(md_path_str) as f:
                content = f.read()
            assert "100" in content  # DV count appears
            assert "500" in content  # Component count appears


class TestOutputPathWithFormatAliases:
    """
    Test --output path handling with format aliases (reports, data, ci).

    Addresses gap: output paths across all alias combinations with --output.
    """

    @pytest.fixture
    def sample_result(self):
        """Create sample OrgReportResult for testing"""
        return OrgReportResult(
            timestamp="2024-01-15T10:30:00",
            org_id="test_org@AdobeOrg",
            parameters=OrgReportConfig(core_threshold=0.5, overlap_threshold=0.8),
            data_view_summaries=[
                DataViewSummary(
                    "dv_1",
                    "DV 1",
                    metric_ids={"m1"},
                    dimension_ids={"d1"},
                    metric_count=1,
                    dimension_count=1,
                ),
            ],
            component_index={
                "m1": ComponentInfo("m1", "metric", data_views={"dv_1"}),
                "d1": ComponentInfo("d1", "dimension", data_views={"dv_1"}),
            },
            distribution=ComponentDistribution(isolated_metrics=["m1"], isolated_dimensions=["d1"]),
            similarity_pairs=[],
            recommendations=[],
            duration=1.0,
        )

    def test_json_with_explicit_output_path(self, sample_result):
        """Test JSON output with explicit --output path"""
        import logging
        import os

        logger = logging.getLogger("test")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "my_report.json"
            result_path_str = write_org_report_json(sample_result, output_path, tmpdir, logger)

            assert result_path_str == str(output_path)
            assert os.path.exists(result_path_str)

    def test_json_with_output_path_no_extension(self, sample_result):
        """Test JSON output when path lacks extension (should add .json)"""
        import logging
        import os

        logger = logging.getLogger("test")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "my_report"  # No extension
            result_path_str = write_org_report_json(sample_result, output_path, tmpdir, logger)

            assert result_path_str == str(output_path) + ".json"
            assert os.path.exists(result_path_str)

    def test_excel_with_explicit_output_path(self, sample_result):
        """Test Excel output with explicit --output path"""
        import logging
        import os

        logger = logging.getLogger("test")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "my_report.xlsx"
            result_path_str = write_org_report_excel(sample_result, output_path, tmpdir, logger)

            assert result_path_str == str(output_path)
            assert os.path.exists(result_path_str)

    def test_markdown_with_explicit_output_path(self, sample_result):
        """Test Markdown output with explicit --output path"""
        import logging
        import os

        logger = logging.getLogger("test")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "my_report.md"
            result_path_str = write_org_report_markdown(sample_result, output_path, tmpdir, logger)

            assert result_path_str == str(output_path)
            assert os.path.exists(result_path_str)

    def test_html_with_explicit_output_path(self, sample_result):
        """Test HTML output with explicit --output path"""
        import logging
        import os

        logger = logging.getLogger("test")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "my_report.html"
            result_path_str = write_org_report_html(sample_result, output_path, tmpdir, logger)

            assert result_path_str == str(output_path)
            assert os.path.exists(result_path_str)

    def test_csv_with_explicit_output_path(self, sample_result):
        """Test CSV output with explicit --output path (creates directory)"""
        import logging
        import os

        logger = logging.getLogger("test")

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "my_csv_output"
            result_path_str = write_org_report_csv(sample_result, output_path, tmpdir, logger)

            assert result_path_str == str(output_path)
            assert os.path.isdir(result_path_str)
            assert os.path.exists(os.path.join(result_path_str, "org_report_summary.csv"))

    def test_alias_base_path_stripping(self, sample_result):
        """Test that alias base path correctly strips extension for multi-format output"""
        import logging
        import os

        logger = logging.getLogger("test")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Simulate what run_org_report does with an alias
            # User provides: --output /path/to/my_report.xlsx --format reports
            output_path = Path(tmpdir) / "my_report.xlsx"
            alias_base = output_path.with_suffix("")  # Strip .xlsx -> my_report

            # Each format writer should use the base name and add its own extension
            json_path_str = write_org_report_json(sample_result, alias_base, tmpdir, logger)
            excel_path_str = write_org_report_excel(sample_result, alias_base, tmpdir, logger)
            md_path_str = write_org_report_markdown(sample_result, alias_base, tmpdir, logger)

            # Verify all files created with same base name
            assert os.path.basename(json_path_str) == "my_report.json"
            assert os.path.basename(excel_path_str) == "my_report.xlsx"
            assert os.path.basename(md_path_str) == "my_report.md"

            # Verify all exist
            assert os.path.exists(json_path_str)
            assert os.path.exists(excel_path_str)
            assert os.path.exists(md_path_str)

    def test_reports_alias_output_files(self, sample_result):
        """Test 'reports' alias generates excel + markdown with consistent naming"""
        import logging
        import os

        logger = logging.getLogger("test")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Simulate: --format reports --output my_analysis
            output_path = Path(tmpdir) / "my_analysis"
            alias_base = output_path.with_suffix("")

            # 'reports' alias = ['excel', 'markdown']
            excel_path_str = write_org_report_excel(sample_result, alias_base, tmpdir, logger)
            md_path_str = write_org_report_markdown(sample_result, alias_base, tmpdir, logger)

            assert os.path.basename(excel_path_str) == "my_analysis.xlsx"
            assert os.path.basename(md_path_str) == "my_analysis.md"
            assert os.path.exists(excel_path_str)
            assert os.path.exists(md_path_str)

    def test_data_alias_output_files(self, sample_result):
        """Test 'data' alias generates csv + json with consistent naming"""
        import logging
        import os

        logger = logging.getLogger("test")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Simulate: --format data --output export
            output_path = Path(tmpdir) / "export"
            alias_base = output_path.with_suffix("")

            # 'data' alias = ['csv', 'json']
            json_path_str = write_org_report_json(sample_result, alias_base, tmpdir, logger)
            csv_path_str = write_org_report_csv(sample_result, alias_base, tmpdir, logger)

            assert os.path.basename(json_path_str) == "export.json"
            assert os.path.basename(csv_path_str) == "export"  # CSV creates a directory
            assert os.path.exists(json_path_str)
            assert os.path.isdir(csv_path_str)

    def test_ci_alias_output_files(self, sample_result):
        """Test 'ci' alias generates json + markdown with consistent naming"""
        import logging
        import os

        logger = logging.getLogger("test")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Simulate: --format ci --output ci_report
            output_path = Path(tmpdir) / "ci_report"
            alias_base = output_path.with_suffix("")

            # 'ci' alias = ['json', 'markdown']
            json_path_str = write_org_report_json(sample_result, alias_base, tmpdir, logger)
            md_path_str = write_org_report_markdown(sample_result, alias_base, tmpdir, logger)

            assert os.path.basename(json_path_str) == "ci_report.json"
            assert os.path.basename(md_path_str) == "ci_report.md"
            assert os.path.exists(json_path_str)
            assert os.path.exists(md_path_str)

    def test_output_path_in_subdirectory(self, sample_result):
        """Test output path works when specifying a subdirectory"""
        import logging
        import os

        logger = logging.getLogger("test")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create nested output path
            subdir = Path(tmpdir) / "reports" / "2024"
            subdir.mkdir(parents=True)
            output_path = subdir / "quarterly_report.json"

            result_path_str = write_org_report_json(sample_result, output_path, tmpdir, logger)

            assert result_path_str == str(output_path)
            assert os.path.exists(result_path_str)

    def test_output_path_overrides_output_dir(self, sample_result):
        """Test explicit output path takes precedence over output_dir"""
        import logging
        import os

        logger = logging.getLogger("test")

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create two directories
            output_dir = Path(tmpdir) / "default_dir"
            output_dir.mkdir()
            explicit_dir = Path(tmpdir) / "explicit_dir"
            explicit_dir.mkdir()

            output_path = explicit_dir / "explicit_report.json"

            # Pass output_dir but also explicit path - explicit path should win
            result_path_str = write_org_report_json(sample_result, output_path, str(output_dir), logger)

            assert result_path_str == str(output_path)
            assert os.path.exists(result_path_str)
            # Default dir should NOT have the file
            assert not os.path.exists(os.path.join(str(output_dir), "explicit_report.json"))

    def test_no_output_path_uses_output_dir(self, sample_result):
        """Test when no output path, uses output_dir with auto-generated name"""
        import logging
        import os

        logger = logging.getLogger("test")

        with tempfile.TemporaryDirectory() as tmpdir:
            result_path_str = write_org_report_json(sample_result, None, tmpdir, logger)
            result_path = Path(result_path_str)

            # Should be in tmpdir with auto-generated name
            assert str(result_path.parent) == tmpdir
            assert "org_report" in result_path.name
            assert result_path.name.endswith(".json")
            assert os.path.exists(result_path_str)


class TestOrgReportOutputHandling:
    """Focused tests for org-report output handling fixes."""

    @pytest.fixture
    def sample_result(self):
        return OrgReportResult(
            timestamp="2024-01-15T10:30:00",
            org_id="org_123",
            parameters=OrgReportConfig(core_threshold=0.5, overlap_threshold=0.8),
            data_view_summaries=[
                DataViewSummary(
                    "dv_1",
                    "DV 1",
                    metric_ids={"m1"},
                    dimension_ids={"d1"},
                    metric_count=1,
                    dimension_count=1,
                ),
            ],
            component_index={
                "m1": ComponentInfo("m1", "metric", data_views={"dv_1"}),
                "d1": ComponentInfo("d1", "dimension", data_views={"dv_1"}),
            },
            distribution=ComponentDistribution(isolated_metrics=["m1"], isolated_dimensions=["d1"]),
            similarity_pairs=[],
            recommendations=[],
            duration=1.0,
        )

    def test_org_stats_json_without_output_path_creates_file(self, sample_result):
        """Org-stats JSON should still write a file when --output is not provided."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with (
                patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "ok", {"org_id": "org_123"})),
                patch("cja_auto_sdr.generator.cjapy.CJA", return_value=Mock()),
                patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer,
            ):
                mock_analyzer.return_value.run_analysis.return_value = sample_result

                success, thresholds = run_org_report(
                    config_file="config.json",
                    output_format="json",
                    output_path=None,
                    output_dir=tmpdir,
                    org_config=OrgReportConfig(org_stats_only=True),
                    profile=None,
                    quiet=True,
                )

                assert success is True
                assert thresholds is False
                json_files = list(Path(tmpdir).glob("org_report_*.json"))
                assert len(json_files) == 1

    def test_format_all_honors_output_base_path(self, sample_result):
        """--format all should respect --output base path for all formats."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_path = Path(tmpdir) / "org_report_base.json"
            with (
                patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "ok", {"org_id": "org_123"})),
                patch("cja_auto_sdr.generator.cjapy.CJA", return_value=Mock()),
                patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer,
            ):
                mock_analyzer.return_value.run_analysis.return_value = sample_result

                success, _ = run_org_report(
                    config_file="config.json",
                    output_format="all",
                    output_path=str(base_path),
                    output_dir=tmpdir,
                    org_config=OrgReportConfig(),
                    profile=None,
                    quiet=True,
                )

                assert success is True
                assert (Path(tmpdir) / "org_report_base.json").exists()
                assert (Path(tmpdir) / "org_report_base.xlsx").exists()
                assert (Path(tmpdir) / "org_report_base.md").exists()
                assert (Path(tmpdir) / "org_report_base.html").exists()
                assert (Path(tmpdir) / "org_report_base").exists()

    def test_json_output_to_stdout(self, sample_result, capsys):
        """--output - should emit JSON to stdout for org-report."""
        with (
            patch("cja_auto_sdr.generator.configure_cjapy", return_value=(True, "ok", {"org_id": "org_123"})),
            patch("cja_auto_sdr.generator.cjapy.CJA", return_value=Mock()),
            patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer,
        ):
            mock_analyzer.return_value.run_analysis.return_value = sample_result

            success, _ = run_org_report(
                config_file="config.json",
                output_format="json",
                output_path="-",
                output_dir=".",
                org_config=OrgReportConfig(),
                profile=None,
                quiet=True,
            )

            assert success is True
            captured = capsys.readouterr()
            assert '"report_type"' in captured.out
            assert '"org_id"' in captured.out

    def test_csv_output_to_stdout_errors(self, sample_result, capsys):
        """CSV org-report should error on stdout since it writes multiple files."""
        with (
            patch(
                "cja_auto_sdr.generator.configure_cjapy",
                return_value=(True, "ok", {"org_id": "org_123"}),
            ) as mock_configure,
            patch("cja_auto_sdr.generator.cjapy.CJA", return_value=Mock()),
            patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer,
        ):
            mock_analyzer.return_value.run_analysis.return_value = sample_result

            success, _ = run_org_report(
                config_file="config.json",
                output_format="csv",
                output_path="-",
                output_dir=".",
                org_config=OrgReportConfig(),
                profile=None,
                quiet=True,
            )

            assert success is False
            captured = capsys.readouterr()
            assert "only supported for --format json or --format console" in captured.out
            mock_configure.assert_not_called()
            mock_analyzer.assert_not_called()

    def test_markdown_output_to_stdout_errors(self, sample_result, capsys):
        """Markdown org-report should fail fast when stdout is requested."""
        with (
            patch(
                "cja_auto_sdr.generator.configure_cjapy",
                return_value=(True, "ok", {"org_id": "org_123"}),
            ) as mock_configure,
            patch("cja_auto_sdr.generator.cjapy.CJA", return_value=Mock()),
            patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer,
        ):
            mock_analyzer.return_value.run_analysis.return_value = sample_result

            success, _ = run_org_report(
                config_file="config.json",
                output_format="markdown",
                output_path="-",
                output_dir=".",
                org_config=OrgReportConfig(),
                profile=None,
                quiet=True,
            )

            assert success is False
            captured = capsys.readouterr()
            assert "only supported for --format json or --format console" in captured.out
            mock_configure.assert_not_called()
            mock_analyzer.assert_not_called()

    def test_alias_output_to_stdout_errors(self, sample_result, capsys):
        """Format aliases should fail fast when stdout is requested."""
        with (
            patch(
                "cja_auto_sdr.generator.configure_cjapy",
                return_value=(True, "ok", {"org_id": "org_123"}),
            ) as mock_configure,
            patch("cja_auto_sdr.generator.cjapy.CJA", return_value=Mock()),
            patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer,
        ):
            mock_analyzer.return_value.run_analysis.return_value = sample_result

            success, _ = run_org_report(
                config_file="config.json",
                output_format="data",
                output_path="-",
                output_dir=".",
                org_config=OrgReportConfig(),
                profile=None,
                quiet=True,
            )

            assert success is False
            captured = capsys.readouterr()
            assert "only supported for --format json or --format console" in captured.out
            mock_configure.assert_not_called()
            mock_analyzer.assert_not_called()

    def test_all_output_to_stdout_errors(self, sample_result, capsys):
        """--format all should fail fast when stdout is requested."""
        with (
            patch(
                "cja_auto_sdr.generator.configure_cjapy",
                return_value=(True, "ok", {"org_id": "org_123"}),
            ) as mock_configure,
            patch("cja_auto_sdr.generator.cjapy.CJA", return_value=Mock()),
            patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer,
        ):
            mock_analyzer.return_value.run_analysis.return_value = sample_result

            success, _ = run_org_report(
                config_file="config.json",
                output_format="all",
                output_path="-",
                output_dir=".",
                org_config=OrgReportConfig(),
                profile=None,
                quiet=True,
            )

            assert success is False
            captured = capsys.readouterr()
            assert "only supported for --format json or --format console" in captured.out
            mock_configure.assert_not_called()
            mock_analyzer.assert_not_called()

    def test_unknown_format_fails_before_analysis(self, sample_result, capsys):
        """Unknown org-report format should fail before any API/configuration work."""
        with (
            patch(
                "cja_auto_sdr.generator.configure_cjapy",
                return_value=(True, "ok", {"org_id": "org_123"}),
            ) as mock_configure,
            patch("cja_auto_sdr.generator.cjapy.CJA", return_value=Mock()),
            patch("cja_auto_sdr.generator.OrgComponentAnalyzer") as mock_analyzer,
        ):
            mock_analyzer.return_value.run_analysis.return_value = sample_result

            success, _ = run_org_report(
                config_file="config.json",
                output_format="not-a-format",
                output_path=None,
                output_dir=".",
                org_config=OrgReportConfig(),
                profile=None,
                quiet=True,
            )

            assert success is False
            captured = capsys.readouterr()
            assert "Unknown format" in captured.out
            mock_configure.assert_not_called()
            mock_analyzer.assert_not_called()


# ==================== NEW FEATURE TESTS ====================


class TestGovernanceThresholds:
    """Test Feature 1: Governance exit codes and threshold checking"""

    @pytest.fixture
    def mock_cja(self):
        return Mock()

    @pytest.fixture
    def mock_logger(self):
        import logging

        return logging.getLogger("test")

    def test_duplicate_threshold_not_exceeded(self, mock_cja, mock_logger):
        """Test no violation when duplicate pairs below threshold"""
        config = OrgReportConfig(duplicate_threshold=5, fail_on_threshold=True)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        # Create 3 high-similarity pairs (below threshold of 5)
        similarity_pairs = [
            SimilarityPair("dv_1", "DV 1", "dv_2", "DV 2", 0.95, 95, 100),
            SimilarityPair("dv_3", "DV 3", "dv_4", "DV 4", 0.92, 92, 100),
            SimilarityPair("dv_5", "DV 5", "dv_6", "DV 6", 0.91, 91, 100),
        ]
        distribution = ComponentDistribution()

        violations, exceeded = analyzer._check_governance_thresholds(similarity_pairs, distribution, 100)

        assert exceeded is False
        assert len(violations) == 0

    def test_duplicate_threshold_exceeded(self, mock_cja, mock_logger):
        """Test violation when duplicate pairs exceed threshold"""
        config = OrgReportConfig(duplicate_threshold=2, fail_on_threshold=True)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        # Create 4 high-similarity pairs (above threshold of 2)
        similarity_pairs = [
            SimilarityPair("dv_1", "DV 1", "dv_2", "DV 2", 0.95, 95, 100),
            SimilarityPair("dv_3", "DV 3", "dv_4", "DV 4", 0.92, 92, 100),
            SimilarityPair("dv_5", "DV 5", "dv_6", "DV 6", 0.91, 91, 100),
            SimilarityPair("dv_7", "DV 7", "dv_8", "DV 8", 0.90, 90, 100),
        ]
        distribution = ComponentDistribution()

        violations, exceeded = analyzer._check_governance_thresholds(similarity_pairs, distribution, 100)

        assert exceeded is True
        assert len(violations) == 1
        assert violations[0]["type"] == "duplicate_threshold_exceeded"
        assert violations[0]["actual"] == 4

    def test_isolated_threshold_exceeded(self, mock_cja, mock_logger):
        """Test violation when isolated percentage exceeds threshold"""
        config = OrgReportConfig(isolated_threshold=0.3, fail_on_threshold=True)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        # Create distribution with 50% isolated (above 30% threshold)
        distribution = ComponentDistribution(
            core_metrics=["m1", "m2"],
            isolated_metrics=["m3", "m4", "m5", "m6", "m7"],  # 50% isolated
        )

        violations, exceeded = analyzer._check_governance_thresholds(
            None,
            distribution,
            10,  # 5 isolated out of 10 total
        )

        assert exceeded is True
        assert len(violations) == 1
        assert violations[0]["type"] == "isolated_threshold_exceeded"

    def test_isolated_threshold_not_exceeded(self, mock_cja, mock_logger):
        """Test no violation when isolated percentage below threshold"""
        config = OrgReportConfig(isolated_threshold=0.5, fail_on_threshold=True)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        # Create distribution with 30% isolated (below 50% threshold)
        distribution = ComponentDistribution(
            core_metrics=["m1", "m2", "m3", "m4", "m5", "m6", "m7"],  # 70% core
            isolated_metrics=["m8", "m9", "m10"],  # 30% isolated
        )

        violations, exceeded = analyzer._check_governance_thresholds(None, distribution, 10)

        assert exceeded is False
        assert len(violations) == 0

    def test_duplicate_threshold_counts_pairs_above_90(self, mock_cja, mock_logger):
        """Test duplicate threshold uses >=0.9 pairs even with higher overlap threshold"""
        config = OrgReportConfig(overlap_threshold=0.95, duplicate_threshold=2, fail_on_threshold=True)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        summaries = [
            DataViewSummary(
                "dv_1",
                "DV 1",
                metric_ids={f"m{i}" for i in range(1, 11)},
                dimension_ids={"d1", "d2"},
            ),
            DataViewSummary(
                "dv_2",
                "DV 2",
                metric_ids={f"m{i}" for i in range(1, 11)},
                dimension_ids={"d1", "d2", "d3"},
            ),
            DataViewSummary(
                "dv_3",
                "DV 3",
                metric_ids={f"m{i}" for i in range(1, 11)},
                dimension_ids={"d1", "d2", "d3"},
            ),
        ]

        similarity_pairs = analyzer._compute_similarity_matrix(summaries)
        violations, exceeded = analyzer._check_governance_thresholds(similarity_pairs, ComponentDistribution(), 100)

        assert exceeded is True
        assert len(violations) == 1
        assert violations[0]["type"] == "duplicate_threshold_exceeded"
        assert violations[0]["actual"] == 3


class TestNamingAudit:
    """Test Feature 3: Naming convention audit"""

    @pytest.fixture
    def mock_cja(self):
        return Mock()

    @pytest.fixture
    def mock_logger(self):
        import logging

        return logging.getLogger("test")

    def test_case_style_detection(self, mock_cja, mock_logger):
        """Test detection of different naming case styles"""
        config = OrgReportConfig(audit_naming=True)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        component_index = {
            "snake_case_metric": ComponentInfo("snake_case_metric", "metric", name="snake_case_metric"),
            "camelCaseMetric": ComponentInfo("camelCaseMetric", "metric", name="camelCaseMetric"),
            "PascalCaseMetric": ComponentInfo("PascalCaseMetric", "metric", name="PascalCaseMetric"),
            "other": ComponentInfo("other", "metric", name="other"),
        }

        audit = analyzer._audit_naming_conventions(component_index)

        assert audit["case_styles"]["snake_case"] == 1
        assert audit["case_styles"]["camelCase"] == 1
        assert audit["case_styles"]["PascalCase"] == 1

    def test_stale_keyword_detection(self, mock_cja, mock_logger):
        """Test detection of stale naming patterns"""
        config = OrgReportConfig(audit_naming=True)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        component_index = {
            "test_metric": ComponentInfo("test_metric", "metric", name="test_metric", data_views={"dv_1"}),
            "old_dimension": ComponentInfo("old_dimension", "dimension", name="old_dimension", data_views={"dv_1"}),
            "temp_field": ComponentInfo("temp_field", "metric", name="temp_field", data_views={"dv_1"}),
            "normal_metric": ComponentInfo("normal_metric", "metric", name="normal_metric", data_views={"dv_1"}),
        }

        audit = analyzer._audit_naming_conventions(component_index)

        # Should find 3 stale patterns (test_, old_, temp_)
        assert len(audit["stale_patterns"]) == 3
        stale_names = [p["name"] for p in audit["stale_patterns"]]
        assert "test_metric" in stale_names
        assert "old_dimension" in stale_names
        assert "temp_field" in stale_names

    def test_version_suffix_detection(self, mock_cja, mock_logger):
        """Test detection of version suffix patterns"""
        config = OrgReportConfig(audit_naming=True)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        component_index = {
            "metric_v1": ComponentInfo("metric_v1", "metric", name="metric_v1", data_views={"dv_1"}),
            "metric_v2": ComponentInfo("metric_v2", "metric", name="metric_v2", data_views={"dv_1"}),
            "metric": ComponentInfo("metric", "metric", name="metric", data_views={"dv_1"}),
        }

        audit = analyzer._audit_naming_conventions(component_index)

        # Should find 2 version suffix patterns
        version_patterns = [p for p in audit["stale_patterns"] if p["pattern"] == "version_suffix"]
        assert len(version_patterns) == 2

    def test_date_pattern_detection(self, mock_cja, mock_logger):
        """Test detection of date patterns in names"""
        config = OrgReportConfig(audit_naming=True)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        component_index = {
            "metric_20240101": ComponentInfo("metric_20240101", "metric", name="metric_20240101", data_views={"dv_1"}),
            "metric_2024-01-15": ComponentInfo(
                "metric_2024-01-15",
                "metric",
                name="metric_2024-01-15",
                data_views={"dv_1"},
            ),
            "current_metric": ComponentInfo("current_metric", "metric", name="current_metric", data_views={"dv_1"}),
        }

        audit = analyzer._audit_naming_conventions(component_index)

        date_patterns = [p for p in audit["stale_patterns"] if p["pattern"] == "date_pattern"]
        assert len(date_patterns) == 2


class TestOwnerSummary:
    """Test Feature 5: Owner/team summary"""

    @pytest.fixture
    def mock_cja(self):
        return Mock()

    @pytest.fixture
    def mock_logger(self):
        import logging

        return logging.getLogger("test")

    def test_owner_grouping(self, mock_cja, mock_logger):
        """Test grouping data views by owner"""
        config = OrgReportConfig(include_owner_summary=True, include_metadata=True)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        summaries = [
            DataViewSummary("dv_1", "DV 1", metric_count=50, dimension_count=30, owner="Alice"),
            DataViewSummary("dv_2", "DV 2", metric_count=40, dimension_count=20, owner="Alice"),
            DataViewSummary("dv_3", "DV 3", metric_count=100, dimension_count=50, owner="Bob"),
            DataViewSummary("dv_4", "DV 4", owner="Unknown"),  # No metrics
        ]

        owner_summary = analyzer._compute_owner_summary(summaries)

        assert owner_summary["total_owners"] == 3
        assert "Alice" in owner_summary["by_owner"]
        assert "Bob" in owner_summary["by_owner"]

        alice_stats = owner_summary["by_owner"]["Alice"]
        assert alice_stats["data_view_count"] == 2
        assert alice_stats["total_metrics"] == 90
        assert alice_stats["avg_metrics_per_dv"] == pytest.approx(45.0)

        bob_stats = owner_summary["by_owner"]["Bob"]
        assert bob_stats["data_view_count"] == 1
        assert bob_stats["total_metrics"] == 100

    def test_owner_summary_empty_owner(self, mock_cja, mock_logger):
        """Test handling of data views with no owner"""
        config = OrgReportConfig(include_owner_summary=True)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        summaries = [
            DataViewSummary("dv_1", "DV 1", metric_count=50, dimension_count=30, owner=None),
            DataViewSummary("dv_2", "DV 2", metric_count=40, dimension_count=20),
        ]

        owner_summary = analyzer._compute_owner_summary(summaries)

        # Both should be grouped under "Unknown"
        assert "Unknown" in owner_summary["by_owner"]
        assert owner_summary["by_owner"]["Unknown"]["data_view_count"] == 2


class TestStaleComponents:
    """Test Feature 6: Stale component heuristics"""

    @pytest.fixture
    def mock_cja(self):
        return Mock()

    @pytest.fixture
    def mock_logger(self):
        import logging

        return logging.getLogger("test")

    def test_detect_stale_keywords(self, mock_cja, mock_logger):
        """Test detection of stale keyword patterns"""
        config = OrgReportConfig(flag_stale=True)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        component_index = {
            "test_metric": ComponentInfo("test_metric", "metric", name="test_metric", data_views={"dv_1"}),
            "deprecated_dim": ComponentInfo("deprecated_dim", "dimension", name="deprecated_dim", data_views={"dv_1"}),
            "backup_field": ComponentInfo("backup_field", "metric", name="backup_field", data_views={"dv_1"}),
            "active_metric": ComponentInfo("active_metric", "metric", name="active_metric", data_views={"dv_1"}),
        }

        stale = analyzer._detect_stale_components(component_index)

        assert len(stale) == 3
        stale_ids = [s["component_id"] for s in stale]
        assert "test_metric" in stale_ids
        assert "deprecated_dim" in stale_ids
        assert "backup_field" in stale_ids
        assert "active_metric" not in stale_ids

    def test_detect_version_suffix(self, mock_cja, mock_logger):
        """Test detection of version suffixes as stale"""
        config = OrgReportConfig(flag_stale=True)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        component_index = {
            "metric_v1": ComponentInfo("metric_v1", "metric", name="metric_v1", data_views={"dv_1"}),
            "metric_V2": ComponentInfo("metric_V2", "metric", name="metric_V2", data_views={"dv_1"}),
            "metric_latest": ComponentInfo("metric_latest", "metric", name="metric_latest", data_views={"dv_1"}),
        }

        stale = analyzer._detect_stale_components(component_index)

        # Should find 2 version suffix patterns
        assert len(stale) == 2
        patterns = [s["pattern"] for s in stale]
        assert all(p == "version_suffix" for p in patterns)


class TestOrgReportComparison:
    """Test Feature 4: Trending/drift report comparison"""

    def test_compare_data_views_added(self):
        """Test detection of added data views"""
        from cja_auto_sdr.generator import OrgReportResult

        # Create current result with 3 DVs
        current = OrgReportResult(
            timestamp="2024-02-01T10:00:00",
            org_id="test_org",
            parameters=OrgReportConfig(),
            data_view_summaries=[
                DataViewSummary("dv_1", "DV 1"),
                DataViewSummary("dv_2", "DV 2"),
                DataViewSummary("dv_3", "DV 3"),  # New DV
            ],
            component_index={},
            distribution=ComponentDistribution(),
            similarity_pairs=[],
            recommendations=[],
            duration=1.0,
        )

        # Create previous report JSON with 2 DVs
        prev_data = _mark_full_fidelity_baseline(
            {
                "generated_at": "2024-01-01T10:00:00",
                "data_views": [
                    {"data_view_id": "dv_1", "data_view_name": "DV 1"},
                    {"data_view_id": "dv_2", "data_view_name": "DV 2"},
                ],
                "summary": {"total_unique_components": 50},
                "distribution": {
                    "core": {"metrics_count": 6, "dimensions_count": 4},
                    "isolated": {"metrics_count": 7, "dimensions_count": 8},
                },
                "similarity_pairs": [
                    {
                        "data_view_1": {"id": "dv_1", "name": "DV 1"},
                        "data_view_2": {"id": "dv_2", "name": "DV 2"},
                        "jaccard_similarity": 0.95,
                        "shared_components": 10,
                        "union_size": 12,
                    },
                ],
            }
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(prev_data, f)
            prev_path = f.name

        try:
            comparison = compare_org_reports(current, prev_path)

            assert len(comparison.data_views_added) == 1
            assert "dv_3" in comparison.data_views_added
            assert len(comparison.data_views_removed) == 0
            assert comparison.summary["data_views_delta"] == 1
        finally:
            os.unlink(prev_path)

    def test_compare_data_views_removed(self):
        """Test detection of removed data views"""

        # Create current result with 1 DV
        current = OrgReportResult(
            timestamp="2024-02-01T10:00:00",
            org_id="test_org",
            parameters=OrgReportConfig(),
            data_view_summaries=[
                DataViewSummary("dv_1", "DV 1"),
            ],
            component_index={},
            distribution=ComponentDistribution(),
            similarity_pairs=[],
            recommendations=[],
            duration=1.0,
        )

        # Previous had 2 DVs
        prev_data = _mark_full_fidelity_baseline(
            {
                "generated_at": "2024-01-01T10:00:00",
                "data_views": [
                    {"data_view_id": "dv_1", "data_view_name": "DV 1"},
                    {"data_view_id": "dv_2", "data_view_name": "DV 2"},
                ],
                "summary": {"total_unique_components": 50},
                "distribution": {
                    "core": {"metrics_count": 6, "dimensions_count": 4},
                    "isolated": {"metrics_count": 7, "dimensions_count": 8},
                },
                "similarity_pairs": [
                    {
                        "data_view_1": {"id": "dv_1", "name": "DV 1"},
                        "data_view_2": {"id": "dv_2", "name": "DV 2"},
                        "jaccard_similarity": 0.95,
                        "shared_components": 10,
                        "union_size": 12,
                    },
                ],
            }
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(prev_data, f)
            prev_path = f.name

        try:
            comparison = compare_org_reports(current, prev_path)

            assert len(comparison.data_views_removed) == 1
            assert "dv_2" in comparison.data_views_removed
            assert comparison.summary["data_views_delta"] == -1
        finally:
            os.unlink(prev_path)

    def test_compare_similarity_pair_order_normalized(self):
        """Test that high-similarity pairs are compared order-independently"""

        current = OrgReportResult(
            timestamp="2024-02-01T10:00:00",
            org_id="test_org",
            parameters=OrgReportConfig(),
            data_view_summaries=[
                DataViewSummary("dv_1", "DV 1"),
                DataViewSummary("dv_2", "DV 2"),
            ],
            component_index={},
            distribution=ComponentDistribution(),
            similarity_pairs=[
                SimilarityPair(
                    dv1_id="dv_2",
                    dv1_name="DV 2",
                    dv2_id="dv_1",
                    dv2_name="DV 1",
                    jaccard_similarity=0.95,
                    shared_count=10,
                    union_count=12,
                    only_in_dv1=[],
                    only_in_dv2=[],
                    only_in_dv1_names=None,
                    only_in_dv2_names=None,
                ),
            ],
            recommendations=[],
            duration=1.0,
        )

        prev_data = _mark_full_fidelity_baseline(
            {
                "generated_at": "2024-01-01T10:00:00",
                "data_views": [
                    {"data_view_id": "dv_1", "data_view_name": "DV 1"},
                    {"data_view_id": "dv_2", "data_view_name": "DV 2"},
                ],
                "summary": {"total_unique_components": 50},
                "distribution": {
                    "core": {"metrics_count": 6, "dimensions_count": 4},
                    "isolated": {"metrics_count": 7, "dimensions_count": 8},
                },
                "similarity_pairs": [
                    {
                        "data_view_1": {"id": "dv_1", "name": "DV 1"},
                        "data_view_2": {"id": "dv_2", "name": "DV 2"},
                        "jaccard_similarity": 0.95,
                        "shared_components": 10,
                        "union_size": 12,
                    },
                ],
            }
        )

        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(prev_data, f)
            prev_path = f.name

        try:
            comparison = compare_org_reports(current, prev_path)
            assert comparison.summary["new_duplicates"] == 0
            assert comparison.summary["resolved_duplicates"] == 0
        finally:
            os.unlink(prev_path)


class TestOrgStatsMode:
    """Test Feature 2: Org-stats quick summary mode"""

    def test_org_stats_config(self):
        """Test org-stats configuration"""
        config = OrgReportConfig(org_stats_only=True)
        assert config.org_stats_only is True

    def test_org_stats_skips_similarity(self):
        """Test that org-stats mode skips similarity computation"""
        config = OrgReportConfig(org_stats_only=True, skip_lock=True)
        mock_cja = Mock()
        # Simulate getDataViews returning a list of data views
        mock_cja.getDataViews.return_value = [
            {"id": "dv_1", "name": "DV 1"},
            {"id": "dv_2", "name": "DV 2"},
        ]
        # Simulate getDataView returning component details
        mock_cja.getDataView.return_value = {
            "id": "dv_1",
            "name": "DV 1",
            "components": [
                {"id": "m1", "type": "metric", "name": "Metric 1"},
            ],
        }

        import logging

        logger = logging.getLogger("test_org_stats_skip_sim")
        analyzer = OrgComponentAnalyzer(mock_cja, config, logger)

        with patch.object(analyzer, "_compute_similarity_matrix") as mock_sim:
            with patch.object(
                analyzer,
                "_list_and_filter_data_views",
                return_value=(
                    [{"id": "dv_1", "name": "DV 1"}, {"id": "dv_2", "name": "DV 2"}],
                    False,
                    2,
                ),
            ):
                with patch.object(
                    analyzer,
                    "_fetch_all_data_views",
                    return_value=[
                        DataViewSummary("dv_1", "DV 1", metric_ids={"m1"}, dimension_ids=set()),
                        DataViewSummary("dv_2", "DV 2", metric_ids={"m1"}, dimension_ids=set()),
                    ],
                ):
                    analyzer.run_analysis()
            mock_sim.assert_not_called()


class TestNewOrgReportResultFields:
    """Test new fields in OrgReportResult"""

    def test_governance_violations_field(self):
        """Test governance_violations field"""
        result = OrgReportResult(
            timestamp="2024-01-15T10:00:00",
            org_id="test",
            parameters=OrgReportConfig(),
            data_view_summaries=[],
            component_index={},
            distribution=ComponentDistribution(),
            similarity_pairs=None,
            recommendations=[],
            duration=1.0,
            governance_violations=[{"type": "test_violation"}],
            thresholds_exceeded=True,
        )
        assert result.governance_violations is not None
        assert result.thresholds_exceeded is True

    def test_naming_audit_field(self):
        """Test naming_audit field"""
        result = OrgReportResult(
            timestamp="2024-01-15T10:00:00",
            org_id="test",
            parameters=OrgReportConfig(),
            data_view_summaries=[],
            component_index={},
            distribution=ComponentDistribution(),
            similarity_pairs=None,
            recommendations=[],
            duration=1.0,
            naming_audit={"case_styles": {"snake_case": 10}},
        )
        assert result.naming_audit is not None
        assert result.naming_audit["case_styles"]["snake_case"] == 10

    def test_owner_summary_field(self):
        """Test owner_summary field"""
        result = OrgReportResult(
            timestamp="2024-01-15T10:00:00",
            org_id="test",
            parameters=OrgReportConfig(),
            data_view_summaries=[],
            component_index={},
            distribution=ComponentDistribution(),
            similarity_pairs=None,
            recommendations=[],
            duration=1.0,
            owner_summary={"total_owners": 3},
        )
        assert result.owner_summary is not None
        assert result.owner_summary["total_owners"] == 3

    def test_stale_components_field(self):
        """Test stale_components field"""
        result = OrgReportResult(
            timestamp="2024-01-15T10:00:00",
            org_id="test",
            parameters=OrgReportConfig(),
            data_view_summaries=[],
            component_index={},
            distribution=ComponentDistribution(),
            similarity_pairs=None,
            recommendations=[],
            duration=1.0,
            stale_components=[{"component_id": "test", "pattern": "stale_keyword"}],
        )
        assert result.stale_components is not None
        assert len(result.stale_components) == 1


class TestNewOrgReportConfigFields:
    """Test new fields in OrgReportConfig"""

    def test_governance_threshold_fields(self):
        """Test governance threshold configuration"""
        config = OrgReportConfig(duplicate_threshold=5, isolated_threshold=0.3, fail_on_threshold=True)
        assert config.duplicate_threshold == 5
        assert config.isolated_threshold == 0.3
        assert config.fail_on_threshold is True

    def test_feature_flags(self):
        """Test new feature flag fields"""
        config = OrgReportConfig(
            org_stats_only=True,
            audit_naming=True,
            compare_org_report="/path/to/prev.json",
            include_owner_summary=True,
            flag_stale=True,
        )
        assert config.org_stats_only is True
        assert config.audit_naming is True
        assert config.compare_org_report == "/path/to/prev.json"
        assert config.include_owner_summary is True
        assert config.flag_stale is True

    def test_defaults_for_new_fields(self):
        """Test default values for new config fields"""
        config = OrgReportConfig()
        assert config.duplicate_threshold is None
        assert config.isolated_threshold is None
        assert config.fail_on_threshold is False
        assert config.org_stats_only is False
        assert config.audit_naming is False
        assert config.compare_org_report is None
        assert config.include_owner_summary is False
        assert config.flag_stale is False

    def test_isolated_review_threshold_default(self):
        """Test isolated_review_threshold default value"""
        config = OrgReportConfig()
        assert config.isolated_review_threshold == 20

    def test_isolated_review_threshold_custom(self):
        """Test isolated_review_threshold custom value"""
        config = OrgReportConfig(isolated_review_threshold=50)
        assert config.isolated_review_threshold == 50


class TestIsolatedReviewThreshold:
    """Test configurable isolated component review threshold"""

    @pytest.fixture
    def mock_cja(self):
        return Mock()

    @pytest.fixture
    def mock_logger(self):
        import logging

        return logging.getLogger("test")

    def test_recommendation_uses_configurable_threshold(self, mock_cja, mock_logger):
        """Test that recommendation threshold is configurable"""
        # Default threshold (20)
        config = OrgReportConfig(isolated_review_threshold=20)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        summaries = [
            DataViewSummary("dv_1", "Specialized DV", metric_count=100, dimension_count=50),
        ]

        # Create 21 isolated components (exceeds default of 20)
        component_index = {
            f"isolated_{i}": ComponentInfo(f"isolated_{i}", "metric", data_views={"dv_1"}) for i in range(21)
        }

        distribution = ComponentDistribution()
        recommendations = analyzer._generate_recommendations(summaries, component_index, distribution, None)

        isolated_rec = [r for r in recommendations if r["type"] == "review_isolated"]
        assert len(isolated_rec) == 1

    def test_higher_threshold_no_recommendation(self, mock_cja, mock_logger):
        """Test higher threshold prevents recommendation"""
        # Set threshold to 50
        config = OrgReportConfig(isolated_review_threshold=50)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        summaries = [
            DataViewSummary("dv_1", "Specialized DV", metric_count=100, dimension_count=50),
        ]

        # Create 21 isolated components (below threshold of 50)
        component_index = {
            f"isolated_{i}": ComponentInfo(f"isolated_{i}", "metric", data_views={"dv_1"}) for i in range(21)
        }

        distribution = ComponentDistribution()
        recommendations = analyzer._generate_recommendations(summaries, component_index, distribution, None)

        # Should NOT trigger recommendation since 21 <= 50
        isolated_rec = [r for r in recommendations if r["type"] == "review_isolated"]
        assert len(isolated_rec) == 0

    def test_lower_threshold_triggers_recommendation(self, mock_cja, mock_logger):
        """Test lower threshold triggers recommendation earlier"""
        # Set threshold to 5
        config = OrgReportConfig(isolated_review_threshold=5)
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        summaries = [
            DataViewSummary("dv_1", "Specialized DV", metric_count=100, dimension_count=50),
        ]

        # Create only 6 isolated components (exceeds threshold of 5)
        component_index = {
            f"isolated_{i}": ComponentInfo(f"isolated_{i}", "metric", data_views={"dv_1"}) for i in range(6)
        }

        distribution = ComponentDistribution()
        recommendations = analyzer._generate_recommendations(summaries, component_index, distribution, None)

        # Should trigger recommendation since 6 > 5
        isolated_rec = [r for r in recommendations if r["type"] == "review_isolated"]
        assert len(isolated_rec) == 1


class TestClusteringMethods:
    """Test clustering method configurations"""

    @pytest.fixture
    def mock_cja(self):
        return Mock()

    def test_average_method_no_warning(self, mock_cja):
        """Test that average method does not log a warning"""
        import logging

        logger = logging.getLogger("test_average")
        logger.setLevel(logging.WARNING)

        class LogCapture(logging.Handler):
            def __init__(self):
                super().__init__()
                self.warnings = []

            def emit(self, record):
                if record.levelno >= logging.WARNING:
                    self.warnings.append(record.getMessage())

        handler = LogCapture()
        logger.addHandler(handler)

        config = OrgReportConfig(enable_clustering=True, cluster_method="average")
        analyzer = OrgComponentAnalyzer(mock_cja, config, logger)

        summaries = [
            DataViewSummary("dv_1", "DV 1", metric_ids={"m1", "m2"}, dimension_ids=set()),
            DataViewSummary("dv_2", "DV 2", metric_ids={"m1", "m3"}, dimension_ids=set()),
        ]

        try:
            try:
                analyzer._compute_clusters(summaries)
            except ImportError:
                pytest.skip("scipy not installed")

            # Check that no warning about ward/euclidean was logged
            assert not any("ward" in w.lower() and "euclidean" in w.lower() for w in handler.warnings)
        finally:
            logger.removeHandler(handler)


class TestMemoryWarning:
    """Test memory usage warning functionality"""

    @pytest.fixture
    def mock_cja(self):
        return Mock()

    @pytest.fixture
    def mock_logger(self):
        import logging

        logger = logging.getLogger("test_memory_warning")
        logger.setLevel(logging.WARNING)
        return logger

    def test_memory_estimation_basic(self, mock_cja, mock_logger):
        """Test that memory estimation returns reasonable values"""
        config = OrgReportConfig()
        analyzer = OrgComponentAnalyzer(mock_cja, config, mock_logger)

        # Create a component index with known sizes
        component_index = {
            f"metric/comp_{i}": ComponentInfo(
                f"metric/comp_{i}",
                "metric",
                name=f"Component {i}",
                data_views={f"dv_{j}" for j in range(10)},
            )
            for i in range(100)
        }

        estimated_mb = analyzer._estimate_component_index_memory(component_index)

        # Should be a positive number
        assert estimated_mb > 0
        # With 100 components, each with ~200 base + 15 id + 12 name + 500 dv overhead + 50 misc
        # = ~777 bytes per component = ~77,700 bytes = ~0.074 MB
        # Allow for some variance in the estimate
        assert 0.01 < estimated_mb < 1.0

    def test_warning_logged_when_threshold_exceeded(self, mock_cja):
        """Test that warning is logged when memory exceeds threshold"""
        import logging

        class LogCapture(logging.Handler):
            def __init__(self):
                super().__init__()
                self.warnings = []

            def emit(self, record):
                if record.levelno >= logging.WARNING:
                    self.warnings.append(record.getMessage())

        logger = logging.getLogger("test_memory_threshold")
        logger.setLevel(logging.WARNING)
        handler = LogCapture()
        logger.addHandler(handler)

        # Set a very low threshold to trigger warning
        config = OrgReportConfig(memory_warning_threshold_mb=1)
        analyzer = OrgComponentAnalyzer(mock_cja, config, logger)

        # Create a large component index
        component_index = {
            f"metric/comp_{i}": ComponentInfo(
                f"metric/comp_{i}",
                "metric",
                name=f"Component {i} with a longer name to increase memory",
                data_views={f"dv_{j}" for j in range(50)},  # Many data views
            )
            for i in range(1000)  # Many components
        }

        try:
            analyzer._check_memory_warning(component_index)

            # Should have logged a warning about memory
            assert any("memory" in w.lower() and "threshold" in w.lower() for w in handler.warnings)
        finally:
            logger.removeHandler(handler)

    def test_no_warning_when_below_threshold(self, mock_cja):
        """Test that no warning is logged when memory is below threshold"""
        import logging

        class LogCapture(logging.Handler):
            def __init__(self):
                super().__init__()
                self.warnings = []

            def emit(self, record):
                if record.levelno >= logging.WARNING:
                    self.warnings.append(record.getMessage())

        logger = logging.getLogger("test_memory_no_warning")
        logger.setLevel(logging.WARNING)
        handler = LogCapture()
        logger.addHandler(handler)

        # Set a high threshold that won't be exceeded
        config = OrgReportConfig(memory_warning_threshold_mb=1000)
        analyzer = OrgComponentAnalyzer(mock_cja, config, logger)

        # Create a small component index
        component_index = {
            f"metric/comp_{i}": ComponentInfo(f"metric/comp_{i}", "metric", data_views={"dv_1"}) for i in range(10)
        }

        try:
            analyzer._check_memory_warning(component_index)

            # Should NOT have logged a warning about memory
            assert not any("memory" in w.lower() and "threshold" in w.lower() for w in handler.warnings)
        finally:
            logger.removeHandler(handler)

    def test_warning_disabled_with_zero(self, mock_cja):
        """Test that no warning is logged when threshold is 0 (disabled)"""
        import logging

        class LogCapture(logging.Handler):
            def __init__(self):
                super().__init__()
                self.warnings = []

            def emit(self, record):
                if record.levelno >= logging.WARNING:
                    self.warnings.append(record.getMessage())

        logger = logging.getLogger("test_memory_disabled")
        logger.setLevel(logging.WARNING)
        handler = LogCapture()
        logger.addHandler(handler)

        # Disable warning with threshold of 0
        config = OrgReportConfig(memory_warning_threshold_mb=0)
        analyzer = OrgComponentAnalyzer(mock_cja, config, logger)

        # Create a large component index that would normally trigger warning
        component_index = {
            f"metric/comp_{i}": ComponentInfo(
                f"metric/comp_{i}",
                "metric",
                name=f"Component {i} with a longer name",
                data_views={f"dv_{j}" for j in range(50)},
            )
            for i in range(1000)
        }

        try:
            analyzer._check_memory_warning(component_index)

            # Should NOT have logged any warning (disabled)
            assert not any("memory" in w.lower() for w in handler.warnings)
        finally:
            logger.removeHandler(handler)

    def test_warning_disabled_with_none(self, mock_cja):
        """Test that no warning is logged when threshold is None (disabled)"""
        import logging

        class LogCapture(logging.Handler):
            def __init__(self):
                super().__init__()
                self.warnings = []

            def emit(self, record):
                if record.levelno >= logging.WARNING:
                    self.warnings.append(record.getMessage())

        logger = logging.getLogger("test_memory_none")
        logger.setLevel(logging.WARNING)
        handler = LogCapture()
        logger.addHandler(handler)

        # Disable warning with threshold of None
        config = OrgReportConfig(memory_warning_threshold_mb=None)
        analyzer = OrgComponentAnalyzer(mock_cja, config, logger)

        # Create a large component index
        component_index = {
            f"metric/comp_{i}": ComponentInfo(f"metric/comp_{i}", "metric", data_views={f"dv_{j}" for j in range(50)})
            for i in range(1000)
        }

        try:
            analyzer._check_memory_warning(component_index)

            # Should NOT have logged any warning (disabled)
            assert not any("memory" in w.lower() for w in handler.warnings)
        finally:
            logger.removeHandler(handler)


class TestSmartCacheInvalidation:
    """Test smart cache invalidation based on modification timestamps"""

    def test_cache_validates_modification_timestamp(self):
        """Test that cache returns None when current_modified differs from cached"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = OrgReportCache(cache_dir=Path(tmpdir))

            # Store a summary with a modification timestamp
            summary = DataViewSummary(
                data_view_id="dv_test",
                data_view_name="Test DV",
                metric_ids={"m1", "m2"},
                dimension_ids={"d1"},
                metric_count=2,
                dimension_count=1,
                modified="2024-01-15T10:00:00Z",
            )
            cache.put(summary, include_metadata=True)

            # Try to get with same modification timestamp - should succeed
            retrieved = cache.get("dv_test", max_age_hours=24, current_modified="2024-01-15T10:00:00Z")
            assert retrieved is not None
            assert retrieved.data_view_id == "dv_test"

            # Try to get with different modification timestamp - should fail
            retrieved = cache.get(
                "dv_test",
                max_age_hours=24,
                current_modified="2024-01-16T10:00:00Z",  # Different timestamp
            )
            assert retrieved is None

    def test_cache_returns_valid_when_no_current_modified(self):
        """Test backward compatibility - cache works when no current_modified provided"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = OrgReportCache(cache_dir=Path(tmpdir))

            summary = DataViewSummary(
                data_view_id="dv_test",
                data_view_name="Test DV",
                metric_ids={"m1"},
                dimension_ids=set(),
                metric_count=1,
                dimension_count=0,
                modified="2024-01-15T10:00:00Z",
            )
            cache.put(summary, include_metadata=True)

            # Get without providing current_modified - should still work
            retrieved = cache.get("dv_test", max_age_hours=24)
            assert retrieved is not None
            assert retrieved.data_view_id == "dv_test"

    def test_has_valid_entry_true_for_fresh_entry(self):
        """Test has_valid_entry returns True for fresh cache entries"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = OrgReportCache(cache_dir=Path(tmpdir))

            summary = DataViewSummary(
                data_view_id="dv_test",
                data_view_name="Test DV",
            )
            cache.put(summary)

            # Fresh entry should be valid
            assert cache.has_valid_entry("dv_test", max_age_hours=24) is True

            # Non-existent entry should not be valid
            assert cache.has_valid_entry("nonexistent", max_age_hours=24) is False

    def test_get_cached_modified(self):
        """Test get_cached_modified returns cached modification timestamp"""
        with tempfile.TemporaryDirectory() as tmpdir:
            cache = OrgReportCache(cache_dir=Path(tmpdir))

            summary = DataViewSummary(
                data_view_id="dv_test",
                data_view_name="Test DV",
                modified="2024-01-15T10:00:00Z",
            )
            cache.put(summary, include_metadata=True)

            # Should return the cached modified timestamp
            assert cache.get_cached_modified("dv_test") == "2024-01-15T10:00:00Z"

            # Non-existent entry should return None
            assert cache.get_cached_modified("nonexistent") is None

    def test_analyzer_validates_when_flag_set(self):
        """Test that analyzer validates cache when validate_cache is True"""
        import logging

        mock_cja = Mock()
        logger = logging.getLogger("test_validate_cache")

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = OrgReportCache(cache_dir=Path(tmpdir))

            # Pre-populate cache with old modified timestamp
            summary = DataViewSummary(
                data_view_id="dv_1",
                data_view_name="DV 1",
                metric_ids={"m1"},
                dimension_ids=set(),
                metric_count=1,
                dimension_count=0,
                modified="2024-01-15T10:00:00Z",
            )
            # Put with all flags to match the config defaults
            cache.put(summary, include_metadata=True, include_component_types=True)

            config = OrgReportConfig(
                use_cache=True,
                validate_cache=True,
                cache_max_age_hours=24,
                include_metadata=True,  # Match the cache flags
                include_component_types=True,  # Default is True, match cache
            )
            analyzer = OrgComponentAnalyzer(mock_cja, config, logger, cache=cache)

            # Pass data view list with different modification timestamp
            # (batch optimization: uses modified from the list, not individual API calls)
            to_fetch, valid_summaries, valid_count, stale_count = analyzer._validate_cache_entries(
                [{"id": "dv_1", "name": "DV 1", "modified": "2024-01-16T10:00:00Z"}],
            )

            # Should detect stale entry and need to re-fetch
            assert len(to_fetch) == 1
            assert len(valid_summaries) == 0
            assert valid_count == 0
            assert stale_count == 1

    def test_analyzer_skips_validation_by_default(self):
        """Test that analyzer does not validate cache when validate_cache is False"""
        import logging

        mock_cja = Mock()
        logger = logging.getLogger("test_no_validate")

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = OrgReportCache(cache_dir=Path(tmpdir))

            # Pre-populate cache
            summary = DataViewSummary(
                data_view_id="dv_1",
                data_view_name="DV 1",
                metric_ids={"m1"},
                dimension_ids=set(),
                metric_count=1,
                dimension_count=0,
                modified="2024-01-15T10:00:00Z",
            )
            cache.put(summary)

            # validate_cache=False (default)
            config = OrgReportConfig(
                use_cache=True,
                validate_cache=False,
                cache_max_age_hours=24,
            )
            OrgComponentAnalyzer(mock_cja, config, logger, cache=cache)

            # Simulate _fetch_all_data_views behavior - should use standard lookup
            # Get from cache without validation
            retrieved = cache.get("dv_1", max_age_hours=24)
            assert retrieved is not None  # Should get from cache without validation

    def test_analyzer_validates_with_matching_timestamp(self):
        """Test that validation passes when timestamps match"""
        import logging

        mock_cja = Mock()
        logger = logging.getLogger("test_validate_match")

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = OrgReportCache(cache_dir=Path(tmpdir))

            # Pre-populate cache with all flags matching the config
            summary = DataViewSummary(
                data_view_id="dv_1",
                data_view_name="DV 1",
                metric_ids={"m1"},
                dimension_ids=set(),
                metric_count=1,
                dimension_count=0,
                modified="2024-01-15T10:00:00Z",
            )
            # Put with all flags to match the config defaults
            cache.put(summary, include_metadata=True, include_component_types=True)

            config = OrgReportConfig(
                use_cache=True,
                validate_cache=True,
                cache_max_age_hours=24,
                include_metadata=True,  # Match the cache flags
                include_component_types=True,  # Default is True, match cache
            )
            analyzer = OrgComponentAnalyzer(mock_cja, config, logger, cache=cache)

            # Pass data view list with same modification timestamp
            # (batch optimization: uses modified from the list, not individual API calls)
            to_fetch, valid_summaries, valid_count, stale_count = analyzer._validate_cache_entries(
                [{"id": "dv_1", "name": "DV 1", "modified": "2024-01-15T10:00:00Z"}],
            )

            # Should detect valid entry and use cache
            assert len(to_fetch) == 0
            assert len(valid_summaries) == 1
            assert valid_count == 1
            assert stale_count == 0

    def test_missing_timestamp_treated_as_stale(self):
        """Test that missing modification timestamps are treated as stale when validating"""
        import logging

        mock_cja = Mock()
        logger = logging.getLogger("test_missing_timestamp")

        with tempfile.TemporaryDirectory() as tmpdir:
            cache = OrgReportCache(cache_dir=Path(tmpdir))

            # Pre-populate cache
            summary = DataViewSummary(
                data_view_id="dv_1",
                data_view_name="DV 1",
                metric_ids={"m1"},
                dimension_ids=set(),
                metric_count=1,
                dimension_count=0,
                modified="2024-01-15T10:00:00Z",
            )
            cache.put(summary, include_metadata=True, include_component_types=True)

            config = OrgReportConfig(
                use_cache=True,
                validate_cache=True,
                cache_max_age_hours=24,
                include_metadata=True,
                include_component_types=True,
            )
            analyzer = OrgComponentAnalyzer(mock_cja, config, logger, cache=cache)

            # Pass data view WITHOUT modification timestamp (some API responses omit this)
            to_fetch, valid_summaries, valid_count, stale_count = analyzer._validate_cache_entries(
                [{"id": "dv_1", "name": "DV 1"}],  # No 'modified' or 'modifiedDate' field
            )

            # Should treat missing timestamp as stale to honor --validate-cache guarantee
            assert len(to_fetch) == 1
            assert len(valid_summaries) == 0
            assert valid_count == 0
            assert stale_count == 1
