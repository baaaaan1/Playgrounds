from __future__ import annotations

from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import QComboBox


class ChevronComboBox(QComboBox):
    """Combo box with a painted chevron so it stays visible on custom themes."""

    def __init__(self, chevron_color: str, parent=None) -> None:
        super().__init__(parent)
        self._chevron = QColor(chevron_color)

    def set_chevron_color(self, color: str) -> None:
        self._chevron = QColor(color)
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pen = QPen(self._chevron, 1.4)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        rect = self.rect()
        center_x = float(rect.right() - 15)
        center_y = float(rect.center().y())
        painter.drawLine(QPointF(center_x - 3.5, center_y - 1.5), QPointF(center_x, center_y + 2))
        painter.drawLine(QPointF(center_x, center_y + 2), QPointF(center_x + 3.5, center_y - 1.5))
        painter.end()
