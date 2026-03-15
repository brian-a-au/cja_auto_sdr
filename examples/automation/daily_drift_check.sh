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
# Keep the example self-contained when copied as a single cron script.
if [[ -f "$SCRIPT_DIR/_common.sh" ]]; then
    # shellcheck source=/dev/null
    source "$SCRIPT_DIR/_common.sh"
else
    is_signal_exit_code() {
        local code="${1:-0}"

        [[ "$code" =~ ^[0-9]+$ ]] || return 1
        (( code > 128 && code <= 192 ))
    }

    capture_command_exit() {
        local exit_var_name="$1"
        shift

        local exit_code=0
        if "$@"; then
            exit_code=0
        else
            exit_code=$?
        fi

        printf -v "$exit_var_name" '%s' "$exit_code"
    }

    capture_command_output() {
        local exit_var_name="$1"
        local output_var_name="$2"
        shift 2

        local exit_code=0
        local output=""
        if output="$("$@")"; then
            exit_code=0
        else
            exit_code=$?
        fi

        printf -v "$exit_var_name" '%s' "$exit_code"
        printf -v "$output_var_name" '%s' "$output"
    }

    exit_on_signal_exit() {
        local code="${1:-0}"
        shift

        if is_signal_exit_code "$code"; then
            if [[ $# -gt 0 ]]; then
                echo "$* (exit $code)" >&2
            fi
            exit "$code"
        fi
    }
fi

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
mkdir -p "$SNAPSHOT_DIR"

BASELINE="$SNAPSHOT_DIR/${DATA_VIEW_ID}_baseline.json"

# Ensure baseline exists
if [[ ! -f "$BASELINE" ]]; then
    echo "$LOG_PREFIX No baseline found. Creating initial snapshot."
    capture_command_exit SNAPSHOT_EXIT uv run cja_auto_sdr "$DATA_VIEW_ID" --snapshot "$BASELINE"
    case $SNAPSHOT_EXIT in
        0) exit 0 ;;
        *)
            exit_on_signal_exit "$SNAPSHOT_EXIT" "$LOG_PREFIX ERROR: Baseline creation interrupted"
            echo "$LOG_PREFIX ERROR: Initial baseline creation failed (exit $SNAPSHOT_EXIT)" >&2
            ;;
    esac
    exit "$SNAPSHOT_EXIT"
fi

# Run drift detection while preserving non-zero exits for policy handling.
capture_command_output DIFF_EXIT DIFF_OUTPUT uv run cja_auto_sdr "$DATA_VIEW_ID" --diff-snapshot "$BASELINE" \
    --format json --output - 2>/dev/null
exit_on_signal_exit "$DIFF_EXIT" "$LOG_PREFIX ERROR: Drift comparison interrupted"

echo "$LOG_PREFIX Drift check exit code: $DIFF_EXIT"

# Notify on drift (exit code 2) or warning (exit code 3).
# Baseline is NOT updated when drift is detected — this is intentional so that
# alerts keep firing until the drift is acknowledged.  To reset the baseline
# after reviewing changes, re-run: uv run cja_auto_sdr "$DATA_VIEW_ID" --snapshot "$BASELINE"
if [[ $DIFF_EXIT -eq 2 || $DIFF_EXIT -eq 3 ]]; then
    SUMMARY=$(printf '%s' "$DIFF_OUTPUT" | python3 -c "
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
        if ! command -v jq >/dev/null 2>&1; then
            echo "$LOG_PREFIX WARNING: jq not installed; skipping Slack notification" >&2
        else
            SEVERITY="warning"
            [[ $DIFF_EXIT -eq 2 ]] && SEVERITY="danger"

            PAYLOAD=$(jq -n \
                --arg color "$SEVERITY" \
                --arg title "CJA Data View Drift Detected" \
                --arg text "Data view: $DATA_VIEW_ID\n$SUMMARY" \
                --arg footer "cja_auto_sdr drift check" \
                --argjson ts "$(date +%s)" \
                '{attachments: [{color: $color, title: $title, text: $text, footer: $footer, ts: $ts}]}')
            if curl -fsS -X POST "$SLACK_WEBHOOK" \
                -H 'Content-Type: application/json' \
                -d "$PAYLOAD" > /dev/null; then
                echo "$LOG_PREFIX Slack notification sent"
            else
                echo "$LOG_PREFIX WARNING: Slack notification failed" >&2
            fi
        fi
    fi
elif [[ $DIFF_EXIT -eq 0 ]]; then
    # Only update baseline when no drift detected
    capture_command_exit SNAPSHOT_EXIT uv run cja_auto_sdr "$DATA_VIEW_ID" --snapshot "$BASELINE"
    case $SNAPSHOT_EXIT in
        0) echo "$LOG_PREFIX Baseline updated (no drift)" ;;
        *)
            exit_on_signal_exit "$SNAPSHOT_EXIT" "$LOG_PREFIX ERROR: Baseline refresh interrupted"
            echo "$LOG_PREFIX ERROR: Baseline refresh failed (exit $SNAPSHOT_EXIT)" >&2
            ;;
    esac
    exit "$SNAPSHOT_EXIT"
else
    echo "$LOG_PREFIX ERROR: Diff comparison failed; baseline preserved" >&2
fi

# Propagate the drift exit code so cron/monitoring can detect policy violations.
# 0 = no drift, 1 = diff failed, 2 = policy threshold exceeded, 3 = warning threshold exceeded.
exit "$DIFF_EXIT"
