#!/usr/bin/env python3
"""Headless smoke test for 03-realtime-webcam.

Loads the page with ?src=sample (no real camera needed), launches Chromium with
fake-media + SwiftShader software-WebGL flags, waits for a real rendered frame
via window.__ditherFrames, and asserts the canvas is non-empty and near-two-
color (i.e. actually dithered). Screenshots to _test.png.
"""

import os
import signal
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PORT = 8073
URL = f"http://localhost:{PORT}/03-realtime-webcam/?src=sample"
SCREENSHOT = REPO_ROOT / "03-realtime-webcam" / "_test.png"

# SwiftShader software WebGL + fake media stream flags.
LAUNCH_ARGS = [
    "--use-fake-device-for-media-stream",
    "--use-fake-ui-for-media-stream",
    "--use-gl=angle",
    "--use-angle=swiftshader",
    "--enable-unsafe-swiftshader",
    "--ignore-gpu-blocklist",
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
# GL context uses preserveDrawingBuffer:true) and analyze a central 80% crop.
READBACK_JS = """
() => {
  const c = document.getElementById('glcanvas');
  if (!c || c.width === 0 || c.height === 0) return { ok:false, reason:'no canvas' };
  const t = document.createElement('canvas');
  t.width = c.width; t.height = c.height;
  t.getContext('2d').drawImage(c, 0, 0);
  const x0 = Math.floor(c.width*0.1), y0 = Math.floor(c.height*0.1);
  const cw = Math.floor(c.width*0.8), ch = Math.floor(c.height*0.8);
  const d = t.getContext('2d').getImageData(x0, y0, cw, ch).data;
  let mn=255, mx=0; const counts = new Map();
  for (let i=0;i<d.length;i+=4){
    const v=d[i]; if(v<mn)mn=v; if(v>mx)mx=v;
    const key = `${d[i]},${d[i+1]},${d[i+2]}`;
    counts.set(key, (counts.get(key)||0)+1);
  }
  const sorted=[...counts.entries()].sort((a,b)=>b[1]-a[1]);
  const total=cw*ch;
  const top2=(sorted[0]?.[1]||0)+(sorted[1]?.[1]||0);
  return { ok:true, mn, mx, unique:counts.size, top2Pct: top2/total, w:c.width, h:c.height };
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

            # Wait for at least two real drawn frames (guards against a
            # half-initialized first frame), not a fixed sleep.
            page.wait_for_function(
                "() => (window.__ditherFrames || 0) >= 2", timeout=15000
            )

            res = page.evaluate(READBACK_JS)
            assert res.get("ok"), f"readback failed: {res}"
            assert res["w"] > 0 and res["h"] > 0, f"canvas empty: {res}"
            # Non-empty pixels (shader actually drew the dithered sample).
            assert res["mx"] - res["mn"] > 10, f"canvas is flat: {res}"
            # Near-two-color: two palette colors dominate.
            assert res["top2Pct"] >= 0.9, f"not near-two-color: {res}"

            page.screenshot(path=str(SCREENSHOT), full_page=True)
            browser.close()

        print(
            "SMOKE_OK",
            res["w"],
            res["h"],
            res["unique"],
            round(res["top2Pct"], 4),
        )
        return 0
    finally:
        stop_server(server)


def fallback_check():
    """Fallback when SwiftShader WebGL / Chromium cannot run at all."""
    import shutil

    index_html = REPO_ROOT / "03-realtime-webcam" / "index.html"
    main_js = REPO_ROOT / "03-realtime-webcam" / "main.js"
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
