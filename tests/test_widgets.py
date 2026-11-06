from __future__ import annotations

import pytest
from PyQt6.QtCore import QPoint, QPointF, Qt
from PyQt6.QtGui import QWheelEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QAbstractSpinBox, QStyle, QStyleFactory, QStyleOptionSpinBox

from app.ui import theme
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


@pytest.mark.parametrize("style_name", ["Fusion", "windowsvista", "windows11"])
@pytest.mark.parametrize("theme_name", ["dark", "light"])
@pytest.mark.parametrize("spin_type", [NoWheelSpinBox, NoWheelDoubleSpinBox])
def test_spin_buttons_use_flat_themed_chevrons_and_native_hit_targets(
    qt_app, spin_type, theme_name, style_name,
):
    style = QStyleFactory.create(style_name)
    if style is None:
        pytest.skip(f"Qt style {style_name} is unavailable")
    old_palette, old_qss = qt_app.palette(), qt_app.styleSheet()
    theme.apply(qt_app, theme_name)
    spin = spin_type()
    spin.setStyle(style)
    spin.setRange(0, 10)
    spin.setValue(5)
    spin.resize(220, 40)
    spin.show()
    qt_app.processEvents()
    try:
        option = QStyleOptionSpinBox()
        spin.initStyleOption(option)
        up, down = [spin.style().subControlRect(
            QStyle.ComplexControl.CC_SpinBox, option, control, spin,
        ) for control in (QStyle.SubControl.SC_SpinBoxUp, QStyle.SubControl.SC_SpinBoxDown)]
        assert up.width() == down.width() == 20
        assert up.center().x() == down.center().x()
        assert up.bottom() < down.top()
        assert spin.lineEdit().geometry().right() <= up.left()
        background = theme.tokens_for(theme_name)["surface"].lower()
        image = spin.grab().toImage()
        for rect in (up, down):
            assert image.pixelColor(rect.left() + 1, rect.center().y()).name() == background
            assert any(image.pixelColor(x, y).name() != background
                       for x in range(rect.center().x() - 5, rect.center().x() + 6)
                       for y in range(rect.center().y() - 5, rect.center().y() + 6))
        QTest.mouseClick(spin, Qt.MouseButton.LeftButton, pos=up.center())
        assert spin.value() == 6
        QTest.mouseClick(spin, Qt.MouseButton.LeftButton, pos=down.center())
        assert spin.value() == 5
        spin.setValue(10)
        at_max = spin.grab().toImage()
        QTest.mouseClick(spin, Qt.MouseButton.LeftButton, pos=up.center())
        assert spin.value() == 10
        spin.setValue(0)
        at_min = spin.grab().toImage()
        QTest.mouseClick(spin, Qt.MouseButton.LeftButton, pos=down.center())
        assert spin.value() == 0
        assert at_min.copy(up) != at_max.copy(up)
        assert at_min.copy(down) != at_max.copy(down)
        spin.setReadOnly(True)
        QTest.mouseClick(spin, Qt.MouseButton.LeftButton, pos=up.center())
        assert spin.value() == 0
        spin.setReadOnly(False)
        spin.setEnabled(False)
        QTest.mouseClick(spin, Qt.MouseButton.LeftButton, pos=up.center())
        assert spin.value() == 0
        spin.setEnabled(True)
        spin.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        assert not spin.grab().isNull()
    finally:
        spin.close()
        qt_app.setPalette(old_palette)
        qt_app.setStyleSheet(old_qss)
