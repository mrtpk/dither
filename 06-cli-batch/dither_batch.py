#!/usr/bin/env python3
"""Batch folder-to-folder image dithering CLI."""

from __future__ import annotations

import argparse
import sys
from multiprocessing import Pool
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shared import pydither as pd  # noqa: E402

Result = Literal["ok", "skip", "fail"]


def pixelate_for_dither(arr: np.ndarray, scale: int) -> np.ndarray:
    """Downsample with nearest-neighbor before dither when scale > 1."""
    if scale <= 1:
        return arr
    h, w = arr.shape[:2]
    small_h = max(1, h // scale)
    small_w = max(1, w // scale)
    return np.asarray(Image.fromarray(arr).resize((small_w, small_h), Image.NEAREST))


def upscale_after_dither(arr: np.ndarray, target_h: int, target_w: int) -> np.ndarray:
    """Nearest-neighbor upscale back to the post-load dimensions."""
    if arr.shape[0] == target_h and arr.shape[1] == target_w:
        return arr
    return np.asarray(Image.fromarray(arr).resize((target_w, target_h), Image.NEAREST))


def build_output_path(
    src: Path, input_root: Path, output_root: Path, suffix: str
) -> Path:
    rel = src.relative_to(input_root)
    stem = rel.stem + suffix
    if rel.parent == Path("."):
        return output_root / f"{stem}.png"
    return output_root / rel.parent / f"{stem}.png"


def discover_files(input_dir: Path, patterns: list[str], recursive: bool) -> list[Path]:
    seen: dict[str, Path] = {}
    glob_fn = input_dir.rglob if recursive else input_dir.glob
    for pat in patterns:
        for path in glob_fn(pat):
            if not path.is_file():
                continue
            key = str(path.resolve())
            if key not in seen:
                seen[key] = path
    return sorted(seen.values(), key=lambda p: str(p).replace("\\", "/"))


def process_one(src: Path, dest: Path, opts: dict) -> Result:
    if dest.exists() and not opts["overwrite"]:
        return "skip"

    try:
        max_dim = opts["max_dim"] if opts["max_dim"] > 0 else None
        arr = pd.load_image(str(src), max_dim=max_dim)
        target_h, target_w = arr.shape[:2]
        scale = opts["scale"]
        if scale > 1:
            arr = pixelate_for_dither(arr, scale)

        palette = pd.PALETTES[opts["palette"]]
        out = pd.dither(
            arr,
            algorithm=opts["algorithm"],
            palette=palette,
            contrast=opts["contrast"],
            brightness=opts["brightness"],
            grayscale=True,
            bayer_n=opts["bayer_n"],
            strength=opts["strength"],
        )

        if scale > 1:
            out = upscale_after_dither(out, target_h, target_w)

        dest.parent.mkdir(parents=True, exist_ok=True)
        pd.save_image(out, str(dest))
        return "ok"
    except Exception as exc:  # noqa: BLE001
        print(f"[ERROR] {src}: {exc}", file=sys.stderr)
        return "fail"


def run_batch(args: argparse.Namespace) -> tuple[int, int, int, int]:
    patterns = [p.strip() for p in args.pattern.split(",") if p.strip()]
    files = discover_files(args.input, patterns, args.recursive)
    total = len(files)

    if total == 0:
        print("No input files matched.", file=sys.stderr)
        return 0, 0, 0, total

    pairs = [
        (src, build_output_path(src, args.input, args.output, args.suffix))
        for src in files
    ]

    opts = {
        "algorithm": args.algorithm,
        "palette": args.palette,
        "contrast": args.contrast,
        "brightness": args.brightness,
        "bayer_n": args.bayer_n,
        "strength": args.strength,
        "max_dim": args.max_dim,
        "scale": args.scale,
        "overwrite": args.overwrite,
    }

    processed = skipped = failed = 0
    jobs = min(args.jobs, total) if args.jobs > 1 else 1

    def handle_result(src: Path, dest: Path, result: Result) -> None:
        nonlocal processed, skipped, failed
        if result == "ok":
            processed += 1
            if not args.quiet:
                print(f"[OK] {src} -> {dest}")
        elif result == "skip":
            skipped += 1
            if not args.quiet:
                print(f"[SKIP] {dest} (exists)")
        else:
            failed += 1

    if jobs > 1:
        with Pool(jobs) as pool:
            for result, (src, dest) in zip(
                pool.starmap(process_one, [(s, d, opts) for s, d in pairs]),
                pairs,
                strict=True,
            ):
                handle_result(src, dest, result)
    else:
        for src, dest in pairs:
            handle_result(src, dest, process_one(src, dest, opts))

    return processed, skipped, failed, total


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Batch-dither images from an input folder to an output folder."
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Input directory containing images.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output directory (created if missing).",
    )
    parser.add_argument(
        "--algorithm",
        default="floyd-steinberg",
        choices=[
            "floyd-steinberg",
            "atkinson",
            "jarvis-judice-ninke",
            "bayer",
            "threshold",
        ],
        help="Dithering algorithm.",
    )
    parser.add_argument(
        "--palette",
        default="bw",
        choices=list(pd.PALETTES.keys()),
        help="Named palette from shared.pydither.",
    )
    parser.add_argument(
        "--bayer-n",
        type=int,
        default=4,
        help="Bayer matrix size (power of two >= 2; only affects --algorithm bayer).",
    )
    parser.add_argument(
        "--contrast",
        type=float,
        default=1.0,
        help="Contrast multiplier applied before dithering.",
    )
    parser.add_argument(
        "--brightness",
        type=float,
        default=0.0,
        help="Brightness offset applied before dithering.",
    )
    parser.add_argument(
        "--strength",
        type=float,
        default=1.0,
        help="Bayer threshold strength (only affects ordered Bayer dither).",
    )
    parser.add_argument(
        "--max-dim",
        type=int,
        default=1024,
        help="Long-edge cap on load (LANCZOS); use 0 to disable.",
    )
    parser.add_argument(
        "--scale",
        type=int,
        default=1,
        help="Pixel block size: downsample NxN before dither, upscale back (1 = off).",
    )
    parser.add_argument(
        "--jobs",
        type=int,
        default=1,
        help="Parallel worker count (multiprocessing Pool).",
    )
    parser.add_argument(
        "--recursive",
        action="store_true",
        help="Search subdirectories under --input.",
    )
    parser.add_argument(
        "--pattern",
        default="*.png,*.jpg,*.jpeg,*.webp",
        help="Comma-separated glob patterns for file discovery.",
    )
    parser.add_argument(
        "--suffix",
        default="_dithered",
        help='Output filename suffix before ".png" (use "" for none).',
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing output files.",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress per-file progress lines.",
    )
    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> str | None:
    if not args.input.exists():
        return f"--input does not exist: {args.input}"
    if not args.input.is_dir():
        return f"--input is not a directory: {args.input}"

    if args.palette not in pd.PALETTES:
        return f"Invalid --palette: {args.palette}"

    if args.bayer_n & (args.bayer_n - 1) != 0 or args.bayer_n < 2:
        return f"--bayer-n must be a power of two >= 2 (got {args.bayer_n})"

    if args.max_dim < 0:
        return f"--max-dim must be >= 0 (got {args.max_dim})"

    if args.scale < 1:
        return f"--scale must be >= 1 (got {args.scale})"

    if args.jobs < 1:
        return f"--jobs must be >= 1 (got {args.jobs})"

    if args.strength < 0:
        return f"--strength must be >= 0 (got {args.strength})"

    return None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    err = validate_args(args)
    if err:
        print(err, file=sys.stderr)
        return 2

    args.output.mkdir(parents=True, exist_ok=True)

    processed, skipped, failed, total = run_batch(args)
    print(f"Done: {processed} written, {skipped} skipped, {failed} failed ({total} matched)")

    if total == 0:
        return 1
    if processed == 0:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
