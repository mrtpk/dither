#!/usr/bin/env python3
"""Coordinator smoke test for 11-depth-aware.

Fast + offline by default (synthetic depth). Optionally attempts the model path
and prints MODEL_SKIP (never fails) when torch/transformers/model is unavailable.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shared import pydither as pd  # noqa: E402

PYTHON = ROOT / ".venv" / "bin" / "python"
CLI = ROOT / "11-depth-aware" / "depth_dither.py"
OUT_DIR = ROOT / "11-depth-aware" / "out"
SAMPLE = ROOT / "data" / "samples" / "01a.png"
OUT = OUT_DIR / "_test_01a.png"
DEPTH = OUT_DIR / "_test_01a_depth.png"
SCRATCH = OUT_DIR / "_test_01a_single.png"
OUT_MODEL = OUT_DIR / "_test_01a_model.png"
TEST_PNG = ROOT / "11-depth-aware" / "_test.png"
PALETTE = "bw"
MAX_DIM = 96


def _run(extra: list[str], timeout: float | None = None) -> subprocess.CompletedProcess:
    cmd = [str(PYTHON), str(CLI), "--input", str(SAMPLE), *extra]
    return subprocess.run(
        cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=timeout
    )


def _valid_png(path: Path) -> bool:
    if not path.exists() or path.stat().st_size <= 100:
        return False
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG"):
        return False
    with Image.open(path) as img:
        img.verify()
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test for depth_dither CLI.")
    parser.add_argument("--no-run", action="store_true", help="Skip CLI runs; assert only.")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    if not SAMPLE.exists():
        print(f"Missing sample {SAMPLE}", file=sys.stderr)
        return 1

    # --- Step 1: synthetic run (required) ---
    if not args.no_run:
        r = _run(
            [
                "--output", str(OUT),
                "--depth-source", "synthetic",
                "--palette", PALETTE,
                "--levels", "3",
                "--min-scale", "1",
                "--max-scale", "8",
                "--algorithm", "bayer",
                "--max-dim", str(MAX_DIM),
                "--save-depth",
            ]
        )
        if r.stdout:
            print(r.stdout, end="")
        if r.stderr:
            print(r.stderr, end="", file=sys.stderr)
        if r.returncode != 0:
            print(f"synthetic run exited {r.returncode}", file=sys.stderr)
            return 1

    # --- Step 2: outputs exist & valid ---
    if not _valid_png(OUT):
        print(f"Invalid/missing output PNG: {OUT}", file=sys.stderr)
        return 1
    if not _valid_png(DEPTH):
        print(f"Invalid/missing depth PNG: {DEPTH}", file=sys.stderr)
        return 1

    arr = np.asarray(Image.open(OUT).convert("RGB"))
    if arr.ndim != 3 or arr.shape[2] != 3:
        print(f"Output not HxWx3 RGB: {arr.shape}", file=sys.stderr)
        return 1

    # --- Step 3: palette subset (dither output only) ---
    uniq = np.unique(arr.reshape(-1, 3), axis=0)
    pal = pd.PALETTES[PALETTE]
    pal_set = {tuple(int(c) for c in row) for row in pal}
    for row in uniq:
        if tuple(int(c) for c in row) not in pal_set:
            print(f"Output color {tuple(row)} not in palette {PALETTE}", file=sys.stderr)
            return 1

    # --- Step 4: non-flat ---
    if int(arr.max()) - int(arr.min()) <= 10:
        print("Output is flat (no dithering happened)", file=sys.stderr)
        return 1

    # --- Step 5: depth modulated the output (hard assert) ---
    if not args.no_run:
        r2 = _run(
            [
                "--output", str(SCRATCH),
                "--depth-source", "synthetic",
                "--palette", PALETTE,
                "--levels", "1",
                "--min-scale", "1",
                "--max-scale", "1",
                "--algorithm", "bayer",
                "--max-dim", str(MAX_DIM),
            ]
        )
        if r2.returncode != 0:
            print(f"single-scale run exited {r2.returncode}", file=sys.stderr)
            if r2.stderr:
                print(r2.stderr, end="", file=sys.stderr)
            return 1
    single = np.asarray(Image.open(SCRATCH).convert("RGB"))
    if single.shape != arr.shape:
        print(f"shape mismatch {single.shape} vs {arr.shape}", file=sys.stderr)
        return 1
    if np.array_equal(single, arr):
        print("Depth-aware output identical to single-scale (no modulation!)", file=sys.stderr)
        return 1

    # Save a static visual proof copy.
    Image.fromarray(arr).save(TEST_PNG)

    # --- Step 6: optional model attempt (never fails) ---
    if not args.no_run:
        try:
            rm = _run(
                [
                    "--output", str(OUT_MODEL),
                    "--depth-source", "model",
                    "--model", "Intel/dpt-hybrid-midas",
                    "--levels", "3",
                    "--algorithm", "bayer",
                    "--max-dim", str(MAX_DIM),
                ],
                timeout=300,
            )
            if rm.returncode == 0 and _valid_png(OUT_MODEL):
                print("MODEL_OK")
            else:
                print("MODEL_SKIP (offline / download failed / model error)")
        except subprocess.TimeoutExpired:
            print("MODEL_SKIP (timeout)")
        except Exception as exc:  # noqa: BLE001
            print(f"MODEL_SKIP ({exc})")

    # --- cleanup scratch ---
    for p in (SCRATCH,):
        try:
            p.unlink()
        except FileNotFoundError:
            pass

    print("DEPTH_OK")
    print("SMOKE_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
