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

# Notify on drift (exit code 2) or warning (exit code 3).
# Baseline is NOT updated when drift is detected — this is intentional so that
# alerts keep firing until the drift is acknowledged.  To reset the baseline
# after reviewing changes, re-run: uv run cja_auto_sdr "$DATA_VIEW_ID" --snapshot "$BASELINE"
if [[ $DIFF_EXIT -eq 2 || $DIFF_EXIT -eq 3 ]]; then
    SUMMARY=$(echo "$DIFF_OUTPUT" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    summary = data.get('summary', {})
    def changed_total(prefix):
        explicit_total = summary.get(f'{prefix}_changed')
        if explicit_total is not None:
            return explicit_total
        return sum(int(summary.get(f'{prefix}_{suffix}', 0) or 0) for suffix in ('added', 'removed', 'modified'))
    print(f\"Metrics: {changed_total('metrics')} changed, Dimensions: {changed_total('dimensions')} changed\")
except Exception:
    print('Unable to parse diff summary')
" 2>/dev/null)

    echo "$LOG_PREFIX DRIFT DETECTED: $SUMMARY"

    # Post to Slack if webhook is configured
    if [[ -n "${SLACK_WEBHOOK:-}" ]]; then
        SEVERITY="warning"
        [[ $DIFF_EXIT -eq 2 ]] && SEVERITY="danger"

        PAYLOAD=$(jq -n \
            --arg color "$SEVERITY" \
            --arg title "CJA Data View Drift Detected" \
            --arg text "Data view: $DATA_VIEW_ID\n$SUMMARY" \
            --arg footer "cja_auto_sdr drift check" \
            --argjson ts "$(date +%s)" \
            '{attachments: [{color: $color, title: $title, text: $text, footer: $footer, ts: $ts}]}')
        curl -s -X POST "$SLACK_WEBHOOK" \
            -H 'Content-Type: application/json' \
            -d "$PAYLOAD" > /dev/null
        echo "$LOG_PREFIX Slack notification sent"
    fi
elif [[ $DIFF_EXIT -eq 0 ]]; then
    # Only update baseline when no drift detected
    uv run cja_auto_sdr "$DATA_VIEW_ID" --snapshot "$BASELINE"
    echo "$LOG_PREFIX Baseline updated (no drift)"
else
    echo "$LOG_PREFIX ERROR: Diff comparison failed; baseline preserved" >&2
fi

# Propagate the drift exit code so cron/monitoring can detect policy violations.
# 0 = no drift, 1 = diff failed, 2 = policy threshold exceeded, 3 = warning threshold exceeded.
exit $DIFF_EXIT
