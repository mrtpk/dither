# 11 — Depth-Aware Dithering

Estimate a **monocular depth map** from a single image and use it to **modulate the
dither scale** so the dot texture follows 3D form: near regions render fine/dense,
far regions render coarse/chunky (reverse with `--invert-depth`). Depth comes from a
`transformers` depth-estimation pipeline, with a **deterministic offline synthetic
fallback** so the tool always works — even with no internet and no model installed.

See [`HOW-IT-WORKS.md`](HOW-IT-WORKS.md) for the concepts and math.

## Prerequisites

- **WSL** with the repo's virtualenv at `.venv`. Always run with `.venv/bin/python`.
- `numpy` + `Pillow` (already used by the shared engine).
- For the **model** path only: `torch` (CPU is fine), `transformers`, and `timm`.
- **Model download note:** the first `--depth-source model` (or `auto`) run downloads
  the model weights and needs **internet**. Weights are cached afterward (under the
  Hugging Face cache) and later runs are offline. The `synthetic` path never touches
  the network.

## Depth sources (`--depth-source`)

| Value | Behavior |
|-------|----------|
| `auto` *(default)* | Try the model; on any failure, print a warning and fall back to synthetic depth. |
| `model` | Require the real model. Exits non-zero if torch/transformers/weights are unavailable. |
| `synthetic` | Deterministic offline pseudo-depth (luminance + vertical + radial cues). No download. |

## CLI flags

| Flag | Default | Meaning |
|------|---------|---------|
| `--input` | *(required)* | Source image path. |
| `--output` | *(required)* | Destination PNG (a directory → `{input_stem}.png` inside it). |
| `--depth-source` | `auto` | `auto` \| `model` \| `synthetic` (see table above). |
| `--model` | `Intel/dpt-hybrid-midas` | HF model id (e.g. `LiheYoung/depth-anything-small-hf` — smaller/faster). |
| `--palette` | `bw` | One of the shared palettes (`bw`, `ink_on_white`, `gameboy`, `loud_neon`, `riso`, `amber`). |
| `--levels` | `3` | Number of discrete depth bands / dither scales. |
| `--invert-depth` | off | Flip near⇄far (reverse which regions are fine vs coarse). |
| `--min-scale` | `1` | Pixel block size for the **nearest** band (finest). |
| `--max-scale` | `8` | Pixel block size for the **farthest** band (coarsest). |
| `--algorithm` | `bayer` | `bayer` \| `floyd-steinberg`. |
| `--max-dim` | `1024` | Long-edge cap on load (LANCZOS). |
| `--save-depth` | off | Also write `<output_stem>_depth.png` (proximity visualization). |
| `--contrast` | `1.0` | Pre-dither contrast. |
| `--bayer-n` | `4` | Bayer matrix size (power of two) when `--algorithm bayer`. |
| `--strength` | `1.0` | Ordered-dither threshold-shift strength. |

Exit codes: `0` success, `2` bad arguments, `1` load/write/model-required failure.

## Examples (from repo root, WSL)

```bash
cd /path/to/dither

# A) OFFLINE synthetic depth (deterministic, no download) — near=fine, far=coarse
.venv/bin/python 11-depth-aware/depth_dither.py \
  --input data/samples/01a.png --output 11-depth-aware/out/01a_depth.png \
  --depth-source synthetic --palette bw --levels 3 --min-scale 1 --max-scale 8 \
  --algorithm bayer --save-depth

# B) MODEL depth (first run downloads weights) — DPT-hybrid-midas
.venv/bin/python 11-depth-aware/depth_dither.py \
  --input data/samples/02a.png --output 11-depth-aware/out/02a_depth.png \
  --depth-source model --model Intel/dpt-hybrid-midas --levels 4 --algorithm floyd-steinberg

# C) AUTO (try model, silently fall back to synthetic if offline), reversed near/far
.venv/bin/python 11-depth-aware/depth_dither.py \
  --input data/samples/03a.png --output 11-depth-aware/out/03a_depth.png \
  --depth-source auto --invert-depth --levels 3 --palette gameboy
```

## Output & viewing

- Dithered results and depth maps land under `11-depth-aware/out/`.
- With `--save-depth`, the `*_depth.png` next to the output shows the **proximity**
  map (white = near, black = far). It's a visualization and is *not* palette-
  constrained — only the dither output uses the palette.
- View by opening the PNGs directly, or serve the folder:
  ```bash
  .venv/bin/python -m http.server 8000
  # then browse to http://localhost:8000/11-depth-aware/out/
  ```

## Smoke test

```bash
.venv/bin/python 11-depth-aware/_smoke.py
```

It runs the synthetic path fast (`--max-dim 96`), asserts the output is a valid PNG
whose colors are a subset of the palette, is non-flat, and **differs** from a single
uniform-scale render (proving depth actually modulated the texture). It optionally
attempts the model path and prints `MODEL_SKIP` (never failing) when the model is
unavailable. On success it prints `SMOKE_OK`.
