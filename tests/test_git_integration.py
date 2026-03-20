"""Tests for Git integration functionality."""

import json
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

from cja_auto_sdr.generator import (
    DataViewSnapshot,
    generate_git_commit_message,
    git_commit_snapshot,
    git_get_user_info,
    git_init_snapshot_repo,
    is_git_repository,
    save_git_friendly_snapshot,
)


class TestIsGitRepository:
    """Tests for is_git_repository function."""

    def test_returns_true_for_git_repo(self, tmp_path):
        """Test that function returns True for a valid Git repository."""
        # Initialize a git repo
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        assert is_git_repository(tmp_path) is True

    def test_returns_false_for_non_git_directory(self, tmp_path):
        """Test that function returns False for non-Git directory."""
        assert is_git_repository(tmp_path) is False

    def test_handles_nonexistent_directory(self, tmp_path):
        """Test that function handles non-existent directory gracefully."""
        nonexistent = tmp_path / "nonexistent"
        assert is_git_repository(nonexistent) is False

    @patch("subprocess.run")
    def test_handles_timeout(self, mock_run):
        """Test that function handles timeout gracefully."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="git", timeout=10)
        assert is_git_repository(Path(".")) is False

    @patch("subprocess.run")
    def test_handles_git_not_found(self, mock_run):
        """Test that function handles missing Git gracefully."""
        mock_run.side_effect = FileNotFoundError()
        assert is_git_repository(Path(".")) is False

    @patch("subprocess.run")
    def test_handles_decode_error(self, mock_run):
        """Test that subprocess decode errors are treated as non-repo signals."""
        mock_run.side_effect = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
        assert is_git_repository(Path(".")) is False


class TestGitGetUserInfo:
    """Tests for git_get_user_info function."""

    @patch("cja_auto_sdr.diff.git.subprocess.run")
    def test_handles_decode_errors(self, mock_run):
        """Decode failures should keep default identity and never raise."""
        mock_run.side_effect = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")
        name, email = git_get_user_info()
        assert name == "CJA SDR Generator"
        assert email == ""


class TestSaveGitFriendlySnapshot:
    """Tests for save_git_friendly_snapshot function."""

    def test_creates_directory_structure(self, tmp_path):
        """Test that function creates correct directory structure."""
        snapshot = DataViewSnapshot(
            data_view_id="dv_12345",
            data_view_name="Test Data View",
            metrics=[{"id": "cm1", "name": "Metric 1"}],
            dimensions=[{"id": "dim1", "name": "Dimension 1"}],
        )

        saved_files = save_git_friendly_snapshot(snapshot, tmp_path)

        assert "metrics" in saved_files
        assert "dimensions" in saved_files
        assert "metadata" in saved_files
        assert saved_files["metrics"].exists()
        assert saved_files["dimensions"].exists()
        assert saved_files["metadata"].exists()

    def test_sorts_metrics_by_id(self, tmp_path):
        """Test that metrics are sorted by ID for consistent diffs."""
        snapshot = DataViewSnapshot(
            data_view_id="dv_12345",
            data_view_name="Test",
            metrics=[
                {"id": "cm_z", "name": "Z Metric"},
                {"id": "cm_a", "name": "A Metric"},
                {"id": "cm_m", "name": "M Metric"},
            ],
            dimensions=[],
        )

        saved_files = save_git_friendly_snapshot(snapshot, tmp_path)

        with open(saved_files["metrics"]) as f:
            metrics = json.load(f)

        ids = [m["id"] for m in metrics]
        assert ids == ["cm_a", "cm_m", "cm_z"]

    def test_sorts_dimensions_by_id(self, tmp_path):
        """Test that dimensions are sorted by ID for consistent diffs."""
        snapshot = DataViewSnapshot(
            data_view_id="dv_12345",
            data_view_name="Test",
            metrics=[],
            dimensions=[
                {"id": "dim_z", "name": "Z Dimension"},
                {"id": "dim_a", "name": "A Dimension"},
            ],
        )

        saved_files = save_git_friendly_snapshot(snapshot, tmp_path)

        with open(saved_files["dimensions"]) as f:
            dimensions = json.load(f)

        ids = [d["id"] for d in dimensions]
        assert ids == ["dim_a", "dim_z"]

    def test_metadata_includes_summary(self, tmp_path):
        """Test that metadata file includes component counts."""
        snapshot = DataViewSnapshot(
            data_view_id="dv_12345",
            data_view_name="Test Data View",
            owner="test_owner",
            description="Test description",
            metrics=[{"id": "cm1"}, {"id": "cm2"}],
            dimensions=[{"id": "dim1"}],
        )

        saved_files = save_git_friendly_snapshot(snapshot, tmp_path)

        with open(saved_files["metadata"]) as f:
            metadata = json.load(f)

        assert metadata["data_view_id"] == "dv_12345"
        assert metadata["data_view_name"] == "Test Data View"
        assert metadata["summary"]["metrics_count"] == 2
        assert metadata["summary"]["dimensions_count"] == 1
        assert metadata["summary"]["total_components"] == 3

    def test_includes_quality_issues_in_metadata(self, tmp_path):
        """Test that quality issues are included in metadata."""
        snapshot = DataViewSnapshot(data_view_id="dv_12345", data_view_name="Test", metrics=[], dimensions=[])

        quality_issues = [
            {"Severity": "HIGH", "Issue": "Test issue 1"},
            {"Severity": "HIGH", "Issue": "Test issue 2"},
            {"Severity": "LOW", "Issue": "Test issue 3"},
        ]

        saved_files = save_git_friendly_snapshot(snapshot, tmp_path, quality_issues=quality_issues)

        with open(saved_files["metadata"]) as f:
            metadata = json.load(f)

        assert "quality" in metadata
        assert metadata["quality"]["total_issues"] == 3
        assert metadata["quality"]["by_severity"]["HIGH"] == 2
        assert metadata["quality"]["by_severity"]["LOW"] == 1

    def test_sanitizes_data_view_name_for_directory(self, tmp_path):
        """Test that special characters in name are sanitized."""
        snapshot = DataViewSnapshot(
            data_view_id="dv_12345",
            data_view_name="Test / Data View: With <Special> Chars!",
            metrics=[],
            dimensions=[],
        )

        saved_files = save_git_friendly_snapshot(snapshot, tmp_path)

        # Check that directory was created with sanitized name
        parent_dir = saved_files["metadata"].parent
        assert "/" not in parent_dir.name
        assert "<" not in parent_dir.name
        assert ">" not in parent_dir.name

    def test_saves_calculated_metrics_inventory(self, tmp_path):
        """Test that calculated metrics inventory is saved as separate file."""
        snapshot = DataViewSnapshot(
            data_view_id="dv_12345",
            data_view_name="Test",
            metrics=[{"id": "cm1"}],
            dimensions=[{"id": "dim1"}],
            calculated_metrics_inventory=[
                {"id": "calc_z", "name": "Z Calculated"},
                {"id": "calc_a", "name": "A Calculated"},
            ],
        )

        saved_files = save_git_friendly_snapshot(snapshot, tmp_path)

        assert "calculated_metrics" in saved_files
        assert saved_files["calculated_metrics"].exists()
        assert saved_files["calculated_metrics"].name == "calculated-metrics.json"

        with open(saved_files["calculated_metrics"]) as f:
            calc_metrics = json.load(f)

        # Should be sorted by ID
        ids = [m["id"] for m in calc_metrics]
        assert ids == ["calc_a", "calc_z"]

    def test_saves_segments_inventory(self, tmp_path):
        """Test that segments inventory is saved as separate file."""
        snapshot = DataViewSnapshot(
            data_view_id="dv_12345",
            data_view_name="Test",
            metrics=[],
            dimensions=[],
            segments_inventory=[
                {"id": "seg_z", "name": "Z Segment"},
                {"id": "seg_a", "name": "A Segment"},
                {"id": "seg_m", "name": "M Segment"},
            ],
        )

        saved_files = save_git_friendly_snapshot(snapshot, tmp_path)

        assert "segments" in saved_files
        assert saved_files["segments"].exists()
        assert saved_files["segments"].name == "segments.json"

        with open(saved_files["segments"]) as f:
            segments = json.load(f)

        # Should be sorted by ID
        ids = [s["id"] for s in segments]
        assert ids == ["seg_a", "seg_m", "seg_z"]

    def test_no_inventory_files_when_not_present(self, tmp_path):
        """Test that inventory files are not created when data not present."""
        snapshot = DataViewSnapshot(
            data_view_id="dv_12345",
            data_view_name="Test",
            metrics=[{"id": "cm1"}],
            dimensions=[{"id": "dim1"}],
        )

        saved_files = save_git_friendly_snapshot(snapshot, tmp_path)

        assert "calculated_metrics" not in saved_files
        assert "segments" not in saved_files

        # Verify files don't exist
        parent_dir = saved_files["metadata"].parent
        assert not (parent_dir / "calculated-metrics.json").exists()
        assert not (parent_dir / "segments.json").exists()

    def test_metadata_includes_inventory_summary(self, tmp_path):
        """Test that metadata includes inventory counts when present."""
        snapshot = DataViewSnapshot(
            data_view_id="dv_12345",
            data_view_name="Test",
            metrics=[{"id": "cm1"}],
            dimensions=[],
            calculated_metrics_inventory=[{"id": "calc1"}, {"id": "calc2"}],
            segments_inventory=[{"id": "seg1"}],
        )

        saved_files = save_git_friendly_snapshot(snapshot, tmp_path)

        with open(saved_files["metadata"]) as f:
            metadata = json.load(f)

        assert "inventory" in metadata
        assert metadata["inventory"]["calculated_metrics_count"] == 2
        assert metadata["inventory"]["segments_count"] == 1

    def test_snapshot_version_upgraded_with_inventory(self, tmp_path):
        """Test that snapshot version is 2.0 when inventory is included."""
        snapshot = DataViewSnapshot(
            data_view_id="dv_12345",
            data_view_name="Test",
            metrics=[],
            dimensions=[],
            calculated_metrics_inventory=[{"id": "calc1"}],
        )

        saved_files = save_git_friendly_snapshot(snapshot, tmp_path)

        with open(saved_files["metadata"]) as f:
            metadata = json.load(f)

        assert metadata["snapshot_version"] == "2.0"


class TestGenerateGitCommitMessage:
    """Tests for generate_git_commit_message function."""

    def test_basic_message_structure(self):
        """Test that commit message has correct structure."""
        message = generate_git_commit_message(
            data_view_id="dv_12345",
            data_view_name="Test Data View",
            metrics_count=10,
            dimensions_count=5,
        )

        assert "[dv_12345]" in message
        assert "Test Data View" in message
        assert "10 metrics" in message
        assert "5 dimensions" in message

    def test_custom_message_included(self):
        """Test that custom message is included in commit."""
        message = generate_git_commit_message(
            data_view_id="dv_12345",
            data_view_name="Test",
            metrics_count=1,
            dimensions_count=1,
            custom_message="Weekly sync",
        )

        assert "Weekly sync" in message
        assert "[dv_12345]" in message

    def test_quality_issues_in_message(self):
        """Test that quality issues are summarized in commit message."""
        quality_issues = [
            {"Severity": "CRITICAL", "Issue": "Issue 1"},
            {"Severity": "HIGH", "Issue": "Issue 2"},
            {"Severity": "HIGH", "Issue": "Issue 3"},
        ]

        message = generate_git_commit_message(
            data_view_id="dv_12345",
            data_view_name="Test",
            metrics_count=1,
            dimensions_count=1,
            quality_issues=quality_issues,
        )

        assert "Quality:" in message
        assert "CRITICAL: 1" in message
        assert "HIGH: 2" in message

    def test_diff_result_changes_in_message(self):
        """Test that diff result changes are included in message."""
        # Create a mock DiffResult with changes
        mock_summary = MagicMock()
        mock_summary.has_changes = True
        mock_summary.metrics_added = 2
        mock_summary.metrics_removed = 1
        mock_summary.metrics_modified = 0
        mock_summary.dimensions_added = 0
        mock_summary.dimensions_removed = 0
        mock_summary.dimensions_modified = 3

        mock_diff = MagicMock()
        mock_diff.summary = mock_summary

        message = generate_git_commit_message(
            data_view_id="dv_12345",
            data_view_name="Test",
            metrics_count=10,
            dimensions_count=5,
            diff_result=mock_diff,
        )

        assert "Changes:" in message
        assert "2 metrics added" in message
        assert "1 metrics removed" in message
        assert "3 dimensions modified" in message


class TestGitInitSnapshotRepo:
    """Tests for git_init_snapshot_repo function."""

    def test_initializes_new_repo(self, tmp_path):
        """Test that function initializes a new Git repository."""
        repo_dir = tmp_path / "new_repo"

        success, _message = git_init_snapshot_repo(repo_dir)

        assert success is True
        assert is_git_repository(repo_dir)
        assert (repo_dir / ".gitignore").exists()
        assert (repo_dir / "README.md").exists()

    def test_handles_existing_repo(self, tmp_path):
        """Test that function handles existing Git repository."""
        # Initialize repo first
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)

        success, message = git_init_snapshot_repo(tmp_path)

        assert success is True
        assert "Already a Git repository" in message

    def test_creates_gitignore(self, tmp_path):
        """Test that .gitignore is created with appropriate content."""
        repo_dir = tmp_path / "new_repo"
        git_init_snapshot_repo(repo_dir)

        gitignore = repo_dir / ".gitignore"
        content = gitignore.read_text()

        assert "*.log" in content
        assert ".DS_Store" in content

    def test_creates_readme(self, tmp_path):
        """Test that README.md is created with documentation."""
        repo_dir = tmp_path / "new_repo"
        git_init_snapshot_repo(repo_dir)

        readme = repo_dir / "README.md"
        content = readme.read_text()

        assert "CJA SDR Snapshots" in content
        assert "metrics.json" in content
        assert "dimensions.json" in content

    @patch("cja_auto_sdr.diff.git.git_get_user_info", return_value=("Test User", "test@example.com"))
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=False)
    @patch("cja_auto_sdr.diff.git.subprocess.run")
    def test_init_fails_when_git_add_fails(self, mock_run, _mock_is_repo, _mock_user_info, tmp_path):
        """Test that git add failures are surfaced during init."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stderr="", stdout=""),  # git init
            MagicMock(returncode=0, stderr="", stdout=""),  # git config user.name
            MagicMock(returncode=0, stderr="", stdout=""),  # git config user.email
            MagicMock(returncode=1, stderr="add failed", stdout=""),  # git add
        ]

        success, message = git_init_snapshot_repo(tmp_path)
        assert success is False
        assert "git add failed" in message

    @patch("cja_auto_sdr.diff.git.git_get_user_info", return_value=("Test User", "test@example.com"))
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=False)
    @patch("cja_auto_sdr.diff.git.subprocess.run")
    def test_init_fails_when_git_commit_fails(self, mock_run, _mock_is_repo, _mock_user_info, tmp_path):
        """Test that git commit failures are surfaced during init."""
        mock_run.side_effect = [
            MagicMock(returncode=0, stderr="", stdout=""),  # git init
            MagicMock(returncode=0, stderr="", stdout=""),  # git config user.name
            MagicMock(returncode=0, stderr="", stdout=""),  # git config user.email
            MagicMock(returncode=0, stderr="", stdout=""),  # git add
            MagicMock(returncode=1, stderr="commit failed", stdout=""),  # git commit
        ]

        success, message = git_init_snapshot_repo(tmp_path)
        assert success is False
        assert "git commit failed" in message

    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=False)
    @patch("cja_auto_sdr.diff.git.subprocess.run")
    def test_init_decode_error_returns_failure_tuple(self, mock_run, _mock_is_repo, tmp_path):
        """Unicode decode failures should preserve non-throwing tuple contract."""
        mock_run.side_effect = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

        success, message = git_init_snapshot_repo(tmp_path)

        assert success is False
        assert "Initialization failed:" in message


