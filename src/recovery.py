"""Deterministic post-reset cycle replay using the original Mru voter."""

START_CYCLES = (302, 303)
HORIZON = 6
FAULTS = ("cleared", "persistent_detected", "persistent_missed")
BOOT_POLICIES = ("resume", "revalidate")
FAULTY_SLOT = 2  # Bit mask for slot 1.
HEALTHY_SLOT = 4  # Bit mask for slot 2. Slot 0 is already retired.

# Each pair lists the first correct cycle offset for starts at 302 and 303.
# None means the correct value was not delivered within the observation window.
EXPECTED = {
    (6, "cleared", "resume"): (0, 0),
    (6, "cleared", "revalidate"): (1, 1),
    (6, "persistent_detected", "resume"): (2, 1),
    (6, "persistent_detected", "revalidate"): (2, 1),
    (6, "persistent_missed", "resume"): (None, None),
    (6, "persistent_missed", "revalidate"): (None, None),
    (4, "cleared", "resume"): (0, 1),
    (4, "cleared", "revalidate"): (0, 1),
    (4, "persistent_detected", "resume"): (0, 1),
    (4, "persistent_detected", "revalidate"): (0, 1),
    (4, "persistent_missed", "resume"): (0, 1),
    (4, "persistent_missed", "revalidate"): (0, 1),
}


def replay(mask, start, fault, policy, vote):
    # The synthetic diagnostic result is an input independent of the vote.
    isolate_on_test = fault == "persistent_detected"
    reply_fault = "clear" if fault == "cleared" else "persist"
    for offset in range(HORIZON):
        cycle = start + offset
        eligible = mask
        if offset == 0 and policy == "revalidate" and eligible & FAULTY_SLOT:
            if isolate_on_test:
                mask &= ~FAULTY_SLOT
            yield (cycle, eligible, "-", "boot_test", 1, mask)
            continue
        if mask == HEALTHY_SLOT and cycle % 2:
            yield (cycle, eligible, "SelfCheck", "idle", 0, mask)
            continue
        mode, output, diagnose = vote(mask, reply_fault)
        tested = int(diagnose)  # Model a diagnosis that completes before the next tick.
        if tested and isolate_on_test:
            mask &= ~FAULTY_SLOT
        yield (cycle, eligible, mode, output, tested, mask)


def check_recovery_cases(restores, vote):
    traces = []
    summary = []
    for cut, mask in restores.items():
        for start_index, start in enumerate(START_CYCLES):
            for fault in FAULTS:
                for policy in BOOT_POLICIES:
                    case = {"cut": cut, "initial_restored_mask": mask, "start_cycle": start,
                            "fault": fault, "boot_policy": policy}
                    rows = list(replay(mask, start, fault, policy, vote))
                    first_correct = next((t[0] - start for t in rows if t[3] == "correct"), None)
                    wrong = sum(t[3] == "wrong" for t in rows)
                    if first_correct != EXPECTED[(mask, fault, policy)][start_index] or wrong:
                        raise AssertionError((case, rows))
                    for cycle, eligible, mode, output, tested, next_mask in rows:
                        traces.append({**case, "cycle": cycle, "eligible_mask": eligible,
                                       "mode": mode, "output": output,
                                       "diagnostic_performed": tested, "next_mask": next_mask})
                    summary.append({**case, "first_correct_cycle_offset": first_correct,
                                    "correct_cycles": sum(t[3] == "correct" for t in rows),
                                    "withheld_disagreements": sum(t[3] == "withheld" for t in rows),
                                    "boot_test_cycles": sum(t[3] == "boot_test" for t in rows),
                                    "idle_cycles": sum(t[3] == "idle" for t in rows),
                                    "wrong_cycles": wrong})
    return summary, traces
