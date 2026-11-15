# Replica-side fault state across a manager process kill

This test asks whether rollback re-admits an affected replica when the fault's enabling state lives outside the manager. Only replica 1 checks for an external file before producing its response. While that file exists, it sends the same fixed wrong value for compute and known-answer requests. The file is a controlled software fixture for the repeated wrong-value symptom, not a model of radiation or hardware physics. See the [upstream fault model](https://github.com/mruspace/flight/blob/main/docs/fault-model.md).

Each case starts in native F Prime at cycle 190 with slot 0 retired and slots 1 and 2 active. The manager delivers cycles 190–199. The harness enables the external fault just after observing cycle 199. The replica produces a bad compute and a bad known-answer reply on cycle 200. As the manager reports retirement, a FIFO blocks the checkpoint write. The harness sends SIGKILL, checks exit 137 and verifies that the checkpoint file still equals the old active seed.

On restart, the retained case leaves the original marker and checkpoint in place. The cleared control removes the marker. The retired comparator retains the same marker but installs a controlled checkpoint with slots 0 and 1 retired and the same restored cycle 190. This comparator measures membership at a fixed logical phase. It does not claim that this checkpoint would have been produced by completing the interrupted save. The comparison uses upstream ordinary recovery and no replayed command sequence. The new replica PID and its bad reply at cycle 190 directly verify that the retained stimulus affects the replica after restart.

Replay scores the observed port rows against the actual pre-kill outputs from the same experiment. Timing starts at the first scheduled tick after restart. It excludes the duration of the kill and relaunch. The consumer is an offline replay with independent committed state.

| After restart | First correct recorder cycle | Time to that row | First fresh correct cycle accepted in replay | Time to that row |
| --- | ---: | ---: | ---: | ---: |
| Fault retained, slot active | 192 | 200.031 and 199.893 ms | 200 | 1000.478 and 1000.276 ms |
| Fault cleared, slot active | 190 | 1.437 and 1.689 ms | 200 | 1000.928 and 1000.732 ms |
| Fault retained, slot retired | 190 | 1.295 and 3.094 ms | 200 | 1000.399 and 1000.505 ms |

The retained active case re-retired slot 1 at cycle 190 in both trials. The cleared and already-retired comparators had no post-restart faulted reply. All six replays rejected repeated IDs and accepted zero wrong results. Earlier isolation improved the first correct recorder output by two logical cycles in this test. Both extra cycles fell within history the consumer had already accepted, so there was no observed gain in fresh delivery. This differs from the [fault scheduled for cycle 200](fprime-matched-replay.md), where ordinary recovery had no earlier opportunity to diagnose the fault.

The reset was a Linux user-space manager kill. The same kernel and filesystem remained available, and the replica processes were relaunched. The marker file says nothing about the persistence of a fault through board reset or loss of power. A bench test would require independently powered manager and replica or stimulus hardware and a recorder outside both reset domains. No such hardware was used.

## Reproduce

Prepare the pinned Docker image from the [timing experiment](fprime-output-timing.md#reproduce-on-windows-with-docker-desktop). Build the instrumented manager and replica in the same PowerShell session:

    $compiled = (New-Item -ItemType Directory -Path (Join-Path $lab 'external-compiled')).FullName
    $buildScript = (Resolve-Path scripts/build_fprime_output.sh).Path
    $instrument = (Resolve-Path scripts/instrument_fprime_output.py).Path
    $replica = (Resolve-Path scripts/instrument_fprime_replica.py).Path
    docker run --rm --mount "type=bind,source=$instrument,target=/instrument.py,readonly" --mount "type=bind,source=$replica,target=/instrument_replica.py,readonly" --mount "type=bind,source=$buildScript,target=/build.sh,readonly" --mount "type=bind,source=$compiled,target=/output" mru-reset-trace-build:bbdad54 /bin/bash /build.sh
    $trial = (New-Item -ItemType Directory -Path (Join-Path $lab 'external-01')).FullName
    $probe = (Resolve-Path scripts/run_fprime_external_fault.sh).Path
    python -B scripts/make_fprime_seed.py (Join-Path $trial 'active.dat')
    python -B scripts/make_fprime_seed.py --retire-slot-1 (Join-Path $trial 'retired.dat')
    docker run --rm --network none --mount "type=bind,source=$compiled,target=/flight,readonly" --mount "type=bind,source=$trial,target=/output" --mount "type=bind,source=$probe,target=/probe.sh,readonly" mru-reset-trace-build:bbdad54 /bin/bash /probe.sh
    python -B scripts/analyze_fprime_external_fault.py $trial $trial

Repeat with a fresh output directory. The runner leaves full event streams, restart summaries, input seeds, old checkpoints, manager exit status and external file identity in each trial directory. See the [matched replay](fprime-matched-replay.md) for the common build identifiers. The manager SHA-256 matches that experiment. The instrumented MruReplica SHA-256 is `f639840e28bb171ad05367a8ee867eacfea8a69977234f8aefa85c942b7d916f`.

[Raw result rows and replay decisions](../results/fprime-external-fault-output.csv) · [Process IDs, marker identities and per-trial scores](../results/fprime-external-fault.json)
