# Mru Reset Isolation Lab

A host-side experiment on whether a spacecraft redundancy manager can bring a retired replica back into the voter after an interrupted save. It builds on the public Mru Flight experiment aboard ESA's OPS-SAT PRETTY.

The C++ fixture executes Mru's retirement function from two pinned snapshots. An explicit reset boundary and an ideal durable store determine which slots come back. The follow-up feeds that restored membership into Mru's original Rust voter.

## What the experiment found

- In the reset-order probe, four of 20 constructed cases restored a slot whose retirement had been reported. These cases exercise two cut points in the same event-to-save interval on both snapshots.
- In the voter probe, a persistent disagreeing reply was masked when two healthy replicas replied. When one healthy replica was already unavailable, the voter withheld output in ten of the 80 constructed cases. All 70 remaining cases delivered the expected value. Committing before reporting can remove a misleading event but does not prevent every reset before the commit.
- The result is for one modeled voting decision with prescribed replies. The fixture models persistence and restart and does not measure real hardware, timing, fault prevalence, or recovery duration.

[Reset-order rows](results/reset-order.csv) · [Voter rows](results/voter-output.csv) · [Experiment method and limitations](docs/method.md) · [Upstream source attribution](upstream/README.md)

## Reproduce

Prerequisites are Python 3.9+, a C++17 compiler and Rust 1.96.0 (the version used for the checked-in results). No package dependencies or credentials are needed.

Linux with GCC or Clang:

    python -B run.py --cxx g++ --verify

Windows with Zig on PATH:

    python -B run.py --cxx zig c++ --verify

Use `--rustc` to point to a local Rust compiler and omit `--verify` to write fresh results without comparing them. Generated sources, binaries and output files go under the ignored `build/` directory. GitHub Actions is configured to replay and compare both CSVs.
