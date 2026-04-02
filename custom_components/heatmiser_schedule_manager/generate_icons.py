#!/usr/bin/env python3
"""Generate icon.png and logo.png from SVG sources.

Run this once on any machine with Python and cairosvg installed:
    pip install cairosvg
    python3 generate_icons.py

The generated PNGs are committed to the repo alongside the SVG sources.
HA requires icon.png (256×256) to show the brand icon in the integrations UI.
HACS displays logo.png in the store listing.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent


def _try_cairosvg() -> bool:
    try:
        import cairosvg  # noqa: PLC0415
    except ImportError:
        return False

    cairosvg.svg2png(
        url=str(HERE / "icon.svg"),
        write_to=str(HERE / "icon.png"),
        output_width=256,
        output_height=256,
    )
    print("icon.png written (256×256)")

    cairosvg.svg2png(
        url=str(HERE / "logo.svg"),
        write_to=str(HERE / "logo.png"),
        output_width=600,
        output_height=200,
    )
    print("logo.png written (600×200)")
    return True


def _try_inkscape() -> bool:
    try:
        subprocess.run(["inkscape", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False

    subprocess.run(
        ["inkscape", str(HERE / "icon.svg"),
         "--export-filename", str(HERE / "icon.png"),
         "--export-width", "256", "--export-height", "256"],
        check=True,
    )
    print("icon.png written via Inkscape")

    subprocess.run(
        ["inkscape", str(HERE / "logo.svg"),
         "--export-filename", str(HERE / "logo.png"),
         "--export-width", "600", "--export-height", "200"],
        check=True,
    )
    print("logo.png written via Inkscape")
    return True


def _try_rsvg() -> bool:
    try:
        subprocess.run(["rsvg-convert", "--version"], capture_output=True, check=True)
    except (FileNotFoundError, subprocess.CalledProcessError):
        return False

    subprocess.run(
        ["rsvg-convert", "-w", "256", "-h", "256",
         str(HERE / "icon.svg"), "-o", str(HERE / "icon.png")],
        check=True,
    )
    print("icon.png written via rsvg-convert")

    subprocess.run(
        ["rsvg-convert", "-w", "600", "-h", "200",
         str(HERE / "logo.svg"), "-o", str(HERE / "logo.png")],
        check=True,
    )
    print("logo.png written via rsvg-convert")
    return True


if __name__ == "__main__":
    if _try_cairosvg():
        sys.exit(0)
    if _try_inkscape():
        sys.exit(0)
    if _try_rsvg():
        sys.exit(0)

    print(
        "No SVG converter found. Install one of:\n"
        "  pip install cairosvg\n"
        "  apt install inkscape\n"
        "  apt install librsvg2-bin"
    )
    sys.exit(1)
