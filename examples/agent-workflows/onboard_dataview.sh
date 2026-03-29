#!/usr/bin/env bash
# onboard_dataview.sh — Onboard a new data view: validate config, inspect,
# generate SDR with quality gating, and save a baseline snapshot.
#
# Designed for agent/automation use:
#   - Uses --agent-mode (expands to --format json --output - --log-format json)
#   - Uses IDs, never display names, for unattended operations
#   - Exits non-zero on quality gate failure (--fail-on-quality MEDIUM)
#
# Usage:
#   DATA_VIEW_ID=dv_abc123 ./onboard_dataview.sh
#
# Environment variables:
#   DATA_VIEW_ID    — data view to onboard (required)
#   REPORT_DIR      — output directory for SDR artifacts and run summary (default: ./reports)
#   SNAPSHOT_DIR    — snapshot directory (default: ./snapshots)
#   QUALITY_GATE    — quality level for --fail-on-quality (default: MEDIUM)
#
# Exit codes follow cja_auto_sdr conventions:
#   0 = success, 1 = error, 2 = quality gate breached

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPORT_DIR="${REPORT_DIR:-$PROJECT_ROOT/reports}"
SNAPSHOT_DIR="${SNAPSHOT_DIR:-$PROJECT_ROOT/snapshots}"
QUALITY_GATE="${QUALITY_GATE:-MEDIUM}"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

# shellcheck source=/dev/null
source "$SCRIPT_DIR/_common.sh"

# Prefer credentials injected by the caller/CI. Fall back to a repo-local
# .env only for workstation-style usage of this example script.
if [[ -z "${ORG_ID:-}" || -z "${CLIENT_ID:-}" || -z "${SECRET:-}" || -z "${SCOPES:-}" ]]; then
    if [[ -f "$PROJECT_ROOT/.env" ]]; then
        set -a
        # shellcheck source=/dev/null
        source "$PROJECT_ROOT/.env"
        set +a
    fi
fi

require_env DATA_VIEW_ID

cd "$PROJECT_ROOT"

echo "$LOG_PREFIX Onboarding data view: $DATA_VIEW_ID"

# --- Step 1: Config preflight ---
echo "$LOG_PREFIX Running config preflight"
if ! uv run cja_auto_sdr --validate-config; then
    echo "$LOG_PREFIX ERROR: Configuration validation failed" >&2
    exit 1
fi
echo "$LOG_PREFIX Configuration validated"

# --- Step 2: Inspect data view metadata ---
echo "$LOG_PREFIX Inspecting data view $DATA_VIEW_ID"
capture_command_output DESCRIBE_EXIT DESCRIBE_OUTPUT \
    uv run cja_auto_sdr --describe-dataview "$DATA_VIEW_ID" --agent-mode
exit_on_signal_exit "$DESCRIBE_EXIT" "$LOG_PREFIX ERROR: Describe interrupted"

if [[ $DESCRIBE_EXIT -ne 0 ]]; then
    echo "$LOG_PREFIX ERROR: Failed to describe data view $DATA_VIEW_ID (exit $DESCRIBE_EXIT)" >&2
    exit 1
fi
echo "$LOG_PREFIX Data view inspection complete"

# --- Step 3: Generate SDR with quality gating ---
echo "$LOG_PREFIX Generating SDR with quality gate: $QUALITY_GATE"

mkdir -p "$REPORT_DIR" "$SNAPSHOT_DIR"

RUN_SUMMARY_FILE="$REPORT_DIR/${DATA_VIEW_ID}_run_summary.json"

capture_command_output SDR_EXIT SDR_OUTPUT \
    uv run cja_auto_sdr "$DATA_VIEW_ID" --agent-mode \
        --output-dir "$REPORT_DIR" \
        --fail-on-quality "$QUALITY_GATE" \
        --run-summary-json "$RUN_SUMMARY_FILE"
exit_on_signal_exit "$SDR_EXIT" "$LOG_PREFIX ERROR: SDR generation interrupted"

case $SDR_EXIT in
    0)
        echo "$LOG_PREFIX SDR generated successfully"
        echo "$LOG_PREFIX SDR artifacts written to: $REPORT_DIR"
        echo "$LOG_PREFIX Run summary written to: $RUN_SUMMARY_FILE"
        ;;
    2)
        echo "$LOG_PREFIX Quality gate breached ($QUALITY_GATE) for $DATA_VIEW_ID" >&2
        SEVERITY="unknown"
        if [[ -f "$RUN_SUMMARY_FILE" ]]; then
            RUN_SUMMARY_JSON="$(<"$RUN_SUMMARY_FILE")"
            SEVERITY=$(extract_highest_quality_severity_from_run_summary "$RUN_SUMMARY_JSON" 2>/dev/null || echo "unknown")
        fi
        notify "Quality gate breach — $DATA_VIEW_ID severity=$SEVERITY"
        exit 2
        ;;
    *)
        echo "$LOG_PREFIX ERROR: SDR generation failed for $DATA_VIEW_ID (exit $SDR_EXIT)" >&2
        exit 1
        ;;
esac

# --- Step 4: Save baseline snapshot ---
echo "$LOG_PREFIX Saving baseline snapshot"

BASELINE="$SNAPSHOT_DIR/${DATA_VIEW_ID}_baseline.json"
capture_command_exit SNAPSHOT_EXIT \
    uv run cja_auto_sdr "$DATA_VIEW_ID" --snapshot "$BASELINE"
exit_on_signal_exit "$SNAPSHOT_EXIT" "$LOG_PREFIX ERROR: Baseline snapshot interrupted"

case $SNAPSHOT_EXIT in
    0)
        echo "$LOG_PREFIX Baseline snapshot saved: $BASELINE"
        ;;
    *)
        echo "$LOG_PREFIX ERROR: Baseline snapshot failed (exit $SNAPSHOT_EXIT)" >&2
        exit 1
        ;;
esac

echo "$LOG_PREFIX Onboarding complete for $DATA_VIEW_ID"
notify "Onboarding complete — $DATA_VIEW_ID"

exit 0