class TestGitCommitSnapshot:
    """Tests for git_commit_snapshot function."""

    def test_commits_changes(self, tmp_path):
        """Test that function commits changes to Git."""
        # Initialize repo
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(tmp_path), capture_output=True)

        # Create a snapshot-style directory to commit
        dv_dir = tmp_path / "Test_DV_dv_12345"
        dv_dir.mkdir()
        test_file = dv_dir / "metadata.json"
        test_file.write_text('{"test": "data"}')

        success, result = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_12345",
            data_view_name="Test",
            metrics_count=1,
            dimensions_count=1,
        )

        assert success is True
        assert len(result) == 8  # Short SHA

        # Verify commit exists
        log_result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
        )
        assert "dv_12345" in log_result.stdout

    def test_returns_no_changes_when_unchanged(self, tmp_path):
        """Test that function returns no_changes when nothing changed."""
        # Initialize repo with initial commit
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(tmp_path), capture_output=True)
        dv_dir = tmp_path / "Test_DV_dv_12345"
        dv_dir.mkdir()
        test_file = dv_dir / "metadata.json"
        test_file.write_text('{"test": "data"}')
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "commit", "-m", "Initial"], cwd=str(tmp_path), capture_output=True)

        # Try to commit again without changes
        success, result = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_12345",
            data_view_name="Test",
            metrics_count=1,
            dimensions_count=1,
        )

        assert success is True
        assert result == "no_changes"

    def test_fails_for_non_git_directory(self, tmp_path):
        """Test that function fails for non-Git directory."""
        success, result = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_12345",
            data_view_name="Test",
            metrics_count=1,
            dimensions_count=1,
        )

        assert success is False
        assert "Not a Git repository" in result

    def test_includes_custom_message(self, tmp_path):
        """Test that custom message is included in commit."""
        # Initialize repo
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(tmp_path), capture_output=True)

        dv_dir = tmp_path / "Test_DV_dv_12345"
        dv_dir.mkdir()
        test_file = dv_dir / "metadata.json"
        test_file.write_text('{"test": "data"}')

        git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_12345",
            data_view_name="Test",
            metrics_count=1,
            dimensions_count=1,
            custom_message="Custom commit message",
        )

        log_result = subprocess.run(
            ["git", "log", "--oneline", "-1"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
        )
        assert "Custom commit message" in log_result.stdout

    def test_only_stages_matching_data_view_snapshot_paths(self, tmp_path):
        """Test that committing one data view does not stage unrelated changes."""
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(tmp_path), capture_output=True)

        target_dir = tmp_path / "Target_dv_12345"
        other_dir = tmp_path / "Other_dv_99999"
        target_dir.mkdir()
        other_dir.mkdir()
        (target_dir / "metadata.json").write_text('{"v": 1}')
        (other_dir / "metadata.json").write_text('{"v": 1}')
        unrelated = tmp_path / "notes.txt"
        unrelated.write_text("base")
        subprocess.run(["git", "add", "."], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "commit", "-m", "baseline"], cwd=str(tmp_path), capture_output=True)

        (target_dir / "metadata.json").write_text('{"v": 2}')
        (other_dir / "metadata.json").write_text('{"v": 2}')
        unrelated.write_text("changed")

        success, result = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_12345",
            data_view_name="Target",
            metrics_count=1,
            dimensions_count=1,
        )

        assert success is True
        assert result != "no_changes"

        changed_files = subprocess.run(
            ["git", "show", "--name-only", "--pretty=format:", "HEAD"],
            cwd=str(tmp_path),
            capture_output=True,
            text=True,
        ).stdout
        assert "Target_dv_12345/metadata.json" in changed_files
        assert "Other_dv_99999/metadata.json" not in changed_files
        assert "notes.txt" not in changed_files

    @patch("cja_auto_sdr.diff.git._snapshot_pathspecs_for_data_view", return_value=["Target_dv_12345"])
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.diff.git.subprocess.run")
    def test_decode_error_returns_git_error_tuple(self, mock_run, _mock_is_repo, _mock_pathspecs, tmp_path):
        """Unicode decode failures must return (False, message), not raise."""
        mock_run.side_effect = UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte")

        success, message = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_12345",
            data_view_name="Target",
            metrics_count=1,
            dimensions_count=1,
        )

        assert success is False
        assert "Git error:" in message

    def test_push_success_logs_and_returns_sha(self, tmp_path):
        """Successful push should preserve the short SHA return contract."""
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(tmp_path), capture_output=True)

        dv_dir = tmp_path / "Push_Test_dv_push"
        dv_dir.mkdir()
        (dv_dir / "metadata.json").write_text('{"test": "push"}')

        original_run = subprocess.run

        def mock_run(cmd, *args, **kwargs):
            if cmd == ["git", "push"]:
                return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
            return original_run(cmd, *args, **kwargs)

        with patch("subprocess.run", side_effect=mock_run):
            success, result = git_commit_snapshot(
                snapshot_dir=tmp_path,
                data_view_id="dv_push",
                data_view_name="Push Test",
                metrics_count=1,
                dimensions_count=1,
                push=True,
            )

        assert success is True
        assert len(result) == 8


