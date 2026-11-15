"""Measure live receiver acceptance across a real F Prime manager process restart."""

import argparse
import csv
import json
import os
import re
import selectors
import subprocess
import threading
import time
from collections import Counter
from functools import lru_cache
from pathlib import Path
from tempfile import TemporaryDirectory

from make_fprime_seed import checkpoint_seed


PERIOD_NS = 100_000_000
MAX_AGE_NS = 500_000_000
FAULT_CYCLE = 200
VALUE = re.compile(rb"^MRU_VALUE,(\d+),(\d+),(\d+)$")
FAULT = re.compile(rb"^MRU_EXTERNAL_REPLY,(\d+),(\d+),([01])$")
LATEST = re.compile(rb"^MRU_LATEST,(\d+),(\d+),(\d+),(\d+)$")
FIELDS = ["phase", "cycle", "source_ns", "port_ns", "receive_ns", "age_ns", "value",
          "expected", "correct", "sequence_only_accept", "live_decision"]
CASES = {
    "active-clear": (False, "cleared"),
    "active-persistent": (False, "persistent"),
    "retired-persistent": (True, "persistent"),
    "active-delayed": (False, "delayed"),
    "retired-delayed": (True, "delayed"),
}


@lru_cache(maxsize=None)
def expected_hash(value):
    """Independent integer oracle for the upstream 4 KiB hash workload."""
    mask = (1 << 64) - 1
    word = (value * 0x9E3779B97F4A7C15 + 1) & mask
    digest = 0xCBF29CE484222325
    for _ in range(512):
        word ^= (word << 13) & mask
        word ^= word >> 7
        word ^= (word << 17) & mask
        for byte in word.to_bytes(8, "little"):
            digest = ((digest ^ byte) * 0x100000001B3) & mask
    return digest


def expected_sample_value(workload, values):
    if workload == "hash":
        return expected_hash(values[0])
    if workload == "median":
        return sorted(values)[1]
    if workload in ("imu", "imu-constant"):
        return sum(value << (10 * axis) for axis, value in enumerate(values))
    raise ValueError(f"Unknown workload: {workload}")


def input_values(cycle, workload):
    if workload == "imu-constant":
        return (125, 250, 375)
    return (37 * cycle % 509, 91 * cycle % 673, 183 * cycle % 587)


def publish_samples(directory, start_cycle, workload, samples, published, ready, stop):
    deadline = time.monotonic_ns()
    cycle = start_cycle
    while not stop.is_set():
        if stop.wait(max(0, deadline - time.monotonic_ns()) / 1e9):
            return
        values = input_values(cycle, workload)
        temporary = directory / "next"
        temporary.write_text(" ".join(map(str, values)), encoding="ascii")
        samples[cycle] = (time.monotonic_ns(), values)
        temporary.replace(directory / str(cycle))
        published[cycle] = time.monotonic_ns()
        ready.set()
        deadline += PERIOD_NS
        cycle += 1


class Consumer:
    """Both policies observe the same live port row and keep state across restart."""

    def __init__(self, workload, samples):
        self.workload = workload
        self.samples = samples
        self.last_order = -1
        self.last_live = -1
        self.rows = []

    def observe(self, phase, match):
        receive_ns = time.monotonic_ns()
        port_ns, cycle, value = map(int, match.groups())
        source_ns, values = self.samples[cycle]
        age = receive_ns - source_ns
        if not source_ns <= port_ns <= receive_ns:
            raise ValueError(f"Inconsistent source/port/receiver clocks for cycle {cycle}")
        order = cycle > self.last_order
        if order:
            self.last_order = cycle
        if cycle <= self.last_live:
            decision = "old-id"
        elif age > MAX_AGE_NS:
            decision = "stale-source"
        else:
            decision = "accepted"
            self.last_live = cycle
        expected = expected_sample_value(self.workload, values)
        # The oracle scores the decision. Neither policy uses it to accept or reject.
        self.rows.append(dict(zip(FIELDS, (phase, cycle, source_ns, port_ns, receive_ns, age, value,
                                          expected, int(value == expected), int(order), decision))))


def port_lines(process, log):
    with selectors.DefaultSelector() as selector:
        selector.register(process.stdout, selectors.EVENT_READ)
        fragment = b""
        while selector.select(timeout=5):
            chunk = os.read(process.stdout.fileno(), 65536)
            if not chunk:
                return
            log.write(chunk)
            log.flush()
            *lines, fragment = (fragment + chunk).split(b"\n")
            yield from lines
        raise TimeoutError("No F Prime trace for five seconds")


