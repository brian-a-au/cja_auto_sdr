#!/usr/bin/env bash
# weekly_sdr.sh — Weekly SDR generation with drift detection
#
# Cron entry (Sunday 2am):
#   0 2 * * 0 /path/to/weekly_sdr.sh >> /var/log/cja_sdr/weekly.log 2>&1
#
# Prerequisites:
#   - Credentials injected via environment variables or secret manager
#   - Optional local-only fallback: .env with ORG_ID, CLIENT_ID, SECRET, SCOPES
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

update_overall_exit() {
    local code="${1:-0}"

    if is_signal_exit_code "$OVERALL_EXIT"; then
        return
    fi

    if is_signal_exit_code "$code"; then
        OVERALL_EXIT="$code"
        return
    fi

    case "$code" in
        0) ;;
        1) OVERALL_EXIT=1 ;;
        2) [[ $OVERALL_EXIT -ne 1 ]] && OVERALL_EXIT=2 ;;
        3) [[ $OVERALL_EXIT -eq 0 ]] && OVERALL_EXIT=3 ;;
        *) OVERALL_EXIT=1 ;;
    esac
}

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

echo "$LOG_PREFIX Starting weekly SDR generation"

# Pre-flight check
if ! uv run cja_auto_sdr --validate-config; then
    echo "$LOG_PREFIX ERROR: Configuration validation failed" >&2
    exit 1
fi

echo "$LOG_PREFIX Configuration validated"

# Get data view list
DATA_VIEWS=$(uv run cja_auto_sdr --list-dataviews --format json --output - | \
    python3 -c "import sys,json; data=json.load(sys.stdin); views=data if isinstance(data, list) else data.get('dataViews', []); [print(dv['id']) for dv in views if isinstance(dv, dict) and dv.get('id')]" 2>/dev/null) || {
    echo "$LOG_PREFIX ERROR: Failed to list data views" >&2
    exit 1
}

mkdir -p "$REPORT_DIR" "$SNAPSHOT_DIR"

OVERALL_EXIT=0

for DV_ID in $DATA_VIEWS; do
    echo "$LOG_PREFIX Processing data view: $DV_ID"

    # Capture non-zero exits without suppressing shell-style signal termination.
    capture_command_exit SDR_EXIT uv run cja_auto_sdr "$DV_ID" --format excel --output-dir "$REPORT_DIR"
    exit_on_signal_exit "$SDR_EXIT" "$LOG_PREFIX  ERROR: SDR generation interrupted"

    case $SDR_EXIT in
        0) echo "$LOG_PREFIX  SDR generated successfully" ;;
        1) echo "$LOG_PREFIX  ERROR: SDR generation failed" >&2; update_overall_exit 1; continue ;;
        2) echo "$LOG_PREFIX  WARNING: Quality threshold exceeded"; update_overall_exit 2 ;;
        *) echo "$LOG_PREFIX  Unexpected exit code: $SDR_EXIT" >&2; update_overall_exit 1; continue ;;
    esac

    # Drift detection against baseline (if snapshot exists)
    BASELINE="$SNAPSHOT_DIR/${DV_ID}_baseline.json"
    DRIFT_REPORT="$REPORT_DIR/${DV_ID}_drift.json"
    SHOULD_UPDATE_BASELINE=1
    if [[ -f "$BASELINE" ]]; then
        capture_command_exit DIFF_EXIT uv run cja_auto_sdr "$DV_ID" --diff-snapshot "$BASELINE" --format json --output - \
            > "$DRIFT_REPORT" 2>/dev/null

        if is_signal_exit_code "$DIFF_EXIT"; then
            echo "$LOG_PREFIX  Diff interrupted (exit $DIFF_EXIT)" >&2
            rm -f "$DRIFT_REPORT"
            exit "$DIFF_EXIT"
        fi

        case $DIFF_EXIT in
            0) echo "$LOG_PREFIX  No drift detected" ;;
            2) echo "$LOG_PREFIX  DRIFT DETECTED — see ${DV_ID}_drift.json"; update_overall_exit 2 ;;
            3) echo "$LOG_PREFIX  Warning threshold exceeded"; update_overall_exit 3 ;;
            *)
                echo "$LOG_PREFIX  Diff failed (exit $DIFF_EXIT)" >&2
                update_overall_exit 1
                SHOULD_UPDATE_BASELINE=0
                rm -f "$DRIFT_REPORT"
                ;;
        esac
    fi

    if [[ $SHOULD_UPDATE_BASELINE -eq 1 ]]; then
        # Update baseline snapshot (data view is positional, --snapshot takes FILE)
        capture_command_exit SNAPSHOT_EXIT uv run cja_auto_sdr "$DV_ID" --snapshot "$SNAPSHOT_DIR/${DV_ID}_baseline.json"
        exit_on_signal_exit "$SNAPSHOT_EXIT" "$LOG_PREFIX  Baseline snapshot interrupted"
        case $SNAPSHOT_EXIT in
            0) echo "$LOG_PREFIX  Baseline snapshot updated" ;;
            *)
                echo "$LOG_PREFIX  Baseline snapshot failed (exit $SNAPSHOT_EXIT); baseline preserved" >&2
                update_overall_exit 1
                ;;
        esac
    else
        echo "$LOG_PREFIX  Baseline preserved due to diff failure"
    fi
done

echo "$LOG_PREFIX Weekly SDR generation complete (exit: $OVERALL_EXIT)"
exit $OVERALL_EXIT
