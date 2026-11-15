"""Add experiment-only monotonic timestamps to the pinned F Prime deployment."""

import argparse
import subprocess
from pathlib import Path

MRU_COMMIT = "bbdad5436e0a699c07a08d07215e0122132602cf"
CLOCK = """
#include <cstdio>
#include <ctime>

namespace {
unsigned long long traceMonotonicNs() {
    timespec ts{};
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) {
        return 0;
    }
    return static_cast<unsigned long long>(ts.tv_sec) * 1000000000ULL
           + static_cast<unsigned long long>(ts.tv_nsec);
}
}  // namespace
"""


def rewrite(path, edits):
    text = path.read_text(encoding="utf-8")
    for old, new in edits:
        if text.count(old) != 1:
            raise SystemExit(f"Expected one instrumentation site in {path}: {old!r}")
        text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8", newline="\n")


def instrument(source):
    head = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if head != MRU_COMMIT:
        raise SystemExit(f"Expected Mru Flight {MRU_COMMIT}, got {head}")
    components = source / "fprime/Mru/Components"
    recorder = components / "RunRecorder/RunRecorder.cpp"
    result = "    if (value == Payload::compute(this->m_block, cycle, false, 0, 0)) {"
    rewrite(recorder, [
        ("\nnamespace Mru {", CLOCK + "\nnamespace Mru {"),
        (result, r'''    const auto received = traceMonotonicNs();
    const bool correct = value == Payload::compute(this->m_block, cycle, false, 0, 0);
    std::fprintf(stderr, "MRU_RESULT,%llu,%llu,%d\n",
                 received, static_cast<unsigned long long>(cycle), static_cast<int>(correct));
    if (correct) {'''),
        ("    this->m_totals.cycles++;", r'''    if (this->m_totals.cycles == 0) {
        std::fprintf(stderr, "MRU_FIRST_TICK,%llu\n", traceMonotonicNs());
    }
    this->m_totals.cycles++;'''),
    ])
    injector = components / "FaultInjector/FaultInjector.cpp"
    active = """            if (!f.announced) {
                f.announced = true;
                this->log_WARNING_LO_FaultApplied(f.kind, f.replica, cycle);
            }
            found = true;
        }
    }
    return found;
}

bool FaultInjector ::corruptAt"""
    rewrite(injector, [
        ("\nnamespace Mru {", CLOCK + "\nnamespace Mru {"),
        (active, active.replace(
            "                this->log_WARNING_LO_FaultApplied",
            r'''                if (kind == FaultKind::STUCK) {
                    std::fprintf(stderr, "MRU_STUCK,%llu,%llu,%u\n", traceMonotonicNs(),
                                 static_cast<unsigned long long>(cycle), static_cast<unsigned>(replica));
                }
                this->log_WARNING_LO_FaultApplied''')),
    ])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Disposable checkout of pinned Mru Flight")
    instrument(parser.parse_args().source)
