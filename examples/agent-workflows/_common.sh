#!/usr/bin/env bash
# Shared helpers for agent workflow scripts.
# Source this file: source "$(dirname "$0")/_common.sh"

set -euo pipefail

# --- Environment Validation ---
require_env() {
    local var_name="$1"
    if [[ -z "${!var_name:-}" ]]; then
        echo "ERROR: Required environment variable $var_name is not set" >&2
        exit 1
    fi
}

# --- Exit Code Handling ---
# Only documented exit codes: 0 (success), 1 (error), 2 (threshold/changes), 3 (partial), 130 (interrupted)
handle_exit_code() {
    local exit_code="$1"
    local context="${2:-command}"
    case "$exit_code" in
        0) echo "[$context] Success" ;;
        1) echo "[$context] Error — aborting" >&2; exit 1 ;;
        2) echo "[$context] Threshold/policy breach or changes detected" ;;
        3) echo "[$context] Partial success" ;;
        130) echo "[$context] Interrupted" >&2; exit 130 ;;
        *) echo "[$context] Unexpected exit code: $exit_code" >&2; exit 1 ;;
    esac
}

CJA_SIGNAL_EXIT_BASE=128
CJA_MAX_SIGNAL_NUMBER=64

is_signal_exit_code() {
    local code="${1:-0}"

    [[ "$code" =~ ^[0-9]+$ ]] || return 1
    (( code > CJA_SIGNAL_EXIT_BASE && code <= CJA_SIGNAL_EXIT_BASE + CJA_MAX_SIGNAL_NUMBER ))
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

# --- JSON Extraction Helpers ---
extract_json_field() {
    local json="$1"
    local field="$2"
    printf '%s' "$json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('$field',''))"
}

extract_advisory_severity() {
    local json="$1"
    printf '%s' "$json" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('advisories',{}).get('severity','info'))"
}

extract_dataview_ids() {
    local json="$1"
    printf '%s' "$json" | python3 -c "
import sys, json
data = json.load(sys.stdin)
for dv in data.get('dataViews', []):
    print(dv.get('id', ''))
"
}

# --- Notification Placeholder ---
notify() {
    local message="$1"
    # Override this function in your workflow for real notifications
    echo "[NOTIFY] $message"
}
