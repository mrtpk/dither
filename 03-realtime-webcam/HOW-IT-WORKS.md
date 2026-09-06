# How It Works — Realtime Webcam Dither

This use case turns a live camera feed into a two-tone, ordered-dithered image
in real time, entirely on the GPU. The interesting part is *why* the dithering
happens in a fragment shader rather than in JavaScript.

## 1. The pipeline

The image flows through a fixed chain, once per animation frame (~60 fps):

```
camera → <video> → per-frame GPU texture upload → fragment shader → <canvas>
```

Every frame, the browser hands the current video frame to the GPU as a texture.
A fragment shader then decides the final color of every pixel of the canvas in
parallel, and the result is displayed immediately. Because the whole transform
is one shader pass over one texture, it comfortably keeps up with live video.

## 2. Luminance and contrast

Color has to be collapsed to a single brightness value before a black/white
(ink/ground) decision can be made. Perceived brightness is a weighted sum of the
red, green, and blue channels using the standard weights `0.299 · R + 0.587 · G
+ 0.114 · B` — green dominates because the human eye is most sensitive to it.

Contrast is applied as a *midpoint stretch* around mid-gray: values are pushed
away from (or pulled toward) 0.5 by a multiplier. Higher contrast makes lights
lighter and darks darker, which sharpens where the dither threshold falls and
gives a punchier 1-bit look.

## 3. Ordered (Bayer) dithering

Ordered dithering compares each pixel's brightness against a threshold read from
a small, repeating `n × n` matrix — the **Bayer matrix**. The matrix is tiled
across the whole image, so the pixel at screen position `(x, y)` uses the
threshold stored at cell `(x mod n, y mod n)`.

If the pixel is brighter than its cell's threshold it becomes the *ground*
color; otherwise it becomes the *ink* color. Because neighboring cells hold
different thresholds, a smoothly varying gray region turns into a stable,
structured pattern of dots whose density tracks the local brightness. Larger
matrices (8×8 vs 2×2) offer more distinct threshold levels and therefore finer
tonal gradations.

## 4. Why the GPU wants ordered, not error diffusion

This is the core design decision.

- **Ordered dithering is stateless per pixel.** A pixel's output depends only on
  its own brightness and a threshold that is a pure function of its coordinates
  (`x mod n, y mod n`). Nothing about one pixel's result depends on any other
  pixel's result. That is exactly the execution model of a fragment shader:
  thousands of fragments are computed independently and simultaneously. Ordered
  dithering therefore parallelizes perfectly.

- **Error diffusion is inherently sequential.** Algorithms like
  Floyd–Steinberg, Atkinson, or Jarvis–Judice–Ninke quantize a pixel and then
  *push the rounding error into neighboring pixels that haven't been processed
  yet*. Each pixel's input depends on the accumulated errors of the pixels
  before it, creating a chain of data dependencies that sweeps across the whole
  image in order. A single-pass parallel shader cannot express that — there is
  no way for one fragment to write into and then read back from its neighbors
  within the same pass.

So for real-time GPU dithering of live video, ordered (Bayer) dithering is the
natural fit, and error diffusion is left to the CPU/Canvas path used elsewhere.

## 5. Bayer threshold math in a shader

The Bayer matrix is built by a recursive construction: a 2×2 seed matrix is
repeatedly expanded, each level quadrupling the previous values and adding a
fixed offset pattern to the four quadrants. The resulting integer indices are
normalized into the range `[0, 1)` so they can be compared directly against
normalized brightness.

Rather than hard-coding the matrix inside the shader, the normalized thresholds
are precomputed and stored in a tiny lookup texture — conceptually a small table
tiled across the screen. The shader reads its cell's threshold with a single
texture lookup. This keeps the shader simple and portable, since it avoids
features that older GPU profiles handle poorly (computed indexing into arrays,
bitwise arithmetic).

## 6. Two-color palette mapping

The final choice is a single comparison: brightness versus threshold. This is a
1-bit decision — one bit of output per pixel — that selects between two colors.
The two colors (ink and ground) are chosen by the user with color pickers, so
the same dithering produces a classic black-on-white look, a neon duotone, an
amber terminal look, and so on, without changing any of the math.

## 7. Pixel scale

Sampling coordinates can be quantized into blocks before the brightness and
threshold lookups happen. When several screen pixels share one block, each
dither cell covers a chunk of the display, producing a deliberately chunky,
low-resolution aesthetic while keeping the dither pattern aligned to the blocks.

## 8. Real-time performance

Two properties make 60 fps achievable. First, there is exactly **one texture
upload per frame** — the current video frame — and no per-pixel work on the CPU.
Second, the per-pixel transform is **embarrassingly parallel**: every fragment
runs the same short program with no cross-pixel communication, so the GPU can
process the entire frame in one pass. A CPU dithering engine, by contrast, must
loop over every pixel in JavaScript (and, for error diffusion, in a strict
order), which cannot sustain live-video frame rates at full resolution.
