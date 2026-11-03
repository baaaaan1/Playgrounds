from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QWheelEvent
from PyQt6.QtWidgets import (
    QComboBox,
    QDoubleSpinBox,
    QSpinBox,
    QStyle,
    QStyleOptionComboBox,
    QStylePainter,
)

from . import icons


class NoWheelSpinBox(QSpinBox):
    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        event.ignore()


class ChevronComboBox(QComboBox):
    """Combo box with a bundled line-md chevron for custom themes."""

    def __init__(self, chevron_color: str, parent=None) -> None:
        super().__init__(parent)
        self._chevron = icons.icon("chevron-down", chevron_color, 14)

    def set_chevron_color(self, color: str) -> None:
        self._chevron = icons.icon("chevron-down", color, 14)
        self.update()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        if self.view().isVisible():
            super().wheelEvent(event)
        else:
            # Let the surrounding page scroll without changing the selection.
            event.ignore()

    def paintEvent(self, event) -> None:  # noqa: N802
        option = QStyleOptionComboBox()
        self.initStyleOption(option)
        # Keep the native field/label, but never draw a second platform arrow.
        option.subControls &= ~QStyle.SubControl.SC_ComboBoxArrow
        painter = QStylePainter(self)
        painter.drawComplexControl(QStyle.ComplexControl.CC_ComboBox, option)
        painter.drawControl(QStyle.ControlElement.CE_ComboBoxLabel, option)
        rect = self.style().subControlRect(
            QStyle.ComplexControl.CC_ComboBox, option,
            QStyle.SubControl.SC_ComboBoxArrow, self,
        )
        mode = QIcon.Mode.Normal if self.isEnabled() else QIcon.Mode.Disabled
        self._chevron.paint(painter, rect, Qt.AlignmentFlag.AlignCenter, mode)
        painter.end()
