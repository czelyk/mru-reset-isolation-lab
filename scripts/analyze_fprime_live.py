"""Verify live receiver records and combine complete F Prime trials."""

import argparse
import csv
import json
from collections import Counter
from pathlib import Path

from run_fprime_live import CASES, FIELDS, MAX_AGE_NS, expected_sample_value


def read_rows(path):
    with path.open(newline="", encoding="ascii") as stream:
        return list(csv.DictReader(stream))


def audit_case(directory):
    result = json.loads((directory / "result.json").read_text(encoding="ascii"))
    samples = {
        int(sample["cycle"]): (int(sample["source_ns"]), [int(sample[f"input_{index}"]) for index in (1, 2, 3)])
        for sample in read_rows(directory / "samples.csv")
    }
    rows = read_rows(directory / "receiver.csv")
    kill = result["before"]["kill_ns"]
    restart_tick = result["after"]["tick_ns"]
    during_restart = sum(kill < time < restart_tick for time, _ in samples.values())
    before_fault_pid = result["before"]["fault_replies"][0][0]
    after_fault_pid = next((record[0] for record in result["after"]["fault_replies"]), None)
    if during_restart == 0 or before_fault_pid == after_fault_pid:
        raise ValueError(f"Did not independently observe the source or replica across restart in {directory}")
    last_order = last_live = -1
    for row in rows:
        cycle = int(row["cycle"])
        origin, values = samples[cycle]
        received, port = int(row["receive_ns"]), int(row["port_ns"])
        age = received - origin
        accepted_order = cycle > last_order
        decision = "old-id" if cycle <= last_live else "stale-source" if age > MAX_AGE_NS else "accepted"
        expected = expected_sample_value(result["workload"], values)
        if (
            int(row["source_ns"]) != origin or not origin <= port <= received or int(row["age_ns"]) != age
            or int(row["expected"]) != expected or int(row["correct"]) != (int(row["value"]) == expected)
            or int(row["sequence_only_accept"]) != accepted_order or row["live_decision"] != decision
        ):
            raise ValueError(f"Receiver record or oracle mismatch in {directory} for cycle {cycle}")
        if accepted_order:
            last_order = cycle
        if decision == "accepted":
            last_live = cycle

    after = [row for row in rows if row["phase"] == "after"]
    correct = [row for row in after if row["correct"] == "1"]
    first_order = next((row for row in correct if row["sequence_only_accept"] == "1"), None)
    first_live = next((row for row in correct if row["live_decision"] == "accepted"), None)
    counts = Counter(row["live_decision"] for row in after)
    summary = {
        "workload": result["workload"], "start_cycle": result["start_cycle"], "condition": result["condition"],
        "manager_kill_ns": kill, "restarted_first_tick_ns": restart_tick,
        "samples_during_restart": during_restart, "receiver_pid": result["receiver_pid"],
        "pre_replica_pid": before_fault_pid, "post_fault_replica_pid": after_fault_pid,
        "post_first_fault_cycle": next((record[1] for record in result["after"]["fault_replies"]), None),
        "old_ids": counts["old-id"], "stale_source": counts["stale-source"], "live_accepted": counts["accepted"],
        "wrong_outputs": len(after) - len(correct),
        "wrong_live_accepted": sum(row["correct"] == "0" and row["live_decision"] == "accepted" for row in after),
    }
    for label, row in (("order", first_order), ("live", first_live)):
        summary[f"{label}_first_cycle"] = int(row["cycle"]) if row else None
        summary[f"{label}_first_age_ms"] = round(int(row["age_ns"]) / 1e6, 3) if row else None
        summary[f"{label}_first_from_kill_ms"] = round((int(row["receive_ns"]) - kill) / 1e6, 3) if row else None
        actual = result[f"first_{label}_correct"]
        if summary[f"{label}_first_cycle"] != (actual["cycle"] if actual else None):
            raise ValueError(f"Online and verified first acceptance disagree in {directory}")
    return summary, rows


def analyze(output, trials, cycles):
    summaries, decisions = [], []
    for trial in trials:
        for workload in ("hash", "median"):
            for cycle in cycles:
                for case in CASES:
                    summary, rows = audit_case(trial / f"{workload}-{cycle}-{case}")
                    summaries.append({"trial": trial.name, **summary})
                    decisions.extend({"trial": trial.name, "workload": workload, "restored_cycle": cycle,
                                      "condition": case, **row} for row in rows)
    for filename, rows in (("fprime-live-results.csv", summaries), ("fprime-live-rows.csv", decisions)):
        with (output / filename).open("w", newline="", encoding="ascii") as stream:
            writer = csv.DictWriter(stream, fieldnames=rows[0], lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
    print(f"Verified {len(decisions)} live rows across {len(summaries)} manager restarts.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("trials", type=Path, nargs="+")
    parser.add_argument("--cycles", type=int, nargs="+", default=[190, 198, 199])
    args = parser.parse_args()
    if len({trial.name for trial in args.trials}) != len(args.trials):
        parser.error("Trial directory names must be distinct")
    analyze(args.output, args.trials, args.cycles)
