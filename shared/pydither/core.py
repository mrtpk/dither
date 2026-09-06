"""Core dithering routines (numpy-vectorized) shared by the Python use cases.

Design goals:
- Pure functions operating on numpy uint8/float arrays.
- Ordered dithering is fully vectorized.
- Error diffusion is a serpentine Python loop (inherently sequential) but kept
  reasonably fast by working on a float32 buffer.
"""

from __future__ import annotations

import numpy as np
from PIL import Image


# --------------------------------------------------------------------------- #
# Palettes (RGB rows, uint8)
# --------------------------------------------------------------------------- #
PALETTES: dict[str, np.ndarray] = {
    "bw": np.array([[0, 0, 0], [255, 255, 255]], dtype=np.uint8),
    "ink_on_white": np.array([[17, 17, 17], [245, 245, 245]], dtype=np.uint8),
    "gameboy": np.array(
        [[15, 56, 15], [48, 98, 48], [139, 172, 15], [155, 188, 15]], dtype=np.uint8
    ),
    "loud_neon": np.array([[10, 10, 10], [214, 255, 0]], dtype=np.uint8),
    "riso": np.array([[30, 30, 120], [255, 70, 130]], dtype=np.uint8),
    "amber": np.array([[20, 12, 0], [255, 176, 0]], dtype=np.uint8),
}


# --------------------------------------------------------------------------- #
# I/O
# --------------------------------------------------------------------------- #
def load_image(path: str, max_dim: int | None = None) -> np.ndarray:
    """Load an image as an HxWx3 uint8 RGB array, optionally downscaling."""
    img = Image.open(path).convert("RGB")
    if max_dim is not None and max(img.size) > max_dim:
        scale = max_dim / max(img.size)
        new_size = (round(img.width * scale), round(img.height * scale))
        img = img.resize(new_size, Image.LANCZOS)
    return np.asarray(img, dtype=np.uint8)


def save_image(arr: np.ndarray, path: str) -> None:
    """Save an HxWx3 (or HxW) uint8 array to disk."""
    arr = np.clip(arr, 0, 255).astype(np.uint8)
    Image.fromarray(arr).save(path)


# --------------------------------------------------------------------------- #
# Pre-processing
# --------------------------------------------------------------------------- #
def to_gray(arr: np.ndarray) -> np.ndarray:
    """Return a float32 HxW luminance array in [0, 255]."""
    if arr.ndim == 2:
        return arr.astype(np.float32)
    w = np.array([0.299, 0.587, 0.114], dtype=np.float32)
    return arr[..., :3].astype(np.float32) @ w


def apply_contrast(arr: np.ndarray, contrast: float = 1.0, brightness: float = 0.0) -> np.ndarray:
    """Contrast (multiplier) + brightness (offset), returns float32 same shape."""
    out = (arr.astype(np.float32) - 128.0) * contrast + 128.0 + brightness
    return np.clip(out, 0.0, 255.0)


# --------------------------------------------------------------------------- #
# Bayer / ordered
# --------------------------------------------------------------------------- #
def bayer_matrix(n: int) -> np.ndarray:
    """Return an n x n Bayer matrix normalized to thresholds in (0, 1).

    n must be a power of two (2, 4, 8, 16, ...).
    """
    if n & (n - 1) != 0 or n < 2:
        raise ValueError("n must be a power of two >= 2")
    m = np.array([[0, 2], [3, 1]], dtype=np.float64)
    size = 2
    while size < n:
        m = np.block(
            [
                [4 * m + 0, 4 * m + 2],
                [4 * m + 3, 4 * m + 1],
            ]
        )
        size *= 2
    return (m + 0.5) / (n * n)


def nearest_palette(pixels: np.ndarray, palette: np.ndarray) -> np.ndarray:
    """Snap an (N,3) float array to the nearest palette color (K,3).

    Returns (N,3) uint8.
    """
    diff = pixels[:, None, :].astype(np.float32) - palette[None, :, :].astype(np.float32)
    idx = np.argmin((diff * diff).sum(axis=2), axis=1)
    return palette[idx]


