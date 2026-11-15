# Latest-sample restart versus replay

The [live receiver test](fprime-live-freshness.md) found that replay could deliver correct, increasing IDs whose original source samples were already too old. This experiment asks whether a restart that advances to the most recent published sample recovers usable delivery on the same F Prime manager, and whether preserving a replica's retirement changes that result.

At the first restored scheduling tick, the latest-sample policy advances the request cursor to the last contiguous published source sample. The existing manager then runs its ordinary voting or self-check logic. The source continues to publish every 100 ms, independent of the manager. Sequence IDs and timestamps are preserved. The receiver still rejects repeat IDs and samples more than 500 ms old. The analyzer verifies the selected cursor against source publication times around the manager's scan. A sample published in the scan interval may or may not be visible to that scan.

The matrix uses the same rebuilt binary with the policy disabled or enabled. It covers checkpoints at cycles 190, 198 and 199, the hash and median workloads, and three recovery conditions. These are active slot with the fault cleared, active slot with the fault present from the first restored request, and slot already retired with the same persistent-fault stimulus. Each cell runs twice. The original manager is killed at the interrupted retirement save, after outputs through cycle 199 reached the receiver. The only constructed checkpoint is the cycle-matched retired comparator. The receiver sees outputs for two seconds after restart and times its first usable result from SIGKILL. The post-restart late-onset condition from the previous experiment is outside this matrix.

The cursor jump skips both old sequence IDs the receiver already saw and some samples it never accepted. The explicit cost reported here counts skipped IDs starting at 200 and ending just before the selected cursor. Missing results at or after the selected cursor, due to fault handling or the single-replica cadence, are visible in the trace. The policy assumes each sample replaces earlier samples and neither workload needs skipped inputs to update internal state.

## Results

The main comparison included 72 restarts. The two policies ran the same binary. Across both workloads and all fault/membership conditions:

| Checkpoint restored at | Previously accepted IDs after rollback | Usable delivery with checkpoint replay | Usable delivery with latest sample |
| ---: | ---: | ---: | ---: |
| 190 | 10 | 0/12 | 12/12 |
| 198 | 2 | 0/12 | 12/12 |
| 199 | 1 | 12/12 | 12/12 |

Latest-sample restart selected cycle 203 in 35 cases and 204 in one case. It advanced past three or four previously unaccepted IDs. The first usable result's source age was 4.886–115.862 ms in the 36 latest-sample runs. In the 11 persistent-fault pairs where both sides selected 203, the first usable result arrived at cycle 204 with either replica membership. The remaining main pair selected different cycles, so it cannot isolate the membership effect.

An additional eight restarts used a 100 ms relaunch delay and a persistent fault from cycle 190 to move the selected sample by approximately one period. All eight delivered a usable result. The extra delay produced selected cycle 204 in six runs and 205 in two. In both workload pairs where the policy selected the same cycle 204 for active and retired membership, isolation moved the first usable result from cycle 206 to 204. Measured from the kill, those gains were 201.637 and 254.870 ms and include host relaunch jitter. The other two pairs selected different cycles. They remain in the raw record. The correctness oracle found zero wrong values in 1,363 output rows across all 80 restarts.

For the two replaceable inputs at the tested rates and age limit, advancing to the latest sample resolved the age failure that persisted through deeper replay. Retaining isolation can still save a cycle pair when the selected sample lands on a cycle that single-replica self-check can serve immediately. This is bounded by the inputs, parity and host scheduling of the test. Applying it to a stateful estimator or a stream that must preserve events would require a different recovery contract. The [IAC assessment](iac-2027-evidence-review.md) remains on hold pending a concrete interface that requires retaining intermediate samples or evidence that this schedule-dependent effect transfers.

[Per-restart metrics and selection evidence](../results/fprime-latest-results.csv) · [Source and receiver timing for every observed result](../results/fprime-latest-rows.csv)

## Reproduce

Build the two binaries using the [live receiver build instructions](fprime-live-freshness.md#reproduce) from this branch. For each repeat, create a fresh trial directory and add the policy and scenario options:

    $trial = (New-Item -ItemType Directory -Path (Join-Path $lab 'latest-01')).FullName
    $scripts = (Resolve-Path scripts).Path
    docker run --rm --network none --mount "type=bind,source=$compiled,target=/flight,readonly" --mount "type=bind,source=$scripts,target=/scripts,readonly" --mount "type=bind,source=$trial,target=/output" mru-reset-trace-build:bbdad54 python3 -B /scripts/run_fprime_live.py /flight /output --cycles 190 198 199 --cases active-clear active-persistent retired-persistent --policies checkpoint latest
    python -B scripts/analyze_fprime_latest.py $trial $trial

Run the same command with a fresh `latest-02` output directory for a second trial. For each of the two additional phase trials, use a new directory and run:

    $phase = (New-Item -ItemType Directory -Path (Join-Path $lab 'latest-phase-01')).FullName
    docker run --rm --network none --mount "type=bind,source=$compiled,target=/flight,readonly" --mount "type=bind,source=$scripts,target=/scripts,readonly" --mount "type=bind,source=$phase,target=/output" mru-reset-trace-build:bbdad54 python3 -B /scripts/run_fprime_live.py /flight /output --cycles 190 --cases active-persistent retired-persistent --policies latest --restart-delay-ms 100
    python -B scripts/analyze_fprime_latest.py $lab (Join-Path $lab 'latest-01') (Join-Path $lab 'latest-02') --phase-trials (Join-Path $lab 'latest-phase-01') (Join-Path $lab 'latest-phase-02')

The runner saves the raw F Prime event streams, source publication timestamps and live receiver rows. The timing is Linux host evidence. Recorded build SHA-256 values:

    MruQuorum  0db1a917962da204c030192e4f01eabe20159a5a8b8f0119fa0c014d4f9c601e
    MruReplica f822ef1b418c50b14081f34d9166d33ed98c17e311165dee868e3a0c9c9502f9
