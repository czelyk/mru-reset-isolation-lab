"""Fetch pinned Basilisk C sources and build them with a minimal messaging adapter."""

import argparse
import hashlib
import subprocess
from pathlib import Path
from urllib.request import urlopen


PIN = "e5eddcb99d5f5e45472d1eae914032eddb43b88c"
MODULE = "fswAlgorithms/transDetermination/dvAccumulation"
UTIL = "architecture/utilities"
PAYLOAD = "architecture/msgPayloadDefC"
SOURCES = (
    f"{MODULE}/dvAccumulation.c", f"{MODULE}/dvAccumulation.h",
    f"{PAYLOAD}/AccDataMsgPayload.h", f"{PAYLOAD}/AccPktDataMsgPayload.h",
    f"{PAYLOAD}/NavTransMsgPayload.h", f"{UTIL}/linearAlgebra.c",
    f"{UTIL}/linearAlgebra.h", f"{UTIL}/macroDefinitions.h", f"{UTIL}/bsk_Print.h",
)
HEADERS = {
    "cMsgCInterface/AccDataMsg_C.h": r'''#pragma once
#include "architecture/msgPayloadDefC/AccDataMsgPayload.h"
typedef struct { AccDataMsgPayload payload; } AccDataMsg_C;
static inline int AccDataMsg_C_isLinked(const AccDataMsg_C *msg) { return msg != 0; }
static inline AccDataMsgPayload AccDataMsg_C_read(const AccDataMsg_C *msg) { return msg->payload; }
''',
    "cMsgCInterface/NavTransMsg_C.h": r'''#pragma once
#include <stdint.h>
#include "architecture/msgPayloadDefC/NavTransMsgPayload.h"
typedef struct { NavTransMsgPayload payload; } NavTransMsg_C;
static inline NavTransMsgPayload NavTransMsg_C_zeroMsgPayload(void) {
    return (NavTransMsgPayload){0};
}
static inline void NavTransMsg_C_init(NavTransMsg_C *msg) { msg->payload = NavTransMsg_C_zeroMsgPayload(); }
static inline void NavTransMsg_C_write(const NavTransMsgPayload *payload, NavTransMsg_C *msg,
                                      int64_t module, uint64_t time) {
    (void)module;
    (void)time;
    msg->payload = *payload;
}
''',
    f"{UTIL}/bskLogging.h": r'''#pragma once
#include <stdlib.h>
typedef struct BSKLogger BSKLogger;
static inline void _bskError(BSKLogger *logger, const char *message) {
    (void)logger;
    (void)message;
    abort();
}
''',
}


def fetch(output):
    source = output / "src"
    manifest = [f"Basilisk {PIN}"]
    for name in SOURCES:
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        url = f"https://raw.githubusercontent.com/AVSLab/basilisk/{PIN}/src/{name}"
        with urlopen(url, timeout=15) as response:
            content = response.read()
        path.write_bytes(content)
        manifest.append(f"{hashlib.sha256(content).hexdigest()}  {name}")
    for name, text in HEADERS.items():
        path = source / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="ascii", newline="\n")
    (output / "source-hashes.txt").write_text("\n".join(manifest) + "\n", encoding="ascii")


def build(output, compiler):
    source = output / "src"
    adapter = Path(__file__).resolve().parent.parent / "src/basilisk_dv_host.c"
    subprocess.run([compiler, "-std=c11", "-O2", "-fPIC", "-shared", "-I", str(source),
                    str(source / f"{MODULE}/dvAccumulation.c"), str(source / f"{UTIL}/linearAlgebra.c"),
                    str(adapter), "-lm", "-o", str(output / "libbasilisk_dv.so")], check=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--action", choices=("fetch", "build"), required=True)
    parser.add_argument("--cc", default="gcc")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    if args.action == "fetch":
        fetch(args.output)
    else:
        build(args.output, args.cc)