class TestCLIGitArguments:
    """Tests for Git-related CLI arguments."""

    def test_git_init_argument_exists(self):
        """Test that --git-init argument is recognized."""
        import sys

        from cja_auto_sdr.generator import parse_arguments

        # Temporarily modify sys.argv
        original_argv = sys.argv
        try:
            sys.argv = ["cja_sdr_generator", "--git-init"]
            args = parse_arguments()
            assert hasattr(args, "git_init")
            assert args.git_init is True
        finally:
            sys.argv = original_argv

    def test_git_commit_argument_exists(self):
        """Test that --git-commit argument is recognized."""
        import sys

        from cja_auto_sdr.generator import parse_arguments

        original_argv = sys.argv
        try:
            sys.argv = ["cja_sdr_generator", "dv_test", "--git-commit"]
            args = parse_arguments()
            assert hasattr(args, "git_commit")
            assert args.git_commit is True
        finally:
            sys.argv = original_argv

    def test_git_push_argument_exists(self):
        """Test that --git-push argument is recognized."""
        import sys

        from cja_auto_sdr.generator import parse_arguments

        original_argv = sys.argv
        try:
            sys.argv = ["cja_sdr_generator", "dv_test", "--git-commit", "--git-push"]
            args = parse_arguments()
            assert hasattr(args, "git_push")
            assert args.git_push is True
        finally:
            sys.argv = original_argv

    def test_git_dir_default_value(self):
        """Test that --git-dir has correct default value."""
        import sys

        from cja_auto_sdr.generator import parse_arguments

        original_argv = sys.argv
        try:
            sys.argv = ["cja_sdr_generator", "dv_test"]
            args = parse_arguments()
            assert args.git_dir == "./sdr-snapshots"
        finally:
            sys.argv = original_argv

    def test_git_message_argument(self):
        """Test that --git-message argument is recognized."""
        import sys

        from cja_auto_sdr.generator import parse_arguments

        original_argv = sys.argv
        try:
            sys.argv = ["cja_sdr_generator", "dv_test", "--git-commit", "--git-message", "Test message"]
            args = parse_arguments()
            assert args.git_message == "Test message"
        finally:
            sys.argv = original_argv
