# Restart into a stateful delta-v consumer

The [latest-sample experiment](fprime-latest-sample.md) showed that jumping forward can restore usable delivery for independent samples. This experiment asks what that jump costs when an estimate depends on the skipped measurements. The consumer is Basilisk's `dvAccumulation` flight-software simulation module. It consumes timestamped accelerometer batches, sorts them, and accumulates three-axis delta-v. It multiplies the new acceleration by the interval since the previous integrated timestamp. The module and its linear algebra utilities are compiled from the [pinned unmodified C sources](https://github.com/AVSLab/basilisk/blob/e5eddcb99d5f5e45472d1eae914032eddb43b88c/src/fswAlgorithms/transDetermination/dvAccumulation/dvAccumulation.c). A host adapter provides the generated message APIs in memory. [Basilisk module documentation](https://avslab.github.io/basilisk/develop/Documentation/fswAlgorithms/transDetermination/dvAccumulation/dvAccumulation.html).

## Method

Native F Prime replicas vote on the same packed three-axis measurement, with 10 bits per axis. The independent producer provides one sample every 100 ms and retains its original acquisition timestamp. Values are scaled by 0.001 m/s² per unit. The changing-acceleration profile and the constant profile are constructed inputs. The manager resumes from cycle 190 or 199 with either its checkpoint cursor or the latest published input. Three recovery conditions cover a cleared fault, a persistent fault on an active replica, and the same persistent stimulus with that replica already retired. The matrix runs twice.

The receiver process captures actual voted measurements and monotonic receipt times before and after the manager is killed. The compiled Basilisk C module subsequently replays these records with the accumulator state from the pre-kill measurements through cycle 199. The oracle integrates the complete source history with an independent Python calculation. The age limit remains the previous lab's 500 ms. An estimate is timely and correct if the last sample met that age limit at the observed receipt time and the vector differs from the complete-history result by at most 1e-9 m/s. The tolerance compares numerical implementations. It is not a navigation error budget. The compiled module also passes an analytic check for out-of-order input and duplicate timestamps.

- **Fresh-only** feeds the actual voted vectors whose age is at most 500 ms.
- **Ordered replay** feeds all actual voted vectors in increasing sequence order. It applies the age limit only to the resulting estimate, so a late sample can repair state before a timely estimate is exposed.
- **Gap-aware** accepts only the next required voted vector for integration. An unresolved gap suppresses subsequent estimates. It applies the same age limit to exposure.
- **Buffered batches** use the voted output as a release point and assume the previous samples are available from a trusted source buffer. Windows hold two, four or eight total samples, including the voted endpoint. The older batch samples come from the source trace. This measures how much history would be needed if batches were available at the recorded receipt times. F Prime voted and transmitted only the endpoint measurement in the executed tests. There is no measured batch transport or online Basilisk processing latency.

## Results

The original C accumulator ran for 288 policy comparisons across 48 native F Prime restarts, producing 2,624 state updates. For the 12 latest-sample restarts with varying acceleration:

| Consumer policy | Runs with a timely and numerically correct estimate | Error at the first timely estimate |
| --- | ---: | ---: |
| Fresh-only | 0/12 | 0.088634–0.251549 m/s |
| Ordered replay | 0/12 | 0.088634–0.251549 m/s |
| Gap-aware | 0/12 | All 149 post-restart updates withheld |
| Two-sample buffer | 0/12 | 0.062357–0.177155 m/s |
| Four-sample buffer | 3/12 | 0–0.088714 m/s |
| Eight-sample buffer | 12/12 | Within numerical tolerance |

The fresh-only policy exposed 149 timely estimates across these 12 runs. All 149 differed from the complete-sample oracle, even though F Prime delivered the correct voted acceleration vectors for those outputs. With varying acceleration, the missing intermediate values change the integral. The constant-acceleration control produced a timely, numerically correct estimate in all 12 latest-sample runs with fresh-only intake. The constant profile can hide sample loss because every missing interval has the same acceleration as the next available sample.

The eight-sample window needed at most seven actual samples in a single update. With that window, the first timely correct estimate used recorded receipt times 169.949–433.433 ms after the kill. At the 190 checkpoint, even a full buffer attached to the replayed endpoint did not recover usable delivery during the observation window because that endpoint was stale. At the 199 checkpoint, five of six varying-acceleration replays reached a timely, correct estimate. With single-sample intake, single-replica cadence introduced 24 subsequent timely errors in those checkpoint runs. The two-sample window repaired those later gaps in the tested traces.

Preserved isolation can reduce the amount of history required, but only in certain scheduling phases. In the one varying-acceleration, persistent-fault pair where both comparators selected cycle 204, the active restore first delivered at 206 and required seven samples to reconstruct the missing prefix. The retired restore first delivered at 204 and required five. This is one matched observation on the shared schedule.

The data establish a failure of age-only acceptance for these input traces. Basilisk already supports ordered batches, and a gap check is a viable baseline that suppresses output without silently accepting integration errors. The modeled buffer results support continuing only if an executed transport and voting comparison can measure whether retaining isolation reduces actual history, bus or memory costs while meeting an independently justified receiver requirement. The finding alone leaves the [IAC topic selection](iac-2027-evidence-review.md) on hold.

[Policy and error summary](../results/stateful-dv-results.csv) · [Compiled consumer updates](../results/stateful-dv-rows.csv) · [Raw source samples and voted port values](../results/stateful-dv-ingress.csv) · [Pinned source hashes](../results/stateful-dv-source-hashes.txt)

## Reproduce

Build native F Prime using the [live receiver build instructions](fprime-live-freshness.md#reproduce) from this branch. Inside the same PowerShell session, run the new sample profiles and fetch/build the pinned Basilisk consumer:

    $scripts = (Resolve-Path scripts).Path
    foreach ($name in @('imu-01','imu-02')) {
        $trial = (New-Item -ItemType Directory -Path (Join-Path $lab $name)).FullName
        docker run --rm --network none --mount "type=bind,source=$compiled,target=/flight,readonly" --mount "type=bind,source=$scripts,target=/scripts,readonly" --mount "type=bind,source=$trial,target=/output" mru-reset-trace-build:bbdad54 python3 -B /scripts/run_fprime_live.py /flight /output --cycles 190 199 --workloads imu imu-constant --cases active-clear active-persistent retired-persistent --policies checkpoint latest
    }
    $repo = (Get-Location).Path
    $dv = Join-Path $lab 'basilisk-dv'
    python -B scripts/build_basilisk_dv.py $dv --action fetch
    docker run --rm --network none --mount "type=bind,source=$repo,target=/repo,readonly" --mount "type=bind,source=$dv,target=/dv" mru-reset-trace-build:bbdad54 python3 -B /repo/scripts/build_basilisk_dv.py /dv --action build
    docker run --rm --network none --mount "type=bind,source=$scripts,target=/scripts,readonly" --mount "type=bind,source=$lab,target=/work" mru-reset-trace-build:bbdad54 python3 -B /scripts/analyze_basilisk_dv.py /work/basilisk-dv/libbasilisk_dv.so /work /work/imu-01 /work/imu-02

The runner keeps full F Prime traces and source records in the trial folders. Recorded build SHA-256 values:

    MruQuorum         35cea70e0a18c8506f0419a63e3874ac4042389644f34c5e9c152e0f77f848eb
    MruReplica        702c0a9d7fa4e1d870e9e93918008ca2bdb07581582e1bb2da72e949c624556f
    libbasilisk_dv.so 990b60fd16e700f4f124656eeb246a6e5e021bb82bdd7ef7518ad7802da778a6
