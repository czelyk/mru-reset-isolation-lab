"""Create the experimental clock and replica seed for the F Prime restart replay."""

import argparse
import struct
import zlib
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    # Mru v0.7.0: magic, version, shrinking policy, slot states, next cycle, CRC-32.
    # Slot 0 was previously retired; slots 1 and 2 remain eligible.
    payload = struct.pack("<IBB3BQ", 0x4D525553, 1, 0, 2, 0, 0, 190)
    args.output.write_bytes(payload + struct.pack("<I", zlib.crc32(payload)))


if __name__ == "__main__":
    main()
