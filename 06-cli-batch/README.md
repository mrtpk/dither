# 06 — CLI Batch Dithering

Headless folder-to-folder batch dithering. Reads images from an input directory, applies `shared.pydither`, writes PNGs to an output directory.

## Prerequisites

- WSL (or Linux) with the repo cloned
- Python virtualenv at `.venv` (from repo root: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`)
- Sample images: `.venv/bin/python shared/make_samples.py` (creates `data/samples/*.png`)

## Usage

From repo root:

```bash
cd /path/to/dither

.venv/bin/python 06-cli-batch/dither_batch.py \
  --input data/samples \
  --output 06-cli-batch/out \
  --algorithm floyd-steinberg \
  --palette bw
```

## Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--input` | *(required)* | Input directory; must exist |
| `--output` | *(required)* | Output directory; created if missing |
| `--algorithm` | `floyd-steinberg` | `floyd-steinberg`, `atkinson`, `jarvis-judice-ninke`, `bayer`, `threshold` |
| `--palette` | `bw` | `bw`, `ink_on_white`, `gameboy`, `loud_neon`, `riso`, `amber` |
| `--bayer-n` | `4` | Bayer matrix size (power of two ≥ 2); only affects `--algorithm bayer` |
| `--contrast` | `1.0` | Contrast multiplier before dither |
| `--brightness` | `0.0` | Brightness offset before dither |
| `--strength` | `1.0` | Bayer threshold strength; only affects ordered Bayer dither |
| `--max-dim` | `1024` | Long-edge cap on load (LANCZOS); `0` = full resolution |
| `--scale` | `1` | Block size in pixels: N×N merge before dither, then upscale back (`1` = off) |
| `--jobs` | `1` | Parallel worker count |
| `--recursive` | off | Search subdirectories under `--input` |
| `--pattern` | `*.png,*.jpg,*.jpeg,*.webp` | Comma-separated globs |
| `--suffix` | `_dithered` | Inserted before `.png` in output names (`""` for none) |
| `--overwrite` | off | Replace existing outputs; otherwise skip with warning |
| `--quiet` | off | Suppress per-file lines; summary still prints |

Grayscale is always enabled (`grayscale=True`).

## Examples

**Basic batch on samples**

```bash
.venv/bin/python 06-cli-batch/dither_batch.py \
  --input data/samples \
  --output 06-cli-batch/out \
  --algorithm floyd-steinberg \
  --palette bw
```

**Bayer 8×8, Game Boy palette, chunky pixels**

```bash
.venv/bin/python 06-cli-batch/dither_batch.py \
  --input data/samples \
  --output 06-cli-batch/out-bayer \
  --algorithm bayer --bayer-n 8 --strength 1.2 \
  --palette gameboy --scale 4
```

**Parallel, recursive, custom patterns**

```bash
.venv/bin/python 06-cli-batch/dither_batch.py \
  --input data \
  --output 06-cli-batch/out-all \
  --recursive --pattern "*.png" \
  --jobs 4 --overwrite --max-dim 2048
```

## Output naming

- Flat mode: `{output}/{stem}{suffix}.png` — e.g. `data/samples/01a.png` → `06-cli-batch/out/01a_dithered.png`
- Recursive: relative subpaths preserved — e.g. `photos/sub/cat.jpg` → `out/sub/cat_dithered.png`
- All outputs are PNG regardless of source format.

## Exit codes

| Code | Meaning |
|------|---------|
| `0` | At least one file written (partial failures OK) |
| `1` | No files matched, or zero files written (all failed/skipped) |
| `2` | Invalid arguments (bad palette, bayer-n, missing input dir, etc.) |

## `--max-dim` vs `--scale`

Order is fixed: **load** (optional LANCZOS long-edge cap) → **scale** (nearest down/up blockify) → **dither** → **save**.

- `--max-dim 1024` caps the long edge when loading.
- `--max-dim 0` loads full file resolution.
- `--scale N` merges each N×N block before quantization; output dimensions stay the same as after load, but pixels look blocky.
- Example: `--max-dim 512 --scale 4` fits long edge to 512, then dithers on a grid 4× coarser before upscaling back.

## `--jobs`

Default `1` is safest for debugging. Error-diffusion algorithms use a per-pixel loop and benefit from `--jobs` on large folders. Ordered/threshold/Bayer paths are already vectorized and fast per image. Match worker count to CPU cores when batching many files with Floyd–Steinberg, Atkinson, or JJN.

## Smoke test

```bash
rm -rf 06-cli-batch/out
.venv/bin/python 06-cli-batch/_smoke.py
```

Prints `BATCH_OK {n}` on success.
