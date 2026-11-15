"""Validate the reset boundary and replay results from the replica-side fault fixture."""

import argparse
import csv
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from analyze_fprime_output import FIRST_TICK, RESULT, observe
from replay_fprime_consumer import RESTORED_SLOTS, RETIREMENT, measure, replay_with_persistent_state


EXTERNAL_REPLY = re.compile(r"^MRU_EXTERNAL_REPLY,(\d+),(\d+),([01])$", re.MULTILINE)


def text(directory, name):
    return (directory / f"{name}.txt").read_text(encoding="utf-8").strip()


def analyze_case(directory, case, db):
    before = text(directory, f"{case}-before-events")
    after_path = directory / f"{case}-after-events.txt"
    after = after_path.read_text(encoding="utf-8")
    prior = [tuple(map(int, row)) for row in RESULT.findall(before)]
    prior_faults = [tuple(map(int, row)) for row in EXTERNAL_REPLY.findall(before)]
    after_faults = [tuple(map(int, row)) for row in EXTERNAL_REPLY.findall(after)]
    retained = case == "retained"
    restored_slot = "RETIRED (2)" if case == "retired" else "ACTIVE (0)"
    marker_before = text(directory, f"{case}-marker-before")
    marker_after = text(directory, f"{case}-marker-after")
    if (
        [(cycle, correct) for _, cycle, correct in prior] != [(cycle, 1) for cycle in range(190, 200)]
        or RESTORED_SLOTS.findall(before) != ["ACTIVE (0)"] or RESTORED_SLOTS.findall(after) != [restored_slot]
        or RETIREMENT.findall(before) != ["200"] or not prior_faults
        or [(cycle, check) for _, cycle, check in prior_faults] != [(200, 0), (200, 1)]
        or not re.fullmatch(r"\d+:\d+", marker_before)
        or marker_after != ("absent" if case == "cleared" else marker_before)
        or text(directory, f"{case}-manager-exit") != "137"
        or (directory / f"{case}-at-kill.dat").read_bytes() != (directory / "active.dat").read_bytes()
        or "FaultScheduled" in before or "FaultScheduled" in after
        or (retained and [(cycle, check) for _, cycle, check in after_faults] != [(190, 0), (190, 1)])
        or (not retained and after_faults)
        or {pid for pid, _, _ in prior_faults} & {pid for pid, _, _ in after_faults}
    ):
        raise ValueError(f"Reset or replica fault evidence did not match in {directory / case}")
    summary = directory / f"{case}-after-summary.txt"
    recorder, rows = observe(after_path, summary)
    if "cycle_ms=100 sequence=none" not in summary.read_text(encoding="utf-8").splitlines()[0]:
        raise ValueError(f"Unexpected recovery configuration in {summary}")
    tick_ns = int(FIRST_TICK.search(after)[1])
    accepted = replay_with_persistent_state(db, prior, rows)
    history_cycles = {cycle for _, cycle, _ in prior}
    return {
        "marker_before_kill": marker_before,
        "marker_before_start": marker_after,
        "manager_exit": 137,
        "checkpoint_equal_to_active_seed": True,
        "restored_slot_1": restored_slot.split()[0].lower(),
        "replica_pid_cycle_and_check_before": prior_faults,
        "replica_pid_cycle_and_check_after": after_faults,
        "slot_1_retired_after_at": list(map(int, RETIREMENT.findall(after))),
        "first_tick_ns": tick_ns,
        "recorder": recorder,
        "consumer": measure(rows, accepted, history_cycles, tick_ns),
    }, prior, rows, accepted


def analyze(trials, output):
    result = {}
    with (output / "fprime-external-fault-output.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["trial", "case", "phase", "receive_monotonic_ns", "cycle", "correct",
                         "high_water_accepted"])
        for trial in trials:
            result[trial.name] = {}
            with TemporaryDirectory() as temp:
                for case in ("retained", "cleared", "retired"):
                    scores, prior, rows, kept = analyze_case(trial, case, Path(temp) / f"{case}.sqlite")
                    writer.writerows((trial.name, case, "before", *row, 1) for row in prior)
                    writer.writerows((trial.name, case, "after", *row, int(keep)) for row, keep in zip(rows, kept))
                    result[trial.name][case] = scores
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Existing output directory")
    parser.add_argument("trials", nargs="+", type=Path)
    args = parser.parse_args()
    if len({path.name for path in args.trials}) != len(args.trials):
        parser.error("Trial directory names must be distinct")
    result = json.dumps(analyze(args.trials, args.output), indent=2) + "\n"
    (args.output / "fprime-external-fault.json").write_text(result, encoding="utf-8")
