#!/usr/bin/env bash
# quarterly_maintenance.sh — Quarterly baseline refresh, governance review, and cleanup
#
# Cron entry (1st of Jan/Apr/Jul/Oct at 3am):
#   0 3 1 1,4,7,10 * /path/to/quarterly_maintenance.sh >> /var/log/cja_sdr/quarterly.log 2>&1
#
# Environment variables:
#   REPORT_DIR      — output directory for reports (default: ./reports)
#   SNAPSHOT_DIR    — snapshot directory (default: ./snapshots)
#   KEEP_LAST       — number of snapshots to retain after pruning (default: 4)
#   SLACK_WEBHOOK   — Slack incoming webhook URL (optional)
#
# Phases:
#   1. Full SDR regeneration (all views, all formats)
#   2. Cross-org governance review (clustering + similarity)
#   3. Snapshot pruning and baseline rotation
#   4. Compliance documentation export

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPORT_DIR="${REPORT_DIR:-$PROJECT_ROOT/reports}"
SNAPSHOT_DIR="${SNAPSHOT_DIR:-$PROJECT_ROOT/snapshots}"
KEEP_LAST="${KEEP_LAST:-4}"
QUARTER="Q$(( ($(date +%-m) - 1) / 3 + 1 ))-$(date +%Y)"
QUARTER_DIR="$REPORT_DIR/$QUARTER"
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

echo "$LOG_PREFIX === Quarterly maintenance: $QUARTER ==="

# Pre-flight check
if ! uv run cja_auto_sdr --validate-config; then
    echo "$LOG_PREFIX ERROR: Configuration validation failed" >&2
    exit 1
fi

# Get data view list
DATA_VIEWS=$(uv run cja_auto_sdr --list-dataviews --format json --output - | \
    python3 -c "import sys,json; data=json.load(sys.stdin); views=data if isinstance(data, list) else data.get('dataViews', []); [print(dv['id']) for dv in views if isinstance(dv, dict) and dv.get('id')]" 2>/dev/null) || {
    echo "$LOG_PREFIX ERROR: Failed to list data views" >&2
    exit 1
}

mkdir -p "$QUARTER_DIR" "$SNAPSHOT_DIR"

OVERALL_EXIT=0

# --- Phase 1: Full SDR regeneration (all views, all formats) ---
echo "$LOG_PREFIX Phase 1: Full SDR regeneration"

for DV_ID in $DATA_VIEWS; do
    echo "$LOG_PREFIX  Generating all formats for $DV_ID"
    capture_command_exit SDR_EXIT uv run cja_auto_sdr "$DV_ID" --format all --output-dir "$QUARTER_DIR"
    exit_on_signal_exit "$SDR_EXIT" "$LOG_PREFIX  ERROR: SDR generation interrupted for $DV_ID"
    SHOULD_UPDATE_BASELINE=1

    case $SDR_EXIT in
        0) echo "$LOG_PREFIX  OK" ;;
        2) echo "$LOG_PREFIX  WARNING: Quality threshold exceeded for $DV_ID"; update_overall_exit 2 ;;
        *)
            echo "$LOG_PREFIX  ERROR: SDR generation failed for $DV_ID (exit $SDR_EXIT)" >&2
            update_overall_exit 1
            SHOULD_UPDATE_BASELINE=0
            ;;
    esac

    if [[ $SHOULD_UPDATE_BASELINE -eq 1 ]]; then
        capture_command_exit SNAPSHOT_EXIT uv run cja_auto_sdr "$DV_ID" --snapshot "$SNAPSHOT_DIR/${DV_ID}_baseline.json"
        exit_on_signal_exit "$SNAPSHOT_EXIT" "$LOG_PREFIX  Baseline snapshot interrupted for $DV_ID"
        case $SNAPSHOT_EXIT in
            0) echo "$LOG_PREFIX  Baseline snapshot updated" ;;
            *)
                echo "$LOG_PREFIX  ERROR: Baseline snapshot failed for $DV_ID (exit $SNAPSHOT_EXIT)" >&2
                update_overall_exit 1
                ;;
        esac
    else
        echo "$LOG_PREFIX  Baseline preserved due to SDR generation failure"
    fi
done

# --- Phase 2: Cross-org governance review ---
echo "$LOG_PREFIX Phase 2: Cross-org governance review"

capture_command_exit GOV_EXIT uv run cja_auto_sdr --org-report --cluster --force-similarity \
    --format json --output - > "$QUARTER_DIR/org_governance.json" 2>/dev/null
