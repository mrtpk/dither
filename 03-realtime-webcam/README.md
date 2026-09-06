# 03 — Realtime Webcam Dither

A live, real-time two-tone **Bayer-dithered webcam feed** rendered by a WebGL
fragment shader (the GPU path). `getUserMedia` → `<video>` → per-frame GPU
texture → shader (luminance → contrast → Bayer threshold → two-tone mix) →
`<canvas>`, at ~60 fps. Vanilla JS + WebGL, no build step.

See [HOW-IT-WORKS.md](./HOW-IT-WORKS.md) for the math and the reasoning behind
using ordered (Bayer) dithering on the GPU.

## Prerequisites

- WSL with the project's `.venv` (used to serve files and run the smoke test).
- The sample image `data/samples/03a.png` must exist (used by the no-camera
  fallback and the test).

## Run

Serve from the **repo root** so `../shared/` and `../data/samples/03a.png`
resolve:

```bash
.venv/bin/python -m http.server 8000
```

Then open:

```
http://localhost:8000/03-realtime-webcam/
```

- The browser will prompt for **camera permission** — allow it to see the live
  dithered feed.
- Stop the server with `Ctrl+C`.

### No-camera / testing fallback

To force the no-camera path (or on machines without a webcam), add `?src=sample`
to load `../data/samples/03a.png` instead of the camera:

```
http://localhost:8000/03-realtime-webcam/?src=sample
```

The render loop keeps running on the static image, so all controls stay live.

## Controls

| Control | What it does |
|---------|--------------|
| **Bayer size** | Threshold matrix size: `2×2`, `4×4`, `8×8`. Larger = finer tonal gradations. |
| **Contrast** | Midpoint stretch around mid-gray (0.5 – 4.0). Higher = punchier 1-bit look. |
| **Pixel scale** | Block size in device pixels (1 – 16). Higher = chunkier, low-res look. |
| **Ink** | Color for pixels darker than their threshold. |
| **Ground** | Color for pixels brighter than their threshold. |
| **Snapshot PNG** | Downloads the current canvas as a PNG. |
| **Record** *(optional)* | Records the canvas to a `.webm` clip if the browser supports `captureStream` + `MediaRecorder`; hidden otherwise. |

Controls update the running render loop every frame — no manual re-render.

## Suggested palette presets

Hex pairs borrowed from `shared/palettes.js` (ink / ground):

| Preset | Ink | Ground |
|--------|-----|--------|
| **bw** | `#000000` | `#ffffff` |
| **loudNeon** | `#0a0a0a` | `#d6ff00` |
| **amber** | `#140c00` | `#ffb000` |

Defaults: Bayer `4×4`, contrast `1.4`, pixel scale `1`, ink `#0a0a0a`, ground
`#f5f5f5`.

## Test

Headless smoke test (self-starts a server on port 8073, loads `?src=sample`,
asserts the canvas renders a non-empty, near-two-color dithered image, and
writes `_test.png`):

```bash
.venv/bin/python 03-realtime-webcam/_smoke.py
```
