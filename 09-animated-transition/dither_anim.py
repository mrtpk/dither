#!/usr/bin/env python3
"""Bayer-mask dither dissolve / materialize animation CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shared import pydither as pd  # noqa: E402


def tile_bayer(h: int, w: int, n: int) -> np.ndarray:
    """Tile an n×n Bayer matrix to HxW. Stable across frames."""
    mat = pd.bayer_matrix(n)
    return np.tile(mat, (h // n + 1, w // n + 1))[:h, :w]


def _resize_rgb(arr: np.ndarray, width: int, height: int, resample: int) -> np.ndarray:
    return np.asarray(Image.fromarray(arr).resize((width, height), resample), dtype=np.uint8)


def _cells_downsample(arr: np.ndarray, cells: int) -> np.ndarray:
    h, w = arr.shape[:2]
    long = max(h, w)
    if long == cells:
        return arr
    if h >= w:
        new_h = cells
        new_w = max(1, round(w * cells / long))
    else:
        new_w = cells
        new_h = max(1, round(h * cells / long))
    return _resize_rgb(arr, new_w, new_h, Image.NEAREST)


def fit_images(
    a: np.ndarray, b_or_none: np.ndarray | None, cells: int | None
) -> tuple[np.ndarray, np.ndarray | None]:
    """Resize B to A's HxW (LANCZOS), then optional NEAREST cells downsample."""
    b = b_or_none
    if b is not None and b.shape[:2] != a.shape[:2]:
        b = _resize_rgb(b, a.shape[1], a.shape[0], Image.LANCZOS)
    if cells is not None:
        a = _cells_downsample(a, cells)
        if b is not None:
            b = _cells_downsample(b, cells)
    return a, b


def paper_frame(h: int, w: int, pal: np.ndarray) -> np.ndarray:
    """Flat HxWx3 filled with the lightest palette RGB (luminance weights)."""
    weights = np.array([0.299, 0.587, 0.114], dtype=np.float32)
    lum = pal.astype(np.float32) @ weights
    color = pal[int(np.argmax(lum))]
    return np.full((h, w, 3), color, dtype=np.uint8)


def snap(frame: np.ndarray, pal: np.ndarray) -> np.ndarray:
    h, w = frame.shape[:2]
    flat = frame.reshape(-1, 3)
    return pd.nearest_palette(flat, pal).reshape(h, w, 3)


def compose(a: np.ndarray, b: np.ndarray, t_field: np.ndarray, t: float) -> np.ndarray:
    """Show B where T < t, else A."""
    mask = t_field < t
    return np.where(mask[..., None], b, a)


def pad_even(frames: list[np.ndarray]) -> list[np.ndarray]:
    """Repeat last row/column so H and W are even (video only)."""
    padded: list[np.ndarray] = []
    for frame in frames:
        out = frame
        if out.shape[0] % 2 == 1:
            out = np.vstack([out, out[-1:]])
        if out.shape[1] % 2 == 1:
            out = np.hstack([out, out[:, -1:]])
        padded.append(out)
    return padded


def resolve_mode(args: argparse.Namespace) -> str:
    if args.mode in (None, "auto"):
        return "dissolve" if args.b is not None else "materialize"
    return args.mode


