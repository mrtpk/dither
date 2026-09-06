#!/usr/bin/env python3
"""Depth-aware dithering CLI.

Estimates a monocular depth map from a single image (via a ``transformers``
depth-estimation pipeline, or a deterministic offline synthetic fallback) and
uses it to modulate the dither *scale* (dot / block size) so the dither texture
follows 3D form: near regions get finer detail, far regions get coarser blocks
(reverse with ``--invert-depth``).

All dithering reuses the shared engine in ``shared/pydither``.

Exit codes:
  0 success
  1 load/write/model-required failure
  2 bad arguments (argparse)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image

# --- shared engine on sys.path ------------------------------------------------
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shared import pydither as pd  # noqa: E402


# --------------------------------------------------------------------------- #
# 1. Depth acquisition
# --------------------------------------------------------------------------- #
def model_depth(rgb: np.ndarray, model_name: str) -> np.ndarray:
    """Estimate depth with a transformers depth-estimation pipeline.

    Returns a float32 HxW array (same size as ``rgb``) where *larger = nearer*.
    torch/transformers are imported lazily here so the module still works
    without them when using the synthetic / auto-fallback paths.

    Raises on any failure (missing deps, download failure, model error) with a
    short reason string so callers can decide whether to fall back.
    """
    H, W = rgb.shape[:2]
    try:
        from transformers import pipeline  # lazy import
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"transformers/torch unavailable: {exc}") from exc

    try:
        pil = Image.fromarray(rgb)  # HxWx3 uint8 -> PIL
        pipe = pipeline("depth-estimation", model=model_name)  # first run downloads weights
        result = pipe(pil)
        # A single-image call returns a dict; some versions wrap it in a list.
        if isinstance(result, list):
            result = result[0]

        depth = None
        if isinstance(result, dict) and result.get("predicted_depth") is not None:
            t = result["predicted_depth"]
            depth = t.squeeze().detach().cpu().numpy().astype(np.float32)
        elif isinstance(result, dict) and result.get("depth") is not None:
            # fallback: derive from the PIL preview (mode "F" -> float, no clip)
            depth = np.asarray(result["depth"].convert("F"), dtype=np.float32)
        else:
            raise RuntimeError("pipeline returned no usable depth field")

        # Resize to working (H, W). float32 -> PIL mode "F" so resize keeps floats.
        depth = np.asarray(
            Image.fromarray(depth, mode="F").resize((W, H), Image.BILINEAR),
            dtype=np.float32,
        )
        return depth
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"model inference failed: {exc}") from exc


def synthetic_depth(rgb: np.ndarray) -> np.ndarray:
    """Deterministic offline pseudo-depth (larger = nearer).

    Combines cheap cues purely as a function of pixels + geometry:
      - luminance   (structure cue)
      - vertical    (bottom of frame nearer, a common photo prior)
      - radial      (center nearer, corners farther)
    """
    gray = pd.to_gray(rgb).astype(np.float32) / 255.0  # [0,1]
    H, W = gray.shape

    vgrad = np.linspace(0.0, 1.0, H, dtype=np.float32)[:, None] * np.ones(
        (1, W), dtype=np.float32
    )

    yy = np.linspace(-1.0, 1.0, H, dtype=np.float32)[:, None] * np.ones(
        (1, W), dtype=np.float32
    )
    xx = np.linspace(-1.0, 1.0, W, dtype=np.float32)[None, :] * np.ones(
        (H, 1), dtype=np.float32
    )
    radial = 1.0 - np.sqrt(xx * xx + yy * yy) / np.sqrt(2.0)

    depth = 0.5 * gray + 0.3 * vgrad + 0.2 * radial
    return depth.astype(np.float32)


def estimate_depth(
    rgb: np.ndarray, source: str, model_name: str
) -> tuple[np.ndarray, str]:
    """Dispatch depth acquisition on ``source`` (synthetic|model|auto).

    Returns ``(depth, effective_source)`` where ``effective_source`` is the
    method actually used (``auto`` may downgrade to ``synthetic``).
    """
    if source == "synthetic":
        return synthetic_depth(rgb), "synthetic"
    if source == "model":
        return model_depth(rgb, model_name), "model"  # re-raises on failure
    # auto: try model, gracefully fall back to synthetic
    try:
        return model_depth(rgb, model_name), "model"
    except Exception as exc:  # noqa: BLE001
        print(
            f"WARN: model unavailable ({exc}); using synthetic depth",
            file=sys.stderr,
        )
        return synthetic_depth(rgb), "synthetic"


# --------------------------------------------------------------------------- #
# 2. Normalize -> proximity
# --------------------------------------------------------------------------- #
def normalize_depth(depth: np.ndarray, invert: bool) -> np.ndarray:
    """Robust percentile min-max to proximity in [0,1] (1 = near, 0 = far)."""
    d = depth.astype(np.float32)
    lo, hi = np.percentile(d, 2), np.percentile(d, 98)
    prox = np.clip((d - lo) / (hi - lo + 1e-6), 0.0, 1.0)
    if invert:
        prox = 1.0 - prox
    return prox.astype(np.float32)


# --------------------------------------------------------------------------- #
# 3. Band quantization + per-band scale
# --------------------------------------------------------------------------- #
def depth_bands(prox: np.ndarray, levels: int) -> np.ndarray:
    """Quantize proximity into ``levels`` bands (0 = nearest ... levels-1 = farthest)."""
    band = np.clip(((1.0 - prox) * levels).astype(int), 0, levels - 1)
    return band.astype(np.int32)


def band_scales(levels: int, min_s: int, max_s: int) -> list[int]:
    """Per-band pixel scale: nearest band = min_scale (fine), farthest = max_scale (coarse)."""
    scales: list[int] = []
    for k in range(levels):
        t = k / (levels - 1) if levels > 1 else 0.0
        scales.append(max(1, int(round(min_s + t * (max_s - min_s)))))
    return scales


# --------------------------------------------------------------------------- #
# 4. Multi-scale dither render
# --------------------------------------------------------------------------- #
def render_scale(
    rgb: np.ndarray,
    scale: int,
    algorithm: str,
    palette: np.ndarray,
    contrast: float,
    bayer_n: int,
    strength: float,
) -> np.ndarray:
    """Downscale -> dither -> NEAREST upscale. Returns full-size HxWx3 uint8.

    NEAREST upscale preserves palette colors exactly (no interpolation), so the
    composite stays a strict subset of the palette.
    """
    H, W = rgb.shape[:2]
    if scale <= 1:
        small = rgb
    else:
        sw, sh = max(1, W // scale), max(1, H // scale)
        small = np.asarray(
            Image.fromarray(rgb).resize((sw, sh), Image.BOX), dtype=np.uint8
        )

    dith = pd.dither(
        small,
        algorithm=algorithm,
        palette=palette,
        contrast=contrast,
        bayer_n=bayer_n,
        strength=strength,
        grayscale=True,
    )
    out = np.asarray(
        Image.fromarray(dith).resize((W, H), Image.NEAREST), dtype=np.uint8
    )
    return out


# --------------------------------------------------------------------------- #
# 5. Per-pixel composite
# --------------------------------------------------------------------------- #
def composite(
    rgb: np.ndarray,
    prox: np.ndarray,
    levels: int,
    scales: list[int],
    algorithm: str,
    palette: np.ndarray,
    contrast: float,
    bayer_n: int,
    strength: float,
) -> np.ndarray:
    """Render each distinct band scale once, select per pixel by its depth band."""
    band = depth_bands(prox, levels)
    out = np.zeros_like(rgb)
    cache: dict[int, np.ndarray] = {}
    for k in range(levels):
        s = scales[k]
        if s not in cache:
            cache[s] = render_scale(
                rgb, s, algorithm, palette, contrast, bayer_n, strength
            )
        m = (band == k)[..., None]
        out = np.where(m, cache[s], out)
    return out.astype(np.uint8)


# --------------------------------------------------------------------------- #
# 6. Save depth (optional)
# --------------------------------------------------------------------------- #
def save_depth_png(prox: np.ndarray, path: Path) -> None:
    """Write the proximity map as an 8-bit grayscale-ish RGB PNG (not palette-constrained)."""
    vis = (np.clip(prox, 0.0, 1.0) * 255.0).round().astype(np.uint8)
    rgb = np.stack([vis, vis, vis], axis=-1)
    pd.save_image(rgb, str(path))


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def _is_power_of_two(n: int) -> bool:
    return n >= 2 and (n & (n - 1)) == 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Depth-aware dithering: modulate dither scale by monocular depth."
    )
    p.add_argument("--input", required=True, help="Source image path.")
    p.add_argument("--output", required=True, help="Destination PNG path.")
    p.add_argument(
        "--depth-source",
        choices=["auto", "model", "synthetic"],
        default="auto",
        help="auto=model then synthetic fallback; model=require model; synthetic=offline.",
    )
    p.add_argument(
        "--model",
        default="Intel/dpt-hybrid-midas",
        help="HF model id for the depth pipeline.",
    )
    p.add_argument(
        "--palette",
        choices=list(pd.PALETTES.keys()),
        default="bw",
        help="Palette name.",
    )
    p.add_argument("--levels", type=int, default=3, help="Number of depth bands.")
    p.add_argument(
        "--invert-depth",
        action="store_true",
        help="Flip near<->far (reverse which regions are fine vs coarse).",
    )
    p.add_argument("--min-scale", type=int, default=1, help="Nearest band pixel block size.")
    p.add_argument("--max-scale", type=int, default=8, help="Farthest band pixel block size.")
    p.add_argument(
        "--algorithm",
        choices=["bayer", "floyd-steinberg"],
        default="bayer",
        help="Dither algorithm.",
    )
    p.add_argument("--max-dim", type=int, default=1024, help="Long-edge cap on load.")
    p.add_argument(
        "--save-depth",
        action="store_true",
        help="Also write <output_stem>_depth.png (proximity visualization).",
    )
    p.add_argument("--contrast", type=float, default=1.0, help="Pre-dither contrast.")
    p.add_argument("--bayer-n", type=int, default=4, help="Bayer matrix size (power of two).")
    p.add_argument("--strength", type=float, default=1.0, help="Ordered-dither strength.")

    args = p.parse_args(argv)

    # Extra validation -> exit 2 on bad args.
    if args.levels < 1:
        p.error("--levels must be >= 1")
    if args.min_scale < 1:
        p.error("--min-scale must be >= 1")
    if args.max_scale < args.min_scale:
        p.error("--max-scale must be >= --min-scale")
    if args.max_dim < 1:
        p.error("--max-dim must be >= 1")
    if args.algorithm == "bayer" and not _is_power_of_two(args.bayer_n):
        p.error("--bayer-n must be a power of two >= 2")

    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    # Load image.
    try:
        rgb = pd.load_image(args.input, max_dim=args.max_dim)
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: failed to load input '{args.input}': {exc}", file=sys.stderr)
        return 1

    # Estimate depth (auto may downgrade to synthetic).
    try:
        depth, effective_source = estimate_depth(rgb, args.depth_source, args.model)
    except Exception as exc:  # noqa: BLE001
        # Only reachable when --depth-source model (re-raises).
        print(f"ERROR: depth estimation failed: {exc}", file=sys.stderr)
        return 1

    prox = normalize_depth(depth, args.invert_depth)
    scales = band_scales(args.levels, args.min_scale, args.max_scale)

    palette = pd.PALETTES[args.palette]
    out = composite(
        rgb,
        prox,
        args.levels,
        scales,
        algorithm=args.algorithm,
        palette=palette,
        contrast=args.contrast,
        bayer_n=args.bayer_n,
        strength=args.strength,
    )

    # Write output (create parent dirs).
    out_path = Path(args.output)
    if out_path.suffix == "":
        out_path = out_path / f"{Path(args.input).stem}.png"
    try:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        pd.save_image(out, str(out_path))
    except Exception as exc:  # noqa: BLE001
        print(f"ERROR: failed to write output '{out_path}': {exc}", file=sys.stderr)
        return 1

    if args.save_depth:
        depth_path = out_path.with_name(f"{out_path.stem}_depth.png")
        try:
            save_depth_png(prox, depth_path)
        except Exception as exc:  # noqa: BLE001
            print(f"ERROR: failed to write depth '{depth_path}': {exc}", file=sys.stderr)
            return 1

    print(
        f"DEPTH_OK source={effective_source} levels={args.levels} "
        f"scales={scales} -> {out_path}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
