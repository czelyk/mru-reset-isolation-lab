# Direct output timing in the F Prime restart experiment

The experiment rebuilds Mru Flight revision bbdad5436e0a699c07a08d07215e0122132602cf and its pinned F Prime submodule. It adds monotonic timestamp probes to the recorder and the existing fault injector. The manager, voter and replica behavior are unchanged. The F Prime topology connects the manager's delivered-result port to the recorder. Each trace row records the cycle, arrival time and whether the value equals the independent computation already used by the upstream recorder. The analyzer verifies that the rows agree with the deployed recorder's correct and wrong totals, rejects missing trace rows, and uses the recorder's first scheduled tick as the startup timing origin. Process launch and boot time are outside this interval.

The controlled interruption uses the same Linux FIFO and checkpoint setup as the released-binary experiment. On restart, the existing sequence reapplies the stuck fault at cycle 200 when its replica is eligible. A timestamp from the fault injector and the first later correct result give the observed interruption length. The post-commit case has no corresponding reinjection and starts at a different restored cycle. Its first-tick measurement is a control with different membership and parity. These Linux host measurements include instrumentation and container scheduling and do not establish target hardware timing.

## Reproduce on Windows with Docker Desktop

Run the following in PowerShell from the repository root. Each trial uses a new output directory. The initial image build downloads the upstream build dependencies.

    $lab = Join-Path (Get-Location) 'build/fprime-timing'
    New-Item -ItemType Directory -Path $lab
    $src = Join-Path $lab 'mru'
    git clone https://github.com/mruspace/flight.git $src
    git -C $src checkout --detach bbdad5436e0a699c07a08d07215e0122132602cf
    git -C $src submodule update --init --recursive
    docker build -t mru-reset-trace-build:bbdad54 -f "$src/fprime/toolchain/Dockerfile" "$src/fprime"

    $compiled = (New-Item -ItemType Directory -Path (Join-Path $lab 'compiled')).FullName
    $buildScript = (Resolve-Path scripts/build_fprime_output.sh).Path
    $instrument = (Resolve-Path scripts/instrument_fprime_output.py).Path
    docker run --rm --mount "type=bind,source=$instrument,target=/instrument.py,readonly" --mount "type=bind,source=$buildScript,target=/build.sh,readonly" --mount "type=bind,source=$compiled,target=/output" mru-reset-trace-build:bbdad54 /bin/bash /build.sh

    $trial = (New-Item -ItemType Directory -Path (Join-Path $lab 'trial')).FullName
    $probe = (Resolve-Path scripts/run_fprime_reset.sh).Path
    python -B scripts/make_fprime_seed.py (Join-Path $trial 'seed.dat')
    docker run --rm --network none --mount "type=bind,source=$compiled,target=/flight,readonly" --mount "type=bind,source=$trial,target=/output" --mount "type=bind,source=$probe,target=/probe.sh,readonly" mru-reset-trace-build:bbdad54 /bin/bash /probe.sh
    python -B scripts/analyze_fprime_output.py $trial

The full event streams, aggregate summaries, and per-output CSV are left in the trial directory.

## Observations

| Condition | First correct output from first restarted tick | First correct output after fault | Repeated correct cycle IDs |
| --- | --- | --- | --- |
| Interrupted before commit | Cycle 190, 2.119 and 1.785 ms | Cycle 202, 199.786 and 199.998 ms after reinjection at cycle 200 | 190–199 in both trials |
| Interrupted after commit | Cycle 202, 100.402 and 100.249 ms after the first tick | Fault was not reapplied to an eligible replica | None in either trial |

The two pre-commit runs delivered ten correct results whose cycle IDs had already appeared at the downstream recorder before termination. Cycle 200 had a detected disagreement and no delivered value. With slot 1 retired again, cycle 201 was the idle odd cycle in the single-replica self-check schedule and cycle 202 delivered the first correct result after the fault. The equal cycle number 202 in the post-commit runs describes a different history: those runs started at cycle 201 with slot 1 already retired. There were no incorrect deliveries in either condition.

These traces show cycle reuse at the recorder input. They do not show that a separate spacecraft consumer repeated an action. A consumer that scopes cycle IDs to a generation or deduplicates them is a competent baseline for that separate question. Boot-time revalidation was not added to F Prime in this run. The next controlled comparison should hold the initial cycle and workload constant, exercise actual boot-time revalidation, and independently observe the consumer's accepted outputs.

[Timing and build provenance](../results/fprime-output-timing.json) · [Per-output rows](../results/fprime-result-port.csv)