def build_frames(args: argparse.Namespace) -> list[np.ndarray]:
    max_dim = None if args.max_dim == 0 else args.max_dim
    a = pd.load_image(str(args.a), max_dim=max_dim)
    mode = resolve_mode(args)
    b: np.ndarray | None = None
    if mode == "dissolve":
        b = pd.load_image(str(args.b), max_dim=max_dim)

    a, b = fit_images(a, b, args.cells)
    pal = pd.PALETTES[args.palette]
    n = args.bayer_n
    contrast = args.contrast
    h, w = a.shape[:2]
    t_field = tile_bayer(h, w, n)
    frame_count = args.frames

    if mode == "materialize":
        src_a = paper_frame(h, w, pal)
        src_b = pd.dither(
            a,
            algorithm="bayer",
            palette=pal,
            contrast=contrast,
            grayscale=True,
            bayer_n=n,
        )
    elif args.no_pre_dither:
        src_a = np.clip(np.rint(pd.apply_contrast(a, contrast)), 0, 255).astype(np.uint8)
        assert b is not None
        src_b = np.clip(np.rint(pd.apply_contrast(b, contrast)), 0, 255).astype(np.uint8)
    else:
        src_a = pd.dither(
            a,
            algorithm="bayer",
            palette=pal,
            contrast=contrast,
            grayscale=True,
            bayer_n=n,
        )
        assert b is not None
        src_b = pd.dither(
            b,
            algorithm="bayer",
            palette=pal,
            contrast=contrast,
            grayscale=True,
            bayer_n=n,
        )

    frames: list[np.ndarray] = []
    for i in range(frame_count):
        t = i / (frame_count - 1)
        frame = compose(src_a, src_b, t_field, t)
        frame = snap(np.asarray(frame, dtype=np.uint8), pal)
        frames.append(frame.astype(np.uint8))
    return frames


def resolve_format(output: Path, fmt: str | None) -> tuple[Path, str]:
    if fmt:
        kind = fmt
        path = output if output.suffix.lower() == f".{kind}" else output.with_suffix(f".{kind}")
        return path, kind

    suffix = output.suffix.lower()
    if suffix == ".gif":
        return output, "gif"
    if suffix == ".mp4":
        return output, "mp4"
    if suffix == ".webm":
        return output, "webm"
    if suffix == "":
        return output.with_suffix(".gif"), "gif"
    return output, "gif"


def write_gif(path: Path, frames: list[np.ndarray], fps: float) -> None:
    imageio.mimwrite(
        path,
        frames,
        format="GIF",
        fps=fps,
        duration=1.0 / fps,
        loop=0,
    )


def _write_video_kind(path: Path, frames: list[np.ndarray], fps: float, kind: str) -> None:
    video_frames = pad_even(frames)
    codec = "libx264" if kind == "mp4" else "libvpx-vp9"
    kwargs = {
        "fps": fps,
        "codec": codec,
        "quality": 7,
        "macro_block_size": 1,
    }
    try:
        imageio.mimwrite(path, video_frames, pixelformat="yuv420p", **kwargs)
    except (TypeError, ValueError):
        imageio.mimwrite(
            path,
            video_frames,
            output_params=["-pix_fmt", "yuv420p"],
            **kwargs,
        )


