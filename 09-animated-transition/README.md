# 09 — Animated dither transition

Bayer-mask dissolve (A → B) or materialize (paper → dithered still), exported as **GIF**, **MP4**, or **WebM**. The wipe is the same ordered threshold field used for still Bayer dither — now driving which source is visible.

See [`HOW-IT-WORKS.md`](./HOW-IT-WORKS.md) for the mask math.

## Prerequisites

- WSL (or Linux) with the repo cloned
- Python virtualenv at `.venv` (from repo root: `python3 -m venv .venv && .venv/bin/pip install -r requirements.txt`). Needs `numpy`, `Pillow`, `imageio`, and `imageio-ffmpeg`.
- Sample images: `.venv/bin/python shared/make_samples.py` (creates `data/samples/*.png`)

Always run with `.venv/bin/python` from the **repo root**. Do not use Windows `py` or system `python` for this folder.

```bash
cd /path/to/dither
```

## Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--a` | *(required)* | Image A (dissolve from / materialize source). Must exist. |
| `--b` | omitted | Image B (dissolve to). Omit → single-image **materialize**. |
| `--output` | *(required)* | Output file. Parent dirs are created. Suffix may pick format. |
| `--format` | infer | `gif`, `mp4`, or `webm`. Overrides the suffix when set. No suffix → `gif`. |
| `--frames` | `24` | Frame count `N` (≥ 2). Inclusive endpoints: first = full A/paper, last = full B/picture. |
| `--fps` | `12` | Frame rate. GIF delay = `1/fps` seconds. Wall time ≈ `N / fps`. |
| `--bayer-n` | `8` | Bayer order for the wipe **and** source dither (power of two ≥ 2). Distinct wipe steps ≈ `n²`. `--frames` > `n² + 1` repeats some masks; default 8 (64 ranks) is enough for 24 frames. |
| `--palette` | `bw` | `bw`, `ink_on_white`, `gameboy`, `loud_neon`, `riso`, `amber`. Used for pre-dither and per-frame snap. |
| `--max-dim` | `256` | Long-edge cap on load (LANCZOS). `0` = no load cap. |
| `--cells` | omitted | Working-grid long edge after load (NEAREST, ≥ 8). Keeps GIF/video small. If set, this wins over `--max-dim` for the working size. |
| `--mode` | auto | `dissolve` or `materialize`. Auto: dissolve if `--b` is set, else materialize. |
| `--contrast` | `1.0` | Contrast multiplier before dither / compose. |
| `--no-pre-dither` | off | Compose contrast-adjusted raw A/B; still snap each frame to the palette. Materialize target stays dithered. |

`--mode dissolve` without `--b` is an error. `--mode materialize` with `--b` warns and ignores `--b`.

B is always resized to **A’s** width × height (LANCZOS) before the wipe. Size knobs (`--max-dim`, `--cells`) matter: every frame is a full compose + snap.

**GIF size:** `--max-dim 256` or `--cells 160`. **MP4** can use `--max-dim 480`.

## Examples

**Dissolve 01a → 02a, looping GIF**

```bash
.venv/bin/python 09-animated-transition/dither_anim.py \
  --a data/samples/01a.png \
  --b data/samples/02a.png \
  --output 09-animated-transition/out/anim.gif \
  --frames 20
```

**Same wipe, more ranks / slower**

```bash
.venv/bin/python 09-animated-transition/dither_anim.py \
  --a data/samples/01a.png --b data/samples/02a.png \
  --output 09-animated-transition/out/dissolve.gif \
  --frames 32 --fps 10 --bayer-n 8 --palette bw --max-dim 256
```

**Materialize a single still** (`--b` omitted → materialize; `--mode` optional)

```bash
.venv/bin/python 09-animated-transition/dither_anim.py \
  --a data/samples/01a.png \
  --output 09-animated-transition/out/materialize.gif \
  --frames 24 --palette ink_on_white --cells 160
```

**MP4** (and WebM if ffmpeg supports VP9)

```bash
.venv/bin/python 09-animated-transition/dither_anim.py \
  --a data/samples/01a.png --b data/samples/02a.png \
  --output 09-animated-transition/out/anim.mp4 \
  --frames 24 --fps 12 --max-dim 320
```

Exit `0` on success, `2` on bad arguments / unreadable images, `1` if every encode fallback fails.

## How to view

- **GIF:** open `09-animated-transition/out/anim.gif` in a browser, VS Code, or Windows Photos (`explorer.exe` on the Windows path). A looping GIF **jumps** from the last frame back to the first (full B → full A).
- **MP4:** browser or VLC.
- **WebM:** Chrome / Firefox. If VP9 is missing, the CLI falls back **WebM → MP4 → GIF** and prints a warning; open the **actual** path printed on stdout. Video writers need even width and height — the CLI pads by repeating the last row/column (GIF is not padded).

GIF is the right default for this look. Dither noise compresses poorly in H.264 / VP9 compared with a 2–4 color GIF.