def ordered_dither(
    gray: np.ndarray,
    palette: np.ndarray,
    n: int = 4,
    strength: float = 1.0,
) -> np.ndarray:
    """Vectorized ordered (Bayer) dithering on a grayscale float image.

    gray: HxW float32 in [0,255]; palette assumed grayscale-ish for 2-color.
    Returns HxWx3 uint8.
    """
    h, w = gray.shape
    mat = bayer_matrix(n)
    tiled = np.tile(mat, (h // n + 1, w // n + 1))[:h, :w]
    shifted = gray + (tiled - 0.5) * 255.0 * strength
    flat = np.stack([shifted, shifted, shifted], axis=-1).reshape(-1, 3)
    out = nearest_palette(flat, palette).reshape(h, w, 3)
    return out.astype(np.uint8)


# --------------------------------------------------------------------------- #
# Error diffusion
# --------------------------------------------------------------------------- #
_KERNELS = {
    "floyd-steinberg": (16.0, [(1, 0, 7), (-1, 1, 3), (0, 1, 5), (1, 1, 1)]),
    "atkinson": (8.0, [(1, 0, 1), (2, 0, 1), (-1, 1, 1), (0, 1, 1), (1, 1, 1), (0, 2, 1)]),
    "jarvis-judice-ninke": (
        48.0,
        [
            (1, 0, 7), (2, 0, 5),
            (-2, 1, 3), (-1, 1, 5), (0, 1, 7), (1, 1, 5), (2, 1, 3),
            (-2, 2, 1), (-1, 2, 3), (0, 2, 5), (1, 2, 3), (2, 2, 1),
        ],
    ),
}


def error_diffusion(
    rgb: np.ndarray,
    palette: np.ndarray,
    kernel: str = "floyd-steinberg",
    serpentine: bool = True,
) -> np.ndarray:
    """Error-diffusion dithering on an HxWx3 (or HxW) image.

    Returns HxWx3 uint8.
    """
    if rgb.ndim == 2:
        rgb = np.stack([rgb, rgb, rgb], axis=-1)
    h, w, _ = rgb.shape
    buf = rgb.astype(np.float32).copy()
    divisor, points = _KERNELS[kernel]
    pal = palette.astype(np.float32)

    for y in range(h):
        xs = range(w)
        flip = serpentine and (y % 2 == 1)
        if flip:
            xs = range(w - 1, -1, -1)
        for x in xs:
            old = buf[y, x]
            d = pal - old[None, :]
            k = int(np.argmin((d * d).sum(axis=1)))
            new = pal[k]
            err = old - new
            buf[y, x] = new
            for dx, dy, wgt in points:
                sx = x - dx if flip else x + dx
                sy = y + dy
                if 0 <= sx < w and 0 <= sy < h:
                    buf[sy, sx] += err * (wgt / divisor)
    return np.clip(buf, 0, 255).astype(np.uint8)


# --------------------------------------------------------------------------- #
# High-level convenience
# --------------------------------------------------------------------------- #
def dither(
    arr: np.ndarray,
    algorithm: str = "floyd-steinberg",
    palette: np.ndarray | None = None,
    contrast: float = 1.0,
    brightness: float = 0.0,
    grayscale: bool = True,
    bayer_n: int = 4,
    strength: float = 1.0,
) -> np.ndarray:
    """One-call dithering. Returns HxWx3 uint8."""
    if palette is None:
        palette = PALETTES["bw"]
    work = apply_contrast(arr, contrast, brightness) if (contrast != 1.0 or brightness) else arr.astype(np.float32)

    if algorithm == "bayer" or algorithm.startswith("bayer"):
        gray = to_gray(work)
        return ordered_dither(gray, palette, n=bayer_n, strength=strength)
    if algorithm == "threshold":
        gray = to_gray(work)
        flat = np.stack([gray, gray, gray], axis=-1).reshape(-1, 3)
        h, w = gray.shape
        return nearest_palette(flat, palette).reshape(h, w, 3).astype(np.uint8)

    if grayscale:
        gray = to_gray(work)
        src = np.stack([gray, gray, gray], axis=-1)
    else:
        src = work
    return error_diffusion(src, palette, kernel=algorithm)
