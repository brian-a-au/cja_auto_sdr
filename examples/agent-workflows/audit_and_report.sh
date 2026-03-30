#!/usr/bin/env bash
# audit_and_report.sh — Periodic audit: discover all data views, compare with
# prior snapshots (or create baselines), then run org-wide report.
#
# Designed for agent/automation use:
#   - Uses --agent-mode (expands to --format json --output - --log-format json)
#   - Parses discovery output using the dataViews JSON shape
#   - Detects first-run and creates baselines without --compare-with-prev
#   - Persists machine-readable diff and org-report JSON artifacts under REPORT_DIR
#   - Remains ID-first throughout; never uses display names for unattended ops
#
# Environment variables:
#   REPORT_DIR      — output directory for reports (default: ./reports)
#   SNAPSHOT_DIR    — snapshot directory (default: ./snapshots)
#
# Exit codes follow cja_auto_sdr conventions:
#   0 = success, 1 = error, 2 = policy/changes detected, 3 = warning

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPORT_DIR="${REPORT_DIR:-$PROJECT_ROOT/reports}"
SNAPSHOT_DIR="${SNAPSHOT_DIR:-$PROJECT_ROOT/snapshots}"
RUN_ID="$(date '+%Y%m%dT%H%M%S')"
REPORT_RUN_DIR="$REPORT_DIR/audit-$RUN_ID"
LOG_PREFIX="[$(date '+%Y-%m-%d %H:%M:%S')]"

# shellcheck source=/dev/null
source "$SCRIPT_DIR/_common.sh"

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

inspect_advisories() {
    local context="$1"
    local json="${2:-}"
    local severity="info"
    local finding_count="0"
    local actions=""

    [[ -n "$json" ]] || return 0

    severity="$(extract_advisory_severity "$json" 2>/dev/null || echo "info")"
    finding_count="$(extract_advisory_finding_count "$json" 2>/dev/null || echo "0")"

    [[ "$finding_count" =~ ^[0-9]+$ ]] || finding_count="0"
    if [[ "$finding_count" -eq 0 ]]; then
        return 0
    fi

    actions="$(extract_advisory_recommended_actions "$json" 2>/dev/null || true)"

    echo "$LOG_PREFIX  Advisories for $context: count=$finding_count severity=$severity"
    if [[ -n "$actions" ]]; then
        echo "$LOG_PREFIX  Recommended actions for $context: $actions"
    fi
}

# Prefer credentials injected by the caller/CI. Fall back to a repo-local
# .env only for workstation-style usage of this example script.
load_auth_from_project_dotenv "$PROJECT_ROOT"

cd "$PROJECT_ROOT"

echo "$LOG_PREFIX Starting audit and report"

# --- Step 1: Discover data views (ID-first, agent-mode JSON output) ---
# --agent-mode expands to --format json --output - --log-format json
capture_command_output DISCOVER_EXIT DISCOVER_OUTPUT \
    uv run cja_auto_sdr --list-dataviews --agent-mode
exit_on_signal_exit "$DISCOVER_EXIT" "$LOG_PREFIX ERROR: Discovery interrupted"

if [[ $DISCOVER_EXIT -ne 0 ]]; then
    echo "$LOG_PREFIX ERROR: Failed to list data views (exit $DISCOVER_EXIT)" >&2
    exit 1
fi

# Parse IDs from the dataViews array in the JSON response
DATA_VIEW_IDS=$(extract_dataview_ids "$DISCOVER_OUTPUT") || {
    echo "$LOG_PREFIX ERROR: Failed to parse data view IDs from discovery output" >&2
    exit 1
}

if [[ -z "$DATA_VIEW_IDS" ]]; then
    echo "$LOG_PREFIX ERROR: No data view IDs found in discovery output" >&2
    exit 1
fi

mkdir -p "$REPORT_RUN_DIR" "$SNAPSHOT_DIR"
printf '%s\n' "$DISCOVER_OUTPUT" > "$REPORT_RUN_DIR/discovery.json"

OVERALL_EXIT=0

