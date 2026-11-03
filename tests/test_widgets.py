from __future__ import annotations

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtTest import QTest

from app.ui.widgets import ChevronComboBox, NoWheelDoubleSpinBox, NoWheelSpinBox


@pytest.mark.parametrize("focused", [False, True])
@pytest.mark.parametrize("editable", [False, True])
@pytest.mark.parametrize("delta", [-120, 120])
def test_closed_combo_ignores_wheel(qt_app, focused, editable, delta) -> None:
    combo = ChevronComboBox("#888888")
    combo.addItems(["First", "Second", "Third"])
    combo.setCurrentIndex(1)
    combo.setEditable(editable)
    combo.show()
    if focused:
        combo.setFocus()
    else:
        combo.clearFocus()
    qt_app.processEvents()
    try:
        position = combo.rect().center()
        event = QWheelEvent(
            QPointF(position), QPointF(combo.mapToGlobal(position)), QPoint(), QPoint(0, delta),
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase, False,
        )
        qt_app.sendEvent(combo, event)
        assert combo.currentIndex() == 1
        assert not event.isAccepted()
        combo.setFocus()
        QTest.keyClick(combo, Qt.Key.Key_Down)
        assert combo.currentIndex() == 2
    finally:
        combo.close()


def test_open_dropdown_list_still_scrolls(qt_app) -> None:
    combo = ChevronComboBox("#888888")
    combo.addItems([f"Model {index}" for index in range(100)])
    combo.show()
    combo.showPopup()
    qt_app.processEvents()
    try:
        view = combo.view()
        position = view.viewport().rect().center()
        event = QWheelEvent(
            QPointF(position), QPointF(view.viewport().mapToGlobal(position)),
            QPoint(), QPoint(0, -120),
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase, False,
        )
        qt_app.sendEvent(view.viewport(), event)
        assert combo.currentIndex() == 0
        assert view.verticalScrollBar().value() > 0
    finally:
        combo.hidePopup()
        combo.close()


@pytest.mark.parametrize("spin_type", [NoWheelSpinBox, NoWheelDoubleSpinBox])
@pytest.mark.parametrize("focused", [False, True])
@pytest.mark.parametrize("delta", [-120, 120])
def test_spin_box_ignores_wheel_but_keeps_keyboard_editing(
    qt_app, spin_type, focused, delta,
) -> None:
    spin = spin_type()
    spin.setRange(0, 100)
    spin.setValue(50)
    spin.show()
    if focused:
        spin.setFocus()
    else:
        spin.clearFocus()
    qt_app.processEvents()
    try:
        position = spin.rect().center()
        event = QWheelEvent(
            QPointF(position), QPointF(spin.mapToGlobal(position)), QPoint(), QPoint(0, delta),
            Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
            Qt.ScrollPhase.NoScrollPhase, False,
        )
        qt_app.sendEvent(spin, event)
        assert spin.value() == 50
        assert not event.isAccepted()
        spin.setFocus()
        QTest.keyClick(spin, Qt.Key.Key_Up)
        assert spin.value() == 51
        spin.selectAll()
        QTest.keyClicks(spin, "25")
        QTest.keyClick(spin, Qt.Key.Key_Return)
        assert spin.value() == 25
    finally:
        spin.close()
