# src/cja_auto_sdr/core/advisories.py
"""Advisory data model for machine-readable interpretation of org/diff results.

Advisories are a derived convenience layer over existing JSON fields. They help
agents branch faster without hiding or replacing the base data.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

_ADVISORY_SEVERITY_ORDER = ("info", "warning", "critical")


@dataclass
class AdvisoryFinding:
    """A single advisory finding derived from existing result data."""

    type: str
    severity: str  # "info" | "warning" | "critical"
    message: str
    details: dict[str, Any]
    recommended_actions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "type": self.type,
            "severity": self.severity,
            "message": self.message,
            "details": self.details,
            "recommended_actions": self.recommended_actions,
        }


@dataclass
class AdvisorySummary:
    """Versioned advisory summary block for JSON output."""

    advisories_version: str  # "1.0"
    severity: str
    findings: list[AdvisoryFinding]
    summary: dict[str, Any]  # {"total_findings": N, "by_severity": {...}}

    def to_dict(self) -> dict[str, Any]:
        return {
            "advisories_version": self.advisories_version,
            "severity": self.severity,
            "findings": [f.to_dict() for f in self.findings],
            "summary": self.summary,
        }
