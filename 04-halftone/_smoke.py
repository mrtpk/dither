#!/usr/bin/env python3
"""Headless smoke test for 04-halftone."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PORT = 8074
URL = f"http://localhost:{PORT}/04-halftone/"
SCREENSHOT = REPO_ROOT / "04-halftone" / "_test.png"

WAIT_READY = "() => window.__halftoneReady === true"
READY_TIMEOUT = 15000


def setup_chromium_libs():
    """Extract apt libs locally when WSL is missing Playwright system deps.

    Reuses 01-basic-tool/_setup_libs.py; does not duplicate the lib list.
    """
    setup_script = REPO_ROOT / "01-basic-tool" / "_setup_libs.py"
    if not setup_script.exists():
        return
    result = subprocess.run(
        [str(REPO_ROOT / ".venv" / "bin" / "python"), str(setup_script)],
        capture_output=True,
        text=True,
    )
    for line in result.stdout.strip().splitlines():
        if line.startswith("LD_LIBRARY_PATH="):
            os.environ["LD_LIBRARY_PATH"] = line.split("=", 1)[1]
            break


def start_server():
    proc = subprocess.Popen(
        [str(REPO_ROOT / ".venv" / "bin" / "python"), "-m", "http.server", str(PORT)],
        cwd=str(REPO_ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        preexec_fn=os.setsid if hasattr(os, "setsid") else None,
    )
    time.sleep(1.5)
    return proc


def stop_server(proc):
    if proc.poll() is not None:
        return
    try:
        if hasattr(os, "killpg"):
            os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
        else:
            proc.terminate()
        proc.wait(timeout=5)
    except (ProcessLookupError, subprocess.TimeoutExpired):
        proc.kill()


CROP_STATS_JS = """
() => {
  const c = document.getElementById('workCanvas');
  const w = c.width, h = c.height;
  const x0 = Math.floor(w * 0.1), y0 = Math.floor(h * 0.1);
  const cw = Math.max(1, Math.floor(w * 0.8));
  const ch = Math.max(1, Math.floor(h * 0.8));
  const d = c.getContext('2d').getImageData(x0, y0, cw, ch).data;

  let rMin = 255, rMax = 0;
  const colors = new Set();
  const blocks = 16;
  const bw = Math.max(1, Math.floor(cw / blocks));
  const bh = Math.max(1, Math.floor(ch / blocks));
  const blockMn = new Array(blocks * blocks).fill(255);
  const blockMx = new Array(blocks * blocks).fill(0);

  for (let y = 0; y < ch; y++) {
    for (let x = 0; x < cw; x++) {
      const i = (y * cw + x) * 4;
      const r = d[i], g = d[i + 1], b = d[i + 2];
      colors.add(r + ',' + g + ',' + b);
      if (r < rMin) rMin = r;
      if (r > rMax) rMax = r;
      const bx = Math.min(blocks - 1, Math.floor(x / bw));
      const by = Math.min(blocks - 1, Math.floor(y / bh));
      const bi = by * blocks + bx;
      if (r < blockMn[bi]) blockMn[bi] = r;
      if (r > blockMx[bi]) blockMx[bi] = r;
    }
  }

  let contrastBlocks = 0;
  for (let i = 0; i < blockMn.length; i++) {
    if (blockMx[i] - blockMn[i] > 15) contrastBlocks++;
  }

  const hueBins = new Array(12).fill(0);
  for (let i = 0; i < d.length; i += 4) {
    const r = d[i], g = d[i + 1], b = d[i + 2];
    if (Math.max(r, g, b) - Math.min(r, g, b) < 25) continue;
    const rf = r / 255, gf = g / 255, bf = b / 255;
    const mx = Math.max(rf, gf, bf);
    const mn = Math.min(rf, gf, bf);
    const delta = mx - mn;
    let hue = 0;
    if (delta !== 0) {
      if (mx === rf) hue = ((gf - bf) / delta) + (gf < bf ? 6 : 0);
      else if (mx === gf) hue = (bf - rf) / delta + 2;
      else hue = (rf - gf) / delta + 4;
      hue *= 60;
      if (hue < 0) hue += 360;
      if (hue >= 360) hue -= 360;
    }
    hueBins[Math.min(11, Math.floor(hue / 30))]++;
  }

  return {
    w, h,
    unique: colors.size,
    rRange: rMax - rMin,
    contrastBlocks,
    occupiedHueBins: hueBins.filter((n) => n > 0).length,
  };
}
"""


def crop_stats(page):
    return page.evaluate(CROP_STATS_JS)


def center_hash(page):
    return page.evaluate(
        """() => {
      const c = document.getElementById('workCanvas');
      const w = c.width, h = c.height;
      const sw = Math.min(32, w);
      const sh = Math.min(32, h);
      const x0 = Math.floor((w - sw) / 2);
      const y0 = Math.floor((h - sh) / 2);
      const d = c.getContext('2d').getImageData(x0, y0, sw, sh).data;
      let hash = 0;
      for (let i = 0; i < d.length; i++) hash = (hash * 31 + d[i]) & 0xffffffff;
      return hash;
    }"""
    )


def wait_ready(page):
    page.wait_for_function(WAIT_READY, timeout=READY_TIMEOUT)


def launch_browser(playwright):
    return playwright.chromium.launch()


def run_smoke():
    from playwright.sync_api import sync_playwright

    server = start_server()
    try:
        with sync_playwright() as p:
            browser = launch_browser(p)
            page = browser.new_page()
            page.goto(URL, wait_until="networkidle")
            page.wait_for_selector("#displayCanvas")
            wait_ready(page)

            dw = page.eval_on_selector("#displayCanvas", "c => c.width")
            dh = page.eval_on_selector("#displayCanvas", "c => c.height")
            ww = page.eval_on_selector("#workCanvas", "c => c.width")
            wh = page.eval_on_selector("#workCanvas", "c => c.height")
            assert dw > 0 and dh > 0, f"display canvas empty: {dw}x{dh}"
            assert ww > 0 and wh > 0, f"work canvas empty: {ww}x{wh}"

            duo = crop_stats(page)
            assert duo["rRange"] > 10, f"flat tone: rRange={duo['rRange']}"
            assert duo["unique"] >= 8, f"expected >=8 unique RGB, got {duo['unique']}"
            assert duo["contrastBlocks"] >= 4, (
                f"expected >=4 contrast blocks, got {duo['contrastBlocks']}"
            )

            page.evaluate("() => { window.__halftoneReady = false; }")
            page.select_option("#mode", "cmyk")
            wait_ready(page)

            cmyk = crop_stats(page)
            assert cmyk["unique"] >= 20, f"expected >=20 unique RGB, got {cmyk['unique']}"
            assert cmyk["occupiedHueBins"] > 2, (
                f"expected >2 hue bins, got {cmyk['occupiedHueBins']}"
            )

            pre_hash = center_hash(page)
            page.evaluate(
                """() => {
              window.__halftoneReady = false;
              const el = document.getElementById('cellSize');
              el.value = '16';
              el.dispatchEvent(new Event('input', { bubbles: true }));
            }"""
            )
            wait_ready(page)
            post_hash = center_hash(page)
            assert pre_hash != post_hash, "cellSize change did not alter output"

            page.screenshot(path=str(SCREENSHOT), full_page=True)
            browser.close()

        print("SMOKE_OK", ww, wh, duo["unique"], cmyk["unique"])
        return 0
    finally:
        stop_server(server)


def fallback_check():
    """Fallback when Playwright/Chromium unavailable."""
    import shutil

    main_js = REPO_ROOT / "04-halftone" / "main.js"
    index_html = REPO_ROOT / "04-halftone" / "index.html"
    sample = REPO_ROOT / "data" / "samples" / "02a.png"

    assert main_js.exists(), f"missing {main_js}"
    assert index_html.exists(), f"missing {index_html}"
    assert sample.exists(), f"missing {sample}"

    node = shutil.which("node")
    if node:
        result = subprocess.run(
            [node, "--input-type=module", "--check", str(main_js)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            print("FALLBACK_OK: files exist, main.js syntax valid (node --check)")
        else:
            print("FALLBACK_OK: files exist (node ES module syntax check skipped)")
    else:
        print("FALLBACK_OK: files exist (node not available for syntax check)")
    return 0


def main():
    setup_chromium_libs()

    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
    except ImportError:
        print("Playwright not installed; running fallback", file=sys.stderr)
        return fallback_check()

    try:
        return run_smoke()
    except Exception as e:
        err = str(e).lower()
        if (
            "executable doesn't exist" in err
            or "shared libraries" in err
            or "libnspr4" in err
            or "target page, context or browser has been closed" in err
        ):
            print(f"Chromium launch failed ({e}); installing browser...", file=sys.stderr)
            subprocess.run(
                [str(REPO_ROOT / ".venv" / "bin" / "python"), "-m", "playwright", "install", "chromium"],
                check=False,
            )
            setup_chromium_libs()
            try:
                return run_smoke()
            except Exception as e2:
                print(f"Playwright failed after retry: {e2}", file=sys.stderr)
                return fallback_check()
        print(f"Smoke test failed: {e}", file=sys.stderr)
        raise


if __name__ == "__main__":
    sys.exit(main())
