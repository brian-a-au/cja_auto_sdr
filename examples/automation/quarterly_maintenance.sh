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

# Load credentials
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$PROJECT_ROOT/.env"
    set +a
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
    python3 -c "import sys,json; [print(dv['id']) for dv in json.load(sys.stdin)]" 2>/dev/null) || {
    echo "$LOG_PREFIX ERROR: Failed to list data views" >&2
    exit 1
}

mkdir -p "$QUARTER_DIR" "$SNAPSHOT_DIR"

OVERALL_EXIT=0

# --- Phase 1: Full SDR regeneration (all views, all formats) ---
echo "$LOG_PREFIX Phase 1: Full SDR regeneration"

for DV_ID in $DATA_VIEWS; do
    echo "$LOG_PREFIX  Generating all formats for $DV_ID"
    SDR_EXIT=0
    uv run cja_auto_sdr "$DV_ID" --format all --output-dir "$QUARTER_DIR" || SDR_EXIT=$?

    case $SDR_EXIT in
        0) echo "$LOG_PREFIX  OK" ;;
        2) echo "$LOG_PREFIX  WARNING: Quality threshold exceeded for $DV_ID"; OVERALL_EXIT=2 ;;
        *) echo "$LOG_PREFIX  ERROR: SDR generation failed for $DV_ID (exit $SDR_EXIT)" >&2; OVERALL_EXIT=1 ;;
    esac

    # Update baseline snapshot
    uv run cja_auto_sdr "$DV_ID" --snapshot "$SNAPSHOT_DIR/${DV_ID}_baseline.json"
done

# --- Phase 2: Cross-org governance review ---
echo "$LOG_PREFIX Phase 2: Cross-org governance review"

GOV_EXIT=0
uv run cja_auto_sdr --org-report --cluster --force-similarity \
    --format json --output - > "$QUARTER_DIR/org_governance.json" 2>/dev/null || GOV_EXIT=$?

case $GOV_EXIT in
    0) echo "$LOG_PREFIX  Governance review: PASS" ;;
    2) echo "$LOG_PREFIX  Governance review: THRESHOLDS EXCEEDED — see org_governance.json" ;;
    *) echo "$LOG_PREFIX  ERROR: Governance review failed (exit $GOV_EXIT)" >&2; OVERALL_EXIT=1 ;;
esac

# Also generate human-readable governance report
uv run cja_auto_sdr --org-report --cluster --force-similarity \
    --format markdown --output - > "$QUARTER_DIR/org_governance.md" 2>/dev/null || true

# --- Phase 3: Snapshot pruning ---
echo "$LOG_PREFIX Phase 3: Snapshot pruning (keeping last $KEEP_LAST)"

uv run cja_auto_sdr --prune-snapshots --keep-last "$KEEP_LAST" --snapshot-dir "$SNAPSHOT_DIR" || true
uv run cja_auto_sdr --prune-org-report-snapshots --org-report-keep-last "$KEEP_LAST" || true

echo "$LOG_PREFIX  Snapshots pruned"

# --- Phase 4: Compliance documentation export ---
echo "$LOG_PREFIX Phase 4: Compliance documentation export"

COMPLIANCE_DIR="$QUARTER_DIR/compliance"
mkdir -p "$COMPLIANCE_DIR"

for DV_ID in $DATA_VIEWS; do
    # Excel + markdown for compliance binders
    COMP_EXIT=0
    uv run cja_auto_sdr "$DV_ID" --format reports --output-dir "$COMPLIANCE_DIR" || COMP_EXIT=$?
    [[ $COMP_EXIT -ne 0 ]] && echo "$LOG_PREFIX  WARNING: Compliance export failed for $DV_ID" >&2
done

echo "$LOG_PREFIX  Compliance docs exported to $COMPLIANCE_DIR"

# --- Summary ---
echo "$LOG_PREFIX === Quarterly maintenance complete (exit: $OVERALL_EXIT) ==="

# Notify on completion
if [[ -n "${SLACK_WEBHOOK:-}" ]]; then
    COLOR="good"
    [[ $OVERALL_EXIT -ne 0 ]] && COLOR="warning"

    curl -s -X POST "$SLACK_WEBHOOK" \
        -H 'Content-Type: application/json' \
        -d "{
            \"attachments\": [{
                \"color\": \"$COLOR\",
                \"title\": \"$QUARTER Quarterly Maintenance Complete\",
                \"text\": \"Exit code: $OVERALL_EXIT\nReports: $QUARTER_DIR\",
                \"footer\": \"cja_auto_sdr quarterly maintenance\",
                \"ts\": $(date +%s)
            }]
        }" > /dev/null
    echo "$LOG_PREFIX Slack notification sent"
fi

exit $OVERALL_EXIT
