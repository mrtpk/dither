# How It Works

This tool reduces full-color photographs to a small, fixed palette while preserving the *perceived* brightness and detail of the original. The result looks like classic print graphics, retro game art, or risograph posters — depending on which palette and algorithm you choose.

## Goal: tone on a limited palette

A digital photo contains millions of colors. A dithered image might use only two, four, or five. The challenge is deciding which palette color each pixel should become without making the image look like a flat poster. Dithering solves this by trading exact color accuracy for spatial patterns of dots that our eyes blend into smooth gradients.

## Grayscale and tone adjustment

Before quantization, the image is converted to grayscale using a luminance formula that weights green more heavily than blue, matching human brightness perception. Contrast stretches values away from mid-gray — higher contrast pushes shadows darker and highlights brighter. Brightness simply shifts every value up or down. These adjustments happen *before* dithering so you can tune the tonal range the algorithm sees.

## Palette snapping (nearest color)

Once a pixel has a gray value (or RGB triple after optional color processing), it must be replaced by the closest color in the chosen palette. "Closest" is measured as squared Euclidean distance in RGB space — the palette entry whose red, green, and blue components differ least from the pixel wins. With only two colors this is binary black-or-white; with more colors you get richer but still limited output.

## Error diffusion (Floyd–Steinberg, Atkinson, Jarvis–Judice–Ninke)

Error-diffusion algorithms process pixels left-to-right, top-to-bottom. For each pixel they snap to the nearest palette color, then compute the *quantization error* — the difference between the original value and the snapped value. That error is distributed to neighboring pixels that have not yet been processed, using a fixed kernel of fractional weights.

Floyd–Steinberg spreads error to four neighbors (right, bottom-left, bottom, bottom-right). Atkinson uses a wider six-neighbor pattern but only passes along a fraction of the error, producing lighter, airier dithering. Jarvis–Judice–Ninke uses a larger 12-neighbor kernel for smoother, more gradual transitions at the cost of a softer look.

The key insight: error diffusion encodes "missing brightness" into nearby pixels, so a 50% gray area becomes an alternating pattern of black and white dots rather than flat mid-gray — which is impossible on a two-color palette anyway.

## Ordered dither (Bayer 2×2, 4×4, 8×8)

Ordered dithering tiles a repeating threshold matrix across the image. Each matrix cell holds a value between 0 and 1. Before snapping to a palette color, the pixel's brightness is offset by a threshold derived from its position in the matrix. Pixels that land above the threshold snap one way; those below snap the other — creating a regular crosshatch or dot-screen pattern.

Larger matrices (8×8) produce finer, more subtle patterns; smaller ones (2×2) produce bold checkerboards. The **strength** control scales how much the threshold shifts the pixel value — at zero the matrix has no effect; at higher values the pattern becomes more pronounced.

## Threshold

Threshold is the degenerate case: a 1×1 matrix with no spatial variation. Every pixel is simply snapped to the nearest palette color with no pattern overlay. On a two-color palette this yields a flat posterized look — hard edges between black and white regions with no dither texture.

## Pixel scale: why downscaling creates chunky pixels

The **pixel scale** control shrinks the image *before* dithering by averaging source pixels into larger blocks. A scale of 4 turns every 4×4 source region into a single cell. Dithering then runs on this smaller grid — each cell becomes one palette color. When the result is displayed upscaled with nearest-neighbor interpolation (no smoothing), each dither cell maps to a visible square block on screen. This is how you get the chunky retro pixel-art aesthetic without manually drawing at low resolution.

## Invert

Checking **invert** applies a photographic negative — each RGB channel becomes `255 minus its value` — before dithering. Light areas become dark and vice versa. This is a simple pre-pass on a fresh copy of the image data each render, so toggling it does not corrupt subsequent frames.
