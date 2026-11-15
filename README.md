# Mru Reset Isolation Lab

A reproducible host-side study of replica retirement across simulated resets. The lab builds on the public Mru Flight experiment aboard ESA's OPS-SAT PRETTY.

The C++ fixture executes the retirement function from two pinned Mru Flight snapshots. It exercises reset boundaries with an ideal durable store and compares upstream event ordering with committing before reporting. The observed result is the replica membership a restart would read from the fixture's store.

## Run the reset probe

Prerequisites are Python 3.9+ and a C++17 compiler. With GCC or Clang on Linux:

    python run.py --cxx g++

On Windows with Zig:

    python run.py --cxx zig c++

The runner executes 20 deterministic reset cases and checks the expected results. It writes the generated source, binaries and CSV to the ignored build directory. See [the experiment notes](docs/method.md) and [upstream sources and license](upstream/README.md).

This is a preliminary host experiment. The durable store, reset, reference reload and event boundary are modeled. The public Mru project performed the orbit experiment.
