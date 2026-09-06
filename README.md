# Dither — a collection of dithering use cases

Eleven self-contained dithering use cases, each in its own folder, sharing a
common engine. Browser use cases are vanilla JS (Canvas/WebGL, no build step);
headless/print/ML use cases are Python running in a root `.venv` on WSL.

## Layout

```
dither/
├── data/                 # source images (+ data/samples/ downscaled for tests)
├── shared/               # reusable engines
│   ├── dither.js         #   JS: Bayer, Floyd-Steinberg, Atkinson, palette snap
│   ├── palettes.js       #   JS: named + two-tone palettes
│   └── pydither/         #   Python: numpy-vectorized port of the same engine
├── 01-basic-tool/        # image -> dither -> export (browser)
├── 02-two-tone-brand/    # screenprint two-tone look (browser)
├── 03-realtime-webcam/   # live 1-bit webcam via WebGL (browser)
├── 04-halftone/          # CMYK / Riso rotated dot screens (browser)
├── 05-ascii/             # brightness -> characters (browser)
├── 06-cli-batch/         # headless folder-to-folder batch (Python)
├── 07-audio-reactive/    # dither driven by mic/track (browser)
├── 08-vector-svg/        # dither -> real SVG for screenprint (Python)
├── 09-animated-transition/ # Bayer dissolve between images -> GIF/WebM (Python)
├── 10-blue-noise/        # void-and-cluster blue-noise dithering (Python)
└── 11-depth-aware/       # depth-map-driven dither density (Python + torch)
```

Each folder contains its own `README.md` (how to run) and `HOW-IT-WORKS.md`
(the math/tech behind the technique).

## Setup (WSL)

```bash
cd /path/to/dither
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python shared/make_samples.py    # build data/samples/
```

## Running

- Browser use cases: serve the repo root and open the folder's `index.html`:
  ```bash
  .venv/bin/python -m http.server 8000
  # then open http://localhost:8000/01-basic-tool/
  ```
- Python use cases: see each folder's `README.md` for exact commands.

## Data

`data/` holds a few JPEG source photos (each < 1 MB). `data/samples/` contains
downscaled PNG copies used by the demos and tests; regenerate them any time with
`.venv/bin/python shared/make_samples.py`.

## License

Released under the [MIT License](LICENSE).
