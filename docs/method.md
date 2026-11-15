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
