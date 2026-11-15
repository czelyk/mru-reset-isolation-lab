"""Compare consumer policies on result-port traces from the matched restart runs."""

import argparse
import csv
import json
import re
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from analyze_fprime_output import FIRST_TICK, STUCK, observe


CASES = {
    "history": ("active", "none", None, None),
    "active-fault": ("active", "ok", 200, 200),
    "retired-fault": ("retired", "ok", None, None),
    "active-control": ("active", "none", None, None),
}
RESTORED_SLOTS = re.compile(
    r"State restored: policy SHRINK \(0\), slots "
    r"\[ RETIRED \(2\), (ACTIVE \(0\)|RETIRED \(2\)), ACTIVE \(0\) \], cycle 190\b"
)
RETIREMENT = re.compile(r"Replica 1 retired \([^\r\n]+\) at cycle (\d+)")


def load_case(directory, name):
    trace = directory / f"{name}-events.txt"
    summary = directory / f"{name}-summary.txt"
    observation, rows = observe(trace, summary)
    events = trace.read_text(encoding="utf-8")
    config = dict(field.split("=", 1) for field in summary.read_text(encoding="utf-8").splitlines()[0].split())
    restored = RESTORED_SLOTS.findall(events)
    retirements = [int(cycle) for cycle in RETIREMENT.findall(events)]
    slot, sequence, fault, retirement = CASES[name]
    if (
        len(restored) != 1 or restored[0].split()[0].lower() != slot
        or config["cycle_ms"] != "100" or config["sequence"] != sequence
        or observation.get("fault_cycle") != fault
        or retirements != ([] if retirement is None else [retirement])
    ):
        raise ValueError(f"Unexpected matched-run setup in {trace}")
    metadata = {
        "restored_cycle": observation["restored_cycle"],
        "restored_slot_1": slot,
        "period_ms": int(config["cycle_ms"]),
        "sequence_status": sequence,
        "first_tick_ns": int(FIRST_TICK.search(events)[1]),
        "stuck_markers": [list(map(int, marker)) + [1] for marker in STUCK.findall(events)],
        "slot_1_retired_at": retirements,
        "detected_disagreements": observation["detected"],
    }
    return metadata, rows


def accept_newer(connection, cycle):
    # One ordered stream. Commit the high-water mark before returning acceptance.
    with connection:
        updated = connection.execute(
            "UPDATE stream SET last_cycle = ? WHERE last_cycle < ?", (cycle, cycle)
        )
        return updated.rowcount == 1


def replay_with_persistent_state(db, prior_rows, rows):
    with closing(sqlite3.connect(db)) as connection:
        with connection:
            connection.execute("CREATE TABLE stream (last_cycle INTEGER NOT NULL)")
            connection.execute("INSERT INTO stream VALUES (-1)")
        for _, cycle, _ in prior_rows:
            if not accept_newer(connection, cycle):
                raise ValueError("History is not strictly ordered")

    # A new connection has only the committed state from the prior consumer.
    with closing(sqlite3.connect(db)) as connection:
        return [accept_newer(connection, cycle) for _, cycle, _ in rows]


def measure(rows, accepted, history_cycles, tick_ns):
    delivered = [row for row, accept in zip(rows, accepted) if accept]
    fresh = next((row for row in delivered if row[2] and row[1] > max(history_cycles)), None)
    return {
        "accepted": len(delivered),
        "accepted_repeated_cycles": [cycle for _, cycle, _ in delivered if cycle in history_cycles],
        "accepted_wrong": sum(not correct for _, _, correct in delivered),
        "first_fresh_correct_cycle": None if fresh is None else fresh[1],
        "first_tick_to_fresh_correct_ms": None if fresh is None else round((fresh[0] - tick_ns) / 1e6, 3),
    }


def analyze(trials, output):
    result = {}
    with (output / "fprime-matched-output.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["trial", "case", "receive_monotonic_ns", "cycle", "correct",
                         "pass_through_accepted", "high_water_accepted"])
        for directory in trials:
            history_metadata, history = load_case(directory, "history")
            prior = [row for row in history if row[1] < 200]
            if [cycle for _, cycle, correct in prior if correct] != list(range(190, 200)) or len(prior) != 10:
                raise ValueError(f"Missing or incorrect prior output in {directory}")
            history_cycles = {cycle for _, cycle, _ in prior}
            writer.writerows((directory.name, "history", *row, 1, 1) for row in prior)
            cases = {}
            with TemporaryDirectory() as tmp:
                for name in ("active-fault", "retired-fault", "active-control"):
                    metadata, rows = load_case(directory, name)
                    kept = replay_with_persistent_state(Path(tmp) / f"{name}.sqlite", prior, rows)
                    writer.writerows((directory.name, name, *row, 1, int(accept)) for row, accept in zip(rows, kept))
                    tick_ns = metadata["first_tick_ns"]
                    cases[name] = {
                        **metadata,
                        "pass_through": measure(rows, [True] * len(rows), history_cycles, tick_ns),
                        "persistent_high_water": measure(rows, kept, history_cycles, tick_ns),
                    }
            result[directory.name] = {
                "history": history_metadata,
                "prior_cycles": sorted(history_cycles),
                "recovery": cases,
            }
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Existing output directory")
    parser.add_argument("trials", nargs="+", type=Path, help="One or more distinct trial directories")
    args = parser.parse_args()
    if len({path.name for path in args.trials}) != len(args.trials):
        parser.error("Trial directory names must be distinct")
    result = json.dumps(analyze(args.trials, args.output), indent=2) + "\n"
    (args.output / "fprime-matched-replay.json").write_text(result, encoding="utf-8")
