"""Shared, numpy-vectorized dithering engine reused by the Python use cases.

Public API:
    load_image, save_image, to_gray, apply_contrast,
    ordered_dither, error_diffusion, dither,
    bayer_matrix, PALETTES, nearest_palette
"""

from .core import (
    load_image,
    save_image,
    to_gray,
    apply_contrast,
    bayer_matrix,
    ordered_dither,
    error_diffusion,
    dither,
    nearest_palette,
    PALETTES,
)

__all__ = [
    "load_image",
    "save_image",
    "to_gray",
    "apply_contrast",
    "bayer_matrix",
    "ordered_dither",
    "error_diffusion",
    "dither",
    "nearest_palette",
    "PALETTES",
]
