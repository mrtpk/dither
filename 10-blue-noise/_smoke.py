#!/usr/bin/env python3
"""Coordinator smoke test for 10-blue-noise.

Generates a small (N=32) blue-noise matrix, validates it is a proper
permutation ranking spanning (0, 1), applies it to a sample and checks the
output colors are a subset of the palette, and runs a soft blue-noise spectral
check. Prints SMOKE_OK on success.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shared import pydither as pd  # noqa: E402

PYTHON = ROOT / ".venv" / "bin" / "python"
CLI = ROOT / "10-blue-noise" / "blue_noise.py"
SAMPLES = ROOT / "data" / "samples"

BASE = ROOT / "10-blue-noise" / "_test_bn"
NPY = BASE.with_suffix(".npy")
PNG = BASE.with_suffix(".png")
APPLY_OUT = ROOT / "10-blue-noise" / "_test_apply.png"
PROOF = ROOT / "10-blue-noise" / "_test.png"
SAMPLE = SAMPLES / "01a.png"

SCRATCH = [NPY, PNG, APPLY_OUT]


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result


def _cleanup() -> None:
    for p in SCRATCH:
        try:
            p.unlink()
        except FileNotFoundError:
            pass


def check_generate() -> int:
    result = _run(
        [
            str(PYTHON), str(CLI), "generate",
            "--size", "32", "--sigma", "1.5", "--seed", "0",
            "--out", str(BASE),
        ]
    )
    if result.returncode != 0:
        print(f"generate exited with {result.returncode}", file=sys.stderr)
        return 1

    if not NPY.is_file() or NPY.stat().st_size < 100:
        print(f"missing/too-small .npy: {NPY}", file=sys.stderr)
        return 1
    if not PNG.is_file() or PNG.stat().st_size < 100:
        print(f"missing/too-small .png: {PNG}", file=sys.stderr)
        return 1
    return 0


def check_ranking() -> int:
    m = np.load(NPY)
    if m.shape != (32, 32):
        print(f"bad matrix shape {m.shape}", file=sys.stderr)
        return 1
    if not np.issubdtype(m.dtype, np.floating):
        print(f"matrix not float dtype: {m.dtype}", file=sys.stderr)
        return 1

    if not (0.0 < m.min()) or not (m.max() < 1.0):
        print(f"matrix out of open (0,1): min={m.min()} max={m.max()}", file=sys.stderr)
        return 1
    if m.min() > 0.05 or m.max() < 0.95:
        print(f"matrix does not span (0,1): min={m.min()} max={m.max()}", file=sys.stderr)
        return 1

    n = m.shape[0]
    total = n * n
    ranks = np.round(m * total - 0.5).astype(int)
    if sorted(ranks.ravel().tolist()) != list(range(total)):
        print("ranks are not a valid permutation of [0, N^2)", file=sys.stderr)
        return 1

    print(f"RANK_OK N={n} unique={total} min={m.min():.4f} max={m.max():.4f}")
    return 0


def check_apply() -> int:
    result = _run(
        [
            str(PYTHON), str(CLI), "apply",
            "--input", str(SAMPLE),
            "--matrix", str(NPY),
            "--palette", "bw",
            "--output", str(APPLY_OUT),
        ]
    )
    if result.returncode != 0:
        print(f"apply exited with {result.returncode}", file=sys.stderr)
        return 1
    if not APPLY_OUT.is_file() or APPLY_OUT.stat().st_size < 100:
        print(f"missing/too-small apply output: {APPLY_OUT}", file=sys.stderr)
        return 1

    img = np.asarray(Image.open(APPLY_OUT).convert("RGB"), dtype=np.uint8)
    if img.ndim != 3 or img.shape[2] != 3:
        print(f"apply output not HxWx3: {img.shape}", file=sys.stderr)
        return 1

    palette = pd.PALETTES["bw"]
    uniq = np.unique(img.reshape(-1, 3), axis=0)
    pal_set = {tuple(int(v) for v in row) for row in palette}
    for row in uniq:
        if tuple(int(v) for v in row) not in pal_set:
            print(f"color {tuple(row)} not in bw palette", file=sys.stderr)
            return 1

    # Save a static visual proof (the dithered sample).
    Image.fromarray(img).save(PROOF)
    print(f"APPLY_CHECK_OK colors={len(uniq)}")
    return 0


def check_spectrum() -> None:
    """Soft blue-noise spectral check (warn, never fail)."""
    try:
        m = np.load(NPY)
        f = np.fft.fftshift(np.abs(np.fft.fft2(m - m.mean())))
        n = m.shape[0]
        cy, cx = n // 2, n // 2
        yy, xx = np.meshgrid(np.arange(n) - cy, np.arange(n) - cx, indexing="ij")
        r = np.sqrt(xx**2 + yy**2)
        rmax = r.max()
        low = (r > 0) & (r <= 0.25 * rmax)
        high = r >= 0.55 * rmax
        low_mean = float(f[low].mean())
        high_mean = float(f[high].mean())
        if low_mean < high_mean:
            print(f"SPECTRUM_OK low={low_mean:.3f} < high={high_mean:.3f}")
        else:
            print(
                f"SPECTRUM_WARN low={low_mean:.3f} >= high={high_mean:.3f} "
                "(N=32 variance; not fatal)",
                file=sys.stderr,
            )
    except Exception as exc:  # noqa: BLE001
        print(f"SPECTRUM_SKIP ({exc})", file=sys.stderr)


def main() -> int:
    if not SAMPLE.is_file():
        print(
            "Missing samples; run: .venv/bin/python shared/make_samples.py",
            file=sys.stderr,
        )
        return 1

    for step in (check_generate, check_ranking, check_apply):
        code = step()
        if code != 0:
            _cleanup()
            return code

    check_spectrum()
    _cleanup()
    print("SMOKE_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
