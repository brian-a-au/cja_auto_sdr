"""Quality policy loading, validation, severity helpers, and report output."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd

from cja_auto_sdr.core.constants import QUALITY_SEVERITY_ORDER, QUALITY_SEVERITY_RANK

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

QUALITY_REPORT_PREFERRED_COLUMNS: tuple[str, ...] = (
    "Data View ID",
    "Data View Name",
    "Severity",
    "Category",
    "Type",
    "Item Name",
    "Issue",
    "Details",
)
QUALITY_POLICY_ALLOWED_KEYS: frozenset[str] = frozenset(
    {
        "fail_on_quality",
        "quality_report",
        "max_issues",
        "allow_partial",
    },
)

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _canonical_quality_policy_key(raw_key: Any) -> str:
    """Normalize policy keys so `fail-on-quality` and `fail_on_quality` are equivalent."""
    return str(raw_key).strip().lower().replace("-", "_")


def _parse_non_negative_policy_int(value: Any, *, key: str) -> int:
    """Validate a quality policy integer field.

    Strictly accepts JSON integer values (rejects bool, float, and string
    coercions) to keep policy contracts explicit and predictable.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"quality policy '{key}' must be an integer >= 0")
    if value < 0:
        raise ValueError(f"quality policy '{key}' must be >= 0")
    return value


def _parse_boolean_policy_flag(value: Any, *, key: str) -> bool:
    """Validate a quality policy boolean field."""
    if not isinstance(value, bool):
        raise ValueError(f"quality policy '{key}' must be a boolean")
    return value


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_quality_policy(policy_file: str | Path) -> dict[str, Any]:
    """Load and validate quality policy JSON file."""
    policy_path = Path(policy_file).expanduser()
    if not policy_path.exists():
        raise FileNotFoundError(f"Policy file not found: {policy_path}")

    with open(policy_path, encoding="utf-8") as f:
        payload = json.load(f)

    if not isinstance(payload, dict):
        raise ValueError("Quality policy must be a JSON object")

    # Allow either flat policy or nested payloads.
    if isinstance(payload.get("quality_policy"), dict):
        payload = payload["quality_policy"]
    elif isinstance(payload.get("quality"), dict):
        payload = payload["quality"]

    normalized_payload = {_canonical_quality_policy_key(key): value for key, value in payload.items()}
    unknown_keys = sorted(set(normalized_payload) - QUALITY_POLICY_ALLOWED_KEYS)
    if unknown_keys:
        raise ValueError(f"Unsupported quality policy key(s): {', '.join(unknown_keys)}")

    normalized_policy: dict[str, Any] = {}

    if "fail_on_quality" in normalized_payload:
        raw_severity = normalized_payload["fail_on_quality"]
        if raw_severity is None or not str(raw_severity).strip():
            raise ValueError("quality policy 'fail_on_quality' cannot be empty")
        normalized_policy["fail_on_quality"] = normalize_quality_severity(str(raw_severity).strip())

    if "quality_report" in normalized_payload:
        report_format = str(normalized_payload["quality_report"]).strip().lower()
        if report_format not in ("json", "csv"):
            raise ValueError("quality policy 'quality_report' must be 'json' or 'csv'")
        normalized_policy["quality_report"] = report_format

    if "max_issues" in normalized_payload:
        normalized_policy["max_issues"] = _parse_non_negative_policy_int(
            normalized_payload["max_issues"],
            key="max_issues",
        )

    if "allow_partial" in normalized_payload:
        normalized_policy["allow_partial"] = _parse_boolean_policy_flag(
            normalized_payload["allow_partial"],
            key="allow_partial",
        )

    if normalized_policy.get("allow_partial", False) and (
        "fail_on_quality" in normalized_policy or "quality_report" in normalized_policy
    ):
        raise ValueError("quality policy 'allow_partial' cannot be combined with fail_on_quality or quality_report")

    return normalized_policy


