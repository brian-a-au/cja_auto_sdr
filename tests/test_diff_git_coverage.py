"""Edge-case tests for cja_auto_sdr.diff.git to increase coverage to 97%+.

Targets uncovered lines in:
- git_commit_snapshot(): L253, 259, 263, 281, 285, 291, 295, 304-310, 312-313
- git_init_snapshot_repo(): L341, 357, 363, 374, 380, 419, 425, 436, 442, 449-450
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from cja_auto_sdr.diff.git import git_commit_snapshot, git_init_snapshot_repo

# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------


def _make_ok(stdout: str = "", stderr: str = "") -> MagicMock:
    """Return a MagicMock resembling a successful CompletedProcess."""
    m = MagicMock(spec=subprocess.CompletedProcess)
    m.returncode = 0
    m.stdout = stdout
    m.stderr = stderr
    return m


def _make_fail(stderr: str = "error output") -> MagicMock:
    """Return a MagicMock resembling a failed CompletedProcess (returncode=1)."""
    m = MagicMock(spec=subprocess.CompletedProcess)
    m.returncode = 1
    m.stdout = ""
    m.stderr = stderr
    return m


# ---------------------------------------------------------------------------
# git_commit_snapshot — git-add failure paths
# ---------------------------------------------------------------------------


class TestGitCommitSnapshotGitAddFailures:
    """Verify graceful degradation when the git-add step has issues."""

    @patch("cja_auto_sdr.diff.git._snapshot_pathspecs_for_data_view", return_value=["dv_dir_dv_123"])
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_git_add_returns_none_result(self, mock_cmd, _mock_repo, _mock_paths, tmp_path):
        """L253: _run_git_command returns (None, None) → unknown subprocess failure."""
        mock_cmd.return_value = (None, None)

        success, message = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_123",
            data_view_name="Test",
            metrics_count=1,
            dimensions_count=1,
        )

        assert success is False
        assert "unknown subprocess failure" in message

    @patch("cja_auto_sdr.diff.git._snapshot_pathspecs_for_data_view", return_value=["dv_dir_dv_123"])
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_git_add_raises_boundary_error(self, mock_cmd, _mock_repo, _mock_paths, tmp_path):
        """L248-251/259: _run_git_command returns (None, error) → formatted boundary error."""
        exc = subprocess.TimeoutExpired(cmd="git", timeout=30)
        mock_cmd.return_value = (None, exc)

        success, message = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_123",
            data_view_name="Test",
            metrics_count=1,
            dimensions_count=1,
        )

        assert success is False
        assert "timed out" in message.lower()


# ---------------------------------------------------------------------------
# git_commit_snapshot — git-diff --cached paths
# ---------------------------------------------------------------------------


class TestGitCommitSnapshotDiffCachedPaths:
    """Verify graceful degradation when the diff-cached step has issues."""

    @patch("cja_auto_sdr.diff.git._snapshot_pathspecs_for_data_view", return_value=["dv_dir_dv_123"])
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_diff_cached_raises_boundary_error(self, mock_cmd, _mock_repo, _mock_paths, tmp_path):
        """L258-261: diff --cached returns (None, error)."""
        exc = FileNotFoundError("git not found")
        mock_cmd.side_effect = [
            (_make_ok(), None),  # git add succeeds
            (None, exc),  # git diff --cached → error
        ]

        success, message = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_123",
            data_view_name="Test",
            metrics_count=1,
            dimensions_count=1,
        )

        assert success is False
        assert "Git not found" in message

    @patch("cja_auto_sdr.diff.git._snapshot_pathspecs_for_data_view", return_value=["dv_dir_dv_123"])
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_diff_cached_returns_none_result(self, mock_cmd, _mock_repo, _mock_paths, tmp_path):
        """L262-263: diff --cached returns (None, None) → unknown subprocess failure."""
        mock_cmd.side_effect = [
            (_make_ok(), None),  # git add succeeds
            (None, None),  # git diff --cached → (None, None)
        ]

        success, message = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_123",
            data_view_name="Test",
            metrics_count=1,
            dimensions_count=1,
        )

        assert success is False
        assert "unknown subprocess failure" in message

    @patch("cja_auto_sdr.diff.git._snapshot_pathspecs_for_data_view", return_value=["dv_dir_dv_123"])
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_diff_cached_returncode_zero_means_no_changes(self, mock_cmd, _mock_repo, _mock_paths, tmp_path):
        """L263-266: diff --cached returncode==0 → no changes to commit."""
        mock_cmd.side_effect = [
            (_make_ok(), None),  # git add succeeds
            (_make_ok(), None),  # git diff --cached returns 0 (no changes)
        ]

        success, message = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_123",
            data_view_name="Test",
            metrics_count=1,
            dimensions_count=1,
        )

        assert success is True
        assert message == "no_changes"


# ---------------------------------------------------------------------------
# git_commit_snapshot — git-commit failure paths
# ---------------------------------------------------------------------------


class TestGitCommitSnapshotCommitFailures:
    """Verify graceful degradation when the git-commit step has issues."""

    @patch("cja_auto_sdr.diff.git._snapshot_pathspecs_for_data_view", return_value=["dv_dir_dv_123"])
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_commit_raises_boundary_error(self, mock_cmd, _mock_repo, _mock_paths, tmp_path):
        """L280-283: git commit returns (None, error) → formatted boundary error."""
        exc = subprocess.TimeoutExpired(cmd="git", timeout=30)
        # diff --cached returns 1 (changes exist)
        diff_result = MagicMock(spec=subprocess.CompletedProcess)
        diff_result.returncode = 1
        diff_result.stdout = ""
        diff_result.stderr = ""

        mock_cmd.side_effect = [
            (_make_ok(), None),  # git add succeeds
            (diff_result, None),  # git diff --cached → returncode 1 (has changes)
            (None, exc),  # git commit → timeout error
        ]

        success, message = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_123",
            data_view_name="Test",
            metrics_count=1,
            dimensions_count=1,
        )

        assert success is False
        assert "timed out" in message.lower()

    @patch("cja_auto_sdr.diff.git._snapshot_pathspecs_for_data_view", return_value=["dv_dir_dv_123"])
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_commit_returns_none_result(self, mock_cmd, _mock_repo, _mock_paths, tmp_path):
        """L284-285: git commit returns (None, None) → unknown subprocess failure."""
        diff_result = MagicMock(spec=subprocess.CompletedProcess)
        diff_result.returncode = 1
        diff_result.stdout = ""
        diff_result.stderr = ""

        mock_cmd.side_effect = [
            (_make_ok(), None),  # git add succeeds
            (diff_result, None),  # git diff --cached → changes exist
            (None, None),  # git commit → (None, None)
        ]

        success, message = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_123",
            data_view_name="Test",
            metrics_count=1,
            dimensions_count=1,
        )

        assert success is False
        assert "unknown subprocess failure" in message


# ---------------------------------------------------------------------------
# git_commit_snapshot — rev-parse failure paths
# ---------------------------------------------------------------------------


class TestGitCommitSnapshotRevParseFailures:
    """Verify graceful degradation when the rev-parse step has issues."""

    def _diff_result_with_changes(self) -> MagicMock:
        m = MagicMock(spec=subprocess.CompletedProcess)
        m.returncode = 1  # non-zero means "there are staged changes"
        m.stdout = ""
        m.stderr = ""
        return m

    @patch("cja_auto_sdr.diff.git._snapshot_pathspecs_for_data_view", return_value=["dv_dir_dv_123"])
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_rev_parse_raises_boundary_error(self, mock_cmd, _mock_repo, _mock_paths, tmp_path):
        """L290-293: rev-parse returns (None, error) → (False, formatted message)."""
        exc = subprocess.TimeoutExpired(cmd="git", timeout=10)

        mock_cmd.side_effect = [
            (_make_ok(), None),  # git add
            (self._diff_result_with_changes(), None),  # git diff --cached
            (_make_ok(), None),  # git commit
            (None, exc),  # git rev-parse → timeout
        ]

        success, message = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_123",
            data_view_name="Test",
            metrics_count=1,
            dimensions_count=1,
        )

        assert success is False
        assert "timed out" in message.lower()

    @patch("cja_auto_sdr.diff.git._snapshot_pathspecs_for_data_view", return_value=["dv_dir_dv_123"])
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_rev_parse_returns_none_result(self, mock_cmd, _mock_repo, _mock_paths, tmp_path):
        """L294-295: rev-parse returns (None, None) → (False, unknown failure)."""
        mock_cmd.side_effect = [
            (_make_ok(), None),  # git add
            (self._diff_result_with_changes(), None),  # git diff --cached
            (_make_ok(), None),  # git commit
            (None, None),  # git rev-parse → (None, None)
        ]

        success, message = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_123",
            data_view_name="Test",
            metrics_count=1,
            dimensions_count=1,
        )

        assert success is False
        assert "unknown subprocess failure" in message


# ---------------------------------------------------------------------------
# git_commit_snapshot — push failure paths (graceful degradation)
# ---------------------------------------------------------------------------


class TestGitCommitSnapshotPushFailures:
    """Push failures must degrade gracefully — still return (True, sha)."""

    def _successful_up_to_rev_parse(self, sha: str = "abcdef1234567890") -> list:
        diff_has_changes = MagicMock(spec=subprocess.CompletedProcess)
        diff_has_changes.returncode = 1
        diff_has_changes.stdout = ""
        diff_has_changes.stderr = ""

        rev_parse_ok = MagicMock(spec=subprocess.CompletedProcess)
        rev_parse_ok.returncode = 0
        rev_parse_ok.stdout = sha + "\n"
        rev_parse_ok.stderr = ""

        return [
            (_make_ok(), None),  # git add
            (diff_has_changes, None),  # git diff --cached
            (_make_ok(), None),  # git commit
            (rev_parse_ok, None),  # git rev-parse HEAD
        ]

    @patch("cja_auto_sdr.diff.git._snapshot_pathspecs_for_data_view", return_value=["dv_dir_dv_123"])
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_push_raises_boundary_error_graceful_degradation(self, mock_cmd, _mock_repo, _mock_paths, tmp_path):
        """L303-310: push returns (None, error) → (True, sha + push-failed message)."""
        exc = subprocess.TimeoutExpired(cmd="git", timeout=60)
        side_effects = self._successful_up_to_rev_parse()
        side_effects.append((None, exc))  # git push → timeout

        mock_cmd.side_effect = side_effects

        success, message = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_123",
            data_view_name="Test",
            metrics_count=1,
            dimensions_count=1,
            push=True,
        )

        assert success is True
        assert "push failed" in message
        assert "abcdef12" in message  # first 8 chars of sha

    @patch("cja_auto_sdr.diff.git._snapshot_pathspecs_for_data_view", return_value=["dv_dir_dv_123"])
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_push_returns_none_result_graceful_degradation(self, mock_cmd, _mock_repo, _mock_paths, tmp_path):
        """L311-313: push returns (None, None) → (True, sha + unknown push failure)."""
        side_effects = self._successful_up_to_rev_parse()
        side_effects.append((None, None))  # git push → (None, None)

        mock_cmd.side_effect = side_effects

        success, message = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_123",
            data_view_name="Test",
            metrics_count=1,
            dimensions_count=1,
            push=True,
        )

        assert success is True
        assert "push failed" in message
        assert "unknown subprocess failure" in message

    @patch("cja_auto_sdr.diff.git._snapshot_pathspecs_for_data_view", return_value=["dv_dir_dv_123"])
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_push_non_zero_returncode_graceful_degradation(self, mock_cmd, _mock_repo, _mock_paths, tmp_path):
        """L314-316: push returns non-zero returncode → (True, sha + push-failed stderr)."""
        push_fail = MagicMock(spec=subprocess.CompletedProcess)
        push_fail.returncode = 128
        push_fail.stdout = ""
        push_fail.stderr = "fatal: remote rejected"

        side_effects = self._successful_up_to_rev_parse()
        side_effects.append((push_fail, None))  # git push → returncode 128

        mock_cmd.side_effect = side_effects

        success, message = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_123",
            data_view_name="Test",
            metrics_count=1,
            dimensions_count=1,
            push=True,
        )

        assert success is True
        assert "push failed" in message
        assert "fatal: remote rejected" in message

    @patch("cja_auto_sdr.diff.git._snapshot_pathspecs_for_data_view", return_value=["dv_dir_dv_123"])
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_push_generic_exception_graceful_degradation(self, mock_cmd, _mock_repo, _mock_paths, tmp_path):
        """L303-310: push raises OSError → (True, sha + formatted push-failed message)."""
        exc = OSError("network error")
        side_effects = self._successful_up_to_rev_parse()
        side_effects.append((None, exc))  # git push → OSError

        mock_cmd.side_effect = side_effects

        success, message = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_123",
            data_view_name="Test",
            metrics_count=1,
            dimensions_count=1,
            push=True,
        )

        assert success is True
        assert "push failed" in message


# ---------------------------------------------------------------------------
# git_init_snapshot_repo — git init failure paths
# ---------------------------------------------------------------------------


class TestGitInitSnapshotRepoInitFailures:
    """Verify error paths during the git-init step."""

    @patch("cja_auto_sdr.diff.git.git_get_user_info", return_value=("Bot", ""))
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=False)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_git_init_returns_none_result(self, mock_cmd, _mock_repo, _mock_user, tmp_path):
        """L340-341: git init returns (None, None) → unknown subprocess failure."""
        mock_cmd.return_value = (None, None)

        success, message = git_init_snapshot_repo(tmp_path)

        assert success is False
        assert "unknown subprocess failure" in message

    @patch("cja_auto_sdr.diff.git.git_get_user_info", return_value=("Bot", ""))
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=False)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_git_init_raises_boundary_error(self, mock_cmd, _mock_repo, _mock_user, tmp_path):
        """L334-339: git init returns (None, error) → formatted boundary error."""
        exc = subprocess.TimeoutExpired(cmd="git", timeout=30)
        mock_cmd.return_value = (None, exc)

        success, message = git_init_snapshot_repo(tmp_path)

        assert success is False
        assert "timed out" in message.lower()


# ---------------------------------------------------------------------------
# git_init_snapshot_repo — git config user.name failure paths
# ---------------------------------------------------------------------------


class TestGitInitSnapshotRepoConfigNameFailures:
    """Verify error paths during git config user.name."""

    @patch("cja_auto_sdr.diff.git.git_get_user_info", return_value=("Bot", ""))
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=False)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_config_name_raises_boundary_error(self, mock_cmd, _mock_repo, _mock_user, tmp_path):
        """L356-361: git config user.name returns (None, error)."""
        exc = subprocess.TimeoutExpired(cmd="git", timeout=30)
        mock_cmd.side_effect = [
            (_make_ok(), None),  # git init
            (None, exc),  # git config user.name → timeout
        ]

        success, message = git_init_snapshot_repo(tmp_path)

        assert success is False
        assert "timed out" in message.lower()

    @patch("cja_auto_sdr.diff.git.git_get_user_info", return_value=("Bot", ""))
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=False)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_config_name_returns_none_result(self, mock_cmd, _mock_repo, _mock_user, tmp_path):
        """L362-363: git config user.name returns (None, None)."""
        mock_cmd.side_effect = [
            (_make_ok(), None),  # git init
            (None, None),  # git config user.name → (None, None)
        ]

        success, message = git_init_snapshot_repo(tmp_path)

        assert success is False
        assert "unknown subprocess failure" in message


# ---------------------------------------------------------------------------
# git_init_snapshot_repo — git config user.email failure paths
# ---------------------------------------------------------------------------


class TestGitInitSnapshotRepoConfigEmailFailures:
    """Verify error paths during git config user.email."""

    @patch("cja_auto_sdr.diff.git.git_get_user_info", return_value=("Bot", ""))
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=False)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_config_email_raises_boundary_error(self, mock_cmd, _mock_repo, _mock_user, tmp_path):
        """L373-378: git config user.email returns (None, error)."""
        exc = subprocess.TimeoutExpired(cmd="git", timeout=30)
        mock_cmd.side_effect = [
            (_make_ok(), None),  # git init
            (_make_ok(), None),  # git config user.name
            (None, exc),  # git config user.email → timeout
        ]

        success, message = git_init_snapshot_repo(tmp_path)

        assert success is False
        assert "timed out" in message.lower()

    @patch("cja_auto_sdr.diff.git.git_get_user_info", return_value=("Bot", ""))
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=False)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_config_email_returns_none_result(self, mock_cmd, _mock_repo, _mock_user, tmp_path):
        """L379-380: git config user.email returns (None, None)."""
        mock_cmd.side_effect = [
            (_make_ok(), None),  # git init
            (_make_ok(), None),  # git config user.name
            (None, None),  # git config user.email → (None, None)
        ]

        success, message = git_init_snapshot_repo(tmp_path)

        assert success is False
        assert "unknown subprocess failure" in message


# ---------------------------------------------------------------------------
# git_init_snapshot_repo — git add failure paths
# ---------------------------------------------------------------------------


class TestGitInitSnapshotRepoAddFailures:
    """Verify error paths during the git-add step inside init."""

    @patch("cja_auto_sdr.diff.git.git_get_user_info", return_value=("Bot", "bot@local"))
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=False)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_git_add_raises_boundary_error(self, mock_cmd, _mock_repo, _mock_user, tmp_path):
        """L418-423: git add returns (None, error) during init."""
        exc = subprocess.TimeoutExpired(cmd="git", timeout=30)
        mock_cmd.side_effect = [
            (_make_ok(), None),  # git init
            (_make_ok(), None),  # git config user.name
            (_make_ok(), None),  # git config user.email
            (None, exc),  # git add → timeout
        ]

        success, message = git_init_snapshot_repo(tmp_path)

        assert success is False
        assert "timed out" in message.lower()

    @patch("cja_auto_sdr.diff.git.git_get_user_info", return_value=("Bot", "bot@local"))
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=False)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_git_add_returns_none_result(self, mock_cmd, _mock_repo, _mock_user, tmp_path):
        """L424-425: git add returns (None, None) during init."""
        mock_cmd.side_effect = [
            (_make_ok(), None),  # git init
            (_make_ok(), None),  # git config user.name
            (_make_ok(), None),  # git config user.email
            (None, None),  # git add → (None, None)
        ]

        success, message = git_init_snapshot_repo(tmp_path)

        assert success is False
        assert "unknown subprocess failure" in message


# ---------------------------------------------------------------------------
# git_init_snapshot_repo — git commit (initial) failure paths
# ---------------------------------------------------------------------------


class TestGitInitSnapshotRepoInitialCommitFailures:
    """Verify error paths during the initial git-commit step inside init."""

    @patch("cja_auto_sdr.diff.git.git_get_user_info", return_value=("Bot", "bot@local"))
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=False)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_initial_commit_raises_boundary_error(self, mock_cmd, _mock_repo, _mock_user, tmp_path):
        """L435-440: initial commit returns (None, error) during init."""
        exc = subprocess.TimeoutExpired(cmd="git", timeout=30)
        mock_cmd.side_effect = [
            (_make_ok(), None),  # git init
            (_make_ok(), None),  # git config user.name
            (_make_ok(), None),  # git config user.email
            (_make_ok(), None),  # git add
            (None, exc),  # git commit → timeout
        ]

        success, message = git_init_snapshot_repo(tmp_path)

        assert success is False
        assert "timed out" in message.lower()

    @patch("cja_auto_sdr.diff.git.git_get_user_info", return_value=("Bot", "bot@local"))
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=False)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_initial_commit_returns_none_result(self, mock_cmd, _mock_repo, _mock_user, tmp_path):
        """L441-442: initial commit returns (None, None) during init."""
        mock_cmd.side_effect = [
            (_make_ok(), None),  # git init
            (_make_ok(), None),  # git config user.name
            (_make_ok(), None),  # git config user.email
            (_make_ok(), None),  # git add
            (None, None),  # git commit → (None, None)
        ]

        success, message = git_init_snapshot_repo(tmp_path)

        assert success is False
        assert "unknown subprocess failure" in message


# ---------------------------------------------------------------------------
# git_init_snapshot_repo — OSError catch-all
# ---------------------------------------------------------------------------


class TestGitInitSnapshotRepoOSErrorCatchAll:
    """Verify OSError during directory creation is caught and returned as tuple."""

    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=False)
    def test_oserror_during_mkdir_returns_failure_tuple(self, _mock_repo, tmp_path):
        """L449-450: OSError (e.g. permission denied on mkdir) returns (False, message)."""
        read_only_parent = tmp_path / "read_only"
        read_only_parent.mkdir()
        read_only_parent.chmod(0o444)

        try:
            target = read_only_parent / "subdir"
            success, message = git_init_snapshot_repo(target)

            # On some CI/macOS environments root may bypass permission; only assert contract
            if not success:
                assert "Initialization failed:" in message
        finally:
            read_only_parent.chmod(0o755)

    @patch("cja_auto_sdr.diff.git.git_get_user_info", return_value=("Bot", "bot@local"))
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=False)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_oserror_during_gitignore_write_returns_failure_tuple(self, mock_cmd, _mock_repo, _mock_user, tmp_path):
        """L449-450: OSError while writing .gitignore is caught as OSError catch-all."""
        # All git commands succeed, but writing .gitignore raises OSError
        mock_cmd.side_effect = [
            (_make_ok(), None),  # git init
            (_make_ok(), None),  # git config user.name
            (_make_ok(), None),  # git config user.email
        ]

        with patch("pathlib.Path.write_text", side_effect=OSError("disk full")):
            success, message = git_init_snapshot_repo(tmp_path)

        assert success is False
        assert "Initialization failed:" in message
        assert "disk full" in message


# ---------------------------------------------------------------------------
# git_commit_snapshot — no snapshot directory found
# ---------------------------------------------------------------------------


class TestGitCommitSnapshotNoSnapshotDir:
    """Verify failure when no snapshot directory is found for the data view."""

    @patch("cja_auto_sdr.diff.git._snapshot_pathspecs_for_data_view", return_value=[])
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=True)
    def test_no_snapshot_dir_returns_failure(self, _mock_repo, _mock_paths, tmp_path):
        """Early exit when pathspecs is empty."""
        success, message = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_999",
            data_view_name="Missing",
            metrics_count=0,
            dimensions_count=0,
        )

        assert success is False
        assert "No snapshot directory found" in message


# ---------------------------------------------------------------------------
# git_commit_snapshot — successful push
# ---------------------------------------------------------------------------


class TestGitCommitSnapshotSuccessfulPush:
    """Verify successful push flow returns (True, sha) without push-failed note."""

    @patch("cja_auto_sdr.diff.git._snapshot_pathspecs_for_data_view", return_value=["dv_dir_dv_123"])
    @patch("cja_auto_sdr.diff.git.is_git_repository", return_value=True)
    @patch("cja_auto_sdr.diff.git._run_git_command")
    def test_successful_push_returns_sha(self, mock_cmd, _mock_repo, _mock_paths, tmp_path):
        """Happy path with push=True: returns (True, 8-char sha) with no push-failed note."""
        diff_has_changes = MagicMock(spec=subprocess.CompletedProcess)
        diff_has_changes.returncode = 1
        diff_has_changes.stdout = ""
        diff_has_changes.stderr = ""

        rev_parse_ok = MagicMock(spec=subprocess.CompletedProcess)
        rev_parse_ok.returncode = 0
        rev_parse_ok.stdout = "deadbeef12345678\n"
        rev_parse_ok.stderr = ""

        mock_cmd.side_effect = [
            (_make_ok(), None),  # git add
            (diff_has_changes, None),  # git diff --cached
            (_make_ok(), None),  # git commit
            (rev_parse_ok, None),  # git rev-parse
            (_make_ok(), None),  # git push → success
        ]

        success, message = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv_123",
            data_view_name="Test",
            metrics_count=1,
            dimensions_count=1,
            push=True,
        )

        assert success is True
        assert message == "deadbeef"
        assert "push failed" not in message
