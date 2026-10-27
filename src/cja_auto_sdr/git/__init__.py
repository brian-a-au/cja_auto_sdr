"""Git module - Git integration for snapshots."""

from cja_auto_sdr.diff.git import (
    generate_git_commit_message,
    git_commit_snapshot,
    git_get_user_info,
    git_init_snapshot_repo,
    git_repository_state,
    is_git_repository,
    save_git_friendly_snapshot,
)

__all__ = [
    "generate_git_commit_message",
    "git_commit_snapshot",
    "git_get_user_info",
    "git_init_snapshot_repo",
    "git_repository_state",
    "is_git_repository",
    "save_git_friendly_snapshot",
]


from cja_auto_sdr.core.lazy import make_getattr

__getattr__ = make_getattr(__name__, __all__, target_module="cja_auto_sdr.generator")
