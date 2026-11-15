# Mru Reset Isolation Lab

A host-side experiment on whether a spacecraft redundancy manager can bring a retired replica back into the voter after an interrupted save. It builds on the public Mru Flight experiment aboard ESA's OPS-SAT PRETTY.

The C++ fixture executes Mru's retirement function from two pinned snapshots. An explicit reset boundary and an ideal durable store determine which slots come back. The follow-up feeds that restored membership into Mru's original Rust voter.

## What the experiment found

- In the reset-order probe, four of 20 constructed cases restored a slot whose retirement had been reported. These cases exercise two cut points in the same event-to-save interval on both snapshots.
- In the voter probe, a persistent disagreeing reply was masked when two healthy replicas replied. When one healthy replica was already unavailable, the voter withheld output in ten of the 80 constructed cases. All 70 remaining cases delivered the expected value. Committing before reporting can remove a misleading event but does not prevent every reset before the commit.
- The result is for one modeled voting decision with prescribed replies. The fixture models persistence and restart and does not measure real hardware, timing, fault prevalence, or recovery duration.

[Reset-order rows](results/reset-order.csv) · [Voter rows](results/voter-output.csv) · [Experiment method and limitations](docs/method.md) · [Upstream source attribution](upstream/README.md)


## Recovery across cycles

A follow-up runs the original voter across 24 modeled restart scenarios. When the same diagnostic detects a persistent fault and completes within a cycle, boot revalidation and ordinary resume deliver the first correct output on the same cycle. After a fault clears, revalidation delays the first correct output by one cycle if the decision to retire the slot had not committed. When the diagnostic misses a persistent fault, both policies withhold correct output throughout the six-cycle observation window. [Scenario results](results/recovery-summary.csv) · [Cycle traces](results/recovery-trace.csv)


## Integrated F Prime test

The unmodified F Prime ARM binaries restored a valid old checkpoint when their save was interrupted. The next run restored the previously retired replica to the active set, and replaying the same fault produced a detected disagreement at cycle 200. The post-commit control retained isolation. See [the integrated test method](docs/method.md#integrated-f-prime-process-restart) and [recorded observations](results/fprime-reset-observations.json).

The follow-up instrumented the native F Prime output port. It measured two cycles from fault injection to correct output and observed repeated correct cycle IDs after a pre-commit restart. [Timing experiment and data](docs/fprime-output-timing.md).

A cycle-matched follow-up replayed the observed port output through two consumer policies. A persisted cycle watermark suppressed every repeated delivery in this ordered stream. With the same starting cycle and prior history, the faulted run with the affected replica still active delivered its first fresh correct output at cycle 202. The run that restored retirement and the fault-free control both delivered at cycle 200. [Matched replay method and data](docs/fprime-matched-replay.md).

An opt-in one-tick boot check caught a fault that corrupted the check reply. It improved the first correct recorder result in that case, but across both tested conditions with fresh delivery it added one tick to the first fresh result accepted by the consumer. Both approaches withheld output for the fault that passed the check. [Boot check experiment](docs/fprime-boot-revalidation.md).

A replica-side fixture kept the same fault state across a real Linux manager process kill. Ordinary recovery retired the re-admitted faulty replica and reached the first fresh correct cycle on the same tick as the cleared and already-retired comparators. The recorder alone showed a two-cycle difference. [External fault experiment](docs/fprime-external-replica-fault.md).

The live receiver kept a separate sample timestamp through 60 manager restarts. With the 500 ms age check, it accepted a first usable result in 18 of 20 one-cycle rollback runs and none of the 40 deeper rollback runs. With a fault delayed until cycle 200, preserved isolation advanced the first usable result by roughly two cycles in both workloads at the shallow rollback point. [Live receiver experiment](docs/fprime-live-freshness.md).

With replaceable samples, starting from the most recent published input provided usable output in all 36 main runs. Replaying the checkpoint delivered usable output in 12 of 36. The newer-input policy skipped three or four previously unseen sequence IDs. [Latest-sample comparison](docs/fprime-latest-sample.md).

## Reproduce

Prerequisites are Python 3.9+, a C++17 compiler and Rust 1.96.0 (the version used for the checked-in results). No package dependencies or credentials are needed.

Linux with GCC or Clang:

    python -B run.py --cxx g++ --verify

Windows with Zig on PATH:

    python -B run.py --cxx zig c++ --verify

Use `--rustc` to point to a local Rust compiler and omit `--verify` to write fresh results without comparing them. Generated sources, binaries and output files go under the ignored `build/` directory. GitHub Actions is configured to replay and compare the recorded CSVs.
