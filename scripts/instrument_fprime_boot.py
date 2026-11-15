"""Install an opt-in one-tick boot check and deterministic reply faults for the lab."""

import argparse
from pathlib import Path

from instrument import rewrite


def add_boot_check(components):
    header = components / "RedundancyManager/RedundancyManager.hpp"
    rewrite(header, [
        ("NONE, DIAGNOSIS, PERIODIC, ADMISSION", "NONE, DIAGNOSIS, PERIODIC, ADMISSION, BOOT"),
        ("    void startCycle();", "    void startCycle();\n    bool startBootCheck();"),
    ])
    implementation = components / "RedundancyManager/RedundancyManager.cpp"
    rewrite(implementation, [
        ("\nnamespace Mru {", "\n#include <cstdio>\n#include <cstdlib>\n\nnamespace Mru {"),
        ("            case KatPurpose::DIAGNOSIS:", r'''            case KatPurpose::BOOT:
                this->m_katPurpose[i] = KatPurpose::NONE;
                std::fprintf(stderr, "MRU_BOOT_REPLY,%u,%d\n", static_cast<unsigned>(i), static_cast<int>(passed));
                if (!passed && this->m_slots[i] == SlotState::ACTIVE) {
                    this->retire(i, RetireReason::KNOWN_ANSWER_FAILED);
                }
                break;
            case KatPurpose::DIAGNOSIS:'''),
        ("void RedundancyManager ::startCycle() {", r'''bool RedundancyManager ::startBootCheck() {
    const char* const enabled = std::getenv("MRU_LAB_BOOT_CHECK");
    if (!this->m_restored || enabled == nullptr || enabled[0] != '1') {
        return false;
    }
    // Use the preceding cycle as the reply token so an overdue reply cannot
    // be confused with an ordinary request for the first restored cycle.
    this->m_cycle = this->m_nextCycle - 1;
    std::fprintf(stderr, "MRU_BOOT_START,%llu\n", static_cast<unsigned long long>(this->m_nextCycle));
    for (FwIndexType i = 0; i < Replicas; i++) {
        if (this->m_slots[i] == SlotState::ACTIVE) {
            this->requestKnownAnswer(i, KatPurpose::BOOT);
        }
    }
    return true;
}

void RedundancyManager ::startCycle() {'''),
        ("    }\n\n    this->m_cycle = this->m_nextCycle;", r'''        if (this->startBootCheck()) {
            return;
        }
    }

    // Unanswered checks expire. Leave the slot with ordinary quorum protection.
    for (FwIndexType i = 0; i < Replicas; i++) {
        if (this->m_katPurpose[i] == KatPurpose::BOOT) {
            std::fprintf(stderr, "MRU_BOOT_UNANSWERED,%u\n", static_cast<unsigned>(i));
            this->m_katPurpose[i] = KatPurpose::NONE;
        }
    }
    this->m_cycle = this->m_nextCycle;'''),
    ])


def add_test_fault(components):
    injector = components / "FaultInjector/FaultInjector.cpp"
    rewrite(injector, [
        ("\nnamespace Mru {", "\n#include <cstdlib>\n\nnamespace Mru {"),
        ("    if (this->active(FaultKind::STUCK, portNum, cycle)) {", r'''    const char* const fault = std::getenv("MRU_LAB_REPLY_FAULT");
    const bool bootFixture = portNum == 1 && fault != nullptr &&
        (fault[0] == 'v' || (fault[0] == 'b' && kind.e != RequestKind::KNOWN_ANSWER));
    if (bootFixture) {
        std::fprintf(stderr, "MRU_BOOT_FIXTURE,%llu,%u,%d\n",
                     static_cast<unsigned long long>(cycle), static_cast<unsigned>(portNum),
                     static_cast<int>(kind.e == RequestKind::KNOWN_ANSWER));
    }
    if (bootFixture || this->active(FaultKind::STUCK, portNum, cycle)) {'''),
    ])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path, help="Pinned checkout after applying instrument_fprime_output.py")
    components = parser.parse_args().source / "fprime/Mru/Components"
    add_boot_check(components)
    add_test_fault(components)
