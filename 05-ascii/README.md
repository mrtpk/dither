# 05 — ASCII Dither

A browser tool that converts a photograph into **ASCII art**: each grid cell is one character whose ink density approximates local brightness. Three glyph ramps (classic punctuation, Unicode blocks, audio-meter bars), optional Bayer pre-dithering, and dual output — copyable text or PNG export.

## Prerequisites

- WSL (Windows Subsystem for Linux)
- Python virtual environment at `.venv` in the repo root
- Sample image at `data/samples/01a.png`

## Run

From Windows, start a static file server via WSL (serve from the **repo root**, not this folder):

```bash
.venv/bin/python -m http.server 8000
```

Open in your browser:

```
http://localhost:8000/05-ascii/
```

Stop the server with `Ctrl+C` in the WSL terminal.

> **Note:** ES modules and image loading require HTTP — opening `index.html` directly as a `file://` URL will not work.

## How to use

On first load the tool automatically displays the sample image `01a.png` with 80 columns, classic ramp, dither on, and acid-green text on black.

### Controls

| Control | What it does |
|---------|--------------|
| **Load image** | Replace the sample with your own raster image |
| **Columns** | Output width in characters (20–300). More columns = finer detail |
| **Ramp** | **Classic** (` .:-=+*#%@`), **Blocks** (shade tiles), or **Audio meter** (bar glyphs) |
| **Contrast / Brightness** | Tone stretch and offset before character selection |
| **Invert** | Swap light and dark mapping |
| **Font size** | Glyph size for both text preview and canvas export (6–24 px) |
| **Foreground / Background** | Text and canvas colors |
| **Dither (Bayer)** | Ordered threshold perturbation before glyph snap; reduces banding |
| **Dither strength** | How strong the Bayer offset is (0–2); disabled when dither is off |
| **View: Text / Canvas** | Toggle between `<pre>` text and canvas PNG preview |
| **Copy text** | Copy the ASCII grid to the clipboard (text view only) |
| **Download PNG** | Export the canvas render (canvas view only) |

The grid readout shows source dimensions, output grid size, and total character count.

### Defaults

- Sample: `01a.png` (auto-loaded)
- Columns: 80
- Ramp: classic
- Contrast: 1.0, brightness: 0
- Dither: on (strength 0.8)
- Colors: `#d6ff00` on `#0a0a0a`
- View: text

See [HOW-IT-WORKS.md](./HOW-IT-WORKS.md) for luminance averaging, aspect-ratio correction, glyph quantization, and how optional Bayer relates to dithering.