def run_manager(flight, state, output, env, phase, duration, consumer, cut_marker=None):
    log_path = output / f"{phase}-events.txt"
    summary = output / f"{phase}-summary.txt"
    metadata = {"restore": None, "tick_ns": None, "fault_replies": [], "kill_ns": None}
    with log_path.open("wb") as log, subprocess.Popen(
        [flight / "MruQuorum", "-t", str(duration), "-p", "100", "-m", "128",
         "-R", flight / "MruReplica", "-C", "0,1,1", "-f", state, "-o", summary],
        env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    ) as process:
        try:
            if cut_marker is not None:
                os.mkfifo(state.with_suffix(".dat.tmp"))
            for line in port_lines(process, log):
                match = VALUE.fullmatch(line)
                if match:
                    consumer.observe(phase, match)
                    if cut_marker is not None and int(match[2]) == FAULT_CYCLE - 1:
                        cut_marker.touch()
                elif b"State restored:" in line:
                    metadata["restore"] = line.decode("ascii").split("State restored: ", 1)[1]
                elif line.startswith(b"MRU_FIRST_TICK,"):
                    metadata["tick_ns"] = int(line.split(b",")[1])
                elif match := FAULT.fullmatch(line):
                    metadata["fault_replies"].append(list(map(int, match.groups())))
                elif match := LATEST.fullmatch(line):
                    if "latest" in metadata:
                        raise ValueError("Multiple latest-sample selections")
                    metadata["latest"] = list(map(int, match.groups()))
                elif cut_marker is not None and b"Replica 1 retired" in line and line.endswith(b"at cycle 200"):
                    metadata["kill_ns"] = time.monotonic_ns()
                    process.kill()
                    cut_marker = None
        finally:
            if process.poll() is None and metadata["kill_ns"] is None:
                # On a trace failure, do not leave a manager blocked on the FIFO.
                try:
                    process.wait(timeout=1)
                except subprocess.TimeoutExpired:
                    process.kill()
    metadata["exit"] = process.returncode
    if metadata["tick_ns"] is None or metadata["restore"] is None:
        raise ValueError(f"Missing startup evidence in {log_path}")
    return metadata


def first_correct(rows, predicate, kill_ns):
    first = next((row for row in rows if row["correct"] and predicate(row)), None)
    if first is None:
        return None
    return {"cycle": first["cycle"], "kill_to_accept_ms": round((first["receive_ns"] - kill_ns) / 1e6, 3),
            "age_at_receive_ms": round(first["age_ns"] / 1e6, 3)}


