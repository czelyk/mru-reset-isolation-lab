"""Compare cumulative and incremental delivery on public Mars rover IMU tables."""

import argparse
import csv
import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from itertools import groupby
from pathlib import Path
from statistics import median
from urllib.request import urlopen


ARCHIVE = "https://pds-atmospheres.nmsu.edu/PDS/data/merimu_1001/DATA"
FILES = {
    "1TRANSFORMED.LBL": "165088f03011bd7ed6363812776c9ecfaa4751b9a6ce59dc29ce1d08109d54d6",
    "1TRANSFORMED.TAB": "a4796482af6ab5e8d955423e423d9a528848a6bad52b7fea280901097ea574a9",
    "2TRANSFORMED.LBL": "bfecf0437ec47a453314d744900171ec8cd998f5ab2418241971aa7de41140f0",
    "2TRANSFORMED.TAB": "3269f400f2a372b150c52897e55ce4a7df270f1fdadf2253f02aeb6ed82e454e",
}
ROVERS = {"1": "Opportunity", "2": "Spirit"}
CADENCES_MS = (125, 250)
DROPPED = (0, 1, 3, 7, 15)
WINDOWS = (1, 4, 8)


@dataclass(frozen=True)
class Record:
    clock_ms: int
    dv_um_per_s: tuple
    incomplete: bool


def read_archive(directory, download):
    contents = {}
    directory.mkdir(parents=True, exist_ok=True)
    for filename, checksum in FILES.items():
        path = directory / filename
        if download and not path.exists():
            with urlopen(f"{ARCHIVE}/{filename}", timeout=30) as response:
                path.write_bytes(response.read())
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != checksum:
            raise ValueError(f"Unexpected source checksum for {path}")
        contents[filename] = data.decode("ascii")
    return contents


def column_slices(label):
    fields = {}
    for col in re.findall(r"OBJECT\s+= COLUMN\b(.*?)END_OBJECT\s+= COLUMN\b", label, flags=re.S):
        name = re.search(r'NAME\s+= "([^"]+)"', col)[1]
        start = int(re.search(r"\bSTART_BYTE\s+= (\d+)", col)[1]) - 1
        width = int(re.search(r"\bBYTES\s+= (\d+)", col)[1])
        fields[name] = slice(start, start + width)
    return fields


def integer_units(value, scale):
    scaled = Decimal(value) * scale
    if scaled != scaled.to_integral_value():
        raise ValueError(f"Archive field exceeds assumed precision: {value}")
    return int(scaled)


def parse_records(label, table):
    fields = column_slices(label)
    lines = table.splitlines()
    if len(lines) != int(re.search(r"^\s*ROWS\s+= (\d+)", label, flags=re.M)[1]):
        raise ValueError("Archive row count differs from the label")
    clock = fields["SPACECRAFT_CLOCK_START_COUNT"]
    dv = [fields[f"ROVER_IMU_DELTA_VEL_{axis}"] for axis in "XYZ"]
    accel = [fields[f"BACKSHELL_IMU_ACCEL_{axis}"] for axis in "XYZ"]
    quaternion = [
        fields[f"{unit}_IMU_QUATERNION_{component}"]
        for unit in ("ROVER", "BACKSHELL") for component in range(1, 5)
    ]
    records = []
    for line in lines:
        vector = tuple(integer_units(line[field], 1_000_000) for field in dv)
        accel_values = [Decimal(line[field]) for field in accel]
        attitude = [Decimal(line[field]) for field in quaternion]
        records.append(Record(integer_units(line[clock], 1000), vector,
                              not any(attitude) or not any((*vector, *accel_values))))
    if any(left.clock_ms > right.clock_ms for left, right in zip(records, records[1:])):
        raise ValueError("Archive timestamps run backwards")
    return records


def clean(records):
    kept = []
    counts = Counter()
    for _, group in groupby(records, key=lambda row: row.clock_ms):
        group = list(group)
        if len(group) > 1:
            counts["repeated_timestamps"] += 1
        complete = [row for row in group if not row.incomplete]
        counts["incomplete_rows"] += len(group) - len(complete)
        if not complete:
            counts["missing_timestamps"] += 1
        elif len({row.dv_um_per_s for row in complete}) != 1:
            counts["conflicting_timestamps"] += 1
        else:
            kept.append(complete[0])
    return kept, counts


def difference(a, b):
    return tuple(x - y for x, y in zip(a, b))


def norm_mps(vector):
    return math.hypot(*vector) / 1e6