def apply_quality_policy_defaults(
    args: argparse.Namespace,
    policy: dict[str, Any],
    argv: list[str] | None = None,
) -> dict[str, Any]:
    """Apply quality policy values only when the corresponding CLI flags were not explicitly set."""
    # Late import to avoid circular dependency — _cli_option_specified lives in
    # generator.py alongside the CLI dispatch layer.
    from cja_auto_sdr.generator import _cli_option_specified

    applied: dict[str, Any] = {}
    fail_on_quality_cli = _cli_option_specified("--fail-on-quality", argv)
    quality_report_cli = _cli_option_specified("--quality-report", argv)
    max_issues_cli = _cli_option_specified("--max-issues", argv)
    allow_partial_cli = _cli_option_specified("--allow-partial", argv)

    # Honor explicit CLI mutually-exclusive quality-mode choices first.
    if "fail_on_quality" in policy and not fail_on_quality_cli and not allow_partial_cli:
        args.fail_on_quality = policy["fail_on_quality"]
        applied["fail_on_quality"] = policy["fail_on_quality"]

    if "quality_report" in policy and not quality_report_cli and not allow_partial_cli:
        args.quality_report = policy["quality_report"]
        applied["quality_report"] = policy["quality_report"]

    if "max_issues" in policy and not max_issues_cli:
        args.max_issues = policy["max_issues"]
        applied["max_issues"] = policy["max_issues"]

    if "allow_partial" in policy and not allow_partial_cli and not fail_on_quality_cli and not quality_report_cli:
        args.allow_partial = policy["allow_partial"]
        applied["allow_partial"] = policy["allow_partial"]

    return applied


def normalize_quality_severity(severity: str) -> str:
    """Normalize severity input and validate against supported values."""
    normalized = severity.upper()
    if normalized not in QUALITY_SEVERITY_RANK:
        raise ValueError(f"Invalid quality severity: {severity}")
    return normalized


def count_quality_issues_by_severity(issues: list[dict[str, Any]]) -> dict[str, int]:
    """Count quality issues by severity in canonical order."""
    counts = dict.fromkeys(QUALITY_SEVERITY_ORDER, 0)
    for issue in issues:
        severity = str(issue.get("Severity", "")).upper()
        if severity in counts:
            counts[severity] += 1
    return {severity: count for severity, count in counts.items() if count > 0}


def has_quality_issues_at_or_above(issues: list[dict[str, Any]], threshold: str) -> bool:
    """Return True if at least one issue meets/exceeds the configured severity."""
    threshold_rank = QUALITY_SEVERITY_RANK[normalize_quality_severity(threshold)]
    for issue in issues:
        severity = str(issue.get("Severity", "")).upper()
        if severity in QUALITY_SEVERITY_RANK and QUALITY_SEVERITY_RANK[severity] <= threshold_rank:
            return True
    return False


def _build_quality_report_dataframe(issues: list[dict[str, Any]]) -> pd.DataFrame:
    """Build quality report dataframe with stable columns for empty/non-empty output."""
    if not issues:
        return pd.DataFrame(columns=list(QUALITY_REPORT_PREFERRED_COLUMNS))

    df = pd.DataFrame(issues)
    preferred_cols = [col for col in QUALITY_REPORT_PREFERRED_COLUMNS if col in df.columns]
    preferred_set = set(preferred_cols)
    other_cols = [col for col in df.columns if col not in preferred_set]
    return df[preferred_cols + other_cols]


def write_quality_report_output(
    issues: list[dict[str, Any]],
    report_format: str,
    output: str | None,
    output_dir: str | Path,
) -> str:
    """Write standalone quality report in JSON or CSV format."""
    output_to_stdout = output in ("-", "stdout")
    report_format = report_format.lower()

    if report_format not in ("json", "csv"):
        raise ValueError(f"Unsupported quality report format: {report_format}")

    issues_df = _build_quality_report_dataframe(issues)

    if output_to_stdout:
        if report_format == "json":
            json.dump(issues, sys.stdout, indent=2, ensure_ascii=False)
            print()
        else:
            issues_df.to_csv(sys.stdout, index=False)
        return "stdout"

    if output:
        output_path = Path(output)
    else:
        timestamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
        output_path = Path(output_dir) / f"quality_report_{timestamp}.{report_format}"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    if report_format == "json":
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(issues, f, indent=2, ensure_ascii=False)
    else:
        issues_df.to_csv(output_path, index=False, encoding="utf-8")

    return str(output_path)
