#!/usr/bin/env bash
# Shared helpers for example automation wrappers.

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
