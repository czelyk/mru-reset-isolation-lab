import argparse
import csv
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
BUILD = ROOT / "build"
SNAPSHOTS = ("bbdad54", "b885359")
ORDERINGS = ("upstream", "commit_then_report")
CUTS = ("disable", "retired_event", "before_commit", "after_commit", "none")


def build_reset_fixture(snapshot, cxx):
    source = ROOT / "upstream" / f"RedundancyManager-{snapshot}.cpp"
    pattern = r"^void RedundancyManager ::retire\([^\n]+\) \{\n.*?^\}"
    matches = re.findall(pattern, source.read_text(encoding="utf-8"), re.M | re.S)
    if len(matches) != 1:
        raise ValueError(f"Expected one retirement function in {source.name}")
    template = (ROOT / "src" / "reset_fixture.cpp.in").read_text(encoding="utf-8")
    generated = BUILD / f"reset-{snapshot}.cpp"
    function = matches[0].replace("RedundancyManager ::", "Manager::", 1)
    generated.write_text(template.replace("/* EXTRACT_RETIRE */", function), encoding="utf-8")
    binary = generated.with_suffix(".exe")
    subprocess.run([*cxx, "-std=c++17", "-Wall", "-Wextra", "-Werror", str(generated),
                    "-o", str(binary)], check=True, cwd=BUILD)
    return binary


def reset_case(binary, ordering, cut, initial_mask):
    raw = subprocess.check_output([str(binary), ordering, cut, str(initial_mask)], text=True)
    reset, announced, mask = map(int, raw.strip().split(","))
    return {"reset": reset, "retirement_event": announced, "restored_active_mask": mask}


def check_reset_cases(binaries):
    rows = []
    for snapshot, binary in binaries.items():
        for ordering in ORDERINGS:
            for cut in CUTS:
                result = reset_case(binary, ordering, cut, 7)
                restored_faulty = bool(result["restored_active_mask"] & 2)
                mismatch = bool(result["retirement_event"]) and restored_faulty
                expected_mismatch = ordering == "upstream" and cut in {"retired_event", "before_commit"}
                if (bool(result["reset"]) != (cut != "none") or mismatch != expected_mismatch
                        or (cut in {"after_commit", "none"} and restored_faulty)):
                    raise AssertionError((snapshot, ordering, cut, result))
                rows.append({"snapshot": snapshot, "ordering": ordering, "cut": cut, **result,
                             "announced_retirement_lost": int(mismatch)})
    return rows


def build_voter(rustc):
    library = BUILD / "libquorum.rlib"
    binary = BUILD / "vote-probe.exe"
    subprocess.run([rustc, "--edition=2021", "--crate-name", "quorum", "--crate-type=rlib",
                    str(ROOT / "upstream" / "quorum.rs"), "-o", str(library)], check=True, cwd=BUILD)
    subprocess.run([rustc, "--edition=2021", "--extern", f"quorum={library}",
                    str(ROOT / "src" / "vote_probe.rs"), "-o", str(binary)], check=True, cwd=BUILD)
    return binary


def check_voter_cases(binaries, voter):
    # These outcomes follow from agreeing healthy replies, one disagreeing reply,
    # and the documented quorum modes. They are checked against the original Rust voter.
    expected_modes = {7: "Vote", 6: "Compare", 5: "Compare", 4: "SelfCheck"}
    rows = []
    for snapshot, binary in binaries.items():
        for ordering in ORDERINGS:
            for cut in CUTS:
                for initial_mask in (7, 6):
                    result = reset_case(binary, ordering, cut, initial_mask)
                    restored_mask = result["restored_active_mask"]
                    after_commit = {"after_commit", "none"}
                    if ordering == "commit_then_report":
                        after_commit.add("retired_event")
                    expected_mask = initial_mask & ~2 if cut in after_commit else initial_mask
                    if expected_mask != restored_mask:
                        raise AssertionError((snapshot, ordering, cut, initial_mask, result))
                    for fault in ("persist", "clear"):
                        raw = subprocess.check_output([str(voter), str(restored_mask), fault], text=True)
                        mode, output, diagnose = raw.strip().split(",")
                        disagreement = expected_mask == 6 and fault == "persist"
                        expected = (expected_modes[expected_mask],
                                    "withheld" if disagreement else "correct", str(int(disagreement)))
                        if (mode, output, diagnose) != expected:
                            raise AssertionError((snapshot, ordering, cut, initial_mask, fault, raw))
                        rows.append({"snapshot": snapshot, "ordering": ordering, "cut": cut,
                                     "initial_active_mask": initial_mask, **result, "fault": fault,
                                     "mode": mode, "output": output, "diagnose": int(diagnose)})
    return rows


def write_csv(name, rows):
    with (BUILD / name).open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Run the Mru reset and voter experiments.")
    parser.add_argument("--cxx", nargs="+", default=["c++"], help="Compiler command, for example zig c++")
    parser.add_argument("--rustc", default="rustc", help="Path to the Rust compiler")
    parser.add_argument("--verify", action="store_true", help="Compare all generated rows to results/")
    args = parser.parse_args()
    BUILD.mkdir(exist_ok=True)
    binaries = {snapshot: build_reset_fixture(snapshot, args.cxx) for snapshot in SNAPSHOTS}
    results = {
        "reset-order.csv": check_reset_cases(binaries),
        "voter-output.csv": check_voter_cases(binaries, build_voter(args.rustc)),
    }
    for name, rows in results.items():
        write_csv(name, rows)
        if args.verify and (BUILD / name).read_bytes() != (ROOT / "results" / name).read_bytes():
            raise SystemExit(f"{name} differs from the recorded result.")
        print(f"{len(rows)} cases passed in {name}.")


if __name__ == "__main__":
    main()
