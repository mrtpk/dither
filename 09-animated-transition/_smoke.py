#!/usr/bin/env python3
"""Coordinator smoke test for 09-animated-transition."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import imageio.v2 as imageio
import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from shared import pydither as pd  # noqa: E402

PYTHON = ROOT / ".venv" / "bin" / "python"
CLI = ROOT / "09-animated-transition" / "dither_anim.py"
SAMPLES = ROOT / "data" / "samples"
OUT_GIF = ROOT / "09-animated-transition" / "out" / "anim.gif"
OUT_MP4 = ROOT / "09-animated-transition" / "out" / "anim.mp4"
TEST_PNG = ROOT / "09-animated-transition" / "_test.png"
A_PATH = SAMPLES / "01a.png"
B_PATH = SAMPLES / "02a.png"


def _run(cmd: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True)
    if result.stdout:
        print(result.stdout, end="")
    if result.stderr:
        print(result.stderr, end="", file=sys.stderr)
    return result


def _count_frames(path: Path) -> tuple[int, list[np.ndarray]]:
    try:
        reader = imageio.get_reader(path)
        frames = [np.asarray(f) for f in reader]
        try:
            length = int(reader.get_length())
        except Exception:  # noqa: BLE001
            length = len(frames)
        if length <= 1 and len(frames) > 1:
            length = len(frames)
        return length, frames
    except Exception:  # noqa: BLE001
        pass

    with Image.open(path) as img:
        n = getattr(img, "n_frames", 1)
        frames = []
        for i in range(n):
            img.seek(i)
            frames.append(np.asarray(img.convert("RGB")))
        return n, frames


def _mae(a: np.ndarray, b: np.ndarray) -> float:
    aa = np.asarray(a, dtype=np.int16)[..., :3]
    bb = np.asarray(b, dtype=np.int16)[..., :3]
    if aa.shape != bb.shape:
        bb = np.asarray(
            Image.fromarray(bb.astype(np.uint8)).resize((aa.shape[1], aa.shape[0]), Image.NEAREST),
            dtype=np.int16,
        )
    return float(np.mean(np.abs(aa - bb)))


def _expected_ab() -> tuple[np.ndarray, np.ndarray]:
    a = pd.load_image(str(A_PATH), max_dim=256)
    b = pd.load_image(str(B_PATH), max_dim=256)
    if b.shape[:2] != a.shape[:2]:
        b = np.asarray(
            Image.fromarray(b).resize((a.shape[1], a.shape[0]), Image.LANCZOS),
            dtype=np.uint8,
        )
    pal = pd.PALETTES["bw"]
    a_d = pd.dither(a, algorithm="bayer", palette=pal, contrast=1.0, grayscale=True, bayer_n=8)
    b_d = pd.dither(b, algorithm="bayer", palette=pal, contrast=1.0, grayscale=True, bayer_n=8)
    return a_d, b_d


def _ffmpeg_available() -> bool:
    try:
        import imageio_ffmpeg

        exe = imageio_ffmpeg.get_ffmpeg_exe()
        return bool(exe)
    except Exception:  # noqa: BLE001
        return False


def assert_gif() -> int:
    if not OUT_GIF.is_file():
        print(f"GIF missing: {OUT_GIF}", file=sys.stderr)
        return 1
    size = OUT_GIF.stat().st_size
    if size <= 100:
        print(f"GIF too small: {OUT_GIF} ({size} bytes)", file=sys.stderr)
        return 1

    nframes, frames = _count_frames(OUT_GIF)
    if nframes <= 1 or len(frames) <= 1:
        print(f"GIF has only {nframes} frame(s)", file=sys.stderr)
        return 1
    if nframes < 18:
        print(f"GIF frame count too low: {nframes} (expected ~20)", file=sys.stderr)
        return 1

    first = frames[0]
    last = frames[-1]
    mid = frames[len(frames) // 2]
    Image.fromarray(np.asarray(mid[..., :3], dtype=np.uint8)).save(TEST_PNG)

    if _mae(first, last) < 5.0:
        print("First and last GIF frames are too similar (expected A vs B)", file=sys.stderr)
        return 1

    a_d, b_d = _expected_ab()
    first_a = _mae(first, a_d)
    first_b = _mae(first, b_d)
    last_a = _mae(last, a_d)
    last_b = _mae(last, b_d)
    if first_a >= first_b or first_a > 20.0:
        print(
            f"First frame is not ~A (mae A={first_a:.2f} B={first_b:.2f})",
            file=sys.stderr,
        )
        return 1
    if last_b >= last_a or last_b > 20.0:
        print(
            f"Last frame is not ~B (mae A={last_a:.2f} B={last_b:.2f})",
            file=sys.stderr,
        )
        return 1

    print(f"ANIM_OK {nframes}")
    print("SMOKE_OK")
    return 0


def try_mp4() -> None:
    if not _ffmpeg_available():
        print("ANIM_MP4_SKIP")
        return

    result = _run(
        [
            str(PYTHON),
            str(CLI),
            "--a",
            str(A_PATH),
            "--b",
            str(B_PATH),
            "--output",
            str(OUT_MP4),
            "--frames",
            "8",
            "--fps",
            "12",
            "--max-dim",
            "128",
        ]
    )
    if result.returncode != 0:
        print("ANIM_MP4_SKIP")
        return
    if not OUT_MP4.is_file() or OUT_MP4.stat().st_size <= 100:
        print("ANIM_MP4_SKIP")
        return
    try:
        nframes, frames = _count_frames(OUT_MP4)
        if nframes <= 1 and len(frames) <= 1:
            print("ANIM_MP4_SKIP")
            return
    except Exception:  # noqa: BLE001
        print("ANIM_MP4_SKIP")
        return
    print(f"ANIM_MP4_OK {max(nframes, len(frames))}")


def main() -> int:
    if not A_PATH.is_file() or not B_PATH.is_file():
        print(
            f"Missing samples; run: .venv/bin/python shared/make_samples.py",
            file=sys.stderr,
        )
        return 1

    result = _run(
        [
            str(PYTHON),
            str(CLI),
            "--a",
            str(A_PATH),
            "--b",
            str(B_PATH),
            "--output",
            str(OUT_GIF),
            "--frames",
            "20",
        ]
    )
    if result.returncode != 0:
        print(f"CLI exited with {result.returncode}", file=sys.stderr)
        return 1

    code = assert_gif()
    if code != 0:
        return code

    try_mp4()
    return 0


if __name__ == "__main__":
    sys.exit(main())
