# 04 — Print Halftone

A browser tool that renders classic print **AM halftone** from a photograph: a rotated grid of ink dots whose **size** carries tone. Two modes — Riso-style **duotone** (one ink on paper) and four-plate **CMYK** with multiply compositing.

This is not dithering. Dots are drawn with Canvas 2D (`arc` / `fillRect`); radius grows with the square root of coverage so area matches tone.

## Prerequisites

- WSL (Windows Subsystem for Linux)
- Python virtual environment at `.venv` in the repo root
- Sample image built at `data/samples/02a.png`

## Run

From Windows, start a static file server via WSL (serve from the **repo root**, not this folder):

```bash
.venv/bin/python -m http.server 8000
```

Open in your browser:

```
http://localhost:8000/04-halftone/
```

Stop the server with `Ctrl+C` in the WSL terminal.

> **Note:** ES modules and image loading require HTTP — opening `index.html` directly as a `file://` URL will not work.

## How to use

On first load the tool automatically displays the sample image `02a.png` in **duotone** with the Riso blue/pink pair, 10 px cells, 45° screen, circle dots, and contrast 1.2.

### Controls

| Control | What it does |
|---------|--------------|
| **Load image** | Replace the sample with your own raster image |
| **Mode** | **Duotone** — one ink screen on paper. **CMYK** — four process plates at classic angles, multiplied on white |
| **Cell size** | Grid spacing in pixels (4–32). Larger cells mean chunkier newspaper dots |
| **Dot shape** | Circle (classic AM), square (area-scaled tiles), or line (full-width bar, thickness = coverage) |
| **Screen angle** | Duotone lattice rotation in degrees (0–90). Disabled in CMYK — process angles are fixed |
| **Contrast** | Midtone stretch before coverage is computed (0.5–3.0) |
| **Tone preset** | Seed ink and paper from Riso, Loud Neon, Ink on White, Amber, Black & White, or Custom. Disabled in CMYK |
| **Ink / Paper color** | Duotone pickers; editing either switches the preset to Custom. Disabled in CMYK |
| **Export PNG** | Download the working-resolution composite (`halftone-{mode}-{shape}.png`) |

### Defaults

- Sample: `02a.png` (auto-loaded)
- Mode: duotone
- Preset: Riso (`#1e1e78` ink, `#ff4682` paper)
- Cell size: 10 px
- Screen angle: 45°
- Dot shape: circle
- Contrast: 1.2

CMYK uses process inks cyan / magenta / yellow / black at 15° / 75° / 0° / 45° on white paper. Those angles and colors are not user-editable.

See [HOW-IT-WORKS.md](./HOW-IT-WORKS.md) for the math: dot-area tone, screen rotation and rosettes, CMYK separation, and how this differs from dithering.
