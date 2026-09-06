# How it works — Blue Noise (void-and-cluster)

This use case has two halves: **generate** a blue-noise threshold matrix, and
**apply** it as an ordered-dither threshold texture (a drop-in replacement for
the classic Bayer matrix). Everything runs in pure numpy — the only nontrivial
tool is the Fast Fourier Transform, used to compute a Gaussian "energy" field.

## 1. What blue noise is

"Blue noise" describes a random-looking distribution whose **power spectrum has
very little low-frequency energy** and is dominated by high frequencies (hence
"blue", the high-frequency end of the spectrum). Spatially, that translates to
points that are **evenly spaced, isotropic, and aperiodic**: there are no clumps
(clusters) and no gaps (voids), yet no visible grid or repeating pattern either.
Think of it as "maximally spread out randomness".

## 2. Why it beats Bayer and white noise

A threshold-matrix dither turns a smooth gradient into a pattern of dots, and the
*spectrum* of that matrix decides how the pattern looks to the eye:

- **Bayer (ordered) matrices** are perfectly periodic. Their spectrum is a set of
  sharp spikes, so the output shows an obvious crosshatch / woven texture and a
  visible tiling repeat. Cheap, but it looks mechanical.
- **White noise** has a flat spectrum — equal energy at all frequencies. Because
  low frequencies are present, random clumps and holes form. The eye is very
  sensitive to those low-frequency blobs, so the result looks grainy and "dirty".
- **Blue noise** deliberately pushes the error into **high frequencies**, exactly
  where human vision is least sensitive. The grain becomes fine and uniform, there
  is no repeating structure, and gradients look smooth and "expensive". You get a
  better-looking dither for the same 1-bit-per-pixel budget.

## 3. Ordered dithering with a threshold texture

Ordered dithering is simple: tile a small threshold matrix across the image, add
`(threshold − 0.5)` (scaled to the pixel range) to each pixel's brightness, then
snap every pixel to the nearest palette color. Where the local brightness plus the
threshold crosses the midpoint, the pixel flips color. The *arrangement* of
thresholds is what forms the dot texture. Bayer and blue noise plug into the exact
same pipeline — only the matrix differs — so swapping in a blue-noise matrix
upgrades the visual quality "for free", with no change to the runtime cost.

## 4. The void-and-cluster algorithm (Ulichney 1993)

Void-and-cluster builds a matrix whose thresholds, taken in increasing order, add
dots one at a time in the most blue-noise way possible. It works on a binary
pattern and a **Gaussian energy field** that measures how crowded each location is
(a pixel's energy is the sum of nearby set pixels, weighted by a Gaussian).

- **Cluster** = a set pixel sitting where the energy is highest (too crowded).
- **Void** = an empty pixel sitting where the energy is lowest (too empty).

The algorithm proceeds in phases:

1. **Initial pattern.** Scatter a small minority of "1" pixels at random (about
   10%) with a seeded RNG so results are reproducible.
2. **Phase 1 — homogenize.** Repeatedly take the pixel in the *tightest cluster*,
   move it to the *largest void*, and recompute the energy. This relaxes the random
   start into a maximally even ("stable") prototype. The loop stops when the void it
   would fill is the very cell it just emptied — a fixed point — with a safety cap on
   iterations in case of rare oscillation.
3. **Phase 2 — rank every pixel.** Assign each of the N² cells a unique rank:
   - Starting from the prototype, repeatedly remove the tightest cluster, handing out
     *decreasing* ranks — this orders the initial minority pixels.
   - Then, again from the prototype, repeatedly fill the largest void, handing out
     *increasing* ranks until every cell is ranked.

   Conceptually the second half is Ulichney's "operate on the complement" step: once
   the majority of pixels are set, the *largest void among the 0s* is the same as the
   *tightest cluster among the 0s* in the inverted pattern. Because the Gaussian
   kernel is normalized so the whole field sums consistently, these two views are
   *identical*, so a single continuous "fill the largest void" loop reproduces the
   complement-based second half exactly.

Finally the ranks are normalized to thresholds in the open interval (0, 1) via
`(rank + 0.5) / N²`, matching the `(m + 0.5)/(n·n)` convention used by the Bayer
matrix in the shared engine. Every threshold value is distinct, so the matrix is a
true permutation of the [0, 1) interval.

## 5. Gaussian energy + toroidal wrap

The energy field is a Gaussian blur of the binary pattern. Rather than a spatial
loop, it is computed as a **circular convolution via FFT**: multiply the pattern's
FFT by the precomputed FFT of the Gaussian kernel and inverse-transform. Two
important details:

- **Origin at (0, 0), not centered.** The kernel is built with its peak at the
  corner (using signed toroidal distances), *not* fftshifted to the middle. Circular
  convolution expects the origin at 0; a centered kernel would shift the whole
  energy field by half the matrix in each axis.
- **Toroidal wrap.** Circular convolution treats the matrix as living on a torus —
  the left edge is adjacent to the right, top to bottom. Cluster/void decisions
  therefore respect wrap-around, which is exactly what makes the finished matrix
  **tile seamlessly** across a large image with no visible seams.

The kernel's `sigma` (default ~1.5) sets the neighborhood scale: larger sigma means
a broader, smoother energy field and coarser blue-noise texture; smaller sigma
tightens the spacing.

## 6. Spectral properties

If you take the 2-D FFT of the finished matrix, its **radial power spectrum** is
suppressed near the center (DC / low frequency) and rises toward the edges (high
frequency) — a ring-like distribution with a quiet middle. This is the blue-noise
signature. Contrast it with:

- **Bayer:** discrete spikes at the periodic frequencies.
- **White noise:** flat, energy everywhere including the damaging low band.

The `_smoke.py` spectral check verifies this by comparing average power in a
low-frequency annulus near the center against a high-frequency annulus farther out
and confirming the low band carries less energy.

## Optional: multi-level blue noise

A single blue-noise matrix is fundamentally a **two-tone** (single-threshold)
method: it decides, per pixel, between the two nearest palette colors. Multi-tone
palettes still work through the same `nearest_palette` snap (as with Bayer), but
that is not the same as true per-level blue noise, which would use a distinct
blue-noise threshold texture between each adjacent pair of palette levels. That
extension is out of scope here and left as a possible future enhancement.
