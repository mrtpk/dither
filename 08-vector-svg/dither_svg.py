#!/usr/bin/env python3
"""Convert one image to a real vector SVG dither (rects or halftone dots)."""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shared import pydither as pd  # noqa: E402

try:
    import svgwrite
except ImportError:  # pragma: no cover
    svgwrite = None  # type: ignore[assignment]

ALGORITHMS = (
    "bayer",
    "threshold",
    "floyd-steinberg",
    "atkinson",
    "jarvis-judice-ninke",
)
TWO_COLOR_PALETTES = frozenset({"bw", "ink_on_white"})
PAPER_CHEB = 12
PAPER_SE = 800
INK_MATCH_TOL = 2
MIN_COVERAGE = 0.01

HEX_SLUGS = {
    "#000000": "black",
    "#ffffff": "white",
    "#111111": "dark",
    "#0a0a0a": "black",
    "#d6ff00": "neon",
    "#1e1e78": "riso_blue",
    "#ff4682": "riso_pink",
    "#140c00": "amber_dark",
    "#ffb000": "amber",
    "#0f380f": "gb0",
    "#306230": "gb1",
    "#8bac0f": "gb2",
    "#9bbc0f": "gb3",
}


class DestIsFileError(OSError):
    """Destination directory path exists as a file."""


def rnd(v: float | int) -> float:
    return round(float(v), 3)


def parse_hex(s: str) -> tuple[int, int, int]:
    raw = (s or "").strip()
    if not raw.startswith("#"):
        raise ValueError(f"invalid hex color (expected #RGB or #RRGGBB): {s!r}")
    h = raw[1:]
    digits = set("0123456789abcdefABCDEF")
    if len(h) == 3 and all(c in digits for c in h):
        return (int(h[0] * 2, 16), int(h[1] * 2, 16), int(h[2] * 2, 16))
    if len(h) == 6 and all(c in digits for c in h):
        return (int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16))
    raise ValueError(f"invalid hex color (expected #RGB or #RRGGBB): {s!r}")


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    r, g, b = (int(c) for c in rgb)
    return f"#{r:02x}{g:02x}{b:02x}"


def near(
    pixel_or_arr: tuple[int, ...] | np.ndarray,
    rgb: tuple[int, int, int],
    tol: int | None = None,
) -> bool | np.ndarray:
    """Paper test (tol=None): Chebyshev ≤ 12 or squared Euclidean < 800.

    With *tol*, Chebyshev ≤ *tol* (used for post-dither ink matching).
    """
    target = np.asarray(rgb, dtype=np.int16)
    arr = np.asarray(pixel_or_arr)
    if arr.ndim >= 2:
        delta = np.abs(arr.astype(np.int16) - target)
        cheb = delta.max(axis=-1)
        if tol is not None:
            return cheb <= tol
        se = (delta.astype(np.int32) ** 2).sum(axis=-1)
        return (cheb <= PAPER_CHEB) | (se < PAPER_SE)
    delta = np.abs(arr.astype(np.int16) - target)
    cheb = int(delta.max())
    if tol is not None:
        return cheb <= tol
    se = int((delta.astype(np.int32) ** 2).sum())
    return cheb <= PAPER_CHEB or se < PAPER_SE


def resolve_inks(
    palette: np.ndarray,
    bg: tuple[int, int, int],
    ink_override: tuple[int, int, int] | None,
) -> list[tuple[str, tuple[int, int, int], str]]:
    if ink_override is not None:
        hx = rgb_to_hex(ink_override)
        return [("ink", ink_override, hx)]
    found: list[tuple[str, tuple[int, int, int], str]] = []
    ink_index = 0
    for row in palette:
        rgb = (int(row[0]), int(row[1]), int(row[2]))
        if near(rgb, bg):
            continue
        hx = rgb_to_hex(rgb)
        slug = HEX_SLUGS.get(hx, f"ink{ink_index}")
        found.append((slug, rgb, hx))
        ink_index += 1
    return found


def downscale_to_cells(arr: np.ndarray, cells: int) -> tuple[np.ndarray, int, int]:
    h, w = arr.shape[:2]
    cols = cells
    rows = max(1, round(h * cols / w))
    small = Image.fromarray(arr).resize((cols, rows), Image.LANCZOS)
    grid = np.asarray(small, dtype=np.uint8)
    return grid, cols, rows


