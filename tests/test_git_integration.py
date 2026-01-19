"""Tests for Git integration functionality."""

import json
import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cja_sdr_generator import (
    DataViewSnapshot,
    generate_git_commit_message,
    git_commit_snapshot,
    git_init_snapshot_repo,
    is_git_repository,
    save_git_friendly_snapshot,
)


class TestIsGitRepository:
    """Tests for is_git_repository function."""

    def test_returns_true_for_git_repo(self, tmp_path):
        """Test that function returns True for a valid Git repository."""
        # Initialize a git repo
        subprocess.run(['git', 'init'], cwd=str(tmp_path), capture_output=True)
        assert is_git_repository(tmp_path) is True

    def test_returns_false_for_non_git_directory(self, tmp_path):
        """Test that function returns False for non-Git directory."""
        assert is_git_repository(tmp_path) is False

    def test_handles_nonexistent_directory(self, tmp_path):
        """Test that function handles non-existent directory gracefully."""
        nonexistent = tmp_path / "nonexistent"
        assert is_git_repository(nonexistent) is False

    @patch('subprocess.run')
    def test_handles_timeout(self, mock_run):
        """Test that function handles timeout gracefully."""
        mock_run.side_effect = subprocess.TimeoutExpired(cmd='git', timeout=10)
        assert is_git_repository(Path('.')) is False

    @patch('subprocess.run')
    def test_handles_git_not_found(self, mock_run):
        """Test that function handles missing Git gracefully."""
        mock_run.side_effect = FileNotFoundError()
        assert is_git_repository(Path('.')) is False


class TestSaveGitFriendlySnapshot:
    """Tests for save_git_friendly_snapshot function."""

    def test_creates_directory_structure(self, tmp_path):
        """Test that function creates correct directory structure."""
        snapshot = DataViewSnapshot(
            data_view_id='dv_12345',
            data_view_name='Test Data View',
            metrics=[{'id': 'cm1', 'name': 'Metric 1'}],
            dimensions=[{'id': 'dim1', 'name': 'Dimension 1'}]
        )

        saved_files = save_git_friendly_snapshot(snapshot, tmp_path)

        assert 'metrics' in saved_files
        assert 'dimensions' in saved_files
        assert 'metadata' in saved_files
        assert saved_files['metrics'].exists()
        assert saved_files['dimensions'].exists()
        assert saved_files['metadata'].exists()

    def test_sorts_metrics_by_id(self, tmp_path):
        """Test that metrics are sorted by ID for consistent diffs."""
        snapshot = DataViewSnapshot(
            data_view_id='dv_12345',
            data_view_name='Test',
            metrics=[
                {'id': 'cm_z', 'name': 'Z Metric'},
                {'id': 'cm_a', 'name': 'A Metric'},
                {'id': 'cm_m', 'name': 'M Metric'},
            ],
            dimensions=[]
        )

        saved_files = save_git_friendly_snapshot(snapshot, tmp_path)

        with open(saved_files['metrics']) as f:
            metrics = json.load(f)

        ids = [m['id'] for m in metrics]
        assert ids == ['cm_a', 'cm_m', 'cm_z']

    def test_sorts_dimensions_by_id(self, tmp_path):
        """Test that dimensions are sorted by ID for consistent diffs."""
        snapshot = DataViewSnapshot(
            data_view_id='dv_12345',
            data_view_name='Test',
            metrics=[],
            dimensions=[
                {'id': 'dim_z', 'name': 'Z Dimension'},
                {'id': 'dim_a', 'name': 'A Dimension'},
            ]
        )

        saved_files = save_git_friendly_snapshot(snapshot, tmp_path)

        with open(saved_files['dimensions']) as f:
            dimensions = json.load(f)

        ids = [d['id'] for d in dimensions]
        assert ids == ['dim_a', 'dim_z']

    def test_metadata_includes_summary(self, tmp_path):
        """Test that metadata file includes component counts."""
        snapshot = DataViewSnapshot(
            data_view_id='dv_12345',
            data_view_name='Test Data View',
            owner='test_owner',
            description='Test description',
            metrics=[{'id': 'cm1'}, {'id': 'cm2'}],
            dimensions=[{'id': 'dim1'}]
        )

        saved_files = save_git_friendly_snapshot(snapshot, tmp_path)

        with open(saved_files['metadata']) as f:
            metadata = json.load(f)

        assert metadata['data_view_id'] == 'dv_12345'
        assert metadata['data_view_name'] == 'Test Data View'
        assert metadata['summary']['metrics_count'] == 2
        assert metadata['summary']['dimensions_count'] == 1
        assert metadata['summary']['total_components'] == 3

    def test_includes_quality_issues_in_metadata(self, tmp_path):
        """Test that quality issues are included in metadata."""
        snapshot = DataViewSnapshot(
            data_view_id='dv_12345',
            data_view_name='Test',
            metrics=[],
            dimensions=[]
        )

        quality_issues = [
            {'Severity': 'HIGH', 'Issue': 'Test issue 1'},
            {'Severity': 'HIGH', 'Issue': 'Test issue 2'},
            {'Severity': 'LOW', 'Issue': 'Test issue 3'},
        ]

        saved_files = save_git_friendly_snapshot(
            snapshot, tmp_path, quality_issues=quality_issues
        )

        with open(saved_files['metadata']) as f:
            metadata = json.load(f)

        assert 'quality' in metadata
        assert metadata['quality']['total_issues'] == 3
        assert metadata['quality']['by_severity']['HIGH'] == 2
        assert metadata['quality']['by_severity']['LOW'] == 1

    def test_sanitizes_data_view_name_for_directory(self, tmp_path):
        """Test that special characters in name are sanitized."""
        snapshot = DataViewSnapshot(
            data_view_id='dv_12345',
            data_view_name='Test / Data View: With <Special> Chars!',
            metrics=[],
            dimensions=[]
        )

        saved_files = save_git_friendly_snapshot(snapshot, tmp_path)

        # Check that directory was created with sanitized name
        parent_dir = saved_files['metadata'].parent
        assert '/' not in parent_dir.name
        assert '<' not in parent_dir.name
        assert '>' not in parent_dir.name


