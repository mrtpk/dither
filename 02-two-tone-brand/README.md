# 02 — Two-Tone Brand Poster

A browser-based poster tool for high-contrast, screenprint-style art. Map photos to a two-color brand palette (ink + ground), add optional headline and meter-bar overlays, and export a composed PNG.

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
http://localhost:8000/02-two-tone-brand/
```

Stop the server with `Ctrl+C` in the WSL terminal.

> **Note:** ES modules and image loading require HTTP — opening `index.html` directly as a `file://` URL will not work.

## How to use

On first load the tool automatically displays the sample image `02a.png` with the **Loud Neon** preset (black ink on acid green), **Bayer 4×4** dithering, high contrast (2.25), and pixel scale 6.

### Controls

| Control | What it does |
|---------|--------------|
| **Load image** | Replace the sample with your own raster image |
| **Brand preset** | Seed ink and ground from Loud Neon, Loud Red, Riso, Amber, or Custom |
| **Ink / Ground color** | Pick the two palette colors; manual edits switch preset to Custom |
| **Algorithm** | Dithering method — error diffusion, Bayer matrices, or threshold |
| **Contrast** | Stretch midtones (0.5–4.0; default 2.25 for poster punch) |
| **Pixel scale** | Block size before dither (1–16; default 6 for chunky cells) |
| **Strength** | Bayer threshold intensity (disabled for non-Bayer algorithms) |
| **Show overlay** | Toggle headline band and meter bars |
| **Headline** | Uppercase text on a ground-colored bottom band (when overlay on) |
| **Meter bars** | Seven pseudo-random vertical bars on the right edge (when overlay on) |
| **Export PNG** | Download the composed poster at native resolution |

### Defaults

- Sample: `02a.png`
- Preset: Loud Neon (`#0a0a0a` ink, `#d6ff00` ground)
- Algorithm: Bayer 4×4
- Contrast: 2.25
- Pixel scale: 6
- Overlay: on (headline + meter bars)

See [HOW-IT-WORKS.md](./HOW-IT-WORKS.md) for the math and visual concepts behind two-tone dithering.
