#!/usr/bin/env bash
# quarterly_governance.sh — Quarterly governance review: trending analysis,
# threshold enforcement, and human-facing artifact generation.
#
# Designed for agent/automation use:
#   - Uses --agent-mode (expands to --format json --output - --log-format json)
#   - Parses structured JSON from org-report for programmatic decisions
#   - Generates human-facing artifacts (markdown) as a separate pass
#   - Emits a compact summary at completion
#
# Environment variables:
#   REPORT_DIR       — output directory for reports (default: ./reports)
#   TRENDING_WINDOW  — number of snapshots for drift window (default: 4)
#
# Exit codes follow cja_auto_sdr conventions:
#   0 = success, 1 = error, 2 = policy threshold exceeded

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
REPORT_DIR="${REPORT_DIR:-$PROJECT_ROOT/reports}"
TRENDING_WINDOW="${TRENDING_WINDOW:-4}"
QUARTER="Q$(( ($(date +%-m) - 1) / 3 + 1 ))-$(date +%Y)"
QUARTER_DIR="$REPORT_DIR/$QUARTER"
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

cd "$PROJECT_ROOT"

echo "$LOG_PREFIX === Quarterly governance: $QUARTER (window=$TRENDING_WINDOW) ==="

mkdir -p "$QUARTER_DIR"

OVERALL_EXIT=0

# --- Step 1: Org-report with trending analysis (machine-readable, agent-mode) ---
echo "$LOG_PREFIX Running org-report with trending (window=$TRENDING_WINDOW)"

capture_command_output ORG_EXIT ORG_OUTPUT \
    uv run cja_auto_sdr --org-report \
        --trending-window "$TRENDING_WINDOW" \
        --fail-on-threshold \
        --agent-mode
exit_on_signal_exit "$ORG_EXIT" "$LOG_PREFIX ERROR: Org report interrupted"

# Persist the machine-readable report for downstream tooling
printf '%s\n' "$ORG_OUTPUT" > "$QUARTER_DIR/org_governance.json"

case $ORG_EXIT in
    0)
        echo "$LOG_PREFIX Org governance report: PASS"
        ;;
    2)
        echo "$LOG_PREFIX Org governance report: THRESHOLDS EXCEEDED — see $QUARTER_DIR/org_governance.json"
        OVERALL_EXIT=2
        notify "Quarterly governance threshold exceeded — $QUARTER"
        ;;
    *)
        echo "$LOG_PREFIX ERROR: Org governance report failed (exit $ORG_EXIT)" >&2
        exit 1
        ;;
esac

# --- Step 2: Human-facing artifact (markdown) — generated separately ---
echo "$LOG_PREFIX Generating human-facing governance report (markdown)"

capture_command_exit MD_EXIT \
    uv run cja_auto_sdr --org-report \
        --trending-window "$TRENDING_WINDOW" \
        --format markdown \
        --output "$QUARTER_DIR/org_governance.md"
exit_on_signal_exit "$MD_EXIT" "$LOG_PREFIX ERROR: Markdown export interrupted"

case $MD_EXIT in
    0)
        echo "$LOG_PREFIX Markdown governance report saved: $QUARTER_DIR/org_governance.md"
        ;;
    2)
        echo "$LOG_PREFIX Markdown report: threshold exceeded (recorded)"
        [[ $OVERALL_EXIT -ne 1 ]] && OVERALL_EXIT=2
        ;;
    *)
        echo "$LOG_PREFIX WARNING: Markdown export failed (exit $MD_EXIT); continuing" >&2
        [[ $OVERALL_EXIT -ne 2 ]] && OVERALL_EXIT=1
        ;;
esac

# --- Step 3: Compact summary ---
GOVERNANCE_STATUS="PASS"
[[ $OVERALL_EXIT -eq 2 ]] && GOVERNANCE_STATUS="THRESHOLDS_EXCEEDED"
[[ $OVERALL_EXIT -eq 1 ]] && GOVERNANCE_STATUS="ERROR"

echo "$LOG_PREFIX === Summary: quarter=$QUARTER status=$GOVERNANCE_STATUS exit=$OVERALL_EXIT ==="
echo "$LOG_PREFIX Reports saved to: $QUARTER_DIR"

notify "Quarterly governance $QUARTER — $GOVERNANCE_STATUS"

exit "$OVERALL_EXIT"
