"""Build the README slideshow from existing app screenshots (requires Pillow)."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps


ASSETS = Path(__file__).resolve().parents[1] / "docs" / "assets"
BACKGROUND = "#0b1018"


def font(size: int):
    for name in ("DejaVuSans.ttf", "C:/Windows/Fonts/arial.ttf"):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default(size=size)


def frame(filename: str, crop: tuple, number: int, title: str, caption: str):
    canvas = Image.new("RGB", (1080, 840), BACKGROUND)
    draw = ImageDraw.Draw(canvas)
    draw.text((40, 24), "REPOWITNESS / SAMPLE WALKTHROUGH", font=font(17), fill="#5eead4")
    draw.text((40, 57), title, font=font(29), fill="#e5edf7")
    draw.text((40, 103), caption, font=font(19), fill="#a2b1c6")
    with Image.open(ASSETS / filename) as screenshot:
        preview = ImageOps.contain(screenshot.crop(crop), (1000, 636), Image.Resampling.LANCZOS)
        canvas.paste(preview, ((1080 - preview.width) // 2, 149 + (636 - preview.height) // 2))
    draw.line((40, 796, 1040, 796), fill="#273449", width=1)
    draw.text((40, 809), "Actual app screenshots · synthetic sample · looping preview", font=font(15), fill="#a2b1c6")
    for index in range(2):
        x = 981 + index * 34
        draw.rounded_rectangle((x, 813, x + 23, 819), radius=3, fill="#5eead4" if index == number else "#273449")
    return canvas


if __name__ == "__main__":
    frames = [
        frame("workspace.png", (739, 498, 1206, 905), 0, "01  Review the claims", "Edit the suggested statements before running an audit."),
        frame("results.png", (206, 180, 1206, 884), 1, "02  Inspect the verdicts", "Each result includes reasoning and an evidence panel."),
    ]
    frames[0].save(ASSETS / "sample-preview.gif", save_all=True, append_images=frames[1:], duration=[4500, 6000], loop=0, optimize=True)
