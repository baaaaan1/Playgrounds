from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt6.QtSvg import QSvgRenderer

_ASSETS = Path(__file__).resolve().parents[1] / "resources" / "line-md"
_APP_ICON = Path(__file__).resolve().parents[2] / "build" / "icon.svg"
_MATERIAL_SYMBOLS = {
    "edit": "edit-outline",
    "regenerate": "refresh",
    "copy": "content-copy-outline",
}
_NAMES = {
    "plus": "plus",
    "send": "arrow-up",
    "stop": "square",
    "sliders": "cog",
    "trash": "trash",
    "theme": "sunny",
    "check": "confirm",
    "close": "close",
    "eye": "watch",
    "eye-off": "watch-off",
    "refresh": "rotate-270",
    "save": "download-outline",
    "minimize": "minus",
    "maximize": "square",
    "restore": "text-box-multiple",
    "chevron-down": "chevron-down",
    "sidebar": "sidebar",
}


@lru_cache(maxsize=32)
def _svg(name: str) -> bytes:
    # Fail explicitly rather than silently substituting an unrelated glyph.
    if name in _MATERIAL_SYMBOLS:
        return (_ASSETS.parent / "material-symbols" / f"{_MATERIAL_SYMBOLS[name]}.svg").read_bytes()
    return (_ASSETS / f"{_NAMES[name]}.svg").read_bytes()


def _paint(name: str, color: str, size: int) -> QPixmap:
    if size < 1:
        raise ValueError("Icon size must be positive")
    tint = QColor(color)
    if not tint.isValid():
        raise ValueError(f"Invalid icon color: {color}")
    svg = _svg(name).replace(b"currentColor", tint.name().encode("ascii"))
    renderer = QSvgRenderer(svg)
    if not renderer.isValid():
        raise ValueError(f"Invalid bundled SVG: {name}")
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setOpacity(tint.alphaF())
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pixmap


@lru_cache(maxsize=256)
def icon(name: str, color: str, size: int = 18) -> QIcon:
    """A bundled SVG icon with theme tinting and 1x/2x/3x raster variants."""
    result = QIcon()
    for scale in (1, 2, 3):
        pixmap = _paint(name, color, size * scale)
        pixmap.setDevicePixelRatio(scale)
        result.addPixmap(pixmap)
    return result


def clear_cache() -> None:
    icon.cache_clear()
    _svg.cache_clear()


@lru_cache(maxsize=1)
def app_icon() -> QIcon:
    """The original, full-color brand SVG, scalable at any display density."""
    return QIcon(str(_APP_ICON))
