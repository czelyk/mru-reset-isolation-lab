#!/usr/bin/env bash
# Run the upstream ARM binaries. The FIFO deliberately stops one normal checkpoint write.
set -euo pipefail

flight=/flight
out=/output
case_dir=$(mktemp -d)
# The container owns the temporary Linux path and will remove it when it exits.
state=$case_dir/state.dat
pid=
cleanup() {
    if [[ -n "$pid" ]]; then
        kill -KILL "$pid" 2>/dev/null || true
        wait "$pid" 2>/dev/null || true
    fi
}
trap cleanup EXIT

wait_for_event() {
    local pattern=$1 file=$2
    for ((attempt=0; attempt<700; attempt++)); do
        if grep -q "$pattern" "$file"; then
            return
        fi
        if ! kill -0 "$pid" 2>/dev/null; then
            break
        fi
        sleep 0.02
    done
    echo "Missing event: $pattern in $file" >&2
    return 1
}

deploy() {
    local name=$1 seconds=$2
    shift 2
    "$flight/MruQuorum" -t "$seconds" -p 100 -m 128 -R "$flight/MruReplica" -C 0,1,1 \
        -f "$state" -o "$out/$name-summary.txt" "$@" >"$out/$name-events.txt" 2>&1 &
    pid=$!
}

for cut in precommit postcommit; do
    cp "$out/seed.dat" "$state"
    deploy "$cut-before" 12 -s "$flight/restart.bin"
    # Startup SET_POLICY also saves. Arm only after that command and the first cycle.
    wait_for_event 'StateRestored' "$out/$cut-before-events.txt"
    if [[ $cut == precommit ]]; then
        mkfifo "$state.tmp"
    fi
    wait_for_event 'Replica 1 retired' "$out/$cut-before-events.txt"
    if [[ $cut == postcommit ]]; then
        for ((attempt=0; attempt<150; attempt++)); do
            if ! cmp -s "$out/seed.dat" "$state"; then
                break
            fi
            sleep 0.02
        done
        if cmp -s "$out/seed.dat" "$state"; then
            echo "Retirement was never committed" >&2
            exit 1
        fi
    else
        # Record each task's kernel wait channel before terminating the manager.
        # The trace is supplementary to the observed checkpoint and event.
        for task in /proc/"$pid"/task/*; do
            printf '%s ' "$task"
            cat "$task/wchan" 2>/dev/null || true
            printf '\n'
        done >"$out/precommit-wait-channels.txt"
        cmp -s "$out/seed.dat" "$state"
    fi
    kill -KILL "$pid"
    rc=0
    wait "$pid" 2>/dev/null || rc=$?
    [[ $rc == 137 ]]
    pid=
    cp "$state" "$out/$cut-at-kill.dat"
    if [[ $cut == precommit ]]; then
        unlink "$state.tmp"
    fi
    sleep 1

    # The upstream launcher creates new replica processes. The original sequence
    # reapplies the same fault when the restored counter reaches 200.
    deploy "$cut-after" 3 -s "$flight/restart.bin"
    wait "$pid"
    pid=
done
