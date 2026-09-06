#!/usr/bin/env python3
"""Coordinator smoke test for 06-cli-batch."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "06-cli-batch"))

from dither_batch import discover_files  # noqa: E402

OUT_DIR = ROOT / "06-cli-batch" / "out"
SAMPLES = ROOT / "data" / "samples"
CLI = ROOT / "06-cli-batch" / "dither_batch.py"
PYTHON = ROOT / ".venv" / "bin" / "python"
DEFAULT_PATTERNS = ["*.png", "*.jpg", "*.jpeg", "*.webp"]


def run_batch() -> int:
    result = subprocess.run(
        [
            str(PYTHON),
            str(CLI),
            "--input",
            str(SAMPLES),
            "--output",
            str(OUT_DIR),
            "--algorithm",
            "floyd-steinberg",
            "--palette",
            "bw",
        ],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result.returncode


def assert_outputs() -> int:
    from PIL import Image

    if not SAMPLES.is_dir():
        print(f"Missing {SAMPLES}; run: .venv/bin/python shared/make_samples.py", file=sys.stderr)
        return 1

    expected_files = discover_files(SAMPLES, DEFAULT_PATTERNS, recursive=False)
    expected = len(expected_files)
    if expected < 1:
        print(
            f"No input samples in {SAMPLES}; run: .venv/bin/python shared/make_samples.py",
            file=sys.stderr,
        )
        return 1

    if not OUT_DIR.is_dir():
        print(f"Output directory missing: {OUT_DIR}", file=sys.stderr)
        return 1

    outputs = sorted(OUT_DIR.glob("*.png"))
    if len(outputs) != expected:
        print(
            f"Expected {expected} PNG(s) in {OUT_DIR}, found {len(outputs)}",
            file=sys.stderr,
        )
        return 1

    non_flat = False
    for path in outputs:
        data = path.read_bytes()
        if len(data) <= 100:
            print(f"Output too small: {path} ({len(data)} bytes)", file=sys.stderr)
            return 1
        if not data.startswith(b"\x89PNG"):
            print(f"Not a PNG: {path}", file=sys.stderr)
            return 1
        with Image.open(path) as img:
            img.verify()
        with Image.open(path) as img:
            arr = np.asarray(img.convert("RGB"))
            vals = arr.reshape(-1)
            if max(vals) - min(vals) > 10:
                non_flat = True

    if not non_flat:
        print("No output had sufficient tonal range (flat image?)", file=sys.stderr)
        return 1

    print(f"BATCH_OK {len(outputs)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test for dither_batch CLI.")
    parser.add_argument(
        "--no-run",
        action="store_true",
        help="Skip subprocess CLI run; only assert existing outputs.",
    )
    args = parser.parse_args()

    if not args.no_run:
        code = run_batch()
        if code != 0:
            print(f"CLI exited with {code}", file=sys.stderr)
            return 1

    return assert_outputs()


if __name__ == "__main__":
    sys.exit(main())
