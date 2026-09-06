# How depth-aware dithering works

This tool makes the dither texture *follow 3D form*: it estimates how near or far
each pixel is, then changes the dot/block size of the dithering accordingly. Near
surfaces get fine, dense dots; far surfaces get coarse, chunky blocks (or the
reverse). The result reads as relief — the halftone appears to wrap the shapes in
the image and recede with distance.

## 1. What a monocular depth model outputs

A monocular depth network predicts a per-pixel depth value from a **single** RGB
image — no stereo pair, no sensor. Crucially it predicts **relative** (or
**inverse**) depth, not metric distance: there is no "3.2 meters" here, only an
ordering of what is nearer and what is farther.

- **DPT / MiDaS** predict *inverse depth*: larger values mean **closer**.
- **Depth-Anything** predicts *relative depth*: larger values also mean **closer**.

Because both conventions make "bigger = nearer", we can treat the raw model output
as a **proximity** signal directly, with no per-model special-casing. The heavy
lifting is done by a `transformers` `depth-estimation` pipeline; the first run
downloads the model weights and caches them.

## 2. Normalizing depth into proximity

Raw depth values live on an arbitrary, model-dependent scale, so we normalize them
into a fixed `[0, 1]` **proximity** range where `1 = nearest` and `0 = farthest`.

We use a **robust percentile min–max**: instead of the true min/max, we clip to the
2nd and 98th percentiles before rescaling. This stops a single hot/cold outlier
pixel from crushing the whole range into a narrow band, which would flatten the
depth effect. `--invert-depth` simply replaces proximity with `1 - proximity`,
swapping which regions are treated as near vs far — useful when a scene's natural
ordering is the opposite of what you want emphasized.

## 3. Banding: quantizing continuous depth

Continuous proximity is quantized into `--levels` discrete slabs ("bands"). Band 0
is the nearest slab, band `levels-1` is the farthest. Each band will be rendered at
its own dither scale. Fewer levels give bold, poster-like depth steps; more levels
give a smoother gradient of texture density.

## 4. How depth modulates dither density

The primary density knob is **pixel scale** — the size of each dither dot/block.

- Render the image at a small size (downscale by the scale factor), dither it, then
  upscale back to full size with **nearest-neighbor** interpolation. A large scale
  factor therefore produces large, chunky dither blocks; scale 1 produces the
  finest possible dots.
- Larger blocks mean fewer, bigger dots per unit area — i.e. **lower spatial
  density**. So mapping *far → large scale* makes distant regions coarse and near
  regions crisp.

The band-to-scale mapping is linear: the nearest band maps to `--min-scale`
(finest) and the farthest band to `--max-scale` (coarsest), with intermediate bands
interpolated between them.

An alternative density knob (documented, not the default) is to vary the **Bayer
matrix size** per band instead of pixel blocks — a finer or coarser ordered-dither
grid. This is especially clean for the `bayer` algorithm because it changes the
threshold pattern's period without resampling the image. Pixel-scale is kept as the
primary knob because it reads most obviously as depth.

## 5. Why this creates a sense of form

Human vision uses texture gradients as a strong depth cue: consistent surface
texture appears finer and denser as it recedes, coarser as it approaches (or vice
versa). By tying dot density to estimated depth, the dithering imitates this
gradient. The halftone stops being a flat screen laid over the picture and instead
seems to sit *on the surfaces*, giving a tactile, sculpted, "wrapped" impression of
the 3D structure.

## 6. Compositing math

Each **distinct** band scale is rendered exactly once over the whole image (renders
that share a scale are cached and reused). Then, for every pixel, the output takes
its color from the render whose scale matches that pixel's depth band — a **hard,
per-pixel selection**, not a blend.

Hard selection matters for color purity: every rendered image is already snapped to
the palette, and nearest-neighbor upscaling introduces no new colors, so selecting
whole pixels keeps the final image a strict **subset of the palette**.

A softer alternative would blend adjacent bands to hide the seams between slabs. But
linearly alpha-blending two palette-snapped images produces off-palette intermediate
colors. The palette-preserving way to soften seams is a **stochastic / dither-based
selection**: pick which band a pixel draws from using its continuous proximity plus
Bayer threshold noise, so the boundary dissolves into a dithered transition while
every pixel still lands on an exact palette color. The tool ships the hard-select
path as the correct default; the stochastic blend is described here as a possible
enhancement.

## 7. Model vs synthetic fallback

Depth can come from three sources (`--depth-source`):

- **`model`** — run the real depth network. Requires `torch` + `transformers` and,
  on first use, an internet connection to download weights. If it can't run, the
  tool exits with an error (so scripts can require real depth).
- **`synthetic`** — a deterministic, offline pseudo-depth built entirely from the
  input pixels and image geometry: a weighted blend of **luminance** (a structure
  cue), a **vertical gradient** (bottom of frame treated as nearer, a common photo
  prior), and a **radial gradient** (center nearer, corners farther). It needs no
  network and always produces the same map for the same input, which is what makes
  the tool and its smoke test reliable everywhere.
- **`auto`** (default) — try the model first; on any failure (missing packages,
  download error, network issue, model load error) print a one-line warning and
  fall back to synthetic depth. This gives the best available result without ever
  hard-failing.
