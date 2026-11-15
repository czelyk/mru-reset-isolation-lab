# Reset-order experiment

The Mru v0.7.0 orbit run restored replica membership after the voter process restarted from a valid checkpoint. That is the positive control for the project. The accompanying run did not power-cycle the board. [Published run report](https://github.com/mruspace/flight/blob/cf6d25db1fea2e2dc5588efa87b2441a7762da5c/docs/opssat.md)

This fixture asks whether the local retirement event can precede the durable membership change. We extract the original retirement function body and bind it to a fixture with explicit boundaries at the disable callback, event callback and before and after the durable write. The fixture models a healthy storage device that keeps every completed commit. With no interruption the retired slot stays out. The comparison disables the slot immediately, commits the new membership and then reports it.

Each of the two pinned snapshots has two constructed reset points in the event-to-commit interval where retirement is reported and the previous slot state is restored. The comparison closes that reported-completion gap. A pre-commit reset can still restore the previous membership. These are targeted cases in one interval, so the counts have no frequency interpretation. The event is a function call in the fixture. There is no F Prime event transport, hardware reset, actual filesystem or OS scheduling in this experiment.

Strom and Yemini establish the general principle of committing recoverable state before releasing external output. A useful avionics extension would need to show a decision-changing difference under representative reset and fault behavior. [Output-commit prior work](https://www.cs.cornell.edu/courses/cs717/2001fa/papers/p204-strom.pdf)


## Voter follow-up

The follow-up compiles the unmodified v0.7.0 quorum crate and calls its shrinking-quorum policy. The original C++ retirement function comes from both snapshots. The recorded membership then selects which replies are present in Rust. This links the two actual upstream logic bodies through a fixture. It does not run the full F Prime manager, message queues, startup scheduler, or diagnosis and readmission sequence.

The 80 deterministic cases cover two source snapshots, two retirement orders, five reset boundaries, two initial memberships (either all three available or slot 0 already retired), and two post-reset fault behaviors. Slot 1 is the subject of retirement. Under a persistent fault it returns 99 if restored to active membership, while healthy slots always return 42. In the cleared-fault controls slot 1 also returns 42. Where self-check is used, this fixture supplies two equal replies from the single healthy slot for an eligible voting cycle. It does not count scheduler cycles between self-checks. CRC checks, media behavior and failure rates are outside this model. The expected output comes from an explicit table based on available healthy channels and independently checks the compiled voter output.

| Persistent fault and one channel already retired | Correct output | Withheld output |
| --- | ---: | ---: |
| Upstream ordering | 4 | 6 |
| Commit before reporting | 6 | 4 |

All corresponding cases with two healthy replicas available returned the correct value, and all cleared-fault controls returned the correct value. None of the 80 cases delivered an incorrect value. The rows are deliberately chosen combinations across two versions. Their counts are test coverage, with no probability interpretation. The comparator changes when retirement is announced. It cannot persist the decision when the reset happens before the commit.

Windows replay used Python 3.12.10, Zig 0.14.1 and Rust 1.96.0. The next research gate is physical or integrated evidence that the fault and reset combination occurs in a representative avionics topology, and measurement of time to first correct output versus boot-time revalidation. [Mru decision core](https://github.com/mruspace/flight/blob/bbdad5436e0a699c07a08d07215e0122132602cf/quorum/src/lib.rs#L83-L139)

## Recovery across consecutive cycles

This replay starts with slot 0 already retired and uses the flown snapshot's C++ retirement body to obtain two checkpoints. A reset before the commit restores slots 1 and 2 as active. A reset after the commit restores only healthy slot 2. The replay calls the original Mru voter on each modeled compute cycle and uses the manager's even-cycle cadence for single-replica self-checks. It starts at cycle 303, the cycle in the published restart record, and at adjacent cycle 302 as a parity control. Every run spans six cycles starting at offset 0. The horizon is a test choice. [Flown manager](https://github.com/mruspace/flight/blob/bbdad5436e0a699c07a08d07215e0122132602cf/fprime/Mru/Components/RedundancyManager/RedundancyManager.cpp#L340-L404)

The resume baseline uses the restored membership immediately. When the voter requests diagnosis, the replay models the known-answer checks completing before the next cycle. The boot revalidation baseline spends the first cycle validating only the questionable, still-eligible slot. Both use the same stipulated diagnostic coverage. One fault survives restart and fails that check. A second fault survives and passes the check while disagreeing on the normal workload. A cleared-fault control agrees on normal outputs and passes the check. The diagnostic is a scripted result. The replay does not execute the real F Prime ports, diagnostic routing, storage, scheduler or power reset. [Mru voter and diagnosis flag](https://github.com/mruspace/flight/blob/bbdad5436e0a699c07a08d07215e0122132602cf/quorum/src/lib.rs#L94-L139)

| Restored checkpoint | Fault | Resume | Boot revalidation |
| --- | --- | --- | --- |
| Before commit | Cleared | 0 / 0 | 1 / 1 |
| Before commit | Persistent and detected | 2 / 1 | 2 / 1 |
| Before commit | Persistent and missed | None in six cycles | None in six cycles |
| After commit | Any of the tested faults | 0 / 1 | 0 / 1 |

Values are cycles to the first correct output for starts at cycle 302 and cycle 303, respectively. Across 24 scenarios and 144 trace rows there were no wrong outputs. With a detectable persistent fault, the ordinary voter withheld a cycle before diagnosis. Boot revalidation substituted a boot-test cycle without advancing the first correct result under these delivery assumptions. With a cleared fault, boot revalidation cost one cycle before the commit; after the commit the retired slot was already excluded and no boot test was scheduled.

This test makes diagnostic coverage and actual completion phase the next hardware measurements. Measure when a real known-answer test responds and whether it covers a persistent normal-workload fault. The equal first-output result relies on both diagnostics completing within the modeled cycle. None of these cases estimates wall-clock recovery time or field fault coverage.

## Integrated F Prime process restart

The released ARMv7 MruQuorum and MruReplica executables and the original command sequence ran in an emulated Linux container on a Windows host. Their SHA-256 values matched the published experiment log. The published restart-only control recovered the expected membership at cycle 303 and returned 297 and 298 correct outputs across two local replays, with zero incorrect outputs and zero detected disagreements in both runs. The flight log reports 299 correct outputs for its 30-second window, which is consistent with environment-dependent cycle counts. [Publisher release](https://github.com/mruspace/flight/releases/tag/v0.7.0) · [Flight logs](https://github.com/mruspace/flight/tree/cf6d25db1fea2e2dc5588efa87b2441a7762da5c/opssat/results/2026-10-28-ops-sat-pretty-on-board-run3)

For the new paired experiment, the synthetic starting checkpoint holds slot 0 retired and slots 1 and 2 active, with next cycle 190. In both initial deployments the released sequence injects the slot 1 fault at cycle 200. The real manager detects a disagreement, performs diagnosis and emits the known-answer failure retirement event at cycle 200. In the first condition a Linux FIFO at the temporary checkpoint path deliberately blocks the writer before it can persist the new membership. The observed manager task wait channel was wait_for_partner. In the second condition the runner allows the replacement to complete and checks that the main checkpoint changed. It kills the manager process in both conditions. New replica processes are launched at restart, so the same upstream sequence supplies a repeatable fault when the restored schedule reaches its injection cycle. No physical fault persisted across a reboot in this test.

| Interruption | Restored cycle and membership | Outcome during the restarted process |
| --- | --- | --- |
| Before the save | 190, retired / active / active | The re-injected slot 1 fault caused one detected disagreement in compare mode at cycle 200. It was diagnosed and retired again in that cycle. |
| After the save | 201, retired / retired / active | The manager started in single-replica self-check. There were no detected disagreements. |

The pre-commit case shows that a valid old checkpoint can yield a successful restore event while restoring eligibility for a previously retired slot. The new cycle-200 disagreement was an actual voter outcome from the published executable. The post-commit control had a different restored cycle and voting mode. The two aggregate totals do not estimate an availability improvement. The released recorder lacks timestamps or cycle IDs for every correct delivered output, so time to the first correct output after the fault remains unmeasured. The injected FIFO hold ensures the ordering can be observed and does not estimate the natural duration or frequency of the save window. This is process-level emulation. A future run needs a recorder on the downstream output port and a fault or fault stimulus that is independent of restarting the voter and replica processes.

To run the package control and both interruptions with Python and Docker configured for Linux ARMv7 execution:

    python -B scripts/run_fprime_integration.py build/integration-replay

Use a fresh output directory. The runner verifies a pinned package hash, uses a pinned ARM Linux image, runs the test container without networking, and checks the recovered memberships and output summaries. It leaves the full traces under the output directory. The checked-in [observations](../results/fprime-reset-observations.json) record the two executed replays.
