#!/usr/bin/env bash
set -euo pipefail
# Keep the checkout and build on the Linux filesystem.
src=/tmp/mru
commit=bbdad5436e0a699c07a08d07215e0122132602cf
git init -q "$src"
git -C "$src" fetch -q --depth 1 https://github.com/mruspace/flight.git "$commit"
git -C "$src" checkout -q --detach FETCH_HEAD
git -C "$src" submodule update --init --recursive --depth 1
python3 -B /instrument.py "$src"
if [[ -f /instrument_boot.py ]]; then
    python3 -B /instrument_boot.py "$src"
fi
if [[ -f /instrument_replica.py ]]; then
    python3 -B /instrument_replica.py "$src"
fi
{
    git -C "$src" rev-parse HEAD
    git -C "$src" submodule status --recursive
    rustc --version
    g++ --version | head -1
    cmake --version | head -1
} >/output/build-provenance.txt
cd "$src/fprime"
fprime-util generate --build-cache /tmp/fprime-build -DCMAKE_BUILD_TYPE=Release >/output/generate.log 2>&1
fprime-util build --build-cache /tmp/fprime-build -j10 >/output/build.log 2>&1
cp /tmp/fprime-build/bin/Linux/MruQuorum /tmp/fprime-build/bin/Linux/MruReplica /output/
dictionary=/tmp/fprime-build/MruQuorum/Top/MruQuorumTopologyDictionary.json
fprime-seqgen --dictionary "$dictionary" "$src/opssat/fprime2/restart.seq" /output/restart.bin
