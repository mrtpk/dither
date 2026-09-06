# 08 — Vector SVG dither

One image in, a **real vector SVG** out: dithered `<rect>` runs or AM-halftone `<circle>`s. Geometry only — no raster `<image>` embed. Built for screenprint / merch (scale, plot, and ink plates).

This is a **single-image** CLI, not a folder batch (that is 06). Use cases 01 and 06 write **pixels**; this writes **paths**.

See [`HOW-IT-WORKS.md`](./HOW-IT-WORKS.md) for the math.

## Prerequisites

- WSL (or Linux) with the repo cloned
- Python virtualenv at `.venv` (from repo root: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`). `requirements.txt` includes `svgwrite`.
- Sample images: `.venv/bin/python shared/make_samples.py` (creates `data/samples/*.png`)

Always run with `.venv/bin/python`. Do not use system `python`.

## Usage

From repo root:

```bash
cd /path/to/dither

.venv/bin/python 08-vector-svg/dither_svg.py \
  --input data/samples/01a.png \
  --output 08-vector-svg/out/01a.svg \
  --style rect
```

`--output` may be a file (`path/to/out.svg`) or a directory (`path/to/out/` → `{stem}.svg`). Parents are created. An existing `.svg` is overwritten.

## Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--input` | *(required)* | Source **file** (not a directory). One image per run; no globs. |
| `--output` | *(required)* | Destination `.svg` **or** a directory (`{stem}.svg`). |
| `--style` | `rect` | `rect` (dither grid → merged rectangles) or `dots` (halftone circles). |
| `--cells` | `120` | Logical **grid width** in cells (8–400), not source pixel width. Height follows aspect. Default 120 keeps file size sane. |
| `--algorithm` | `bayer` | **rect only** (ignored for `dots`): `bayer`, `threshold`, `floyd-steinberg`, `atkinson`, `jarvis-judice-ninke`. |
| `--palette` | `bw` | `bw`, `ink_on_white`, `gameboy`, `loud_neon`, `riso`, `amber`. |
| `--contrast` | `1.0` | Contrast multiplier before dither / coverage. |
| `--angle` | `45` | **dots only**. Screen rotation of the dot layer in degrees. `0` = axis-aligned. |
| `--max-dim` | `1024` | Long-edge cap on load (LANCZOS); `0` = no load cap. Does not change `--cells`. |
| `--bg` | `#ffffff` | Paper / ground fill (`#RRGGBB` or `#RGB`). Composite only. |
| `--ink` | unset | Force a single ink fill (and 1-bit “on” color for rect). |
| `--separate` | off | One SVG per ink plate instead of a composite. |
| `--bayer-n` | `4` | Bayer matrix size (power of two ≥ 2). Only meaningful for `--algorithm bayer`. |

Grayscale, brightness (`0`), and strength (`1`) are fixed and not exposed.

`--cells` is the working resolution. Higher values grow the file quickly (especially Bayer checkerboards). Prefer the default unless you need a finer screen.

## Examples

**Default — Bayer rects, black on white, 120 cells**

```bash
.venv/bin/python 08-vector-svg/dither_svg.py \
  --input data/samples/01a.png \
  --output 08-vector-svg/out/01a.svg \
  --style rect
```

**Floyd–Steinberg rects, neon ink on custom paper, finer grid**

```bash
.venv/bin/python 08-vector-svg/dither_svg.py \
  --input data/samples/02a.png \
  --output 08-vector-svg/out/02a-neon.svg \
  --style rect --algorithm floyd-steinberg \
  --palette loud_neon --ink "#0a0a0a" --bg "#d6ff00" \
  --cells 160 --contrast 1.4
```

**Halftone dots at 45° (newspaper black)**

`--style dots` ignores `--algorithm`. Default `--angle 45` rotates the dot layer and over-scans the lattice so the field covers the whole canvas.

```bash
.venv/bin/python 08-vector-svg/dither_svg.py \
  --input data/samples/01a.png \
  --output 08-vector-svg/out/01a-dots.svg \
  --style dots --cells 80 --angle 45 --ink "#111111" --bg "#f5f5f5"
```

**Riso two-ink plates (rect)**

`--separate` writes `{stem}_{slug}.svg` — ink geometry only, no paper fill, same viewBox for registration.

```bash
.venv/bin/python 08-vector-svg/dither_svg.py \
  --input data/samples/02a.png \
  --output 08-vector-svg/out \
  --style rect --palette riso --bg "#ffffff" --separate
```

Produces `08-vector-svg/out/02a_riso_blue.svg` and `02a_riso_pink.svg`.

## How to open the SVG

- **Browser:** drag the `.svg` onto a tab, or serve the repo and open the file:
  ```bash
  .venv/bin/python -m http.server 8000
  ```
  then visit `http://localhost:8000/08-vector-svg/out/01a.svg`.
- **Print / merch:** Inkscape, Illustrator, or Affinity. Scale to shirt size — `viewBox` is in cell units, `width`/`height` are millimeters (1 cell = 1 mm), and `preserveAspectRatio` is `xMidYMid meet` so the design letterboxes instead of stretching.
- **Plotter / cut:** ungroup, select one ink, send paths. Plate files from `--separate` are already one ink and have no paper rectangle to cut.

## Output notes

- Composite (default): paper rectangle plus all inks, each ink in a group `ink-{slug}`.
- `--separate`: `{prefix}_{slug}.svg` (known slugs include `black`, `riso_blue`, `riso_pink`, `gb0`…; `--ink` override uses `ink`). Transparent background — ink marks only.
- Exit `0` on success, `2` on bad arguments, `1` on load/write failure.
