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


def write_csv(name, rows):
    with (BUILD / name).open("w", encoding="utf-8", newline="") as output:
        writer = csv.DictWriter(output, fieldnames=list(rows[0]), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description="Run the Mru replica reset-order experiment.")
    parser.add_argument("--cxx", nargs="+", default=["c++"], help="Compiler command, for example zig c++")
    args = parser.parse_args()
    BUILD.mkdir(exist_ok=True)
    binaries = {snapshot: build_reset_fixture(snapshot, args.cxx) for snapshot in SNAPSHOTS}
    rows = check_reset_cases(binaries)
    write_csv("reset-order.csv", rows)
    print(f"{len(rows)} reset-order cases passed.")


if __name__ == "__main__":
    main()
