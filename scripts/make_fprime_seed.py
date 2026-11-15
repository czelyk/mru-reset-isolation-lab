"""Create the experimental membership seed for the F Prime restart replay."""

import argparse
import struct
import zlib
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    parser.add_argument("--retire-slot-1", action="store_true")
    args = parser.parse_args()
    # Mru v0.7.0: magic, version, shrinking policy, slot states, next cycle, CRC-32.
    # Slot 0 is always retired. Slot 2 is always active.
    slot_1 = 2 if args.retire_slot_1 else 0
    payload = struct.pack("<IBB3BQ", 0x4D525553, 1, 0, 2, slot_1, 0, 190)
    args.output.write_bytes(payload + struct.pack("<I", zlib.crc32(payload)))


if __name__ == "__main__":
    main()
