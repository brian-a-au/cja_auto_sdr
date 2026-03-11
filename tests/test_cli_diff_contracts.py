"""Contract tests for CLI and diff module public API signatures and return types.

These tests verify that public APIs honour their documented contracts — correct
callable return types, correct parameter shapes, and correct return value types —
without testing internal behaviour (that belongs to unit/integration suites).
"""

from __future__ import annotations

import argparse
import inspect
from collections.abc import Callable
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_args(**kwargs: Any) -> argparse.Namespace:
    """Build an argparse.Namespace with sensible defaults for execution tests."""
    defaults: dict[str, Any] = {
        "config_file": "config.json",
        "output_dir": ".",
        "log_level": "WARNING",
        "log_format": "text",
        "format": "excel",
        "quiet": False,
        "production": False,
        "dry_run": False,
        "batch": False,
        "workers": 1,
        "continue_on_error": False,
        "enable_cache": False,
        "cache_size": 100,
        "cache_ttl": 3600,
        "skip_validation": False,
        "max_issues": 100,
        "clear_cache": False,
        "show_timings": False,
        "include_derived_inventory": False,
        "include_calculated_metrics": False,
        "include_segments_inventory": False,
        "inventory_only": False,
        "inventory_summary": False,
        "metrics_only": False,
        "dimensions_only": False,
        "assume_yes": False,
        "api_auto_tune": False,
        "circuit_breaker": False,
        "allow_partial": False,
        "open": False,
        "git_commit": False,
        "profile": None,
        "quality_report": None,
    }
    defaults.update(kwargs)
    return argparse.Namespace(**defaults)


# ---------------------------------------------------------------------------
# Class 1: List command factory functions (_fetch_*)
# ---------------------------------------------------------------------------


