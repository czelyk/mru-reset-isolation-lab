# F Prime recovery with a live timestamp-aware receiver

The experiment measures the first correct result the receiver can actually use after the manager is killed and relaunched. A result can have a newer sequence number and still come from a sample that is too old. NASA Astrobee checks the age of the first setpoint when accepting a trajectory segment. This lab applies the same 500 ms age threshold to its own source samples. Astrobee's trajectory interface and timer behavior are outside the model. [Astrobee acceptance code](https://github.com/nasa/astrobee/blob/master/gnc/ctl/src/ctl_ros.cc#L41-L52) · [Threshold definition](https://github.com/nasa/astrobee/blob/master/gnc/ctl/include/ctl/ctl_ros.h#L77-L78).

## Method

A producer thread in a process outside the manager publishes a sample every 100 ms. An atomic file publication gives Mru replicas the same sample for a given cycle and assigns an original timestamp once. The source keeps publishing while the manager is down. Every result carries the original source timestamp via its cycle association. The native F Prime result-port recorder logs the delivered numeric value. A live receiver reads that pipe in the producer's host process, records its own receipt time and retains the accepted cycle across both manager instances. The producer, port recorder and receiver share one Linux monotonic clock.

The pipe feeds two receivers with the same ordered stream. The sequence-only comparison accepts any cycle newer than its last accepted one. The age-aware receiver checks that rule and discards a sample whose age exceeds 500 ms. An independent Python calculation scores result correctness. Neither acceptance rule can use that calculation. The two payloads run through the same native redundancy manager. One hashes the first sample value over a 4 KiB working block. The other returns the median of three generated sample values. They use different calculations and the same manager cadence, including the even-cycle restriction in single-replica self-check mode.

In every run, the harness activates a fixed wrong reply on replica 1 after the receiver has seen cycle 199. At cycle 200, the harness observes retirement, interrupts the checkpoint save with a FIFO and sends SIGKILL. It verifies the original active checkpoint bytes and restores the same logical cycle used before the cut. The retired comparator supplies an otherwise matching checkpoint with replica 1 retired. It separates replica membership from the restored cycle. The selected seeds restore at 190, 198 or 199, leaving 10, 2 or 1 previously accepted IDs, respectively. These include both parities.

On restart, the five conditions use an active replica with the fault cleared, active or retired membership with the fault present from the first restored cycle, and active or retired membership with the fault again visible from cycle 200. The last pair models delayed manifestation at a matched cycle. It keeps the external marker and applies a cycle condition in the fixture. The normal deployment has no command sequence in these tests. The first accepted result is timed from SIGKILL, including the relaunch. Each restarted deployment runs for two seconds. The 100 ms period, sample data and fault stimulus are laboratory inputs.

## Results

Two full trials produced 60 manager restarts and 960 result rows. The producer published two or three new samples between each kill and the first restarted tick. The independent oracle found zero incorrect outputs. After restart, the live policy rejected 168 old IDs and 356 newer IDs whose source samples exceeded the age limit.

| Restored cycle | Old IDs in receiver history at that cycle or later | Age of first correct sequence-only acceptance | Live receiver obtained a usable result |
| ---: | ---: | ---: | ---: |
| 190 | 10 | 1341.589–1409.717 ms | 0/20 |
| 198 | 2 | 583.785–601.167 ms | 0/20 |
| 199 | 1 | 482.968–508.175 ms | 18/20 |

Sequence-only acceptance advanced in all 60 runs. When recovery started at 199 and the fault became visible at cycle 200, preserved isolation moved the first usable result from cycle 202 to 200 in all four workload/trial pairs. Measured from the kill, the paired gains were 194.811 and 200.939 ms for the hash, and 190.676 and 199.196 ms for the median. When the fault was already present at restart, all eight corresponding cases accepted at cycle 200. Two of the four fault-cleared controls starting at 199 had no usable result within the window. Their first sequence-only rows were 501.793 and 508.175 ms old, which exposes how sensitive this configuration is near the 500 ms threshold.

The tested producer and manager advance at the same nominal rate. A manager that falls behind cannot generally erase that accumulated delay in this setup. Preserving isolation addresses the missing cycle after delayed fault detection, while its benefit for usable delivery depends on the age of the source sample. The two workloads use the same manager and cadence. The campaign establishes a repeatable bounded result on the host and leaves cross-schedule transfer, physical reset and flight timing open. It also leaves untested the comparison with resuming at the latest available sample. For an interface that permits dropping old samples, that is a meaningful competing policy. The existing [IAC evidence review](iac-2027-evidence-review.md) remains provisional.

[Per-restart metrics](../results/fprime-live-results.csv) · [Source, port and receiver timestamps for every observed result](../results/fprime-live-rows.csv)

## Reproduce

Prepare the pinned Docker image from the [direct output timing experiment](fprime-output-timing.md#reproduce-on-windows-with-docker-desktop). Build and run the live campaign from the repository root in the same PowerShell session:

    $compiled = (New-Item -ItemType Directory -Path (Join-Path $lab 'live-compiled')).FullName
    $buildScript = (Resolve-Path scripts/build_fprime_output.sh).Path
    $instrument = (Resolve-Path scripts/instrument_fprime_output.py).Path
    $replica = (Resolve-Path scripts/instrument_fprime_replica.py).Path
    $live = (Resolve-Path scripts/instrument_fprime_live.py).Path
    docker run --rm --mount "type=bind,source=$instrument,target=/instrument.py,readonly" --mount "type=bind,source=$replica,target=/instrument_replica.py,readonly" --mount "type=bind,source=$live,target=/instrument_live.py,readonly" --mount "type=bind,source=$buildScript,target=/build.sh,readonly" --mount "type=bind,source=$compiled,target=/output" mru-reset-trace-build:bbdad54 /bin/bash /build.sh
    $scripts = (Resolve-Path scripts).Path
    $trial = (New-Item -ItemType Directory -Path (Join-Path $lab 'live-01')).FullName
    docker run --rm --network none --mount "type=bind,source=$compiled,target=/flight,readonly" --mount "type=bind,source=$scripts,target=/scripts,readonly" --mount "type=bind,source=$trial,target=/output" mru-reset-trace-build:bbdad54 python3 -B /scripts/run_fprime_live.py /flight /output
    python -B scripts/analyze_fprime_live.py $trial $trial

Repeat in a fresh directory and pass both trial directories after the analyzer's output path. The runner keeps the full runtime logs, source samples, per-row receiver decisions and restart metadata. The analyzer verifies the logged input age, rescores both policies and checks the result against the live records. The exact upstream revisions and image ID are those of the [matched replay](fprime-matched-replay.md). The Linux runner used Python 3.11.2. Build hashes for the recorded binaries:

    MruQuorum  5930d1fba4de974c5bccda1e5f3fb17ceaa44240ca2b6cb5ea5b70b016328d65
    MruReplica f822ef1b418c50b14081f34d9166d33ed98c17e311165dee868e3a0c9c9502f9
