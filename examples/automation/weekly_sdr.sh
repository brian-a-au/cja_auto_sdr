#!/usr/bin/env bash
# weekly_sdr.sh — Weekly SDR generation with drift detection
#
# Cron entry (Sunday 2am):
#   0 2 * * 0 /path/to/weekly_sdr.sh >> /var/log/cja_sdr/weekly.log 2>&1
#
# Prerequisites:
#   - .env file with ORG_ID, CLIENT_ID, SECRET, SCOPES
#   - uv installed and cja_auto_sdr synced
#
# Exit codes follow cja_auto_sdr conventions:
#   0 = success, 1 = error, 2 = policy threshold exceeded, 3 = warning threshold

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPORT_DIR="${REPORT_DIR:-$PROJECT_ROOT/reports}"
SNAPSHOT_DIR="${SNAPSHOT_DIR:-$PROJECT_ROOT/snapshots}"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

# Load credentials
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$PROJECT_ROOT/.env"
    set +a
fi

cd "$PROJECT_ROOT"

echo "$LOG_PREFIX Starting weekly SDR generation"

# Pre-flight check
if ! uv run cja_auto_sdr --validate-config; then
    echo "$LOG_PREFIX ERROR: Configuration validation failed" >&2
    exit 1
fi

echo "$LOG_PREFIX Configuration validated"

# Get data view list
DATA_VIEWS=$(uv run cja_auto_sdr --list-dataviews --format json --output - | \
    python3 -c "import sys,json; [print(dv['id']) for dv in json.load(sys.stdin)]" 2>/dev/null) || {
    echo "$LOG_PREFIX ERROR: Failed to list data views" >&2
    exit 1
}

mkdir -p "$REPORT_DIR" "$SNAPSHOT_DIR"

OVERALL_EXIT=0

for DV_ID in $DATA_VIEWS; do
    echo "$LOG_PREFIX Processing data view: $DV_ID"

    # Generate SDR (capture exit code — set -e would abort on non-zero)
    SDR_EXIT=0
    uv run cja_auto_sdr "$DV_ID" --format excel --output-dir "$REPORT_DIR" || SDR_EXIT=$?

    case $SDR_EXIT in
        0) echo "$LOG_PREFIX  SDR generated successfully" ;;
        1) echo "$LOG_PREFIX  ERROR: SDR generation failed" >&2; OVERALL_EXIT=1; continue ;;
        2) echo "$LOG_PREFIX  WARNING: Quality threshold exceeded"; OVERALL_EXIT=2 ;;
        *) echo "$LOG_PREFIX  Unexpected exit code: $SDR_EXIT" >&2; OVERALL_EXIT=1; continue ;;
    esac

    # Drift detection against baseline (if snapshot exists)
    BASELINE="$SNAPSHOT_DIR/${DV_ID}_baseline.json"
    if [[ -f "$BASELINE" ]]; then
        DIFF_EXIT=0
        uv run cja_auto_sdr "$DV_ID" --diff-snapshot "$BASELINE" --format json --output - \
            > "$REPORT_DIR/${DV_ID}_drift.json" 2>/dev/null || DIFF_EXIT=$?

        case $DIFF_EXIT in
            0) echo "$LOG_PREFIX  No drift detected" ;;
            2) echo "$LOG_PREFIX  DRIFT DETECTED — see ${DV_ID}_drift.json" ;;
            3) echo "$LOG_PREFIX  Warning threshold exceeded" ;;
            *) echo "$LOG_PREFIX  Diff failed (exit $DIFF_EXIT)" >&2 ;;
        esac
    fi

    # Update baseline snapshot (data view is positional, --snapshot takes FILE)
    uv run cja_auto_sdr "$DV_ID" --snapshot "$SNAPSHOT_DIR/${DV_ID}_baseline.json"
    echo "$LOG_PREFIX  Baseline snapshot updated"
done

echo "$LOG_PREFIX Weekly SDR generation complete (exit: $OVERALL_EXIT)"
exit $OVERALL_EXIT