class TestGenerateGitCommitMessage:
    """Tests for generate_git_commit_message function."""

    def test_basic_message_structure(self):
        """Test that commit message has correct structure."""
        message = generate_git_commit_message(
            data_view_id='dv_12345',
            data_view_name='Test Data View',
            metrics_count=10,
            dimensions_count=5
        )

        assert '[dv_12345]' in message
        assert 'Test Data View' in message
        assert '10 metrics' in message
        assert '5 dimensions' in message

    def test_custom_message_included(self):
        """Test that custom message is included in commit."""
        message = generate_git_commit_message(
            data_view_id='dv_12345',
            data_view_name='Test',
            metrics_count=1,
            dimensions_count=1,
            custom_message='Weekly sync'
        )

        assert 'Weekly sync' in message
        assert '[dv_12345]' in message

    def test_quality_issues_in_message(self):
        """Test that quality issues are summarized in commit message."""
        quality_issues = [
            {'Severity': 'CRITICAL', 'Issue': 'Issue 1'},
            {'Severity': 'HIGH', 'Issue': 'Issue 2'},
            {'Severity': 'HIGH', 'Issue': 'Issue 3'},
        ]

        message = generate_git_commit_message(
            data_view_id='dv_12345',
            data_view_name='Test',
            metrics_count=1,
            dimensions_count=1,
            quality_issues=quality_issues
        )

        assert 'Quality:' in message
        assert 'CRITICAL: 1' in message
        assert 'HIGH: 2' in message

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
            data_view_id='dv_12345',
            data_view_name='Test',
            metrics_count=10,
            dimensions_count=5,
            diff_result=mock_diff
        )

        assert 'Changes:' in message
        assert '2 metrics added' in message
        assert '1 metrics removed' in message
        assert '3 dimensions modified' in message


class TestGitInitSnapshotRepo:
    """Tests for git_init_snapshot_repo function."""

    def test_initializes_new_repo(self, tmp_path):
        """Test that function initializes a new Git repository."""
        repo_dir = tmp_path / 'new_repo'

        success, message = git_init_snapshot_repo(repo_dir)

        assert success is True
        assert is_git_repository(repo_dir)
        assert (repo_dir / '.gitignore').exists()
        assert (repo_dir / 'README.md').exists()

    def test_handles_existing_repo(self, tmp_path):
        """Test that function handles existing Git repository."""
        # Initialize repo first
        subprocess.run(['git', 'init'], cwd=str(tmp_path), capture_output=True)

        success, message = git_init_snapshot_repo(tmp_path)

        assert success is True
        assert 'Already a Git repository' in message

    def test_creates_gitignore(self, tmp_path):
        """Test that .gitignore is created with appropriate content."""
        repo_dir = tmp_path / 'new_repo'
        git_init_snapshot_repo(repo_dir)

        gitignore = repo_dir / '.gitignore'
        content = gitignore.read_text()

        assert '*.log' in content
        assert '.DS_Store' in content

    def test_creates_readme(self, tmp_path):
        """Test that README.md is created with documentation."""
        repo_dir = tmp_path / 'new_repo'
        git_init_snapshot_repo(repo_dir)

        readme = repo_dir / 'README.md'
        content = readme.read_text()

        assert 'CJA SDR Snapshots' in content
        assert 'metrics.json' in content
        assert 'dimensions.json' in content


