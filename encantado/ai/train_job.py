"""Train a grain model in a separate process.

CUDA and Qt worker threads do not get along on this stack — initialising a CUDA
context inside a QThread segfaults the whole application. Training therefore
runs as its own process: the GUI stays responsive, and if training dies it
cannot take the user's project down with it.

Usage:  python -m encantado.ai.train_job <job.json>
Emits:  PROGRESS <fraction> <message> | DONE <path> | ERROR <message>
"""
from __future__ import annotations

import json
import sys


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("ERROR no job file", flush=True)
        return 2
    try:
        with open(argv[1], encoding="utf-8") as fh:
            job = json.load(fh)
    except Exception as exc:
        print(f"ERROR could not read job: {exc}", flush=True)
        return 2

    def emit(frac: float, msg: str) -> bool:
        print(f"PROGRESS {frac:.4f} {msg}", flush=True)
        return True

    try:
        from .dataset import build_dataset
        from .trainer import GrainModel, TrainConfig

        paths = list(job["paths"])
        emit(0.02, "reading audio…")
        patches, feats, _ = build_dataset(
            paths, progress=lambda f, m: emit(0.02 + f * 0.20, m),
            max_grains=int(job.get("max_grains", 4000)))
        if patches.size == 0:
            print("ERROR no usable audio in those files", flush=True)
            return 1
        model = GrainModel()
        model.sources = paths
        model.fit(patches,
                  TrainConfig(epochs=int(job.get("epochs", 120)),
                              max_seconds=float(job.get("seconds", 180))),
                  progress=lambda f, m: emit(0.22 + f * 0.72, m))
        emit(0.96, "calibrating controls…")
        model.calibrate(patches, feats)
        out = job["out"]
        model.save(out)
        print(f"DONE {out}", flush=True)
        return 0
    except Exception as exc:
        print(f"ERROR {exc}", flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
