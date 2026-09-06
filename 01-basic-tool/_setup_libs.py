#!/usr/bin/env python3
"""Setup local lib path for Playwright Chromium on WSL without sudo."""

import glob
import os
import subprocess
import sys
from pathlib import Path

CACHE = Path("/tmp/dither-playwright-libs")
CACHE.mkdir(exist_ok=True)

PACKAGES = [
    "libnspr4",
    "libnss3",
    "libatk1.0-0",
    "libatk-bridge2.0-0",
    "libcups2",
    "libdrm2",
    "libxkbcommon0",
    "libxcomposite1",
    "libxdamage1",
    "libxfixes3",
    "libxrandr2",
    "libgbm1",
    "libasound2t64",
    "libasound2",
]


def download_and_extract():
    lib_dirs = []
    for pkg in PACKAGES:
        deb_pattern = str(CACHE / f"{pkg}*.deb")
        if not glob.glob(deb_pattern):
            r = subprocess.run(
                ["apt-get", "download", pkg],
                cwd=str(CACHE),
                capture_output=True,
                text=True,
            )
            if r.returncode != 0:
                continue
        for deb in glob.glob(deb_pattern):
            extract = CACHE / deb.replace(".deb", "").split("/")[-1]
            extract.mkdir(exist_ok=True)
            subprocess.run(
                ["dpkg-deb", "-x", deb, str(extract)],
                check=False,
            )
            for sub in ("usr/lib/x86_64-linux-gnu", "usr/lib"):
                p = extract / sub
                if p.is_dir():
                    lib_dirs.append(str(p))
    return lib_dirs


def main():
    lib_dirs = download_and_extract()
    if not lib_dirs:
        print("NO_LIBS", file=sys.stderr)
        return 1
    existing = os.environ.get("LD_LIBRARY_PATH", "")
    os.environ["LD_LIBRARY_PATH"] = ":".join(lib_dirs + ([existing] if existing else []))
    print("LD_LIBRARY_PATH=" + os.environ["LD_LIBRARY_PATH"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
