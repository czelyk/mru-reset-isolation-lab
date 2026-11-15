"""Run the pinned flight-package control and controlled checkpoint interruptions."""

import argparse
import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tarfile
import zlib
from pathlib import Path
from urllib.request import urlretrieve

ROOT = Path(__file__).resolve().parents[1]
ASSET = "exp4051-mru-flight-fprime-processes-v0.7.0.tar.gz"
URL = f"https://github.com/mruspace/flight/releases/download/v0.7.0/{ASSET}"
SHA256 = "ab4af9778d67ca6d9010ad53ce6a687163c5932535cf31395af5e34880eb445d"
IMAGE = "debian@sha256:734a72b3d6142a71993b4bc580ca01d8ca687f77a2c422d96a961d3376b179bc"
FILES = ("run", "MruQuorum", "MruReplica", "shrink.bin", "tmr.bin", "restart.bin")


def unpack(path, target):
    if hashlib.sha256(path.read_bytes()).hexdigest() != SHA256:
        raise SystemExit(f"Unexpected SHA-256 for {path}")
    target.mkdir()
    with tarfile.open(path, "r:gz") as archive:
        for name in FILES:
            member = archive.getmember(name)
            if not member.isfile():
                raise SystemExit(f"Expected a regular file in the archive: {name}")
            file = target / name
            with archive.extractfile(member) as source, file.open("wb") as destination:
                shutil.copyfileobj(source, destination)
            os.chmod(file, 0o755)


def run_docker(flight, output, command, *, env=(), probe=None):
    output.mkdir()
    args = ["docker", "run", "--rm", "--platform", "linux/arm/v7", "--network", "none",
            "--mount", f"type=bind,source={flight},target=/flight,readonly",
            "--mount", f"type=bind,source={output},target=/output"]
    for key, value in env:
        args.extend(("--env", f"{key}={value}"))
    if probe is not None:
        args.extend(("--mount", f"type=bind,source={probe},target=/probe.sh,readonly"))
        # A temporary seed outside the runtime container is passed as an ordinary file.
        subprocess.run([sys.executable, str(ROOT / "scripts/make_fprime_seed.py"),
                        str(output / "seed.dat")], check=True)
    subprocess.run([*args, IMAGE, "/bin/bash", command], check=True, timeout=120)


def summary_counts(path):
    lines = path.read_text().splitlines()
    entries = dict(field.split("=", 1) for field in lines[1].split())
    return {name: int(entries[name]) for name in ("useful", "detected", "wrong", "late")}


def verify(control, cut):
    positive = (control / "events-restart-2.txt").read_text()
    control_info = (control / "run-info.txt").read_text()
    if ("restart-1: exit=137" not in control_info
            or "slots [ ACTIVE (0), RETIRED (2), ACTIVE (0) ], cycle 303" not in positive):
        raise SystemExit("The published restart control did not reproduce.")
    control_counts = summary_counts(control / "summary-restart.txt")
    if control_counts["useful"] == 0 or control_counts["wrong"] != 0:
        raise SystemExit(f"Unexpected published-control output: {control_counts}")

    seeds = {name: (cut / name).read_bytes()
             for name in ("seed.dat", "precommit-at-kill.dat", "postcommit-at-kill.dat")}
    for name, record in seeds.items():
        if len(record) != 21 or zlib.crc32(record[:-4]) != int.from_bytes(record[-4:], "little"):
            raise SystemExit(f"Invalid checkpoint record: {name}")
    if seeds["seed.dat"] != seeds["precommit-at-kill.dat"]:
        raise SystemExit("The pre-commit checkpoint does not match the seed.")
    postcommit = seeds["postcommit-at-kill.dat"]
    if postcommit[6:9] != bytes((2, 2, 0)) or struct.unpack_from("<Q", postcommit, 9)[0] != 201:
        raise SystemExit("The post-commit checkpoint has unexpected membership or cycle.")
    observations = {}
    for name in ("precommit", "postcommit"):
        before = (cut / f"{name}-before-events.txt").read_text()
        after = (cut / f"{name}-after-events.txt").read_text()
        counts = summary_counts(cut / f"{name}-after-summary.txt")
        if "Replica 1 retired (KNOWN_ANSWER_FAILED (0)) at cycle 200" not in before:
            raise SystemExit(f"{name} does not retire replica 1 before interruption.")
        if counts["wrong"] != 0 or counts["useful"] == 0:
            raise SystemExit(f"Unexpected output after {name}: {counts}")
        if name == "precommit":
            if ("slots [ RETIRED (2), ACTIVE (0), ACTIVE (0) ], cycle 190" not in after
                    or "Disagreement caught at cycle 200 in COMPARE" not in after
                    or "Replica 1 retired (KNOWN_ANSWER_FAILED (0)) at cycle 200" not in after
                    or counts["detected"] < 1):
                raise SystemExit("Pre-commit replay did not reproduce the old membership and disagreement.")
        elif ("slots [ RETIRED (2), RETIRED (2), ACTIVE (0) ], cycle 201" not in after
              or "Disagreement caught" in after or counts["detected"] != 0):
            raise SystemExit("Post-commit replay did not preserve retirement.")
        record = seeds[f"{name}-at-kill.dat"]
        observations[name] = {
            "restored_cycle": struct.unpack_from("<Q", record, 9)[0],
            "restored_slot_ids": list(record[6:9]),
            "checkpoint_sha256": hashlib.sha256(record).hexdigest(),
            "restart_summary": counts,
        }
        print(f"{name}: {counts}")
    print(f"published restart: {control_counts}")
    return {
        "published_control": {"restored_cycle": 303, "restart_summary": control_counts},
        "controlled_interruption": observations,
        "precommit_fifo_wait_observed": "wait_for_partner" in (cut / "precommit-wait-channels.txt").read_text(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path, help="New directory for package and raw traces")
    parser.add_argument("--archive", type=Path, help="Use an existing copy of the release package")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True)
    archive = args.archive
    if archive is None:
        archive = output / ASSET
        urlretrieve(URL, archive)
    flight = output / "flight"
    unpack(archive, flight)
    control = output / "published-control"
    cut = output / "controlled-cut"
    run_docker(flight, control, "/flight/run", env=(("SEGMENTS", "restart"), ("OUT_DIR", "/output")))
    run_docker(flight, cut, "/probe.sh", probe=ROOT / "scripts/run_fprime_reset.sh")
    observations = verify(control, cut)
    (output / "observations.json").write_text(json.dumps(observations, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
