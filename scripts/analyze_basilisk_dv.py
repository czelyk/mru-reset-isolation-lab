"""Execute the original Basilisk accumulator against captured F Prime deliveries."""

import argparse
import csv
import ctypes
import math
from contextlib import contextmanager
from itertools import product
from pathlib import Path

from analyze_fprime_latest import audit_selection
from analyze_fprime_live import audit_case, read_rows
from run_fprime_live import FAULT_CYCLE, MAX_AGE_NS


ORACLE_TOLERANCE_MPS = 1e-9
POLICIES = {"fresh-only": 1, "ordered-replay": 1, "gap-aware": 1,
            "buffer-2": 2, "buffer-4": 4, "buffer-8": 8}


class AccumulatorLibrary:
    def __init__(self, path):
        self.lib = ctypes.CDLL(str(path.resolve()))
        self.lib.dv_create.argtypes = []
        self.lib.dv_create.restype = ctypes.c_void_p
        self.lib.dv_destroy.argtypes = [ctypes.c_void_p]
        self.lib.dv_destroy.restype = None
        self.lib.dv_push.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_uint64),
                                    ctypes.POINTER(ctypes.c_double), ctypes.c_size_t,
                                    ctypes.POINTER(ctypes.c_double)]
        self.lib.dv_push.restype = ctypes.c_int

    @contextmanager
    def state(self):
        handle = self.lib.dv_create()
        if not handle:
            raise MemoryError("Failed to allocate Basilisk state")
        try:
            yield handle
        finally:
            self.lib.dv_destroy(handle)

    def push(self, handle, packet):
        timestamps = (ctypes.c_uint64 * len(packet))(*(time for time, _ in packet))
        values = (ctypes.c_double * (3 * len(packet)))(*(v for _, vector in packet for v in vector))
        output = (ctypes.c_double * 3)()
        if self.lib.dv_push(handle, timestamps, values, len(packet), output):
            raise ValueError("Invalid Basilisk packet")
        return tuple(output)


def oracle(samples):
    """Complete-history right-endpoint integration over original acquisition times."""
    increments = [[], [], []]
    results = {}
    previous = None
    for cycle, (timestamp, values) in samples.items():
        if previous is not None:
            for axis, value in enumerate(values):
                increments[axis].append(value * (timestamp - previous) * 1e-9)
        results[cycle] = tuple(math.fsum(axis) for axis in increments)
        previous = timestamp
    return results


def decoded_sample(row):
    encoded = int(row["value"])
    return int(row["source_ns"]), tuple(((encoded >> (10 * i)) & 1023) / 1000.0 for i in range(3))


def verify_adapter(library):
    baseline = [(100_000_000, (0.0, 0.0, 0.0)), (200_000_000, (1.0, 2.0, 3.0)),
                (400_000_000, (4.0, -2.0, 0.5))]
    with library.state() as handle:
        actual = library.push(handle, baseline[::-1])
        expected = (0.9, -0.2, 0.4)
        if math.dist(actual, expected) > ORACLE_TOLERANCE_MPS:
            raise ValueError("Compiled accumulator failed the sorted analytic case")
        if library.push(handle, baseline) != actual:
            raise ValueError("Compiled accumulator re-integrated repeated timestamps")


