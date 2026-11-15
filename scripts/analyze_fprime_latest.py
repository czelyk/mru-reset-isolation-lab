"""Compare checkpoint replay and forward-only restart on the same F Prime build."""

import argparse
import csv
import json
from itertools import product
from pathlib import Path

from analyze_fprime_live import audit_case, read_rows
from run_fprime_live import FAULT_CYCLE


def audit_selection(directory, start, policy):
    result = json.loads((directory / "result.json").read_text(encoding="ascii"))
    if policy == "checkpoint":
        if "latest" in result["after"]:
            raise ValueError(f"Checkpoint replay changed the cursor in {directory}")
        return {"selected_cycle": start, "cursor_jump": 0, "new_source_ids_skipped": 0}
    old, selected, scan_start, scan_end = result["after"]["latest"]
    samples = read_rows(directory / "samples.csv")
    visibly_published = [int(row["cycle"]) for row in samples if int(row["published_ns"]) < scan_start]
    prepared = [int(row["cycle"]) for row in samples if int(row["source_ns"]) <= scan_end]
    skipped = max(0, selected - FAULT_CYCLE)
    if (
        old != start or not result["before"]["kill_ns"] < scan_start <= scan_end
        or not visibly_published or not prepared
        or not max(start, max(visibly_published)) <= selected <= max(prepared)
        or result["new_source_ids_skipped"] != skipped or "latest" in result["before"]
    ):
        raise ValueError(f"Selected cursor disagrees with source timeline in {directory}")
    return {
        "selected_cycle": selected, "cursor_jump": selected - start, "new_source_ids_skipped": skipped,
        "scan_start_ns": scan_start, "scan_end_ns": scan_end,
        "last_published_before_scan": max(visibly_published), "last_prepared_by_scan_end": max(prepared),
    }


def comparison_cases(trials, phase_trials):
    workloads = ("hash", "median")
    persistent = ("active-persistent", "retired-persistent")
    for trial, workload, start, case, policy in product(
        trials, workloads, (190, 198, 199), ("active-clear", *persistent), ("checkpoint", "latest")
    ):
        yield trial, workload, start, case, policy, 0
    for trial, workload, case in product(phase_trials, workloads, persistent):
        yield trial, workload, 190, case, "latest", 100


def analyze(output, trials, phase_trials):
    summaries, decisions = [], []
    for trial, workload, start, case, policy, delay in comparison_cases(trials, phase_trials):
        name = f"{workload}-{start}-{case}"
        directory = trial / (name if policy == "checkpoint" else f"{name}-latest")
        base = {"trial": trial.name, "policy": policy, "restart_delay_ms": delay}
        summary, rows = audit_case(directory)
        selection = audit_selection(directory, start, policy)
        result = json.loads((directory / "result.json").read_text(encoding="ascii"))
        if result.get("restart_delay_ms", 0) != delay:
            raise ValueError(f"Unexpected restart phase in {directory}")
        summaries.append({**base, **summary, **selection})
        decisions.extend({**base, "workload": workload, "restored_cycle": start,
                          "condition": case, **row} for row in rows)
    for filename, rows in (("fprime-latest-results.csv", summaries), ("fprime-latest-rows.csv", decisions)):
        fields = list(dict.fromkeys(key for row in rows for key in row))
        with (output / filename).open("w", newline="", encoding="ascii") as stream:
            writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    print(f"Verified {len(decisions)} live rows across {len(summaries)} manager restarts.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("trials", type=Path, nargs="+")
    parser.add_argument("--phase-trials", type=Path, nargs="+", default=[])
    args = parser.parse_args()
    all_trials = args.trials + args.phase_trials
    if len({trial.name for trial in all_trials}) != len(all_trials):
        parser.error("Trial directory names must be distinct")
    analyze(args.output, args.trials, args.phase_trials)
