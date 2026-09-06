#!/usr/bin/env python3
"""Assert coordinator SVGs are real vector geometry (no raster embed)."""

from __future__ import annotations

import sys
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
RECT_SVG = HERE / "out" / "01a.svg"
DOTS_SVG = HERE / "out" / "01a-dots.svg"
PLATE_A = HERE / "out" / "02a_riso_blue.svg"
PLATE_B = HERE / "out" / "02a_riso_pink.svg"


def _is_tag(elem: ET.Element, name: str) -> bool:
    return elem.tag == name or elem.tag.endswith("}" + name)


def _count(root: ET.Element, name: str) -> int:
    return len(root.findall(f".//{{*}}{name}"))


def check_rect(path: Path) -> int:
    if not path.is_file():
        raise AssertionError(f"missing {path}")
    size = path.stat().st_size
    if size <= 200:
        raise AssertionError(f"{path} is too small ({size} bytes)")
    tree = ET.parse(path)
    root = tree.getroot()
    if not _is_tag(root, "svg"):
        raise AssertionError(f"root tag is not svg: {root.tag}")
    text = path.read_text(encoding="utf-8")
    if "<svg" not in text:
        raise AssertionError(f"{path} has no <svg opening")
    n_rect = _count(root, "rect")
    if n_rect < 50:
        raise AssertionError(f"{path}: expected >= 50 rects, got {n_rect}")
    if _count(root, "image") or "<image" in text:
        raise AssertionError(f"{path} embeds a raster <image>")
    if root.get("viewBox") is None:
        raise AssertionError(f"{path} missing viewBox")
    return n_rect


def check_dots(path: Path) -> int:
    if not path.is_file():
        raise AssertionError(f"missing {path}")
    size = path.stat().st_size
    if size <= 200:
        raise AssertionError(f"{path} is too small ({size} bytes)")
    tree = ET.parse(path)
    root = tree.getroot()
    if not _is_tag(root, "svg"):
        raise AssertionError(f"root tag is not svg: {root.tag}")
    text = path.read_text(encoding="utf-8")
    n_circle = _count(root, "circle")
    if n_circle < 20:
        raise AssertionError(f"{path}: expected >= 20 circles, got {n_circle}")
    if _count(root, "image") or "<image" in text:
        raise AssertionError(f"{path} embeds a raster <image>")
    return n_circle


def check_plates() -> tuple[int, int] | None:
    """Optional: riso --separate plates, if present."""
    if not PLATE_A.is_file() or not PLATE_B.is_file():
        return None
    counts: list[int] = []
    for path in (PLATE_A, PLATE_B):
        if path.stat().st_size <= 200:
            raise AssertionError(f"{path} is too small")
        root = ET.parse(path).getroot()
        if not _is_tag(root, "svg"):
            raise AssertionError(f"{path} root is not svg")
        text = path.read_text(encoding="utf-8")
        n_rect = _count(root, "rect")
        if n_rect < 50:
            raise AssertionError(f"{path}: expected >= 50 rects, got {n_rect}")
        if _count(root, "image") or "<image" in text:
            raise AssertionError(f"{path} embeds a raster <image>")
        if root.get("viewBox") is None:
            raise AssertionError(f"{path} missing viewBox")
        # plates: no paper fill group — only ink geometry
        if 'id="ink-' not in text:
            raise AssertionError(f"{path} missing ink group")
        counts.append(n_rect)
    return counts[0], counts[1]


def main() -> int:
    try:
        n_rect = check_rect(RECT_SVG)
        n_circle = check_dots(DOTS_SVG)
        plates = check_plates()
    except (AssertionError, ET.ParseError, OSError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"SVG_OK  rects={n_rect} circles={n_circle}")
    if plates is not None:
        print(f"SEPARATE_OK  {PLATE_A.name}={plates[0]} {PLATE_B.name}={plates[1]}")
    print("SMOKE_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
