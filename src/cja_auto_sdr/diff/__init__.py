"""Diff module - data view comparison and snapshot tooling."""

from __future__ import annotations

from cja_auto_sdr.diff.comparator import DataViewComparator
from cja_auto_sdr.diff.git import (
    generate_git_commit_message,
    git_commit_snapshot,
    git_get_user_info,
    git_init_snapshot_repo,
    git_repository_state,
    is_git_repository,
    save_git_friendly_snapshot,
)
from cja_auto_sdr.diff.models import (
    ChangeType,
    ComponentDiff,
    DataViewSnapshot,
    DiffResult,
    DiffSummary,
    InventoryItemDiff,
    MetadataDiff,
)
from cja_auto_sdr.diff.snapshot import SnapshotManager, parse_retention_period

__all__ = [
    "ChangeType",
    "ComponentDiff",
    "DataViewComparator",
    "DataViewSnapshot",
    "DiffResult",
    "DiffSummary",
    "InventoryItemDiff",
    "MetadataDiff",
    "SnapshotManager",
    "generate_git_commit_message",
    "git_commit_snapshot",
    "git_get_user_info",
    "git_init_snapshot_repo",
    "git_repository_state",
    "is_git_repository",
    "parse_retention_period",
    "save_git_friendly_snapshot",
    "write_diff_console_output",
    "write_diff_csv_output",
    "write_diff_excel_output",
    "write_diff_html_output",
    "write_diff_json_output",
    "write_diff_markdown_output",
    "write_diff_output",
    "write_diff_pr_comment_output",
]


from cja_auto_sdr.core.lazy import make_getattr

__getattr__ = make_getattr(
    __name__,
    [
        "write_diff_console_output",
        "write_diff_csv_output",
        "write_diff_excel_output",
        "write_diff_html_output",
        "write_diff_json_output",
        "write_diff_markdown_output",
        "write_diff_output",
        "write_diff_pr_comment_output",
    ],
    target_module="cja_auto_sdr.diff.writers",
)