class TestListCommandFactories:
    """_fetch_connections, _fetch_dataviews, and _fetch_datasets return callables."""

    def test_fetch_connections_returns_callable(self) -> None:
        from cja_auto_sdr.cli.commands.list import _fetch_connections

        result = _fetch_connections(output_format="table")
        assert callable(result), "_fetch_connections must return a callable"

    def test_fetch_connections_callable_accepts_two_args(self) -> None:
        from cja_auto_sdr.cli.commands.list import _fetch_connections

        cb = _fetch_connections(output_format="table")
        sig = inspect.signature(cb)
        params = list(sig.parameters.keys())
        assert len(params) == 2, f"callback must accept exactly 2 params, got {params}"

    @pytest.mark.parametrize("fmt", ["table", "json", "csv"])
    def test_fetch_connections_all_formats_return_callable(self, fmt: str) -> None:
        from cja_auto_sdr.cli.commands.list import _fetch_connections

        cb = _fetch_connections(output_format=fmt)
        assert callable(cb)

    def test_fetch_connections_optional_params_accepted(self) -> None:
        from cja_auto_sdr.cli.commands.list import _fetch_connections

        # Should not raise with all optional params provided
        cb = _fetch_connections(
            output_format="json",
            filter_pattern="prod*",
            exclude_pattern="test*",
            limit=10,
            sort_expression="name asc",
        )
        assert callable(cb)

    def test_fetch_dataviews_returns_callable(self) -> None:
        from cja_auto_sdr.cli.commands.list import _fetch_dataviews

        result = _fetch_dataviews(output_format="table")
        assert callable(result)

    def test_fetch_dataviews_callable_accepts_two_args(self) -> None:
        from cja_auto_sdr.cli.commands.list import _fetch_dataviews

        cb = _fetch_dataviews(output_format="table")
        sig = inspect.signature(cb)
        params = list(sig.parameters.keys())
        assert len(params) == 2

    @pytest.mark.parametrize("fmt", ["table", "json", "csv"])
    def test_fetch_dataviews_all_formats_return_callable(self, fmt: str) -> None:
        from cja_auto_sdr.cli.commands.list import _fetch_dataviews

        assert callable(_fetch_dataviews(output_format=fmt))

    def test_fetch_datasets_returns_callable(self) -> None:
        from cja_auto_sdr.cli.commands.list import _fetch_datasets

        result = _fetch_datasets(output_format="table")
        assert callable(result)

    def test_fetch_datasets_callable_accepts_two_args(self) -> None:
        from cja_auto_sdr.cli.commands.list import _fetch_datasets

        cb = _fetch_datasets(output_format="table")
        sig = inspect.signature(cb)
        params = list(sig.parameters.keys())
        assert len(params) == 2

    @pytest.mark.parametrize("fmt", ["table", "json", "csv"])
    def test_fetch_datasets_all_formats_return_callable(self, fmt: str) -> None:
        from cja_auto_sdr.cli.commands.list import _fetch_datasets

        assert callable(_fetch_datasets(output_format=fmt))

    # ------------------------------------------------------------------
    # Verify callback return-type contract: Optional[str]
    # ------------------------------------------------------------------

    def test_fetch_connections_callback_returns_str_or_none_for_empty(self) -> None:
        """The inner callback must return str | None."""
        from cja_auto_sdr.cli.commands.list import _fetch_connections

        mock_cja = MagicMock()
        mock_cja.getConnections.return_value = []
        mock_cja.getDataViews.return_value = []

        cb = _fetch_connections(output_format="json")
        result = cb(mock_cja, True)
        assert result is None or isinstance(result, str)

    def test_fetch_dataviews_callback_returns_str_or_none_for_empty(self) -> None:
        from cja_auto_sdr.cli.commands.list import _fetch_dataviews

        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = []

        cb = _fetch_dataviews(output_format="json")
        result = cb(mock_cja, True)
        assert result is None or isinstance(result, str)

    def test_fetch_datasets_callback_returns_str_or_none_for_empty(self) -> None:
        from cja_auto_sdr.cli.commands.list import _fetch_datasets

        mock_cja = MagicMock()
        mock_cja.getConnections.return_value = []
        mock_cja.getDataViews.return_value = []

        cb = _fetch_datasets(output_format="json")
        result = cb(mock_cja, True)
        assert result is None or isinstance(result, str)

    def test_fetch_connections_callback_returns_str_for_data(self) -> None:
        from cja_auto_sdr.cli.commands.list import _fetch_connections

        mock_cja = MagicMock()
        mock_cja.getConnections.return_value = [
            {"id": "conn1", "name": "My Conn", "ownerFullName": "Alice", "dataSets": []}
        ]

        cb = _fetch_connections(output_format="json")
        result = cb(mock_cja, True)
        assert isinstance(result, str), "callback must return str when data is present"

    def test_fetch_dataviews_callback_returns_str_for_data(self) -> None:
        from cja_auto_sdr.cli.commands.list import _fetch_dataviews

        mock_cja = MagicMock()
        mock_cja.getDataViews.return_value = [{"id": "dv1", "name": "My DV", "owner": {"imsUserId": "u1"}}]

        cb = _fetch_dataviews(output_format="json")
        result = cb(mock_cja, True)
        assert isinstance(result, str)


# ---------------------------------------------------------------------------
# Class 2: Config command public functions
# ---------------------------------------------------------------------------