def merge_row_runs(mask: np.ndarray) -> list[tuple[int, int, int]]:
    """Collapse consecutive True cells in each row into (x, y, width)."""
    rows, cols = mask.shape
    runs: list[tuple[int, int, int]] = []
    for y in range(rows):
        x = 0
        row = mask[y]
        while x < cols:
            if not row[x]:
                x += 1
                continue
            x0 = x
            while x < cols and row[x]:
                x += 1
            runs.append((x0, y, x - x0))
    return runs


def sample_coverage(cov: np.ndarray, sx: float, sy: float) -> float:
    """Mean coverage of pixels whose centers fall in a 1×1 window at (sx, sy)."""
    rows, cols = cov.shape
    i0 = math.ceil(sx - 1.0)
    i1 = math.floor(sx)
    j0 = math.ceil(sy - 1.0)
    j1 = math.floor(sy)
    i0c = max(0, i0)
    i1c = min(cols - 1, i1)
    j0c = max(0, j0)
    j1c = min(rows - 1, j1)
    if i0c > i1c or j0c > j1c:
        i = int(min(max(round(sx - 0.5), 0), cols - 1))
        j = int(min(max(round(sy - 0.5), 0), rows - 1))
        return float(cov[j, i])
    return float(cov[j0c : j1c + 1, i0c : i1c + 1].mean())


def emit_rects(dwg, group, runs: list[tuple[float, float, float]]) -> None:
    for x, y, w in runs:
        group.add(dwg.rect(insert=(rnd(x), rnd(y)), size=(rnd(w), 1)))


def emit_circles(dwg, group, circles: list[tuple[float, float, float]]) -> None:
    for cx, cy, r in circles:
        group.add(dwg.circle(center=(rnd(cx), rnd(cy)), r=rnd(r)))


def new_drawing(path: Path, cols: int, rows: int, bg_hex: str | None):
    dwg = svgwrite.Drawing(
        str(path),
        size=(f"{cols}mm", f"{rows}mm"),
        viewBox=f"0 0 {cols} {rows}",
        profile="full",
    )
    dwg.attribs["preserveAspectRatio"] = "xMidYMid meet"
    if bg_hex is not None:
        dwg.add(dwg.rect(insert=(0, 0), size=(cols, rows), fill=bg_hex))
    return dwg


def write_svg(
    path: Path,
    cols: int,
    rows: int,
    bg: str | None,
    layers: list[tuple[str, str, list[tuple]]],
    rotate: tuple[float, float, float] | None = None,
) -> tuple[int, int]:
    dwg = new_drawing(path, cols, rows, bg_hex=bg)
    n_rects = 0
    n_circles = 0
    for slug, fill, geoms in layers:
        attrs: dict = {"id": f"ink-{slug}", "fill": fill}
        if rotate is not None:
            angle, ox, oy = rotate
            attrs["transform"] = f"rotate({rnd(angle)} {rnd(ox)} {rnd(oy)})"
        group = dwg.g(**attrs)
        rects: list[tuple[float, float, float]] = []
        circles: list[tuple[float, float, float]] = []
        for geom in geoms:
            kind = geom[0]
            if kind == "rect":
                _, x, y, w, _h = geom
                rects.append((x, y, w))
            else:
                _, cx, cy, r = geom
                circles.append((cx, cy, r))
        emit_rects(dwg, group, rects)
        emit_circles(dwg, group, circles)
        n_rects += len(rects)
        n_circles += len(circles)
        dwg.add(group)
    path.parent.mkdir(parents=True, exist_ok=True)
    dwg.save()
    return n_rects, n_circles


def run_rect(
    grid: np.ndarray,
    algorithm: str,
    palette: np.ndarray,
    contrast: float,
    bayer_n: int,
    inks: list[tuple[str, tuple[int, int, int], str]],
    bg_rgb: tuple[int, int, int],
    two_color: bool,
) -> list[tuple[str, str, list[tuple]]]:
    dithered = pd.dither(
        grid,
        algorithm=algorithm,
        palette=palette,
        contrast=contrast,
        brightness=0.0,
        grayscale=True,
        bayer_n=bayer_n,
        strength=1.0,
    )
    layers: list[tuple[str, str, list[tuple]]] = []
    if two_color:
        if not inks:
            return layers
        slug, _rgb, hx = inks[0]
        mask = np.logical_not(near(dithered, bg_rgb))
        runs = merge_row_runs(mask)
        geoms = [("rect", float(x), float(y), float(w), 1.0) for x, y, w in runs]
        layers.append((slug, hx, geoms))
        return layers
    for slug, rgb, hx in inks:
        mask = near(dithered, rgb, tol=INK_MATCH_TOL)
        runs = merge_row_runs(mask)
        geoms = [("rect", float(x), float(y), float(w), 1.0) for x, y, w in runs]
        layers.append((slug, hx, geoms))
    return layers


