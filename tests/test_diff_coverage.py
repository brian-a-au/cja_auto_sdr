"""Tests targeting uncovered lines in the cja_auto_sdr.diff package.

Covers edge cases in comparator.py, models.py, and git.py to maximize
line coverage across the diff subpackage.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

from cja_auto_sdr.diff.comparator import DataViewComparator
from cja_auto_sdr.diff.git import (
    _snapshot_pathspecs_for_data_view,
    generate_git_commit_message,
    git_commit_snapshot,
    git_get_user_info,
    git_init_snapshot_repo,
    save_git_friendly_snapshot,
)
from cja_auto_sdr.diff.models import (
    ChangeType,
    ComponentDiff,
    DataViewSnapshot,
    DiffResult,
    DiffSummary,
    InventoryItemDiff,
)

# ==================== Helpers ====================


def _make_snapshot(**overrides) -> DataViewSnapshot:
    """Build a minimal DataViewSnapshot with sensible defaults."""
    defaults = {
        "data_view_id": "dv_test",
        "data_view_name": "Test DV",
        "owner": "owner@test.com",
        "description": "desc",
        "metrics": [],
        "dimensions": [],
    }
    defaults.update(overrides)
    return DataViewSnapshot(**defaults)


# ==================== comparator.py tests ====================


class TestDimensionsOnly:
    """Lines 144-145: dimensions_only=True skips metrics."""

    def test_dimensions_only_skips_metrics(self):
        source = _make_snapshot(
            metrics=[{"id": "m1", "name": "Metric A"}],
            dimensions=[{"id": "d1", "name": "Dim A"}],
        )
        target = _make_snapshot(
            metrics=[{"id": "m1", "name": "Metric A changed"}],
            dimensions=[{"id": "d1", "name": "Dim A"}],
        )

        comp = DataViewComparator(dimensions_only=True)
        result = comp.compare(source, target)

        # Metrics are empty because dimensions_only skips them
        assert result.metric_diffs == []
        # Dimensions should still be compared
        assert len(result.dimension_diffs) >= 1


class TestIncludeSegments:
    """Lines 169-177: include_segments=True compares segment inventory."""

    def test_compare_with_segments_inventory(self):
        source = _make_snapshot(
            segments_inventory=[
                {"segment_id": "s1", "segment_name": "Seg A", "description": "old desc"},
            ],
        )
        target = _make_snapshot(
            segments_inventory=[
                {"segment_id": "s1", "segment_name": "Seg A", "description": "new desc"},
                {"segment_id": "s2", "segment_name": "Seg B", "description": "brand new"},
            ],
        )

        comp = DataViewComparator(include_segments=True)
        result = comp.compare(source, target)

        assert result.segments_diffs is not None
        assert len(result.segments_diffs) == 2

        change_types = {d.id: d.change_type for d in result.segments_diffs}
        assert change_types["s1"] == ChangeType.MODIFIED
        assert change_types["s2"] == ChangeType.ADDED


class TestCountChanges:
    """Line 202: _count_changes with None and empty list."""

    def test_count_changes_none(self):
        comp = DataViewComparator()
        assert comp._count_changes(None) == "0 items"

    def test_count_changes_empty_list(self):
        comp = DataViewComparator()
        assert comp._count_changes([]) == "0 items"

    def test_count_changes_with_items(self):
        comp = DataViewComparator()
        diffs = [
            InventoryItemDiff(id="1", name="A", change_type=ChangeType.ADDED, inventory_type="calculated_metric"),
            InventoryItemDiff(id="2", name="B", change_type=ChangeType.REMOVED, inventory_type="calculated_metric"),
            InventoryItemDiff(id="3", name="C", change_type=ChangeType.MODIFIED, inventory_type="calculated_metric"),
        ]
        result = comp._count_changes(diffs)
        assert result == "+1 -1 ~1"


class TestFindInventoryChangedFields:
    """Lines 296-305, 314: derived_field type, unknown type fallback, ignore_fields, field differences."""

    def test_derived_field_type(self):
        comp = DataViewComparator()
        source = {"name": "DF1", "description": "old", "logic_summary": "if A"}
        target = {"name": "DF1", "description": "new", "logic_summary": "if B"}

        changed = comp._find_inventory_changed_fields(source, target, "derived_field")

        assert "description" in changed
        assert "logic_summary" in changed

    def test_unknown_inventory_type_falls_back(self):
        comp = DataViewComparator()
        source = {"name": "X", "description": "old"}
        target = {"name": "X", "description": "new"}

        # Unknown type falls back to CALC_METRICS_COMPARE_FIELDS
        changed = comp._find_inventory_changed_fields(source, target, "unknown_type")
        assert "description" in changed

    def test_ignore_fields_skips_fields(self):
        comp = DataViewComparator(ignore_fields=["description"])
        source = {"name": "X", "description": "old"}
        target = {"name": "X", "description": "new"}

        changed = comp._find_inventory_changed_fields(source, target, "calculated_metric")
        assert "description" not in changed

    def test_records_field_differences(self):
        comp = DataViewComparator()
        source = {"name": "A", "description": "desc1", "owner": "alice"}
        target = {"name": "A", "description": "desc2", "owner": "bob"}

        changed = comp._find_inventory_changed_fields(source, target, "calculated_metric")
        assert changed["description"] == ("desc1", "desc2")
        assert changed["owner"] == ("alice", "bob")


class TestNormalizeValue:
    """Line 377: exception path when pd.isna raises TypeError."""

    def test_normalize_value_type_error_from_isna(self):
        comp = DataViewComparator()
        # A list causes pd.isna to return an array, and the truthiness check
        # of that array raises a TypeError / ValueError in the except clause.
        result = comp._normalize_value(["a", "b"])
        assert result == ["a", "b"]

    def test_normalize_value_dict_triggers_normalize_dict(self):
        comp = DataViewComparator()
        result = comp._normalize_value({"key": "value"})
        assert result == {"key": "value"}

    def test_normalize_value_none(self):
        comp = DataViewComparator()
        assert comp._normalize_value(None) == ""


class TestNormalizeDict:
    """Lines 392-393: _normalize_dict({}) returns {}."""

    def test_normalize_empty_dict(self):
        comp = DataViewComparator()
        assert comp._normalize_dict({}) == {}

    def test_normalize_dict_strips_empty_values(self):
        comp = DataViewComparator()
        result = comp._normalize_dict({"a": "", "b": "hello", "c": None, "d": {}})
        assert result == {"b": "hello"}


class TestBuildSummaryWithSegments:
    """Lines 455-461: _build_summary with segments_diffs populated."""

    def test_build_summary_includes_segments(self):
        source = _make_snapshot(
            segments_inventory=[
                {"segment_id": "s1", "segment_name": "S1"},
                {"segment_id": "s2", "segment_name": "S2"},
            ],
        )
        target = _make_snapshot(
            segments_inventory=[
                {"segment_id": "s1", "segment_name": "S1"},
                {"segment_id": "s3", "segment_name": "S3"},
            ],
        )

        seg_diffs = [
            InventoryItemDiff(id="s1", name="S1", change_type=ChangeType.UNCHANGED, inventory_type="segment"),
            InventoryItemDiff(id="s2", name="S2", change_type=ChangeType.REMOVED, inventory_type="segment"),
            InventoryItemDiff(id="s3", name="S3", change_type=ChangeType.ADDED, inventory_type="segment"),
        ]

        comp = DataViewComparator()
        summary = comp._build_summary(source, target, [], [], segments_diffs=seg_diffs)

        assert summary.source_segments_count == 2
        assert summary.target_segments_count == 2
        assert summary.segments_added == 1
        assert summary.segments_removed == 1
        assert summary.segments_unchanged == 1


# ==================== models.py tests ====================


class TestComponentDiffPostInit:
    """Line 33: ComponentDiff(changed_fields=None) initializes to {}."""

    def test_changed_fields_none_defaults_to_empty(self):
        diff = ComponentDiff(id="c1", name="comp", change_type=ChangeType.ADDED, changed_fields=None)
        assert diff.changed_fields == {}

    def test_changed_fields_provided_stays(self):
        diff = ComponentDiff(id="c1", name="comp", change_type=ChangeType.ADDED, changed_fields={"a": ("x", "y")})
        assert diff.changed_fields == {"a": ("x", "y")}


class TestInventoryItemDiffPostInit:
    """Line 274: InventoryItemDiff(changed_fields=None) initializes to {}."""

    def test_changed_fields_none_defaults_to_empty(self):
        diff = InventoryItemDiff(
            id="i1",
            name="item",
            change_type=ChangeType.ADDED,
            inventory_type="calculated_metric",
            changed_fields=None,
        )
        assert diff.changed_fields == {}


class TestCalcMetricsChangePercent:
    """Lines 154-159: calc_metrics_change_percent property."""

    def test_calc_metrics_change_percent_nonzero(self):
        summary = DiffSummary(
            source_calc_metrics_count=10,
            target_calc_metrics_count=10,
            calc_metrics_added=2,
            calc_metrics_removed=1,
            calc_metrics_modified=1,
        )
        assert summary.calc_metrics_change_percent == 40.0

    def test_calc_metrics_change_percent_zero_total(self):
        summary = DiffSummary()
        assert summary.calc_metrics_change_percent == 0.0


class TestSegmentsChangePercent:
    """Lines 167-172: segments_change_percent property."""

    def test_segments_change_percent_nonzero(self):
        summary = DiffSummary(
            source_segments_count=20,
            target_segments_count=20,
            segments_added=4,
        )
        assert summary.segments_change_percent == 20.0

    def test_segments_change_percent_zero_total(self):
        summary = DiffSummary()
        assert summary.segments_change_percent == 0.0


class TestNaturalLanguageSummary:
    """Lines 195-221: natural_language_summary with calc_metrics/segments."""

    def test_summary_with_calc_metrics_and_segments(self):
        summary = DiffSummary(
            metrics_added=1,
            dimensions_removed=2,
            calc_metrics_added=3,
            calc_metrics_removed=1,
            calc_metrics_modified=2,
            segments_added=5,
            segments_removed=0,
            segments_modified=1,
        )
        text = summary.natural_language_summary
        assert "Metrics: 1 added" in text
        assert "Dimensions: 2 removed" in text
        assert "Calculated Metrics: 3 added, 1 removed, 2 modified" in text
        assert "Segments: 5 added, 1 modified" in text

    def test_summary_no_changes(self):
        summary = DiffSummary()
        assert summary.natural_language_summary == "No changes detected"

    def test_summary_only_calc_metrics(self):
        summary = DiffSummary(calc_metrics_modified=7)
        text = summary.natural_language_summary
        assert "Calculated Metrics: 7 modified" in text
        # The plain "Metrics:" section (not prefixed by "Calculated ") should be absent
        parts = text.split("; ")
        assert not any(p.startswith("Metrics:") for p in parts)
        assert not any(p.startswith("Dimensions:") for p in parts)

    def test_summary_only_segments(self):
        summary = DiffSummary(segments_removed=3)
        text = summary.natural_language_summary
        assert "Segments: 3 removed" in text


class TestGetInventorySummary:
    """Line 352: get_inventory_summary on DataViewSnapshot with inventory data."""

    def test_inventory_summary_with_data(self):
        snap = _make_snapshot(
            calculated_metrics_inventory=[{"metric_id": "m1"}, {"metric_id": "m2"}],
            segments_inventory=[{"segment_id": "s1"}],
        )
        result = snap.get_inventory_summary()
        assert result["calculated_metrics"]["present"] is True
        assert result["calculated_metrics"]["count"] == 2
        assert result["segments"]["present"] is True
        assert result["segments"]["count"] == 1

    def test_inventory_summary_without_data(self):
        snap = _make_snapshot()
        result = snap.get_inventory_summary()
        assert result["calculated_metrics"]["present"] is False
        assert result["calculated_metrics"]["count"] == 0
        assert result["segments"]["present"] is False
        assert result["segments"]["count"] == 0


# ==================== git.py tests ====================


class TestSnapshotPathspecs:
    """Lines 18-19: _snapshot_pathspecs_for_data_view with non-existent dir."""

    def test_non_existent_directory_returns_empty(self, tmp_path):
        result = _snapshot_pathspecs_for_data_view(tmp_path / "does_not_exist", "dv_123")
        assert result == []

    def test_matching_directory(self, tmp_path):
        (tmp_path / "MyDV_dv_123").mkdir()
        (tmp_path / "OtherDV_dv_456").mkdir()
        result = _snapshot_pathspecs_for_data_view(tmp_path, "dv_123")
        assert result == ["MyDV_dv_123"]


class TestGitGetUserInfo:
    """Lines 42-50: git_get_user_info when subprocess raises TimeoutExpired or FileNotFoundError."""

    @patch("cja_auto_sdr.diff.git.subprocess.run")
    def test_timeout_expired_falls_back(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=5)
        name, email = git_get_user_info()
        assert name == "CJA SDR Generator"
        assert email == ""

    @patch("cja_auto_sdr.diff.git.subprocess.run")
    def test_file_not_found_falls_back(self, mock_run):
        mock_run.side_effect = FileNotFoundError("git not found")
        name, email = git_get_user_info()
        assert name == "CJA SDR Generator"
        assert email == ""


class TestGenerateGitCommitMessage:
    """Lines 173-177: commit message with calc_metrics/segments changes and removals."""

    def test_commit_message_with_diff_result(self):
        summary = DiffSummary(
            metrics_added=2,
            metrics_removed=1,
            metrics_modified=3,
            dimensions_added=0,
            dimensions_removed=4,
            dimensions_modified=0,
            source_metrics_count=10,
            target_metrics_count=11,
            source_dimensions_count=8,
            target_dimensions_count=4,
        )
        diff_result = DiffResult(
            summary=summary,
            metadata_diff=MagicMock(),
            metric_diffs=[],
            dimension_diffs=[],
        )

        msg = generate_git_commit_message(
            data_view_id="dv_abc",
            data_view_name="My Data View",
            metrics_count=11,
            dimensions_count=4,
            diff_result=diff_result,
        )

        assert "+ 2 metrics added" in msg
        assert "- 1 metrics removed" in msg
        assert "~ 3 metrics modified" in msg
        assert "- 4 dimensions removed" in msg

    def test_commit_message_custom(self):
        msg = generate_git_commit_message(
            data_view_id="dv_abc",
            data_view_name="My DV",
            metrics_count=5,
            dimensions_count=3,
            custom_message="Manual snapshot",
        )
        assert "[dv_abc] Manual snapshot" in msg


class TestGitCommitSnapshotEdgeCases:
    """Lines 222-276: git_commit_snapshot edge cases and failure paths."""

    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.diff.git._snapshot_pathspecs_for_data_view", return_value=[])
    def test_no_matching_snapshot_dirs(self, mock_pathspecs, mock_is_git, tmp_path):
        ok, msg = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_missing",
            data_view_name="Missing",
            metrics_count=0,
            dimensions_count=0,
        )
        assert ok is False
        assert "No snapshot directory found" in msg

    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.diff.git._snapshot_pathspecs_for_data_view", return_value=["snap_dv_x"])
    @patch("cja_auto_sdr.diff.git.subprocess.run")
    def test_git_add_fails(self, mock_run, mock_pathspecs, mock_is_git, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stderr="fatal: bad path")
        ok, msg = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_x",
            data_view_name="DV X",
            metrics_count=5,
            dimensions_count=3,
        )
        assert ok is False
        assert "git add failed" in msg

    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.diff.git._snapshot_pathspecs_for_data_view", return_value=["snap_dv_x"])
    @patch("cja_auto_sdr.diff.git.subprocess.run")
    def test_git_commit_fails(self, mock_run, mock_pathspecs, mock_is_git, tmp_path):
        def run_side_effect(cmd, **kwargs):
            mock_result = MagicMock()
            if cmd[1] == "add":
                mock_result.returncode = 0
                mock_result.stderr = ""
            elif cmd[1] == "diff":
                # returncode=1 means there are staged changes
                mock_result.returncode = 1
            elif cmd[1] == "commit":
                mock_result.returncode = 1
                mock_result.stderr = "commit hook failed"
            else:
                mock_result.returncode = 0
                mock_result.stdout = ""
                mock_result.stderr = ""
            return mock_result

        mock_run.side_effect = run_side_effect
        ok, msg = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_x",
            data_view_name="DV X",
            metrics_count=5,
            dimensions_count=3,
        )
        assert ok is False
        assert "git commit failed" in msg

    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.diff.git._snapshot_pathspecs_for_data_view", return_value=["snap_dv_x"])
    @patch("cja_auto_sdr.diff.git.subprocess.run")
    def test_push_failure(self, mock_run, mock_pathspecs, mock_is_git, tmp_path):
        call_count = 0

        def run_side_effect(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            if cmd[1] == "add":
                mock_result.returncode = 0
                mock_result.stderr = ""
            elif cmd[1] == "diff":
                mock_result.returncode = 1  # has changes
            elif cmd[1] == "commit":
                mock_result.returncode = 0
                mock_result.stdout = ""
                mock_result.stderr = ""
            elif cmd[1] == "rev-parse":
                mock_result.returncode = 0
                mock_result.stdout = "abc12345"
            elif cmd[1] == "push":
                mock_result.returncode = 1
                mock_result.stderr = "remote rejected"
            else:
                mock_result.returncode = 0
                mock_result.stdout = ""
                mock_result.stderr = ""
            return mock_result

        mock_run.side_effect = run_side_effect
        ok, msg = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_x",
            data_view_name="DV X",
            metrics_count=5,
            dimensions_count=3,
            push=True,
        )
        # Commit succeeds but push fails — still returns True
        assert ok is True
        assert "push failed" in msg

    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.diff.git._snapshot_pathspecs_for_data_view", return_value=["snap_dv_x"])
    @patch("cja_auto_sdr.diff.git.subprocess.run")
    def test_timeout_expired_exception(self, mock_run, mock_pathspecs, mock_is_git, tmp_path):
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=30)
        ok, msg = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_x",
            data_view_name="DV X",
            metrics_count=5,
            dimensions_count=3,
        )
        assert ok is False
        assert "timed out" in msg

    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.diff.git._snapshot_pathspecs_for_data_view", return_value=["snap_dv_x"])
    @patch("cja_auto_sdr.diff.git.subprocess.run")
    def test_file_not_found_exception(self, mock_run, mock_pathspecs, mock_is_git, tmp_path):
        mock_run.side_effect = FileNotFoundError("git not installed")
        ok, msg = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_x",
            data_view_name="DV X",
            metrics_count=5,
            dimensions_count=3,
        )
        assert ok is False
        assert "Git not found" in msg

    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.diff.git._snapshot_pathspecs_for_data_view", return_value=["snap_dv_x"])
    @patch("cja_auto_sdr.diff.git.subprocess.run")
    def test_generic_exception(self, mock_run, mock_pathspecs, mock_is_git, tmp_path):
        mock_run.side_effect = subprocess.SubprocessError("unexpected git problem")
        ok, msg = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_x",
            data_view_name="DV X",
            metrics_count=5,
            dimensions_count=3,
        )
        assert ok is False
        assert "Git error" in msg


class TestGitInitSnapshotRepo:
    """Lines 292-362: git_init_snapshot_repo failures."""

    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=False)
    @patch("cja_auto_sdr.diff.git.subprocess.run")
    def test_git_init_fails(self, mock_run, mock_is_git, tmp_path):
        mock_run.return_value = MagicMock(returncode=1, stderr="init error")
        ok, msg = git_init_snapshot_repo(tmp_path / "new_repo")
        assert ok is False
        assert "git init failed" in msg

    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=False)
    @patch("cja_auto_sdr.diff.git.git_get_user_info", return_value=("User", "user@e.com"))
    @patch("cja_auto_sdr.diff.git.subprocess.run")
    def test_git_config_user_name_fails(self, mock_run, mock_user_info, mock_is_git, tmp_path):
        call_count = 0

        def run_side_effect(cmd, **kwargs):
            nonlocal call_count
            call_count += 1
            mock_result = MagicMock()
            if "init" in cmd:
                mock_result.returncode = 0
            elif "user.name" in cmd:
                mock_result.returncode = 1
                mock_result.stderr = "config error"
            else:
                mock_result.returncode = 0
                mock_result.stdout = ""
                mock_result.stderr = ""
            return mock_result

        mock_run.side_effect = run_side_effect
        ok, msg = git_init_snapshot_repo(tmp_path / "repo_config_fail")
        assert ok is False
        assert "user.name failed" in msg

    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=False)
    @patch("cja_auto_sdr.diff.git.git_get_user_info", return_value=("User", "user@e.com"))
    @patch("cja_auto_sdr.diff.git.subprocess.run")
    def test_git_config_user_email_fails(self, mock_run, mock_user_info, mock_is_git, tmp_path):
        def run_side_effect(cmd, **kwargs):
            mock_result = MagicMock()
            if "init" in cmd:
                mock_result.returncode = 0
            elif "user.name" in cmd:
                mock_result.returncode = 0
            elif "user.email" in cmd:
                mock_result.returncode = 1
                mock_result.stderr = "email config error"
            else:
                mock_result.returncode = 0
                mock_result.stdout = ""
                mock_result.stderr = ""
            return mock_result

        mock_run.side_effect = run_side_effect
        ok, msg = git_init_snapshot_repo(tmp_path / "repo_email_fail")
        assert ok is False
        assert "user.email failed" in msg

    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=False)
    @patch("cja_auto_sdr.diff.git.git_get_user_info", return_value=("User", "user@e.com"))
    @patch("cja_auto_sdr.diff.git.subprocess.run")
    def test_git_add_in_init_fails(self, mock_run, mock_user_info, mock_is_git, tmp_path):
        repo_dir = tmp_path / "repo_add_fail"

        def run_side_effect(cmd, **kwargs):
            mock_result = MagicMock()
            if "init" in cmd:
                mock_result.returncode = 0
            elif "user.name" in cmd:
                mock_result.returncode = 0
            elif "user.email" in cmd:
                mock_result.returncode = 0
            elif cmd[1] == "add":
                mock_result.returncode = 1
                mock_result.stderr = "add failed"
            else:
                mock_result.returncode = 0
                mock_result.stdout = ""
                mock_result.stderr = ""
            return mock_result

        mock_run.side_effect = run_side_effect
        ok, msg = git_init_snapshot_repo(repo_dir)
        assert ok is False
        assert "git add failed" in msg

    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=False)
    @patch("cja_auto_sdr.diff.git.git_get_user_info", return_value=("User", "user@e.com"))
    @patch("cja_auto_sdr.diff.git.subprocess.run")
    def test_git_commit_in_init_fails(self, mock_run, mock_user_info, mock_is_git, tmp_path):
        repo_dir = tmp_path / "repo_commit_fail"

        def run_side_effect(cmd, **kwargs):
            mock_result = MagicMock()
            if "init" in cmd:
                mock_result.returncode = 0
            elif "user.name" in cmd:
                mock_result.returncode = 0
            elif "user.email" in cmd:
                mock_result.returncode = 0
            elif cmd[1] == "add":
                mock_result.returncode = 0
            elif cmd[1] == "commit":
                mock_result.returncode = 1
                mock_result.stderr = "initial commit failed"
            else:
                mock_result.returncode = 0
                mock_result.stdout = ""
                mock_result.stderr = ""
            return mock_result

        mock_run.side_effect = run_side_effect
        ok, msg = git_init_snapshot_repo(repo_dir)
        assert ok is False
        assert "git commit failed" in msg

    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=False)
    @patch("cja_auto_sdr.diff.git.subprocess.run")
    def test_generic_exception_in_init(self, mock_run, mock_is_git, tmp_path):
        mock_run.side_effect = OSError("disk full")
        ok, msg = git_init_snapshot_repo(tmp_path / "repo_explode")
        assert ok is False
        assert "Initialization failed" in msg


class TestIgnoreFieldsInComponentComparison:
    """Line 305 equivalent for _find_changed_fields (component-level ignore_fields)."""

    def test_ignore_fields_skips_in_component_comparison(self):
        comp = DataViewComparator(ignore_fields=["description"])
        source = _make_snapshot(
            metrics=[{"id": "m1", "name": "M1", "description": "old desc"}],
        )
        target = _make_snapshot(
            metrics=[{"id": "m1", "name": "M1", "description": "new desc"}],
        )
        result = comp.compare(source, target)
        # Description change is ignored, so metric should be UNCHANGED
        m1_diff = result.metric_diffs[0]
        assert m1_diff.change_type == ChangeType.UNCHANGED


class TestSegmentInventoryType:
    """Line 296-297: segment inventory_type branch in _find_inventory_changed_fields."""

    def test_segment_inventory_type(self):
        comp = DataViewComparator()
        source = {"name": "SegA", "description": "old", "definition_summary": "old summary"}
        target = {"name": "SegA", "description": "new", "definition_summary": "new summary"}

        changed = comp._find_inventory_changed_fields(source, target, "segment")
        assert "description" in changed
        assert "definition_summary" in changed


class TestBuildSummaryWithCalcMetrics:
    """Lines 447-453: _build_summary with calc_metrics_diffs populated."""

    def test_build_summary_includes_calc_metrics(self):
        source = _make_snapshot(
            calculated_metrics_inventory=[{"metric_id": "cm1"}, {"metric_id": "cm2"}, {"metric_id": "cm3"}],
        )
        target = _make_snapshot(
            calculated_metrics_inventory=[{"metric_id": "cm1"}, {"metric_id": "cm4"}],
        )

        cm_diffs = [
            InventoryItemDiff(
                id="cm1",
                name="CM1",
                change_type=ChangeType.UNCHANGED,
                inventory_type="calculated_metric",
            ),
            InventoryItemDiff(id="cm2", name="CM2", change_type=ChangeType.REMOVED, inventory_type="calculated_metric"),
            InventoryItemDiff(id="cm3", name="CM3", change_type=ChangeType.REMOVED, inventory_type="calculated_metric"),
            InventoryItemDiff(id="cm4", name="CM4", change_type=ChangeType.ADDED, inventory_type="calculated_metric"),
        ]

        comp = DataViewComparator()
        summary = comp._build_summary(source, target, [], [], calc_metrics_diffs=cm_diffs)

        assert summary.source_calc_metrics_count == 3
        assert summary.target_calc_metrics_count == 2
        assert summary.calc_metrics_added == 1
        assert summary.calc_metrics_removed == 2
        assert summary.calc_metrics_unchanged == 1


class TestDiffSummaryTotalProperties:
    """Additional coverage for total_added, total_removed, total_modified, total_summary."""

    def test_total_summary_with_inventory_changes(self):
        summary = DiffSummary(
            metrics_added=1,
            dimensions_removed=1,
            calc_metrics_modified=1,
            segments_added=1,
        )
        assert summary.total_added == 2
        assert summary.total_removed == 1
        assert summary.total_modified == 1
        assert "2 added" in summary.total_summary
        assert "1 removed" in summary.total_summary
        assert "1 modified" in summary.total_summary

    def test_has_inventory_changes_true(self):
        summary = DiffSummary(segments_modified=1)
        assert summary.has_inventory_changes is True

    def test_has_inventory_changes_false(self):
        summary = DiffSummary()
        assert summary.has_inventory_changes is False


class TestDataViewSnapshotVersionUpgrade:
    """Snapshot auto-upgrades version to 2.0 when inventory is present."""

    def test_version_upgraded_with_inventory(self):
        snap = _make_snapshot(calculated_metrics_inventory=[])
        assert snap.snapshot_version == "2.0"

    def test_version_stays_1_without_inventory(self):
        snap = _make_snapshot()
        assert snap.snapshot_version == "1.0"


class TestDiffResultHasInventoryDiffs:
    """Line 300-302: has_inventory_diffs property."""

    def test_has_inventory_diffs_true(self):
        result = DiffResult(
            summary=DiffSummary(),
            metadata_diff=MagicMock(),
            metric_diffs=[],
            dimension_diffs=[],
            calc_metrics_diffs=[InventoryItemDiff(id="x", name="X", change_type=ChangeType.ADDED, inventory_type="cm")],
        )
        assert result.has_inventory_diffs is True

    def test_has_inventory_diffs_false(self):
        result = DiffResult(
            summary=DiffSummary(),
            metadata_diff=MagicMock(),
            metric_diffs=[],
            dimension_diffs=[],
        )
        assert result.has_inventory_diffs is False


# ---------------------------------------------------------------------------
# comparator.py — compare_fields kwarg + pd.isna branch (lines 122, 376)
# ---------------------------------------------------------------------------


class TestComparatorMiscBranches:
    """Cover specific uncovered branches in DataViewComparator."""

    def test_compare_fields_kwarg(self):
        """Line 122: compare_fields provided directly bypasses defaults."""
        from cja_auto_sdr.diff.comparator import DataViewComparator

        comp = DataViewComparator(compare_fields=["name", "id"])
        assert comp.compare_fields == ["name", "id"]

    def test_normalize_value_isna_true(self):
        """Line 376: pd.isna(value) returns True → returns ''."""
        import numpy as np

        from cja_auto_sdr.diff.comparator import DataViewComparator

        comp = DataViewComparator()
        assert comp._normalize_value(np.nan) == ""
        assert comp._normalize_value(float("nan")) == ""


# ---------------------------------------------------------------------------
# git.py — dimensions_added, push success, email fallback (lines 175, 267, 297)
# ---------------------------------------------------------------------------


class TestGitMiscBranches:
    """Cover specific uncovered branches in diff/git.py."""

    def test_commit_message_dimensions_added(self):
        """Line 175: dimensions_added > 0 appears in commit message."""
        from cja_auto_sdr.diff.git import generate_git_commit_message

        diff_result = MagicMock()
        diff_result.summary = DiffSummary(metrics_added=1, dimensions_added=3)
        msg = generate_git_commit_message(
            data_view_id="dv1",
            data_view_name="TestDV",
            metrics_count=5,
            dimensions_count=10,
            diff_result=diff_result,
        )
        assert "3 dimensions added" in msg

    def test_init_snapshot_repo_email_fallback(self, tmp_path):
        """Line 297: user_email empty → falls back to 'cja-auto-sdr@local'."""
        from cja_auto_sdr.diff.git import git_init_snapshot_repo

        with (
            patch("cja_auto_sdr.diff.git.git_get_user_info", return_value=("User", "")),
            patch("cja_auto_sdr.diff.git.is_git_repository", return_value=False),
            patch("subprocess.run") as mock_run,
        ):
            mock_run.return_value = MagicMock(returncode=0, stdout="", stderr="")
            git_init_snapshot_repo(tmp_path)
            # Find the call that sets user.email
            found = False
            for call in mock_run.call_args_list:
                args = call[0][0]
                if len(args) >= 4 and args[2] == "user.email":
                    assert args[3] == "cja-auto-sdr@local"
                    found = True
                    break
            assert found, "No user.email config call found"


# ==================== Truthiness regression tests (v3.5.11) ====================


class TestInventorySummaryEmptyVsNone:
    """Regression: get_inventory_summary() must distinguish [] from None.

    Before the fix, both returned count=0 with no way to tell whether
    inventory was requested-but-empty vs not-requested-at-all.
    """

    def test_empty_list_reports_present_true(self):
        snap = _make_snapshot(calculated_metrics_inventory=[], segments_inventory=[])
        summary = snap.get_inventory_summary()
        assert summary["calculated_metrics"]["present"] is True
        assert summary["calculated_metrics"]["count"] == 0
        assert summary["segments"]["present"] is True
        assert summary["segments"]["count"] == 0

    def test_none_reports_present_false(self):
        snap = _make_snapshot()  # inventory fields default to None
        summary = snap.get_inventory_summary()
        assert summary["calculated_metrics"]["present"] is False
        assert summary["calculated_metrics"]["count"] == 0
        assert summary["segments"]["present"] is False
        assert summary["segments"]["count"] == 0

    def test_mixed_one_empty_one_none(self):
        snap = _make_snapshot(calculated_metrics_inventory=[], segments_inventory=None)
        summary = snap.get_inventory_summary()
        assert summary["calculated_metrics"]["present"] is True
        assert summary["segments"]["present"] is False


class TestGitSnapshotEmptyInventory:
    """Regression: save_git_friendly_snapshot() must write files for [].

    Before the fix, empty inventory lists were falsy so no
    calculated-metrics.json / segments.json files were created, and
    metadata omitted the inventory counts section.
    """

    def test_empty_inventory_creates_files(self, tmp_path):
        snap = _make_snapshot(calculated_metrics_inventory=[], segments_inventory=[])
        saved = save_git_friendly_snapshot(snap, tmp_path)

        assert "calculated_metrics" in saved
        assert "segments" in saved
        assert saved["calculated_metrics"].exists()
        assert saved["segments"].exists()

        with open(saved["calculated_metrics"]) as f:
            assert json.load(f) == []
        with open(saved["segments"]) as f:
            assert json.load(f) == []

    def test_empty_inventory_metadata_has_counts(self, tmp_path):
        snap = _make_snapshot(calculated_metrics_inventory=[], segments_inventory=[])
        saved = save_git_friendly_snapshot(snap, tmp_path)

        with open(saved["metadata"]) as f:
            metadata = json.load(f)

        assert "inventory" in metadata
        assert metadata["inventory"]["calculated_metrics_count"] == 0
        assert metadata["inventory"]["segments_count"] == 0

    def test_none_inventory_omits_files_and_metadata(self, tmp_path):
        snap = _make_snapshot()  # no inventory
        saved = save_git_friendly_snapshot(snap, tmp_path)

        assert "calculated_metrics" not in saved
        assert "segments" not in saved

        with open(saved["metadata"]) as f:
            metadata = json.load(f)
        assert "inventory" not in metadata


class TestComparatorEmptyInventory:
    """Regression: comparator must handle [] inventory without skipping.

    Before the fix, `or []` coalesced both None and [] identically,
    which happened to work but masked the semantic difference.  The
    explicit `is not None` checks ensure the comparator only runs
    inventory comparison when the caller opted in.
    """

    def test_empty_inventory_produces_zero_diffs(self):
        source = _make_snapshot(calculated_metrics_inventory=[], segments_inventory=[])
        target = _make_snapshot(calculated_metrics_inventory=[], segments_inventory=[])
        comp = DataViewComparator(
            dimensions_only=False,
            include_calc_metrics=True,
            include_segments=True,
        )
        result = comp.compare(source, target)

        assert result.calc_metrics_diffs is not None
        assert len(result.calc_metrics_diffs) == 0
        assert result.segments_diffs is not None
        assert len(result.segments_diffs) == 0

    def test_empty_inventory_summary_counts_are_zero(self):
        source = _make_snapshot(calculated_metrics_inventory=[], segments_inventory=[])
        target = _make_snapshot(calculated_metrics_inventory=[], segments_inventory=[])
        comp = DataViewComparator(
            dimensions_only=False,
            include_calc_metrics=True,
            include_segments=True,
        )
        result = comp.compare(source, target)

        assert result.summary.source_calc_metrics_count == 0
        assert result.summary.target_calc_metrics_count == 0
        assert result.summary.source_segments_count == 0
        assert result.summary.target_segments_count == 0

    def test_none_inventory_with_flags_off_skips_comparison(self):
        source = _make_snapshot()  # no inventory
        target = _make_snapshot()
        comp = DataViewComparator(
            dimensions_only=False,
            include_calc_metrics=False,
            include_segments=False,
        )
        result = comp.compare(source, target)

        # Flags off — diffs should be None (comparison not requested)
        assert result.calc_metrics_diffs is None
        assert result.segments_diffs is None

    def test_none_inventory_with_flags_on_coalesces_to_empty(self):
        source = _make_snapshot()  # inventory is None
        target = _make_snapshot()
        comp = DataViewComparator(
            dimensions_only=False,
            include_calc_metrics=True,
            include_segments=True,
        )
        result = comp.compare(source, target)

        # Flags on but inventory is None — coalesces to [] for comparison
        assert result.calc_metrics_diffs is not None
        assert len(result.calc_metrics_diffs) == 0
        assert result.segments_diffs is not None
        assert len(result.segments_diffs) == 0
