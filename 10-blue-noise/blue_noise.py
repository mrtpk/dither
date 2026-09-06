#!/usr/bin/env python3
"""Blue-noise (void-and-cluster) threshold matrix: generate + apply.

Two subcommands:
  generate  build a tileable blue-noise threshold matrix (Ulichney 1993)
            using numpy FFT toroidal Gaussian energy. Saves .npy + .png.
  apply     use a blue-noise matrix as an ordered-dither threshold texture
            (drop-in Bayer replacement) and snap to a palette.

Pure numpy (no scipy). Run with .venv/bin/python from the repo root.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shared import pydither as pd  # noqa: E402

DEFAULT_DIR = ROOT / "10-blue-noise" / "matrices"


# --------------------------------------------------------------------------- #
# 1. Gaussian energy filter (FFT, toroidal / circular convolution)
# --------------------------------------------------------------------------- #
def build_gaussian_fft(n: int, sigma: float) -> np.ndarray:
    """Precompute rfft2 of a normalized Gaussian with origin at (0, 0).

    The kernel is *not* fftshifted: origin-at-0 is the correct form for
    circular (toroidal) convolution via FFT. A centered kernel would shift
    the energy field by N/2 in each axis. Normalizing to sum=1 makes
    energy(1s) == 1 - energy(0s) exactly (required for the single Phase-2 loop).
    """
    ax = np.fft.fftfreq(n) * n  # 0, 1, ..., -2, -1  (signed toroidal distances)
    xx, yy = np.meshgrid(ax, ax, indexing="ij")
    g = np.exp(-(xx**2 + yy**2) / (2.0 * sigma**2))
    g /= g.sum()
    return np.fft.rfft2(g)


def filtered_energy(binary: np.ndarray, gfft: np.ndarray) -> np.ndarray:
    """Circular Gaussian convolution of a binary NxN pattern (float NxN)."""
    return np.fft.irfft2(np.fft.rfft2(binary.astype(np.float64)) * gfft, s=binary.shape)


# --------------------------------------------------------------------------- #
# 2. Cluster / void location (argmax / argmin restricted to 1s / 0s)
# --------------------------------------------------------------------------- #
def tightest_cluster(energy: np.ndarray, pattern: np.ndarray) -> int:
    """Flat index of the 1-pixel sitting in the densest neighborhood (max energy)."""
    masked = np.where(pattern == 1, energy, -np.inf)
    return int(np.argmax(masked))


def largest_void(energy: np.ndarray, pattern: np.ndarray) -> int:
    """Flat index of the 0-pixel in the emptiest neighborhood (min energy)."""
    masked = np.where(pattern == 0, energy, np.inf)
    return int(np.argmin(masked))


# --------------------------------------------------------------------------- #
# 3. Void-and-cluster core
# --------------------------------------------------------------------------- #
def make_initial(n: int, initial_ones: int, seed: int) -> np.ndarray:
    """Random binary NxN pattern with exactly `initial_ones` ones (seeded)."""
    rng = np.random.default_rng(seed)
    flat = np.zeros(n * n, dtype=np.uint8)
    idx = rng.choice(n * n, size=initial_ones, replace=False)
    flat[idx] = 1
    return flat.reshape(n, n)


def generate_blue_noise(
    n: int,
    sigma: float = 1.5,
    seed: int = 0,
    density: float = 0.1,
) -> np.ndarray:
    """Return an NxN blue-noise threshold matrix, float64 values in (0, 1)."""
    if n < 2:
        raise ValueError("size must be >= 2")
    if not (0.0 < density < 0.5):
        raise ValueError("density must be in (0, 0.5)")

    total = n * n
    initial_ones = int(round(total * density))
    initial_ones = max(1, min(initial_ones, total - 1))

    gfft = build_gaussian_fft(n, sigma)

    # --- Phase 1: homogenize the initial pattern ---------------------------- #
    pattern = make_initial(n, initial_ones, seed).astype(np.float64)
    max_iter = 4 * total
    for _ in range(max_iter):
        energy = filtered_energy(pattern, gfft)
        c = tightest_cluster(energy, pattern)
        pattern.flat[c] = 0.0
        energy = filtered_energy(pattern, gfft)  # recompute after removal
        v = largest_void(energy, pattern)
        pattern.flat[v] = 1.0
        if v == c:
            break

    prototype = pattern.copy()
    rank = np.full(total, -1, dtype=np.int64)

    # --- Phase 2a: initial ones, ranks initial_ones-1 .. 0 ------------------ #
    work = prototype.copy()
    for r in range(initial_ones - 1, -1, -1):
        energy = filtered_energy(work, gfft)
        c = tightest_cluster(energy, work)
        work.flat[c] = 0.0
        rank[c] = r

    # --- Phase 2b/2c: fill largest void, ranks initial_ones .. total-1 ------ #
    # One continuous loop. Because g is normalized (sum=1), energy(1s) ==
    # 1 - energy(0s), so "largest void" is identically Ulichney's "tightest
    # cluster of 0s in the complement" for the second half. Exact, not approx.
    work = prototype.copy()
    for r in range(initial_ones, total):
        energy = filtered_energy(work, gfft)
        v = largest_void(energy, work)
        work.flat[v] = 1.0
        rank[v] = r

    if (rank < 0).any():
        raise RuntimeError("void-and-cluster left cells unranked (internal error)")

    matrix = (rank.astype(np.float64) + 0.5) / total
    return matrix.reshape(n, n)


# --------------------------------------------------------------------------- #
# 4. Persistence
# --------------------------------------------------------------------------- #
def save_matrix(matrix: np.ndarray, png_path: Path, npy_path: Path) -> None:
    npy_path.parent.mkdir(parents=True, exist_ok=True)
    png_path.parent.mkdir(parents=True, exist_ok=True)
    np.save(npy_path, matrix)
    preview = (matrix * 255.0).round().astype(np.uint8)
    pd.save_image(preview, str(png_path))


def load_matrix(path: Path) -> np.ndarray:
    """Load a matrix from .npy (exact) or .png (8-bit fallback) into (0, 1)."""
    suffix = path.suffix.lower()
    if suffix == ".npy":
        m = np.load(path)
        return m.astype(np.float64)
    # PNG (or any image): read as gray, map 0..255 -> (v + 0.5) / 256 in (0, 1)
    from PIL import Image

    gray = np.asarray(Image.open(path).convert("L"), dtype=np.float64)
    return (gray + 0.5) / 256.0


# --------------------------------------------------------------------------- #
# 5. Default-matrix cache
# --------------------------------------------------------------------------- #
def ensure_default_matrix(size: int = 64, sigma: float = 1.5, seed: int = 0) -> Path:
    npy_path = DEFAULT_DIR / f"blue_noise_{size}.npy"
    png_path = DEFAULT_DIR / f"blue_noise_{size}.png"
    if not npy_path.is_file():
        print(f"GEN default matrix N={size} sigma={sigma} seed={seed}")
        matrix = generate_blue_noise(size, sigma=sigma, seed=seed)
        save_matrix(matrix, png_path, npy_path)
    return npy_path


# --------------------------------------------------------------------------- #
# 6. Apply / dither path (Bayer replacement)
# --------------------------------------------------------------------------- #
def resize_nearest(matrix: np.ndarray, shape: tuple[int, int]) -> np.ndarray:
    """Pure-numpy nearest-neighbor stretch of an NxN matrix to (h, w)."""
    n = matrix.shape[0]
    h, w = shape
    yi = np.clip((np.arange(h) * n) // h, 0, n - 1)
    xi = np.clip((np.arange(w) * n) // w, 0, n - 1)
    return matrix[yi][:, xi]


def blue_noise_dither(
    gray: np.ndarray,
    matrix: np.ndarray,
    palette: np.ndarray,
    strength: float = 1.0,
    tile: bool = True,
) -> np.ndarray:
    """Ordered dither with a blue-noise threshold texture. Returns HxWx3 uint8."""
    h, w = gray.shape
    n = matrix.shape[0]
    if tile:
        tiled = np.tile(matrix, (h // n + 1, w // n + 1))[:h, :w]
    else:
        tiled = resize_nearest(matrix, (h, w))
    shifted = gray + (tiled - 0.5) * 255.0 * strength
    flat = np.stack([shifted, shifted, shifted], axis=-1).reshape(-1, 3)
    out = pd.nearest_palette(flat, palette).reshape(h, w, 3)
    return out.astype(np.uint8)


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="blue_noise.py",
        description="Generate and apply void-and-cluster blue-noise threshold matrices.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    gen = sub.add_parser("generate", help="build a blue-noise threshold matrix")
    gen.add_argument("--size", "-N", type=int, default=64, help="matrix side N")
    gen.add_argument("--sigma", type=float, default=1.5, help="Gaussian energy sigma")
    gen.add_argument("--seed", type=int, default=0, help="RNG seed (reproducible)")
    gen.add_argument("--density", type=float, default=0.1, help="initial ones fraction")
    gen.add_argument(
        "--out",
        type=str,
        default=None,
        help="base output path; writes {out}.png + {out}.npy",
    )

    ap = sub.add_parser("apply", help="apply a matrix as a threshold texture")
    ap.add_argument("--input", type=str, required=True, help="source image")
    ap.add_argument("--matrix", type=str, default=None, help=".npy/.png matrix (auto if omitted)")
    ap.add_argument("--palette", type=str, default="bw", choices=sorted(pd.PALETTES), help="palette")
    ap.add_argument("--contrast", type=float, default=1.0, help="contrast multiplier")
    ap.add_argument("--strength", type=float, default=1.0, help="threshold shift scale")
    ap.add_argument("--max-dim", type=int, default=1024, help="long-edge cap on load")
    ap.add_argument("--compare", action="store_true", help="also emit Bayer-8 side-by-side")
    tile_grp = ap.add_mutually_exclusive_group()
    tile_grp.add_argument("--tile", dest="tile", action="store_true", help="tile matrix (default)")
    tile_grp.add_argument("--no-tile", dest="tile", action="store_false", help="stretch matrix to fit")
    ap.set_defaults(tile=True)
    ap.add_argument("--output", type=str, required=True, help="destination PNG (or dir)")

    return parser


def _resolve_output(output: str, stem: str) -> Path:
    p = Path(output)
    if p.is_dir() or output.endswith(("/", "\\")):
        return p / f"{stem}.png"
    return p


def cmd_generate(args: argparse.Namespace) -> int:
    if args.size < 2:
        print("size must be >= 2", file=sys.stderr)
        return 2
    if not (0.0 < args.density < 0.5):
        print("density must be in (0, 0.5)", file=sys.stderr)
        return 2

    base = args.out if args.out is not None else str(DEFAULT_DIR / f"blue_noise_{args.size}")
    base_path = Path(base)
    if base_path.suffix.lower() in (".npy", ".png"):
        base_path = base_path.with_suffix("")
    npy_path = base_path.with_suffix(".npy")
    png_path = base_path.with_suffix(".png")

    try:
        matrix = generate_blue_noise(args.size, sigma=args.sigma, seed=args.seed, density=args.density)
        save_matrix(matrix, png_path, npy_path)
    except Exception as exc:  # noqa: BLE001
        print(f"failed to generate matrix: {exc}", file=sys.stderr)
        return 1

    print(f"GEN_OK N={args.size} sigma={args.sigma} -> {npy_path} {png_path}")
    return 0


def cmd_apply(args: argparse.Namespace) -> int:
    max_dim = None if args.max_dim == 0 else args.max_dim
    try:
        arr = pd.load_image(str(args.input), max_dim=max_dim)
    except Exception as exc:  # noqa: BLE001
        print(f"failed to load image: {exc}", file=sys.stderr)
        return 1

    try:
        matrix_path = Path(args.matrix) if args.matrix else ensure_default_matrix()
        matrix = load_matrix(Path(matrix_path))
    except Exception as exc:  # noqa: BLE001
        print(f"failed to load matrix: {exc}", file=sys.stderr)
        return 1

    if matrix.ndim != 2 or matrix.shape[0] != matrix.shape[1]:
        print("matrix must be a square 2D array", file=sys.stderr)
        return 1

    palette = pd.PALETTES[args.palette]
    work = pd.apply_contrast(arr, args.contrast) if args.contrast != 1.0 else arr.astype(np.float32)
    gray = pd.to_gray(work)

    try:
        result = blue_noise_dither(gray, matrix, palette, strength=args.strength, tile=args.tile)
        compare_img = None
        if args.compare:
            bayer = pd.ordered_dither(gray, palette, n=8, strength=args.strength)
            compare_img = np.hstack([result, bayer])
    except Exception as exc:  # noqa: BLE001
        print(f"failed to dither: {exc}", file=sys.stderr)
        return 1

    stem = Path(args.input).stem
    dest = _resolve_output(args.output, stem)
    try:
        dest.parent.mkdir(parents=True, exist_ok=True)
        pd.save_image(result, str(dest))
        if compare_img is not None:
            cmp_dest = dest.with_name(f"{dest.stem}_compare{dest.suffix}")
            pd.save_image(compare_img, str(cmp_dest))
    except Exception as exc:  # noqa: BLE001
        print(f"failed to write output: {exc}", file=sys.stderr)
        return 1

    print(f"APPLY_OK {dest}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.command == "generate":
        return cmd_generate(args)
    if args.command == "apply":
        return cmd_apply(args)
    parser.print_help(sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
