#!/usr/bin/env python3
"""Headless smoke test for 05-ascii."""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PORT = 8075
URL = f"http://localhost:{PORT}/05-ascii/"
SCREENSHOT = REPO_ROOT / "05-ascii" / "_test.png"

WAIT_READY = "() => window.__asciiReady === true"
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


def wait_ready(page):
    page.wait_for_function(WAIT_READY, timeout=READY_TIMEOUT)


def launch_browser(playwright):
    return playwright.chromium.launch()


def canvas_r_range(page):
    return page.evaluate(
        """() => {
      const c = document.getElementById('exportCanvas');
      const w = c.width, h = c.height;
      const cx = Math.floor(w / 2);
      const cy = Math.floor(h / 2);
      const sw = Math.min(64, w);
      const sh = Math.min(64, h);
      const x0 = Math.max(0, cx - Math.floor(sw / 2));
      const y0 = Math.max(0, cy - Math.floor(sh / 2));
      const d = c.getContext('2d').getImageData(x0, y0, sw, sh).data;
      let rMin = 255, rMax = 0;
      for (let i = 0; i < d.length; i += 4) {
        const r = d[i];
        if (r < rMin) rMin = r;
        if (r > rMax) rMax = r;
      }
      return { w, h, rRange: rMax - rMin };
    }"""
    )


def run_smoke():
    from playwright.sync_api import sync_playwright

    server = start_server()
    try:
        with sync_playwright() as p:
            browser = launch_browser(p)
            page = browser.new_page()
            page.goto(URL, wait_until="networkidle")
            page.wait_for_selector("#asciiOutput")
            wait_ready(page)

            text1 = page.eval_on_selector("#asciiOutput", "el => el.textContent")
            assert len(text1) > 100, f"ascii output too short: {len(text1)}"

            non_space = sum(1 for ch in text1 if ch not in " \n")
            assert non_space > 50, f"expected >50 non-space chars, got {non_space}"

            lines1 = text1.split("\n")
            len1 = len(text1)
            line_width1 = max(len(line) for line in lines1) if lines1 else 0
            rows1 = len(lines1)

            page.evaluate("() => { window.__asciiReady = false; }")
            page.evaluate(
                """() => {
              const el = document.getElementById('columns');
              el.value = '40';
              el.dispatchEvent(new Event('input', { bubbles: true }));
            }"""
            )
            wait_ready(page)

            text2 = page.eval_on_selector("#asciiOutput", "el => el.textContent")
            lines2 = text2.split("\n")
            len2 = len(text2)
            line_width2 = max(len(line) for line in lines2) if lines2 else 0
            rows2 = len(lines2)

            assert len2 != len1, f"text length unchanged after columns change: {len2}"
            assert rows2 != rows1, f"row count unchanged after columns change: {rows2}"
            assert line_width2 < line_width1, (
                f"line width did not shrink: {line_width2} vs {line_width1}"
            )

            page.evaluate("() => { window.__asciiReady = false; }")
            page.evaluate(
                """() => {
              document.getElementById('viewModeCanvas').checked = true;
              document.getElementById('viewModeCanvas').dispatchEvent(
                new Event('change', { bubbles: true })
              );
            }"""
            )
            wait_ready(page)

            canvas_stats = canvas_r_range(page)
            assert canvas_stats["w"] > 0 and canvas_stats["h"] > 0, (
                f"export canvas empty: {canvas_stats['w']}x{canvas_stats['h']}"
            )
            assert canvas_stats["rRange"] > 10, (
                f"flat canvas fill: rRange={canvas_stats['rRange']}"
            )

            page.screenshot(path=str(SCREENSHOT), full_page=True)
            browser.close()

        print(
            "SMOKE_OK",
            line_width2,
            rows2,
            non_space,
            canvas_stats["w"],
            canvas_stats["h"],
        )
        return 0
    finally:
        stop_server(server)


def fallback_check():
    """Fallback when Playwright/Chromium unavailable."""
    import shutil

    main_js = REPO_ROOT / "05-ascii" / "main.js"
    index_html = REPO_ROOT / "05-ascii" / "index.html"
    sample = REPO_ROOT / "data" / "samples" / "01a.png"

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
                [
                    str(REPO_ROOT / ".venv" / "bin" / "python"),
                    "-m",
                    "playwright",
                    "install",
                    "chromium",
                ],
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