def run_case(flight, directory, start_cycle, workload, case, policy="checkpoint", restart_delay_ms=0):
    retired, fault_mode = CASES[case]
    directory.mkdir()
    with TemporaryDirectory() as tmp:
        workspace = Path(tmp)
        source = workspace / "samples"
        source.mkdir()
        state = workspace / "state.dat"
        marker = workspace / "fault"
        seed = checkpoint_seed(start_cycle)
        state.write_bytes(seed)
        env = dict(os.environ, MRU_LAB_SAMPLES=str(source), MRU_LAB_WORKLOAD=workload,
                   MRU_LAB_REPLICA_FAULT_MARKER=str(marker), MRU_LAB_FIRST_FAULT_CYCLE=str(FAULT_CYCLE))
        env.pop("MRU_LAB_LATEST", None)
        samples, published = {}, {}
        ready, stop = threading.Event(), threading.Event()
        producer = threading.Thread(target=publish_samples,
                                    args=(source, start_cycle, workload, samples, published, ready, stop))
        consumer = Consumer(workload, samples)
        producer.start()
        try:
            if not ready.wait(2):
                raise TimeoutError("Sample source did not start")
            before = run_manager(flight, state, directory, env, "before", 6, consumer, marker)
            if (before["exit"] != -9 or state.read_bytes() != seed or not marker.exists()
                    or not before["restore"].endswith(f"cycle {start_cycle}")):
                raise ValueError(f"Expected a manager kill with the old active checkpoint in {directory}")
            marker_inode = marker.stat().st_ino
            state.with_suffix(".dat.tmp").unlink()
            if fault_mode == "cleared":
                marker.unlink()
            elif fault_mode == "persistent":
                env.pop("MRU_LAB_FIRST_FAULT_CYCLE")
            if retired:
                state.write_bytes(checkpoint_seed(start_cycle, retire_slot_1=True))
            if policy == "latest":
                env["MRU_LAB_LATEST"] = str(source)
            if restart_delay_ms:
                time.sleep(restart_delay_ms / 1000)
            after = run_manager(flight, state, directory, env, "after", 2, consumer)
            if marker.exists() and marker.stat().st_ino != marker_inode:
                raise ValueError(f"Fault marker replaced in {directory}")
        finally:
            stop.set()
            producer.join()

    expected_slots = "[ RETIRED (2), RETIRED (2), ACTIVE (0) ]" if retired else "[ RETIRED (2), ACTIVE (0), ACTIVE (0) ]"
    if after["exit"] != 0 or not after["restore"].endswith(f"{expected_slots}, cycle {start_cycle}"):
        raise ValueError(f"Unexpected restored deployment in {directory}")
    initial_cycle = start_cycle
    if policy == "latest":
        original, initial_cycle, scan_start, scan_end = after["latest"]
        already_published = max((cycle for cycle, timestamp in published.items() if timestamp < scan_start), default=original)
        possible = max((cycle for cycle, (timestamp, _) in samples.items() if timestamp <= scan_end), default=original)
        if original != start_cycle or not max(original, already_published) <= initial_cycle <= max(original, possible):
            raise ValueError(f"Latest sample disagrees with source publication timeline in {directory}")
    elif "latest" in after:
        raise ValueError(f"Checkpoint policy unexpectedly advanced the cursor in {directory}")
    fault_onsets = [(cycle, for_check) for _, cycle, for_check in after["fault_replies"]]
    fault_start = initial_cycle if fault_mode == "persistent" else max(initial_cycle, FAULT_CYCLE)
    expected_faults = [(fault_start, 0), (fault_start, 1)] if not retired and fault_mode != "cleared" else []
    if fault_onsets != expected_faults or [(cycle, check) for _, cycle, check in before["fault_replies"]] != [(200, 0), (200, 1)]:
        raise ValueError(f"Unexpected fault onset in {directory}")
    before_ids = [row["cycle"] for row in consumer.rows if row["phase"] == "before"
                  and row["live_decision"] == "accepted" and row["correct"]]
    if before_ids != list(range(start_cycle, FAULT_CYCLE)):
        raise ValueError(f"Missing or stale pre-kill history in {directory}")
    rows = [row for row in consumer.rows if row["phase"] == "after"]
    if not rows or rows[-1]["cycle"] < FAULT_CYCLE + 3:
        raise ValueError(f"Insufficient output observation window in {directory}")
    with (directory / "samples.csv").open("w", newline="", encoding="ascii") as stream:
        writer = csv.writer(stream)
        writer.writerow(["cycle", "source_ns", "input_1", "input_2", "input_3", "published_ns"])
        writer.writerows((cycle, timestamp, *values, published[cycle]) for cycle, (timestamp, values) in samples.items())
    summary = {"workload": workload, "start_cycle": start_cycle, "condition": case,
               "restart_delay_ms": restart_delay_ms,
               "receiver_pid": os.getpid(), "before": before, "after": after,
               "receiver_last_before": before_ids[-1], "after_decisions": dict(Counter(row["live_decision"] for row in rows)),
               "wrong_outputs": sum(not row["correct"] for row in rows),
               "wrong_accepted": sum(not row["correct"] and row["live_decision"] == "accepted" for row in rows),
               "first_order_correct": first_correct(rows, lambda row: row["sequence_only_accept"], before["kill_ns"]),
               "first_live_correct": first_correct(rows, lambda row: row["live_decision"] == "accepted", before["kill_ns"])}
    if policy == "latest":
        summary["new_source_ids_skipped"] = max(0, initial_cycle - FAULT_CYCLE)
    return consumer.rows, summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("flight", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cycles", type=int, nargs="+", default=[190, 198, 199], choices=range(190, 200))
    parser.add_argument("--workloads", nargs="+", choices=["hash", "median", "imu", "imu-constant"],
                        default=["hash", "median"])
    parser.add_argument("--cases", nargs="+", choices=CASES, default=list(CASES))
    parser.add_argument("--policies", nargs="+", choices=["checkpoint", "latest"], default=["checkpoint"])
    parser.add_argument("--restart-delay-ms", type=int, choices=[0, 100], default=0,
                        help="Shift the producer/manager phase by one nominal sample period")
    args = parser.parse_args()
    for workload in args.workloads:
        for start in args.cycles:
            for case in args.cases:
                for policy in args.policies:
                    name = f"{workload}-{start}-{case}"
                    if policy == "latest":
                        name += "-latest"
                    rows, result = run_case(args.flight, args.output / name, start, workload, case, policy,
                                            args.restart_delay_ms)
                    with (args.output / name / "receiver.csv").open("w", newline="", encoding="ascii") as stream:
                        writer = csv.DictWriter(stream, fieldnames=FIELDS)
                        writer.writeheader()
                        writer.writerows(rows)
                    (args.output / name / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="ascii")
                    print(name, result["first_live_correct"], flush=True)


if __name__ == "__main__":
    main()
