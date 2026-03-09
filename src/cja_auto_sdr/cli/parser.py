"""CLI argument parsing for CJA Auto SDR.

Contains the ``parse_arguments`` function and its helpers.  Extracted from
``generator.py`` so that the CLI definition lives in the ``cli`` subpackage
while the rest of the generator focuses on data processing.
"""

from __future__ import annotations

import argparse
import logging
import os
from collections.abc import Callable

from cja_auto_sdr.core.constants import (
    DEFAULT_AUTO_PRUNE_KEEP_LAST,
    DEFAULT_AUTO_PRUNE_KEEP_SINCE,
    DEFAULT_CACHE_SIZE,
    DEFAULT_CACHE_TTL,
    DEFAULT_RETRY_CONFIG,
    MAX_BATCH_WORKERS,
    QUALITY_SEVERITY_ORDER,
)
from cja_auto_sdr.core.version import __version__

# Attempt to load argcomplete for shell tab-completion (optional dependency)
_ARGCOMPLETE_AVAILABLE = False
try:
    import argcomplete

    _ARGCOMPLETE_AVAILABLE = True  # pragma: no cover
except ImportError:
    pass  # argcomplete not installed


def _bounded_float(min_val: float, max_val: float):
    """Argparse type factory for a float bounded to [min_val, max_val]."""

    def _type(value: str) -> float:
        f = float(value)
        if f < min_val or f > max_val:
            raise argparse.ArgumentTypeError(f"must be between {min_val} and {max_val}, got {f}")
        return f

    _type.__name__ = f"float[{min_val}-{max_val}]"
    return _type


def _safe_env_number(env_var: str, default: int | float, cast: Callable[[str], int | float]) -> int | float:
    """Read a numeric env var and fall back to default when invalid."""
    raw = os.environ.get(env_var)
    if raw is None:
        return default
    try:
        return cast(raw)
    except TypeError, ValueError:
        return default