class TestConfigCommandSignatures:
    """Public functions in cli/commands/config.py honour their return-type contracts."""

    def test_generate_sample_config_signature(self) -> None:
        from cja_auto_sdr.cli.commands.config import generate_sample_config

        sig = inspect.signature(generate_sample_config)
        params = sig.parameters
        # Must accept output_path with a default
        assert "output_path" in params
        assert params["output_path"].default is not inspect.Parameter.empty

    def test_generate_sample_config_returns_bool(self, tmp_path: Path) -> None:
        from cja_auto_sdr.cli.commands.config import generate_sample_config

        out = tmp_path / "config.sample.json"
        result = generate_sample_config(output_path=str(out))
        assert isinstance(result, bool)

    def test_generate_sample_config_returns_true_on_success(self, tmp_path: Path) -> None:
        from cja_auto_sdr.cli.commands.config import generate_sample_config

        result = generate_sample_config(output_path=str(tmp_path / "cfg.sample.json"))
        assert result is True

    def test_generate_sample_config_returns_false_on_permission_error(self, tmp_path: Path) -> None:
        from cja_auto_sdr.cli.commands.config import generate_sample_config

        with patch("builtins.open", side_effect=PermissionError("denied")):
            result = generate_sample_config(output_path=str(tmp_path / "cfg.sample.json"))
        assert result is False

    def test_read_config_status_file_returns_tuple(self, tmp_path: Path) -> None:
        import logging

        from cja_auto_sdr.cli.commands.config import _read_config_status_file

        config_path = tmp_path / "config.json"
        config_path.write_text('{"org_id": "test@AdobeOrg"}')
        logger = logging.getLogger("test")

        payload, error = _read_config_status_file(str(config_path), logger)
        assert isinstance(payload, dict) or payload is None
        assert isinstance(error, str) or error is None

    def test_read_config_status_file_success_path(self, tmp_path: Path) -> None:
        import logging

        from cja_auto_sdr.cli.commands.config import _read_config_status_file

        config_path = tmp_path / "config.json"
        config_path.write_text('{"org_id": "test@AdobeOrg", "client_id": "cid"}')
        logger = logging.getLogger("test")

        payload, error = _read_config_status_file(str(config_path), logger)
        assert payload is not None
        assert error is None

    def test_read_config_status_file_bad_json_returns_error_string(self, tmp_path: Path) -> None:
        import logging

        from cja_auto_sdr.cli.commands.config import _read_config_status_file

        config_path = tmp_path / "config.json"
        config_path.write_text("{not valid json}")
        logger = logging.getLogger("test")

        payload, error = _read_config_status_file(str(config_path), logger)
        assert payload is None
        assert isinstance(error, str)

    def test_read_config_status_file_non_dict_returns_error(self, tmp_path: Path) -> None:
        import logging

        from cja_auto_sdr.cli.commands.config import _read_config_status_file

        config_path = tmp_path / "config.json"
        config_path.write_text("[1, 2, 3]")
        logger = logging.getLogger("test")

        payload, error = _read_config_status_file(str(config_path), logger)
        assert payload is None
        assert isinstance(error, str)

    def test_resolve_output_dir_path_returns_path(self) -> None:
        from cja_auto_sdr.cli.commands.config import _resolve_output_dir_path

        result = _resolve_output_dir_path(".")
        assert isinstance(result, Path)

    def test_resolve_output_dir_path_accepts_path_object(self, tmp_path: Path) -> None:
        from cja_auto_sdr.cli.commands.config import _resolve_output_dir_path

        result = _resolve_output_dir_path(tmp_path)
        assert isinstance(result, Path)

    def test_check_output_dir_access_returns_4tuple(self, tmp_path: Path) -> None:
        from cja_auto_sdr.cli.commands.config import _check_output_dir_access

        result = _check_output_dir_access(tmp_path)
        assert isinstance(result, tuple)
        assert len(result) == 4

    def test_check_output_dir_access_existing_writable(self, tmp_path: Path) -> None:
        from cja_auto_sdr.cli.commands.config import _check_output_dir_access

        ok, resolved, reason, parent = _check_output_dir_access(tmp_path)
        assert isinstance(ok, bool)
        assert isinstance(resolved, Path)
        assert isinstance(reason, str)
        # parent may be None or Path
        assert parent is None or isinstance(parent, Path)

    def test_check_output_dir_access_not_a_directory(self, tmp_path: Path) -> None:
        from cja_auto_sdr.cli.commands.config import _check_output_dir_access

        file_path = tmp_path / "file.txt"
        file_path.write_text("data")
        ok, _, reason, _ = _check_output_dir_access(file_path)
        assert ok is False
        assert reason == "not_directory"

    def test_check_output_dir_access_nonexistent_creatable(self, tmp_path: Path) -> None:
        from cja_auto_sdr.cli.commands.config import _check_output_dir_access

        new_dir = tmp_path / "new_subdir"
        ok, _, reason, _ = _check_output_dir_access(new_dir)
        assert ok is True
        assert reason == "creatable"

    def test_show_config_status_returns_bool(self) -> None:
        from cja_auto_sdr.cli.commands.config import show_config_status

        with patch("cja_auto_sdr.cli.commands.config._generator_module") as mock_gen:
            mock_gen_obj = MagicMock()
            mock_gen_obj.BANNER_WIDTH = 60
            mock_gen_obj.ConsoleColors.error = str
            mock_gen_obj.ConsoleColors.success = str
            mock_gen_obj.load_profile_credentials.return_value = None
            mock_gen_obj.load_credentials_from_env.return_value = None
            mock_gen_obj.validate_env_credentials.return_value = False
            mock_gen.return_value = mock_gen_obj

            # Non-existent config file path — should return False
            result = show_config_status(config_file="/nonexistent/config.json")
        assert isinstance(result, bool)

    def test_validate_config_only_signature(self) -> None:
        from cja_auto_sdr.cli.commands.config import validate_config_only

        sig = inspect.signature(validate_config_only)
        params = sig.parameters
        assert "config_file" in params
        assert "profile" in params
        assert "output_dir" in params

    def test_validate_config_only_returns_bool(self) -> None:
        """validate_config_only must return bool regardless of credential path taken."""
        import sys

        from cja_auto_sdr.cli.commands.config import validate_config_only

        with patch("cja_auto_sdr.cli.commands.config._generator_module") as mock_gen:
            mock_gen_obj = MagicMock()
            mock_gen_obj.BANNER_WIDTH = 60
            mock_gen_obj.ConsoleColors.error = str
            mock_gen_obj.ConsoleColors.success = str
            mock_gen_obj.ConsoleColors.info = str
            mock_gen_obj.ConsoleColors.warning = str
            # Use real version_info so .major/.minor/.micro attributes work
            mock_gen_obj.sys.version_info = sys.version_info
            mock_gen_obj.sys.platform = sys.platform
            mock_gen_obj.platform.system.return_value = "Linux"
            mock_gen_obj.platform.release.return_value = "5.x"
            mock_gen_obj.platform.mac_ver.return_value = ("", ("", "", ""), "")
            mock_gen_obj._CORE_DEPENDENCIES = []
            mock_gen_obj.load_profile_credentials.return_value = None
            mock_gen_obj.load_credentials_from_env.return_value = None
            mock_gen_obj.validate_env_credentials.return_value = False
            # No config file, so it should return False quickly
            mock_gen.return_value = mock_gen_obj

            result = validate_config_only(config_file="/nonexistent/config.json")
        assert isinstance(result, bool)


