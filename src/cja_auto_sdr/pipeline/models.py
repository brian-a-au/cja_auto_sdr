"""Pipeline data models for single and batch SDR processing."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from cja_auto_sdr.api.cache import SharedValidationCache
from cja_auto_sdr.core.config import APITuningConfig, CircuitBreakerConfig

ValidationIssue = dict[str, Any]

__all__ = [
    "BatchConfig",
    "ProcessingConfig",
    "ProcessingResult",
    "WorkerArgs",
]


def _generator_module():
    from cja_auto_sdr import generator as _generator

    return _generator


@dataclass
class ProcessingResult:
    """Result of processing a single data view."""

    data_view_id: str
    data_view_name: str
    success: bool
    duration: float
    metrics_count: int = 0
    dimensions_count: int = 0
    dq_issues_count: int = 0
    dq_issues: list[ValidationIssue] = field(default_factory=list)
    dq_severity_counts: dict[str, int] = field(default_factory=dict)
    output_file: str = ""
    output_files: list[str] = field(default_factory=list)
    error_message: str = ""
    failure_code: str = ""
    failure_reason: str = ""
    partial_output: bool = False
    partial_reasons: list[str] = field(default_factory=list)
    file_size_bytes: int = 0
    segments_count: int = 0
    segments_high_complexity: int = 0
    calculated_metrics_count: int = 0
    calculated_metrics_high_complexity: int = 0
    derived_fields_count: int = 0
    derived_fields_high_complexity: int = 0

    def __post_init__(self) -> None:
        """Normalize output and partial-run observability fields."""
        generator = _generator_module()
        self.output_file, self.output_files = generator._normalize_output_artifact_state(
            self.output_file,
            self.output_files,
        )
        self.partial_output, self.partial_reasons = generator._normalize_partial_state(
            self.partial_output,
            self.partial_reasons,
        )

    @property
    def file_size_formatted(self) -> str:
        """Return human-readable file size (for example, ``1.5 MB``)."""
        return _generator_module().format_file_size(self.file_size_bytes)

    @property
    def emitted_output_files(self) -> list[str]:
        """Return the normalized emitted artifact list."""
        return list(self.output_files)

    @property
    def has_inventory(self) -> bool:
        """Check if any inventory data was collected."""
        return self.segments_count > 0 or self.calculated_metrics_count > 0 or self.derived_fields_count > 0

    @property
    def total_high_complexity(self) -> int:
        """Total count of high-complexity items across all inventories."""
        return (
            self.segments_high_complexity
            + self.calculated_metrics_high_complexity
            + self.derived_fields_high_complexity
        )


@dataclass
class WorkerArgs:
    """Arguments for ``process_single_dataview_worker``."""

    data_view_id: str
    config_file: str = "config.json"
    output_dir: str = "."
    log_level: str = "INFO"
    log_format: str = "text"
    output_format: str = "excel"
    enable_cache: bool = False
    cache_size: int = 1000
    cache_ttl: int = 3600
    quiet: bool = False
    skip_validation: bool = False
    max_issues: int = 0
    clear_cache: bool = False
    show_timings: bool = False
    metrics_only: bool = False
    dimensions_only: bool = False
    profile: str | None = None
    shared_cache: SharedValidationCache | None = None
    api_tuning_config: APITuningConfig | None = None
    circuit_breaker_config: CircuitBreakerConfig | None = None
    include_derived_inventory: bool = False
    include_calculated_metrics: bool = False
    include_segments_inventory: bool = False
    inventory_only: bool = False
    inventory_order: list[str] | None = None
    quality_report_only: bool = False
    allow_partial: bool = False
    production_mode: bool = False
    batch_id: str | None = None


@dataclass(frozen=True)
class ProcessingConfig:
    """Configuration bundle for single data view processing."""

    config_file: str = "config.json"
    output_dir: str | Path = "."
    log_level: str = "INFO"
    log_format: str = "text"
    output_format: str = "excel"
    enable_cache: bool = False
    cache_size: int = 1000
    cache_ttl: int = 3600
    quiet: bool = False
    skip_validation: bool = False
    max_issues: int = 0
    clear_cache: bool = False
    show_timings: bool = False
    metrics_only: bool = False
    dimensions_only: bool = False
    profile: str | None = None
    shared_cache: SharedValidationCache | None = None
    api_tuning_config: APITuningConfig | None = None
    circuit_breaker_config: CircuitBreakerConfig | None = None
    include_derived_inventory: bool = False
    include_calculated_metrics: bool = False
    include_segments_inventory: bool = False
    inventory_only: bool = False
    inventory_order: list[str] | None = None
    quality_report_only: bool = False
    allow_partial: bool = False
    production_mode: bool = False
    batch_id: str | None = None


@dataclass(frozen=True)
class BatchConfig:
    """Configuration bundle for batch processing."""

    config_file: str = "config.json"
    output_dir: str = "."
    workers: int = 4
    continue_on_error: bool = False
    log_level: str = "INFO"
    log_format: str = "text"
    output_format: str = "excel"
    enable_cache: bool = False
    cache_size: int = 1000
    cache_ttl: int = 3600
    quiet: bool = False
    skip_validation: bool = False
    max_issues: int = 0
    clear_cache: bool = False
    show_timings: bool = False
    metrics_only: bool = False
    dimensions_only: bool = False
    profile: str | None = None
    shared_cache: bool = False
    api_tuning_config: APITuningConfig | None = None
    circuit_breaker_config: CircuitBreakerConfig | None = None
    include_derived_inventory: bool = False
    include_calculated_metrics: bool = False
    include_segments_inventory: bool = False
    inventory_only: bool = False
    inventory_order: list[str] | None = None
    quality_report_only: bool = False
    allow_partial: bool = False
    production_mode: bool = False