def run_dots(
    grid: np.ndarray,
    contrast: float,
    angle: float,
    inks: list[tuple[str, tuple[int, int, int], str]],
) -> tuple[list[tuple[str, str, list[tuple]]], tuple[float, float, float] | None]:
    work = pd.apply_contrast(grid, contrast=contrast, brightness=0.0)
    gray = pd.to_gray(work)
    coverage = 1.0 - (gray / 255.0)
    if not inks:
        return [], None
    slug, _rgb, hx = inks[0]
    rows, cols = grid.shape[:2]
    max_r = (1.0 * math.sqrt(2.0)) / 2.0
    circles: list[tuple] = []
    rotate: tuple[float, float, float] | None = None

    if angle % 180 == 0:
        for j in range(rows):
            for i in range(cols):
                c = float(coverage[j, i])
                if c < MIN_COVERAGE:
                    continue
                circles.append(("circle", i + 0.5, j + 0.5, math.sqrt(c) * max_r))
    else:
        theta = angle * math.pi / 180.0
        ox, oy = cols / 2.0, rows / 2.0
        half_diag = math.hypot(cols, rows) / 2.0
        n = math.ceil(half_diag + 1)
        cos_t, sin_t = math.cos(theta), math.sin(theta)
        rotate = (angle, ox, oy)
        for j in range(-n, n + 1):
            for i in range(-n, n + 1):
                lx, ly = i + 0.5, j + 0.5
                sx = ox + lx * cos_t - ly * sin_t
                sy = oy + lx * sin_t + ly * cos_t
                if sx < -1.0 or sx >= cols + 1.0 or sy < -1.0 or sy >= rows + 1.0:
                    continue
                c = sample_coverage(coverage, sx, sy)
                if c < MIN_COVERAGE:
                    continue
                circles.append(("circle", ox + lx, oy + ly, math.sqrt(c) * max_r))

    return [(slug, hx, circles)], rotate


def as_dir(p: Path) -> bool:
    return (p.exists() and p.is_dir()) or p.suffix.lower() != ".svg"


def resolve_output_paths(
    out: Path, input_stem: str, separate: bool, slugs: list[str]
) -> list[Path]:
    if separate:
        if as_dir(out):
            dest_dir, prefix = out, input_stem
        else:
            dest_dir, prefix = out.parent, out.stem
        if dest_dir.exists() and dest_dir.is_file():
            raise DestIsFileError(str(dest_dir))
        dest_dir.mkdir(parents=True, exist_ok=True)
        return [dest_dir / f"{prefix}_{slug}.svg" for slug in slugs]

    if as_dir(out):
        dest_dir = out
        if dest_dir.exists() and dest_dir.is_file():
            raise DestIsFileError(str(dest_dir))
        dest_dir.mkdir(parents=True, exist_ok=True)
        return [dest_dir / f"{input_stem}.svg"]

    dest = out
    dest.parent.mkdir(parents=True, exist_ok=True)
    return [dest]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Convert a single image to a real vector SVG dither "
            "(rect runs or halftone dots). One file per invocation."
        )
    )
    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Source image file (must exist; not a directory).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Destination .svg file, or a directory (writes {stem}.svg).",
    )
    parser.add_argument(
        "--style",
        default="rect",
        choices=("rect", "dots"),
        help="Geometry family: rect (dither grid) or dots (halftone).",
    )
    parser.add_argument(
        "--cells",
        type=int,
        default=120,
        help="Logical grid width in cells (not source pixel width). Default 120.",
    )
    parser.add_argument(
        "--algorithm",
        default="bayer",
        help=(
            "Dither kernel for --style rect only: bayer, threshold, "
            "floyd-steinberg, atkinson, jarvis-judice-ninke."
        ),
    )
    parser.add_argument(
        "--palette",
        default="bw",
        help=f"Palette key: {', '.join(pd.PALETTES)}.",
    )
    parser.add_argument(
        "--contrast",
        type=float,
        default=1.0,
        help="Contrast multiplier before dither / coverage.",
    )
    parser.add_argument(
        "--angle",
        type=float,
        default=45.0,
        help="Screen rotation in degrees for --style dots only. 0 = axis-aligned.",
    )
    parser.add_argument(
        "--max-dim",
        type=int,
        default=1024,
        help="Long-edge cap on load (LANCZOS); 0 = no load cap.",
    )
    parser.add_argument(
        "--bg",
        default="#ffffff",
        help="Paper / ground fill as CSS hex (#RRGGBB or #RGB). Composite only.",
    )
    parser.add_argument(
        "--ink",
        default=None,
        help="Force a single ink fill (CSS hex). Unset = palette inks.",
    )
    parser.add_argument(
        "--separate",
        action="store_true",
        help="Write one SVG per ink plate instead of a composite.",
    )
    parser.add_argument(
        "--bayer-n",
        type=int,
        default=4,
        help="Bayer matrix size (power of two >= 2). Only used with --algorithm bayer.",
    )
    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> str | None:
    if not args.input.exists():
        return f"--input does not exist: {args.input}"
    if not args.input.is_file():
        return f"--input is not a file: {args.input}"
    if args.palette not in pd.PALETTES:
        return f"unknown --palette: {args.palette!r} (expected one of {', '.join(pd.PALETTES)})"
    if args.algorithm not in ALGORITHMS:
        return f"unknown --algorithm: {args.algorithm!r} (expected one of {', '.join(ALGORITHMS)})"
    if args.cells < 8 or args.cells > 400:
        return f"--cells must be between 8 and 400 (got {args.cells})"
    if args.bayer_n < 2 or args.bayer_n & (args.bayer_n - 1) != 0:
        return f"--bayer-n must be a power of two >= 2 (got {args.bayer_n})"
    if args.max_dim < 0:
        return f"--max-dim must be >= 0 (got {args.max_dim})"
    if args.style not in ("rect", "dots"):
        return f"unknown --style: {args.style!r}"
    try:
        parse_hex(args.bg)
    except ValueError as exc:
        return str(exc)
    if args.ink is not None:
        try:
            parse_hex(args.ink)
        except ValueError as exc:
            return str(exc)
    return None


