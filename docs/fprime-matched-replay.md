# Cycle-matched F Prime output replay

This experiment holds the restored start cycle at 190 across three Linux process-level runs. Slot 0 is always retired. Slot 2 is always active. Each run restores a valid seed before its first decision. The 100 ms period, deployment, replica processes and workload are the same.

An independent, fault-free run supplies actual correct result-port records for cycles 190–199. Each replay starts with those same ten records already accepted. The active-fault and retired-fault cases use the same command sequence, which schedules a stuck result for slot 1 at cycle 200. When retired membership is restored, the deployment skips the fault on that slot. The active control runs without the command sequence and uses the same shrinking policy as the seed.

The pass-through consumer accepts every result. The second consumer records its highest accepted cycle in a local SQLite database. The replay closes and reopens the connection after ingesting the ten prior records. It accepts only IDs above the stored cycle. Both consumers accept based on policy without access to the recorder's correctness label, which is used only for scoring.

| Condition | Repeats accepted by pass-through, per trial | Repeats accepted by high-water, per trial | First fresh correct cycle, both policies | From first scheduled tick to that result-port record |
| --- | ---: | ---: | ---: | ---: |
| Slot 1 active, stuck fault applied | 10 | 0 | 202 | 1200.345 and 1200.343 ms |
| Slot 1 retired, same sequence | 5 | 0 | 200 | 1000.435 and 1000.388 ms |
| Slot 1 active, fault-free control | 10 | 0 | 200 | 1000.615 and 1000.576 ms |

Both trials recorded a detected disagreement and retirement at cycle 200 in the active-fault case. The run did not deliver a result that cycle. It then followed the single-replica self-check schedule and delivered at cycle 202. The retired checkpoint followed that schedule from the start, so only even prior cycle IDs reappeared. Neither consumer accepted a wrong result in these trials.

A durable watermark sufficed for replay suppression in this single ordered stream. It could not supply a missing result at cycle 200. Under this particular checkpoint, sequence and parity, restored retirement recovered that cycle. The experiment measures a fresh result at the recorder, with acceptance evaluated offline. It does not measure SQLite processing latency, downtime across the real checkpoint interruption, actuator side effects, or behavior when legitimate lower IDs can arrive out of order or be reused by a new stream. The two constructed trials establish neither the size of a field effect nor its prevalence. A fault maintained outside the manager reset domain remains a separate test.

## Reproduce

Build the instrumented native binaries using the build steps in the [direct output timing experiment](fprime-output-timing.md#reproduce-on-windows-with-docker-desktop), then run the following PowerShell commands from the repository root in the same session:

    $trial = (New-Item -ItemType Directory -Path (Join-Path $lab 'matched-01')).FullName
    $probe = (Resolve-Path scripts/run_fprime_matched.sh).Path
    python -B scripts/make_fprime_seed.py (Join-Path $trial 'active.dat')
    python -B scripts/make_fprime_seed.py --retire-slot-1 (Join-Path $trial 'retired.dat')
    docker run --rm --network none --mount "type=bind,source=$compiled,target=/flight,readonly" --mount "type=bind,source=$trial,target=/output" --mount "type=bind,source=$probe,target=/probe.sh,readonly" mru-reset-trace-build:bbdad54 /bin/bash /probe.sh
    python -B scripts/replay_fprime_consumer.py $trial $trial

Repeat with a fresh trial directory. The analyzer accepts multiple trial paths after the output directory. The runner retains complete event logs, recorder summaries and input checkpoints in each trial directory. The checked-in CSV and JSON contain the observed rows used by the replay, the consumer decisions and the fault/retirement evidence.

Recorded software uses Mru Flight `bbdad5436e0a699c07a08d07215e0122132602cf`, F Prime `558b7ef48edd5d25f3bdddcbbe7afddb9cc22d09`, Docker image `sha256:8c194b33cbde940aaea9a175855f3258e63e14bf40c5b41da3609a2746ba067b` and Python 3.12.10 for replay. SHA-256 identifiers for the recorded inputs are:

    MruQuorum   f8e597ad01de927adc10199854f6d565337c004d099ec9f831cc36ba8293ead2
    MruReplica  848ef9a2a65f4fc96c23875f152e2ed5c6f3bee07e376cdc93f16c1bcef5613d
    restart.bin 4d11c45ac9a1a898feb02d6157092d80abe4c60d64898f9a7cd16edb69767755

[Result rows and replay decisions](../results/fprime-matched-output.csv) · [Per-trial summary and markers](../results/fprime-matched-replay.json)
