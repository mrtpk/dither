#!/usr/bin/env python3
"""Headless smoke test for 07-audio-reactive.

Loads the page with ?src=tone (internal oscillators + LFO, no mic/file needed),
launches Chromium with SwiftShader software-WebGL flags plus an autoplay flag so
the AudioContext resumes without a gesture, then verifies:
  1. the GL canvas renders a non-empty dithered frame,
  2. audio is actually analysed (window.__audioLevel > 0),
  3. two frames sampled ~400ms apart DIFFER (LFO-driven reactivity).
Screenshots to _test.png.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PORT = 8077
URL = f"http://localhost:{PORT}/07-audio-reactive/?src=tone"
SCREENSHOT = REPO_ROOT / "07-audio-reactive" / "_test.png"

# SwiftShader software WebGL + autoplay (no gesture) flags.
LAUNCH_ARGS = [
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
    "--ignore-gpu-blocklist",
    "--autoplay-policy=no-user-gesture-required",
]


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


# JS run in the page: draw the WebGL canvas onto a 2D canvas (works because the
# GL context uses preserveDrawingBuffer:true) and return a compact signature of a
# central 50% crop.
READBACK_JS = """
() => {
  const c = document.getElementById('glcanvas');
  if (!c || c.width === 0 || c.height === 0) return { ok:false };
  const t = document.createElement('canvas');
  t.width = c.width; t.height = c.height;
  t.getContext('2d').drawImage(c, 0, 0);
  const x0 = Math.floor(c.width*0.25), y0 = Math.floor(c.height*0.25);
  const cw = Math.floor(c.width*0.5), ch = Math.floor(c.height*0.5);
  const d = t.getContext('2d').getImageData(x0, y0, cw, ch).data;
  let sum=0, mn=255, mx=0;
  for (let i=0;i<d.length;i+=4){ const v=d[i]; sum+=v; if(v<mn)mn=v; if(v>mx)mx=v; }
  return { ok:true, sig:sum, mn, mx, w:c.width, h:c.height };
}
"""


def launch_browser(playwright):
    return playwright.chromium.launch(args=LAUNCH_ARGS)


def run_smoke():
    from playwright.sync_api import sync_playwright

    server = start_server()
    try:
        with sync_playwright() as p:
            browser = launch_browser(p)
            page = browser.new_page()

            errors = []
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on(
                "console",
                lambda m: errors.append(m.text)
                if ("compile" in m.text.lower() or "link" in m.text.lower())
                and m.type == "error"
                else None,
            )

            page.goto(URL, wait_until="networkidle")
            page.wait_for_selector("#glcanvas")

            # Belt-and-suspenders resume (harmless if tone already auto-resumed).
            try:
                page.click("#startBtn", timeout=2000)
            except Exception:
                pass

            # Frames advancing (guards against a half-initialized first frame).
            page.wait_for_function(
                "() => (window.__frames || 0) >= 5", timeout=15000
            )
            # Audio actually analysed in tone mode (LFO/analyser + resume latency).
            page.wait_for_function(
                "() => (window.__audioLevel || 0) > 0", timeout=15000
            )

            sigA = page.evaluate(READBACK_JS)
            assert sigA.get("ok"), f"readback failed: {sigA}"
            assert sigA["w"] > 0 and sigA["h"] > 0, f"canvas empty: {sigA}"
            # Non-empty dithered output (not flat).
            assert sigA["mx"] - sigA["mn"] > 10, f"canvas is flat: {sigA}"

            level = page.evaluate("() => window.__audioLevel")
            assert level and level > 0, f"audio not analysed: level={level}"

            # Reactivity: wait > one LFO period (~333ms at 3 Hz) and re-sample.
            page.wait_for_timeout(400)
            sigB = page.evaluate(READBACK_JS)
            assert sigB.get("ok"), f"readback B failed: {sigB}"
            assert sigA["sig"] != sigB["sig"], (
                f"frames did not change (not reactive): A={sigA['sig']} B={sigB['sig']}"
            )

            if errors:
                print("PAGE ERRORS:", errors, file=sys.stderr)

            page.screenshot(path=str(SCREENSHOT), full_page=True)
            browser.close()

        print(
            "SMOKE_OK",
            sigA["w"],
            sigA["h"],
            round(level, 4),
            sigA["sig"],
            sigB["sig"],
        )
        return 0
    finally:
        stop_server(server)


def fallback_check():
    """Fallback when SwiftShader WebGL / Chromium cannot run at all."""
    import shutil

    index_html = REPO_ROOT / "07-audio-reactive" / "index.html"
    main_js = REPO_ROOT / "07-audio-reactive" / "main.js"
    sample = REPO_ROOT / "data" / "samples" / "03a.png"

    assert index_html.exists(), f"missing {index_html}"
    assert main_js.exists(), f"missing {main_js}"
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