def parse_arguments(
    argv: list[str] | None = None,
    *,
    return_parser: bool = False,
    enable_autocomplete: bool = True,
) -> argparse.Namespace | argparse.ArgumentParser:
    """Build and parse CLI arguments.

    Args:
        argv: Optional argv list to parse. Defaults to sys.argv when None.
        return_parser: When True, return the configured parser without parsing.
        enable_autocomplete: Enable argcomplete integration when available.
    """
    # Load .env before reading any os.environ-backed defaults so options like
    # --output-dir, --log-level, --max-retries, and --profile honor .env values.
    # Skip this in return_parser mode because callers typically need parser
    # metadata only (option discovery/introspection) and should remain
    # lightweight without importing API/bootstrap dependencies.
    if not return_parser:
        from cja_auto_sdr.api.client import _bootstrap_dotenv

        _bootstrap_dotenv(logging.getLogger(__name__))

    parser = argparse.ArgumentParser(
        description="CJA SDR Generator - Generate Solution Design Reference for CJA Data Views",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single data view
  cja_auto_sdr dv_12345

  # Multiple data views (automatically triggers parallel processing)
  cja_auto_sdr dv_12345 dv_67890 dv_abcde

  # Batch processing with explicit flag (same as above)
  cja_auto_sdr --batch dv_12345 dv_67890 dv_abcde

  # Auto-detect optimal workers (default)
  cja_auto_sdr --batch dv_12345 dv_67890 --workers auto

  # Or specify explicit worker count
  cja_auto_sdr --batch dv_12345 dv_67890 --workers 2

  # Custom output directory
  cja_auto_sdr dv_12345 --output-dir ./reports

  # Continue on errors
  cja_auto_sdr --batch dv_* --continue-on-error

  # With custom log level
  cja_auto_sdr --batch dv_* --log-level WARNING

  # JSON structured logging (for Splunk, ELK, CloudWatch)
  cja_auto_sdr dv_12345 --log-format json

  # Export as CSV files
  cja_auto_sdr dv_12345 --format csv

  # Export as JSON
  cja_auto_sdr dv_12345 --format json

  # Export as HTML
  cja_auto_sdr dv_12345 --format html

  # Export as Markdown (GitHub/Confluence)
  cja_auto_sdr dv_12345 --format markdown

  # Export in all formats
  cja_auto_sdr dv_12345 --format all

  # Dry-run to validate config and connectivity
  cja_auto_sdr dv_12345 --dry-run

  # Quiet mode (errors only)
  cja_auto_sdr dv_12345 --quiet

  # List all accessible data views
  cja_auto_sdr --list-dataviews

  # Skip data quality validation (faster processing)
  cja_auto_sdr dv_12345 --skip-validation

  # Generate sample configuration file
  cja_auto_sdr --sample-config

  # Limit data quality issues to top 10 by severity
  cja_auto_sdr dv_12345 --max-issues 10

  # Apply reusable quality policy defaults from file
  cja_auto_sdr dv_12345 --quality-policy ./quality_policy.json

  # Validate only (alias for --dry-run)
  cja_auto_sdr dv_12345 --validate-only

  # --- Data View Comparison (Diff) ---

  # Compare two live data views
  cja_auto_sdr --diff dv_prod_12345 dv_staging_67890
  cja_auto_sdr --diff "Production Analytics" "Staging Analytics"

  # Save a snapshot for later comparison
  cja_auto_sdr dv_12345 --snapshot ./snapshots/baseline.json

  # Compare current state against a saved snapshot
  cja_auto_sdr dv_12345 --diff-snapshot ./snapshots/baseline.json

  # Diff output options
  cja_auto_sdr --diff dv_A dv_B --format html --output-dir ./reports
  cja_auto_sdr --diff dv_A dv_B --format all
  cja_auto_sdr --diff dv_A dv_B --changes-only
  cja_auto_sdr --diff dv_A dv_B --summary

  # Advanced diff options
  cja_auto_sdr --diff dv_A dv_B --ignore-fields description,title
  cja_auto_sdr --diff dv_A dv_B --diff-labels Production Staging

  # Auto-snapshot: automatically save snapshots during diff for audit trail
  cja_auto_sdr --diff dv_A dv_B --auto-snapshot
  cja_auto_sdr --diff dv_A dv_B --auto-snapshot --snapshot-dir ./history
  cja_auto_sdr --diff dv_A dv_B --auto-snapshot --keep-last 10

  # --- Quick UX Features ---

  # Quick stats without full report
  cja_auto_sdr dv_12345 --stats
  cja_auto_sdr dv_1 dv_2 dv_3 --stats

  # Stats in JSON format for scripting
  cja_auto_sdr dv_12345 --stats --format json
  cja_auto_sdr dv_12345 --stats --output -    # Output to stdout

  # Open file after generation
  cja_auto_sdr dv_12345 --open

  # List data views in JSON format (for scripting/piping)
  cja_auto_sdr --list-dataviews --format json
  cja_auto_sdr --list-dataviews --output -    # JSON to stdout

  # List connections with their datasets
  cja_auto_sdr --list-connections
  cja_auto_sdr --list-connections --format json
  cja_auto_sdr --list-connections --format csv --output connections.csv

  # List data views with their backing connections and datasets
  cja_auto_sdr --list-datasets
  cja_auto_sdr --list-datasets --format json
  cja_auto_sdr --list-datasets --format csv --output datasets.csv

  # --- Profile Management ---

  # List all available profiles
  cja_auto_sdr --profile-list

  # Use a named profile
  cja_auto_sdr --profile client-a --list-dataviews
  cja_auto_sdr -p client-a "My Data View" --format excel

  # Create a new profile interactively
  cja_auto_sdr --profile-add client-c

  # Test profile credentials
  cja_auto_sdr --profile-test client-a

  # Show profile configuration (secrets masked)
  cja_auto_sdr --profile-show client-a

  # Import profile non-interactively from JSON/.env file
  cja_auto_sdr --profile-import client-d ./client-d.env
  cja_auto_sdr --profile-import client-d ./client-d.json --profile-overwrite

  # Use profile via environment variable
  export CJA_PROFILE=client-a
  cja_auto_sdr --list-dataviews

Note:
  At least one data view ID or name is required for SDR, stats, and diff comparison modes.
  Use 'cja_auto_sdr --help' to see all options.

Exit Codes:
  0 - Success (diff: no differences found)
  1 - Error occurred
  2 - Policy threshold exceeded (diff changes, quality gate, or governance threshold)
  3 - Diff warning threshold exceeded (--warn-threshold)

Requirements:
  Python 3.14 or higher required. Verify with: python3 --version
        """,
    )

    parser.add_argument(
        "--version",
        "-V",
        action="version",
        version=f"%(prog)s {__version__}",
        help="Show program version and exit",
    )

    parser.add_argument("--exit-codes", action="store_true", help="Display exit code reference and exit")

    parser.add_argument(
        "--completion",
        choices=["bash", "zsh", "fish"],
        metavar="SHELL",
        help="Print shell completion activation script for SHELL (bash, zsh, fish) and exit",
    )

    parser.add_argument(
        "data_views",
        nargs="*",
        metavar="DATA_VIEW_ID_OR_NAME",
        help="Data view IDs (e.g., dv_12345) or exact names (use quotes for names with spaces). "
        "If a name matches multiple data views, all will be processed. "
        "At least one required unless using --version, --list-dataviews, etc.",
    )

    parser.add_argument("--batch", action="store_true", help="Enable batch processing mode (parallel execution)")

    parser.add_argument(
        "--workers",
        type=str,
        default="auto",
        help=f"Number of parallel workers for batch mode (1-{MAX_BATCH_WORKERS}). "
        f'Use "auto" (default) for intelligent detection based on CPU cores, '
        f"data view count, and component complexity. Auto-reduces workers for "
        f"large data views (>5K components) to prevent memory exhaustion",
    )

    parser.add_argument(
        "--output-dir",
        type=str,
        default=os.environ.get("OUTPUT_DIR", "."),
        help="Output directory for generated files (default: current directory, or OUTPUT_DIR env var)",
    )

    parser.add_argument(
        "--config-file",
        type=str,
        default="config.json",
        help="Path to CJA configuration file (default: config.json)",
    )

    parser.add_argument(
        "--continue-on-error",
        action="store_true",
        help="Continue processing remaining data views if one fails",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        default=os.environ.get("LOG_LEVEL", "INFO"),
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO, or LOG_LEVEL environment variable)",
    )

    parser.add_argument(
        "--log-format",
        type=str,
        default="text",
        choices=["text", "json"],
        help='Log output format: "text" (default) for human-readable, '
        '"json" for structured logging (Splunk, ELK, CloudWatch compatible)',
    )

    parser.add_argument(
        "--production",
        action="store_true",
        help="Enable production mode (minimal logging for maximum performance)",
    )

    parser.add_argument(
        "--enable-cache",
        action="store_true",
        help="Enable validation result caching (50-90%% faster on repeated validations)",
    )

    parser.add_argument(
        "--clear-cache",
        action="store_true",
        help="Clear validation cache before processing (use with --enable-cache for fresh validation)",
    )

    parser.add_argument(
        "--cache-size",
        type=int,
        default=DEFAULT_CACHE_SIZE,
        help=f"Maximum number of cached validation results (default: {DEFAULT_CACHE_SIZE})",
    )

    parser.add_argument(
        "--cache-ttl",
        type=int,
        default=DEFAULT_CACHE_TTL,
        help=f"Cache time-to-live in seconds (default: {DEFAULT_CACHE_TTL} = 1 hour)",
    )

    parser.add_argument(
        "--max-retries",
        type=int,
        default=int(_safe_env_number("MAX_RETRIES", DEFAULT_RETRY_CONFIG["max_retries"], int)),
        help=f"Maximum API retry attempts (default: {DEFAULT_RETRY_CONFIG['max_retries']}, or MAX_RETRIES env var)",
    )

    parser.add_argument(
        "--retry-base-delay",
        type=float,
        default=float(_safe_env_number("RETRY_BASE_DELAY", DEFAULT_RETRY_CONFIG["base_delay"], float)),
        help=f"Initial retry delay in seconds (default: {DEFAULT_RETRY_CONFIG['base_delay']}, or RETRY_BASE_DELAY env var)",
    )

    parser.add_argument(
        "--retry-max-delay",
        type=float,
        default=float(_safe_env_number("RETRY_MAX_DELAY", DEFAULT_RETRY_CONFIG["max_delay"], float)),
        help=f"Maximum retry delay in seconds (default: {DEFAULT_RETRY_CONFIG['max_delay']}, or RETRY_MAX_DELAY env var)",
    )

    # ==================== RELIABILITY/PERFORMANCE ARGUMENTS ====================

    reliability_group = parser.add_argument_group(
        "Reliability & Performance",
        "Options for API resilience and performance tuning",
    )

    reliability_group.add_argument(
        "--api-auto-tune",
        action="store_true",
        help="Enable automatic API worker tuning based on response times. "
        "Scales workers up when responses are fast, down when slow",
    )

    reliability_group.add_argument(
        "--api-min-workers",
        type=int,
        default=1,
        metavar="N",
        help="Minimum workers for auto-tuning (default: 1, requires --api-auto-tune)",
    )

    reliability_group.add_argument(
        "--api-max-workers",
        type=int,
        default=10,
        metavar="N",
        help="Maximum workers for auto-tuning (default: 10, requires --api-auto-tune)",
    )

    reliability_group.add_argument(
        "--circuit-breaker",
        action="store_true",
        help="Enable circuit breaker pattern for API calls. "
        "Prevents cascading failures by stopping requests after repeated failures",
    )

    reliability_group.add_argument(
        "--circuit-failure-threshold",
        type=int,
        default=5,
        metavar="N",
        help="Consecutive failures before opening circuit (default: 5, requires --circuit-breaker)",
    )

    reliability_group.add_argument(
        "--circuit-timeout",
        type=float,
        default=30.0,
        metavar="SECONDS",
        help="Seconds before attempting recovery from open circuit (default: 30, requires --circuit-breaker)",
    )

    reliability_group.add_argument(
        "--shared-cache",
        action="store_true",
        help="Share validation cache across batch workers (requires --batch and --enable-cache). "
        "Enables cache reuse across data views for common validation patterns",
    )

    parser.add_argument(
        "--format",
        type=str,
        default=None,
        choices=["console", "excel", "csv", "json", "html", "markdown", "all", "reports", "data", "ci"],
        help="Output format: excel, csv, json, html, markdown, all, or aliases (reports=excel+markdown, data=csv+json, ci=json+markdown). Default: excel for SDR, console for diff",
    )

    parser.add_argument(
        "--dry-run",
        "--validate-only",
        action="store_true",
        dest="dry_run",
        help="Validate configuration and connectivity without generating reports",
    )

    parser.add_argument(
        "--quiet",
        "-q",
        action="store_true",
        help="Quiet mode - suppress all output except errors and final summary",
    )

    discovery_group = parser.add_argument_group(
        "Discovery",
        "Commands to explore available CJA resources (mutually exclusive)",
    )
    discovery_mx = discovery_group.add_mutually_exclusive_group()

    discovery_mx.add_argument(
        "--list-dataviews",
        action="store_true",
        help="List all accessible data views and exit (no data view ID required)",
    )

    discovery_mx.add_argument(
        "--list-connections",
        action="store_true",
        help="List all accessible connections with their datasets and exit",
    )

    discovery_mx.add_argument(
        "--list-datasets",
        action="store_true",
        help="List all data views with their backing connections and datasets, then exit",
    )

    discovery_mx.add_argument(
        "--describe-dataview",
        type=str,
        metavar="DATA_VIEW_ID_OR_NAME",
        help="Show detailed metadata and component counts for a single data view. Accepts a data view ID (dv_...) or name. Honors --name-match.",
    )

    discovery_mx.add_argument(
        "--list-metrics",
        type=str,
        metavar="DATA_VIEW_ID_OR_NAME",
        help="List all metrics in a data view (supports --filter, --exclude, --sort, --limit). Accepts a data view ID (dv_...) or name. Honors --name-match.",
    )

    discovery_mx.add_argument(
        "--list-dimensions",
        type=str,
        metavar="DATA_VIEW_ID_OR_NAME",
        help="List all dimensions in a data view (supports --filter, --exclude, --sort, --limit). Accepts a data view ID (dv_...) or name. Honors --name-match.",
    )

    discovery_mx.add_argument(
        "--list-segments",
        type=str,
        metavar="DATA_VIEW_ID_OR_NAME",
        help="List all segments/filters scoped to a data view (supports --filter, --exclude, --sort, --limit). Accepts a data view ID (dv_...) or name. Honors --name-match.",
    )

    discovery_mx.add_argument(
        "--list-calculated-metrics",
        type=str,
        metavar="DATA_VIEW_ID_OR_NAME",
        help="List all calculated metrics for a data view (supports --filter, --exclude, --sort, --limit). Accepts a data view ID (dv_...) or name. Honors --name-match.",
    )

    parser.add_argument(
        "--sort",
        type=str,
        dest="discovery_sort",
        metavar="FIELD",
        help='Sort discovery output by field (prefix "-" for descending), e.g. --sort name or --sort=-id',
    )

    parser.add_argument(
        "--skip-validation",
        action="store_true",
        help="Skip data quality validation for faster processing (20-30%% faster)",
    )

    parser.add_argument("--sample-config", action="store_true", help="Generate a sample configuration file and exit")

    parser.add_argument(
        "--validate-config",
        action="store_true",
        help="Validate configuration and API connectivity without processing any data views",
    )

    parser.add_argument(
        "--config-status",
        action="store_true",
        help="Show configuration status (source, fields, masked credentials) without API call. "
        "Faster than --validate-config for quick troubleshooting",
    )

    parser.add_argument(
        "--config-json",
        action="store_true",
        help="Output --config-status as machine-readable JSON (for scripting and CI/CD)",
    )

    parser.add_argument(
        "--yes",
        "-y",
        action="store_true",
        dest="assume_yes",
        help="Skip confirmation prompts (e.g., for large batch operations)",
    )

    parser.add_argument(
        "--max-issues",
        type=int,
        default=0,
        metavar="N",
        help="Limit data quality issues to top N by severity (0 = show all, default: 0)",
    )

    parser.add_argument(
        "--fail-on-quality",
        type=str.upper,
        choices=list(QUALITY_SEVERITY_ORDER),
        metavar="SEVERITY",
        help="Exit with code 2 when quality issues at or above SEVERITY are found (CRITICAL, HIGH, MEDIUM, LOW, INFO)",
    )

    parser.add_argument(
        "--quality-report",
        type=str,
        choices=["json", "csv"],
        metavar="FORMAT",
        help="Generate standalone quality issues report only (json or csv) without SDR files",
    )

    parser.add_argument(
        "--allow-partial",
        action="store_true",
        help="Opt-in exploratory mode: allow partial SDR output when component fetches or validation runtime fail. "
        "Default is strict fail-closed behavior.",
    )

    parser.add_argument(
        "--quality-policy",
        type=str,
        metavar="PATH",
        help="Load quality defaults from JSON file (supported keys: fail_on_quality, quality_report, "
        "max_issues, allow_partial). "
        "Explicit CLI flags take precedence.",
    )

    # ==================== UX ENHANCEMENT ARGUMENTS ====================

    parser.add_argument(
        "--show-timings",
        action="store_true",
        help="Display performance timing breakdown after processing (API calls, validation, output generation)",
    )

    parser.add_argument(
        "--open",
        action="store_true",
        help="Open the generated file(s) in the default application after creation",
    )

    parser.add_argument(
        "--stats",
        action="store_true",
        help="Show quick statistics about data view(s) without generating full reports. "
        "Displays counts of metrics, dimensions, and basic info",
    )

    parser.add_argument(
        "--interactive",
        "-i",
        action="store_true",
        help="Launch interactive mode for guided SDR generation. "
        "Walks through: (1) data view selection, (2) output format, "
        "(3) inventory options (segments, calculated metrics, derived fields). "
        "Ideal for new users or one-off generation tasks",
    )

    parser.add_argument(
        "--name-match",
        type=str,
        choices=["exact", "insensitive", "fuzzy"],
        default="exact",
        help="Data view name matching mode: exact (default), case-insensitive, or fuzzy nearest match",
    )

    parser.add_argument(
        "--output",
        type=str,
        metavar="PATH",
        help='Output file path. Use "-" or "stdout" to write to standard output (JSON/CSV only). '
        "For stdout, implies --quiet to suppress other output",
    )

    parser.add_argument(
        "--run-summary-json",
        type=str,
        metavar="PATH",
        help='Write a machine-readable run summary JSON (all modes). Use "-" or "stdout" for stdout.',
    )

    # ==================== DIFF COMPARISON ARGUMENTS ====================

    diff_group = parser.add_argument_group("Diff Comparison", "Options for comparing data views")

    diff_group.add_argument(
        "--diff",
        action="store_true",
        help="Compare two data views. Provide exactly 2 data view IDs/names as positional arguments",
    )

    diff_group.add_argument(
        "--snapshot",
        type=str,
        metavar="FILE",
        help="Save a snapshot of the data view to a JSON file (use with single data view)",
    )

    diff_group.add_argument(
        "--list-snapshots",
        action="store_true",
        help="List snapshots from --snapshot-dir (optional DATA_VIEW_ID filters via positional args)",
    )

    diff_group.add_argument(
        "--prune-snapshots",
        action="store_true",
        help="Apply retention policies to snapshots in --snapshot-dir without running a diff",
    )

    diff_group.add_argument(
        "--diff-snapshot",
        type=str,
        metavar="FILE",
        help="Compare data view against a saved snapshot file",
    )

    diff_group.add_argument(
        "--compare-with-prev",
        action="store_true",
        help="Compare data view against its most recent snapshot in --snapshot-dir (default: ./snapshots)",
    )

    diff_group.add_argument(
        "--compare-snapshots",
        nargs=2,
        metavar=("SOURCE", "TARGET"),
        help="Compare two snapshot files directly (no API calls required). "
        "Example: --compare-snapshots baseline.json current.json",
    )

    diff_group.add_argument(
        "--changes-only",
        action="store_true",
        help="Only show changed items in diff output (hide unchanged)",
    )

    diff_group.add_argument("--summary", action="store_true", help="Show summary statistics only (no detailed changes)")

    diff_group.add_argument(
        "--ignore-fields",
        type=str,
        metavar="FIELDS",
        help='Comma-separated list of fields to ignore during comparison (e.g., "description,title")',
    )

    diff_group.add_argument(
        "--diff-labels",
        nargs=2,
        metavar=("SOURCE", "TARGET"),
        help="Custom labels for the two sides of the comparison (default: Source, Target)",
    )

    diff_group.add_argument(
        "--show-only",
        type=str,
        metavar="TYPES",
        help="Filter diff output to show only specific change types. "
        'Comma-separated list: added,removed,modified,unchanged (e.g., "added,modified")',
    )

    diff_group.add_argument(
        "--metrics-only",
        action="store_true",
        help="Only include metrics (exclude dimensions). Works for both SDR generation and diff comparison",
    )

    diff_group.add_argument(
        "--dimensions-only",
        action="store_true",
        help="Only include dimensions (exclude metrics). Works for both SDR generation and diff comparison",
    )

    diff_group.add_argument(
        "--extended-fields",
        action="store_true",
        help="Use extended field comparison including attribution, format, bucketing, "
        "persistence settings (default: basic fields only)",
    )

    diff_group.add_argument(
        "--side-by-side",
        action="store_true",
        help="Show side-by-side comparison view for modified items (console and markdown)",
    )

    diff_group.add_argument("--no-color", action="store_true", help="Disable ANSI color codes in console output")

    diff_group.add_argument(
        "--color-theme",
        type=str,
        choices=["default", "accessible"],
        default="default",
        help='Color theme for diff output: "default" (green/red) or "accessible" (blue/orange for accessibility)',
    )

    diff_group.add_argument(
        "--quiet-diff",
        action="store_true",
        help="Suppress diff output, only return exit code (0=no changes, 2=changes found)",
    )

    diff_group.add_argument(
        "--reverse-diff",
        action="store_true",
        help="Reverse the comparison direction (swap source and target)",
    )

    diff_group.add_argument(
        "--warn-threshold",
        type=float,
        metavar="PERCENT",
        help="Exit with code 3 if change percentage exceeds threshold (e.g., --warn-threshold 10)",
    )

    diff_group.add_argument(
        "--group-by-field",
        action="store_true",
        help="Group changes by field name instead of by component",
    )

    diff_group.add_argument(
        "--group-by-field-limit",
        type=int,
        default=10,
        metavar="N",
        help="Max items per section in --group-by-field output (default: 10, 0 = unlimited)",
    )

    diff_group.add_argument(
        "--diff-output",
        type=str,
        metavar="FILE",
        help="Write diff output directly to file instead of stdout",
    )

    diff_group.add_argument(
        "--format-pr-comment",
        action="store_true",
        help="Output in GitHub/GitLab PR comment format (markdown with collapsible details)",
    )

    diff_group.add_argument(
        "--auto-snapshot",
        action="store_true",
        help="Automatically save snapshots of data views during diff comparison. "
        "Creates timestamped snapshots in --snapshot-dir for audit trail",
    )

    diff_group.add_argument(
        "--auto-prune",
        action="store_true",
        help=(
            "When used with --auto-snapshot, automatically apply default retention "
            f"(--keep-last {DEFAULT_AUTO_PRUNE_KEEP_LAST} and --keep-since {DEFAULT_AUTO_PRUNE_KEEP_SINCE}) "
            "if explicit retention flags are not provided"
        ),
    )

    diff_group.add_argument(
        "--snapshot-dir",
        type=str,
        default="./snapshots",
        metavar="DIR",
        help="Directory for auto-saved snapshots (default: ./snapshots). Used with --auto-snapshot",
    )

    diff_group.add_argument(
        "--keep-last",
        type=int,
        default=0,
        metavar="N",
        help="Retention policy: keep only the last N snapshots per data view (0 = keep all). Used with --auto-snapshot",
    )

    diff_group.add_argument(
        "--keep-since",
        type=str,
        default=None,
        metavar="PERIOD",
        help="Date-based retention: delete snapshots older than PERIOD. "
        "Formats: 7d (7 days), 2w (2 weeks), 1m (1 month), 30 (30 days). "
        "Used with --auto-snapshot. Can be combined with --keep-last.",
    )

    # ==================== PROFILE MANAGEMENT ARGUMENTS ====================

    profile_group = parser.add_argument_group(
        "Profile Management",
        "Manage organization/credential profiles stored in ~/.cja/orgs/",
    )

    profile_group.add_argument(
        "--profile",
        "-p",
        type=str,
        metavar="NAME",
        default=os.environ.get("CJA_PROFILE"),
        help="Use named profile from ~/.cja/orgs/<NAME>/. Can also be set via CJA_PROFILE environment variable",
    )

    profile_group.add_argument("--profile-list", action="store_true", help="List all available profiles and exit")

    profile_group.add_argument("--profile-add", type=str, metavar="NAME", help="Create a new profile interactively")

    profile_group.add_argument(
        "--profile-test",
        type=str,
        metavar="NAME",
        help="Test profile credentials and API connectivity",
    )

    profile_group.add_argument(
        "--profile-show",
        type=str,
        metavar="NAME",
        help="Show profile configuration (with masked secrets)",
    )

    profile_group.add_argument(
        "--profile-import",
        nargs=2,
        metavar=("NAME", "FILE"),
        help="Import profile credentials from JSON/.env file (or profile directory) without prompts",
    )

    profile_group.add_argument(
        "--profile-overwrite",
        action="store_true",
        help="Allow --profile-import to overwrite an existing profile",
    )

    # ==================== GIT INTEGRATION ARGUMENTS ====================

    git_group = parser.add_argument_group("Git Integration", "Options for version-controlled snapshots")

    git_group.add_argument(
        "--git-commit",
        action="store_true",
        help="Save snapshot in Git-friendly format and commit to Git repository. "
        "Creates separate JSON files (metrics.json, dimensions.json, metadata.json) "
        "for easy diffing in Git",
    )

    git_group.add_argument(
        "--git-push",
        action="store_true",
        help="Push to remote after committing (requires --git-commit)",
    )

    git_group.add_argument(
        "--git-message",
        type=str,
        metavar="MESSAGE",
        help="Custom message for Git commit (used with --git-commit)",
    )

    git_group.add_argument(
        "--git-dir",
        type=str,
        default="./sdr-snapshots",
        metavar="DIR",
        help="Directory for Git-tracked snapshots (default: ./sdr-snapshots). "
        "Will be initialized as Git repo if not already",
    )

    git_group.add_argument(
        "--git-init",
        action="store_true",
        help="Initialize a new Git repository for snapshots at --git-dir location",
    )

    # ==================== DERIVED FIELD INVENTORY ARGUMENTS ====================

    derived_group = parser.add_argument_group(
        "Derived Field Inventory",
        "Include summary inventory of derived fields in SDR output",
    )

    derived_group.add_argument(
        "--include-derived",
        action="store_true",
        dest="include_derived_inventory",
        help='Include derived field inventory in SDR output. Adds a "Derived Fields" sheet/section '
        "with complexity scores, functions used, and logic summaries. "
        "Note: For SDR generation only; not used in snapshot diff comparisons since derived "
        "fields are already captured in standard metrics/dimensions output.",
    )

    # ==================== CALCULATED METRICS INVENTORY ARGUMENTS ====================

    calc_metrics_group = parser.add_argument_group(
        "Calculated Metrics Inventory",
        "Include summary inventory of calculated metrics in SDR output",
    )

    calc_metrics_group.add_argument(
        "--include-calculated",
        action="store_true",
        dest="include_calculated_metrics",
        help='Include calculated metrics inventory in SDR output. Adds a "Calculated Metrics" sheet/section '
        "with complexity scores, formula summaries, and metric references",
    )

    # ==================== SEGMENTS INVENTORY ARGUMENTS ====================

    segments_group = parser.add_argument_group(
        "Segments Inventory",
        "Include summary inventory of segments (filters) in SDR output",
    )

    segments_group.add_argument(
        "--include-segments",
        action="store_true",
        dest="include_segments_inventory",
        help='Include segments inventory in SDR output. Adds a "Segments" sheet/section '
        "with complexity scores, definition summaries, and dimension/metric references",
    )

    # ==================== INVENTORY-ONLY MODE ====================

    inventory_only_group = parser.add_argument_group(
        "Inventory-Only Mode",
        "Generate output with only inventory sheets (no standard SDR content)",
    )

    inventory_only_group.add_argument(
        "--inventory-only",
        action="store_true",
        dest="inventory_only",
        help="Output only inventory sheets (Calculated Metrics, Segments, Derived Fields). "
        "Skips standard SDR sheets (Metadata, Data Quality, DataView, Metrics, Dimensions). "
        "Requires at least one --include-* flag.",
    )

    inventory_only_group.add_argument(
        "--inventory-summary",
        action="store_true",
        dest="inventory_summary",
        help="Display quick inventory statistics without generating full output files. "
        "Shows counts, complexity distribution, and high-complexity warnings. "
        "Requires at least one --include-* flag. Cannot be used with --inventory-only.",
    )

    inventory_only_group.add_argument(
        "--include-all-inventory",
        action="store_true",
        dest="include_all_inventory",
        help="Enable all inventory options. In SDR mode, enables --include-segments, "
        "--include-calculated, and --include-derived. In snapshot/snapshot-diff modes "
        "(--snapshot, --diff-snapshot, --compare-snapshots, --compare-with-prev) and "
        "with --git-commit, enables only --include-segments and --include-calculated "
        "(derived fields are not supported there).",
    )

    # ==================== ORG-WIDE ANALYSIS ARGUMENTS ====================

    org_group = parser.add_argument_group(
        "Org-Wide Analysis",
        "Analyze component distribution across all data views in the organization",
    )

    org_group.add_argument(
        "--org-report",
        action="store_true",
        help="Generate org-wide component analysis report. Analyzes all accessible "
        "data views to show component distribution, similarity matrix, and "
        "governance recommendations. No data view arguments required.",
    )

    org_group.add_argument(
        "--filter",
        type=str,
        metavar="PATTERN",
        dest="org_filter",
        help="Include only data views whose name matches this regex pattern "
        '(e.g., "Prod.*" or "prod|production"). Avoid complex nested quantifiers',
    )

    org_group.add_argument(
        "--exclude",
        type=str,
        metavar="PATTERN",
        dest="org_exclude",
        help="Exclude data views whose name matches this regex pattern "
        '(e.g., "Test.*|Dev.*|sandbox"). Avoid complex nested quantifiers',
    )

    org_group.add_argument(
        "--limit",
        type=int,
        metavar="N",
        dest="org_limit",
        help="Limit the number of data views to analyze (useful for testing or large orgs)",
    )

    org_group.add_argument(
        "--core-threshold",
        type=float,
        default=0.5,
        metavar="PERCENT",
        help='Threshold for "core" components as fraction of data views '
        "(default: 0.5 = components in >= 50%% of DVs are core)",
    )

    org_group.add_argument(
        "--core-min-count",
        type=int,
        metavar="N",
        help='Minimum absolute count for "core" components (overrides --core-threshold). '
        "E.g., --core-min-count 5 means components in >= 5 DVs are core",
    )

    org_group.add_argument(
        "--overlap-threshold",
        type=_bounded_float(0.0, 1.0),
        default=0.8,
        metavar="PERCENT",
        help='Threshold for "high overlap" pairs in similarity analysis '
        "(default: 0.8). Note: For governance checks (--fail-on-threshold), "
        "values above 0.9 are capped at 90%% to ensure duplicate detection",
    )

    org_group.add_argument(
        "--skip-similarity",
        action="store_true",
        help="Skip the O(n^2) pairwise similarity matrix calculation. Useful for very large orgs with many data views",
    )

    org_group.add_argument(
        "--similarity-max-dvs",
        type=int,
        metavar="N",
        dest="org_similarity_max_dvs",
        default=250,
        help="Guardrail to skip similarity when data views exceed N (default: 250). "
        "Use --force-similarity to override.",
    )

    org_group.add_argument(
        "--force-similarity",
        action="store_true",
        dest="org_force_similarity",
        help="Force similarity matrix even if guardrails would skip it",
    )

    org_group.add_argument(
        "--include-names",
        action="store_true",
        dest="org_include_names",
        help="Include component names in the report (slower - requires fetching full component details)",
    )

    org_group.add_argument(
        "--org-summary",
        action="store_true",
        help="Show only summary statistics, suppress detailed component lists",
    )

    org_group.add_argument(
        "--org-verbose",
        action="store_true",
        help="Include full component lists and detailed breakdowns in output",
    )

    # Component type breakdown (enabled by default)
    org_group.add_argument(
        "--no-component-types",
        action="store_true",
        dest="no_component_types",
        help="Disable component type breakdown (standard vs derived metrics/dimensions)",
    )

    # Metadata
    org_group.add_argument(
        "--include-metadata",
        action="store_true",
        dest="org_include_metadata",
        help="Include data view metadata (owner, creation/modification dates, descriptions)",
    )

    # Drift detection
    org_group.add_argument(
        "--include-drift",
        action="store_true",
        dest="org_include_drift",
        help="Include component drift details showing exact differences between similar DV pairs",
    )

    org_group.add_argument(
        "--org-shared-client",
        action="store_true",
        dest="org_shared_client",
        help="Use a single shared cjapy client across threads. WARNING: This is experimental "
        "and may cause race conditions if cjapy is not thread-safe. Use only if you have "
        "tested with your cjapy version. Default creates one client per thread (safer)",
    )

    # Sampling options
    org_group.add_argument(
        "--sample",
        type=int,
        metavar="N",
        dest="org_sample_size",
        help="Randomly sample N data views (useful for very large orgs)",
    )

    org_group.add_argument(
        "--sample-seed",
        type=int,
        metavar="SEED",
        dest="org_sample_seed",
        help="Random seed for reproducible sampling",
    )

    org_group.add_argument(
        "--sample-stratified",
        action="store_true",
        dest="org_sample_stratified",
        help="Stratify sample by data view name prefix",
    )

    # Caching options
    org_group.add_argument(
        "--use-cache",
        action="store_true",
        dest="org_use_cache",
        help="Enable caching of data view components for faster repeat runs",
    )

    org_group.add_argument(
        "--cache-max-age",
        type=int,
        metavar="HOURS",
        default=24,
        dest="org_cache_max_age",
        help="Maximum cache age in hours (default: 24)",
    )

    org_group.add_argument(
        "--refresh-cache",
        action="store_true",
        dest="org_clear_cache",
        help="Clear the org-report cache and fetch fresh data",
    )

    org_group.add_argument(
        "--validate-cache",
        action="store_true",
        dest="org_validate_cache",
        help="Validate cached entries against data view modification timestamps before using",
    )

    org_group.add_argument(
        "--memory-warning",
        type=int,
        metavar="MB",
        default=100,
        dest="org_memory_warning",
        help="Warn if component index estimated memory exceeds this threshold in MB (default: 100, 0 to disable)",
    )

    org_group.add_argument(
        "--memory-limit",
        type=int,
        metavar="MB",
        default=None,
        dest="org_memory_limit",
        help="Abort if component index exceeds this size in MB. Protects against OOM for very large orgs (default: no limit)",
    )

    # Clustering options
    org_group.add_argument(
        "--cluster",
        action="store_true",
        dest="org_cluster",
        help="Enable hierarchical clustering to group related data views (requires 'clustering' extra: uv pip install 'cja-auto-sdr[clustering]')",
    )

    org_group.add_argument(
        "--cluster-method",
        type=str,
        choices=["average", "complete"],
        default="average",
        dest="org_cluster_method",
        help="Clustering linkage method: average (recommended) or complete. Both work correctly with Jaccard distances",
    )

    # Feature 1: Governance exit codes
    org_group.add_argument(
        "--duplicate-threshold",
        type=int,
        metavar="N",
        dest="org_duplicate_threshold",
        help="Maximum allowed high-similarity pairs (>=90%%). Exit with code 2 if exceeded when --fail-on-threshold is set",
    )

    org_group.add_argument(
        "--isolated-threshold",
        type=_bounded_float(0.0, 1.0),
        metavar="PERCENT",
        dest="org_isolated_threshold",
        help="Maximum isolated component percentage (0.0-1.0). Exit with code 2 if exceeded when --fail-on-threshold is set",
    )

    org_group.add_argument(
        "--fail-on-threshold",
        action="store_true",
        dest="org_fail_on_threshold",
        help="Enable exit code 2 when governance thresholds are exceeded (for CI/CD integration)",
    )

    # Feature 2: Org summary stats mode
    org_group.add_argument(
        "--org-stats",
        action="store_true",
        dest="org_stats_only",
        help="Quick summary stats only - skips similarity matrix and clustering for faster results",
    )

    # Feature 3: Naming convention audit
    org_group.add_argument(
        "--audit-naming",
        action="store_true",
        dest="org_audit_naming",
        help="Detect naming pattern inconsistencies (snake_case vs camelCase, stale prefixes, etc.)",
    )

    # Feature 4: Trending/drift report
    org_group.add_argument(
        "--compare-org-report",
        type=str,
        metavar="PREV.json",
        dest="org_compare_report",
        help="Compare current org-report to a previous JSON report for trending/drift analysis",
    )
    org_group.add_argument(
        "--trending-window",
        type=int,
        nargs="?",
        const=10,
        default=None,
        metavar="N",
        dest="trending_window",
        help="Show trending across the last N cached org-report snapshots (default: 10). "
        "Requires --org-report. Output appears in all requested formats.",
    )
    org_group.add_argument(
        "--list-org-report-snapshots",
        action="store_true",
        dest="list_org_report_snapshots",
        help="List cached org-report snapshots from the persistent trending history store",
    )
    org_group.add_argument(
        "--inspect-org-report-snapshot",
        type=str,
        metavar="FILE",
        dest="inspect_org_report_snapshot",
        help="Inspect one cached org-report snapshot JSON without running a fresh org-report",
    )
    org_group.add_argument(
        "--prune-org-report-snapshots",
        action="store_true",
        dest="prune_org_report_snapshots",
        help="Apply retention policies to cached org-report snapshots in the persistent trending history store",
    )
    org_group.add_argument(
        "--org-report-snapshot-org",
        type=str,
        metavar="ORG_ID",
        dest="org_report_snapshot_org",
        help="Filter org-report snapshot listing/pruning to one org ID",
    )
    org_group.add_argument(
        "--org-report-keep-last",
        type=int,
        default=0,
        metavar="N",
        dest="org_report_keep_last",
        help="For --prune-org-report-snapshots, keep only the last N snapshots per org (0 = keep all)",
    )
    org_group.add_argument(
        "--org-report-keep-since",
        type=str,
        default=None,
        metavar="PERIOD",
        dest="org_report_keep_since",
        help="For --prune-org-report-snapshots, delete org-report snapshots older than PERIOD (e.g. 30d, 12w)",
    )

    # Feature 5: Owner/team summary
    org_group.add_argument(
        "--owner-summary",
        action="store_true",
        dest="org_owner_summary",
        help="Group statistics by data view owner (requires --include-metadata)",
    )

    # Feature 6: Stale component heuristics
    org_group.add_argument(
        "--flag-stale",
        action="store_true",
        dest="org_flag_stale",
        help="Flag components with stale naming patterns (test, old, temp, deprecated, version suffixes, date patterns)",
    )

    # Enable shell tab-completion if argcomplete is installed
    if enable_autocomplete and _ARGCOMPLETE_AVAILABLE:
        argcomplete.autocomplete(parser)  # pragma: no cover

    if return_parser:
        return parser

    return parser.parse_args(argv)
