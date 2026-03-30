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

load_auth_from_project_dotenv() {
    local project_root="$1"
    local dotenv_path="${2:-$project_root/.env}"
    local dotenv_values=""
    local key=""
    local value=""

    if [[ -n "${ORG_ID:-}" && -n "${CLIENT_ID:-}" && -n "${SECRET:-}" && -n "${SCOPES:-}" ]]; then
        return 0
    fi

    if [[ ! -f "$dotenv_path" ]]; then
        return 0
    fi

    dotenv_values="$(
        (
            set -a
            # shellcheck source=/dev/null
            source "$dotenv_path"
            set +a

            printf 'ORG_ID=%s\n' "${ORG_ID:-}"
            printf 'CLIENT_ID=%s\n' "${CLIENT_ID:-}"
            printf 'SECRET=%s\n' "${SECRET:-}"
            printf 'SCOPES=%s\n' "${SCOPES:-}"
        )
    )" || return 1

    while IFS='=' read -r key value; do
        case "$key" in
            ORG_ID)
                if [[ -z "${ORG_ID:-}" && -n "$value" ]]; then
                    ORG_ID="$value"
                    export ORG_ID
                fi
                ;;
            CLIENT_ID)
                if [[ -z "${CLIENT_ID:-}" && -n "$value" ]]; then
                    CLIENT_ID="$value"
                    export CLIENT_ID
                fi
                ;;
            SECRET)
                if [[ -z "${SECRET:-}" && -n "$value" ]]; then
                    SECRET="$value"
                    export SECRET
                fi
                ;;
            SCOPES)
                if [[ -z "${SCOPES:-}" && -n "$value" ]]; then
                    SCOPES="$value"
                    export SCOPES
                fi
                ;;
        esac
    done <<< "$dotenv_values"
}

# --- Exit Code Handling ---
# Only documented exit codes: 0 (success), 1 (error), 2 (threshold/changes), 3 (warning threshold), 130 (interrupted)
handle_exit_code() {
    local exit_code="$1"
    local context="${2:-command}"
    case "$exit_code" in
        0) echo "[$context] Success" ;;
        1) echo "[$context] Error — aborting" >&2; exit 1 ;;
        2) echo "[$context] Threshold/policy breach or changes detected" ;;
        3) echo "[$context] Warning threshold exceeded" ;;
        130) echo "[$context] Interrupted" >&2; exit 130 ;;
        *) echo "[$context] Unexpected exit code: $exit_code" >&2; exit 1 ;;
    esac
}

is_signal_exit_code() {
    local code="${1:-0}"
    [[ "$code" == "130" ]]
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

extract_advisory_finding_count() {
    local json="$1"
    printf '%s' "$json" | python3 -c "
import sys, json

data = json.load(sys.stdin)
findings = (data.get('advisories') or {}).get('findings') or []
print(len(findings))
"
}

extract_advisory_recommended_actions() {
    local json="$1"
    printf '%s' "$json" | python3 -c "
import sys, json

data = json.load(sys.stdin)
actions = (data.get('advisories') or {}).get('recommended_actions') or []
print(','.join(actions))
"
}

extract_highest_quality_severity_from_run_summary() {
    local json="$1"
    printf '%s' "$json" | python3 -c "
import json, sys

order = ['CRITICAL', 'HIGH', 'MEDIUM', 'LOW', 'INFO']

try:
    payload = json.load(sys.stdin)
except Exception:
    print('unknown')
    raise SystemExit(0)

for result in payload.get('results', []):
    counts = result.get('dq_severity_counts') or {}
    for severity in order:
        if int(counts.get(severity, 0) or 0) > 0:
            print(severity)
            raise SystemExit(0)

print('unknown')
"
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

extract_snapshot_count() {
    local json="$1"
    printf '%s' "$json" | python3 -c "
import sys, json

data = json.load(sys.stdin)
snapshots = data if isinstance(data, list) else data.get('snapshots', [])
print(len(snapshots))
"
}

# --- Notification Placeholder ---
notify() {
    local message="$1"
    # Override this function in your workflow for real notifications
    echo "[NOTIFY] $message"
}
