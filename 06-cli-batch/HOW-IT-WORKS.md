# How Batch Dithering Works

## Goal

Batch dithering reduces many full-color photographs to a small, fixed palette while preserving perceived tone and structure. The CLI applies the same transform to every image in a folder so you can process large sets without opening a browser or editing files one at a time.

## Grayscale path

Each pixel’s color is converted to a single luminance value using standard weights: roughly 30% red, 59% green, and 11% blue. That gray value drives quantization. **Contrast** stretches values around mid-gray (multiplier on the distance from 128). **Brightness** shifts all tones up or down uniformly. Both happen before any dithering pattern is applied.

## Palette snapping

A palette is a small set of allowed RGB colors. For each pixel (represented as a gray triple or full RGB), the engine picks the palette color whose squared Euclidean distance in RGB space is smallest. For ordered and threshold paths this comparison runs across the entire image at once—every pixel independently finds its nearest neighbor in the palette.

## Error diffusion

Algorithms such as Floyd–Steinberg, Atkinson, and Jarvis–Judice–Ninke work one pixel at a time in scan order:

1. Quantize the current pixel to the nearest palette color.
2. Compute the error between the original value and the chosen color.
3. Distribute fractions of that error to nearby pixels that have not yet been processed.

Each algorithm uses a different kernel: a set of neighbor offsets and weights that define how error spreads. **Serpentine** scanning alternates row direction (left-to-right, then right-to-left) so error does not accumulate in a visible diagonal bias. Error diffusion cannot be fully vectorized because each pixel’s quantization depends on accumulated errors from earlier pixels in the same pass.

## Ordered dither (Bayer)

Instead of propagating error spatially, ordered dither tiles a small threshold matrix (a Bayer matrix) across the image. Each cell’s threshold is added to the local tone (scaled by strength) before palette snapping. Where tone plus offset crosses a decision boundary, the pixel flips to the other palette color. The whole grid is computed with array operations—no per-pixel dependency chain—so it is much faster on large images.

## Threshold

Threshold is the degenerate case: map each tone directly to the nearest palette color with no spatial pattern and no error spread. Useful as a baseline or when you want flat posterization without texture.

## Why NumPy matters

Ordered and threshold paths benefit from whole-array arithmetic: tiling matrices, broadcasting offsets, and batch nearest-color lookup over millions of pixels in one shot. Error diffusion still loops in Python over pixels, but it keeps a float32 working buffer so additions stay fast and stable. Batch CLI parallelism (`--jobs`) helps most when many images use error-diffusion algorithms, since each file’s inner loop is inherently sequential.

## Pixel scale (block size)

When **scale** is greater than one, the image is downsampled with nearest-neighbor so each logical cell merges an N×N block of source pixels. Dithering runs on the smaller grid, then the result is upscaled with nearest neighbor back to the original dimensions. Output width and height match the loaded image, but each visible “pixel” is an N×N block of identical color—chunky retro blocks without shrinking the canvas.
