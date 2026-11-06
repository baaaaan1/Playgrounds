from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QIcon, QPalette, QWheelEvent
from PyQt6.QtWidgets import (
    QAbstractSpinBox,
    QComboBox,
    QDoubleSpinBox,
    QSpinBox,
    QStyle,
    QStyleOptionComboBox,
    QStyleOptionSpinBox,
    QStylePainter,
)

from . import icons


def _paint_spin_box(widget: QSpinBox | QDoubleSpinBox) -> None:
    option = QStyleOptionSpinBox()
    widget.initStyleOption(option)
    controls = option.subControls
    # Retain native layout and hit testing, without platform-specific beveled step panels.
    option.subControls &= ~(QStyle.SubControl.SC_SpinBoxUp | QStyle.SubControl.SC_SpinBoxDown)
    painter = QStylePainter(widget)
    painter.drawComplexControl(QStyle.ComplexControl.CC_SpinBox, option)
    option.subControls = controls
    if option.buttonSymbols != QAbstractSpinBox.ButtonSymbols.NoButtons:
        arrow = icons.icon("chevron-down", option.palette.color(QPalette.ColorRole.Text).name(), 12)
        for control, step, rotate in (
            (QStyle.SubControl.SC_SpinBoxUp, QAbstractSpinBox.StepEnabledFlag.StepUpEnabled, True),
            (QStyle.SubControl.SC_SpinBoxDown, QAbstractSpinBox.StepEnabledFlag.StepDownEnabled, False),
        ):
            rect = widget.style().subControlRect(QStyle.ComplexControl.CC_SpinBox, option, control, widget)
            enabled = widget.isEnabled() and not widget.isReadOnly() and bool(widget.stepEnabled() & step)
            painter.save()
            painter.setOpacity(1.0 if enabled else 0.4)
            if rotate:
                painter.translate(rect.center())
                painter.rotate(180)
                painter.translate(-rect.center())
            arrow.paint(painter, rect, Qt.AlignmentFlag.AlignCenter)
            painter.restore()
    painter.end()


class NoWheelSpinBox(QSpinBox):
    def paintEvent(self, event) -> None:  # noqa: N802
        _paint_spin_box(self)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        event.ignore()


class NoWheelDoubleSpinBox(QDoubleSpinBox):
    def paintEvent(self, event) -> None:  # noqa: N802
        _paint_spin_box(self)

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
