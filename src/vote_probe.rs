use quorum::{decide, Outcome, Policy, Reply, REPLICAS};

const CORRECT: u64 = 42;
const INCORRECT: u64 = 99;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    let [_, mask, fault] = args.as_slice() else {
        panic!("usage: vote_probe ACTIVE_MASK persist|clear");
    };
    let mask = mask.parse::<u8>().expect("numeric active mask");
    assert!(mask < 1 << REPLICAS, "three slots only");
    let persists = match fault.as_str() {
        "persist" => true,
        "clear" => false,
        _ => panic!("fault must be persist or clear"),
    };

    let mut replies = [Reply::Absent; REPLICAS];
    for (slot, reply) in replies.iter_mut().enumerate() {
        if mask & (1 << slot) == 0 {
            continue;
        }
        let value = if slot == 1 && persists { INCORRECT } else { CORRECT };
        *reply = if mask.count_ones() == 1 {
            Reply::Pair(value, value)
        } else {
            Reply::Single(value)
        };
    }

    let verdict = decide(Policy::Shrink, &replies);
    let output = match verdict.outcome {
        Outcome::Deliver(CORRECT) => "correct",
        Outcome::Deliver(_) => "wrong",
        Outcome::Detected => "withheld",
        Outcome::Halted => "halted",
    };
    println!("{:?},{output},{}", verdict.mode, u8::from(verdict.diagnose));
}
