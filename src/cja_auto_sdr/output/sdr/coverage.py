"""Per-family coverage state and quality audit status shared by the SDR writers.

Pure derivation (no I/O): the generator computes one :class:`SdrCoverage` per
run and every format renders it, so a reader can tell a family that was
collected empty apart from one that was excluded, not requested, or failed,
and can tell "no audit ran" apart from an audit's findings and gate verdict.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Final

import pandas as pd

from cja_auto_sdr.api.quality_policy import (
    count_quality_issues_by_severity,
    has_quality_issues_at_or_above,
    normalize_quality_severity,
)

COVERAGE_SHEET_NAME: Final = "Coverage"
COVERAGE_COLUMNS: Final = ("Family", "State", "Count", "Detail")
DATA_QUALITY_SECTION: Final = "Data Quality"

# Report order, with the section/sheet heading for each family.
FAMILY_HEADINGS: Final[dict[str, str]] = {
    "metrics": "Metrics",
    "dimensions": "Dimensions",
    "derived_fields": "Derived Fields",
    "calculated_metrics": "Calculated Metrics",
    "segments": "Segments",
}

# Inventory families keyed by the generator's inventory status keys.
_INVENTORY_FAMILIES: Final[dict[str, str]] = {
    "derived_fields": "derived",
    "calculated_metrics": "calculated",
    "segments": "segments",
}
_INVENTORY_FLAGS: Final[dict[str, str]] = {
    "derived_fields": "--include-derived",
    "calculated_metrics": "--include-calculated",
    "segments": "--include-segments",
}

GATE_PASS: Final = "PASS"  # noqa: S105 - gate verdict, not a credential
GATE_FAIL: Final = "FAIL"
GATE_NOT_EVALUATED: Final = "NOT_EVALUATED"


class CoverageState(StrEnum):
    COLLECTED = "collected"
    COLLECTED_EMPTY = "collected_empty"
    EXCLUDED = "excluded"
    NOT_REQUESTED = "not_requested"
    FAILED = "failed"


_STATE_LABELS: Final[dict[CoverageState, str]] = {
    CoverageState.COLLECTED: "Collected",
    CoverageState.COLLECTED_EMPTY: "Collected — no components",
    CoverageState.EXCLUDED: "Excluded from this run",
    CoverageState.NOT_REQUESTED: "Not requested",
    CoverageState.FAILED: "Fetch failed",
}


class QualityState(StrEnum):
    RAN = "ran"
    SKIPPED = "skipped"
    FAILED = "failed"
    NOT_RUN = "not_run"


_VALIDATION_STATUS_TO_QUALITY: Final[dict[str, QualityState]] = {
    "completed": QualityState.RAN,
    "skipped": QualityState.SKIPPED,
    "failed": QualityState.FAILED,
}


@dataclass(frozen=True, slots=True)
class CoverageRow:
    family: str
    state: CoverageState
    count: int | None
    note: str = ""

    @property
    def heading(self) -> str:
        return FAMILY_HEADINGS[self.family]

    @property
    def label(self) -> str:
        return _STATE_LABELS[self.state]

    @property
    def detail(self) -> str:
        """Human-readable state, with the reason when one applies."""
        if self.state is CoverageState.FAILED:
            text = "Fetch failed: unavailable — not an empty result"
            return f"{text} ({self.note})" if self.note else text
        return f"{self.label} ({self.note})" if self.note else self.label

    def to_json(self) -> dict[str, Any]:
        return {"family": self.family, "state": self.state.value, "count": self.count, "detail": self.detail}


@dataclass(frozen=True, slots=True)
class QualityStatus:
    state: QualityState
    status_detail: str = ""
    issue_count: int | None = None
    severity_counts: dict[str, int] = field(default_factory=dict)
    gate_threshold: str | None = None
    gate_verdict: str | None = None

    @property
    def line(self) -> str:
        """One-sentence quality status for report readers."""
        match self.state:
            case QualityState.RAN:
                count = self.issue_count or 0
                if count == 0:
                    text = "Quality audit ran: no issues found."
                else:
                    noun = "issue" if count == 1 else "issues"
                    counts = ", ".join(f"{sev}: {n}" for sev, n in self.severity_counts.items())
                    text = f"Quality audit ran: {count} {noun} ({counts})."
            case QualityState.SKIPPED:
                reason = _skip_reason(self.status_detail)
                text = f"Quality audit skipped: {reason}." if reason else "Quality audit skipped."
            case QualityState.FAILED:
                text = f"Quality audit failed: {self.status_detail or 'validation failed'}."
            case _:
                text = "No quality audit ran."
        if self.gate_threshold is not None:
            if self.gate_verdict == GATE_NOT_EVALUATED:
                text += f" Quality gate at threshold {self.gate_threshold} not evaluated."
            else:
                text += f" Quality gate {self.gate_verdict} at threshold {self.gate_threshold}."
        return text

    def metadata_rows(self) -> list[tuple[str, str]]:
        """Metadata rows for the gate, only when ``--fail-on-quality`` was requested."""
        if self.gate_threshold is None:
            return []
        return [
            ("Quality Gate Verdict", str(self.gate_verdict)),
            ("Quality Gate Threshold", self.gate_threshold),
        ]

    def to_json(self) -> dict[str, Any]:
        gate = None
        if self.gate_threshold is not None:
            gate = {"threshold": self.gate_threshold, "verdict": self.gate_verdict}
        return {
            "state": self.state.value,
            "detail": self.line,
            "issue_count": self.issue_count,
            "severity_counts": dict(self.severity_counts),
            "gate": gate,
        }


@dataclass(frozen=True, slots=True)
class SdrCoverage:
    rows: tuple[CoverageRow, ...]
    quality: QualityStatus

    @property
    def collected_components(self) -> tuple[str, ...]:
        """Families the run requested; a failed family is still listed."""
        return tuple(
            row.family for row in self.rows if row.state not in (CoverageState.EXCLUDED, CoverageState.NOT_REQUESTED)
        )

    def to_frame(self) -> pd.DataFrame:
        records = [(row.heading, row.state.value, row.count, row.detail) for row in self.rows]
        records.append((DATA_QUALITY_SECTION, self.quality.state.value, self.quality.issue_count, self.quality.line))
        return pd.DataFrame(records, columns=list(COVERAGE_COLUMNS)).astype({"Count": "object"})

    def to_json(self) -> dict[str, Any]:
        return {"families": [row.to_json() for row in self.rows], "quality": self.quality.to_json()}


def _skip_reason(detail: str) -> str:
    text = (detail or "").strip()
    if text.startswith("Skipped (") and text.endswith(")"):
        return text[len("Skipped (") : -1]
    if text in ("", "Skipped"):
        return ""
    return text


def _status_field(status: Any, name: str) -> str:
    value = status.get(name) if isinstance(status, Mapping) else getattr(status, name, None)
    return str(value or "")


def excluded_standard_families(
    *,
    metrics_only: bool,
    dimensions_only: bool,
    inventory_only: bool = False,
) -> dict[str, str]:
    """Return ``{family: flag}`` for standard families this run leaves out.

    Both component filters together keep both families, matching the
    required-endpoint policy.
    """
    if inventory_only:
        return {"metrics": "--inventory-only", "dimensions": "--inventory-only"}
    if metrics_only and dimensions_only:
        return {}
    if metrics_only:
        return {"dimensions": "--metrics-only"}
    if dimensions_only:
        return {"metrics": "--dimensions-only"}
    return {}


def quality_gate_verdict(issues: Sequence[Mapping[str, Any]], threshold: str) -> str:
    """Return the ``--fail-on-quality`` verdict using the run-level gate predicate."""
    return GATE_FAIL if has_quality_issues_at_or_above(list(issues), threshold) else GATE_PASS


def _quality_status(
    *,
    validation_status: str | None,
    validation_status_detail: str,
    dq_issues: Sequence[Mapping[str, Any]],
    fail_on_quality: str | None,
) -> QualityStatus:
    state = _VALIDATION_STATUS_TO_QUALITY.get(str(validation_status or "").lower(), QualityState.NOT_RUN)
    issue_count: int | None = None
    severity_counts: dict[str, int] = {}
    if state is QualityState.RAN:
        issue_count = len(dq_issues)
        severity_counts = count_quality_issues_by_severity(list(dq_issues))
    threshold = normalize_quality_severity(fail_on_quality) if fail_on_quality else None
    verdict = None
    if threshold is not None:
        verdict = quality_gate_verdict(dq_issues, threshold) if state is QualityState.RAN else GATE_NOT_EVALUATED
    return QualityStatus(
        state=state,
        status_detail=validation_status_detail or "",
        issue_count=issue_count,
        severity_counts=severity_counts,
        gate_threshold=threshold,
        gate_verdict=verdict,
    )


def build_sdr_coverage(
    *,
    metrics_count: int,
    dimensions_count: int,
    metrics_only: bool = False,
    dimensions_only: bool = False,
    inventory_only: bool = False,
    fetch_statuses: Mapping[str, Any] | None = None,
    inventory_statuses: Mapping[str, str] | None = None,
    inventory_counts: Mapping[str, int] | None = None,
    validation_status: str | None = None,
    validation_status_detail: str = "",
    dq_issues: Sequence[Mapping[str, Any]] = (),
    fail_on_quality: str | None = None,
) -> SdrCoverage:
    """Compute per-family coverage rows and the quality status for one SDR run."""
    fetch_statuses = fetch_statuses or {}
    inventory_statuses = inventory_statuses or {}
    inventory_counts = inventory_counts or {}
    excluded = excluded_standard_families(
        metrics_only=metrics_only,
        dimensions_only=dimensions_only,
        inventory_only=inventory_only,
    )
    standard_counts = {"metrics": metrics_count, "dimensions": dimensions_count}

    rows: list[CoverageRow] = []
    for family in FAMILY_HEADINGS:
        if family in standard_counts:
            status = fetch_statuses.get(family)
            if family in excluded:
                row = CoverageRow(family, CoverageState.EXCLUDED, None, f"by {excluded[family]}")
            elif status is not None and _status_field(status, "status").lower() == "failed":
                note = _status_field(status, "error_message") or _status_field(status, "reason")
                row = CoverageRow(family, CoverageState.FAILED, None, note)
            else:
                count = int(standard_counts[family])
                state = CoverageState.COLLECTED if count else CoverageState.COLLECTED_EMPTY
                row = CoverageRow(family, state, count)
        else:
            key = _INVENTORY_FAMILIES[family]
            status = str(inventory_statuses.get(key, "not_requested")).lower()
            if status == "failed":
                row = CoverageRow(family, CoverageState.FAILED, None, "inventory collection failed; see logs")
            elif status == "completed":
                count = int(inventory_counts.get(key, 0) or 0)
                state = CoverageState.COLLECTED if count else CoverageState.COLLECTED_EMPTY
                row = CoverageRow(family, state, count)
            else:
                row = CoverageRow(family, CoverageState.NOT_REQUESTED, None, f"use {_INVENTORY_FLAGS[family]}")
        rows.append(row)

    quality = _quality_status(
        validation_status=validation_status,
        validation_status_detail=validation_status_detail,
        dq_issues=dq_issues,
        fail_on_quality=fail_on_quality,
    )
    return SdrCoverage(rows=tuple(rows), quality=quality)


def coverage_section_labels(data_dict: Mapping[str, pd.DataFrame]) -> dict[str, str]:
    """Map section names to their coverage detail, read from the ``Coverage`` sheet.

    Writers use this to label empty sections with the family's state instead of
    generic "no data" text. Returns ``{}`` when the run produced no coverage sheet.
    """
    frame = data_dict.get(COVERAGE_SHEET_NAME)
    if not isinstance(frame, pd.DataFrame) or frame.empty or not {"Family", "Detail"} <= set(frame.columns):
        return {}
    return {str(family): str(detail) for family, detail in zip(frame["Family"], frame["Detail"], strict=True)}
