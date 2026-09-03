#!/usr/bin/env python3
"""Generate the Windows application icon (src/audiflix/resources/audiflix.ico).

The icon is committed to the repository, so this script only needs to run when
the artwork changes. It requires Pillow, which is a development-only dependency:

    python -m pip install pillow
    python tools/make_icon.py

Design: a dark navy rounded square (high contrast against both light and dark
taskbars), an open book drawn in white and a play triangle - audio plus books.
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from PIL import Image, ImageDraw
except ImportError:  # pragma: no cover - developer tooling
    print("Pillow is required: python -m pip install pillow", file=sys.stderr)
    raise SystemExit(1) from None

ROOT = Path(__file__).resolve().parent.parent
TARGET = ROOT / "src" / "audiflix" / "resources" / "audiflix.ico"

BACKGROUND = (23, 37, 66, 255)     # deep navy
ACCENT = (255, 255, 255, 255)      # white
HIGHLIGHT = (94, 176, 255, 255)    # light blue

SIZES = [16, 24, 32, 48, 64, 128, 256]
CANVAS = 256


def draw_icon() -> Image.Image:
    image = Image.new("RGBA", (CANVAS, CANVAS), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    draw.rounded_rectangle([0, 0, CANVAS - 1, CANVAS - 1], radius=48, fill=BACKGROUND)

    # Open book: two pages meeting in the middle.
    left = [(38, 176), (38, 78), (122, 96), (122, 194)]
    right = [(218, 176), (218, 78), (134, 96), (134, 194)]
    draw.polygon(left, fill=ACCENT)
    draw.polygon(right, fill=ACCENT)
    draw.line([(128, 96), (128, 194)], fill=BACKGROUND, width=8)

    # Play triangle in the lower right corner, on a light blue disc.
    draw.ellipse([146, 140, 236, 230], fill=HIGHLIGHT)
    draw.polygon([(176, 162), (176, 208), (212, 185)], fill=BACKGROUND)

    return image


def main() -> int:
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    icon = draw_icon()
    icon.save(TARGET, format="ICO", sizes=[(size, size) for size in SIZES])
    print(f"Wrote {TARGET} ({TARGET.stat().st_size} bytes, sizes: {SIZES})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
