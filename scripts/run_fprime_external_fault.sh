#!/usr/bin/env bash
set -euo pipefail

flight=/flight
out=/output
state_dir=$(mktemp -d)
pid=
trap 'if [[ -n "$pid" ]]; then kill -KILL "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true; fi' EXIT

wait_for_event() {
    local pattern=$1 log=$2
    for ((attempt=0; attempt<400; attempt++)); do
        if [[ -f "$log" ]] && grep -Eq "$pattern" "$log"; then return; fi
        if ! kill -0 "$pid" 2>/dev/null; then break; fi
        sleep 0.01
    done
    echo "Missing event $pattern in $log" >&2
    return 1
}

launch() {
    local name=$1 duration=$2
    MRU_LAB_REPLICA_FAULT_MARKER="$marker" \
        "$flight/MruQuorum" -t "$duration" -p 100 -m 128 -R "$flight/MruReplica" -C 0,1,1 \
        -f "$state" -o "$out/$name-summary.txt" >"$out/$name-events.txt" 2>&1 &
    pid=$!
}

for case in retained cleared retired; do
    state=$state_dir/$case.dat
    marker=$state_dir/$case-fault
    cp "$out/active.dat" "$state"
    launch "$case-before" 12
    wait_for_event 'StateRestored' "$out/$case-before-events.txt"
    mkfifo "$state.tmp"
    wait_for_event '^MRU_RESULT,[0-9]+,199,1$' "$out/$case-before-events.txt"
    touch "$marker"
    wait_for_event 'Replica 1 retired .* at cycle 200$' "$out/$case-before-events.txt"
    cmp -s "$out/active.dat" "$state"
    stat -c '%d:%i' "$marker" >"$out/$case-marker-before.txt"
    kill -KILL "$pid"
    rc=0
    wait "$pid" 2>/dev/null || rc=$?
    [[ $rc == 137 ]]
    pid=
    printf '%s\n' "$rc" >"$out/$case-manager-exit.txt"
    cp "$state" "$out/$case-at-kill.dat"
    unlink "$state.tmp"
    if [[ $case == cleared ]]; then
        unlink "$marker"
    fi
    if [[ $case == retired ]]; then
        cp "$out/retired.dat" "$state"
    fi
    if [[ -f "$marker" ]]; then
        stat -c '%d:%i' "$marker" >"$out/$case-marker-after.txt"
    else
        printf 'absent\n' >"$out/$case-marker-after.txt"
    fi
    launch "$case-after" 3
    wait "$pid"
    pid=
done
