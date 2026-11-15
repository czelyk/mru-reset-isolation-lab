"""Let lab replica 1 simulate a stuck reply while an external marker remains set."""

import argparse
from pathlib import Path

from instrument import rewrite


def instrument(source):
    main = source / "fprime/MruReplica/Main.cpp"
    rewrite(main, [
        ("    Os::init();", r'''    const char* const marker = std::getenv("MRU_LAB_REPLICA_FAULT_MARKER");
    if (replica == 1 && marker != nullptr) {
        if (setenv("MRU_LAB_SLOT1_REPLY_MARKER", marker, 1) != 0) {
            return 1;
        }
    } else {
        (void)unsetenv("MRU_LAB_SLOT1_REPLY_MARKER");
    }
    Os::init();'''),
    ])
    host = source / "fprime/Mru/Components/ReplicaHost/ReplicaHost.cpp"
    rewrite(host, [
        ("\nnamespace Mru {", "\n#include <cstdio>\n#include <cstdlib>\n#include <unistd.h>\n\nnamespace Mru {"),
        ("    this->replyOut_out(0, cycle, kind, first, second);", r'''    const char* const marker = std::getenv("MRU_LAB_SLOT1_REPLY_MARKER");
    if (marker != nullptr && access(marker, F_OK) == 0) {
        first = 0xdeadbeefULL;
        second = 0xdeadbeefULL;
        std::fprintf(stderr, "MRU_EXTERNAL_REPLY,%d,%llu,%d\n", static_cast<int>(getpid()),
                     static_cast<unsigned long long>(cycle), static_cast<int>(kind.e == RequestKind::KNOWN_ANSWER));
    }
    this->replyOut_out(0, cycle, kind, first, second);'''),
    ])


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    instrument(parser.parse_args().source)
