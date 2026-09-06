"""Downscale the large source PNGs in data/ into data/samples/ for fast tests.

Run: .venv/bin/python shared/make_samples.py
"""

import os
from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data")
DST = os.path.join(SRC, "samples")
MAX_DIM = 1024

os.makedirs(DST, exist_ok=True)

count = 0
for name in sorted(os.listdir(SRC)):
    path = os.path.join(SRC, name)
    if not os.path.isfile(path):
        continue
    if not name.lower().endswith((".png", ".jpg", ".jpeg", ".webp", ".bmp")):
        continue
    try:
        img = Image.open(path).convert("RGB")
    except Exception as e:  # noqa: BLE001
        print(f"skip {name}: {e}")
        continue
    if max(img.size) > MAX_DIM:
        scale = MAX_DIM / max(img.size)
        img = img.resize((round(img.width * scale), round(img.height * scale)), Image.LANCZOS)
    out = os.path.join(DST, os.path.splitext(name)[0] + ".png")
    img.save(out)
    count += 1
    print(f"wrote {out} ({img.width}x{img.height})")

print(f"done: {count} sample(s)")
