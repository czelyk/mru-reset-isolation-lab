"""Validate the F Prime output trace and summarize each restart."""

import argparse
import csv
import json
import re
from pathlib import Path

RESULT = re.compile(r"^MRU_RESULT,(\d+),(\d+),([01])$", re.MULTILINE)
FIRST_TICK = re.compile(r"^MRU_FIRST_TICK,(\d+)$", re.MULTILINE)
STUCK = re.compile(r"^MRU_STUCK,(\d+),(\d+),1$", re.MULTILINE)
RESTORED = re.compile(r"State restored: .*?, cycle (\d+)")


def observe(trace, summary, *, allow_no_correct=False):
    text = trace.read_text(encoding="utf-8")
    ticks = FIRST_TICK.findall(text)
    results = [tuple(map(int, row)) for row in RESULT.findall(text)]
    faults = [tuple(map(int, row)) for row in STUCK.findall(text)]
    restored = RESTORED.findall(text)
    rows = dict(field.split("=", 1) for field in summary.read_text(encoding="utf-8").splitlines()[1].split())
    if (
        len(ticks) != 1 or len(restored) != 1
        or len(faults) > 1
        or sum(row[2] for row in results) != int(rows["useful"])
        or sum(not row[2] for row in results) != int(rows["wrong"])
        or any(t <= 0 for t, _, _ in results)
        or any(a[0] > b[0] or a[1] >= b[1] for a, b in zip(results, results[1:]))
    ):
        raise ValueError(f"Incomplete or inconsistent trace: {trace}")
    tick_ns = int(ticks[0])
    first_correct = next((row for row in results if row[2]), None)
    if tick_ns == 0 or (results and results[0][0] < tick_ns) or (first_correct is None and not allow_no_correct):
        raise ValueError(f"No correctly timed first output: {trace}")
    observation = {"restored_cycle": int(restored[0]), "correct": int(rows["useful"]),
                   "wrong": int(rows["wrong"]), "detected": int(rows["detected"]),
                   "first_correct_cycle": None if first_correct is None else first_correct[1],
                   "first_tick_to_first_correct_ms": None if first_correct is None else
                   round((first_correct[0] - tick_ns) / 1e6, 3)}
    if faults:
        at_ns, at_cycle = faults[0]
        first_after_fault = next((row for row in results if row[2] and row[1] >= at_cycle), None)
        if first_after_fault is None or first_after_fault[0] < at_ns or at_ns < tick_ns:
            raise ValueError(f"No correctly timed output after the fault: {trace}")
        observation.update({
            "fault_cycle": at_cycle,
            "output_at_fault_cycle": next((bool(v) for _, c, v in results if c == at_cycle), None),
            "first_correct_after_fault_cycle": first_after_fault[1],
            "fault_to_first_correct_ms": round((first_after_fault[0] - at_ns) / 1e6, 3),
        })
    return observation, results


def analyze(directory):
    observations = {}
    csv_path = directory / "result-port.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as out:
        writer = csv.writer(out, lineterminator="\n")
        writer.writerow(["case", "phase", "receive_monotonic_ns", "cycle", "correct"])
        for case in ("precommit", "postcommit"):
            obs, rows = observe(directory / f"{case}-after-events.txt", directory / f"{case}-after-summary.txt")
            before = (directory / f"{case}-before-events.txt").read_text(encoding="utf-8")
            prior_rows = [tuple(map(int, row)) for row in RESULT.findall(before)]
            if not prior_rows:
                raise ValueError(f"Missing output trace prior to {case} interruption")
            prior_cycles = {cycle for _, cycle, correct in prior_rows if correct}
            restored_cycles = {cycle for _, cycle, correct in rows if correct}
            obs["replayed_correct_cycles"] = sorted(prior_cycles & restored_cycles)
            observations[case] = obs
            writer.writerows((case, "before", *row) for row in prior_rows)
            writer.writerows((case, "after", *row) for row in rows)
    pre, post = observations["precommit"], observations["postcommit"]
    if (pre["restored_cycle"] != 190 or post["restored_cycle"] != 201
            or pre.get("fault_cycle") != 200 or pre.get("output_at_fault_cycle") is not None
            or pre["detected"] != 1 or post["detected"] != 0
            or "fault_cycle" in post):
        raise ValueError(f"Unexpected comparison: {observations}")
    return observations


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    result = json.dumps(analyze(args.output), indent=2) + "\n"
    (args.output / "result-port-summary.json").write_text(result, encoding="utf-8")
    print(result, end="")