# ---------------------------------------------------------------------------
# Class 3: Execution module public functions
# ---------------------------------------------------------------------------


class TestExecutionModuleSignatures:
    """cli/execution.py public functions return the documented types."""

    def test_resolve_inventory_mode_configuration_returns_list(self) -> None:
        from cja_auto_sdr.cli.execution import resolve_inventory_mode_configuration

        args = _make_args()
        with patch("cja_auto_sdr.cli.execution._generator_module") as mock_gen:
            mock_gen_obj = MagicMock()
            mock_gen_obj.ConsoleColors.error = str
            mock_gen.return_value = mock_gen_obj

            result = resolve_inventory_mode_configuration(args, argv=[])
        assert isinstance(result, list)

    def test_resolve_inventory_mode_configuration_list_contains_strings(self) -> None:
        from cja_auto_sdr.cli.execution import resolve_inventory_mode_configuration

        args = _make_args(include_segments_inventory=True)
        with patch("cja_auto_sdr.cli.execution._generator_module") as mock_gen:
            mock_gen_obj = MagicMock()
            mock_gen_obj.ConsoleColors.error = str
            mock_gen.return_value = mock_gen_obj

            result = resolve_inventory_mode_configuration(args, argv=["cja_auto_sdr", "dv1", "--include-segments"])
        assert all(isinstance(item, str) for item in result)

    def test_resolve_inventory_mode_configuration_no_flags_returns_empty_list(self) -> None:
        from cja_auto_sdr.cli.execution import resolve_inventory_mode_configuration

        args = _make_args()
        with patch("cja_auto_sdr.cli.execution._generator_module") as mock_gen:
            mock_gen_obj = MagicMock()
            mock_gen_obj.ConsoleColors.error = str
            mock_gen.return_value = mock_gen_obj

            result = resolve_inventory_mode_configuration(args, argv=[])
        assert result == []

    def test_resolve_inventory_mode_configuration_returns_known_inventory_names(self) -> None:
        from cja_auto_sdr.cli.execution import resolve_inventory_mode_configuration

        args = _make_args(
            include_derived_inventory=True,
            include_calculated_metrics=True,
            include_segments_inventory=True,
        )
        with patch("cja_auto_sdr.cli.execution._generator_module") as mock_gen:
            mock_gen_obj = MagicMock()
            mock_gen_obj.ConsoleColors.error = str
            mock_gen.return_value = mock_gen_obj

            result = resolve_inventory_mode_configuration(
                args,
                argv=["prog", "--include-derived", "--include-calculated", "--include-segments"],
            )
        valid_names = {"derived", "calculated", "segments"}
        assert set(result) <= valid_names

    def test_resolve_inventory_mode_configuration_preserves_cli_order(self) -> None:
        from cja_auto_sdr.cli.execution import resolve_inventory_mode_configuration

        args = _make_args(
            include_calculated_metrics=True,
            include_segments_inventory=True,
        )
        with patch("cja_auto_sdr.cli.execution._generator_module") as mock_gen:
            mock_gen_obj = MagicMock()
            mock_gen_obj.ConsoleColors.error = str
            mock_gen.return_value = mock_gen_obj

            result = resolve_inventory_mode_configuration(
                args,
                argv=["prog", "--include-segments", "--include-calculated"],
            )
        # segments appears before calculated in argv, so segments should come first
        assert result == ["segments", "calculated"]

    def test_resolve_inventory_mode_configuration_is_in_all(self) -> None:
        from cja_auto_sdr.cli import execution

        assert "resolve_inventory_mode_configuration" in execution.__all__

    def test_execute_sdr_processing_modes_is_in_all(self) -> None:
        from cja_auto_sdr.cli import execution

        assert "execute_sdr_processing_modes" in execution.__all__

    def test_prepare_sdr_execution_context_is_in_all(self) -> None:
        from cja_auto_sdr.cli import execution

        assert "prepare_sdr_execution_context" in execution.__all__

    def test_dispatch_inventory_summary_mode_is_in_all(self) -> None:
        from cja_auto_sdr.cli import execution

        assert "dispatch_inventory_summary_mode" in execution.__all__


