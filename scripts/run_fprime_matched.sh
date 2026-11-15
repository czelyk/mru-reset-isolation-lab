#!/usr/bin/env bash
set -euo pipefail

flight=/flight
out=/output
state_dir=$(mktemp -d)

run_case() {
    local name=$1 seed=$2
    shift 2
    local state=$state_dir/$name.dat
    cp "$out/$seed.dat" "$state"
    "$flight/MruQuorum" -t 3 -p 100 -m 128 -R "$flight/MruReplica" -C 0,1,1 \
        -f "$state" -o "$out/$name-summary.txt" "$@" >"$out/$name-events.txt" 2>&1
}

run_case history active
run_case active-fault active -s "$flight/restart.bin"
run_case retired-fault retired -s "$flight/restart.bin"
run_case active-control active