class TestGitCommitSnapshot:
    """Tests for git_commit_snapshot function."""

    def test_commits_changes(self, tmp_path):
        """Test that function commits changes to Git."""
        # Initialize repo
        subprocess.run(['git', 'init'], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ['git', 'config', 'user.email', 'test@test.com'],
            cwd=str(tmp_path), capture_output=True
        )
        subprocess.run(
            ['git', 'config', 'user.name', 'Test User'],
            cwd=str(tmp_path), capture_output=True
        )

        # Create a file to commit
        test_file = tmp_path / 'test.json'
        test_file.write_text('{"test": "data"}')

        success, result = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id='dv_12345',
            data_view_name='Test',
            metrics_count=1,
            dimensions_count=1
        )

        assert success is True
        assert len(result) == 8  # Short SHA

        # Verify commit exists
        log_result = subprocess.run(
            ['git', 'log', '--oneline', '-1'],
            cwd=str(tmp_path),
            capture_output=True,
            text=True
        )
        assert 'dv_12345' in log_result.stdout

    def test_returns_no_changes_when_unchanged(self, tmp_path):
        """Test that function returns no_changes when nothing changed."""
        # Initialize repo with initial commit
        subprocess.run(['git', 'init'], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ['git', 'config', 'user.email', 'test@test.com'],
            cwd=str(tmp_path), capture_output=True
        )
        subprocess.run(
            ['git', 'config', 'user.name', 'Test User'],
            cwd=str(tmp_path), capture_output=True
        )
        test_file = tmp_path / 'test.json'
        test_file.write_text('{"test": "data"}')
        subprocess.run(['git', 'add', '.'], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ['git', 'commit', '-m', 'Initial'],
            cwd=str(tmp_path), capture_output=True
        )

        # Try to commit again without changes
        success, result = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id='dv_12345',
            data_view_name='Test',
            metrics_count=1,
            dimensions_count=1
        )

        assert success is True
        assert result == 'no_changes'

    def test_fails_for_non_git_directory(self, tmp_path):
        """Test that function fails for non-Git directory."""
        success, result = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id='dv_12345',
            data_view_name='Test',
            metrics_count=1,
            dimensions_count=1
        )

        assert success is False
        assert 'Not a Git repository' in result

    def test_includes_custom_message(self, tmp_path):
        """Test that custom message is included in commit."""
        # Initialize repo
        subprocess.run(['git', 'init'], cwd=str(tmp_path), capture_output=True)
        subprocess.run(
            ['git', 'config', 'user.email', 'test@test.com'],
            cwd=str(tmp_path), capture_output=True
        )
        subprocess.run(
            ['git', 'config', 'user.name', 'Test User'],
            cwd=str(tmp_path), capture_output=True
        )

        test_file = tmp_path / 'test.json'
        test_file.write_text('{"test": "data"}')

        git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id='dv_12345',
            data_view_name='Test',
            metrics_count=1,
            dimensions_count=1,
            custom_message='Custom commit message'
        )

        log_result = subprocess.run(
            ['git', 'log', '--oneline', '-1'],
            cwd=str(tmp_path),
            capture_output=True,
            text=True
        )
        assert 'Custom commit message' in log_result.stdout


class TestCLIGitArguments:
    """Tests for Git-related CLI arguments."""

    def test_git_init_argument_exists(self):
        """Test that --git-init argument is recognized."""
        from cja_sdr_generator import parse_arguments
        import sys

        # Temporarily modify sys.argv
        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator', '--git-init']
            args = parse_arguments()
            assert hasattr(args, 'git_init')
            assert args.git_init is True
        finally:
            sys.argv = original_argv

    def test_git_commit_argument_exists(self):
        """Test that --git-commit argument is recognized."""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator', 'dv_test', '--git-commit']
            args = parse_arguments()
            assert hasattr(args, 'git_commit')
            assert args.git_commit is True
        finally:
            sys.argv = original_argv

    def test_git_push_argument_exists(self):
        """Test that --git-push argument is recognized."""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator', 'dv_test', '--git-commit', '--git-push']
            args = parse_arguments()
            assert hasattr(args, 'git_push')
            assert args.git_push is True
        finally:
            sys.argv = original_argv

    def test_git_dir_default_value(self):
        """Test that --git-dir has correct default value."""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator', 'dv_test']
            args = parse_arguments()
            assert args.git_dir == './sdr-snapshots'
        finally:
            sys.argv = original_argv

    def test_git_message_argument(self):
        """Test that --git-message argument is recognized."""
        from cja_sdr_generator import parse_arguments
        import sys

        original_argv = sys.argv
        try:
            sys.argv = ['cja_sdr_generator', 'dv_test', '--git-commit', '--git-message', 'Test message']
            args = parse_arguments()
            assert args.git_message == 'Test message'
        finally:
            sys.argv = original_argv
