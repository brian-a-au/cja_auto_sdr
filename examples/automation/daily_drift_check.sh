#!/usr/bin/env bash
# daily_drift_check.sh — Daily drift detection with Slack notification
#
# Cron entry (daily 6am):
#   0 6 * * * /path/to/daily_drift_check.sh >> /var/log/cja_sdr/drift.log 2>&1
#
# Environment variables:
#   DATA_VIEW_ID    — data view to monitor (required)
#   SLACK_WEBHOOK   — Slack incoming webhook URL (optional)
#   SNAPSHOT_DIR    — snapshot directory (default: ./snapshots)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SNAPSHOT_DIR="${SNAPSHOT_DIR:-$PROJECT_ROOT/snapshots}"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

if [[ -z "${DATA_VIEW_ID:-}" ]]; then
    echo "$LOG_PREFIX ERROR: DATA_VIEW_ID not set" >&2
    exit 1
fi

# Load credentials
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$PROJECT_ROOT/.env"
    set +a
fi

cd "$PROJECT_ROOT"

BASELINE="$SNAPSHOT_DIR/${DATA_VIEW_ID}_baseline.json"

# Ensure baseline exists
if [[ ! -f "$BASELINE" ]]; then
    echo "$LOG_PREFIX No baseline found. Creating initial snapshot."
    uv run cja_auto_sdr "$DATA_VIEW_ID" --snapshot "$BASELINE"
    exit 0
fi

# Run drift detection (capture exit code before || true consumes it)
DIFF_EXIT=0
DIFF_OUTPUT=$(uv run cja_auto_sdr "$DATA_VIEW_ID" --diff-snapshot "$BASELINE" \
    --format json --output - 2>/dev/null) || DIFF_EXIT=$?

echo "$LOG_PREFIX Drift check exit code: $DIFF_EXIT"

# Notify on drift (exit code 2) or warning (exit code 3)
if [[ $DIFF_EXIT -eq 2 || $DIFF_EXIT -eq 3 ]]; then
    SUMMARY=$(echo "$DIFF_OUTPUT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    summary = data.get('summary', {})
    print(f\"Metrics: {summary.get('metrics_changed', '?')} changed, Dimensions: {summary.get('dimensions_changed', '?')} changed\")
except Exception:
    print('Unable to parse diff summary')
" 2>/dev/null)

    echo "$LOG_PREFIX DRIFT DETECTED: $SUMMARY"

    # Post to Slack if webhook is configured
    if [[ -n "${SLACK_WEBHOOK:-}" ]]; then
        SEVERITY="warning"
        [[ $DIFF_EXIT -eq 2 ]] && SEVERITY="danger"

        curl -s -X POST "$SLACK_WEBHOOK" \
            -H 'Content-Type: application/json' \
            -d "{
                \"attachments\": [{
                    \"color\": \"$SEVERITY\",
                    \"title\": \"CJA Data View Drift Detected\",
                    \"text\": \"Data view: $DATA_VIEW_ID\n$SUMMARY\",
                    \"footer\": \"cja_auto_sdr drift check\",
                    \"ts\": $(date +%s)
                }]
            }" > /dev/null
        echo "$LOG_PREFIX Slack notification sent"
    fi
fi

# Update baseline after check
uv run cja_auto_sdr "$DATA_VIEW_ID" --snapshot "$BASELINE"
echo "$LOG_PREFIX Baseline updated"

exit 0