def evaluate(library, before, after, samples, truth, kill, policy, window):
    estimates = []
    gaps = 0
    gap_rejections = 0
    last_cycle = int(before[-1]["cycle"])
    with library.state() as handle:
        for row in before:
            value = library.push(handle, [decoded_sample(row)])
            if math.dist(value, truth[int(row["cycle"])]) > ORACLE_TOLERANCE_MPS:
                raise ValueError("Basilisk state diverged before the manager restart")
        for row in after:
            cycle = int(row["cycle"])
            timely = int(row["age_ns"]) <= MAX_AGE_NS
            if cycle <= last_cycle or (policy == "fresh-only" and not timely):
                continue
            if policy == "gap-aware" and cycle != last_cycle + 1:
                gap_rejections += 1
                continue
            first = max(last_cycle + 1, cycle - window + 1)
            gaps += first - last_cycle - 1
            packet = [samples[index] for index in range(first, cycle)]
            packet.append(decoded_sample(row))
            delta = library.push(handle, packet)
            reference = truth[cycle]
            error = math.dist(delta, reference)
            estimates.append({
                "cycle": cycle, "receive_ns": int(row["receive_ns"]), "source_ns": int(row["source_ns"]),
                "age_ms": int(row["age_ns"]) / 1e6, "from_kill_ms": (int(row["receive_ns"]) - kill) / 1e6,
                "timely": int(timely), "numerically_correct": int(error <= ORACLE_TOLERANCE_MPS),
                "integrated_in_update": len(packet), "cumulative_skipped": gaps,
                "dv_x": delta[0], "dv_y": delta[1], "dv_z": delta[2],
                "oracle_x": reference[0], "oracle_y": reference[1], "oracle_z": reference[2],
                "error_mps": error,
            })
            last_cycle = cycle
    timely_rows = [row for row in estimates if row["timely"]]
    first_timely = next(iter(timely_rows), None)
    first_valid = next((row for row in timely_rows if row["numerically_correct"]), None)
    return {
        "timely_estimates": len(timely_rows),
        "timely_incorrect_estimates": sum(not row["numerically_correct"] for row in timely_rows),
        "gap_rejections": gap_rejections,
        "first_timely_cycle": first_timely["cycle"] if first_timely else None,
        "first_timely_error_mps": first_timely["error_mps"] if first_timely else None,
        "first_timely_correct_cycle": first_valid["cycle"] if first_valid else None,
        "first_timely_correct_from_kill_ms": first_valid["from_kill_ms"] if first_valid else None,
        "max_packets_integrated_at_once": max((row["integrated_in_update"] for row in estimates), default=0),
        "terminal_skipped_ids": gaps,
        "terminal_error_mps": estimates[-1]["error_mps"] if estimates else None,
    }, estimates


def analyze(library, output, trials):
    verify_adapter(library)
    summaries, details, ingress = [], [], []
    for trial, workload, start, condition, restart in product(
        trials, ("imu", "imu-constant"), (190, 199),
        ("active-clear", "active-persistent", "retired-persistent"), ("checkpoint", "latest")
    ):
        name = f"{workload}-{start}-{condition}"
        directory = trial / (name if restart == "checkpoint" else f"{name}-latest")
        checked, rows = audit_case(directory)
        selection = audit_selection(directory, start, restart)
        if checked["wrong_outputs"]:
            raise ValueError(f"Wrong voted accelerometer sample in {directory}")
        samples = {
            int(row["cycle"]): (int(row["source_ns"]), tuple(float(row[f"input_{i}"]) / 1000 for i in (1, 2, 3)))
            for row in read_rows(directory / "samples.csv")
        }
        truth = oracle(samples)
        before = [row for row in rows if row["phase"] == "before"]
        after = [row for row in rows if row["phase"] == "after" and int(row["cycle"]) >= FAULT_CYCLE]
        before_by_cycle = {int(row["cycle"]): row for row in before}
        after_by_cycle = {int(row["cycle"]): row for row in rows if row["phase"] == "after"}
        base = {"trial": trial.name, "workload": workload, "restored_cycle": start,
                "condition": condition, "restart": restart}
        for cycle, (timestamp, values) in samples.items():
            record = {**base, "cycle": cycle, "source_ns": timestamp,
                      **{f"accel_{axis}": value for axis, value in zip("xyz", values)}}
            for phase, delivered in (("before", before_by_cycle), ("after", after_by_cycle)):
                row = delivered.get(cycle, {})
                record.update({f"{phase}_{key}": row.get(key) for key in ("port_ns", "receive_ns", "value")})
            ingress.append(record)
        for consumer, window in POLICIES.items():
            evaluated = {**base, "consumer": consumer}
            summary, estimates = evaluate(library, before, after, samples, truth,
                                          checked["manager_kill_ns"], consumer, window)
            summaries.append({**evaluated, "selected_cycle": selection["selected_cycle"],
                              "manager_kill_ns": checked["manager_kill_ns"], **summary})
            details.extend({**evaluated, **row} for row in estimates)
    for filename, rows in (("stateful-dv-results.csv", summaries), ("stateful-dv-rows.csv", details),
                           ("stateful-dv-ingress.csv", ingress)):
        with (output / filename).open("w", newline="", encoding="ascii") as stream:
            writer = csv.DictWriter(stream, fieldnames=list(rows[0]), lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    print(f"Executed the compiled Basilisk consumer for {len(summaries)} comparisons and {len(details)} updates.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("library", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("trials", type=Path, nargs="+")
    args = parser.parse_args()
    if len({trial.name for trial in args.trials}) != len(args.trials):
        parser.error("Trial directory names must be distinct")
    analyze(AccumulatorLibrary(args.library), args.output, args.trials)
