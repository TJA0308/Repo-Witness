"""Render the README's illustrated walkthrough (optional Pillow and resvg-py)."""

import io
from pathlib import Path

from PIL import Image
from resvg_py import svg_to_bytes


ASSETS = Path(__file__).resolve().parents[1] / "docs" / "assets"


if __name__ == "__main__":
    frames = []
    for filename in ("claim-trace.svg", "change-review.svg"):
        png = svg_to_bytes(svg_path=str(ASSETS / filename), width=1200)
        with Image.open(io.BytesIO(png)) as image:
            frames.append(image.convert("RGB"))
    # Equal vector canvases preserve every source line without cropping.
    frames[0].save(
        ASSETS / "sample-preview.gif", save_all=True, append_images=frames[1:],
        duration=[6500, 8000], loop=0, optimize=True,
    )
