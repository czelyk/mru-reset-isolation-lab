"""Score the boot-check variants on matched checkpoint and reply-fault traces."""

import argparse
import csv
import json
import re
from pathlib import Path
from tempfile import TemporaryDirectory

from analyze_fprime_output import FIRST_TICK, observe
from replay_fprime_consumer import RESTORED_SLOTS, RETIREMENT, measure, replay_with_persistent_state


START_CYCLE = 190
LAST_SCORED_CYCLE = 208
BOOT_START = re.compile(r"^MRU_BOOT_START,(\d+)$", re.MULTILINE)
BOOT_REPLY = re.compile(r"^MRU_BOOT_REPLY,(\d+),([01])$", re.MULTILINE)
FIXTURE = re.compile(r"^MRU_BOOT_FIXTURE,(\d+),1,([01])$", re.MULTILINE)


def load_case(directory, name, scenario, boot):
    trace = directory / f"{name}-events.txt"
    summary = directory / f"{name}-summary.txt"
    obs, rows = observe(trace, summary, allow_no_correct=True)
    events = trace.read_text(encoding="utf-8")
    config = dict(field.split("=", 1) for field in summary.read_text(encoding="utf-8").splitlines()[0].split())
    start = list(map(int, BOOT_START.findall(events)))
    replies = sorted(tuple(map(int, reply)) for reply in BOOT_REPLY.findall(events))
    expected_replies = [(1, int(scenario != "visible")), (2, 1)] if boot else []
    faults = [tuple(map(int, fault)) for fault in FIXTURE.findall(events)]
    expected_first_fault = (START_CYCLE - 1, 1) if boot and scenario == "visible" else (START_CYCLE, 0)
    if (
        RESTORED_SLOTS.findall(events) != ["ACTIVE (0)"] or config["cycle_ms"] != "100"
        or config["sequence"] != "none" or int(config["cycles"]) < LAST_SCORED_CYCLE - START_CYCLE + 1 + int(boot)
        or start != ([START_CYCLE] if boot else []) or replies != expected_replies
        or "MRU_BOOT_UNANSWERED" in events
        or (bool(faults) and faults[0] != expected_first_fault)
        or bool(faults) != (scenario != "cleared")
        or (scenario == "blind" and any(is_check for _, is_check in faults))
    ):
        raise ValueError(f"Boot check or fault setup did not match in {trace}")
    return {
        "restored_cycle": obs["restored_cycle"],
        "scheduled_ticks": int(config["cycles"]),
        "first_tick_ns": int(FIRST_TICK.search(events)[1]),
        "boot_replies": replies,
        "injected_reply_faults": faults,
        "slot_1_retired_at": list(map(int, RETIREMENT.findall(events))),
        "detected_disagreements": obs["detected"],
        "first_correct_cycle": obs["first_correct_cycle"],
        "first_tick_to_correct_ms": obs["first_tick_to_first_correct_ms"],
    }, [row for row in rows if row[1] <= LAST_SCORED_CYCLE]


def analyze(trials, output):
    results = {}
    with (output / "fprime-boot-output.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream, lineterminator="\n")
        writer.writerow(["trial", "case", "receive_monotonic_ns", "cycle", "correct", "high_water_accepted"])
        for trial in trials:
            _, history = load_case(trial, "history", "cleared", boot=False)
            prior = [row for row in history if row[1] < 200]
            if [cycle for _, cycle, correct in prior if correct] != list(range(START_CYCLE, 200)) or len(prior) != 10:
                raise ValueError(f"Missing or incorrect prior output in {trial}")
            history_cycles = {cycle for _, cycle, _ in prior}
            writer.writerows((trial.name, "history", *row, 1) for row in prior)
            scores = {}
            with TemporaryDirectory() as temp:
                for scenario in ("cleared", "visible", "blind"):
                    for mode in ("ordinary", "revalidate"):
                        name = f"{scenario}-{mode}"
                        obs, rows = load_case(trial, name, scenario, boot=(mode == "revalidate"))
                        accepted = replay_with_persistent_state(Path(temp) / f"{name}.sqlite", prior, rows)
                        writer.writerows((trial.name, name, *row, int(keep)) for row, keep in zip(rows, accepted))
                        scores[name] = {
                            **obs,
                            "cycles_without_result": LAST_SCORED_CYCLE - START_CYCLE + 1 - len(rows),
                            "consumer": measure(rows, accepted, history_cycles, obs["first_tick_ns"]),
                        }
            results[trial.name] = scores
    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="Existing output directory")
    parser.add_argument("trials", nargs="+", type=Path)
    args = parser.parse_args()
    if len({path.name for path in args.trials}) != len(args.trials):
        parser.error("Trial directory names must be distinct")
    result = json.dumps(analyze(args.trials, args.output), indent=2) + "\n"
    (args.output / "fprime-boot-revalidation.json").write_text(result, encoding="utf-8")