def _count_geoms(layers: list[tuple[str, str, list[tuple]]]) -> tuple[int, int]:
    n_rects = n_circles = 0
    for _slug, _hx, geoms in layers:
        for geom in geoms:
            if geom[0] == "rect":
                n_rects += 1
            else:
                n_circles += 1
    return n_rects, n_circles


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    err = validate_args(args)
    if err:
        print(err, file=sys.stderr)
        return 2

    if svgwrite is None:
        print("svgwrite is required (pip install svgwrite)", file=sys.stderr)
        return 1

    max_dim = None if args.max_dim == 0 else args.max_dim
    try:
        arr = pd.load_image(str(args.input), max_dim=max_dim)
    except Exception as exc:  # noqa: BLE001
        print(f"failed to load image: {exc}", file=sys.stderr)
        return 1

    grid, cols, rows = downscale_to_cells(arr, args.cells)
    bg_rgb = parse_hex(args.bg)
    bg_hex = rgb_to_hex(bg_rgb)
    ink_override = parse_hex(args.ink) if args.ink is not None else None
    inks = resolve_inks(pd.PALETTES[args.palette], bg_rgb, ink_override)

    try:
        if args.style == "rect":
            two_color = ink_override is not None or args.palette in TWO_COLOR_PALETTES
            layers = run_rect(
                grid,
                args.algorithm,
                pd.PALETTES[args.palette],
                args.contrast,
                args.bayer_n,
                inks,
                bg_rgb,
                two_color,
            )
            rotate = None
        else:
            layers, rotate = run_dots(grid, args.contrast, args.angle, inks)
    except Exception as exc:  # noqa: BLE001
        print(f"failed to build geometry: {exc}", file=sys.stderr)
        return 1

    n_rects, n_circles = _count_geoms(layers)
    if n_rects + n_circles == 0:
        print(
            "warning: every cell is near paper; writing a paper-only SVG",
            file=sys.stderr,
        )

    stem = Path(args.input).stem
    try:
        if args.separate:
            if not layers:
                layers = [("empty", "#000000", [])]
            slugs = [s for s, _hx, _geoms in layers]
            paths = resolve_output_paths(args.output, stem, True, slugs)
            written = []
            for dest, layer in zip(paths, layers):
                nr, nc = write_svg(dest, cols, rows, None, [layer], rotate=rotate)
                written.append((dest, nr, nc))
        else:
            dest = resolve_output_paths(args.output, stem, False, [])[0]
            nr, nc = write_svg(dest, cols, rows, bg_hex, layers, rotate=rotate)
            written = [(dest, nr, nc)]
    except DestIsFileError as exc:
        print(f"destination directory exists as a file: {exc}", file=sys.stderr)
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"failed to write SVG: {exc}", file=sys.stderr)
        return 1

    for dest, nr, nc in written:
        print(f"{dest}  rects={nr} circles={nc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
