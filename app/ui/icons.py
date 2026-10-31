from __future__ import annotations

from functools import lru_cache

from PyQt6.QtCore import QPointF, QRectF, Qt
from PyQt6.QtGui import (
    QColor,
    QFont,
    QIcon,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QPixmap,
)


def _paint(name: str, color: str, size: int) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

    pen = QPen(QColor(color))
    pen.setWidthF(max(1.4, size * 0.09))
    pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(Qt.BrushStyle.NoBrush)

    s = float(size)
    if name == "plus":
        painter.drawLine(QPointF(s * 0.28, s * 0.5), QPointF(s * 0.72, s * 0.5))
        painter.drawLine(QPointF(s * 0.5, s * 0.28), QPointF(s * 0.5, s * 0.72))
    elif name == "send":
        path = QPainterPath()
        path.moveTo(s * 0.5, s * 0.24)
        path.lineTo(s * 0.5, s * 0.76)
        path.moveTo(s * 0.31, s * 0.43)
        path.lineTo(s * 0.5, s * 0.24)
        path.lineTo(s * 0.69, s * 0.43)
        painter.drawPath(path)
    elif name == "stop":
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(QRectF(s * 0.33, s * 0.33, s * 0.34, s * 0.34), 2.5, 2.5)
    elif name == "sliders":
        for y, knob in ((s * 0.35, s * 0.38), (s * 0.65, s * 0.62)):
            painter.drawLine(QPointF(s * 0.22, y), QPointF(s * 0.78, y))
            painter.setBrush(QColor(color))
            painter.drawEllipse(QPointF(knob, y), 2.6, 2.6)
            painter.setBrush(Qt.BrushStyle.NoBrush)
    elif name == "trash":
        painter.drawLine(QPointF(s * 0.26, s * 0.32), QPointF(s * 0.74, s * 0.32))
        painter.drawLine(QPointF(s * 0.42, s * 0.32), QPointF(s * 0.43, s * 0.24))
        painter.drawLine(QPointF(s * 0.58, s * 0.32), QPointF(s * 0.57, s * 0.24))
        painter.drawLine(QPointF(s * 0.43, s * 0.24), QPointF(s * 0.57, s * 0.24))
        path = QPainterPath()
        path.moveTo(s * 0.33, s * 0.32)
        path.lineTo(s * 0.37, s * 0.78)
        path.lineTo(s * 0.63, s * 0.78)
        path.lineTo(s * 0.67, s * 0.32)
        painter.drawPath(path)
        painter.drawLine(QPointF(s * 0.44, s * 0.44), QPointF(s * 0.45, s * 0.68))
        painter.drawLine(QPointF(s * 0.56, s * 0.44), QPointF(s * 0.55, s * 0.68))
    elif name == "theme":
        painter.drawEllipse(QPointF(s * 0.5, s * 0.5), s * 0.24, s * 0.24)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(color))
        path = QPainterPath()
        path.moveTo(s * 0.5, s * 0.26)
        path.arcTo(QRectF(s * 0.26, s * 0.26, s * 0.48, s * 0.48), 90, 180)
        path.closeSubpath()
        painter.drawPath(path)
    elif name == "copy":
        painter.drawRoundedRect(QRectF(s * 0.36, s * 0.3, s * 0.36, s * 0.42), 2.0, 2.0)
        painter.drawRoundedRect(QRectF(s * 0.28, s * 0.22, s * 0.36, s * 0.42), 2.0, 2.0)
    elif name == "check":
        path = QPainterPath()
        path.moveTo(s * 0.28, s * 0.52)
        path.lineTo(s * 0.44, s * 0.68)
        path.lineTo(s * 0.73, s * 0.34)
        painter.drawPath(path)
    elif name == "close":
        painter.drawLine(QPointF(s * 0.34, s * 0.34), QPointF(s * 0.66, s * 0.66))
        painter.drawLine(QPointF(s * 0.66, s * 0.34), QPointF(s * 0.34, s * 0.66))
    else:
        painter.drawEllipse(QPointF(s * 0.5, s * 0.5), s * 0.24, s * 0.24)

    painter.end()
    return pixmap


@lru_cache(maxsize=128)
def icon(name: str, color: str, size: int = 18) -> QIcon:
    result = QIcon()
    result.addPixmap(_paint(name, color, size))
    result.addPixmap(_paint(name, color, size * 2))
    return result


def clear_cache() -> None:
    icon.cache_clear()


def _app_pixmap(size: int, accent: str, accent_hover: str, text_color: str) -> QPixmap:
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    gradient = QLinearGradient(QPointF(0, 0), QPointF(size, size))
    gradient.setColorAt(0.0, QColor(accent))
    gradient.setColorAt(1.0, QColor(accent_hover))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(gradient)
    painter.drawRoundedRect(QRectF(0, 0, size, size), size * 0.24, size * 0.24)

    font = QFont("Segoe UI Variable Display")
    font.setPixelSize(int(size * 0.56))
    font.setWeight(QFont.Weight.DemiBold)
    painter.setFont(font)
    painter.setPen(QColor(text_color))
    painter.drawText(QRectF(0, 0, size, size), Qt.AlignmentFlag.AlignCenter, "P")
    painter.end()
    return pixmap


def app_icon(accent: str, accent_hover: str, text_color: str) -> QIcon:
    result = QIcon()
    for size in (16, 24, 32, 48, 64, 128, 256):
        result.addPixmap(_app_pixmap(size, accent, accent_hover, text_color))
    return result

