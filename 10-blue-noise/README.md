# 10 — Blue Noise (void-and-cluster)

Generate a tileable **blue-noise threshold matrix** with the void-and-cluster
algorithm (Ulichney 1993), then apply it as an ordered-dither threshold texture —
a drop-in replacement for the Bayer matrix that produces smoother, non-repeating,
"expensive-looking" grain. See [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md) for the theory.

Pure numpy — **scipy is not required**. The Gaussian "energy" filter uses numpy's
FFT (toroidal / circular convolution), which is what makes the matrix tile
seamlessly.

## Prerequisites

- WSL with the repo's `.venv` (numpy, Pillow, imageio).
- Run everything with `.venv/bin/python` from the repo root. **Never** `python -c`.

```bash
cd /path/to/dither
```

## Usage

Two subcommands: `generate` and `apply`.

### generate

Build a blue-noise threshold matrix and save it as both `.npy` (exact float
thresholds) and `.png` (8-bit preview / lossy fallback).

| Flag | Default | Meaning |
|------|---------|---------|
| `--size` / `-N` | `64` | Matrix side N (64 is the sweet spot; 128 is much slower). |
| `--sigma` | `1.5` | Gaussian energy sigma (neighborhood scale). |
| `--seed` | `0` | RNG seed for the initial pattern (reproducible). |
| `--density` | `0.1` | Fraction of cells set as initial ones (must be in (0, 0.5)). |
| `--out` | `10-blue-noise/matrices/blue_noise_{N}` | Base path; writes `{out}.png` + `{out}.npy`. |

```bash
# 64x64 tileable blue-noise matrix (png + npy)
.venv/bin/python 10-blue-noise/blue_noise.py generate --size 64 --sigma 1.5 --seed 0 \
  --out 10-blue-noise/matrices/blue_noise_64
```

### apply

Tile (or stretch) the matrix across an image, offset each pixel's brightness by the
local threshold, and snap to a palette.

| Flag | Default | Meaning |
|------|---------|---------|
| `--input` | *(required)* | Source image. |
| `--matrix` | *(auto)* | Path to `.npy`/`.png` matrix; if omitted, a default 64×64 matrix is generated once and cached. |
| `--palette` | `bw` | One of the shared palettes (`bw`, `ink_on_white`, `gameboy`, `loud_neon`, `riso`, `amber`). |
| `--contrast` | `1.0` | Contrast multiplier before dithering. |
| `--strength` | `1.0` | Threshold shift scale (parity with `ordered_dither`). |
| `--tile` / `--no-tile` | `--tile` | Tile matrix across the image (default) vs stretch-to-fit (blockier). |
| `--max-dim` | `1024` | Long-edge cap on load (LANCZOS downscale). |
| `--compare` | off | Also emit a Bayer-8 side-by-side `*_compare.png`. |
| `--output` | *(required)* | Destination PNG (or a directory → `{stem}.png`). |

```bash
# apply a matrix to a sample
.venv/bin/python 10-blue-noise/blue_noise.py apply \
  --input data/samples/01a.png \
  --matrix 10-blue-noise/matrices/blue_noise_64.npy \
  --palette bw --contrast 1.1 \
  --output 10-blue-noise/out/01a_bluenoise.png

# omit --matrix to auto-generate + cache a default 64x64 matrix
.venv/bin/python 10-blue-noise/blue_noise.py apply \
  --input data/samples/02a.png --palette gameboy \
  --output 10-blue-noise/out/02a_bluenoise.png

# side-by-side vs Bayer-8
.venv/bin/python 10-blue-noise/blue_noise.py apply \
  --input data/samples/02a.png --compare \
  --output 10-blue-noise/out/02a_bluenoise.png
```

## Outputs & how to view

- Generated matrices land in `10-blue-noise/matrices/` (default cache) or wherever
  `--out` points; dithered images land wherever `--output` points (e.g.
  `10-blue-noise/out/`).
- Open the `.png` files directly, or serve the folder and browse:

  ```bash
  .venv/bin/python -m http.server 8000
  # then open http://localhost:8000/10-blue-noise/out/ in a browser
  ```

## Exit codes

- `0` — success.
- `2` — bad arguments (e.g. invalid `--size` or `--density`).
- `1` — runtime failure (image load, matrix load, or write error).

## Smoke test

```bash
.venv/bin/python 10-blue-noise/_smoke.py
```

Generates a fast 32×32 matrix, checks it is a valid permutation ranking spanning
(0, 1), applies it to a sample and confirms the colors are a subset of the palette,
runs a soft blue-noise spectral check, and prints `SMOKE_OK`.