# --- Step 2: Per-data-view snapshot comparison or baseline creation ---
for DV_ID in $DATA_VIEW_IDS; do
    echo "$LOG_PREFIX Processing data view: $DV_ID"

    # Detect whether prior snapshots exist for this data view
    capture_command_output SNAP_LIST_EXIT SNAP_LIST_OUTPUT \
        uv run cja_auto_sdr --list-snapshots --snapshot-dir "$SNAPSHOT_DIR" --format json --output - "$DV_ID" 2>/dev/null
    exit_on_signal_exit "$SNAP_LIST_EXIT" "$LOG_PREFIX ERROR: Snapshot list interrupted for $DV_ID"

    if [[ $SNAP_LIST_EXIT -ne 0 ]]; then
        echo "$LOG_PREFIX  ERROR: Snapshot list failed for $DV_ID (exit $SNAP_LIST_EXIT)" >&2
        update_overall_exit 1
        continue
    fi

    HAS_SNAPSHOTS=0
    if [[ -n "$SNAP_LIST_OUTPUT" ]]; then
        SNAP_COUNT="$(extract_snapshot_count "$SNAP_LIST_OUTPUT" 2>/dev/null)" || {
            echo "$LOG_PREFIX  ERROR: Failed to parse snapshot inventory for $DV_ID" >&2
            update_overall_exit 1
            continue
        }
        [[ "${SNAP_COUNT:-0}" -gt 0 ]] && HAS_SNAPSHOTS=1
    fi

    if [[ $HAS_SNAPSHOTS -eq 1 ]]; then
        # Prior snapshots exist — run comparison and auto-update snapshot
        echo "$LOG_PREFIX  Comparing with previous snapshot for $DV_ID"
        capture_command_output DIFF_EXIT DIFF_OUTPUT \
            uv run cja_auto_sdr "$DV_ID" --compare-with-prev --agent-mode \
                --auto-snapshot --snapshot-dir "$SNAPSHOT_DIR" 2>/dev/null
        exit_on_signal_exit "$DIFF_EXIT" "$LOG_PREFIX  ERROR: Diff comparison interrupted for $DV_ID"

        if [[ -n "$DIFF_OUTPUT" ]]; then
            printf '%s\n' "$DIFF_OUTPUT" > "$REPORT_RUN_DIR/${DV_ID}_diff.json"
        fi
        inspect_advisories "diff $DV_ID" "$DIFF_OUTPUT"

        case $DIFF_EXIT in
            0) echo "$LOG_PREFIX  No changes detected for $DV_ID" ;;
            2)
                echo "$LOG_PREFIX  Changes detected for $DV_ID"
                update_overall_exit 2
                ;;
            3)
                echo "$LOG_PREFIX  Warning threshold exceeded for $DV_ID"
                update_overall_exit 3
                ;;
            *)
                echo "$LOG_PREFIX  ERROR: Diff comparison failed for $DV_ID (exit $DIFF_EXIT)" >&2
                update_overall_exit 1
                ;;
        esac
    else
        # First run — create baseline snapshot without attempting --compare-with-prev
        echo "$LOG_PREFIX  No prior snapshots found. Creating baseline for $DV_ID"
        capture_command_exit BASELINE_EXIT \
            uv run cja_auto_sdr "$DV_ID" --snapshot "$SNAPSHOT_DIR/${DV_ID}_baseline.json"
        exit_on_signal_exit "$BASELINE_EXIT" "$LOG_PREFIX  ERROR: Baseline creation interrupted for $DV_ID"

        case $BASELINE_EXIT in
            0) echo "$LOG_PREFIX  Baseline created for $DV_ID" ;;
            *)
                echo "$LOG_PREFIX  ERROR: Baseline creation failed for $DV_ID (exit $BASELINE_EXIT)" >&2
                update_overall_exit 1
                ;;
        esac
    fi
done

# --- Step 3: Org-wide report ---
echo "$LOG_PREFIX Running org-wide report"

capture_command_output ORG_EXIT ORG_OUTPUT \
    uv run cja_auto_sdr --org-report --agent-mode
exit_on_signal_exit "$ORG_EXIT" "$LOG_PREFIX ERROR: Org report interrupted"

if [[ -n "$ORG_OUTPUT" ]]; then
    printf '%s\n' "$ORG_OUTPUT" > "$REPORT_RUN_DIR/org_report.json"
fi
inspect_advisories "org report" "$ORG_OUTPUT"

case $ORG_EXIT in
    0) echo "$LOG_PREFIX Org report: OK" ;;
    2)
        echo "$LOG_PREFIX Org report: thresholds exceeded"
        update_overall_exit 2
        ;;
    3)
        echo "$LOG_PREFIX Org report: warning threshold exceeded"
        update_overall_exit 3
        ;;
    *)
        echo "$LOG_PREFIX ERROR: Org report failed (exit $ORG_EXIT)" >&2
        update_overall_exit 1
        ;;
esac

echo "$LOG_PREFIX Reports saved to: $REPORT_RUN_DIR"
echo "$LOG_PREFIX Audit and report complete (exit: $OVERALL_EXIT)"
notify "CJA audit complete — exit $OVERALL_EXIT"

exit "$OVERALL_EXIT"
