# 01 — Basic Dither Tool

A browser-based image dithering tool. Load a photo, pick an algorithm and palette, tweak sliders, and download the result as a PNG.

## Prerequisites

- WSL (Windows Subsystem for Linux)
- This repo cloned locally
- Python virtual environment at `.venv` in the repo root

## Run

From Windows, start a static file server via WSL (serve from the **repo root**, not this folder):

```bash
.venv/bin/python -m http.server 8000
```

Open in your browser:

```
http://localhost:8000/01-basic-tool/
```

Stop the server with `Ctrl+C` in the WSL terminal.

> **Note:** ES modules and image loading require HTTP — opening `index.html` directly as a `file://` URL will not work.

## How to use

On first load the tool automatically displays the sample image `01a.png`.

### Controls

| Control | What it does |
|---------|--------------|
| **Load image** | Replace the sample with your own raster image (PNG, JPG, etc.) |
| **Algorithm** | Dithering method — error diffusion (Floyd–Steinberg, Atkinson, Jarvis–Judice–Ninke), ordered Bayer matrices, or flat threshold |
| **Palette** | Color set to quantize into — from simple black & white to Game Boy greens, neon pairs, or CMYK |
| **Contrast** | Stretch midtones (0.25 = flat, 3.0 = harsh) |
| **Brightness** | Shift all tones lighter or darker (−128 to +128) |
| **Pixel scale** | Downscale before dithering — higher values produce larger visible blocks (1 = full resolution) |
| **Strength** | Bayer pattern intensity (only active for Bayer algorithms) |
| **Invert** | Flip to a photographic negative before dithering |
| **Download PNG** | Save the dithered image at native resolution (not the upscaled preview) |

Adjust any control and the preview updates live. The size readout under the preview shows source dimensions → dither grid size (e.g. `683 × 1024 → 171 × 256` when pixel scale is 4).
