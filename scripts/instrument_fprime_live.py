"""Connect the F Prime lab payload and result recorder to the live sample harness."""

import argparse
from pathlib import Path

from instrument import CLOCK, rewrite


def instrument(source):
    mru = source / "fprime/Mru"
    rewrite(mru / "Payload/Payload.cpp", [
        ("\nnamespace Mru {", "\n#include <algorithm>\n#include <array>\n#include <cstdio>\n#include <cstdlib>\n\nnamespace Mru {"),
        ("    U64 s = (input * FILL_MULTIPLIER) + 1;", r'''    const char* const directory = std::getenv("MRU_LAB_SAMPLES");
    if (directory != nullptr && input != KNOWN_ANSWER_INPUT) {
        char path[1024];
        const int length = std::snprintf(path, sizeof(path), "%s/%llu",
                                        directory, static_cast<unsigned long long>(input));
        if (length < 0 || static_cast<size_t>(length) >= sizeof(path)) {
            std::abort();
        }
        auto* sample = std::fopen(path, "r");
        std::array<unsigned long long, 3> values{};
        const int count = sample == nullptr ? 0 : std::fscanf(sample, "%llu %llu %llu",
                                                            &values[0], &values[1], &values[2]);
        if (sample != nullptr) {
            std::fclose(sample);
        }
        if (count != 3) {
            std::fprintf(stderr, "MRU_MISSING_SAMPLE,%llu\n", static_cast<unsigned long long>(input));
            std::abort();
        }
        const char* const workload = std::getenv("MRU_LAB_WORKLOAD");
        if (workload != nullptr && workload[0] == 'm') {
            std::sort(values.begin(), values.end());
            return values[1];
        }
        if (workload != nullptr && workload[0] == 'i') {
            return values[0] | (values[1] << 10) | (values[2] << 20);
        }
        input = values[0];
    }
    U64 s = (input * FILL_MULTIPLIER) + 1;'''),
    ])
    rewrite(mru / "Components/RunRecorder/RunRecorder.cpp", [
        ("    if (correct) {", r'''    std::fprintf(stderr, "MRU_VALUE,%llu,%llu,%llu\n",
                 received, static_cast<unsigned long long>(cycle), static_cast<unsigned long long>(value));
    if (correct) {'''),
    ])
    rewrite(mru / "Components/ReplicaHost/ReplicaHost.cpp", [
        ("    if (marker != nullptr && access(marker, F_OK) == 0) {", r'''    const char* const minimum = std::getenv("MRU_LAB_FIRST_FAULT_CYCLE");
    if (marker != nullptr && access(marker, F_OK) == 0 &&
        (minimum == nullptr || cycle >= std::strtoull(minimum, nullptr, 10))) {'''),
    ])
    rewrite(mru / "Components/RedundancyManager/RedundancyManager.cpp", [
        ("\nnamespace Mru {", "\n#include <cstdlib>\n#include <unistd.h>\n" + CLOCK + "\nnamespace Mru {"),
        ("    }\n\n    this->m_cycle = this->m_nextCycle;", r'''        const char* const directory = std::getenv("MRU_LAB_LATEST");
        if (this->m_restored && directory != nullptr) {
            const auto start = traceMonotonicNs();
            const auto original = static_cast<unsigned long long>(this->m_nextCycle);
            auto selected = original;
            // The harness publishes contiguous immutable sample files in order.
            char path[1024];
            for (;;) {
                const int length = std::snprintf(path, sizeof(path), "%s/%llu", directory, selected + 1);
                if (length < 0 || static_cast<size_t>(length) >= sizeof(path)) {
                    std::abort();
                }
                if (access(path, F_OK) != 0) {
                    break;
                }
                ++selected;
            }
            this->m_nextCycle = selected;
            std::fprintf(stderr, "MRU_LATEST,%llu,%llu,%llu,%llu\n", original, selected,
                         start, traceMonotonicNs());
        }
    }

    this->m_cycle = this->m_nextCycle;'''),
    ])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    instrument(parser.parse_args().source)