# ---------------------------------------------------------------------------
# Class 4: Diff/Git module public functions
# ---------------------------------------------------------------------------


class TestDiffGitSignatures:
    """diff/git.py public functions return their documented types."""

    # --- is_git_repository ---

    def test_is_git_repository_signature(self) -> None:
        from cja_auto_sdr.diff.git import is_git_repository

        sig = inspect.signature(is_git_repository)
        params = list(sig.parameters.keys())
        assert params == ["path"]

    def test_is_git_repository_returns_bool_for_nonexistent_path(self, tmp_path: Path) -> None:
        from cja_auto_sdr.diff.git import is_git_repository

        result = is_git_repository(tmp_path / "not_a_repo")
        assert isinstance(result, bool)

    def test_is_git_repository_returns_false_for_plain_directory(self, tmp_path: Path) -> None:
        from cja_auto_sdr.diff.git import is_git_repository

        result = is_git_repository(tmp_path)
        assert result is False

    def test_is_git_repository_returns_bool_when_git_unavailable(self, tmp_path: Path) -> None:
        from cja_auto_sdr.diff.git import is_git_repository

        with patch("subprocess.run", side_effect=FileNotFoundError("git not found")):
            result = is_git_repository(tmp_path)
        assert isinstance(result, bool)
        assert result is False

    # --- generate_git_commit_message ---

    def test_generate_git_commit_message_signature(self) -> None:
        from cja_auto_sdr.diff.git import generate_git_commit_message

        sig = inspect.signature(generate_git_commit_message)
        params = sig.parameters
        assert "data_view_id" in params
        assert "data_view_name" in params
        assert "metrics_count" in params
        assert "dimensions_count" in params

    def test_generate_git_commit_message_returns_str(self) -> None:
        from cja_auto_sdr.diff.git import generate_git_commit_message

        result = generate_git_commit_message(
            data_view_id="dv_abc123",
            data_view_name="My Data View",
            metrics_count=10,
            dimensions_count=20,
        )
        assert isinstance(result, str)

    def test_generate_git_commit_message_contains_data_view_id(self) -> None:
        from cja_auto_sdr.diff.git import generate_git_commit_message

        result = generate_git_commit_message(
            data_view_id="dv_abc123",
            data_view_name="My Data View",
            metrics_count=10,
            dimensions_count=20,
        )
        assert "dv_abc123" in result

    def test_generate_git_commit_message_with_custom_message(self) -> None:
        from cja_auto_sdr.diff.git import generate_git_commit_message

        result = generate_git_commit_message(
            data_view_id="dv_abc123",
            data_view_name="My Data View",
            metrics_count=5,
            dimensions_count=10,
            custom_message="weekly snapshot",
        )
        assert isinstance(result, str)
        assert "weekly snapshot" in result

    def test_generate_git_commit_message_with_quality_issues(self) -> None:
        from cja_auto_sdr.diff.git import generate_git_commit_message

        issues = [{"Severity": "HIGH"}, {"Severity": "LOW"}, {"Severity": "HIGH"}]
        result = generate_git_commit_message(
            data_view_id="dv_x",
            data_view_name="DV",
            metrics_count=0,
            dimensions_count=0,
            quality_issues=issues,
        )
        assert isinstance(result, str)
        assert "HIGH" in result

    def test_generate_git_commit_message_is_nonempty(self) -> None:
        from cja_auto_sdr.diff.git import generate_git_commit_message

        result = generate_git_commit_message(
            data_view_id="dv1",
            data_view_name="Name",
            metrics_count=1,
            dimensions_count=1,
        )
        assert len(result) > 0

    # --- git_commit_snapshot ---

    def test_git_commit_snapshot_signature(self) -> None:
        from cja_auto_sdr.diff.git import git_commit_snapshot

        sig = inspect.signature(git_commit_snapshot)
        params = sig.parameters
        assert "snapshot_dir" in params
        assert "data_view_id" in params
        assert "data_view_name" in params
        assert "metrics_count" in params
        assert "dimensions_count" in params

    def test_git_commit_snapshot_returns_tuple_when_not_git_repo(self, tmp_path: Path) -> None:
        from cja_auto_sdr.diff.git import git_commit_snapshot

        ok, msg = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv1",
            data_view_name="My DV",
            metrics_count=5,
            dimensions_count=10,
        )
        assert isinstance(ok, bool)
        assert isinstance(msg, str)

    def test_git_commit_snapshot_returns_false_for_nonrepo(self, tmp_path: Path) -> None:
        from cja_auto_sdr.diff.git import git_commit_snapshot

        ok, msg = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv1",
            data_view_name="My DV",
            metrics_count=5,
            dimensions_count=10,
        )
        assert ok is False
        assert len(msg) > 0

    def test_git_commit_snapshot_tuple_length(self, tmp_path: Path) -> None:
        from cja_auto_sdr.diff.git import git_commit_snapshot

        result = git_commit_snapshot(
            snapshot_dir=tmp_path,
            data_view_id="dv1",
            data_view_name="My DV",
            metrics_count=5,
            dimensions_count=10,
        )
        assert isinstance(result, tuple)
        assert len(result) == 2

    # --- git_init_snapshot_repo ---

    def test_git_init_snapshot_repo_signature(self) -> None:
        from cja_auto_sdr.diff.git import git_init_snapshot_repo

        sig = inspect.signature(git_init_snapshot_repo)
        params = sig.parameters
        assert "directory" in params

    def test_git_init_snapshot_repo_returns_tuple(self, tmp_path: Path) -> None:
        from cja_auto_sdr.diff.git import git_init_snapshot_repo

        new_dir = tmp_path / "snapshots"
        result = git_init_snapshot_repo(new_dir)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_git_init_snapshot_repo_tuple_types(self, tmp_path: Path) -> None:
        from cja_auto_sdr.diff.git import git_init_snapshot_repo

        new_dir = tmp_path / "snapshots"
        ok, msg = git_init_snapshot_repo(new_dir)
        assert isinstance(ok, bool)
        assert isinstance(msg, str)

    def test_git_init_snapshot_repo_returns_false_for_os_error(self, tmp_path: Path) -> None:
        from cja_auto_sdr.diff.git import git_init_snapshot_repo

        with patch("pathlib.Path.mkdir", side_effect=OSError("permission denied")):
            ok, msg = git_init_snapshot_repo(tmp_path / "snapshots")
        assert ok is False
        assert isinstance(msg, str)

    def test_git_init_snapshot_repo_creates_directory_on_success(self, tmp_path: Path) -> None:
        """When git is available and init succeeds, the directory is created."""
        import subprocess

        from cja_auto_sdr.diff.git import git_init_snapshot_repo

        new_dir = tmp_path / "my_snapshots"

        # Only run this test if git is actually available
        try:
            subprocess.run(["git", "--version"], capture_output=True, timeout=5, check=True)
        except FileNotFoundError, subprocess.SubprocessError:
            pytest.skip("git not available in test environment")

        ok, msg = git_init_snapshot_repo(new_dir)
        if ok:
            assert new_dir.exists()
        assert isinstance(ok, bool)
        assert isinstance(msg, str)


