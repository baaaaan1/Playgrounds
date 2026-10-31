"""Generate build/app.ico used by PyInstaller and the installer."""

from __future__ import annotations

import sys
from pathlib import Path

ACCENT = (124, 156, 255)
ACCENT_DARK = (59, 91, 219)
TEXT = (11, 16, 32)


def _load_font(px: int):
    from PIL import ImageFont

    for name in ("seguisb.ttf", "segoeuib.ttf", "arialbd.ttf"):
        try:
            return ImageFont.truetype(name, px)
        except OSError:
            continue
    return ImageFont.load_default()


def _draw(size: int):
    from PIL import Image, ImageDraw

    scale = 4
    canvas = size * scale
    image = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))

    gradient = Image.new("RGBA", (canvas, canvas))
    draw = ImageDraw.Draw(gradient)
    for y in range(canvas):
        for_x = y / max(1, canvas - 1)
        color = tuple(
            int(ACCENT[i] + (ACCENT_DARK[i] - ACCENT[i]) * for_x) for i in range(3)
        )
        draw.line([(0, y), (canvas, y)], fill=(*color, 255))

    mask = Image.new("L", (canvas, canvas), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        [0, 0, canvas - 1, canvas - 1], radius=int(canvas * 0.24), fill=255
    )
    image.paste(gradient, (0, 0), mask)

    font = _load_font(int(canvas * 0.56))
    pen = ImageDraw.Draw(image)
    box = pen.textbbox((0, 0), "P", font=font)
    x = (canvas - (box[2] - box[0])) / 2 - box[0]
    y = (canvas - (box[3] - box[1])) / 2 - box[1]
    pen.text((x, y), "P", font=font, fill=(*TEXT, 255))

    return image.resize((size, size), Image.Resampling.LANCZOS)


def main() -> int:
    from importlib.util import find_spec

    if find_spec("PIL") is None:
        print("Pillow not installed, skipping icon generation", file=sys.stderr)
        return 0

    target = Path(__file__).with_name("app.ico")
    sizes = [16, 24, 32, 48, 64, 128, 256]
    frames = [_draw(size) for size in sizes]
    frames[-1].save(target, format="ICO", sizes=[(s, s) for s in sizes])
    print(f"wrote {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