if is_signal_exit_code "$GOV_EXIT"; then
    echo "$LOG_PREFIX  ERROR: Governance review interrupted (exit $GOV_EXIT)" >&2
    exit "$GOV_EXIT"
fi

case $GOV_EXIT in
    0) echo "$LOG_PREFIX  Governance review: PASS" ;;
    2) echo "$LOG_PREFIX  Governance review: THRESHOLDS EXCEEDED — see org_governance.json"; update_overall_exit 2 ;;
    *) echo "$LOG_PREFIX  ERROR: Governance review failed (exit $GOV_EXIT)" >&2; update_overall_exit 1 ;;
esac

# Also generate human-readable governance report
capture_command_exit GOV_MD_EXIT uv run cja_auto_sdr --org-report --cluster --force-similarity \
    --format markdown --output "$QUARTER_DIR/org_governance.md"
if [[ $GOV_MD_EXIT -ne 0 ]]; then
    exit_on_signal_exit "$GOV_MD_EXIT" "$LOG_PREFIX  ERROR: Governance markdown export interrupted"
    echo "$LOG_PREFIX  ERROR: Governance markdown export failed (exit $GOV_MD_EXIT)" >&2
    update_overall_exit 1
fi

# --- Phase 3: Snapshot pruning ---
echo "$LOG_PREFIX Phase 3: Snapshot pruning (keeping last $KEEP_LAST)"

capture_command_exit PRUNE_EXIT uv run cja_auto_sdr --prune-snapshots --keep-last "$KEEP_LAST" --snapshot-dir "$SNAPSHOT_DIR"
case $PRUNE_EXIT in
    0) ;;
    *)
        exit_on_signal_exit "$PRUNE_EXIT" "$LOG_PREFIX  ERROR: Snapshot pruning interrupted"
        echo "$LOG_PREFIX  ERROR: Snapshot pruning failed (exit $PRUNE_EXIT)" >&2
        update_overall_exit 1
        ;;
esac

capture_command_exit ORG_PRUNE_EXIT uv run cja_auto_sdr --prune-org-report-snapshots --org-report-keep-last "$KEEP_LAST"
case $ORG_PRUNE_EXIT in
    0) ;;
    *)
        exit_on_signal_exit "$ORG_PRUNE_EXIT" "$LOG_PREFIX  ERROR: Org-report snapshot pruning interrupted"
        echo "$LOG_PREFIX  ERROR: Org-report snapshot pruning failed (exit $ORG_PRUNE_EXIT)" >&2
        update_overall_exit 1
        ;;
esac

echo "$LOG_PREFIX  Snapshots pruned"

# --- Phase 4: Compliance documentation export ---
echo "$LOG_PREFIX Phase 4: Compliance documentation export"

COMPLIANCE_DIR="$QUARTER_DIR/compliance"
mkdir -p "$COMPLIANCE_DIR"

for DV_ID in $DATA_VIEWS; do
    # Excel + markdown for compliance binders
    capture_command_exit COMP_EXIT uv run cja_auto_sdr "$DV_ID" --format reports --output-dir "$COMPLIANCE_DIR"
    case $COMP_EXIT in
        0) ;;
        2)
            echo "$LOG_PREFIX  WARNING: Compliance export exceeded quality threshold for $DV_ID" >&2
            update_overall_exit 2
            ;;
        *)
            exit_on_signal_exit "$COMP_EXIT" "$LOG_PREFIX  ERROR: Compliance export interrupted for $DV_ID"
            echo "$LOG_PREFIX  WARNING: Compliance export failed for $DV_ID (exit $COMP_EXIT)" >&2
            update_overall_exit 1
            ;;
    esac
done

echo "$LOG_PREFIX  Compliance docs exported to $COMPLIANCE_DIR"

# --- Summary ---
echo "$LOG_PREFIX === Quarterly maintenance complete (exit: $OVERALL_EXIT) ==="

# Notify on completion
if [[ -n "${SLACK_WEBHOOK:-}" ]]; then
    if ! command -v jq >/dev/null 2>&1; then
        echo "$LOG_PREFIX WARNING: jq not installed; skipping Slack notification" >&2
    else
        COLOR="good"
        [[ $OVERALL_EXIT -ne 0 ]] && COLOR="warning"

        PAYLOAD=$(jq -n \
            --arg color "$COLOR" \
            --arg title "$QUARTER Quarterly Maintenance Complete" \
            --arg text "Exit code: $OVERALL_EXIT\nReports: $QUARTER_DIR" \
            --arg footer "cja_auto_sdr quarterly maintenance" \
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

exit $OVERALL_EXIT
