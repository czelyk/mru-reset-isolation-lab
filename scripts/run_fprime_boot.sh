#!/usr/bin/env bash
set -euo pipefail

flight=/flight
out=/output
state_dir=$(mktemp -d)

run_case() {
    local name=$1 boot=$2 fault=$3
    local state=$state_dir/$name.dat
    cp "$out/active.dat" "$state"
    MRU_LAB_BOOT_CHECK=$boot MRU_LAB_REPLY_FAULT=$fault \
        "$flight/MruQuorum" -t 3 -p 100 -m 128 -R "$flight/MruReplica" -C 0,1,1 \
        -f "$state" -o "$out/$name-summary.txt" >"$out/$name-events.txt" 2>&1
}

run_case history 0 cleared
for fault in cleared visible blind; do
    run_case "$fault-ordinary" 0 "$fault"
    run_case "$fault-revalidate" 1 "$fault"
done
