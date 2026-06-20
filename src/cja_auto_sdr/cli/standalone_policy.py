"""Shared standalone prevalidation policy metadata.

This module is intentionally lightweight so both ``generator.py`` and the
fast-path entrypoint in ``__main__.py`` can consume the same standalone-mode
policy definitions without importing the full generator stack.
"""

from __future__ import annotations

from dataclasses import dataclass

from cja_auto_sdr.cli.mode_scoped_options import org_report_mode_scoped_dests

_STANDALONE_FAST_PATH_METADATA_DESTS = frozenset({"agent_mode", "config_file", "format", "output_dir", "profile"})
_ORG_REPORT_MODE_SCOPED_DESTS = org_report_mode_scoped_dests()

_WRAPPER_EXECUTION_TOLERATED_SEMANTIC_DESTS = frozenset(
    {
        "auto_prune",
        "auto_snapshot",
        "skip_validation",
    },
)
_INFORMATIONAL_MODE_TOLERATED_SEMANTIC_DESTS = (
    frozenset(
        {
            "allow_partial",
            "fail_on_quality",
            "quality_report",
        }
    )
    | _WRAPPER_EXECUTION_TOLERATED_SEMANTIC_DESTS
)


@dataclass(frozen=True)
class StandalonePrevalidationPolicy:
    """Standalone-mode semantic-validation policy before early dispatch."""

    ignored_semantic_dests: frozenset[str] = frozenset()
    validate_org_report_mode_scoped_options: bool = True

    def tolerated_fast_path_dests(self) -> frozenset[str]:
        """Return parser dests that should not disable the standalone fast path."""
        tolerated = set(_STANDALONE_FAST_PATH_METADATA_DESTS)
        tolerated.update(self.ignored_semantic_dests)
        tolerated.add("quality_policy")
        if not self.validate_org_report_mode_scoped_options:
            tolerated.update(_ORG_REPORT_MODE_SCOPED_DESTS)
        return frozenset(tolerated)


_INFORMATIONAL_STANDALONE_POLICY = StandalonePrevalidationPolicy(
    ignored_semantic_dests=_INFORMATIONAL_MODE_TOLERATED_SEMANTIC_DESTS,
)
_COMPLETION_STANDALONE_POLICY = StandalonePrevalidationPolicy(
    ignored_semantic_dests=_INFORMATIONAL_MODE_TOLERATED_SEMANTIC_DESTS,
    validate_org_report_mode_scoped_options=False,
)
_SAMPLE_CONFIG_STANDALONE_POLICY = StandalonePrevalidationPolicy(
    ignored_semantic_dests=_WRAPPER_EXECUTION_TOLERATED_SEMANTIC_DESTS,
)
_PUSH_TO_NOTION_STANDALONE_POLICY = StandalonePrevalidationPolicy(
    ignored_semantic_dests=(
        frozenset({"notion_force_new", "notion_database_id", "notion_create_database"})
        | _WRAPPER_EXECUTION_TOLERATED_SEMANTIC_DESTS
    ),
    validate_org_report_mode_scoped_options=False,
)

_STANDALONE_PREVALIDATION_POLICIES: dict[str, StandalonePrevalidationPolicy] = {
    "completion": _COMPLETION_STANDALONE_POLICY,
    "explain_exit_code": _INFORMATIONAL_STANDALONE_POLICY,
    "exit_codes": _INFORMATIONAL_STANDALONE_POLICY,
    "sample_config": _SAMPLE_CONFIG_STANDALONE_POLICY,
    "push_to_notion": _PUSH_TO_NOTION_STANDALONE_POLICY,
}


def standalone_prevalidation_policy(mode: str) -> StandalonePrevalidationPolicy | None:
    """Return standalone semantic-validation policy for the given run-mode name."""
    return _STANDALONE_PREVALIDATION_POLICIES.get(mode)