def write_video(path: Path, frames: list[np.ndarray], fps: float, kind: str) -> Path:
    """Write video; WebM → MP4 → GIF fallback. Returns the actual path written."""
    if kind == "webm":
        sequence = ["webm", "mp4", "gif"]
    elif kind == "mp4":
        sequence = ["mp4", "gif"]
    else:
        sequence = ["gif"]

    last_error: Exception | None = None
    for i, candidate in enumerate(sequence):
        dest = path.with_suffix(f".{candidate}")
        try:
            if candidate == "gif":
                write_gif(dest, frames, fps)
            else:
                _write_video_kind(dest, frames, fps, candidate)
            return dest
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            remaining = sequence[i + 1 :]
            if not remaining:
                break
            nxt = remaining[0]
            if candidate == "webm" and nxt == "mp4":
                print("WebM/VP9 unavailable, falling back to MP4", file=sys.stderr)
            else:
                print("… falling back to GIF", file=sys.stderr)

    raise RuntimeError(f"encode failed after all fallbacks: {last_error}")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Build an animated Bayer-mask dither transition (dissolve A→B or "
            "materialize paper→picture) and write GIF / MP4 / WebM."
        )
    )
    parser.add_argument(
        "--a",
        type=Path,
        required=True,
        help="Image A (dissolve from / materialize source). Must exist.",
    )
    parser.add_argument(
        "--b",
        type=Path,
        default=None,
        help="Image B (dissolve to). Omit for single-image materialize.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Output file path (parent dirs created). Suffix may pick format.",
    )
    parser.add_argument(
        "--format",
        choices=["gif", "mp4", "webm"],
        default=None,
        help="Override output format (default: infer from --output suffix, else gif).",
    )
    parser.add_argument(
        "--frames",
        type=int,
        default=24,
        help="Number of animation frames N (>= 2). Default 24.",
    )
    parser.add_argument(
        "--fps",
        type=float,
        default=12,
        help="Frame rate. GIF duration = 1/fps seconds. Default 12.",
    )
    parser.add_argument(
        "--bayer-n",
        type=int,
        default=8,
        help=(
            "Bayer order for the wipe mask T and source dither "
            "(power of two >= 2). Distinct wipe steps ≈ n²; "
            "frames > n²+1 repeats some masks. Default 8 (64 ranks)."
        ),
    )
    parser.add_argument(
        "--palette",
        default="bw",
        choices=list(pd.PALETTES.keys()),
        help="Palette for pre-dither and per-frame snap.",
    )
    parser.add_argument(
        "--max-dim",
        type=int,
        default=256,
        help="Long-edge cap on load (LANCZOS). 0 = no cap. Default 256.",
    )
    parser.add_argument(
        "--cells",
        type=int,
        default=None,
        help=(
            "Working-grid long edge after load (NEAREST, >= 8). "
            "Keeps GIF/video small. Size knob — animation is expensive per frame."
        ),
    )
    parser.add_argument(
        "--mode",
        choices=["dissolve", "materialize"],
        default=None,
        help="Wipe mode. Default: dissolve if --b is set, else materialize.",
    )
    parser.add_argument(
        "--contrast",
        type=float,
        default=1.0,
        help="Contrast multiplier passed into dither / apply_contrast.",
    )
    parser.add_argument(
        "--no-pre-dither",
        action="store_true",
        help=(
            "Compose contrast-adjusted raw A/B (still snap each frame). "
            "Ignored for the materialize target (that stays dithered)."
        ),
    )
    return parser.parse_args(argv)


def validate_args(args: argparse.Namespace) -> str | None:
    if not args.a.exists() or not args.a.is_file():
        return f"--a is not a readable file: {args.a}"
    if args.b is not None and (not args.b.exists() or not args.b.is_file()):
        return f"--b is not a readable file: {args.b}"

    if args.mode == "dissolve" and args.b is None:
        return "--mode dissolve requires --b"

    if args.palette not in pd.PALETTES:
        return f"Invalid --palette: {args.palette}"

    if args.bayer_n & (args.bayer_n - 1) != 0 or args.bayer_n < 2:
        return f"--bayer-n must be a power of two >= 2 (got {args.bayer_n})"

    if args.frames < 2:
        return f"--frames must be >= 2 (got {args.frames})"

    if args.fps <= 0:
        return f"--fps must be > 0 (got {args.fps})"

    if args.max_dim < 0:
        return f"--max-dim must be >= 0 (got {args.max_dim})"

    if args.cells is not None and args.cells < 8:
        return f"--cells must be >= 8 if set (got {args.cells})"

    return None


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.mode == "materialize" and args.b is not None:
        print("warning: --b ignored in materialize mode", file=sys.stderr)
        args.b = None

    err = validate_args(args)
    if err:
        print(err, file=sys.stderr)
        return 2

    try:
        frames = build_frames(args)
    except (OSError, ValueError, FileNotFoundError) as exc:
        print(f"Unreadable image path: {exc}", file=sys.stderr)
        return 2

    path, kind = resolve_format(args.output, args.format)
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        if kind == "gif":
            write_gif(path, frames, args.fps)
            actual = path
        else:
            actual = write_video(path, frames, args.fps, kind)
    except Exception as exc:  # noqa: BLE001
        print(f"Encode failed: {exc}", file=sys.stderr)
        return 1

    print(actual)
    return 0


if __name__ == "__main__":
    sys.exit(main())
