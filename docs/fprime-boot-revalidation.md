# Startup known-answer check versus ordinary recovery

Both variants use the same rebuilt native F Prime deployment and restore the same seed at cycle 190. Slot 0 is retired and slots 1 and 2 are active. The ordinary variant opens on the first scheduled tick with the upstream quorum behavior. The experimental variant uses that tick to request a known answer from the two restored active slots. It reuses the existing replica interface and retires a slot only on an explicit failing reply. Unanswered checks expire before ordinary recovery without retiring a slot. Normal computation starts on the second tick at the same cycle ID, so the time penalty is visible without introducing an initial parity change.

The same reply fixture is present in both variants. With the fault cleared, slot 1 answers normally. In the visible case every slot 1 reply is replaced by a fixed wrong value from the start of the run. In the check-blind case the startup and diagnostic replies remain correct while compute replies are replaced. The fixture runs in the manager's F Prime fault injector. It represents persistent faulty replies over each run. The separate experiment for a stimulus that survives manager restart remains necessary.

The high-water consumer accepts only results newer than the ten observed and correct pre-recovery outputs at cycles 190–199. Timing is from the first scheduled tick to the observed recorder result for the accepted cycle. Replays are offline. Counts cover logical cycles 190–208 in both variants, with the extra boot tick reported separately through wall time. Full event logs and recorder summaries remain in each local trial directory.

| Fault | First correct recorder cycle, ordinary → boot check | Approximate time to first correct recorder row | First fresh correct cycle, ordinary → boot check | Approximate time to first fresh correct row | Cycles without a result, ordinary → boot check |
| --- | --- | --- | --- | --- | ---: |
| Cleared | 190 → 190 | 2 → 102 ms | 200 → 200 | 1000 → 1101 ms | 0 → 0 |
| Visible to the check | 192 → 190 | 200 → 101 ms | 200 → 200 | 1000 → 1100 ms | 10 → 9 |
| Blind to the check | none → none | — | none → none | — | 19 → 19 |

The paired comparison was repeated twice. No incorrect or repeated result was accepted by the high-water consumer. Early detection provided one additional correct result at cycle 190 in the detectable case, but this ID was already in consumer history. Both variants eventually reached fresh cycle 200, with ordinary recovery doing so about 100 ms sooner. Keep ordinary recovery as the default for this configuration. A shorter or interrupted prior history could change the usefulness of the cycle 190 result, and the experiment does not cover that condition, test other diagnostic inputs, measure a physical reset, or estimate how often faults escape the check.

## Reproduce

Prepare the pinned Docker image with the first commands in the [timing experiment](fprime-output-timing.md#reproduce-on-windows-with-docker-desktop). Then build with both probes and run the cases from the repository root in the same PowerShell session:

    $compiled = (New-Item -ItemType Directory -Path (Join-Path $lab 'boot-compiled')).FullName
    $buildScript = (Resolve-Path scripts/build_fprime_output.sh).Path
    $instrument = (Resolve-Path scripts/instrument_fprime_output.py).Path
    $boot = (Resolve-Path scripts/instrument_fprime_boot.py).Path
    docker run --rm --mount "type=bind,source=$instrument,target=/instrument.py,readonly" --mount "type=bind,source=$boot,target=/instrument_boot.py,readonly" --mount "type=bind,source=$buildScript,target=/build.sh,readonly" --mount "type=bind,source=$compiled,target=/output" mru-reset-trace-build:bbdad54 /bin/bash /build.sh
    $trial = (New-Item -ItemType Directory -Path (Join-Path $lab 'boot-01')).FullName
    $probe = (Resolve-Path scripts/run_fprime_boot.sh).Path
    python -B scripts/make_fprime_seed.py (Join-Path $trial 'active.dat')
    docker run --rm --network none --mount "type=bind,source=$compiled,target=/flight,readonly" --mount "type=bind,source=$trial,target=/output" --mount "type=bind,source=$probe,target=/probe.sh,readonly" mru-reset-trace-build:bbdad54 /bin/bash /probe.sh
    python -B scripts/analyze_fprime_boot.py $trial $trial

Repeat in a fresh directory. The analyzer accepts both trial directories after the output directory argument. The exact upstream revisions, image ID, and replay Python version are the same as the [matched replay](fprime-matched-replay.md). The new MruQuorum SHA-256 is `b6c447163c3bd26a04d5f686e5c236169babc0dd7700a8145ce04cb4a6bcc839`.

[Result port rows and replay decisions](../results/fprime-boot-output.csv) · [Boot replies, injected faults and per-trial results](../results/fprime-boot-revalidation.json)
