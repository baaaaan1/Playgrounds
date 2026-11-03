"""Generate build/app.ico from the locally bundled Material Line brand SVG."""

from __future__ import annotations

import os
import sys
from io import BytesIO
from pathlib import Path


def main() -> int:
    # QtSvg rendering needs no display server, including on headless build hosts.
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PIL import Image
    from PyQt6.QtCore import QBuffer, QIODevice, QRectF, Qt
    from PyQt6.QtGui import QGuiApplication, QImage, QPainter
    from PyQt6.QtSvg import QSvgRenderer

    app = QGuiApplication.instance() or QGuiApplication(sys.argv)
    source = Path(__file__).resolve().parents[1] / "app/resources/line-md/chat-round-dots.svg"
    renderer = QSvgRenderer(source.read_bytes().replace(b"currentColor", b"#7c9cff"))
    if not renderer.isValid():
        raise RuntimeError(f"Invalid brand SVG: {source}")

    image = QImage(1024, 1024, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(Qt.GlobalColor.transparent)
    painter = QPainter(image)
    renderer.render(painter, QRectF(0, 0, 1024, 1024))
    painter.end()
    buffer = QBuffer()
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    if not image.save(buffer, "PNG"):
        raise RuntimeError("Cannot encode rendered brand icon")
    sizes = [(size, size) for size in (16, 24, 32, 48, 64, 128, 256)]
    target = Path(__file__).with_name("app.ico")
    with Image.open(BytesIO(bytes(buffer.data()))) as rendered:
        rendered.save(target, format="ICO", sizes=sizes)
    print(f"wrote {target}")
    del app
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