# ---------------------------------------------------------------------------
# Class 5: _run_list_command contract
# ---------------------------------------------------------------------------


class TestRunListCommandContract:
    """_run_list_command returns bool and accepts the documented signature."""

    def test_run_list_command_signature(self) -> None:
        from cja_auto_sdr.cli.commands.list import _run_list_command

        sig = inspect.signature(_run_list_command)
        params = sig.parameters
        assert "banner_text" in params
        assert "command_name" in params
        assert "fetch_and_format" in params
        assert "config_file" in params
        assert "output_format" in params
        assert "output_file" in params
        assert "profile" in params
        assert "validate_inputs" in params

    def test_run_list_command_returns_bool(self) -> None:
        from cja_auto_sdr.cli.commands.list import _run_list_command

        dummy_callable: Callable[[Any, bool], str | None] = lambda cja, mr: None  # noqa: E731

        with (
            patch("cja_auto_sdr.cli.commands.list._generator") as mock_gen,
        ):
            mock_gen.resolve_active_profile.return_value = None
            mock_gen.BANNER_WIDTH = 60
            mock_gen._is_machine_readable_output.return_value = False
            mock_gen.configure_cjapy.return_value = (False, "Config error", None)
            mock_gen._emit_discovery_error = MagicMock()

            result = _run_list_command(
                banner_text="TEST",
                command_name="test",
                fetch_and_format=dummy_callable,
            )
        assert isinstance(result, bool)

    def test_run_list_command_returns_false_on_config_error(self) -> None:
        from cja_auto_sdr.cli.commands.list import _run_list_command

        dummy_callable: Callable[[Any, bool], str | None] = lambda cja, mr: "data"  # noqa: E731

        with patch("cja_auto_sdr.cli.commands.list._generator") as mock_gen:
            mock_gen.resolve_active_profile.return_value = None
            mock_gen.BANNER_WIDTH = 60
            mock_gen._is_machine_readable_output.return_value = True
            mock_gen.configure_cjapy.return_value = (False, "Bad config", None)
            mock_gen._emit_discovery_error = MagicMock()

            result = _run_list_command(
                banner_text="TEST",
                command_name="test",
                fetch_and_format=dummy_callable,
            )
        assert result is False