def reset_candidates(records):
    """Conservative offline signatures; these are not onboard reset labels."""
    for i, (before, after) in enumerate(zip(records, records[1:])):
        prior_norm = norm_mps(before.dv_um_per_s)
        next_three = records[i + 2:i + 5]
        if (
            after.clock_ms - before.clock_ms <= 500
            and prior_norm >= 10 and norm_mps(after.dv_um_per_s) <= 2
            and len(next_three) == 3
            and all(norm_mps(row.dv_um_per_s) < max(10, prior_norm / 4) for row in next_three)
        ):
            yield i + 1


def epoch_difference(anchor, endpoint, expected_epoch, packet_epoch):
    if expected_epoch != packet_epoch:
        return None
    return difference(endpoint.dv_um_per_s, anchor.dv_um_per_s)


def segments(records, cadence):
    start = 0
    for index in range(1, len(records)):
        if records[index].clock_ms - records[index - 1].clock_ms != cadence:
            yield records[start:index]
            start = index
    yield records[start:]


def compare_gaps(records, cadence, dropped, rover):
    errors = {window: [] for window in WINDOWS}
    examined = 0
    for block in segments(records, cadence):
        for index in range(len(block) - dropped - 1):
            span = block[index:index + dropped + 2]
            anchor, endpoint = span[0], span[-1]
            reference = epoch_difference(anchor, endpoint, 0, 0)
            increments = [difference(b.dv_um_per_s, a.dv_um_per_s) for a, b in zip(span, span[1:])]
            if tuple(map(sum, zip(*increments))) != reference:
                raise ValueError("Full incremental replay differs from the published endpoint change")
            for window in WINDOWS:
                retained = tuple(map(sum, zip(*increments[-window:])))
                errors[window].append(norm_mps(difference(reference, retained)))
            examined += 1
    for window, values in errors.items():
        if not values:
            continue
        yield {"rover": rover, "cadence_ms": cadence, "dropped_rows": dropped, "window_samples": window,
               "windows": examined, "cumulative_exact": examined,
               "incremental_exact": sum(value == 0 for value in values),
               "incremental_median_error_mps": round(median(values), 6),
               "incremental_max_error_mps": round(max(values), 6)}


def write_csv(path, rows):
    with path.open("w", newline="", encoding="ascii") as stream:
        writer = csv.DictWriter(stream, list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def analyze(contents, output):
    gaps, boundaries, quality = [], [], []
    for prefix, rover in ROVERS.items():
        records = parse_records(contents[f"{prefix}TRANSFORMED.LBL"], contents[f"{prefix}TRANSFORMED.TAB"])
        complete, counts = clean(records)
        candidates = list(reset_candidates(complete))
        if not candidates:
            raise ValueError(f"No reset signature found for {rover}")
        for index in candidates:
            before, after = complete[index - 1:index + 1]
            for dropped in DROPPED:
                endpoint_index = index + dropped
                if endpoint_index >= len(complete) or any(index < other <= endpoint_index for other in candidates):
                    continue  # isolate one observed boundary
                endpoint = complete[endpoint_index]
                unchecked = epoch_difference(before, endpoint, 0, 0)
                guarded = epoch_difference(before, endpoint, 0, 1)
                boundaries.append({
                    "rover": rover, "before_sclk_s": before.clock_ms / 1000,
                    "boundary_after_sclk_s": after.clock_ms / 1000, "received_sclk_s": endpoint.clock_ms / 1000,
                    "dropped_rows_after_boundary": dropped,
                    "pre_norm_mps": round(norm_mps(before.dv_um_per_s), 6),
                    "received_norm_mps": round(norm_mps(endpoint.dv_um_per_s), 6),
                    "naive_apparent_increment_mps": round(norm_mps(unchecked), 6),
                    "withheld_with_external_epoch_change": int(guarded is None),
                })
        quality.append({
            "rover": rover, "original_rows": len(records),
            **{key: counts[key] for key in ("repeated_timestamps", "incomplete_rows",
                                           "missing_timestamps", "conflicting_timestamps")},
            "kept_timestamps": len(complete), "reset_like_boundaries": len(candidates),
        })
        # Windows are deliberately limited to the segment before the first candidate.
        for cadence in CADENCES_MS:
            for dropped in DROPPED:
                gaps.extend(compare_gaps(complete[:candidates[0]], cadence, dropped, rover))
    write_csv(output / "mer-dv-archive-quality.csv", quality)
    write_csv(output / "mer-dv-reset-boundaries.csv", boundaries)
    write_csv(output / "mer-dv-loss-windows.csv", gaps)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--download", action="store_true", help="Download missing public archive files")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    analyze(read_archive(args.archive, args.download), args.output)
